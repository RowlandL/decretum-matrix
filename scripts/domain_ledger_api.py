"""Domain ledger API: authority-bound Create/Read/Update for court ledgers.

This is the shared domain layer referenced by devspec FR-D D2a: the unified
CLI, proactive CLI and MCP adapters may call these functions; MCP projections
stay read-only (see court_public_registry), so write paths here are invoked
through the authorized CLI/proactive paths only.

Guarantees implemented in this module:

- ACL/authority: write operations refuse ``authority == "approval"``.
- write_set: callers declare a write_set that must be a subset of the allowed
  set for the ledger kind; the ledger file itself always stays under root.
- Create is idempotent per (kind, topic); Update appends an immutable revision
  and is idempotent per (kind, topic, idempotency_key).
- Every successful write appends a revision and makes one atomic Git commit in
  the ledger root; failed writes never commit and never append.
- Read returns a metadata projection without raw content for pending/private
  scopes.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from shiguan_paths import reference_path

LEDGER_SCHEMA = "court.domain_ledger.v1"
ALLOWED_AUTHORITIES = ("approval", "autonomous", "super")
ALLOWED_KINDS = ("memory", "capability")
ALLOWED_OPERATIONS = ("create", "update", "read")
ALLOWED_WRITE_SETS = {
    "memory": ("memory",),
    "capability": ("capability-index",),
}
TOPIC_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
CONTENT_MAX_CHARS = 2048


def default_ledger_root() -> Path:
    """Resolve the shared court-runtime root (read-only resolution)."""
    return reference_path("court-runtime")


def ledger_file(root: Path, kind: str) -> Path:
    return Path(root) / "domain-ledger" / f"{kind}.json"


def _topic_sha256(topic: str) -> str:
    return hashlib.sha256(topic.encode("utf-8")).hexdigest()


def _load_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": LEDGER_SCHEMA, "kind": path.stem, "revisions": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != LEDGER_SCHEMA:
        raise ValueError("domain_ledger_corrupt")
    return value


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    from court_file_lock import atomic_write_text

    atomic_write_text(path, text)


def _git_commit(root: Path, message: str) -> str | None:
    """Make one atomic Git commit in ``root``; return the commit sha or None.

    Only files under ``domain-ledger/`` are staged. A missing/invalid Git
    repository fails closed (raises) so a write can never claim success without
    its commit.
    """
    commands = [
        ["git", "-C", str(root), "add", "--", "domain-ledger/"],
        ["git", "-C", str(root), "commit", "-q", "-m", message],
        ["git", "-C", str(root), "rev-parse", "HEAD"],
    ]
    commit_sha: str | None = None
    for command in commands:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        subcommand = command[3] if len(command) > 3 else ""
        if result.returncode != 0:
            if subcommand == "commit" and "nothing to commit" in (result.stderr or ""):
                continue
            raise ValueError(f"domain_ledger_git_failed:{subcommand}:{(result.stderr or result.stdout or '').strip()[:200]}")
        if subcommand == "rev-parse":
            commit_sha = result.stdout.strip() or None
    return commit_sha


def _authority_gate(authority: str | None) -> str | None:
    """Return an error code when the authority cannot write, else None."""
    selected = str(authority or "").strip().lower()
    if selected not in ALLOWED_AUTHORITIES:
        return "invalid_authority"
    if selected == "approval":
        return "authority_read_only"
    return None


def _write_set_gate(kind: str, write_set: object) -> list[str] | None:
    """Return violation codes when the declared write_set is not allowed."""
    allowed = set(ALLOWED_WRITE_SETS.get(kind, ()))
    declared = {str(item).strip() for item in write_set if str(item).strip()} if isinstance(write_set, (list, tuple)) else set()
    if not declared:
        return ["empty_write_set"]
    violations = [f"write_set_not_allowed:{item}" for item in sorted(declared - allowed)]
    return violations or None


def _topic_gate(topic: object) -> str | None:
    text = str(topic or "").strip()
    if TOPIC_RE.fullmatch(text) is None:
        return "invalid_topic"
    return None


def _content_gate(content: object) -> str | None:
    if not isinstance(content, str):
        return "content_must_be_string"
    if len(content) > CONTENT_MAX_CHARS:
        return "content_too_long"
    return None


def domain_ledger_read(kind: str, root: Path | None = None, limit: int = 50) -> dict[str, Any]:
    """Read a domain ledger as a metadata projection (no write side effects)."""
    if kind not in ALLOWED_KINDS:
        return {"schema": LEDGER_SCHEMA, "kind": str(kind), "ok": False, "errors": [{"field": "kind", "kind": "contract", "code": "invalid_kind"}]}
    bounded = max(1, min(int(limit), 200))
    try:
        ledger = _load_ledger(ledger_file(root or default_ledger_root(), kind))
    except (OSError, ValueError) as exc:
        return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": False, "errors": [{"field": "root", "kind": "runtime", "code": str(exc)}]}
    revisions = [
        {
            "revision": item.get("revision"),
            "operation": item.get("operation"),
            "topic": item.get("topic"),
            "content_sha256": item.get("content_sha256"),
            "actor": item.get("actor"),
            "authority": item.get("authority"),
            "write_set": item.get("write_set"),
            "git_commit": item.get("git_commit"),
            "created_at": item.get("created_at"),
        }
        for item in ledger.get("revisions", [])[-bounded:]
        if isinstance(item, dict)
    ]
    return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": True, "errors": [], "revisions": revisions, "count": len(revisions)}


def domain_ledger_write(
    *,
    kind: str,
    operation: str,
    topic: str,
    content: str,
    actor: str,
    authority: str,
    write_set: list[str],
    root: Path | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Authorized domain ledger Create/Update with immutable revisions + Git commit.

    ``metadata`` is an optional structured summary (actor/role/write_set/skill
    selection etc.) stored verbatim in the ledger record; it must be
    JSON-serializable and is subject to the same privacy discipline as the
    rest of the ledger (no raw pending/private bodies).
    """
    if kind not in ALLOWED_KINDS:
        return {"schema": LEDGER_SCHEMA, "kind": str(kind), "ok": False, "errors": [{"field": "kind", "kind": "contract", "code": "invalid_kind"}]}
    if operation not in ALLOWED_OPERATIONS or operation == "read":
        return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": False, "errors": [{"field": "operation", "kind": "contract", "code": "invalid_operation"}]}
    errors: list[dict[str, Any]] = []
    authority_error = _authority_gate(authority)
    if authority_error:
        errors.append({"field": "authority", "kind": "acl", "code": authority_error})
    write_set_error = _write_set_gate(kind, write_set)
    if write_set_error:
        errors.append({"field": "write_set", "kind": "acl", "code": write_set_error[0]})
    topic_error = _topic_gate(topic)
    if topic_error:
        errors.append({"field": "topic", "kind": "contract", "code": topic_error})
    content_error = _content_gate(content)
    if content_error:
        errors.append({"field": "content", "kind": "contract", "code": content_error})
    if not str(actor or "").strip():
        errors.append({"field": "actor", "kind": "acl", "code": "missing_actor"})
    if errors:
        return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": False, "errors": errors}

    selected_root = Path(root or default_ledger_root())
    path = ledger_file(selected_root, kind)
    try:
        ledger = _load_ledger(path)
    except (OSError, ValueError) as exc:
        return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": False, "errors": [{"field": "root", "kind": "runtime", "code": str(exc)}]}

    revisions = ledger.get("revisions", [])
    # Create idempotency: an existing topic returns the existing record unchanged.
    existing = [item for item in reversed(revisions) if isinstance(item, dict) and item.get("topic") == topic]
    if operation == "create" and existing:
        record = existing[0]
        return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": True, "errors": [], "idempotent": True, "record": record}
    # Update idempotency: same (topic, idempotency_key) returns the recorded result.
    if operation == "update" and idempotency_key:
        for item in reversed(revisions):
            if isinstance(item, dict) and item.get("topic") == topic and item.get("idempotency_key") == idempotency_key:
                return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": True, "errors": [], "idempotent": True, "record": item}

    import uuid
    from datetime import datetime, timezone

    revision = len(revisions) + 1
    payload = {
        "schema": LEDGER_SCHEMA,
        "revision": revision,
        "operation": operation,
        "topic": topic,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "actor": str(actor).strip(),
        "authority": str(authority).strip().lower(),
        "write_set": sorted(str(item).strip() for item in write_set if str(item).strip()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if idempotency_key:
        payload["idempotency_key"] = str(idempotency_key).strip()
    if metadata is not None:
        if not isinstance(metadata, dict):
            return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": False, "errors": [{"field": "metadata", "kind": "contract", "code": "metadata_must_be_object"}]}
        try:
            json.dumps(metadata, ensure_ascii=False)
        except (TypeError, ValueError):
            return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": False, "errors": [{"field": "metadata", "kind": "contract", "code": "metadata_not_serializable"}]}
        payload["metadata"] = metadata
    # optimistic concurrency for update: base_revision handled by caller via read
    ledger["revisions"] = [*revisions, payload]
    _atomic_write_text(path, json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    try:
        commit_sha = _git_commit(selected_root, f"domain-ledger: {kind} {operation} {_topic_sha256(topic)[:12]}")
    except (OSError, ValueError) as exc:
        # roll back the file so a failed commit never leaves a dangling revision
        try:
            ledger["revisions"] = revisions
            _atomic_write_text(path, json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        except OSError:
            pass
        return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": False, "errors": [{"field": "git", "kind": "runtime", "code": str(exc)}]}
    payload["git_commit"] = commit_sha
    # persist commit sha into the revision for auditability
    ledger["revisions"][-1]["git_commit"] = commit_sha
    _atomic_write_text(path, json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": True, "errors": [], "record": ledger["revisions"][-1]}


def domain_skill_load_record(
    *,
    actor: str,
    role: str,
    authority: str,
    write_set: list[str],
    skill_path: str,
    skill_hash: str,
    selection_reason: str,
    root: Path | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Record a minimal multi-skill load decision in the capability ledger.

    P2-6 orchestration: the host loads the smallest dependency-ordered skill
    set after an index-first lookup, then records actor/role/authority/
    write_set/skill path + sha256/selection reason here. ``topic`` is the skill
    name derived from the path; every successful record gets a revision and a
    Git commit through the shared ledger path.
    """
    errors: list[dict[str, Any]] = []
    if not str(actor or "").strip():
        errors.append({"field": "actor", "kind": "acl", "code": "missing_actor"})
    if not str(role or "").strip():
        errors.append({"field": "role", "kind": "acl", "code": "missing_role"})
    if not str(skill_path or "").strip():
        errors.append({"field": "skill_path", "kind": "contract", "code": "missing_skill_path"})
    digest = str(skill_hash or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors.append({"field": "skill_hash", "kind": "contract", "code": "invalid_skill_hash"})
    reason = str(selection_reason or "").strip()
    if not reason:
        errors.append({"field": "selection_reason", "kind": "contract", "code": "missing_selection_reason"})
    elif len(reason) > 200:
        errors.append({"field": "selection_reason", "kind": "contract", "code": "selection_reason_too_long"})
    if errors:
        return {"schema": LEDGER_SCHEMA, "kind": "capability", "ok": False, "errors": errors}
    topic = Path(str(skill_path)).name or "skill"
    topic_error = _topic_gate(topic)
    if topic_error:
        return {"schema": LEDGER_SCHEMA, "kind": "capability", "ok": False, "errors": [{"field": "topic", "kind": "contract", "code": topic_error}]}
    metadata = {
        "actor": str(actor).strip(),
        "role": str(role).strip(),
        "authority": str(authority).strip().lower(),
        "write_set": sorted(str(item).strip() for item in write_set if str(item).strip()),
        "skill_path": str(skill_path).strip(),
        "skill_hash": digest,
        "selection_reason": reason,
    }
    return domain_ledger_write(
        kind="capability",
        operation="create",
        topic=topic,
        content="skill-load-record",
        actor=str(actor).strip(),
        authority=str(authority).strip().lower(),
        write_set=[str(item).strip() for item in write_set if str(item).strip()],
        root=root,
        idempotency_key=idempotency_key,
        metadata=metadata,
    )


def domain_gbrain_recall(query: str, limit: int = 10) -> dict[str, Any]:
    """GBrain recall through the shared query layer (read-only, idempotent).

    Uses the same GBrain-first/fallback selection as ``shiguan.query`` and
    returns a metadata projection without pending/private bodies.
    """
    bounded = max(1, min(int(limit), 50))
    term = str(query or "").strip()
    if not term:
        return {"schema": "court.gbrain_recall.result.v1", "ok": False, "errors": [{"field": "query", "kind": "contract", "code": "empty_query"}]}
    try:
        from query_shiguan_index import load_entries, select_query_matches
        from court_public_api import SHIGUAN_ENTRY_PROJECTION_FIELDS, _metadata_projection

        entries = load_entries()
        matches = select_query_matches(entries, [term])
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return {"schema": "court.gbrain_recall.result.v1", "ok": False, "errors": [{"field": "query", "kind": "runtime", "code": str(exc)}]}
    projection = [_metadata_projection(entry) for entry in matches[:bounded]]
    return {"schema": "court.gbrain_recall.result.v1", "ok": True, "errors": [], "entries": projection, "count": len(projection)}


def domain_court_code_preview(topic: str, date_text: str | None = None) -> dict[str, Any]:
    """Preview the unified court_code generator without writing (read-only).

    The preview reuses the archive-checkpoint numbering functions so any caller
    sees exactly what the authoritative generator would produce; it never
    assigns or persists a code.
    """
    from datetime import date

    try:
        from archive_checkpoint import next_daily_sequence

        selected_date = date_text or date.today().strftime("%Y%m%d")
        archive = reference_path("plan-archives")
        index = archive / "index.json"
        from pathlib import Path as _P

        if _P(index).exists():
            sequence = next_daily_sequence(index, selected_date)
        else:
            sequence = "1"
    except (ImportError, OSError, TypeError, ValueError) as exc:
        return {"schema": "court.court_code_preview.result.v1", "ok": False, "errors": [{"field": "topic", "kind": "runtime", "code": str(exc)}]}
    return {"schema": "court.court_code_preview.result.v1", "ok": True, "errors": [], "topic": str(topic), "date": selected_date, "daily_sequence": sequence, "preview_only": True}
