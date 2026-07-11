"""Self-test the local /court runtime state machine without touching real tasks."""

from __future__ import annotations

from argparse import Namespace
import tempfile
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True

import court_runtime
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
from check_court_agent_lifecycle import run_agent_lifecycle_checks
import report_office_startup_latency as startup_latency


def main() -> int:
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

    capacity = admit_roles(
        host_capacity=64,
        active_threads=1,
        retained_threads=0,
        requested_roles=[f"role-{index}" for index in range(20)],
        max_threads=16,
        next_depth=4,
        max_depth=4,
    )
    assert capacity.allowed is True
    assert capacity.effective_host_capacity == 16
    assert len(capacity.selected_roles) == 15
    assert len(capacity.deferred_roles) == 5
    assert capacity.available_slots == 15

    depth_rejected = admit_roles(
        host_capacity=64,
        active_threads=1,
        retained_threads=0,
        requested_roles=["menxia"],
        max_threads=16,
        next_depth=5,
        max_depth=4,
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
                ("ShiguanRecorded", "shiguan"),
                ("Done", "menxia"),
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
            assert len(events) == 11
            payload = court_runtime.status_payload(Namespace(limit=5, state=""))
            assert payload["kind"] == "court_runtime_status"
            assert payload["runtime_schema_version"] == court_runtime.RUNTIME_SCHEMA_VERSION
            assert payload["task_count"] == 1
            assert payload["tasks"][0]["state"] == "Done"
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
