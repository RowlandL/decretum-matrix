"""Check IKU repair read-only dry-run, --yes gate, idempotency, rollback and
receipt pointers (FR-A A2 / P3-4 / P3-5) against isolated temp directories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any
from unittest.mock import patch

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from iku_candidates import detect_candidates, placeholder_kind  # noqa: E402
import archive_checkpoint
from repair_archive_placeholders import (  # noqa: E402
    apply_repairs,
    plan_repairs,
    rollback,
)


RECORD = """# Archive: probe

## Checkpoint: Done
- time: 2026-01-01T00:00:00+00:00
- status: DONE
- summary: IKU repair probe
- record_id: TP-20260101-0001
- court_code: SDMLTIUW7-20260101-1-ABAA
- ancient_lineage: 史馆总纪/中书省委/尚书省丞/典创专部/应用部/考据条
- receipt: archive_checkpoint 2026-01-01T09:00:00Z

诏令编号：［IKU］ 待 archive_checkpoint 生成
古制谱系：占位符由 archive_checkpoint 自动回填
"""


def evaluate() -> dict[str, Any]:
    failures: list[str] = []
    evidence: dict[str, Any] = {}

    # A normal alphanumeric substring is not a placeholder. The old repeated
    # review lineage code is a separate, review-only identity candidate.
    false_positive = placeholder_kind(
        "- court_code: SAIKUB-20260101-1-ABAA"
    )
    if false_positive is not None:
        failures.append("iku_literal_matched_court_code_substring")
    evidence["iku_literal_court_code_false_positive_rejected"] = (
        false_positive is None
    )
    if placeholder_kind("- court_code: SUIKUIKUIKUIKUIKULD-20260101-1-ABAA") != "LEGACY_REVIEW_CODE":
        failures.append("legacy_review_code_not_detected")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        archive = temp / "plan-archives"
        archive.mkdir(parents=True)
        record_path = archive / "probe-20260101-iku.md"
        with patch.object(archive_checkpoint, "relative_to_data", return_value=record_path.relative_to(archive.parent.parent).as_posix()):
            receipt = archive_checkpoint.build_archive_receipt(record_path, {
                "court_code": "SDMLTIUW7-20260101-1-ABAA",
                "lineage_display": "史馆总纪/中书省委/尚书省丞/典创专部/应用部/考据条",
                "time": "2026-01-01T00:00:00+00:00",
            }, {})
        fixture = RECORD.replace("- receipt: archive_checkpoint 2026-01-01T09:00:00Z", "- archive_receipt_json: " + json.dumps(receipt, ensure_ascii=False))
        record_path.write_text(fixture, encoding="utf-8", newline="\n")
        original_bytes = record_path.read_bytes()

        # Dry-run: plan exists, zero byte mutation.
        plan = plan_repairs(root=archive)
        after_dry_bytes = record_path.read_bytes()
        if after_dry_bytes != original_bytes:
            failures.append("dry_run_mutated_file")
        evidence["dry_run_zero_byte_unchanged"] = after_dry_bytes == original_bytes
        if len(plan) < 2:
            failures.append("repair_plan_missing_identity_candidates")
        evidence["repair_plan_candidate_count"] = len(plan)
        if any(
            item.get("field") not in {"诏令编号", "古制谱系"}
            for item in plan
        ):
            failures.append("repair_plan_touched_non_identity_field")
        if any(not item.get("receipt_hint") for item in plan):
            failures.append("repair_plan_missing_receipt_pointer")
        evidence["repair_plan_has_receipt_pointers"] = all(
            item.get("receipt_hint") for item in plan
        )

        # --yes gate: apply without confirmation must refuse and mutate nothing.
        refused = False
        try:
            apply_repairs(plan, root=archive, backup_root=temp / "backups", yes=False)
        except ValueError as exc:
            refused = str(exc) == "repair_requires_yes"
        if not refused:
            failures.append("apply_without_yes_not_refused")
        after_refuse_bytes = record_path.read_bytes()
        if after_refuse_bytes != original_bytes:
            failures.append("refused_apply_mutated_file")
        evidence["apply_requires_yes_gate"] = refused and (
            after_refuse_bytes == original_bytes
        )

        # Apply with --yes: backup + journal/receipt written, file repaired.
        backup_root = temp / "backups"
        result = apply_repairs(
            plan, root=archive, backup_root=backup_root, yes=True
        )
        if not (result.get("ok") is True and result.get("files") == 1):
            failures.append("apply_result_invalid")
        repaired_bytes = record_path.read_bytes()
        if repaired_bytes == original_bytes:
            failures.append("apply_did_not_repair")
        backup_files = list(backup_root.glob("*.bak"))
        if not backup_files:
            failures.append("rollback_snapshot_missing")
        journal_files = list(backup_root.glob("repair-journal-*.json"))
        if not journal_files:
            failures.append("repair_journal_missing")
        journal = (
            json.loads(journal_files[0].read_text(encoding="utf-8"))
            if journal_files
            else {}
        )
        journal_entries = journal.get("files") or []
        if len(journal_entries) != 1:
            failures.append("repair_journal_entry_count_invalid")
        entry = journal_entries[0] if journal_entries else {}
        if entry.get("original_size_bytes") != len(original_bytes) or entry.get("beforeimage_verification") != "exact_bytes":
            failures.append("repair_journal_beforeimage_verification_missing")
        if not backup_files or backup_files[0].read_bytes() != original_bytes:
            failures.append("repair_backup_beforeimage_mismatch")
        if not entry.get("backup_path") or not entry.get("receipt_hint"):
            failures.append("repair_journal_receipt_or_snapshot_pointer_missing")
        if not entry.get("nearest_court_code") or not entry.get("nearest_lineage"):
            failures.append("repair_verbatim_source_missing")
        if entry.get("replacements"):
            if not all(
                isinstance(item.get("fragment_reference"), dict)
                and isinstance(item.get("line_coordinate"), dict)
                and item["line_coordinate"].get("record_ref")
                and item["line_coordinate"].get("checkpoint_ref")
                and item["line_coordinate"].get("line_number")
                for item in entry["replacements"]
            ):
                failures.append("repair_journal_structured_reference_missing")
        evidence["repair_journal_receipt_and_snapshot"] = (
            entry.get("original_size_bytes") == len(original_bytes)
            and entry.get("beforeimage_verification") == "exact_bytes"
            and bool(entry.get("backup_path"))
            and bool(entry.get("receipt_hint"))
            and bool(entry.get("nearest_court_code"))
            and bool(entry.get("nearest_lineage"))
        )

        # Idempotency: repaired text carries verbatim receipt identity and a
        # second dry-run finds no new REPAIR_CANDIDATE.
        repaired_text = record_path.read_text(encoding="utf-8")
        if "诏令编号：SDMLTIUW7-20260101-1-ABAA" not in repaired_text:
            failures.append("repaired_court_code_not_verbatim_receipt")
        if "古制谱系：史馆总纪/中书省委/尚书省丞/典创专部/应用部/考据条" not in repaired_text:
            failures.append("repaired_lineage_not_verbatim_receipt")
        second_plan = plan_repairs(root=archive)
        if second_plan:
            failures.append("repair_not_idempotent")
        candidates_after = detect_candidates(root=archive)
        if any(
            item.get("suggested_action") == "REPAIR_CANDIDATE"
            for item in candidates_after
        ):
            failures.append("repair_candidate_remains_after_apply")
        evidence["apply_idempotent"] = not second_plan and not any(
            item.get("suggested_action") == "REPAIR_CANDIDATE"
            for item in candidates_after
        )

        # Rollback: restore original bytes from snapshot.
        if backup_files:
            rollback(backup_files[0], record_path)
            rolled_back_bytes = record_path.read_bytes()
            if rolled_back_bytes != original_bytes:
                failures.append("rollback_did_not_restore_original")
            evidence["rollback_restores_original"] = (
                rolled_back_bytes == original_bytes
            )
        else:
            evidence["rollback_restores_original"] = False

    failures = list(dict.fromkeys(failures))
    return {
        "schema": "court.iku_repair_check.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": "IKU_REPAIR",
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
            "schema": "court.iku_repair_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "IKU_REPAIR",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        for stream in (sys.stdout,):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"IKU_REPAIR={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
