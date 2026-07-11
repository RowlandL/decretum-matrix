"""Crash-safe cross-process file locking and atomic text replacement.

The OS owns the cross-process lock, so an abnormal process exit releases it.
A per-path in-process lock is layered on top because POSIX ``flock`` locks are
process-scoped and therefore do not serialize threads in the same process.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from contextlib import contextmanager
import errno
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import BinaryIO, Iterator


_LOCAL_LOCKS_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[str, threading.RLock] = {}
_THREAD_STATE = threading.local()


def _path_key(path: Path) -> str:
    try:
        value = str(path.resolve())
    except OSError:
        value = str(path.absolute())
    return value.casefold() if os.name == "nt" else value


def _local_lock(path: Path) -> threading.RLock:
    key = _path_key(path)
    with _LOCAL_LOCKS_GUARD:
        lock = _LOCAL_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCAL_LOCKS[key] = lock
        return lock


def _thread_depths() -> dict[str, int]:
    depths = getattr(_THREAD_STATE, "depths", None)
    if depths is None:
        depths = {}
        _THREAD_STATE.depths = depths
    return depths


def _prepare_lock_file(handle: BinaryIO) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)


def _try_os_lock(handle: BinaryIO) -> bool:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK, errno.EPERM}:
                return False
            raise
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            return False
        raise
    return True


def _unlock_os(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def file_lock(
    path: Path,
    timeout: float = 30.0,
    poll_interval: float = 0.05,
) -> Iterator[None]:
    """Acquire an exclusive per-path thread and process lock.

    ``TimeoutError`` is raised if either layer cannot be acquired before the
    common deadline. The lock file is persistent; ownership is the OS byte lock,
    not the presence of the file.
    """

    target = Path(path)
    key = _path_key(target)
    timeout = max(0.0, float(timeout))
    poll_interval = max(0.001, float(poll_interval))
    deadline = time.monotonic() + timeout
    local = _local_lock(target)
    local_timeout = max(0.0, deadline - time.monotonic())
    if not local.acquire(timeout=local_timeout):
        raise TimeoutError(f"timed out waiting for in-process lock: {target}")

    depths = _thread_depths()
    if depths.get(key, 0):
        depths[key] += 1
        try:
            yield
        finally:
            depths[key] -= 1
            local.release()
        return

    handle: BinaryIO | None = None
    os_locked = False
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = target.open("a+b", buffering=0)
        _prepare_lock_file(handle)
        while True:
            if _try_os_lock(handle):
                os_locked = True
                depths[key] = 1
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for cross-process lock: {target}")
            time.sleep(min(poll_interval, remaining))
        yield
    finally:
        try:
            if handle is not None:
                try:
                    if os_locked:
                        _unlock_os(handle)
                finally:
                    handle.close()
        finally:
            depths.pop(key, None)
            local.release()


def atomic_write_text(
    path: Path,
    text: str,
    encoding: str = "utf-8",
    newline: str = "\n",
) -> None:
    """Durably write text to a sibling temp file, then atomically replace.

    Threads are serialized per target. Cross-process replace collisions on
    Windows are transiently retried; callers that need read-modify-write
    semantics must still hold ``file_lock`` around the whole transaction.
    """

    target = Path(path)
    with _local_lock(target):
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_temp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
        temp_path = Path(raw_temp)
        try:
            with os.fdopen(fd, "w", encoding=encoding, newline=newline) as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            if target.exists():
                try:
                    os.chmod(temp_path, target.stat().st_mode)
                except OSError:
                    pass

            replace_deadline = time.monotonic() + 2.0
            while True:
                try:
                    os.replace(temp_path, target)
                    break
                except PermissionError:
                    if time.monotonic() >= replace_deadline:
                        raise
                    time.sleep(0.01)
            fsync_parent_directory(target.parent)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                temp_path.unlink()
            except OSError:
                pass
            raise


def fsync_parent_directory(path: Path) -> bool:
    """Best-effort directory durability after an atomic replace.

    POSIX filesystems generally support fsync on a directory descriptor.
    Windows/Python combinations may reject opening a directory this way; the
    replace remains atomic, and callers receive ``False`` rather than a false
    durability claim.
    """

    directory = Path(path)
    flags = os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0) or 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(str(directory), flags)
        os.fsync(descriptor)
        return True
    except OSError:
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def shiguan_write_lock_path() -> Path:
    """Return the single shared write-lock path for authoritative Shiguan data."""

    from shiguan_paths import reference_path

    return reference_path("court-runtime", "shiguan-write.lock")
