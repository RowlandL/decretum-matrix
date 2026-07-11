"""Isolated process and strict-config helpers for Codex runtime probes."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None  # type: ignore[assignment]

sys.dont_write_bytecode = True


def _safe_probe_environment(home: Path, credential_canary: str) -> dict[str, str]:
    env: dict[str, str] = {}
    blocked_terms = ("TOKEN", "SECRET", "PASSWORD", "COOKIE", "API_KEY", "AUTH")
    for key, value in os.environ.items():
        upper = key.upper()
        if any(term in upper for term in blocked_terms):
            continue
        if upper in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}:
            continue
        env[key] = value
    env["CODEX_HOME"] = str(home)
    env["COURT_PROBE_API_KEY"] = credential_canary
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    return env


def _process_creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def _windows_descendant_pids(root_pid: int) -> list[int]:
    if os.name != "nt":
        return []
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("PowerShell is required for Windows process-tree verification")
    script = (
        "$all=Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId;"
        f"$pending=New-Object System.Collections.Generic.Queue[int];$pending.Enqueue({int(root_pid)});"
        "$found=New-Object System.Collections.Generic.List[int];"
        "while($pending.Count -gt 0){$parent=$pending.Dequeue();"
        "$all | Where-Object {$_.ParentProcessId -eq $parent} | ForEach-Object {"
        "$pidValue=[int]$_.ProcessId;if(-not $found.Contains($pidValue)){"
        "$found.Add($pidValue);$pending.Enqueue($pidValue)}}};"
        "$found | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command", script],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
            creationflags=_process_creation_flags(),
        )
        if result.returncode != 0:
            raise RuntimeError("Windows process-tree verification failed")
        if not result.stdout.strip():
            return []
        parsed = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("Windows process-tree verification failed") from exc
    values = parsed if isinstance(parsed, list) else [parsed]
    return sorted({int(value) for value in values if str(value).isdigit()})


def _existing_pids(pids: list[int]) -> list[int]:
    if not pids or os.name != "nt":
        return []
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("PowerShell is required for Windows process cleanup verification")
    joined = ",".join(str(pid) for pid in pids)
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-Command",
            f"@(Get-Process -Id @({joined}) -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id) | ConvertTo-Json -Compress",
        ],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
        creationflags=_process_creation_flags(),
    )
    if result.returncode != 0:
        raise RuntimeError("Windows process cleanup verification failed")
    if not result.stdout.strip():
        return []
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Windows process cleanup verification failed") from exc
    values = parsed if isinstance(parsed, list) else [parsed]
    return sorted({int(value) for value in values if str(value).isdigit()})


def _stop_owned_pids(pids: list[int]) -> bool:
    if not pids:
        return True
    if os.name != "nt":
        raise RuntimeError("owned child cleanup is unsupported on this platform")
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("PowerShell is required for Windows process cleanup")
    existing = _existing_pids(pids)
    if not existing:
        return True
    joined = ",".join(str(pid) for pid in existing)
    subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-Command",
            f"Get-Process -Id @({joined}) -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue",
        ],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
        creationflags=_process_creation_flags(),
    )
    # A descendant can exit between Get-Process and Stop-Process. Physical
    # liveness is authoritative even if PowerShell reports that benign race.
    for _ in range(3):
        if not _existing_pids(existing):
            return True
        time.sleep(0.1)
    return False


def _toml_key_names(text: str) -> list[str]:
    if tomllib is None:
        return []
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    names: list[str] = []

    def sanitized(parts: list[str]) -> str:
        normalized = list(parts)
        if normalized and normalized[0] in {"projects", "plugins", "mcp_servers", "marketplaces", "model_providers"}:
            if len(normalized) >= 2:
                normalized[1] = "<entry>"
        if normalized[:2] == ["hooks", "state"] and len(normalized) >= 3:
            normalized[2] = "<entry>"
        if normalized[:2] == ["shell_environment_policy", "set"] and len(normalized) >= 3:
            normalized = normalized[:2] + ["<entry>"]
        if normalized[:2] == ["desktop", "open-in-target-preferences"] and len(normalized) >= 3:
            if normalized[2] == "perPath" and len(normalized) >= 4:
                normalized = normalized[:3] + ["<entry>"]
            elif normalized[2] not in {"global", "perPath"}:
                normalized[2] = "<entry>"
        if normalized[:2] == ["tui", "model_availability_nux"] and len(normalized) >= 3:
            normalized = normalized[:2] + ["<entry>"]
        if normalized[:3] == ["mcp_servers", "<entry>", "env"] and len(normalized) >= 4:
            normalized[3] = "<entry>"
        return ".".join(normalized)

    def walk(value: object, parts: list[str] | None = None) -> None:
        if not isinstance(value, dict):
            return
        prefix = list(parts or [])
        for key in sorted(value):
            next_parts = prefix + [str(key)]
            names.append(sanitized(next_parts))
            walk(value[key], next_parts)

    walk(data)
    return sorted(set(names))


def strict_config_text_probe(
    executable_path: Path,
    config_text: str,
    *,
    startup_grace_seconds: float = 1.5,
) -> dict[str, object]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="court-codex-strict-config-") as temp_dir:
        home = Path(temp_dir) / "home"
        home.mkdir()
        (home / "config.toml").write_text(config_text, encoding="utf-8", newline="\n")
        env = _safe_probe_environment(home, "strict-config-no-credential")
        process = subprocess.Popen(
            [str(executable_path), "app-server", "--strict-config", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=_process_creation_flags(),
        )
        accepted = False
        descendants: list[int] = []
        try:
            process.wait(timeout=startup_grace_seconds)
        except subprocess.TimeoutExpired:
            accepted = True
            descendants = _windows_descendant_pids(process.pid)
            _terminate_process(process)
        cleanup_verified = _stop_owned_pids(descendants)
        remaining_descendants = _existing_pids(descendants)
        if accepted:
            stdout = ""
            stderr = ""
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        else:
            stdout, stderr = process.communicate(timeout=3)
        lowered = (stdout + "\n" + stderr).lower()
        if "unknown configuration field" in lowered:
            error_class = "unknown_configuration_field"
        elif accepted:
            error_class = "none"
        else:
            error_class = "strict_config_startup_failed"
        return {
            "schema": "court.codex-strict-config-proof.v1",
            "accepted": accepted,
            "error_class": error_class,
            "config_sha256": hashlib.sha256(config_text.encode("utf-8")).hexdigest(),
            "config_key_names": _toml_key_names(config_text),
            "full_config_archived": False,
            "client_exit_code": process.returncode,
            "terminated_by_probe": accepted,
            "descendant_process_count_observed": len(descendants),
            "cleanup_verified": cleanup_verified,
            "orphan_process_count": len(remaining_descendants),
            "duration_ms": round((time.perf_counter() - started) * 1000),
        }


def strict_config_file_probe(executable_path: Path, config_path: Path) -> dict[str, object]:
    return strict_config_text_probe(executable_path, config_path.read_text(encoding="utf-8"))
