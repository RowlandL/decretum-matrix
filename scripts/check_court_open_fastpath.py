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

    @staticmethod
    def validate_fast_admission(task: dict[str, object], request: dict[str, object]) -> dict[str, object]:
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
            "branch": "release/beta1.0.0",
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
        "worktree": str(worktree),
        "skill_root": str(root),
        "host_capacity": 16,
        "host_active_agents": 1,
        "host_retained_agents": 0,
        "host_reclamation_status": "verified",
        "system_memory_percent": 40.0,
        "requested_offices": list(court_open_fastpath.THREE_DEPARTMENTS),
        "include_shangshu_ministries": True,
        "write_sets": {},
        "expected_branch": "release/beta1.0.0",
        "expected_head": "5" * 40,
        "expected_semantic_receipt_sha256": "1" * 64,
        "expected_plan_sha256": "4" * 64,
        "transport": "codex",
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
        checks["six_ministries"] = len(first.get("shangshu_ministry_packets", [])) == 6
        checks["ministry_superiors"] = all(
            packet["hierarchy"]["direct_superior"] == "shangshu"
            for packet in first.get("shangshu_ministry_packets", [])
        )
        checks["preload_target"] = all(
            preload.get("target_met") is True for preload in first.get("preloads", [])
        )
        checks["compact_metadata"] = all(
            isinstance(preload.get("metadata_bytes"), int)
            and preload["metadata_bytes"] > 0
            and preload.get("metadata", {}).get("registry_policy") == "registry-first"
            and "references/manifests/court-dispatch-hierarchy.v1.json"
            in preload.get("loaded_paths", [])
            for preload in first.get("preloads", [])
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

        wrong_root = Path(tmp_text) / "wrong-skill"
        wrong_root.mkdir()
        _write_skill(wrong_root, wrong_ministry="gongbu")
        wrong = dict(request)
        wrong["skill_root"] = str(wrong_root)
        wrong_miss = court_open_fastpath.prepare_fast_open(
            wrong,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        checks["ministry_atomic_miss"] = (
            wrong_miss.get("status") == "FAST_PATH_MISS:hierarchy_incomplete"
            and wrong_miss.get("mutations") == []
        )

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
            "preload_budget_miss",
            "compact_metadata",
        )
    )
    shangshu_gate = all(
        checks.get(name) is True
        for name in (
            "six_ministries",
            "ministry_superiors",
            "ministry_atomic_miss",
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
