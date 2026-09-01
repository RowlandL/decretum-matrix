"""Transaction-manifest regressions for preserve-only Obsidian sync."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import tempfile
from typing import Any
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import sync_shiguan_obsidian_vault as sync  # type: ignore  # noqa: E402
import ensure_obsidian_shared_vault as vault  # type: ignore  # noqa: E402
import obsidian_config_state as config_state  # type: ignore  # noqa: E402


class SimulatedSyncCrash(RuntimeError):
    pass


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _manifest(cache: Path) -> dict[str, Any]:
    value = json.loads((cache / sync.SYNC_MANIFEST_NAME).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError("sync manifest must be an object")
    return value


def _isolated_paths(temp: Path) -> ExitStack:
    shared = temp / "shared"
    references = shared / "references"
    stack = ExitStack()
    stack.enter_context(mock.patch.object(sync, "shared_root", return_value=shared))
    stack.enter_context(mock.patch.object(sync, "shared_references_root", return_value=references))
    stack.enter_context(
        mock.patch.object(sync, "reference_path", side_effect=lambda *parts: references.joinpath(*parts))
    )
    return stack


def check_first_sync(temp: Path) -> dict[str, Any]:
    source = temp / "first-source"
    cache = temp / "first-cache"
    source.mkdir()
    _write(source / "first.md", "generated-first\n")
    result = sync.mirror_tree(source, cache)
    manifest = _manifest(cache)
    desired_hash = sync.file_sha256(source / "first.md")
    for field in ("transaction_id", "previous_files", "desired_files", "applied_files"):
        if field not in manifest:
            raise AssertionError(f"transaction manifest missing {field}")
    if manifest.get("state") != "committed":
        raise AssertionError(f"first sync did not commit: {manifest}")
    if manifest.get("previous_files") != {}:
        raise AssertionError("first sync previous_files must be empty")
    if manifest.get("desired_files", {}).get("first.md") != desired_hash:
        raise AssertionError("first sync desired hash drifted")
    if manifest.get("applied_files", {}).get("first.md") != desired_hash:
        raise AssertionError("first sync did not record the verified applied hash")
    if manifest.get("files", {}).get("first.md") != desired_hash:
        raise AssertionError("legacy files compatibility view did not expose committed hashes")
    if result.get("removed") != 0:
        raise AssertionError("preserve-only first sync reported removals")
    return {"copied": result.get("copied"), "removed": result.get("removed")}


def check_legacy_committed_compatibility(temp: Path) -> dict[str, Any]:
    source = temp / "legacy-source"
    cache = temp / "legacy-cache"
    source.mkdir()
    cache.mkdir()
    _write(source / "legacy.md", "generated-v1\n")
    _write(cache / "legacy.md", "generated-v1\n")
    legacy_hash = sync.file_sha256(cache / "legacy.md")
    sync.write_sync_manifest(
        cache,
        {
            "schema": sync.SYNC_MANIFEST_SCHEMA,
            "state": "committed",
            "managed_by": "decretum-matrix",
            "updated_at": "legacy-fixture",
            "files": {"legacy.md": legacy_hash},
        },
    )
    _write(source / "legacy.md", "generated-v2\n")
    result = sync.mirror_tree(source, cache)
    if result.get("updated") != 1 or result.get("user_modified_conflict_count") != 0:
        raise AssertionError(f"legacy committed manifest was not accepted: {result}")
    return {"updated": result.get("updated"), "conflicts": result.get("user_modified_conflict_count")}


def check_crash_and_recovery(temp: Path) -> dict[str, Any]:
    source = temp / "crash-source"
    cache = temp / "crash-cache"
    source.mkdir()
    cache.mkdir()
    for name in ("a.md", "b.md"):
        _write(source / name, f"{name}-generated-v1\n")
        _write(cache / name, f"{name}-generated-v1\n")
    sync.write_sync_manifest(cache, sync.generated_sync_manifest(source, "committed"))
    previous = dict(sync.load_sync_manifest_hashes(cache))
    for name in ("a.md", "b.md"):
        _write(source / name, f"{name}-generated-v2\n")

    original_staged_copy2 = sync.staged_copy2
    replaced = 0

    def crash_after_first_replace(src: Path, dst: Path, expected_dst_hash: str | None) -> bool:
        nonlocal replaced
        result = original_staged_copy2(src, dst, expected_dst_hash)
        if result:
            replaced += 1
            if replaced == 1:
                raise SimulatedSyncCrash("fixture crash after first replace")
        return result

    try:
        with mock.patch.object(sync, "staged_copy2", side_effect=crash_after_first_replace):
            sync.mirror_tree(source, cache)
    except SimulatedSyncCrash:
        pass
    else:
        raise AssertionError("simulated sync crash was not raised")

    applying = _manifest(cache)
    if applying.get("state") != "applying":
        raise AssertionError(f"interrupted manifest did not remain applying: {applying}")
    if applying.get("previous_files") != previous:
        raise AssertionError("interrupted transaction lost the previous committed baseline")
    desired = applying.get("desired_files")
    if not isinstance(desired, dict) or set(desired) != {"a.md", "b.md"}:
        raise AssertionError("interrupted transaction lost its desired output set")
    if applying.get("files") != desired:
        raise AssertionError("applying manifest legacy files view must expose desired hashes for suppression")
    if applying.get("applied_files"):
        raise AssertionError("a replace interrupted before second verification was recorded as applied")

    recovery = sync.mirror_tree(source, cache)
    if recovery.get("user_modified_conflict_count") != 0:
        raise AssertionError(f"interrupted generated output became a false user conflict: {recovery}")
    if recovery.get("removed") != 0:
        raise AssertionError("recovery violated preserve-only removed=0")
    for name in ("a.md", "b.md"):
        if (cache / name).read_text(encoding="utf-8") != f"{name}-generated-v2\n":
            raise AssertionError(f"recovery left {name} stale")
    committed = _manifest(cache)
    if committed.get("state") != "committed":
        raise AssertionError("recovery did not commit the new transaction")
    desired = committed.get("desired_files")
    applied = committed.get("applied_files")
    if not isinstance(desired, dict) or applied != desired or committed.get("files") != applied:
        raise AssertionError("recovery committed hashes that were not verified as applied")
    return {
        "replaced_before_crash": replaced,
        "updated_on_recovery": recovery.get("updated"),
        "conflicts": recovery.get("user_modified_conflict_count"),
        "removed": recovery.get("removed"),
    }


def check_second_verification(temp: Path) -> dict[str, Any]:
    source = temp / "verify-source"
    cache = temp / "verify-cache"
    source.mkdir()
    cache.mkdir()
    _write(source / "verify.md", "generated-v1\n")
    _write(cache / "verify.md", "generated-v1\n")
    sync.write_sync_manifest(cache, sync.generated_sync_manifest(source, "committed"))
    _write(source / "verify.md", "generated-v2\n")
    original_staged_copy2 = sync.staged_copy2

    def edit_after_replace(src: Path, dst: Path, expected_dst_hash: str | None) -> bool:
        result = original_staged_copy2(src, dst, expected_dst_hash)
        if result:
            _write(dst, "user edit after replace\n")
        return result

    with mock.patch.object(sync, "staged_copy2", side_effect=edit_after_replace):
        result = sync.mirror_tree(source, cache)
    if result.get("user_modified_conflict_count") != 1:
        raise AssertionError(f"post-replace edit escaped second verification: {result}")
    manifest = _manifest(cache)
    if "verify.md" in manifest.get("applied_files", {}) or "verify.md" in manifest.get("files", {}):
        raise AssertionError("post-replace unverified hash entered the committed manifest")
    if (cache / "verify.md").read_text(encoding="utf-8") != "user edit after replace\n":
        raise AssertionError("post-replace user edit was not preserved")
    return {"conflicts": result.get("user_modified_conflict_count"), "committed": 0}


def check_user_conflict_and_preserve_only(temp: Path) -> dict[str, Any]:
    source = temp / "conflict-source"
    cache = temp / "conflict-cache"
    source.mkdir()
    cache.mkdir()
    _write(source / "conflict.md", "generated-v1\n")
    _write(cache / "conflict.md", "generated-v1\n")
    _write(cache / "stale.md", "previous generated text must stay\n")
    sync.write_sync_manifest(cache, sync.generated_sync_manifest(cache, "committed"))
    _write(cache / "conflict.md", "user edit\n")
    _write(source / "conflict.md", "generated-v2\n")

    result = sync.mirror_tree(source, cache)
    if result.get("user_modified_conflict_count") != 1:
        raise AssertionError(f"user conflict was not preserved: {result}")
    if (cache / "conflict.md").read_text(encoding="utf-8") != "user edit\n":
        raise AssertionError("user conflict was overwritten")
    if not (cache / "stale.md").is_file() or result.get("removed") != 0:
        raise AssertionError("preserve-only sync removed a stale generated file")
    manifest = _manifest(cache)
    desired_hash = sync.file_sha256(source / "conflict.md")
    if manifest.get("desired_files", {}).get("conflict.md") != desired_hash:
        raise AssertionError("desired conflict hash was not retained for audit")
    if "conflict.md" in manifest.get("applied_files", {}) or "conflict.md" in manifest.get("files", {}):
        raise AssertionError("unapplied conflict hash was incorrectly committed")
    return {
        "conflicts": result.get("user_modified_conflict_count"),
        "preserved": result.get("preserved"),
        "removed": result.get("removed"),
    }


def check_obsidian_config_cas(temp: Path) -> dict[str, Any]:
    config_path = temp / "obsidian-config" / "obsidian.json"
    shared_vault = temp / "shared-vault"
    shared_vault.mkdir()
    _write(
        config_path,
        json.dumps(
            {
                "theme": "dark",
                "vaults": {
                    "other": {
                        "path": "other-vault",
                        "ts": 1,
                        "open": False,
                        "custom": "preserve-me",
                    }
                },
            },
            ensure_ascii=False,
        )
        + "\n",
    )

    def unrelated_writer(path: Path) -> None:
        current = json.loads(path.read_text(encoding="utf-8"))
        current["theme"] = "light"
        current["external_field"] = "preserve-external"
        _write(path, json.dumps(current, ensure_ascii=False) + "\n")

    with mock.patch.object(vault, "obsidian_config_path", return_value=config_path):
        merged = vault.register_obsidian_vault(
            shared_vault,
            True,
            False,
            precommit_hook=unrelated_writer,
        )
    merged_value = json.loads(config_path.read_text(encoding="utf-8"))
    target_id = vault.vault_id(shared_vault)
    if merged.get("conflict") is not False or merged.get("post_write_verified") is not True:
        raise AssertionError(f"unrelated Obsidian config writer was not merged: {merged}")
    if merged_value.get("theme") != "light" or merged_value.get("external_field") != "preserve-external":
        raise AssertionError("unrelated concurrent Obsidian fields were overwritten")
    if merged_value.get("vaults", {}).get("other", {}).get("custom") != "preserve-me":
        raise AssertionError("existing vault custom field was lost")
    if merged_value.get("vaults", {}).get(target_id, {}).get("open") is not True:
        raise AssertionError("target vault registration was not committed")

    def same_field_writer(path: Path) -> None:
        current = json.loads(path.read_text(encoding="utf-8"))
        current["vaults"][target_id]["path"] = "external-conflicting-path"
        _write(path, json.dumps(current, ensure_ascii=False) + "\n")

    with mock.patch.object(vault, "obsidian_config_path", return_value=config_path):
        conflict = vault.register_obsidian_vault(
            shared_vault,
            False,
            False,
            precommit_hook=same_field_writer,
        )
    conflict_value = json.loads(config_path.read_text(encoding="utf-8"))
    if conflict.get("conflict") is not True or conflict.get("written") is not False:
        raise AssertionError(f"same-field Obsidian config conflict was not rejected: {conflict}")
    if conflict_value["vaults"][target_id]["path"] != "external-conflicting-path":
        raise AssertionError("same-field external edit was overwritten")
    return {
        "unrelated_fields_preserved": True,
        "same_field_conflicts": int(conflict.get("conflict") is True),
        "post_write_verified": merged.get("post_write_verified"),
    }


def check_sync_config_cas(temp: Path) -> dict[str, Any]:
    config_path = temp / "sync-config" / "config.json"
    lock_path = temp / "sync-config" / "obsidian-config.lock"
    _write(
        config_path,
        json.dumps(
            {
                "api_key": "fixture",
                "vault_path": "old-vault",
                "unrelated": "preserve-me",
            },
            ensure_ascii=False,
        )
        + "\n",
    )
    base = config_state.read_config_snapshot(config_path)

    def unrelated_writer(path: Path) -> None:
        current = json.loads(path.read_text(encoding="utf-8"))
        current["external_field"] = "external-preserved"
        _write(path, json.dumps(current, ensure_ascii=False) + "\n")

    merged = config_state.patch_config(
        {"vault_path": "new-vault", "autosync_enabled": True},
        config_path=config_path,
        lock_path=lock_path,
        base_snapshot=base,
        precommit_hook=unrelated_writer,
    )
    committed = config_state.read_config_snapshot(config_path)
    if merged.get("conflict") is not False or merged.get("post_write_verified") is not True:
        raise AssertionError(f"unrelated sync-config writer was not merged: {merged}")
    if committed.get("external_field") != "external-preserved" or committed.get("unrelated") != "preserve-me":
        raise AssertionError("unrelated sync-config fields were overwritten")
    if committed.get("api_key") != "fixture":
        raise AssertionError("sync-config CAS lost the local API key")
    if committed.get("vault_path") != "new-vault" or int(committed.get("revision") or 0) != 1:
        raise AssertionError("sync-config CAS did not commit the intended revision")
    if not str(committed.get("transaction_id") or ""):
        raise AssertionError("sync-config CAS omitted transaction_id")
    public = config_state.public_config(committed)
    if "api_key" in public or "fixture" in json.dumps(public):
        raise AssertionError("sync-config public projection leaked API key")

    conflict_base = config_state.read_config_snapshot(config_path)

    def same_field_writer(path: Path) -> None:
        current = json.loads(path.read_text(encoding="utf-8"))
        current["vault_path"] = "external-conflicting-vault"
        _write(path, json.dumps(current, ensure_ascii=False) + "\n")

    conflict = config_state.patch_config(
        {"vault_path": "third-vault"},
        config_path=config_path,
        lock_path=lock_path,
        base_snapshot=conflict_base,
        precommit_hook=same_field_writer,
    )
    after_conflict = config_state.read_config_snapshot(config_path)
    if conflict.get("conflict") is not True or conflict.get("written") is not False:
        raise AssertionError(f"same-field sync-config conflict was not rejected: {conflict}")
    if after_conflict.get("vault_path") != "external-conflicting-vault":
        raise AssertionError("same-field external sync-config edit was overwritten")
    return {
        "unrelated_fields_preserved": True,
        "same_field_conflicts": 1,
        "revision": committed.get("revision"),
        "secret_publicly_exposed": False,
        "post_write_verified": merged.get("post_write_verified"),
    }


def check_staged_copy_durability(temp: Path) -> dict[str, Any]:
    source = temp / "durability" / "source.md"
    target = temp / "durability" / "target.md"
    _write(source, "new-complete-value\n")
    _write(target, "old-complete-value\n")
    old_hash = sync.file_sha256(target)
    parent_fsync_calls = 0
    original_parent_fsync = sync.fsync_parent_directory

    def counted_parent_fsync(path: Path) -> bool:
        nonlocal parent_fsync_calls
        parent_fsync_calls += 1
        return original_parent_fsync(path)

    with mock.patch.object(sync, "fsync_parent_directory", side_effect=counted_parent_fsync):
        copied = sync.staged_copy2(source, target, old_hash)
    if not copied or target.read_text(encoding="utf-8") != "new-complete-value\n":
        raise AssertionError("durable staged copy did not commit the complete new value")
    if parent_fsync_calls != 1:
        raise AssertionError("durable staged copy did not attempt exactly one parent-directory fsync")

    _write(source, "third-complete-value\n")
    committed_before_failure = target.read_bytes()
    with mock.patch.object(sync.os, "replace", side_effect=OSError("fixture replace failure")):
        try:
            sync.staged_copy2(source, target, sync.file_sha256(target))
        except OSError:
            pass
        else:
            raise AssertionError("replace failure was not propagated")
    if target.read_bytes() != committed_before_failure:
        raise AssertionError("replace failure exposed a partial target value")
    return {
        "parent_fsync_attempts": parent_fsync_calls,
        "post_write_hash_verified": True,
        "replace_failure_preserved_old": True,
    }


def run_checks() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="court-obsidian-sync-transaction-") as raw_temp:
        temp = Path(raw_temp)
        with _isolated_paths(temp):
            first = check_first_sync(temp)
            legacy = check_legacy_committed_compatibility(temp)
            crash = check_crash_and_recovery(temp)
            second_verification = check_second_verification(temp)
            conflict = check_user_conflict_and_preserve_only(temp)
            config_cas = check_obsidian_config_cas(temp)
            sync_config_cas = check_sync_config_cas(temp)
            staged_copy_durability = check_staged_copy_durability(temp)
    return {
        "ok": True,
        "schema": "court.obsidian_sync.transaction_check.v1",
        "first_sync": first,
        "legacy_compatibility": legacy,
        "crash_recovery": crash,
        "second_verification": second_verification,
        "user_conflict": conflict,
        "obsidian_config_cas": config_cas,
        "sync_config_cas": sync_config_cas,
        "staged_copy_durability": staged_copy_durability,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = run_checks()
    except Exception as exc:
        result = {
            "ok": False,
            "schema": "court.obsidian_sync.transaction_check.v1",
            "error": str(exc),
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print(
            "OBSIDIAN_SYNC_TRANSACTION_OK "
            f"crash_conflicts={result['crash_recovery']['conflicts']} "
            f"user_conflicts={result['user_conflict']['conflicts']} "
            f"removed={result['user_conflict']['removed']}"
        )
    else:
        print(f"OBSIDIAN_SYNC_TRANSACTION_FAILED {result['error']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
