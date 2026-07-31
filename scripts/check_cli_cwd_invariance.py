"""Verify request-file-relative CLI paths do not depend on the ambient cwd."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from court_open_fastpath import REQUEST_SCHEMA, _request_value, normalize_request


def _normalize_from_cwd(
    request_file: Path,
    cwd: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    previous = Path.cwd()
    try:
        os.chdir(cwd)
        value = _request_value(
            argparse.Namespace(
                request_file=str(request_file.resolve()),
                request_json=None,
            )
        )
        if not isinstance(value, dict):
            raise TypeError("request_value_object_required")
        return value, normalize_request(value)
    finally:
        os.chdir(previous)


def evaluate() -> dict[str, Any]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        request_root = temp / "request-root"
        request_root.mkdir()
        cwd_a = temp / "cwd-a"
        cwd_b = temp / "cwd-b"
        cwd_a.mkdir()
        cwd_b.mkdir()
        request_file = request_root / "court-open.json"
        request_file.write_text(
            json.dumps(
                {
                    "schema": REQUEST_SCHEMA,
                    "task_id": "cwd-invariance",
                    "authority": "super",
                    "authority_source": "explicit_latest_user",
                    "behavior": "serial",
                    "worktree": "relative-worktree",
                    "requested_offices": ["zhongshu"],
                    "write_sets": {"zhongshu": []},
                    "host_capacity": 16,
                    "host_active_agents": 1,
                    "host_retained_agents": 0,
                    "host_reclamation_status": "verified",
                    "system_memory_percent": 10.0,
                    "task_focus": "cwd invariance probe",
                    "expires_at_utc": "2099-01-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        fixture_value = json.loads(request_file.read_text(encoding="utf-8"))
        if "path_basis" in fixture_value:
            raise ValueError("fixture_must_not_self_report_path_basis")
        first_loaded, first = _normalize_from_cwd(request_file.resolve(), cwd_a)
        second_loaded, second = _normalize_from_cwd(request_file.resolve(), cwd_b)
        expected = str((request_root / "relative-worktree").resolve())
        expected_basis = {
            "kind": "request_file_parent",
            "path": str(request_root.resolve()),
        }
        first_worktree = str(first.get("worktree"))
        second_worktree = str(second.get("worktree"))
        if first_worktree != second_worktree or first_worktree != expected:
            failures.append("relative_worktree_depends_on_ambient_cwd")
        if (
            first_loaded.get("path_basis") != expected_basis
            or second_loaded.get("path_basis") != expected_basis
            or first.get("path_basis") != expected_basis
            or second.get("path_basis") != expected_basis
        ):
            failures.append("path_basis_receipt_missing")

    return {
        "schema": "court.cli_cwd_invariance_check.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": "CLI_CWD_INVARIANCE",
        "evidence": {
            "request_file": str(request_file),
            "expected_worktree": expected,
            "cwd_a_worktree": first_worktree,
            "cwd_b_worktree": second_worktree,
            "fixture_declared_path_basis": fixture_value.get("path_basis"),
            "expected_path_basis": expected_basis,
            "cwd_a_loaded_path_basis": first_loaded.get("path_basis"),
            "cwd_b_loaded_path_basis": second_loaded.get("path_basis"),
            "cwd_a_path_basis": first.get("path_basis"),
            "cwd_b_path_basis": second.get("path_basis"),
        },
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate()
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": "court.cli_cwd_invariance_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "CLI_CWD_INVARIANCE",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"CLI_CWD_INVARIANCE={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
