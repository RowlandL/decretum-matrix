"""Whole-tree role admission and write-scope rules for court agents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
    "shiguan-hermes": "taizi/menxia",
    "zaochao": "taizi",
    "patrol-inspector": "taizi",
}
_SIX_MINISTRY_ROLES = frozenset({"libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"})
_SPECIAL_LIFECYCLE_ROLES = frozenset(
    {"shiguan", "shiguan-hermes", "zaochao", "patrol-inspector"}
)
_FORMAL_HIERARCHY_ROLES = frozenset(
    {
        "taizi",
        "zhongshu",
        "menxia",
        "shangshu",
        *_SIX_MINISTRY_ROLES,
        *_SPECIAL_LIFECYCLE_ROLES,
    }
)
_WORKER_INSTANCE_KINDS = frozenset({"worker", "craftsman", "office_worker_instance"})
_CANONICAL_INSTANCE_KINDS = frozenset({"office", "canonical_authority"})


_CHILD_PROFILE_OUTER_FIELDS = {
    "role": "role_key",
    "instance_id": "office_instance_id",
    "owner_role": "owner_role",
    "direct_superior": "direct_superior",
    "instance_kind": "instance_kind",
    "canonical_authority": "canonical_authority",
    "child_role": "child_role",
    "bounded_mandate": "bounded_mandate",
    "expected_result": "expected_result",
    "read_scope": "read_scope",
    "write_set": "write_set",
    "task_id": "task_id",
    "dispatch_uid": "dispatch_uid",
    "shard_id": "shard_id",
    "attempt": "attempt",
    "expires_at_utc": "expires_at_utc",
    "terminal_condition": "terminal_condition",
}
_PRELOAD_HASH_FIELDS = ("profile_hash", "dossier_hash", "court_skill_hash")


def _normalized_preload_hashes(value: object) -> tuple[str, str, str] | None:
    if not isinstance(value, Mapping) or set(value) != set(_PRELOAD_HASH_FIELDS):
        return None
    hashes = tuple(str(value.get(field) or "").strip().lower() for field in _PRELOAD_HASH_FIELDS)
    if any(re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in hashes):
        return None
    return hashes[0], hashes[1], hashes[2]


def _child_profile_scope_binding_error(binding: Mapping[str, object]) -> str | None:
    profile = binding.get("child_profile")
    if not isinstance(profile, Mapping):
        return None
    for outer_field, profile_field in _CHILD_PROFILE_OUTER_FIELDS.items():
        if outer_field not in binding or binding.get(outer_field) != profile.get(profile_field):
            return "dispatch_hierarchy_child_scope_binding_mismatch"
    outer_hashes = _normalized_preload_hashes(binding.get("preload_hashes"))
    profile_hashes = (
        str(profile.get("profile_sha256") or "").strip().lower(),
        str(profile.get("dossier_sha256") or "").strip().lower(),
        str(profile.get("skill_sha256") or "").strip().lower(),
    )
    if outer_hashes is None or outer_hashes != profile_hashes:
        return "approved_budget_preload_mismatch"
    return None


def _special_lifecycle_hierarchy_decision(
    role: str,
    decision: DispatchHierarchyDecision,
) -> DispatchHierarchyDecision:
    if (
        role not in _SPECIAL_LIFECYCLE_ROLES
        or decision.reason_codes != ("dispatch_hierarchy_edge_forbidden",)
        or decision.normalized_caller
        not in _OFFICE_DIRECT_SUPERIORS[role].split("/")
    ):
        return decision
    return DispatchHierarchyDecision(
        allowed=True,
        edge_class="special_lifecycle_dispatch",
        normalized_caller=decision.normalized_caller,
        normalized_target=decision.normalized_target,
        normalized_owner=decision.normalized_owner,
        reason_codes=(),
        hierarchy_schema=decision.hierarchy_schema,
        hierarchy_manifest_sha256=decision.hierarchy_manifest_sha256,
    )


def scoped_hierarchy_denial(
    *,
    calling_office: object,
    requested_roles: Sequence[str],
    requested_bindings: Sequence[Mapping[str, object]] | None,
) -> DispatchHierarchyDecision | None:
    """Validate hierarchy-scoped requests before capacity or lease selection."""

    if (
        requested_bindings is None
        or isinstance(requested_bindings, (str, bytes))
        or len(requested_bindings) != len(requested_roles)
    ):
        for raw_role in requested_roles:
            role = str(raw_role or "").strip().lower()
            if role in _FORMAL_HIERARCHY_ROLES:
                return validate_dispatch_hierarchy(
                    action="dispatch",
                    calling_office=calling_office,
                    target_role=role,
                    target_direct_superior=_OFFICE_DIRECT_SUPERIORS[role],
                    instance_kind=None,
                    canonical_authority=None,
                    owner_role=None,
                    child_profile=None,
                )
        return None
    for role, binding in zip(requested_roles, requested_bindings):
        if not isinstance(binding, Mapping):
            continue
        canonical_authority = binding.get("canonical_authority")
        child_profile = binding.get("child_profile")
        instance_kind = (
            binding.get("instance_kind") or binding.get("office_instance_kind")
        )
        owner_role = binding.get("owner_role")
        child_shape = (
            canonical_authority is False
            or str(instance_kind or "").strip().lower() in _WORKER_INSTANCE_KINDS
            or owner_role not in {None, ""}
        )
        if not (
            (role in _FORMAL_HIERARCHY_ROLES and canonical_authority is True)
            or child_shape
            or child_profile is not None
        ):
            continue
        decision = validate_dispatch_hierarchy(
            action="dispatch",
            calling_office=calling_office,
            target_role=role,
            target_direct_superior=binding.get("direct_superior"),
            instance_kind=instance_kind,
            canonical_authority=canonical_authority,
            owner_role=owner_role,
            child_profile=child_profile,
        )
        decision = _special_lifecycle_hierarchy_decision(role, decision)
        if not decision.allowed:
            return decision
        profile_error = _child_profile_scope_binding_error(binding)
        if profile_error is not None:
            return DispatchHierarchyDecision(
                allowed=False,
                edge_class=None,
                normalized_caller=decision.normalized_caller,
                normalized_target=decision.normalized_target,
                normalized_owner=decision.normalized_owner,
                reason_codes=(profile_error,),
                hierarchy_schema=decision.hierarchy_schema,
                hierarchy_manifest_sha256=decision.hierarchy_manifest_sha256,
            )
    return None


_first_scoped_hierarchy_denial = scoped_hierarchy_denial


def validate_admission_instance_shape(
    bindings: Sequence[Mapping[str, object]],
    *,
    allow_taizi_singleton: bool,
    allow_worker_only: bool = False,
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
        if canonical_count > 1 or (
            len(instances) > 1
            and canonical_count == 0
            and not allow_worker_only
        ):
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


def _admission_lease_metadata_error(
    budget_lease: Mapping[str, object],
    *,
    calling_office: str,
    direct_superior: str,
    next_depth: int | None,
) -> str | None:
    if str(budget_lease.get("schema") or "") != "court.agent.admission_lease.v2":
        return "approved_budget_lease_schema_invalid"
    budget_id = str(budget_lease.get("budget_id") or "").strip()
    lease_id = str(budget_lease.get("lease_id") or "").strip()
    parent_budget_id = str(budget_lease.get("parent_budget_id") or "").strip()
    parent_id = str(budget_lease.get("parent_id") or "").strip().lower()
    approved_by = str(budget_lease.get("approved_by") or "").strip().lower()
    grantee_role = str(budget_lease.get("grantee_role") or "").strip().lower()
    if (
        not budget_id
        or not lease_id
        or not parent_budget_id
        or len({budget_id, lease_id, parent_budget_id}) != 3
    ):
        return "approved_budget_parent_binding_invalid"
    if (
        not calling_office
        or not direct_superior
        or parent_id != direct_superior
        or approved_by != direct_superior
        or grantee_role != calling_office
        or approved_by == calling_office
    ):
        return "approved_budget_parent_authority_mismatch"
    lease_depth = budget_lease.get("lease_depth")
    approved_next_depth = budget_lease.get("approved_next_depth")
    if (
        next_depth is None
        or isinstance(next_depth, bool)
        or not isinstance(next_depth, int)
        or isinstance(lease_depth, bool)
        or not isinstance(lease_depth, int)
        or isinstance(approved_next_depth, bool)
        or not isinstance(approved_next_depth, int)
        or lease_depth < 0
        or approved_next_depth != next_depth
        or approved_next_depth != lease_depth + 1
    ):
        return "approved_budget_depth_mismatch"
    expires_text = str(budget_lease.get("expires_at_utc") or "").strip()
    try:
        expires_at = datetime.fromisoformat(expires_text.replace("Z", "+00:00"))
    except ValueError:
        return "approved_budget_lease_expiry_invalid"
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        return "approved_budget_lease_expiry_invalid"
    if expires_at.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        return "approved_budget_lease_expired"
    return None


def _write_set_within_parent_scope(
    write_set: Sequence[str],
    parent_scope: Sequence[str],
) -> bool:
    return all(
        any(path == parent or path.startswith(f"{parent}/") for parent in parent_scope)
        for path in write_set
    )


def budget_lease_access_contract_error(
    budget_lease: Mapping[str, object] | None,
    bindings: Sequence[Mapping[str, object]],
) -> str | None:
    """Return a stable reason when current bindings escape the admitted lease access scope."""

    if not isinstance(budget_lease, Mapping):
        return "approved_budget_access_contract_invalid"
    if str(budget_lease.get("status") or "").strip().upper() != "ACTIVE":
        return "approved_budget_access_contract_invalid"
    approved_instances_raw = budget_lease.get("approved_instance_ids")
    approved_write_sets_raw = budget_lease.get("approved_write_sets")
    approved_access_raw = budget_lease.get("approved_access_contracts")
    if (
        not isinstance(approved_instances_raw, (list, tuple))
        or not isinstance(approved_write_sets_raw, Mapping)
        or (
            approved_access_raw is not None
            and not isinstance(approved_access_raw, Mapping)
        )
    ):
        return "approved_budget_access_contract_invalid"

    approved_instances = tuple(
        str(value or "").strip().lower() for value in approved_instances_raw
    )
    if (
        not approved_instances
        or any(not value for value in approved_instances)
        or len(set(approved_instances)) != len(approved_instances)
    ):
        return "approved_budget_access_contract_invalid"

    def normalized_mapping(value: Mapping[object, object]) -> dict[str, object] | None:
        normalized: dict[str, object] = {}
        for key, item in value.items():
            instance_id = str(key or "").strip().lower()
            if not instance_id or instance_id in normalized:
                return None
            normalized[instance_id] = item
        return normalized

    approved_write_sets = normalized_mapping(approved_write_sets_raw)
    approved_access_contracts = (
        normalized_mapping(approved_access_raw)
        if isinstance(approved_access_raw, Mapping)
        else None
    )
    if (
        approved_write_sets is None
        or set(approved_write_sets) != set(approved_instances)
        or (
            approved_access_contracts is not None
            and set(approved_access_contracts) != set(approved_instances)
        )
    ):
        return "approved_budget_access_contract_invalid"

    current_bindings: dict[str, Mapping[str, object]] = {}
    for binding in bindings:
        if not isinstance(binding, Mapping):
            return "approved_budget_access_contract_invalid"
        instance_id = str(binding.get("instance_id") or "").strip().lower()
        if not instance_id or instance_id in current_bindings:
            return "approved_budget_access_contract_invalid"
        current_bindings[instance_id] = binding
    if not current_bindings or not set(current_bindings).issubset(approved_instances):
        return "approved_budget_access_contract_mismatch"

    for instance_id, current_binding in current_bindings.items():
        current_contract = _normalized_access_contract(current_binding)
        approved_access = (
            approved_access_contracts.get(instance_id)
            if approved_access_contracts is not None
            else None
        )
        if approved_access is None:
            approved_access = {
                "access_mode": "read_write",
                "read_scope": approved_write_sets[instance_id],
                "mutation_allowed": True,
                "integration_authority": False,
            }
        if not isinstance(approved_access, Mapping):
            return "approved_budget_access_contract_invalid"
        approved_contract = _normalized_access_contract(
            {
                **approved_access,
                "write_set": approved_write_sets[instance_id],
            }
        )
        if current_contract is None or approved_contract is None:
            return "approved_budget_access_contract_invalid"
        if current_contract != approved_contract:
            return "approved_budget_access_contract_mismatch"
    return None


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
        validate_admission_instance_shape(
            bindings,
            allow_taizi_singleton=False,
            allow_worker_only=True,
        )
    except ValueError:
        return None, "approved_budget_instance_shape_mismatch"

    requested: dict[
        str,
        tuple[
            int,
            str,
            str,
            tuple[object, ...],
            tuple[str, bool, str, str],
            tuple[str, str, str],
        ],
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
        preload_hashes = _normalized_preload_hashes(binding.get("preload_hashes"))
        if (
            not role
            or role != requested_role
            or not instance_id
            or not shard_id
            or access_contract is None
            or preload_hashes is None
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
            preload_hashes,
        )
        requested_shards.add(shard_id)

    approved_roles_raw = budget_lease.get("approved_roles")
    approved_instances_raw = budget_lease.get("approved_instance_ids")
    approved_shards_raw = budget_lease.get("approved_shards")
    approved_write_sets = budget_lease.get("approved_write_sets")
    approved_access_contracts = budget_lease.get("approved_access_contracts")
    approved_instance_shapes = budget_lease.get("approved_instance_shapes")
    approved_preload_hashes_raw = budget_lease.get("approved_preload_hashes")
    parent_write_scope = _normalized_write_set(
        budget_lease.get("parent_write_scope"),
        allow_empty=True,
    )
    if (
        not isinstance(approved_roles_raw, (list, tuple))
        or not isinstance(approved_instances_raw, (list, tuple))
        or not isinstance(approved_shards_raw, (list, tuple))
        or not isinstance(approved_write_sets, Mapping)
        or not isinstance(approved_instance_shapes, Mapping)
        or not isinstance(approved_preload_hashes_raw, Mapping)
        or parent_write_scope is None
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
    normalized_preload_hashes: dict[str, tuple[str, str, str]] = {}
    for key, value in approved_preload_hashes_raw.items():
        instance_id = str(key or "").strip().lower()
        preload_hashes = _normalized_preload_hashes(value)
        if not instance_id or preload_hashes is None or instance_id in normalized_preload_hashes:
            return None, "approved_budget_preload_mismatch"
        normalized_preload_hashes[instance_id] = preload_hashes
    if set(normalized_preload_hashes) != set(approved_instances):
        return None, "approved_budget_preload_mismatch"
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
            allow_worker_only=True,
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
            requested_preload_hashes,
        ) = requested_binding
        if normalized_preload_hashes[instance_id] != requested_preload_hashes:
            return None, "approved_budget_preload_mismatch"
        if (
            role != requested_role
            or shard_id != requested_shard
            or normalized_access_contracts[instance_id] != requested_access_contract
            or normalized_instance_shapes[instance_id] != requested_instance_shape
        ):
            return None, "approved_budget_scope_mismatch"
        requested_write_set = requested_access_contract[1]
        if not isinstance(requested_write_set, tuple) or not _write_set_within_parent_scope(
            requested_write_set,
            parent_write_scope,
        ):
            return None, "approved_budget_parent_write_scope_mismatch"
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
    next_depth: int | None = None,
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
    lease_error = _admission_lease_metadata_error(
        budget_lease,
        calling_office=expected_caller,
        direct_superior=expected_superior,
        next_depth=next_depth,
    )
    if lease_error is not None:
        return None, lease_error
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
    next_depth: int | None = None,
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
        next_depth=next_depth,
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
    hierarchy_denial = _first_scoped_hierarchy_denial(
        calling_office=calling_office,
        requested_roles=roles,
        requested_bindings=requested_bindings,
    )
    if hierarchy_denial is not None:
        return RoleAdmissionDecision(
            False,
            (),
            roles,
            hierarchy_denial.reason_codes,
            None,
            None,
            None,
            None,
        )
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
        next_depth=next_depth,
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
