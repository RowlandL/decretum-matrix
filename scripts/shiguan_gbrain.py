"""Metadata-first Shiguan GBrain recall and settlement candidates."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
import zlib

sys.dont_write_bytecode = True

from shiguan_entry_utils import index_path, load_entries, score_entry, select_matches
from shiguan_paths import reference_path


RECALL_SCHEMA = "decretum.gbrain.recall.v1"
SETTLEMENT_SCHEMA = "decretum.gbrain.settlement_candidates.v1"


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
