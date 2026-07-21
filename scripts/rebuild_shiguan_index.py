"""Rebuild Shiguan recall index from all existing archives and memory decisions."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import zlib

sys.dont_write_bytecode = True

from court_file_lock import atomic_write_text, file_lock, shiguan_write_lock_path
from shiguan_entry_utils import base36, enrich_entry
from shiguan_paths import code_root, ensure_shared_seed, references_root as shared_references_root, relative_to_data


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.\\/-]{2,}|[\u4e00-\u9fff]{2,}")
FIELD_RE = re.compile(r"^- ([a-zA-Z_]+):\s*(.*)$")
NOISE_TERMS = {
    "and",
    "the",
    "with",
    "for",
    "this",
    "that",
    "none",
    "court",
    "checkpoint",
    "memory",
    "decision",
}


def skill_root() -> Path:
    return code_root()


def references_root() -> Path:
    return shared_references_root()


def index_path() -> Path:
    ensure_shared_seed()
    return references_root() / "shiguan-index.jsonl"


def write_index_if_changed(path: Path, text: str) -> bool:
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    atomic_write_text(path, text)
    return True


def unique(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        value = value.strip()
        if not value:
            continue
        key = value.lower()
        if key in seen or key in NOISE_TERMS:
            continue
        seen.add(key)
        output.append(value)
        if len(output) >= limit:
            break
    return output


def derive_keywords(*values: str) -> list[str]:
    text = "\n".join(value for value in values if value)
    tokens = [
        token.strip("`'\".,:()[]{}<>")
        for token in TOKEN_RE.findall(text)
        if token.lower() not in NOISE_TERMS
    ]
    return unique(tokens, 32)


def stable_id(entry: dict[str, object]) -> str:
    material = "|".join(
        str(entry.get(key, ""))
        for key in ("record_type", "source", "time", "topic", "phase", "status", "summary")
    )
    return f"{zlib.crc32(material.encode('utf-8')):08x}"


def relative(path: Path) -> str:
    return relative_to_data(path)


def parse_fields(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key: str | None = None
    for line in block.splitlines():
        match = FIELD_RE.match(line)
        if match:
            current_key = match.group(1)
            fields[current_key] = match.group(2).strip()
            continue
        if current_key and line.startswith("  "):
            fields[current_key] += "\n" + line.strip()
    return fields


def topic_from_text(path: Path, text: str) -> str:
    for pattern in (r"^- topic:\s*(.+)$", r"^# .*?:\s*(.+)$"):
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match:
            return match.group(1).strip()
    stem = path.stem
    stem = re.sub(r"^(plan|memory)-\d{8}-", "", stem)
    stem = re.sub(r"-\d+$", "", stem)
    return stem


def date_from_path(path: Path) -> str:
    match = re.search(r"(\d{8})", path.name)
    if match:
        return match.group(1)
    return datetime.now().strftime("%Y%m%d")


def parse_archive(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    topic = topic_from_text(path, text)
    source = relative(path)
    chunks = re.split(r"(?m)^## Checkpoint:\s*", text)
    entries: list[dict[str, object]] = []
    for chunk in chunks[1:]:
        first_line, _, rest = chunk.partition("\n")
        phase = first_line.strip() or "checkpoint"
        fields = parse_fields(rest)
        time = fields.get("time") or date_from_path(path)
        status = fields.get("status", "UNKNOWN")
        summary = fields.get("summary", "")
        evidence = fields.get("evidence", "")
        memory_decision = fields.get("memory_decision", "DEFERRED")
        memory_content = fields.get("memory_content", "none")
        memory_reason = fields.get("memory_reason", "")
        next_action = fields.get("next", "")
        entry: dict[str, object] = {
            "record_type": "checkpoint",
            "court_code": fields.get("court_code", ""),
            "topic": topic,
            "phase": phase,
            "status": status,
            "time": time,
            "keywords": derive_keywords(topic, phase, status, summary, evidence, memory_content),
            "key_actions": unique(
                [
                    f"phase:{phase}",
                    f"status:{status}",
                    f"memory:{memory_decision}",
                    f"next:{next_action}",
                ],
                16,
            ),
            "summary": summary,
            "evidence": evidence,
            "next": next_action,
            "memory_decision": memory_decision,
            "risk_level": fields.get("risk_level", ""),
            "knowledge_value": fields.get("knowledge_value", ""),
            "priority_level": fields.get("priority_level", ""),
            "memory_content": memory_content,
            "memory_reason": memory_reason,
            "source": source,
        }
        enrich_entry(entry)
        entry["id"] = stable_id(entry)
        entries.append(entry)
    return entries


def parse_memory(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    topic = topic_from_text(path, text)
    source = relative(path)
    chunks = re.split(r"(?m)^## Memory Decision:\s*", text)
    entries: list[dict[str, object]] = []
    for chunk in chunks[1:]:
        first_line, _, rest = chunk.partition("\n")
        decision = first_line.strip().upper() or "DEFERRED"
        fields = parse_fields(rest)
        time = fields.get("time") or date_from_path(path)
        content = fields.get("content", "")
        reason = fields.get("reason", "")
        entry: dict[str, object] = {
            "record_type": "memory_decision",
            "court_code": fields.get("court_code", ""),
            "topic": topic,
            "phase": "记忆裁定",
            "status": decision,
            "time": time,
            "keywords": derive_keywords(topic, decision, content, reason),
            "key_actions": unique(
                [
                    "phase:记忆裁定",
                    f"memory:{decision}",
                    "source:memory_decision.py",
                ],
                16,
            ),
            "summary": content,
            "evidence": "memory_decision.py",
            "next": "await Menxia seal or memory interface when needed",
            "memory_decision": decision,
            "risk_level": fields.get("risk_level", ""),
            "knowledge_value": fields.get("knowledge_value", ""),
            "priority_level": fields.get("priority_level", ""),
            "memory_content": content,
            "memory_reason": reason,
            "source": source,
        }
        enrich_entry(entry)
        entry["id"] = stable_id(entry)
        entries.append(entry)
    return entries


def normalize_manual(entry: dict[str, object], path: Path) -> dict[str, object] | None:
    if not isinstance(entry, dict):
        return None
    normalized: dict[str, object] = {
        "record_type": str(entry.get("record_type") or "manual_note"),
        "court_code": str(entry.get("court_code") or ""),
        "topic": str(entry.get("topic") or "manual"),
        "phase": str(entry.get("phase") or "手动修订"),
        "status": str(entry.get("status") or "DRAFT"),
        "time": str(entry.get("time") or date_from_path(path)),
        "keywords": entry.get("keywords") if isinstance(entry.get("keywords"), list) else [],
        "key_actions": entry.get("key_actions") if isinstance(entry.get("key_actions"), list) else [],
        "summary": str(entry.get("summary") or ""),
        "evidence": str(entry.get("evidence") or "local shiguan web"),
        "next": str(entry.get("next") or ""),
        "memory_decision": str(entry.get("memory_decision") or "DEFERRED"),
        "risk_level": str(entry.get("risk_level") or ""),
        "knowledge_value": str(entry.get("knowledge_value") or ""),
        "priority_level": str(entry.get("priority_level") or ""),
        "memory_content": str(entry.get("memory_content") or ""),
        "memory_reason": str(entry.get("memory_reason") or ""),
        "source": relative(path),
    }
    if entry.get("origin_source"):
        normalized["origin_source"] = str(entry.get("origin_source"))
    if not normalized["keywords"]:
        normalized["keywords"] = derive_keywords(
            str(normalized["topic"]),
            str(normalized["phase"]),
            str(normalized["status"]),
            str(normalized["summary"]),
            str(normalized["evidence"]),
            str(normalized["memory_content"]),
        )
    if not normalized["key_actions"]:
        normalized["key_actions"] = unique(
            [
                f"phase:{normalized['phase']}",
                f"status:{normalized['status']}",
                f"memory:{normalized['memory_decision']}",
            ],
            16,
        )
    normalized["id"] = str(entry.get("id") or stable_id(normalized))
    enrich_entry(normalized)
    return normalized


def parse_manual(path: Path) -> list[dict[str, object]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return []
    if isinstance(value, list):
        entries = [normalize_manual(item, path) for item in value if isinstance(item, dict)]
        return [entry for entry in entries if entry is not None]
    if isinstance(value, dict):
        entry = normalize_manual(value, path)
        return [entry] if entry is not None else []
    return []


def rebuild_index() -> tuple[int, Path]:
    with file_lock(shiguan_write_lock_path()):
        ensure_shared_seed()
        refs = references_root()
        entries: list[dict[str, object]] = []
        for path in sorted((refs / "plan-archives").glob("*.md")):
            entries.extend(parse_archive(path))
        for path in sorted((refs / "memory-decisions").glob("*.md")):
            entries.extend(parse_memory(path))
        for path in sorted((refs / "shiguan-tree" / "manual").glob("*.json")):
            entries.extend(parse_manual(path))

        deduped: dict[str, dict[str, object]] = {}
        for entry in entries:
            deduped[str(entry["id"])] = entry
        ordered = sorted(
            deduped.values(),
            key=lambda entry: (str(entry.get("time", "")), str(entry.get("source", ""))),
        )
        per_day: dict[str, int] = {}
        for entry in ordered:
            day_match = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", str(entry.get("time") or ""))
            day = "".join(day_match.groups()) if day_match else date_from_path(Path(str(entry.get("source") or "")))
            per_day[day] = per_day.get(day, 0) + 1
            entry["daily_sequence"] = base36(per_day[day])
            enrich_entry(entry)

        index = index_path()
        index.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(
            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
            for entry in ordered
        )
        write_index_if_changed(index, text)

    try:
        from grow_shiguan_tree import grow_tree

        grow_tree()
    except Exception as exc:  # pragma: no cover - report but keep rebuilt index.
        print(f"SHIGUAN_TREE_REFRESH_WARNING {exc}", file=sys.stderr)

    try:
        from build_shiguan_knowledge_graph import build_and_write

        build_and_write()
    except Exception as exc:  # pragma: no cover - report but keep rebuilt index.
        print(f"SHIGUAN_KG_REFRESH_WARNING {exc}", file=sys.stderr)

    return len(ordered), index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    count, path = rebuild_index()
    if not args.quiet:
        print(f"SHIGUAN_INDEX_REBUILT {path} entries={count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
