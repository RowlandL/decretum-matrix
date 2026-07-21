"""Focused regressions for explicit single-session closeout."""

from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode = True

try:
    import court_session_closeout
except ModuleNotFoundError as exc:
    raise AssertionError("SESSION_CLOSEOUT_MODULE_MISSING") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def item(
    sequence: int,
    kind: str,
    content: str,
    *,
    session_id: str = "session-a",
    closed: bool = False,
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "sequence": sequence,
        "kind": kind,
        "content": content,
        "closed": closed,
    }


def check_aggregate_contract() -> None:
    source = [
        item(3, "light_answer", "轻量回答"),
        item(1, "chat", "前置闲聊"),
        item(2, "task", "已自然结诏任务", closed=True),
        item(4, "correction", "后续修正"),
        item(5, "result", "已完成结果", closed=True),
        item(6, "task", "尚未自然结诏任务"),
        item(7, "result", "尚未结诏结果"),
    ]
    original = deepcopy(source)
    draft = court_session_closeout.aggregate_session_closeout(
        source,
        last_closeout_sequence=0,
    )
    require(source == original, "aggregate mutated its input")
    require(draft["session_id"] == "session-a", "aggregate lost session identity")
    require(draft["last_closeout_sequence"] == 0, "aggregate changed starting cursor")
    require(draft["next_closeout_sequence"] == 7, "closed entries did not advance high-water cursor")
    require(
        [entry["sequence"] for entry in draft["items"]] == [1, 3, 4, 6, 7],
        "closed task/result were not excluded or chat ordering drifted",
    )
    require(
        [entry["kind"] for entry in draft["items"]]
        == ["chat", "light_answer", "correction", "task", "result"],
        "explicit closeout did not retain surrounding chat/light content",
    )

    after_cursor = court_session_closeout.aggregate_session_closeout(
        source,
        last_closeout_sequence=3,
    )
    require(
        [entry["sequence"] for entry in after_cursor["items"]] == [4, 6, 7],
        "aggregate re-selected entries at or below cursor",
    )
    require(after_cursor["next_closeout_sequence"] == 7, "high-water cursor regressed")


def check_cross_session_rejected() -> None:
    try:
        court_session_closeout.aggregate_session_closeout(
            [item(1, "chat", "a"), item(2, "chat", "b", session_id="session-b")],
            last_closeout_sequence=0,
        )
    except ValueError as exc:
        require(exc.args == ("cross_session_items",), f"unexpected cross-session error: {exc.args!r}")
    else:
        raise AssertionError("cross-session aggregate was accepted")

    try:
        court_session_closeout.aggregate_session_closeout(
            [item(0, "chat", "zero is not a conversation sequence")],
            last_closeout_sequence=0,
        )
    except ValueError as exc:
        require(exc.args == ("sequence",), f"unexpected zero-sequence error: {exc.args!r}")
    else:
        raise AssertionError("sequence zero was accepted")


def check_commit_transaction_and_idempotency() -> None:
    draft = court_session_closeout.aggregate_session_closeout(
        [item(1, "chat", "hello"), item(2, "light_answer", "world")],
        last_closeout_sequence=0,
    )
    with tempfile.TemporaryDirectory(prefix="decretum-closeout-") as raw:
        root = Path(raw)
        cursor_path = root / "cursor.json"
        failed_calls: list[dict[str, object]] = []

        def failing_writer(value: dict[str, object]) -> dict[str, object]:
            failed_calls.append(value)
            raise RuntimeError("archive failed")

        try:
            court_session_closeout.commit_session_closeout(
                draft,
                archive_writer=failing_writer,
                cursor_path=cursor_path,
            )
        except RuntimeError as exc:
            require(str(exc) == "archive failed", "archive failure was rewritten")
        else:
            raise AssertionError("archive failure was swallowed")
        require(len(failed_calls) == 1, "failing archive writer was not called exactly once")
        require(not cursor_path.exists(), "cursor advanced after archive failure")

        archive_path = root / "archive.md"
        successful_calls: list[dict[str, object]] = []

        def successful_writer(value: dict[str, object]) -> dict[str, object]:
            successful_calls.append(value)
            archive_path.write_text("human editable archive\n", encoding="utf-8")
            return {"archive_path": str(archive_path)}

        receipt = court_session_closeout.commit_session_closeout(
            draft,
            archive_writer=successful_writer,
            cursor_path=cursor_path,
        )
        require(len(successful_calls) == 1, "successful archive writer was not called exactly once")
        require(receipt["archive_written"] is True, "successful commit did not report archive write")
        require(receipt["last_closeout_sequence"] == 2, "successful commit cursor is wrong")
        cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
        require(
            set(cursor)
            == {
                "session_id",
                "last_closeout_sequence",
                "last_archive_path",
                "updated_at",
            },
            "cursor contains transcript, ledger, hash, or extra gate fields",
        )
        require(cursor["session_id"] == "session-a", "cursor session mismatch")
        require(cursor["last_closeout_sequence"] == 2, "cursor sequence mismatch")
        require(cursor["last_archive_path"] == str(archive_path), "cursor archive path mismatch")

        retry_calls: list[dict[str, object]] = []

        def forbidden_retry_writer(value: dict[str, object]) -> dict[str, object]:
            retry_calls.append(value)
            raise AssertionError("retry archived twice")

        retry = court_session_closeout.commit_session_closeout(
            draft,
            archive_writer=forbidden_retry_writer,
            cursor_path=cursor_path,
        )
        require(retry_calls == [], "same end sequence invoked archive writer twice")
        require(retry["archive_written"] is False, "retry did not report idempotent no-op")
        require(retry["last_archive_path"] == str(archive_path), "retry lost prior archive path")


def check_empty_and_closed_only_batches() -> None:
    with tempfile.TemporaryDirectory(prefix="decretum-closeout-empty-") as raw:
        root = Path(raw)
        calls: list[dict[str, object]] = []

        def forbidden_writer(value: dict[str, object]) -> dict[str, object]:
            calls.append(value)
            raise AssertionError("empty draft attempted archive")

        empty = court_session_closeout.aggregate_session_closeout([], last_closeout_sequence=7)
        result = court_session_closeout.commit_session_closeout(
            empty,
            archive_writer=forbidden_writer,
            cursor_path=root / "empty.json",
        )
        require(calls == [], "empty input invoked archive writer")
        require(result["archive_written"] is False, "empty input reported archive write")
        require(not (root / "empty.json").exists(), "truly empty input created a cursor")

        closed_only = court_session_closeout.aggregate_session_closeout(
            [item(8, "task", "already closed", closed=True)],
            last_closeout_sequence=0,
        )
        cursor_path = root / "closed-only.json"
        result = court_session_closeout.commit_session_closeout(
            closed_only,
            archive_writer=forbidden_writer,
            cursor_path=cursor_path,
        )
        require(calls == [], "closed-only input invoked archive writer")
        require(result["last_closeout_sequence"] == 8, "closed-only high-water cursor did not advance")
        cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
        require(cursor["last_closeout_sequence"] == 8, "closed-only cursor file did not advance")
        require(cursor["last_archive_path"] == "", "closed-only cursor invented an archive path")


def check_direct_commit_revalidates_items() -> None:
    draft = court_session_closeout.aggregate_session_closeout(
        [item(1, "chat", "same session")],
        last_closeout_sequence=0,
    )
    forged = deepcopy(draft)
    forged["items"][0]["session_id"] = "session-b"
    with tempfile.TemporaryDirectory(prefix="decretum-closeout-forged-") as raw:
        calls: list[dict[str, object]] = []

        def forbidden_writer(value: dict[str, object]) -> dict[str, object]:
            calls.append(value)
            raise AssertionError("forged draft reached writer")

        try:
            court_session_closeout.commit_session_closeout(
                forged,
                archive_writer=forbidden_writer,
                cursor_path=Path(raw) / "cursor.json",
            )
        except ValueError as exc:
            require(exc.args == ("cross_session_draft",), f"unexpected forged draft error: {exc.args!r}")
        else:
            raise AssertionError("direct commit accepted a cross-session draft")
        require(calls == [], "cross-session draft invoked archive writer")


def check_stale_draft_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="decretum-closeout-stale-") as raw:
        root = Path(raw)
        cursor_path = root / "cursor.json"

        def writer(value: dict[str, object]) -> dict[str, object]:
            path = root / f"archive-{value['next_closeout_sequence']}.md"
            path.write_text("archive\n", encoding="utf-8")
            return {"archive_path": str(path)}

        first = court_session_closeout.aggregate_session_closeout(
            [item(1, "chat", "first")],
            last_closeout_sequence=0,
        )
        court_session_closeout.commit_session_closeout(
            first,
            archive_writer=writer,
            cursor_path=cursor_path,
        )
        stale = court_session_closeout.aggregate_session_closeout(
            [item(1, "chat", "first"), item(2, "chat", "second")],
            last_closeout_sequence=0,
        )
        calls = 0

        def forbidden_stale_writer(value: dict[str, object]) -> dict[str, object]:
            nonlocal calls
            calls += 1
            raise AssertionError("stale draft reached writer")

        try:
            court_session_closeout.commit_session_closeout(
                stale,
                archive_writer=forbidden_stale_writer,
                cursor_path=cursor_path,
            )
        except ValueError as exc:
            require(exc.args == ("stale_closeout_draft",), f"unexpected stale draft error: {exc.args!r}")
        else:
            raise AssertionError("stale draft was accepted")
        require(calls == 0, "stale draft invoked archive writer")
        cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
        require(cursor["last_closeout_sequence"] == 1, "stale draft changed cursor")


def check_concurrent_same_draft_archives_once() -> None:
    draft = court_session_closeout.aggregate_session_closeout(
        [item(1, "chat", "one"), item(2, "light_answer", "two")],
        last_closeout_sequence=0,
    )
    with tempfile.TemporaryDirectory(prefix="decretum-closeout-concurrent-") as raw:
        root = Path(raw)
        cursor_path = root / "cursor.json"
        start = threading.Barrier(3)
        calls: list[int] = []
        calls_lock = threading.Lock()
        results: list[dict[str, object]] = []
        errors: list[BaseException] = []

        def writer(value: dict[str, object]) -> dict[str, object]:
            with calls_lock:
                calls.append(int(value["next_closeout_sequence"]))
            time.sleep(0.1)
            path = root / "archive.md"
            path.write_text("one archive\n", encoding="utf-8")
            return {"archive_path": str(path)}

        def worker() -> None:
            start.wait()
            try:
                results.append(
                    court_session_closeout.commit_session_closeout(
                        draft,
                        archive_writer=writer,
                        cursor_path=cursor_path,
                    )
                )
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        start.wait()
        for thread in threads:
            thread.join(timeout=5)
        require(all(not thread.is_alive() for thread in threads), "concurrent commit threads did not finish")
        require(errors == [], f"concurrent commit raised: {errors!r}")
        require(calls == [2], f"concurrent same draft archived {len(calls)} times")
        require(len(results) == 2, "concurrent commit lost a result")
        require(
            sorted(result["archive_written"] for result in results) == [False, True],
            "concurrent commit did not produce one writer and one idempotent reader",
        )


def check_default_writer_stays_lightweight() -> None:
    draft = court_session_closeout.aggregate_session_closeout(
        [item(1, "chat", "human editable")],
        last_closeout_sequence=0,
    )
    with tempfile.TemporaryDirectory(prefix="decretum-closeout-writer-") as raw:
        previous = os.environ.get("COURT_SHARED_SHIGUAN_ROOT")
        os.environ["COURT_SHARED_SHIGUAN_ROOT"] = raw
        try:
            import archive_checkpoint

            original_receipt_builder = archive_checkpoint.build_archive_receipt

            def forbidden_receipt_builder(*args: object, **kwargs: object) -> dict[str, object]:
                raise AssertionError("ordinary closeout constructed an archive receipt")

            archive_checkpoint.build_archive_receipt = forbidden_receipt_builder
            try:
                result = court_session_closeout._default_archive_writer(draft)
            finally:
                archive_checkpoint.build_archive_receipt = original_receipt_builder

            require(
                set(result) <= {"archive_path", "court_code"},
                "ordinary closeout constructed an archive/receipt hash envelope",
            )
            require(
                not archive_checkpoint.refresh_request_path().exists(),
                "ordinary closeout requested derived-tree refresh",
            )
        finally:
            if previous is None:
                os.environ.pop("COURT_SHARED_SHIGUAN_ROOT", None)
            else:
                os.environ["COURT_SHARED_SHIGUAN_ROOT"] = previous


def check_unified_cli_roundtrip() -> None:
    with tempfile.TemporaryDirectory(prefix="decretum-closeout-cli-") as raw:
        root = Path(raw)
        request_path = root / "request.json"
        shared_root = root / "shared-shiguan"
        request = {
            "schema": "court.session_closeout.request.v1",
            "session_id": "session-cli",
            "items": [
                item(1, "chat", "cli chat", session_id="session-cli"),
                item(2, "light_answer", "cli answer", session_id="session-cli"),
            ],
        }
        request_path.write_text(
            json.dumps(request, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        env = dict(os.environ)
        env["COURT_SHARED_SHIGUAN_ROOT"] = str(shared_root)
        command = [
            sys.executable,
            "-B",
            "scripts/court_cli.py",
            "--format",
            "json",
            "court",
            "closeout-session",
            "--request-file",
            str(request_path),
        ]
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        require(completed.returncode == 0, f"unified CLI failed: {completed.stderr or completed.stdout}")
        envelope = json.loads(completed.stdout)
        require(envelope["ok"] is True, "unified CLI envelope is not successful")
        require(envelope["command"] == "court closeout-session", "unified CLI command label drifted")
        payload = envelope["payload"]
        require(payload["schema"] == "court.session_closeout.receipt.v1", "CLI receipt schema drifted")
        payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        require("archive_sha256" not in payload_text, "CLI payload exposed an archive hash gate")
        require("receipt_sha256" not in payload_text, "CLI payload exposed a receipt hash gate")
        require(payload["archive_written"] is True, "CLI did not archive the session")
        require(payload["last_closeout_sequence"] == 2, "CLI did not advance cursor")
        archive_path = Path(payload["last_archive_path"])
        cursor_path = Path(payload["cursor_path"])
        require(archive_path.is_file(), "CLI archive path does not exist")
        require(cursor_path.is_file(), "CLI cursor path does not exist")
        require(shared_root.resolve() in cursor_path.resolve().parents, "CLI cursor escaped shared Shiguan root")
        require(
            not (shared_root / "references" / "obsidian-sync" / "refresh-request.json").exists(),
            "CLI closeout requested derived-tree/Obsidian refresh",
        )
        first_archive = archive_path.read_bytes()

        repeated = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        require(repeated.returncode == 0, f"CLI retry failed: {repeated.stderr or repeated.stdout}")
        repeated_payload = json.loads(repeated.stdout)["payload"]
        require(repeated_payload["archive_written"] is False, "CLI retry archived twice")
        require(archive_path.read_bytes() == first_archive, "CLI retry changed the archive")


def check_public_request_and_error_envelopes() -> None:
    with tempfile.TemporaryDirectory(prefix="decretum-closeout-errors-") as raw:
        root = Path(raw)
        shared_root = root / "shared-shiguan"
        previous = os.environ.get("COURT_SHARED_SHIGUAN_ROOT")
        os.environ["COURT_SHARED_SHIGUAN_ROOT"] = str(shared_root)
        try:
            injected = {
                "schema": "court.session_closeout.request.v1",
                "session_id": "session-injected",
                "items": [item(1, "chat", "must not choose cursor", session_id="session-injected")],
                "cursor_path": str(root / "arbitrary-local-file.json"),
            }
            injected_path = root / "injected.json"
            injected_path.write_text(json.dumps(injected), encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = court_session_closeout.main(
                    ["--request-file", str(injected_path), "--format", "json"]
                )
            payload = json.loads(stdout.getvalue())
            require(code == 3, "cursor_path injection was not classified INVALID")
            require(payload["error_code"] == "invalid_request_fields", "cursor_path error code drifted")
            require(not (root / "arbitrary-local-file.json").exists(), "cursor_path injection wrote a file")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = court_session_closeout.main(
                    ["--request-file", str(root / "missing.json"), "--format", "json"]
                )
            payload = json.loads(stdout.getvalue())
            require(code == 3, "missing request file was not classified INVALID")
            require(payload["error_code"] == "invalid_request_file", "missing request error code drifted")

            broken_path = root / "broken.json"
            broken_path.write_text("{broken", encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = court_session_closeout.main(
                    ["--request-file", str(broken_path), "--format", "json"]
                )
            payload = json.loads(stdout.getvalue())
            require(code == 3, "broken JSON was not classified INVALID")
            require(payload["error_code"] == "invalid_request_json", "broken JSON error code drifted")

            valid_path = root / "valid.json"
            valid_path.write_text(
                json.dumps(
                    {
                        "schema": "court.session_closeout.request.v1",
                        "session_id": "session-blocked",
                        "items": [item(1, "chat", "archive blocks", session_id="session-blocked")],
                    }
                ),
                encoding="utf-8",
            )
            original_writer = court_session_closeout._default_archive_writer

            def blocked_writer(value: dict[str, object]) -> dict[str, object]:
                raise RuntimeError("archive unavailable")

            court_session_closeout._default_archive_writer = blocked_writer
            try:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    code = court_session_closeout.main(
                        ["--request-file", str(valid_path), "--format", "json"]
                    )
            finally:
                court_session_closeout._default_archive_writer = original_writer
            payload = json.loads(stdout.getvalue())
            require(code == 2, "archive runtime error was not classified BLOCKED")
            require(payload["error_code"] == "blocked_archive_runtime", "blocked archive error code drifted")
            require(payload["ok"] is False, "blocked archive response lost JSON failure envelope")
        finally:
            if previous is None:
                os.environ.pop("COURT_SHARED_SHIGUAN_ROOT", None)
            else:
                os.environ["COURT_SHARED_SHIGUAN_ROOT"] = previous


def main() -> int:
    check_aggregate_contract()
    check_cross_session_rejected()
    check_commit_transaction_and_idempotency()
    check_empty_and_closed_only_batches()
    check_direct_commit_revalidates_items()
    check_stale_draft_rejected()
    check_concurrent_same_draft_archives_once()
    check_default_writer_stays_lightweight()
    check_unified_cli_roundtrip()
    check_public_request_and_error_envelopes()
    print("COURT_SESSION_CLOSEOUT_OK core=PASS transaction=PASS cli=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
