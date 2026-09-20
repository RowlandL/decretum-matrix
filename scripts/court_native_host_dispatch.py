"""Pure native-host dispatch protocol with injected host and lifecycle adapters.

This module never imports or calls a model-reserved host API. The host owns the
actual spawn/followup callback and returns its opaque identifiers. The bridge
binds that result to the admitted request and delivers a single-use receipt to
the injected lifecycle consumer.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Mapping, MutableSet

import sys

sys.dont_write_bytecode = True

from court_case_binding import case_reference


HOST_DISPATCH_REQUEST_SCHEMA = "court.native_host_dispatch_request.v1"
HOST_ACTION_RECEIPT_SCHEMA = "court.native_host_action_receipt.v1"
HOST_MODEL_EXECUTION_BINDING_SCHEMA = "court.host_model_execution_binding.v1"
ADMISSION_RECEIPT_SCHEMA = "court.agent.admission_receipt.v1"
REUSE_CONTEXT_LIMIT = 0.80
THREE_DEPARTMENTS = frozenset({"zhongshu", "menxia", "shangshu"})
SIX_MINISTRIES = frozenset(
    {"libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"}
)
REQUEST_BINDING_FIELDS = (
    "task_id",
    "wave_id",
    "dispatch_uid",
    "attempt",
    "role",
    "instance_id",
    "direct_superior",
    "semantic_epoch",
    "case_ref",
    "office_capsule_ref",
    "lease_id",
    "assignment",
    "duty_scope",
    "write_set",
    "role_ack",
    "admission_anchor",
)
HOST_BINDING_FIELDS = (
    "host_task_id",
    "host_thread_id",
    "host_instance_id",
    "host_action_id",
)
CANONICAL_AGENT_PATH_IDENTITY_KIND = "canonical_agent_path"
CANONICAL_IDENTITY_RECEIPT_FIELDS = (
    "host_identity_kind",
    "trace_issuer_thread_id",
    "trace_reader_thread_id",
    "trace_session_id",
    "case_session_id",
    "trusted_parent_kind",
)
OBSERVED_CAPABILITY_FIELDS = (
    "observed_spawn_agent_type_field",
    "observed_child_agent_role",
)
CANONICAL_AGENT_PATH_RE = re.compile(r"^/root(?:/[a-z0-9_]+)+$")
SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def native_request_reference(request: Mapping[str, object]) -> dict[str, object]:
    """Identify a dispatch by its issued case and existing office/attempt."""
    return {
        "court_code": case_reference(request["case_ref"])["court_code"],
        "office_instance_id": request["instance_id"],
        "dispatch_uid": request["dispatch_uid"],
        "attempt": request["attempt"],
    }


def native_task_suffix(request: Mapping[str, object]) -> str:
    """Keep the existing 16-character host naming suffix using the dispatch ID."""
    dispatch_uid = str(request["dispatch_uid"]).removeprefix("DSP-").replace("-", "")
    attempt = _positive_int(request["attempt"], "attempt")
    if not re.fullmatch(r"[0-9a-f]{32}", dispatch_uid) or attempt > 65535:
        raise ValueError("native_host_action_receipt:dispatch_identity_invalid")
    return f"{dispatch_uid[-12:]}{attempt:04x}"


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str):
        raise ValueError(f"native_host_action_receipt:{field}_invalid")
    text = value.strip()
    if not text or len(text) > maximum or "\x00" in text:
        raise ValueError(f"native_host_action_receipt:{field}_invalid")
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"native_host_action_receipt:{field}_invalid")
    return value


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"native_host_action_receipt:{field}_invalid")
    result = [_text(item, field, maximum=1024) for item in value]
    if len(result) != len(set(result)):
        raise ValueError(f"native_host_action_receipt:{field}_duplicate")
    return result


def _normalize_role_ack(
    value: object,
    *,
    role: str,
    direct_superior: str,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("native_host_action_receipt:role_ack_invalid")
    normalized = {
        "role": _text(value.get("role"), "role_ack.role", maximum=64).lower(),
        "direct_superior": _text(
            value.get("direct_superior"),
            "role_ack.direct_superior",
            maximum=64,
        ).lower(),
        **{field: _text(value.get(field), f"role_ack.{field}")
           for field in (
               "profile_source",
               "dossier_path",
               "court_skill_path",
               "startup_guide_path",
           )},
    }
    if normalized["role"] != role or normalized["direct_superior"] != direct_superior:
        raise ValueError("native_host_action_receipt:role_ack_binding_mismatch")
    return normalized


def _normalize_admission_anchor(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or value.get("schema") != ADMISSION_RECEIPT_SCHEMA:
        raise ValueError("native_host_action_receipt:admission_anchor_invalid")
    return {
        "schema": ADMISSION_RECEIPT_SCHEMA,
        "receipt_id": _text(value.get("receipt_id"), "admission_anchor.receipt_id"),
    }


def _expected_superior(role: str) -> str | None:
    if role in THREE_DEPARTMENTS:
        return "taizi"
    if role in SIX_MINISTRIES:
        return "shangshu"
    return None


def _normalize_candidate(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("native_host_action_receipt:reuse_candidate_invalid")
    ratio = value.get("context_utilization")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
        raise ValueError("native_host_action_receipt:reuse_context_invalid")
    semantic = value.get("semantic_receipt")
    if not isinstance(semantic, Mapping):
        raise ValueError("native_host_action_receipt:reuse_semantic_invalid")
    role = _text(value.get("role"), "reuse.role", maximum=64).lower()
    superior = _text(
        value.get("direct_superior"), "reuse.direct_superior", maximum=64
    ).lower()
    role_ack = value.get("role_ack")
    if not isinstance(role_ack, Mapping):
        raise ValueError("native_host_action_receipt:reuse_role_ack_invalid")
    normalized_role_ack = {
        "role": _text(role_ack.get("role"), "reuse.role_ack.role", maximum=64).lower(),
        "direct_superior": _text(
            role_ack.get("direct_superior"),
            "reuse.role_ack.direct_superior",
            maximum=64,
        ).lower(),
        **{field: _text(role_ack.get(field), f"reuse.role_ack.{field}")
           for field in (
               "profile_source",
               "dossier_path",
               "court_skill_path",
               "startup_guide_path",
           )},
    }
    return {
        "host_task_id": _text(value.get("host_task_id"), "reuse.host_task_id"),
        "host_thread_id": _text(value.get("host_thread_id"), "reuse.host_thread_id"),
        "host_instance_id": _text(
            value.get("host_instance_id"), "reuse.host_instance_id"
        ),
        "task_id": _text(value.get("task_id"), "reuse.task_id"),
        "role": role,
        "direct_superior": superior,
        "assignment": _text(value.get("assignment"), "reuse.assignment"),
        "duty_scope": _string_list(value.get("duty_scope"), "reuse.duty_scope"),
        "semantic_receipt": {
            "semantic_epoch": _positive_int(
                semantic.get("semantic_epoch"), "reuse.semantic_epoch"
            ),
            "case_ref": case_reference(semantic.get("case_ref", {})),
        },
        "lease_id": _text(value.get("lease_id"), "reuse.lease_id"),
        "write_set": _string_list(value.get("write_set"), "reuse.write_set"),
        "role_ack": normalized_role_ack,
        "context_utilization": float(ratio),
        "status": _text(value.get("status"), "reuse.status", maximum=32).lower(),
    }


def normalize_native_host_dispatch_request(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or value.get("schema") != HOST_DISPATCH_REQUEST_SCHEMA:
        raise ValueError("native_host_action_receipt:request_schema_invalid")
    role = _text(value.get("role"), "role", maximum=64).lower()
    direct_superior = _text(
        value.get("direct_superior"), "direct_superior", maximum=64
    ).lower()
    expected_superior = _expected_superior(role)
    if expected_superior is not None and direct_superior != expected_superior:
        raise ValueError("native_host_action_receipt:direct_superior_mismatch")
    raw_candidates = value.get("compatible_live_instances", [])
    if not isinstance(raw_candidates, (list, tuple)):
        raise ValueError("native_host_action_receipt:reuse_candidates_invalid")
    normalized = {
        "schema": HOST_DISPATCH_REQUEST_SCHEMA,
        "task_id": _text(value.get("task_id"), "task_id"),
        "wave_id": _text(value.get("wave_id"), "wave_id"),
        "dispatch_uid": _text(value.get("dispatch_uid"), "dispatch_uid"),
        "attempt": _positive_int(value.get("attempt"), "attempt"),
        "role": role,
        "instance_id": _text(value.get("instance_id"), "instance_id").lower(),
        "direct_superior": direct_superior,
        "semantic_epoch": _positive_int(value.get("semantic_epoch"), "semantic_epoch"),
        "case_ref": case_reference(value.get("case_ref", {})),
        "office_capsule_ref": deepcopy(value.get("office_capsule_ref")),
        "lease_id": _text(value.get("lease_id"), "lease_id"),
        "assignment": _text(value.get("assignment"), "assignment"),
        "duty_scope": _string_list(value.get("duty_scope"), "duty_scope"),
        "write_set": _string_list(value.get("write_set"), "write_set"),
        "role_ack": _normalize_role_ack(
            value.get("role_ack"), role=role, direct_superior=direct_superior
        ),
        "admission_anchor": _normalize_admission_anchor(value.get("admission_anchor")),
        "compatible_live_instances": [
            _normalize_candidate(candidate) for candidate in raw_candidates
        ],
    }
    capsule = normalized["office_capsule_ref"]
    if normalized["case_ref"]["charter_revision"] != normalized["semantic_epoch"]:
        raise ValueError("native_host_action_receipt:case_revision_mismatch")
    if (not isinstance(capsule, Mapping)
            or capsule.get("case_ref") != normalized["case_ref"]
            or capsule.get("office_instance_id") != normalized["instance_id"]
            or capsule.get("role_key") != role):
        raise ValueError("native_host_action_receipt:office_capsule_binding_mismatch")
    from court_case_binding import office_capsule_reference
    expected_capsule = office_capsule_reference(
        normalized["case_ref"], role, normalized["instance_id"], capsule.get("issued_at")
    )
    if dict(capsule) != expected_capsule:
        raise ValueError("native_host_action_receipt:office_capsule_binding_mismatch")
    return normalized


def _candidate_is_compatible(
    candidate: Mapping[str, object],
    request: Mapping[str, object],
) -> bool:
    if candidate.get("status") not in {"idle", "running", "active", "waiting"}:
        return False
    if float(candidate.get("context_utilization", 1.0)) >= REUSE_CONTEXT_LIMIT:
        return False
    exact_fields = (
        "task_id",
        "role",
        "direct_superior",
        "assignment",
        "duty_scope",
        "lease_id",
        "write_set",
        "role_ack",
    )
    if any(candidate.get(field) != request.get(field) for field in exact_fields):
        return False
    semantic = candidate.get("semantic_receipt")
    if not isinstance(semantic, Mapping):
        return False
    return all(
        semantic.get(field) == request.get(field)
        for field in (
            "semantic_epoch",
            "case_ref",
        )
    )


def select_native_host_action(
    request: Mapping[str, object],
) -> tuple[str, str, dict[str, object] | None]:
    for candidate in request.get("compatible_live_instances", []):
        if isinstance(candidate, Mapping) and _candidate_is_compatible(candidate, request):
            return "reuse", "followup", dict(candidate)
    return "spawn", "spawn", None


def _normalize_observed_capability(
    value: Mapping[str, object],
    *,
    field_prefix: str,
) -> dict[str, object] | None:
    present = tuple(field in value for field in OBSERVED_CAPABILITY_FIELDS)
    if not any(present):
        return None
    if not all(present):
        raise ValueError(
            f"native_host_action_receipt:{field_prefix}_observed_capability_incomplete"
        )
    capability = value.get("observed_spawn_agent_type_field")
    observed_role = value.get("observed_child_agent_role")
    if capability not in {"visible", "hidden", "unverified"}:
        raise ValueError(
            f"native_host_action_receipt:{field_prefix}_observed_capability_invalid"
        )
    if capability == "visible":
        observed_role = _text(
            observed_role,
            f"{field_prefix}.observed_child_agent_role",
            maximum=64,
        ).lower()
    elif observed_role is not None:
        raise ValueError(
            f"native_host_action_receipt:{field_prefix}_unproved_role_must_be_null"
        )
    return {
        "observed_spawn_agent_type_field": capability,
        "observed_child_agent_role": observed_role,
    }


def _normalize_model_turn_context(
    value: object,
    *,
    field_prefix: str,
) -> dict[str, object]:
    required = {"model", "effort", "trace_line", "turn_id"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError(
            f"native_host_action_receipt:{field_prefix}_invalid"
        )
    return {
        "model": _text(value.get("model"), f"{field_prefix}.model"),
        "effort": _text(value.get("effort"), f"{field_prefix}.effort"),
        "trace_line": _positive_int(
            value.get("trace_line"), f"{field_prefix}.trace_line"
        ),
        "turn_id": _text(
            value.get("turn_id"), f"{field_prefix}.turn_id", maximum=512
        ),
    }


def _normalize_host_model_execution_binding(value: object) -> dict[str, object]:
    required = {
        "schema",
        "selection_id",
        "applied_spawn_fields",
        "parent_turn_context",
        "child_turn_context",
        "status",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError(
            "native_host_action_receipt:host_model_execution_binding_invalid"
        )
    if value.get("schema") != HOST_MODEL_EXECUTION_BINDING_SCHEMA:
        raise ValueError(
            "native_host_action_receipt:host_model_execution_binding_schema_invalid"
        )
    selection_id = value.get("selection_id")
    if not isinstance(selection_id, str) or re.fullmatch(
        r"MEA-[0-9a-f]{32}", selection_id
    ) is None:
        raise ValueError(
            "native_host_action_receipt:host_model_execution_selection_id_invalid"
        )
    applied = value.get("applied_spawn_fields")
    allowed_order = ("model", "reasoning_effort")
    if (
        not isinstance(applied, (list, tuple))
        or not applied
        or list(applied)
        != [field for field in allowed_order if field in applied]
    ):
        raise ValueError(
            "native_host_action_receipt:host_model_execution_fields_invalid"
        )
    if value.get("status") != "MATCHED":
        raise ValueError(
            "native_host_action_receipt:host_model_execution_status_invalid"
        )
    return {
        "schema": HOST_MODEL_EXECUTION_BINDING_SCHEMA,
        "selection_id": selection_id,
        "applied_spawn_fields": list(applied),
        "parent_turn_context": _normalize_model_turn_context(
            value.get("parent_turn_context"),
            field_prefix="parent_turn_context",
        ),
        "child_turn_context": _normalize_model_turn_context(
            value.get("child_turn_context"),
            field_prefix="child_turn_context",
        ),
        "status": "MATCHED",
    }


def _normalize_model_authorization_binding(
    value: object,
    *,
    request: Mapping[str, object],
) -> dict[str, object]:
    from court_model_router import validate_current_codex_model_selection

    try:
        return validate_current_codex_model_selection(
            value,
            expected_case_ref=request["case_ref"],
            expected_semantic_epoch=request["semantic_epoch"],
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(
            "native_host_action_receipt:model_authorization_binding_invalid"
        ) from exc


def _validate_model_execution_authorization(
    authorization: Mapping[str, object],
    execution: Mapping[str, object],
) -> None:
    from court_model_router import validate_explicit_model_execution_binding

    case_ref = authorization.get("case_ref")
    if not isinstance(case_ref, Mapping):
        raise ValueError(
            "native_host_action_receipt:model_execution_authorization_mismatch"
        )
    try:
        validate_explicit_model_execution_binding(
            authorization,
            execution,
            expected_case_ref=case_ref,
            expected_semantic_epoch=authorization.get("semantic_epoch"),
        )
    except ValueError as exc:
        raise ValueError(
            "native_host_action_receipt:model_execution_authorization_mismatch"
        ) from exc


def _normalize_host_result(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or not isinstance(value.get("ok"), bool):
        raise ValueError("native_host_action_receipt:host_result_invalid")
    result = deepcopy(dict(value))
    observed = _normalize_observed_capability(result, field_prefix="host_result")
    if observed is not None:
        result.update(observed)
    if "host_model_execution_binding" in result:
        result["host_model_execution_binding"] = (
            _normalize_host_model_execution_binding(
                result["host_model_execution_binding"]
            )
        )
    if 'host_spawn_evidence' in result:
        from court_native_trace import validate_spawn_evidence
        result['host_spawn_evidence'] = validate_spawn_evidence(result['host_spawn_evidence'], result)
    if result.get("host_identity_kind") is not None:
        if result.get("ok") is not True:
            raise ValueError("native_host_action_receipt:canonical_identity_requires_success")
        return _normalize_canonical_agent_path_result(result)
    for field in HOST_BINDING_FIELDS:
        result[field] = _text(result.get(field), field)
    if result["ok"] is False:
        result["error_code"] = _text(
            result.get("error_code") or "unknown", "error_code", maximum=128
        )
        result["reason"] = _text(
            result.get("reason") or "host refused delivery", "reason", maximum=2048
        )
    return result


def _canonical_agent_path(value: object, field: str) -> str:
    path = _text(value, field)
    if CANONICAL_AGENT_PATH_RE.fullmatch(path) is None:
        raise ValueError(f"native_host_action_receipt:{field}_invalid")
    return path


def _canonical_session_id(value: object, field: str) -> str:
    session_id = _text(value, field, maximum=64).lower()
    if SESSION_ID_RE.fullmatch(session_id) is None:
        raise ValueError(f"native_host_action_receipt:{field}_invalid")
    return session_id


def _normalize_canonical_agent_path_result(value: Mapping[str, object]) -> dict[str, object]:
    if value.get("host_identity_kind") != CANONICAL_AGENT_PATH_IDENTITY_KIND:
        raise ValueError("native_host_action_receipt:host_identity_kind_invalid")
    host_task_id = _canonical_agent_path(value.get("host_task_id"), "host_task_id")
    host_instance_id = _canonical_agent_path(
        value.get("host_instance_id"), "host_instance_id"
    )
    if host_task_id != host_instance_id:
        raise ValueError("native_host_action_receipt:canonical_identity_path_mismatch")
    if value.get("host_thread_id") is not None:
        raise ValueError("native_host_action_receipt:canonical_identity_thread_must_be_null")
    if value.get("trace_issuer_thread_id") is not None:
        raise ValueError("native_host_action_receipt:canonical_identity_issuer_must_be_null")
    parent_kind = _text(value.get("trusted_parent_kind"), "trusted_parent_kind", maximum=64)
    if parent_kind not in {"taizi_root", "same_case_ready_shangshu"}:
        raise ValueError("native_host_action_receipt:trusted_parent_kind_invalid")
    return {
        **deepcopy(dict(value)),
        "host_identity_kind": CANONICAL_AGENT_PATH_IDENTITY_KIND,
        "host_task_id": host_task_id,
        "host_instance_id": host_instance_id,
        "host_thread_id": None,
        "trace_issuer_thread_id": None,
        "trace_reader_thread_id": _text(
            value.get("trace_reader_thread_id"), "trace_reader_thread_id"
        ),
        "trace_session_id": _canonical_session_id(
            value.get("trace_session_id"), "trace_session_id"
        ),
        "case_session_id": _canonical_session_id(
            value.get("case_session_id"), "case_session_id"
        ),
        "trusted_parent_kind": parent_kind,
        "host_action_id": _text(value.get("host_action_id"), "host_action_id"),
    }


def _build_receipt(
    request: Mapping[str, object],
    host_result: Mapping[str, object],
    *,
    decision: str,
    host_action: str,
) -> dict[str, object]:
    outcome = "succeeded" if host_result.get("ok") is True else "refused"
    receipt: dict[str, object] = {
        "schema": HOST_ACTION_RECEIPT_SCHEMA,
        "decision": decision,
        "host_action": host_action,
        "outcome": outcome,
        "request_ref": native_request_reference(request),
        "host_result": deepcopy(dict(host_result)),
        "acted_at": datetime.now(timezone.utc).isoformat(),
        "request": deepcopy(dict(request)),
        **{field: deepcopy(request[field]) for field in REQUEST_BINDING_FIELDS},
        **{field: host_result[field] for field in HOST_BINDING_FIELDS},
    }
    observed = _normalize_observed_capability(
        host_result,
        field_prefix="host_result",
    )
    if observed is not None:
        if host_action != "spawn" or outcome != "succeeded":
            raise ValueError(
                "native_host_action_receipt:observed_capability_action_mismatch"
            )
        if (
            observed["observed_spawn_agent_type_field"] == "visible"
            and observed["observed_child_agent_role"] != request.get("role")
        ):
            raise ValueError(
                "native_host_action_receipt:observed_child_agent_role_mismatch"
            )
        receipt.update(observed)
    if host_result.get("host_identity_kind") == CANONICAL_AGENT_PATH_IDENTITY_KIND:
        receipt.update(
            {
                field: deepcopy(host_result[field])
                for field in CANONICAL_IDENTITY_RECEIPT_FIELDS
            }
        )
    if 'host_spawn_evidence' in host_result:
        if host_action != 'spawn' or outcome != 'succeeded':
            raise ValueError('native_host_action_receipt:spawn_evidence_action_mismatch')
        receipt['host_spawn_evidence'] = deepcopy(host_result['host_spawn_evidence'])
    if "model_authorization_binding" in host_result:
        if host_action != "spawn" or outcome != "succeeded":
            raise ValueError(
                "native_host_action_receipt:model_authorization_binding_action_mismatch"
            )
        receipt["model_authorization_binding"] = deepcopy(
            host_result["model_authorization_binding"]
        )
    if "host_model_execution_binding" in host_result:
        if host_action != "spawn" or outcome != "succeeded":
            raise ValueError(
                "native_host_action_receipt:model_execution_binding_action_mismatch"
            )
        receipt["host_model_execution_binding"] = deepcopy(
            host_result["host_model_execution_binding"]
        )
    receipt["receipt_id"] = "native-host-" + str(host_result["host_action_id"])
    return receipt


def validate_native_host_action_receipt(
    value: object,
    *,
    expected: object,
    replay_guard: MutableSet[str],
) -> dict[str, object]:
    if not isinstance(value, Mapping) or value.get("schema") != HOST_ACTION_RECEIPT_SCHEMA:
        raise ValueError("native_host_action_receipt:schema_invalid")
    if not isinstance(replay_guard, MutableSet):
        raise TypeError("native_host_action_receipt:replay_guard_invalid")
    request = normalize_native_host_dispatch_request(expected)
    embedded = value.get("request")
    if embedded is not None and normalize_native_host_dispatch_request(embedded) != request:
        raise ValueError("native_host_action_receipt:embedded_request_mismatch")
    decision, host_action, _ = select_native_host_action(request)
    outcome = _text(value.get("outcome"), "outcome", maximum=32).lower()
    if outcome not in {"succeeded", "refused"}:
        raise ValueError("native_host_action_receipt:outcome_invalid")
    if value.get("decision") != decision or value.get("host_action") != host_action:
        raise ValueError("native_host_action_receipt:action_binding_mismatch")
    host_result = _normalize_host_result(value.get("host_result"))
    if (any(value.get(field) != host_result.get(field) for field in HOST_BINDING_FIELDS)
            or any(value.get(field) != host_result.get(field)
                   for field in (*CANONICAL_IDENTITY_RECEIPT_FIELDS, "host_spawn_evidence"))
            or (outcome == "succeeded") != host_result["ok"]):
        raise ValueError("native_host_action_receipt:host_result_binding_mismatch")
    receipt_observed = _normalize_observed_capability(
        value,
        field_prefix="receipt",
    )
    host_observed = _normalize_observed_capability(
        host_result,
        field_prefix="host_result",
    )
    if receipt_observed != host_observed:
        raise ValueError(
            "native_host_action_receipt:observed_capability_binding_mismatch"
        )
    if host_observed is not None:
        if host_action != "spawn" or outcome != "succeeded":
            raise ValueError(
                "native_host_action_receipt:observed_capability_action_mismatch"
            )
        if (
            host_observed["observed_spawn_agent_type_field"] == "visible"
            and host_observed["observed_child_agent_role"] != request.get("role")
        ):
            raise ValueError(
                "native_host_action_receipt:observed_child_agent_role_mismatch"
            )
    receipt_has_authorization = "model_authorization_binding" in value
    host_has_authorization = "model_authorization_binding" in host_result
    if receipt_has_authorization != host_has_authorization:
        raise ValueError(
            "native_host_action_receipt:model_authorization_binding_incomplete"
        )
    model_authorization: dict[str, object] | None = None
    if host_has_authorization:
        receipt_authorization = _normalize_model_authorization_binding(
            value.get("model_authorization_binding"),
            request=request,
        )
        host_authorization = _normalize_model_authorization_binding(
            host_result.get("model_authorization_binding"),
            request=request,
        )
        if receipt_authorization != host_authorization:
            raise ValueError(
                "native_host_action_receipt:model_authorization_binding_mismatch"
            )
        if host_action != "spawn" or outcome != "succeeded":
            raise ValueError(
                "native_host_action_receipt:model_authorization_binding_action_mismatch"
            )
        model_authorization = receipt_authorization
    receipt_has_model_binding = "host_model_execution_binding" in value
    host_has_model_binding = "host_model_execution_binding" in host_result
    if receipt_has_model_binding != host_has_model_binding:
        raise ValueError(
            "native_host_action_receipt:model_execution_binding_incomplete"
        )
    if host_has_model_binding:
        receipt_model_binding = _normalize_host_model_execution_binding(
            value.get("host_model_execution_binding")
        )
        if (
            receipt_model_binding
            != host_result.get("host_model_execution_binding")
        ):
            raise ValueError(
                "native_host_action_receipt:model_execution_binding_mismatch"
            )
        if host_action != "spawn" or outcome != "succeeded":
            raise ValueError(
                "native_host_action_receipt:model_execution_binding_action_mismatch"
            )
        if model_authorization is None:
            raise ValueError(
                "native_host_action_receipt:model_authorization_binding_required"
            )
        _validate_model_execution_authorization(
            model_authorization,
            receipt_model_binding,
        )
    elif model_authorization is not None:
        raise ValueError(
            "native_host_action_receipt:model_execution_binding_required"
        )
    for field in REQUEST_BINDING_FIELDS:
        if value.get(field) != request.get(field):
            raise ValueError(f"native_host_action_receipt:{field}_mismatch")
    if value.get("host_identity_kind") is None:
        if any(field in value for field in CANONICAL_IDENTITY_RECEIPT_FIELDS[1:]):
            raise ValueError("native_host_action_receipt:legacy_identity_metadata_unexpected")
        for field in HOST_BINDING_FIELDS:
            _text(value.get(field), field)
    else:
        _normalize_canonical_agent_path_result(value)
    if value.get("request_ref") != native_request_reference(request):
        raise ValueError("native_host_action_receipt:request_ref_mismatch")
    if 'host_spawn_evidence' in value:
        from court_native_trace import validate_spawn_evidence
        if host_action != 'spawn' or outcome != 'succeeded':
            raise ValueError('native_host_action_receipt:spawn_evidence_action_mismatch')
        validate_spawn_evidence(value['host_spawn_evidence'], value)
    acted_at = _text(value.get("acted_at"), "acted_at", maximum=64)
    try:
        parsed = datetime.fromisoformat(acted_at)
    except ValueError as exc:
        raise ValueError("native_host_action_receipt:acted_at_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("native_host_action_receipt:acted_at_invalid")
    receipt_id = _text(value.get("receipt_id"), "receipt_id")
    if receipt_id != "native-host-" + str(value.get("host_action_id")):
        raise ValueError("native_host_action_receipt:receipt_id_invalid")
    if receipt_id in replay_guard:
        raise ValueError("native_host_action_receipt:replay")
    replay_guard.add(receipt_id)
    return deepcopy(dict(value))


def dispatch_native_host_action(
    value: object,
    *,
    host: object,
    lifecycle: object,
) -> dict[str, object]:
    request = normalize_native_host_dispatch_request(value)
    decision, host_action, candidate = select_native_host_action(request)
    if host_action == "spawn":
        callback = getattr(host, "spawn", None)
        if not callable(callback):
            raise TypeError("native_host_action_receipt:host_spawn_unavailable")
        host_result = _normalize_host_result(callback(deepcopy(request)))
    else:
        callback = getattr(host, "followup", None)
        if not callable(callback) or candidate is None:
            raise TypeError("native_host_action_receipt:host_followup_unavailable")
        host_result = _normalize_host_result(
            callback(str(candidate["host_instance_id"]), deepcopy(request))
        )
        if host_result.get("host_identity_kind") == CANONICAL_AGENT_PATH_IDENTITY_KIND:
            raise ValueError("native_host_action_receipt:canonical_followup_issuer_unavailable")
        if host_result["host_instance_id"] != candidate["host_instance_id"]:
            raise ValueError("native_host_action_receipt:reuse_host_identity_mismatch")
        for field in ("host_task_id", "host_thread_id"):
            if host_result[field] != candidate[field]:
                raise ValueError("native_host_action_receipt:reuse_host_identity_mismatch")

    receipt = _build_receipt(
        request,
        host_result,
        decision=decision,
        host_action=host_action,
    )
    validate_native_host_action_receipt(receipt, expected=request, replay_guard=set())

    if host_result["ok"] is False:
        consumer = getattr(lifecycle, "spawn_failed", None)
        if not callable(consumer):
            raise TypeError("native_host_action_receipt:spawn_failed_consumer_unavailable")
        lifecycle_result = consumer(
            deepcopy(request),
            {**deepcopy(host_result), "native_host_action_receipt": deepcopy(receipt)},
        )
    else:
        consumer_name = "start" if host_action == "spawn" else "followup"
        consumer = getattr(lifecycle, consumer_name, None)
        if not callable(consumer):
            raise TypeError(
                f"native_host_action_receipt:{consumer_name}_consumer_unavailable"
            )
        try:
            lifecycle_result = consumer(deepcopy(receipt))
        except Exception as exc:
            quarantine = getattr(lifecycle, "quarantine", None)
            reconcile = getattr(lifecycle, "reconcile", None)
            if callable(quarantine):
                quarantine(deepcopy(receipt), exc)
            if callable(reconcile):
                reconcile(deepcopy(receipt), exc)
            raise

    return {
        "schema": "court.native_host_dispatch.v1",
        "ok": host_result["ok"] is True,
        "decision": decision,
        "host_action": host_action,
        "outcome": receipt["outcome"],
        "host_action_receipt": receipt,
        "lifecycle_result": lifecycle_result,
    }
