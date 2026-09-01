"""Metadata-only, fail-closed gate for the shared Shiguan migration.

This module evaluates whether migration preflight or post-cutover evidence is
complete.  It does not move, copy, delete, hash, open, or mark pending bodies,
and the small ``scan`` CLI deliberately supplies no trusted binding or stable
scan evidence yet.
"""



from __future__ import annotations

# A+B layering: real module lives in scripts/services/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True

from typing import Any, Callable
from uuid import UUID

from court_safe_fs import SafeFilesystemError, validate_relative_path
from shiguan_paths import (
    LOCAL_AUTHORITY_REALM_SCHEMA,
    LOCAL_AUTHORITY_REQUIRED_PRODUCTION_GATES,
    _valid_empty_binding_snapshot,
)

RESULT_SCHEMA = "court.shiguan_migration_gate.result.v1"
AUTHORITY_ADMISSION_SCHEMA = "court.shiguan_authority_realm_admission.result.v1"
PENDING_BLOCK = "MIGRATION_BLOCKED_PENDING_BODIES"
READY = "READY_TO_MIGRATE"
POST_CUTOVER_VERIFIED = "POST_CUTOVER_VERIFIED"
SIDECAR_SUFFIXES = (".metadata.json", ".meta.json")
PROTECTED_PATHS = (
    "references/shiguan-index.jsonl",
    "references/shiguan-knowledge-graph.json",
    "references/shiguan-tree/_index.md",
    "references/shiguan-tree/capability-index/_index.md",
)
HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
INVENTORY_FIELDS = (
    "canonical_source_root",
    "source_volume_serial",
    "source_directory_id",
    "file_count",
    "total_bytes",
    "newest_mtime_utc",
    "inventory_digest",
    "exclusion_policy_id",
)
READY_RECEIPT_TTL_SECONDS = 300
EVIDENCE_TTL_SECONDS = 300
DEFAULT_PROTECTED_ROOT = (
    Path.home()
    / ".agents"
    / "skills"
    / "court-capability-router"
    / "references"
).resolve(strict=False)


def _result(
    *,
    phase: str,
    status: str,
    allowed: bool,
    reason_codes: list[str],
    pending_count: int | None,
) -> dict[str, object]:
    return {
        "schema": RESULT_SCHEMA,
        "phase": phase,
        "status": status,
        "allowed": allowed,
        "reason_codes": reason_codes,
        "pending_count": pending_count,
    }


def _blocked(
    *,
    phase: str,
    status: str,
    reason: str,
    pending_count: int | None,
) -> dict[str, object]:
    return _result(
        phase=phase,
        status=status,
        allowed=False,
        reason_codes=[reason],
        pending_count=pending_count,
    )


def _call(
    operations: object, method_name: str, *args: object
) -> tuple[bool, object]:
    try:
        method = getattr(operations, method_name)
        if not callable(method):
            return False, None
        return True, method(*args)
    except Exception:
        return False, None


def _nonblank(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in HEX_DIGITS for character in value)
    )


def evaluate_authority_realm_admission(
    *,
    task_id: str,
    operation_id: str,
    expected_receipt: object,
    presented_receipt: object,
) -> dict[str, object]:
    """Compare authority identity before a caller allocates or writes."""

    def result(
        status: str, allowed: bool, reason_codes: list[str]
    ) -> dict[str, object]:
        return {
            "schema": AUTHORITY_ADMISSION_SCHEMA,
            "task_id": task_id,
            "operation_id": operation_id,
            "status": status,
            "allowed": allowed,
            "reason_codes": reason_codes,
            "admission_stage": "BEFORE_SEQUENCE_AND_WRITES",
            "side_effects_authorized": allowed,
            "sequence_allocation_authorized": allowed,
            "writes_authorized": allowed,
            "distributed_lock": "NOT_USED",
            "production_ready": False,
            "authority_root_bound": False,
            "archive_transaction_bound": False,
            "required_production_gates": list(
                LOCAL_AUTHORITY_REQUIRED_PRODUCTION_GATES
            ),
        }

    normalized_task = _nonblank(task_id)
    normalized_operation = _nonblank(operation_id)
    try:
        parsed_operation = UUID(normalized_operation or "")
    except (ValueError, AttributeError):
        parsed_operation = None
    if (
        normalized_task is None
        or normalized_operation is None
        or parsed_operation is None
        or str(parsed_operation) != normalized_operation.lower()
    ):
        return result(
            "AUTHORITY_RECEIPT_INVALID",
            False,
            ["authority_operation_binding_invalid"],
        )

    def receipt_state(value: object) -> str:
        if not isinstance(value, dict):
            return "invalid"
        if value.get("schema") != LOCAL_AUTHORITY_REALM_SCHEMA:
            return "invalid"
        status = value.get("status")
        if (
            status == "AUTHORITY_TRANSPORT_UNSUPPORTED"
            or value.get("transport") != "local_filesystem"
            or value.get("local_filesystem_verified") is not True
        ):
            return "transport_unsupported"
        if status == "AUTHORITY_ROOT_UNTRUSTED":
            return "root_untrusted"
        if (
            status != "AUTHORITY_REALM_READY"
            or value.get("allowed") is not True
            or _nonblank(value.get("authority_realm_id")) is None
            or not _valid_sha256(value.get("root_fingerprint"))
        ):
            return "invalid"
        return "ready"

    expected_state = receipt_state(expected_receipt)
    presented_state = receipt_state(presented_receipt)
    states = {expected_state, presented_state}
    if "invalid" in states:
        return result(
            "AUTHORITY_RECEIPT_INVALID",
            False,
            ["authority_receipt_invalid"],
        )
    if "transport_unsupported" in states:
        return result(
            "AUTHORITY_TRANSPORT_UNSUPPORTED",
            False,
            ["authority_transport_unsupported"],
        )
    if "root_untrusted" in states:
        return result(
            "AUTHORITY_ROOT_UNTRUSTED",
            False,
            ["authority_root_untrusted"],
        )

    expected = expected_receipt
    presented = presented_receipt
    reasons: list[str] = []
    if expected.get("authority_realm_id") != presented.get(
        "authority_realm_id"
    ):
        reasons.append("authority_realm_id_mismatch")
    if expected.get("root_fingerprint") != presented.get("root_fingerprint"):
        reasons.append("root_fingerprint_mismatch")
    return result(
        "AUTHORITY_REALM_MISMATCH" if reasons else "AUTHORITY_REALM_MATCH",
        not reasons,
        reasons or ["authority_realm_match"],
    )


def _inventory(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    canonical_source = _resolved_path(value.get("canonical_source_root"))
    source_volume_serial = value.get("source_volume_serial")
    source_directory_id = _nonblank(value.get("source_directory_id"))
    file_count = value.get("file_count")
    total_bytes = value.get("total_bytes")
    newest_mtime = _aware_timestamp(value.get("newest_mtime_utc"))
    digest = value.get("inventory_digest")
    exclusion_policy_id = _nonblank(value.get("exclusion_policy_id"))
    captured_at = _aware_timestamp(value.get("captured_at"))
    evidence_id = _nonblank(value.get("evidence_id"))
    if (
        canonical_source is None
        or type(source_volume_serial) is not int
        or source_volume_serial <= 0
        or source_directory_id is None
        or type(file_count) is not int
        or file_count < 0
        or type(total_bytes) is not int
        or total_bytes < 0
        or newest_mtime is None
        or not _valid_sha256(digest)
        or exclusion_policy_id is None
        or captured_at is None
        or evidence_id is None
    ):
        return None
    return {
        "canonical_source_root": str(canonical_source),
        "source_volume_serial": source_volume_serial,
        "source_directory_id": source_directory_id,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "newest_mtime_utc": newest_mtime.isoformat(),
        "inventory_digest": str(digest).lower(),
        "exclusion_policy_id": exclusion_policy_id,
        "captured_at": captured_at,
        "evidence_id": evidence_id,
    }


def _inventory_signature(value: dict[str, object]) -> tuple[object, ...]:
    return tuple(value[field] for field in INVENTORY_FIELDS)


def _aware_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _resolved_path(value: object) -> Path | None:
    if not isinstance(value, (str, os.PathLike)):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return Path(value).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _safe_absolute_path(value: object) -> Path | None:
    if not isinstance(value, (str, os.PathLike)):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        raw = Path(value).expanduser()
        if not raw.is_absolute() or not raw.anchor:
            return None
        relative = raw.relative_to(Path(raw.anchor))
        if not relative.parts:
            return None
        validate_relative_path(relative)
        return raw.resolve(strict=False)
    except (SafeFilesystemError, OSError, RuntimeError, ValueError):
        return None


def _separate_root(
    candidate: Path, *, source_root: Path, target_root: Path
) -> bool:
    for inventory_root in (source_root, target_root):
        if _same_path(candidate, inventory_root):
            return False
        try:
            candidate.relative_to(inventory_root)
            return False
        except ValueError:
            pass
        try:
            inventory_root.relative_to(candidate)
            return False
        except ValueError:
            pass
    return True


def _same_path(left: object, right: object) -> bool:
    left_path = _resolved_path(left)
    right_path = _resolved_path(right)
    if left_path is None or right_path is None:
        return False
    return os.path.normcase(str(left_path)) == os.path.normcase(str(right_path))


def _is_reparse_point(path: Path) -> bool | None:
    try:
        metadata = path.lstat()
    except OSError:
        return None
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _nearest_existing_ancestor(path: Path) -> Path | None:
    candidate = path
    while True:
        try:
            candidate.lstat()
            return candidate
        except OSError:
            parent = candidate.parent
            if parent == candidate:
                return None
            candidate = parent


def _same_volume(source_root: Path, target_root: Path) -> bool | None:
    target_anchor = _nearest_existing_ancestor(target_root.parent)
    if target_anchor is None:
        return None
    try:
        return source_root.lstat().st_dev == target_anchor.stat().st_dev
    except OSError:
        return None


def _valid_protected_snapshot(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != set(PROTECTED_PATHS):
        return False
    for metadata in value.values():
        if not isinstance(metadata, dict):
            return False
        length = metadata.get("length")
        sha256 = metadata.get("sha256")
        if (
            type(length) is not int
            or length < 0
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in HEX_DIGITS for character in sha256)
        ):
            return False
    return True


def _evaluate_preflight(
    *, operations: object, pending_count: int, now: datetime
) -> dict[str, object]:
    ok, raw_bindings = _call(operations, "get_record_bindings")
    if not ok:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_RECORD_BINDINGS",
            reason="record_bindings_probe_failed",
            pending_count=pending_count,
        )
    if type(raw_bindings) is not list:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_RECORD_BINDINGS",
            reason="record_bindings_malformed",
            pending_count=pending_count,
        )

    binding_states: set[str] = set()
    for binding in raw_bindings:
        if not isinstance(binding, dict):
            return _blocked(
                phase="preflight",
                status="MIGRATION_BLOCKED_RECORD_BINDINGS",
                reason="record_bindings_malformed",
                pending_count=pending_count,
            )
        state_value = binding.get("state")
        if not isinstance(state_value, str) or not state_value.strip():
            binding_states.add("unknown")
        else:
            state = state_value.strip().lower()
            if state in {"active", "stale", "unknown"}:
                binding_states.add(state)

    for state, reason in (
        ("active", "active_binding"),
        ("stale", "stale_binding"),
        ("unknown", "unknown_binding"),
    ):
        if state in binding_states:
            return _blocked(
                phase="preflight",
                status="MIGRATION_BLOCKED_RECORD_BINDINGS",
                reason=reason,
                pending_count=pending_count,
            )
    if raw_bindings:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_RECORD_BINDINGS",
            reason="nonempty_binding_evidence",
            pending_count=pending_count,
        )
    binding_snapshot = {"bindings": raw_bindings}
    if not _valid_empty_binding_snapshot(binding_snapshot):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_RECORD_BINDINGS",
            reason="binding_snapshot_malformed",
            pending_count=pending_count,
        )

    ok, raw_scans = _call(operations, "get_stable_scans")
    if not ok:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_STABLE_SCANS",
            reason="stable_scans_probe_failed",
            pending_count=pending_count,
        )
    if not isinstance(raw_scans, (list, tuple)):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_STABLE_SCANS",
            reason="stable_scans_malformed",
            pending_count=pending_count,
        )
    if len(raw_scans) != 2:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_STABLE_SCANS",
            reason="two_stable_scans_required",
            pending_count=pending_count,
        )

    earlier, later = raw_scans
    earlier_inventory = _inventory(earlier)
    later_inventory = _inventory(later)
    if earlier_inventory is None or later_inventory is None:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_STABLE_SCANS",
            reason="stable_scans_malformed",
            pending_count=pending_count,
        )
    earlier_at = earlier_inventory["captured_at"]
    later_at = later_inventory["captured_at"]
    if (
        earlier_inventory["evidence_id"] == later_inventory["evidence_id"]
    ):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_STABLE_SCANS",
            reason="duplicate_scan_evidence",
            pending_count=pending_count,
        )
    if earlier_at > now or later_at > now:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_STABLE_SCANS",
            reason="future_scan_evidence",
            pending_count=pending_count,
        )
    if (
        (now - earlier_at).total_seconds() > EVIDENCE_TTL_SECONDS
        or (now - later_at).total_seconds() > EVIDENCE_TTL_SECONDS
    ):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_STABLE_SCANS",
            reason="stale_scan_evidence",
            pending_count=pending_count,
        )
    if (later_at - earlier_at).total_seconds() < 30:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_STABLE_SCANS",
            reason="stable_scan_interval_too_short",
            pending_count=pending_count,
        )
    if _inventory_signature(earlier_inventory) != _inventory_signature(
        later_inventory
    ):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_STABLE_SCANS",
            reason="stable_scan_mismatch",
            pending_count=pending_count,
        )

    ok, current_snapshot = _call(operations, "get_current_source_snapshot")
    if not ok:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_SOURCE_DRIFT",
            reason="current_snapshot_probe_failed",
            pending_count=pending_count,
        )
    current_inventory = _inventory(current_snapshot)
    if current_inventory is None:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_SOURCE_DRIFT",
            reason="current_snapshot_malformed",
            pending_count=pending_count,
        )
    current_at = current_inventory["captured_at"]
    if current_inventory["evidence_id"] in {
        earlier_inventory["evidence_id"],
        later_inventory["evidence_id"],
    }:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_SOURCE_DRIFT",
            reason="duplicate_scan_evidence",
            pending_count=pending_count,
        )
    if current_at > now:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_SOURCE_DRIFT",
            reason="future_scan_evidence",
            pending_count=pending_count,
        )
    if (now - current_at).total_seconds() > EVIDENCE_TTL_SECONDS:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_SOURCE_DRIFT",
            reason="stale_scan_evidence",
            pending_count=pending_count,
        )
    if current_at < later_at or _inventory_signature(
        current_inventory
    ) != _inventory_signature(later_inventory):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_SOURCE_DRIFT",
            reason="source_drift",
            pending_count=pending_count,
        )

    ok, target_context = _call(operations, "get_target_context")
    if not ok or not isinstance(target_context, dict):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="target_context_malformed",
            pending_count=pending_count,
        )
    source_root = _safe_absolute_path(target_context.get("source_root"))
    if source_root is None:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="unsafe_source_path",
            pending_count=pending_count,
        )
    pending_root = _safe_absolute_path(target_context.get("pending_root"))
    if (
        pending_root is None
        or not _same_path(
            pending_root,
            source_root / "shiguan-imports" / "pending",
        )
    ):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="unsafe_pending_path",
            pending_count=pending_count,
        )
    target_root = _resolved_path(target_context.get("target_root"))
    agents_root = _resolved_path(target_context.get("agents_root"))
    protected_root = _safe_absolute_path(target_context.get("protected_root"))
    if target_root is None or agents_root is None or protected_root is None:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="target_context_malformed",
            pending_count=pending_count,
        )
    ok, authorized_protected_value = _call(
        operations, "get_authorized_protected_root"
    )
    authorized_protected_root = _safe_absolute_path(
        authorized_protected_value
    )
    if (
        not ok
        or authorized_protected_root is None
        or not _same_path(protected_root, authorized_protected_root)
    ):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="protected_root_not_authorized",
            pending_count=pending_count,
        )
    if not _separate_root(
        protected_root,
        source_root=source_root,
        target_root=target_root,
    ):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="protected_root_inside_inventory",
            pending_count=pending_count,
        )
    if _same_path(source_root, target_root):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="self_migration",
            pending_count=pending_count,
        )
    try:
        relative_target = target_root.relative_to(agents_root)
    except ValueError:
        relative_target = None
    if relative_target is None or not relative_target.parts:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="target_outside_agents",
            pending_count=pending_count,
        )
    try:
        validate_relative_path(relative_target)
    except (SafeFilesystemError, OSError, ValueError):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="unsafe_target_path",
            pending_count=pending_count,
        )
    same_volume = target_context.get("same_volume")
    target_exists = target_context.get("target_exists")
    source_is_reparse = target_context.get("source_is_reparse")
    pending_is_reparse = target_context.get("pending_is_reparse")
    target_is_reparse = target_context.get("target_is_reparse")
    target_parent_reparse_free = target_context.get(
        "target_parent_reparse_free"
    )
    source_volume_serial = target_context.get("source_volume_serial")
    target_volume_serial = target_context.get("target_volume_serial")
    source_directory_id = _nonblank(target_context.get("source_directory_id"))
    delete_share_verified = target_context.get("delete_share_verified")
    source_file_id_verified = target_context.get("source_file_id_verified")
    target_parent_file_id_verified = target_context.get(
        "target_parent_file_id_verified"
    )
    control_root = _resolved_path(target_context.get("control_root"))
    if (
        type(same_volume) is not bool
        or type(target_exists) is not bool
        or type(source_is_reparse) is not bool
        or type(pending_is_reparse) is not bool
        or type(target_is_reparse) is not bool
        or type(target_parent_reparse_free) is not bool
        or type(source_volume_serial) is not int
        or source_volume_serial <= 0
        or type(target_volume_serial) is not int
        or target_volume_serial <= 0
        or source_directory_id is None
        or control_root is None
    ):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="target_context_malformed",
            pending_count=pending_count,
        )
    if not same_volume or source_volume_serial != target_volume_serial:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="cross_volume_target",
            pending_count=pending_count,
        )
    if target_exists:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="target_already_exists",
            pending_count=pending_count,
        )
    if source_is_reparse:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="source_is_reparse_point",
            pending_count=pending_count,
        )
    if pending_is_reparse:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="pending_is_reparse_point",
            pending_count=pending_count,
        )
    if target_is_reparse:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="target_is_reparse_point",
            pending_count=pending_count,
        )
    if target_parent_reparse_free is not True:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="target_parent_reparse_untrusted",
            pending_count=pending_count,
        )
    if delete_share_verified is not True:
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="delete_share_unverified",
            pending_count=pending_count,
        )
    if (
        source_file_id_verified is not True
        or target_parent_file_id_verified is not True
    ):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_TARGET_ROOT",
            reason="file_id_unverified",
            pending_count=pending_count,
        )
    if (
        not _same_path(current_inventory["canonical_source_root"], source_root)
        or current_inventory["source_volume_serial"] != source_volume_serial
        or current_inventory["source_directory_id"] != source_directory_id
    ):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_SOURCE_DRIFT",
            reason="source_identity_mismatch",
            pending_count=pending_count,
        )
    for inventory_root in (source_root, target_root):
        if control_root == inventory_root or control_root.is_relative_to(
            inventory_root
        ):
            return _blocked(
                phase="preflight",
                status="MIGRATION_BLOCKED_RECEIPT_BINDING",
                reason="control_root_inside_inventory",
                pending_count=pending_count,
            )

    ok, receipt_identity = _call(operations, "get_receipt_identity")
    if not ok or not isinstance(receipt_identity, dict):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_RECEIPT_BINDING",
            reason="receipt_identity_malformed",
            pending_count=pending_count,
        )
    migration_id = _nonblank(receipt_identity.get("migration_id"))
    receipt_id = _nonblank(receipt_identity.get("receipt_id"))
    run_owner = _nonblank(receipt_identity.get("run_owner"))
    run_marker_id = _nonblank(receipt_identity.get("run_marker_id"))
    identity_control_root = _resolved_path(receipt_identity.get("control_root"))
    issued_at = receipt_identity.get("issued_at")
    nonce = _nonblank(receipt_identity.get("nonce"))
    issued_time = _aware_timestamp(issued_at)
    expires_time = (
        issued_time + timedelta(seconds=READY_RECEIPT_TTL_SECONDS)
        if issued_time is not None
        else None
    )
    if (
        migration_id is None
        or receipt_id is None
        or run_owner is None
        or run_marker_id is None
        or identity_control_root is None
        or identity_control_root != control_root
        or issued_time is None
        or expires_time is None
        or issued_time > now
        or now > expires_time
        or nonce is None
    ):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_RECEIPT_BINDING",
            reason="receipt_identity_malformed",
            pending_count=pending_count,
        )

    ok, protected_before = _call(
        operations, "get_protected_file_snapshot", protected_root
    )
    if not ok or not _valid_protected_snapshot(protected_before):
        return _blocked(
            phase="preflight",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="protected_snapshot_malformed",
            pending_count=pending_count,
        )

    result = _result(
        phase="preflight",
        status=READY,
        allowed=True,
        reason_codes=["preflight_verified"],
        pending_count=pending_count,
    )
    result.update(
        {
            "source_root": str(source_root),
            "target_root": str(target_root),
            "protected_root": str(protected_root),
            "source_volume_serial": source_volume_serial,
            "source_directory_id": source_directory_id,
            "file_count": current_inventory["file_count"],
            "total_bytes": current_inventory["total_bytes"],
            "newest_mtime_utc": current_inventory["newest_mtime_utc"],
            "inventory_digest": current_inventory["inventory_digest"],
            "exclusion_policy_id": current_inventory["exclusion_policy_id"],
            "inventory_captured_at": current_inventory[
                "captured_at"
            ].isoformat(),
            "inventory_evidence_id": current_inventory["evidence_id"],
            "migration_id": migration_id,
            "receipt_id": receipt_id,
            "run_owner": run_owner,
            "run_marker_id": run_marker_id,
            "control_root": str(control_root),
            "issued_at": issued_at,
            "expires_at": expires_time.isoformat(),
            "nonce": nonce,
            "pending_snapshot": {"pending_count": pending_count},
            "binding_snapshot": binding_snapshot,
            "protected_files_before": protected_before,
        }
    )
    return result


def _evaluate_post_cutover(*, operations: object, pending_count: int) -> dict[str, object]:
    ok, state = _call(operations, "get_post_cutover_state")
    if not ok:
        return _blocked(
            phase="post_cutover",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="post_cutover_probe_failed",
            pending_count=pending_count,
        )
    if not isinstance(state, dict):
        return _blocked(
            phase="post_cutover",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="post_cutover_state_malformed",
            pending_count=pending_count,
        )

    physical_store_count = state.get("physical_store_count")
    if type(physical_store_count) is not int or physical_store_count < 0:
        return _blocked(
            phase="post_cutover",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="physical_store_count_malformed",
            pending_count=pending_count,
        )
    if physical_store_count != 1:
        return _blocked(
            phase="post_cutover",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason=(
                "multiple_physical_stores"
                if physical_store_count > 1
                else "physical_store_missing"
            ),
            pending_count=pending_count,
        )
    if state.get("old_path_kind") != "junction":
        return _blocked(
            phase="post_cutover",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="old_path_not_junction",
            pending_count=pending_count,
        )
    if not _same_path(state.get("junction_target"), state.get("canonical_target")):
        return _blocked(
            phase="post_cutover",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="junction_mismatch",
            pending_count=pending_count,
        )
    old_directory_id = state.get("old_path_directory_id")
    target_directory_id = state.get("target_directory_id")
    if (
        old_directory_id is None
        or target_directory_id is None
        or old_directory_id == ""
        or target_directory_id == ""
    ):
        return _blocked(
            phase="post_cutover",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="directory_id_malformed",
            pending_count=pending_count,
        )
    if old_directory_id != target_directory_id:
        return _blocked(
            phase="post_cutover",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="directory_id_mismatch",
            pending_count=pending_count,
        )

    protected_root = _safe_absolute_path(state.get("protected_root"))
    if protected_root is None:
        return _blocked(
            phase="post_cutover",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="protected_root_untrusted",
            pending_count=pending_count,
        )
    ok, protected = _call(
        operations, "get_protected_file_snapshots", protected_root
    )
    if (
        not ok
        or not isinstance(protected, (list, tuple))
        or len(protected) != 2
        or not _valid_protected_snapshot(protected[0])
        or not _valid_protected_snapshot(protected[1])
    ):
        return _blocked(
            phase="post_cutover",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="protected_snapshot_malformed",
            pending_count=pending_count,
        )
    if protected[0] != protected[1]:
        return _blocked(
            phase="post_cutover",
            status="MIGRATION_BLOCKED_POST_CUTOVER",
            reason="protected_file_changed",
            pending_count=pending_count,
        )

    return _result(
        phase="post_cutover",
        status=POST_CUTOVER_VERIFIED,
        allowed=True,
        reason_codes=["post_cutover_verified"],
        pending_count=pending_count,
    )


def evaluate_migration_gate(
    *,
    phase: str,
    operations: object,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Evaluate migration evidence without performing migration or body access."""

    pending_ok, raw_pending_count = _call(operations, "get_pending_body_count")
    if (
        not pending_ok
        or type(raw_pending_count) is not int
        or raw_pending_count < 0
    ):
        return _blocked(
            phase=phase,
            status=PENDING_BLOCK,
            reason="pending_bodies_unknown",
            pending_count=None,
        )
    pending_count = raw_pending_count
    if pending_count > 0:
        return _blocked(
            phase=phase,
            status=PENDING_BLOCK,
            reason="pending_bodies_nonzero",
            pending_count=pending_count,
        )

    if phase == "preflight":
        provider = clock or getattr(operations, "current_time", None)
        try:
            now = provider() if callable(provider) else datetime.now(timezone.utc)
        except Exception:
            now = None
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            return _blocked(
                phase=phase,
                status="MIGRATION_BLOCKED_RECEIPT_BINDING",
                reason="receipt_clock_malformed",
                pending_count=pending_count,
            )
        return _evaluate_preflight(
            operations=operations, pending_count=pending_count, now=now
        )
    if phase == "post_cutover":
        return _evaluate_post_cutover(operations=operations, pending_count=pending_count)
    return _blocked(
        phase=phase,
        status="MIGRATION_BLOCKED_INVALID_PHASE",
        reason="invalid_phase",
        pending_count=pending_count,
    )


def _is_sidecar_name(name: str) -> bool:
    lowered = name.lower()
    return any(lowered.endswith(suffix) for suffix in SIDECAR_SUFFIXES)


def _is_plain_metadata_directory(path: Path) -> bool:
    try:
        root_stat = path.lstat()
    except (FileNotFoundError, OSError, ValueError):
        return False
    attributes = int(getattr(root_stat, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    is_junction = getattr(path, "is_junction", None)
    try:
        junction = bool(callable(is_junction) and is_junction())
    except OSError:
        return False
    return bool(
        stat.S_ISDIR(root_stat.st_mode)
        and not stat.S_ISLNK(root_stat.st_mode)
        and not bool(attributes & reparse_flag)
        and not junction
    )


def _metadata_only_pending_count(pending_root: Path) -> tuple[int | None, str | None]:
    try:
        if not _is_plain_metadata_directory(pending_root):
            return None, "pending_root_not_plain_directory"
        count = 0
        with os.scandir(pending_root) as entries:
            for entry in entries:
                if _is_sidecar_name(entry.name):
                    continue
                entry_stat = entry.stat(follow_symlinks=False)
                if stat.S_ISREG(entry_stat.st_mode):
                    count += 1
                elif stat.S_ISDIR(entry_stat.st_mode):
                    return None, "nested_pending_entry"
                else:
                    return None, "non_regular_pending_entry"
        return count, None
    except (OSError, ValueError):
        return None, "pending_metadata_probe_failed"


class _ScanOperations:
    """Read-only CLI adapter with deliberately untrusted migration evidence."""

    def __init__(self, *, source_root: Path, target_root: Path) -> None:
        self.source_root = source_root
        self.target_root = target_root
        source_pending = source_root / "shiguan-imports" / "pending"
        target_pending = target_root / "shiguan-imports" / "pending"
        try:
            source_root.lstat()
            source_absent = False
        except FileNotFoundError:
            source_absent = True
        except (OSError, ValueError):
            source_absent = False
        if (
            source_absent
            and _is_plain_metadata_directory(target_root)
            and _is_plain_metadata_directory(target_pending)
        ):
            self.pending_root = target_pending
            self.pending_root_mode = "existing_canonical_target"
        else:
            self.pending_root = source_pending
            self.pending_root_mode = "migration_source"
        self.pending_probe_error: str | None = None
        self.calls: list[str] = []

    def get_pending_body_count(self) -> int | None:
        self.calls.append("get_pending_body_count")
        count, error = _metadata_only_pending_count(self.pending_root)
        self.pending_probe_error = error
        return count

    def get_record_bindings(self) -> list[dict[str, str]]:
        self.calls.append("get_record_bindings")
        return [{"state": "unknown", "record": "*"}]

    def get_stable_scans(self) -> list[dict[str, object]]:
        self.calls.append("get_stable_scans")
        return []

    def get_current_source_snapshot(self) -> dict[str, object]:
        self.calls.append("get_current_source_snapshot")
        return {}

    def get_target_context(self) -> dict[str, object]:
        self.calls.append("get_target_context")
        resolved_target = _resolved_path(self.target_root)
        agents_root = ""
        if resolved_target is not None:
            for ancestor in resolved_target.parents:
                if ancestor.name.lower() == ".agents":
                    agents_root = str(ancestor)
                    break
        return {
            "source_root": str(self.source_root),
            "target_root": str(self.target_root),
            "agents_root": agents_root,
            "pending_root": str(self.pending_root),
            "protected_root": str(DEFAULT_PROTECTED_ROOT),
            "same_volume": _same_volume(self.source_root, self.target_root),
            "target_exists": _nearest_existing_ancestor(self.target_root)
            == self.target_root,
            "source_is_reparse": _is_reparse_point(self.source_root),
            "pending_is_reparse": _is_reparse_point(self.pending_root),
            "target_is_reparse": _is_reparse_point(self.target_root),
            "target_parent_reparse_free": False,
            "source_volume_serial": None,
            "target_volume_serial": None,
            "delete_share_verified": None,
            "source_file_id_verified": None,
            "target_parent_file_id_verified": None,
            "source_directory_id": None,
            "control_root": str(
                self.source_root.parent
                / "private-runtime"
                / "shiguan-migration"
            ),
        }

    def get_authorized_protected_root(self) -> Path:
        return DEFAULT_PROTECTED_ROOT

    def get_post_cutover_state(self) -> dict[str, object]:
        self.calls.append("get_post_cutover_state")
        return {}

    def get_protected_file_snapshots(self) -> tuple[dict[str, object], dict[str, object]]:
        self.calls.append("get_protected_file_snapshots")
        return {}, {}


def _scan_command(args: argparse.Namespace) -> int:
    operations = _ScanOperations(
        source_root=Path(args.source_root),
        target_root=Path(args.target_root),
    )
    result = evaluate_migration_gate(phase="preflight", operations=operations)
    result.update(
        {
            "command": "scan",
            "migration_id": args.migration_id,
            "pending_root": str(operations.pending_root),
            "pending_root_mode": operations.pending_root_mode,
            "pending_probe_error": operations.pending_probe_error,
            "probe_calls": operations.calls,
            "evidence_gaps": ["unknown_binding", "two_stable_scans_required"],
            "side_effects": [],
        }
    )
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"status: {result['status']}")
        print(f"allowed: {str(result['allowed']).lower()}")
        print(f"pending_count: {result['pending_count']}")
        print(f"reason_codes: {','.join(result['reason_codes'])}")
    return 0 if result.get("allowed") is True else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan = subparsers.add_parser("scan", help="run a metadata-only preflight scan")
    scan.add_argument("--source-root", required=True)
    scan.add_argument("--target-root", required=True)
    scan.add_argument("--migration-id", required=True)
    scan.add_argument("--format", choices=("json", "text"), default="json")
    scan.set_defaults(handler=_scan_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())

