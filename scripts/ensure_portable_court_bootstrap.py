#!/usr/bin/env python3
"""Bootstrap a portable court-capability-router install on a target host.

The bootstrap is intentionally composed from the skill's own local scripts:
shared Shiguan seed creation, Obsidian linking, Shiguan service daemon setup,
Codex/Hermes built-in memory enablement, metadata-only Shiguan bridging, and
first-run superCC dependency installation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform as host_platform
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from typing import Any, Callable

from court_platform import user_data_base
from shiguan_paths import (
    default_legacy_shared_root,
    default_obsidian_shared_vault,
    default_previous_shared_root,
    default_shared_root,
    ensure_shared_seed,
    references_root,
    runtime_code_root,
    shared_seed_layout,
    shared_root,
)


DEFAULT_TIMEOUT = 120
GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_LATEST_DOWNLOAD = "https://github.com/{repo}/releases/latest/download/{asset}"
ZELLIJ_REPO = "zellij-org/zellij"
ZELLIJ_ASSET = "zellij-x86_64-pc-windows-msvc.zip"
SQUAD_REPO = os.environ.get("COURT_SQUAD_GITHUB_REPO", "mco-org/squad")
SQUAD_ASSET = "squad-x86_64-pc-windows-msvc.zip"
OPTIONAL_SUPERCC_DEPENDENCIES = [
    {
        "name": "zellij",
        "project": "Zellij",
        "url": "https://github.com/zellij-org/zellij",
        "purpose": "optional terminal workspace for visible superCC panes",
    },
    {
        "name": "squad",
        "project": "squad",
        "url": "https://github.com/mco-org/squad",
        "purpose": "optional structured task/message bus for superCC dispatch evidence",
    },
]


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def user_home() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("USERPROFILE") or Path.home())
    return Path(os.environ.get("HOME") or Path.home())


def default_install_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("COURT_TOOL_INSTALL_DIR", r"C:\Tools\bin"))
    return Path(os.environ.get("COURT_TOOL_INSTALL_DIR", str(user_home() / ".local" / "bin")))


def skill_root() -> Path:
    return runtime_code_root()


def path_kind(path: Path) -> str:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "unknown"
    junction_probe = getattr(path, "is_junction", None)
    try:
        if callable(junction_probe) and junction_probe():
            return "junction"
    except OSError:
        return "unknown"
    if path.is_symlink():
        return "symlink"
    reparse = int(getattr(metadata, "st_file_attributes", 0) or 0) & 0x400
    if reparse:
        return "reparse"
    return "directory" if path.is_dir() else "other"


def directory_identity(path: Path) -> dict[str, int]:
    metadata = path.stat()
    return {"device": int(metadata.st_dev), "inode": int(metadata.st_ino)}


def _same_lexical_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
        os.path.abspath(str(right))
    )


def _same_path(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return _same_lexical_path(left, right)


def _paths_match_exactly(values: list[Path], expected: list[Path]) -> bool:
    if len(values) != len(expected):
        return False
    unmatched = list(expected)
    for value in values:
        matches = [
            index
            for index, candidate in enumerate(unmatched)
            if _same_lexical_path(value, candidate)
        ]
        if len(matches) != 1:
            return False
        unmatched.pop(matches[0])
    return not unmatched


class CompatibilityJunctionAdapter:
    def target(self, path: Path) -> Path | None:
        if path_kind(path) != "junction":
            return None
        try:
            return path.resolve(strict=True)
        except OSError:
            return None

    def create(self, path: Path, target: Path) -> None:
        if sys.platform != "win32":
            raise RuntimeError("compatibility_junction_not_supported")
        if path_kind(path) != "absent" or path_kind(target) != "directory":
            raise RuntimeError("compatibility_junction_precondition_failed")
        path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/j", str(path), str(target)],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=30,
        )
        if result.returncode or path_kind(path) != "junction":
            raise RuntimeError("compatibility_junction_create_failed")

    def remove(self, path: Path, expected_target: Path) -> None:
        actual = self.target(path)
        if actual is None or os.path.normcase(str(actual)) != os.path.normcase(str(expected_target.resolve())):
            raise RuntimeError("compatibility_junction_target_mismatch")
        path.rmdir()


def _write_topology_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _write_topology_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def _capture_topology_control_preimage(
    canonical: Path,
    backup: Path,
    *,
    kind_probe: Callable[[Path], str],
) -> dict[str, dict[str, object]]:
    control_root = canonical.parent / "private-runtime" / "shiguan-migration"
    result: dict[str, dict[str, object]] = {}
    for name in ("shiguan-topology-receipt.json", "shiguan-topology-commit.json"):
        path = control_root / name
        kind = kind_probe(path)
        if kind == "absent":
            result[name] = {"state": "absent"}
            continue
        if kind != "other" or not path.is_file() or path.is_symlink():
            raise RuntimeError(f"topology_control_preimage_untrusted:{name}:{kind}")
        payload = path.read_bytes()
        relative = Path("control-preimage") / name
        _write_topology_bytes(backup / relative, payload)
        result[name] = {
            "state": "file",
            "backup_relative": relative.as_posix(),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }
    return result


def _restore_topology_control_preimage(
    canonical: Path,
    backup: Path,
    preimage: dict[str, dict[str, object]],
    *,
    kind_probe: Callable[[Path], str],
) -> None:
    control_root = canonical.parent / "private-runtime" / "shiguan-migration"
    for name, metadata in preimage.items():
        path = control_root / name
        state = metadata.get("state")
        kind = kind_probe(path)
        if state == "absent":
            if kind == "absent":
                continue
            if kind != "other" or not path.is_file() or path.is_symlink():
                raise RuntimeError(f"topology_control_rollback_untrusted:{name}:{kind}")
            path.unlink()
            continue
        if state != "file":
            raise RuntimeError(f"topology_control_preimage_state_invalid:{name}")
        relative = Path(str(metadata.get("backup_relative", "")))
        source = backup / relative
        payload = source.read_bytes()
        if (
            hashlib.sha256(payload).hexdigest() != metadata.get("sha256")
            or len(payload) != metadata.get("size")
        ):
            raise RuntimeError(f"topology_control_backup_invalid:{name}")
        if kind not in {"absent", "other"} or (
            kind == "other" and (not path.is_file() or path.is_symlink())
        ):
            raise RuntimeError(f"topology_control_rollback_untrusted:{name}:{kind}")
        _write_topology_bytes(path, payload)


def ensure_physical_shiguan_topology(
    apply: bool,
    *,
    canonical_references: Path | None = None,
    legacy_references: list[Path] | None = None,
    junction_adapter: CompatibilityJunctionAdapter | None = None,
    backup_root: Path | None = None,
    kind_probe: Callable[[Path], str] | None = None,
    identity_probe: Callable[[Path], dict[str, int]] | None = None,
    replace_operation: Callable[[Path, Path], object] | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    """Create or atomically migrate one physical root without reading bodies."""

    canonical = canonical_references or (default_shared_root() / "references")
    legacy = legacy_references or [
        default_previous_shared_root() / "references",
        default_legacy_shared_root() / "references",
    ]
    deduplicated: list[Path] = []
    seen: set[str] = set()
    for path in legacy:
        key = os.path.normcase(os.path.abspath(str(path)))
        if key != os.path.normcase(os.path.abspath(str(canonical))) and key not in seen:
            seen.add(key)
            deduplicated.append(path)
    legacy = deduplicated
    probe_kind = kind_probe or path_kind
    probe_identity = identity_probe or directory_identity
    replace = replace_operation or os.replace
    runtime_platform = platform or sys.platform
    kinds = {str(path): probe_kind(path) for path in [canonical, *legacy]}
    if kinds[str(canonical)] not in {"absent", "directory"}:
        return {"ok": False, "status": "BLOCKED", "reason": "canonical_root_not_physical", "paths": kinds}
    physical_legacy = [path for path in legacy if kinds[str(path)] == "directory"]
    invalid_legacy = [
        path
        for path in legacy
        if kinds[str(path)] not in {"absent", "directory", "junction"}
    ]
    if invalid_legacy:
        return {"ok": False, "status": "BLOCKED", "reason": "legacy_root_untrusted", "paths": kinds}
    if kinds[str(canonical)] == "directory" and physical_legacy:
        return {"ok": False, "status": "BLOCKED", "reason": "dual_physical_shiguan_roots", "paths": kinds}
    if kinds[str(canonical)] == "absent" and len(physical_legacy) > 1:
        return {"ok": False, "status": "BLOCKED", "reason": "multiple_legacy_physical_roots", "paths": kinds}

    adapter = junction_adapter or CompatibilityJunctionAdapter()
    junction_targets: dict[str, str] = {}
    for path in legacy:
        if kinds[str(path)] != "junction":
            continue
        target = adapter.target(path)
        expected = canonical if kinds[str(canonical)] == "directory" else (physical_legacy[0] if physical_legacy else canonical)
        if target is None or not _same_path(target, expected):
            return {"ok": False, "status": "BLOCKED", "reason": "legacy_junction_mismatch", "paths": kinds}
        junction_targets[str(path)] = str(target)

    action = "REUSE_PHYSICAL_CANONICAL"
    source = None
    if kinds[str(canonical)] == "absent":
        if physical_legacy:
            action = "ATOMIC_RENAME_LEGACY_TO_CANONICAL"
            source = physical_legacy[0]
        else:
            action = "CREATE_PHYSICAL_CANONICAL"
    plan = {
        "schema": "court.shiguan_physical_topology.v1",
        "ok": True,
        "status": "PLANNED" if not apply else "IN_PROGRESS",
        "action": action,
        "canonical_references": str(canonical),
        "legacy_references": [str(path) for path in legacy],
        "preimage": kinds,
        "pending_body_access": "NO",
        "body_content_reads": 0,
        "body_hashes": 0,
        "physical_authority_required": True,
        "canonical_locator_kind": "physical_directory",
        "compatibility_locator_kind": "junction_not_symlink",
        "preexisting_junction_targets": junction_targets,
    }
    if not apply:
        return plan

    backup = backup_root or (
        user_home()
        / ".agents"
        / "install-backups"
        / "decretum-matrix"
        / f"shiguan-topology-{now_stamp()}-{os.getpid()}"
    )
    if backup.exists():
        return {**plan, "ok": False, "status": "BLOCKED", "reason": "backup_root_exists"}
    backup.mkdir(parents=True)
    _write_topology_json(backup / "preimage.json", plan)
    created_aliases: list[Path] = []
    removed_aliases: list[tuple[Path, Path]] = []
    moved_identity: dict[str, int] | None = None
    control_preimage: dict[str, dict[str, object]] = {}
    try:
        control_preimage = _capture_topology_control_preimage(
            canonical,
            backup,
            kind_probe=probe_kind,
        )
        _write_topology_json(backup / "control-preimage.json", control_preimage)
        if action == "ATOMIC_RENAME_LEGACY_TO_CANONICAL":
            assert source is not None
            for path in legacy:
                if probe_kind(path) != "junction":
                    continue
                target = adapter.target(path)
                if target is None or not _same_path(target, source):
                    raise RuntimeError("legacy_junction_pre_move_target_drift")
                adapter.remove(path, source)
                removed_aliases.append((path, source))
            moved_identity = probe_identity(source)
            canonical.parent.mkdir(parents=True, exist_ok=True)
            replace(source, canonical)
            if probe_kind(canonical) != "directory" or probe_identity(canonical) != moved_identity:
                raise RuntimeError("atomic_migration_identity_mismatch")
        elif action == "CREATE_PHYSICAL_CANONICAL":
            canonical.mkdir(parents=True, exist_ok=False)
        if probe_kind(canonical) != "directory":
            raise RuntimeError("canonical_root_not_physical_after_apply")
        if runtime_platform == "win32":
            for path in legacy:
                kind = probe_kind(path)
                if kind == "junction":
                    target = adapter.target(path)
                    if target is None or not _same_path(target, canonical):
                        raise RuntimeError("legacy_locator_target_drift_after_migration")
                    continue
                if kind != "absent":
                    raise RuntimeError("legacy_locator_not_empty_after_migration")
                adapter.create(path, canonical)
                created_aliases.append(path)
        postimage = {str(path): probe_kind(path) for path in [canonical, *legacy]}
        post_targets: dict[str, str] = {}
        if runtime_platform == "win32":
            for path in legacy:
                target = adapter.target(path)
                if postimage[str(path)] != "junction" or target is None or not _same_path(target, canonical):
                    raise RuntimeError("compatibility_junction_verification_failed")
                post_targets[str(path)] = str(target)
        receipt = {
            **plan,
            "status": "PHYSICAL_TOPOLOGY_VERIFIED",
            "committed_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
            "backup_root": str(backup),
            "postimage": postimage,
            "canonical_identity": probe_identity(canonical),
            "created_compatibility_junctions": [str(path) for path in created_aliases],
            "replaced_compatibility_junctions": [str(path) for path, _target in removed_aliases],
            "compatibility_junction_targets": post_targets,
            "control_preimage": control_preimage,
            "rollback_supported": True,
            "rollback_scope": "automatic_transaction_failure_before_external_use",
        }
        _write_topology_json(backup / "receipt.json", receipt)
        control_root = canonical.parent / "private-runtime" / "shiguan-migration"
        persistent_receipt = control_root / "shiguan-topology-receipt.json"
        _write_topology_json(persistent_receipt, receipt)
        receipt_digest = hashlib.sha256(
            json.dumps(
                receipt,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        _write_topology_json(
            control_root / "shiguan-topology-commit.json",
            {
                "schema": "court.shiguan_physical_topology.commit.v1",
                "state": "COMMITTED",
                "canonical_references": str(canonical),
                "receipt_path": str(persistent_receipt),
                "receipt_sha256": receipt_digest,
                "committed_at": receipt["committed_at"],
            },
        )
        receipt["persistent_receipt"] = str(persistent_receipt)
        receipt["receipt_sha256"] = receipt_digest
        return receipt
    except Exception as exc:
        rollback_errors: list[str] = []
        for path in reversed(created_aliases):
            try:
                adapter.remove(path, canonical)
            except Exception as rollback_exc:  # noqa: BLE001 - preserve every rollback fault.
                rollback_errors.append(f"alias:{path}:{type(rollback_exc).__name__}:{rollback_exc}")
        if action == "ATOMIC_RENAME_LEGACY_TO_CANONICAL" and source is not None and probe_kind(canonical) == "directory":
            try:
                if moved_identity is None or probe_identity(canonical) != moved_identity:
                    raise RuntimeError("rollback_identity_mismatch")
                source.parent.mkdir(parents=True, exist_ok=True)
                replace(canonical, source)
            except Exception as rollback_exc:  # noqa: BLE001
                rollback_errors.append(f"move:{type(rollback_exc).__name__}:{rollback_exc}")
        elif action == "CREATE_PHYSICAL_CANONICAL" and probe_kind(canonical) == "directory":
            try:
                canonical.rmdir()
            except Exception as rollback_exc:  # noqa: BLE001
                rollback_errors.append(f"create:{type(rollback_exc).__name__}:{rollback_exc}")
        for path, target in removed_aliases:
            try:
                if probe_kind(path) != "absent":
                    raise RuntimeError("rollback_alias_destination_occupied")
                adapter.create(path, target)
            except Exception as rollback_exc:  # noqa: BLE001
                rollback_errors.append(f"alias_restore:{path}:{type(rollback_exc).__name__}:{rollback_exc}")
        if control_preimage:
            try:
                _restore_topology_control_preimage(
                    canonical,
                    backup,
                    control_preimage,
                    kind_probe=probe_kind,
                )
            except Exception as rollback_exc:  # noqa: BLE001
                rollback_errors.append(f"control:{type(rollback_exc).__name__}:{rollback_exc}")
        failed = {
            **plan,
            "ok": False,
            "status": "ROLLED_BACK" if not rollback_errors else "BLOCKED_MANUAL_RECOVERY",
            "reason": f"{type(exc).__name__}:{exc}",
            "backup_root": str(backup),
            "rollback_errors": rollback_errors,
        }
        _write_topology_json(backup / "failure.json", failed)
        return failed


def _capture_seed_preimage(
    refs: Path,
    backup: Path,
) -> dict[str, object]:
    layout = shared_seed_layout(refs)
    mutable = {str(path) for path in layout["mutable_control_files"]}
    directories = {
        str(path): path_kind(path) for path in layout["directories"]
    }
    files: dict[str, dict[str, object]] = {}
    for path in layout["files"]:
        kind = path_kind(path)
        metadata: dict[str, object] = {"state": kind}
        if str(path) in mutable and kind != "absent":
            if kind != "other" or not path.is_file() or path.is_symlink():
                raise RuntimeError(f"seed_control_preimage_untrusted:{path}:{kind}")
            payload = path.read_bytes()
            relative = Path("seed-control-preimage") / path.name
            _write_topology_bytes(backup / relative, payload)
            metadata.update(
                {
                    "backup_relative": relative.as_posix(),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                }
            )
        files[str(path)] = metadata
    preimage = {
        "schema": "court.shiguan_seed_preimage.v1",
        "references_root": str(refs),
        "directories": directories,
        "files": files,
        "pending_body_access": "NO",
        "body_content_reads": 0,
        "body_hashes": 0,
    }
    _write_topology_json(backup / "seed-preimage.json", preimage)
    return preimage


def _seed_receipt(preimage: dict[str, object]) -> dict[str, object]:
    directories = preimage.get("directories")
    files = preimage.get("files")
    if not isinstance(directories, dict) or not isinstance(files, dict):
        raise RuntimeError("seed_preimage_invalid")
    created_directories = [
        path
        for path, state in directories.items()
        if state == "absent" and path_kind(Path(path)) == "directory"
    ]
    created_files = [
        path
        for path, metadata in files.items()
        if isinstance(metadata, dict)
        and metadata.get("state") == "absent"
        and path_kind(Path(path)) == "other"
        and Path(path).is_file()
        and not Path(path).is_symlink()
    ]
    return {
        "schema": "court.shiguan_seed_transaction.v1",
        "status": "SEEDED",
        "created_directories": created_directories,
        "created_files": created_files,
        "pending_body_access": "NO",
        "body_content_reads": 0,
        "body_hashes": 0,
        "rollback_supported": True,
    }


def _rollback_seed_preimage(
    preimage: dict[str, object],
    backup: Path,
) -> dict[str, object]:
    directories = preimage.get("directories")
    files = preimage.get("files")
    if not isinstance(directories, dict) or not isinstance(files, dict):
        raise RuntimeError("seed_preimage_invalid")
    removed_files: list[str] = []
    restored_files: list[str] = []
    for value, metadata in reversed(list(files.items())):
        if not isinstance(metadata, dict):
            raise RuntimeError("seed_file_preimage_invalid")
        path = Path(value)
        before = metadata.get("state")
        current = path_kind(path)
        if before == "absent":
            if current == "absent":
                continue
            if current != "other" or not path.is_file() or path.is_symlink():
                raise RuntimeError(f"seed_rollback_file_untrusted:{path}:{current}")
            path.unlink()
            removed_files.append(str(path))
            continue
        backup_relative = metadata.get("backup_relative")
        if backup_relative is None:
            continue
        source = backup / Path(str(backup_relative))
        payload = source.read_bytes()
        if (
            hashlib.sha256(payload).hexdigest() != metadata.get("sha256")
            or len(payload) != metadata.get("size")
        ):
            raise RuntimeError(f"seed_control_backup_invalid:{path}")
        if current not in {"absent", "other"} or (
            current == "other" and (not path.is_file() or path.is_symlink())
        ):
            raise RuntimeError(f"seed_control_rollback_untrusted:{path}:{current}")
        _write_topology_bytes(path, payload)
        restored_files.append(str(path))
    removed_directories: list[str] = []
    for value, before in reversed(list(directories.items())):
        path = Path(value)
        if before != "absent" or path_kind(path) == "absent":
            continue
        if path_kind(path) != "directory":
            raise RuntimeError(f"seed_rollback_directory_untrusted:{path}")
        path.rmdir()
        removed_directories.append(str(path))
    return {
        "schema": "court.shiguan_seed_rollback.v1",
        "status": "ROLLED_BACK",
        "removed_files": removed_files,
        "restored_files": restored_files,
        "removed_directories": removed_directories,
        "pending_body_access": "NO",
        "body_content_reads": 0,
        "body_hashes": 0,
    }


def _rollback_applied_topology(receipt: dict[str, Any]) -> dict[str, object]:
    canonical = Path(str(receipt.get("canonical_references", "")))
    backup = Path(str(receipt.get("backup_root", "")))
    identity = receipt.get("canonical_identity")
    legacy_values = receipt.get("legacy_references")
    expected_canonical = default_shared_root() / "references"
    expected_legacy = [
        default_previous_shared_root() / "references",
        default_legacy_shared_root() / "references",
    ]
    if (
        receipt.get("status") != "PHYSICAL_TOPOLOGY_VERIFIED"
        or not _same_path(canonical, expected_canonical)
        or not isinstance(legacy_values, list)
        or any(not isinstance(value, str) for value in legacy_values)
        or not _paths_match_exactly(
            [Path(str(value)) for value in legacy_values], expected_legacy
        )
        or path_kind(canonical) != "directory"
        or directory_identity(canonical) != identity
        or not backup.is_dir()
    ):
        raise RuntimeError("topology_rollback_receipt_invalid")
    adapter = CompatibilityJunctionAdapter()
    for value in reversed(receipt.get("created_compatibility_junctions", [])):
        adapter.remove(Path(str(value)), canonical)
    action = receipt.get("action")
    if action == "ATOMIC_RENAME_LEGACY_TO_CANONICAL":
        preimage = receipt.get("preimage")
        if not isinstance(preimage, dict):
            raise RuntimeError("topology_rollback_preimage_invalid")
        sources = [Path(path) for path, kind in preimage.items() if kind == "directory" and not _same_path(Path(path), canonical)]
        if len(sources) != 1 or path_kind(sources[0]) != "absent":
            raise RuntimeError("topology_rollback_source_invalid")
        sources[0].parent.mkdir(parents=True, exist_ok=True)
        os.replace(canonical, sources[0])
    elif action == "CREATE_PHYSICAL_CANONICAL":
        canonical.rmdir()
    elif action != "REUSE_PHYSICAL_CANONICAL":
        raise RuntimeError("topology_rollback_action_invalid")
    preexisting = receipt.get("preexisting_junction_targets")
    replaced = receipt.get("replaced_compatibility_junctions")
    if not isinstance(preexisting, dict) or not isinstance(replaced, list):
        raise RuntimeError("topology_rollback_alias_preimage_invalid")
    for value in replaced:
        path = Path(str(value))
        target_value = preexisting.get(str(path))
        if not isinstance(target_value, str) or path_kind(path) != "absent":
            raise RuntimeError("topology_rollback_alias_restore_invalid")
        adapter.create(path, Path(target_value))
    control_preimage = receipt.get("control_preimage")
    if not isinstance(control_preimage, dict):
        raise RuntimeError("topology_control_preimage_invalid")
    _restore_topology_control_preimage(
        canonical,
        backup,
        control_preimage,
        kind_probe=path_kind,
    )
    return {
        "schema": "court.shiguan_physical_topology.rollback.v1",
        "status": "ROLLED_BACK",
        "action": action,
        "pending_body_access": "NO",
        "body_content_reads": 0,
        "body_hashes": 0,
    }


def tool_env(install_dir: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    profile = os.environ.get("USERPROFILE") if sys.platform == "win32" else None
    if profile:
        env["HOME"] = profile
    paths = []
    if install_dir:
        paths.append(str(install_dir))
    if sys.platform == "win32":
        paths.append(r"C:\Tools\bin")
    current = env.get("PATH", "")
    current_lower = current.lower()
    for path in paths:
        if path and path.lower() not in current_lower:
            current = path + os.pathsep + current
            current_lower = current.lower()
    env["PATH"] = current
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def truncate(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"...<truncated {len(text) - limit} chars>"


def resolved_invocation(args: list[str], install_dir: Path | None = None) -> list[str]:
    if not args:
        return args
    command = args[0]
    if any(sep in command for sep in ("\\", "/")):
        resolved = command
    else:
        resolved = shutil.which(command, path=tool_env(install_dir).get("PATH")) or command
    suffix = Path(resolved).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        return ["cmd.exe", "/d", "/c", resolved, *args[1:]]
    if suffix == ".ps1":
        return [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            resolved,
            *args[1:],
        ]
    return [resolved, *args[1:]]


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    install_dir: Path | None = None,
    stdout_limit: int = 6000,
    stderr_limit: int = 4000,
) -> dict[str, Any]:
    invocation = resolved_invocation(args, install_dir)
    try:
        proc = subprocess.run(
            invocation,
            cwd=str(cwd) if cwd else None,
            env=tool_env(install_dir),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "args": args,
            "invocation": invocation,
            "stdout": truncate(proc.stdout.strip(), stdout_limit),
            "stderr": truncate(proc.stderr.strip(), stderr_limit),
        }
    except FileNotFoundError as exc:
        return {"ok": False, "returncode": None, "args": args, "stderr": f"not found: {exc}", "stdout": ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": None, "args": args, "stderr": f"timeout after {timeout}s", "stdout": ""}


def command_available(command: str, install_dir: Path | None = None) -> bool:
    return shutil.which(command, path=tool_env(install_dir).get("PATH")) is not None


def backup_file(path: Path) -> str:
    if not path.exists():
        return ""
    backup = path.with_name(path.name + f".court-bootstrap-{now_stamp()}.bak")
    shutil.copy2(path, backup)
    return str(backup)


def section_bounds(lines: list[str], section: str) -> tuple[int | None, int]:
    header = f"[{section}]"
    start: int | None = None
    end = len(lines)
    for index, line in enumerate(lines):
        if line.strip() == header:
            start = index
            break
    if start is None:
        return None, len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break
    return start, end


def ensure_toml_bool_settings(text: str, settings: dict[str, dict[str, bool]]) -> tuple[str, bool]:
    lines = text.splitlines()
    changed = False
    if text and not text.endswith(("\n", "\r\n")):
        changed = True
    for section, values in settings.items():
        start, end = section_bounds(lines, section)
        if start is None:
            if lines and lines[-1].strip():
                lines.append("")
            start = len(lines)
            lines.append(f"[{section}]")
            end = len(lines)
            changed = True
        for key, value in values.items():
            wanted = f"{key} = {'true' if value else 'false'}"
            key_re = re.compile(rf"^(\s*){re.escape(key)}\s*=")
            replaced = False
            for index in range(start + 1, end):
                if key_re.match(lines[index]):
                    if lines[index].strip() != wanted:
                        lines[index] = wanted
                        changed = True
                    replaced = True
                    break
            if not replaced:
                lines.insert(end, wanted)
                end += 1
                changed = True
    output = "\n".join(lines).rstrip() + "\n"
    return output, changed


def enable_codex_memory(apply: bool) -> dict[str, Any]:
    codex_home = Path(os.environ.get("CODEX_HOME") or (user_home() / ".codex"))
    path = codex_home / "config.toml"
    exists_before = path.exists()
    original = path.read_text(encoding="utf-8", errors="replace") if exists_before else ""
    updated, changed = ensure_toml_bool_settings(
        original,
        {
            "features": {"memories": True},
            "memories": {"generate_memories": True, "use_memories": True},
        },
    )
    backup = ""
    if apply and changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = backup_file(path)
        path.write_text(updated, encoding="utf-8", newline="\n")
    return {
        "ok": True,
        "path": str(path),
        "exists_before": exists_before,
        "changed": changed and apply,
        "would_change": changed and not apply,
        "backup": backup,
        "settings": {
            "features.memories": True,
            "memories.generate_memories": True,
            "memories.use_memories": True,
        },
    }


def hermes_config_path() -> Path:
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        return Path(env_home) / "config.yaml"
    local = user_data_base() / "hermes" / "config.yaml"
    if local.exists() or local.parent.exists():
        return local
    return user_home() / ".hermes" / "config.yaml"


def ensure_simple_yaml_section(text: str, section: str, values: dict[str, bool]) -> tuple[str, bool]:
    lines = text.splitlines()
    changed = False
    start: int | None = None
    end = len(lines)
    section_re = re.compile(rf"^{re.escape(section)}:\s*(?:#.*)?$")
    for index, line in enumerate(lines):
        if section_re.match(line.strip()):
            start = index
            break
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{section}:")
        start = len(lines) - 1
        end = len(lines)
        changed = True
    else:
        for index in range(start + 1, len(lines)):
            line = lines[index]
            if line.strip() and not line.startswith((" ", "\t")):
                end = index
                break
    for key, value in values.items():
        wanted = f"  {key}: {'true' if value else 'false'}"
        key_re = re.compile(rf"^\s+{re.escape(key)}\s*:")
        replaced = False
        for index in range(start + 1, end):
            if key_re.match(lines[index]):
                if lines[index].strip() != wanted.strip():
                    lines[index] = wanted
                    changed = True
                replaced = True
                break
        if not replaced:
            lines.insert(end, wanted)
            end += 1
            changed = True
    return "\n".join(lines).rstrip() + "\n", changed


def enable_hermes_memory(apply: bool) -> dict[str, Any]:
    path = hermes_config_path()
    exists_before = path.exists()
    original = path.read_text(encoding="utf-8", errors="replace") if exists_before else ""
    updated, changed = ensure_simple_yaml_section(
        original,
        "memory",
        {"memory_enabled": True, "user_profile_enabled": True},
    )
    backup = ""
    if apply and changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = backup_file(path)
        path.write_text(updated, encoding="utf-8", newline="\n")
    return {
        "ok": True,
        "path": str(path),
        "exists_before": exists_before,
        "changed": changed and apply,
        "would_change": changed and not apply,
        "backup": backup,
        "settings": {"memory.memory_enabled": True, "memory.user_profile_enabled": True},
        "provider_policy": "preserve_existing_provider",
    }


def ensure_shared(apply: bool) -> dict[str, Any]:
    topology = ensure_physical_shiguan_topology(apply)
    if not topology.get("ok"):
        return {
            "ok": False,
            "changed": False,
            "topology": topology,
            "reason": topology.get("reason"),
        }
    root = shared_root()
    refs = references_root()
    seed_missing = not refs.exists()
    seed: dict[str, object] = {
        "schema": "court.shiguan_seed_transaction.v1",
        "status": "PLANNED" if not apply else "NOT_RUN",
        "pending_body_access": "NO",
        "body_content_reads": 0,
        "body_hashes": 0,
    }
    if apply:
        backup = Path(str(topology.get("backup_root", "")))
        try:
            preimage = _capture_seed_preimage(refs, backup)
            refs = ensure_shared_seed()
            seed = _seed_receipt(preimage)
        except Exception as exc:  # noqa: BLE001 - preserve both rollback outcomes.
            rollback_errors: list[str] = []
            seed_rollback: dict[str, object] | None = None
            topology_rollback: dict[str, object] | None = None
            if "preimage" in locals():
                try:
                    seed_rollback = _rollback_seed_preimage(preimage, backup)
                except Exception as rollback_exc:  # noqa: BLE001
                    rollback_errors.append(
                        f"seed:{type(rollback_exc).__name__}:{rollback_exc}"
                    )
            if not rollback_errors:
                try:
                    topology_rollback = _rollback_applied_topology(topology)
                except Exception as rollback_exc:  # noqa: BLE001
                    rollback_errors.append(
                        f"topology:{type(rollback_exc).__name__}:{rollback_exc}"
                    )
            return {
                "ok": False,
                "changed": False,
                "reason": f"seed_transaction_failed:{type(exc).__name__}:{exc}",
                "status": (
                    "ROLLED_BACK"
                    if not rollback_errors
                    else "BLOCKED_MANUAL_RECOVERY"
                ),
                "topology": topology,
                "seed_rollback": seed_rollback,
                "topology_rollback": topology_rollback,
                "rollback_errors": rollback_errors,
                "pending_body_access": "NO",
            }
    topology_changed = bool(
        apply
        and (
            topology.get("action") != "REUSE_PHYSICAL_CANONICAL"
            or topology.get("created_compatibility_junctions")
        )
    )
    return {
        "ok": True,
        "changed": topology_changed or (apply and seed_missing),
        "would_change": not apply and seed_missing,
        "shared_root": str(root),
        "references_root": str(refs),
        "seed_exists": refs.exists(),
        "topology": topology,
        "seed": seed,
    }


def rollback_shared_transaction(backup_root: Path) -> dict[str, object]:
    backup = Path(backup_root).resolve(strict=False)
    allowed = (
        user_home()
        / ".agents"
        / "install-backups"
        / "decretum-matrix"
    ).resolve(strict=False)
    try:
        backup.relative_to(allowed)
    except ValueError:
        return {
            "ok": False,
            "changed": False,
            "status": "BLOCKED",
            "reason": "shared_transaction_backup_outside_authority",
        }
    try:
        seed_preimage = json.loads(
            (backup / "seed-preimage.json").read_text(encoding="utf-8")
        )
        topology = json.loads(
            (backup / "receipt.json").read_text(encoding="utf-8")
        )
        if not isinstance(seed_preimage, dict) or not isinstance(topology, dict):
            raise RuntimeError("shared_transaction_receipt_invalid")
        expected_refs = default_shared_root() / "references"
        layout = shared_seed_layout(expected_refs)
        directory_preimage = seed_preimage.get("directories")
        file_preimage = seed_preimage.get("files")
        if (
            not _same_path(
                Path(str(seed_preimage.get("references_root", ""))),
                expected_refs,
            )
            or not isinstance(directory_preimage, dict)
            or not isinstance(file_preimage, dict)
            or any(not isinstance(value, str) for value in directory_preimage)
            or any(not isinstance(value, str) for value in file_preimage)
            or not _paths_match_exactly(
                [Path(value) for value in directory_preimage],
                list(layout["directories"]),
            )
            or not _paths_match_exactly(
                [Path(value) for value in file_preimage],
                list(layout["files"]),
            )
        ):
            raise RuntimeError("shared_transaction_preimage_scope_invalid")
        seed = _rollback_seed_preimage(seed_preimage, backup)
        topology_result = _rollback_applied_topology(topology)
        receipt = {
            "schema": "court.shiguan_shared_transaction.rollback.v1",
            "ok": True,
            "changed": True,
            "status": "ROLLED_BACK",
            "backup_root": str(backup),
            "seed": seed,
            "topology": topology_result,
            "pending_body_access": "NO",
            "body_content_reads": 0,
            "body_hashes": 0,
        }
        _write_topology_json(backup / "shared-rollback-receipt.json", receipt)
        return receipt
    except Exception as exc:  # noqa: BLE001
        return {
            "schema": "court.shiguan_shared_transaction.rollback.v1",
            "ok": False,
            "changed": False,
            "status": "BLOCKED_MANUAL_RECOVERY",
            "reason": f"{type(exc).__name__}:{exc}",
            "backup_root": str(backup),
            "pending_body_access": "NO",
        }


def ensure_obsidian(apply: bool, set_open: bool) -> dict[str, Any]:
    script = skill_root() / "scripts" / "ensure_obsidian_shared_vault.py"
    shared_vault = default_obsidian_shared_vault()
    if not apply:
        registered = False
        config_path = ""
        vault_key = ""
        try:
            from ensure_obsidian_shared_vault import obsidian_config_path, read_json, vault_id

            config = obsidian_config_path()
            config_path = str(config)
            vault_key = vault_id(shared_vault)
            data = read_json(config, {"vaults": {}})
            vaults = data.get("vaults") if isinstance(data, dict) else {}
            registered = isinstance(vaults, dict) and vault_key in vaults
        except Exception as exc:  # noqa: BLE001 - check-only diagnostics should stay non-fatal.
            return {
                "ok": True,
                "changed": False,
                "check_only": True,
                "script": str(script),
                "shared_vault_path": str(shared_vault),
                "set_open": set_open,
                "registered": False,
                "check_warning": str(exc),
            }
        return {
            "ok": True,
            "changed": False,
            "check_only": True,
            "script": str(script),
            "shared_vault_path": str(shared_vault),
            "set_open": set_open,
            "obsidian_config": config_path,
            "vault_id": vault_key,
            "registered": registered,
            "would_change": not registered,
        }
    args = [sys.executable, str(script)]
    if not set_open:
        args.append("--no-set-open")
    result = run_command(args, cwd=skill_root(), timeout=60)
    return {"ok": result["ok"], "changed": result["ok"], "script": str(script), "result": result}


def ensure_service_daemon(apply: bool) -> dict[str, Any]:
    script = skill_root() / "scripts" / "ensure_shiguan_service_daemon.py"
    if not apply:
        status = references_root() / "court-runtime" / "shiguan-service-daemon.json"
        task = run_command(["schtasks", "/Query", "/TN", "CourtShiguanDaemon"], timeout=20) if sys.platform == "win32" else {}
        return {
            "ok": True,
            "changed": False,
            "check_only": True,
            "script": str(script),
            "status_path": str(status),
            "status_exists": status.exists(),
            "task_exists": bool(task.get("ok")),
            "would_change": not status.exists() or (sys.platform == "win32" and not task.get("ok")),
        }
    arguments = [sys.executable, str(script)]
    if os.environ.get("DECRETUM_MATRIX_BOOTSTRAP_INSTALL_CONTEXT") == "npm":
        arguments.append("--no-start-now")
    result = run_command(arguments, cwd=skill_root(), timeout=90)
    return {"ok": result["ok"], "changed": result["ok"], "script": str(script), "result": result}


def run_memory_bridge(apply: bool, result_json: str = "") -> dict[str, Any]:
    script = skill_root() / "scripts" / "internal_memory_shiguan_bridge.py"
    if not apply:
        result = run_command(
            [sys.executable, str(script), "inspect", "--agents", "all", "--content-mode", "metadata", "--format", "json"],
            cwd=skill_root(),
            timeout=60,
            stdout_limit=12000,
        )
        return {"ok": result["ok"], "changed": False, "mode": "inspect", "script": str(script), "result": result}
    args = [
        sys.executable,
        str(script),
        "record",
        "--agents",
        "all",
        "--content-mode",
        "metadata",
        "--format",
        "json",
        "--source-agent",
        "codex",
        "--refresh-mode",
        "async",
    ]
    if result_json:
        args.extend(["--result-json", result_json])
    result = run_command(args, cwd=skill_root(), timeout=90, stdout_limit=12000)
    return {"ok": result["ok"], "changed": result["ok"], "mode": "record", "script": str(script), "result": result}


def http_get_bytes(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "court-capability-router-bootstrap"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-approved bootstrap source.
        return response.read()


def fetch_release_assets(repo: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(http_get_bytes(GITHUB_API.format(repo=repo), timeout=30).decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []
    assets = data.get("assets")
    return assets if isinstance(assets, list) else []


def select_asset(repo: str, fallback_asset: str, regexes: list[str]) -> dict[str, str]:
    assets = fetch_release_assets(repo)
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in regexes]
    for pattern in compiled:
        for asset in assets:
            name = str(asset.get("name") or "")
            if pattern.search(name):
                return {
                    "url": str(asset.get("browser_download_url") or GITHUB_LATEST_DOWNLOAD.format(repo=repo, asset=name)),
                    "name": name,
                    "digest": str(asset.get("digest") or ""),
                    "source": "github_api",
                }
    return {
        "url": GITHUB_LATEST_DOWNLOAD.format(repo=repo, asset=fallback_asset),
        "name": fallback_asset,
        "digest": "",
        "source": "latest_download_fallback",
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checksum_from_digest(digest: str) -> str:
    text = digest.strip()
    if text.lower().startswith("sha256:"):
        return text.split(":", 1)[1].lower()
    if re.fullmatch(r"[a-fA-F0-9]{64}", text):
        return text.lower()
    return ""


def checksum_from_sidecar(asset_url: str) -> str:
    for suffix in (".sha256sum", ".sha256", ".sha256.txt"):
        try:
            text = http_get_bytes(asset_url + suffix, timeout=20).decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        match = re.search(r"\b([a-fA-F0-9]{64})\b", text)
        if match:
            return match.group(1).lower()
    return ""


def verify_download(name: str, data: bytes, expected: str, allow_unverified: bool) -> dict[str, Any]:
    actual = sha256_bytes(data)
    if expected:
        return {
            "ok": actual.lower() == expected.lower(),
            "status": "verified" if actual.lower() == expected.lower() else "mismatch",
            "sha256": actual,
            "expected_sha256": expected,
        }
    if allow_unverified:
        return {"ok": True, "status": "allowed_without_checksum", "sha256": actual, "expected_sha256": ""}
    return {
        "ok": False,
        "status": "checksum_unavailable",
        "sha256": actual,
        "expected_sha256": "",
        "reason": f"{name} release asset had no GitHub digest or sha256 sidecar",
    }


def normalized_host_arch() -> str:
    machine = host_platform.machine().lower()
    if machine in {"amd64", "x64", "x86-64"}:
        return "x86_64"
    if machine in {"arm64", "aarch64"}:
        return "aarch64"
    return machine or "unknown"


def host_release_target(tool: str) -> dict[str, str]:
    arch = normalized_host_arch()
    if sys.platform == "win32":
        if arch != "x86_64":
            return {"ok": "false", "reason": f"{tool} Windows bootstrap supports x86_64 only", "arch": arch}
        return {"ok": "true", "triple": "x86_64-pc-windows-msvc", "archive": "zip", "binary": f"{tool}.exe"}
    if sys.platform == "darwin":
        if arch not in {"x86_64", "aarch64"}:
            return {"ok": "false", "reason": f"{tool} macOS bootstrap does not know arch {arch}", "arch": arch}
        return {"ok": "true", "triple": f"{arch}-apple-darwin", "archive": "tar.gz", "binary": tool}
    if sys.platform.startswith("linux"):
        if tool == "squad" and arch != "x86_64":
            return {"ok": "false", "reason": "squad Linux bootstrap currently has no known aarch64 release asset", "arch": arch}
        if arch not in {"x86_64", "aarch64"}:
            return {"ok": "false", "reason": f"{tool} Linux bootstrap does not know arch {arch}", "arch": arch}
        return {"ok": "true", "triple": f"{arch}-unknown-linux-musl", "archive": "tar.gz", "binary": tool}
    return {"ok": "false", "reason": f"unsupported platform for {tool}: {sys.platform}", "arch": arch}


def release_asset_patterns(tool: str, target: dict[str, str]) -> tuple[str, list[str]]:
    triple = target["triple"]
    archive = target["archive"]
    if archive == "zip":
        fallback = f"{tool}-{triple}.zip"
        return fallback, [rf"^{re.escape(tool)}-{re.escape(triple)}\.zip$"]
    fallback = f"{tool}-{triple}.tar.gz"
    return fallback, [rf"^{re.escape(tool)}-{re.escape(triple)}\.tar\.gz$"]


def extract_binary_from_zip(zip_bytes: bytes, binary_name: str, install_dir: Path) -> dict[str, Any]:
    install_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="court-tool-install-") as temp_text:
        temp = Path(temp_text)
        archive_path = temp / "tool.zip"
        archive_path.write_bytes(zip_bytes)
        with zipfile.ZipFile(archive_path) as archive:
            candidates = [name for name in archive.namelist() if Path(name).name.lower() == binary_name.lower()]
            if not candidates:
                return {"ok": False, "reason": f"{binary_name} not found in zip"}
            target = install_dir / binary_name
            if target.exists():
                backup_file(target)
            with archive.open(candidates[0], "r") as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
    return finalize_installed_binary(install_dir / binary_name)


def extract_binary_from_tar(tar_bytes: bytes, binary_name: str, install_dir: Path) -> dict[str, Any]:
    install_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="court-tool-install-") as temp_text:
        temp = Path(temp_text)
        archive_path = temp / "tool.tar.gz"
        archive_path.write_bytes(tar_bytes)
        with tarfile.open(archive_path, mode="r:*") as archive:
            candidates = [
                member
                for member in archive.getmembers()
                if member.isfile() and Path(member.name).name.lower() == binary_name.lower()
            ]
            if not candidates:
                return {"ok": False, "reason": f"{binary_name} not found in tar archive"}
            source = archive.extractfile(candidates[0])
            if source is None:
                return {"ok": False, "reason": f"{binary_name} could not be extracted"}
            target = install_dir / binary_name
            if target.exists():
                backup_file(target)
            with source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
    return finalize_installed_binary(install_dir / binary_name)


def finalize_installed_binary(target: Path) -> dict[str, Any]:
    if not target.is_file():
        return {"ok": False, "reason": f"binary was not installed: {target}"}
    if sys.platform != "win32":
        target.chmod(target.stat().st_mode | 0o755)
    return {"ok": True, "target": str(target)}


def install_release_archive_tool(
    *,
    tool: str,
    repo: str,
    install_dir: Path,
    apply: bool,
    allow_unverified: bool,
    version_args: list[str],
) -> dict[str, Any]:
    available_before = command_available(tool, install_dir)
    if available_before:
        version = run_command([tool, *version_args], timeout=20, install_dir=install_dir)
        return {"ok": True, "tool": tool, "available_before": True, "changed": False, "version": version}
    target = host_release_target(tool)
    if target.get("ok") != "true":
        return {"ok": False, "tool": tool, "changed": False, "target": target, "reason": target.get("reason")}
    fallback_asset, regexes = release_asset_patterns(tool, target)
    asset = select_asset(repo, fallback_asset, regexes)
    if not apply:
        return {
            "ok": True,
            "tool": tool,
            "available_before": False,
            "changed": False,
            "would_install": True,
            "repo": repo,
            "asset": asset,
            "target": target,
            "install_dir": str(install_dir),
        }
    try:
        archive_bytes = http_get_bytes(asset["url"], timeout=120)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "tool": tool, "changed": False, "repo": repo, "asset": asset, "reason": str(exc)}
    expected = checksum_from_digest(asset.get("digest", "")) or checksum_from_sidecar(asset["url"])
    verification = verify_download(tool, archive_bytes, expected, allow_unverified)
    if not verification["ok"]:
        return {
            "ok": False,
            "tool": tool,
            "changed": False,
            "repo": repo,
            "asset": asset,
            "target": target,
            "verification": verification,
        }
    if str(target["archive"]) == "zip":
        install = extract_binary_from_zip(archive_bytes, str(target["binary"]), install_dir)
    else:
        install = extract_binary_from_tar(archive_bytes, str(target["binary"]), install_dir)
    version = run_command([tool, *version_args], timeout=20, install_dir=install_dir) if install.get("ok") else {}
    return {
        "ok": bool(install.get("ok")) and bool(version.get("ok")),
        "tool": tool,
        "available_before": False,
        "changed": bool(install.get("ok")),
        "repo": repo,
        "asset": asset,
        "target": target,
        "verification": verification,
        "install": install,
        "version": version,
    }


def ensure_squad_workspace(workspace: Path, install_dir: Path, apply: bool) -> dict[str, Any]:
    marker = workspace / ".squad"
    available = command_available("squad", install_dir)
    if not available:
        return {"ok": False, "changed": False, "workspace": str(workspace), "reason": "squad command unavailable"}
    if marker.exists():
        doctor = run_command(["squad", "doctor"], cwd=workspace, timeout=30, install_dir=install_dir)
        return {"ok": doctor["ok"], "changed": False, "workspace": str(workspace), "initialized": True, "doctor": doctor}
    if not apply:
        return {"ok": True, "changed": False, "would_init": True, "workspace": str(workspace)}
    init = run_command(["squad", "init"], cwd=workspace, timeout=60, install_dir=install_dir)
    doctor = run_command(["squad", "doctor"], cwd=workspace, timeout=30, install_dir=install_dir)
    return {
        "ok": init["ok"] and doctor["ok"],
        "changed": init["ok"],
        "workspace": str(workspace),
        "init": init,
        "doctor": doctor,
    }


def ensure_supercc_deps(args: argparse.Namespace) -> dict[str, Any]:
    install_dir = Path(args.install_dir).resolve()
    workspace = Path(args.workspace).resolve()
    zellij = install_release_archive_tool(
        tool="zellij",
        repo=ZELLIJ_REPO,
        install_dir=install_dir,
        apply=args.apply,
        allow_unverified=args.allow_unverified_release_asset,
        version_args=["--version"],
    )
    squad = install_release_archive_tool(
        tool="squad",
        repo=SQUAD_REPO,
        install_dir=install_dir,
        apply=args.apply,
        allow_unverified=args.allow_unverified_release_asset,
        version_args=["--version"],
    )
    squad_workspace = ensure_squad_workspace(workspace, install_dir, args.apply) if not args.no_squad_init else {
        "ok": True,
        "changed": False,
        "skipped": True,
        "reason": "--no-squad-init",
    }
    return {
        "ok": bool(zellij.get("ok")) and bool(squad.get("ok")) and bool(squad_workspace.get("ok")),
        "changed": bool(zellij.get("changed")) or bool(squad.get("changed")) or bool(squad_workspace.get("changed")),
        "install_dir": str(install_dir),
        "zellij": zellij,
        "squad": squad,
        "squad_workspace": squad_workspace,
        "sources": {
            "zellij": f"https://github.com/{ZELLIJ_REPO}/releases/latest",
            "squad": f"https://github.com/{SQUAD_REPO}/releases/latest",
        },
        "open_source_acknowledgements": OPTIONAL_SUPERCC_DEPENDENCIES,
    }


def step_status(step: dict[str, Any]) -> str:
    if not step.get("ok"):
        return "FAILED"
    if step.get("changed"):
        return "CHANGED"
    if step.get("check_only"):
        return "CHECK_ONLY"
    if step.get("would_change"):
        return "WOULD_CHANGE"
    return "OK"


def _bootstrap_payload(args: argparse.Namespace, steps: dict[str, Any]) -> dict[str, Any]:
    ok = all(bool(step.get("ok")) for step in steps.values())
    changed = any(bool(step.get("changed")) for step in steps.values())
    return {
        "ok": ok,
        "mode": "apply" if args.apply else "check",
        "changed": changed,
        "generated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
        "skill_root": str(skill_root()),
        "workspace": str(Path(args.workspace).resolve()),
        "step_status": {name: step_status(step) for name, step in steps.items()},
        "steps": steps,
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.check_only:
        args.apply = False
    if args.rollback_shared_transaction:
        args.apply = True
        steps = {
            "shared_transaction_rollback": rollback_shared_transaction(
                Path(args.rollback_shared_transaction)
            )
        }
        return _bootstrap_payload(args, steps)
    if args.shared_shiguan_and_obsidian_only:
        args.skip_supercc_deps = True
        args.supercc_deps_only = False
        args.skip_memory = True
        args.skip_memory_bridge = True
    steps: dict[str, Any] = {}
    if not args.skip_supercc_deps:
        steps["supercc_dependencies"] = ensure_supercc_deps(args)
        if not steps["supercc_dependencies"].get("ok"):
            return _bootstrap_payload(args, steps)
    if not args.supercc_deps_only:
        steps["shared_shiguan"] = ensure_shared(args.apply)
        if not steps["shared_shiguan"].get("ok"):
            return _bootstrap_payload(args, steps)
        if not args.skip_obsidian:
            steps["obsidian_shared_vault"] = ensure_obsidian(args.apply, args.set_open_obsidian)
            if not steps["obsidian_shared_vault"].get("ok"):
                return _bootstrap_payload(args, steps)
        if not args.skip_service_daemon:
            steps["shiguan_service_daemon"] = ensure_service_daemon(args.apply)
            if not steps["shiguan_service_daemon"].get("ok"):
                return _bootstrap_payload(args, steps)
        if not args.skip_memory:
            steps["codex_memory"] = enable_codex_memory(args.apply)
            if not steps["codex_memory"].get("ok"):
                return _bootstrap_payload(args, steps)
            steps["hermes_memory"] = enable_hermes_memory(args.apply)
            if not steps["hermes_memory"].get("ok"):
                return _bootstrap_payload(args, steps)
        if not args.skip_memory_bridge:
            steps["memory_shiguan_bridge"] = run_memory_bridge(args.apply, args.result_json)
    return _bootstrap_payload(args, steps)


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        f"portable_bootstrap: {'PASSED' if payload.get('ok') else 'FAILED'}",
        f"mode: {payload.get('mode')} changed={payload.get('changed')}",
    ]
    for name, status in payload.get("step_status", {}).items():
        lines.append(f"{name}: {status}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write configs, install first-run superCC dependencies, and record the bridge.")
    parser.add_argument("--check-only", action="store_true", help="Inspect/plan without changing host state.")
    parser.add_argument("--supercc-deps-only", action="store_true", help="Only install/check zellij+squad and initialize the squad workspace.")
    parser.add_argument("--workspace", default=str(user_home()), help="Workspace for squad init and superCC runtime. Defaults to the current user's home directory.")
    parser.add_argument("--install-dir", default=str(default_install_dir()), help="Directory for zellij and squad. Defaults to C:\\Tools\\bin on Windows and ~/.local/bin on POSIX.")
    parser.add_argument("--skip-supercc-deps", action="store_true")
    parser.add_argument("--skip-obsidian", action="store_true")
    parser.add_argument("--skip-service-daemon", action="store_true")
    parser.add_argument("--skip-memory", action="store_true")
    parser.add_argument("--skip-memory-bridge", action="store_true")
    parser.add_argument(
        "--rollback-shared-transaction",
        default="",
        help="Rollback one verified shared-Shiguan topology+seed transaction by backup root.",
    )
    parser.add_argument(
        "--shared-shiguan-and-obsidian-only",
        action="store_true",
        help="Install the physical shared Shiguan topology, Obsidian binding, and service only.",
    )
    parser.add_argument("--set-open-obsidian", action="store_true", help="Mark the shared Shiguan vault as Obsidian's open vault.")
    parser.add_argument("--no-squad-init", action="store_true", help="Do not run squad init when the workspace lacks .squad.")
    parser.add_argument("--allow-unverified-release-asset", action="store_true", help="Install a release asset even if no sha256 digest/sidecar is available.")
    parser.add_argument("--result-json", default="", help="Optional result JSON path passed to the memory bridge archive command.")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = build_payload(args)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(payload))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
