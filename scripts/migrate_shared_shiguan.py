"""Merge legacy court Shiguan records into the shared Shiguan data root."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Callable

sys.dont_write_bytecode = True

from shiguan_paths import (
    _success_rollback_is_consumable,
    _valid_empty_binding_snapshot,
    default_migration_source_root,
    default_shared_root,
)
from court_file_lock import atomic_write_text
from court_safe_fs import SafeFilesystemError, validate_relative_path

GATE_SCHEMA = "court.shiguan_migration_gate.result.v1"
CUTOVER_SCHEMA = "court.shiguan_atomic_cutover.result.v1"
CUTOVER_COMMIT_SCHEMA = "court.shiguan_atomic_cutover.commit.v1"
READY = "READY_TO_MIGRATE"
CUTOVER_VERIFIED = "CUTOVER_VERIFIED"
CUTOVER_BLOCKED = "CUTOVER_BLOCKED"
CUTOVER_ROLLED_BACK = "CUTOVER_ROLLED_BACK"
CUTOVER_ROLLBACK_FAILED = "CUTOVER_ROLLBACK_FAILED"
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
PROTECTED_PATHS = (
    "references/shiguan-index.jsonl",
    "references/shiguan-knowledge-graph.json",
    "references/shiguan-tree/_index.md",
    "references/shiguan-tree/capability-index/_index.md",
)
HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
READY_RECEIPT_TTL_SECONDS = 300


def _cutover_receipt_sha256(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


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


def _inventory_signature(value: object) -> tuple[object, ...] | None:
    inventory = _inventory(value)
    if inventory is None:
        return None
    return tuple(inventory[field] for field in INVENTORY_FIELDS)


def _receipt_inventory(value: object) -> tuple[object, ...] | None:
    if not isinstance(value, dict):
        return None
    canonical_source = _resolved_path(value.get("source_root"))
    newest_mtime = _aware_timestamp(value.get("newest_mtime_utc"))
    digest = value.get("inventory_digest")
    if (
        canonical_source is None
        or type(value.get("source_volume_serial")) is not int
        or int(value["source_volume_serial"]) <= 0
        or _nonblank(value.get("source_directory_id")) is None
        or type(value.get("file_count")) is not int
        or int(value["file_count"]) < 0
        or type(value.get("total_bytes")) is not int
        or int(value["total_bytes"]) < 0
        or newest_mtime is None
        or not _valid_sha256(digest)
        or _nonblank(value.get("exclusion_policy_id")) is None
    ):
        return None
    return (
        str(canonical_source),
        value["source_volume_serial"],
        value["source_directory_id"].strip(),
        value["file_count"],
        value["total_bytes"],
        newest_mtime.isoformat(),
        str(digest).lower(),
        value["exclusion_policy_id"].strip(),
    )


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


def _valid_protected_snapshot(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != set(PROTECTED_PATHS):
        return False
    for metadata in value.values():
        if not isinstance(metadata, dict):
            return False
        length = metadata.get("length")
        digest = metadata.get("sha256")
        if (
            type(length) is not int
            or length < 0
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in HEX_DIGITS for character in digest)
        ):
            return False
    return True


def _valid_gate_receipt(value: object, *, now: datetime) -> bool:
    if not isinstance(value, dict):
        return False
    source_root = _safe_absolute_path(value.get("source_root"))
    target_root = _resolved_path(value.get("target_root"))
    control_root = _resolved_path(value.get("control_root"))
    protected_root = _safe_absolute_path(value.get("protected_root"))
    pending_snapshot = value.get("pending_snapshot")
    binding_snapshot = value.get("binding_snapshot")
    issued_at = _aware_timestamp(value.get("issued_at"))
    expires_at = _aware_timestamp(value.get("expires_at"))
    inventory_captured_at = _aware_timestamp(value.get("inventory_captured_at"))
    if (
        source_root is None
        or target_root is None
        or control_root is None
        or protected_root is None
        or _same_path(source_root, target_root)
        or control_root == source_root
        or control_root.is_relative_to(source_root)
        or control_root == target_root
        or control_root.is_relative_to(target_root)
        or not _separate_root(
            protected_root,
            source_root=source_root,
            target_root=target_root,
        )
    ):
        return False
    return bool(
        value.get("schema") == GATE_SCHEMA
        and value.get("phase") == "preflight"
        and value.get("status") == READY
        and value.get("allowed") is True
        and value.get("pending_count") == 0
        and _receipt_inventory(value) is not None
        and _aware_timestamp(value.get("newest_mtime_utc")) is not None
        and inventory_captured_at is not None
        and inventory_captured_at <= now
        and _nonblank(value.get("inventory_evidence_id")) is not None
        and _nonblank(value.get("migration_id")) is not None
        and _nonblank(value.get("receipt_id")) is not None
        and _nonblank(value.get("run_owner")) is not None
        and _nonblank(value.get("run_marker_id")) is not None
        and issued_at is not None
        and expires_at is not None
        and issued_at <= now <= expires_at
        and 0 < (expires_at - issued_at).total_seconds() <= READY_RECEIPT_TTL_SECONDS
        and _nonblank(value.get("nonce")) is not None
        and isinstance(pending_snapshot, dict)
        and pending_snapshot.get("pending_count") == 0
        and _valid_empty_binding_snapshot(binding_snapshot)
        and _valid_protected_snapshot(value.get("protected_files_before"))
    )


def _current_time(
    operations: object, clock: Callable[[], datetime] | None
) -> datetime | None:
    provider = clock or getattr(operations, "current_time", None)
    try:
        value = provider() if callable(provider) else datetime.now(timezone.utc)
    except Exception:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value


def _valid_cutover_receipt(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    source_root = _safe_absolute_path(value.get("source_root"))
    target_root = _resolved_path(value.get("target_root"))
    control_root = _resolved_path(value.get("control_root"))
    protected_root = _safe_absolute_path(value.get("protected_root"))
    pending_snapshot = value.get("pending_snapshot")
    binding_snapshot = value.get("binding_snapshot")
    protected_before = value.get("protected_files_before")
    protected_after = value.get("protected_files_after")
    rollback = value.get("rollback")
    common = bool(
        value.get("schema") == CUTOVER_SCHEMA
        and value.get("pending_count") == 0
        and source_root is not None
        and target_root is not None
        and control_root is not None
        and protected_root is not None
        and not _same_path(source_root, target_root)
        and not control_root.is_relative_to(source_root)
        and not control_root.is_relative_to(target_root)
        and _separate_root(
            protected_root,
            source_root=source_root,
            target_root=target_root,
        )
        and _receipt_inventory(value) is not None
        and _nonblank(value.get("migration_id")) is not None
        and _nonblank(value.get("receipt_id")) is not None
        and _nonblank(value.get("run_owner")) is not None
        and _nonblank(value.get("run_marker_id")) is not None
        and _aware_timestamp(value.get("issued_at")) is not None
        and _nonblank(value.get("nonce")) is not None
        and isinstance(pending_snapshot, dict)
        and pending_snapshot.get("pending_count") == 0
        and _valid_empty_binding_snapshot(binding_snapshot)
        and _valid_protected_snapshot(protected_before)
        and isinstance(rollback, dict)
    )
    if not common:
        return False
    status = value.get("status")
    if status == CUTOVER_VERIFIED:
        return bool(
            value.get("ok") is True
            and _aware_timestamp(value.get("committed_at")) is not None
            and value.get("junction_verified") is True
            and value.get("protected_postcheck") == "verified"
            and _valid_protected_snapshot(protected_after)
            and protected_before == protected_after
            and _success_rollback_is_consumable(rollback)
        )
    if status not in {CUTOVER_ROLLED_BACK, CUTOVER_ROLLBACK_FAILED}:
        return False
    reasons = value.get("reason_codes")
    if (
        value.get("ok") is not False
        or not isinstance(reasons, list)
        or any(not isinstance(reason, str) or not reason for reason in reasons)
        or not reasons
    ):
        return False
    if status == CUTOVER_ROLLED_BACK:
        return rollback.get("ok") is True
    return (
        rollback.get("ok") is False
        and rollback.get("conservative_stopped") is True
    )


def _cutover_receipt_path(context: dict[str, object]) -> Path:
    control_root = context.get("control_root")
    if not isinstance(control_root, Path):
        raise RuntimeError("cutover_receipt_control_root_malformed")
    return control_root / "shiguan-cutover-receipt.json"


def _cutover_commit_path(context: dict[str, object]) -> Path:
    control_root = context.get("control_root")
    if not isinstance(control_root, Path):
        raise RuntimeError("cutover_commit_control_root_malformed")
    return control_root / "shiguan-cutover-commit.json"


def _cutover_commit_marker(
    receipt: dict[str, object], *, state: str
) -> dict[str, object]:
    if state not in {"PREPARED", "COMMITTED"}:
        raise RuntimeError("cutover_commit_state_malformed")
    marker = {
        "schema": CUTOVER_COMMIT_SCHEMA,
        "state": state,
        "source_root": receipt["source_root"],
        "target_root": receipt["target_root"],
        "control_root": receipt["control_root"],
        "migration_id": receipt["migration_id"],
        "receipt_id": receipt["receipt_id"],
        "run_owner": receipt["run_owner"],
        "run_marker_id": receipt["run_marker_id"],
        "nonce": receipt["nonce"],
        "receipt_sha256": None,
        "committed_at": None,
    }
    if state == "COMMITTED":
        digest = _cutover_receipt_sha256(receipt)
        committed_at = receipt.get("committed_at")
        if digest is None or _aware_timestamp(committed_at) is None:
            raise RuntimeError("cutover_commit_receipt_malformed")
        marker["receipt_sha256"] = digest
        marker["committed_at"] = committed_at
    return marker


def _valid_cutover_commit_marker(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("schema") != CUTOVER_COMMIT_SCHEMA:
        return False
    for field in (
        "source_root",
        "target_root",
        "control_root",
        "migration_id",
        "receipt_id",
        "run_owner",
        "run_marker_id",
        "nonce",
    ):
        if _nonblank(value.get(field)) is None:
            return False
    state = value.get("state")
    if state == "PREPARED":
        return (
            value.get("receipt_sha256") is None
            and value.get("committed_at") is None
        )
    return bool(
        state == "COMMITTED"
        and _valid_sha256(value.get("receipt_sha256"))
        and _aware_timestamp(value.get("committed_at")) is not None
    )


def _persist_cutover_receipt(path: Path, receipt: dict[str, object]) -> None:
    atomic_write_text(
        path,
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _reread_cutover_receipt(
    path: Path, expected: dict[str, object]
) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("cutover_receipt_reread_failed") from exc
    if value != expected or not _valid_cutover_receipt(value):
        raise RuntimeError("cutover_receipt_strict_validation_failed")
    return value


def _persist_cutover_commit_marker(
    path: Path, marker: dict[str, object]
) -> None:
    atomic_write_text(
        path,
        json.dumps(marker, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _reread_cutover_commit_marker(
    path: Path, expected: dict[str, object]
) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("cutover_commit_reread_failed") from exc
    if value != expected or not _valid_cutover_commit_marker(value):
        raise RuntimeError("cutover_commit_strict_validation_failed")
    return value


def _cutover_blocked(reason: str, gate_receipt: object) -> dict[str, object]:
    gate_status = gate_receipt.get("status") if isinstance(gate_receipt, dict) else None
    pending_count = (
        gate_receipt.get("pending_count") if isinstance(gate_receipt, dict) else None
    )
    return {
        "schema": CUTOVER_SCHEMA,
        "ok": False,
        "status": CUTOVER_BLOCKED,
        "reason_codes": [reason],
        "gate_status": gate_status,
        "pending_count": pending_count,
        "rollback": {"applied": False, "ok": True, "actions": [], "errors": []},
    }


def _validate_cutover_context(
    value: object,
    *,
    authorized_protected_root: Path | None = None,
) -> tuple[dict[str, object] | None, str | None]:
    if not isinstance(value, dict):
        return None, "cutover_context_malformed"
    source_root = _safe_absolute_path(value.get("source_root"))
    if source_root is None:
        return None, "unsafe_source_path"
    pending_root = _safe_absolute_path(value.get("pending_root"))
    if (
        pending_root is None
        or not _same_path(
            pending_root,
            source_root / "shiguan-imports" / "pending",
        )
    ):
        return None, "unsafe_pending_path"
    target_root = _resolved_path(value.get("target_root"))
    agents_root = _resolved_path(value.get("agents_root"))
    control_root = _resolved_path(value.get("control_root"))
    protected_root = _safe_absolute_path(value.get("protected_root"))
    directory_id = _nonblank(value.get("source_directory_id"))
    inventory_value = _inventory(value.get("source_inventory"))
    inventory = _inventory_signature(value.get("source_inventory"))
    source_volume_serial = value.get("source_volume_serial")
    target_volume_serial = value.get("target_volume_serial")
    if (
        target_root is None
        or agents_root is None
        or control_root is None
        or protected_root is None
        or directory_id is None
        or inventory_value is None
        or inventory is None
        or type(value.get("same_volume")) is not bool
        or type(value.get("target_exists")) is not bool
        or type(value.get("source_is_reparse")) is not bool
        or type(value.get("pending_is_reparse")) is not bool
        or type(value.get("target_is_reparse")) is not bool
        or type(value.get("target_parent_reparse_free")) is not bool
        or type(source_volume_serial) is not int
        or source_volume_serial <= 0
        or type(target_volume_serial) is not int
        or target_volume_serial <= 0
    ):
        return None, "cutover_context_malformed"
    if _same_path(source_root, target_root):
        return None, "self_migration"
    if not _separate_root(
        protected_root,
        source_root=source_root,
        target_root=target_root,
    ):
        return None, "protected_root_inside_inventory"
    if (
        authorized_protected_root is None
        or not _same_path(protected_root, authorized_protected_root)
    ):
        return None, "protected_root_not_authorized"
    try:
        relative_target = target_root.relative_to(agents_root)
    except ValueError:
        relative_target = None
    if relative_target is None or not relative_target.parts:
        return None, "target_outside_agents"
    try:
        validate_relative_path(relative_target)
    except (SafeFilesystemError, OSError, ValueError):
        return None, "unsafe_target_path"
    if (
        value["same_volume"] is not True
        or source_volume_serial != target_volume_serial
    ):
        return None, "cross_volume_target"
    if value["target_exists"] is True:
        return None, "target_already_exists"
    if value["source_is_reparse"] is True:
        return None, "source_is_reparse_point"
    if value["pending_is_reparse"] is True:
        return None, "pending_is_reparse_point"
    if value["target_is_reparse"] is True:
        return None, "target_is_reparse_point"
    if value["target_parent_reparse_free"] is not True:
        return None, "target_parent_reparse_untrusted"
    if value.get("delete_share_verified") is not True:
        return None, "delete_share_unverified"
    if (
        value.get("source_file_id_verified") is not True
        or value.get("target_parent_file_id_verified") is not True
    ):
        return None, "file_id_unverified"
    if (
        not _same_path(inventory_value["canonical_source_root"], source_root)
        or inventory_value["source_volume_serial"] != source_volume_serial
        or inventory_value["source_directory_id"] != directory_id
    ):
        return None, "source_identity_mismatch"
    for inventory_root in (source_root, target_root):
        if control_root == inventory_root or control_root.is_relative_to(
            inventory_root
        ):
            return None, "control_root_inside_inventory"
    normalized = dict(value)
    normalized.update(
        {
            "source_root": source_root,
            "target_root": target_root,
            "agents_root": agents_root,
            "pending_root": pending_root,
            "protected_root": protected_root,
            "control_root": control_root,
            "source_volume_serial": source_volume_serial,
            "source_directory_id": directory_id,
            "source_inventory_signature": inventory,
            "source_inventory": inventory_value,
        }
    )
    return normalized, None


def _validate_receipt_binding(
    receipt: dict[str, object], context: dict[str, object]
) -> str | None:
    if not _same_path(receipt.get("source_root"), context["source_root"]):
        return "receipt_source_root_mismatch"
    if not _same_path(receipt.get("target_root"), context["target_root"]):
        return "receipt_target_root_mismatch"
    if not _same_path(receipt.get("control_root"), context["control_root"]):
        return "receipt_control_root_mismatch"
    if not _same_path(receipt.get("protected_root"), context["protected_root"]):
        return "receipt_protected_root_mismatch"
    if _receipt_inventory(receipt) != context["source_inventory_signature"]:
        return "receipt_inventory_mismatch"
    return None


def _receipt_identity(receipt: dict[str, object]) -> dict[str, object]:
    return {
        key: deepcopy(receipt[key])
        for key in (
            "source_root",
            "target_root",
            "protected_root",
            "source_volume_serial",
            "source_directory_id",
            "file_count",
            "total_bytes",
            "newest_mtime_utc",
            "inventory_digest",
            "exclusion_policy_id",
            "migration_id",
            "receipt_id",
            "run_owner",
            "run_marker_id",
            "control_root",
            "issued_at",
            "nonce",
            "pending_snapshot",
            "binding_snapshot",
        )
    }


def _verify_final_metadata_recheck(
    receipt: dict[str, object], value: object, *, now: datetime
) -> None:
    if not isinstance(value, dict):
        raise RuntimeError("final_metadata_recheck_malformed")
    if value.get("pending_count") != 0:
        raise RuntimeError("final_pending_count_drift")
    for field in (
        "source_root",
        "target_root",
        "control_root",
        "protected_root",
    ):
        if not _same_path(value.get(field), receipt.get(field)):
            raise RuntimeError(f"final_{field}_drift")
    captured_at = _aware_timestamp(value.get("captured_at"))
    if (
        captured_at is None
        or captured_at > now
        or (now - captured_at).total_seconds() > READY_RECEIPT_TTL_SECONDS
    ):
        raise RuntimeError("final_snapshot_clock_malformed")
    for field in (
        "source_volume_serial",
        "source_directory_id",
        "file_count",
        "total_bytes",
        "newest_mtime_utc",
        "inventory_digest",
        "exclusion_policy_id",
        "migration_id",
        "receipt_id",
        "run_owner",
        "run_marker_id",
        "issued_at",
        "nonce",
        "pending_snapshot",
        "binding_snapshot",
    ):
        if value.get(field) != receipt.get(field):
            raise RuntimeError(f"final_{field}_drift")
    if not _valid_empty_binding_snapshot(value.get("binding_snapshot")):
        raise RuntimeError("final_binding_snapshot_not_empty")


def _verify_source_snapshot(context: dict[str, object], value: object) -> None:
    if not isinstance(value, dict):
        raise RuntimeError("source_snapshot_malformed")
    if value.get("source_directory_id") != context["source_directory_id"]:
        raise RuntimeError("source_directory_id_drift")
    if _inventory_signature(value.get("source_inventory")) != context[
        "source_inventory_signature"
    ]:
        raise RuntimeError("source_inventory_drift")


def _verify_cutover_state(context: dict[str, object], value: object) -> None:
    if not isinstance(value, dict):
        raise RuntimeError("post_cutover_state_malformed")
    if value.get("physical_store_count") != 1:
        raise RuntimeError("single_physical_store_not_proven")
    if value.get("old_path_kind") != "junction":
        raise RuntimeError("old_path_not_junction")
    if not _same_path(value.get("junction_target"), context["target_root"]):
        raise RuntimeError("junction_target_mismatch")
    if not _same_path(value.get("canonical_target"), context["target_root"]):
        raise RuntimeError("canonical_target_mismatch")
    expected_id = context["source_directory_id"]
    if (
        value.get("old_path_directory_id") != expected_id
        or value.get("target_directory_id") != expected_id
    ):
        raise RuntimeError("directory_id_mismatch")
    if value.get("target_volume_serial") != context["source_volume_serial"]:
        raise RuntimeError("volume_identity_mismatch")
    if _inventory_signature(value.get("target_inventory")) != context[
        "source_inventory_signature"
    ]:
        raise RuntimeError("target_inventory_mismatch")


def _verify_final_cutover_state(
    context: dict[str, object],
    receipt: dict[str, object],
    value: object,
    *,
    protected_after: object,
) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict):
        raise RuntimeError("final_cutover_state_malformed")
    if value.get("daemon_running") is not True:
        raise RuntimeError("daemon_restart_unconfirmed")
    _verify_cutover_state(context, value)
    if value.get("pending_count") != 0:
        raise RuntimeError("final_pending_count_drift")
    if not _valid_empty_binding_snapshot(value.get("binding_snapshot")):
        raise RuntimeError("final_binding_snapshot_not_empty")
    if not _same_path(value.get("protected_root"), context["protected_root"]):
        raise RuntimeError("protected_root_drift")
    if (
        not _valid_protected_snapshot(protected_after)
        or protected_after != receipt["protected_files_before"]
        or value.get("protected_files_after") != protected_after
    ):
        raise RuntimeError("protected_postcheck_blocked")
    rollback = value.get("rollback")
    if not _success_rollback_is_consumable(rollback):
        raise RuntimeError("rollback_terminal_state_untrusted")
    return deepcopy(protected_after)


def _run_identity(receipt: dict[str, object]) -> dict[str, object]:
    return {
        key: deepcopy(receipt[key])
        for key in (
            "migration_id",
            "run_owner",
            "run_marker_id",
            "control_root",
        )
    }


def _validate_run_lock_state(
    value: object, identity: dict[str, object]
) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        value.get("migration_id") == identity.get("migration_id")
        and value.get("run_owner") == identity.get("run_owner")
        and value.get("run_marker_id") == identity.get("run_marker_id")
        and _same_path(value.get("control_root"), identity.get("control_root"))
    )


def _run_owner_verified(
    operations: object, identity: dict[str, object]
) -> bool:
    try:
        verify = getattr(operations, "verify_run_owner")
        return callable(verify) and verify(deepcopy(identity)) is True
    except Exception:
        return False


def _validated_actual_state(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    if (
        type(value.get("daemon_running")) is not bool
        or type(value.get("source_exists")) is not bool
        or type(value.get("target_exists")) is not bool
        or value.get("old_path_kind") not in {"directory", "junction", "absent"}
    ):
        return None
    return dict(value)


def _rollback_cutover(
    *,
    operations: object,
    context: dict[str, object],
    run_identity: dict[str, object],
) -> dict[str, object]:
    actions: list[str] = []
    errors: list[str] = []

    def probe(label: str) -> dict[str, object] | None:
        try:
            state = _validated_actual_state(operations.inspect_actual_state())
        except Exception as exc:
            errors.append(f"{label}_probe:{type(exc).__name__}:{exc}")
            return None
        if state is None:
            errors.append(f"{label}_probe:malformed")
        return state

    state = probe("rollback_initial")
    if state is None:
        return {
            "applied": False,
            "ok": False,
            "actions": actions,
            "errors": errors,
            "conservative_stopped": False,
        }
    if not _run_owner_verified(operations, run_identity):
        errors.append("rollback_run_owner_mismatch")
        return {
            "applied": False,
            "ok": False,
            "actions": actions,
            "errors": errors,
            "conservative_stopped": state.get("daemon_running") is False,
        }

    path_dirty = bool(state["target_exists"]) or state["old_path_kind"] != "directory"
    if path_dirty and state["daemon_running"]:
        try:
            operations.stop_daemon()
        except Exception:
            pass
        state = probe("rollback_stop")
        if state is None or state["daemon_running"]:
            errors.append("rollback_daemon_stop_unconfirmed")
            return {
                "applied": True,
                "ok": False,
                "actions": actions,
                "errors": errors,
                "conservative_stopped": False,
            }
        actions.append("stop_daemon")

    if state["old_path_kind"] == "junction":
        if not _same_path(state.get("junction_target"), context["target_root"]):
            errors.append("rollback_junction_target_mismatch")
        elif state.get("target_directory_id") != context["source_directory_id"]:
            errors.append("rollback_junction_directory_id_mismatch")
        else:
            removal_error: str | None = None
            if not _run_owner_verified(operations, run_identity):
                errors.append("rollback_run_owner_mismatch")
                return {
                    "applied": bool(actions),
                    "ok": False,
                    "actions": actions,
                    "errors": errors,
                    "conservative_stopped": state.get("daemon_running") is False,
                }
            try:
                operations.remove_compatibility_junction(context["target_root"])
            except Exception as exc:
                removal_error = (
                    f"rollback_junction_removal_failed:{type(exc).__name__}:{exc}"
                )
            next_state = probe("rollback_remove_junction")
            if removal_error is not None:
                errors.append(removal_error)
                if next_state is not None:
                    state = next_state
            elif next_state is None or next_state["old_path_kind"] == "junction":
                errors.append("rollback_junction_removal_unconfirmed")
            else:
                actions.append("remove_compatibility_junction")
                state = next_state

    if errors:
        return {
            "applied": True,
            "ok": False,
            "actions": actions,
            "errors": errors,
            "conservative_stopped": state.get("daemon_running") is False,
        }

    if state["target_exists"]:
        if state["old_path_kind"] != "absent":
            errors.append("rollback_source_path_not_clear")
        elif state.get("target_directory_id") != context["source_directory_id"]:
            errors.append("rollback_target_directory_id_mismatch")
        else:
            if not _run_owner_verified(operations, run_identity):
                errors.append("rollback_run_owner_mismatch")
                return {
                    "applied": bool(actions),
                    "ok": False,
                    "actions": actions,
                    "errors": errors,
                    "conservative_stopped": state.get("daemon_running") is False,
                }
            try:
                operations.atomic_rename_to_source(context["source_directory_id"])
            except Exception:
                pass
            next_state = probe("rollback_rename_source")
            if (
                next_state is None
                or next_state["old_path_kind"] != "directory"
                or next_state["target_exists"]
                or next_state.get("source_directory_id")
                != context["source_directory_id"]
            ):
                errors.append("rollback_source_restore_unconfirmed")
            else:
                actions.append("atomic_rename_to_source")
                state = next_state

    restored = (
        state["old_path_kind"] == "directory"
        and state["target_exists"] is False
        and state.get("source_directory_id") == context["source_directory_id"]
    )
    if not restored:
        errors.append("rollback_source_not_restored")

    if restored and state["daemon_running"] is False:
        if not _run_owner_verified(operations, run_identity):
            errors.append("rollback_run_owner_mismatch")
            return {
                "applied": bool(actions),
                "ok": False,
                "actions": actions,
                "errors": errors,
                "conservative_stopped": True,
            }
        try:
            operations.start_daemon()
        except Exception:
            pass
        next_state = probe("rollback_start")
        if next_state is None or next_state["daemon_running"] is not True:
            errors.append("rollback_daemon_start_unconfirmed")
        else:
            actions.append("start_daemon")
            state = next_state

    ok = not errors and restored and state["daemon_running"] is True
    return {
        "applied": bool(actions or errors),
        "ok": ok,
        "actions": actions,
        "errors": errors,
        "conservative_stopped": not ok and state.get("daemon_running") is False,
    }


def _receipt_core(
    receipt: dict[str, object], context: dict[str, object]
) -> dict[str, object]:
    return {
        "schema": CUTOVER_SCHEMA,
        "gate_status": READY,
        "pending_count": 0,
        "source_root": str(context["source_root"]),
        "target_root": str(context["target_root"]),
        "protected_root": str(context["protected_root"]),
        "source_volume_serial": receipt["source_volume_serial"],
        "source_directory_id": receipt["source_directory_id"],
        "file_count": receipt["file_count"],
        "total_bytes": receipt["total_bytes"],
        "newest_mtime_utc": receipt["newest_mtime_utc"],
        "inventory_digest": receipt["inventory_digest"],
        "exclusion_policy_id": receipt["exclusion_policy_id"],
        "migration_id": receipt["migration_id"],
        "receipt_id": receipt["receipt_id"],
        "run_owner": receipt["run_owner"],
        "run_marker_id": receipt["run_marker_id"],
        "control_root": str(context["control_root"]),
        "issued_at": receipt["issued_at"],
        "nonce": receipt["nonce"],
        "pending_snapshot": deepcopy(receipt["pending_snapshot"]),
        "binding_snapshot": deepcopy(receipt["binding_snapshot"]),
        "protected_files_before": deepcopy(receipt["protected_files_before"]),
    }


def _terminal_receipt(
    *,
    receipt: dict[str, object],
    context: dict[str, object],
    failure_reason: str,
    rollback: dict[str, object],
) -> dict[str, object]:
    status = CUTOVER_ROLLED_BACK if rollback.get("ok") is True else CUTOVER_ROLLBACK_FAILED
    return {
        **_receipt_core(receipt, context),
        "ok": False,
        "status": status,
        "reason_codes": [failure_reason],
        "rollback": deepcopy(rollback),
    }


def _force_conservative_stop(
    *, operations: object, run_identity: dict[str, object]
) -> bool:
    if not _run_owner_verified(operations, run_identity):
        return False
    try:
        state = _validated_actual_state(operations.inspect_actual_state())
    except Exception:
        state = None
    if state is not None and state.get("daemon_running") is False:
        return True
    try:
        operations.stop_daemon()
    except Exception:
        pass
    try:
        state = _validated_actual_state(operations.inspect_actual_state())
    except Exception:
        return False
    return state is not None and state.get("daemon_running") is False


def execute_atomic_cutover(
    *,
    gate_receipt: object,
    operations: object,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Execute one fail-closed rename/junction transaction via an adapter."""

    now = _current_time(operations, clock)
    if now is None or not _valid_gate_receipt(gate_receipt, now=now):
        return _cutover_blocked("migration_gate_not_ready", gate_receipt)
    receipt = gate_receipt
    if not isinstance(receipt, dict):
        return _cutover_blocked("migration_gate_not_ready", gate_receipt)
    authorized_provider = getattr(
        operations, "get_authorized_protected_root", None
    )
    try:
        authorized_protected_root = _safe_absolute_path(
            authorized_provider() if callable(authorized_provider) else None
        )
    except Exception:
        authorized_protected_root = None
    if (
        authorized_protected_root is None
        or not _same_path(
            receipt.get("protected_root"), authorized_protected_root
        )
    ):
        return _cutover_blocked(
            "protected_root_not_authorized", gate_receipt
        )
    identity = _run_identity(receipt)
    lock_factory = getattr(operations, "migration_run_lock", None)
    if not callable(lock_factory):
        return _cutover_blocked("migration_run_lock_unavailable", gate_receipt)
    try:
        lock_context = lock_factory(deepcopy(identity))
        with lock_context as lock_state:
            if not _validate_run_lock_state(lock_state, identity):
                return _cutover_blocked("migration_run_owner_mismatch", gate_receipt)
            try:
                raw_context = operations.inspect_cutover_context()
            except Exception as exc:
                return _cutover_blocked(
                    f"cutover_context_probe_failed:{type(exc).__name__}:{exc}",
                    gate_receipt,
                )
            context, error = _validate_cutover_context(
                raw_context,
                authorized_protected_root=authorized_protected_root,
            )
            if context is None:
                return _cutover_blocked(
                    error or "cutover_context_malformed", gate_receipt
                )
            receipt_error = _validate_receipt_binding(receipt, context)
            if receipt_error is not None:
                return _cutover_blocked(receipt_error, gate_receipt)

            receipt_path = _cutover_receipt_path(context)
            commit_path = _cutover_commit_path(context)
            try:
                prepared_marker = _cutover_commit_marker(
                    receipt, state="PREPARED"
                )
                _persist_cutover_commit_marker(
                    commit_path, prepared_marker
                )
                _reread_cutover_commit_marker(
                    commit_path, prepared_marker
                )
                operations.stop_daemon()
                recheck_now = _current_time(operations, clock)
                if recheck_now is None:
                    raise RuntimeError("final_metadata_clock_malformed")
                _verify_final_metadata_recheck(
                    receipt,
                    operations.final_metadata_recheck(
                        _receipt_identity(receipt)
                    ),
                    now=recheck_now,
                )
                _verify_source_snapshot(context, operations.snapshot_source())
                operations.atomic_rename_to_target()
                operations.create_compatibility_junction()
                _verify_cutover_state(context, operations.verify_post_cutover())
                protected_after = operations.get_protected_file_snapshot(
                    context["protected_root"]
                )
                if (
                    not _valid_protected_snapshot(protected_after)
                    or protected_after != receipt["protected_files_before"]
                ):
                    raise RuntimeError("protected_postcheck_blocked")
                operations.start_daemon()
                final_state = operations.inspect_final_cutover_state()
                final_snapshot = operations.get_protected_file_snapshot(
                    context["protected_root"]
                )
                final_protected = _verify_final_cutover_state(
                    context,
                    receipt,
                    final_state,
                    protected_after=final_snapshot,
                )
                committed_at = _current_time(operations, clock)
                if committed_at is None:
                    raise RuntimeError("cutover_commit_clock_malformed")
                success_receipt = {
                    **_receipt_core(receipt, context),
                    "ok": True,
                    "status": CUTOVER_VERIFIED,
                    "reason_codes": ["atomic_cutover_verified"],
                    "committed_at": committed_at.isoformat(),
                    "junction_verified": True,
                    "protected_postcheck": "verified",
                    "protected_files_after": final_protected,
                    "rollback": {
                        "applied": False,
                        "ok": True,
                        "actions": [],
                        "errors": [],
                        "conservative_stopped": False,
                    },
                }
                _persist_cutover_receipt(receipt_path, success_receipt)
                committed_receipt = _reread_cutover_receipt(
                    receipt_path, success_receipt
                )
                committed_marker = _cutover_commit_marker(
                    committed_receipt, state="COMMITTED"
                )
                _persist_cutover_commit_marker(
                    commit_path, committed_marker
                )
                _reread_cutover_commit_marker(
                    commit_path, committed_marker
                )
                return committed_receipt
            except Exception as exc:
                try:
                    invalidated_marker = _cutover_commit_marker(
                        receipt, state="PREPARED"
                    )
                    _persist_cutover_commit_marker(
                        commit_path, invalidated_marker
                    )
                    _reread_cutover_commit_marker(
                        commit_path, invalidated_marker
                    )
                except Exception:
                    pass
                rollback = _rollback_cutover(
                    operations=operations,
                    context=context,
                    run_identity=identity,
                )
                if rollback.get("ok") is not True and rollback.get(
                    "conservative_stopped"
                ) is not True:
                    rollback["conservative_stopped"] = _force_conservative_stop(
                        operations=operations, run_identity=identity
                    )
                failure_reason = (
                    f"cutover_failed:{type(exc).__name__}:{exc}"
                )
                terminal = _terminal_receipt(
                    receipt=receipt,
                    context=context,
                    failure_reason=failure_reason,
                    rollback=rollback,
                )
                try:
                    _persist_cutover_receipt(receipt_path, terminal)
                    return _reread_cutover_receipt(receipt_path, terminal)
                except Exception as receipt_exc:
                    stopped = _force_conservative_stop(
                        operations=operations, run_identity=identity
                    )
                    rollback["ok"] = False
                    rollback["conservative_stopped"] = stopped
                    rollback.setdefault("errors", []).append(
                        "terminal_receipt_failed:"
                        f"{type(receipt_exc).__name__}:{receipt_exc}"
                    )
                    failed_terminal = _terminal_receipt(
                        receipt=receipt,
                        context=context,
                        failure_reason=failure_reason,
                        rollback=rollback,
                    )
                    try:
                        _persist_cutover_receipt(receipt_path, failed_terminal)
                        return _reread_cutover_receipt(
                            receipt_path, failed_terminal
                        )
                    except Exception as retry_exc:
                        rollback.setdefault("errors", []).append(
                            "terminal_receipt_retry_failed:"
                            f"{type(retry_exc).__name__}:{retry_exc}"
                        )
                        return _terminal_receipt(
                            receipt=receipt,
                            context=context,
                            failure_reason=failure_reason,
                            rollback=rollback,
                        )
    except Exception as exc:
        return _cutover_blocked(
            f"migration_run_lock_failed:{type(exc).__name__}:{exc}",
            gate_receipt,
        )


def migration_plan(
    source_root: Path | None = None, target_root: Path | None = None
) -> dict[str, object]:
    source = source_root or (default_migration_source_root() / "references")
    target = target_root or (default_shared_root() / "references")
    return {
        "schema": "court.shiguan_atomic_cutover.plan.v1",
        "ok": True,
        "status": "PLAN_ONLY",
        "source_root": str(source),
        "target_root": str(target),
        "required_gate": READY,
        "required_pending_count": 0,
        "strategy": "same_volume_atomic_rename_then_exact_compatibility_junction",
        "fallback_copy": False,
        "side_effects": [],
    }


def migrate(dry_run: bool = False) -> dict[str, object]:
    """Compatibility CLI surface; phase one deliberately permits planning only."""

    plan = migration_plan()
    if dry_run:
        return plan
    return {
        **plan,
        "ok": False,
        "status": CUTOVER_BLOCKED,
        "reason_codes": ["verified_gate_receipt_and_live_adapter_required"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        report = migrate(args.dry_run)
    except Exception as exc:
        print(f"SHIGUAN_MIGRATION_FAILED {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
