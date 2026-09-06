"""Render the source installation contract into an active runtime projection.

The source manifests remain the only authority.  This module is deliberately
pure: callers receive expected target bytes and decide whether and how to
transactionally apply them.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from fnmatch import fnmatchcase
import json
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any


PROJECTION_SCHEMA = "court.install_projection.v1"
ACTIVE_RENDER_SCHEMA = "court.install_projection.active_render.v1"
ACTIVE_RENDER_MATCHER = "posix_glob.v1"
PROJECTION_MANIFEST_RELATIVE = PurePosixPath(
    "references/manifests/install-projection.v1.json"
)
CLI_SURFACE_RELATIVE = PurePosixPath(
    "references/manifests/cli-command-surface.v1.json"
)
PRELOAD_IDENTITY_RELATIVE = PurePosixPath("references/manifests/installed-preload-identity.v1.json")


def render_installed_preload_identity(files: dict[PurePosixPath, bytes]) -> bytes:
    """Pin final projected preload bytes once, as part of installation rendering."""
    body = {
        "schema": "court.installed_preload_identity.v1",
        "authority": "installer",
        "status": "INSTALLATION_PINNED",
        "file_sha256": {
            relative.as_posix(): hashlib.sha256(payload).hexdigest()
            for relative, payload in sorted(files.items(), key=lambda item: item[0].as_posix())
            if relative.as_posix() == "SKILL.md"
            or relative.as_posix().startswith(("agents/standing-officials/", "agents/office-dossiers/", "agents/supercc-dossiers/"))
        },
    }
    body["identity_sha256"] = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return _json_bytes(body)


RUNTIME_PROJECTION_NAMES = (
    "shared_agents",
    "portable_current_tool",
    "cli_public",
)
TARGET_PROJECTION_NAMES = (
    "shared_agents",
    "portable_current_tool",
)
CLI_ACTIVE_METADATA_FIELDS = (
    "schema",
    "schema_version",
    "public_command",
    "source_entry",
)


class ActiveProjectionRenderError(ValueError):
    """The source authority cannot produce a safe active projection."""


@dataclass(frozen=True)
class RenderedActiveProjection:
    target_class: str
    projection_manifest: dict[str, Any]
    cli_surface: dict[str, Any]
    files: dict[PurePosixPath, bytes]
    excluded_path_globs: tuple[str, ...]
    source_projection_sha256: str
    source_cli_surface_sha256: str


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    if len(value) >= 2 and value[1] == ":":
        return False
    relative = PurePosixPath(value)
    return not relative.is_absolute() and not relative.drive and all(
        part not in {"", ".", ".."} for part in relative.parts
    )


def _safe_glob(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    if len(value) >= 2 and value[1] == ":":
        return False
    parts = PurePosixPath(value).parts
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _is_link_or_reparse(value: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(value.st_mode) or bool(
        reparse_flag and getattr(value, "st_file_attributes", 0) & reparse_flag
    )


def _safe_source_path(source_root: Path, relative: PurePosixPath) -> Path:
    root = source_root.resolve(strict=False)
    root_status = _lstat(root)
    if root_status is None or _is_link_or_reparse(root_status) or not root.is_dir():
        raise ActiveProjectionRenderError(f"source_root_unsafe:{root}")
    current = root
    for part in relative.parts:
        current = current / part
        status = _lstat(current)
        if status is None:
            raise ActiveProjectionRenderError(
                f"source_projection_missing:{relative.as_posix()}"
            )
        if _is_link_or_reparse(status):
            raise ActiveProjectionRenderError(
                f"source_projection_link_forbidden:{relative.as_posix()}"
            )
    return current


def _read_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ActiveProjectionRenderError(
            f"{label}_invalid:{type(exc).__name__}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ActiveProjectionRenderError(f"{label}_invalid:root_not_object")
    return value, payload


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2)
        + "\n"
    ).encode("utf-8")


def _projection_lists(source_manifest: dict[str, Any]) -> dict[str, list[str]]:
    if source_manifest.get("schema") != PROJECTION_SCHEMA:
        raise ActiveProjectionRenderError("projection_manifest_schema_mismatch")
    projections = source_manifest.get("projections")
    if not isinstance(projections, dict):
        raise ActiveProjectionRenderError("projection_manifest_projections_missing")
    output: dict[str, list[str]] = {}
    for name in RUNTIME_PROJECTION_NAMES:
        values = projections.get(name)
        if not isinstance(values, list) or any(
            not _safe_relative(value) for value in values
        ):
            raise ActiveProjectionRenderError(
                f"projection_manifest_projection_invalid:{name}"
            )
        output[name] = [str(value) for value in values]
    return output


def _active_policy(source_manifest: dict[str, Any]) -> tuple[list[str], set[str]]:
    policy = source_manifest.get("active_render")
    if not isinstance(policy, dict):
        raise ActiveProjectionRenderError("active_render_policy_missing")
    if policy.get("schema") != ACTIVE_RENDER_SCHEMA:
        raise ActiveProjectionRenderError("active_render_policy_schema_mismatch")
    if policy.get("path_matcher") != ACTIVE_RENDER_MATCHER:
        raise ActiveProjectionRenderError("active_render_policy_matcher_mismatch")
    globs = policy.get("exclude_path_globs")
    groups = policy.get("excluded_cli_groups")
    if (
        not isinstance(globs, list)
        or not globs
        or any(not _safe_glob(value) for value in globs)
        or not isinstance(groups, list)
        or not groups
        or any(not isinstance(value, str) or not value for value in groups)
    ):
        raise ActiveProjectionRenderError("active_render_policy_invalid")
    if len(set(globs)) != len(globs) or len(set(groups)) != len(groups):
        raise ActiveProjectionRenderError("active_render_policy_duplicates")
    return [str(value) for value in globs], set(groups)


def _excluded(relative: str, globs: list[str]) -> bool:
    return any(fnmatchcase(relative, pattern) for pattern in globs)


def active_path_is_excluded(relative: str, globs: tuple[str, ...]) -> bool:
    """Return whether the source authority explicitly classifies a path as source-only."""

    return _excluded(relative, list(globs))


def render_active_projection_manifest(
    source_manifest: dict[str, Any],
) -> tuple[dict[str, Any], list[str], set[str]]:
    """Render an active-only installation manifest from the source authority."""

    projection_lists = _projection_lists(source_manifest)
    globs, excluded_groups = _active_policy(source_manifest)
    projections = {
        name: [
            relative
            for relative in projection_lists[name]
            if not _excluded(relative, globs)
        ]
        for name in RUNTIME_PROJECTION_NAMES
    }
    projections["repository_only"] = []
    for name in TARGET_PROJECTION_NAMES:
        if PRELOAD_IDENTITY_RELATIVE.as_posix() not in projections[name]:
            projections[name].append(PRELOAD_IDENTITY_RELATIVE.as_posix())
    required_fields = (
        "schema",
        "schema_version",
        "identity_manifest",
        "policy",
        "protected_shared_agents_seeds",
        "frozen_install_references",
        "persistent_bindings",
    )
    missing = [field for field in required_fields if field not in source_manifest]
    if missing:
        raise ActiveProjectionRenderError(
            f"projection_manifest_required_fields_missing:{','.join(missing)}"
        )
    active = {
        field: deepcopy(source_manifest[field])
        for field in required_fields
    }
    active["projections"] = projections
    _validate_active_projection_manifest(active, globs)
    return active, globs, excluded_groups


def _validate_active_projection_manifest(
    active_manifest: dict[str, Any],
    globs: list[str],
) -> None:
    if "active_render" in active_manifest:
        raise ActiveProjectionRenderError("active_render_policy_leaked")
    projections = active_manifest.get("projections")
    if not isinstance(projections, dict):
        raise ActiveProjectionRenderError("active_projection_missing")
    if projections.get("repository_only") != []:
        raise ActiveProjectionRenderError("active_repository_only_not_empty")
    for name in RUNTIME_PROJECTION_NAMES:
        values = projections.get(name)
        if not isinstance(values, list) or any(
            not isinstance(value, str) or _excluded(value, globs)
            for value in values
        ):
            raise ActiveProjectionRenderError(
                f"active_projection_exclusion_leak:{name}"
            )


def render_active_cli_surface(
    source_cli_surface: dict[str, Any],
    excluded_groups: set[str],
) -> dict[str, Any]:
    """Preserve operational CLI/MCP entries while removing source-only groups."""

    entries = source_cli_surface.get("entries")
    groups = source_cli_surface.get("groups")
    if not isinstance(entries, list) or not isinstance(groups, list):
        raise ActiveProjectionRenderError("cli_surface_invalid")
    if any(
        not isinstance(entry, dict) or not isinstance(entry.get("group"), str)
        for entry in entries
    ):
        raise ActiveProjectionRenderError("cli_surface_entries_invalid")
    if any(not isinstance(group, str) for group in groups):
        raise ActiveProjectionRenderError("cli_surface_groups_invalid")
    active = {
        key: deepcopy(source_cli_surface[key])
        for key in CLI_ACTIVE_METADATA_FIELDS
        if key in source_cli_surface
    }
    active["entries"] = [
        deepcopy(entry)
        for entry in entries
        if str(entry["group"]) not in excluded_groups
    ]
    active["groups"] = [
        group
        for group in groups
        if group not in excluded_groups
    ]
    if any(
        entry.get("group") in excluded_groups
        for entry in active["entries"]
    ) or any(group in excluded_groups for group in active["groups"]):
        raise ActiveProjectionRenderError("active_cli_source_only_registration_leak")
    return active


def _json_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _json_strings(child)]
    if isinstance(value, dict):
        return [
            item
            for key, child in value.items()
            for item in [*(_json_strings(key)), *(_json_strings(child))]
        ]
    return []


def _source_only_json_paths(
    projection_lists: dict[str, list[str]],
    source_cli_surface: dict[str, Any],
    globs: list[str],
    excluded_groups: set[str],
) -> set[str]:
    paths = {
        relative
        for values in projection_lists.values()
        for relative in values
        if _excluded(relative, globs)
    }
    entries = source_cli_surface.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("group") not in excluded_groups:
                continue
            for key in ("authority_source", "legacy_path", "handler"):
                value = entry.get(key)
                if not isinstance(value, str):
                    continue
                paths.add(value.replace("\\", "/").split(":", 1)[-1])
    return {path for path in paths if path}


def _validate_active_manifest_strings(
    *,
    label: str,
    value: dict[str, Any],
    source_only_paths: set[str],
    excluded_groups: set[str],
    globs: list[str],
) -> None:
    leaks: set[str] = set()
    for text in _json_strings(value):
        normalized = text.replace("\\", "/")
        if text in excluded_groups:
            leaks.add(text)
        if _excluded(normalized, globs):
            leaks.add(normalized)
        for path in source_only_paths:
            if path in normalized:
                leaks.add(path)
    if leaks:
        raise ActiveProjectionRenderError(
            f"{label}_source_only_string_leak:{','.join(sorted(leaks))}"
        )


def _expand_projected_files(
    source_root: Path,
    entries: list[str],
    globs: list[str],
) -> dict[PurePosixPath, bytes]:
    files: dict[PurePosixPath, bytes] = {}
    for value in entries:
        relative = PurePosixPath(value)
        source = _safe_source_path(source_root, relative)
        status = _lstat(source)
        assert status is not None
        if stat.S_ISREG(status.st_mode):
            files[relative] = source.read_bytes()
            continue
        if not stat.S_ISDIR(status.st_mode):
            raise ActiveProjectionRenderError(
                f"source_projection_not_regular:{relative.as_posix()}"
            )
        stack = [source]
        while stack:
            current = stack.pop()
            with os.scandir(current) as children:
                for child in children:
                    child_path = Path(child.path)
                    child_status = child.stat(follow_symlinks=False)
                    if _is_link_or_reparse(child_status):
                        raise ActiveProjectionRenderError(
                            "source_projection_link_forbidden:"
                            + child_path.relative_to(source_root).as_posix()
                        )
                    if stat.S_ISDIR(child_status.st_mode):
                        stack.append(child_path)
                        continue
                    if not stat.S_ISREG(child_status.st_mode):
                        raise ActiveProjectionRenderError(
                            "source_projection_not_regular:"
                            + child_path.relative_to(source_root).as_posix()
                        )
                    child_relative = PurePosixPath(
                        child_path.relative_to(source_root).as_posix()
                    )
                    if (
                        "__pycache__" in child_relative.parts
                        or child_relative.suffix.casefold() == ".pyc"
                    ):
                        continue
                    files[child_relative] = child_path.read_bytes()
    leaked = [
        relative.as_posix()
        for relative in files
        if _excluded(relative.as_posix(), globs)
    ]
    if leaked:
        raise ActiveProjectionRenderError(
            f"active_projection_exclusion_leak:{','.join(sorted(leaked))}"
        )
    return files


def render_active_projection(
    *,
    source_root: Path,
    target_class: str,
) -> RenderedActiveProjection:
    """Return the exact byte map an active root must contain."""

    if target_class not in TARGET_PROJECTION_NAMES:
        raise ActiveProjectionRenderError(f"target_class_invalid:{target_class}")
    root = Path(source_root).resolve(strict=False)
    projection_path = _safe_source_path(root, PROJECTION_MANIFEST_RELATIVE)
    cli_path = _safe_source_path(root, CLI_SURFACE_RELATIVE)
    source_manifest, source_manifest_bytes = _read_json(
        projection_path,
        label="projection_manifest",
    )
    source_cli, source_cli_bytes = _read_json(
        cli_path,
        label="cli_surface",
    )
    active_manifest, globs, excluded_groups = render_active_projection_manifest(
        source_manifest
    )
    active_cli = render_active_cli_surface(source_cli, excluded_groups)
    projection_lists = _projection_lists(source_manifest)
    source_only_paths = _source_only_json_paths(
        projection_lists,
        source_cli,
        globs,
        excluded_groups,
    )
    identity_relative_value = active_manifest.get("identity_manifest")
    if not _safe_relative(identity_relative_value):
        raise ActiveProjectionRenderError("identity_manifest_relative_invalid")
    identity_relative = PurePosixPath(str(identity_relative_value))
    identity_path = _safe_source_path(root, identity_relative)
    active_identity, active_identity_bytes = _read_json(
        identity_path,
        label="identity_manifest",
    )
    _validate_active_manifest_strings(
        label="active_projection_manifest",
        value=active_manifest,
        source_only_paths=source_only_paths,
        excluded_groups=excluded_groups,
        globs=globs,
    )
    _validate_active_manifest_strings(
        label="active_cli_surface",
        value=active_cli,
        source_only_paths=source_only_paths,
        excluded_groups=excluded_groups,
        globs=globs,
    )
    _validate_active_manifest_strings(
        label="active_identity_manifest",
        value=active_identity,
        source_only_paths=source_only_paths,
        excluded_groups=excluded_groups,
        globs=globs,
    )
    projections = active_manifest["projections"]
    assert isinstance(projections, dict)
    entries = [
        *list(projections[target_class]),
        *list(projections["cli_public"]),
    ]
    entries = [entry for entry in entries if entry != PRELOAD_IDENTITY_RELATIVE.as_posix()]
    files = _expand_projected_files(root, entries, globs)
    if (
        PROJECTION_MANIFEST_RELATIVE not in files
        or CLI_SURFACE_RELATIVE not in files
        or identity_relative not in files
    ):
        raise ActiveProjectionRenderError("active_projection_manifests_not_projected")
    files[PROJECTION_MANIFEST_RELATIVE] = _json_bytes(active_manifest)
    files[CLI_SURFACE_RELATIVE] = _json_bytes(active_cli)
    files[identity_relative] = active_identity_bytes
    files[PRELOAD_IDENTITY_RELATIVE] = render_installed_preload_identity(files)

    return RenderedActiveProjection(
        target_class=target_class,
        projection_manifest=active_manifest,
        cli_surface=active_cli,
        files=dict(sorted(files.items(), key=lambda item: item[0].as_posix())),
        excluded_path_globs=tuple(globs),
        source_projection_sha256=hashlib.sha256(source_manifest_bytes).hexdigest(),
        source_cli_surface_sha256=hashlib.sha256(source_cli_bytes).hexdigest(),
    )


__all__ = [
    "ACTIVE_RENDER_SCHEMA",
    "ActiveProjectionRenderError",
    "RenderedActiveProjection",
    "active_path_is_excluded",
    "render_active_cli_surface",
    "render_active_projection",
    "render_active_projection_manifest",
]
