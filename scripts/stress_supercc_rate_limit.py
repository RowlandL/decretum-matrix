"""Bounded superCC multi-agent pressure test.

This script opens/dispatches multiple superCC office agents while enforcing a
single request budget. It is intentionally conservative: every launch that can
start an office client and every native ENTER_DISPATCH is counted as one
model-triggering request even when the downstream office is reused or blocked.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ENSURE = ROOT / "scripts" / "ensure_supercc_court.py"
MINISTRY_ROLES = ("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu")
RATE_SIGNAL_RE = re.compile(r"(?i)(429|rate[ _.-]?limit|too many requests)")
ERROR_KEYS = {
    "error",
    "errors",
    "exception",
    "stderr",
    "stderr_tail",
    "returncode",
    "status",
    "reason",
    "rate_limit",
    "rate_limit_signals",
}


def rate_signals_from_text(text: str) -> list[str]:
    return sorted(set(match.group(1) for match in RATE_SIGNAL_RE.finditer(text)))[:20]


def error_signal_payload(value: Any) -> Any:
    if isinstance(value, dict):
        filtered: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in ERROR_KEYS:
                filtered[key] = item
            else:
                nested = error_signal_payload(item)
                if nested not in ({}, [], None, ""):
                    filtered[key] = nested
        return filtered
    if isinstance(value, list):
        filtered_list = [error_signal_payload(item) for item in value]
        return [item for item in filtered_list if item not in ({}, [], None, "")]
    return None


def rate_signals(value: Any) -> list[str]:
    text = json.dumps(error_signal_payload(value), ensure_ascii=False, default=str)
    return rate_signals_from_text(text)


def run_ensure(workspace: Path, ensure_args: list[str], *, timeout: int = 240) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ENSURE),
        "--workspace",
        str(workspace),
        "--no-auto-install-deps",
        "--format",
        "json",
        *ensure_args,
    ]
    started = dt.datetime.now(dt.timezone.utc)
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    try:
        payload: Any = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = None
    failed = result.returncode != 0 or (isinstance(payload, dict) and not bool(payload.get("ok", payload.get("passed", True))))
    signal_source = {
        "stderr": result.stderr,
        "payload": payload,
        "stdout": result.stdout if failed else "",
    }
    return {
        "ok": not failed,
        "returncode": result.returncode,
        "started_at": started.isoformat(),
        "ended_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "command": command,
        "payload": payload,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "rate_limit_signals": rate_signals(signal_source),
    }


def ensure_budget(count: int, total_limit: int, label: str) -> None:
    if count > total_limit:
        raise RuntimeError(f"{label} would exceed total request limit: planned={count} total_limit={total_limit}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=str(Path.home()))
    parser.add_argument("--requests-per-minute", type=int, default=20)
    parser.add_argument("--total-limit", type=int, default=20)
    parser.add_argument("--launch-offices", default="all", help="Office selection passed to ensure_supercc_court.py --launch-offices.")
    parser.add_argument("--dispatch-ministries", action="store_true", default=True, help="Dispatch one bounded task to each ministry after launch.")
    parser.add_argument("--no-dispatch-ministries", action="store_false", dest="dispatch_ministries")
    parser.add_argument("--include-inspector", action="store_true", help="Include 监察使. Default skips it for this bounded diagnostic.")
    parser.add_argument("--office-client", choices=("codex", "hermescli"), default="codex")
    parser.add_argument("--reclaim-existing", action="store_true")
    parser.add_argument("--post-launch-buffer", type=float, default=5.0)
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    rpm = max(1, args.requests_per_minute)
    interval = 60.0 / rpm
    total_limit = max(1, args.total_limit)
    counted_requests = 0
    steps: list[dict[str, Any]] = []
    skip_inspector_arg = [] if args.include_inspector else ["--skip-inspector"]

    try:
        check = run_ensure(workspace, ["--check-only", "--office-client", args.office_client], timeout=60)
        steps.append({"step": "check_only", "counted_model_requests": 0, "result": check})
        if not check["ok"]:
            raise RuntimeError("superCC check-only gate failed")

        dry_launch_args = [
            "--launch-offices",
            args.launch_offices,
            "--office-client",
            args.office_client,
            "--request-rate-limit-per-minute",
            str(rpm),
            "--request-total-limit",
            str(total_limit),
            "--codex-start-stagger",
            f"{interval:g}",
            "--codex-start-jitter",
            "0",
            "--codex-retry-attempts",
            "1",
            "--launch-delay",
            "0.5",
            "--dry-run",
            *skip_inspector_arg,
        ]
        dry_launch = run_ensure(workspace, dry_launch_args, timeout=90)
        steps.append({"step": "launch_dry_run", "counted_model_requests": 0, "result": dry_launch})
        if not dry_launch["ok"]:
            raise RuntimeError("launch dry-run failed")
        dry_payload = dry_launch.get("payload") if isinstance(dry_launch.get("payload"), dict) else {}
        launch_roles = list(dry_payload.get("visible_offices_to_launch") or [])
        ensure_budget(counted_requests + len(launch_roles), total_limit, "launch")

        live_launch_args = [
            "--launch-offices",
            args.launch_offices,
            "--office-client",
            args.office_client,
            "--request-rate-limit-per-minute",
            str(rpm),
            "--request-total-limit",
            str(total_limit - counted_requests),
            "--codex-start-stagger",
            f"{interval:g}",
            "--codex-start-jitter",
            "0",
            "--codex-retry-attempts",
            "1",
            "--launch-delay",
            "0.5",
            *skip_inspector_arg,
        ]
        if args.reclaim_existing:
            live_launch_args.append("--reclaim-existing")
        live_launch = run_ensure(workspace, live_launch_args, timeout=360)
        counted_requests += len(launch_roles)
        steps.append({"step": "launch_live", "counted_model_requests": len(launch_roles), "roles": launch_roles, "result": live_launch})
        if not live_launch["ok"]:
            raise RuntimeError("live launch failed")

        if launch_roles:
            time.sleep(interval * len(launch_roles) + max(0.0, args.post_launch_buffer))

        if args.dispatch_ministries:
            for index, role in enumerate(MINISTRY_ROLES, start=1):
                ensure_budget(counted_requests + 1, total_limit, f"dispatch {role}")
                dispatch_uid = f"STRESS-RATE-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')}-{role}"
                message = (
                    "STRESS_RATE_LIMIT bounded dispatch; role must answer only as its own 六部 agente. "
                    "Do not ask the user, do not spawn descendants, do not edit files. "
                    "Return one compact heartbeat/report to 尚书省; this is a bounded rate-budget probe."
                )
                dispatch = run_ensure(
                    workspace,
                    [
                        "--enter-dispatch",
                        "--role",
                        role,
                        "--calling-office",
                        "shangshu",
                        "--dispatch-uid",
                        dispatch_uid,
                        "--message",
                        message,
                        "--office-client",
                        args.office_client,
                        *skip_inspector_arg,
                    ],
                    timeout=120,
                )
                counted_requests += 1
                steps.append({"step": "dispatch_ministry", "role": role, "counted_model_requests": 1, "dispatch_uid": dispatch_uid, "result": dispatch})
                if index < len(MINISTRY_ROLES):
                    time.sleep(interval)

        signals = sorted(set(signal for step in steps for signal in rate_signals(step)))
        summary = {
            "ok": not signals and counted_requests <= total_limit,
            "schema": "court.supercc.rate_limit_stress.v1",
            "workspace": str(workspace),
            "requests_per_minute_limit": rpm,
            "request_interval_seconds": interval,
            "total_request_limit": total_limit,
            "counted_model_requests": counted_requests,
            "include_inspector": bool(args.include_inspector),
            "office_client": args.office_client,
            "rate_limit_signals": signals,
            "observed_429": any(signal == "429" for signal in signals),
            "steps": steps,
        }
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        summary = {
            "ok": False,
            "schema": "court.supercc.rate_limit_stress.v1",
            "workspace": str(workspace),
            "requests_per_minute_limit": rpm,
            "request_interval_seconds": interval,
            "total_request_limit": total_limit,
            "counted_model_requests": counted_requests,
            "include_inspector": bool(args.include_inspector),
            "office_client": args.office_client,
            "rate_limit_signals": sorted(set(signal for step in steps for signal in rate_signals(step))),
            "observed_429": False,
            "error": str(exc),
            "steps": steps,
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
