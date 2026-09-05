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
    canonical_json_sha256,
    dispatch_native_host_action,
    normalize_native_host_dispatch_request,
    select_native_host_action,
)
from court_native_identity import canonical_agent_path_identity


NATIVE_REQUEST_INPUT_SCHEMA = "court.office.native_request.v1"
NATIVE_REQUEST_RESULT_SCHEMA = "court.office.native_request.result.v1"
NATIVE_CAPTURE_INPUT_SCHEMA = "court.office.native_capture.v1"
NATIVE_CAPTURE_RESULT_SCHEMA = "court.office.native_capture.result.v1"
HOST_MESSAGE_SCHEMA = "court.native_host_message.v1"
HOST_MARKER_PREFIX = "COURT_NATIVE_REQUEST_SHA256="
HOST_BINDING_MARKER_PREFIX = "COURT_NATIVE_BINDING_SHA256="
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


def _binding_sha256(request: Mapping[str, object]) -> str:
    return canonical_json_sha256(
        {
            "task_id": request["task_id"],
            "role": request["role"],
            "direct_superior": request["direct_superior"],
            "admission_anchor": request["admission_anchor"],
        }
    )


def host_message_marker(request: object) -> str:
    normalized = normalize_native_host_dispatch_request(request)
    request_sha256 = canonical_json_sha256(normalized)
    return (
        f"{HOST_MARKER_PREFIX}{request_sha256};"
        f"{HOST_BINDING_MARKER_PREFIX}{_binding_sha256(normalized)}"
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
        "invariant_capsule_sha256",
        "semantic_receipt_id",
        "semantic_receipt_sha256",
        "fork_context",
        "context_mode",
        "pointers",
    )
    if any(field not in value for field in fields):
        raise ValueError("native_bridge:p00_context_invalid")
    if (
        value.get("schema") != "court.semantic.dispatch_context_packet.v1"
        or value.get("semantic_epoch") != request.get("semantic_epoch")
        or value.get("invariant_capsule_sha256")
        != request.get("invariant_capsule_sha256")
        or value.get("fork_context") != "none"
        or value.get("context_mode") != "bounded"
    ):
        raise ValueError("native_bridge:p00_context_binding_mismatch")
    pointers = value.get("pointers")
    if not isinstance(pointers, (list, tuple)) or not pointers:
        raise ValueError("native_bridge:p00_paths_invalid")
    normalized_pointers: list[dict[str, str]] = []
    for pointer in pointers:
        if not isinstance(pointer, Mapping) or set(pointer) != {"path", "sha256"}:
            raise ValueError("native_bridge:p00_paths_invalid")
        normalized_pointers.append(
            {
                "path": _text(pointer.get("path"), "p00.path", maximum=512),
                "sha256": _text(pointer.get("sha256"), "p00.path_sha256", maximum=64).lower(),
            }
        )
    return {
        "schema": "court.semantic.dispatch_context_packet.v1",
        "semantic_epoch": request["semantic_epoch"],
        "invariant_capsule_sha256": request["invariant_capsule_sha256"],
        "semantic_receipt_id": _text(
            value.get("semantic_receipt_id"), "p00.semantic_receipt_id", maximum=256
        ),
        "semantic_receipt_sha256": _text(
            value.get("semantic_receipt_sha256"), "p00.semantic_receipt_sha256", maximum=64
        ).lower(),
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
    request_sha256 = canonical_json_sha256(normalized)
    normalized_agent_type = None
    if agent_type is not None:
        normalized_agent_type = _text(agent_type, "agent_type", maximum=64).lower()
        if normalized_agent_type != normalized["role"]:
            raise ValueError("native_bridge:bound_agent_type_mismatch")
    message = {
        "schema": HOST_MESSAGE_SCHEMA,
        "marker": host_message_marker(normalized),
        "request_sha256": request_sha256,
        "binding_sha256": _binding_sha256(normalized),
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
            "charter_sha256": normalized["charter_sha256"],
            "invariant_capsule_sha256": normalized["invariant_capsule_sha256"],
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
            + canonical_json_sha256(request)[:16]
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
    request_sha256 = canonical_json_sha256(normalized)
    message = canonical_host_message(
        normalized,
        execution=execution,
        p00_context=p00_context,
        agent_type=agent_type,
    )
    return {
        "schema": NATIVE_REQUEST_RESULT_SCHEMA,
        "request": deepcopy(normalized),
        "request_sha256": request_sha256,
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
    raw_arguments = next(
        (payload[key] for key in ("arguments", "input", "args") if key in payload),
        None,
    )
    if isinstance(raw_arguments, str):
        return marker in raw_arguments
    if isinstance(raw_arguments, Mapping):
        return marker in json.dumps(raw_arguments, ensure_ascii=False, sort_keys=True)
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
        return None
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
    trace_path = _session_metadata_path(home, session_id)
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
                    value = item["payload"].get("id")
                    if isinstance(value, str) and value.strip():
                        session_values.add(value.strip().lower())
                    for field in ("thread_id", "threadId"):
                        thread_value = item["payload"].get(field)
                        if isinstance(thread_value, str) and thread_value.strip():
                            thread_values.add(thread_value.strip())
                    continue
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
        "request_sha256": canonical_json_sha256(normalized),
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
