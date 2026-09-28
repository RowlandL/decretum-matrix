"""Size-bounded stdout logs for the Shiguan background service launchers."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import os
from pathlib import Path
import tempfile
from typing import IO

from court_file_lock import file_lock


DEFAULT_MAX_BYTES = 8 * 1024 * 1024
LOCK_TIMEOUT_SECONDS = 2.0


def service_log_path(name: str) -> Path:
    return Path(tempfile.gettempdir()) / name


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


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
            os.replace(target, archive)
            return {"action": "ROTATED", "size_bytes": locked_size, "archive": str(archive)}
    except (TimeoutError, OSError):
        return {"action": "SKIPPED_LOCKED", "size_bytes": size, "archive": None}


def open_service_log(path: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> IO[str]:
    target = Path(path)
    rotate_service_log(target, max_bytes=max_bytes)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target.open("a", encoding="utf-8")
