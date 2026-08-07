"""Stage-3 focused gate: real production result-recovery chain.

Drives the production runtime through the complete recovery chain:
quarantine (agent_finish binding mismatch) -> menxia review -> shangshu
handoff with a bridge-minted native host follow-up receipt -> target finish
with recovery_input_ids -> automatic consume.  Also exercises the negative
gates (wrong actor, CAS conflict, legacy read-only, privacy, idempotent
replay, consume-before-handoff) and verifies quarantine-core immutability
plus the typed receipt chain (review/handoff/consume receipts).

The native host action receipt is minted by the existing bridge fixture
(court_native_host_dispatch.dispatch_native_host_action with a fixture Host)
and is explicitly marked fixture-minted in the evidence; it is not a real
host delivery.
"""

from __future__ import annotations

import argparse
from argparse import Namespace
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import uuid
from typing import Callable

sys.dont_write_bytecode = True

# Import the lifecycle checker first: its module-level code installs the
# import-isolation environment.  We then point runtime_root() at this
# checker's own fixture root (runtime_root() resolves dynamically), exactly
# like the lifecycle suite does.
import check_court_agent_lifecycle as lifecycle  # noqa: E402
import court_runtime  # noqa: E402
from court_semantic_continuity import build_result_recovery_binding  # noqa: E402
from check_court_native_host_dispatch import load_bridge  # noqa: E402
import check_install_release_boundary as boundary  # noqa: E402


CONTRACT = "COURT_STAGE3_RECOVERY_CHAIN"
SCHEMA = "court.stage3_recovery_chain_check.v1"
SELECTION = "stage3-recovery-chain"
NOT_EVALUATED = [
    "cross-task-recovery",
    "worktree-thread-source",
    "multi-recovery-batch-consume",
]

EVIDENCE_PREFIX = "stage3/evidence/recovery-chain"

_failures: list[str] = []
_evidence: dict[str, object] = {}
_bridge: object | None = None


def _reject(action: Callable[[], object], label: str, expected_reason: str) -> None:
    """Run a mutation that must fail with the expected reason and leave bytes alone."""
    tasks_path = court_runtime.tasks_path()
    events_path = court_runtime.events_path()
    before_tasks = tasks_path.read_bytes() if tasks_path.exists() else b""
    before_events = events_path.read_bytes() if events_path.exists() else b""
    try:
        action()
    except ValueError as exc:
        if expected_reason not in str(exc):
            _failures.append(f"{label}:expected={expected_reason} got={exc}")
            return
    except Exception as exc:  # noqa: BLE001
        _failures.append(f"{label}:unexpected={type(exc).__name__}:{exc}")
        return
    else:
        _failures.append(f"{label}:mutation_was_not_rejected")
        return
    if (
        tasks_path.read_bytes() != before_tasks
        or events_path.read_bytes() != before_events
    ):
        _failures.append(f"{label}:runtime_bytes_changed")


def _office_agent(
    task_id: str,
    wave_id: str,
    instance_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Admit + spawn-receipt start + preload ack for one child_agent instance."""
    carrier_proof = {"agent_id": instance_id}
    task_name = f"{instance_id.replace('-', '_')}_office"
    admission = lifecycle.admit(
        task_id,
        wave_id,
        office_api=True,
        office_instance_kind="child_agent",
        office_instance_id=instance_id,
        collaboration_task_name=task_name,
        carrier_proof=carrier_proof,
    )
    start = lifecycle.start_args(
        admission,
        task_id,
        wave_id,
        instance_id,
        instance_id=instance_id,
        collaboration_task_name=task_name,
        office_instance_kind="child_agent",
        office_instance_id=instance_id,
        carrier_proof=carrier_proof,
    )
    start._production_cli = True
    request = lifecycle._native_host_request(
        admission,
        task_id=task_id,
        wave_id=wave_id,
        instance_id=instance_id,
    )
    token = uuid.uuid4().hex
    host_result = {
        "ok": True,
        "host_task_id": f"host-task-{token}",
        "host_thread_id": f"host-thread-{token}",
        "host_instance_id": f"host-instance-{token}",
        "host_action_id": f"host-action-{token}",
    }
    receipt, mint = lifecycle._mint_native_host_receipt(
        _bridge, request, host_result=host_result
    )
    if receipt is None:
        raise AssertionError(f"spawn receipt mint failed: {mint}")
    start.native_host_action_receipt = deepcopy(receipt)
    court_runtime.office_start(start)
    court_runtime.agent_preload_ack(lifecycle.ack_args(task_id, instance_id))
    record = court_runtime.load_tasks()[task_id]["agents"][instance_id]
    return admission, dict(record)


def _quarantine_source(
    task_id: str,
    source_instance: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Trigger a real quarantine by finishing with a stale-attempt envelope."""
    stale = lifecycle.finish_args(task_id, source_instance)
    stale.office_instance_kind = "child_agent"
    stale.office_instance_id = source_instance
    stale.carrier_proof = {"agent_id": source_instance}
    original_envelope = deepcopy(stale.result_envelope)
    original_envelope["attempt"] = int(original_envelope["attempt"]) + 1
    stale.result_envelope = deepcopy(original_envelope)
    court_runtime.office_finish(stale)
    task = court_runtime.load_tasks()[task_id]
    source = task["agents"][source_instance]
    if source.get("result_state") != "QUARANTINED":
        raise AssertionError("source agent was not quarantined")
    records = task.get("quarantined_results")
    metadata = next(
        (
            item
            for item in records
            if isinstance(item, dict)
            and isinstance(item.get("core"), dict)
        ),
        None,
    )
    if not isinstance(metadata, dict):
        raise AssertionError("quarantine core missing")
    return dict(metadata["core"]), original_envelope


def _review_args(
    task_id: str,
    core: dict[str, object],
    original_envelope: dict[str, object],
    *,
    operation_id: str,
    evidence_pointer: str = f"{EVIDENCE_PREFIX}/review",
    actor: str = "menxia",
    **overrides: object,
) -> Namespace:
    values: dict[str, object] = {
        "task_id": task_id,
        "actor": actor,
        "decision": "ACCEPT",
        "quarantine_id": core["quarantine_id"],
        "source_result": deepcopy(original_envelope),
        "reason_codes": ["ACCEPT_BOUNDED_EVIDENCE"],
        "evidence_pointer": evidence_pointer,
        "operation_id": operation_id,
    }
    values.update(overrides)
    return Namespace(**values)


def _native_followup_fixture(
    admission: dict[str, object],
    task_id: str,
    wave_id: str,
    instance_id: str,
    recovery_binding: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Mint a reuse/followup native host receipt bound to a recovery request."""
    request = lifecycle._native_host_request(
        admission,
        task_id=task_id,
        wave_id=wave_id,
        instance_id=instance_id,
    )
    request["recovery_binding"] = deepcopy(recovery_binding)
    token = uuid.uuid4().hex
    candidate = {
        "host_task_id": f"host-task-reuse-{token}",
        "host_thread_id": f"host-thread-reuse-{token}",
        "host_instance_id": f"host-instance-reuse-{token}",
        "task_id": request["task_id"],
        "role": request["role"],
        "direct_superior": request["direct_superior"],
        "assignment": request["assignment"],
        "duty_scope": list(request["duty_scope"]),
        "semantic_receipt": {
            "semantic_epoch": request["semantic_epoch"],
            "charter_sha256": request["charter_sha256"],
            "invariant_capsule_sha256": request["invariant_capsule_sha256"],
        },
        "lease_id": request["lease_id"],
        "write_set": list(request["write_set"]),
        "role_ack": deepcopy(request["role_ack"]),
        "context_utilization": 0.42,
        "status": "running",
    }
    request["compatible_live_instances"] = [candidate]
    host_result = {
        "ok": True,
        "host_task_id": candidate["host_task_id"],
        "host_thread_id": candidate["host_thread_id"],
        "host_instance_id": candidate["host_instance_id"],
        "host_action_id": f"host-action-reuse-{token}",
    }
    receipt, mint = lifecycle._mint_native_host_receipt(
        _bridge, request, host_result=host_result
    )
    if receipt is None:
        raise AssertionError(f"followup receipt mint failed: {mint}")
    return receipt, request, host_result


def _run_full_chain() -> None:
    task_id = "stage3-full-recovery-chain"
    source_instance = "gongbu-stage3-source-0001"
    target_instance = "gongbu-stage3-target-0001"
    lifecycle.create_task(task_id)
    lifecycle.open_decree(task_id)
    _office_agent(task_id, "stage3-source-wave", source_instance)
    target_admission, _ = _office_agent(task_id, "stage3-target-wave", target_instance)

    core, original_envelope = _quarantine_source(task_id, source_instance)
    quarantine_id = str(core["quarantine_id"])
    recovery_id = "REC-" + quarantine_id

    # --- menxia review ---------------------------------------------------
    review = court_runtime.review_quarantined_result(
        _review_args(
            task_id,
            core,
            original_envelope,
            operation_id=f"review-{recovery_id}",
        )
    )
    if review.get("status") != "COMMITTED":
        raise AssertionError(f"review not committed: {review}")
    review_receipt = review["receipt"]
    _evidence["review_receipt"] = {
        "schema": review_receipt["schema"],
        "receipt_id": review_receipt["receipt_id"],
        "actor": review_receipt["actor"],
        "decision": review_receipt["decision"],
        "recovery_revision": review_receipt["recovery_revision"],
        "reason_codes": review_receipt["reason_codes"],
    }
    if review_receipt["schema"] != "court.office.result_recovery_review_receipt.v1":
        _failures.append("full_chain_review_schema_mismatch")
    if review_receipt["actor"] != "menxia":
        _failures.append("full_chain_review_actor_mismatch")
    if review_receipt["decision"] != "ACCEPT":
        _failures.append("full_chain_review_decision_mismatch")

    # --- idempotent replay of the same review ----------------------------
    replay = court_runtime.review_quarantined_result(
        _review_args(
            task_id,
            core,
            original_envelope,
            operation_id=f"review-{recovery_id}",
        )
    )
    if replay.get("status") != "REPLAYED" or replay.get("receipt") != review_receipt:
        _failures.append("full_chain_review_replay_not_idempotent")

    # --- shangshu handoff with native follow-up receipt ------------------
    task = court_runtime.load_tasks()[task_id]
    target = task["agents"][target_instance]
    target_binding, target_binding_sha256 = court_runtime._validate_target_binding(
        task, target
    )
    recovery_binding = build_result_recovery_binding(
        recovery_id=recovery_id,
        quarantine_id=quarantine_id,
        quarantine_core_sha256=str(core["core_sha256"]),
        recovery_head_sha256=str(review["head"]["head_sha256"]),
        projection_sha256=str(review["projection"]["projection_sha256"]),
        review_receipt_sha256=str(review_receipt["receipt_sha256"]),
        target_binding_sha256=target_binding_sha256,
    )
    native_receipt, native_request, native_host_result = _native_followup_fixture(
        target_admission,
        task_id,
        "stage3-target-wave",
        target_instance,
        recovery_binding,
    )
    _evidence["native_host_receipt"] = {
        "nature": "bridge_fixture_minted",
        "note": (
            "minted by court_native_host_dispatch.dispatch_native_host_action "
            "with a fixture Host; not a real host delivery"
        ),
        "receipt_id": native_receipt["receipt_id"],
        "decision": native_receipt["decision"],
        "host_action": native_receipt["host_action"],
        "outcome": native_receipt["outcome"],
        "host_instance_id": native_host_result["host_instance_id"],
    }
    if native_receipt["decision"] != "reuse" or native_receipt["host_action"] != "followup":
        _failures.append("full_chain_native_receipt_not_reuse_followup")

    handoff = court_runtime.handoff_recovered_result(
        Namespace(
            task_id=task_id,
            actor="shangshu",
            quarantine_id=quarantine_id,
            recovery_id=recovery_id,
            target_agent_id=target_instance,
            native_host_request=deepcopy(native_request),
            native_host_action_receipt=deepcopy(native_receipt),
            evidence_pointer=f"{EVIDENCE_PREFIX}/handoff",
            operation_id=f"handoff-{recovery_id}",
        )
    )
    if handoff.get("status") != "COMMITTED":
        raise AssertionError(f"handoff not committed: {handoff}")
    handoff_receipt = handoff["receipt"]
    _evidence["handoff_receipt"] = {
        "schema": handoff_receipt["schema"],
        "receipt_id": handoff_receipt["receipt_id"],
        "actor": handoff_receipt["actor"],
        "target_binding_sha256": handoff_receipt["target_binding_sha256"],
        "native_host_action_receipt_id": handoff_receipt["native_host_action_receipt_id"],
        "recovery_revision": handoff_receipt["recovery_revision"],
    }
    if handoff_receipt["schema"] != "court.office.result_recovery_handoff_receipt.v1":
        _failures.append("full_chain_handoff_schema_mismatch")
    if handoff_receipt["actor"] != "shangshu":
        _failures.append("full_chain_handoff_actor_mismatch")
    if (
        handoff_receipt["native_host_action_receipt_id"]
        != native_receipt["receipt_id"]
    ):
        _failures.append("full_chain_handoff_native_receipt_not_bound")
    if handoff.get("recovery_binding") != recovery_binding:
        _failures.append("full_chain_recovery_binding_mismatch")

    # --- target finish with recovery_input_ids (automatic consume) -------
    target_finish = lifecycle.finish_args(task_id, target_instance)
    target_finish.office_instance_kind = "child_agent"
    target_finish.office_instance_id = target_instance
    target_finish.carrier_proof = {"agent_id": target_instance}
    target_finish.result_envelope["recovery_input_ids"] = [recovery_id]
    finished = court_runtime.office_finish(target_finish)
    finish_event = finished["event"]
    consume_receipt_ids = finish_event.get("recovery_consume_receipt_ids") or []
    if len(consume_receipt_ids) != 1:
        raise AssertionError(f"consume receipts missing: {finish_event}")

    task = court_runtime.load_tasks()[task_id]
    operations = task["result_recovery_operations"]
    consume_operation = next(
        (
            value
            for value in operations.values()
            if str(value.get("operation_id", "")).startswith("consume-")
        ),
        None,
    )
    if not isinstance(consume_operation, dict):
        raise AssertionError("consume operation missing")
    consume_receipt = consume_operation["receipt"]
    _evidence["consume_receipt"] = {
        "schema": consume_receipt["schema"],
        "receipt_id": consume_receipt["receipt_id"],
        "actor": consume_receipt["actor"],
        "recovery_revision": consume_receipt["recovery_revision"],
        "target_result_envelope_sha256": consume_receipt["target_result_envelope_sha256"],
    }
    if consume_receipt["schema"] != "court.office.result_recovery_consume_receipt.v1":
        _failures.append("full_chain_consume_schema_mismatch")
    if consume_receipt["actor"] != "shangshu":
        _failures.append("full_chain_consume_actor_mismatch")
    if consume_receipt["receipt_id"] not in consume_receipt_ids:
        _failures.append("full_chain_consume_receipt_not_in_finish_event")

    # --- head chain and quarantine-core immutability ---------------------
    history = task["result_recovery_history"]
    states = [str(head.get("state")) for head in history]
    revisions = [int(head.get("revision")) for head in history]
    zero = "0" * 64
    if states != ["READY_FOR_HANDOFF", "HANDED_OFF", "CONSUMED"]:
        _failures.append(f"full_chain_head_states:{states}")
    if revisions != [1, 2, 3]:
        _failures.append(f"full_chain_head_revisions:{revisions}")
    if str(history[0].get("previous_head_sha256")) != zero:
        _failures.append("full_chain_head_previous_not_zero")
    if (
        str(history[1].get("previous_head_sha256"))
        != str(history[0].get("head_sha256"))
        or str(history[2].get("previous_head_sha256"))
        != str(history[1].get("head_sha256"))
    ):
        _failures.append("full_chain_head_chain_broken")
    stored_core = next(
        (
            item["core"]
            for item in task["quarantined_results"]
            if isinstance(item, dict) and isinstance(item.get("core"), dict)
        ),
        None,
    )
    if stored_core != core:
        _failures.append("full_chain_quarantine_core_mutated")
    target_record = task["agents"][target_instance]
    if recovery_id not in (target_record.get("recovery_consumed_ids") or []):
        _failures.append("full_chain_target_consumed_ledger_missing")
    if str(target_record.get("result_state") or "") != "" and str(
        target_record.get("result_state")
    ) != "NONE":
        _failures.append(f"full_chain_target_result_state:{target_record.get('result_state')}")

    _evidence["head_chain"] = [
        {
            "state": head.get("state"),
            "revision": head.get("revision"),
            "review_receipt_sha256": head.get("review_receipt_sha256"),
            "handoff_receipt_sha256": head.get("handoff_receipt_sha256"),
            "consume_receipt_sha256": head.get("consume_receipt_sha256"),
        }
        for head in history
    ]


def _test_review_wrong_actor() -> None:
    task_id = "stage3-neg-review-actor"
    source_instance = "gongbu-stage3-neg-actor-0001"
    lifecycle.create_task(task_id)
    lifecycle.open_decree(task_id)
    _office_agent(task_id, "stage3-neg-actor-wave", source_instance)
    core, original_envelope = _quarantine_source(task_id, source_instance)
    _reject(
        lambda: court_runtime.review_quarantined_result(
            _review_args(
                task_id,
                core,
                original_envelope,
                operation_id="neg-review-actor",
                actor="gongbu",
            )
        ),
        "negative_review_wrong_actor",
        "result_recovery_actor_forbidden",
    )


def _test_review_cas_conflict() -> None:
    task_id = "stage3-neg-review-cas"
    source_instance = "gongbu-stage3-neg-cas-0001"
    lifecycle.create_task(task_id)
    lifecycle.open_decree(task_id)
    _office_agent(task_id, "stage3-neg-cas-wave", source_instance)
    core, original_envelope = _quarantine_source(task_id, source_instance)
    _reject(
        lambda: court_runtime.review_quarantined_result(
            _review_args(
                task_id,
                core,
                original_envelope,
                operation_id="neg-review-cas",
                expected_head_sha256="1" * 64,
            )
        ),
        "negative_review_head_conflict",
        "result_recovery_head_conflict",
    )


def _test_handoff_wrong_actor() -> None:
    task_id = "stage3-neg-handoff-actor"
    source_instance = "gongbu-stage3-neg-hoa-source-0001"
    target_instance = "gongbu-stage3-neg-hoa-target-0001"
    lifecycle.create_task(task_id)
    lifecycle.open_decree(task_id)
    _office_agent(task_id, "stage3-neg-hoa-source-wave", source_instance)
    _office_agent(task_id, "stage3-neg-hoa-target-wave", target_instance)
    core, original_envelope = _quarantine_source(task_id, source_instance)
    recovery_id = "REC-" + str(core["quarantine_id"])
    court_runtime.review_quarantined_result(
        _review_args(
            task_id,
            core,
            original_envelope,
            operation_id=f"neg-hoa-review-{recovery_id}",
        )
    )
    _reject(
        lambda: court_runtime.handoff_recovered_result(
            Namespace(
                task_id=task_id,
                actor="gongbu",
                quarantine_id=core["quarantine_id"],
                recovery_id=recovery_id,
                target_agent_id=target_instance,
                evidence_pointer=f"{EVIDENCE_PREFIX}/neg-hoa",
                operation_id=f"neg-hoa-handoff-{recovery_id}",
            )
        ),
        "negative_handoff_wrong_actor",
        "result_recovery_actor_forbidden",
    )


def _test_legacy_read_only() -> None:
    task_id = "stage3-neg-legacy"
    lifecycle.create_task(task_id)
    lifecycle.open_decree(task_id)

    def inject_legacy(task: dict[str, object]) -> None:
        records = task.setdefault("quarantined_results", [])
        records.append(
            {
                "schema": "court.office.result_quarantine.v1",
                "quarantine_id": "QR-LEGACY-V1",
                "payload_sha256": "0" * 64,
                "task_id": task_id,
                "source_status": "failed",
                "source_final_status": "failed",
            }
        )

    lifecycle.set_task_field(task_id, inject_legacy)
    _reject(
        lambda: court_runtime.review_quarantined_result(
            Namespace(
                task_id=task_id,
                actor="menxia",
                decision="ACCEPT",
                quarantine_id="QR-LEGACY-V1",
                evidence_pointer=f"{EVIDENCE_PREFIX}/neg-legacy",
                operation_id="neg-legacy-review",
            )
        ),
        "negative_legacy_read_only",
        "result_recovery_legacy_read_only",
    )


def _test_privacy_gate() -> None:
    task_id = "stage3-neg-privacy"
    source_instance = "gongbu-stage3-neg-privacy-0001"
    lifecycle.create_task(task_id)
    lifecycle.open_decree(task_id)
    _office_agent(task_id, "stage3-neg-privacy-wave", source_instance)
    core, original_envelope = _quarantine_source(task_id, source_instance)
    _reject(
        lambda: court_runtime.review_quarantined_result(
            _review_args(
                task_id,
                core,
                original_envelope,
                operation_id="neg-privacy-review",
                evidence_pointer="stage3/pending/private-leak",
            )
        ),
        "negative_privacy_gate",
        "result_recovery_privacy_gate_failed",
    )


def _test_consume_without_handoff() -> None:
    task_id = "stage3-neg-consume-early"
    source_instance = "gongbu-stage3-neg-early-source-0001"
    target_instance = "gongbu-stage3-neg-early-target-0001"
    lifecycle.create_task(task_id)
    lifecycle.open_decree(task_id)
    _office_agent(task_id, "stage3-neg-early-source-wave", source_instance)
    _office_agent(task_id, "stage3-neg-early-target-wave", target_instance)
    core, original_envelope = _quarantine_source(task_id, source_instance)
    recovery_id = "REC-" + str(core["quarantine_id"])
    court_runtime.review_quarantined_result(
        _review_args(
            task_id,
            core,
            original_envelope,
            operation_id=f"neg-early-review-{recovery_id}",
        )
    )
    target_finish = lifecycle.finish_args(task_id, target_instance)
    target_finish.office_instance_kind = "child_agent"
    target_finish.office_instance_id = target_instance
    target_finish.carrier_proof = {"agent_id": target_instance}
    target_finish.result_envelope["recovery_input_ids"] = [recovery_id]
    _reject(
        lambda: court_runtime.office_finish(target_finish),
        "negative_consume_without_handoff",
        "result_recovery_not_handed_off",
    )


def _killpoint_case(phase: str) -> None:
    slug = phase.lower().replace('_', '-')
    label = 'killpoint_' + slug
    task_id = 'stage3-neg-killpoint-' + slug
    source_instance = 'gongbu-stage3-neg-kp-' + slug + '-0001'
    lifecycle.create_task(task_id)
    lifecycle.open_decree(task_id)
    _office_agent(task_id, 'stage3-neg-kp-' + slug + '-wave', source_instance)
    core, original_envelope = _quarantine_source(task_id, source_instance)
    operation_id = 'kp-' + slug + '-review'
    tasks_path = court_runtime.tasks_path()
    events_path = court_runtime.events_path()
    pre_tasks = tasks_path.read_bytes()
    pre_events = events_path.read_bytes()
    pre_event_count = len([line for line in pre_events.decode('utf-8').splitlines() if line.strip()])
    crashed = False
    try:
        court_runtime.review_quarantined_result(
            _review_args(
                task_id, core, original_envelope,
                operation_id=operation_id, killpoint=phase,
            )
        )
    except court_runtime.SimulatedResultRecoveryCrash as exc:
        crashed = str(exc) == phase
    if not crashed:
        _failures.append(label + ':no_simulated_crash')
        return
    marker_path = court_runtime.result_recovery_marker_path(operation_id)
    if not marker_path.exists():
        _failures.append(label + ':marker_missing_after_crash')
        return
    if phase == 'TASK_WRITTEN':
        tasks_path.write_bytes(pre_tasks[: max(1, len(pre_tasks) // 2)])
    outcome = court_runtime.recover_result_recovery_operation(operation_id)
    if marker_path.exists():
        _failures.append(label + ':marker_not_cleared')
    task = court_runtime.load_tasks()[task_id]
    history = task.get('result_recovery_history') or []
    operations = task.get('result_recovery_operations') or {}
    post_event_count = len(
        [line for line in events_path.read_bytes().decode('utf-8').splitlines() if line.strip()]
    )
    if phase == 'EVENT_WRITTEN':
        if outcome.get('outcome') != 'FINALIZE':
            _failures.append(label + ':expected_finalize')
        if len(history) != 1 or str(history[0].get('state')) != 'READY_FOR_HANDOFF':
            _failures.append(label + ':head_not_exactly_one')
        operation = operations.get(operation_id)
        if not isinstance(operation, dict) or not isinstance(operation.get('receipt'), dict):
            _failures.append(label + ':receipt_missing_after_finalize')
        if post_event_count != pre_event_count + 1:
            _failures.append(label + ':second_event_written')
        replay = court_runtime.recover_result_recovery_operation(operation_id)
        if replay.get('outcome') != 'REPLAYED':
            _failures.append(label + ':replay_not_idempotent')
        replay_event_count = len(
            [line for line in events_path.read_bytes().decode('utf-8').splitlines() if line.strip()]
        )
        if replay_event_count != post_event_count:
            _failures.append(label + ':replay_wrote_second_event')
        # M1 explicit negative assertion (correctness review): a legal
        # root-set input (exact schema, non-empty authority, fixture write
        # points) must receive a judgment from the strict evaluator, never a
        # silent empty rejection set that would mask an APPROVED verdict.
        # This is the positive control for the subset assertion relied on by
        # this forward-completion case; it runs in-memory against a tempfile
        # fixture root and performs zero writes to real install roots.
        with tempfile.TemporaryDirectory(prefix='court-stage3-strict-probe-') as probe_dir:
            probe_base = Path(probe_dir)
            _, probe_receipt, probe_proofs, probe_plan = boundary.build_fixture(probe_base)
            strict = boundary.evaluate_root_write_plan_strict(
                deepcopy(probe_receipt), deepcopy(probe_proofs), deepcopy(probe_plan)
            )
            if (
                strict.get('decision') != 'APPROVED'
                or strict.get('rejections') != []
            ):
                _failures.append(
                    label + ':strict_evaluator_silent_empty_on_legal_input'
                )
            else:
                _evidence[label + '_strict_nonempty_judgment'] = 'APPROVED'
    else:
        if outcome.get('outcome') != 'ROLLBACK':
            _failures.append(label + ':expected_rollback')
        if tasks_path.read_bytes() != pre_tasks or events_path.read_bytes() != pre_events:
            _failures.append(label + ':preimage_not_restored')
        if history or operations.get(operation_id):
            _failures.append(label + ':second_head_or_receipt_after_rollback')
        forward = court_runtime.review_quarantined_result(
            _review_args(task_id, core, original_envelope, operation_id=operation_id)
        )
        if forward.get('status') != 'COMMITTED':
            _failures.append(label + ':forward_path_not_clean_after_rollback')
    _evidence[label] = {'phase': phase, 'outcome': outcome.get('outcome')}
def _test_killpoint_recovery() -> None:
    # Killpoint negatives: PREPARED/TASK_WRITTEN/EVENT_WRITTEN crash then recover.
    for phase in ('PREPARED', 'TASK_WRITTEN', 'EVENT_WRITTEN'):
        _killpoint_case(phase)

def evaluate_stage3_recovery_chain() -> dict[str, object]:
    """Run the complete recovery-chain contract in an isolated fixture root."""
    global _bridge
    bridge, bridge_failures = load_bridge()
    _failures.extend(f"bridge:{failure}" for failure in bridge_failures)
    if bridge is None:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "FAIL",
            "contract": CONTRACT,
            "selection": SELECTION,
            "failures": list(_failures),
            "not_evaluated": list(NOT_EVALUATED),
        }
    _bridge = bridge
    _evidence["bridge_loaded"] = True
    with tempfile.TemporaryDirectory(prefix="court-stage3-recovery-") as temp_dir:
        fixture_root = Path(temp_dir)
        task_skill = fixture_root / "skills" / "stage3-recovery" / "SKILL.md"
        task_skill.parent.mkdir(parents=True)
        task_skill.write_text("# stage3 recovery chain fixture\n", encoding="utf-8")
        lifecycle.TASK_SPECIFIC_SKILL_PATH = task_skill
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: fixture_root / "runtime"  # type: ignore[assignment]
        try:
            _run_full_chain()
            _test_review_wrong_actor()
            _test_review_cas_conflict()
            _test_handoff_wrong_actor()
            _test_legacy_read_only()
            _test_privacy_gate()
            _test_consume_without_handoff()
            _test_killpoint_recovery()
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]
            lifecycle.TASK_SPECIFIC_SKILL_PATH = None
    return {
        "schema": SCHEMA,
        "ok": not _failures,
        "status": "PASS" if not _failures else "FAIL",
        "contract": CONTRACT,
        "selection": SELECTION,
        "failures": list(_failures),
        "not_evaluated": list(NOT_EVALUATED),
        "evidence": deepcopy(_evidence),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate_stage3_recovery_chain()
    except Exception as exc:  # noqa: BLE001
        result = {
            "schema": SCHEMA,
            "ok": False,
            "status": "ERROR",
            "contract": CONTRACT,
            "selection": SELECTION,
            "failures": [
                f"stage3_recovery_chain_checker_error:{type(exc).__name__}:{exc}"
            ],
            "not_evaluated": list(NOT_EVALUATED),
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{CONTRACT}={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
