"""Regression checks for court mode and dynamic office dispatch policy."""

from __future__ import annotations

import json
import sys

sys.dont_write_bytecode = True

from court_dispatch_policy import normalize_mode, select_wave, validate_dispatch_plan


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_mode_semantics() -> dict[str, object]:
    parallel = normalize_mode("super并行")
    require(parallel.authority == "super", "super并行 lost super authority")
    require(parallel.topology == "ordinary_parallel", "super并行 did not select ordinary parallel topology")
    require(parallel.runtime_family == "spawned_subagent", "super并行 selected the wrong runtime family")
    require(not parallel.supercc, "super并行 incorrectly activated superCC")

    supercc = normalize_mode("superCC")
    require(supercc.authority == "super", "superCC lost super authority")
    require(supercc.topology == "court_runtime", "superCC did not select court runtime topology")
    require(supercc.runtime_family == "visible_zellij_squad", "superCC selected the wrong runtime family")
    require(supercc.supercc, "superCC was not explicit")
    return {"super_parallel": parallel.__dict__, "supercc": supercc.__dict__}


def check_dynamic_capacity() -> dict[str, object]:
    six = select_wave(
        useful_roles=["libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"],
        host_capacity=8,
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        host_retained=0,
        next_depth=1,
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
    )
    require(current_host.selected_roles == ("zhongshu", "menxia", "shangshu"), "four-slot host selected the wrong roles")
    require(current_host.deferred_roles == ("shiguan",), "four-slot host did not defer the fourth role")
    require(current_host.reason == "runtime_capacity", "capacity deferral reported the wrong reason")
    twenty_roles = tuple(f"role-{index:02d}" for index in range(1, 21))
    root_tree_cap = select_wave(
        useful_roles=twenty_roles,
        host_capacity=64,
        host_active=1,
        user_agent_budget=None,
        provider_launch_budget=None,
        host_retained=0,
        next_depth=1,
    )
    require(len(root_tree_cap.selected_roles) == 15, "root-counted sixteen-thread tree did not cap children at fifteen")
    require(len(root_tree_cap.deferred_roles) == 5, "sixteen-thread tree did not defer five of twenty roles")
    require(root_tree_cap.effective_host_capacity == 16, "host capacity was not clamped to configured max_threads=16")

    depth_four = select_wave(
        useful_roles=("xingbu",), host_capacity=16, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, next_depth=4,
        host_retained=0,
    )
    require(depth_four.selected_roles == ("xingbu",), "next_depth=4 should be allowed")
    depth_five = select_wave(
        useful_roles=("xingbu",), host_capacity=16, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, next_depth=5,
        host_retained=0,
    )
    require(depth_five.selected_roles == (), "next_depth=5 should fail closed")
    require(depth_five.reason == "max_depth_exceeded", "depth overflow reported the wrong reason")

    unknown = select_wave(
        useful_roles=("xingbu",), host_capacity=None, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, next_depth=1,
        host_retained=0,
    )
    require(unknown.selected_roles == () and unknown.reason == "host_capacity_unknown", "unknown capacity did not fail closed")
    unknown_occupancy = select_wave(
        useful_roles=("xingbu",), host_capacity=16, host_active=None,
        user_agent_budget=None, provider_launch_budget=None, next_depth=1,
        host_retained=0,
    )
    require(unknown_occupancy.selected_roles == () and unknown_occupancy.reason == "host_occupancy_unknown", "unknown occupancy did not fail closed")
    unknown_depth = select_wave(
        useful_roles=("xingbu",), host_capacity=16, host_active=1,
        user_agent_budget=None, provider_launch_budget=None, next_depth=None,
        host_retained=0,
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
    )
    require(
        retained_reclaimed.selected_roles == ("zhongshu", "menxia", "shangshu"),
        "verified terminal-node reclamation did not restore active-only capacity",
    )
    return {
        "six_roles": six.__dict__,
        "current_host": current_host.__dict__,
        "root_tree_cap": root_tree_cap.__dict__,
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
    }


def check_dispatch_plan() -> dict[str, object]:
    plan = validate_dispatch_plan(
        [
            dispatch_item("libu", "礼部", "report wording"),
            dispatch_item("xingbu", "刑部", "risk review"),
        ],
        mode="super并行",
    )
    require(plan.roles == ("libu", "xingbu"), "dispatch plan forced unrelated ministries")
    require(plan.unjustified_roles == (), "valid duties were marked unjustified")

    invalid_cases = [
        [dispatch_item("gongbu", "工部", ""), dispatch_item("gongbu", "工部", "duplicate")],
        [{**dispatch_item("libu", "礼部", "wording"), "direct_superior": "taizi"}],
        [{**dispatch_item("xingbu", "刑部", "risk"), "evidence_contract": ""}],
        [{**dispatch_item("gongbu", "工部", "build"), "visibility": "visible_core"}],
    ]
    rejected = 0
    for case in invalid_cases:
        try:
            validate_dispatch_plan(case, mode="super并行")
        except ValueError:
            rejected += 1
        else:
            raise AssertionError("invalid dispatch plan was accepted")
    return {"roles": plan.roles, "invalid_cases_rejected": rejected}


def main() -> int:
    result = {
        "ok": True,
        "mode_semantics": check_mode_semantics(),
        "dynamic_capacity": check_dynamic_capacity(),
        "dispatch_plan": check_dispatch_plan(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
