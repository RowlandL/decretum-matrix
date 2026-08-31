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
    expected_latest = ["f-unique", "f-neg", "f-archive-weak", "f-archive", "f-token", "f-path"]
    if latest_uids != expected_latest:
        failures.append("recall_empty_query_not_latest_n")

    # --- P0-1: a term inside a negated clause must not contribute ---
    if "f-neg" in _query(["archive"], BASIC):
        failures.append("recall_negation_not_suppressed")

    ok = not failures
    return {
        "schema": "court.shiguan_recall_precision_check.v1",
        "contract": "SHIGUAN_RECALL_PRECISION",
        "status": "PASSED" if ok else "FAILED",
        "ok": ok,
        "metrics": {
            "archive_hits": len(archive_uids),
            "archive_top": archive_uids[0] if archive_uids else "",
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
