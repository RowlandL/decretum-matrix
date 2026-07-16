"""Build and exclusively publish immutable Decretum Matrix release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Mapping

sys.dont_write_bytecode = True

import package_skill
import release_payload_manifest


ROOT = Path(__file__).resolve().parents[1]
NAME = "decretum-matrix"
DISPLAY_NAME = "Decretum Matrix（诏令矩阵）"
LICENSE_ID = "AGPL-3.0-only"
ATTESTATION_SCHEMA = "court.release_attestation.v1"
RELEASE_RE = re.compile(r"^beta(?P<core>0\.[0-9]+\.[0-9]+)$")
TAG_SIGNATURE_MARKERS = (
    "-----BEGIN PGP SIGNATURE-----",
    "-----BEGIN SSH SIGNATURE-----",
    "-----BEGIN SIGNED MESSAGE-----",
)


class ArtifactBuildError(RuntimeError):
    """Raised when a release artifact contract cannot be satisfied."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_release_label(root: Path = ROOT) -> str:
    try:
        value = (root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ArtifactBuildError(f"VERSION read failed: {exc}") from exc
    if not RELEASE_RE.fullmatch(value):
        raise ArtifactBuildError(f"invalid release label: {value!r}")
    return value


def load_payload_manifest(root: Path = ROOT) -> dict[str, object]:
    try:
        checked = release_payload_manifest.check_current(root)
    except release_payload_manifest.ManifestError as exc:
        raise ArtifactBuildError(f"release payload manifest contract failed: {exc}") from exc
    if not checked.get("ok"):
        raise ArtifactBuildError(
            "release payload manifest is stale: "
            + ",".join(str(item) for item in checked.get("problems", []))
        )
    manifest = checked.get("manifest")
    if not isinstance(manifest, dict):
        raise ArtifactBuildError("release payload manifest did not decode to an object")
    return manifest


def git_text(*args: str, root: Path = ROOT, allowed_returncodes: tuple[int, ...] = (0,)) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode not in allowed_returncodes:
        detail = (completed.stderr or completed.stdout).strip()
        raise ArtifactBuildError(f"git {' '.join(args)} failed: {detail[:500]}")
    return completed.stdout.strip()


def tag_has_signature(tag_body: str) -> bool:
    return any(marker in tag_body for marker in TAG_SIGNATURE_MARKERS)


def collect_source_identity(release_label: str, root: Path = ROOT) -> dict[str, str]:
    if git_text("status", "--porcelain", root=root):
        raise ArtifactBuildError("release source worktree is not clean")
    tag_ref = f"refs/tags/{release_label}"
    tag_type = git_text("cat-file", "-t", tag_ref, root=root)
    if tag_type != "tag":
        raise ArtifactBuildError(f"release ref must be an annotated tag: {tag_ref}")
    head_commit = git_text("rev-parse", "HEAD", root=root)
    tag_object = git_text("rev-parse", tag_ref, root=root)
    tag_commit = git_text("rev-parse", f"{tag_ref}^{{}}", root=root)
    tree = git_text("rev-parse", "HEAD^{tree}", root=root)
    if tag_commit != head_commit:
        raise ArtifactBuildError(f"release tag does not point to HEAD: {tag_commit} != {head_commit}")
    tag_body = git_text("cat-file", "-p", tag_ref, root=root)
    if tag_has_signature(tag_body):
        git_text("verify-tag", release_label, root=root)
        tag_signature = "PASSED"
    else:
        tag_signature = "UNAVAILABLE"
    return {
        "head_commit": head_commit,
        "tag_ref": tag_ref,
        "tag_object": tag_object,
        "tag_commit": tag_commit,
        "tree": tree,
        "tag_signature": tag_signature,
    }


def expected_names(manifest: Mapping[str, object]) -> tuple[str, str, str, str, str]:
    release_label = str(manifest.get("release_label"))
    if (
        manifest.get("name") != NAME
        or manifest.get("display_name") != DISPLAY_NAME
        or manifest.get("package_name") != NAME
        or manifest.get("license") != {"declared": LICENSE_ID, "file": "LICENSE"}
        or manifest.get("archive_root") != f"{package_skill.ROOT_NAME}/"
    ):
        raise ArtifactBuildError("release manifest product/license/locator identity mismatch")
    expected_zip = f"{NAME}-{release_label}.zip"
    if manifest.get("artifact_name") != expected_zip:
        raise ArtifactBuildError(f"release artifact name mismatch: expected {expected_zip}")
    return (
        expected_zip,
        str(manifest.get("sidecar_name")),
        str(manifest.get("attestation_name")),
        f"{NAME}-{release_label}.release-notes.md",
        "SBOM.spdx.json",
    )


def build_candidate_zip(path: Path) -> bytes:
    entry_count, zip_count, problems = package_skill.build(path)
    if problems:
        raise ArtifactBuildError("candidate package failed: " + ",".join(problems[:20]))
    if entry_count != zip_count:
        raise ArtifactBuildError(f"candidate package count mismatch: {entry_count} != {zip_count}")
    return path.read_bytes()


def build_attestation(
    *,
    manifest: Mapping[str, object],
    source: Mapping[str, str],
    zip_bytes: bytes,
    notes_bytes: bytes,
    sbom_bytes: bytes,
    root: Path = ROOT,
) -> dict[str, object]:
    zip_name, sidecar_name, _, notes_name, sbom_name = expected_names(manifest)
    zip_sha = sha256_bytes(zip_bytes)
    sidecar_bytes = f"{zip_sha}  {zip_name}\n".encode("utf-8")
    manifest_bytes = (root / release_payload_manifest.MANIFEST_NAME).read_bytes()
    integrity = manifest.get("integrity")
    if not isinstance(integrity, dict):
        raise ArtifactBuildError("release payload manifest integrity block is missing")
    return {
        "schema": ATTESTATION_SCHEMA,
        "name": NAME,
        "display_name": DISPLAY_NAME,
        "package_name": NAME,
        "license": LICENSE_ID,
        "archive_root": f"{package_skill.ROOT_NAME}/",
        "release_label": manifest.get("release_label"),
        "source": dict(source),
        "release_manifest": {
            "path": release_payload_manifest.MANIFEST_NAME,
            "sha256": sha256_bytes(manifest_bytes),
            "payload_index_sha256": integrity.get("payload_index_sha256"),
        },
        "artifacts": [
            {"name": zip_name, "sha256": zip_sha, "size": len(zip_bytes)},
            {"name": sidecar_name, "sha256": sha256_bytes(sidecar_bytes), "size": len(sidecar_bytes)},
            {"name": notes_name, "sha256": sha256_bytes(notes_bytes), "size": len(notes_bytes)},
            {"name": sbom_name, "sha256": sha256_bytes(sbom_bytes), "size": len(sbom_bytes)},
        ],
        "build_contract": {
            "deterministic_zip": True,
            "no_clobber": True,
            "exclusive_final_directory": True,
            "exclusive_asset_create": True,
        },
    }


def build_candidate_artifacts(
    *,
    candidate_zip: Path,
    manifest: Mapping[str, object],
    source: Mapping[str, str],
    root: Path = ROOT,
) -> dict[str, bytes]:
    zip_name, sidecar_name, attestation_name, notes_name, sbom_name = expected_names(manifest)
    zip_bytes = build_candidate_zip(candidate_zip)
    zip_sha = sha256_bytes(zip_bytes)
    notes_bytes = (root / "RELEASE-LOG.md").read_bytes()
    sbom_bytes = (root / "SBOM.spdx.json").read_bytes()
    attestation = build_attestation(
        manifest=manifest,
        source=source,
        zip_bytes=zip_bytes,
        notes_bytes=notes_bytes,
        sbom_bytes=sbom_bytes,
        root=root,
    )
    return {
        zip_name: zip_bytes,
        sidecar_name: f"{zip_sha}  {zip_name}\n".encode("utf-8"),
        attestation_name: (json.dumps(attestation, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        notes_name: notes_bytes,
        sbom_name: sbom_bytes,
    }


def validate_candidate_artifacts(
    artifacts: Mapping[str, bytes],
    *,
    manifest: Mapping[str, object],
    source: Mapping[str, str],
    root: Path = ROOT,
) -> dict[str, object]:
    expected = expected_names(manifest)
    if set(artifacts) != set(expected):
        raise ArtifactBuildError(
            f"candidate artifact set mismatch: expected={sorted(expected)!r} actual={sorted(artifacts)!r}"
        )
    zip_name, sidecar_name, attestation_name, notes_name, sbom_name = expected
    zip_bytes = artifacts[zip_name]
    zip_sha = sha256_bytes(zip_bytes)
    expected_sidecar = f"{zip_sha}  {zip_name}\n".encode("utf-8")
    if artifacts[sidecar_name] != expected_sidecar:
        raise ArtifactBuildError("checksum sidecar does not match candidate ZIP")
    try:
        attestation = json.loads(artifacts[attestation_name].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactBuildError(f"attestation is not valid UTF-8 JSON: {exc}") from exc
    expected_attestation = build_attestation(
        manifest=manifest,
        source=source,
        zip_bytes=zip_bytes,
        notes_bytes=artifacts[notes_name],
        sbom_bytes=artifacts[sbom_name],
        root=root,
    )
    if attestation != expected_attestation:
        raise ArtifactBuildError("attestation does not match HEAD/tag/tree/manifest/artifacts")
    with tempfile.TemporaryDirectory(prefix="decretum-release-validate-") as tmp_text:
        archive_path = Path(tmp_text) / zip_name
        archive_path.write_bytes(zip_bytes)
        _, package_problems = package_skill.validate_zip(archive_path)
        payload_problems = release_payload_manifest.validate_zip_payload(archive_path)
    if package_problems or payload_problems:
        raise ArtifactBuildError(
            "candidate ZIP validation failed: " + ",".join((package_problems + payload_problems)[:20])
        )
    return {
        "zip_sha256": zip_sha,
        "zip_size": len(zip_bytes),
        "attestation": attestation,
    }


def exclusive_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def create_final_directory(root: Path, release_label: str) -> Path:
    final = root / release_label
    final.mkdir(parents=False, exist_ok=False)
    return final


def publish_candidate(
    out_root: Path,
    *,
    manifest: Mapping[str, object],
    source: Mapping[str, str],
    artifacts: Mapping[str, bytes],
    root: Path = ROOT,
) -> tuple[Path, dict[str, object]]:
    release_label = str(manifest.get("release_label"))
    final = out_root / release_label
    if final.exists():
        raise ArtifactBuildError(f"final version directory already exists: {final}")
    validation = validate_candidate_artifacts(artifacts, manifest=manifest, source=source, root=root)
    final = create_final_directory(out_root, release_label)
    for name in sorted(artifacts, key=lambda value: value.encode("utf-8")):
        exclusive_write(final / name, artifacts[name])
    return final, validation


def synthetic_source_identity(root: Path = ROOT) -> dict[str, str]:
    head = git_text("rev-parse", "HEAD", root=root)
    tree = git_text("rev-parse", "HEAD^{tree}", root=root)
    return {
        "head_commit": head,
        "tag_ref": f"refs/tags/{read_release_label(root)}",
        "tag_object": "1" * 40,
        "tag_commit": head,
        "tree": tree,
        "tag_signature": "UNAVAILABLE",
    }


def run_self_tests(root: Path = ROOT) -> dict[str, bool]:
    tests: dict[str, bool] = {
        "canonical_release_product_name_required": NAME == "decretum-matrix",
        "canonical_display_name_required": getattr(release_payload_manifest, "DISPLAY_NAME", None)
        == "Decretum Matrix（诏令矩阵）",
        "canonical_beta_0_5_10_artifact_required": (
            release_payload_manifest.RELEASE_LABEL == "beta0.5.10"
            and release_payload_manifest.ARTIFACT_NAME == "decretum-matrix-beta0.5.10.zip"
        ),
        "agpl_only_release_required": getattr(release_payload_manifest, "LICENSE_ID", None)
        == "AGPL-3.0-only",
        "stable_install_locator_required": package_skill.ROOT_NAME == "court-capability-router",
    }
    if not all(tests.values()):
        return tests
    manifest = load_payload_manifest(root)
    source = synthetic_source_identity(root)
    release_label = str(manifest["release_label"])
    tests["annotated_tag_signature_markers_detected"] = (
        all(tag_has_signature(f"tag body\n{marker}\nfixture") for marker in TAG_SIGNATURE_MARKERS)
        and not tag_has_signature("unsigned annotated tag body")
    )
    with tempfile.TemporaryDirectory(prefix="decretum-release-builder-self-test-") as tmp_text:
        temp_root = Path(tmp_text)
        first = temp_root / "candidate-a.zip"
        second = temp_root / "candidate-b.zip"
        first_bytes = build_candidate_zip(first)
        second_bytes = build_candidate_zip(second)
        tests["two_candidate_builds_have_identical_zip_sha256"] = sha256_bytes(first_bytes) == sha256_bytes(second_bytes)

        zip_name = str(manifest["artifact_name"])
        artifacts = build_candidate_artifacts(
            candidate_zip=temp_root / "candidate-c.zip",
            manifest=manifest,
            source=source,
            root=root,
        )
        validation = validate_candidate_artifacts(artifacts, manifest=manifest, source=source, root=root)
        tests["sidecar_matches_zip"] = validation["zip_sha256"] == sha256_bytes(artifacts[zip_name])
        attestation = validation["attestation"]
        tests["attestation_matches_head_tag_tree_and_manifest"] = (
            isinstance(attestation, dict)
            and attestation.get("source") == source
            and isinstance(attestation.get("release_manifest"), dict)
            and attestation["release_manifest"].get("sha256")
            == sha256_bytes((root / release_payload_manifest.MANIFEST_NAME).read_bytes())
        )

        existing_root = temp_root / "existing-root"
        existing_root.mkdir()
        existing_final = existing_root / release_label
        existing_final.mkdir()
        sentinel = existing_final / "sentinel.txt"
        sentinel.write_bytes(b"preserve")
        try:
            publish_candidate(existing_root, manifest=manifest, source=source, artifacts=artifacts, root=root)
        except ArtifactBuildError:
            tests["existing_version_directory_is_rejected"] = sentinel.read_bytes() == b"preserve"
        else:
            tests["existing_version_directory_is_rejected"] = False

        existing_asset = temp_root / "existing-asset.txt"
        existing_asset.write_bytes(b"preserve")
        try:
            exclusive_write(existing_asset, b"replace")
        except FileExistsError:
            tests["existing_asset_is_rejected"] = existing_asset.read_bytes() == b"preserve"
        else:
            tests["existing_asset_is_rejected"] = False

        failure_root = temp_root / "failure-root"
        failure_root.mkdir()
        broken = dict(artifacts)
        broken[str(manifest["sidecar_name"])] = b"wrong\n"
        try:
            publish_candidate(failure_root, manifest=manifest, source=source, artifacts=broken, root=root)
        except ArtifactBuildError:
            tests["failure_does_not_create_a_final_version_directory"] = not (failure_root / release_label).exists()
        else:
            tests["failure_does_not_create_a_final_version_directory"] = False
    return tests


def build_release(out_root: Path, root: Path = ROOT) -> dict[str, object]:
    manifest = load_payload_manifest(root)
    release_label = read_release_label(root)
    if manifest.get("release_label") != release_label:
        raise ArtifactBuildError("VERSION and release payload manifest disagree")
    out_root = out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    final = out_root / release_label
    if final.exists():
        raise ArtifactBuildError(f"final version directory already exists: {final}")
    source = collect_source_identity(release_label, root)
    with tempfile.TemporaryDirectory(prefix=f".{release_label}.candidate-", dir=out_root) as tmp_text:
        candidate_zip = Path(tmp_text) / str(manifest["artifact_name"])
        artifacts = build_candidate_artifacts(
            candidate_zip=candidate_zip,
            manifest=manifest,
            source=source,
            root=root,
        )
        final, validation = publish_candidate(
            out_root,
            manifest=manifest,
            source=source,
            artifacts=artifacts,
            root=root,
        )
    return {
        "ok": True,
        "release_label": release_label,
        "final_directory": str(final),
        "artifacts": [
            {
                "name": path.name,
                "size": path.stat().st_size,
                "sha256": sha256_bytes(path.read_bytes()),
            }
            for path in sorted(final.iterdir(), key=lambda value: value.name.encode("utf-8"))
        ],
        "zip_sha256": validation["zip_sha256"],
        "source": source,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, default=ROOT.parent / "release-packages" / NAME)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            tests = run_self_tests()
            result: dict[str, object] = {"ok": all(tests.values()), "self_test": tests}
        else:
            result = build_release(args.out_root)
    except (ArtifactBuildError, FileExistsError, OSError, subprocess.SubprocessError) as exc:
        result = {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result.get("ok"):
        print("RELEASE_ARTIFACT_BUILDER_PASSED")
    else:
        print(f"RELEASE_ARTIFACT_BUILDER_FAILED {result.get('error', 'self-test')}")
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
