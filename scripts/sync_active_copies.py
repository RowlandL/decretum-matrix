"""Synchronize Decretum Matrix source files to known active installations.

This tool copies the manifest-selected runtime surface to the five local skill
roots. It compares file bytes directly to decide whether a copy is needed and
does not perform startup validation of unrelated files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True

from court_platform import user_data_base


CANONICAL_INSTALL_DIRECTORY_NAME = "decretum-matrix"
LEGACY_INSTALL_DIRECTORY_NAME = "court-capability-router"
PROJECTION_MANIFEST_RELATIVE = Path("references/manifests/install-projection.v1.json")
FROZEN_INSTALL_REFERENCES_KEY = "frozen_install_references"


def default_roots() -> list[Path]:
    home = Path.home()
    return [
        home / ".agents" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        home / ".codex" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        home / ".claude" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        home / ".hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        user_data_base() / "hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
    ]


def qoder_root() -> Path:
    return Path.home() / ".qoder" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME


def _absolute_no_follow(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _stat_is_link_or_reparse(value: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(value.st_mode) or bool(
        reparse_flag and getattr(value, "st_file_attributes", 0) & reparse_flag
    )


def _is_link_or_reparse(path: Path) -> bool:
    value = _lstat(path)
    return value is not None and _stat_is_link_or_reparse(value)


def _known_alias_target(root: Path) -> Path | None:
    """Return the physical target for the two explicitly governed aliases."""
    absolute = _absolute_no_follow(root)
    home = Path.home()
    aliases = {
        _absolute_no_follow(home / ".hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME):
            _absolute_no_follow(user_data_base() / "hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME),
        _absolute_no_follow(home / ".qoder" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME):
            _absolute_no_follow(home / ".agents" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME),
    }
    target = aliases.get(absolute)
    if target is None or not _is_link_or_reparse(absolute):
        return None
    try:
        resolved = absolute.resolve(strict=True)
    except OSError:
        return None
    return target if _absolute_no_follow(resolved) == _absolute_no_follow(target.resolve()) else None


def _physical_authority_root(root: Path) -> Path:
    absolute = _absolute_no_follow(root)
    return _known_alias_target(absolute) or absolute


def _path_key(path: Path) -> str:
    return os.path.normcase(str(_absolute_no_follow(path)))


def _physical_target_groups(targets: list[Path]) -> list[tuple[Path, list[Path]]]:
    groups: dict[str, tuple[Path, list[Path]]] = {}
    for target in targets:
        physical = _physical_authority_root(target)
        key = _path_key(physical)
        if key not in groups:
            groups[key] = (physical, [])
        groups[key][1].append(_absolute_no_follow(target))
    return list(groups.values())


def _safe_relative(value: str | Path, *, label: str) -> Path:
    relative = Path(value)
    if (
        relative == Path(".")
        or relative.is_absolute()
        or bool(relative.anchor)
        or bool(relative.drive)
        or ".." in relative.parts
    ):
        raise ValueError(f"unsafe {label}: {value}")
    return relative


def _is_under(path: Path, root: Path) -> bool:
    try:
        _absolute_no_follow(path).relative_to(_absolute_no_follow(root))
    except ValueError:
        return False
    return True


def _assert_safe_root(root: Path, *, allow_missing: bool, label: str) -> Path:
    absolute = _absolute_no_follow(root)
    alias_target = _known_alias_target(absolute)
    for candidate in [*reversed(absolute.parents), absolute]:
        value = _lstat(candidate)
        if value is None:
            continue
        if _stat_is_link_or_reparse(value):
            if candidate == absolute and alias_target is not None:
                continue
            raise ValueError(f"{label} contains a link or reparse point: {candidate}")
        if not stat.S_ISDIR(value.st_mode):
            raise ValueError(f"{label} ancestor is not a directory: {candidate}")
    if not allow_missing and _lstat(absolute) is None:
        raise ValueError(f"{label} is missing: {absolute}")
    if alias_target is not None:
        target_value = _lstat(alias_target)
        if target_value is None or _stat_is_link_or_reparse(target_value) or not stat.S_ISDIR(target_value.st_mode):
            raise ValueError(f"{label} alias target is unsafe: {alias_target}")
    return absolute


def _assert_safe_descendant(
    root: Path,
    path: Path,
    *,
    allow_missing: bool,
    require_file: bool,
    label: str,
) -> Path:
    root_absolute = _absolute_no_follow(root)
    path_absolute = _absolute_no_follow(path)
    if not _is_under(path_absolute, root_absolute):
        raise ValueError(f"{label} escapes root: {path_absolute}")
    relative = path_absolute.relative_to(root_absolute)
    current = root_absolute
    for index, part in enumerate(relative.parts):
        current = current / part
        value = _lstat(current)
        leaf = index == len(relative.parts) - 1
        if value is None:
            if not allow_missing:
                raise ValueError(f"{label} is missing: {current}")
            continue
        if _stat_is_link_or_reparse(value):
            raise ValueError(f"{label} contains a link or reparse point: {current}")
        if not leaf and not stat.S_ISDIR(value.st_mode):
            raise ValueError(f"{label} parent is not a directory: {current}")
        if leaf and require_file and not stat.S_ISREG(value.st_mode):
            raise ValueError(f"{label} is not a regular file: {current}")
    return path_absolute


def _scan_safe_tree(root: Path, *, label: str) -> tuple[list[Path], list[Path]]:
    root_absolute = _assert_safe_root(root, allow_missing=False, label=label)
    files: list[Path] = []
    directories: list[Path] = []
    stack = [root_absolute]
    while stack:
        current = stack.pop()
        with os.scandir(current) as entries:
            for entry in sorted(entries, key=lambda item: item.name.casefold()):
                path = Path(entry.path)
                value = entry.stat(follow_symlinks=False)
                if _stat_is_link_or_reparse(value):
                    raise ValueError(f"{label} contains a link or reparse point: {path}")
                if stat.S_ISDIR(value.st_mode):
                    directories.append(path)
                    stack.append(path)
                elif stat.S_ISREG(value.st_mode):
                    files.append(path)
                else:
                    raise ValueError(f"{label} contains a non-regular path: {path}")
    return files, directories


def _ensure_safe_directory(root: Path, directory: Path) -> None:
    root_absolute = _absolute_no_follow(root)
    directory_absolute = _absolute_no_follow(directory)
    alias_target = _known_alias_target(root_absolute)
    if not _is_under(directory_absolute, root_absolute):
        raise ValueError(f"target directory escapes root: {directory_absolute}")
    for candidate in [*reversed(root_absolute.parents), root_absolute]:
        value = _lstat(candidate)
        if value is None:
            candidate.mkdir()
            value = _lstat(candidate)
        if (
            value is None
            or (
                _stat_is_link_or_reparse(value)
                and not (candidate == root_absolute and alias_target is not None)
            )
            or not stat.S_ISDIR(value.st_mode)
        ):
            raise ValueError(f"unsafe target root component: {candidate}")
    current = root_absolute
    for part in directory_absolute.relative_to(root_absolute).parts:
        current = current / part
        value = _lstat(current)
        if value is None:
            current.mkdir()
            value = _lstat(current)
        if value is None or _stat_is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
            raise ValueError(f"unsafe target directory: {current}")


def _copy_regular_file(source: Path, target: Path) -> None:
    with tempfile.NamedTemporaryFile(
        prefix=".decretum-sync-",
        dir=target.parent,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copy2(source, temporary)
        target_value = _lstat(target)
        if target_value is not None:
            if _stat_is_link_or_reparse(target_value) or not stat.S_ISREG(target_value.st_mode):
                raise ValueError(f"refusing to replace unsafe target: {target}")
            make_writable(target)
        os.replace(temporary, target)
        installed = _lstat(target)
        if installed is None or _stat_is_link_or_reparse(installed) or not stat.S_ISREG(installed.st_mode):
            raise ValueError(f"installed target is not a regular file: {target}")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def legacy_locator_conflicts(roots: list[Path]) -> list[str]:
    conflicts: list[str] = []
    for root in roots:
        legacy = root.with_name(LEGACY_INSTALL_DIRECTORY_NAME)
        if (legacy.exists() or legacy.is_symlink()) and (
            legacy.resolve(strict=False) != root.resolve(strict=False)
        ):
            conflicts.append(str(legacy))
    return conflicts


def _legacy_migration_candidates(roots: list[Path]) -> list[tuple[Path, Path]]:
    candidates: list[tuple[Path, Path]] = []
    for canonical in roots:
        canonical = _assert_safe_root(
            canonical,
            allow_missing=True,
            label="canonical target root",
        )
        legacy = canonical.with_name(LEGACY_INSTALL_DIRECTORY_NAME)
        value = _lstat(legacy)
        if value is None:
            continue
        if _stat_is_link_or_reparse(value):
            try:
                resolved = legacy.resolve(strict=True)
            except OSError as exc:
                raise ValueError(f"legacy locator is unresolved: {legacy}") from exc
            if _absolute_no_follow(resolved) == _absolute_no_follow(
                canonical.resolve(strict=False)
            ):
                continue
            raise ValueError(f"legacy locator is not a physical directory: {legacy}")
        if not stat.S_ISDIR(value.st_mode):
            raise ValueError(f"legacy locator is not a directory: {legacy}")
        candidates.append((canonical, legacy))
    return candidates


def _legacy_backup_root() -> Path:
    home = _absolute_no_follow(Path.home())
    base = home / ".agents" / "install-backups" / CANONICAL_INSTALL_DIRECTORY_NAME
    _ensure_safe_directory(home, base)
    backup = base / f"legacy-locator-{uuid.uuid4().hex}"
    if _lstat(backup) is not None:
        raise ValueError(f"legacy backup path already exists: {backup}")
    return backup


def _write_legacy_migration_receipt(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _create_legacy_alias(legacy: Path, canonical: Path) -> None:
    if _lstat(legacy) is not None:
        raise ValueError(f"legacy alias destination is occupied: {legacy}")
    if os.name == "nt":
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/j", str(legacy), str(canonical)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"legacy junction creation failed: {legacy}")
    else:
        legacy.symlink_to(canonical, target_is_directory=True)
    try:
        resolved = legacy.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"legacy alias is unresolved: {legacy}") from exc
    if _absolute_no_follow(resolved) != _absolute_no_follow(canonical.resolve()):
        raise RuntimeError(f"legacy alias target mismatch: {legacy}")


def _remove_legacy_alias(legacy: Path) -> None:
    value = _lstat(legacy)
    if value is None:
        return
    if not _stat_is_link_or_reparse(value):
        raise ValueError(f"refusing to remove non-alias legacy locator: {legacy}")
    if stat.S_ISDIR(value.st_mode) or _stat_is_link_or_reparse(value):
        legacy.rmdir()
    else:
        legacy.unlink()


def _apply_legacy_migration(
    candidates: list[tuple[Path, Path]],
    *,
    backup_root: Path | None = None,
) -> dict[str, object]:
    if not candidates:
        return {
            "ok": True,
            "status": "NOT_REQUIRED",
            "entries": [],
            "backup_root": None,
            "rollback_supported": True,
        }
    backup = _absolute_no_follow(backup_root or _legacy_backup_root())
    if _lstat(backup) is not None:
        raise ValueError(f"legacy backup path already exists: {backup}")
    backup.mkdir(parents=True, exist_ok=False)
    entries = [
        {
            "canonical_root": str(canonical),
            "legacy_root": str(legacy),
            "backup_root": str(backup / f"legacy-{index}"),
        }
        for index, (canonical, legacy) in enumerate(candidates)
    ]
    moved: list[dict[str, str]] = []
    aliases: list[dict[str, str]] = []
    try:
        for entry in entries:
            legacy = Path(str(entry["legacy_root"]))
            backup_entry = Path(str(entry["backup_root"]))
            if _lstat(legacy) is None or _lstat(backup_entry) is not None:
                raise RuntimeError(f"legacy preimage drift: {legacy}")
            os.replace(legacy, backup_entry)
            moved.append({"legacy_root": str(legacy), "backup_root": str(backup_entry)})
        for entry in entries:
            legacy = Path(str(entry["legacy_root"]))
            canonical = Path(str(entry["canonical_root"]))
            _create_legacy_alias(legacy, canonical)
            aliases.append({"legacy_root": str(legacy), "canonical_root": str(canonical)})
    except (OSError, ValueError, RuntimeError) as exc:
        rollback_errors: list[str] = []
        for alias in reversed(aliases):
            try:
                _remove_legacy_alias(Path(alias["legacy_root"]))
            except (OSError, ValueError) as rollback_exc:
                rollback_errors.append(
                    f"alias:{type(rollback_exc).__name__}:{rollback_exc}"
                )
        for move in reversed(moved):
            legacy = Path(move["legacy_root"])
            backup_entry = Path(move["backup_root"])
            try:
                if _lstat(legacy) is not None:
                    raise RuntimeError("legacy restore destination occupied")
                os.replace(backup_entry, legacy)
            except (OSError, RuntimeError) as rollback_exc:
                rollback_errors.append(
                    f"restore:{type(rollback_exc).__name__}:{rollback_exc}"
                )
        receipt = {
            "ok": False,
            "status": "ROLLED_BACK" if not rollback_errors else "ROLLBACK_FAILED",
            "backup_root": str(backup),
            "entries": entries,
            "rollback_errors": rollback_errors,
            "error": f"{type(exc).__name__}: {exc}",
            "rollback_supported": True,
        }
        _write_legacy_migration_receipt(backup / "receipt.json", receipt)
        return receipt
    receipt = {
        "ok": True,
        "status": "MIGRATED",
        "backup_root": str(backup),
        "entries": entries,
        "rollback_supported": True,
        "rollback_scope": "restore_legacy_locator_directories_from_backup",
    }
    _write_legacy_migration_receipt(backup / "receipt.json", receipt)
    return receipt


def _rollback_legacy_migration(receipt: dict[str, object]) -> dict[str, object]:
    entries = receipt.get("entries")
    if not isinstance(entries, list):
        return {"ok": False, "status": "ROLLBACK_FAILED", "error": "entries_invalid"}
    errors: list[str] = []
    for value in reversed(entries):
        if not isinstance(value, dict):
            errors.append("entry_invalid")
            continue
        legacy = Path(str(value.get("legacy_root", "")))
        backup = Path(str(value.get("backup_root", "")))
        try:
            _remove_legacy_alias(legacy)
            if _lstat(backup) is None:
                raise RuntimeError("legacy backup is missing")
            os.replace(backup, legacy)
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"{legacy}:{type(exc).__name__}:{exc}")
    return {
        "ok": not errors,
        "status": "ROLLED_BACK" if not errors else "ROLLBACK_FAILED",
        "errors": errors,
        "backup_root": receipt.get("backup_root"),
    }


def load_projection(source: Path) -> dict[str, object]:
    path = source / PROJECTION_MANIFEST_RELATIVE
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != "court.install_projection.v1":
        raise ValueError(f"invalid projection manifest: {path}")
    projections = value.get("projections")
    if not isinstance(projections, dict):
        raise ValueError("projection manifest has no projections")
    if value.get("protected_shared_agents_seeds") != []:
        raise ValueError("protected_shared_agents_seeds must be empty")
    return value


def projection_entries(manifest: dict[str, object]) -> set[str]:
    projections = manifest.get("projections")
    if not isinstance(projections, dict):
        return set()
    entries: set[str] = set()
    for name in ("shared_agents", "portable_current_tool"):
        values = projections.get(name)
        if isinstance(values, list):
            entries.update(str(value) for value in values if isinstance(value, str))
    return entries


def iter_projected_files(source: Path, manifest: dict[str, object] | None = None) -> list[Path]:
    source = _assert_safe_root(source, allow_missing=False, label="source root")
    entries = projection_entries(manifest or load_projection(source))
    if not entries:
        raise ValueError("managed projection is empty")
    files: set[Path] = set()
    for relative_text in sorted(entries):
        relative = _safe_relative(relative_text, label="managed projection path")
        candidate = _assert_safe_descendant(
            source,
            source / relative,
            allow_missing=False,
            require_file=False,
            label="managed projection path",
        )
        value = _lstat(candidate)
        if value is not None and stat.S_ISREG(value.st_mode):
            files.add(relative)
            continue
        if value is None or not stat.S_ISDIR(value.st_mode):
            raise ValueError(f"managed projection path is missing: {relative_text}")
        projected_files, _ = _scan_safe_tree(candidate, label="managed projection")
        for child in projected_files:
            if "__pycache__" not in child.parts and child.suffix.lower() != ".pyc":
                files.add(child.relative_to(source))
    if not files:
        raise ValueError("managed projection contains no files")
    return sorted(files)


def frozen_install_references(manifest: dict[str, object], source_files: set[Path]) -> set[Path]:
    raw = manifest.get(FROZEN_INSTALL_REFERENCES_KEY, [])
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{FROZEN_INSTALL_REFERENCES_KEY} must be a list of relative paths")
    frozen: set[Path] = set()
    for item in raw:
        relative = _safe_relative(item, label="frozen install reference")
        if relative not in source_files:
            raise ValueError(f"frozen install reference is not projected: {item}")
        frozen.add(relative)
    return frozen


def make_writable(path: Path) -> None:
    value = _lstat(path)
    if value is None:
        return
    if _stat_is_link_or_reparse(value) or not stat.S_ISREG(value.st_mode):
        raise ValueError(f"refusing to chmod non-regular path: {path}")
    if getattr(value, "st_nlink", 1) > 1:
        raise ValueError(f"refusing to chmod multiply-linked path: {path}")
    path.chmod(value.st_mode | stat.S_IWUSR)


def freeze_installed_reference(path: Path) -> None:
    value = _lstat(path)
    if value is None or _stat_is_link_or_reparse(value) or not stat.S_ISREG(value.st_mode):
        raise ValueError(f"cannot freeze non-regular installed reference: {path}")
    if getattr(value, "st_nlink", 1) > 1:
        raise ValueError(f"refusing to chmod multiply-linked path: {path}")
    path.chmod(value.st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def same_bytes(left: Path, right: Path) -> bool:
    left_value = _lstat(left)
    if (
        left_value is None
        or _stat_is_link_or_reparse(left_value)
        or not stat.S_ISREG(left_value.st_mode)
    ):
        raise ValueError(f"source is not a safe regular file: {left}")
    right_value = _lstat(right)
    if right_value is None:
        return False
    if _stat_is_link_or_reparse(right_value) or not stat.S_ISREG(right_value.st_mode):
        raise ValueError(f"target is not a safe regular file: {right}")
    if left_value.st_size != right_value.st_size:
        return False
    with left.open("rb") as left_handle, right.open("rb") as right_handle:
        while True:
            left_chunk = left_handle.read(1024 * 1024)
            right_chunk = right_handle.read(1024 * 1024)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def obsolete_managed_files(root: Path, desired_files: set[Path]) -> set[Path]:
    root = _assert_safe_root(root, allow_missing=True, label="target root")
    if _lstat(root) is None:
        return set()
    desired = {
        _safe_relative(relative, label="desired managed path")
        for relative in desired_files
    }
    obsolete: set[Path] = set()
    files, _ = _scan_safe_tree(root, label="target root")
    for path in files:
        relative = path.relative_to(root)
        if (
            "__pycache__" in relative.parts
            or path.suffix.lower() == ".pyc"
            or relative not in desired
        ):
            obsolete.add(relative)
    return obsolete


def remove_empty_managed_dirs(root: Path) -> None:
    root = _assert_safe_root(root, allow_missing=True, label="target root")
    if _lstat(root) is None:
        return
    _, directories = _scan_safe_tree(root, label="target root")
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def prune_obsolete_managed_files(root: Path, desired_files: set[Path], *, write: bool) -> list[str]:
    root_resolved = _assert_safe_root(root, allow_missing=True, label="target root")
    removed: list[str] = []
    for relative in sorted(obsolete_managed_files(root, desired_files)):
        path = _assert_safe_descendant(
            root_resolved,
            root_resolved / relative,
            allow_missing=False,
            require_file=True,
            label="obsolete managed path",
        )
        if not _is_under(path, root_resolved):
            raise ValueError(f"refusing to prune outside root: {path}")
        removed.append(relative.as_posix())
        if write:
            make_writable(path)
            path.unlink()
    if write:
        remove_empty_managed_dirs(root)
    return removed


def sync_target(
    source: Path,
    target: Path,
    source_files: set[Path],
    frozen_files: set[Path],
    *,
    write: bool,
    prune_obsolete: bool,
) -> dict[str, object]:
    source = _assert_safe_root(source, allow_missing=False, label="source root")
    target = _assert_safe_root(target, allow_missing=True, label="target root")
    if not source_files:
        raise ValueError("source projection contains no files")
    normalized_source_files = {
        _safe_relative(relative, label="source projection path")
        for relative in source_files
    }
    normalized_frozen_files = {
        _safe_relative(relative, label="frozen install path")
        for relative in frozen_files
    }
    if not normalized_frozen_files.issubset(normalized_source_files):
        raise ValueError("frozen install paths must be projected source files")
    copied: list[str] = []
    removed: list[str] = []
    unchanged = 0

    for relative in sorted(normalized_source_files):
        src = _assert_safe_descendant(
            source,
            source / relative,
            allow_missing=False,
            require_file=True,
            label="source projection file",
        )
        dst = _assert_safe_descendant(
            target,
            target / relative,
            allow_missing=True,
            require_file=True,
            label="target projection file",
        )
        if same_bytes(src, dst):
            unchanged += 1
            continue
        copied.append(relative.as_posix())
        if write:
            _ensure_safe_directory(target, dst.parent)
            _assert_safe_descendant(
                target,
                dst,
                allow_missing=True,
                require_file=True,
                label="target projection file",
            )
            _copy_regular_file(src, dst)

    frozen: list[str] = []
    for relative in sorted(normalized_frozen_files):
        dst = _assert_safe_descendant(
            target,
            target / relative,
            allow_missing=not write,
            require_file=True,
            label="frozen installed reference",
        )
        if write:
            freeze_installed_reference(dst)
        frozen.append(relative.as_posix())

    if prune_obsolete:
        removed.extend(
            prune_obsolete_managed_files(
                target,
                normalized_source_files,
                write=write,
            )
        )

    return {
        "target": str(target),
        "target_alias_of": (
            str(_known_alias_target(target))
            if _known_alias_target(target) is not None
            else None
        ),
        "physical_authority": str(_physical_authority_root(target)),
        "write": write,
        "prune_obsolete": prune_obsolete,
        "ok": True,
        "status": "APPLIED" if write else "PLANNED",
        "copied_count": len(copied),
        "removed_count": len(removed),
        "unchanged_count": unchanged,
        "frozen_count": len(frozen),
        "copied": copied,
        "frozen": frozen,
        "removed": removed,
    }


def resolve_source(value: Path | None) -> Path:
    if value is not None:
        return _assert_safe_root(value, allow_missing=False, label="source root")
    current = _absolute_no_follow(Path(__file__)).parents[1]
    if _lstat(current / PROJECTION_MANIFEST_RELATIVE) is not None:
        _assert_safe_descendant(
            current,
            current / PROJECTION_MANIFEST_RELATIVE,
            allow_missing=False,
            require_file=True,
            label="projection manifest",
        )
        return current
    canonical = default_roots()[0]
    if _lstat(canonical / PROJECTION_MANIFEST_RELATIVE) is not None:
        return _assert_safe_root(canonical, allow_missing=False, label="source root")
    raise FileNotFoundError("cannot resolve source skill root")


def _self_test() -> dict[str, object]:
    failures: list[str] = []
    evidence: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="decretum-active-copy-sync-") as temporary:
        fixture = Path(temporary)
        source = fixture / "source"
        (source / "scripts").mkdir(parents=True)
        (source / "scripts" / "runtime.py").write_text(
            "VALUE = 1\n",
            encoding="utf-8",
        )
        manifest: dict[str, object] = {
            "schema": "court.install_projection.v1",
            "projections": {
                "shared_agents": ["scripts/runtime.py"],
                "portable_current_tool": ["scripts/runtime.py"],
            },
            "protected_shared_agents_seeds": [],
        }
        source_files = set(iter_projected_files(source, manifest))
        evidence["safe_projection"] = [item.as_posix() for item in sorted(source_files)]
        if source_files != {Path("scripts/runtime.py")}:
            failures.append("safe_projection:unexpected_files")

        outside_projection = fixture / "outside.py"
        outside_projection.write_text("VALUE = 2\n", encoding="utf-8")
        traversal_manifest: dict[str, object] = {
            "schema": "court.install_projection.v1",
            "projections": {
                "shared_agents": ["../outside.py"],
                "portable_current_tool": [],
            },
            "protected_shared_agents_seeds": [],
        }
        try:
            iter_projected_files(source, traversal_manifest)
        except ValueError as exc:
            evidence["projection_traversal_rejected"] = str(exc)
        else:
            failures.append("projection_traversal_rejected:expected_error")

        outside_file = fixture / "outside-runtime.py"
        outside_file.write_text("VALUE = 1\n", encoding="utf-8")
        file_link_target = fixture / "file-link-target"
        (file_link_target / "scripts").mkdir(parents=True)
        linked_file = file_link_target / "scripts" / "runtime.py"
        try:
            linked_file.symlink_to(outside_file)
        except OSError as exc:
            evidence["target_file_link_rejected"] = {
                "status": "SKIP",
                "reason": f"symlink_fixture_unavailable:{type(exc).__name__}:{exc}",
            }
        else:
            try:
                sync_target(
                    source,
                    file_link_target,
                    source_files,
                    set(),
                    write=False,
                    prune_obsolete=False,
                )
            except ValueError as exc:
                evidence["target_file_link_rejected"] = str(exc)
            else:
                failures.append("target_file_link_rejected:expected_error")

        outside_directory = fixture / "outside-directory"
        outside_directory.mkdir()
        (outside_directory / "runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
        parent_link_target = fixture / "parent-link-target"
        parent_link_target.mkdir()
        linked_parent = parent_link_target / "scripts"
        try:
            linked_parent.symlink_to(outside_directory, target_is_directory=True)
        except OSError as exc:
            evidence["target_parent_link_rejected"] = {
                "status": "SKIP",
                "reason": f"symlink_fixture_unavailable:{type(exc).__name__}:{exc}",
            }
        else:
            try:
                sync_target(
                    source,
                    parent_link_target,
                    source_files,
                    set(),
                    write=False,
                    prune_obsolete=False,
                )
            except ValueError as exc:
                evidence["target_parent_link_rejected"] = str(exc)
            else:
                failures.append("target_parent_link_rejected:expected_error")

        migration_root = fixture / "legacy-migration"
        canonical = migration_root / CANONICAL_INSTALL_DIRECTORY_NAME
        legacy = migration_root / LEGACY_INSTALL_DIRECTORY_NAME
        canonical.mkdir(parents=True)
        legacy.mkdir()
        (legacy / "preserved.txt").write_text("preserved\n", encoding="utf-8")
        migration = _apply_legacy_migration(
            [(canonical, legacy)],
            backup_root=fixture / "legacy-backup",
        )
        evidence["legacy_migration"] = migration
        alias_ok = (
            migration.get("ok") is True
            and _lstat(legacy) is not None
            and _stat_is_link_or_reparse(_lstat(legacy))
            and _absolute_no_follow(legacy.resolve(strict=True))
            == _absolute_no_follow(canonical.resolve())
            and (fixture / "legacy-backup" / "legacy-0" / "preserved.txt").is_file()
        )
        rollback = _rollback_legacy_migration(migration)
        evidence["legacy_migration_rollback"] = rollback
        if (
            not alias_ok
            or rollback.get("ok") is not True
            or not (legacy / "preserved.txt").is_file()
            or _stat_is_link_or_reparse(_lstat(legacy))
        ):
            failures.append("legacy_migration:transaction_or_rollback_failed")

        # ---- M2 投影子门 RED：R-P3 include-qoder 无授权证明必须 fail closed（计划书 §4.4 第 3 条）----
        # 期望：--include-qoder 在 receipt selected_roots 未含 Qoder 时目标解析拒绝，
        # reason=include_qoder_legacy_switch_rejected；GREEN 后 main() 先经 receipt 检查
        # （有合法 receipt 但不含 Qoder）→ 走到 include-qoder 分支拒绝。
        r3_environment = {
            "HOME": str(fixture / "home"),
            "USERPROFILE": str(fixture / "home"),
            "LOCALAPPDATA": str(fixture / "local-data"),
            "APPDATA": str(fixture / "roaming-data"),
            "XDG_DATA_HOME": str(fixture / "xdg-data"),
        }
        r3_previous = {key: os.environ.get(key) for key in r3_environment}
        os.environ.update(r3_environment)
        import io
        import contextlib
        import sys as _sys
        # 补齐 fixture source 的 manifest，使 main() 可完整执行到 include-qoder 分支。
        r3_manifest_dir = source / "references" / "manifests"
        r3_manifest_dir.mkdir(parents=True, exist_ok=True)
        r3_manifest_path = r3_manifest_dir / "install-projection.v1.json"
        r3_manifest_original = (
            r3_manifest_path.read_text(encoding="utf-8") if r3_manifest_path.is_file() else None
        )
        r3_manifest_path.write_text(
            json.dumps(
                {
                    "schema": "court.install_projection.v1",
                    "schema_version": 1,
                    "identity_manifest": "references/manifests/skill-identity.v1.json",
                    "policy": {
                        "required_target": ".agents",
                        "default_optional_target": "current_agent_tool_only",
                        "extra_targets": "explicit_latest_user_request_only",
                        "fanout": "forbidden",
                    },
                    "protected_shared_agents_seeds": [],
                    "frozen_install_references": [],
                    "projections": {
                        "shared_agents": ["scripts/runtime.py"],
                        "portable_current_tool": ["scripts/runtime.py"],
                        "repository_only": [],
                    },
                    "persistent_bindings": [],
                }
            ),
            encoding="utf-8",
        )
        # 写入合法 receipt（selected_roots 仅含 agents 类根、不含 Qoder），
        # 使 main() 通过 receipt 检查后于 include-qoder 分支拒绝。
        r3_receipt = fixture / "home" / ".agents" / "install-receipts" / "decretum-matrix" / "install-valid-fixture.json"
        r3_receipt.parent.mkdir(parents=True, exist_ok=True)
        r3_agents_root = fixture / "receipt-agents-root-r3"
        r3_agents_root.mkdir(parents=True, exist_ok=True)
        r3_receipt.write_text(
            json.dumps(
                {
                    "schema": "court.install_current_agent_copy.result.v1",
                    "status": "APPLIED",
                    "selection_policy": "receipt",
                    "primary_root": str(r3_agents_root),
                    "current_tool": "fixture",
                    "current_tool_root": str(r3_agents_root),
                    "current_tool_root_proof": "fixture-ok",
                    "explicit_extra_targets": [],
                    "selected_roots": [str(r3_agents_root)],
                    "authority": "fixture-authority",
                    "receipt_sha256": "fixture-receipt-sha256",
                }
            ),
            encoding="utf-8",
        )
        r3_buffer = io.StringIO()
        r3_old_argv = _sys.argv
        _sys.argv = ["sync_active_copies.py", "--json", "--source", str(source), "--include-qoder"]
        try:
            with contextlib.redirect_stdout(r3_buffer):
                r3_rc = main()
        finally:
            _sys.argv = r3_old_argv
            r3_receipt.unlink(missing_ok=True)
            if r3_manifest_original is None:
                r3_manifest_path.unlink(missing_ok=True)
            else:
                r3_manifest_path.write_text(r3_manifest_original, encoding="utf-8")
            for key, value in r3_previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        try:
            r3_main = json.loads(r3_buffer.getvalue())
        except json.JSONDecodeError:
            r3_main = {
                "ok": False,
                "status": "ERROR",
                "failures": [f"unparseable:{r3_buffer.getvalue()[:200]}"],
            }
        evidence["include_qoder_legacy_switch_rejected"] = r3_main
        if r3_main.get("ok") or "include_qoder_legacy_switch_rejected" not in " ".join(
            str(item) for item in r3_main.get("failures", [])
        ):
            failures.append("include_qoder_legacy_switch_rejected:expected_fail")

        # ---- M2 迁移子门 RED：R-M1/R-M2/R-M3 共用 fixture environment + manifest 补全
        # （R-P3 的 finally 已恢复真实环境；三个迁移用例需 fixture HOME 隔离 + manifest 完整，
        # 使 main() 可执行到 targets/迁移解析面；必须置于 R-M1 调用之前）----
        r1_environment = {
            "HOME": str(fixture / "home"),
            "USERPROFILE": str(fixture / "home"),
            "LOCALAPPDATA": str(fixture / "local-data"),
            "APPDATA": str(fixture / "roaming-data"),
            "XDG_DATA_HOME": str(fixture / "xdg-data"),
        }
        r1_previous = {key: os.environ.get(key) for key in r1_environment}
        os.environ.update(r1_environment)
        r1_manifest_dir = source / "references" / "manifests"
        r1_manifest_dir.mkdir(parents=True, exist_ok=True)
        r1_manifest_path = r1_manifest_dir / "install-projection.v1.json"
        r1_manifest_original = (
            r1_manifest_path.read_text(encoding="utf-8") if r1_manifest_path.is_file() else None
        )
        r1_manifest_path.write_text(
            json.dumps(
                {
                    "schema": "court.install_projection.v1",
                    "schema_version": 1,
                    "identity_manifest": "references/manifests/skill-identity.v1.json",
                    "policy": {
                        "required_target": ".agents",
                        "default_optional_target": "current_agent_tool_only",
                        "extra_targets": "explicit_latest_user_request_only",
                        "fanout": "forbidden",
                    },
                    "protected_shared_agents_seeds": [],
                    "frozen_install_references": [],
                    "projections": {
                        "shared_agents": ["scripts/runtime.py"],
                        "portable_current_tool": ["scripts/runtime.py"],
                        "repository_only": [],
                    },
                    "persistent_bindings": [],
                }
            ),
            encoding="utf-8",
        )

        # ---- M2 迁移子门 RED：R-M1 默认路径无 receipt 不得回落五根 fanout（计划书 L188 + §4.4 第 3 条）----
        # 期望：main() 默认路径（无 --root 且无 --include-qoder）在无已验证 receipt 时必须 fail closed，
        # reason=selected_roots_receipt_required；现状 targets=default_roots() 无条件执行 → RED FAIL。
        r1_buffer = io.StringIO()
        r1_old_argv = _sys.argv
        _sys.argv = ["sync_active_copies.py", "--json", "--source", str(source)]
        try:
            with contextlib.redirect_stdout(r1_buffer):
                r1_rc = main()
        finally:
            _sys.argv = r1_old_argv
        try:
            r1_main = json.loads(r1_buffer.getvalue())
        except json.JSONDecodeError:
            r1_main = {
                "ok": False,
                "status": "ERROR",
                "failures": [f"unparseable:{r1_buffer.getvalue()[:200]}"],
            }
        evidence["selected_roots_receipt_required"] = r1_main
        if r1_main.get("ok") or "selected_roots_receipt_required" not in " ".join(
            str(item) for item in r1_main.get("failures", [])
        ):
            failures.append("selected_roots_receipt_required:expected_fail")

        # ---- M2 迁移子门 RED：R-M2 legacy 迁移必须绑定 receipt（计划书 L188）----
        # 期望：无已验证 receipt 时，--migrate-legacy-locators 必须 fail closed
        # （reason=legacy_migration_not_receipt_derived）；现状 main() 无条件执行迁移
        # 推导（无 receipt 校验）→ RED FAIL。行为面断言，与 R-M1 同环境互补（迁移面更具体）。
        r2_legacy_root = fixture / "legacy-migration-root"
        r2_legacy_root.mkdir(parents=True, exist_ok=True)
        r2_legacy_dir = r2_legacy_root.with_name(LEGACY_INSTALL_DIRECTORY_NAME)
        r2_legacy_dir.mkdir(parents=True, exist_ok=True)
        (r2_legacy_dir / "preserved.txt").write_text("preserved\n", encoding="utf-8")
        r2_buffer = io.StringIO()
        r2_old_argv = _sys.argv
        _sys.argv = [
            "sync_active_copies.py",
            "--json",
            "--source",
            str(source),
            "--migrate-legacy-locators",
        ]
        try:
            with contextlib.redirect_stdout(r2_buffer):
                r2_rc = main()
        finally:
            _sys.argv = r2_old_argv
        try:
            r2_main = json.loads(r2_buffer.getvalue())
        except json.JSONDecodeError:
            r2_main = {
                "ok": False,
                "status": "ERROR",
                "failures": [f"unparseable:{r2_buffer.getvalue()[:200]}"],
            }
        evidence["legacy_migration_not_receipt_derived"] = r2_main
        if r2_main.get("ok") or "legacy_migration_not_receipt_derived" not in " ".join(
            str(item) for item in r2_main.get("failures", [])
        ):
            failures.append("legacy_migration_not_receipt_derived:expected_fail")

        # ---- M2 迁移子门 RED：R-M3 alias 分组必须绑定 receipt selected set（计划书 L188）----
        # 期望：有合法 receipt（selected_roots 仅含 .agents 类根）时，main() 默认路径 targets
        # 严格等于 receipt selected_roots（不含默认五根中的 alias 根）；现状 main() 用
        # default_roots()（含 user_data hermes 等 alias 目标）→ RED FAIL。
        # 先清理 R-M2 遗留的 legacy fixture（fixture/court-capability-router 会与 R-M3 的
        # agents_root 兄弟路径冲突，触发 legacy_locator_conflicts 而非 receipt 语义）。
        r3_legacy_leftover = fixture / LEGACY_INSTALL_DIRECTORY_NAME
        if r3_legacy_leftover.is_dir():
            shutil.rmtree(r3_legacy_leftover, ignore_errors=True)
        r3_receipt = fixture / "home" / ".agents" / "install-receipts" / "decretum-matrix" / "install-valid-fixture.json"
        r3_receipt.parent.mkdir(parents=True, exist_ok=True)
        r3_agents_root = fixture / "receipt-agents-root"
        r3_agents_root.mkdir(parents=True, exist_ok=True)
        r3_receipt.write_text(
            json.dumps(
                {
                    "schema": "court.install_current_agent_copy.result.v1",
                    "status": "APPLIED",
                    "selection_policy": "receipt",
                    "primary_root": str(r3_agents_root),
                    "current_tool": "fixture",
                    "current_tool_root": str(r3_agents_root),
                    "current_tool_root_proof": "fixture-ok",
                    "explicit_extra_targets": [],
                    "selected_roots": [str(r3_agents_root)],
                    "authority": "fixture-authority",
                    "receipt_sha256": "fixture-receipt-sha256",
                }
            ),
            encoding="utf-8",
        )
        r3_buffer = io.StringIO()
        r3_old_argv = _sys.argv
        _sys.argv = ["sync_active_copies.py", "--json", "--source", str(source)]
        try:
            with contextlib.redirect_stdout(r3_buffer):
                r3_rc = main()
        finally:
            _sys.argv = r3_old_argv
        try:
            r3_main = json.loads(r3_buffer.getvalue())
        except json.JSONDecodeError:
            r3_main = {
                "ok": False,
                "status": "ERROR",
                "failures": [f"unparseable:{r3_buffer.getvalue()[:200]}"],
            }
        evidence["alias_group_not_receipt_derived"] = r3_main
        r3_targets = [str(item.get("target")) for item in r3_main.get("targets", [])]
        if (
            not r3_main.get("ok")
            or r3_main.get("logical_target_count") != 1
            or str(r3_agents_root) not in r3_targets
        ):
            failures.append("alias_group_not_receipt_derived:expected_fail")
        r3_receipt.unlink(missing_ok=True)
        if r1_manifest_original is None:
            r1_manifest_path.unlink(missing_ok=True)
        else:
            r1_manifest_path.write_text(r1_manifest_original, encoding="utf-8")
        for key, value in r1_previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    return {
        "schema": "court.active_copy_sync_self_test.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "evidence": evidence,
        "failures": failures,
        "pending_body_access": "NO",
    }


def _qoder_in_verified_selected_roots() -> bool:
    """仅当已验证 install receipt 的 selected_roots 显式含 Qoder 根时返回 True（计划书 §4.4 第 3 条）。

    读取 ~/.agents/install-receipts/decretum-matrix/ 下最新 JSON receipt；
    无 receipt、receipt 无 selected_roots、或 selected_roots 不含 Qoder → False（fail closed）。
    """
    home = Path.home()
    receipts_dir = home / ".agents" / "install-receipts" / "decretum-matrix"
    if not receipts_dir.is_dir():
        return False
    # 只读 installer 生成的 install-*.json（§4.4 receipt），排除 npm-postinstall-*.json。
    candidates = sorted(
        (path for path in receipts_dir.glob("install-*.json") if path.is_file()),
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True,
    )
    if not candidates:
        return False
    try:
        receipt = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    selected = receipt.get("selected_roots")
    if not isinstance(selected, list):
        return False
    qoder = _absolute_no_follow(qoder_root())
    for item in selected:
        try:
            if _absolute_no_follow(Path(item)) == qoder:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _load_verified_selected_roots() -> list[Path] | None:
    """读取最新 install receipt 的 selected_roots 作为唯一合法目标集（计划书 §4.4 第 3 条）。

    无 receipt、receipt 读取失败、或 selected_roots 缺失/非 list → None（fail closed）。
    返回的列表逐根为绝对路径；调用方以 None 判定 fail closed 并记录原因。
    """
    home = Path.home()
    receipts_dir = home / ".agents" / "install-receipts" / "decretum-matrix"
    if not receipts_dir.is_dir():
        return None
    # 只读 installer 生成的 install-*.json（§4.4 receipt），排除 npm-postinstall-*.json
    # 运行收条（无 selected_roots，会污染「最新 receipt」判定）。
    candidates = sorted(
        (path for path in receipts_dir.glob("install-*.json") if path.is_file()),
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True,
    )
    if not candidates:
        return None
    try:
        receipt = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    selected = receipt.get("selected_roots")
    if not isinstance(selected, list) or not selected:
        return None
    roots: list[Path] = []
    for item in selected:
        try:
            roots.append(_absolute_no_follow(Path(item)))
        except (TypeError, ValueError):
            return None
    return roots


def _write_first_install_receipt(canonical_root: Path) -> dict[str, object]:
    """npm postinstall 首装时生成 §4.4 install receipt（计划书 §4.4 第 4 条）。

    仅在无既有 receipt 且目标仅为 canonical primary root 时由 main() 调用；
    selected_roots 仅含 canonical_root（不 fanout），status=INSTALLED，
    authority=installer（本包自装）。receipt_sha256 为除自身字段外的规范序列化哈希。
    """
    home = Path.home()
    primary_root = _absolute_no_follow(canonical_root)
    receipt_body: dict[str, object] = {
        "schema": "court.install_current_agent_copy.result.v1",
        "selection_policy": "receipt",
        "primary_root": str(primary_root),
        "current_tool": "codex",
        "current_tool_root": str(primary_root),
        "current_tool_root_proof": "install_applied",
        "status": "INSTALLED",
        "explicit_extra_targets": [],
        "selected_roots": [str(primary_root)],
        "authority": "installer",
    }
    receipt_body["receipt_sha256"] = hashlib.sha256(
        json.dumps(receipt_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    receipts_dir = home / ".agents" / "install-receipts" / "decretum-matrix"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipts_dir / f"install-{receipt_body['receipt_sha256'][:16]}.json"
    receipt_path.write_text(
        json.dumps(receipt_body, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "path": str(receipt_path),
        "receipt_sha256": str(receipt_body["receipt_sha256"]),
        "selected_roots": [str(primary_root)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source", type=Path, help="Skill root to copy from. Defaults to this script's skill root.")
    parser.add_argument("--write", action="store_true", help="Apply the synchronization. Default is a read-only plan.")
    parser.add_argument(
        "--prune-obsolete",
        action="store_true",
        help="Remove obsolete managed files from targets when they are outside the current projection.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--include-qoder",
        action="store_true",
        help="Also synchronize the Qoder skill root when explicitly authorized.",
    )
    parser.add_argument(
        "--migrate-legacy-locators",
        action="store_true",
        help="With --write, back up physical legacy locators and replace them with canonical compatibility aliases.",
    )
    args = parser.parse_args()

    if args.self_test:
        result = _self_test()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1

    source = resolve_source(args.source)
    first_install_extra: dict[str, object] | None = None
    # M2 迁移子门 GREEN（R-M1/R-M2/R-M3）：默认路径 targets 必须从已验证 receipt 的
    # selected_roots 派生（计划书 §4.4 第 3 条 + L188「以同一 receipt 为依据」）；
    # 无 receipt → fail closed（带 --migrate-legacy-locators 时报迁移专属 reason）。
    # 例外：npm postinstall 首装（--write + 显式 --source + 无 receipt）→ 仅写 canonical
    # primary root 并生成 §4.4 install receipt（计划书 L88「零写入」仅指无授权 fanout，
    # canonical 首装不是 fanout；receipt 由 installer 在首装时生成，之后 sync 从 receipt 派生）。
    verified_roots = _load_verified_selected_roots()
    if verified_roots is None:
        if args.write and args.source is not None:
            first_install_targets = [default_roots()[0]]
            targets = first_install_targets
            install_receipt = _write_first_install_receipt(targets[0])
            first_install_extra = {
                "first_install": True,
                "install_receipt": install_receipt,
            }
        else:
            failure_reason = (
                "legacy_migration_not_receipt_derived"
                if args.migrate_legacy_locators
                else "selected_roots_receipt_required"
            )
            result = {
                "ok": False,
                "status": "FAIL",
                "schema": "court.active_copy_sync.v1",
                "source": str(source),
                "source_files": 0,
                "write": args.write,
                "prune_obsolete": args.prune_obsolete,
                "include_qoder": args.include_qoder,
                "migrate_legacy_locators": args.migrate_legacy_locators,
                "frozen_install_references": [],
                "targets": [],
                "logical_target_count": 0,
                "physical_authority_count": 0,
                "legacy_locator_conflicts": [],
                "failures": [failure_reason],
            }
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"ACTIVE_COPY_SYNC_FAIL {failure_reason}")
            return 1
    if "targets" not in locals():
        targets = list(verified_roots)
    if args.include_qoder:
        # M2 投影子门 GREEN（R-P3）：include-qoder 必须具有最新授权/proof 证据。
        # 仅当已验证 install receipt 的 selected_roots 显式含 Qoder 根时才允许，
        # 否则 fail closed（include_qoder_legacy_switch_rejected）；不得从旧开关推导授权（计划书 §4.4 第 3 条）。
        if not _qoder_in_verified_selected_roots():
            result = {
                "ok": False,
                "status": "FAIL",
                "schema": "court.active_copy_sync.v1",
                "source": str(source),
                "source_files": 0,
                "write": args.write,
                "prune_obsolete": args.prune_obsolete,
                "include_qoder": True,
                "migrate_legacy_locators": False,
                "frozen_install_references": [],
                "targets": [],
                "logical_target_count": 0,
                "physical_authority_count": 0,
                "legacy_locator_conflicts": [],
                "failures": ["include_qoder_legacy_switch_rejected"],
            }
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print("ACTIVE_COPY_SYNC_FAIL include_qoder_legacy_switch_rejected")
            return 1
        targets.append(qoder_root())
    target_groups = _physical_target_groups(targets)
    physical_targets = [physical for physical, _logical in target_groups]
    conflicts = legacy_locator_conflicts(physical_targets)
    if conflicts and not args.migrate_legacy_locators:
        result = {
            "ok": False,
            "status": "FAIL",
            "schema": "court.active_copy_sync.v1",
            "source": str(source),
            "source_files": 0,
            "write": args.write,
            "prune_obsolete": args.prune_obsolete,
            "include_qoder": args.include_qoder,
            "migrate_legacy_locators": False,
            "frozen_install_references": [],
            "targets": [],
            "logical_target_count": len(targets),
            "physical_authority_count": len(physical_targets),
            "legacy_locator_conflicts": conflicts,
            "failures": [
                "legacy install locator conflicts with canonical authority"
            ],
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                "ACTIVE_COPY_SYNC_FAIL legacy_locator_conflicts={}".format(
                    len(conflicts)
                )
            )
        return 1
    migration_candidates: list[tuple[Path, Path]] = []
    legacy_migration: dict[str, object] = {
        "ok": True,
        "status": "NOT_REQUESTED",
        "entries": [],
        "backup_root": None,
        "rollback_supported": True,
    }
    if args.migrate_legacy_locators:
        try:
            migration_candidates = _legacy_migration_candidates(physical_targets)
        except (OSError, ValueError) as exc:
            result = {
                "ok": False,
                "status": "FAIL",
                "schema": "court.active_copy_sync.v1",
                "source": str(source),
                "source_files": 0,
                "write": args.write,
                "prune_obsolete": args.prune_obsolete,
                "include_qoder": args.include_qoder,
                "migrate_legacy_locators": True,
                "targets": [],
                "logical_target_count": len(targets),
                "physical_authority_count": len(physical_targets),
                "legacy_locator_conflicts": conflicts,
                "legacy_migration": {
                    "ok": False,
                    "status": "REJECTED",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                "failures": ["legacy migration preflight rejected"],
            }
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 1
        legacy_migration = {
            "ok": True,
            "status": "PLANNED" if not args.write else "PENDING",
            "entries": [
                {
                    "canonical_root": str(canonical),
                    "legacy_root": str(legacy),
                }
                for canonical, legacy in migration_candidates
            ],
            "backup_root": None,
            "rollback_supported": True,
        }
    manifest = load_projection(source)
    source_files = set(iter_projected_files(source, manifest))
    frozen_files = frozen_install_references(manifest, source_files)
    def target_failure(target: Path, exc: BaseException) -> dict[str, object]:
        return {
            "target": str(target),
            "write": args.write,
            "prune_obsolete": args.prune_obsolete,
            "status": "FAIL",
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "copied_count": 0,
            "removed_count": 0,
            "unchanged_count": 0,
            "frozen_count": 0,
            "copied": [],
            "frozen": [],
            "removed": [],
        }

    def physical_key(target: Path) -> str:
        return _path_key(_physical_authority_root(target))

    def logical_results(
        physical_results: dict[str, dict[str, object]],
    ) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for target in targets:
            physical = _physical_authority_root(target)
            physical_result = physical_results[physical_key(target)]
            if _path_key(target) == _path_key(physical):
                results.append(physical_result)
                continue
            aliased = {
                "target": str(_absolute_no_follow(target)),
                "target_alias_of": str(physical),
                "physical_authority": str(physical),
                "write": physical_result["write"],
                "prune_obsolete": physical_result["prune_obsolete"],
                "status": (
                    "ALIAS_REUSED"
                    if physical_result.get("ok", True)
                    else "ALIAS_BLOCKED"
                ),
                "ok": physical_result.get("ok", True),
                "copied_count": 0,
                "removed_count": 0,
                "unchanged_count": 0,
                "frozen_count": 0,
                "copied": [],
                "frozen": [],
                "removed": [],
            }
            if not physical_result.get("ok", True):
                aliased["error"] = (
                    "physical authority failed: "
                    + str(physical_result.get("error", physical))
                )
            results.append(aliased)
        return results

    failures: list[str] = []
    plan_by_physical: dict[str, dict[str, object]] = {}
    for target in physical_targets:
        try:
            plan_by_physical[physical_key(target)] = sync_target(
                source,
                target,
                source_files,
                frozen_files,
                write=False,
                prune_obsolete=args.prune_obsolete,
            )
        except (OSError, ValueError) as exc:
            failures.append(f"{target}:{type(exc).__name__}:{exc}")
            plan_by_physical[physical_key(target)] = target_failure(target, exc)

    results = logical_results(plan_by_physical)
    partial_applied = False
    if args.write and not failures:
        if migration_candidates:
            legacy_migration = _apply_legacy_migration(migration_candidates)
            if not legacy_migration.get("ok", False):
                failures.append(
                    "legacy migration failed: "
                    + str(legacy_migration.get("error", "unknown failure"))
                )
        applied_targets: list[str] = []
        write_by_physical: dict[str, dict[str, object]] = {}
        if not failures:
            for target in physical_targets:
                try:
                    write_by_physical[physical_key(target)] = sync_target(
                        source,
                        target,
                        source_files,
                        frozen_files,
                        write=True,
                        prune_obsolete=args.prune_obsolete,
                    )
                    applied_targets.append(str(target))
                except (OSError, ValueError) as exc:
                    failures.append(f"{target}:{type(exc).__name__}:{exc}")
                    write_by_physical[physical_key(target)] = target_failure(target, exc)
                    partial_applied = bool(applied_targets)
                    break
        for target in physical_targets:
            key = physical_key(target)
            if key not in write_by_physical:
                write_by_physical[key] = {
                    **target_failure(target, RuntimeError("write not attempted after prior failure")),
                    "status": "NOT_ATTEMPTED",
                }
        results = logical_results(write_by_physical)
        if failures and legacy_migration.get("status") == "MIGRATED":
            rollback = _rollback_legacy_migration(legacy_migration)
            legacy_migration["rollback_after_sync_failure"] = rollback
            if not rollback.get("ok", False):
                failures.append("legacy migration rollback failed")
    result = {
        "ok": not failures,
        "status": (
            "PASS"
            if not failures
            else "FAIL_PARTIAL_APPLIED"
            if partial_applied
            else "FAIL"
        ),
        "schema": "court.active_copy_sync.v1",
        "source": str(source),
        "source_files": len(source_files),
        "write": args.write,
        "prune_obsolete": args.prune_obsolete,
        "include_qoder": args.include_qoder,
        "migrate_legacy_locators": args.migrate_legacy_locators,
        "frozen_install_references": [item.as_posix() for item in sorted(frozen_files)],
        "targets": results,
        "logical_target_count": len(targets),
        "physical_authority_count": len(physical_targets),
        "physical_authorities": [str(item) for item in physical_targets],
        "partial_applied": partial_applied,
        "recovery_required": (
            "run the source-only active-copy hash check before any further install action"
            if partial_applied
            else None
        ),
        "failures": failures,
        "legacy_locator_conflicts": conflicts,
        "legacy_migration": legacy_migration,
        **({"first_install": first_install_extra} if first_install_extra is not None else {}),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "ACTIVE_COPY_SYNC_{} source_files={} copied={} removed={}".format(
                "APPLIED" if args.write else "PLAN",
                len(source_files),
                sum(int(item["copied_count"]) for item in results),
                sum(int(item["removed_count"]) for item in results),
            )
        )
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
