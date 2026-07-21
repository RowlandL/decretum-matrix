"""Synchronize Decretum Matrix source files to known active installations.

This tool copies the manifest-selected runtime surface to the five local skill
roots. It compares file bytes directly to decide whether a copy is needed and
does not perform startup validation of unrelated files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True

from court_platform import user_data_base


CANONICAL_INSTALL_DIRECTORY_NAME = "decretum-matrix"
LEGACY_INSTALL_DIRECTORY_NAME = "court-capability-router"
PROJECTION_MANIFEST_RELATIVE = Path("references/manifests/install-projection.v1.json")


def default_roots() -> list[Path]:
    home = Path.home()
    return [
        home / ".agents" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        home / ".codex" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        home / ".claude" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        home / ".hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
        user_data_base() / "hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME,
    ]


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def legacy_locator_conflicts(roots: list[Path]) -> list[str]:
    conflicts: list[str] = []
    for root in roots:
        legacy = root.with_name(LEGACY_INSTALL_DIRECTORY_NAME)
        if (legacy.exists() or legacy.is_symlink()) and (
            legacy.resolve(strict=False) != root.resolve(strict=False)
        ):
            conflicts.append(str(legacy))
    return conflicts


def load_projection(source: Path) -> dict[str, object]:
    path = source / PROJECTION_MANIFEST_RELATIVE
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != "court.install_projection.v1":
        raise ValueError(f"invalid projection manifest: {path}")
    projections = value.get("projections")
    if not isinstance(projections, dict):
        raise ValueError("projection manifest has no projections")
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
    protected_value = manifest.get("protected_shared_agents_seeds")
    if isinstance(protected_value, dict):
        entries.update(str(key) for key in protected_value)
    elif isinstance(protected_value, list):
        entries.update(str(item) for item in protected_value if isinstance(item, str))
    return entries


def iter_projected_files(source: Path) -> list[Path]:
    entries = projection_entries(load_projection(source))
    files: set[Path] = set()
    for relative_text in sorted(entries):
        relative = Path(relative_text)
        candidate = source / relative
        if candidate.is_symlink():
            raise ValueError(f"managed projection contains a symlink: {relative_text}")
        if candidate.is_file():
            files.add(candidate.relative_to(source))
            continue
        if not candidate.is_dir():
            raise ValueError(f"managed projection path is missing: {relative_text}")
        for child in sorted(candidate.rglob("*")):
            if child.is_symlink():
                raise ValueError(f"managed projection contains a symlink: {child.relative_to(source)}")
            if child.is_file() and "__pycache__" not in child.parts and child.suffix.lower() != ".pyc":
                files.add(child.relative_to(source))
    return sorted(files)


def same_bytes(left: Path, right: Path) -> bool:
    if not right.exists() or not right.is_file():
        return False
    if left.stat().st_size != right.stat().st_size:
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
    if not root.exists():
        return set()
    obsolete: set[Path] = set()
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts or path.suffix.lower() == ".pyc":
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"refusing to prune non-regular managed path: {path}")
        relative = path.relative_to(root)
        if relative not in desired_files:
            obsolete.add(relative)
    return obsolete


def remove_empty_managed_dirs(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted((item for item in root.rglob("*") if item.is_dir()), key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def prune_obsolete_managed_files(root: Path, desired_files: set[Path], *, write: bool) -> list[str]:
    root_resolved = root.resolve(strict=False)
    removed: list[str] = []
    for relative in sorted(obsolete_managed_files(root, desired_files)):
        path = root / relative
        if not _is_under(path, root_resolved):
            raise ValueError(f"refusing to prune outside root: {path}")
        removed.append(relative.as_posix())
        if write:
            path.unlink()
    if write:
        remove_empty_managed_dirs(root)
    return removed


def sync_target(
    source: Path,
    target: Path,
    source_files: set[Path],
    *,
    write: bool,
    prune_obsolete: bool,
) -> dict[str, object]:
    copied: list[str] = []
    removed: list[str] = []
    unchanged = 0

    for relative in sorted(source_files):
        src = source / relative
        dst = target / relative
        if same_bytes(src, dst):
            unchanged += 1
            continue
        copied.append(relative.as_posix())
        if write:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    if prune_obsolete:
        removed.extend(prune_obsolete_managed_files(target, source_files, write=write))

    return {
        "target": str(target),
        "write": write,
        "prune_obsolete": prune_obsolete,
        "copied_count": len(copied),
        "removed_count": len(removed),
        "unchanged_count": unchanged,
        "copied": copied,
        "removed": removed,
    }


def resolve_source(value: Path | None) -> Path:
    if value is not None:
        return value.resolve()
    current = Path(__file__).resolve().parents[1]
    if (current / PROJECTION_MANIFEST_RELATIVE).exists():
        return current
    canonical = default_roots()[0]
    if (canonical / PROJECTION_MANIFEST_RELATIVE).exists():
        return canonical
    raise FileNotFoundError("cannot resolve source skill root")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Skill root to copy from. Defaults to this script's skill root.")
    parser.add_argument("--write", action="store_true", help="Apply the synchronization. Default is a read-only plan.")
    parser.add_argument(
        "--prune-obsolete",
        action="store_true",
        help="Remove obsolete managed files from targets when they are outside the current projection.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    source = resolve_source(args.source)
    targets = default_roots()
    conflicts = legacy_locator_conflicts(targets)
    if conflicts:
        raise SystemExit(f"legacy install locator conflicts with canonical authority: {conflicts}")
    source_files = set(iter_projected_files(source))
    results = [
        sync_target(
            source,
            target,
            source_files,
            write=args.write,
            prune_obsolete=args.prune_obsolete,
        )
        for target in targets
    ]
    result = {
        "ok": True,
        "schema": "court.active_copy_sync.v1",
        "source": str(source),
        "source_files": len(source_files),
        "write": args.write,
        "prune_obsolete": args.prune_obsolete,
        "targets": results,
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
