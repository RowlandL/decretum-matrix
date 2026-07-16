"""Whole-tree role admission and write-scope rules for court agents."""

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

HARD_MAX_DEPTH = 4
DEFAULT_HIGH_PARALLEL_THREADS = DEFAULT_NORMAL_PARALLEL_LIMIT


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
