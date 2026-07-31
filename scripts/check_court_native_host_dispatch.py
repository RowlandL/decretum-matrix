"""Verify native parallel execution is bound to real host actions and receipts."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any
import uuid

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from court_native_execution import select_native_execution


BRIDGE_PATH = SCRIPTS / "court_native_host_dispatch.py"
HOST_RECEIPT_SCHEMA = "court.native_host_action_receipt.v1"
BRIDGE_MODULE = "court_native_host_dispatch"
REQUIRED_BRIDGE_SYMBOLS = (
    "HOST_ACTION_RECEIPT_SCHEMA",
    "dispatch_native_host_action",
    "validate_native_host_action_receipt",
)
MINISTRY_ROLES = ("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu")
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


def load_bridge() -> tuple[object | None, list[str]]:
    try:
        bridge = importlib.import_module(BRIDGE_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name == BRIDGE_MODULE:
            return None, ["native_host_dispatch_bridge_missing"]
        raise
    missing = [name for name in REQUIRED_BRIDGE_SYMBOLS if not hasattr(bridge, name)]
    return bridge, [f"native_host_dispatch_symbol_missing:{name}" for name in missing]


def _request(*, role: str = "gongbu", suffix: str = "01") -> dict[str, object]:
    return {
        "schema": "court.native_host_dispatch_request.v1",
        "task_id": f"task-native-host-{suffix}",
        "wave_id": f"wave-{suffix}",
        "dispatch_uid": f"dispatch-{suffix}",
        "attempt": 1,
        "role": role,
        "instance_id": f"{role}-{suffix}",
        "direct_superior": "shangshu",
        "semantic_epoch": 7,
        "charter_sha256": "c" * 64,
        "invariant_capsule_sha256": "e" * 64,
        "lease_id": f"lease-{suffix}",
        "assignment": "implement bounded native host dispatch",
        "duty_scope": ["scripts/court_native_host_dispatch.py"],
        "write_set": ["scripts/court_native_host_dispatch.py"],
        "role_ack": {
            "role": role,
            "direct_superior": "shangshu",
            "profile_sha256": "b" * 64,
            "dossier_sha256": "d" * 64,
        },
        "admission_anchor": {
            "schema": "court.agent.admission_receipt.v1",
            "receipt_id": f"admit-{suffix}",
            "receipt_sha256": "a" * 64,
        },
        "compatible_live_instances": [],
    }


def _compatible_candidate(
    request: dict[str, object],
    *,
    context_utilization: float = 0.42,
    assignment: str | None = None,
) -> dict[str, object]:
    token = uuid.uuid4().hex
    return {
        "host_task_id": f"host-task-reuse-{token}",
        "host_thread_id": f"host-thread-reuse-{token}",
        "host_instance_id": f"host-instance-reuse-{token}",
        "task_id": request["task_id"],
        "role": request["role"],
        "direct_superior": request["direct_superior"],
        "assignment": assignment or request["assignment"],
        "duty_scope": deepcopy(request["duty_scope"]),
        "semantic_receipt": {
            "semantic_epoch": request["semantic_epoch"],
            "charter_sha256": request["charter_sha256"],
            "invariant_capsule_sha256": request["invariant_capsule_sha256"],
        },
        "lease_id": request["lease_id"],
        "write_set": deepcopy(request["write_set"]),
        "role_ack": deepcopy(request["role_ack"]),
        "context_utilization": context_utilization,
        "status": "idle",
    }


class _RecordingHost:
    def __init__(
        self,
        *,
        suffix: str,
        spawn_response: dict[str, object] | None = None,
        followup_response: dict[str, object] | None = None,
    ) -> None:
        self.spawn_requests: list[dict[str, object]] = []
        self.followup_requests: list[tuple[str, dict[str, object]]] = []
        token = uuid.uuid4().hex
        self.spawn_response = spawn_response or {
            "ok": True,
            "host_task_id": f"host-task-{suffix}-{token}",
            "host_thread_id": f"host-thread-{suffix}-{token}",
            "host_instance_id": f"host-instance-{suffix}-{token}",
            "host_action_id": f"host-action-{suffix}-{token}",
        }
        self.followup_response = followup_response

    def spawn(self, request: dict[str, object]) -> dict[str, object]:
        self.spawn_requests.append(deepcopy(request))
        return deepcopy(self.spawn_response)

    def followup(
        self,
        host_instance_id: str,
        request: dict[str, object],
    ) -> dict[str, object]:
        self.followup_requests.append((host_instance_id, deepcopy(request)))
        token = uuid.uuid4().hex
        response = self.followup_response or {
            "ok": True,
            "host_task_id": f"host-task-reuse-{token}",
            "host_thread_id": f"host-thread-reuse-{token}",
            "host_instance_id": host_instance_id,
            "host_action_id": f"host-action-followup-{token}",
        }
        return deepcopy(response)


class _RecordingLifecycle:
    def __init__(self, *, fail_start: bool = False) -> None:
        self.fail_start = fail_start
        self.started: list[dict[str, object]] = []
        self.followed_up: list[dict[str, object]] = []
        self.spawn_failures: list[tuple[dict[str, object], dict[str, object]]] = []
        self.quarantines: list[tuple[dict[str, object], str]] = []
        self.reconciliations: list[tuple[dict[str, object], str]] = []

    def start(self, receipt: dict[str, object]) -> dict[str, object]:
        self.started.append(deepcopy(receipt))
        if self.fail_start:
            raise RuntimeError("fixture_lifecycle_commit_failed")
        return {"ok": True, "action": "agent_start"}

    def followup(self, receipt: dict[str, object]) -> dict[str, object]:
        self.followed_up.append(deepcopy(receipt))
        return {"ok": True, "action": "agent_followup"}

    def spawn_failed(
        self,
        request: dict[str, object],
        failure: dict[str, object],
    ) -> dict[str, object]:
        self.spawn_failures.append((deepcopy(request), deepcopy(failure)))
        return {"ok": True, "action": "agent_spawn_failed"}

    def quarantine(
        self,
        receipt: dict[str, object],
        error: Exception,
    ) -> dict[str, object]:
        self.quarantines.append((deepcopy(receipt), str(error)))
        return {"ok": True, "action": "agent_result_quarantine"}

    def reconcile(
        self,
        receipt: dict[str, object],
        error: Exception,
    ) -> dict[str, object]:
        self.reconciliations.append((deepcopy(receipt), str(error)))
        return {"ok": True, "action": "agent_reconcile"}

    def counts(self) -> dict[str, int]:
        return {
            "start": len(self.started),
            "followup": len(self.followed_up),
            "spawn_failed": len(self.spawn_failures),
            "quarantine": len(self.quarantines),
            "reconcile": len(self.reconciliations),
        }


def _dispatch_result(
    dispatch: object,
    request: dict[str, object],
    *,
    host: _RecordingHost,
    lifecycle: _RecordingLifecycle,
) -> tuple[object | None, Exception | None]:
    try:
        return dispatch(deepcopy(request), host=host, lifecycle=lifecycle), None  # type: ignore[operator]
    except Exception as exc:
        return None, exc


def _receipt(result: object | None) -> dict[str, object] | None:
    if not isinstance(result, dict):
        return None
    candidate = result.get("host_action_receipt")
    return candidate if isinstance(candidate, dict) else None


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validation_accepts(
    validate: object,
    receipt: dict[str, object],
    *,
    expected: dict[str, object],
    replay_guard: set[str],
) -> tuple[bool, str | None]:
    try:
        accepted = validate(  # type: ignore[operator]
            deepcopy(receipt),
            expected=deepcopy(expected),
            replay_guard=replay_guard,
        )
    except Exception as exc:
        return False, type(exc).__name__
    return accepted is not False, None


def _check_receipt_contract(
    validate: object,
    receipt: dict[str, object],
    *,
    request: dict[str, object],
    host_response: dict[str, object],
    decision: str,
    host_action: str,
    outcome: str,
) -> list[str]:
    failures: list[str] = []
    required_fields = {
        "schema",
        "receipt_id",
        "receipt_sha256",
        "decision",
        "host_action",
        "outcome",
        "request_sha256",
        "result_sha256",
        "acted_at",
        *REQUEST_BINDING_FIELDS,
        *HOST_BINDING_FIELDS,
    }
    if not required_fields.issubset(receipt):
        failures.append("native_host_action_receipt_fields_incomplete")
    if receipt.get("schema") != HOST_RECEIPT_SCHEMA:
        failures.append("native_host_action_receipt_schema_mismatch")
    expected_semantics = {
        "decision": decision,
        "host_action": host_action,
        "outcome": outcome,
    }
    for field, expected_value in expected_semantics.items():
        if receipt.get(field) != expected_value:
            failures.append(f"native_host_action_receipt_semantics_mismatch:{field}")
    if receipt.get("action") == "refusal":
        failures.append("native_host_refusal_encoded_as_action")
    if receipt.get("request_sha256") != _canonical_sha256(request):
        failures.append("native_host_action_receipt_request_sha256_mismatch")
    if receipt.get("result_sha256") != _canonical_sha256(host_response):
        failures.append("native_host_action_receipt_result_sha256_mismatch")
    if not isinstance(receipt.get("acted_at"), str) or not receipt.get("acted_at"):
        failures.append("native_host_action_receipt_acted_at_missing")
    for field in REQUEST_BINDING_FIELDS:
        if receipt.get(field) != request.get(field):
            failures.append(f"native_host_action_receipt_request_binding_mismatch:{field}")
    for field in HOST_BINDING_FIELDS:
        if receipt.get(field) != host_response.get(field):
            failures.append(f"native_host_action_receipt_host_binding_mismatch:{field}")

    accepted, error_kind = _validation_accepts(
        validate,
        receipt,
        expected=request,
        replay_guard=set(),
    )
    if not accepted:
        failures.append(
            "native_host_action_receipt_validation_failed"
            + (f":{error_kind}" if error_kind else "")
        )

    tamper_cases: list[tuple[str, dict[str, object]]] = []
    for field, value in (
        ("schema", "court.native_host_action_receipt.invalid"),
        ("task_id", "other-task"),
        ("wave_id", "other-wave"),
        ("dispatch_uid", "other-dispatch"),
        ("attempt", 99),
        ("role", "hubu"),
        ("instance_id", "other-instance"),
        ("direct_superior", "taizi"),
        ("semantic_epoch", 8),
        ("charter_sha256", "f" * 64),
        ("invariant_capsule_sha256", "f" * 64),
        ("lease_id", "other-lease"),
        ("assignment", "unrelated assignment"),
        ("duty_scope", ["scripts/unrelated.py"]),
        ("write_set", ["scripts/unrelated.py"]),
        (
            "role_ack",
            {
                "role": "gongbu",
                "direct_superior": "taizi",
                "profile_sha256": "b" * 64,
                "dossier_sha256": "d" * 64,
            },
        ),
        ("decision", "reuse" if decision == "spawn" else "spawn"),
        ("host_action", "followup" if host_action == "spawn" else "spawn"),
        ("outcome", "refused" if outcome == "succeeded" else "succeeded"),
        ("request_sha256", "1" * 64),
        ("result_sha256", "2" * 64),
        ("acted_at", "1900-01-01T00:00:00Z"),
        ("host_task_id", "other-host-task"),
        ("host_thread_id", "other-host-thread"),
        ("host_instance_id", "other-host-instance"),
        ("host_action_id", "other-host-action"),
        ("receipt_id", "other-receipt"),
        ("receipt_sha256", "0" * 64),
    ):
        candidate = deepcopy(receipt)
        candidate[field] = value
        tamper_cases.append((field, candidate))
    anchor_tamper = deepcopy(receipt)
    anchor = deepcopy(anchor_tamper.get("admission_anchor", {}))
    if isinstance(anchor, dict):
        anchor["receipt_sha256"] = "b" * 64
    anchor_tamper["admission_anchor"] = anchor
    tamper_cases.append(("admission_anchor", anchor_tamper))
    for field, candidate in tamper_cases:
        tamper_accepted, _ = _validation_accepts(
            validate,
            candidate,
            expected=request,
            replay_guard=set(),
        )
        if tamper_accepted:
            failures.append(f"native_host_action_receipt_tamper_accepted:{field}")

    for field in ("task_id", "wave_id"):
        mismatched_expected = deepcopy(request)
        mismatched_expected[field] = f"cross-{field}"
        cross_accepted, _ = _validation_accepts(
            validate,
            receipt,
            expected=mismatched_expected,
            replay_guard=set(),
        )
        if cross_accepted:
            failures.append(f"native_host_action_receipt_cross_binding_accepted:{field}")

    replay_guard: set[str] = set()
    first_accepted, _ = _validation_accepts(
        validate,
        receipt,
        expected=request,
        replay_guard=replay_guard,
    )
    second_accepted, _ = _validation_accepts(
        validate,
        receipt,
        expected=request,
        replay_guard=replay_guard,
    )
    if not first_accepted:
        failures.append("native_host_action_receipt_replay_first_use_rejected")
    elif second_accepted:
        failures.append("native_host_action_receipt_replay_accepted")

    anchor = request["admission_anchor"]
    if isinstance(anchor, dict):
        admission_accepted, _ = _validation_accepts(
            validate,
            anchor,
            expected=request,
            replay_guard=set(),
        )
        if admission_accepted:
            failures.append("admission_receipt_impersonated_host_delivery")
    return failures


def evaluate_native_host_lifecycle_contract(
    bridge: object,
) -> tuple[list[str], dict[str, object]]:
    failures: list[str] = []
    dispatch = getattr(bridge, "dispatch_native_host_action", None)
    validate = getattr(bridge, "validate_native_host_action_receipt", None)
    if not callable(dispatch) or not callable(validate):
        return ["native_host_lifecycle_bridge_symbols_unavailable"], {
            "behavior_evaluated": False
        }

    refusal_request = _request(suffix="refusal")
    refusal_host = _RecordingHost(
        suffix="refusal",
        spawn_response={
            "ok": False,
            "error_code": "host_refused",
            "reason": "fixture host capacity refusal",
            "host_task_id": "host-task-refusal",
            "host_thread_id": "host-thread-refusal",
            "host_instance_id": "host-instance-refusal",
            "host_action_id": f"host-action-refusal-{uuid.uuid4().hex}",
        },
    )
    refusal_lifecycle = _RecordingLifecycle()
    refusal_result, refusal_error = _dispatch_result(
        dispatch,
        refusal_request,
        host=refusal_host,
        lifecycle=refusal_lifecycle,
    )
    refusal_receipt = _receipt(refusal_result)
    refusal_counts = refusal_lifecycle.counts()
    if len(refusal_host.spawn_requests) != 1:
        failures.append("native_host_refusal_spawn_callback_count_invalid")
    if refusal_counts["spawn_failed"] != 1:
        failures.append("native_host_refusal_agent_spawn_failed_missing")
    if any(
        refusal_counts[key]
        for key in ("start", "followup", "quarantine", "reconcile")
    ):
        failures.append("native_host_refusal_mutated_agent_lifecycle")
    if not isinstance(refusal_receipt, dict):
        failures.append("native_host_refusal_receipt_missing")
    else:
        failures.extend(
            _check_receipt_contract(
                validate,
                refusal_receipt,
                request=refusal_request,
                host_response=refusal_host.spawn_response,
                decision="spawn",
                host_action="spawn",
                outcome="refused",
            )
        )

    compensation_request = _request(suffix="compensation")
    compensation_host = _RecordingHost(suffix="compensation")
    compensation_lifecycle = _RecordingLifecycle(fail_start=True)
    _, compensation_error = _dispatch_result(
        dispatch,
        compensation_request,
        host=compensation_host,
        lifecycle=compensation_lifecycle,
    )
    compensation_counts = compensation_lifecycle.counts()
    if len(compensation_host.spawn_requests) != 1:
        failures.append("native_host_lifecycle_failure_spawn_callback_count_invalid")
    if compensation_counts["start"] != 1:
        failures.append("native_host_success_lifecycle_start_missing")
    if compensation_counts["quarantine"] != 1:
        failures.append("native_host_success_lifecycle_failure_not_quarantined")
    if compensation_counts["reconcile"] != 1:
        failures.append("native_host_success_lifecycle_failure_not_reconciled")
    if compensation_counts["spawn_failed"]:
        failures.append("native_host_success_lifecycle_failure_misreported_as_spawn_failure")
    if compensation_counts["followup"]:
        failures.append("native_host_success_lifecycle_failure_misreported_as_followup")
    if compensation_lifecycle.started:
        started_receipt = compensation_lifecycle.started[0]
        failures.extend(
            _check_receipt_contract(
                validate,
                started_receipt,
                request=compensation_request,
                host_response=compensation_host.spawn_response,
                decision="spawn",
                host_action="spawn",
                outcome="succeeded",
            )
        )
        if (
            compensation_lifecycle.quarantines
            and compensation_lifecycle.quarantines[0][0] != started_receipt
        ):
            failures.append("native_host_lifecycle_quarantine_receipt_drift")
        if (
            compensation_lifecycle.reconciliations
            and compensation_lifecycle.reconciliations[0][0] != started_receipt
        ):
            failures.append("native_host_lifecycle_reconcile_receipt_drift")

    ministry_evidence: dict[str, dict[str, object]] = {}
    for index, role in enumerate(MINISTRY_ROLES, start=1):
        request = _request(role=role, suffix=f"ministry-{index}")
        host = _RecordingHost(suffix=f"ministry-{index}")
        lifecycle = _RecordingLifecycle()
        result, error = _dispatch_result(
            dispatch,
            request,
            host=host,
            lifecycle=lifecycle,
        )
        receipt = _receipt(result)
        if error is not None:
            failures.append(
                f"native_six_ministry_valid_dispatch_failed:{role}:{type(error).__name__}"
            )
        if len(host.spawn_requests) != 1:
            failures.append(f"native_six_ministry_spawn_callback_count_invalid:{role}")
        if lifecycle.counts()["start"] != 1:
            failures.append(f"native_six_ministry_lifecycle_start_count_invalid:{role}")
        if not isinstance(receipt, dict) or receipt.get("direct_superior") != "shangshu":
            failures.append(f"native_six_ministry_superior_binding_missing:{role}")

        invalid_request = deepcopy(request)
        invalid_request["direct_superior"] = "taizi"
        invalid_host = _RecordingHost(suffix=f"invalid-ministry-{index}")
        invalid_lifecycle = _RecordingLifecycle()
        _, invalid_error = _dispatch_result(
            dispatch,
            invalid_request,
            host=invalid_host,
            lifecycle=invalid_lifecycle,
        )
        if invalid_host.spawn_requests or invalid_host.followup_requests:
            failures.append(f"native_six_ministry_superior_violation_accepted:{role}")
        if any(invalid_lifecycle.counts().values()):
            failures.append(f"native_six_ministry_superior_violation_mutated_lifecycle:{role}")
        ministry_evidence[role] = {
            "valid_error": type(error).__name__ if error else None,
            "invalid_error": type(invalid_error).__name__ if invalid_error else None,
            "valid_spawn_calls": len(host.spawn_requests),
            "invalid_host_calls": len(invalid_host.spawn_requests)
            + len(invalid_host.followup_requests),
        }

    return failures, {
        "behavior_evaluated": True,
        "refusal": {
            "dispatch_error": type(refusal_error).__name__ if refusal_error else None,
            "host_spawn_calls": len(refusal_host.spawn_requests),
            "lifecycle_calls": refusal_counts,
        },
        "lifecycle_compensation": {
            "dispatch_error": (
                type(compensation_error).__name__ if compensation_error else None
            ),
            "host_spawn_calls": len(compensation_host.spawn_requests),
            "lifecycle_calls": compensation_counts,
        },
        "six_ministries": ministry_evidence,
    }


def evaluate_bridge_contract(bridge: object) -> tuple[list[str], dict[str, object]]:
    failures: list[str] = []
    schema = getattr(bridge, "HOST_ACTION_RECEIPT_SCHEMA", None)
    if schema != HOST_RECEIPT_SCHEMA:
        failures.append("native_host_action_receipt_schema_mismatch")
    dispatch = getattr(bridge, "dispatch_native_host_action", None)
    validate = getattr(bridge, "validate_native_host_action_receipt", None)
    if not callable(dispatch):
        failures.append("native_host_dispatch_symbol_not_callable")
    if not callable(validate):
        failures.append("native_host_receipt_validator_symbol_not_callable")
    if not callable(dispatch) or not callable(validate):
        return failures, {"behavior_evaluated": False}

    request = _request(suffix="spawn")
    host = _RecordingHost(suffix="spawn")
    lifecycle = _RecordingLifecycle()
    result, error = _dispatch_result(
        dispatch,
        request,
        host=host,
        lifecycle=lifecycle,
    )
    receipt = _receipt(result)
    if error is not None:
        failures.append(f"native_host_spawn_contract_failed:{type(error).__name__}")
    if len(host.spawn_requests) != 1 or host.followup_requests:
        failures.append("native_host_spawn_callback_count_invalid")
    spawn_lifecycle_counts = lifecycle.counts()
    if spawn_lifecycle_counts["start"] != 1:
        failures.append("native_host_spawn_lifecycle_start_count_invalid")
    if any(
        spawn_lifecycle_counts[key]
        for key in ("followup", "spawn_failed", "quarantine", "reconcile")
    ):
        failures.append("native_host_spawn_lifecycle_path_contaminated")
    if not isinstance(receipt, dict):
        failures.append("native_host_action_receipt_missing")
    else:
        failures.extend(
            _check_receipt_contract(
                validate,
                receipt,
                request=request,
                host_response=host.spawn_response,
                decision="spawn",
                host_action="spawn",
                outcome="succeeded",
            )
        )
        if lifecycle.started and lifecycle.started[0] != receipt:
            failures.append("native_host_spawn_lifecycle_receipt_binding_drift")

    reuse_request = _request(suffix="reuse")
    reuse_candidate = _compatible_candidate(reuse_request)
    reuse_request["compatible_live_instances"] = [reuse_candidate]
    reuse_host = _RecordingHost(
        suffix="reuse",
        followup_response={
            "ok": True,
            "host_task_id": reuse_candidate["host_task_id"],
            "host_thread_id": reuse_candidate["host_thread_id"],
            "host_instance_id": reuse_candidate["host_instance_id"],
            "host_action_id": f"host-action-followup-{uuid.uuid4().hex}",
        },
    )
    reuse_lifecycle = _RecordingLifecycle()
    reuse_result, reuse_error = _dispatch_result(
        dispatch,
        reuse_request,
        host=reuse_host,
        lifecycle=reuse_lifecycle,
    )
    reuse_receipt = _receipt(reuse_result)
    if reuse_error is not None:
        failures.append(f"native_host_reuse_contract_failed:{type(reuse_error).__name__}")
    if reuse_host.spawn_requests or len(reuse_host.followup_requests) != 1:
        failures.append("native_compatible_reuse_did_not_use_followup")
    else:
        followup_identity, followup_request = reuse_host.followup_requests[0]
        if followup_identity != reuse_candidate["host_instance_id"]:
            failures.append("native_compatible_reuse_host_identity_changed")
        for field in (
            "task_id",
            "assignment",
            "duty_scope",
            "role",
            "direct_superior",
            "semantic_epoch",
            "charter_sha256",
            "invariant_capsule_sha256",
            "lease_id",
            "write_set",
            "role_ack",
        ):
            if followup_request.get(field) != reuse_request.get(field):
                failures.append(f"native_compatible_reuse_duty_continuity_broken:{field}")
    reuse_lifecycle_counts = reuse_lifecycle.counts()
    if reuse_lifecycle_counts["followup"] != 1:
        failures.append("native_compatible_reuse_lifecycle_followup_count_invalid")
    if any(
        reuse_lifecycle_counts[key]
        for key in ("start", "spawn_failed", "quarantine", "reconcile")
    ):
        failures.append("native_compatible_reuse_created_second_lifecycle_record")
    if not isinstance(reuse_receipt, dict):
        failures.append("native_compatible_reuse_receipt_missing")
    else:
        failures.extend(
            _check_receipt_contract(
                validate,
                reuse_receipt,
                request=reuse_request,
                host_response=reuse_host.followup_response or {},
                decision="reuse",
                host_action="followup",
                outcome="succeeded",
            )
        )
        if reuse_lifecycle.followed_up and reuse_lifecycle.followed_up[0] != reuse_receipt:
            failures.append("native_compatible_reuse_lifecycle_receipt_binding_drift")

    nonreuse_cases = (
        "context-limit",
        "unrelated",
        "task-drift",
        "semantic-drift",
        "lease-drift",
        "write-set-drift",
        "role-ack-drift",
    )
    nonreuse_evidence: dict[str, dict[str, int]] = {}
    for label in nonreuse_cases:
        candidate_request = _request(suffix=label)
        candidate = _compatible_candidate(
            candidate_request,
            context_utilization=0.80 if label == "context-limit" else 0.20,
            assignment=(
                "unrelated release publishing" if label == "unrelated" else None
            ),
        )
        if label == "task-drift":
            candidate["task_id"] = "other-task"
        elif label == "semantic-drift":
            semantic_receipt = deepcopy(candidate["semantic_receipt"])
            semantic_receipt["semantic_epoch"] = 8
            candidate["semantic_receipt"] = semantic_receipt
        elif label == "lease-drift":
            candidate["lease_id"] = "other-lease"
        elif label == "write-set-drift":
            candidate["write_set"] = ["scripts/unrelated.py"]
        elif label == "role-ack-drift":
            role_ack = deepcopy(candidate["role_ack"])
            role_ack["direct_superior"] = "taizi"
            candidate["role_ack"] = role_ack
        candidate_request["compatible_live_instances"] = [candidate]
        candidate_host = _RecordingHost(suffix=label)
        candidate_lifecycle = _RecordingLifecycle()
        candidate_result, candidate_error = _dispatch_result(
            dispatch,
            candidate_request,
            host=candidate_host,
            lifecycle=candidate_lifecycle,
        )
        candidate_receipt = _receipt(candidate_result)
        if candidate_error is not None:
            failures.append(
                f"native_nonreuse_spawn_contract_failed:{label}:{type(candidate_error).__name__}"
            )
        if len(candidate_host.spawn_requests) != 1 or candidate_host.followup_requests:
            failures.append(f"native_incompatible_instance_reused:{label}")
        candidate_lifecycle_counts = candidate_lifecycle.counts()
        if candidate_lifecycle_counts["start"] != 1:
            failures.append(f"native_nonreuse_lifecycle_start_count_invalid:{label}")
        if any(
            candidate_lifecycle_counts[key]
            for key in ("followup", "spawn_failed", "quarantine", "reconcile")
        ):
            failures.append(f"native_nonreuse_lifecycle_path_contaminated:{label}")
        if not isinstance(candidate_receipt, dict):
            failures.append(f"native_nonreuse_receipt_missing:{label}")
        else:
            failures.extend(
                f"{label}:{failure}"
                for failure in _check_receipt_contract(
                    validate,
                    candidate_receipt,
                    request=candidate_request,
                    host_response=candidate_host.spawn_response,
                    decision="spawn",
                    host_action="spawn",
                    outcome="succeeded",
                )
            )
            if (
                candidate_lifecycle.started
                and candidate_lifecycle.started[0] != candidate_receipt
            ):
                failures.append(f"native_nonreuse_lifecycle_receipt_binding_drift:{label}")
        nonreuse_evidence[label] = {
            "spawn": len(candidate_host.spawn_requests),
            "followup": len(candidate_host.followup_requests),
            "lifecycle": candidate_lifecycle_counts,
            "receipt_present": isinstance(candidate_receipt, dict),
        }

    dynamic_request = _request(suffix="dynamic")
    dynamic_host = _RecordingHost(suffix="dynamic")
    dynamic_lifecycle = _RecordingLifecycle()
    dynamic_result, dynamic_error = _dispatch_result(
        dispatch,
        dynamic_request,
        host=dynamic_host,
        lifecycle=dynamic_lifecycle,
    )
    dynamic_receipt = _receipt(dynamic_result)
    if dynamic_lifecycle.counts()["start"] != 1:
        failures.append("native_host_dynamic_receipt_lifecycle_start_count_invalid")
    if dynamic_error is not None or not isinstance(dynamic_receipt, dict):
        failures.append("native_host_dynamic_receipt_second_dispatch_failed")
    else:
        failures.extend(
            _check_receipt_contract(
                validate,
                dynamic_receipt,
                request=dynamic_request,
                host_response=dynamic_host.spawn_response,
                decision="spawn",
                host_action="spawn",
                outcome="succeeded",
            )
        )
        if isinstance(receipt, dict) and (
            dynamic_receipt.get("receipt_id") == receipt.get("receipt_id")
            or dynamic_receipt.get("receipt_sha256") == receipt.get("receipt_sha256")
        ):
            failures.append("native_host_constant_receipt_reused")

    lifecycle_failures, lifecycle_evidence = evaluate_native_host_lifecycle_contract(
        bridge
    )
    failures.extend(lifecycle_failures)
    return failures, {
        "behavior_evaluated": True,
        "spawn": {
            "error": type(error).__name__ if error else None,
            "spawn_calls": len(host.spawn_requests),
            "followup_calls": len(host.followup_requests),
            "lifecycle_calls": lifecycle.counts(),
            "receipt": receipt,
        },
        "reuse": {
            "error": type(reuse_error).__name__ if reuse_error else None,
            "spawn_calls": len(reuse_host.spawn_requests),
            "followup_calls": len(reuse_host.followup_requests),
            "receipt": reuse_receipt,
        },
        "nonreuse": nonreuse_evidence,
        "native_host_lifecycle": lifecycle_evidence,
    }


def evaluate() -> dict[str, Any]:
    failures: list[str] = []
    execution = select_native_execution(
        authority="super",
        behavior="parallel",
        root=ROOT,
    ).as_dict()
    if execution.get("transport") not in {"host_dispatch_pending", "host_action_required"}:
        failures.append("native_parallel_transport_not_host_pending")
    if execution.get("transport") == "spawned_subagent" or execution.get("spawned") is True:
        failures.append("native_selector_premature_spawn_claim")
    selector_effect_fields = {
        "host_action_receipt",
        "host_task_id",
        "host_thread_id",
        "host_instance_id",
        "host_action_id",
        "decision",
        "host_action",
        "outcome",
    }
    leaked_effect_fields = sorted(selector_effect_fields.intersection(execution))
    if leaked_effect_fields:
        failures.append("native_selector_premature_host_receipt")
    if execution.get("host_callback_count", 0) != 0:
        failures.append("native_selector_invoked_host_callback")

    bridge, bridge_failures = load_bridge()
    failures.extend(bridge_failures)
    bridge_evidence: dict[str, object] = {"behavior_evaluated": False}
    if bridge is not None and not bridge_failures:
        behavior_failures, bridge_evidence = evaluate_bridge_contract(bridge)
        failures.extend(behavior_failures)

    return {
        "schema": "court.native_host_dispatch_check.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": "COURT_NATIVE_HOST_DISPATCH",
        "evidence": {
            "execution": execution,
            "bridge_path": str(BRIDGE_PATH),
            "bridge_exists": bridge is not None,
            "required_host_receipt_schema": HOST_RECEIPT_SCHEMA,
            "selector_purity": {
                "host_callback_count": execution.get("host_callback_count", 0),
                "effect_fields": leaked_effect_fields,
            },
            "required_host_actions": ["spawn", "followup"],
            "required_lifecycle_compensations": ["quarantine", "reconcile"],
            "required_outcomes": ["succeeded", "refused"],
            "bridge_contract": bridge_evidence,
        },
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate()
    except Exception as exc:
        result = {
            "schema": "court.native_host_dispatch_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "COURT_NATIVE_HOST_DISPATCH",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"COURT_NATIVE_HOST_DISPATCH={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
