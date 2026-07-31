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


def _is_review(parts: dict[str, object]) -> bool:
    for key in ("classification_status", "review_status", "status"):
        if str(parts.get(key) or "").strip().casefold() in REVIEW_VALUES:
            return True
    return any("待审" in str(value) for value in parts.values())


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
        if not case_ok:
            failures.append(str(case.get("failure_code") or f"lineage_case_failed:{case.get('id')}"))
        results.append(
            {
                "id": case.get("id"),
                "ok": case_ok,
                "expected": expected,
                "actual_taxonomy_version": actual_version,
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
