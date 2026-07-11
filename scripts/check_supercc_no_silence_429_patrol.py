"""Regression checks for superCC no-silence, 429 ladder, and silent supervision."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def legacy_term(*parts: str) -> str:
    return "_".join(parts)


LEGACY_FIELD_TERMS = [
    legacy_term("patrol", "status", "table", "markdown"),
    legacy_term("patrol", "status", "table", "rendered"),
    legacy_term("gum", "status", "render", "policy"),
    legacy_term("patrol", "agent", "duty", "dispatch"),
    legacy_term("jiancha", "bidirectional", "recovery"),
    "visible " + "patrol table",
]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require_terms(path: str, terms: list[str]) -> None:
    text = read(path)
    missing = [term for term in terms if term not in text]
    if missing:
        raise AssertionError(f"{path} missing terms: {missing}")


def reject_terms(path: str, terms: list[str]) -> None:
    text = read(path)
    found = [term for term in terms if term in text]
    if found:
        raise AssertionError(f"{path} still has forbidden terms: {found}")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_source_terms() -> None:
    default_terms = [
        "taizi_no_silence",
        "three_departments_no_silence",
        "rate_limit_wake_hierarchy",
        "taizi_stale_explanation",
        "closeout_silence_policy",
        "idle_receive",
        "noncurrent_inactive_pane_cleanup",
        "direct_superior_source",
        "post_dispatch_physical_enter_delay_seconds",
        "six_ministry_step_plan_policy",
        "no_silence_roles",
    ]
    require_terms(
        "SKILL.md",
        [
            "Core Metadata Index",
            "Reference Index",
            "Token Three-Level Optimization",
            "Request pressure is rate-bounded",
            "court-startup-authority.md",
            "court-state-runtime-agents.md",
            "court-offices-dispatch.md",
            "court-closeout-validation.md",
            "supercc_watchdog.py",
            "watchdog_daemon_stop",
            "cli_probe",
        ],
    )
    for path in (
        "references/court-startup-authority.md",
        "references/court-state-runtime-agents.md",
        "references/court-offices-dispatch.md",
        "references/court-closeout-validation.md",
    ):
        require_terms(path, default_terms)
    require_terms(
        "scripts/ensure_supercc_court.py",
        [term for term in default_terms if term != "taizi_stale_explanation"],
    )

    memorial_terms = [
        "silent_supervisor",
        "supercc_watchdog",
        "watchdog_process",
        "watchdog_log_jsonl",
        "watchdog_pid_file",
        "watchdog_daemon_start",
        "watchdog_daemon_stop",
        "watchdog_no_visible_window",
        "legacy_patrol_visible_pane",
        "cli_probe",
    ]
    for path in (
        "SKILL.md",
        "references/court-closeout-validation.md",
        "references/court-supercc-runtime-selection.md",
    ):
        require_terms(path, memorial_terms)
    require_terms(
        "scripts/supercc_watchdog.py",
        [
            "silent_supervisor",
            "supercc_watchdog",
            "watchdog_process",
            "watchdog_log_jsonl",
            "watchdog_pid_file",
            "watchdog_daemon_start",
            "watchdog_daemon_stop",
            "watchdog_no_visible_window",
            "watchdog_actions",
            "watchdog_abnormal_roles",
            "legacy_patrol_visible_pane",
        ],
    )

    for path in (
        "SKILL.md",
        "references/court-closeout-validation.md",
        "references/court-state-runtime-agents.md",
        "references/court-supercc-runtime-selection.md",
        "references/supercc-phase-cycling-model.md",
    ):
        reject_terms(
            path,
            LEGACY_FIELD_TERMS,
        )


def check_launcher_contract() -> None:
    sys.path.insert(0, str(SCRIPTS))
    ensure_supercc_court = load_module("ensure_supercc_court_no_silence_test", SCRIPTS / "ensure_supercc_court.py")
    supercc_watchdog = load_module("supercc_watchdog_no_silence_test", SCRIPTS / "supercc_watchdog.py")

    expected_no_silence = ("taizi", "zhongshu", "menxia", "shangshu")
    if tuple(ensure_supercc_court.NO_SILENCE_ROLES) != expected_no_silence:
        raise AssertionError(f"NO_SILENCE_ROLES drifted: {ensure_supercc_court.NO_SILENCE_ROLES!r}")
    if "patrol-inspector" in ensure_supercc_court.SUPERCC_VISIBLE_CORE_OFFICES:
        raise AssertionError("routine visible core must not include patrol-inspector")
    if "taizi" not in ensure_supercc_court.STATUS_OFFICES:
        raise AssertionError(f"STATUS_OFFICES must include taizi: {ensure_supercc_court.STATUS_OFFICES!r}")
    if set(ensure_supercc_court.CLOSEOUT_SILENCE_ROLES) != (set(ensure_supercc_court.STATUS_OFFICES) - set(ensure_supercc_court.INSPECTION_OFFICES)):
        raise AssertionError("closeout silence roles must be every status role except legacy inspection identity")
    if ensure_supercc_court.inspector_enabled(argparse.Namespace(enable_inspector=True, skip_inspector=False)):
        raise AssertionError("legacy inspector must stay disabled even if deprecated flag is supplied")
    if ensure_supercc_court.SUPERCC_WATCHDOG_SCRIPT != "supercc_watchdog.py":
        raise AssertionError("silent supervisor script name drifted")

    hierarchy = ensure_supercc_court.RATE_LIMIT_WAKE_HIERARCHY
    for key in ("taizi", "three_departments", "ministries", "final_review"):
        if key not in hierarchy:
            raise AssertionError(f"rate_limit_wake_hierarchy missing {key!r}")

    fake_check = {
        "squad": {
            "agents_json": [
                {
                    "id": "gongbu",
                    "last_seen": "1970-01-01T00:00:00+00:00",
                    "status": "active",
                }
            ]
        },
        "zellij": {
            "env": {"ZELLIJ_SESSION_NAME": "TEST"},
            "panes_list": [],
        },
    }
    cleanup = ensure_supercc_court.noncurrent_inactive_cleanup_evaluator(
        ROOT,
        fake_check,
        ("gongbu",),
        inactive_age_seconds=1.0,
        include_task_probe=False,
    )
    if "noncurrent_inactive_pane_cleanup" not in cleanup:
        raise AssertionError("cleanup evaluator missing noncurrent_inactive_pane_cleanup")

    args = argparse.Namespace(
        workspace=str(ROOT),
        roles="visible-core",
        zellij_session=None,
        apply=False,
        no_apply=True,
        dry_run=True,
        force=False,
        max_actions=1,
        stale_seconds=1.0,
        log_jsonl=None,
    )
    command = supercc_watchdog.build_recovery_command(
        args,
        {"role": "zhongshu", "reasons": ["rate_limit_signal"]},
    )
    joined = json.dumps(command, ensure_ascii=False)
    if "ensure_supercc_court.py" not in joined or "--turn-start" not in command:
        raise AssertionError(f"watchdog recovery command drifted: {command}")

    daemon_args = argparse.Namespace(
        workspace=str(ROOT),
        roles="visible-core",
        zellij_session=None,
        apply=False,
        no_apply=True,
        dry_run=True,
        force=False,
        max_actions=1,
        max_iterations=1,
        interval=1.0,
        log_jsonl=str(Path(tempfile.gettempdir()) / "supercc-watchdog-test.jsonl"),
    )
    daemon_command = supercc_watchdog.hidden_daemon_command(daemon_args)
    daemon_text = json.dumps(daemon_command, ensure_ascii=False)
    for term in ("supercc_watchdog.py", "--watch", "--quiet", "--log-jsonl"):
        if term not in daemon_text:
            raise AssertionError(f"hidden daemon command missing {term!r}: {daemon_command}")


def main() -> int:
    check_source_terms()
    check_launcher_contract()
    print("SUPERCC_NO_SILENCE_429_SILENT_SUPERVISOR_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
