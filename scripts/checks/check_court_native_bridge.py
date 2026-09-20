"""Focused safety checks for the current-session native host bridge."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sys
import tempfile
import unittest
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
from court_native_host_dispatch import (
    native_request_reference,
    validate_native_host_action_receipt,
)
from court_office_bootstrap import (
    OFFICE_ASSIGNMENT_IDENTITIES,
    ROOT as OFFICE_ROOT,
    build_preload_manifest,
)
from court_office_config import (
    ENTRY_PRELOAD_BUDGET_BYTES,
    ORDINARY_NATIVE_REQUIRED_HEADROOM_BYTES,
)

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


def _write_child_session_meta(
    home: Path,
    *,
    child_thread_id: str,
    session_id: str,
    agent_role: str | None,
) -> None:
    sessions = home / "sessions" / "2026" / "09"
    sessions.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": child_thread_id,
        "session_id": session_id,
        "thread_id": child_thread_id,
        "parent_thread_id": "root-native-bridge",
        "thread_source": "subagent",
        "source": {
            "subagent": {
                "thread_spawn": {
                    "parent_thread_id": "root-native-bridge",
                    "agent_role": agent_role,
                }
            }
        },
    }
    (sessions / f"rollout-{child_thread_id}.jsonl").write_text(
        json.dumps({"type": "session_meta", "payload": payload}) + "\n",
        encoding="utf-8",
    )


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
    selector = {
        "schema": "court.office.native_request.v1",
        "task_id": task_id,
        "wave_id": wave_id,
        "instance_id": instance_id,
        "spawn_agent_type_field": "visible",
    }
    try:
        normalized_selector = bridge.normalize_native_request_input(selector)
    except ValueError as exc:
        raise AssertionError(
            "native request selector must accept the legacy four fields plus "
            "spawn_agent_type_field=visible"
        ) from exc
    assert normalized_selector == selector
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
        def request_result_stub(
            _task, _admission, admitted_binding, request, *,
            spawn_agent_type_field=None,
        ):
            return bridge.native_request_result(
                request,
                execution=_execution(),
                p00_context=_p00_context(request),
                agent_type=(
                    admitted_binding["role"]
                    if spawn_agent_type_field == "visible"
                    else None
                ),
            )

        court_runtime.load_tasks = lambda: {task_id: task}  # type: ignore[assignment]
        court_runtime.events_for_task = lambda *_args, **_kwargs: [event]  # type: ignore[assignment]
        court_runtime.require_semantic_mutation_binding = lambda _task: None  # type: ignore[assignment]
        court_runtime._native_bridge_caller_guard = lambda *_args, **_kwargs: None  # type: ignore[assignment]
        court_runtime._native_bridge_request_result = request_result_stub  # type: ignore[assignment]
        bridge.current_host_identity = lambda **_kwargs: {  # type: ignore[assignment]
            "thread_id": "root-native-bridge",
            "session_id": "019f4eb0-38e7-7760-bbc9-77a030b7cf0e",
        }
        result = court_runtime.office_native_request(
            Namespace(**selector)
        )
        assert result["request"]["task_id"] == task_id
        assert result["request"]["admission_anchor"]["receipt_id"] == event["event_id"]
        assert result["expected_host_action"] == "spawn"
        invocation = result["host_invocation"]
        assert invocation["tool_name"] == "spawn_agent"
        arguments = invocation["arguments"]
        assert arguments["agent_type"] == binding["role"]
        assert not ({"model", "reasoning_effort"} & set(arguments))
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
    for authority in ("approval", "autonomous", "super"):
        selected = {"authority": authority, "behavior": "parallel"}
        bound = {**task, "case_binding": {**CASE_REF, "case_execution": selected}}
        reply = court_runtime._native_bridge_request_result(bound, admission, binding, request)
        assert json.loads(reply["host_message"])["execution"] == selected
    for selected in ({"authority": "super", "behavior": "serial"},
                     {"authority": "unknown", "behavior": "parallel"}):
        _expect_rejected(lambda: court_runtime._native_bridge_host_message_inputs(
            {**task, "case_binding": {**CASE_REF, "case_execution": selected}}, admission),
            "invalid native dispatch selection")
    _expect_rejected(lambda: court_runtime._prepare_explicit_office_admission(
        Namespace(requested_roles=["gongbu"])), "office admission role type")

    # Exercise the capture's actual start-request generator, not a hand-filled
    # lifecycle request that could hide an empty required-skill list.
    admitted_pool = court_runtime.public_context_budget_pool(task, request['wave_id'])
    admitted_pool['normalized_total_share'] = 100  # PowerShell JSON round trips 100.0 as 100.
    admission['context_budget_pool_ref'] = json.loads(json.dumps(admitted_pool))
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
    assert generated['context_budget_pool'] == admission['context_budget_pool_ref']
    assert generated['context_budget_pool'] is not admission['context_budget_pool_ref']

    # A capture-proved explicit model selection must survive the existing
    # capture -> office-start producer boundary unchanged.  The lifecycle
    # consumer, not a caller reconstruction, owns these values.
    model_selection = {
        'schema': 'court.codex.model_selection.v1',
        'selection_id': 'MEA-' + 'd' * 32,
        'source': 'current_user_explicit',
        'case_ref': dict(CASE_REF),
        'semantic_epoch': request['semantic_epoch'],
        'model': 'gpt-6-astra',
        'reasoning_effort': 'ultra',
    }
    host_model_binding = {
        'schema': 'court.host_model_execution_binding.v1',
        'selection_id': model_selection['selection_id'],
        'applied_spawn_fields': ['model', 'reasoning_effort'],
        'parent_turn_context': {
            'model': 'gpt-5.6-sol', 'effort': 'ultra',
            'trace_line': 2, 'turn_id': 'parent-turn-001',
        },
        'child_turn_context': {
            'model': 'gpt-6-astra', 'effort': 'ultra',
            'trace_line': 2, 'turn_id': 'child-turn-001',
        },
        'status': 'MATCHED',
    }
    explicit_admission = deepcopy(admission)
    explicit_admission['model_authorization_binding'] = deepcopy(model_selection)
    explicit_admission['model_routes'][request['instance_id']][
        'model_authorization_binding'
    ] = deepcopy(model_selection)
    explicit_capture = {
        'request_ref': native_request_reference(request),
        'native_host_action_receipt': {
            'model_authorization_binding': deepcopy(model_selection),
            'host_model_execution_binding': deepcopy(host_model_binding),
            'host_result': {
                'model_authorization_binding': deepcopy(model_selection),
                'host_model_execution_binding': deepcopy(host_model_binding),
            },
        },
        'model_authorization_binding': deepcopy(model_selection),
        'host_model_execution_binding': deepcopy(host_model_binding),
    }
    with patch.object(court_runtime, '_native_bridge_model_inputs', return_value={
        'assignment':'fixture', 'task_focus':'fixture', 'complexity':'low',
        'risk':'low', 'ambiguity':'low', 'transport':'codex'}), patch.object(
        court_runtime, 'public_dispatch_context_packet', return_value={}), patch.object(
        court_runtime, 'public_context_budget_pool', return_value={}), patch.object(
        court_runtime, '_revalidate_context_economy_start', return_value=None):
        explicit_start = court_runtime._native_bridge_start_request(
            task,
            explicit_admission,
            {**binding, 'instance_id':'gongbu#0001'},
            request,
            explicit_capture,
        )
    assert explicit_start['model_authorization_binding'] == model_selection
    assert explicit_start['host_model_execution_binding'] == host_model_binding
    assert explicit_start['model_authorization_binding'] is not model_selection
    assert explicit_start['host_model_execution_binding'] is not host_model_binding
    for missing in ('model_authorization_binding', 'host_model_execution_binding'):
        incomplete = deepcopy(explicit_capture)
        incomplete.pop(missing)
        with patch.object(court_runtime, '_native_bridge_model_inputs', return_value={
            'assignment':'fixture', 'task_focus':'fixture', 'complexity':'low',
            'risk':'low', 'ambiguity':'low', 'transport':'codex'}), patch.object(
            court_runtime, 'public_dispatch_context_packet', return_value={}), patch.object(
            court_runtime, 'public_context_budget_pool', return_value={}), patch.object(
            court_runtime, '_revalidate_context_economy_start', return_value=None):
            _expect_rejected(
                lambda: court_runtime._native_bridge_start_request(
                    task, explicit_admission,
                    {**binding, 'instance_id':'gongbu#0001'}, request, incomplete,
                ),
                f'missing {missing} accepted by start producer',
            )
    mismatched = deepcopy(explicit_capture)
    mismatched['host_model_execution_binding']['selection_id'] = 'MEA-' + 'e' * 32
    with patch.object(court_runtime, '_native_bridge_model_inputs', return_value={
        'assignment':'fixture', 'task_focus':'fixture', 'complexity':'low',
        'risk':'low', 'ambiguity':'low', 'transport':'codex'}), patch.object(
        court_runtime, 'public_dispatch_context_packet', return_value={}), patch.object(
        court_runtime, 'public_context_budget_pool', return_value={}), patch.object(
        court_runtime, '_revalidate_context_economy_start', return_value=None):
        _expect_rejected(
            lambda: court_runtime._native_bridge_start_request(
                task, explicit_admission,
                {**binding, 'instance_id':'gongbu#0001'}, request, mismatched,
            ),
            'mismatched model execution selection accepted by start producer',
        )

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


class NativeCapabilityContractTests(unittest.TestCase):
    child_thread_id = "019f4eb1-38e7-7760-bbc9-77a030b7cf0e"
    session_id = "019f4eb0-38e7-7760-bbc9-77a030b7cf0e"
    binding = {"role": "gongbu", "instance_id": "gongbu-native-0001"}

    @staticmethod
    def _admission(protocol: str) -> dict[str, object]:
        metadata: dict[str, object] = {"fork_turns": "none"}
        if protocol == "v1":
            metadata["agent_type"] = "gongbu"
        return {
            "selected_protocol": protocol,
            "model_routes": {
                "gongbu-native-0001": {
                    "transport": "codex",
                    "protocol": protocol,
                    "role": "gongbu",
                    "spawn_metadata": metadata,
                }
            },
        }

    @staticmethod
    def _model_selection(
        *,
        model: str | None,
        reasoning_effort: str | None,
        digit: str,
    ) -> dict[str, object]:
        return {
            "schema": "court.codex.model_selection.v1",
            "selection_id": "MEA-" + digit * 32,
            "source": "current_user_explicit",
            "case_ref": dict(CASE_REF),
            "semantic_epoch": 3,
            "model": model,
            "reasoning_effort": reasoning_effort,
        }

    @classmethod
    def _runtime_request_case(
        cls,
        selection: dict[str, object] | None = None,
        *,
        followup: bool = False,
    ) -> tuple[
        dict[str, object],
        dict[str, object],
        dict[str, object],
        dict[str, object],
    ]:
        request = _request()
        if followup:
            request["compatible_live_instances"] = [
                {
                    "host_task_id": "gongbu-host-task-02",
                    "host_thread_id": "gongbu-host-thread-02",
                    "host_instance_id": "gongbu-host-agent-02",
                    "task_id": request["task_id"],
                    "role": request["role"],
                    "direct_superior": request["direct_superior"],
                    "assignment": request["assignment"],
                    "duty_scope": request["duty_scope"],
                    "semantic_receipt": {
                        "semantic_epoch": request["semantic_epoch"],
                        "case_ref": dict(CASE_REF),
                    },
                    "lease_id": request["lease_id"],
                    "write_set": request["write_set"],
                    "role_ack": request["role_ack"],
                    "context_utilization": 0.42,
                    "status": "running",
                }
            ]
        route: dict[str, object] = {
            "transport": "codex",
            "protocol": "v2",
            "role": request["role"],
            "spawn_metadata": {"fork_turns": "none"},
        }
        admission: dict[str, object] = {
            "wave_id": request["wave_id"],
            "selected_protocol": "v2",
            "model_routes": {request["instance_id"]: route},
        }
        if selection is not None:
            route["model_authorization_binding"] = deepcopy(selection)
            admission["model_authorization_binding"] = deepcopy(selection)
        task: dict[str, object] = {
            "task_id": request["task_id"],
            **CASE_REF,
            "case_binding": MappingProxyType(
                {
                    **CASE_REF,
                    "case_execution": {
                        "authority": "super",
                        "behavior": "parallel",
                    },
                }
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
            "preload_sources": court_runtime._semantic_preload_sources(
                str(request["role"])
            ),
        }
        return task, admission, binding, request

    def test_model_effort_selector_capabilities_are_closed_and_value_free(self):
        base = {
            "schema": "court.office.native_request.v1",
            "task_id": "selector-model-capability-task",
            "wave_id": "selector-model-capability-wave",
            "instance_id": "gongbu-native-0001",
        }
        for model_capability in (None, "visible", "hidden"):
            for effort_capability in (None, "visible", "hidden"):
                selector = dict(base)
                if model_capability is not None:
                    selector["spawn_model_field"] = model_capability
                if effort_capability is not None:
                    selector["spawn_reasoning_effort_field"] = effort_capability
                with self.subTest(
                    model=model_capability,
                    effort=effort_capability,
                ):
                    self.assertEqual(
                        bridge.normalize_native_request_input(selector),
                        selector,
                    )
        for forbidden, value in (
            ("model", "gpt-6-astra"),
            ("reasoning_effort", "ultra"),
            ("service_tier", "priority"),
            ("selection_id", "MEA-" + "1" * 32),
            ("authorization_id", "MEA-" + "1" * 32),
            ("model_authorization_binding", {}),
            ("current_codex_model_selection", {}),
        ):
            with self.subTest(forbidden=forbidden), self.assertRaisesRegex(
                ValueError,
                "native_bridge:native_request_fields_invalid",
            ):
                bridge.normalize_native_request_input({**base, forbidden: value})
        for field in ("spawn_model_field", "spawn_reasoning_effort_field"):
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError,
                f"native_bridge:native_request_{field}_invalid",
            ):
                bridge.normalize_native_request_input({**base, field: "unknown"})

    def test_native_capture_selector_redeclares_model_effort_capabilities(self):
        base = {
            "schema": "court.office.native_capture.v1",
            "task_id": "selector-model-capture-task",
            "wave_id": "selector-model-capture-wave",
            "instance_id": "gongbu-native-0001",
        }
        for model_capability in (None, "visible", "hidden"):
            for effort_capability in (None, "visible", "hidden"):
                selector = dict(base)
                if model_capability is not None:
                    selector["spawn_model_field"] = model_capability
                if effort_capability is not None:
                    selector["spawn_reasoning_effort_field"] = effort_capability
                with self.subTest(
                    model=model_capability,
                    effort=effort_capability,
                ):
                    self.assertEqual(
                        bridge.normalize_native_capture_input(selector),
                        selector,
                    )
        for forbidden, value in (
            ("model", "gpt-6-astra"),
            ("reasoning_effort", "ultra"),
            ("service_tier", "priority"),
            ("selection_id", "MEA-" + "1" * 32),
            ("model_authorization_binding", {}),
        ):
            with self.subTest(forbidden=forbidden), self.assertRaisesRegex(
                ValueError,
                "native_bridge:native_capture_fields_invalid",
            ):
                bridge.normalize_native_capture_input({**base, forbidden: value})

    def test_unbound_model_capabilities_never_add_spawn_arguments(self):
        task, admission, binding, request = self._runtime_request_case()
        task_names: set[str] = set()
        for agent_capability in (None, "visible", "hidden"):
            for model_capability in (None, "visible", "hidden"):
                for effort_capability in (None, "visible", "hidden"):
                    kwargs: dict[str, object] = {}
                    if agent_capability is not None:
                        kwargs["spawn_agent_type_field"] = agent_capability
                    if model_capability is not None:
                        kwargs["spawn_model_field"] = model_capability
                    if effort_capability is not None:
                        kwargs["spawn_reasoning_effort_field"] = effort_capability
                    with self.subTest(
                        agent=agent_capability,
                        model=model_capability,
                        effort=effort_capability,
                    ):
                        result = court_runtime._native_bridge_request_result(
                            task,
                            admission,
                            binding,
                            request,
                            **kwargs,
                        )
                        arguments = result["host_invocation"]["arguments"]
                        self.assertFalse(
                            {"model", "reasoning_effort", "service_tier"}
                            & set(arguments)
                        )
                        task_names.add(arguments["task_name"])
        self.assertEqual(len(task_names), 1)

    def test_explicit_model_effort_and_pair_use_only_route_bound_exact_values(self):
        cases = (
            (
                "model-only",
                self._model_selection(
                    model="gpt-6-astra",
                    reasoning_effort=None,
                    digit="1",
                ),
                {"model": "gpt-6-astra"},
            ),
            (
                "effort-only",
                self._model_selection(
                    model=None,
                    reasoning_effort="ultra",
                    digit="2",
                ),
                {"reasoning_effort": "ultra"},
            ),
            (
                "model-and-effort",
                self._model_selection(
                    model="gpt-5.6-terra",
                    reasoning_effort="high",
                    digit="3",
                ),
                {"model": "gpt-5.6-terra", "reasoning_effort": "high"},
            ),
        )
        for label, selection, expected_values in cases:
            task, admission, binding, request = self._runtime_request_case(selection)
            task_names: set[str] = set()
            for agent_capability in ("visible", "hidden"):
                with self.subTest(label=label, agent=agent_capability):
                    result = court_runtime._native_bridge_request_result(
                        task,
                        admission,
                        binding,
                        request,
                        spawn_agent_type_field=agent_capability,
                        spawn_model_field="visible",
                        spawn_reasoning_effort_field="visible",
                    )
                    arguments = result["host_invocation"]["arguments"]
                    expected_keys = {
                        "task_name",
                        "fork_turns",
                        "message",
                        *expected_values,
                    }
                    if agent_capability == "visible":
                        expected_keys.add("agent_type")
                        self.assertEqual(arguments["agent_type"], "gongbu")
                    self.assertEqual(set(arguments), expected_keys)
                    for field, value in expected_values.items():
                        self.assertEqual(arguments[field], value)
                    self.assertNotIn("service_tier", arguments)
                    task_names.add(arguments["task_name"])
            self.assertEqual(len(task_names), 1)

            required_capabilities = []
            if selection["model"] is not None:
                required_capabilities.append(
                    (
                        "spawn_model_field",
                        "native_bridge:explicit_model_field_unavailable",
                    )
                )
            if selection["reasoning_effort"] is not None:
                required_capabilities.append(
                    (
                        "spawn_reasoning_effort_field",
                        "native_bridge:explicit_reasoning_effort_field_unavailable",
                    )
                )
            for field, error in required_capabilities:
                for unavailable in (None, "hidden"):
                    kwargs = {
                        "spawn_model_field": "visible",
                        "spawn_reasoning_effort_field": "visible",
                    }
                    if unavailable is None:
                        kwargs.pop(field)
                    else:
                        kwargs[field] = unavailable
                    with self.subTest(
                        label=label,
                        unavailable_field=field,
                        unavailable=unavailable,
                    ), self.assertRaisesRegex(ValueError, error):
                        court_runtime._native_bridge_request_result(
                            task,
                            admission,
                            binding,
                            request,
                            **kwargs,
                        )

    def test_followup_model_effort_capabilities_are_not_applicable(self):
        task, admission, binding, request = self._runtime_request_case(
            followup=True
        )
        control = court_runtime._native_bridge_request_result(
            task,
            admission,
            binding,
            request,
        )
        self.assertEqual(control["expected_host_action"], "followup")
        self.assertEqual(control["host_invocation"]["tool_name"], "followup_task")
        self.assertFalse(
            {"model", "reasoning_effort", "service_tier"}
            & set(control["host_invocation"]["arguments"])
        )
        for field in ("spawn_model_field", "spawn_reasoning_effort_field"):
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError,
                f"native_bridge:{field}_not_applicable",
            ):
                court_runtime._native_bridge_request_result(
                    task,
                    admission,
                    binding,
                    request,
                    **{field: "visible"},
                )

    def test_explicit_hidden_conflicts_with_legacy_v1_before_or_after_adaptation(self):
        v1 = self._admission("v1")
        conflict = "native_bridge:spawn_agent_type_field_protocol_conflict"
        with self.subTest(stage="route"), self.assertRaisesRegex(ValueError, conflict):
            court_runtime._native_bridge_bound_agent_type(
                v1, self.binding, spawn_agent_type_field="hidden"
            )
        with self.subTest(stage="adapter"):
            self.assertFalse(
                hasattr(court_runtime, "_native_bridge_apply_selector_capability"),
                "selector capability must have no second host-message rebuild path",
            )

    def test_complete_selector_capability_matrix(self):
        v1 = self._admission("v1")
        v2 = self._admission("v2")
        cases = (
            ("absent-v1", v1, None, "gongbu"),
            ("absent-v2", v2, None, None),
            ("visible-v1", v1, "visible", "gongbu"),
            ("visible-v2", v2, "visible", "gongbu"),
            ("hidden-v2", v2, "hidden", None),
        )
        for label, admission, capability, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(
                    court_runtime._native_bridge_bound_agent_type(
                        admission,
                        self.binding,
                        spawn_agent_type_field=capability,
                    ),
                    expected,
                )
        with self.assertRaisesRegex(
            ValueError,
            "native_bridge:spawn_agent_type_field_protocol_conflict",
        ):
            court_runtime._native_bridge_bound_agent_type(
                v1,
                self.binding,
                spawn_agent_type_field="hidden",
            )

    def _capture(
        self,
        *,
        actual_agent_type: str | None,
        expected_agent_type: str | None,
        child_agent_role: str | None,
        actual_argument: str = "exact",
        child_thread_id: str | None = None,
    ) -> dict[str, object]:
        observed_thread_id = child_thread_id or self.child_thread_id
        request = _request()
        native = bridge.native_request_result(
            request,
            execution=_execution(),
            p00_context=_p00_context(request),
            agent_type=actual_agent_type,
        )
        invocation = {
            **native["host_invocation"],
            "arguments": dict(native["host_invocation"]["arguments"]),
        }
        if actual_argument == "missing":
            invocation["arguments"].pop("agent_type", None)
        elif actual_argument == "foreign":
            invocation["arguments"]["agent_type"] = "hubu"
        with tempfile.TemporaryDirectory(prefix="court-native-capability-") as temp_dir:
            home = Path(temp_dir)
            _write_trace(
                home,
                session_id=self.session_id,
                marker=str(native["host_message_marker"]),
                invocation=invocation,
                host_thread_id=observed_thread_id,
            )
            _write_child_session_meta(
                home,
                child_thread_id=observed_thread_id,
                session_id=self.session_id,
                agent_role=child_agent_role,
            )
            return bridge.capture_current_native_delivery(
                request,
                execution=_execution(),
                p00_context=_p00_context(request),
                agent_type=expected_agent_type,
                environment={
                    "CODEX_THREAD_ID": "root-native-bridge",
                    "CODEX_SESSION_ID": self.session_id,
                },
                codex_home=home,
            )

    def test_visible_capture_rejects_null_child_role_after_exact_role_control(self):
        exact = self._capture(
            actual_agent_type="gongbu",
            expected_agent_type="gongbu",
            child_agent_role="gongbu",
        )
        self.assertEqual(exact["host_thread_id"], self.child_thread_id)
        with self.assertRaisesRegex(
            ValueError,
            "native_bridge:child_session_agent_role_mismatch",
        ):
            self._capture(
                actual_agent_type="gongbu",
                expected_agent_type="gongbu",
                child_agent_role=None,
            )

    def test_office_start_templates_capture_proved_explicit_model_ack(self):
        manifest = asdict(
            build_preload_manifest(
                "gongbu",
                court_code=CASE_REF["court_code"],
            )
        )
        for label, requested_model, requested_effort, policy in (
            (
                "model-only",
                "gpt-6-astra",
                None,
                "explicit_model_host_default_effort",
            ),
            (
                "effort-only",
                None,
                "high",
                "inherit_model_explicit_effort",
            ),
            (
                "pair",
                "gpt-6-astra",
                "ultra",
                "explicit_model_and_effort",
            ),
        ):
            with self.subTest(label=label):
                digit = {"model-only": "1", "effort-only": "2", "pair": "3"}[label]
                selection = {
                    "schema": "court.codex.model_selection.v1",
                    "selection_id": "MEA-" + digit * 32,
                    "source": "current_user_explicit",
                    "case_ref": dict(CASE_REF),
                    "semantic_epoch": CASE_REF["charter_revision"],
                    "model": requested_model,
                    "reasoning_effort": requested_effort,
                }
                applied = [
                    field
                    for field, value in (
                        ("model", requested_model),
                        ("reasoning_effort", requested_effort),
                    )
                    if value is not None
                ]
                child_model = requested_model or "gpt-5.6-sol"
                child_effort = (
                    requested_effort
                    if requested_effort is not None
                    else ("low" if requested_model is not None else "ultra")
                )
                host_binding = {
                    "schema": "court.host_model_execution_binding.v1",
                    "selection_id": selection["selection_id"],
                    "applied_spawn_fields": applied,
                    "parent_turn_context": {
                        "model": "gpt-5.6-sol", "effort": "ultra",
                        "trace_line": 2, "turn_id": "parent-turn-001",
                    },
                    "child_turn_context": {
                        "model": child_model, "effort": child_effort,
                        "trace_line": 2, "turn_id": "child-turn-001",
                    },
                    "status": "MATCHED",
                }
                record = {
                    "semantic_epoch": CASE_REF["charter_revision"],
                    "case_ref": dict(CASE_REF),
                    "checkpoint_id": "SC-NATIVE-BRIDGE-01",
                    "dispatch_uid": DISPATCH_UID,
                    "attempt": 1,
                    "role": "gongbu",
                    "office_instance_kind": "child_agent",
                    "office_instance_id": "gongbu#0001",
                    "carrier_proof": {"agent_id": "gongbu-native-01"},
                    "native_host_request_ref": _request()["case_ref"],
                    "preload_manifest": manifest,
                    "model_route": {
                        "model_route_id": "cmr-explicit1",
                        "inheritance_policy": "inherit_main_thread_model_reserved_schema",
                        "model_override_applied": False,
                        "model_authorization_binding": selection,
                        "host_model_execution_binding": host_binding,
                    },
                }
                payload = {
                    "office_instance": record,
                    "receipt": {"action": "start"},
                    "event": {"action": "agent_start"},
                }
                with patch.object(
                    court_runtime, "_prepare_office_start_args", return_value=None
                ), patch.object(
                    court_runtime, "agent_start", return_value=object()
                ), patch.object(
                    court_runtime,
                    "_office_transition_payload",
                    return_value=payload,
                ):
                    result = court_runtime.office_start(
                        Namespace(
                            task_id="native-bridge-task",
                            agent_id="gongbu-native-01",
                            actor="shangshu",
                        )
                    )
                template = result["preload_ack_request"]
                self.assertEqual(
                    template["model_selection_id"], selection["selection_id"]
                )
                self.assertEqual(template["active_model"], child_model)
                self.assertEqual(
                    template["active_reasoning_effort"], child_effort
                )
                self.assertEqual(template["model_override_applied"], "YES")
                self.assertEqual(template["inheritance_policy"], policy)

    def test_capture_capability_evidence_and_fail_closed_matrix(self):
        visible = self._capture(
            actual_agent_type="gongbu",
            expected_agent_type="gongbu",
            child_agent_role="gongbu",
        )
        hidden = self._capture(
            actual_agent_type=None,
            expected_agent_type=None,
            child_agent_role=None,
        )
        for captured, capability, role in (
            (visible, "visible", "gongbu"),
            (hidden, "hidden", None),
        ):
            with self.subTest(capability=capability, surface="capture"):
                self.assertEqual(
                    captured["observed_spawn_agent_type_field"], capability
                )
                self.assertEqual(captured["observed_child_agent_role"], role)
            host_result = captured["native_host_action_receipt"]["host_result"]
            receipt = captured["native_host_action_receipt"]
            with self.subTest(capability=capability, surface="receipt"):
                for surface in (receipt, host_result):
                    self.assertEqual(
                        surface.get("observed_spawn_agent_type_field"), capability
                    )
                    self.assertEqual(surface.get("observed_child_agent_role"), role)
                if capability == "visible":
                    self.assertEqual(receipt["request"]["role"], role)
                    self.assertEqual(receipt["role"], role)
            validate_native_host_action_receipt(
                receipt,
                expected=_request(),
                replay_guard=set(),
            )
        with self.assertRaisesRegex(
            ValueError,
            "native_bridge:child_session_agent_role_mismatch",
        ):
            self._capture(
                actual_agent_type="gongbu",
                expected_agent_type="gongbu",
                child_agent_role="hubu",
            )
        for actual, expected, role in (
            ("gongbu", None, "gongbu"),
            (None, "gongbu", None),
        ):
            with self.subTest(drift=(actual, expected)), self.assertRaises(ValueError):
                self._capture(
                    actual_agent_type=actual,
                    expected_agent_type=expected,
                    child_agent_role=role,
                )
        for actual_argument in ("missing", "foreign"):
            with self.subTest(actual_argument=actual_argument), self.assertRaises(ValueError):
                self._capture(
                    actual_agent_type="gongbu",
                    expected_agent_type="gongbu",
                    child_agent_role="gongbu",
                    actual_argument=actual_argument,
                )

    def test_receipt_observed_capability_layers_and_visible_uuid_fail_closed(self):
        visible = self._capture(
            actual_agent_type="gongbu",
            expected_agent_type="gongbu",
            child_agent_role="gongbu",
        )
        receipt = visible["native_host_action_receipt"]
        tampered_receipts = []
        for layer, field in (
            ("top", "observed_spawn_agent_type_field"),
            ("top", "observed_child_agent_role"),
            ("host_result", "observed_spawn_agent_type_field"),
            ("host_result", "observed_child_agent_role"),
        ):
            tampered = deepcopy(receipt)
            target = tampered if layer == "top" else tampered[layer]
            target.pop(field, None)
            tampered_receipts.append((layer, "missing_" + field, tampered))
        for layer, field, value in (
            ("top", "observed_spawn_agent_type_field", None),
            ("top", "observed_child_agent_role", "hubu"),
            ("host_result", "observed_spawn_agent_type_field", None),
            ("host_result", "observed_child_agent_role", "hubu"),
            ("request", "role", "hubu"),
        ):
            tampered = deepcopy(receipt)
            target = tampered if layer == "top" else tampered[layer]
            target[field] = value
            tampered_receipts.append((layer, field, tampered))
        for layer, field, tampered in tampered_receipts:
            with self.subTest(layer=layer, field=field), self.assertRaises(ValueError):
                validate_native_host_action_receipt(
                    tampered,
                    expected=_request(),
                    replay_guard=set(),
                )
        with self.assertRaises(ValueError):
            self._capture(
                actual_agent_type="gongbu",
                expected_agent_type="gongbu",
                child_agent_role="gongbu",
                child_thread_id="visible-child-not-a-uuid",
            )

    def test_visible_hidden_spawn_shape_and_trace_reserved_fields_are_stable(self):
        request = _request()
        hidden = bridge.native_request_result(
            request,
            execution=_execution(),
            p00_context=_p00_context(request),
        )
        visible = bridge.native_request_result(
            request,
            execution=_execution(),
            p00_context=_p00_context(request),
            agent_type="gongbu",
        )
        hidden_arguments = hidden["host_invocation"]["arguments"]
        visible_arguments = visible["host_invocation"]["arguments"]
        self.assertEqual(hidden_arguments["task_name"], visible_arguments["task_name"])
        forbidden = {"model", "reasoning_effort", "service_tier", "set_thread_title"}
        for result, arguments in ((hidden, hidden_arguments), (visible, visible_arguments)):
            self.assertFalse(forbidden & set(arguments))
            self.assertEqual(result["host_invocation"]["tool_name"], "spawn_agent")
        visible_capture = self._capture(
            actual_agent_type="gongbu",
            expected_agent_type="gongbu",
            child_agent_role="gongbu",
        )
        hidden_capture = self._capture(
            actual_agent_type=None,
            expected_agent_type=None,
            child_agent_role=None,
        )
        for captured in (visible_capture, hidden_capture):
            self.assertFalse(forbidden & set(captured["trace"]))
            self.assertNotEqual(captured["trace"]["tool_name"], "set_thread_title")

    def test_followup_rejects_spawn_agent_type_capability(self):
        reuse = _request()
        reuse["compatible_live_instances"] = [{
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
        }]
        control = bridge.native_request_result(
            reuse,
            execution=_execution(),
            p00_context=_p00_context(reuse),
        )
        self.assertEqual(control["expected_host_action"], "followup")
        with self.assertRaisesRegex(
            ValueError,
            "native_bridge:spawn_agent_type_field_not_applicable",
        ):
            bridge.native_request_result(
                reuse,
                execution=_execution(),
                p00_context=_p00_context(reuse),
                agent_type="gongbu",
            )

    def test_explicit_model_followup_reuses_only_same_matched_authorization(self):
        selection = self._model_selection(
            model="gpt-6-astra",
            reasoning_effort="ultra",
            digit="7",
        )
        task, admission, binding, request = self._runtime_request_case(
            selection,
            followup=True,
        )
        host_binding = {
            "schema": "court.host_model_execution_binding.v1",
            "selection_id": selection["selection_id"],
            "applied_spawn_fields": ["model", "reasoning_effort"],
            "parent_turn_context": {
                "model": "gpt-5.6-sol", "effort": "ultra",
                "trace_line": 2, "turn_id": "parent-turn-001",
            },
            "child_turn_context": {
                "model": "gpt-6-astra", "effort": "ultra",
                "trace_line": 2, "turn_id": "child-turn-001",
            },
            "status": "MATCHED",
        }
        task["agents"] = {
            "gongbu-live": {
                "role": "gongbu",
                "office_instance_id": binding["instance_id"],
                "model_authorization_binding": deepcopy(selection),
                "host_model_execution_binding": deepcopy(host_binding),
                "model_selection_id": selection["selection_id"],
                "status": "running",
                "release_status": "active",
            }
        }
        result = court_runtime._native_bridge_request_result(
            task,
            admission,
            binding,
            request,
        )
        self.assertEqual(result["expected_host_action"], "followup")
        self.assertIsNone(
            court_runtime._native_bridge_capture_model_authorization_binding(
                admission,
                binding,
                request,
            )
        )
        self.assertFalse(
            {"model", "reasoning_effort", "service_tier"}
            & set(result["host_invocation"]["arguments"])
        )
        stale_task = {**task, "agents": deepcopy(task["agents"])}
        stale_task["agents"]["gongbu-live"]["model_selection_id"] = (
            "MEA-" + "8" * 32
        )
        with self.assertRaisesRegex(
            ValueError,
            "native_bridge:followup_model_authorization_mismatch",
        ):
            court_runtime._native_bridge_request_result(
                stale_task,
                admission,
                binding,
                request,
            )

    def test_real_startup_inclusive_native_entry_budget_stays_at_20k(self):
        request = _request()
        native = bridge.native_request_result(
            request,
            execution=_execution(),
            p00_context=_p00_context(request),
        )
        manifest = build_preload_manifest("gongbu")
        startup = "references/court-normal-startup.md"
        material_bytes = {
            "court_skill_bytes": (OFFICE_ROOT / manifest.court_skill_path).stat().st_size,
            "startup_guide_bytes": (OFFICE_ROOT / startup).stat().st_size,
            "profile_bytes": (OFFICE_ROOT / manifest.profile_source).stat().st_size,
            "dossier_bytes": (OFFICE_ROOT / manifest.dossier_path).stat().st_size,
        }
        host_input_bytes = len(native["host_message"].encode("utf-8"))
        actual_total = sum(material_bytes.values()) + host_input_bytes
        self.assertEqual(ENTRY_PRELOAD_BUDGET_BYTES, 20 * 1024)
        self.assertLessEqual(
            actual_total,
            ENTRY_PRELOAD_BUDGET_BYTES,
            f"startup-inclusive native input exceeds the fixed entry budget: {actual_total}",
        )
        binding = {
            "role": "gongbu",
            "office_instance_kind": "child_agent",
            "preload_sources": court_runtime._semantic_preload_sources("gongbu"),
        }
        self.assertEqual(
            binding["preload_sources"]["startup_guide_path"],
            startup,
        )
        measured = court_runtime._native_bridge_preload_input_budget(
            binding,
            native["host_message"],
        )
        self.assertEqual(measured["startup_guide_bytes"], material_bytes["startup_guide_bytes"])
        self.assertEqual(measured["host_input_bytes"], host_input_bytes)
        self.assertEqual(measured["total_bytes"], actual_total)
        self.assertEqual(measured["limit_bytes"], 20 * 1024)

    def test_native_role_ack_sources_include_exact_installed_startup(self):
        preload = court_runtime._semantic_preload_sources("gongbu")
        sources = court_runtime._native_role_ack_sources(preload)
        expected = str(
            (OFFICE_ROOT / "references" / "court-normal-startup.md").resolve()
        )
        self.assertEqual(
            sources.get("startup_guide_path"),
            expected,
            "native role acknowledgement omitted trusted installed startup path",
        )

    def test_all_fourteen_roles_fit_real_startup_inclusive_native_budget(self):
        self.assertEqual(len(OFFICE_ASSIGNMENT_IDENTITIES), 14)
        self.assertEqual(ENTRY_PRELOAD_BUDGET_BYTES, 20 * 1024)
        ordinary_roles = {
            "zhongshu", "menxia", "shangshu",
            "libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu",
        }
        table = {}
        for role in OFFICE_ASSIGNMENT_IDENTITIES:
            manifest = build_preload_manifest(role)
            instance_id = f"{role}-native-budget-0001"
            request = _request()
            request.update(
                role=role,
                instance_id=instance_id,
                direct_superior=manifest.direct_superior,
                role_ack={
                    "role": role,
                    "direct_superior": manifest.direct_superior,
                    **court_runtime._native_role_ack_sources(
                        court_runtime._semantic_preload_sources(role)
                    ),
                },
                office_capsule_ref=office_capsule_reference(
                    CASE_REF, role, instance_id, ISSUED_AT
                ),
                compatible_live_instances=[],
            )
            table[role] = {}
            for capability, agent_type in (("hidden", None), ("visible", role)):
                native = bridge.native_request_result(
                    request,
                    execution=_execution(),
                    p00_context=_p00_context(request),
                    agent_type=agent_type,
                )
                binding = {
                    "role": role,
                    "office_instance_kind": "child_agent",
                    "preload_sources": court_runtime._semantic_preload_sources(role),
                }
                measured = court_runtime._native_bridge_preload_input_budget(
                    binding,
                    native["host_message"],
                )
                headroom = ENTRY_PRELOAD_BUDGET_BYTES - measured["total_bytes"]
                table[role][capability] = {
                    "skill": measured["court_skill_bytes"],
                    "startup": measured["startup_guide_bytes"],
                    "profile": measured["profile_bytes"],
                    "dossier": measured["dossier_bytes"],
                    "host_input": measured["host_input_bytes"],
                    "total": measured["total_bytes"],
                    "headroom": headroom,
                }
                with self.subTest(role=role, capability=capability):
                    self.assertLessEqual(
                        measured["total_bytes"],
                        ENTRY_PRELOAD_BUDGET_BYTES,
                        json.dumps(table[role][capability], ensure_ascii=False, sort_keys=True),
                    )
                    if role in ordinary_roles:
                        self.assertGreaterEqual(
                            headroom,
                            ORDINARY_NATIVE_REQUIRED_HEADROOM_BYTES,
                            json.dumps(table[role][capability], ensure_ascii=False, sort_keys=True),
                        )
                    self.assertEqual(measured["limit_bytes"], 20 * 1024)
        self.assertEqual(set(table), set(OFFICE_ASSIGNMENT_IDENTITIES))


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
        startup_fixture = fixture_root / "references" / "court-normal-startup.md"
        startup_fixture.parent.mkdir(parents=True, exist_ok=True)
        startup_fixture.write_text("# Isolated startup fixture\n", encoding="utf-8")
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

    capability_suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        NativeCapabilityContractTests
    )
    if not unittest.TextTestRunner(verbosity=1).run(capability_suite).wasSuccessful():
        return 1

    from checks import check_native_opaque_capture
    suite = unittest.defaultTestLoader.loadTestsFromModule(check_native_opaque_capture)
    if not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful():
        return 1
    print("COURT_NATIVE_BRIDGE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
