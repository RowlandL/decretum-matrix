"""Verify and repair Windows bare-``codex`` command resolution.

Windows ``CreateProcess`` does not execute npm ``.cmd`` or ``.ps1`` shims when
the caller uses ``subprocess.run(["codex", ...])``.  A stale desktop-bundled
``codex.exe`` later on PATH can therefore win unexpectedly.  This module puts
an executable link next to the first npm shim and requires it to share file
identity with the verified npm-native Codex binary.

Conflicting executable entries are migrated to an append-only host backup
before repair.  Nothing is deleted.
"""



from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

sys.dont_write_bytecode = True

from court_platform import user_config_base
from shiguan_paths import references_root


VERSION_RE = re.compile(r"^codex-cli\s+([^\s]+)$")


def parse_codex_version(output: str) -> str:
    text = str(output or "").strip()
    match = VERSION_RE.fullmatch(text)
    if not match:
        raise ValueError("unexpected Codex version output")
    return match.group(1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_native(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    info = resolved.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("native Codex path must be a strict regular file")
    return resolved


def default_native_path() -> Path:
    return user_config_base() / "npm" / "node_modules" / "@openai" / "codex" / "node_modules" / "@openai" / "codex-win32-x64" / "vendor" / "x86_64-pc-windows-msvc" / "bin" / "codex.exe"


def default_front_path() -> Path:
    for raw in os.environ.get("PATH", "").split(os.pathsep):
        directory = Path(raw.strip('"')) if raw.strip('"') else None
        if directory is None:
            continue
        if (directory / "codex.cmd").is_file() or (directory / "codex.ps1").is_file():
            return directory / "codex.exe"
    raise FileNotFoundError("no npm Codex shim directory found on PATH")


def _same_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except (FileNotFoundError, OSError):
        return False


def build_resolution_report(
    *,
    native_path: Path,
    front_path: Path,
    native_version_output: str,
    front_version_output: str,
    bare_version_output: str,
    which_path: Path | None,
) -> dict[str, object]:
    native = _strict_native(native_path)
    front = front_path.expanduser().absolute()
    if not front.is_file():
        raise FileNotFoundError(f"front Codex executable missing: {front}")
    native_sha = sha256_file(native)
    front_sha = sha256_file(front)
    native_version = parse_codex_version(native_version_output)
    front_version = parse_codex_version(front_version_output)
    bare_version = parse_codex_version(bare_version_output)
    same_identity = _same_file(native, front)
    which_identity = bool(which_path and _same_file(native, Path(which_path)))
    hash_equal = native_sha == front_sha
    versions_equal = native_version == front_version == bare_version
    return {
        "schema": "court.codex_host_resolution.v1",
        "healthy": same_identity and which_identity and hash_equal and versions_equal,
        "native_path": str(native),
        "front_path": str(front),
        "which_path": str(which_path) if which_path else None,
        "native_version": native_version,
        "front_version": front_version,
        "bare_version": bare_version,
        "native_sha256": native_sha,
        "front_sha256": front_sha,
        "same_file_identity": same_identity,
        "which_matches_native": which_identity,
        "hash_equal": hash_equal,
        "versions_equal": versions_equal,
    }


def ensure_front_link(
    *,
    native_path: Path,
    front_path: Path,
    backup_root: Path,
    prefer_symlink: bool = True,
) -> dict[str, object]:
    native = _strict_native(native_path)
    front = front_path.expanduser().absolute()
    front.parent.mkdir(parents=True, exist_ok=True)
    if _same_file(native, front):
        return {
            "changed": False,
            "link_kind": "existing",
            "front_path": str(front),
            "native_path": str(native),
            "migrated_path": None,
        }

    migrated: Path | None = None
    if os.path.lexists(front):
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
        migrated = backup_root.expanduser().absolute() / stamp / front.name
        migrated.parent.mkdir(parents=True, exist_ok=False)
        front.replace(migrated)

    link_kind = ""
    try:
        if prefer_symlink:
            try:
                os.symlink(native, front)
                link_kind = "symlink"
            except OSError:
                link_kind = ""
        if not link_kind:
            os.link(native, front)
            link_kind = "hardlink"
    except OSError:
        if migrated is not None and not os.path.lexists(front):
            migrated.replace(front)
        raise

    if not _same_file(native, front):
        raise RuntimeError("Codex front executable does not share native file identity")
    return {
        "changed": True,
        "link_kind": link_kind,
        "front_path": str(front),
        "native_path": str(native),
        "migrated_path": str(migrated) if migrated else None,
    }


def _version_output(executable: str | Path) -> str:
    completed = subprocess.run(
        [str(executable), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("Codex version probe failed")
    return completed.stdout


def inspect_live(native_path: Path, front_path: Path) -> dict[str, object]:
    which = shutil.which("codex")
    return build_resolution_report(
        native_path=native_path,
        front_path=front_path,
        native_version_output=_version_output(native_path),
        front_version_output=_version_output(front_path),
        bare_version_output=_version_output("codex"),
        which_path=Path(which) if which else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-path", type=Path, default=default_native_path())
    parser.add_argument("--front-path", type=Path)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--no-symlink", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    front = args.front_path or default_front_path()
    backup = args.backup_root or (references_root() / "host-capability-backups" / "codex-command-resolution")
    repair_result = None
    if args.repair:
        repair_result = ensure_front_link(
            native_path=args.native_path,
            front_path=front,
            backup_root=backup,
            prefer_symlink=not args.no_symlink,
        )
    report = inspect_live(args.native_path, front)
    report["repair"] = repair_result
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

