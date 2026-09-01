

#!/usr/bin/env python3
"""Archive an old full Codex skill replica before installing a release ZIP.

The current installer refuses a Codex root carrying shared-only Shiguan anchors.
This helper preserves that whole root as an atomic preimage, invokes the exact
ZIP's installer, and keeps both rollback receipts.
"""

from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
import uuid
import zipfile
from typing import Any


sys.dont_write_bytecode = True

SCHEMA = "court.current_tool_replica_migration.v1"
NAME = "decretum-matrix"
TOOL = "codex"
BACKUP_PARTS = (".agents", "install-backups", NAME)
PROTECTED_ANCHORS = (
    "references/shiguan-index.jsonl",
    "references/shiguan-knowledge-graph.json",
    "references/shiguan-tree/_index.md",
    "references/shiguan-tree/capability-index/_index.md",
)
REQUIRED_FILES = (
    "SKILL.md",
    "VERSION",
    "references/manifests/install-projection.v1.json",
)


def absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def is_link_or_reparse(value: os.stat_result | None) -> bool:
    if value is None:
        return False
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(value.st_mode) or bool(
        reparse and getattr(value, "st_file_attributes", 0) & reparse
    )


def within(path: Path, root: Path) -> bool:
    try:
        absolute(path).relative_to(absolute(root))
    except ValueError:
        return False
    return True


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def codex_root(home: Path) -> Path:
    return absolute(home / ".codex" / "skills" / NAME)


def validate_root(home: Path, root: Path, *, allow_missing: bool) -> Path:
    root = absolute(root)
    if root.name != NAME or not within(root, home):
        raise ValueError(f"root_outside_home:{root}")
    for candidate in [*reversed(root.parents), root]:
        if not within(candidate, home):
            continue
        value = lstat(candidate)
        if value is None:
            continue
        if is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
            raise ValueError(f"unsafe_root_component:{candidate}")
    if lstat(root) is None and not allow_missing:
        raise ValueError(f"root_missing:{root}")
    return root


def ensure_directory(home: Path, directory: Path) -> None:
    if not within(directory, home):
        raise ValueError(f"backup_outside_home:{directory}")
    current = absolute(home)
    for part in absolute(directory).relative_to(current).parts:
        current = current / part
        value = lstat(current)
        if value is None:
            current.mkdir()
            value = lstat(current)
        if value is None or is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
            raise ValueError(f"unsafe_backup_component:{current}")


def backup_root(home: Path) -> Path:
    base = absolute(home.joinpath(*BACKUP_PARTS))
    ensure_directory(home, base)
    root = base / f"current-tool-replica-{uuid.uuid4().hex}"
    root.mkdir()
    return root


def validate_member(info: zipfile.ZipInfo) -> None:
    path = PurePosixPath(info.filename)
    if not info.filename or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe_archive_member:{info.filename!r}")
    if not path.parts or path.parts[0] != NAME:
        raise ValueError(f"archive_root_mismatch:{info.filename!r}")
    if ((info.external_attr >> 16) & 0o170000) == stat.S_IFLNK:
        raise ValueError(f"archive_symlink_rejected:{info.filename!r}")


def extract_package(package: Path, destination: Path) -> Path:
    with zipfile.ZipFile(package) as archive:
        for info in archive.infolist():
            validate_member(info)
        archive.extractall(destination)
    source = destination / NAME
    missing = [item for item in REQUIRED_FILES if not (source / item).is_file()]
    if missing:
        raise ValueError("package_payload_missing:" + ",".join(missing))
    return source


def load_installer(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("decretum_package_installer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"installer_load_failed:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archive_installer(backup: Path) -> tuple[Path, str]:
    source = Path(__file__).resolve().parents[1] / "install_current_agent_copy.py"
    if not source.is_file():
        raise RuntimeError(f"installer_missing:{source}")
    archived = backup / "installer.py"
    shutil.copy2(source, archived)
    return archived, sha256(archived)


def write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def remove_empty_tree(root: Path) -> None:
    value = lstat(root)
    if value is None:
        return
    if is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
        raise ValueError(f"rollback_target_not_plain_directory:{root}")
    with os.scandir(root) as entries:
        children = list(entries)
    for child in children:
        path = Path(child.path)
        value = path.stat(follow_symlinks=False)
        if is_link_or_reparse(value):
            raise ValueError(f"rollback_target_contains_link:{path}")
        if stat.S_ISDIR(value.st_mode):
            remove_empty_tree(path)
        else:
            raise ValueError(f"rollback_target_not_empty:{path}")
    root.rmdir()


def plan(package: Path, home: Path) -> dict[str, Any]:
    package = absolute(package)
    if not package.is_file():
        raise ValueError(f"package_missing:{package}")
    root = validate_root(home, codex_root(home), allow_missing=True)
    root_exists = lstat(root) is not None
    anchors = [
        item for item in PROTECTED_ANCHORS if root_exists and lstat(root / item) is not None
    ]
    return {
        "schema": SCHEMA,
        "ok": True,
        "status": "PLANNED",
        "write": False,
        "current_tool": TOOL,
        "current_tool_root": str(root),
        "current_root_exists": root_exists,
        "current_root_mode": "ARCHIVE_FULL_CURRENT_TOOL_REPLICA" if root_exists else "INSTALL_NO_PREIMAGE",
        "protected_anchor_paths_present": anchors,
        "protected_anchor_contents_accessed": False,
        "package": str(package),
        "package_sha256": sha256(package),
        "rollback_supported": True,
    }


def apply(package: Path, *, write: bool) -> dict[str, Any]:
    home = absolute(Path.home())
    try:
        result = plan(package, home)
    except (OSError, ValueError) as exc:
        return {"schema": SCHEMA, "ok": False, "status": "REJECTED", "write": write, "failures": [f"preflight:{type(exc).__name__}:{exc}"]}
    if not write:
        return result

    package = Path(str(result["package"]))
    target = Path(str(result["current_tool_root"]))
    backup = backup_root(home)
    preimage = backup / "current-tool-preimage"
    receipt_path = backup / "receipt.json"
    moved = False
    installer: Any | None = None
    install_result: dict[str, Any] | None = None
    rollback_errors: list[str] = []
    try:
        installer_path, installer_sha256 = archive_installer(backup)
        installer = load_installer(installer_path)
        if lstat(target) is not None:
            os.replace(target, preimage)
            moved = True
        with tempfile.TemporaryDirectory(prefix="decretum-current-tool-replica-") as raw:
            source = extract_package(package, Path(raw))
            raw_result = installer.install_current_agent_copy(
                source_root=source,
                home_root=home,
                current_tool=TOOL,
                explicit_tools=[],
                tool_roots={TOOL: target},
                projection_manifest=source / "references" / "manifests" / "install-projection.v1.json",
                write=True,
                source_package_sha256=str(result["package_sha256"]),
                backup_root=backup / "managed-projection",
            )
        if not isinstance(raw_result, dict) or raw_result.get("ok") is not True:
            raise RuntimeError(f"installer_rejected:{raw_result}")
        install_result = raw_result
        receipt = {
            "schema": SCHEMA,
            "ok": True,
            "status": "MIGRATED_AND_INSTALLED",
            "write": True,
            "current_tool": TOOL,
            "current_tool_root": str(target),
            "package": str(package),
            "package_sha256": result["package_sha256"],
            "backup_root": str(backup),
            "current_tool_preimage": str(preimage) if moved else None,
            "installer_archive": str(installer_path),
            "installer_sha256": installer_sha256,
            "managed_projection_backup": install_result.get("backup"),
            "install_receipt_path": install_result.get("install_receipt_path"),
            "protected_anchor_contents_accessed": False,
            "rollback_supported": True,
            "rollback_command": f"python -B scripts/migrate_current_tool_replica.py rollback --receipt {receipt_path} --package {package} --write --json",
            "failures": [],
        }
        write_json(receipt_path, receipt)
        return {**receipt, "receipt_path": str(receipt_path)}
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        if install_result is not None and installer is not None:
            managed = install_result.get("backup")
            if isinstance(managed, dict) and managed.get("status") == "CREATED":
                try:
                    rollback = installer.rollback_install_backup(home_root=home, backup_root=Path(str(managed["backup_root"])))
                    if not isinstance(rollback, dict) or rollback.get("ok") is not True:
                        rollback_errors.append(f"managed_rollback_failed:{rollback}")
                except Exception as rollback_exc:
                    rollback_errors.append(f"managed_rollback:{type(rollback_exc).__name__}:{rollback_exc}")
        if moved:
            try:
                remove_empty_tree(target)
                os.replace(preimage, target)
            except (OSError, ValueError) as rollback_exc:
                rollback_errors.append(f"preimage_restore:{type(rollback_exc).__name__}:{rollback_exc}")
        receipt = {
            "schema": SCHEMA,
            "ok": False,
            "status": "ROLLED_BACK" if not rollback_errors else "ROLLBACK_FAILED",
            "write": True,
            "current_tool": TOOL,
            "current_tool_root": str(target),
            "package": str(package),
            "package_sha256": result["package_sha256"],
            "backup_root": str(backup),
            "current_tool_preimage": str(preimage) if moved else None,
            "error": f"{type(exc).__name__}:{exc}",
            "rollback_errors": rollback_errors,
            "protected_anchor_contents_accessed": False,
        }
        write_json(receipt_path, receipt)
        return {**receipt, "receipt_path": str(receipt_path)}


def rollback(receipt_path: Path, package: Path, *, write: bool) -> dict[str, Any]:
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"schema": SCHEMA, "ok": False, "status": "REJECTED", "write": write, "failures": [f"receipt_unreadable:{type(exc).__name__}:{exc}"]}
    if receipt.get("schema") != SCHEMA or receipt.get("status") != "MIGRATED_AND_INSTALLED":
        return {"schema": SCHEMA, "ok": False, "status": "REJECTED", "write": write, "failures": ["receipt_schema_or_status_invalid"]}
    package = absolute(package)
    if not package.is_file() or sha256(package) != receipt.get("package_sha256"):
        return {"schema": SCHEMA, "ok": False, "status": "REJECTED", "write": write, "failures": ["package_sha256_mismatch"]}
    home = absolute(Path.home())
    target = Path(str(receipt.get("current_tool_root", "")))
    preimage = Path(str(receipt.get("current_tool_preimage", "")))
    installer_path = Path(str(receipt.get("installer_archive", "")))
    installer_sha256 = receipt.get("installer_sha256")
    try:
        validate_root(home, target, allow_missing=True)
        if lstat(preimage) is None:
            raise ValueError(f"preimage_missing:{preimage}")
        if not isinstance(installer_sha256, str) or not installer_path.is_file():
            raise ValueError("installer_archive_missing")
        if sha256(installer_path) != installer_sha256:
            raise ValueError("installer_archive_sha256_mismatch")
    except (OSError, ValueError) as exc:
        return {"schema": SCHEMA, "ok": False, "status": "REJECTED", "write": write, "failures": [f"rollback_preflight:{type(exc).__name__}:{exc}"]}
    result = {"schema": SCHEMA, "ok": True, "status": "ROLLBACK_PLANNED", "write": False, "receipt": str(receipt_path), "current_tool_root": str(target), "current_tool_preimage": str(preimage), "package": str(package)}
    if not write:
        return result
    try:
        installer = load_installer(installer_path)
        managed = receipt.get("managed_projection_backup")
        if isinstance(managed, dict) and managed.get("status") == "CREATED":
            restored = installer.rollback_install_backup(home_root=home, backup_root=Path(str(managed["backup_root"])))
            if not isinstance(restored, dict) or restored.get("ok") is not True:
                raise RuntimeError(f"managed_projection_rollback_failed:{restored}")
        remove_empty_tree(target)
        os.replace(preimage, target)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        return {"schema": SCHEMA, "ok": False, "status": "ROLLBACK_FAILED", "write": True, "receipt": str(receipt_path), "failures": [f"rollback:{type(exc).__name__}:{exc}"]}
    completed = {**result, "ok": True, "status": "ROLLED_BACK", "write": True}
    rollback_path = receipt_path.with_name(f"{receipt_path.stem}.rollback.json")
    write_json(rollback_path, completed)
    return {**completed, "rollback_receipt_path": str(rollback_path)}


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="decretum-current-tool-replica-test-") as raw:
        root = Path(raw)
        old = root / "old"
        archived = root / "archived"
        restored = root / "restored"
        old.mkdir()
        (old / "preserved.txt").write_text("preserved\n", encoding="utf-8")
        os.replace(old, archived)
        restored.mkdir()
        remove_empty_tree(restored)
        os.replace(archived, restored)
        checks["atomic_preimage_restore"] = (restored / "preserved.txt").is_file()
        nonempty = root / "nonempty"
        nonempty.mkdir()
        (nonempty / "unexpected.txt").write_text("block\n", encoding="utf-8")
        try:
            remove_empty_tree(nonempty)
        except ValueError:
            checks["nonempty_rollback_target_rejected"] = nonempty.is_dir()
        else:
            checks["nonempty_rollback_target_rejected"] = False
        try:
            validate_member(zipfile.ZipInfo("../escape"))
        except ValueError:
            checks["zip_traversal_rejected"] = True
        else:
            checks["zip_traversal_rejected"] = False
    return {"schema": SCHEMA, "ok": all(checks.values()), "status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "apply", "rollback", "self-test"))
    parser.add_argument("--package", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.command == "self-test":
        result = self_test()
    elif args.command == "plan":
        if args.package is None:
            parser.error("plan requires --package")
        result = apply(args.package, write=False)
    elif args.command == "apply":
        if args.package is None:
            parser.error("apply requires --package")
        result = apply(args.package, write=args.write)
    else:
        if args.receipt is None or args.package is None:
            parser.error("rollback requires --receipt and --package")
        result = rollback(args.receipt, args.package, write=args.write)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) if args.json else f"CURRENT_TOOL_REPLICA_{result.get('status', 'UNKNOWN')}")
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
