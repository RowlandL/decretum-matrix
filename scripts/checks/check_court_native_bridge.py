"""Focused safety checks for the current-session native host bridge."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import uuid
from unittest.mock import patch
from argparse import Namespace
from types import MappingProxyType

sys.dont_write_bytecode = True


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from commands import court_native_bridge as bridge
import court_runtime
from court_case_binding import office_capsule_reference
from court_native_host_dispatch import native_request_reference

CASE_REF = {"court_code": "CFT-20260906-001-A001", "charter_revision": 3}
DISPATCH_UID = "DSP-" + uuid.uuid4().hex
ISSUED_AT = "2026-09-06T12:30:00+08:00"


def _request() -> dict[str, object]:
    return {
        "schema": "court.native_host_dispatch_request.v1",
        "task_id": "native-bridge-task",
        "wave_id": "native-bridge-wave",
        "dispatch_uid": DISPATCH_UID,
        "attempt": 1,
        "role": "gongbu",
        "instance_id": "gongbu-native-0001",
        "direct_superior": "shangshu",
        "semantic_epoch": 3,
        "case_ref": dict(CASE_REF),
        "office_capsule_ref": office_capsule_reference(CASE_REF, "gongbu", "gongbu-native-0001", ISSUED_AT),
        "lease_id": "native-bridge-lease",
        "assignment": "bounded native bridge safety fixture",
        "duty_scope": ["scripts/commands/court_native_bridge.py"],
        "write_set": ["scripts/commands/court_native_bridge.py"],
        "role_ack": {
            "role": "gongbu",
            "direct_superior": "shangshu",
            **court_runtime._native_role_ack_sources(court_runtime._semantic_preload_sources("gongbu")),
        },
        "admission_anchor": {
            "schema": "court.agent.admission_receipt.v1",
            "receipt_id": "EVT-NATIVE-BRIDGE-01",
        },
        "compatible_live_instances": [],
    }


def _execution() -> dict[str, object]:
    return {"authority": "super", "behavior": "parallel"}


def _p00_context(request: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "court.semantic.dispatch_context_packet.v1",
        "semantic_epoch": request["semantic_epoch"],
        "case_ref": dict(CASE_REF),
        "semantic_receipt_id": "SEM-NATIVE-BRIDGE-01",
        "fork_context": "none",
        "context_mode": "bounded",
        "pointers": [{"path": "authority/current.md", "case_ref": dict(CASE_REF)}],
    }


def _write_trace(
    home: Path,
    *,
    session_id: str,
    marker: str,
    thread_id: str = "root-native-bridge",
    meta_session_id: str | None = None,
    tool_name: str = "spawn_agent",
    include_marker: bool = True,
    host_agent_id: str = "gongbu-host-agent-01",
    host_thread_id: str = "gongbu-host-thread-01",
    host_task_id: str = "gongbu-host-task-01",
    invocation: dict[str, object] | None = None,
    argument_overrides: dict[str, object] | None = None,
    output_only_task_name: bool = False,
) -> None:
    sessions = home / "sessions" / "2026" / "09"
    sessions.mkdir(parents=True)
    path = sessions / f"rollout-{session_id}.jsonl"
    expected_arguments = (
        dict(invocation.get("arguments") or {}) if isinstance(invocation, dict) else {}
    )
    message = str(expected_arguments.get("message") or marker)
    if not include_marker:
        message = "unrelated bounded fixture message"
    arguments = {
        "task_name": "gongbu_native_bridge",
        "fork_turns": "none",
        "message": message,
    }
    if expected_arguments:
        arguments = expected_arguments
    if argument_overrides:
        arguments.update(argument_overrides)
    records = [
        {
            "type": "session_meta",
            "payload": {
                "id": meta_session_id or session_id,
                "thread_id": thread_id,
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": str(invocation.get("tool_name")) if isinstance(invocation, dict) else tool_name,
                "call_id": "call-native-bridge-01",
                "arguments": json.dumps(
                    arguments
                ),
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call-native-bridge-01",
                "output": json.dumps(
                    {"task_name": host_task_id}
                    if output_only_task_name
                    else {
                        "ok": True,
                        "agent_id": host_agent_id,
                        "thread_id": host_thread_id,
                        "task_id": host_task_id,
                    }
                ),
            },
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in records), encoding="utf-8")


def _expect_rejected(call: object, label: str) -> None:
    try:
        call()  # type: ignore[operator]
    except (TypeError, ValueError):
        return
    raise AssertionError(f"{label}: expected fail-closed rejection")


def _runtime_request_builder_fixture() -> None:
    """Exercise the runtime thin wiring without a real session or ledger write."""

    task_id = "native-bridge-runtime-task"
    wave_id = "native-bridge-runtime-wave"
    instance_id = "gongbu-native-0001"
    binding: dict[str, object] = {
        "role": "gongbu",
        "instance_id": instance_id,
        "direct_superior": "shangshu",
        "lease_id": "native-bridge-runtime-lease",
        "read_scope": ["scripts/commands/court_native_bridge.py"],
        "write_set": ["scripts/commands/court_native_bridge.py"],
        "preload_sources": court_runtime._semantic_preload_sources("gongbu"),
        "office_capsule_ref": office_capsule_reference(CASE_REF, "gongbu", instance_id, ISSUED_AT),
    }
    admission: dict[str, object] = {
        "task_id": task_id,
        "wave_id": wave_id,
        "allowed": True,
        "dispatch_uid": DISPATCH_UID,
        "attempt": 1,
        "semantic_epoch": 3,
        "case_ref": dict(CASE_REF),
        "selected_bindings": [binding],
        "model_route_inputs": {
            "assignment": "bounded runtime native request fixture",
            "task_focus": "native bridge",
            "complexity": "medium",
            "risk": "medium",
            "ambiguity": "low",
            "transport": "codex",
        },
    }
    admission["admission_event_id"] = "EVT-NATIVE-BRIDGE-RUNTIME-01"
    task: dict[str, object] = {
        "task_id": task_id,
        **CASE_REF,
        "agent_admissions": {wave_id: admission},
        "agents": {},
    }
    event = {
        "action": "agent_admit",
        "wave_id": wave_id,
        "allowed": True,
        "admission_record": court_runtime._admission_bound_record(admission),
        "event_id": "EVT-NATIVE-BRIDGE-RUNTIME-01",
    }
    original_load_tasks = court_runtime.load_tasks
    original_events_for_task = court_runtime.events_for_task
    original_binding_guard = court_runtime.require_semantic_mutation_binding
    original_caller_guard = court_runtime._native_bridge_caller_guard
    original_request_result = court_runtime._native_bridge_request_result
    original_identity = bridge.current_host_identity
    try:
        court_runtime.load_tasks = lambda: {task_id: task}  # type: ignore[assignment]
        court_runtime.events_for_task = lambda *_args, **_kwargs: [event]  # type: ignore[assignment]
        court_runtime.require_semantic_mutation_binding = lambda _task: None  # type: ignore[assignment]
        court_runtime._native_bridge_caller_guard = lambda *_args, **_kwargs: None  # type: ignore[assignment]
        court_runtime._native_bridge_request_result = lambda _task, _admission, _binding, request: bridge.native_request_result(  # type: ignore[assignment]
            request,
            execution=_execution(),
            p00_context=_p00_context(request),
        )
        bridge.current_host_identity = lambda **_kwargs: {  # type: ignore[assignment]
            "thread_id": "root-native-bridge",
            "session_id": "019f4eb0-38e7-7760-bbc9-77a030b7cf0e",
        }
        result = court_runtime.office_native_request(
            Namespace(
                schema="court.office.native_request.v1",
                task_id=task_id,
                wave_id=wave_id,
                instance_id=instance_id,
            )
        )
        assert result["request"]["task_id"] == task_id
        assert result["request"]["admission_anchor"]["receipt_id"] == event["event_id"]
        assert result["expected_host_action"] == "spawn"
    finally:
        court_runtime.load_tasks = original_load_tasks  # type: ignore[assignment]
        court_runtime.events_for_task = original_events_for_task  # type: ignore[assignment]
        court_runtime.require_semantic_mutation_binding = original_binding_guard  # type: ignore[assignment]
        court_runtime._native_bridge_caller_guard = original_caller_guard  # type: ignore[assignment]
        court_runtime._native_bridge_request_result = original_request_result  # type: ignore[assignment]
        bridge.current_host_identity = original_identity  # type: ignore[assignment]


def _runtime_host_message_fixture() -> None:
    """Exercise P1 authority/P00/budget message construction without a ledger."""

    request = _request()
    admission: dict[str, object] = {
        "wave_id": request["wave_id"],
        "message_budget_effective_chars": 1,
        "selected_protocol": "v2",
        "model_routes": {
            request["instance_id"]: {
                "transport": "codex",
                "protocol": "v2",
                "role": request["role"],
                "spawn_metadata": {"fork_turns": "none"},
            }
        },
    }
    task: dict[str, object] = {
        "task_id": request["task_id"],
        **CASE_REF,
        "case_binding": MappingProxyType(
            {**CASE_REF, "case_execution": {"authority": "super", "behavior": "parallel"}}
        ),
        "semantic_receipt": {
            "semantic_epoch": request["semantic_epoch"],
            "case_ref": dict(CASE_REF),
            "receipt_id": "SEM-NATIVE-BRIDGE-01",
            "plan_cursor": "ThreeDepartments@3",
        },
    }
    binding = {
        "role": request["role"],
        "instance_id": request["instance_id"],
        "office_instance_kind": "child_agent",
        "preload_sources": court_runtime._semantic_preload_sources(str(request["role"])),
    }
    result = court_runtime._native_bridge_request_result(task, admission, binding, request)
    message = json.loads(result["host_message"])
    assert message["task"]["task_id"] == request["task_id"]
    assert message["task"]["role_key"] == request["role"]
    assert message["execution"] == {"authority": "super", "behavior": "parallel"}
    assert message["p00"]["dispatch_context"]["fork_context"] == "none"
    assert result["host_input_budget"]["status"] == "within_budget"
    assert result["host_input_budget"]["total_bytes"] <= 20 * 1024
    assert result["bound_agent_type"] is None

    # Exercise the capture's actual start-request generator, not a hand-filled
    # lifecycle request that could hide an empty required-skill list.
    with patch.object(court_runtime, '_native_bridge_model_inputs', return_value={
        'assignment':'fixture', 'task_focus':'fixture', 'complexity':'low',
        'risk':'low', 'ambiguity':'low', 'transport':'codex'}), patch.object(
        court_runtime, 'public_dispatch_context_packet', return_value={}), patch.object(
        court_runtime, 'public_context_budget_pool', return_value={}), patch.object(
        court_runtime, '_revalidate_context_economy_start', return_value=None):
        generated = court_runtime._native_bridge_start_request(
            task, admission, {**binding, 'instance_id':'gongbu#0001'}, request,
            {'request_ref':native_request_reference(request), 'native_host_action_receipt':{}})
    required = json.loads(generated['skill_requirements_json'])
    assert len(required) == 1 and required[0]['name'] == 'decretum-matrix'
    assert required[0]['source'] == str((court_runtime.skill_root() / 'SKILL.md').resolve())
    assert set(required[0]) == {'name', 'source', 'purpose', 'ack_name'}
    assert required[0]['ack_name'] == 'decretum-matrix'

    v1_admission = {
        **admission,
        "selected_protocol": "v1",
        "model_routes": {
            request["instance_id"]: {
                "transport": "codex",
                "protocol": "v1",
                "role": request["role"],
                "spawn_metadata": {"agent_type": "gongbu", "fork_turns": "none"},
            }
        },
    }
    assert court_runtime._native_bridge_bound_agent_type(v1_admission, binding) == "gongbu"
    bad_v1 = {
        **v1_admission,
        "model_routes": {
            request["instance_id"]: {
                **v1_admission["model_routes"][request["instance_id"]],
                "spawn_metadata": {"fork_turns": "none"},
            }
        },
    }
    _expect_rejected(
        lambda: court_runtime._native_bridge_bound_agent_type(bad_v1, binding),
        "v1 bound agent_type missing",
    )
    _expect_rejected(
        lambda: court_runtime._native_bridge_preload_input_budget(
            binding,
            "x" * (20 * 1024),
        ),
        "entry and preload budget exceeded",
    )


def _caller_guard_fixture() -> None:
    """Root may dispatch 三省; a ministry must be reached through Shangshu."""

    import court_case_binding

    root_session = "019f4eb0-38e7-7760-bbc9-77a030b7cf0e"
    ministry_binding = {"role": "gongbu", "direct_superior": "shangshu"}
    department_binding = {"role": "shangshu", "direct_superior": "taizi"}
    task: dict[str, object] = {
        "case_binding": {"session_id": root_session},
        "agents": {},
    }
    original_validate = court_case_binding.validate_case_binding
    original_identity = bridge.current_host_identity
    original_identity_context = court_runtime._native_bridge_identity_context
    try:
        court_case_binding.validate_case_binding = lambda *_args, **_kwargs: {}  # type: ignore[assignment]
        court_runtime._native_bridge_identity_context = lambda *_args, **_kwargs: None  # type: ignore[assignment]
        bridge.current_host_identity = lambda **_kwargs: {  # type: ignore[assignment]
            "thread_id": "root-thread",
            "session_id": root_session,
        }
        _expect_rejected(
            lambda: court_runtime._native_bridge_caller_guard(task, ministry_binding),
            "root to gongbu bypass",
        )
        court_runtime._native_bridge_caller_guard(task, department_binding)
        task["agents"] = {
            "shangshu-native": {
                "role": "shangshu",
                "native_host_thread_id": "shangshu-native-thread",
                "native_host_action_receipt_id": "native-host-shangshu",
                "preload_status": "PASSED",
                "office_execution_ready": True,
                "status": "running",
            }
        }
        bridge.current_host_identity = lambda **_kwargs: {  # type: ignore[assignment]
            "thread_id": "shangshu-native-thread",
            "session_id": "019f4eae-7c0c-71c3-b992-e4cd83f21ae8",
        }
        court_runtime._native_bridge_caller_guard(task, ministry_binding)
    finally:
        court_case_binding.validate_case_binding = original_validate  # type: ignore[assignment]
        bridge.current_host_identity = original_identity  # type: ignore[assignment]
        court_runtime._native_bridge_identity_context = original_identity_context  # type: ignore[assignment]


def main() -> int:
    request = _request()
    execution = _execution()
    p00_context = _p00_context(request)
    result = bridge.native_request_result(
        request,
        execution=execution,
        p00_context=p00_context,
    )
    assert result["schema"] == "court.office.native_request.result.v1"
    marker = result["host_message_marker"]
    assert isinstance(marker, str) and bridge.HOST_MARKER_PREFIX in marker
    assert result["request_ref"] == native_request_reference(request)
    assert json.loads(result["host_message"])["marker"] == marker
    assert result["host_invocation"]["arguments"]["message"] == result["host_message"]

    _expect_rejected(
        lambda: bridge.normalize_native_capture_input(
            {
                "schema": "court.office.native_capture.v1",
                "task_id": request["task_id"],
                "wave_id": request["wave_id"],
                "instance_id": request["instance_id"],
                "host_result": {"ok": True},
            }
        ),
        "caller host_result",
    )
    _expect_rejected(
        lambda: bridge.normalize_native_capture_input(
            {
                "schema": "court.office.native_capture.v1",
                "task_id": request["task_id"],
                "wave_id": request["wave_id"],
                "instance_id": request["instance_id"],
                "trace_path": "outside.jsonl",
            }
        ),
        "caller trace_path",
    )
    _runtime_request_builder_fixture()
    from installed_identity_fixture import write_skill
    with tempfile.TemporaryDirectory(prefix='native-bridge-installed-identity-') as tmp:
        fixture_root = Path(tmp)
        write_skill(fixture_root)
        original_builder = court_runtime.build_preload_manifest
        with patch.object(court_runtime, 'build_preload_manifest',
                          side_effect=lambda *a, **k: original_builder(*a, **{**k, 'skill_root': fixture_root})), \
                patch.object(court_runtime, 'skill_root', return_value=fixture_root):
            _runtime_host_message_fixture()
    _caller_guard_fixture()

    session_id = "019f4eb0-38e7-7760-bbc9-77a030b7cf0e"
    environment = {"CODEX_THREAD_ID": "root-native-bridge", "CODEX_SESSION_ID": session_id}
    with tempfile.TemporaryDirectory(prefix="court-native-bridge-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(home, session_id=session_id, marker=marker, invocation=result["host_invocation"])
        captured = bridge.capture_current_native_delivery(
            request,
            execution=execution,
            p00_context=p00_context,
            environment=environment,
            codex_home=home,
        )
        receipt = captured["native_host_action_receipt"]
        assert isinstance(receipt, dict)
        assert receipt["schema"] == "court.native_host_action_receipt.v1"
        assert receipt["host_action"] == "spawn"
        assert captured["host_instance_id"] == "gongbu-host-agent-01"
        serialized = json.dumps(captured, ensure_ascii=False)
        assert "message" not in serialized

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-legacy-thread-reject-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(home, session_id=session_id, marker=marker, invocation=result["host_invocation"])
        _expect_rejected(
            lambda: bridge.capture_current_native_delivery(
                request,
                execution=execution,
                p00_context=p00_context,
                environment={"CODEX_THREAD_ID": "different-legacy-thread", "CODEX_SESSION_ID": session_id},
                codex_home=home,
            ),
            "legacy thread metadata mismatch",
        )

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-reject-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            marker=marker,
            invocation=result["host_invocation"],
            argument_overrides={"message": str(result["host_message"]) + " override"},
        )
        _expect_rejected(
            lambda: bridge.capture_current_native_delivery(
                request,
                execution=execution,
                p00_context=p00_context,
                environment=environment,
                codex_home=home,
            ),
            "same marker different message",
        )

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-reject-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            marker=marker,
            invocation=result["host_invocation"],
            argument_overrides={"task_name": "gongbu_override_target"},
        )
        _expect_rejected(
            lambda: bridge.capture_current_native_delivery(
                request,
                execution=execution,
                p00_context=p00_context,
                environment=environment,
                codex_home=home,
            ),
            "same marker different task target",
        )

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-reject-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            marker=marker,
            invocation=result["host_invocation"],
            argument_overrides={"agent_type": "hubu"},
        )
        _expect_rejected(
            lambda: bridge.capture_current_native_delivery(
                request,
                execution=execution,
                p00_context=p00_context,
                environment=environment,
                codex_home=home,
            ),
            "same marker different role",
        )

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-reject-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            marker=marker,
            invocation=result["host_invocation"],
            output_only_task_name=True,
        )
        _expect_rejected(
            lambda: bridge.capture_current_native_delivery(
                request,
                execution=execution,
                p00_context=p00_context,
                environment=environment,
                codex_home=home,
            ),
            "host identity unavailable",
        )

    canonical_leaf = result["host_invocation"]["arguments"]["task_name"]
    canonical_context = {
        "case_session_id": session_id,
        "semantic_epoch": request["semantic_epoch"],
        "trusted_parent_paths": [{"path": "/root", "kind": "taizi_root", "thread_id": session_id}],
    }
    with tempfile.TemporaryDirectory(prefix="court-native-bridge-canonical-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            marker=marker,
            invocation=result["host_invocation"],
            output_only_task_name=True,
            host_task_id="/root/" + str(canonical_leaf),
        )
        canonical_capture = bridge.capture_current_native_delivery(
            request,
            execution=execution,
            p00_context=p00_context,
            identity_context=canonical_context,
            environment={"CODEX_THREAD_ID": "child-thread-not-session", "CODEX_SESSION_ID": session_id},
            codex_home=home,
        )
        canonical_receipt = canonical_capture["native_host_action_receipt"]
        assert canonical_receipt["host_identity_kind"] == "canonical_agent_path"
        assert canonical_receipt["host_thread_id"] is None
        assert canonical_receipt["host_task_id"] == "/root/" + str(canonical_leaf)
        assert canonical_receipt["trace_issuer_thread_id"] is None
        assert canonical_receipt["trace_reader_thread_id"] == "child-thread-not-session"
        assert canonical_capture["trace_issuer_thread_id"] is None
        assert canonical_capture["trace_reader_thread_id"] == "child-thread-not-session"

    for label, path, context in (
        (
            "wrong leaf",
            "/root/foreign_leaf",
            canonical_context,
        ),
        (
            "wrong parent",
            "/root/untrusted_parent/" + str(canonical_leaf),
            canonical_context,
        ),
        (
            "wrong epoch",
            "/root/" + str(canonical_leaf),
            {**canonical_context, "semantic_epoch": int(request["semantic_epoch"]) + 1},
        ),
        (
            "case session mismatch",
            "/root/" + str(canonical_leaf),
            {**canonical_context, "case_session_id": "019f4eae-7c0c-71c3-b992-e4cd83f21ae8"},
        ),
    ):
        with tempfile.TemporaryDirectory(prefix="court-native-bridge-canonical-reject-") as temp_dir:
            home = Path(temp_dir)
            _write_trace(
                home,
                session_id=session_id,
                marker=marker,
                invocation=result["host_invocation"],
                output_only_task_name=True,
                host_task_id=path,
            )
            _expect_rejected(
                lambda context=context: bridge.capture_current_native_delivery(
                    request,
                    execution=execution,
                    p00_context=p00_context,
                    identity_context=context,
                    environment=environment,
                    codex_home=home,
                ),
                label,
            )

    shangshu_parent = "/root/shangshu_ready"
    shangshu_context = {
        "case_session_id": session_id,
        "semantic_epoch": request["semantic_epoch"],
        "trusted_parent_paths": [
            {"path": shangshu_parent, "kind": "same_case_ready_shangshu"}
        ],
    }
    with tempfile.TemporaryDirectory(prefix="court-native-bridge-canonical-shangshu-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            marker=marker,
            invocation=result["host_invocation"],
            output_only_task_name=True,
            host_task_id=shangshu_parent + "/" + str(canonical_leaf),
        )
        shangshu_capture = bridge.capture_current_native_delivery(
            request,
            execution=execution,
            p00_context=p00_context,
            identity_context=shangshu_context,
            environment=environment,
            codex_home=home,
        )
        assert shangshu_capture["native_host_action_receipt"]["trusted_parent_kind"] == "same_case_ready_shangshu"

    v1_result = bridge.native_request_result(
        request,
        execution=execution,
        p00_context=p00_context,
        agent_type="gongbu",
    )
    assert v1_result["host_invocation"]["arguments"]["agent_type"] == "gongbu"
    with tempfile.TemporaryDirectory(prefix="court-native-bridge-v1-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            marker=marker,
            invocation=v1_result["host_invocation"],
        )
        v1_capture = bridge.capture_current_native_delivery(
            request,
            execution=execution,
            p00_context=p00_context,
            agent_type="gongbu",
            environment=environment,
            codex_home=home,
        )
        assert v1_capture["office_command"] == "start"

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-v1-reject-") as temp_dir:
        home = Path(temp_dir)
        invocation = dict(v1_result["host_invocation"])
        invocation["arguments"] = {
            key: value
            for key, value in invocation["arguments"].items()
            if key != "agent_type"
        }
        _write_trace(home, session_id=session_id, marker=marker, invocation=invocation)
        _expect_rejected(
            lambda: bridge.capture_current_native_delivery(
                request,
                execution=execution,
                p00_context=p00_context,
                agent_type="gongbu",
                environment=environment,
                codex_home=home,
            ),
            "v1 agent_type missing",
        )

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-v1-reject-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            marker=marker,
            invocation=v1_result["host_invocation"],
            argument_overrides={"agent_type": "hubu"},
        )
        _expect_rejected(
            lambda: bridge.capture_current_native_delivery(
                request,
                execution=execution,
                p00_context=p00_context,
                agent_type="gongbu",
                environment=environment,
                codex_home=home,
            ),
            "v1 agent_type wrong",
        )

    reuse = _request()
    reuse["compatible_live_instances"] = [
        {
            "host_task_id": "gongbu-host-task-02",
            "host_thread_id": "gongbu-host-thread-02",
            "host_instance_id": "gongbu-host-agent-02",
            "task_id": reuse["task_id"],
            "role": reuse["role"],
            "direct_superior": reuse["direct_superior"],
            "assignment": reuse["assignment"],
            "duty_scope": reuse["duty_scope"],
            "semantic_receipt": {
                "semantic_epoch": reuse["semantic_epoch"],
                "case_ref": dict(CASE_REF),
            },
            "lease_id": reuse["lease_id"],
            "write_set": reuse["write_set"],
            "role_ack": reuse["role_ack"],
            "context_utilization": 0.42,
            "status": "running",
        }
    ]
    reuse_p00_context = _p00_context(reuse)
    reuse_result = bridge.native_request_result(
        reuse,
        execution=execution,
        p00_context=reuse_p00_context,
    )
    reuse_marker = reuse_result["host_message_marker"]
    with tempfile.TemporaryDirectory(prefix="court-native-bridge-followup-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            marker=str(reuse_marker),
            tool_name="followup_task",
            invocation=reuse_result["host_invocation"],
            host_agent_id="gongbu-host-agent-02",
            host_thread_id="gongbu-host-thread-02",
            host_task_id="gongbu-host-task-02",
        )
        followed_up = bridge.capture_current_native_delivery(
            reuse,
            execution=execution,
            p00_context=reuse_p00_context,
            environment=environment,
            codex_home=home,
        )
        assert followed_up["office_command"] == "followup"
        assert followed_up["native_host_action_receipt"]["host_action"] == "followup"

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-send-input-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            marker=str(reuse_marker),
            invocation={
                **reuse_result["host_invocation"],
                "tool_name": "send_input",
            },
            host_agent_id="gongbu-host-agent-02",
            host_thread_id="gongbu-host-thread-02",
            host_task_id="gongbu-host-task-02",
        )
        sent = bridge.capture_current_native_delivery(
            reuse,
            execution=execution,
            p00_context=reuse_p00_context,
            environment=environment,
            codex_home=home,
        )
        assert sent["office_command"] == "followup"

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-reject-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            marker=str(reuse_marker),
            invocation=reuse_result["host_invocation"],
            argument_overrides={"target": "foreign-native-target"},
            host_agent_id="gongbu-host-agent-02",
            host_thread_id="gongbu-host-thread-02",
            host_task_id="gongbu-host-task-02",
        )
        _expect_rejected(
            lambda: bridge.capture_current_native_delivery(
                reuse,
                execution=execution,
                p00_context=reuse_p00_context,
                environment=environment,
                codex_home=home,
            ),
            "same marker different followup target",
        )

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-followup-no-issuer-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            marker=str(reuse_marker),
            invocation=reuse_result["host_invocation"],
            output_only_task_name=True,
            host_task_id="/root/gongbu_followup_handle",
        )
        _expect_rejected(
            lambda: bridge.capture_current_native_delivery(
                reuse,
                execution=execution,
                p00_context=reuse_p00_context,
                identity_context=canonical_context,
                environment=environment,
                codex_home=home,
            ),
            "followup issuer unavailable",
        )

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-reject-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(
            home,
            session_id=session_id,
            meta_session_id="019f4eae-7c0c-71c3-b992-e4cd83f21ae8",
            marker=marker,
        )
        _expect_rejected(
            lambda: bridge.capture_current_native_delivery(
                request,
                execution=execution,
                p00_context=p00_context,
                environment=environment,
                codex_home=home,
            ),
            "session metadata mismatch",
        )

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-reject-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(home, session_id=session_id, marker=marker, tool_name="unknown_host_shape")
        _expect_rejected(
            lambda: bridge.capture_current_native_delivery(
                request,
                execution=execution,
                p00_context=p00_context,
                environment=environment,
                codex_home=home,
            ),
            "unknown tool shape",
        )

    with tempfile.TemporaryDirectory(prefix="court-native-bridge-reject-") as temp_dir:
        home = Path(temp_dir)
        _write_trace(home, session_id=session_id, marker=marker, include_marker=False)
        _expect_rejected(
            lambda: bridge.capture_current_native_delivery(
                request,
                execution=execution,
                p00_context=p00_context,
                environment=environment,
                codex_home=home,
            ),
            "missing request marker",
        )

    print("COURT_NATIVE_BRIDGE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
