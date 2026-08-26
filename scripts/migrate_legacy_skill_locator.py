#!/usr/bin/env python3
"""Plan, apply, or roll back legacy skill locator migration.

The canonical skill/install directory is ``decretum-matrix``. The old
``court-capability-router`` directory is allowed only as a compatibility locator
that resolves to the same physical authority. This tool gives that rename path a
dedicated, auditable entrypoint while reusing the install sync primitives.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any

sys.dont_write_bytecode = True

from sync_active_copies import (  # noqa: E402
    CANONICAL_INSTALL_DIRECTORY_NAME,
    LEGACY_INSTALL_DIRECTORY_NAME,
    _absolute_no_follow,
    _create_legacy_alias,
    _legacy_backup_root,
    _load_verified_selected_roots,
    _lstat,
    _physical_target_groups,
    _remove_legacy_alias,
    _stat_is_link_or_reparse,
    _write_legacy_migration_receipt,
)


SCHEMA = "court.legacy_skill_locator_migration.v1"
MUTATING_MODES = {"MIGRATE_LEGACY_TO_CANONICAL", "BACKUP_LEGACY_AND_ALIAS"}


def _path_key(path: Path) -> str:
    return os.path.normcase(str(_absolute_no_follow(path)))


def _same_physical_path(left: Path, right: Path) -> bool:
    return _path_key(left.resolve(strict=False)) == _path_key(right.resolve(strict=False))


def _canonical_root(path: Path) -> Path:
    root = _absolute_no_follow(path)
    if root.name != CANONICAL_INSTALL_DIRECTORY_NAME:
        raise ValueError(
            "canonical root basename must be "
            f"{CANONICAL_INSTALL_DIRECTORY_NAME!r}: {root}"
        )
    return root


def _resolve_roots(explicit_roots: list[Path] | None) -> tuple[list[Path], list[str]]:
    if explicit_roots:
        roots = explicit_roots
        source = "explicit-root"
    else:
        selected = _load_verified_selected_roots()
        if selected is None:
            return [], ["selected_roots_receipt_required"]
        roots = selected
        source = "install-receipt"
    try:
        canonical_roots = [_canonical_root(root) for root in roots]
    except (TypeError, ValueError) as exc:
        return [], [f"canonical_root_invalid:{type(exc).__name__}:{exc}"]
    groups = _physical_target_groups(canonical_roots)
    physical_roots = sorted((physical for physical, _logical in groups), key=_path_key)
    return physical_roots, [f"root_source:{source}"]


def _entry_for_root(canonical: Path) -> dict[str, Any]:
    legacy = canonical.with_name(LEGACY_INSTALL_DIRECTORY_NAME)
    canonical_stat = _lstat(canonical)
    legacy_stat = _lstat(legacy)
    base = {
        "canonical_root": str(canonical),
        "legacy_root": str(legacy),
    }
    if legacy_stat is None:
        return {**base, "mode": "NOT_REQUIRED", "ok": True}
    if _stat_is_link_or_reparse(legacy_stat):
        try:
            if canonical_stat is not None and _same_physical_path(legacy, canonical):
                return {**base, "mode": "ALIAS_OK", "ok": True}
        except OSError as exc:
            return {
                **base,
                "mode": "REJECTED",
                "ok": False,
                "reason": f"legacy_alias_unresolved:{type(exc).__name__}:{exc}",
            }
        return {
            **base,
            "mode": "REJECTED",
            "ok": False,
            "reason": "legacy_alias_target_mismatch",
        }
    if not stat.S_ISDIR(legacy_stat.st_mode):
        return {
            **base,
            "mode": "REJECTED",
            "ok": False,
            "reason": "legacy_locator_not_directory",
        }
    if canonical_stat is None:
        return {**base, "mode": "MIGRATE_LEGACY_TO_CANONICAL", "ok": True}
    if _stat_is_link_or_reparse(canonical_stat) or not stat.S_ISDIR(canonical_stat.st_mode):
        return {
            **base,
            "mode": "REJECTED",
            "ok": False,
            "reason": "canonical_root_not_physical_directory",
        }
    return {**base, "mode": "BACKUP_LEGACY_AND_ALIAS", "ok": True}


def plan_migration(explicit_roots: list[Path] | None = None) -> dict[str, Any]:
    roots, notes = _resolve_roots(explicit_roots)
    if not roots:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "FAIL",
            "write": False,
            "canonical_name": CANONICAL_INSTALL_DIRECTORY_NAME,
            "legacy_name": LEGACY_INSTALL_DIRECTORY_NAME,
            "entries": [],
            "failures": notes,
        }
    entries = [_entry_for_root(root) for root in roots]
    failures = [
        f"{entry['legacy_root']}:{entry.get('reason', entry['mode'])}"
        for entry in entries
        if not entry.get("ok", False)
    ]
    planned = [entry for entry in entries if entry.get("mode") in MUTATING_MODES]
    status = "FAIL" if failures else "PLANNED" if planned else "NOT_REQUIRED"
    return {
        "schema": SCHEMA,
        "ok": not failures,
        "status": status,
        "write": False,
        "canonical_name": CANONICAL_INSTALL_DIRECTORY_NAME,
        "legacy_name": LEGACY_INSTALL_DIRECTORY_NAME,
        "entries": entries,
        "planned_count": len(planned),
        "rollback_supported": True,
        "notes": notes,
        "failures": failures,
    }


def _rollback_applied(
    applied: list[dict[str, Any]],
    aliases: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    for alias in reversed(aliases):
        try:
            _remove_legacy_alias(Path(alias["legacy_root"]))
        except (OSError, ValueError) as exc:
            errors.append(f"alias:{type(exc).__name__}:{exc}")
    for entry in reversed(applied):
        canonical = Path(str(entry["canonical_root"]))
        legacy = Path(str(entry["legacy_root"]))
        mode = str(entry["mode"])
        try:
            if _lstat(legacy) is not None:
                raise RuntimeError("legacy restore destination occupied")
            if mode == "MIGRATE_LEGACY_TO_CANONICAL":
                if _lstat(canonical) is None:
                    raise RuntimeError("canonical restore source missing")
                os.replace(canonical, legacy)
            elif mode == "BACKUP_LEGACY_AND_ALIAS":
                backup = Path(str(entry["backup_root"]))
                if _lstat(backup) is None:
                    raise RuntimeError("legacy backup missing")
                os.replace(backup, legacy)
        except (OSError, RuntimeError) as exc:
            errors.append(f"restore:{type(exc).__name__}:{exc}")
    return errors


def apply_migration(
    explicit_roots: list[Path] | None = None,
    *,
    write: bool,
) -> dict[str, Any]:
    plan = plan_migration(explicit_roots)
    if not plan.get("ok", False):
        return plan
    entries = [
        dict(entry)
        for entry in plan["entries"]
        if entry.get("mode") in MUTATING_MODES
    ]
    if not entries:
        return {**plan, "status": "NOT_REQUIRED", "write": write}
    if not write:
        return plan
    backup = _absolute_no_follow(_legacy_backup_root())
    backup.mkdir(parents=True, exist_ok=False)
    applied: list[dict[str, Any]] = []
    aliases: list[dict[str, str]] = []
    receipt = {
        "schema": SCHEMA,
        "ok": False,
        "status": "PENDING",
        "write": True,
        "canonical_name": CANONICAL_INSTALL_DIRECTORY_NAME,
        "legacy_name": LEGACY_INSTALL_DIRECTORY_NAME,
        "entries": entries,
        "backup_root": str(backup),
        "rollback_supported": True,
        "failures": [],
    }
    try:
        for index, entry in enumerate(entries):
            canonical = Path(str(entry["canonical_root"]))
            legacy = Path(str(entry["legacy_root"]))
            mode = str(entry["mode"])
            current = _entry_for_root(canonical)
            if current.get("mode") != mode:
                raise RuntimeError(
                    f"preimage_drift:{legacy}:{current.get('mode')}:{mode}"
                )
            if mode == "MIGRATE_LEGACY_TO_CANONICAL":
                os.replace(legacy, canonical)
                entry["rollback_root"] = str(canonical)
            elif mode == "BACKUP_LEGACY_AND_ALIAS":
                backup_entry = backup / f"legacy-{index}"
                if _lstat(backup_entry) is not None:
                    raise RuntimeError(f"backup entry exists: {backup_entry}")
                os.replace(legacy, backup_entry)
                entry["backup_root"] = str(backup_entry)
            applied.append(entry)
        for entry in entries:
            canonical = Path(str(entry["canonical_root"]))
            legacy = Path(str(entry["legacy_root"]))
            _create_legacy_alias(legacy, canonical)
            aliases.append({"legacy_root": str(legacy), "canonical_root": str(canonical)})
    except (OSError, RuntimeError, ValueError) as exc:
        rollback_errors = _rollback_applied(applied, aliases)
        receipt.update(
            {
                "ok": False,
                "status": "ROLLED_BACK" if not rollback_errors else "ROLLBACK_FAILED",
                "entries": entries,
                "error": f"{type(exc).__name__}: {exc}",
                "rollback_errors": rollback_errors,
                "failures": [f"legacy migration failed: {type(exc).__name__}: {exc}"],
            }
        )
        _write_legacy_migration_receipt(backup / "receipt.json", receipt)
        return receipt
    receipt.update(
        {
            "ok": True,
            "status": "MIGRATED",
            "entries": entries,
            "aliases": aliases,
            "receipt_path": str(backup / "receipt.json"),
            "rollback_command": (
                "python -B scripts/migrate_legacy_skill_locator.py rollback "
                f"--receipt {backup / 'receipt.json'} --write"
            ),
            "post_migration_action": (
                "run the normal installer or sync_active_copies.py from the current "
                "release source to refresh managed files"
            ),
            "failures": [],
        }
    )
    _write_legacy_migration_receipt(backup / "receipt.json", receipt)
    return receipt


def rollback_receipt(receipt_path: Path, *, write: bool) -> dict[str, Any]:
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "FAIL",
            "write": write,
            "failures": [f"receipt_unreadable:{type(exc).__name__}:{exc}"],
        }
    if receipt.get("schema") != SCHEMA:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "FAIL",
            "write": write,
            "failures": ["receipt_schema_mismatch"],
        }
    entries = receipt.get("entries")
    if not isinstance(entries, list):
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "FAIL",
            "write": write,
            "failures": ["receipt_entries_invalid"],
        }
    pending = [
        dict(entry)
        for entry in entries
        if isinstance(entry, dict) and entry.get("mode") in MUTATING_MODES
    ]
    planned = {
        "schema": SCHEMA,
        "ok": True,
        "status": "ROLLBACK_PLANNED",
        "write": False,
        "receipt": str(receipt_path),
        "entries": pending,
        "failures": [],
    }
    if not write:
        return planned
    aliases = [
        {"legacy_root": str(entry["legacy_root"]), "canonical_root": str(entry["canonical_root"])}
        for entry in pending
    ]
    errors = _rollback_applied(pending, aliases)
    result = {
        "schema": SCHEMA,
        "ok": not errors,
        "status": "ROLLED_BACK" if not errors else "ROLLBACK_FAILED",
        "write": True,
        "receipt": str(receipt_path),
        "entries": pending,
        "failures": errors,
    }
    rollback_path = receipt_path.with_name(f"{receipt_path.stem}.rollback.json")
    _write_legacy_migration_receipt(rollback_path, result)
    result["rollback_receipt_path"] = str(rollback_path)
    return result


def run_self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    previous = {key: os.environ.get(key) for key in ("HOME", "USERPROFILE")}
    with tempfile.TemporaryDirectory(prefix="decretum-legacy-locator-") as raw:
        fixture = Path(raw)
        home = fixture / "home"
        home.mkdir()
        os.environ["HOME"] = str(home)
        os.environ["USERPROFILE"] = str(home)
        try:
            duplicate_parent = fixture / "duplicate" / "skills"
            duplicate_canonical = duplicate_parent / CANONICAL_INSTALL_DIRECTORY_NAME
            duplicate_legacy = duplicate_parent / LEGACY_INSTALL_DIRECTORY_NAME
            duplicate_canonical.mkdir(parents=True)
            duplicate_legacy.mkdir()
            (duplicate_legacy / "preserved.txt").write_text("preserved\n", encoding="utf-8")
            duplicate_apply = apply_migration([duplicate_canonical], write=True)
            duplicate_alias_ok = (
                duplicate_apply.get("ok") is True
                and _lstat(duplicate_legacy) is not None
                and _stat_is_link_or_reparse(_lstat(duplicate_legacy))
                and _same_physical_path(duplicate_legacy, duplicate_canonical)
            )
            duplicate_receipt = Path(str(duplicate_apply.get("receipt_path")))
            duplicate_rollback = rollback_receipt(duplicate_receipt, write=True)
            checks["duplicate_legacy_backed_up_and_rollbackable"] = (
                duplicate_alias_ok
                and duplicate_rollback.get("ok") is True
                and (duplicate_legacy / "preserved.txt").is_file()
                and not _stat_is_link_or_reparse(_lstat(duplicate_legacy))
            )

            rename_parent = fixture / "rename" / "skills"
            rename_canonical = rename_parent / CANONICAL_INSTALL_DIRECTORY_NAME
            rename_legacy = rename_parent / LEGACY_INSTALL_DIRECTORY_NAME
            rename_legacy.mkdir(parents=True)
            (rename_legacy / "old.txt").write_text("old\n", encoding="utf-8")
            rename_apply = apply_migration([rename_canonical], write=True)
            rename_alias_ok = (
                rename_apply.get("ok") is True
                and (rename_canonical / "old.txt").is_file()
                and _lstat(rename_legacy) is not None
                and _stat_is_link_or_reparse(_lstat(rename_legacy))
                and _same_physical_path(rename_legacy, rename_canonical)
            )
            rename_receipt = Path(str(rename_apply.get("receipt_path")))
            rename_rollback = rollback_receipt(rename_receipt, write=True)
            checks["legacy_only_root_renamed_and_rollbackable"] = (
                rename_alias_ok
                and rename_rollback.get("ok") is True
                and (rename_legacy / "old.txt").is_file()
                and _lstat(rename_canonical) is None
            )

            alias_parent = fixture / "alias" / "skills"
            alias_canonical = alias_parent / CANONICAL_INSTALL_DIRECTORY_NAME
            alias_legacy = alias_parent / LEGACY_INSTALL_DIRECTORY_NAME
            alias_canonical.mkdir(parents=True)
            _create_legacy_alias(alias_legacy, alias_canonical)
            alias_plan = plan_migration([alias_canonical])
            checks["existing_alias_is_not_remigrated"] = (
                alias_plan.get("ok") is True
                and alias_plan.get("planned_count") == 0
                and alias_plan["entries"][0]["mode"] == "ALIAS_OK"
            )

            missing_receipt_plan = plan_migration(None)
            checks["default_without_receipt_fails_closed"] = (
                missing_receipt_plan.get("ok") is False
                and "selected_roots_receipt_required" in missing_receipt_plan.get("failures", [])
            )
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    return {
        "schema": "court.legacy_skill_locator_migration.self_test.v1",
        "ok": all(checks.values()),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        nargs="?",
        choices=("plan", "apply", "rollback", "self-test"),
        default="plan",
    )
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        help=(
            "Canonical decretum-matrix root to inspect. May be repeated. "
            "Without --root, selected_roots must come from the latest install receipt."
        ),
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        help="Migration receipt for rollback.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply a migration or rollback. Omit for read-only planning.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON (the default output format; retained for explicit callers).",
    )
    args = parser.parse_args(argv)

    if args.action == "self-test":
        result = run_self_test()
    elif args.action == "rollback":
        if args.receipt is None:
            result = {
                "schema": SCHEMA,
                "ok": False,
                "status": "FAIL",
                "write": args.write,
                "failures": ["receipt_required"],
            }
        else:
            result = rollback_receipt(args.receipt, write=args.write)
    elif args.action == "apply":
        result = apply_migration(args.root, write=args.write)
    else:
        result = plan_migration(args.root)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
