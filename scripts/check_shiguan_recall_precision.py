"""Check Shiguan recall precision: field pollution, negation, threshold, token exactness.

Regression gate for the P0 recall hardening (beta1.0.8):
- P0-3 low-value provenance fields (source/evidence/next/capability_source_paths/
  court_code_legend) never drive selection.
- P0-1 negation-aware matching: a term inside a negated clause contributes no score.
- P0-2 tokenized TF-IDF with a minimum score and a positive top-1 margin.
- Empty query keeps "latest N" semantics (time descending).
- GBrain and fallback query paths stay a single scorer (parity).

The fixture corpora are inline and deterministic; the real Shiguan index is never
read, so this gate is hermetic and CI-safe.
"""

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

import shiguan_entry_utils as recall
import query_shiguan_index as query


BASIC = [
    {
        "record_uid": "f-path",
        "time": "2026-08-01T00:00:00",
        "topic": "capability registry refresh",
        "keywords": ["registry"],
        "summary": "registry refresh only",
        "source": "references/plan-archives/plan-20260801-registry.md",
    },
    {
        "record_uid": "f-token",
        "time": "2026-08-01T01:00:00",
        "topic": "plan-archives rollup",
        "keywords": ["rollup"],
        "summary": "merge plan-archives rollup",
    },
    {
        "record_uid": "f-archive",
        "time": "2026-08-02T00:00:00",
        "topic": "shiguan archive checkpoint",
        "keywords": ["archive", "checkpoint"],
        "summary": "create shiguan archive checkpoint",
    },
    {
        "record_uid": "f-archive-weak",
        "time": "2026-08-02T01:00:00",
        "topic": "checkpoint sync",
        "keywords": ["archive"],
        "summary": "sync checkpoint files",
    },
    {
        "record_uid": "f-neg",
        "time": "2026-08-04T00:00:00",
        "topic": "memory cleanup",
        "keywords": ["memory"],
        "summary": "本次不涉及 archive 清理，仅处理 memory 保留",
    },
    {
        "record_uid": "f-unique",
        "time": "2026-08-05T00:00:00",
        "topic": "hologram projection",
        "keywords": ["hologram"],
        "summary": "hologram projection experiment",
    },
    {
        "record_uid": "f-affirm",
        "time": "2026-08-06T00:00:00",
        "topic": "memory audit",
        "keywords": ["archive"],
        "summary": "涉及 archive 评估",
    },
    {
        "record_uid": "f-uncertain",
        "time": "2026-08-06T01:00:00",
        "topic": "memory audit",
        "keywords": ["archive"],
        "summary": "可能涉及 archive 评估",
    },
    {
        "record_uid": "f-hypo",
        "time": "2026-08-06T02:00:00",
        "topic": "memory audit",
        "keywords": ["archive"],
        "summary": "如果要做 archive 迁移，先评估",
    },
    {
        "record_uid": "f-rejected",
        "time": "2026-08-06T03:00:00",
        "topic": "port cleanup",
        "keywords": ["port"],
        "summary": "port cleanup attempted",
        "status": "REJECTED",
    },
    {
        "record_uid": "f-blocked",
        "time": "2026-08-06T04:00:00",
        "topic": "deploy sync",
        "keywords": ["deploy"],
        "summary": "deploy sync paused",
        "status": "BLOCKED",
    },
]

COMMON = [
    {
        "record_uid": f"f-common-{index}",
        "time": f"2026-08-{index:02d}T00:00:00",
        "topic": f"史馆记录检查{index}",
        "keywords": ["史馆"],
    }
    for index in range(1, 9)
]


def _uids(entries: list[dict[str, Any]]) -> list[str]:
    return [str(entry.get("record_uid") or "") for entry in entries]


def _query(terms: list[str], corpus: list[dict[str, Any]], mode: str = "fallback") -> list[str]:
    return _uids(query.select_query_matches([dict(entry) for entry in corpus], terms, mode=mode))


def evaluate() -> dict[str, Any]:
    failures: list[str] = []

    # --- P0-3: provenance-field pollution must not drive selection ---
    archive_uids = _query(["archive"], BASIC)
    if "f-path" in archive_uids:
        failures.append("recall_source_path_pollution")
    if not archive_uids or archive_uids[0] != "f-archive":
        failures.append("recall_archive_top_missing")

    # --- Empty query: latest-N (time descending) ---
    latest_uids = _query([], BASIC)
    expected_latest = [
        "f-blocked",
        "f-rejected",
        "f-hypo",
        "f-uncertain",
        "f-affirm",
        "f-unique",
        "f-neg",
        "f-archive-weak",
        "f-archive",
        "f-token",
        "f-path",
    ]
    if latest_uids != expected_latest:
        failures.append("recall_empty_query_not_latest_n")

    # --- P0-1: a term inside a negated clause must not contribute ---
    if "f-neg" in _query(["archive"], BASIC):
        failures.append("recall_negation_not_suppressed")

    # --- P0-2: ASCII tokens match exactly, never inside a longer path token ---
    if "f-token" in _query(["archive"], BASIC):
        failures.append("recall_path_token_substring")

    # --- P0-2: a term present in every document is non-discriminative and
    # falls back to latest-N (time descending) instead of fake text ranking ---
    common_uids = _query(["史馆"], COMMON)
    expected_common = [f"f-common-{index}" for index in range(8, 0, -1)]
    if common_uids != expected_common:
        failures.append("recall_common_term_not_latest_n")

    # --- P0-2: unique terms still surface and top-1 keeps a positive margin ---
    unique_uids = _query(["hologram"], BASIC)
    if not unique_uids or unique_uids[0] != "f-unique":
        failures.append("recall_unique_term_missing")
    idf = recall.recall_idf([dict(entry) for entry in BASIC], ["archive"])
    archive_scores = [
        recall.score_entry_recall(entry, ["archive"], idf=idf) for entry in BASIC
    ]
    ranked = sorted((score for score in archive_scores if score > 0.0), reverse=True)
    if len(ranked) < 2 or ranked[0] - ranked[1] <= 0.0:
        failures.append("recall_top_margin_not_positive")

    # --- GBrain / fallback parity: a single scorer ---
    if _query(["archive"], BASIC, mode="gbrain") != archive_uids:
        failures.append("recall_gbrain_fallback_diverged")

    # --- A+D: assertion weights order affirmed > uncertain > hypothetical,
    # and a negated clause is a soft penalty (negative score), not exclusion ---
    idf_archive = recall.recall_idf([dict(entry) for entry in BASIC], ["archive"])
    scores_archive = {
        str(entry.get("record_uid")): recall.score_entry_recall(entry, ["archive"], idf=idf_archive)
        for entry in BASIC
    }
    if not (
        scores_archive.get("f-affirm", 0.0)
        > scores_archive.get("f-uncertain", 0.0)
        > scores_archive.get("f-hypo", 0.0)
    ):
        failures.append("recall_assertion_weight_order")
    if scores_archive.get("f-neg", 0.0) >= 0.0:
        failures.append("recall_negation_not_soft_penalty")
    if "f-neg" in archive_uids:
        failures.append("recall_negation_still_surfaced")

    # --- B (guard): status is never a hard exclusion ---
    if "f-rejected" not in _query(["port"], BASIC):
        failures.append("recall_status_hard_excluded")

    # --- B: status semantics are a queryable relevance facet ---
    if "f-rejected" not in _query(["失败"], BASIC):
        failures.append("recall_status_facet_failure_query")
    if "f-blocked" not in _query(["打断"], BASIC):
        failures.append("recall_status_facet_blocked_query")
    rejected_rank = _query(["失败"], BASIC).index("f-rejected") if "f-rejected" in _query(["失败"], BASIC) else -1
    if rejected_rank > 0:
        failures.append("recall_status_facet_not_top")

    ok = not failures
    return {
        "schema": "court.shiguan_recall_precision_check.v1",
        "contract": "SHIGUAN_RECALL_PRECISION",
        "status": "PASSED" if ok else "FAILED",
        "ok": ok,
        "metrics": {
            "archive_hits": len(archive_uids),
            "archive_top": archive_uids[0] if archive_uids else "",
            "common_hits": len(common_uids),
            "unique_top": unique_uids[0] if unique_uids else "",
            "empty_query_count": len(latest_uids),
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
            "schema": "court.shiguan_recall_precision_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "SHIGUAN_RECALL_PRECISION",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"SHIGUAN_RECALL_PRECISION={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
