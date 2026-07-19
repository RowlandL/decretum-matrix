#!/usr/bin/env python3
"""Hash-bound npm launcher for the packaged Decretum Matrix CLI."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import runpy
import shutil
import stat
import sys
import tempfile
import uuid
import zipfile


sys.dont_write_bytecode = True

ARCHIVE_ROOT = "decretum-matrix"
MAX_MEMBER_COUNT = 5000
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
FORBIDDEN_PARTS = {
    "agente-logs",
    "court-runtime",
    "memory-decisions",
    "pending",
    "plan-archives",
    "private",
    "shiguan-imports",
}


class LauncherError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _release_archive(package_root: Path) -> tuple[Path, str]:
    release_root = package_root / "release"
    archives = sorted(release_root.glob("decretum-matrix-beta*.zip"))
    if len(archives) != 1:
        raise LauncherError(f"expected one release ZIP, found {len(archives)}")
    archive = archives[0]
    sidecar = archive.with_name(f"{archive.name}.sha256")
    try:
        fields = sidecar.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise LauncherError(f"release sidecar unavailable: {exc}") from exc
    if len(fields) != 2 or fields[1] != archive.name or len(fields[0]) != 64:
        raise LauncherError("release sidecar contract invalid")
    expected = fields[0].lower()
    if any(character not in "0123456789abcdef" for character in expected):
        raise LauncherError("release sidecar digest invalid")
    actual = _sha256(archive)
    if actual != expected:
        raise LauncherError("release ZIP digest mismatch")
    return archive, actual


def _member_parts(name: str) -> tuple[str, ...]:
    if "\\" in name or "\x00" in name:
        raise LauncherError("release ZIP member path invalid")
    value = PurePosixPath(name)
    if value.is_absolute() or value.drive or any(part in {"", ".", ".."} for part in value.parts):
        raise LauncherError("release ZIP member path unsafe")
    if not value.parts or value.parts[0] != ARCHIVE_ROOT:
        raise LauncherError("release ZIP root mismatch")
    if any(part.casefold() in FORBIDDEN_PARTS for part in value.parts[1:]):
        raise LauncherError("release ZIP contains a private runtime surface")
    return value.parts


def _extract_runtime(archive: Path, cache_root: Path, digest: str) -> Path:
    marker = cache_root / ".npm-runtime.json"
    cli = cache_root / "scripts" / "court_cli.py"
    if marker.is_file() and cli.is_file():
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict) and value.get("archive_sha256") == digest:
            return cache_root
        raise LauncherError(f"runtime cache is invalid: {cache_root}")
    if cache_root.exists() or cache_root.is_symlink():
        raise LauncherError(f"runtime cache is incomplete: {cache_root}")

    cache_root.parent.mkdir(parents=True, exist_ok=True)
    staging = cache_root.parent / f".{cache_root.name}.extract-{uuid.uuid4().hex}"
    staging.mkdir(exist_ok=False)
    try:
        with zipfile.ZipFile(archive) as package:
            infos = package.infolist()
            if not infos or len(infos) > MAX_MEMBER_COUNT:
                raise LauncherError("release ZIP member count invalid")
            total = 0
            seen: set[str] = set()
            for info in infos:
                parts = _member_parts(info.filename.rstrip("/"))
                normalized = "/".join(parts)
                if normalized in seen:
                    raise LauncherError("release ZIP contains duplicate members")
                seen.add(normalized)
                total += info.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise LauncherError("release ZIP exceeds runtime size limit")
                file_type = (info.external_attr >> 16) & 0o170000
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise LauncherError("release ZIP contains a link or special file")
                destination = staging.joinpath(*parts)
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with package.open(info, "r") as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        extracted = staging / ARCHIVE_ROOT
        extracted_cli = extracted / "scripts" / "court_cli.py"
        if not extracted_cli.is_file():
            raise LauncherError("release ZIP lacks scripts/court_cli.py")
        marker_payload = json.dumps(
            {
                "schema": "decretum.npm_runtime_cache.v1",
                "archive_sha256": digest,
            },
            ensure_ascii=True,
            sort_keys=True,
        ) + "\n"
        (extracted / ".npm-runtime.json").write_text(marker_payload, encoding="utf-8")
        try:
            os.replace(extracted, cache_root)
        except OSError:
            if not (cache_root / "scripts" / "court_cli.py").is_file():
                raise
        return cache_root
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main(argv: list[str] | None = None) -> int:
    package_root = Path(__file__).resolve().parents[1]
    archive, digest = _release_archive(package_root)
    cache_base = Path(
        os.environ.get("DECRETUM_MATRIX_NPM_CACHE_ROOT")
        or Path(tempfile.gettempdir()) / "decretum-matrix" / "npm-runtime"
    ).resolve(strict=False)
    runtime_root = _extract_runtime(archive, cache_base / digest, digest)
    cli = runtime_root / "scripts" / "court_cli.py"
    sys.path.insert(0, str(cli.parent))
    sys.argv = [str(cli), *(sys.argv[1:] if argv is None else argv)]
    runpy.run_path(str(cli), run_name="__main__")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LauncherError, OSError, zipfile.BadZipFile) as exc:
        print(f"decretum-matrix launcher failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
