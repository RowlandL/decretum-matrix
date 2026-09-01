"""Regression checks for superCC super-entry and generic CLI routing."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ensure_supercc_court as court  # noqa: E402
import supercc_watchdog as watchdog  # noqa: E402


def base_args(**overrides: object) -> argparse.Namespace:
    values = {
        "office_client": "auto",
        "requested_office_client": "auto",
        "office_client_selection_source": "test",
        "office_client_selection_signals": [],
        "office_client_command": None,
        "office_client_arg": [],
        "office_client_args": None,
        "office_client_prompt_mode": "argument",
        "office_client_map": [],
        "office_client_command_map": [],
        "office_client_args_map": [],
        "office_client_prompt_mode_map": [],
        "hermescli_command": "hermes",
        "claude_command": "claude",
        "zellij_session": None,
        "workspace": str(ROOT),
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def check_per_office_map() -> None:
    args = base_args(
        office_client="codex",
        requested_office_client="codex",
        office_client_map=["zhongshu=claude,menxia=cli,shangshu=hermescli"],
        office_client_command_map=["menxia=python"],
        office_client_args_map=["menxia=--version"],
        office_client_prompt_mode_map=["menxia=stdin"],
    )
    court.normalize_office_client_maps(args)
    if court.office_client_for_role(args, "zhongshu") != "claude":
        raise AssertionError("zhongshu role map did not resolve to claude")
    if court.office_client_for_role(args, "menxia") != "cli":
        raise AssertionError("menxia role map did not resolve to generic cli")
    if court.office_client_command_for_role(args, "menxia") != "python":
        raise AssertionError("generic cli command map did not resolve")
    if court.office_client_extra_args_for_role(args, "menxia") != ["--version"]:
        raise AssertionError("generic cli args map did not resolve")
    if court.office_client_prompt_mode_for_role(args, "menxia") != "stdin":
        raise AssertionError("generic cli prompt mode map did not resolve")
    plan = court.office_client_role_plan(args, court.THREE_OFFICES)
    if plan["menxia"]["selection"] != "role_map":
        raise AssertionError(f"expected role_map selection evidence: {plan}")
    future_args = base_args(
        office_client="codex",
        requested_office_client="codex",
        office_client_map=["zhongshu=futureagent"],
    )
    court.normalize_office_client_maps(future_args)
    if court.office_client_for_role(future_args, "zhongshu") != "cli":
        raise AssertionError("unknown per-office client must normalize to generic cli")
    if court.office_client_command_for_role(future_args, "zhongshu") != "futureagent":
        raise AssertionError("unknown per-office client must become the generic cli command")


def check_generic_cli_probe() -> None:
    future_args = base_args(office_client="futureagent")
    court.resolve_office_client_args(future_args)
    if future_args.office_client != "cli" or future_args.office_client_command != "futureagent":
        raise AssertionError(f"unknown --office-client must become probed generic cli: {future_args}")

    available = court.check_office_client_values(
        "cli",
        "hermes",
        ROOT,
        office_client_command="python",
        office_client_args=["--version"],
        requested_office_client="cli",
    )
    if not available["available"]:
        raise AssertionError(f"generic CLI should pass command availability gate: {available}")
    probe = available.get("cli_probe") or {}
    if not probe.get("known_from_probe"):
        raise AssertionError(f"generic CLI probe must turn unknown tool into probed evidence: {available}")
    if available["squad_client"] is not None:
        raise AssertionError("generic CLI must not fabricate a squad client enum")


def check_launch_command_uses_role_client() -> None:
    command = court.build_office_launch_command(
        "zhongshu",
        ROOT,
        court_code=None,
        office_client="cli",
        hermescli_command="hermes",
        claude_command="claude",
        office_client_command="python",
        office_client_args=["--version"],
        office_client_prompt_mode="argument",
        zellij_session="TEST",
        ministry_mode="silent",
        dangerous_yolo=False,
        codex_start_delay=0,
        codex_retry_attempts=1,
        codex_retry_backoff_base=300,
        layout_direction="right",
    )
    text = " ".join(str(part) for part in command)
    for term in ("zellij", "powershell.exe", "AZS Zhongshu #0001"):
        if term not in text:
            raise AssertionError(f"launch command missing {term!r}: {text[:500]}")


def check_watchdog_classifier() -> None:
    fake_check = {
        "squad": {"agents_json": []},
        "zellij": {"panes_list": []},
    }
    fake_state = {
        "ok": True,
        "roles": {
            "zhongshu": {
                "mode": "429",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        },
    }
    row = watchdog.classify_role(
        "zhongshu",
        check=fake_check,
        state=fake_state,
        stale_seconds=1.0,
        now=1783300000.0,
    )
    for reason in ("missing_visible_pane", "missing_active_squad_identity", "abnormal_state_mode", "rate_limit_signal"):
        if reason not in row["reasons"]:
            raise AssertionError(f"watchdog row missing {reason!r}: {row}")
    if row["recommended_action"] != "turn_start_wake_visible_core":
        raise AssertionError(f"unexpected watchdog action: {row}")


def main() -> int:
    check_per_office_map()
    check_generic_cli_probe()
    check_launch_command_uses_role_client()
    check_watchdog_classifier()
    print("SUPERCC_SUPER_ENTRY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
