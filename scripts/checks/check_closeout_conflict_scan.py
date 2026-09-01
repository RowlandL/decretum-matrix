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

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from closeout_conflict_scan import apply_decisions, scan  # noqa: E402


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


def evaluate() -> dict[str, Any]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if fixture.get("schema") != "court.closeout_conflict_expiry_fixture.v1":
        raise ValueError("closeout_fixture_schema_invalid")
    entries = fixture["entries"]
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
            if len({r.get("git_commit") for r in revisions}) != 2:
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
        if len(ledger2.get("revisions") or []) != 2:
            failures.append("closeout_apply_not_idempotent")

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
        if approval_ok:
            failures.append("closeout_apply_approval_not_refused")
        ledger3 = json.loads(ledger_file.read_text(encoding="utf-8"))
        if len(ledger3.get("revisions") or []) != 2:
            failures.append("closeout_apply_approval_mutated_ledger")

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
