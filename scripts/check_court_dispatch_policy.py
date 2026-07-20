"""Regression checks for court mode and dynamic office dispatch policy."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Mapping, Sequence

sys.dont_write_bytecode = True

import court_agent_admission as _admission
import court_multi_agent_protocol as _protocol
from court_dispatch_policy import select_wave as _select_wave, validate_dispatch_plan
from court_native_execution import AUTHORITIES, BEHAVIORS, select_native_execution
from court_multi_agent_protocol import admit_roles as _admit_roles
from court_office_bootstrap import canonical_child_office_binding_sha256


TARGET_SUPERIORS = {
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
MINISTRY_ROLES = ("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu")
DISPATCH_PRELOAD_BY_ROLE: dict[str, dict[str, str]] = {}
BOUND_PRELOAD_HASHES = {
    "profile_hash": "1" * 64,
    "dossier_hash": "2" * 64,
    "court_skill_hash": "3" * 64,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_admission_facade() -> dict[str, object]:
    exports = (
        "RoleAdmissionDecision",
        "admit_roles",
        "approved_budget_limit",
        "approved_budget_selection",
        "canonical_repo_relative_paths",
        "repository_paths_overlap",
        "validate_admission_instance_shape",
    )
    for name in exports:
        require(
            getattr(_protocol, name) is getattr(_admission, name),
            f"court_multi_agent_protocol stopped re-exporting {name}",
        )
    require(
        _protocol.HARD_MAX_DEPTH == _admission.HARD_MAX_DEPTH,
        "HARD_MAX_DEPTH facade value drifted",
    )
    require(
        _protocol.DEFAULT_HIGH_PARALLEL_THREADS
        == _admission.DEFAULT_HIGH_PARALLEL_THREADS,
        "DEFAULT_HIGH_PARALLEL_THREADS facade value drifted",
    )
    return {
        "exports": list(exports),
        "hard_max_depth": _protocol.HARD_MAX_DEPTH,
        "default_high_parallel_threads": _protocol.DEFAULT_HIGH_PARALLEL_THREADS,
    }


def active_budget(
    approved_count: int,
    *,
    task_id: str = "dispatch-policy-check",
    calling_office: str = "shangshu",
    direct_superior: str = "taizi",
    approved_roles: Sequence[str] | None = None,
    **overrides: object,
) -> dict[str, object]:
    budget_id = f"budget:{task_id}:phase:wave"
    result: dict[str, object] = {
        "schema": "court.agent.admission_lease.v2",
        "budget_id": budget_id,
        "lease_id": f"lease-{task_id}-{approved_count}",
        "parent_budget_id": f"{budget_id}:{direct_superior}",
        "parent_id": direct_superior,
        "approved_by": direct_superior,
        "grantee_role": calling_office,
        "expires_at_utc": "2099-01-01T00:00:00+00:00",
        "status": "ACTIVE",
        "approved_count": approved_count,
        "task_id": task_id,
        "calling_office": calling_office,
        "direct_superior": direct_superior,
    }
    if approved_roles is not None:
        result["approved_roles"] = list(approved_roles)
    result.update(overrides)
    return result


def _bindings(
    roles: Sequence[str],
    overrides: Mapping[int, Mapping[str, object]] | None = None,
) -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    result: list[dict[str, object]] = []
    for index, raw_role in enumerate(roles):
        role = str(raw_role).strip().lower()
        counts[role] = counts.get(role, 0) + 1
        number = counts[role]
        worker = number > 1 and role in {"libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"}
        binding: dict[str, object] = {
            "role": role,
            "instance_id": f"{role}#{number:04d}",
            "shard_id": f"{role}-shard-{number:04d}",
            "write_set": [f"work/{role}/{number:04d}.txt"],
            "access_mode": "read_write",
            "read_scope": [f"work/{role}/{number:04d}.txt"],
            "mutation_allowed": True,
            "integration_authority": False,
            "preload_hashes": dict(BOUND_PRELOAD_HASHES),
            "direct_superior": role if worker else TARGET_SUPERIORS.get(role, "shangshu"),
            "instance_kind": "office_worker_instance" if worker else "office",
            "canonical_authority": number == 1,
            "owner_role": role if worker else None,
        }
        if overrides and index in overrides:
            binding.update(overrides[index])
        profile = binding.get("child_profile")
        if isinstance(profile, Mapping):
            for outer_field, profile_field in {
                "child_role": "child_role",
                "bounded_mandate": "bounded_mandate",
                "expected_result": "expected_result",
                "task_id": "task_id",
                "dispatch_uid": "dispatch_uid",
                "attempt": "attempt",
                "expires_at_utc": "expires_at_utc",
                "terminal_condition": "terminal_condition",
            }.items():
                binding.setdefault(outer_field, profile.get(profile_field))
        result.append(binding)
    return result


def _bounded_child_profile(
    *,
    owner_role: str = "gongbu",
    office_instance_id: str = "gongbu#0001",
    ordinal: int = 1,
) -> dict[str, object]:
    return {
        "schema": "court.child_office_profile.v1",
        "child_role": "GongBu-GongJiang",
        "role_key": owner_role,
        "office_instance_id": office_instance_id,
        "owner_role": owner_role,
        "direct_superior": owner_role,
        "canonical_authority": False,
        "instance_kind": "office_worker_instance",
        "bounded_mandate": "execute one bounded Gongbu implementation shard",
        "expected_result": "return one structured implementation receipt",
        "read_scope": [f"work/{owner_role}/{ordinal:04d}.txt"],
        "write_set": [f"work/{owner_role}/{ordinal:04d}.txt"],
        "task_id": "dispatch-policy-child-profile",
        "dispatch_uid": f"DSP-DISPATCH-POLICY-CHILD-{ordinal:04d}",
        "shard_id": f"{owner_role}-shard-{ordinal:04d}",
        "attempt": 1,
        "profile_sha256": "1" * 64,
        "dossier_sha256": "2" * 64,
        "skill_sha256": "3" * 64,
        "terminal_condition": "stop after the bounded receipt is accepted",
        "expires_at_utc": "2099-01-01T00:00:00Z",
        "dispatch_context_packet_schema": "court.semantic.dispatch_context_packet.v1",
        "dispatch_context_packet_sha256": "4" * 64,
        "semantic_receipt_sha256": "5" * 64,
        "invariant_capsule_schema": "court.semantic.invariant_capsule.v1",
        "invariant_capsule_sha256": "6" * 64,
    }


def _approved_scope_kwargs(
    roles: Sequence[str],
    budget_lease: Mapping[str, object] | None,
    *,
    integration_domain: str,
    authority: str,
    binding_overrides: Mapping[int, Mapping[str, object]] | None,
    next_depth: int = 2,
) -> dict[str, object]:
    requested_bindings = _bindings(roles, binding_overrides)
    if budget_lease is None:
        return {
            "budget_lease": None,
            "requested_bindings": requested_bindings,
            "integration_domain": integration_domain,
            "authority": authority,
        }
    lease = dict(budget_lease)
    approved_count = lease.get("approved_count")
    count = approved_count if isinstance(approved_count, int) and not isinstance(approved_count, bool) else 0
    approved_roles = [str(role).strip().lower() for role in lease.get("approved_roles", list(roles[:count]))]
    available_by_role: dict[str, list[dict[str, object]]] = {}
    for binding in requested_bindings:
        available_by_role.setdefault(str(binding["role"]), []).append(binding)
    approved_bindings: list[dict[str, object]] = []
    for role in approved_roles:
        candidates = available_by_role.get(role, [])
        if candidates:
            approved_bindings.append(candidates.pop(0))
        else:
            approved_bindings.extend(_bindings((role,)))
    lease.setdefault("approved_roles", [binding["role"] for binding in approved_bindings])
    lease.setdefault("approved_instance_ids", [binding["instance_id"] for binding in approved_bindings])
    lease.setdefault("approved_shards", [binding["shard_id"] for binding in approved_bindings])
    lease.setdefault(
        "approved_write_sets",
        {str(binding["instance_id"]): list(binding["write_set"]) for binding in approved_bindings},
    )
    lease.setdefault(
        "parent_write_scope",
        sorted(
            {
                str(path)
                for binding in approved_bindings
                for path in binding["write_set"]
            }
        ),
    )
    lease.setdefault(
        "approved_access_contracts",
        {
            str(binding["instance_id"]): {
                "access_mode": binding["access_mode"],
                "read_scope": list(binding["read_scope"]),
                "mutation_allowed": binding["mutation_allowed"],
                "integration_authority": binding["integration_authority"],
            }
            for binding in approved_bindings
        },
    )
    lease.setdefault(
        "approved_instance_shapes",
        {
            str(binding["instance_id"]): {
                "instance_kind": binding["instance_kind"],
                "canonical_authority": binding["canonical_authority"],
                "owner_role": binding["owner_role"],
                "direct_superior": binding["direct_superior"],
            }
            for binding in approved_bindings
        },
    )
    lease.setdefault(
        "approved_binding_sha256s",
        {
            str(binding["instance_id"]): canonical_child_office_binding_sha256(
                binding
            )
            for binding in approved_bindings
            if isinstance(binding.get("child_profile"), Mapping)
        },
    )
    lease.setdefault("lease_depth", max(0, int(next_depth) - 1))
    lease.setdefault("approved_next_depth", int(next_depth))
    lease.setdefault(
        "approved_preload_hashes",
        {
            str(binding["instance_id"]): dict(binding["preload_hashes"])
            for binding in approved_bindings
        },
    )
    lease.setdefault("integration_domain", integration_domain)
    lease.setdefault("authority", authority)
    return {
        "budget_lease": lease,
        "requested_bindings": requested_bindings,
        "integration_domain": integration_domain,
        "authority": authority,
    }


def select_wave(*args: object, **kwargs: object) -> object:
    roles = tuple(kwargs.get("useful_roles") or (args[0] if args else ()))
    integration_domain = str(kwargs.pop("integration_domain", "dispatch-policy"))
    authority = str(kwargs.pop("authority", "super"))
    binding_overrides = kwargs.pop("binding_overrides", None)
    budget_lease = kwargs.pop("budget_lease", None)
    kwargs.update(
        _approved_scope_kwargs(
            roles,
            budget_lease if isinstance(budget_lease, Mapping) else None,
            integration_domain=integration_domain,
            authority=authority,
            binding_overrides=binding_overrides if isinstance(binding_overrides, Mapping) else None,
            next_depth=int(kwargs.get("next_depth") or 0),
        )
    )
    return _select_wave(*args, **kwargs)


def admit_roles(**kwargs: object) -> object:
    roles = tuple(kwargs.get("requested_roles") or ())
    integration_domain = str(kwargs.pop("integration_domain", "dispatch-policy"))
    authority = str(kwargs.pop("authority", "super"))
    binding_overrides = kwargs.pop("binding_overrides", None)
    budget_lease = kwargs.pop("budget_lease", None)
    kwargs.update(
        _approved_scope_kwargs(
            roles,
            budget_lease if isinstance(budget_lease, Mapping) else None,
            integration_domain=integration_domain,
            authority=authority,
            binding_overrides=binding_overrides if isinstance(binding_overrides, Mapping) else None,
            next_depth=int(kwargs.get("next_depth") or 0),
        )
    )
    return _admit_roles(**kwargs)


def check_mode_semantics() -> dict[str, object]:
    combinations: list[dict[str, object]] = []
    for authority in sorted(AUTHORITIES):
        for behavior in sorted(BEHAVIORS):
            selection = select_native_execution(authority=authority, behavior=behavior)
            require(selection.authority == authority, "structured authority drift")
            require(selection.behavior == behavior, "structured behavior drift")
            combinations.append(selection.as_dict())
    require(len(combinations) == 6, "authority/behavior cartesian product incomplete")
    return {"cartesian": combinations}


def check_dynamic_capacity() -> dict[str, object]:
    six = select_wave(
        useful_roles=["libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"],
        host_capacity=8,
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        host_retained=0,
        next_depth=1,
        budget_lease=active_budget(6),
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(six.selected_roles == ("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"), "six useful roles did not fit seven free slots")
    require(six.static_wave_cap is None, "a static ordinary wave cap remains")

    current_host = select_wave(
        useful_roles=["zhongshu", "menxia", "shangshu", "shiguan"],
        host_capacity=4,
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        host_retained=0,
        next_depth=1,
        budget_lease=active_budget(
            4,
            calling_office="taizi",
            direct_superior="user",
        ),
        task_id="dispatch-policy-check",
        calling_office="taizi",
        direct_superior="user",
    )
    require(current_host.selected_roles == ("zhongshu", "menxia", "shangshu"), "four-slot host selected the wrong roles")
    require(current_host.deferred_roles == ("shiguan",), "four-slot host did not defer the fourth role")
    require(current_host.reason == "runtime_capacity", "capacity deferral reported the wrong reason")
    forty_roles = tuple(f"role-{index:02d}" for index in range(1, 41))
    explicit_high_parallel = select_wave(
        useful_roles=forty_roles,
        host_capacity=64,
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        host_retained=0,
        next_depth=1,
        max_threads=48,
        explicit_parallel_count=48,
        parallel_control_source="latest_user_explicit",
        budget_lease=active_budget(40),
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(len(explicit_high_parallel.selected_roles) == 40, "explicit 48-thread setting was hard-clamped below the requested work")
    require(explicit_high_parallel.deferred_roles == (), "roles were deferred solely because total count exceeded sixteen")
    require(explicit_high_parallel.effective_host_capacity == 48, "configured threads above 16 were not preserved")
    protocol_high_parallel = admit_roles(
        host_capacity=64,
        active_threads=1,
        retained_threads=0,
        requested_roles=forty_roles,
        max_threads=48,
        explicit_parallel_count=48,
        parallel_control_source="latest_user_explicit",
        next_depth=1,
        max_depth=4,
        budget_lease=active_budget(40),
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(protocol_high_parallel.allowed is True, "protocol admission rejected a valid high-parallel wave")
    require(len(protocol_high_parallel.selected_roles) == 40, "protocol admission hard-clamped total threads to sixteen")

    host_limited = select_wave(
        useful_roles=forty_roles,
        host_capacity=24,
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        host_retained=0,
        next_depth=1,
        max_threads=64,
        explicit_parallel_count=64,
        parallel_control_source="latest_user_explicit",
        budget_lease=active_budget(40),
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(len(host_limited.selected_roles) == 23, "real host capacity did not remain the admission gate")
    require(host_limited.reason == "runtime_capacity", "host rejection/capacity reported the wrong gate")

    budget_limited = select_wave(
        useful_roles=forty_roles,
        host_capacity=64,
        host_active=1,
        user_agent_budget=7,
        provider_launch_budget=9,
        host_retained=0,
        next_depth=1,
        max_threads=48,
        explicit_parallel_count=48,
        parallel_control_source="latest_user_explicit",
        budget_lease=active_budget(40),
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(len(budget_limited.selected_roles) == 7, "user/resource budget stopped gating a high-parallel wave")
    require(budget_limited.reason == "user_budget", "budget-limited wave reported the wrong gate")

    approved_prefix = select_wave(
        useful_roles=forty_roles,
        host_capacity=64,
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        host_retained=0,
        next_depth=1,
        max_threads=48,
        explicit_parallel_count=48,
        parallel_control_source="latest_user_explicit",
        budget_lease=active_budget(7),
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(len(approved_prefix.selected_roles) == 7, "dispatch selected more roles than the approved lease count")
    require(approved_prefix.reason == "approved_budget", "approved lease limit reported the wrong gate")
    protocol_approved_prefix = admit_roles(
        host_capacity=64,
        active_threads=1,
        retained_threads=0,
        requested_roles=forty_roles,
        max_threads=48,
        explicit_parallel_count=48,
        parallel_control_source="latest_user_explicit",
        next_depth=1,
        max_depth=4,
        budget_lease=active_budget(7),
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(len(protocol_approved_prefix.selected_roles) == 7, "protocol admitted roles beyond the approved lease count")

    missing_budget = select_wave(
        useful_roles=("gongbu",),
        host_capacity=4,
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        host_retained=0,
        next_depth=1,
        budget_lease=None,
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(missing_budget.selected_roles == () and missing_budget.reason == "approved_budget_missing", "missing approved budget did not fail closed")
    inactive_budget = select_wave(
        useful_roles=("gongbu",),
        host_capacity=4,
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        host_retained=0,
        next_depth=1,
        budget_lease={**active_budget(1), "status": "PENDING"},
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(inactive_budget.selected_roles == () and inactive_budget.reason == "approved_budget_not_active", "inactive budget lease did not fail closed")
    insufficient_budget = select_wave(
        useful_roles=("gongbu",),
        host_capacity=4,
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        host_retained=0,
        next_depth=1,
        budget_lease=active_budget(0),
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(insufficient_budget.selected_roles == () and insufficient_budget.reason == "approved_budget_insufficient", "zero approved_count did not fail closed")
    task_mismatch = select_wave(
        useful_roles=("gongbu",),
        host_capacity=4,
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        host_retained=0,
        next_depth=1,
        budget_lease=active_budget(1, task_id="different-task"),
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(task_mismatch.selected_roles == () and task_mismatch.reason == "approved_budget_task_mismatch", "budget task mismatch did not fail closed")
    hierarchy_mismatch = select_wave(
        useful_roles=("gongbu",),
        host_capacity=4,
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        host_retained=0,
        next_depth=1,
        budget_lease=active_budget(1, calling_office="taizi"),
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(hierarchy_mismatch.selected_roles == () and hierarchy_mismatch.reason == "approved_budget_hierarchy_mismatch", "budget hierarchy mismatch did not fail closed")
    protocol_missing_budget = admit_roles(
        host_capacity=4,
        active_threads=1,
        retained_threads=0,
        requested_roles=("gongbu",),
        max_threads=32,
        next_depth=1,
        max_depth=4,
        budget_lease=None,
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(protocol_missing_budget.allowed is False and protocol_missing_budget.reason_codes == ("approved_budget_missing",), "protocol missing budget did not fail closed")

    role_scope_mismatch = select_wave(
        useful_roles=("gongbu",), host_capacity=4, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, host_retained=0, next_depth=1,
        budget_lease=active_budget(1, approved_roles=("menxia",)),
        task_id="dispatch-policy-check", calling_office="shangshu", direct_superior="taizi",
    )
    require(role_scope_mismatch.selected_roles == () and role_scope_mismatch.reason == "approved_budget_scope_mismatch", "approved_roles=[menxia] allowed gongbu")
    instance_scope_mismatch = select_wave(
        useful_roles=("gongbu",), host_capacity=4, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, host_retained=0, next_depth=1,
        budget_lease=active_budget(1, approved_instance_ids=["gongbu#9999"]),
        task_id="dispatch-policy-check", calling_office="shangshu", direct_superior="taizi",
    )
    require(instance_scope_mismatch.selected_roles == () and instance_scope_mismatch.reason == "approved_budget_scope_mismatch", "unapproved instance id was admitted")
    shard_scope_mismatch = select_wave(
        useful_roles=("gongbu",), host_capacity=4, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, host_retained=0, next_depth=1,
        budget_lease=active_budget(1, approved_shards=["unapproved-shard"]),
        task_id="dispatch-policy-check", calling_office="shangshu", direct_superior="taizi",
    )
    require(shard_scope_mismatch.selected_roles == () and shard_scope_mismatch.reason == "approved_budget_scope_mismatch", "unapproved shard was admitted")
    write_set_scope_mismatch = select_wave(
        useful_roles=("gongbu",), host_capacity=4, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, host_retained=0, next_depth=1,
        budget_lease=active_budget(1, approved_write_sets={"gongbu#0001": ["work/other.txt"]}),
        task_id="dispatch-policy-check", calling_office="shangshu", direct_superior="taizi",
    )
    require(write_set_scope_mismatch.selected_roles == () and write_set_scope_mismatch.reason == "approved_budget_scope_mismatch", "unapproved write set was admitted")
    integration_domain_mismatch = select_wave(
        useful_roles=("gongbu",), host_capacity=4, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, host_retained=0, next_depth=1,
        budget_lease=active_budget(1, integration_domain="other-domain"),
        task_id="dispatch-policy-check", calling_office="shangshu", direct_superior="taizi",
    )
    require(integration_domain_mismatch.selected_roles == () and integration_domain_mismatch.reason == "approved_budget_integration_domain_mismatch", "integration-domain mismatch was admitted")
    authority_mismatch = select_wave(
        useful_roles=("gongbu",), host_capacity=4, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, host_retained=0, next_depth=1,
        budget_lease=active_budget(1, authority="approval"),
        task_id="dispatch-policy-check", calling_office="shangshu", direct_superior="taizi",
    )
    require(authority_mismatch.selected_roles == () and authority_mismatch.reason == "approved_budget_authority_mismatch", "authority mismatch was admitted")
    ministry_parent_mismatch = select_wave(
        useful_roles=("gongbu",), host_capacity=4, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, host_retained=0, next_depth=1,
        budget_lease=active_budget(1), binding_overrides={0: {"direct_superior": "taizi"}},
        task_id="dispatch-policy-check", calling_office="shangshu", direct_superior="taizi",
    )
    require(ministry_parent_mismatch.selected_roles == () and ministry_parent_mismatch.reason == "dispatch_hierarchy_target_superior_mismatch", "six-ministry direct superior mismatch was admitted")
    worker_parent_mismatch = select_wave(
        useful_roles=("gongbu",), host_capacity=4, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, host_retained=0, next_depth=1,
        budget_lease=active_budget(
            1,
            calling_office="gongbu",
            direct_superior="shangshu",
        ),
        binding_overrides={
            0: {
                "instance_kind": "worker",
                "canonical_authority": False,
                "owner_role": "gongbu",
                "direct_superior": "shangshu",
                "child_profile": _bounded_child_profile(),
            }
        },
        task_id="dispatch-policy-check", calling_office="gongbu", direct_superior="shangshu",
    )
    require(worker_parent_mismatch.selected_roles == () and worker_parent_mismatch.reason == "dispatch_hierarchy_target_superior_mismatch", "worker was admitted above its owning ministry")
    protocol_role_scope_mismatch = admit_roles(
        host_capacity=4, active_threads=1, retained_threads=0,
        requested_roles=("gongbu",), max_threads=32, next_depth=1, max_depth=4,
        budget_lease=active_budget(1, approved_roles=("menxia",)),
        task_id="dispatch-policy-check", calling_office="shangshu", direct_superior="taizi",
    )
    require(protocol_role_scope_mismatch.allowed is False and protocol_role_scope_mismatch.reason_codes == ("approved_budget_scope_mismatch",), "protocol admitted an unapproved role")
    non_prefix_approved = select_wave(
        useful_roles=("gongbu", "xingbu"), host_capacity=4, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, host_retained=0, next_depth=1,
        budget_lease=active_budget(1, approved_roles=("xingbu",)),
        task_id="dispatch-policy-check", calling_office="shangshu", direct_superior="taizi",
    )
    require(
        non_prefix_approved.selected_roles == ("xingbu",)
        and non_prefix_approved.deferred_roles == ("gongbu",),
        "dispatch did not select only the non-prefix instance approved by the lease",
    )
    protocol_duplicate_instances = admit_roles(
        host_capacity=4, active_threads=1, retained_threads=0,
        requested_roles=("gongbu", "gongbu"), max_threads=32, next_depth=1, max_depth=4,
        budget_lease=active_budget(
            2,
            approved_roles=("gongbu", "gongbu"),
            calling_office="gongbu",
            direct_superior="shangshu",
        ),
        task_id="dispatch-policy-check", calling_office="gongbu", direct_superior="shangshu",
        binding_overrides={
            0: {
                "instance_kind": "office_worker_instance",
                "canonical_authority": False,
                "owner_role": "gongbu",
                "direct_superior": "gongbu",
                "child_profile": _bounded_child_profile(
                    office_instance_id="gongbu#0001",
                    ordinal=1,
                ),
            },
            1: {
                "instance_kind": "office_worker_instance",
                "canonical_authority": False,
                "owner_role": "gongbu",
                "direct_superior": "gongbu",
                "child_profile": _bounded_child_profile(
                    office_instance_id="gongbu#0002",
                    ordinal=2,
                ),
            },
        },
    )
    require(
        protocol_duplicate_instances.allowed is True
        and protocol_duplicate_instances.selected_roles == ("gongbu", "gongbu"),
        "protocol deduplicated distinct approved instances that share one role",
    )
    worker_owner_not_ministry = select_wave(
        useful_roles=("gongbu",), host_capacity=4, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, host_retained=0, next_depth=1,
        budget_lease=active_budget(
            1,
            calling_office="menxia",
            direct_superior="taizi",
        ),
        binding_overrides={
            0: {
                "instance_kind": "worker",
                "canonical_authority": False,
                "owner_role": "menxia",
                "direct_superior": "menxia",
                "child_profile": _bounded_child_profile(owner_role="menxia"),
            }
        },
        task_id="dispatch-policy-check", calling_office="menxia", direct_superior="taizi",
    )
    require(
        worker_owner_not_ministry.selected_roles == ()
        and worker_owner_not_ministry.reason == "dispatch_hierarchy_child_owner_mismatch",
        "worker owner outside the six ministries was admitted",
    )

    depth_four = select_wave(
        useful_roles=("xingbu",), host_capacity=16, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, next_depth=4,
        host_retained=0,
        budget_lease=active_budget(1), task_id="dispatch-policy-check",
        calling_office="shangshu", direct_superior="taizi",
    )
    require(depth_four.selected_roles == ("xingbu",), "next_depth=4 should be allowed")
    depth_five = select_wave(
        useful_roles=("xingbu",), host_capacity=16, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, next_depth=5,
        host_retained=0,
        budget_lease=active_budget(1), task_id="dispatch-policy-check",
        calling_office="shangshu", direct_superior="taizi",
    )
    require(depth_five.selected_roles == (), "next_depth=5 should fail closed")
    require(depth_five.reason == "max_depth_exceeded", "depth overflow reported the wrong reason")

    unknown = select_wave(
        useful_roles=("xingbu",), host_capacity=None, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, next_depth=1,
        host_retained=0,
        budget_lease=active_budget(1), task_id="dispatch-policy-check",
        calling_office="shangshu", direct_superior="taizi",
    )
    require(unknown.selected_roles == () and unknown.reason == "host_capacity_unknown", "unknown capacity did not fail closed")
    unknown_occupancy = select_wave(
        useful_roles=("xingbu",), host_capacity=16, host_active=None,
        user_agent_budget=None, provider_launch_budget=None, next_depth=1,
        host_retained=0,
        budget_lease=active_budget(1), task_id="dispatch-policy-check",
        calling_office="shangshu", direct_superior="taizi",
    )
    require(unknown_occupancy.selected_roles == () and unknown_occupancy.reason == "host_occupancy_unknown", "unknown occupancy did not fail closed")
    unknown_depth = select_wave(
        useful_roles=("xingbu",), host_capacity=16, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, next_depth=None,
        host_retained=0,
        budget_lease=active_budget(1), task_id="dispatch-policy-check",
        calling_office="shangshu", direct_superior="taizi",
    )
    require(unknown_depth.selected_roles == () and unknown_depth.reason == "next_depth_unknown", "unknown depth did not fail closed")

    unknown_reclamation = select_wave(
        useful_roles=("zhongshu", "menxia", "shangshu"),
        host_capacity=4,
        host_active=1,
        host_retained=3,
        host_reclamation_verified=None,
        user_agent_budget=None,
        provider_launch_budget=None,
        next_depth=1,
        budget_lease=active_budget(
            3,
            calling_office="taizi",
            direct_superior="user",
        ),
        task_id="dispatch-policy-check",
        calling_office="taizi",
        direct_superior="user",
    )
    require(
        unknown_reclamation.selected_roles == ()
        and unknown_reclamation.reason == "host_reclamation_unknown",
        "retained terminal nodes with unknown reclamation did not fail closed",
    )
    retained_not_reclaimed = select_wave(
        useful_roles=("zhongshu", "menxia", "shangshu"),
        host_capacity=4,
        host_active=1,
        host_retained=3,
        host_reclamation_verified=False,
        user_agent_budget=None,
        provider_launch_budget=None,
        next_depth=1,
        budget_lease=active_budget(
            3,
            calling_office="taizi",
            direct_superior="user",
        ),
        task_id="dispatch-policy-check",
        calling_office="taizi",
        direct_superior="user",
    )
    require(
        retained_not_reclaimed.selected_roles == ()
        and retained_not_reclaimed.reason == "runtime_capacity",
        "known retained terminal nodes were not counted against host capacity",
    )
    retained_reclaimed = select_wave(
        useful_roles=("zhongshu", "menxia", "shangshu"),
        host_capacity=4,
        host_active=1,
        host_retained=3,
        host_reclamation_verified=True,
        user_agent_budget=None,
        provider_launch_budget=None,
        next_depth=1,
        budget_lease=active_budget(
            3,
            calling_office="taizi",
            direct_superior="user",
        ),
        task_id="dispatch-policy-check",
        calling_office="taizi",
        direct_superior="user",
    )
    require(
        retained_reclaimed.selected_roles == ("zhongshu", "menxia", "shangshu"),
        "verified terminal-node reclamation did not restore active-only capacity",
    )
    return {
        "six_roles": six.__dict__,
        "current_host": current_host.__dict__,
        "explicit_high_parallel": explicit_high_parallel.__dict__,
        "protocol_high_parallel": protocol_high_parallel.__dict__,
        "host_limited": host_limited.__dict__,
        "budget_limited": budget_limited.__dict__,
        "approved_prefix": approved_prefix.__dict__,
        "protocol_approved_prefix": protocol_approved_prefix.__dict__,
        "missing_budget": missing_budget.__dict__,
        "inactive_budget": inactive_budget.__dict__,
        "insufficient_budget": insufficient_budget.__dict__,
        "task_mismatch": task_mismatch.__dict__,
        "hierarchy_mismatch": hierarchy_mismatch.__dict__,
        "protocol_missing_budget": protocol_missing_budget.__dict__,
        "role_scope_mismatch": role_scope_mismatch.__dict__,
        "instance_scope_mismatch": instance_scope_mismatch.__dict__,
        "shard_scope_mismatch": shard_scope_mismatch.__dict__,
        "write_set_scope_mismatch": write_set_scope_mismatch.__dict__,
        "integration_domain_mismatch": integration_domain_mismatch.__dict__,
        "authority_mismatch": authority_mismatch.__dict__,
        "ministry_parent_mismatch": ministry_parent_mismatch.__dict__,
        "worker_parent_mismatch": worker_parent_mismatch.__dict__,
        "protocol_role_scope_mismatch": protocol_role_scope_mismatch.__dict__,
        "non_prefix_approved": non_prefix_approved.__dict__,
        "protocol_duplicate_instances": protocol_duplicate_instances.__dict__,
        "worker_owner_not_ministry": worker_owner_not_ministry.__dict__,
        "depth_four": depth_four.__dict__,
        "depth_five": depth_five.__dict__,
        "unknown": unknown.__dict__,
        "unknown_occupancy": unknown_occupancy.__dict__,
        "unknown_depth": unknown_depth.__dict__,
        "unknown_reclamation": unknown_reclamation.__dict__,
        "retained_not_reclaimed": retained_not_reclaimed.__dict__,
        "retained_reclaimed": retained_reclaimed.__dict__,
    }


def dispatch_item(role: str, office_zh: str, duty: str, direct_superior: str = "shangshu") -> dict[str, object]:
    preload = DISPATCH_PRELOAD_BY_ROLE[role]
    return {
        "role": role,
        "office_zh": office_zh,
        "duty": duty,
        "direct_superior": direct_superior,
        "dependency_roles": [],
        "parallel_group": "review",
        "allowed_actions": ["read", "report"],
        "forbidden_actions": ["mutate_unrelated_state"],
        "evidence_contract": "return bounded findings with source pointers",
        "stop_conditions": ["scope_change"],
        "visibility": "non_visible",
        "instance_key": f"{role}#0001",
        "profile_path": preload["profile_path"],
        "dossier_path": preload["dossier_path"],
        "skill_path": preload["skill_path"],
        "profile_hash": preload["profile_hash"],
        "dossier_hash": preload["dossier_hash"],
        "court_skill_hash": preload["court_skill_hash"],
        "preload_ack": "PASSED",
    }


def _initialize_dispatch_preload(root: Path) -> None:
    DISPATCH_PRELOAD_BY_ROLE.clear()
    skill = root / "SKILL.md"
    skill.write_text("fixture court skill\n", encoding="utf-8")
    skill_hash = hashlib.sha256(skill.read_bytes()).hexdigest()
    for role in TARGET_SUPERIORS:
        profile_rel = f"agents/standing-officials/{role}.toml"
        dossier_rel = f"agents/office-dossiers/{role}/AGENTS.md"
        profile = root / profile_rel
        dossier = root / dossier_rel
        profile.parent.mkdir(parents=True, exist_ok=True)
        dossier.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text(f"role = {role!r}\n", encoding="utf-8")
        dossier.write_text(f"# {role} fixture dossier\n", encoding="utf-8")
        DISPATCH_PRELOAD_BY_ROLE[role] = {
            "profile_path": profile_rel,
            "dossier_path": dossier_rel,
            "skill_path": "SKILL.md",
            "profile_hash": hashlib.sha256(profile.read_bytes()).hexdigest(),
            "dossier_hash": hashlib.sha256(dossier.read_bytes()).hexdigest(),
            "court_skill_hash": skill_hash,
            "preload_ack": "PASSED",
        }


def _dispatch_manifest(entries: Sequence[Mapping[str, object]]) -> dict[str, dict[str, str]]:
    return {
        str(entry["instance_key"]): dict(DISPATCH_PRELOAD_BY_ROLE[str(entry["role"])])
        for entry in entries
    }


def check_dispatch_plan() -> dict[str, object]:
    valid_entries = [
        dispatch_item("libu", "礼部", "report wording"),
        dispatch_item("xingbu", "刑部", "risk review"),
    ]
    plan = validate_dispatch_plan(
        valid_entries,
        authority="super",
        behavior="parallel",
        trusted_preload_manifest=_dispatch_manifest(valid_entries),
    )
    require(plan.roles == ("libu", "xingbu"), "dispatch plan forced unrelated ministries")
    require(plan.unjustified_roles == (), "valid duties were marked unjustified")

    invalid_cases = [
        [dispatch_item("gongbu", "工部", ""), dispatch_item("gongbu", "工部", "duplicate")],
        [{**dispatch_item("libu", "礼部", "wording"), "direct_superior": "taizi"}],
        [{**dispatch_item("xingbu", "刑部", "risk"), "evidence_contract": ""}],
        [{**dispatch_item("gongbu", "工部", "build"), "visibility": "visible_core"}],
        [{**dispatch_item("gongbu", "工部", "build"), "preload_ack": ""}],
        [{**dispatch_item("gongbu", "工部", "build"), "profile_hash": "not-a-sha256"}],
        [{**dispatch_item("gongbu", "工部", "build"), "dossier_hash": ""}],
        [{**dispatch_item("gongbu", "工部", "build"), "court_skill_hash": ""}],
        [{**dispatch_item("gongbu", "工部", "build"), "profile_hash": "0" * 64}],
        [{**dispatch_item("gongbu", "工部", "build"), "dossier_hash": "f" * 64}],
        [{**dispatch_item("gongbu", "工部", "build"), "court_skill_hash": "a" * 64}],
        [{**dispatch_item("gongbu", "工部", "build"), "profile_path": "agents/standing-officials/menxia.toml"}],
        [{**dispatch_item("gongbu", "工部", "build"), "dossier_path": "../outside/AGENTS.md"}],
        [{**dispatch_item("gongbu", "工部", "build"), "skill_path": "references/SKILL.md"}],
    ]
    try:
        validate_dispatch_plan(
            [dispatch_item("gongbu", "工部", "build")],
            authority="super",
            behavior="parallel",
        )
    except ValueError as exc:
        require("exact_preload_contract_gate" in str(exc), f"unexpected missing-manifest rejection: {exc!s}")
    else:
        raise AssertionError("dispatch plan passed without a trusted preload manifest")
    rejected = 0
    for case in invalid_cases:
        try:
            validate_dispatch_plan(
                case,
                authority="super",
                behavior="parallel",
                trusted_preload_manifest=_dispatch_manifest(case),
            )
        except ValueError:
            rejected += 1
        else:
            raise AssertionError("invalid dispatch plan was accepted")
    return {"roles": plan.roles, "invalid_cases_rejected": rejected}


def check_parallel_limit_authorization() -> dict[str, object]:
    roles = tuple(f"role-{index:02d}" for index in range(1, 18))
    common = {
        "useful_roles": roles,
        "host_capacity": 48,
        "host_active": 1,
        "host_retained": 0,
        "host_reclamation_verified": True,
        "user_agent_budget": None,
        "provider_launch_budget": None,
        "next_depth": 2,
        "max_threads": 48,
        "budget_lease": active_budget(17, approved_roles=roles),
        "task_id": "dispatch-policy-check",
        "calling_office": "shangshu",
        "direct_superior": "taizi",
    }

    default = select_wave(**common)
    require(default.max_threads == 16, "default dispatch did not normalize to 16")
    require(len(default.selected_roles) < 17, "default dispatch started the seventeenth agent")

    explicit = select_wave(
        **common,
        explicit_parallel_count=18,
        parallel_control_source="latest_user_explicit",
    )
    require(len(explicit.selected_roles) == 17, "explicit count above 16 was not honored")

    unlocked = select_wave(
        **common,
        parallel_unlimited=True,
        parallel_control_source="latest_user_explicit",
    )
    require(len(unlocked.selected_roles) == 17, "explicit unlock did not admit the seventeenth agent")

    stale = select_wave(
        **common,
        explicit_parallel_count=18,
        parallel_control_source="prior_memory",
    )
    require(
        stale.selected_roles == ()
        and stale.reason == "parallel_override_not_current_user_explicit",
        "stale parallel override did not fail closed",
    )

    no_lease = {**common, "budget_lease": None}
    unlocked_without_budget = select_wave(
        **no_lease,
        parallel_unlimited=True,
        parallel_control_source="latest_user_explicit",
    )
    require(
        unlocked_without_budget.selected_roles == ()
        and unlocked_without_budget.reason == "approved_budget_missing",
        "unlock bypassed the Taizi budget lease",
    )

    bounded_lease = {**common, "budget_lease": active_budget(5, approved_roles=roles[:5])}
    bounded = select_wave(
        **bounded_lease,
        parallel_unlimited=True,
        parallel_control_source="latest_user_explicit",
    )
    require(len(bounded.selected_roles) == 5, "unlock auto-filled beyond the approved budget")
    return {
        "default_selected": len(default.selected_roles),
        "explicit_selected": len(explicit.selected_roles),
        "unlock_selected": len(unlocked.selected_roles),
        "budget_selected": len(bounded.selected_roles),
    }


def check_read_only_budget_admission() -> None:
    decision = admit_roles(
        host_capacity=8,
        active_threads=1,
        retained_threads=0,
        terminal_reclamation_verified=True,
        requested_roles=("gongbu",),
        max_threads=16,
        next_depth=2,
        max_depth=4,
        budget_lease=active_budget(1, approved_roles=("gongbu",)),
        task_id="dispatch-policy-check",
        calling_office="shangshu",
        direct_superior="taizi",
        binding_overrides={
            0: {
                "write_set": [],
                "access_mode": "read_only",
                "read_scope": ["scripts", "references"],
                "mutation_allowed": False,
                "integration_authority": False,
            }
        },
    )
    require(decision.allowed is True, f"valid read-only binding was rejected: {decision.reason_codes!r}")
    require(decision.selected_roles == ("gongbu",), "read-only binding lost its approved role")

    invalid_overrides = (
        {"access_mode": "read_write", "write_set": [], "mutation_allowed": True},
        {"read_scope": []},
        {"read_scope": ["../outside"]},
        {"mutation_allowed": True},
        {"integration_authority": True},
    )
    for overrides in invalid_overrides:
        rejected = admit_roles(
            host_capacity=8,
            active_threads=1,
            retained_threads=0,
            terminal_reclamation_verified=True,
            requested_roles=("gongbu",),
            max_threads=16,
            next_depth=2,
            max_depth=4,
            budget_lease=active_budget(1, approved_roles=("gongbu",)),
            task_id="dispatch-policy-check",
            calling_office="shangshu",
            direct_superior="taizi",
            binding_overrides={
                0: {
                    "write_set": [],
                    "access_mode": "read_only",
                    "read_scope": ["scripts"],
                    "mutation_allowed": False,
                    "integration_authority": False,
                    **overrides,
                }
            },
        )
        require(
            rejected.allowed is False
            and rejected.reason_codes == ("approved_budget_scope_mismatch",),
            f"invalid access contract was admitted: {overrides!r}",
        )


def check_repository_relative_access_paths() -> None:
    common = {
        "host_capacity": 8,
        "active_threads": 1,
        "retained_threads": 0,
        "terminal_reclamation_verified": True,
        "requested_roles": ("gongbu",),
        "max_threads": 16,
        "next_depth": 2,
        "max_depth": 4,
        "budget_lease": active_budget(1, approved_roles=("gongbu",)),
        "task_id": "dispatch-policy-check",
        "calling_office": "shangshu",
        "direct_superior": "taizi",
    }
    portable = admit_roles(
        **common,
        binding_overrides={
            0: {
                "write_set": ["Scripts\\Runtime\\Worker.py"],
                "read_scope": ["SCRIPTS/runtime/worker.PY"],
            }
        },
    )
    require(portable.allowed is True, f"portable path spelling was rejected: {portable.reason_codes!r}")

    invalid_paths = (
        "C:\\repo\\worker.py",
        "\\\\server\\share\\worker.py",
        "/repo/worker.py",
        "../worker.py",
        "scripts/../worker.py",
        "./worker.py",
        "scripts//worker.py",
        None,
    )
    for invalid_path in invalid_paths:
        for field in ("write_set", "read_scope"):
            overrides: dict[str, object] = {
                "write_set": ["scripts/worker.py"],
                "read_scope": ["scripts/worker.py"],
            }
            overrides[field] = [invalid_path]
            rejected = admit_roles(
                **common,
                binding_overrides={0: overrides},
            )
            require(
                rejected.allowed is False
                and rejected.reason_codes == ("approved_budget_scope_mismatch",),
                f"non-repository-relative {field} was admitted: {invalid_path!r}",
            )

    duplicate_portable_key = admit_roles(
        **common,
        binding_overrides={
            0: {
                "write_set": ["Scripts/Worker.py", "scripts\\worker.PY"],
                "read_scope": ["scripts/worker.py"],
            }
        },
    )
    require(
        duplicate_portable_key.allowed is False
        and duplicate_portable_key.reason_codes == ("approved_budget_scope_mismatch",),
        "case/slash-equivalent duplicate writer paths were admitted",
    )


def check_same_role_instance_admission() -> None:
    roles = ("gongbu", "gongbu")
    decision = admit_roles(
        host_capacity=8,
        active_threads=1,
        retained_threads=0,
        terminal_reclamation_verified=True,
        requested_roles=roles,
        max_threads=16,
        next_depth=2,
        max_depth=4,
        budget_lease=active_budget(
            2,
            calling_office="gongbu",
            direct_superior="shangshu",
            approved_roles=roles,
        ),
        task_id="dispatch-policy-check",
        calling_office="gongbu",
        direct_superior="shangshu",
        binding_overrides={
            0: {
                "instance_kind": "office_worker_instance",
                "canonical_authority": False,
                "owner_role": "gongbu",
                "direct_superior": "gongbu",
                "child_profile": _bounded_child_profile(
                    office_instance_id="gongbu#0001",
                    ordinal=1,
                ),
            },
            1: {
                "instance_kind": "office_worker_instance",
                "canonical_authority": False,
                "owner_role": "gongbu",
                "direct_superior": "gongbu",
                "child_profile": _bounded_child_profile(
                    office_instance_id="gongbu#0002",
                    ordinal=2,
                ),
            },
        },
    )
    require(decision.allowed is True, f"two bounded Gongbu workers were rejected: {decision.reason_codes!r}")
    require(decision.selected_roles == roles, "same-role instance selection collapsed by role")


def check_public_admission_canonical_shape() -> None:
    common = {
        "host_capacity": 8,
        "active_threads": 1,
        "retained_threads": 0,
        "terminal_reclamation_verified": True,
        "max_threads": 16,
        "next_depth": 2,
        "max_depth": 4,
        "task_id": "dispatch-policy-check",
        "calling_office": "shangshu",
        "direct_superior": "taizi",
    }
    duplicate_taizi = admit_roles(
        **common,
        requested_roles=("taizi", "taizi"),
        budget_lease=active_budget(2, approved_roles=("taizi", "taizi")),
    )
    require(
        duplicate_taizi.allowed is False,
        "public admission allowed two Taizi instances",
    )

    duplicate_gongbu_canonical = admit_roles(
        **common,
        requested_roles=("gongbu", "gongbu"),
        budget_lease=active_budget(2, approved_roles=("gongbu", "gongbu")),
        binding_overrides={
            1: {
                "instance_kind": "office",
                "canonical_authority": True,
                "owner_role": None,
                "direct_superior": "shangshu",
            }
        },
    )
    require(
        duplicate_gongbu_canonical.allowed is False,
        "public admission allowed two canonical Gongbu offices",
    )

    forged_shape = admit_roles(
        **common,
        requested_roles=("gongbu",),
        budget_lease=active_budget(
            1,
            approved_roles=("gongbu",),
            approved_instance_shapes={
                "gongbu#0001": {
                    "instance_kind": "office_worker_instance",
                    "canonical_authority": False,
                    "owner_role": "gongbu",
                    "direct_superior": "gongbu",
                }
            },
        ),
    )
    require(
        forged_shape.allowed is False,
        "public admission accepted a requested canonical shape that differed from the lease",
    )


def check_taizi_root_mainline_cannot_dispatch_ministries() -> dict[str, object]:
    """Future contract: root/mainline Taizi cannot select or admit a ministry."""

    evidence: dict[str, object] = {
        "caller_surface": "root/mainline",
        "calling_office": "taizi",
        "targets": {},
    }
    violations: list[str] = []
    for role in MINISTRY_ROLES:
        task_id = f"dispatch-policy-root-mainline-taizi-{role}"
        lease = active_budget(
            1,
            task_id=task_id,
            calling_office="taizi",
            direct_superior="user",
            approved_roles=(role,),
        )
        wave = select_wave(
            useful_roles=(role,),
            host_capacity=4,
            host_active=1,
            host_retained=0,
            host_reclamation_verified=True,
            user_agent_budget=None,
            provider_launch_budget=None,
            next_depth=1,
            max_threads=16,
            max_depth=4,
            budget_lease=lease,
            task_id=task_id,
            calling_office="taizi",
            direct_superior="user",
        )
        admission = admit_roles(
            host_capacity=4,
            active_threads=1,
            retained_threads=0,
            terminal_reclamation_verified=True,
            requested_roles=(role,),
            max_threads=16,
            next_depth=1,
            max_depth=4,
            budget_lease=lease,
            task_id=task_id,
            calling_office="taizi",
            direct_superior="user",
        )
        evidence["targets"][role] = {
            "select_wave": {
                "selected_roles": list(wave.selected_roles),
                "deferred_roles": list(wave.deferred_roles),
                "reason": wave.reason,
            },
            "admit_roles": {
                "allowed": admission.allowed,
                "selected_roles": list(admission.selected_roles),
                "deferred_roles": list(admission.deferred_roles),
                "reason_codes": list(admission.reason_codes),
            },
        }
        if (
            wave.selected_roles
            or wave.deferred_roles != (role,)
            or wave.reason != "dispatch_hierarchy_edge_forbidden"
        ):
            violations.append(
                f"select_wave taizi->{role} selected={wave.selected_roles!r} "
                f"deferred={wave.deferred_roles!r} reason={wave.reason!r}"
            )
        if (
            admission.allowed
            or admission.selected_roles
            or admission.deferred_roles != (role,)
            or admission.reason_codes != ("dispatch_hierarchy_edge_forbidden",)
        ):
            violations.append(
                f"admit_roles taizi->{role} allowed={admission.allowed!r} "
                f"selected={admission.selected_roles!r} deferred={admission.deferred_roles!r} "
                f"reasons={admission.reason_codes!r}"
            )
    require(
        not violations,
        "missing shared dispatch hierarchy enforcement at ordinary entry points: "
        + "; ".join(violations),
    )
    return evidence


def check_ministry_profile_mismatch_denied_before_capacity() -> dict[str, object]:
    task_id = "dispatch-policy-ministry-superior-mismatch"
    lease = active_budget(
        1,
        task_id=task_id,
        calling_office="shangshu",
        direct_superior="taizi",
        approved_roles=("gongbu",),
    )
    binding_overrides = {0: {"direct_superior": "taizi"}}
    wave = select_wave(
        useful_roles=("gongbu",),
        host_capacity=4,
        host_active=1,
        host_retained=0,
        host_reclamation_verified=True,
        user_agent_budget=None,
        provider_launch_budget=None,
        next_depth=1,
        max_threads=16,
        max_depth=4,
        budget_lease=lease,
        task_id=task_id,
        calling_office="shangshu",
        direct_superior="taizi",
        binding_overrides=binding_overrides,
    )
    admission = admit_roles(
        host_capacity=4,
        active_threads=1,
        retained_threads=0,
        terminal_reclamation_verified=True,
        requested_roles=("gongbu",),
        max_threads=16,
        next_depth=1,
        max_depth=4,
        budget_lease=lease,
        task_id=task_id,
        calling_office="shangshu",
        direct_superior="taizi",
        binding_overrides=binding_overrides,
    )
    require(
        wave.selected_roles == ()
        and wave.deferred_roles == ("gongbu",)
        and wave.reason == "dispatch_hierarchy_target_superior_mismatch",
        "select_wave admitted a ministry with a forged direct superior",
    )
    require(
        admission.allowed is False
        and admission.selected_roles == ()
        and admission.deferred_roles == ("gongbu",)
        and admission.reason_codes
        == ("dispatch_hierarchy_target_superior_mismatch",),
        "admit_roles admitted a ministry with a forged direct superior",
    )
    return {
        "select_wave": wave.__dict__,
        "admit_roles": admission.__dict__,
    }


def check_three_department_requires_taizi_caller() -> dict[str, object]:
    task_id = "dispatch-policy-three-department-caller"
    lease = active_budget(
        1,
        task_id=task_id,
        calling_office="shangshu",
        direct_superior="taizi",
        approved_roles=("menxia",),
    )
    wave = select_wave(
        useful_roles=("menxia",),
        host_capacity=4,
        host_active=1,
        host_retained=0,
        host_reclamation_verified=True,
        user_agent_budget=None,
        provider_launch_budget=None,
        next_depth=1,
        max_threads=16,
        max_depth=4,
        budget_lease=lease,
        task_id=task_id,
        calling_office="shangshu",
        direct_superior="taizi",
    )
    admission = admit_roles(
        host_capacity=4,
        active_threads=1,
        retained_threads=0,
        terminal_reclamation_verified=True,
        requested_roles=("menxia",),
        max_threads=16,
        next_depth=1,
        max_depth=4,
        budget_lease=lease,
        task_id=task_id,
        calling_office="shangshu",
        direct_superior="taizi",
    )
    require(
        wave.selected_roles == ()
        and wave.deferred_roles == ("menxia",)
        and wave.reason == "dispatch_hierarchy_edge_forbidden",
        "select_wave allowed Shangshu to dispatch Menxia",
    )
    require(
        admission.allowed is False
        and admission.selected_roles == ()
        and admission.deferred_roles == ("menxia",)
        and admission.reason_codes == ("dispatch_hierarchy_edge_forbidden",),
        "admit_roles allowed Shangshu to dispatch Menxia",
    )
    return {
        "select_wave": wave.__dict__,
        "admit_roles": admission.__dict__,
    }


def check_formal_dispatch_requires_target_binding() -> dict[str, object]:
    task_id = "dispatch-policy-target-binding-required"
    scoped = _approved_scope_kwargs(
        ("gongbu",),
        active_budget(
            1,
            task_id=task_id,
            calling_office="shangshu",
            direct_superior="taizi",
            approved_roles=("gongbu",),
        ),
        integration_domain="dispatch-policy",
        authority="super",
        binding_overrides=None,
    )
    lease = scoped["budget_lease"]
    assert isinstance(lease, Mapping)
    wave = _select_wave(
        ("gongbu",),
        4,
        1,
        None,
        None,
        host_retained=0,
        host_reclamation_verified=True,
        next_depth=1,
        max_threads=16,
        max_depth=4,
        budget_lease=lease,
        task_id=task_id,
        calling_office="shangshu",
        direct_superior="taizi",
        requested_bindings=None,
        integration_domain="dispatch-policy",
        authority="super",
    )
    admission = _admit_roles(
        host_capacity=4,
        active_threads=1,
        retained_threads=0,
        terminal_reclamation_verified=True,
        requested_roles=("gongbu",),
        max_threads=16,
        next_depth=1,
        max_depth=4,
        budget_lease=lease,
        task_id=task_id,
        calling_office="shangshu",
        direct_superior="taizi",
        requested_bindings=None,
        integration_domain="dispatch-policy",
        authority="super",
    )
    require(
        wave.selected_roles == ()
        and wave.deferred_roles == ("gongbu",)
        and wave.reason == "dispatch_hierarchy_target_profile_required",
        "select_wave reached capacity/budget without a formal target binding",
    )
    require(
        admission.allowed is False
        and admission.selected_roles == ()
        and admission.deferred_roles == ("gongbu",)
        and admission.reason_codes
        == ("dispatch_hierarchy_target_profile_required",),
        "admit_roles reached capacity/budget without a formal target binding",
    )
    return {
        "select_wave": wave.__dict__,
        "admit_roles": admission.__dict__,
    }


def check_worker_requires_bounded_child_profile() -> dict[str, object]:
    task_id = "dispatch-policy-bounded-child-profile"
    lease = active_budget(
        1,
        task_id=task_id,
        calling_office="gongbu",
        direct_superior="shangshu",
        approved_roles=("gongbu",),
    )
    worker_shape = {
        0: {
            "instance_kind": "office_worker_instance",
            "canonical_authority": False,
            "owner_role": "gongbu",
            "direct_superior": "gongbu",
        }
    }
    missing = select_wave(
        useful_roles=("gongbu",),
        host_capacity=4,
        host_active=1,
        host_retained=0,
        host_reclamation_verified=True,
        user_agent_budget=None,
        provider_launch_budget=None,
        next_depth=2,
        max_threads=16,
        max_depth=4,
        budget_lease=lease,
        task_id=task_id,
        calling_office="gongbu",
        direct_superior="shangshu",
        binding_overrides=worker_shape,
    )
    missing_admission = admit_roles(
        host_capacity=4,
        active_threads=1,
        retained_threads=0,
        terminal_reclamation_verified=True,
        requested_roles=("gongbu",),
        max_threads=16,
        next_depth=2,
        max_depth=4,
        budget_lease=lease,
        task_id=task_id,
        calling_office="gongbu",
        direct_superior="shangshu",
        binding_overrides=worker_shape,
    )
    require(
        missing.selected_roles == ()
        and missing.deferred_roles == ("gongbu",)
        and missing.reason == "dispatch_hierarchy_child_profile_required",
        "select_wave admitted a worker without a bounded child profile",
    )
    require(
        missing_admission.allowed is False
        and missing_admission.selected_roles == ()
        and missing_admission.deferred_roles == ("gongbu",)
        and missing_admission.reason_codes
        == ("dispatch_hierarchy_child_profile_required",),
        "admit_roles admitted a worker without a bounded child profile",
    )

    bounded_shape = {
        0: {
            **worker_shape[0],
            "child_profile": _bounded_child_profile(),
        }
    }
    allowed = select_wave(
        useful_roles=("gongbu",),
        host_capacity=4,
        host_active=1,
        host_retained=0,
        host_reclamation_verified=True,
        user_agent_budget=None,
        provider_launch_budget=None,
        next_depth=2,
        max_threads=16,
        max_depth=4,
        budget_lease=lease,
        task_id=task_id,
        calling_office="gongbu",
        direct_superior="shangshu",
        binding_overrides=bounded_shape,
    )
    require(
        allowed.selected_roles == ("gongbu",)
        and allowed.deferred_roles == (),
        "same-owner bounded child profile was rejected",
    )
    return {
        "missing_profile": missing.__dict__,
        "missing_profile_admission": missing_admission.__dict__,
        "bounded_profile": allowed.__dict__,
    }


def check_child_profile_binding_digest_is_immutable_before_capacity() -> dict[str, object]:
    task_id = "dispatch-policy-child-profile-binding-digest"
    roles = ("gongbu",)
    scoped = _approved_scope_kwargs(
        roles,
        active_budget(
            1,
            task_id=task_id,
            calling_office="gongbu",
            direct_superior="shangshu",
            approved_roles=roles,
        ),
        integration_domain="dispatch-policy",
        authority="super",
        binding_overrides={
            0: {
                "instance_kind": "office_worker_instance",
                "canonical_authority": False,
                "owner_role": "gongbu",
                "direct_superior": "gongbu",
                "child_profile": _bounded_child_profile(),
            }
        },
    )
    lease = scoped["budget_lease"]
    bindings = scoped["requested_bindings"]
    assert isinstance(lease, Mapping)
    assert isinstance(bindings, Sequence)
    original_binding = bindings[0]
    assert isinstance(original_binding, Mapping)
    digest_map = lease.get("approved_binding_sha256s")
    require(
        isinstance(digest_map, Mapping)
        and digest_map.get("gongbu#0001")
        == canonical_child_office_binding_sha256(original_binding),
        "child binding digest was not frozen into the approved lease",
    )

    common = {
        "useful_roles": roles,
        "host_capacity": 4,
        "host_active": 1,
        "host_retained": 0,
        "host_reclamation_verified": True,
        "user_agent_budget": None,
        "provider_launch_budget": None,
        "next_depth": 2,
        "max_threads": 16,
        "max_depth": 4,
        "task_id": task_id,
        "calling_office": "gongbu",
        "direct_superior": "shangshu",
        "integration_domain": "dispatch-policy",
        "authority": "super",
    }
    allowed = _select_wave(
        **common,
        budget_lease=lease,
        requested_bindings=bindings,
    )
    require(
        allowed.selected_roles == roles and allowed.deferred_roles == (),
        "lease-bound child profile was rejected",
    )

    tampered_bindings = deepcopy(bindings)
    tampered_profile = tampered_bindings[0]["child_profile"]
    assert isinstance(tampered_profile, dict)
    tampered_profile["bounded_mandate"] = (
        "silently widened but still schema-valid child mandate"
    )
    tampered = _select_wave(
        **common,
        budget_lease=lease,
        requested_bindings=tampered_bindings,
    )
    require(
        tampered.selected_roles == ()
        and tampered.deferred_roles == roles
        and tampered.reason == "dispatch_hierarchy_child_scope_binding_mismatch",
        "nested child-profile tamper bypassed outer-scope parity",
    )
    return {
        "allowed": allowed.__dict__,
        "tampered": tampered.__dict__,
        "approved_binding_sha256": digest_map["gongbu#0001"],
    }


def check_special_lifecycle_uses_shared_hierarchy_gate() -> dict[str, object]:
    task_id = "dispatch-policy-special-lifecycle-hierarchy"
    lease = active_budget(
        1,
        task_id=task_id,
        calling_office="shangshu",
        direct_superior="taizi",
        approved_roles=("shiguan",),
    )
    common = {
        "host_capacity": 4,
        "host_retained": 0,
        "host_reclamation_verified": True,
        "next_depth": 2,
        "max_threads": 16,
        "max_depth": 4,
        "budget_lease": lease,
        "task_id": task_id,
        "calling_office": "shangshu",
        "direct_superior": "taizi",
    }
    selected = select_wave(
        useful_roles=("shiguan",),
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        **common,
    )
    admitted = admit_roles(
        requested_roles=("shiguan",),
        active_threads=1,
        retained_threads=0,
        terminal_reclamation_verified=True,
        **{key: value for key, value in common.items() if key not in {"host_retained", "host_reclamation_verified"}},
    )
    require(
        selected.selected_roles == ()
        and selected.reason == "dispatch_hierarchy_edge_forbidden",
        "ordinary select_wave bypassed the shared hierarchy gate for Shiguan",
    )
    require(
        admitted.allowed is False
        and admitted.reason_codes == ("dispatch_hierarchy_edge_forbidden",),
        "ordinary admit_roles bypassed the shared hierarchy gate for Shiguan",
    )
    return {"select_wave": selected.__dict__, "admit_roles": admitted.__dict__}


def check_child_profile_outer_scope_must_match() -> dict[str, object]:
    task_id = "dispatch-policy-child-profile-scope-parity"
    profile = _bounded_child_profile()
    profile["read_scope"] = ["work/gongbu/different-input.txt"]
    scoped = _approved_scope_kwargs(
        ("gongbu",),
        active_budget(
            1,
            task_id=task_id,
            calling_office="gongbu",
            direct_superior="shangshu",
            approved_roles=("gongbu",),
        ),
        integration_domain="dispatch-policy",
        authority="super",
        binding_overrides={
            0: {
                "instance_kind": "office_worker_instance",
                "canonical_authority": False,
                "owner_role": "gongbu",
                "direct_superior": "gongbu",
                "child_profile": profile,
            }
        },
        next_depth=2,
    )
    decision = _select_wave(
        useful_roles=("gongbu",),
        host_capacity=4,
        host_active=1,
        host_retained=0,
        host_reclamation_verified=True,
        user_agent_budget=None,
        provider_launch_budget=None,
        next_depth=2,
        max_threads=16,
        max_depth=4,
        budget_lease=scoped["budget_lease"],
        task_id=task_id,
        calling_office="gongbu",
        direct_superior="shangshu",
        requested_bindings=scoped["requested_bindings"],
        integration_domain="dispatch-policy",
        authority="super",
    )
    require(
        decision.selected_roles == ()
        and decision.reason == "dispatch_hierarchy_child_scope_binding_mismatch",
        "outer binding and nested child_profile scope drift was admitted",
    )
    return decision.__dict__


def check_admission_lease_authority_expiry_depth_scope_and_preload() -> dict[str, object]:
    task_id = "dispatch-policy-lease-hard-gates"
    roles = ("gongbu",)

    def decision(**lease_overrides: object) -> object:
        return select_wave(
            useful_roles=roles,
            host_capacity=4,
            host_active=1,
            host_retained=0,
            host_reclamation_verified=True,
            user_agent_budget=None,
            provider_launch_budget=None,
            next_depth=2,
            max_threads=16,
            max_depth=4,
            budget_lease=active_budget(
                1,
                task_id=task_id,
                calling_office="shangshu",
                direct_superior="taizi",
                approved_roles=roles,
                **lease_overrides,
            ),
            task_id=task_id,
            calling_office="shangshu",
            direct_superior="taizi",
        )

    cases = {
        "self_issued": (
            decision(parent_id="shangshu", approved_by="shangshu"),
            "approved_budget_parent_authority_mismatch",
        ),
        "self_parent_budget": (
            decision(
                parent_budget_id=f"budget:{task_id}:phase:wave",
            ),
            "approved_budget_parent_binding_invalid",
        ),
        "invalid_expiry": (
            decision(expires_at_utc="not-an-instant"),
            "approved_budget_lease_expiry_invalid",
        ),
        "expired": (
            decision(expires_at_utc="2000-01-01T00:00:00+00:00"),
            "approved_budget_lease_expired",
        ),
        "depth": (
            decision(lease_depth=2, approved_next_depth=3),
            "approved_budget_depth_mismatch",
        ),
        "write_scope": (
            decision(parent_write_scope=["unrelated"]),
            "approved_budget_parent_write_scope_mismatch",
        ),
        "preload": (
            decision(
                approved_preload_hashes={
                    "gongbu#0001": {
                        **BOUND_PRELOAD_HASHES,
                        "profile_hash": "f" * 64,
                    }
                }
            ),
            "approved_budget_preload_mismatch",
        ),
    }
    for name, (current, reason) in cases.items():
        require(
            current.selected_roles == () and current.reason == reason,
            f"{name} lease mutation bypassed the admission hard gate",
        )
    return {name: current.__dict__ for name, (current, _reason) in cases.items()}


def main() -> int:
    with TemporaryDirectory(prefix="court-dispatch-preload-") as temp_dir:
        _initialize_dispatch_preload(Path(temp_dir))
        check_read_only_budget_admission()
        check_repository_relative_access_paths()
        check_same_role_instance_admission()
        check_public_admission_canonical_shape()
        hierarchy_entrypoints = check_taizi_root_mainline_cannot_dispatch_ministries()
        hierarchy_profile_mismatch = check_ministry_profile_mismatch_denied_before_capacity()
        three_department_caller = check_three_department_requires_taizi_caller()
        target_binding_required = check_formal_dispatch_requires_target_binding()
        bounded_child_profile = check_worker_requires_bounded_child_profile()
        child_profile_binding_digest = (
            check_child_profile_binding_digest_is_immutable_before_capacity()
        )
        special_lifecycle_hierarchy = check_special_lifecycle_uses_shared_hierarchy_gate()
        child_profile_scope_parity = check_child_profile_outer_scope_must_match()
        lease_hard_gates = check_admission_lease_authority_expiry_depth_scope_and_preload()
        result = {
            "ok": True,
            "admission_facade": check_admission_facade(),
            "mode_semantics": check_mode_semantics(),
            "dynamic_capacity": check_dynamic_capacity(),
            "dispatch_plan": check_dispatch_plan(),
            "parallel_limit_authorization": check_parallel_limit_authorization(),
            "lease_access_contract": "PASSED",
            "repository_relative_access_paths": "PASSED",
            "same_role_instance_admission": "PASSED",
            "public_admission_canonical_shape": "PASSED",
            "hierarchy_entrypoints": hierarchy_entrypoints,
            "hierarchy_profile_mismatch": hierarchy_profile_mismatch,
            "three_department_caller": three_department_caller,
            "target_binding_required": target_binding_required,
            "bounded_child_profile": bounded_child_profile,
            "child_profile_binding_digest": child_profile_binding_digest,
            "special_lifecycle_hierarchy": special_lifecycle_hierarchy,
            "child_profile_scope_parity": child_profile_scope_parity,
            "lease_hard_gates": lease_hard_gates,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
