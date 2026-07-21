"""Query Shiguan checkpoint keywords and key behaviors."""

from __future__ import annotations

import argparse
import json
import sys

sys.dont_write_bytecode = True

from shiguan_entry_utils import index_path, load_entries, score_entry, select_matches as fallback_select_matches


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
    print(f"  memory: {entry.get('memory_decision', '')} {truncate(entry.get('memory_content', ''), summary_chars)}")


def select_query_matches(
    entries: list[dict[str, object]],
    terms: list[str],
    *,
    mode: str = "gbrain",
) -> list[dict[str, object]]:
    """Select query matches through GBrain, with the Shiguan base query as fallback."""

    if mode not in {"gbrain", "fallback"}:
        raise ValueError("query_mode_invalid")
    if mode == "gbrain":
        try:
            from shiguan_gbrain import select_matches as gbrain_select_matches
        except (ImportError, OSError, RuntimeError, ValueError):
            pass
        else:
            return gbrain_select_matches(entries, terms)
    return fallback_select_matches(entries, terms)


select_matches = select_query_matches


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("terms", nargs="*", help="Keywords or key actions to search.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--summary-chars", type=int, default=160)
    parser.add_argument("--format", choices=["compact", "detail", "json"], default="compact")
    parser.add_argument(
        "--query-mode",
        choices=["gbrain", "fallback"],
        default="gbrain",
        help="Use GBrain as the Shiguan query layer by default; fallback keeps the base Shiguan scorer.",
    )
    args = parser.parse_args()

    entries = load_entries()
    if not entries:
        print(f"SHIGUAN_INDEX_EMPTY {index_path()}")
        return 1

    terms = [term for term in args.terms if term.strip()]
    matches = select_query_matches(entries, terms, mode=args.query_mode)[: max(args.limit, 1)]

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
