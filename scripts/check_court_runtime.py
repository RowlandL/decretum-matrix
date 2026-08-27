"""Self-test the local /court runtime state machine without touching real tasks."""

from __future__ import annotations

from argparse import Namespace
from copy import deepcopy
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True

import court_runtime
from court_office_bootstrap import (
    build_child_office_profile,
    canonical_child_office_binding_sha256,
)
from court_multi_agent_protocol import (
    ProtocolRequirements,
    QuiescenceSnapshot,
    assess_quiescence,
    admit_roles,
    build_exact_resume_command,
    render_protocol_config,
    select_protocol,
    validate_session_id,
    validate_protocol_config,
)
from court_codex_protocol_launcher import ProtocolSwitchLedger, SwitchInProgress, execute_switch
from check_court_agent_lifecycle import (
    context_budget_pool,
    dispatch_context_packet,
    run_agent_lifecycle_checks,
)
import report_office_startup_latency as startup_latency


def formal_gate_fixture(*, mutates_state: bool = False) -> dict[str, object]:
    return {
        "schema": "court.conversation_gate.v1",
        "active_decree": False,
        "active_decree_state": "NONE",
        "message_class": "FORMAL_TASK",
        "confidence": "HIGH",
        "relation_to_active_decree": "NONE",
        "taskization_consent": "EXPLICIT",
        "requires_tools": True,
        "mutates_state": mutates_state,
        "risk_present": False,
        "next_route": "THREE_DEPARTMENTS",
        "question": "",
        "rationale": "self-test formal court task",
        "understanding": deepcopy(
            court_runtime.minimal_formal_task_example()["understanding"]
        ),
    }


def create_args(task_id: str, *, intake_gate: object, work_kind: str = "audit") -> Namespace:
    charter = "formal runtime schema fixture"
    charter_sha256 = hashlib.sha256(charter.encode("utf-8")).hexdigest()
    return Namespace(
        title=task_id,
        charter=charter,
        task_id=task_id,
        owner="taizi",
        report_tier="brief",
        evidence=f"create {task_id}",
        note="runtime schema fixture",
        work_kind=work_kind,
        intake_gate=intake_gate,
        intake_file=None,
        invariant_capsule={
            "schema": "court.semantic.invariant_capsule.v1",
            "latest_decree_anchor": charter,
            "latest_decree_sha256": charter_sha256,
            "non_goals": ["do not mutate real runtime state"],
            "boundaries": ["TemporaryDirectory fixture only"],
            "allowed_actions": ["synthetic runtime verification"],
            "forbidden_actions": ["real Shiguan access"],
            "acceptance": ["runtime checker passes"],
            "evidence_requirements": ["machine-readable receipt"],
            "stop_gates": ["semantic drift"],
            "write_set": ["scripts/check_court_runtime.py"],
            "governing_hashes": {"fixture": charter_sha256},
            "charter_sha256": charter_sha256,
        },
        invariant_capsule_file=None,
    )


def _semantic_context_fixture() -> dict[str, object]:
    digest = lambda label: hashlib.sha256(label.encode("utf-8")).hexdigest()
    return {
        "authority_revision": 1,
        "authority_sha256": digest("runtime-authority"),
        "plan_revision": 1,
        "plan_sha256": digest("runtime-plan"),
        "plan_cursor": "runtime-checker",
        "git_fingerprint": "runtime-checker-head",
        "recovery_checkpoint_id": "runtime-checker-recovery",
        "shiguan_revision": 0,
        "shiguan_fingerprint": digest("runtime-synthetic-shiguan"),
    }


def _make_task_dispatchable(task_id: str) -> dict[str, object]:
    context = _semantic_context_fixture()
    common = dict(
        task_id=task_id,
        semantic_context=context,
        semantic_context_file=None,
        actor="taizi",
        evidence="runtime semantic dispatch fixture",
        note="runtime semantic dispatch fixture",
    )
    court_runtime.semantic_checkpoint_task(
        Namespace(**common, trigger="checkpoint")
    )
    return court_runtime.semantic_verify_task(
        Namespace(**common, trigger="verify")
    ).task


def _bind_admission_args(args: Namespace, task: dict[str, object]) -> Namespace:
    receipt = task["semantic_receipt"]
    args.expected_semantic_epoch = task["semantic_epoch"]
    args.expected_charter_sha256 = task["charter_sha256"]
    args.expected_invariant_capsule_sha256 = task["invariant_capsule_sha256"]
    args.expected_checkpoint_id = receipt["checkpoint_id"]
    bindings = json.loads(args.requested_bindings_json)
    for binding in bindings:
        if binding.pop("child_profile", None) is None:
            continue
        role = str(binding["role"])
        binding.update(
            child_role="GongBu-GongJiang" if role == "gongbu" else f"{role}-worker",
            bounded_mandate="execute one synthetic runtime admission shard",
            expected_result="return one bounded runtime admission receipt",
            terminal_condition="stop after the synthetic admission is evaluated",
        )
    lease = json.loads(args.budget_lease_json)
    lease.pop("approved_binding_sha256s", None)
    args.requested_bindings_json = json.dumps(bindings, ensure_ascii=False)
    args.budget_lease_json = json.dumps(lease, ensure_ascii=False)
    args.dispatch_context_packet = dispatch_context_packet(task, args.wave_id)
    args.context_budget_pool = context_budget_pool(str(task["task_id"]), args.wave_id)
    args.context_result_mode = "bounded_structured_receipt"
    args.context_tool_output_mode = "pointer"
    args.context_override_source = None
    args._context_contract_required = True
    return args


def _public_admission_fixture(
    *,
    task_id: str,
    roles: tuple[str, ...],
    integration_domain: str,
    approved_count: int | None = None,
    calling_office: str = "shangshu",
    worker_only: bool = False,
    next_depth: int = 2,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    normalized_roles = court_runtime.parse_requested_roles(roles, len(roles))
    count = len(normalized_roles) if approved_count is None else approved_count
    if count < 1 or count > len(normalized_roles):
        raise ValueError("approved fixture count is outside the requested role set")
    direct_superiors = {
        "taizi": "user",
        "zhongshu": "taizi",
        "menxia": "taizi",
        "shangshu": "taizi",
        "libu-hr": "shangshu",
        "hubu": "shangshu",
        "libu": "shangshu",
        "bingbu": "shangshu",
        "xingbu": "shangshu",
        "gongbu": "shangshu",
        "shiguan": "taizi/menxia",
    }
    ministry_roles = {"libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"}
    role_counts: dict[str, int] = {}
    bindings: list[dict[str, object]] = []
    for index, role in enumerate(normalized_roles):
        role_counts[role] = role_counts.get(role, 0) + 1
        role_number = role_counts[role]
        instance_id = f"{role}#{role_number:04d}"
        worker = role in ministry_roles and (worker_only or role_number > 1)
        try:
            preload_hashes = court_runtime._semantic_preload_hashes(role)
        except ValueError:
            preload_hashes = {
                "profile_hash": "1" * 64,
                "dossier_hash": "2" * 64,
                "court_skill_hash": "3" * 64,
            }
        binding: dict[str, object] = {
            "role": role,
            "instance_id": instance_id,
            "shard_id": f"{role}-shard-{role_number:04d}",
            "direct_superior": role if worker else direct_superiors.get(role, "shangshu"),
            "instance_kind": "office_worker_instance" if worker else "office",
            "canonical_authority": False if worker else role_number == 1,
            "owner_role": role if worker else None,
            "write_set": [f"work/{role}/{role_number:04d}.txt"],
            "access_mode": "read_write",
            "read_scope": [f"work/{role}/{role_number:04d}.txt"],
            "mutation_allowed": True,
            "integration_authority": False,
            "preload_hashes": dict(preload_hashes),
        }
        if worker:
            child_profile = dict(
                build_child_office_profile(
                    {
                        **binding,
                        "task_id": task_id,
                        "dispatch_uid": f"DSP-{task_id}-{role_number:04d}",
                        "attempt": 1,
                        "bounded_mandate": "execute one synthetic runtime admission shard",
                        "expected_result": "return one bounded runtime admission receipt",
                        "terminal_condition": "stop after the synthetic admission is evaluated",
                    },
                    child_role="GongBu-GongJiang" if role == "gongbu" else f"{role}-worker",
                    profile_sha256=preload_hashes["profile_hash"],
                    dossier_sha256=preload_hashes["dossier_hash"],
                    skill_sha256=preload_hashes["court_skill_hash"],
                    dispatch_context_packet_sha256="4" * 64,
                    semantic_receipt_sha256="5" * 64,
                    invariant_capsule_sha256="6" * 64,
                    expires_at_utc="2099-01-01T00:00:00Z",
                )
            )
            binding["child_profile"] = child_profile
            for outer_field, profile_field in {
                "child_role": "child_role",
                "bounded_mandate": "bounded_mandate",
                "expected_result": "expected_result",
                "task_id": "task_id",
                "dispatch_uid": "dispatch_uid",
                "attempt": "attempt",
                "expires_at_utc": "expires_at_utc",
                "terminal_condition": "terminal_condition",
            }.items():
                binding[outer_field] = child_profile[profile_field]
        bindings.append(binding)
    approved = bindings[:count]
    budget_id = f"budget:{task_id}:phase:wave"
    lease_superior = direct_superiors.get(calling_office, "taizi")
    lease: dict[str, object] = {
        "schema": "court.agent.admission_lease.v2",
        "budget_id": budget_id,
        "status": "ACTIVE",
        "lease_id": f"{task_id}-lease-{count}",
        "parent_budget_id": f"{budget_id}:{lease_superior}",
        "parent_id": lease_superior,
        "approved_by": lease_superior,
        "grantee_role": calling_office,
        "lease_depth": max(0, next_depth - 1),
        "approved_next_depth": next_depth,
        "expires_at_utc": "2099-01-01T00:00:00+00:00",
        "parent_write_scope": ["work"],
        "approved_count": count,
        "task_id": task_id,
        "calling_office": calling_office,
        "direct_superior": direct_superiors.get(calling_office, "taizi"),
        "integration_domain": integration_domain,
        "authority": "super",
        "approved_roles": [binding["role"] for binding in approved],
        "approved_instance_ids": [binding["instance_id"] for binding in approved],
        "approved_shards": [binding["shard_id"] for binding in approved],
        "approved_write_sets": {
            str(binding["instance_id"]): list(binding["write_set"]) for binding in approved
        },
        "approved_access_contracts": {
            str(binding["instance_id"]): {
                "access_mode": binding["access_mode"],
                "read_scope": list(binding["read_scope"]),
                "mutation_allowed": binding["mutation_allowed"],
                "integration_authority": binding["integration_authority"],
            }
            for binding in approved
        },
        "approved_instance_shapes": {
            str(binding["instance_id"]): {
                "instance_kind": binding["instance_kind"],
                "canonical_authority": binding["canonical_authority"],
                "owner_role": binding["owner_role"],
                "direct_superior": binding["direct_superior"],
            }
            for binding in approved
        },
        "approved_binding_sha256s": {
            str(binding["instance_id"]): canonical_child_office_binding_sha256(
                binding
            )
            for binding in approved
            if isinstance(binding.get("child_profile"), dict)
        },
        "approved_preload_hashes": {
            str(binding["instance_id"]): dict(binding["preload_hashes"])
            for binding in approved
        },
    }
    return lease, bindings


def _public_admission_fields(
    *,
    task_id: str,
    roles: tuple[str, ...],
    integration_domain: str,
    approved_count: int | None = None,
    calling_office: str = "shangshu",
    next_depth: int = 1,
) -> dict[str, object]:
    lease, bindings = _public_admission_fixture(
        task_id=task_id,
        roles=roles,
        integration_domain=integration_domain,
        approved_count=approved_count,
        calling_office=calling_office,
        next_depth=next_depth,
    )
    return {
        "budget_lease_json": json.dumps(lease, ensure_ascii=False),
        "requested_bindings_json": json.dumps(bindings, ensure_ascii=False),
        "integration_domain": integration_domain,
        "authority": "super",
        "calling_office": lease["calling_office"],
        "direct_superior": lease["direct_superior"],
    }


def _cardinality_fixture(*, approved_count: int = 17) -> tuple[dict[str, object], list[dict[str, object]]]:
    return _public_admission_fixture(
        task_id="runtime-cardinality",
        roles=tuple("gongbu" for _ in range(17)),
        integration_domain="runtime-cardinality",
        approved_count=approved_count,
        calling_office="gongbu",
        worker_only=True,
    )


def _cardinality_args(
    *,
    approved_count: int = 17,
    explicit_count: int | None = None,
    unlimited: bool = False,
    control_source: str | None = None,
    memory_percent: float = 40.0,
) -> Namespace:
    lease, bindings = _cardinality_fixture(approved_count=approved_count)
    argv = [
        "agent-admit",
        "--task-id", "runtime-cardinality",
        "--wave-id", "runtime-cardinality-wave",
        "--execution-topology", "parallel",
        "--protocol-mode", "v2",
        "--active-session-protocol", "v2",
        "--requested-fork-turns", "none",
        "--context-tokens", "1000",
        "--message-chars", "100",
        "--requested-agents", "17",
        "--requested-roles", ",".join("gongbu" for _ in range(17)),
        "--host-active-agents", "1",
        "--host-capacity", "48",
        "--host-retained-agents", "0",
        "--host-reclamation-status", "verified",
        "--next-depth", "2",
        "--max-depth", "4",
        "--max-threads", "48",
        "--budget-lease-json", json.dumps(lease, ensure_ascii=False),
        "--requested-bindings-json", json.dumps(bindings, ensure_ascii=False),
        "--integration-domain", "runtime-cardinality",
        "--authority", "super",
        "--calling-office", "gongbu",
        "--direct-superior", "shangshu",
        "--assignment", "cardinality tracer",
        "--task-focus", "runtime admission",
        "--complexity", "medium",
        "--risk", "low",
        "--ambiguity", "low",
        "--transport", "codex",
        "--evidence", "synthetic public parser tracer",
        "--system-memory-percent", str(memory_percent),
    ]
    if explicit_count is not None:
        argv.extend(("--explicit-parallel-count", str(explicit_count)))
    if unlimited:
        argv.append("--parallel-unlimited")
    if control_source is not None:
        argv.extend(("--parallel-control-source", control_source))
    return court_runtime.build_parser().parse_args(argv)


def _cardinality_create_args() -> Namespace:
    args = create_args(
        "runtime-cardinality",
        intake_gate=formal_gate_fixture(mutates_state=True),
    )
    args.invariant_capsule["write_set"] = [
        f"work/gongbu/{index:04d}.txt" for index in range(1, 18)
    ]
    return args


def check_runtime_parallel_cardinality() -> None:
    task = {"task_id": "runtime-cardinality", "agents": {}}

    default = court_runtime.evaluate_agent_admission(task, _cardinality_args())
    assert len(default["selected_roles"]) == 15

    explicit_17 = court_runtime.evaluate_agent_admission(
        task,
        _cardinality_args(explicit_count=17, control_source="current_user_explicit"),
    )
    assert len(explicit_17["selected_roles"]) == 16

    explicit_18 = court_runtime.evaluate_agent_admission(
        task,
        _cardinality_args(explicit_count=18, control_source="current_user_explicit"),
    )
    assert len(explicit_18["selected_roles"]) == 17

    unlimited = court_runtime.evaluate_agent_admission(
        task,
        _cardinality_args(unlimited=True, control_source="current_user_explicit"),
    )
    assert len(unlimited["selected_roles"]) == 17

    for source in (None, "prior_memory"):
        stale = court_runtime.evaluate_agent_admission(
            task,
            _cardinality_args(explicit_count=18, control_source=source),
        )
        assert stale["allowed"] is False
        assert "parallel_override_not_current_user_explicit" in stale["selection_basis"]
        assert stale["selected_bindings"] == ()
        assert stale["selected_instance_ids"] == ()

    bounded = court_runtime.evaluate_agent_admission(task, _cardinality_args(approved_count=5))
    assert len(bounded["selected_roles"]) == 5

    pressure = court_runtime.evaluate_agent_admission(
        task,
        _cardinality_args(
            explicit_count=18,
            control_source="current_user_explicit",
            memory_percent=99.0,
        ),
    )
    assert len(pressure["selected_roles"]) == 15


def check_runtime_instance_keyed_routes() -> None:
    with tempfile.TemporaryDirectory(prefix="court-runtime-instance-routes-") as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_cardinality_create_args())
            task = _make_task_dispatchable("runtime-cardinality")
            admission = court_runtime.agent_admit(
                _bind_admission_args(_cardinality_args(approved_count=3), task)
            )
            assert tuple(admission["model_routes"]) == (
                "gongbu#0001",
                "gongbu#0002",
                "gongbu#0003",
            )
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def _instance_start_args(
    *,
    instance_id: str,
    agent_id: str,
    dispatch_requested_at: str,
) -> Namespace:
    skill_path = Path(court_runtime.__file__).resolve().parents[1] / "SKILL.md"
    skill_hash = hashlib.sha256(skill_path.read_bytes()).hexdigest()
    suffix = instance_id.split("#", 1)[-1]
    args = court_runtime.build_parser().parse_args(
        [
            "agent-start",
            "--task-id", "runtime-cardinality",
            "--agent-id", agent_id,
            "--instance-id", instance_id,
            "--role", "gongbu",
            "--collaboration-task-name", f"gongbu_rc1_{suffix}",
            "--skill-requirements-json",
            json.dumps(
                [
                    {
                        "name": "decretum-matrix",
                        "source": str(skill_path.resolve()),
                        "sha256": skill_hash,
                        "purpose": "RC1 instance-keyed runtime tracer",
                        "ack_name": "decretum-matrix",
                        "ack_sha256": skill_hash,
                    }
                ]
            ),
            "--scope", "cardinality tracer",
            "--task-focus", "runtime admission",
            "--complexity", "medium",
            "--risk", "low",
            "--ambiguity", "low",
            "--transport", "codex",
            "--wave-id", "runtime-cardinality-wave",
            "--dispatch-requested-at", dispatch_requested_at,
            "--fork-turns", "none",
            "--context-tokens", "1000",
            "--actor", "shangshu",
            "--evidence", f"start {instance_id}",
        ]
    )
    task = court_runtime.load_tasks()["runtime-cardinality"]
    admission = task["agent_admissions"]["runtime-cardinality-wave"]
    bindings = admission["selected_bindings"]
    binding = next(
        item for item in bindings if item.get("instance_id") == instance_id
    )
    for field in court_runtime.AGENT_SEMANTIC_ARG_FIELDS:
        setattr(args, field, binding[field])
    args.dispatch_context_packet = dispatch_context_packet(
        task,
        "runtime-cardinality-wave",
    )
    args.context_budget_pool = context_budget_pool(
        str(task["task_id"]),
        "runtime-cardinality-wave",
    )
    args.context_result_mode = binding["context_result_mode"]
    args.context_tool_output_mode = binding["context_tool_output_mode"]
    args.context_override_source = binding["context_override_source"]
    args.system_memory_percent = binding["context_system_memory_percent"]
    args._context_contract_required = True
    return args


def _spawn_failed_args(*, instance_id: str | None) -> Namespace:
    argv = [
        "agent-spawn-failed",
        "--task-id", "runtime-cardinality",
        "--wave-id", "runtime-cardinality-wave",
        "--role", "gongbu",
        "--error-kind", "retryable",
        "--result", "synthetic host refusal",
        "--actor", "shangshu",
        "--evidence", "RC1 instance-keyed spawn failure tracer",
    ]
    if instance_id is not None:
        argv.extend(("--instance-id", instance_id))
    return court_runtime.build_parser().parse_args(argv)


def check_runtime_instance_keyed_spawn_failure() -> None:
    with tempfile.TemporaryDirectory(prefix="court-runtime-instance-failure-") as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_cardinality_create_args())
            task = _make_task_dispatchable("runtime-cardinality")
            court_runtime.agent_admit(
                _bind_admission_args(_cardinality_args(approved_count=3), task)
            )
            try:
                court_runtime.agent_spawn_failed(_spawn_failed_args(instance_id=None))
            except ValueError as exc:
                assert "instance-id" in str(exc)
            else:
                raise AssertionError("multi-instance spawn-failed accepted without instance-id")

            first = court_runtime.agent_spawn_failed(
                _spawn_failed_args(instance_id="gongbu#0001")
            )
            second = court_runtime.agent_spawn_failed(
                _spawn_failed_args(instance_id="gongbu#0002")
            )
            assert first["failed_instance_id"] == "gongbu#0001"
            assert second["failed_instance_id"] == "gongbu#0002"
            task = court_runtime.load_tasks()["runtime-cardinality"]
            stored = task["agent_admissions"]["runtime-cardinality-wave"]
            assert tuple(stored["failed_instances"]) == ("gongbu#0001", "gongbu#0002")
            assert "gongbu#0003" not in stored["failed_instances"]
            assert stored.get("consumed_instances", {}) == {}
            for instance_id in ("gongbu#0001", "gongbu#0002"):
                assert stored["failed_instances"][instance_id]["model_route_id"] == (
                    stored["model_routes"][instance_id]["model_route_id"]
                )
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    with tempfile.TemporaryDirectory(prefix="court-runtime-unique-failure-") as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_cardinality_create_args())
            task = _make_task_dispatchable("runtime-cardinality")
            court_runtime.agent_admit(
                _bind_admission_args(_cardinality_args(approved_count=1), task)
            )
            inferred = court_runtime.agent_spawn_failed(
                _spawn_failed_args(instance_id=None)
            )
            assert inferred["failed_instance_id"] == "gongbu#0001"
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_runtime_instance_keyed_consumption() -> None:
    with tempfile.TemporaryDirectory(prefix="court-runtime-instance-consumption-") as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_cardinality_create_args())
            task = _make_task_dispatchable("runtime-cardinality")
            admission = court_runtime.agent_admit(
                _bind_admission_args(_cardinality_args(approved_count=3), task)
            )
            dispatch_requested_at = str(admission["dispatch_requested_at"])
            court_runtime.agent_start(
                _instance_start_args(
                    instance_id="gongbu#0001",
                    agent_id="gongbu-0001",
                    dispatch_requested_at=dispatch_requested_at,
                )
            )
            court_runtime.agent_start(
                _instance_start_args(
                    instance_id="gongbu#0002",
                    agent_id="gongbu-0002",
                    dispatch_requested_at=dispatch_requested_at,
                )
            )
            task = court_runtime.load_tasks()["runtime-cardinality"]
            stored = task["agent_admissions"]["runtime-cardinality-wave"]
            assert stored["consumed_instances"] == {
                "gongbu#0001": "gongbu-0001",
                "gongbu#0002": "gongbu-0002",
            }
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def assert_create_rejected_before_lock(args: Namespace, expected: str) -> None:
    original_runtime_lock = court_runtime.runtime_lock

    def forbidden_lock(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("formal intake validation acquired the runtime lock")

    court_runtime.runtime_lock = forbidden_lock  # type: ignore[assignment]
    try:
        try:
            court_runtime.create_task(args)
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError("invalid formal intake was accepted")
    finally:
        court_runtime.runtime_lock = original_runtime_lock  # type: ignore[assignment]


def canonical_task_bytes(task: dict[str, object]) -> bytes:
    return json.dumps(task, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def expected_legacy_normalization(task: dict[str, object]) -> dict[str, object]:
    normalized = dict(task)
    normalized["migrated_from_runtime_schema_version"] = int(
        normalized.get("runtime_schema_version") or 2
    )
    normalized["runtime_schema_version"] = 3
    normalized.setdefault("work_kind", "legacy")
    normalized.setdefault(
        "conversation_gate",
        {
            "schema": "court.conversation_gate.legacy.v1",
            "active_decree": False,
            "active_decree_state": "NONE",
            "message_class": "LEGACY_UNCLASSIFIED",
            "confidence": "LOW",
            "relation_to_active_decree": "UNCLEAR",
            "taskization_consent": "PENDING",
            "requires_tools": False,
            "mutates_state": False,
            "risk_present": False,
            "next_route": "SINGLE_QUESTION",
            "question": "",
            "rationale": "legacy runtime task requires revise-charter before new work",
            "creatable": False,
            "revisable": False,
        },
    )
    normalized.setdefault("charter_revision_history", [])
    normalized.setdefault(
        "outcome_assessment",
        {
            "schema": "court.outcome_assessment.v1",
            "gate": "UNASSESSED",
            "reasons": [],
            "outcome": None,
        },
    )
    normalized.setdefault("shiguan_checkpoint", {})
    normalized.setdefault("completion", {"status": "UNASSESSED"})
    normalized.setdefault("agent_runtime", court_runtime.default_agent_runtime())
    normalized.setdefault("stop_condition", "")
    normalized.setdefault("unsafe_remaining", "")
    normalized.setdefault("evidence_preserved", "")
    normalized.setdefault("agents", {})
    return normalized


def check_runtime_schema_v3_intake_and_migration() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            assert_create_rejected_before_lock(
                create_args("missing-intake", intake_gate=None),
                "formal conversation gate is required",
            )
            non_formal_gate = {
                **formal_gate_fixture(),
                "message_class": "TRIVIAL_DIRECT",
                "taskization_consent": "NOT_REQUIRED",
                "requires_tools": False,
                "next_route": "DIRECT_ANSWER",
            }
            assert_create_rejected_before_lock(
                create_args("invalid-intake", intake_gate=non_formal_gate),
                "new_formal_task_gate_required",
            )

            created = court_runtime.create_task(
                create_args("schema-v3", intake_gate=formal_gate_fixture())
            )
            assert created.task["runtime_schema_version"] == 3
            assert created.task["work_kind"] == "audit"
            assert created.task["conversation_gate"]["message_class"] == "FORMAL_TASK"
            assert created.task["charter_revision_history"] == []
            assert created.task["outcome_assessment"] == {
                "schema": "court.outcome_assessment.v1",
                "gate": "UNASSESSED",
                "reasons": [],
                "outcome": None,
            }
            assert created.task["shiguan_checkpoint"] == {}
            assert created.task["completion"] == {"status": "UNASSESSED"}
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            raw_legacy: dict[str, object] = {
                "runtime_schema_version": 2,
                "task_id": "legacy-task",
                "title": "legacy fixture",
                "charter": "legacy charter",
                "state": "Pending",
                "owner": "taizi",
                "report_tier": "brief",
                "last_evidence": "legacy evidence",
            }
            path = court_runtime.tasks_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"legacy-task": raw_legacy}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            before_read = path.read_bytes()
            normalized = court_runtime.load_tasks()["legacy-task"]
            assert normalized == expected_legacy_normalization(raw_legacy)
            assert path.read_bytes() == before_read
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    raw_missing_version: dict[str, object] = {
        "task_id": "missing-version-legacy-task",
        "title": "missing version legacy fixture",
        "state": "Pending",
    }
    normalized_missing_version = court_runtime.normalize_task(raw_missing_version)
    assert normalized_missing_version == expected_legacy_normalization(raw_missing_version)
    assert "runtime_schema_version" not in raw_missing_version

    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            raw_legacy = {
                "runtime_schema_version": 2,
                "task_id": "legacy-task",
                "title": "legacy fixture",
                "charter": "legacy charter",
                "state": "Pending",
                "owner": "taizi",
                "report_tier": "brief",
                "last_evidence": "legacy evidence",
            }
            raw_target = {
                "runtime_schema_version": 3,
                "task_id": "target-task",
                "title": "target fixture",
                "charter": "target charter",
                "state": "Pending",
                "owner": "taizi",
                "report_tier": "brief",
                "last_evidence": "target evidence",
                "work_kind": "audit",
                "conversation_gate": formal_gate_fixture(),
                "charter_revision_history": [],
                "outcome_assessment": {
                    "schema": "court.outcome_assessment.v1",
                    "gate": "UNASSESSED",
                    "reasons": [],
                    "outcome": None,
                },
                "shiguan_checkpoint": {},
                "completion": {"status": "UNASSESSED"},
                "agent_runtime": court_runtime.default_agent_runtime(),
                "stop_condition": "",
                "unsafe_remaining": "",
                "evidence_preserved": "",
                "agents": {},
            }
            path = court_runtime.tasks_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {"legacy-task": raw_legacy, "target-task": raw_target},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            tasks = {
                "legacy-task": expected_legacy_normalization(raw_legacy),
                "target-task": {**raw_target, "last_evidence": "unrelated target mutation"},
            }
            court_runtime.write_tasks(tasks)
            persisted = json.loads(path.read_text(encoding="utf-8"))
            assert canonical_task_bytes(persisted["legacy-task"]) == canonical_task_bytes(raw_legacy)
            assert "work_kind" not in persisted["legacy-task"]
            assert "migrated_from_runtime_schema_version" not in persisted["legacy-task"]
            assert persisted["target-task"]["last_evidence"] == "unrelated target mutation"
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_future_runtime_schema_rejected() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            future_task = {
                "runtime_schema_version": 4,
                "task_id": "future-task",
                "title": "future fixture",
                "charter": "must remain opaque to this runtime",
                "state": "Pending",
                "owner": "taizi",
                "report_tier": "brief",
                "future_payload": {"preserve": ["exactly"]},
            }
            path = court_runtime.tasks_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"future-task": future_task}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            before_tasks = path.read_bytes()
            events = court_runtime.events_path()
            assert not events.exists()
            try:
                court_runtime.create_task(
                    create_args("unrelated-create", intake_gate=formal_gate_fixture())
                )
            except ValueError as exc:
                assert str(exc) == "unsupported runtime schema version 4; maximum supported is 3"
            else:
                raise AssertionError("future runtime schema was normalized and persisted as v3")
            assert path.read_bytes() == before_tasks
            assert not events.exists()
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_malformed_task_entries_rejected() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            path = court_runtime.tasks_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"malformed-target": ["opaque", {"preserve": True}]}, indent=2)
                + "\n",
                encoding="utf-8",
            )
            before_tasks = path.read_bytes()
            try:
                court_runtime.load_tasks()
            except ValueError as exc:
                assert str(exc) == (
                    "tasks.json entry 'malformed-target' must contain an object"
                )
            else:
                raise AssertionError("malformed target entry was silently filtered")
            assert path.read_bytes() == before_tasks
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            valid_target = {
                "runtime_schema_version": 3,
                "task_id": "valid-target",
                "title": "valid fixture",
                "charter": "valid charter",
                "state": "Pending",
                "owner": "taizi",
                "report_tier": "brief",
            }
            path = court_runtime.tasks_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "valid-target": valid_target,
                        "opaque-sibling": ["must", "survive", {"nested": [1, 2, 3]}],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            before_tasks = path.read_bytes()
            events = court_runtime.events_path()
            assert not events.exists()
            try:
                court_runtime.create_task(
                    create_args("unrelated-create", intake_gate=formal_gate_fixture())
                )
            except ValueError as exc:
                assert str(exc) == "tasks.json entry 'opaque-sibling' must contain an object"
            else:
                raise AssertionError("unrelated write silently deleted a malformed sibling entry")
            assert path.read_bytes() == before_tasks
            assert not events.exists()
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_normalization_deep_copy() -> None:
    source = {
        "runtime_schema_version": 3,
        "task_id": "deep-copy",
        "conversation_gate": {
            **formal_gate_fixture(),
            "details": {"reasons": ["source"]},
        },
        "charter_revision_history": [{"evidence": ["source"]}],
        "outcome_assessment": {
            "schema": "court.outcome_assessment.v1",
            "gate": "UNASSESSED",
            "reasons": [{"detail": ["source"]}],
            "outcome": None,
        },
        "shiguan_checkpoint": {"evidence": ["source"]},
        "completion": {"status": "UNASSESSED", "detail": ["source"]},
        "agent_runtime": {"kind": "fixture", "capabilities": ["source"]},
        "agents": {"agent-1": {"evidence": ["source"]}},
    }
    before_source = canonical_task_bytes(source)
    normalized = court_runtime.normalize_task(source)
    normalized["conversation_gate"]["details"]["reasons"].append("normalized")
    normalized["charter_revision_history"][0]["evidence"].append("normalized")
    normalized["outcome_assessment"]["reasons"][0]["detail"].append("normalized")
    normalized["shiguan_checkpoint"]["evidence"].append("normalized")
    normalized["completion"]["detail"].append("normalized")
    normalized["agent_runtime"]["capabilities"].append("normalized")
    normalized["agents"]["agent-1"]["evidence"].append("normalized")
    assert canonical_task_bytes(source) == before_source


def check_existing_task_intake_cannot_create_new_task() -> None:
    for message_class, relation in (
        ("TASK_CORRECTION", "CORRECTS"),
        ("TASK_CONTINUATION", "CONTINUES"),
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_runtime_root = court_runtime.runtime_root
            court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
            try:
                target_task_id = f"target-{message_class.lower()}"
                court_runtime.create_task(
                    create_args(target_task_id, intake_gate=formal_gate_fixture())
                )
                path = court_runtime.tasks_path()
                before_tasks = path.read_bytes()
                before_task_ids = set(court_runtime.load_tasks())
                existing_task_gate = {
                    **formal_gate_fixture(mutates_state=True),
                    "active_decree": True,
                    "active_decree_state": "ACTIVE",
                    "message_class": message_class,
                    "relation_to_active_decree": relation,
                    "taskization_consent": "NOT_REQUIRED",
                    "target_task_id": target_task_id,
                }
                assert_create_rejected_before_lock(
                    create_args(
                        f"forbidden-new-{message_class.lower()}",
                        intake_gate=existing_task_gate,
                    ),
                    "new_formal_task_gate_required",
                )
                assert set(court_runtime.load_tasks()) == before_task_ids
                assert path.read_bytes() == before_tasks

                missing_target_gate = dict(existing_task_gate)
                del missing_target_gate["target_task_id"]
                assert_create_rejected_before_lock(
                    create_args(
                        f"missing-target-{message_class.lower()}",
                        intake_gate=missing_target_gate,
                    ),
                    "target_task_id_required",
                )
                assert set(court_runtime.load_tasks()) == before_task_ids
                assert path.read_bytes() == before_tasks
            finally:
                court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_rejected_admission_has_zero_runtime_side_effects() -> None:
    with tempfile.TemporaryDirectory(prefix="court-runtime-rejected-admission-") as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_cardinality_create_args())
            task = _make_task_dispatchable("runtime-cardinality")
            args = _bind_admission_args(_cardinality_args(approved_count=1), task)
            args.requested_fork_turns = "all"
            before = deepcopy(court_runtime.load_tasks()["runtime-cardinality"])
            before_events = court_runtime.events_for_task(
                "runtime-cardinality", limit=None
            )

            rejected = court_runtime.agent_admit(args)
            assert rejected["allowed"] is False
            assert rejected["decision"] == "unbounded_context_fork"

            after = court_runtime.load_tasks()["runtime-cardinality"]
            after_events = court_runtime.events_for_task(
                "runtime-cardinality", limit=None
            )
            for field in (
                "next_semantic_dispatch_attempt",
                "semantic_dispatch_attempts",
                "agent_admissions",
                "last_agent_admission",
            ):
                assert after.get(field) == before.get(field), field
            assert after_events == before_events
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_admission_immutable_event_anchor_rejects_coherent_rewrite() -> None:
    with tempfile.TemporaryDirectory(prefix="court-runtime-admission-anchor-") as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_cardinality_create_args())
            task = _make_task_dispatchable("runtime-cardinality")
            admission = court_runtime.agent_admit(
                _bind_admission_args(_cardinality_args(approved_count=1), task)
            )
            tasks = court_runtime.load_tasks()
            stored = tasks["runtime-cardinality"]["agent_admissions"][
                "runtime-cardinality-wave"
            ]
            rebound_scope = ["work/gongbu/coherently-rewritten.txt"]
            selected = stored["selected_bindings"][0]
            requested = stored["requested_bindings"][0]
            for binding in (selected, requested):
                binding["write_set"] = list(rebound_scope)
                binding["read_scope"] = list(rebound_scope)
                child_profile = binding["child_profile"]
                child_profile["write_set"] = list(rebound_scope)
                child_profile["read_scope"] = list(rebound_scope)
            lease = stored["budget_lease"]
            lease["approved_write_sets"]["gongbu#0001"] = list(rebound_scope)
            lease["approved_access_contracts"]["gongbu#0001"][
                "read_scope"
            ] = list(rebound_scope)
            lease["approved_binding_sha256s"]["gongbu#0001"] = (
                canonical_child_office_binding_sha256(requested)
            )
            stored["admission_binding_sha256s"]["gongbu#0001"] = (
                canonical_child_office_binding_sha256(selected)
            )
            court_runtime.write_tasks(tasks)

            try:
                court_runtime.agent_start(
                    _instance_start_args(
                        instance_id="gongbu#0001",
                        agent_id="gongbu-anchor-tamper",
                        dispatch_requested_at=str(admission["dispatch_requested_at"]),
                    )
                )
            except ValueError as exc:
                assert "agent_start_admission_immutable_anchor_mismatch" in str(exc)
            else:
                raise AssertionError(
                    "coherent request/lease/admission/digest rewrite bypassed the append-only event anchor"
                )
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_canonical_preload_hashes_bound_before_admission() -> None:
    with tempfile.TemporaryDirectory(prefix="court-runtime-preload-anchor-") as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_cardinality_create_args())
            task = _make_task_dispatchable("runtime-cardinality")
            args = _bind_admission_args(_cardinality_args(approved_count=1), task)
            bindings = json.loads(args.requested_bindings_json)
            lease = json.loads(args.budget_lease_json)
            forged = dict(bindings[0]["preload_hashes"])
            forged["profile_hash"] = "f" * 64
            bindings[0]["preload_hashes"] = forged
            lease["approved_preload_hashes"]["gongbu#0001"] = dict(forged)
            args.requested_bindings_json = json.dumps(bindings, ensure_ascii=False)
            args.budget_lease_json = json.dumps(lease, ensure_ascii=False)

            try:
                court_runtime.agent_admit(args)
            except ValueError as exc:
                assert "agent_admission_canonical_preload_mismatch" in str(exc)
            else:
                raise AssertionError(
                    "forged but request/lease-consistent preload hashes were admitted"
                )
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_omitted_capsule_denies_mutable_admission() -> None:
    original_runtime_root = court_runtime.runtime_root
    with tempfile.TemporaryDirectory(prefix="court-runtime-capsule-scope-") as temp_dir:
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            create = create_args(
                "runtime-cardinality",
                intake_gate=formal_gate_fixture(mutates_state=True),
                work_kind="implementation",
            )
            create.invariant_capsule = None
            court_runtime.create_task(create)
            task = _make_task_dispatchable("runtime-cardinality")
            args = _bind_admission_args(
                _cardinality_args(approved_count=1),
                task,
            )
            before = {
                path.name: path.read_bytes()
                for path in Path(temp_dir).iterdir()
                if path.is_file()
            }
            try:
                court_runtime.agent_admit(args)
            except ValueError as exc:
                assert "agent_admission_write_scope_exceeds_capsule" in str(exc)
            else:
                raise AssertionError("OMITTED_CAPSULE_MUTABLE_ADMISSION_ALLOWED")
            after = {
                path.name: path.read_bytes()
                for path in Path(temp_dir).iterdir()
                if path.is_file()
            }
            assert after == before, "rejected capsule-scope admission mutated the ledger"
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_full_context_private_body_not_persisted() -> None:
    original_runtime_root = court_runtime.runtime_root
    with tempfile.TemporaryDirectory(prefix="court-runtime-private-context-") as temp_dir:
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.create_task(_cardinality_create_args())
            task = _make_task_dispatchable("runtime-cardinality")
            args = _bind_admission_args(
                _cardinality_args(approved_count=1),
                task,
            )
            private_sentinel = "PRIVATE-CONTEXT-BODY-MUST-NOT-PERSIST"
            packet = dict(args.dispatch_context_packet)
            packet.update(
                context_mode="full",
                full_context={"private_body": private_sentinel},
                budget_override={"explicit": True, "granted_by": "taizi", "max_bytes": 8192},
            )
            args.dispatch_context_packet = packet
            args.context_override_source = "taizi_explicit_budget"
            result = court_runtime.agent_admit(args)
            assert result["allowed"] is True
            persisted = court_runtime.tasks_path().read_text(encoding="utf-8")
            persisted += court_runtime.events_path().read_text(encoding="utf-8")
            assert private_sentinel not in persisted, "FULL_CONTEXT_PRIVATE_BODY_PERSISTED"
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def check_public_create_help_contract() -> None:
    cli = Path(__file__).with_name("court_cli.py")
    with tempfile.TemporaryDirectory(prefix="court-runtime-public-help-") as temp_dir:
        temp_root = Path(temp_dir)
        runtime_root = temp_root / "runtime"
        host_spawn_marker = temp_root / "host-spawn.marker"
        env = dict(os.environ)
        env["COURT_RUNTIME_ROOT"] = str(runtime_root)
        env["COURT_TEST_HOST_SPAWN_MARKER"] = str(host_spawn_marker)

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, "-B", str(cli), *args],
                text=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                check=False,
            )

        top_help = run("--help")
        assert top_help.returncode == 0, top_help.stderr
        for command in (
            "intake-schema",
            "intake-template",
            "intake-validate",
            "capsule-template",
            "capsule-validate",
            "semantic-context-schema",
            "semantic-context-template",
            "semantic-context-validate",
            "admission-schema",
            "admission-template",
            "admission-validate",
        ):
            assert command in top_help.stdout, f"PUBLIC_TOP_HELP_MISSING:{command}"

        completed = run("create", "--help")
        assert completed.returncode == 0, completed.stderr
        help_text = completed.stdout
        for fragment in (
            "court.conversation_gate.v1",
            "FORMAL_TASK",
            "JSON",
            "required nonempty exact UTF-8 charter",
            "court.semantic.invariant_capsule.v1",
            "court.request_understanding.v1",
            "95",
            "sha256(exact UTF-8 charter)",
            "13 fields",
            "2048",
        ):
            assert fragment in help_text, f"PUBLIC_CREATE_HELP_MISSING:{fragment}"
        for command in ("intake-schema", "intake-template", "intake-validate", "capsule-template", "capsule-validate"):
            assert command in help_text, f"PUBLIC_CREATE_HELP_DISCOVERY_MISSING:{command}"
        assert not runtime_root.exists(), "create --help mutated runtime state"

        schema_result = run("intake-schema", "--format", "json")
        assert schema_result.returncode == 0, schema_result.stderr
        contract = json.loads(schema_result.stdout)
        gate_schema = contract["conversation_gate_schema"]
        capsule_schema = contract["invariant_capsule_schema"]
        assert gate_schema["additionalProperties"] is False
        assert capsule_schema["additionalProperties"] is False
        assert gate_schema["optional"] == ["target_task_id", "understanding"]
        assert capsule_schema["optional"] == []
        assert contract["minimal_formal_task"]["message_class"] == "FORMAL_TASK"
        assert contract["minimal_formal_task"]["understanding"]["score"] >= 95
        assert gate_schema["properties"]["understanding"]["$id"] == "court.request_understanding.v1"
        workflow = " ".join(str(step["command"]) for step in contract["workflow"])
        for command in ("create", "semantic checkpoint", "semantic verify", "agent-admit"):
            assert command in workflow, f"PUBLIC_WORKFLOW_STEP_MISSING:{command}"

        invalid_intake = temp_root / "invalid-intake.json"
        invalid_intake.write_text(
            json.dumps(
                {
                    "schema": "court.conversation_gate.v0",
                    "active_decree": "false",
                    "message_class": "INVALID",
                    "confidence": "VERY_HIGH",
                    "unknown_field": True,
                }
            ),
            encoding="utf-8",
        )
        invalid_result = run(
            "intake-validate",
            "--charter",
            "invalid intake must not mutate",
            "--intake-file",
            str(invalid_intake),
            "--format",
            "json",
        )
        assert invalid_result.returncode == 2
        invalid_payload = json.loads(invalid_result.stdout)
        fields = {str(item["field"]) for item in invalid_payload["errors"]}
        assert {"active_decree", "active_decree_state", "message_class", "confidence", "unknown_field"} <= fields
        assert not runtime_root.exists(), "intake-validate mutated the runtime tree"
        assert not host_spawn_marker.exists(), "intake-validate attempted a host spawn"

        charter = "诏" * 200 + " exact UTF-8 public charter"
        template_result = run("intake-template", "--charter", charter, "--format", "json")
        assert template_result.returncode == 0, template_result.stderr
        template = json.loads(template_result.stdout)
        capsule = template["invariant_capsule"]
        expected_digest = hashlib.sha256(charter.encode("utf-8")).hexdigest()
        assert len(capsule) == 13
        assert capsule["latest_decree_sha256"] == expected_digest == capsule["charter_sha256"]
        anchor = capsule["latest_decree_anchor"]
        assert charter.startswith(anchor) and len(anchor.encode("utf-8")) <= 256
        assert len(json.dumps(capsule, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= 2048

        exact_charter = " \r\n诏令：保留前后空白、CRLF 与非 ASCII。\r\n "
        exact_digest = hashlib.sha256(exact_charter.encode("utf-8")).hexdigest()
        exact_template_result = run(
            "intake-template", "--charter", exact_charter, "--format", "json"
        )
        assert exact_template_result.returncode == 0, exact_template_result.stderr
        exact_template = json.loads(exact_template_result.stdout)
        assert exact_template["charter"] == exact_charter, "PUBLIC_EXACT_CHARTER_REWRITTEN"
        assert exact_template["invariant_capsule"]["charter_sha256"] == exact_digest
        assert exact_template["invariant_capsule"]["latest_decree_anchor"] == exact_charter
        exact_intake_file = temp_root / "exact-intake.json"
        exact_intake_file.write_text(
            json.dumps(exact_template["conversation_gate"]), encoding="utf-8"
        )
        exact_create = run(
            "create", "--task-id", "exact-charter", "--title", "exact charter",
            "--charter", exact_charter, "--work-kind", "audit",
            "--intake-file", str(exact_intake_file), "--format", "json",
        )
        assert exact_create.returncode == 0, exact_create.stderr
        exact_task = json.loads(exact_create.stdout)["task"]
        assert exact_task["charter"] == exact_charter, "STORED_EXACT_CHARTER_REWRITTEN"
        assert exact_task["charter_sha256"] == exact_digest
        assert exact_task["invariant_capsule"]["charter_sha256"] == exact_digest

        intake_file = temp_root / "intake.json"
        intake_file.write_text(json.dumps(template["conversation_gate"]), encoding="utf-8")
        wrong_capsule = dict(capsule)
        wrong_capsule["charter_sha256"] = "0" * 64
        wrong_capsule_file = temp_root / "wrong-capsule.json"
        wrong_capsule_file.write_text(json.dumps(wrong_capsule), encoding="utf-8")
        wrong_validate = run(
            "capsule-validate", "--charter", charter,
            "--invariant-capsule-file", str(wrong_capsule_file), "--format", "json",
        )
        assert wrong_validate.returncode == 2
        assert "charter_sha256_mismatch" in wrong_validate.stdout
        wrong_before = {
            path.relative_to(runtime_root).as_posix(): path.read_bytes()
            for path in runtime_root.rglob("*")
            if path.is_file()
        }
        wrong_create = run(
            "create", "--task-id", "wrong-capsule", "--title", "wrong capsule",
            "--charter", charter, "--work-kind", "audit", "--intake-file", str(intake_file),
            "--invariant-capsule-file", str(wrong_capsule_file), "--format", "json",
        )
        assert wrong_create.returncode != 0
        wrong_after = {
            path.relative_to(runtime_root).as_posix(): path.read_bytes()
            for path in runtime_root.rglob("*")
            if path.is_file()
        }
        assert wrong_after == wrong_before, "wrong capsule create mutated the runtime ledger"

        omitted = run(
            "create", "--task-id", "omitted-capsule", "--title", "omitted capsule",
            "--charter", charter, "--work-kind", "audit", "--intake-file", str(intake_file),
            "--format", "json",
        )
        assert omitted.returncode == 0, omitted.stderr
        omitted_task = json.loads(omitted.stdout)["task"]
        assert len(omitted_task["invariant_capsule"]) == 13
        assert omitted_task["invariant_capsule"]["charter_sha256"] == expected_digest
        omitted_canonical = json.dumps(
            omitted_task["invariant_capsule"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        assert omitted_task["invariant_capsule_sha256"] == hashlib.sha256(
            omitted_canonical
        ).hexdigest()


def main() -> int:
    check_public_create_help_contract()
    check_omitted_capsule_denies_mutable_admission()
    check_full_context_private_body_not_persisted()
    check_runtime_parallel_cardinality()
    check_runtime_instance_keyed_routes()
    check_runtime_instance_keyed_spawn_failure()
    check_runtime_instance_keyed_consumption()
    check_runtime_schema_v3_intake_and_migration()
    check_future_runtime_schema_rejected()
    check_malformed_task_entries_rejected()
    check_normalization_deep_copy()
    check_existing_task_intake_cannot_create_new_task()
    check_rejected_admission_has_zero_runtime_side_effects()
    check_admission_immutable_event_anchor_rejects_coherent_rewrite()
    check_canonical_preload_hashes_bound_before_admission()
    ordinary = ProtocolRequirements(
        child_agents_required=True,
        needs_parallel_tree=True,
        active_session_protocol="v2",
    )
    ordinary_decision = select_protocol("auto", ordinary)
    assert ordinary_decision.selected_mode == "v2"
    assert ordinary_decision.conflict is False

    model_override = ProtocolRequirements(
        child_agents_required=True,
        needs_model_override=True,
        active_session_protocol="v2",
    )
    model_decision = select_protocol("auto", model_override)
    assert model_decision.selected_mode is None
    assert model_decision.conflict is True
    assert model_decision.model_override_capability == "blocked"

    flat_v1 = select_protocol(
        "auto",
        ProtocolRequirements(child_agents_required=True, active_session_protocol="v1"),
    )
    assert flat_v1.selected_mode == "v1" and flat_v1.conflict is False
    unknown_namespace = select_protocol("auto", ProtocolRequirements(child_agents_required=True))
    assert unknown_namespace.selected_mode is None and unknown_namespace.conflict is True
    assert "active_session_protocol_unknown" in unknown_namespace.reason_codes

    serial_decision = select_protocol("auto", ProtocolRequirements(child_agents_required=False))
    assert serial_decision.selected_mode == "serial"
    assert serial_decision.model_override_capability == "not_applicable"

    conflict = select_protocol(
        "auto",
        ProtocolRequirements(
            child_agents_required=True,
            needs_cross_branch_messages=True,
            needs_agent_type_override=True,
            active_session_protocol="v2",
        ),
    )
    assert conflict.conflict is True
    assert conflict.selected_mode is None
    assert "capability_conflict" in conflict.reason_codes

    capacity_roles = tuple(f"role-{index}" for index in range(20))
    capacity_bindings = tuple(
        {
            "role": role,
            "instance_id": f"{role}#0001",
            "shard_id": f"capacity-{index}",
            "direct_superior": "shangshu",
            "instance_kind": "office",
            "canonical_authority": True,
            "owner_role": None,
            "write_set": [f"synthetic/runtime-capacity/{index}"],
            "access_mode": "read_write",
            "read_scope": [f"synthetic/runtime-capacity/{index}"],
            "mutation_allowed": True,
            "integration_authority": False,
            "preload_hashes": {
                "profile_hash": "1" * 64,
                "dossier_hash": "2" * 64,
                "court_skill_hash": "3" * 64,
            },
        }
        for index, role in enumerate(capacity_roles)
    )
    capacity_lease = {
        "schema": "court.agent.admission_lease.v2",
        "budget_id": "budget:runtime-capacity-check:phase:wave",
        "status": "ACTIVE",
        "lease_id": "runtime-capacity-lease",
        "parent_budget_id": "budget:runtime-capacity-check:phase:wave:taizi",
        "parent_id": "taizi",
        "approved_by": "taizi",
        "grantee_role": "shangshu",
        "lease_depth": 3,
        "approved_next_depth": 4,
        "expires_at_utc": "2099-01-01T00:00:00+00:00",
        "parent_write_scope": ["synthetic/runtime-capacity"],
        "approved_count": len(capacity_roles),
        "task_id": "runtime-capacity-check",
        "calling_office": "shangshu",
        "direct_superior": "taizi",
        "integration_domain": "runtime-capacity",
        "authority": "super",
        "approved_roles": list(capacity_roles),
        "approved_instance_ids": [
            str(binding["instance_id"]) for binding in capacity_bindings
        ],
        "approved_shards": [
            str(binding["shard_id"]) for binding in capacity_bindings
        ],
        "approved_write_sets": {
            str(binding["instance_id"]): list(binding["write_set"])
            for binding in capacity_bindings
        },
        "approved_access_contracts": {
            str(binding["instance_id"]): {
                "access_mode": binding["access_mode"],
                "read_scope": list(binding["read_scope"]),
                "mutation_allowed": binding["mutation_allowed"],
                "integration_authority": binding["integration_authority"],
            }
            for binding in capacity_bindings
        },
        "approved_instance_shapes": {
            str(binding["instance_id"]): {
                "instance_kind": binding["instance_kind"],
                "canonical_authority": binding["canonical_authority"],
                "owner_role": binding["owner_role"],
                "direct_superior": binding["direct_superior"],
            }
            for binding in capacity_bindings
        },
        "approved_preload_hashes": {
            str(binding["instance_id"]): dict(binding["preload_hashes"])
            for binding in capacity_bindings
        },
    }
    capacity = admit_roles(
        host_capacity=64,
        active_threads=1,
        retained_threads=0,
        requested_roles=capacity_roles,
        max_threads=16,
        next_depth=4,
        max_depth=4,
        budget_lease=capacity_lease,
        task_id="runtime-capacity-check",
        calling_office="shangshu",
        direct_superior="taizi",
        requested_bindings=capacity_bindings,
        integration_domain="runtime-capacity",
        authority="super",
    )
    assert capacity.allowed is True
    assert capacity.effective_host_capacity == 16
    assert len(capacity.selected_roles) == 15
    assert len(capacity.deferred_roles) == 5
    assert capacity.available_slots == 15
    assert "capacity_clamped" in capacity.reason_codes
    assert "approved_budget_clamped" not in capacity.reason_codes

    runtime_bound_lease, runtime_bound_bindings = _public_admission_fixture(
        task_id="runtime-bound-check",
        roles=("menxia",),
        integration_domain="runtime-bound",
        calling_office="taizi",
    )
    depth_rejected = admit_roles(
        host_capacity=64,
        active_threads=1,
        retained_threads=0,
        requested_roles=["menxia"],
        max_threads=16,
        next_depth=5,
        max_depth=4,
        budget_lease=runtime_bound_lease,
        task_id="runtime-bound-check",
        calling_office="taizi",
        direct_superior="user",
        requested_bindings=runtime_bound_bindings,
        integration_domain="runtime-bound",
        authority="super",
    )
    assert depth_rejected.allowed is False
    assert depth_rejected.selected_roles == ()
    assert "max_depth_exceeded" in depth_rejected.reason_codes

    for unknown in (
        {"host_capacity": None, "active_threads": 1, "retained_threads": 0, "next_depth": 1},
        {"host_capacity": 4, "active_threads": None, "retained_threads": 0, "next_depth": 1},
        {"host_capacity": 4, "active_threads": 1, "retained_threads": 0, "next_depth": None},
    ):
        denied = admit_roles(
            requested_roles=["menxia"],
            max_threads=16,
            max_depth=4,
            budget_lease=runtime_bound_lease,
            task_id="runtime-bound-check",
            calling_office="taizi",
            direct_superior="user",
            requested_bindings=runtime_bound_bindings,
            integration_domain="runtime-bound",
            authority="super",
            **unknown,
        )
        assert denied.allowed is False
        assert "unknown_runtime_bound" in denied.reason_codes

    original_protocol_config = """model = \"gpt-5.6-sol\"
private_marker = \"preserve-me\"

[features]
goals = true

[agents]
max_depth = 2
max_threads = 6
"""
    v2_text = render_protocol_config(original_protocol_config, "v2")
    v2_validation = validate_protocol_config(v2_text, expected_mode="v2")
    assert v2_validation["ok"] is True
    assert "private_marker = \"preserve-me\"" in v2_text
    assert render_protocol_config(v2_text, "v2") == v2_text

    v1_text = render_protocol_config(v2_text, "v1")
    v1_validation = validate_protocol_config(v1_text, expected_mode="v1")
    assert v1_validation["ok"] is True
    assert v1_validation["effective_child_thread_limit"] == 15
    assert v1_validation["inactive_v2_config_preserved"] is True
    assert "max_concurrent_threads_per_session = 16" in v1_text
    assert "hide_spawn_agent_metadata = true" in v1_text
    assert render_protocol_config(v1_text, "v1") == v1_text

    mixed_text = v1_text.replace(
        "enabled = false",
        "enabled = true",
    )
    mixed_validation = validate_protocol_config(mixed_text)
    assert mixed_validation["ok"] is False
    assert "v2_enabled_with_legacy_max_threads" in mixed_validation["errors"]

    assert render_protocol_config(v2_text, "serial") == v2_text
    isolated_serial = render_protocol_config(v2_text, "serial", isolated_serial=True)
    serial_validation = validate_protocol_config(isolated_serial, expected_mode="serial")
    assert serial_validation["ok"] is True
    assert serial_validation["multi_agent_enabled"] is False
    assert serial_validation["multi_agent_v2_enabled"] is False

    session_id = "019f482b-6e27-7cb3-af2d-ce01be40bc22"
    assert validate_session_id(session_id) == session_id
    for invalid_session in ("", "--last", "--ephemeral", "court-task", "SCOSZLSZUVP-20260711-01-AAAS"):
        try:
            validate_session_id(invalid_session)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid session id accepted: {invalid_session!r}")
    resume_command = build_exact_resume_command(
        "codex.exe",
        session_id,
        "COURT_INTERNAL_RESUME operation=test",
    )
    assert resume_command == (
        "codex.exe",
        "resume",
        session_id,
        "COURT_INTERNAL_RESUME operation=test",
    )
    assert "--last" not in resume_command
    assert "--ephemeral" not in resume_command

    quiescent = QuiescenceSnapshot(
        main_turn_finished=True,
        active_agents=0,
        unfinished_agents=(),
        pending_messages=0,
        pending_followups=0,
        pending_waits=0,
        running_tool_calls=0,
        result_merge_complete=True,
        session_id=session_id,
        goal_persisted=True,
        court_task_persisted=True,
        side_effect_ledger_committed=True,
        credential_state_clear=True,
        protocol_switch_capability_verified=True,
        capacity_known=True,
        occupancy_known=True,
        depth_known=True,
    )
    assert assess_quiescence(quiescent).ok is True
    for field, value in (
        ("main_turn_finished", False),
        ("active_agents", 1),
        ("unfinished_agents", ("/root/menxia",)),
        ("pending_messages", 1),
        ("pending_followups", 1),
        ("pending_waits", 1),
        ("running_tool_calls", 1),
        ("result_merge_complete", False),
        ("goal_persisted", False),
        ("court_task_persisted", False),
        ("side_effect_ledger_committed", False),
        ("credential_state_clear", False),
        ("protocol_switch_capability_verified", False),
        ("capacity_known", False),
        ("occupancy_known", False),
        ("depth_known", False),
    ):
        values = dict(quiescent.__dict__)
        values[field] = value
        assert assess_quiescence(QuiescenceSnapshot(**values)).ok is False, field
    unknown_counts = dict(quiescent.__dict__)
    unknown_counts["active_agents"] = None
    assert assess_quiescence(QuiescenceSnapshot(**unknown_counts)).ok is False

    class FakeEngine:
        def __init__(self) -> None:
            self.stops = 0
            self.resumes = 0
            self.verifications = 0

        def stop(self, operation_id: str) -> bool:
            self.stops += 1
            return bool(operation_id)

        def resume(self, operation_id: str, command: tuple[str, ...]) -> bool:
            self.resumes += 1
            return bool(operation_id and command[1] == "resume")

        def verify(self, operation_id: str, expected: dict[str, str]) -> bool:
            self.verifications += 1
            return expected["session_id"] == session_id and bool(operation_id)

    with tempfile.TemporaryDirectory() as switch_temp:
        ledger = ProtocolSwitchLedger(Path(switch_temp))
        operation_id = str(uuid.uuid4())
        engine = FakeEngine()
        result = execute_switch(
            ledger=ledger,
            operation_id=operation_id,
            session_id=session_id,
            goal_thread_id=session_id,
            court_task_id="court-self-loop-ei-quiescent-20260711-1",
            from_protocol="v2",
            to_protocol="v1",
            quiescence=quiescent,
            resume_command=resume_command,
            history_prefix_sha256="a" * 64,
            engine=engine,
        )
        assert result["state"] == "RESUME_VERIFIED"
        assert engine.stops == 1 and engine.resumes == 1 and engine.verifications == 1
        replay = execute_switch(
            ledger=ledger,
            operation_id=operation_id,
            session_id=session_id,
            goal_thread_id=session_id,
            court_task_id="court-self-loop-ei-quiescent-20260711-1",
            from_protocol="v2",
            to_protocol="v1",
            quiescence=quiescent,
            resume_command=resume_command,
            history_prefix_sha256="a" * 64,
            engine=engine,
        )
        assert replay["state"] == "RESUME_VERIFIED"
        assert replay["replayed"] is True
        assert engine.stops == 1 and engine.resumes == 1 and engine.verifications == 1
        second_operation = str(uuid.uuid4())
        second = ledger.acquire(
            operation_id=second_operation,
            session_id=session_id,
            goal_thread_id=session_id,
            court_task_id="task-second",
            from_protocol="v1",
            to_protocol="v2",
            history_prefix_sha256="d" * 64,
        )
        assert second["state"] == "SWITCH_REQUESTED"
        active_operation = str(uuid.uuid4())
        ledger.acquire(
            operation_id=active_operation,
            session_id=str(uuid.uuid4()),
            goal_thread_id=session_id,
            court_task_id="task-a",
            from_protocol="v2",
            to_protocol="v1",
            history_prefix_sha256="b" * 64,
        )
        blocked_operation = str(uuid.uuid4())
        try:
            ledger.acquire(
                operation_id=blocked_operation,
                session_id=ledger.latest(active_operation)["session_id"],
                goal_thread_id=session_id,
                court_task_id="task-b",
                from_protocol="v2",
                to_protocol="v1",
                history_prefix_sha256="c" * 64,
            )
        except SwitchInProgress:
            pass
        else:
            raise AssertionError("concurrent switch lease was not rejected")
        assert ledger.event_count(operation_id) >= 8

    complete_latency = startup_latency.build_agent_latency_report(
        {
            "agent_id": "latency-agent",
            "role": "xingbu",
            "dispatch_requested_at": "2026-07-10T12:00:00+00:00",
            "host_session_started_at": "2026-07-10T12:00:02+00:00",
            "preload_ack_at": "2026-07-10T12:00:03.500000+00:00",
            "first_office_report_at": "2026-07-10T12:00:05+00:00",
            "finished_at": "2026-07-10T12:00:13.500000+00:00",
        }
    )
    assert complete_latency["status"] == "COMPLETE"
    assert complete_latency["segments"]["host_spawn_queue_ms"] == 2000
    assert complete_latency["segments"]["preload_ms"] == 1500
    assert complete_latency["segments"]["first_report_ms"] == 1500
    assert complete_latency["segments"]["execution_ms"] == 10000
    partial_latency = startup_latency.build_agent_latency_report(
        {"agent_id": "partial", "role": "xingbu", "host_session_started_at": "2026-07-10T12:00:02+00:00"}
    )
    assert partial_latency["status"] == "PARTIAL"
    assert partial_latency["segments"]["preload_ms"] == "unavailable"
    legacy = startup_latency.legacy_fixture_report("CCR-20260710-183747-AGENT-AUDIT")
    assert legacy["status"] == "PARTIAL"
    assert legacy["legacy_evidence"]["dispatch_to_start_ms"] == 43601
    assert "supercc_stagger_root_cause" not in str(legacy)

    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            created = court_runtime.create_task(
                Namespace(
                    title="self-test read-only decree",
                    charter="只读 review only，不要改文件",
                    task_id="self-test",
                    owner="taizi",
                    report_tier="",
                    evidence="self-test",
                    note="create",
                    work_kind="audit",
                    intake_gate=formal_gate_fixture(),
                    intake_file=None,
                )
            )
            assert created.task["read_only"] is True
            assert created.task["report_tier"] == "brief"
            path = [
                ("Taizi", "taizi"),
                ("ThreeDepartments", "zhongshu"),
                ("ThreeDepartmentsPetition", "zhongshu"),
                ("TaiziReply", "taizi"),
                ("ShangshuDispatch", "shangshu"),
                ("SixMinistries", "shangshu"),
                ("Workshops", "gongbu"),
                ("MenxiaReview", "menxia"),
            ]
            for state, actor in path:
                court_runtime.transition_task(
                    Namespace(
                        task_id="self-test",
                        to_state=state,
                        actor=actor,
                        owner="",
                        heartbeat="alive" if state != "Done" else "completed",
                        evidence=f"transition {state}",
                        note="self-test",
                    )
                )
            try:
                court_runtime.transition_task(
                    Namespace(
                        task_id="self-test",
                        to_state="ShiguanRecorded",
                        actor="shiguan",
                        owner="",
                        heartbeat="alive",
                        evidence="generic checkpoint must fail",
                        note="self-test",
                    )
                )
            except ValueError as exc:
                assert str(exc) == "assessment_binding_integrity"
            else:
                raise AssertionError("generic ShiguanRecorded transition was accepted")
            recorded_probe = dict(court_runtime.load_tasks()["self-test"])
            recorded_probe["state"] = "ShiguanRecorded"
            try:
                court_runtime.validate_runtime_gate(
                    recorded_probe,
                    "ShiguanRecorded",
                    "Done",
                    "generic completion must fail",
                )
            except ValueError as exc:
                assert str(exc) == "atomic_completion_required"
            else:
                raise AssertionError("generic Done transition was accepted")
            try:
                court_runtime.transition_task(
                    Namespace(
                        task_id="self-test",
                        to_state="Pending",
                        actor="taizi",
                        owner="",
                        heartbeat="",
                        evidence="illegal",
                        note="must fail",
                    )
                )
            except ValueError:
                pass
            else:
                raise AssertionError("illegal transition was accepted")
            events = court_runtime.read_events(limit=50, task_id="self-test")
            assert len(events) == 9
            payload = court_runtime.status_payload(Namespace(limit=5, state=""))
            assert payload["kind"] == "court_runtime_status"
            assert payload["runtime_schema_version"] == court_runtime.RUNTIME_SCHEMA_VERSION
            assert payload["task_count"] == 1
            assert payload["tasks"][0]["state"] == "MenxiaReview"
            assert "COURT RUNTIME" in payload["dashboard"]
            probe = court_runtime.probe_payload()
            assert probe["kind"] == "court_runtime_probe"
            assert "pause" in probe["supported_commands"]
            assert "agent-admit" in probe["supported_commands"]
            assert "agent-preload-ack" in probe["supported_commands"]
            assert "agent-report" in probe["supported_commands"]
            assert "agent-reconcile" in probe["supported_commands"]
            assert "agent-spawn-failed" in probe["supported_commands"]
            assert probe["agent_dispatch_policy"]["wave_policy"] == "dynamic_by_duty_and_capacity"
            assert probe["agent_dispatch_policy"]["static_wave_cap"] is None
            assert probe["agent_dispatch_policy"]["host_capacity_required"] is True
            assert probe["agent_dispatch_policy"]["host_retained_agents_required"] is True
            assert probe["agent_dispatch_policy"]["terminal_reclamation_evidence_required_when_retained"] is True
            assert probe["agent_dispatch_policy"]["max_threads"] == 16
            assert probe["agent_dispatch_policy"]["max_depth"] == 4
            assert probe["agent_dispatch_policy"]["long_context_fork_turns"] == "none"
            assert probe["agent_dispatch_policy"]["message_budget_schema"] == "court.agent.dispatch_message_budget.v1"
            assert probe["agent_dispatch_policy"]["message_budget_floor_chars"] == 6000
            assert probe["agent_dispatch_policy"]["message_budget_quantum_chars"] == 1000
            assert probe["agent_dispatch_policy"]["message_budget_ceiling_chars"] == 12000
            assert probe["agent_model_routing"]["schema"] == "court.office.model_route.v2"
            assert probe["agent_model_routing"]["codex_models"] == {
                "gpt-5.6-luna": "max",
                "gpt-5.6-sol": "ultra",
                "gpt-5.6-terra": "ultra",
            }
            assert probe["agent_model_routing"]["codex_enforcement"] == "protocol_bound_child_inheritance_required"
            assert probe["agent_model_routing"]["model_visible_spawn_fields"] == ["message", "task_name", "fork_turns"]
            assert probe["agent_model_routing"]["fresh_worker_script"] == "scripts/court_codex_office_worker.py"
            assert probe["agent_model_routing"]["fresh_worker_binary_pin_required"] is True
            assert probe["agent_model_routing"]["fresh_worker_same_session"] is False
            assert probe["agent_model_routing"]["v1_v2_child_override_status"] == "unavailable_in_current_reserved_spawn_path"
            assert probe["agent_model_routing"]["claude_code"] == "inherit_main_thread_model"
            assert probe["agent_model_routing"]["hermes"] == "inherit_main_profile_model_design_deferred"

            def sized_admission(
                message_chars: object,
                wave_id: str,
                *,
                required_chars: object | None = None,
                optional_chars: object | None = None,
            ) -> dict[str, object]:
                values: dict[str, object] = {
                    "wave_id": wave_id,
                    "context_tokens": 1000,
                    "requested_agents": 1,
                    "requested_roles": "gongbu",
                    "host_active_agents": 1,
                    "host_capacity": 4,
                    "host_retained_agents": 0,
                    "host_reclamation_status": "unknown",
                    "next_depth": 1,
                    "user_agent_budget": None,
                    "provider_launch_budget": None,
                    "requested_fork_turns": "none",
                    "execution_topology": "parallel",
                    "active_session_protocol": "v2",
                }
                values.update(
                    _public_admission_fields(
                        task_id=wave_id,
                        roles=("gongbu",),
                        integration_domain="runtime-message-budget",
                    )
                )
                if message_chars is not None:
                    values["message_chars"] = message_chars
                if required_chars is not None:
                    values["message_required_chars"] = required_chars
                if optional_chars is not None:
                    values["message_optional_chars"] = optional_chars
                return court_runtime.evaluate_agent_admission(
                    {"task_id": wave_id, "agents": {}},
                    Namespace(**values),
                )

            for message_chars, effective_budget in (
                (6000, 6000),
                (6001, 7000),
                (9000, 9000),
                (12000, 12000),
            ):
                budgeted = sized_admission(message_chars, f"message-{message_chars}")
                assert budgeted["allowed"] is True
                assert budgeted["message_budget_schema"] == "court.agent.dispatch_message_budget.v1"
                assert budgeted["message_measurement"] == "unicode_code_points"
                assert budgeted["message_scope"] == "max_single_final_message_per_wave"
                assert budgeted["message_chars"] == message_chars
                assert budgeted["message_budget_effective_chars"] == effective_budget
                assert budgeted["message_budget_status"] == "within_budget"
                assert budgeted["message_overage_chars"] == 0
                assert budgeted["message_budget_retryable"] is False

            oversized = sized_admission(12001, "message-12001")
            assert oversized["allowed"] is False
            assert oversized["decision"] == "dispatch_message_too_large"
            assert oversized["message_budget_effective_chars"] == 12000
            assert oversized["message_budget_status"] == "exceeded"
            assert oversized["message_overage_chars"] == 1
            assert oversized["required_reduction_chars"] == 1
            assert oversized["message_budget_retryable"] is True
            assert "new wave_id" in oversized["compression_guidance"]

            legacy_unmeasured = sized_admission(None, "message-legacy")
            assert legacy_unmeasured["allowed"] is True
            assert legacy_unmeasured["message_chars"] is None
            assert legacy_unmeasured["message_budget_status"] == "legacy_unmeasured"
            assert legacy_unmeasured["message_budget_effective_chars"] == 6000

            invalid_size = sized_admission(-1, "message-invalid")
            assert invalid_size["allowed"] is False
            assert invalid_size["decision"] == "invalid_dispatch_message_size"
            assert invalid_size["message_budget_status"] == "invalid"

            invalid_body_sentinel = sized_admission("PRIVATE-DISPATCH-BODY", "message-invalid-body")
            assert invalid_body_sentinel["allowed"] is False
            assert invalid_body_sentinel["message_chars"] is None
            assert "PRIVATE-DISPATCH-BODY" not in repr(invalid_body_sentinel)

            optional_compression = sized_admission(
                13000,
                "message-components-compressible",
                required_chars=11500,
                optional_chars=1500,
            )
            assert optional_compression["allowed"] is False
            assert optional_compression["message_component_status"] == "measured"
            assert optional_compression["optional_compression_target_chars"] == 1000
            assert optional_compression["required_message_overage_chars"] == 0
            assert optional_compression["compression_possible_without_required_loss"] is True

            required_overage = sized_admission(
                13000,
                "message-components-required-overage",
                required_chars=12500,
                optional_chars=500,
            )
            assert required_overage["required_message_overage_chars"] == 500
            assert required_overage["compression_possible_without_required_loss"] is False

            invalid_components = sized_admission(
                9000,
                "message-components-invalid",
                required_chars=6000,
                optional_chars=2000,
            )
            assert invalid_components["allowed"] is False
            assert invalid_components["decision"] == "invalid_dispatch_message_size"
            assert invalid_components["message_component_status"] == "invalid"
            assert invalid_components["message_component_reason"] == "component_sum_mismatch"
            assert "equal message_chars" in invalid_components["compression_guidance"]
            assert invalid_components["message_budget_retryable"] is True

            missing_component = sized_admission(
                9000,
                "message-components-missing",
                required_chars=9000,
            )
            assert missing_component["allowed"] is False
            assert missing_component["message_component_reason"] == "component_missing"
            assert "provide both" in missing_component["compression_guidance"]
            assert missing_component["message_budget_retryable"] is True

            negative_component = sized_admission(
                9000,
                "message-components-negative",
                required_chars=-1,
                optional_chars=9001,
            )
            assert negative_component["allowed"] is False
            assert negative_component["message_component_reason"] == "component_negative"
            assert "non-negative" in negative_component["compression_guidance"]
            assert negative_component["message_budget_retryable"] is True
            six_role_admission = court_runtime.evaluate_agent_admission(
                {"task_id": "dynamic-six", "agents": {}},
                Namespace(
                    wave_id="six",
                    context_tokens=1000,
                    requested_agents=1,
                    requested_roles="libu-hr,hubu,libu,bingbu,xingbu,gongbu",
                    host_active_agents=1,
                    host_capacity=8,
                    host_retained_agents=0,
                    host_reclamation_status="unknown",
                    next_depth=1,
                    user_agent_budget=None,
                    provider_launch_budget=None,
                    message_chars=100,
                    requested_fork_turns="none",
                    execution_topology="parallel",
                    active_session_protocol="v2",
                    **_public_admission_fields(
                        task_id="dynamic-six",
                        roles=("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"),
                        integration_domain="runtime-dynamic-six",
                    ),
                ),
            )
            assert six_role_admission["allowed"] is True
            assert six_role_admission["selected_protocol"] == "v2"
            assert tuple(six_role_admission["selected_roles"]) == ("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu")
            assert six_role_admission["static_wave_cap"] is None
            partial_admission = court_runtime.evaluate_agent_admission(
                {"task_id": "dynamic-four", "agents": {}},
                Namespace(
                    wave_id="four",
                    context_tokens=1000,
                    requested_agents=1,
                    requested_roles="zhongshu,menxia,shangshu,shiguan",
                    host_active_agents=1,
                    host_capacity=4,
                    host_retained_agents=0,
                    host_reclamation_status="unknown",
                    next_depth=1,
                    user_agent_budget=None,
                    provider_launch_budget=None,
                    message_chars=100,
                    requested_fork_turns="none",
                    execution_topology="parallel",
                    active_session_protocol="v2",
                    **_public_admission_fields(
                        task_id="dynamic-four",
                        roles=("zhongshu", "menxia", "shangshu", "shiguan"),
                        integration_domain="runtime-dynamic-four",
                        calling_office="taizi",
                    ),
                ),
            )
            assert tuple(partial_admission["selected_roles"]) == ("zhongshu", "menxia", "shangshu")
            assert tuple(partial_admission["deferred_roles"]) == ("shiguan",)
            assert partial_admission["selection_basis"] == "runtime_capacity"
            root_tree_cap = court_runtime.evaluate_agent_admission(
                {"task_id": "root-tree-cap", "agents": {}},
                Namespace(
                    wave_id="root-tree-cap",
                    context_tokens=1000,
                    requested_agents=20,
                    requested_roles=",".join(f"unspecified-{index}" for index in range(1, 21)),
                    host_active_agents=1,
                    host_capacity=64,
                    host_retained_agents=0,
                    host_reclamation_status="unknown",
                    next_depth=1,
                    user_agent_budget=None,
                    provider_launch_budget=None,
                    message_chars=100,
                    requested_fork_turns="none",
                    execution_topology="parallel",
                    active_session_protocol="v2",
                    **_public_admission_fields(
                        task_id="root-tree-cap",
                        roles=tuple(f"unspecified-{index}" for index in range(1, 21)),
                        integration_domain="runtime-root-tree-cap",
                    ),
                ),
            )
            assert root_tree_cap["allowed"] is True
            assert len(root_tree_cap["selected_roles"]) == 15
            assert len(root_tree_cap["deferred_roles"]) == 5
            assert root_tree_cap["effective_host_capacity"] == 16
            depth_five = court_runtime.evaluate_agent_admission(
                {"task_id": "depth-five", "agents": {}},
                Namespace(
                    wave_id="depth-five",
                    context_tokens=1000,
                    requested_agents=1,
                    requested_roles="xingbu",
                    host_active_agents=1,
                    host_capacity=16,
                    host_retained_agents=0,
                    host_reclamation_status="unknown",
                    next_depth=5,
                    user_agent_budget=None,
                    provider_launch_budget=None,
                    message_chars=100,
                    requested_fork_turns="none",
                    execution_topology="parallel",
                    active_session_protocol="v2",
                    **_public_admission_fields(
                        task_id="depth-five",
                        roles=("xingbu",),
                        integration_domain="runtime-depth-five",
                    ),
                ),
            )
            assert depth_five["allowed"] is False
            assert depth_five["decision"] == "max_depth_exceeded"
            v1_override_admission = court_runtime.evaluate_agent_admission(
                {"task_id": "v1-override", "agents": {}},
                Namespace(
                    wave_id="v1-override",
                    context_tokens=1000,
                    requested_agents=1,
                    requested_roles="xingbu",
                    host_active_agents=1,
                    host_capacity=4,
                    host_retained_agents=0,
                    host_reclamation_status="unknown",
                    next_depth=1,
                    user_agent_budget=None,
                    provider_launch_budget=None,
                    message_chars=100,
                    requested_fork_turns="none",
                    execution_topology="auto",
                    protocol_mode="auto",
                    needs_agent_type_override=True,
                    active_session_protocol="v1",
                    **_public_admission_fields(
                        task_id="v1-override",
                        roles=("xingbu",),
                        integration_domain="runtime-v1-override",
                    ),
                ),
            )
            assert v1_override_admission["allowed"] is True
            assert v1_override_admission["selected_protocol"] == "v1"
            protocol_conflict = court_runtime.evaluate_agent_admission(
                {"task_id": "protocol-conflict", "agents": {}},
                Namespace(
                    wave_id="protocol-conflict",
                    context_tokens=1000,
                    requested_agents=1,
                    requested_roles="xingbu",
                    host_active_agents=1,
                    host_capacity=4,
                    host_retained_agents=0,
                    host_reclamation_status="unknown",
                    next_depth=1,
                    user_agent_budget=None,
                    provider_launch_budget=None,
                    message_chars=100,
                    requested_fork_turns="none",
                    execution_topology="parallel",
                    protocol_mode="auto",
                    needs_model_override=True,
                    active_session_protocol="v2",
                ),
            )
            assert protocol_conflict["allowed"] is False
            assert protocol_conflict["decision"] == "protocol_capability_conflict"
            assert court_runtime.classify_agent_error("agent thread limit reached") == "capacity"
            assert court_runtime.classify_agent_error("403 Forbidden: quota insufficient") == "fatal-quota"
            assert court_runtime.classify_agent_error("401 unauthorized") == "fatal-auth"
            paused = court_runtime.create_task(
                Namespace(
                    title="paused resume gate",
                    charter="implement then pause",
                    task_id="paused-gate",
                    owner="taizi",
                    report_tier="",
                    evidence="create",
                    note="create",
                    work_kind="audit",
                    intake_gate=formal_gate_fixture(),
                    intake_file=None,
                )
            )
            assert paused.task["state"] == "Pending"
            for state, actor in [
                ("Taizi", "taizi"),
                ("ThreeDepartments", "zhongshu"),
                ("ThreeDepartmentsPetition", "zhongshu"),
                ("TaiziReply", "taizi"),
                ("ShangshuDispatch", "shangshu"),
            ]:
                court_runtime.transition_task(
                    Namespace(
                        task_id="paused-gate",
                        to_state=state,
                        actor=actor,
                        owner="",
                        heartbeat="alive",
                        evidence=f"transition {state}",
                        note="pause gate",
                    )
                )
            try:
                court_runtime.transition_task(
                    Namespace(
                        task_id="paused-gate",
                        to_state="Paused",
                        actor="shangshu",
                        owner="",
                        heartbeat="paused",
                        evidence="direct pause should fail",
                        note="must fail",
                    )
                )
            except ValueError:
                pass
            else:
                raise AssertionError("direct Paused transition was accepted")
            paused_result = court_runtime.pause_task(
                Namespace(
                    task_id="paused-gate",
                    actor="shangshu",
                    reason="self-test pause",
                    affected_scope="runtime test",
                    evidence_preserved="temp ledger events",
                    unsafe_remaining="none",
                    note="pause command",
                )
            )
            assert paused_result.task["state"] == "Paused"
            assert paused_result.task["paused_from"] == "ShangshuDispatch"
            try:
                court_runtime.transition_task(
                    Namespace(
                        task_id="paused-gate",
                        to_state="Workshops",
                        actor="gongbu",
                        owner="",
                        heartbeat="",
                        evidence="skip six ministries",
                        note="must fail",
                    )
                )
            except ValueError:
                pass
            else:
                raise AssertionError("paused resume skip was accepted")
            court_runtime.resume_task(
                Namespace(
                    task_id="paused-gate",
                    to_state="ShangshuDispatch",
                    actor="shangshu",
                    resume_evidence="resume to paused source",
                    affected_scope="runtime test",
                    from_paused_state="ShangshuDispatch",
                    note="resume command",
                )
            )
            cancel_gate = court_runtime.create_task(
                Namespace(
                    title="cancel gate",
                    charter="cancel active work",
                    task_id="cancel-gate",
                    owner="taizi",
                    report_tier="",
                    evidence="create",
                    note="create",
                    work_kind="audit",
                    intake_gate=formal_gate_fixture(),
                    intake_file=None,
                )
            )
            assert cancel_gate.task["state"] == "Pending"
            court_runtime.transition_task(
                Namespace(
                    task_id="cancel-gate",
                    to_state="Taizi",
                    actor="taizi",
                    owner="",
                    heartbeat="alive",
                    evidence="intake",
                    note="cancel gate",
                )
            )
            try:
                court_runtime.transition_task(
                    Namespace(
                        task_id="cancel-gate",
                        to_state="Cancelled",
                        actor="taizi",
                        owner="",
                        heartbeat="cancelled",
                        evidence="direct cancel should fail",
                        note="must fail",
                    )
                )
            except ValueError:
                pass
            else:
                raise AssertionError("direct Cancelled transition was accepted")
            cancelled = court_runtime.cancel_task(
                Namespace(
                    task_id="cancel-gate",
                    actor="taizi",
                    reason="self-test cancel",
                    affected_scope="runtime test",
                    evidence_preserved="temp ledger events",
                    unsafe_remaining="none",
                    note="cancel command",
                )
            )
            assert cancelled.task["state"] == "Cancelled"
            done_gate = court_runtime.create_task(
                Namespace(
                    title="done evidence gate",
                    charter="trivial intake",
                    task_id="done-gate",
                    owner="taizi",
                    report_tier="brief",
                    evidence="create",
                    note="create",
                    work_kind="audit",
                    intake_gate=formal_gate_fixture(),
                    intake_file=None,
                )
            )
            assert done_gate.task["state"] == "Pending"
            court_runtime.transition_task(
                Namespace(
                    task_id="done-gate",
                    to_state="Taizi",
                    actor="taizi",
                    owner="",
                    heartbeat="alive",
                    evidence="intake",
                    note="done gate",
                )
            )
            try:
                court_runtime.transition_task(
                    Namespace(
                        task_id="done-gate",
                        to_state="Done",
                        actor="taizi",
                        owner="",
                        heartbeat="completed",
                        evidence="",
                        note="must fail",
                    )
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Done without evidence was accepted")
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]
    run_agent_lifecycle_checks()
    print("COURT_RUNTIME_SELF_TEST_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
