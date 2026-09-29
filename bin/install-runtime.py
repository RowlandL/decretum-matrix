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
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_ROOT = PACKAGE_ROOT / "scripts"
RELEASE_ROOT = PACKAGE_ROOT / "release"

INSTALL_PAYLOAD_MEMBERS = (
    "scripts/install_current_agent_copy.py",
    "scripts/install_projection_renderer.py",
    "scripts/fix_decretum_matrix.py",
    "scripts/commands/fix_decretum_matrix.py",
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


def _driver_argv(forwarded: list[str]) -> list[str]:
    """Point the install driver at this package as the candidate install source."""

    identity = _package_identity()
    release_label = str(identity.get("releaseLabel") or "")
    source = identity.get("source")
    commit = str(source.get("commit") or "") if isinstance(source, dict) else ""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    argv = [
        "update",
        "--candidate-package-root",
        str(PACKAGE_ROOT),
        "--caller-cwd",
        str(Path.cwd()),
    ]
    if release_label:
        argv += ["--transaction-id", f"{release_label}-package-install-{stamp}"]
    if release_label and commit:
        argv += ["--installation-id", f"{release_label}-{commit[:12]}"]
    return argv + forwarded


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
    if str(SCRIPTS_ROOT) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_ROOT))
    from commands import fix_decretum_matrix as driver

    return driver.main(_driver_argv(forwarded))


if __name__ == "__main__":
    raise SystemExit(main())
