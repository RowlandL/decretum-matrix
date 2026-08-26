"""Shared read-only public API used by both CLI and MCP adapters.

This module deliberately contains no transport code and no second ledger. The
CLI and MCP facades call these functions as peers, so neither adapter shells
out to the other or inherits the other's encoding boundary.
"""

from __future__ import annotations

from argparse import Namespace
import json
import sys
from typing import Any

sys.dont_write_bytecode = True

from court_runtime import status_payload
from query_shiguan_index import load_entries, select_query_matches


def _api_result(payload: object, *, stderr: str = "", exit_status: int = 0) -> dict[str, object]:
    return {
        "exit_status": exit_status,
        "stdout": payload,
        "stderr": stderr,
    }


def court_status(limit: int = 12) -> dict[str, object]:
    """Return the canonical court status projection without a subprocess."""

    bounded_limit = max(1, min(int(limit), 100))
    return _api_result(status_payload(Namespace(limit=bounded_limit)))


def court_command_help() -> dict[str, object]:
    """Return the public court help projection without invoking the CLI."""

    from court_cli_registry import render_group_help

    return _api_result({"command": "court help", "help": render_group_help("court")})


def shiguan_query(terms: list[str] | None = None, limit: int = 5) -> dict[str, object]:
    """Return Shiguan query results through the shared query implementation."""

    bounded_limit = max(1, min(int(limit), 20))
    entries = load_entries()
    matches = select_query_matches(entries, [term for term in (terms or []) if term.strip()])
    return _api_result(matches[:bounded_limit])


def shiguan_archive_dry_run() -> dict[str, object]:
    """Expose the archive boundary without creating a checkpoint."""

    return _api_result(
        {
            "dry_run": True,
            "write_enabled": False,
            "command": "archive-checkpoint",
        }
    )


def memory_scan() -> dict[str, object]:
    """Expose the public memory-scan boundary without reading private bodies."""

    return _api_result(
        {
            "dry_run": True,
            "write_enabled": False,
            "private_body_access": False,
            "command": "internal-memory-shiguan-bridge",
        }
    )


def has_replacement_characters(value: object) -> bool:
    """Detect transport corruption in a structured public result."""

    return "\ufffd" in json.dumps(value, ensure_ascii=False)
