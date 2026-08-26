"""Emit bounded Codex lifecycle context for Decretum Matrix.

The hook is intentionally advisory. It never writes the court ledger, memory,
Git configuration, MCP configuration, or closeout receipts.
"""

from __future__ import annotations

import argparse
import json
import sys

sys.dont_write_bytecode = True


EVENTS = ("SessionStart", "UserPromptSubmit")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", choices=EVENTS, required=True)
    args = parser.parse_args(argv)
    message = (
        "Decretum Matrix integration is active. CLI and MCP are peer transports "
        "over the shared public API; use the registered mcp__decretum_matrix "
        "read-only tools when structured court status or Shiguan evidence is needed. "
        "Use archive-checkpoint receipts as the sole source of decree numbers."
    )
    print(
        json.dumps(
            {
                "priority": "INFO",
                "event": args.event,
                "advisory_only": True,
                "authoritative_gate": False,
                "message": message,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
