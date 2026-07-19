"""Metadata-first Shiguan recall shared by governance implementations."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

from shiguan_entry_utils import enrich_entry
from shiguan_paths import reference_path


RECALL_SCHEMA = "decretum.gbrain.recall.v1"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def index_path() -> Path:
    return reference_path("shiguan-index.jsonl")


def load_entries(path: Path | None = None) -> list[dict[str, object]]:
    source = path or index_path()
    if not source.exists():
        return []
    entries: list[dict[str, object]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
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
    for key in (
        "capability_vector_text",
        "vector_text",
        "embedding_text",
        "capability_vector_hash",
        "capability_vector_kind",
    ):
        value = entry.get(key)
        if isinstance(value, str):
            weighted_parts.append((5, value))
    for key in (
        "summary",
        "memory_content",
        "memory_reason",
        "display_labels_zh",
        "display_summary_zh",
        "display_reason_zh",
    ):
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


def select_matches(entries: list[dict[str, object]], terms: list[str]) -> list[dict[str, object]]:
    if terms:
        scored = [(score_entry(entry, terms), entry) for entry in entries]
        matches = [(score, entry) for score, entry in scored if score > 0]
        matches.sort(
            key=lambda item: (item[0], str(item[1].get("time", ""))),
            reverse=True,
        )
        return [entry for _, entry in matches]
    return sorted(entries, key=lambda entry: str(entry.get("time", "")), reverse=True)


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
    return "recall-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _memory_git_provenance(value: object | None) -> dict[str, object]:
    if value is None:
        try:
            from shiguan_git_federation import recall_provenance

            value = recall_provenance(shared_root=reference_path())
        except (ImportError, OSError, RuntimeError, ValueError):
            value = None
    if not isinstance(value, dict):
        return {
            "schema": "decretum.gbrain.memory_git_provenance.v1",
            "registry_available": False,
            "migration_links_verified": False,
            "managed_store_count": 0,
            "stores": [],
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
    }
    for key in ("shared_registry_commit", "transaction_id"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            result[key] = item.strip()
    return result


def build_recall_context(
    entries: list[dict[str, object]],
    terms: list[str],
    *,
    governance_id: str,
    current_decree_sha256: str,
    as_of: str,
    limit: int = 5,
    memory_git_provenance: dict[str, object] | None = None,
) -> dict[str, object]:
    if not isinstance(governance_id, str) or not governance_id.strip():
        raise ValueError("governance_id_required")
    if not _DIGEST_RE.fullmatch(current_decree_sha256):
        raise ValueError("current_decree_sha256_invalid")
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
        "current_decree_sha256": current_decree_sha256,
        "current_decree_precedence": True,
        "authority": "advisory",
        "execution_authority": False,
        "as_of": as_of,
        "terms": normalized_terms,
        "match_count": len(matches),
        "matches": matches,
        "memory_git": _memory_git_provenance(memory_git_provenance),
    }
