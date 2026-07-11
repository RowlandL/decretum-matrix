"""Functional smoke test for the superCC runtime path.

The default mode is a read-only audit: it verifies gate reporting, silent
supervisor status, dry-run dispatch behavior, and non-mutating side-effect
manifests without starting or closing office panes. Use ``--live-mutating`` for
the older live turn-start/launch/closeout smoke.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ENSURE = ROOT / "scripts" / "ensure_supercc_court.py"
WATCHDOG = ROOT / "scripts" / "supercc_watchdog.py"
OPEN_DECREE_ROLES = {"taizi", "zhongshu", "menxia", "shangshu"}
POST_CLOSEOUT_IDLE_ROLES = {
    "taizi",
    "zhongshu",
    "menxia",
    "shangshu",
    "libu-hr",
    "hubu",
    "libu",
    "bingbu",
    "xingbu",
    "gongbu",
    "shiguan",
}
SUCCESS_DISPATCH_CHANNELS = {
    "NATIVE_DOUBLE_ENTER_VISIBLE",
}
STRUCTURED_BLOCK_CHANNELS = {
    "FAILED_OFFICE_UNIQUENESS_GATE",
    "FAILED_VISIBLE_PANE_GATE",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_json(workspace: Path, args: list[str], *, timeout: int = 180, allowed_returncodes: set[int] | None = None) -> dict[str, object]:
    command = [
        sys.executable,
        str(ENSURE),
        "--workspace",
        str(workspace),
        "--no-auto-install-deps",
        "--format",
        "json",
        *args,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    allowed = allowed_returncodes or {0}
    if result.returncode not in allowed:
        raise AssertionError(
            "command failed:\n"
            + " ".join(command)
            + f"\nexit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"expected JSON output from {' '.join(command)}\n{result.stdout}") from exc


def run_watchdog(workspace: Path) -> dict[str, object]:
    command = [
        sys.executable,
        str(WATCHDOG),
        "--workspace",
        str(workspace),
        "--roles",
        "visible-core",
        "--no-apply",
        "--dry-run",
        "--format",
        "json",
        "--max-iterations",
        "1",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if result.returncode not in {0, 2}:
        raise AssertionError(f"watchdog command failed exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}")
    return json.loads(result.stdout)


def assert_dispatch(payload: dict[str, object]) -> None:
    require(
        payload.get("dispatch_delivery_channel") in SUCCESS_DISPATCH_CHANNELS,
        "dispatch did not use native double-enter visible channel or legacy alias",
    )
    require(payload.get("post_dispatch_physical_enter_delay_seconds") == 1.0, "dispatch missing one-second physical Enter evidence")
    native = payload.get("native_enter_dispatch")
    require(isinstance(native, dict), "native_enter_dispatch missing")
    commands = native.get("commands")
    require(isinstance(commands, list) and len(commands) == 4, "dry-run native dispatch must plan write, Enter, sleep, Enter")
    require(native.get("squad_delivery_order") == "SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER", "dispatch must queue squad task/send before native Enter")
    require(native.get("native_enter_payload_kind") == "SUPERCC_SQUAD_RECEIVE_COMMAND", "native Enter payload must be the superCC squad receive command")
    command_text = " ".join(str(part) for part in commands[0])
    require(("supercc-squad" in command_text or "supercc_squad.py" in command_text) and "receive" in command_text, "native dispatch must enter the receive wrapper command")
    require(commands[1][-1] == "13" and commands[3][-1] == "13", "native dispatch must use carriage-return physical Enter byte 13")
    require(commands[2] == ["sleep", "1s"], "dry-run native dispatch must sleep one second before the second Enter")
    require(payload.get("squad_evidence"), "dispatch missing squad mirror evidence")


def run_functional(workspace: Path) -> dict[str, object]:
    check_result = run_json(workspace, ["--check-only"], allowed_returncodes={0, 2})

    if not check_result.get("passed"):
        launch_result = run_json(
            workspace,
            [
                "--launch-visible-core",
                "--reclaim-existing",
                "--codex-start-stagger",
                "2",
                "--codex-start-jitter",
                "0",
                "--codex-retry-attempts",
                "1",
                "--launch-delay",
                "0.5",
            ],
        )
        require(launch_result.get("ok"), "failed to prepare visible-core")

    turn_start = run_json(workspace, ["--turn-start", "visible-core", "--reclaim-existing"])
    require(bool(turn_start.get("ok")), "turn-start did not complete successfully")
    actions = turn_start.get("actions")
    require(isinstance(actions, list), "turn-start missing action evidence")
    wake_actions = [
        action.get("native_turn_start_wake")
        for action in actions
        if isinstance(action, dict) and action.get("native_turn_start_wake")
    ]
    applied_side_effects = set((turn_start.get("side_effects") or {}).get("applied") or [])
    require(
        bool(wake_actions) or "native_wake_visible_departments" in applied_side_effects,
        "turn-start missing native wake evidence",
    )

    supervisor = run_watchdog(workspace)
    require(supervisor.get("silent_supervisor") is True, "supervisor did not report silent mode")
    require(supervisor.get("legacy_patrol_visible_pane") == "disabled", "legacy visible monitor pane was not disabled")
    require(supervisor.get("watchdog_no_visible_window") is True, "supervisor must be non-popup/non-visible")
    require(supervisor.get("watchdog_daemon_stop") == "NOT_APPLICABLE", "read-only status pass must not require daemon stop")
    rows = supervisor.get("roles")
    require(isinstance(rows, list), "supervisor payload missing roles list")
    for role in OPEN_DECREE_ROLES:
        require(any(isinstance(row, dict) and row.get("role") == role for row in rows), f"supervisor missing role {role}")

    dispatch = run_json(
        workspace,
        [
            "--enter-dispatch",
            "--role",
            "zhongshu",
            "--calling-office",
            "taizi",
            "--dispatch-uid",
            "SUPERCC-FUNCTIONAL-ZHONGSHU",
            "--message",
            "functional probe only; no work required; confirm ENTER_DISPATCH shape",
            "--dry-run",
        ],
    )
    require(bool(dispatch.get("ok")), "dry-run ENTER_DISPATCH failed")
    assert_dispatch(dispatch)

    closeout = run_json(workspace, ["--closeout-silence"])
    require(bool(closeout.get("ok")), "closeout-silence failed")
    silenced = set(closeout.get("silenced", []))
    require(POST_CLOSEOUT_IDLE_ROLES <= silenced, "closeout did not silence all expected roles")

    return {
        "check_passed": check_result.get("passed"),
        "turn_start": {
            "visible_core": turn_start.get("supercc_visible_core_roles"),
        },
        "supervisor": {
            "silent_supervisor": supervisor.get("silent_supervisor"),
            "abnormal_count": len(supervisor.get("abnormal_roles") or []),
        },
        "dispatch": {
            "channel": dispatch.get("dispatch_delivery_channel"),
            "post_enter_delay": dispatch.get("post_dispatch_physical_enter_delay_seconds"),
        },
        "closeout": {
            "silenced_count": len(silenced),
        },
    }


def run_read_only_audit(workspace: Path) -> dict[str, object]:
    check_result = run_json(workspace, ["--check-only"], allowed_returncodes={0, 2})
    side_effects = check_result.get("side_effects") or {}
    require(side_effects.get("mutates_runtime") is False, "check-only must be non-mutating")
    show_delay = check_result.get("office_show_delay") or {}
    require(float(check_result.get("office_show_delay_seconds") or 0.0) <= 5.0, "office show delay exceeded five seconds")
    require(show_delay.get("first_office_delay_seconds") == 0.0, "first office retained an artificial cooldown")
    require(check_result.get("ordinary_spawn_delay_seconds") == 0.0, "ordinary spawned agents inherited presentation delay")
    require(check_result.get("provider_rate_limit_state") == "queued_rate_limit", "provider queue state was not separated")
    require(check_result.get("visible_display_gate") in {"PASSED", "runtime_degraded"}, "check-only missing display gate")
    require(check_result.get("office_client_gate") in {"PASSED", "runtime_degraded"}, "check-only missing office client gate")

    capped_alias = run_json(
        workspace,
        ["--check-only", "--codex-start-stagger", "9"],
        allowed_returncodes={0, 2},
    )
    alias_delay = capped_alias.get("office_show_delay") or {}
    require(alias_delay.get("effective_interval_seconds") == 5.0, "deprecated stagger alias was not capped")
    require(any("capped_to=5" in str(item) for item in alias_delay.get("warnings") or []), "capped alias warning missing")

    entry_check = run_json(workspace, ["--super-entry", "check"], allowed_returncodes={0, 2})
    entry_side_effects = entry_check.get("side_effects") or {}
    require(entry_side_effects.get("mutates_runtime") is False, "super-entry check must be non-mutating")
    require(entry_check.get("supercc_super_entry_policy"), "super-entry check missing policy evidence")

    supervisor = run_watchdog(workspace)
    require(supervisor.get("silent_supervisor") is True, "supervisor did not report silent mode")
    require(supervisor.get("legacy_patrol_visible_pane") == "disabled", "legacy visible monitor pane was not disabled")
    require(supervisor.get("watchdog_no_visible_window") is True, "supervisor must be non-popup/non-visible")

    dispatch = run_json(
        workspace,
        [
            "--enter-dispatch",
            "--role",
            "zhongshu",
            "--calling-office",
            "taizi",
            "--dispatch-uid",
            "SUPERCC-FUNCTIONAL-ZHONGSHU",
            "--message",
            "functional read-only probe only; no work required; confirm ENTER_DISPATCH shape",
            "--dry-run",
        ],
        allowed_returncodes={0, 2},
    )
    dispatch_side_effects = dispatch.get("side_effects") or {}
    require(dispatch_side_effects.get("mutates_runtime") is False, "dry-run dispatch must be non-mutating")
    if dispatch.get("ok"):
        assert_dispatch(dispatch)
    else:
        require(
            dispatch.get("dispatch_delivery_channel") in STRUCTURED_BLOCK_CHANNELS,
            "failed dry-run dispatch must preserve structured block evidence",
        )
        require(dispatch.get("dispatch_blocked") is True, "failed dry-run dispatch must be explicitly blocked")
        require(isinstance(dispatch.get("office_uniqueness_gate"), dict), "failed dry-run dispatch must preserve uniqueness-gate evidence")

    return {
        "mode": "read_only_audit",
        "check_passed": check_result.get("passed"),
        "supercc_env_gate": check_result.get("supercc_env_gate"),
        "super_entry_gate": entry_check.get("supercc_env_gate"),
        "office_show_delay_seconds": check_result.get("office_show_delay_seconds"),
        "ordinary_spawn_delay_seconds": check_result.get("ordinary_spawn_delay_seconds"),
        "supervisor": {
            "silent_supervisor": supervisor.get("silent_supervisor"),
            "abnormal_count": len(supervisor.get("abnormal_roles") or []),
        },
        "dispatch": {
            "ok": dispatch.get("ok"),
            "channel": dispatch.get("dispatch_delivery_channel"),
            "blocked": dispatch.get("dispatch_blocked"),
            "post_enter_delay": dispatch.get("post_dispatch_physical_enter_delay_seconds"),
        },
    }


def strict_passes(summary: dict[str, object]) -> bool:
    dispatch = summary.get("dispatch")
    dispatch_ok = isinstance(dispatch, dict) and dispatch.get("ok") is True
    supervisor = summary.get("supervisor")
    supervisor_ok = (
        isinstance(supervisor, dict)
        and supervisor.get("silent_supervisor") is True
        and int(supervisor.get("abnormal_count") or 0) == 0
    )
    return (
        summary.get("check_passed") is True
        and summary.get("supercc_env_gate") == "PASSED"
        and dispatch_ok
        and supervisor_ok
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=str(Path.home()), help="Workspace used for the live superCC command path.")
    parser.add_argument("--json", action="store_true", help="Print full JSON summary.")
    parser.add_argument("--rounds", type=int, default=1, help="Run the full functional smoke sequence this many times.")
    parser.add_argument("--live-mutating", action="store_true", help="Run the live launch/turn-start/dispatch/closeout path instead of the default read-only audit.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--diagnose", action="store_true", help="Diagnostic mode: return 0 when the read-only audit completes, even if the local runtime is degraded.")
    mode.add_argument("--strict", action="store_true", help="Strict mode: return nonzero unless the superCC environment and dry-run dispatch gates are fully ready.")
    args = parser.parse_args()
    try:
        rounds = max(1, args.rounds)
        runner = run_functional if args.live_mutating else run_read_only_audit
        summaries = [runner(Path(args.workspace).resolve()) for _ in range(rounds)]
        summary = {"rounds": rounds, "runs": summaries, **summaries[-1]}
    except (AssertionError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"SUPERCC_FUNCTIONAL_FAILED {exc}")
        return 1
    exit_policy = "strict" if args.strict else "diagnose"
    summary["exit_policy"] = exit_policy
    summary["strict_passed"] = strict_passes(summary)
    ok = bool(summary["strict_passed"]) if args.strict else True
    if args.json:
        print(json.dumps({"ok": ok, **summary}, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status = "SUPERCC_FUNCTIONAL_OK" if ok else "SUPERCC_FUNCTIONAL_STRICT_FAILED"
        print(
            f"{status} "
            f"exit_policy={exit_policy} "
            f"mode={summary.get('mode', 'live_mutating')} "
            f"rounds={summary['rounds']} "
            f"dispatch={summary['dispatch']['channel']} "
            f"post_enter_delay={summary['dispatch'].get('post_enter_delay', 'n/a')} "
            f"silent_supervisor={summary['supervisor']['silent_supervisor']} "
            f"strict_passed={summary['strict_passed']}"
        )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
