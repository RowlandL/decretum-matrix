"""Validate the optional advisory Git hook boundary."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "court_hooks_advisory.py"
CODEX_HOOK = ROOT / "scripts" / "court_codex_hook.py"
PLUGIN_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
HOOKS_MANIFEST = ROOT / "hooks" / "claude-codex-hooks.json"


def _run_report(*args: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        cwd=ROOT,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    report = json.loads(completed.stdout)
    if not isinstance(report, dict):
        raise AssertionError("hooks_advisory_report_not_object")
    return report


def run() -> dict[str, object]:
    report = _run_report("--event", "post-commit", "--marker", "refresh-request")
    forbidden = set(report.get("forbidden_authority_actions", []))
    checks = [
        ("schema", report.get("schema") == "decretum.hooks_advisory.v1"),
        ("advisory_only", report.get("advisory_only") is True),
        ("not_authoritative", report.get("authoritative_gate") is False),
        (
            "no_git_hook_install",
            report.get("installs_git_hook") is False
            and report.get("requires_core_hooks_path") is False,
        ),
        (
            "no_authority_writes",
            report.get("writes_closeout") is False
            and report.get("writes_memory") is False
            and report.get("writes_release") is False,
        ),
        ("marker_is_not_written", report.get("marker_write_enabled") is False),
        (
            "forbidden_authority_actions_explicit",
            {
                "archive_checkpoint",
                "closeout_identity",
                "memory_write",
                "release_or_publish",
                "menxia_verdict",
                "host_dispatch",
            }.issubset(forbidden),
        ),
        (
            "authority_path_preserved",
            report.get("authority_path") == "court_cli_or_runtime_receipt_only",
        ),
        (
            "codex_plugin_manifest_present",
            PLUGIN_MANIFEST.is_file()
            and json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8")).get("hooks")
            == "./hooks/claude-codex-hooks.json",
        ),
        (
            "codex_hooks_manifest_present",
            HOOKS_MANIFEST.is_file()
            and {"SessionStart", "UserPromptSubmit"}.issubset(
                json.loads(HOOKS_MANIFEST.read_text(encoding="utf-8")).get("hooks", {})
            ),
        ),
        (
            "codex_hook_is_advisory",
            CODEX_HOOK.is_file()
            and "advisory_only" in CODEX_HOOK.read_text(encoding="utf-8")
            and "archive-checkpoint" in CODEX_HOOK.read_text(encoding="utf-8"),
        ),
    ]
    return {
        "schema": "decretum.hooks_advisory_check.v1",
        "ok": all(ok for _, ok in checks),
        "checks": [{"name": name, "ok": ok} for name, ok in checks],
    }


def main() -> int:
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
