"""Silent superCC supervisor script for 429, abnormal close, and abnormal silence.

The supervisor is intentionally independent of any dedicated 监察 visible pane.
It can run silently on a blank host with only this skill package, Python,
zellij/squad on PATH, and the selected CLI executable. State files are optional
evidence, not startup prerequisites.
"""



from __future__ import annotations

# A+B layering: real module lives in scripts/services/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
import time
from typing import Any

import ensure_supercc_court as court


WATCHDOG_SCHEMA = "court.supercc.watchdog.v1"
WATCHDOG_PROCESS_SCHEMA = "court.supercc.watchdog_process.v1"
VISIBLE_DEFAULT_ROLES = ("taizi", *court.SUPERCC_VISIBLE_CORE_OFFICES)
DEFAULT_STALE_SECONDS = 900.0
ABNORMAL_MODES = {
    "429",
    "rate_limited",
    "runtime_degraded",
    "closed",
    "exited",
    "crashed",
    "abnormal",
    "abnormal_silence",
    "missing",
}


def parse_time(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.timestamp()


def age_seconds(value: Any, now: float) -> float | None:
    parsed = parse_time(value)
    if parsed is None:
        return None
    return max(0.0, now - parsed)


def role_expected_visible(role: str) -> bool:
    return role in VISIBLE_DEFAULT_ROLES


def load_optional_state(workspace: Path, zellij_session: str | None) -> dict[str, Any]:
    return court.read_office_state(workspace, zellij_session)


def default_log_path() -> Path:
    return court.shiguan_runtime_path("supercc-watchdog.jsonl")


def default_pid_path() -> Path:
    return court.shiguan_runtime_path("supercc-watchdog.pid.json")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def hidden_daemon_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--workspace",
        str(Path(args.workspace).resolve()),
        "--roles",
        str(args.roles),
        "--watch",
        "--quiet",
        "--log-jsonl",
        str(Path(args.log_jsonl or default_log_path()).resolve()),
        "--interval",
        str(max(1.0, float(args.interval))),
    ]
    if args.zellij_session:
        command.extend(["--zellij-session", str(args.zellij_session)])
    if args.apply:
        command.append("--apply")
    if args.no_apply:
        command.append("--no-apply")
    if args.dry_run:
        command.append("--dry-run")
    if args.force:
        command.append("--force")
    if args.max_actions is not None:
        command.extend(["--max-actions", str(max(0, int(args.max_actions)))])
    if args.max_iterations:
        command.extend(["--max-iterations", str(max(0, int(args.max_iterations)))])
    return command


def parse_pid(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if text.startswith("PID="):
        text = text.split("=", 1)[1].strip()
    try:
        pid = int(text)
    except ValueError:
        return None
    return pid if pid > 0 else None


def write_pid_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def read_pid_record(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "reason": "missing_pid_file", "pid_path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "reason": str(exc), "pid_path": str(path)}
    payload["ok"] = True
    payload["pid_path"] = str(path)
    return payload


def start_hidden_daemon(args: argparse.Namespace) -> dict[str, Any]:
    command = hidden_daemon_command(args)
    log_path = Path(args.log_jsonl or default_log_path()).resolve()
    pid_path = Path(args.pid_file or default_pid_path()).resolve()
    record = {
        "schema": WATCHDOG_PROCESS_SCHEMA,
        "mode": "daemon_start",
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "command": command,
        "log_jsonl": str(log_path),
        "pid_file": str(pid_path),
        "platform": os.name,
        "hidden_window": True,
        "watchdog_no_visible_window": True,
        "watchdog_daemon_start": "PENDING",
    }
    try:
        if os.name == "nt":
            powershell = [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    "$ErrorActionPreference='Stop'; "
                    "$p=Start-Process -FilePath " + court.powershell_arg(command[0])
                    + " -ArgumentList @("
                    + ",".join(court.powershell_arg(part) for part in command[1:])
                    + ") -WindowStyle Hidden -PassThru; "
                    + "'PID=' + $p.Id"
                ),
            ]
            result = court.run_command(powershell, cwd=Path(args.workspace).resolve(), timeout=20, stdout_limit=2000, stderr_limit=4000)
            record["ok"] = bool(result.get("ok"))
            record["launcher"] = "powershell_start_process_hidden"
            record["pid"] = parse_pid(result.get("stdout"))
            record["result"] = {k: result.get(k) for k in ("ok", "returncode", "stderr", "error")}
        else:
            stdout = open(os.devnull, "wb")
            stderr = open(os.devnull, "wb")
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(Path(args.workspace).resolve()),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=True,
                    close_fds=True,
                )
            finally:
                stdout.close()
                stderr.close()
            record["ok"] = True
            record["launcher"] = "subprocess_start_new_session"
            record["pid"] = process.pid
    except Exception as exc:
        record["ok"] = False
        record["error"] = str(exc)
    if record.get("ok"):
        record["watchdog_daemon_start"] = "PASSED"
        write_pid_record(pid_path, record)
    else:
        record["watchdog_daemon_start"] = "FAILED"
    append_jsonl(log_path, record)
    return record


def stop_daemon(args: argparse.Namespace) -> dict[str, Any]:
    pid_path = Path(args.pid_file or default_pid_path()).resolve()
    log_path = Path(args.log_jsonl or default_log_path()).resolve()
    record = read_pid_record(pid_path)
    payload: dict[str, Any] = {
        "schema": WATCHDOG_PROCESS_SCHEMA,
        "mode": "daemon_stop",
        "stopped_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "pid_file": str(pid_path),
        "log_jsonl": str(log_path),
        "hidden_window": True,
        "watchdog_no_visible_window": True,
        "watchdog_daemon_stop": "PENDING",
        "read_pid_record": record,
    }
    pid = parse_pid(record.get("pid"))
    if not pid:
        payload["ok"] = False
        payload["reason"] = record.get("reason", "missing_pid")
        payload["watchdog_daemon_stop"] = "FAILED"
        append_jsonl(log_path, payload)
        return payload
    try:
        if os.name == "nt":
            command = [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"Stop-Process -Id {pid} -ErrorAction SilentlyContinue; 'STOPPED={pid}'",
            ]
            result = court.run_command(command, cwd=Path(args.workspace).resolve(), timeout=20, stdout_limit=2000, stderr_limit=4000)
            payload["ok"] = bool(result.get("ok"))
            payload["result"] = {k: result.get(k) for k in ("ok", "returncode", "stdout", "stderr", "error")}
        else:
            try:
                os.kill(pid, 15)
                payload["ok"] = True
                payload["result"] = {"signal": 15}
            except ProcessLookupError:
                payload["ok"] = True
                payload["result"] = {"already_stopped": True}
        if payload.get("ok") and pid_path.exists():
            pid_path.unlink()
    except Exception as exc:
        payload["ok"] = False
        payload["error"] = str(exc)
    payload["watchdog_daemon_stop"] = "PASSED" if payload.get("ok") else "FAILED"
    append_jsonl(log_path, payload)
    return payload


def detect_rate_limit_signals(*payloads: Any) -> list[str]:
    signals: list[str] = []
    for payload in payloads:
        for signal in court.rate_limit_signals(payload):
            if signal not in signals:
                signals.append(signal)
    return signals


def classify_role(
    role: str,
    *,
    check: dict[str, Any],
    state: dict[str, Any],
    stale_seconds: float,
    now: float,
) -> dict[str, Any]:
    agents = court.active_agents_by_id(check.get("squad", {}).get("agents_json", []))
    visible = court.visible_office_panes(check)
    row = agents.get(role)
    panes = visible.get(role, [])
    role_state = (state.get("roles") or {}).get(role, {}) if state.get("ok") else {}
    mode = str(role_state.get("mode") or "").strip().lower()
    updated_age = age_seconds(role_state.get("updated_at"), now)
    last_seen_age = court.last_seen_age_seconds(row)
    rate_signals = detect_rate_limit_signals(role_state, row)

    reasons: list[str] = []
    expected_visible = role_expected_visible(role)
    if expected_visible and not panes:
        reasons.append("missing_visible_pane")
    if expected_visible and len(panes) > 1:
        reasons.append("duplicate_visible_panes")
    if role in ("taizi", *court.NO_SILENCE_ROLES) and not row:
        reasons.append("missing_active_squad_identity")
    if row and last_seen_age is not None and last_seen_age > stale_seconds:
        reasons.append("stale_active_squad_identity")
    if row and last_seen_age is None:
        reasons.append("unknown_active_squad_heartbeat")
    if mode in ABNORMAL_MODES or any(token in mode for token in ("429", "rate", "degraded", "crash", "closed", "exit")):
        reasons.append("abnormal_state_mode")
    if role in court.NO_SILENCE_ROLES and mode in court.EXPECTED_IDLE_MODES:
        reasons.append("abnormal_silence_no_silence_role")
    if updated_age is not None and updated_age > stale_seconds and mode not in court.EXPECTED_IDLE_MODES:
        reasons.append("stale_office_state")
    if rate_signals:
        reasons.append("rate_limit_signal")

    severity = "ok"
    if reasons:
        severity = "recover"
    if "duplicate_visible_panes" in reasons:
        severity = "manual_review"

    if role == "taizi":
        owner = "zhongshu"
        action = "report_taizi_abnormal_and_trigger_turn_start"
    elif role in court.THREE_OFFICES:
        owner = "taizi"
        action = "turn_start_wake_visible_core"
    elif role in court.MINISTRY_OFFICES:
        owner = "shangshu"
        action = "wake_or_redispatch_ministry"
    else:
        owner = "taizi"
        action = "wake_special_office"

    return {
        "role": role,
        "expected_visible": expected_visible,
        "visible_pane_count": len(panes),
        "pane_ids": [pane.get("pane_id") for pane in panes],
        "active_squad_identity": row is not None,
        "last_seen_age_seconds": None if last_seen_age is None else round(last_seen_age, 3),
        "state_mode": mode or None,
        "state_updated_age_seconds": None if updated_age is None else round(updated_age, 3),
        "rate_limit_signals": rate_signals,
        "reasons": reasons,
        "severity": severity,
        "owner": owner,
        "recommended_action": action,
    }


def build_recovery_command(args: argparse.Namespace, row: dict[str, Any]) -> list[str]:
    role = str(row["role"])
    base = [
        sys.executable,
    str(Path(__file__).resolve().parents[1] / "commands" / "ensure_supercc_court.py"),
        "--workspace",
        str(Path(args.workspace).resolve()),
    ]
    if args.zellij_session:
        base.extend(["--zellij-session", args.zellij_session])
    if args.force:
        base.append("--force")
    if args.dry_run:
        base.append("--dry-run")
    if role in ("taizi", *court.THREE_OFFICES):
        base.extend(["--turn-start", "visible-core"])
        return base
    base.extend(["--wake-offices", role, "--wake-reason", f"watchdog_auto_recover:{','.join(row.get('reasons') or [])}"])
    return base


def apply_recovery(args: argparse.Namespace, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    recoverable = [row for row in rows if row.get("severity") == "recover"]
    for row in recoverable[: max(0, int(args.max_actions))]:
        command = build_recovery_command(args, row)
        if args.no_apply:
            actions.append({"role": row["role"], "skipped": True, "reason": "no_apply", "command": command})
            continue
        result = court.run_command(command, cwd=Path(args.workspace).resolve(), timeout=60, stdout_limit=30000, stderr_limit=12000)
        actions.append(
            {
                "role": row["role"],
                "command": command,
                "result": {k: result.get(k) for k in ("ok", "returncode", "stderr", "error")},
            }
        )
    return actions


def watchdog_once(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    check_args = argparse.Namespace(
        workspace=str(workspace),
        office_client="cli",
        requested_office_client="cli",
        office_client_command=sys.executable,
        office_client_arg=[],
        office_client_args=None,
        office_client_prompt_mode="argument",
        office_client_selection_source="watchdog_internal_python_probe",
        office_client_selection_signals=[],
        hermescli_command="hermes",
        claude_command="claude",
        zellij_session=args.zellij_session,
    )
    check = court.supercc_check_for_args(check_args, workspace)
    state_session = court.current_zellij_session(check) or args.zellij_session
    state = load_optional_state(workspace, state_session)
    roles = court.expand_status_selection(args.roles)
    now = time.time()
    rows = [
        classify_role(role, check=check, state=state, stale_seconds=args.stale_seconds, now=now)
        for role in roles
        if role != "patrol-inspector"
    ]
    abnormal = [row for row in rows if row["severity"] != "ok"]
    actions = apply_recovery(args, rows) if args.apply else []
    return {
        "schema": WATCHDOG_SCHEMA,
        "ok": not any(row["severity"] == "manual_review" for row in rows),
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "workspace": str(workspace),
        "zellij_session": state_session,
        "supercc_watchdog": "read_only" if not args.apply else "applied",
        "watchdog_process": "NOT_APPLICABLE",
        "roles": rows,
        "abnormal_roles": abnormal,
        "watchdog_abnormal_roles": abnormal,
        "actions": actions,
        "watchdog_actions": actions if actions else "none",
        "apply": bool(args.apply),
        "no_apply": bool(args.no_apply),
        "legacy_patrol_visible_pane": "disabled",
        "silent_supervisor": True,
        "no_visible_window": True,
        "watchdog_no_visible_window": True,
        "log_jsonl": str(Path(args.log_jsonl).resolve()) if getattr(args, "log_jsonl", None) else None,
        "watchdog_log_jsonl": str(Path(args.log_jsonl).resolve()) if getattr(args, "log_jsonl", None) else None,
        "watchdog_pid_file": str(Path(args.pid_file).resolve()) if getattr(args, "pid_file", None) else None,
        "watchdog_daemon_start": "NOT_APPLICABLE",
        "watchdog_daemon_stop": "NOT_APPLICABLE",
        "blank_environment_policy": "requires only packaged skill scripts, Python, PATH-resolved zellij/squad, and optional CLI command/env; Shiguan state is optional evidence",
        "supercc_env_gate": check.get("supercc_env_gate"),
        "visible_display_gate": check.get("visible_display_gate"),
        "display_transport_gate": check.get("display_transport_gate"),
        "state_available": bool(state.get("ok")),
        "state_path": state.get("path"),
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        f"schema: {payload.get('schema')}",
        f"ok: {payload.get('ok')}",
        f"supercc_env_gate: {payload.get('supercc_env_gate')}",
        f"visible_display_gate: {payload.get('visible_display_gate')}",
        "roles:",
    ]
    for row in payload.get("roles", []):
        reasons = ",".join(row.get("reasons") or ["ok"])
        lines.append(f"- {row.get('role')}: {row.get('severity')} [{reasons}] owner={row.get('owner')}")
    if payload.get("actions"):
        lines.append("actions:")
        for action in payload["actions"]:
            lines.append(f"- {action.get('role')}: ok={(action.get('result') or {}).get('ok')} skipped={action.get('skipped', False)}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=str(court.user_home()))
    parser.add_argument("--roles", default="visible-core")
    parser.add_argument("--zellij-session", default=os.environ.get("COURT_ZELLIJ_SESSION"))
    parser.add_argument("--stale-seconds", type=float, default=DEFAULT_STALE_SECONDS)
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument("--apply", action="store_true", help="Apply bounded recovery actions. Default is read-only.")
    recovery.add_argument("--no-apply", action="store_true", help="Explicitly keep recovery in read-only planning mode.")
    parser.add_argument("--dry-run", action="store_true", help="Pass --dry-run to delegated recovery commands.")
    parser.add_argument("--force", action="store_true", help="Pass --force to delegated recovery commands.")
    parser.add_argument("--max-actions", type=int, default=1)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--daemon", action="store_true", help="Start a silent background supervisor without opening a visible window.")
    parser.add_argument("--stop-daemon", action="store_true", help="Stop a previously started silent background supervisor using its pid file.")
    parser.add_argument("--quiet", action="store_true", help="Suppress stdout; use with --log-jsonl for background operation.")
    parser.add_argument("--log-jsonl", default=None, help="Append supervisor records to this JSONL file. Disabled for one-shot read-only checks unless explicitly set.")
    parser.add_argument("--pid-file", default=None, help="PID record for --daemon and --stop-daemon; those modes use the managed default when omitted.")
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--max-iterations", type=int, default=0, help="0 means unbounded when --watch is set.")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.stop_daemon:
        payload = stop_daemon(args)
        if not args.quiet:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") else 2
    if args.daemon:
        payload = start_hidden_daemon(args)
        if not args.quiet:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") else 2
    if args.no_apply:
        args.apply = False
    iterations = 0
    last_payload: dict[str, Any] = {}
    while True:
        last_payload = watchdog_once(args)
        if args.log_jsonl:
            append_jsonl(Path(args.log_jsonl), last_payload)
        if not args.quiet:
            if args.format == "json":
                print(json.dumps(last_payload, ensure_ascii=False, indent=2))
            else:
                print(render_text(last_payload))
        iterations += 1
        if not args.watch:
            break
        if args.max_iterations and iterations >= args.max_iterations:
            break
        time.sleep(max(1.0, float(args.interval)))
    return 0 if last_payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
