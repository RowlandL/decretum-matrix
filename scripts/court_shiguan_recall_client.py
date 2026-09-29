"""Read-only client for the local Shiguan recall advisory service.

The recall engine needs torch + a 322M encoder, so it runs as a local read-only
service (default http://127.0.0.1:8767) instead of being imported into the court
CLI/MCP process. This client is stdlib-only and fails closed with an actionable
problem code when the service is not running.

Contract:
  - read_only: never writes Shiguan data, never mutates the taxonomy
  - advisory: results carry authority=advisory and execution_authority=false
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

sys.dont_write_bytecode = True


DEFAULT_URL = "http://127.0.0.1:8767"
SERVICE_ENV = "SHIGUAN_RECALL_URL"
TIMEOUT_ENV = "SHIGUAN_RECALL_TIMEOUT"
START_HINT = (
    "start the local recall service first, then retry: run serve_http.py --port 8767 "
    "from training/laya-shiguan/service (see its README)"
)


def _base_url() -> str:
    return str(os.environ.get(SERVICE_ENV) or DEFAULT_URL).rstrip("/")


def _timeout() -> float:
    try:
        return max(1.0, float(os.environ.get(TIMEOUT_ENV) or 60))
    except ValueError:
        return 60.0


def _request(path: str, payload: dict | None = None) -> dict[str, object]:
    url = f"{_base_url()}{path}"
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=_timeout()) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        return {"ok": False, "problem": f"recall_service_http_{exc.code}", "detail": detail}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "problem": "recall_service_unavailable", "detail": str(exc)[:400], "hint": START_HINT}
    except json.JSONDecodeError as exc:
        return {"ok": False, "problem": "recall_service_bad_json", "detail": str(exc)[:200]}
    if not isinstance(body, dict):
        return {"ok": False, "problem": "recall_service_bad_payload"}
    return body


def recall(state: str, k: int = 5, same_topic: bool = False) -> dict[str, object]:
    """Return the k most similar historical Shiguan records (advisory only)."""

    if not isinstance(state, str) or not state.strip():
        return {"ok": False, "problem": "state_required"}
    bounded_k = max(1, min(int(k), 20))
    body = _request("/recall", {"state": state, "k": bounded_k, "same_topic": bool(same_topic)})
    if body.get("ok") is not True:
        return body
    body["advisory"] = {
        "authority": "advisory",
        "execution_authority": False,
        "source": f"laya-recall@{_base_url()}",
        "note": "对照参考；不得据以写入史馆或替代门下裁定",
    }
    return body


def stats() -> dict[str, object]:
    """Return recall service and index statistics."""

    body = _request("/stats")
    if body.get("ok") is not True:
        return body
    body["advisory"] = {"authority": "advisory", "execution_authority": False, "source": f"laya-recall@{_base_url()}"}
    return body
