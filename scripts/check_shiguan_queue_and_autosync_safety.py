"""Isolated regressions for Shiguan seen-ledger and autosync health truth.

The checks use a temporary shared root and monkeypatched process evidence.  They
do not inspect the host pending queue and do not start or stop real daemons.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
import tempfile
from unittest import mock


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import ensure_shiguan_autosync as autosync  # noqa: E402
import check_shiguan_import_queue as import_queue  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_seen_ledger_concurrency() -> dict[str, object]:
    worker = """
import os
import sys
sys.path.insert(0, os.environ['COURT_TEST_SCRIPTS'])
import check_shiguan_import_queue as queue
queue.queue_summary = lambda limit: {'_pending_ids': [os.environ['COURT_TEST_SEEN_ID']]}
sys.argv = ['check_shiguan_import_queue.py', '--format', 'json', '--mark-seen']
raise SystemExit(queue.main())
""".strip()
    expected = {f"concurrent-{index:02d}" for index in range(32)}
    with tempfile.TemporaryDirectory(prefix="court-seen-ledger-") as raw_temp:
        root = Path(raw_temp)
        processes: list[subprocess.Popen[str]] = []
        for seen_id in sorted(expected):
            env = os.environ.copy()
            env.update(
                {
                    "COURT_SHARED_SHIGUAN_ROOT": str(root),
                    "COURT_DISABLE_AGENT_PRESENCE": "1",
                    "COURT_TEST_SCRIPTS": str(SCRIPTS),
                    "COURT_TEST_SEEN_ID": seen_id,
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-c", worker],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        failures: list[str] = []
        for process in processes:
            _, stderr = process.communicate(timeout=30)
            if process.returncode != 0:
                failures.append(stderr[-1000:])
        require(not failures, f"concurrent --mark-seen workers failed: {failures[:3]}")
        ledger = root / "references" / "shiguan-imports" / "startup-seen.json"
        payload = json.loads(ledger.read_text(encoding="utf-8"))
        actual = {str(item) for item in payload.get("seen_ids", [])}
        require(actual == expected, f"seen ledger lost updates: missing={sorted(expected - actual)}")
        lock_path = root / "references" / "court-runtime" / "shiguan-import-seen.lock"
        require(lock_path.is_file(), "shared seen-ledger lock was not created in the isolated root")
        return {"workers": len(processes), "seen_ids": len(actual), "lock_exists": True}


def check_invalid_sidecar_truth() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="court-invalid-sidecar-") as raw_temp:
        root = Path(raw_temp)
        pending = root / "references" / "shiguan-imports" / "pending"
        pending.mkdir(parents=True)
        bodies = [pending / "extra-key.json", pending / "oversized.json"]
        for body in bodies:
            body.write_bytes(b"opaque-pending-body-never-opened")
        (pending / "extra-key.metadata.json").write_text(
            json.dumps({"id": "extra-key", "content": "must-not-leak"}),
            encoding="utf-8",
        )
        (pending / "oversized.metadata.json").write_bytes(
            b"{" + b" " * import_queue.MAX_SIDECAR_BYTES + b"}"
        )
        original_read_text = Path.read_text
        original_open = Path.open

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path.resolve() in {body.resolve() for body in bodies}:
                raise AssertionError(f"pending body was opened: {path}")
            return original_read_text(path, *args, **kwargs)

        def guarded_open(path: Path, *args: object, **kwargs: object):
            if path.resolve() in {body.resolve() for body in bodies}:
                raise AssertionError(f"pending body was opened: {path}")
            return original_open(path, *args, **kwargs)

        with (
            mock.patch.dict(os.environ, {"COURT_SHARED_SHIGUAN_ROOT": str(root)}),
            mock.patch.object(Path, "read_text", guarded_read_text),
            mock.patch.object(Path, "open", guarded_open),
        ):
            summary = import_queue.queue_summary(8)
        serialized = json.dumps(summary, ensure_ascii=False)
        require(summary.get("unknown_metadata_count") == 2, "invalid sidecars were counted as valid metadata")
        require(summary.get("unknown_estimated_tokens_count") == 2, "missing token metrics were undercounted")
        require("must-not-leak" not in serialized, "unknown sidecar field leaked into queue output")
        require("2 份缺少可用 estimated_tokens" in str(summary.get("startup_message")), "unknown metric message drifted")
        return {"invalid_sidecars": 2, "pending_body_reads": 0, "unknown_tokens": 2}


def fresh_status(pid: int, interval: int = 20) -> dict[str, object]:
    return {
        "ok": True,
        "mode": "daemon",
        "pid": pid,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "interval_seconds": interval,
    }


def check_autosync_health_truth() -> dict[str, object]:
    exact = f'"{sys.executable}" "{autosync.daemon_script()}" --interval 20'
    wrong = autosync.daemon_script().with_name("not-the-daemon.py")
    require(autosync.command_line_runs_daemon(exact), "exact canonical daemon path was not recognized")
    require(
        not autosync.command_line_runs_daemon(f'"{sys.executable}" "{wrong}" --interval 20'),
        "different script path was accepted as the daemon",
    )
    require(
        not autosync.command_line_runs_daemon(f'"{sys.executable}" "{autosync.daemon_script()}.bak"'),
        "daemon-path prefix/suffix lookalike was accepted",
    )
    require(
        autosync.status_is_fresh({"updated_at": datetime.now().astimezone().isoformat()}, 20),
        "timezone-aware daemon timestamp was rejected",
    )
    require(
        not autosync.command_line_runs_daemon(
            f'"{sys.executable}" "{wrong}" --decoy "{autosync.daemon_script()}"'
        ),
        "daemon path in a decoy argument was accepted as the executed script",
    )
    alternate = autosync.daemon_script().parents[2] / ".codex-fixture" / "scripts" / autosync.daemon_script().name
    with mock.patch.object(
        autosync,
        "trusted_daemon_script_paths",
        return_value={
            autosync.normalized_process_path(autosync.daemon_script()),
            autosync.normalized_process_path(alternate),
        },
    ):
        require(
            autosync.command_line_runs_daemon(f'"{sys.executable}" "{alternate}" --interval 20'),
            "trusted alternate active-copy daemon path was not recognized",
        )

    with tempfile.TemporaryDirectory(prefix="court-autosync-health-") as raw_temp:
        isolated_lock = Path(raw_temp) / "obsidian-autosync-ensure.lock"
        with (
            mock.patch.object(autosync, "ensure_lock_path", return_value=isolated_lock),
            mock.patch.object(autosync, "read_json", return_value=fresh_status(101)),
            mock.patch.object(autosync, "pid_alive", side_effect=lambda pid: pid == 101),
            mock.patch.object(autosync, "find_running_daemon_pid", return_value=101),
        ):
            reused = autosync.ensure(20, check_only=False)
        require(reused.get("status") == "REUSED", "fresh same-PID exact process was not reused")

        stale = {"pid": 202, "updated_at": "2000-01-01T00:00:00", "interval_seconds": 20}
        with (
            mock.patch.object(autosync, "ensure_lock_path", return_value=isolated_lock),
            mock.patch.object(autosync, "read_json", return_value=stale),
            mock.patch.object(autosync, "pid_alive", side_effect=lambda pid: pid == 202),
            mock.patch.object(autosync, "find_running_daemon_pid", return_value=202),
            mock.patch.object(autosync, "ensure_shared_seed", side_effect=AssertionError("must not start second daemon")),
            mock.patch.object(autosync, "start_daemon", side_effect=AssertionError("must not start second daemon")),
        ):
            unhealthy = autosync.ensure(20, check_only=False)
        require(unhealthy.get("status") == "RUNNING_UNHEALTHY", "stale running daemon was falsely reused")
        require("status_stale_or_missing" in str(unhealthy.get("reason")), "stale reason was not preserved")

        with (
            mock.patch.object(autosync, "read_json", return_value=stale),
            mock.patch.object(autosync, "pid_alive", side_effect=lambda pid: pid == 202),
            mock.patch.object(autosync, "find_running_daemon_pid", return_value=202),
        ):
            read_only_unhealthy = autosync.ensure(20, check_only=True)
        require(
            read_only_unhealthy.get("status") == "RUNNING_UNHEALTHY",
            "read-only audit hid a stale but still-running daemon",
        )
        require(
            "status_stale_or_missing" in str(read_only_unhealthy.get("reason")),
            "read-only stale-process reason was not preserved",
        )

        with (
            mock.patch.object(autosync, "ensure_lock_path", return_value=isolated_lock),
            mock.patch.object(autosync, "read_json", return_value=fresh_status(303)),
            mock.patch.object(autosync, "pid_alive", return_value=True),
            mock.patch.object(
                autosync,
                "find_running_daemon_pid",
                return_value=autosync.PROCESS_DISCOVERY_MULTIPLE,
            ),
            mock.patch.object(autosync, "start_daemon", side_effect=AssertionError("must not start with duplicates")),
        ):
            multiple = autosync.ensure(20, check_only=False)
        require(multiple.get("status") == "RUNNING_UNHEALTHY", "duplicate daemons were not rejected")

        with (
            mock.patch.object(autosync, "ensure_lock_path", return_value=isolated_lock),
            mock.patch.object(autosync, "read_json", return_value=stale),
            mock.patch.object(autosync, "pid_alive", return_value=True),
            mock.patch.object(autosync, "find_running_daemon_pid", return_value=0),
            mock.patch.object(autosync, "ensure_shared_seed"),
            mock.patch.object(autosync, "start_daemon", return_value=404),
            mock.patch.object(autosync, "write_json"),
        ):
            started = autosync.ensure(20, check_only=False)
        require(started.get("status") == "STARTED" and started.get("pid") == 404, "clean absence did not start one daemon")

    with tempfile.TemporaryDirectory(prefix="court-autosync-read-only-") as raw_temp:
        isolated_root = Path(raw_temp) / "court-data"
        with (
            mock.patch.dict(os.environ, {"COURT_SHARED_SHIGUAN_ROOT": str(isolated_root)}),
            mock.patch.object(autosync, "find_running_daemon_pid", return_value=0),
        ):
            read_only = autosync.ensure(20, check_only=True)
        require(read_only.get("status") == "NOT_RUNNING", "blank read-only audit returned an unexpected state")
        require(not isolated_root.exists(), "--check-only created shared-root or lock state")

    malformed = {
        "ok": True,
        "mode": "daemon",
        "pid": "not-an-int",
        "interval_seconds": "not-an-int",
        "updated_at": "not-a-time",
    }
    with (
        mock.patch.object(autosync, "read_json", return_value=malformed),
        mock.patch.object(autosync, "find_running_daemon_pid", return_value=0),
    ):
        malformed_report = autosync.ensure(20, check_only=True)
    require(malformed_report.get("status") == "NOT_RUNNING", "malformed status crashed or became healthy")

    return {
        "exact_path_match": True,
        "fresh_same_pid": reused.get("status"),
        "stale_exact_process": unhealthy.get("status"),
        "stale_exact_process_check_only": read_only_unhealthy.get("status"),
        "multiple_exact_processes": multiple.get("status"),
        "clean_absence": started.get("status"),
        "blank_check_only_no_write": True,
        "malformed_status_fail_closed": True,
    }


def main() -> int:
    result = {
        "seen_ledger": check_seen_ledger_concurrency(),
        "invalid_sidecar_truth": check_invalid_sidecar_truth(),
        "autosync_health": check_autosync_health_truth(),
    }
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
