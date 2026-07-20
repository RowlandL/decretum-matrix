"""Neutral standing-office configuration pointer shared across runtimes."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OFFICE_CONFIG_RELATIVE_PATH = "references/manifests/court-dispatch-hierarchy.v1.json"


@lru_cache(maxsize=16)
def _neutral_office_config(base_text: str) -> tuple[str, int, str, str, int]:
    base = Path(base_text)
    path = base / OFFICE_CONFIG_RELATIVE_PATH
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict) or value.get("schema") != "court.dispatch_hierarchy.v1":
        raise ValueError("neutral_office_config_schema_invalid")
    hierarchy_sha256 = hashlib.sha256(payload).hexdigest()
    profiles: list[dict[str, str]] = []
    total_bytes = len(payload)
    for profile in sorted((base / "agents" / "standing-officials").glob("*.toml")):
        profile_payload = profile.read_bytes()
        total_bytes += len(profile_payload)
        profiles.append(
            {
                "path": profile.relative_to(base).as_posix(),
                "sha256": hashlib.sha256(profile_payload).hexdigest(),
            }
        )
    if not profiles:
        raise ValueError("neutral_office_profiles_missing")
    profile_bytes = json.dumps(
        profiles,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    profiles_sha256 = hashlib.sha256(profile_bytes).hexdigest()
    composite = json.dumps(
        {
            "hierarchy_sha256": hierarchy_sha256,
            "profiles_sha256": profiles_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return (
        hashlib.sha256(composite).hexdigest(),
        total_bytes,
        hierarchy_sha256,
        profiles_sha256,
        len(profiles),
    )


def neutral_office_config(root: Path | str = ROOT) -> dict[str, object]:
    digest, size, hierarchy_digest, profiles_digest, profile_count = _neutral_office_config(str(root))
    return {
        "schema": "court.neutral_office_config.pointer.v1",
        "path": OFFICE_CONFIG_RELATIVE_PATH,
        "sha256": digest,
        "bytes": size,
        "hierarchy_sha256": hierarchy_digest,
        "standing_profiles": {
            "path": "agents/standing-officials",
            "sha256": profiles_digest,
            "count": profile_count,
        },
    }
