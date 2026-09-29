#!/usr/bin/env python3
"""Install-source entry point bundled with the published package.

The published npm package carries the install driver so that a published
artifact is a self-sufficient install source
(``.scratch/install-from-published-artifact/spec.md`` D1).

These modules are install tooling: they are deliberately absent from the
install-projection allowlist and must never be projected into an installed
copy (``references/validation-packaging.md:3``).
"""

from __future__ import annotations

import argparse
import atexit
import json
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_ROOT = PACKAGE_ROOT / "scripts"
RELEASE_ROOT = PACKAGE_ROOT / "release"

# 驱动模块：活动投影刻意排除安装工具，因此它们只存在于包内。
INSTALL_PAYLOAD_SCRIPTS_MEMBERS = (
    "scripts/install_current_agent_copy.py",
    "scripts/install_projection_renderer.py",
    "scripts/fix_decretum_matrix.py",
    "scripts/commands/fix_decretum_matrix.py",
    "scripts/court_diagnostics.py",
    "scripts/commands/release_payload_manifest.py",
    "scripts/release_payload_manifest.py",
    "scripts/commands/package_skill.py",
    "scripts/package_skill.py",
    "scripts/check_active_copy_hashes.py",
    "scripts/checks/check_active_copy_hashes.py",
    "scripts/checks/check_codex_agent_roles.py",
    "references/manifests/install-projection.v1.json",
)

INSTALL_PAYLOAD_MEMBERS = (
    "bin/install-runtime.py",
    *INSTALL_PAYLOAD_SCRIPTS_MEMBERS,
)


def payload_problems() -> list[str]:
    """Report why this package cannot act as an install source."""

    problems: list[str] = []
    if not SCRIPTS_ROOT.is_dir():
        problems.append(f"install payload directory missing: {SCRIPTS_ROOT}")
        return problems
    for relative in INSTALL_PAYLOAD_MEMBERS:
        if not (PACKAGE_ROOT / relative).is_file():
            problems.append(f"install payload member missing: {relative}")
    if not any(RELEASE_ROOT.glob("*.zip")):
        problems.append(f"release payload missing under: {RELEASE_ROOT}")
    return problems


def _package_identity() -> dict[str, object]:
    """Read the published identity this package declares, if any."""

    try:
        package = json.loads((PACKAGE_ROOT / "package.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    identity = package.get("decretumMatrix")
    return identity if isinstance(identity, dict) else {}


def _driver_argv(forwarded: list[str], source_root: Path) -> list[str]:
    """Point the install driver at this package as the candidate install source."""

    identity = _package_identity()
    release_label = str(identity.get("releaseLabel") or "")
    source = identity.get("source")
    commit = str(source.get("commit") or "") if isinstance(source, dict) else ""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    argv = [
        forwarded[0],
        "--candidate-package-root",
        str(PACKAGE_ROOT),
        "--caller-cwd",
        str(Path.cwd()),
        "--source-root",
        str(source_root),
    ]
    if release_label:
        argv += ["--transaction-id", f"{release_label}-package-install-{stamp}"]
    if release_label and commit:
        argv += ["--installation-id", f"{release_label}-{commit[:12]}"]
    return argv + forwarded[1:]


def _materialize_install_source() -> Path:
    """Extract the install source this package embeds, then merge the driver into it.

    The archive ships the projection closure (court_diagnostics and friends) but
    deliberately not the install tooling, which only lives in the package. Two
    separate scripts roots cannot share sys.path -- the commands package would
    resolve to only one of them -- so the driver is copied into the materialized
    source to yield one coherent install source.
    """

    archives = sorted(RELEASE_ROOT.glob("*.zip"))
    if len(archives) != 1:
        raise SystemExit("install-runtime: expected exactly one release archive")
    staging = Path(tempfile.mkdtemp(prefix="decretum-install-source-"))
    atexit.register(shutil.rmtree, staging, True)
    with zipfile.ZipFile(archives[0]) as archive:
        archive.extractall(staging)
    roots = sorted(item for item in staging.iterdir() if item.is_dir())
    if len(roots) != 1:
        raise SystemExit("install-runtime: unexpected archive layout")
    source_root = roots[0]
    for relative in INSTALL_PAYLOAD_SCRIPTS_MEMBERS:
        origin = PACKAGE_ROOT / relative
        if not origin.is_file():
            raise SystemExit(f"install-runtime: install payload member missing: {relative}")
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, destination)
    return source_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="install-runtime")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="verify that the bundled install payload is complete",
    )
    parsed, forwarded = parser.parse_known_args(
        sys.argv[1:] if argv is None else argv
    )

    problems = payload_problems()
    if parsed.self_check:
        for problem in problems:
            print(f"install-runtime: {problem}", file=sys.stderr)
        if not problems:
            print(f"install-runtime payload OK: {PACKAGE_ROOT}")
        return 1 if problems else 0

    if problems:
        for problem in problems:
            print(f"install-runtime: {problem}", file=sys.stderr)
        return 1
    if not forwarded or forwarded[0].startswith("-"):
        forwarded = ["update", *forwarded]
    source_root = _materialize_install_source()
    install_scripts = source_root / "scripts"
    if str(install_scripts) not in sys.path:
        sys.path.insert(0, str(install_scripts))
    from commands import fix_decretum_matrix as driver

    return driver.main(_driver_argv(forwarded, source_root))


if __name__ == "__main__":
    raise SystemExit(main())
