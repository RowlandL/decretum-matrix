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
import subprocess
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


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


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


def _run_postinstall(runtime_root: Path, digest: str) -> int:
    home = _postinstall_home()
    scripts = runtime_root / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        from install_current_agent_copy import (  # type: ignore[import-not-found]
            install_current_agent_copy,
            rollback_install_backup,
        )
    except ImportError as exc:
        raise LauncherError(f"release runtime lacks the install updater: {exc}") from exc

    install = install_current_agent_copy(
        source_root=runtime_root,
        home_root=home,
        current_tool="npm",
        explicit_tools=[],
        tool_roots={},
        projection_manifest=(
            runtime_root
            / "references"
            / "manifests"
            / "install-projection.v1.json"
        ),
        write=True,
        source_package_sha256=digest,
    )
    if install.get("ok") is not True:
        raise LauncherError(
            "transactional canonical install failed: "
            f"{install.get('reason')}:{install.get('detail', '')}"
        )

    installed_root = home / ".agents" / "skills" / "decretum-matrix"
    bootstrap = installed_root / "scripts" / "ensure_portable_court_bootstrap.py"
    if not bootstrap.is_file():
        raise LauncherError("installed runtime lacks the portable bootstrap")
    activate = os.environ.get(
        "DECRETUM_MATRIX_POSTINSTALL_ACTIVATE_SERVICES", "1"
    ).strip().casefold() not in {"0", "false", "no", "off"}
    bootstrap_arguments = [
        sys.executable,
        "-B",
        str(bootstrap),
        "--apply",
        "--shared-shiguan-and-obsidian-only",
        "--format",
        "json",
    ]
    if not activate:
        bootstrap_arguments.extend(["--skip-obsidian", "--skip-service-daemon"])
    child_env = dict(os.environ)
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    child_env["DECRETUM_MATRIX_BOOTSTRAP_INSTALL_CONTEXT"] = "npm"
    bootstrap_receipt = _run_json_command(bootstrap_arguments, env=child_env)

    receipt_path = (
        home
        / ".agents"
        / "install-receipts"
        / "decretum-matrix"
        / f"npm-postinstall-{digest}.json"
    )
    combined: dict[str, object] = {
        "schema": "decretum.npm_postinstall.v1",
        "ok": bootstrap_receipt.get("ok") is True,
        "status": (
            "INSTALLED"
            if bootstrap_receipt.get("ok") is True
            else "ROLLBACK_REQUIRED"
        ),
        "archive_sha256": digest,
        "home_root": str(home),
        "installed_root": str(installed_root),
        "service_activation_requested": activate,
        "install": install,
        "bootstrap": bootstrap_receipt,
        "pending_body_access": "NO",
        "body_content_reads": 0,
        "body_hashes": 0,
    }
    if bootstrap_receipt.get("ok") is not True:
        rollbacks: dict[str, object] = {}
        shared_step = (
            bootstrap_receipt.get("steps", {}).get("shared_shiguan")
            if isinstance(bootstrap_receipt.get("steps"), dict)
            else None
        )
        topology = (
            shared_step.get("topology")
            if isinstance(shared_step, dict)
            else None
        )
        shared_backup = (
            topology.get("backup_root") if isinstance(topology, dict) else None
        )
        if (
            isinstance(shared_step, dict)
            and shared_step.get("status") == "ROLLED_BACK"
        ) or (
            isinstance(topology, dict)
            and topology.get("status") == "ROLLED_BACK"
        ):
            rollbacks["shared"] = {
                "ok": True,
                "status": "ALREADY_ROLLED_BACK",
                "pending_body_access": "NO",
            }
        elif isinstance(shared_backup, str) and shared_backup:
            rollbacks["shared"] = _run_json_command(
                [
                    sys.executable,
                    "-B",
                    str(bootstrap),
                    "--rollback-shared-transaction",
                    shared_backup,
                    "--format",
                    "json",
                ],
                env=child_env,
            )
        backup = install.get("backup")
        backup_root = (
            backup.get("backup_root") if isinstance(backup, dict) else None
        )
        if isinstance(backup_root, str) and backup_root:
            rollbacks["install"] = rollback_install_backup(
                home_root=home,
                backup_root=Path(backup_root),
            )
        combined["rollbacks"] = rollbacks
        combined["status"] = (
            "ROLLED_BACK"
            if rollbacks
            and all(
                isinstance(value, dict) and value.get("ok") is True
                for value in rollbacks.values()
            )
            else "BLOCKED_MANUAL_RECOVERY"
        )
        _write_json_atomic(receipt_path, combined)
        raise LauncherError(
            f"postinstall bootstrap failed; receipt: {receipt_path}"
        )
    _write_json_atomic(receipt_path, combined)
    print(json.dumps(combined, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    package_root = Path(__file__).resolve().parents[1]
    archive, digest = _release_archive(package_root)
    cache_base = Path(
        os.environ.get("DECRETUM_MATRIX_NPM_CACHE_ROOT")
        or Path(tempfile.gettempdir()) / "decretum-matrix" / "npm-runtime"
    ).resolve(strict=False)
    runtime_root = _extract_runtime(archive, cache_base / digest, digest)
    effective_argv = sys.argv[1:] if argv is None else argv
    if effective_argv == ["--npm-postinstall"]:
        return _run_postinstall(runtime_root, digest)
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
