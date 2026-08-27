"""Read-only diagnostics shared by the public doctor and debug commands."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tomllib
import uuid
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
NAME = "decretum-matrix"
GITHUB_REPOSITORY = "https://github.com/RowlandL/decretum-matrix"
PROJECTION_PATH = Path("references/manifests/install-projection.v1.json")
CLI_MANIFEST_PATH = Path("references/manifests/cli-command-surface.v1.json")
TEXT_SUFFIXES = frozenset({".cmd", ".js", ".json", ".mjs", ".ps1", ".py", ".sh", ".toml", ".yaml", ".yml"})
PATH_PATTERN = re.compile(
    r"(?ix)"
    r"(?:"
    r"[a-z]:\\(?:users\\[^\\\s\"']+|project(?:\\|$)|gitmirror(?:\\|$))"
    r"|\\\\\d{1,3}(?:\.\d{1,3}){3}\\[^\s\"']+"
    r"|/(?:Users|home)/[^/\s\"']+"
    r"|/mnt/[a-z]/Users/[^/\s\"']+"
    r")"
)


def _audit_base() -> tuple[Path, str]:
    """Resolve the canonical workspace event root without embedding a host path."""

    for candidate in (ROOT, *ROOT.parents):
        control = candidate / ".repo-control"
        if control.is_dir() and (candidate / "workspace.yaml").is_file():
            return control / "events", "workspace_repo_control"
    return (
        Path.home() / ".agents" / "court-shiguan" / NAME / "diagnostic-events",
        "runtime_fallback",
    )


def write_audit_event(
    *,
    task: str,
    operation: str,
    phase: str,
    status: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """Append one schema-compatible event and return its redacted location."""

    event_id = (
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-"
        f"{uuid.uuid4().hex}"
    )
    base, location = _audit_base()
    event_dir = base / NAME / task
    event_dir.mkdir(parents=True, exist_ok=True)
    event = {
        "schema": "workspace.operation_event.v1",
        "schema_version": 1,
        "event_id": event_id,
        "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": NAME,
        "project": NAME,
        "task": task,
        "operation": operation,
        "action": operation,
        "phase": phase,
        "status": status,
        "payload": {**payload, "audit_location": location},
    }
    path = event_dir / f"{event_id}.json"
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)
    return {"event_id": event_id, "path": str(path), "location": location}


def resolve_user_path(value: str | None, *, default: Path) -> Path:
    path = Path(value).expanduser() if value else default
    if not path.is_absolute():
        path = Path.cwd() / path
    return Path(os.path.abspath(os.fspath(path)))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_head(root: Path) -> tuple[str | None, str | None]:
    completed = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={root.as_posix()}",
            "-C",
            str(root),
            "rev-parse",
            "HEAD",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=False,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value:
        return None, f"git_head_unavailable:{completed.returncode}"
    return value, None


def _git_state(root: Path) -> dict[str, object]:
    commands = {
        "branch": ["branch", "--show-current"],
        "head": ["rev-parse", "HEAD"],
        "status": ["status", "--short"],
    }
    values: dict[str, object] = {}
    for key, arguments in commands.items():
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
        )
        values[key] = completed.stdout.strip() if completed.returncode == 0 else None
        if completed.returncode != 0:
            values[f"{key}_error"] = completed.returncode
    status_lines = str(values.get("status") or "").splitlines()
    values["change_count"] = len(status_lines)
    values["changes"] = status_lines[:50]
    return values


def _source_identity(root: Path) -> tuple[dict[str, object] | None, str | None]:
    required = (root / "VERSION", root / CLI_MANIFEST_PATH, root / PROJECTION_PATH)
    missing = [path.relative_to(root).as_posix() for path in required if not path.is_file()]
    if missing:
        return None, "source_contract_missing:" + ",".join(missing)
    try:
        git_head, git_head_error = _git_head(root)
        return {
            "version": (root / "VERSION").read_text(encoding="utf-8").strip(),
            "cli_manifest_sha256": sha256(root / CLI_MANIFEST_PATH),
            "projection_manifest_sha256": sha256(root / PROJECTION_PATH),
            "git_head": git_head,
            "git_head_error": git_head_error,
        }, None
    except OSError as exc:
        return None, f"source_contract_unreadable:{type(exc).__name__}:{exc}"


def _compare_source_identity(
    requested: dict[str, object],
    mapped: dict[str, object],
) -> tuple[bool, str]:
    fields = ("version", "cli_manifest_sha256", "projection_manifest_sha256")
    if any(requested.get(field) != mapped.get(field) for field in fields):
        return False, "artifact_identity_mismatch"
    requested_head = requested.get("git_head")
    mapped_head = mapped.get("git_head")
    if isinstance(requested_head, str) and isinstance(mapped_head, str):
        if requested_head != mapped_head:
            return False, "git_head_mismatch"
        return True, "verified"
    return True, "artifact_verified_git_head_unavailable"


def select_source(
    *,
    source_root: str | None,
    mapped_root: str | None,
) -> dict[str, object]:
    requested = resolve_user_path(source_root, default=ROOT)
    requested_identity, requested_error = _source_identity(requested)
    result: dict[str, object] = {
        "requested_root": str(requested),
        "mapped_root": None,
        "selected_root": None,
        "fallback_reason": None,
        "identity": None,
        "mapped_root_verified": None,
        "equivalence_status": None,
    }
    if requested_identity is not None:
        result["selected_root"] = str(requested)
        result["identity"] = requested_identity
        if mapped_root:
            mapped = resolve_user_path(mapped_root, default=ROOT)
            mapped_identity, mapped_error = _source_identity(mapped)
            result["mapped_root"] = str(mapped)
            if mapped_identity is not None:
                equivalent, status = _compare_source_identity(
                    requested_identity, mapped_identity
                )
                result["mapped_root_verified"] = equivalent
                result["equivalence_status"] = status
            else:
                result["mapped_root_verified"] = False
            if mapped_error is not None:
                result["mapped_root_error"] = mapped_error
        return result

    result["requested_root_error"] = requested_error or "requested_source_unavailable"
    if not mapped_root:
        return result
    mapped = resolve_user_path(mapped_root, default=ROOT)
    mapped_identity, mapped_error = _source_identity(mapped)
    result["mapped_root"] = str(mapped)
    if mapped_identity is None:
        result["mapped_root_error"] = mapped_error or "mapped_source_unavailable"
        return result
    result.update(
        {
            "selected_root": str(mapped),
            "fallback_reason": "requested_source_unavailable",
            "identity": mapped_identity,
            "mapped_root_verified": True,
            "equivalence_status": "requested_source_unavailable",
        }
    )
    return result


def _read_projection(root: Path) -> tuple[set[str], list[str]]:
    try:
        manifest = json.loads((root / PROJECTION_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return set(), [f"projection_manifest_unreadable:{type(exc).__name__}:{exc}"]
    projections = manifest.get("projections") if isinstance(manifest, dict) else None
    if not isinstance(projections, dict):
        return set(), ["projection_manifest_invalid"]
    selected: set[str] = set()
    for name in ("shared_agents", "portable_current_tool", "cli_public"):
        values = projections.get(name)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            return set(), [f"projection_invalid:{name}"]
        selected.update(values)
    return selected, []


def _projected_files(root: Path, entries: set[str]) -> tuple[dict[str, Path], list[str]]:
    files: dict[str, Path] = {}
    problems: list[str] = []
    for entry in sorted(entries):
        candidate = root / Path(entry)
        if candidate.is_symlink():
            problems.append(f"projection_symlink:{entry}")
            continue
        if candidate.is_file():
            files[entry.replace("\\", "/")] = candidate
            continue
        if not candidate.is_dir():
            problems.append(f"projection_source_missing:{entry}")
            continue
        for current, directories, names in os.walk(candidate, followlinks=False):
            current_path = Path(current)
            directories[:] = [
                name for name in directories if not (current_path / name).is_symlink()
            ]
            for name in names:
                path = current_path / name
                if path.is_symlink() or not path.is_file():
                    problems.append(
                        "projection_nonregular:" + path.relative_to(root).as_posix()
                    )
                    continue
                files[path.relative_to(root).as_posix()] = path
    return files, problems


def _tree_files(root: Path) -> tuple[dict[str, Path], list[str]]:
    files: dict[str, Path] = {}
    problems: list[str] = []
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name
            for name in directories
            if name != "__pycache__" and not (current_path / name).is_symlink()
        ]
        for name in names:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.suffix.lower() == ".pyc":
                continue
            if path.is_symlink() or not path.is_file():
                problems.append(f"target_nonregular:{relative}")
                continue
            files[relative] = path
    return files, problems


def _compare_projection(source: Path, home: Path) -> dict[str, object]:
    entries, problems = _read_projection(source)
    source_files, source_problems = _projected_files(source, entries)
    problems.extend(source_problems)
    targets = {
        "shared_agents": home / ".agents" / "skills" / NAME,
        "codex": home / ".codex" / "skills" / NAME,
    }
    target_results: dict[str, object] = {}
    for label, target in targets.items():
        if not target.is_dir() or target.is_symlink():
            target_results[label] = {
                "root": str(target),
                "status": "MISSING",
                "matches": False,
                "missing_count": len(source_files),
                "mismatched_count": 0,
                "unexpected_count": 0,
                "samples": [],
            }
            continue
        target_files, target_problems = _tree_files(target)
        missing = sorted(set(source_files) - set(target_files))
        unexpected = sorted(set(target_files) - set(source_files))
        mismatched = sorted(
            relative
            for relative in set(source_files).intersection(target_files)
            if sha256(source_files[relative]) != sha256(target_files[relative])
        )
        samples = [
            *[f"missing:{value}" for value in missing[:8]],
            *[f"mismatched:{value}" for value in mismatched[:8]],
            *[f"unexpected:{value}" for value in unexpected[:8]],
            *target_problems[:8],
        ]
        matches = not missing and not unexpected and not mismatched and not target_problems
        target_results[label] = {
            "root": str(target),
            "status": "MATCH" if matches else "DRIFT",
            "matches": matches,
            "missing_count": len(missing),
            "mismatched_count": len(mismatched),
            "unexpected_count": len(unexpected),
            "samples": samples,
        }
    return {
        "expected_file_count": len(source_files),
        "source_problems": problems,
        "targets": target_results,
    }


def _mcp_config(home: Path) -> dict[str, object]:
    config = home / ".codex" / "config.toml"
    if not config.is_file():
        return {"status": "MISSING", "configured": False, "config_path": str(config)}
    try:
        parsed = tomllib.loads(config.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {
            "status": "INVALID",
            "configured": False,
            "config_path": str(config),
            "reason": f"config_unreadable:{type(exc).__name__}",
        }
    servers = parsed.get("mcp_servers") if isinstance(parsed, dict) else None
    server = servers.get("decretum_matrix") if isinstance(servers, dict) else None
    if not isinstance(server, dict):
        return {"status": "MISSING", "configured": False, "config_path": str(config)}
    command = server.get("command")
    arguments = server.get("args")
    server_script = ""
    if isinstance(arguments, list):
        python_scripts = [value for value in arguments if isinstance(value, str) and value.endswith(".py")]
        if python_scripts:
            server_script = Path(python_scripts[-1]).name
    configured = isinstance(command, str) and isinstance(arguments, list)
    runtime_probe: dict[str, object] = {"status": "NOT_RUN", "ok": False}
    if configured and server_script == "court_mcp_server.py":
        runtime_probe = _probe_mcp_server(
            Path(command),
            [str(value) for value in arguments],
            base_dir=config.parent,
        )
    return {
        "status": "CONFIGURED" if configured else "INVALID",
        "configured": configured,
        "config_path": str(config),
        "command_basename": Path(command).name if isinstance(command, str) else None,
        "server_script": server_script or None,
        "startup_timeout_sec": server.get("startup_timeout_sec"),
        "runtime_probe": runtime_probe,
        "secret_values_exposed": False,
    }


def _probe_mcp_server(
    command: Path,
    arguments: list[str],
    *,
    base_dir: Path,
) -> dict[str, object]:
    command_path = command if command.is_absolute() else Path(shutil.which(str(command)) or command)
    script_values = [value for value in arguments if value.endswith(".py")]
    script = Path(script_values[-1]) if script_values else None
    if script is not None and not script.is_absolute():
        script = base_dir / script
    if not command_path.is_file() or script is None or not script.is_file():
        return {"status": "MISSING", "ok": False}
    modern_meta = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "decretum-doctor", "version": "1"},
    }
    modern_messages = (
        {
            "jsonrpc": "2.0",
            "id": "modern-discover",
            "method": "server/discover",
            "params": {"_meta": modern_meta},
        },
        {
            "jsonrpc": "2.0",
            "id": "modern-tools",
            "method": "tools/list",
            "params": {"_meta": modern_meta},
        },
        {
            "jsonrpc": "2.0",
            "id": "modern-status",
            "method": "tools/call",
            "params": {
                "_meta": modern_meta,
                "name": "court.status",
                "arguments": {},
            },
        },
    )
    legacy_messages = (
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "decretum-doctor", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {"_meta": {"progressToken": "decretum-doctor"}},
        },
    )

    def run_messages(messages: tuple[dict[str, object], ...]) -> tuple[int, str, list[dict[str, object]]]:
        completed = subprocess.run(
            [str(command_path), *arguments],
            input="\n".join(json.dumps(message) for message in messages) + "\n",
            cwd=script.parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
            shell=False,
        )
        responses = [
            json.loads(line)
            for line in completed.stdout.splitlines()
            if line.strip()
        ]
        return completed.returncode, completed.stderr, responses

    try:
        modern_exit, modern_stderr, modern_responses = run_messages(modern_messages)
        legacy_exit, legacy_stderr, legacy_responses = run_messages(legacy_messages)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "ok": False, "reason": type(exc).__name__}

    discover = next((item for item in modern_responses if item.get("id") == "modern-discover"), {})
    modern_tools_response = next((item for item in modern_responses if item.get("id") == "modern-tools"), {})
    modern_status = next((item for item in modern_responses if item.get("id") == "modern-status"), {})
    legacy_initialize = next((item for item in legacy_responses if item.get("id") == 1), {})
    legacy_tools_response = next((item for item in legacy_responses if item.get("id") == 2), {})

    def names_from(response: dict[str, object]) -> list[str]:
        result = response.get("result")
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return sorted(
            str(item.get("name"))
            for item in tools
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        )

    modern_names = names_from(modern_tools_response)
    legacy_names = names_from(legacy_tools_response)
    expected = {
        "court.command_help",
        "court.status",
        "memory.scan",
        "shiguan.archive_dry_run",
        "shiguan.query",
    }
    discover_result = discover.get("result") if isinstance(discover, dict) else None
    modern_tools_result = modern_tools_response.get("result") if isinstance(modern_tools_response, dict) else None
    modern_status_result = modern_status.get("result") if isinstance(modern_status, dict) else None
    legacy_initialize_result = legacy_initialize.get("result") if isinstance(legacy_initialize, dict) else None
    modern_ok = (
        modern_exit == 0
        and isinstance(discover_result, dict)
        and discover_result.get("resultType") == "complete"
        and "2026-07-28" in discover_result.get("supportedVersions", [])
        and isinstance(modern_tools_result, dict)
        and modern_tools_result.get("resultType") == "complete"
        and set(modern_names) == expected
        and isinstance(modern_status_result, dict)
        and modern_status_result.get("isError") is not True
    )
    legacy_ok = (
        legacy_exit == 0
        and isinstance(legacy_initialize_result, dict)
        and legacy_initialize_result.get("protocolVersion") == "2025-11-25"
        and set(legacy_names) == expected
        and not any("error" in response for response in legacy_responses)
    )
    return {
        "status": "PASS" if modern_ok and legacy_ok else "FAIL",
        "ok": modern_ok and legacy_ok,
        "protocol_version": "2026-07-28",
        "modern": {
            "ok": modern_ok,
            "exit_code": modern_exit,
            "stderr_empty": not modern_stderr.strip(),
            "tool_count": len(modern_names),
            "tool_names": modern_names,
        },
        "legacy": {
            "ok": legacy_ok,
            "exit_code": legacy_exit,
            "stderr_empty": not legacy_stderr.strip(),
            "tool_count": len(legacy_names),
            "tool_names": legacy_names,
        },
        "tool_count": len(modern_names),
        "tool_names": modern_names,
    }


def _is_fixture_or_test(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return (
        "fixtures" in parts
        or "tests" in parts
        or path.name.startswith(("check_", "test_"))
        or path.name.endswith("_fixture.py")
    )


def scan_hardcoded_paths(root: Path) -> dict[str, object]:
    production: list[dict[str, object]] = []
    fixture_or_test: list[dict[str, object]] = []
    scanned = 0
    for relative_root in ("scripts", "bin", "agents", "hooks", ".codex-plugin"):
        directory = root / relative_root
        if not directory.is_dir():
            continue
        for current, directories, names in os.walk(directory, followlinks=False):
            current_path = Path(current)
            directories[:] = [
                name for name in directories if not (current_path / name).is_symlink()
            ]
            for name in names:
                path = current_path / name
                if path.suffix.lower() not in TEXT_SUFFIXES or path.is_symlink():
                    continue
                if path.resolve(strict=False) == Path(__file__).resolve(strict=False):
                    continue
                scanned += 1
                try:
                    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                destination = fixture_or_test if _is_fixture_or_test(path.relative_to(root)) else production
                for line_number, line in enumerate(lines, start=1):
                    if PATH_PATTERN.search(line):
                        destination.append(
                            {"path": path.relative_to(root).as_posix(), "line": line_number}
                        )
    return {
        "scanned_file_count": scanned,
        "production_hardcoded_path_count": len(production),
        "fixture_hardcoded_path_count": len(fixture_or_test),
        "production_samples": production[:20],
        "fixture_samples": fixture_or_test[:20],
        "policy_source_skipped": Path(__file__).name,
    }


def _codex_agent_roles(home: Path) -> dict[str, object]:
    """Reuse the existing native-role checker for the selected home."""

    try:
        module = importlib.import_module("check_codex_agent_roles")
        result = module.validate_installed_agents(
            agents_dir=home / ".codex" / "agents",
        )
        return result if isinstance(result, dict) else {"ok": False, "status": "INVALID"}
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        return {
            "ok": False,
            "status": "ERROR",
            "reason": f"codex_agent_roles_check_failed:{type(exc).__name__}",
        }


def doctor(
    *,
    source_root: str | None = None,
    mapped_root: str | None = None,
    home_root: str | None = None,
    audit_enabled: bool = True,
) -> dict[str, object]:
    audit = (
        write_audit_event(
            task="doctor-current-thread",
            operation="doctor",
            phase="intent",
            status="started",
            payload={"source_root": source_root, "mapped_root": mapped_root, "home_root": home_root},
        )
        if audit_enabled
        else None
    )
    source_selection = select_source(source_root=source_root, mapped_root=mapped_root)
    selected_raw = source_selection.get("selected_root")
    if not isinstance(selected_raw, str):
        result = {
            "schema": "decretum.doctor.v1",
            "ok": False,
            "healthy": False,
            "status": "BLOCKED",
            "source_selection": source_selection,
            "private_body_accessed": False,
            "secret_values_exposed": False,
        }
        if audit is not None:
            result["audit_intent"] = audit
            result["audit_result"] = write_audit_event(
                task="doctor-current-thread",
                operation="doctor",
                phase="result",
                status="failed",
                payload={"status": result["status"], "source_selection": source_selection},
            )
        return result
    source = Path(selected_raw)
    home = resolve_user_path(home_root, default=Path.home())
    projection = _compare_projection(source, home)
    path_policy = scan_hardcoded_paths(source)
    mcp = _mcp_config(home)
    codex_agent_roles = _codex_agent_roles(home)
    target_matches = [
        bool(item.get("matches"))
        for item in projection["targets"].values()
        if isinstance(item, dict)
    ]
    health_checks = {
        "source_contract": not projection["source_problems"],
        "managed_projection": bool(target_matches) and all(target_matches),
        "mcp_configuration": mcp.get("configured") is True,
        "mcp_runtime_probe": mcp.get("runtime_probe", {}).get("ok") is True,
        "codex_agent_roles": codex_agent_roles.get("ok") is True,
        "production_path_portability": path_policy["production_hardcoded_path_count"] == 0,
    }
    healthy = all(health_checks.values())
    result = {
        "schema": "decretum.doctor.v1",
        "ok": True,
        "healthy": healthy,
        "status": "PASS" if healthy else "DRIFT",
        "source_authority": {
            "current_mode": "local_development",
            "future_default": "github_release",
            "github_repository": GITHUB_REPOSITORY,
            "network_fetch_enabled": False,
        },
        "source_selection": source_selection,
        "install_projection": projection,
        "mcp_configuration": mcp,
        "codex_agent_roles": codex_agent_roles,
        "health_checks": health_checks,
        "path_policy": path_policy,
        "private_body_accessed": False,
        "secret_values_exposed": False,
    }
    if audit is not None:
        result["audit_intent"] = audit
        result["audit_result"] = write_audit_event(
            task="doctor-current-thread",
            operation="doctor",
            phase="result",
            status="succeeded",
            payload={
                "status": result["status"],
                "healthy": healthy,
                "source_selection": source_selection,
                "health_checks": health_checks,
            },
        )
    return result


def debug(
    *,
    source_root: str | None = None,
    mapped_root: str | None = None,
    home_root: str | None = None,
) -> dict[str, object]:
    audit = write_audit_event(
        task="debug-current-thread",
        operation="debug",
        phase="intent",
        status="started",
        payload={"source_root": source_root, "mapped_root": mapped_root, "home_root": home_root},
    )
    result = doctor(
        source_root=source_root,
        mapped_root=mapped_root,
        home_root=home_root,
        audit_enabled=False,
    )
    payload = {
        "schema": "decretum.debug.v1",
        "ok": result.get("ok") is True,
        "status": result.get("status"),
        "doctor": result,
        "source_selection": result.get("source_selection"),
        "runtime": {
            "python_version": sys.version.split()[0],
            "python_executable": Path(sys.executable).name,
            "platform": platform.platform(),
            "os_name": os.name,
            "runtime_root": str(ROOT),
        },
        "git": _git_state(Path(str(result.get("source_selection", {}).get("selected_root") or ROOT))),
        "private_body_accessed": False,
        "secret_values_exposed": False,
    }
    payload["audit_intent"] = audit
    payload["audit_result"] = write_audit_event(
        task="debug-current-thread",
        operation="debug",
        phase="result",
        status="succeeded" if result.get("ok") is True else "failed",
        payload={"status": payload["status"], "source_selection": payload["source_selection"]},
    )
    return payload


def command_main(command: str, argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=f"Decretum Matrix {command} diagnostics")
    parser.add_argument("--source-root")
    parser.add_argument("--mapped-root")
    parser.add_argument("--home-root")
    parser.add_argument("--format", choices=("text", "json"), default="json")
    args = parser.parse_args(argv)
    if command == "doctor":
        result = doctor(
            source_root=args.source_root,
            mapped_root=args.mapped_root,
            home_root=args.home_root,
        )
    elif command == "debug":
        result = debug(
            source_root=args.source_root,
            mapped_root=args.mapped_root,
            home_root=args.home_root,
        )
    else:
        raise ValueError(f"unsupported diagnostic command: {command}")
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{command.upper()}_{result.get('status', 'UNKNOWN')}")
    if command == "doctor":
        return 0 if result.get("healthy") is True else 2
    return 0 if result.get("ok") is True else 2
