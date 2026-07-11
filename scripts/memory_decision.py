"""Record a /court memory decision when Codex /memories is unavailable."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

from court_file_lock import atomic_write_text, file_lock, shiguan_write_lock_path
from shiguan_entry_utils import enrich_entry
from shiguan_paths import code_root, ensure_shared_seed, reference_path, relative_to_data


VALID_DECISIONS = {"WRITE", "PROPOSE", "SKIP", "DEFERRED"}
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.\\/-]{2,}|[\u4e00-\u9fff]{2,}")
NOISE_TERMS = {
    "and",
    "the",
    "with",
    "for",
    "this",
    "that",
    "none",
    "memory",
    "decision",
}


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = value.strip("-")
    return value[:48] or "memory"


def skill_root() -> Path:
    return code_root()


def memory_dir() -> Path:
    ensure_shared_seed()
    return reference_path("memory-decisions")


def memory_path(topic: str, date_text: str) -> Path:
    return memory_dir() / f"memory-{date_text}-{slugify(topic)}-1.md"


def index_path() -> Path:
    ensure_shared_seed()
    return reference_path("shiguan-index.jsonl")


def split_terms(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[,;，；\n]+", value)
    return [part.strip() for part in parts if part.strip()]


def unique(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
        if len(output) >= limit:
            break
    return output


def derive_keywords(args: argparse.Namespace, decision: str) -> list[str]:
    manual = split_terms(args.keywords)
    text = "\n".join([args.topic, decision, args.content, args.reason])
    automatic = [
        token.strip("`'\".,:()[]{}<>")
        for token in TOKEN_RE.findall(text)
        if token.lower() not in NOISE_TERMS
    ]
    return unique(manual + automatic, 32)


def derive_key_actions(args: argparse.Namespace, decision: str) -> list[str]:
    manual = split_terms(args.key_actions)
    automatic = [
        "phase:记忆裁定",
        f"memory:{decision}",
        "source:memory_decision.py",
    ]
    return unique(manual + automatic, 16)


def append_index_entry(args: argparse.Namespace, now: datetime, path: Path, decision: str) -> Path:
    index = index_path()
    index.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "time": now.isoformat(timespec="seconds"),
        "record_type": "memory_decision",
        "topic": args.topic,
        "phase": "记忆裁定",
        "status": decision,
        "keywords": derive_keywords(args, decision),
        "key_actions": derive_key_actions(args, decision),
        "summary": args.content,
        "evidence": "memory_decision.py",
        "next": "await Menxia seal or memory interface when needed",
        "memory_decision": decision,
        "memory_content": args.content,
        "memory_reason": args.reason,
        "source": relative_to_data(path),
    }
    enrich_entry(entry)
    with index.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return index


def grow_tree_best_effort() -> None:
    try:
        from grow_shiguan_tree import grow_tree

        grow_tree()
    except Exception as exc:  # pragma: no cover - memory write must not fail on tree refresh.
        print(f"SHIGUAN_TREE_REFRESH_WARNING {exc}", file=sys.stderr)


def append_decision(args: argparse.Namespace) -> Path:
    decision = args.decision.upper()
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {', '.join(sorted(VALID_DECISIONS))}")

    with file_lock(shiguan_write_lock_path(), timeout=float(getattr(args, "lock_timeout", 30.0))):
        ensure_shared_seed()
        now = datetime.now()
        date_text = now.strftime("%Y%m%d")
        path = memory_path(args.topic, date_text)
        path.parent.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            atomic_write_text(
                path,
                "\n".join(
                    [
                        f"# Court Memory Decisions: {args.topic}",
                        "",
                        f"- created_at: {now.isoformat(timespec='seconds')}",
                        f"- topic: {args.topic}",
                        "",
                    ]
                ),
            )

        block = "\n".join(
            [
                f"## Memory Decision: {decision}",
                "",
                f"- time: {now.isoformat(timespec='seconds')}",
                f"- content: {args.content}",
                f"- reason: {args.reason}",
                "",
            ]
        )
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(block)
            handle.flush()
            os.fsync(handle.fileno())
        append_index_entry(args, now, path, decision)
    grow_tree_best_effort()
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--decision", required=True)
    parser.add_argument("--content", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--keywords", help="Comma/semicolon separated Shiguan recall keywords.")
    parser.add_argument("--key-actions", help="Comma/semicolon separated key behaviors for future court recall.")
    parser.add_argument("--lock-timeout", type=float, default=30.0)
    args = parser.parse_args()

    try:
        path = append_decision(args)
    except PermissionError as exc:
        print(f"MEMORY_PERMISSION_REQUIRED {exc}", file=sys.stderr)
        print("Request approval/escalation, then rerun the same memory command.", file=sys.stderr)
        return 13
    except TimeoutError as exc:
        print(f"MEMORY_LOCK_TIMEOUT {exc}", file=sys.stderr)
        return 12
    except ValueError as exc:
        print(f"MEMORY_INVALID {exc}", file=sys.stderr)
        return 2

    print(f"MEMORY_DECISION_OK {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
