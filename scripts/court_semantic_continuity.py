"""Pure semantic-binding helpers for the file-backed court runtime."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


INVARIANT_CAPSULE_SCHEMA = "court.semantic.invariant_capsule.v1"
INVARIANT_CAPSULE_MAX_BYTES = 2048
SEMANTIC_RECEIPT_SCHEMA = "court.semantic.receipt.v1"
OFFICE_RESULT_SCHEMA = "court.office.result.v1"
DISPATCH_CONTEXT_PACKET_SCHEMA = "court.semantic.dispatch_context_packet.v1"
DISPATCH_CONTEXT_PACKET_MAX_BYTES = 2048
SEMANTIC_CONTEXT_FIELDS = (
    "authority_revision",
    "authority_sha256",
    "plan_revision",
    "plan_sha256",
    "plan_cursor",
    "git_fingerprint",
    "recovery_checkpoint_id",
    "shiguan_revision",
    "shiguan_fingerprint",
)
INVARIANT_CAPSULE_REQUIRED_FIELDS = {
    "schema",
    "latest_decree_anchor",
    "latest_decree_sha256",
    "non_goals",
    "boundaries",
    "allowed_actions",
    "forbidden_actions",
    "acceptance",
    "evidence_requirements",
    "stop_gates",
    "write_set",
    "governing_hashes",
    "charter_sha256",
}
SEMANTIC_RECEIPT_ID_FIELDS = {"receipt_id", "receipt_sha256"}
SEMANTIC_GATE_TRIGGERS = {
    "semantic_checkpoint": {
        "checkpoint",
        "compaction",
        "pre-compaction",
        "post-reconcile-checkpoint",
    },
    "semantic_verify": {
        "verify",
        "pre-mutation",
        "compaction",
        "reboot",
        "long-idle",
        "post-reconcile-verify",
    },
    "semantic_resume": {"resume"},
    "semantic_quarantine": {"pre-apply", "pre-mutation", "drift", "manual"},
    "semantic_reconcile": {"reconcile"},
    "semantic_correct": {"correction"},
}
SEMANTIC_GATE_VERDICTS = {
    "semantic_checkpoint": {"VERIFIED"},
    "semantic_verify": {"DISPATCHABLE", "QUARANTINED"},
    "semantic_resume": {"REVERIFY"},
    "semantic_quarantine": {"QUARANTINED"},
    "semantic_reconcile": {"REVERIFY"},
    "semantic_correct": {"REVERIFY"},
}
DISPATCH_CONTEXT_PACKET_REQUIRED_FIELDS = {
    "schema",
    "task_id",
    "sub_id",
    "semantic_epoch",
    "invariant_capsule_sha256",
    "semantic_receipt_id",
    "semantic_receipt_sha256",
    "authority_sha256",
    "plan_sha256",
    "plan_cursor",
    "fork_context",
    "context_mode",
    "pointers",
}
DISPATCH_CONTEXT_PACKET_OPTIONAL_FIELDS = {
    "summary",
    "full_context",
    "budget_override",
}
DISPATCH_CONTEXT_SUMMARY_FIELDS = {
    "text",
    "semantic_receipt_id",
    "semantic_receipt_sha256",
}
DISPATCH_CONTEXT_POINTER_FIELDS = {"path", "sha256"}
DISPATCH_CONTEXT_BUDGET_OVERRIDE_FIELDS = {
    "explicit",
    "granted_by",
    "max_bytes",
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def semantic_receipt_payload(receipt: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in receipt.items()
        if key not in SEMANTIC_RECEIPT_ID_FIELDS
    }


def finalize_semantic_receipt(receipt: dict[str, object]) -> dict[str, object]:
    finalized = semantic_receipt_payload(dict(receipt))
    digest = canonical_json_sha256(finalized)
    finalized["receipt_id"] = "SR-" + digest[:24].upper()
    finalized["receipt_sha256"] = digest
    return finalized


def derive_semantic_receipt(
    receipt: dict[str, object],
    *,
    receipt_sequence: int,
    gate: str,
    verdict: str,
    trigger: str,
    reason_codes: list[str],
    created_at: str,
    event_head_sha256: str,
    event_head_bytes: int,
    updates: dict[str, object] | None = None,
) -> dict[str, object]:
    derived = semantic_receipt_payload(dict(receipt))
    derived.update(
        receipt_sequence=receipt_sequence,
        gate=gate,
        verdict=verdict,
        trigger=trigger,
        reason_codes=list(reason_codes),
        created_at=created_at,
        event_head_sha256=_canonical_digest(
            event_head_sha256,
            "event_head_sha256",
        ),
        event_head_bytes=event_head_bytes,
    )
    if updates:
        derived.update(updates)
    return finalize_semantic_receipt(derived)


def semantic_checkpoint_material(receipt: dict[str, object]) -> dict[str, object]:
    fields = (
        "task_id",
        "semantic_epoch",
        "charter_sha256",
        "invariant_capsule_sha256",
        *SEMANTIC_CONTEXT_FIELDS,
        "write_set_sha256",
        "event_head_sha256",
        "event_head_bytes",
    )
    return {field: receipt.get(field) for field in fields}


def semantic_checkpoint_id(receipt: dict[str, object]) -> str:
    return "SC-" + canonical_json_sha256(semantic_checkpoint_material(receipt))[:24].upper()


def _timezone_aware(value: object) -> bool:
    text = str(value or "").strip()
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def semantic_receipt_integrity_problems(
    task: dict[str, object],
    receipt: object,
) -> list[str]:
    if not isinstance(receipt, dict):
        return ["semantic_receipt_integrity:missing"]
    problems: list[str] = []
    if receipt.get("schema") != SEMANTIC_RECEIPT_SCHEMA:
        problems.append("semantic_receipt_integrity:schema")
    sequence = receipt.get("receipt_sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        problems.append("semantic_receipt_integrity:receipt_sequence")
    canonical = finalize_semantic_receipt(receipt)
    for field in ("receipt_id", "receipt_sha256"):
        if receipt.get(field) != canonical[field]:
            problems.append(f"semantic_receipt_integrity:{field}")
    for field in (
        "charter_sha256",
        "invariant_capsule_sha256",
        "write_set_sha256",
        "event_head_sha256",
    ):
        if not _is_digest(receipt.get(field)):
            problems.append(f"semantic_receipt_integrity:{field}")
    event_head_bytes = receipt.get("event_head_bytes")
    if (
        not isinstance(event_head_bytes, int)
        or isinstance(event_head_bytes, bool)
        or event_head_bytes < 0
    ):
        problems.append("semantic_receipt_integrity:event_head_bytes")
    if not _timezone_aware(receipt.get("created_at")):
        problems.append("semantic_receipt_integrity:created_at")
    gate = str(receipt.get("gate") or "")
    trigger = str(receipt.get("trigger") or "")
    if gate not in SEMANTIC_GATE_TRIGGERS:
        problems.append("semantic_receipt_integrity:gate")
    elif trigger not in SEMANTIC_GATE_TRIGGERS[gate]:
        problems.append("semantic_receipt_integrity:trigger")
    if gate in SEMANTIC_GATE_VERDICTS and receipt.get("verdict") not in SEMANTIC_GATE_VERDICTS[gate]:
        problems.append("semantic_receipt_integrity:verdict")
    reason_codes = receipt.get("reason_codes")
    if not isinstance(reason_codes, list) or any(
        not isinstance(reason, str) or not reason for reason in reason_codes
    ):
        problems.append("semantic_receipt_integrity:reason_codes")
    capsule = task.get("invariant_capsule")
    if isinstance(capsule, dict):
        expected_write_set = canonical_json_sha256(capsule.get("write_set", []))
        if receipt.get("write_set_sha256") != expected_write_set:
            problems.append("semantic_receipt_integrity:write_set_sha256_binding")
    else:
        problems.append("semantic_receipt_integrity:write_set_source_missing")
    if gate == "semantic_checkpoint":
        if receipt.get("checkpoint_id") != semantic_checkpoint_id(receipt):
            problems.append("semantic_receipt_integrity:checkpoint_id")
        for field in SEMANTIC_CONTEXT_FIELDS:
            if field not in receipt:
                problems.append(f"semantic_receipt_integrity:{field}")
    elif not isinstance(receipt.get("checkpoint_id"), str) or not str(
        receipt.get("checkpoint_id")
    ).startswith("SC-"):
        problems.append("semantic_receipt_integrity:checkpoint_id")
    return problems


def _canonical_digest(value: object, field: str) -> str:
    digest = str(value or "").lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"invalid_{field}")
    return digest


def _utf8_prefix(value: str, limit: int) -> str:
    raw = value.encode("utf-8")
    if len(raw) <= limit:
        return value
    prefix = raw[:limit]
    while prefix:
        try:
            return prefix.decode("utf-8")
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    return ""


def build_invariant_capsule(charter: str, charter_sha256: str) -> dict[str, Any]:
    capsule: dict[str, Any] = {
        "schema": INVARIANT_CAPSULE_SCHEMA,
        "latest_decree_anchor": _utf8_prefix(charter, 256),
        "latest_decree_sha256": charter_sha256,
        "non_goals": [],
        "boundaries": [],
        "allowed_actions": [],
        "forbidden_actions": [],
        "acceptance": [],
        "evidence_requirements": [],
        "stop_gates": [],
        "write_set": [],
        "governing_hashes": {},
        "charter_sha256": charter_sha256,
    }
    if len(canonical_json_bytes(capsule)) > INVARIANT_CAPSULE_MAX_BYTES:
        raise ValueError("invariant_capsule_exceeds_2kib")
    return capsule


def normalize_invariant_capsule(
    charter: str,
    charter_sha256: str,
    value: object | None,
) -> dict[str, Any]:
    if value is None:
        return build_invariant_capsule(charter, charter_sha256)
    if not isinstance(value, dict):
        raise ValueError("invariant_capsule_must_be_object")
    capsule = dict(value)
    missing = sorted(INVARIANT_CAPSULE_REQUIRED_FIELDS - set(capsule))
    if missing:
        raise ValueError("invariant_capsule_fields_missing:" + ",".join(missing))
    unknown = sorted(set(capsule) - INVARIANT_CAPSULE_REQUIRED_FIELDS)
    if unknown:
        raise ValueError("invariant_capsule_fields_unknown:" + ",".join(unknown))
    if capsule.get("schema") != INVARIANT_CAPSULE_SCHEMA:
        raise ValueError("invalid_invariant_capsule_schema")
    if capsule.get("latest_decree_anchor") != _utf8_prefix(charter, 256):
        raise ValueError("invariant_capsule_decree_anchor_mismatch")
    if capsule.get("charter_sha256") != charter_sha256:
        raise ValueError("invariant_capsule_charter_sha256_mismatch")
    if capsule.get("latest_decree_sha256") != charter_sha256:
        raise ValueError("invariant_capsule_decree_sha256_mismatch")
    for field in (
        "non_goals",
        "boundaries",
        "allowed_actions",
        "forbidden_actions",
        "acceptance",
        "evidence_requirements",
        "stop_gates",
        "write_set",
    ):
        items = capsule.get(field)
        if not isinstance(items, list) or any(
            not isinstance(item, str) or not item.strip() for item in items
        ):
            raise ValueError(f"invalid_invariant_capsule_field:{field}")
    governing_hashes = capsule.get("governing_hashes")
    if not isinstance(governing_hashes, dict) or any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(digest, str)
        or digest != digest.lower()
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        for key, digest in governing_hashes.items()
    ):
        raise ValueError("invalid_invariant_capsule_field:governing_hashes")
    if len(canonical_json_bytes(capsule)) > INVARIANT_CAPSULE_MAX_BYTES:
        raise ValueError("invariant_capsule_exceeds_2kib")
    return capsule


def semantic_binding_problems(
    task: dict[str, object],
    *,
    require_complete: bool = False,
) -> list[str]:
    problems: list[str] = []
    charter = task.get("charter")
    if not isinstance(charter, str) or not charter.strip():
        problems.append("charter_body_missing")
        charter_digest = None
    else:
        charter_digest = sha256_text(charter)
    revision = task.get("charter_revision")
    epoch = task.get("semantic_epoch")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        problems.append("charter_revision_invalid")
    if epoch != revision:
        problems.append("semantic_epoch_mismatch")
    if charter_digest is None or task.get("charter_sha256") != charter_digest:
        problems.append("charter_sha256_mismatch")
    capsule = task.get("invariant_capsule")
    if not isinstance(capsule, dict):
        problems.append("invariant_capsule_missing")
    else:
        missing = sorted(INVARIANT_CAPSULE_REQUIRED_FIELDS - set(capsule))
        if missing:
            problems.append("invariant_capsule_fields_missing:" + ",".join(missing))
        if len(canonical_json_bytes(capsule)) > INVARIANT_CAPSULE_MAX_BYTES:
            problems.append("invariant_capsule_exceeds_2kib")
        if capsule.get("charter_sha256") != charter_digest:
            problems.append("invariant_capsule_charter_sha256_mismatch")
        if task.get("invariant_capsule_sha256") != canonical_json_sha256(capsule):
            problems.append("invariant_capsule_sha256_mismatch")
        if require_complete:
            for field in (
                "non_goals",
                "boundaries",
                "allowed_actions",
                "forbidden_actions",
                "acceptance",
                "evidence_requirements",
                "stop_gates",
                "write_set",
                "governing_hashes",
            ):
                value = capsule.get(field)
                if not value:
                    problems.append(f"invariant_capsule_empty:{field}")
    return problems


def normalize_semantic_context(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("semantic_context_required")
    context: dict[str, object] = {}
    for field in ("authority_revision", "plan_revision", "shiguan_revision"):
        raw = value.get(field)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            raise ValueError(f"invalid_{field}")
        context[field] = raw
    for field in ("authority_sha256", "plan_sha256", "shiguan_fingerprint"):
        context[field] = _canonical_digest(value.get(field), field)
    for field in ("plan_cursor", "git_fingerprint", "recovery_checkpoint_id"):
        text = str(value.get(field) or "").strip()
        if not text:
            raise ValueError(f"invalid_{field}")
        context[field] = text
    return context


def build_semantic_receipt(
    task: dict[str, object],
    context_value: object,
    *,
    event_head_sha256: str,
    event_head_bytes: int,
    trigger: str,
    created_at: str,
    receipt_sequence: int = 1,
) -> dict[str, object]:
    problems = semantic_binding_problems(task, require_complete=True)
    if problems:
        raise ValueError("semantic_binding_drift:" + ",".join(problems))
    context = normalize_semantic_context(context_value)
    event_head = _canonical_digest(event_head_sha256, "event_head_sha256")
    trigger_text = str(trigger or "").strip()
    if not trigger_text:
        raise ValueError("invalid_semantic_trigger")
    capsule = task["invariant_capsule"]
    assert isinstance(capsule, dict)
    receipt = {
        "schema": SEMANTIC_RECEIPT_SCHEMA,
        "receipt_sequence": receipt_sequence,
        "task_id": task.get("task_id"),
        "semantic_epoch": task.get("semantic_epoch"),
        "charter_sha256": task.get("charter_sha256"),
        "invariant_capsule_sha256": task.get("invariant_capsule_sha256"),
        **context,
        "dispatch_uid": None,
        "attempt": None,
        "agent_id": None,
        "write_set_sha256": canonical_json_sha256(capsule.get("write_set", [])),
        "event_head_sha256": event_head,
        "event_head_bytes": event_head_bytes,
        "trigger": trigger_text,
        "gate": "semantic_checkpoint",
        "verdict": "VERIFIED",
        "reason_codes": [],
        "created_at": created_at,
    }
    receipt["checkpoint_id"] = semantic_checkpoint_id(receipt)
    finalized = finalize_semantic_receipt(receipt)
    integrity = semantic_receipt_integrity_problems(task, finalized)
    if integrity:
        raise ValueError("semantic_receipt_integrity_failed:" + ",".join(integrity))
    return finalized


def verify_semantic_receipt(
    task: dict[str, object],
    receipt: object,
    context_value: object,
) -> list[str]:
    problems = semantic_binding_problems(task)
    if not isinstance(receipt, dict):
        return [*problems, "semantic_receipt_missing"]
    problems.extend(semantic_receipt_integrity_problems(task, receipt))
    context = normalize_semantic_context(context_value)
    expected = {
        "schema": SEMANTIC_RECEIPT_SCHEMA,
        "task_id": task.get("task_id"),
        "semantic_epoch": task.get("semantic_epoch"),
        "charter_sha256": task.get("charter_sha256"),
        "invariant_capsule_sha256": task.get("invariant_capsule_sha256"),
        **context,
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            problems.append(f"semantic_receipt_mismatch:{field}")
    if receipt.get("verdict") not in {"VERIFIED", "DISPATCHABLE"}:
        problems.append("semantic_receipt_not_verified")
    return problems


def _normalize_dispatch_context_pointers(
    value: object,
    *,
    field: str,
) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"invalid_{field}")
    normalized: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"invalid_{field}:{index}")
        unknown = sorted(set(raw) - DISPATCH_CONTEXT_POINTER_FIELDS)
        missing = sorted(DISPATCH_CONTEXT_POINTER_FIELDS - set(raw))
        if missing or unknown:
            raise ValueError(f"invalid_{field}:{index}:fields")
        path = raw.get("path")
        if (
            not isinstance(path, str)
            or not path
            or path != path.strip()
            or path.endswith(("/", "\\"))
            or any(character in path for character in "*?[]{}\x00\r\n")
            or ".." in path.replace("\\", "/").split("/")
        ):
            raise ValueError(f"dispatch_context_pointer_not_exact:{index}:path")
        if path in seen_paths:
            raise ValueError(f"dispatch_context_pointer_duplicate:{path}")
        seen_paths.add(path)
        normalized.append(
            {
                "path": path,
                "sha256": _canonical_digest(raw.get("sha256"), f"{field}_sha256"),
            }
        )
    return normalized


def _normalize_dispatch_context_summary(
    value: object,
    receipt: dict[str, object],
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("invalid_dispatch_context_summary")
    if set(value) != DISPATCH_CONTEXT_SUMMARY_FIELDS:
        raise ValueError("invalid_dispatch_context_summary_fields")
    text = value.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("invalid_dispatch_context_summary_text")
    for field in ("semantic_receipt_id", "semantic_receipt_sha256"):
        receipt_field = field.removeprefix("semantic_")
        if value.get(field) != receipt.get(receipt_field):
            raise ValueError(f"dispatch_context_summary_receipt_mismatch:{field}")
    return {
        "text": text,
        "semantic_receipt_id": str(value["semantic_receipt_id"]),
        "semantic_receipt_sha256": str(value["semantic_receipt_sha256"]),
    }


def _normalize_dispatch_context_budget_override(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("dispatch_context_full_requires_explicit_budget_override")
    if set(value) != DISPATCH_CONTEXT_BUDGET_OVERRIDE_FIELDS:
        raise ValueError("invalid_dispatch_context_budget_override_fields")
    if value.get("explicit") is not True:
        raise ValueError("dispatch_context_full_requires_explicit_budget_override")
    granted_by = str(value.get("granted_by") or "")
    if granted_by not in {"user", "taizi"}:
        raise ValueError("dispatch_context_budget_override_actor_forbidden")
    max_bytes = value.get("max_bytes")
    if (
        not isinstance(max_bytes, int)
        or isinstance(max_bytes, bool)
        or max_bytes <= DISPATCH_CONTEXT_PACKET_MAX_BYTES
    ):
        raise ValueError("invalid_dispatch_context_budget_override_max_bytes")
    return {
        "explicit": True,
        "granted_by": granted_by,
        "max_bytes": max_bytes,
    }


def validate_dispatch_context_packet(
    task: dict[str, object],
    receipt: object,
    value: object,
    *,
    previous_packet: object | None = None,
    reloaded_pointers: object | None = None,
) -> dict[str, object]:
    if not isinstance(receipt, dict):
        raise ValueError("dispatch_context_current_receipt_required")
    integrity = semantic_receipt_integrity_problems(task, receipt)
    if integrity:
        raise ValueError("dispatch_context_receipt_integrity_failed:" + ",".join(integrity))
    current_receipt = task.get("semantic_receipt")
    if not isinstance(current_receipt, dict):
        raise ValueError("dispatch_context_current_receipt_required")
    for field in ("receipt_id", "receipt_sha256"):
        if current_receipt.get(field) != receipt.get(field):
            raise ValueError(f"dispatch_context_receipt_not_current:{field}")
    if not isinstance(value, dict):
        raise ValueError("dispatch_context_packet_required")
    missing = sorted(DISPATCH_CONTEXT_PACKET_REQUIRED_FIELDS - set(value))
    if missing:
        raise ValueError("dispatch_context_packet_fields_missing:" + ",".join(missing))
    unknown = sorted(
        set(value)
        - DISPATCH_CONTEXT_PACKET_REQUIRED_FIELDS
        - DISPATCH_CONTEXT_PACKET_OPTIONAL_FIELDS
    )
    if unknown:
        raise ValueError("dispatch_context_packet_fields_unknown:" + ",".join(unknown))
    if value.get("schema") != DISPATCH_CONTEXT_PACKET_SCHEMA:
        raise ValueError("invalid_dispatch_context_packet_schema")
    task_id = str(task.get("task_id") or "")
    if not task_id or value.get("task_id") != task_id or receipt.get("task_id") != task_id:
        raise ValueError("dispatch_context_task_id_mismatch")
    sub_id = value.get("sub_id")
    if not isinstance(sub_id, str) or not sub_id.strip():
        raise ValueError("invalid_dispatch_context_sub_id")
    semantic_epoch = task.get("semantic_epoch")
    if (
        value.get("semantic_epoch") != semantic_epoch
        or receipt.get("semantic_epoch") != semantic_epoch
    ):
        raise ValueError("dispatch_context_semantic_epoch_mismatch")
    capsule_sha256 = task.get("invariant_capsule_sha256")
    if (
        value.get("invariant_capsule_sha256") != capsule_sha256
        or receipt.get("invariant_capsule_sha256") != capsule_sha256
    ):
        raise ValueError("dispatch_context_capsule_authority_mismatch")
    for field in ("semantic_receipt_id", "semantic_receipt_sha256"):
        receipt_field = field.removeprefix("semantic_")
        if value.get(field) != receipt.get(receipt_field):
            raise ValueError(f"dispatch_context_receipt_mismatch:{field}")
    for field in ("authority_sha256", "plan_sha256", "plan_cursor"):
        if value.get(field) != receipt.get(field):
            raise ValueError(f"dispatch_context_receipt_mismatch:{field}")
    fork_context = value.get("fork_context")
    if fork_context not in {"none", "minimal"}:
        raise ValueError("invalid_dispatch_context_fork_context")
    context_mode = value.get("context_mode")
    if context_mode not in {"bounded", "full"}:
        raise ValueError("invalid_dispatch_context_mode")

    packet = dict(value)
    pointers = _normalize_dispatch_context_pointers(
        value.get("pointers"),
        field="dispatch_context_pointers",
    )
    packet["pointers"] = pointers
    pointer_hashes = {pointer["sha256"] for pointer in pointers}
    for field in ("authority_sha256", "plan_sha256"):
        if receipt.get(field) not in pointer_hashes:
            raise ValueError(f"dispatch_context_pointer_missing:{field}")
    if "summary" in value:
        packet["summary"] = _normalize_dispatch_context_summary(
            value.get("summary"),
            receipt,
        )

    if context_mode == "bounded":
        if "full_context" in value or "budget_override" in value:
            raise ValueError("dispatch_context_bounded_full_context_forbidden")
        packet_bytes = len(canonical_json_bytes(packet))
        if packet_bytes > DISPATCH_CONTEXT_PACKET_MAX_BYTES:
            raise ValueError("dispatch_context_packet_exceeds_2kib")
    else:
        if "full_context" not in value:
            raise ValueError("dispatch_context_full_context_required")
        override = _normalize_dispatch_context_budget_override(
            value.get("budget_override")
        )
        packet["budget_override"] = override
        packet_bytes = len(canonical_json_bytes(packet))
        if packet_bytes > int(override["max_bytes"]):
            raise ValueError("dispatch_context_packet_exceeds_explicit_budget")

    reload_required: list[str] = []
    if previous_packet is not None:
        if not isinstance(previous_packet, dict):
            raise ValueError("invalid_previous_dispatch_context_packet")
        if previous_packet.get("task_id") != task_id:
            raise ValueError("dispatch_context_resume_task_id_mismatch")
        if previous_packet.get("sub_id") != sub_id:
            raise ValueError("dispatch_context_resume_sub_id_mismatch")
        if previous_packet.get("invariant_capsule_sha256") != capsule_sha256:
            raise ValueError("dispatch_context_resume_capsule_changed")
        previous_pointers = _normalize_dispatch_context_pointers(
            previous_packet.get("pointers"),
            field="previous_dispatch_context_pointers",
        )
        previous_by_path = {
            pointer["path"]: pointer["sha256"] for pointer in previous_pointers
        }
        reload_required = sorted(
            pointer["path"]
            for pointer in pointers
            if previous_by_path.get(pointer["path"]) != pointer["sha256"]
        )
        if reloaded_pointers is None:
            reloaded_by_path: dict[str, str] = {}
        else:
            normalized_reloaded = _normalize_dispatch_context_pointers(
                reloaded_pointers,
                field="reloaded_dispatch_context_pointers",
            )
            reloaded_by_path = {
                pointer["path"]: pointer["sha256"]
                for pointer in normalized_reloaded
            }
        current_by_path = {
            pointer["path"]: pointer["sha256"] for pointer in pointers
        }
        for path in sorted(reloaded_by_path):
            if path not in reload_required:
                raise ValueError(f"dispatch_context_reload_not_required:{path}")
            if reloaded_by_path[path] != current_by_path.get(path):
                raise ValueError(f"dispatch_context_reload_hash_mismatch:{path}")
        for path in reload_required:
            if reloaded_by_path.get(path) != current_by_path[path]:
                raise ValueError(f"dispatch_context_reload_required:{path}")
    elif reloaded_pointers is not None:
        raise ValueError("dispatch_context_reload_without_resume")

    return {
        "packet": packet,
        "packet_bytes": packet_bytes,
        "packet_sha256": canonical_json_sha256(packet),
        "reload_required": reload_required,
    }


def resume_context_problems(
    receipt: object,
    context_value: object,
) -> tuple[dict[str, object], list[str]]:
    context = normalize_semantic_context(context_value)
    if not isinstance(receipt, dict):
        return context, ["semantic_receipt_missing"]
    problems: list[str] = []
    for field in SEMANTIC_CONTEXT_FIELDS:
        if field in {"authority_revision", "authority_sha256"}:
            continue
        if receipt.get(field) != context.get(field):
            problems.append(f"semantic_receipt_mismatch:{field}")
    current_authority_revision = receipt.get("authority_revision")
    if (
        not isinstance(current_authority_revision, int)
        or isinstance(current_authority_revision, bool)
        or int(context["authority_revision"]) < current_authority_revision
    ):
        problems.append("authority_revision_regressed")
    return context, problems


def normalize_result_envelope(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("structured_result_envelope_required")
    envelope = dict(value)
    if envelope.get("schema") != OFFICE_RESULT_SCHEMA:
        raise ValueError("invalid_result_envelope_schema")
    text_fields = (
        "task_id",
        "charter_sha256",
        "invariant_capsule_sha256",
        "checkpoint_id",
        "dispatch_uid",
        "office_instance_id",
        "agent_id",
        "role",
        "direct_superior",
        "worktree",
        "write_set_sha256",
        "status",
        "summary",
        "produced_at",
    )
    for field in text_fields:
        if not isinstance(envelope.get(field), str) or not str(envelope[field]).strip():
            raise ValueError(f"invalid_result_envelope_field:{field}")
    for field in ("semantic_epoch", "attempt"):
        raw = envelope.get(field)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1:
            raise ValueError(f"invalid_result_envelope_field:{field}")
    for field in (
        "charter_sha256",
        "invariant_capsule_sha256",
        "write_set_sha256",
    ):
        envelope[field] = _canonical_digest(envelope[field], field)
    if envelope["status"] not in {"completed", "failed", "cancelled"}:
        raise ValueError("invalid_result_envelope_field:status")
    evidence = envelope.get("evidence")
    if not isinstance(evidence, list) or any(
        not isinstance(item, str) or not item.strip() for item in evidence
    ):
        raise ValueError("invalid_result_envelope_field:evidence")
    return envelope


def result_binding_problems(
    envelope: dict[str, object],
    binding: dict[str, object],
) -> list[str]:
    expected = {
        "task_id": binding.get("task_id"),
        "semantic_epoch": binding.get("semantic_epoch"),
        "charter_sha256": binding.get("charter_sha256"),
        "invariant_capsule_sha256": binding.get("invariant_capsule_sha256"),
        "checkpoint_id": binding.get("checkpoint_id"),
        "dispatch_uid": binding.get("dispatch_uid"),
        "attempt": binding.get("attempt"),
        "office_instance_id": binding.get("office_instance_id"),
        "agent_id": binding.get("agent_id"),
        "role": binding.get("role"),
        "direct_superior": binding.get("direct_superior"),
        "worktree": binding.get("worktree"),
        "write_set_sha256": canonical_json_sha256(binding.get("write_set", [])),
    }
    return [
        f"agent_result_binding_mismatch:{field}"
        for field, expected_value in expected.items()
        if envelope.get(field) != expected_value
    ]


def result_quarantine_metadata(
    envelope: dict[str, object],
    reason_codes: list[str],
    *,
    received_at: str,
) -> dict[str, object]:
    return {
        "schema": "court.office.result_quarantine.v1",
        "payload_sha256": canonical_json_sha256(envelope),
        "task_id": envelope.get("task_id"),
        "semantic_epoch": envelope.get("semantic_epoch"),
        "dispatch_uid": envelope.get("dispatch_uid"),
        "attempt": envelope.get("attempt"),
        "office_instance_id": envelope.get("office_instance_id"),
        "agent_id": envelope.get("agent_id"),
        "role": envelope.get("role"),
        "status": "QUARANTINED",
        "reason_codes": list(reason_codes),
        "received_at": received_at,
    }


def semantic_binding_for_revision(
    charter: object,
    revision: int,
    invariant_capsule: object | None = None,
) -> dict[str, object]:
    if not isinstance(charter, str) or not charter.strip():
        raise ValueError("charter_body_required")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("invalid_charter_revision")
    charter_sha256 = sha256_text(charter)
    capsule = normalize_invariant_capsule(charter, charter_sha256, invariant_capsule)
    return {
        "charter_revision": revision,
        "semantic_epoch": revision,
        "charter_sha256": charter_sha256,
        "invariant_capsule": capsule,
        "invariant_capsule_sha256": canonical_json_sha256(capsule),
        "semantic_state": "UNVERIFIED",
        "semantic_receipt": {},
        "semantic_receipt_id": None,
        "semantic_receipts": [],
    }


def initial_semantic_binding(
    charter: object,
    invariant_capsule: object | None = None,
) -> dict[str, object]:
    return {
        **semantic_binding_for_revision(charter, 1, invariant_capsule),
        "charter_revision_history": [],
    }
