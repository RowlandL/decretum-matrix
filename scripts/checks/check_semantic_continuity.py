"""Focused TDD checks for the A02 semantic-continuity core.

The checker uses only temporary ``COURT_RUNTIME_ROOT`` fixtures.  It never
opens the real Shiguan archive or pending import queue.
"""



from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading

sys.dont_write_bytecode = True

import court_operation_journal
from court_intake_gate import minimal_request_understanding_example
import court_semantic_continuity
import court_runtime


CAPSULE_REQUIRED_FIELDS = {
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


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _digest(label: str) -> str:
    return _sha256_text(label)


def check_public_invariant_capsule_contract() -> None:
    schema_factory = getattr(court_semantic_continuity, "invariant_capsule_json_schema", None)
    template_factory = getattr(court_semantic_continuity, "invariant_capsule_template", None)
    require_custom = getattr(court_semantic_continuity, "validate_invariant_capsule", None)
    if not callable(schema_factory):
        raise AssertionError("PUBLIC_INVARIANT_CAPSULE_SCHEMA_MISSING")
    if not callable(template_factory):
        raise AssertionError("PUBLIC_INVARIANT_CAPSULE_TEMPLATE_MISSING")
    if not callable(require_custom):
        raise AssertionError("PUBLIC_INVARIANT_CAPSULE_VALIDATE_MISSING")

    schema = schema_factory()
    if set(schema.get("required", [])) != CAPSULE_REQUIRED_FIELDS:
        raise AssertionError("PUBLIC_INVARIANT_CAPSULE_FIELDS_NOT_EXACT13")
    if schema.get("additionalProperties") is not False:
        raise AssertionError("PUBLIC_INVARIANT_CAPSULE_SCHEMA_NOT_CLOSED")

    charter = "诏" * 200 + " exact UTF-8 charter suffix"
    capsule = template_factory(charter, {"write_set": ["scripts/check_semantic_continuity.py"]})
    expected_sha256 = _sha256_text(charter)
    if capsule.get("latest_decree_sha256") != expected_sha256:
        raise AssertionError("PUBLIC_INVARIANT_CAPSULE_DECREE_HASH_RULE_DRIFTED")
    if capsule.get("charter_sha256") != expected_sha256:
        raise AssertionError("PUBLIC_INVARIANT_CAPSULE_CHARTER_HASH_RULE_DRIFTED")
    anchor = str(capsule.get("latest_decree_anchor", ""))
    if len(anchor.encode("utf-8")) > 256 or not charter.startswith(anchor):
        raise AssertionError("PUBLIC_INVARIANT_CAPSULE_UTF8_PREFIX_RULE_DRIFTED")
    normalized = require_custom(charter, capsule)
    if normalized != capsule:
        raise AssertionError("PUBLIC_INVARIANT_CAPSULE_CUSTOM_VALIDATE_DRIFTED")
    canonical = json.dumps(capsule, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(canonical) > 2048:
        raise AssertionError("PUBLIC_INVARIANT_CAPSULE_EXCEEDS_2KIB")

    exact_charter = " \r\n诏令：保留前后空白与 CRLF。\r\n "
    exact_digest = _sha256_text(exact_charter)
    exact_capsule = template_factory(exact_charter)
    if exact_capsule.get("latest_decree_sha256") != exact_digest:
        raise AssertionError("EXACT_CHARTER_DECREE_HASH_REWRITTEN")
    if exact_capsule.get("charter_sha256") != exact_digest:
        raise AssertionError("EXACT_CHARTER_HASH_REWRITTEN")
    exact_anchor = str(exact_capsule.get("latest_decree_anchor", ""))
    if not exact_charter.startswith(exact_anchor):
        raise AssertionError("EXACT_CHARTER_ANCHOR_REWRITTEN")


def _formal_gate_fixture() -> dict[str, object]:
    return {
        "schema": "court.conversation_gate.v1",
        "active_decree": False,
        "active_decree_state": "NONE",
        "message_class": "FORMAL_TASK",
        "confidence": "HIGH",
        "relation_to_active_decree": "NONE",
        "taskization_consent": "EXPLICIT",
        "requires_tools": True,
        "mutates_state": True,
        "risk_present": False,
        "next_route": "THREE_DEPARTMENTS",
        "question": "",
        "rationale": "F-RED-002 synthetic semantic-binding fixture",
        "understanding": minimal_request_understanding_example(),
    }


def _create_args(task_id: str, charter: str) -> Namespace:
    charter_sha256 = _sha256_text(charter)
    invariant_capsule = {
        "schema": "court.semantic.invariant_capsule.v1",
        "latest_decree_anchor": charter,
        "latest_decree_sha256": charter_sha256,
        "non_goals": ["do not expand scope"],
        "boundaries": ["TemporaryDirectory fixture only"],
        "allowed_actions": ["synthetic runtime mutation"],
        "forbidden_actions": ["real Shiguan access"],
        "acceptance": ["focused checker passes"],
        "evidence_requirements": ["JSON receipt"],
        "stop_gates": ["semantic drift"],
        "write_set": ["scripts/court_semantic_continuity.py"],
        "governing_hashes": {"execution_plan": _digest("execution-plan")},
        "charter_sha256": charter_sha256,
    }
    return Namespace(
        title=task_id,
        charter=charter,
        task_id=task_id,
        owner="taizi",
        report_tier="brief",
        evidence=f"create {task_id}",
        note="F-RED-002 create binding",
        work_kind="implementation",
        intake_gate=_formal_gate_fixture(),
        intake_file=None,
        invariant_capsule=invariant_capsule,
        invariant_capsule_file=None,
    )


def _correction_gate_fixture(task_id: str) -> dict[str, object]:
    return {
        "schema": "court.conversation_gate.v1",
        "active_decree": True,
        "active_decree_state": "ACTIVE",
        "message_class": "TASK_CORRECTION",
        "confidence": "HIGH",
        "relation_to_active_decree": "CORRECTS",
        "taskization_consent": "NOT_REQUIRED",
        "requires_tools": True,
        "mutates_state": True,
        "risk_present": False,
        "next_route": "THREE_DEPARTMENTS",
        "question": "",
        "rationale": "F-RED-002 body-bound correction fixture",
        "target_task_id": task_id,
    }


def _continuation_gate_fixture(task_id: str) -> dict[str, object]:
    return {
        "schema": "court.conversation_gate.v1",
        "active_decree": True,
        "active_decree_state": "PAUSED",
        "message_class": "TASK_CONTINUATION",
        "confidence": "HIGH",
        "relation_to_active_decree": "CONTINUES",
        "taskization_consent": "NOT_REQUIRED",
        "requires_tools": True,
        "mutates_state": True,
        "risk_present": False,
        "next_route": "THREE_DEPARTMENTS",
        "question": "",
        "rationale": "semantic resume fixture",
        "target_task_id": task_id,
    }


def _revise_args(
    task_id: str,
    *,
    old_charter: str,
    new_charter: str | None,
) -> Namespace:
    return Namespace(
        task_id=task_id,
        correction_gate=_correction_gate_fixture(task_id),
        correction_file=None,
        expected_revision=1,
        expected_sha256=_sha256_text(old_charter),
        new_revision=2,
        new_sha256=_sha256_text(new_charter or "declared hash without body"),
        new_charter=new_charter,
        new_charter_file=None,
        new_invariant_capsule=(
            _revision_capsule(new_charter, "revision-2")
            if new_charter is not None
            else None
        ),
        new_invariant_capsule_file=None,
        actor="taizi",
        evidence="F-RED-002 correction binding",
        note="body-bound correction",
    )


def check_create_initializes_atomic_semantic_binding() -> None:
    charter = "F-RED-002 初始章程正文"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            created = court_runtime.create_task(_create_args("f-red-002-create", charter))
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    task = created.task
    capsule = task.get("invariant_capsule")
    problems: list[str] = []
    if task.get("charter") != charter:
        problems.append("charter_body_mismatch")
    if task.get("charter_revision") != 1:
        problems.append("charter_revision_missing")
    if task.get("semantic_epoch") != 1:
        problems.append("semantic_epoch_missing")
    if task.get("charter_sha256") != _sha256_text(charter):
        problems.append("charter_sha256_mismatch")
    if not isinstance(capsule, dict):
        problems.append("invariant_capsule_missing")
    else:
        missing = sorted(CAPSULE_REQUIRED_FIELDS - set(capsule))
        if missing:
            problems.append("invariant_capsule_fields_missing:" + ",".join(missing))
        if capsule.get("charter_sha256") != task.get("charter_sha256"):
            problems.append("capsule_charter_sha256_mismatch")
        if len(
            json.dumps(
                capsule,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ) > 2048:
            problems.append("invariant_capsule_exceeds_2kib")
        if task.get("invariant_capsule_sha256") != _canonical_sha256(capsule):
            problems.append("invariant_capsule_sha256_mismatch")
    if task.get("charter_revision") != task.get("semantic_epoch"):
        problems.append("semantic_epoch_not_charter_revision")
    if problems:
        raise AssertionError("F-RED-002_CREATE_BINDING_MISSING " + ";".join(problems))


def check_correction_requires_and_binds_charter_body() -> None:
    task_id = "f-red-002-correct"
    old_charter = "F-RED-002 原章程正文"
    new_charter = "F-RED-002 修订章程正文"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, old_charter))
            before_tasks = court_runtime.tasks_path().read_bytes()
            before_events = court_runtime.events_path().read_bytes()
            try:
                court_runtime.revise_charter_task(
                    _revise_args(task_id, old_charter=old_charter, new_charter=None)
                )
            except ValueError as exc:
                if str(exc) != "charter_body_required":
                    raise AssertionError(
                        "F-RED-002_HASH_ONLY_CORRECTION_WRONG_ERROR " + str(exc)
                    ) from exc
            else:
                raise AssertionError("F-RED-002_HASH_ONLY_CORRECTION_ACCEPTED")
            if court_runtime.tasks_path().read_bytes() != before_tasks:
                raise AssertionError("F-RED-002_HASH_ONLY_CORRECTION_MUTATED_TASK")
            if court_runtime.events_path().read_bytes() != before_events:
                raise AssertionError("F-RED-002_HASH_ONLY_CORRECTION_MUTATED_EVENT")

            revised = court_runtime.revise_charter_task(
                _revise_args(task_id, old_charter=old_charter, new_charter=new_charter)
            ).task
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    capsule = revised.get("invariant_capsule")
    problems: list[str] = []
    if revised.get("charter") != new_charter:
        problems.append("charter_body_not_replaced")
    if revised.get("charter_revision") != 2:
        problems.append("charter_revision_not_incremented")
    if revised.get("semantic_epoch") != 2:
        problems.append("semantic_epoch_not_incremented")
    if revised.get("charter_sha256") != _sha256_text(new_charter):
        problems.append("charter_sha256_not_body_bound")
    if not isinstance(capsule, dict):
        problems.append("invariant_capsule_missing_after_correction")
    else:
        if capsule.get("charter_sha256") != revised.get("charter_sha256"):
            problems.append("corrected_capsule_charter_sha256_mismatch")
        if revised.get("invariant_capsule_sha256") != _canonical_sha256(capsule):
            problems.append("corrected_capsule_sha256_mismatch")
    if revised.get("charter_revision") != revised.get("semantic_epoch"):
        problems.append("corrected_epoch_revision_mismatch")
    if problems:
        raise AssertionError("F-RED-002_CORRECTION_BINDING_MISSING " + ";".join(problems))


def _semantic_context() -> dict[str, object]:
    return {
        "authority_revision": 3,
        "authority_sha256": _digest("authority-v3"),
        "plan_revision": 7,
        "plan_sha256": _digest("plan-v7"),
        "plan_cursor": "phase1/rc2/checkpoint",
        "git_fingerprint": _digest("git-worktree-state"),
        "recovery_checkpoint_id": "recovery-fixture-001",
        "shiguan_revision": 0,
        "shiguan_fingerprint": _digest("synthetic-shiguan-none"),
    }


def _semantic_args(
    task_id: str,
    trigger: str,
    *,
    context: dict[str, object] | None = None,
) -> Namespace:
    return Namespace(
        task_id=task_id,
        semantic_context=context or _semantic_context(),
        semantic_context_file=None,
        trigger=trigger,
        actor="taizi",
        evidence=f"semantic {trigger} fixture",
        note=f"semantic {trigger}",
    )


def check_checkpoint_verify_promotes_dispatchable() -> None:
    task_id = "semantic-checkpoint-verify"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            created = court_runtime.create_task(_create_args(task_id, "checkpoint charter"))
            if created.task.get("semantic_state") != "UNVERIFIED":
                raise AssertionError("SEMANTIC_INITIAL_STATE_NOT_UNVERIFIED")
            checkpointed = court_runtime.semantic_checkpoint_task(
                _semantic_args(task_id, "checkpoint")
            )
            verified = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "verify")
            )
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    receipt = checkpointed.task.get("semantic_receipt")
    problems: list[str] = []
    if checkpointed.task.get("semantic_state") != "VERIFIED":
        problems.append("checkpoint_not_verified")
    if not isinstance(receipt, dict):
        problems.append("semantic_receipt_missing")
    else:
        required = {
            "schema",
            "checkpoint_id",
            "task_id",
            "semantic_epoch",
            "charter_sha256",
            "invariant_capsule_sha256",
            "authority_revision",
            "authority_sha256",
            "plan_revision",
            "plan_sha256",
            "plan_cursor",
            "git_fingerprint",
            "recovery_checkpoint_id",
            "shiguan_revision",
            "shiguan_fingerprint",
            "write_set_sha256",
            "event_head_sha256",
            "trigger",
            "gate",
            "verdict",
            "reason_codes",
            "created_at",
        }
        missing = sorted(required - set(receipt))
        if missing:
            problems.append("semantic_receipt_fields_missing:" + ",".join(missing))
        for field, value in _semantic_context().items():
            if receipt.get(field) != value:
                problems.append(f"semantic_context_not_separate:{field}")
    if verified.task.get("semantic_state") != "DISPATCHABLE":
        problems.append("verify_not_dispatchable")
    if verified.task.get("charter_revision") != verified.task.get("semantic_epoch"):
        problems.append("verify_epoch_revision_mismatch")
    if problems:
        raise AssertionError("SEMANTIC_CHECKPOINT_VERIFY_MISSING " + ";".join(problems))


def check_drift_is_quarantined_before_mutation() -> None:
    task_id = "semantic-drift-quarantine"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "drift charter"))
            court_runtime.semantic_checkpoint_task(_semantic_args(task_id, "checkpoint"))
            court_runtime.semantic_verify_task(_semantic_args(task_id, "verify"))
            drifted_context = _semantic_context()
            drifted_context["plan_cursor"] = "phase1/rc2/unapproved-drift"
            try:
                court_runtime.semantic_verify_task(
                    _semantic_args(task_id, "pre-mutation", context=drifted_context)
                )
            except ValueError as exc:
                if not str(exc).startswith("semantic_drift_quarantined:"):
                    raise AssertionError("SEMANTIC_DRIFT_WRONG_ERROR " + str(exc)) from exc
            else:
                raise AssertionError("SEMANTIC_DRIFT_MUTATION_NOT_BLOCKED")
            task = court_runtime.load_tasks()[task_id]
            events = court_runtime.events_for_task(task_id)
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    receipt = task.get("semantic_receipt")
    problems: list[str] = []
    if task.get("semantic_state") != "QUARANTINED":
        problems.append("drift_not_quarantined")
    if not isinstance(receipt, dict) or receipt.get("verdict") != "QUARANTINED":
        problems.append("quarantine_receipt_missing")
    elif "semantic_receipt_mismatch:plan_cursor" not in receipt.get("reason_codes", []):
        problems.append("quarantine_reason_missing")
    if not events or events[-1].get("action") != "semantic_quarantine":
        problems.append("quarantine_event_missing")
    if problems:
        raise AssertionError("SEMANTIC_DRIFT_QUARANTINE_MISSING " + ";".join(problems))


def _dispatch_binding_fixture(task_id: str) -> tuple[dict[str, object], dict[str, object]]:
    preload_hashes = court_runtime._semantic_preload_hashes("gongbu")
    binding: dict[str, object] = {
        "role": "gongbu",
        "instance_id": "gongbu#0001",
        "shard_id": "semantic-binding-shard-0001",
        "direct_superior": "shangshu",
        "instance_kind": "office",
        "canonical_authority": True,
        "owner_role": None,
        "worktree": ".",
        "write_set": ["scripts/court_semantic_continuity.py"],
        "access_mode": "read_write",
        "read_scope": ["scripts/court_semantic_continuity.py"],
        "mutation_allowed": True,
        "integration_authority": False,
        "preload_hashes": preload_hashes,
    }
    budget_id = f"budget:{task_id}:semantic-binding"
    lease: dict[str, object] = {
        "schema": "court.agent.admission_lease.v2",
        "budget_id": budget_id,
        "status": "ACTIVE",
        "lease_id": f"{task_id}-lease-0001",
        "parent_budget_id": f"{budget_id}:taizi",
        "parent_id": "taizi",
        "approved_by": "taizi",
        "grantee_role": "shangshu",
        "lease_depth": 1,
        "approved_next_depth": 2,
        "expires_at_utc": "2099-01-01T00:00:00+00:00",
        "parent_write_scope": ["scripts/court_semantic_continuity.py"],
        "approved_count": 1,
        "task_id": task_id,
        "calling_office": "shangshu",
        "direct_superior": "taizi",
        "integration_domain": "semantic-binding",
        "authority": "super",
        "approved_roles": ["gongbu"],
        "approved_instance_ids": ["gongbu#0001"],
        "approved_shards": ["semantic-binding-shard-0001"],
        "approved_write_sets": {"gongbu#0001": list(binding["write_set"])},
        "approved_access_contracts": {
            "gongbu#0001": {
                "access_mode": "read_write",
                "read_scope": list(binding["read_scope"]),
                "mutation_allowed": True,
                "integration_authority": False,
            }
        },
        "approved_instance_shapes": {
            "gongbu#0001": {
                "instance_kind": "office",
                "canonical_authority": True,
                "owner_role": None,
                "direct_superior": "shangshu",
            }
        },
        "approved_preload_hashes": {"gongbu#0001": preload_hashes},
    }
    return lease, binding


def _admit_args(task: dict[str, object]) -> Namespace:
    task_id = str(task["task_id"])
    lease, binding = _dispatch_binding_fixture(task_id)
    receipt = task["semantic_receipt"]
    return court_runtime.build_parser().parse_args(
        [
            "agent-admit",
            "--task-id", task_id,
            "--expected-semantic-epoch", str(task["semantic_epoch"]),
            "--expected-charter-sha256", str(task["charter_sha256"]),
            "--expected-invariant-capsule-sha256",
            str(task["invariant_capsule_sha256"]),
            "--expected-checkpoint-id", str(receipt["checkpoint_id"]),
            "--wave-id", "semantic-binding-wave",
            "--execution-topology", "parallel",
            "--protocol-mode", "v2",
            "--active-session-protocol", "v2",
            "--requested-fork-turns", "none",
            "--context-tokens", "1000",
            "--message-chars", "100",
            "--requested-agents", "1",
            "--requested-roles", "gongbu",
            "--host-active-agents", "1",
            "--host-capacity", "16",
            "--host-retained-agents", "0",
            "--host-reclamation-status", "verified",
            "--next-depth", "2",
            "--max-depth", "4",
            "--max-threads", "16",
            "--budget-lease-json", json.dumps(lease, ensure_ascii=False),
            "--requested-bindings-json", json.dumps([binding], ensure_ascii=False),
            "--integration-domain", "semantic-binding",
            "--authority", "super",
            "--calling-office", "shangshu",
            "--direct-superior", "taizi",
            "--assignment", "semantic binding tracer",
            "--task-focus", "runtime admission binding",
            "--complexity", "medium",
            "--risk", "low",
            "--ambiguity", "low",
            "--transport", "codex",
            "--evidence", "semantic admission fixture",
        ]
    )


def _start_args(task: dict[str, object], admission: dict[str, object]) -> Namespace:
    skill_path = Path(court_runtime.__file__).resolve().parents[2] / "SKILL.md"
    skill_hash = hashlib.sha256(skill_path.read_bytes()).hexdigest()
    args = court_runtime.build_parser().parse_args(
        [
            "agent-start",
            "--task-id", str(task["task_id"]),
            "--semantic-epoch", str(admission["semantic_epoch"]),
            "--charter-sha256", str(admission["charter_sha256"]),
            "--invariant-capsule-sha256",
            str(admission["invariant_capsule_sha256"]),
            "--checkpoint-id", str(admission["checkpoint_id"]),
            "--dispatch-uid", str(admission["dispatch_uid"]),
            "--attempt", str(admission["attempt"]),
            "--agent-id", "gongbu-semantic-0001",
            "--instance-id", "gongbu#0001",
            "--role", "gongbu",
            "--collaboration-task-name", "gongbu_semantic_binding_01",
            "--skill-requirements-json",
            json.dumps(
                [
                    {
                        "name": "decretum-matrix",
                        "source": str(skill_path),
                        "sha256": skill_hash,
                        "purpose": "semantic binding tracer",
                        "ack_name": "decretum-matrix",
                        "ack_sha256": skill_hash,
                    }
                ]
            ),
            "--scope", "semantic binding tracer",
            "--task-focus", "runtime admission binding",
            "--complexity", "medium",
            "--risk", "low",
            "--ambiguity", "low",
            "--transport", "codex",
            "--wave-id", "semantic-binding-wave",
            "--dispatch-requested-at", str(admission["dispatch_requested_at"]),
            "--fork-turns", "none",
            "--context-tokens", "1000",
            "--actor", "shangshu",
            "--evidence", "semantic start fixture",
        ]
    )
    return args


def check_dispatch_start_report_bind_current_receipt() -> None:
    task_id = "semantic-dispatch-binding"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "dispatch charter"))
            court_runtime.semantic_checkpoint_task(_semantic_args(task_id, "checkpoint"))
            dispatchable = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "verify")
            ).task
            admission = court_runtime.agent_admit(_admit_args(dispatchable))
            started = court_runtime.agent_start(_start_args(dispatchable, admission)).task
            _ack_semantic_agent(task_id, "gongbu-semantic-0001")
            report_args = Namespace(
                task_id=task_id,
                agent_id="gongbu-semantic-0001",
                role="gongbu",
                actor="shangshu",
                evidence="semantic report fixture",
                note="semantic report",
                dispatch_uid=admission["dispatch_uid"],
                attempt=admission["attempt"],
                semantic_epoch=admission["semantic_epoch"],
                charter_sha256=admission["charter_sha256"],
                invariant_capsule_sha256=admission["invariant_capsule_sha256"],
                checkpoint_id=admission["checkpoint_id"],
            )
            reported = court_runtime.agent_report(report_args)
            report_args.attempt = int(admission["attempt"]) + 1
            try:
                court_runtime.agent_report(report_args)
            except ValueError as exc:
                if str(exc) != "agent_semantic_binding_mismatch:attempt":
                    raise AssertionError("AGENT_BINDING_WRONG_ERROR " + str(exc)) from exc
            else:
                raise AssertionError("AGENT_BINDING_STALE_ATTEMPT_ACCEPTED")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    selected = admission.get("selected_bindings")
    binding = selected[0] if isinstance(selected, (list, tuple)) and selected else None
    agent = started.get("agents", {}).get("gongbu-semantic-0001")
    problems: list[str] = []
    required = {
        "task_id",
        "semantic_epoch",
        "charter_sha256",
        "invariant_capsule_sha256",
        "checkpoint_id",
        "dispatch_uid",
        "attempt",
        "office_instance_id",
        "role",
        "direct_superior",
        "worktree",
        "write_set",
        "lease_id",
        "preload_hashes",
    }
    if not isinstance(binding, dict):
        problems.append("dispatch_binding_missing")
    else:
        missing = sorted(required - set(binding))
        if missing:
            problems.append("dispatch_binding_fields_missing:" + ",".join(missing))
    if not isinstance(agent, dict):
        problems.append("started_agent_missing")
    else:
        for field in required - {"preload_hashes"}:
            if binding is not None and agent.get(field) != binding.get(field):
                problems.append(f"start_binding_mismatch:{field}")
    if reported.event.get("dispatch_uid") != admission.get("dispatch_uid"):
        problems.append("report_event_dispatch_uid_missing")
    if problems:
        raise AssertionError("SEMANTIC_AGENT_BINDING_MISSING " + ";".join(problems))


def _ack_semantic_agent(task_id: str, agent_id: str) -> None:
    record = court_runtime.load_tasks()[task_id]["agents"][agent_id]
    manifest = record["preload_manifest"]
    court_runtime.agent_preload_ack(
        Namespace(
            task_id=task_id,
            agent_id=agent_id,
            role="gongbu",
            office_zh="",
            direct_superior=manifest["direct_superior"],
            profile_hash=manifest["profile_hash"],
            dossier_hash=manifest["dossier_hash"],
            court_skill_hash=manifest["court_skill_hash"],
            loaded_skills="decretum-matrix,tdd",
            agent_dossier_loaded="YES",
            model_route_id=record["model_route"]["model_route_id"],
            active_model="",
            active_reasoning_effort="",
            model_override_applied="NO",
            inheritance_policy=record["model_route"]["inheritance_policy"],
            schema=manifest["preload_ack_schema"],
            preload_status="PASSED",
            actor="shangshu",
            evidence=f"ack {agent_id}",
            note="semantic result fixture",
        )
    )


def _result_envelope(
    agent: dict[str, object],
    *,
    attempt: int | None = None,
) -> dict[str, object]:
    write_set = agent.get("write_set")
    envelope = {
        "schema": "court.office.result.v1",
        "task_id": agent["task_id"],
        "semantic_epoch": agent["semantic_epoch"],
        "charter_sha256": agent["charter_sha256"],
        "invariant_capsule_sha256": agent["invariant_capsule_sha256"],
        "checkpoint_id": agent["checkpoint_id"],
        "dispatch_uid": agent["dispatch_uid"],
        "attempt": agent["attempt"] if attempt is None else attempt,
        "office_instance_id": agent["office_instance_id"],
        "agent_id": agent["agent_id"],
        "role": agent["role"],
        "direct_superior": agent["direct_superior"],
        "worktree": agent["worktree"],
        "write_set_sha256": _canonical_sha256(write_set),
        "status": "completed",
        "summary": "bounded structured result",
        "evidence": ["synthetic-result-pointer"],
        "produced_at": "2026-07-16T00:00:00+00:00",
    }
    if agent.get("office_instance_kind") and agent.get("carrier_proof"):
        envelope["office_instance_kind"] = agent["office_instance_kind"]
        envelope["carrier_proof"] = dict(agent["carrier_proof"])
    return envelope


def _finish_args(
    task_id: str,
    agent: dict[str, object],
    *,
    envelope: dict[str, object] | None,
    free_text: str = "",
) -> Namespace:
    return Namespace(
        task_id=task_id,
        agent_id=agent["agent_id"],
        role=agent["role"],
        status="completed",
        result=free_text,
        result_envelope=envelope,
        result_envelope_file=None,
        actor="shangshu",
        evidence="semantic finish fixture",
        note="semantic finish",
        dispatch_uid=agent["dispatch_uid"],
        attempt=agent["attempt"],
        semantic_epoch=agent["semantic_epoch"],
        charter_sha256=agent["charter_sha256"],
        invariant_capsule_sha256=agent["invariant_capsule_sha256"],
        checkpoint_id=agent["checkpoint_id"],
    )


def check_finish_requires_structured_result_and_quarantines_stale() -> None:
    task_id = "semantic-finish-envelope"
    agent_id = "gongbu-semantic-finish-0001"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "finish charter"))
            court_runtime.semantic_checkpoint_task(_semantic_args(task_id, "checkpoint"))
            dispatchable = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "verify")
            ).task
            admission = court_runtime.agent_admit(_admit_args(dispatchable))
            start_args = _start_args(dispatchable, admission)
            start_args.agent_id = agent_id
            court_runtime.agent_start(start_args)
            _ack_semantic_agent(task_id, agent_id)
            agent = court_runtime.load_tasks()[task_id]["agents"][agent_id]
            before = court_runtime.tasks_path().read_bytes()
            try:
                court_runtime.agent_finish(
                    _finish_args(task_id, agent, envelope=None, free_text="free text bypass")
                )
            except ValueError as exc:
                if str(exc) != "structured_result_envelope_required":
                    raise AssertionError("FREE_TEXT_RESULT_WRONG_ERROR " + str(exc)) from exc
            else:
                raise AssertionError("FREE_TEXT_RESULT_BYPASS_ACCEPTED")
            if court_runtime.tasks_path().read_bytes() != before:
                raise AssertionError("FREE_TEXT_RESULT_MUTATED_TASK")

            stale = _result_envelope(agent, attempt=int(agent["attempt"]) + 1)
            quarantined = court_runtime.agent_finish(
                _finish_args(task_id, agent, envelope=stale)
            )
            current_after_quarantine = quarantined.task["agents"][agent_id]
            if (
                current_after_quarantine.get("status") != "failed"
                or current_after_quarantine.get("final_status") != "failed"
                or current_after_quarantine.get("release_status") != "closed"
                or current_after_quarantine.get("result_state") != "QUARANTINED"
                or current_after_quarantine.get("office_execution_ready") is not False
            ):
                raise AssertionError("STALE_RESULT_SOURCE_NOT_TERMINALIZED")

            valid = _result_envelope(agent)
            try:
                court_runtime.agent_finish(_finish_args(task_id, agent, envelope=valid))
            except ValueError as exc:
                if str(exc) != "terminal agent cannot accept lifecycle events":
                    raise AssertionError("QUARANTINED_SOURCE_WRONG_FINISH_ERROR " + str(exc)) from exc
            else:
                raise AssertionError("QUARANTINED_SOURCE_FINISH_ACCEPTED")
            finished = quarantined.task
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    quarantine = finished.get("quarantined_results")
    final_agent = finished.get("agents", {}).get(agent_id)
    problems: list[str] = []
    if not isinstance(quarantine, list) or len(quarantine) != 1:
        problems.append("stale_result_quarantine_missing")
    else:
        entry = quarantine[0]
        if "agent_result_binding_mismatch:attempt" not in entry.get("reason_codes", []):
            problems.append("stale_result_reason_missing")
        if not entry.get("payload_sha256"):
            problems.append("stale_result_payload_hash_missing")
        if any(field in entry for field in ("summary", "evidence", "result", "body")):
            problems.append("stale_result_body_persisted")
    if not isinstance(final_agent, dict) or final_agent.get("result_state") != "QUARANTINED":
        problems.append("quarantined_source_state_not_persisted")
    elif "result_envelope" in final_agent:
        problems.append("quarantined_source_result_envelope_persisted")
    if problems:
        raise AssertionError("SEMANTIC_RESULT_ENVELOPE_MISSING " + ";".join(problems))


def check_correction_invalidates_all_derived_state_append_only() -> None:
    task_id = "semantic-correction-invalidation"
    old_charter = "correction invalidation old charter"
    new_charter = "correction invalidation new charter"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            created = court_runtime.create_task(_create_args(task_id, old_charter)).task
            court_runtime.semantic_checkpoint_task(_semantic_args(task_id, "checkpoint"))
            dispatchable = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "verify")
            ).task
            admission = court_runtime.agent_admit(_admit_args(dispatchable))
            start_args = _start_args(dispatchable, admission)
            start_args.agent_id = "gongbu-correction-0001"
            court_runtime.agent_start(start_args)
            tasks = court_runtime.load_tasks()
            seeded = tasks[task_id]
            seeded.update(
                outcome_assessment={
                    "schema": "court.outcome_assessment.v1",
                    "gate": "PASSED",
                    "reasons": [],
                    "outcome": {"status": "STALE"},
                },
                assessment_binding={"status": "VERIFIED"},
                shiguan_checkpoint={"status": "VERIFIED"},
                completion={"status": "READY"},
                dispatch_plan={"status": "ACTIVE", "dispatch_uid": admission["dispatch_uid"]},
                task_point_capsules=[
                    {"capsule_id": "TPC-OLD", "status": "ACTIVE", "attempt": 1}
                ],
            )
            old_capsule_sha256 = seeded["invariant_capsule_sha256"]
            court_runtime.write_tasks(tasks)
            revised = court_runtime.revise_charter_task(
                _revise_args(task_id, old_charter=old_charter, new_charter=new_charter)
            ).task
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    problems: list[str] = []
    if revised.get("state") != "ThreeDepartments":
        problems.append("correction_not_returned_to_three_departments")
    if revised.get("semantic_state") != "REVERIFY":
        problems.append("correction_not_in_reverify")
    state_history = revised.get("semantic_state_history")
    if not isinstance(state_history, list) or [
        item.get("state") for item in state_history[-2:] if isinstance(item, dict)
    ] != ["CORRECTED", "REVERIFY"]:
        problems.append("corrected_reverify_history_missing")
    invalidations = revised.get("semantic_invalidations")
    if not isinstance(invalidations, list) or len(invalidations) != 1:
        problems.append("append_only_invalidation_record_missing")
    else:
        snapshot = invalidations[0]
        required_snapshot = {
            "outcome_assessment",
            "assessment_binding",
            "shiguan_checkpoint",
            "completion",
            "dispatch_plan",
            "agent_admissions",
            "agents",
            "invariant_capsule",
            "semantic_dispatch_attempts",
            "task_point_capsules",
        }
        missing = sorted(required_snapshot - set(snapshot))
        if missing:
            problems.append("invalidation_snapshot_fields_missing:" + ",".join(missing))
        if snapshot.get("invariant_capsule_sha256") != old_capsule_sha256:
            problems.append("old_capsule_not_preserved")
    if revised.get("outcome_assessment", {}).get("gate") != "UNASSESSED":
        problems.append("assessment_not_invalidated")
    if revised.get("assessment_binding") not in ({}, None):
        problems.append("assessment_binding_not_invalidated")
    if revised.get("shiguan_checkpoint") not in ({}, None):
        problems.append("checkpoint_not_invalidated")
    if not str(revised.get("completion", {}).get("status") or "").startswith("INVALIDATED"):
        problems.append("completion_not_invalidated")
    if not str(revised.get("dispatch_plan", {}).get("status") or "").startswith("INVALIDATED"):
        problems.append("dispatch_not_invalidated")
    admissions = revised.get("agent_admissions")
    if not isinstance(admissions, dict) or any(
        not str(record.get("status") or "").startswith("INVALIDATED")
        for record in admissions.values()
        if isinstance(record, dict)
    ):
        problems.append("admission_not_invalidated")
    agents = revised.get("agents")
    if not isinstance(agents, dict) or any(
        not record.get("assignment_invalidated_by_charter_revision")
        for record in agents.values()
        if isinstance(record, dict)
    ):
        problems.append("active_agent_not_invalidated")
    attempts = revised.get("semantic_dispatch_attempts")
    if not isinstance(attempts, list) or any(
        not str(record.get("status") or "").startswith("INVALIDATED")
        for record in attempts
        if isinstance(record, dict)
    ):
        problems.append("attempt_not_invalidated")
    capsules = revised.get("task_point_capsules")
    if not isinstance(capsules, list) or any(
        not str(record.get("status") or "").startswith("INVALIDATED")
        for record in capsules
        if isinstance(record, dict)
    ):
        problems.append("task_point_capsule_not_invalidated")
    if problems:
        raise AssertionError("SEMANTIC_CORRECTION_INVALIDATION_MISSING " + ";".join(problems))


def _resume_args(
    task: dict[str, object],
    *,
    expected_epoch: int,
    to_state: str,
    context: dict[str, object],
) -> Namespace:
    receipt = task["semantic_receipt"]
    return Namespace(
        task_id=task["task_id"],
        continuation_gate=_continuation_gate_fixture(str(task["task_id"])),
        continuation_file=None,
        expected_semantic_epoch=expected_epoch,
        expected_charter_sha256=task["charter_sha256"],
        expected_invariant_capsule_sha256=task["invariant_capsule_sha256"],
        expected_checkpoint_id=receipt["checkpoint_id"],
        semantic_context=context,
        semantic_context_file=None,
        to_state=to_state,
        trigger="resume",
        actor="taizi",
        evidence="semantic resume fixture",
        note="semantic resume",
    )


def check_semantic_resume_preserves_epoch_and_requires_reverify() -> None:
    task_id = "semantic-resume"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "resume charter"))
            court_runtime.semantic_checkpoint_task(_semantic_args(task_id, "checkpoint"))
            dispatchable = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "verify")
            ).task
            tasks = court_runtime.load_tasks()
            tasks[task_id]["state"] = "Paused"
            tasks[task_id]["paused_from"] = "SixMinistries"
            court_runtime.write_tasks(tasks)
            paused = court_runtime.load_tasks()[task_id]
            authority_context = _semantic_context()
            authority_context["authority_revision"] = 4
            authority_context["authority_sha256"] = _digest("authority-v4")
            before = court_runtime.tasks_path().read_bytes()
            try:
                court_runtime.semantic_resume_task(
                    _resume_args(
                        paused,
                        expected_epoch=int(paused["semantic_epoch"]) - 1,
                        to_state="ThreeDepartments",
                        context=authority_context,
                    )
                )
            except ValueError as exc:
                if str(exc) != "stale_semantic_epoch":
                    raise AssertionError("SEMANTIC_RESUME_STALE_WRONG_ERROR " + str(exc)) from exc
            else:
                raise AssertionError("SEMANTIC_RESUME_STALE_EPOCH_ACCEPTED")
            if court_runtime.tasks_path().read_bytes() != before:
                raise AssertionError("SEMANTIC_RESUME_STALE_MUTATED_TASK")
            try:
                court_runtime.semantic_resume_task(
                    _resume_args(
                        paused,
                        expected_epoch=int(paused["semantic_epoch"]),
                        to_state="SixMinistries",
                        context=authority_context,
                    )
                )
            except ValueError as exc:
                if str(exc) != "semantic_resume_requires_three_departments":
                    raise AssertionError("SEMANTIC_RESUME_JUMP_WRONG_ERROR " + str(exc)) from exc
            else:
                raise AssertionError("SEMANTIC_RESUME_DIRECT_EXECUTION_ACCEPTED")
            resumed = court_runtime.semantic_resume_task(
                _resume_args(
                    paused,
                    expected_epoch=int(paused["semantic_epoch"]),
                    to_state="ThreeDepartments",
                    context=authority_context,
                )
            ).task
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    problems: list[str] = []
    if resumed.get("task_id") != task_id:
        problems.append("resume_created_second_task")
    if resumed.get("semantic_epoch") != dispatchable.get("semantic_epoch"):
        problems.append("authority_change_incremented_semantic_epoch")
    if resumed.get("charter_revision") != resumed.get("semantic_epoch"):
        problems.append("resume_epoch_revision_mismatch")
    if resumed.get("state") != "ThreeDepartments":
        problems.append("resume_not_returned_to_three_departments")
    if resumed.get("semantic_state") != "REVERIFY":
        problems.append("resume_not_marked_reverify")
    context = resumed.get("semantic_context")
    if not isinstance(context, dict) or context.get("authority_revision") != 4:
        problems.append("authority_revision_not_updated_separately")
    if resumed.get("semantic_receipt", {}).get("verdict") != "REVERIFY":
        problems.append("resume_receipt_not_reverify")
    if problems:
        raise AssertionError("SEMANTIC_RESUME_MISSING " + ";".join(problems))


def check_compaction_reboot_idle_reuse_immutable_receipt() -> None:
    task_id = "semantic-restore-triggers"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "restore trigger charter"))
            checkpointed = court_runtime.semantic_checkpoint_task(
                _semantic_args(task_id, "checkpoint")
            ).task
            checkpoint_receipt = checkpointed["semantic_receipt"]
            checkpoint_id = str(checkpoint_receipt["checkpoint_id"])
            receipt_sha256 = _canonical_sha256(checkpoint_receipt)
            dispatchable = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "verify")
            ).task
            capsule_sha256 = str(dispatchable["invariant_capsule_sha256"])
            current = dispatchable
            for trigger in ("compaction", "reboot", "long-idle"):
                current = court_runtime.semantic_verify_task(
                    _semantic_args(task_id, trigger)
                ).task
                frozen = court_runtime.semantic_receipt_by_checkpoint_id(
                    current,
                    checkpoint_id,
                )
                if _canonical_sha256(frozen) != receipt_sha256:
                    raise AssertionError(f"SEMANTIC_CHECKPOINT_RECEIPT_REWRITTEN:{trigger}")
                if current.get("invariant_capsule_sha256") != capsule_sha256:
                    raise AssertionError(f"INVARIANT_CAPSULE_REWRITTEN:{trigger}")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    verifications = current.get("semantic_verifications")
    triggers = [
        item.get("trigger")
        for item in verifications or []
        if isinstance(item, dict)
    ]
    if triggers[-3:] != ["compaction", "reboot", "long-idle"]:
        raise AssertionError("SEMANTIC_RESTORE_VERIFICATION_HISTORY_MISSING")


def check_incomplete_capsule_and_multisource_drift_fail_closed() -> None:
    incomplete_task_id = "semantic-incomplete-capsule"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            incomplete_args = _create_args(incomplete_task_id, "incomplete capsule charter")
            incomplete_capsule = dict(incomplete_args.invariant_capsule)
            for field in ("non_goals", "forbidden_actions", "acceptance", "write_set"):
                incomplete_capsule[field] = []
            incomplete_capsule["governing_hashes"] = {}
            incomplete_args.invariant_capsule = incomplete_capsule
            court_runtime.create_task(incomplete_args)
            before = court_runtime.tasks_path().read_bytes()
            try:
                court_runtime.semantic_checkpoint_task(
                    _semantic_args(incomplete_task_id, "checkpoint")
                )
            except ValueError as exc:
                error = str(exc)
                required_reasons = (
                    "invariant_capsule_empty:non_goals",
                    "invariant_capsule_empty:forbidden_actions",
                    "invariant_capsule_empty:acceptance",
                    "invariant_capsule_empty:write_set",
                    "invariant_capsule_empty:governing_hashes",
                )
                if not error.startswith("semantic_binding_drift:") or any(
                    reason not in error for reason in required_reasons
                ):
                    raise AssertionError("INCOMPLETE_CAPSULE_WRONG_ERROR " + error) from exc
            else:
                raise AssertionError("INCOMPLETE_CAPSULE_CHECKPOINT_ACCEPTED")
            if court_runtime.tasks_path().read_bytes() != before:
                raise AssertionError("INCOMPLETE_CAPSULE_MUTATED_TASK")

            drift_task_id = "semantic-multisource-drift"
            court_runtime.create_task(_create_args(drift_task_id, "multisource drift charter"))
            court_runtime.semantic_checkpoint_task(
                _semantic_args(drift_task_id, "checkpoint")
            )
            court_runtime.semantic_verify_task(_semantic_args(drift_task_id, "verify"))
            drifted_context = _semantic_context()
            drifted_context["git_fingerprint"] = _digest("different-git")
            drifted_context["recovery_checkpoint_id"] = "different-recovery"
            drifted_context["shiguan_fingerprint"] = _digest("different-shiguan")
            try:
                court_runtime.semantic_verify_task(
                    _semantic_args(
                        drift_task_id,
                        "pre-mutation",
                        context=drifted_context,
                    )
                )
            except ValueError as exc:
                if not str(exc).startswith("semantic_drift_quarantined:"):
                    raise AssertionError("MULTISOURCE_DRIFT_WRONG_ERROR " + str(exc)) from exc
            else:
                raise AssertionError("MULTISOURCE_DRIFT_ACCEPTED")
            drifted = court_runtime.load_tasks()[drift_task_id]
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    reason_codes = drifted.get("semantic_receipt", {}).get("reason_codes", [])
    for reason in (
        "semantic_receipt_mismatch:git_fingerprint",
        "semantic_receipt_mismatch:recovery_checkpoint_id",
        "semantic_receipt_mismatch:shiguan_fingerprint",
    ):
        if reason not in reason_codes:
            raise AssertionError("MULTISOURCE_DRIFT_REASON_MISSING:" + reason)


def _operation_args(
    task_id: str,
    operation_id: str,
    payload: dict[str, object],
    *,
    killpoint: str = "",
) -> Namespace:
    return Namespace(
        task_id=task_id,
        operation_id=operation_id,
        payload=payload,
        payload_file=None,
        expected_task_revision=1,
        killpoint=killpoint,
        actor="taizi",
        evidence=f"F-CRASH-003 {operation_id}",
        note="paired ledger crash tracer",
    )


def check_f_crash_003_paired_ledger_recovery_and_replay() -> None:
    task_id = "f-crash-003"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "F-CRASH-003 charter"))
            baseline_tasks = court_runtime.tasks_path().read_bytes()
            baseline_events = court_runtime.events_path().read_bytes()

            rollback_id = "00000000-0000-4000-8000-000000000301"
            rollback_args = _operation_args(
                task_id,
                rollback_id,
                {"action": "rollback-fixture", "value": 1},
                killpoint="after_task_write",
            )
            try:
                court_runtime.apply_synthetic_paired_operation(rollback_args)
            except court_runtime.SimulatedPairedLedgerCrash:
                pass
            else:
                raise AssertionError("F_CRASH_003_TASK_KILLPOINT_DID_NOT_CRASH")
            rollback = court_runtime.recover_paired_operation(rollback_id)
            if rollback.get("outcome") != "ROLLBACK":
                raise AssertionError("F_CRASH_003_TASK_KILLPOINT_NOT_ROLLED_BACK")
            if court_runtime.tasks_path().read_bytes() != baseline_tasks:
                raise AssertionError("F_CRASH_003_TASK_ROLLBACK_MISMATCH")
            if court_runtime.events_path().read_bytes() != baseline_events:
                raise AssertionError("F_CRASH_003_EVENT_ROLLBACK_MISMATCH")

            finalize_id = "00000000-0000-4000-8000-000000000302"
            finalize_payload = {"action": "finalize-fixture", "value": 2}
            finalize_args = _operation_args(
                task_id,
                finalize_id,
                finalize_payload,
                killpoint="after_event_write",
            )
            try:
                court_runtime.apply_synthetic_paired_operation(finalize_args)
            except court_runtime.SimulatedPairedLedgerCrash:
                pass
            else:
                raise AssertionError("F_CRASH_003_EVENT_KILLPOINT_DID_NOT_CRASH")
            finalized = court_runtime.recover_paired_operation(finalize_id)
            if finalized.get("outcome") != "FINALIZE":
                raise AssertionError("F_CRASH_003_EVENT_KILLPOINT_NOT_FINALIZED")
            task_after_finalize = court_runtime.load_tasks()[task_id]
            operation = task_after_finalize.get("operations", {}).get(finalize_id)
            if not isinstance(operation, dict):
                raise AssertionError("F_CRASH_003_OPERATION_NOT_IN_TASK_AUTHORITY")
            operation_events_before = [
                event
                for event in court_runtime.events_for_task(task_id)
                if event.get("operation_id") == finalize_id
            ]
            replay = court_runtime.apply_synthetic_paired_operation(
                _operation_args(task_id, finalize_id, finalize_payload)
            )
            operation_events_after = [
                event
                for event in court_runtime.events_for_task(task_id)
                if event.get("operation_id") == finalize_id
            ]
            if replay.get("receipt") != operation.get("receipt"):
                raise AssertionError("F_CRASH_003_REPLAY_DID_NOT_RETURN_RECEIPT")
            if len(operation_events_after) != len(operation_events_before):
                raise AssertionError("F_CRASH_003_REPLAY_DUPLICATED_EVENT")
            before_conflict = court_runtime.tasks_path().read_bytes()
            try:
                court_runtime.apply_synthetic_paired_operation(
                    _operation_args(
                        task_id,
                        finalize_id,
                        {"action": "different-payload", "value": 3},
                    )
                )
            except ValueError as exc:
                if str(exc) != "operation_payload_conflict":
                    raise AssertionError("F_CRASH_003_CONFLICT_WRONG_ERROR " + str(exc)) from exc
            else:
                raise AssertionError("F_CRASH_003_CONFLICT_ACCEPTED")
            if court_runtime.tasks_path().read_bytes() != before_conflict:
                raise AssertionError("F_CRASH_003_CONFLICT_MUTATED_TASK")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_legacy_v2_v3_are_diagnostic_only_until_semantically_bound() -> None:
    legacy_tasks = {
        "legacy-v2": {
            "runtime_schema_version": 2,
            "task_id": "legacy-v2",
            "title": "legacy v2 diagnostic fixture",
            "charter": "legacy v2 charter",
            "state": "Pending",
            "owner": "taizi",
            "heartbeat": "legacy",
            "last_evidence": "legacy v2 fixture",
        },
        "legacy-v3": {
            "runtime_schema_version": 3,
            "task_id": "legacy-v3",
            "title": "legacy v3 diagnostic fixture",
            "charter": "legacy v3 charter",
            "state": "Pending",
            "owner": "taizi",
            "heartbeat": "legacy",
            "last_evidence": "legacy v3 fixture",
        },
    }
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.ensure_runtime_root()
            court_runtime.atomic_write_text(
                court_runtime.tasks_path(),
                json.dumps(legacy_tasks, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
            before = court_runtime.tasks_path().read_bytes()
            listed = court_runtime.list_tasks(Namespace(state="", limit=10))
            status = court_runtime.status_payload(Namespace(limit=10))
            if {str(task.get("task_id")) for task in listed} != set(legacy_tasks):
                raise AssertionError("LEGACY_DIAGNOSTIC_LIST_INCOMPLETE")
            if "legacy-v2" not in str(status.get("dashboard")):
                raise AssertionError("LEGACY_DIAGNOSTIC_STATUS_INCOMPLETE")
            if court_runtime.tasks_path().read_bytes() != before:
                raise AssertionError("LEGACY_DIAGNOSTIC_READ_MUTATED_LEDGER")

            for task_id in legacy_tasks:
                try:
                    court_runtime.update_heartbeat(
                        Namespace(
                            task_id=task_id,
                            heartbeat="must-not-write",
                            actor="taizi",
                            evidence="legacy mutation tracer",
                            note="",
                        )
                    )
                except ValueError as exc:
                    if not str(exc).startswith("legacy_semantic_binding_read_only:"):
                        raise AssertionError(
                            f"LEGACY_MUTATION_WRONG_ERROR:{task_id}:{exc}"
                        ) from exc
                else:
                    raise AssertionError(f"LEGACY_MUTATION_ACCEPTED:{task_id}")

            try:
                court_runtime.agent_admit(
                    Namespace(
                        task_id="legacy-v3",
                        wave_id="legacy-wave",
                        evidence="legacy dispatch tracer",
                        actor="shangshu",
                        note="",
                    )
                )
            except ValueError as exc:
                if not str(exc).startswith("legacy_semantic_binding_read_only:"):
                    raise AssertionError("LEGACY_DISPATCH_WRONG_ERROR:" + str(exc)) from exc
            else:
                raise AssertionError("LEGACY_DISPATCH_ACCEPTED")
            if court_runtime.tasks_path().read_bytes() != before:
                raise AssertionError("LEGACY_REJECTED_MUTATION_CHANGED_LEDGER")

            for field in court_runtime.LEGACY_SEMANTIC_BINDING_FIELDS:
                if court_runtime._legacy_semantic_bootstrap(
                    {**legacy_tasks["legacy-v3"], field: None}
                ):
                    raise AssertionError(f"LEGACY_PARTIAL_BINDING_ACCEPTED:{field}")

            def bootstrap_args(task_id: str) -> Namespace:
                old = str(legacy_tasks[task_id]["charter"])
                args = _revise_args(task_id, old_charter=old, new_charter=old + " bound")
                args.expected_revision = 0
                args.new_revision = 1
                return args

            def ledger_bytes():
                return tuple(
                    path.read_bytes() if path.exists() else None
                    for path in (court_runtime.tasks_path(), court_runtime.events_path())
                )

            def rejected(args: Namespace, error_type: type[Exception]) -> None:
                preimage = ledger_bytes()
                try:
                    court_runtime.revise_charter_task(args)
                except error_type:
                    pass
                else:
                    raise AssertionError("LEGACY_REJECT_ACCEPTED")
                if ledger_bytes() != preimage:
                    raise AssertionError("LEGACY_REJECT_MUTATED_LEDGER")

            for field, value in (("expected_revision", 1), ("expected_sha256", "0" * 64)):
                args = bootstrap_args("legacy-v3")
                setattr(args, field, value)
                rejected(args, ValueError)

            original_append_event = court_runtime.append_event
            court_runtime.append_event = lambda _event: (_ for _ in ()).throw(
                RuntimeError("injected append failure")
            )
            try:
                rejected(
                    bootstrap_args("legacy-v2"), RuntimeError
                )
            finally:
                court_runtime.append_event = original_append_event

            for task_id in legacy_tasks:
                revised = court_runtime.revise_charter_task(
                    bootstrap_args(task_id)
                ).task
                if tuple(revised.get(key) for key in (
                    "charter_revision", "semantic_epoch", "semantic_state"
                )) != (1, 1, "REVERIFY"):
                    raise AssertionError(f"LEGACY_BOOTSTRAP_INVALID:{task_id}")
            court_runtime.semantic_checkpoint_task(
                _semantic_args("legacy-v3", "checkpoint")
            )
            if court_runtime.semantic_verify_task(
                _semantic_args("legacy-v3", "verify")
            ).task.get("semantic_state") != "DISPATCHABLE":
                raise AssertionError("LEGACY_BOOTSTRAP_NOT_DISPATCHABLE")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_semantic_checkpoint_cli_is_json_and_machine_stable() -> None:
    task_id = "semantic-cli-checkpoint"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "semantic CLI checkpoint charter"))
            context_path = Path(temp_dir) / "semantic-context.json"
            context_path.write_text(
                json.dumps(_semantic_context(), ensure_ascii=False),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = court_runtime.main(
                        [
                            "semantic",
                            "checkpoint",
                            "--task-id",
                            task_id,
                            "--context-file",
                            str(context_path),
                            "--trigger",
                            "compaction",
                            "--actor",
                            "taizi",
                            "--evidence",
                            "semantic CLI checkpoint tracer",
                            "--note",
                            "checkpoint JSON contract",
                        ]
                    )
            except SystemExit as exc:
                raise AssertionError(
                    f"SEMANTIC_CLI_CHECKPOINT_UNAVAILABLE:{exc.code}:{stderr.getvalue()}"
                ) from exc
            if exit_code != 0:
                raise AssertionError(
                    f"SEMANTIC_CLI_CHECKPOINT_EXIT:{exit_code}:{stderr.getvalue()}"
                )
            try:
                payload = json.loads(stdout.getvalue())
            except json.JSONDecodeError as exc:
                raise AssertionError("SEMANTIC_CLI_CHECKPOINT_NOT_JSON") from exc
            if payload.get("schema") != "court.semantic.cli.v1":
                raise AssertionError("SEMANTIC_CLI_CHECKPOINT_SCHEMA_MISSING")
            if payload.get("ok") is not True or payload.get("command") != "checkpoint":
                raise AssertionError("SEMANTIC_CLI_CHECKPOINT_RECEIPT_INVALID")
            result = payload.get("result")
            if not isinstance(result, dict):
                raise AssertionError("SEMANTIC_CLI_CHECKPOINT_RESULT_MISSING")
            task = result.get("task")
            if not isinstance(task, dict) or task.get("semantic_state") != "VERIFIED":
                raise AssertionError("SEMANTIC_CLI_CHECKPOINT_NOT_VERIFIED")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def _run_runtime_cli(argv: list[str]) -> tuple[int, dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = court_runtime.main(argv)
    except SystemExit as exc:
        raise AssertionError(
            f"SEMANTIC_CLI_UNAVAILABLE:{exc.code}:{stderr.getvalue()}"
        ) from exc
    try:
        payload = json.loads(stdout.getvalue())
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"SEMANTIC_CLI_NOT_JSON:{stdout.getvalue()}:{stderr.getvalue()}"
        ) from exc
    if not isinstance(payload, dict):
        raise AssertionError("SEMANTIC_CLI_PAYLOAD_NOT_OBJECT")
    return exit_code, payload, stderr.getvalue()


def check_semantic_verify_cli_success_and_drift_exit_codes() -> None:
    task_id = "semantic-cli-verify"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "semantic CLI verify charter"))
            context_path = Path(temp_dir) / "semantic-context.json"
            context = _semantic_context()
            context_path.write_text(
                json.dumps(context, ensure_ascii=False),
                encoding="utf-8",
            )
            court_runtime.semantic_checkpoint_task(
                _semantic_args(task_id, "checkpoint", context=context)
            )
            base_args = [
                "semantic",
                "verify",
                "--task-id",
                task_id,
                "--context-file",
                str(context_path),
                "--trigger",
                "reboot",
                "--actor",
                "taizi",
                "--evidence",
                "semantic CLI verify tracer",
            ]
            exit_code, payload, stderr = _run_runtime_cli(base_args)
            if exit_code != 0 or payload.get("ok") is not True:
                raise AssertionError(f"SEMANTIC_CLI_VERIFY_EXIT:{exit_code}:{stderr}")
            if payload.get("command") != "verify":
                raise AssertionError("SEMANTIC_CLI_VERIFY_COMMAND_MISMATCH")

            context["plan_cursor"] = "drifted-plan-cursor"
            context_path.write_text(
                json.dumps(context, ensure_ascii=False),
                encoding="utf-8",
            )
            drift_exit, drift_payload, drift_stderr = _run_runtime_cli(base_args)
            if drift_exit != 2 or drift_payload.get("fail_closed") is not True:
                raise AssertionError(
                    f"SEMANTIC_CLI_DRIFT_EXIT:{drift_exit}:{drift_stderr}"
                )
            if not str(drift_payload.get("error") or "").startswith(
                "semantic_drift_quarantined:"
            ):
                raise AssertionError("SEMANTIC_CLI_DRIFT_ERROR_MISSING")
            task = court_runtime.load_tasks()[task_id]
            if task.get("semantic_state") != "QUARANTINED":
                raise AssertionError("SEMANTIC_CLI_DRIFT_NOT_QUARANTINED")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_semantic_correct_cli_binds_body_and_reverify_state() -> None:
    task_id = "semantic-cli-correct"
    old_charter = "semantic CLI old charter"
    new_charter = "semantic CLI corrected charter body"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, old_charter))
            correction_path = Path(temp_dir) / "correction-gate.json"
            charter_path = Path(temp_dir) / "corrected-charter.txt"
            capsule_path = Path(temp_dir) / "corrected-capsule.json"
            correction_path.write_text(
                json.dumps(_correction_gate_fixture(task_id), ensure_ascii=False),
                encoding="utf-8",
            )
            charter_path.write_text(new_charter, encoding="utf-8")
            capsule_path.write_text(
                json.dumps(
                    _revision_capsule(new_charter, "cli-revision-2"),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            exit_code, payload, stderr = _run_runtime_cli(
                [
                    "semantic",
                    "correct",
                    "--task-id",
                    task_id,
                    "--expected-revision",
                    "1",
                    "--expected-sha256",
                    _sha256_text(old_charter),
                    "--new-revision",
                    "2",
                    "--new-sha256",
                    _sha256_text(new_charter),
                    "--new-charter-file",
                    str(charter_path),
                    "--new-invariant-capsule-file",
                    str(capsule_path),
                    "--correction-file",
                    str(correction_path),
                    "--actor",
                    "taizi",
                    "--evidence",
                    "semantic CLI correction tracer",
                    "--note",
                    "correct command contract",
                ]
            )
            if exit_code != 0 or payload.get("ok") is not True:
                raise AssertionError(f"SEMANTIC_CLI_CORRECT_EXIT:{exit_code}:{stderr}")
            if payload.get("command") != "correct":
                raise AssertionError("SEMANTIC_CLI_CORRECT_COMMAND_MISMATCH")
            task = court_runtime.load_tasks()[task_id]
            if task.get("charter") != new_charter:
                raise AssertionError("SEMANTIC_CLI_CORRECT_BODY_NOT_BOUND")
            if task.get("semantic_epoch") != 2 or task.get("charter_revision") != 2:
                raise AssertionError("SEMANTIC_CLI_CORRECT_EPOCH_NOT_INCREMENTED")
            if task.get("state") != "ThreeDepartments":
                raise AssertionError("SEMANTIC_CLI_CORRECT_STATE_NOT_RESET")
            if task.get("semantic_state") != "REVERIFY":
                raise AssertionError("SEMANTIC_CLI_CORRECT_NOT_REVERIFY")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_semantic_resume_cli_returns_to_review_without_epoch_change() -> None:
    task_id = "semantic-cli-resume"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "semantic CLI resume charter"))
            context = _semantic_context()
            court_runtime.semantic_checkpoint_task(
                _semantic_args(task_id, "checkpoint", context=context)
            )
            dispatchable = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "verify", context=context)
            ).task
            tasks = court_runtime.load_tasks()
            tasks[task_id]["state"] = "Paused"
            tasks[task_id]["paused_from"] = "SixMinistries"
            court_runtime.write_tasks(tasks)
            paused = court_runtime.load_tasks()[task_id]
            continuation_path = Path(temp_dir) / "continuation-gate.json"
            context_path = Path(temp_dir) / "resume-context.json"
            continuation_path.write_text(
                json.dumps(_continuation_gate_fixture(task_id), ensure_ascii=False),
                encoding="utf-8",
            )
            context["authority_revision"] = 4
            context["authority_sha256"] = _digest("semantic-cli-authority-v4")
            context_path.write_text(
                json.dumps(context, ensure_ascii=False),
                encoding="utf-8",
            )
            receipt = paused["semantic_receipt"]
            exit_code, payload, stderr = _run_runtime_cli(
                [
                    "semantic",
                    "resume",
                    "--task-id",
                    task_id,
                    "--continuation-file",
                    str(continuation_path),
                    "--expected-semantic-epoch",
                    str(paused["semantic_epoch"]),
                    "--expected-charter-sha256",
                    str(paused["charter_sha256"]),
                    "--expected-invariant-capsule-sha256",
                    str(paused["invariant_capsule_sha256"]),
                    "--expected-checkpoint-id",
                    str(receipt["checkpoint_id"]),
                    "--context-file",
                    str(context_path),
                    "--actor",
                    "taizi",
                    "--evidence",
                    "semantic CLI resume tracer",
                ]
            )
            if exit_code != 0 or payload.get("ok") is not True:
                raise AssertionError(f"SEMANTIC_CLI_RESUME_EXIT:{exit_code}:{stderr}")
            if payload.get("command") != "resume":
                raise AssertionError("SEMANTIC_CLI_RESUME_COMMAND_MISMATCH")
            resumed = court_runtime.load_tasks()[task_id]
            if resumed.get("state") != "ThreeDepartments":
                raise AssertionError("SEMANTIC_CLI_RESUME_STATE_NOT_REVIEW")
            if resumed.get("semantic_state") != "REVERIFY":
                raise AssertionError("SEMANTIC_CLI_RESUME_NOT_REVERIFY")
            if resumed.get("semantic_epoch") != dispatchable.get("semantic_epoch"):
                raise AssertionError("SEMANTIC_CLI_RESUME_CHANGED_EPOCH")
            if resumed.get("semantic_context", {}).get("authority_revision") != 4:
                raise AssertionError("SEMANTIC_CLI_RESUME_AUTHORITY_NOT_SEPARATE")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_semantic_quarantine_cli_is_bound_and_append_only() -> None:
    task_id = "semantic-cli-quarantine"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "semantic CLI quarantine charter"))
            court_runtime.semantic_checkpoint_task(_semantic_args(task_id, "checkpoint"))
            task = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "verify")
            ).task
            receipt = task["semantic_receipt"]
            args = [
                "semantic",
                "quarantine",
                "--task-id",
                task_id,
                "--expected-semantic-epoch",
                str(task["semantic_epoch"]),
                "--expected-charter-sha256",
                str(task["charter_sha256"]),
                "--expected-invariant-capsule-sha256",
                str(task["invariant_capsule_sha256"]),
                "--expected-checkpoint-id",
                str(receipt["checkpoint_id"]),
                "--reason-code",
                "manual_evidence_conflict",
                "--reason-code",
                "apply_gate_blocked",
                "--trigger",
                "pre-apply",
                "--actor",
                "menxia",
                "--evidence",
                "semantic CLI quarantine tracer",
            ]
            exit_code, payload, stderr = _run_runtime_cli(args)
            if exit_code != 0 or payload.get("ok") is not True:
                raise AssertionError(f"SEMANTIC_CLI_QUARANTINE_EXIT:{exit_code}:{stderr}")
            if payload.get("command") != "quarantine":
                raise AssertionError("SEMANTIC_CLI_QUARANTINE_COMMAND_MISMATCH")
            quarantined = court_runtime.load_tasks()[task_id]
            if quarantined.get("semantic_state") != "QUARANTINED":
                raise AssertionError("SEMANTIC_CLI_QUARANTINE_STATE_MISSING")
            quarantine_history = quarantined.get("semantic_quarantines")
            if not isinstance(quarantine_history, list) or len(quarantine_history) != 1:
                raise AssertionError("SEMANTIC_CLI_QUARANTINE_HISTORY_MISSING")
            if quarantine_history[0].get("reason_codes") != [
                "manual_evidence_conflict",
                "apply_gate_blocked",
            ]:
                raise AssertionError("SEMANTIC_CLI_QUARANTINE_REASONS_MISSING")
            before = court_runtime.tasks_path().read_bytes()
            stale_args = list(args)
            stale_index = stale_args.index("--expected-semantic-epoch") + 1
            stale_args[stale_index] = "999"
            stale_exit, stale_payload, _ = _run_runtime_cli(stale_args)
            if stale_exit != 2 or stale_payload.get("fail_closed") is not True:
                raise AssertionError("SEMANTIC_CLI_QUARANTINE_STALE_EXIT")
            if court_runtime.tasks_path().read_bytes() != before:
                raise AssertionError("SEMANTIC_CLI_QUARANTINE_STALE_MUTATED")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_semantic_reconcile_cli_requires_restored_sources_then_reverify() -> None:
    task_id = "semantic-cli-reconcile"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "semantic CLI reconcile charter"))
            context = _semantic_context()
            court_runtime.semantic_checkpoint_task(
                _semantic_args(task_id, "checkpoint", context=context)
            )
            task = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "verify", context=context)
            ).task
            receipt = task["semantic_receipt"]
            court_runtime.semantic_quarantine_task(
                Namespace(
                    task_id=task_id,
                    expected_semantic_epoch=task["semantic_epoch"],
                    expected_charter_sha256=task["charter_sha256"],
                    expected_invariant_capsule_sha256=task[
                        "invariant_capsule_sha256"
                    ],
                    expected_checkpoint_id=receipt["checkpoint_id"],
                    reason_code=["manual_evidence_conflict"],
                    trigger="pre-apply",
                    actor="menxia",
                    evidence="semantic reconcile setup",
                    note="",
                )
            )
            context_path = Path(temp_dir) / "reconcile-context.json"
            drifted_context = dict(context)
            drifted_context["git_fingerprint"] = "drifted-worktree"
            context_path.write_text(
                json.dumps(drifted_context, ensure_ascii=False),
                encoding="utf-8",
            )
            base_args = [
                "semantic",
                "reconcile",
                "--task-id",
                task_id,
                "--expected-semantic-epoch",
                str(task["semantic_epoch"]),
                "--expected-charter-sha256",
                str(task["charter_sha256"]),
                "--expected-invariant-capsule-sha256",
                str(task["invariant_capsule_sha256"]),
                "--expected-checkpoint-id",
                str(receipt["checkpoint_id"]),
                "--context-file",
                str(context_path),
                "--resolution-code",
                "evidence_restored",
                "--actor",
                "menxia",
                "--evidence",
                "semantic CLI reconcile tracer",
            ]
            before = court_runtime.tasks_path().read_bytes()
            drift_exit, drift_payload, _ = _run_runtime_cli(base_args)
            if drift_exit != 2 or drift_payload.get("fail_closed") is not True:
                raise AssertionError("SEMANTIC_CLI_RECONCILE_DRIFT_EXIT")
            if court_runtime.tasks_path().read_bytes() != before:
                raise AssertionError("SEMANTIC_CLI_RECONCILE_DRIFT_MUTATED")

            context_path.write_text(
                json.dumps(context, ensure_ascii=False),
                encoding="utf-8",
            )
            exit_code, payload, stderr = _run_runtime_cli(base_args)
            if exit_code != 0 or payload.get("ok") is not True:
                raise AssertionError(f"SEMANTIC_CLI_RECONCILE_EXIT:{exit_code}:{stderr}")
            if payload.get("command") != "reconcile":
                raise AssertionError("SEMANTIC_CLI_RECONCILE_COMMAND_MISMATCH")
            reconciled = court_runtime.load_tasks()[task_id]
            if reconciled.get("semantic_state") != "REVERIFY":
                raise AssertionError("SEMANTIC_CLI_RECONCILE_NOT_REVERIFY")
            history = reconciled.get("semantic_reconciliations")
            if not isinstance(history, list) or len(history) != 1:
                raise AssertionError("SEMANTIC_CLI_RECONCILE_HISTORY_MISSING")
            if history[0].get("resolution_code") != "evidence_restored":
                raise AssertionError("SEMANTIC_CLI_RECONCILE_RESOLUTION_MISSING")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def _decree_open_args(
    task_id: str,
    operation_id: str,
    payload: dict[str, object],
    *,
    expected_revision: int,
    killpoint: str = "",
) -> Namespace:
    return Namespace(
        task_id=task_id,
        operation_id=operation_id,
        payload=payload,
        payload_file=None,
        expected_task_revision=expected_revision,
        killpoint=killpoint,
        actor="taizi",
        evidence=f"decree-open {operation_id}",
        note="decree open fixture",
    )


def check_decree_open_is_idempotent_concurrent_and_crash_recoverable() -> None:
    task_id = "decree-open-idempotent"
    operation_id = "00000000-0000-4000-8000-000000000401"
    payload = {"title": "主诏并发编号", "decree_anchor": "RC2 synthetic fixture"}
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "decree-open charter"))

            def replay(_: int) -> dict[str, object]:
                return court_runtime.decree_open_task(
                    _decree_open_args(
                        task_id,
                        operation_id,
                        payload,
                        expected_revision=1,
                    )
                )

            with ThreadPoolExecutor(max_workers=16) as pool:
                results = list(pool.map(replay, range(32)))
            receipts = [result.get("receipt") for result in results]
            if not all(isinstance(receipt, dict) for receipt in receipts):
                raise AssertionError("DECREE_OPEN_RECEIPT_MISSING")
            canonical = receipts[0]
            if any(receipt != canonical for receipt in receipts[1:]):
                raise AssertionError("DECREE_OPEN_REPLAY_RECEIPT_DIVERGED")
            assert isinstance(canonical, dict)
            if canonical.get("daily_sequence") != 1:
                raise AssertionError("DECREE_OPEN_FIRST_SEQUENCE_INVALID")
            if not str(canonical.get("main_court_code") or "").endswith("-0001"):
                raise AssertionError("DECREE_OPEN_MAIN_CODE_INVALID")
            operation_events = [
                event
                for event in court_runtime.events_for_task(task_id)
                if event.get("operation_id") == operation_id
            ]
            if len(operation_events) != 1:
                raise AssertionError("DECREE_OPEN_REPLAY_DUPLICATED_EVENT")
            before_conflict = court_runtime.tasks_path().read_bytes()
            try:
                court_runtime.decree_open_task(
                    _decree_open_args(
                        task_id,
                        operation_id,
                        {"title": "conflicting payload"},
                        expected_revision=1,
                    )
                )
            except ValueError as exc:
                if str(exc) != "operation_payload_conflict":
                    raise AssertionError("DECREE_OPEN_CONFLICT_WRONG_ERROR:" + str(exc)) from exc
            else:
                raise AssertionError("DECREE_OPEN_CONFLICT_ACCEPTED")
            if court_runtime.tasks_path().read_bytes() != before_conflict:
                raise AssertionError("DECREE_OPEN_CONFLICT_MUTATED")

            crash_id = "00000000-0000-4000-8000-000000000402"
            crash_payload = {"title": "allocation crash decree"}
            try:
                court_runtime.decree_open_task(
                    _decree_open_args(
                        task_id,
                        crash_id,
                        crash_payload,
                        expected_revision=2,
                        killpoint="after_allocation",
                    )
                )
            except court_runtime.SimulatedDecreeOpenCrash:
                pass
            else:
                raise AssertionError("DECREE_OPEN_ALLOCATION_KILLPOINT_DID_NOT_CRASH")
            recovered = court_runtime.recover_decree_open_operation(crash_id)
            recovered_receipt = recovered.get("receipt")
            if not isinstance(recovered_receipt, dict):
                raise AssertionError("DECREE_OPEN_RECOVERY_RECEIPT_MISSING")
            if recovered_receipt.get("daily_sequence") != 2:
                raise AssertionError("DECREE_OPEN_RECOVERY_RENUMBERED")
            recovered_events = [
                event
                for event in court_runtime.events_for_task(task_id)
                if event.get("operation_id") == crash_id
            ]
            if len(recovered_events) != 1:
                raise AssertionError("DECREE_OPEN_RECOVERY_EVENT_NOT_EXACTLY_ONCE")

            next_id = "00000000-0000-4000-8000-000000000403"
            next_result = court_runtime.decree_open_task(
                _decree_open_args(
                    task_id,
                    next_id,
                    {"title": "post recovery decree"},
                    expected_revision=3,
                )
            )
            next_receipt = next_result.get("receipt")
            if not isinstance(next_receipt, dict) or next_receipt.get("daily_sequence") != 3:
                raise AssertionError("DECREE_OPEN_POST_RECOVERY_SEQUENCE_REUSED")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def _synthetic_closeout_args(
    task_id: str,
    operation_id: str,
    payload: dict[str, object],
    *,
    expected_revision: int,
    synthetic_root: Path,
    killpoint: str = "",
) -> Namespace:
    return Namespace(
        task_id=task_id,
        operation_id=operation_id,
        payload=payload,
        payload_file=None,
        expected_task_revision=expected_revision,
        synthetic_archive_root=synthetic_root,
        killpoint=killpoint,
        actor="shiguan",
        evidence=f"synthetic closeout {operation_id}",
        note="synthetic closeout fixture",
    )


def _jsonl_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise AssertionError("SYNTHETIC_CLOSEOUT_ROW_NOT_OBJECT")
            rows.append(value)
    return rows


def check_operation_journal_rmw_is_serialized() -> None:
    operation_id = "00000000-0000-4000-8000-000000000409"
    payload_digest = _digest("operation journal serialized rmw")
    first_load_entered = threading.Event()
    second_write_started = threading.Event()
    release_first_load = threading.Event()
    overlap_detected = threading.Event()
    state_lock = threading.Lock()
    active_loads = 0
    load_calls = 0
    original_load_json = court_operation_journal.load_json

    def controlled_load_json(path: Path) -> dict[str, object] | None:
        nonlocal active_loads, load_calls
        with state_lock:
            load_calls += 1
            call_number = load_calls
            active_loads += 1
            if active_loads > 1:
                overlap_detected.set()
        try:
            if call_number == 1:
                first_load_entered.set()
                if not release_first_load.wait(timeout=5):
                    raise AssertionError("OPERATION_JOURNAL_FIRST_LOAD_RELEASE_TIMEOUT")
            return original_load_json(path)
        finally:
            with state_lock:
                active_loads -= 1

    def write(root: Path, index: int) -> dict[str, object]:
        if index == 2:
            second_write_started.set()
        return court_operation_journal.write_journal(
            root,
            operation_id=operation_id,
            payload_digest=payload_digest,
            task_id="operation-journal-rmw",
            phase="PREPARED",
            receipt=None,
            updated_at=f"2026-07-16T00:00:0{index}+00:00",
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        court_operation_journal.load_json = controlled_load_json
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(write, root, 1)
                if not first_load_entered.wait(timeout=2):
                    raise AssertionError("OPERATION_JOURNAL_FIRST_LOAD_NOT_ENTERED")
                second = pool.submit(write, root, 2)
                if not second_write_started.wait(timeout=2):
                    raise AssertionError("OPERATION_JOURNAL_SECOND_WRITE_NOT_STARTED")
                overlap_detected.wait(timeout=0.5)
                release_first_load.set()
                first.result(timeout=10)
                second.result(timeout=10)
        finally:
            release_first_load.set()
            court_operation_journal.load_json = original_load_json
    if overlap_detected.is_set():
        raise AssertionError("OPERATION_JOURNAL_RMW_NOT_SERIALIZED")


def check_synthetic_closeout_saga_recovers_all_side_effect_killpoints() -> None:
    task_id = "synthetic-closeout-saga"
    decree_operation_id = "00000000-0000-4000-8000-000000000410"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "synthetic closeout charter"))
            decree = court_runtime.decree_open_task(
                _decree_open_args(
                    task_id,
                    decree_operation_id,
                    {"title": "synthetic closeout main decree"},
                    expected_revision=1,
                )
            )["receipt"]
            assert isinstance(decree, dict)
            synthetic_root = Path(temp_dir) / "synthetic-closeout-fixture"
            concurrent_id = "00000000-0000-4000-8000-000000000411"
            concurrent_payload = {
                "decree_id": decree["decree_id"],
                "main_court_code": decree["main_court_code"],
                "summary": "32 replay synthetic closeout",
            }

            def replay(_: int) -> dict[str, object]:
                return court_runtime.synthetic_closeout_task(
                    _synthetic_closeout_args(
                        task_id,
                        concurrent_id,
                        concurrent_payload,
                        expected_revision=2,
                        synthetic_root=synthetic_root,
                    )
                )

            with ThreadPoolExecutor(max_workers=16) as pool:
                replay_results = list(pool.map(replay, range(32)))
            replay_receipts = [result.get("receipt") for result in replay_results]
            canonical = replay_receipts[0]
            if not isinstance(canonical, dict) or any(
                receipt != canonical for receipt in replay_receipts[1:]
            ):
                raise AssertionError("SYNTHETIC_CLOSEOUT_REPLAY_DIVERGED")

            killpoints = ("after_archive", "after_index", "after_task", "after_event")
            recovered_receipts: list[dict[str, object]] = [canonical]
            for offset, killpoint in enumerate(killpoints, start=12):
                operation_id = f"00000000-0000-4000-8000-{offset:012d}"
                task_before = court_runtime.load_tasks()[task_id]
                expected_revision = int(task_before["task_revision"])
                payload = {
                    "decree_id": decree["decree_id"],
                    "main_court_code": decree["main_court_code"],
                    "summary": f"synthetic {killpoint}",
                }
                args = _synthetic_closeout_args(
                    task_id,
                    operation_id,
                    payload,
                    expected_revision=expected_revision,
                    synthetic_root=synthetic_root,
                    killpoint=killpoint,
                )
                try:
                    court_runtime.synthetic_closeout_task(args)
                except court_runtime.SimulatedCloseoutCrash:
                    pass
                else:
                    raise AssertionError(
                        f"SYNTHETIC_CLOSEOUT_KILLPOINT_DID_NOT_CRASH:{killpoint}"
                    )
                recovered = court_runtime.recover_closeout_operation(operation_id)
                receipt = recovered.get("receipt")
                if not isinstance(receipt, dict):
                    raise AssertionError(
                        f"SYNTHETIC_CLOSEOUT_RECOVERY_RECEIPT_MISSING:{killpoint}"
                    )
                if receipt.get("status") != "TASK_EVENT_COMMITTED":
                    raise AssertionError(
                        f"SYNTHETIC_CLOSEOUT_RECOVERY_PHASE_INVALID:{killpoint}"
                    )
                recovered_receipts.append(receipt)
                replayed = court_runtime.synthetic_closeout_task(
                    _synthetic_closeout_args(
                        task_id,
                        operation_id,
                        payload,
                        expected_revision=expected_revision,
                        synthetic_root=synthetic_root,
                    )
                )
                if replayed.get("receipt") != receipt:
                    raise AssertionError(
                        f"SYNTHETIC_CLOSEOUT_REPLAY_RECEIPT_CHANGED:{killpoint}"
                    )

            archive_rows = _jsonl_rows(synthetic_root / "archive.jsonl")
            index_rows = _jsonl_rows(synthetic_root / "index.jsonl")
            expected_operation_ids = {
                concurrent_id,
                *{
                    f"00000000-0000-4000-8000-{offset:012d}"
                    for offset in range(12, 16)
                },
            }
            for operation_id in expected_operation_ids:
                if sum(row.get("operation_id") == operation_id for row in archive_rows) != 1:
                    raise AssertionError(
                        f"SYNTHETIC_CLOSEOUT_ARCHIVE_NOT_EXACTLY_ONCE:{operation_id}"
                    )
                if sum(row.get("operation_id") == operation_id for row in index_rows) != 1:
                    raise AssertionError(
                        f"SYNTHETIC_CLOSEOUT_INDEX_NOT_EXACTLY_ONCE:{operation_id}"
                    )
                if sum(
                    event.get("operation_id") == operation_id
                    and event.get("action") == "closeout_commit"
                    for event in court_runtime.events_for_task(task_id)
                ) != 1:
                    raise AssertionError(
                        f"SYNTHETIC_CLOSEOUT_EVENT_NOT_EXACTLY_ONCE:{operation_id}"
                    )
            record_uids = [str(receipt.get("archive_record_uid") or "") for receipt in recovered_receipts]
            if len(set(record_uids)) != len(record_uids) or any(not uid for uid in record_uids):
                raise AssertionError("SYNTHETIC_CLOSEOUT_RECORD_UID_COLLISION")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_operation_cli_exposes_decree_open_and_closeout_recovery() -> None:
    task_id = "operation-cli"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "operation CLI charter"))
            decree_payload_path = Path(temp_dir) / "decree-payload.json"
            decree_payload_path.write_text(
                json.dumps({"title": "operation CLI decree"}, ensure_ascii=False),
                encoding="utf-8",
            )
            decree_operation_id = "00000000-0000-4000-8000-000000000420"
            decree_exit, decree_payload, decree_stderr = _run_runtime_cli(
                [
                    "decree-open",
                    "--task-id",
                    task_id,
                    "--operation-id",
                    decree_operation_id,
                    "--expected-task-revision",
                    "1",
                    "--payload-file",
                    str(decree_payload_path),
                    "--actor",
                    "taizi",
                    "--evidence",
                    "operation CLI decree tracer",
                ]
            )
            if decree_exit != 0 or decree_payload.get("ok") is not True:
                raise AssertionError(
                    f"OPERATION_CLI_DECREE_OPEN_EXIT:{decree_exit}:{decree_stderr}"
                )
            if decree_payload.get("command") != "decree-open":
                raise AssertionError("OPERATION_CLI_DECREE_COMMAND_MISMATCH")
            decree_receipt = decree_payload.get("result", {}).get("receipt")
            if not isinstance(decree_receipt, dict):
                raise AssertionError("OPERATION_CLI_DECREE_RECEIPT_MISSING")

            synthetic_root = Path(temp_dir) / "synthetic-operation-cli"
            closeout_payload_path = Path(temp_dir) / "closeout-payload.json"
            closeout_payload = {
                "decree_id": decree_receipt["decree_id"],
                "main_court_code": decree_receipt["main_court_code"],
                "summary": "operation CLI closeout",
            }
            closeout_payload_path.write_text(
                json.dumps(closeout_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            closeout_operation_id = "00000000-0000-4000-8000-000000000421"
            try:
                court_runtime.synthetic_closeout_task(
                    _synthetic_closeout_args(
                        task_id,
                        closeout_operation_id,
                        closeout_payload,
                        expected_revision=2,
                        synthetic_root=synthetic_root,
                        killpoint="after_archive",
                    )
                )
            except court_runtime.SimulatedCloseoutCrash:
                pass
            else:
                raise AssertionError("OPERATION_CLI_RECOVERY_SETUP_DID_NOT_CRASH")
            recover_exit, recover_payload, recover_stderr = _run_runtime_cli(
                [
                    "closeout-recover",
                    "--operation-id",
                    closeout_operation_id,
                ]
            )
            if recover_exit != 0 or recover_payload.get("ok") is not True:
                raise AssertionError(
                    f"OPERATION_CLI_RECOVER_EXIT:{recover_exit}:{recover_stderr}"
                )
            if recover_payload.get("command") != "closeout-recover":
                raise AssertionError("OPERATION_CLI_RECOVER_COMMAND_MISMATCH")
            recovered_receipt = recover_payload.get("result", {}).get("receipt")
            if not isinstance(recovered_receipt, dict) or recovered_receipt.get(
                "status"
            ) != "TASK_EVENT_COMMITTED":
                raise AssertionError("OPERATION_CLI_RECOVER_RECEIPT_MISSING")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def _revision_capsule(charter: str, revision_label: str) -> dict[str, object]:
    charter_sha256 = _sha256_text(charter)
    return {
        "schema": "court.semantic.invariant_capsule.v1",
        "latest_decree_anchor": charter,
        "latest_decree_sha256": charter_sha256,
        "non_goals": [f"{revision_label}:non-goal"],
        "boundaries": [f"{revision_label}:boundary"],
        "allowed_actions": [f"{revision_label}:allowed"],
        "forbidden_actions": [f"{revision_label}:forbidden"],
        "acceptance": [f"{revision_label}:acceptance"],
        "evidence_requirements": [f"{revision_label}:evidence"],
        "stop_gates": [f"{revision_label}:stop"],
        "write_set": [f"work/{revision_label}.txt"],
        "governing_hashes": {revision_label: _digest(revision_label)},
        "charter_sha256": charter_sha256,
    }


def check_p1_a_correction_requires_new_canonical_capsule() -> None:
    task_id = "p1-a-correction-capsule"
    old_charter = "P1-A old charter"
    new_charter = "P1-A new charter"
    new_capsule = _revision_capsule(new_charter, "new-revision")
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            created = court_runtime.create_task(_create_args(task_id, old_charter)).task
            court_runtime.semantic_checkpoint_task(_semantic_args(task_id, "checkpoint"))
            current = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "verify")
            ).task
            old_capsule = json.loads(json.dumps(current["invariant_capsule"]))
            old_receipt = json.loads(json.dumps(current["semantic_receipt"]))
            before_tasks = court_runtime.tasks_path().read_bytes()
            before_events = court_runtime.events_path().read_bytes()

            missing = _revise_args(
                task_id,
                old_charter=old_charter,
                new_charter=new_charter,
            )
            missing.new_invariant_capsule = None
            missing.new_invariant_capsule_file = None
            try:
                court_runtime.revise_charter_task(missing)
            except ValueError as exc:
                if str(exc) != "new_invariant_capsule_required":
                    raise AssertionError("P1_A_MISSING_CAPSULE_WRONG_ERROR:" + str(exc)) from exc
            else:
                raise AssertionError("P1_A_MISSING_CAPSULE_ACCEPTED")
            if court_runtime.tasks_path().read_bytes() != before_tasks:
                raise AssertionError("P1_A_MISSING_CAPSULE_MUTATED_TASK")
            if court_runtime.events_path().read_bytes() != before_events:
                raise AssertionError("P1_A_MISSING_CAPSULE_MUTATED_EVENT")

            mismatched = _revise_args(
                task_id,
                old_charter=old_charter,
                new_charter=new_charter,
            )
            mismatched.new_invariant_capsule = _revision_capsule(
                "different charter",
                "mismatched-revision",
            )
            mismatched.new_invariant_capsule_file = None
            try:
                court_runtime.revise_charter_task(mismatched)
            except ValueError as exc:
                if "invariant_capsule" not in str(exc):
                    raise AssertionError("P1_A_MISMATCHED_CAPSULE_WRONG_ERROR:" + str(exc)) from exc
            else:
                raise AssertionError("P1_A_MISMATCHED_CAPSULE_ACCEPTED")
            if court_runtime.tasks_path().read_bytes() != before_tasks:
                raise AssertionError("P1_A_MISMATCHED_CAPSULE_MUTATED_TASK")
            if court_runtime.events_path().read_bytes() != before_events:
                raise AssertionError("P1_A_MISMATCHED_CAPSULE_MUTATED_EVENT")

            valid = _revise_args(
                task_id,
                old_charter=old_charter,
                new_charter=new_charter,
            )
            valid.new_invariant_capsule = new_capsule
            valid.new_invariant_capsule_file = None
            revised = court_runtime.revise_charter_task(valid).task
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    if revised.get("invariant_capsule") != new_capsule:
        raise AssertionError("P1_A_NEW_CAPSULE_NOT_EXACTLY_BOUND")
    if revised.get("invariant_capsule") == old_capsule:
        raise AssertionError("P1_A_OLD_CAPSULE_REUSED")
    for field in ("boundaries", "allowed_actions", "forbidden_actions", "acceptance"):
        old_values = set(old_capsule.get(field, []))
        new_values = set(revised["invariant_capsule"].get(field, []))
        if old_values & new_values:
            raise AssertionError(f"P1_A_OLD_POLICY_FLOWED:{field}")
    invalidations = revised.get("semantic_invalidations")
    if not isinstance(invalidations, list) or not invalidations:
        raise AssertionError("P1_A_INVALIDATION_SNAPSHOT_MISSING")
    snapshot = invalidations[-1]
    if snapshot.get("invariant_capsule") != old_capsule:
        raise AssertionError("P1_A_OLD_CAPSULE_NOT_SNAPSHOTTED")
    if snapshot.get("semantic_receipt") != old_receipt:
        raise AssertionError("P1_A_OLD_RECEIPT_NOT_SNAPSHOTTED")


def _semantic_receipt_history(task: dict[str, object]) -> list[dict[str, object]]:
    history = task.get("semantic_receipts")
    if not isinstance(history, list) or any(
        not isinstance(receipt, dict) for receipt in history
    ):
        raise AssertionError("P1_B_RECEIPT_HISTORY_MISSING")
    return history


def check_p1_b_semantic_receipts_are_immutable_across_revisions() -> None:
    task_id = "p1-b-immutable-receipts"
    old_charter = "P1-B old charter"
    new_charter = "P1-B corrected charter"
    context = _semantic_context()
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, old_charter))
            checkpointed = court_runtime.semantic_checkpoint_task(
                _semantic_args(task_id, "checkpoint", context=context)
            ).task
            checkpoint_receipt = json.loads(
                json.dumps(checkpointed["semantic_receipt"])
            )
            checkpoint_bytes = json.dumps(
                checkpoint_receipt,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            history = _semantic_receipt_history(checkpointed)
            if history != [checkpoint_receipt]:
                raise AssertionError("P1_B_CHECKPOINT_NOT_FIRST_HISTORY_RECEIPT")

            verified = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "verify", context=context)
            ).task
            history = _semantic_receipt_history(verified)
            frozen = court_runtime.semantic_receipt_by_checkpoint_id(
                verified,
                str(checkpoint_receipt["checkpoint_id"]),
            )
            frozen_bytes = json.dumps(
                frozen,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            if frozen_bytes != checkpoint_bytes:
                raise AssertionError("P1_B_CHECKPOINT_RECEIPT_MUTATED_BY_VERIFY")
            if len(history) != 2:
                raise AssertionError("P1_B_VERIFY_DID_NOT_APPEND_RECEIPT")

            verified_again = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "reboot", context=context)
            ).task
            if len(_semantic_receipt_history(verified_again)) != 3:
                raise AssertionError("P1_B_REVERIFY_DID_NOT_APPEND_RECEIPT")
            current = verified_again["semantic_receipt"]
            quarantined = court_runtime.semantic_quarantine_task(
                Namespace(
                    task_id=task_id,
                    expected_semantic_epoch=verified_again["semantic_epoch"],
                    expected_charter_sha256=verified_again["charter_sha256"],
                    expected_invariant_capsule_sha256=verified_again[
                        "invariant_capsule_sha256"
                    ],
                    expected_checkpoint_id=current["checkpoint_id"],
                    reason_code=["p1_b_manual_quarantine"],
                    trigger="pre-apply",
                    actor="menxia",
                    evidence="P1-B quarantine",
                    note="P1-B immutable receipt chain",
                )
            ).task
            if len(_semantic_receipt_history(quarantined)) != 4:
                raise AssertionError("P1_B_QUARANTINE_DID_NOT_APPEND_RECEIPT")
            quarantined_current = quarantined["semantic_receipt"]
            reconciled = court_runtime.semantic_reconcile_task(
                Namespace(
                    task_id=task_id,
                    expected_semantic_epoch=quarantined["semantic_epoch"],
                    expected_charter_sha256=quarantined["charter_sha256"],
                    expected_invariant_capsule_sha256=quarantined[
                        "invariant_capsule_sha256"
                    ],
                    expected_checkpoint_id=quarantined_current["checkpoint_id"],
                    semantic_context=context,
                    semantic_context_file=None,
                    resolution_code="p1_b_sources_restored",
                    actor="menxia",
                    evidence="P1-B reconcile",
                    note="P1-B immutable receipt chain",
                )
            ).task
            if len(_semantic_receipt_history(reconciled)) != 5:
                raise AssertionError("P1_B_RECONCILE_DID_NOT_APPEND_RECEIPT")

            court_runtime.semantic_checkpoint_task(
                _semantic_args(task_id, "post-reconcile-checkpoint", context=context)
            )
            dispatchable = court_runtime.semantic_verify_task(
                _semantic_args(task_id, "post-reconcile-verify", context=context)
            ).task
            history_before_resume = len(_semantic_receipt_history(dispatchable))
            tasks = court_runtime.load_tasks()
            tasks[task_id]["state"] = "Paused"
            tasks[task_id]["paused_from"] = "SixMinistries"
            court_runtime.write_tasks(tasks)
            paused = court_runtime.load_tasks()[task_id]
            resumed = court_runtime.semantic_resume_task(
                _resume_args(
                    paused,
                    expected_epoch=int(paused["semantic_epoch"]),
                    to_state="ThreeDepartments",
                    context=context,
                )
            ).task
            if len(_semantic_receipt_history(resumed)) != history_before_resume + 1:
                raise AssertionError("P1_B_RESUME_DID_NOT_APPEND_RECEIPT")

            history_before_correction = json.loads(
                json.dumps(_semantic_receipt_history(resumed))
            )
            correction = _revise_args(
                task_id,
                old_charter=old_charter,
                new_charter=new_charter,
            )
            correction.new_invariant_capsule = _revision_capsule(
                new_charter,
                "p1-b-revision-2",
            )
            corrected = court_runtime.revise_charter_task(correction).task
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    corrected_history = _semantic_receipt_history(corrected)
    if corrected_history[:-1] != history_before_correction:
        raise AssertionError("P1_B_CORRECTION_DROPPED_OLD_RECEIPT_HISTORY")
    if corrected_history[-1].get("gate") != "semantic_correct":
        raise AssertionError("P1_B_CORRECTION_RECEIPT_MISSING")
    receipt_ids = [receipt.get("receipt_id") for receipt in corrected_history]
    if any(not receipt_id for receipt_id in receipt_ids):
        raise AssertionError("P1_B_RECEIPT_ID_MISSING")
    if len(set(receipt_ids)) != len(receipt_ids):
        raise AssertionError("P1_B_RECEIPT_ID_NOT_UNIQUE")
    if corrected.get("semantic_receipt") != corrected_history[-1]:
        raise AssertionError("P1_B_CURRENT_RECEIPT_NOT_LATEST")
    if corrected.get("semantic_receipt_id") != corrected_history[-1].get("receipt_id"):
        raise AssertionError("P1_B_CURRENT_RECEIPT_POINTER_MISSING")
    invalidations = corrected.get("semantic_invalidations")
    if not isinstance(invalidations, list) or not invalidations:
        raise AssertionError("P1_B_CORRECTION_INVALIDATION_MISSING")
    snapshot = invalidations[-1]
    if snapshot.get("semantic_receipts") != history_before_correction:
        raise AssertionError("P1_B_CORRECTION_HISTORY_NOT_SNAPSHOTTED")


def _tamper_receipt_field(receipt: dict[str, object], field: str) -> None:
    if field in {
        "semantic_epoch",
        "authority_revision",
        "plan_revision",
        "shiguan_revision",
    }:
        receipt[field] = int(receipt[field]) + 1
    elif field == "created_at":
        receipt[field] = "2026-07-16T00:00:00"
    elif field == "trigger":
        receipt[field] = "invalid-trigger"
    elif field == "gate":
        receipt[field] = "invalid-gate"
    elif field == "checkpoint_id":
        receipt[field] = "SC-000000000000000000000000"
    elif field in {
        "event_head_sha256",
        "write_set_sha256",
        "charter_sha256",
        "invariant_capsule_sha256",
        "authority_sha256",
        "plan_sha256",
        "shiguan_fingerprint",
    }:
        receipt[field] = _digest("tampered:" + field)
    else:
        receipt[field] = "tampered:" + field


def check_p1_c_checkpoint_receipt_tamper_table_fails_closed() -> None:
    fields = (
        "checkpoint_id",
        "event_head_sha256",
        "write_set_sha256",
        "trigger",
        "gate",
        "created_at",
        "task_id",
        "semantic_epoch",
        "charter_sha256",
        "invariant_capsule_sha256",
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
    for field in fields:
        task_id = "p1-c-tamper-" + field.replace("_", "-")
        with tempfile.TemporaryDirectory() as temp_dir:
            original_runtime_root = court_runtime.runtime_root
            court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
            try:
                court_runtime.create_task(_create_args(task_id, f"P1-C {field} charter"))
                checkpointed = court_runtime.semantic_checkpoint_task(
                    _semantic_args(task_id, "checkpoint")
                ).task
                tampered = json.loads(json.dumps(checkpointed["semantic_receipt"]))
                _tamper_receipt_field(tampered, field)
                tampered = court_runtime.finalize_semantic_receipt(tampered)
                tasks = court_runtime.load_tasks()
                tasks[task_id]["semantic_receipts"][0] = tampered
                tasks[task_id]["semantic_receipt"] = tampered
                tasks[task_id]["semantic_receipt_id"] = tampered["receipt_id"]
                court_runtime.write_tasks(tasks)
                before_tasks = court_runtime.tasks_path().read_bytes()
                before_events = court_runtime.events_path().read_bytes()
                try:
                    court_runtime.semantic_verify_task(
                        _semantic_args(task_id, "verify")
                    )
                except ValueError as exc:
                    if not str(exc).startswith("semantic_receipt_integrity_failed:"):
                        raise AssertionError(
                            f"P1_C_TAMPER_WRONG_ERROR:{field}:{exc}"
                        ) from exc
                else:
                    raise AssertionError(f"P1_C_TAMPER_ACCEPTED:{field}")
                if court_runtime.tasks_path().read_bytes() != before_tasks:
                    raise AssertionError(f"P1_C_TAMPER_MUTATED_TASK:{field}")
                if court_runtime.events_path().read_bytes() != before_events:
                    raise AssertionError(f"P1_C_TAMPER_MUTATED_EVENT:{field}")
            finally:
                court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def _dispatch_context_packet(
    task_id: str,
    receipt: dict[str, object],
) -> dict[str, object]:
    return {
        "schema": "court.semantic.dispatch_context_packet.v1",
        "task_id": task_id,
        "sub_id": "worker-01",
        "semantic_epoch": receipt["semantic_epoch"],
        "invariant_capsule_sha256": receipt["invariant_capsule_sha256"],
        "semantic_receipt_id": receipt["receipt_id"],
        "semantic_receipt_sha256": receipt["receipt_sha256"],
        "authority_sha256": receipt["authority_sha256"],
        "plan_sha256": receipt["plan_sha256"],
        "plan_cursor": receipt["plan_cursor"],
        "fork_context": "minimal",
        "context_mode": "bounded",
        "pointers": [
            {
                "path": "authority/current.md",
                "sha256": receipt["authority_sha256"],
            },
            {
                "path": "plans/current.md",
                "sha256": receipt["plan_sha256"],
            },
        ],
        "summary": {
            "text": "bounded semantic dispatch packet",
            "semantic_receipt_id": receipt["receipt_id"],
            "semantic_receipt_sha256": receipt["receipt_sha256"],
        },
    }


def _expect_dispatch_packet_error(
    task: dict[str, object],
    receipt: dict[str, object],
    packet: dict[str, object],
    expected: str,
    **kwargs: object,
) -> None:
    try:
        court_semantic_continuity.validate_dispatch_context_packet(
            task,
            receipt,
            packet,
            **kwargs,
        )
    except ValueError as exc:
        if not str(exc).startswith(expected):
            raise AssertionError(
                f"P00_CONTEXT_PACKET_WRONG_ERROR:{expected}:{exc}"
            ) from exc
    else:
        raise AssertionError(f"P00_CONTEXT_PACKET_ACCEPTED:{expected}")


def check_p00_bounded_context_packet_preserves_semantic_continuity() -> None:
    task_id = "p00-context-packet"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_create_args(task_id, "P00 packet charter"))
            task = court_runtime.semantic_checkpoint_task(
                _semantic_args(task_id, "checkpoint")
            ).task
            receipt = task["semantic_receipt"]
            assert isinstance(receipt, dict)
            packet = _dispatch_context_packet(task_id, receipt)
            validated = court_semantic_continuity.validate_dispatch_context_packet(
                task,
                receipt,
                packet,
            )
            if validated.get("packet_bytes", 2049) > 2048:
                raise AssertionError("P00_CONTEXT_PACKET_DEFAULT_EXCEEDS_2KIB")
            if validated.get("reload_required") != []:
                raise AssertionError("P00_CONTEXT_PACKET_FRESH_RELOAD_REQUIRED")

            oversized = json.loads(json.dumps(packet))
            oversized["summary"]["text"] = "x" * 3000
            _expect_dispatch_packet_error(
                task,
                receipt,
                oversized,
                "dispatch_context_packet_exceeds_2kib",
            )

            inherited = json.loads(json.dumps(packet))
            inherited["fork_context"] = "all"
            _expect_dispatch_packet_error(
                task,
                receipt,
                inherited,
                "invalid_dispatch_context_fork_context",
            )

            broad_pointer = json.loads(json.dumps(packet))
            broad_pointer["pointers"][0]["path"] = "authority/*.md"
            _expect_dispatch_packet_error(
                task,
                receipt,
                broad_pointer,
                "dispatch_context_pointer_not_exact",
            )

            unbound_summary = json.loads(json.dumps(packet))
            unbound_summary["summary"]["semantic_receipt_sha256"] = _digest(
                "stale-summary-receipt"
            )
            _expect_dispatch_packet_error(
                task,
                receipt,
                unbound_summary,
                "dispatch_context_summary_receipt_mismatch",
            )

            alternate_capsule = json.loads(json.dumps(packet))
            alternate_capsule["invariant_capsule_sha256"] = _digest(
                "alternate-capsule-authority"
            )
            _expect_dispatch_packet_error(
                task,
                receipt,
                alternate_capsule,
                "dispatch_context_capsule_authority_mismatch",
            )

            extra_context = json.loads(json.dumps(packet))
            extra_context["transcript"] = "unbounded inherited conversation"
            _expect_dispatch_packet_error(
                task,
                receipt,
                extra_context,
                "dispatch_context_packet_fields_unknown",
            )

            full_context = json.loads(json.dumps(packet))
            full_context.update(
                context_mode="full",
                full_context="x" * 3000,
            )
            _expect_dispatch_packet_error(
                task,
                receipt,
                full_context,
                "dispatch_context_full_requires_explicit_budget_override",
            )
            full_context["budget_override"] = {
                "explicit": True,
                "granted_by": "user",
                "max_bytes": 8192,
            }
            court_semantic_continuity.validate_dispatch_context_packet(
                task,
                receipt,
                full_context,
            )

            resumed_receipt = court_semantic_continuity.derive_semantic_receipt(
                receipt,
                receipt_sequence=2,
                gate="semantic_verify",
                verdict="DISPATCHABLE",
                trigger="verify",
                reason_codes=[],
                created_at="2026-07-16T00:00:01+00:00",
                event_head_sha256=_digest("p00-resume-event-head"),
                event_head_bytes=0,
            )
            resumed_task = json.loads(json.dumps(task))
            resumed_task["semantic_receipt"] = resumed_receipt
            resumed_packet = _dispatch_context_packet(task_id, resumed_receipt)
            unchanged = court_semantic_continuity.validate_dispatch_context_packet(
                resumed_task,
                resumed_receipt,
                resumed_packet,
                previous_packet=packet,
            )
            if unchanged.get("reload_required") != []:
                raise AssertionError("P00_CONTEXT_PACKET_UNCHANGED_HASH_RELOAD_REQUIRED")

            changed_authority = _digest("p00-changed-authority")
            changed_receipt = court_semantic_continuity.derive_semantic_receipt(
                receipt,
                receipt_sequence=2,
                gate="semantic_resume",
                verdict="REVERIFY",
                trigger="resume",
                reason_codes=["authority_revision_updated"],
                created_at="2026-07-16T00:00:02+00:00",
                event_head_sha256=_digest("p00-changed-event-head"),
                event_head_bytes=0,
                updates={"authority_sha256": changed_authority},
            )
            changed_task = json.loads(json.dumps(task))
            changed_task["semantic_receipt"] = changed_receipt
            changed_packet = _dispatch_context_packet(task_id, changed_receipt)
            _expect_dispatch_packet_error(
                changed_task,
                changed_receipt,
                changed_packet,
                "dispatch_context_reload_required:authority/current.md",
                previous_packet=packet,
            )
            reloaded = court_semantic_continuity.validate_dispatch_context_packet(
                changed_task,
                changed_receipt,
                changed_packet,
                previous_packet=packet,
                reloaded_pointers=[
                    {
                        "path": "authority/current.md",
                        "sha256": changed_authority,
                    }
                ],
            )
            if reloaded.get("reload_required") != ["authority/current.md"]:
                raise AssertionError("P00_CONTEXT_PACKET_CHANGED_HASH_RELOAD_MISSING")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_stage3_result_recovery_pure_schema_core_head_idempotency_red() -> None:
    required_helpers = (
        "office_result_envelope_json_schema",
        "result_quarantine_core_json_schema",
        "result_recovery_head_json_schema",
        "result_recovery_review_receipt_json_schema",
        "result_recovery_handoff_receipt_json_schema",
        "result_recovery_consume_receipt_json_schema",
        "source_result_payload_sha256",
        "build_result_quarantine_core",
        "validate_result_quarantine_core",
        "build_result_recovery_head",
        "validate_result_recovery_head",
        "result_recovery_target_binding_fields",
        "deterministic_result_recovery_event_id",
        "result_recovery_record_disposition",
        "apply_result_recovery_operation",
    )
    missing = [
        name
        for name in required_helpers
        if not callable(getattr(court_semantic_continuity, name, None))
    ]
    if missing:
        raise AssertionError(
            "STAGE3_RESULT_RECOVERY_PURE_HELPERS_MISSING:" + ",".join(missing)
        )

    def assert_closed_schema(
        helper_name: str,
        required_fields: set[str],
        optional_fields: set[str] | None = None,
    ) -> dict[str, object]:
        factory = getattr(court_semantic_continuity, helper_name)
        schema = factory()
        if not isinstance(schema, dict):
            raise AssertionError(f"STAGE3_SCHEMA_NOT_OBJECT:{helper_name}")
        if schema.get("additionalProperties") is not False:
            raise AssertionError(f"STAGE3_SCHEMA_NOT_CLOSED:{helper_name}")
        if set(schema.get("required", [])) != required_fields:
            raise AssertionError(f"STAGE3_SCHEMA_REQUIRED_FIELDS_DRIFT:{helper_name}")
        expected_properties = required_fields | (optional_fields or set())
        properties = schema.get("properties")
        if not isinstance(properties, dict) or set(properties) != expected_properties:
            raise AssertionError(f"STAGE3_SCHEMA_PROPERTY_WHITELIST_DRIFT:{helper_name}")
        return schema

    def schema_property(schema: dict[str, object], field: str) -> dict[str, object]:
        properties = schema.get("properties")
        value = properties.get(field) if isinstance(properties, dict) else None
        if not isinstance(value, dict):
            raise AssertionError(f"STAGE3_SCHEMA_PROPERTY_INVALID:{field}")
        return value

    def assert_schema_const(
        schema: dict[str, object],
        expected_schema: str,
    ) -> None:
        if schema_property(schema, "schema").get("const") != expected_schema:
            raise AssertionError(f"STAGE3_SCHEMA_CONST_DRIFT:{expected_schema}")

    def assert_sha256_property(schema: dict[str, object], field: str) -> None:
        prop = schema_property(schema, field)
        if prop.get("type") != "string" or prop.get("pattern") != "^[0-9a-f]{64}$":
            raise AssertionError(f"STAGE3_SHA256_PROPERTY_DRIFT:{field}")

    def assert_positive_integer_property(
        schema: dict[str, object],
        field: str,
    ) -> None:
        prop = schema_property(schema, field)
        if prop.get("type") != "integer" or prop.get("minimum") != 1:
            raise AssertionError(f"STAGE3_POSITIVE_INTEGER_PROPERTY_DRIFT:{field}")

    def assert_unique_string_array(
        schema: dict[str, object],
        field: str,
    ) -> None:
        prop = schema_property(schema, field)
        items = prop.get("items")
        if (
            prop.get("type") != "array"
            or prop.get("uniqueItems") is not True
            or not isinstance(items, dict)
            or items.get("type") != "string"
            or items.get("minLength") != 1
        ):
            raise AssertionError(f"STAGE3_UNIQUE_STRING_ARRAY_DRIFT:{field}")

    envelope_required = {
        "schema",
        "task_id",
        "semantic_epoch",
        "charter_sha256",
        "invariant_capsule_sha256",
        "checkpoint_id",
        "dispatch_uid",
        "attempt",
        "office_instance_id",
        "agent_id",
        "role",
        "direct_superior",
        "worktree",
        "write_set_sha256",
        "status",
        "summary",
        "evidence",
        "produced_at",
    }
    envelope_schema = assert_closed_schema(
        "office_result_envelope_json_schema",
        envelope_required,
        {"office_instance_kind", "carrier_proof", "recovery_input_ids"},
    )
    assert_schema_const(envelope_schema, "court.office.result.v1")
    for field in ("charter_sha256", "invariant_capsule_sha256", "write_set_sha256"):
        assert_sha256_property(envelope_schema, field)
    for field in ("semantic_epoch", "attempt"):
        assert_positive_integer_property(envelope_schema, field)
    if set(schema_property(envelope_schema, "status").get("enum", [])) != {
        "completed",
        "failed",
        "cancelled",
    }:
        raise AssertionError("STAGE3_RESULT_ENVELOPE_STATUS_ENUM_DRIFT")
    if set(schema_property(envelope_schema, "office_instance_kind").get("enum", [])) != {
        "child_agent",
        "worktree_thread",
    }:
        raise AssertionError("STAGE3_RESULT_ENVELOPE_KIND_ENUM_DRIFT")
    assert_unique_string_array(envelope_schema, "evidence")
    assert_unique_string_array(envelope_schema, "recovery_input_ids")
    carrier_schema = schema_property(envelope_schema, "carrier_proof")
    carrier_variants = carrier_schema.get("oneOf")
    if not isinstance(carrier_variants, list) or len(carrier_variants) != 2:
        raise AssertionError("STAGE3_CARRIER_PROOF_VARIANTS_MISSING")
    carrier_shapes: set[frozenset[str]] = set()
    for variant in carrier_variants:
        if not isinstance(variant, dict) or variant.get("additionalProperties") is not False:
            raise AssertionError("STAGE3_CARRIER_PROOF_VARIANT_NOT_CLOSED")
        required = variant.get("required")
        properties = variant.get("properties")
        if not isinstance(required, list) or not isinstance(properties, dict):
            raise AssertionError("STAGE3_CARRIER_PROOF_VARIANT_INVALID")
        if set(required) != set(properties):
            raise AssertionError("STAGE3_CARRIER_PROOF_REQUIRED_FIELDS_DRIFT")
        carrier_shapes.add(frozenset(properties))
    if carrier_shapes != {
        frozenset({"agent_id"}),
        frozenset(
            {
                "thread_id",
                "canonical_worktree_id",
                "canonical_worktree_path",
                "repo_id",
                "common_dir_fingerprint",
                "worktree_fingerprint",
                "branch",
                "start_head",
            }
        ),
    }:
        raise AssertionError("STAGE3_CARRIER_PROOF_EXACT_SHAPES_DRIFT")

    quarantine_required = {
        "schema",
        "quarantine_id",
        "payload_sha256",
        "task_id",
        "semantic_epoch",
        "charter_sha256",
        "invariant_capsule_sha256",
        "checkpoint_id",
        "dispatch_uid",
        "attempt",
        "office_instance_id",
        "office_instance_kind",
        "carrier_proof_sha256",
        "agent_id",
        "role",
        "direct_superior",
        "worktree",
        "write_set_sha256",
        "source_status",
        "source_final_status",
        "source_release_status",
        "source_result_state",
        "failure_kind",
        "reason_codes",
        "received_at",
        "quarantine_event_id",
        "core_sha256",
    }
    quarantine_schema = assert_closed_schema(
        "result_quarantine_core_json_schema",
        quarantine_required,
    )
    assert_schema_const(quarantine_schema, "court.office.result_quarantine.v2")
    for field in (
        "payload_sha256",
        "charter_sha256",
        "invariant_capsule_sha256",
        "carrier_proof_sha256",
        "write_set_sha256",
        "core_sha256",
    ):
        assert_sha256_property(quarantine_schema, field)
    for field in ("semantic_epoch", "attempt"):
        assert_positive_integer_property(quarantine_schema, field)
    for field, expected in (
        ("source_status", "failed"),
        ("source_final_status", "failed"),
        ("source_release_status", "closed"),
        ("source_result_state", "QUARANTINED"),
        ("failure_kind", "result_binding_quarantine"),
    ):
        if schema_property(quarantine_schema, field).get("const") != expected:
            raise AssertionError(f"STAGE3_QUARANTINE_CORE_CONST_DRIFT:{field}")
    assert_unique_string_array(quarantine_schema, "reason_codes")

    recovery_head_required = {
        "schema",
        "recovery_id",
        "quarantine_id",
        "revision",
        "state",
        "previous_head_sha256",
        "projection_sha256",
        "target_binding_sha256",
        "review_receipt_sha256",
        "handoff_receipt_sha256",
        "consume_receipt_sha256",
        "operation_id",
        "event_id",
        "created_at",
        "head_sha256",
    }
    recovery_head_schema = assert_closed_schema(
        "result_recovery_head_json_schema",
        recovery_head_required,
    )
    assert_schema_const(recovery_head_schema, "court.office.result_recovery_head.v1")
    assert_positive_integer_property(recovery_head_schema, "revision")
    if set(schema_property(recovery_head_schema, "state").get("enum", [])) != {
        "REVIEW_PENDING",
        "READY_FOR_HANDOFF",
        "REJECTED",
        "HANDED_OFF",
        "CONSUMED",
    }:
        raise AssertionError("STAGE3_RECOVERY_HEAD_STATE_ENUM_DRIFT")
    for field in (
        "previous_head_sha256",
        "projection_sha256",
        "target_binding_sha256",
        "review_receipt_sha256",
        "handoff_receipt_sha256",
        "consume_receipt_sha256",
        "head_sha256",
    ):
        assert_sha256_property(recovery_head_schema, field)

    receipt_contracts = (
        (
            "result_recovery_review_receipt_json_schema",
            "court.office.result_recovery_review_receipt.v1",
            {
                "schema", "receipt_id", "operation_id", "task_id",
                "task_revision", "quarantine_id", "quarantine_core_sha256",
                "recovery_id", "recovery_revision", "previous_head_sha256",
                "decision", "reason_codes", "evidence_pointer",
                "evidence_sha256", "projection_sha256", "actor",
                "reviewed_at", "event_id", "receipt_sha256",
            },
        ),
        (
            "result_recovery_handoff_receipt_json_schema",
            "court.office.result_recovery_handoff_receipt.v1",
            {
                "schema", "receipt_id", "operation_id", "task_id",
                "task_revision", "quarantine_id", "recovery_id",
                "recovery_revision", "previous_head_sha256",
                "review_receipt_sha256", "target_binding_sha256",
                "native_host_request_sha256", "native_host_action_receipt_id",
                "native_host_action_receipt_sha256", "reason_codes",
                "evidence_pointer", "evidence_sha256", "actor",
                "handed_off_at", "event_id", "receipt_sha256",
            },
        ),
        (
            "result_recovery_consume_receipt_json_schema",
            "court.office.result_recovery_consume_receipt.v1",
            {
                "schema", "receipt_id", "operation_id", "task_id",
                "task_revision", "quarantine_id", "recovery_id",
                "recovery_revision", "previous_head_sha256",
                "handoff_receipt_sha256", "target_binding_sha256",
                "target_result_envelope_sha256", "target_finish_event_id",
                "reason_codes", "evidence_pointer", "evidence_sha256",
                "actor", "consumed_at", "event_id", "receipt_sha256",
            },
        ),
    )
    for helper_name, schema_name, required_fields in receipt_contracts:
        receipt_schema = assert_closed_schema(helper_name, required_fields)
        assert_schema_const(receipt_schema, schema_name)
        assert_sha256_property(receipt_schema, "receipt_sha256")
        assert_sha256_property(receipt_schema, "evidence_sha256")
        assert_unique_string_array(receipt_schema, "reason_codes")

    source_hash = getattr(court_semantic_continuity, "source_result_payload_sha256")
    source_a = {"schema": "court.office.result.v1", "summary": "raw", "status": "completed"}
    source_b = {"status": "completed", "summary": "raw", "schema": "court.office.result.v1"}
    source_c = {"schema": "court.office.result.v1", "summary": "changed", "status": "completed"}
    if source_hash(source_a) != _canonical_sha256(source_a):
        raise AssertionError("STAGE3_PRE_ADAPT_SOURCE_HASH_NOT_CANONICAL")
    if source_hash(source_a) != source_hash(source_b):
        raise AssertionError("STAGE3_PRE_ADAPT_SOURCE_HASH_KEY_ORDER_SENSITIVE")
    if source_hash(source_a) == source_hash(source_c):
        raise AssertionError("STAGE3_PRE_ADAPT_SOURCE_HASH_VALUE_BLIND")

    target_fields = set(
        getattr(court_semantic_continuity, "result_recovery_target_binding_fields")()
    )
    expected_target_fields = {
        "task_id", "semantic_epoch", "charter_sha256",
        "invariant_capsule_sha256", "checkpoint_id", "dispatch_uid",
        "attempt", "office_instance_id", "office_instance_kind",
        "carrier_proof", "agent_id", "role", "direct_superior", "worktree",
        "write_set_sha256", "hierarchy_schema", "hierarchy_gate",
        "hierarchy_edge_class", "preload_status", "office_execution_ready",
        "status", "final_status", "release_status", "result_state",
    }
    if target_fields != expected_target_fields:
        raise AssertionError("STAGE3_TARGET_BINDING_FIELDS_NOT_EXACT")

    expected_event_id = "EVT-RR-" + hashlib.sha256(
        b"OP-RED|review|payload-red"
    ).hexdigest()[:24].upper()
    if (
        court_semantic_continuity.deterministic_result_recovery_event_id(
            "OP-RED", "review", "payload-red"
        )
        != expected_event_id
    ):
        raise AssertionError("STAGE3_RESULT_RECOVERY_EVENT_ID_NOT_DETERMINISTIC")
    if (
        court_semantic_continuity.deterministic_result_recovery_event_id(
            "OP-RED", "handoff", "payload-red"
        )
        == expected_event_id
    ):
        raise AssertionError("STAGE3_RESULT_RECOVERY_EVENT_ID_ACTION_BLIND")
    if (
        court_semantic_continuity.deterministic_result_recovery_event_id(
            "OP-RED", "review", "payload-blue"
        )
        == expected_event_id
    ):
        raise AssertionError("STAGE3_RESULT_RECOVERY_EVENT_ID_PAYLOAD_BLIND")

    disposition = getattr(court_semantic_continuity, "result_recovery_record_disposition")
    legacy_records = (
        {"schema": "court.office.result_quarantine.v1"},
        {"schema": "court.office.result_quarantine.v2"},
        {"schema": "court.office.result_recovery_head.v1", "head_sha256": _digest("head")},
    )
    for record in legacy_records:
        if disposition(record) != "READ_ONLY_LEGACY":
            raise AssertionError("STAGE3_LEGACY_RESULT_RECOVERY_RECORD_MUTABLE")

    valid = {
        "schema": "court.office.result.v1",
        "task_id": "stage3-red",
        "semantic_epoch": 1,
        "charter_sha256": _digest("stage3-charter"),
        "invariant_capsule_sha256": _digest("stage3-capsule"),
        "checkpoint_id": "CHK-STAGE3-RED",
        "dispatch_uid": "dispatch-stage3-red",
        "attempt": 1,
        "office_instance_id": "gongbu-stage3-red",
        "office_instance_kind": "child_agent",
        "carrier_proof": {"agent_id": "gongbu-stage3-red"},
        "agent_id": "gongbu-stage3-red",
        "role": "gongbu",
        "direct_superior": "shangshu",
        "worktree": "D:/project/worktrees/decretum-matrix/beta106-local-stage-019fb7f5",
        "write_set_sha256": _digest("stage3-write-set"),
        "status": "completed",
        "summary": "bounded projection",
        "evidence": ["receipts/stage3-red.json"],
        "produced_at": "2026-08-03T00:00:00+00:00",
        "recovery_input_ids": ["REC-STAGE3-SEED"],
    }

    def expect_envelope_refusal(field: str, value: object, error: str) -> None:
        candidate = dict(valid)
        candidate[field] = value
        try:
            court_semantic_continuity.normalize_result_envelope(candidate)
        except ValueError as exc:
            if str(exc) != error:
                raise AssertionError(
                    f"STAGE3_RESULT_ENVELOPE_WRONG_ERROR:{field}:{exc}"
                ) from exc
        else:
            raise AssertionError(f"STAGE3_RESULT_ENVELOPE_BYPASS_ACCEPTED:{field}")

    normalized_valid = court_semantic_continuity.normalize_result_envelope(valid)
    if normalized_valid != valid:
        raise AssertionError("STAGE3_VALID_RESULT_ENVELOPE_NOT_CANONICAL")

    expect_envelope_refusal("unexpected", "value", "result_envelope_unknown_field")
    expect_envelope_refusal("raw_body", "private", "result_envelope_private_field")
    expect_envelope_refusal(
        "recovery_input_ids",
        [{"recovery_id": "REC-RED"}],
        "result_envelope_nested_field_forbidden",
    )
    expect_envelope_refusal(
        "recovery_input_ids",
        ["REC-STAGE3-DUPLICATE", "REC-STAGE3-DUPLICATE"],
        "result_envelope_duplicate_recovery_id",
    )
    expect_envelope_refusal(
        "carrier_proof",
        {"agent_id": "gongbu-stage3-red", "unexpected": "value"},
        "result_envelope_unknown_nested_field",
    )

    def expect_value_error(expected_error: str, call) -> None:
        try:
            call()
        except ValueError as exc:
            if str(exc) != expected_error:
                raise AssertionError(
                    f"STAGE3_RESULT_RECOVERY_WRONG_ERROR:{expected_error}:{exc}"
                ) from exc
        else:
            raise AssertionError(
                f"STAGE3_RESULT_RECOVERY_EXPECTED_ERROR_MISSING:{expected_error}"
            )

    failed_source = dict(normalized_valid)
    failed_source["status"] = "failed"
    failed_source["summary"] = "quarantined bounded projection"
    core_a = court_semantic_continuity.build_result_quarantine_core(
        source_result=failed_source,
        source_final_status="failed",
        source_release_status="closed",
        source_result_state="QUARANTINED",
        reason_codes=["result_binding_mismatch"],
        received_at="2026-08-03T00:01:00+00:00",
    )
    core_b = court_semantic_continuity.build_result_quarantine_core(
        source_result=failed_source,
        source_final_status="failed",
        source_release_status="closed",
        source_result_state="QUARANTINED",
        reason_codes=["result_binding_mismatch"],
        received_at="2026-08-03T00:01:00+00:00",
    )
    if core_a != core_b:
        raise AssertionError("STAGE3_QUARANTINE_CORE_NOT_DETERMINISTIC")
    if court_semantic_continuity.validate_result_quarantine_core(core_a) != core_a:
        raise AssertionError("STAGE3_QUARANTINE_CORE_NOT_CANONICAL")
    tampered_core = dict(core_a)
    tampered_core["reason_codes"] = ["tampered_reason"]
    expect_value_error(
        "result_quarantine_core_digest_mismatch",
        lambda: court_semantic_continuity.validate_result_quarantine_core(
            tampered_core
        ),
    )
    if (
        court_semantic_continuity.result_recovery_record_disposition(core_a)
        != "CURRENT_QUARANTINE_CORE"
    ):
        raise AssertionError("STAGE3_VALID_QUARANTINE_CORE_DISPOSITION_DRIFT")

    zero_sha256 = "0" * 64
    recovery_id = "REC-STAGE3-RED"
    head_1 = court_semantic_continuity.build_result_recovery_head(
        quarantine_core=core_a,
        recovery_id=recovery_id,
        previous_head=None,
        state="REVIEW_PENDING",
        projection_sha256=_digest("stage3-projection-rev1"),
        target_binding_sha256=_digest("stage3-target-binding"),
        review_receipt_sha256=zero_sha256,
        handoff_receipt_sha256=zero_sha256,
        consume_receipt_sha256=zero_sha256,
        operation_id="OP-STAGE3-HEAD-REV1",
        event_id=court_semantic_continuity.deterministic_result_recovery_event_id(
            "OP-STAGE3-HEAD-REV1", "quarantine", core_a["core_sha256"]
        ),
        created_at="2026-08-03T00:02:00+00:00",
    )
    if head_1.get("revision") != 1 or head_1.get("previous_head_sha256") != zero_sha256:
        raise AssertionError("STAGE3_RECOVERY_HEAD_REV1_CHAIN_DRIFT")
    if (
        court_semantic_continuity.validate_result_recovery_head(
            head_1,
            expected_revision=1,
            expected_head_sha256=head_1["head_sha256"],
        )
        != head_1
    ):
        raise AssertionError("STAGE3_RECOVERY_HEAD_REV1_NOT_CANONICAL")

    operation_id = "OP-STAGE3-REVIEW"
    operation_payload = {
        "state": "READY_FOR_HANDOFF",
        "projection_sha256": _digest("stage3-projection-rev2"),
        "target_binding_sha256": _digest("stage3-target-binding"),
        "review_receipt_sha256": _digest("stage3-review-receipt"),
        "handoff_receipt_sha256": zero_sha256,
        "consume_receipt_sha256": zero_sha256,
        "created_at": "2026-08-03T00:03:00+00:00",
    }
    operation_payload_sha256 = _canonical_sha256(operation_payload)
    operation_event_id = (
        court_semantic_continuity.deterministic_result_recovery_event_id(
            operation_id, "review", operation_payload_sha256
        )
    )
    head_2 = court_semantic_continuity.build_result_recovery_head(
        quarantine_core=core_a,
        recovery_id=recovery_id,
        previous_head=head_1,
        state=operation_payload["state"],
        projection_sha256=operation_payload["projection_sha256"],
        target_binding_sha256=operation_payload["target_binding_sha256"],
        review_receipt_sha256=operation_payload["review_receipt_sha256"],
        handoff_receipt_sha256=operation_payload["handoff_receipt_sha256"],
        consume_receipt_sha256=operation_payload["consume_receipt_sha256"],
        operation_id=operation_id,
        event_id=operation_event_id,
        created_at=operation_payload["created_at"],
    )
    if (
        head_2.get("revision") != 2
        or head_2.get("previous_head_sha256") != head_1.get("head_sha256")
    ):
        raise AssertionError("STAGE3_RECOVERY_HEAD_REV2_CHAIN_DRIFT")
    if (
        court_semantic_continuity.validate_result_recovery_head(
            head_2,
            expected_revision=2,
            expected_head_sha256=head_2["head_sha256"],
        )
        != head_2
    ):
        raise AssertionError("STAGE3_RECOVERY_HEAD_REV2_NOT_CANONICAL")

    tampered_head = dict(head_2)
    tampered_head["projection_sha256"] = _digest("tampered-stage3-projection")
    expect_value_error(
        "result_recovery_head_digest_mismatch",
        lambda: court_semantic_continuity.validate_result_recovery_head(
            tampered_head
        ),
    )
    expect_value_error(
        "result_recovery_revision_conflict",
        lambda: court_semantic_continuity.validate_result_recovery_head(
            head_2,
            expected_revision=1,
            expected_head_sha256=head_2["head_sha256"],
        ),
    )
    expect_value_error(
        "result_recovery_head_conflict",
        lambda: court_semantic_continuity.validate_result_recovery_head(
            head_2,
            expected_revision=2,
            expected_head_sha256=head_1["head_sha256"],
        ),
    )
    if (
        court_semantic_continuity.result_recovery_record_disposition(head_2)
        != "CURRENT_RECOVERY_HEAD"
    ):
        raise AssertionError("STAGE3_VALID_RECOVERY_HEAD_DISPOSITION_DRIFT")

    applied = court_semantic_continuity.apply_result_recovery_operation(
        quarantine_core=core_a,
        current_head=head_1,
        operation_id=operation_id,
        action="review",
        payload=operation_payload,
        expected_revision=1,
        expected_head_sha256=head_1["head_sha256"],
    )
    if applied != head_2:
        raise AssertionError("STAGE3_RESULT_RECOVERY_APPLY_RESULT_DRIFT")
    replayed = court_semantic_continuity.apply_result_recovery_operation(
        quarantine_core=core_a,
        current_head=applied,
        operation_id=operation_id,
        action="review",
        payload=operation_payload,
        expected_revision=1,
        expected_head_sha256=head_1["head_sha256"],
    )
    if replayed != applied:
        raise AssertionError("STAGE3_RESULT_RECOVERY_OPERATION_REPLAY_DRIFT")

    changed_payload = dict(operation_payload)
    changed_payload["projection_sha256"] = _digest("stage3-projection-conflict")
    expect_value_error(
        "result_recovery_operation_conflict",
        lambda: court_semantic_continuity.apply_result_recovery_operation(
            quarantine_core=core_a,
            current_head=applied,
            operation_id=operation_id,
            action="review",
            payload=changed_payload,
            expected_revision=1,
            expected_head_sha256=head_1["head_sha256"],
        ),
    )
    expect_value_error(
        "result_recovery_revision_conflict",
        lambda: court_semantic_continuity.apply_result_recovery_operation(
            quarantine_core=core_a,
            current_head=applied,
            operation_id="OP-STAGE3-STALE-REVISION",
            action="review",
            payload=operation_payload,
            expected_revision=1,
            expected_head_sha256=applied["head_sha256"],
        ),
    )
    expect_value_error(
        "result_recovery_head_conflict",
        lambda: court_semantic_continuity.apply_result_recovery_operation(
            quarantine_core=core_a,
            current_head=applied,
            operation_id="OP-STAGE3-STALE-HEAD",
            action="review",
            payload=operation_payload,
            expected_revision=applied["revision"],
            expected_head_sha256=head_1["head_sha256"],
        ),
    )

    # Xingbu FAIL 3: identity/structure validation must not be digest-only.
    broken_head = dict(head_2)
    broken_head["operation_id"] = ""
    broken_head["head_sha256"] = _canonical_sha256(
        {key: item for key, item in broken_head.items() if key != "head_sha256"}
    )
    try:
        court_semantic_continuity.validate_result_recovery_head(broken_head)
    except ValueError as exc:
        if str(exc) != "result_recovery_head_identity_required":
            raise AssertionError(
                "STAGE3_XINGBU_FAIL3_WRONG_HEAD_ERROR " + str(exc)
            ) from exc
    else:
        raise AssertionError("STAGE3_XINGBU_FAIL3_EMPTY_OPERATION_ID_ACCEPTED")

    projection = court_semantic_continuity.build_result_recovery_projection(
        source_result=failed_source,
        recovery_id=recovery_id,
        quarantine_id=core_a["quarantine_id"],
    )
    tampered_projection = dict(projection)
    tampered_projection["semantic_epoch"] = 2
    tampered_projection["projection_sha256"] = _canonical_sha256(
        {
            key: item
            for key, item in tampered_projection.items()
            if key != "projection_sha256"
        }
    )
    try:
        court_semantic_continuity.validate_result_recovery_projection(
            tampered_projection,
            expected_core=core_a,
        )
    except ValueError as exc:
        if str(exc) != "result_recovery_projection_core_mismatch":
            raise AssertionError(
                "STAGE3_XINGBU_FAIL3_WRONG_PROJECTION_ERROR " + str(exc)
            ) from exc
    else:
        raise AssertionError(
            "STAGE3_XINGBU_FAIL3_PROJECTION_EPOCH_MISMATCH_ACCEPTED"
        )

    # Xingbu FAIL 2: missing carrier kind must fail closed, never default.
    kindless = dict(failed_source)
    kindless.pop("office_instance_kind", None)
    kindless.pop("carrier_proof", None)
    try:
        court_semantic_continuity.build_result_quarantine_core(
            source_result=kindless,
            source_final_status="failed",
            source_release_status="closed",
            source_result_state="QUARANTINED",
            reason_codes=["result_binding_mismatch"],
            received_at="2026-08-03T00:04:00+00:00",
        )
    except ValueError as exc:
        if str(exc) != "result_envelope_carrier_binding_required":
            raise AssertionError(
                "STAGE3_XINGBU_FAIL2_KINDLESS_CORE_WRONG_ERROR " + str(exc)
            ) from exc
    else:
        raise AssertionError("STAGE3_XINGBU_FAIL2_KINDLESS_CORE_DEFAULTED")
    try:
        court_semantic_continuity.build_result_recovery_projection(
            source_result=kindless,
            recovery_id=recovery_id,
            quarantine_id=core_a["quarantine_id"],
        )
    except ValueError as exc:
        if str(exc) != "result_recovery_projection_kind_required":
            raise AssertionError(
                "STAGE3_XINGBU_FAIL2_KINDLESS_PROJECTION_WRONG_ERROR " + str(exc)
            ) from exc
    else:
        raise AssertionError("STAGE3_XINGBU_FAIL2_KINDLESS_PROJECTION_DEFAULTED")


def check_stage3_xingbu_fail_gates() -> None:
    # FAIL 1: carrier fields must be compared for office/carrier-bound flows.
    binding = {
        "task_id": "t",
        "semantic_epoch": 1,
        "charter_sha256": _digest("c"),
        "invariant_capsule_sha256": _digest("i"),
        "checkpoint_id": "chk",
        "dispatch_uid": "d",
        "attempt": 1,
        "office_instance_id": "o",
        "agent_id": "internal-1",
        "role": "gongbu",
        "direct_superior": "shangshu",
        "worktree": "wt",
        "write_set": [],
        "office_instance_kind": "child_agent",
        "carrier_proof": {"agent_id": "internal-1"},
    }
    envelope = {
        "task_id": "t",
        "semantic_epoch": 1,
        "charter_sha256": _digest("c"),
        "invariant_capsule_sha256": _digest("i"),
        "checkpoint_id": "chk",
        "dispatch_uid": "d",
        "attempt": 1,
        "office_instance_id": "o",
        "agent_id": "internal-1",
        "role": "gongbu",
        "direct_superior": "shangshu",
        "worktree": "wt",
        "write_set_sha256": _canonical_sha256([]),
    }
    problems = court_semantic_continuity.result_binding_problems(
        dict(envelope), binding
    )
    if (
        "agent_result_binding_mismatch:office_instance_kind" not in problems
        or "agent_result_binding_mismatch:carrier_proof" not in problems
    ):
        raise AssertionError("STAGE3_XINGBU_FAIL1_CARRIER_FIELDS_NOT_COMPARED")
    full_envelope = dict(envelope)
    full_envelope["office_instance_kind"] = "child_agent"
    full_envelope["carrier_proof"] = {"agent_id": "internal-1"}
    if court_semantic_continuity.result_binding_problems(full_envelope, binding):
        raise AssertionError("STAGE3_XINGBU_FAIL1_MATCHING_CARRIER_REJECTED")
    plain_binding = {
        key: value
        for key, value in binding.items()
        if key not in {"office_instance_kind", "carrier_proof"}
    }
    if court_semantic_continuity.result_binding_problems(dict(envelope), plain_binding):
        raise AssertionError("STAGE3_XINGBU_FAIL1_PLAIN_AGENT_OVER_REJECTED")

    # FAIL 2: pre-adapt source hash must survive office adaptation.
    raw_a = {
        "schema": "court.office.result.v1",
        "agent_id": "raw-1",
        "office_instance_kind": "child_agent",
        "carrier_proof": {"agent_id": "raw-1"},
        "summary": "same",
    }
    raw_b = {
        "schema": "court.office.result.v1",
        "agent_id": "raw-2",
        "office_instance_kind": "child_agent",
        "carrier_proof": {"agent_id": "raw-2"},
        "summary": "same",
    }
    hash_a = court_semantic_continuity.source_result_payload_sha256(raw_a)
    hash_b = court_semantic_continuity.source_result_payload_sha256(raw_b)
    if hash_a == hash_b:
        raise AssertionError("STAGE3_XINGBU_FAIL2_RAW_AGENT_HASH_BLIND")
    record = {
        "office_instance_kind": "child_agent",
        "carrier_proof": {"agent_id": "internal-1"},
        "worktree": "wt",
    }
    adapt_args = Namespace(result_envelope=dict(raw_a), result_envelope_file=None)
    court_runtime._adapt_office_result_envelope(adapt_args, record, "internal-1")
    if adapt_args._source_result_payload_sha256 != hash_a:
        raise AssertionError("STAGE3_XINGBU_FAIL2_PRE_ADAPT_HASH_NOT_STASHED")
    if adapt_args._original_result_envelope.get("agent_id") != "raw-1":
        raise AssertionError("STAGE3_XINGBU_FAIL2_ORIGINAL_ENVELOPE_LOST")
    if adapt_args.result_envelope.get("agent_id") not in {
        "internal-1",
        "internal-1-stale-proof",
    }:
        raise AssertionError("STAGE3_XINGBU_FAIL2_ADAPT_ENVELOPE_UNEXPECTED")

    # FAIL 4: recovery notes scrubbed and journal preimages privacy-gated.
    scrubbed = court_runtime.scrub_agent_provider_detail(
        "note https://provider.example request_id=abc api_key=secret balance=100"
    )
    if (
        "secret" in scrubbed
        or "provider.example" in scrubbed
        or "abc" in scrubbed
        or "100" in scrubbed
    ):
        raise AssertionError("STAGE3_XINGBU_FAIL4_NOTE_NOT_SCRUBBED")
    if (
        court_runtime._journal_preimage_privacy_violation(
            b'{"task_id":"t","task":{"body":"secret"}}'
        )
        is None
    ):
        raise AssertionError("STAGE3_XINGBU_FAIL4_PREIMAGE_PRIVATE_KEY_ACCEPTED")
    if (
        court_runtime._journal_preimage_privacy_violation(
            b'{"task_id":"t","task":{"summary":"ok"}}'
        )
        is not None
    ):
        raise AssertionError("STAGE3_XINGBU_FAIL4_CLEAN_PREIMAGE_REJECTED")


def evaluate() -> dict[str, object]:
    checks = (
        ("PUBLIC_INVARIANT_CAPSULE_CONTRACT", check_public_invariant_capsule_contract),
        (
            "STAGE3_RESULT_RECOVERY_PURE_SCHEMA_CORE_HEAD_IDEMPOTENCY_RED",
            check_stage3_result_recovery_pure_schema_core_head_idempotency_red,
        ),
        ("STAGE3_XINGBU_FAIL_GATES", check_stage3_xingbu_fail_gates),
        ("F-RED-002_CREATE_BINDING", check_create_initializes_atomic_semantic_binding),
        ("F-RED-002_CORRECTION_BINDING", check_correction_requires_and_binds_charter_body),
        ("SEMANTIC_CHECKPOINT_VERIFY", check_checkpoint_verify_promotes_dispatchable),
        ("SEMANTIC_DRIFT_QUARANTINE", check_drift_is_quarantined_before_mutation),
        ("SEMANTIC_AGENT_BINDING", check_dispatch_start_report_bind_current_receipt),
        (
            "SEMANTIC_RESULT_ENVELOPE",
            check_finish_requires_structured_result_and_quarantines_stale,
        ),
        (
            "SEMANTIC_CORRECTION_INVALIDATION",
            check_correction_invalidates_all_derived_state_append_only,
        ),
        ("SEMANTIC_RESUME", check_semantic_resume_preserves_epoch_and_requires_reverify),
        (
            "SEMANTIC_RESTORE_TRIGGERS",
            check_compaction_reboot_idle_reuse_immutable_receipt,
        ),
        (
            "SEMANTIC_CAPSULE_AND_MULTISOURCE_DRIFT",
            check_incomplete_capsule_and_multisource_drift_fail_closed,
        ),
        (
            "F-CRASH-003",
            check_f_crash_003_paired_ledger_recovery_and_replay,
        ),
        (
            "LEGACY_V2_V3_DIAGNOSTIC_ONLY",
            check_legacy_v2_v3_are_diagnostic_only_until_semantically_bound,
        ),
        (
            "SEMANTIC_CLI_CHECKPOINT",
            check_semantic_checkpoint_cli_is_json_and_machine_stable,
        ),
        (
            "SEMANTIC_CLI_VERIFY",
            check_semantic_verify_cli_success_and_drift_exit_codes,
        ),
        (
            "SEMANTIC_CLI_CORRECT",
            check_semantic_correct_cli_binds_body_and_reverify_state,
        ),
        (
            "SEMANTIC_CLI_RESUME",
            check_semantic_resume_cli_returns_to_review_without_epoch_change,
        ),
        (
            "SEMANTIC_CLI_QUARANTINE",
            check_semantic_quarantine_cli_is_bound_and_append_only,
        ),
        (
            "SEMANTIC_CLI_RECONCILE",
            check_semantic_reconcile_cli_requires_restored_sources_then_reverify,
        ),
        (
            "DECREE_OPEN_IDEMPOTENT",
            check_decree_open_is_idempotent_concurrent_and_crash_recoverable,
        ),
        (
            "OPERATION_JOURNAL_RMW_SERIALIZATION",
            check_operation_journal_rmw_is_serialized,
        ),
        (
            "SYNTHETIC_CLOSEOUT_SAGA",
            check_synthetic_closeout_saga_recovers_all_side_effect_killpoints,
        ),
        (
            "OPERATION_CLI",
            check_operation_cli_exposes_decree_open_and_closeout_recovery,
        ),
        (
            "P1_A_CORRECTION_CAPSULE",
            check_p1_a_correction_requires_new_canonical_capsule,
        ),
        (
            "P1_B_IMMUTABLE_RECEIPTS",
            check_p1_b_semantic_receipts_are_immutable_across_revisions,
        ),
        (
            "P1_C_RECEIPT_INTEGRITY",
            check_p1_c_checkpoint_receipt_tamper_table_fails_closed,
        ),
        (
            "P00_CONTEXT_PACKET_CONTINUITY",
            check_p00_bounded_context_packet_preserves_semantic_continuity,
        ),
    )
    passed: list[str] = []
    for case_id, check in checks:
        try:
            check()
        except Exception as exc:
            return {
                "ok": False,
                "schema": "court.semantic_continuity.check.v1",
                "sentinel": "SEMANTIC_BINDING_CORE_RED",
                "failed_case": case_id,
                "error": str(exc),
                "passed_cases": passed,
                "pending_body_access": "NO",
            }
        passed.append(case_id)
    return {
        "ok": True,
        "schema": "court.semantic_continuity.check.v1",
        "sentinel": "SEMANTIC_BINDING_CORE_PASS",
        "passed_cases": passed,
        "pending_body_access": "NO",
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in args
    result = evaluate()
    if json_mode:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif result["ok"]:
        print(result["sentinel"])
    else:
        print(f"{result['sentinel']} {result['failed_case']}: {result['error']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

