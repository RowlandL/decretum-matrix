"""Deep tidy Shiguan source records with backups and an audit report."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
from typing import Iterable

from rebuild_shiguan_index import (
    date_from_path,
    derive_keywords,
    parse_fields,
    stable_id,
    topic_from_text,
    unique,
)
from reevaluate_memory_decisions import recommend as recommend_memory_decision
from shiguan_entry_utils import enrich_entry
from shiguan_paths import code_root, ensure_shared_seed, resolve_source, references_root as shared_references_root, relative_to_data


ARCHIVE_FIELD_ORDER = [
    "time",
    "court_code",
    "ancient_lineage",
    "status",
    "summary",
    "evidence",
    "memory_decision",
    "risk_level",
    "knowledge_value",
    "priority_level",
    "memory_content",
    "memory_reason",
    "next",
]

MEMORY_FIELD_ORDER = [
    "time",
    "court_code",
    "ancient_lineage",
    "content",
    "reason",
    "risk_level",
    "knowledge_value",
    "priority_level",
]

DECISIONS = {"WRITE", "PROPOSE", "SKIP", "DEFERRED"}
FIELD_RE = re.compile(r"^- ([a-zA-Z_]+):\s*(.*)$")
SENSITIVE_RE = re.compile(
    r"(?i)("
    r"api[_ -]?key\s*[:=]\s*[^\s;，；]+|"
    r"secret\s*[:=]\s*[^\s;，；]+|"
    r"password\s*[:=]\s*[^\s;，；]+|"
    r"passwd\s*[:=]\s*[^\s;，；]+|"
    r"cookie\s*[:=]\s*[^\s;，；]+|"
    r"authorization\s*[:=]\s*[^\s;，；]+|"
    r"bearer\s+[a-z0-9._~+/=-]{16,}|"
    r"private[_ -]?key\s*[:=]\s*[^\s;，；]+|"
    r"access[_ -]?token\s*[:=]\s*[^\s;，；]+|"
    r"refresh[_ -]?token\s*[:=]\s*[^\s;，；]+|"
    r"私密二维码\s*[:=：]\s*\S+|"
    r"二维码密钥\s*[:=：]\s*\S+|"
    r"微信\s*id\s*[:=：]\s*\S+|"
    r"wechat\s*id\s*[:=]\s*\S+"
    r")"
)


def skill_root() -> Path:
    return code_root()


def references_root() -> Path:
    ensure_shared_seed()
    return shared_references_root()


def default_report_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return references_root() / "shiguan-tidy-reports" / f"tidy-shiguan-{stamp}.json"


def default_backup_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return references_root() / "shiguan-backups" / f"tidy-{stamp}"


def as_line(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def source_path(source: str) -> Path:
    return resolve_source(source)


def topic_for_source(path: Path, text: str) -> str:
    return topic_from_text(path, text)


def archive_entry(path: Path, topic: str, phase: str, fields: dict[str, str]) -> dict[str, object]:
    memory_decision = (fields.get("memory_decision") or "DEFERRED").upper()
    next_action = fields.get("next", "")
    entry: dict[str, object] = {
        "record_type": "checkpoint",
        "court_code": "",
        "topic": topic,
        "phase": phase,
        "status": fields.get("status", "UNKNOWN"),
        "time": fields.get("time") or date_from_path(path),
        "keywords": derive_keywords(
            topic,
            phase,
            fields.get("status", "UNKNOWN"),
            fields.get("summary", ""),
            fields.get("evidence", ""),
            fields.get("memory_content", "none"),
        ),
        "key_actions": unique(
            [
                f"phase:{phase}",
                f"status:{fields.get('status', 'UNKNOWN')}",
                f"memory:{memory_decision}",
                f"next:{next_action}",
            ],
            16,
        ),
        "summary": fields.get("summary", ""),
        "evidence": fields.get("evidence", ""),
        "next": next_action,
        "memory_decision": memory_decision,
        "risk_level": fields.get("risk_level", ""),
        "knowledge_value": fields.get("knowledge_value", ""),
        "priority_level": fields.get("priority_level", ""),
        "memory_content": fields.get("memory_content", "none"),
        "memory_reason": fields.get("memory_reason", ""),
        "source": relative_to_data(path),
    }
    enrich_entry(entry)
    entry["id"] = stable_id(entry)
    return entry


def memory_entry(path: Path, topic: str, decision: str, fields: dict[str, str]) -> dict[str, object]:
    decision = (decision or "DEFERRED").upper()
    entry: dict[str, object] = {
        "record_type": "memory_decision",
        "court_code": "",
        "topic": topic,
        "phase": "记忆裁定",
        "status": decision,
        "time": fields.get("time") or date_from_path(path),
        "keywords": derive_keywords(topic, decision, fields.get("content", ""), fields.get("reason", "")),
        "key_actions": unique(
            [
                "phase:记忆裁定",
                f"memory:{decision}",
                "source:memory_decision.py",
            ],
            16,
        ),
        "summary": fields.get("content", ""),
        "evidence": "memory_decision.py",
        "next": "await Menxia seal or memory interface when needed",
        "memory_decision": decision,
        "risk_level": fields.get("risk_level", ""),
        "knowledge_value": fields.get("knowledge_value", ""),
        "priority_level": fields.get("priority_level", ""),
        "memory_content": fields.get("content", ""),
        "memory_reason": fields.get("reason", ""),
        "source": relative_to_data(path),
    }
    enrich_entry(entry)
    entry["id"] = stable_id(entry)
    return entry


def has_sensitive_memory(entry: dict[str, object]) -> bool:
    text = "\n".join(
        str(entry.get(key) or "")
        for key in ("memory_content", "memory_reason", "summary", "evidence", "next")
    )
    return bool(SENSITIVE_RE.search(text))


def memory_recommendation(entry: dict[str, object]) -> tuple[str, str]:
    current = str(entry.get("memory_decision") or "DEFERRED").upper()
    proposed, reason = recommend_memory_decision(entry)
    if has_sensitive_memory(entry):
        if current in {"WRITE", "PROPOSE"}:
            return "SKIP", "含敏感凭据/私密标识线索，不得写入长期记忆。"
        return current if current in DECISIONS else "DEFERRED", "含敏感凭据/私密标识线索，保留非写入裁定。"
    if proposed == "WRITE" and not as_line(entry.get("memory_reason")):
        return "WRITE", reason or "深整理重判：长期规则或偏好具备写入价值。"
    return proposed if proposed in DECISIONS else "DEFERRED", reason


FALSE_SENSITIVE_REASON = "深整理重判：含敏感凭据/私密标识线索，不得写入长期记忆。"


def clean_false_sensitive_reason(value: str) -> str:
    text = as_line(value)
    for token in (
        f"；{FALSE_SENSITIVE_REASON}",
        FALSE_SENSITIVE_REASON,
    ):
        text = text.replace(token, "")
    return text.strip("；; ")


def merged_reason(
    original: str,
    proposed: str,
    reason: str,
    changed: bool,
    *,
    clear_false_sensitive: bool = False,
) -> str:
    original = as_line(original)
    if clear_false_sensitive:
        original = clean_false_sensitive_reason(original)
    reason = as_line(reason)
    if proposed == "WRITE" and not original:
        return reason or "深整理重判：长期规则或偏好具备写入价值。"
    if changed and reason and reason not in original:
        return f"{original}；深整理重判：{reason}" if original else f"深整理重判：{reason}"
    return original


def desired_archive_fields(entry: dict[str, object], current_fields: dict[str, str]) -> dict[str, str]:
    proposed_decision, decision_reason = memory_recommendation(entry)
    current_decision = (current_fields.get("memory_decision") or "DEFERRED").upper()
    changed = proposed_decision != current_decision
    clear_false_sensitive = not has_sensitive_memory(entry)
    return {
        "court_code": as_line(entry.get("court_code")),
        "ancient_lineage": as_line(entry.get("ancient_lineage") or entry.get("lineage_display")),
        "memory_decision": proposed_decision,
        "risk_level": as_line(entry.get("risk_level")),
        "knowledge_value": as_line(entry.get("knowledge_value")),
        "priority_level": as_line(entry.get("priority_level")),
        "memory_reason": merged_reason(
            current_fields.get("memory_reason", ""),
            proposed_decision,
            decision_reason,
            changed,
            clear_false_sensitive=clear_false_sensitive,
        ),
    }


def desired_memory_fields(entry: dict[str, object], current_fields: dict[str, str]) -> dict[str, str]:
    proposed_decision, decision_reason = memory_recommendation(entry)
    current_decision = str(entry.get("memory_decision") or "DEFERRED").upper()
    changed = proposed_decision != current_decision
    clear_false_sensitive = not has_sensitive_memory(entry)
    return {
        "court_code": as_line(entry.get("court_code")),
        "ancient_lineage": as_line(entry.get("ancient_lineage") or entry.get("lineage_display")),
        "reason": merged_reason(
            current_fields.get("reason", ""),
            proposed_decision,
            decision_reason,
            changed,
            clear_false_sensitive=clear_false_sensitive,
        ),
        "risk_level": as_line(entry.get("risk_level")),
        "knowledge_value": as_line(entry.get("knowledge_value")),
        "priority_level": as_line(entry.get("priority_level")),
    }


def skip_continuation(lines: list[str], start: int) -> int:
    index = start + 1
    while index < len(lines) and lines[index].startswith("  "):
        index += 1
    return index


def set_markdown_fields(block: str, updates: dict[str, str], order: list[str]) -> str:
    lines = block.splitlines()
    output: list[str] = []
    present: set[str] = set()
    index = 0
    while index < len(lines):
        line = lines[index]
        match = FIELD_RE.match(line)
        if match and match.group(1) in updates:
            key = match.group(1)
            output.append(f"- {key}: {updates[key]}")
            present.add(key)
            index = skip_continuation(lines, index)
            continue
        output.append(line)
        index += 1

    missing = [key for key in order if key in updates and key not in present]
    if missing:
        if output and output[-1].strip():
            output.append("")
        for key in missing:
            output.append(f"- {key}: {updates[key]}")
    return "\n".join(output).rstrip() + "\n"


def field_changes(current: dict[str, str], desired: dict[str, str]) -> dict[str, dict[str, str]]:
    changes: dict[str, dict[str, str]] = {}
    for key, new in desired.items():
        old = as_line(current.get(key, ""))
        if old != new:
            changes[key] = {"old": old, "new": new}
    return changes


def summarize_change(
    *,
    source: str,
    record_type: str,
    topic: str,
    phase: str,
    entry: dict[str, object],
    current_fields: dict[str, str],
    desired: dict[str, str],
) -> dict[str, object] | None:
    changes = field_changes(current_fields, desired)
    proposed_decision, decision_reason = memory_recommendation(entry)
    current_decision = str(entry.get("memory_decision") or "DEFERRED").upper()
    lineage_old = current_fields.get("ancient_lineage", "")
    lineage_new = str(entry.get("ancient_lineage") or entry.get("lineage_display") or "")
    if lineage_old != lineage_new and "ancient_lineage" not in changes:
        changes["ancient_lineage"] = {"old": lineage_old, "new": lineage_new}
    if not changes:
        return None
    return {
        "source": source,
        "record_type": record_type,
        "topic": topic,
        "phase": phase,
        "court_code": entry.get("court_code"),
        "current_decision": current_decision,
        "recommended_decision": proposed_decision,
        "decision_reason_zh": decision_reason,
        "lineage_old": lineage_old,
        "lineage_new": lineage_new,
        "risk_level": entry.get("risk_level"),
        "knowledge_value": entry.get("knowledge_value"),
        "priority_level": entry.get("priority_level"),
        "changed_fields": sorted(changes),
        "changes": changes,
    }


def split_archive(text: str) -> tuple[str, list[tuple[str, str]]]:
    chunks = re.split(r"(?m)^## Checkpoint:\s*", text)
    head = chunks[0]
    blocks: list[tuple[str, str]] = []
    for chunk in chunks[1:]:
        first, _, rest = chunk.partition("\n")
        blocks.append((first.strip(), rest))
    return head, blocks


def render_archive(head: str, blocks: list[tuple[str, str]]) -> str:
    text = head.rstrip() + "\n\n"
    for phase, rest in blocks:
        text += f"## Checkpoint: {phase}\n{rest.rstrip()}\n\n"
    return text


def tidy_archive(path: Path) -> tuple[str | None, list[dict[str, object]]]:
    original = read_text(path)
    topic = topic_for_source(path, original)
    head, blocks = split_archive(original)
    if not blocks:
        return None, []
    new_blocks: list[tuple[str, str]] = []
    changes: list[dict[str, object]] = []
    for phase, rest in blocks:
        fields = parse_fields(rest)
        entry = archive_entry(path, topic, phase, fields)
        desired = desired_archive_fields(entry, fields)
        summary = summarize_change(
            source=relative_to_data(path),
            record_type="checkpoint",
            topic=topic,
            phase=phase,
            entry=entry,
            current_fields=fields,
            desired=desired,
        )
        if summary:
            changes.append(summary)
        new_blocks.append((phase, set_markdown_fields(rest, desired, ARCHIVE_FIELD_ORDER)))
    rendered = render_archive(head, new_blocks)
    return (rendered if rendered != original else None), changes


def split_memory(text: str) -> tuple[str, list[tuple[str, str]]]:
    chunks = re.split(r"(?m)^## Memory Decision:\s*", text)
    head = chunks[0]
    blocks: list[tuple[str, str]] = []
    for chunk in chunks[1:]:
        first, _, rest = chunk.partition("\n")
        blocks.append((first.strip().upper(), rest))
    return head, blocks


def render_memory(head: str, blocks: list[tuple[str, str]]) -> str:
    text = head.rstrip() + "\n\n"
    for decision, rest in blocks:
        text += f"## Memory Decision: {decision}\n{rest.rstrip()}\n\n"
    return text


def tidy_memory(path: Path) -> tuple[str | None, list[dict[str, object]]]:
    if path.name == "README.md":
        return None, []
    original = read_text(path)
    topic = topic_for_source(path, original)
    head, blocks = split_memory(original)
    if not blocks:
        return None, []
    new_blocks: list[tuple[str, str]] = []
    changes: list[dict[str, object]] = []
    for decision, rest in blocks:
        fields = parse_fields(rest)
        entry = memory_entry(path, topic, decision, fields)
        proposed_decision, _ = memory_recommendation(entry)
        desired = desired_memory_fields(entry, fields)
        current_fields = dict(fields)
        current_fields["memory_decision"] = decision
        desired_for_report = dict(desired)
        desired_for_report["memory_decision"] = proposed_decision
        summary = summarize_change(
            source=relative_to_data(path),
            record_type="memory_decision",
            topic=topic,
            phase="记忆裁定",
            entry=entry,
            current_fields=current_fields,
            desired=desired_for_report,
        )
        if summary:
            changes.append(summary)
        new_blocks.append((proposed_decision, set_markdown_fields(rest, desired, MEMORY_FIELD_ORDER)))
    rendered = render_memory(head, new_blocks)
    return (rendered if rendered != original else None), changes


def iter_sources() -> Iterable[Path]:
    refs = references_root()
    yield from sorted((refs / "plan-archives").glob("*.md"))
    yield from sorted((refs / "memory-decisions").glob("*.md"))


def backup_sources(backup_dir: Path) -> None:
    refs = references_root()
    if backup_dir.exists():
        raise FileExistsError(f"backup directory already exists: {backup_dir}")
    backup_dir.mkdir(parents=True)
    for name in (
        "plan-archives",
        "memory-decisions",
        "shiguan-tree",
    ):
        source = refs / name
        if source.exists():
            shutil.copytree(source, backup_dir / name)
    for name in ("shiguan-index.jsonl", "shiguan-knowledge-graph.json"):
        source = refs / name
        if source.exists():
            shutil.copy2(source, backup_dir / name)


def build_report(changes: list[dict[str, object]], writes: dict[Path, str], backup_dir: Path | None) -> dict[str, object]:
    decision_changes = Counter(
        (
            str(change.get("current_decision")),
            str(change.get("recommended_decision")),
        )
        for change in changes
        if change.get("current_decision") != change.get("recommended_decision")
    )
    field_counts = Counter(field for change in changes for field in change.get("changed_fields", []))
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "apply" if backup_dir else "dry-run",
        "source_files_scanned": len(list(iter_sources())),
        "source_files_to_write": len(writes),
        "changed_records": len(changes),
        "backup_dir": str(backup_dir) if backup_dir else "",
        "decision_changes": [
            {"from": old, "to": new, "count": count}
            for (old, new), count in sorted(decision_changes.items())
        ],
        "field_change_counts": dict(sorted(field_counts.items())),
        "sample_changes": changes[:20],
        "changes": changes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--report", type=Path, default=default_report_path())
    args = parser.parse_args()

    writes: dict[Path, str] = {}
    changes: list[dict[str, object]] = []
    for path in iter_sources():
        if "plan-archives" in path.parts:
            rendered, path_changes = tidy_archive(path)
        else:
            rendered, path_changes = tidy_memory(path)
        if rendered is not None:
            writes[path] = rendered
        changes.extend(path_changes)

    backup_dir = args.backup_dir or default_backup_dir()
    report = build_report(changes, writes, backup_dir if args.apply else None)
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    backup_sources(backup_dir)
    for path, rendered in writes.items():
        write_text(path, rendered)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_text(args.report, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(
        f"SHIGUAN_TIDY_APPLIED report={args.report} backup={backup_dir} "
        f"files={len(writes)} records={len(changes)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
