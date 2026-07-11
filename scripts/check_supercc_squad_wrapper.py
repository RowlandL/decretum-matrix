"""Check portable superCC squad wrapper behavior without mutating squad state."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(condition: bool, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": bool(condition), "message": message, "details": details or {}}


def run_checks() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    wrapper = load_module("supercc_squad_under_test", root / "scripts" / "supercc_squad.py")
    launcher = load_module("ensure_supercc_court_under_test", root / "scripts" / "ensure_supercc_court.py")

    checks: list[dict[str, Any]] = []

    parsed = wrapper.parse_wrapper_args(
        ["--supercc-print-command", "--supercc-squad-command", "python fake.py", "--", "receive", "menxia", "--json"]
    )
    checks.append(
        check(
            parsed == (True, "python fake.py", ["receive", "menxia", "--json"]),
            "parse_wrapper_args handles wrapper options before passthrough",
            {"parsed": parsed},
        )
    )

    split = wrapper.split_command('python -c "import sys;sys.exit(0)"')
    checks.append(
        check(
            split == ["python", "-c", "import sys;sys.exit(0)"],
            "split_command removes grouping quotes for executable command overrides",
            {"split": split},
        )
    )

    original = (wrapper.is_wsl, wrapper.is_msys, wrapper.is_cygwin, wrapper.shutil.which, wrapper.os.name)
    try:
        wrapper.os.name = "posix"
        wrapper.shutil.which = lambda _name: None
        wrapper.is_wsl = lambda: True
        wrapper.is_msys = lambda: False
        wrapper.is_cygwin = lambda: False
        checks.append(
            check(
                wrapper.convert_windows_path(r"C:\Tools\bin\squad.exe") == "/mnt/c/Tools/bin/squad.exe",
                "convert_windows_path falls back to WSL mount syntax",
            )
        )
        wrapper.is_wsl = lambda: False
        wrapper.is_msys = lambda: True
        checks.append(
            check(
                wrapper.convert_windows_path(r"C:\Tools\bin\squad.exe") == "/c/Tools/bin/squad.exe",
                "convert_windows_path falls back to MSYS mount syntax",
            )
        )
        wrapper.is_msys = lambda: False
        wrapper.is_cygwin = lambda: True
        checks.append(
            check(
                wrapper.convert_windows_path(r"C:\Tools\bin\squad.exe") == "/cygdrive/c/Tools/bin/squad.exe",
                "convert_windows_path falls back to Cygwin mount syntax",
            )
        )
    finally:
        wrapper.is_wsl, wrapper.is_msys, wrapper.is_cygwin, wrapper.shutil.which, wrapper.os.name = original

    original_windows_env_var = wrapper.windows_env_var
    try:
        wrapper.windows_env_var = lambda _name: ""
        env = wrapper.child_env(["/mnt/c/Tools/bin/squad.exe"])
        empty_injected = any(key in env and env[key] == "" for key in ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "SystemRoot"))
        checks.append(check(not empty_injected, "child_env does not inject empty Windows variables"))
    finally:
        wrapper.windows_env_var = original_windows_env_var

    command = launcher.supercc_squad_relative_commands("send", "menxia", "taizi", "BRIEF_MEMORIAL with space")
    checks.append(
        check(
            "'BRIEF_MEMORIAL with space'" in command["posix"]
            and "'BRIEF_MEMORIAL with space'" in command["powershell"]
            and '"BRIEF_MEMORIAL with space"' in command["cmd"],
            "supercc_squad_relative_commands quotes args with spaces",
            {"command": command},
        )
    )

    workspace = Path.home()
    cwd_by_client = {
        client: str(launcher.runtime_process_cwd_for_client(client, "menxia", workspace))
        for client in ("codex", "claude", "hermescli", "cli")
    }
    expected = str(launcher.office_dossier_dir("menxia"))
    checks.append(
        check(
            all(value == expected for value in cwd_by_client.values()),
            "all office clients start from the role dossier directory",
            {"cwd_by_client": cwd_by_client, "expected": expected},
        )
    )

    prompt = launcher.office_prompt("menxia", "menxia", workspace, None, office_client="hermescli")
    checks.append(
        check(
            "task_workspace_env=SUPERCC_TASK_WORKSPACE" in prompt
            and "C:\\Users" not in prompt
            and "/mnt/" not in prompt
            and "supercc-squad.sh receive menxia --json" in prompt,
            "office_prompt exposes wrapper contract without host-specific workspace paths",
        )
    )

    return {
        "ok": all(item["ok"] for item in checks),
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
        print(f"SUPERCC_SQUAD_WRAPPER_OK checks={len(result['checks'])}")
    else:
        print("SUPERCC_SQUAD_WRAPPER_FAILED")
        for item in result["checks"]:
            if not item["ok"]:
                print(json.dumps(item, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
