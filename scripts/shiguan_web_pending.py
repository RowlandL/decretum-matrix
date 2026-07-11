"""Metadata-only inspection helpers for the Shiguan pending import queue.

Pending body files are enumerated from directory entries and ``lstat`` data but
are never opened here.  Only a strict, bounded, non-symlink metadata sidecar may
contribute content to the queue summary.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True
import json
import os
from pathlib import Path
import re
import stat
from shiguan_paths import references_root as shared_references_root
PENDING_IMPORT_METADATA_SUFFIX = ".metadata.json"
PENDING_IMPORT_METADATA_MAX_BYTES = 256 * 1024
PENDING_IMPORT_METADATA_FIELDS = {
    "id", "filename", "source_type", "status", "imported_at", "char_count",
    "estimated_tokens", "sha256", "suggested_processor",
}
PENDING_IMPORT_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def import_queue_root() -> Path:
    return shared_references_root() / "shiguan-imports"

def import_pending_root() -> Path:
    return import_queue_root() / "pending"

def import_processed_root() -> Path:
    return import_queue_root() / "processed"

def import_seen_path() -> Path:
    return import_queue_root() / "startup-seen.json"


def _same_open_file(before: os.stat_result, opened: os.stat_result) -> bool:
    """Reject a sidecar swapped between ``lstat`` and ``open``."""

    if before.st_dev != opened.st_dev:
        return False
    if before.st_ino and opened.st_ino and before.st_ino != opened.st_ino:
        return False
    return before.st_size == opened.st_size


def _read_strict_sidecar(path: Path) -> object | None:
    try:
        before = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(before.st_mode) or before.st_size > PENDING_IMPORT_METADATA_MAX_BYTES:
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size > PENDING_IMPORT_METADATA_MAX_BYTES
                or not _same_open_file(before, opened)
            ):
                return None
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _read_json_file(path: Path, default: object) -> object:
    try:
        if not path.is_file():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def pending_import_files() -> list[Path]:
    root = import_pending_root()
    try:
        if root.is_symlink() or not root.is_dir():
            return []
        paths: list[Path] = []
        with os.scandir(root) as entries:
            for entry in entries:
                lowered = entry.name.lower()
                if not lowered.endswith(".json") or lowered.endswith(PENDING_IMPORT_METADATA_SUFFIX):
                    continue
                try:
                    mode = entry.stat(follow_symlinks=False).st_mode
                except OSError:
                    continue
                if stat.S_ISREG(mode) or stat.S_ISLNK(mode):
                    paths.append(root / entry.name)
        return sorted(paths, key=lambda path: path.name)
    except OSError:
        return []


def pending_import_metadata_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}{PENDING_IMPORT_METADATA_SUFFIX}")

def read_pending_import(path: Path) -> dict[str, object] | None:
    value = _read_strict_sidecar(pending_import_metadata_path(path))
    filename = value.get("filename") if isinstance(value, dict) else None
    if not (
        isinstance(value, dict)
        and set(value) == PENDING_IMPORT_METADATA_FIELDS
        and isinstance(value.get("id"), str)
        and str(value.get("id")).strip()
        and isinstance(filename, str)
        and filename.strip()
        and Path(filename).name == filename
        and isinstance(value.get("source_type"), str)
        and str(value.get("source_type")).strip()
        and value.get("status") == "pending"
        and isinstance(value.get("imported_at"), str)
        and str(value.get("imported_at")).strip()
        and type(value.get("char_count")) is int
        and int(value.get("char_count")) >= 0
        and type(value.get("estimated_tokens")) is int
        and int(value.get("estimated_tokens")) >= 0
        and isinstance(value.get("sha256"), str)
        and PENDING_IMPORT_SHA256_RE.fullmatch(str(value.get("sha256")))
        and isinstance(value.get("suggested_processor"), str)
        and str(value.get("suggested_processor")).strip()
    ):
        return None
    return value


def import_seen_ids() -> set[str]:
    value = _read_json_file(import_seen_path(), {})
    if not isinstance(value, dict):
        return set()
    raw_ids = value.get("seen_ids")
    if not isinstance(raw_ids, list):
        return set()
    return {str(item) for item in raw_ids if str(item).strip()}


def public_pending_import(record: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in record.items()
        if key in PENDING_IMPORT_METADATA_FIELDS or key == "metadata_status"
    }


def optional_nonnegative_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None

def aggregate_import_metric(
    records: list[dict[str, object]],
    key: str,
) -> tuple[int | None, int, str]:
    known = [value for record in records if isinstance((value := optional_nonnegative_int(record.get(key))), int)]
    known_total = sum(known)
    if len(known) == len(records):
        return known_total, known_total, "complete"
    if known:
        return None, known_total, "partial"
    return None, 0, "unknown"


def import_queue_summary(limit: int = 8) -> dict[str, object]:
    seen_ids = import_seen_ids()
    records: list[dict[str, object]] = []
    unknown_metadata_count = 0
    for path in pending_import_files():
        record = read_pending_import(path)
        if record is None:
            unknown_metadata_count += 1
            record = {
                "id": path.stem,
                "filename": path.name,
                "source_type": path.suffix.lower().lstrip("."),
                "status": "pending",
                "imported_at": "",
                "char_count": None,
                "estimated_tokens": None,
                "sha256": "",
                "suggested_processor": "codex",
                "metadata_status": "unknown",
            }
        else:
            record = dict(record)
            record["metadata_status"] = "sidecar"
        records.append(record)
    public_records = [public_pending_import(record) for record in records]
    for record in public_records:
        record["is_new"] = str(record.get("id") or "") not in seen_ids
    new_records = [record for record in public_records if record.get("is_new")]
    total_tokens, known_tokens, token_status = aggregate_import_metric(records, "estimated_tokens")
    total_chars, known_chars, char_status = aggregate_import_metric(records, "char_count")
    new_tokens, new_known_tokens, new_token_status = aggregate_import_metric(new_records, "estimated_tokens")
    new_chars, new_known_chars, new_char_status = aggregate_import_metric(new_records, "char_count")
    unknown_estimated_tokens_count = sum(1 for record in records if optional_nonnegative_int(record.get("estimated_tokens")) is None)
    unknown_char_count_count = sum(1 for record in records if optional_nonnegative_int(record.get("char_count")) is None)
    if token_status == "complete":
        estimate_message = f"全部约 {total_tokens} tokens，新增约 {new_tokens} tokens。"
    elif token_status == "partial":
        estimate_message = f"token 估算 partial（已知至少 {known_tokens} tokens；{unknown_estimated_tokens_count} 份缺少可用 estimated_tokens，其中 {unknown_metadata_count} 份缺少有效 metadata sidecar）。"
    else:
        estimate_message = f"token 估算 unknown（{unknown_estimated_tokens_count} 份缺少可用 estimated_tokens，其中 {unknown_metadata_count} 份缺少有效 metadata sidecar）。"
    return {
        "pending_count": len(records),
        "new_count": len(new_records),
        "estimated_tokens": total_tokens,
        "known_estimated_tokens": known_tokens,
        "estimated_tokens_status": token_status,
        "new_estimated_tokens": new_tokens,
        "new_known_estimated_tokens": new_known_tokens,
        "new_estimated_tokens_status": new_token_status,
        "char_count": total_chars,
        "known_char_count": known_chars,
        "char_count_status": char_status,
        "new_char_count": new_chars,
        "new_known_char_count": new_known_chars,
        "new_char_count_status": new_char_status,
        "unknown_metadata_count": unknown_metadata_count,
        "unknown_estimated_tokens_count": unknown_estimated_tokens_count,
        "unknown_char_count_count": unknown_char_count_count,
        "queue_root": str(import_pending_root()),
        "seen_path": str(import_seen_path()),
        "samples": public_records[:limit],
        "new_samples": new_records[:limit],
        "has_pending": bool(records),
        "has_new": bool(new_records),
        "startup_message": (
            f"发现 {len(records)} 份待 Codex 处理导入材料，其中新增 {len(new_records)} 份；"
            f"{estimate_message}"
            if records
            else "没有待 Codex 处理的导入材料。"
        ),
    }
