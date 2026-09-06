"""Fail-closed current-session evidence adapter for native court host delivery.

The host performs the actual collaboration action.  This adapter never accepts
a caller-supplied host result or trace path: it reconstructs a receipt only from
the current Codex session metadata after a matching native host action appears
there.  It deliberately exposes no MCP-facing surface.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping

from court_native_host_dispatch import (
    native_request_reference,
    native_task_suffix,
    dispatch_native_host_action,
    normalize_native_host_dispatch_request,
    select_native_host_action,
)
from court_native_identity import canonical_agent_path_identity
from court_native_trace import (bind_opaque_spawn, is_opaque_message, spawn_activity,
                                skill_read_order, NativeEvidencePending)


NATIVE_REQUEST_INPUT_SCHEMA = "court.office.native_request.v1"
NATIVE_REQUEST_RESULT_SCHEMA = "court.office.native_request.result.v1"
NATIVE_CAPTURE_INPUT_SCHEMA = "court.office.native_capture.v1"
NATIVE_CAPTURE_RESULT_SCHEMA = "court.office.native_capture.result.v1"
HOST_MESSAGE_SCHEMA = "court.native_host_message.v1"
HOST_MARKER_PREFIX = "COURT_NATIVE_REQUEST="
TRACE_MAX_BYTES = 64 * 1024 * 1024
TRACE_MAX_LINES = 20_000
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_SPAWN_TOOL_NAMES = frozenset({"spawn_agent", "collaboration.spawn_agent"})
_FOLLOWUP_TOOL_NAMES = frozenset(
    {
        "followup_task",
        "send_input",
        "collaboration.followup_task",
        "collaboration.send_input",
    }
)
_CALL_TYPES = frozenset({"function_call", "tool_call", "custom_tool_call"})
_OUTPUT_TYPES = frozenset(
    {"function_call_output", "tool_result", "custom_tool_call_output"}
)


def _text(value: object, field: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str):
        raise ValueError(f"native_bridge:{field}_invalid")
    text = value.strip()
    if not text or len(text) > maximum or "\x00" in text:
        raise ValueError(f"native_bridge:{field}_invalid")
    return text


def _input(value: object, *, schema: str, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "task_id",
        "wave_id",
        "instance_id",
    }:
        raise ValueError(f"native_bridge:{label}_fields_invalid")
    if value.get("schema") != schema:
        raise ValueError(f"native_bridge:{label}_schema_invalid")
    return {
        "schema": schema,
        "task_id": _text(value.get("task_id"), f"{label}.task_id"),
        "wave_id": _text(value.get("wave_id"), f"{label}.wave_id"),
        "instance_id": _text(value.get("instance_id"), f"{label}.instance_id").lower(),
    }


def normalize_native_request_input(value: object) -> dict[str, str]:
    """Accept only task/admission identity selectors for a request build."""

    return _input(value, schema=NATIVE_REQUEST_INPUT_SCHEMA, label="native_request")


def normalize_native_capture_input(value: object) -> dict[str, str]:
    """Reject caller-provided host results, ids, paths, and trace selectors."""

    return _input(value, schema=NATIVE_CAPTURE_INPUT_SCHEMA, label="native_capture")


def host_message_marker(request: object) -> str:
    normalized = normalize_native_host_dispatch_request(request)
    return HOST_MARKER_PREFIX + json.dumps(
        native_request_reference(normalized), ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    )


def _message_context(
    request: Mapping[str, object],
    value: object,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("native_bridge:p00_context_invalid")
    fields = (
        "schema",
        "semantic_epoch",
        "case_ref",
        "semantic_receipt_id",
        "fork_context",
        "context_mode",
        "pointers",
    )
    if any(field not in value for field in fields):
        raise ValueError("native_bridge:p00_context_invalid")
    if (
        value.get("schema") != "court.semantic.dispatch_context_packet.v1"
        or value.get("semantic_epoch") != request.get("semantic_epoch")
        or value.get("case_ref") != request.get("case_ref")
        or value.get("fork_context") != "none"
        or value.get("context_mode") != "bounded"
    ):
        raise ValueError("native_bridge:p00_context_binding_mismatch")
    pointers = value.get("pointers")
    if not isinstance(pointers, (list, tuple)) or not pointers:
        raise ValueError("native_bridge:p00_paths_invalid")
    normalized_pointers: list[dict[str, object]] = []
    for pointer in pointers:
        if not isinstance(pointer, Mapping) or set(pointer) not in (
            {"path", "case_ref"}, {"path", "plan_ref"}
        ):
            raise ValueError("native_bridge:p00_paths_invalid")
        field = "plan_ref" if "plan_ref" in pointer else "case_ref"
        reference = pointer[field]
        if (not isinstance(reference, Mapping)
                or any(reference.get(key) != val for key, val in request["case_ref"].items())):
            raise ValueError("native_bridge:p00_path_case_mismatch")
        normalized_pointers.append(
            {
                "path": _text(pointer.get("path"), "p00.path", maximum=512),
                field: deepcopy(dict(reference)),
            }
        )
    return {
        "schema": "court.semantic.dispatch_context_packet.v1",
        "semantic_epoch": request["semantic_epoch"],
        "case_ref": deepcopy(request["case_ref"]),
        "semantic_receipt_id": _text(
            value.get("semantic_receipt_id"), "p00.semantic_receipt_id", maximum=256
        ),
        "fork_context": "none",
        "context_mode": "bounded",
        "pointers": normalized_pointers,
    }


def _execution(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"authority", "behavior"}:
        raise ValueError("native_bridge:execution_invalid")
    authority = _text(value.get("authority"), "authority", maximum=32).lower()
    behavior = _text(value.get("behavior"), "behavior", maximum=32).lower()
    if authority not in {"approval", "autonomous", "super"} or behavior not in {
        "serial",
        "parallel",
    }:
        raise ValueError("native_bridge:execution_invalid")
    return {"authority": authority, "behavior": behavior}


def canonical_host_message(
    request: object,
    *,
    execution: object,
    p00_context: object,
    agent_type: str | None = None,
) -> str:
    """Render the exact bounded message that a host tool must receive."""

    normalized = normalize_native_host_dispatch_request(request)
    decision, action, _ = select_native_host_action(normalized)
    request_ref = native_request_reference(normalized)
    normalized_agent_type = None
    if agent_type is not None:
        normalized_agent_type = _text(agent_type, "agent_type", maximum=64).lower()
        if normalized_agent_type != normalized["role"]:
            raise ValueError("native_bridge:bound_agent_type_mismatch")
    message = {
        "schema": HOST_MESSAGE_SCHEMA,
        "marker": host_message_marker(normalized),
        "request_ref": request_ref,
        "bootstrap": {
            "first_action": "Fully read SKILL.md before any business CLI or MCP call.",
            "skill_base": "Use the installed skill location declared by your role card; all paths below are relative to it.",
            "skill": "SKILL.md",
            "then_read": [f"agents/standing-officials/{normalized['role']}.toml",
                          f"agents/office-dossiers/{normalized['role']}/AGENTS.md"],
            "then": "Read and acknowledge only; reuse supplied case/capsule references without standalone preflight scripts or root intake. Emit child_acceptance as one JSON-only assistant commentary after all reads; send the preload acknowledgement with the supplied request_ref to the direct superior, and wait for acceptance before business CLI/MCP.",
            "child_acceptance": {
                "schema": "court.child_preload_acceptance.v1",
                "task_id": normalized['task_id'], "role_key": normalized['role'],
                "office_instance_id": normalized['instance_id'],
                "request_ref": request_ref,
                "skill_loaded": True, "profile_loaded": True, "dossier_loaded": True,
            },
        },
        "task": {
            "task_id": normalized["task_id"],
            "role_key": normalized["role"],
            "office_instance_id": normalized["instance_id"],
            "direct_superior": normalized["direct_superior"],
            "assignment": normalized["assignment"],
        },
        "execution": _execution(execution),
        "p00": {
            "semantic_epoch": normalized["semantic_epoch"],
            "case_ref": deepcopy(normalized["case_ref"]),
            "office_capsule_ref": deepcopy(normalized["office_capsule_ref"]),
            "lease_id": normalized["lease_id"],
            "admission_anchor": deepcopy(normalized["admission_anchor"]),
            "dispatch_context": _message_context(normalized, p00_context),
        },
        "paths": {
            "duty_scope": deepcopy(normalized["duty_scope"]),
            "write_set": deepcopy(normalized["write_set"]),
        },
        "host_action": action,
        "host_agent_type": normalized_agent_type,
        "stop": "Reject scope, role, task, superior, admission, or host-evidence drift; report only through the direct superior.",
    }
    return json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _host_invocation(
    request: Mapping[str, object],
    *,
    message: str,
    agent_type: str | None,
) -> dict[str, object]:
    _decision, action, candidate = select_native_host_action(request)
    if action == "spawn":
        task_name = (
            str(request["role"]).replace("-", "_")
            + "_native_"
            + native_task_suffix(request)
        )
        arguments: dict[str, object] = {
            "task_name": task_name,
            "fork_turns": "none",
            "message": message,
        }
        if agent_type is not None:
            arguments["agent_type"] = agent_type
        return {
            "tool_name": "spawn_agent",
            "arguments": arguments,
        }
    if candidate is None:
        raise ValueError("native_bridge:followup_candidate_missing")
    return {
        "tool_name": "followup_task",
        "arguments": {
            "target": candidate["host_task_id"],
            "message": message,
        },
        "target_candidates": [
            candidate["host_task_id"],
            candidate["host_thread_id"],
            candidate["host_instance_id"],
        ],
    }


def native_request_result(
    request: object,
    *,
    execution: object,
    p00_context: object,
    agent_type: str | None = None,
) -> dict[str, object]:
    """Expose the exact canonical host message and direct host invocation."""

    normalized = normalize_native_host_dispatch_request(request)
    decision, action, _ = select_native_host_action(normalized)
    request_ref = native_request_reference(normalized)
    message = canonical_host_message(
        normalized,
        execution=execution,
        p00_context=p00_context,
        agent_type=agent_type,
    )
    return {
        "schema": NATIVE_REQUEST_RESULT_SCHEMA,
        "request": deepcopy(normalized),
        "request_ref": request_ref,
        "host_message_marker": host_message_marker(normalized),
        "host_message": message,
        "host_invocation": _host_invocation(
            normalized,
            message=message,
            agent_type=agent_type,
        ),
        "decision": decision,
        "expected_host_action": action,
    }


def _session_id(value: object) -> str:
    session_id = _text(value, "CODEX_SESSION_ID", maximum=64).lower()
    if _UUID_RE.fullmatch(session_id) is None:
        raise ValueError("native_bridge:current_session_id_invalid")
    return session_id


def _current_environment(
    environment: Mapping[str, str] | None,
) -> tuple[dict[str, str], str, str]:
    env = dict(os.environ if environment is None else environment)
    thread_id = _text(env.get("CODEX_THREAD_ID"), "CODEX_THREAD_ID", maximum=512)
    session_id = _session_id(env.get("CODEX_SESSION_ID"))
    return env, thread_id, session_id


def current_host_identity(
    *, environment: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Return only the required current-session identifiers for runtime binding."""

    _env, thread_id, session_id = _current_environment(environment)
    return {"thread_id": thread_id, "session_id": session_id}


def _assert_strict_path(path: Path, *, root: Path) -> Path:
    try:
        candidate = path.resolve(strict=True)
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise ValueError("native_bridge:session_path_unavailable") from exc
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("native_bridge:session_path_outside_root") from exc
    current = path
    while True:
        try:
            info = current.lstat()
        except OSError as exc:
            raise ValueError("native_bridge:session_path_unavailable") from exc
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("native_bridge:session_path_symlink")
        if current == root:
            break
        parent = current.parent
        if parent == current:
            raise ValueError("native_bridge:session_path_outside_root")
        current = parent
    if not stat.S_ISREG(candidate.stat().st_mode):
        raise ValueError("native_bridge:session_path_not_regular")
    return candidate


def _session_metadata_path(codex_home: Path, session_id: str) -> Path:
    sessions_root = codex_home / "sessions"
    try:
        root_info = sessions_root.lstat()
    except OSError as exc:
        raise ValueError("native_bridge:sessions_root_unavailable") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise ValueError("native_bridge:sessions_root_invalid")
    candidates: list[Path] = []
    try:
        for candidate in sessions_root.rglob("*.jsonl"):
            if session_id not in candidate.name.lower():
                continue
            candidates.append(_assert_strict_path(candidate, root=sessions_root))
    except OSError as exc:
        raise ValueError("native_bridge:session_path_unavailable") from exc
    unique = sorted({str(path): path for path in candidates}.values(), key=str)
    if len(unique) != 1:
        raise ValueError("native_bridge:current_session_metadata_not_unique")
    return unique[0]


def _json_object(value: object, field: str) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or len(value.encode("utf-8")) > 65_536:
        raise ValueError(f"native_bridge:{field}_invalid")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"native_bridge:{field}_invalid") from exc
    if not isinstance(parsed, Mapping):
        raise ValueError(f"native_bridge:{field}_invalid")
    return dict(parsed)


def _payload(item: object) -> dict[str, object] | None:
    if not isinstance(item, Mapping) or item.get("type") != "response_item":
        return None
    value = item.get("payload")
    return dict(value) if isinstance(value, Mapping) else None


def _call_arguments(payload: Mapping[str, object]) -> dict[str, object]:
    for key in ("arguments", "input", "args"):
        if key in payload:
            return _json_object(payload[key], f"tool_{key}")
    raise ValueError("native_bridge:tool_arguments_missing")


def _call_output(payload: Mapping[str, object]) -> dict[str, object]:
    for key in ("output", "result"):
        if key in payload:
            return _json_object(payload[key], f"tool_{key}")
    raise ValueError("native_bridge:tool_output_missing")


def _call_id(payload: Mapping[str, object]) -> str:
    for key in ("call_id", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _text(value, f"tool.{key}", maximum=512)
    raise ValueError("native_bridge:tool_call_id_missing")


def _marker_present(payload: Mapping[str, object], marker: str) -> bool:
    try:
        arguments = _call_arguments(payload)
    except ValueError:
        return False
    for field in ("message", "prompt"):
        raw_message = arguments.get(field)
        if not isinstance(raw_message, str):
            continue
        try:
            message = json.loads(raw_message)
        except ValueError:
            continue
        if isinstance(message, Mapping) and message.get("marker") == marker:
            return True
    return False


def _exact_message(arguments: Mapping[str, object], expected: str) -> None:
    fields = [field for field in ("message", "prompt") if field in arguments]
    if len(fields) != 1 or arguments.get(fields[0]) != expected:
        raise ValueError("native_bridge:host_message_mismatch")


def _agent_type_guard(
    arguments: Mapping[str, object],
    request: Mapping[str, object],
    *,
    expected_agent_type: str | None,
) -> None:
    actual = arguments.get("agent_type")
    if expected_agent_type is None:
        if actual is not None:
            raise ValueError("native_bridge:reserved_agent_type_override_rejected")
        return
    if not isinstance(actual, str) or actual.strip().lower() != expected_agent_type:
        raise ValueError("native_bridge:host_agent_type_mismatch")
    if expected_agent_type != request.get("role"):
        raise ValueError("native_bridge:bound_agent_type_mismatch")


def _exact_spawn_call(
    payload: Mapping[str, object],
    *,
    request: Mapping[str, object],
    marker: str,
    invocation: Mapping[str, object],
    expected_agent_type: str | None,
) -> tuple[str, str] | None:
    event_type = str(payload.get("type") or "").strip().lower()
    if event_type not in _CALL_TYPES:
        return None
    name = str(payload.get("name") or "").strip().lower()
    if not _marker_present(payload, marker):
        if name != invocation.get('tool_name'):
            return None
        candidate = _call_arguments(payload)
        expected = invocation.get('arguments', {})
        if candidate.get('task_name') != expected.get('task_name'):
            return None
        if not is_opaque_message(candidate.get('message')):
            raise ValueError('native_bridge:host_message_mismatch')
    if name != invocation.get("tool_name"):
        raise ValueError("native_bridge:unknown_host_tool_shape")
    arguments = _call_arguments(payload)
    expected = invocation.get("arguments")
    if not isinstance(expected, Mapping):
        raise ValueError("native_bridge:host_invocation_invalid")
    allowed = {"task_name", "fork_turns", "message", "prompt", "agent_type"}
    if set(arguments) - allowed:
        raise ValueError("native_bridge:host_argument_override_rejected")
    if arguments.get("task_name") != expected.get("task_name"):
        raise ValueError("native_bridge:host_task_name_mismatch")
    if arguments.get("fork_turns") != "none":
        raise ValueError("native_bridge:host_fork_turns_mismatch")
    if not is_opaque_message(arguments.get('message')):
        _exact_message(arguments, str(expected.get("message") or ""))
    _agent_type_guard(
        arguments,
        request,
        expected_agent_type=expected_agent_type,
    )
    return _call_id(payload), name


def _exact_followup_call(
    payload: Mapping[str, object],
    *,
    request: Mapping[str, object],
    marker: str,
    invocation: Mapping[str, object],
) -> tuple[str, str] | None:
    event_type = str(payload.get("type") or "").strip().lower()
    if event_type not in _CALL_TYPES:
        return None
    name = str(payload.get("name") or "").strip().lower()
    if not _marker_present(payload, marker):
        return None
    if name not in _FOLLOWUP_TOOL_NAMES:
        raise ValueError("native_bridge:unknown_host_tool_shape")
    arguments = _call_arguments(payload)
    expected = invocation.get("arguments")
    candidates = invocation.get("target_candidates")
    if not isinstance(expected, Mapping) or not isinstance(candidates, (list, tuple)):
        raise ValueError("native_bridge:host_invocation_invalid")
    allowed = {
        "target",
        "task_name",
        "agent_id",
        "agentId",
        "thread_id",
        "threadId",
        "message",
        "prompt",
        "agent_type",
    }
    if set(arguments) - allowed:
        raise ValueError("native_bridge:host_argument_override_rejected")
    target_fields = [
        field
        for field in ("target", "task_name", "agent_id", "agentId", "thread_id", "threadId")
        if field in arguments
    ]
    if len(target_fields) != 1 or arguments.get(target_fields[0]) not in candidates:
        raise ValueError("native_bridge:followup_target_mismatch")
    _exact_message(arguments, str(expected.get("message") or ""))
    _agent_type_guard(arguments, request, expected_agent_type=None)
    return _call_id(payload), name


def _output_record(payload: Mapping[str, object]) -> tuple[str, dict[str, object]] | None:
    event_type = str(payload.get("type") or "").strip().lower()
    if event_type not in _OUTPUT_TYPES:
        return None
    return _call_id(payload), _call_output(payload)


def _identifier_values(value: object, names: tuple[str, ...]) -> set[str]:
    pending: list[tuple[object, int]] = [(value, 0)]
    values: set[str] = set()
    while pending:
        current, depth = pending.pop()
        if depth > 3 or not isinstance(current, Mapping):
            continue
        for name in names:
            candidate = current.get(name)
            if isinstance(candidate, str) and candidate.strip():
                values.add(_text(candidate, f"host_result.{name}", maximum=512))
        for key in ("result", "data", "structuredContent"):
            nested = current.get(key)
            if isinstance(nested, Mapping):
                pending.append((nested, depth + 1))
    return values


def _one_identifier(value: object, names: tuple[str, ...], label: str) -> str:
    values = _identifier_values(value, names)
    if len(values) != 1:
        raise ValueError(f"native_bridge:{label}_missing_or_ambiguous")
    return next(iter(values))


def _host_result_from_output(
    output: Mapping[str, object],
    *,
    call_id: str,
    identity_context: object | None,
    expected_leaf: object | None,
    trace_reader_thread_id: object,
    trace_session_id: object,
    expected_epoch: int,
) -> dict[str, object]:
    if output.get("ok") is False or output.get("success") is False:
        raise ValueError("native_bridge:host_tool_not_successful")
    try:
        agent_id = _one_identifier(output, ("agent_id", "agentId"), "host_agent_id")
        thread_id = _one_identifier(output, ("thread_id", "threadId"), "host_thread_id")
    except ValueError as exc:
        task_names = _identifier_values(output, ("task_name",))
        if (
            len(task_names) != 1
            or identity_context is None
            or expected_leaf is None
        ):
            raise ValueError("native_bridge:host_identity_unavailable") from exc
        try:
            return {
                "ok": True,
                **canonical_agent_path_identity(
                    next(iter(task_names)),
                    expected_leaf=expected_leaf,
                    context=identity_context,
                    expected_epoch=expected_epoch,
                    trace_reader_thread_id=trace_reader_thread_id,
                    trace_session_id=trace_session_id,
                    host_action_id=call_id,
                ),
            }
        except ValueError as identity_error:
            raise ValueError("native_bridge:canonical_path_identity_untrusted") from identity_error
    task_ids = _identifier_values(output, ("task_id", "taskId"))
    if len(task_ids) > 1:
        raise ValueError("native_bridge:host_task_id_missing_or_ambiguous")
    task_id = next(iter(task_ids)) if task_ids else agent_id
    return {
        "ok": True,
        "host_task_id": task_id,
        "host_thread_id": thread_id,
        "host_instance_id": agent_id,
        "host_action_id": call_id,
    }


class _TraceVerifiedHost:
    """Host adapter whose sole result came from a verified current-session trace."""

    def __init__(self, request: Mapping[str, object], result: Mapping[str, object]) -> None:
        self._request = deepcopy(dict(request))
        self._result = deepcopy(dict(result))

    def _result_for(self, request: object) -> dict[str, object]:
        if normalize_native_host_dispatch_request(request) != self._request:
            raise ValueError("native_bridge:adapter_request_mismatch")
        return deepcopy(self._result)

    def spawn(self, request: object) -> dict[str, object]:
        return self._result_for(request)

    def followup(self, host_instance_id: object, request: object) -> dict[str, object]:
        if host_instance_id != self._result.get("host_instance_id"):
            raise ValueError("native_bridge:adapter_instance_mismatch")
        return self._result_for(request)


class _ReceiptCollector:
    def __init__(self) -> None:
        self.receipt: dict[str, object] | None = None

    def start(self, receipt: object) -> dict[str, object]:
        self.receipt = deepcopy(dict(receipt)) if isinstance(receipt, Mapping) else None
        return {"captured": True, "action": "start"}

    def followup(self, receipt: object) -> dict[str, object]:
        self.receipt = deepcopy(dict(receipt)) if isinstance(receipt, Mapping) else None
        return {"captured": True, "action": "followup"}

    def spawn_failed(self, _request: object, _failure: object) -> dict[str, object]:
        raise ValueError("native_bridge:host_tool_not_successful")


def _read_session_header(path: Path) -> dict[str, object]:
    with path.open(encoding='utf-8') as handle:
        line = handle.readline(262145)
    if len(line.encode('utf-8')) > 262144:
        raise ValueError('native_bridge:child_metadata_too_large')
    try:
        row = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError('native_bridge:child_metadata_invalid') from exc
    if row.get('type') != 'session_meta' or not isinstance(row.get('payload'), dict):
        raise ValueError('native_bridge:child_metadata_missing')
    return row['payload']


def _root_thread_from_trace(home: Path, reader_thread: str, session: str) -> str:
    """Walk host-recorded ancestry; a session identifier is not a thread identifier."""
    seen = set()
    current = reader_thread
    for _ in range(32):
        if current in seen:
            raise ValueError('native_bridge:root_ancestry_cycle')
        seen.add(current)
        meta = _read_session_header(_session_metadata_path(home, _session_id(current)))
        if meta.get('id') != current or (meta.get('session_id') or meta.get('id')) != session:
            raise ValueError('native_bridge:root_ancestry_session_mismatch')
        if meta.get('thread_source') != 'subagent' and not meta.get('parent_thread_id'):
            if meta.get('agent_path') not in (None, '', '/root'):
                raise ValueError('native_bridge:root_agent_path_invalid')
            return current
        current = _session_id(meta.get('parent_thread_id'))
    raise ValueError('native_bridge:root_ancestry_too_deep')


def captured_child_read_order(record: Mapping[str, object], manifest: object,
                             *, task_id: str = '') -> dict[str, object] | None:
    evidence = record.get('native_host_spawn_evidence')
    if not isinstance(evidence, Mapping):
        if record.get('native_host_action_receipt_id'):
            raise NativeEvidencePending('native_bridge:child_spawn_metadata_not_observed')
        return None
    env, _reader, session_id = _current_environment(None)
    if session_id != evidence.get('root_session_id'):
        raise ValueError('native_bridge:preload_session_mismatch')
    home = Path(env.get('CODEX_HOME') or (Path.home() / '.codex'))
    path = _session_metadata_path(home, _session_id(evidence.get('child_thread_id')))
    meta = _read_session_header(path)
    if (meta.get('id') != evidence.get('child_thread_id')
            or meta.get('session_id') != session_id
            or meta.get('agent_path') != evidence.get('child_agent_path')
            or meta.get('parent_thread_id') != evidence.get('parent_thread_id')):
        raise ValueError('native_bridge:preload_child_identity_mismatch')
    if path.stat().st_size > TRACE_MAX_BYTES:
        raise ValueError('native_bridge:child_trace_too_large')
    rows = []
    with path.open(encoding='utf-8') as handle:
        for number, line in enumerate(handle, 1):
            if number > TRACE_MAX_LINES:
                raise ValueError('native_bridge:child_trace_too_many_lines')
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    # Supported installed aliases; paths are resolved only at the host boundary.
    roots = set()
    # Only active native skill projections with the required office materials.
    # Source trees and npm caches do not qualify by containing this module.
    for root in {Path.home() / '.agents/skills/decretum-matrix', home / 'skills/decretum-matrix'}:
        try:
            for attr in ('court_skill_path', 'profile_source', 'dossier_path'):
                material = (root / str(getattr(manifest, attr))).resolve()
                material.relative_to(root.resolve())
                if not material.is_file():
                    raise ValueError('native_bridge:installed_material_missing')
        except (OSError, ValueError):
            continue
        roots.add(root)
    if not roots:
        raise NativeEvidencePending('native_bridge:active_install_identity_not_observed')
    required = {name: [str(r / str(getattr(manifest, attr))) for r in roots]
                for name, attr in (('skill', 'court_skill_path'), ('profile', 'profile_source'), ('dossier', 'dossier_path'))}
    ack = {'schema': 'court.child_preload_acceptance.v1', 'task_id': task_id,
           'role_key': record.get('role'), 'office_instance_id': record.get('office_instance_id'),
           'request_ref': record.get('native_host_request_ref'),
           'skill_loaded': True, 'profile_loaded': True, 'dossier_loaded': True}
    return skill_read_order(rows, required, child_ack=ack, child_thread_id=str(evidence['child_thread_id']))


def capture_current_native_delivery(
    request: object,
    *,
    execution: object,
    p00_context: object,
    agent_type: str | None = None,
    identity_context: object | None = None,
    environment: Mapping[str, str] | None = None,
    codex_home: Path | None = None,
) -> dict[str, object]:
    """Capture only a successful, marked native action in this current session.

    ``environment`` and ``codex_home`` exist for isolated adapter tests.  They
    are never CLI arguments, and no caller may provide a trace file or result.
    """

    normalized = normalize_native_host_dispatch_request(request)
    env, thread_id, session_id = _current_environment(environment)
    home = (codex_home or Path(env.get("CODEX_HOME") or (Path.home() / ".codex"))).expanduser()
    decision, expected_action, _ = select_native_host_action(normalized)
    expected_message = canonical_host_message(
        normalized,
        execution=execution,
        p00_context=p00_context,
        agent_type=agent_type,
    )
    marker = host_message_marker(normalized)
    invocation = _host_invocation(
        normalized,
        message=expected_message,
        agent_type=agent_type,
    )
    # Capture may be requested by the coordinator, but evidence must come from
    # the actual permitted parent, never from the reader's identity by inference.
    parent_threads = set()
    if isinstance(identity_context, Mapping):
        identity_context = deepcopy(dict(identity_context))
        for parent in identity_context.get('trusted_parent_paths', []):
            if isinstance(parent, Mapping):
                if parent.get('kind') == 'taizi_root' and not parent.get('thread_id'):
                    parent['thread_id'] = _root_thread_from_trace(home, thread_id, session_id)
                parent_id = parent.get('thread_id')
                if parent_id:
                    parent_threads.add(str(parent_id))
    if len(parent_threads) == 1:
        trace_id = next(iter(parent_threads))
    elif thread_id in parent_threads:
        trace_id = thread_id
    elif parent_threads:
        raise ValueError('native_bridge:parent_trace_ambiguous')
    else:
        trace_id = session_id  # Legacy plaintext protocol uses its declared session trace.
    trace_path = _session_metadata_path(home, trace_id)
    try:
        info = trace_path.stat()
    except OSError as exc:
        raise ValueError("native_bridge:session_path_unavailable") from exc
    if info.st_size > TRACE_MAX_BYTES:
        raise ValueError("native_bridge:session_trace_too_large")

    session_values: set[str] = set()
    thread_values: set[str] = set()
    marked_calls: list[tuple[str, str]] = []
    outputs: dict[str, dict[str, object]] = {}
    activities: list[dict[str, object]] = []
    opaque_calls: dict[str, tuple[int, str]] = {}
    spawn_calls: dict[str, tuple[int, str]] = {}
    trace_ids: set[str] = set()
    try:
        with trace_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line_number > TRACE_MAX_LINES:
                    raise ValueError("native_bridge:session_trace_too_many_lines")
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(item, Mapping):
                    continue
                if item.get("type") == "session_meta" and isinstance(item.get("payload"), Mapping):
                    trace_ids.add(str(item['payload'].get('id') or '').lower())
                    value = item["payload"].get("session_id") or item['payload'].get('id')
                    if isinstance(value, str) and value.strip():
                        session_values.add(value.strip().lower())
                    for field in ("thread_id", "threadId"):
                        thread_value = item["payload"].get(field)
                        if isinstance(thread_value, str) and thread_value.strip():
                            thread_values.add(thread_value.strip())
                    continue
                activity = spawn_activity(item, line_number)
                if activity is not None:
                    activities.append(activity)
                payload = _payload(item)
                if payload is None:
                    continue
                marked = (
                    _exact_spawn_call(
                        payload,
                        request=normalized,
                        marker=marker,
                        invocation=invocation,
                        expected_agent_type=agent_type,
                    )
                    if expected_action == "spawn"
                    else _exact_followup_call(
                        payload,
                        request=normalized,
                        marker=marker,
                        invocation=invocation,
                    )
                )
                if marked is not None:
                    marked_calls.append(marked)
                    if expected_action == 'spawn':
                        spawn_calls[marked[0]] = (line_number, str(item.get('timestamp') or ''))
                    if expected_action == 'spawn' and is_opaque_message(_call_arguments(payload).get('message')):
                        opaque_calls[marked[0]] = (line_number, str(item.get('timestamp') or ''))
                    continue
                event_type = str(payload.get("type") or "").strip().lower()
                if event_type in _OUTPUT_TYPES:
                    call_id = _call_id(payload)
                    if any(marked_call_id == call_id for marked_call_id, _name in marked_calls):
                        output = _output_record(payload)
                        if output is None:
                            raise ValueError("native_bridge:matching_host_output_missing")
                        _, value = output
                        if call_id in outputs:
                            raise ValueError("native_bridge:host_output_ambiguous")
                        outputs[call_id] = value
    except OSError as exc:
        raise ValueError("native_bridge:session_trace_unreadable") from exc

    if session_values != {session_id}:
        raise ValueError("native_bridge:session_metadata_mismatch")
    if trace_ids != {trace_id.lower()}:
        raise ValueError('native_bridge:trace_thread_metadata_mismatch')
    if len(marked_calls) != 1:
        raise ValueError("native_bridge:marked_host_action_missing_or_ambiguous")
    call_id, tool_name = marked_calls[0]
    output = outputs.get(call_id)
    if output is None:
        raise ValueError("native_bridge:matching_host_output_missing")
    expected_arguments = invocation.get("arguments")
    expected_leaf = (
        expected_arguments.get("task_name")
        if expected_action == "spawn" and isinstance(expected_arguments, Mapping)
        else None
    )
    host_result = _host_result_from_output(
        output,
        call_id=call_id,
        identity_context=identity_context if expected_action == "spawn" else None,
        expected_leaf=expected_leaf,
        trace_reader_thread_id=thread_id,
        trace_session_id=session_id,
        expected_epoch=int(normalized["semantic_epoch"]),
    )
    matching = [activity for activity in activities if activity.get('call_id') == call_id]
    if call_id in opaque_calls or (expected_action == 'spawn' and matching
                                   and host_result.get('host_identity_kind') == 'canonical_agent_path'):
        if host_result.get('host_identity_kind') != 'canonical_agent_path' or not isinstance(identity_context, Mapping):
            raise ValueError('native_bridge:opaque_spawn_requires_host_metadata')
        if len(matching) != 1:
            raise ValueError('native_bridge:opaque_spawn_activity_missing_or_ambiguous')
        child_id = _session_id(matching[0].get('child_thread_id'))
        child_path = _session_metadata_path(home, child_id)
        child_meta = _read_session_header(child_path)
        call_line, call_time = spawn_calls[call_id]
        host_result['host_spawn_evidence'] = bind_opaque_spawn(
            call_id=call_id, call_line=call_line, call_time=call_time, activity=matching[0],
            child_meta=child_meta, host_result=host_result, identity_context=identity_context,
            trace_thread_id=trace_id,
        )
        if call_id not in opaque_calls:
            host_result['host_spawn_evidence']['message_verification'] = 'PLAINTEXT_EXACT_MATCHED'
    if host_result.get("host_identity_kind") != "canonical_agent_path":
        if thread_values and thread_values != {thread_id}:
            raise ValueError("native_bridge:thread_metadata_mismatch")
        if not thread_values and thread_id != session_id:
            raise ValueError("native_bridge:thread_session_binding_missing")
    host = _TraceVerifiedHost(normalized, host_result)
    collector = _ReceiptCollector()
    dispatched = dispatch_native_host_action(normalized, host=host, lifecycle=collector)
    receipt = dispatched.get("host_action_receipt") if isinstance(dispatched, Mapping) else None
    if not isinstance(receipt, Mapping) or collector.receipt != receipt:
        raise ValueError("native_bridge:canonical_receipt_missing")
    if dispatched.get("ok") is not True or dispatched.get("host_action") != expected_action:
        raise ValueError("native_bridge:canonical_dispatch_mismatch")
    result = {
        "schema": NATIVE_CAPTURE_RESULT_SCHEMA,
        "request_ref": native_request_reference(normalized),
        "decision": decision,
        "office_command": "start" if expected_action == "spawn" else "followup",
        "native_host_action_receipt": deepcopy(dict(receipt)),
        "host_task_id": host_result["host_task_id"],
        "host_thread_id": host_result["host_thread_id"],
        "host_instance_id": host_result["host_instance_id"],
        "host_action_id": host_result["host_action_id"],
        "trace": {
            "session_id": session_id,
            "tool_name": tool_name,
            "call_id": call_id,
            "source": "host_managed_current_session_metadata",
        },
    }
    if 'host_spawn_evidence' in host_result:
        result['host_spawn_evidence'] = deepcopy(host_result['host_spawn_evidence'])
        result['capture_scope'] = 'HOST_SPAWN_ONLY_PRELOAD_PENDING'
    if host_result.get("host_identity_kind") == "canonical_agent_path":
        result.update(
            host_identity_kind="canonical_agent_path",
            trace_issuer_thread_id=host_result.get("trace_issuer_thread_id"),
            trace_reader_thread_id=host_result.get("trace_reader_thread_id"),
            trace_session_id=host_result.get("trace_session_id"),
            case_session_id=host_result.get("case_session_id"),
            trusted_parent_kind=host_result.get("trusted_parent_kind"),
        )
    return result
