

#!/usr/bin/env python3
"""Regression checks for the doctor, debug, and fix CLI aliases."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "court_cli.py"
SCHEMA = "decretum.doctor_debug_fix_check.v1"


def _run(
    *arguments: str, env: dict[str, str] | None = None,
) -> tuple[int, dict[str, object], str]:
    completed = subprocess.run(
        [sys.executable, "-B", str(CLI), "--format", "json", *arguments],
        cwd=ROOT,
        env=env,
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

    from checks.check_court_mcp_server import EXPECTED_TOOLS, _source_runtime_fixture

    fixture, home, server, env = _source_runtime_fixture()
    with fixture:
        home = home.resolve()
        codex_home = home / ".codex"
        env.update({
            "CODEX_HOME": str(codex_home),
            "COURT_SHARED_SHIGUAN_ROOT": str(home / "isolated shiguan"),
            "COURT_RUNTIME_ROOT": str(home / "isolated court runtime"),
        })
        # Relative entry exercises config-relative argv resolution.
        config = codex_home / "config.toml"
        config.parent.mkdir(parents=True)
        base_config = "[agents]\nmax_depth = 4\nmax_concurrent_threads_per_session = 16\n"
        config.write_text(base_config, encoding="utf-8")
        subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / "sync_codex_agents_from_profiles.py"), "--write"],
            cwd=ROOT, env=env, check=True, capture_output=True,
        )
        source_args = (
            "--source-root", str(missing_source), "--mapped-root", str(ROOT),
            "--home-root", str(home),
        )
        _, unconfigured, _ = _run("doctor", *source_args, env=env)
        checks["doctor_reports_unconfigured_mcp"] = (
            _nested(unconfigured)["mcp_configuration"]["status"] == "MISSING"
        )
        config.write_text(
            base_config + "\n[mcp_servers.decretum_matrix]\n"
            + f"command = {json.dumps(sys.executable, ensure_ascii=False)}\n"
            + f"args = {json.dumps(['-B', Path(os.path.relpath(server, codex_home)).as_posix()], ensure_ascii=False)}\n",
            encoding="utf-8",
        )
        # Parent HOME differs from --home-root, so the child must use the
        # requested host's binding rather than the invoking user's binding.
        invoker = str(home.parent / "invoker")
        _, selected_home_probe, _ = _run(
            "doctor", *source_args, env={**env, "HOME": invoker, "USERPROFILE": invoker},
        )
        checks["doctor_probes_selected_home_binding"] = (
            _nested(selected_home_probe)["mcp_configuration"]["runtime_probe"]["ok"] is True
        )
        doctor_code, doctor_envelope, doctor_stderr = _run("doctor", *source_args, env=env)
        doctor = _nested(doctor_envelope)
        # File symlinks may be disabled by host policy on Windows. Exercise
        # the same entry through a link wherever the OS allows creating one.
        link = codex_home / "linked MCP" / server.name
        link.parent.mkdir()
        try:
            link.symlink_to(server)
        except (NotImplementedError, OSError):
            pass
        else:
            config.write_text(
                base_config + "\n[mcp_servers.decretum_matrix]\n"
                + f"command = {json.dumps(sys.executable, ensure_ascii=False)}\n"
                + f"args = {json.dumps(['-B', Path(os.path.relpath(link, codex_home)).as_posix()], ensure_ascii=False)}\n",
                encoding="utf-8",
            )
            _, through_link, _ = _run("doctor", *source_args, env=env)
            checks["doctor_accepts_linked_bound_mcp_entry"] = (
                _nested(through_link)["mcp_configuration"]["runtime_probe"]["ok"] is True
            )

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
        and mcp_probe.get("tool_count") == len(EXPECTED_TOOLS)
        and mcp_probe["modern"].get("tool_names") == sorted(EXPECTED_TOOLS)
        and mcp_probe["legacy"].get("tool_names") == sorted(EXPECTED_TOOLS)
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
        sandbox = Path(raw).resolve()
        home = sandbox / "isolated home"
        npm_prefix = sandbox / "isolated npm"
        plan_args = (
            "--source-root", str(ROOT), "--home-root", str(home),
            "--npm-prefix", str(npm_prefix),
        )
        plans = []
        for entry in (("fix", "update"), ("install", "fix", "update")):
            fix_code, fix_envelope, fix_stderr = _run(*entry, *plan_args)
            fix = _nested(fix_envelope)
            result = fix.get("result")
            plans.append(
                fix_code == 0
                and fix_envelope.get("ok") is True
                and fix.get("operation") == "update"
                and fix.get("write") is False
                and isinstance(result, dict)
                and result.get("status") == "PLANNED"
                and result.get("target_classes") == ["shared_agents", "codex"]
                and result.get("codex_agent_roles", {}).get("mode") == "dry-run"
                and "installation_binding" not in result
                and "install_receipt" not in result
                and not home.exists()
                and not npm_prefix.exists()
                and not fix_stderr
            )
        checks["fix_update_defaults_to_read_only_projection_plan"] = all(plans)
        receipt_code, receipt_envelope, _ = _run(
            "fix", "update", *plan_args, "--candidate-receipt", str(sandbox / "missing.json"),
        )
        checks["fix_update_does_not_ignore_incomplete_candidate"] = (
            receipt_code == 2
            and _nested(receipt_envelope).get("result", {}).get("reason") == "candidate_package_required"
            and not home.exists()
            and not npm_prefix.exists()
        )
        apply_code, apply_envelope, apply_stderr = _run(
            "fix", "update", *plan_args, "--caller-cwd", str(sandbox), "--apply",
        )
        checks["fix_update_apply_still_requires_candidate"] = (
            apply_code == 2
            and apply_envelope.get("ok") is False
            and _nested(apply_envelope).get("result", {}).get("reason") == "candidate_package_required"
            and not (home / ".agents" / "skills").exists()
            and not (home / ".codex").exists()
            and not npm_prefix.exists()
            and not apply_stderr
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

    # Windows path limit: the atomic temporary name must stay short even when the
    # event directory is already deep. The final event name and schema stay exact,
    # consecutive events must not overwrite each other and no temporary is left.
    import court_diagnostics

    with tempfile.TemporaryDirectory(prefix="court-deep-events-") as deep_root:
        event_dir = Path(deep_root) / court_diagnostics.NAME / "fix-current-thread"
        # Grow the fixture with a single filler segment so the event directory is
        # about 180 characters without overshooting the Windows limit for the
        # final event file (~241 characters).
        filler = 180 - len(str(event_dir)) - 1
        if filler > 0:
            event_dir = Path(deep_root) / ("s" * filler) / court_diagnostics.NAME / "fix-current-thread"
        deep_base = event_dir.parents[1]
        event_dir.mkdir(parents=True, exist_ok=True)
        deep_event_dir_length = len(str(event_dir))
        original_audit_base = court_diagnostics._audit_base
        court_diagnostics._audit_base = lambda: (deep_base, "fixture_deep_event_path")
        try:
            first = court_diagnostics.write_audit_event(
                task="fix-current-thread", operation="fixture", phase="intent", status="started", payload={"n": 1}
            )
            second = court_diagnostics.write_audit_event(
                task="fix-current-thread", operation="fixture", phase="result", status="succeeded", payload={"n": 2}
            )
        finally:
            court_diagnostics._audit_base = original_audit_base
        first_body = json.loads(Path(first["path"]).read_text(encoding="utf-8"))
        second_body = json.loads(Path(second["path"]).read_text(encoding="utf-8"))
        leftovers = [entry.name for entry in Path(first["path"]).parent.iterdir() if entry.name.startswith(".")]
        final_path_length = len(first["path"])
    checks["deep_event_path_atomic_write_succeeds"] = (
        170 <= deep_event_dir_length <= 200
        and final_path_length < 250
        and first_body["schema"] == "workspace.operation_event.v1"
        and first_body["event_id"] != second_body["event_id"]
        and first_body["phase"] == "intent"
        and first_body["status"] == "started"
        and second_body["phase"] == "result"
        and second_body["status"] == "succeeded"
        and first_body["payload"]["n"] == 1
        and second_body["payload"]["n"] == 2
        and not leftovers
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

