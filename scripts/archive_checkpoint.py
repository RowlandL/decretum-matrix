"""Append a court-mode checkpoint to the Shiguan record."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

from court_file_lock import atomic_write_text, file_lock, shiguan_write_lock_path
from shiguan_entry_utils import base36, enrich_entry, existing_content_lineage_parts
from shiguan_paths import (
    code_root,
    detect_runtime_agent,
    ensure_shared_seed,
    reference_path,
    references_root,
    relative_to_data,
    source_agent_choices,
)


TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\\/-]{2,}|[\u4e00-\u9fff]{2,}")
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
}
ARCHIVE_RECEIPT_SCHEMA = "court.shiguan_archive_checkpoint_receipt.v1"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = value.strip("-")
    return value[:48] or "court"


def skill_root() -> Path:
    return code_root()


def archive_dir() -> Path:
    return reference_path("plan-archives")


def index_path() -> Path:
    return reference_path("shiguan-index.jsonl")


def refresh_request_path() -> Path:
    return reference_path("obsidian-sync", "refresh-request.json")


def archive_path(topic: str, date_text: str) -> Path:
    return archive_dir() / f"plan-{date_text}-{slugify(topic)}-1.md"


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


def derive_keywords(args: argparse.Namespace, memory_decision: str, memory_content: str) -> list[str]:
    manual = split_terms(args.keywords)
    text = "\n".join(
        [
            args.topic,
            args.phase,
            args.status,
            args.summary,
            args.evidence,
            args.next,
            memory_decision,
            memory_content,
        ]
    )
    automatic = [
        token.strip("`'\".,:()[]{}<>")
        for token in TOKEN_RE.findall(text)
        if token.lower() not in NOISE_TERMS
    ]
    return unique(manual + automatic, 32)


def derive_key_actions(args: argparse.Namespace, memory_decision: str) -> list[str]:
    manual = split_terms(args.key_actions)
    automatic = [
        f"phase:{args.phase}",
        f"status:{args.status}",
        f"memory:{memory_decision}",
        f"next:{args.next}",
    ]
    return unique(manual + automatic, 16)


def detect_source_agent(args: argparse.Namespace) -> dict[str, str]:
    return detect_runtime_agent(args.source_agent)


def read_full_record(args: argparse.Namespace) -> str:
    if args.full_record and args.full_record_file:
        raise ValueError("Use either --full-record or --full-record-file, not both.")
    if args.full_record_file:
        return Path(args.full_record_file).read_text(encoding="utf-8", errors="replace").strip()
    return (args.full_record or "").strip()


def normalize_generated_identity_fields(text: str, entry: dict[str, object]) -> str:
    """Canonicalize generated identity fields in full_record by label, not wording.

    The root problem was treating placeholder text as the contract. The contract
    is the field label: any full_record line beginning with `诏令编号：`,
    `古制谱系：`, or `作业AI：` must be rewritten from this checkpoint's
    generated entry.
    """
    if not text:
        return text
    court_code = str(entry.get("court_code") or "").strip()
    lineage = str(entry.get("lineage_display") or entry.get("ancient_lineage") or "").strip()
    source_agent_label = str(entry.get("source_agent_label") or entry.get("source_agent") or "").strip()
    output: list[str] = []
    has_code = False
    has_lineage = False
    has_source_agent = False
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        newline = line[len(stripped):]
        if stripped.startswith("诏令编号：") and court_code:
            output.append(f"诏令编号：{court_code}{newline}")
            has_code = True
            continue
        if stripped.startswith("古制谱系：") and lineage:
            output.append(f"古制谱系：{lineage}{newline}")
            has_lineage = True
            continue
        if stripped.startswith("作业AI：") and source_agent_label:
            if not has_source_agent:
                output.append(f"作业AI：{source_agent_label}{newline}")
                has_source_agent = True
            continue
        if stripped.startswith("状态："):
            output.append(line)
            if source_agent_label and not has_source_agent:
                output.append(f"作业AI：{source_agent_label}{newline}")
                has_source_agent = True
            continue
        output.append(line)
    prefix: list[str] = []
    if court_code and not has_code:
        prefix.append(f"诏令编号：{court_code}\n")
    if lineage and not has_lineage:
        prefix.append(f"古制谱系：{lineage}\n")
    if source_agent_label and not has_source_agent:
        prefix.append(f"作业AI：{source_agent_label}\n")
    if prefix:
        if output and output[0].strip():
            prefix.append("\n")
        output = prefix + output
    return "".join(output)


def scrub_raw_placeholder_mentions(text: str) -> str:
    for raw in ("待 archive_checkpoint 生成", "占位符由 archive_checkpoint 自动回填"):
        text = text.replace(raw, "archive_checkpoint 生成前占位符")
    return text


def fill_generated_placeholders(text: str, entry: dict[str, object]) -> str:
    """Normalize generated fields and scrub legacy placeholder prose."""
    return scrub_raw_placeholder_mentions(normalize_generated_identity_fields(text, entry))


def next_daily_sequence(index: Path, date_text: str) -> str:
    if not index.exists():
        return "1"
    count = 0
    highest = 0
    for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(entry.get("time", "")).replace("-", "").startswith(date_text):
            count += 1
            raw_sequence = str(entry.get("daily_sequence") or "").strip()
            if not raw_sequence:
                code = str(entry.get("court_code") or "")
                pieces = code.rsplit("-", 2)
                raw_sequence = pieces[1] if len(pieces) == 3 else ""
            if re.fullmatch(r"[0-9A-Z]+", raw_sequence.upper()):
                highest = max(highest, int(raw_sequence, 36))
    return base36(max(count, highest) + 1)


def build_index_entry(
    args: argparse.Namespace,
    now: datetime,
    path: Path,
    memory_decision: str,
    memory_content: str,
    memory_reason: str,
    has_full_record: bool,
) -> dict[str, object]:
    index = index_path()
    allocation = getattr(args, "session_allocation", None)
    source_agent = detect_source_agent(args)
    agent_keywords = [
        f"agent:{source_agent['source_agent']}",
        f"source_agent:{source_agent['source_agent']}",
        f"代理:{source_agent['source_agent_label']}",
    ]
    allocated_sequence = (
        str(allocation.get("daily_sequence") or "").strip()
        if isinstance(allocation, dict)
        else ""
    )
    entry = {
        "time": now.isoformat(timespec="seconds"),
        "record_type": "checkpoint",
        "topic": args.topic,
        "phase": args.phase,
        "status": args.status,
        "keywords": unique(derive_keywords(args, memory_decision, memory_content) + agent_keywords, 40),
        "key_actions": unique(derive_key_actions(args, memory_decision) + [f"source_agent:{source_agent['source_agent']}"], 20),
        "summary": args.summary,
        "evidence": args.evidence,
        "next": args.next,
        "memory_decision": memory_decision,
        "risk_level": args.risk_level or "",
        "knowledge_value": args.knowledge_value or "",
        "priority_level": args.priority_level or "",
        "memory_content": memory_content,
        "memory_reason": memory_reason,
        "has_full_record": has_full_record,
        "source": relative_to_data(path),
        "daily_sequence": (
            allocated_sequence
            if allocated_sequence
            else next_daily_sequence(index, now.strftime("%Y%m%d"))
        ),
    }
    if isinstance(allocation, dict) and allocation.get("court_code"):
        entry["court_code"] = str(allocation["court_code"])
        entry["court_code_issued_at_start"] = True
    entry.update(source_agent)
    enrich_entry(entry)
    return entry


def lineage_parts_archive_json(entry: dict[str, object]) -> str:
    parts = existing_content_lineage_parts(entry)
    if parts is None:
        return ""
    return json.dumps(
        parts,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def append_text_synced(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = False
    if path.exists() and path.stat().st_size:
        with path.open("rb") as existing:
            existing.seek(-1, os.SEEK_END)
            needs_newline = existing.read(1) != b"\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        if needs_newline:
            handle.write("\n")
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def append_index_entry(index: Path, entry: dict[str, object]) -> None:
    append_text_synced(index, json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def append_archive_block(path: Path, block: str) -> None:
    append_text_synced(path, block)


def grow_tree_best_effort() -> None:
    try:
        from grow_shiguan_tree import grow_tree

        grow_tree()
        from build_shiguan_knowledge_graph import build_and_write

        build_and_write()
    except Exception as exc:  # pragma: no cover - archival write must not fail on tree refresh.
        print(f"SHIGUAN_TREE_REFRESH_WARNING {exc}", file=sys.stderr)


def background_python() -> str:
    candidate = Path(sys.executable)
    if sys.platform == "win32":
        pythonw = candidate.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(candidate)


def hidden_run_kwargs() -> dict[str, object]:
    if sys.platform != "win32":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def realtime_obsidian_sync_best_effort(timeout: int = 600) -> dict[str, object]:
    """Mirror the web UI's event-driven generation/export path for closeouts."""
    try:
        script = skill_root() / "scripts" / "shiguan_autosync_daemon.py"
        with tempfile.NamedTemporaryFile(prefix="shiguan-autosync-result-", suffix=".json", delete=False) as handle:
            result_path = Path(handle.name)
        try:
            proc = subprocess.run(
                [background_python(), str(script), "--once", "--force-sync", "--result-json", str(result_path)],
                cwd=str(skill_root()),
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=timeout,
                **hidden_run_kwargs(),
            )
            if proc.returncode != 0:
                detail = (proc.stderr or "sync failed")[-1200:]
                print(f"SHIGUAN_OBSIDIAN_SYNC_WARNING {detail}", file=sys.stderr)
                return {"status": "warning", "error": detail}
            result = json.loads(result_path.read_text(encoding="utf-8"))
            print("SHIGUAN_AUTOSYNC_OK " + json.dumps(result, ensure_ascii=False, sort_keys=True))
            return {"status": "synced", "result": result}
        finally:
            try:
                result_path.unlink()
            except OSError:
                pass
    except Exception as exc:  # pragma: no cover - archival write must not fail on Obsidian refresh.
        print(f"SHIGUAN_OBSIDIAN_SYNC_WARNING {exc}", file=sys.stderr)
        return {"status": "warning", "error": str(exc)}


def request_async_refresh(entry: dict[str, object], path: Path, mode: str) -> dict[str, object]:
    request = {
        "requested_at": datetime.now().isoformat(timespec="seconds"),
        "reason": "archive_checkpoint",
        "mode": mode,
        "topic": entry.get("topic", ""),
        "phase": entry.get("phase", ""),
        "court_code": entry.get("court_code", ""),
        "source": relative_to_data(path),
        "shared_shiguan_root": str(references_root()),
    }
    target = refresh_request_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        target,
        json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return {"status": "requested", "path": str(target)}


def finish_refresh(args: argparse.Namespace, entry: dict[str, object], path: Path) -> dict[str, object]:
    mode = str(args.refresh_mode or "async")
    if args.no_refresh:
        mode = "none"
    if args.refresh_tree:
        mode = "tree"
    if args.sync:
        mode = "sync"

    if mode == "none":
        return {"status": "skipped", "mode": mode}
    if mode == "tree":
        grow_tree_best_effort()
        return {"status": "tree_refreshed", "mode": mode}
    if mode == "sync":
        grow_tree_best_effort()
        result = realtime_obsidian_sync_best_effort(timeout=max(5, int(args.sync_timeout)))
        return {"mode": mode, **result}
    return {"mode": mode, **request_async_refresh(entry, path, mode)}


def append_checkpoint(args: argparse.Namespace) -> tuple[Path, dict[str, object], dict[str, object]]:
    memory_decision = (args.memory_decision or "DEFERRED").upper()
    memory_content = scrub_raw_placeholder_mentions(args.memory_content or "none")
    memory_reason = scrub_raw_placeholder_mentions(args.memory_reason or "not evaluated for this checkpoint")
    args.summary = scrub_raw_placeholder_mentions(args.summary)
    args.evidence = scrub_raw_placeholder_mentions(args.evidence)
    args.next = scrub_raw_placeholder_mentions(args.next)
    raw_full_record = read_full_record(args)
    lock_timeout = float(getattr(args, "lock_timeout", 30.0))

    with file_lock(shiguan_write_lock_path(), timeout=lock_timeout):
        # Seed creation, sequence allocation, archive append, and index append
        # form one serialized write transaction. Archive comes first so a crash
        # can leave only a recoverable orphan block, never a dangling index row.
        ensure_shared_seed()
        now = datetime.now()
        date_text = now.strftime("%Y%m%d")
        path = archive_path(args.topic, date_text)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            atomic_write_text(
                path,
                "\n".join(
                    [
                        f"# Court Shiguan Record: {args.topic}",
                        "",
                        f"- created_at: {now.isoformat(timespec='seconds')}",
                        f"- topic: {args.topic}",
                        "",
                    ]
                ),
            )

        session_id = str(getattr(args, "session_id", "") or "").strip()
        if session_id:
            from court_session_numbering import resolve_session_allocation

            args.session_allocation = resolve_session_allocation(
                session_id, date_text
            )
        else:
            args.session_allocation = None
        entry = build_index_entry(
            args,
            now,
            path,
            memory_decision,
            memory_content,
            memory_reason,
            bool(raw_full_record),
        )
        full_record = fill_generated_placeholders(raw_full_record, entry)
        lineage_parts_json = lineage_parts_archive_json(entry)
        block_lines = [
            f"## Checkpoint: {args.phase}",
            "",
            f"- time: {now.isoformat(timespec='seconds')}",
            f"- court_code: {entry.get('court_code', '')}",
            f"- ancient_lineage: {entry.get('ancient_lineage', '')}",
            *(
                [f"- lineage_parts_json: {lineage_parts_json}"]
                if lineage_parts_json
                else []
            ),
            f"- status: {args.status}",
            f"- summary: {args.summary}",
            f"- evidence: {args.evidence}",
            f"- full_record: {'yes' if full_record else 'no'}",
            f"- memory_decision: {memory_decision}",
            f"- risk_level: {entry.get('risk_level', '')}",
            f"- knowledge_value: {entry.get('knowledge_value', '')}",
            f"- priority_level: {entry.get('priority_level', '')}",
            f"- memory_content: {memory_content}",
            f"- memory_reason: {memory_reason}",
            f"- next: {args.next}",
            "",
        ]
        if full_record:
            block_lines.extend(
                [
                    "### Full Shiguan Record",
                    "",
                    "```text",
                    full_record,
                    "```",
                    "",
                ]
            )
        append_archive_block(path, "\n".join(block_lines))
        append_index_entry(index_path(), entry)

    refresh = finish_refresh(args, entry, path)
    return path, entry, refresh


def build_archive_receipt(
    path: Path,
    entry: dict[str, object],
    refresh: dict[str, object],
) -> dict[str, object]:
    court_code = str(entry.get("court_code") or "").strip()
    lineage_display = str(
        entry.get("lineage_display") or entry.get("ancient_lineage") or ""
    ).strip()
    source_agent_label = str(
        entry.get("source_agent_label") or entry.get("source_agent") or ""
    ).strip()
    closeout_identity = "\n".join(
        (
            f"诏令编号：{court_code}",
            f"古制谱系：{lineage_display}",
            f"作业AI：{source_agent_label}",
        )
    )
    receipt: dict[str, object] = {
        "schema": ARCHIVE_RECEIPT_SCHEMA,
        "receipt_id": f"shiguan:{court_code}",
        "path": str(path),
        "source": relative_to_data(path),
        "court_code": court_code,
        "ancient_lineage": str(entry.get("ancient_lineage") or ""),
        "lineage_display": lineage_display,
        "source_agent": str(entry.get("source_agent") or ""),
        "source_agent_label": source_agent_label,
        "closeout_identity": closeout_identity,
        "refresh": refresh,
    }
    lineage_parts = existing_content_lineage_parts(entry)
    if lineage_parts is not None:
        receipt["lineage_parts"] = lineage_parts
    return receipt


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument(
        "--session-id",
        default="",
        help=(
            "Session id allocated at conversation start; when present the "
            "closeout reuses the session's issued court_code instead of "
            "generating a new number."
        ),
    )
    parser.add_argument("--phase", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--next", required=True)
    parser.add_argument("--memory-decision", choices=["WRITE", "PROPOSE", "SKIP", "DEFERRED", "write", "propose", "skip", "deferred"])
    parser.add_argument("--memory-content")
    parser.add_argument("--memory-reason")
    parser.add_argument("--risk-level", choices=list("SABCDEFsabcdef"))
    parser.add_argument("--knowledge-value", choices=list("SABCDEFsabcdef"))
    parser.add_argument("--priority-level", choices=list("SABCDEFsabcdef"))
    parser.add_argument("--keywords", help="Comma/semicolon separated Shiguan recall keywords.")
    parser.add_argument("--key-actions", help="Comma/semicolon separated key behaviors for future court recall.")
    parser.add_argument(
        "--source-agent",
        help=(
            "Override source agent id for shared Shiguan records. "
            f"Allowed: {', '.join(source_agent_choices())}."
        ),
    )
    parser.add_argument("--full-record", help="Complete Shiguan memorial/process record text to append after the compact checkpoint.")
    parser.add_argument("--full-record-file", help="UTF-8 file containing the complete Shiguan memorial/process record.")
    parser.add_argument("--refresh-mode", choices=["async", "none", "tree", "sync"], default="async", help="Post-write refresh mode. Default writes a fast async refresh request for the service daemon.")
    parser.add_argument("--no-refresh", action="store_true", help="Only append archive/index records; do not refresh tree or request Obsidian sync.")
    parser.add_argument("--refresh-tree", action="store_true", help="Refresh the Shiguan tree/knowledge graph inline, but do not sync Obsidian.")
    parser.add_argument("--sync", action="store_true", help="Force inline tree refresh plus preserve-only Obsidian sync. This can be slow.")
    parser.add_argument("--sync-timeout", type=int, default=600)
    parser.add_argument("--lock-timeout", type=float, default=30.0, help="Seconds to wait for the shared Shiguan write lock.")
    parser.add_argument("--result-json", default="", help="Write a JSON summary with court_code/lineage/path for callers.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    try:
        path, entry, refresh = append_checkpoint(args)
    except TimeoutError as exc:
        print(f"ARCHIVE_LOCK_TIMEOUT {exc}", file=sys.stderr)
        return 12
    except PermissionError as exc:
        print(f"ARCHIVE_PERMISSION_REQUIRED {exc}", file=sys.stderr)
        print("Request approval/escalation, then rerun the same Shiguan command.", file=sys.stderr)
        return 13
    except ValueError as exc:
        prefix = (
            "ARCHIVE_SOURCE_AGENT_INVALID"
            if str(exc).startswith("source_agent_not_allowed:")
            else "ARCHIVE_ARGUMENT_INVALID"
        )
        print(f"{prefix} {exc}", file=sys.stderr)
        return 14

    result = build_archive_receipt(path, entry, refresh)
    if args.result_json:
        atomic_write_text(
            Path(args.result_json),
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"ARCHIVE_OK {path}")
        print("ARCHIVE_OK_JSON " + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
