"""Office-client selection and per-role client-map parsing for superCC."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any

sys.dont_write_bytecode = True


THREE_OFFICES = ("zhongshu", "menxia", "shangshu")
MINISTRY_OFFICES = ("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu")
INSPECTION_OFFICES = ("patrol-inspector",)
SPECIAL_OFFICES = ("shiguan",)
SUPERCC_VISIBLE_CORE_OFFICES = THREE_OFFICES
ALL_VISIBLE_OFFICES = (*SUPERCC_VISIBLE_CORE_OFFICES, *MINISTRY_OFFICES, *SPECIAL_OFFICES)
OFFICE_ROLE_KEYS = frozenset((*ALL_VISIBLE_OFFICES, *INSPECTION_OFFICES))
BUILTIN_OFFICE_CLIENTS = ("codex", "hermescli", "claude")
OFFICE_CLIENT_CHOICES = ("auto", *BUILTIN_OFFICE_CLIENTS, "cli")


def split_extra_cli_args(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        return shlex.split(value, posix=True)
    except ValueError:
        return [value]


def office_client_extra_args(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    raw_values = getattr(args, "office_client_arg", None) or []
    values.extend(str(item) for item in raw_values if str(item))
    values.extend(split_extra_cli_args(getattr(args, "office_client_args", None)))
    return values


def _map_raw_values(args: argparse.Namespace, attr: str, env_name: str) -> list[str]:
    values = [str(item) for item in (getattr(args, attr, None) or []) if str(item).strip()]
    env_value = os.environ.get(env_name)
    if env_value:
        values.append(env_value)
    return values


def _iter_key_value_map_entries(values: list[str]) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        candidates = [text]
        if "," in text:
            split_candidates = [part.strip() for part in text.split(",") if part.strip()]
            if split_candidates and all("=" in part for part in split_candidates):
                candidates = split_candidates
        for candidate in candidates:
            if "=" not in candidate:
                raise ValueError(f"expected role=value mapping, got {candidate!r}")
            key, mapped_value = candidate.split("=", 1)
            key = key.strip()
            mapped_value = mapped_value.strip()
            if not key or not mapped_value:
                raise ValueError(f"empty role or value in mapping {candidate!r}")
            entries.append((key, mapped_value))
    return entries


def expand_office_selection(selection: str | None) -> tuple[str, ...]:
    if not selection:
        return THREE_OFFICES
    roles: list[str] = []
    aliases = {
        "three": THREE_OFFICES,
        "三省": THREE_OFFICES,
        "visible-core": SUPERCC_VISIBLE_CORE_OFFICES,
        "core": SUPERCC_VISIBLE_CORE_OFFICES,
        "显性核心": SUPERCC_VISIBLE_CORE_OFFICES,
        "核心": SUPERCC_VISIBLE_CORE_OFFICES,
        "inspection": INSPECTION_OFFICES,
        "patrol": INSPECTION_OFFICES,
        "jiancha": INSPECTION_OFFICES,
        "监察": INSPECTION_OFFICES,
        "监察使": INSPECTION_OFFICES,
        "巡查": INSPECTION_OFFICES,
        "ministries": MINISTRY_OFFICES,
        "six": MINISTRY_OFFICES,
        "六部": MINISTRY_OFFICES,
        "special": SPECIAL_OFFICES,
        "史馆": SPECIAL_OFFICES,
        "scale": ALL_VISIBLE_OFFICES,
        "supercc-scale": ALL_VISIBLE_OFFICES,
        "官署scale": ALL_VISIBLE_OFFICES,
        "all": ALL_VISIBLE_OFFICES,
        "全部": ALL_VISIBLE_OFFICES,
    }
    for raw in re.split(r"[,;，；\s]+", selection):
        token = raw.strip()
        if not token:
            continue
        mapped = aliases.get(token)
        if mapped:
            roles.extend(mapped)
            continue
        if token not in OFFICE_ROLE_KEYS:
            raise ValueError(f"unknown office role: {token}")
        roles.append(token)
    ordered: list[str] = []
    for role in roles:
        if role not in ordered:
            ordered.append(role)
    return tuple(ordered)


def _roles_for_map_key(raw_key: str) -> tuple[str, ...]:
    key = raw_key.strip()
    if key in {"taizi", "太子"}:
        return ("taizi",)
    return expand_office_selection(key)


def parse_office_value_map(values: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw_key, raw_value in _iter_key_value_map_entries(values):
        for role in _roles_for_map_key(raw_key):
            mapping[role] = raw_value
    return mapping


def normalize_office_client_name(value: str) -> str:
    client = value.strip().lower()
    aliases = {
        "hermes": "hermescli",
        "hermes-cli": "hermescli",
        "claude-code": "claude",
        "claude_code": "claude",
        "generic": "cli",
        "custom": "cli",
    }
    return aliases.get(client, client)


def normalize_office_client_maps(args: argparse.Namespace) -> argparse.Namespace:
    client_values = _map_raw_values(args, "office_client_map", "COURT_OFFICE_CLIENT_MAP")
    command_values = _map_raw_values(args, "office_client_command_map", "COURT_OFFICE_CLIENT_COMMAND_MAP")
    args_values = _map_raw_values(args, "office_client_args_map", "COURT_OFFICE_CLIENT_ARGS_MAP")
    prompt_mode_values = _map_raw_values(args, "office_client_prompt_mode_map", "COURT_OFFICE_CLIENT_PROMPT_MODE_MAP")

    command_map = parse_office_value_map(command_values)
    client_map: dict[str, str] = {}
    for role, client in parse_office_value_map(client_values).items():
        normalized = normalize_office_client_name(client)
        if normalized not in OFFICE_CLIENT_CHOICES:
            client_map[role] = "cli"
            command_map.setdefault(role, client.strip())
            continue
        client_map[role] = normalized

    prompt_mode_map: dict[str, str] = {}
    for role, mode in parse_office_value_map(prompt_mode_values).items():
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"argument", "stdin"}:
            raise ValueError(f"unknown prompt mode {mode!r} for role {role}; choices: argument, stdin")
        prompt_mode_map[role] = normalized_mode

    args.office_client_map_resolved = client_map
    args.office_client_command_map_resolved = command_map
    args.office_client_args_map_resolved = {
        role: split_extra_cli_args(value)
        for role, value in parse_office_value_map(args_values).items()
    }
    args.office_client_prompt_mode_map_resolved = prompt_mode_map
    return args


def office_client_for_role(args: argparse.Namespace, role: str) -> str:
    role_map = getattr(args, "office_client_map_resolved", {}) or {}
    requested = role_map.get(role)
    if requested and requested != "auto":
        return str(requested)
    return str(getattr(args, "office_client", "codex"))


def office_client_command_for_role(args: argparse.Namespace, role: str) -> str | None:
    command_map = getattr(args, "office_client_command_map_resolved", {}) or {}
    return command_map.get(role) or getattr(args, "office_client_command", None)


def office_client_extra_args_for_role(args: argparse.Namespace, role: str) -> list[str]:
    args_map = getattr(args, "office_client_args_map_resolved", {}) or {}
    return list(args_map.get(role) or office_client_extra_args(args))


def office_client_prompt_mode_for_role(args: argparse.Namespace, role: str) -> str:
    mode_map = getattr(args, "office_client_prompt_mode_map_resolved", {}) or {}
    return str(mode_map.get(role) or getattr(args, "office_client_prompt_mode", "argument"))


def office_client_role_plan(args: argparse.Namespace, roles: tuple[str, ...] | list[str]) -> dict[str, dict[str, Any]]:
    plan: dict[str, dict[str, Any]] = {}
    for role in roles:
        client = office_client_for_role(args, role)
        plan[role] = {
            "office_client": client,
            "command": office_client_command_for_role(args, role) if client == "cli" else None,
            "args": office_client_extra_args_for_role(args, role) if client == "cli" else [],
            "prompt_mode": office_client_prompt_mode_for_role(args, role) if client == "cli" else None,
            "selection": "role_map" if role in (getattr(args, "office_client_map_resolved", {}) or {}) else getattr(args, "office_client_selection_source", None),
        }
    return plan


def _tool_env() -> dict[str, str]:
    env = dict(os.environ)
    profile = os.environ.get("USERPROFILE") if os.name == "nt" else None
    if profile and not env.get("HOME"):
        env["HOME"] = profile
    tools_bin = env.get("COURT_TOOLS_BIN")
    current_path = env.get("PATH", "")
    if tools_bin and tools_bin.lower() not in current_path.lower():
        env["PATH"] = tools_bin + os.pathsep + current_path
    return env


def current_process_chain_signals(limit: int = 8) -> list[str]:
    if os.name != "nt":
        return []
    script = "\n".join(
        [
            f"$currentProcessId = {os.getpid()}",
            f"for ($i = 0; $i -lt {max(1, int(limit))}; $i++) {{",
            '  $p = Get-CimInstance Win32_Process -Filter "ProcessId=$currentProcessId" -ErrorAction SilentlyContinue',
            "  if ($null -eq $p) { break }",
            '  "pid=$($p.ProcessId);name=$($p.Name)"',
            "  if ($null -eq $p.ParentProcessId -or $p.ParentProcessId -eq 0) { break }",
            "  $currentProcessId = $p.ParentProcessId",
            "}",
        ]
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            env=_tool_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def cli_source_signals() -> dict[str, Any]:
    env = os.environ
    env_names = set(env)
    raw_skill_path = str(Path(__file__)).lower()
    cwd = str(Path.cwd()).lower()

    explicit_client = normalize_office_client_name(
        (env.get("COURT_OFFICE_CLIENT") or env.get("COURT_SOURCE_CLI") or "").strip()
    )
    explicit_command = (env.get("COURT_OFFICE_CLIENT_COMMAND") or env.get("COURT_SOURCE_CLI_COMMAND") or "").strip()
    if explicit_client in BUILTIN_OFFICE_CLIENTS or explicit_client == "cli":
        return {
            "office_client": explicit_client,
            "source": "env_explicit_client",
            "command": explicit_command or None,
            "signals": [f"explicit_client={explicit_client}"],
        }
    if explicit_client:
        return {
            "office_client": "cli",
            "source": "env_explicit_generic_client",
            "command": explicit_command or explicit_client,
            "signals": [f"explicit_generic_client={explicit_client}"],
        }
    if explicit_command:
        return {
            "office_client": "cli",
            "source": "env_explicit_command",
            "command": explicit_command,
            "signals": ["COURT_OFFICE_CLIENT_COMMAND|COURT_SOURCE_CLI_COMMAND"],
        }

    strong_codex_signals = [
        name
        for name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_AGENT_ID")
        if env.get(name)
    ]
    if strong_codex_signals:
        return {
            "office_client": "codex",
            "source": "auto_current_cli_env_strong",
            "command": None,
            "signals": strong_codex_signals,
        }

    claude_signals = [name for name in env_names if name.startswith("CLAUDE") or name.startswith("ANTHROPIC")]
    if claude_signals:
        return {"office_client": "claude", "source": "auto_current_cli_env", "command": None, "signals": sorted(claude_signals)}
    codex_signals = [name for name in env_names if name.startswith("CODEX")]
    if codex_signals:
        return {"office_client": "codex", "source": "auto_current_cli_env", "command": None, "signals": sorted(codex_signals)}

    process_signals = current_process_chain_signals()
    process_text = "\n".join(process_signals).lower()
    if "claude" in process_text or "anthropic" in process_text:
        return {"office_client": "claude", "source": "auto_process_chain", "command": None, "signals": process_signals}
    if "codex" in process_text:
        return {"office_client": "codex", "source": "auto_process_chain", "command": None, "signals": process_signals}
    if "hermes" in process_text:
        return {"office_client": "hermescli", "source": "auto_process_chain", "command": None, "signals": process_signals}

    if ".claude" in raw_skill_path or ".claude" in cwd:
        return {"office_client": "claude", "source": "auto_current_cli_path", "command": None, "signals": ["path:.claude"]}
    if ".codex" in raw_skill_path or ".codex" in cwd:
        return {"office_client": "codex", "source": "auto_current_cli_path", "command": None, "signals": ["path:.codex"]}

    hermes_strong = [name for name in env_names if name in {"HERMES_PROFILE", "HERMES_SESSION", "HERMES_SURFACE", "HERMES_SOURCE_AGENT"}]
    hermes_fallback = [name for name in env_names if name.startswith("HERMES")]
    if hermes_strong or hermes_fallback or ".hermes" in raw_skill_path or ".hermes" in cwd:
        return {
            "office_client": "hermescli",
            "source": "auto_current_cli",
            "command": None,
            "signals": sorted(hermes_strong or hermes_fallback) or ["path:.hermes"],
        }

    return {
        "office_client": "hermescli",
        "source": "fallback_hermescli_no_cli_signal",
        "command": None,
        "signals": [],
    }


def resolve_office_client_args(args: argparse.Namespace) -> argparse.Namespace:
    raw_requested = (getattr(args, "office_client", None) or "auto").strip()
    requested = normalize_office_client_name(raw_requested)
    if requested not in OFFICE_CLIENT_CHOICES:
        args.requested_office_client = requested
        args.office_client = "cli"
        args.office_client_selection_source = "explicit_argument_generic_client"
        args.office_client_selection_signals = [f"explicit_generic_client={raw_requested}"]
        if not getattr(args, "office_client_command", None):
            args.office_client_command = raw_requested
        return args
    args.requested_office_client = requested
    if requested != "auto":
        args.office_client = requested
        args.office_client_selection_source = "explicit_argument"
        args.office_client_selection_signals = []
        return args

    selection = cli_source_signals()
    args.office_client = selection["office_client"]
    args.office_client_selection_source = selection["source"]
    args.office_client_selection_signals = selection.get("signals", [])
    if selection.get("command") and not getattr(args, "office_client_command", None):
        args.office_client_command = selection["command"]
    return args
