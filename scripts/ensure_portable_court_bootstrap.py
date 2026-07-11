#!/usr/bin/env python3
"""Bootstrap a portable court-capability-router install on a target host.

The bootstrap is intentionally composed from the skill's own local scripts:
shared Shiguan seed creation, Obsidian linking, Shiguan service daemon setup,
Codex/Hermes built-in memory enablement, metadata-only Shiguan bridging, and
first-run superCC dependency installation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
import tempfile
import urllib.error
import urllib.request
import zipfile
from typing import Any

from court_platform import user_data_base
from shiguan_paths import (
    default_obsidian_shared_vault,
    ensure_shared_seed,
    references_root,
    shared_root,
)


DEFAULT_TIMEOUT = 120
GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_LATEST_DOWNLOAD = "https://github.com/{repo}/releases/latest/download/{asset}"
ZELLIJ_REPO = "zellij-org/zellij"
ZELLIJ_ASSET = "zellij-x86_64-pc-windows-msvc.zip"
SQUAD_REPO = os.environ.get("COURT_SQUAD_GITHUB_REPO", "mco-org/squad")
SQUAD_ASSET = "squad-x86_64-pc-windows-msvc.zip"


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def user_home() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("USERPROFILE") or Path.home())
    return Path(os.environ.get("HOME") or Path.home())


def default_install_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("COURT_TOOL_INSTALL_DIR", r"C:\Tools\bin"))
    return Path(os.environ.get("COURT_TOOL_INSTALL_DIR", str(user_home() / ".local" / "bin")))


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def tool_env(install_dir: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    profile = os.environ.get("USERPROFILE") if sys.platform == "win32" else None
    if profile:
        env["HOME"] = profile
    paths = []
    if install_dir:
        paths.append(str(install_dir))
    if sys.platform == "win32":
        paths.append(r"C:\Tools\bin")
    current = env.get("PATH", "")
    current_lower = current.lower()
    for path in paths:
        if path and path.lower() not in current_lower:
            current = path + os.pathsep + current
            current_lower = current.lower()
    env["PATH"] = current
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def truncate(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"...<truncated {len(text) - limit} chars>"


def resolved_invocation(args: list[str], install_dir: Path | None = None) -> list[str]:
    if not args:
        return args
    command = args[0]
    if any(sep in command for sep in ("\\", "/")):
        resolved = command
    else:
        resolved = shutil.which(command, path=tool_env(install_dir).get("PATH")) or command
    suffix = Path(resolved).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        return ["cmd.exe", "/d", "/c", resolved, *args[1:]]
    if suffix == ".ps1":
        return [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            resolved,
            *args[1:],
        ]
    return [resolved, *args[1:]]


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    install_dir: Path | None = None,
    stdout_limit: int = 6000,
    stderr_limit: int = 4000,
) -> dict[str, Any]:
    invocation = resolved_invocation(args, install_dir)
    try:
        proc = subprocess.run(
            invocation,
            cwd=str(cwd) if cwd else None,
            env=tool_env(install_dir),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "args": args,
            "invocation": invocation,
            "stdout": truncate(proc.stdout.strip(), stdout_limit),
            "stderr": truncate(proc.stderr.strip(), stderr_limit),
        }
    except FileNotFoundError as exc:
        return {"ok": False, "returncode": None, "args": args, "stderr": f"not found: {exc}", "stdout": ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": None, "args": args, "stderr": f"timeout after {timeout}s", "stdout": ""}


def command_available(command: str, install_dir: Path | None = None) -> bool:
    return shutil.which(command, path=tool_env(install_dir).get("PATH")) is not None


def backup_file(path: Path) -> str:
    if not path.exists():
        return ""
    backup = path.with_name(path.name + f".court-bootstrap-{now_stamp()}.bak")
    shutil.copy2(path, backup)
    return str(backup)


def section_bounds(lines: list[str], section: str) -> tuple[int | None, int]:
    header = f"[{section}]"
    start: int | None = None
    end = len(lines)
    for index, line in enumerate(lines):
        if line.strip() == header:
            start = index
            break
    if start is None:
        return None, len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break
    return start, end


def ensure_toml_bool_settings(text: str, settings: dict[str, dict[str, bool]]) -> tuple[str, bool]:
    lines = text.splitlines()
    changed = False
    if text and not text.endswith(("\n", "\r\n")):
        changed = True
    for section, values in settings.items():
        start, end = section_bounds(lines, section)
        if start is None:
            if lines and lines[-1].strip():
                lines.append("")
            start = len(lines)
            lines.append(f"[{section}]")
            end = len(lines)
            changed = True
        for key, value in values.items():
            wanted = f"{key} = {'true' if value else 'false'}"
            key_re = re.compile(rf"^(\s*){re.escape(key)}\s*=")
            replaced = False
            for index in range(start + 1, end):
                if key_re.match(lines[index]):
                    if lines[index].strip() != wanted:
                        lines[index] = wanted
                        changed = True
                    replaced = True
                    break
            if not replaced:
                lines.insert(end, wanted)
                end += 1
                changed = True
    output = "\n".join(lines).rstrip() + "\n"
    return output, changed


def enable_codex_memory(apply: bool) -> dict[str, Any]:
    codex_home = Path(os.environ.get("CODEX_HOME") or (user_home() / ".codex"))
    path = codex_home / "config.toml"
    exists_before = path.exists()
    original = path.read_text(encoding="utf-8", errors="replace") if exists_before else ""
    updated, changed = ensure_toml_bool_settings(
        original,
        {
            "features": {"memories": True},
            "memories": {"generate_memories": True, "use_memories": True},
        },
    )
    backup = ""
    if apply and changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = backup_file(path)
        path.write_text(updated, encoding="utf-8", newline="\n")
    return {
        "ok": True,
        "path": str(path),
        "exists_before": exists_before,
        "changed": changed and apply,
        "would_change": changed and not apply,
        "backup": backup,
        "settings": {
            "features.memories": True,
            "memories.generate_memories": True,
            "memories.use_memories": True,
        },
    }


def hermes_config_path() -> Path:
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        return Path(env_home) / "config.yaml"
    local = user_data_base() / "hermes" / "config.yaml"
    if local.exists() or local.parent.exists():
        return local
    return user_home() / ".hermes" / "config.yaml"


def ensure_simple_yaml_section(text: str, section: str, values: dict[str, bool]) -> tuple[str, bool]:
    lines = text.splitlines()
    changed = False
    start: int | None = None
    end = len(lines)
    section_re = re.compile(rf"^{re.escape(section)}:\s*(?:#.*)?$")
    for index, line in enumerate(lines):
        if section_re.match(line.strip()):
            start = index
            break
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{section}:")
        start = len(lines) - 1
        end = len(lines)
        changed = True
    else:
        for index in range(start + 1, len(lines)):
            line = lines[index]
            if line.strip() and not line.startswith((" ", "\t")):
                end = index
                break
    for key, value in values.items():
        wanted = f"  {key}: {'true' if value else 'false'}"
        key_re = re.compile(rf"^\s+{re.escape(key)}\s*:")
        replaced = False
        for index in range(start + 1, end):
            if key_re.match(lines[index]):
                if lines[index].strip() != wanted.strip():
                    lines[index] = wanted
                    changed = True
                replaced = True
                break
        if not replaced:
            lines.insert(end, wanted)
            end += 1
            changed = True
    return "\n".join(lines).rstrip() + "\n", changed


def enable_hermes_memory(apply: bool) -> dict[str, Any]:
    path = hermes_config_path()
    exists_before = path.exists()
    original = path.read_text(encoding="utf-8", errors="replace") if exists_before else ""
    updated, changed = ensure_simple_yaml_section(
        original,
        "memory",
        {"memory_enabled": True, "user_profile_enabled": True},
    )
    backup = ""
    if apply and changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = backup_file(path)
        path.write_text(updated, encoding="utf-8", newline="\n")
    return {
        "ok": True,
        "path": str(path),
        "exists_before": exists_before,
        "changed": changed and apply,
        "would_change": changed and not apply,
        "backup": backup,
        "settings": {"memory.memory_enabled": True, "memory.user_profile_enabled": True},
        "provider_policy": "preserve_existing_provider",
    }


def ensure_shared(apply: bool) -> dict[str, Any]:
    root = shared_root()
    refs = references_root()
    if apply:
        refs = ensure_shared_seed()
    return {
        "ok": True,
        "changed": apply,
        "would_change": not apply and not refs.exists(),
        "shared_root": str(root),
        "references_root": str(refs),
        "seed_exists": refs.exists(),
    }


def ensure_obsidian(apply: bool, set_open: bool) -> dict[str, Any]:
    script = skill_root() / "scripts" / "ensure_obsidian_shared_vault.py"
    shared_vault = default_obsidian_shared_vault()
    if not apply:
        registered = False
        config_path = ""
        vault_key = ""
        try:
            from ensure_obsidian_shared_vault import obsidian_config_path, read_json, vault_id

            config = obsidian_config_path()
            config_path = str(config)
            vault_key = vault_id(shared_vault)
            data = read_json(config, {"vaults": {}})
            vaults = data.get("vaults") if isinstance(data, dict) else {}
            registered = isinstance(vaults, dict) and vault_key in vaults
        except Exception as exc:  # noqa: BLE001 - check-only diagnostics should stay non-fatal.
            return {
                "ok": True,
                "changed": False,
                "check_only": True,
                "script": str(script),
                "shared_vault_path": str(shared_vault),
                "set_open": set_open,
                "registered": False,
                "check_warning": str(exc),
            }
        return {
            "ok": True,
            "changed": False,
            "check_only": True,
            "script": str(script),
            "shared_vault_path": str(shared_vault),
            "set_open": set_open,
            "obsidian_config": config_path,
            "vault_id": vault_key,
            "registered": registered,
            "would_change": not registered,
        }
    args = [sys.executable, str(script)]
    if not set_open:
        args.append("--no-set-open")
    result = run_command(args, cwd=skill_root(), timeout=60)
    return {"ok": result["ok"], "changed": result["ok"], "script": str(script), "result": result}


def ensure_service_daemon(apply: bool) -> dict[str, Any]:
    script = skill_root() / "scripts" / "ensure_shiguan_service_daemon.py"
    if not apply:
        status = references_root() / "court-runtime" / "shiguan-service-daemon.json"
        task = run_command(["schtasks", "/Query", "/TN", "CourtShiguanDaemon"], timeout=20) if sys.platform == "win32" else {}
        return {
            "ok": True,
            "changed": False,
            "check_only": True,
            "script": str(script),
            "status_path": str(status),
            "status_exists": status.exists(),
            "task_exists": bool(task.get("ok")),
            "would_change": not status.exists() or (sys.platform == "win32" and not task.get("ok")),
        }
    result = run_command([sys.executable, str(script)], cwd=skill_root(), timeout=90)
    return {"ok": result["ok"], "changed": result["ok"], "script": str(script), "result": result}


def run_memory_bridge(apply: bool, result_json: str = "") -> dict[str, Any]:
    script = skill_root() / "scripts" / "internal_memory_shiguan_bridge.py"
    if not apply:
        result = run_command(
            [sys.executable, str(script), "inspect", "--agents", "all", "--content-mode", "metadata", "--format", "json"],
            cwd=skill_root(),
            timeout=60,
            stdout_limit=12000,
        )
        return {"ok": result["ok"], "changed": False, "mode": "inspect", "script": str(script), "result": result}
    args = [
        sys.executable,
        str(script),
        "record",
        "--agents",
        "all",
        "--content-mode",
        "metadata",
        "--format",
        "json",
        "--source-agent",
        "codex",
        "--refresh-mode",
        "async",
    ]
    if result_json:
        args.extend(["--result-json", result_json])
    result = run_command(args, cwd=skill_root(), timeout=90, stdout_limit=12000)
    return {"ok": result["ok"], "changed": result["ok"], "mode": "record", "script": str(script), "result": result}


def http_get_bytes(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "court-capability-router-bootstrap"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-approved bootstrap source.
        return response.read()


def fetch_release_assets(repo: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(http_get_bytes(GITHUB_API.format(repo=repo), timeout=30).decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []
    assets = data.get("assets")
    return assets if isinstance(assets, list) else []


def select_asset(repo: str, fallback_asset: str, regexes: list[str]) -> dict[str, str]:
    assets = fetch_release_assets(repo)
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in regexes]
    for pattern in compiled:
        for asset in assets:
            name = str(asset.get("name") or "")
            if pattern.search(name):
                return {
                    "url": str(asset.get("browser_download_url") or GITHUB_LATEST_DOWNLOAD.format(repo=repo, asset=name)),
                    "name": name,
                    "digest": str(asset.get("digest") or ""),
                    "source": "github_api",
                }
    return {
        "url": GITHUB_LATEST_DOWNLOAD.format(repo=repo, asset=fallback_asset),
        "name": fallback_asset,
        "digest": "",
        "source": "latest_download_fallback",
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checksum_from_digest(digest: str) -> str:
    text = digest.strip()
    if text.lower().startswith("sha256:"):
        return text.split(":", 1)[1].lower()
    if re.fullmatch(r"[a-fA-F0-9]{64}", text):
        return text.lower()
    return ""


def checksum_from_sidecar(asset_url: str) -> str:
    for suffix in (".sha256sum", ".sha256", ".sha256.txt"):
        try:
            text = http_get_bytes(asset_url + suffix, timeout=20).decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        match = re.search(r"\b([a-fA-F0-9]{64})\b", text)
        if match:
            return match.group(1).lower()
    return ""


def verify_download(name: str, data: bytes, expected: str, allow_unverified: bool) -> dict[str, Any]:
    actual = sha256_bytes(data)
    if expected:
        return {
            "ok": actual.lower() == expected.lower(),
            "status": "verified" if actual.lower() == expected.lower() else "mismatch",
            "sha256": actual,
            "expected_sha256": expected,
        }
    if allow_unverified:
        return {"ok": True, "status": "allowed_without_checksum", "sha256": actual, "expected_sha256": ""}
    return {
        "ok": False,
        "status": "checksum_unavailable",
        "sha256": actual,
        "expected_sha256": "",
        "reason": f"{name} release asset had no GitHub digest or sha256 sidecar",
    }


def extract_exe_from_zip(zip_bytes: bytes, exe_name: str, install_dir: Path) -> dict[str, Any]:
    install_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="court-tool-install-") as temp_text:
        temp = Path(temp_text)
        archive_path = temp / "tool.zip"
        archive_path.write_bytes(zip_bytes)
        with zipfile.ZipFile(archive_path) as archive:
            candidates = [name for name in archive.namelist() if Path(name).name.lower() == exe_name.lower()]
            if not candidates:
                return {"ok": False, "reason": f"{exe_name} not found in zip"}
            archive.extract(candidates[0], temp)
            source = temp / candidates[0]
            target = install_dir / exe_name
            if target.exists():
                backup_file(target)
            shutil.copy2(source, target)
    return {"ok": True, "target": str(install_dir / exe_name)}


def install_windows_zip_tool(
    *,
    tool: str,
    exe_name: str,
    repo: str,
    fallback_asset: str,
    regexes: list[str],
    install_dir: Path,
    apply: bool,
    allow_unverified: bool,
    version_args: list[str],
) -> dict[str, Any]:
    available_before = command_available(tool, install_dir)
    if available_before:
        version = run_command([tool, *version_args], timeout=20, install_dir=install_dir)
        return {"ok": True, "tool": tool, "available_before": True, "changed": False, "version": version}
    if sys.platform != "win32":
        return {"ok": False, "tool": tool, "changed": False, "reason": "automatic zip install is Windows-only"}
    asset = select_asset(repo, fallback_asset, regexes)
    if not apply:
        return {
            "ok": True,
            "tool": tool,
            "available_before": False,
            "changed": False,
            "would_install": True,
            "repo": repo,
            "asset": asset,
            "install_dir": str(install_dir),
        }
    try:
        zip_bytes = http_get_bytes(asset["url"], timeout=120)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "tool": tool, "changed": False, "repo": repo, "asset": asset, "reason": str(exc)}
    expected = checksum_from_digest(asset.get("digest", "")) or checksum_from_sidecar(asset["url"])
    verification = verify_download(tool, zip_bytes, expected, allow_unverified)
    if not verification["ok"]:
        return {
            "ok": False,
            "tool": tool,
            "changed": False,
            "repo": repo,
            "asset": asset,
            "verification": verification,
        }
    install = extract_exe_from_zip(zip_bytes, exe_name, install_dir)
    version = run_command([tool, *version_args], timeout=20, install_dir=install_dir) if install.get("ok") else {}
    return {
        "ok": bool(install.get("ok")) and bool(version.get("ok")),
        "tool": tool,
        "available_before": False,
        "changed": bool(install.get("ok")),
        "repo": repo,
        "asset": asset,
        "verification": verification,
        "install": install,
        "version": version,
    }


def ensure_squad_workspace(workspace: Path, install_dir: Path, apply: bool) -> dict[str, Any]:
    marker = workspace / ".squad"
    available = command_available("squad", install_dir)
    if not available:
        return {"ok": False, "changed": False, "workspace": str(workspace), "reason": "squad command unavailable"}
    if marker.exists():
        doctor = run_command(["squad", "doctor"], cwd=workspace, timeout=30, install_dir=install_dir)
        return {"ok": doctor["ok"], "changed": False, "workspace": str(workspace), "initialized": True, "doctor": doctor}
    if not apply:
        return {"ok": True, "changed": False, "would_init": True, "workspace": str(workspace)}
    init = run_command(["squad", "init"], cwd=workspace, timeout=60, install_dir=install_dir)
    doctor = run_command(["squad", "doctor"], cwd=workspace, timeout=30, install_dir=install_dir)
    return {
        "ok": init["ok"] and doctor["ok"],
        "changed": init["ok"],
        "workspace": str(workspace),
        "init": init,
        "doctor": doctor,
    }


def ensure_supercc_deps(args: argparse.Namespace) -> dict[str, Any]:
    install_dir = Path(args.install_dir).resolve()
    workspace = Path(args.workspace).resolve()
    zellij = install_windows_zip_tool(
        tool="zellij",
        exe_name="zellij.exe",
        repo=ZELLIJ_REPO,
        fallback_asset=ZELLIJ_ASSET,
        regexes=[r"zellij.*x86_64.*windows.*msvc.*\.zip$", r"zellij-x86_64-pc-windows-msvc\.zip$"],
        install_dir=install_dir,
        apply=args.apply,
        allow_unverified=args.allow_unverified_release_asset,
        version_args=["--version"],
    )
    squad = install_windows_zip_tool(
        tool="squad",
        exe_name="squad.exe",
        repo=SQUAD_REPO,
        fallback_asset=SQUAD_ASSET,
        regexes=[
            r"squad.*x86_64.*windows.*msvc.*\.zip$",
            r"squad.*windows.*x86_64.*\.zip$",
            r"squad-x86_64-pc-windows-msvc\.zip$",
        ],
        install_dir=install_dir,
        apply=args.apply,
        allow_unverified=args.allow_unverified_release_asset,
        version_args=["--version"],
    )
    squad_workspace = ensure_squad_workspace(workspace, install_dir, args.apply) if not args.no_squad_init else {
        "ok": True,
        "changed": False,
        "skipped": True,
        "reason": "--no-squad-init",
    }
    return {
        "ok": bool(zellij.get("ok")) and bool(squad.get("ok")) and bool(squad_workspace.get("ok")),
        "changed": bool(zellij.get("changed")) or bool(squad.get("changed")) or bool(squad_workspace.get("changed")),
        "install_dir": str(install_dir),
        "zellij": zellij,
        "squad": squad,
        "squad_workspace": squad_workspace,
        "sources": {
            "zellij": f"https://github.com/{ZELLIJ_REPO}/releases/latest",
            "squad": f"https://github.com/{SQUAD_REPO}/releases/latest",
        },
    }


def step_status(step: dict[str, Any]) -> str:
    if not step.get("ok"):
        return "FAILED"
    if step.get("changed"):
        return "CHANGED"
    if step.get("check_only"):
        return "CHECK_ONLY"
    if step.get("would_change"):
        return "WOULD_CHANGE"
    return "OK"


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.check_only:
        args.apply = False
    steps: dict[str, Any] = {}
    if not args.skip_supercc_deps:
        steps["supercc_dependencies"] = ensure_supercc_deps(args)
    if not args.supercc_deps_only:
        steps["shared_shiguan"] = ensure_shared(args.apply)
        if not args.skip_obsidian:
            steps["obsidian_shared_vault"] = ensure_obsidian(args.apply, args.set_open_obsidian)
        if not args.skip_service_daemon:
            steps["shiguan_service_daemon"] = ensure_service_daemon(args.apply)
        if not args.skip_memory:
            steps["codex_memory"] = enable_codex_memory(args.apply)
            steps["hermes_memory"] = enable_hermes_memory(args.apply)
        if not args.skip_memory_bridge:
            steps["memory_shiguan_bridge"] = run_memory_bridge(args.apply, args.result_json)
    ok = all(bool(step.get("ok")) for step in steps.values())
    changed = any(bool(step.get("changed")) for step in steps.values())
    return {
        "ok": ok,
        "mode": "apply" if args.apply else "check",
        "changed": changed,
        "generated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "skill_root": str(skill_root()),
        "workspace": str(Path(args.workspace).resolve()),
        "step_status": {name: step_status(step) for name, step in steps.items()},
        "steps": steps,
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        f"portable_bootstrap: {'PASSED' if payload.get('ok') else 'FAILED'}",
        f"mode: {payload.get('mode')} changed={payload.get('changed')}",
    ]
    for name, status in payload.get("step_status", {}).items():
        lines.append(f"{name}: {status}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write configs, install missing tools, and record the bridge.")
    parser.add_argument("--check-only", action="store_true", help="Inspect/plan without changing host state.")
    parser.add_argument("--supercc-deps-only", action="store_true", help="Only install/check zellij+squad and initialize the squad workspace.")
    parser.add_argument("--workspace", default=str(user_home()), help="Workspace for squad init and superCC runtime. Defaults to the current user's home directory.")
    parser.add_argument("--install-dir", default=str(default_install_dir()), help="Directory for zellij.exe and squad.exe. Defaults to C:\\Tools\\bin on Windows.")
    parser.add_argument("--skip-supercc-deps", action="store_true")
    parser.add_argument("--skip-obsidian", action="store_true")
    parser.add_argument("--skip-service-daemon", action="store_true")
    parser.add_argument("--skip-memory", action="store_true")
    parser.add_argument("--skip-memory-bridge", action="store_true")
    parser.add_argument("--set-open-obsidian", action="store_true", help="Mark the shared Shiguan vault as Obsidian's open vault.")
    parser.add_argument("--no-squad-init", action="store_true", help="Do not run squad init when the workspace lacks .squad.")
    parser.add_argument("--allow-unverified-release-asset", action="store_true", help="Install a release asset even if no sha256 digest/sidecar is available.")
    parser.add_argument("--result-json", default="", help="Optional result JSON path passed to the memory bridge archive command.")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = build_payload(args)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(payload))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
