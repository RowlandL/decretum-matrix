"""Public Decretum Matrix command-line entrypoint."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from court_cli_registry import main


if __name__ == "__main__":
    sys.exit(main())
