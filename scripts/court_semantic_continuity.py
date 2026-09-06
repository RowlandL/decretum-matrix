"""Pure semantic-binding helpers for the file-backed court runtime."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import uuid
from datetime import datetime
from typing import Any, Mapping

import sys

sys.dont_write_bytecode = True


INVARIANT_CAPSULE_SCHEMA = "court.semantic.invariant_capsule.v1"
INVARIANT_CAPSULE_MAX_BYTES = 2048
SEMANTIC_RECEIPT_SCHEMA = "court.semantic.receipt.v1"
OFFICE_RESULT_SCHEMA = "court.office.result.v1"
CONSULTATION_REF_SCHEMA = "court.consultation_ref.v1"
CONSULTATION_REF_FIELDS = {
    "task_id",
    "charter_revision",
    "charter_sha256",
    "from_role",
    "to_role",
    "purpose",
    "input_pointer",
    "input_sha256",
    "reply_pointer",
    "reply_sha256",
    "write_authority_granted",
}
CONSULTATION_REF_MAX_COUNT = 16
CONSULTATION_REF_MAX_POINTER_BYTES = 512
CONSULTATION_REF_MAX_PURPOSE_BYTES = 256
RESULT_RECOVERY_PROJECTION_SCHEMA = "court.office.recovered_result_projection.v1"
RESULT_RECOVERY_BINDING_SCHEMA = "court.office.result_recovery_binding.v1"
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
    "non_goals",
    "boundaries",
    "allowed_actions",
    "forbidden_actions",
    "acceptance",
    "evidence_requirements",
    "stop_gates",
    "write_set",
    "case_ref",
}
SEMANTIC_RECEIPT_ID_FIELDS = {"receipt_id"}
REFERENCE_SEMANTIC_CONTEXT_FIELDS = (
    "authority_revision",
    "case_ref",
    "plan_ref",
    "plan_cursor",
    "recovery_checkpoint_id",
    "shiguan_revision",
)
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
    """Assign only an ordinary receipt id to a reference-bound receipt.

    The receipt is tied to the recorded case and event ids.  It deliberately
    does not derive either identity from a serialization of its content.
    """

    if not isinstance(receipt, dict):
        raise ValueError("semantic_receipt_required")
    finalized = dict(receipt)
    if "case_ref" not in finalized:
        raise ValueError("court_code_required")
    from court_case_binding import case_reference

    finalized["case_ref"] = case_reference(finalized["case_ref"])
    if _contains_digest_reference(finalized):
        raise ValueError("semantic_receipt_digest_field_forbidden")
    receipt_id = finalized.get("receipt_id")
    if receipt_id is None:
        finalized["receipt_id"] = "SEM-" + uuid.uuid4().hex.upper()
    elif not isinstance(receipt_id, str) or not receipt_id.strip():
        raise ValueError("semantic_receipt_id_invalid")
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
    event_head_id: str,
    updates: dict[str, object] | None = None,
) -> dict[str, object]:
    if not isinstance(receipt, dict) or "case_ref" not in receipt:
        raise ValueError("court_code_required")
    if not isinstance(receipt_sequence, int) or isinstance(receipt_sequence, bool) or receipt_sequence < 1:
        raise ValueError("semantic_receipt_sequence_invalid")
    if not isinstance(reason_codes, list) or any(
        not isinstance(reason, str) or not reason.strip() for reason in reason_codes
    ):
        raise ValueError("semantic_receipt_reason_codes_invalid")
    head_id = _required_reference_text(event_head_id, "event_head_id")
    derived = semantic_receipt_payload(dict(receipt))
    derived.update(
        receipt_sequence=receipt_sequence,
        gate=gate,
        verdict=verdict,
        trigger=trigger,
        reason_codes=list(reason_codes),
        created_at=created_at,
        event_head_id=head_id,
    )
    if updates:
        derived.update(updates)
    return finalize_semantic_receipt(derived)


def semantic_checkpoint_material(receipt: dict[str, object]) -> dict[str, object]:
    fields = (
        "task_id",
        "semantic_epoch",
        *REFERENCE_SEMANTIC_CONTEXT_FIELDS,
        "event_head_id",
    )
    return {field: receipt.get(field) for field in fields}


def semantic_checkpoint_id(receipt: dict[str, object]) -> str:
    checkpoint_id = receipt.get("checkpoint_id")
    if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
        raise ValueError("semantic_checkpoint_id_missing")
    return checkpoint_id


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


def _required_reference_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"semantic_receipt_{field}_required")
    return value.strip()


def _contains_digest_reference(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).lower()
            if (
                "sha256" in lowered
                or "fingerprint" in lowered
                or "governing_hash" in lowered
            ):
                return True
            if _contains_digest_reference(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_digest_reference(item) for item in value)
    return False


def semantic_receipt_integrity_problems(
    task: dict[str, object],
    receipt: object,
) -> list[str]:
    if not isinstance(receipt, dict):
        return ["semantic_receipt_integrity:missing"]
    problems: list[str] = []
    problems.extend(
        "semantic_binding:" + problem
        for problem in semantic_binding_problems(task, require_complete=True)
    )
    if receipt.get("schema") != SEMANTIC_RECEIPT_SCHEMA:
        problems.append("semantic_receipt_integrity:schema")
    sequence = receipt.get("receipt_sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        problems.append("semantic_receipt_integrity:receipt_sequence")
    for field in ("receipt_id", "checkpoint_id", "event_head_id"):
        if not isinstance(receipt.get(field), str) or not str(receipt[field]).strip():
            problems.append(f"semantic_receipt_integrity:{field}")
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
    try:
        from court_case_binding import case_reference

        expected_case_ref = case_reference(task)
        if receipt.get("case_ref") != expected_case_ref:
            problems.append("semantic_receipt_integrity:case_ref")
        context = {
            field: receipt.get(field)
            for field in REFERENCE_SEMANTIC_CONTEXT_FIELDS
        }
        normalize_semantic_context(context)
    except ValueError as exc:
        problems.append("semantic_receipt_integrity:context:" + str(exc))
    capsule = task.get("invariant_capsule")
    if isinstance(capsule, dict):
        if receipt.get("write_set") != capsule.get("write_set"):
            problems.append("semantic_receipt_integrity:write_set_binding")
    else:
        problems.append("semantic_receipt_integrity:write_set_source_missing")
    if receipt.get("semantic_epoch") != task.get("semantic_epoch"):
        problems.append("semantic_receipt_integrity:semantic_epoch")
    if _contains_digest_reference(receipt):
        problems.append("semantic_receipt_integrity:digest_field_forbidden")
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


INVARIANT_CAPSULE_TEMPLATE_FIELDS = frozenset(
    INVARIANT_CAPSULE_REQUIRED_FIELDS - {"case_ref"}
)
INVARIANT_CAPSULE_BODY_LIST_FIELDS = (
    "non_goals",
    "boundaries",
    "allowed_actions",
    "forbidden_actions",
    "acceptance",
    "evidence_requirements",
    "stop_gates",
    "write_set",
)


def build_invariant_capsule(charter: str) -> dict[str, Any]:
    """Return the pre-allocation capsule body used by public intake.

    The court number is intentionally bound only after allocation.  The body
    remains the original scope, authority, acceptance, and write-set contract.
    """

    if not isinstance(charter, str) or not charter.strip():
        raise ValueError("charter_body_required")
    capsule: dict[str, Any] = {
        "schema": INVARIANT_CAPSULE_SCHEMA,
        "latest_decree_anchor": _utf8_prefix(charter, 256),
        "non_goals": ["no unstated scope expansion"],
        "boundaries": ["exact charter only"],
        "allowed_actions": ["no mutation until explicit authority is bound"],
        "forbidden_actions": ["actions outside the exact charter"],
        "acceptance": ["exact charter remains authoritative"],
        "evidence_requirements": ["machine-readable runtime evidence"],
        "stop_gates": ["authority or semantic drift"],
        "write_set": ["NO_WRITES_DECLARED"],
    }
    if len(canonical_json_bytes(capsule)) > INVARIANT_CAPSULE_MAX_BYTES:
        raise ValueError("invariant_capsule_exceeds_2kib")
    return capsule


def invariant_capsule_json_schema() -> dict[str, object]:
    properties: dict[str, object] = {
        "schema": {"type": "string", "const": INVARIANT_CAPSULE_SCHEMA},
        "latest_decree_anchor": {"type": "string"},
        "case_ref": {"type": "object"},
    }
    for field in INVARIANT_CAPSULE_TEMPLATE_FIELDS - set(properties):
        properties[field] = {"type": "array", "items": {"type": "string"}}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": INVARIANT_CAPSULE_SCHEMA,
        "type": "object",
        "required": sorted(INVARIANT_CAPSULE_TEMPLATE_FIELDS),
        "optional": ["case_ref"],
        "properties": properties,
        "additionalProperties": False,
        "anchor_rule": "UTF-8 prefix of exact charter, at most 256 bytes",
        "binding_rule": "case_ref is required after a court code is allocated",
        "canonical_max_bytes": INVARIANT_CAPSULE_MAX_BYTES,
    }


def invariant_capsule_template(
    charter: str,
    overrides: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    capsule = build_invariant_capsule(charter)
    for field, value in dict(overrides or {}).items():
        if field not in INVARIANT_CAPSULE_TEMPLATE_FIELDS:
            raise ValueError(f"invariant_capsule_fields_unknown:{field}")
        if field in {"schema", "latest_decree_anchor"}:
            raise ValueError(f"invariant_capsule_binding_field_not_customizable:{field}")
        capsule[field] = value
    return normalize_invariant_capsule(charter, capsule)


def validate_invariant_capsule(charter: str, value: object) -> dict[str, Any]:
    return normalize_invariant_capsule(charter, value)


def normalize_invariant_capsule(
    charter: str,
    value: object | None,
    *,
    case_ref: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    expected_case_ref: dict[str, object] | None = None
    if case_ref is not None:
        from court_case_binding import case_reference

        expected_case_ref = case_reference(case_ref)
    if value is None:
        if expected_case_ref is not None:
            capsule = build_invariant_capsule(charter)
            capsule["case_ref"] = expected_case_ref
            return capsule
        return build_invariant_capsule(charter)
    if not isinstance(value, dict):
        raise ValueError("invariant_capsule_must_be_object")
    capsule = dict(value)
    required = (
        INVARIANT_CAPSULE_REQUIRED_FIELDS
        if expected_case_ref is not None
        else INVARIANT_CAPSULE_TEMPLATE_FIELDS
    )
    missing = sorted(required - set(capsule))
    if missing:
        raise ValueError("invariant_capsule_fields_missing:" + ",".join(missing))
    unknown = sorted(set(capsule) - required)
    if unknown:
        raise ValueError("invariant_capsule_fields_unknown:" + ",".join(unknown))
    if capsule.get("schema") != INVARIANT_CAPSULE_SCHEMA:
        raise ValueError("invalid_invariant_capsule_schema")
    if capsule.get("latest_decree_anchor") != _utf8_prefix(charter, 256):
        raise ValueError("invariant_capsule_decree_anchor_mismatch")
    if expected_case_ref is not None and capsule.get("case_ref") != expected_case_ref:
        raise ValueError("invariant_capsule_case_ref_mismatch")
    for field in INVARIANT_CAPSULE_BODY_LIST_FIELDS:
        items = capsule.get(field)
        if not isinstance(items, list) or any(
            not isinstance(item, str) or not item.strip() for item in items
        ):
            raise ValueError(f"invalid_invariant_capsule_field:{field}")
    if _contains_digest_reference(capsule):
        raise ValueError("invariant_capsule_digest_field_forbidden")
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
    revision = task.get("charter_revision")
    epoch = task.get("semantic_epoch")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        problems.append("charter_revision_invalid")
    if epoch != revision:
        problems.append("semantic_epoch_mismatch")
    try:
        from court_case_binding import case_reference

        case_ref = case_reference(task)
    except ValueError:
        case_ref = None
        problems.append("court_code_required")
    capsule = task.get("invariant_capsule")
    if not isinstance(capsule, dict):
        problems.append("invariant_capsule_missing")
    else:
        missing = sorted(INVARIANT_CAPSULE_REQUIRED_FIELDS - set(capsule))
        if missing:
            problems.append("invariant_capsule_fields_missing:" + ",".join(missing))
        unknown = sorted(set(capsule) - INVARIANT_CAPSULE_REQUIRED_FIELDS)
        if unknown:
            problems.append("invariant_capsule_fields_unknown:" + ",".join(unknown))
        if len(canonical_json_bytes(capsule)) > INVARIANT_CAPSULE_MAX_BYTES:
            problems.append("invariant_capsule_exceeds_2kib")
        if isinstance(charter, str) and charter.strip() and capsule.get(
            "latest_decree_anchor"
        ) != _utf8_prefix(charter, 256):
            problems.append("invariant_capsule_decree_anchor_mismatch")
        if case_ref is not None and capsule.get("case_ref") != case_ref:
            problems.append("invariant_capsule_case_ref_mismatch")
        if _contains_digest_reference(capsule):
            problems.append("invariant_capsule_digest_field_forbidden")
        for field in INVARIANT_CAPSULE_BODY_LIST_FIELDS:
            value = capsule.get(field)
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                problems.append(f"invalid_invariant_capsule_field:{field}")
        if require_complete:
            for field in INVARIANT_CAPSULE_BODY_LIST_FIELDS:
                value = capsule.get(field)
                if not value:
                    problems.append(f"invariant_capsule_empty:{field}")
    return problems


def normalize_semantic_context(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("semantic_context_required")
    if "case_ref" in value:
        from court_case_binding import case_reference, plan_reference

        required = {
            "authority_revision",
            "case_ref",
            "plan_ref",
            "plan_cursor",
            "recovery_checkpoint_id",
            "shiguan_revision",
        }
        if set(value) != required:
            raise ValueError("reference_semantic_context_fields_invalid")
        case_ref = case_reference(value["case_ref"])
        authority_revision = value.get("authority_revision")
        if (
            not isinstance(authority_revision, int)
            or isinstance(authority_revision, bool)
            or authority_revision != case_ref["charter_revision"]
        ):
            raise ValueError("reference_semantic_context_authority_invalid")
        raw_plan = value.get("plan_ref")
        plan_ref = None
        if raw_plan is not None:
            if not isinstance(raw_plan, Mapping):
                raise ValueError("reference_semantic_context_plan_invalid")
            plan_ref = plan_reference(raw_plan)
            if (
                plan_ref["court_code"] != case_ref["court_code"]
                or plan_ref["charter_revision"] != case_ref["charter_revision"]
            ):
                raise ValueError("reference_semantic_context_plan_foreign")
        for field in ("plan_cursor", "recovery_checkpoint_id"):
            if not isinstance(value.get(field), str) or not value[field].strip():
                raise ValueError(f"invalid_{field}")
        shiguan_revision = value.get("shiguan_revision")
        if (
            not isinstance(shiguan_revision, int)
            or isinstance(shiguan_revision, bool)
            or shiguan_revision < 0
        ):
            raise ValueError("invalid_shiguan_revision")
        return {
            "authority_revision": authority_revision,
            "case_ref": case_ref,
            "plan_ref": plan_ref,
            "plan_cursor": str(value["plan_cursor"]).strip(),
            "recovery_checkpoint_id": str(value["recovery_checkpoint_id"]).strip(),
            "shiguan_revision": shiguan_revision,
        }
    raise ValueError("court_code_required")


def build_semantic_receipt(
    task: dict[str, object],
    context_value: object,
    *,
    event_head_id: str,
    trigger: str,
    created_at: str,
    receipt_sequence: int = 1,
) -> dict[str, object]:
    problems = semantic_binding_problems(task, require_complete=True)
    if problems:
        raise ValueError("semantic_binding_drift:" + ",".join(problems))
    context = normalize_semantic_context(context_value)
    from court_case_binding import case_reference

    case_ref = case_reference(task)
    if context["case_ref"] != case_ref:
        raise ValueError("semantic_receipt_case_reference_mismatch")
    capsule = task.get("invariant_capsule")
    if not isinstance(capsule, Mapping):
        raise ValueError("semantic_receipt_write_set_source_missing")
    write_set = capsule.get("write_set")
    if not isinstance(write_set, list) or any(
        not isinstance(item, str) or not item.strip() for item in write_set
    ):
        raise ValueError("semantic_receipt_write_set_invalid")
    trigger_text = str(trigger or "").strip()
    if not trigger_text:
        raise ValueError("invalid_semantic_trigger")
    if not isinstance(receipt_sequence, int) or isinstance(receipt_sequence, bool) or receipt_sequence < 1:
        raise ValueError("semantic_receipt_sequence_invalid")
    head_id = _required_reference_text(event_head_id, "event_head_id")
    if not _timezone_aware(created_at):
        raise ValueError("invalid_semantic_created_at")
    receipt = {
        "schema": SEMANTIC_RECEIPT_SCHEMA,
        "receipt_sequence": receipt_sequence,
        "task_id": task.get("task_id"),
        "semantic_epoch": task.get("semantic_epoch"),
        **context,
        "dispatch_uid": None,
        "attempt": None,
        "agent_id": None,
        "write_set": list(write_set),
        "event_head_id": head_id,
        "trigger": trigger_text,
        "gate": "semantic_checkpoint",
        "verdict": "VERIFIED",
        "reason_codes": [],
        "created_at": created_at,
        "checkpoint_id": "SC-" + uuid.uuid4().hex.upper(),
    }
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
    context = normalize_semantic_context(context_value)
    problems = semantic_binding_problems(task, require_complete=True)
    if not isinstance(receipt, dict):
        return [*problems, "semantic_receipt_missing"]
    problems.extend(semantic_receipt_integrity_problems(task, receipt))
    from court_case_binding import case_reference

    try:
        expected_case_ref = case_reference(task)
    except ValueError:
        return [*problems, "court_code_required"]
    expected = {
        "schema": SEMANTIC_RECEIPT_SCHEMA,
        "task_id": task.get("task_id"),
        "semantic_epoch": task.get("semantic_epoch"),
        **context,
    }
    for field, expected_value in expected.items():
        if receipt.get(field) != expected_value:
            problems.append(f"semantic_receipt_mismatch:{field}")
    capsule = task.get("invariant_capsule")
    if not isinstance(capsule, Mapping) or receipt.get("write_set") != capsule.get("write_set"):
        problems.append("semantic_receipt_mismatch:write_set")
    if receipt.get("verdict") not in {"VERIFIED", "DISPATCHABLE"}:
        problems.append("semantic_receipt_not_verified")
    if receipt.get("case_ref") != expected_case_ref:
        problems.append("semantic_receipt_mismatch:case_ref")
    return list(dict.fromkeys(problems))


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
    if not isinstance(receipt, dict) or "case_ref" not in receipt:
        raise ValueError("court_code_required")
    binding_problems = semantic_binding_problems(task, require_complete=True)
    if binding_problems:
        raise ValueError(
            "dispatch_context_semantic_binding_failed:" + ",".join(binding_problems)
        )
    integrity = semantic_receipt_integrity_problems(task, receipt)
    if integrity:
        raise ValueError("dispatch_context_receipt_integrity_failed:" + ",".join(integrity))
    if not isinstance(value, dict):
        raise ValueError("dispatch_context_packet_required")
    from court_case_binding import case_reference, plan_reference

    required = {
        "schema", "task_id", "sub_id", "semantic_epoch", "case_ref", "plan_ref",
        "semantic_receipt_id", "plan_cursor", "fork_context", "context_mode", "pointers",
    }
    optional = {"summary", "full_context", "budget_override"}
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    if missing or unknown or value.get("schema") != DISPATCH_CONTEXT_PACKET_SCHEMA:
        raise ValueError("reference_dispatch_context_fields_invalid")
    current_receipt = task.get("semantic_receipt")
    if not isinstance(current_receipt, Mapping) or (
        current_receipt.get("receipt_id") != receipt.get("receipt_id")
    ):
        raise ValueError("dispatch_context_receipt_not_current:receipt_id")
    case_ref = case_reference(task)
    receipt_plan = receipt.get("plan_ref")
    plan_ref = None
    if isinstance(receipt_plan, Mapping):
        plan_ref = plan_reference(receipt_plan)
        if (
            plan_ref["court_code"] != case_ref["court_code"]
            or plan_ref["charter_revision"] != case_ref["charter_revision"]
        ):
            raise ValueError("reference_dispatch_context_plan_foreign")
    if (
        value.get("task_id") != task.get("task_id")
        or value.get("semantic_epoch") != task.get("semantic_epoch")
        or case_reference(value.get("case_ref")) != case_ref
        or receipt.get("case_ref") != case_ref
        or value.get("semantic_receipt_id") != receipt.get("receipt_id")
        or value.get("plan_cursor") != receipt.get("plan_cursor")
    ):
        raise ValueError("reference_dispatch_context_scope_mismatch")
    raw_packet_plan = value.get("plan_ref")
    packet_plan = None if raw_packet_plan is None else plan_reference(raw_packet_plan)
    if packet_plan != plan_ref:
        raise ValueError("reference_dispatch_context_plan_mismatch")
    sub_id = _required_reference_text(value.get("sub_id"), "sub_id")
    if value.get("fork_context") not in {"none", "minimal"}:
        raise ValueError("invalid_dispatch_context_fork_context")
    context_mode = value.get("context_mode")
    if context_mode not in {"bounded", "full"}:
        raise ValueError("invalid_dispatch_context_mode")

    def normalize_pointers(raw: object, *, field: str) -> list[dict[str, object]]:
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"invalid_{field}")
        normalized: list[dict[str, object]] = []
        seen_paths: set[str] = set()
        for index, pointer in enumerate(raw):
            if not isinstance(pointer, Mapping):
                raise ValueError(f"invalid_{field}:{index}")
            path = pointer.get("path")
            if (
                not isinstance(path, str) or not path or path != path.strip()
                or path.endswith(("/", "\\"))
                or any(character in path for character in "*?[]{}\x00\r\n")
                or ".." in path.replace("\\", "/").split("/")
            ):
                raise ValueError(f"dispatch_context_pointer_not_exact:{index}:path")
            if path in seen_paths:
                raise ValueError(f"dispatch_context_pointer_duplicate:{path}")
            seen_paths.add(path)
            has_case = "case_ref" in pointer
            has_plan = "plan_ref" in pointer
            if has_case == has_plan:
                raise ValueError("reference_dispatch_context_pointer_kind_invalid")
            if has_case:
                if set(pointer) != {"path", "case_ref"} or case_reference(pointer["case_ref"]) != case_ref:
                    raise ValueError("reference_dispatch_context_pointer_case_mismatch")
                normalized.append({"path": path, "case_ref": case_ref})
            else:
                if (
                    plan_ref is None
                    or set(pointer) != {"path", "plan_ref"}
                    or plan_reference(pointer["plan_ref"]) != plan_ref
                ):
                    raise ValueError("reference_dispatch_context_pointer_plan_mismatch")
                normalized.append({"path": path, "plan_ref": plan_ref})
        return normalized

    packet = dict(value)
    packet["case_ref"] = case_ref
    packet["plan_ref"] = plan_ref
    packet["sub_id"] = sub_id
    packet["pointers"] = normalize_pointers(value.get("pointers"), field="dispatch_context_pointers")
    if "summary" in packet:
        summary = packet["summary"]
        if (
            not isinstance(summary, Mapping)
            or set(summary) != {"text", "semantic_receipt_id"}
            or not isinstance(summary.get("text"), str)
            or not summary.get("text", "").strip()
            or summary.get("semantic_receipt_id") != receipt.get("receipt_id")
        ):
            raise ValueError("invalid_dispatch_context_summary")
        packet["summary"] = {
            "text": str(summary["text"]),
            "semantic_receipt_id": str(summary["semantic_receipt_id"]),
        }
    if context_mode == "bounded":
        if "full_context" in packet or "budget_override" in packet:
            raise ValueError("dispatch_context_bounded_full_context_forbidden")
        packet_bytes = len(canonical_json_bytes(packet))
        if packet_bytes > DISPATCH_CONTEXT_PACKET_MAX_BYTES:
            raise ValueError("dispatch_context_packet_exceeds_2kib")
    else:
        if "full_context" not in packet:
            raise ValueError("dispatch_context_full_context_required")
        packet["budget_override"] = _normalize_dispatch_context_budget_override(
            packet.get("budget_override")
        )
        packet_bytes = len(canonical_json_bytes(packet))
        if packet_bytes > int(packet["budget_override"]["max_bytes"]):
            raise ValueError("dispatch_context_packet_exceeds_explicit_budget")

    reload_required: list[str] = []
    if previous_packet is not None:
        if not isinstance(previous_packet, Mapping):
            raise ValueError("invalid_previous_dispatch_context_packet")
        if previous_packet.get("task_id") != task.get("task_id"):
            raise ValueError("dispatch_context_resume_task_id_mismatch")
        if previous_packet.get("sub_id") != sub_id:
            raise ValueError("dispatch_context_resume_sub_id_mismatch")
        if (
            case_reference(previous_packet.get("case_ref")) != case_ref
            or (None if previous_packet.get("plan_ref") is None else plan_reference(previous_packet["plan_ref"])) != plan_ref
        ):
            raise ValueError("dispatch_context_resume_case_or_plan_changed")
        previous_pointers = normalize_pointers(
            previous_packet.get("pointers"), field="previous_dispatch_context_pointers"
        )
        previous_by_path = {pointer["path"]: pointer for pointer in previous_pointers}
        current_by_path = {pointer["path"]: pointer for pointer in packet["pointers"]}
        reload_required = sorted(
            path for path, pointer in current_by_path.items()
            if previous_by_path.get(path) != pointer
        )
        reloaded_by_path: dict[str, dict[str, object]] = {}
        if reloaded_pointers is not None:
            reloaded_by_path = {
                pointer["path"]: pointer
                for pointer in normalize_pointers(
                    reloaded_pointers, field="reloaded_dispatch_context_pointers"
                )
            }
        for path, pointer in reloaded_by_path.items():
            if path not in reload_required:
                raise ValueError(f"dispatch_context_reload_not_required:{path}")
            if pointer != current_by_path.get(path):
                raise ValueError(f"dispatch_context_reload_reference_mismatch:{path}")
        for path in reload_required:
            if reloaded_by_path.get(path) != current_by_path[path]:
                raise ValueError(f"dispatch_context_reload_required:{path}")
    elif reloaded_pointers is not None:
        raise ValueError("dispatch_context_reload_without_resume")
    return {"packet": packet, "packet_bytes": packet_bytes, "reload_required": reload_required}


def resume_context_problems(
    receipt: object,
    context_value: object,
) -> tuple[dict[str, object], list[str]]:
    context = normalize_semantic_context(context_value)
    if not isinstance(receipt, dict):
        return context, ["semantic_receipt_missing"]
    problems: list[str] = []
    if "case_ref" not in receipt:
        return context, ["court_code_required"]
    for field in REFERENCE_SEMANTIC_CONTEXT_FIELDS:
        if field == "authority_revision":
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


def _bounded_consultation_text(value: object, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"consultation_ref_{field}_required")
    text = value.strip()
    if len(text.encode("utf-8")) > limit or any(
        character in text for character in "\x00\r\n"
    ):
        raise ValueError(f"consultation_ref_{field}_invalid")
    return text


def _consultation_role(value: object, field: str) -> str:
    role = _bounded_consultation_text(value, field, 64).lower()
    if not re.fullmatch(r"[a-z][a-z0-9-]*", role):
        raise ValueError(f"consultation_ref_{field}_invalid")
    return role


def _consultation_pointer(value: object, field: str) -> str:
    pointer = _bounded_consultation_text(
        value, field, CONSULTATION_REF_MAX_POINTER_BYTES
    )
    lowered = pointer.casefold()
    if any(token in lowered for token in ("pending/", "/pending/", "private/", "/private/")):
        raise ValueError("consultation_ref_privacy_gate_failed")
    return pointer


def normalize_consultation_refs(value: object) -> list[dict[str, object]]:
    """Validate bounded, non-authoritative consultation metadata.

    The references are attached to an existing report or result envelope only.
    They never describe a new dispatch, transport, ledger, or authority edge.
    """

    if not isinstance(value, list) or not value:
        raise ValueError("consultation_refs_required")
    if len(value) > CONSULTATION_REF_MAX_COUNT:
        raise ValueError("consultation_refs_exceed_limit")
    if not all(isinstance(item, dict) and "case_ref" in item for item in value):
        raise ValueError("court_code_required")
    from court_case_binding import case_reference, plan_reference

    fields = {
        "consultation_id",
        "case_ref",
        "plan_ref",
        "from_role",
        "to_role",
        "purpose",
        "input_pointer",
        "reply_pointer",
        "write_authority_granted",
    }
    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for item in value:
        if set(item) != fields:
            raise ValueError("consultation_ref_fields_invalid")
        reference = case_reference(item["case_ref"])
        raw_plan = item.get("plan_ref")
        plan_ref = None
        if raw_plan is not None:
            if not isinstance(raw_plan, Mapping):
                raise ValueError("consultation_ref_plan_invalid")
            plan_ref = plan_reference(raw_plan)
            if (
                plan_ref["court_code"] != reference["court_code"]
                or plan_ref["charter_revision"] != reference["charter_revision"]
            ):
                raise ValueError("consultation_ref_plan_foreign")
        consultation_id = _bounded_consultation_text(
            item.get("consultation_id"), "consultation_id", 128
        )
        if consultation_id in seen_ids:
            raise ValueError("consultation_ref_duplicate")
        seen_ids.add(consultation_id)
        from_role = _consultation_role(item.get("from_role"), "from_role")
        to_role = _consultation_role(item.get("to_role"), "to_role")
        if from_role == to_role:
            raise ValueError("consultation_ref_roles_must_differ")
        if item.get("write_authority_granted") is not False:
            raise ValueError("consultation_ref_write_authority_forbidden")
        normalized.append(
            {
                "consultation_id": consultation_id,
                "case_ref": reference,
                "plan_ref": plan_ref,
                "from_role": from_role,
                "to_role": to_role,
                "purpose": _bounded_consultation_text(
                    item.get("purpose"), "purpose", CONSULTATION_REF_MAX_PURPOSE_BYTES
                ),
                "input_pointer": _consultation_pointer(
                    item.get("input_pointer"), "input_pointer"
                ),
                "reply_pointer": _consultation_pointer(
                    item.get("reply_pointer"), "reply_pointer"
                ),
                "write_authority_granted": False,
            }
        )
    return normalized


def normalize_result_envelope(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("structured_result_envelope_required")
    envelope = dict(value)
    if envelope.get("schema") != OFFICE_RESULT_SCHEMA:
        raise ValueError("invalid_result_envelope_schema")
    if "case_ref" not in envelope:
        raise ValueError("court_code_required")
    if "plan_ref" not in envelope:
        raise ValueError("result_envelope_plan_ref_required")
    from court_case_binding import case_reference, plan_reference

    allowed_fields = {
        "schema",
        "task_id",
        "semantic_epoch",
        "case_ref",
        "plan_ref",
        "checkpoint_id",
        "dispatch_uid",
        "attempt",
        "office_instance_id",
        "office_instance_kind",
        "carrier_proof",
        "agent_id",
        "role",
        "direct_superior",
        "worktree",
        "write_set",
        "status",
        "summary",
        "evidence",
        "produced_at",
        "recovery_input_ids",
        "consultation_refs",
    }
    private_fields = {
        field
        for field in envelope
        if field in {
            "raw", "raw_body", "body", "result", "raw_result", "log", "transcript",
            "prompt", "private", "private_body", "pending", "source_envelope",
            "secret", "credential", "token", "password",
        }
    }
    if private_fields:
        raise ValueError("result_envelope_private_field")
    unknown_fields = set(envelope) - allowed_fields
    if unknown_fields:
        raise ValueError("result_envelope_unknown_field")
    text_fields = (
        "task_id",
        "checkpoint_id",
        "dispatch_uid",
        "office_instance_id",
        "agent_id",
        "role",
        "direct_superior",
        "worktree",
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
    envelope["case_ref"] = case_reference(envelope["case_ref"])
    raw_plan = envelope.get("plan_ref")
    if raw_plan is not None:
        if not isinstance(raw_plan, Mapping):
            raise ValueError("invalid_result_envelope_field:plan_ref")
        envelope["plan_ref"] = plan_reference(raw_plan)
        if (
            envelope["plan_ref"]["court_code"] != envelope["case_ref"]["court_code"]
            or envelope["plan_ref"]["charter_revision"]
            != envelope["case_ref"]["charter_revision"]
        ):
            raise ValueError("result_envelope_plan_foreign")
    write_set = envelope.get("write_set")
    if not isinstance(write_set, list) or any(
        not isinstance(item, str) or not item.strip() for item in write_set
    ):
        raise ValueError("invalid_result_envelope_field:write_set")
    if envelope["status"] not in {"completed", "failed", "cancelled"}:
        raise ValueError("invalid_result_envelope_field:status")
    evidence = envelope.get("evidence")
    if not isinstance(evidence, list) or any(
        not isinstance(item, str) or not item.strip() for item in evidence
    ):
        raise ValueError("invalid_result_envelope_field:evidence")
    if len(set(evidence)) != len(evidence):
        raise ValueError("result_envelope_duplicate_evidence")
    kind = envelope.get("office_instance_kind")
    proof = envelope.get("carrier_proof")
    if "office_instance_kind" in envelope:
        if kind not in {"child_agent", "worktree_thread"}:
            raise ValueError("result_envelope_invalid_office_instance_kind")
        if not isinstance(proof, dict):
            raise ValueError("result_envelope_carrier_proof_required")
        if kind == "child_agent":
            if set(proof) != {"agent_id"} or not isinstance(
                proof.get("agent_id"), str
            ) or not proof["agent_id"].strip():
                raise ValueError("result_envelope_unknown_nested_field")
        else:
            expected = {
                "thread_id",
                "canonical_worktree_id",
                "canonical_worktree_path",
                "repo_id",
                "common_dir_fingerprint",
                "worktree_fingerprint",
                "branch",
                "start_head",
            }
            if set(proof) != expected or any(
                not isinstance(proof.get(field), str) or not proof[field].strip()
                for field in expected
            ):
                raise ValueError("result_envelope_unknown_nested_field")
    elif "carrier_proof" in envelope:
        raise ValueError("result_envelope_carrier_proof_required")
    if "recovery_input_ids" in envelope:
        recovery_ids = envelope["recovery_input_ids"]
        if not isinstance(recovery_ids, list) or any(
            not isinstance(item, str) or not item.strip() for item in recovery_ids
        ):
            raise ValueError("result_envelope_nested_field_forbidden")
        if len(set(recovery_ids)) != len(recovery_ids):
            raise ValueError("result_envelope_duplicate_recovery_id")
    if "consultation_refs" in envelope:
        envelope["consultation_refs"] = normalize_consultation_refs(
            envelope["consultation_refs"]
        )
    return envelope


def _string_schema(*, const: str | None = None) -> dict[str, object]:
    value: dict[str, object] = {"type": "string", "minLength": 1}
    if const is not None:
        value["const"] = const
    return value


def _digest_schema() -> dict[str, object]:
    return {"type": "string", "pattern": "^[0-9a-f]{64}$"}


def _positive_integer_schema() -> dict[str, object]:
    return {"type": "integer", "minimum": 1}


def _unique_string_array_schema() -> dict[str, object]:
    return {
        "type": "array",
        "uniqueItems": True,
        "items": {"type": "string", "minLength": 1},
    }


def _consultation_refs_json_schema() -> dict[str, object]:
    case_ref = {
        "type": "object",
        "additionalProperties": False,
        "required": ["court_code", "charter_revision"],
        "properties": {
            "court_code": _string_schema(),
            "charter_revision": _positive_integer_schema(),
        },
    }
    plan_ref = {
        "type": "object",
        "additionalProperties": False,
        "required": ["court_code", "charter_revision", "plan_revision"],
        "properties": {
            "court_code": _string_schema(),
            "charter_revision": _positive_integer_schema(),
            "plan_revision": _positive_integer_schema(),
        },
    }
    fields = {
        "consultation_id", "case_ref", "plan_ref", "from_role", "to_role",
        "purpose", "input_pointer", "reply_pointer", "write_authority_granted",
    }
    return {
        "type": "array",
        "minItems": 1,
        "maxItems": CONSULTATION_REF_MAX_COUNT,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": sorted(fields),
            "properties": {
                "consultation_id": _string_schema(),
                "case_ref": case_ref,
                "plan_ref": {"oneOf": [plan_ref, {"type": "null"}]},
                "from_role": _string_schema(),
                "to_role": _string_schema(),
                "purpose": _string_schema(),
                "input_pointer": _string_schema(),
                "reply_pointer": _string_schema(),
                "write_authority_granted": {"type": "boolean", "const": False},
            },
        },
    }


def office_result_envelope_json_schema() -> dict[str, object]:
    carrier_child = {
        "type": "object",
        "additionalProperties": False,
        "required": ["agent_id"],
        "properties": {"agent_id": _string_schema()},
    }
    carrier_worktree_fields = {
        "thread_id",
        "canonical_worktree_id",
        "canonical_worktree_path",
        "repo_id",
        "common_dir_fingerprint",
        "worktree_fingerprint",
        "branch",
        "start_head",
    }
    carrier_worktree = {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(carrier_worktree_fields),
        "properties": {field: _string_schema() for field in carrier_worktree_fields},
    }
    required = {
        "schema",
        "task_id",
        "semantic_epoch",
        "case_ref",
        "plan_ref",
        "checkpoint_id",
        "dispatch_uid",
        "attempt",
        "office_instance_id",
        "agent_id",
        "role",
        "direct_superior",
        "worktree",
        "write_set",
        "status",
        "summary",
        "evidence",
        "produced_at",
    }
    properties: dict[str, object] = {
        "schema": _string_schema(const=OFFICE_RESULT_SCHEMA),
        "task_id": _string_schema(),
        "semantic_epoch": _positive_integer_schema(),
        "case_ref": {
            "type": "object",
            "additionalProperties": False,
            "required": ["court_code", "charter_revision"],
            "properties": {
                "court_code": _string_schema(),
                "charter_revision": _positive_integer_schema(),
            },
        },
        "plan_ref": {
            "oneOf": [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["court_code", "charter_revision", "plan_revision"],
                    "properties": {
                        "court_code": _string_schema(),
                        "charter_revision": _positive_integer_schema(),
                        "plan_revision": _positive_integer_schema(),
                    },
                },
                {"type": "null"},
            ],
        },
        "checkpoint_id": _string_schema(),
        "dispatch_uid": _string_schema(),
        "attempt": _positive_integer_schema(),
        "office_instance_id": _string_schema(),
        "office_instance_kind": {
            "type": "string",
            "enum": ["child_agent", "worktree_thread"],
        },
        "carrier_proof": {"oneOf": [carrier_child, carrier_worktree]},
        "agent_id": _string_schema(),
        "role": _string_schema(),
        "direct_superior": _string_schema(),
        "worktree": _string_schema(),
        "write_set": _unique_string_array_schema(),
        "status": {"type": "string", "enum": ["completed", "failed", "cancelled"]},
        "summary": _string_schema(),
        "evidence": _unique_string_array_schema(),
        "produced_at": _string_schema(),
        "recovery_input_ids": _unique_string_array_schema(),
        "consultation_refs": _consultation_refs_json_schema(),
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(required),
        "properties": properties,
    }


def result_quarantine_core_json_schema() -> dict[str, object]:
    required = {
        "schema", "quarantine_id", "payload_sha256", "task_id", "semantic_epoch",
        "case_ref", "plan_ref", "checkpoint_id", "dispatch_uid",
        "attempt", "office_instance_id", "office_instance_kind", "carrier_proof",
        "agent_id", "role", "direct_superior", "worktree", "write_set",
        "source_status", "source_final_status", "source_release_status",
        "source_result_state", "failure_kind", "reason_codes", "received_at",
        "quarantine_event_id", "core_sha256",
    }
    properties: dict[str, object] = {field: _string_schema() for field in required}
    properties.update(
        {
            "schema": _string_schema(const="court.office.result_quarantine.v2"),
            "semantic_epoch": _positive_integer_schema(),
            "attempt": _positive_integer_schema(),
            "payload_sha256": _digest_schema(),
            "case_ref": {"type": "object"},
            "plan_ref": {"type": ["object", "null"]},
            "carrier_proof": {"type": "object"},
            "write_set": _unique_string_array_schema(),
            "core_sha256": _digest_schema(),
            "source_status": _string_schema(const="failed"),
            "source_final_status": _string_schema(const="failed"),
            "source_release_status": _string_schema(const="closed"),
            "source_result_state": _string_schema(const="QUARANTINED"),
            "failure_kind": _string_schema(const="result_binding_quarantine"),
            "reason_codes": _unique_string_array_schema(),
        }
    )
    return {"type": "object", "additionalProperties": False, "required": sorted(required), "properties": properties}


def result_recovery_head_json_schema() -> dict[str, object]:
    required = {
        "schema", "recovery_id", "quarantine_id", "revision", "state",
        "previous_head_sha256", "projection_sha256", "target_binding_sha256",
        "review_receipt_sha256", "handoff_receipt_sha256", "consume_receipt_sha256",
        "operation_id", "event_id", "created_at", "head_sha256",
    }
    properties: dict[str, object] = {field: _string_schema() for field in required}
    properties.update(
        {
            "schema": _string_schema(const="court.office.result_recovery_head.v1"),
            "revision": _positive_integer_schema(),
            "state": {
                "type": "string",
                "enum": ["REVIEW_PENDING", "READY_FOR_HANDOFF", "REJECTED", "HANDED_OFF", "CONSUMED"],
            },
        }
    )
    for field in (
        "previous_head_sha256", "projection_sha256", "target_binding_sha256",
        "review_receipt_sha256", "handoff_receipt_sha256", "consume_receipt_sha256", "head_sha256",
    ):
        properties[field] = _digest_schema()
    return {"type": "object", "additionalProperties": False, "required": sorted(required), "properties": properties}


def _result_recovery_receipt_schema(schema_name: str, fields: set[str]) -> dict[str, object]:
    properties: dict[str, object] = {field: _string_schema() for field in fields}
    properties.update(
        {
            "schema": _string_schema(const=schema_name),
            "task_revision": _positive_integer_schema(),
            "recovery_revision": _positive_integer_schema(),
            "reason_codes": _unique_string_array_schema(),
        }
    )
    for field in (
        "quarantine_core_sha256", "previous_head_sha256", "projection_sha256",
        "review_receipt_sha256", "handoff_receipt_sha256", "target_binding_sha256",
        "evidence_sha256", "receipt_sha256", "target_result_envelope_sha256",
    ):
        if field in fields:
            properties[field] = _digest_schema()
    if "native_host_request_ref" in fields:
        properties["native_host_request_ref"] = {
            "type": "object",
            "additionalProperties": False,
            "required": ["court_code", "office_instance_id", "dispatch_uid", "attempt"],
            "properties": {
                "court_code": _string_schema(),
                "office_instance_id": _string_schema(),
                "dispatch_uid": _string_schema(),
                "attempt": _positive_integer_schema(),
            },
        }
    if "native_host_action_receipt" in fields:
        properties["native_host_action_receipt"] = {
            "type": "object",
            "required": ["receipt_id", "request_ref", "host_action_id"],
            "properties": {
                "receipt_id": _string_schema(),
                "request_ref": properties.get("native_host_request_ref", {"type": "object"}),
                "host_action_id": _string_schema(),
            },
        }
    return {"type": "object", "additionalProperties": False, "required": sorted(fields), "properties": properties}


def result_recovery_review_receipt_json_schema() -> dict[str, object]:
    return _result_recovery_receipt_schema(
        "court.office.result_recovery_review_receipt.v1",
        {
            "schema", "receipt_id", "operation_id", "task_id", "task_revision",
            "quarantine_id", "quarantine_core_sha256", "recovery_id", "recovery_revision",
            "previous_head_sha256", "decision", "reason_codes", "evidence_pointer",
            "evidence_sha256", "projection_sha256", "actor", "reviewed_at", "event_id", "receipt_sha256",
        },
    )


def result_recovery_handoff_receipt_json_schema() -> dict[str, object]:
    return _result_recovery_receipt_schema(
        "court.office.result_recovery_handoff_receipt.v1",
        {
            "schema", "receipt_id", "operation_id", "task_id", "task_revision", "quarantine_id",
            "recovery_id", "recovery_revision", "previous_head_sha256", "review_receipt_sha256",
            "target_binding_sha256", "native_host_request_ref", "native_host_action_receipt_id",
            "native_host_action_receipt", "reason_codes", "evidence_pointer", "evidence_sha256",
            "actor", "handed_off_at", "event_id", "receipt_sha256",
        },
    )


def result_recovery_consume_receipt_json_schema() -> dict[str, object]:
    return _result_recovery_receipt_schema(
        "court.office.result_recovery_consume_receipt.v1",
        {
            "schema", "receipt_id", "operation_id", "task_id", "task_revision", "quarantine_id",
            "recovery_id", "recovery_revision", "previous_head_sha256", "handoff_receipt_sha256",
            "target_binding_sha256", "target_result_envelope_sha256", "target_finish_event_id",
            "reason_codes", "evidence_pointer", "evidence_sha256", "actor", "consumed_at", "event_id", "receipt_sha256",
        },
    )


def result_recovery_projection_json_schema() -> dict[str, object]:
    """Closed, metadata-only projection used after Menxia review.

    The projection deliberately keeps the bounded result envelope shape and
    adds only recovery identifiers and its own recovery integrity fields. It never carries the source
    envelope, transcript, prompt, or other raw/private material.
    """
    required = {
        "schema", "recovery_id", "quarantine_id", "source_payload_sha256",
        "task_id", "semantic_epoch", "case_ref", "plan_ref",
        "checkpoint_id", "dispatch_uid", "attempt", "office_instance_id",
        "office_instance_kind", "carrier_proof", "agent_id", "role",
        "direct_superior", "worktree", "write_set", "status", "summary",
        "evidence", "produced_at", "projection_sha256",
    }
    properties: dict[str, object] = {field: _string_schema() for field in required}
    properties.update(
        {
            "schema": _string_schema(const=RESULT_RECOVERY_PROJECTION_SCHEMA),
            "semantic_epoch": _positive_integer_schema(),
            "attempt": _positive_integer_schema(),
            "case_ref": {
                "type": "object", "additionalProperties": False,
                "required": ["court_code", "charter_revision"],
                "properties": {"court_code": _string_schema(), "charter_revision": _positive_integer_schema()},
            },
            "plan_ref": {"type": ["object", "null"]},
            "carrier_proof": {"type": "object"},
            "write_set": _unique_string_array_schema(),
            "evidence": _unique_string_array_schema(),
            "projection_sha256": _digest_schema(),
        }
    )
    for field in ("source_payload_sha256",):
        properties[field] = _digest_schema()
    properties["office_instance_kind"] = {
        "type": "string",
        "enum": ["child_agent", "worktree_thread"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(required),
        "properties": properties,
    }


def result_recovery_binding_json_schema() -> dict[str, object]:
    required = {
        "schema", "recovery_id", "quarantine_id", "quarantine_core_sha256",
        "recovery_head_sha256", "projection_sha256", "review_receipt_sha256",
        "target_binding_sha256",
    }
    properties: dict[str, object] = {field: _string_schema() for field in required}
    properties["schema"] = _string_schema(const=RESULT_RECOVERY_BINDING_SCHEMA)
    for field in (
        "quarantine_core_sha256", "recovery_head_sha256", "projection_sha256",
        "review_receipt_sha256", "target_binding_sha256",
    ):
        properties[field] = _digest_schema()
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(required),
        "properties": properties,
    }


_RESULT_PRIVATE_KEY_TOKENS = frozenset(
    {
        "raw", "raw_body", "body", "prompt", "transcript", "private",
        "private_body", "pending", "secret", "credential", "token", "password",
    }
)


def _result_private_nested(value: object) -> bool:
    """Reject private/pending keys recursively without persisting their body."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().casefold()
            if normalized in _RESULT_PRIVATE_KEY_TOKENS:
                return True
            if _result_private_nested(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_result_private_nested(child) for child in value)
    return False


def _bounded_evidence_pointers(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("result_recovery_projection_evidence_invalid")
    if len(value) > 8:
        raise ValueError("result_recovery_projection_evidence_invalid")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("result_recovery_projection_evidence_invalid")
        text = item.strip()
        if len(text.encode("utf-8")) > 512 or any(char in text for char in "\x00\r\n"):
            raise ValueError("result_recovery_projection_evidence_invalid")
        lowered = text.casefold()
        if any(token in lowered for token in ("pending/", "/pending/", "private/", "/private/")):
            raise ValueError("result_recovery_privacy_gate_failed")
        result.append(text)
    if len(set(result)) != len(result):
        raise ValueError("result_recovery_projection_evidence_invalid")
    return result


def build_result_recovery_projection(
    *,
    source_result: Mapping[str, object],
    recovery_id: str,
    quarantine_id: str,
) -> dict[str, object]:
    envelope = normalize_result_envelope(dict(source_result))
    kind = envelope.get("office_instance_kind")
    if kind not in {"child_agent", "worktree_thread"}:
        raise ValueError("result_recovery_projection_kind_required")
    if _result_private_nested(source_result):
        raise ValueError("result_recovery_privacy_gate_failed")
    if not isinstance(recovery_id, str) or not recovery_id.strip():
        raise ValueError("result_recovery_projection_identity_required")
    if not isinstance(quarantine_id, str) or not quarantine_id.strip():
        raise ValueError("result_recovery_projection_identity_required")
    summary = str(envelope["summary"])
    if len(summary.encode("utf-8")) > 2048 or any(char in summary for char in "\x00\r\n"):
        raise ValueError("result_recovery_privacy_gate_failed")
    projection: dict[str, object] = {
        "schema": RESULT_RECOVERY_PROJECTION_SCHEMA,
        "recovery_id": recovery_id.strip(),
        "quarantine_id": quarantine_id.strip(),
        "source_payload_sha256": source_result_payload_sha256(envelope),
        "task_id": envelope["task_id"],
        "semantic_epoch": envelope["semantic_epoch"],
        "case_ref": deepcopy(envelope["case_ref"]),
        "plan_ref": deepcopy(envelope["plan_ref"]),
        "checkpoint_id": envelope["checkpoint_id"],
        "dispatch_uid": envelope["dispatch_uid"],
        "attempt": envelope["attempt"],
        "office_instance_id": envelope["office_instance_id"],
        "office_instance_kind": kind,
        "carrier_proof": deepcopy(envelope.get("carrier_proof", {})),
        "agent_id": envelope["agent_id"],
        "role": envelope["role"],
        "direct_superior": envelope["direct_superior"],
        "worktree": envelope["worktree"],
        "write_set": deepcopy(envelope["write_set"]),
        "status": envelope["status"],
        "summary": summary,
        "evidence": _bounded_evidence_pointers(envelope["evidence"]),
        "produced_at": envelope["produced_at"],
    }
    projection["projection_sha256"] = canonical_json_sha256(projection)
    return projection


def validate_result_recovery_projection(
    value: object,
    *,
    expected_core: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("result_recovery_projection_required")
    required = set(result_recovery_projection_json_schema()["required"])
    if set(value) != required or value.get("schema") != RESULT_RECOVERY_PROJECTION_SCHEMA:
        raise ValueError("result_recovery_projection_schema_mismatch")
    for field in ("source_payload_sha256", "projection_sha256"):
        _canonical_digest(value.get(field), field)
    for field in ("semantic_epoch", "attempt"):
        raw = value.get(field)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1:
            raise ValueError("result_recovery_projection_schema_mismatch")
    if value.get("office_instance_kind") not in {"child_agent", "worktree_thread"}:
        raise ValueError("result_recovery_projection_schema_mismatch")
    try:
        from court_case_binding import case_reference, plan_reference

        case_ref = case_reference(value.get("case_ref"))
        raw_plan = value.get("plan_ref")
        if raw_plan is not None:
            plan_ref = plan_reference(raw_plan)
            if (
                plan_ref["court_code"] != case_ref["court_code"]
                or plan_ref["charter_revision"] != case_ref["charter_revision"]
            ):
                raise ValueError("result_recovery_projection_schema_mismatch")
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc) == "result_recovery_projection_schema_mismatch":
            raise
        raise ValueError("result_recovery_projection_schema_mismatch") from exc
    if not isinstance(value.get("carrier_proof"), Mapping):
        raise ValueError("result_recovery_projection_schema_mismatch")
    if not isinstance(value.get("write_set"), list) or any(
        not isinstance(item, str) or not item.strip() for item in value["write_set"]
    ):
        raise ValueError("result_recovery_projection_schema_mismatch")
    summary = value.get("summary")
    if not isinstance(summary, str) or len(summary.encode("utf-8")) > 2048 or any(
        char in summary for char in "\x00\r\n"
    ):
        raise ValueError("result_recovery_privacy_gate_failed")
    _bounded_evidence_pointers(value.get("evidence"))
    if canonical_json_sha256({key: item for key, item in value.items() if key != "projection_sha256"}) != value.get("projection_sha256"):
        raise ValueError("result_recovery_projection_digest_mismatch")
    if expected_core is not None:
        if (
            value.get("semantic_epoch") != expected_core.get("semantic_epoch")
            or value.get("quarantine_id") != expected_core.get("quarantine_id")
            or value.get("source_payload_sha256") != expected_core.get("payload_sha256")
        ):
            raise ValueError("result_recovery_projection_core_mismatch")
    return dict(value)


def build_result_recovery_binding(
    *,
    recovery_id: str,
    quarantine_id: str,
    quarantine_core_sha256: str,
    recovery_head_sha256: str,
    projection_sha256: str,
    review_receipt_sha256: str,
    target_binding_sha256: str,
) -> dict[str, object]:
    binding = {
        "schema": RESULT_RECOVERY_BINDING_SCHEMA,
        "recovery_id": recovery_id,
        "quarantine_id": quarantine_id,
        "quarantine_core_sha256": _canonical_digest(quarantine_core_sha256, "quarantine_core_sha256"),
        "recovery_head_sha256": _canonical_digest(recovery_head_sha256, "recovery_head_sha256"),
        "projection_sha256": _canonical_digest(projection_sha256, "projection_sha256"),
        "review_receipt_sha256": _canonical_digest(review_receipt_sha256, "review_receipt_sha256"),
        "target_binding_sha256": _canonical_digest(target_binding_sha256, "target_binding_sha256"),
    }
    if not all(isinstance(binding.get(field), str) and str(binding[field]).strip() for field in ("recovery_id", "quarantine_id")):
        raise ValueError("result_recovery_binding_identity_required")
    return binding


def validate_result_recovery_binding(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("result_recovery_binding_required")
    required = set(result_recovery_binding_json_schema()["required"])
    if set(value) != required or value.get("schema") != RESULT_RECOVERY_BINDING_SCHEMA:
        raise ValueError("result_recovery_binding_schema_mismatch")
    for field in (
        "quarantine_core_sha256", "recovery_head_sha256", "projection_sha256",
        "review_receipt_sha256", "target_binding_sha256",
    ):
        _canonical_digest(value.get(field), field)
    for field in ("recovery_id", "quarantine_id"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ValueError("result_recovery_binding_identity_required")
    return dict(value)


def source_result_payload_sha256(source_result: object) -> str:
    return canonical_json_sha256(source_result)


def _core_digest(value: Mapping[str, object]) -> str:
    return canonical_json_sha256({key: item for key, item in value.items() if key != "core_sha256"})


def build_result_quarantine_core(
    *,
    source_result: Mapping[str, object],
    source_final_status: str,
    source_release_status: str,
    source_result_state: str,
    reason_codes: list[str],
    received_at: str,
    payload_sha256: str | None = None,
) -> dict[str, object]:
    envelope = normalize_result_envelope(dict(source_result))
    kind = envelope.get("office_instance_kind")
    if kind not in {"child_agent", "worktree_thread"}:
        raise ValueError("result_envelope_carrier_binding_required")
    if source_final_status != "failed" or source_release_status != "closed" or source_result_state != "QUARANTINED":
        raise ValueError("result_quarantine_core_terminal_state_required")
    if not isinstance(reason_codes, list) or not reason_codes or any(
        not isinstance(code, str) or not code.strip() for code in reason_codes
    ) or len(set(reason_codes)) != len(reason_codes):
        raise ValueError("result_quarantine_core_reason_codes_invalid")
    carrier = envelope.get("carrier_proof", {})
    source_payload = (
        str(payload_sha256 or "").strip()
        or source_result_payload_sha256(envelope)
    )
    core: dict[str, object] = {
        "schema": "court.office.result_quarantine.v2",
        "quarantine_id": "QR-" + source_payload[:24].upper(),
        "payload_sha256": source_payload,
        "task_id": envelope["task_id"],
        "semantic_epoch": envelope["semantic_epoch"],
        "case_ref": deepcopy(envelope["case_ref"]),
        "plan_ref": deepcopy(envelope["plan_ref"]),
        "checkpoint_id": envelope["checkpoint_id"],
        "dispatch_uid": envelope["dispatch_uid"],
        "attempt": envelope["attempt"],
        "office_instance_id": envelope["office_instance_id"],
        "office_instance_kind": kind,
        "carrier_proof": deepcopy(carrier),
        "agent_id": envelope["agent_id"],
        "role": envelope["role"],
        "direct_superior": envelope["direct_superior"],
        "worktree": envelope["worktree"],
        "write_set": deepcopy(envelope["write_set"]),
        "source_status": "failed",
        "source_final_status": "failed",
        "source_release_status": "closed",
        "source_result_state": "QUARANTINED",
        "failure_kind": "result_binding_quarantine",
        "reason_codes": sorted(reason_codes),
        "received_at": received_at,
        "quarantine_event_id": deterministic_result_recovery_event_id(
            "QUARANTINE-" + source_payload,
            "quarantine",
            source_payload,
        ),
    }
    core["core_sha256"] = _core_digest(core)
    return core


def validate_result_quarantine_core(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("result_quarantine_core_required")
    required = set(result_quarantine_core_json_schema()["required"])
    if set(value) != required:
        raise ValueError("result_quarantine_core_schema_mismatch")
    if value.get("schema") != "court.office.result_quarantine.v2":
        raise ValueError("result_quarantine_core_schema_mismatch")
    for field in ("payload_sha256", "core_sha256"):
        _canonical_digest(value.get(field), field)
    try:
        from court_case_binding import case_reference, plan_reference

        case_ref = case_reference(value.get("case_ref"))
        raw_plan = value.get("plan_ref")
        if raw_plan is not None:
            plan_ref = plan_reference(raw_plan)
            if (
                plan_ref["court_code"] != case_ref["court_code"]
                or plan_ref["charter_revision"] != case_ref["charter_revision"]
            ):
                raise ValueError("result_quarantine_core_schema_mismatch")
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc) == "result_quarantine_core_schema_mismatch":
            raise
        raise ValueError("result_quarantine_core_schema_mismatch") from exc
    if not isinstance(value.get("carrier_proof"), Mapping):
        raise ValueError("result_quarantine_core_schema_mismatch")
    if not isinstance(value.get("write_set"), list) or any(
        not isinstance(item, str) or not item.strip() for item in value["write_set"]
    ):
        raise ValueError("result_quarantine_core_schema_mismatch")
    if value.get("source_status") != "failed" or value.get("source_final_status") != "failed" or value.get("source_release_status") != "closed" or value.get("source_result_state") != "QUARANTINED" or value.get("failure_kind") != "result_binding_quarantine":
        raise ValueError("result_quarantine_core_terminal_state_mismatch")
    reasons = value.get("reason_codes")
    if not isinstance(reasons, list) or not reasons or len(set(reasons)) != len(reasons):
        raise ValueError("result_quarantine_core_reason_codes_invalid")
    if _core_digest(value) != value["core_sha256"]:
        raise ValueError("result_quarantine_core_digest_mismatch")
    return dict(value)


def build_result_recovery_head(
    *,
    quarantine_core: Mapping[str, object],
    recovery_id: str,
    previous_head: Mapping[str, object] | None,
    state: str,
    projection_sha256: str,
    target_binding_sha256: str,
    review_receipt_sha256: str,
    handoff_receipt_sha256: str,
    consume_receipt_sha256: str,
    operation_id: str,
    event_id: str,
    created_at: str,
) -> dict[str, object]:
    core = validate_result_quarantine_core(dict(quarantine_core))
    if not isinstance(recovery_id, str) or not recovery_id.strip() or not isinstance(operation_id, str) or not operation_id.strip() or not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("result_recovery_head_identity_required")
    if state not in {"REVIEW_PENDING", "READY_FOR_HANDOFF", "REJECTED", "HANDED_OFF", "CONSUMED"}:
        raise ValueError("result_recovery_head_state_invalid")
    revision = 1
    previous_sha = "0" * 64
    if previous_head is not None:
        prior = validate_result_recovery_head(previous_head)
        revision = int(prior["revision"]) + 1
        previous_sha = str(prior["head_sha256"])
    head: dict[str, object] = {
        "schema": "court.office.result_recovery_head.v1",
        "recovery_id": recovery_id,
        "quarantine_id": core["quarantine_id"],
        "revision": revision,
        "state": state,
        "previous_head_sha256": previous_sha,
        "projection_sha256": _canonical_digest(projection_sha256, "projection_sha256"),
        "target_binding_sha256": _canonical_digest(target_binding_sha256, "target_binding_sha256"),
        "review_receipt_sha256": _canonical_digest(review_receipt_sha256, "review_receipt_sha256"),
        "handoff_receipt_sha256": _canonical_digest(handoff_receipt_sha256, "handoff_receipt_sha256"),
        "consume_receipt_sha256": _canonical_digest(consume_receipt_sha256, "consume_receipt_sha256"),
        "operation_id": operation_id,
        "event_id": event_id,
        "created_at": created_at,
    }
    head["head_sha256"] = canonical_json_sha256(head)
    return head


def validate_result_recovery_head(
    value: object,
    *,
    expected_revision: int | None = None,
    expected_head_sha256: str | None = None,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("result_recovery_head_required")
    required = set(result_recovery_head_json_schema()["required"])
    if set(value) != required or value.get("schema") != "court.office.result_recovery_head.v1":
        raise ValueError("result_recovery_head_schema_mismatch")
    for field in ("recovery_id", "quarantine_id", "operation_id", "event_id", "created_at"):
        raw = value.get(field)
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("result_recovery_head_identity_required")
    if not isinstance(value.get("revision"), int) or isinstance(value["revision"], bool) or value["revision"] < 1:
        raise ValueError("result_recovery_head_revision_invalid")
    if value.get("state") not in {"REVIEW_PENDING", "READY_FOR_HANDOFF", "REJECTED", "HANDED_OFF", "CONSUMED"}:
        raise ValueError("result_recovery_head_state_invalid")
    for field in ("previous_head_sha256", "projection_sha256", "target_binding_sha256", "review_receipt_sha256", "handoff_receipt_sha256", "consume_receipt_sha256"):
        _canonical_digest(value.get(field), field)
    if canonical_json_sha256({key: item for key, item in value.items() if key != "head_sha256"}) != value.get("head_sha256"):
        raise ValueError("result_recovery_head_digest_mismatch")
    if expected_revision is not None and value["revision"] != expected_revision:
        raise ValueError("result_recovery_revision_conflict")
    if expected_head_sha256 is not None and value["head_sha256"] != expected_head_sha256:
        raise ValueError("result_recovery_head_conflict")
    return dict(value)


def result_recovery_target_binding_fields() -> tuple[str, ...]:
    return (
        "task_id", "semantic_epoch", "case_ref", "plan_ref",
        "checkpoint_id", "dispatch_uid", "attempt", "office_instance_id", "office_instance_kind",
        "carrier_proof", "agent_id", "role", "direct_superior", "worktree", "write_set",
        "hierarchy_schema", "hierarchy_gate", "hierarchy_edge_class", "preload_status",
        "office_execution_ready", "status", "final_status", "release_status", "result_state",
    )


def deterministic_result_recovery_event_id(operation_id: object, action: object, payload_sha256: object) -> str:
    return "EVT-RR-" + hashlib.sha256(
        f"{operation_id}|{action}|{payload_sha256}".encode("utf-8")
    ).hexdigest()[:24].upper()


def result_recovery_record_disposition(record: object) -> str:
    if not isinstance(record, dict):
        return "READ_ONLY_LEGACY"
    if record.get("schema") == "court.office.result_quarantine.v2":
        try:
            validate_result_quarantine_core(record)
        except ValueError:
            return "READ_ONLY_LEGACY"
        return "CURRENT_QUARANTINE_CORE"
    if record.get("schema") == "court.office.result_recovery_head.v1":
        try:
            validate_result_recovery_head(record)
        except ValueError:
            return "READ_ONLY_LEGACY"
        return "CURRENT_RECOVERY_HEAD"
    return "READ_ONLY_LEGACY"


def apply_result_recovery_operation(
    *,
    quarantine_core: Mapping[str, object],
    current_head: Mapping[str, object],
    operation_id: str,
    action: str,
    payload: Mapping[str, object],
    expected_revision: int,
    expected_head_sha256: str,
) -> dict[str, object]:
    current = validate_result_recovery_head(dict(current_head))
    payload_sha = canonical_json_sha256(dict(payload))
    event_id = deterministic_result_recovery_event_id(operation_id, action, payload_sha)
    if current.get("operation_id") == operation_id:
        if current.get("event_id") != event_id:
            raise ValueError("result_recovery_operation_conflict")
        if current.get("revision") != expected_revision + 1 or current.get("previous_head_sha256") != expected_head_sha256:
            raise ValueError("result_recovery_operation_conflict")
        for field in ("state", "projection_sha256", "target_binding_sha256", "review_receipt_sha256", "handoff_receipt_sha256", "consume_receipt_sha256", "created_at"):
            if current.get(field) != payload.get(field):
                raise ValueError("result_recovery_operation_conflict")
        return dict(current)
    if current.get("revision") != expected_revision:
        raise ValueError("result_recovery_revision_conflict")
    if current.get("head_sha256") != expected_head_sha256:
        raise ValueError("result_recovery_head_conflict")
    return build_result_recovery_head(
        quarantine_core=quarantine_core,
        recovery_id=str(current["recovery_id"]),
        previous_head=current,
        state=str(payload["state"]),
        projection_sha256=str(payload["projection_sha256"]),
        target_binding_sha256=str(payload["target_binding_sha256"]),
        review_receipt_sha256=str(payload["review_receipt_sha256"]),
        handoff_receipt_sha256=str(payload["handoff_receipt_sha256"]),
        consume_receipt_sha256=str(payload["consume_receipt_sha256"]),
        operation_id=operation_id,
        event_id=event_id,
        created_at=str(payload["created_at"]),
    )


def result_binding_problems(
    envelope: dict[str, object],
    binding: dict[str, object],
) -> list[str]:
    if "case_ref" not in envelope:
        return ["agent_result_binding_mismatch:case_ref"]
    from court_case_binding import case_reference

    binding_ref = binding.get("case_ref")
    if not isinstance(binding_ref, Mapping):
        binding_ref = {
            "court_code": binding.get("court_code"),
            "charter_revision": binding.get(
                "charter_revision", binding.get("semantic_epoch")
            ),
        }
    expected = {
        "case_ref": case_reference(binding_ref),
        "semantic_epoch": binding.get("semantic_epoch"),
        "checkpoint_id": binding.get("checkpoint_id"),
        "dispatch_uid": binding.get("dispatch_uid"),
        "attempt": binding.get("attempt"),
        "office_instance_id": binding.get("office_instance_id"),
        "agent_id": binding.get("agent_id"),
        "role": binding.get("role"),
        "direct_superior": binding.get("direct_superior"),
        "worktree": binding.get("worktree"),
        "write_set": binding.get("write_set", []),
    }
    problems = [
        f"agent_result_binding_mismatch:{field}"
        for field, expected_value in expected.items()
        if envelope.get(field) != expected_value
    ]
    if (
        binding.get("office_instance_kind") is not None
        and binding.get("carrier_proof") is not None
    ):
        for field in ("office_instance_kind", "carrier_proof"):
            expected_value = binding.get(field)
            if envelope.get(field) != expected_value:
                problems.append(f"agent_result_binding_mismatch:{field}")
    return problems


def result_quarantine_metadata(
    envelope: dict[str, object],
    reason_codes: list[str],
    *,
    received_at: str,
) -> dict[str, object]:
    return {
        "schema": "court.office.result_quarantine.v2",
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
    *,
    court_code: str | None = None,
) -> dict[str, object]:
    if not isinstance(charter, str) or not charter.strip():
        raise ValueError("charter_body_required")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("invalid_charter_revision")
    if court_code is None:
        raise ValueError("court_code_required")
    from court_case_binding import case_reference

    case_ref = case_reference(
        {"court_code": court_code, "charter_revision": revision}
    )
    template = normalize_invariant_capsule(charter, invariant_capsule)
    capsule = normalize_invariant_capsule(
        charter,
        {**template, "case_ref": case_ref},
        case_ref=case_ref,
    )
    return {
        "charter_revision": revision,
        "semantic_epoch": revision,
        "court_code": case_ref["court_code"],
        "invariant_capsule": capsule,
        "semantic_state": "UNVERIFIED",
        "semantic_receipt": {},
        "semantic_receipt_id": None,
        "semantic_receipts": [],
    }


def initial_semantic_binding(
    charter: object,
    invariant_capsule: object | None = None,
    *,
    court_code: str | None = None,
) -> dict[str, object]:
    return {
        **semantic_binding_for_revision(
            charter,
            1,
            invariant_capsule,
            court_code=court_code,
        ),
        "charter_revision_history": [],
    }
