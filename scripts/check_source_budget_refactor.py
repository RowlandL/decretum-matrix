"""Deprecated entrypoint for the consolidated source-state budget gate."""

import sys

sys.dont_write_bytecode = True

from check_source_state_budget import main


if __name__ == "__main__":
    raise SystemExit(main())
