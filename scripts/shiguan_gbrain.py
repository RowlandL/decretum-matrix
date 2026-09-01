"""Metadata-first Shiguan GBrain recall and settlement candidates.

P2-1 naming: GBrain is a *metadata enhancement layer*, not an independent
recaller. All recall ranking flows through the single canonical scorer in
``shiguan_entry_utils`` (``select_matches`` / ``score_entry_recall_breakdown``);
this module adds governance applicability, conflict preservation, memory-git
provenance and full-record pointers on top of the same ranked entries.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import zlib

sys.dont_write_bytecode = True

from shiguan_entry_utils import index_path, load_entries, score_entry, select_matches
from shiguan_paths import reference_path


RECALL_SCHEMA = "decretum.gbrain.recall.v1"
SETTLEMENT_SCHEMA = "decretum.gbrain.settlement_candidates.v1"
FULL_RECORD_POINTER_SCHEMA = "court.full_record_pointer.v1"
FULL_RECORD_INDEX_SCHEMA = "court.full_record_index.v1"


def _relative_source_ref(entry: dict[str, object]) -> str | None:
    """Return a portable relative source path or None for absolute host paths."""
    source = str(entry.get("source") or "").strip()
    if not source:
        return None
    if re.match(r"^[A-Za-z]:[\\/]", source) or source.startswith(("/", "\\")):
        return None
    return source.replace("\\", "/")


def _canonical_metadata_digest(entry: dict[str, object]) -> str:
    """Deterministic sha256 over canonical entry metadata (no body read)."""
    projection: dict[str, object] = {}
    for key in (
        "record_uid",
        "court_code",
        "time",
        "topic",
        "phase",
        "status",
        "summary",
        "source",
        "memory_decision",
        "lineage_key",
        "lineage_display",
    ):
        if entry.get(key) is not None:
            projection[key] = entry[key]
    return hashlib.sha256(
        json.dumps(
            projection,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def full_record_pointer(entry: dict[str, object]) -> dict[str, object]:
    """Metadata-only full-record pointer (P3-7/P3-9): no body copies, no
    absolute host path contract, only relative locator + section + source hash
    + access status. Pending/private bodies are never copied into the index."""
    source_ref = _relative_source_ref(entry)
    phase = str(entry.get("phase") or "")
    status = str(entry.get("status") or "").upper()
    summary = str(entry.get("summary") or "")
    evidence = str(entry.get("evidence") or "")
    next_step = str(entry.get("next") or "")
    key_actions = [
        str(item) for item in (entry.get("key_actions") or []) if str(item).strip()
    ]
    resolved = status in {
        "DONE",
        "DONE_WITH_CONCERNS",
        "APPROVED",
        "APPROVED_WITH_CAVEATS",
    }
    section = f"## Checkpoint: {phase}" if phase else None
    return {
        "schema": FULL_RECORD_POINTER_SCHEMA,
        "source_ref": source_ref,
        "section": section,
        "line_anchor": phase or None,
        "source_hash": _canonical_metadata_digest(entry),
        "access_status": "metadata_only",
        "fields": {
            "initial_question": str(entry.get("topic") or ""),
            "process_questions": [phase] if phase else [],
            "initial_actions": key_actions[0] if key_actions else None,
            "subsequent_actions": key_actions[1:],
            "final_result": summary or evidence,
            "resolved": resolved,
            "resolution_scope": phase or source_ref,
            "next_step": next_step,
        },
        "unindexed_fields": ["errors", "fixes", "full_body"],
        "locator": (
            f"{source_ref}#{section}" if source_ref and section else source_ref
        ),
    }


def build_leaves(
    entries: list[dict[str, object]],
    entry: dict[str, object],
    limit: int = 8,
) -> list[dict[str, object]]:
    """Related leaf metadata for a record (same lineage or topic, no bodies)."""
    bounded = max(1, min(int(limit), 32))
    self_uid = _record_uid(entry)
    lineage = str(
        entry.get("lineage_key") or entry.get("lineage_display") or ""
    ).strip()
    topic = " ".join(str(entry.get("topic") or "").casefold().split())
    leaves: list[dict[str, object]] = []
    for candidate in entries:
        if _record_uid(candidate) == self_uid:
            continue
        candidate_lineage = str(
            candidate.get("lineage_key") or candidate.get("lineage_display") or ""
        ).strip()
        candidate_topic = " ".join(
            str(candidate.get("topic") or "").casefold().split()
        )
        related = bool(
            (lineage and candidate_lineage == lineage)
            or (topic and candidate_topic == topic)
        )
        if not related:
            continue
        leaves.append(
            {
                "record_uid": _record_uid(candidate),
                "court_code": str(candidate.get("court_code") or ""),
                "topic": str(candidate.get("topic") or ""),
                "summary": str(candidate.get("summary") or "")[:120],
                "time": str(candidate.get("time") or ""),
                "phase": str(candidate.get("phase") or ""),
                "full_record": full_record_pointer(candidate),
            }
        )
        if len(leaves) >= bounded:
            break
    return leaves


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _applicability(entry: dict[str, object], as_of: datetime) -> str:
    valid_from = _timestamp(entry.get("valid_from"))
    valid_until = _timestamp(entry.get("valid_until"))
    if valid_from is None and valid_until is None:
        return "undated"
    if valid_from is not None and as_of < valid_from:
        return "future"
    if valid_until is not None and as_of > valid_until:
        return "historical"
    return "current"


def _conflict(entry: dict[str, object]) -> str:
    state = str(entry.get("conflict_state") or "").strip().casefold()
    if entry.get("memory_conflict") is True or state not in {"", "none", "resolved"}:
        return "preserved"
    return "none"


def _record_uid(entry: dict[str, object]) -> str:
    for field in ("record_uid", "court_code"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    material = json.dumps(
        {
            "time": entry.get("time"),
            "topic": entry.get("topic"),
            "source": entry.get("source"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"recall-{zlib.crc32(material.encode('utf-8')):08x}"


def _load_memory_git_provenance(shared_root: Path | None = None) -> dict[str, object]:
    from shiguan_git_federation import recall_provenance

    return recall_provenance(shared_root=shared_root or reference_path())


def _memory_git_provenance(
    value: object | None,
    *,
    include_memory_git: bool = False,
    shared_root: Path | None = None,
    loader: object | None = None,
) -> dict[str, object]:
    trigger_mode = "explicit_provenance" if isinstance(value, dict) else "not_requested"
    if not isinstance(value, dict) and include_memory_git:
        try:
            if callable(loader):
                value = loader(shared_root)
            else:
                value = _load_memory_git_provenance(shared_root)
            trigger_mode = "gbrain_triggered"
        except (ImportError, OSError, RuntimeError, ValueError):
            trigger_mode = "trigger_failed"
    if not isinstance(value, dict):
        return {
            "schema": "decretum.gbrain.memory_git_provenance.v1",
            "registry_available": False,
            "migration_links_verified": False,
            "managed_store_count": 0,
            "stores": [],
            "trigger_mode": trigger_mode,
        }
    stores: list[dict[str, object]] = []
    raw_stores = value.get("stores")
    if isinstance(raw_stores, list):
        allowed = (
            "memory_store_id",
            "tool_class",
            "memory_state",
            "native_commit",
            "shared_commit",
            "transaction_id",
        )
        for raw in raw_stores:
            if not isinstance(raw, dict):
                continue
            stores.append(
                {
                    key: raw[key]
                    for key in allowed
                    if isinstance(raw.get(key), (str, int, bool))
                }
            )
    result: dict[str, object] = {
        "schema": "decretum.gbrain.memory_git_provenance.v1",
        "registry_available": value.get("registry_available") is True,
        "migration_links_verified": value.get("migration_links_verified") is True,
        "managed_store_count": int(value.get("managed_store_count") or 0),
        "stores": stores,
        "trigger_mode": trigger_mode,
    }
    for key in ("shared_registry_commit", "transaction_id"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            result[key] = item.strip()
    return result


def _current_decree_id(
    current_decree_id: str | None,
    current_decree_sha256: str | None,
) -> str:
    value = current_decree_id or current_decree_sha256
    if not isinstance(value, str) or not value.strip():
        raise ValueError("current_decree_id_required")
    return value.strip()


def build_recall_context(
    entries: list[dict[str, object]],
    terms: list[str],
    *,
    governance_id: str,
    current_decree_id: str | None = None,
    current_decree_sha256: str | None = None,
    as_of: str,
    limit: int = 5,
    memory_git_provenance: dict[str, object] | None = None,
    include_memory_git: bool = False,
    memory_git_shared_root: Path | None = None,
    memory_git_loader: object | None = None,
) -> dict[str, object]:
    if not isinstance(governance_id, str) or not governance_id.strip():
        raise ValueError("governance_id_required")
    decree_id = _current_decree_id(current_decree_id, current_decree_sha256)
    instant = _timestamp(as_of)
    if instant is None:
        raise ValueError("as_of_invalid")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit_invalid")
    normalized_terms = [term.strip() for term in terms if isinstance(term, str) and term.strip()]
    selected = select_matches(entries, normalized_terms)[:limit]
    matches: list[dict[str, object]] = []
    for entry in selected:
        matches.append(
            {
                "record_uid": _record_uid(entry),
                "court_code": str(entry.get("court_code") or ""),
                "time": str(entry.get("time") or ""),
                "source": str(entry.get("source") or ""),
                "evidence": str(entry.get("evidence") or ""),
                "summary": str(
                    entry.get("keyword_summary_zh")
                    or entry.get("display_summary_zh")
                    or entry.get("summary")
                    or ""
                ),
                "memory_decision": str(entry.get("memory_decision") or ""),
                "score": score_entry(entry, normalized_terms),
                "applicability": _applicability(entry, instant),
                "conflict": _conflict(entry),
                "full_record": full_record_pointer(entry),
                "leaves": build_leaves(entries, entry, limit=6),
            }
        )
    return {
        "schema": RECALL_SCHEMA,
        "governance_id": governance_id,
        "current_decree_id": decree_id,
        "current_decree_precedence": True,
        "authority": "advisory",
        "execution_authority": False,
        "as_of": as_of,
        "terms": normalized_terms,
        "match_count": len(matches),
        "matches": matches,
        "memory_git": _memory_git_provenance(
            memory_git_provenance,
            include_memory_git=include_memory_git,
            shared_root=memory_git_shared_root,
            loader=memory_git_loader,
        ),
    }


def build_full_record_index(
    entries: list[dict[str, object]],
) -> dict[str, object]:
    """Queryable leaves + full-record pointer index (P3-9).

    Preserves the original fourteen-line compact memorial and record structure
    upstream; this index only adds queryable leaves and full-record pointers
    (relative source path / section / line anchor / source hash / access
    status). Pending/private bodies are never copied; absolute host paths are
    rejected as non-portable.
    """
    records: list[dict[str, object]] = []
    for entry in entries:
        pointer = full_record_pointer(entry)
        if pointer.get("source_ref") is None:
            continue
        records.append(
            {
                "record_uid": _record_uid(entry),
                "court_code": str(entry.get("court_code") or ""),
                "topic": str(entry.get("topic") or ""),
                "phase": str(entry.get("phase") or ""),
                "status": str(entry.get("status") or ""),
                "source_ref": pointer["source_ref"],
                "source_hash": pointer["source_hash"],
                "section": pointer["section"],
                "line_anchor": pointer["line_anchor"],
                "access_status": pointer["access_status"],
                "fields": pointer["fields"],
                "unindexed_fields": pointer["unindexed_fields"],
                "locator": pointer["locator"],
                "leaves": build_leaves(entries, entry, limit=8),
            }
        )
    return {
        "schema": FULL_RECORD_INDEX_SCHEMA,
        "record_count": len(records),
        "records": records,
    }


def _settlement_disposition(entry: dict[str, object], as_of: datetime) -> str:
    decision = str(entry.get("memory_decision") or "").strip().upper()
    applicability = _applicability(entry, as_of)
    conflict = _conflict(entry)
    if conflict == "preserved":
        return "preserve_conflict_for_menxia_review"
    if applicability in {"historical", "future"}:
        return f"review_{applicability}_record"
    if decision == "WRITE":
        return "candidate_long_term_memory"
    if decision == "PROPOSE":
        return "candidate_menxia_review"
    if decision == "SKIP":
        return "candidate_skip_preserved"
    return "candidate_classify"


def build_settlement_candidates(
    entries: list[dict[str, object]],
    terms: list[str],
    *,
    current_decree_id: str | None = None,
    current_decree_sha256: str | None = None,
    as_of: str,
    limit: int = 10,
    include_memory_git: bool = False,
    memory_git_provenance: dict[str, object] | None = None,
    memory_git_shared_root: Path | None = None,
    memory_git_loader: object | None = None,
) -> dict[str, object]:
    """Return read-only GBrain organization candidates without writing memory."""

    decree_id = _current_decree_id(current_decree_id, current_decree_sha256)
    instant = _timestamp(as_of)
    if instant is None:
        raise ValueError("as_of_invalid")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit_invalid")
    normalized_terms = [term.strip() for term in terms if isinstance(term, str) and term.strip()]
    selected = select_matches(entries, normalized_terms)[:limit]
    candidates: list[dict[str, object]] = []
    seen_summaries: dict[str, str] = {}
    duplicate_groups: list[dict[str, object]] = []
    for entry in selected:
        summary = str(
            entry.get("keyword_summary_zh")
            or entry.get("display_summary_zh")
            or entry.get("summary")
            or ""
        ).strip()
        uid = _record_uid(entry)
        if summary:
            normalized_summary = " ".join(summary.casefold().split())
            prior = seen_summaries.get(normalized_summary)
            if prior:
                duplicate_groups.append({"summary": summary, "record_uids": [prior, uid]})
            else:
                seen_summaries[normalized_summary] = uid
        candidates.append(
            {
                "record_uid": uid,
                "court_code": str(entry.get("court_code") or ""),
                "summary": summary,
                "memory_decision": str(entry.get("memory_decision") or ""),
                "applicability": _applicability(entry, instant),
                "conflict": _conflict(entry),
                "disposition": _settlement_disposition(entry, instant),
            }
        )
    return {
        "schema": SETTLEMENT_SCHEMA,
        "authority": "advisory",
        "execution_authority": False,
        "write_authority": False,
        "current_decree_precedence": True,
        "current_decree_id": decree_id,
        "as_of": as_of,
        "terms": normalized_terms,
        "derived_from": "existing_shiguan_records",
        "existing_toolchain": [
            "scripts/memory_decision.py",
            "scripts/reevaluate_memory_decisions.py",
            "scripts/tidy_shiguan_records.py",
        ],
        "candidate_count": len(candidates),
        "candidates": candidates,
        "duplicate_groups": duplicate_groups,
        "memory_git": _memory_git_provenance(
            memory_git_provenance,
            include_memory_git=include_memory_git,
            shared_root=memory_git_shared_root,
            loader=memory_git_loader,
        ),
    }
