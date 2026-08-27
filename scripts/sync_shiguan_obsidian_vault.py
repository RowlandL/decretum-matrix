#!/usr/bin/env python
"""Synchronize the Court Shiguan growth tree into the local Obsidian vault.

This is a bounded preserve-only filesystem sync: it rebuilds the Shiguan
index/tree, exports a fresh Obsidian-compatible copy to a temporary directory,
then adds or updates generated Shiguan files in the configured vault while
preserving `.obsidian/` plugin/config files and any existing/original text that
is no longer present in the generated export. It must not delete user notes or
previously exported source text unless a future user decree explicitly approves a
specific deletion.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import filecmp
import hashlib
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
SYNC_MANIFEST_SCHEMA = "court.shiguan.sync-manifest.v1"
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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filesystem_sync_lock_path() -> Path:
    return reference_path("court-runtime", "obsidian-filesystem-sync.lock")


def staged_copy2(src: Path, dst: Path, expected_dst_hash: str | None) -> bool:
    """Copy through a sibling temp file and replace only if dst stayed stable."""

    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".sync.tmp", dir=str(dst.parent))
    os.close(fd)
    temp_path = Path(raw_temp)
    try:
        source_hash = file_sha256(src)
        shutil.copy2(src, temp_path)
        with temp_path.open("r+b") as handle:
            os.fsync(handle.fileno())
        if file_sha256(temp_path) != source_hash:
            raise RuntimeError(f"staged copy hash mismatch before replace: {src}")
        if expected_dst_hash is None:
            if dst.exists():
                return False
        else:
            if not dst.is_file() or file_sha256(dst) != expected_dst_hash:
                return False
        deadline = time.monotonic() + 2.0
        while True:
            try:
                os.replace(temp_path, dst)
                fsync_parent_directory(dst.parent)
                if not dst.is_file() or file_sha256(dst) != source_hash:
                    raise RuntimeError(f"staged copy post-write verification failed: {dst}")
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


def normalized_manifest_hashes(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(rel).replace("\\", "/"): str(digest)
        for rel, digest in value.items()
        if str(rel).strip() and len(str(digest)) == 64
    }


def generated_sync_manifest(
    src: Path,
    state: str,
    *,
    transaction_id: str | None = None,
    previous_files: dict[str, str] | None = None,
    applied_files: dict[str, str] | None = None,
) -> dict[str, object]:
    if state not in {"applying", "committed"}:
        raise ValueError(f"unsupported sync manifest state: {state}")
    desired_files: dict[str, str] = {}
    for path in sorted(item for item in src.rglob("*") if item.is_file()):
        if path.name == EXPORT_MANAGED_MARKER_NAME:
            continue
        desired_files[path.relative_to(src).as_posix()] = file_sha256(path)
    previous = normalized_manifest_hashes(previous_files or {})
    applied = normalized_manifest_hashes(
        desired_files if state == "committed" and applied_files is None else (applied_files or {})
    )
    return {
        "schema": SYNC_MANIFEST_SCHEMA,
        "state": state,
        "transaction_id": transaction_id or uuid.uuid4().hex,
        "managed_by": "decretum-matrix",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "previous_files": previous,
        "desired_files": desired_files,
        "applied_files": applied,
        # Compatibility contract: the daemon and older readers use ``files``.
        # While applying it is the intended output set used for suppression;
        # after commit it contains only hashes verified on disk.
        "files": dict(desired_files if state == "applying" else applied),
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
    if not isinstance(value, dict) or value.get("schema") != SYNC_MANIFEST_SCHEMA:
        return {}
    return value


def load_sync_manifest_hashes(dst: Path) -> dict[str, str]:
    value = load_sync_manifest(dst)
    state = value.get("state")
    if state == "applying":
        # An interrupted transaction must compare cache content with the last
        # committed baseline, never with the intended-but-not-yet-copied set.
        if "previous_files" in value:
            return normalized_manifest_hashes(value.get("previous_files"))
        # Compatibility for an old v1 applying manifest, whose ``files`` field
        # represented desired output and therefore cannot be a conflict base.
        return legacy_autosync_snapshot_hashes(dst)
    if state != "committed":
        return {}
    if "applied_files" in value:
        return normalized_manifest_hashes(value.get("applied_files"))
    return normalized_manifest_hashes(value.get("files"))


def update_sync_manifest_hash(dst: Path, rel: str) -> None:
    value = load_sync_manifest(dst)
    if not value:
        return
    target = dst / rel
    if not target.is_file():
        return
    normalized_rel = rel.replace("\\", "/")
    digest = file_sha256(target)
    desired = normalized_manifest_hashes(value.get("desired_files") or value.get("files"))
    applied = normalized_manifest_hashes(value.get("applied_files") or value.get("files"))
    desired[normalized_rel] = digest
    applied[normalized_rel] = digest
    value["desired_files"] = desired
    value["applied_files"] = applied
    value["files"] = dict(desired if value.get("state") == "applying" else applied)
    value.setdefault("previous_files", {})
    value.setdefault("transaction_id", uuid.uuid4().hex)
    value["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_sync_manifest(dst, value)


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


def legacy_autosync_snapshot_hashes(dst: Path) -> dict[str, str]:
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
    hashes: dict[str, str] = {}
    for item in snapshot.values():
        if not isinstance(item, dict):
            continue
        try:
            root = Path(str(item.get("root") or "")).resolve()
        except OSError:
            continue
        rel = str(item.get("rel") or "").replace("\\", "/")
        digest = str(item.get("sha256") or "")
        if root == state_cache and rel and len(digest) == 64:
            hashes[rel] = digest
    return hashes


def legacy_generated_hashes(dst: Path) -> dict[str, str]:
    if not valid_legacy_export_marker(dst):
        return {}
    hashes = legacy_autosync_snapshot_hashes(dst)
    for path in dst.rglob("*"):
        if not path.is_file() or path.name in {
            SYNC_MANIFEST_NAME,
            EXPORT_MANAGED_MARKER_NAME,
        }:
            continue
        if path.suffix.lower() in {".md", ".txt"}:
            continue
        try:
            hashes.setdefault(path.relative_to(dst).as_posix(), file_sha256(path))
        except OSError:
            continue
    return hashes


def mirror_tree(src: Path, dst: Path, dry_run: bool = False) -> dict[str, object]:
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
    previous_generated_hashes = load_sync_manifest_hashes(dst)
    manifest_migration_source = "sync_manifest" if existing_manifest else "none"
    if not existing_manifest and not previous_generated_hashes:
        previous_generated_hashes = legacy_generated_hashes(dst)
        if previous_generated_hashes:
            manifest_migration_source = "legacy_autosync_snapshot_and_managed_nontext"
    if not dry_run:
        # Preserve the last committed baseline separately from the desired
        # output set. An interrupted transaction must never reinterpret desired
        # hashes as if they had already been copied.
        sync_manifest = generated_sync_manifest(
            src,
            "applying",
            previous_files=previous_generated_hashes,
        )
        previous_status_hash = previous_generated_hashes.get(AUTO_SYNC_STATUS_NAME)
        if previous_status_hash:
            desired_files = normalized_manifest_hashes(sync_manifest.get("desired_files"))
            desired_files[AUTO_SYNC_STATUS_NAME] = previous_status_hash
            sync_manifest["desired_files"] = desired_files
            sync_manifest["files"] = dict(desired_files)
            status_marker = dst / AUTO_SYNC_STATUS_NAME
            if status_marker.is_file() and file_sha256(status_marker) == previous_status_hash:
                applied_files = normalized_manifest_hashes(sync_manifest.get("applied_files"))
                applied_files[AUTO_SYNC_STATUS_NAME] = previous_status_hash
                sync_manifest["applied_files"] = applied_files
        write_sync_manifest(dst, sync_manifest)
    legacy_export_marker_removed = remove_legacy_export_marker(dst) if not dry_run else False

    desired_generated_hashes = (
        normalized_manifest_hashes(sync_manifest.get("desired_files"))
        if sync_manifest is not None
        else {
            path.relative_to(src).as_posix(): file_sha256(path)
            for path in sorted(item for item in src.rglob("*") if item.is_file())
            if path.name != EXPORT_MANAGED_MARKER_NAME
        }
    )
    applied_generated_hashes = (
        normalized_manifest_hashes(sync_manifest.get("applied_files"))
        if sync_manifest is not None
        else {}
    )
    applied_since_checkpoint = 0

    def verify_applied(rel_text: str, target: Path, *, persist: bool) -> bool:
        nonlocal applied_since_checkpoint
        if sync_manifest is None:
            return True
        expected_hash = desired_generated_hashes.get(rel_text)
        if not expected_hash or not target.is_file():
            return False
        try:
            actual_hash = file_sha256(target)
        except OSError:
            return False
        if actual_hash != expected_hash:
            return False
        applied_generated_hashes[rel_text] = expected_hash
        sync_manifest["applied_files"] = dict(applied_generated_hashes)
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
            elif staged_copy2(s, d, None):
                if verify_applied(rel_text, d, persist=True):
                    copied += 1
                else:
                    user_modified_conflicts.append(rel_text)
                    preserved += 1
            else:
                user_modified_conflicts.append(rel_text)
                preserved += 1
        elif filecmp.cmp(s, d, shallow=False):
            if not dry_run and not verify_applied(rel_text, d, persist=False):
                user_modified_conflicts.append(rel_text)
                preserved += 1
        else:
            try:
                current_hash = file_sha256(d)
            except OSError:
                user_modified_conflicts.append(rel_text)
                preserved += 1
                continue
            previous_hash = previous_generated_hashes.get(rel_text)
            if current_hash != previous_hash:
                # With no trusted prior generated hash, or when the destination
                # diverged from it, preserve the cache text. The daemon will
                # route this exact conflict into pending review instead of the
                # forward sync silently overwriting a user edit.
                user_modified_conflicts.append(rel_text)
                preserved += 1
                continue
            if dry_run:
                updated += 1
            elif staged_copy2(s, d, current_hash):
                if verify_applied(rel_text, d, persist=True):
                    updated += 1
                else:
                    user_modified_conflicts.append(rel_text)
                    preserved += 1
            else:
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
        # Recheck every candidate immediately before commit. Only hashes still
        # present on disk at their desired value enter the committed view.
        for rel_text, expected_hash in list(applied_generated_hashes.items()):
            target = dst / Path(rel_text)
            try:
                verified = target.is_file() and file_sha256(target) == expected_hash
            except OSError:
                verified = False
            if verified:
                continue
            applied_generated_hashes.pop(rel_text, None)
            if rel_text not in user_modified_conflicts:
                user_modified_conflicts.append(rel_text)
                preserved += 1
        sync_manifest["state"] = "committed"
        sync_manifest["applied_files"] = dict(applied_generated_hashes)
        sync_manifest["files"] = dict(applied_generated_hashes)
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
        "sync_manifest_files": len(sync_manifest.get("files", {})) if sync_manifest else 0,
        "sync_transaction_id": str(sync_manifest.get("transaction_id") or "") if sync_manifest else "",
        "sync_previous_files": len(sync_manifest.get("previous_files", {})) if sync_manifest else 0,
        "sync_desired_files": len(sync_manifest.get("desired_files", {})) if sync_manifest else 0,
        "sync_applied_files": len(sync_manifest.get("applied_files", {})) if sync_manifest else 0,
        "user_modified_conflicts": user_modified_conflicts,
        "user_modified_conflict_count": len(user_modified_conflicts),
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
    previous_hash = load_sync_manifest_hashes(vault).get(AUTO_SYNC_STATUS_NAME)
    if marker.is_file():
        current_hash = file_sha256(marker)
        new_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if current_hash != new_hash and current_hash != previous_hash:
            return {
                "written": False,
                "conflict": True,
                "path": str(marker),
                "rel": AUTO_SYNC_STATUS_NAME,
            }
    atomic_write_text(marker, text)
    update_sync_manifest_hash(vault, AUTO_SYNC_STATUS_NAME)
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
    with tempfile.TemporaryDirectory(prefix="shiguan-obsidian-sync-") as tmp:
        export_dir = Path(tmp) / "Court Shiguan"
        copy_tree(export_dir)
        errors = check_export(export_dir)
        if errors:
            emit_result({"ok": False, "stage": "check_export", "errors": errors[:50]}, args.result_json)
            return 2
        result = mirror_tree(export_dir, vault, False)
    result.update({
        "ok": True,
        "vault": str(vault),
        "shared_shiguan_root": str(shared_references_root()),
        "entries": count,
        "dry_run": False,
        "synced_at": datetime.now().isoformat(timespec="seconds"),
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
        result = mirror_tree(source_tree, vault, dry_run=True)
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
