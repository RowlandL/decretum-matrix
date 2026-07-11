"""Select candidate capabilities from the local court capability index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

from shiguan_paths import reference_path


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def codex_home() -> Path:
    return Path.home() / ".codex"


def manifest_path() -> Path:
    return reference_path("installed-capabilities-manifest.json")


def catalog_path() -> Path:
    return reference_path("installed-capabilities-catalog.md")


def load_records() -> list[dict[str, object]]:
    path = manifest_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    records = data.get("capabilities") if isinstance(data, dict) else []
    return [record for record in records if isinstance(record, dict)]


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", text)]


def score_record(record: dict[str, object], terms: list[str]) -> int:
    haystack = " ".join(
        [
            str(record.get("name", "")),
            str(record.get("kind", "")),
            str(record.get("source", "")),
            str(record.get("description", "")),
            str(record.get("path", "")),
            " ".join(str(item) for item in record.get("court_units", []) or []),
            " ".join(str(item) for item in record.get("primary_fit", []) or []),
        ]
    ).lower()
    return sum(3 if term in str(record.get("name", "")).lower() else 1 for term in terms if term in haystack)


def prerequisite_status() -> dict[str, object]:
    home = codex_home()
    find_skills = home / "skills" / "find-skills" / "SKILL.md"
    skill_creator = home / "skills" / ".system" / "skill-creator" / "SKILL.md"
    quick_validate = home / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
    shiguan_index = catalog_path()
    shared_capability_index = reference_path("shiguan-tree", "capability-index", "_index.md")
    return {
        "find_skills": find_skills.exists(),
        "skill_creator": skill_creator.exists(),
        "quick_validate": quick_validate.exists(),
        "catalog": shiguan_index.exists(),
        "manifest_path": str(manifest_path()),
        "catalog_path": str(shiguan_index),
        "shared_shiguan_capability_index": shared_capability_index.exists(),
        "shared_shiguan_capability_index_path": str(shared_capability_index),
    }


def select_candidates(query: str, top: int) -> list[dict[str, object]]:
    terms = tokenize(query)
    records = load_records()
    ranked: list[tuple[int, dict[str, object]]] = []
    for record in records:
        score = score_record(record, terms)
        if score:
            ranked.append((score, record))
    ranked.sort(key=lambda item: (item[0], str(item[1].get("kind", "")), str(item[1].get("name", ""))), reverse=True)
    return [
        {
            "score": score,
            "kind": record.get("kind", ""),
            "name": record.get("name", ""),
            "source": record.get("source", ""),
            "court_units": record.get("court_units", []),
            "primary_fit": record.get("primary_fit", []),
            "relative_path": record.get("relative_path", ""),
            "description": record.get("description", ""),
        }
        for score, record in ranked[:top]
    ]


def evaluate(query: str, top: int) -> dict[str, object]:
    prereq = prerequisite_status()
    candidates = select_candidates(query, top)
    if not manifest_path().exists():
        gate = "FAILED"
    elif not all(bool(prereq[key]) for key in ("find_skills", "skill_creator", "quick_validate", "catalog")):
        gate = "PARTIAL"
    elif not candidates:
        gate = "PARTIAL"
    else:
        gate = "PASSED"
    return {
        "capability_index_skill_gate": gate,
        "query": query,
        "manifest": str(manifest_path()),
        "catalog": str(catalog_path()),
        "prerequisites": prereq,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "invocation_rule": "index_first_select_one_or_bounded_set; do_not_invoke_all_candidates",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = evaluate(args.query, max(1, args.top))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "CAPABILITY_INDEX_GATE "
            f"{result['capability_index_skill_gate']} "
            f"query={args.query!r} candidates={result['candidate_count']}"
        )
        for candidate in result["candidates"]:
            print(
                f"- {candidate['kind']}:{candidate['name']} "
                f"score={candidate['score']} units={candidate['court_units']} "
                f"path={candidate['relative_path']}"
            )
    return 0 if result["capability_index_skill_gate"] in {"PASSED", "PARTIAL"} else 2


if __name__ == "__main__":
    sys.exit(main())
