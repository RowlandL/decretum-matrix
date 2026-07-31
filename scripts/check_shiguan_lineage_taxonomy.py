"""Check Shiguan taxonomy confidence, tie, negation, and unknown behavior."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import shiguan_entry_utils as lineage


FIXTURE = ROOT / "references" / "fixtures" / "shiguan-lineage-taxonomy-golden.json"
REVIEW_VALUES = {"review", "pending_review", "unknown", "待审"}
CLASSIFIED_VALUES = {"classified", "matched"}


def _is_review(parts: dict[str, object]) -> bool:
    for key in ("classification_status", "review_status", "status"):
        if str(parts.get(key) or "").strip().casefold() in REVIEW_VALUES:
            return True
    return any("待审" in str(value) for value in parts.values())


def _classification_metadata_problems(
    parts: dict[str, object],
    expected: dict[str, object],
) -> list[str]:
    problems: list[str] = []
    status = str(parts.get("classification_status") or "").strip().casefold()
    reason = str(parts.get("classification_reason") or "").strip().casefold()
    confidence = parts.get("classification_confidence")
    score = parts.get("classification_score")
    margin = parts.get("classification_margin")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        problems.append("confidence_missing")
    elif not 0.0 <= float(confidence) <= 1.0:
        problems.append("confidence_out_of_range")
    if isinstance(score, bool) or not isinstance(score, int) or score < 0:
        problems.append("score_invalid")
    if isinstance(margin, bool) or not isinstance(margin, int) or margin < 0:
        problems.append("margin_invalid")

    expected_status = str(expected.get("status") or "").casefold()
    expected_reason = str(expected.get("reason") or "").casefold()
    if expected_status == "review":
        if status not in REVIEW_VALUES or reason != expected_reason:
            problems.append("review_reason_mismatch")
        if any(
            parts.get(field) != "待审"
            for field in ("zhi", "men", "gang", "mu", "tiao")
        ):
            problems.append("review_placeholder_missing")
        if reason == "low_confidence" and not (
            isinstance(score, int)
            and 0 < score < lineage.CONTENT_TAXONOMY_MIN_SCORE
        ):
            problems.append("low_confidence_score_invalid")
        if reason == "tie" and margin != 0:
            problems.append("tie_margin_invalid")
        if reason == "negated_evidence":
            count = parts.get("classification_negated_evidence_count")
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                problems.append("negated_evidence_missing")
        if reason == "unknown" and score != 0:
            problems.append("unknown_score_invalid")
    elif expected_status == "classified":
        if status not in CLASSIFIED_VALUES or reason != "matched":
            problems.append("classified_metadata_invalid")
        if not isinstance(score, int) or score < 2:
            problems.append("classified_score_too_low")
        if not isinstance(margin, int) or margin < 1:
            problems.append("classified_margin_too_low")
    return problems


def evaluate() -> dict[str, Any]:
    corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if not isinstance(corpus, dict) or corpus.get("schema") != "court.shiguan_lineage_taxonomy_golden.v1":
        raise ValueError("golden_fixture_schema_invalid")
    cases = corpus.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("golden_fixture_cases_required")

    failures: list[str] = []
    results: list[dict[str, object]] = []
    golden_version = str(corpus.get("taxonomy_version") or "")
    actual_versions: list[object] = []

    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("entry"), dict):
            raise ValueError("golden_fixture_case_invalid")
        expected = case.get("expected")
        if not isinstance(expected, dict):
            raise ValueError("golden_fixture_expected_invalid")
        parts = lineage.content_lineage_parts(dict(case["entry"]))
        actual_version = parts.get("taxonomy_version")
        actual_versions.append(actual_version)
        if not actual_version or str(actual_version) != golden_version:
            failures.append("lineage_golden_corpus_unversioned")
        case_ok = True
        if expected.get("status") == "review":
            case_ok = _is_review(parts)
        elif expected.get("status") == "classified":
            expected_parts = expected.get("parts")
            if not isinstance(expected_parts, dict):
                raise ValueError("golden_fixture_expected_parts_invalid")
            case_ok = all(parts.get(key) == value for key, value in expected_parts.items())
        else:
            raise ValueError("golden_fixture_expected_status_invalid")
        metadata_problems = _classification_metadata_problems(parts, expected)
        case_ok = case_ok and not metadata_problems
        if not case_ok:
            failures.append(str(case.get("failure_code") or f"lineage_case_failed:{case.get('id')}"))
        results.append(
            {
                "id": case.get("id"),
                "ok": case_ok,
                "expected": expected,
                "actual_taxonomy_version": actual_version,
                "metadata_problems": metadata_problems,
                "actual": parts,
            }
        )

    failures = list(dict.fromkeys(failures))
    unique_actual_versions: list[object] = []
    for value in actual_versions:
        if value not in unique_actual_versions:
            unique_actual_versions.append(value)
    return {
        "schema": "court.shiguan_lineage_taxonomy_check.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": "SHIGUAN_LINEAGE_TAXONOMY",
        "golden_taxonomy_version": golden_version,
        "actual_taxonomy_versions": unique_actual_versions,
        "results": results,
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
            "schema": "court.shiguan_lineage_taxonomy_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "SHIGUAN_LINEAGE_TAXONOMY",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"SHIGUAN_LINEAGE_TAXONOMY={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
