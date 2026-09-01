"""Self-test decree usage estimates and summary aggregation."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
import tempfile
from typing import Any


CONCURRENT_WRITERS = 32


def concurrent_worker(start_event: Any, runtime_root: str, writer_id: int) -> None:
    os.environ["COURT_RUNTIME_ROOT"] = runtime_root
    start_event.wait(20)
    from court_usage_ledger import now_text, write_event

    write_event(
        {
            "kind": "record",
            "recorded_at": now_text(),
            "task_id": "usage-concurrent",
            "role": f"worker-{writer_id}",
            "agent_id": f"agent-{writer_id}",
            "source": "agent_reported",
            "precision": "exact_or_reported",
            "input_tokens": writer_id,
            "output_tokens": 1,
            "total_tokens": writer_id + 1,
            "wall_seconds": 0.01,
            "started_at": "",
            "ended_at": "",
            "note": f"concurrent-writer-{writer_id}",
        }
    )


def run(script: Path, args: list[str], env: dict[str, str]) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(script), "--format", "json", *args],
        cwd=str(script.parents[2]),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout)


def main() -> int:
    script = Path(__file__).resolve().parents[1] / "court_usage_ledger.py"
    with tempfile.TemporaryDirectory() as temp_dir:
        env = dict(os.environ)
        env["COURT_RUNTIME_ROOT"] = temp_dir
        estimate = run(
            script,
            [
                "estimate",
                "--task-id",
                "usage-test",
                "--decree",
                "super parallel add usage accounting",
                "--authority",
                "super",
                "--behavior",
                "parallel",
                "--runtime",
                "native",
                "--roles",
                "hubu,gongbu,xingbu",
                "--subagent-count",
                "2",
                "--expected-tool-calls",
                "4",
            ],
            env,
        )
        assert estimate["kind"] == "estimate"
        assert estimate["token_estimate"]["total_tokens"] > 0
        run(
            script,
            [
                "record",
                "--task-id",
                "usage-test",
                "--role",
                "taizi",
                "--source",
                "provider_reported",
                "--input-tokens",
                "100",
                "--output-tokens",
                "50",
                "--wall-seconds",
                "12.5",
            ],
            env,
        )
        run(
            script,
            [
                "record",
                "--task-id",
                "usage-test",
                "--role",
                "gongbu",
                "--source",
                "estimated_fallback",
                "--estimate-from-text",
                "fallback text for a child office report",
                "--wall-seconds",
                "30",
            ],
            env,
        )
        run(
            script,
            [
                "record",
                "--task-id",
                "usage-test",
                "--role",
                "menxia",
                "--source",
                "unavailable",
                "--note",
                "child office did not expose token telemetry",
            ],
            env,
        )
        summary = run(script, ["summary", "--task-id", "usage-test"], env)
        assert summary["kind"] == "usage_summary"
        assert summary["latest_estimate"]["authority"] == "super"
        assert summary["latest_estimate"]["behavior"] == "parallel"
        assert summary["latest_estimate"]["runtime"] == "native"
        assert summary["actual"]["total_tokens"] >= 150
        assert summary["actual"]["precision"] == "mixed"
        assert summary["actual"]["token_usage_precision"] == "mixed"
        assert summary["actual"]["worker_elapsed_sum_seconds"] == 42.5
        assert summary["actual"]["wall_clock_actual_seconds"] is None
        assert len(summary["usage_source_breakdown"]) == 3
        assert "taizi" in summary["by_role"]
        assert "gongbu" in summary["by_role"]
        assert summary["by_role"]["menxia"]["total_tokens"] is None
        assert summary["by_role"]["menxia"]["wall_seconds"] is None
        run(
            script,
            [
                "record",
                "--task-id",
                "usage-total-only",
                "--role",
                "taizi",
                "--source",
                "provider_reported",
                "--total-tokens",
                "123",
            ],
            env,
        )
        run(
            script,
            [
                "record",
                "--task-id",
                "usage-total-only",
                "--role",
                "menxia",
                "--source",
                "unavailable",
            ],
            env,
        )
        total_only = run(script, ["summary", "--task-id", "usage-total-only"], env)
        assert total_only["actual"]["total_tokens"] == 123
        assert total_only["actual"]["input_tokens"] is None
        assert total_only["actual"]["output_tokens"] is None
        assert total_only["actual"]["token_record_count"] == 1
        ledger = Path(temp_dir) / "usage-ledger.jsonl"
        assert ledger.exists()
        ledger.write_text(ledger.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8", newline="\n")

        context = multiprocessing.get_context("spawn")
        start_event = context.Event()
        workers = [
            context.Process(target=concurrent_worker, args=(start_event, temp_dir, index))
            for index in range(CONCURRENT_WRITERS)
        ]
        for worker in workers:
            worker.start()
        start_event.set()
        for worker in workers:
            worker.join(40)
            if worker.is_alive():
                worker.terminate()
                worker.join(5)
                raise AssertionError(f"usage writer timed out: pid={worker.pid}")
            assert worker.exitcode == 0, f"usage writer failed: pid={worker.pid} exit={worker.exitcode}"

        raw_lines = [line for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
        events = [json.loads(line) for line in raw_lines]
        concurrent = [event for event in events if event.get("task_id") == "usage-concurrent"]
        assert len(concurrent) == CONCURRENT_WRITERS
        assert len({event["note"] for event in concurrent}) == CONCURRENT_WRITERS
        concurrent_summary = run(script, ["summary", "--task-id", "usage-concurrent"], env)
        assert concurrent_summary["record_count"] == CONCURRENT_WRITERS
        assert concurrent_summary["actual"]["token_record_count"] == CONCURRENT_WRITERS
    print("COURT_USAGE_LEDGER_SELF_TEST_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())


