"""Concurrency and crash-safety regressions for the superCC runtime store."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
from pathlib import Path
import queue
import sys

sys.dont_write_bytecode = True
import tempfile
from typing import Any
from unittest import mock


SCRIPTS = Path(__file__).resolve().parent
ROLE_WRITERS = 12
HEALTH_WRITERS = 16


def _load_court(shared_root: str):
    os.environ["COURT_SHARED_SHIGUAN_ROOT"] = shared_root
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import ensure_supercc_court  # type: ignore

    return ensure_supercc_court


def check_extracted_store_contract(shared_root: Path) -> dict[str, Any]:
    court = _load_court(str(shared_root))
    import supercc_office_state as store  # type: ignore

    if court.SUPERCC_STATE_SCHEMA != store.SUPERCC_STATE_SCHEMA:
        raise AssertionError("launcher and extracted store schema drifted")
    if court.read_office_state is not store.read_office_state:
        raise AssertionError("launcher did not re-export the extracted read API")
    if court.office_state_path() != store.office_state_path():
        raise AssertionError("launcher and extracted store path drifted")
    return {"module": "supercc_office_state", "read_api_reexported": True, "write_wrapper_injects_dossier_state": True}


def _role_writer(
    shared_root: str,
    role: str,
    ready: Any,
    start: Any,
    results: Any,
) -> None:
    try:
        court = _load_court(shared_root)
        ready.put(role)
        if not start.wait(20):
            raise TimeoutError("role writer start gate timed out")
        result = court.write_office_state(
            Path(shared_root),
            {
                role: {
                    "mode": "fixture",
                    "writer": role,
                    "payload": role * 32768,
                }
            },
            zellij_session="fixture-session",
            dry_run=False,
        )
        results.put({"role": role, "ok": bool(result.get("ok"))})
    except BaseException as exc:  # pragma: no cover - child-process evidence
        results.put({"role": role, "ok": False, "error": repr(exc)})


def _health_writer(
    shared_root: str,
    writer: int,
    ready: Any,
    start: Any,
    results: Any,
) -> None:
    try:
        court = _load_court(shared_root)
        ready.put(writer)
        if not start.wait(20):
            raise TimeoutError("health writer start gate timed out")
        payload = {
            "schema": court.SUPERCC_HEALTH_SCHEMA,
            "writer": writer,
            "payload": str(writer) * 16384,
        }
        result = court.append_turn_health(payload, dry_run=False)
        results.put({"writer": writer, "ok": bool(result.get("ok"))})
    except BaseException as exc:  # pragma: no cover - child-process evidence
        results.put({"writer": writer, "ok": False, "error": repr(exc)})


def _crash_while_holding_runtime_lock(shared_root: str, acquired: Any) -> None:
    court = _load_court(shared_root)
    from court_file_lock import file_lock

    with file_lock(court.supercc_runtime_lock_path(), timeout=10.0):
        acquired.set()
        os._exit(17)


def _collect_process_results(processes: list[Any], results: Any, expected: int) -> list[dict[str, Any]]:
    for process in processes:
        process.join(45)
    stuck = [process.pid for process in processes if process.is_alive()]
    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(10)
    if stuck:
        raise AssertionError(f"worker processes did not exit: {stuck}")

    records: list[dict[str, Any]] = []
    for _ in range(expected):
        try:
            records.append(results.get(timeout=5))
        except queue.Empty as exc:
            raise AssertionError(f"expected {expected} worker results, received {len(records)}") from exc
    failures = [record for record in records if not record.get("ok")]
    if failures:
        raise AssertionError(f"worker failures: {failures}")
    return records


def _start_workers(ctx: Any, target: Any, argument_rows: list[tuple[Any, ...]]) -> tuple[list[Any], Any, Any]:
    ready = ctx.Queue()
    start = ctx.Event()
    results = ctx.Queue()
    processes = [
        ctx.Process(target=target, args=(*arguments, ready, start, results))
        for arguments in argument_rows
    ]
    for process in processes:
        process.start()
    for _ in processes:
        try:
            ready.get(timeout=30)
        except queue.Empty as exc:
            raise AssertionError("workers did not reach the start gate") from exc
    start.set()
    return processes, results, start


def check_role_merge(ctx: Any, shared_root: Path) -> dict[str, Any]:
    roles = [f"fixture-role-{index:02d}" for index in range(ROLE_WRITERS)]
    processes, results, _ = _start_workers(
        ctx,
        _role_writer,
        [(str(shared_root), role) for role in roles],
    )
    _collect_process_results(processes, results, len(roles))

    court = _load_court(str(shared_root))
    state = court.read_office_state(shared_root, "fixture-session")
    if not state.get("ok"):
        raise AssertionError(f"runtime state was not readable after concurrent writes: {state}")
    actual_roles = set((state.get("roles") or {}).keys())
    missing = sorted(set(roles) - actual_roles)
    if missing:
        raise AssertionError(f"concurrent role updates were lost: {missing}")
    return {"writers": len(roles), "roles": len(actual_roles)}


def check_context_isolation(shared_root: Path) -> dict[str, Any]:
    court = _load_court(str(shared_root))
    workspace_a = shared_root / "workspace-a"
    workspace_b = shared_root / "workspace-b"
    court.write_office_state(
        workspace_a,
        {"role-a": {"writer": "a"}, "shared-role": {"writer": "a"}},
        zellij_session="session-a",
        dry_run=False,
    )
    court.write_office_state(
        workspace_b,
        {"role-b": {"writer": "b"}, "shared-role": {"writer": "b"}},
        zellij_session="session-b",
        dry_run=False,
    )
    state_a = court.read_office_state(workspace_a, "session-a")
    state_b = court.read_office_state(workspace_b, "session-b")
    roles_a = state_a.get("roles") or {}
    roles_b = state_b.get("roles") or {}
    if "role-b" in roles_a or "role-a" in roles_b:
        raise AssertionError("different context roles leaked across workspace/session boundaries")
    if (roles_a.get("shared-role") or {}).get("writer") != "a" or (roles_b.get("shared-role") or {}).get("writer") != "b":
        raise AssertionError("same role was overwritten across contexts")
    missing = court.read_office_state(workspace_a, "session-missing")
    if missing.get("reason") != "context_missing" or missing.get("roles"):
        raise AssertionError(f"unknown context did not fail closed: {missing}")
    raw = json.loads(court.office_state_path().read_text(encoding="utf-8"))
    if raw.get("schema") != court.SUPERCC_STATE_SCHEMA or len(raw.get("contexts") or {}) != 2:
        raise AssertionError("v2 context partition was not durably committed")
    if raw.get("active_context_id") != state_b.get("context_id") or (raw.get("roles", {}).get("shared-role") or {}).get("writer") != "b":
        raise AssertionError("top-level compatibility projection did not select the active context")
    return {"contexts": 2, "same_role_isolated": True, "missing_context_closed": True}


def check_v1_lazy_migration(shared_root: Path) -> dict[str, Any]:
    court = _load_court(str(shared_root))
    legacy_workspace = shared_root / "legacy-workspace"
    path = court.office_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = {
        "schema": court.SUPERCC_STATE_SCHEMA_V1,
        "updated_at": "2026-01-01T00:00:00+00:00",
        "workspace": str(legacy_workspace.resolve()),
        "zellij_session": "legacy-session",
        "roles": {"legacy-role": {"writer": "legacy"}},
    }
    path.write_text(json.dumps(legacy, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    before = path.read_bytes()
    compatible = court.read_office_state(legacy_workspace, "legacy-session")
    if not compatible.get("ok") or "legacy-role" not in (compatible.get("roles") or {}) or path.read_bytes() != before:
        raise AssertionError("v1 compatibility read mutated or lost the legacy state")
    new_workspace = shared_root / "new-workspace"
    court.write_office_state(
        new_workspace,
        {"new-role": {"writer": "new"}},
        zellij_session="new-session",
        dry_run=False,
    )
    migrated = json.loads(path.read_text(encoding="utf-8"))
    legacy_id = court.office_context_id(legacy_workspace, "legacy-session")
    new_id = court.office_context_id(new_workspace, "new-session")
    contexts = migrated.get("contexts") or {}
    if migrated.get("schema") != court.SUPERCC_STATE_SCHEMA or set(contexts) != {legacy_id, new_id}:
        raise AssertionError("v1 state did not lazily migrate into v2 contexts")
    if "legacy-role" not in (contexts[legacy_id].get("roles") or {}) or "new-role" not in (contexts[new_id].get("roles") or {}):
        raise AssertionError("v1 migration lost a context role")
    return {"read_zero_write": True, "contexts_after_migration": 2}


def check_unknown_schema_closed(shared_root: Path) -> dict[str, Any]:
    court = _load_court(str(shared_root))
    path = court.office_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    unknown = {
        "schema": "court.supercc.office_state.future",
        "workspace": str((shared_root / "workspace").resolve()),
        "zellij_session": "session",
        "roles": {"must-not-load": {"writer": "future"}},
    }
    path.write_text(json.dumps(unknown, sort_keys=True) + "\n", encoding="utf-8")
    before = path.read_bytes()
    read_result = court.read_office_state(shared_root / "workspace", "session")
    if read_result.get("reason") != "unsupported_schema" or read_result.get("roles"):
        raise AssertionError(f"unknown state schema did not fail closed on read: {read_result}")
    try:
        court.write_office_state(shared_root / "workspace", {"new": {}}, zellij_session="session", dry_run=False)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown state schema did not fail closed on write")
    if path.read_bytes() != before:
        raise AssertionError("unknown-schema rejection changed committed bytes")
    return {"read_closed": True, "write_closed": True, "bytes_preserved": True}


def check_known_schema_malformed_closed(shared_root: Path) -> dict[str, Any]:
    court = _load_court(str(shared_root))
    path = court.office_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    workspace_a, workspace_b = shared_root / "workspace-a", shared_root / "workspace-b"
    context_a = court.office_context_id(workspace_a, "session-a")
    valid_context = {
        "context_id": context_a, "updated_at": "fixture", "workspace": str(workspace_a.resolve()),
        "zellij_session": "session-a", "roles": {"fixture": {}},
    }
    cases = [
        {"schema": court.SUPERCC_STATE_SCHEMA_V1, "workspace": str(workspace_a.resolve()), "zellij_session": "session-a", "roles": []},
        {"schema": court.SUPERCC_STATE_SCHEMA_V1, "workspace": str(workspace_a.resolve()), "zellij_session": "session-a", "roles": {"taizi": []}},
        {
            "schema": court.SUPERCC_STATE_SCHEMA, "active_context_id": context_a,
            "workspace": str(workspace_b.resolve()), "zellij_session": "session-b", "roles": {},
            "contexts": {context_a: {**valid_context, "workspace": str(workspace_b.resolve()), "zellij_session": "session-b"}},
        },
        {
            "schema": court.SUPERCC_STATE_SCHEMA, "active_context_id": context_a,
            "workspace": str(workspace_b.resolve()), "zellij_session": "session-a", "roles": {"fixture": {}},
            "contexts": {context_a: valid_context},
        },
        {
            "schema": court.SUPERCC_STATE_SCHEMA, "active_context_id": context_a,
            "workspace": str(workspace_a.resolve()), "zellij_session": "session-a", "roles": {"taizi": []},
            "contexts": {context_a: {**valid_context, "roles": {"taizi": []}}},
        },
    ]
    for index, payload in enumerate(cases):
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        before = path.read_bytes()
        read_result = court.read_office_state(workspace_a, "session-a")
        if read_result.get("ok") or read_result.get("roles"):
            raise AssertionError(f"known malformed schema case {index} did not fail closed: {read_result}")
        try:
            court.write_office_state(workspace_a, {"new": {}}, zellij_session="session-a", dry_run=False)
        except ValueError:
            pass
        else:
            raise AssertionError(f"known malformed schema case {index} was writable")
        if path.read_bytes() != before:
            raise AssertionError(f"known malformed schema case {index} changed committed bytes")
    return {"cases": len(cases), "read_closed": True, "write_closed": True, "bytes_preserved": True}


def check_health_jsonl(ctx: Any, shared_root: Path) -> dict[str, Any]:
    processes, results, _ = _start_workers(
        ctx,
        _health_writer,
        [(str(shared_root), writer) for writer in range(HEALTH_WRITERS)],
    )
    _collect_process_results(processes, results, HEALTH_WRITERS)

    court = _load_court(str(shared_root))
    path = court.office_health_path()
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) != HEALTH_WRITERS:
        raise AssertionError(f"health JSONL lost records: expected {HEALTH_WRITERS}, got {len(lines)}")
    records = [json.loads(line) for line in lines]
    writers = {int(record["writer"]) for record in records}
    if writers != set(range(HEALTH_WRITERS)):
        raise AssertionError(f"health JSONL writer set drifted: {sorted(writers)}")
    return {"writers": HEALTH_WRITERS, "lines": len(lines)}


def check_crash_release(ctx: Any, shared_root: Path) -> dict[str, Any]:
    acquired = ctx.Event()
    process = ctx.Process(
        target=_crash_while_holding_runtime_lock,
        args=(str(shared_root), acquired),
    )
    process.start()
    if not acquired.wait(20):
        process.terminate()
        process.join(10)
        raise AssertionError("crash worker did not acquire the runtime lock")
    process.join(20)
    if process.is_alive():
        process.terminate()
        process.join(10)
        raise AssertionError("crash worker did not exit")
    if process.exitcode != 17:
        raise AssertionError(f"unexpected crash worker exit code: {process.exitcode}")

    court = _load_court(str(shared_root))
    result = court.write_office_state(
        shared_root,
        {"after-crash": {"mode": "fixture"}},
        zellij_session="fixture-session",
        dry_run=False,
    )
    if not result.get("ok"):
        raise AssertionError(f"runtime store did not recover after lock owner crash: {result}")
    return {"crash_exit_code": process.exitcode, "recovered": True}


def check_dry_run_zero_files(shared_root: Path) -> dict[str, Any]:
    court = _load_court(str(shared_root))
    state_result = court.write_office_state(
        shared_root,
        {"dry-run-role": {"mode": "fixture"}},
        zellij_session="fixture-session",
        dry_run=True,
    )
    health_result = court.append_turn_health(
        {"schema": court.SUPERCC_HEALTH_SCHEMA, "writer": "dry-run"},
        dry_run=True,
    )
    read_result = court.read_office_state(shared_root, "fixture-session")
    files = sorted(path for path in shared_root.rglob("*") if path.is_file()) if shared_root.exists() else []
    if files:
        raise AssertionError(f"dry-run/read-only operations created files: {files}")
    if not state_result.get("dry_run") or not health_result.get("dry_run"):
        raise AssertionError("dry-run result markers are missing")
    if read_result.get("reason") != "missing":
        raise AssertionError(f"unexpected read-only missing-state result: {read_result}")
    return {"files_created": 0}


def check_health_atomic_failure(shared_root: Path) -> dict[str, Any]:
    court = _load_court(str(shared_root))
    court.append_turn_health({"writer": "baseline"}, dry_run=False)
    path = court.office_health_path()
    before = path.read_bytes()
    with mock.patch.object(court, "atomic_write_text", side_effect=OSError("fixture replace failure")):
        try:
            court.append_turn_health({"writer": "interrupted"}, dry_run=False)
        except OSError:
            pass
        else:
            raise AssertionError("simulated health transaction failure unexpectedly succeeded")
    if path.read_bytes() != before:
        raise AssertionError("failed health transaction changed the committed JSONL")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if [record.get("writer") for record in records] != ["baseline"]:
        raise AssertionError(f"health JSONL was not crash-safe: {records}")
    return {"committed_lines": 1, "failed_transaction_preserved": True}


def check_state_atomic_failure(shared_root: Path) -> dict[str, Any]:
    court = _load_court(str(shared_root))
    workspace = shared_root / "workspace"
    court.write_office_state(workspace, {"baseline": {"writer": "baseline"}}, zellij_session="session", dry_run=False)
    path = court.office_state_path()
    before = path.read_bytes()
    with mock.patch.object(court, "atomic_write_text", side_effect=OSError("fixture replace failure")):
        try:
            court.write_office_state(workspace, {"interrupted": {"writer": "interrupted"}}, zellij_session="session", dry_run=False)
        except OSError:
            pass
        else:
            raise AssertionError("simulated state transaction failure unexpectedly succeeded")
    if path.read_bytes() != before:
        raise AssertionError("failed state transaction changed committed bytes")
    state = court.read_office_state(workspace, "session")
    if "baseline" not in (state.get("roles") or {}) or "interrupted" in (state.get("roles") or {}):
        raise AssertionError("state atomic failure exposed an uncommitted role")
    return {"failed_transaction_preserved": True}


def check_watchdog_context_selection(shared_root: Path) -> dict[str, Any]:
    court = _load_court(str(shared_root))
    import supercc_watchdog as watchdog  # type: ignore

    workspace = shared_root / "watchdog-workspace"
    court.write_office_state(workspace, {"watchdog-role": {"writer": "selected"}}, zellij_session="watchdog-session", dry_run=False)
    args = argparse.Namespace(
        workspace=str(workspace), zellij_session="watchdog-session", roles="visible-core",
        stale_seconds=900.0, apply=False, no_apply=True, log_jsonl=None, pid_file=None,
    )
    with mock.patch.object(watchdog.court, "supercc_check_for_args", return_value={"zellij": {"selected_session": "watchdog-session"}}), \
         mock.patch.object(watchdog.court, "expand_status_selection", return_value=()), \
         mock.patch.object(watchdog, "load_optional_state", wraps=watchdog.load_optional_state) as loader:
        payload = watchdog.watchdog_once(args)
    loader.assert_called_once_with(workspace.resolve(), "watchdog-session")
    if not payload.get("state_available"):
        raise AssertionError("watchdog did not select its workspace/session state")
    return {"workspace_session_forwarded": True}


def run_checks() -> dict[str, Any]:
    ctx = mp.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="court-supercc-state-concurrency-") as raw_temp:
        temp = Path(raw_temp)
        extracted_store_result = check_extracted_store_contract(temp / "extracted-store-shared")
        role_result = check_role_merge(ctx, temp / "role-shared")
        context_result = check_context_isolation(temp / "context-shared")
        migration_result = check_v1_lazy_migration(temp / "migration-shared")
        unknown_schema_result = check_unknown_schema_closed(temp / "unknown-schema-shared")
        known_malformed_result = check_known_schema_malformed_closed(temp / "known-malformed-shared")
        health_result = check_health_jsonl(ctx, temp / "health-shared")
        crash_result = check_crash_release(ctx, temp / "crash-shared")
        dry_run_result = check_dry_run_zero_files(temp / "dry-run-shared")
        health_atomic_result = check_health_atomic_failure(temp / "health-atomic-shared")
        state_atomic_result = check_state_atomic_failure(temp / "state-atomic-shared")
        watchdog_result = check_watchdog_context_selection(temp / "watchdog-shared")
    return {
        "ok": True,
        "schema": "court.supercc.state_concurrency_check.v1",
        "extracted_store": extracted_store_result,
        "role_merge": role_result,
        "context_isolation": context_result,
        "v1_lazy_migration": migration_result,
        "unknown_schema": unknown_schema_result,
        "known_schema_malformed": known_malformed_result,
        "health_jsonl": health_result,
        "crash_release": crash_result,
        "dry_run": dry_run_result,
        "health_atomic_failure": health_atomic_result,
        "state_atomic_failure": state_atomic_result,
        "watchdog_context_selection": watchdog_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = run_checks()
    except Exception as exc:
        result = {
            "ok": False,
            "schema": "court.supercc.state_concurrency_check.v1",
            "error": str(exc),
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print(
            "SUPERCC_STATE_CONCURRENCY_OK "
            f"roles={result['role_merge']['roles']} "
            f"health_lines={result['health_jsonl']['lines']} "
            f"crash_recovered={str(result['crash_release']['recovered']).lower()} "
            f"dry_run_files={result['dry_run']['files_created']}"
        )
    else:
        print(f"SUPERCC_STATE_CONCURRENCY_FAILED {result['error']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
