"""Disposable idempotency/recovery receipts for court operations.

The current task in ``tasks.json`` and its append-only event remain authoritative.
This module stores only replay/recovery receipts and crash markers; deleting the
journal does not delete the task operation record.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True

from court_file_lock import atomic_write_text, file_lock


JOURNAL_SCHEMA = "court.operation_journal.v1"
MARKER_SCHEMA = "court.paired_ledger_mutation.v1"


def canonical_operation_id(value: object) -> str:
    text = str(value or "").strip().lower()
    try:
        parsed = uuid.UUID(text)
    except (ValueError, AttributeError) as exc:
        raise ValueError("invalid_operation_id") from exc
    canonical = str(parsed)
    if text != canonical:
        raise ValueError("invalid_operation_id")
    return canonical


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def payload_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _key(operation_id: str) -> str:
    return hashlib.sha256(operation_id.encode("utf-8")).hexdigest()


def journal_path(root: Path, operation_id: object) -> Path:
    canonical = canonical_operation_id(operation_id)
    return Path(root) / "operation-journal" / f"{_key(canonical)}.json"


def marker_path(root: Path, operation_id: object) -> Path:
    canonical = canonical_operation_id(operation_id)
    return Path(root) / "operation-markers" / f"{_key(canonical)}.json"


def load_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("operation_journal_corrupt")
    return value


def write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def write_journal(
    root: Path,
    *,
    operation_id: object,
    payload_digest: str,
    task_id: str,
    phase: str,
    receipt: dict[str, object] | None,
    updated_at: str,
) -> dict[str, object]:
    canonical = canonical_operation_id(operation_id)
    path = journal_path(root, canonical)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with file_lock(lock_path, timeout=30.0, poll_interval=0.02):
        existing = load_json(path)
        if existing is not None and existing.get("payload_sha256") != payload_digest:
            raise ValueError("operation_payload_conflict")
        record: dict[str, object] = {
            "schema": JOURNAL_SCHEMA,
            "operation_id": canonical,
            "payload_sha256": payload_digest,
            "task_id": task_id,
            "phase": phase,
            "receipt": receipt,
            "updated_at": updated_at,
        }
        if existing and existing.get("created_at"):
            record["created_at"] = existing["created_at"]
        else:
            record["created_at"] = updated_at
        write_json(path, record)
    return record


def remove_marker(root: Path, operation_id: object) -> None:
    path = marker_path(root, operation_id)
    if path.exists():
        path.unlink()
