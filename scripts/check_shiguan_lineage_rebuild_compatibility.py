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
from shiguan_entry_utils import content_lineage_display, enrich_entry


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
        rebuilt = parse_archive(archive_path)
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
            "fixture_kind": "synthetic_temp_archive",
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
