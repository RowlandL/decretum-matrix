#!/usr/bin/env python
"""Register the current court-capability-router runtime as an active agente."""

from __future__ import annotations

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
