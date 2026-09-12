"""Exercise ledger recovery, bounded history reads, and concurrent CLI writers."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import json
import os
import subprocess
import tempfile

sys.dont_write_bytecode = True

from court_intake_gate import minimal_request_understanding_example


def check_transition_recovery() -> None:
    from argparse import Namespace
    from unittest.mock import patch
    import court_runtime as runtime
    from checks.check_court_runtime import create_args, formal_gate_fixture

    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"COURT_RUNTIME_ROOT": directory}):
        runtime.create_task(create_args("paired", intake_gate=formal_gate_fixture()))
        paths = (runtime.tasks_path(), runtime.events_path())
        with paths[1].open("ab") as stream:
            stream.write(b"\xff\n")  # Preserve existing malformed history byte-for-byte.
        before = tuple(path.read_bytes() for path in paths)
        args = Namespace(task_id="paired", to_state="Taizi", actor="taizi", owner="",
                         heartbeat="", evidence="transaction test", note="")

        def partial_event(event):
            line = (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode()
            with runtime.events_path().open("ab") as stream:
                stream.write(line[:13])
            raise OSError("partial event")

        for target, failure in (("write_tasks", OSError("task write")),
                                ("append_event", OSError("event write")),
                                ("append_event", partial_event)):
            try:
                with patch.object(runtime, target, side_effect=failure):
                    runtime.apply_transition(args)
            except OSError:
                pass
            else:
                raise AssertionError("injected failure was ignored")
            assert tuple(path.read_bytes() for path in paths) == before

        for phase in ("task", "event"):
            callback = "os._exit(77)" if phase == "task" else "(append(e),os._exit(77))"
            code = (
                "import os,sys;sys.path.insert(0,'scripts');import court_runtime as r;"
                f"from argparse import Namespace;append=r.append_event;r.append_event=lambda e:{callback};"
                "r.apply_transition(Namespace(task_id='paired',to_state='Taizi',actor='taizi',"
                "owner='',heartbeat='',evidence='transaction test',note=''))"
            )
            crashed = subprocess.run([sys.executable, "-B", "-c", code],
                                     cwd=Path(__file__).resolve().parents[2], timeout=15)
            assert crashed.returncode == 77
            interrupted = tuple(path.read_bytes() for path in paths)
            for read in (runtime.load_tasks, runtime.read_events):
                try:
                    read()
                except ValueError as exc:
                    assert str(exc) == "ledger_pair_recovery_required"
                else:
                    raise AssertionError("partial state was exposed")
            try:
                with runtime.runtime_lock(recover=False):
                    raise AssertionError("read-only recovery was accepted")
            except ValueError as exc:
                assert str(exc) == "ledger_pair_recovery_required"
            assert tuple(path.read_bytes() for path in paths) == interrupted
            paths[0].write_bytes(b'{"external":"edit"}')
            try:
                with runtime.runtime_lock():
                    raise AssertionError("conflicting state was overwritten")
            except ValueError as exc:
                assert str(exc) == "ledger_pair_recovery_conflict"
            assert paths[0].read_bytes() == b'{"external":"edit"}'
            assert paths[1].read_bytes() == interrupted[1]
            paths[0].write_bytes(interrupted[0])
            with runtime.runtime_lock():
                assert tuple(path.read_bytes() for path in paths) == before
        runtime.apply_transition(args)
        assert runtime.load_tasks()["paired"]["state"] == "Taizi"
        assert len(runtime.read_events()) == 2


def check_event_history() -> None:
    from unittest.mock import patch
    import court_runtime as runtime

    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"COURT_RUNTIME_ROOT": directory}):
        rows = [{"task_id": "old", "note": "中文" * 40000},
                {"task_id": "old", "note": "line\u2028separator"}, {"task_id": "latest"}]
        path = runtime.events_path()
        path.write_bytes(b"\r\n".join(json.dumps(row, ensure_ascii=False).encode() for row in rows)
                         + b"\nnull\n[]\ninvalid\n")
        assert runtime.read_events(limit=None) == rows
        assert runtime.read_events(limit=1) == rows[-1:]
        assert runtime.read_events(limit=2, task_id="old") == rows[:2]
        assert runtime.read_events(limit=0) == rows[-1:]
        assert runtime.read_events(limit=20, task_id="missing") == []
        # Finite queries must stop at the tail even when old history is large.
        with path.open("rb") as handle:
            from io import BytesIO
            class CountingReader(BytesIO):
                bytes_read = 0
                def read(self, size=-1):
                    value = super().read(size)
                    self.bytes_read += len(value)
                    return value
            reader = CountingReader(handle.read())
        with patch.object(Path, "open", return_value=reader):
            assert runtime.read_events(limit=1) == rows[-1:]
        assert reader.bytes_read <= 65536


def main() -> int:
    check_transition_recovery()
    check_event_history()
    script = Path(__file__).resolve().parents[1] / "court_cli.py"
    with tempfile.TemporaryDirectory() as temp_dir:
        env = dict(os.environ)
        env["COURT_RUNTIME_ROOT"] = temp_dir
        intake_file = Path(temp_dir) / "formal-task-intake.json"
        intake_file.write_text(
            json.dumps(
                {
                    "schema": "court.conversation_gate.v1",
                    "active_decree": False,
                    "active_decree_state": "NONE",
                    "message_class": "FORMAL_TASK",
                    "confidence": "HIGH",
                    "relation_to_active_decree": "NEW_TASK",
                    "taskization_consent": "EXPLICIT",
                    "requires_tools": True,
                    "mutates_state": True,
                    "risk_present": False,
                    "next_route": "THREE_DEPARTMENTS",
                    "question": "",
                    "rationale": "concurrency smoke formal task fixture",
                    "understanding": minimal_request_understanding_example(),
                }
            ),
            encoding="utf-8",
        )
        create = subprocess.run(
            [
                sys.executable,
                str(script),
                "create",
                "--legacy-compatibility",
                "--task-id",
                "concurrency",
                "--title",
                "concurrency smoke",
                "--charter",
                "concurrency smoke charter",
                "--evidence",
                "create",
                "--work-kind",
                "operation",
                "--intake-file",
                str(intake_file),
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

