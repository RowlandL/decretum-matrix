"""Run a source-side MCP 2026-07-28 stdio wire probe.

This probe is deliberately host-neutral: it starts the source server directly,
uses the official per-request metadata shape, and emits a typed receipt.  It
does not inspect CC Switch, Codex configuration, or plugin activation state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SERVER = ROOT / "scripts" / "court_mcp_server.py"
PROTOCOL_VERSION = "2026-07-28"
PROTOCOL_META = "io.modelcontextprotocol/protocolVersion"
CLIENT_INFO_META = "io.modelcontextprotocol/clientInfo"
CLIENT_CAPABILITIES_META = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO_META = "io.modelcontextprotocol/serverInfo"
EXPECTED_TOOLS = {
    "court.status",
    "court.command_help",
    "shiguan.query",
    "shiguan.archive_dry_run",
    "memory.scan",
}


def _meta() -> dict[str, object]:
    return {
        PROTOCOL_META: PROTOCOL_VERSION,
        CLIENT_INFO_META: {"name": "@modelcontextprotocol/sdk", "version": "2026-wire-probe"},
        CLIENT_CAPABILITIES_META: {},
    }


def _request(request_id: str, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": {"_meta": _meta(), **(params or {})},
    }


def _rpc(proc: subprocess.Popen[str], request: dict[str, object]) -> dict[str, Any]:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("mcp_modern_wire_no_response")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise RuntimeError("mcp_modern_wire_response_not_object")
    return value


def _artifact(path: Path) -> dict[str, object]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {"path": str(path), "exists": False, "sha256": None, "bytes": 0, "error": str(exc)}
    return {
        "path": str(path),
        "exists": True,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _artifact_map(root: Path, server: Path) -> dict[str, dict[str, object]]:
    return {
        "server": _artifact(server),
        "skill": _artifact(root / "SKILL.md"),
        "command_manifest": _artifact(root / "references" / "manifests" / "cli-command-surface.v1.json"),
        "public_registry": _artifact(root / "scripts" / "court_public_registry.py"),
        "public_api": _artifact(root / "scripts" / "court_public_api.py"),
    }


def run(
    *,
    server: Path,
    root: Path | None = None,
    expected_root: Path | None = None,
    host_state: str = "NOT_PROBED",
) -> dict[str, object]:
    server = server.resolve()
    if root is None:
        root = server.parents[1]
    root = root.resolve()
    if not server.is_file():
        raise FileNotFoundError(server)
    artifacts = _artifact_map(root, server)
    expected_artifacts = None
    if expected_root is not None:
        expected_root = expected_root.resolve()
        expected_artifacts = _artifact_map(expected_root, expected_root / "scripts" / "court_mcp_server.py")
    proc: subprocess.Popen[str] | None = None
    discover: dict[str, Any] = {}
    listed: dict[str, Any] = {}
    called: dict[str, Any] = {}
    errors: list[str] = []
    try:
        proc = subprocess.Popen(
            [sys.executable, "-B", str(server)],
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        discover = _rpc(proc, _request("discover-1", "server/discover"))
        listed = _rpc(proc, _request("list-1", "tools/list", {"cursor": ""}))
        called = _rpc(
            proc,
            _request("call-1", "tools/call", {"name": "court.status", "arguments": {}}),
        )
    except Exception as exc:  # noqa: BLE001 - receipt must preserve a typed failure.
        errors.append(f"{type(exc).__name__}:{exc}")
    finally:
        if proc is not None and proc.stdin is not None:
            proc.stdin.close()
        if proc is not None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    listed_tools = {
        item.get("name")
        for item in listed.get("result", {}).get("tools", [])
        if isinstance(item, dict)
    }
    result = called.get("result", {})
    structured = result.get("structuredContent", {}) if isinstance(result, dict) else {}
    server_info = result.get("_meta", {}).get(SERVER_INFO_META) if isinstance(result, dict) else None
    checks = [
        ("discover_result_type", discover.get("result", {}).get("resultType") == "complete"),
        (
            "discover_versions",
            discover.get("result", {}).get("supportedVersions") == [PROTOCOL_VERSION, "2025-11-25"],
        ),
        ("discover_capabilities", discover.get("result", {}).get("capabilities") == {"tools": {}}),
        (
            "tools_list_result_type_and_cache",
            listed.get("result", {}).get("resultType") == "complete"
            and listed.get("result", {}).get("ttlMs") == 300000
            and listed.get("result", {}).get("cacheScope") == "public",
        ),
        ("tools_list_allowlist", listed_tools == EXPECTED_TOOLS),
        (
            "tools_call_result_metadata",
            result.get("resultType") == "complete"
            and isinstance(server_info, dict)
            and server_info.get("name") == "decretum-matrix",
        ),
        (
            "tools_call_unicode_safe",
            structured.get("ok") is True
            and structured.get("transport_corruption") is False
            and "\ufffd" not in json.dumps(structured, ensure_ascii=False),
        ),
        (
            "hash_bound_runtime_surface",
            all(item.get("exists") is True and isinstance(item.get("sha256"), str) for item in artifacts.values()),
        ),
        (
            "hash_matches_expected_source",
            expected_artifacts is None
            or all(
                artifacts[name].get("exists") is True
                and artifacts[name].get("sha256") == expected_artifacts[name].get("sha256")
                for name in artifacts
            ),
        ),
    ]
    return {
        "schema": "decretum.mcp.modern_wire_receipt.v1",
        "status": "PASS" if all(ok for _, ok in checks) else "FAIL",
        "protocol": PROTOCOL_VERSION,
        "transport": "stdio",
        "client_shape": "@modelcontextprotocol/sdk-compatible-per-request-meta",
        "host_state": host_state,
        "root": str(root),
        "server": str(server),
        "expected_root": str(expected_root) if expected_root is not None else None,
        "version": (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").is_file() else "unknown",
        "artifacts": artifacts,
        "expected_artifacts": expected_artifacts,
        "errors": errors,
        "checks": [{"name": name, "ok": ok} for name, ok in checks],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server",
        type=Path,
        default=DEFAULT_SERVER,
        help="court_mcp_server.py path to probe. Defaults to the source checkout.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="Working root for the server. Defaults to the server's skill root.",
    )
    parser.add_argument(
        "--expected-root",
        type=Path,
        help="Optional validated source root whose runtime-surface hashes must match.",
    )
    parser.add_argument(
        "--host-state",
        default="NOT_PROBED",
        help="Receipt label for the surrounding host state; this probe does not inspect it.",
    )
    args = parser.parse_args(argv)
    receipt = run(server=args.server, root=args.root, expected_root=args.expected_root, host_state=args.host_state)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
