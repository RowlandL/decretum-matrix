"""Pure native-host dispatch protocol with injected host and lifecycle adapters.

This module never imports or calls a model-reserved host API. The host owns the
actual spawn/followup callback and returns its opaque identifiers. The bridge
binds that result to the admitted request and delivers a single-use receipt to
the injected lifecycle consumer.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Mapping, MutableSet


HOST_DISPATCH_REQUEST_SCHEMA = "court.native_host_dispatch_request.v1"
HOST_ACTION_RECEIPT_SCHEMA = "court.native_host_action_receipt.v1"
ADMISSION_RECEIPT_SCHEMA = "court.agent.admission_receipt.v1"
REUSE_CONTEXT_LIMIT = 0.80
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
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
    "charter_sha256",
    "invariant_capsule_sha256",
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


def canonical_json_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str):
        raise ValueError(f"native_host_action_receipt:{field}_invalid")
    text = value.strip()
    if not text or len(text) > maximum or "\x00" in text:
        raise ValueError(f"native_host_action_receipt:{field}_invalid")
    return text


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, maximum=64).lower()
    if not SHA256_RE.fullmatch(text):
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
        "profile_sha256": _sha256(
            value.get("profile_sha256"), "role_ack.profile_sha256"
        ),
        "dossier_sha256": _sha256(
            value.get("dossier_sha256"), "role_ack.dossier_sha256"
        ),
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
        "receipt_sha256": _sha256(
            value.get("receipt_sha256"), "admission_anchor.receipt_sha256"
        ),
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
        "profile_sha256": _sha256(
            role_ack.get("profile_sha256"), "reuse.role_ack.profile_sha256"
        ),
        "dossier_sha256": _sha256(
            role_ack.get("dossier_sha256"), "reuse.role_ack.dossier_sha256"
        ),
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
            "charter_sha256": _sha256(
                semantic.get("charter_sha256"), "reuse.charter_sha256"
            ),
            "invariant_capsule_sha256": _sha256(
                semantic.get("invariant_capsule_sha256"),
                "reuse.invariant_capsule_sha256",
            ),
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
        "charter_sha256": _sha256(value.get("charter_sha256"), "charter_sha256"),
        "invariant_capsule_sha256": _sha256(
            value.get("invariant_capsule_sha256"), "invariant_capsule_sha256"
        ),
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
            "charter_sha256",
            "invariant_capsule_sha256",
        )
    )


def select_native_host_action(
    request: Mapping[str, object],
) -> tuple[str, str, dict[str, object] | None]:
    for candidate in request.get("compatible_live_instances", []):
        if isinstance(candidate, Mapping) and _candidate_is_compatible(candidate, request):
            return "reuse", "followup", dict(candidate)
    return "spawn", "spawn", None


def _normalize_host_result(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or not isinstance(value.get("ok"), bool):
        raise ValueError("native_host_action_receipt:host_result_invalid")
    result = deepcopy(dict(value))
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
        "request_sha256": canonical_json_sha256(request),
        "result_sha256": canonical_json_sha256(host_result),
        "acted_at": datetime.now(timezone.utc).isoformat(),
        "request": deepcopy(dict(request)),
        **{field: deepcopy(request[field]) for field in REQUEST_BINDING_FIELDS},
        **{field: host_result[field] for field in HOST_BINDING_FIELDS},
    }
    receipt["receipt_id"] = "native-host-" + canonical_json_sha256(receipt)[:24]
    receipt["receipt_sha256"] = canonical_json_sha256(receipt)
    return receipt


def _receipt_without_digest(value: Mapping[str, object]) -> dict[str, object]:
    result = deepcopy(dict(value))
    result.pop("receipt_sha256", None)
    return result


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
    for field in REQUEST_BINDING_FIELDS:
        if value.get(field) != request.get(field):
            raise ValueError(f"native_host_action_receipt:{field}_mismatch")
    for field in HOST_BINDING_FIELDS:
        _text(value.get(field), field)
    if value.get("request_sha256") != canonical_json_sha256(request):
        raise ValueError("native_host_action_receipt:request_sha256_mismatch")
    _sha256(value.get("result_sha256"), "result_sha256")
    acted_at = _text(value.get("acted_at"), "acted_at", maximum=64)
    try:
        parsed = datetime.fromisoformat(acted_at)
    except ValueError as exc:
        raise ValueError("native_host_action_receipt:acted_at_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("native_host_action_receipt:acted_at_invalid")
    receipt_id = _text(value.get("receipt_id"), "receipt_id", maximum=64)
    if not receipt_id.startswith("native-host-"):
        raise ValueError("native_host_action_receipt:receipt_id_invalid")
    receipt_sha256 = _sha256(value.get("receipt_sha256"), "receipt_sha256")
    if receipt_sha256 != canonical_json_sha256(_receipt_without_digest(value)):
        raise ValueError("native_host_action_receipt:receipt_sha256_mismatch")
    if receipt_id != "native-host-" + canonical_json_sha256(
        {k: v for k, v in _receipt_without_digest(value).items() if k != "receipt_id"}
    )[:24]:
        raise ValueError("native_host_action_receipt:receipt_id_mismatch")
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
