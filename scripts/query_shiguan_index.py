"""Query Shiguan checkpoint keywords and key behaviors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from shiguan_entry_utils import enrich_entry
from shiguan_paths import code_root, reference_path


def skill_root() -> Path:
    return code_root()


def index_path() -> Path:
    return reference_path("shiguan-index.jsonl")


def load_entries() -> list[dict[str, object]]:
    path = index_path()
    if not path.exists():
        return []

    entries: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            enrich_entry(value)
            entries.append(value)
    return entries


def score_entry(entry: dict[str, object], terms: list[str]) -> int:
    if not terms:
        return 0
    weighted_parts: list[tuple[int, str]] = []
    for key in (
        "topic",
        "phase",
        "status",
        "court_code",
        "ancient_lineage",
        "lineage_display",
        "lineage_key",
        "court_code_legend",
    ):
        value = entry.get(key)
        if isinstance(value, str):
            weighted_parts.append((4, value))
    lineage_parts = entry.get("lineage_parts")
    if isinstance(lineage_parts, dict):
        weighted_parts.extend((4, str(value)) for value in lineage_parts.values())
    facets = entry.get("facet_dimensions")
    if isinstance(facets, dict):
        for values in facets.values():
            if isinstance(values, list):
                weighted_parts.extend((4, str(value)) for value in values)
            else:
                weighted_parts.append((4, str(values)))
    parts = entry.get("court_code_parts")
    if isinstance(parts, dict):
        weighted_parts.extend((4, str(value)) for value in parts.values())
    for key in ("keywords", "key_actions"):
        value = entry.get(key)
        if isinstance(value, list):
            weighted_parts.extend((5, str(item)) for item in value)
    for key in ("capability_vector_terms", "capability_source_paths"):
        value = entry.get(key)
        if isinstance(value, list):
            weighted_parts.extend((6, str(item)) for item in value)
    capability_lineage = entry.get("capability_lineage")
    if isinstance(capability_lineage, dict):
        for value in capability_lineage.values():
            if isinstance(value, list):
                weighted_parts.extend((6, str(item)) for item in value)
            else:
                weighted_parts.append((6, str(value)))
    for key in ("capability_vector_text", "vector_text", "embedding_text", "capability_vector_hash", "capability_vector_kind"):
        value = entry.get(key)
        if isinstance(value, str):
            weighted_parts.append((5, value))
    for key in ("summary", "memory_content", "memory_reason", "display_labels_zh", "display_summary_zh", "display_reason_zh"):
        value = entry.get(key)
        if isinstance(value, str):
            weighted_parts.append((2, value))
    for key in ("keyword_summary_zh", "keyword_summary_en"):
        value = entry.get(key)
        if isinstance(value, str):
            weighted_parts.append((4, value))
    for key in ("keywords_zh", "keywords_en"):
        value = entry.get(key)
        if isinstance(value, list):
            weighted_parts.extend((5, str(item)) for item in value)
    for key in ("evidence", "next", "source"):
        value = entry.get(key)
        if isinstance(value, str):
            weighted_parts.append((1, value))
    score = 0
    for weight, value in weighted_parts:
        lowered = value.lower()
        score += sum(weight for term in terms if term.lower() in lowered)
    return score


def truncate(value: object, limit: int) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def compact_line(entry: dict[str, object], summary_chars: int) -> str:
    return " | ".join(
        [
            str(entry.get("time", "")),
            str(entry.get("court_code", "")),
            str(entry.get("lineage_display") or entry.get("ancient_lineage", "")),
            str(entry.get("topic", "")),
            str(entry.get("phase", "")),
            str(entry.get("status", "")),
            truncate(entry.get("keyword_summary_zh") or entry.get("summary", ""), summary_chars),
            truncate(entry.get("keyword_summary_en", ""), summary_chars),
            str(entry.get("source", "")),
        ]
    )


def print_detail(entry: dict[str, object], summary_chars: int) -> None:
    print(compact_line(entry, summary_chars))
    print(f"  lineage: {entry.get('lineage_display') or entry.get('ancient_lineage', '')}")
    print(f"  keywords: {', '.join(str(item) for item in entry.get('keywords', []))}")
    print(f"  keywords_zh: {', '.join(str(item) for item in entry.get('keywords_zh', []))}")
    print(f"  keywords_en: {', '.join(str(item) for item in entry.get('keywords_en', []))}")
    print(f"  关键词: {', '.join(str(item) for item in entry.get('display_keywords_zh') or entry.get('keywords_zh', []))}")
    print(f"  摘要: {entry.get('display_summary_zh') or entry.get('keyword_summary_zh') or truncate(entry.get('summary', ''), summary_chars)}")
    print(f"  理由: {truncate(entry.get('display_reason_zh') or entry.get('memory_reason') or entry.get('next', ''), summary_chars)}")
    print(f"  key_actions: {', '.join(str(item) for item in entry.get('key_actions', []))}")
    print(f"  capability_vector_terms: {', '.join(str(item) for item in entry.get('capability_vector_terms', []))}")
    print(f"  capability_source_paths: {', '.join(str(item) for item in entry.get('capability_source_paths', []))}")
    print(f"  capability_vector_hash: {entry.get('capability_vector_hash', '')}")
    print(f"  memory: {entry.get('memory_decision', '')} {truncate(entry.get('memory_content', ''), summary_chars)}")


def select_matches(entries: list[dict[str, object]], terms: list[str]) -> list[dict[str, object]]:
    if terms:
        scored = [
            (score_entry(entry, terms), entry)
            for entry in entries
        ]
        matches = [(score, entry) for score, entry in scored if score > 0]
        matches.sort(
            key=lambda item: (item[0], str(item[1].get("time", ""))),
            reverse=True,
        )
        return [entry for _, entry in matches]
    return sorted(entries, key=lambda entry: str(entry.get("time", "")), reverse=True)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("terms", nargs="*", help="Keywords or key actions to search.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--summary-chars", type=int, default=160)
    parser.add_argument("--format", choices=["compact", "detail", "json"], default="compact")
    args = parser.parse_args()

    entries = load_entries()
    if not entries:
        print(f"SHIGUAN_INDEX_EMPTY {index_path()}")
        return 1

    terms = [term for term in args.terms if term.strip()]
    matches = select_matches(entries, terms)[: max(args.limit, 1)]

    if args.format == "json":
        print(json.dumps(matches, ensure_ascii=False, indent=2))
        return 0

    for entry in matches:
        if args.format == "detail":
            print_detail(entry, args.summary_chars)
        else:
            print(compact_line(entry, args.summary_chars))

    return 0


if __name__ == "__main__":
    sys.exit(main())
