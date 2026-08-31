"""Manifest-derived stdio MCP facade with the CLI as a peer transport."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
import uuid

sys.dont_write_bytecode = True

from court_operation_journal import payload_sha256, write_journal
from court_public_api import has_replacement_characters
from court_public_registry import invoke_public_tool, load_public_tools, validate_public_tool_arguments
from shiguan_paths import reference_path
from stdio_encoding import configure_stdin, configure_stdio


ROOT = Path(__file__).resolve().parents[1]
CURRENT_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = (CURRENT_PROTOCOL_VERSION, LEGACY_PROTOCOL_VERSION)
PROTOCOL_META_KEY = "io.modelcontextprotocol/protocolVersion"
CLIENT_INFO_META_KEY = "io.modelcontextprotocol/clientInfo"
CLIENT_CAPABILITIES_META_KEY = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO_META_KEY = "io.modelcontextprotocol/serverInfo"
CACHE_TTL_MS = 300000


def _version() -> str:
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def _tool_result(payload: dict[str, object], *, error: bool = False) -> dict[str, object]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            }
        ],
        "structuredContent": payload,
        "isError": error,
    }


def _modern_tool_result(payload: dict[str, object], *, error: bool = False) -> dict[str, object]:
    """Add the 2026-07-28 result envelope without changing legacy callers."""

    result = _tool_result(payload, error=error)
    result["resultType"] = "complete"
    result["_meta"] = {SERVER_INFO_META_KEY: {"name": "decretum-matrix", "version": _version()}}
    return result


def _bounded_arguments(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("arguments_must_be_object")
    return value


def _write_mcp_audit(
    operation_id: str,
    tool_name: str,
    arguments: object,
    receipt: dict[str, object],
) -> None:
    """Write the tools/call audit journal entry (digest only, never raw args).

    Audit failures must never break the tool surface: the journal is best-effort
    and any error is swallowed after an attempt. Only hashes and receipts are
    stored; arguments and result bodies are never written.
    """

    try:
        root = reference_path("court-runtime")
        digest = payload_sha256({"tool": tool_name, "args": arguments})
        write_journal(
            root,
            operation_id=operation_id,
            payload_digest=digest,
            task_id="mcp",
            phase="mcp-call",
            receipt=receipt,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    except (ImportError, OSError, TypeError, ValueError):
        # best-effort audit: journal unavailability must not break calls
        return


def _audit_receipt(result: dict[str, object]) -> dict[str, object]:
    """Build the journal receipt from a call_tool result (hashes only)."""

    ok = result.get("ok") is True
    api = result.get("api")
    if ok and isinstance(api, dict):
        result_sha256 = payload_sha256(api)
    else:
        result_sha256 = None
    return {"ok": ok, "result_sha256": result_sha256}


def call_tool(name: str, arguments: object = None, *, modern: bool = False) -> dict[str, object]:
    tools = load_public_tools()
    tool = tools.get(name)
    if tool is None:
        result = {"ok": False, "problem": f"tool_not_allowed:{name}"}
        return _modern_tool_result(result, error=True) if modern else _tool_result(result, error=True)
    try:
        api_result = invoke_public_tool(tool, arguments)
    except (ImportError, TypeError, ValueError) as exc:
        result = {"ok": False, "problem": str(exc)}
        return _modern_tool_result(result, error=True) if modern else _tool_result(result, error=True)
    result = {
        "ok": True,
        "tool": name,
        "command_id": tool.command_id,
        "api": api_result,
        "dry_run": tool.dry_run,
        "write_enabled": False,
    }
    if name == "court.status":
        result["transport_corruption"] = has_replacement_characters(api_result)
    return _modern_tool_result(result) if modern else _tool_result(result)


def list_tools() -> list[dict[str, object]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
            "annotations": {"readOnlyHint": True, "destructiveHint": False},
        }
        for tool in load_public_tools().values()
    ]


def _response(request_id: object, result: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _unsupported_version(request_id: object, requested: object) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32022,
            "message": "Unsupported protocol version",
            "data": {
                "supported": list(SUPPORTED_PROTOCOL_VERSIONS),
                "requested": requested,
                "path": "modern_per_request",
            },
        },
    }


def _modern_meta(message: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None, dict[str, object] | None]:
    params = message.get("params")
    if not isinstance(params, dict):
        return None, None, _error(message.get("id"), -32602, "Modern requests require params._meta")
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return None, None, _error(message.get("id"), -32602, "Modern requests require params._meta")
    version = meta.get(PROTOCOL_META_KEY)
    if not isinstance(version, str):
        return None, None, _error(message.get("id"), -32602, f"Missing _meta.{PROTOCOL_META_KEY}")
    if version != CURRENT_PROTOCOL_VERSION:
        return version, meta, _unsupported_version(message.get("id"), version)
    if not isinstance(meta.get(CLIENT_CAPABILITIES_META_KEY), dict):
        return version, meta, _error(message.get("id"), -32602, f"Missing _meta.{CLIENT_CAPABILITIES_META_KEY}")
    if CLIENT_INFO_META_KEY in meta:
        client_info = meta.get(CLIENT_INFO_META_KEY)
        if not isinstance(client_info, dict):
            return version, meta, _error(message.get("id"), -32602, f"Invalid _meta.{CLIENT_INFO_META_KEY}")
        if not isinstance(client_info.get("name"), str) or not client_info.get("name", "").strip():
            return version, meta, _error(message.get("id"), -32602, f"Invalid _meta.{CLIENT_INFO_META_KEY}.name")
        if not isinstance(client_info.get("version"), str) or not client_info.get("version", "").strip():
            return version, meta, _error(message.get("id"), -32602, f"Invalid _meta.{CLIENT_INFO_META_KEY}.version")
    return version, meta, None


def _validate_cursor(message: dict[str, Any]) -> dict[str, object] | None:
    params = message.get("params")
    if not isinstance(params, dict) or "cursor" not in params:
        return None
    cursor = params.get("cursor")
    if cursor == "":
        return None
    return _error(message.get("id"), -32602, "This server does not paginate tools/list; cursor must be empty")


def _discover_result() -> dict[str, object]:
    return {
        "resultType": "complete",
        "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
        "capabilities": {"tools": {}},
        "_meta": {
            SERVER_INFO_META_KEY: {
                "name": "decretum-matrix",
                "version": _version(),
            }
        },
        "instructions": "Use only the read-only tools exposed by this server. Archive and memory operations are dry-run boundaries.",
        "ttlMs": CACHE_TTL_MS,
        "cacheScope": "public",
    }


def handle(message: dict[str, Any], state: dict[str, object]) -> dict[str, object] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if request_id is None:
        return None
    if method == "server/discover":
        negotiated_version, _meta, error = _modern_meta(message)
        if error is not None:
            return error
        return _response(request_id, _discover_result())
    if method == "initialize":
        params = message.get("params")
        if not isinstance(params, dict):
            return _error(request_id, -32602, "initialize params must be an object")
        requested = params.get("protocolVersion")
        if not isinstance(requested, str) or not requested.strip():
            return _error(request_id, -32602, "initialize params.protocolVersion is required")
        if not isinstance(params.get("capabilities"), dict):
            return _error(request_id, -32602, "initialize params.capabilities is required")
        if not isinstance(params.get("clientInfo"), dict):
            return _error(request_id, -32602, "initialize params.clientInfo is required")
        # Legacy MCP negotiation: echo the requested legacy version when
        # supported, otherwise answer with the latest legacy version this
        # dual-era server can operate through the initialize handshake.
        negotiated = (
            requested
            if requested == LEGACY_PROTOCOL_VERSION
            else LEGACY_PROTOCOL_VERSION
        )
        state["legacy_initialized"] = True
        state["protocol_version"] = negotiated
        return _response(
            request_id,
            {
                "protocolVersion": negotiated,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "decretum-matrix", "version": _version()},
            },
        )
    params = message.get("params")
    # An initialize handshake owns the protocol mode for the process. Standard
    # legacy clients may still attach request metadata such as progressToken.
    if state.get("legacy_initialized"):
        modern = False
    # Modern 2026 requests are stateless: every request carries its own
    # protocol/client metadata and never relies on an earlier handshake.
    elif isinstance(params, dict) and "_meta" in params:
        negotiated_version, _meta, error = _modern_meta(message)
        if error is not None:
            return error
        modern = True
    else:
        negotiated_version, _meta, error = _modern_meta(message)
        return error if error is not None else _error(request_id, -32602, "Modern requests require params._meta")
    if method == "tools/list":
        cursor_error = _validate_cursor(message)
        if cursor_error is not None:
            return cursor_error
        result: dict[str, object] = {"tools": list_tools()}
        if modern:
            result.update(
                {
                    "resultType": "complete",
                    "_meta": {SERVER_INFO_META_KEY: {"name": "decretum-matrix", "version": _version()}},
                    "ttlMs": CACHE_TTL_MS,
                    "cacheScope": "public",
                }
            )
        return _response(request_id, result)
    if method == "tools/call":
        params = message.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return _error(request_id, -32602, "Invalid tools/call params")
        tools = load_public_tools()
        tool = tools.get(params["name"])
        arguments = params.get("arguments")
        operation_id = str(uuid.uuid4())
        if tool is None:
            _write_mcp_audit(
                operation_id,
                str(params.get("name") or ""),
                arguments,
                {"ok": False, "result_sha256": None, "error": "tool_not_allowed"},
            )
            return _error(request_id, -32602, f"Unknown tool: {params['name']}")
        try:
            validate_public_tool_arguments(tool, arguments)
        except (TypeError, ValueError) as exc:
            _write_mcp_audit(
                operation_id,
                tool.name,
                arguments,
                {"ok": False, "result_sha256": None, "error": str(exc)},
            )
            return _error(request_id, -32602, str(exc))
        result = call_tool(params["name"], arguments, modern=modern)
        _write_mcp_audit(operation_id, tool.name, arguments, _audit_receipt(result))
        return _response(request_id, result)
    return _error(request_id, -32601, f"Method not found: {method}")


def main() -> int:
    configure_stdio()
    configure_stdin()
    state = {"legacy_initialized": False}
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        else:
            if not isinstance(message, dict):
                response = _error(None, -32600, "Invalid Request")
            elif message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
                response = _error(message.get("id"), -32600, "Invalid Request")
            elif "id" not in message:
                response = None if message["method"].startswith("notifications/") else _error(None, -32600, "Invalid Request")
            elif message.get("id") is None or isinstance(message.get("id"), bool) or not isinstance(message.get("id"), (str, int, float)):
                response = _error(None, -32600, "Invalid Request")
            else:
                try:
                    response = handle(message, state)
                except Exception as exc:  # noqa: BLE001 - JSON-RPC server must fail closed per request.
                    response = _error(message.get("id"), -32603, str(exc))
        if response is not None:
            # JSON escapes keep stdio safe on Windows hosts whose active code page is not UTF-8.
            print(json.dumps(response, ensure_ascii=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
