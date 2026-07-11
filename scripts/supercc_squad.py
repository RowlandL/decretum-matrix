#!/usr/bin/env python3
"""Portable squad entrypoint for terminal-visible superCC offices.

The launcher and office prompts call this script instead of teaching each CLI
pane how to translate host paths. The script resolves the real ``squad``
program for the current environment, including native Windows shells, WSL,
MSYS/Git Bash, Cygwin, Linux, and macOS.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


def is_wsl() -> bool:
    if os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False


def is_msys() -> bool:
    return bool(os.environ.get("MSYSTEM") or os.environ.get("MINGW_PREFIX"))


def is_cygwin() -> bool:
    return sys.platform.startswith("cygwin")


def is_windows_path(text: str) -> bool:
    return bool(WINDOWS_PATH_RE.match(text))


def run_capture(args: list[str], timeout: int = 5) -> str:
    try:
        completed = subprocess.run(
            args,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def convert_windows_path(path: str) -> str:
    if os.name == "nt" or not is_windows_path(path):
        return path
    converter = "wslpath" if is_wsl() else "cygpath" if (is_msys() or is_cygwin()) else ""
    if converter and shutil.which(converter):
        converted = run_capture([converter, "-u", path])
        if converted:
            return converted.splitlines()[0].strip()
    drive = path[0].lower()
    rest = path[2:].lstrip("\\/").replace("\\", "/")
    if is_wsl():
        return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"
    if is_cygwin():
        return f"/cygdrive/{drive}/{rest}" if rest else f"/cygdrive/{drive}"
    return f"/{drive}/{rest}" if rest else f"/{drive}"


def split_command(text: str) -> list[str]:
    if os.name == "nt":
        parsed = split_windows_command_line(text)
        if parsed:
            return parsed
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        try:
            parts = shlex.split(text, posix=False)
            return [strip_matching_quotes(part) for part in parts]
        except ValueError:
            return [strip_matching_quotes(text)]


def strip_matching_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def split_windows_command_line(text: str) -> list[str]:
    if not text:
        return []
    try:
        import ctypes
        from ctypes import wintypes

        argc = ctypes.c_int(0)
        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32
        shell32.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        argv = shell32.CommandLineToArgvW(text, ctypes.byref(argc))
        if not argv:
            return []
        try:
            return [argv[index] for index in range(argc.value)]
        finally:
            kernel32.LocalFree(argv)
    except Exception:
        return []


def env_override_command() -> list[str] | None:
    for name in ("SUPERCC_SQUAD_COMMAND", "SQUAD_COMMAND", "SQUAD_EXE"):
        value = os.environ.get(name)
        if value:
            parts = split_command(value)
            if parts:
                parts[0] = convert_windows_path(parts[0])
                return parts
    return None


def path_command() -> list[str] | None:
    for name in ("squad", "squad.exe"):
        found = shutil.which(name)
        if found:
            return [convert_windows_path(found)]
    return None


def windows_bridge_command() -> list[str] | None:
    candidates: list[str] = []
    if shutil.which("cmd.exe") or os.name == "nt":
        output = run_capture(["cmd.exe", "/d", "/c", "where", "squad.exe"])
        candidates.extend(line.strip() for line in output.splitlines() if line.strip())
    shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("pwsh")
    if shell:
        output = run_capture(
            [
                shell,
                "-NoLogo",
                "-NoProfile",
                "-Command",
                "$c=Get-Command squad.exe -ErrorAction SilentlyContinue; if ($c) { $c.Source }",
            ]
        )
        candidates.extend(line.strip() for line in output.splitlines() if line.strip())
    for candidate in candidates:
        executable = convert_windows_path(candidate)
        if executable:
            return [executable]
    return None


def resolve_squad() -> tuple[list[str], str]:
    for source, resolver in (
        ("env", env_override_command),
        ("path", path_command),
        ("windows_bridge", windows_bridge_command),
    ):
        command = resolver()
        if command:
            return command, source
    return ["squad"], "fallback"


def windows_env_var(name: str) -> str:
    if not (shutil.which("cmd.exe") or os.name == "nt"):
        return ""
    output = run_capture(["cmd.exe", "/d", "/c", f"echo %{name}%"])
    if not output or output == f"%{name}%":
        return ""
    return output.splitlines()[0].strip()


def command_looks_windows(command: str) -> bool:
    lower = command.lower()
    return lower.endswith(".exe") or is_windows_path(command)


def child_env(command: list[str]) -> dict[str, str]:
    env = dict(os.environ)
    if os.name == "nt":
        profile = env.get("USERPROFILE") or str(Path.home())
        env.setdefault("USERPROFILE", profile)
        env["HOME"] = profile
        return env
    if command and command_looks_windows(command[0]):
        for name in ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "SystemRoot"):
            value = windows_env_var(name)
            if value:
                env.setdefault(name, value)
        if env.get("USERPROFILE"):
            env["HOME"] = env["USERPROFILE"]
    return env


def parse_wrapper_args(argv: list[str]) -> tuple[bool, str | None, list[str]]:
    print_command = False
    explicit_command: str | None = None
    passthrough: list[str] = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--supercc-print-command":
            print_command = True
            index += 1
            continue
        if item == "--supercc-squad-command":
            if index + 1 >= len(argv):
                raise SystemExit("--supercc-squad-command requires a value")
            explicit_command = argv[index + 1]
            index += 2
            continue
        if item == "--":
            passthrough.extend(argv[index + 1 :])
            break
        passthrough.extend(argv[index:])
        break
    return print_command, explicit_command, passthrough


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print(
            "Usage: supercc_squad.py [--supercc-print-command] "
            "[--supercc-squad-command COMMAND] -- <squad arguments>\n"
            "Example: supercc_squad.py receive menxia --json"
        )
        return 0
    print_command, explicit_command, squad_args = parse_wrapper_args(argv)
    if not squad_args:
        print("supercc_squad.py: missing squad arguments", file=sys.stderr)
        return 2
    if explicit_command:
        command = split_command(explicit_command)
        command[0] = convert_windows_path(command[0])
        source = "explicit"
    else:
        command, source = resolve_squad()
    if print_command:
        print(json.dumps({"command": command, "source": source, "args": squad_args}, ensure_ascii=False))
        return 0
    try:
        completed = subprocess.run([*command, *squad_args], env=child_env(command))
    except FileNotFoundError:
        print(
            "supercc_squad.py: cannot resolve squad. Set SUPERCC_SQUAD_COMMAND "
            "or install squad on PATH.",
            file=sys.stderr,
        )
        return 127
    return int(completed.returncode)


if __name__ == "__main__":
    sys.exit(main())
