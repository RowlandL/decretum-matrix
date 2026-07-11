"""Mode-neutral policy primitives for court office dispatch."""

from __future__ import annotations

from dataclasses import dataclass


MAX_AGENT_TREE_DEPTH = 4
MAX_AGENT_TREE_THREADS = 16


@dataclass(frozen=True)
class CourtMode:
    authority: str
    topology: str
    runtime_family: str
    supercc: bool


@dataclass(frozen=True)
class DispatchDecision:
    selected_roles: tuple[str, ...]
    deferred_roles: tuple[str, ...]
    available_slots: int
    effective_host_capacity: int
    max_threads: int
    next_depth: int | None
    max_depth: int
    static_wave_cap: None
    reason: str


@dataclass(frozen=True)
class DispatchPlanItem:
    role: str
    office_zh: str
    duty: str
    direct_superior: str
    dependency_roles: tuple[str, ...]
    parallel_group: str
    allowed_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    evidence_contract: str
    stop_conditions: tuple[str, ...]
    visibility: str


@dataclass(frozen=True)
class DispatchPlan:
    entries: tuple[DispatchPlanItem, ...]
    roles: tuple[str, ...]
    unjustified_roles: tuple[str, ...]


OFFICE_SPECS = {
    "taizi": ("太子", "user"),
    "zhongshu": ("中书省", "taizi"),
    "menxia": ("门下省", "taizi"),
    "shangshu": ("尚书省", "taizi"),
    "libu-hr": ("吏部", "shangshu"),
    "hubu": ("户部", "shangshu"),
    "libu": ("礼部", "shangshu"),
    "bingbu": ("兵部", "shangshu"),
    "xingbu": ("刑部", "shangshu"),
    "gongbu": ("工部", "shangshu"),
    "shiguan": ("史馆", "taizi/menxia"),
    "zaochao": ("早朝", "taizi"),
}
VISIBLE_CORE_ROLES = {"taizi", "zhongshu", "menxia", "shangshu"}
VISIBILITIES = {"non_visible", "visible_core", "bounded_visible_diagnostic"}


def normalize_mode(text: str) -> CourtMode:
    normalized = " ".join(str(text).strip().casefold().replace("_", " ").split())
    if "supercc" in normalized:
        return CourtMode("super", "court_runtime", "visible_zellij_squad", True)
    if "super并行" in normalized or "super parallel" in normalized:
        return CourtMode("super", "ordinary_parallel", "spawned_subagent", False)
    if "super" in normalized:
        return CourtMode("super", "auto", "ordinary", False)
    raise ValueError("explicit court authority required")


def select_wave(
    useful_roles: list[str] | tuple[str, ...],
    host_capacity: int | None,
    host_active: int | None,
    user_agent_budget: int | None,
    provider_launch_budget: int | None,
    *,
    host_retained: int | None,
    host_reclamation_verified: bool | None = None,
    next_depth: int | None = None,
    max_threads: int | None = MAX_AGENT_TREE_THREADS,
    max_depth: int | None = MAX_AGENT_TREE_DEPTH,
) -> DispatchDecision:
    roles = tuple(str(role).strip() for role in useful_roles if str(role).strip())
    if max_threads is None or int(max_threads) <= 0:
        return DispatchDecision((), roles, 0, 0, 0, next_depth, int(max_depth or 0), None, "max_threads_unknown")
    configured_threads = min(int(max_threads), MAX_AGENT_TREE_THREADS)
    if max_depth is None or int(max_depth) < 0:
        return DispatchDecision((), roles, 0, 0, configured_threads, next_depth, 0, None, "max_depth_unknown")
    configured_depth = min(int(max_depth), MAX_AGENT_TREE_DEPTH)
    if next_depth is None:
        return DispatchDecision((), roles, 0, 0, configured_threads, None, configured_depth, None, "next_depth_unknown")
    resolved_depth = int(next_depth)
    if resolved_depth < 0:
        return DispatchDecision((), roles, 0, 0, configured_threads, resolved_depth, configured_depth, None, "next_depth_invalid")
    if resolved_depth > configured_depth:
        return DispatchDecision((), roles, 0, 0, configured_threads, resolved_depth, configured_depth, None, "max_depth_exceeded")
    if host_capacity is None or int(host_capacity) <= 0:
        return DispatchDecision((), roles, 0, 0, configured_threads, resolved_depth, configured_depth, None, "host_capacity_unknown")
    effective_capacity = min(int(host_capacity), configured_threads)
    if host_active is None or int(host_active) < 0:
        return DispatchDecision((), roles, 0, effective_capacity, configured_threads, resolved_depth, configured_depth, None, "host_occupancy_unknown")
    if host_retained is None:
        return DispatchDecision((), roles, 0, effective_capacity, configured_threads, resolved_depth, configured_depth, None, "host_retained_unknown")
    if isinstance(host_retained, bool) or not isinstance(host_retained, int) or host_retained < 0:
        return DispatchDecision((), roles, 0, effective_capacity, configured_threads, resolved_depth, configured_depth, None, "host_retained_invalid")
    if host_retained and host_reclamation_verified is None:
        return DispatchDecision((), roles, 0, effective_capacity, configured_threads, resolved_depth, configured_depth, None, "host_reclamation_unknown")
    if host_reclamation_verified not in {None, True, False}:
        return DispatchDecision((), roles, 0, effective_capacity, configured_threads, resolved_depth, configured_depth, None, "host_reclamation_invalid")
    retained_occupancy = 0 if host_reclamation_verified is True else host_retained
    effective_active = max(1, int(host_active)) + retained_occupancy
    available = max(0, effective_capacity - effective_active)
    limits = [(available, "runtime_capacity"), (len(roles), "all_useful_roles_selected")]
    if user_agent_budget is not None:
        limits.append((max(0, int(user_agent_budget)), "user_budget"))
    if provider_launch_budget is not None:
        limits.append((max(0, int(provider_launch_budget)), "provider_budget"))
    count = min(limit for limit, _reason in limits)
    selected = roles[:count]
    deferred = roles[count:]
    if not deferred:
        reason = "all_useful_roles_selected"
    elif available == count:
        reason = "runtime_capacity"
    elif user_agent_budget is not None and max(0, int(user_agent_budget)) == count:
        reason = "user_budget"
    else:
        reason = "provider_budget"
    return DispatchDecision(
        selected,
        deferred,
        available,
        effective_capacity,
        configured_threads,
        resolved_depth,
        configured_depth,
        None,
        reason,
    )


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if not result:
        raise ValueError(f"{field} must not be empty")
    return result


def validate_dispatch_plan(
    entries: list[dict[str, object]] | tuple[dict[str, object], ...],
    *,
    mode: str = "super",
    allow_bounded_visible_diagnostic: bool = False,
) -> DispatchPlan:
    if not entries:
        raise ValueError("dispatch plan must contain at least one useful role")
    court_mode = normalize_mode(mode)
    seen: set[str] = set()
    normalized: list[DispatchPlanItem] = []
    for raw in entries:
        if not isinstance(raw, dict):
            raise ValueError("dispatch plan entries must be objects")
        role = str(raw.get("role") or "").strip().lower()
        if role not in OFFICE_SPECS or role in seen:
            raise ValueError(f"invalid or duplicate role: {role}")
        seen.add(role)
        office_zh, expected_superior = OFFICE_SPECS[role]
        if str(raw.get("office_zh") or "").strip() != office_zh:
            raise ValueError(f"office_zh mismatch for {role}")
        direct_superior = str(raw.get("direct_superior") or "").strip().lower()
        if direct_superior != expected_superior:
            raise ValueError(f"direct_superior mismatch for {role}")
        duty = str(raw.get("duty") or "").strip()
        evidence = str(raw.get("evidence_contract") or "").strip()
        parallel_group = str(raw.get("parallel_group") or "").strip()
        if not duty or not evidence or not parallel_group:
            raise ValueError(f"duty, evidence_contract, and parallel_group are required for {role}")
        dependencies = tuple(str(item).strip().lower() for item in raw.get("dependency_roles", []) if str(item).strip()) if isinstance(raw.get("dependency_roles", []), (list, tuple)) else ()
        if role in dependencies or len(set(dependencies)) != len(dependencies) or any(item not in OFFICE_SPECS for item in dependencies):
            raise ValueError(f"invalid dependency_roles for {role}")
        visibility = str(raw.get("visibility") or "").strip().lower()
        if visibility not in VISIBILITIES:
            raise ValueError(f"invalid visibility for {role}")
        if not court_mode.supercc and visibility != "non_visible":
            raise ValueError("ordinary dispatch must remain non-visible")
        if court_mode.supercc:
            if visibility == "visible_core" and role not in VISIBLE_CORE_ROLES:
                raise ValueError("only taizi and three departments may be visible_core")
            if visibility == "bounded_visible_diagnostic" and not allow_bounded_visible_diagnostic:
                raise ValueError("bounded visible diagnostics require explicit authorization")
        normalized.append(
            DispatchPlanItem(
                role=role,
                office_zh=office_zh,
                duty=duty,
                direct_superior=direct_superior,
                dependency_roles=dependencies,
                parallel_group=parallel_group,
                allowed_actions=_string_tuple(raw.get("allowed_actions"), "allowed_actions"),
                forbidden_actions=_string_tuple(raw.get("forbidden_actions"), "forbidden_actions"),
                evidence_contract=evidence,
                stop_conditions=_string_tuple(raw.get("stop_conditions"), "stop_conditions"),
                visibility=visibility,
            )
        )
    return DispatchPlan(tuple(normalized), tuple(item.role for item in normalized), ())
