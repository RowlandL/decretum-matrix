#!/usr/bin/env python
"""Watchdog daemon for Shiguan WebUI and preserve-only autosync."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import time

from shiguan_paths import ensure_shared_seed, reference_path, references_root


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def status_path() -> Path:
    return reference_path("court-runtime", "shiguan-service-daemon.json")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def web_args() -> argparse.Namespace:
    return argparse.Namespace(
        host="0.0.0.0",
        port=8765,
        max_port=8765,
        timeout=8.0,
        attempts=20,
        sleep=0.25,
        check_only=False,
    )


def run_once(interval: int) -> dict[str, object]:
    os.environ["COURT_DISABLE_AGENT_PRESENCE"] = "1"
    ensure_shared_seed()
    from ensure_shiguan_autosync import ensure as ensure_autosync
    from ensure_shiguan_web import ensure as ensure_web

    web = ensure_web(web_args())
    autosync = ensure_autosync(interval, check_only=False)
    ok = str(web.get("status")) in {"RUNNING", "REUSED", "STARTED", "CHECK_ONLY"} and str(autosync.get("status")) in {"REUSED", "STARTED"}
    report = {
        "ok": ok,
        "mode": "daemon",
        "pid": os.getpid(),
        "updated_at": now_text(),
        "interval_seconds": interval,
        "shared_shiguan_root": str(references_root()),
        "web": web,
        "autosync": autosync,
        "status_path": str(status_path()),
    }
    write_json(status_path(), report)
    return report


def daemon_loop(interval: int) -> int:
    os.environ["COURT_DISABLE_AGENT_PRESENCE"] = "1"
    ensure_shared_seed()
    while True:
        try:
            run_once(interval)
        except Exception as exc:
            write_json(
                status_path(),
                {
                    "ok": False,
                    "mode": "daemon",
                    "pid": os.getpid(),
                    "updated_at": now_text(),
                    "interval_seconds": interval,
                    "shared_shiguan_root": str(references_root()),
                    "error": str(exc),
                },
            )
        time.sleep(max(10, interval))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Run one watchdog cycle and exit.")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()
    interval = max(10, args.interval)
    if args.once:
        print(json.dumps(run_once(interval), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    return daemon_loop(interval)


if __name__ == "__main__":
    sys.exit(main())
