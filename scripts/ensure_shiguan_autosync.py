#!/usr/bin/env python
"""Ensure the independent Shiguan autosync daemon is running."""

from __future__ import annotations

from datetime import datetime
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
import tempfile

from court_platform import user_data_base
from shiguan_paths import ensure_shared_seed, reference_path, references_root
from court_file_lock import atomic_write_text, file_lock


PROCESS_DISCOVERY_MULTIPLE = -1
PROCESS_DISCOVERY_FAILED = -2


def daemon_script() -> Path:
    return Path(__file__).with_name("shiguan_autosync_daemon.py")


def trusted_daemon_script_paths() -> set[str]:
    """Return exact daemon paths for the current and known active skill copies."""

    home = Path.home()
    roots = {
        Path(__file__).resolve().parents[1],
        home / ".agents" / "skills" / "court-capability-router",
        home / ".codex" / "skills" / "court-capability-router",
        home / ".claude" / "skills" / "court-capability-router",
        home / ".hermes" / "skills" / "court-capability-router",
        user_data_base() / "hermes" / "skills" / "court-capability-router",
    }
    return {
        normalized_process_path(root / "scripts" / "shiguan_autosync_daemon.py")
        for root in roots
    }


def background_python() -> str:
    candidate = Path(sys.executable)
    if sys.platform == "win32":
        pythonw = candidate.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(candidate)


def status_path() -> Path:
    return reference_path("obsidian-sync", "autosync-daemon.json")


def ensure_lock_path() -> Path:
    return reference_path("court-runtime", "obsidian-autosync-ensure.lock")


def log_path() -> Path:
    return Path(tempfile.gettempdir()) / "court-shiguan-autosync.log"


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: object) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def hidden_run_kwargs() -> dict[str, object]:
    if sys.platform != "win32":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def windows_pid_alive(pid: int) -> bool:
    if sys.platform != "win32" or pid <= 0:
        return False
    try:
        import ctypes

        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        process_query_limited_information = 0x1000
        still_active = 259
        handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
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


def status_is_fresh(value: object, interval: int) -> bool:
    if not isinstance(value, dict):
        return False
    raw = str(value.get("updated_at") or "").strip()
    if not raw:
        return False
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return False
    now = datetime.now(stamp.tzinfo) if stamp.tzinfo is not None else datetime.now()
    age = (now - stamp).total_seconds()
    return -5.0 <= age <= max(60.0, float(interval) * 3.0)


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def normalized_process_path(value: object) -> str:
    text = str(value or "").strip().strip('"')
    if not text:
        return ""
    expanded = os.path.expandvars(os.path.expanduser(text))
    try:
        resolved = Path(expanded).resolve(strict=False)
    except OSError:
        resolved = Path(expanded).absolute()
    return os.path.normcase(str(resolved))


def command_line_runs_daemon(command_line: object) -> bool:
    text = str(command_line or "").strip()
    if not text:
        return False
    try:
        tokens = shlex.split(text, posix=sys.platform != "win32")
    except ValueError:
        return False
    if len(tokens) < 2 or not Path(tokens[0].strip('"')).name.lower().startswith("python"):
        return False
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token in {"-c", "-m"}:
            return False
        if token in {"-W", "-X"}:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    return index < len(tokens) and normalized_process_path(tokens[index]) in trusted_daemon_script_paths()


def _windows_python_process_rows() -> tuple[bool, list[dict[str, object]]]:
    """Read Python command lines through Win32 APIs without spawning PowerShell.

    PowerShell creates profile directories even with ``-NoProfile`` when HOME is
    redirected to a blank audit root.  Native process enumeration keeps
    ``--check-only`` genuinely zero-write.
    """

    try:
        import ctypes
        from ctypes import wintypes

        th32cs_snapprocess = 0x00000002
        process_query_limited_information = 0x1000
        process_command_line_information = 60
        max_path = 260
        error_no_more_files = 18

        class ProcessEntry32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * max_path),
            ]

        class UnicodeString(ctypes.Structure):
            _fields_ = [
                ("Length", wintypes.USHORT),
                ("MaximumLength", wintypes.USHORT),
                ("Buffer", wintypes.LPWSTR),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll")
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
        kernel32.Process32NextW.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        ntdll.NtQueryInformationProcess.argtypes = [
            wintypes.HANDLE,
            wintypes.ULONG,
            wintypes.LPVOID,
            wintypes.ULONG,
            ctypes.POINTER(wintypes.ULONG),
        ]
        ntdll.NtQueryInformationProcess.restype = wintypes.LONG

        snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            return False, []
        rows: list[dict[str, object]] = []
        try:
            entry = ProcessEntry32W()
            entry.dwSize = ctypes.sizeof(entry)
            more = bool(kernel32.Process32FirstW(snapshot, ctypes.byref(entry)))
            if not more:
                return ctypes.get_last_error() == error_no_more_files, []
            while more:
                process_name = str(entry.szExeFile).lower()
                if process_name.startswith("python") and int(entry.th32ProcessID) != os.getpid():
                    handle = kernel32.OpenProcess(
                        process_query_limited_information,
                        False,
                        int(entry.th32ProcessID),
                    )
                    if not handle:
                        return False, []
                    try:
                        command_line = ""
                        for size in (32768, 65536, 131072):
                            buffer = ctypes.create_string_buffer(size)
                            required = wintypes.ULONG()
                            status = ntdll.NtQueryInformationProcess(
                                handle,
                                process_command_line_information,
                                buffer,
                                size,
                                ctypes.byref(required),
                            )
                            if status == 0:
                                value = ctypes.cast(buffer, ctypes.POINTER(UnicodeString)).contents
                                command_line = (
                                    ctypes.wstring_at(value.Buffer, value.Length // 2)
                                    if value.Buffer and value.Length
                                    else ""
                                )
                                break
                            if required.value <= size:
                                break
                        if not command_line:
                            return False, []
                        rows.append(
                            {
                                "ProcessId": int(entry.th32ProcessID),
                                "CommandLine": command_line,
                            }
                        )
                    finally:
                        kernel32.CloseHandle(handle)
                more = bool(kernel32.Process32NextW(snapshot, ctypes.byref(entry)))
            if ctypes.get_last_error() not in {0, error_no_more_files}:
                return False, []
        finally:
            kernel32.CloseHandle(snapshot)
    except Exception:
        return False, []
    return True, rows


def _posix_python_process_rows() -> tuple[bool, list[dict[str, object]]]:
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            text=True,
            capture_output=True,
            timeout=10,
        )
    except Exception:
        return False, []
    if proc.returncode != 0:
        return False, []
    rows: list[dict[str, object]] = []
    for line in proc.stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        rows.append({"ProcessId": int(parts[0]), "CommandLine": parts[1]})
    return True, rows


def find_running_daemon_pid() -> int:
    """Return the one exact daemon PID, or a negative discovery sentinel."""

    discovery_ok, rows = (
        _windows_python_process_rows()
        if sys.platform == "win32"
        else _posix_python_process_rows()
    )
    if not discovery_ok:
        return PROCESS_DISCOVERY_FAILED
    pids: set[int] = set()
    for row in rows:
        try:
            pid = int(row.get("ProcessId") or 0)
        except (TypeError, ValueError):
            continue
        if pid <= 0 or pid == os.getpid() or not command_line_runs_daemon(row.get("CommandLine")):
            continue
        if pid_alive(pid):
            pids.add(pid)
    if len(pids) > 1:
        return PROCESS_DISCOVERY_MULTIPLE
    return next(iter(pids), 0)


def start_daemon(interval: int) -> int:
    log_path().parent.mkdir(parents=True, exist_ok=True)
    handle = log_path().open("a", encoding="utf-8")
    args = [background_python(), "-B", str(daemon_script()), "--interval", str(interval)]
    env = os.environ.copy()
    env["COURT_DISABLE_AGENT_PRESENCE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
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


def _ensure_unlocked(interval: int, check_only: bool = False) -> dict[str, object]:
    current = read_json(status_path(), {})
    recorded_pid = safe_int(current.get("pid"), 0) if isinstance(current, dict) else 0
    recorded_interval = safe_int(current.get("interval_seconds"), interval) if isinstance(current, dict) else interval
    recorded_interval = max(5, recorded_interval)
    recorded_alive = pid_alive(recorded_pid)
    recorded_status_valid = bool(
        isinstance(current, dict)
        and current.get("ok") is True
        and current.get("mode") == "daemon"
    )
    recorded_fresh = recorded_status_valid and status_is_fresh(current, recorded_interval)

    discovered_pid = find_running_daemon_pid()
    if discovered_pid == PROCESS_DISCOVERY_FAILED:
        return {
            "status": "PROCESS_DISCOVERY_UNAVAILABLE",
            "pid": recorded_pid if recorded_alive else 0,
            "reason": "exact_daemon_process_discovery_failed; refusing to reuse or start a second instance",
            "status_path": str(status_path()),
            "log_path": str(log_path()),
            "shared_shiguan_root": str(references_root()),
        }
    if discovered_pid == PROCESS_DISCOVERY_MULTIPLE:
        return {
            "status": "RUNNING_UNHEALTHY",
            "pid": 0,
            "reason": "multiple_exact_daemon_processes",
            "status_path": str(status_path()),
            "log_path": str(log_path()),
            "shared_shiguan_root": str(references_root()),
        }

    current_reusable = (
        discovered_pid > 0
        and discovered_pid == recorded_pid
        and recorded_alive
        and recorded_fresh
    )
    if current_reusable:
        report = {
            "status": "REUSED",
            "pid": recorded_pid,
            "interval_seconds": recorded_interval,
            "status_path": str(status_path()),
            "log_path": str(log_path()),
            "shared_shiguan_root": str(references_root()),
        }
        return report
    if discovered_pid > 0:
        reasons: list[str] = []
        if discovered_pid != recorded_pid:
            reasons.append("status_pid_mismatch")
        if not recorded_alive:
            reasons.append("recorded_pid_dead")
        if not recorded_fresh:
            reasons.append("status_stale_or_missing")
        if not recorded_status_valid:
            reasons.append("status_not_healthy_daemon")
        return {
            "status": "RUNNING_UNHEALTHY",
            "pid": discovered_pid,
            "recorded_pid": recorded_pid,
            "interval_seconds": recorded_interval,
            "reason": ",".join(reasons) or "process_health_not_proven",
            "status_path": str(status_path()),
            "log_path": str(log_path()),
            "shared_shiguan_root": str(references_root()),
        }
    if check_only:
        return {
            "status": "NOT_RUNNING",
            "pid": 0,
            "status_path": str(status_path()),
            "log_path": str(log_path()),
            "shared_shiguan_root": str(references_root()),
        }
    ensure_shared_seed()
    new_pid = start_daemon(interval)
    report = {
        "status": "STARTED",
        "pid": new_pid,
        "interval_seconds": interval,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "status_path": str(status_path()),
        "log_path": str(log_path()),
        "shared_shiguan_root": str(references_root()),
    }
    write_json(status_path(), {**report, "ok": True, "mode": "daemon"})
    return report


def ensure(interval: int, check_only: bool = False) -> dict[str, object]:
    if check_only:
        # A read-only audit must not create even a persistent lock file. It can
        # safely inspect health without startup serialization because it never
        # launches a process or writes status.
        return _ensure_unlocked(interval, check_only=True)
    # Serialize discovery + possible start. Without this lock, two simultaneous
    # service/watchdog callers can both observe zero candidates and each launch
    # a daemon before either status record becomes visible.
    with file_lock(ensure_lock_path(), timeout=30.0):
        return _ensure_unlocked(interval, check_only=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=int, default=20)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    report = ensure(max(5, args.interval), check_only=args.check_only)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
