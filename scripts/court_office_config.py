"""Neutral standing-office configuration pointer shared across runtimes."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# 2026-10-05 F22: one bounded business block in the native host message needs 52
# bytes more than the old ceiling; +512 keeps the fixed ceiling while leaving the
# business assignment room to describe the bounded scope (no unbounded growth).
ENTRY_PRELOAD_BUDGET_BYTES = 20 * 1024 + 512
ORDINARY_NATIVE_REQUIRED_HEADROOM_BYTES = 768
ORDINARY_NATIVE_HEADROOM_ROLES = frozenset(
    {
        "zhongshu", "menxia", "shangshu",
        "libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu",
    }
)
OFFICE_CONFIG_RELATIVE_PATH = "references/manifests/court-dispatch-hierarchy.v1.json"


def neutral_office_config(root: Path | str = ROOT) -> dict[str, object]:
    """Return portable pointers, not a pre-admission profile inventory.

    The selected office's existing preload/hierarchy validator reads and
    validates its content at use time. Runtime selection has no such need.
    ``root`` remains accepted for callers of the original pointer interface.
    """
    return {
        "schema": "court.neutral_office_config.pointer.v1",
        "path": OFFICE_CONFIG_RELATIVE_PATH,
        "standing_profiles": {
            "path": "agents/standing-officials",
        },
    }
