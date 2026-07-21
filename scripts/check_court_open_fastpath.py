#!/usr/bin/env python3
"""Focused checks for the single-process court-open and Shangshu packet path."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True

import court_open_fastpath


class FakeRuntime:
    def __init__(self, task: dict[str, object]) -> None:
        self.task = task
        self.load_calls = 0
        self.admission_calls = 0

    def load_tasks(self) -> dict[str, dict[str, object]]:
        self.load_calls += 1
        return {str(self.task["task_id"]): self.task}

    @staticmethod
    def public_dispatch_context_packet(task: dict[str, object], wave_id: str) -> dict[str, object]:
        receipt = task["semantic_receipt"]
        return {
            "schema": "court.semantic.dispatch_context_packet.v1",
            "task_id": task["task_id"],
            "sub_id": wave_id,
            "semantic_epoch": receipt["semantic_epoch"],
            "semantic_receipt_sha256": receipt["receipt_sha256"],
        }

    @staticmethod
    def public_context_budget_pool(task: dict[str, object], wave_id: str) -> dict[str, object]:
        return {
            "schema": "court.budget.pool.v1",
            "budget_id": f"budget:{task['task_id']}:{wave_id}",
            "root_id": "taizi",
        }

    def validate_fast_admission(
        self,
        task: dict[str, object],
        request: dict[str, object],
    ) -> dict[str, object]:
        self.admission_calls += 1
        binding = request["requested_bindings"][0]
        return {
            "allowed": True,
            "decision": "admitted",
            "selected_protocol": "v2",
            "selected_bindings": [binding],
        }


def _task() -> dict[str, object]:
    return {
        "task_id": "fast-open-fixture",
        "semantic_epoch": 3,
        "semantic_state": "DISPATCHABLE",
        "semantic_receipt": {
            "receipt_id": "SR-FAST-OPEN",
            "receipt_sha256": "1" * 64,
            "semantic_epoch": 3,
            "charter_sha256": "2" * 64,
            "invariant_capsule_sha256": "3" * 64,
            "checkpoint_id": "SC-FAST-OPEN",
            "plan_sha256": "4" * 64,
            "plan_cursor": "PHASE5.2 -> PHASE9 -> PHASE10",
            "verdict": "DISPATCHABLE",
        },
    }


def _identity(path: Path) -> tuple[dict[str, object], list[list[str]]]:
    return (
        {
            "path": str(path.resolve()),
            "branch": "release/beta1.0.2-hotfix-v1",
            "HEAD": "5" * 40,
            "index_count": 0,
            "tracked_dirty_count": 0,
        },
        [["git", "fixture"]],
    )


def _write_skill(root: Path, *, wrong_ministry: str | None = None, oversized: bool = False) -> None:
    skill = "---\nname: decretum-matrix\n---\n# Decretum Matrix\n"
    if oversized:
        skill += "x" * court_open_fastpath.MINIMAL_PRELOAD_BYTES
    (root / "SKILL.md").write_text(skill, encoding="utf-8")
    hierarchy_path = root / "references" / "manifests" / "court-dispatch-hierarchy.v1.json"
    hierarchy_path.parent.mkdir(parents=True, exist_ok=True)
    hierarchy_path.write_text(
        json.dumps(
            {
                "schema": "court.dispatch_hierarchy.v1",
                "canonical_roles": {
                    role: {"direct_superior": superior}
                    for role, superior in court_open_fastpath.ROLE_SUPERIORS.items()
                },
                "allowed_edges": [
                    *[
                        {"action": "dispatch", "caller": "taizi", "target": role}
                        for role in court_open_fastpath.THREE_DEPARTMENTS
                    ],
                    *[
                        {"action": "dispatch", "caller": "shangshu", "target": role}
                        for role in court_open_fastpath.SIX_MINISTRIES
                    ],
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    office_zh = {
        "zhongshu": "Zhongshu",
        "menxia": "Menxia",
        "shangshu": "Shangshu",
        "libu-hr": "LibuHR",
        "hubu": "Hubu",
        "libu": "Libu",
        "bingbu": "Bingbu",
        "xingbu": "Xingbu",
        "gongbu": "Gongbu",
    }
    for role in (*court_open_fastpath.THREE_DEPARTMENTS, *court_open_fastpath.SIX_MINISTRIES):
        superior = court_open_fastpath.ROLE_SUPERIORS[role]
        if role == wrong_ministry:
            superior = "taizi"
        profile = root / "agents" / "standing-officials" / f"{role}.toml"
        dossier = root / "agents" / "office-dossiers" / role / "AGENTS.md"
        profile.parent.mkdir(parents=True, exist_ok=True)
        dossier.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text(
            "[profile]\n"
            f'role_key = "{role}"\n'
            f'office_zh = "{office_zh[role]}"\n'
            f'direct_superior = "{superior}"\n',
            encoding="utf-8",
        )
        dossier.write_text(f"# Fixture\n\n- role: {role}\n", encoding="utf-8")


def _request(root: Path, worktree: Path) -> dict[str, object]:
    return {
        "schema": court_open_fastpath.REQUEST_SCHEMA,
        "task_id": "fast-open-fixture",
        "authority": "super",
        "authority_source": "explicit_latest_user",
        "behavior": "parallel",
        "worktree": str(worktree),
        "skill_root": str(root),
        "host_capacity": 16,
        "host_active_agents": 1,
        "host_retained_agents": 0,
        "host_reclamation_status": "verified",
        "system_memory_percent": 40.0,
        "requested_offices": list(court_open_fastpath.THREE_DEPARTMENTS),
        "write_sets": {},
        "expected_branch": "release/beta1.0.2-hotfix-v1",
        "expected_head": "5" * 40,
        "expected_semantic_receipt_sha256": "1" * 64,
        "expected_plan_sha256": "4" * 64,
        "transport": "codex",
        "task_focus": "fast court open fixture",
        "expires_at_utc": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
    }


def run_checks(*, shangshu_only: bool = False, concurrent_probes: bool = True) -> dict[str, object]:
    problems: list[str] = []
    checks: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="court-open-fastpath-") as tmp_text:
        root = Path(tmp_text) / "skill"
        worktree = Path(tmp_text) / "worktree"
        root.mkdir()
        worktree.mkdir()
        _write_skill(root)
        request = _request(root, worktree)
        runtime = FakeRuntime(_task())
        first = court_open_fastpath.prepare_fast_open(
            request,
            runtime_api=runtime,
            identity_loader=_identity,
            concurrent_preload=concurrent_probes,
        )
        second = court_open_fastpath.prepare_fast_open(
            request,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=concurrent_probes,
        )
        checks["success"] = first.get("ok") is True
        checks["runtime_loaded_once"] = runtime.load_calls == 1
        checks["single_process"] = first.get("python_child_processes") == 0
        checks["no_partial_mutation"] = first.get("mutations") == []
        checks["exact_retry"] = (
            first.get("operation_id") == second.get("operation_id")
            and first.get("receipt_id") == second.get("receipt_id")
            and first.get("packet_sha256") == second.get("packet_sha256")
        )
        checks["three_departments"] = len(first.get("department_packets", [])) == 3
        checks["default_zero_ministries"] = (
            first.get("shangshu_ministry_packets") == []
            and first.get("shangshu_ministry_coordination") is None
            and first.get("planned_ministry_count") == 0
            and first.get("planned_office_count") == 3
            and first.get("admission_check_count") == 3
            and len(first.get("preloads", [])) == 3
        )
        checks["preparation_never_claims_spawn"] = (
            first.get("preparation_only") is True
            and first.get("host_spawn_performed") is False
            and first.get("dispatch_count") == 0
            and first.get("physical_child_dispatch_count") == 0
            and all(
                packet.get("physical_child_agent_spawned") is False
                and packet.get("host_spawn_status") == "NOT_PERFORMED_PREPARATION_ONLY"
                for packet in first.get("department_packets", [])
            )
        )

        one_request = {**request, "ministry_assignments": ["gongbu"]}
        one_runtime = FakeRuntime(_task())
        one = court_open_fastpath.prepare_fast_open(
            one_request,
            runtime_api=one_runtime,
            identity_loader=_identity,
            concurrent_preload=concurrent_probes,
        )
        checks["one_ministry_assignment"] = (
            [packet.get("role") for packet in one.get("shangshu_ministry_packets", [])]
            == ["gongbu"]
            and one.get("planned_ministry_count") == 1
            and one.get("planned_office_count") == 4
            and one.get("admission_check_count") == 4
            and one_runtime.admission_calls == 4
            and one.get("dispatch_count") == 0
            and one.get("physical_child_dispatch_count") == 0
        )

        two_request = {**request, "ministry_assignments": ["hubu", "gongbu"]}
        two_runtime = FakeRuntime(_task())
        two = court_open_fastpath.prepare_fast_open(
            two_request,
            runtime_api=two_runtime,
            identity_loader=_identity,
            concurrent_preload=concurrent_probes,
        )
        checks["two_ministry_assignments"] = (
            [packet.get("role") for packet in two.get("shangshu_ministry_packets", [])]
            == ["hubu", "gongbu"]
            and two.get("planned_ministry_count") == 2
            and two.get("planned_office_count") == 5
            and two.get("admission_check_count") == 5
            and two_runtime.admission_calls == 5
            and len(two.get("preloads", [])) == 5
        )
        checks["ministry_superiors"] = all(
            packet["hierarchy"]["direct_superior"] == "shangshu"
            for packet in two.get("shangshu_ministry_packets", [])
        )
        coordination = two.get("shangshu_ministry_coordination")
        checks["shangshu_coordination_present"] = (
            isinstance(coordination, dict)
            and coordination.get("schema") == "court.shangshu_ministry_coordination.v1"
            and coordination.get("coordinator") == "shangshu"
            and coordination.get("behavior") == request["behavior"]
        )
        checks["shangshu_selects_ministries"] = (
            isinstance(coordination, dict)
            and coordination.get("selected_ministries") == ["hubu", "gongbu"]
            and coordination.get("selection_policy")
            == "bounded_ministries_selected_by_shangshu_after_taizi_reply"
        )
        checks["shangshu_prepares_ministry_children_without_dispatch"] = (
            isinstance(coordination, dict)
            and coordination.get("dispatch_initiator") is None
            and coordination.get("planned_dispatch_initiator") == "shangshu"
            and coordination.get("dispatch_target_kind") == "six_ministry_child_offices"
            and coordination.get("host_dispatch_performed") is False
            and coordination.get("dispatch_status") == "PREPARED_NOT_PERFORMED"
            and coordination.get("taizi_direct_ministry_dispatch_allowed") is False
        )
        checks["shangshu_integrates_ministries"] = (
            isinstance(coordination, dict)
            and coordination.get("integration_owner") == "shangshu"
            and coordination.get("evidence_return") == "shangshu_integrates_then_reports_to_taizi"
        )
        checks["ministry_admission_caller_is_shangshu"] = all(
            packet.get("admission", {}).get("calling_office") == "shangshu"
            for packet in two.get("shangshu_ministry_packets", [])
        )
        checks["ministry_binding_superior_is_shangshu"] = all(
            packet.get("admission", {})
            .get("requested_bindings", [{}])[0]
            .get("direct_superior")
            == "shangshu"
            for packet in two.get("shangshu_ministry_packets", [])
        )
        authority_gate = first.get("authority_selection_gate")
        checks["startup_authority_binding_only"] = (
            isinstance(authority_gate, dict)
            and authority_gate.get("schema") == "court.startup.authority_selection_gate.v1"
            and authority_gate.get("authority_source") == "explicit_latest_user"
            and authority_gate.get("source_policy")
            == "latest_explicit_or_current_question_or_same_conversation_same_boundary"
            and authority_gate.get("semantic_owner") == "SKILL.md"
            and authority_gate.get("selected_authority") == "super"
            and authority_gate.get("selected_behavior") == "parallel"
            and authority_gate.get("authority_behavior_orthogonal") is True
            and "prompt" not in authority_gate
            and "must_not_inherit_from" not in authority_gate
        )
        agent_hierarchy = two.get("agent_hierarchy")
        hierarchy_nodes = agent_hierarchy.get("nodes", []) if isinstance(agent_hierarchy, dict) else []
        ministry_parent_map = {
            node.get("role"): node.get("parent_role")
            for node in hierarchy_nodes
            if isinstance(node, dict) and node.get("role") in court_open_fastpath.SIX_MINISTRIES
        }
        checks["agent_tree_ministries_under_shangshu"] = (
            isinstance(agent_hierarchy, dict)
            and agent_hierarchy.get("schema") == "court.agent_hierarchy_tree.v1"
            and agent_hierarchy.get("six_ministry_parent") == "shangshu"
            and agent_hierarchy.get("six_ministries_are_shangshu_child_agents") is True
            and ministry_parent_map
            == {"hubu": "shangshu", "gongbu": "shangshu"}
            and agent_hierarchy.get("rendering_contract")
            == "render_six_ministries_nested_under_shangshu_not_as_taizi_siblings"
        )
        reuse_policy = first.get("agent_reuse_policy")
        checks["agent_reuse_policy_present"] = (
            isinstance(reuse_policy, dict)
            and reuse_policy.get("schema") == "court.agent.reuse_policy.v1"
            and reuse_policy.get("compatible_instance_policy") == "REUSE_FIRST"
            and reuse_policy.get("context_occupancy_limit") == 0.80
            and "context_occupancy_ratio >= 0.80" in reuse_policy.get("do_not_reuse_if", [])
        )
        reuse_candidate = {
            "status": "running",
            "role": "gongbu",
            "direct_superior": "shangshu",
            "context_occupancy_ratio": 0.42,
            "task_relation": "related",
        }
        checks["agent_reuse_decision_reuses_related_live"] = (
            court_open_fastpath.evaluate_agent_reuse_candidate(
                reuse_candidate,
                {"role": "gongbu", "direct_superior": "shangshu", "next_task_relation": "related"},
            ).get("decision")
            == "REUSE"
        )
        checks["agent_reuse_decision_blocks_80_percent_context"] = (
            court_open_fastpath.evaluate_agent_reuse_candidate(
                {**reuse_candidate, "context_occupancy_ratio": 0.80},
                {"role": "gongbu", "direct_superior": "shangshu", "next_task_relation": "related"},
            ).get("reason_codes")
            == ["context_occupancy_at_or_above_80_percent"]
        )
        checks["agent_reuse_decision_blocks_unrelated_task"] = (
            court_open_fastpath.evaluate_agent_reuse_candidate(
                reuse_candidate,
                {"role": "gongbu", "direct_superior": "shangshu", "next_task_relation": "unrelated"},
            ).get("reason_codes")
            == ["next_task_unrelated"]
        )
        checks["agent_reuse_decision_allows_fresh_large_parallel"] = (
            court_open_fastpath.evaluate_agent_reuse_candidate(
                reuse_candidate,
                {
                    "role": "gongbu",
                    "direct_superior": "shangshu",
                    "next_task_relation": "related",
                    "large_scale_parallel": True,
                    "performance_allows_fresh_instance": True,
                },
            ).get("reason_codes")
            == ["large_scale_parallel_fresh_instance_preferred"]
        )
        checks["preload_target"] = all(
            preload.get("target_met") is True for preload in first.get("preloads", [])
        )
        checks["compact_metadata"] = all(
            isinstance(preload.get("metadata_bytes"), int)
            and preload["metadata_bytes"] > 0
            and preload.get("metadata", {}).get("registry_policy") == "registry-first"
            and "references/manifests/court-dispatch-hierarchy.v1.json"
            in preload.get("verified_source_paths", [])
            and preload.get("preload_evidence_kind") == "dispatcher_source_validation"
            and preload.get("child_preload_ack_status") == "NOT_AVAILABLE_PRE_SPAWN"
            for preload in first.get("preloads", [])
        )

        no_probe_request = dict(request)
        no_probe_request.pop("expected_branch")
        no_probe_request.pop("expected_head")
        original_capability_resolver = court_open_fastpath.resolve_capability_snapshot

        def forbidden_identity(_path: Path) -> tuple[dict[str, object], list[list[str]]]:
            raise AssertionError("default preparation attempted a Git probe")

        def forbidden_capability(*_args: object, **_kwargs: object) -> tuple[dict[str, object], str, float]:
            raise AssertionError("default preparation attempted a capability probe")

        court_open_fastpath.resolve_capability_snapshot = forbidden_capability
        try:
            no_probe = court_open_fastpath.prepare_fast_open(
                no_probe_request,
                runtime_api=FakeRuntime(_task()),
                identity_loader=forbidden_identity,
                concurrent_preload=False,
            )
        finally:
            court_open_fastpath.resolve_capability_snapshot = original_capability_resolver
        checks["capability_and_git_checks_are_opt_in"] = (
            no_probe.get("ok") is True
            and no_probe.get("git_check_requested") is False
            and no_probe.get("worktree", {}).get("status") == "NOT_REQUESTED"
            and no_probe.get("process_audit") == []
            and no_probe.get("capability_check_requested") is False
            and no_probe.get("capability_cache_status") == "NOT_REQUESTED"
            and no_probe.get("capability_snapshot", {}).get("status") == "NOT_REQUESTED"
        )

        capacity = dict(request)
        capacity["host_capacity"] = 2
        capacity_miss = court_open_fastpath.prepare_fast_open(
            capacity,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        checks["capacity_miss"] = capacity_miss.get("status") == "FAST_PATH_MISS:capacity_insufficient"

        overlap = dict(request)
        overlap["write_sets"] = {"zhongshu": ["shared.txt"], "menxia": ["shared.txt"]}
        overlap_miss = court_open_fastpath.prepare_fast_open(
            overlap,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        checks["overlap_miss"] = overlap_miss.get("status") == "FAST_PATH_MISS:write_set_overlap"

        stale = dict(request)
        stale["expected_semantic_receipt_sha256"] = "f" * 64
        stale_miss = court_open_fastpath.prepare_fast_open(
            stale,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        checks["semantic_miss"] = stale_miss.get("status") == "FAST_PATH_MISS:semantic_receipt_drift"

        missing_authority_source = dict(request)
        missing_authority_source.pop("authority_source")
        try:
            court_open_fastpath.prepare_fast_open(
                missing_authority_source,
                runtime_api=FakeRuntime(_task()),
                identity_loader=_identity,
                concurrent_preload=False,
            )
        except court_open_fastpath.FastPathInvalid as exc:
            checks["authority_source_required"] = str(exc) == "authority_source_required"
        else:
            checks["authority_source_required"] = False

        serial = dict(request)
        serial["behavior"] = "serial"
        serial_result = court_open_fastpath.prepare_fast_open(
            serial,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        serial_packets = (
            serial_result.get("department_packets", [])
            + serial_result.get("shangshu_ministry_packets", [])
        )
        checks["serial_preserves_office_duties_without_child_spawn"] = (
            serial_result.get("ok") is True
            and serial_result.get("dispatch_count") == 0
            and serial_result.get("physical_child_dispatch_count") == 0
            and serial_result.get("planned_office_count") == 3
            and serial_result.get("admission_check_count") == 0
            and serial_result.get("serial_office_duty_count") == 3
            and all(
                packet.get("serial_action") == "serial_inline_office_duty"
                and packet.get("office_duty_preserved") is True
                and packet.get("physical_child_agent_spawned") is False
                for packet in serial_packets
            )
        )

        wrong_root = Path(tmp_text) / "wrong-skill"
        wrong_root.mkdir()
        _write_skill(wrong_root, wrong_ministry="gongbu")
        unselected_wrong = {**request, "skill_root": str(wrong_root)}
        unselected_result = court_open_fastpath.prepare_fast_open(
            unselected_wrong,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        selected_wrong = {
            **unselected_wrong,
            "ministry_assignments": ["gongbu"],
        }
        wrong_miss = court_open_fastpath.prepare_fast_open(
            selected_wrong,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        checks["unselected_broken_profile_not_loaded"] = (
            unselected_result.get("ok") is True
            and [preload.get("role") for preload in unselected_result.get("preloads", [])]
            == list(court_open_fastpath.THREE_DEPARTMENTS)
        )
        checks["selected_broken_profile_fails_atomically"] = (
            wrong_miss.get("status") == "FAST_PATH_MISS:hierarchy_incomplete"
            and wrong_miss.get("mutations") == []
        )

        invalid_ministry = {**request, "ministry_assignments": ["not-a-ministry"]}
        duplicate_ministry = {**request, "ministry_assignments": ["gongbu", "gongbu"]}
        bounded_errors: list[str] = []
        for candidate in (invalid_ministry, duplicate_ministry):
            try:
                court_open_fastpath.normalize_request(candidate)
            except court_open_fastpath.FastPathInvalid as exc:
                bounded_errors.append(str(exc))
        checks["ministry_assignments_are_bounded"] = bounded_errors == [
            "ministry_assignment_invalid:not-a-ministry",
            "ministry_assignments_duplicate",
        ]

        large_root = Path(tmp_text) / "large-skill"
        large_root.mkdir()
        _write_skill(large_root, oversized=True)
        large = dict(request)
        large["skill_root"] = str(large_root)
        large_miss = court_open_fastpath.prepare_fast_open(
            large,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        checks["preload_budget_miss"] = large_miss.get("status") == "FAST_PATH_MISS:preload_budget_exceeded"
        source_text = Path(court_open_fastpath.__file__).read_text(encoding="utf-8")
        checks["production_capability_not_checker_import"] = (
            "check_capability_index_gate" not in source_text
        )
        checks["legacy_include_ministries_path_removed"] = (
            "include_shangshu_ministries" not in source_text
        )

    for name, passed in checks.items():
        if passed is not True:
            problems.append(name)
    fast_gate = all(
        checks.get(name) is True
        for name in (
            "success",
            "runtime_loaded_once",
            "single_process",
            "no_partial_mutation",
            "capacity_miss",
            "overlap_miss",
            "semantic_miss",
            "authority_source_required",
            "default_zero_ministries",
            "preparation_never_claims_spawn",
            "capability_and_git_checks_are_opt_in",
            "serial_preserves_office_duties_without_child_spawn",
            "preload_budget_miss",
            "compact_metadata",
            "production_capability_not_checker_import",
            "legacy_include_ministries_path_removed",
        )
    )
    shangshu_gate = all(
        checks.get(name) is True
        for name in (
            "one_ministry_assignment",
            "two_ministry_assignments",
            "ministry_superiors",
            "shangshu_coordination_present",
            "shangshu_selects_ministries",
            "shangshu_prepares_ministry_children_without_dispatch",
            "shangshu_integrates_ministries",
            "ministry_admission_caller_is_shangshu",
            "ministry_binding_superior_is_shangshu",
            "startup_authority_binding_only",
            "agent_tree_ministries_under_shangshu",
            "agent_reuse_policy_present",
            "agent_reuse_decision_reuses_related_live",
            "agent_reuse_decision_blocks_80_percent_context",
            "agent_reuse_decision_blocks_unrelated_task",
            "agent_reuse_decision_allows_fresh_large_parallel",
            "unselected_broken_profile_not_loaded",
            "selected_broken_profile_fails_atomically",
            "ministry_assignments_are_bounded",
            "exact_retry",
        )
    )
    ok = shangshu_gate if shangshu_only else fast_gate and shangshu_gate and not problems
    return {
        "schema": "court.open.fast.check.v1",
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "FAST_OPEN_SINGLE_PROCESS": "PASS" if fast_gate else "FAIL",
        "SHANGSHU_FIRST_DISPATCH": "PASS" if shangshu_gate else "FAIL",
        "SIX_MINISTRY_DIRECT_SUPERIOR": "PASS" if checks.get("ministry_superiors") is True else "FAIL",
        "checks": checks,
        "problems": problems,
        "pending_body_access": "NO",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shangshu", action="store_true")
    parser.add_argument("--serial-probes", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = run_checks(
        shangshu_only=args.shangshu,
        concurrent_probes=not args.serial_probes,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        for gate in (
            "FAST_OPEN_SINGLE_PROCESS",
            "SHANGSHU_FIRST_DISPATCH",
            "SIX_MINISTRY_DIRECT_SUPERIOR",
        ):
            print(f"{gate}={result[gate]}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
