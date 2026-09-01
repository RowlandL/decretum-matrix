

#!/usr/bin/env python
"""Register the current Decretum Matrix runtime as an active agente."""

from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
import json
import sys

sys.dont_write_bytecode = True

from shiguan_paths import ensure_shared_seed, register_agent_presence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-agent", default="", help="Override detected agent id, e.g. codex or hermes.")
    parser.add_argument("--event", default="manual-register")
    args = parser.parse_args()

    ensure_shared_seed()
    record = register_agent_presence(args.event, args.source_agent or None)
    print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

