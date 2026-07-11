"""Static regression checks for Claude/generic-CLI superCC hard gates.

The checks avoid private Claude logs. They verify the generated skill semantics
that should keep Claude Code from copying stale bare squad commands, host-specific
cd/path snippets, or controller-side zellij typing into office panes.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


HOST_PATH_RE = re.compile(
    r"(?:C:\\Users\\[^\\\s]+|/mnt/[a-z]/Users/[^/\s]+|/[a-z]/Users/[^/\s]+|/Users/(?:Administrator|32893)\b)",
    re.IGNORECASE,
)


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(condition: bool, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": bool(condition), "message": message, "details": details or {}}


def bare_squad_receive_pattern(role: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!supercc-)squad\s+receive\s+{re.escape(role)}\s+--json\b")


def bad_path_matches(text: str) -> list[str]:
    return sorted({match.group(0) for match in HOST_PATH_RE.finditer(text)})


def launch_command_for_claude(launcher: Any, role: str, workspace: Path) -> list[str]:
    return launcher.build_office_launch_command(
        role,
        workspace,
        court_code=None,
        office_client="claude",
        hermescli_command="hermes",
        claude_command="claude",
        office_client_command=None,
        office_client_args=[],
        office_client_prompt_mode="argument",
        zellij_session="static-test-session",
        ministry_mode="silent",
        dangerous_yolo=False,
        codex_start_delay=0,
        codex_retry_attempts=1,
        codex_retry_backoff_base=300,
        layout_direction="right",
    )


def decoded_encoded_command(command: list[str]) -> str:
    try:
        index = command.index("-EncodedCommand")
        encoded = command[index + 1]
    except (ValueError, IndexError):
        return ""
    try:
        return base64.b64decode(encoded).decode("utf-16le", errors="replace")
    except Exception:
        return ""


def run_checks() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    launcher = load_module("ensure_supercc_court_under_claude_gate_test", root / "scripts" / "ensure_supercc_court.py")
    workspace = Path.home()
    role = "zhongshu"
    checks: list[dict[str, Any]] = []

    shell_contract = launcher.shell_contract_block(role, workspace)
    checks.append(
        check(
            "supercc-squad.sh receive zhongshu --json" in shell_contract
            and "supercc-squad.ps1" in shell_contract
            and "supercc-squad.cmd" in shell_contract
            and "Never run bare squad commands directly" in shell_contract
            and "older transcripts" in shell_contract
            and "Controller/main panes" in shell_contract,
            "shell contract names all wrappers and rejects stale direct-command drift",
            {"shell_contract": shell_contract},
        )
    )

    prompt = launcher.office_prompt(role, role, workspace, None, office_client="claude")
    checks.append(
        check(
            "runtime_client=claude" in prompt
            and "task_workspace_env=SUPERCC_TASK_WORKSPACE" in prompt
            and "local superCC squad wrapper" in prompt
            and "ignore stale examples" in prompt
            and "older transcripts" in prompt,
            "Claude office prompt carries wrapper contract and drift guard",
        )
    )
    checks.append(
        check(
            bare_squad_receive_pattern(role).search(prompt) is None,
            "Claude office prompt does not instruct a bare squad receive",
            {"matches": bare_squad_receive_pattern(role).findall(prompt)},
        )
    )
    checks.append(
        check(
            not bad_path_matches(prompt),
            "Claude office prompt avoids host-specific workspace paths",
            {"matches": bad_path_matches(prompt)},
        )
    )

    dossier = launcher.office_dossier_text(role)
    checks.append(
        check(
            "## Shell Contract" in dossier
            and "supercc-squad.sh receive zhongshu --json" in dossier
            and "Use the receive command from Shell Contract" in dossier
            and "older transcripts" in dossier,
            "role dossier embeds wrapper contract and stale-context guard",
        )
    )
    checks.append(
        check(
            bare_squad_receive_pattern(role).search(dossier) is None
            and "loaded by Codex" not in dossier
            and not bad_path_matches(dossier),
            "role dossier has no legacy direct receive or host-specific bootstrap text",
            {
                "bare_receive_matches": bare_squad_receive_pattern(role).findall(dossier),
                "host_path_matches": bad_path_matches(dossier),
                "loaded_by_codex": "loaded by Codex" in dossier,
            },
        )
    )

    launch_command = launch_command_for_claude(launcher, role, workspace)
    launch_text = "\n".join(str(part) for part in launch_command)
    launch_script = decoded_encoded_command(launch_command)
    combined_launch_text = launch_text + "\n" + launch_script
    checks.append(
        check(
            "--add-dir" in combined_launch_text
            and "--append-system-prompt" in combined_launch_text
            and str(launcher.office_dossier_dir(role)) in combined_launch_text
            and str(workspace) in combined_launch_text,
            "Claude launch command starts from role dossier and allowlists task workspace",
            {"command": launch_command, "decoded_script_present": bool(launch_script)},
        )
    )
    checks.append(
        check(
            launcher.runtime_process_cwd_for_client("claude", role, workspace) == launcher.office_dossier_dir(role),
            "Claude process cwd resolves to the role dossier directory",
        )
    )
    checks.append(
        check(
            tuple(launcher.SUPERCC_VISIBLE_CORE_OFFICES) == tuple(launcher.THREE_OFFICES)
            and "patrol-inspector" not in launcher.SUPERCC_VISIBLE_CORE_OFFICES
            and tuple(launcher.MONITOR_NO_SILENCE_ROLES) == tuple(launcher.NO_SILENCE_ROLES),
            "routine visible core is Taizi current pane plus three departments; patrol is explicit diagnostic only",
            {
                "visible_core": list(launcher.SUPERCC_VISIBLE_CORE_OFFICES),
                "monitor_no_silence_roles": list(launcher.MONITOR_NO_SILENCE_ROLES),
            },
        )
    )

    runtime_ref = (root / "references" / "court-supercc-runtime-selection.md").read_text(encoding="utf-8")
    platform_ref = (root / "references" / "court-host-platform-pitfalls.md").read_text(encoding="utf-8")
    skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
    checks.append(
        check(
            "older role prompts" in runtime_ref
            and "controller-side `zellij write-chars`" in runtime_ref
            and "current role dossier and generated shell contract supersede" in runtime_ref
            and "transcript as stale drift evidence" in platform_ref
            and "Old Claude/Codex logs" in skill_text,
            "governing references and SKILL.md preserve Claude drift guard semantics",
        )
    )

    return {
        "ok": all(item["ok"] for item in checks),
        "schema": "court.supercc.claude_hard_gates.v1",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_checks()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print(f"SUPERCC_CLAUDE_HARD_GATES_OK checks={len(result['checks'])}")
    else:
        print("SUPERCC_CLAUDE_HARD_GATES_FAILED")
        for item in result["checks"]:
            if not item["ok"]:
                print(json.dumps(item, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
