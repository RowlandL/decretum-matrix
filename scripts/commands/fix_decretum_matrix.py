

#!/usr/bin/env python3
"""Plan or apply Decretum Matrix update, migration, and rollback repairs."""

from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
from copy import deepcopy
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import shutil
import stat
import sys
import subprocess
import tempfile
import uuid
import zipfile

sys.dont_write_bytecode = True

from court_diagnostics import (
    NAME,
    PROJECTION_PATH,
    resolve_user_path,
    select_source,
    write_audit_event,
)


SCHEMA = "decretum.fix.v1"
CANDIDATE_RECEIPT_SCHEMA = "court.release_candidate_receipt.v1"
CANDIDATE_PACKAGE_SCHEMA = "decretum.npm_local_install_candidate.v1"
CANDIDATE_STATE = "CANDIDATE_NOT_RELEASED"
INSTALLATION_ACCEPTANCE_SCHEMA = "court.installation_acceptance.v1"
POST_PROJECTION_PRODUCER_SCHEMA = "court.active_copy_hashes.v2"
POST_PROJECTION_CONTRACT = "POST_INSTALL_STANDALONE_HASH_CHECK"
POST_PROJECTION_CHECKER_RELATIVE = Path("scripts/checks/check_active_copy_hashes.py")
MAX_METADATA_BYTES = 256 * 1024
NPM_PACKAGE_NAME = "@rowlandl/decretum-matrix"
NPM_REPLACE_BACKUP_SCHEMA = "decretum.npm_global_replace_backup.v1"
NPM_PACKAGE_RELATIVE = PurePosixPath("node_modules/@rowlandl/decretum-matrix")
NPM_LOCAL_BIN_RELATIVES = (
    PurePosixPath("node_modules/.bin/decretum-matrix"),
    PurePosixPath("node_modules/.bin/decretum-matrix.cmd"),
    PurePosixPath("node_modules/.bin/decretum-matrix.ps1"),
)
NPM_GLOBAL_SHIM_RELATIVES = (
    PurePosixPath("decretum-matrix"),
    PurePosixPath("decretum-matrix.cmd"),
    PurePosixPath("decretum-matrix.ps1"),
)


def _home_root(value: str | None) -> Path:
    return resolve_user_path(value, default=Path.home())


def _sync_codex_agent_roles(home: Path, *, write: bool) -> dict[str, object]:
    """Reuse the existing renderer for native Codex role files."""

    module = importlib.import_module("sync_codex_agents_from_profiles")
    keys = (
        "APPDATA",
        "CODEX_HOME",
        "HOME",
        "LOCALAPPDATA",
        "USERPROFILE",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
    )
    previous = {key: os.environ.get(key) for key in keys}
    os.environ.update(
        {
            "APPDATA": str(home / "AppData" / "Roaming"),
            "CODEX_HOME": str(home / ".codex"),
            "HOME": str(home),
            "LOCALAPPDATA": str(home / "AppData" / "Local"),
            "USERPROFILE": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_CACHE_HOME": str(home / ".cache"),
        }
    )
    try:
        result = module.sync_agents(write=write)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return result if isinstance(result, dict) else {"ok": False, "status": "INVALID"}


def _nonempty(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _is_link_or_reparse(path: Path) -> bool:
    try:
        value = path.lstat()
    except FileNotFoundError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(value.st_mode) or bool(
        reparse_flag and getattr(value, "st_file_attributes", 0) & reparse_flag
    )


def _physical_directory(path: Path, *, label: str) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    for candidate in [*reversed(absolute.parents), absolute]:
        try:
            value = candidate.lstat()
        except FileNotFoundError as exc:
            raise RuntimeError(f"{label}_missing:{candidate}") from exc
        if _is_link_or_reparse(candidate):
            raise RuntimeError(f"{label}_link_or_reparse:{candidate}")
        if not stat.S_ISDIR(value.st_mode):
            raise RuntimeError(f"{label}_not_directory:{candidate}")
    return absolute


def _read_json_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        value = path.lstat()
        if _is_link_or_reparse(path) or not stat.S_ISREG(value.st_mode):
            raise RuntimeError(f"{label}_not_regular")
        if value.st_size > MAX_METADATA_BYTES:
            raise RuntimeError(f"{label}_oversized")
        payload = path.read_text(encoding="utf-8")
        if len(payload.encode("utf-8")) > MAX_METADATA_BYTES:
            raise RuntimeError(f"{label}_oversized")
        decoded = json.loads(payload)
    except RuntimeError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label}_invalid:{type(exc).__name__}") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError(f"{label}_object_required")
    return decoded


def _safe_candidate_file(root: Path, relative: object, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise RuntimeError(f"{label}_path_invalid")
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or candidate.drive or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise RuntimeError(f"{label}_path_invalid")
    path = (root / Path(*candidate.parts)).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"{label}_path_escape") from exc
    current = root
    for part in candidate.parts:
        current = current / part
        if _is_link_or_reparse(current):
            raise RuntimeError(f"{label}_link_or_reparse:{current}")
    return path


def _path_from_relative(root: Path, relative: PurePosixPath | str) -> Path:
    normalized = relative if isinstance(relative, PurePosixPath) else PurePosixPath(str(relative))
    if normalized.is_absolute() or any(part in {"", ".", ".."} for part in normalized.parts):
        raise RuntimeError("relative_path_invalid")
    return root / Path(*normalized.parts)


def _git_output(source: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={source.as_posix()}", *args],
            cwd=source,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"installation_binding_source_git:{type(exc).__name__}") from exc
    if result.returncode != 0:
        raise RuntimeError("installation_binding_source_git:unavailable")
    return result.stdout.strip()


def _validate_candidate_zip_payload(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            manifest_info = archive.getinfo(
                "decretum-matrix/release-manifest.json"
            )
            if (
                manifest_info.is_dir()
                or manifest_info.file_size > MAX_METADATA_BYTES
                or stat.S_IFMT((manifest_info.external_attr >> 16) & 0xFFFF)
                not in {0, stat.S_IFREG}
            ):
                raise RuntimeError("candidate_artifact_manifest_unsafe")
            payload = json.loads(
                archive.read("decretum-matrix/release-manifest.json").decode("utf-8")
            )
    except (
        OSError,
        KeyError,
        UnicodeError,
        json.JSONDecodeError,
        RuntimeError,
        zipfile.BadZipFile,
    ) as exc:
        raise RuntimeError("candidate_artifact_invalid") from exc
    entries = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise RuntimeError("candidate_artifact_manifest_invalid")
    checker_paths = sorted(
        {
            str(entry.get("path"))
            for entry in entries
            if isinstance(entry, dict)
            and isinstance(entry.get("path"), str)
            and (
                entry["path"] == "scripts/check_active_copy_hashes.py"
                or entry["path"].startswith("scripts/check_")
                or entry["path"].startswith("scripts/checks/")
            )
        }
    )
    if checker_paths:
        raise RuntimeError(
            "candidate_payload_checker_entries:" + ",".join(checker_paths)
        )


def _candidate_binding_metadata(
    source: Path,
    *,
    candidate_package_root: Path,
    candidate_receipt: Path | None,
    npm_prefix: Path | None,
    transaction_id: str,
    installation_id: str,
) -> dict[str, object]:
    source = _physical_directory(source, label="installation_binding_source")
    package_root = _physical_directory(
        candidate_package_root,
        label="installation_binding_candidate_package",
    )
    if npm_prefix is not None:
        prefix = _physical_directory(npm_prefix, label="installation_binding_npm_prefix")
        try:
            package_root.relative_to(prefix)
        except ValueError as exc:
            raise RuntimeError("candidate_package_outside_npm_prefix") from exc
    for value, label in (
        (transaction_id, "installation_binding_transaction_id"),
        (installation_id, "installation_binding_installation_id"),
    ):
        if _nonempty(value) is None or any(char in value for char in "/\\\x00"):
            raise RuntimeError(f"{label}_invalid")

    status = _git_output(source, "status", "--porcelain", "--untracked-files=no")
    if status:
        raise RuntimeError("candidate_source_tracked_worktree_dirty")
    source_commit = _git_output(source, "rev-parse", "HEAD")
    source_tree = _git_output(source, "rev-parse", "HEAD^{tree}")
    try:
        release_label = (source / "VERSION").read_text(encoding="utf-8").strip()
        source_manifest = _read_json_object(
            source / "release-manifest.json",
            label="installation_binding_source_metadata",
        )
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"installation_binding_source_metadata:{type(exc).__name__}") from exc
    manifest_label = _nonempty(source_manifest.get("release_label"))
    artifact_name = _nonempty(source_manifest.get("artifact_name"))
    if (
        not release_label
        or manifest_label != release_label
        or not artifact_name
        or "/" in artifact_name
        or "\\" in artifact_name
    ):
        raise RuntimeError("installation_binding_source_metadata:release_identity_mismatch")
    expected_artifact_ref = f"release/{artifact_name}@{source_commit}"
    expected_build_id = f"{release_label}:{source_commit}:{source_tree}"

    package = _read_json_object(package_root / "package.json", label="candidate_package")
    package_identity = package.get("decretumMatrix")
    if not isinstance(package_identity, dict):
        raise RuntimeError("candidate_package_metadata_missing")
    if package_identity.get("schema") != CANDIDATE_PACKAGE_SCHEMA:
        raise RuntimeError("candidate_package_schema_mismatch")
    if package_identity.get("payloadKind") != "runtime":
        raise RuntimeError("candidate_package_payload_kind_mismatch")
    if package_identity.get("candidate") != "local-install" or package_identity.get("private") is not True:
        raise RuntimeError("candidate_package_not_private_local")
    if package_identity.get("publication") != "FORBIDDEN":
        raise RuntimeError("candidate_package_publication_not_forbidden")
    package_label = _nonempty(package_identity.get("releaseLabel"))
    package_artifact_ref = _nonempty(package_identity.get("artifactRef"))
    package_build_id = _nonempty(package_identity.get("buildId"))
    package_source = package_identity.get("source")
    if package_label != release_label:
        raise RuntimeError("candidate_release_label_mismatch")
    if package_artifact_ref != expected_artifact_ref:
        raise RuntimeError("candidate_artifact_ref_mismatch")
    if package_build_id != expected_build_id:
        raise RuntimeError("candidate_build_id_mismatch")
    if not isinstance(package_source, dict) or (
        package_source.get("commit") != source_commit
        or package_source.get("tree") != source_tree
    ):
        raise RuntimeError("candidate_source_identity_mismatch")
    nested_binding = package_identity.get("installationBinding")
    if not isinstance(nested_binding, dict) or any(
        nested_binding.get(key) != expected
        for key, expected in (
            ("schema", "court.installation_binding.v2"),
            ("source_commit", source_commit),
            ("release_label", release_label),
            ("artifact_ref", expected_artifact_ref),
            ("build_id", expected_build_id),
        )
    ):
        raise RuntimeError("candidate_package_binding_metadata_mismatch")
    cli = package_identity.get("cli")
    if not isinstance(cli, dict) or cli.get("installLifecycleScripts") is not False or cli.get(
        "postinstallContract"
    ) != "disabled_explicit_installer_required":
        raise RuntimeError("candidate_package_lifecycle_contract_mismatch")
    scripts = package.get("scripts")
    if isinstance(scripts, dict) and "postinstall" in scripts:
        raise RuntimeError("candidate_package_postinstall_present")
    for relative in ("bin/decretum-matrix.js", "bin/decretum-matrix.py"):
        path = _safe_candidate_file(package_root, relative, label="candidate_shim")
        try:
            value = path.lstat()
        except OSError as exc:
            raise RuntimeError("candidate_shim_missing") from exc
        if _is_link_or_reparse(path) or not stat.S_ISREG(value.st_mode):
            raise RuntimeError("candidate_shim_not_regular")

    receipt_relative = package_identity.get("candidateReceipt")
    if candidate_receipt is None:
        if not isinstance(receipt_relative, str):
            raise RuntimeError("candidate_receipt_missing")
        receipt_path = _safe_candidate_file(
            package_root,
            receipt_relative,
            label="candidate_receipt",
        )
    else:
        receipt_path = Path(candidate_receipt).resolve(strict=False)
        try:
            receipt_relative_value = receipt_path.relative_to(package_root).as_posix()
        except ValueError as exc:
            raise RuntimeError("candidate_receipt_outside_package") from exc
        receipt_path = _safe_candidate_file(
            package_root,
            receipt_relative_value,
            label="candidate_receipt",
        )
    receipt = _read_json_object(receipt_path, label="candidate_receipt")
    if receipt.get("schema") != CANDIDATE_RECEIPT_SCHEMA or receipt.get("state") != CANDIDATE_STATE:
        raise RuntimeError("candidate_receipt_schema_or_state_mismatch")
    if receipt.get("release_label") != release_label or receipt.get("candidate_id") != source_commit:
        raise RuntimeError("candidate_receipt_identity_mismatch")
    receipt_source = receipt.get("source")
    if not isinstance(receipt_source, dict) or (
        receipt_source.get("head_commit") != source_commit
        or receipt_source.get("tree") != source_tree
        or receipt_source.get("worktree_clean") is not True
    ):
        raise RuntimeError("candidate_receipt_source_mismatch")
    receipt_manifest = receipt.get("release_manifest")
    if (
        not isinstance(receipt_manifest, dict)
        or receipt_manifest.get("path") != "release-manifest.json"
        or receipt_manifest.get("expected_final_tag")
        != source_manifest.get("expected_final_tag")
    ):
        raise RuntimeError("candidate_receipt_manifest_mismatch")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or not any(
        isinstance(item, dict) and item.get("name") == artifact_name
        for item in artifacts
    ):
        raise RuntimeError("candidate_receipt_artifact_missing")
    artifact_path = _safe_candidate_file(
        package_root,
        f"release/{artifact_name}",
        label="candidate_artifact",
    )
    if not artifact_path.is_file() or _is_link_or_reparse(artifact_path):
        raise RuntimeError("candidate_artifact_missing")
    _validate_candidate_zip_payload(artifact_path)
    receipt_ref = f"candidate:{receipt_path.relative_to(package_root).as_posix()}@{source_commit}"
    return {
        "source_commit": source_commit,
        "source_tree": source_tree,
        "release_label": release_label,
        "artifact_ref": expected_artifact_ref,
        "build_id": expected_build_id,
        "installation_id": installation_id,
        "transaction_id": transaction_id,
        "provenance_receipt_ref": receipt_ref,
        "candidate_package_root": str(package_root),
        "candidate_receipt_ref": receipt_ref,
    }


def _installation_binding_metadata(
    source: Path,
    *,
    candidate_package_root: Path | None = None,
    candidate_tgz: Path | None = None,
    candidate_receipt: Path | None = None,
    npm_prefix: Path | None = None,
    transaction_id: str | None = None,
    installation_id: str | None = None,
) -> dict[str, object]:
    """Derive binding metadata only from a clean, verified local candidate."""

    if candidate_package_root is None:
        raise RuntimeError("candidate_package_required")
    if _nonempty(transaction_id) is None or _nonempty(installation_id) is None:
        raise RuntimeError("installation_binding_transaction_and_installation_required")
    return _candidate_binding_metadata(
        source,
        candidate_package_root=candidate_package_root,
        candidate_receipt=candidate_receipt,
        npm_prefix=npm_prefix,
        transaction_id=str(transaction_id),
        installation_id=str(installation_id),
    )


def _acceptance_environment(home: Path) -> dict[str, str]:
    """Give the repository-only checker an isolated metadata environment."""

    environment = dict(os.environ)
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "DECRETUM_MATRIX_TEST_PLATFORM",
    ):
        environment.pop(key, None)
    local_appdata = home / "AppData" / "Local"
    appdata = home / "AppData" / "Roaming"
    environment.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(appdata),
            "LOCALAPPDATA": str(local_appdata),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "npm_config_prefix": str(home / "npm-prefix"),
            "npm_config_cache": str(home / "npm-cache"),
            "npm_config_userconfig": str(home / "empty-npm-userconfig"),
            "COURT_RUNTIME_ROOT": str(home / "court-runtime"),
            "COURT_SHARED_SHIGUAN_ROOT": str(home / "test-shiguan"),
            "COURT_DISABLE_AGENT_PRESENCE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
        }
    )
    return environment


def _npm_executable() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _candidate_tgz_regular(path: Path) -> Path:
    candidate = Path(os.path.abspath(os.fspath(path)))
    try:
        value = candidate.lstat()
    except OSError as exc:
        raise RuntimeError("candidate_tgz_missing") from exc
    if any(_is_link_or_reparse(parent) for parent in (candidate, *candidate.parents)) or not stat.S_ISREG(value.st_mode):
        raise RuntimeError("candidate_tgz_unsafe")
    return candidate


def _candidate_npm_owned_targets(prefix: Path) -> tuple[Path, ...]:
    """Return only paths npm may create for this private candidate package."""

    return tuple(
        _path_from_relative(prefix, relative)
        for relative in (NPM_PACKAGE_RELATIVE, *NPM_LOCAL_BIN_RELATIVES)
    )


def _candidate_npm_owned_relative(target: Path, prefix: Path) -> str:
    try:
        relative = Path(os.path.abspath(target)).relative_to(Path(os.path.abspath(prefix)))
    except ValueError as exc:
        raise RuntimeError("candidate_npm_target_outside_prefix") from exc
    return PurePosixPath(relative.as_posix()).as_posix()


def _candidate_npm_replacement_backup_root(home: Path) -> Path:
    base = home / ".agents" / "install-backups" / NAME
    base.mkdir(parents=True, exist_ok=True)
    _physical_directory(base, label="candidate_npm_backup_base")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    root = base / f"npm-local-{stamp}-{uuid.uuid4().hex}"
    root.mkdir(mode=0o700)
    return root


def _snapshot_optional_npm_shim(
    *,
    backup_root: Path,
    prefix: Path,
    relative: PurePosixPath,
) -> dict[str, object] | None:
    target = _path_from_relative(prefix, relative)
    if not target.exists() and not target.is_symlink():
        return None
    try:
        parent = _physical_directory(target.parent, label="candidate_npm_global_shim_parent")
    except RuntimeError as exc:
        raise RuntimeError(f"candidate_npm_global_shim_parent_invalid:{relative}") from exc
    try:
        parent.relative_to(prefix)
    except ValueError as exc:
        raise RuntimeError(f"candidate_npm_global_shim_parent_escape:{relative}") from exc
    status = target.lstat()
    if _is_link_or_reparse(target) or not stat.S_ISREG(status.st_mode):
        raise RuntimeError(f"candidate_npm_global_shim_unsafe:{relative}")
    backup_relative = PurePosixPath("shims") / relative
    backup_target = _path_from_relative(backup_root, backup_relative)
    backup_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup_target)
    return {
        "target_relative": relative.as_posix(),
        "backup_relative": backup_relative.as_posix(),
        "kind": "file",
        "action": "SNAPSHOT_ONLY",
        "size": status.st_size,
    }


def _move_existing_candidate_npm_target(
    *,
    backup_root: Path,
    prefix: Path,
    target: Path,
) -> dict[str, object] | None:
    if not target.exists() and not target.is_symlink():
        return None
    relative = PurePosixPath(_candidate_npm_owned_relative(target, prefix))
    parent = _physical_directory(target.parent, label="candidate_npm_existing_parent")
    try:
        parent.relative_to(prefix)
    except ValueError as exc:
        raise RuntimeError(f"candidate_npm_existing_parent_escape:{relative}") from exc
    status = target.lstat()
    kind = "symlink" if stat.S_ISLNK(status.st_mode) else "directory" if stat.S_ISDIR(status.st_mode) else "file"
    package_root = _path_from_relative(prefix, NPM_PACKAGE_RELATIVE)
    if kind == "symlink":
        if target not in [_path_from_relative(prefix, item) for item in NPM_LOCAL_BIN_RELATIVES] or not _candidate_npm_bin_link(target, package_root):
            raise RuntimeError(f"candidate_npm_existing_target_unsafe:{relative}")
    elif _is_link_or_reparse(target) or kind not in {"directory", "file"}:
        raise RuntimeError(f"candidate_npm_existing_target_unsafe:{relative}")
    backup_relative = PurePosixPath("targets") / relative
    backup_target = _path_from_relative(backup_root, backup_relative)
    backup_target.parent.mkdir(parents=True, exist_ok=True)
    if backup_target.exists() or backup_target.is_symlink():
        raise RuntimeError(f"candidate_npm_backup_collision:{backup_relative}")
    os.replace(target, backup_target)
    return {
        "target_relative": relative.as_posix(),
        "backup_relative": backup_relative.as_posix(),
        "kind": kind,
        "action": "MOVED",
        "size": status.st_size,
    }


def _prepare_candidate_npm_replacement(prefix: Path, home: Path) -> dict[str, object]:
    """Move only owned package/.bin targets aside; record paths relative to npm prefix."""

    backup_root = _candidate_npm_replacement_backup_root(home)
    moved: list[dict[str, object]] = []
    snapshots: list[dict[str, object]] = []
    try:
        for target in _candidate_npm_owned_targets(prefix):
            item = _move_existing_candidate_npm_target(
                backup_root=backup_root,
                prefix=prefix,
                target=target,
            )
            if item is not None:
                moved.append(item)
        for relative in NPM_GLOBAL_SHIM_RELATIVES:
            item = _snapshot_optional_npm_shim(
                backup_root=backup_root,
                prefix=prefix,
                relative=relative,
            )
            if item is not None:
                snapshots.append(item)
        manifest = {
            "schema": NPM_REPLACE_BACKUP_SCHEMA,
            "status": "CREATED",
            "path_style": "relative_to_npm_prefix",
            "npm_prefix_evidence": str(prefix),
            "backup_root": str(backup_root),
            "moved_targets": moved,
            "unmoved_global_shim_snapshots": snapshots,
            "rollback_supported": True,
        }
        (backup_root / "backup-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return manifest
    except Exception:
        _restore_candidate_npm_replacement(
            prefix=prefix,
            replacement_backup={
                "schema": NPM_REPLACE_BACKUP_SCHEMA,
                "status": "CREATED",
                "backup_root": str(backup_root),
                "moved_targets": moved,
            },
        )
        raise


def _restore_candidate_npm_replacement(
    *,
    prefix: Path,
    replacement_backup: dict[str, object] | None,
) -> dict[str, object]:
    if replacement_backup is None:
        return {"ok": True, "status": "NOT_REQUIRED"}
    if replacement_backup.get("schema") != NPM_REPLACE_BACKUP_SCHEMA:
        return {"ok": False, "status": "RECOVERY_REQUIRED", "reason": "npm_replacement_backup_schema_invalid"}
    backup_root_value = _nonempty(replacement_backup.get("backup_root"))
    moved = replacement_backup.get("moved_targets")
    if backup_root_value is None or not isinstance(moved, list):
        return {"ok": False, "status": "RECOVERY_REQUIRED", "reason": "npm_replacement_backup_incomplete"}
    backup_root = Path(backup_root_value)
    restored: list[dict[str, object]] = []
    try:
        _physical_directory(backup_root, label="candidate_npm_restore_backup_root")
        _candidate_npm_parent_check(prefix)
        for item in moved:
            if not isinstance(item, dict):
                raise RuntimeError("candidate_npm_restore_item_invalid")
            target_relative = _nonempty(item.get("target_relative"))
            backup_relative = _nonempty(item.get("backup_relative"))
            if target_relative is None or backup_relative is None:
                raise RuntimeError("candidate_npm_restore_relative_missing")
            target = _path_from_relative(prefix, PurePosixPath(target_relative))
            source = _path_from_relative(backup_root, PurePosixPath(backup_relative))
            if target.exists() or target.is_symlink():
                raise RuntimeError(f"candidate_npm_restore_target_exists:{target_relative}")
            if not source.exists() and not source.is_symlink():
                raise RuntimeError(f"candidate_npm_restore_source_missing:{backup_relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            _physical_directory(target.parent, label="candidate_npm_restore_parent")
            os.replace(source, target)
            restored.append({
                "target_relative": target_relative,
                "backup_relative": backup_relative,
            })
    except (OSError, RuntimeError) as exc:
        return {
            "ok": False,
            "status": "RECOVERY_REQUIRED",
            "reason": f"npm_replacement_restore_failed:{type(exc).__name__}:{exc}",
            "restored": restored,
        }
    return {
        "ok": True,
        "status": "RESTORED" if restored else "NOT_REQUIRED",
        "restored": restored,
    }


def _candidate_npm_residual_targets(prefix: Path) -> list[str]:
    return [
        str(target)
        for target in _candidate_npm_owned_targets(prefix)
        if target.exists() or target.is_symlink()
    ]


def _candidate_npm_parent_check(prefix: Path) -> None:
    modules = prefix / "node_modules"
    for parent in (modules, modules / "@rowlandl", modules / ".bin"):
        if parent.exists() or _is_link_or_reparse(parent):
            _physical_directory(parent, label="candidate_npm_parent")


def _candidate_npm_bin_link(target: Path, package: Path) -> bool:
    if target != package.parents[1] / ".bin" / "decretum-matrix" or not target.is_symlink():
        return False
    if Path(os.readlink(target)).is_absolute():
        return False
    try:
        relative = target.resolve(strict=True).relative_to(package)
        return _safe_candidate_file(package, relative.as_posix(), label="candidate_npm_bin").is_file()
    except (OSError, RuntimeError, ValueError):
        return False


def _subprocess_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value if isinstance(value, str) else ""


def _install_candidate_npm(
    *,
    candidate_tgz: Path,
    npm_prefix: Path,
    home: Path,
    caller_cwd: Path,
    replace_existing: bool = False,
) -> dict[str, object]:
    tgz = _candidate_tgz_regular(candidate_tgz)
    prefix = Path(npm_prefix).resolve(strict=False)
    if prefix.exists() and _is_link_or_reparse(prefix):
        return {"ok": False, "status": "BLOCKED", "reason": "npm_prefix_unsafe"}
    prefix.mkdir(parents=True, exist_ok=True)
    try:
        prefix = _physical_directory(prefix, label="installation_binding_npm_prefix")
        caller = _physical_directory(caller_cwd, label="candidate_npm_caller_cwd")
        _candidate_npm_parent_check(prefix)
    except RuntimeError as exc:
        return {"ok": False, "status": "BLOCKED", "reason": str(exc)}
    package_root = prefix / "node_modules" / "@rowlandl" / "decretum-matrix"
    replacement_backup: dict[str, object] | None = None
    if replace_existing:
        try:
            replacement_backup = _prepare_candidate_npm_replacement(prefix, home)
        except RuntimeError as exc:
            return {
                "ok": False,
                "status": "BLOCKED",
                "reason": str(exc),
                "mutation_attempted": True,
            }
    if package_root.exists() or package_root.is_symlink():
        return {"ok": False, "status": "BLOCKED", "reason": "candidate_package_preexisting"}
    preexisting_shims = [
        str(target)
        for target in _candidate_npm_owned_targets(prefix)[1:]
        if target.exists() or target.is_symlink()
    ]
    if preexisting_shims:
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": "candidate_shim_preexisting",
            "preexisting_targets": preexisting_shims,
            **({"replacement_backup": replacement_backup} if replacement_backup else {}),
        }
    stage_prefix = Path(tempfile.mkdtemp(prefix="decretum-candidate-npm-"))
    command = [_npm_executable(), "install", "--ignore-scripts", "--package-lock=false",
               "--save=false", "--prefix", str(stage_prefix), str(tgz)]
    environment = _acceptance_environment(home)
    environment["npm_config_prefix"] = str(stage_prefix)
    environment["npm_config_ignore_scripts"] = "true"

    def failed(reason: str, **details: object) -> dict[str, object]:
        return {"ok": False, "status": "BLOCKED", "reason": reason,
                "mutation_attempted": True, "command": command, "cwd": str(caller),
                "residual_targets": _candidate_npm_residual_targets(prefix),
                **({"replacement_backup": replacement_backup} if replacement_backup else {}),
                **details}

    try:
        try:
            completed = subprocess.run(command, cwd=caller, env=environment,
                                       capture_output=True, text=True, encoding="utf-8",
                                       errors="replace", check=False, shell=False, timeout=300)
        except subprocess.TimeoutExpired as exc:
            return failed("npm_candidate_install_timeout",
                          stdout=_subprocess_text(exc.stdout)[-4000:],
                          stderr=_subprocess_text(exc.stderr)[-4000:])
        except (OSError, subprocess.SubprocessError) as exc:
            return failed(f"npm_candidate_install_failed:{type(exc).__name__}")
        if completed.returncode != 0:
            return failed("npm_candidate_install_failed", exit_code=completed.returncode,
                          stdout=completed.stdout[-4000:], stderr=completed.stderr[-4000:])
        staged = _candidate_npm_owned_targets(stage_prefix)
        if not staged[0].is_dir() or _is_link_or_reparse(staged[0]):
            return failed("npm_candidate_package_missing_after_install", exit_code=completed.returncode)
        _physical_directory(staged[0], label="candidate_npm_staged_package")
        for staged_target in staged[1:]:
            if _is_link_or_reparse(staged_target) and not _candidate_npm_bin_link(staged_target, staged[0]):
                raise RuntimeError("candidate_npm_stage_target_unsafe")
        for staged_target, target in zip(staged, _candidate_npm_owned_targets(prefix)):
            if not staged_target.exists() and not staged_target.is_symlink():
                continue
            _candidate_npm_parent_check(prefix)
            if target.exists() or _is_link_or_reparse(target):
                raise RuntimeError("candidate_npm_stage_target_unsafe")
            target.parent.mkdir(parents=True, exist_ok=True)
            _physical_directory(target.parent, label="candidate_npm_parent")
            shutil.move(str(staged_target), str(target))
        if not package_root.is_dir() or _is_link_or_reparse(package_root):
            raise RuntimeError("candidate_npm_target_missing_after_stage")
        return {
            "ok": True, "status": "INSTALLED", "command": command, "cwd": str(caller),
            "exit_code": completed.returncode,
            "package_root": str(package_root.resolve(strict=False)),
            "npm_prefix": str(prefix), "mutation_attempted": True,
            "residual_targets": _candidate_npm_residual_targets(prefix),
            **({"replacement_backup": replacement_backup} if replacement_backup else {}),
        }
    except (OSError, RuntimeError) as exc:
        return failed(f"candidate_npm_stage_failed:{type(exc).__name__}")
    finally:
        shutil.rmtree(stage_prefix, ignore_errors=True)


def _rollback_candidate_npm(
    *,
    npm_prefix: Path,
    home: Path,
    caller_cwd: Path,
    replacement_backup: dict[str, object] | None = None,
) -> dict[str, object]:
    try:
        prefix = _physical_directory(npm_prefix, label="installation_binding_npm_prefix")
        caller = _physical_directory(caller_cwd, label="candidate_npm_caller_cwd")
        _candidate_npm_parent_check(prefix)
    except RuntimeError as exc:
        return {"ok": False, "status": "RECOVERY_REQUIRED", "reason": str(exc)}
    residual_before = _candidate_npm_residual_targets(prefix)
    if not residual_before:
        restore = _restore_candidate_npm_replacement(
            prefix=prefix,
            replacement_backup=replacement_backup,
        )
        current_targets = (
            _candidate_npm_residual_targets(prefix)
            if replacement_backup is not None
            else []
        )
        return {
            "ok": restore.get("ok") is True,
            "status": (
                "ROLLED_BACK"
                if replacement_backup is not None and restore.get("ok") is True
                else "NOT_REQUIRED"
                if restore.get("ok") is True
                else "RECOVERY_REQUIRED"
            ),
            "removed": True,
            "residual_targets": [],
            "current_owned_targets": current_targets,
            "replacement_restore": restore,
        }
    try:
        targets = _candidate_npm_owned_targets(prefix)
        for target in reversed(targets):
            try:
                metadata = target.lstat()
            except FileNotFoundError:
                continue
            if _is_link_or_reparse(target):
                if not _candidate_npm_bin_link(target, targets[0]):
                    raise RuntimeError("candidate_npm_target_unsafe")
                target.unlink()
            elif stat.S_ISDIR(metadata.st_mode):
                shutil.rmtree(target)
            elif stat.S_ISREG(metadata.st_mode):
                target.unlink()
            else:
                raise RuntimeError("candidate_npm_target_not_regular")
    except (OSError, RuntimeError) as exc:
        return {
            "ok": False,
            "status": "RECOVERY_REQUIRED",
            "reason": f"candidate_npm_target_remove_failed:{type(exc).__name__}",
            "cwd": str(caller),
            "residual_targets": _candidate_npm_residual_targets(prefix),
        }
    restore = _restore_candidate_npm_replacement(
        prefix=prefix,
        replacement_backup=replacement_backup,
    )
    if restore.get("ok") is not True:
        return {
            "ok": False,
            "status": "RECOVERY_REQUIRED",
            "reason": str(restore.get("reason") or "npm_replacement_restore_failed"),
            "command": ["owned_remove"],
            "cwd": str(caller),
            "removed": True,
            "residual_targets": _candidate_npm_residual_targets(prefix),
            "replacement_restore": restore,
        }
    residual_after = _candidate_npm_residual_targets(prefix)
    if replacement_backup is not None:
        return {
            "ok": True,
            "status": "ROLLED_BACK",
            "command": ["owned_remove"],
            "cwd": str(caller),
            "removed": True,
            "residual_targets": [],
            "restored_owned_targets": residual_after,
            "replacement_restore": restore,
        }
    removed = not residual_after
    return {
        "ok": removed,
        "status": "ROLLED_BACK" if removed else "RECOVERY_REQUIRED",
        "command": ["owned_remove"],
        "cwd": str(caller),
        "removed": removed,
        "residual_targets": residual_after,
        "replacement_restore": restore,
    }


def _run_post_projection_acceptance(
    *,
    source: Path,
    home: Path,
    binding: dict[str, object],
    candidate: dict[str, object],
    installer_module: object,
) -> dict[str, object]:
    """Run the existing repository-only checker once after all projections."""

    checker = source / POST_PROJECTION_CHECKER_RELATIVE
    try:
        checker_status = checker.lstat()
    except OSError as exc:
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": f"post_projection_checker_missing:{type(exc).__name__}",
        }
    if _is_link_or_reparse(checker) or not stat.S_ISREG(checker_status.st_mode):
        return {"ok": False, "status": "BLOCKED", "reason": "post_projection_checker_unsafe"}
    command = [
        sys.executable,
        "-B",
        str(checker),
        "--json",
        "--source",
        str(source),
        "--projection",
        "shared_agents",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=source,
            env=_acceptance_environment(home),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": f"post_projection_checker_failed:{type(exc).__name__}",
            "command": command,
            "cwd": str(source),
        }
    try:
        producer = json.loads(completed.stdout)
    except (UnicodeError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": f"post_projection_checker_invalid_json:{type(exc).__name__}",
            "command": command,
            "cwd": str(source),
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    if not isinstance(producer, dict):
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": "post_projection_checker_result_not_object",
            "command": command,
            "cwd": str(source),
            "exit_code": completed.returncode,
        }
    if completed.returncode != 0 or producer.get("ok") is not True:
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": "post_projection_checker_not_passed",
            "command": command,
            "cwd": str(source),
            "exit_code": completed.returncode,
            "producer_receipt": producer,
        }
    receipt_root = producer.get("roots")
    selected_roots = binding.get("selected_roots")
    if not isinstance(receipt_root, list) or not isinstance(selected_roots, list):
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": "post_projection_checker_roots_missing",
            "producer_receipt": producer,
        }
    if [_path_key(Path(str(item))) for item in receipt_root] != [
        _path_key(Path(str(item))) for item in selected_roots
    ]:
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": "post_projection_checker_roots_mismatch",
            "producer_receipt": producer,
        }
    transaction_id = str(binding["transaction_id"])
    receipt_path = (
        home
        / ".agents"
        / "install-receipts"
        / NAME
        / f"post-validation-{transaction_id}.json"
    )
    validation = {
        "schema": INSTALLATION_ACCEPTANCE_SCHEMA,
        "producer_receipt": producer,
        "candidate": {
            "source_root": str(source),
            "source_commit": candidate["source_commit"],
            "source_tree": candidate["source_tree"],
            "release_label": candidate["release_label"],
            "artifact_ref": candidate["artifact_ref"],
            "build_id": candidate["build_id"],
            "candidate_receipt_ref": candidate["candidate_receipt_ref"],
        },
        "binding": deepcopy(binding),
        "post_projection_receipt_ref": str(receipt_path),
    }
    try:
        writer = getattr(installer_module, "_write_json_atomic")
        writer(receipt_path, validation)
    except (AttributeError, OSError, ValueError) as exc:
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": f"post_projection_receipt_persist_failed:{type(exc).__name__}",
            "producer_receipt": producer,
        }
    committed = installer_module.commit_installation_binding(
        home_root=home,
        external_validation=validation,
    )
    if not isinstance(committed, dict) or committed.get("ok") is not True:
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": "installation_binding_commit_rejected",
            "producer_receipt": producer,
            "validation_receipt": str(receipt_path),
            "commit_result": committed,
        }
    return {
        "ok": True,
        "status": "COMMITTED",
        "producer_receipt": producer,
        "validation_receipt": str(receipt_path),
        "commit_result": committed,
    }


def _snapshot_codex_roles(home: Path) -> dict[str, tuple[bytes, int]]:
    role_root = home / ".codex" / "agents"
    if not role_root.exists():
        return {}
    if _is_link_or_reparse(role_root) or not role_root.is_dir():
        raise RuntimeError("codex_agent_roles_root_unsafe")
    snapshot: dict[str, tuple[bytes, int]] = {}
    for path in sorted(role_root.glob("*.toml")):
        if _is_link_or_reparse(path) or not path.is_file():
            raise RuntimeError("codex_agent_role_file_unsafe")
        value = path.stat()
        snapshot[path.name] = (path.read_bytes(), value.st_mode)
    return snapshot


def _restore_codex_roles(
    home: Path,
    snapshot: dict[str, tuple[bytes, int]],
) -> dict[str, object]:
    role_root = home / ".codex" / "agents"
    try:
        role_root.mkdir(parents=True, exist_ok=True)
        if _is_link_or_reparse(role_root) or not role_root.is_dir():
            raise RuntimeError("codex_agent_roles_root_unsafe")
        for path in role_root.glob("*.toml"):
            if _is_link_or_reparse(path) or not path.is_file():
                raise RuntimeError("codex_agent_role_file_unsafe")
            if path.name not in snapshot:
                path.unlink()
        for name, (payload, mode) in snapshot.items():
            path = role_root / name
            path.write_bytes(payload)
            path.chmod(mode)
    except (OSError, RuntimeError) as exc:
        return {
            "ok": False,
            "status": "RECOVERY_REQUIRED",
            "reason": f"codex_agent_roles_rollback_failed:{type(exc).__name__}:{exc}",
        }
    return {
        "ok": True,
        "status": "ROLLED_BACK",
        "restored_count": len(snapshot),
    }


def _compensate_projection(
    *,
    installer_module: object,
    home: Path,
    result: dict[str, object],
    role_snapshot: dict[str, tuple[bytes, int]] | None = None,
) -> dict[str, object]:
    backup = result.get("backup")
    if not isinstance(backup, dict) or not backup.get("backup_root"):
        projection = {
            "ok": True,
            "status": "NOT_REQUIRED",
            "reason": "no_projection_backup",
        }
        if role_snapshot is not None:
            roles = _restore_codex_roles(home, role_snapshot)
            projection["roles"] = roles
            projection["ok"] = roles.get("ok") is True
            if projection["ok"] is not True:
                projection["status"] = "RECOVERY_REQUIRED"
        return projection
    try:
        rollback = installer_module.rollback_install_backup(
            home_root=home,
            backup_root=Path(str(backup["backup_root"])),
        )
    except Exception as exc:
        return {
            "ok": False,
            "status": "RECOVERY_REQUIRED",
            "reason": f"projection_rollback_failed:{type(exc).__name__}:{exc}",
        }
    projection = rollback if isinstance(rollback, dict) else {
        "ok": False,
        "status": "RECOVERY_REQUIRED",
        "reason": "projection_rollback_invalid",
    }
    if role_snapshot is not None:
        roles = _restore_codex_roles(home, role_snapshot)
        projection["roles"] = roles
        projection["ok"] = projection.get("ok") is True and roles.get("ok") is True
        if projection["ok"] is not True:
            projection["status"] = "RECOVERY_REQUIRED"
    return projection


def _demote_committed_binding(
    *,
    home: Path,
    installer_module: object,
) -> dict[str, object]:
    path = home / ".agents" / "install-receipts" / NAME / "installation-binding-v2.json"
    try:
        binding = _read_json_object(path, label="installation_binding")
        if binding.get("schema") != "court.installation_binding.v2":
            return {"ok": False, "status": "RECOVERY_REQUIRED", "reason": "binding_schema_invalid"}
        binding["completion"] = "RECOVERY_REQUIRED"
        writer = getattr(installer_module, "_write_json_atomic")
        writer(path, binding)
    except (AttributeError, OSError, RuntimeError, ValueError) as exc:
        return {
            "ok": False,
            "status": "RECOVERY_REQUIRED",
            "reason": f"binding_demote_failed:{type(exc).__name__}:{exc}",
        }
    return {"ok": True, "status": "RECOVERY_REQUIRED", "path": str(path)}


def _run_public_shim_probe(
    *,
    candidate_package_root: Path,
    source: Path,
    home: Path,
    binding: dict[str, object],
    caller_cwd: Path | None,
) -> dict[str, object]:
    if caller_cwd is None:
        return {"ok": False, "status": "BLOCKED", "reason": "caller_cwd_required"}
    try:
        caller = _physical_directory(caller_cwd, label="public_shim_caller_cwd")
        source_physical = _physical_directory(source, label="public_shim_source")
        package_root = _physical_directory(
            candidate_package_root,
            label="public_shim_candidate_package",
        )
    except RuntimeError as exc:
        return {"ok": False, "status": "BLOCKED", "reason": str(exc)}
    try:
        caller.relative_to(source_physical)
    except ValueError:
        pass
    else:
        return {"ok": False, "status": "BLOCKED", "reason": "public_shim_caller_inside_source"}
    try:
        node_modules = package_root.parents[1]
    except IndexError:
        return {"ok": False, "status": "BLOCKED", "reason": "public_shim_layout_invalid"}
    if node_modules.name.casefold() != "node_modules":
        return {"ok": False, "status": "BLOCKED", "reason": "public_shim_layout_invalid"}
    try:
        shim_root = _physical_directory(
            node_modules / ".bin",
            label="public_shim_directory",
        )
        prefix_root = _physical_directory(
            node_modules.parent,
            label="public_shim_prefix",
        )
    except RuntimeError as exc:
        return {"ok": False, "status": "BLOCKED", "reason": str(exc)}
    if os.name == "nt":
        shim_candidates = (
            prefix_root / "decretum-matrix.cmd",
            shim_root / "decretum-matrix.cmd",
        )
        shim = next(
            (candidate for candidate in shim_candidates if candidate.exists()),
            shim_candidates[-1],
        )
        try:
            shim_status = shim.lstat()
        except OSError as exc:
            return {"ok": False, "status": "BLOCKED", "reason": f"public_shim_missing:{type(exc).__name__}"}
        if _is_link_or_reparse(shim) or not stat.S_ISREG(shim_status.st_mode):
            return {"ok": False, "status": "BLOCKED", "reason": "public_shim_unsafe"}
        command = [
            os.environ.get("ComSpec", "cmd.exe"),
            "/d",
            "/s",
            "/c",
            subprocess.list2cmdline([str(shim), "--runtime-identity"]),
        ]
    else:
        shim = shim_root / "decretum-matrix"
        try:
            resolved_shim = shim.resolve(strict=True)
            shim_status = resolved_shim.lstat()
            resolved_shim.relative_to(package_root)
        except (OSError, ValueError) as exc:
            return {"ok": False, "status": "BLOCKED", "reason": f"public_shim_missing:{type(exc).__name__}"}
        if _is_link_or_reparse(resolved_shim) or not stat.S_ISREG(shim_status.st_mode):
            return {"ok": False, "status": "BLOCKED", "reason": "public_shim_unsafe"}
        command = [str(shim), "--runtime-identity"]
    try:
        completed = subprocess.run(
            command,
            cwd=caller,
            env=_acceptance_environment(home),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": f"public_shim_failed:{type(exc).__name__}",
            "command": command,
            "cwd": str(caller),
        }
    try:
        emitted = json.loads(completed.stdout.strip())
    except (UnicodeError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": f"public_shim_invalid_json:{type(exc).__name__}",
            "command": command,
            "cwd": str(caller),
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    if completed.returncode != 0 or not isinstance(emitted, dict):
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": "public_shim_not_passed",
            "command": command,
            "cwd": str(caller),
            "exit_code": completed.returncode,
            "identity": emitted,
        }
    if any(
        emitted.get(field) != binding.get(field)
        for field in (
            "schema",
            "source_commit",
            "release_label",
            "artifact_ref",
            "build_id",
            "installation_id",
            "generation",
            "canonical_root",
            "selected_roots",
            "completion",
            "transaction_id",
            "rollback_ref",
        )
    ):
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": "public_shim_binding_mismatch",
            "command": command,
            "cwd": str(caller),
            "identity": emitted,
        }
    return {
        "ok": True,
        "status": "PASS",
        "command": command,
        "cwd": str(caller),
        "exit_code": completed.returncode,
        "identity": emitted,
    }


def _install_update(
    source_selection: dict[str, object],
    home: Path,
    *,
    write: bool,
    candidate_package_root: Path | None = None,
    candidate_tgz: Path | None = None,
    candidate_receipt: Path | None = None,
    npm_prefix: Path | None = None,
    transaction_id: str | None = None,
    installation_id: str | None = None,
    caller_cwd: Path | None = None,
    replace_existing_npm: bool = False,
) -> dict[str, object]:
    selected = source_selection.get("selected_root")
    if not isinstance(selected, str):
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "reason": "source_unavailable",
        }
    if write and caller_cwd is None:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "reason": "caller_cwd_required",
        }
    npm_install_result: dict[str, object] | None = None
    npm_mutation_attempted = False
    npm_install_failed = False
    if candidate_tgz is not None:
        if not write:
            return {
                "schema": SCHEMA,
                "ok": False,
                "status": "PLANNED",
                "reason": "explicit_apply_required_for_candidate_npm_install",
            }
        if npm_prefix is None:
            return {
                "schema": SCHEMA,
                "ok": False,
                "status": "BLOCKED",
                "reason": "npm_prefix_required_for_candidate_tgz",
            }
        npm_install_result = _install_candidate_npm(
            candidate_tgz=candidate_tgz,
            npm_prefix=npm_prefix,
            home=home,
            caller_cwd=caller_cwd,
            replace_existing=replace_existing_npm,
        )
        npm_mutation_attempted = (
            npm_install_result.get("mutation_attempted") is True
            or npm_install_result.get("ok") is True
        )
        if npm_install_result.get("ok") is not True:
            npm_install_failed = True
        else:
            candidate_package_root = Path(str(npm_install_result["package_root"]))

    def attach_npm_compensation(payload: dict[str, object]) -> dict[str, object]:
        if not npm_mutation_attempted or npm_prefix is None or caller_cwd is None:
            return payload
        rollback = _rollback_candidate_npm(
            npm_prefix=npm_prefix,
            home=home,
            caller_cwd=caller_cwd,
            replacement_backup=(
                npm_install_result.get("replacement_backup")
                if isinstance(npm_install_result, dict)
                and isinstance(npm_install_result.get("replacement_backup"), dict)
                else None
            ),
        )
        payload["npm_candidate_install"] = npm_install_result
        payload["npm_candidate_compensation"] = rollback
        if rollback.get("ok") is not True:
            payload["status"] = "RECOVERY_REQUIRED"
            payload["recovery_required"] = True
        elif (
            payload.get("status") == "BLOCKED"
            and (
                str(payload.get("reason") or "").startswith("npm_candidate_install_")
                or payload.get("reason") == "npm_candidate_package_missing_after_install"
            )
        ):
            payload["status"] = "ROLLED_BACK"
            payload["recovery_required"] = False
        return payload
    if npm_install_failed:
        assert npm_install_result is not None
        return attach_npm_compensation({"schema": SCHEMA, **npm_install_result})
    try:
        binding_metadata = _installation_binding_metadata(
            Path(selected),
            candidate_package_root=candidate_package_root,
            candidate_receipt=candidate_receipt,
            npm_prefix=npm_prefix,
            transaction_id=transaction_id,
            installation_id=installation_id,
        )
    except RuntimeError as exc:
        return attach_npm_compensation({
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "reason": str(exc),
        })
    module = importlib.import_module("install_current_agent_copy")
    result = module.install_current_agent_copy(
        source_root=Path(selected),
        home_root=home,
        current_tool="codex",
        explicit_tools=[],
        tool_roots={"codex": home / ".codex" / "skills" / NAME},
        projection_manifest=Path(selected) / PROJECTION_PATH,
        write=write,
        fanout=False,
        installation_binding=binding_metadata,
    )
    if not isinstance(result, dict) or result.get("ok") is not True:
        return attach_npm_compensation(
            result if isinstance(result, dict) else {"ok": False, "status": "INVALID"}
        )
    try:
        role_snapshot = _snapshot_codex_roles(home) if write else None
    except RuntimeError as exc:
        compensation = _compensate_projection(
            installer_module=module,
            home=home,
            result=result,
        ) if write else {"ok": True, "status": "NOT_APPLIED"}
        return attach_npm_compensation({
            **result,
            "ok": False,
            "status": "ROLLED_BACK" if compensation.get("ok") is True else "RECOVERY_REQUIRED",
            "reason": "codex_agent_roles_snapshot_failed",
            "compensation": compensation,
            "recovery_required": compensation.get("ok") is not True,
        })
    try:
        role_result = _sync_codex_agent_roles(home, write=write)
    except Exception as exc:
        role_result = {
            "ok": False,
            "status": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
        }
    result = {**result, "codex_agent_roles": role_result}
    if role_result.get("ok") is not True:
        compensation = _compensate_projection(
            installer_module=module,
            home=home,
            result=result,
            role_snapshot=role_snapshot,
        ) if write else {"ok": True, "status": "NOT_APPLIED"}
        result.update(
            {
                "ok": False,
                "status": "ROLLED_BACK" if compensation.get("ok") is True else "RECOVERY_REQUIRED",
                "reason": "codex_agent_roles_sync_failed",
                "compensation": compensation,
                "recovery_required": compensation.get("ok") is not True,
            }
        )
        return attach_npm_compensation(result)
    if write:
        binding = result.get("installation_binding")
        if not isinstance(binding, dict):
            return attach_npm_compensation({
                **result,
                "ok": False,
                "status": "RECOVERY_REQUIRED",
                "reason": "installation_binding_missing_after_projection",
                "compensation": _compensate_projection(
                    installer_module=module,
                    home=home,
                    result=result,
                    role_snapshot=role_snapshot,
                ),
            })
        acceptance = _run_post_projection_acceptance(
            source=Path(selected),
            home=home,
            binding=binding,
            candidate=binding_metadata,
            installer_module=module,
        )
        result["post_projection_acceptance"] = acceptance
        result["candidate_package_root"] = binding_metadata.get("candidate_package_root")
        if acceptance.get("ok") is not True:
            compensation = _compensate_projection(
                installer_module=module,
                home=home,
                result=result,
                role_snapshot=role_snapshot,
            )
            result.update(
                {
                    "ok": False,
                    "status": "ROLLED_BACK" if compensation.get("ok") is True else "RECOVERY_REQUIRED",
                    "reason": "post_projection_acceptance_failed",
                    "compensation": compensation,
                    "recovery_required": compensation.get("ok") is not True,
                }
            )
            return attach_npm_compensation(result)
        committed_binding = (
            acceptance.get("commit_result", {}).get("installation_binding")
            if isinstance(acceptance.get("commit_result"), dict)
            else None
        )
        if not isinstance(committed_binding, dict):
            committed_binding = dict(binding)
            committed_binding["completion"] = "COMMITTED"
        result["installation_binding"] = committed_binding
        result["status"] = "COMMITTED"
        result["reason"] = "projection_applied_and_post_projection_accepted"
        shim_probe = _run_public_shim_probe(
            candidate_package_root=Path(str(binding_metadata["candidate_package_root"])),
            source=Path(selected),
            home=home,
            binding=committed_binding,
            caller_cwd=caller_cwd,
        )
        result["public_shim"] = shim_probe
        if shim_probe.get("ok") is not True:
            demoted = _demote_committed_binding(
                home=home,
                installer_module=module,
            )
            compensation = _compensate_projection(
                installer_module=module,
                home=home,
                result=result,
                role_snapshot=role_snapshot,
            )
            compensation["binding"] = demoted
            compensation_ok = (
                compensation.get("ok") is True and demoted.get("ok") is True
            )
            result.update(
                {
                    "ok": False,
                    "status": "ROLLED_BACK" if compensation_ok else "RECOVERY_REQUIRED",
                    "reason": "public_shim_probe_failed",
                    "compensation": compensation,
                    "recovery_required": not compensation_ok,
                }
            )
            return attach_npm_compensation(result)
    if npm_install_result is not None:
        result["npm_candidate_install"] = npm_install_result
    return result


def _legacy_migration(home: Path, roots: list[str], receipt: str | None, *, write: bool) -> dict[str, object]:
    if receipt:
        return {
            "schema": "court.legacy_skill_locator_migration.v1",
            "ok": False,
            "status": "BLOCKED",
            "write": write,
            "reason": "migration_receipt_requires_explicit_legacy_rollback_entrypoint",
        }
    module = importlib.import_module("migrate_legacy_skill_locator")
    selected = [
        resolve_user_path(value, default=home)
        for value in roots
    ] if roots else [
        home / ".agents" / "skills" / NAME,
        home / ".codex" / "skills" / NAME,
    ]
    return module.apply_migration(selected, write=write)


def _projection_rollback(home: Path, backup_root: str | None) -> dict[str, object]:
    if not backup_root:
        return {"ok": False, "status": "BLOCKED", "reason": "backup_root_required"}
    resolved = resolve_user_path(backup_root, default=home)
    if not resolved.is_dir():
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": "backup_root_missing",
            "backup_root": str(resolved),
        }
    module = importlib.import_module("install_current_agent_copy")
    return module.rollback_install_backup(
        home_root=home,
        backup_root=resolved,
    )


def _commit_installation_binding(
    home: Path,
    validation_receipt: str | None,
    *,
    source_root: Path | None = None,
    candidate_package_root: Path | None = None,
    candidate_receipt: Path | None = None,
    npm_prefix: Path | None = None,
) -> dict[str, object]:
    if not validation_receipt:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "reason": "validation_receipt_required",
        }
    resolved = resolve_user_path(validation_receipt, default=home)
    try:
        validation = _read_json_object(resolved, label="validation_receipt")
    except RuntimeError as exc:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "reason": f"validation_receipt_invalid:{exc}",
        }
    if validation.get("schema") != INSTALLATION_ACCEPTANCE_SCHEMA:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "reason": "validation_receipt_producer_schema_required",
        }
    binding = validation.get("binding")
    if not isinstance(binding, dict):
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "reason": "validation_receipt_binding_context_required",
        }
    if source_root is None or candidate_package_root is None:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "reason": "candidate_context_required_for_commit",
        }
    try:
        candidate = _installation_binding_metadata(
            source_root,
            candidate_package_root=candidate_package_root,
            candidate_receipt=candidate_receipt,
            npm_prefix=npm_prefix,
            transaction_id=str(binding.get("transaction_id") or ""),
            installation_id=str(binding.get("installation_id") or ""),
        )
    except RuntimeError as exc:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "reason": str(exc),
        }
    if any(
        candidate.get(field) != binding.get(field)
        for field in (
            "source_commit",
            "release_label",
            "artifact_ref",
            "build_id",
            "installation_id",
            "transaction_id",
            "provenance_receipt_ref",
        )
    ):
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "reason": "candidate_binding_context_mismatch",
        }
    module = importlib.import_module("install_current_agent_copy")
    result = module.commit_installation_binding(
        home_root=home,
        external_validation=validation,
    )
    return result if isinstance(result, dict) else {"ok": False, "status": "INVALID"}


def _legacy_rollback(home: Path, receipt: str, *, write: bool) -> dict[str, object]:
    module = importlib.import_module("migrate_legacy_skill_locator")
    resolved = resolve_user_path(receipt, default=home)
    return module.rollback_receipt(resolved, write=write)


def run(argv: list[str] | None = None) -> dict[str, object]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation",
        choices=("update", "migrate", "rollback", "commit-binding"),
    )
    parser.add_argument("--apply", action="store_true", help="Apply the requested repair. Default is a read-only plan.")
    parser.add_argument("--source-root")
    parser.add_argument("--mapped-root")
    parser.add_argument("--home-root")
    parser.add_argument("--root", action="append", default=[])
    parser.add_argument("--receipt")
    parser.add_argument("--backup-root")
    parser.add_argument("--validation-receipt")
    parser.add_argument("--candidate-package-root")
    parser.add_argument("--candidate-tgz")
    parser.add_argument("--candidate-receipt")
    parser.add_argument("--npm-prefix")
    parser.add_argument("--transaction-id")
    parser.add_argument("--installation-id")
    parser.add_argument("--caller-cwd")
    parser.add_argument(
        "--replace-existing-npm",
        action="store_true",
        help="Back up and replace an existing npm prefix package/shim set for an explicit upgrade.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="json")
    args = parser.parse_args(argv)
    audit_intent = write_audit_event(
        task="fix-current-thread",
        operation=f"fix_{args.operation}",
        phase="intent",
        status="started",
        payload={
            "operation": args.operation,
            "apply": bool(args.apply),
            "source_root": args.source_root,
            "mapped_root": args.mapped_root,
            "home_root": args.home_root,
            "candidate_package_root": args.candidate_package_root,
            "candidate_tgz": args.candidate_tgz,
            "candidate_receipt": args.candidate_receipt,
            "npm_prefix": args.npm_prefix,
            "transaction_id": args.transaction_id,
            "installation_id": args.installation_id,
            "caller_cwd": args.caller_cwd,
            "replace_existing_npm": args.replace_existing_npm,
        },
    )
    home = _home_root(args.home_root)
    candidate_package_root = (
        resolve_user_path(args.candidate_package_root, default=home)
        if args.candidate_package_root
        else None
    )
    candidate_tgz = (
        resolve_user_path(args.candidate_tgz, default=home)
        if args.candidate_tgz
        else None
    )
    candidate_receipt = (
        resolve_user_path(args.candidate_receipt, default=home)
        if args.candidate_receipt
        else None
    )
    npm_prefix = (
        resolve_user_path(args.npm_prefix, default=home)
        if args.npm_prefix
        else None
    )
    caller_cwd = (
        resolve_user_path(args.caller_cwd, default=home)
        if args.caller_cwd
        else None
    )
    source_selection = (
        {
            "selected_root": None,
            "status": "NOT_REQUIRED",
            "reason": "installation_binding_commit_uses_existing_home_binding",
        }
        if args.operation == "commit-binding"
        else select_source(
            source_root=args.source_root,
            mapped_root=args.mapped_root,
        )
    )
    backup = resolve_user_path(args.backup_root, default=home) if args.backup_root else None
    try:
        if args.operation == "update":
            result = _install_update(
                source_selection,
                home,
                write=args.apply,
                candidate_package_root=candidate_package_root,
                candidate_tgz=candidate_tgz,
                candidate_receipt=candidate_receipt,
                npm_prefix=npm_prefix,
                transaction_id=args.transaction_id,
                installation_id=args.installation_id,
                caller_cwd=caller_cwd,
                replace_existing_npm=args.replace_existing_npm,
            )
        elif args.operation == "migrate":
            result = _legacy_migration(home, args.root, args.receipt, write=args.apply)
        elif args.operation == "commit-binding":
            result = (
                _commit_installation_binding(
                    home,
                    args.validation_receipt,
                    source_root=(
                        Path(args.source_root).resolve(strict=False)
                        if args.source_root
                        else None
                    ),
                    candidate_package_root=candidate_package_root,
                    candidate_receipt=candidate_receipt,
                    npm_prefix=npm_prefix,
                )
                if args.apply
                else {
                    "schema": "court.installation_binding.v2",
                    "ok": False,
                    "status": "PLANNED",
                    "write": False,
                    "reason": "explicit_apply_required",
                }
            )
        elif args.receipt:
            result = _legacy_rollback(home, args.receipt, write=args.apply)
        else:
            result = (
                _projection_rollback(home, args.backup_root)
                if args.apply
                else {
                    "schema": "court.install_projection_rollback.v1",
                    "ok": backup is not None and backup.is_dir(),
                    "status": "ROLLBACK_PLANNED" if backup is not None and backup.is_dir() else "BLOCKED",
                    "write": False,
                    "backup_root": str(backup) if backup is not None else None,
                    "rollback_supported": backup is not None and backup.is_dir(),
                }
            )
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        result = {
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "write": bool(args.apply),
            "reason": f"fix_operation_failed:{type(exc).__name__}",
        }
    payload = {
        "schema": SCHEMA,
        "ok": result.get("ok") is True,
        "status": result.get("status", "INVALID"),
        "operation": args.operation,
        "write": bool(args.apply),
        "source_selection": source_selection,
        "home_root": str(home),
        "result": result,
        "private_body_accessed": False,
        "secret_values_exposed": False,
    }
    payload["audit_intent"] = audit_intent
    payload["audit_result"] = write_audit_event(
        task="fix-current-thread",
        operation=f"fix_{args.operation}",
        phase="result",
        status="succeeded" if payload["ok"] else "failed",
        payload={
            "operation": args.operation,
            "write": bool(args.apply),
            "status": payload["status"],
            "source_selection": source_selection,
            "result_status": result.get("status"),
        },
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    result = run(argv)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
