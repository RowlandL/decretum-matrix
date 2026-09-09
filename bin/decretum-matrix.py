#!/usr/bin/env python3
"""Public launcher for an already committed Decretum Matrix installation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import stat
import sys
from urllib.parse import quote


sys.dont_write_bytecode = True


INSTALLATION_BINDING_SCHEMA = "court.installation_binding.v2"
INSTALLATION_BINDING_RELATIVE = Path(
    ".agents/install-receipts/decretum-matrix/installation-binding-v2.json"
)
INSTALLATION_BINDING_FIELDS = (
    "source_commit",
    "release_label",
    "artifact_ref",
    "build_id",
    "installation_id",
    "generation",
    "canonical_root",
    "selected_roots",
    "completion",
    "provenance_receipt_ref",
    "transaction_id",
    "rollback_ref",
)
CANONICAL_INSTALL_RELATIVE = Path(
    ".agents/skills/decretum-matrix"
)
MAX_METADATA_BYTES = 256 * 1024


class LauncherError(RuntimeError):
    """The public launcher cannot prove a committed installation binding."""


def _configure_standard_streams(streams: tuple[object, ...] | None = None) -> None:
    for stream in streams or (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


_configure_standard_streams()


def _runtime_home() -> Path:
    value = (
        os.environ.get("USERPROFILE")
        if os.name == "nt"
        else os.environ.get("HOME")
    )
    return Path(value or Path.home()).expanduser().resolve(strict=False)


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path))))


def _same_path(left: Path, right: Path) -> bool:
    return _path_key(left) == _path_key(right)


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([_path_key(path), _path_key(root)]) == _path_key(root)
    except ValueError:
        return False


def _path_is_link_or_reparse(path: Path) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(value.st_mode) or bool(
        reparse_flag and getattr(value, "st_file_attributes", 0) & reparse_flag
    )


def _physical_directory(path: Path) -> bool:
    raw = Path(os.path.abspath(os.fspath(path)))
    if _path_is_link_or_reparse(raw):
        return False
    path = Path(os.path.realpath(os.fspath(raw)))
    try:
        value = path.lstat()
    except OSError:
        return False
    if any(
        _path_is_link_or_reparse(parent)
        for parent in (path, *path.parents)
    ):
        return False
    return (
        stat.S_ISDIR(value.st_mode)
        and not _path_is_link_or_reparse(path)
    )


def _safe_binding_path(home: Path) -> Path:
    binding_path = home / INSTALLATION_BINDING_RELATIVE
    current = home
    for part in INSTALLATION_BINDING_RELATIVE.parts[:-1]:
        current = current / part
        if current.exists() and _path_is_link_or_reparse(current):
            raise LauncherError("installation binding path is a link or reparse point")
    if binding_path.exists() and _path_is_link_or_reparse(binding_path):
        raise LauncherError("installation binding is a link or reparse point")
    return binding_path


def _read_json_object(path: Path) -> dict[str, object] | None:
    try:
        value_info = path.lstat()
        if (
            not stat.S_ISREG(value_info.st_mode)
            or _path_is_link_or_reparse(path)
            or value_info.st_size > MAX_METADATA_BYTES
        ):
            return None
        payload = path.read_text(encoding="utf-8")
        if len(payload.encode("utf-8")) > MAX_METADATA_BYTES:
            return None
        value = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _package_binding_metadata(package_root: Path) -> dict[str, str] | None:
    """Read package lineage metadata only; never inspect runtime file contents."""

    package = _read_json_object(package_root / "package.json")
    metadata = package.get("decretumMatrix") if isinstance(package, dict) else None
    if not isinstance(metadata, dict):
        return None
    source = metadata.get("source")
    if not isinstance(source, dict):
        return None
    binding = metadata.get("installationBinding")
    binding = binding if isinstance(binding, dict) else metadata.get("installation_binding")
    binding = binding if isinstance(binding, dict) else {}
    values: dict[str, str] = {}
    candidates = {
        "source_commit": source.get("commit") or binding.get("source_commit"),
        "release_label": metadata.get("releaseLabel") or binding.get("release_label"),
        "artifact_ref": metadata.get("artifactRef")
        or metadata.get("artifact_ref")
        or binding.get("artifact_ref"),
        "build_id": metadata.get("buildId")
        or metadata.get("build_id")
        or binding.get("build_id"),
    }
    for field, value in candidates.items():
        if isinstance(value, str) and value.strip():
            values[field] = value.strip()
    if any(field not in values for field in ("source_commit", "release_label", "artifact_ref", "build_id")):
        return None
    return values


def cache_generation_key(binding: object) -> str | None:
    """Return a stable, path-safe cache identity from trusted binding metadata."""

    if not isinstance(binding, dict):
        return None
    artifact_ref = binding.get("artifact_ref")
    build_id = binding.get("build_id")
    installation_id = binding.get("installation_id")
    generation = binding.get("generation")
    if any(
        not isinstance(value, str) or not value.strip()
        for value in (artifact_ref, build_id, installation_id)
    ):
        return None
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        return None
    components = (
        quote(artifact_ref.strip(), safe="._-"),
        quote(build_id.strip(), safe="._-"),
        quote(installation_id.strip(), safe="._-"),
        f"g{generation}",
    )
    return "--".join(components)


def _validate_installation_binding(
    package_root: Path,
    home: Path,
    binding: object,
) -> tuple[Path, dict[str, object]] | None:
    if not isinstance(binding, dict):
        return None
    if binding.get("schema") != INSTALLATION_BINDING_SCHEMA:
        return None
    forbidden_fields = {
        "content_digest",
        "runtime_content_digest",
        "source_package_sha256",
        "court_code",
        "case_ref",
        "record_ref",
    }
    if any(
        key in forbidden_fields or str(key).casefold().endswith("sha256")
        for key in binding
    ):
        return None
    if any(
        field not in binding
        for field in INSTALLATION_BINDING_FIELDS
    ):
        return None
    for field in INSTALLATION_BINDING_FIELDS:
        if field in {"generation", "selected_roots"}:
            continue
        value = binding.get(field)
        if not isinstance(value, str) or not value.strip():
            return None
    generation = binding.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        return None
    if binding.get("completion") != "COMMITTED":
        return None
    selected = binding.get("selected_roots")
    if not isinstance(selected, list) or not selected:
        return None
    if any(not isinstance(value, str) or not value.strip() for value in selected):
        return None

    canonical_path = home / CANONICAL_INSTALL_RELATIVE
    if not _physical_directory(canonical_path):
        return None
    canonical = canonical_path.resolve(strict=False)
    bound_canonical = Path(str(binding["canonical_root"])).resolve(strict=False)
    if not _same_path(bound_canonical, canonical):
        return None
    selected_roots: list[Path] = []
    for value in selected:
        raw_candidate = Path(value).expanduser()
        if not _physical_directory(raw_candidate):
            return None
        candidate = raw_candidate.resolve(strict=False)
        if any(_same_path(candidate, existing) for existing in selected_roots):
            return None
        if not _path_is_under(candidate, home):
            return None
        selected_roots.append(candidate)
    if not any(_same_path(candidate, canonical) for candidate in selected_roots):
        return None

    package_metadata = _package_binding_metadata(package_root)
    if package_metadata is None:
        return None
    for field, expected in package_metadata.items():
        if binding.get(field) != expected:
            return None
    normalized = dict(binding)
    normalized["canonical_root"] = str(canonical)
    normalized["selected_roots"] = [str(candidate) for candidate in selected_roots]
    return canonical, normalized


def _read_installation_binding(
    package_root: Path,
    *,
    home: Path | None = None,
) -> tuple[Path, dict[str, object]] | None:
    selected_home = (home or _runtime_home()).resolve(strict=False)
    try:
        binding_path = _safe_binding_path(selected_home)
    except LauncherError:
        return None
    binding = _read_json_object(binding_path)
    return _validate_installation_binding(package_root, selected_home, binding)


def _canonical_runtime_selection(
    package_root: Path,
    home: Path | None = None,
    *,
    expected_binding: dict[str, object] | None = None,
) -> tuple[Path, dict[str, object]] | None:
    selected_home = (home or _runtime_home()).resolve(strict=False)
    binding = expected_binding
    if binding is None:
        try:
            binding_path = _safe_binding_path(selected_home)
        except LauncherError:
            return None
        binding = _read_json_object(binding_path)
    return _validate_installation_binding(package_root, selected_home, binding)


def _canonical_runtime_root(
    package_root: Path,
    home: Path | None = None,
    *,
    expected_binding: dict[str, object] | None = None,
) -> Path | None:
    selection = _canonical_runtime_selection(
        package_root,
        home=home,
        expected_binding=expected_binding,
    )
    return selection[0] if selection is not None else None


def _select_runtime(
    package_root: Path,
    *,
    home: Path | None = None,
    cache_base: Path | None = None,
) -> tuple[Path, dict[str, object]]:
    del cache_base
    selection = _canonical_runtime_selection(package_root, home=home)
    if selection is None:
        raise LauncherError("installation_binding_missing_or_invalid")
    runtime_root, binding = selection
    cli = runtime_root / "scripts" / "court_cli.py"
    if not _physical_directory(cli.parent) or not cli.is_file() or _path_is_link_or_reparse(cli):
        raise LauncherError("canonical runtime entrypoint missing_or_invalid")
    return runtime_root, binding


def runtime_identity_probe(
    package_root: Path,
    *,
    home: Path | None = None,
    cache_base: Path | None = None,
) -> dict[str, object]:
    _, binding = _select_runtime(package_root, home=home, cache_base=cache_base)
    return binding


def main(argv: list[str] | None = None) -> int:
    package_root = Path(__file__).resolve().parents[1]
    effective_argv = sys.argv[1:] if argv is None else argv
    if effective_argv == ["--npm-postinstall"]:
        raise LauncherError("npm_postinstall_disabled")
    runtime_root, runtime_binding = _select_runtime(package_root)
    if effective_argv == ["--runtime-identity"]:
        print(json.dumps(runtime_binding, ensure_ascii=False, sort_keys=True))
        return 0
    cli = runtime_root / "scripts" / "court_cli.py"
    sys.path.insert(0, str(cli.parent))
    sys.argv = [str(cli), *effective_argv]
    runpy.run_path(str(cli), run_name="__main__")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LauncherError, OSError) as exc:
        print(f"decretum-matrix launcher failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
