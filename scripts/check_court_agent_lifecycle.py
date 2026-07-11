"""Focused regression checks for admitted court-agent lifecycle integrity."""

from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
from typing import Callable

sys.dont_write_bytecode = True

import court_runtime


ROUTE = {
    "assignment": "bounded lifecycle work",
    "task_focus": "runtime lifecycle implementation",
    "complexity": "high",
    "risk": "medium",
    "ambiguity": "medium",
    "transport": "codex",
}


def create_task(task_id: str) -> None:
    court_runtime.create_task(
        Namespace(
            title=task_id,
            charter="bounded ordinary parallel lifecycle fixture",
            task_id=task_id,
            owner="taizi",
            report_tier="brief",
            evidence=f"create {task_id}",
            note="lifecycle fixture",
        )
    )


def admit(task_id: str, wave_id: str, role: str = "gongbu", **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "task_id": task_id,
        "wave_id": wave_id,
        "execution_topology": "parallel",
        "active_session_protocol": "v2",
        "requested_fork_turns": "none",
        "context_tokens": 1000,
        "message_chars": 100,
        "requested_agents": 1,
        "requested_roles": role,
        "host_active_agents": 1,
        "host_capacity": 16,
        "host_retained_agents": 0,
        "host_reclamation_status": "unknown",
        "next_depth": 1,
        "user_agent_budget": None,
        "provider_launch_budget": None,
        **ROUTE,
        "actor": "shangshu",
        "evidence": f"admit {role} for {wave_id}",
        "note": "lifecycle fixture",
    }
    values.update(overrides)
    return court_runtime.agent_admit(Namespace(**values))


def start_args(
    admission: dict[str, object],
    task_id: str,
    wave_id: str,
    agent_id: str,
    role: str = "gongbu",
    **overrides: object,
) -> Namespace:
    inputs = dict(admission.get("model_route_inputs") or ROUTE)
    values: dict[str, object] = {
        "task_id": task_id,
        "agent_id": agent_id,
        "role": role,
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
        "office_zh": "",
        "direct_superior": manifest["direct_superior"],
        "profile_hash": manifest["profile_hash"],
        "dossier_hash": manifest["dossier_hash"],
        "court_skill_hash": manifest["court_skill_hash"],
        "loaded_skills": "court-capability-router,tdd",
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
    values: dict[str, object] = {
        "task_id": task_id,
        "agent_id": agent_id,
        "role": role,
        "actor": "shangshu",
        "evidence": f"event {agent_id}",
        "note": "lifecycle fixture",
        "result": "done",
        "status": "completed",
    }
    values.update(overrides)
    return Namespace(**values)


def reject_unchanged(task_id: str, action: Callable[[], object], label: str) -> None:
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


def set_task_field(task_id: str, mutate: Callable[[dict[str, object]], None]) -> None:
    tasks = court_runtime.load_tasks()
    mutate(tasks[task_id])
    court_runtime.write_tasks(tasks)


def check_admission_binding() -> None:
    task_id = "lifecycle-binding"
    create_task(task_id)
    route = admit(task_id, "route-wave")
    route_id = route["model_routes"]["gongbu"]["model_route_id"]

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
        task["agent_admissions"]["wave"]["consumed_roles"] = []

    set_task_field("corrupt-consumed", corrupt_consumed)
    reject_unchanged(
        "corrupt-consumed",
        lambda: court_runtime.agent_start(start_args(corrupt, "corrupt-consumed", "wave", "agent")),
        "corrupt consumed_roles was replaced",
    )

    started = court_runtime.agent_start(start_args(route, task_id, "route-wave", "agent-1"))
    agent = started.task["agents"]["agent-1"]
    assert agent["model_route"]["model_route_id"] == route_id
    assert started.task["agent_admissions"]["route-wave"]["consumed_roles"]["gongbu"] == "agent-1"
    reject_unchanged(
        task_id,
        lambda: court_runtime.agent_start(start_args(route, task_id, "route-wave", "agent-2")),
        "consumed admitted role reused",
    )
    reject_unchanged(
        task_id,
        lambda: court_runtime.agent_start(start_args(route, task_id, "route-wave", "agent-1")),
        "existing agent id restarted",
    )
    for action in (
        lambda: court_runtime.agent_heartbeat(event_args(task_id, "unknown")),
        lambda: court_runtime.agent_report(event_args(task_id, "unknown")),
        lambda: court_runtime.agent_finish(event_args(task_id, "unknown")),
        lambda: court_runtime.agent_close(event_args(task_id, "unknown")),
    ):
        reject_unchanged(task_id, action, "unknown agent lifecycle accepted")
    for action in (
        lambda: court_runtime.agent_heartbeat(event_args(task_id, "agent-1", "menxia")),
        lambda: court_runtime.agent_report(event_args(task_id, "agent-1", "menxia")),
        lambda: court_runtime.agent_finish(event_args(task_id, "agent-1", "menxia")),
        lambda: court_runtime.agent_close(event_args(task_id, "agent-1", "menxia")),
        lambda: court_runtime.agent_preload_ack(ack_args(task_id, "agent-1", "menxia")),
    ):
        reject_unchanged(task_id, action, "role mismatch mutated lifecycle")
    reject_unchanged(
        task_id,
        lambda: court_runtime.agent_event(event_args(task_id, "agent-1"), "unknown_action", "running", "evidence"),
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
    assert failed["deferred_roles"] == ["menxia", "shangshu"]
    assert court_runtime.load_tasks()[prestart_task]["agents"] == {}
    assert court_runtime.load_tasks()[prestart_task]["agent_wave_blocks"]["prestart-wave"]["error_kind"] == "capacity"
    reject_unchanged(
        prestart_task,
        lambda: court_runtime.agent_start(
            start_args(prestart_admission, prestart_task, "prestart-wave", "late-menxia", role="menxia")
        ),
        "capacity-failed role started after the wave was blocked",
    )


def check_terminal_and_identity() -> None:
    task_id = "terminal-agent"
    create_task(task_id)
    admission = admit(task_id, "terminal-wave")
    start = start_args(admission, task_id, "terminal-wave", "terminal")
    court_runtime.agent_start(start)
    try:
        court_runtime.agent_preload_ack(ack_args(task_id, "terminal", profile_hash="invalid"))
    except ValueError:
        pass
    else:
        raise AssertionError("invalid preload acknowledgement passed")
    terminal = court_runtime.load_tasks()[task_id]["agents"]["terminal"]
    assert terminal["status"] == "failed"
    assert terminal["final_status"] == "failed"
    assert terminal["release_status"] == "closed"
    for action in (
        lambda: court_runtime.agent_heartbeat(event_args(task_id, "terminal")),
        lambda: court_runtime.agent_report(event_args(task_id, "terminal")),
        lambda: court_runtime.agent_finish(event_args(task_id, "terminal")),
        lambda: court_runtime.agent_start(start),
        lambda: court_runtime.agent_preload_ack(ack_args(task_id, "terminal")),
    ):
        reject_unchanged(task_id, action, "terminal agent was mutated")

    identity_task = "manifest-identity"
    create_task(identity_task)
    identity_admission = admit(identity_task, "identity-wave")
    court_runtime.agent_start(start_args(identity_admission, identity_task, "identity-wave", "identity"))
    parsed = court_runtime.build_parser().parse_args(
        [
            "agent-preload-ack",
            "--task-id",
            identity_task,
            "--agent-id",
            "identity",
            "--role",
            "gongbu",
            "--direct-superior",
            "shangshu",
            "--profile-hash",
            court_runtime.load_tasks()[identity_task]["agents"]["identity"]["preload_manifest"]["profile_hash"],
            "--dossier-hash",
            court_runtime.load_tasks()[identity_task]["agents"]["identity"]["preload_manifest"]["dossier_hash"],
            "--court-skill-hash",
            court_runtime.load_tasks()[identity_task]["agents"]["identity"]["preload_manifest"]["court_skill_hash"],
            "--loaded-skills",
            "court-capability-router,tdd",
            "--agent-dossier-loaded",
            "YES",
            "--model-route-id",
            court_runtime.load_tasks()[identity_task]["agents"]["identity"]["model_route"]["model_route_id"],
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
    court_runtime.agent_report(event_args(identity_task, "identity"))
    court_runtime.agent_heartbeat(event_args(identity_task, "identity"))
    court_runtime.agent_finish(event_args(identity_task, "identity"))
    court_runtime.agent_close(event_args(identity_task, "identity"))
    reject_unchanged(
        identity_task,
        lambda: court_runtime.agent_close(event_args(identity_task, "identity")),
        "repeated close mutated record",
    )

    mojibake = admit(identity_task, "mojibake-wave")
    court_runtime.agent_start(start_args(mojibake, identity_task, "mojibake-wave", "mojibake"))
    try:
        court_runtime.agent_preload_ack(ack_args(identity_task, "mojibake", office_zh="å·¥éƒ¨"))
    except ValueError:
        pass
    else:
        raise AssertionError("inconsistent explicit office_zh passed")
    assert court_runtime.load_tasks()[identity_task]["agents"]["mojibake"]["status"] == "failed"

    uppercase_task = "uppercase-digest-identity"
    create_task(uppercase_task)
    uppercase_admission = admit(uppercase_task, "uppercase-wave")
    court_runtime.agent_start(
        start_args(uppercase_admission, uppercase_task, "uppercase-wave", "uppercase")
    )
    uppercase_record = court_runtime.load_tasks()[uppercase_task]["agents"]["uppercase"]
    uppercase_manifest = uppercase_record["preload_manifest"]
    uppercase_ack = court_runtime.agent_preload_ack(
        ack_args(
            uppercase_task,
            "uppercase",
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
    court_runtime.agent_start(start_args(v1_admission, v1_task, "v1-wave", "v1-agent"))
    v1_ack = court_runtime.agent_preload_ack(ack_args(v1_task, "v1-agent"))
    assert v1_ack["agent"]["status"] == "running"
    assert v1_ack["agent"]["model_override_applied"] is False
    assert v1_ack["agent"]["inheritance_policy"] == "inherit_main_thread_model_v1_agent_type"


def run_agent_lifecycle_checks() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            check_admission_binding()
            check_terminal_and_identity()
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]


def main() -> int:
    run_agent_lifecycle_checks()
    print("COURT_AGENT_LIFECYCLE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
