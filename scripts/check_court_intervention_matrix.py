"""Integration-test court intervention and agent lifecycle commands."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True

import tempfile
from datetime import datetime, timedelta, timezone

from court_complexity_budget import normalize_budget_pool
from court_office_bootstrap import build_preload_manifest


TASK_BINDINGS: dict[str, dict[str, object]] = {}
CONTEXT_HARD_LIMITS = {
    "ram_percent_max": 99.0,
    "memory_mb_max": 2_048,
    "context_tokens_max": 100_000,
    "message_chars_max": 12_000,
    "tool_calls_max": 8,
    "time_seconds_max": 600.0,
    "retained_agents_max": 15,
}


def run_cli(script: Path, env: dict[str, str], *args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([sys.executable, str(script), *args], text=True, capture_output=True, env=env, check=False)
    if result.returncode != expect:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise AssertionError(f"command {args} returned {result.returncode}, expected {expect}")
    return result


def json_cli(script: Path, env: dict[str, str], *args: str) -> dict[str, object]:
    return json.loads(run_cli(script, env, "--format", "json", *args).stdout)


def create_formal_task(
    cli: Path,
    env: dict[str, str],
    intake_file: Path,
    *args: str,
) -> dict[str, object]:
    values = list(args)
    task_id = values[values.index("--task-id") + 1]
    charter = values[values.index("--charter") + 1] if "--charter" in values else ""
    charter_sha256 = hashlib.sha256(charter.encode("utf-8")).hexdigest()
    capsule_file = intake_file.parent / f"{task_id}-invariant-capsule.json"
    capsule_file.write_text(
        json.dumps(
            {
                "schema": "court.semantic.invariant_capsule.v1",
                "latest_decree_anchor": charter,
                "latest_decree_sha256": charter_sha256,
                "non_goals": ["do not mutate real runtime state"],
                "boundaries": ["TemporaryDirectory fixture only"],
                "allowed_actions": ["synthetic intervention verification"],
                "forbidden_actions": ["real Shiguan access"],
                "acceptance": ["intervention matrix passes"],
                "evidence_requirements": ["machine-readable receipt"],
                "stop_gates": ["semantic drift"],
                "write_set": ["scripts/check_court_intervention_matrix.py"],
                "governing_hashes": {"fixture": charter_sha256},
                "charter_sha256": charter_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    run_cli(
        cli,
        env,
        "create",
        *args,
        "--work-kind",
        "audit",
        "--intake-file",
        str(intake_file),
        "--invariant-capsule-file",
        str(capsule_file),
    )
    context_file = intake_file.parent / f"{task_id}-semantic-context.json"
    context_file.write_text(
        json.dumps(
            {
                "authority_revision": 3,
                "authority_sha256": hashlib.sha256(b"authority-v3").hexdigest(),
                "plan_revision": 7,
                "plan_sha256": hashlib.sha256(b"plan-v7").hexdigest(),
                "plan_cursor": "phase1/rc2/intervention-matrix",
                "git_fingerprint": hashlib.sha256(b"intervention-git-fixture").hexdigest(),
                "recovery_checkpoint_id": "intervention-recovery-fixture",
                "shiguan_revision": 0,
                "shiguan_fingerprint": hashlib.sha256(b"synthetic-shiguan-none").hexdigest(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for command in ("checkpoint", "verify"):
        payload = json_cli(
            cli,
            env,
            "semantic",
            command,
            "--task-id",
            task_id,
            "--context-file",
            str(context_file),
            "--trigger",
            command,
            "--actor",
            "taizi",
            "--evidence",
            f"intervention matrix semantic {command}",
        )
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("task"), dict):
        raise AssertionError("semantic verification did not return a task")
    task = result["task"]
    TASK_BINDINGS[task_id] = task
    return task


def task_semantic_args(task_id: str) -> list[str]:
    task = TASK_BINDINGS[task_id]
    receipt = task.get("semantic_receipt")
    if not isinstance(receipt, dict):
        raise AssertionError(f"semantic receipt missing for {task_id}")
    return [
        "--expected-semantic-epoch",
        str(task["semantic_epoch"]),
        "--expected-charter-sha256",
        str(task["charter_sha256"]),
        "--expected-invariant-capsule-sha256",
        str(task["invariant_capsule_sha256"]),
        "--expected-checkpoint-id",
        str(receipt["checkpoint_id"]),
    ]


def dispatch_context_packet(task_id: str, wave_id: str) -> dict[str, object]:
    task = TASK_BINDINGS[task_id]
    receipt = task.get("semantic_receipt")
    if not isinstance(receipt, dict):
        raise AssertionError(f"semantic receipt missing for {task_id}")
    return {
        "schema": "court.semantic.dispatch_context_packet.v1",
        "task_id": task_id,
        "sub_id": wave_id,
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
            {"path": "authority/current.md", "sha256": receipt["authority_sha256"]},
            {"path": "plans/current.md", "sha256": receipt["plan_sha256"]},
        ],
        "summary": {
            "text": "bounded intervention dispatch packet",
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
        phase="P00-INTERVENTION",
        wave_id=wave_id,
        approved_by="taizi",
        approved_at="2026-07-16T00:00:00+00:00",
        expected_output="bounded intervention receipt",
        return_conditions=("COMPLETED", "FAILED_CLOSED", "CANCELLED"),
    )


def context_economy_args(task_id: str, wave_id: str) -> list[str]:
    return [
        "--dispatch-context-packet-json",
        json.dumps(dispatch_context_packet(task_id, wave_id), ensure_ascii=False),
        "--context-budget-pool-json",
        json.dumps(context_budget_pool(task_id, wave_id), ensure_ascii=False),
        "--context-result-mode",
        "bounded_structured_receipt",
        "--context-tool-output-mode",
        "pointer",
    ]


def role_budget_args(
    task_id: str,
    requested_roles: str,
    *,
    next_depth: int = 1,
) -> list[str]:
    roles = [item.strip() for item in requested_roles.split(",") if item.strip()]
    if not roles:
        return []
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
    pure_child_owner = (
        roles[0]
        if len(roles) > 1 and len(set(roles)) == 1 and roles[0] in ministry_roles
        else None
    )
    caller_role = pure_child_owner or (
        "shangshu" if any(role in ministry_roles for role in roles) else "taizi"
    )
    caller_direct_superior = direct_superiors[caller_role]
    counts: dict[str, int] = {}
    bindings: list[dict[str, object]] = []
    for role in roles:
        counts[role] = counts.get(role, 0) + 1
        number = counts[role]
        instance_id = f"{role}#{number:04d}"
        worker = pure_child_owner == role or (number > 1 and role in ministry_roles)
        preload = build_preload_manifest(role)
        bindings.append(
            {
                "role": role,
                "instance_id": instance_id,
                "shard_id": f"{role}-shard-{number:04d}",
                "direct_superior": role if worker else direct_superiors.get(role, "shangshu"),
                "instance_kind": "office_worker_instance" if worker else "office",
                "canonical_authority": not worker,
                "owner_role": role if worker else None,
                "write_set": [f"work/{role}/{number:04d}.txt"] if worker else [],
                "access_mode": "read_write" if worker else "read_only",
                "read_scope": [f"work/{role}/{number:04d}.txt"],
                "mutation_allowed": worker,
                "integration_authority": False,
                "preload_hashes": {
                    "profile_hash": preload.profile_hash,
                    "dossier_hash": preload.dossier_hash,
                    "court_skill_hash": preload.court_skill_hash,
                },
            }
        )
    budget_id = f"budget:{task_id}:phase:wave"
    lease = {
        "schema": "court.agent.admission_lease.v2",
        "budget_id": budget_id,
        "status": "ACTIVE",
        "lease_id": f"{task_id}-lease-{len(bindings)}",
        "parent_budget_id": f"{budget_id}:{caller_direct_superior}",
        "parent_id": caller_direct_superior,
        "approved_by": caller_direct_superior,
        "grantee_role": caller_role,
        "lease_depth": max(0, next_depth - 1),
        "approved_next_depth": next_depth,
        "expires_at_utc": "2099-01-01T00:00:00+00:00",
        "parent_write_scope": ["work"],
        "approved_count": len(bindings),
        "task_id": task_id,
        "calling_office": caller_role,
        "direct_superior": caller_direct_superior,
        "integration_domain": "intervention-matrix",
        "authority": "super",
        "approved_roles": [binding["role"] for binding in bindings],
        "approved_instance_ids": [binding["instance_id"] for binding in bindings],
        "approved_shards": [binding["shard_id"] for binding in bindings],
        "approved_write_sets": {
            str(binding["instance_id"]): list(binding["write_set"]) for binding in bindings
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
    return [
        "--budget-lease-json",
        json.dumps(lease, ensure_ascii=False),
        "--requested-bindings-json",
        json.dumps(bindings, ensure_ascii=False),
        "--integration-domain",
        "intervention-matrix",
        "--authority",
        "super",
        "--calling-office",
        caller_role,
        "--direct-superior",
        caller_direct_superior,
    ]


def agent_semantic_args(env: dict[str, str], task_id: str, agent_id: str) -> list[str]:
    tasks = json.loads((Path(env["COURT_RUNTIME_ROOT"]) / "tasks.json").read_text(encoding="utf-8"))
    agent = tasks[task_id]["agents"][agent_id]
    return [
        "--semantic-epoch",
        str(agent["semantic_epoch"]),
        "--charter-sha256",
        str(agent["charter_sha256"]),
        "--invariant-capsule-sha256",
        str(agent["invariant_capsule_sha256"]),
        "--checkpoint-id",
        str(agent["checkpoint_id"]),
        "--dispatch-uid",
        str(agent["dispatch_uid"]),
        "--attempt",
        str(agent["attempt"]),
    ]


def result_envelope_file(
    env: dict[str, str],
    task_id: str,
    agent_id: str,
    role: str,
    status: str,
) -> Path:
    runtime_root = Path(env["COURT_RUNTIME_ROOT"])
    tasks = json.loads((runtime_root / "tasks.json").read_text(encoding="utf-8"))
    agent = tasks[task_id]["agents"][agent_id]
    write_set_sha256 = hashlib.sha256(
        json.dumps(
            agent.get("write_set"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    envelope = {
        "schema": "court.office.result.v1",
        "task_id": task_id,
        "semantic_epoch": agent["semantic_epoch"],
        "charter_sha256": agent["charter_sha256"],
        "invariant_capsule_sha256": agent["invariant_capsule_sha256"],
        "checkpoint_id": agent["checkpoint_id"],
        "dispatch_uid": agent["dispatch_uid"],
        "attempt": agent["attempt"],
        "office_instance_id": agent["office_instance_id"],
        "agent_id": agent_id,
        "role": role,
        "direct_superior": agent["direct_superior"],
        "worktree": agent["worktree"],
        "write_set_sha256": write_set_sha256,
        "status": status,
        "summary": "bounded structured intervention result",
        "evidence": ["synthetic-intervention-result-pointer"],
        "produced_at": "2026-07-16T00:00:00+00:00",
    }
    path = runtime_root / f"{agent_id}-{status}-result.json"
    path.write_text(
        json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def admission_semantic_args(admission: dict[str, object]) -> list[str]:
    return [
        "--semantic-epoch",
        str(admission["semantic_epoch"]),
        "--charter-sha256",
        str(admission["charter_sha256"]),
        "--invariant-capsule-sha256",
        str(admission["invariant_capsule_sha256"]),
        "--checkpoint-id",
        str(admission["checkpoint_id"]),
        "--dispatch-uid",
        str(admission["dispatch_uid"]),
        "--attempt",
        str(admission["attempt"]),
    ]


def skill_requirements_json() -> str:
    skill = Path(__file__).resolve().parents[1] / "SKILL.md"
    digest = hashlib.sha256(skill.read_bytes()).hexdigest()
    return json.dumps(
        [
            {
                "name": "decretum-matrix",
                "source": str(skill.resolve()),
                "sha256": digest,
                "purpose": "intervention matrix assignment binding",
                "ack_name": "decretum-matrix",
                "ack_sha256": digest,
            }
        ],
        ensure_ascii=False,
    )


def start_contract_args(
    admission: dict[str, object],
    task_id: str,
    wave_id: str,
    collaboration_task_name: str,
) -> list[str]:
    return [
        *admission_semantic_args(admission),
        "--collaboration-task-name",
        collaboration_task_name,
        "--skill-requirements-json",
        skill_requirements_json(),
        *context_economy_args(task_id, wave_id),
    ]


def admit(
    cli: Path,
    env: dict[str, str],
    task_id: str,
    wave_id: str,
    fork_turns: str = "none",
    context_tokens: int = 1000,
    evidence: str = "policy admission",
    requested_roles: str = "",
    host_capacity: int = 4,
    host_active: int = 1,
    next_depth: int = 1,
    user_budget: int | None = None,
    provider_budget: int | None = None,
    assignment: str = "bounded court office work",
    task_focus: str = "general coordination",
    complexity: str = "medium",
    risk: str = "medium",
    ambiguity: str = "medium",
    transport: str = "codex",
    message_chars: int | None = None,
    message_required_chars: int | None = None,
    message_optional_chars: int | None = None,
    expected_error: str | None = None,
) -> dict[str, object]:
    args = [
        "agent-admit",
        "--task-id",
        task_id,
        *task_semantic_args(task_id),
        "--wave-id",
        wave_id,
        "--requested-fork-turns",
        fork_turns,
        "--context-tokens",
        str(context_tokens),
        *context_economy_args(task_id, wave_id),
        "--host-active-agents",
        str(host_active),
        "--host-capacity",
        str(host_capacity),
        "--host-retained-agents",
        "0",
        "--next-depth",
        str(next_depth),
        "--active-session-protocol",
        "v2",
        "--assignment",
        assignment,
        "--task-focus",
        task_focus,
        "--complexity",
        complexity,
        "--risk",
        risk,
        "--ambiguity",
        ambiguity,
        "--transport",
        transport,
        "--evidence",
        evidence,
    ]
    if requested_roles:
        args.extend(("--requested-roles", requested_roles))
        args.extend(
            role_budget_args(
                task_id,
                requested_roles,
                next_depth=next_depth,
            )
        )
    if message_chars is not None:
        args.extend(("--message-chars", str(message_chars)))
    if message_required_chars is not None:
        args.extend(("--message-required-chars", str(message_required_chars)))
    if message_optional_chars is not None:
        args.extend(("--message-optional-chars", str(message_optional_chars)))
    if user_budget is not None:
        args.extend(("--user-agent-budget", str(user_budget)))
    if provider_budget is not None:
        args.extend(("--provider-launch-budget", str(provider_budget)))
    if expected_error is not None:
        failed = run_cli(cli, env, "--format", "json", *args, expect=1)
        assert expected_error in failed.stderr, failed.stderr
        return {"expected_error": expected_error}
    return json_cli(
        cli,
        env,
        *args,
    )


def preload_ack(cli: Path, env: dict[str, str], task_id: str, agent_id: str, role: str) -> dict[str, object]:
    manifest = build_preload_manifest(role)
    tasks = json.loads((Path(env["COURT_RUNTIME_ROOT"]) / "tasks.json").read_text(encoding="utf-8"))
    model_route = tasks[task_id]["agents"][agent_id]["model_route"]
    route_args = [
        "--model-route-id", str(model_route["model_route_id"]),
        "--model-override-applied", "YES" if model_route["model_override_applied"] else "NO",
    ]
    if model_route["model_override_applied"]:
        route_args.extend(
            (
                "--active-model", str(model_route["model"]),
                "--active-reasoning-effort", str(model_route["reasoning_effort"]),
            )
        )
    else:
        route_args.extend(("--inheritance-policy", str(model_route["inheritance_policy"])))
    return json_cli(
        cli,
        env,
        "agent-preload-ack",
        "--task-id", task_id,
        *agent_semantic_args(env, task_id, agent_id),
        "--agent-id", agent_id,
        "--role", role,
        "--office-zh", manifest.office_zh,
        "--direct-superior", manifest.direct_superior,
        "--profile-hash", manifest.profile_hash,
        "--dossier-hash", manifest.dossier_hash,
        "--court-skill-hash", manifest.court_skill_hash,
        "--loaded-skills", "decretum-matrix",
        "--agent-dossier-loaded", "YES",
        *route_args,
        "--evidence", "preload manifest verified",
    )


def main() -> int:
    menxia_role_args = role_budget_args("caller-contract-menxia", "menxia")
    menxia_lease = json.loads(menxia_role_args[menxia_role_args.index("--budget-lease-json") + 1])
    menxia_bindings = json.loads(menxia_role_args[menxia_role_args.index("--requested-bindings-json") + 1])
    gongbu_role_args = role_budget_args("caller-contract-gongbu", "gongbu")
    gongbu_lease = json.loads(gongbu_role_args[gongbu_role_args.index("--budget-lease-json") + 1])
    gongbu_bindings = json.loads(gongbu_role_args[gongbu_role_args.index("--requested-bindings-json") + 1])
    actual_caller_contract = {
        "menxia_cli_caller": menxia_role_args[menxia_role_args.index("--calling-office") + 1],
        "menxia_cli_direct_superior": menxia_role_args[menxia_role_args.index("--direct-superior") + 1],
        "menxia_lease_caller": menxia_lease["calling_office"],
        "menxia_lease_direct_superior": menxia_lease["direct_superior"],
        "menxia_binding_direct_superior": menxia_bindings[0]["direct_superior"],
        "gongbu_cli_caller": gongbu_role_args[gongbu_role_args.index("--calling-office") + 1],
        "gongbu_cli_direct_superior": gongbu_role_args[gongbu_role_args.index("--direct-superior") + 1],
        "gongbu_lease_caller": gongbu_lease["calling_office"],
        "gongbu_lease_direct_superior": gongbu_lease["direct_superior"],
        "gongbu_binding_direct_superior": gongbu_bindings[0]["direct_superior"],
    }
    expected_caller_contract = {
        "menxia_cli_caller": "taizi",
        "menxia_cli_direct_superior": "user",
        "menxia_lease_caller": "taizi",
        "menxia_lease_direct_superior": "user",
        "menxia_binding_direct_superior": "taizi",
        "gongbu_cli_caller": "shangshu",
        "gongbu_cli_direct_superior": "taizi",
        "gongbu_lease_caller": "shangshu",
        "gongbu_lease_direct_superior": "taizi",
        "gongbu_binding_direct_superior": "shangshu",
    }
    assert actual_caller_contract == expected_caller_contract, actual_caller_contract
    pure_child_role_args = role_budget_args(
        "caller-contract-gongbu-children",
        "gongbu,gongbu",
    )
    pure_child_lease = json.loads(
        pure_child_role_args[pure_child_role_args.index("--budget-lease-json") + 1]
    )
    pure_child_bindings = json.loads(
        pure_child_role_args[pure_child_role_args.index("--requested-bindings-json") + 1]
    )
    actual_pure_child_contract = {
        "cli_caller": pure_child_role_args[pure_child_role_args.index("--calling-office") + 1],
        "cli_direct_superior": pure_child_role_args[pure_child_role_args.index("--direct-superior") + 1],
        "lease_caller": pure_child_lease["calling_office"],
        "lease_direct_superior": pure_child_lease["direct_superior"],
        "binding_direct_superiors": [binding["direct_superior"] for binding in pure_child_bindings],
        "binding_canonical_authorities": [binding["canonical_authority"] for binding in pure_child_bindings],
        "binding_owner_roles": [binding["owner_role"] for binding in pure_child_bindings],
        "binding_write_sets": [binding["write_set"] for binding in pure_child_bindings],
    }
    expected_pure_child_contract = {
        "cli_caller": "gongbu",
        "cli_direct_superior": "shangshu",
        "lease_caller": "gongbu",
        "lease_direct_superior": "shangshu",
        "binding_direct_superiors": ["gongbu", "gongbu"],
        "binding_canonical_authorities": [False, False],
        "binding_owner_roles": ["gongbu", "gongbu"],
        "binding_write_sets": [["work/gongbu/0001.txt"], ["work/gongbu/0002.txt"]],
    }
    assert actual_pure_child_contract == expected_pure_child_contract, actual_pure_child_contract
    scripts = Path(__file__).resolve().parent
    cli = scripts / "court_cli.py"
    watch = scripts / "court_heartbeat_watch.py"
    with tempfile.TemporaryDirectory() as temp_dir:
        env = dict(os.environ)
        env["COURT_RUNTIME_ROOT"] = temp_dir
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        intake_file = Path(temp_dir) / "formal-task-intake.json"
        intake_file.write_text(
            json.dumps(
                {
                    "schema": "court.conversation_gate.v1",
                    "active_decree": False,
                    "active_decree_state": "NONE",
                    "message_class": "FORMAL_TASK",
                    "confidence": "HIGH",
                    "relation_to_active_decree": "NONE",
                    "taskization_consent": "EXPLICIT",
                    "requires_tools": True,
                    "mutates_state": False,
                    "risk_present": False,
                    "next_route": "THREE_DEPARTMENTS",
                    "question": "",
                    "rationale": "intervention matrix formal task fixture",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        create_formal_task(
            cli,
            env,
            intake_file,
            "--task-id",
            "serial-policy",
            "--title",
            "serial policy",
            "--charter",
            "parallel_dispatch=NOT_APPLICABLE/user_serial_override; no child spawn",
            "--evidence",
            "create",
        )
        runtime_root = Path(env["COURT_RUNTIME_ROOT"])
        serial_state_before = {
            path.relative_to(runtime_root).as_posix(): (
                path.stat().st_mtime_ns,
                path.read_bytes(),
            )
            for path in runtime_root.rglob("*")
            if path.is_file()
        }
        serial_admission = admit(cli, env, "serial-policy", "serial-wave", evidence="serial override check")
        assert serial_admission["allowed"] is False
        assert serial_admission["decision"] == "user_serial_override"
        assert serial_admission["parallel_dispatch"] == "NOT_APPLICABLE/user_serial_override"
        serial_state_after = {
            path.relative_to(runtime_root).as_posix(): (
                path.stat().st_mtime_ns,
                path.read_bytes(),
            )
            for path in runtime_root.rglob("*")
            if path.is_file()
        }
        assert serial_state_after == serial_state_before

        create_formal_task(
            cli,
            env,
            intake_file,
            "--task-id",
            "agent-policy",
            "--title",
            "agent policy",
            "--charter",
            "bounded ordinary parallel review",
            "--evidence",
            "create",
        )
        missing_preload = admit(
            cli,
            env,
            "agent-policy",
            "missing-preload-wave",
            evidence="nonserial missing preload rejection",
            expected_error="agent_admission_canonical_preload_mismatch",
        )
        assert missing_preload["expected_error"] == "agent_admission_canonical_preload_mismatch"
        unbounded = admit(
            cli,
            env,
            "agent-policy",
            "wave-1",
            "all",
            100000,
            "long context fork check",
            requested_roles="menxia",
        )
        assert unbounded["allowed"] is False
        assert unbounded["decision"] == "unbounded_context_fork"
        assert unbounded["recommended_fork_turns"] == "none"

        bounded = admit(
            cli,
            env,
            "agent-policy",
            "wave-1-retry",
            context_tokens=100000,
            evidence="bounded context admission",
            requested_roles="menxia",
            assignment="policy test",
            task_focus="standards review",
        )
        assert bounded["allowed"] is True, bounded
        assert bounded["static_wave_cap"] is None
        assert bounded["wave_policy"] == "dynamic_by_duty_and_capacity"
        assert bounded["deadline_seconds"] == 600
        assert bounded["tool_call_budget"] == 8
        assert bounded["message_budget_status"] == "legacy_unmeasured"

        dynamic_message = admit(
            cli,
            env,
            "agent-policy",
            "message-budget-9000",
            message_chars=9000,
            requested_roles="gongbu",
            evidence="bounded dynamic message admission",
        )
        assert dynamic_message["allowed"] is True
        assert dynamic_message["message_budget_effective_chars"] == 9000
        assert dynamic_message["message_budget_status"] == "within_budget"

        oversized_message = admit(
            cli,
            env,
            "agent-policy",
            "message-budget-12001",
            message_chars=12001,
            message_required_chars=11500,
            message_optional_chars=501,
            requested_roles="gongbu",
            evidence="oversized dynamic message admission",
        )
        assert oversized_message["allowed"] is False
        assert oversized_message["decision"] == "dispatch_message_too_large"
        assert oversized_message["required_reduction_chars"] == 1
        assert oversized_message["optional_compression_target_chars"] == 1
        assert oversized_message["compression_possible_without_required_loss"] is True
        assert oversized_message["message_budget_retryable"] is True

        create_formal_task(
            cli,
            env,
            intake_file,
            "--task-id",
            "dynamic-capacity",
            "--title",
            "dynamic capacity",
            "--charter",
            "bounded ordinary parallel review",
            "--evidence",
            "create",
        )
        six_roles = admit(
            cli, env, "dynamic-capacity", "six-role-wave",
            requested_roles="libu-hr,hubu,libu,bingbu,xingbu,gongbu", host_capacity=8,
        )
        assert six_roles["allowed"] is True
        assert six_roles["selected_roles"] == ["libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"]
        assert six_roles["deferred_roles"] == []
        assert all(route["recommended_model"] == "gpt-5.6-terra" for route in six_roles["model_routes"].values())
        assert all(route["recommended_reasoning_effort"] == "ultra" for route in six_roles["model_routes"].values())
        assert all(route["model_override_applied"] is False for route in six_roles["model_routes"].values())
        security_routes = admit(
            cli,
            env,
            "dynamic-capacity",
            "security-route-wave",
            requested_roles="xingbu,gongbu",
            task_focus="security privacy and destructive-operation risk",
            risk="high",
        )
        assert security_routes["allowed"] is True, security_routes
        assert security_routes["model_routes"]["xingbu#0001"]["recommended_model"] == "gpt-5.6-sol"
        assert security_routes["model_routes"]["xingbu#0001"]["recommended_reasoning_effort"] == "ultra"
        four_slots = admit(
            cli, env, "dynamic-capacity", "four-slot-wave",
            requested_roles="zhongshu,menxia,shangshu,shiguan", host_capacity=4,
        )
        assert four_slots["selected_roles"] == ["zhongshu", "menxia", "shangshu"]
        assert four_slots["deferred_roles"] == ["shiguan"]
        assert four_slots["selection_basis"] == "runtime_capacity"
        tree_cap = admit(
            cli, env, "dynamic-capacity", "tree-cap-wave",
            requested_roles=",".join("gongbu" for _ in range(16)),
            host_capacity=64, host_active=1, next_depth=1,
        )
        assert len(tree_cap["selected_roles"]) == 15
        assert len(tree_cap["deferred_roles"]) == 1
        assert tree_cap["effective_host_capacity"] == 16
        assert tree_cap["calling_office"] == "gongbu"
        assert tree_cap["direct_superior"] == "shangshu"
        assert len(tree_cap["hierarchy_receipts"]) == 15
        assert all(
            receipt["hierarchy_gate"] == "PASSED"
            and receipt["hierarchy_edge_class"] == "bounded_child_office"
            and receipt["hierarchy_calling_office"] == "gongbu"
            and receipt["hierarchy_target_role"] == "gongbu"
            and receipt["hierarchy_owner_role"] == "gongbu"
            for receipt in tree_cap["hierarchy_receipts"]
        )
        depth_five = admit(
            cli, env, "dynamic-capacity", "depth-five-wave",
            requested_roles="xingbu", host_capacity=16, host_active=1, next_depth=5,
        )
        assert depth_five["allowed"] is False
        assert depth_five["decision"] == "max_depth_exceeded"
        run_cli(cli, env, "agent-spawn", "--task-id", "agent-policy",
                *start_contract_args(bounded, "agent-policy", "wave-1-retry", "menxia_policy_review"),
                "--agent-id", "menxia-policy-01",
                "--role", "menxia", "--scope", "policy test", "--wave-id", "wave-1-retry", "--fork-turns", "none",
                "--dispatch-requested-at", str(bounded["dispatch_requested_at"]),
                "--task-focus", "standards review", "--complexity", "medium", "--risk", "medium",
                "--ambiguity", "medium", "--transport", "codex",
                "--context-tokens", "100000", "--deadline-seconds", "600", "--tool-call-budget", "8",
                "--evidence", "spawned after admission")
        reconciled = json_cli(
            cli, env, "agent-reconcile", "--task-id", "agent-policy",
            *agent_semantic_args(env, "agent-policy", "menxia-policy-01"), "--agent-id", "menxia-policy-01",
            "--role", "menxia", "--error-kind", "fatal-quota", "--result",
            "403 Forbidden: quota insufficient; balance=-0.05; request id: req-sensitive; url: https://provider.invalid/v1/responses",
            "--evidence", "fatal quota from https://provider.invalid; request id: req-sensitive; balance=-0.05",
        )
        assert reconciled["agent"]["status"] == "failed"
        assert reconciled["agent"]["final_status"] == "failed"
        assert reconciled["agent"]["release_status"] == "closed"
        assert reconciled["agent"]["finished_at"]
        assert reconciled["agent"]["closed_at"]
        assert reconciled["circuit_breaker"]["state"] == "open"
        assert reconciled["circuit_breaker"]["scope"] == "task"
        assert reconciled["raw_provider_detail_stored"] is False
        assert "provider.invalid" not in reconciled["agent"]["result"]
        assert "req-sensitive" not in reconciled["agent"]["result"]
        assert "-0.05" not in reconciled["agent"]["result"]
        blocked_after_fatal = admit(
            cli,
            env,
            "agent-policy",
            "wave-2",
            evidence="circuit breaker check",
            requested_roles="menxia",
        )
        assert blocked_after_fatal["allowed"] is False
        assert blocked_after_fatal["decision"] == "fatal_provider_circuit_open"

        create_formal_task(
            cli,
            env,
            intake_file,
            "--task-id",
            "capacity-policy",
            "--title",
            "capacity policy",
            "--charter",
            "bounded ordinary parallel review",
            "--evidence",
            "create",
        )
        capacity_admission = admit(
            cli,
            env,
            "capacity-policy",
            "capacity-wave",
            requested_roles="shangshu",
            assignment="capacity test",
            task_focus="capacity coordination",
        )
        run_cli(cli, env, "agent-spawn", "--task-id", "capacity-policy",
                *start_contract_args(
                    capacity_admission,
                    "capacity-policy",
                    "capacity-wave",
                    "shangshu_capacity_review",
                ), "--agent-id", "shangshu-capacity-01",
                "--role", "shangshu", "--scope", "capacity test", "--wave-id", "capacity-wave",
                "--dispatch-requested-at", str(capacity_admission["dispatch_requested_at"]),
                "--task-focus", "capacity coordination", "--complexity", "medium", "--risk", "medium",
                "--ambiguity", "medium", "--transport", "codex",
                "--evidence", "spawn capacity test agent")
        capacity_reconciled = json_cli(
            cli, env, "agent-reconcile", "--task-id", "capacity-policy",
            *agent_semantic_args(env, "capacity-policy", "shangshu-capacity-01"),
            "--agent-id", "shangshu-capacity-01",
            "--role", "shangshu", "--error-kind", "capacity", "--result", "agent thread limit reached",
            "--evidence", "host capacity response",
        )
        assert capacity_reconciled["circuit_breaker"]["scope"] == "wave"
        assert capacity_reconciled["circuit_breaker"]["reuse_errored_agents"] is False
        same_wave = run_cli(
            cli,
            env,
            "agent-admit",
            "--task-id",
            "capacity-policy",
            *task_semantic_args("capacity-policy"),
            *context_economy_args("capacity-policy", "capacity-wave"),
            *role_budget_args("capacity-policy", "shangshu"),
            "--wave-id",
            "capacity-wave",
            "--requested-roles",
            "shangshu",
            "--requested-fork-turns",
            "none",
            "--context-tokens",
            "1000",
            "--host-active-agents",
            "1",
            "--host-capacity",
            "4",
            "--host-retained-agents",
            "0",
            "--next-depth",
            "1",
            "--assignment",
            "capacity test",
            "--task-focus",
            "capacity coordination",
            "--complexity",
            "medium",
            "--risk",
            "medium",
            "--ambiguity",
            "medium",
            "--transport",
            "codex",
            "--evidence",
            "same wave blocked",
            expect=1,
        )
        assert "agent admission wave already exists: capacity-wave" in same_wave.stderr
        next_wave = admit(
            cli,
            env,
            "capacity-policy",
            "capacity-wave-2",
            requested_roles="shangshu",
            evidence="new bounded wave",
        )
        assert next_wave["allowed"] is True, next_wave
        assert next_wave["reuse_errored_agents"] is False

        create_formal_task(
            cli,
            env,
            intake_file,
            "--task-id",
            "matrix",
            "--title",
            "matrix",
            "--charter",
            "bounded intervention matrix lifecycle",
            "--evidence",
            "create",
        )
        for state, actor in [
            ("Taizi", "taizi"),
            ("ThreeDepartments", "zhongshu"),
            ("ThreeDepartmentsPetition", "zhongshu"),
            ("TaiziReply", "taizi"),
            ("ShangshuDispatch", "shangshu"),
        ]:
            run_cli(
                cli,
                env,
                "transition",
                "--task-id",
                "matrix",
                "--to-state",
                state,
                "--actor",
                actor,
                "--evidence",
                f"to {state}",
            )
        run_cli(
            cli,
            env,
            "transition",
            "--task-id",
            "matrix",
            "--to-state",
            "Paused",
            "--actor",
            "shangshu",
            "--evidence",
            "direct pause",
            expect=1,
        )
        run_cli(
            cli,
            env,
            "pause",
            "--task-id",
            "matrix",
            "--reason",
            "matrix pause",
            "--affected-scope",
            "test",
            "--evidence-preserved",
            "events",
            "--unsafe-remaining",
            "none",
        )
        run_cli(
            cli,
            env,
            "resume",
            "--task-id",
            "matrix",
            "--to-state",
            "Workshops",
            "--resume-evidence",
            "skip",
            "--affected-scope",
            "test",
            expect=1,
        )
        run_cli(
            cli,
            env,
            "resume",
            "--task-id",
            "matrix",
            "--to-state",
            "ShangshuDispatch",
            "--resume-evidence",
            "resume source",
            "--affected-scope",
            "test",
        )
        matrix_admission = admit(
            cli,
            env,
            "matrix",
            "gongbu-matrix-wave-01",
            requested_roles="gongbu",
            assignment="matrix",
            task_focus="architecture and final integration",
            complexity="high",
            risk="medium",
            ambiguity="high",
        )
        dispatch_requested_at = str(matrix_admission["dispatch_requested_at"])
        run_cli(
            cli,
            env,
            "agent-spawn",
            "--task-id",
            "matrix",
            *start_contract_args(
                matrix_admission,
                "matrix",
                "gongbu-matrix-wave-01",
                "gongbu_matrix_integration",
            ),
            "--agent-id",
            "gongbu-matrix-01",
            "--role",
            "gongbu",
            "--scope",
            "matrix",
            "--wave-id",
            "gongbu-matrix-wave-01",
            "--task-focus",
            "architecture and final integration",
            "--complexity",
            "high",
            "--risk",
            "medium",
            "--ambiguity",
            "high",
            "--transport",
            "codex",
            "--dispatch-requested-at",
            dispatch_requested_at,
            "--evidence",
            "spawned",
        )
        acked = preload_ack(cli, env, "matrix", "gongbu-matrix-01", "gongbu")
        assert acked["agent"]["status"] == "running"
        assert acked["agent"]["office_identity_evidence"] == "PASSED"
        assert acked["agent"]["dispatch_requested_at"] == dispatch_requested_at
        assert acked["agent"]["host_session_started_at"]
        assert acked["agent"]["preload_ack_at"]
        assert acked["agent"]["model_route"]["recommended_model"] == "gpt-5.6-sol"
        assert acked["agent"]["model_route"]["recommended_reasoning_effort"] == "ultra"
        assert acked["agent"]["model_override_applied"] is False
        assert acked["agent"]["inheritance_policy"] == "inherit_main_thread_model_reserved_schema"
        assert acked["agent"]["model_route_status"] == "PASSED"
        reported = json_cli(
            cli, env, "agent-report", "--task-id", "matrix",
            *agent_semantic_args(env, "matrix", "gongbu-matrix-01"),
            "--agent-id", "gongbu-matrix-01",
            "--role", "gongbu", "--evidence", "first substantive office report",
        )
        assert reported["task"]["agents"]["gongbu-matrix-01"]["first_office_report_at"]
        run_cli(
            cli,
            env,
            "agent-heartbeat",
            "--task-id",
            "matrix",
            *agent_semantic_args(env, "matrix", "gongbu-matrix-01"),
            "--agent-id",
            "gongbu-matrix-01",
            "--role",
            "gongbu",
            "--evidence",
            "alive",
        )
        agents = run_cli(cli, env, "--format", "json", "agents", "--stale-after", "3600").stdout
        agents_payload = json.loads(agents)
        agent = next(item for item in agents_payload["agents"] if item["agent_id"] == "gongbu-matrix-01")
        assert agent["status"] == "running"
        watch_payload = json.loads(run_cli(watch, env, "--stale-seconds", "3600").stdout)
        assert watch_payload["ok"] is True
        tasks_path = Path(temp_dir) / "tasks.json"
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        stale_time = (datetime.now(timezone.utc).astimezone() - timedelta(minutes=10)).isoformat(timespec="seconds")
        tasks["matrix"]["agents"]["gongbu-matrix-01"]["last_heartbeat"] = stale_time
        tasks["matrix"]["agents"]["gongbu-matrix-01"]["expected_duration"] = "short"
        tasks_path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        stale_payload = json.loads(run_cli(watch, env, "--stale-seconds", "3600", expect=1).stdout)
        stale_agent = stale_payload["stale_agents"][0]
        assert stale_agent["expected_duration"] == "short"
        assert stale_agent["highlight"] == "[ATTN]"
        assert "threshold 300s" in stale_agent["stale_reason"]
        marked_payload = json.loads(run_cli(watch, env, "--stale-seconds", "3600", "--mark-stale", expect=1).stdout)
        assert marked_payload["mark_stale"] is True
        marked_tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        marked_agent = marked_tasks["matrix"]["agents"]["gongbu-matrix-01"]
        assert marked_agent["status"] == "stale"
        assert "threshold 300s" in marked_agent["stale_reason"]
        finish_envelope = result_envelope_file(
            env,
            "matrix",
            "gongbu-matrix-01",
            "gongbu",
            "cancelled",
        )
        run_cli(
            cli,
            env,
            "agent-finish",
            "--task-id",
            "matrix",
            *agent_semantic_args(env, "matrix", "gongbu-matrix-01"),
            "--agent-id",
            "gongbu-matrix-01",
            "--role",
            "gongbu",
            "--status",
            "cancelled",
            "--result-envelope-file",
            str(finish_envelope),
            "--evidence",
            "stale watchdog cancellation",
        )
        run_cli(
            cli,
            env,
            "agent-close",
            "--task-id",
            "matrix",
            *agent_semantic_args(env, "matrix", "gongbu-matrix-01"),
            "--agent-id",
            "gongbu-matrix-01",
            "--role",
            "gongbu",
            "--result",
            "done",
            "--evidence",
            "closed",
        )
        run_cli(
            cli,
            env,
            "cancel",
            "--task-id",
            "matrix",
            "--reason",
            "matrix cancel",
            "--affected-scope",
            "test",
            "--evidence-preserved",
            "events",
            "--unsafe-remaining",
            "none",
        )
    print("COURT_INTERVENTION_MATRIX_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
