"""Report the optional advisory Git hook boundary for Decretum Matrix.

This script is intentionally not a Git hook installer. A local operator may call
it from a hook to display or enqueue a refresh hint, but it never produces
closeout, memory, release, or dispatch authority.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

sys.dont_write_bytecode = True


SCHEMA = "decretum.hooks_advisory.v1"
AUTHORIZED_EVENTS = ("manual", "pre-commit", "post-commit", "post-merge", "post-checkout")
FORBIDDEN_AUTHORITY_ACTIONS = (
    "archive_checkpoint",
    "closeout_identity",
    "memory_write",
    "release_or_publish",
    "menxia_verdict",
    "host_dispatch",
)


def build_report(event: str, marker: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "schema_version": 1,
        "ok": True,
        "event": event,
        "marker": marker,
        "advisory_only": True,
        "authoritative_gate": False,
        "installs_git_hook": False,
        "requires_core_hooks_path": False,
        "marker_write_enabled": False,
        "writes_closeout": False,
        "writes_memory": False,
        "writes_release": False,
        "authority_path": "court_cli_or_runtime_receipt_only",
        "forbidden_authority_actions": list(FORBIDDEN_AUTHORITY_ACTIONS),
        "message": "Optional hook integrations may only surface a local advisory refresh hint.",
    }


def render_text(report: dict[str, Any]) -> str:
    return (
        "HOOK_ADVISORY "
        f"event={report['event']} "
        f"marker={report['marker'] or 'none'} "
        "advisory_only=true "
        "authoritative_gate=false"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", choices=AUTHORIZED_EVENTS, default="manual")
    parser.add_argument("--marker", default="")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)

    report = build_report(args.event, args.marker)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
