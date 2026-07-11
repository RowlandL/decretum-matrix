"""Smoke-test court_runtime lockfile with concurrent CLI writers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> int:
    script = Path(__file__).resolve().parent / "court_cli.py"
    with tempfile.TemporaryDirectory() as temp_dir:
        env = dict(os.environ)
        env["COURT_RUNTIME_ROOT"] = temp_dir
        create = subprocess.run(
            [
                sys.executable,
                str(script),
                "create",
                "--task-id",
                "concurrency",
                "--title",
                "concurrency smoke",
                "--evidence",
                "create",
            ],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        if create.returncode:
            print(create.stderr or create.stdout, file=sys.stderr)
            return create.returncode
        workers = []
        for index in range(8):
            workers.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        str(script),
                        "heartbeat",
                        "--task-id",
                        "concurrency",
                        "--heartbeat",
                        f"alive-{index}",
                        "--actor",
                        "gongbu",
                        "--evidence",
                        f"worker {index}",
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                )
            )
        failed: list[str] = []
        for worker in workers:
            stdout, stderr = worker.communicate(timeout=20)
            if worker.returncode:
                failed.append(stderr or stdout)
        if failed:
            print("\n".join(failed), file=sys.stderr)
            return 1
        tasks = json.loads((Path(temp_dir) / "tasks.json").read_text(encoding="utf-8"))
        if tasks["concurrency"]["state"] != "Pending":
            print("CONCURRENCY_STATE_CHANGED", file=sys.stderr)
            return 2
        events = (Path(temp_dir) / "court_events.jsonl").read_text(encoding="utf-8").splitlines()
        if len(events) != 9:
            print(f"CONCURRENCY_EVENT_COUNT {len(events)}", file=sys.stderr)
            return 3
    print("COURT_RUNTIME_CONCURRENCY_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
