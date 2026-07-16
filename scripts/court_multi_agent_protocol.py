"""Pure protocol selection and whole-tree admission rules for court agents."""

from __future__ import annotations

from dataclasses import dataclass
import re
import sys
from typing import Literal, Mapping, Sequence
import uuid

sys.dont_write_bytecode = True

from court_complexity_budget import (
    DEFAULT_NORMAL_PARALLEL_LIMIT,
    resolve_parallel_limit,
)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ expected.
    tomllib = None  # type: ignore[assignment]

RequestedMode = Literal["auto", "v1", "v2", "serial"]
SelectedMode = Literal["v1", "v2", "serial"]
ModelOverrideCapability = Literal["applied", "inherited", "not_applicable", "blocked"]

HARD_MAX_DEPTH = 4
ADVISORY_BASELINE_THREADS = 16
DEFAULT_HIGH_PARALLEL_THREADS = DEFAULT_NORMAL_PARALLEL_LIMIT


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
    return tuple(
        normalized
        for role in requested_roles
        if (normalized := str(role or "").strip().lower())
    )


_OFFICE_DIRECT_SUPERIORS = {
    "taizi": "user",
    "zhongshu": "taizi",
    "menxia": "taizi",
    "shangshu": "taizi",
    "libu-hr": "shangshu",
    "hubu": "shangshu",
    "libu": "shangshu",
    "bingbu": "shangshu",
    "xingbu": "shangshu",
    "gongbu": "shangshu",
    "shiguan": "taizi/menxia",
}
_SIX_MINISTRY_ROLES = frozenset({"libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"})
_WORKER_INSTANCE_KINDS = frozenset({"worker", "craftsman", "office_worker_instance"})
_CANONICAL_INSTANCE_KINDS = frozenset({"office", "canonical_authority"})


def validate_admission_instance_shape(
    bindings: Sequence[Mapping[str, object]],
    *,
    allow_taizi_singleton: bool,
) -> None:
    """Validate the one-canonical/many-worker shape shared by plan and admission."""

    if not isinstance(bindings, Sequence) or isinstance(bindings, (str, bytes)):
        raise ValueError("instance_shape_gate: bindings must be a sequence")
    by_role: dict[str, list[tuple[str, str, bool]]] = {}
    for binding in bindings:
        if not isinstance(binding, Mapping):
            raise ValueError("instance_shape_gate: binding must be an object")
        role = str(binding.get("role") or "").strip().lower()
        instance_id = str(binding.get("instance_id") or "").strip().lower()
        instance_kind = str(binding.get("instance_kind") or "").strip().lower()
        canonical_authority = binding.get("canonical_authority")
        if (
            not role
            or not instance_id
            or not instance_kind
            or not isinstance(canonical_authority, bool)
        ):
            raise ValueError("instance_shape_gate: exact role/instance/kind/canonical binding required")
        if canonical_authority:
            if instance_kind not in _CANONICAL_INSTANCE_KINDS:
                raise ValueError("canonical_authority_shape_gate: canonical instance kind mismatch")
        elif instance_kind not in _WORKER_INSTANCE_KINDS:
            raise ValueError("office_worker_instance_shape_gate: non-canonical instance must be a worker")
        by_role.setdefault(role, []).append((instance_id, instance_kind, canonical_authority))

    for role, instances in by_role.items():
        canonical_count = sum(1 for _instance, _kind, canonical in instances if canonical)
        if role == "taizi":
            if not allow_taizi_singleton or len(instances) != 1 or canonical_count != 1:
                raise ValueError("single_taizi_gate: taizi is the only singleton office")
            continue
        if canonical_count > 1 or (len(instances) > 1 and canonical_count != 1):
            raise ValueError(
                "canonical_authority_uniqueness_gate: exactly one canonical authority is required"
            )


def canonical_repo_relative_paths(
    value: object,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...] | None:
    if not isinstance(value, (list, tuple)):
        return None
    if not value:
        return () if allow_empty else None
    normalized: list[str] = []
    for path in value:
        if not isinstance(path, str):
            return None
        candidate = path.strip().replace("\\", "/")
        parts = candidate.split("/")
        if (
            not candidate
            or candidate.startswith("/")
            or re.match(r"^[A-Za-z]:", candidate)
            or "\x00" in candidate
            or any(part in {"", ".", ".."} or ":" in part for part in parts)
        ):
            return None
        normalized.append("/".join(part.casefold() for part in parts))
    return tuple(normalized) if len(set(normalized)) == len(normalized) else None


def repository_paths_overlap(left: str, right: str) -> bool:
    return (
        left == right
        or left.startswith(f"{right}/")
        or right.startswith(f"{left}/")
    )


def _normalized_write_set(value: object, *, allow_empty: bool = False) -> tuple[str, ...] | None:
    return canonical_repo_relative_paths(value, allow_empty=allow_empty)


def _normalized_read_scope(value: object) -> tuple[str, ...] | None:
    return canonical_repo_relative_paths(value)


def _normalized_access_contract(binding: Mapping[str, object]) -> tuple[object, ...] | None:
    access_mode = str(binding.get("access_mode") or "read_write").strip().lower()
    mutation_allowed = binding.get("mutation_allowed", access_mode == "read_write")
    integration_authority = binding.get("integration_authority", False)
    if not isinstance(mutation_allowed, bool) or not isinstance(integration_authority, bool):
        return None
    write_set = _normalized_write_set(
        binding.get("write_set"),
        allow_empty=access_mode == "read_only",
    )
    if write_set is None:
        return None
    read_scope_value = binding.get("read_scope")
    read_scope = (
        write_set
        if access_mode == "read_write" and read_scope_value is None
        else _normalized_read_scope(read_scope_value)
    )
    if read_scope is None:
        return None
    if access_mode == "read_only":
        if write_set or mutation_allowed or integration_authority:
            return None
    elif access_mode == "read_write":
        if not write_set or not mutation_allowed:
            return None
    else:
        return None
    return access_mode, write_set, read_scope, mutation_allowed, integration_authority


def _approved_scope_selection(
    budget_lease: Mapping[str, object],
    *,
    approved_count: int,
    requested_roles: Sequence[str],
    requested_bindings: Sequence[Mapping[str, object]] | None,
    integration_domain: str | None,
    authority: str | None,
) -> tuple[tuple[int, ...] | None, str | None]:
    expected_domain = str(integration_domain or "").strip()
    lease_domain = str(budget_lease.get("integration_domain") or "").strip()
    if not expected_domain or lease_domain != expected_domain:
        return None, "approved_budget_integration_domain_mismatch"
    expected_authority = str(authority or "").strip().lower()
    lease_authority = str(budget_lease.get("authority") or "").strip().lower()
    if not expected_authority or lease_authority != expected_authority:
        return None, "approved_budget_authority_mismatch"
    if requested_bindings is None or isinstance(requested_bindings, (str, bytes)):
        return None, "approved_budget_scope_mismatch"
    roles = tuple(str(role or "").strip().lower() for role in requested_roles)
    bindings = tuple(requested_bindings)
    if (
        len(bindings) != len(roles)
        or len(bindings) < approved_count
        or any(not isinstance(item, Mapping) for item in bindings)
    ):
        return None, "approved_budget_scope_mismatch"
    try:
        validate_admission_instance_shape(bindings, allow_taizi_singleton=False)
    except ValueError:
        return None, "approved_budget_instance_shape_mismatch"

    requested: dict[
        str,
        tuple[int, str, str, tuple[object, ...], tuple[str, bool, str, str]],
    ] = {}
    requested_shards: set[str] = set()
    for index, (requested_role, binding) in enumerate(zip(roles, bindings)):
        role = str(binding.get("role") or "").strip().lower()
        instance_id = str(binding.get("instance_id") or "").strip().lower()
        shard_id = str(binding.get("shard_id") or "").strip()
        direct_superior = str(binding.get("direct_superior") or "").strip().lower()
        instance_kind = str(binding.get("instance_kind") or "office").strip().lower()
        canonical_authority = binding.get("canonical_authority")
        owner_role = str(binding.get("owner_role") or "").strip().lower()
        access_contract = _normalized_access_contract(binding)
        if (
            not role
            or role != requested_role
            or not instance_id
            or not shard_id
            or access_contract is None
            or instance_id in requested
            or shard_id in requested_shards
        ):
            return None, "approved_budget_scope_mismatch"
        if instance_kind in _WORKER_INSTANCE_KINDS:
            if owner_role not in _SIX_MINISTRY_ROLES or direct_superior != owner_role:
                return None, "approved_budget_hierarchy_mismatch"
        else:
            expected_superior = _OFFICE_DIRECT_SUPERIORS.get(role, "shangshu")
            if direct_superior != expected_superior:
                return None, "approved_budget_hierarchy_mismatch"
        if not isinstance(canonical_authority, bool):
            return None, "approved_budget_instance_shape_mismatch"
        requested[instance_id] = (
            index,
            role,
            shard_id,
            access_contract,
            (instance_kind, canonical_authority, owner_role, direct_superior),
        )
        requested_shards.add(shard_id)

    approved_roles_raw = budget_lease.get("approved_roles")
    approved_instances_raw = budget_lease.get("approved_instance_ids")
    approved_shards_raw = budget_lease.get("approved_shards")
    approved_write_sets = budget_lease.get("approved_write_sets")
    approved_access_contracts = budget_lease.get("approved_access_contracts")
    approved_instance_shapes = budget_lease.get("approved_instance_shapes")
    if (
        not isinstance(approved_roles_raw, (list, tuple))
        or not isinstance(approved_instances_raw, (list, tuple))
        or not isinstance(approved_shards_raw, (list, tuple))
        or not isinstance(approved_write_sets, Mapping)
        or not isinstance(approved_instance_shapes, Mapping)
        or (
            approved_access_contracts is not None
            and not isinstance(approved_access_contracts, Mapping)
        )
    ):
        return None, "approved_budget_scope_mismatch"
    approved_roles = tuple(str(value).strip().lower() for value in approved_roles_raw)
    approved_instances = tuple(str(value).strip().lower() for value in approved_instances_raw)
    approved_shards = tuple(str(value).strip() for value in approved_shards_raw)
    if (
        len(approved_roles) != approved_count
        or len(approved_instances) != approved_count
        or len(approved_shards) != approved_count
        or any(not value for value in (*approved_roles, *approved_instances, *approved_shards))
        or len(set(approved_instances)) != approved_count
        or len(set(approved_shards)) != approved_count
    ):
        return None, "approved_budget_scope_mismatch"
    normalized_access_contracts: dict[str, tuple[object, ...]] = {}
    for key, value in approved_write_sets.items():
        instance_id = str(key).strip().lower()
        approved_access = (
            approved_access_contracts.get(key)
            if isinstance(approved_access_contracts, Mapping)
            else None
        )
        if approved_access is None and isinstance(approved_access_contracts, Mapping):
            approved_access = approved_access_contracts.get(instance_id)
        if approved_access is None:
            approved_access = {
                "access_mode": "read_write",
                "read_scope": value,
                "mutation_allowed": True,
                "integration_authority": False,
            }
        if not isinstance(approved_access, Mapping):
            return None, "approved_budget_scope_mismatch"
        access_contract = _normalized_access_contract({**approved_access, "write_set": value})
        if not instance_id or access_contract is None or instance_id in normalized_access_contracts:
            return None, "approved_budget_scope_mismatch"
        normalized_access_contracts[instance_id] = access_contract
    if set(normalized_access_contracts) != set(approved_instances):
        return None, "approved_budget_scope_mismatch"
    if isinstance(approved_access_contracts, Mapping) and {
        str(key).strip().lower() for key in approved_access_contracts
    } != set(approved_instances):
        return None, "approved_budget_scope_mismatch"
    normalized_instance_shapes: dict[str, tuple[str, bool, str, str]] = {}
    for key, value in approved_instance_shapes.items():
        instance_id = str(key).strip().lower()
        if not instance_id or not isinstance(value, Mapping):
            return None, "approved_budget_instance_shape_mismatch"
        instance_kind = str(value.get("instance_kind") or "").strip().lower()
        canonical_authority = value.get("canonical_authority")
        owner_role = str(value.get("owner_role") or "").strip().lower()
        direct_superior = str(value.get("direct_superior") or "").strip().lower()
        if (
            not instance_kind
            or not isinstance(canonical_authority, bool)
            or instance_id in normalized_instance_shapes
        ):
            return None, "approved_budget_instance_shape_mismatch"
        normalized_instance_shapes[instance_id] = (
            instance_kind,
            canonical_authority,
            owner_role,
            direct_superior,
        )
    if set(normalized_instance_shapes) != set(approved_instances):
        return None, "approved_budget_instance_shape_mismatch"
    try:
        validate_admission_instance_shape(
            [
                {
                    "role": role,
                    "instance_id": instance_id,
                    "instance_kind": normalized_instance_shapes[instance_id][0],
                    "canonical_authority": normalized_instance_shapes[instance_id][1],
                }
                for role, instance_id in zip(approved_roles, approved_instances)
            ],
            allow_taizi_singleton=False,
        )
    except ValueError:
        return None, "approved_budget_instance_shape_mismatch"

    selected_indices: list[int] = []
    for role, instance_id, shard_id in zip(
        approved_roles, approved_instances, approved_shards
    ):
        requested_binding = requested.get(instance_id)
        if requested_binding is None:
            return None, "approved_budget_scope_mismatch"
        (
            index,
            requested_role,
            requested_shard,
            requested_access_contract,
            requested_instance_shape,
        ) = requested_binding
        if (
            role != requested_role
            or shard_id != requested_shard
            or normalized_access_contracts[instance_id] != requested_access_contract
            or normalized_instance_shapes[instance_id] != requested_instance_shape
        ):
            return None, "approved_budget_scope_mismatch"
        selected_indices.append(index)
    return tuple(selected_indices), None


def approved_budget_selection(
    budget_lease: Mapping[str, object] | None,
    *,
    task_id: str | None,
    calling_office: str | None,
    direct_superior: str | None,
    requested_roles: Sequence[str],
    requested_bindings: Sequence[Mapping[str, object]] | None = None,
    integration_domain: str | None = None,
    authority: str | None = None,
) -> tuple[tuple[int, ...] | None, str | None]:
    """Validate Phase 0.5 scope and return only lease-approved request indices."""

    if budget_lease is None:
        return None, "approved_budget_missing"
    if not isinstance(budget_lease, Mapping):
        return None, "approved_budget_invalid"
    if str(budget_lease.get("status") or "").strip().upper() != "ACTIVE":
        return None, "approved_budget_not_active"
    if not str(budget_lease.get("lease_id") or "").strip():
        return None, "approved_budget_invalid"
    approved_count = budget_lease.get("approved_count")
    if isinstance(approved_count, bool) or not isinstance(approved_count, int):
        return None, "approved_budget_invalid"
    if approved_count < 1:
        return None, "approved_budget_insufficient"

    expected_task = str(task_id or "").strip()
    lease_task = str(budget_lease.get("task_id") or "").strip()
    if not expected_task or lease_task != expected_task:
        return None, "approved_budget_task_mismatch"

    expected_caller = str(calling_office or "").strip().lower()
    expected_superior = str(direct_superior or "").strip().lower()
    lease_caller = str(budget_lease.get("calling_office") or "").strip().lower()
    lease_superior = str(budget_lease.get("direct_superior") or "").strip().lower()
    if (
        not expected_caller
        or not expected_superior
        or lease_caller != expected_caller
        or lease_superior != expected_superior
    ):
        return None, "approved_budget_hierarchy_mismatch"
    return _approved_scope_selection(
        budget_lease,
        approved_count=approved_count,
        requested_roles=requested_roles,
        requested_bindings=requested_bindings,
        integration_domain=integration_domain,
        authority=authority,
    )


def approved_budget_limit(
    budget_lease: Mapping[str, object] | None,
    *,
    task_id: str | None,
    calling_office: str | None,
    direct_superior: str | None,
    requested_bindings: Sequence[Mapping[str, object]] | None = None,
    integration_domain: str | None = None,
    authority: str | None = None,
) -> tuple[int | None, str | None]:
    """Compatibility wrapper returning the number of approved bound requests."""

    roles = tuple(
        str(binding.get("role") or "").strip().lower()
        for binding in requested_bindings or ()
        if isinstance(binding, Mapping)
    )
    selected, error = approved_budget_selection(
        budget_lease,
        task_id=task_id,
        calling_office=calling_office,
        direct_superior=direct_superior,
        requested_roles=roles,
        requested_bindings=requested_bindings,
        integration_domain=integration_domain,
        authority=authority,
    )
    return (len(selected) if selected is not None else None), error


def admit_roles(
    *,
    host_capacity: int | None,
    active_threads: int | None,
    retained_threads: int | None,
    terminal_reclamation_verified: bool | None = None,
    requested_roles: Sequence[str],
    max_threads: int | None = DEFAULT_HIGH_PARALLEL_THREADS,
    next_depth: int | None,
    max_depth: int | None = HARD_MAX_DEPTH,
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
    try:
        parallel_limit = resolve_parallel_limit(
            configured_limit=max_threads,
            explicit_count=explicit_parallel_count,
            unlock=parallel_unlimited,
            control_source=parallel_control_source,
            system_memory_percent=system_memory_percent,
        )
    except ValueError as exc:
        return RoleAdmissionDecision(
            False,
            (),
            roles,
            (str(exc),),
            min(host_capacity, DEFAULT_NORMAL_PARALLEL_LIMIT),
            DEFAULT_NORMAL_PARALLEL_LIMIT,
            min(max_depth, HARD_MAX_DEPTH),
            0,
        )
    effective_max_threads = int(parallel_limit["effective_limit"])
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
        return RoleAdmissionDecision(
            False,
            (),
            roles,
            (budget_error,),
            effective_host_capacity,
            effective_max_threads,
            effective_max_depth,
            available_slots,
        )
    assert approved_indices is not None
    selected_indices = approved_indices[:available_slots]
    selected_index_set = set(selected_indices)
    selected = tuple(roles[index] for index in selected_indices)
    deferred = tuple(role for index, role in enumerate(roles) if index not in selected_index_set)
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
    if not deferred:
        reason_codes = ("admitted",)
    else:
        clamps = []
        if len(approved_indices) < len(roles):
            clamps.append("approved_budget_clamped")
        if available_slots < len(approved_indices):
            clamps.append("capacity_clamped")
        reason_codes = ("partial_admission", *clamps)
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
    total_threads: int = DEFAULT_HIGH_PARALLEL_THREADS,
    v1_child_threads: int | None = None,
    isolated_serial: bool = False,
) -> str:
    """Render one active host protocol while preserving the inactive V2 rollback table."""

    if mode not in {"v1", "v2", "serial"}:
        raise ValueError(f"unsupported protocol mode: {mode}")
    if mode == "serial" and not isolated_serial:
        return original
    if v1_child_threads is None:
        v1_child_threads = total_threads - 1
    if max_depth < 1 or total_threads < 2 or v1_child_threads < 1:
        raise ValueError("protocol limits must be positive")
    max_depth = min(max_depth, HARD_MAX_DEPTH)
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
        and isinstance(v2_threads, int)
        and not isinstance(v2_threads, bool)
        and v2_threads >= 2
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
        if not isinstance(v2_threads, int) or isinstance(v2_threads, bool) or v2_threads < 2:
            errors.append("v2_total_threads_must_be_at_least_2")
        if hidden_metadata is not True:
            errors.append("v2_reserved_spawn_schema_must_be_hidden")
        if isinstance(v2_threads, int) and not isinstance(v2_threads, bool):
            effective_child_limit = max(v2_threads - 1, 0)
    elif v2_disabled and multi_agent_enabled is True and legacy_threads is not None:
        mode = "v1"
        if max_depth != HARD_MAX_DEPTH:
            errors.append("v1_max_depth_must_equal_4")
        if not isinstance(legacy_threads, int) or isinstance(legacy_threads, bool) or legacy_threads < 1:
            errors.append("v1_child_threads_must_be_positive")
        if not isinstance(v2_threads, int) or isinstance(v2_threads, bool) or v2_threads < 2:
            errors.append("v1_inactive_v2_total_threads_must_be_at_least_2")
        elif isinstance(legacy_threads, int) and legacy_threads > v2_threads - 1:
            errors.append("v1_child_threads_exceed_inactive_v2_capacity")
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
