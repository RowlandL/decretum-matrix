#!/usr/bin/env python
"""Ensure the Shiguan service watchdog is installed and running."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from xml.sax.saxutils import escape

sys.dont_write_bytecode = True

from shiguan_paths import ensure_shared_seed, reference_path, references_root


TASK_NAME = "CourtShiguanDaemon"


def daemon_script() -> Path:
    return Path(__file__).with_name("shiguan_service_daemon.py")


def status_path() -> Path:
    return reference_path("court-runtime", "shiguan-service-daemon.json")


def log_path() -> Path:
    return Path(tempfile.gettempdir()) / "court-shiguan-service-daemon.log"


def wrapper_path() -> Path:
    return reference_path("court-runtime", "ShiguanServiceDaemon.vbs")


def pythonw_path() -> Path:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    if sys.platform == "win32" and candidate.exists():
        return candidate
    return Path(sys.executable)


def vbs_string(value: Path | str) -> str:
    return str(value).replace('"', '""')


def write_wrapper(interval: int) -> Path:
    path = wrapper_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(
        [
            "' Court Shiguan silent service daemon launcher",
            "Option Explicit",
            "Dim sh, env, cmd",
            "Set sh = CreateObject(\"WScript.Shell\")",
            "Set env = sh.Environment(\"PROCESS\")",
            "env.Item(\"COURT_DISABLE_AGENT_PRESENCE\") = \"1\"",
            "env.Item(\"PYTHONUTF8\") = \"1\"",
            "env.Item(\"PYTHONIOENCODING\") = \"utf-8\"",
            "env.Item(\"PYTHONDONTWRITEBYTECODE\") = \"1\"",
            f"sh.CurrentDirectory = \"{vbs_string(Path(__file__).resolve().parents[1])}\"",
            f"cmd = Chr(34) & \"{vbs_string(pythonw_path())}\" & Chr(34) & \" \" & Chr(34) & \"{vbs_string(daemon_script())}\" & Chr(34) & \" --interval {interval}\"",
            "sh.Run cmd, 0, False",
            "",
        ]
    )
    path.write_text(body, encoding="utf-8", newline="\r\n")
    return path


def hidden_run_kwargs() -> dict[str, object]:
    if sys.platform != "win32":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def run_text(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        **hidden_run_kwargs(),
    )


def windows_pid_alive(pid: int) -> bool:
    if sys.platform != "win32" or pid <= 0:
        return False
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        process_query_limited_information = 0x1000
        still_active = 259
        error_access_denied = 5
        handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if not handle:
            return ctypes.get_last_error() == error_access_denied
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def find_running_daemon_pid() -> int:
    if sys.platform != "win32":
        current = read_json(status_path(), {})
        pid = int(current.get("pid") or 0) if isinstance(current, dict) else 0
        return pid if pid_alive(pid) else 0
    try:
        proc = run_text(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*shiguan_service_daemon.py*' } | "
                "Select-Object -ExpandProperty ProcessId",
            ],
            timeout=10,
        )
    except Exception:
        return 0
    for line in (proc.stdout or "").splitlines():
        text = line.strip()
        if not text.isdigit():
            continue
        pid = int(text)
        if pid != os.getpid() and pid_alive(pid):
            return pid
    return 0


def recorded_daemon_pid() -> int:
    current = read_json(status_path(), {})
    pid = int(current.get("pid") or 0) if isinstance(current, dict) else 0
    return pid if pid_alive(pid) else 0


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def current_user() -> str:
    try:
        proc = run_text(["whoami"], timeout=10)
        value = (proc.stdout or "").strip()
        if value:
            return value
    except Exception:
        pass
    domain = os.environ.get("USERDOMAIN", "").strip()
    user = os.environ.get("USERNAME", "").strip()
    return f"{domain}\\{user}" if domain and user else user


def task_xml(interval: int) -> str:
    wrapper = write_wrapper(interval)
    command = "wscript.exe"
    args = escape(f'//B //Nologo "{wrapper}"')
    workdir = escape(str(Path(__file__).resolve().parents[1]))
    user = escape(current_user())
    registered = datetime.now().isoformat(timespec="seconds")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>{registered}</Date>
    <Author>{user}</Author>
    <Description>Starts the Court Shiguan WebUI and preserve-only autosync watchdog at user logon.</Description>
    <URI>\\{TASK_NAME}</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{args}</Arguments>
      <WorkingDirectory>{workdir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def query_task() -> dict[str, object]:
    if sys.platform != "win32":
        return {"exists": False, "status": "UNSUPPORTED", "task_name": TASK_NAME}
    proc = run_text(
        ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"],
        timeout=20,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    return {
        "exists": proc.returncode == 0,
        "status": "EXISTS" if proc.returncode == 0 else "MISSING",
        "task_name": TASK_NAME,
        "query_output": stdout[-1200:] if proc.returncode == 0 else stderr[-1200:],
    }


def install_task(interval: int) -> dict[str, object]:
    if sys.platform != "win32":
        return {"status": "UNSUPPORTED", "task_name": TASK_NAME}
    xml_path = Path(tempfile.gettempdir()) / f"{TASK_NAME}.xml"
    xml_path.write_text(task_xml(interval), encoding="utf-16", newline="\r\n")
    proc = run_text(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"],
        timeout=30,
    )
    if proc.returncode == 0:
        return {
            "status": "INSTALLED",
            "method": "xml",
            "task_name": TASK_NAME,
            "task_xml": str(xml_path),
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
        }

    wrapper = write_wrapper(interval)
    trigger_command = f'wscript.exe //B //Nologo "{wrapper}"'
    fallback = run_text(
        [
            "schtasks",
            "/Create",
            "/TN",
            TASK_NAME,
            "/SC",
            "ONLOGON",
            "/TR",
            trigger_command,
            "/F",
            "/RL",
            "LIMITED",
        ],
        timeout=30,
    )
    return {
        "status": "INSTALLED" if fallback.returncode == 0 else "FAILED",
        "method": "xml" if proc.returncode == 0 else "onlogon_tr_fallback",
        "task_name": TASK_NAME,
        "task_xml": str(xml_path),
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "fallback_stdout": (fallback.stdout or "").strip(),
        "fallback_stderr": (fallback.stderr or "").strip(),
        "trigger_command": trigger_command,
    }


def start_task() -> dict[str, object]:
    if sys.platform != "win32":
        return {"status": "UNSUPPORTED", "task_name": TASK_NAME}
    proc = run_text(
        ["schtasks", "/Run", "/TN", TASK_NAME],
        timeout=20,
    )
    return {
        "status": "START_REQUESTED" if proc.returncode == 0 else "FAILED",
        "task_name": TASK_NAME,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
    }


def unregister_task() -> dict[str, object]:
    if sys.platform != "win32":
        return {"status": "UNSUPPORTED", "task_name": TASK_NAME}
    proc = run_text(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        timeout=20,
    )
    return {
        "status": "UNREGISTERED" if proc.returncode == 0 else "FAILED",
        "task_name": TASK_NAME,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
    }


def start_direct(interval: int) -> int:
    log_path().parent.mkdir(parents=True, exist_ok=True)
    handle = log_path().open("a", encoding="utf-8")
    env = os.environ.copy()
    env["COURT_DISABLE_AGENT_PRESENCE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    args = [str(pythonw_path()), str(daemon_script()), "--interval", str(interval)]
    kwargs: dict[str, object] = {
        "cwd": str(Path(__file__).resolve().parents[1]),
        "stdout": handle,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "env": env,
    }
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(args, **kwargs)
    handle.close()
    return int(proc.pid)


def ensure(interval: int, check_only: bool = False, install: bool = True, start_now: bool = True) -> dict[str, object]:
    task_before = query_task()
    pid = recorded_daemon_pid() if check_only else find_running_daemon_pid()
    if check_only:
        return {
            "status": "RUNNING" if pid else "NOT_RUNNING",
            "pid": pid,
            "task": task_before,
            "task_name": TASK_NAME,
            "status_path": str(status_path()),
            "log_path": str(log_path()),
            "shared_shiguan_root": str(references_root()),
        }

    ensure_shared_seed()
    install_report = {"status": "SKIPPED", "task_name": TASK_NAME}
    if install:
        install_report = install_task(interval)
    task_after = query_task()

    start_report = {"status": "SKIPPED", "task_name": TASK_NAME}
    if start_now and not pid:
        if task_after.get("exists"):
            start_report = start_task()
            time.sleep(2.0)
            pid = find_running_daemon_pid()
        if not pid:
            pid = start_direct(interval)
            time.sleep(1.0)

    return {
        "status": "RUNNING" if pid else "START_REQUESTED",
        "pid": pid,
        "interval_seconds": interval,
        "task_name": TASK_NAME,
        "task_before": task_before,
        "task_after": task_after,
        "install": install_report,
        "start": start_report,
        "status_path": str(status_path()),
        "log_path": str(log_path()),
        "shared_shiguan_root": str(references_root()),
        "manual_revoke": f"schtasks /Delete /TN {TASK_NAME} /F",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument("--no-start-now", action="store_true")
    parser.add_argument("--unregister", action="store_true")
    args = parser.parse_args()

    if args.unregister:
        report = unregister_task()
    else:
        report = ensure(
            max(10, args.interval),
            check_only=args.check_only,
            install=not args.no_install,
            start_now=not args.no_start_now,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if str(report.get("status")) != "FAILED" else 1


if __name__ == "__main__":
    # Fix for Windows UTF-8 encoding issues (2026-07-05)
    # On Windows, stdout may default to CP936/GBK encoding, causing UnicodeEncodeError
    # when printing JSON with Chinese characters (e.g., 官署代称, 太子, etc.)
    # This reconfigures stdout to UTF-8 before main() executes to ensure proper output
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
