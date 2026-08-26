"""Validate the Decretum Matrix stdio MCP facade against modern and legacy wire shapes."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

sys.dont_write_bytecode = True

from court_public_api import court_command_help, court_status, memory_scan, shiguan_archive_dry_run, shiguan_query
from court_public_registry import load_public_tools
import court_mcp_server


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "court_mcp_server.py"
EXPECTED_TOOLS = {
    "court.status",
    "court.command_help",
    "shiguan.query",
    "shiguan.archive_dry_run",
    "memory.scan",
}
CURRENT_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
PROTOCOL_META_KEY = "io.modelcontextprotocol/protocolVersion"
CLIENT_INFO_META_KEY = "io.modelcontextprotocol/clientInfo"
CLIENT_CAPABILITIES_META_KEY = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO_META_KEY = "io.modelcontextprotocol/serverInfo"
EXPECTED_COMMAND_IDS = {
    "court.status": "court.court-runtime",
    "court.command_help": "court.court-runtime",
    "shiguan.query": "shiguan.query-shiguan-index",
    "shiguan.archive_dry_run": "shiguan.archive-checkpoint",
    "memory.scan": "shiguan.internal-memory-shiguan-bridge",
}


def _start() -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-B", str(SERVER)],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _close(proc: subprocess.Popen[str]) -> None:
    if proc.stdin is not None:
        proc.stdin.close()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _rpc(proc: subprocess.Popen[str], request: dict[str, Any]) -> dict[str, Any]:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        raise AssertionError(f"mcp_server_no_response:{stderr[:400]}")
    response = json.loads(line)
    if not isinstance(response, dict):
        raise AssertionError("mcp_response_not_object")
    return response


def _raw_rpc(proc: subprocess.Popen[str], raw: str) -> dict[str, Any]:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(raw + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        raise AssertionError(f"mcp_server_no_response:{stderr[:400]}")
    response = json.loads(line)
    if not isinstance(response, dict):
        raise AssertionError("mcp_response_not_object")
    return response


def _modern_meta(client_name: str = "decretum-modern-wire-probe") -> dict[str, object]:
    return {
        PROTOCOL_META_KEY: CURRENT_PROTOCOL_VERSION,
        CLIENT_INFO_META_KEY: {"name": client_name, "version": "1"},
        CLIENT_CAPABILITIES_META_KEY: {},
    }


def _modern_request(
    request_id: object,
    method: str,
    *,
    params: dict[str, object] | None = None,
    meta: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": {"_meta": meta or _modern_meta(), **(params or {})},
    }


def _listed(response: dict[str, Any]) -> set[object]:
    return {
        item.get("name")
        for item in response.get("result", {}).get("tools", [])
        if isinstance(item, dict)
    }


def _modern_session() -> dict[str, Any]:
    proc = _start()
    try:
        discover = _rpc(proc, _modern_request("discover-1", "server/discover"))
        tools = _rpc(proc, _modern_request("tools-1", "tools/list", params={"cursor": ""}))
        status = _rpc(
            proc,
            _modern_request(
                "call-1",
                "tools/call",
                params={"name": "court.status", "arguments": {}},
            ),
        )
        memory = _rpc(
            proc,
            _modern_request(
                "call-2",
                "tools/call",
                params={"name": "memory.scan", "arguments": {}},
            ),
        )
        missing_meta = _rpc(proc, {"jsonrpc": "2.0", "id": "missing-meta", "method": "tools/list", "params": {}})
        unsupported = _rpc(
            proc,
            _modern_request(
                "bad-version",
                "server/discover",
                meta={
                    **_modern_meta(),
                    PROTOCOL_META_KEY: "1900-01-01",
                },
            ),
        )
        omitted_client_info = _rpc(
            proc,
            _modern_request(
                "omitted-client-info",
                "tools/list",
                meta={
                    PROTOCOL_META_KEY: CURRENT_PROTOCOL_VERSION,
                    CLIENT_CAPABILITIES_META_KEY: {},
                },
            ),
        )
        invalid_client_info = _rpc(
            proc,
            _modern_request(
                "invalid-client-info",
                "tools/list",
                meta={
                    **_modern_meta(),
                    CLIENT_INFO_META_KEY: "not-an-object",
                },
            ),
        )
        null_client_info = _rpc(
            proc,
            _modern_request(
                "null-client-info",
                "tools/list",
                meta={
                    **_modern_meta(),
                    CLIENT_INFO_META_KEY: None,
                },
            ),
        )
        invalid_client_info_shape = _rpc(
            proc,
            _modern_request(
                "invalid-client-info-shape",
                "tools/list",
                meta={
                    **_modern_meta(),
                    CLIENT_INFO_META_KEY: {"name": "only"},
                },
            ),
        )
        invalid_client_capabilities = _rpc(
            proc,
            _modern_request(
                "invalid-client-capabilities",
                "tools/list",
                meta={
                    **_modern_meta(),
                    CLIENT_CAPABILITIES_META_KEY: "not-an-object",
                },
            ),
        )
        invalid_cursor = _rpc(
            proc,
            _modern_request("invalid-cursor", "tools/list", params={"cursor": "not-supported"}),
        )
        unknown_tool = _rpc(
            proc,
            _modern_request(
                "unknown-tool",
                "tools/call",
                params={"name": "not.allowed", "arguments": {}},
            ),
        )
        invalid_arguments = _rpc(
            proc,
            _modern_request(
                "invalid-arguments",
                "tools/call",
                params={"name": "court.status", "arguments": {"limit": 0}},
            ),
        )
        malformed_json = _raw_rpc(proc, "{not-json")
        non_object = _raw_rpc(proc, "[]")
        wrong_jsonrpc = _rpc(
            proc,
            {"jsonrpc": "1.0", "id": "wrong-version", "method": "tools/list", "params": {}},
        )
        missing_id = _rpc(proc, {"jsonrpc": "2.0", "method": "tools/list", "params": {}})
        null_id = _rpc(proc, {"jsonrpc": "2.0", "id": None, "method": "tools/list", "params": {}})
        return {
            "discover": discover,
            "tools": tools,
            "status": status,
            "memory": memory,
            "missing_meta": missing_meta,
            "unsupported": unsupported,
            "omitted_client_info": omitted_client_info,
            "invalid_client_info": invalid_client_info,
            "null_client_info": null_client_info,
            "invalid_client_info_shape": invalid_client_info_shape,
            "invalid_client_capabilities": invalid_client_capabilities,
            "invalid_cursor": invalid_cursor,
            "unknown_tool": unknown_tool,
            "invalid_arguments": invalid_arguments,
            "malformed_json": malformed_json,
            "non_object": non_object,
            "wrong_jsonrpc": wrong_jsonrpc,
            "missing_id": missing_id,
            "null_id": null_id,
        }
    finally:
        _close(proc)


def _legacy_session() -> dict[str, Any]:
    proc = _start()
    try:
        initialize = _rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": LEGACY_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "@modelcontextprotocol/sdk", "version": "legacy-wire-probe"},
                },
            },
        )
        assert proc.stdin is not None
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()
        tools = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        help_result = _rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "court.command_help", "arguments": {}},
            },
        )
        fallback = _rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2099-01-01",
                    "capabilities": {},
                    "clientInfo": {"name": "legacy-fallback-probe", "version": "1"},
                },
            },
        )
        return {"initialize": initialize, "tools": tools, "help": help_result, "fallback": fallback}
    finally:
        _close(proc)


def run() -> dict[str, object]:
    modern = _modern_session()
    legacy = _legacy_session()
    modern_tools = _listed(modern["tools"])
    legacy_tools = _listed(legacy["tools"])
    modern_status = modern["status"].get("result", {}).get("structuredContent", {})
    modern_memory = modern["memory"].get("result", {}).get("structuredContent", {})
    legacy_help = legacy["help"].get("result", {}).get("structuredContent", {})
    modern_server_info = modern["status"].get("result", {}).get("_meta", {}).get(SERVER_INFO_META_KEY)
    checks = [
        (
            "modern_latest_server_discover",
            modern["discover"].get("result", {}).get("resultType") == "complete"
            and modern["discover"].get("result", {}).get("supportedVersions") == [
                CURRENT_PROTOCOL_VERSION,
                LEGACY_PROTOCOL_VERSION,
            ]
            and modern["discover"].get("result", {}).get("capabilities") == {"tools": {}}
            and modern["discover"].get("result", {}).get("ttlMs") == 300000
            and modern["discover"].get("result", {}).get("cacheScope") == "public"
            and isinstance(modern["discover"].get("result", {}).get("_meta", {}).get(SERVER_INFO_META_KEY), dict),
        ),
        (
            "modern_tools_list_accepts_per_request_meta",
            modern["tools"].get("result", {}).get("resultType") == "complete"
            and modern_tools == EXPECTED_TOOLS
            and modern["tools"].get("result", {}).get("ttlMs") == 300000
            and modern["tools"].get("result", {}).get("cacheScope") == "public"
            and isinstance(modern["tools"].get("result", {}).get("_meta", {}).get(SERVER_INFO_META_KEY), dict),
        ),
        (
            "modern_tool_call_self_describing_metadata",
            modern["status"].get("result", {}).get("resultType") == "complete"
            and isinstance(modern_server_info, dict)
            and modern_server_info.get("name") == "decretum-matrix"
            and modern_status.get("ok") is True,
        ),
        (
            "modern_status_call_is_unicode_safe",
            "\ufffd" not in json.dumps(modern_status, ensure_ascii=False)
            and "\\ufffd" not in json.dumps(modern_status, ensure_ascii=False)
            and modern_status.get("transport_corruption") is False,
        ),
        (
            "modern_memory_scan_is_public_dry_run",
            modern_memory.get("dry_run") is True
            and modern_memory.get("write_enabled") is False
            and modern_memory.get("api", {}).get("stdout", {}).get("private_body_access") is False,
        ),
        (
            "modern_missing_meta_rejected",
            modern["missing_meta"].get("error", {}).get("code") == -32602,
        ),
        (
            "modern_client_info_optional",
            modern["omitted_client_info"].get("result", {}).get("resultType") == "complete"
            and _listed(modern["omitted_client_info"]) == EXPECTED_TOOLS,
        ),
        (
            "modern_invalid_client_info_rejected",
            modern["invalid_client_info"].get("error", {}).get("code") == -32602,
        ),
        (
            "modern_null_client_info_rejected",
            modern["null_client_info"].get("error", {}).get("code") == -32602,
        ),
        (
            "modern_invalid_client_info_shape_rejected",
            modern["invalid_client_info_shape"].get("error", {}).get("code") == -32602,
        ),
        (
            "modern_invalid_client_capabilities_rejected",
            modern["invalid_client_capabilities"].get("error", {}).get("code") == -32602,
        ),
        (
            "modern_cursor_contract_rejects_nonempty_cursor",
            modern["invalid_cursor"].get("error", {}).get("code") == -32602,
        ),
        (
            "modern_unknown_tool_is_jsonrpc_error",
            modern["unknown_tool"].get("error", {}).get("code") == -32602
            and "result" not in modern["unknown_tool"],
        ),
        (
            "modern_invalid_arguments_are_jsonrpc_error",
            modern["invalid_arguments"].get("error", {}).get("code") == -32602
            and "result" not in modern["invalid_arguments"],
        ),
        (
            "jsonrpc_malformed_json_is_parse_error",
            modern["malformed_json"].get("error", {}).get("code") == -32700,
        ),
        (
            "jsonrpc_non_object_is_invalid_request",
            modern["non_object"].get("error", {}).get("code") == -32600,
        ),
        (
            "jsonrpc_wrong_version_is_invalid_request",
            modern["wrong_jsonrpc"].get("error", {}).get("code") == -32600,
        ),
        (
            "jsonrpc_missing_id_is_invalid_request",
            modern["missing_id"].get("error", {}).get("code") == -32600,
        ),
        (
            "jsonrpc_null_id_is_invalid_request",
            modern["null_id"].get("error", {}).get("code") == -32600,
        ),
        (
            "unsupported_modern_version_reports_all_supported_versions",
            modern["unsupported"].get("error", {}).get("code") == -32022
            and modern["unsupported"].get("error", {}).get("data", {}).get("supported") == [
                CURRENT_PROTOCOL_VERSION,
                LEGACY_PROTOCOL_VERSION,
            ],
        ),
        (
            "legacy_initialize_echoes_requested_version",
            legacy["initialize"].get("result", {}).get("protocolVersion") == LEGACY_PROTOCOL_VERSION,
        ),
        (
            "legacy_initialize_has_tools_capability",
            legacy["initialize"].get("result", {}).get("capabilities") == {"tools": {}},
        ),
        ("legacy_tools_list_without_custom_meta", legacy_tools == EXPECTED_TOOLS),
        (
            "legacy_tool_call_without_modern_envelope",
            legacy_help.get("ok") is True
            and legacy_help.get("api", {}).get("stdout", {}).get("command") == "court help"
            and "resultType" not in legacy["help"].get("result", {}),
        ),
        (
            "legacy_unknown_version_negotiates_legacy_baseline",
            legacy["fallback"].get("result", {}).get("protocolVersion") == LEGACY_PROTOCOL_VERSION,
        ),
        (
            "tool_allowlist_exact",
            modern_tools == EXPECTED_TOOLS and legacy_tools == EXPECTED_TOOLS,
        ),
        (
            "manifest_derived_public_registry",
            not hasattr(court_mcp_server, "TOOLS")
            and modern_tools == set(load_public_tools()),
        ),
        (
            "manifest_command_identity_and_api_bindings",
            {name: tool.command_id for name, tool in load_public_tools().items()} == EXPECTED_COMMAND_IDS
            and all(
                callable(getattr(__import__("court_public_api"), tool.public_api, None))
                for tool in load_public_tools().values()
            ),
        ),
        (
            "tool_schemas_closed",
            all(
                isinstance(item.get("inputSchema"), dict)
                and item["inputSchema"].get("additionalProperties") is False
                for item in modern["tools"].get("result", {}).get("tools", [])
                if isinstance(item, dict)
            ),
        ),
    ]
    return {
        "schema": "decretum.mcp_stdio_adapter_check.v2",
        "ok": all(ok for _, ok in checks),
        "checks": [{"name": name, "ok": ok} for name, ok in checks],
        "modern": {
            "standard_client_shape": "2026-07-28-per-request-meta",
            "protocol": CURRENT_PROTOCOL_VERSION,
            "tools": sorted(modern_tools),
            "receipt_parts": [
                "server/discover",
                "tools/list",
                "tools/call",
                "metadata_validation",
                "cursor_contract",
                "jsonrpc_error_contract",
                "missing_meta_rejection",
                "unsupported_version_rejection",
            ],
        },
        "legacy": {
            "standard_client_shape": "2025-11-25-initialize",
            "protocol": LEGACY_PROTOCOL_VERSION,
            "tools": sorted(legacy_tools),
            "receipt_parts": ["initialize", "notifications/initialized", "tools/list", "tools/call"],
        },
    }


def main() -> int:
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
