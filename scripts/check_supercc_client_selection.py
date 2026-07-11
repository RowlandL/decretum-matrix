"""Regression checks for the extracted superCC office-client selector."""

from __future__ import annotations

import argparse
import os
import sys

sys.dont_write_bytecode = True

from supercc_client_selection import (
    cli_source_signals,
    expand_office_selection,
    normalize_office_client_maps,
    office_client_command_for_role,
    office_client_for_role,
    office_client_role_plan,
    resolve_office_client_args,
)


def base_namespace() -> argparse.Namespace:
    return argparse.Namespace(
        office_client="codex",
        office_client_command=None,
        office_client_arg=[],
        office_client_args=None,
        office_client_prompt_mode="argument",
        office_client_map=[],
        office_client_command_map=[],
        office_client_args_map=[],
        office_client_prompt_mode_map=[],
    )


def main() -> int:
    assert expand_office_selection("three") == ("zhongshu", "menxia", "shangshu")
    assert expand_office_selection("ministries") == (
        "libu-hr",
        "hubu",
        "libu",
        "bingbu",
        "xingbu",
        "gongbu",
    )

    args = base_namespace()
    args.office_client_map = ["ministries=codex", "shiguan=claude-code", "menxia=my-new-cli"]
    args.office_client_command_map = ["menxia=C:/Tools/my-new-cli.exe"]
    args.office_client_args_map = ["menxia=--quiet --json"]
    args.office_client_prompt_mode_map = ["menxia=stdin"]
    normalize_office_client_maps(args)
    assert office_client_for_role(args, "xingbu") == "codex"
    assert office_client_for_role(args, "shiguan") == "claude"
    assert office_client_for_role(args, "menxia") == "cli"
    assert office_client_command_for_role(args, "menxia") == "C:/Tools/my-new-cli.exe"
    plan = office_client_role_plan(args, ["menxia", "xingbu", "shiguan"])
    assert plan["menxia"]["args"] == ["--quiet", "--json"]
    assert plan["menxia"]["prompt_mode"] == "stdin"
    assert plan["shiguan"]["office_client"] == "claude"

    explicit = base_namespace()
    explicit.office_client = "third-party-agent"
    resolve_office_client_args(explicit)
    assert explicit.office_client == "cli"
    assert explicit.office_client_command == "third-party-agent"
    assert explicit.office_client_selection_source == "explicit_argument_generic_client"

    saved = {name: os.environ.get(name) for name in ("CODEX_THREAD_ID", "ANTHROPIC_AUTH_TOKEN")}
    try:
        os.environ["CODEX_THREAD_ID"] = "test-codex-thread"
        os.environ["ANTHROPIC_AUTH_TOKEN"] = "test-present-but-not-current-runtime"
        mixed = cli_source_signals()
        assert mixed["office_client"] == "codex"
        assert mixed["source"] == "auto_current_cli_env_strong"
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    print("SUPERCC_CLIENT_SELECTION_SELF_TEST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
