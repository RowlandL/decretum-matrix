#!/usr/bin/env python3
"""Public doctor command adapter."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from court_diagnostics import command_main


def main(argv: list[str] | None = None) -> int:
    return command_main("doctor", argv)


if __name__ == "__main__":
    raise SystemExit(main())
