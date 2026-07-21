#!/usr/bin/env python3
"""Focused regressions for beta1.0.2 startup and semantic fast paths."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import importlib
import io
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Callable

sys.dont_write_bytecode = True

import check_court_open_fastpath as fixture
import court_open_fastpath


AUTHORITIES = ("approval", "autonomous", "super")
BEHAVIORS = ("serial", "parallel")
ALLOCATION_KINDS = ("skill", "mcp", "plugin", "cli", "script")
ACCEPTED_WARM_OPEN_P50_MS = 9.057


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _run_case(
    name: str,
    function: Callable[[], dict[str, object]],
    checks: dict[str, object],
    problems: list[str],
) -> None:
    try:
        checks[name] = function()
    except Exception as exc:
        checks[name] = {
            "ok": False,
            "exception_type": type(exc).__name__,
            "error": str(exc),
        }
        problems.append(f"{name}:{type(exc).__name__}:{exc}")


def check_structured_execution_contract() -> dict[str, object]:
    native = importlib.import_module("court_native_execution")
    select_native = getattr(native, "select_native_execution")
    require(
        set(getattr(native, "AUTHORITIES")) == set(AUTHORITIES),
        "native authority domain is not exactly approval|autonomous|super",
    )
    require(
        set(getattr(native, "BEHAVIORS")) == set(BEHAVIORS),
        "native behavior domain is not exactly serial|parallel",
    )
    selections: list[dict[str, object]] = []
    for authority in AUTHORITIES:
        for behavior in BEHAVIORS:
            selection = select_native(authority=authority, behavior=behavior)
            payload = selection.as_dict()
            require(payload.get("authority") == authority, f"authority drift:{authority}:{behavior}")
            require(payload.get("behavior") == behavior, f"behavior drift:{authority}:{behavior}")
            require(payload.get("runtime") == "native", f"native runtime drift:{authority}:{behavior}")
            require(payload.get("entry_path") == "court", f"native entry drift:{authority}:{behavior}")
            require("runtime_candidates" not in payload, "native selector exposed runtime candidates")
            selections.append(payload)
    return {"ok": True, "cartesian_count": len(selections), "selections": selections}


def check_distinct_runtime_entries() -> dict[str, object]:
    native = importlib.import_module("court_native_execution")
    selected_native = native.select_native_execution(authority="super", behavior="parallel")
    supercc = importlib.import_module("court_supercc_execution")
    selected_supercc = supercc.select_supercc_execution(authority="super", behavior="parallel")
    native_payload = selected_native.as_dict()
    supercc_payload = selected_supercc.as_dict()
    require(native_payload.get("entry_path") == "court", "native entry path is not court")
    require(supercc_payload.get("entry_path") == "supercc", "superCC entry path is not isolated")
    require(native_payload.get("state_namespace") != supercc_payload.get("state_namespace"), "runtime state is shared")
    require(native_payload.get("office_config") == supercc_payload.get("office_config"), "neutral office config drift")
    require(native_payload.get("runtime") != supercc_payload.get("runtime"), "runtime identity collapsed")
    supercc_cartesian = [
        supercc.select_supercc_execution(authority=authority, behavior=behavior).as_dict()
        for authority in AUTHORITIES
        for behavior in BEHAVIORS
    ]
    require(
        all(item["authority"] in AUTHORITIES and item["behavior"] in BEHAVIORS for item in supercc_cartesian),
        "superCC selector coupled authority and behavior",
    )
    launcher = importlib.import_module("ensure_supercc_court")
    prompt = launcher.office_prompt(
        "zhongshu",
        "zhongshu",
        Path.cwd(),
        None,
        authority="autonomous",
        behavior="serial",
    )
    require("runtime=superCC; authority=autonomous; behavior=serial" in prompt, "superCC prompt lost structured execution fields")
    try:
        native.select_native_execution(authority="super", behavior="parallel", runtime="supercc")
    except TypeError:
        pass
    else:
        raise AssertionError("native selector accepted a runtime switch")
    return {
        "ok": True,
        "native": native_payload,
        "supercc": supercc_payload,
        "supercc_cartesian_count": len(supercc_cartesian),
    }


def check_cli_process_isolation() -> dict[str, object]:
    registry = importlib.import_module("court_cli_registry")
    watched = {
        "court_open_fastpath",
        "court_runtime",
        "ensure_supercc_court",
    }
    for module in watched:
        sys.modules.pop(module, None)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        result = registry._resolve_and_run(
            "court",
            "open",
            ["--help"],
            "text",
            invocation_cwd=Path.cwd().resolve(strict=False),
        )
    require(result == 0, "native court help failed through unified CLI")
    loaded = sorted(module for module in watched if module in sys.modules)
    require(not loaded, "unified CLI imported a runtime instead of process-dispatching:" + ",".join(loaded))
    return {"ok": True, "dispatcher_runtime_imports": loaded}


def _import_graph(module: str, exact: tuple[str, ...], prefixes: tuple[str, ...]) -> list[str]:
    code = (
        "import importlib,json,sys;"
        f"importlib.import_module({module!r});"
        f"exact={exact!r};prefixes={prefixes!r};"
        "print(json.dumps(sorted(name for name in sys.modules "
        "if name in exact or any(name.startswith(prefix) for prefix in prefixes))))"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=Path(__file__).resolve().parent,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    require(completed.returncode == 0, f"import graph probe failed:{module}:{completed.stderr}")
    value = json.loads(completed.stdout)
    require(isinstance(value, list), f"import graph probe invalid:{module}")
    return [str(item) for item in value]


def check_runtime_import_graph() -> dict[str, object]:
    native_loaded = _import_graph(
        "court_runtime",
        ("ensure_supercc_court", "court_supercc_execution"),
        ("supercc_",),
    )
    supercc_loaded = _import_graph(
        "ensure_supercc_court",
        ("court_runtime", "court_open_fastpath"),
        ("court_native_",),
    )
    require(not native_loaded, "native runtime loaded superCC modules:" + ",".join(native_loaded))
    require(not supercc_loaded, "superCC runtime loaded native modules:" + ",".join(supercc_loaded))
    return {"ok": True, "native_cross_imports": [], "supercc_cross_imports": []}


def check_semantic_template_roundtrip() -> dict[str, object]:
    runtime = importlib.import_module("court_runtime")
    task_id = "semantic-template-roundtrip"
    task = {
        "task_id": task_id,
        "charter_revision": 1,
        "charter_sha256": "1" * 64,
        "invariant_capsule_sha256": "2" * 64,
        "state": "ThreeDepartments",
    }
    originals = {
        "load_tasks": runtime.load_tasks,
        "_event_head_sha256": runtime._event_head_sha256,
        "_event_head_bytes": runtime._event_head_bytes,
        "events_for_task": runtime.events_for_task,
    }
    runtime.load_tasks = lambda: {task_id: task}
    runtime._event_head_sha256 = lambda: "3" * 64
    runtime._event_head_bytes = lambda: 0
    runtime.events_for_task = lambda _task_id: []
    try:
        produced = runtime.public_semantic_context_template_payload(task_id)
        validation = runtime.public_semantic_context_validation_payload(produced)
        require(validation.get("ok") is True, "public template is rejected by public validator")
        consumed = runtime._semantic_context_from_args(
            SimpleNamespace(semantic_context=produced, semantic_context_file=None)
        )
        require(consumed == produced.get("context"), "checkpoint consumer did not unwrap the public template")
    finally:
        for name, value in originals.items():
            setattr(runtime, name, value)
    return {"ok": True, "producer_schema": produced.get("schema")}


class RejectRuntime(fixture.FakeRuntime):
    def __init__(self) -> None:
        task = fixture._task()
        task["semantic_state"] = "REVERIFY"
        task["semantic_receipt"] = None
        super().__init__(task)
        self.admission_calls = 0

    def validate_fast_admission(
        self,
        task: dict[str, object],
        request: dict[str, object],
    ) -> dict[str, object]:
        self.admission_calls += 1
        return super().validate_fast_admission(task, request)


def check_fail_closed_zero_dispatch() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="semantic-zero-dispatch-") as temp_text:
        root = Path(temp_text) / "skill"
        worktree = Path(temp_text) / "worktree"
        root.mkdir()
        worktree.mkdir()
        fixture._write_skill(root)
        request = fixture._request(root, worktree)
        request["behavior"] = "parallel"
        request["task_focus"] = "semantic checkpoint boundary"
        runtime = RejectRuntime()
        result = court_open_fastpath.prepare_fast_open(
            request,
            runtime_api=runtime,
            identity_loader=fixture._identity,
            concurrent_preload=False,
        )
    require(result.get("ok") is False, "invalid semantic state reached READY")
    require(runtime.admission_calls == 0, "invalid semantic state reached admission")
    require(result.get("dispatch_count") == 0, "fail-closed receipt does not prove zero dispatch")
    require(result.get("manual_bypass_allowed") is False, "fail-closed receipt permits manual bypass")
    return {"ok": True, "status": result.get("status"), "dispatch_count": 0}


class OrderedRuntime(fixture.FakeRuntime):
    def __init__(self, events: list[str]) -> None:
        super().__init__(fixture._task())
        self.events = events
        self.admission_calls = 0

    def validate_fast_admission(
        self,
        task: dict[str, object],
        request: dict[str, object],
    ) -> dict[str, object]:
        self.events.append("deliberation:" + str(request.get("calling_office")))
        self.admission_calls += 1
        return super().validate_fast_admission(task, request)


def _capability_result(*_args: object, **_kwargs: object) -> dict[str, object]:
    candidate = {
        "kind": "skill",
        "name": "decretum-release-fastpath",
        "source": "agent_fallback_skills",
        "relative_path": "decretum-release-fastpath/SKILL.md",
        "dispatchable": True,
        "observed_content_hash": "a" * 64,
        "hash_status": "MATCH",
        "version_status": "DECLARED",
        "tool_compatibility_status": "VERIFIED",
        "verification_status": "VERIFIED_LOCAL",
    }
    return {
        "schema": "court.capability.registry_first.v1",
        "owner": "libu-hr",
        "registry_path": "fixture-manifest.json",
        "manifest_state": "current",
        "selection_source": "registry",
        "fallback_reason": None,
        "selected_candidate": candidate,
        "registry_candidates_considered": [candidate],
        "dispatchable": True,
        "discovery_invoked": False,
        "discovery_call_count": 0,
        "second_registry": False,
        "daemon": False,
    }


def check_capability_snapshot_before_deliberation() -> dict[str, object]:
    events: list[str] = []
    capability_calls = 0

    def capability_loader(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal capability_calls
        capability_calls += 1
        events.append("capability")
        return _capability_result(*args, **kwargs)

    def preload_loader(*args: object, **kwargs: object) -> dict[str, court_open_fastpath.RolePreload]:
        events.append("preload")
        return court_open_fastpath.load_preloads(*args, **kwargs)

    clear_cache = getattr(court_open_fastpath, "clear_capability_snapshot_cache")
    clear_cache()
    with tempfile.TemporaryDirectory(prefix="capability-before-deliberation-") as temp_text:
        root = Path(temp_text) / "skill"
        worktree = Path(temp_text) / "worktree"
        root.mkdir()
        worktree.mkdir()
        fixture._write_skill(root)
        request = fixture._request(root, worktree)
        request["behavior"] = "parallel"
        request["task_focus"] = "startup semantic release fastpath"
        request["capability_manifest_state"] = "current"
        runtime = OrderedRuntime(events)
        first = court_open_fastpath.prepare_fast_open(
            request,
            runtime_api=runtime,
            identity_loader=fixture._identity,
            preload_loader=preload_loader,
            capability_loader=capability_loader,
            concurrent_preload=False,
        )
        started = time.perf_counter_ns()
        second = court_open_fastpath.prepare_fast_open(
            request,
            runtime_api=OrderedRuntime([]),
            identity_loader=fixture._identity,
            preload_loader=preload_loader,
            capability_loader=capability_loader,
            concurrent_preload=False,
        )
        warm_ms = (time.perf_counter_ns() - started) / 1_000_000
    require(first.get("ok") is True and second.get("ok") is True, "capability fast open not READY")
    require(capability_calls == 1, f"warm cache reloaded capability index:{capability_calls}")
    first_deliberation = next(index for index, value in enumerate(events) if value.startswith("deliberation:"))
    require(events.index("capability") < first_deliberation, "capability snapshot resolved after deliberation")
    require(events.index("preload") < first_deliberation, "office preload resolved after deliberation")
    snapshot = first.get("capability_snapshot")
    require(isinstance(snapshot, dict), "capability snapshot missing")
    allocations = snapshot.get("proposed_allocations") if isinstance(snapshot, dict) else None
    require(isinstance(allocations, dict), "capability allocations missing")
    require(set(allocations) == set(ALLOCATION_KINDS), "capability allocation kinds incomplete")
    snapshot_sha = snapshot.get("snapshot_sha256") if isinstance(snapshot, dict) else None
    require(
        all(packet.get("capability_snapshot_sha256") == snapshot_sha for packet in first.get("department_packets", [])),
        "Three Departments did not receive the same snapshot",
    )
    require(second.get("capability_cache_status") == "HIT", "warm open did not report cache hit")
    require(float(second.get("capability_lookup_ms") or 999999) <= 50.0, "warm capability lookup exceeded 50 ms")
    require(warm_ms <= ACCEPTED_WARM_OPEN_P50_MS * 1.10, "single warm open exceeded accepted +10% bound")
    return {
        "ok": True,
        "capability_calls": capability_calls,
        "events": events,
        "warm_open_ms": round(warm_ms, 3),
    }


def check_preload_cache_invalidation() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="preload-cache-") as temp_text:
        root = Path(temp_text) / "skill"
        root.mkdir(); fixture._write_skill(root)
        court_open_fastpath.clear_preload_cache()
        load = lambda: court_open_fastpath.load_preloads(root, ("zhongshu",), concurrent=False)["zhongshu"]
        first = load(); second = load()
        require(first is second, "unchanged preload did not use cache")
        profile = root / "agents" / "standing-officials" / "zhongshu.toml"
        profile.write_text(profile.read_text(encoding="utf-8") + "\n", encoding="utf-8", newline="\n")
        third = load()
        require(third is not first, "changed preload reused stale cache object")
        require(third.profile_sha256 != first.profile_sha256, "changed preload retained stale profile hash")
    return {"ok": True, "cache_hit_reused_object": True, "changed_profile_invalidated": True}


def check_authority_behavior_end_to_end() -> dict[str, object]:
    results: list[dict[str, object]] = []
    clear_cache = getattr(court_open_fastpath, "clear_capability_snapshot_cache")
    with tempfile.TemporaryDirectory(prefix="execution-cartesian-") as temp_text:
        root = Path(temp_text) / "skill"
        worktree = Path(temp_text) / "worktree"
        root.mkdir()
        worktree.mkdir()
        fixture._write_skill(root)
        for authority in AUTHORITIES:
            for behavior in BEHAVIORS:
                clear_cache()
                request = fixture._request(root, worktree)
                request["authority"] = authority
                request["behavior"] = behavior
                request["task_focus"] = f"{authority} {behavior} startup"
                runtime = OrderedRuntime([])
                receipt = court_open_fastpath.prepare_fast_open(
                    request,
                    runtime_api=runtime,
                    identity_loader=fixture._identity,
                    capability_loader=_capability_result,
                    concurrent_preload=False,
                )
                require(receipt.get("ok") is True, f"cartesian open failed:{authority}:{behavior}")
                execution = receipt.get("execution")
                require(isinstance(execution, dict), "execution receipt missing")
                require(execution.get("authority") == authority, "receipt authority drift")
                require(execution.get("behavior") == behavior, "receipt behavior drift")
                expected_dispatch = 9 if behavior == "parallel" else 0
                require(receipt.get("dispatch_count") == expected_dispatch, "behavior dispatch count drift")
                require(runtime.admission_calls == expected_dispatch, "behavior admission count drift")
                if behavior == "parallel":
                    coordination = receipt.get("shangshu_ministry_coordination")
                    require(isinstance(coordination, dict), "parallel shangshu coordination missing")
                    require(
                        coordination.get("schema") == "court.shangshu_ministry_coordination.v1",
                        "parallel shangshu coordination schema drift",
                    )
                    require(
                        coordination.get("dispatch_initiator") == "shangshu",
                        "parallel ministries were not dispatched by shangshu",
                    )
                    require(
                        coordination.get("dispatch_target_kind") == "six_ministry_child_offices",
                        "parallel ministry target kind drift",
                    )
                    require(
                        coordination.get("taizi_direct_ministry_dispatch_allowed") is False,
                        "taizi direct ministry dispatch leaked into parallel receipt",
                    )
                    require(
                        coordination.get("selected_ministries") == list(court_open_fastpath.SIX_MINISTRIES),
                        "parallel selected ministries drift",
                    )
                results.append({"authority": authority, "behavior": behavior, "dispatch_count": expected_dispatch})
    return {"ok": True, "cartesian_count": len(results), "results": results}


def check_bounded_maintenance_paths() -> dict[str, object]:
    outcomes: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="capability-maintenance-") as temp_text:
        root = Path(temp_text) / "skill"
        worktree = Path(temp_text) / "worktree"
        root.mkdir()
        worktree.mkdir()
        fixture._write_skill(root)
        manifests = {
            "missing": Path(temp_text) / "missing.json",
            "stale": Path(temp_text) / "stale.json",
            "corrupt": Path(temp_text) / "corrupt.json",
        }
        manifests["stale"].write_text(json.dumps({"capabilities": []}), encoding="utf-8")
        manifests["corrupt"].write_text("{", encoding="utf-8")
        for state, manifest in manifests.items():
            before = manifest.read_bytes() if manifest.exists() else None
            court_open_fastpath.clear_capability_snapshot_cache()
            request = fixture._request(root, worktree)
            request["behavior"] = "serial"
            request["task_focus"] = "bounded capability maintenance"
            request["capability_manifest"] = str(manifest)
            request["capability_manifest_state"] = state
            runtime = OrderedRuntime([])
            receipt = court_open_fastpath.prepare_fast_open(
                request,
                runtime_api=runtime,
                identity_loader=fixture._identity,
                concurrent_preload=False,
            )
            require(receipt.get("ok") is True, f"maintenance open failed:{state}")
            snapshot = receipt.get("capability_snapshot")
            maintenance = snapshot.get("maintenance") if isinstance(snapshot, dict) else None
            require(isinstance(maintenance, dict), f"maintenance receipt missing:{state}")
            require(maintenance.get("invoked") is True, f"maintenance not invoked:{state}")
            require(maintenance.get("call_count") == 1, f"maintenance call count drift:{state}")
            require(maintenance.get("second_registry") is False, f"second registry created:{state}")
            require(maintenance.get("daemon") is False, f"daemon started:{state}")
            assignment = maintenance.get("assignment")
            require(isinstance(assignment, dict), f"maintenance assignment missing:{state}")
            require(assignment.get("owner") == "libu-hr", f"maintenance owner drift:{state}")
            after = manifest.read_bytes() if manifest.exists() else None
            require(after == before, f"manifest mutated:{state}")
            require(runtime.admission_calls == 0, f"serial maintenance dispatched:{state}")
            outcomes[state] = {
                "call_count": maintenance.get("call_count"),
                "manifest_unchanged": True,
            }
    return {"ok": True, "outcomes": outcomes}


def run_checks() -> dict[str, object]:
    checks: dict[str, object] = {}
    problems: list[str] = []
    for name, function in (
        ("structured_execution_contract", check_structured_execution_contract),
        ("distinct_runtime_entries", check_distinct_runtime_entries),
        ("cli_process_isolation", check_cli_process_isolation),
        ("runtime_import_graph", check_runtime_import_graph),
        ("semantic_template_roundtrip", check_semantic_template_roundtrip),
        ("fail_closed_zero_dispatch", check_fail_closed_zero_dispatch),
        ("capability_snapshot_before_deliberation", check_capability_snapshot_before_deliberation),
        ("preload_cache_invalidation", check_preload_cache_invalidation),
        ("authority_behavior_end_to_end", check_authority_behavior_end_to_end),
        ("bounded_maintenance_paths", check_bounded_maintenance_paths),
    ):
        _run_case(name, function, checks, problems)
    return {
        "schema": "decretum.startup_fastpath_contract.check.v1",
        "ok": not problems,
        "status": "PASS" if not problems else "FAIL",
        "STARTUP_SEMANTIC_FASTPATH": "PASS" if not problems else "FAIL",
        "checks": checks,
        "problems": problems,
        "pending_body_access": "NO",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = run_checks()
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        print(f"STARTUP_SEMANTIC_FASTPATH={result['STARTUP_SEMANTIC_FASTPATH']}")
        for problem in result["problems"]:
            print(f"problem={problem}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
