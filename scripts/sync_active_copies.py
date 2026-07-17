"""Synchronize validated court skill source files to known active installations.

The first root returned by ``check_active_copy_hashes.active_roots`` is the
canonical ``.agents`` working copy. Runtime/state directories are excluded.
Target-only files are always preserved; this synchronizer never deletes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True

from check_active_copy_hashes import (
    CANONICAL_INSTALL_DIRECTORY_NAME,
    active_roots,
    iter_source_files,
    legacy_locator_conflicts,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_roots(source: Path, targets: list[Path]) -> None:
    home = Path.home().resolve()
    expected = {
        (home / ".codex" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME).resolve(strict=False),
        (home / ".claude" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME).resolve(strict=False),
        (home / ".hermes" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME).resolve(strict=False),
        (active_roots()[-1]).resolve(strict=False),
    }
    if source.resolve() != (home / ".agents" / "skills" / CANONICAL_INSTALL_DIRECTORY_NAME).resolve(strict=False):
        raise ValueError(f"unexpected canonical source: {source}")
    actual = {target.resolve(strict=False) for target in targets}
    if actual != expected:
        raise ValueError("active target set does not match the fixed court installation roots")
    conflicts = legacy_locator_conflicts([source, *targets])
    if conflicts:
        raise ValueError(f"legacy install locator conflicts with canonical authority: {conflicts}")


def target_source_files(target: Path) -> set[Path]:
    if not target.exists():
        return set()
    return set(iter_source_files(target))


def sync_target(source: Path, target: Path, source_files: set[Path], *, write: bool) -> dict[str, object]:
    target_files = target_source_files(target)
    copied: list[str] = []
    removed: list[str] = []
    unchanged = 0

    for relative in sorted(source_files):
        src = source / relative
        dst = target / relative
        if dst.exists() and dst.is_file() and sha256(src) == sha256(dst):
            unchanged += 1
            continue
        copied.append(relative.as_posix())
        if write:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    return {
        "target": str(target),
        "write": write,
        "copied_count": len(copied),
        "removed_count": len(removed),
        "unchanged_count": unchanged,
        "copied": copied,
        "removed": removed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Apply the synchronization. Default is a read-only plan.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    roots = active_roots()
    source, targets = roots[0], roots[1:]
    validate_roots(source, targets)
    if not source.is_dir():
        raise SystemExit(f"canonical source is missing: {source}")
    source_files = set(iter_source_files(source))
    results = [sync_target(source, target, source_files, write=args.write) for target in targets]
    result = {
        "ok": True,
        "schema": "court.active_copy_sync.v1",
        "source": str(source),
        "source_files": len(source_files),
        "write": args.write,
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
