"""Verify stored Shiguan lineage survives enrichment and archive rebuild parsing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rebuild_shiguan_index import parse_archive
from archive_checkpoint import lineage_parts_archive_json
from shiguan_entry_utils import (
    content_lineage_display,
    content_lineage_parts,
    enrich_entry,
)


def evaluate() -> dict[str, Any]:
    stored_parts = {
        "root": "史馆总纪",
        "zhi": "旧志",
        "men": "旧门",
        "gang": "旧纲",
        "mu": "旧目",
        "tiao": "旧条",
        "zhao": "旧诏",
    }
    stored_display = content_lineage_display(stored_parts)
    stored_code = "SOLD-20260101-1-DSSS"
    direct_entry: dict[str, object] = {
        "record_type": "checkpoint",
        "topic": "agent",
        "phase": "Done",
        "status": "DONE",
        "summary": "agent",
        "evidence": "synthetic public fixture",
        "next": "none",
        "memory_decision": "SKIP",
        "memory_content": "none",
        "time": "2026-01-01T00:00:00+00:00",
        "source": "synthetic-fixture",
        "lineage_parts": dict(stored_parts),
        "lineage_display": stored_display,
        "ancient_lineage": stored_display,
        "court_code": stored_code,
    }
    enrich_entry(direct_entry)

    failures: list[str] = []
    if direct_entry.get("lineage_parts") != stored_parts:
        failures.append("stored_lineage_overwritten_on_enrich")

    with tempfile.TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "archive-20260101-lineage.md"
        archive_path.write_text(
            "\n".join(
                [
                    "# Archive: agent",
                    "",
                    "## Checkpoint: Done",
                    "- time: 2026-01-01T00:00:00+00:00",
                    "- status: DONE",
                    "- summary: agent",
                    "- evidence: synthetic public fixture",
                    "- next: none",
                    "- memory_decision: SKIP",
                    "- memory_content: none",
                    "- memory_reason: compatibility probe",
                    f"- court_code: {stored_code}",
                    f"- ancient_lineage: {stored_display}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        archive_sha_before = __import__("hashlib").sha256(
            archive_path.read_bytes()
        ).hexdigest()
        rebuilt = parse_archive(archive_path)
        classified_parts = content_lineage_parts(
            {
                "topic": "史馆实录索引与生长树",
                "summary": "史馆 archive index keyword",
            }
        )
        classified_display = content_lineage_display(classified_parts)
        classified_code = "SDMLTIU1-20260102-2-DSSS"
        classified_path = Path(temp_dir) / "archive-20260102-classified.md"
        classified_path.write_text(
            "\n".join(
                [
                    "# Archive: classified lineage",
                    "",
                    "## Checkpoint: Done",
                    "- time: 2026-01-02T00:00:00+00:00",
                    "- status: DONE",
                    "- summary: 史馆实录索引与生长树",
                    "- evidence: synthetic public fixture",
                    "- next: none",
                    "- memory_decision: SKIP",
                    "- memory_content: none",
                    "- memory_reason: classified compatibility probe",
                    f"- court_code: {classified_code}",
                    f"- ancient_lineage: {classified_display}",
                    "- lineage_parts_json: "
                    + lineage_parts_archive_json(
                        {"lineage_parts": classified_parts}
                    ),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        classified_sha_before = __import__("hashlib").sha256(
            classified_path.read_bytes()
        ).hexdigest()
        rebuilt_classified = parse_archive(classified_path)
        mismatch_path = Path(temp_dir) / "archive-20260103-mismatch.md"
        mismatch_path.write_text(
            "\n".join(
                [
                    "# Archive: mismatched lineage evidence",
                    "",
                    "## Checkpoint: Done",
                    "- time: 2026-01-03T00:00:00+00:00",
                    "- status: DONE",
                    "- summary: mismatch",
                    "- evidence: synthetic public fixture",
                    f"- ancient_lineage: {stored_display}",
                    "- lineage_parts_json: "
                    + lineage_parts_archive_json(
                        {"lineage_parts": classified_parts}
                    ),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        mismatch_sha_before = __import__("hashlib").sha256(
            mismatch_path.read_bytes()
        ).hexdigest()
        try:
            parse_archive(mismatch_path)
        except ValueError as exc:
            mismatch_rejected = str(exc) == "stored_lineage_evidence_mismatch"
        else:
            mismatch_rejected = False
        archive_sha_after = __import__("hashlib").sha256(
            archive_path.read_bytes()
        ).hexdigest()
        classified_sha_after = __import__("hashlib").sha256(
            classified_path.read_bytes()
        ).hexdigest()
        mismatch_sha_after = __import__("hashlib").sha256(
            mismatch_path.read_bytes()
        ).hexdigest()
    if len(rebuilt) != 1:
        raise ValueError(f"synthetic_archive_entry_count_invalid:{len(rebuilt)}")
    rebuilt_entry = rebuilt[0]
    rebuilt_display = str(
        rebuilt_entry.get("lineage_display") or rebuilt_entry.get("ancient_lineage") or ""
    )
    if rebuilt_display != stored_display:
        failures.append("archive_lineage_not_round_tripped")
        failures.append("rebuild_implicit_reclassification")
    if rebuilt_entry.get("court_code") == stored_code and rebuilt_display != stored_display:
        failures.append("court_code_lineage_mismatch")
    if len(rebuilt_classified) != 1:
        raise ValueError(
            f"classified_archive_entry_count_invalid:{len(rebuilt_classified)}"
        )
    classified_entry = rebuilt_classified[0]
    if classified_entry.get("lineage_parts") != classified_parts:
        failures.append("classified_lineage_metadata_not_round_tripped")
    if classified_entry.get("lineage_display") != classified_display:
        failures.append("classified_lineage_display_not_round_tripped")
    if classified_entry.get("court_code") != classified_code:
        failures.append("classified_court_code_not_round_tripped")
    if not mismatch_rejected:
        failures.append("conflicting_stored_lineage_not_rejected")
    roundtrip_zero_byte_unchanged = archive_sha_before == archive_sha_after
    classified_zero_byte_unchanged = classified_sha_before == classified_sha_after
    mismatch_zero_byte_unchanged = mismatch_sha_before == mismatch_sha_after
    if not roundtrip_zero_byte_unchanged:
        failures.append("rebuild_implicit_reclassification")
    if not mismatch_zero_byte_unchanged:
        failures.append("stored_lineage_evidence_mismatch")

    # Q1 / R-07: tidy maintenance path must not implicitly reclassify stored
    # lineage (negative gate, semantic domain rebuild_implicit_reclassification).
    import hashlib
    import re
    from tidy_shiguan_records import tidy_archive

    tidy_parts = content_lineage_parts(
        {
            "topic": "史馆实录索引与生长树",
            "summary": "史馆 archive index keyword",
        }
    )
    tidy_display = content_lineage_display(tidy_parts)
    tidy_code = "STIDY2601-20260101-3-DSSS"
    with tempfile.TemporaryDirectory() as tidy_temp_dir:
        tidy_path = Path(tidy_temp_dir) / "archive-20260101-tidy.md"
        tidy_path.write_text(
            "\n".join(
                [
                    "# Archive: tidy stored lineage",
                    "",
                    "## Checkpoint: Done",
                    "- time: 2026-01-01T00:00:00+00:00",
                    "- status: DONE",
                    "- summary: stored lineage round trip",
                    "- evidence: synthetic public fixture",
                    "- next: none",
                    "- memory_decision: SKIP",
                    "- memory_content: none",
                    "- memory_reason: tidy compatibility probe",
                    f"- court_code: {tidy_code}",
                    f"- ancient_lineage: {tidy_display}",
                    "- lineage_parts_json: "
                    + lineage_parts_archive_json(
                        {"lineage_parts": tidy_parts}
                    ),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        tidy_sha_before = hashlib.sha256(tidy_path.read_bytes()).hexdigest()
        rendered, _tidy_changes = tidy_archive(tidy_path)
        tidy_sha_after = hashlib.sha256(tidy_path.read_bytes()).hexdigest()
    tidy_zero_byte_unchanged = tidy_sha_before == tidy_sha_after
    if rendered is not None:
        from rebuild_shiguan_index import parse_fields

        rendered_fields = parse_fields(
            re.split(r"(?m)^## Checkpoint:\s*", rendered)[1].partition("\n")[2]
        )
        stored_lineage_rewrite = (
            rendered_fields.get("court_code", tidy_code) != tidy_code
            or rendered_fields.get("ancient_lineage", tidy_display) != tidy_display
            or rendered_fields.get(
                "lineage_parts_json",
                lineage_parts_archive_json({"lineage_parts": tidy_parts}),
            )
            != lineage_parts_archive_json({"lineage_parts": tidy_parts})
        )
        if stored_lineage_rewrite:
            failures.append("tidy_implicit_reclassification")

    # Q2 / R-08: normalization/classification products must not grant
    # execution authority; _task_frozen_lineage must fail closed with zero
    # mutation before the raise.
    from copy import deepcopy
    from court_runtime import _task_frozen_lineage

    normalization_execution_refused = True
    for probe_parts in (classified_parts, stored_parts):
        probe_task: dict[str, object] = {
            "lineage_parts": dict(probe_parts),
            "lineage_key": "normalized/classification/product",
            "lineage_display": content_lineage_display(probe_parts),
            "lineage_version": 2,
        }
        probe_snapshot = deepcopy(probe_task)
        try:
            _task_frozen_lineage(probe_task)
        except ValueError as exc:
            raised = str(exc) == "office_frozen_lineage_missing"
        else:
            raised = False
        if not raised or probe_task != probe_snapshot:
            normalization_execution_refused = False
    if not normalization_execution_refused:
        failures.append("normalization_granted_execution_authority")

    failures = list(dict.fromkeys(failures))
    return {
        "schema": "court.shiguan_lineage_rebuild_compatibility_check.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": "SHIGUAN_LINEAGE_REBUILD_COMPATIBILITY",
        "evidence": {
            "stored_lineage_parts": stored_parts,
            "direct_enriched_lineage_parts": direct_entry.get("lineage_parts"),
            "stored_lineage_display": stored_display,
            "rebuilt_lineage_display": rebuilt_display,
            "stored_court_code": stored_code,
            "rebuilt_court_code": rebuilt_entry.get("court_code"),
            "classified_lineage_parts": classified_parts,
            "rebuilt_classified_lineage_parts": classified_entry.get(
                "lineage_parts"
            ),
            "classified_lineage_display": classified_display,
            "rebuilt_classified_lineage_display": classified_entry.get(
                "lineage_display"
            ),
            "conflicting_stored_lineage_rejected": mismatch_rejected,
            "fixture_kind": "synthetic_temp_archive",
            "zero_byte_unchanged_roundtrip_archive": roundtrip_zero_byte_unchanged,
            "zero_byte_unchanged_classified_archive": classified_zero_byte_unchanged,
            "zero_byte_unchanged_mismatch_archive": mismatch_zero_byte_unchanged,
            "zero_byte_unchanged_tidy_fixture": tidy_zero_byte_unchanged,
            "tidy_implicit_reclassification_rejected": (
                "tidy_implicit_reclassification" not in failures
            ),
            "normalization_execution_authority_refused": normalization_execution_refused,
        },
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate()
    except (OSError, TypeError, ValueError) as exc:
        result = {
            "schema": "court.shiguan_lineage_rebuild_compatibility_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "SHIGUAN_LINEAGE_REBUILD_COMPATIBILITY",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"SHIGUAN_LINEAGE_REBUILD_COMPATIBILITY={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
