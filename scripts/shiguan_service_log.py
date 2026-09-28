"""Size-bounded stdout logs for the Shiguan background service launchers."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import io
import json
import os
from datetime import datetime
from pathlib import Path
import tempfile
from typing import IO

from court_file_lock import atomic_write_text, file_lock


DEFAULT_MAX_BYTES = 8 * 1024 * 1024
LOCK_TIMEOUT_SECONDS = 2.0
TAIL_KEEP_BYTES = 256 * 1024
# The launcher and the daemon it spawns must agree on one log anchor; the name
# lives here so a daemon can bound the exact file its own stdout is sent to.
AUTOSYNC_LOG_NAME = "court-shiguan-autosync.log"
SERVICE_DAEMON_LOG_NAME = "court-shiguan-service-daemon.log"
JOURNAL_SUFFIX = ".rotation.json"
JOURNAL_SCHEMA = "court.shiguan_service_log_rotation.v1"
# Below the cap nothing happened, so a KEPT result is not journalled: rewriting
# it every daemon cycle would add no diagnosis and only churn the sidecar.
RECORDED_ACTIONS = frozenset(
    {"ROTATED", "ROTATED_INPLACE", "ROTATION_BLOCKED", "SKIPPED_LOCKED"}
)
DEGRADED_ACTIONS = frozenset({"ROTATED_INPLACE", "ROTATION_BLOCKED", "SKIPPED_LOCKED"})


def service_log_path(name: str) -> Path:
    return Path(tempfile.gettempdir()) / name


def rotation_journal_path(path: Path) -> Path:
    target = Path(path)
    return target.with_name(target.name + JOURNAL_SUFFIX)


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _kept(size: int | None) -> dict[str, object]:
    return {"action": "KEPT", "size_bytes": 0 if size is None else size, "archive": None}


def _skipped_locked(size: int) -> dict[str, object]:
    return {"action": "SKIPPED_LOCKED", "size_bytes": size, "archive": None}


def rotate_service_log(path: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, object]:
    target = Path(path)
    size = _file_size(target)
    if size is None:
        return {"action": "KEPT", "size_bytes": 0, "archive": None}
    if size <= max_bytes:
        return {"action": "KEPT", "size_bytes": size, "archive": None}
    archive = target.with_name(f"{target.name}.1")
    try:
        with file_lock(target.with_name(f"{target.name}.lock"), timeout=LOCK_TIMEOUT_SECONDS):
            locked_size = _file_size(target)
            if locked_size is None:
                return {"action": "KEPT", "size_bytes": 0, "archive": None}
            if locked_size <= max_bytes:
                return {"action": "KEPT", "size_bytes": locked_size, "archive": None}
            try:
                os.replace(target, archive)
            except OSError:
                return _rotate_in_place(target, locked_size, archive)
            return {"action": "ROTATED", "size_bytes": locked_size, "archive": str(archive)}
    except (TimeoutError, OSError):
        return {"action": "SKIPPED_LOCKED", "size_bytes": size, "archive": None}


def _stream_matches_log(stream: IO[str] | None, target: Path) -> bool:
    """True when ``stream`` provably writes to ``target``.

    Without that proof no in-place reclaim may run: truncating a file we are not
    appending to would leave the real holder writing at its own offset anyway.
    """

    if stream is None:
        return False
    try:
        descriptor = stream.fileno()
    except (AttributeError, ValueError, OSError, io.UnsupportedOperation):
        return False
    try:
        held = os.fstat(descriptor)
        actual = target.stat()
    except OSError:
        return False
    if not held.st_ino or not actual.st_ino:
        return False
    return (held.st_dev, held.st_ino) == (actual.st_dev, actual.st_ino)


def _repositionable(stream: IO[str]) -> bool:
    try:
        stream.seek(stream.tell())
        return True
    except (AttributeError, ValueError, OSError, io.UnsupportedOperation):
        return False


def _rewind(stream: IO[str]) -> bool:
    try:
        stream.seek(0)
        return True
    except (AttributeError, ValueError, OSError, io.UnsupportedOperation):
        return False


def rotate_held_service_log(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    live_stream: IO[str] | None = None,
) -> dict[str, object]:
    """Reclaim a log whose appending handle this process itself keeps open.

    The launcher hands ``<path>`` to a detached daemon and exits, so only the
    daemon can bound its own live log. Renaming that log either fails (Windows
    keeps an open handle against ``os.replace``) or moves the daemon's later
    writes into the archive (POSIX), so this path reclaims in place and then
    *rewinds the held stream to zero*: truncation does not move a file offset, so
    a write at the stale pre-truncation offset would punch a zero-filled hole
    into the fresh log. The rewind is what makes the in-place reclaim safe, so it
    runs only when ``live_stream`` provably is the log (same device and file
    index) and can be repositioned; otherwise the log is left intact and the
    caller sees ``ROTATION_BLOCKED``.
    """

    target = Path(path)
    size = _file_size(target)
    if size is None or size <= max_bytes:
        return _kept(size)
    try:
        if live_stream is not None:
            live_stream.flush()
    except (OSError, ValueError):
        pass
    if not _stream_matches_log(live_stream, target):
        return {"action": "ROTATION_BLOCKED", "size_bytes": size, "archive": None}
    try:
        with file_lock(target.with_name(f"{target.name}.lock"), timeout=LOCK_TIMEOUT_SECONDS):
            locked_size = _file_size(target)
            if locked_size is None or locked_size <= max_bytes:
                return _kept(locked_size)
            if not _repositionable(live_stream):
                return {"action": "ROTATION_BLOCKED", "size_bytes": locked_size, "archive": None}
            result = _rotate_in_place(target, locked_size, target.with_name(f"{target.name}.1"))
            if result.get("action") != "ROTATED_INPLACE":
                return result
            if not _rewind(live_stream):
                return {
                    "action": "ROTATION_BLOCKED",
                    "size_bytes": locked_size,
                    "archive": result.get("archive"),
                }
            return result
    except (TimeoutError, OSError):
        return _skipped_locked(size)


def _rotate_in_place(target: Path, size: int, archive: Path) -> dict[str, object]:
    """Reclaim space when a live holder blocks the rename.

    The launcher hands the log to a detached child that keeps the handle open,
    so the rename can fail exactly when rotation matters most. Keep a bounded
    tail for context, then truncate in place; a reclaim that is itself blocked
    reports ``ROTATION_BLOCKED`` so a degraded rotation stays observable instead
    of masquerading as an ordinary lock skip.

    The reclaim is all or nothing: when the tail cannot be read or cannot be
    archived, nothing is truncated and the caller gets ``ROTATION_BLOCKED`` with
    every original byte intact. Truncating a log whose tail never reached the
    archive would destroy the only copy of the region the tail was meant to keep.
    """

    blocked: dict[str, object] = {
        "action": "ROTATION_BLOCKED",
        "size_bytes": size,
        "archive": None,
    }
    try:
        with target.open("rb") as handle:
            handle.seek(max(0, size - TAIL_KEEP_BYTES))
            tail = handle.read(TAIL_KEEP_BYTES)
    except OSError:
        return blocked
    if not tail:
        return blocked
    try:
        archive.write_bytes(tail)
    except OSError:
        return blocked
    try:
        with target.open("r+b") as handle:
            handle.truncate(0)
    except OSError:
        return {"action": "ROTATION_BLOCKED", "size_bytes": size, "archive": str(archive)}
    return {"action": "ROTATED_INPLACE", "size_bytes": size, "archive": str(archive)}


def record_rotation(path: Path, result: dict[str, object]) -> Path | None:
    """Publish a rotation action to the bounded ``<log>.rotation.json`` journal.

    Launchers used to drop the ``rotate_service_log`` action, so a degraded
    reclaim (in place, blocked, lock skip) left no runtime trace at all. The
    journal is rewritten atomically under a fixed payload, never appended, so it
    cannot grow: its size is bounded by ``JOURNAL_SCHEMA`` plus one result.
    """

    action = str(result.get("action") or "")
    if action not in RECORDED_ACTIONS:
        return None
    target = Path(path)
    journal = rotation_journal_path(target)
    payload = {
        "schema": JOURNAL_SCHEMA,
        "log": target.name,
        "action": action,
        "size_bytes": result.get("size_bytes"),
        "archive": result.get("archive"),
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        atomic_write_text(journal, json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return None
    return journal


class DegradedLogSink:
    """Last-resort text sink when neither the log nor ``os.devnull`` opens.

    A service start must not depend on a writable log directory, so the sink
    swallows writes and only refuses ``fileno()``: callers that need a real
    descriptor fail loudly instead of silently logging into nowhere.
    """

    def __init__(self) -> None:
        self.closed = False

    def write(self, text: str) -> int:
        return len(text)

    def writelines(self, lines: object) -> None:
        for _line in lines:  # type: ignore[union-attr]
            pass

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    def fileno(self) -> int:
        raise io.UnsupportedOperation("degraded service log sink has no file descriptor")

    def __enter__(self) -> "DegradedLogSink":
        return self

    def __exit__(self, *_exc: object) -> bool:
        self.close()
        return False


def open_service_log(path: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> IO[str]:
    """Rotate, publish the action, then open the log for appending.

    Rotation used to run only on the launcher path and its action was discarded,
    so a degraded reclaim was invisible and a daemon that outlived its launcher
    grew without bound. The action now lands in the bounded rotation journal, and
    the open itself degrades instead of raising: an unwritable log target must
    never block a service start.
    """

    target = Path(path)
    record_rotation(target, rotate_service_log(target, max_bytes=max_bytes))
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        return target.open("a", encoding="utf-8")
    except OSError:
        pass
    try:
        return open(os.devnull, "a", encoding="utf-8")
    except OSError:
        return DegradedLogSink()


def maintain_service_log(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    live_stream: IO[str] | None = None,
) -> dict[str, object]:
    """Periodically bound the live log of a long-running process.

    Called from a daemon loop, so the log the daemon inherits from its launcher
    stays bounded for the whole lifetime of the process without an extra thread
    or process. Below the cap this is one ``stat``; above it the log is reclaimed
    in place and the held stream is rewound (see ``rotate_held_service_log``),
    and the action is published to the bounded rotation journal.
    """

    target = Path(path)
    result = rotate_held_service_log(target, max_bytes=max_bytes, live_stream=live_stream)
    record_rotation(target, result)
    return result
