#!/usr/bin/env python
"""Synchronize the Court Shiguan growth tree into the local Obsidian vault.

This is a bounded preserve-only filesystem sync: it rebuilds the Shiguan
index/tree, exports a fresh Obsidian-compatible copy to a temporary directory,
then adds generated Shiguan files in the configured vault while
preserving `.obsidian/` plugin/config files and any existing/original text that
is no longer present in the generated export. It must not delete user notes or
previously exported source text unless a future user decree explicitly approves a
specific deletion. Existing targets require an explicit trusted transaction
reference; without one they are preserved and reported as conflicts.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import shutil
from pathlib import Path
import sys
import tempfile
import time
import uuid

sys.dont_write_bytecode = True

from shiguan_paths import (
    code_root,
    reference_path,
    references_root as shared_references_root,
    shared_root,
)
from court_file_lock import atomic_write_text, file_lock, fsync_parent_directory
from obsidian_config_state import config_lock_path, read_config_snapshot


SYNC_MANIFEST_NAME = ".court-shiguan-sync-manifest.json"
SYNC_MANIFEST_SCHEMA = "court.shiguan.sync-manifest.v2"
LEGACY_SYNC_MANIFEST_SCHEMA = "court.shiguan.sync-manifest.v1"
AUTO_SYNC_STATUS_NAME = "Auto Sync Status.md"
EXPORT_MANAGED_MARKER_NAME = ".court-shiguan-managed.json"
EXPORT_MANAGED_MARKER_SCHEMA = "court.shiguan.managed-export.v1"
APPLIED_MANIFEST_CHECKPOINT_FILES = 64


def skill_root() -> Path:
    return code_root()


def default_vault() -> Path:
    value = read_config_snapshot()
    configured = (
        value.get("vault_path")
        or value.get("filesystem_vault_path")
        or value.get("filesystem_vault")
    )
    if configured:
        return Path(str(configured)).expanduser()
    return Path.home() / "Documents" / "Obsidian Vault" / "Court Shiguan"


def protected(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    return bool(rel.parts and rel.parts[0] == ".obsidian")


def filesystem_sync_lock_path() -> Path:
    return reference_path("court-runtime", "obsidian-filesystem-sync.lock")


def staged_copy2(src: Path, dst: Path, expected_dst_ref: object = None) -> bool:
    """Copy a new target through a sibling temp file.

    Existing targets are deliberately never replaced by this low-level helper.
    A caller must obtain an explicit, non-content target reference in a future
    transaction before an overwrite can be authorized.  This keeps an
    unobservable external edit from being mistaken for a safe compare-and-swap.
    """

    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".sync.tmp", dir=str(dst.parent))
    os.close(fd)
    temp_path = Path(raw_temp)
    try:
        shutil.copy2(src, temp_path)
        with temp_path.open("r+b") as handle:
            os.fsync(handle.fileno())
        # No body comparison is performed here.  The transaction lock and the
        # explicit absence precondition are the only safe facts available.
        if dst.exists():
            return False
        deadline = time.monotonic() + 2.0
        while True:
            try:
                os.replace(temp_path, dst)
                fsync_parent_directory(dst.parent)
                if not dst.is_file():
                    raise RuntimeError(f"staged copy post-write target missing: {dst}")
                return True
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass


def normalized_manifest_refs(value: object) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, dict[str, str]] = {}
    for rel, raw in value.items():
        rel_text = str(rel).replace("\\", "/").strip()
        if not rel_text:
            continue
        if isinstance(raw, str) and raw.strip():
            normalized[rel_text] = {"source_ref": raw.strip()}
            continue
        if not isinstance(raw, dict):
            continue
        reference = {
            key: str(raw[key]).strip()
            for key in ("source_ref", "source_revision", "transaction_id")
            if str(raw.get(key) or "").strip()
        }
        if reference:
            normalized[rel_text] = reference
    return normalized


def _source_reference(
    source_revision: object,
    source_ref: object,
    transaction_id: object,
) -> dict[str, str]:
    reference = {
        "source_revision": str(source_revision or "").strip() or "UNKNOWN",
        "source_ref": str(source_ref or "").strip() or "shiguan://unbound",
    }
    transaction = str(transaction_id or "").strip()
    if transaction:
        reference["transaction_id"] = transaction
    return reference


def _reference_matches(item: dict[str, str], reference: dict[str, str]) -> bool:
    return all(
        not reference.get(key)
        or str(item.get(key) or "") == str(reference.get(key) or "")
        for key in ("source_revision", "source_ref", "transaction_id")
    )


def generated_sync_manifest(
    src: Path,
    state: str,
    *,
    transaction_id: str | None = None,
    producer_transaction_id: str | None = None,
    previous_refs: dict[str, object] | None = None,
    applied_refs: dict[str, object] | None = None,
    source_revision: str | None = None,
    source_ref: str | None = None,
) -> dict[str, object]:
    if state not in {"applying", "committed"}:
        raise ValueError(f"unsupported sync manifest state: {state}")
    transaction = transaction_id or uuid.uuid4().hex
    producer_transaction = str(producer_transaction_id or "").strip()
    revision = str(source_revision or "").strip() or "UNKNOWN"
    reference = str(source_ref or "").strip() or f"shiguan://export/{revision}"
    desired_refs: dict[str, dict[str, str]] = {}
    for path in sorted(item for item in src.rglob("*") if item.is_file()):
        if path.name == EXPORT_MANAGED_MARKER_NAME:
            continue
        desired_refs[path.relative_to(src).as_posix()] = _source_reference(
            revision,
            f"{reference}#{path.relative_to(src).as_posix()}",
            transaction,
        )
    previous = normalized_manifest_refs(previous_refs or {})
    applied = normalized_manifest_refs(
        desired_refs if state == "committed" and applied_refs is None else (applied_refs or {})
    )
    return {
        "schema": SYNC_MANIFEST_SCHEMA,
        "state": state,
        "transaction_id": transaction,
        "producer_transaction_id": producer_transaction,
        "managed_by": "decretum-matrix",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source_revision": revision,
        "source_ref": reference,
        "previous_refs": previous,
        "desired_refs": desired_refs,
        "applied_refs": applied,
    }


def write_sync_manifest(dst: Path, manifest: dict[str, object]) -> None:
    atomic_write_text(
        dst / SYNC_MANIFEST_NAME,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def load_sync_manifest(dst: Path) -> dict[str, object]:
    path = dst / SYNC_MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict) or value.get("schema") not in {
        SYNC_MANIFEST_SCHEMA,
        LEGACY_SYNC_MANIFEST_SCHEMA,
    }:
        return {}
    return value


def load_sync_manifest_refs(dst: Path) -> dict[str, dict[str, str]]:
    value = load_sync_manifest(dst)
    state = value.get("state")
    if value.get("schema") != SYNC_MANIFEST_SCHEMA:
        # v1 ``files`` values are body digests and cannot be promoted to a
        # trusted reference.  Keep the legacy cache read-only instead.
        return {}
    if state == "applying":
        return normalized_manifest_refs(value.get("previous_refs"))
    if state != "committed":
        return {}
    return normalized_manifest_refs(value.get("applied_refs"))


def load_sync_manifest_hashes(dst: Path) -> dict[str, dict[str, str]]:
    """Compatibility alias with reference semantics, never body hashes."""
    return load_sync_manifest_refs(dst)


def update_sync_manifest_ref(
    dst: Path,
    rel: str,
    *,
    source_revision: str = "",
    source_ref: str = "",
    transaction_id: str = "",
) -> None:
    value = load_sync_manifest(dst)
    if not value or value.get("schema") != SYNC_MANIFEST_SCHEMA:
        return
    target = dst / rel
    if not target.is_file():
        return
    normalized_rel = rel.replace("\\", "/")
    reference = _source_reference(
        source_revision or value.get("source_revision"),
        source_ref or value.get("source_ref"),
        transaction_id or value.get("transaction_id"),
    )
    desired = normalized_manifest_refs(value.get("desired_refs"))
    applied = normalized_manifest_refs(value.get("applied_refs"))
    desired[normalized_rel] = dict(reference)
    applied[normalized_rel] = dict(reference)
    value["desired_refs"] = desired
    value["applied_refs"] = applied
    value.setdefault("previous_refs", {})
    value["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_sync_manifest(dst, value)


def update_sync_manifest_hash(dst: Path, rel: str) -> None:
    """Compatibility alias; updates only the current source reference."""
    update_sync_manifest_ref(dst, rel)


def remove_legacy_export_marker(dst: Path) -> bool:
    marker = dst / EXPORT_MANAGED_MARKER_NAME
    if not marker.is_file() or not (dst / SYNC_MANIFEST_NAME).is_file():
        return False
    if not valid_legacy_export_marker(dst):
        return False
    marker.unlink()
    return True


def valid_legacy_export_marker(dst: Path) -> bool:
    marker = dst / EXPORT_MANAGED_MARKER_NAME
    if not marker.is_file():
        return False
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and value.get("schema") == EXPORT_MANAGED_MARKER_SCHEMA


def legacy_autosync_snapshot_refs(dst: Path) -> dict[str, dict[str, str]]:
    state_path = reference_path("obsidian-sync", "autosync-state.json")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(state, dict):
        return {}
    try:
        state_cache = Path(str(state.get("cache_vault_path") or "")).resolve()
    except OSError:
        return {}
    if state_cache != dst.resolve():
        return {}
    snapshot = state.get("snapshot")
    if not isinstance(snapshot, dict):
        return {}
    references: dict[str, dict[str, str]] = {}
    for item in snapshot.values():
        if not isinstance(item, dict):
            continue
        try:
            root = Path(str(item.get("root") or "")).resolve()
        except OSError:
            continue
        rel = str(item.get("rel") or "").replace("\\", "/")
        source_ref = str(item.get("source_ref") or "").strip()
        source_revision = str(item.get("source_revision") or "").strip()
        if root == state_cache and rel and (source_ref or source_revision):
            references[rel] = _source_reference(
                source_revision,
                source_ref,
                item.get("transaction_id"),
            )
    return references


def legacy_autosync_snapshot_hashes(dst: Path) -> dict[str, dict[str, str]]:
    """Compatibility alias; legacy digest fields are intentionally ignored."""
    return legacy_autosync_snapshot_refs(dst)


def legacy_generated_refs(dst: Path) -> dict[str, dict[str, str]]:
    if not valid_legacy_export_marker(dst):
        return {}
    return legacy_autosync_snapshot_refs(dst)


def legacy_generated_hashes(dst: Path) -> dict[str, dict[str, str]]:
    """Compatibility alias; no legacy body digest is read or generated."""
    return legacy_generated_refs(dst)


def mirror_tree(
    src: Path,
    dst: Path,
    dry_run: bool = False,
    *,
    source_revision: str = "",
    source_ref: str = "",
    transaction_id: str | None = None,
    producer_transaction_id: str | None = None,
) -> dict[str, object]:
    src = src.resolve()
    dst = dst.resolve()
    if not src.exists() or not src.is_dir():
        raise ValueError(f"source export missing: {src}")
    if dst == skill_root() or skill_root() in dst.parents:
        raise ValueError("refusing to sync into the source skill directory")
    data_root = shared_root().resolve()
    refs_root = shared_references_root().resolve()
    if dst == data_root or data_root in dst.parents or dst == refs_root or refs_root in dst.parents:
        raise ValueError("refusing to sync into the authoritative Shiguan data directory")
    if not dry_run:
        dst.mkdir(parents=True, exist_ok=True)
    copied = updated = removed = skipped = preserved = 0
    user_modified_conflicts: list[str] = []
    src_files = {
        p.relative_to(src)
        for p in src.rglob("*")
        if p.is_file() and p.name != EXPORT_MANAGED_MARKER_NAME
    }
    dst_files = {
        p.relative_to(dst)
        for p in dst.rglob("*")
        if p.is_file()
        and not protected(p, dst)
        and p.name not in {SYNC_MANIFEST_NAME, AUTO_SYNC_STATUS_NAME, EXPORT_MANAGED_MARKER_NAME}
    }
    existing_manifest = load_sync_manifest(dst)
    sync_manifest: dict[str, object] | None = None
    previous_generated_refs = load_sync_manifest_refs(dst)
    manifest_migration_source = (
        "sync_manifest"
        if existing_manifest.get("schema") == SYNC_MANIFEST_SCHEMA
        else ("legacy_unverified" if existing_manifest else "none")
    )
    if not existing_manifest and not previous_generated_refs:
        previous_generated_refs = legacy_generated_refs(dst)
        if previous_generated_refs:
            manifest_migration_source = "legacy_autosync_snapshot_unverified"
    current_transaction_id = str(
        transaction_id
        or (
            existing_manifest.get("transaction_id")
            if existing_manifest.get("schema") == SYNC_MANIFEST_SCHEMA
            and existing_manifest.get("state") == "applying"
            else ""
        )
        or uuid.uuid4().hex
    )
    current_producer_transaction_id = str(
        producer_transaction_id
        or (
            existing_manifest.get("producer_transaction_id")
            if existing_manifest.get("schema") == SYNC_MANIFEST_SCHEMA
            and existing_manifest.get("state") == "applying"
            else ""
        )
        or ""
    ).strip()
    current_source_revision = str(source_revision or "").strip() or "UNKNOWN"
    current_source_ref = str(source_ref or "").strip() or f"shiguan://export/{current_source_revision}"
    if not dry_run:
        # Preserve the last committed baseline separately from the desired
        # output set. An interrupted transaction must never reinterpret desired
        # references as if they had already been copied.
        sync_manifest = generated_sync_manifest(
            src,
            "applying",
            transaction_id=current_transaction_id,
            producer_transaction_id=current_producer_transaction_id,
            previous_refs=previous_generated_refs,
            source_revision=current_source_revision,
            source_ref=current_source_ref,
        )
        write_sync_manifest(dst, sync_manifest)
    inflight_refs = (
        normalized_manifest_refs(existing_manifest.get("applied_refs"))
        if existing_manifest.get("schema") == SYNC_MANIFEST_SCHEMA
        and existing_manifest.get("state") == "applying"
        else {}
    )
    legacy_export_marker_removed = (
        remove_legacy_export_marker(dst)
        if not dry_run and existing_manifest.get("schema") == SYNC_MANIFEST_SCHEMA
        else False
    )

    desired_generated_refs = (
        normalized_manifest_refs(sync_manifest.get("desired_refs"))
        if sync_manifest is not None
        else {
            path.relative_to(src).as_posix(): _source_reference(
                current_source_revision,
                f"{current_source_ref}#{path.relative_to(src).as_posix()}",
                current_transaction_id,
            )
            for path in sorted(item for item in src.rglob("*") if item.is_file())
            if path.name != EXPORT_MANAGED_MARKER_NAME
        }
    )
    applied_generated_refs = (
        normalized_manifest_refs(sync_manifest.get("applied_refs"))
        if sync_manifest is not None
        else {}
    )
    applied_since_checkpoint = 0

    def verify_applied(rel_text: str, target: Path, *, persist: bool) -> bool:
        nonlocal applied_since_checkpoint
        if sync_manifest is None:
            return True
        expected_ref = desired_generated_refs.get(rel_text)
        if not expected_ref or not target.is_file():
            return False
        # A target's bytes are intentionally not inspected.  This verification
        # only records that this transaction atomically created the target.
        applied_generated_refs[rel_text] = dict(expected_ref)
        sync_manifest["applied_refs"] = dict(applied_generated_refs)
        if persist:
            applied_since_checkpoint += 1
            if applied_since_checkpoint >= APPLIED_MANIFEST_CHECKPOINT_FILES:
                sync_manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
                write_sync_manifest(dst, sync_manifest)
                applied_since_checkpoint = 0
        return True

    for rel in sorted(src_files):
        s = src / rel
        d = dst / rel
        rel_text = rel.as_posix()
        if protected(d, dst):
            skipped += 1
            continue
        if not d.exists():
            if dry_run:
                copied += 1
            else:
                # Record the in-flight target reference before replacing the
                # file so recovery can distinguish this transaction's partial
                # create from an unrelated external file.
                if sync_manifest is not None:
                    applied_generated_refs[rel_text] = dict(desired_generated_refs[rel_text])
                    sync_manifest["applied_refs"] = dict(applied_generated_refs)
                    write_sync_manifest(dst, sync_manifest)
                if staged_copy2(s, d, None):
                    if verify_applied(rel_text, d, persist=True):
                        copied += 1
                    else:
                        user_modified_conflicts.append(rel_text)
                        preserved += 1
                else:
                    applied_generated_refs.pop(rel_text, None)
                    if sync_manifest is not None:
                        sync_manifest["applied_refs"] = dict(applied_generated_refs)
                    user_modified_conflicts.append(rel_text)
                    preserved += 1
        elif (
            rel_text in inflight_refs
            and _reference_matches(inflight_refs[rel_text], desired_generated_refs.get(rel_text, {}))
        ):
            # Recovery of a target already created by this applying
            # transaction is reference-bound.  No body compare is attempted.
            if sync_manifest is not None:
                applied_generated_refs[rel_text] = dict(desired_generated_refs[rel_text])
            continue
        else:
            # Existing text has no trustworthy non-content compare-and-swap
            # token.  Preserve it and surface a conflict for review.
            user_modified_conflicts.append(rel_text)
            preserved += 1

    for rel in sorted(dst_files - src_files):
        d = dst / rel
        if protected(d, dst):
            skipped += 1
            continue
        # Preserve-only rule: user corrections explicitly forbid deleting original
        # or previously exported text. Keep files that are no longer present in
        # the generated export and report them for audit instead of unlinking.
        preserved += 1

    if sync_manifest is not None:
        # Only transaction references produced by successful atomic creates
        # enter the committed view.  Existing targets remain conflicts because
        # their bytes cannot be proven unchanged without a content digest.
        for rel_text, expected_ref in list(applied_generated_refs.items()):
            target = dst / Path(rel_text)
            if target.is_file():
                continue
            applied_generated_refs.pop(rel_text, None)
            if rel_text not in user_modified_conflicts:
                user_modified_conflicts.append(rel_text)
                preserved += 1
        sync_manifest["state"] = "conflict" if user_modified_conflicts else "committed"
        sync_manifest["applied_refs"] = dict(applied_generated_refs)
        sync_manifest["conflicts"] = sorted(user_modified_conflicts)
        sync_manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
        write_sync_manifest(dst, sync_manifest)

    return {
        "copied": copied,
        "updated": updated,
        "preserved": preserved,
        "removed": 0,
        "skipped_protected": skipped,
        "preserve_only": True,
        "sync_manifest": str(dst / SYNC_MANIFEST_NAME) if not dry_run else "",
        "sync_manifest_files": len(sync_manifest.get("applied_refs", {})) if sync_manifest else 0,
        "sync_transaction_id": str(sync_manifest.get("transaction_id") or "") if sync_manifest else "",
        "producer_transaction_id": str(sync_manifest.get("producer_transaction_id") or current_producer_transaction_id) if sync_manifest else current_producer_transaction_id,
        "sync_source_revision": str(sync_manifest.get("source_revision") or current_source_revision) if sync_manifest else current_source_revision,
        "sync_source_ref": str(sync_manifest.get("source_ref") or current_source_ref) if sync_manifest else current_source_ref,
        "sync_previous_refs": len(sync_manifest.get("previous_refs", {})) if sync_manifest else len(previous_generated_refs),
        "sync_desired_refs": len(sync_manifest.get("desired_refs", {})) if sync_manifest else len(desired_generated_refs),
        "sync_applied_refs": len(sync_manifest.get("applied_refs", {})) if sync_manifest else len(applied_generated_refs),
        "transaction_state": str(sync_manifest.get("state") or ("dry_run" if dry_run else "unknown")) if sync_manifest else ("dry_run" if dry_run else "unknown"),
        "user_modified_conflicts": user_modified_conflicts,
        "user_modified_conflict_count": len(user_modified_conflicts),
        "unverifiable_external_change_count": len(user_modified_conflicts),
        "legacy_export_marker_removed": legacy_export_marker_removed,
        "manifest_migration_source": manifest_migration_source,
    }


def write_marker(vault: Path, result: dict[str, object], dry_run: bool) -> dict[str, object]:
    if dry_run:
        return {"written": False, "conflict": False, "dry_run": True}
    marker = vault / AUTO_SYNC_STATUS_NAME
    body = [
        "---",
        "type: shiguan_obsidian_auto_sync_status",
        f"updated_at: \"{datetime.now().isoformat(timespec='seconds')}\"",
        "preserve_only: true",
        "architecture: parent_vault_references_source_with_cache",
        "---",
        "",
        "# Shiguan → Obsidian Auto Sync Status",
        "",
        "This folder is a preserve-only Obsidian cache refreshed by the background `decretum-matrix` Shiguan service when authoritative Shiguan sources change.",
        "Original/source text and user notes are preserved; sync is allowed to add or update generated files, not delete old text.",
        "This is event-driven sync, not a periodic cron freshness mechanism.",
        "",
        f"Authoritative shared source tree: `{reference_path('shiguan-tree')}`.",
        "Parent vault entry: [[../史馆入口|史馆入口]].",
        "",
        "## Last result",
        "",
        "```json",
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "Start at [[_index]].",
        "",
    ]
    text = "\n".join(body)
    if marker.is_file():
        # The status marker is ordinary text and cannot be compared by body
        # digest in this contract.  Keep an existing marker until an explicit
        # external transaction reference authorizes its replacement.
        return {
            "written": False,
            "conflict": True,
            "path": str(marker),
            "rel": AUTO_SYNC_STATUS_NAME,
            "reason": "status_marker_external_state_unverifiable",
        }
    atomic_write_text(marker, text)
    update_sync_manifest_ref(vault, AUTO_SYNC_STATUS_NAME)
    return {
        "written": True,
        "conflict": False,
        "path": str(marker),
        "rel": AUTO_SYNC_STATUS_NAME,
    }


def emit_result(result: dict[str, object], result_json: str = "", allow_write: bool = True) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if result_json and allow_write:
        Path(result_json).write_text(text + "\n", encoding="utf-8", newline="\n")
    if getattr(sys, "stdout", None):
        print(text)


def run_write_sync(args: argparse.Namespace, vault: Path) -> int:
    from rebuild_shiguan_index import rebuild_index
    from grow_shiguan_tree import grow_tree
    from export_shiguan_obsidian import check_export, copy_tree, zip_dir

    count, _ = rebuild_index()
    grow_tree()
    source_revision = str(getattr(args, "source_revision", "") or "").strip() or "UNKNOWN"
    source_ref = str(getattr(args, "source_ref", "") or "").strip() or f"shiguan://export/{source_revision}"
    producer_transaction_id = str(getattr(args, "producer_transaction_id", "") or "").strip()
    with tempfile.TemporaryDirectory(prefix="shiguan-obsidian-sync-") as tmp:
        export_dir = Path(tmp) / "Court Shiguan"
        copy_tree(export_dir)
        errors = check_export(export_dir)
        if errors:
            emit_result({"ok": False, "stage": "check_export", "errors": errors[:50]}, args.result_json)
            return 2
        result = mirror_tree(
            export_dir,
            vault,
            False,
            source_revision=source_revision,
            source_ref=source_ref,
            producer_transaction_id=producer_transaction_id,
        )
    result.update({
        "ok": True,
        "vault": str(vault),
        "shared_shiguan_root": str(shared_references_root()),
        "entries": count,
        "dry_run": False,
        "synced_at": datetime.now().isoformat(timespec="seconds"),
        "source_revision": source_revision,
        "source_ref": source_ref,
        "producer_transaction_id": producer_transaction_id,
        "source_revision_state": "KNOWN"
        if (
            source_revision != "UNKNOWN"
            and source_ref != "shiguan://export/UNKNOWN"
            and producer_transaction_id
        )
        else "UNKNOWN",
        "md_count": sum(1 for _ in vault.rglob("*.md")) if vault.exists() else 0,
        "index_exists": (vault / "_index.md").exists(),
        "obsidian_config_preserved": (vault / ".obsidian" / "community-plugins.json").exists(),
        "filesystem_sync_lock": str(filesystem_sync_lock_path()),
    })
    marker_result = write_marker(vault, result, False)
    result["status_marker"] = marker_result
    if marker_result.get("conflict"):
        conflicts = result.get("user_modified_conflicts")
        if not isinstance(conflicts, list):
            conflicts = []
            result["user_modified_conflicts"] = conflicts
        if AUTO_SYNC_STATUS_NAME not in conflicts:
            conflicts.append(AUTO_SYNC_STATUS_NAME)
        result["user_modified_conflict_count"] = len(conflicts)
    if result.get("user_modified_conflict_count"):
        result["ok"] = False
        result["transaction_state"] = "conflict"
    elif result.get("source_revision_state") != "KNOWN":
        result["ok"] = False
        result["transaction_state"] = "committed_unverified_source"
    if args.zip:
        result["zip"] = str(zip_dir(vault))
    emit_result(result, args.result_json)
    return 0


def run_locked_write_sync(args: argparse.Namespace, vault: Path) -> int:
    with file_lock(filesystem_sync_lock_path(), timeout=max(0.0, args.lock_timeout)):
        return run_write_sync(args, vault)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--zip", action="store_true", help="also refresh <vault>.zip")
    parser.add_argument("--result-json", default="", help="Write the JSON result to this path for pythonw callers.")
    parser.add_argument("--lock-timeout", type=float, default=600.0)
    parser.add_argument("--source-revision", default="", help="Controlled Shiguan/export revision reference.")
    parser.add_argument("--source-ref", default="", help="Controlled Shiguan/export source reference.")
    parser.add_argument("--producer-transaction-id", default="", help="Producer transaction reference; kept separate from the sync transaction.")
    args = parser.parse_args()

    root = skill_root()
    sys.path.insert(0, str(root / "scripts"))

    explicit_vault = bool(str(args.vault or "").strip())
    vault = Path(args.vault).expanduser().resolve() if explicit_vault else default_vault().resolve()
    if args.dry_run:
        source_tree = reference_path("shiguan-tree").resolve()
        if not source_tree.exists():
            emit_result(
                {
                    "ok": False,
                    "stage": "inspect_existing_tree",
                    "reason": "shared Shiguan tree is missing; dry-run does not initialize or rebuild it",
                    "vault": str(vault),
                    "shared_shiguan_root": str(shared_references_root()),
                    "dry_run": True,
                    "preserve_only": True,
                    "removed": 0,
                    "result_json_written": False,
                },
                args.result_json,
                allow_write=False,
            )
            return 2
        result = mirror_tree(
            source_tree,
            vault,
            dry_run=True,
            source_revision=args.source_revision,
            source_ref=args.source_ref,
            producer_transaction_id=args.producer_transaction_id,
        )
        result.update(
            {
                "ok": True,
                "stage": "inspect_existing_tree",
                "vault": str(vault),
                "shared_shiguan_root": str(shared_references_root()),
                "dry_run": True,
                "source_tree_rebuilt": False,
                "marker_written": False,
                "result_json_written": False,
                "md_count": sum(1 for _ in vault.rglob("*.md")) if vault.exists() else 0,
                "index_exists": (vault / "_index.md").exists(),
                "obsidian_config_preserved": (vault / ".obsidian" / "community-plugins.json").exists(),
            }
        )
        emit_result(result, args.result_json, allow_write=False)
        return 0

    try:
        if explicit_vault:
            return run_locked_write_sync(args, vault)
        with file_lock(config_lock_path(), timeout=max(0.0, args.lock_timeout)):
            vault = default_vault().resolve()
            return run_locked_write_sync(args, vault)
    except TimeoutError as exc:
        emit_result(
            {
                "ok": False,
                "stage": "filesystem_sync_lock",
                "reason": str(exc),
                "lock_path": str(filesystem_sync_lock_path()),
            },
            args.result_json,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
