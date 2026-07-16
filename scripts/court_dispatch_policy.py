"""Mode-neutral policy primitives for court office dispatch."""

from __future__ import annotations

from dataclasses import dataclass
import re
import sys
from typing import Mapping, Sequence

sys.dont_write_bytecode = True

from court_complexity_budget import (
    DEFAULT_NORMAL_PARALLEL_LIMIT,
    resolve_parallel_limit,
)
from court_dispatch_hierarchy import (
    DispatchHierarchyDecision,
    validate_dispatch_hierarchy,
)
from court_multi_agent_protocol import (
    approved_budget_selection,
    validate_admission_instance_shape,
)


MAX_AGENT_TREE_DEPTH = 4
ADVISORY_BASELINE_THREADS = 16
DEFAULT_HIGH_PARALLEL_THREADS = 32
# Compatibility export for the Lane G runtime until it consumes the integration
# proposal. Dispatch policy itself never clamps a caller-supplied thread value.
MAX_AGENT_TREE_THREADS = DEFAULT_NORMAL_PARALLEL_LIMIT


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
    selected_indices: tuple[int, ...] = ()


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
    runtime_family: str
    role_key: str
    canonical_role_id: str
    office_instance_id: str
    instance_key: str
    office_instance_kind: str
    canonical_authority: bool
    global_integration_owner: bool
    task_id: str
    dispatch_uid: str
    shard_id: str
    attempt: int
    owned_paths: tuple[str, ...]
    write_set: tuple[str, ...]
    profile_path: str
    dossier_path: str
    skill_path: str
    profile_hash: str
    dossier_hash: str
    court_skill_hash: str
    preload_ack: str
    evidence_pointer: str
    heartbeat_state: str
    release_state: str
    super_giant_task_gate: str
    remaining_super_giant: bool
    system_memory_percent: float
    scale_out_priority: str


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


def _first_scoped_hierarchy_denial(
    *,
    calling_office: object,
    requested_roles: Sequence[str],
    requested_bindings: Sequence[Mapping[str, object]] | None,
) -> DispatchHierarchyDecision | None:
    """Validate hierarchy-scoped requests before capacity or lease selection."""

    ministry_roles = frozenset(
        {"libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"}
    )
    if (
        requested_bindings is None
        or isinstance(requested_bindings, (str, bytes))
        or len(requested_bindings) != len(requested_roles)
    ):
        return None
    for role, binding in zip(requested_roles, requested_bindings):
        if not isinstance(binding, Mapping):
            continue
        canonical_authority = binding.get("canonical_authority")
        child_profile = binding.get("child_profile")
        if not (
            (role in ministry_roles and canonical_authority is True)
            or child_profile is not None
        ):
            continue
        decision = validate_dispatch_hierarchy(
            action="dispatch",
            calling_office=calling_office,
            target_role=role,
            target_direct_superior=binding.get("direct_superior"),
            instance_kind=(
                binding.get("instance_kind")
                or binding.get("office_instance_kind")
            ),
            canonical_authority=canonical_authority,
            owner_role=binding.get("owner_role"),
            child_profile=child_profile,
        )
        if (
            not decision.allowed
            and (
                child_profile is not None
                or decision.reason_codes
                in {
                    ("dispatch_hierarchy_edge_forbidden",),
                    ("dispatch_hierarchy_manifest_invalid",),
                }
            )
        ):
            return decision
    return None


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
    max_threads: int | None = DEFAULT_NORMAL_PARALLEL_LIMIT,
    max_depth: int | None = MAX_AGENT_TREE_DEPTH,
    explicit_parallel_count: int | None = None,
    parallel_unlimited: bool = False,
    parallel_control_source: str | None = None,
    system_memory_percent: float = 0.0,
    budget_lease: Mapping[str, object] | None = None,
    task_id: str | None = None,
    calling_office: str | None = None,
    direct_superior: str | None = None,
    requested_bindings: Sequence[Mapping[str, object]] | None = None,
    integration_domain: str | None = None,
    authority: str | None = None,
) -> DispatchDecision:
    roles = tuple(str(role).strip() for role in useful_roles if str(role).strip())
    hierarchy_denial = _first_scoped_hierarchy_denial(
        calling_office=calling_office,
        requested_roles=roles,
        requested_bindings=requested_bindings,
    )
    if hierarchy_denial is not None:
        return DispatchDecision(
            (),
            roles,
            0,
            0,
            int(max_threads) if isinstance(max_threads, int) and not isinstance(max_threads, bool) else 0,
            next_depth,
            int(max_depth) if isinstance(max_depth, int) and not isinstance(max_depth, bool) else 0,
            None,
            hierarchy_denial.reason_codes[0],
        )
    if max_threads is None or int(max_threads) <= 0:
        return DispatchDecision((), roles, 0, 0, 0, next_depth, int(max_depth or 0), None, "max_threads_unknown")
    configured_capacity = int(max_threads)
    try:
        parallel_limit = resolve_parallel_limit(
            configured_limit=configured_capacity,
            explicit_count=explicit_parallel_count,
            unlock=parallel_unlimited,
            control_source=parallel_control_source,
            system_memory_percent=system_memory_percent,
        )
    except ValueError as exc:
        return DispatchDecision(
            (),
            roles,
            0,
            0,
            min(configured_capacity, DEFAULT_NORMAL_PARALLEL_LIMIT),
            next_depth,
            int(max_depth or 0),
            None,
            str(exc),
        )
    configured_threads = int(parallel_limit["effective_limit"])
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
    approved_indices, budget_error = approved_budget_selection(
        budget_lease,
        task_id=task_id,
        calling_office=calling_office,
        direct_superior=direct_superior,
        requested_roles=roles,
        requested_bindings=requested_bindings,
        integration_domain=integration_domain,
        authority=authority,
    )
    if budget_error is not None:
        return DispatchDecision(
            (),
            roles,
            available,
            effective_capacity,
            configured_threads,
            resolved_depth,
            configured_depth,
            None,
            budget_error,
        )
    assert approved_indices is not None
    approved_count = len(approved_indices)
    limits = [
        (available, "runtime_capacity"),
        (approved_count, "approved_budget"),
    ]
    if user_agent_budget is not None:
        limits.append((max(0, int(user_agent_budget)), "user_budget"))
    if provider_launch_budget is not None:
        limits.append((max(0, int(provider_launch_budget)), "provider_budget"))
    count = min(limit for limit, _reason in limits)
    selected_indices = approved_indices[:count]
    selected_index_set = set(selected_indices)
    selected = tuple(roles[index] for index in selected_indices)
    deferred = tuple(role for index, role in enumerate(roles) if index not in selected_index_set)
    if not deferred:
        reason = "all_useful_roles_selected"
    elif available < approved_count and available == count:
        reason = "runtime_capacity"
    elif (
        user_agent_budget is not None
        and max(0, int(user_agent_budget)) < approved_count
        and max(0, int(user_agent_budget)) == count
    ):
        reason = "user_budget"
    elif (
        provider_launch_budget is not None
        and max(0, int(provider_launch_budget)) < approved_count
        and max(0, int(provider_launch_budget)) == count
    ):
        reason = "provider_budget"
    else:
        reason = "approved_budget"
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
        tuple(selected_indices),
    )


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if not result:
        raise ValueError(f"{field} must not be empty")
    return result


def _validate_trusted_preload_manifest(
    entries: Sequence[dict[str, object]],
    trusted_preload_manifest: Mapping[str, Mapping[str, object]] | None,
) -> None:
    if not isinstance(trusted_preload_manifest, Mapping):
        raise ValueError(
            "exact_preload_contract_gate: trusted preload manifest is required"
        )
    expected_keys: set[str] = set()
    for raw in entries:
        role = str(raw.get("role") or "").strip().lower()
        instance_key = str(raw.get("instance_key") or "").strip().lower()
        if not role or not instance_key:
            raise ValueError(
                "exact_preload_contract_gate: role and instance_key are required"
            )
        expected_keys.add(instance_key)
        trusted = trusted_preload_manifest.get(instance_key)
        if not isinstance(trusted, Mapping):
            raise ValueError(
                "exact_preload_contract_gate: trusted instance manifest is missing"
            )
        expected_paths = {
            "profile_path": f"agents/standing-officials/{role}.toml",
            "dossier_path": f"agents/supercc-dossiers/{role}/AGENTS.md",
            "skill_path": "SKILL.md",
        }
        for field, expected in expected_paths.items():
            trusted_value = str(trusted.get(field) or "").strip()
            raw_value = str(raw.get(field) or "").strip()
            if trusted_value != expected or raw_value != expected:
                raise ValueError(
                    f"exact_preload_contract_gate: {field} does not match role manifest"
                )
        for field in ("profile_hash", "dossier_hash", "court_skill_hash"):
            trusted_hash = str(trusted.get(field) or "").strip().lower()
            raw_hash = str(raw.get(field) or "").strip().lower()
            if (
                re.fullmatch(r"[0-9a-f]{64}", trusted_hash) is None
                or raw_hash != trusted_hash
            ):
                raise ValueError(
                    f"exact_preload_contract_gate: {field} does not match trusted manifest"
                )
        if (
            str(trusted.get("preload_ack") or "").strip() != "PASSED"
            or str(raw.get("preload_ack") or "").strip() != "PASSED"
        ):
            raise ValueError(
                "exact_preload_contract_gate: preload acknowledgement is not trusted"
            )
    manifest_keys = {
        str(key).strip().lower() for key in trusted_preload_manifest if str(key).strip()
    }
    if manifest_keys != expected_keys:
        raise ValueError(
            "exact_preload_contract_gate: trusted manifest instance set mismatch"
        )


def validate_dispatch_plan(
    entries: list[dict[str, object]] | tuple[dict[str, object], ...],
    *,
    mode: str = "super",
    allow_bounded_visible_diagnostic: bool = False,
    trusted_preload_manifest: Mapping[str, Mapping[str, object]] | None = None,
) -> DispatchPlan:
    if not entries:
        raise ValueError("dispatch plan must contain at least one useful role")
    _validate_trusted_preload_manifest(entries, trusted_preload_manifest)
    court_mode = normalize_mode(mode)
    role_counts: dict[str, int] = {}
    for raw in entries:
        if isinstance(raw, dict):
            role = str(raw.get("role") or "").strip().lower()
            role_counts[role] = role_counts.get(role, 0) + 1
    seen_instances: set[str] = set()
    role_instances: dict[str, list[DispatchPlanItem]] = {}
    normalized: list[DispatchPlanItem] = []
    for ordinal, raw in enumerate(entries, start=1):
        if not isinstance(raw, dict):
            raise ValueError("dispatch plan entries must be objects")
        role = str(raw.get("role") or "").strip().lower()
        if role not in OFFICE_SPECS:
            raise ValueError(f"invalid role: {role}")
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
        instance_key = str(raw.get("instance_key") or f"{role}#{ordinal:04d}").strip().lower()
        if not re.fullmatch(rf"{re.escape(role)}#\d{{4}}", instance_key) or instance_key in seen_instances:
            raise ValueError("office_worker_instance_identity_gate: invalid or duplicate instance_key")
        seen_instances.add(instance_key)
        canonical_authority = bool(raw.get("canonical_authority", role_counts.get(role, 0) == 1))
        global_integration_owner = bool(
            raw.get("global_integration_owner", role_counts.get(role, 0) == 1)
        )
        scale_out_priority = (
            "HIGHEST"
            if role in {"libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"}
            else "EXTREMELY_LOW"
            if role == "shangshu"
            else "LOW"
        )
        owned_paths_raw = raw.get("owned_paths", ())
        write_set_raw = raw.get("write_set", ())
        owned_paths = tuple(
            str(value).strip() for value in owned_paths_raw if str(value).strip()
        ) if isinstance(owned_paths_raw, (list, tuple)) else ()
        write_set = tuple(
            str(value).strip() for value in write_set_raw if str(value).strip()
        ) if isinstance(write_set_raw, (list, tuple)) else ()
        profile_hash = str(raw.get("profile_hash") or "").strip()
        dossier_hash = str(raw.get("dossier_hash") or "").strip()
        court_skill_hash = str(raw.get("court_skill_hash") or "").strip()
        preload_ack = str(raw.get("preload_ack") or "").strip()
        if preload_ack != "PASSED":
            raise ValueError(
                "exact_preload_contract_gate: preload_ack must equal PASSED"
            )
        for field, digest in (
            ("profile_hash", profile_hash),
            ("dossier_hash", dossier_hash),
            ("court_skill_hash", court_skill_hash),
        ):
            if re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
                raise ValueError(
                    f"exact_preload_contract_gate: {field} must be a SHA-256 digest"
                )
        item = DispatchPlanItem(
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
            runtime_family=str(
                raw.get("runtime_family")
                or ("visible_zellij_squad" if visibility != "non_visible" else "spawned_subagent")
            ).strip(),
            role_key=str(raw.get("role_key") or role).strip().lower(),
            canonical_role_id=str(raw.get("canonical_role_id") or f"{role}#canonical").strip(),
            office_instance_id=str(raw.get("office_instance_id") or f"office-{instance_key}").strip(),
            instance_key=instance_key,
            office_instance_kind=str(
                raw.get("office_instance_kind")
                or ("canonical_authority" if canonical_authority else "office_worker_instance")
            ).strip(),
            canonical_authority=canonical_authority,
            global_integration_owner=global_integration_owner,
            task_id=str(raw.get("task_id") or f"task-{instance_key}").strip(),
            dispatch_uid=str(raw.get("dispatch_uid") or f"dispatch-{instance_key}").strip(),
            shard_id=str(
                raw.get("shard_id")
                or ("canonical-integration" if canonical_authority else instance_key)
            ).strip(),
            attempt=int(raw.get("attempt") or 1),
            owned_paths=owned_paths,
            write_set=write_set,
            profile_path=str(
                raw.get("profile_path") or f"agents/standing-officials/{role}.toml"
            ).strip(),
            dossier_path=str(
                raw.get("dossier_path") or f"agents/supercc-dossiers/{role}/AGENTS.md"
            ).strip(),
            skill_path=str(raw.get("skill_path") or "SKILL.md").strip(),
            profile_hash=profile_hash,
            dossier_hash=dossier_hash,
            court_skill_hash=court_skill_hash,
            preload_ack=preload_ack,
            evidence_pointer=str(raw.get("evidence_pointer") or "").strip(),
            heartbeat_state=str(raw.get("heartbeat_state") or "").strip(),
            release_state=str(raw.get("release_state") or "").strip(),
            super_giant_task_gate=str(
                raw.get("super_giant_task_gate") or "NOT_APPLICABLE"
            ).strip(),
            remaining_super_giant=bool(raw.get("remaining_super_giant", False)),
            system_memory_percent=float(raw.get("system_memory_percent", 0.0)),
            scale_out_priority=scale_out_priority,
        )
        if item.role_key != role:
            raise ValueError("office_worker_instance_identity_gate: role_key mismatch")
        if role_counts.get(role, 0) > 1 and (
            not item.office_instance_id
            or not item.task_id
            or not item.dispatch_uid
            or not item.shard_id
            or item.attempt < 1
        ):
            raise ValueError("office_worker_instance_identity_gate: incomplete instance identity")
        normalized.append(item)
        role_instances.setdefault(role, []).append(item)

    for role, instances in role_instances.items():
        if len(instances) == 1:
            continue
        if sum(item.global_integration_owner for item in instances) != 1:
            raise ValueError(
                "single_integration_owner_gate: exactly one integration owner is required"
            )
        validate_admission_instance_shape(
            [
                {
                    "role": item.role,
                    "instance_id": item.instance_key,
                    "instance_kind": item.office_instance_kind,
                    "canonical_authority": item.canonical_authority,
                }
                for item in instances
            ],
            allow_taizi_singleton=True,
        )
        workers = [item for item in instances if not item.canonical_authority]
        task_ids = [item.task_id for item in workers]
        shard_ids = [item.shard_id for item in workers]
        if len(task_ids) != len(set(task_ids)) or len(shard_ids) != len(set(shard_ids)):
            raise ValueError(
                "assignment_ownership_and_write_set_gate: duplicate task or shard"
            )
        claimed_paths: set[str] = set()
        for item in workers:
            claims = set(item.write_set)
            if claimed_paths.intersection(claims):
                raise ValueError(
                    "assignment_ownership_and_write_set_gate: overlapping write_set"
                )
            claimed_paths.update(claims)
        if any(item.system_memory_percent >= 99.0 for item in instances):
            raise ValueError(
                "system_memory_pressure_downgrade_gate: scale-out disabled at 99 percent memory"
            )
        if role == "shangshu":
            if any(item.super_giant_task_gate != "PASSED" for item in instances):
                raise ValueError(
                    "super_giant_shangshu_scale_gate: deputy requires super-giant approval"
                )
            if any(item.remaining_super_giant is not True for item in instances):
                raise ValueError(
                    "super_giant_scale_reassessment_gate: scale-out must downgrade"
                )
        if court_mode.supercc:
            visible = [item for item in instances if item.visibility != "non_visible"]
            if len(visible) > 1 or any(
                not item.canonical_authority
                or item.runtime_family != "visible_zellij_squad"
                for item in visible
            ):
                raise ValueError(
                    "supercc_canonical_visibility_gate: extra instances must remain ordinary non-visible workers"
                )
    return DispatchPlan(tuple(normalized), tuple(item.role for item in normalized), ())
