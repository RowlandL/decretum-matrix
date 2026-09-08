

#!/usr/bin/env python
"""Independent Shiguan autosync loop, not dependent on Hermes cron."""

from __future__ import annotations

# A+B layering: real module lives in scripts/services/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


from datetime import datetime
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

sys.dont_write_bytecode = True

from shiguan_paths import (
    code_root,
    default_obsidian_cache_vault,
    default_obsidian_inbox,
    ensure_shared_seed,
    reference_path,
    references_root,
    shared_root,
)
from court_file_lock import atomic_write_text, file_lock
from obsidian_config_state import config_lock_path, read_config_snapshot


TEXT_SUFFIXES = {".md", ".txt"}
EXCLUDED_DIRS = {".obsidian", ".trash"}
MAX_WATCH_ROOTS = 8
SYNC_MANIFEST_NAME = ".court-shiguan-sync-manifest.json"
SYNC_MANIFEST_SCHEMA = "court.shiguan.sync-manifest.v2"
LEGACY_SYNC_MANIFEST_SCHEMA = "court.shiguan.sync-manifest.v1"
PENDING_METADATA_SUFFIX = ".metadata.json"
MAX_CYCLE_FRESH_SECONDS = 1260


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: object) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


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


def sync_config() -> dict[str, object]:
    return read_config_snapshot()


def state_path() -> Path:
    return reference_path("obsidian-sync", "autosync-state.json")


def status_path() -> Path:
    return reference_path("obsidian-sync", "autosync-daemon.json")


def refresh_request_path() -> Path:
    return reference_path("obsidian-sync", "refresh-request.json")


def pending_root() -> Path:
    return reference_path("shiguan-imports", "pending")


def autosync_cycle_lock_path() -> Path:
    return reference_path("court-runtime", "obsidian-autosync-cycle.lock")


def estimate_tokens(text: str) -> int:
    cjk_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    non_cjk_count = max(0, len(text) - cjk_count)
    return max(1, int(cjk_count * 0.8 + non_cjk_count / 4 + 120))


def path_is_same_or_ancestor(candidate: Path, protected: Path) -> bool:
    return candidate == protected or candidate in protected.parents


def validate_watch_root(value: object) -> Path:
    raw = Path(str(value or "").strip()).expanduser()
    if not raw.is_absolute():
        raise ValueError("Obsidian watch root must be an absolute path")
    resolved = raw.resolve()
    if resolved == Path(resolved.anchor):
        raise ValueError("Obsidian watch root cannot be a drive or filesystem root")
    home = Path.home().resolve()
    if path_is_same_or_ancestor(resolved, home):
        raise ValueError("Obsidian watch root cannot be the user home or its ancestor")
    dedicated_ingress = default_obsidian_inbox().resolve()
    for protected in (code_root().resolve(), shared_root().resolve()):
        if resolved == dedicated_ingress and protected == shared_root().resolve():
            continue
        if path_is_same_or_ancestor(resolved, protected) or protected in resolved.parents:
            raise ValueError("Obsidian watch root cannot cover skill/shared data")
    return resolved


def configured_cache_vault(config: dict[str, object]) -> Path:
    return validate_watch_root(
        config.get("cache_vault_path")
        or config.get("vault_path")
        or default_obsidian_cache_vault()
    )


def configured_watch_roots(config: dict[str, object]) -> list[Path]:
    raw = config.get("watch_paths")
    if isinstance(raw, list):
        candidates = [item for item in raw if str(item).strip()]
    else:
        candidates = [configured_cache_vault(config), default_obsidian_inbox().resolve()]
    if len(candidates) > MAX_WATCH_ROOTS:
        raise ValueError(f"Obsidian watch_paths supports at most {MAX_WATCH_ROOTS} roots")
    roots = [validate_watch_root(item) for item in candidates]
    output: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(root)
    return output


def is_watchable_file(path: Path, root: Path) -> bool:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return False
    return True


def snapshot_roots(roots: list[Path]) -> dict[str, dict[str, object]]:
    snapshot: dict[str, dict[str, object]] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or not is_watchable_file(path, root):
                continue
            rel = path.relative_to(root).as_posix()
            key = f"{root}|{rel}"
            stat = path.stat()
            snapshot[key] = {
                "root": str(root),
                "rel": rel,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "observation_state": "UNVERIFIED",
                "source_ref": f"filesystem://{root}/{rel}",
                "source_revision": "UNKNOWN",
            }
    return snapshot


def _normalized_refs(value: object) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for rel, raw in value.items():
        rel_text = str(rel).replace("\\", "/").strip()
        if not rel_text:
            continue
        if isinstance(raw, str) and raw.strip():
            result[rel_text] = {"source_ref": raw.strip()}
            continue
        if not isinstance(raw, dict):
            continue
        reference = {
            key: str(raw[key]).strip()
            for key in ("source_ref", "source_revision", "transaction_id")
            if str(raw.get(key) or "").strip()
        }
        if reference:
            result[rel_text] = reference
    return result


def managed_sync_refs(cache_vault: Path) -> dict[str, dict[str, str]]:
    value = read_json(cache_vault / SYNC_MANIFEST_NAME, {})
    if not isinstance(value, dict) or value.get("schema") != SYNC_MANIFEST_SCHEMA:
        return {}
    if value.get("state") not in {"applying", "committed", "conflict"}:
        return {}
    if value.get("state") == "applying":
        return _normalized_refs(value.get("previous_refs"))
    return _normalized_refs(value.get("applied_refs"))


def managed_sync_hashes(cache_vault: Path) -> dict[str, dict[str, str]]:
    """Compatibility alias; returns references, never body hashes."""
    return managed_sync_refs(cache_vault)


def pending_metadata_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}{PENDING_METADATA_SUFFIX}")


def existing_pending_reference(
    pending: Path,
    *,
    source_revision: str,
    source_ref: str,
    transaction_id: str,
) -> tuple[str, Path] | None:
    """Find a prior v2 sidecar using metadata only, never its body."""
    if not pending.is_dir() or pending.is_symlink():
        return None
    try:
        candidates = sorted(pending.glob(f"*{PENDING_METADATA_SUFFIX}"))
    except OSError:
        return None
    for candidate in candidates:
        metadata = read_json(candidate, {})
        if not isinstance(metadata, dict):
            continue
        if (
            metadata.get("schema") == "court.shiguan.pending-import.v2"
            and metadata.get("source_revision") == source_revision
            and metadata.get("source_ref") == source_ref
            and metadata.get("transaction_id") == transaction_id
        ):
            return str(metadata.get("id") or ""), candidate
    return None


def snapshot_item_matches_root(item: dict[str, object], root: Path) -> bool:
    candidate = Path(str(item.get("root") or ""))
    try:
        return candidate.resolve() == root.resolve()
    except OSError:
        return candidate.absolute() == root.absolute()


def queue_pending_file(
    path: Path,
    root: Path,
    rel: str,
    source_revision: str = "",
    source_ref: str = "",
    transaction_id: str = "",
    reason: str = "unknown",
) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="replace")
    normalized_revision = str(source_revision or "").strip() or "UNKNOWN"
    normalized_ref = str(source_ref or "").strip() or f"filesystem://{root}/{rel}"
    normalized_transaction = str(transaction_id or "").strip() or uuid.uuid4().hex
    pending = pending_root()
    if pending.exists() and (pending.is_symlink() or not pending.is_dir()):
        return {
            "queued": False,
            "conflict": True,
            "reason": "pending_root_unusable",
            "path": str(path),
            "rel": rel,
        }
    prior = existing_pending_reference(
        pending,
        source_revision=normalized_revision,
        source_ref=normalized_ref,
        transaction_id=normalized_transaction,
    )
    if prior is not None and prior[0]:
        return {
            "queued": False,
            "duplicate": True,
            "id": prior[0],
            "path": str(path),
            "rel": rel,
            "metadata_sidecar": str(prior[1]),
            "metadata_repaired": False,
        }
    import_id = "IMP-" + uuid.uuid4().hex.upper()
    target = pending_root() / f"{import_id}.json"
    record = {
        "schema": "court.shiguan.pending-import.v2",
        "id": import_id,
        "filename": Path(rel).name,
        "source_type": path.suffix.lower().lstrip("."),
        "status": "pending",
        "imported_at": now_text(),
        "char_count": len(text),
        "estimated_tokens": estimate_tokens(text),
        "source_revision": normalized_revision,
        "source_ref": normalized_ref,
        "transaction_id": normalized_transaction,
        "verification_state": "UNVERIFIED",
        "suggested_processor": "codex",
        "source": f"obsidian-autosync:{root}:{rel}",
        "reason": reason,
        "text": text,
    }
    metadata = {
        key: record[key]
        for key in (
            "schema",
            "id",
            "filename",
            "source_type",
            "status",
            "imported_at",
            "char_count",
            "estimated_tokens",
            "source_revision",
            "source_ref",
            "transaction_id",
            "verification_state",
            "suggested_processor",
        )
    }
    # The sidecar is the commit marker for the generated pending body.  Its
    # filename binds that queue object; the original Obsidian name remains in
    # the body record and source provenance.
    metadata["filename"] = target.name
    pending.mkdir(parents=True, exist_ok=True)
    metadata_path = pending_metadata_path(target)
    if not target.exists():
        write_json(target, record)
        write_json(metadata_path, metadata)
        return {
            "queued": True,
            "id": import_id,
            "path": str(path),
            "rel": rel,
            "tokens": record["estimated_tokens"],
            "metadata_sidecar": str(metadata_path),
        }
    existing_metadata = read_json(metadata_path, {})
    if (
        isinstance(existing_metadata, dict)
        and existing_metadata.get("schema") == "court.shiguan.pending-import.v2"
        and existing_metadata.get("source_ref") == normalized_ref
        and existing_metadata.get("source_revision") == normalized_revision
        and existing_metadata.get("transaction_id") == normalized_transaction
    ):
        return {
            "queued": False,
            "duplicate": True,
            "id": str(existing_metadata.get("id") or import_id),
            "path": str(path),
            "rel": rel,
            "metadata_sidecar": str(metadata_path),
            "metadata_repaired": False,
        }
    repaired = (
        not isinstance(existing_metadata, dict)
        or "text" in existing_metadata
        or "raw_text" in existing_metadata
        or any(existing_metadata.get(key) != value for key, value in metadata.items())
    )
    if repaired:
        write_json(metadata_path, metadata)
    return {
        "queued": False,
        "duplicate": True,
        "id": import_id,
        "path": str(path),
        "rel": rel,
        "metadata_sidecar": str(metadata_path),
        "metadata_repaired": repaired,
    }


def queue_vault_changes(
    before: dict[str, dict[str, object]],
    after: dict[str, dict[str, object]],
    first_run: bool,
    cache_vault: Path | None = None,
    generated_refs: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    queued: list[dict[str, object]] = []
    for key, current in sorted(after.items()):
        previous = before.get(key)
        root = Path(str(current["root"]))
        rel = str(current["rel"])
        path = root / rel
        normalized_rel = rel.replace("\\", "/")
        managed_cache = False
        if cache_vault is not None:
            try:
                managed_cache = root.resolve() == cache_vault.resolve()
            except OSError:
                managed_cache = root.absolute() == cache_vault.absolute()
        generated_ref = (generated_refs or {}).get(normalized_rel)
        if (
            managed_cache
            and generated_ref
            and current.get("observation_state") == "MANAGED"
            and _reference_matches(current, generated_ref)
        ):
            queued.append(
                {
                    "queued": False,
                    "skipped": True,
                    "reason": "managed_sync_output",
                    "path": str(path),
                    "rel": rel,
                }
            )
            continue
        if previous and _stat_tuple(previous) == _stat_tuple(current):
            # Same size/mtime is not proof that an external editor did not
            # change the bytes.  Preserve the target and surface uncertainty.
            queued.append(
                {
                    "queued": False,
                    "conflict": True,
                    "reason": "unverifiable_external_change",
                    "path": str(path),
                    "rel": rel,
                }
            )
            continue
        if first_run:
            reason = "bootstrap_untracked"
        else:
            reason = "changed" if previous else "new"
        queued.append(
            queue_pending_file(
                path,
                root,
                rel,
                str(current.get("source_revision") or "UNKNOWN"),
                str(current.get("source_ref") or ""),
                str(current.get("transaction_id") or ""),
                reason,
            )
        )
    return queued


def _stat_tuple(value: dict[str, object]) -> tuple[object, object]:
    return value.get("size"), value.get("mtime_ns")


def _reference_matches(item: dict[str, object], reference: dict[str, str]) -> bool:
    return all(
        not reference.get(key)
        or str(item.get(key) or "") == str(reference.get(key) or "")
        for key in ("source_revision", "source_ref", "transaction_id")
    )


def stat_signature(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"exists": False}
    stat = path.stat()
    return {"exists": True, "mtime_ns": stat.st_mtime_ns, "size": stat.st_size}


def latest_file_signature(root: Path, suffixes: set[str]) -> dict[str, object]:
    if not root.exists():
        return {"exists": False, "count": 0, "latest_mtime_ns": 0}
    count = 0
    latest = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        count += 1
        try:
            latest = max(latest, path.stat().st_mtime_ns)
        except OSError:
            continue
    return {"exists": True, "count": count, "latest_mtime_ns": latest}


def authoritative_source_reference() -> dict[str, str]:
    """Return the latest non-content Shiguan source reference available."""
    refresh = read_json(refresh_request_path(), {})
    if isinstance(refresh, dict):
        transaction_id = str(refresh.get("transaction_id") or "").strip()
        source_revision = str(refresh.get("source_revision") or "").strip()
        source_ref = str(refresh.get("source_ref") or "").strip()
        if transaction_id or source_revision or source_ref:
            return {
                "source_revision": source_revision or "UNKNOWN",
                "source_ref": source_ref or "shiguan://refresh-request",
                "transaction_id": transaction_id,
                "state": "KNOWN" if source_revision and source_ref and transaction_id else "UNKNOWN",
            }
    index = reference_path("shiguan-index.jsonl")
    try:
        lines = [line for line in index.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    except OSError:
        lines = []
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        record_ref = str(entry.get("record_ref") or "").strip()
        court_code = str(entry.get("court_code") or "").strip()
        recorded_at = str(entry.get("time") or "").strip()
        if record_ref or court_code:
            revision = ":".join(item for item in (record_ref, recorded_at) if item)
            transaction_id = str(
                entry.get("transaction_id")
                or entry.get("source_transaction_id")
                or ""
            ).strip()
            return {
                "source_revision": revision or court_code,
                "source_ref": f"shiguan://index/{court_code or record_ref}",
                "transaction_id": transaction_id,
                "state": "KNOWN" if revision and transaction_id else "UNKNOWN",
            }
    return {
        "source_revision": "UNKNOWN",
        "source_ref": "shiguan://unbound",
        "transaction_id": "",
        "state": "UNKNOWN",
    }


def source_signature() -> dict[str, object]:
    source = authoritative_source_reference()
    return {
        "index": stat_signature(reference_path("shiguan-index.jsonl")),
        "memory_index": stat_signature(reference_path("memory-index.jsonl")),
        "refresh_request": stat_signature(refresh_request_path()),
        "manual_tree": latest_file_signature(reference_path("shiguan-tree", "manual"), TEXT_SUFFIXES),
        "config": stat_signature(reference_path("obsidian-sync", "config.json")),
        "source_revision": source["source_revision"],
        "source_ref": source["source_ref"],
        "source_revision_state": source["state"],
        "source_transaction_id": source["transaction_id"],
    }


def run_filesystem_sync(config: dict[str, object], timeout: int = 600) -> dict[str, object]:
    script = Path(__file__).with_name("sync_shiguan_obsidian_vault.py")
    vault = configured_cache_vault(config)
    source = authoritative_source_reference()
    with tempfile.NamedTemporaryFile(prefix="shiguan-sync-result-", suffix=".json", delete=False) as handle:
        result_path = Path(handle.name)
    cmd = [
        background_python(), "-B", str(script), "--vault", str(vault),
        "--source-revision", source["source_revision"],
        "--source-ref", source["source_ref"],
        "--producer-transaction-id", source["transaction_id"],
        "--result-json", str(result_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(Path(__file__).resolve().parents[2]),
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=timeout,
            **hidden_run_kwargs(),
        )
        if proc.returncode != 0:
            detail = proc.stderr or "filesystem sync failed"
            raise RuntimeError(detail[-1200:])
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if isinstance(result, dict):
            result.setdefault("source_revision", source["source_revision"])
            result.setdefault("source_ref", source["source_ref"])
            result.setdefault("producer_transaction_id", source["transaction_id"])
        return result
    finally:
        try:
            result_path.unlink()
        except OSError:
            pass


def _run_once_unlocked(
    snapshot_only: bool = False,
    force_sync: bool = False,
    config_snapshot: dict[str, object] | None = None,
    publish_status: bool = True,
) -> dict[str, object]:
    ensure_shared_seed()
    config = dict(config_snapshot) if isinstance(config_snapshot, dict) else sync_config()
    watch_roots = configured_watch_roots(config)
    previous_state = read_json(state_path(), {})
    previous_snapshot = previous_state.get("snapshot") if isinstance(previous_state, dict) else {}
    if not isinstance(previous_snapshot, dict):
        previous_snapshot = {}
    previous_source_signature = previous_state.get("source_signature") if isinstance(previous_state, dict) else {}
    if not isinstance(previous_source_signature, dict):
        previous_source_signature = {}
    first_run = not bool(previous_snapshot)
    current_source_signature = source_signature()
    source_changed = current_source_signature != previous_source_signature
    cache_vault = configured_cache_vault(config)
    generated_refs = managed_sync_refs(cache_vault)
    before = snapshot_roots(watch_roots)
    defer_cache_bootstrap = bool(first_run and not generated_refs)
    queue_snapshot = (
        {
            key: item
            for key, item in before.items()
            if not snapshot_item_matches_root(item, cache_vault)
        }
        if defer_cache_bootstrap
        else before
    )
    queued = queue_vault_changes(
        previous_snapshot,
        queue_snapshot,
        first_run,
        cache_vault=cache_vault,
        generated_refs=generated_refs,
    )
    source_revision_unknown = current_source_signature.get("source_revision_state") != "KNOWN"
    should_sync = bool(force_sync or first_run or source_changed or source_revision_unknown)
    sync_result: dict[str, object] = {
        "skipped": True,
        "reason": "snapshot_only" if snapshot_only else "source_unchanged",
        "source_changed": source_changed,
        "force_sync": bool(force_sync),
    }
    if not snapshot_only and should_sync:
        sync_result = run_filesystem_sync(config)
        sync_result["source_changed"] = source_changed
        sync_result["force_sync"] = bool(force_sync)
    after = snapshot_roots(watch_roots)
    generated_refs = managed_sync_refs(cache_vault)
    sync_source_revision = str(sync_result.get("source_revision") or "") if isinstance(sync_result, dict) else ""
    sync_source_ref = str(sync_result.get("source_ref") or "") if isinstance(sync_result, dict) else ""
    sync_transaction_id = str(sync_result.get("sync_transaction_id") or "") if isinstance(sync_result, dict) else ""
    if sync_source_revision and sync_source_ref:
        for key, item in after.items():
            if not isinstance(item, dict) or not snapshot_item_matches_root(item, cache_vault):
                continue
            rel = str(item.get("rel") or "").replace("\\", "/")
            if rel in generated_refs or rel == "Auto Sync Status.md":
                item.update(
                    {
                        "observation_state": "MANAGED",
                        "source_revision": sync_source_revision,
                        "source_ref": f"{sync_source_ref}#{rel}",
                        "transaction_id": sync_transaction_id,
                    }
                )
    if defer_cache_bootstrap:
        cache_after = {
            key: item
            for key, item in after.items()
            if snapshot_item_matches_root(item, cache_vault)
        }
        queued.extend(
            queue_vault_changes(
                {},
                cache_after,
                True,
                cache_vault=cache_vault,
                generated_refs=generated_refs,
            )
        )
    conflict_queue_count = 0
    raw_conflicts = sync_result.get("user_modified_conflicts")
    if isinstance(raw_conflicts, list):
        for item in raw_conflicts:
            rel = str(item).replace("\\", "/")
            path = cache_vault / Path(rel)
            if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
                continue
            if any(str(event.get("rel") or "").replace("\\", "/") == rel for event in queued):
                continue
            key = f"{cache_vault}|{rel}"
            current = after.get(key)
            event = queue_pending_file(
                path,
                cache_vault,
                rel,
                str(current.get("source_revision") or "UNKNOWN") if isinstance(current, dict) else "UNKNOWN",
                str(current.get("source_ref") or "") if isinstance(current, dict) else "",
                str(current.get("transaction_id") or "") if isinstance(current, dict) else "",
                "user_modified_conflict",
            )
            event["conflict_preserved"] = True
            queued.append(event)
            conflict_queue_count += 1
    generated_refs = managed_sync_refs(cache_vault)
    state = {
        "updated_at": now_text(),
        "shared_shiguan_root": str(references_root()),
        "cache_vault_path": str(configured_cache_vault(config)),
        "watch_roots": [str(root) for root in watch_roots],
        "snapshot": after,
        "source_signature": current_source_signature,
        "source_revision": current_source_signature.get("source_revision"),
        "source_ref": current_source_signature.get("source_ref"),
        "source_revision_state": current_source_signature.get("source_revision_state"),
        "source_transaction_id": current_source_signature.get("source_transaction_id"),
    }
    write_json(state_path(), state)
    report = {
        "ok": bool(sync_result.get("ok", True)) and not any(
            isinstance(item, dict) and item.get("conflict") is True
            for item in queued
        ),
        "first_run": first_run,
        "queued": queued,
        "queued_count": sum(1 for item in queued if item.get("queued")),
        "duplicate_count": sum(1 for item in queued if item.get("duplicate")),
        "managed_output_skip_count": sum(
            1 for item in queued if item.get("reason") == "managed_sync_output"
        ),
        "managed_sync_manifest_count": len(generated_refs),
        "conflict_queue_count": conflict_queue_count,
        "deferred_cache_bootstrap": defer_cache_bootstrap,
        "autosync_cycle_lock": str(autosync_cycle_lock_path()),
        "filesystem_sync": sync_result,
        "source_changed": source_changed,
        "source_revision_unknown": source_revision_unknown,
        "force_sync": bool(force_sync),
        "source_signature": current_source_signature,
        "state_path": str(state_path()),
        "shared_shiguan_root": str(references_root()),
        "cache_vault_path": str(configured_cache_vault(config)),
        "watch_roots": [str(root) for root in watch_roots],
        "updated_at": now_text(),
    }
    if publish_status:
        write_json(
            status_path(),
            {
                **report,
                "ok": False,
                "last_cycle_ok": report.get("ok") is True,
                "pid": None,
                "mode": "once",
                "phase": "stopped",
                "message": "单次 preserve-only 同步已完成；未声明常驻 daemon 健康",
            },
        )
    return report


def run_once(
    snapshot_only: bool = False,
    force_sync: bool = False,
    lock_timeout: float = 600.0,
    publish_status: bool = True,
) -> dict[str, object]:
    with file_lock(autosync_cycle_lock_path(), timeout=max(0.0, lock_timeout)):
        with file_lock(config_lock_path(), timeout=max(0.0, lock_timeout)):
            config = sync_config()
            return _run_once_unlocked(
                snapshot_only=snapshot_only,
                force_sync=force_sync,
                config_snapshot=config,
                publish_status=publish_status,
            )


def daemon_loop(interval: int) -> int:
    ensure_shared_seed()
    started_at = now_text()
    write_json(
        status_path(),
        {
            "ok": False,
            "mode": "daemon",
            "phase": "starting",
            "message": "autosync daemon 已启动，尚未完成首轮 preserve-only 同步",
            "pid": os.getpid(),
            "started_at": started_at,
            "updated_at": started_at,
            "interval_seconds": interval,
            "fresh_for_seconds": MAX_CYCLE_FRESH_SECONDS,
            "shared_shiguan_root": str(references_root()),
        },
    )
    while True:
        cycle_started_at = now_text()
        previous = read_json(status_path(), {})
        write_json(
            status_path(),
            {
                **(previous if isinstance(previous, dict) else {}),
                "ok": False,
                "mode": "daemon",
                "phase": "running",
                "message": "autosync 正在执行 preserve-only 同步",
                "pid": os.getpid(),
                "interval_seconds": interval,
                "cycle_started_at": cycle_started_at,
                "updated_at": cycle_started_at,
                "fresh_for_seconds": MAX_CYCLE_FRESH_SECONDS,
            },
        )
        try:
            report = run_once(force_sync=False, publish_status=False)
            report["mode"] = "daemon"
            report["phase"] = "idle"
            report["pid"] = os.getpid()
            report["interval_seconds"] = interval
            report["cycle_started_at"] = cycle_started_at
            report["cycle_completed_at"] = report.get("updated_at") or now_text()
            report["fresh_for_seconds"] = MAX_CYCLE_FRESH_SECONDS
            write_json(status_path(), report)
            print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
        except Exception as exc:
            error = {
                "ok": False,
                "mode": "daemon",
                "phase": "failed",
                "pid": os.getpid(),
                "interval_seconds": interval,
                "cycle_started_at": cycle_started_at,
                "error": str(exc),
                "updated_at": now_text(),
                "fresh_for_seconds": MAX_CYCLE_FRESH_SECONDS,
                "shared_shiguan_root": str(references_root()),
            }
            write_json(status_path(), error)
            print(json.dumps(error, ensure_ascii=False, sort_keys=True), flush=True)
        time.sleep(max(5, interval))


def emit_result(result: dict[str, object], result_json: str = "") -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if result_json:
        Path(result_json).write_text(text + "\n", encoding="utf-8", newline="\n")
    if getattr(sys, "stdout", None):
        print(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Run one import/sync/snapshot cycle and exit.")
    parser.add_argument("--snapshot-only", action="store_true", help="Only refresh the autosync snapshot.")
    parser.add_argument("--force-sync", action="store_true", help="Force a preserve-only filesystem sync even when Shiguan source files are unchanged.")
    parser.add_argument("--if-needed", action="store_true", help="With --once, sync only when Shiguan sources changed instead of forcing a sync.")
    parser.add_argument("--interval", type=int, default=20)
    parser.add_argument("--result-json", default="", help="Write the JSON result to this path for pythonw callers.")
    parser.add_argument("--lock-timeout", type=float, default=600.0)
    args = parser.parse_args()
    if args.once or args.snapshot_only:
        force_sync = bool(args.force_sync or (args.once and not args.if_needed and not args.snapshot_only))
        emit_result(
            run_once(
                snapshot_only=args.snapshot_only,
                force_sync=force_sync,
                lock_timeout=args.lock_timeout,
            ),
            args.result_json,
        )
        return 0
    return daemon_loop(args.interval)


if __name__ == "__main__":
    sys.exit(main())
