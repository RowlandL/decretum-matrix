"""Check start-of-conversation court_code allocation with closeout reuse
(P3-1 fix): issue-at-start -> closeout reuse (not regeneration), idempotency,
collision avoidance across concurrent sessions, fallback when no allocation
exists, and CLI issue/show round-trip, all against isolated temp directories."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from archive_checkpoint import build_index_entry  # noqa: E402
from court_session_numbering import (  # noqa: E402
    domain_court_code_issue,
    resolve_session_allocation,
)


COURT_CODE_RE = re.compile(r"^[A-Z0-9]+-\d{8}-[0-9A-Z]+-[A-Z0-9]{4}$")


def _closeout_args(session_id: str, allocation: dict[str, object] | None) -> argparse.Namespace:
    return argparse.Namespace(
        topic="测试结诏会话编号复用",
        phase="结诏",
        status="DONE",
        summary="结诏复用会话开始分配的编号",
        evidence="synthetic closeout probe",
        next="none",
        memory_decision="SKIP",
        memory_content="none",
        memory_reason="closeout probe",
        risk_level=None,
        knowledge_value=None,
        priority_level=None,
        keywords="测试,结诏",
        key_actions="closeout",
        source_agent=None,
        session_id=session_id,
        session_allocation=allocation,
    )


def evaluate() -> dict[str, Any]:
    failures: list[str] = []
    evidence: dict[str, Any] = {}

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        numbering_root = temp / "session-numbering"
        index = temp / "index.jsonl"

        # 1. Issue at conversation start (unified generator, persisted).
        issued = domain_court_code_issue(
            "sess-start-1",
            "史馆索引检索优化",
            date_text="20260101",
            index=index,
            numbering_root=numbering_root,
        )
        if not (issued.get("ok") is True and issued.get("preview_only") is False):
            failures.append("issue_not_allocated")
        court_code = str(issued.get("court_code") or "")
        if not COURT_CODE_RE.fullmatch(court_code):
            failures.append(f"issued_court_code_invalid:{court_code}")
        if issued.get("generator") != "archive_checkpoint.next_daily_sequence":
            failures.append("issued_generator_not_unified")
        if not issued.get("receipt_hint"):
            failures.append("issued_receipt_hint_missing")
        allocation_file = numbering_root / "sess-start-1.json"
        if not allocation_file.exists():
            failures.append("allocation_file_not_persisted")
        evidence["issue_at_start_ok"] = True
        evidence["issued_court_code"] = court_code

        # 2. Idempotent per session: re-issue returns the same code.
        reissued = domain_court_code_issue(
            "sess-start-1",
            "史馆索引检索优化",
            date_text="20260101",
            index=index,
            numbering_root=numbering_root,
        )
        if not (reissued.get("idempotent") is True and reissued.get("court_code") == court_code):
            failures.append("issue_not_idempotent_per_session")
        evidence["issue_idempotent"] = (
            reissued.get("idempotent") is True
            and reissued.get("court_code") == court_code
        )

        # 3. Collision avoidance: a second session on the same date gets a
        # different daily sequence, even before any closeout writes the index.
        second = domain_court_code_issue(
            "sess-start-2",
            "安装包打包",
            date_text="20260101",
            index=index,
            numbering_root=numbering_root,
        )
        if second.get("daily_sequence") == issued.get("daily_sequence"):
            failures.append("concurrent_allocation_collision")
        if second.get("court_code") == court_code:
            failures.append("concurrent_allocation_same_court_code")
        evidence["concurrent_sessions_distinct"] = (
            second.get("daily_sequence") != issued.get("daily_sequence")
        )

        # R-09: concurrent allocations on the same date must be serialized so
        # the read-compute-write section never overlaps (two sessions computing
        # the same daily_sequence from the same allocation set). Overlap is
        # detected deterministically via a patched _next_sequence that widens
        # the in-section window; a second functional assertion checks the two
        # concurrent sessions get distinct sequences.
        import threading
        import time
        from unittest import mock
        import court_session_numbering as csn

        concurrency_root = temp / "concurrency-numbering"
        overlap = {"detected": False}
        active = {"n": 0}
        gate = threading.Lock()
        original_next = csn._next_sequence

        def racing_next(index_path, date_text, root):
            with gate:
                active["n"] += 1
                if active["n"] > 1:
                    overlap["detected"] = True
            time.sleep(0.05)
            try:
                return original_next(index_path, date_text, root)
            finally:
                with gate:
                    active["n"] -= 1

        results: dict[int, dict[str, Any]] = {}

        def worker(idx: int) -> None:
            results[idx] = csn.domain_court_code_issue(
                f"sess-concurrent-{idx}",
                f"并发主题-{idx}",
                date_text="20260101",
                index=index,
                numbering_root=concurrency_root,
            )

        threads = []
        with mock.patch.object(csn, "_next_sequence", side_effect=racing_next):
            for idx in range(2):
                thread = threading.Thread(target=worker, args=(idx,))
                threads.append(thread)
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
        seqs = [str(results[idx].get("daily_sequence") or "") for idx in range(2)]
        if overlap["detected"]:
            failures.append("concurrent_allocation_read_compute_write_overlapped")
        if len(set(seqs)) != 2:
            failures.append(f"concurrent_allocation_sequence_collision:{seqs}")
        evidence["concurrent_serialized_no_overlap"] = not overlap["detected"]
        evidence["concurrent_sequences_distinct"] = len(set(seqs)) == 2

        # 4. Closeout reuse: build_index_entry with the session allocation must
        # keep the issued court_code verbatim (no regeneration).
        now = datetime.fromisoformat("2026-01-01T12:00:00+08:00")
        path = temp / "archive-20260101-sess.md"
        allocated_args = _closeout_args("sess-start-1", issued)
        entry = build_index_entry(
            allocated_args,
            now,
            path,
            "SKIP",
            "none",
            "closeout probe",
            False,
        )
        if entry.get("court_code") != court_code:
            failures.append(
                f"closeout_did_not_reuse_issued_code:{entry.get('court_code')} != {court_code}"
            )
        if entry.get("court_code_issued_at_start") is not True:
            failures.append("closeout_issued_at_start_flag_missing")
        if entry.get("daily_sequence") != issued.get("daily_sequence"):
            failures.append("closeout_daily_sequence_drift")
        evidence["closeout_reuses_issued_code"] = (
            entry.get("court_code") == court_code
            and entry.get("court_code_issued_at_start") is True
        )

        # 5. Fallback: without an allocation, build_index_entry computes a
        # normal number (existing behavior, no issued-at-start flag).
        fallback_args = _closeout_args("sess-noalloc", None)
        fallback_entry = build_index_entry(
            fallback_args,
            now,
            path,
            "SKIP",
            "none",
            "closeout probe",
            False,
        )
        if fallback_entry.get("court_code_issued_at_start") is not None:
            failures.append("fallback_entry_has_issued_flag")
        if not COURT_CODE_RE.fullmatch(
            str(fallback_entry.get("court_code") or "")
        ):
            failures.append("fallback_court_code_invalid")
        evidence["fallback_without_allocation"] = (
            fallback_entry.get("court_code_issued_at_start") is None
        )

        # 6. resolve_session_allocation: wrong date / missing session -> None.
        if resolve_session_allocation("sess-start-1", "20260102", numbering_root) is not None:
            failures.append("resolve_wrong_date_not_none")
        if resolve_session_allocation("missing-session", "20260101", numbering_root) is not None:
            failures.append("resolve_missing_session_not_none")
        evidence["resolve_gates"] = True

        # 7. CLI issue/show round-trip (isolated temp roots).
        proc = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPTS / "court_session_numbering.py"),
                "issue",
                "--session-id",
                "cli-sess",
                "--topic",
                "CLI 冒烟",
                "--date",
                "20260102",
                "--index",
                str(index),
                "--root",
                str(numbering_root),
                "--json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            failures.append("cli_issue_failed")
        else:
            cli_issued = json.loads(proc.stdout)
            show_proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "court_session_numbering.py"),
                    "show",
                    "--session-id",
                    "cli-sess",
                    "--date",
                    "20260102",
                    "--root",
                    str(numbering_root),
                    "--json",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if show_proc.returncode != 0:
                failures.append("cli_show_failed")
            else:
                cli_shown = json.loads(show_proc.stdout)
                if cli_shown.get("court_code") != cli_issued.get("court_code"):
                    failures.append("cli_show_mismatch")
        evidence["cli_round_trip"] = True

    failures = list(dict.fromkeys(failures))
    return {
        "schema": "court.court_code_session_numbering_check.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": "COURT_CODE_SESSION_NUMBERING",
        "evidence": evidence,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate()
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": "court.court_code_session_numbering_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "COURT_CODE_SESSION_NUMBERING",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        for stream in (sys.stdout,):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"COURT_CODE_SESSION_NUMBERING={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
