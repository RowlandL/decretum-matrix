"""Focused regression checks for admitted court-agent lifecycle integrity."""

from __future__ import annotations

from argparse import Namespace
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Callable
import uuid

sys.dont_write_bytecode = True

_IMPORT_ISOLATION = tempfile.TemporaryDirectory(prefix="court-rc4-import-")
_IMPORT_ISOLATION_ROOT = Path(_IMPORT_ISOLATION.name).resolve()
_IMPORT_RUNTIME_ROOT = _IMPORT_ISOLATION_ROOT / "runtime"
_IMPORT_SHIGUAN_ROOT = _IMPORT_ISOLATION_ROOT / "shared-shiguan"
os.environ["COURT_RUNTIME_ROOT"] = str(_IMPORT_RUNTIME_ROOT)
os.environ["COURT_SHARED_SHIGUAN_ROOT"] = str(_IMPORT_SHIGUAN_ROOT)
os.environ["SHIGUAN_SHARED_ROOT"] = str(_IMPORT_SHIGUAN_ROOT)

import court_runtime
from court_agent_admission import budget_lease_access_contract_error
from court_complexity_budget import normalize_budget_pool
from check_court_office_assignment_binding import run_office_assignment_binding_checks
from court_office_bootstrap import canonical_child_office_binding_sha256


ROUTE = {
    "assignment": "bounded lifecycle work",
    "task_focus": "runtime lifecycle implementation",
    "complexity": "high",
    "risk": "medium",
    "ambiguity": "medium",
    "transport": "codex",
}
CONTEXT_HARD_LIMITS = {
    "ram_percent_max": 99.0,
    "memory_mb_max": 2_048,
    "context_tokens_max": 100_000,
    "message_chars_max": 12_000,
    "tool_calls_max": 8,
    "time_seconds_max": 600.0,
    "retained_agents_max": 15,
}
TASK_SPECIFIC_SKILL_PATH: Path | None = None
FIXTURE_SLOT_COUNT = 32
_FIXTURE_WAVE_SLOTS: dict[tuple[str, str], tuple[int, int]] = {}
FIXTURE_EXPLICIT_WRITE_SET = (
    "work/gongbu/worker-0001.txt",
    "work/gongbu/worker-tamper-0001.txt",
    "work/gongbu/worker-access-tamper-0001.txt",
    "Fixture-Writes\\Writer",
    "fixture-writes/independent-writer.py",
    "fixture-writes/independent-attempt.py",
)


def check_import_root_isolation() -> None:
    assert court_runtime.runtime_root().resolve() == _IMPORT_RUNTIME_ROOT
    expected_reference_root = (_IMPORT_SHIGUAN_ROOT / "references").resolve()
    assert court_runtime.reference_path().resolve() == expected_reference_root
    assert not court_runtime.reference_path("shiguan-imports", "pending").exists()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_skill_requirements_json() -> str:
    court_skill = Path(court_runtime.__file__).resolve().parents[1] / "SKILL.md"
    task_skill = TASK_SPECIFIC_SKILL_PATH
    if task_skill is None or not task_skill.is_file():
        raise AssertionError("task-specific lifecycle skill fixture is unavailable")
    requirements = []
    for name, source in (
        ("decretum-matrix", court_skill),
        ("task-specific-lifecycle-fixture", task_skill),
    ):
        digest = sha256(source)
        requirements.append(
            {
                "name": name,
                "source": str(source.resolve()),
                "sha256": digest,
                "purpose": "runtime assignment binding regression",
                "ack_name": name,
                "ack_sha256": digest,
            }
        )
    return json.dumps(requirements)


def formal_gate_fixture(*, mutates_state: bool = True) -> dict[str, object]:
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
        "rationale": "self-test formal court lifecycle task",
    }


def semantic_context_fixture() -> dict[str, object]:
    return {
        "authority_revision": 3,
        "authority_sha256": hashlib.sha256(b"lifecycle-authority-v3").hexdigest(),
        "plan_revision": 7,
        "plan_sha256": hashlib.sha256(b"lifecycle-plan-v7").hexdigest(),
        "plan_cursor": "phase1/rc4/lifecycle",
        "git_fingerprint": hashlib.sha256(b"lifecycle-worktree").hexdigest(),
        "recovery_checkpoint_id": "lifecycle-recovery-001",
        "shiguan_revision": 0,
        "shiguan_fingerprint": hashlib.sha256(b"synthetic-shiguan-none").hexdigest(),
    }


def semantic_args(task_id: str, trigger: str) -> Namespace:
    return Namespace(
        task_id=task_id,
        semantic_context=semantic_context_fixture(),
        semantic_context_file=None,
        trigger=trigger,
        actor="taizi",
        evidence=f"semantic {trigger} lifecycle fixture",
        note=f"semantic {trigger}",
    )


def dispatch_context_packet(
    task: dict[str, object],
    wave_id: str,
    *,
    fork_context: str = "none",
) -> dict[str, object]:
    receipt = task["semantic_receipt"]
    assert isinstance(receipt, dict)
    return {
        "schema": "court.semantic.dispatch_context_packet.v1",
        "task_id": task["task_id"],
        "sub_id": wave_id,
        "semantic_epoch": receipt["semantic_epoch"],
        "invariant_capsule_sha256": receipt["invariant_capsule_sha256"],
        "semantic_receipt_id": receipt["receipt_id"],
        "semantic_receipt_sha256": receipt["receipt_sha256"],
        "authority_sha256": receipt["authority_sha256"],
        "plan_sha256": receipt["plan_sha256"],
        "plan_cursor": receipt["plan_cursor"],
        "fork_context": fork_context,
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
            "text": "bounded lifecycle dispatch packet",
            "semantic_receipt_id": receipt["receipt_id"],
            "semantic_receipt_sha256": receipt["receipt_sha256"],
        },
    }


def context_budget_pool(task_id: str, wave_id: str) -> dict[str, object]:
    return normalize_budget_pool(
        total_share=100.0,
        root_id="taizi",
        reserve_share=10.0,
        hard_limits=CONTEXT_HARD_LIMITS,
        task_id=task_id,
        phase="P00-RUNTIME-01",
        wave_id=wave_id,
        approved_by="taizi",
        approved_at="2026-07-16T00:00:00+00:00",
        expected_output="bounded structured dispatch receipt",
        return_conditions=("COMPLETED", "FAILED_CLOSED", "CANCELLED"),
    )


def create_task(task_id: str) -> None:
    for key in tuple(_FIXTURE_WAVE_SLOTS):
        if key[0] == task_id:
            del _FIXTURE_WAVE_SLOTS[key]
    charter = "bounded ordinary parallel lifecycle fixture"
    charter_sha256 = hashlib.sha256(charter.encode("utf-8")).hexdigest()
    invariant_capsule = {
        "schema": "court.semantic.invariant_capsule.v1",
        "latest_decree_anchor": charter,
        "latest_decree_sha256": charter_sha256,
        "non_goals": ["do not expand the RC4 write set"],
        "boundaries": ["TemporaryDirectory fixture only"],
        "allowed_actions": ["synthetic lifecycle mutation"],
        "forbidden_actions": ["real Shiguan access"],
        "acceptance": ["focused lifecycle checker passes"],
        "evidence_requirements": ["current semantic receipt"],
        "stop_gates": ["semantic drift"],
        "write_set": [
            *(f"f/{index:02d}" for index in range(1, FIXTURE_SLOT_COUNT + 1)),
            *FIXTURE_EXPLICIT_WRITE_SET,
        ],
        "governing_hashes": {
            "execution_plan": hashlib.sha256(b"rc4-execution-plan").hexdigest()
        },
        "charter_sha256": charter_sha256,
    }
    court_runtime.create_task(
        Namespace(
            title=task_id,
            charter=charter,
            task_id=task_id,
            owner="taizi",
            report_tier="brief",
            evidence=f"create {task_id}",
            note="lifecycle fixture",
            work_kind="implementation",
            intake_gate=formal_gate_fixture(),
            intake_file=None,
            invariant_capsule=invariant_capsule,
            invariant_capsule_file=None,
        )
    )
    court_runtime.semantic_checkpoint_task(semantic_args(task_id, "checkpoint"))
    court_runtime.semantic_verify_task(semantic_args(task_id, "verify"))


def admit(task_id: str, wave_id: str, role: str = "gongbu", **overrides: object) -> dict[str, object]:
    office_api = bool(overrides.pop("office_api", False))
    return_namespace = bool(overrides.pop("return_namespace", False))
    child_worker = bool(overrides.pop("child_worker", False))
    office_write_set = overrides.pop("office_write_set", None)
    task = court_runtime.load_tasks()[task_id]
    receipt = task["semantic_receipt"]
    packet = (
        overrides.pop("dispatch_context_packet")
        if "dispatch_context_packet" in overrides
        else dispatch_context_packet(task, wave_id)
    )
    pool = (
        overrides.pop("context_budget_pool")
        if "context_budget_pool" in overrides
        else context_budget_pool(task_id, wave_id)
    )
    result_mode = overrides.pop(
        "context_result_mode",
        "bounded_structured_receipt",
    )
    tool_output_mode = overrides.pop("context_tool_output_mode", "pointer")
    override_source = overrides.pop("context_override_source", None)
    context_contract_required = overrides.pop("_context_contract_required", True)
    requested_roles_text = str(overrides.get("requested_roles", role) or role)
    requested_roles = [item.strip() for item in requested_roles_text.split(",") if item.strip()]
    requested_count = int(overrides.get("requested_agents", len(requested_roles)) or 0)
    approved_roles = requested_roles[:requested_count]
    slot_key = (task_id, wave_id)
    slot = _FIXTURE_WAVE_SLOTS.get(slot_key)
    if slot is None:
        next_slot = 1 + max(
            (base + count - 1 for (bound_task, _), (base, count) in _FIXTURE_WAVE_SLOTS.items() if bound_task == task_id),
            default=0,
        )
        slot = (next_slot, max(1, len(approved_roles)))
        if slot[0] + slot[1] - 1 > FIXTURE_SLOT_COUNT:
            raise AssertionError("lifecycle fixture write slots exhausted")
        _FIXTURE_WAVE_SLOTS[slot_key] = slot
    default_write_sets = [f"f/{slot[0] + index:02d}" for index in range(len(approved_roles))]
    default_calling_office = (
        approved_roles[0]
        if child_worker and len(set(approved_roles)) == 1
        else "taizi"
        if approved_roles
        and all(item in {"zhongshu", "menxia", "shangshu"} for item in approved_roles)
        else "shangshu"
    )
    calling_office = str(
        overrides.get("calling_office", default_calling_office)
        or default_calling_office
    )
    office_direct_superiors = {
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
    }
    caller_direct_superior = str(
        overrides.get(
            "direct_superior",
            office_direct_superiors.get(calling_office, "taizi"),
        )
        or ""
    )
    bindings: list[dict[str, object]] = []
    for index, binding_role in enumerate(approved_roles, start=1):
        default_instance_id = (
            f"{binding_role}-worker-{index:04d}"
            if child_worker
            else binding_role
        )
        instance_id = str(
            overrides.get("office_instance_id", default_instance_id)
            or default_instance_id
        )
        direct_superior = (
            binding_role
            if child_worker
            else "shangshu"
            if binding_role in {"libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"}
            else "taizi"
        )
        preload_hashes = court_runtime._semantic_preload_hashes(binding_role)
        binding = {
            "role": binding_role,
            "instance_id": instance_id,
            "shard_id": f"{wave_id}-{binding_role}-{index:04d}",
            "direct_superior": direct_superior,
            "instance_kind": "office_worker_instance" if child_worker else "office",
            "canonical_authority": not child_worker,
            "owner_role": binding_role if child_worker else None,
            "worktree": ".",
            "write_set": list(office_write_set)
            if isinstance(office_write_set, (list, tuple))
            else [default_write_sets[index - 1]],
            "access_mode": "read_write",
            "read_scope": list(office_write_set)
            if isinstance(office_write_set, (list, tuple))
            else [default_write_sets[index - 1]],
            "mutation_allowed": True,
            "integration_authority": False,
            "preload_hashes": preload_hashes,
        }
        if child_worker:
            binding.update(
                child_role=(
                    "GongBu-GongJiang"
                    if binding_role == "gongbu"
                    else f"{binding_role}-worker"
                ),
                bounded_mandate=str(
                    overrides.get("bounded_mandate")
                    or "execute one bounded child-office assignment"
                ),
                expected_result=str(
                    overrides.get("expected_result")
                    or "return one bounded structured receipt"
                ),
                terminal_condition=str(
                    overrides.get("terminal_condition")
                    or "stop after the bounded receipt is accepted"
                ),
            )
        bindings.append(binding)
    budget_id = f"budget:{task_id}:{wave_id}"
    lease = {
        "schema": "court.agent.admission_lease.v2",
        "budget_id": budget_id,
        "status": "ACTIVE",
        "lease_id": f"{task_id}-{wave_id}-lease",
        "parent_budget_id": f"{budget_id}:{caller_direct_superior}",
        "parent_id": caller_direct_superior,
        "approved_by": caller_direct_superior,
        "grantee_role": calling_office,
        "lease_depth": 0,
        "approved_next_depth": 1,
        "expires_at_utc": "2099-01-01T00:00:00+00:00",
        "parent_write_scope": sorted(
            {
                str(path)
                for binding in bindings
                for path in binding["write_set"]
            }
        ),
        "approved_count": len(bindings),
        "task_id": task_id,
        "calling_office": calling_office,
        "direct_superior": caller_direct_superior,
        "integration_domain": "agent-lifecycle",
        "authority": "super",
        "approved_roles": [binding["role"] for binding in bindings],
        "approved_instance_ids": [binding["instance_id"] for binding in bindings],
        "approved_shards": [binding["shard_id"] for binding in bindings],
        "approved_write_sets": {
            str(binding["instance_id"]): list(binding["write_set"])
            for binding in bindings
        },
        "approved_access_contracts": {
            str(binding["instance_id"]): {
                "access_mode": binding["access_mode"],
                "read_scope": list(binding["read_scope"]),
                "mutation_allowed": binding["mutation_allowed"],
                "integration_authority": binding["integration_authority"],
            }
            for binding in bindings
        },
        "approved_instance_shapes": {
            str(binding["instance_id"]): {
                "instance_kind": binding["instance_kind"],
                "canonical_authority": binding["canonical_authority"],
                "owner_role": binding["owner_role"],
                "direct_superior": binding["direct_superior"],
            }
            for binding in bindings
        },
        "approved_preload_hashes": {
            str(binding["instance_id"]): dict(binding["preload_hashes"])
            for binding in bindings
        },
    }
    values: dict[str, object] = {
        "task_id": task_id,
        "expected_semantic_epoch": task["semantic_epoch"],
        "expected_charter_sha256": task["charter_sha256"],
        "expected_invariant_capsule_sha256": task["invariant_capsule_sha256"],
        "expected_checkpoint_id": receipt["checkpoint_id"],
        "wave_id": wave_id,
        "execution_topology": "parallel",
        "active_session_protocol": "v2",
        "requested_fork_turns": "none",
        "context_tokens": 1000,
        "dispatch_context_packet": packet,
        "context_budget_pool": pool,
        "context_result_mode": result_mode,
        "context_tool_output_mode": tool_output_mode,
        "context_override_source": override_source,
        "_context_contract_required": context_contract_required,
        "message_chars": 100,
        "requested_agents": len(requested_roles),
        "requested_roles": requested_roles_text,
        "host_active_agents": 1,
        "host_capacity": 16,
        "host_retained_agents": 0,
        "host_reclamation_status": "verified",
        "next_depth": 1,
        "user_agent_budget": None,
        "provider_launch_budget": None,
        "budget_lease_json": json.dumps(lease, ensure_ascii=False),
        "requested_bindings_json": json.dumps(bindings, ensure_ascii=False),
        "integration_domain": "agent-lifecycle",
        "authority": "super",
        "calling_office": calling_office,
        "direct_superior": caller_direct_superior,
        **ROUTE,
        "actor": "shangshu",
        "evidence": f"admit {role} for {wave_id}",
        "note": "lifecycle fixture",
    }
    values.update(overrides)
    namespace = Namespace(**values)
    if return_namespace:
        return namespace  # type: ignore[return-value]
    handler = court_runtime.office_admit if office_api else court_runtime.agent_admit
    return handler(namespace)


def start_args(
    admission: dict[str, object],
    task_id: str,
    wave_id: str,
    agent_id: str,
    role: str = "gongbu",
    **overrides: object,
) -> Namespace:
    inputs = dict(admission.get("model_route_inputs") or ROUTE)
    task = court_runtime.load_tasks()[task_id]
    values: dict[str, object] = {
        "task_id": task_id,
        "semantic_epoch": admission.get("semantic_epoch"),
        "charter_sha256": admission.get("charter_sha256"),
        "invariant_capsule_sha256": admission.get("invariant_capsule_sha256"),
        "checkpoint_id": admission.get("checkpoint_id"),
        "dispatch_uid": admission.get("dispatch_uid"),
        "attempt": admission.get("attempt"),
        "agent_id": agent_id,
        "role": role,
        "collaboration_task_name": f"{role.replace('-', '_')}_lifecycle",
        "requires_gongjiang": False,
        "skill_requirements_json": runtime_skill_requirements_json(),
        "scope": inputs["assignment"],
        "task_focus": inputs["task_focus"],
        "complexity": inputs["complexity"],
        "risk": inputs["risk"],
        "ambiguity": inputs["ambiguity"],
        "transport": inputs["transport"],
        "wave_id": wave_id,
        "dispatch_requested_at": admission.get("dispatch_requested_at"),
        "fork_turns": "none",
        "context_tokens": 1000,
        "dispatch_context_packet": dispatch_context_packet(task, wave_id),
        "context_budget_pool": context_budget_pool(task_id, wave_id),
        "context_result_mode": "bounded_structured_receipt",
        "context_tool_output_mode": "pointer",
        "context_override_source": None,
        "system_memory_percent": admission.get("context_system_memory_percent", 0.0),
        "_context_contract_required": True,
        "deadline_seconds": 600,
        "tool_call_budget": 8,
        "actor": "shangshu",
        "evidence": f"start {agent_id}",
        "note": "lifecycle fixture",
    }
    values.update(overrides)
    return Namespace(**values)


def ack_args(task_id: str, agent_id: str, role: str = "gongbu", **overrides: object) -> Namespace:
    record = court_runtime.load_tasks()[task_id]["agents"][agent_id]
    manifest = record["preload_manifest"]
    values: dict[str, object] = {
        "task_id": task_id,
        "agent_id": agent_id,
        "role": role,
        "semantic_epoch": record.get("semantic_epoch"),
        "charter_sha256": record.get("charter_sha256"),
        "invariant_capsule_sha256": record.get("invariant_capsule_sha256"),
        "checkpoint_id": record.get("checkpoint_id"),
        "dispatch_uid": record.get("dispatch_uid"),
        "attempt": record.get("attempt"),
        "office_zh": "",
        "direct_superior": manifest["direct_superior"],
        "profile_hash": manifest["profile_hash"],
        "dossier_hash": manifest["dossier_hash"],
        "court_skill_hash": manifest["court_skill_hash"],
        "loaded_skills": "decretum-matrix,tdd",
        "agent_dossier_loaded": "YES",
        "model_route_id": record["model_route"]["model_route_id"],
        "active_model": "",
        "active_reasoning_effort": "",
        "model_override_applied": "NO",
        "inheritance_policy": record["model_route"]["inheritance_policy"],
        "schema": manifest["preload_ack_schema"],
        "preload_status": "PASSED",
        "actor": "shangshu",
        "evidence": f"ack {agent_id}",
        "note": "lifecycle fixture",
    }
    values.update(overrides)
    return Namespace(**values)


def event_args(task_id: str, agent_id: str, role: str = "gongbu", **overrides: object) -> Namespace:
    agents = court_runtime.load_tasks()[task_id].get("agents")
    record = agents.get(agent_id, {}) if isinstance(agents, dict) else {}
    write_set_sha256 = hashlib.sha256(
        json.dumps(
            record.get("write_set"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    result_envelope = {
        "schema": "court.office.result.v1",
        "task_id": task_id,
        "semantic_epoch": record.get("semantic_epoch"),
        "charter_sha256": record.get("charter_sha256"),
        "invariant_capsule_sha256": record.get("invariant_capsule_sha256"),
        "checkpoint_id": record.get("checkpoint_id"),
        "dispatch_uid": record.get("dispatch_uid"),
        "attempt": record.get("attempt"),
        "office_instance_id": record.get("office_instance_id"),
        "agent_id": agent_id,
        "role": role,
        "direct_superior": record.get("direct_superior"),
        "worktree": record.get("worktree"),
        "write_set_sha256": write_set_sha256,
        "status": "completed",
        "summary": "bounded structured lifecycle result",
        "evidence": ["synthetic-lifecycle-result-pointer"],
        "produced_at": "2026-07-16T00:00:00+00:00",
    }
    values: dict[str, object] = {
        "task_id": task_id,
        "agent_id": agent_id,
        "role": role,
        "semantic_epoch": record.get("semantic_epoch"),
        "charter_sha256": record.get("charter_sha256"),
        "invariant_capsule_sha256": record.get("invariant_capsule_sha256"),
        "checkpoint_id": record.get("checkpoint_id"),
        "dispatch_uid": record.get("dispatch_uid"),
        "attempt": record.get("attempt"),
        "actor": "shangshu",
        "evidence": f"event {agent_id}",
        "note": "lifecycle fixture",
        "result": "done",
        "result_envelope": result_envelope,
        "result_envelope_file": None,
        "status": "completed",
    }
    values.update(overrides)
    return Namespace(**values)


def finish_args(task_id: str, agent_id: str, role: str = "gongbu", **overrides: object) -> Namespace:
    return event_args(task_id, agent_id, role, result="", **overrides)


def reject_unchanged(task_id: str, action: Callable[[], object], label: str) -> None:
    tasks_path = court_runtime.tasks_path()
    events_path = court_runtime.events_path()
    before_task_bytes = tasks_path.read_bytes() if tasks_path.exists() else b""
    before_event_bytes = events_path.read_bytes() if events_path.exists() else b""
    before = court_runtime.load_tasks()[task_id]
    try:
        action()
    except ValueError:
        pass
    else:
        raise AssertionError(label)
    after = court_runtime.load_tasks()[task_id]
    assert after == before
    assert after["last_evidence"] == before["last_evidence"]
    assert (tasks_path.read_bytes() if tasks_path.exists() else b"") == before_task_bytes
    assert (events_path.read_bytes() if events_path.exists() else b"") == before_event_bytes


def runtime_bytes(path: Path) -> bytes:
    return path.read_bytes() if path.exists() else b""


def reject_runtime_bytes_unchanged(action: Callable[[], object], label: str, expected_reason: str) -> None:
    tasks_path = court_runtime.tasks_path()
    events_path = court_runtime.events_path()
    before_tasks = runtime_bytes(tasks_path)
    before_events = runtime_bytes(events_path)
    try:
        action()
    except ValueError as exc:
        assert expected_reason in str(exc), (expected_reason, str(exc))
    else:
        raise AssertionError(label)
    assert runtime_bytes(tasks_path) == before_tasks, f"{label}: tasks.json bytes changed"
    assert runtime_bytes(events_path) == before_events, f"{label}: events JSONL bytes changed"


def set_task_field(task_id: str, mutate: Callable[[dict[str, object]], None]) -> None:
    tasks = court_runtime.load_tasks()
    mutate(tasks[task_id])
    court_runtime.write_tasks(tasks)


def check_admission_binding() -> None:
    budget_task = "message-budget-ledger"
    create_task(budget_task)
    budgeted = admit(budget_task, "budget-wave", message_chars=9000)
    assert budgeted["allowed"] is True
    assert budgeted["message_budget_effective_chars"] == 9000
    stored_budget = court_runtime.load_tasks()[budget_task]["agent_admissions"]["budget-wave"]
    for field in (
        "message_budget_schema",
        "message_measurement",
        "message_scope",
        "message_chars",
        "message_budget_floor_chars",
        "message_budget_quantum_chars",
        "message_budget_ceiling_chars",
        "message_budget_effective_chars",
        "message_budget_status",
        "message_required_chars",
        "message_optional_chars",
        "message_component_status",
        "message_overage_chars",
        "required_reduction_chars",
        "optional_compression_target_chars",
        "required_message_overage_chars",
        "compression_possible_without_required_loss",
        "message_budget_retryable",
        "compression_guidance",
    ):
        assert stored_budget[field] == budgeted[field]
    budget_events = court_runtime.read_events(limit=10, task_id=budget_task)
    budget_event = next(event for event in budget_events if event["action"] == "agent_admit")
    assert budget_event["message_chars"] == 9000
    assert budget_event["message_budget_effective_chars"] == 9000
    assert budget_event["message_budget_status"] == "within_budget"
    assert 0 < budgeted["dispatch_context_packet_bytes"] < 2048
    assert budgeted["dispatch_context_packet_bytes"] != budgeted["message_budget_effective_chars"]

    task_id = "lifecycle-binding"
    create_task(task_id)
    route = admit(task_id, "route-wave")
    route_id = route["model_routes"]["gongbu"]["model_route_id"]
    stored_route = court_runtime.load_tasks()[task_id]["agent_admissions"]["route-wave"]
    for hierarchy_record in (route, stored_route):
        assert hierarchy_record["hierarchy_gate"] == "PASSED"
        assert hierarchy_record["hierarchy_schema"] == "court.dispatch_hierarchy.v1"
        assert re.fullmatch(
            r"[0-9a-f]{64}",
            str(hierarchy_record["hierarchy_manifest_sha256"]),
        )
        assert hierarchy_record["hierarchy_edge_class"] == "ministry_execution_dispatch"
        assert hierarchy_record["hierarchy_calling_office"] == "shangshu"
        assert hierarchy_record["hierarchy_target_role"] == "gongbu"
        assert hierarchy_record["hierarchy_owner_role"] is None

    reject_unchanged(
        task_id,
        lambda: admit(task_id, "route-wave", assignment="duplicate"),
        "duplicate wave overwrote admission",
    )

    create_task("corrupt-admissions")
    set_task_field("corrupt-admissions", lambda task: task.__setitem__("agent_admissions", []))
    reject_unchanged(
        "corrupt-admissions",
        lambda: admit("corrupt-admissions", "wave"),
        "corrupt admission ledger was replaced",
    )

    reject_unchanged(
        task_id,
        lambda: court_runtime.agent_start(start_args(route, task_id, "missing-wave", "missing")),
        "missing admission minted a route",
    )
    denied = admit(task_id, "denied-wave", host_capacity=None)
    assert denied["allowed"] is False
    reject_unchanged(
        task_id,
        lambda: court_runtime.agent_start(start_args(denied, task_id, "denied-wave", "denied")),
        "denied admission started",
    )
    reject_unchanged(
        task_id,
        lambda: court_runtime.agent_start(
            start_args(route, task_id, "route-wave", "timestamp-mismatch", dispatch_requested_at="2020-01-01T00:00:00+00:00")
        ),
        "mismatched dispatch timestamp started",
    )

    expired = admit(task_id, "expired-wave")
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=601)).isoformat(timespec="seconds")

    def expire(task: dict[str, object]) -> None:
        record = task["agent_admissions"]["expired-wave"]
        record["dispatch_requested_at"] = expired_at
        record["generated_at"] = expired_at

    set_task_field(task_id, expire)
    reject_unchanged(
        task_id,
        lambda: court_runtime.agent_start(
            start_args(expired, task_id, "expired-wave", "expired", dispatch_requested_at=expired_at)
        ),
        "expired exact admission started",
    )

    mismatch = admit(task_id, "mismatch-wave")
    for field, value in (
        ("scope", "different"),
        ("task_focus", "different"),
        ("complexity", "low"),
        ("risk", "critical"),
        ("ambiguity", "low"),
        ("transport", "claude-code"),
    ):
        reject_unchanged(
            task_id,
            lambda field=field, value=value: court_runtime.agent_start(
                start_args(mismatch, task_id, "mismatch-wave", f"mismatch-{field}", **{field: value})
            ),
            f"routing mismatch accepted: {field}",
        )
    for field, value in (
        ("fork_turns", "1"),
        ("context_tokens", 1001),
        ("deadline_seconds", 601),
        ("tool_call_budget", 9),
    ):
        reject_unchanged(
            task_id,
            lambda field=field, value=value: court_runtime.agent_start(
                start_args(mismatch, task_id, "mismatch-wave", f"budget-{field}", **{field: value})
            ),
            f"admission budget exceeded: {field}",
        )

    create_task("corrupt-consumed")
    corrupt = admit("corrupt-consumed", "wave")

    def corrupt_consumed(task: dict[str, object]) -> None:
        task["agent_admissions"]["wave"]["consumed_instances"] = []

    set_task_field("corrupt-consumed", corrupt_consumed)
    reject_unchanged(
        "corrupt-consumed",
        lambda: court_runtime.agent_start(start_args(corrupt, "corrupt-consumed", "wave", "agent")),
        "corrupt consumed_instances was replaced",
    )

    started = court_runtime.agent_start(start_args(route, task_id, "route-wave", "gongbu-agent-1"))
    agent = started.task["agents"]["gongbu-agent-1"]
    assert agent["model_route"]["model_route_id"] == route_id
    for field in (
        "hierarchy_gate",
        "hierarchy_schema",
        "hierarchy_manifest_sha256",
        "hierarchy_edge_class",
        "hierarchy_calling_office",
        "hierarchy_target_role",
        "hierarchy_owner_role",
    ):
        assert started.event[field] == agent[field]
    assert started.task["agent_admissions"]["route-wave"]["consumed_instances"]["gongbu"] == "gongbu-agent-1"
    reject_unchanged(
        task_id,
        lambda: court_runtime.agent_start(start_args(route, task_id, "route-wave", "gongbu-agent-2")),
        "consumed admitted role reused",
    )
    reject_unchanged(
        task_id,
        lambda: court_runtime.agent_start(start_args(route, task_id, "route-wave", "gongbu-agent-1")),
        "existing agent id restarted",
    )
    for action in (
        lambda: court_runtime.agent_heartbeat(event_args(task_id, "unknown")),
        lambda: court_runtime.agent_report(event_args(task_id, "unknown")),
        lambda: court_runtime.agent_finish(finish_args(task_id, "unknown")),
        lambda: court_runtime.agent_close(event_args(task_id, "unknown")),
    ):
        reject_unchanged(task_id, action, "unknown agent lifecycle accepted")
    for action in (
        lambda: court_runtime.agent_heartbeat(event_args(task_id, "gongbu-agent-1", "menxia")),
        lambda: court_runtime.agent_report(event_args(task_id, "gongbu-agent-1", "menxia")),
        lambda: court_runtime.agent_finish(finish_args(task_id, "gongbu-agent-1", "menxia")),
        lambda: court_runtime.agent_close(event_args(task_id, "gongbu-agent-1", "menxia")),
        lambda: court_runtime.agent_preload_ack(ack_args(task_id, "gongbu-agent-1", "menxia")),
    ):
        reject_unchanged(task_id, action, "role mismatch mutated lifecycle")
    reject_unchanged(
        task_id,
        lambda: court_runtime.agent_event(event_args(task_id, "gongbu-agent-1"), "unknown_action", "running", "evidence"),
        "unknown lifecycle action accepted",
    )

    prestart_task = "prestart-capacity-failure"
    create_task(prestart_task)
    prestart_admission = admit(
        prestart_task,
        "prestart-wave",
        requested_roles="menxia,shangshu",
        requested_agents=2,
        host_capacity=4,
        host_active_agents=1,
    )
    failed = court_runtime.agent_spawn_failed(
        Namespace(
            task_id=prestart_task,
            wave_id="prestart-wave",
            role="menxia",
            error_kind="capacity",
            result="host refused before agent record existed",
            actor="taizi",
            evidence="agent thread limit reached",
            note="prestart capacity fixture",
        )
    )
    assert failed["kind"] == "court_agent_spawn_failed"
    assert failed["failed_role"] == "menxia"
    assert failed["failed_instance_id"] == "menxia"
    assert failed["deferred_roles"] == ["shangshu"]
    assert court_runtime.load_tasks()[prestart_task]["agents"] == {}
    assert court_runtime.load_tasks()[prestart_task]["agent_wave_blocks"]["prestart-wave"]["error_kind"] == "capacity"
    reject_unchanged(
        prestart_task,
        lambda: court_runtime.agent_start(
            start_args(prestart_admission, prestart_task, "prestart-wave", "menxia-late-1", role="menxia")
        ),
        "capacity-failed role started after the wave was blocked",
    )


def check_runtime_generates_bounded_child_profile() -> None:
    task_id = "runtime-generated-bounded-child-profile"
    wave_id = "runtime-generated-bounded-child-profile-wave"
    create_task(task_id)
    admission = admit(
        task_id,
        wave_id,
        role="gongbu",
        child_worker=True,
        office_instance_id="gongbu-worker-0001",
        office_write_set=["work/gongbu/worker-0001.txt"],
    )
    assert admission["allowed"] is True
    binding = admission["selected_bindings"][0]
    profile = binding["child_profile"]
    assert profile["schema"] == "court.child_office_profile.v1"
    assert profile["child_role"] == "GongBu-GongJiang"
    assert profile["owner_role"] == "gongbu"
    assert profile["direct_superior"] == "gongbu"
    assert profile["canonical_authority"] is False
    assert profile["read_scope"] == ["work/gongbu/worker-0001.txt"]
    assert profile["write_set"] == ["work/gongbu/worker-0001.txt"]
    assert profile["dispatch_context_packet_sha256"] == admission["dispatch_context_packet_sha256"]
    assert profile["semantic_receipt_sha256"] == admission["semantic_receipt_sha256"]
    assert profile["invariant_capsule_sha256"] == admission["invariant_capsule_sha256"]
    assert binding["hierarchy_edge_class"] == "bounded_child_office"
    assert binding["hierarchy_calling_office"] == "gongbu"
    assert binding["hierarchy_owner_role"] == "gongbu"
    request_binding = admission["requested_bindings"][0]
    approved_binding_sha256s = admission["budget_lease"][
        "approved_binding_sha256s"
    ]
    assert approved_binding_sha256s == {
        "gongbu-worker-0001": canonical_child_office_binding_sha256(
            request_binding
        )
    }
    admission_binding_sha256s = admission["admission_binding_sha256s"]
    assert admission_binding_sha256s == {
        "gongbu-worker-0001": canonical_child_office_binding_sha256(binding)
    }
    stored = court_runtime.load_tasks()[task_id]["agent_admissions"][wave_id]
    assert stored["selected_bindings"][0]["child_profile"] == profile
    assert stored["admission_binding_sha256s"] == admission_binding_sha256s


def check_caller_child_binding_digest_rejected_before_admission_write() -> None:
    cases = (
        (
            "mismatch",
            {"gongbu-worker-caller-digest-0001": "0" * 64},
            "approved_budget_binding_digest_mismatch",
        ),
        (
            "partial",
            {},
            "approved_budget_binding_digest_missing",
        ),
    )
    for suffix, supplied_digests, expected_reason in cases:
        task_id = f"caller-child-binding-digest-{suffix}"
        wave_id = f"caller-child-binding-digest-{suffix}-wave"
        create_task(task_id)
        namespace = admit(
            task_id,
            wave_id,
            role="gongbu",
            child_worker=True,
            office_instance_id="gongbu-worker-caller-digest-0001",
            office_write_set=[
                f"work/gongbu/worker-caller-digest-{suffix}-0001.txt"
            ],
            return_namespace=True,
        )
        lease = json.loads(namespace.budget_lease_json)
        lease["approved_binding_sha256s"] = supplied_digests
        namespace.budget_lease_json = json.dumps(lease, ensure_ascii=False)
        reject_runtime_bytes_unchanged(
            lambda: court_runtime.agent_admit(namespace),
            f"caller {suffix} child binding digest reached admission persistence",
            expected_reason,
        )


def check_child_profile_tamper_rejected_before_start_write() -> None:
    task_id = "child-profile-start-tamper"
    wave_id = "child-profile-start-tamper-wave"
    create_task(task_id)
    admission = admit(
        task_id,
        wave_id,
        role="gongbu",
        child_worker=True,
        office_instance_id="gongbu-worker-tamper-0001",
        office_write_set=["work/gongbu/worker-tamper-0001.txt"],
    )

    def tamper_profile(task: dict[str, object]) -> None:
        widened_mandate = "silently widened but still non-empty mandate"
        binding = task["agent_admissions"][wave_id]["selected_bindings"][0]
        binding["bounded_mandate"] = widened_mandate
        binding["child_profile"]["bounded_mandate"] = widened_mandate
        task["agent_admissions"][wave_id]["admission_binding_sha256s"][
            "gongbu-worker-tamper-0001"
        ] = canonical_child_office_binding_sha256(binding)

    set_task_field(task_id, tamper_profile)
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.agent_start(
            start_args(
                admission,
                task_id,
                wave_id,
                "gongbu-gongjiang-tamper-1",
                collaboration_task_name="gongbu_gongjiang_tamper",
                requires_gongjiang=True,
            )
        ),
        "synchronized binding and child-profile tamper reached agent start persistence",
        "agent_start_admission_immutable_anchor_mismatch",
    )


def check_budget_lease_access_contract_allows_approved_subset() -> None:
    approved_bindings = [
        {
            "instance_id": f"gongbu-worker-subset-{index:04d}",
            "write_set": [f"work/gongbu/subset-{index:04d}.txt"],
            "access_mode": "read_write",
            "read_scope": [f"work/gongbu/subset-{index:04d}.txt"],
            "mutation_allowed": True,
            "integration_authority": False,
        }
        for index in (1, 2)
    ]
    lease = {
        "status": "ACTIVE",
        "approved_instance_ids": [
            binding["instance_id"] for binding in approved_bindings
        ],
        "approved_write_sets": {
            binding["instance_id"]: list(binding["write_set"])
            for binding in approved_bindings
        },
        "approved_access_contracts": {
            binding["instance_id"]: {
                "access_mode": binding["access_mode"],
                "read_scope": list(binding["read_scope"]),
                "mutation_allowed": binding["mutation_allowed"],
                "integration_authority": binding["integration_authority"],
            }
            for binding in approved_bindings
        },
    }
    assert budget_lease_access_contract_error(lease, approved_bindings[:1]) is None
    unknown = dict(approved_bindings[0])
    unknown["instance_id"] = "gongbu-worker-subset-unknown"
    assert (
        budget_lease_access_contract_error(lease, [unknown])
        == "approved_budget_access_contract_mismatch"
    )


def check_child_access_contract_tamper_rejected_before_start_write() -> None:
    task_id = "child-access-contract-start-tamper"
    wave_id = "child-access-contract-start-tamper-wave"
    create_task(task_id)
    admission = admit(
        task_id,
        wave_id,
        role="gongbu",
        child_worker=True,
        office_instance_id="gongbu-worker-access-tamper-0001",
        office_write_set=["work/gongbu/worker-access-tamper-0001.txt"],
    )

    def tamper_access_contract(task: dict[str, object]) -> None:
        widened_scope = ["work/gongbu/unleased-output.txt"]
        binding = task["agent_admissions"][wave_id]["selected_bindings"][0]
        binding["write_set"] = widened_scope
        binding["read_scope"] = widened_scope
        binding["child_profile"]["write_set"] = widened_scope
        binding["child_profile"]["read_scope"] = widened_scope

    set_task_field(task_id, tamper_access_contract)
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.agent_start(
            start_args(
                admission,
                task_id,
                wave_id,
                "gongbu-gongjiang-access-tamper-1",
                collaboration_task_name="gongbu_gongjiang_access_tamper",
                requires_gongjiang=True,
            )
        ),
        "synchronized child access-contract tamper reached agent start persistence",
        "agent_start_admission_immutable_anchor_mismatch",
    )


def check_dispatch_context_economy_contract() -> None:
    missing_task = "context-contract-missing"
    create_task(missing_task)
    reject_runtime_bytes_unchanged(
        lambda: admit(
            missing_task,
            "missing-packet-wave",
            dispatch_context_packet=None,
        ),
        "production agent admission accepted a missing context packet",
        "dispatch_context_packet_required",
    )

    task = court_runtime.load_tasks()[missing_task]
    stale_packet = dispatch_context_packet(task, "stale-packet-wave")
    stale_packet["semantic_receipt_sha256"] = "0" * 64
    reject_runtime_bytes_unchanged(
        lambda: admit(
            missing_task,
            "stale-packet-wave",
            dispatch_context_packet=stale_packet,
        ),
        "stale semantic receipt packet was admitted",
        "dispatch_context_receipt_mismatch:semantic_receipt_sha256",
    )

    second_capsule = dispatch_context_packet(task, "second-capsule-wave")
    second_capsule["second_invariant_capsule_sha256"] = "1" * 64
    reject_runtime_bytes_unchanged(
        lambda: admit(
            missing_task,
            "second-capsule-wave",
            dispatch_context_packet=second_capsule,
        ),
        "a second invariant capsule was admitted",
        "dispatch_context_packet_fields_unknown:second_invariant_capsule_sha256",
    )

    implicit_full = dispatch_context_packet(task, "implicit-full-wave")
    implicit_full.update(
        context_mode="full",
        full_context={"transcript": "bounded fixture"},
        budget_override={
            "explicit": True,
            "granted_by": "user",
            "max_bytes": 4096,
        },
    )
    reject_runtime_bytes_unchanged(
        lambda: admit(
            missing_task,
            "implicit-full-wave",
            dispatch_context_packet=implicit_full,
            context_override_source=None,
        ),
        "implicit full context was admitted",
        "implicit_full_context_forbidden",
    )

    over_budget = dispatch_context_packet(task, "over-budget-wave")
    over_budget["summary"]["text"] = "x" * 4096
    reject_runtime_bytes_unchanged(
        lambda: admit(
            missing_task,
            "over-budget-wave",
            dispatch_context_packet=over_budget,
        ),
        "over-budget context packet was admitted",
        "dispatch_context_packet_exceeds_2kib",
    )
    reject_runtime_bytes_unchanged(
        lambda: admit(
            missing_task,
            "missing-pool-wave",
            context_budget_pool=None,
        ),
        "context admission without a budget pool was accepted",
        "context_budget_pool_required",
    )
    reject_runtime_bytes_unchanged(
        lambda: admit(
            missing_task,
            "stale-pool-wave",
            context_budget_pool=context_budget_pool(
                missing_task,
                "different-wave",
            ),
        ),
        "a budget pool bound to a different wave was accepted",
        "context_budget_pool_wave_mismatch",
    )
    reject_runtime_bytes_unchanged(
        lambda: admit(
            missing_task,
            "free-result-wave",
            context_result_mode="free_text",
        ),
        "unbounded result mode was admitted",
        "bounded_structured_receipt_required",
    )
    reject_runtime_bytes_unchanged(
        lambda: admit(
            missing_task,
            "raw-tool-wave",
            context_tool_output_mode="raw",
        ),
        "raw tool output mode was admitted",
        "aggregate_or_pointer_tool_output_required",
    )

    explicit_full = dispatch_context_packet(task, "explicit-full-wave")
    explicit_full.update(
        context_mode="full",
        full_context={"bounded_pointer_expansion": ["authority/current.md"]},
        budget_override={
            "explicit": True,
            "granted_by": "taizi",
            "max_bytes": 4096,
        },
    )
    explicit = admit(
        missing_task,
        "explicit-full-wave",
        dispatch_context_packet=explicit_full,
        context_override_source="taizi_explicit_budget",
    )
    assert explicit["context_economy_decision"] == "APPROVED_OVERRIDE"
    assert explicit["context_mode"] == "full"

    office_task = "context-contract-office"
    create_task(office_task)
    open_decree(office_task)
    office_values = {
        "office_api": True,
        "office_instance_kind": "child_agent",
        "office_instance_id": "gongbu-context-01",
        "collaboration_task_name": "gongbu_context_01",
        "carrier_proof": {"agent_id": "gongbu-context-01"},
    }
    reject_runtime_bytes_unchanged(
        lambda: admit(
            office_task,
            "office-missing-packet-wave",
            dispatch_context_packet=None,
            **office_values,
        ),
        "generic office admission accepted a missing context packet",
        "dispatch_context_packet_required",
    )

    positive = admit(
        office_task,
        "office-context-wave",
        **office_values,
    )
    hash_fields = {
        "dispatch_context_packet_sha256",
        "semantic_receipt_sha256",
        "context_economy_receipt_sha256",
        "context_budget_pool_sha256",
    }
    assert hash_fields.issubset(positive)
    assert hash_fields.issubset(positive["receipt"])
    stored = court_runtime.load_tasks()[office_task]["agent_admissions"]["office-context-wave"]
    assert hash_fields.issubset(stored)
    admission_event = next(
        event
        for event in court_runtime.read_events(limit=20, task_id=office_task)
        if event["action"] == "agent_admit" and event["wave_id"] == "office-context-wave"
    )
    assert hash_fields.issubset(admission_event)

    reject_runtime_bytes_unchanged(
        lambda: court_runtime.office_start(
            start_args(
                positive,
                office_task,
                "office-context-wave",
                "gongbu-context-01",
                instance_id="gongbu-context-01",
                collaboration_task_name="gongbu_context_01",
                office_instance_kind="child_agent",
                office_instance_id="gongbu-context-01",
                carrier_proof={"agent_id": "gongbu-context-01"},
                dispatch_context_packet=None,
            )
        ),
        "start accepted a missing context packet",
        "dispatch_context_packet_required",
    )

    started = court_runtime.office_start(
        start_args(
            positive,
            office_task,
            "office-context-wave",
            "gongbu-context-01",
            instance_id="gongbu-context-01",
            collaboration_task_name="gongbu_context_01",
            office_instance_kind="child_agent",
            office_instance_id="gongbu-context-01",
            carrier_proof={"agent_id": "gongbu-context-01"},
        )
    )
    assert hash_fields.issubset(started["office_instance"])
    assert hash_fields.issubset(started["event"])

    tamper_task = "context-contract-start-recheck"
    create_task(tamper_task)
    open_decree(tamper_task)
    tamper_admission = admit(
        tamper_task,
        "context-tamper-wave",
        office_api=True,
        office_instance_kind="child_agent",
        office_instance_id="gongbu-context-02",
        collaboration_task_name="gongbu_context_02",
        carrier_proof={"agent_id": "gongbu-context-02"},
    )

    def tamper_packet(value: dict[str, object]) -> None:
        admission = value["agent_admissions"]["context-tamper-wave"]
        admission["dispatch_context_packet_sha256"] = "f" * 64

    set_task_field(tamper_task, tamper_packet)
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.office_start(
            start_args(
                tamper_admission,
                tamper_task,
                "context-tamper-wave",
                "gongbu-context-02",
                instance_id="gongbu-context-02",
                collaboration_task_name="gongbu_context_02",
                office_instance_kind="child_agent",
                office_instance_id="gongbu-context-02",
                carrier_proof={"agent_id": "gongbu-context-02"},
            )
        ),
        "tampered context packet passed start recheck",
        "agent_start_admission_immutable_anchor_mismatch",
    )


def check_terminal_and_identity() -> None:
    task_id = "terminal-agent"
    create_task(task_id)
    admission = admit(task_id, "terminal-wave")
    start = start_args(admission, task_id, "terminal-wave", "gongbu-terminal-1")
    court_runtime.agent_start(start)
    try:
        court_runtime.agent_preload_ack(ack_args(task_id, "gongbu-terminal-1", profile_hash="invalid"))
    except ValueError:
        pass
    else:
        raise AssertionError("invalid preload acknowledgement passed")
    terminal = court_runtime.load_tasks()[task_id]["agents"]["gongbu-terminal-1"]
    assert terminal["status"] == "failed"
    assert terminal["final_status"] == "failed"
    assert terminal["release_status"] == "closed"
    for action in (
        lambda: court_runtime.agent_heartbeat(event_args(task_id, "gongbu-terminal-1")),
        lambda: court_runtime.agent_report(event_args(task_id, "gongbu-terminal-1")),
        lambda: court_runtime.agent_finish(finish_args(task_id, "gongbu-terminal-1")),
        lambda: court_runtime.agent_start(start),
        lambda: court_runtime.agent_preload_ack(ack_args(task_id, "gongbu-terminal-1")),
    ):
        reject_unchanged(task_id, action, "terminal agent was mutated")

    identity_task = "manifest-identity"
    create_task(identity_task)
    identity_admission = admit(identity_task, "identity-wave")
    court_runtime.agent_start(start_args(identity_admission, identity_task, "identity-wave", "gongbu-identity-1"))
    parsed = court_runtime.build_parser().parse_args(
        [
            "agent-preload-ack",
            "--task-id",
            identity_task,
            "--agent-id",
            "gongbu-identity-1",
            "--role",
            "gongbu",
            "--direct-superior",
            "shangshu",
            "--profile-hash",
            court_runtime.load_tasks()[identity_task]["agents"]["gongbu-identity-1"]["preload_manifest"]["profile_hash"],
            "--dossier-hash",
            court_runtime.load_tasks()[identity_task]["agents"]["gongbu-identity-1"]["preload_manifest"]["dossier_hash"],
            "--court-skill-hash",
            court_runtime.load_tasks()[identity_task]["agents"]["gongbu-identity-1"]["preload_manifest"]["court_skill_hash"],
            "--loaded-skills",
            "decretum-matrix,tdd",
            "--agent-dossier-loaded",
            "YES",
            "--model-route-id",
            court_runtime.load_tasks()[identity_task]["agents"]["gongbu-identity-1"]["model_route"]["model_route_id"],
            "--model-override-applied",
            "NO",
            "--inheritance-policy",
            "inherit_main_thread_model_reserved_schema",
            "--evidence",
            "manifest identity",
        ]
    )
    acked = court_runtime.agent_preload_ack(parsed)
    assert acked["ack"]["office_zh"] == "工部"
    court_runtime.agent_report(event_args(identity_task, "gongbu-identity-1"))
    court_runtime.agent_heartbeat(event_args(identity_task, "gongbu-identity-1"))
    court_runtime.agent_finish(finish_args(identity_task, "gongbu-identity-1"))
    court_runtime.agent_close(event_args(identity_task, "gongbu-identity-1"))
    reject_unchanged(
        identity_task,
        lambda: court_runtime.agent_close(event_args(identity_task, "gongbu-identity-1")),
        "repeated close mutated record",
    )

    mojibake = admit(identity_task, "mojibake-wave")
    court_runtime.agent_start(start_args(mojibake, identity_task, "mojibake-wave", "gongbu-mojibake-1"))
    try:
        court_runtime.agent_preload_ack(ack_args(identity_task, "gongbu-mojibake-1", office_zh="å·¥éƒ¨"))
    except ValueError:
        pass
    else:
        raise AssertionError("inconsistent explicit office_zh passed")
    assert court_runtime.load_tasks()[identity_task]["agents"]["gongbu-mojibake-1"]["status"] == "failed"

    uppercase_task = "uppercase-digest-identity"
    create_task(uppercase_task)
    uppercase_admission = admit(uppercase_task, "uppercase-wave")
    court_runtime.agent_start(
        start_args(uppercase_admission, uppercase_task, "uppercase-wave", "gongbu-uppercase-1")
    )
    uppercase_record = court_runtime.load_tasks()[uppercase_task]["agents"]["gongbu-uppercase-1"]
    uppercase_manifest = uppercase_record["preload_manifest"]
    uppercase_ack = court_runtime.agent_preload_ack(
        ack_args(
            uppercase_task,
            "gongbu-uppercase-1",
            profile_hash=str(uppercase_manifest["profile_hash"]).upper(),
            dossier_hash=str(uppercase_manifest["dossier_hash"]).upper(),
            court_skill_hash=str(uppercase_manifest["court_skill_hash"]).upper(),
        )
    )
    assert uppercase_ack["agent"]["status"] == "running"
    assert uppercase_ack["agent"]["profile_hash"] == uppercase_manifest["profile_hash"]
    assert uppercase_ack["agent"]["dossier_hash"] == uppercase_manifest["dossier_hash"]
    assert uppercase_ack["agent"]["court_skill_hash"] == uppercase_manifest["court_skill_hash"]

    v1_task = "v1-inherited-model-lifecycle"
    create_task(v1_task)
    v1_admission = admit(
        v1_task,
        "v1-wave",
        protocol_mode="auto",
        active_session_protocol="v1",
        needs_agent_type_override=True,
    )
    assert v1_admission["selected_protocol"] == "v1"
    court_runtime.agent_start(start_args(v1_admission, v1_task, "v1-wave", "gongbu-v1-agent"))
    v1_ack = court_runtime.agent_preload_ack(ack_args(v1_task, "gongbu-v1-agent"))
    assert v1_ack["agent"]["status"] == "running"
    assert v1_ack["agent"]["model_override_applied"] is False
    assert v1_ack["agent"]["inheritance_policy"] == "inherit_main_thread_model_v1_agent_type"


def check_malformed_sibling_blocks_lifecycle_write() -> None:
    task_id = "malformed-sibling-lifecycle"
    create_task(task_id)
    path = court_runtime.tasks_path()
    raw_tasks = json.loads(path.read_text(encoding="utf-8"))
    raw_tasks["opaque-sibling"] = ["must", "survive", {"nested": [1, 2, 3]}]
    path.write_text(
        json.dumps(raw_tasks, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    before_tasks = path.read_bytes()
    events = court_runtime.events_path()
    before_events = events.read_bytes()
    try:
        admit(task_id, "blocked-by-malformed-sibling")
    except ValueError as exc:
        assert str(exc) == "tasks.json entry 'opaque-sibling' must contain an object"
    else:
        raise AssertionError("lifecycle write silently deleted a malformed sibling entry")
    assert path.read_bytes() == before_tasks
    assert events.read_bytes() == before_events


def check_office_name_identity_binding() -> None:
    rejected_cases = (
        ("gongbu", "runtime_r2", "worker-1", False, "office_name_mismatch"),
        ("gongbu", "notgongbu_runtime", "notgongbu-worker-1", False, "office_name_mismatch"),
        ("libu-hr", "recruitment", "libu-worker-1", False, "office_name_mismatch"),
        (
            "libu-hr",
            "libu_hrx_recruitment",
            "libu_hrx-worker-1",
            False,
            "office_name_mismatch",
        ),
        ("gongbu", "gongbu_runtime", "gongbu-worker-1", True, "missing_gongjiang"),
    )
    for index, (role, task_name, agent_id, requires_gongjiang, expected_reason) in enumerate(
        rejected_cases
    ):
        invalid_task = f"office-bound-invalid-{index}"
        create_task(invalid_task)
        invalid_admission = admit(
            invalid_task,
            f"office-bound-invalid-wave-{index}",
            role=role,
        )
        for attempt in range(2):
            reject_runtime_bytes_unchanged(
                lambda invalid_admission=invalid_admission, invalid_task=invalid_task, index=index, agent_id=agent_id, role=role, task_name=task_name, requires_gongjiang=requires_gongjiang: court_runtime.agent_start(
                    start_args(
                        invalid_admission,
                        invalid_task,
                        f"office-bound-invalid-wave-{index}",
                        agent_id,
                        role=role,
                        collaboration_task_name=task_name,
                        requires_gongjiang=requires_gongjiang,
                    )
                ),
                f"invalid office identity was accepted on attempt {attempt}: {expected_reason}",
                expected_reason,
            )

    skill_task = "office-bound-invalid-skill"
    create_task(skill_task)
    skill_admission = admit(skill_task, "office-bound-invalid-skill-wave")
    bad_requirements = json.loads(runtime_skill_requirements_json())
    bad_requirements[1]["sha256"] = "0" * 64
    bad_requirements[1]["ack_sha256"] = "0" * 64
    for attempt in range(2):
        reject_runtime_bytes_unchanged(
            lambda: court_runtime.agent_start(
                start_args(
                    skill_admission,
                    skill_task,
                    "office-bound-invalid-skill-wave",
                    "gongbu-skill-invalid-1",
                    skill_requirements_json=json.dumps(bad_requirements),
                )
            ),
            f"invalid skill binding was accepted on attempt {attempt}",
            "required_skill_hash_mismatch",
        )

    profile_task = "office-bound-invalid-profile"
    create_task(profile_task)
    profile_admission = admit(profile_task, "office-bound-invalid-profile-wave")
    original_builder = court_runtime.build_office_assignment_binding

    def reject_profile(**_: object) -> dict[str, object]:
        raise ValueError("standing_profile_identity_mismatch")

    court_runtime.build_office_assignment_binding = reject_profile  # type: ignore[assignment]
    try:
        for attempt in range(2):
            reject_runtime_bytes_unchanged(
                lambda: court_runtime.agent_start(
                    start_args(
                        profile_admission,
                        profile_task,
                        "office-bound-invalid-profile-wave",
                        "gongbu-profile-invalid-1",
                    )
                ),
                f"invalid profile binding was accepted on attempt {attempt}",
                "standing_profile_identity_mismatch",
            )
    finally:
        court_runtime.build_office_assignment_binding = original_builder

    persistence_task = "office-bound-identity"
    create_task(persistence_task)
    admission = admit(persistence_task, "office-bound-wave", role="libu-hr")
    court_runtime.agent_start(
        start_args(
            admission,
            persistence_task,
            "office-bound-wave",
            "libu-hr-worker-1",
            role="libu-hr",
            collaboration_task_name="libu_hr_recruitment",
            requires_gongjiang=False,
            official_name_head="FORGED",
            office_zh="伪署",
            profile_hash="f" * 64,
        )
    )
    persisted = court_runtime.load_tasks()[persistence_task]["agents"]["libu-hr-worker-1"]
    assert persisted["role_key"] == "libu-hr"
    assert persisted["office_name_token"] == "libu_hr"
    assert persisted["collaboration_task_name"] == "libu_hr_recruitment"
    assert persisted["court_agent_id"] == "libu-hr-worker-1"
    assert persisted["official_name_head"] == "LiBuHR"
    assert persisted["office_zh"] != "伪署"
    assert persisted["profile_hash"] != "f" * 64
    assert persisted["profile_binding"] == "PASSED"
    assert persisted["skill_binding"] == "PASSED"
    assert persisted["assignment_binding_ready"] is True
    assert persisted["office_execution_ready"] is False
    assert persisted["legacy_assignment_binding_unenforced"] is False
    assert len(persisted["required_skill_bindings"]) == 2
    court_runtime.agent_preload_ack(
        ack_args(persistence_task, "libu-hr-worker-1", role="libu-hr")
    )
    persisted = court_runtime.load_tasks()[persistence_task]["agents"]["libu-hr-worker-1"]
    assert persisted["office_execution_ready"] is True

    legacy_task = "legacy-assignment-read"
    create_task(legacy_task)
    tasks = court_runtime.load_tasks()
    tasks[legacy_task]["agents"] = {"legacy-1": {"agent_id": "legacy-1", "role": "gongbu"}}
    court_runtime.write_tasks(tasks)
    before = court_runtime.tasks_path().read_bytes()
    legacy = court_runtime.load_tasks()[legacy_task]["agents"]["legacy-1"]
    assert legacy["legacy_assignment_binding_unenforced"] is True
    assert legacy["office_execution_ready"] is False
    assert court_runtime.tasks_path().read_bytes() == before


def check_assignment_binding_toctou_rejected() -> None:
    task_id = "assignment-binding-toctou"
    create_task(task_id)
    admission = admit(task_id, "assignment-binding-toctou-wave")
    with tempfile.TemporaryDirectory() as fixture_dir:
        root = Path(fixture_dir)
        profiles = root / "profiles"
        profiles.mkdir()
        profile = profiles / "gongbu.toml"
        profile.write_text(
            '[profile]\nrole_key = "gongbu"\noffice_zh = "工部"\n'
            'direct_superior = "shangshu"\n',
            encoding="utf-8",
        )
        skill_root = root / "skills"
        court_skill = Path(court_runtime.__file__).resolve().parents[1] / "SKILL.md"
        tdd_skill = skill_root / "tdd" / "SKILL.md"
        tdd_skill.parent.mkdir(parents=True)
        tdd_skill.write_text("tdd fixture\n", encoding="utf-8")
        requirements = []
        for name, source in (
            ("decretum-matrix", court_skill),
            ("test-driven-development", tdd_skill),
        ):
            digest = sha256(source)
            requirements.append(
                {
                    "name": name,
                    "source": str(source.resolve()),
                    "sha256": digest,
                    "purpose": "TOCTOU fixture",
                    "ack_name": name,
                    "ack_sha256": digest,
                }
            )

        original_builder = court_runtime.build_office_assignment_binding
        original_lock = court_runtime.runtime_lock

        def fixture_builder(**kwargs: object) -> dict[str, object]:
            return original_builder(**kwargs, profile_root=profiles)  # type: ignore[arg-type]

        @contextmanager
        def mutating_lock(*args: object, **kwargs: object):
            with original_lock(*args, **kwargs):  # type: ignore[arg-type]
                profile.write_text(profile.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
                tdd_skill.write_text(tdd_skill.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
                yield

        court_runtime.build_office_assignment_binding = fixture_builder  # type: ignore[assignment]
        court_runtime.runtime_lock = mutating_lock  # type: ignore[assignment]
        try:
            reject_runtime_bytes_unchanged(
                lambda: court_runtime.agent_start(
                    start_args(
                        admission,
                        task_id,
                        "assignment-binding-toctou-wave",
                        "gongbu-toctou-1",
                        skill_requirements_json=json.dumps(requirements),
                    )
                ),
                "stale profile/skill binding was accepted",
                "stale_profile_or_skill",
            )
        finally:
            court_runtime.runtime_lock = original_lock  # type: ignore[assignment]
            court_runtime.build_office_assignment_binding = original_builder


def check_dispatch_hierarchy_revalidated_before_start_write() -> None:
    task_id = "dispatch-hierarchy-start-revalidation"
    wave_id = "dispatch-hierarchy-start-revalidation-wave"
    create_task(task_id)
    admission = admit(task_id, wave_id, role="gongbu")

    def tamper_caller(task: dict[str, object]) -> None:
        task["agent_admissions"][wave_id]["calling_office"] = "taizi"

    set_task_field(task_id, tamper_caller)
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.agent_start(
            start_args(
                admission,
                task_id,
                wave_id,
                "gongbu-hierarchy-tamper-1",
            )
        ),
        "tampered dispatch hierarchy reached agent start persistence",
        "agent_start_admission_immutable_anchor_mismatch",
    )


def check_three_department_hierarchy_revalidated_before_start_write() -> None:
    task_id = "three-department-hierarchy-start-revalidation"
    wave_id = "three-department-hierarchy-start-revalidation-wave"
    create_task(task_id)
    admission = admit(task_id, wave_id, role="menxia")

    def tamper_caller(task: dict[str, object]) -> None:
        task["agent_admissions"][wave_id]["calling_office"] = "shangshu"

    set_task_field(task_id, tamper_caller)
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.agent_start(
            start_args(
                admission,
                task_id,
                wave_id,
                "menxia-hierarchy-tamper-1",
                role="menxia",
            )
        ),
        "tampered three-department hierarchy reached agent start persistence",
        "agent_start_admission_immutable_anchor_mismatch",
    )


def check_dispatch_hierarchy_receipt_tamper_rejected_before_start_write() -> None:
    task_id = "dispatch-hierarchy-receipt-tamper"
    wave_id = "dispatch-hierarchy-receipt-tamper-wave"
    create_task(task_id)
    admission = admit(task_id, wave_id, role="gongbu")

    def tamper_manifest_hash(task: dict[str, object]) -> None:
        task["agent_admissions"][wave_id]["selected_bindings"][0][
            "hierarchy_manifest_sha256"
        ] = "0" * 64

    set_task_field(task_id, tamper_manifest_hash)
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.agent_start(
            start_args(
                admission,
                task_id,
                wave_id,
                "gongbu-hierarchy-receipt-tamper-1",
            )
        ),
        "tampered hierarchy receipt reached agent start persistence",
        "agent_start_admission_immutable_anchor_mismatch",
    )


def open_decree(task_id: str) -> dict[str, object]:
    task = court_runtime.load_tasks()[task_id]
    operation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"court-rc4:{task_id}"))
    result = court_runtime.decree_open_task(
        Namespace(
            task_id=task_id,
            operation_id=operation_id,
            payload={
                "title": task_id,
                "decree_anchor": "RC4 unified office lifecycle fixture",
                "lineage_parts": ["court", "runtime", "office-lifecycle"],
            },
            payload_file=None,
            expected_task_revision=task["task_revision"],
            killpoint="",
            actor="taizi",
            evidence=f"open decree {task_id}",
            note="RC4 lifecycle fixture",
        )
    )
    return dict(result["receipt"])


def run_git(path: Path, *args: str) -> str:
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    completed = subprocess.run(
        ["git", "-C", str(path), *args],
        check=False,
        capture_output=True,
        env=env,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"git fixture command failed: {args!r}: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def portable_host_path_key(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").casefold()


def recompute_worktree_fingerprint(proof: dict[str, object]) -> None:
    payload = {
        field: proof[field]
        for field in court_runtime.WORKTREE_PROOF_FIELDS
        if field != "worktree_fingerprint"
    }
    proof["worktree_fingerprint"] = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def ensure_git_worktree(
    fixture_root: Path,
    index: int,
    *,
    authority: str = "primary",
) -> Path:
    repo = fixture_root / "git-authorities" / authority / "court-capability-router"
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        run_git(repo, "init", "-b", "main")
        run_git(repo, "config", "user.email", "rc4-fixture@example.invalid")
        run_git(repo, "config", "user.name", "RC4 Fixture")
        (repo / "fixture.txt").write_text("RC4 Git authority fixture\n", encoding="utf-8")
        run_git(repo, "add", "fixture.txt")
        run_git(repo, "commit", "-m", "RC4 Git authority fixture")
    worktree = fixture_root / "git-worktrees" / authority / f"rc4-{index:02d}"
    if not worktree.exists():
        worktree.parent.mkdir(parents=True, exist_ok=True)
        branch = f"codex/gongbu-{authority}-rc4-{index:02d}"
        run_git(repo, "worktree", "add", "-b", branch, str(worktree), "HEAD")
    return worktree.resolve()


def worktree_proof(
    fixture_root: Path,
    index: int,
    *,
    authority: str = "primary",
) -> dict[str, object]:
    worktree = ensure_git_worktree(fixture_root, index, authority=authority)
    top = Path(run_git(worktree, "rev-parse", "--show-toplevel")).resolve()
    git_dir = Path(run_git(worktree, "rev-parse", "--absolute-git-dir")).resolve()
    common_dir = Path(
        run_git(
            worktree,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        )
    ).resolve()
    repo_id = common_dir.parent.name.casefold()
    worktree_token = "main" if git_dir == common_dir else git_dir.name.casefold()
    proof: dict[str, object] = {
        "thread_id": str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"court-rc4-worktree:{authority}:{index}",
            )
        ),
        "canonical_worktree_id": f"{repo_id}:{worktree_token}",
        "canonical_worktree_path": str(top),
        "repo_id": repo_id,
        "common_dir_fingerprint": hashlib.sha256(
            portable_host_path_key(common_dir).encode("utf-8")
        ).hexdigest(),
        "branch": run_git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD"),
        "start_head": run_git(worktree, "rev-parse", "HEAD").lower(),
    }
    recompute_worktree_fingerprint(proof)
    return proof


def check_unified_office_instance_lifecycle() -> None:
    task_id = "office-instance-isomorphic"
    create_task(task_id)
    decree = open_decree(task_id)
    fixture_root = court_runtime.runtime_root()
    cases = (
        ("child_agent", "gongbu-child-01", {"agent_id": "gongbu-child-01"}),
        ("child_agent", "gongbu-child-02", {"agent_id": "gongbu-child-02"}),
        ("worktree_thread", "gongbu-worktree-01", worktree_proof(fixture_root, 1)),
        ("worktree_thread", "gongbu-worktree-02", worktree_proof(fixture_root, 2)),
    )
    close_receipts: list[dict[str, object]] = []
    context_hash_fields = {
        "dispatch_context_packet_sha256",
        "semantic_receipt_sha256",
        "context_economy_receipt_sha256",
        "context_budget_pool_sha256",
    }
    hierarchy_fields = {
        "hierarchy_gate",
        "hierarchy_schema",
        "hierarchy_manifest_sha256",
        "hierarchy_edge_class",
        "hierarchy_calling_office",
        "hierarchy_target_role",
        "hierarchy_owner_role",
    }
    for index, (kind, instance_id, carrier_proof) in enumerate(cases, start=1):
        wave_id = f"office-instance-wave-{index:02d}"
        task_name = f"gongbu_rc4_{index:02d}"
        admission = admit(
            task_id,
            wave_id,
            office_api=True,
            office_instance_kind=kind,
            office_instance_id=instance_id,
            collaboration_task_name=task_name,
            carrier_proof=carrier_proof,
        )
        assert admission["receipt"]["action"] == "admit"
        assert admission["receipt"]["office_instance_kind"] == kind
        assert context_hash_fields.issubset(admission["receipt"])
        assert hierarchy_fields.issubset(admission["receipt"])
        internal_id = str(carrier_proof.get("agent_id") or instance_id)
        start = start_args(
            admission,
            task_id,
            wave_id,
            internal_id,
            instance_id=instance_id,
            collaboration_task_name=task_name,
            office_instance_kind=kind,
            office_instance_id=instance_id,
            carrier_proof=carrier_proof,
        )
        started = court_runtime.office_start(start)
        assert started["receipt"]["action"] == "start"
        assert context_hash_fields.issubset(started["office_instance"])
        assert context_hash_fields.issubset(started["event"])

        ack = ack_args(task_id, internal_id)
        ack.office_instance_kind = kind
        ack.office_instance_id = instance_id
        ack.carrier_proof = carrier_proof
        acknowledged = court_runtime.office_preload_ack(ack)
        assert acknowledged["receipt"]["action"] == "preload_ack"

        report = event_args(task_id, internal_id)
        report.office_instance_kind = kind
        report.office_instance_id = instance_id
        report.carrier_proof = carrier_proof
        reported = court_runtime.office_report(report)
        assert reported["receipt"]["action"] == "report"
        assert context_hash_fields.issubset(reported["event"])

        finish = finish_args(task_id, internal_id)
        finish.office_instance_kind = kind
        finish.office_instance_id = instance_id
        finish.carrier_proof = carrier_proof
        finish.result_envelope["office_instance_kind"] = kind
        finish.result_envelope["carrier_proof"] = carrier_proof
        finished = court_runtime.office_finish(finish)
        assert finished["receipt"]["action"] == "finish"

        close = event_args(task_id, internal_id)
        close.office_instance_kind = kind
        close.office_instance_id = instance_id
        close.carrier_proof = carrier_proof
        closed = court_runtime.office_close(close)
        close_receipts.append(closed["receipt"])

    assert all(set(receipt) == set(close_receipts[0]) for receipt in close_receipts)
    assert [receipt["child_no"] for receipt in close_receipts] == [1, 2, 3, 4]
    assert all(receipt["main_court_code"] == decree["main_court_code"] for receipt in close_receipts)
    assert all(receipt["parent_court_code"] == decree["main_court_code"] for receipt in close_receipts)
    assert len({receipt["lineage_key"] for receipt in close_receipts}) == 1
    assert len({receipt["metadata_record_pointer"] for receipt in close_receipts[2:]}) == 2
    assert all(set(receipt["carrier_proof"]) == {"agent_id"} for receipt in close_receipts[:2])
    worktree_fields = {
        "thread_id",
        "canonical_worktree_id",
        "canonical_worktree_path",
        "repo_id",
        "common_dir_fingerprint",
        "worktree_fingerprint",
        "branch",
        "start_head",
    }
    assert all(set(receipt["carrier_proof"]) == worktree_fields for receipt in close_receipts[2:])
    task = court_runtime.load_tasks()[task_id]
    assert len(task["agents"]) == 4
    assert "office_instances" not in task


def check_office_instance_proof_writer_and_attempt_guards() -> None:
    assert all(
        command and command[0] in {"rev-parse", "symbolic-ref"}
        for command in court_runtime.WORKTREE_GIT_READ_ONLY_COMMANDS
    )
    root = court_runtime.runtime_root()
    tofu_task = "office-instance-proof-no-tofu"
    create_task(tofu_task)
    open_decree(tofu_task)
    forged_first_proof = worktree_proof(root, 10)
    forged_first_proof["repo_id"] = "self-asserted-repository"
    recompute_worktree_fingerprint(forged_first_proof)
    reject_runtime_bytes_unchanged(
        lambda: admit(
            tofu_task,
            "proof-forged-first-wave",
            office_api=True,
            office_instance_kind="worktree_thread",
            office_instance_id="gongbu-worktree-10",
            collaboration_task_name="gongbu_proof_10",
            carrier_proof=forged_first_proof,
        ),
        "first self-asserted worktree proof became authority",
        "worktree_repo_id_mismatch",
    )

    proof_task = "office-instance-proof-guards"
    create_task(proof_task)
    open_decree(proof_task)
    invalid_fingerprint = worktree_proof(root, 11)
    invalid_fingerprint["worktree_fingerprint"] = "0" * 64
    reject_runtime_bytes_unchanged(
        lambda: admit(
            proof_task,
            "proof-invalid-wave",
            office_api=True,
            office_instance_kind="worktree_thread",
            office_instance_id="gongbu-worktree-11",
            collaboration_task_name="gongbu_proof_11",
            carrier_proof=invalid_fingerprint,
        ),
        "invalid worktree fingerprint was admitted",
        "worktree_fingerprint_mismatch",
    )
    canonical_proof = worktree_proof(root, 12)
    admit(
        proof_task,
        "proof-canonical-wave",
        office_api=True,
        office_instance_kind="worktree_thread",
        office_instance_id="gongbu-worktree-12",
        collaboration_task_name="gongbu_proof_12",
        carrier_proof=canonical_proof,
    )
    tampered_proofs: list[tuple[str, dict[str, object], str]] = []
    for label, field, value, reason in (
        (
            "canonical-id",
            "canonical_worktree_id",
            "court-capability-router:forged",
            "worktree_id_mismatch",
        ),
        (
            "branch",
            "branch",
            "codex/forged-branch",
            "worktree_branch_mismatch",
        ),
        (
            "head",
            "start_head",
            "0" * 40,
            "worktree_start_head_mismatch",
        ),
    ):
        tampered = dict(canonical_proof)
        tampered[field] = value
        recompute_worktree_fingerprint(tampered)
        tampered_proofs.append((label, tampered, reason))
    non_git_path = (root / "not-a-git-worktree").resolve()
    non_git_path.mkdir(parents=True, exist_ok=True)
    non_git = dict(canonical_proof)
    non_git["canonical_worktree_path"] = str(non_git_path)
    recompute_worktree_fingerprint(non_git)
    tampered_proofs.append(("non-git-path", non_git, "worktree_git_proof_failed"))
    for offset, (label, proof, reason) in enumerate(tampered_proofs, start=30):
        reject_runtime_bytes_unchanged(
            lambda proof=proof, offset=offset, label=label: admit(
                proof_task,
                f"proof-{label}-wave",
                office_api=True,
                office_instance_kind="worktree_thread",
                office_instance_id=f"gongbu-worktree-{offset}",
                collaboration_task_name=f"gongbu_proof_{offset}",
                carrier_proof=proof,
                office_write_set=[f"fixtures/proof-{label}.txt"],
            ),
            f"tampered {label} worktree proof was admitted",
            reason,
        )

    wrong_common_dir = worktree_proof(root, 13, authority="secondary")
    reject_runtime_bytes_unchanged(
        lambda: admit(
            proof_task,
            "proof-common-dir-wave",
            office_api=True,
            office_instance_kind="worktree_thread",
            office_instance_id="gongbu-worktree-13",
            collaboration_task_name="gongbu_proof_13",
            carrier_proof=wrong_common_dir,
        ),
        "different actual repository common-dir was admitted",
        "office_common_dir_fingerprint_mismatch",
    )

    writer_task = "office-instance-writer-guards"
    create_task(writer_task)
    open_decree(writer_task)
    first_proof = {"agent_id": "gongbu-writer-01"}
    first = admit(
        writer_task,
        "writer-wave-01",
        office_api=True,
        office_instance_kind="child_agent",
        office_instance_id="gongbu-writer-01",
        collaboration_task_name="gongbu_writer_01",
        carrier_proof=first_proof,
        office_write_set=["Fixture-Writes\\Writer\\Shared"],
    )
    court_runtime.office_start(
        start_args(
            first,
            writer_task,
            "writer-wave-01",
            "gongbu-writer-01",
            instance_id="gongbu-writer-01",
            collaboration_task_name="gongbu_writer_01",
            office_instance_kind="child_agent",
            office_instance_id="gongbu-writer-01",
            carrier_proof=first_proof,
        )
    )
    persisted_first = court_runtime.load_tasks()[writer_task]["agents"]["gongbu-writer-01"]
    assert persisted_first["write_set"] == ["fixture-writes/writer/shared"]
    assert persisted_first["read_scope"] == ["fixture-writes/writer/shared"]
    reject_runtime_bytes_unchanged(
        lambda: admit(
            writer_task,
            "writer-wave-02",
            office_api=True,
            office_instance_kind="child_agent",
            office_instance_id="gongbu-writer-02",
            collaboration_task_name="gongbu_writer_02",
            carrier_proof={"agent_id": "gongbu-writer-02"},
            office_write_set=["fixture-writes/writer/shared/child.py"],
        ),
        "descendant active writer was admitted",
        "office_writer_conflict",
    )
    reject_runtime_bytes_unchanged(
        lambda: admit(
            writer_task,
            "writer-wave-ancestor",
            office_api=True,
            office_instance_kind="child_agent",
            office_instance_id="gongbu-writer-04",
            collaboration_task_name="gongbu_writer_04",
            carrier_proof={"agent_id": "gongbu-writer-04"},
            office_write_set=["FIXTURE-WRITES\\WRITER"],
        ),
        "ancestor active writer was admitted",
        "office_writer_conflict",
    )
    reject_runtime_bytes_unchanged(
        lambda: admit(
            writer_task,
            "writer-instance-replay",
            office_api=True,
            office_instance_kind="child_agent",
            office_instance_id="gongbu-writer-01",
            collaboration_task_name="gongbu_writer_01",
            carrier_proof=first_proof,
            office_write_set=["fixture-writes/independent-writer.py"],
        ),
        "duplicate office instance was admitted",
        "office_instance_already_admitted",
    )

    first_attempt = int(first["attempt"])
    set_task_field(
        writer_task,
        lambda task: task.__setitem__("next_semantic_dispatch_attempt", first_attempt),
    )
    reject_runtime_bytes_unchanged(
        lambda: admit(
            writer_task,
            "writer-attempt-replay",
            office_api=True,
            office_instance_kind="child_agent",
            office_instance_id="gongbu-writer-03",
            collaboration_task_name="gongbu_writer_03",
            carrier_proof={"agent_id": "gongbu-writer-03"},
            office_write_set=["fixture-writes/independent-attempt.py"],
        ),
        "duplicate semantic dispatch attempt was admitted",
        "semantic_dispatch_attempt_conflict",
    )


def check_office_instance_semantic_and_result_binding() -> None:
    task_id = "office-instance-result-binding"
    create_task(task_id)
    open_decree(task_id)
    other_task = "office-instance-wrong-task"
    create_task(other_task)
    open_decree(other_task)
    proof = worktree_proof(court_runtime.runtime_root(), 21)
    instance_id = "gongbu-worktree-21"
    wave_id = "office-result-wave"
    task_name = "gongbu_result_21"
    admission = admit(
        task_id,
        wave_id,
        office_api=True,
        office_instance_kind="worktree_thread",
        office_instance_id=instance_id,
        collaboration_task_name=task_name,
        carrier_proof=proof,
    )

    reject_runtime_bytes_unchanged(
        lambda: court_runtime.office_start(
            start_args(
                admission,
                other_task,
                wave_id,
                instance_id,
                instance_id=instance_id,
                collaboration_task_name=task_name,
                office_instance_kind="worktree_thread",
                office_instance_id=instance_id,
                carrier_proof=proof,
            )
        ),
        "cross-task office start was accepted",
        "agent start admission not found",
    )
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.office_start(
            start_args(
                admission,
                task_id,
                wave_id,
                instance_id,
                instance_id=instance_id,
                collaboration_task_name=task_name,
                office_instance_kind="worktree_thread",
                office_instance_id=instance_id,
                carrier_proof=proof,
                semantic_epoch=int(admission["semantic_epoch"]) + 1,
            )
        ),
        "wrong semantic epoch office start was accepted",
        "agent_semantic_binding_mismatch:semantic_epoch",
    )
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.office_start(
            start_args(
                admission,
                task_id,
                wave_id,
                instance_id,
                instance_id=instance_id,
                collaboration_task_name=task_name,
                office_instance_kind="worktree_thread",
                office_instance_id=instance_id,
                carrier_proof=proof,
                dispatch_uid="DSP-WRONG",
            )
        ),
        "wrong dispatch uid office start was accepted",
        "agent_semantic_binding_mismatch:dispatch_uid",
    )

    court_runtime.office_start(
        start_args(
            admission,
            task_id,
            wave_id,
            instance_id,
            instance_id=instance_id,
            collaboration_task_name=task_name,
            office_instance_kind="worktree_thread",
            office_instance_id=instance_id,
            carrier_proof=proof,
        )
    )
    ack = ack_args(task_id, instance_id)
    ack.office_instance_kind = "worktree_thread"
    ack.office_instance_id = instance_id
    ack.carrier_proof = proof
    court_runtime.office_preload_ack(ack)

    stale = finish_args(task_id, instance_id)
    stale.office_instance_kind = "worktree_thread"
    stale.office_instance_id = instance_id
    stale.carrier_proof = proof
    stale.result_envelope.pop("agent_id")
    stale.result_envelope.pop("worktree")
    stale.result_envelope["office_instance_kind"] = "worktree_thread"
    stale.result_envelope["carrier_proof"] = proof
    stale.result_envelope["attempt"] = int(stale.result_envelope["attempt"]) + 1
    quarantined = court_runtime.office_finish(stale)
    assert quarantined["event"]["action"] == "agent_result_quarantine"
    assert quarantined["receipt"]["status"] == "running"
    persisted = court_runtime.load_tasks()[task_id]["agents"][instance_id]
    assert persisted["status"] == "running"
    assert "result_envelope" not in persisted
    assert court_runtime.load_tasks()[task_id]["quarantined_results"][-1]["status"] == "QUARANTINED"

    finish = finish_args(task_id, instance_id)
    finish.office_instance_kind = "worktree_thread"
    finish.office_instance_id = instance_id
    finish.carrier_proof = proof
    finish.result_envelope.pop("agent_id")
    finish.result_envelope.pop("worktree")
    finish.result_envelope["office_instance_kind"] = "worktree_thread"
    finish.result_envelope["carrier_proof"] = proof
    completed = court_runtime.office_finish(finish)
    assert completed["receipt"]["status"] == "completed"
    assert completed["office_instance"]["result_envelope"]["carrier_proof"] == proof
    close = event_args(task_id, instance_id)
    close.office_instance_kind = "worktree_thread"
    close.office_instance_id = instance_id
    close.carrier_proof = proof
    court_runtime.office_close(close)


def check_office_task_name_and_readiness_binding() -> None:
    task_id = "office-task-name-binding"
    create_task(task_id)
    open_decree(task_id)
    reject_runtime_bytes_unchanged(
        lambda: admit(
            task_id,
            "generic-instance-wave",
            office_api=True,
            office_instance_kind="child_agent",
            office_instance_id="worker-01",
            collaboration_task_name="gongbu_generic_01",
            carrier_proof={"agent_id": "gongbu-generic-01"},
        ),
        "generic office instance id was admitted",
        "office_instance_id_not_role_prefixed",
    )
    reject_runtime_bytes_unchanged(
        lambda: admit(
            task_id,
            "generic-task-name-wave",
            office_api=True,
            office_instance_kind="child_agent",
            office_instance_id="gongbu-generic-02",
            collaboration_task_name="worker_generic_02",
            carrier_proof={"agent_id": "gongbu-generic-02"},
        ),
        "generic collaboration task_name was admitted",
        "office_task_name_mismatch",
    )

    proof_one = {"agent_id": "gongbu-address-01"}
    first = admit(
        task_id,
        "address-wave-01",
        office_api=True,
        office_instance_kind="child_agent",
        office_instance_id="gongbu-address-01",
        collaboration_task_name="gongbu_shared_address",
        carrier_proof=proof_one,
    )
    first_start = start_args(
        first,
        task_id,
        "address-wave-01",
        "gongbu-address-01",
        instance_id="gongbu-address-01",
        collaboration_task_name="gongbu_shared_address",
        office_instance_kind="child_agent",
        office_instance_id="gongbu-address-01",
        carrier_proof=proof_one,
        sidebar_title="MenXia misleading title",
        thread_title="generic helper",
    )
    started = court_runtime.office_start(first_start)
    assert started["office_instance"]["role"] == "gongbu"
    assert started["office_instance"]["collaboration_task_name"] == "gongbu_shared_address"
    assert started["office_instance"]["office_execution_ready"] is False
    ack = ack_args(task_id, "gongbu-address-01")
    ack.office_instance_kind = "child_agent"
    ack.office_instance_id = "gongbu-address-01"
    ack.carrier_proof = proof_one
    acknowledged = court_runtime.office_preload_ack(ack)
    assert acknowledged["office_instance"]["office_execution_ready"] is True

    proof_two = {"agent_id": "gongbu-address-02"}
    second = admit(
        task_id,
        "address-wave-02",
        office_api=True,
        office_instance_kind="child_agent",
        office_instance_id="gongbu-address-02",
        collaboration_task_name="gongbu_shared_address",
        carrier_proof=proof_two,
    )
    court_runtime.office_start(
        start_args(
            second,
            task_id,
            "address-wave-02",
            "gongbu-address-02",
            instance_id="gongbu-address-02",
            collaboration_task_name="gongbu_shared_address",
            office_instance_kind="child_agent",
            office_instance_id="gongbu-address-02",
            carrier_proof=proof_two,
        )
    )

    fixed = admit(
        task_id,
        "address-fixed-wave",
        office_api=True,
        office_instance_kind="child_agent",
        office_instance_id="gongbu-address-03",
        collaboration_task_name="gongbu_fixed_address",
        carrier_proof={"agent_id": "gongbu-address-03"},
    )
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.office_start(
            start_args(
                fixed,
                task_id,
                "address-fixed-wave",
                "gongbu-address-03",
                instance_id="gongbu-address-03",
                collaboration_task_name="gongbu_changed_address",
                office_instance_kind="child_agent",
                office_instance_id="gongbu-address-03",
                carrier_proof={"agent_id": "gongbu-address-03"},
            )
        ),
        "first-spawn collaboration task_name was changed",
        "office_task_name_mismatch",
    )

    libu_proof = {"agent_id": "libu-address-01"}
    libu = admit(
        task_id,
        "cross-role-libu-wave",
        role="libu",
        office_api=True,
        office_instance_kind="child_agent",
        office_instance_id="libu-address-01",
        collaboration_task_name="libu_hr_shared_address",
        carrier_proof=libu_proof,
    )
    court_runtime.office_start(
        start_args(
            libu,
            task_id,
            "cross-role-libu-wave",
            "libu-address-01",
            role="libu",
            instance_id="libu-address-01",
            collaboration_task_name="libu_hr_shared_address",
            office_instance_kind="child_agent",
            office_instance_id="libu-address-01",
            carrier_proof=libu_proof,
        )
    )
    libu_hr_proof = {"agent_id": "libu-hr-address-01"}
    libu_hr = admit(
        task_id,
        "cross-role-libu-hr-wave",
        role="libu-hr",
        office_api=True,
        office_instance_kind="child_agent",
        office_instance_id="libu-hr-address-01",
        collaboration_task_name="libu_hr_shared_address",
        carrier_proof=libu_hr_proof,
    )
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.office_start(
            start_args(
                libu_hr,
                task_id,
                "cross-role-libu-hr-wave",
                "libu-hr-address-01",
                role="libu-hr",
                instance_id="libu-hr-address-01",
                collaboration_task_name="libu_hr_shared_address",
                office_instance_kind="child_agent",
                office_instance_id="libu-hr-address-01",
                carrier_proof=libu_hr_proof,
            )
        ),
        "cross-role collaboration task_name reuse was accepted",
        "office_task_name_cross_role_reuse",
    )


def office_cli(command: str, request: Namespace) -> dict[str, object]:
    output = io.StringIO()
    with redirect_stdout(output):
        status = court_runtime.main(
            [
                "office",
                command,
                "--request-json",
                json.dumps(vars(request), ensure_ascii=False),
            ]
        )
    assert status == 0, output.getvalue()
    payload = json.loads(output.getvalue())
    assert payload["schema"] == "court.office.cli.v1"
    assert payload["ok"] is True
    assert payload["command"] == command
    return payload["result"]


def raw_office_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            status = court_runtime.main(argv)
        except SystemExit as exc:
            status = int(exc.code or 0)
    return status, stdout.getvalue(), stderr.getvalue()


def check_office_lifecycle_authority_guards() -> None:
    def launch(
        task_id: str,
        suffix: str,
        *,
        preload: bool,
    ) -> tuple[dict[str, object], str, dict[str, object], str]:
        create_task(task_id)
        open_decree(task_id)
        instance_id = f"gongbu-{suffix}"
        task_name = f"gongbu_{suffix.replace('-', '_')}"
        proof = {"agent_id": instance_id}
        wave_id = f"{suffix}-wave"
        admission = admit(
            task_id,
            wave_id,
            office_api=True,
            office_instance_kind="child_agent",
            office_instance_id=instance_id,
            collaboration_task_name=task_name,
            carrier_proof=proof,
        )
        court_runtime.office_start(
            start_args(
                admission,
                task_id,
                wave_id,
                instance_id,
                instance_id=instance_id,
                collaboration_task_name=task_name,
                office_instance_kind="child_agent",
                office_instance_id=instance_id,
                carrier_proof=proof,
            )
        )
        if preload:
            ack = ack_args(task_id, instance_id)
            ack.office_instance_kind = "child_agent"
            ack.office_instance_id = instance_id
            ack.carrier_proof = proof
            court_runtime.office_preload_ack(ack)
        return admission, instance_id, proof, wave_id

    start_task = "office-semantic-start-guard"
    create_task(start_task)
    open_decree(start_task)
    start_instance = "gongbu-semantic-start"
    start_task_name = "gongbu_semantic_start"
    start_proof = {"agent_id": start_instance}
    start_admission = admit(
        start_task,
        "semantic-start-wave",
        office_api=True,
        office_instance_kind="child_agent",
        office_instance_id=start_instance,
        collaboration_task_name=start_task_name,
        carrier_proof=start_proof,
    )
    set_task_field(
        start_task,
        lambda task: task.__setitem__("semantic_state", "QUARANTINED"),
    )
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.office_start(
            start_args(
                start_admission,
                start_task,
                "semantic-start-wave",
                start_instance,
                instance_id=start_instance,
                collaboration_task_name=start_task_name,
                office_instance_kind="child_agent",
                office_instance_id=start_instance,
                carrier_proof=start_proof,
            )
        ),
        "QUARANTINED task advanced office start",
        "semantic_mutation_not_dispatchable",
    )

    _, pending_instance, pending_proof, _ = launch(
        "office-preload-report-guard",
        "preload-report",
        preload=False,
    )
    pending_report = event_args("office-preload-report-guard", pending_instance)
    pending_report.office_instance_kind = "child_agent"
    pending_report.office_instance_id = pending_instance
    pending_report.carrier_proof = pending_proof
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.office_report(pending_report),
        "preload-pending office report mutated the runtime",
        "office_preload_not_passed",
    )

    _, guarded_instance, guarded_proof, _ = launch(
        "office-semantic-action-guard",
        "semantic-action",
        preload=True,
    )
    set_task_field(
        "office-semantic-action-guard",
        lambda task: task.__setitem__("semantic_state", "QUARANTINED"),
    )
    guarded_report = event_args("office-semantic-action-guard", guarded_instance)
    guarded_report.office_instance_kind = "child_agent"
    guarded_report.office_instance_id = guarded_instance
    guarded_report.carrier_proof = guarded_proof
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.office_report(guarded_report),
        "QUARANTINED task accepted an office report",
        "semantic_mutation_not_dispatchable",
    )
    guarded_finish = finish_args("office-semantic-action-guard", guarded_instance)
    guarded_finish.office_instance_kind = "child_agent"
    guarded_finish.office_instance_id = guarded_instance
    guarded_finish.carrier_proof = guarded_proof
    guarded_finish.result_envelope["office_instance_kind"] = "child_agent"
    guarded_finish.result_envelope["carrier_proof"] = guarded_proof
    reject_runtime_bytes_unchanged(
        lambda: court_runtime.office_finish(guarded_finish),
        "QUARANTINED task accepted an office finish",
        "semantic_mutation_not_dispatchable",
    )

    _, close_instance, close_proof, _ = launch(
        "office-semantic-close-release",
        "semantic-close",
        preload=True,
    )
    close_finish = finish_args("office-semantic-close-release", close_instance)
    close_finish.office_instance_kind = "child_agent"
    close_finish.office_instance_id = close_instance
    close_finish.carrier_proof = close_proof
    close_finish.result_envelope["office_instance_kind"] = "child_agent"
    close_finish.result_envelope["carrier_proof"] = close_proof
    court_runtime.office_finish(close_finish)
    set_task_field(
        "office-semantic-close-release",
        lambda task: task.__setitem__("semantic_state", "QUARANTINED"),
    )
    close = event_args("office-semantic-close-release", close_instance)
    close.office_instance_kind = "child_agent"
    close.office_instance_id = close_instance
    close.carrier_proof = close_proof
    closed = court_runtime.office_close(close)
    assert closed["receipt"]["status"] == "closed"

    _, reconcile_instance, _, reconcile_wave = launch(
        "office-semantic-reconcile-release",
        "semantic-reconcile",
        preload=True,
    )
    set_task_field(
        "office-semantic-reconcile-release",
        lambda task: task.__setitem__("semantic_state", "QUARANTINED"),
    )
    reconciled = court_runtime.agent_reconcile(
        Namespace(
            task_id="office-semantic-reconcile-release",
            agent_id=reconcile_instance,
            role="gongbu",
            error_kind="fatal-auth",
            result="synthetic terminal reconciliation",
            wave_id=reconcile_wave,
            actor="shangshu",
            evidence="synthetic release reconciliation",
            note="release-only contract",
        )
    )
    assert reconciled["agent"]["release_status"] == "closed"


def check_same_second_office_report_event_ids_are_unique() -> None:
    task_id = "office-report-event-id-uniqueness"
    create_task(task_id)
    open_decree(task_id)
    instance_id = "gongbu-event-id"
    task_name = "gongbu_event_id"
    proof = {"agent_id": instance_id}
    admission = admit(
        task_id,
        "event-id-wave",
        office_api=True,
        office_instance_kind="child_agent",
        office_instance_id=instance_id,
        collaboration_task_name=task_name,
        carrier_proof=proof,
    )
    court_runtime.office_start(
        start_args(
            admission,
            task_id,
            "event-id-wave",
            instance_id,
            instance_id=instance_id,
            collaboration_task_name=task_name,
            office_instance_kind="child_agent",
            office_instance_id=instance_id,
            carrier_proof=proof,
        )
    )
    ack = ack_args(task_id, instance_id)
    ack.office_instance_kind = "child_agent"
    ack.office_instance_id = instance_id
    ack.carrier_proof = proof
    court_runtime.office_preload_ack(ack)
    fixed_now = "2026-07-16T12:34:56+08:00"
    original_now_text = court_runtime.now_text
    court_runtime.now_text = lambda: fixed_now  # type: ignore[assignment]
    try:
        receipts: list[dict[str, object]] = []
        for _ in range(2):
            report = event_args(task_id, instance_id)
            report.office_instance_kind = "child_agent"
            report.office_instance_id = instance_id
            report.carrier_proof = proof
            receipts.append(court_runtime.office_report(report)["receipt"])
    finally:
        court_runtime.now_text = original_now_text  # type: ignore[assignment]
    event_ids = [str(receipt["event_id"]) for receipt in receipts]
    assert len(set(event_ids)) == 2, event_ids


def check_office_cli_error_contract() -> None:
    cases = (
        (
            ["office", "admit", "--request-json", "{"],
            "office_cli_invalid_json",
        ),
        (["office", "admit"], "office_cli_missing_arguments"),
        (["office", "unknown"], "office_cli_unknown_subcommand"),
        (
            ["office", "report", "--request-json", "{}"],
            "office_business_error",
        ),
    )
    for argv, expected_error_code in cases:
        status, stdout, stderr = raw_office_cli(argv)
        assert status == 2, (argv, status, stdout, stderr)
        assert stdout.strip(), (argv, "missing JSON error payload", stderr)
        payload = json.loads(stdout)
        assert payload["schema"] == "court.office.cli.v1"
        assert payload["ok"] is False
        assert payload["fail_closed"] is True
        assert payload["error_code"] == expected_error_code, payload
        assert "usage:" not in stderr.lower(), (argv, stderr)


def check_office_lifecycle_json_cli() -> None:
    task_id = "office-json-cli"
    create_task(task_id)
    open_decree(task_id)
    instance_id = "gongbu-cli-01"
    task_name = "gongbu_cli_01"
    proof = {"agent_id": instance_id}
    admission_request = admit(
        task_id,
        "office-cli-wave",
        office_api=True,
        return_namespace=True,
        office_instance_kind="child_agent",
        office_instance_id=instance_id,
        collaboration_task_name=task_name,
        carrier_proof=proof,
    )
    admission = office_cli("admit", admission_request)  # type: ignore[arg-type]
    assert admission["receipt"]["action"] == "admit"

    start = start_args(
        admission,
        task_id,
        "office-cli-wave",
        instance_id,
        instance_id=instance_id,
        collaboration_task_name=task_name,
        office_instance_kind="child_agent",
        office_instance_id=instance_id,
        carrier_proof=proof,
    )
    assert office_cli("start", start)["receipt"]["action"] == "start"

    ack = ack_args(task_id, instance_id)
    ack.office_instance_kind = "child_agent"
    ack.office_instance_id = instance_id
    ack.carrier_proof = proof
    assert office_cli("preload-ack", ack)["receipt"]["action"] == "preload_ack"

    report = event_args(task_id, instance_id)
    report.office_instance_kind = "child_agent"
    report.office_instance_id = instance_id
    report.carrier_proof = proof
    assert office_cli("report", report)["receipt"]["action"] == "report"

    finish = finish_args(task_id, instance_id)
    finish.office_instance_kind = "child_agent"
    finish.office_instance_id = instance_id
    finish.carrier_proof = proof
    finish.result_envelope["office_instance_kind"] = "child_agent"
    finish.result_envelope["carrier_proof"] = proof
    assert office_cli("finish", finish)["receipt"]["action"] == "finish"

    close = event_args(task_id, instance_id)
    close.office_instance_kind = "child_agent"
    close.office_instance_id = instance_id
    close.carrier_proof = proof
    assert office_cli("close", close)["receipt"]["action"] == "close"
    supported = court_runtime.probe_payload()["supported_commands"]
    assert "office admit|start|preload-ack|report|finish|close" in supported
    assert all(
        alias in supported
        for alias in (
            "agent-admit",
            "agent-start",
            "agent-preload-ack",
            "agent-report",
            "agent-finish",
            "agent-close",
        )
    )


def run_agent_lifecycle_checks() -> None:
    global TASK_SPECIFIC_SKILL_PATH
    check_import_root_isolation()
    # The pure binding gate must pass before lifecycle persistence checks can run.
    run_office_assignment_binding_checks()
    with tempfile.TemporaryDirectory() as temp_dir:
        fixture_root = Path(temp_dir)
        task_skill = fixture_root / "skills" / "task-specific-lifecycle" / "SKILL.md"
        task_skill.parent.mkdir(parents=True)
        task_skill.write_text("# lifecycle task-specific fixture\n", encoding="utf-8")
        TASK_SPECIFIC_SKILL_PATH = task_skill
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: fixture_root / "runtime"  # type: ignore[assignment]
        try:
            check_office_name_identity_binding()
            check_assignment_binding_toctou_rejected()
            check_dispatch_hierarchy_revalidated_before_start_write()
            check_three_department_hierarchy_revalidated_before_start_write()
            check_dispatch_hierarchy_receipt_tamper_rejected_before_start_write()
            check_admission_binding()
            check_runtime_generates_bounded_child_profile()
            check_caller_child_binding_digest_rejected_before_admission_write()
            check_child_profile_tamper_rejected_before_start_write()
            check_budget_lease_access_contract_allows_approved_subset()
            check_child_access_contract_tamper_rejected_before_start_write()
            check_dispatch_context_economy_contract()
            check_terminal_and_identity()
            check_unified_office_instance_lifecycle()
            check_office_instance_proof_writer_and_attempt_guards()
            check_office_instance_semantic_and_result_binding()
            check_office_task_name_and_readiness_binding()
            check_office_lifecycle_authority_guards()
            check_same_second_office_report_event_ids_are_unique()
            check_office_lifecycle_json_cli()
            check_office_cli_error_contract()
            check_malformed_sibling_blocks_lifecycle_write()
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]
            TASK_SPECIFIC_SKILL_PATH = None


def main() -> int:
    run_agent_lifecycle_checks()
    print("COURT_AGENT_LIFECYCLE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
