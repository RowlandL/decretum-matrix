"""RED regression checks for the Proposal C complexity-budget contract.

The production contract intentionally does not exist at the start of A02 Phase 1.
This checker therefore fails closed until ``court_complexity_budget.py`` provides
the pure decision helpers exercised below.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import inspect
import math
import sys

sys.dont_write_bytecode = True

import court_complexity_budget as complexity_budget_module

try:
    from court_complexity_budget import (
        COMPLEXITY_RESULTS,
        allocate_budget_lease,
        evaluate_complexity_budget,
        is_super_giant_task,
        normalize_budget_pool,
        plan_budgeted_launch,
        reassess_budget_pool,
        release_budget_lease,
        should_degrade_complexity,
    )
except ModuleNotFoundError as exc:
    if exc.name != "court_complexity_budget":
        raise
    print(
        "COURT_COMPLEXITY_BUDGET_RED "
        "missing production contract: scripts/court_complexity_budget.py",
        file=sys.stderr,
    )
    raise SystemExit(1) from None


EXPECTED_RESULTS = frozenset(
    {
        "MINIMAL_PASS",
        "NECESSARY_COMPLEXITY_APPROVED",
        "LOW_VALUE_REJECTED",
        "BUDGET_DEFERRED",
    }
)

SAFE_RESOURCE_STATE = {
    "sample_id": "resource-sample-001",
    "sampled_at": "2026-07-15T00:00:00Z",
    "decision_at": "2026-07-15T00:00:30Z",
    "now": "2026-07-15T00:00:30Z",
    "max_sample_age_seconds": 300,
    "host_capacity": 24,
    "active_agents": 1,
    "retained_agents": 0,
    "reclamation_verified": True,
    "ram_percent": 40.0,
    "free_memory_mb": 16_384,
    "context_tokens": 20_000,
    "message_chars": 1_000,
    "tool_calls": 1,
    "time_seconds": 30.0,
}

HARD_LIMITS = {
    "ram_percent_max": 99.0,
    "memory_mb_max": 2_048,
    "context_tokens_max": 100_000,
    "message_chars_max": 12_000,
    "tool_calls_max": 8,
    "time_seconds_max": 600.0,
    "retained_agents_max": 15,
}

LEASE_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "budget_id",
        "lease_id",
        "parent_budget_id",
        "task_id",
        "phase_id",
        "wave_id",
        "role_key",
        "instance_key",
        "level",
        "direct_superior",
        "normalized_share",
        "hard_caps",
        "measured_cost",
        "write_set",
        "access_mode",
        "read_scope",
        "mutation_allowed",
        "expected_output",
        "complexity_score",
        "marginal_value_score",
        "approved_by",
        "approved_at",
        "start_condition",
        "expiry_condition",
        "return_conditions",
        "preload_ack",
        "shard_id",
        "integration_domain",
        "integration_authority",
        "status",
        "release_evidence",
        "release_authority",
        "released_by",
        "released_at",
        "release_generation",
        "release_history",
        "launch_state",
        "launch_sample_id",
        "launch_usage",
        "launch_history",
    }
)

COMPOSITE_FACTORS = frozenset(
    {
        "agent_count",
        "host_capacity",
        "retained_agents",
        "reclamation_verified",
        "ram_percent",
        "free_memory_mb",
        "measured_agent_cost",
        "message_chars",
        "time_seconds",
        "write_set",
        "complexity",
        "marginal_value",
        "lease",
    }
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def decide(**overrides: object) -> Mapping[str, object]:
    values: dict[str, object] = {
        "user_instruction": None,
        "necessary_complexity": False,
        "simpler_equivalent_available": True,
        "low_marginal_value": False,
        "budget_sufficient": True,
        "risk_acceptable": True,
        "rollback_ready": True,
    }
    values.update(overrides)
    result = evaluate_complexity_budget(**values)
    require(isinstance(result, Mapping), "complexity decision must be a mapping")
    require(
        result.get("result") in EXPECTED_RESULTS,
        f"complexity decision returned a non-contract result: {result.get('result')!r}",
    )
    return result


def require_decision(
    value: Mapping[str, object],
    *,
    result: str,
    source: str,
) -> None:
    require(value.get("result") == result, f"expected {result}, got {value!r}")
    require(
        value.get("decision_source") == source,
        f"expected decision_source={source}, got {value!r}",
    )
    require(
        value.get("hard_gates_preserved") is True,
        "complexity budget decision did not preserve hard gates",
    )


def require_rejected(action: object, expected: str) -> None:
    try:
        action()  # type: ignore[operator]
    except ValueError as exc:
        require(
            exc.args == (expected,),
            f"expected rejection {expected!r}, got {exc.args!r}",
        )
    else:
        raise AssertionError(f"invalid budget-pool action was accepted: {expected}")


def require_stable_rejected(action: object, expected: str) -> None:
    try:
        action()  # type: ignore[operator]
    except ValueError as exc:
        require(exc.args == (expected,), f"expected rejection {expected!r}, got {exc.args!r}")
    except Exception as exc:
        raise AssertionError(
            f"invalid input raised unstable {type(exc).__name__} instead of {expected}"
        ) from exc
    else:
        raise AssertionError(f"invalid input was accepted: {expected}")


def case_require(case_id: str, condition: bool, message: str) -> None:
    require(condition, f"{case_id}: {message}")


def case_rejected(case_id: str, action: object, expected: str) -> None:
    try:
        require_stable_rejected(action, expected)
    except AssertionError as exc:
        raise AssertionError(f"{case_id}: {exc}") from exc


def case_accepts(case_id: str, action: object) -> object:
    try:
        return action()  # type: ignore[operator]
    except Exception as exc:
        raise AssertionError(f"{case_id}: valid action raised {type(exc).__name__}: {exc}") from exc


def release(
    pool: Mapping[str, object],
    *,
    lease_id: str,
    reason: str,
    evidence: str | None,
    active_useful: bool,
    released_by: str = "gongbu",
    released_at: str = "2026-07-15T00:15:00Z",
) -> Mapping[str, object]:
    values: dict[str, object] = {
        "lease_id": lease_id,
        "reason": reason,
        "evidence": evidence,
        "active_useful": active_useful,
    }
    parameters = inspect.signature(release_budget_lease).parameters
    if "released_by" in parameters and "released_at" in parameters:
        values["released_by"] = released_by
        values["released_at"] = released_at
    return release_budget_lease(pool, **values)  # type: ignore[arg-type]


def leases(pool: Mapping[str, object]) -> Mapping[str, Mapping[str, object]]:
    value = pool.get("leases")
    require(isinstance(value, Mapping), "budget pool did not expose a lease mapping")
    for lease_id, lease in value.items():
        require(isinstance(lease_id, str), "budget pool lease id must be a string")
        require(isinstance(lease, Mapping), f"lease {lease_id!r} must be a mapping")
    return value  # type: ignore[return-value]


def lease(pool: Mapping[str, object], lease_id: str) -> Mapping[str, object]:
    value = leases(pool).get(lease_id)
    require(value is not None, f"budget pool omitted lease {lease_id!r}")
    return value


def approval_binding(pool: Mapping[str, object], child_id: str) -> dict[str, object]:
    value = lease(pool, child_id)
    return {
        "child_id": child_id,
        "lease_id": value.get("lease_id"),
        "instance_key": value.get("instance_key"),
        "role_key": value.get("role_key"),
        "write_set": tuple(value.get("write_set", ())),
        "approved_by": "taizi",
    }


def call_plan(
    pool: Mapping[str, object],
    *,
    candidates: object,
    resource_state: Mapping[str, object],
    requested_count: object,
    taizi_approved_count: object,
    previous_sample_id: str | None,
    taizi_approved_bindings: object | None = None,
) -> Mapping[str, object]:
    values: dict[str, object] = {
        "candidates": candidates,
        "resource_state": resource_state,
        "requested_count": requested_count,
        "taizi_approved_count": taizi_approved_count,
        "previous_sample_id": previous_sample_id,
    }
    if taizi_approved_bindings is None and isinstance(candidates, (tuple, list)):
        bindings = []
        if isinstance(taizi_approved_count, int) and not isinstance(taizi_approved_count, bool):
            for candidate in candidates:
                if len(bindings) >= taizi_approved_count or not isinstance(candidate, Mapping):
                    break
                child_id = candidate.get("child_id")
                if isinstance(child_id, str) and child_id in leases(pool):
                    bindings.append(approval_binding(pool, child_id))
        taizi_approved_bindings = tuple(bindings)
    if "taizi_approved_bindings" in inspect.signature(plan_budgeted_launch).parameters:
        values["taizi_approved_bindings"] = taizi_approved_bindings
    return plan_budgeted_launch(pool, **values)  # type: ignore[arg-type]


def allocate(
    pool: Mapping[str, object],
    *,
    parent_id: str,
    allocator_id: str,
    child_id: str,
    child_level: str,
    share: float,
    reserve_share: float = 0.0,
    owning_worker_id: str | None = None,
    role_key: str | None = None,
    instance_key: str | None = None,
    direct_superior: str | None = None,
    shard_id: str | None = None,
    write_set: tuple[str, ...] | None = None,
    integration_domain: str | None = None,
    integration_authority: bool = False,
    access_mode: str = "read_write",
    read_scope: tuple[str, ...] = (),
    mutation_allowed: bool = True,
    preload_ack: str = "PASSED",
    measured_cost: Mapping[str, object] | None = None,
    complexity_score: float = 5.0,
    marginal_value_score: float = 8.0,
    task_id: str = "CCR-R2-SHIR-20260714-A02",
    phase_id: str = "PHASE1",
    wave_id: str = "A02-LANE-J-W1",
    hard_caps: Mapping[str, object] | None = None,
    approved_by: str | None = None,
) -> Mapping[str, object]:
    effective_role = role_key or child_id.split("#", 1)[0]
    effective_instance = instance_key or child_id
    result = allocate_budget_lease(
        pool,
        parent_id=parent_id,
        allocator_id=allocator_id,
        child_id=child_id,
        child_level=child_level,
        share=share,
        reserve_share=reserve_share,
        owning_worker_id=owning_worker_id,
        task_id=task_id,
        phase=phase_id,
        wave_id=wave_id,
        role_key=effective_role,
        instance_key=effective_instance,
        direct_superior=direct_superior or parent_id,
        shard_id=shard_id or effective_instance,
        write_set=(f"synthetic/{effective_instance}",) if write_set is None else write_set,
        expected_output=f"verified output for {effective_instance}",
        approved_by=allocator_id if approved_by is None else approved_by,
        approved_at="2026-07-15T00:00:00Z",
        start_condition="approval_and_preload_passed",
        expiry_condition="wave_or_resource_change_requires_reassessment",
        return_conditions=(
            "COMPLETED",
            "FAILED_CLOSED",
            "CANCELLED",
            "DEGRADED",
            "SAFETY_EXCEPTION",
        ),
        preload_ack=preload_ack,
        hard_caps=HARD_LIMITS if hard_caps is None else hard_caps,
        measured_cost=measured_cost
        or {
            "memory_mb": 512,
            "context_tokens": 8_000,
            "message_chars": 1_000,
            "tool_calls": 2,
            "time_seconds": 30.0,
        },
        complexity_score=complexity_score,
        marginal_value_score=marginal_value_score,
        integration_domain=integration_domain or effective_role,
        integration_authority=integration_authority,
        access_mode=access_mode,
        read_scope=read_scope,
        mutation_allowed=mutation_allowed,
    )
    require(isinstance(result, Mapping), "budget lease allocation must return a pool mapping")
    return result


def hierarchical_pool(*, super_giant_task_gate: bool = False) -> Mapping[str, object]:
    normalize_values: dict[str, object] = {
        "total_share": 100.0,
        "root_id": "taizi",
        "reserve_share": 10.0,
        "hard_limits": HARD_LIMITS,
        "task_id": "CCR-R2-SHIR-20260714-A02",
        "phase": "PHASE1",
        "wave_id": "A02-LANE-J-W1",
        "approved_by": "taizi",
        "approved_at": "2026-07-15T00:00:00Z",
        "expected_output": "bounded court execution",
        "return_conditions": ("DECREE_COMPLETE", "CANCELLED"),
    }
    if "super_giant_task_gate" in inspect.signature(normalize_budget_pool).parameters:
        normalize_values["super_giant_task_gate"] = super_giant_task_gate
    elif super_giant_task_gate:
        raise AssertionError("normalize_budget_pool omitted the super-giant task gate")
    pool = normalize_budget_pool(
        **normalize_values,  # type: ignore[arg-type]
    )
    require(isinstance(pool, Mapping), "normalized budget pool must be a mapping")
    pool = allocate(
        pool,
        parent_id="taizi",
        allocator_id="taizi",
        child_id="zhongshu",
        child_level="department",
        share=20.0,
        reserve_share=2.0,
    )
    pool = allocate(
        pool,
        parent_id="taizi",
        allocator_id="taizi",
        child_id="menxia",
        child_level="department",
        share=20.0,
        reserve_share=2.0,
    )
    pool = allocate(
        pool,
        parent_id="taizi",
        allocator_id="taizi",
        child_id="shangshu",
        child_level="department",
        share=40.0,
        reserve_share=5.0,
        integration_authority=True,
    )
    pool = allocate(
        pool,
        parent_id="shangshu",
        allocator_id="shangshu",
        child_id="gongbu",
        child_level="ministry",
        share=20.0,
        reserve_share=2.0,
    )
    return allocate(
        pool,
        parent_id="gongbu",
        allocator_id="gongbu",
        child_id="gongbu#worker-1",
        child_level="worker",
        share=8.0,
        owning_worker_id="gongbu#worker-1",
    )


def check_strict_result_enum() -> None:
    require(
        frozenset(COMPLEXITY_RESULTS) == EXPECTED_RESULTS,
        "complexity result enum must contain exactly the four approved values",
    )
    require(
        len(tuple(COMPLEXITY_RESULTS)) == len(EXPECTED_RESULTS),
        "complexity result enum contains aliases or duplicates",
    )


def check_user_explicit_instruction_precedence() -> None:
    minimal = decide(
        user_instruction="MINIMAL",
        necessary_complexity=True,
        simpler_equivalent_available=False,
        budget_sufficient=True,
        risk_acceptable=True,
        rollback_ready=True,
    )
    require_decision(minimal, result="BUDGET_DEFERRED", source="USER_EXPLICIT")

    allowed = decide(
        user_instruction="ALLOW_NECESSARY",
        necessary_complexity=True,
        simpler_equivalent_available=False,
        budget_sufficient=True,
        risk_acceptable=True,
        rollback_ready=True,
    )
    require_decision(
        allowed,
        result="NECESSARY_COMPLEXITY_APPROVED",
        source="USER_EXPLICIT",
    )

    user_deferred = decide(
        user_instruction="DEFER_FOR_BUDGET",
        necessary_complexity=True,
        simpler_equivalent_available=False,
        budget_sufficient=True,
        risk_acceptable=True,
        rollback_ready=True,
    )
    require_decision(user_deferred, result="BUDGET_DEFERRED", source="USER_EXPLICIT")

    unsafe_even_when_allowed = decide(
        user_instruction="ALLOW_NECESSARY",
        necessary_complexity=True,
        simpler_equivalent_available=False,
        budget_sufficient=True,
        risk_acceptable=False,
        rollback_ready=True,
    )
    require_decision(
        unsafe_even_when_allowed,
        result="BUDGET_DEFERRED",
        source="USER_EXPLICIT",
    )


def check_taizi_budget_judgment_when_unspecified() -> None:
    necessary = decide(
        necessary_complexity=True,
        simpler_equivalent_available=False,
        low_marginal_value=False,
        budget_sufficient=True,
        risk_acceptable=True,
        rollback_ready=True,
    )
    require_decision(
        necessary,
        result="NECESSARY_COMPLEXITY_APPROVED",
        source="TAIZI_BUDGET",
    )
    require(
        set(necessary.get("considered_factors", ()))
        == {"necessity", "budget", "risk", "rollback"},
        "Taizi decision did not prove all four required factors",
    )

    minimal = decide(
        necessary_complexity=False,
        simpler_equivalent_available=True,
        low_marginal_value=False,
    )
    require_decision(minimal, result="MINIMAL_PASS", source="TAIZI_BUDGET")

    low_value_polish = decide(
        necessary_complexity=False,
        simpler_equivalent_available=True,
        low_marginal_value=True,
        budget_sufficient=True,
        risk_acceptable=True,
        rollback_ready=True,
    )
    require_decision(
        low_value_polish,
        result="LOW_VALUE_REJECTED",
        source="TAIZI_BUDGET",
    )

    unavailable_budget = decide(
        necessary_complexity=True,
        simpler_equivalent_available=False,
        low_marginal_value=False,
        budget_sufficient=False,
        risk_acceptable=True,
        rollback_ready=True,
    )
    require_decision(
        unavailable_budget,
        result="BUDGET_DEFERRED",
        source="TAIZI_BUDGET",
    )

    missing_rollback = decide(
        necessary_complexity=True,
        simpler_equivalent_available=False,
        low_marginal_value=False,
        budget_sufficient=True,
        risk_acceptable=True,
        rollback_ready=False,
    )
    require_decision(
        missing_rollback,
        result="BUDGET_DEFERRED",
        source="TAIZI_BUDGET",
    )


def check_super_giant_examples_and_boundaries() -> None:
    for task_kind in (
        "small_game_development",
        "medium_game_design",
        "large_game_development",
    ):
        require(
            is_super_giant_task(task_kind=task_kind),
            f"complete game development/design was not classified super-giant: {task_kind}",
        )

    require(
        not is_super_giant_task(task_kind="batch_processing", batch_item_count=10),
        "batch threshold must be strictly greater than 10",
    )
    require(
        is_super_giant_task(task_kind="batch_processing", batch_item_count=11),
        "batch work above 10 was not classified super-giant",
    )
    require(
        not is_super_giant_task(
            task_kind="complex_information_judgment",
            information_unit_count=30,
        ),
        "information threshold must be strictly greater than 30",
    )
    require(
        is_super_giant_task(
            task_kind="complex_information_judgment",
            information_unit_count=31,
        ),
        "complex information judgment above 30 units was not classified super-giant",
    )
    require(
        not is_super_giant_task(task_kind="routine_review"),
        "routine work was incorrectly classified super-giant",
    )


def check_wave_reassessment_degrades() -> None:
    require(
        should_degrade_complexity(
            remaining_super_giant=False,
            system_memory_percent=40.0,
        ),
        "scale reduction did not require topology downgrade",
    )
    require(
        should_degrade_complexity(
            remaining_super_giant=True,
            system_memory_percent=99.0,
        ),
        "system memory near 99 percent did not require topology downgrade",
    )
    require(
        not should_degrade_complexity(
            remaining_super_giant=True,
            system_memory_percent=98.9,
        ),
        "safe boundary below 99 percent degraded without another pressure signal",
    )


def check_normalized_hierarchical_pool() -> None:
    pool = hierarchical_pool()
    require(pool.get("normalized_total_share") == 100.0, "budget pool is not normalized to 100 percent")
    require(pool.get("hard_limits") == HARD_LIMITS, "hard limits were folded into percentage allocation")

    root = lease(pool, "taizi")
    require(root.get("envelope_share") == 100.0, "Taizi root envelope is not 100 percent")
    departments = {
        lease_id
        for lease_id, value in leases(pool).items()
        if value.get("parent_id") == "taizi" and value.get("level") == "department"
    }
    require(
        departments == {"zhongshu", "menxia", "shangshu"},
        f"Taizi envelopes did not target exactly the Three Departments: {departments}",
    )

    ministry = lease(pool, "gongbu")
    worker = lease(pool, "gongbu#worker-1")
    require(ministry.get("parent_id") == "shangshu", "ministry envelope did not originate at Shangshu")
    require(worker.get("parent_id") == "gongbu", "worker lease did not originate at its ministry")
    require(worker.get("owner_id") == "gongbu#worker-1", "worker lease lacks owning-worker identity")

    for parent_id in ("taizi", "shangshu", "gongbu"):
        parent = lease(pool, parent_id)
        envelope = float(parent.get("envelope_share", -1.0))
        allocated = float(parent.get("allocated_share", -1.0))
        reserve = float(parent.get("reserve_share", -1.0))
        require(envelope >= 0.0 and allocated >= 0.0 and reserve >= 0.0, f"invalid shares for {parent_id}")
        require(
            allocated + reserve <= envelope,
            f"allocations plus reserve exceeded parent envelope for {parent_id}",
        )


def check_complete_lease_schema() -> None:
    pool = hierarchical_pool()
    root = lease(pool, "taizi")
    budget_id = root.get("budget_id")
    require(isinstance(budget_id, str) and budget_id, "root budget_id is missing")
    require(root.get("parent_budget_id") is None, "root budget has a parent budget id")

    for child_id, value in leases(pool).items():
        missing = LEASE_REQUIRED_FIELDS.difference(value)
        require(not missing, f"lease {child_id!r} omitted schema fields: {sorted(missing)!r}")
        require(value.get("schema") == "court.budget.lease.v1", f"lease {child_id!r} has the wrong schema")
        require(value.get("budget_id") == budget_id, f"lease {child_id!r} escaped the root budget")
        require(value.get("task_id") == "CCR-R2-SHIR-20260714-A02", f"lease {child_id!r} lost task scope")
        require(value.get("phase_id") == "PHASE1", f"lease {child_id!r} lost phase scope")
        require(value.get("wave_id") == "A02-LANE-J-W1", f"lease {child_id!r} lost wave scope")
        require(value.get("normalized_share") == value.get("envelope_share"), f"lease {child_id!r} share is ambiguous")
        require(value.get("hard_caps") == HARD_LIMITS, f"lease {child_id!r} lost independent hard caps")
        require(isinstance(value.get("write_set"), tuple) and value.get("write_set"), f"lease {child_id!r} lacks a write set")
        require(isinstance(value.get("expected_output"), str) and value.get("expected_output"), f"lease {child_id!r} lacks expected output")
        require(value.get("approved_by"), f"lease {child_id!r} lacks approving authority")
        require(value.get("approved_at"), f"lease {child_id!r} lacks approval time")
        require(value.get("start_condition"), f"lease {child_id!r} lacks start condition")
        require(value.get("expiry_condition"), f"lease {child_id!r} lacks expiry condition")
        require(value.get("return_conditions"), f"lease {child_id!r} lacks return conditions")
        require(value.get("preload_ack") == "PASSED", f"lease {child_id!r} lacks preload acknowledgement")
        measured_cost = value.get("measured_cost")
        require(isinstance(measured_cost, Mapping), f"lease {child_id!r} lacks measured single-agent cost")
        require(float(measured_cost.get("memory_mb", 0)) > 0, f"lease {child_id!r} has no measured memory cost")

    for child_id, value in leases(pool).items():
        parent_id = value.get("parent_id")
        if parent_id is None:
            continue
        parent = lease(pool, str(parent_id))
        require(
            value.get("parent_budget_id") == parent.get("lease_id"),
            f"lease {child_id!r} does not point to its direct parent lease",
        )


def check_read_only_lease_access_contract() -> None:
    pool = hierarchical_pool()
    pool = allocate(
        pool,
        parent_id="gongbu",
        allocator_id="gongbu",
        child_id="gongbu#readonly-reviewer",
        child_level="worker",
        share=2.0,
        role_key="gongbu",
        instance_key="gongbu#readonly-reviewer",
        shard_id="readonly-reviewer",
        write_set=(),
        access_mode="read_only",
        read_scope=("scripts", "references"),
        mutation_allowed=False,
        integration_authority=False,
    )
    reviewer = lease(pool, "gongbu#readonly-reviewer")
    require(reviewer.get("access_mode") == "read_only", "read-only lease lost its access mode")
    require(reviewer.get("write_set") == (), "read-only lease acquired a write set")
    require(reviewer.get("read_scope") == ("scripts", "references"), "read-only lease lost its read scope")
    require(reviewer.get("mutation_allowed") is False, "read-only lease gained mutation authority")
    require(reviewer.get("integration_authority") is False, "read-only lease gained integration authority")


def check_lease_access_contract_rejections() -> None:
    def attempt(**overrides: object) -> Mapping[str, object]:
        values: dict[str, object] = {
            "write_set": (),
            "access_mode": "read_only",
            "read_scope": ("scripts",),
            "mutation_allowed": False,
            "integration_authority": False,
        }
        values.update(overrides)
        return allocate(
            hierarchical_pool(),
            parent_id="gongbu",
            allocator_id="gongbu",
            child_id="gongbu#access-probe",
            child_level="worker",
            share=2.0,
            role_key="gongbu",
            instance_key="gongbu#access-probe",
            shard_id="access-probe",
            **values,  # type: ignore[arg-type]
        )

    require_rejected(
        lambda: attempt(access_mode="read_write", mutation_allowed=True),
        "write_set_required",
    )
    require_rejected(lambda: attempt(read_scope=()), "read_scope_required")
    require_rejected(lambda: attempt(read_scope=("../outside",)), "read_scope_out_of_bounds")
    require_rejected(lambda: attempt(mutation_allowed=True), "read_only_authority_forbidden")
    require_rejected(lambda: attempt(integration_authority=True), "read_only_authority_forbidden")

def add_worker(
    pool: Mapping[str, object],
    child_id: str,
    *,
    shard_id: str,
    write_set: tuple[str, ...],
    share: float = 4.0,
    instance_key: str | None = None,
    direct_superior: str = "gongbu",
    preload_ack: str = "PASSED",
    integration_authority: bool = False,
    integration_domain: str = "gongbu",
    complexity_score: float = 5.0,
    marginal_value_score: float = 8.0,
    memory_mb: int = 512,
    context_tokens: int = 8_000,
    message_chars: int = 1_000,
    tool_calls: int = 2,
    time_seconds: float = 30.0,
    task_id: str = "CCR-R2-SHIR-20260714-A02",
    phase_id: str = "PHASE1",
    wave_id: str = "A02-LANE-J-W1",
    hard_caps: Mapping[str, object] | None = None,
    approved_by: str | None = None,
) -> Mapping[str, object]:
    return allocate(
        pool,
        parent_id="gongbu",
        allocator_id="gongbu",
        child_id=child_id,
        child_level="worker",
        share=share,
        owning_worker_id=child_id,
        role_key="gongbu",
        instance_key=instance_key or child_id,
        direct_superior=direct_superior,
        shard_id=shard_id,
        write_set=write_set,
        integration_domain=integration_domain,
        integration_authority=integration_authority,
        preload_ack=preload_ack,
        measured_cost={
            "memory_mb": memory_mb,
            "context_tokens": context_tokens,
            "message_chars": message_chars,
            "tool_calls": tool_calls,
            "time_seconds": time_seconds,
        },
        complexity_score=complexity_score,
        marginal_value_score=marginal_value_score,
        task_id=task_id,
        phase_id=phase_id,
        wave_id=wave_id,
        hard_caps=hard_caps,
        approved_by=approved_by,
    )


def check_budget_input_identity_contract() -> None:
    pool = hierarchical_pool()
    valid = add_worker(
        pool,
        "gongbu#worker-2",
        shard_id="gongbu-shard-2",
        write_set=("synthetic/gongbu-worker-2",),
    )
    require(
        {value.get("instance_key") for value in leases(valid).values() if value.get("role_key") == "gongbu"}
        >= {"gongbu", "gongbu#worker-1", "gongbu#worker-2"},
        "same-role budget leases were rejected despite disjoint input contracts",
    )

    require_rejected(
        lambda: allocate(
            pool,
            parent_id="taizi",
            allocator_id="taizi",
            child_id="taizi#0002",
            child_level="department",
            share=1.0,
            role_key="taizi",
            instance_key="taizi#0002",
            shard_id="taizi-2",
            write_set=("synthetic/taizi-2",),
        ),
        "taizi_singleton",
    )
    require_rejected(
        lambda: add_worker(
            pool,
            "gongbu#worker-duplicate-instance",
            instance_key="gongbu#worker-1",
            shard_id="unique-shard",
            write_set=("synthetic/unique-instance-check",),
        ),
        "duplicate_instance_key",
    )
    require_rejected(
        lambda: add_worker(
            pool,
            "gongbu#worker-duplicate-shard",
            shard_id="gongbu#worker-1",
            write_set=("synthetic/unique-shard-check",),
        ),
        "duplicate_shard",
    )
    require_rejected(
        lambda: add_worker(
            pool,
            "gongbu#worker-write-conflict",
            shard_id="write-conflict-shard",
            write_set=("synthetic/gongbu#worker-1",),
        ),
        "write_set_overlap",
    )
    require_rejected(
        lambda: add_worker(
            pool,
            "gongbu#worker-duplicate-integrator",
            shard_id="integrator-shard",
            write_set=("synthetic/integrator-check",),
            integration_authority=True,
        ),
        "duplicate_integration_authority",
    )
    require_rejected(
        lambda: add_worker(
            pool,
            "gongbu#worker-wrong-superior",
            shard_id="wrong-superior-shard",
            write_set=("synthetic/wrong-superior",),
            direct_superior="shangshu",
        ),
        "direct_superior_mismatch",
    )
    require_rejected(
        lambda: add_worker(
            pool,
            "gongbu#worker-no-preload",
            shard_id="no-preload-shard",
            write_set=("synthetic/no-preload",),
            preload_ack="",
        ),
        "preload_required",
    )


def check_exact_authority_role_chain() -> None:
    pool = hierarchical_pool()
    invalid_allocations = (
        lambda: allocate(
            pool,
            parent_id="zhongshu",
            allocator_id="zhongshu",
            child_id="gongbu-from-zhongshu",
            child_level="ministry",
            share=1.0,
            role_key="gongbu",
            shard_id="illegal-zhongshu-gongbu",
            write_set=("synthetic/illegal-zhongshu-gongbu",),
        ),
        lambda: allocate(
            pool,
            parent_id="taizi",
            allocator_id="taizi",
            child_id="hubu-direct-department",
            child_level="department",
            share=1.0,
            role_key="hubu",
            shard_id="illegal-taizi-hubu",
            write_set=("synthetic/illegal-taizi-hubu",),
        ),
        lambda: allocate(
            pool,
            parent_id="shangshu",
            allocator_id="shangshu",
            child_id="zhongshu-as-ministry",
            child_level="ministry",
            share=1.0,
            role_key="zhongshu",
            shard_id="illegal-shangshu-zhongshu",
            write_set=("synthetic/illegal-shangshu-zhongshu",),
        ),
        lambda: allocate(
            pool,
            parent_id="gongbu",
            allocator_id="gongbu",
            child_id="xingbu#borrowed-worker",
            child_level="worker",
            share=1.0,
            role_key="xingbu",
            shard_id="illegal-cross-ministry-worker",
            write_set=("synthetic/illegal-cross-ministry-worker",),
            owning_worker_id="xingbu#borrowed-worker",
        ),
    )
    for action in invalid_allocations:
        require_rejected(action, "authority_chain_violation")


def check_duplicate_child_id_is_rejected_before_accounting() -> None:
    pool = hierarchical_pool()
    allocated_before = lease(pool, "gongbu").get("allocated_share")
    require_rejected(
        lambda: add_worker(
            pool,
            "gongbu#worker-1",
            instance_key="gongbu#worker-replacement",
            shard_id="replacement-shard",
            write_set=("synthetic/replacement-write",),
            share=1.0,
        ),
        "duplicate_child_id",
    )
    require(
        lease(pool, "gongbu").get("allocated_share") == allocated_before,
        "duplicate child allocation mutated parent accounting",
    )


def check_active_descendants_block_parent_release() -> None:
    pool = hierarchical_pool()
    for parent_id in ("gongbu", "shangshu"):
        require_rejected(
            lambda parent_id=parent_id: release(
                deepcopy(pool),
                lease_id=str(lease(pool, parent_id).get("lease_id")),
                reason="COMPLETED",
                evidence=f"completion evidence for {parent_id}",
                active_useful=False,
            ),
            "active_descendants_present",
        )


def check_release_requires_terminal_reason_and_evidence() -> None:
    pool = hierarchical_pool()
    worker_lease_id = str(lease(pool, "gongbu#worker-1").get("lease_id"))
    require_rejected(
        lambda: release(
            deepcopy(pool),
            lease_id=worker_lease_id,
            reason="REBALANCE",
            evidence="rebalance request without terminal authority",
            active_useful=False,
        ),
        "release_reason_not_terminal",
    )
    require_rejected(
        lambda: release(
            deepcopy(pool),
            lease_id=worker_lease_id,
            reason="COMPLETED",
            evidence=None,
            active_useful=False,
        ),
        "release_evidence_required",
    )
    degraded = release(
        deepcopy(pool),
        lease_id=worker_lease_id,
        reason="DEGRADED",
        evidence="resource sample resource-sample-099 forced traced downgrade",
        active_useful=False,
    )
    require(
        lease(degraded, "gongbu#worker-1").get("release_reason") == "DEGRADED",
        "traced degradation did not release the lease",
    )


def check_non_finite_numbers_fail_closed() -> None:
    for invalid in (float("nan"), float("inf"), float("-inf")):
        require_rejected(
            lambda invalid=invalid: normalize_budget_pool(
                total_share=invalid,
                root_id="taizi",
                reserve_share=10.0,
                hard_limits=HARD_LIMITS,
                task_id="CCR-R2-SHIR-20260714-A02",
                phase="PHASE1",
                wave_id="A02-LANE-J-W1",
                approved_by="taizi",
                approved_at="2026-07-15T00:00:00Z",
                expected_output="bounded court execution",
                return_conditions=("DECREE_COMPLETE", "CANCELLED"),
            ),
            "non_finite_number",
        )

    pool = hierarchical_pool()
    require_rejected(
        lambda: add_worker(
            pool,
            "gongbu#worker-nan-share",
            shard_id="nan-share",
            write_set=("synthetic/nan-share",),
            share=float("nan"),
        ),
        "non_finite_number",
    )
    require_rejected(
        lambda: add_worker(
            pool,
            "gongbu#worker-inf-cost",
            shard_id="inf-cost",
            write_set=("synthetic/inf-cost",),
            memory_mb=float("inf"),
        ),
        "non_finite_number",
    )
    require_rejected(
        lambda: plan_budgeted_launch(
            pool,
            candidates=[worker_candidate(pool)],
            resource_state={**SAFE_RESOURCE_STATE, "free_memory_mb": float("nan")},
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        ),
        "resource_sample_non_finite",
    )
    require_rejected(
        lambda: normalize_budget_pool(
            total_share=100.0,
            root_id="taizi",
            reserve_share=10.0,
            hard_limits={**HARD_LIMITS, "ram_percent_max": float("inf")},
            task_id="CCR-R2-SHIR-20260714-A02",
            phase="PHASE1",
            wave_id="A02-LANE-J-W1",
            approved_by="taizi",
            approved_at="2026-07-15T00:00:00Z",
            expected_output="bounded court execution",
            return_conditions=("DECREE_COMPLETE", "CANCELLED"),
        ),
        "non_finite_number",
    )

    valid = hierarchical_pool()
    for child_id, value in leases(valid).items():
        for field in ("normalized_share", "envelope_share", "allocated_share", "reserve_share", "available_share"):
            require(math.isfinite(float(value.get(field, float("nan")))), f"{child_id} {field} became non-finite")


def check_resource_sample_timestamp_and_age() -> None:
    pool = hierarchical_pool()
    candidate = worker_candidate(pool)
    require_rejected(
        lambda: plan_budgeted_launch(
            pool,
            candidates=[candidate],
            resource_state={
                **SAFE_RESOURCE_STATE,
                "sample_id": "resource-sample-stale",
                "sampled_at": "2000-01-01T00:00:00Z",
            },
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        ),
        "resource_sample_stale",
    )
    require_rejected(
        lambda: plan_budgeted_launch(
            pool,
            candidates=[candidate],
            resource_state={**SAFE_RESOURCE_STATE, "sampled_at": "not-a-timestamp"},
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        ),
        "resource_sample_timestamp_invalid",
    )



def check_reassessment_requires_new_sample_identity() -> None:
    pool = hierarchical_pool()
    first = reassess_budget_pool(
        deepcopy(pool),
        trigger="NEW_WAVE",
        resource_state=SAFE_RESOURCE_STATE,
        active_useful_lease_ids=(str(lease(pool, "gongbu#worker-1").get("lease_id")),),
        cancelled_lease_ids=(),
        exception_evidence={},
    )
    require_rejected(
        lambda: reassess_budget_pool(
            deepcopy(first),
            trigger="RESOURCE_CHANGE",
            resource_state=SAFE_RESOURCE_STATE,
            active_useful_lease_ids=(str(lease(pool, "gongbu#worker-1").get("lease_id")),),
            cancelled_lease_ids=(),
            exception_evidence={},
        ),
        "resource_resample_required",
    )


def check_per_agent_hard_caps_project_to_admission() -> None:
    context_pool = add_worker(
        hierarchical_pool(),
        "gongbu#worker-context-overage",
        shard_id="context-overage",
        write_set=("synthetic/context-overage",),
        share=3.0,
        context_tokens=100_001,
    )
    context_child = "gongbu#worker-context-overage"
    context_plan = launch_plan(
        context_pool,
        [worker_candidate_for(context_pool, context_child)],
        SAFE_RESOURCE_STATE,
        approval_count=1,
    )
    require(tuple(context_plan.get("launch_ids", ())) == (), "per-agent context overage was launched")
    context_deferred = context_plan.get("deferred")
    require(isinstance(context_deferred, Mapping), "context overage omitted deferral evidence")
    require(
        context_deferred.get(context_child) == "hard_limit:per_agent_context",
        "per-agent context cap was not projected into admission",
    )

    tool_pool = add_worker(
        hierarchical_pool(),
        "gongbu#worker-tool-overage",
        shard_id="tool-overage",
        write_set=("synthetic/tool-overage",),
        share=3.0,
        tool_calls=9,
    )
    tool_child = "gongbu#worker-tool-overage"
    tool_plan = launch_plan(
        tool_pool,
        [worker_candidate_for(tool_pool, tool_child)],
        SAFE_RESOURCE_STATE,
        approval_count=1,
    )
    require(tuple(tool_plan.get("launch_ids", ())) == (), "per-agent tool overage was launched")
    tool_deferred = tool_plan.get("deferred")
    require(isinstance(tool_deferred, Mapping), "tool overage omitted deferral evidence")
    require(
        tool_deferred.get(tool_child) == "hard_limit:per_agent_tools",
        "per-agent tool cap was not projected into admission",
    )


def check_windows_write_set_aliases_conflict() -> None:
    mixed_case_alias = "C:" + r"\Repo\Area\..\X"
    normalized_alias = "c:" + "/repo/x"
    pool = add_worker(
        hierarchical_pool(),
        "gongbu#worker-windows-path-1",
        shard_id="windows-path-1",
        write_set=(mixed_case_alias,),
        share=3.0,
    )
    require_rejected(
        lambda: add_worker(
            pool,
            "gongbu#worker-windows-path-2",
            shard_id="windows-path-2",
            write_set=(normalized_alias,),
            share=3.0,
        ),
        "write_set_overlap",
    )


def check_released_child_history_is_immutable() -> None:
    pool = hierarchical_pool()
    child_id = "gongbu#worker-1"
    original_lease_id = str(lease(pool, child_id).get("lease_id"))
    completed = release(
        deepcopy(pool),
        lease_id=original_lease_id,
        reason="COMPLETED",
        evidence="completion evidence immutable-001",
        active_useful=False,
    )
    require_rejected(
        lambda: add_worker(
            completed,
            child_id,
            instance_key="gongbu#worker-1-generation-2",
            shard_id="generation-2",
            write_set=("synthetic/generation-2",),
            share=1.0,
        ),
        "child_id_history_conflict",
    )
    released = lease(completed, child_id)
    require(released.get("lease_id") == original_lease_id, "released lease id was replaced")
    require(
        released.get("release_evidence") == "completion evidence immutable-001",
        "released lease evidence was overwritten",
    )
    history = released.get("release_history")
    require(isinstance(history, tuple) and len(history) == 1, "release history is not immutable append-only evidence")


def check_public_pool_actions_reject_forged_accounting() -> None:
    pool = hierarchical_pool()
    worker_id = str(lease(pool, "gongbu#worker-1").get("lease_id"))

    forged_available = deepcopy(pool)
    forged_available["leases"]["gongbu"]["available_share"] = 999.0  # type: ignore[index]
    require_rejected(
        lambda: add_worker(
            forged_available,
            "gongbu#forged-allocate",
            shard_id="forged-allocate",
            write_set=("synthetic/forged-allocate",),
            share=1.0,
        ),
        "budget_pool_invariant_violation",
    )

    forged_allocated = deepcopy(pool)
    forged_allocated["leases"]["gongbu"]["allocated_share"] = 0.0  # type: ignore[index]
    require_rejected(
        lambda: release(
            forged_allocated,
            lease_id=worker_id,
            reason="COMPLETED",
            evidence="forged release must fail",
            active_useful=False,
        ),
        "budget_pool_invariant_violation",
    )

    forged_reserve = deepcopy(pool)
    forged_reserve["leases"]["gongbu"]["reserve_share"] = 0.0  # type: ignore[index]
    require_rejected(
        lambda: plan_budgeted_launch(
            forged_reserve,
            candidates=[worker_candidate(pool)],
            resource_state=SAFE_RESOURCE_STATE,
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        ),
        "budget_pool_invariant_violation",
    )

    forged_envelope = deepcopy(pool)
    forged_envelope["leases"]["gongbu"]["envelope_share"] = 21.0  # type: ignore[index]
    require_rejected(
        lambda: reassess_budget_pool(
            forged_envelope,
            trigger="NEW_WAVE",
            resource_state=SAFE_RESOURCE_STATE,
            active_useful_lease_ids=(worker_id,),
            cancelled_lease_ids=(),
            exception_evidence={},
        ),
        "budget_pool_invariant_violation",
    )


def check_previous_sample_is_authoritative_and_monotonic() -> None:
    pool = hierarchical_pool()
    worker_lease_id = str(lease(pool, "gongbu#worker-1").get("lease_id"))
    sampled = reassess_budget_pool(
        deepcopy(pool),
        trigger="NEW_WAVE",
        resource_state=SAFE_RESOURCE_STATE,
        active_useful_lease_ids=(worker_lease_id,),
        cancelled_lease_ids=(),
        exception_evidence={},
    )
    candidate = worker_candidate(sampled)
    require_rejected(
        lambda: plan_budgeted_launch(
            sampled,
            candidates=[candidate],
            resource_state=SAFE_RESOURCE_STATE,
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        ),
        "resource_resample_required",
    )
    require_rejected(
        lambda: plan_budgeted_launch(
            sampled,
            candidates=[candidate],
            resource_state={**SAFE_RESOURCE_STATE, "sample_id": "resource-sample-002"},
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        ),
        "resource_resample_required",
    )
    older = {
        **SAFE_RESOURCE_STATE,
        "sample_id": "resource-sample-002",
        "sampled_at": "2026-07-14T23:59:59Z",
    }
    require_rejected(
        lambda: reassess_budget_pool(
            sampled,
            trigger="RESOURCE_CHANGE",
            resource_state=older,
            active_useful_lease_ids=(worker_lease_id,),
            cancelled_lease_ids=(),
            exception_evidence={},
        ),
        "resource_resample_required",
    )


def check_cumulative_prospective_resources() -> None:
    memory_pool = add_worker(
        hierarchical_pool(),
        "gongbu#worker-memory-overage",
        shard_id="memory-overage",
        write_set=("synthetic/memory-overage",),
        share=3.0,
        memory_mb=2_049,
    )
    memory_child = "gongbu#worker-memory-overage"
    memory_plan = launch_plan(
        memory_pool,
        [worker_candidate_for(memory_pool, memory_child)],
        SAFE_RESOURCE_STATE,
        approval_count=1,
    )
    require(tuple(memory_plan.get("launch_ids", ())) == (), "per-agent memory overage was launched")
    require(
        memory_plan.get("deferred", {}).get(memory_child) == "hard_limit:per_agent_memory",  # type: ignore[union-attr]
        "per-agent memory cap was not projected into admission",
    )

    context_pool = hierarchical_pool()
    context_ids = ("gongbu#context-a", "gongbu#context-b")
    for child_id in context_ids:
        context_pool = add_worker(
            context_pool,
            child_id,
            shard_id=child_id,
            write_set=(f"synthetic/{child_id}",),
            share=3.0,
            memory_mb=100,
            context_tokens=45_000,
            tool_calls=1,
        )
    context_plan = launch_plan(
        context_pool,
        [worker_candidate_for(context_pool, child_id) for child_id in context_ids],
        SAFE_RESOURCE_STATE,
        approval_count=2,
    )
    require(len(tuple(context_plan.get("launch_ids", ()))) == 1, "prospective context was not cumulative")
    require(
        "composite_budget_exhausted:context" in context_plan.get("deferred", {}).values(),  # type: ignore[union-attr]
        "cumulative context exhaustion was not recorded",
    )

    tool_pool = hierarchical_pool()
    tool_ids = ("gongbu#tools-a", "gongbu#tools-b")
    for child_id in tool_ids:
        tool_pool = add_worker(
            tool_pool,
            child_id,
            shard_id=child_id,
            write_set=(f"synthetic/{child_id}",),
            share=3.0,
            memory_mb=100,
            context_tokens=1_000,
            tool_calls=4,
        )
    tool_plan = launch_plan(
        tool_pool,
        [worker_candidate_for(tool_pool, child_id) for child_id in tool_ids],
        SAFE_RESOURCE_STATE,
        approval_count=2,
    )
    require(len(tuple(tool_plan.get("launch_ids", ()))) == 1, "prospective tools were not cumulative")
    require(
        "composite_budget_exhausted:tools" in tool_plan.get("deferred", {}).values(),  # type: ignore[union-attr]
        "cumulative tool exhaustion was not recorded",
    )

    slot_plan = launch_plan(
        context_pool,
        [worker_candidate_for(context_pool, child_id) for child_id in context_ids],
        {**SAFE_RESOURCE_STATE, "host_capacity": 2, "active_agents": 1},
        approval_count=2,
    )
    require(len(tuple(slot_plan.get("launch_ids", ()))) == 1, "prospective slots were not cumulative")
    require(
        "composite_budget_exhausted:host_capacity" in slot_plan.get("deferred", {}).values(),  # type: ignore[union-attr]
        "cumulative slot exhaustion was not recorded",
    )


def check_windows_extended_aliases_conflict() -> None:
    extended_prefix = "\\\\" + "?\\"
    drive = "C:"
    extended_alias = extended_prefix + drive + r"\Repo\Area.\Temp \..\X. "
    ordinary_alias = "c:" + "/repo/area/./x"
    pool = add_worker(
        hierarchical_pool(),
        "gongbu#windows-extended-a",
        shard_id="windows-extended-a",
        write_set=(extended_alias,),
        share=3.0,
    )
    require_rejected(
        lambda: add_worker(
            pool,
            "gongbu#windows-extended-b",
            shard_id="windows-extended-b",
            write_set=(ordinary_alias,),
            share=3.0,
        ),
        "write_set_overlap",
    )


def check_numeric_domains_reject_invalid_values_stably() -> None:
    pool = hierarchical_pool()
    candidate = worker_candidate(pool)
    for requested in (-1, 1.5, "1", float("nan"), float("inf")):
        require_stable_rejected(
            lambda requested=requested: plan_budgeted_launch(
                pool,
                candidates=[candidate],
                resource_state=SAFE_RESOURCE_STATE,
                requested_count=requested,  # type: ignore[arg-type]
                taizi_approved_count=1,
                previous_sample_id=None,
            ),
            "invalid_requested_count",
        )
    for approved in (-1, 1.5, "1", float("nan"), float("inf")):
        require_stable_rejected(
            lambda approved=approved: plan_budgeted_launch(
                pool,
                candidates=[candidate],
                resource_state=SAFE_RESOURCE_STATE,
                requested_count=1,
                taizi_approved_count=approved,  # type: ignore[arg-type]
                previous_sample_id=None,
            ),
            "invalid_approved_count",
        )
    resource_cases = (
        ({**SAFE_RESOURCE_STATE, "active_agents": -1}, "resource_sample_negative"),
        ({**SAFE_RESOURCE_STATE, "active_agents": 1.5}, "resource_sample_count_not_integer"),
        ({**SAFE_RESOURCE_STATE, "host_capacity": 1.5}, "resource_sample_count_not_integer"),
        ({**SAFE_RESOURCE_STATE, "ram_percent": -1.0}, "resource_sample_negative"),
    )
    for resource_state, expected in resource_cases:
        require_stable_rejected(
            lambda resource_state=resource_state: plan_budgeted_launch(
                pool,
                candidates=[candidate],
                resource_state=resource_state,
                requested_count=1,
                taizi_approved_count=1,
                previous_sample_id=None,
            ),
            expected,
        )


def check_release_authority_and_timestamp_binding() -> None:
    pool = hierarchical_pool()
    worker_lease_id = str(lease(pool, "gongbu#worker-1").get("lease_id"))
    completed = release(
        deepcopy(pool),
        lease_id=worker_lease_id,
        reason="COMPLETED",
        evidence="completion evidence release-bind-001",
        active_useful=False,
        released_by="gongbu",
        released_at="2026-07-15T00:15:00Z",
    )
    terminal = lease(completed, "gongbu#worker-1")
    require(terminal.get("released_by") == "gongbu", "release actor was not bound")
    require(terminal.get("release_authority") == "gongbu", "release authority was not preserved")
    require(terminal.get("released_at") == "2026-07-15T00:15:00Z", "release timestamp was not preserved")

    require_rejected(
        lambda: release(
            deepcopy(pool),
            lease_id=worker_lease_id,
            reason="COMPLETED",
            evidence="wrong authority",
            active_useful=False,
            released_by="OTHER",
        ),
        "release_authority_mismatch",
    )
    require_rejected(
        lambda: release(
            deepcopy(pool),
            lease_id=worker_lease_id,
            reason="COMPLETED",
            evidence="missing authority",
            active_useful=False,
            released_by="",
        ),
        "release_authority_required",
    )
    require_rejected(
        lambda: release(
            deepcopy(pool),
            lease_id=worker_lease_id,
            reason="COMPLETED",
            evidence="bad timestamp",
            active_useful=False,
            released_at="not-a-timestamp",
        ),
        "release_timestamp_invalid",
    )


def check_integration_authority_is_globally_bound() -> None:
    pool = hierarchical_pool()
    authorities = [
        value.get("instance_key")
        for value in leases(pool).values()
        if value.get("status") == "ACTIVE" and value.get("integration_authority") is True
    ]
    require(authorities == ["shangshu"], f"integration authority is not globally unique: {authorities!r}")
    require_rejected(
        lambda: add_worker(
            pool,
            "gongbu#domain-bypass",
            shard_id="domain-bypass",
            write_set=("synthetic/domain-bypass",),
            integration_domain="attacker-domain",
        ),
        "integration_domain_mismatch",
    )
    require_rejected(
        lambda: allocate(
            pool,
            parent_id="taizi",
            allocator_id="taizi",
            child_id="zhongshu#second-integrator",
            child_level="department",
            share=1.0,
            role_key="zhongshu",
            shard_id="second-integrator",
            write_set=("synthetic/second-integrator",),
            integration_domain="zhongshu",
            integration_authority=True,
        ),
        "duplicate_integration_authority",
    )


def check_absolute_sample_age_uses_now() -> None:
    pool = hierarchical_pool()
    ancient = {
        **SAFE_RESOURCE_STATE,
        "sample_id": "resource-sample-ancient-self-certified",
        "sampled_at": "2000-01-01T00:00:00Z",
        "decision_at": "2000-01-01T00:00:00Z",
    }
    require_rejected(
        lambda: plan_budgeted_launch(
            pool,
            candidates=[worker_candidate(pool)],
            resource_state=ancient,
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        ),
        "resource_sample_stale",
    )


def check_release_reason_is_lease_bound() -> None:
    pool = hierarchical_pool()
    worker_id = "gongbu#worker-1"
    restricted = deepcopy(pool)
    restricted["leases"][worker_id]["return_conditions"] = ("COMPLETED",)  # type: ignore[index]
    require_rejected(
        lambda: release(
            restricted,
            lease_id=str(lease(pool, worker_id).get("lease_id")),
            reason="DEGRADED",
            evidence="arbitrary evidence cannot expand return conditions",
            active_useful=False,
        ),
        "release_reason_not_allowed",
    )


def check_degradation_and_task_counts_reject_non_finite() -> None:
    for invalid in (float("nan"), float("inf"), float("-inf")):
        require_stable_rejected(
            lambda invalid=invalid: should_degrade_complexity(
                remaining_super_giant=True,
                system_memory_percent=invalid,
            ),
            "invalid_system_memory_percent",
        )
        require_stable_rejected(
            lambda invalid=invalid: is_super_giant_task(
                task_kind="batch_processing",
                batch_item_count=invalid,  # type: ignore[arg-type]
            ),
            "invalid_task_count",
        )


def check_child_scope_and_authority_binding() -> None:
    pool = hierarchical_pool()
    worker = lease(pool, "gongbu#worker-1")
    parent = lease(pool, "gongbu")
    require(parent.get("task_id") == "CCR-R2-SHIR-20260714-A02", "parent task scope is missing")
    require(parent.get("phase_id") == "PHASE1", "parent phase scope is missing")
    require(parent.get("wave_id") == "A02-LANE-J-W1", "parent wave scope is missing")
    require(worker.get("task_id") == parent.get("task_id"), "child task id did not inherit parent scope")
    require(worker.get("phase_id") == "PHASE1", "child phase id did not inherit parent scope")
    require(worker.get("wave_id") == parent.get("wave_id"), "child wave id did not inherit parent scope")
    require(worker.get("hard_caps") == parent.get("hard_caps"), "child hard caps did not inherit parent scope")
    require(worker.get("approved_by") == "gongbu", "child approver is not its direct allocating authority")

    invalid_bindings = (
        (
            lambda: add_worker(
                pool,
                "gongbu#worker-other-task",
                shard_id="other-task",
                write_set=("synthetic/other-task",),
                task_id="OTHER",
            ),
            "task_scope_mismatch",
        ),
        (
            lambda: add_worker(
                pool,
                "gongbu#worker-other-phase",
                shard_id="other-phase",
                write_set=("synthetic/other-phase",),
                phase_id="OTHER",
            ),
            "phase_scope_mismatch",
        ),
        (
            lambda: add_worker(
                pool,
                "gongbu#worker-other-wave",
                shard_id="other-wave",
                write_set=("synthetic/other-wave",),
                wave_id="OTHER",
            ),
            "wave_scope_mismatch",
        ),
        (
            lambda: add_worker(
                pool,
                "gongbu#worker-empty-caps",
                shard_id="empty-caps",
                write_set=("synthetic/empty-caps",),
                hard_caps={},
            ),
            "hard_caps_required",
        ),
        (
            lambda: add_worker(
                pool,
                "gongbu#worker-other-caps",
                shard_id="other-caps",
                write_set=("synthetic/other-caps",),
                hard_caps={**HARD_LIMITS, "ram_percent_max": 98.0},
            ),
            "hard_caps_mismatch",
        ),
        (
            lambda: add_worker(
                pool,
                "gongbu#worker-other-approver",
                shard_id="other-approver",
                write_set=("synthetic/other-approver",),
                approved_by="OTHER",
            ),
            "approver_mismatch",
        ),
    )
    for action, expected in invalid_bindings:
        require_rejected(action, expected)


def check_envelope_conservation_and_hierarchy_rejections() -> None:
    pool = hierarchical_pool()
    require_rejected(
        lambda: allocate(
            pool,
            parent_id="taizi",
            allocator_id="taizi",
            child_id="zhongshu#budget-overflow",
            child_level="department",
            share=11.0,
        ),
        "parent_envelope_exceeded",
    )
    require_rejected(
        lambda: allocate(
            pool,
            parent_id="gongbu",
            allocator_id="gongbu",
            child_id="gongbu#worker-2",
            child_level="worker",
            share=11.0,
            owning_worker_id="gongbu#worker-2",
        ),
        "parent_envelope_exceeded",
    )
    require_rejected(
        lambda: allocate(
            pool,
            parent_id="taizi",
            allocator_id="taizi",
            child_id="gongbu-direct",
            child_level="ministry",
            share=1.0,
        ),
        "cross_level_allocation",
    )
    require_rejected(
        lambda: allocate(
            pool,
            parent_id="shangshu",
            allocator_id="libu",
            child_id="libu",
            child_level="ministry",
            share=1.0,
        ),
        "self_mint_forbidden",
    )
    require_rejected(
        lambda: allocate(
            pool,
            parent_id="xingbu",
            allocator_id="xingbu",
            child_id="xingbu#worker-1",
            child_level="worker",
            share=1.0,
            owning_worker_id="xingbu#worker-1",
        ),
        "missing_parent_lease",
    )


def worker_candidate(pool: Mapping[str, object]) -> dict[str, object]:
    worker = lease(pool, "gongbu#worker-1")
    lease_id = worker.get("lease_id")
    require(isinstance(lease_id, str) and lease_id, "worker lease id is missing")
    return {"child_id": "gongbu#worker-1", "lease_id": lease_id}


def launch_plan(
    pool: Mapping[str, object],
    candidates: list[dict[str, object]],
    resource_state: Mapping[str, object],
    *,
    approval_count: int | None = None,
    previous_sample_id: str | None = None,
    approved_child_ids: tuple[str, ...] | None = None,
) -> Mapping[str, object]:
    effective_approval_count = len(candidates) if approval_count is None else approval_count
    approved_bindings = (
        tuple(approval_binding(pool, child_id) for child_id in approved_child_ids)
        if approved_child_ids is not None
        else None
    )
    plan = call_plan(
        pool,
        candidates=candidates,
        resource_state=resource_state,
        requested_count=len(candidates),
        taizi_approved_count=effective_approval_count,
        previous_sample_id=previous_sample_id,
        taizi_approved_bindings=approved_bindings,
    )
    require(isinstance(plan, Mapping), "budgeted launch planner must return a mapping")
    require(plan.get("preflight_before_launch") is True, "launch planner did not budget before launch")
    require(tuple(plan.get("interrupt_ids", ())) == (), "launch planner used surplus post-launch interrupts")
    require(
        plan.get("decision_model") == "COMPOSITE_NOT_SINGLE_THRESHOLD",
        "launch planner used a single non-hard threshold",
    )
    require(
        set(plan.get("decision_factors", ())) == COMPOSITE_FACTORS,
        "launch planner did not jointly consider the complete budget factor set",
    )
    require(plan.get("resource_sample_complete") is True, "launch planner accepted an incomplete resource sample")
    return plan


def check_child_lease_and_preflight_launch_contract() -> None:
    pool = hierarchical_pool()
    candidate = worker_candidate(pool)
    unleased = {"child_id": "gongbu#worker-unleased", "lease_id": None}
    plan = launch_plan(pool, [candidate, unleased], SAFE_RESOURCE_STATE, approval_count=1)
    require(tuple(plan.get("launch_ids", ())) == ("gongbu#worker-1",), "leased worker was not the sole launch")
    deferred = plan.get("deferred")
    require(isinstance(deferred, Mapping), "launch plan did not expose deferred children")
    require(
        deferred.get("gongbu#worker-unleased") == "child_lease_required",
        "child without a lease was not deferred before launch",
    )


def check_hard_limits_are_independent() -> None:
    pool = hierarchical_pool()
    candidate = worker_candidate(pool)
    cases = (
        ("ram", {**SAFE_RESOURCE_STATE, "ram_percent": 99.0}),
        ("context", {**SAFE_RESOURCE_STATE, "context_tokens": 100_001}),
        ("tools", {**SAFE_RESOURCE_STATE, "tool_calls": 9}),
        ("host_capacity", {**SAFE_RESOURCE_STATE, "host_capacity": 1, "active_agents": 1}),
        ("free_memory", {**SAFE_RESOURCE_STATE, "free_memory_mb": 511}),
    )
    for reason, resource_state in cases:
        plan = launch_plan(pool, [candidate], resource_state)
        require(tuple(plan.get("launch_ids", ())) == (), f"{reason} hard limit still launched a child")
        deferred = plan.get("deferred")
        require(isinstance(deferred, Mapping), f"{reason} hard-limit plan omitted deferral evidence")
        require(
            deferred.get("gongbu#worker-1") == f"hard_limit:{reason}",
            f"{reason} hard limit was replaced by percentage-budget reasoning",
        )


def composite_candidate_pool() -> Mapping[str, object]:
    pool = hierarchical_pool()
    pool = add_worker(
        pool,
        "gongbu#worker-2",
        shard_id="gongbu-shard-2",
        write_set=("synthetic/composite-2",),
        share=3.0,
        complexity_score=2.0,
        marginal_value_score=9.0,
        memory_mb=256,
    )
    pool = add_worker(
        pool,
        "gongbu#worker-3",
        shard_id="gongbu-shard-3",
        write_set=("synthetic/composite-3",),
        share=3.0,
        complexity_score=8.0,
        marginal_value_score=9.0,
        memory_mb=1_024,
    )
    return add_worker(
        pool,
        "gongbu#worker-4",
        shard_id="gongbu-shard-4",
        write_set=("synthetic/composite-4",),
        share=3.0,
        complexity_score=9.0,
        marginal_value_score=2.0,
        memory_mb=256,
    )


def composite_candidates(pool: Mapping[str, object]) -> list[dict[str, object]]:
    return [worker_candidate_for(pool, f"gongbu#worker-{index}") for index in range(1, 5)]


def worker_candidate_for(pool: Mapping[str, object], child_id: str) -> dict[str, object]:
    value = lease(pool, child_id)
    lease_id = value.get("lease_id")
    require(isinstance(lease_id, str) and lease_id, f"worker lease id is missing for {child_id}")
    return {"child_id": child_id, "lease_id": lease_id}


def check_composite_resource_and_value_admission() -> None:
    pool = composite_candidate_pool()
    candidates = composite_candidates(pool)
    ample = launch_plan(pool, candidates, SAFE_RESOURCE_STATE, approval_count=4)
    require(ample.get("requested_count") == 4, "composite plan lost requested agent count")
    require(ample.get("approved_count") == 3, "low-value work was counted as an approved launch")
    require(
        set(ample.get("launch_ids", ())) == {
            "gongbu#worker-1",
            "gongbu#worker-2",
            "gongbu#worker-3",
        },
        "composite plan did not retain the three useful independent workers",
    )
    deferred = ample.get("deferred")
    require(isinstance(deferred, Mapping), "composite plan omitted deferral reasons")
    require(
        deferred.get("gongbu#worker-4") == "low_marginal_value",
        "ample capacity admitted low-value complexity",
    )

    memory_limited = launch_plan(
        pool,
        candidates[:3],
        {**SAFE_RESOURCE_STATE, "free_memory_mb": 700},
        approval_count=3,
    )
    require(
        len(tuple(memory_limited.get("launch_ids", ()))) == 1,
        "agent count and host slots overrode measured free-memory cost",
    )
    host_limited = launch_plan(
        pool,
        candidates[:3],
        {**SAFE_RESOURCE_STATE, "host_capacity": 2, "active_agents": 1},
        approval_count=3,
    )
    require(
        len(tuple(host_limited.get("launch_ids", ()))) == 1,
        "free memory overrode actual host-capacity headroom",
    )

    incomplete = dict(SAFE_RESOURCE_STATE)
    incomplete.pop("free_memory_mb")
    require_rejected(
        lambda: plan_budgeted_launch(
            pool,
            candidates=candidates[:1],
            resource_state=incomplete,
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        ),
        "resource_sample_incomplete",
    )


def check_small_wave_approval_and_resample() -> None:
    pool = composite_candidate_pool()
    candidates = composite_candidates(pool)[:3]
    downsized = launch_plan(pool, candidates, SAFE_RESOURCE_STATE, approval_count=2)
    require(downsized.get("requested_count") == 3, "small-wave request count is wrong")
    require(downsized.get("taizi_approved_count") == 2, "Taizi approval count is missing")
    require(downsized.get("approved_count") == 2, "small-wave approved count is wrong")
    require(len(tuple(downsized.get("launch_ids", ()))) == 2, "request N launched more than approved M")
    require(downsized.get("approval_status") == "DOWNSIZED", "N-to-M decision was not recorded")
    require(downsized.get("resource_sample_id") == "resource-sample-001", "resource sample id was not recorded")
    require(downsized.get("resample_required_before_next_wave") is True, "next wave did not require re-sampling")
    deferred = downsized.get("deferred")
    require(isinstance(deferred, Mapping), "downsized wave omitted deferred candidates")
    require(
        sum(reason == "not_approved_this_wave" for reason in deferred.values()) == 1,
        "downsized wave did not preserve the unapproved candidate",
    )
    consumed_pool = downsized.get("budget_pool")
    require(isinstance(consumed_pool, Mapping), "launch plan did not return the consumed budget pool")

    require_rejected(
        lambda: call_plan(
            consumed_pool,
            candidates=candidates,
            resource_state=SAFE_RESOURCE_STATE,
            requested_count=3,
            taizi_approved_count=1,
            previous_sample_id="resource-sample-001",
        ),
        "resource_resample_required",
    )
    fresh_sample = {
        **SAFE_RESOURCE_STATE,
        "sample_id": "resource-sample-002",
        "sampled_at": "2026-07-15T00:05:00Z",
        "decision_at": "2026-07-15T00:05:30Z",
        "now": "2026-07-15T00:05:30Z",
        "active_agents": 3,
        "free_memory_mb": 14_000,
    }
    remaining_ids = tuple(
        child_id for child_id, reason in deferred.items() if reason == "not_approved_this_wave"
    )
    require(len(remaining_ids) == 1, "downsized wave did not identify exactly one unused lease")
    remaining_candidates = [worker_candidate_for(consumed_pool, remaining_ids[0])]
    next_wave = launch_plan(
        consumed_pool,
        remaining_candidates,
        fresh_sample,
        approval_count=1,
        previous_sample_id="resource-sample-001",
    )
    require(next_wave.get("resource_sample_id") == "resource-sample-002", "fresh re-sample was ignored")
    require(len(tuple(next_wave.get("launch_ids", ()))) == 1, "fresh wave exceeded its new approval")

    above_sixteen = launch_plan(
        pool,
        candidates[:1],
        {
            **fresh_sample,
            "sample_id": "resource-sample-003",
            "sampled_at": "2026-07-15T00:10:00Z",
            "decision_at": "2026-07-15T00:10:30Z",
            "now": "2026-07-15T00:10:30Z",
            "host_capacity": 24,
            "active_agents": 17,
        },
        approval_count=1,
        previous_sample_id=None,
    )
    require(
        len(tuple(above_sixteen.get("launch_ids", ()))) == 1,
        "agent count above sixteen was treated as a Lane-J static rejection",
    )


def check_active_lease_protection_and_return() -> None:
    pool = hierarchical_pool()
    worker = lease(pool, "gongbu#worker-1")
    worker_lease_id = str(worker.get("lease_id"))
    worker_share = float(worker.get("envelope_share", -1.0))
    parent_available_before = float(lease(pool, "gongbu").get("available_share", -1.0))
    require(worker_share > 0.0 and parent_available_before >= 0.0, "lease accounting fields are invalid")

    require_rejected(
        lambda: release(
            deepcopy(pool),
            lease_id=worker_lease_id,
            reason="REBALANCE",
            evidence=None,
            active_useful=True,
        ),
        "active_useful_lease_protected",
    )
    require_rejected(
        lambda: release(
            deepcopy(pool),
            lease_id=worker_lease_id,
            reason="SAFETY_EXCEPTION",
            evidence=None,
            active_useful=True,
        ),
        "exception_evidence_required",
    )
    require_rejected(
        lambda: release(
            deepcopy(pool),
            lease_id=worker_lease_id,
            reason="CANCELLED",
            evidence=None,
            active_useful=True,
        ),
        "exception_evidence_required",
    )

    for reason, evidence in (
        ("SAFETY_EXCEPTION", "ram_percent=99.0"),
        ("CANCELLED", "user cancellation event court-msg-42"),
    ):
        exceptional = release(
            deepcopy(pool),
            lease_id=worker_lease_id,
            reason=reason,
            evidence=evidence,
            active_useful=True,
        )
        require(isinstance(exceptional, Mapping), f"{reason} did not return a pool mapping")
        exceptional_lease = lease(exceptional, "gongbu#worker-1")
        require(exceptional_lease.get("status") == "RELEASED", f"{reason} did not release the lease")
        require(exceptional_lease.get("release_reason") == reason, f"{reason} release reason was not preserved")
        require(exceptional_lease.get("release_evidence") == evidence, f"{reason} evidence was not preserved")

    completed = release(
        deepcopy(pool),
        lease_id=worker_lease_id,
        reason="COMPLETED",
        evidence="task completion recorded",
        active_useful=False,
    )
    require(isinstance(completed, Mapping), "lease completion did not return a pool mapping")
    require(lease(completed, "gongbu#worker-1").get("status") == "RELEASED", "completed lease stayed active")
    parent_available_after = float(lease(completed, "gongbu").get("available_share", -1.0))
    require(
        parent_available_after == parent_available_before + worker_share,
        "completed child lease did not return its share to the parent envelope",
    )


def check_wave_and_resource_reassessment() -> None:
    pool = hierarchical_pool()
    worker_lease_id = str(lease(pool, "gongbu#worker-1").get("lease_id"))
    generation = int(pool.get("reassessment_generation", 0))
    wave = reassess_budget_pool(
        deepcopy(pool),
        trigger="NEW_WAVE",
        resource_state=SAFE_RESOURCE_STATE,
        active_useful_lease_ids=(worker_lease_id,),
        cancelled_lease_ids=(),
        exception_evidence={},
    )
    require(isinstance(wave, Mapping), "new-wave reassessment must return a pool mapping")
    require(wave.get("last_reassessment_trigger") == "NEW_WAVE", "new wave did not trigger reassessment")
    require(int(wave.get("reassessment_generation", -1)) == generation + 1, "new-wave generation did not advance")
    require(lease(wave, "gongbu#worker-1").get("status") == "ACTIVE", "useful active lease was revoked")

    changed = reassess_budget_pool(
        deepcopy(wave),
        trigger="RESOURCE_CHANGE",
        resource_state={
            **SAFE_RESOURCE_STATE,
            "sample_id": "resource-sample-002",
            "sampled_at": "2026-07-15T00:05:00Z",
            "decision_at": "2026-07-15T00:05:30Z",
            "now": "2026-07-15T00:05:30Z",
            "active_agents": 2,
        },
        active_useful_lease_ids=(worker_lease_id,),
        cancelled_lease_ids=(),
        exception_evidence={},
    )
    require(isinstance(changed, Mapping), "resource-change reassessment must return a pool mapping")
    require(
        changed.get("last_reassessment_trigger") == "RESOURCE_CHANGE",
        "resource change did not trigger reassessment",
    )
    require(
        int(changed.get("reassessment_generation", -1)) == generation + 2,
        "resource-change generation did not advance",
    )
    require(lease(changed, "gongbu#worker-1").get("status") == "ACTIVE", "safe resource change revoked useful work")


def check_launch_consumes_sample_and_child_lease() -> None:
    pool = hierarchical_pool()
    candidate = worker_candidate(pool)
    first = launch_plan(pool, [candidate], SAFE_RESOURCE_STATE, approval_count=1)
    case_require(
        "J-LAUNCH-CONSUME-001",
        tuple(first.get("launch_ids", ())) == ("gongbu#worker-1",),
        "approved child was not launched",
    )
    consumed = first.get("budget_pool")
    case_require(
        "J-LAUNCH-CONSUME-002",
        isinstance(consumed, Mapping),
        "launch did not return a consumed budget pool",
    )
    consumed_pool = consumed  # type: ignore[assignment]
    consumed_worker = lease(consumed_pool, "gongbu#worker-1")
    case_require(
        "J-LAUNCH-CONSUME-003",
        consumed_worker.get("launch_state") == "CONSUMED"
        and consumed_worker.get("launch_sample_id") == "resource-sample-001",
        "launch did not consume the child lease and bind the resource sample",
    )
    case_require(
        "J-LAUNCH-CONSUME-004",
        isinstance(consumed_worker.get("launch_usage"), Mapping)
        and len(tuple(consumed_worker.get("launch_history", ()))) == 1,
        "launch consumption evidence is incomplete",
    )
    last_sample = consumed_pool.get("last_resource_sample")
    case_require(
        "J-LAUNCH-CONSUME-005",
        isinstance(last_sample, Mapping) and last_sample.get("sample_id") == "resource-sample-001",
        "resource sample was not consumed into the pool",
    )

    case_rejected(
        "J-LAUNCH-REUSE-SAMPLE-001",
        lambda: call_plan(
            consumed_pool,
            candidates=[worker_candidate(consumed_pool)],
            resource_state=SAFE_RESOURCE_STATE,
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id="resource-sample-001",
        ),
        "resource_resample_required",
    )
    fresh = {
        **SAFE_RESOURCE_STATE,
        "sample_id": "resource-sample-002",
        "sampled_at": "2026-07-15T00:05:00Z",
        "decision_at": "2026-07-15T00:05:30Z",
        "now": "2026-07-15T00:05:30Z",
    }
    case_rejected(
        "J-LAUNCH-REUSE-LEASE-001",
        lambda: call_plan(
            consumed_pool,
            candidates=[worker_candidate(consumed_pool)],
            resource_state=fresh,
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id="resource-sample-001",
        ),
        "child_lease_already_consumed",
    )

    root_candidate = {
        "child_id": "taizi",
        "lease_id": lease(pool, "taizi").get("lease_id"),
    }
    case_rejected(
        "J-LAUNCH-ROOT-001",
        lambda: call_plan(
            pool,
            candidates=[root_candidate],
            resource_state=SAFE_RESOURCE_STATE,
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        ),
        "root_or_taizi_candidate_forbidden",
    )


def check_pool_structure_rejects_semantic_forgeries() -> None:
    pool = hierarchical_pool()

    def probe(forged: Mapping[str, object]) -> Mapping[str, object]:
        return call_plan(
            forged,
            candidates=[worker_candidate(forged)],
            resource_state=SAFE_RESOURCE_STATE,
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        )

    for case_id, field, forged_value in (
        ("J-POOL-AUTHORITY-001", "approved_by", "taizi"),
        ("J-POOL-LEVEL-001", "level", "ministry"),
        ("J-POOL-SUPERIOR-001", "direct_superior", "shangshu"),
        ("J-POOL-BOOL-001", "integration_authority", 1),
    ):
        forged = deepcopy(pool)
        forged["leases"]["gongbu#worker-1"][field] = forged_value  # type: ignore[index]
        case_rejected(
            case_id,
            lambda forged=forged: probe(forged),
            "budget_pool_invariant_violation",
        )

    forged_generation = deepcopy(pool)
    forged_generation["reassessment_generation"] = True
    case_rejected(
        "J-POOL-GENERATION-001",
        lambda: probe(forged_generation),
        "budget_pool_invariant_violation",
    )

    completed = release(
        deepcopy(pool),
        lease_id=str(lease(pool, "gongbu#worker-1").get("lease_id")),
        reason="COMPLETED",
        evidence="history binding evidence",
        active_useful=False,
    )
    forged_history = deepcopy(completed)
    history = list(lease(forged_history, "gongbu#worker-1").get("release_history", ()))
    history[0] = {**history[0], "released_by": "taizi"}
    forged_history["leases"]["gongbu#worker-1"]["release_history"] = tuple(history)  # type: ignore[index]
    case_rejected(
        "J-POOL-HISTORY-001",
        lambda: add_worker(
            forged_history,
            "gongbu#history-probe",
            shard_id="history-probe",
            write_set=("synthetic/history-probe",),
            share=1.0,
        ),
        "budget_pool_invariant_violation",
    )


def check_release_time_authority_and_bulk_order() -> None:
    pool = hierarchical_pool()
    worker_id = "gongbu#worker-1"
    worker_lease_id = str(lease(pool, worker_id).get("lease_id"))
    case_rejected(
        "J-RELEASE-TIME-001",
        lambda: release(
            deepcopy(pool),
            lease_id=worker_lease_id,
            reason="COMPLETED",
            evidence="release cannot predate approval",
            active_useful=False,
            released_at="2026-07-14T23:59:59Z",
        ),
        "release_before_approval",
    )
    taizi_release = case_accepts(
        "J-RELEASE-TAIZI-001",
        lambda: release(
            deepcopy(pool),
            lease_id=worker_lease_id,
            reason="COMPLETED",
            evidence="Taizi terminal release evidence",
            active_useful=False,
            released_by="taizi",
        ),
    )
    case_require(
        "J-RELEASE-TAIZI-002",
        isinstance(taizi_release, Mapping)
        and lease(taizi_release, worker_id).get("released_by") == "taizi",
        "Taizi release authority was not preserved",
    )

    ministry_lease_id = str(lease(pool, "gongbu").get("lease_id"))
    evidence = {
        ministry_lease_id: "bulk cancellation ministry evidence",
        worker_lease_id: "bulk cancellation worker evidence",
    }
    results = []
    for order in (
        (ministry_lease_id, worker_lease_id),
        (worker_lease_id, ministry_lease_id),
    ):
        results.append(
            reassess_budget_pool(
                deepcopy(pool),
                trigger="NEW_WAVE",
                resource_state=SAFE_RESOURCE_STATE,
                active_useful_lease_ids=(),
                cancelled_lease_ids=order,
                exception_evidence=evidence,
            )
        )
    for result in results:
        case_require(
            "J-RELEASE-BULK-001",
            lease(result, worker_id).get("status") == "RELEASED"
            and lease(result, "gongbu").get("status") == "RELEASED",
            "bulk release did not release descendants before ancestors",
        )
    case_require(
        "J-RELEASE-BULK-002",
        results[0] == results[1],
        "bulk release result depends on caller order",
    )


def check_windows_write_set_rejects_unsafe_forms() -> None:
    pool = hierarchical_pool()
    cases = (
        ("J-WRITESET-DOT-001", ".", "write_set_current_directory_forbidden"),
        ("J-WRITESET-DOT-002", ".\\", "write_set_current_directory_forbidden"),
        ("J-WRITESET-TYPE-001", None, "write_set_path_must_be_string"),
        ("J-WRITESET-TYPE-002", 7, "write_set_path_must_be_string"),
        ("J-WRITESET-ADS-001", r"C:\Repo\file.txt:stream", "write_set_ads_forbidden"),
        ("J-WRITESET-ADS-002", "synthetic/file.txt:stream", "write_set_ads_forbidden"),
    )
    for case_id, path, expected in cases:
        case_rejected(
            case_id,
            lambda path=path: add_worker(
                pool,
                f"gongbu#{case_id}",
                shard_id=case_id,
                write_set=(path,),  # type: ignore[arg-type]
                share=1.0,
            ),
            expected,
        )


def check_strict_booleans_and_hard_limit_domains() -> None:
    decision_values: dict[str, object] = {
        "user_instruction": None,
        "necessary_complexity": False,
        "simpler_equivalent_available": True,
        "low_marginal_value": False,
        "budget_sufficient": True,
        "risk_acceptable": True,
        "rollback_ready": True,
    }
    for field in (
        "necessary_complexity",
        "simpler_equivalent_available",
        "low_marginal_value",
        "budget_sufficient",
        "risk_acceptable",
        "rollback_ready",
    ):
        forged = {**decision_values, field: 1}
        case_rejected(
            f"J-BOOL-DECISION-{field}",
            lambda forged=forged: evaluate_complexity_budget(**forged),  # type: ignore[arg-type]
            "strict_bool_required",
        )
    case_rejected(
        "J-BOOL-DEGRADE-001",
        lambda: should_degrade_complexity(
            remaining_super_giant=1,  # type: ignore[arg-type]
            system_memory_percent=40.0,
        ),
        "strict_bool_required",
    )

    pool = hierarchical_pool()
    case_rejected(
        "J-BOOL-LEASE-001",
        lambda: add_worker(
            pool,
            "gongbu#bool-integration",
            shard_id="bool-integration",
            write_set=("synthetic/bool-integration",),
            share=1.0,
            integration_authority=1,  # type: ignore[arg-type]
        ),
        "strict_bool_required",
    )
    case_rejected(
        "J-BOOL-RELEASE-001",
        lambda: release(
            deepcopy(pool),
            lease_id=str(lease(pool, "gongbu#worker-1").get("lease_id")),
            reason="COMPLETED",
            evidence="strict bool release",
            active_useful=0,  # type: ignore[arg-type]
        ),
        "strict_bool_required",
    )

    def normalize_with_limits(limits: Mapping[str, object]) -> Mapping[str, object]:
        return normalize_budget_pool(
            total_share=100.0,
            root_id="taizi",
            reserve_share=10.0,
            hard_limits=limits,
            task_id="CCR-R2-SHIR-20260714-A02",
            phase="PHASE1",
            wave_id="A02-LANE-J-W1",
            approved_by="taizi",
            approved_at="2026-07-15T00:00:00Z",
            expected_output="bounded court execution",
            return_conditions=("DECREE_COMPLETE", "CANCELLED"),
        )

    case_rejected(
        "J-HARD-CAP-NEGATIVE-001",
        lambda: normalize_with_limits({**HARD_LIMITS, "memory_mb_max": -1}),
        "hard_limit_negative",
    )
    case_rejected(
        "J-HARD-CAP-RAM-001",
        lambda: normalize_with_limits({**HARD_LIMITS, "ram_percent_max": 100.1}),
        "hard_limit_ram_percent_invalid",
    )
    case_rejected(
        "J-RESOURCE-RAM-001",
        lambda: call_plan(
            pool,
            candidates=[worker_candidate(pool)],
            resource_state={**SAFE_RESOURCE_STATE, "ram_percent": 100.1},
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        ),
        "resource_sample_ram_percent_invalid",
    )
    case_rejected(
        "J-HARD-CAP-WEAKEN-001",
        lambda: add_worker(
            pool,
            "gongbu#weakened-cap",
            shard_id="weakened-cap",
            write_set=("synthetic/weakened-cap",),
            share=1.0,
            hard_caps={**HARD_LIMITS, "ram_percent_max": 100.0},
        ),
        "hard_caps_mismatch",
    )


def check_exact_taizi_approval_bindings() -> None:
    pool = composite_candidate_pool()
    candidates = composite_candidates(pool)[:3]
    approved_child = "gongbu#worker-3"
    exact = call_plan(
        pool,
        candidates=candidates,
        resource_state=SAFE_RESOURCE_STATE,
        requested_count=3,
        taizi_approved_count=1,
        previous_sample_id=None,
        taizi_approved_bindings=(approval_binding(pool, approved_child),),
    )
    case_require(
        "J-APPROVAL-BINDING-001",
        tuple(exact.get("launch_ids", ())) == (approved_child,),
        "planner replaced the approved instance with an internally preferred candidate",
    )
    deferred = exact.get("deferred")
    case_require(
        "J-APPROVAL-BINDING-002",
        isinstance(deferred, Mapping)
        and deferred.get("gongbu#worker-1") == "not_approved_this_wave"
        and deferred.get("gongbu#worker-2") == "not_approved_this_wave",
        "unapproved identities were not kept out of the launch set",
    )

    for case_id, field, value in (
        ("J-APPROVAL-ROLE-001", "role_key", "xingbu"),
        ("J-APPROVAL-INSTANCE-001", "instance_key", "gongbu#other"),
        ("J-APPROVAL-WRITESET-001", "write_set", ("synthetic/other",)),
        ("J-APPROVAL-AUTHORITY-001", "approved_by", "gongbu"),
    ):
        forged = {**approval_binding(pool, approved_child), field: value}
        case_rejected(
            case_id,
            lambda forged=forged: call_plan(
                pool,
                candidates=candidates,
                resource_state=SAFE_RESOURCE_STATE,
                requested_count=3,
                taizi_approved_count=1,
                previous_sample_id=None,
                taizi_approved_bindings=(forged,),
            ),
            "approved_binding_mismatch",
        )

    case_rejected(
        "J-APPROVAL-COUNT-001",
        lambda: call_plan(
            pool,
            candidates=candidates,
            resource_state=SAFE_RESOURCE_STATE,
            requested_count=3,
            taizi_approved_count=1,
            previous_sample_id=None,
            taizi_approved_bindings=(
                approval_binding(pool, "gongbu#worker-2"),
                approval_binding(pool, approved_child),
            ),
        ),
        "approved_binding_count_mismatch",
    )
    case_rejected(
        "J-APPROVAL-NOT-REQUESTED-001",
        lambda: call_plan(
            pool,
            candidates=candidates,
            resource_state=SAFE_RESOURCE_STATE,
            requested_count=3,
            taizi_approved_count=1,
            previous_sample_id=None,
            taizi_approved_bindings=(approval_binding(pool, "gongbu#worker-4"),),
        ),
        "approved_binding_not_requested",
    )


def check_extended_resource_contract_and_mandatory_caps() -> None:
    pool = hierarchical_pool()
    candidate = worker_candidate(pool)
    for field in ("retained_agents", "reclamation_verified", "message_chars", "time_seconds"):
        incomplete = dict(SAFE_RESOURCE_STATE)
        incomplete.pop(field)
        case_rejected(
            f"J-R2-RESOURCE-MISSING-{field}",
            lambda incomplete=incomplete: call_plan(
                pool,
                candidates=[candidate],
                resource_state=incomplete,
                requested_count=1,
                taizi_approved_count=1,
                previous_sample_id=None,
            ),
            "resource_sample_incomplete",
        )

    invalid_resources = (
        ("J-R2-RESOURCE-RETAINED-TYPE", {**SAFE_RESOURCE_STATE, "retained_agents": 1.5}, "resource_sample_count_not_integer"),
        ("J-R2-RESOURCE-RECLAMATION-BOOL", {**SAFE_RESOURCE_STATE, "reclamation_verified": 1}, "strict_bool_required"),
        ("J-R2-RESOURCE-MESSAGE-TYPE", {**SAFE_RESOURCE_STATE, "message_chars": 1.5}, "resource_sample_count_not_integer"),
        ("J-R2-RESOURCE-TIME-NEGATIVE", {**SAFE_RESOURCE_STATE, "time_seconds": -1.0}, "resource_sample_negative"),
    )
    for case_id, resource_state, expected in invalid_resources:
        case_rejected(
            case_id,
            lambda resource_state=resource_state: call_plan(
                pool,
                candidates=[candidate],
                resource_state=resource_state,
                requested_count=1,
                taizi_approved_count=1,
                previous_sample_id=None,
            ),
            expected,
        )

    def normalize_with_limits(limits: Mapping[str, object]) -> Mapping[str, object]:
        return normalize_budget_pool(
            total_share=100.0,
            root_id="taizi",
            reserve_share=10.0,
            hard_limits=limits,
            task_id="CCR-R2-SHIR-20260714-A02",
            phase="PHASE1",
            wave_id="A02-LANE-J-W1",
            approved_by="taizi",
            approved_at="2026-07-15T00:00:00Z",
            expected_output="bounded court execution",
            return_conditions=("DECREE_COMPLETE", "CANCELLED"),
        )

    for field in (
        "ram_percent_max",
        "memory_mb_max",
        "context_tokens_max",
        "message_chars_max",
        "tool_calls_max",
        "time_seconds_max",
        "retained_agents_max",
    ):
        missing = dict(HARD_LIMITS)
        missing.pop(field)
        case_rejected(
            f"J-R2-HARD-CAP-MISSING-{field}",
            lambda missing=missing: normalize_with_limits(missing),
            "hard_limits_missing_mandatory_cap",
        )
    case_rejected(
        "J-R2-HARD-CAP-COUNT-TYPE",
        lambda: normalize_with_limits({**HARD_LIMITS, "message_chars_max": 1.5}),
        "hard_limit_count_not_integer",
    )

    admission_cases = (
        ("messages", {**SAFE_RESOURCE_STATE, "message_chars": 12_001}),
        ("time", {**SAFE_RESOURCE_STATE, "time_seconds": 600.1}),
        ("retained", {**SAFE_RESOURCE_STATE, "retained_agents": 16}),
        (
            "host_capacity",
            {
                **SAFE_RESOURCE_STATE,
                "host_capacity": 4,
                "active_agents": 2,
                "retained_agents": 2,
                "reclamation_verified": False,
            },
        ),
    )
    for reason, resource_state in admission_cases:
        result = call_plan(
            pool,
            candidates=[candidate],
            resource_state=resource_state,
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        )
        case_require(
            f"J-R2-RESOURCE-ADMISSION-{reason}",
            result.get("deferred", {}).get("gongbu#worker-1") == f"hard_limit:{reason}",  # type: ignore[union-attr]
            f"{reason} hard limit was not enforced",
        )


def check_shangshu_integration_authority_binding() -> None:
    pool = hierarchical_pool()
    binding = pool.get("integration_authority_binding")
    case_require(
        "J-R2-INTEGRATOR-BINDING-001",
        isinstance(binding, Mapping),
        "pool omitted the unique Shangshu integration-authority binding",
    )
    shangshu = lease(pool, "shangshu")
    expected = {
        "child_id": "shangshu",
        "lease_id": shangshu.get("lease_id"),
        "role_key": "shangshu",
        "instance_key": shangshu.get("instance_key"),
        "shard_id": shangshu.get("shard_id"),
        "write_set": shangshu.get("write_set"),
        "approved_by": shangshu.get("approved_by"),
        "release_generation": shangshu.get("release_generation"),
        "release_history": shangshu.get("release_history"),
        "generation": pool.get("reassessment_generation"),
    }
    for field, value in expected.items():
        case_require(
            f"J-R2-INTEGRATOR-BINDING-{field}",
            binding.get(field) == value,  # type: ignore[union-attr]
            f"integration binding drifted from {field}",
        )

    forged_no_authority = deepcopy(pool)
    forged_no_authority["leases"]["shangshu"]["integration_authority"] = False  # type: ignore[index]
    case_rejected(
        "J-R2-INTEGRATOR-MISSING-001",
        lambda: call_plan(
            forged_no_authority,
            candidates=[worker_candidate(forged_no_authority)],
            resource_state=SAFE_RESOURCE_STATE,
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        ),
        "budget_pool_invariant_violation",
    )
    forged_transfer = deepcopy(pool)
    forged_transfer["leases"]["shangshu"]["integration_authority"] = False  # type: ignore[index]
    forged_transfer["leases"]["zhongshu"]["integration_authority"] = True  # type: ignore[index]
    case_rejected(
        "J-R2-INTEGRATOR-TRANSFER-001",
        lambda: call_plan(
            forged_transfer,
            candidates=[worker_candidate(forged_transfer)],
            resource_state=SAFE_RESOURCE_STATE,
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        ),
        "budget_pool_invariant_violation",
    )
    for field, value in (
        ("instance_key", "shangshu#forged"),
        ("shard_id", "shangshu-forged-shard"),
        ("write_set", ("synthetic/forged-shangshu",)),
    ):
        forged = deepcopy(pool)
        forged["leases"]["shangshu"][field] = value  # type: ignore[index]
        case_rejected(
            f"J-R2-INTEGRATOR-DRIFT-{field}",
            lambda forged=forged: call_plan(
                forged,
                candidates=[worker_candidate(forged)],
                resource_state=SAFE_RESOURCE_STATE,
                requested_count=1,
                taizi_approved_count=1,
                previous_sample_id=None,
            ),
            "budget_pool_invariant_violation",
        )
    for field, value in (
        ("release_history", ({"forged": True},)),
        ("generation", 1),
    ):
        forged = deepcopy(pool)
        forged["integration_authority_binding"][field] = value  # type: ignore[index]
        case_rejected(
            f"J-R2-INTEGRATOR-BINDING-DRIFT-{field}",
            lambda forged=forged: call_plan(
                forged,
                candidates=[worker_candidate(forged)],
                resource_state=SAFE_RESOURCE_STATE,
                requested_count=1,
                taizi_approved_count=1,
                previous_sample_id=None,
            ),
            "budget_pool_invariant_violation",
        )


def check_resource_sample_history_is_global_and_monotonic() -> None:
    pool = hierarchical_pool()
    candidate = worker_candidate(pool)
    first = call_plan(
        pool,
        candidates=[candidate],
        resource_state=SAFE_RESOURCE_STATE,
        requested_count=1,
        taizi_approved_count=1,
        previous_sample_id=None,
    )
    first_pool = first.get("budget_pool")
    case_require("J-R2-SAMPLE-HISTORY-001", isinstance(first_pool, Mapping), "first plan omitted pool")
    history = first_pool.get("resource_sample_history")  # type: ignore[union-attr]
    case_require(
        "J-R2-SAMPLE-HISTORY-002",
        isinstance(history, tuple)
        and tuple(item.get("sample_id") for item in history) == ("resource-sample-001",),
        "resource sample was not appended to all-history identity state",
    )

    fresh = {
        **SAFE_RESOURCE_STATE,
        "sample_id": "resource-sample-002",
        "sampled_at": "2026-07-15T00:05:00Z",
        "decision_at": "2026-07-15T00:05:30Z",
        "now": "2026-07-15T00:05:30Z",
    }
    remaining = add_worker(
        first_pool,  # type: ignore[arg-type]
        "gongbu#sample-history-worker",
        shard_id="sample-history-worker",
        write_set=("synthetic/sample-history-worker",),
        share=1.0,
    )
    second_candidate = worker_candidate_for(remaining, "gongbu#sample-history-worker")
    second = call_plan(
        remaining,
        candidates=[second_candidate],
        resource_state=fresh,
        requested_count=1,
        taizi_approved_count=1,
        previous_sample_id="resource-sample-001",
    )
    second_pool = second.get("budget_pool")
    case_require("J-R2-SAMPLE-HISTORY-003", isinstance(second_pool, Mapping), "second plan omitted pool")

    replay = {
        **SAFE_RESOURCE_STATE,
        "sample_id": "resource-sample-001",
        "sampled_at": "2026-07-15T00:10:00Z",
        "decision_at": "2026-07-15T00:10:30Z",
        "now": "2026-07-15T00:10:30Z",
    }
    case_rejected(
        "J-R2-SAMPLE-REPLAY-001",
        lambda: call_plan(
            second_pool,
            candidates=[],
            resource_state=replay,
            requested_count=0,
            taizi_approved_count=0,
            previous_sample_id="resource-sample-002",
        ),
        "resource_sample_replayed",
    )

    non_monotonic_decision = {
        **SAFE_RESOURCE_STATE,
        "sample_id": "resource-sample-decision-regression",
        "sampled_at": "2026-07-15T00:00:10Z",
        "decision_at": "2026-07-15T00:00:20Z",
        "now": "2026-07-15T00:00:40Z",
    }
    case_rejected(
        "J-R2-SAMPLE-DECISION-MONOTONIC-001",
        lambda: call_plan(
            first_pool,
            candidates=[],
            resource_state=non_monotonic_decision,
            requested_count=0,
            taizi_approved_count=0,
            previous_sample_id="resource-sample-001",
        ),
        "resource_sample_time_not_monotonic",
    )

    late_now = {**SAFE_RESOURCE_STATE, "now": "2026-07-15T00:01:00Z"}
    baseline = call_plan(
        pool,
        candidates=[],
        resource_state=late_now,
        requested_count=0,
        taizi_approved_count=0,
        previous_sample_id=None,
    ).get("budget_pool")
    regressed_now = {
        **SAFE_RESOURCE_STATE,
        "sample_id": "resource-sample-now-regression",
        "sampled_at": "2026-07-15T00:00:35Z",
        "decision_at": "2026-07-15T00:00:40Z",
        "now": "2026-07-15T00:00:50Z",
    }
    case_rejected(
        "J-R2-SAMPLE-NOW-MONOTONIC-001",
        lambda: call_plan(
            baseline,
            candidates=[],
            resource_state=regressed_now,
            requested_count=0,
            taizi_approved_count=0,
            previous_sample_id="resource-sample-001",
        ),
        "resource_sample_time_not_monotonic",
    )


def check_shared_write_set_serializes_without_identity_replacement() -> None:
    pool = add_worker(
        hierarchical_pool(),
        "gongbu#serialized-worker-2",
        shard_id="serialized-worker-2",
        write_set=("synthetic/serialized-worker-2",),
        share=2.0,
    )
    requested = []
    for child_id in ("gongbu#worker-1", "gongbu#serialized-worker-2"):
        candidate = worker_candidate_for(pool, child_id)
        candidate["prospective_write_set"] = ("synthetic/proposed-shared",)
        requested.append(candidate)
    approved_order = ("gongbu#serialized-worker-2", "gongbu#worker-1")
    result = call_plan(
        pool,
        candidates=requested,
        resource_state=SAFE_RESOURCE_STATE,
        requested_count=2,
        taizi_approved_count=2,
        previous_sample_id=None,
        taizi_approved_bindings=tuple(approval_binding(pool, child_id) for child_id in approved_order),
    )
    case_require(
        "J-R2-SERIALIZED-001",
        result.get("approval_status") == "SERIALIZED",
        "shared write set did not return exact SERIALIZED status",
    )
    case_require(
        "J-R2-SERIALIZED-002",
        tuple(result.get("launch_ids", ())) == ()
        and tuple(result.get("serial_queue", ())) == approved_order,
        "serialization sorted or replaced approved identities",
    )


def check_windows_device_aliases_are_rejected() -> None:
    pool = hierarchical_pool()
    for index, path in enumerate(
        (
            r"\\.\C:\Repo\X",
            "//./C:/Repo/X",
            r"\??\C:\Repo\X",
            r"\\??\C:\Repo\X",
            r"\Device\HarddiskVolume1\Repo\X",
            r"\GLOBAL??\C:\Repo\X",
            r"\DosDevices\C:\Repo\X",
            r"\\?\GLOBALROOT\Device\HarddiskVolume1\Repo\X",
            r"\\?\Volume{01234567-89ab-cdef-0123-456789abcdef}\Repo\X",
        ),
        start=1,
    ):
        case_rejected(
            f"J-R2-WINDOWS-DEVICE-{index:03d}",
            lambda path=path, index=index: add_worker(
                pool,
                f"gongbu#device-alias-{index}",
                shard_id=f"device-alias-{index}",
                write_set=(path,),
                share=1.0,
            ),
            "write_set_device_alias_forbidden",
        )


def check_game_design_and_development_budget_paths() -> None:
    for scale in ("small", "medium", "large"):
        for activity in ("game_design", "game_development"):
            task_kind = f"{scale}_{activity}"
            case_require(
                f"J-R2-GAME-CLASS-{task_kind}",
                is_super_giant_task(task_kind=task_kind),
                f"{task_kind} was not classified as super-giant",
            )

    for activity in ("design", "development"):
        small_pool = hierarchical_pool()
        small = call_plan(
            small_pool,
            candidates=[worker_candidate(small_pool)],
            resource_state=SAFE_RESOURCE_STATE,
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        )
        case_require(
            f"J-R2-GAME-SMALL-{activity.upper()}-APPROVED",
            small.get("approval_status") == "APPROVED",
            f"small game {activity} representative budget was not approved",
        )

        medium_pool = composite_candidate_pool()
        medium_candidates = composite_candidates(medium_pool)[:2]
        medium = call_plan(
            medium_pool,
            candidates=medium_candidates,
            resource_state=SAFE_RESOURCE_STATE,
            requested_count=2,
            taizi_approved_count=1,
            previous_sample_id=None,
            taizi_approved_bindings=(approval_binding(medium_pool, "gongbu#worker-2"),),
        )
        case_require(
            f"J-R2-GAME-MEDIUM-{activity.upper()}-DOWNSIZED",
            medium.get("approval_status") == "DOWNSIZED"
            and tuple(medium.get("launch_ids", ())) == ("gongbu#worker-2",),
            f"medium game {activity} approval did not preserve the approved identity",
        )

        large_pool = hierarchical_pool()
        large = call_plan(
            large_pool,
            candidates=[worker_candidate(large_pool)],
            resource_state={**SAFE_RESOURCE_STATE, "ram_percent": 99.0},
            requested_count=1,
            taizi_approved_count=1,
            previous_sample_id=None,
        )
        case_require(
            f"J-R2-GAME-LARGE-{activity.upper()}-DEGRADE",
            large.get("approval_status") == "DEFERRED"
            and should_degrade_complexity(remaining_super_giant=True, system_memory_percent=99.0),
            f"large game {activity} path did not degrade under the 99 percent RAM gate",
        )


def check_release_generation_binding_and_progression() -> None:
    pool = add_worker(
        hierarchical_pool(),
        "gongbu#generation-worker-2",
        shard_id="generation-worker-2",
        write_set=("synthetic/generation-worker-2",),
        share=2.0,
    )
    first_id = str(lease(pool, "gongbu#worker-1").get("lease_id"))
    second_id = str(lease(pool, "gongbu#generation-worker-2").get("lease_id"))
    first = release(
        deepcopy(pool),
        lease_id=first_id,
        reason="COMPLETED",
        evidence="generation release one",
        active_useful=False,
    )
    first_lease = lease(first, "gongbu#worker-1")
    case_require(
        "J-R2-RELEASE-GENERATION-001",
        first.get("reassessment_generation") == 1
        and first.get("last_reassessment_trigger") == "LEASE_RELEASE"
        and first_lease.get("release_generation") == 1
        and first_lease.get("release_history", ())[0].get("generation") == 1,
        "first release did not advance and bind generation 1",
    )
    second = release(
        first,
        lease_id=second_id,
        reason="COMPLETED",
        evidence="generation release two",
        active_useful=False,
    )
    second_lease = lease(second, "gongbu#generation-worker-2")
    case_require(
        "J-R2-RELEASE-GENERATION-002",
        second.get("reassessment_generation") == 2
        and second_lease.get("release_generation") == 2
        and second_lease.get("release_history", ())[0].get("generation") == 2,
        "second release did not advance and bind generation 2",
    )

    forged_old = deepcopy(second)
    history = list(lease(forged_old, "gongbu#generation-worker-2").get("release_history", ()))
    history[0] = {**history[0], "generation": 0}
    forged_old["leases"]["gongbu#generation-worker-2"]["release_history"] = tuple(history)  # type: ignore[index]
    case_rejected(
        "J-R2-RELEASE-GENERATION-OLD-001",
        lambda: add_worker(
            forged_old,
            "gongbu#generation-probe",
            shard_id="generation-probe",
            write_set=("synthetic/generation-probe",),
            share=1.0,
        ),
        "budget_pool_invariant_violation",
    )

    base = hierarchical_pool()
    worker_id = str(lease(base, "gongbu#worker-1").get("lease_id"))
    ministry_id = str(lease(base, "gongbu").get("lease_id"))
    evidence = {worker_id: "ordered child release", ministry_id: "ordered parent release"}
    bulk_results = []
    for order in ((ministry_id, worker_id), (worker_id, ministry_id)):
        bulk_results.append(
            reassess_budget_pool(
                deepcopy(base),
                trigger="NEW_WAVE",
                resource_state=SAFE_RESOURCE_STATE,
                active_useful_lease_ids=(),
                cancelled_lease_ids=order,
                exception_evidence=evidence,
            )
        )
    child_generation = lease(bulk_results[0], "gongbu#worker-1").get("release_generation")
    parent_generation = lease(bulk_results[0], "gongbu").get("release_generation")
    case_require(
        "J-R2-RELEASE-ORDER-001",
        bulk_results[0] == bulk_results[1]
        and child_generation == 1
        and parent_generation == 2,
        "bulk release order did not deterministically advance child before parent",
    )

    forged_order = deepcopy(bulk_results[0])
    child = forged_order["leases"]["gongbu#worker-1"]  # type: ignore[index]
    parent = forged_order["leases"]["gongbu"]  # type: ignore[index]
    child_history = list(child["release_history"])
    parent_history = list(parent["release_history"])
    child["release_generation"], parent["release_generation"] = 2, 1
    child_history[0] = {**child_history[0], "generation": 2}
    parent_history[0] = {**parent_history[0], "generation": 1}
    child["release_history"] = tuple(child_history)
    parent["release_history"] = tuple(parent_history)
    case_rejected(
        "J-R2-RELEASE-ORDER-ATTACK-001",
        lambda: add_worker(
            forged_order,
            "gongbu#order-probe",
            shard_id="order-probe",
            write_set=("synthetic/order-probe",),
            share=1.0,
        ),
        "budget_pool_invariant_violation",
    )


def check_w3_pool_global_antiforgery() -> None:
    pool = add_worker(
        hierarchical_pool(),
        "gongbu#w3-global-worker-2",
        shard_id="w3-global-worker-2",
        write_set=("synthetic/w3-global-worker-2",),
        share=2.0,
    )
    failures: list[str] = []

    def expect_pool_rejected(case_id: str, forged: Mapping[str, object]) -> None:
        try:
            add_worker(
                forged,
                f"gongbu#{case_id.casefold()}",
                shard_id=f"{case_id.casefold()}-probe",
                write_set=(f"synthetic/{case_id.casefold()}-probe",),
                share=1.0,
            )
        except ValueError as exc:
            if exc.args != ("budget_pool_invariant_violation",):
                failures.append(f"{case_id}:wrong_rejection={exc.args!r}")
        except Exception as exc:
            failures.append(f"{case_id}:unstable={type(exc).__name__}:{exc}")
        else:
            failures.append(f"{case_id}:accepted")

    first = lease(pool, "gongbu#worker-1")
    second_id = "gongbu#w3-global-worker-2"
    for case_id, field, value in (
        ("W3-GLOBAL-INSTANCE", "instance_key", first.get("instance_key")),
        ("W3-GLOBAL-SHARD", "shard_id", first.get("shard_id")),
        ("W3-GLOBAL-WRITESET", "write_set", first.get("write_set")),
    ):
        forged = deepcopy(pool)
        forged["leases"][second_id][field] = deepcopy(value)  # type: ignore[index]
        expect_pool_rejected(case_id, forged)

    released = release(
        pool,
        lease_id=str(first.get("lease_id")),
        reason="COMPLETED",
        evidence="w3 release one",
        active_useful=False,
    )
    released = release(
        released,
        lease_id=str(lease(released, second_id).get("lease_id")),
        reason="COMPLETED",
        evidence="w3 release two",
        active_useful=False,
    )
    global_history = released.get("lease_release_history")
    if not isinstance(global_history, tuple) or len(global_history) != 2:
        failures.append("W3-GLOBAL-HISTORY:missing_pool_release_ledger")

    forged_reason = deepcopy(released)
    reason_lease = forged_reason["leases"]["gongbu#worker-1"]  # type: ignore[index]
    reason_history = list(reason_lease["release_history"])
    reason_lease["release_reason"] = "DEGRADED"
    reason_history[0] = {**reason_history[0], "reason": "DEGRADED"}
    reason_lease["release_history"] = tuple(reason_history)
    expect_pool_rejected("W3-GLOBAL-REASON", forged_reason)

    forged_history = deepcopy(released)
    history_lease = forged_history["leases"]["gongbu#worker-1"]  # type: ignore[index]
    local_history = list(history_lease["release_history"])
    history_lease["release_evidence"] = "forged local-only evidence"
    local_history[0] = {**local_history[0], "evidence": "forged local-only evidence"}
    history_lease["release_history"] = tuple(local_history)
    expect_pool_rejected("W3-GLOBAL-HISTORY", forged_history)

    forged_generation = deepcopy(released)
    first_release = forged_generation["leases"]["gongbu#worker-1"]  # type: ignore[index]
    second_release = forged_generation["leases"][second_id]  # type: ignore[index]
    first_history = list(first_release["release_history"])
    second_history = list(second_release["release_history"])
    first_release["release_generation"], second_release["release_generation"] = 2, 1
    first_history[0] = {**first_history[0], "generation": 2}
    second_history[0] = {**second_history[0], "generation": 1}
    first_release["release_history"] = tuple(first_history)
    second_release["release_history"] = tuple(second_history)
    expect_pool_rejected("W3-GLOBAL-GENERATION", forged_generation)

    require(not failures, "global pool anti-forgery gaps: " + "; ".join(failures))


def check_w3_prospective_serialization_contract() -> None:
    pool = add_worker(
        hierarchical_pool(),
        "gongbu#w3-serialized-worker-2",
        shard_id="w3-serialized-worker-2",
        write_set=("synthetic/w3-serialized-worker-2",),
        share=2.0,
    )
    approved_order = ("gongbu#w3-serialized-worker-2", "gongbu#worker-1")
    candidates = []
    for child_id in approved_order:
        candidate = worker_candidate_for(pool, child_id)
        candidate["prospective_write_set"] = ("synthetic/w3-proposed-shared",)
        candidates.append(candidate)
    before = deepcopy(pool)
    result = call_plan(
        pool,
        candidates=candidates,
        resource_state=SAFE_RESOURCE_STATE,
        requested_count=2,
        taizi_approved_count=2,
        previous_sample_id=None,
        taizi_approved_bindings=tuple(approval_binding(pool, child_id) for child_id in approved_order),
    )
    require(result.get("approval_status") == "SERIALIZED", "prospective overlap did not serialize")
    require(tuple(result.get("launch_ids", ())) == (), "serialized proposal launched a child")
    require(tuple(result.get("serial_queue", ())) == approved_order, "serialized queue replaced identities")
    require(pool == before, "public planner mutated its input pool")
    require(result.get("budget_pool") == before, "serialized plan forged or replaced the pool")

    safety_stop = call_plan(
        pool,
        candidates=candidates,
        resource_state={**SAFE_RESOURCE_STATE, "ram_percent": 99.0},
        requested_count=2,
        taizi_approved_count=2,
        previous_sample_id=None,
        taizi_approved_bindings=tuple(approval_binding(pool, child_id) for child_id in approved_order),
    )
    require(safety_stop.get("approval_status") == "DEFERRED", "serialization overrode a safety hard stop")
    require(
        set(safety_stop.get("deferred", {}).values()) == {"hard_limit:ram"},  # type: ignore[union-attr]
        "safety hard-stop evidence was replaced by serialization",
    )


def check_w3_message_and_time_are_prospective_caps() -> None:
    per_agent_message = add_worker(
        hierarchical_pool(),
        "gongbu#w3-message-overage",
        shard_id="w3-message-overage",
        write_set=("synthetic/w3-message-overage",),
        share=2.0,
        message_chars=12_001,
    )
    message_id = "gongbu#w3-message-overage"
    message_plan = launch_plan(
        per_agent_message,
        [worker_candidate_for(per_agent_message, message_id)],
        SAFE_RESOURCE_STATE,
    )
    require(
        message_plan.get("deferred", {}).get(message_id) == "hard_limit:per_agent_messages",  # type: ignore[union-attr]
        "per-agent prospective message cap was not enforced",
    )

    message_pool = hierarchical_pool()
    message_ids = ("gongbu#w3-message-a", "gongbu#w3-message-b")
    for child_id in message_ids:
        message_pool = add_worker(
            message_pool,
            child_id,
            shard_id=child_id,
            write_set=(f"synthetic/{child_id}",),
            share=2.0,
            memory_mb=100,
            context_tokens=1_000,
            message_chars=6_000,
            tool_calls=1,
            time_seconds=10.0,
        )
    cumulative_messages = launch_plan(
        message_pool,
        [worker_candidate_for(message_pool, child_id) for child_id in message_ids],
        SAFE_RESOURCE_STATE,
    )
    require(len(tuple(cumulative_messages.get("launch_ids", ()))) == 1, "prospective messages were not cumulative")
    require(
        "composite_budget_exhausted:messages" in cumulative_messages.get("deferred", {}).values(),  # type: ignore[union-attr]
        "cumulative prospective message exhaustion was not recorded",
    )

    time_pool = hierarchical_pool()
    time_ids = ("gongbu#w3-time-a", "gongbu#w3-time-b")
    for child_id in time_ids:
        time_pool = add_worker(
            time_pool,
            child_id,
            shard_id=child_id,
            write_set=(f"synthetic/{child_id}",),
            share=2.0,
            memory_mb=100,
            context_tokens=1_000,
            message_chars=100,
            tool_calls=1,
            time_seconds=300.0,
        )
    cumulative_time = launch_plan(
        time_pool,
        [worker_candidate_for(time_pool, child_id) for child_id in time_ids],
        SAFE_RESOURCE_STATE,
    )
    require(len(tuple(cumulative_time.get("launch_ids", ()))) == 1, "prospective time was not cumulative")
    require(
        "composite_budget_exhausted:time" in cumulative_time.get("deferred", {}).values(),  # type: ignore[union-attr]
        "cumulative prospective time exhaustion was not recorded",
    )


def check_w3_canonical_shangshu_and_deputy_gate() -> None:
    default_pool = hierarchical_pool()
    case_rejected(
        "W3-SHANGSHU-DEPUTY-GATE",
        lambda: allocate(
            default_pool,
            parent_id="taizi",
            allocator_id="taizi",
            child_id="shangshu#deputy-1",
            child_level="department",
            share=1.0,
            role_key="shangshu",
            instance_key="shangshu#deputy-1",
            shard_id="portfolio-1",
            write_set=("synthetic/w3-shangshu-deputy-1",),
            integration_authority=False,
        ),
        "shangshu_deputy_requires_super_giant",
    )

    super_pool = hierarchical_pool(super_giant_task_gate=True)
    deputy_pool = case_accepts(
        "W3-SHANGSHU-DEPUTY-ALLOW",
        lambda: allocate(
            super_pool,
            parent_id="taizi",
            allocator_id="taizi",
            child_id="shangshu#deputy-1",
            child_level="department",
            share=1.0,
            role_key="shangshu",
            instance_key="shangshu#deputy-1",
            shard_id="portfolio-1",
            write_set=("synthetic/w3-shangshu-deputy-1",),
            integration_authority=False,
        ),
    )
    require(isinstance(deputy_pool, Mapping), "super-giant Shangshu deputy was not admitted")
    case_rejected(
        "W3-SHANGSHU-DEPUTY-INTEGRATOR",
        lambda: allocate(
            super_pool,
            parent_id="taizi",
            allocator_id="taizi",
            child_id="shangshu#deputy-integrator",
            child_level="department",
            share=1.0,
            role_key="shangshu",
            instance_key="shangshu#deputy-integrator",
            shard_id="portfolio-integrator",
            write_set=("synthetic/w3-shangshu-deputy-integrator",),
            integration_authority=True,
        ),
        "shangshu_deputy_not_global_integrator",
    )

    forged_transfer = deepcopy(deputy_pool)
    canonical = forged_transfer["leases"]["shangshu"]  # type: ignore[index]
    deputy = forged_transfer["leases"]["shangshu#deputy-1"]  # type: ignore[index]
    canonical["integration_authority"] = False
    deputy["integration_authority"] = True
    forged_transfer["integration_authority_binding"] = {
        "child_id": "shangshu#deputy-1",
        "lease_id": deputy.get("lease_id"),
        "role_key": deputy.get("role_key"),
        "instance_key": deputy.get("instance_key"),
        "shard_id": deputy.get("shard_id"),
        "write_set": deepcopy(deputy.get("write_set")),
        "approved_by": deputy.get("approved_by"),
        "release_generation": deputy.get("release_generation"),
        "release_history": deepcopy(deputy.get("release_history")),
        "generation": forged_transfer.get("reassessment_generation"),
    }
    case_rejected(
        "W3-SHANGSHU-CANONICAL-INTEGRATOR",
        lambda: add_worker(
            forged_transfer,
            "gongbu#w3-integrator-probe",
            shard_id="w3-integrator-probe",
            write_set=("synthetic/w3-integrator-probe",),
            share=1.0,
        ),
        "budget_pool_invariant_violation",
    )


def check_w3_windows_dos_reserved_names() -> None:
    for index, path in enumerate(
        (
            r"C:\repo\CON",
            r"C:\repo\prn.txt",
            r"synthetic\AUX ",
            r"synthetic\NUL.log",
            r"synthetic\COM1.json",
            r"synthetic\lpt9",
            r"\\?\C:\repo\con.txt",
        ),
        start=1,
    ):
        case_rejected(
            f"W3-DOS-RESERVED-{index:03d}",
            lambda path=path, index=index: add_worker(
                hierarchical_pool(),
                f"gongbu#w3-dos-{index}",
                shard_id=f"w3-dos-{index}",
                write_set=(path,),
                share=1.0,
            ),
            "write_set_dos_reserved_name",
        )

    accepted = hierarchical_pool()
    for index, path in enumerate((r"synthetic\COM10", r"synthetic\LPT0", r"synthetic\console.txt"), start=1):
        accepted = case_accepts(
            f"W3-DOS-LEGAL-{index:03d}",
            lambda accepted=accepted, path=path, index=index: add_worker(
                accepted,
                f"gongbu#w3-dos-legal-{index}",
                shard_id=f"w3-dos-legal-{index}",
                write_set=(path,),
                share=1.0,
            ),
        )
        require(isinstance(accepted, Mapping), "legal DOS-like path was not admitted")


def check_w3_repair_contracts() -> None:
    failures: list[str] = []
    for label, check in (
        ("A_GLOBAL_POOL_ANTIFORGERY", check_w3_pool_global_antiforgery),
        ("B_PROSPECTIVE_SERIALIZATION", check_w3_prospective_serialization_contract),
        ("C_PROSPECTIVE_MESSAGE_TIME", check_w3_message_and_time_are_prospective_caps),
        ("D_CANONICAL_SHANGSHU", check_w3_canonical_shangshu_and_deputy_gate),
        ("E_DOS_RESERVED_NAMES", check_w3_windows_dos_reserved_names),
    ):
        try:
            check()
        except Exception as exc:
            failures.append(f"{label}={type(exc).__name__}:{exc}")
    require(not failures, "W3_REPAIR_RED | " + " | ".join(failures))


def check_parallel_limit_override_contract() -> None:
    resolver = getattr(complexity_budget_module, "resolve_parallel_limit", None)
    require(callable(resolver), "parallel_limit_override_contract_missing")

    default = resolver(
        configured_limit=48,
        explicit_count=None,
        unlock=False,
        control_source=None,
        system_memory_percent=40.0,
    )
    require(default["effective_limit"] == 16, "default parallel limit exceeded 16")
    require(default["authorization"] == "DEFAULT_NORMAL_16", "default authorization drifted")

    explicit = resolver(
        configured_limit=48,
        explicit_count=17,
        unlock=False,
        control_source="latest_user_explicit",
        system_memory_percent=40.0,
    )
    require(explicit["effective_limit"] == 17, "explicit count above 16 was clamped")
    require(explicit["authorization"] == "EXPLICIT_COUNT", "explicit count source was lost")

    unlocked = resolver(
        configured_limit=48,
        explicit_count=None,
        unlock=True,
        control_source="latest_user_explicit",
        system_memory_percent=40.0,
    )
    require(unlocked["effective_limit"] == 48, "explicit unlock did not expose configured capacity")
    require(unlocked["authorization"] == "EXPLICIT_UNLOCK", "unlock source was lost")

    pressure = resolver(
        configured_limit=48,
        explicit_count=None,
        unlock=True,
        control_source="latest_user_explicit",
        system_memory_percent=99.0,
    )
    require(pressure["effective_limit"] == 16, "memory pressure did not downgrade unlock")
    require(pressure["degraded"] is True, "memory pressure downgrade was not explicit")

    try:
        resolver(
            configured_limit=48,
            explicit_count=17,
            unlock=False,
            control_source="prior_memory",
            system_memory_percent=40.0,
        )
    except ValueError as exc:
        require(
            str(exc) == "parallel_override_not_current_user_explicit",
            f"stale override rejected with wrong reason: {exc!s}",
        )
    else:
        raise AssertionError("stale or memory-derived parallel override was accepted")


def check_context_economy_contract() -> None:
    evaluator = getattr(complexity_budget_module, "evaluate_context_economy", None)
    require(callable(evaluator), "context_economy_contract_missing")
    pool = hierarchical_pool()
    base = {
        "pool": pool,
        "semantic_receipt_hash": "a" * 64,
        "invariant_capsule_hash": "b" * 64,
        "capsule_bytes": 2048,
        "fork_context": "minimal",
        "result_mode": "bounded_structured_receipt",
        "tool_output_mode": "aggregate",
        "override_source": None,
        "system_memory_percent": 40.0,
    }
    approved = evaluator(**base)
    require(approved["decision"] == "APPROVED", "default context economy was rejected")
    require(approved["budget_id"] == pool["budget_id"], "context economy lost budget binding")
    require(approved["semantic_receipt_hash"] == "a" * 64, "semantic receipt binding drifted")
    require(approved["invariant_capsule_hash"] == "b" * 64, "capsule hash binding drifted")

    rejected = (
        ({"semantic_receipt_hash": None}, "semantic_receipt_hash_required"),
        ({"capsule_bytes": 2049}, "context_capsule_budget_exceeded"),
        ({"fork_context": "all"}, "implicit_full_context_forbidden"),
        ({"result_mode": "free_text"}, "bounded_structured_receipt_required"),
        ({"tool_output_mode": "full"}, "aggregate_or_pointer_tool_output_required"),
    )
    for changes, reason in rejected:
        try:
            evaluator(**{**base, **changes})
        except ValueError as exc:
            require(str(exc) == reason, f"context economy rejected with wrong reason: {exc!s}")
        else:
            raise AssertionError(f"context economy accepted forbidden input: {reason}")

    override = evaluator(
        **{
            **base,
            "capsule_bytes": 4096,
            "fork_context": "all",
            "result_mode": "expanded_structured_receipt",
            "tool_output_mode": "full",
            "override_source": "taizi_explicit_budget",
        }
    )
    require(override["decision"] == "APPROVED_OVERRIDE", "Taizi override was not honored")
    pressure = evaluator(**{**base, "override_source": "latest_user_explicit", "system_memory_percent": 99.0})
    require(pressure["decision"] == "DEGRADED", "host memory pressure did not take precedence")


def main() -> int:
    check_strict_result_enum()
    check_user_explicit_instruction_precedence()
    check_taizi_budget_judgment_when_unspecified()
    check_super_giant_examples_and_boundaries()
    check_wave_reassessment_degrades()
    check_normalized_hierarchical_pool()
    check_launch_consumes_sample_and_child_lease()
    check_pool_structure_rejects_semantic_forgeries()
    check_release_time_authority_and_bulk_order()
    check_windows_write_set_rejects_unsafe_forms()
    check_strict_booleans_and_hard_limit_domains()
    check_exact_taizi_approval_bindings()
    check_extended_resource_contract_and_mandatory_caps()
    check_shangshu_integration_authority_binding()
    check_resource_sample_history_is_global_and_monotonic()
    check_shared_write_set_serializes_without_identity_replacement()
    check_windows_device_aliases_are_rejected()
    check_game_design_and_development_budget_paths()
    check_release_generation_binding_and_progression()
    check_exact_authority_role_chain()
    check_duplicate_child_id_is_rejected_before_accounting()
    check_active_descendants_block_parent_release()
    check_release_requires_terminal_reason_and_evidence()
    check_non_finite_numbers_fail_closed()
    check_resource_sample_timestamp_and_age()
    check_reassessment_requires_new_sample_identity()
    check_per_agent_hard_caps_project_to_admission()
    check_windows_write_set_aliases_conflict()
    check_released_child_history_is_immutable()
    check_public_pool_actions_reject_forged_accounting()
    check_previous_sample_is_authoritative_and_monotonic()
    check_cumulative_prospective_resources()
    check_windows_extended_aliases_conflict()
    check_numeric_domains_reject_invalid_values_stably()
    check_release_authority_and_timestamp_binding()
    check_integration_authority_is_globally_bound()
    check_absolute_sample_age_uses_now()
    check_release_reason_is_lease_bound()
    check_degradation_and_task_counts_reject_non_finite()
    check_child_scope_and_authority_binding()
    check_complete_lease_schema()
    check_read_only_lease_access_contract()
    check_lease_access_contract_rejections()
    check_budget_input_identity_contract()
    check_envelope_conservation_and_hierarchy_rejections()
    check_child_lease_and_preflight_launch_contract()
    check_hard_limits_are_independent()
    check_composite_resource_and_value_admission()
    check_small_wave_approval_and_resample()
    check_active_lease_protection_and_return()
    check_wave_and_resource_reassessment()
    check_w3_repair_contracts()
    check_parallel_limit_override_contract()
    check_context_economy_contract()
    print(
        "COURT_COMPLEXITY_BUDGET_OK "
        "results=4 user_priority=PASSED taizi_four_factors=PASSED "
        "super_giant_boundaries=PASSED degradation=PASSED "
        "hierarchical_pool=PASSED authority_chain=PASSED duplicate_child=PASSED "
        "launch_consumption=PASSED semantic_pool_invariants=PASSED bulk_release=PASSED "
        "unsafe_write_set=PASSED strict_bool=PASSED exact_approval_binding=PASSED "
        "extended_resources=PASSED shangshu_integrator_binding=PASSED sample_history=PASSED "
        "shared_write_serialization=PASSED windows_device_alias=PASSED game_budget_paths=PASSED "
        "release_generation=PASSED "
        "descendant_release=PASSED traced_release=PASSED finite_numbers=PASSED "
        "sample_freshness=PASSED per_agent_caps=PASSED windows_write_set=PASSED "
        "release_history=PASSED pool_invariants=PASSED monotonic_sample=PASSED "
        "prospective_resources=PASSED windows_extended_alias=PASSED numeric_domains=PASSED "
        "release_binding=PASSED global_integrator=PASSED absolute_age=PASSED "
        "lease_return_conditions=PASSED finite_degradation=PASSED "
        "scope_binding=PASSED lease_schema=PASSED lease_access_contract=PASSED input_contract=PASSED "
        "composite_admission=PASSED small_wave=PASSED "
        "lease_lifecycle=PASSED hard_limits=PASSED w3_repair=PASSED "
        "parallel_limit_override=PASSED context_economy=PASSED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
