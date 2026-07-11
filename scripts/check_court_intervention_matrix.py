"""Integration-test court intervention and agent lifecycle commands."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True

import tempfile
from datetime import datetime, timedelta, timezone

from court_office_bootstrap import build_preload_manifest


def run_cli(script: Path, env: dict[str, str], *args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([sys.executable, str(script), *args], text=True, capture_output=True, env=env, check=False)
    if result.returncode != expect:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise AssertionError(f"command {args} returned {result.returncode}, expected {expect}")
    return result


def json_cli(script: Path, env: dict[str, str], *args: str) -> dict[str, object]:
    return json.loads(run_cli(script, env, "--format", "json", *args).stdout)


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
) -> dict[str, object]:
    args = [
        "agent-admit",
        "--task-id",
        task_id,
        "--wave-id",
        wave_id,
        "--requested-fork-turns",
        fork_turns,
        "--context-tokens",
        str(context_tokens),
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
    if user_budget is not None:
        args.extend(("--user-agent-budget", str(user_budget)))
    if provider_budget is not None:
        args.extend(("--provider-launch-budget", str(provider_budget)))
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
        "--agent-id", agent_id,
        "--role", role,
        "--office-zh", manifest.office_zh,
        "--direct-superior", manifest.direct_superior,
        "--profile-hash", manifest.profile_hash,
        "--dossier-hash", manifest.dossier_hash,
        "--court-skill-hash", manifest.court_skill_hash,
        "--loaded-skills", "court-capability-router",
        "--agent-dossier-loaded", "YES",
        *route_args,
        "--evidence", "preload manifest verified",
    )


def main() -> int:
    scripts = Path(__file__).resolve().parent
    cli = scripts / "court_cli.py"
    watch = scripts / "court_heartbeat_watch.py"
    with tempfile.TemporaryDirectory() as temp_dir:
        env = dict(os.environ)
        env["COURT_RUNTIME_ROOT"] = temp_dir
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        run_cli(cli, env, "create", "--task-id", "serial-policy", "--title", "serial policy", "--charter",
                "parallel_dispatch=NOT_APPLICABLE/user_serial_override; no child spawn", "--evidence", "create")
        serial_admission = admit(cli, env, "serial-policy", "serial-wave", evidence="serial override check")
        assert serial_admission["allowed"] is False
        assert serial_admission["decision"] == "user_serial_override"
        assert serial_admission["parallel_dispatch"] == "NOT_APPLICABLE/user_serial_override"

        run_cli(cli, env, "create", "--task-id", "agent-policy", "--title", "agent policy", "--charter",
                "bounded ordinary parallel review", "--evidence", "create")
        unbounded = admit(cli, env, "agent-policy", "wave-1", "all", 100000, "long context fork check")
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
        assert bounded["allowed"] is True
        assert bounded["static_wave_cap"] is None
        assert bounded["wave_policy"] == "dynamic_by_duty_and_capacity"
        assert bounded["deadline_seconds"] == 600
        assert bounded["tool_call_budget"] == 8

        run_cli(cli, env, "create", "--task-id", "dynamic-capacity", "--title", "dynamic capacity",
                "--charter", "bounded ordinary parallel review", "--evidence", "create")
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
            requested_roles="xingbu,shiguan",
            task_focus="security privacy and destructive-operation risk",
            risk="high",
        )
        assert security_routes["model_routes"]["xingbu"]["recommended_model"] == "gpt-5.6-sol"
        assert security_routes["model_routes"]["xingbu"]["recommended_reasoning_effort"] == "ultra"
        four_slots = admit(
            cli, env, "dynamic-capacity", "four-slot-wave",
            requested_roles="zhongshu,menxia,shangshu,shiguan", host_capacity=4,
        )
        assert four_slots["selected_roles"] == ["zhongshu", "menxia", "shangshu"]
        assert four_slots["deferred_roles"] == ["shiguan"]
        assert four_slots["selection_basis"] == "runtime_capacity"
        tree_cap = admit(
            cli, env, "dynamic-capacity", "tree-cap-wave",
            requested_roles=",".join(f"unspecified-{index}" for index in range(1, 21)),
            host_capacity=64, host_active=1, next_depth=1,
        )
        assert len(tree_cap["selected_roles"]) == 15
        assert len(tree_cap["deferred_roles"]) == 5
        assert tree_cap["effective_host_capacity"] == 16
        depth_five = admit(
            cli, env, "dynamic-capacity", "depth-five-wave",
            requested_roles="xingbu", host_capacity=16, host_active=1, next_depth=5,
        )
        assert depth_five["allowed"] is False
        assert depth_five["decision"] == "max_depth_exceeded"
        run_cli(cli, env, "agent-spawn", "--task-id", "agent-policy", "--agent-id", "policy-agent",
                "--role", "menxia", "--scope", "policy test", "--wave-id", "wave-1-retry", "--fork-turns", "none",
                "--dispatch-requested-at", str(bounded["dispatch_requested_at"]),
                "--task-focus", "standards review", "--complexity", "medium", "--risk", "medium",
                "--ambiguity", "medium", "--transport", "codex",
                "--context-tokens", "100000", "--deadline-seconds", "600", "--tool-call-budget", "8",
                "--evidence", "spawned after admission")
        reconciled = json_cli(
            cli, env, "agent-reconcile", "--task-id", "agent-policy", "--agent-id", "policy-agent",
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
        blocked_after_fatal = admit(cli, env, "agent-policy", "wave-2", evidence="circuit breaker check")
        assert blocked_after_fatal["allowed"] is False
        assert blocked_after_fatal["decision"] == "fatal_provider_circuit_open"

        run_cli(cli, env, "create", "--task-id", "capacity-policy", "--title", "capacity policy", "--charter",
                "bounded ordinary parallel review", "--evidence", "create")
        capacity_admission = admit(
            cli,
            env,
            "capacity-policy",
            "capacity-wave",
            requested_roles="shangshu",
            assignment="capacity test",
            task_focus="capacity coordination",
        )
        run_cli(cli, env, "agent-spawn", "--task-id", "capacity-policy", "--agent-id", "capacity-agent",
                "--role", "shangshu", "--scope", "capacity test", "--wave-id", "capacity-wave",
                "--dispatch-requested-at", str(capacity_admission["dispatch_requested_at"]),
                "--task-focus", "capacity coordination", "--complexity", "medium", "--risk", "medium",
                "--ambiguity", "medium", "--transport", "codex",
                "--evidence", "spawn capacity test agent")
        capacity_reconciled = json_cli(
            cli, env, "agent-reconcile", "--task-id", "capacity-policy", "--agent-id", "capacity-agent",
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
            "--wave-id",
            "capacity-wave",
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
        next_wave = admit(cli, env, "capacity-policy", "capacity-wave-2", evidence="new bounded wave")
        assert next_wave["allowed"] is True
        assert next_wave["reuse_errored_agents"] is False

        run_cli(cli, env, "create", "--task-id", "matrix", "--title", "matrix", "--evidence", "create")
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
            "matrix-agent-1",
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
            "--agent-id",
            "agent-1",
            "--role",
            "gongbu",
            "--scope",
            "matrix",
            "--wave-id",
            "matrix-agent-1",
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
        acked = preload_ack(cli, env, "matrix", "agent-1", "gongbu")
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
            cli, env, "agent-report", "--task-id", "matrix", "--agent-id", "agent-1",
            "--role", "gongbu", "--evidence", "first substantive office report",
        )
        assert reported["task"]["agents"]["agent-1"]["first_office_report_at"]
        run_cli(
            cli,
            env,
            "agent-heartbeat",
            "--task-id",
            "matrix",
            "--agent-id",
            "agent-1",
            "--role",
            "gongbu",
            "--evidence",
            "alive",
        )
        agents = run_cli(cli, env, "--format", "json", "agents", "--stale-after", "3600").stdout
        agents_payload = json.loads(agents)
        agent = next(item for item in agents_payload["agents"] if item["agent_id"] == "agent-1")
        assert agent["status"] == "running"
        watch_payload = json.loads(run_cli(watch, env, "--stale-seconds", "3600").stdout)
        assert watch_payload["ok"] is True
        tasks_path = Path(temp_dir) / "tasks.json"
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        stale_time = (datetime.now(timezone.utc).astimezone() - timedelta(minutes=10)).isoformat(timespec="seconds")
        tasks["matrix"]["agents"]["agent-1"]["last_heartbeat"] = stale_time
        tasks["matrix"]["agents"]["agent-1"]["expected_duration"] = "short"
        tasks_path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        stale_payload = json.loads(run_cli(watch, env, "--stale-seconds", "3600", expect=1).stdout)
        stale_agent = stale_payload["stale_agents"][0]
        assert stale_agent["expected_duration"] == "short"
        assert stale_agent["highlight"] == "[ATTN]"
        assert "threshold 300s" in stale_agent["stale_reason"]
        marked_payload = json.loads(run_cli(watch, env, "--stale-seconds", "3600", "--mark-stale", expect=1).stdout)
        assert marked_payload["mark_stale"] is True
        marked_tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        marked_agent = marked_tasks["matrix"]["agents"]["agent-1"]
        assert marked_agent["status"] == "stale"
        assert "threshold 300s" in marked_agent["stale_reason"]
        run_cli(
            cli,
            env,
            "agent-finish",
            "--task-id",
            "matrix",
            "--agent-id",
            "agent-1",
            "--role",
            "gongbu",
            "--status",
            "cancelled",
            "--result",
            "stale agent reclaimed",
            "--evidence",
            "stale watchdog cancellation",
        )
        run_cli(
            cli,
            env,
            "agent-close",
            "--task-id",
            "matrix",
            "--agent-id",
            "agent-1",
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
