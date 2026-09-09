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
- Every successful write appends a revision plus a committed receipt sidecar in
  one path-scoped Git commit. The response-only ``git_commit`` is resolved from
  that immutable sidecar, avoiding an impossible self-referential Git SHA in
  the committed ledger blob; pre-commit failures restore file and index bytes.
- Read returns a metadata projection without raw content for pending/private
  scopes.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
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
GIT_RECEIPT_SCHEMA = "court.domain_ledger.git_receipt.v1"
GIT_TIMEOUT_SECONDS = 30


def default_ledger_root() -> Path:
    """Resolve the shared court-runtime root (read-only resolution)."""
    return reference_path("court-runtime")


def ledger_file(root: Path, kind: str) -> Path:
    return Path(root) / "domain-ledger" / f"{kind}.json"


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


def _git_run(
    root: Path,
    *args: str,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run one Git command rooted at the ledger repository.

    Keeping this adapter narrow makes the transaction's write surface auditable:
    only the caller-supplied pathspecs reach ``git add`` or ``git commit``.
    """
    command = ["git", "-C", str(root), *args]
    subcommand = args[0] if args else "git"
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"domain_ledger_git_failed:{subcommand}:{str(exc)[:200]}") from exc
    if result.returncode != 0 and not allow_failure:
        detail = (result.stderr or result.stdout or "").strip()[:200]
        raise ValueError(f"domain_ledger_git_failed:{subcommand}:{detail}")
    return result


def _ledger_transaction_lock_path(root: Path) -> Path:
    """Resolve a persistent transaction lock inside this repository's Git dir."""
    inside = _git_run(root, "rev-parse", "--is-inside-work-tree").stdout.strip().lower()
    if inside != "true":
        raise ValueError("domain_ledger_git_root_invalid")
    top_level = Path(_git_run(root, "rev-parse", "--show-toplevel").stdout.strip())
    if top_level.resolve() != root.resolve():
        raise ValueError("domain_ledger_git_root_mismatch")
    raw_path = _git_run(root, "rev-parse", "--git-path", "domain-ledger.transaction.lock").stdout.strip()
    if not raw_path:
        raise ValueError("domain_ledger_git_lock_path_missing")
    path = Path(raw_path)
    return path if path.is_absolute() else root / path


def _git_index_path(root: Path) -> Path:
    raw_path = _git_run(root, "rev-parse", "--git-path", "index").stdout.strip()
    if not raw_path:
        raise ValueError("domain_ledger_git_index_path_missing")
    path = Path(raw_path)
    return path if path.is_absolute() else root / path


def _git_head(root: Path) -> str | None:
    """Return HEAD when present; an unborn but valid repository has no HEAD."""
    result = _git_run(root, "rev-parse", "--verify", "HEAD", allow_failure=True)
    if result.returncode == 0:
        value = result.stdout.strip()
        if re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
            return value
        raise ValueError("domain_ledger_git_head_invalid")
    if result.returncode == 128:
        return None
    detail = (result.stderr or result.stdout or "").strip()[:200]
    raise ValueError(f"domain_ledger_git_failed:rev-parse:{detail}")


def _relative_ledger_path(root: Path, relative: str) -> Path:
    """Return a checked ledger-relative path without accepting traversal."""
    parsed = PurePosixPath(relative)
    if not relative or parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError("domain_ledger_relative_path_invalid")
    candidate = root.joinpath(*parsed.parts)
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("domain_ledger_relative_path_escape") from exc
    return candidate


def _assert_ledger_target_clean(root: Path, path: Path, relative: str) -> None:
    """Refuse to overwrite a user-modified ledger target.

    Unrelated staged paths are intentionally allowed.  The managed ledger file
    itself must start clean so a transaction never replaces a user's local
    staged or working-copy revision.
    """
    tracked = _git_run(root, "ls-files", "--error-unmatch", "--", relative, allow_failure=True)
    if tracked.returncode not in {0, 1}:
        detail = (tracked.stderr or tracked.stdout or "").strip()[:200]
        raise ValueError(f"domain_ledger_git_failed:ls-files:{detail}")
    if path.exists() and tracked.returncode != 0:
        raise ValueError("domain_ledger_target_untracked")
    for label, arguments in (
        ("worktree", ("diff", "--quiet", "--", relative)),
        ("index", ("diff", "--cached", "--quiet", "--", relative)),
    ):
        result = _git_run(root, *arguments, allow_failure=True)
        if result.returncode == 0:
            continue
        if result.returncode == 1:
            raise ValueError(f"domain_ledger_target_dirty:{label}")
        detail = (result.stderr or result.stdout or "").strip()[:200]
        raise ValueError(f"domain_ledger_git_failed:diff:{detail}")


def _snapshot_file(path: Path) -> tuple[bool, bytes]:
    return (True, path.read_bytes()) if path.exists() else (False, b"")


def _atomic_write_bytes(path: Path, value: bytes) -> None:
    """Atomically restore the binary Git index without reconstructing it."""
    from court_file_lock import fsync_parent_directory

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(
        prefix=f".{target.name}.domain-ledger-",
        suffix=".tmp",
        dir=str(target.parent),
    )
    temporary = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        fsync_parent_directory(target.parent)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _restore_file_preimage(path: Path, preimage: tuple[bool, bytes]) -> None:
    existed, value = preimage
    if existed:
        _atomic_write_text(path, value.decode("utf-8"))
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _restore_index_preimage(path: Path, preimage: tuple[bool, bytes]) -> None:
    existed, value = preimage
    if existed:
        _atomic_write_bytes(path, value)
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _rollback_transaction(
    root: Path,
    *,
    before_head: str | None,
    index_path: Path,
    index_preimage: tuple[bool, bytes],
    ledger_path: Path,
    ledger_preimage: tuple[bool, bytes],
    receipt_path: Path,
    receipt_preimage: tuple[bool, bytes],
) -> list[str]:
    """Restore all pre-commit mutable surfaces when HEAD has not advanced."""
    try:
        if _git_head(root) != before_head:
            return ["head_changed_during_failed_transaction"]
    except (OSError, ValueError):
        return ["head_state_unavailable_during_failed_transaction"]
    failures: list[str] = []
    for label, restore in (
        ("ledger", lambda: _restore_file_preimage(ledger_path, ledger_preimage)),
        ("receipt", lambda: _restore_file_preimage(receipt_path, receipt_preimage)),
        ("index", lambda: _restore_index_preimage(index_path, index_preimage)),
    ):
        try:
            restore()
        except (OSError, UnicodeError, ValueError) as exc:
            failures.append(f"{label}:{str(exc)[:120]}")
    return failures


def _receipt_relative_path(kind: str, transaction_id: str) -> str:
    return f"domain-ledger/receipts/{kind}-{transaction_id}.json"


def _git_show_text(root: Path, commit_sha: str, relative: str) -> str | None:
    result = _git_run(root, "show", f"{commit_sha}:{relative}", allow_failure=True)
    return result.stdout if result.returncode == 0 else None


def _receipt_commit_proves_record(
    root: Path,
    *,
    commit_sha: str,
    record: dict[str, Any],
    receipt_relative_path: str,
    ledger_relative_path: str,
    transaction_id: str,
) -> bool:
    """Require the original commit to introduce a receipt and its ledger row."""
    receipt_text = _git_show_text(root, commit_sha, receipt_relative_path)
    ledger_text = _git_show_text(root, commit_sha, ledger_relative_path)
    if receipt_text is None or ledger_text is None:
        return False
    try:
        receipt = json.loads(receipt_text)
        ledger = json.loads(ledger_text)
    except json.JSONDecodeError:
        return False
    if (
        receipt.get("schema") != GIT_RECEIPT_SCHEMA
        or receipt.get("transaction_id") != transaction_id
        or receipt.get("ledger_path") != ledger_relative_path
        or receipt.get("revision") != record.get("revision")
    ):
        return False
    revisions = ledger.get("revisions") if isinstance(ledger, dict) else None
    matching = [
        item
        for item in revisions or []
        if isinstance(item, dict)
        and isinstance(item.get("git_receipt"), dict)
        and item["git_receipt"].get("transaction_id") == transaction_id
        and item["git_receipt"].get("path") == receipt_relative_path
    ]
    if len(matching) != 1:
        return False
    candidate = matching[0]
    for field in ("revision", "topic", "operation", "actor", "authority", "write_set", "idempotency_key"):
        if candidate.get(field) != record.get(field):
            return False
    parents = _git_run(root, "show", "-s", "--format=%P", commit_sha).stdout.strip().split()
    if parents:
        parent_ledger_text = _git_show_text(root, parents[0], ledger_relative_path)
        if parent_ledger_text is not None:
            try:
                parent_ledger = json.loads(parent_ledger_text)
            except json.JSONDecodeError:
                return False
            for item in parent_ledger.get("revisions") or []:
                if isinstance(item, dict) and isinstance(item.get("git_receipt"), dict) and item["git_receipt"].get("transaction_id") == transaction_id:
                    return False
    changed = _git_run(root, "diff-tree", "--root", "--no-commit-id", "-r", "--name-status", commit_sha).stdout.splitlines()
    changed_paths = {
        line.split("\t", 1)[1]: line.split("\t", 1)[0]
        for line in changed
        if "\t" in line
    }
    return (
        changed_paths.get(receipt_relative_path) == "A"
        and changed_paths.get(ledger_relative_path) in {"A", "M"}
    )


def _record_git_commit(root: Path, record: dict[str, Any]) -> str | None:
    """Recover only the original transaction commit from a receipt sidecar."""
    legacy = record.get("git_commit")
    if isinstance(legacy, str) and legacy.strip():
        return legacy.strip()
    receipt = record.get("git_receipt")
    if not isinstance(receipt, dict):
        return None
    relative = receipt.get("path")
    ledger_relative = receipt.get("ledger_path")
    transaction_id = receipt.get("transaction_id")
    if (
        not isinstance(relative, str)
        or not relative.startswith("domain-ledger/receipts/")
        or not isinstance(ledger_relative, str)
        or not ledger_relative.startswith("domain-ledger/")
        or not isinstance(transaction_id, str)
        or not transaction_id
    ):
        return None
    try:
        _relative_ledger_path(root, relative)
        _relative_ledger_path(root, ledger_relative)
        result = _git_run(root, "log", "--format=%H", "--", relative, allow_failure=True)
    except (OSError, ValueError):
        return None
    if result.returncode != 0:
        return None
    for value in result.stdout.splitlines():
        if re.fullmatch(r"[0-9a-fA-F]{40,64}", value) and _receipt_commit_proves_record(
            root,
            commit_sha=value,
            record=record,
            receipt_relative_path=relative,
            ledger_relative_path=ledger_relative,
            transaction_id=transaction_id,
        ):
            return value
    return None


def _record_with_git_commit(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    projected = dict(record)
    commit_sha = _record_git_commit(root, projected)
    if commit_sha:
        projected["git_commit"] = commit_sha
    return projected


def _commit_receipt_text(
    *,
    transaction_id: str,
    kind: str,
    revision: int,
    ledger_relative_path: str,
    parent_commit: str | None,
) -> str:
    """Build a durable receipt before committing, avoiding a self-referential SHA."""
    receipt = {
        "schema": GIT_RECEIPT_SCHEMA,
        "transaction_id": transaction_id,
        "kind": kind,
        "revision": revision,
        "ledger_path": ledger_relative_path,
        "parent_commit": parent_commit,
    }
    return json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _git_commit(root: Path, message: str, paths: list[str]) -> str:
    """Commit only this transaction's exact paths, preserving other staging."""
    if not paths:
        raise ValueError("domain_ledger_git_paths_missing")
    _git_run(root, "add", "--", *paths)
    _git_run(root, "commit", "--only", "-q", "-m", message, "--", *paths)
    commit_sha = _git_run(root, "rev-parse", "--verify", "HEAD").stdout.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit_sha):
        raise ValueError("domain_ledger_git_commit_missing")
    return commit_sha


def _verify_committed_receipt(
    root: Path,
    *,
    commit_sha: str,
    ledger_relative_path: str,
    ledger_text: str,
    receipt_relative_path: str,
    receipt_text: str,
    transaction_id: str,
    revision: int,
) -> None:
    """Require committed, index, and worktree copies to agree before success."""
    for relative, expected, label in (
        (ledger_relative_path, ledger_text, "ledger"),
        (receipt_relative_path, receipt_text, "receipt"),
    ):
        actual = _git_run(root, "show", f"{commit_sha}:{relative}").stdout
        if actual != expected:
            raise ValueError(f"domain_ledger_commit_receipt_{label}_blob_mismatch")
    try:
        receipt = json.loads(receipt_text)
    except json.JSONDecodeError as exc:  # pragma: no cover - generated above
        raise ValueError("domain_ledger_commit_receipt_invalid") from exc
    if (
        receipt.get("transaction_id") != transaction_id
        or receipt.get("ledger_path") != ledger_relative_path
        or receipt.get("revision") != revision
    ):
        raise ValueError("domain_ledger_commit_receipt_mismatch")
    for label, arguments in (
        ("worktree", ("diff", "--quiet", commit_sha, "--", ledger_relative_path, receipt_relative_path)),
        ("index", ("diff", "--cached", "--quiet", commit_sha, "--", ledger_relative_path, receipt_relative_path)),
    ):
        result = _git_run(root, *arguments, allow_failure=True)
        if result.returncode == 0:
            continue
        if result.returncode == 1:
            raise ValueError(f"domain_ledger_commit_receipt_{label}_mismatch")
        detail = (result.stderr or result.stdout or "").strip()[:200]
        raise ValueError(f"domain_ledger_git_failed:diff:{detail}")


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
    selected_root = Path(root or default_ledger_root())
    try:
        ledger = _load_ledger(ledger_file(selected_root, kind))
    except (OSError, ValueError) as exc:
        return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": False, "errors": [{"field": "root", "kind": "runtime", "code": str(exc)}]}
    revisions = [
        {
            "revision": item.get("revision"),
            "operation": item.get("operation"),
            "topic": item.get("topic"),
            "idempotency_key": item.get("idempotency_key"),
            "transaction_id": (
                item["git_receipt"].get("transaction_id")
                if isinstance(item.get("git_receipt"), dict)
                else None
            ),
            "receipt_path": (
                item["git_receipt"].get("path")
                if isinstance(item.get("git_receipt"), dict)
                else None
            ),
            "actor": item.get("actor"),
            "authority": item.get("authority"),
            "write_set": item.get("write_set"),
            "git_commit": _record_with_git_commit(selected_root, item).get("git_commit"),
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
    """Authorized Create/Update with a locked, receipt-bound Git transaction.

    ``metadata`` is an optional structured summary (actor/role/write_set/skill
    selection etc.) stored verbatim in the ledger record; it must be
    JSON-serializable and is subject to the same privacy discipline as the
    rest of the ledger (no raw pending/private bodies).  The returned record
    retains ``git_commit`` compatibility; its durable ``git_receipt`` locator
    is committed with the ledger because an in-tree file cannot contain the
    SHA of the very commit that hashes that file.
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

    if metadata is not None:
        if not isinstance(metadata, dict):
            return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": False, "errors": [{"field": "metadata", "kind": "contract", "code": "metadata_must_be_object"}]}
        try:
            json.dumps(metadata, ensure_ascii=False)
        except (TypeError, ValueError):
            return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": False, "errors": [{"field": "metadata", "kind": "contract", "code": "metadata_not_serializable"}]}

    selected_root = Path(root or default_ledger_root()).resolve()
    ledger_relative_path = f"domain-ledger/{kind}.json"
    normalized_idempotency_key = str(idempotency_key).strip() if idempotency_key else None
    try:
        lock_path = _ledger_transaction_lock_path(selected_root)
        from court_file_lock import file_lock

        with file_lock(lock_path, timeout=30.0, poll_interval=0.02):
            path = _relative_ledger_path(selected_root, ledger_relative_path)
            _assert_ledger_target_clean(selected_root, path, ledger_relative_path)
            ledger = _load_ledger(path)
            revisions = ledger.get("revisions", [])
            if not isinstance(revisions, list):
                raise ValueError("domain_ledger_corrupt")

            # Re-check idempotency only after acquiring the shared transaction lock.
            existing = [item for item in reversed(revisions) if isinstance(item, dict) and item.get("topic") == topic]
            if operation == "create" and existing:
                return {
                    "schema": LEDGER_SCHEMA,
                    "kind": kind,
                    "ok": True,
                    "errors": [],
                    "idempotent": True,
                    "record": _record_with_git_commit(selected_root, existing[0]),
                }
            if operation == "update" and normalized_idempotency_key:
                for item in reversed(revisions):
                    if item.get("topic") == topic and item.get("idempotency_key") == normalized_idempotency_key:
                        return {
                            "schema": LEDGER_SCHEMA,
                            "kind": kind,
                            "ok": True,
                            "errors": [],
                            "idempotent": True,
                            "record": _record_with_git_commit(selected_root, item),
                        }

            import uuid
            from datetime import datetime, timezone

            revision = len(revisions) + 1
            transaction_id = uuid.uuid4().hex
            receipt_relative_path = _receipt_relative_path(kind, transaction_id)
            receipt_path = _relative_ledger_path(selected_root, receipt_relative_path)
            payload: dict[str, Any] = {
                "schema": LEDGER_SCHEMA,
                "revision": revision,
                "operation": operation,
                "topic": topic,
                "actor": str(actor).strip(),
                "authority": str(authority).strip().lower(),
                "write_set": sorted(str(item).strip() for item in write_set if str(item).strip()),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "git_receipt": {
                    "schema": GIT_RECEIPT_SCHEMA,
                    "transaction_id": transaction_id,
                    "path": receipt_relative_path,
                    "ledger_path": ledger_relative_path,
                },
            }
            if normalized_idempotency_key:
                payload["idempotency_key"] = normalized_idempotency_key
            if metadata is not None:
                payload["metadata"] = metadata
            ledger["revisions"] = [*revisions, payload]
            ledger_text = json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            before_head = _git_head(selected_root)
            receipt_text = _commit_receipt_text(
                transaction_id=transaction_id,
                kind=kind,
                revision=revision,
                ledger_relative_path=ledger_relative_path,
                parent_commit=before_head,
            )
            index_path = _git_index_path(selected_root)
            index_preimage = _snapshot_file(index_path)
            ledger_preimage = _snapshot_file(path)
            receipt_preimage = _snapshot_file(receipt_path)
            failure_stage = "ledger_persist"
            try:
                _atomic_write_text(path, ledger_text)
                failure_stage = "receipt_persist"
                _atomic_write_text(receipt_path, receipt_text)
                failure_stage = "git_commit"
                commit_sha = _git_commit(
                    selected_root,
                    f"domain-ledger: {kind} {operation} {topic}",
                    [ledger_relative_path, receipt_relative_path],
                )
            except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
                rollback_failures = _rollback_transaction(
                    selected_root,
                    before_head=before_head,
                    index_path=index_path,
                    index_preimage=index_preimage,
                    ledger_path=path,
                    ledger_preimage=ledger_preimage,
                    receipt_path=receipt_path,
                    receipt_preimage=receipt_preimage,
                )
                code = str(exc)
                if failure_stage == "receipt_persist":
                    code = f"commit_receipt_persist_failed:{code}"
                elif failure_stage == "ledger_persist":
                    code = f"ledger_persist_failed:{code}"
                if rollback_failures:
                    code += ";rollback_failed:" + ",".join(rollback_failures)
                return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": False, "errors": [{"field": "git", "kind": "runtime", "code": code}]}
            try:
                _verify_committed_receipt(
                    selected_root,
                    commit_sha=commit_sha,
                    ledger_relative_path=ledger_relative_path,
                    ledger_text=ledger_text,
                    receipt_relative_path=receipt_relative_path,
                    receipt_text=receipt_text,
                    transaction_id=transaction_id,
                    revision=revision,
                )
            except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
                return {
                    "schema": LEDGER_SCHEMA,
                    "kind": kind,
                    "ok": False,
                    "errors": [{"field": "git", "kind": "runtime", "code": f"commit_receipt_inconsistent:{commit_sha}:{exc}"}],
                }
            record = dict(ledger["revisions"][-1])
            record["git_commit"] = commit_sha
            return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": True, "errors": [], "record": record}
    except (OSError, ValueError, UnicodeError, TimeoutError, subprocess.TimeoutExpired) as exc:
        return {"schema": LEDGER_SCHEMA, "kind": kind, "ok": False, "errors": [{"field": "root", "kind": "runtime", "code": str(exc)}]}


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
    from shiguan_gbrain import build_leaves, full_record_pointer

    projection: list[dict[str, Any]] = []
    for entry in matches[:bounded]:
        item = _metadata_projection(entry)
        item["full_record"] = full_record_pointer(entry)
        item["leaves"] = build_leaves(entries, entry, limit=6)
        projection.append(item)
    return {"schema": "court.gbrain_recall.result.v1", "ok": True, "errors": [], "entries": projection, "count": len(projection)}


def domain_court_code_preview(
    topic: str,
    date_text: str | None = None,
    index_path: Path | None = None,
) -> dict[str, Any]:
    """Preview the unified court_code generator without writing (read-only).

    The preview reuses the archive-checkpoint numbering functions so any caller
    sees exactly what the authoritative generator would produce; it never
    assigns or persists a code. The returned ``generator`` / ``authority`` /
    ``receipt_hint`` fields make the numbering source traceable to the unified
    archive-checkpoint generator (single authority, no second numbering set).

    ``index_path`` overrides the plan-archive index for read-only probes; it
    must point at an existing file or the caller gets a deterministic error.
    """
    from datetime import date

    try:
        from archive_checkpoint import next_daily_sequence

        selected_date = date_text or date.today().strftime("%Y%m%d")
        if index_path is not None:
            index = Path(str(index_path))
        else:
            index = reference_path("plan-archives") / "index.json"
        if index.exists():
            sequence = next_daily_sequence(index, selected_date)
        else:
            sequence = "1"
    except (ImportError, OSError, TypeError, ValueError) as exc:
        return {"schema": "court.court_code_preview.result.v1", "ok": False, "errors": [{"field": "topic", "kind": "runtime", "code": str(exc)}]}
    return {
        "schema": "court.court_code_preview.result.v1",
        "ok": True,
        "errors": [],
        "topic": str(topic),
        "date": selected_date,
        "daily_sequence": sequence,
        "preview_only": True,
        "generator": "archive_checkpoint.next_daily_sequence",
        "authority": "unified_court_code_generator",
        "receipt_hint": "court.shiguan_archive_checkpoint_receipt.v1",
    }
