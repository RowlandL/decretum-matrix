"""Check portable superCC squad wrapper behavior without mutating squad state."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return sys.modules.get(name, module)


def check(condition: bool, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": bool(condition), "message": message, "details": details or {}}


def cmd_exit_checks(root: Path) -> list[dict[str, Any]]:
    """Run the real cmd entry, with isolated interpreter selectors and a harmless child."""
    if os.name != "nt":
        return [check(True, "Windows cmd execution NOT_RUN on this platform")]
    compiler = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    if not compiler.is_file():
        return [check(True, "Windows cmd execution NOT_RUN: system C# compiler unavailable", {"skipped": True})]
    checks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="supercc-cmd-check-") as directory:
        fixture = Path(directory)
        # A native proxy is necessary: calling a .cmd interpreter stub would
        # replace the outer batch and hide its stale ERRORLEVEL regression.
        source = fixture / "Interpreter.cs"
        source.write_text(r'''
using System;
using System.Diagnostics;
using System.IO;
class Interpreter {
    static int Main() {
        string raw = Environment.CommandLine;
        int end = raw.StartsWith("\"") ? raw.IndexOf('"', 1) + 1 : raw.IndexOf(' ');
        string arguments = end < 0 ? "" : raw.Substring(end).TrimStart();
        if (Path.GetFileNameWithoutExtension(Environment.GetCommandLineArgs()[0]) == "py") {
            if (!arguments.StartsWith("-3 ")) return 91;
            arguments = arguments.Substring(3);
        }
        var start = new ProcessStartInfo(Environment.GetEnvironmentVariable("SUPERCC_TEST_PYTHON"), arguments);
        start.UseShellExecute = false;
        using (var child = Process.Start(start)) { child.WaitForExit(); return child.ExitCode; }
    }
}
''', encoding="utf-8")
        compiled = fixture / "Interpreter.exe"
        build = subprocess.run([str(compiler), "/nologo", "/target:exe", f"/out:{compiled}", str(source)], capture_output=True, text=True)
        if build.returncode:
            return [check(False, "compile native interpreter fixture", {"stdout": build.stdout, "stderr": build.stderr})]
        child = fixture / "echo_args.py"
        child.write_text("import json,sys\nprint(json.dumps(sys.argv[2:],ensure_ascii=False))\nsys.exit(int(sys.argv[1]))\n", encoding="utf-8")
        arguments = ["with space", "", "bang!value", "中文"]
        env = dict(os.environ)
        env["SUPERCC_TEST_PYTHON"] = sys.executable
        env["SUPERCC_SQUAD_COMMAND"] = subprocess.list2cmdline([sys.executable, str(child)])
        env["PYTHONIOENCODING"] = "utf-8"
        # Only the selected executable and system tools are visible to WHERE.
        env["PATH"] = str(fixture) + os.pathsep + str(Path(env.get("SystemRoot", r"C:\Windows")) / "System32")
        for interpreter in ("python", "python3", "py"):
            proxy = fixture / f"{interpreter}.exe"
            shutil.copyfile(compiled, proxy)
            for code in (0, 17):
                passthrough = ["--", str(code), *arguments]
                direct = subprocess.run([sys.executable, str(root / "scripts/supercc_squad.py"), *passthrough], env=env, capture_output=True, text=True, encoding="utf-8")
                command = subprocess.list2cmdline([str(root / "scripts/supercc-squad.cmd"), *passthrough])
                via_cmd = subprocess.run('"' + env.get("COMSPEC", "cmd.exe") + '" /d /v:off /s /c "' + command + '"', env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
                checks.append(check(
                    via_cmd.returncode == direct.returncode == code and via_cmd.stdout == direct.stdout and json.loads(direct.stdout) == arguments,
                    f"cmd {interpreter} preserves exit {code} and each supported argument",
                    {"cmd_exit": via_cmd.returncode, "python_exit": direct.returncode, "cmd_stdout": via_cmd.stdout, "python_stdout": direct.stdout, "cmd_stderr": via_cmd.stderr},
                ))
            proxy.unlink()
    return checks


def run_checks() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
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

    checks.extend(cmd_exit_checks(root))
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



