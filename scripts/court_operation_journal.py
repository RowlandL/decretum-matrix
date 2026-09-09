"""Disposable idempotency/recovery receipts for court operations.

The current task in ``tasks.json`` and its append-only event remain authoritative.
This module stores only replay/recovery receipts and crash markers; deleting the
journal does not delete the task operation record.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import uuid
from collections.abc import Mapping

sys.dont_write_bytecode = True

from court_file_lock import atomic_write_text, file_lock


JOURNAL_SCHEMA = "court.operation_journal.v2"
LEGACY_JOURNAL_SCHEMA = "court.operation_journal.v1"
MARKER_SCHEMA = "court.paired_ledger_mutation.v2"
LEGACY_MARKER_SCHEMA = "court.paired_ledger_mutation.v1"
OPERATION_V2_NAMESPACE = "v2"
OPERATION_BINDING_FIELDS = frozenset(
    {
        "operation_id",
        "task_id",
        "operation_kind",
        "case_ref",
        "actor",
        "role",
        "expected_task_revision",
        "target_ref",
        "request_schema",
    }
)
_REFERENCE_BODY_FIELDS = frozenset(
    {"payload", "payload_file", "body", "raw", "raw_body", "result", "raw_result"}
)
_PHASE_ORDER = {
    "PREPARED": 10,
    "ALLOCATED": 20,
    "ARCHIVE_COMMITTED": 30,
    "TASK_WRITTEN": 40,
    "EVENT_WRITTEN": 50,
    "COMMITTED": 60,
    "ROLLED_BACK": 60,
    "mcp-call": 60,
}


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


def _reference_has_body(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).strip().casefold() in _REFERENCE_BODY_FIELDS
            or _reference_has_body(child)
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_reference_has_body(child) for child in value)
    return False


def _reference(value: object, field: str) -> object:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"operation_binding_{field}_invalid")
    if _reference_has_body(value):
        raise ValueError(f"operation_binding_{field}_body_forbidden")
    try:
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"operation_binding_{field}_invalid") from exc
    return deepcopy(dict(value))


def normalize_operation_binding(
    value: object,
    *,
    operation_id: object | None = None,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("operation_binding_required")
    if set(value) != OPERATION_BINDING_FIELDS:
        raise ValueError("operation_binding_fields_invalid")
    canonical = canonical_operation_id(value.get("operation_id"))
    if operation_id is not None and canonical != canonical_operation_id(operation_id):
        raise ValueError("operation_binding_operation_id_mismatch")
    text_fields = ("task_id", "operation_kind", "actor", "role", "request_schema")
    normalized: dict[str, object] = {"operation_id": canonical}
    for field in text_fields:
        text = value.get(field)
        if not isinstance(text, str) or not text.strip() or any(
            character in text for character in "\x00\r\n"
        ):
            raise ValueError(f"operation_binding_{field}_invalid")
        normalized[field] = text.strip().lower() if field in {"operation_kind", "role", "request_schema"} else text.strip()
    revision = value.get("expected_task_revision")
    if (
        not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision < 0
    ):
        raise ValueError("operation_binding_expected_task_revision_invalid")
    normalized["expected_task_revision"] = revision
    normalized["case_ref"] = _reference(value.get("case_ref"), "case_ref")
    normalized["target_ref"] = _reference(value.get("target_ref"), "target_ref")
    return normalized


def journal_path(root: Path, operation_id: object) -> Path:
    canonical = canonical_operation_id(operation_id)
    return Path(root) / "operation-journal" / OPERATION_V2_NAMESPACE / f"{canonical}.json"


def marker_path(root: Path, operation_id: object) -> Path:
    canonical = canonical_operation_id(operation_id)
    return Path(root) / "operation-markers" / OPERATION_V2_NAMESPACE / f"{canonical}.json"


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
    operation_binding: Mapping[str, object],
    phase: str,
    receipt_ref: object | None,
    updated_at: str,
    committed_task_revision: int | None = None,
    event_id: str | None = None,
    receipt_metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    canonical = canonical_operation_id(operation_id)
    binding = normalize_operation_binding(operation_binding, operation_id=canonical)
    if not isinstance(phase, str) or phase not in _PHASE_ORDER:
        raise ValueError("operation_phase_invalid")
    if committed_task_revision is not None and (
        not isinstance(committed_task_revision, int)
        or isinstance(committed_task_revision, bool)
        or committed_task_revision < 1
    ):
        raise ValueError("operation_committed_task_revision_invalid")
    if event_id is not None and (
        not isinstance(event_id, str) or not event_id.strip()
    ):
        raise ValueError("operation_event_id_invalid")
    if receipt_ref is not None:
        if isinstance(receipt_ref, str):
            if not receipt_ref.strip() or any(
                character in receipt_ref for character in "\x00\r\n"
            ):
                raise ValueError("operation_receipt_ref_invalid")
            normalized_receipt_ref: object = receipt_ref.strip()
        else:
            normalized_receipt_ref = _reference(receipt_ref, "receipt_ref")
    else:
        normalized_receipt_ref = None
    if receipt_metadata is not None:
        if not isinstance(receipt_metadata, Mapping) or _reference_has_body(
            receipt_metadata
        ):
            raise ValueError("operation_receipt_metadata_invalid")
        try:
            json.dumps(
                receipt_metadata,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("operation_receipt_metadata_invalid") from exc
        normalized_receipt_metadata: dict[str, object] | None = deepcopy(
            dict(receipt_metadata)
        )
    else:
        normalized_receipt_metadata = None
    path = journal_path(root, canonical)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with file_lock(lock_path, timeout=30.0, poll_interval=0.02):
        existing = load_json(path)
        if existing is not None:
            if existing.get("schema") == LEGACY_JOURNAL_SCHEMA:
                raise ValueError("legacy_operation_requires_explicit_recovery")
            if existing.get("schema") != JOURNAL_SCHEMA:
                raise ValueError("operation_journal_corrupt")
            try:
                existing_binding = normalize_operation_binding(
                    existing.get("operation_binding"), operation_id=canonical
                )
            except ValueError as exc:
                raise ValueError("operation_journal_corrupt") from exc
            if existing_binding != binding:
                raise ValueError("operation_binding_conflict")
            previous_phase = existing.get("phase")
            if not isinstance(previous_phase, str) or previous_phase not in _PHASE_ORDER:
                raise ValueError("operation_journal_corrupt")
            if previous_phase == "ROLLED_BACK" and phase != "ROLLED_BACK":
                raise ValueError("operation_phase_regression")
            if phase != "ROLLED_BACK" and _PHASE_ORDER[phase] < _PHASE_ORDER[previous_phase]:
                raise ValueError("operation_phase_regression")
        record: dict[str, object] = {
            "schema": JOURNAL_SCHEMA,
            "operation_id": canonical,
            "operation_binding": binding,
            "phase": phase,
            "updated_at": updated_at,
        }
        if normalized_receipt_ref is not None:
            record["receipt_ref"] = normalized_receipt_ref
        elif existing is not None and "receipt_ref" in existing:
            record["receipt_ref"] = existing["receipt_ref"]
        if normalized_receipt_metadata is not None:
            record["receipt"] = normalized_receipt_metadata
        elif existing is not None and "receipt" in existing:
            record["receipt"] = existing["receipt"]
        if committed_task_revision is not None:
            record["committed_task_revision"] = committed_task_revision
        elif existing is not None and "committed_task_revision" in existing:
            record["committed_task_revision"] = existing["committed_task_revision"]
        if event_id is not None:
            record["event_id"] = event_id.strip()
        elif existing is not None and "event_id" in existing:
            record["event_id"] = existing["event_id"]
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
