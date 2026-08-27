#!/usr/bin/env python3
"""Regression checks for the doctor, debug, and fix CLI aliases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "court_cli.py"
SCHEMA = "decretum.doctor_debug_fix_check.v1"


def _run(*arguments: str) -> tuple[int, dict[str, object], str]:
    completed = subprocess.run(
        [sys.executable, "-B", str(CLI), "--format", "json", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"CLI did not return JSON: {completed.stdout!r} {completed.stderr!r}"
        ) from exc
    if not isinstance(payload, dict):
        raise AssertionError("CLI JSON envelope must be an object")
    return completed.returncode, payload, completed.stderr


def _nested(envelope: dict[str, object]) -> dict[str, object]:
    value = envelope.get("payload")
    if not isinstance(value, dict):
        raise AssertionError(f"CLI payload must be an object: {value!r}")
    return value


def evaluate() -> dict[str, object]:
    checks: dict[str, bool] = {}
    missing_source = ROOT / "__doctor_missing_source__"

    doctor_code, doctor_envelope, doctor_stderr = _run(
        "doctor",
        "--source-root",
        str(missing_source),
        "--mapped-root",
        str(ROOT),
    )
    doctor = _nested(doctor_envelope)
    source = doctor.get("source_selection")
    path_policy = doctor.get("path_policy")
    mcp = doctor.get("mcp_configuration")
    roles = doctor.get("codex_agent_roles")
    mcp_probe = mcp.get("runtime_probe") if isinstance(mcp, dict) else None
    checks["doctor_alias_uses_verified_mapped_root_fallback"] = (
        doctor_code in (0, 2)
        and doctor_envelope.get("status") in ("PASS", "BLOCKED")
        and doctor.get("ok") is True
        and isinstance(source, dict)
        and source.get("selected_root") == str(ROOT)
        and source.get("fallback_reason") == "requested_source_unavailable"
    )
    checks["doctor_classifies_fixture_paths_without_production_false_positive"] = (
        isinstance(path_policy, dict)
        and path_policy.get("production_hardcoded_path_count") == 0
        and int(path_policy.get("fixture_hardcoded_path_count", 0)) >= 1
        and not doctor_stderr
    )
    checks["doctor_validates_modern_and_legacy_mcp_protocols"] = (
        isinstance(mcp_probe, dict)
        and mcp_probe.get("protocol_version") == "2026-07-28"
        and isinstance(mcp_probe.get("modern"), dict)
        and mcp_probe["modern"].get("ok") is True
        and isinstance(mcp_probe.get("legacy"), dict)
        and mcp_probe["legacy"].get("ok") is True
        and mcp_probe.get("tool_count") == 5
    )
    checks["doctor_includes_codex_role_consistency"] = (
        isinstance(roles, dict)
        and roles.get("ok") is True
    )

    debug_code, debug_envelope, debug_stderr = _run("debug", "--source-root", str(ROOT))
    debug = _nested(debug_envelope)
    checks["debug_alias_exposes_runtime_and_source_trace"] = (
        debug_code == 0
        and debug_envelope.get("ok") is True
        and isinstance(debug.get("runtime"), dict)
        and isinstance(debug.get("source_selection"), dict)
        and debug.get("private_body_accessed") is False
        and not debug_stderr
    )

    with tempfile.TemporaryDirectory(prefix="decretum-fix-plan-") as raw:
        home = Path(raw) / "home"
        fix_code, fix_envelope, fix_stderr = _run(
            "fix",
            "update",
            "--source-root",
            str(ROOT),
            "--home-root",
            str(home),
        )
        fix = _nested(fix_envelope)
        checks["fix_update_defaults_to_read_only_projection_plan"] = (
            fix_code == 0
            and fix_envelope.get("ok") is True
            and fix.get("operation") == "update"
            and fix.get("write") is False
            and isinstance(fix.get("result"), dict)
            and fix["result"].get("status") == "PLANNED"
            and not home.exists()
            and not fix_stderr
        )

    rollback_code, rollback_envelope, rollback_stderr = _run("fix", "rollback")
    rollback = _nested(rollback_envelope)
    checks["fix_rollback_requires_explicit_backup"] = (
        rollback_code == 2
        and rollback_envelope.get("ok") is False
        and rollback_envelope.get("status") == "BLOCKED"
        and rollback.get("status") == "BLOCKED"
        and rollback.get("write") is False
        and not rollback_stderr
    )

    receipt_code, receipt_envelope, receipt_stderr = _run(
        "fix", "rollback", "--receipt", str(ROOT / "__missing_migration_receipt__.json")
    )
    receipt = _nested(receipt_envelope)
    checks["fix_rollback_receipt_routes_to_legacy_api"] = (
        receipt_code == 2
        and receipt_envelope.get("status") == "BLOCKED"
        and receipt.get("operation") == "rollback"
        and isinstance(receipt.get("result"), dict)
        and receipt["result"].get("schema") == "court.legacy_skill_locator_migration.v1"
        and not receipt_stderr
    )

    return {
        "schema": SCHEMA,
        "ok": all(checks.values()),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="json")
    args = parser.parse_args(argv)
    result = evaluate()
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"DOCTOR_DEBUG_FIX_{result['status']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
