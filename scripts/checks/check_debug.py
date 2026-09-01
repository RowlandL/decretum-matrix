

#!/usr/bin/env python3
"""Public debug command adapter."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import sys

sys.dont_write_bytecode = True

from court_diagnostics import command_main


def main(argv: list[str] | None = None) -> int:
    return command_main("debug", argv)


if __name__ == "__main__":
    raise SystemExit(main())

