#!/usr/bin/env python3
"""Benchmark fragmented legacy preload orchestration against court open --fast."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Sequence


sys.dont_write_bytecode = True

import court_open_fastpath


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
ROLES = (*court_open_fastpath.THREE_DEPARTMENTS, *court_open_fastpath.SIX_MINISTRIES)


class BenchmarkRuntime:
    def load_tasks(self) -> dict[str, dict[str, object]]:
        return {"cli-performance-fixture": _task()}

    @staticmethod
    def public_dispatch_context_packet(
        task: dict[str, object], wave_id: str
    ) -> dict[str, object]:
        receipt = task["semantic_receipt"]
        assert isinstance(receipt, dict)
        return {
            "schema": "court.semantic.dispatch_context_packet.v1",
            "task_id": task["task_id"],
            "sub_id": wave_id,
            "semantic_epoch": receipt["semantic_epoch"],
            "semantic_receipt_sha256": receipt["receipt_sha256"],
        }

    @staticmethod
    def public_context_budget_pool(
        task: dict[str, object], wave_id: str
    ) -> dict[str, object]:
        return {
            "schema": "court.budget.pool.v1",
            "budget_id": f"budget:{task['task_id']}:{wave_id}",
            "root_id": "taizi",
        }

    @staticmethod
    def validate_fast_admission(
        _task_value: dict[str, object], request: dict[str, object]
    ) -> dict[str, object]:
        return {
            "allowed": True,
            "decision": "admitted",
            "selected_protocol": "v2",
            "selected_bindings": list(request["requested_bindings"]),
        }


def _task() -> dict[str, object]:
    return {
        "task_id": "cli-performance-fixture",
        "semantic_epoch": 7,
        "semantic_state": "DISPATCHABLE",
        "semantic_receipt": {
            "receipt_id": "SR-CLI-PERFORMANCE",
            "receipt_sha256": "1" * 64,
            "semantic_epoch": 7,
            "charter_sha256": "2" * 64,
            "invariant_capsule_sha256": "3" * 64,
            "checkpoint_id": "SC-CLI-PERFORMANCE",
            "plan_sha256": "4" * 64,
            "plan_cursor": "PHASE5.2 -> PHASE9 -> PHASE10",
            "verdict": "DISPATCHABLE",
        },
    }


def _identity(path: Path) -> tuple[dict[str, object], list[list[str]]]:
    return (
        {
            "path": str(path.resolve()),
            "branch": "release/beta0.5.13",
            "HEAD": "5" * 40,
            "index_count": 0,
            "tracked_dirty_count": 0,
        },
        [["git", "benchmark-fixture"]],
    )


def _request() -> dict[str, object]:
    return {
        "schema": court_open_fastpath.REQUEST_SCHEMA,
        "task_id": "cli-performance-fixture",
        "authority": "super",
        "worktree": str(ROOT),
        "skill_root": str(ROOT),
        "host_capacity": 16,
        "host_active_agents": 1,
        "host_retained_agents": 0,
        "host_reclamation_status": "verified",
        "system_memory_percent": 40.0,
        "requested_offices": list(court_open_fastpath.THREE_DEPARTMENTS),
        "include_shangshu_ministries": True,
        "write_sets": {},
        "expected_branch": "release/beta0.5.13",
        "expected_head": "5" * 40,
        "expected_semantic_receipt_sha256": "1" * 64,
        "expected_plan_sha256": "4" * 64,
        "transport": "codex",
        "expires_at_utc": "2099-01-01T00:00:00+00:00",
    }


def _fast_operation() -> dict[str, object]:
    result = court_open_fastpath.prepare_fast_open(
        _request(),
        runtime_api=BenchmarkRuntime(),
        identity_loader=_identity,
        concurrent_preload=False,
    )
    if result.get("ok") is not True:
        raise RuntimeError(f"fast operation failed: {result}")
    return {
        "packet_sha256": result["packet_sha256"],
        "operation_id": result["operation_id"],
        "python_processes": 1,
        "max_loaded_bytes": max(
            int(item["loaded_bytes"]) for item in result["preloads"]
        ),
    }


def _legacy_role_operation(role: str) -> dict[str, object]:
    preloads = court_open_fastpath.load_preloads(ROOT, [role], concurrent=False)
    preload = preloads[role]
    caller = "taizi" if role in court_open_fastpath.THREE_DEPARTMENTS else "shangshu"
    hierarchy = court_open_fastpath._hierarchy_decision(caller, role)
    return {
        "role": role,
        "direct_superior": hierarchy["direct_superior"],
        "loaded_bytes": preload.loaded_bytes,
        "metadata_sha256": preload.metadata_sha256,
    }


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _run_worker(kind: str, role: str | None = None) -> dict[str, object]:
    command = [sys.executable, "-B", str(SCRIPT), "--worker", kind]
    if role is not None:
        command.extend(("--role", role))
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"worker {kind}/{role or '-'} failed: {completed.stdout}{completed.stderr}"
        )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("worker receipt invalid")
    return value


def _legacy_operation() -> dict[str, object]:
    receipts = [_run_worker("legacy-role", role) for role in ROLES]
    return {
        "receipt_sha256": _canonical_sha256(receipts),
        "python_processes": len(receipts),
        "max_loaded_bytes": max(int(item["loaded_bytes"]) for item in receipts),
    }


def _sample(operation) -> tuple[float, dict[str, object]]:
    started = time.perf_counter_ns()
    receipt = operation()
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    return elapsed_ms, receipt


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _summary(values: list[float]) -> dict[str, object]:
    return {
        "samples": len(values),
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(_percentile(values, 0.95), 3),
        "min_ms": round(min(values), 3),
        "max_ms": round(max(values), 3),
        "raw_ms": [round(value, 3) for value in values],
    }


def _improvement(legacy: dict[str, object], fast: dict[str, object]) -> float:
    legacy_p50 = float(legacy["p50_ms"])
    fast_p50 = float(fast["p50_ms"])
    return round(((legacy_p50 - fast_p50) / legacy_p50) * 100.0, 2)


def benchmark(samples: int) -> dict[str, object]:
    if samples < 10:
        raise ValueError("at least 10 samples are required")

    cold_fast: list[float] = []
    cold_legacy: list[float] = []
    fast_receipts: list[str] = []
    legacy_receipts: list[str] = []
    for index in range(samples):
        first, second = (
            (("fast", lambda: _run_worker("fast")), ("legacy", _legacy_operation))
            if index % 2 == 0
            else (("legacy", _legacy_operation), ("fast", lambda: _run_worker("fast")))
        )
        for label, operation in (first, second):
            elapsed, receipt = _sample(operation)
            if label == "fast":
                cold_fast.append(elapsed)
                fast_receipts.append(str(receipt["packet_sha256"]))
            else:
                cold_legacy.append(elapsed)
                legacy_receipts.append(str(receipt["receipt_sha256"]))

    _fast_operation()
    _legacy_operation()
    warm_fast: list[float] = []
    warm_legacy: list[float] = []
    for index in range(samples):
        first, second = (
            (("fast", _fast_operation), ("legacy", _legacy_operation))
            if index % 2 == 0
            else (("legacy", _legacy_operation), ("fast", _fast_operation))
        )
        for label, operation in (first, second):
            elapsed, receipt = _sample(operation)
            if label == "fast":
                warm_fast.append(elapsed)
                fast_receipts.append(str(receipt["packet_sha256"]))
            else:
                warm_legacy.append(elapsed)
                legacy_receipts.append(str(receipt["receipt_sha256"]))

    cold = {"legacy": _summary(cold_legacy), "fast": _summary(cold_fast)}
    warm = {"legacy": _summary(warm_legacy), "fast": _summary(warm_fast)}
    cold_improvement = _improvement(cold["legacy"], cold["fast"])
    warm_improvement = _improvement(warm["legacy"], warm["fast"])
    deterministic = len(set(fast_receipts)) == 1 and len(set(legacy_receipts)) == 1
    fast_probe = _fast_operation()
    legacy_probe = _legacy_operation()
    ok = (
        deterministic
        and int(fast_probe["python_processes"]) == 1
        and int(legacy_probe["python_processes"]) == len(ROLES)
        and int(fast_probe["max_loaded_bytes"])
        <= court_open_fastpath.MINIMAL_PRELOAD_BYTES
        and cold_improvement >= 30.0
        and warm_improvement >= 30.0
    )
    return {
        "schema": "decretum.cli_performance_check.v1",
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "CLI_PERFORMANCE_GATE": "PASS" if ok else "FAIL",
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "samples_per_class": samples,
        "definitions": {
            "cold": "fresh Python process per command; no model or real child startup",
            "warm": "primed filesystem/import state; fast repeats in one interpreter",
            "legacy": "nine serial role-local Python commands loading the exact compact preload and hierarchy",
            "fast": "one Python interpreter prepares all department/ministry preload, semantic admission, and packets",
        },
        "process_counts": {
            "legacy_python_processes": legacy_probe["python_processes"],
            "fast_python_processes": fast_probe["python_processes"],
        },
        "cold": cold,
        "warm": warm,
        "cold_p50_improvement_percent": cold_improvement,
        "warm_p50_improvement_percent": warm_improvement,
        "deterministic_receipts": deterministic,
        "max_fast_preload_bytes": fast_probe["max_loaded_bytes"],
        "preload_target_bytes": court_open_fastpath.MINIMAL_PRELOAD_BYTES,
        "pending_body_access": "NO",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("fast", "legacy-role"))
    parser.add_argument("--role", choices=ROLES)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.worker == "fast":
        print(json.dumps(_fast_operation(), sort_keys=True))
        return 0
    if args.worker == "legacy-role":
        if args.role is None:
            parser.error("--role is required for legacy-role")
        print(json.dumps(_legacy_role_operation(args.role), sort_keys=True))
        return 0
    report = benchmark(args.samples)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.json else None, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
