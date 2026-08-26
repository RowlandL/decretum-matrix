"""Small host-neutral helpers for subprocess-safe UTF-8 output."""

from __future__ import annotations

import sys


def configure_stdio() -> None:
    """Keep command output UTF-8 even when Windows uses an ACP console."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            # Embedded callers may provide a stream that cannot be reconfigured.
            continue


def configure_stdin() -> None:
    """Force JSON-RPC input to UTF-8 on hosts with a non-UTF-8 ACP."""

    reconfigure = getattr(sys.stdin, "reconfigure", None)
    if not callable(reconfigure):
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        # Embedded callers may provide a stream that cannot be reconfigured.
        return
