#!/usr/bin/env python3
"""Npm launcher for the packaged Decretum Matrix CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import zipfile


sys.dont_write_bytecode = True


def _configure_standard_streams(streams: tuple[object, ...] | None = None) -> None:
    for stream in streams or (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


_configure_standard_streams()

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


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _release_archive(package_root: Path) -> Path:
    release_root = package_root / "release"
    archives = sorted(release_root.glob("decretum-matrix-beta*.zip"))
    if len(archives) != 1:
        raise LauncherError(f"expected one release ZIP, found {len(archives)}")
    archive = archives[0]
    return archive


def _archive_cache_id(archive: Path) -> str:
    candidate = archive.stem.replace("decretum-matrix-", "", 1)
    cleaned = "".join(
        character if character.isalnum() or character in "._-" else "-"
        for character in candidate
    ).strip(".-_")
    return cleaned or "runtime"


def _packaged_version(package_root: Path) -> str:
    version_path = package_root / "VERSION"
    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError:
        version = ""
    if version:
        return version
    try:
        package_json = json.loads((package_root / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    metadata = package_json.get("decretumMatrix") if isinstance(package_json, dict) else None
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("releaseLabel") or "").strip()


def _canonical_runtime_root(package_root: Path, home: Path | None = None) -> Path | None:
    expected_version = _packaged_version(package_root)
    if not expected_version:
        return None
    root = (home or _postinstall_home()) / ".agents" / "skills" / "decretum-matrix"
    version_path = root / "VERSION"
    cli = root / "scripts" / "court_cli.py"
    skill = root / "SKILL.md"
    try:
        installed_version = version_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if installed_version != expected_version:
        return None
    if not cli.is_file() or not skill.is_file():
        return None
    return root


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


def _extract_runtime(archive: Path, cache_root: Path, archive_id: str) -> Path:
    marker = cache_root / ".npm-runtime.json"
    cli = cache_root / "scripts" / "court_cli.py"
    if marker.is_file() and cli.is_file():
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict) and value.get("archive_id") == archive_id:
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
                "archive_id": archive_id,
                "archive_name": archive.name,
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


def _postinstall_home() -> Path:
    value = (
        os.environ.get("USERPROFILE")
        if os.name == "nt"
        else os.environ.get("HOME")
    )
    return Path(value or Path.home()).expanduser().resolve(strict=False)


def _run_json_command(arguments: list[str], *, env: dict[str, str]) -> dict[str, object]:
    try:
        result = subprocess.run(
            arguments,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env=env,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "status": "COMMAND_FAILED",
            "reason": f"{type(exc).__name__}:{exc}",
            "returncode": None,
        }
    try:
        payload = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "status": "INVALID_RECEIPT",
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
    if not isinstance(payload, dict):
        payload = {"ok": False, "status": "INVALID_RECEIPT"}
    payload["returncode"] = result.returncode
    return payload


def _ensure_shared_shiguan_seed(runtime_root: Path) -> Path:
    scripts_root = runtime_root / "scripts"
    if not (scripts_root / "shiguan_paths.py").is_file():
        raise LauncherError("release runtime lacks scripts/shiguan_paths.py")
    inserted = str(scripts_root) not in sys.path
    if inserted:
        sys.path.insert(0, str(scripts_root))
    try:
        import shiguan_paths

        return shiguan_paths.ensure_shared_seed()
    except (OSError, RuntimeError) as exc:
        raise LauncherError(f"shared Shiguan seed failed: {exc}") from exc
    finally:
        if inserted:
            sys.path.remove(str(scripts_root))


def _run_postinstall(runtime_root: Path, archive_id: str) -> int:
    home = _postinstall_home()
    sync_script = runtime_root / "scripts" / "sync_active_copies.py"
    if not sync_script.is_file():
        raise LauncherError("release runtime lacks scripts/sync_active_copies.py")
    sync_arguments = [
        sys.executable,
        "-B",
        str(sync_script),
        "--source",
        str(runtime_root),
        "--write",
        "--prune-obsolete",
        "--json",
    ]
    child_env = dict(os.environ)
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    child_env["DECRETUM_MATRIX_BOOTSTRAP_INSTALL_CONTEXT"] = "npm"
    sync_receipt = _run_json_command(sync_arguments, env=child_env)
    shared_shiguan: dict[str, object]
    if sync_receipt.get("ok") is True:
        try:
            references = _ensure_shared_shiguan_seed(runtime_root)
            shared_shiguan = {
                "status": "SEEDED",
                "references": str(references),
            }
        except LauncherError as exc:
            shared_shiguan = {"status": "FAILED", "reason": str(exc)}
    else:
        shared_shiguan = {"status": "NOT_RUN"}

    receipt_path = (
        home
        / ".agents"
        / "install-receipts"
        / "decretum-matrix"
        / f"npm-postinstall-{archive_id}.json"
    )
    combined: dict[str, object] = {
        "schema": "decretum.npm_postinstall.v1",
        "ok": sync_receipt.get("ok") is True and shared_shiguan["status"] == "SEEDED",
        "status": (
            "INSTALLED"
            if sync_receipt.get("ok") is True and shared_shiguan["status"] == "SEEDED"
            else "FAILED"
        ),
        "archive_id": archive_id,
        "home_root": str(home),
        "sync": sync_receipt,
        "shared_shiguan": shared_shiguan,
        "pending_body_access": "NO",
        "body_content_reads": 0,
        "bootstrap_validation": "STRUCTURAL_ONLY",
        "temporary_validation_helper": "NOT_USED",
    }
    if combined["ok"] is not True:
        _write_json_atomic(receipt_path, combined)
        raise LauncherError(f"postinstall sync failed; receipt: {receipt_path}")
    _write_json_atomic(receipt_path, combined)
    print(json.dumps(combined, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    package_root = Path(__file__).resolve().parents[1]
    effective_argv = sys.argv[1:] if argv is None else argv
    if effective_argv == ["--npm-postinstall"]:
        archive = _release_archive(package_root)
        archive_id = _archive_cache_id(archive)
        cache_base = Path(
            os.environ.get("DECRETUM_MATRIX_NPM_CACHE_ROOT")
            or Path(tempfile.gettempdir()) / "decretum-matrix" / "npm-runtime"
        ).resolve(strict=False)
        runtime_root = _extract_runtime(archive, cache_base / archive_id, archive_id)
        return _run_postinstall(runtime_root, archive_id)
    runtime_root = _canonical_runtime_root(package_root)
    if runtime_root is None:
        archive = _release_archive(package_root)
        archive_id = _archive_cache_id(archive)
        cache_base = Path(
            os.environ.get("DECRETUM_MATRIX_NPM_CACHE_ROOT")
            or Path(tempfile.gettempdir()) / "decretum-matrix" / "npm-runtime"
        ).resolve(strict=False)
        runtime_root = _extract_runtime(archive, cache_base / archive_id, archive_id)
    cli = runtime_root / "scripts" / "court_cli.py"
    sys.path.insert(0, str(cli.parent))
    sys.argv = [str(cli), *effective_argv]
    runpy.run_path(str(cli), run_name="__main__")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LauncherError, OSError, zipfile.BadZipFile) as exc:
        print(f"decretum-matrix launcher failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
