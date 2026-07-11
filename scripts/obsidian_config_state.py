"""Single-writer CAS state for the local Obsidian sync configuration.

The config may contain a local REST API key, so public projections never expose
the value.  Writers patch named top-level fields through one lock and a
three-way comparison; unrelated concurrent fields survive while same-field
drift fails closed.
"""

from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Callable
import uuid

sys.dont_write_bytecode = True

from court_file_lock import atomic_write_text, file_lock
from shiguan_paths import reference_path


CONFIG_SCHEMA = "court.obsidian.sync_config.v2"
CONFIG_MAX_BYTES = 1024 * 1024
RESERVED_FIELDS = frozenset({"schema", "revision", "transaction_id", "updated_at"})


def config_path() -> Path:
    return reference_path("obsidian-sync", "config.json")


def config_lock_path() -> Path:
    return reference_path("court-runtime", "obsidian-config.lock")


_DEFAULT_CONFIG_PATH = config_path
_DEFAULT_CONFIG_LOCK_PATH = config_lock_path


def _is_reparse(stat_result: os.stat_result) -> bool:
    attributes = int(getattr(stat_result, "st_file_attributes", 0) or 0)
    flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(attributes & flag)


def _validate_file(path: Path) -> None:
    if not path.exists():
        return
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
        raise RuntimeError("Obsidian sync config must not be a symlink or reparse point")
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError("Obsidian sync config must be a regular file")
    if info.st_size > CONFIG_MAX_BYTES:
        raise RuntimeError("Obsidian sync config exceeds the size limit")


def _normalized(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError("Obsidian sync config root must be an object")
    result = copy.deepcopy(value)
    schema = result.get("schema")
    if schema not in {None, "", CONFIG_SCHEMA}:
        raise RuntimeError("Obsidian sync config schema is unsupported")
    revision = result.get("revision", 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise RuntimeError("Obsidian sync config revision is invalid")
    transaction_id = result.get("transaction_id", "")
    if not isinstance(transaction_id, str):
        raise RuntimeError("Obsidian sync config transaction_id is invalid")
    result["schema"] = CONFIG_SCHEMA
    result["revision"] = revision
    result["transaction_id"] = transaction_id
    result["updated_at"] = str(result.get("updated_at") or "")
    return result


def read_config_snapshot(path: Path | None = None) -> dict[str, object]:
    target = Path(path or config_path())
    if not target.exists():
        return _normalized({})
    _validate_file(target)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Obsidian sync config is unreadable or malformed") from exc
    return _normalized(value)


def config_digest(value: dict[str, object]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def public_config(value: dict[str, object]) -> dict[str, object]:
    result = {key: copy.deepcopy(item) for key, item in value.items() if key != "api_key"}
    result["has_api_key"] = bool(value.get("api_key"))
    return result


def _field_changed(base: dict[str, object], current: dict[str, object], field: str) -> bool:
    return (field in base) != (field in current) or base.get(field) != current.get(field)


def patch_config(
    changes: dict[str, object],
    *,
    config_path: Path | None = None,
    lock_path: Path | None = None,
    base_snapshot: dict[str, object] | None = None,
    precommit_hook: Callable[[Path], None] | None = None,
    timeout: float = 15.0,
) -> dict[str, object]:
    if not isinstance(changes, dict):
        raise TypeError("Obsidian sync config changes must be an object")
    reserved = sorted(RESERVED_FIELDS.intersection(changes))
    if reserved:
        raise ValueError("reserved Obsidian sync config fields cannot be patched: " + ", ".join(reserved))
    target = Path(config_path or _DEFAULT_CONFIG_PATH())
    lock = Path(lock_path or _DEFAULT_CONFIG_LOCK_PATH())
    base = _normalized(base_snapshot) if base_snapshot is not None else read_config_snapshot(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(lock, timeout=timeout):
        if precommit_hook is not None:
            precommit_hook(target)
        current = read_config_snapshot(target)
        conflicts = sorted(
            field
            for field, desired in changes.items()
            if _field_changed(base, current, field) and current.get(field) != desired
        )
        if conflicts:
            return {
                "schema": "court.obsidian.sync_config.patch_result.v1",
                "conflict": True,
                "conflict_fields": conflicts,
                "written": False,
                "post_write_verified": False,
                "base_revision": int(base.get("revision") or 0),
                "current_revision": int(current.get("revision") or 0),
                "base_digest": config_digest(base),
                "current_digest": config_digest(current),
            }
        committed = copy.deepcopy(current)
        committed.update(copy.deepcopy(changes))
        committed["schema"] = CONFIG_SCHEMA
        committed["revision"] = int(current.get("revision") or 0) + 1
        committed["transaction_id"] = str(uuid.uuid4())
        committed["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        atomic_write_text(
            target,
            json.dumps(committed, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        )
        verified = read_config_snapshot(target)
        post_write_verified = verified == committed
        if not post_write_verified:
            raise RuntimeError("Obsidian sync config post-write verification failed")
        return {
            "schema": "court.obsidian.sync_config.patch_result.v1",
            "conflict": False,
            "conflict_fields": [],
            "written": True,
            "post_write_verified": True,
            "base_revision": int(base.get("revision") or 0),
            "current_revision": int(current.get("revision") or 0),
            "committed_revision": int(verified.get("revision") or 0),
            "transaction_id": str(verified.get("transaction_id") or ""),
            "base_digest": config_digest(base),
            "current_digest": config_digest(current),
            "committed_digest": config_digest(verified),
        }
