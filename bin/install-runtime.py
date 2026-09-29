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
import sys
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="install-runtime")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="verify that the bundled install payload is complete",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    problems = payload_problems()
    if args.self_check:
        for problem in problems:
            print(f"install-runtime: {problem}", file=sys.stderr)
        if not problems:
            print(f"install-runtime payload OK: {PACKAGE_ROOT}")
        return 1 if problems else 0

    if problems:
        for problem in problems:
            print(f"install-runtime: {problem}", file=sys.stderr)
        return 1
    parser.error(
        "no install operation selected; see "
        ".scratch/install-from-published-artifact/issues/"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
