"""Exercise crash release and concurrent Shiguan checkpoint integrity."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import tempfile
import time
from typing import Any

from court_file_lock import atomic_write_text, file_lock


CHECKPOINT_WRITERS = 32
WEB_UPSERT_THREADS = 32
ATOMIC_WRITERS = 32


def checkpoint_worker(
    start_event: Any,
    shared_root: str,
    runtime_root: str,
    writer_id: int,
) -> None:
    os.environ["COURT_SHARED_SHIGUAN_ROOT"] = shared_root
    os.environ["COURT_RUNTIME_ROOT"] = runtime_root
    os.environ["COURT_DISABLE_AGENT_PRESENCE"] = "1"
    if not start_event.wait(20):
        raise TimeoutError("checkpoint concurrency start barrier timed out")

    from archive_checkpoint import append_checkpoint

    args = argparse.Namespace(
        topic="concurrency-integrity",
        phase=f"worker-{writer_id}",
        status="PASS",
        summary=f"concurrent checkpoint {writer_id}",
        evidence=f"writer={writer_id}",
        next="none",
        memory_decision="SKIP",
        memory_content="none",
        memory_reason="isolated concurrency self-test",
        risk_level="D",
        knowledge_value="C",
        priority_level="C",
        keywords="concurrency,integrity",
        key_actions=f"writer:{writer_id}",
        source_agent="test",
        full_record="",
        full_record_file=None,
        refresh_mode="async",
        no_refresh=False,
        refresh_tree=False,
        sync=False,
        sync_timeout=5,
        lock_timeout=30.0,
    )
    append_checkpoint(args)


def crash_lock_worker(acquired_event: Any, lock_path: str) -> None:
    with file_lock(Path(lock_path), timeout=5.0):
        acquired_event.set()
        os._exit(17)


def join_processes(processes: list[multiprocessing.Process], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    for process in processes:
        process.join(max(0.0, min(60.0, deadline - time.monotonic())))
    alive = [process for process in processes if process.is_alive()]
    for process in alive:
        process.terminate()
    for process in alive:
        process.join(5)
    if alive:
        raise AssertionError(f"workers timed out: {[process.pid for process in alive]}")


def main() -> int:
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="court-shiguan-concurrency-") as temp_dir:
        temp_root = Path(temp_dir)
        shared_root = temp_root / "shared"
        runtime_root = temp_root / "runtime"

        atomic_target = temp_root / "atomic" / "request.json"
        with ThreadPoolExecutor(max_workers=ATOMIC_WRITERS) as executor:
            futures = [
                executor.submit(
                    atomic_write_text,
                    atomic_target,
                    json.dumps({"state": "complete", "writer": writer_id}, sort_keys=True) + "\n",
                )
                for writer_id in range(ATOMIC_WRITERS)
            ]
            for future in futures:
                future.result(timeout=10)
        atomic_value = json.loads(atomic_target.read_text(encoding="utf-8"))
        assert atomic_value["state"] == "complete"
        assert int(atomic_value["writer"]) in range(ATOMIC_WRITERS)
        assert not list(atomic_target.parent.glob(f".{atomic_target.name}.*.tmp"))

        crash_lock = temp_root / "crash-release.lock"
        acquired = context.Event()
        crashed = context.Process(target=crash_lock_worker, args=(acquired, str(crash_lock)))
        crashed.start()
        assert acquired.wait(15), "crash worker did not acquire the file lock"
        crashed.join(15)
        assert crashed.exitcode == 17, f"unexpected crash worker exit: {crashed.exitcode}"
        with file_lock(crash_lock, timeout=5.0):
            with file_lock(crash_lock, timeout=5.0):
                pass

        start_event = context.Event()
        workers = [
            context.Process(
                target=checkpoint_worker,
                args=(start_event, str(shared_root), str(runtime_root), writer_id),
            )
            for writer_id in range(CHECKPOINT_WRITERS)
        ]
        for worker in workers:
            worker.start()
        start_event.set()
        join_processes(workers, timeout=75.0)
        failures = [(worker.pid, worker.exitcode) for worker in workers if worker.exitcode != 0]
        assert not failures, f"checkpoint workers failed: {failures}"

        index_path = shared_root / "references" / "shiguan-index.jsonl"
        raw_lines = [line for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        entries = [json.loads(line) for line in raw_lines]
        assert len(entries) == CHECKPOINT_WRITERS
        assert len({str(entry.get("daily_sequence")) for entry in entries}) == CHECKPOINT_WRITERS
        assert len({str(entry.get("court_code")) for entry in entries}) == CHECKPOINT_WRITERS
        assert {str(entry.get("phase")) for entry in entries} == {
            f"worker-{writer_id}" for writer_id in range(CHECKPOINT_WRITERS)
        }

        archives = list((shared_root / "references" / "plan-archives").glob("plan-*-concurrency-integrity-1.md"))
        assert len(archives) == 1, f"unexpected archive files: {archives}"
        archive_text = archives[0].read_text(encoding="utf-8")
        assert archive_text.count("## Checkpoint:") == CHECKPOINT_WRITERS
        for entry in entries:
            assert f"- court_code: {entry['court_code']}" in archive_text
        refresh_request = shared_root / "references" / "obsidian-sync" / "refresh-request.json"
        refresh_value = json.loads(refresh_request.read_text(encoding="utf-8"))
        assert refresh_value["reason"] == "archive_checkpoint"
        assert refresh_value["court_code"] in {entry["court_code"] for entry in entries}
        assert not list(refresh_request.parent.glob(f".{refresh_request.name}.*.tmp"))

        os.environ["COURT_SHARED_SHIGUAN_ROOT"] = str(shared_root)
        os.environ["COURT_RUNTIME_ROOT"] = str(runtime_root)
        os.environ["COURT_DISABLE_AGENT_PRESENCE"] = "1"
        from shiguan_paths import ensure_shared_seed

        ensure_shared_seed()
        import serve_shiguan_tree as web

        web.ensure_shared_seed = lambda: shared_root / "references"
        web.refresh_tree = lambda: None

        def upsert(writer_id: int) -> dict[str, object]:
            return web.upsert_entry(
                {
                    "id": f"thread-entry-{writer_id}",
                    "topic": f"threaded upsert {writer_id}",
                    "phase": "concurrency-test",
                    "status": "PASS",
                    "summary": f"serialized web RMW {writer_id}",
                    "evidence": f"thread={writer_id}",
                    "memory_decision": "SKIP",
                    "risk_level": "D",
                    "knowledge_value": "C",
                    "priority_level": "C",
                }
            )

        with ThreadPoolExecutor(max_workers=WEB_UPSERT_THREADS) as executor:
            futures = [executor.submit(upsert, writer_id) for writer_id in range(WEB_UPSERT_THREADS)]
            web_entries = [future.result(timeout=30) for future in futures]
        assert len({str(entry.get("id")) for entry in web_entries}) == WEB_UPSERT_THREADS

        final_lines = [line for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        final_entries = [json.loads(line) for line in final_lines]
        web_ids = {
            str(entry.get("id"))
            for entry in final_entries
            if str(entry.get("id", "")).startswith("thread-entry-")
        }
        assert web_ids == {f"thread-entry-{writer_id}" for writer_id in range(WEB_UPSERT_THREADS)}
        manual_files = list((shared_root / "references" / "shiguan-tree" / "manual").glob("thread-entry-*.json"))
        assert len(manual_files) == WEB_UPSERT_THREADS

    print(
        "SHIGUAN_CONCURRENCY_SELF_TEST_OK "
        + json.dumps(
            {
                "checkpoint_writers": CHECKPOINT_WRITERS,
                "unique_sequences": CHECKPOINT_WRITERS,
                "crash_release": True,
                "atomic_replace": True,
                "atomic_replace_writers": ATOMIC_WRITERS,
                "web_upsert_threads": WEB_UPSERT_THREADS,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
