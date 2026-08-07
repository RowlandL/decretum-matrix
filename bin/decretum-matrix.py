#!/usr/bin/env python3
"""Npm launcher for the packaged Decretum Matrix CLI."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from pathlib import Path, PurePosixPath
import re
import runpy
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
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
GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_LATEST_DOWNLOAD = "https://github.com/{repo}/releases/latest/download/{asset}"
SUPERCC_DEPENDENCY_REPOS = {
    "zellij": "zellij-org/zellij",
    "squad": os.environ.get("COURT_SQUAD_GITHUB_REPO", "mco-org/squad"),
}
OPEN_SOURCE_ACKNOWLEDGEMENTS = [
    {
        "name": "zellij",
        "project": "Zellij",
        "url": "https://github.com/zellij-org/zellij",
        "thanks": "Decretum Matrix thanks the Zellij project for the optional terminal workspace used by visible superCC panes.",
    },
    {
        "name": "squad",
        "project": "squad",
        "url": "https://github.com/mco-org/squad",
        "thanks": "Decretum Matrix thanks the squad project for the optional structured task/message bus used by superCC dispatch evidence.",
    },
]
RUNTIME_IDENTITY_SCHEMA = "court.runtime_identity.v1"
RUNTIME_IDENTITY_PATHS = ("VERSION", "SKILL.md", "scripts/court_cli.py")


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


def _runtime_content_digest(root: Path) -> str | None:
    try:
        payloads = {
            relative: (root / relative).read_bytes()
            for relative in RUNTIME_IDENTITY_PATHS
        }
    except OSError:
        return None
    return _runtime_content_digest_from_payloads(payloads)


def _runtime_content_digest_from_payloads(payloads: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative in RUNTIME_IDENTITY_PATHS:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payloads[relative])
        digest.update(b"\0")
    return digest.hexdigest()


def _runtime_identity(root: Path, *, source_kind: str) -> dict[str, str] | None:
    try:
        version = (root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    content_digest = _runtime_content_digest(root)
    if not version or not content_digest:
        return None
    return {
        "schema": RUNTIME_IDENTITY_SCHEMA,
        "root": str(root.resolve(strict=False)),
        "version": version,
        "source_kind": source_kind,
        "content_digest": content_digest,
    }


def _embedded_runtime_identity(package_root: Path) -> dict[str, str] | None:
    archive = _release_archive(package_root)
    try:
        with zipfile.ZipFile(archive) as package:
            payloads: dict[str, bytes] = {}
            for relative in RUNTIME_IDENTITY_PATHS:
                member_name = f"{ARCHIVE_ROOT}/{relative}"
                matches = [
                    info
                    for info in package.infolist()
                    if info.filename.rstrip("/") == member_name
                ]
                if len(matches) != 1 or matches[0].is_dir():
                    return None
                payloads[relative] = package.read(matches[0])
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    try:
        version = payloads["VERSION"].decode("utf-8").strip()
    except UnicodeError:
        return None
    packaged_version = _packaged_version(package_root)
    if not version or not packaged_version or version != packaged_version:
        return None
    return {
        "schema": RUNTIME_IDENTITY_SCHEMA,
        "root": f"{archive.resolve(strict=False)}!/{ARCHIVE_ROOT}",
        "version": version,
        "source_kind": "embedded_package",
        "content_digest": _runtime_content_digest_from_payloads(payloads),
    }


def _expected_runtime_identity(package_root: Path) -> dict[str, str] | None:
    direct = _runtime_identity(package_root, source_kind="package")
    return direct if direct is not None else _embedded_runtime_identity(package_root)


def _runtime_identity_matches(
    expected: dict[str, str],
    candidate: dict[str, str],
) -> bool:
    return (
        candidate.get("version") == expected.get("version")
        and candidate.get("content_digest") == expected.get("content_digest")
    )


def _canonical_runtime_selection(
    package_root: Path,
    home: Path | None = None,
    *,
    expected_identity: dict[str, str] | None = None,
) -> tuple[Path, dict[str, str]] | None:
    expected = expected_identity or _expected_runtime_identity(package_root)
    if expected is None:
        return None
    root = (home or _postinstall_home()) / ".agents" / "skills" / "decretum-matrix"
    installed = _runtime_identity(root, source_kind="installed")
    if installed is None or not _runtime_identity_matches(expected, installed):
        return None
    return root, installed


def _canonical_runtime_root(
    package_root: Path,
    home: Path | None = None,
    *,
    expected_identity: dict[str, str] | None = None,
) -> Path | None:
    selection = _canonical_runtime_selection(
        package_root,
        home=home,
        expected_identity=expected_identity,
    )
    return selection[0] if selection is not None else None


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


def _select_runtime(
    package_root: Path,
    *,
    home: Path | None = None,
    cache_base: Path | None = None,
) -> tuple[Path, dict[str, str]]:
    expected = _expected_runtime_identity(package_root)
    if expected is None:
        raise LauncherError("package runtime identity unavailable")
    canonical = _canonical_runtime_selection(
        package_root,
        home=home,
        expected_identity=expected,
    )
    if canonical is not None:
        return canonical

    archive = _release_archive(package_root)
    archive_id = _archive_cache_id(archive)
    resolved_cache_base = (
        cache_base
        or Path(
            os.environ.get("DECRETUM_MATRIX_NPM_CACHE_ROOT")
            or Path(tempfile.gettempdir()) / "decretum-matrix" / "npm-runtime"
        )
    ).resolve(strict=False)
    runtime_root = _extract_runtime(archive, resolved_cache_base / archive_id, archive_id)
    identity = _runtime_identity(runtime_root, source_kind="embedded_cache")
    if identity is None or not _runtime_identity_matches(expected, identity):
        raise LauncherError("embedded runtime identity mismatch")
    return runtime_root, identity


def runtime_identity_probe(
    package_root: Path,
    *,
    home: Path | None = None,
    cache_base: Path | None = None,
) -> dict[str, str]:
    _, identity = _select_runtime(
        package_root,
        home=home,
        cache_base=cache_base,
    )
    return identity


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


def _tool_install_dir(home: Path) -> Path:
    if os.name == "nt":
        return Path(os.environ.get("COURT_TOOL_INSTALL_DIR", r"C:\Tools\bin")).resolve(strict=False)
    return Path(os.environ.get("COURT_TOOL_INSTALL_DIR", str(home / ".local" / "bin"))).expanduser().resolve(strict=False)


def _tool_path_env(install_dir: Path) -> str:
    current = os.environ.get("PATH", "")
    return str(install_dir) + (os.pathsep + current if current else "")


def _resolve_tool_command(tool: str, install_dir: Path) -> list[str]:
    resolved = shutil.which(tool, path=_tool_path_env(install_dir)) or tool
    suffix = Path(resolved).suffix.lower()
    if suffix in {".cmd", ".bat"}:
        return [os.environ.get("ComSpec") or "cmd.exe", "/d", "/c", resolved]
    return [resolved]


def _run_tool_version(tool: str, install_dir: Path) -> dict[str, object]:
    command = [*_resolve_tool_command(tool, install_dir), "--version"]
    try:
        result = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env={**os.environ, "PATH": _tool_path_env(install_dir)},
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": f"{type(exc).__name__}:{exc}", "command": command}
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "command": command[:1] + ["..."],
        "stdout": (result.stdout or "").strip()[-1200:],
        "stderr": (result.stderr or "").strip()[-1200:],
    }


def _normalized_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x64", "x86-64"}:
        return "x86_64"
    if machine in {"arm64", "aarch64"}:
        return "aarch64"
    return machine or "unknown"


def _tool_target(tool: str) -> dict[str, str]:
    arch = _normalized_arch()
    if os.name == "nt":
        if arch != "x86_64":
            return {"ok": "false", "reason": f"{tool} Windows asset target is not known for {arch}"}
        return {"ok": "true", "triple": "x86_64-pc-windows-msvc", "archive": "zip", "binary": f"{tool}.exe"}
    if sys.platform == "darwin":
        if arch not in {"x86_64", "aarch64"}:
            return {"ok": "false", "reason": f"{tool} macOS asset target is not known for {arch}"}
        return {"ok": "true", "triple": f"{arch}-apple-darwin", "archive": "tar.gz", "binary": tool}
    if sys.platform.startswith("linux"):
        if tool == "squad" and arch != "x86_64":
            return {"ok": "false", "reason": "squad Linux asset target is only known for x86_64"}
        if arch not in {"x86_64", "aarch64"}:
            return {"ok": "false", "reason": f"{tool} Linux asset target is not known for {arch}"}
        return {"ok": "true", "triple": f"{arch}-unknown-linux-musl", "archive": "tar.gz", "binary": tool}
    return {"ok": "false", "reason": f"{tool} asset target is not known for platform {sys.platform}"}


def _asset_name_and_pattern(tool: str, target: dict[str, str]) -> tuple[str, re.Pattern[str]]:
    suffix = "zip" if target["archive"] == "zip" else "tar.gz"
    name = f"{tool}-{target['triple']}.{suffix}"
    return name, re.compile(rf"^{re.escape(name)}$", re.IGNORECASE)


def _http_json(url: str) -> dict[str, object]:
    request = urllib.request.Request(url, headers={"User-Agent": "decretum-matrix-postinstall"})
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310 - user-approved first-install dependency fetch.
        return json.loads(response.read().decode("utf-8"))


def _http_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "decretum-matrix-postinstall"})
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310 - user-approved first-install dependency fetch.
        return response.read()


def _select_release_asset(tool: str, repo: str, target: dict[str, str]) -> dict[str, str]:
    fallback_name, pattern = _asset_name_and_pattern(tool, target)
    try:
        release = _http_json(GITHUB_API.format(repo=repo))
        assets = release.get("assets")
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        assets = []
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "")
            if pattern.fullmatch(name):
                return {
                    "name": name,
                    "url": str(asset.get("browser_download_url") or GITHUB_LATEST_DOWNLOAD.format(repo=repo, asset=name)),
                    "digest": str(asset.get("digest") or ""),
                    "source": "github_api",
                }
    return {
        "name": fallback_name,
        "url": GITHUB_LATEST_DOWNLOAD.format(repo=repo, asset=fallback_name),
        "digest": "",
        "source": "latest_download_fallback",
    }


def _digest_sha256(digest: str) -> str:
    value = digest.strip()
    if value.lower().startswith("sha256:"):
        return value.split(":", 1)[1].lower()
    if re.fullmatch(r"[0-9a-fA-F]{64}", value):
        return value.lower()
    return ""


def _sidecar_candidates(asset_url: str) -> list[str]:
    candidates = [asset_url + ".sha256sum", asset_url + ".sha256", asset_url + ".sha256.txt"]
    for suffix in (".tar.gz", ".zip"):
        if asset_url.endswith(suffix):
            stem = asset_url[: -len(suffix)]
            candidates.append(stem + ".sha256sum")
            candidates.append(stem + ".sha256")
    return candidates


def _sidecar_sha256(asset_url: str) -> str:
    for url in _sidecar_candidates(asset_url):
        try:
            text = _http_bytes(url).decode("utf-8", errors="replace")
        except (OSError, TimeoutError, urllib.error.URLError):
            continue
        match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
        if match:
            return match.group(1).lower()
    return ""


def _verify_dependency_download(tool: str, data: bytes, asset: dict[str, str]) -> dict[str, object]:
    actual = hashlib.sha256(data).hexdigest()
    expected = _digest_sha256(asset.get("digest", "")) or _sidecar_sha256(asset["url"])
    if not expected:
        return {
            "ok": False,
            "status": "checksum_unavailable",
            "sha256": actual,
            "reason": f"{tool} release asset did not expose a sha256 digest or sidecar",
        }
    return {
        "ok": actual == expected,
        "status": "verified" if actual == expected else "mismatch",
        "sha256": actual,
        "expected_sha256": expected,
    }


def _install_archive_binary(tool: str, archive_bytes: bytes, target: dict[str, str], install_dir: Path) -> dict[str, object]:
    binary = target["binary"]
    destination = install_dir / binary
    install_dir.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        backup = destination.with_name(destination.name + ".decretum-backup")
        shutil.copy2(destination, backup)
    with tempfile.TemporaryDirectory(prefix="decretum-dep-install-") as temp_text:
        temp = Path(temp_text)
        archive_path = temp / ("tool.zip" if target["archive"] == "zip" else "tool.tar.gz")
        archive_path.write_bytes(archive_bytes)
        if target["archive"] == "zip":
            with zipfile.ZipFile(archive_path) as archive:
                names = [name for name in archive.namelist() if Path(name).name.lower() == binary.lower()]
                if not names:
                    return {"ok": False, "reason": f"{binary} not found in {tool} archive"}
                with archive.open(names[0], "r") as source, destination.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
        else:
            with tarfile.open(archive_path, mode="r:*") as archive:
                members = [
                    member
                    for member in archive.getmembers()
                    if member.isfile() and Path(member.name).name.lower() == binary.lower()
                ]
                if not members:
                    return {"ok": False, "reason": f"{binary} not found in {tool} archive"}
                source = archive.extractfile(members[0])
                if source is None:
                    return {"ok": False, "reason": f"{binary} could not be extracted"}
                with source, destination.open("wb") as handle:
                    shutil.copyfileobj(source, handle)
    if os.name != "nt":
        destination.chmod(destination.stat().st_mode | 0o755)
    return {"ok": True, "target": str(destination)}


def _install_supercc_tool(tool: str, install_dir: Path) -> dict[str, object]:
    existing = shutil.which(tool, path=_tool_path_env(install_dir))
    if existing:
        return {
            "ok": True,
            "tool": tool,
            "changed": False,
            "available_before": True,
            "path": existing,
            "version": _run_tool_version(tool, install_dir),
        }
    repo = SUPERCC_DEPENDENCY_REPOS[tool]
    target = _tool_target(tool)
    if target.get("ok") != "true":
        return {"ok": False, "tool": tool, "changed": False, "target": target, "reason": target.get("reason")}
    asset = _select_release_asset(tool, repo, target)
    try:
        archive_bytes = _http_bytes(asset["url"])
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        return {"ok": False, "tool": tool, "changed": False, "asset": asset, "reason": f"{type(exc).__name__}:{exc}"}
    verification = _verify_dependency_download(tool, archive_bytes, asset)
    if verification.get("ok") is not True:
        return {"ok": False, "tool": tool, "changed": False, "asset": asset, "verification": verification}
    install = _install_archive_binary(tool, archive_bytes, target, install_dir)
    version = _run_tool_version(tool, install_dir) if install.get("ok") is True else {"ok": False, "status": "NOT_RUN"}
    return {
        "ok": install.get("ok") is True and version.get("ok") is True,
        "tool": tool,
        "changed": install.get("ok") is True,
        "asset": asset,
        "target": target,
        "verification": verification,
        "install": install,
        "version": version,
    }


def _install_supercc_dependencies(home: Path) -> dict[str, object]:
    install_dir = _tool_install_dir(home)
    if os.environ.get("DECRETUM_MATRIX_SKIP_SUPERCC_DEPS") == "1":
        return {
            "ok": True,
            "status": "SKIPPED",
            "reason": "DECRETUM_MATRIX_SKIP_SUPERCC_DEPS=1",
            "install_dir": str(install_dir),
            "open_source_acknowledgements": OPEN_SOURCE_ACKNOWLEDGEMENTS,
        }
    zellij = _install_supercc_tool("zellij", install_dir)
    squad = _install_supercc_tool("squad", install_dir)
    return {
        "ok": zellij.get("ok") is True and squad.get("ok") is True,
        "status": "INSTALLED_OR_PRESENT" if zellij.get("ok") is True and squad.get("ok") is True else "FAILED",
        "install_dir": str(install_dir),
        "zellij": zellij,
        "squad": squad,
        "open_source_acknowledgements": OPEN_SOURCE_ACKNOWLEDGEMENTS,
    }


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
    if sync_receipt.get("ok") is True and shared_shiguan["status"] == "SEEDED":
        supercc_dependencies = _install_supercc_dependencies(home)
    else:
        supercc_dependencies = {
            "ok": False,
            "status": "NOT_RUN",
            "reason": "runtime sync or shared Shiguan seed failed first",
            "open_source_acknowledgements": OPEN_SOURCE_ACKNOWLEDGEMENTS,
        }

    receipt_path = (
        home
        / ".agents"
        / "install-receipts"
        / "decretum-matrix"
        / f"npm-postinstall-{archive_id}.json"
    )
    installed_ok = (
        sync_receipt.get("ok") is True
        and shared_shiguan["status"] == "SEEDED"
        and supercc_dependencies.get("ok") is True
    )
    combined: dict[str, object] = {
        "schema": "decretum.npm_postinstall.v1",
        "ok": installed_ok,
        "status": "INSTALLED" if installed_ok else "FAILED",
        "archive_id": archive_id,
        "home_root": str(home),
        "sync": sync_receipt,
        "shared_shiguan": shared_shiguan,
        "supercc_dependencies": supercc_dependencies,
        "open_source_acknowledgements": OPEN_SOURCE_ACKNOWLEDGEMENTS,
        "pending_body_access": "NO",
        "body_content_reads": 0,
        "body_hashes": 0,
        "bootstrap_validation": "STRUCTURAL_ONLY",
        "service_activation_requested": False,
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
    runtime_root, runtime_identity = _select_runtime(package_root)
    if effective_argv == ["--runtime-identity"]:
        print(json.dumps(runtime_identity, ensure_ascii=False, sort_keys=True))
        return 0
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
