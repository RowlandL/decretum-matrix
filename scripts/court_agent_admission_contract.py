"""Hierarchy, preload, child-profile, and instance-shape admission contract."""

from __future__ import annotations

import re
import sys
from typing import Mapping, Sequence

sys.dont_write_bytecode = True

from court_dispatch_hierarchy import (
    DispatchHierarchyDecision,
    validate_dispatch_hierarchy,
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
_SIX_MINISTRY_ROLES = frozenset(
    {"libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"}
)
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
_WORKER_INSTANCE_KINDS = frozenset(
    {"worker", "craftsman", "office_worker_instance"}
)
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
    hashes = tuple(
        str(value.get(field) or "").strip().lower()
        for field in _PRELOAD_HASH_FIELDS
    )
    if any(re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in hashes):
        return None
    return hashes[0], hashes[1], hashes[2]


def _child_profile_scope_binding_error(
    binding: Mapping[str, object],
) -> str | None:
    profile = binding.get("child_profile")
    if not isinstance(profile, Mapping):
        return None
    for outer_field, profile_field in _CHILD_PROFILE_OUTER_FIELDS.items():
        if outer_field not in binding or binding.get(outer_field) != profile.get(
            profile_field
        ):
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
        instance_kind = binding.get("instance_kind") or binding.get(
            "office_instance_kind"
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
            raise ValueError(
                "instance_shape_gate: exact role/instance/kind/canonical binding required"
            )
        if canonical_authority:
            if instance_kind not in _CANONICAL_INSTANCE_KINDS:
                raise ValueError(
                    "canonical_authority_shape_gate: canonical instance kind mismatch"
                )
        elif instance_kind not in _WORKER_INSTANCE_KINDS:
            raise ValueError(
                "office_worker_instance_shape_gate: non-canonical instance must be a worker"
            )
        by_role.setdefault(role, []).append(
            (instance_id, instance_kind, canonical_authority)
        )

    for role, instances in by_role.items():
        canonical_count = sum(
            1 for _instance, _kind, canonical in instances if canonical
        )
        if role == "taizi":
            if (
                not allow_taizi_singleton
                or len(instances) != 1
                or canonical_count != 1
            ):
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
