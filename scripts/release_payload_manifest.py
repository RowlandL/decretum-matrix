"""Generate and strictly validate the current Decretum Matrix payload manifest."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile


sys.dont_write_bytecode = True

import package_skill
from stdio_encoding import configure_stdio


SCHEMA = "court.release_manifest.v2"
NAME = "decretum-matrix"
DISPLAY_NAME = "Decretum Matrix（诏令矩阵）"
PACKAGE_NAME = NAME
LICENSE_ID = "AGPL-3.0-only"
RELEASE_LABEL = "beta1.0.7"
VERSION_CORE = "1.0.7"
ARTIFACT_NAME = f"decretum-matrix-{RELEASE_LABEL}.zip"
SIDECAR_NAME = f"{ARTIFACT_NAME}.sha256"
ATTESTATION_NAME = f"decretum-matrix-{RELEASE_LABEL}.release-attestation.json"
MANIFEST_NAME = "release-manifest.json"
ARCHIVE_ROOT = f"{package_skill.ROOT_NAME}/"
INDEX_FORMAT = "mode SP sha256 SP size SP path LF; UTF-8; sorted by UTF-8 path bytes"
LEGAL_PATHS = {
    "LICENSE",
    "NOTICE",
    "THIRD_PARTY_NOTICES.md",
    "PROVENANCE.md",
    "COMMERCIAL-LICENSE.md",
    "CLA.md",
    "TRADEMARKS.md",
    "AUTHORS.md",
    "SECURITY.md",
    "PRIVACY.md",
    "CONTRIBUTING.md",
    "SBOM.spdx.json",
}
BUILD_CONTRACT = {
    "deterministic_zip": True,
    "zip_compression": "stored",
    "zip_timestamp": "1980-01-01T00:00:00Z",
    "zip_file_mode": "100644",
    "no_clobber": True,
    "atomic_publish": "same_directory_hard_link_no_replace",
}


class ManifestError(ValueError):
    pass


def manifest_error_result(exc: ManifestError) -> dict[str, object]:
    message = str(exc)
    status = (
        "SOURCE_CHECKOUT_REQUIRED"
        if "not a git repository" in message.casefold()
        else "MANIFEST_ERROR"
    )
    return {
        "ok": False,
        "status": status,
        "error": f"{type(exc).__name__}:{message}",
    }


def root_path() -> Path:
    return Path(__file__).resolve().parents[1]


def sorted_paths(values: list[str] | set[str]) -> list[str]:
    return sorted(values, key=lambda item: item.encode("utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def release_identity(version_text: str) -> dict[str, str]:
    value = version_text.strip()
    match = re.fullmatch(
        r"beta(?P<core>\d+\.\d+\.\d+)(?:-hotfix-v(?P<hotfix>[1-9]\d*))?",
        value,
    )
    if not match:
        raise ManifestError(f"invalid VERSION: {value!r}")
    version_core = match.group("core")
    if value != RELEASE_LABEL or version_core != VERSION_CORE:
        raise ManifestError(f"stale VERSION: expected {RELEASE_LABEL}, got {value}")
    return {
        "version_core": version_core,
        "channel": "beta",
        "release_label": value,
        "artifact_name": ARTIFACT_NAME,
        "sidecar_name": SIDECAR_NAME,
        "attestation_name": ATTESTATION_NAME,
        "expected_final_tag": f"refs/tags/{value}",
    }


def tracked_paths(root: Path) -> set[str]:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", "ls-files", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ManifestError(completed.stderr.decode("utf-8", errors="replace").strip() or "git ls-files failed")
    return {
        item.decode("utf-8", errors="strict")
        for item in completed.stdout.split(b"\0")
        if item
    }


def inventory_entry(relative: str, data: bytes, mode: str = "100644") -> dict[str, object]:
    return {
        "path": relative,
        "mode": mode,
        "size": len(data),
        "sha256": sha256_bytes(data),
    }


def payload_index(entries: list[dict[str, object]]) -> bytes:
    return "".join(
        f"{entry['mode']} {entry['sha256']} {entry['size']} {entry['path']}\n"
        for entry in entries
    ).encode("utf-8")


def stage_inventory(root: Path) -> tuple[list[dict[str, object]], set[str]]:
    with tempfile.TemporaryDirectory(prefix="court-release-manifest-") as tmp_text:
        stage = Path(tmp_text) / package_skill.ROOT_NAME
        package_skill.copy_portable_tree(root, stage)
        package_skill.write_core_shiguan_files(stage)
        package_skill.cleanup_stage_transients(stage)
        staged_manifest = stage / MANIFEST_NAME
        staged_manifest.unlink(missing_ok=True)
        entries: list[dict[str, object]] = []
        staged_paths: set[str] = set()
        for path in sorted(
            (item for item in stage.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(stage).as_posix().encode("utf-8"),
        ):
            relative = path.relative_to(stage).as_posix()
            if relative == MANIFEST_NAME:
                raise ManifestError("manifest self-inclusion")
            data = package_skill.read_source_file_stable(path, Path(relative), stage.resolve(strict=True))
            entries.append(inventory_entry(relative, data))
            staged_paths.add(relative)
        return entries, staged_paths


def payload_tree_inventory(root: Path) -> list[dict[str, object]]:
    """Inventory an already-materialized payload without source regeneration or Git."""

    named_root = Path(os.path.abspath(root))
    if package_skill.is_link_or_reparse(named_root):
        raise ManifestError("payload root is a symlink or reparse point")
    source_root = named_root.resolve(strict=True)
    entries: list[dict[str, object]] = []

    def visit(directory: Path, relative_directory: Path) -> None:
        try:
            children = sorted(
                os.scandir(directory),
                key=lambda entry: (entry.name.casefold(), entry.name),
            )
        except OSError as exc:
            raise ManifestError(
                f"cannot scan payload directory:{relative_directory.as_posix()}:{exc}"
            ) from exc
        for child in children:
            path = Path(child.path)
            relative = relative_directory / child.name
            if package_skill.is_link_or_reparse(path):
                raise ManifestError(f"payload symlink or reparse point:{relative.as_posix()}")
            try:
                is_directory = child.is_dir(follow_symlinks=False)
                is_file = child.is_file(follow_symlinks=False)
            except OSError as exc:
                raise ManifestError(
                    f"cannot classify payload entry:{relative.as_posix()}:{exc}"
                ) from exc
            if is_directory:
                visit(path, relative)
                continue
            if not is_file:
                raise ManifestError(f"unsupported payload entry:{relative.as_posix()}")
            relative_text = relative.as_posix()
            if relative_text == MANIFEST_NAME:
                continue
            data = package_skill.read_source_file_stable(
                path,
                relative,
                source_root,
            )
            entries.append(inventory_entry(relative_text, data))

    visit(source_root, Path())
    return sorted(entries, key=lambda entry: str(entry["path"]).encode("utf-8"))


def build_manifest(root: Path) -> dict[str, object]:
    root = root.resolve()
    identity = release_identity((root / "VERSION").read_text(encoding="utf-8"))
    entries, staged_paths = stage_inventory(root)
    tracked = tracked_paths(root)
    tracked_without_manifest = tracked - {MANIFEST_NAME}
    generated = staged_paths - tracked_without_manifest
    repository_only = tracked_without_manifest - staged_paths
    index = payload_index(entries)
    return {
        "schema": SCHEMA,
        "name": NAME,
        "display_name": DISPLAY_NAME,
        "package_name": PACKAGE_NAME,
        **identity,
        "archive_root": ARCHIVE_ROOT,
        "license": {"declared": LICENSE_ID, "file": "LICENSE"},
        "third_party_notices": "THIRD_PARTY_NOTICES.md",
        "provenance": "PROVENANCE.md",
        "commercial_license_notice": "COMMERCIAL-LICENSE.md",
        "contributor_license_agreement": "CLA.md",
        "trademarks": "TRADEMARKS.md",
        "authors": "AUTHORS.md",
        "contributing": "CONTRIBUTING.md",
        "security_policy": "SECURITY.md",
        "privacy_policy": "PRIVACY.md",
        "sbom": "SBOM.spdx.json",
        "build": dict(BUILD_CONTRACT),
        "integrity": {
            "algorithm": "sha256",
            "manifest_path": MANIFEST_NAME,
            "manifest_in_file_inventory": False,
            "source_tracked_file_count": len(tracked_without_manifest),
            "source_packaged_tracked_file_count": len(staged_paths & tracked_without_manifest),
            "generated_portable_seed_count": len(generated),
            "payload_file_count": len(entries),
            "payload_bytes": sum(int(entry["size"]) for entry in entries),
            "payload_index_format": INDEX_FORMAT,
            "payload_index_sha256": sha256_bytes(index),
        },
        "generated_portable_seed_paths": sorted_paths(generated),
        "repository_only_files": sorted_paths(repository_only),
        "files": entries,
    }


def shape_problems(manifest: object) -> list[str]:
    if not isinstance(manifest, dict):
        return ["manifest:not-object"]
    problems: list[str] = []
    expected = {
        "schema": SCHEMA,
        "name": NAME,
        "display_name": DISPLAY_NAME,
        "package_name": PACKAGE_NAME,
        "version_core": VERSION_CORE,
        "channel": "beta",
        "release_label": RELEASE_LABEL,
        "artifact_name": ARTIFACT_NAME,
        "archive_root": ARCHIVE_ROOT,
        "sidecar_name": SIDECAR_NAME,
        "attestation_name": ATTESTATION_NAME,
        "expected_final_tag": f"refs/tags/{RELEASE_LABEL}",
        "third_party_notices": "THIRD_PARTY_NOTICES.md",
        "provenance": "PROVENANCE.md",
        "commercial_license_notice": "COMMERCIAL-LICENSE.md",
        "contributor_license_agreement": "CLA.md",
        "trademarks": "TRADEMARKS.md",
        "authors": "AUTHORS.md",
        "contributing": "CONTRIBUTING.md",
        "security_policy": "SECURITY.md",
        "privacy_policy": "PRIVACY.md",
        "sbom": "SBOM.spdx.json",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            problems.append(f"identity:{key}")
    license_info = manifest.get("license")
    if license_info != {"declared": LICENSE_ID, "file": "LICENSE"}:
        problems.append("identity:license")
    build = manifest.get("build")
    if build != BUILD_CONTRACT:
        problems.append("build:contract")
    files = manifest.get("files")
    if not isinstance(files, list):
        return problems + ["files:not-list"]
    paths: list[str] = []
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            problems.append(f"files:{index}:not-object")
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path or path == MANIFEST_NAME:
            problems.append(f"files:{index}:path")
            continue
        paths.append(path)
        if entry.get("mode") != "100644":
            problems.append(f"files:{path}:mode")
        if not isinstance(entry.get("size"), int) or isinstance(entry.get("size"), bool) or int(entry["size"]) < 0:
            problems.append(f"files:{path}:size")
        if not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256"))):
            problems.append(f"files:{path}:sha256")
    if len(paths) != len(set(paths)):
        problems.append("files:duplicate")
    if paths != sorted_paths(paths):
        problems.append("files:unsorted")
    missing_legal = LEGAL_PATHS - set(paths)
    problems.extend(f"files:missing-legal:{path}" for path in sorted_paths(missing_legal))
    integrity = manifest.get("integrity")
    if not isinstance(integrity, dict):
        problems.append("integrity:not-object")
    else:
        if integrity.get("manifest_in_file_inventory") is not False:
            problems.append("integrity:self-inclusion")
        if integrity.get("payload_file_count") != len(files):
            problems.append("integrity:file-count")
        if integrity.get("payload_bytes") != sum(int(entry.get("size") or 0) for entry in files if isinstance(entry, dict)):
            problems.append("integrity:payload-bytes")
        if integrity.get("payload_index_sha256") != sha256_bytes(payload_index([entry for entry in files if isinstance(entry, dict)])):
            problems.append("integrity:index-sha256")
    return sorted(set(problems))


def compare_manifest(actual: object, expected: dict[str, object]) -> list[str]:
    problems = shape_problems(actual)
    if not isinstance(actual, dict):
        return problems
    for key in expected:
        if key == "files":
            continue
        if actual.get(key) != expected.get(key):
            problems.append(f"stale:{key}")
    actual_files = actual.get("files") if isinstance(actual.get("files"), list) else []
    expected_files = expected["files"]
    actual_map = {str(entry.get("path")): entry for entry in actual_files if isinstance(entry, dict)}
    expected_map = {str(entry.get("path")): entry for entry in expected_files if isinstance(entry, dict)}
    for path in sorted_paths(set(expected_map) - set(actual_map)):
        problems.append(f"missing-payload:{path}")
    for path in sorted_paths(set(actual_map) - set(expected_map)):
        problems.append(f"extra-payload:{path}")
    for path in sorted_paths(set(actual_map) & set(expected_map)):
        if actual_map[path] != expected_map[path]:
            problems.append(f"payload-drift:{path}")
    return sorted(set(problems))


def compare_staged_payload(actual: object, expected_files: list[dict[str, object]]) -> list[str]:
    problems = shape_problems(actual)
    if not isinstance(actual, dict):
        return problems
    actual_files = actual.get("files") if isinstance(actual.get("files"), list) else []
    actual_map = {
        str(entry.get("path")): entry
        for entry in actual_files
        if isinstance(entry, dict)
    }
    expected_map = {str(entry["path"]): entry for entry in expected_files}
    for path in sorted_paths(set(expected_map) - set(actual_map)):
        problems.append(f"missing-payload:{path}")
    for path in sorted_paths(set(actual_map) - set(expected_map)):
        problems.append(f"extra-payload:{path}")
    for path in sorted_paths(set(actual_map) & set(expected_map)):
        if actual_map[path] != expected_map[path]:
            problems.append(f"payload-drift:{path}")
    return sorted(set(problems))


def check_current(root: Path) -> dict[str, object]:
    root = root.resolve()
    path = root / MANIFEST_NAME
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "problems": [f"manifest-read:{type(exc).__name__}"]}
    if os.environ.get("COURT_PACKAGE_STAGE_VALIDATION") == "1":
        expected_files = payload_tree_inventory(root)
        problems = compare_staged_payload(actual, expected_files)
        return {
            "ok": not problems,
            "problems": problems,
            "manifest": actual,
            "validation_mode": "staged_payload_without_git_metadata",
        }
    expected = build_manifest(root)
    problems = compare_manifest(actual, expected)
    return {"ok": not problems, "problems": problems, "manifest": actual, "expected": expected}


def write_manifest(root: Path) -> dict[str, object]:
    root = root.resolve()
    manifest = build_manifest(root)
    target = root / MANIFEST_NAME
    data = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=target.parent, delete=False) as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, target)
    return manifest


def validate_zip_payload(path: Path) -> list[str]:
    problems: list[str] = []
    manifest_member = f"{package_skill.ROOT_NAME}/{MANIFEST_NAME}"
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if archive.comment:
                problems.append("release-manifest:zip-comment")
            for info in infos:
                if info.is_dir():
                    problems.append(f"release-manifest:directory-entry:{info.filename}")
                    continue
                if info.compress_type != zipfile.ZIP_STORED:
                    problems.append(f"release-manifest:compression-not-stored:{info.filename}")
                if info.date_time != package_skill.ZIP_TIMESTAMP:
                    problems.append(f"release-manifest:timestamp-drift:{info.filename}")
                if info.create_system != 3:
                    problems.append(f"release-manifest:create-system-drift:{info.filename}")
                mode = (info.external_attr >> 16) & 0xFFFF
                if mode != 0o100644:
                    problems.append(f"release-manifest:mode-drift:{info.filename}")
                if info.extra:
                    problems.append(f"release-manifest:extra-field:{info.filename}")
                if info.comment:
                    problems.append(f"release-manifest:member-comment:{info.filename}")
            names = [info.filename for info in infos if not info.is_dir()]
            if names != sorted(names, key=lambda item: item.encode("utf-8")):
                problems.append("release-manifest:member-order")
            if names.count(manifest_member) != 1:
                problems.append("release-manifest:missing-or-duplicate")
                return sorted(set(problems))
            try:
                manifest = json.loads(archive.read(manifest_member).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return ["release-manifest:invalid-json"]
            problems.extend(f"release-manifest:{item}" for item in shape_problems(manifest))
            if not isinstance(manifest, dict):
                return sorted(set(problems))
            files = manifest.get("files")
            if not isinstance(files, list):
                return sorted(set(problems))
            expected = {str(entry.get("path")): entry for entry in files if isinstance(entry, dict)}
            actual: dict[str, dict[str, object]] = {}
            for info in infos:
                if info.is_dir() or info.filename == manifest_member:
                    continue
                prefix = ARCHIVE_ROOT
                if not info.filename.startswith(prefix):
                    problems.append(f"release-manifest:unexpected-root:{info.filename}")
                    continue
                relative = info.filename[len(prefix):]
                data = archive.read(info)
                actual[relative] = inventory_entry(relative, data, f"{(info.external_attr >> 16) & 0xFFFF:06o}")
            for relative in sorted_paths(set(expected) - set(actual)):
                problems.append(f"release-manifest:missing-payload:{relative}")
            for relative in sorted_paths(set(actual) - set(expected)):
                problems.append(f"release-manifest:extra-payload:{relative}")
            for relative in sorted_paths(set(actual) & set(expected)):
                if actual[relative] != expected[relative]:
                    problems.append(f"release-manifest:payload-drift:{relative}")
    except (OSError, zipfile.BadZipFile) as exc:
        problems.append(f"release-manifest:zip-read:{type(exc).__name__}")
    return sorted(set(problems))


def self_tests() -> dict[str, bool]:
    entries = [
        inventory_entry(path, path.encode("utf-8"))
        for path in sorted_paths(LEGAL_PATHS | {"SKILL.md"})
    ]
    index = payload_index(entries)
    base: dict[str, object] = {
        "schema": SCHEMA,
        "name": NAME,
        "display_name": DISPLAY_NAME,
        "package_name": PACKAGE_NAME,
        **release_identity(RELEASE_LABEL),
        "archive_root": ARCHIVE_ROOT,
        "license": {"declared": LICENSE_ID, "file": "LICENSE"},
        "third_party_notices": "THIRD_PARTY_NOTICES.md",
        "provenance": "PROVENANCE.md",
        "commercial_license_notice": "COMMERCIAL-LICENSE.md",
        "contributor_license_agreement": "CLA.md",
        "trademarks": "TRADEMARKS.md",
        "authors": "AUTHORS.md",
        "contributing": "CONTRIBUTING.md",
        "security_policy": "SECURITY.md",
        "privacy_policy": "PRIVACY.md",
        "sbom": "SBOM.spdx.json",
        "build": dict(BUILD_CONTRACT),
        "integrity": {
            "manifest_in_file_inventory": False,
            "payload_file_count": len(entries),
            "payload_bytes": sum(int(entry["size"]) for entry in entries),
            "payload_index_sha256": sha256_bytes(index),
        },
        "files": entries,
    }
    tests: dict[str, bool] = {
        "valid_shape_passes": shape_problems(base) == [],
        "canonical_product_identity_required": (
            NAME == "decretum-matrix"
            and globals().get("DISPLAY_NAME") == "Decretum Matrix（诏令矩阵）"
        ),
        "current_artifact_identity_required": (
            RELEASE_LABEL == "beta1.0.7"
            and VERSION_CORE == "1.0.7"
            and ARTIFACT_NAME == "decretum-matrix-beta1.0.7.zip"
        ),
        "agpl_only_license_required": base.get("license")
        == {"declared": "AGPL-3.0-only", "file": "LICENSE"},
        "complete_legal_surface_required": {
            "LICENSE",
            "NOTICE",
            "THIRD_PARTY_NOTICES.md",
            "PROVENANCE.md",
            "COMMERCIAL-LICENSE.md",
            "CLA.md",
            "TRADEMARKS.md",
            "AUTHORS.md",
            "CONTRIBUTING.md",
            "SBOM.spdx.json",
        }.issubset(LEGAL_PATHS),
        "canonical_archive_locator_required": ARCHIVE_ROOT == "decretum-matrix/",
        "non_git_install_is_typed_source_checkout_boundary": (
            manifest_error_result(ManifestError("fatal: not a git repository"))["status"]
            == "SOURCE_CHECKOUT_REQUIRED"
        ),
    }
    with tempfile.TemporaryDirectory(prefix="court-staged-payload-self-test-") as tmp_text:
        staged_root = Path(tmp_text)
        for entry in entries:
            target = staged_root / str(entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(str(entry["path"]).encode("utf-8"))
        (staged_root / MANIFEST_NAME).write_text(
            json.dumps(base, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        previous_stage_validation = os.environ.get("COURT_PACKAGE_STAGE_VALIDATION")
        os.environ["COURT_PACKAGE_STAGE_VALIDATION"] = "1"
        try:
            staged_result = check_current(staged_root)
            (staged_root / "extra.txt").write_text("extra\n", encoding="utf-8")
            staged_extra_result = check_current(staged_root)
        finally:
            if previous_stage_validation is None:
                os.environ.pop("COURT_PACKAGE_STAGE_VALIDATION", None)
            else:
                os.environ["COURT_PACKAGE_STAGE_VALIDATION"] = previous_stage_validation
        tests["staged_payload_without_git_metadata_passes"] = bool(
            staged_result.get("ok")
            and staged_result.get("validation_mode")
            == "staged_payload_without_git_metadata"
        )
        tests["staged_unmanifested_payload_rejected"] = (
            "missing-payload:extra.txt" in staged_extra_result.get("problems", [])
        )
    try:
        release_identity("beta0.5.9")
    except ManifestError:
        tests["stale_VERSION_rejected"] = True
    else:
        tests["stale_VERSION_rejected"] = False
    for name, mutate in {
        "wrong_release_label_rejected": lambda value: value.__setitem__("release_label", "beta0.5.9"),
        "wrong_display_name_rejected": lambda value: value.__setitem__("display_name", "wrong"),
        "wrong_package_name_rejected": lambda value: value.__setitem__("package_name", "wrong"),
        "wrong_license_rejected": lambda value: value.__setitem__(
            "license", {"declared": "Apache-2.0", "file": "LICENSE"}
        ),
        "wrong_artifact_name_rejected": lambda value: value.__setitem__("artifact_name", "wrong.zip"),
        "manifest_self_inclusion_rejected": lambda value: value["files"].append(inventory_entry(MANIFEST_NAME, b"self")),
        "unsorted_payload_rejected": lambda value: value.__setitem__("files", list(reversed(value["files"]))),
        "wrong_size_or_sha_rejected": lambda value: value["files"][0].__setitem__("sha256", "0" * 64),
        "missing_legal_rejected": lambda value: value.__setitem__("files", [entry for entry in value["files"] if entry["path"] != "LICENSE"]),
    }.items():
        candidate = deepcopy(base)
        mutate(candidate)
        tests[name] = bool(shape_problems(candidate))
    expected = deepcopy(base)
    actual_missing = deepcopy(base)
    actual_missing["files"] = actual_missing["files"][1:]
    tests["missing_tracked_payload_rejected"] = bool(compare_manifest(actual_missing, expected))
    actual_extra = deepcopy(base)
    actual_extra["files"].append(inventory_entry("extra.txt", b"extra"))
    tests["extra_payload_rejected"] = bool(compare_manifest(actual_extra, expected))
    with tempfile.TemporaryDirectory(prefix="court-release-manifest-self-test-") as tmp_text:
        archive_path = Path(tmp_text) / "malformed.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(f"{ARCHIVE_ROOT}{MANIFEST_NAME}", b'{"schema":"court.release.v1"}\n')
        malformed_problems = validate_zip_payload(archive_path)
    tests["malformed_zip_manifest_rejected_without_exception"] = bool(malformed_problems)
    payloads = {str(entry["path"]): str(entry["path"]).encode("utf-8") for entry in entries}

    def write_fixture_zip(
        archive_path: Path,
        *,
        altered_compression: bool = False,
        altered_timestamp: bool = False,
        reverse_order: bool = False,
    ) -> None:
        members = {
            **payloads,
            MANIFEST_NAME: (json.dumps(base, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
        }
        names = sorted_paths(set(members))
        if reverse_order:
            names.reverse()
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
            for index, relative in enumerate(names):
                info = package_skill.deterministic_zip_info(f"{ARCHIVE_ROOT}{relative}")
                compression = zipfile.ZIP_STORED
                if index == 0 and altered_compression:
                    compression = zipfile.ZIP_DEFLATED
                if index == 0 and altered_timestamp:
                    info.date_time = (2026, 7, 12, 0, 0, 0)
                archive.writestr(info, members[relative], compress_type=compression)

    with tempfile.TemporaryDirectory(prefix="court-release-metadata-self-test-") as tmp_text:
        tmp = Path(tmp_text)
        valid_zip = tmp / "valid.zip"
        compressed_zip = tmp / "compressed.zip"
        timestamp_zip = tmp / "timestamp.zip"
        reordered_zip = tmp / "reordered.zip"
        write_fixture_zip(valid_zip)
        write_fixture_zip(compressed_zip, altered_compression=True)
        write_fixture_zip(timestamp_zip, altered_timestamp=True)
        write_fixture_zip(reordered_zip, reverse_order=True)
        tests["valid_zip_metadata_passes"] = validate_zip_payload(valid_zip) == []
        tests["wrong_zip_compression_rejected"] = any(
            "compression-not-stored" in item for item in validate_zip_payload(compressed_zip)
        )
        tests["wrong_zip_timestamp_rejected"] = any(
            "timestamp-drift" in item for item in validate_zip_payload(timestamp_zip)
        )
        tests["wrong_zip_member_order_rejected"] = any(
            "member-order" in item for item in validate_zip_payload(reordered_zip)
        )
    return tests


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root_path())
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result: dict[str, object] = {}
    try:
        if args.self_test:
            tests = self_tests()
            result["self_test"] = tests
            result["self_test_ok"] = all(tests.values())
        if args.write:
            result["written"] = write_manifest(args.root)
        if args.check or not (args.write or args.self_test):
            result["check"] = check_current(args.root)
        result["ok"] = all(
            bool(value)
            for value in (
                result.get("self_test_ok", True),
                result.get("check", {}).get("ok", True)
                if isinstance(result.get("check"), dict)
                else True,
            )
        )
    except ManifestError as exc:
        result = manifest_error_result(exc)
    except (package_skill.PackagePolicyError, OSError, subprocess.SubprocessError) as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"RELEASE_PAYLOAD_MANIFEST {'PASSED' if result['ok'] else 'FAILED'}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
