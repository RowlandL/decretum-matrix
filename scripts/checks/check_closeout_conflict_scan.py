"""Check closeout conflict/expiry handling (D2a / P3-6): fixture-driven
SUPERSEDED / DEGRADED / REVIEW decisions, determinism, Git revision on apply,
before/after + reason + user-notice fields, approval refusal and incremental
affected-topic scoping (P3-8 interface)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
from unittest import mock

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from closeout_conflict_scan import apply_decisions, scan  # noqa: E402
import domain_ledger_api  # noqa: E402
from domain_ledger_api import domain_ledger_read  # noqa: E402


FIXTURE = (
    ROOT / "references" / "fixtures" / "closeout-conflict-expiry.json"
)


def _git_init(tmp: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp), "config", "user.email", "check@local"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp), "config", "user.name", "check"], check=True
    )


def _git_output(tmp: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(tmp), *args], text=True, encoding="utf-8", errors="replace").strip()


def _git_bytes(tmp: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(tmp), *args])


def evaluate() -> dict[str, Any]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if fixture.get("schema") != "court.closeout_conflict_expiry_fixture.v1":
        raise ValueError("closeout_fixture_schema_invalid")
    entries = [dict(item) for item in fixture["entries"]]
    for entry in entries:
        if entry.get("record_uid") in {"CONFLICT-NEW", "CONFLICT-OLD"}:
            entry["conflict_key"] = "install-validation-rule"
    as_of = fixture["as_of"]
    expected = fixture["expected"]
    failures: list[str] = []

    report = scan(entries, as_of)
    decision_map = {
        str(item["record_uid"]): item
        for item in report["decisions"]
    }
    superseded = {
        uid for uid, item in decision_map.items() if item["action"] == "SUPERSEDED"
    }
    degraded = {
        uid for uid, item in decision_map.items() if item["action"] == "DEGRADED"
    }
    review = {
        uid for uid, item in decision_map.items() if item["action"] == "REVIEW"
    }
    decided = set(decision_map)
    clean = {str(item.get("record_uid")) for item in entries} - decided

    if superseded != set(expected["superseded_uids"]):
        failures.append(f"closeout_superseded_set_mismatch:{sorted(superseded)}")
    if degraded != set(expected["degraded_uids"]):
        failures.append(f"closeout_degraded_set_mismatch:{sorted(degraded)}")
    if review != set(expected["review_uids"]):
        failures.append(f"closeout_review_set_mismatch:{sorted(review)}")
    if clean != set(expected["clean_uids"]):
        failures.append(f"closeout_clean_set_mismatch:{sorted(clean)}")

    superseded_item = decision_map.get("CONFLICT-OLD")
    if superseded_item is None or not (
        superseded_item.get("deterministic") is True
        and superseded_item.get("superseded_by") == "CONFLICT-NEW"
        and superseded_item.get("before") == "WRITE"
        and superseded_item.get("after") == "SUPERSEDED"
        and bool(superseded_item.get("user_notice"))
    ):
        failures.append("closeout_superseded_metadata_invalid")
    degraded_item = decision_map.get("EXPIRED-REC")
    if degraded_item is None or not (
        degraded_item.get("deterministic") is True
        and degraded_item.get("after") == "DEGRADED"
        and degraded_item.get("reason") == "record_expired"
        and bool(degraded_item.get("user_notice"))
    ):
        failures.append("closeout_degraded_metadata_invalid")
    review_items = [decision_map[uid] for uid in expected["review_uids"] if uid in decision_map]
    if not review_items or not all(
        item.get("deterministic") is False for item in review_items
    ):
        failures.append("closeout_review_not_advisory")

    complementary_entries = [
        {
            "record_uid": "COMPLEMENT-TIMEOUT",
            "topic": "服务运行参数",
            "time": "2026-09-01T00:00:00+00:00",
            "memory_decision": "WRITE",
            "memory_content": "timeout=30",
            "conflict_key": "timeout",
        },
        {
            "record_uid": "COMPLEMENT-LOGLEVEL",
            "topic": "服务运行参数",
            "time": "2026-09-02T00:00:00+00:00",
            "memory_decision": "WRITE",
            "memory_content": "log-level=debug",
            "conflict_key": "log-level",
        },
    ]
    complementary_report = scan(complementary_entries, "2026-09-05T00:00:00+00:00")
    if complementary_report["decisions"]:
        failures.append("closeout_complementary_structured_facts_not_clean")

    unstructured_entries = [
        {
            "record_uid": "UNSTRUCTURED-OLD",
            "topic": "未结构化主题",
            "time": "2026-09-01T00:00:00+00:00",
            "memory_decision": "WRITE",
            "memory_content": "value=old",
        },
        {
            "record_uid": "UNSTRUCTURED-NEW",
            "topic": "未结构化主题",
            "time": "2026-09-02T00:00:00+00:00",
            "memory_decision": "WRITE",
            "memory_content": "value=new",
        },
    ]
    unstructured_report = scan(unstructured_entries, "2026-09-05T00:00:00+00:00")
    unstructured_reviews = {item["record_uid"] for item in unstructured_report["decisions"] if item["action"] == "REVIEW"}
    if unstructured_reviews != {"UNSTRUCTURED-OLD", "UNSTRUCTURED-NEW"} or any(item["deterministic"] for item in unstructured_report["decisions"]):
        failures.append("closeout_unstructured_content_not_sent_to_review")

    future_entries = [
        {
            "record_uid": "CURRENT-FACT",
            "topic": "未来配置",
            "time": "2026-09-01T00:00:00+00:00",
            "memory_decision": "WRITE",
            "memory_content": "mode=current",
            "conflict_key": "mode",
            "valid_from": "2026-09-01T00:00:00+00:00",
        },
        {
            "record_uid": "FUTURE-FACT",
            "topic": "未来配置",
            "time": "2027-01-01T00:00:00+00:00",
            "memory_decision": "WRITE",
            "memory_content": "mode=future",
            "conflict_key": "mode",
            "valid_from": "2027-01-01T00:00:00+00:00",
        },
    ]
    future_report = scan(future_entries, "2026-09-05T00:00:00+00:00")
    future_map = {item["record_uid"]: item for item in future_report["decisions"]}
    if not (
        future_map.get("FUTURE-FACT", {}).get("action") == "REVIEW"
        and future_map["FUTURE-FACT"].get("reason") == "future_record_not_yet_active"
        and "CURRENT-FACT" not in future_map
        and not any(item["action"] == "SUPERSEDED" and item["deterministic"] for item in future_report["decisions"])
    ):
        failures.append("closeout_future_record_superseded_current")

    # Determinism: repeated scan byte-identical canonical JSON.
    rerun = scan(entries, as_of)
    if json.dumps(report, ensure_ascii=False, sort_keys=True).encode(
        "utf-8"
    ) != json.dumps(rerun, ensure_ascii=False, sort_keys=True).encode("utf-8"):
        failures.append("closeout_scan_nondeterministic")

    # Incremental affected-topic scoping (P3-8 interface): only the affected
    # topic is evaluated, deterministic count is minimal.
    incremental = scan(entries, as_of, affected_topics=["安装包校验规则"])
    incremental_uids = {
        str(item["record_uid"]) for item in incremental["decisions"]
    }
    if incremental_uids != {"CONFLICT-OLD"}:
        failures.append(
            f"closeout_incremental_affected_set_not_minimal:{sorted(incremental_uids)}"
        )
    if incremental["deterministic_count"] != 1:
        failures.append("closeout_incremental_rebuilt_unnecessary_records")

    # Apply: deterministic decisions go through the domain ledger with one Git
    # commit each (base: domain_ledger_api revision + git commit).
    with tempfile.TemporaryDirectory() as temp_dir:
        tmp = Path(temp_dir)
        _git_init(tmp)
        result = apply_decisions(
            report["decisions"],
            actor="check",
            authority="super",
            write_set=["memory"],
            root=tmp,
            idempotency_keys={"CONFLICT-OLD": "k1", "EXPIRED-REC": "k2"},
        )
        if not (result.get("ok") is True and result.get("applied") == 2):
            failures.append(f"closeout_apply_applied_count_invalid:{result.get('applied')}")
        receipts = result.get("receipts") or []
        ok_receipts = [r for r in receipts if r.get("ok")]
        if len(ok_receipts) != 2:
            failures.append("closeout_apply_receipt_count_invalid")
        for receipt in ok_receipts:
            record = receipt.get("record") or {}
            metadata = record.get("metadata") or {}
            if not record.get("git_commit"):
                failures.append("closeout_apply_git_commit_missing")
            for field in ("decision", "before", "after", "reason", "user_notice"):
                if not metadata.get(field):
                    failures.append(f"closeout_apply_metadata_{field}_missing")
        ledger_file = tmp / "domain-ledger" / "memory.json"
        if not ledger_file.exists():
            failures.append("closeout_apply_ledger_file_missing")
        else:
            ledger = json.loads(ledger_file.read_text(encoding="utf-8"))
            revisions = ledger.get("revisions") or []
            if len(revisions) != 2:
                failures.append(
                    f"closeout_apply_revision_count_invalid:{len(revisions)}"
                )
            projection = domain_ledger_read("memory", root=tmp)
            projected_by_revision = {
                item.get("revision"): item
                for item in projection.get("revisions", [])
                if isinstance(item, dict)
            }
            verified_commits: set[str] = set()
            for revision in revisions:
                receipt_ref = revision.get("git_receipt") if isinstance(revision, dict) else None
                projected = projected_by_revision.get(revision.get("revision")) if isinstance(revision, dict) else None
                if not isinstance(receipt_ref, dict) or not isinstance(projected, dict):
                    failures.append("closeout_apply_git_receipt_locator_missing")
                    continue
                receipt_path = receipt_ref.get("path")
                ledger_path = receipt_ref.get("ledger_path")
                transaction_id = receipt_ref.get("transaction_id")
                commit_sha = projected.get("git_commit")
                if not all(isinstance(value, str) and value for value in (receipt_path, ledger_path, transaction_id, commit_sha)):
                    failures.append("closeout_apply_git_receipt_locator_invalid")
                    continue
                try:
                    receipt = json.loads(_git_bytes(tmp, "show", f"{commit_sha}:{receipt_path}").decode("utf-8"))
                    committed_ledger_bytes = _git_bytes(tmp, "show", f"{commit_sha}:{ledger_path}")
                    committed_ledger = json.loads(committed_ledger_bytes.decode("utf-8"))
                    matching = [
                        item
                        for item in committed_ledger.get("revisions", [])
                        if isinstance(item, dict)
                        and isinstance(item.get("git_receipt"), dict)
                        and item["git_receipt"].get("transaction_id") == transaction_id
                        and item["git_receipt"].get("path") == receipt_path
                    ]
                    changed_paths = {
                        line.split("\t", 1)[1]: line.split("\t", 1)[0]
                        for line in _git_output(tmp, "diff-tree", "--root", "--no-commit-id", "-r", "--name-status", commit_sha).splitlines()
                        if "\t" in line
                    }
                except (OSError, UnicodeError, json.JSONDecodeError, subprocess.CalledProcessError):
                    failures.append("closeout_apply_git_receipt_blob_unreadable")
                    continue
                if not (
                    receipt.get("schema") == domain_ledger_api.GIT_RECEIPT_SCHEMA
                    and receipt.get("transaction_id") == transaction_id
                    and receipt.get("ledger_path") == ledger_path
                    and receipt.get("revision") == revision.get("revision")
                    and "ledger_sha256" not in receipt
                    and len(matching) == 1
                    and matching[0].get("revision") == revision.get("revision")
                    and matching[0].get("topic") == revision.get("topic")
                    and projected.get("transaction_id") == transaction_id
                    and projected.get("receipt_path") == receipt_path
                    and changed_paths.get(receipt_path) == "A"
                    and changed_paths.get(ledger_path) in {"A", "M"}
                ):
                    failures.append("closeout_apply_git_receipt_unverified")
                    continue
                verified_commits.add(commit_sha)
            if len(verified_commits) != 2:
                failures.append("closeout_apply_commits_not_one_per_write")

        # Idempotent apply with same idempotency keys: no duplicate revisions.
        result2 = apply_decisions(
            report["decisions"],
            actor="check",
            authority="super",
            write_set=["memory"],
            root=tmp,
            idempotency_keys={"CONFLICT-OLD": "k1", "EXPIRED-REC": "k2"},
        )
        ledger2 = json.loads(ledger_file.read_text(encoding="utf-8"))
        if not (result2.get("ok") is True and result2.get("applied") == 0 and len(ledger2.get("revisions") or []) == 2):
            failures.append("closeout_apply_not_idempotent")

        noop_result = apply_decisions(
            [
                {
                    "action": "REVIEW",
                    "deterministic": False,
                    "record_uid": "ADVISORY-NOOP",
                }
            ],
            actor="check",
            authority="super",
            write_set=["memory"],
            root=tmp,
        )
        if not (
            noop_result.get("ok") is True
            and noop_result.get("applied") == 0
            and noop_result.get("receipt_count") == 0
            and noop_result.get("failure_count") == 0
        ):
            failures.append("closeout_apply_noop_not_successful")

        # approval authority must refuse writes (no revision, no commit).
        approval_result = apply_decisions(
            report["decisions"],
            actor="check",
            authority="approval",
            write_set=["memory"],
            root=tmp,
        )
        approval_ok = [
            r for r in (approval_result.get("receipts") or []) if r.get("ok")
        ]
        if approval_ok or not (
            approval_result.get("ok") is False
            and approval_result.get("applied") == 0
            and approval_result.get("failure_count") == 2
        ):
            failures.append("closeout_apply_approval_not_refused")
        ledger3 = json.loads(ledger_file.read_text(encoding="utf-8"))
        if len(ledger3.get("revisions") or []) != 2:
            failures.append("closeout_apply_approval_mutated_ledger")

    with tempfile.TemporaryDirectory() as temp_dir:
        partial_root = Path(temp_dir)
        _git_init(partial_root)
        partial_decisions = [
            {
                "action": "DEGRADED",
                "deterministic": True,
                "record_uid": "PARTIAL-OK",
                "before": "WRITE",
                "after": "DEGRADED",
                "reason": "fixture",
                "user_notice": "fixture notice",
                "as_of": as_of,
                "superseded_by": None,
            },
            {
                "action": "DEGRADED",
                "deterministic": True,
                "record_uid": "PARTIAL-FAIL",
                "before": "WRITE",
                "after": "DEGRADED",
                "reason": "fixture",
                "user_notice": "fixture notice",
                "as_of": as_of,
                "superseded_by": None,
            },
        ]
        real_domain_write = domain_ledger_api.domain_ledger_write

        def partial_domain_write(**kwargs: object) -> dict[str, object]:
            if kwargs.get("topic") == "PARTIAL-FAIL":
                return {
                    "schema": "court.domain_ledger.v1",
                    "kind": "memory",
                    "ok": False,
                    "errors": [{"field": "git", "kind": "runtime", "code": "fixture_rejection"}],
                }
            return real_domain_write(**kwargs)

        with mock.patch.object(domain_ledger_api, "domain_ledger_write", side_effect=partial_domain_write):
            partial_result = apply_decisions(
                partial_decisions,
                actor="check",
                authority="super",
                write_set=["memory"],
                root=partial_root,
            )
        if not (
            partial_result.get("ok") is False
            and partial_result.get("applied") == 1
            and partial_result.get("receipt_count") == 2
            and partial_result.get("failure_count") == 1
        ):
            failures.append("closeout_apply_partial_failure_not_propagated")

    with tempfile.TemporaryDirectory() as temp_dir:
        cli_root = Path(temp_dir) / "ledger-root"
        cli_root.mkdir()
        _git_init(cli_root)
        cli_index = Path(temp_dir) / "entries.jsonl"
        cli_index.write_text(
            json.dumps(
                {
                    "record_uid": "CLI-DENIED",
                    "topic": "cli denial",
                    "time": "2026-08-01T00:00:00+00:00",
                    "memory_decision": "WRITE",
                    "memory_content": "expired fixture",
                    "valid_until": "2026-08-02T00:00:00+00:00",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        denied_cli = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts" / "closeout_conflict_scan.py"),
                "--index",
                str(cli_index),
                "--as-of",
                "2026-09-05T00:00:00+00:00",
                "--apply",
                "--yes",
                "--root",
                str(cli_root),
                "--authority",
                "approval",
                "--json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        try:
            denied_payload = json.loads(denied_cli.stdout)
        except json.JSONDecodeError:
            denied_payload = {}
        if not (
            denied_cli.returncode == 1
            and denied_payload.get("ok") is False
            and denied_payload.get("applied") == 0
            and denied_payload.get("failure_count") == 1
        ):
            failures.append("closeout_cli_apply_denial_not_nonzero")

    # CLI robustness: an invalid --as-of must fail cleanly (no bare traceback).
    invalid_cli = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts" / "closeout_conflict_scan.py"),
            "--as-of",
            "garbage",
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if invalid_cli.returncode != 2 or "CLOSEOUT_CONFLICT_SCAN_INVALID" not in (
        invalid_cli.stderr or ""
    ):
        failures.append("closeout_cli_invalid_as_of_not_fail_closed")
    cli_invalid_as_of_fail_closed = (
        invalid_cli.returncode == 2
        and "CLOSEOUT_CONFLICT_SCAN_INVALID" in (invalid_cli.stderr or "")
    )

    failures = list(dict.fromkeys(failures))
    return {
        "schema": "court.closeout_conflict_scan_check.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": "CLOSEOUT_CONFLICT_SCAN",
        "evidence": {
            "superseded_uids": sorted(superseded),
            "degraded_uids": sorted(degraded),
            "review_uids": sorted(review),
            "clean_uids": sorted(clean),
            "deterministic_count": report["deterministic_count"],
            "review_count": report["review_count"],
            "scan_deterministic": json.dumps(report, ensure_ascii=False, sort_keys=True)
            == json.dumps(rerun, ensure_ascii=False, sort_keys=True),
            "incremental_affected_set_minimal": incremental_uids == {"CONFLICT-OLD"},
            "apply_applied_count": result.get("applied") if "result" in dir() else None,
            "cli_invalid_as_of_fail_closed": cli_invalid_as_of_fail_closed,
        },
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
            "schema": "court.closeout_conflict_scan_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "CLOSEOUT_CONFLICT_SCAN",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        for stream in (sys.stdout,):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"CLOSEOUT_CONFLICT_SCAN={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
