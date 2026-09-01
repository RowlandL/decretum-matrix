"""Deprecated entrypoint for the consolidated source-state budget gate."""

import sys

sys.dont_write_bytecode = True

from check_source_state_budget import main


if __name__ == "__main__":
    raise SystemExit(main())




# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)
