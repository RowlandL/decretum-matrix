"""Small cross-platform helpers for court-capability-router scripts."""

from __future__ import annotations

import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess


def system_name() -> str:
    return platform.system().lower()


def is_windows() -> bool:
    return system_name() == "windows"


def is_macos() -> bool:
    return system_name() == "darwin"


def is_linux() -> bool:
    return system_name() == "linux"


def user_data_base() -> Path:
    """Return a writable per-user data root using native OS conventions."""
    if is_windows():
        return Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home() / "AppData" / "Local")
    if is_macos():
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def user_config_base() -> Path:
    if is_windows():
        return Path(os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Roaming")
    if is_macos():
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def user_cache_base() -> Path:
    if is_windows():
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    if is_macos():
        return Path.home() / "Library" / "Caches"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")


def which_any(*commands: str) -> str | None:
    for command in commands:
        found = shutil.which(command)
        if found:
            return found
    return None


def powershell_command() -> str:
    return which_any("pwsh", "pwsh.exe", "powershell.exe", "powershell") or "powershell"


def display_path(path: Path) -> str:
    return str(path)


def sh_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def terminal_launch_plan(title: str, command: str, *, keep_open: bool) -> dict[str, object]:
    """Return a best-effort native terminal launch command without executing it."""
    if is_windows():
        ps = powershell_command()
        args = [ps, "-NoExit" if keep_open else "-NoProfile", "-Command", command]
        return {"platform": "windows", "available": True, "args": args, "creationflags": subprocess.CREATE_NEW_CONSOLE}

    if is_macos():
        osascript = which_any("osascript")
        if osascript:
            escaped = command.replace("\\", "\\\\").replace('"', '\\"')
            script = f'tell application "Terminal" to do script "{escaped}"'
            return {"platform": "darwin", "available": True, "args": [osascript, "-e", script], "creationflags": 0}
        return {"platform": "darwin", "available": False, "reason": "osascript not found", "args": [], "creationflags": 0}

    linux_candidates = [
        ("x-terminal-emulator", ["x-terminal-emulator", "-e", "sh", "-lc", command]),
        ("gnome-terminal", ["gnome-terminal", "--", "sh", "-lc", command]),
        ("konsole", ["konsole", "-e", "sh", "-lc", command]),
        ("xfce4-terminal", ["xfce4-terminal", "-e", command]),
        ("xterm", ["xterm", "-T", title, "-e", "sh", "-lc", command]),
    ]
    for executable, args in linux_candidates:
        found = shutil.which(executable)
        if found:
            args[0] = found
            return {"platform": "linux", "available": True, "args": args, "creationflags": 0}
    return {"platform": system_name() or "posix", "available": False, "reason": "no supported terminal emulator found", "args": [], "creationflags": 0}
