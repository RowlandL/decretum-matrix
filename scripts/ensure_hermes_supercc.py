"""Validate Hermes superCC runtime selection without mutating Hermes state.

This script is intentionally read-only. It checks the Hermes profile-native
surface used by Decretum Matrix and reports whether Hermes CLI or
desktop readiness exists. A normal superCC environment still requires the
current execution surface to prove zellij plus squad; profile-native readiness
alone is never a passing superCC environment.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from typing import Any

from court_platform import user_data_base


ROLE_PROFILE_MAP = {
    "taizi": "taizi",
    "zhongshu": "zhongshu",
    "menxia": "menxia",
    "shangshu": "shangshu",
    "libu-hr": "libu-hr",
    "hubu": "hubu",
    "libu": "libu",
    "bingbu": "bingbu",
    "xingbu": "xingbu",
    "gongbu": "gongbu",
    "shiguan": "shiguan",
}

DESKTOP_SOURCE_CHECKS = {
    "desktop_profile_store": (
        Path("hermes-agent") / "apps" / "desktop" / "src" / "store" / "profile.ts",
        ["ensureGatewayProfile", "activeGatewayProfile"],
    ),
    "desktop_session_actions": (
        Path("hermes-agent")
        / "apps"
        / "desktop"
        / "src"
        / "app"
        / "session"
        / "hooks"
        / "use-session-actions.ts",
        ["session.create", "profile"],
    ),
    "desktop_bridge_types": (
        Path("hermes-agent") / "apps" / "desktop" / "src" / "global.d.ts",
        ["getConnection", "profile"],
    ),
    "gateway_profile_binding": (
        Path("hermes-agent") / "tui_gateway" / "server.py",
        ["profile_home", "HERMES_HOME"],
    ),
    "dashboard_profile_binding": (
        Path("hermes-agent") / "hermes_cli" / "web_server.py",
        ["profile_home", "HERMES_HOME"],
    ),
}


def run_command(command: list[str], timeout: int = 20) -> dict[str, Any]:
    env = os.environ.copy()
    if os.name == "nt" and "HOME" not in env and env.get("USERPROFILE"):
        env["HOME"] = env["USERPROFILE"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "returncode": None,
            "args": command,
            "error": f"not_found: {exc}",
            "stdout": "",
            "stderr": "",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "args": command,
            "error": f"timeout_after_{timeout}s",
            "stdout": (exc.stdout or "")[:4000],
            "stderr": (exc.stderr or "")[:4000],
        }
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "args": command,
        "stdout": completed.stdout[:4000],
        "stderr": completed.stderr[:4000],
    }


def default_hermes_root() -> Path:
    configured = os.environ.get("COURT_HERMES_ROOT")
    if configured:
        return Path(configured)
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        path = Path(hermes_home)
        if path.name.lower() == "hermes":
            return path
    local = user_data_base() / "hermes"
    if local.exists():
        return local
    return Path.home() / ".hermes"


def parse_profiles(raw: str | None) -> dict[str, str]:
    if not raw:
        return ROLE_PROFILE_MAP.copy()
    selected: dict[str, str] = {}
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        if "=" in value:
            role, profile = value.split("=", 1)
            selected[role.strip()] = profile.strip()
        else:
            selected[value] = ROLE_PROFILE_MAP.get(value, value)
    return selected


def summarize_active_sessions(profile_home: Path) -> dict[str, Any]:
    """Return metadata-only active-session evidence for a Hermes profile."""
    active_sessions = profile_home / "runtime" / "active_sessions.json"
    summary: dict[str, Any] = {
        "path": str(active_sessions),
        "exists": active_sessions.exists(),
        "count": None,
        "mtime": None,
        "status": "missing",
    }
    if not active_sessions.exists():
        return summary

    try:
        stat = active_sessions.stat()
        summary["mtime"] = stat.st_mtime
        summary["size"] = stat.st_size
        data = json.loads(active_sessions.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            entries = data.get("entries", [])
        elif isinstance(data, list):
            entries = data
        else:
            entries = []
        summary["count"] = len(entries) if isinstance(entries, list) else None
        summary["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 - metadata probe must not fail the gate
        summary["status"] = f"unreadable: {type(exc).__name__}"
    return summary


def check_profile(root: Path, role: str, profile: str) -> dict[str, Any]:
    profile_home = root if profile == "default" else root / "profiles" / profile
    skill_md = profile_home / "skills" / "decretum-matrix" / "SKILL.md"
    result = {
        "role": role,
        "profile": profile,
        "profile_home": str(profile_home),
        "exists": profile_home.exists(),
        "skill_md": skill_md.exists(),
        "config_yaml": (profile_home / "config.yaml").exists(),
        "soul_md": (profile_home / "SOUL.md").exists(),
        "state_db": (profile_home / "state.db").exists(),
        "active_sessions": summarize_active_sessions(profile_home),
    }
    result["ok"] = all(
        result[key]
        for key in ("exists", "skill_md", "config_yaml", "soul_md", "state_db")
    )
    return result


def check_desktop_sources(root: Path) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    ok = True
    for name, (relative, required_terms) in DESKTOP_SOURCE_CHECKS.items():
        path = root / relative
        item: dict[str, Any] = {
            "path": str(path),
            "exists": path.exists(),
            "required_terms": required_terms,
            "terms_present": [],
            "missing_terms": [],
        }
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            for term in required_terms:
                if term in text:
                    item["terms_present"].append(term)
                else:
                    item["missing_terms"].append(term)
        else:
            item["missing_terms"] = list(required_terms)
        item["ok"] = item["exists"] and not item["missing_terms"]
        ok = ok and item["ok"]
        checks[name] = item
    return {"ok": ok, "checks": checks}


def check_zellij() -> dict[str, Any]:
    zellij = shutil.which("zellij")
    result: dict[str, Any] = {
        "available": bool(zellij),
        "path": zellij,
        "env": {
            "ZELLIJ": os.environ.get("ZELLIJ"),
            "ZELLIJ_SESSION_NAME": os.environ.get("ZELLIJ_SESSION_NAME"),
            "ZELLIJ_PANE_ID": os.environ.get("ZELLIJ_PANE_ID"),
        },
    }
    inside = bool(result["env"].get("ZELLIJ_SESSION_NAME") or result["env"].get("ZELLIJ_PANE_ID"))
    if zellij:
        result["version"] = run_command([zellij, "--version"], timeout=10)
        result["panes"] = run_command([zellij, "action", "list-panes"], timeout=10)
        pane_text = "\n".join(
            str(result["panes"].get(key) or "")
            for key in ("stdout", "stderr")
        ).strip()
        lowered = pane_text.lower()
        rejected_prompts = (
            "please specify",
            "no active zellij session",
            "not in a zellij session",
        )
        panes_prove_session = bool(
            result["panes"].get("ok")
            and pane_text
            and not any(marker in lowered for marker in rejected_prompts)
        )
        result["panes_prove_session"] = panes_prove_session
        inside = inside or panes_prove_session
    result["inside"] = inside
    result["ok"] = bool(zellij) and inside
    return result


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    surface = args.surface
    root = args.hermes_root.resolve()
    profiles = parse_profiles(args.profiles)
    profile_results = {
        role: check_profile(root, role, profile) for role, profile in profiles.items()
    }

    hermes_command = args.hermes_command
    hermes_path = shutil.which(hermes_command) or hermes_command
    cli_gate = {
        "hermes_command": hermes_command,
        "resolved": hermes_path,
        "available": bool(shutil.which(hermes_command) or Path(hermes_command).exists()),
        "profile_list": None,
    }
    if cli_gate["available"] and surface in {"cli", "auto"}:
        cli_gate["profile_list"] = run_command([hermes_path, "profile", "list"], timeout=90)
    cli_gate["ok"] = bool(cli_gate["available"]) and bool(
        surface == "desktop"
        or (cli_gate["profile_list"] and cli_gate["profile_list"].get("ok"))
    )

    desktop_source_gate = check_desktop_sources(root)

    squad_path = shutil.which("squad")
    squad_fallback_gate: dict[str, Any] = {
        "required": not args.no_require_squad_fallback,
        "available": bool(squad_path),
        "path": squad_path,
    }
    if squad_path:
        squad_fallback_gate["help"] = run_command([squad_path, "help"], timeout=10)
        squad_fallback_gate["doctor"] = run_command([squad_path, "doctor"], timeout=15)
    squad_fallback_gate["ok"] = bool(squad_path) and bool(
        squad_fallback_gate.get("help", {}).get("ok")
    )

    if args.check_zellij_for_cli:
        zellij_gate = check_zellij()
        zellij_gate["status"] = (
            f"REQUIRED_FOR_SUPERCC_{surface.upper()}_PASSED"
            if zellij_gate.get("ok")
            else f"REQUIRED_FOR_SUPERCC_{surface.upper()}_FAILED"
        )
        zellij_gate["reason"] = (
            "Normal superCC requires current zellij plus squad environment "
            "even when Hermes profile or desktop readiness is also checked."
        )
    else:
        zellij_gate = {
            "ok": False,
            "status": f"NOT_CHECKED_FOR_SUPERCC_{surface.upper()}",
            "reason": "zellij+squad proof is required before claiming normal superCC.",
        }

    root_skill = root / "skills" / "decretum-matrix" / "SKILL.md"
    profiles_ok = all(item["ok"] for item in profile_results.values())
    taizi_profile = profile_results.get("taizi", {})

    desktop_ok = desktop_source_gate["ok"] if surface in {"desktop", "auto"} else True
    cli_ok = cli_gate["ok"] if surface in {"cli", "auto"} else True
    squad_ok = squad_fallback_gate["ok"] or args.no_require_squad_fallback
    zellij_ok = bool(zellij_gate.get("ok"))

    ok = all(
        [
            root.exists(),
            root_skill.exists(),
            profiles_ok,
            bool(taizi_profile.get("ok")),
            desktop_ok,
            cli_ok,
            squad_ok,
            zellij_ok,
        ]
    )
    profile_readiness_evidence = "PASSED" if profiles_ok and desktop_ok else "runtime_degraded"
    profile_session_activity = {
        role: {
            "profile": item.get("profile"),
            "active_sessions": item.get("active_sessions"),
        }
        for role, item in profile_results.items()
    }

    return {
        "ok": ok,
        "runtime_selection_gate": "PASSED" if ok else "runtime_degraded",
        "supercc_runtime_family": "visible_zellij_squad",
        "supercc_env_gate": "PASSED" if ok else "runtime_degraded",
        "visible_display_gate": "PASSED" if zellij_ok else "runtime_degraded",
        "display_transport_gate": "PASSED" if zellij_ok and squad_ok else "runtime_degraded",
        "hermes_supercc_gate": "PASSED" if ok else "runtime_degraded",
        "runtime_client": "hermes_desktop_readiness" if surface == "desktop" else "hermescli",
        "hermes_surface": surface,
        "source_agent_label": "Hermes",
        "workspace": str(args.workspace.resolve()),
        "hermes_root": str(root),
        "root_exists": root.exists(),
        "root_skill_md": str(root_skill),
        "root_skill_exists": root_skill.exists(),
        "hermes_forced_profile": "taizi" if taizi_profile.get("ok") else "FAILED",
        "taizi_activation_policy": "force taizi for superCC entry; do not rewrite sticky default",
        "profile_silent_call_policy": "silent profile-native calls; preserve corresponding profile/session evidence",
        "supercc_normal_env_requirement": "zellij+squad",
        "dispatch_delivery_channel": "NOT_RUN_READINESS_PROBE_ONLY",
        "profile_native_evidence_scope": "readiness_only_not_dispatch_not_normal_without_zellij_squad",
        "hermes_profile_readiness_evidence": profile_readiness_evidence,
        "hermes_profile_dispatch_evidence": "NOT_RUN_READINESS_PROBE_ONLY",
        "profile_session_activity": profile_session_activity,
        "hermes_desktop_zellij_gate": zellij_gate.get("status"),
        "profiles_ok": profiles_ok,
        "profiles": profile_results,
        "cli_gate": cli_gate,
        "desktop_source_gate": desktop_source_gate,
        "zellij_gate": zellij_gate,
        "squad_fallback_gate": squad_fallback_gate,
        "hermes_profile_native_evidence": "PROFILE_READINESS_PASSED" if profiles_ok and desktop_ok else "runtime_degraded",
        "notes": [
            "read-only probe; no Hermes config/profile/session mutation",
            "this readiness probe does not prove zhongshu/menxia/shangshu/patrol dispatch",
            "no auth.json, .env, token, cookie, or raw conversation body is read",
            "normal superCC requires zellij+squad; Hermes profile readiness is supplemental evidence",
            "squad is required for the normal environment and does not replace Hermes native profile evidence",
        ],
    }


def print_text(report: dict[str, Any]) -> None:
    status = "PASSED" if report["ok"] else "runtime_degraded"
    print(f"HERMES_SUPERCC_GATE {status}")
    print(f"runtime_client={report['runtime_client']}")
    print(f"surface={report['hermes_surface']}")
    print(f"hermes_root={report['hermes_root']}")
    print(f"hermes_forced_profile={report['hermes_forced_profile']}")
    print(f"hermes_desktop_zellij_gate={report['hermes_desktop_zellij_gate']}")
    print(f"hermes_profile_readiness_evidence={report['hermes_profile_readiness_evidence']}")
    print(f"hermes_profile_dispatch_evidence={report['hermes_profile_dispatch_evidence']}")
    print(f"profiles_ok={report['profiles_ok']}")
    print(f"cli_gate_ok={report['cli_gate']['ok']}")
    print(f"desktop_source_gate_ok={report['desktop_source_gate']['ok']}")
    print(f"squad_fallback_gate_ok={report['squad_fallback_gate']['ok']}")
    for role, item in report["profiles"].items():
        print(
            "PROFILE "
            f"{role}={item['profile']} ok={item['ok']} "
            f"skill={item['skill_md']} config={item['config_yaml']} "
            f"soul={item['soul_md']} state={item['state_db']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Compatibility flag; the script is always read-only.")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--surface", choices=["auto", "cli", "desktop"], default="auto")
    parser.add_argument("--hermes-root", type=Path, default=default_hermes_root())
    parser.add_argument("--hermes-command", default=os.environ.get("COURT_HERMES_COMMAND", "hermes"))
    parser.add_argument("--profiles", help="Comma list of role or role=profile entries.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--no-require-squad-fallback", action="store_true")
    parser.add_argument("--check-zellij-for-cli", dest="check_zellij_for_cli", action="store_true", default=True)
    parser.add_argument("--no-check-zellij-for-cli", dest="check_zellij_for_cli", action="store_false")
    args = parser.parse_args()

    report = build_report(args)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    # Fix for Windows UTF-8 encoding issues (2026-07-05)
    # On Windows, stdout may default to CP936/GBK encoding, causing UnicodeEncodeError
    # when printing JSON with Chinese characters (e.g., 官署代称, 太子, etc.)
    # This reconfigures stdout to UTF-8 before main() executes to ensure proper output
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
