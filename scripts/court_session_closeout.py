"""Explicitly close all still-open content in one conversation session."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

sys.dont_write_bytecode = True

from court_file_lock import atomic_write_text, file_lock


REQUEST_SCHEMA = "court.session_closeout.request.v1"
DRAFT_SCHEMA = "court.session_closeout.draft.v1"
RECEIPT_SCHEMA = "court.session_closeout.receipt.v1"
SUPPORTED_KINDS = frozenset({"chat", "light_answer", "task", "correction", "result"})

ArchiveWriter = Callable[[dict[str, object]], object]


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _normalize_item(value: object) -> dict[str, object]:
    _require(isinstance(value, Mapping), "item_type")
    session_id = value.get("session_id")
    sequence = value.get("sequence")
    kind = value.get("kind")
    content = value.get("content")
    closed = value.get("closed", False)
    _require(isinstance(session_id, str) and bool(session_id.strip()), "session_id")
    _require(type(sequence) is int and sequence >= 1, "sequence")
    _require(isinstance(kind, str) and kind in SUPPORTED_KINDS, "kind")
    _require(isinstance(content, str), "content")
    _require(type(closed) is bool, "closed")
    return {
        "session_id": session_id.strip(),
        "sequence": sequence,
        "kind": kind,
        "content": content,
        "closed": closed,
    }


def aggregate_session_closeout(
    items: Iterable[object],
    *,
    last_closeout_sequence: int,
) -> dict[str, object]:
    """Build a deterministic closeout draft without reading or writing state."""

    _require(type(last_closeout_sequence) is int and last_closeout_sequence >= 0, "last_closeout_sequence")
    normalized = [_normalize_item(item) for item in items]
    session_ids = {str(item["session_id"]) for item in normalized}
    _require(len(session_ids) <= 1, "cross_session_items")
    sequences = [int(item["sequence"]) for item in normalized]
    _require(len(sequences) == len(set(sequences)), "duplicate_sequence")
    selected = [
        item
        for item in sorted(normalized, key=lambda entry: int(entry["sequence"]))
        if int(item["sequence"]) > last_closeout_sequence and item["closed"] is False
    ]
    next_sequence = max([last_closeout_sequence, *sequences])
    return {
        "schema": DRAFT_SCHEMA,
        "session_id": next(iter(session_ids), None),
        "last_closeout_sequence": last_closeout_sequence,
        "next_closeout_sequence": next_sequence,
        "items": selected,
    }


def _read_cursor(path: Path, session_id: str | None) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cursor_invalid") from exc
    required = {
        "session_id",
        "last_closeout_sequence",
        "last_archive_path",
        "updated_at",
    }
    _require(isinstance(value, dict) and set(value) == required, "cursor_invalid")
    _require(isinstance(value["session_id"], str) and bool(value["session_id"]), "cursor_invalid")
    _require(type(value["last_closeout_sequence"]) is int and value["last_closeout_sequence"] >= 0, "cursor_invalid")
    _require(isinstance(value["last_archive_path"], str), "cursor_invalid")
    _require(isinstance(value["updated_at"], str), "cursor_invalid")
    if session_id is not None:
        _require(value["session_id"] == session_id, "cursor_session_mismatch")
    return value


def _atomic_write_cursor(path: Path, value: dict[str, object]) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _archive_path_from_result(value: object) -> str:
    if isinstance(value, Mapping):
        candidate = value.get("archive_path", value.get("path", ""))
    else:
        candidate = value
    _require(isinstance(candidate, (str, os.PathLike)) and bool(str(candidate)), "archive_path_missing")
    return str(candidate)


def _receipt(
    *,
    session_id: str | None,
    cursor_path: Path,
    last_closeout_sequence: int,
    last_archive_path: str,
    archive_written: bool,
    selected_count: int,
) -> dict[str, object]:
    return {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": (
            f"session:{session_id}:{last_closeout_sequence}"
            if session_id is not None
            else None
        ),
        "session_id": session_id,
        "cursor_path": str(cursor_path),
        "last_closeout_sequence": last_closeout_sequence,
        "last_archive_path": last_archive_path,
        "archive_written": archive_written,
        "selected_count": selected_count,
    }


def commit_session_closeout(
    draft: object,
    *,
    archive_writer: ArchiveWriter,
    cursor_path: str | os.PathLike[str],
) -> dict[str, object]:
    """Archive once, then atomically advance the per-session cursor."""

    _require(isinstance(draft, Mapping) and draft.get("schema") == DRAFT_SCHEMA, "draft_invalid")
    session_id = draft.get("session_id")
    _require(session_id is None or isinstance(session_id, str), "draft_session_id")
    start = draft.get("last_closeout_sequence")
    target = draft.get("next_closeout_sequence")
    selected = draft.get("items")
    _require(type(start) is int and start >= 0, "draft_cursor")
    _require(type(target) is int and target >= start, "draft_cursor")
    _require(isinstance(selected, list), "draft_items")
    normalized_selected = [_normalize_item(item) for item in selected]
    if session_id is None:
        _require(not normalized_selected, "draft_session_id")
    else:
        _require(
            all(item["session_id"] == session_id for item in normalized_selected),
            "cross_session_draft",
        )
    _require(
        all(start < int(item["sequence"]) <= target for item in normalized_selected),
        "draft_sequence",
    )
    _require(all(item["closed"] is False for item in normalized_selected), "draft_closed_item")
    selected_sequences = [int(item["sequence"]) for item in normalized_selected]
    _require(len(selected_sequences) == len(set(selected_sequences)), "duplicate_sequence")
    normalized_selected.sort(key=lambda item: int(item["sequence"]))
    normalized_draft = {
        "schema": DRAFT_SCHEMA,
        "session_id": session_id,
        "last_closeout_sequence": start,
        "next_closeout_sequence": target,
        "items": normalized_selected,
    }
    path = Path(cursor_path)

    if session_id is None:
        return _receipt(
            session_id=None,
            cursor_path=path,
            last_closeout_sequence=start,
            last_archive_path="",
            archive_written=False,
            selected_count=0,
        )

    lock_path = path.with_name(f".{path.name}.closeout.lock")
    with file_lock(lock_path):
        current = _read_cursor(path, session_id)
        current_sequence = int(current["last_closeout_sequence"]) if current else 0
        current_archive_path = str(current["last_archive_path"]) if current else ""

        if current_sequence >= target:
            return _receipt(
                session_id=session_id,
                cursor_path=path,
                last_closeout_sequence=current_sequence,
                last_archive_path=current_archive_path,
                archive_written=False,
                selected_count=0,
            )
        _require(current_sequence == start, "stale_closeout_draft")

        archive_written = False
        archive_path = current_archive_path
        if normalized_selected:
            archive_path = _archive_path_from_result(archive_writer(normalized_draft))
            archive_written = True

        cursor = {
            "session_id": session_id,
            "last_closeout_sequence": target,
            "last_archive_path": archive_path,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        # The archive and cursor are separate files. A host crash between these
        # writes remains a residual risk; no second journal or ledger is added.
        _atomic_write_cursor(path, cursor)
        return _receipt(
            session_id=session_id,
            cursor_path=path,
            last_closeout_sequence=target,
            last_archive_path=archive_path,
            archive_written=archive_written,
            selected_count=len(normalized_selected),
        )


def render_session_closeout_markdown(draft: Mapping[str, object]) -> str:
    session_id = str(draft.get("session_id") or "")
    items = draft.get("items")
    _require(isinstance(items, list), "draft_items")
    lines = [
        "# 会话结诏",
        "",
        f"- session_id: {session_id}",
        f"- through_sequence: {draft.get('next_closeout_sequence')}",
        "",
        "## 未结诏内容",
        "",
    ]
    for entry in items:
        _require(isinstance(entry, Mapping), "draft_item")
        lines.extend(
            (
                f"### {entry.get('sequence')} [{entry.get('kind')}]",
                "",
                str(entry.get("content", "")),
                "",
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def _default_archive_writer(draft: dict[str, object]) -> dict[str, object]:
    from archive_checkpoint import append_checkpoint

    session_id = str(draft["session_id"])
    selected = draft["items"]
    args = argparse.Namespace(
        session_id=session_id,
        topic=f"session-closeout-{session_id}",
        phase="结诏",
        status="DONE",
        summary=f"显式合并结诏会话内容 {len(selected)} 条",
        evidence=(
            f"session_id={session_id}; "
            f"sequence={draft['last_closeout_sequence']}..{draft['next_closeout_sequence']}"
        ),
        next="none",
        memory_decision="SKIP",
        memory_content="none",
        memory_reason="会话结诏是史馆记录，不自动提升为长期记忆",
        risk_level=None,
        knowledge_value=None,
        priority_level=None,
        keywords="会话结诏,session closeout",
        key_actions="closeout-session",
        source_agent=None,
        full_record=render_session_closeout_markdown(draft),
        full_record_file=None,
        refresh_mode="none",
        no_refresh=True,
        refresh_tree=False,
        sync=False,
        sync_timeout=600,
        lock_timeout=30.0,
    )
    path, entry, _refresh = append_checkpoint(args)
    return {
        "archive_path": str(path),
        "court_code": str(entry.get("court_code") or ""),
    }


def _default_cursor_path(session_id: str) -> Path:
    from shiguan_paths import reference_path

    directory = quote(session_id, safe="")
    _require(directory not in {"", ".", ".."}, "session_id")
    return reference_path("court-runtime", "session-closeout", directory, "cursor.json")


def execute_request(request: object) -> dict[str, object]:
    _require(isinstance(request, Mapping), "request_type")
    _require(set(request) == {"schema", "session_id", "items"}, "request_fields")
    _require(request.get("schema") == REQUEST_SCHEMA, "request_schema")
    session_id = request.get("session_id")
    items = request.get("items")
    _require(isinstance(session_id, str) and bool(session_id.strip()), "request_session_id")
    _require(isinstance(items, list), "request_items")
    session_id = session_id.strip()
    cursor_path = _default_cursor_path(session_id)
    current = _read_cursor(cursor_path, session_id)
    last_sequence = int(current["last_closeout_sequence"]) if current else 0
    draft = aggregate_session_closeout(items, last_closeout_sequence=last_sequence)
    if draft["session_id"] is None:
        draft = {**draft, "session_id": session_id}
    _require(draft["session_id"] == session_id, "request_session_mismatch")
    return commit_session_closeout(
        draft,
        archive_writer=_default_archive_writer,
        cursor_path=cursor_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    def emit_error(error_code: str, returncode: int) -> int:
        print(
            json.dumps(
                {
                    "schema": RECEIPT_SCHEMA,
                    "ok": False,
                    "error_code": error_code,
                    "problems": [error_code],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return returncode

    try:
        raw_request = Path(args.request_file).read_text(encoding="utf-8")
    except OSError:
        return emit_error("invalid_request_file", 3)
    try:
        request = json.loads(raw_request)
    except json.JSONDecodeError:
        return emit_error("invalid_request_json", 3)
    try:
        result = execute_request(request)
    except ValueError as exc:
        reason = str(exc) or "request"
        error_code = reason if reason.startswith("invalid_") else f"invalid_{reason}"
        return emit_error(error_code, 3)
    except (OSError, RuntimeError, TimeoutError):
        return emit_error("blocked_archive_runtime", 2)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"SESSION_CLOSEOUT_OK {result['last_archive_path']}")
        print(f"SESSION_CLOSEOUT_CURSOR {result['cursor_path']} {result['last_closeout_sequence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
