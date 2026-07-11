"""Command-line UI for the local /court runtime ledger."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from court_runtime import main


if __name__ == "__main__":
    sys.exit(main())
