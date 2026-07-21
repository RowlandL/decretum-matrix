"""Neutral standing-office configuration pointer shared across runtimes."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OFFICE_CONFIG_RELATIVE_PATH = "references/manifests/court-dispatch-hierarchy.v1.json"


@lru_cache(maxsize=16)
def _neutral_office_config(base_text: str) -> tuple[int, int]:
    base = Path(base_text)
    path = base / OFFICE_CONFIG_RELATIVE_PATH
    payload = path.read_text(encoding="utf-8")
    value = json.loads(payload)
    if not isinstance(value, dict) or value.get("schema") != "court.dispatch_hierarchy.v1":
        raise ValueError("neutral_office_config_schema_invalid")
    profiles = sorted((base / "agents" / "standing-officials").glob("*.toml"))
    if not profiles:
        raise ValueError("neutral_office_profiles_missing")
    total_bytes = len(payload.encode("utf-8"))
    total_bytes += sum(len(profile.read_bytes()) for profile in profiles)
    return total_bytes, len(profiles)


def neutral_office_config(root: Path | str = ROOT) -> dict[str, object]:
    size, profile_count = _neutral_office_config(str(root))
    return {
        "schema": "court.neutral_office_config.pointer.v1",
        "path": OFFICE_CONFIG_RELATIVE_PATH,
        "bytes": size,
        "standing_profiles": {
            "path": "agents/standing-officials",
            "count": profile_count,
        },
    }
