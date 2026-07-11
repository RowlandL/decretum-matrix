"""Security helpers for the Shiguan local/LAN service."""

from __future__ import annotations

import os


ADMIN_TOKEN_ENV = "SHIGUAN_ADMIN_TOKEN"
MAX_JSON_BODY_BYTES = int(os.environ.get("SHIGUAN_MAX_JSON_BODY_BYTES", str(8 * 1024 * 1024)))


def client_is_local(address: str) -> bool:
    return address.startswith("127.") or address in {"::1", "localhost"}


def admin_auth_public_state() -> dict[str, object]:
    return {
        "required_for_lan": True,
        "token_env": ADMIN_TOKEN_ENV,
        "max_json_body_bytes": MAX_JSON_BODY_BYTES,
    }
