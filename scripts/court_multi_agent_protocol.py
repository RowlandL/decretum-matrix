"""Pure protocol selection and whole-tree admission rules for court agents."""

from __future__ import annotations

from dataclasses import dataclass
import re
import sys
from typing import Literal, Sequence
import uuid

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ expected.
    tomllib = None  # type: ignore[assignment]

sys.dont_write_bytecode = True


RequestedMode = Literal["auto", "v1", "v2", "serial"]
SelectedMode = Literal["v1", "v2", "serial"]
ModelOverrideCapability = Literal["applied", "inherited", "not_applicable", "blocked"]

HARD_MAX_THREADS = 16
HARD_MAX_DEPTH = 4
V1_CHILD_THREAD_LIMIT = 15


@dataclass(frozen=True)
class ProtocolRequirements:
    needs_parallel_tree: bool = False
    needs_fork_turns: bool = False
    needs_cross_branch_messages: bool = False
    needs_agent_type_override: bool = False
    needs_model_override: bool = False
    needs_reasoning_effort_override: bool = False
    child_agents_required: bool = True
    active_session_protocol: Literal["v1", "v2"] | None = None


@dataclass(frozen=True)
class ProtocolDecision:
    requested_mode: RequestedMode
    selected_mode: SelectedMode | None
    reason_codes: tuple[str, ...]
    conflict: bool
    model_override_capability: ModelOverrideCapability


@dataclass(frozen=True)
class RoleAdmissionDecision:
    allowed: bool
    selected_roles: tuple[str, ...]
    deferred_roles: tuple[str, ...]
    reason_codes: tuple[str, ...]
    effective_host_capacity: int | None
    effective_max_threads: int | None
    effective_max_depth: int | None
    available_slots: int | None


@dataclass(frozen=True)
class QuiescenceSnapshot:
    main_turn_finished: bool
    active_agents: int | None
    unfinished_agents: tuple[str, ...]
    pending_messages: int | None
    pending_followups: int | None
    pending_waits: int | None
    running_tool_calls: int | None
    result_merge_complete: bool
    session_id: str | None
    goal_persisted: bool
    court_task_persisted: bool
    side_effect_ledger_committed: bool
    credential_state_clear: bool
    protocol_switch_capability_verified: bool
    capacity_known: bool
    occupancy_known: bool
    depth_known: bool


@dataclass(frozen=True)
class QuiescenceDecision:
    ok: bool
    errors: tuple[str, ...]
    session_id: str | None


def _decision(
    requested_mode: RequestedMode,
    selected_mode: SelectedMode | None,
    *reason_codes: str,
    conflict: bool = False,
    model_override_capability: ModelOverrideCapability = "not_applicable",
) -> ProtocolDecision:
    return ProtocolDecision(
        requested_mode=requested_mode,
        selected_mode=selected_mode,
        reason_codes=tuple(reason_codes),
        conflict=conflict,
        model_override_capability=model_override_capability,
    )


def select_protocol(requested_mode: RequestedMode, requirements: ProtocolRequirements) -> ProtocolDecision:
    """Select one protocol without pretending an unverified V1 override was applied."""

    if requested_mode not in {"auto", "v1", "v2", "serial"}:
        raise ValueError(f"unsupported protocol mode: {requested_mode}")
    hard_v1 = requirements.needs_agent_type_override
    hard_v2 = any(
        (
            requirements.needs_parallel_tree,
            requirements.needs_fork_turns,
            requirements.needs_cross_branch_messages,
        )
    )
    unsupported_override = requirements.needs_model_override or requirements.needs_reasoning_effort_override
    active = requirements.active_session_protocol
    if active not in {None, "v1", "v2"}:
        raise ValueError(f"unsupported active session protocol: {active}")
    if not requirements.child_agents_required:
        if hard_v1 or hard_v2 or unsupported_override:
            return _decision(
                requested_mode,
                None,
                "capability_conflict",
                "child_agents_disabled_but_required",
                conflict=True,
                model_override_capability="blocked" if unsupported_override else "not_applicable",
            )
        return _decision(
            requested_mode,
            "serial",
            "child_agents_not_required",
            model_override_capability="not_applicable",
        )
    if unsupported_override:
        return _decision(
            requested_mode,
            None,
            "capability_conflict",
            "child_model_or_effort_override_unavailable",
            conflict=True,
            model_override_capability="blocked",
        )
    if hard_v1 and hard_v2:
        return _decision(
            requested_mode,
            None,
            "capability_conflict",
            "v1_override_and_v2_tree_required",
            conflict=True,
            model_override_capability="blocked",
        )

    selected: SelectedMode
    if requested_mode == "auto":
        if active is None:
            return _decision(
                requested_mode,
                None,
                "capability_conflict",
                "active_session_protocol_unknown",
                conflict=True,
            )
        selected = active
    else:
        selected = requested_mode
    if selected == "serial":
        return _decision(
            requested_mode,
            None,
            "capability_conflict",
            "serial_conflicts_with_child_requirement",
            conflict=True,
            model_override_capability="not_applicable",
        )
    if active is not None and selected != active:
        return _decision(
            requested_mode,
            None,
            "capability_conflict",
            f"active_{active}_session_conflicts_with_{selected}",
            conflict=True,
        )
    if selected == "v1" and hard_v2:
        return _decision(
            requested_mode,
            None,
            "capability_conflict",
            "v1_conflicts_with_v2_tree_requirement",
            conflict=True,
        )
    if selected == "v2" and hard_v1:
        return _decision(
            requested_mode,
            None,
            "capability_conflict",
            "v2_cannot_apply_requested_override",
            conflict=True,
            model_override_capability="blocked",
        )
    if selected == "v1":
        capability: ModelOverrideCapability = "inherited"
        reason = "v1_agent_type_required" if hard_v1 else "active_or_explicit_v1"
    else:
        capability = "inherited"
        reason = "v2_tree_required" if hard_v2 else "active_or_explicit_v2"
    return _decision(
        requested_mode,
        selected,
        reason,
        model_override_capability=capability,
    )


def _normalized_roles(requested_roles: Sequence[str]) -> tuple[str, ...]:
    roles: list[str] = []
    seen: set[str] = set()
    for role in requested_roles:
        normalized = str(role or "").strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            roles.append(normalized)
    return tuple(roles)


def admit_roles(
    *,
    host_capacity: int | None,
    active_threads: int | None,
    retained_threads: int | None,
    terminal_reclamation_verified: bool | None = None,
    requested_roles: Sequence[str],
    max_threads: int | None = HARD_MAX_THREADS,
    next_depth: int | None,
    max_depth: int | None = HARD_MAX_DEPTH,
) -> RoleAdmissionDecision:
    """Admit a bounded role prefix; any unknown runtime bound fails closed."""

    roles = _normalized_roles(requested_roles)
    unknown = any(
        value is None
        for value in (host_capacity, active_threads, retained_threads, max_threads, next_depth, max_depth)
    )
    if unknown:
        return RoleAdmissionDecision(False, (), roles, ("unknown_runtime_bound",), None, None, None, None)
    values = (host_capacity, active_threads, retained_threads, max_threads, next_depth, max_depth)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        return RoleAdmissionDecision(False, (), roles, ("invalid_runtime_bound",), None, None, None, None)
    assert host_capacity is not None
    assert active_threads is not None
    assert retained_threads is not None
    assert max_threads is not None
    assert next_depth is not None
    assert max_depth is not None
    if (
        host_capacity < 1
        or active_threads < 1
        or retained_threads < 0
        or max_threads < 1
        or next_depth < 1
        or max_depth < 1
    ):
        return RoleAdmissionDecision(False, (), roles, ("invalid_runtime_bound",), None, None, None, None)
    if retained_threads and terminal_reclamation_verified is None:
        return RoleAdmissionDecision(False, (), roles, ("host_reclamation_unknown",), None, None, None, None)
    if terminal_reclamation_verified not in {None, True, False}:
        return RoleAdmissionDecision(False, (), roles, ("invalid_runtime_bound",), None, None, None, None)
    effective_max_threads = min(max_threads, HARD_MAX_THREADS)
    effective_max_depth = min(max_depth, HARD_MAX_DEPTH)
    effective_host_capacity = min(host_capacity, effective_max_threads)
    retained_occupancy = 0 if terminal_reclamation_verified is True else retained_threads
    available_slots = max(effective_host_capacity - active_threads - retained_occupancy, 0)
    if next_depth > effective_max_depth:
        return RoleAdmissionDecision(
            False,
            (),
            roles,
            ("max_depth_exceeded",),
            effective_host_capacity,
            effective_max_threads,
            effective_max_depth,
            available_slots,
        )
    if not roles:
        return RoleAdmissionDecision(
            False,
            (),
            (),
            ("no_roles_requested",),
            effective_host_capacity,
            effective_max_threads,
            effective_max_depth,
            available_slots,
        )
    selected = roles[:available_slots]
    deferred = roles[available_slots:]
    if not selected:
        return RoleAdmissionDecision(
            False,
            (),
            deferred,
            ("capacity_exhausted",),
            effective_host_capacity,
            effective_max_threads,
            effective_max_depth,
            available_slots,
        )
    reason_codes = ("admitted",) if not deferred else ("partial_admission", "capacity_clamped")
    return RoleAdmissionDecision(
        True,
        selected,
        deferred,
        reason_codes,
        effective_host_capacity,
        effective_max_threads,
        effective_max_depth,
        available_slots,
    )


def _find_section(lines: list[str], name: str) -> tuple[int | None, int]:
    start: int | None = None
    end = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == f"[{name}]":
            start = index
            continue
        if start is not None and index > start and re.match(r"^\[[^\]]+\]\s*$", stripped):
            end = index
            break
    return start, end


def _ensure_section(lines: list[str], name: str) -> tuple[int, int]:
    start, end = _find_section(lines, name)
    if start is not None:
        return start, end
    insert_at = len(lines)
    prefix = f"[{name}."
    for index, line in enumerate(lines):
        if line.strip().startswith(prefix):
            insert_at = index
            break
    block = [f"[{name}]"]
    if insert_at > 0 and lines[insert_at - 1].strip():
        block.insert(0, "")
    if insert_at < len(lines) and lines[insert_at].strip():
        block.append("")
    lines[insert_at:insert_at] = block
    start, end = _find_section(lines, name)
    assert start is not None
    return start, end


def _render_toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    raise TypeError(f"unsupported protocol config value: {value!r}")


def _set_key(lines: list[str], section: str, key: str, value: object) -> None:
    start, end = _ensure_section(lines, section)
    pattern = re.compile(rf"^(\s*){re.escape(key)}\s*=.*$")
    rendered = _render_toml_value(value)
    for index in range(start + 1, end):
        match = pattern.match(lines[index])
        if match:
            lines[index] = f"{match.group(1)}{key} = {rendered}"
            return
    lines.insert(end, f"{key} = {rendered}")


def _remove_key(lines: list[str], section: str, key: str) -> None:
    start, end = _find_section(lines, section)
    if start is None:
        return
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=.*$")
    for index in range(end - 1, start, -1):
        if pattern.match(lines[index]):
            lines.pop(index)


def render_protocol_config(
    original: str,
    mode: SelectedMode,
    *,
    max_depth: int = HARD_MAX_DEPTH,
    total_threads: int = HARD_MAX_THREADS,
    v1_child_threads: int = V1_CHILD_THREAD_LIMIT,
    isolated_serial: bool = False,
) -> str:
    """Render one active host protocol while preserving the inactive V2 rollback table."""

    if mode not in {"v1", "v2", "serial"}:
        raise ValueError(f"unsupported protocol mode: {mode}")
    if mode == "serial" and not isolated_serial:
        return original
    if max_depth < 1 or total_threads < 2 or v1_child_threads < 1:
        raise ValueError("protocol limits must be positive")
    max_depth = min(max_depth, HARD_MAX_DEPTH)
    total_threads = min(total_threads, HARD_MAX_THREADS)
    v1_child_threads = min(v1_child_threads, total_threads - 1)
    had_newline = original.endswith(("\n", "\r\n"))
    lines = original.splitlines()
    _set_key(lines, "agents", "max_depth", max_depth)
    _remove_key(lines, "features", "multi_agent_v2")
    if mode == "v2":
        _remove_key(lines, "agents", "max_threads")
        _set_key(lines, "features.multi_agent_v2", "enabled", True)
        _set_key(lines, "features.multi_agent_v2", "max_concurrent_threads_per_session", total_threads)
        _set_key(lines, "features.multi_agent_v2", "hide_spawn_agent_metadata", True)
    elif mode == "v1":
        _set_key(lines, "agents", "max_threads", v1_child_threads)
        _set_key(lines, "features", "multi_agent", True)
        _set_key(lines, "features.multi_agent_v2", "enabled", False)
        _set_key(lines, "features.multi_agent_v2", "max_concurrent_threads_per_session", total_threads)
        _set_key(lines, "features.multi_agent_v2", "hide_spawn_agent_metadata", True)
    else:
        _remove_key(lines, "agents", "max_threads")
        _set_key(lines, "features", "multi_agent", False)
        _set_key(lines, "features.multi_agent_v2", "enabled", False)
        _remove_key(lines, "features.multi_agent_v2", "max_concurrent_threads_per_session")
        _remove_key(lines, "features.multi_agent_v2", "hide_spawn_agent_metadata")
    rendered = "\n".join(lines)
    if had_newline or not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def validate_protocol_config(text: str, *, expected_mode: SelectedMode | None = None) -> dict[str, object]:
    """Validate the active protocol while allowing an inert V2 rollback table under V1."""

    errors: list[str] = []
    if tomllib is None:
        return {"ok": False, "errors": ["tomllib_unavailable"], "mode": None}
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {"ok": False, "errors": ["toml_decode_error"], "mode": None}
    agents = data.get("agents") if isinstance(data, dict) else None
    features = data.get("features") if isinstance(data, dict) else None
    agents = agents if isinstance(agents, dict) else {}
    features = features if isinstance(features, dict) else {}
    v2 = features.get("multi_agent_v2")
    v2 = v2 if isinstance(v2, dict) else {}
    max_depth = agents.get("max_depth")
    legacy_threads = agents.get("max_threads")
    multi_agent_enabled = features.get("multi_agent")
    v2_enabled = v2.get("enabled") is True
    v2_disabled = v2.get("enabled") is False
    v2_threads = v2.get("max_concurrent_threads_per_session")
    hidden_metadata = v2.get("hide_spawn_agent_metadata")
    inactive_v2_config_preserved = bool(
        v2_disabled
        and v2_threads == HARD_MAX_THREADS
        and hidden_metadata is True
    )

    if v2_enabled and legacy_threads is not None:
        errors.append("v2_enabled_with_legacy_max_threads")
    mode: SelectedMode | None = None
    effective_child_limit: int | None = None
    if v2_enabled:
        mode = "v2"
        if max_depth != HARD_MAX_DEPTH:
            errors.append("v2_max_depth_must_equal_4")
        if v2_threads != HARD_MAX_THREADS:
            errors.append("v2_total_threads_must_equal_16")
        if hidden_metadata is not True:
            errors.append("v2_reserved_spawn_schema_must_be_hidden")
        if isinstance(v2_threads, int) and not isinstance(v2_threads, bool):
            effective_child_limit = max(v2_threads - 1, 0)
    elif v2_disabled and multi_agent_enabled is True and legacy_threads is not None:
        mode = "v1"
        if max_depth != HARD_MAX_DEPTH:
            errors.append("v1_max_depth_must_equal_4")
        if legacy_threads != V1_CHILD_THREAD_LIMIT:
            errors.append("v1_child_threads_must_equal_15")
        if v2_threads != HARD_MAX_THREADS:
            errors.append("v1_inactive_v2_total_threads_must_equal_16")
        if hidden_metadata is not True:
            errors.append("v1_inactive_v2_reserved_schema_must_remain_hidden")
        if isinstance(legacy_threads, int) and not isinstance(legacy_threads, bool):
            effective_child_limit = legacy_threads
    elif v2_disabled and multi_agent_enabled is False:
        mode = "serial"
        if legacy_threads is not None or v2_threads is not None:
            errors.append("serial_concurrency_fields_must_be_absent")
    else:
        errors.append("protocol_mode_unresolved")
    if expected_mode is not None and mode != expected_mode:
        errors.append(f"expected_{expected_mode}_got_{mode or 'unknown'}")
    return {
        "ok": not errors,
        "errors": errors,
        "mode": mode,
        "max_depth": max_depth,
        "legacy_max_threads": legacy_threads,
        "multi_agent_enabled": multi_agent_enabled,
        "multi_agent_v2_enabled": v2_enabled,
        "max_concurrent_threads_per_session": v2_threads,
        "hide_spawn_agent_metadata": hidden_metadata,
        "inactive_v2_config_preserved": inactive_v2_config_preserved,
        "effective_child_thread_limit": effective_child_limit,
    }


def validate_session_id(value: object) -> str:
    text = str(value or "")
    if not text or text != text.strip() or text in {"--last", "--ephemeral"}:
        raise ValueError("exact canonical session UUID is required")
    try:
        parsed = uuid.UUID(text)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("exact canonical session UUID is required") from exc
    canonical = str(parsed)
    if text.lower() != canonical:
        raise ValueError("session UUID must use canonical hyphenated form")
    return canonical


def build_exact_resume_command(
    executable: str,
    session_id: str,
    internal_prompt: str,
    *,
    exec_mode: bool = False,
) -> tuple[str, ...]:
    executable_text = str(executable or "").strip()
    prompt = str(internal_prompt or "")
    if not executable_text:
        raise ValueError("Codex executable is required")
    if not prompt or "\x00" in prompt:
        raise ValueError("bounded internal resume prompt is required")
    exact_session = validate_session_id(session_id)
    command = [executable_text]
    if exec_mode:
        command.append("exec")
    command.extend(["resume", exact_session, prompt])
    if "--last" in command or "--ephemeral" in command:
        raise ValueError("automatic resume must use an exact session UUID")
    return tuple(command)


def assess_quiescence(snapshot: QuiescenceSnapshot) -> QuiescenceDecision:
    errors: list[str] = []
    if snapshot.main_turn_finished is not True:
        errors.append("main_turn_not_finished")
    counts = {
        "active_agents": snapshot.active_agents,
        "pending_messages": snapshot.pending_messages,
        "pending_followups": snapshot.pending_followups,
        "pending_waits": snapshot.pending_waits,
        "running_tool_calls": snapshot.running_tool_calls,
    }
    for name, value in counts.items():
        if value is None or isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"{name}_unknown")
        elif value != 0:
            errors.append(f"{name}_not_zero")
    if snapshot.unfinished_agents:
        errors.append("unfinished_agents_present")
    if snapshot.result_merge_complete is not True:
        errors.append("result_merge_incomplete")
    if snapshot.goal_persisted is not True:
        errors.append("goal_not_persisted")
    if snapshot.court_task_persisted is not True:
        errors.append("court_task_not_persisted")
    if snapshot.side_effect_ledger_committed is not True:
        errors.append("side_effect_ledger_uncommitted")
    if snapshot.credential_state_clear is not True:
        errors.append("credential_state_not_clear")
    if snapshot.protocol_switch_capability_verified is not True:
        errors.append("protocol_switch_capability_unverified")
    if snapshot.capacity_known is not True:
        errors.append("capacity_unknown")
    if snapshot.occupancy_known is not True:
        errors.append("occupancy_unknown")
    if snapshot.depth_known is not True:
        errors.append("depth_unknown")
    exact_session: str | None = None
    try:
        exact_session = validate_session_id(snapshot.session_id)
    except ValueError:
        errors.append("session_id_invalid")
    return QuiescenceDecision(not errors, tuple(errors), exact_session)
