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


if os.name == "nt":
    import ctypes
    from ctypes import wintypes
    import msvcrt

    class _OVERLAPPED(ctypes.Structure):
        _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE)]

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _LOCK_FILE_EX = _KERNEL32.LockFileEx
    _LOCK_FILE_EX.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                             wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_OVERLAPPED)]
    _LOCK_FILE_EX.restype = wintypes.BOOL
    _UNLOCK_FILE_EX = _KERNEL32.UnlockFileEx
    _UNLOCK_FILE_EX.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                               wintypes.DWORD, ctypes.POINTER(_OVERLAPPED)]
    _UNLOCK_FILE_EX.restype = wintypes.BOOL


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


def _try_os_lock(handle: BinaryIO, *, shared: bool = False) -> bool:
    handle.seek(0)
    if os.name == "nt":
        # CRT LK_NBRLCK equals LK_NBLCK; only LockFileEx supplies a true shared
        # byte lock. Offset zero / length one stays interoperable with old CRT.
        flags = 0x00000001 | (0 if shared else 0x00000002)  # FAIL_IMMEDIATELY / EXCLUSIVE_LOCK
        overlapped = _OVERLAPPED()
        if not _LOCK_FILE_EX(msvcrt.get_osfhandle(handle.fileno()), flags, 0, 1, 0,
                             ctypes.byref(overlapped)):
            error = ctypes.get_last_error()
            if error == 33:  # ERROR_LOCK_VIOLATION only; other failures are not contention.
                return False
            raise ctypes.WinError(error)
        return True

    import fcntl

    mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    try:
        fcntl.flock(handle.fileno(), mode | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            return False
        raise
    return True


def _unlock_os(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        overlapped = _OVERLAPPED()
        if not _UNLOCK_FILE_EX(msvcrt.get_osfhandle(handle.fileno()), 0, 1, 0,
                               ctypes.byref(overlapped)):
            raise ctypes.WinError(ctypes.get_last_error())
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def file_lock(
    path: Path,
    timeout: float = 30.0,
    poll_interval: float = 0.05,
    *,
    shared: bool = False,
) -> Iterator[None]:
    """Acquire a per-path thread and process lock.

    ``shared=False`` (the default) takes the exclusive byte lock and serializes
    every holder. ``shared=True`` takes the shared byte lock instead, so any
    number of holders may hold the same path at once: use it for idempotent
    seed/maintenance writes whose correctness does not depend on being the only
    writer, and keep the exclusive form for read-modify-write transitions. The
    two forms exclude each other in both directions even though shared holders
    do not exclude one another.

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
    modes = getattr(_THREAD_STATE, "modes", None)
    if modes is None:
        modes = {}
        _THREAD_STATE.modes = modes
    if depths.get(key, 0):
        if modes[key] and not shared:
            local.release()
            raise ValueError("cannot upgrade a reentrant shared file lock to exclusive")
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
            if _try_os_lock(handle, shared=shared):
                os_locked = True
                depths[key] = 1
                modes[key] = shared
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
            modes.pop(key, None)
            local.release()


def atomic_write_text(
    path: Path,
    text: str,
    encoding: str = "utf-8",
    newline: str = "\n",
) -> None:
    """Encode text using the same newline rules as ``open``, then replace atomically."""
    if newline not in (None, "", "\n", "\r", "\r\n"):
        raise ValueError(f"illegal newline value: {newline!r}")
    separator = os.linesep if newline is None else newline
    if separator and separator != "\n":
        text = text.replace("\n", separator)
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_bytes(path: Path, data: bytes, *, no_clobber: bool = False) -> None:
    """Durably write bytes to a sibling temp file, then atomically replace.

    Threads are serialized per target. Cross-process replace collisions on
    Windows are transiently retried; callers that need read-modify-write
    semantics must still hold ``file_lock`` around the whole transaction.
    ``no_clobber=True`` publishes the complete candidate with Windows rename
    or a POSIX hard link, raising ``FileExistsError`` if the name is occupied.
    Other OS errors
    propagate; there is no fallback to replacement or a partial final file.
    """

    target = Path(path)
    with _local_lock(target):
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_temp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
        temp_path = Path(raw_temp)
        try:
            handle = os.fdopen(fd, "wb")
            fd = None  # fdopen owns it now; its closed number may be reused.
            with handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if no_clobber:
                if os.name == "nt":
                    os.rename(temp_path, target)  # Windows rename never replaces.
                else:
                    os.link(temp_path, target, follow_symlinks=False)
                    temp_path.unlink()
            else:
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
            if fd is not None:
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
