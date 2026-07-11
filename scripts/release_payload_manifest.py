"""Generate and strictly validate the beta0.5.9 staged-package payload manifest."""

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


SCHEMA = "court.release_manifest.v2"
NAME = "court-capability-router"
RELEASE_LABEL = "beta0.5.9"
VERSION_CORE = "0.5.9"
ARTIFACT_NAME = "court-capability-router-beta0.5.9.zip"
SIDECAR_NAME = f"{ARTIFACT_NAME}.sha256"
ATTESTATION_NAME = "court-capability-router-beta0.5.9.release-attestation.json"
MANIFEST_NAME = "release-manifest.json"
ARCHIVE_ROOT = f"{package_skill.ROOT_NAME}/"
INDEX_FORMAT = "mode SP sha256 SP size SP path LF; UTF-8; sorted by UTF-8 path bytes"
LEGAL_PATHS = {
    "LICENSE",
    "NOTICE",
    "THIRD_PARTY_NOTICES.md",
    "SECURITY.md",
    "PRIVACY.md",
    "CONTRIBUTING.md",
    "SBOM.spdx.json",
}


class ManifestError(ValueError):
    pass


def root_path() -> Path:
    return Path(__file__).resolve().parents[1]


def sorted_paths(values: list[str] | set[str]) -> list[str]:
    return sorted(values, key=lambda item: item.encode("utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def release_identity(version_text: str) -> dict[str, str]:
    value = version_text.strip()
    match = re.fullmatch(r"beta(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ManifestError(f"invalid VERSION: {value!r}")
    version_core = ".".join(match.groups())
    if value != RELEASE_LABEL or version_core != VERSION_CORE:
        raise ManifestError(f"stale VERSION: expected {RELEASE_LABEL}, got {value}")
    return {
        "version_core": version_core,
        "channel": "beta",
        "release_label": value,
        "artifact_name": ARTIFACT_NAME,
        "sidecar_name": SIDECAR_NAME,
        "attestation_name": ATTESTATION_NAME,
        "source_ref": f"refs/tags/{value}",
    }


def tracked_paths(root: Path) -> set[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
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
        **identity,
        "archive_root": ARCHIVE_ROOT,
        "license": {"declared": "Apache-2.0", "file": "LICENSE"},
        "third_party_notices": "THIRD_PARTY_NOTICES.md",
        "security_policy": "SECURITY.md",
        "privacy_policy": "PRIVACY.md",
        "sbom": "SBOM.spdx.json",
        "build": {
            "deterministic_zip": True,
            "zip_compression": "stored",
            "zip_timestamp": "1980-01-01T00:00:00Z",
            "zip_file_mode": "100644",
            "no_clobber": True,
            "atomic_publish": "same_directory_hard_link_no_replace",
        },
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
        "version_core": VERSION_CORE,
        "channel": "beta",
        "release_label": RELEASE_LABEL,
        "artifact_name": ARTIFACT_NAME,
        "archive_root": ARCHIVE_ROOT,
        "sidecar_name": SIDECAR_NAME,
        "attestation_name": ATTESTATION_NAME,
        "source_ref": f"refs/tags/{RELEASE_LABEL}",
        "third_party_notices": "THIRD_PARTY_NOTICES.md",
        "security_policy": "SECURITY.md",
        "privacy_policy": "PRIVACY.md",
        "sbom": "SBOM.spdx.json",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            problems.append(f"identity:{key}")
    license_info = manifest.get("license")
    if license_info != {"declared": "Apache-2.0", "file": "LICENSE"}:
        problems.append("identity:license")
    build = manifest.get("build")
    if not isinstance(build, dict) or build.get("deterministic_zip") is not True or build.get("no_clobber") is not True:
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


def check_current(root: Path) -> dict[str, object]:
    root = root.resolve()
    expected = build_manifest(root)
    path = root / MANIFEST_NAME
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "problems": [f"manifest-read:{type(exc).__name__}"], "expected": expected}
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
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
            if names.count(manifest_member) != 1:
                return ["release-manifest:missing-or-duplicate"]
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
            for info in archive.infolist():
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
        **release_identity(RELEASE_LABEL),
        "archive_root": ARCHIVE_ROOT,
        "license": {"declared": "Apache-2.0", "file": "LICENSE"},
        "third_party_notices": "THIRD_PARTY_NOTICES.md",
        "security_policy": "SECURITY.md",
        "privacy_policy": "PRIVACY.md",
        "sbom": "SBOM.spdx.json",
        "build": {"deterministic_zip": True, "no_clobber": True},
        "integrity": {
            "manifest_in_file_inventory": False,
            "payload_file_count": len(entries),
            "payload_bytes": sum(int(entry["size"]) for entry in entries),
            "payload_index_sha256": sha256_bytes(index),
        },
        "files": entries,
    }
    tests: dict[str, bool] = {"valid_shape_passes": shape_problems(base) == []}
    try:
        release_identity("beta0.5.8")
    except ManifestError:
        tests["stale_VERSION_rejected"] = True
    else:
        tests["stale_VERSION_rejected"] = False
    for name, mutate in {
        "wrong_release_label_rejected": lambda value: value.__setitem__("release_label", "beta0.5.8"),
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
    return tests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root_path())
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result: dict[str, object] = {}
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
            result.get("check", {}).get("ok", True) if isinstance(result.get("check"), dict) else True,
        )
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"RELEASE_PAYLOAD_MANIFEST {'PASSED' if result['ok'] else 'FAILED'}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
