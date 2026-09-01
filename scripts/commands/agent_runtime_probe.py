"""Probe local Codex-only court runtime capabilities without secrets."""

from __future__ import annotations

import argparse
import http.server
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None  # type: ignore[assignment]

sys.dont_write_bytecode = True

from codex_runtime_probe_support import (
    _existing_pids,
    _process_creation_flags,
    _safe_probe_environment,
    _terminate_process,
    _toml_key_names,
    _windows_descendant_pids,
    strict_config_file_probe,
    strict_config_text_probe,
)
from court_multi_agent_protocol import validate_protocol_config
from court_model_router import MODEL_MAX_REASONING_EFFORT


RECOMMENDED_AGENT_MAX_DEPTH = 4
RECOMMENDED_AGENT_MAX_THREADS = 32


def parse_codex_wrapper_target(text: str) -> Path | None:
    match = re.search(r'["\']([^"\'\r\n]*[\\/]codex\.js)["\']', text, re.IGNORECASE)
    if not match:
        return None
    return Path(match.group(1))


def validate_store_false_evidence(evidence: dict[str, object]) -> dict[str, object]:
    errors: list[str] = []

    def require(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    require(evidence.get("client_exit_code") == 0, "client_exit_code")
    require(evidence.get("endpoint_loopback") is True, "endpoint_loopback")
    require(evidence.get("listener_bind") == "127.0.0.1", "listener_bind")
    require(evidence.get("total_http_requests") == 1, "total_http_requests")
    require(evidence.get("responses_request_count") == 1, "responses_request_count")
    require(evidence.get("request_method") == "POST", "request_method")
    require(evidence.get("request_path") == "/v1/responses", "request_path")
    require(
        str(evidence.get("request_content_type") or "").lower().startswith("application/json"),
        "request_content_type",
    )
    require(evidence.get("store_present") is True, "store_present")
    require(evidence.get("store_type") == "boolean", "store_type")
    require(evidence.get("store_value") is False, "store_value")
    require(evidence.get("duplicate_store_keys") == 0, "duplicate_store_keys")
    require(evidence.get("prompt_marker_in_request") is True, "prompt_marker_in_request")
    require(evidence.get("authorization_present") is True, "authorization_present")
    for field in ("raw_request_archived", "raw_response_archived", "headers_archived", "full_config_archived"):
        require(evidence.get(field) is False, field)
    require(evidence.get("timeout_triggered") is False, "timeout_triggered")
    require(evidence.get("cleanup_verified") is True, "cleanup_verified")
    require(evidence.get("orphan_process_count") == 0, "orphan_process_count")
    require(evidence.get("listener_closed") is True, "listener_closed")
    require(evidence.get("session_file_count") == 0, "session_file_count")
    for field in ("prompt_marker_matches", "response_marker_matches", "credential_canary_matches"):
        require(evidence.get(field) == 0, field)
    return {
        "ok": not errors,
        "errors": errors,
        "claim_scope": "client_emitted_store_false_only",
    }


def validate_codex_resolution(resolution: dict[str, object]) -> dict[str, object]:
    errors: list[str] = []
    if resolution.get("exact_native_executable") is not True:
        errors.append("exact_native_executable")
    if resolution.get("version_match") is not True:
        errors.append("version_match")
    if not str(resolution.get("version") or "").startswith("codex-cli "):
        errors.append("version")
    if str(resolution.get("executable_name") or "").lower() != "codex.exe":
        errors.append("executable_name")
    return {"ok": not errors, "errors": errors}


def _version_for_path(path: Path) -> str:
    try:
        result = subprocess.run(
            [str(path), "--version"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    return (result.stdout or result.stderr or "").splitlines()[0].strip()


def _path_digest(path: Path) -> str:
    normalized = str(path.resolve()).casefold().encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(normalized).hexdigest()


def resolve_codex_executable(command: str = "codex", *, include_binary_hash: bool = False) -> dict[str, object]:
    invocation_text = shutil.which(command)
    if not invocation_text:
        return {
            "ok": False,
            "errors": ["command_not_found"],
            "command": command,
        }
    invocation = Path(invocation_text).resolve()
    invocation_version = _version_for_path(invocation)
    executable = invocation
    source = "native_path"
    exact_native = invocation.suffix.lower() == ".exe"
    wrapper_target: Path | None = None
    if not exact_native and invocation.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        try:
            wrapper_target = parse_codex_wrapper_target(invocation.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            wrapper_target = None
        if wrapper_target is not None:
            package_root = wrapper_target.parent.parent
            candidates = sorted(
                path.resolve()
                for path in (package_root / "node_modules").rglob("codex.exe")
                if path.is_file()
            )
            version_matches = [path for path in candidates if _version_for_path(path) == invocation_version]
            if len(version_matches) == 1:
                executable = version_matches[0]
                exact_native = True
                source = "npm_wrapper_target"
            elif len(version_matches) > 1:
                source = "ambiguous_npm_wrapper_target"
            else:
                source = "unresolved_npm_wrapper_target"
    executable_version = _version_for_path(executable)
    payload: dict[str, object] = {
        "command": command,
        "invocation_path": str(invocation),
        "invocation_path_sha256": _path_digest(invocation),
        "invocation_version": invocation_version,
        "wrapper_target": str(wrapper_target) if wrapper_target is not None else None,
        "executable_path": str(executable),
        "executable_path_sha256": _path_digest(executable),
        "executable_name": executable.name.lower(),
        "version": executable_version,
        "version_match": bool(invocation_version and executable_version == invocation_version),
        "exact_native_executable": exact_native,
        "resolution_source": source,
    }
    if include_binary_hash and exact_native and executable.is_file():
        payload["executable_sha256"] = sha256_file(executable)
    validation = validate_codex_resolution(payload)
    payload["ok"] = validation["ok"]
    payload["errors"] = validation["errors"]
    return payload


class _DuplicateAwareDict(dict[str, object]):
    def __init__(self, pairs: list[tuple[str, object]]) -> None:
        super().__init__()
        duplicate_keys: dict[str, int] = {}
        for key, value in pairs:
            if key in self:
                duplicate_keys[key] = duplicate_keys.get(key, 0) + 1
            self[key] = value
        self.duplicate_keys = duplicate_keys


def _json_type(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _request_tool_summary(parsed: object) -> dict[str, object]:
    """Return only tool/schema key names; never retain descriptions or request bodies."""

    if not isinstance(parsed, dict):
        return {"tool_names": [], "tool_schemas": [], "agent_tools": [], "spawn_agent_tools": []}
    tools = parsed.get("tools")
    if not isinstance(tools, list):
        return {"tool_names": [], "tool_schemas": [], "agent_tools": [], "spawn_agent_tools": []}
    rows: list[dict[str, object]] = []
    schema_markers = (
        "message",
        "task_name",
        "fork_turns",
        "agent_type",
        "model",
        "reasoning_effort",
        "service_tier",
    )
    for item in tools:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        parameters = item.get("parameters")
        nested = item.get("function")
        if not isinstance(name, str) and isinstance(nested, dict):
            name = nested.get("name")
            parameters = nested.get("parameters")
        if not isinstance(name, str) or not name:
            continue
        properties = parameters.get("properties") if isinstance(parameters, dict) else None
        required = parameters.get("required") if isinstance(parameters, dict) else None
        serialized = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        rows.append(
            {
                "name": name,
                "definition_keys": sorted(str(key) for key in item),
                "property_keys": sorted(str(key) for key in properties) if isinstance(properties, dict) else [],
                "required_keys": sorted(str(key) for key in required) if isinstance(required, list) else [],
                "schema_marker_presence": {
                    marker: re.search(rf"(?<![A-Za-z0-9_]){re.escape(marker)}(?![A-Za-z0-9_])", serialized)
                    is not None
                    for marker in schema_markers
                },
            }
        )
    rows.sort(key=lambda row: str(row["name"]))
    return {
        "tool_names": [str(row["name"]) for row in rows],
        "tool_schemas": rows,
        "agent_tools": [row for row in rows if "agent" in str(row["name"]) or row["name"] == "collaboration"],
        "spawn_agent_tools": [
            row for row in rows
            if "spawn_agent" in str(row["name"]) or row["name"] == "collaboration"
        ],
    }


def _stop_owned_pids(pids: list[int]) -> bool:
    """Stop owned descendants while keeping the public probe seam patchable."""
    if not pids:
        return True
    if os.name != "nt":
        raise RuntimeError("owned child cleanup is unsupported on this platform")
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("PowerShell is required for Windows process cleanup")
    existing = _existing_pids(pids)
    if not existing:
        return True
    joined = ",".join(str(pid) for pid in existing)
    subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-Command",
            f"Get-Process -Id @({joined}) -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue",
        ],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
        creationflags=_process_creation_flags(),
    )
    for _ in range(3):
        if not _existing_pids(existing):
            return True
        time.sleep(0.1)
    return False


def _count_marker_matches(root: Path, markers: dict[str, bytes], stdout: str, stderr: str) -> dict[str, int]:
    counts = {name: 0 for name in markers}
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        for name, marker in markers.items():
            counts[name] += data.count(marker)
    combined = (stdout + "\n" + stderr).encode("utf-8", errors="replace")
    for name, marker in markers.items():
        counts[name] += combined.count(marker)
    return counts


def run_store_false_probe(
    executable_path: Path,
    *,
    timeout_seconds: float = 20.0,
    response_delay_seconds: float = 0.0,
    agent_protocol: str = "serial",
) -> dict[str, object]:
    if agent_protocol not in {"serial", "v1", "v2"}:
        raise ValueError(f"unsupported agent protocol probe: {agent_protocol}")
    started = time.perf_counter()
    prompt_marker = f"COURT_PROMPT_{uuid.uuid4().hex}"
    response_marker = f"COURT_RESPONSE_{uuid.uuid4().hex}"
    credential_canary = f"COURT_CREDENTIAL_{uuid.uuid4().hex}"
    requests: list[dict[str, object]] = []
    requests_lock = threading.Lock()
    cancel_response = threading.Event()

    class ProbeServer(http.server.ThreadingHTTPServer):
        daemon_threads = True
        block_on_close = False

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _record(self, metadata: dict[str, object]) -> None:
            with requests_lock:
                requests.append(metadata)

        def do_GET(self) -> None:  # noqa: N802
            self._record({"method": "GET", "path": self.path, "content_type": ""})
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            content_length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(content_length)
            try:
                parsed = json.loads(raw, object_pairs_hook=_DuplicateAwareDict)
            except (json.JSONDecodeError, UnicodeDecodeError):
                parsed = _DuplicateAwareDict([])
            store_present = isinstance(parsed, dict) and "store" in parsed
            store_value = parsed.get("store") if isinstance(parsed, dict) else None
            duplicate_store_keys = (
                parsed.duplicate_keys.get("store", 0) if isinstance(parsed, _DuplicateAwareDict) else 0
            )
            tool_summary = _request_tool_summary(parsed)
            self._record(
                {
                    "method": "POST",
                    "path": self.path,
                    "content_type": self.headers.get("Content-Type", ""),
                    "body_sha256": hashlib.sha256(raw).hexdigest(),
                    "body_bytes": len(raw),
                    "top_level_keys": sorted(parsed.keys()) if isinstance(parsed, dict) else [],
                    "store_present": store_present,
                    "store_type": _json_type(store_value) if store_present else "missing",
                    "store_value": store_value,
                    "duplicate_store_keys": duplicate_store_keys,
                    "tool_names": tool_summary["tool_names"],
                    "agent_tools": tool_summary["agent_tools"],
                    "spawn_agent_tools": tool_summary["spawn_agent_tools"],
                    "prompt_marker_in_request": prompt_marker.encode("utf-8") in raw,
                    "authorization_present": bool(self.headers.get("Authorization")),
                }
            )
            if response_delay_seconds > 0 and cancel_response.wait(response_delay_seconds):
                return
            response = {
                "id": "resp_court_probe",
                "object": "response",
                "created_at": int(time.time()),
                "status": "completed",
                "model": parsed.get("model", "court-probe-model") if isinstance(parsed, dict) else "court-probe-model",
                "output": [
                    {
                        "id": "msg_court_probe",
                        "type": "message",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": response_marker, "annotations": []}
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "total_tokens": 2,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            }
            event = json.dumps(
                {"type": "response.completed", "sequence_number": 0, "response": response},
                separators=(",", ":"),
            ).encode("utf-8")
            body = b"event: response.completed\ndata: " + event + b"\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass

    server = ProbeServer(("127.0.0.1", 0), Handler)
    listener_port = int(server.server_address[1])
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    timeout_triggered = False
    stdout = ""
    stderr = ""
    process: subprocess.Popen[str] | None = None
    with tempfile.TemporaryDirectory(prefix="court-codex-store-false-") as temp_dir:
        root = Path(temp_dir)
        home = root / "home"
        work = root / "work"
        home.mkdir()
        work.mkdir()
        env = _safe_probe_environment(home, credential_canary)
        base_url = f"http://127.0.0.1:{listener_port}/v1"
        config_keys = [
            "model",
            "model_provider",
            "model_providers.court_probe.base_url",
            "model_providers.court_probe.env_key",
            "model_providers.court_probe.name",
            "model_providers.court_probe.requires_openai_auth",
            "model_providers.court_probe.wire_api",
        ]
        protocol_args = ["--disable", "multi_agent", "--disable", "multi_agent_v2"]
        protocol_config_args: list[str] = []
        if agent_protocol == "v1":
            protocol_args = ["--enable", "multi_agent", "--disable", "multi_agent_v2"]
            protocol_config_args = [
                "-c",
                "agents.max_depth=4",
                "-c",
                f"agents.max_threads={RECOMMENDED_AGENT_MAX_THREADS - 1}",
                "-c",
                "features.multi_agent=true",
                "-c",
                "features.multi_agent_v2.enabled=false",
                "-c",
                f"features.multi_agent_v2.max_concurrent_threads_per_session={RECOMMENDED_AGENT_MAX_THREADS}",
                "-c",
                "features.multi_agent_v2.hide_spawn_agent_metadata=true",
            ]
            config_keys.extend(
                [
                    "agents.max_depth",
                    "agents.max_threads",
                    "features.multi_agent",
                    "features.multi_agent_v2.enabled",
                    "features.multi_agent_v2.max_concurrent_threads_per_session",
                    "features.multi_agent_v2.hide_spawn_agent_metadata",
                ]
            )
        elif agent_protocol == "v2":
            protocol_args = ["--disable", "multi_agent"]
            protocol_config_args = [
                "-c", "agents.max_depth=4",
                "-c", "features.multi_agent_v2.enabled=true",
                "-c", f"features.multi_agent_v2.max_concurrent_threads_per_session={RECOMMENDED_AGENT_MAX_THREADS}",
                "-c", "features.multi_agent_v2.hide_spawn_agent_metadata=true",
            ]
            config_keys.extend(
                [
                    "agents.max_depth",
                    "features.multi_agent_v2.enabled",
                    "features.multi_agent_v2.max_concurrent_threads_per_session",
                    "features.multi_agent_v2.hide_spawn_agent_metadata",
                ]
            )
        command = [
            str(executable_path),
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--disable",
            "apps",
            "--disable",
            "plugins",
            "--disable",
            "memories",
            "--disable",
            "goals",
            *protocol_args,
            "--sandbox",
            "read-only",
            "-C",
            str(work),
            "-c",
            'model_provider="court_probe"',
            "-c",
            'model="court-probe-model"',
            "-c",
            f'model_providers.court_probe.base_url="{base_url}"',
            "-c",
            'model_providers.court_probe.name="Court Probe"',
            "-c",
            'model_providers.court_probe.wire_api="responses"',
            "-c",
            'model_providers.court_probe.env_key="COURT_PROBE_API_KEY"',
            "-c",
            "model_providers.court_probe.requires_openai_auth=false",
            *protocol_config_args,
            "--json",
        ]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=_process_creation_flags(),
        )
        descendants = _windows_descendant_pids(process.pid)
        try:
            stdout, stderr = process.communicate(input=prompt_marker, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timeout_triggered = True
            descendants = sorted(set(descendants) | set(_windows_descendant_pids(process.pid)))
            _terminate_process(process)
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                stdout = ""
                stderr = ""
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
        cleanup_verified = _stop_owned_pids(descendants)
        remaining_descendants = _existing_pids(descendants)
        session_files = [path for path in (home / "sessions").rglob("*") if path.is_file()] if (home / "sessions").exists() else []
        markers = {
            "prompt": prompt_marker.encode("utf-8"),
            "response": response_marker.encode("utf-8"),
            "credential": credential_canary.encode("utf-8"),
        }
        marker_counts = _count_marker_matches(root, markers, stdout, stderr)
        isolated_home_file_count = sum(1 for path in home.rglob("*") if path.is_file())
        client_exit_code = process.returncode
        config_template_sha256 = hashlib.sha256("\n".join(config_keys).encode("utf-8")).hexdigest()
    cancel_response.set()
    server.shutdown()
    server.server_close()
    server_thread.join(timeout=2)
    try:
        with socket.create_connection(("127.0.0.1", listener_port), timeout=0.25):
            listener_closed = False
    except OSError:
        listener_closed = True
    with requests_lock:
        captured = list(requests)
    responses = [item for item in captured if item.get("method") == "POST" and item.get("path") == "/v1/responses"]
    request = responses[0] if len(responses) == 1 else {}
    evidence: dict[str, object] = {
        "schema": "court.codex-store-false-proof.v1",
        "run_id": uuid.uuid4().hex,
        "harness_sha256": sha256_file(Path(__file__)),
        "verifier_sha256": sha256_file(Path(__file__)),
        "config_template_sha256": config_template_sha256,
        "config_key_names": config_keys,
        "listener_bind": "127.0.0.1",
        "listener_port_recorded": False,
        "endpoint_loopback": True,
        "total_http_requests": len(captured),
        "responses_request_count": len(responses),
        "request_method": request.get("method"),
        "request_path": request.get("path"),
        "request_content_type": request.get("content_type"),
        "request_body_sha256": request.get("body_sha256"),
        "request_body_bytes": request.get("body_bytes"),
        "request_top_level_keys": request.get("top_level_keys", []),
        "multi_agent_protocol": agent_protocol,
        "agent_schema_claim_scope": (
            "v1_tool_name_and_field_marker_presence_only"
            if agent_protocol == "v1"
            else "v2_core_fields_and_optional_field_presence"
            if agent_protocol == "v2"
            else "not_applicable"
        ),
        "tool_names": request.get("tool_names", []),
        "agent_tools": request.get("agent_tools", []),
        "spawn_agent_tools": request.get("spawn_agent_tools", []),
        "store_present": request.get("store_present", False),
        "store_type": request.get("store_type", "missing"),
        "store_value": request.get("store_value"),
        "duplicate_store_keys": request.get("duplicate_store_keys", 0),
        "prompt_marker_in_request": request.get("prompt_marker_in_request", False),
        "authorization_present": request.get("authorization_present", False),
        "raw_request_archived": False,
        "raw_response_archived": False,
        "headers_archived": False,
        "full_config_archived": False,
        "client_exit_code": client_exit_code,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "timeout_triggered": timeout_triggered,
        "descendant_process_count_observed": len(descendants),
        "cleanup_verified": cleanup_verified,
        "orphan_process_count": len(remaining_descendants),
        "listener_closed": listener_closed,
        "session_file_count": len(session_files),
        "isolated_home_file_count": isolated_home_file_count,
        "prompt_marker_matches": marker_counts["prompt"],
        "response_marker_matches": marker_counts["response"],
        "credential_canary_matches": marker_counts["credential"],
        "raw_stdout_archived": False,
        "raw_stderr_archived": False,
        "claim_scope": "client_emitted_store_false_only",
    }
    validation = validate_store_false_evidence(evidence)
    evidence["overall_gate"] = "PASSED" if validation["ok"] else "FAILED"
    evidence["errors"] = validation["errors"]
    return evidence


def native_config_read_summary(executable_path: Path, *, cwd: Path, timeout_seconds: float = 15.0) -> dict[str, object]:
    """Read the host-effective config through app-server without retaining private fields."""
    process = subprocess.Popen(
        [str(executable_path), "app-server", "--stdio"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    messages: queue.Queue[dict[str, object]] = queue.Queue()
    def read_messages() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                messages.put(item)
    threading.Thread(target=read_messages, daemon=True).start()
    def send(item: dict[str, object]) -> None:
        assert process.stdin is not None
        process.stdin.write(json.dumps(item, separators=(",", ":")) + "\n")
        process.stdin.flush()
    def response(request_id: int) -> dict[str, object]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError(f"app-server response timeout: {request_id}")
            item = messages.get(timeout=remaining)
            if item.get("id") == request_id:
                return item
    try:
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "court-config-gate", "version": "1"}}})
        initialized = response(1)
        if "error" in initialized:
            raise RuntimeError("app-server initialize failed")
        send({"method": "initialized", "params": {}})
        send({"id": 2, "method": "config/read", "params": {"cwd": str(cwd), "includeLayers": True}})
        reply = response(2)
        if "error" in reply or not isinstance(reply.get("result"), dict):
            raise RuntimeError("app-server config/read failed")
        result = reply["result"]
        config = result.get("config") if isinstance(result, dict) else None
        config = config if isinstance(config, dict) else {}
        agents = config.get("agents") if isinstance(config.get("agents"), dict) else {}
        features = config.get("features") if isinstance(config.get("features"), dict) else {}
        v2 = features.get("multi_agent_v2") if isinstance(features.get("multi_agent_v2"), dict) else {}
        selected = (
            "v2" if v2.get("enabled") is True and agents.get("max_threads") is None
            else "v1" if v2.get("enabled") is False and features.get("multi_agent") is True and isinstance(agents.get("max_threads"), int) and agents.get("max_threads") >= 1
            else None
        )
        errors: list[str] = []
        if agents.get("max_depth") != 4: errors.append("max_depth")
        if selected == "v2" and (
            not isinstance(v2.get("max_concurrent_threads_per_session"), int)
            or v2.get("max_concurrent_threads_per_session") < 2
            or v2.get("hide_spawn_agent_metadata") is not True
        ):
            errors.append("v2_bounds_or_reserved_schema")
        if selected == "v1" and (
            not isinstance(v2.get("max_concurrent_threads_per_session"), int)
            or v2.get("max_concurrent_threads_per_session") < 2
            or v2.get("hide_spawn_agent_metadata") is not True
        ):
            errors.append("v1_inactive_v2_table")
        if selected is None: errors.append("protocol_unresolved")
        layers = result.get("layers") if isinstance(result, dict) and isinstance(result.get("layers"), list) else []
        layer_rows = []
        for layer in layers:
            if isinstance(layer, dict):
                name = layer.get("name")
                layer_rows.append({"type": name.get("type") if isinstance(name, dict) else str(name), "version": layer.get("version")})
        return {
            "ok": not errors,
            "errors": errors,
            "selected_protocol": selected,
            "max_depth": agents.get("max_depth"),
            "legacy_max_threads": agents.get("max_threads"),
            "multi_agent": features.get("multi_agent"),
            "multi_agent_v2": {key: v2.get(key) for key in ("enabled", "max_concurrent_threads_per_session", "hide_spawn_agent_metadata")},
            "layer_count": len(layers),
            "layers": layer_rows,
            "full_config_archived": False,
        }
    finally:
        if process.stdin is not None: process.stdin.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_version(command: str) -> str:
    path = shutil.which(command)
    if not path:
        return ""
    return _version_for_path(Path(path)) or "available"


def _sanitize_public_value(value: object, roots: tuple[tuple[Path, str], ...]) -> object:
    if isinstance(value, dict):
        return {str(key): _sanitize_public_value(item, roots) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_public_value(item, roots) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_public_value(item, roots) for item in value)
    if not isinstance(value, str):
        return value
    sanitized = value
    for root, alias in roots:
        raw = str(root.resolve())
        for variant in {raw, raw.replace("\\", "/")}:
            sanitized = re.sub(re.escape(variant), alias, sanitized, flags=re.IGNORECASE)
    if re.search(r"(?i)(?:[a-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+)", sanitized):
        digest = hashlib.sha256(sanitized.encode("utf-8", errors="surrogatepass")).hexdigest()[:16]
        return f"<local-path:{digest}>"
    return sanitized


def sanitize_probe_payload(payload: dict[str, object], *, home: Path, court_root: Path) -> dict[str, object]:
    roots = tuple(
        sorted(
            (
                (court_root.resolve(), "$COURT_SKILL_ROOT"),
                (home.resolve(), "$CODEX_HOME"),
                (Path.home().resolve(), "$USER_HOME"),
            ),
            key=lambda item: len(str(item[0])),
            reverse=True,
        )
    )
    sanitized = _sanitize_public_value(payload, roots)
    if not isinstance(sanitized, dict):
        raise TypeError("sanitized probe payload must remain an object")
    return sanitized


def _latest_turn_context(
    codex_home: Path,
    session_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Read only model/effort metadata from a Codex session JSONL.

    Never returns conversation text or credentials; any probe failure yields
    (None, None) so callers fail closed without raising. When ``session_id`` is
    provided, only that session's JSONL is considered so a host proof never
    reads turn context from an unrelated session (R-11); otherwise the most
    recent session files are used (host-level approximation).
    """
    sessions_dir = codex_home / "sessions"
    if not sessions_dir.is_dir():
        return None, None
    try:
        candidates = [path for path in sessions_dir.glob("*.jsonl") if path.is_file()]
    except OSError:
        return None, None
    requested = str(session_id or "").strip()
    if requested:
        candidates = [
            path
            for path in candidates
            if requested.casefold() in path.name.casefold()
        ]
    if not candidates:
        return None, None
    for path in sorted(
        candidates,
        key=lambda item: (item.stat().st_mtime_ns, str(item)),
        reverse=True,
    )[:5]:
        try:
            if path.is_symlink() or path.stat().st_size > 64 * 1024 * 1024:
                continue
        except OSError:
            continue
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if line_number > 2000:
                        break
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(item, dict):
                        continue
                    payload = item.get("payload")
                    if item.get("type") == "turn_context" and isinstance(payload, dict):
                        model = payload.get("model")
                        effort = payload.get("effort")
                        return (
                            str(model) if isinstance(model, str) and model else None,
                            str(effort) if isinstance(effort, str) and effort else None,
                        )
        except OSError:
            continue
    return None, None


def _config_exposes_model(codex_home: Path) -> bool | None:
    """Report whether the effective Codex config exposes a model field.

    True when the effective file carries a top-level ``model`` or
    ``model_provider``; False when parsed but absent; None when the effective
    file is unavailable (so probe consumers fail closed, never guessing).
    """
    try:
        summary = effective_config_agent_summary(codex_home)
    except Exception:
        return None
    source = str(summary.get("effective_config_source") or "")
    if not source:
        return None
    path = codex_home / source
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if tomllib is None:
        return None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    return "model" in data or "model_provider" in data


def config_agent_summary(path: Path) -> dict[str, object]:
    summary: dict[str, object] = {
        "path": path.name,
        "exists": path.exists(),
        "byte_length": None,
        "parse_ok": False,
        "parse_error_class": None,
        "agents_section": False,
        "max_depth": None,
        "max_threads": None,
        "legacy_max_threads": None,
        "max_concurrent_threads_per_session": None,
        "effective_child_thread_limit": None,
        "config_conflict": False,
        "selected_protocol": None,
        "protocol_config_ok": False,
        "protocol_config_errors": [],
        "multi_agent_enabled": None,
        "multi_agent_v2_present": False,
        "multi_agent_v2_enabled": False,
        "spawn_agent_metadata_visible": False,
        "spawn_agent_metadata_hidden": False,
        "reserved_spawn_schema_compatible": False,
        "inactive_v2_config_preserved": False,
        "deprecated_disable_response_storage_present": False,
        "protocol_material_present": False,
    }
    if not path.exists():
        return summary
    summary["byte_length"] = path.stat().st_size
    text = path.read_text(encoding="utf-8", errors="replace")
    if tomllib is None:
        summary["parse_error_class"] = "tomllib_unavailable"
        return summary
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        summary["parse_error_class"] = "toml_decode_error"
        return summary
    if not isinstance(data, dict):
        summary["parse_error_class"] = "toml_root_not_table"
        return summary
    summary["parse_ok"] = True
    contract = validate_protocol_config(text)
    summary["selected_protocol"] = contract.get("mode")
    summary["protocol_config_ok"] = contract.get("ok") is True
    summary["protocol_config_errors"] = list(contract.get("errors", []))
    summary["inactive_v2_config_preserved"] = contract.get("inactive_v2_config_preserved") is True
    summary["deprecated_disable_response_storage_present"] = "disable_response_storage" in data
    agents = data.get("agents")
    if isinstance(agents, dict):
        summary["agents_section"] = True
        depth = agents.get("max_depth")
        legacy_threads = agents.get("max_threads")
        if isinstance(depth, int) and not isinstance(depth, bool):
            summary["max_depth"] = depth
        if isinstance(legacy_threads, int) and not isinstance(legacy_threads, bool):
            summary["legacy_max_threads"] = legacy_threads
            summary["max_threads"] = legacy_threads
    features = data.get("features")
    if isinstance(features, dict):
        summary["multi_agent_enabled"] = features.get("multi_agent")
    multi_agent = features.get("multi_agent_v2") if isinstance(features, dict) else None
    if isinstance(multi_agent, dict):
        summary["multi_agent_v2_present"] = True
        summary["multi_agent_v2_enabled"] = multi_agent.get("enabled") is True
        summary["spawn_agent_metadata_visible"] = multi_agent.get("hide_spawn_agent_metadata") is False
        summary["spawn_agent_metadata_hidden"] = multi_agent.get("hide_spawn_agent_metadata") is True
        v2_threads = multi_agent.get("max_concurrent_threads_per_session")
        if isinstance(v2_threads, int) and not isinstance(v2_threads, bool):
            summary["max_concurrent_threads_per_session"] = v2_threads
            if summary["selected_protocol"] == "v2":
                summary["max_threads"] = v2_threads
                summary["effective_child_thread_limit"] = max(v2_threads - 1, 0)
    if summary["selected_protocol"] == "v1":
        summary["max_threads"] = summary["legacy_max_threads"]
        summary["effective_child_thread_limit"] = summary["legacy_max_threads"]
    summary["config_conflict"] = bool(
        summary["multi_agent_v2_enabled"] and summary["legacy_max_threads"] is not None
    )
    summary["reserved_spawn_schema_compatible"] = bool(
        summary["multi_agent_v2_enabled"] and summary["spawn_agent_metadata_hidden"]
    )
    summary["protocol_material_present"] = bool(
        summary["multi_agent_v2_present"]
        or summary["multi_agent_enabled"] is not None
        or summary["legacy_max_threads"] is not None
    )
    return summary


def effective_config_agent_summary(home: Path) -> dict[str, object]:
    """Return the effective multi-agent config without letting an empty overlay self-block.

    Desktop/CC Switch may leave managed_config.toml present but empty as a normal
    overlay placeholder. That file must not mask a valid user config.toml when
    deciding whether host-native multi-agent dispatch is available.
    """

    config_path = home / "config.toml"
    managed_path = home / "managed_config.toml"
    user_config = config_agent_summary(config_path)
    if not managed_path.exists():
        user_config["effective_config_source"] = "config.toml"
        user_config["managed_overlay"] = {"exists": False}
        return user_config

    managed = config_agent_summary(managed_path)
    managed_has_material = managed.get("protocol_material_present") is True
    managed_has_nonempty_parse_error = (
        managed.get("parse_ok") is not True and int(managed.get("byte_length") or 0) > 0
    )
    if managed_has_material or managed_has_nonempty_parse_error:
        managed["effective_config_source"] = "managed_config.toml"
        managed["managed_overlay"] = {
            "exists": True,
            "used": True,
            "reason": "contains_protocol_material" if managed_has_material else "nonempty_parse_failure",
            "byte_length": managed.get("byte_length"),
        }
        return managed

    user_config["effective_config_source"] = "config.toml"
    user_config["managed_overlay"] = {
        "exists": True,
        "used": False,
        "reason": "empty_overlay" if int(managed.get("byte_length") or 0) == 0 else "no_protocol_material",
        "byte_length": managed.get("byte_length"),
        "parse_ok": managed.get("parse_ok"),
    }
    return user_config


def standing_profile_summary(agents_dir: Path, templates_dir: Path) -> dict[str, object]:
    scripts_dir = skill_root() / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        import check_codex_agent_roles  # type: ignore

        required_files = list(check_codex_agent_roles.REQUIRED_PROFILE_FILES)
        role_state = check_codex_agent_roles.validate_installed_agents(agents_dir, templates_dir)
        sync_rows = list(role_state["sync_rows"])
    except Exception as exc:
        required_files = sorted(path.name for path in templates_dir.glob("*.toml")) if templates_dir.exists() else []
        role_state = {
            "ok": False,
            "error": str(exc),
            "malformed_count": None,
            "unsynced_count": None,
            "schema_rows": [],
        }
        sync_rows = []
        for name in required_files:
            template = templates_dir / name
            installed = agents_dir / name
            template_hash = sha256_file(template) if template.exists() else None
            installed_hash = sha256_file(installed) if installed.exists() else None
            status = "synced" if installed.exists() and template_hash == installed_hash else "unknown_render_status"
            sync_rows.append(
                {
                    "agent": name,
                    "template_exists": template.exists(),
                    "installed_exists": installed.exists(),
                    "template_hash": template_hash,
                    "installed_hash": installed_hash,
                    "status": status,
                }
            )
    validation_errors: list[str] = []
    validated_profiles = 0
    try:
        import court_office_bootstrap  # type: ignore

        for name in required_files:
            role = Path(name).stem
            try:
                court_office_bootstrap.load_standing_profile_binding(role, profile_root=templates_dir)
                validated_profiles += 1
            except Exception as exc:
                validation_errors.append(f"{role}:{exc}")
    except Exception as exc:
        validation_errors.append(f"validator:{exc}")
    validation = {
        "ok": not validation_errors and validated_profiles == len(required_files),
        "validator": "court_office_bootstrap.load_standing_profile_binding",
        "carrier_kind": "child_agent",
        "profile_count": validated_profiles,
        "required_count": len(required_files),
        "errors": validation_errors,
    }
    return {
        "validation": validation,
        "installed_role_schema": role_state,
        "malformed_count": role_state.get("malformed_count"),
        "unsynced_count": role_state.get("unsynced_count"),
        "profile_install_sync_status": sync_rows,
    }


def probe() -> dict[str, object]:
    home = codex_home()
    agents_dir = home / "agents"
    skills_dir = home / "skills"
    standing_templates = skill_root() / "agents" / "standing-officials"
    agent_files = sorted(path.name for path in agents_dir.glob("*.toml")) if agents_dir.exists() else []
    template_files = sorted(path.name for path in standing_templates.glob("*.toml")) if standing_templates.exists() else []
    config = effective_config_agent_summary(home)
    codex_resolution = resolve_codex_executable()
    profile_state = standing_profile_summary(agents_dir, standing_templates)
    degraded: list[str] = []
    config_notices: list[str] = []
    if not skills_dir.exists():
        degraded.append("codex skills directory missing")
    if not agents_dir.exists():
        degraded.append("codex agents directory missing")
    if not config.get("parse_ok"):
        config_notices.append("codex config could not be parsed; compatibility fails closed")
    if not config.get("agents_section"):
        config_notices.append("codex [agents] config missing; install should run ensure_court_agent_config.py --write")
    if not config.get("max_depth") or int(config.get("max_depth") or 0) < RECOMMENDED_AGENT_MAX_DEPTH:
        config_notices.append(f"codex max_depth below recommended {RECOMMENDED_AGENT_MAX_DEPTH}")
    if config.get("config_conflict"):
        config_notices.append("codex agents.max_threads conflicts with enabled features.multi_agent_v2")
    if config.get("deprecated_disable_response_storage_present"):
        config_notices.append("codex disable_response_storage is not accepted by strict config")
    selected_protocol = config.get("selected_protocol")
    if selected_protocol == "v2":
        if not config.get("max_threads") or int(config.get("max_threads") or 0) < RECOMMENDED_AGENT_MAX_THREADS:
            config_notices.append(f"codex V2 total thread ceiling below recommended {RECOMMENDED_AGENT_MAX_THREADS}")
        if not config.get("reserved_spawn_schema_compatible"):
            config_notices.append("codex reserved collaboration.spawn_agent schema is incompatible")
    elif selected_protocol == "v1":
        if not config.get("max_threads") or int(config.get("max_threads") or 0) < RECOMMENDED_AGENT_MAX_THREADS - 1:
            config_notices.append(
                f"codex V1 child thread limit below recommended {RECOMMENDED_AGENT_MAX_THREADS - 1}"
            )
        if not config.get("inactive_v2_config_preserved"):
            config_notices.append("codex inactive V2 rollback table is not fully preserved")
    else:
        config_notices.append("codex multi-agent protocol mode is unresolved")
    if not config.get("protocol_config_ok"):
        config_notices.extend(f"protocol config: {error}" for error in config.get("protocol_config_errors", []))
    host_native_probe_status = (
        "config_preferred"
        if selected_protocol in {"v2", "v1"}
        else "verify_with_minimal_host_action"
    )
    if host_native_probe_status == "verify_with_minimal_host_action":
        config_notices.append(
            "verify with a minimal host spawn/reuse action before deciding dispatch availability"
        )
    compatibility = (
        "preferred_v2_configured"
        if not config_notices and selected_protocol == "v2"
        else "v1_fallback_configured"
        if not config_notices and selected_protocol == "v1"
        else "compatible_below_recommended"
    )
    codex_available = bool(codex_resolution.get("ok")) and bool(
        str(codex_resolution.get("version") or "").strip()
    )
    codex_version: str | None = None
    codex_executable: str | None = None
    supported_pairs: list[dict[str, str]] | None = None
    if codex_available:
        raw_version = str(codex_resolution.get("version") or "")
        codex_version = raw_version.removeprefix("codex-cli ").strip() or None
        codex_executable = str(codex_resolution.get("executable_path") or "") or None
        supported_pairs = [
            {"model": model, "effort": effort}
            for model, effort in sorted(MODEL_MAX_REASONING_EFFORT.items())
        ]
    turn_context_model, turn_context_effort = (
        _latest_turn_context(home) if codex_available else (None, None)
    )
    config_exposes_model = _config_exposes_model(home) if codex_available else None
    payload = {
        "kind": "agent_runtime_probe",
        "runtime": "codex-only",
        "openclaw": "not_used",
        "codex_home": str(home),
        "skill_root": str(skill_root()),
        "commands": {
            "codex": codex_resolution.get("version") or command_version("codex"),
            "codex_resolution": {
                key: codex_resolution.get(key)
                for key in (
                    "ok",
                    "invocation_path_sha256",
                    "executable_path_sha256",
                    "executable_name",
                    "version",
                    "version_match",
                    "exact_native_executable",
                    "resolution_source",
                    "errors",
                )
            },
            "python": sys.version.split()[0],
        },
        "host_proof": {
            "codex_version": codex_version,
            "codex_executable": codex_executable,
            "supported_model_effort_pairs": supported_pairs,
            "config_exposes_model": config_exposes_model,
            "turn_context_model": turn_context_model,
            "turn_context_effort": turn_context_effort,
        },
        "paths": {
            "skills_dir": str(skills_dir),
            "agents_dir": str(agents_dir),
            "standing_templates": str(standing_templates),
        },
        "counts": {
            "agent_files": len(agent_files),
            "standing_templates": len(template_files),
        },
        "config": config,
        "config_compatibility": compatibility,
        "config_notices": config_notices,
        "standing_profiles": profile_state,
        "recommended_config": {
            "max_depth": RECOMMENDED_AGENT_MAX_DEPTH,
            "max_threads": RECOMMENDED_AGENT_MAX_THREADS,
            "legacy_agents_max_threads": "must_be_absent_when_multi_agent_v2_enabled",
            "max_concurrent_threads_per_session": RECOMMENDED_AGENT_MAX_THREADS,
            "effective_child_thread_limit": RECOMMENDED_AGENT_MAX_THREADS - 1,
            "meaning": "bounded host ceiling, not an ordinary-wave dispatch target",
            "remediation": f"python -B scripts/ensure_court_agent_config.py --apply --threads {RECOMMENDED_AGENT_MAX_THREADS}",
            "multi_agent_v2_enabled": True,
            "hide_spawn_agent_metadata": True,
            "reserved_spawn_schema_compatible": True,
            "supported_v1_fallback": {
                "multi_agent_enabled": True,
                "agents_max_threads": RECOMMENDED_AGENT_MAX_THREADS - 1,
                "multi_agent_v2_enabled": False,
                "inactive_v2_config_preserved": True,
            },
            "response_storage_contract": "verify_client_emitted_store_false_with_live_installation_gate",
            "deprecated_disable_response_storage_key": "must_be_absent_under_strict_config",
        },
        "ordinary_dispatch_policy": {
            "topology": "ordinary_parallel",
            "carrier_kind": "child_agent",
            "carrier_dossier_family": "ordinary",
            "presentation_extension_loaded": False,
            "wave_policy": "dynamic_by_duty_and_capacity",
            "static_wave_cap": None,
            "selection_basis": "useful_roles_plus_live_capacity_and_budgets",
            "selection_inputs": "task_duty_dependencies_and_evidence_value",
            "host_capacity_required": True,
            "host_occupancy_required": True,
            "next_depth_required": True,
            "max_depth": RECOMMENDED_AGENT_MAX_DEPTH,
            "max_threads": RECOMMENDED_AGENT_MAX_THREADS,
            "root_thread_counts_toward_limit": True,
            "unknown_capacity_occupancy_or_depth": "fail_closed",
            "ordinary_spawn_delay_seconds": 0.0,
            "default_fork_turns": "none",
            "long_context_threshold_tokens": 32000,
            "long_context_fork_turns": "none",
            "max_recent_fork_turns": 3,
            "deadline_seconds": 600,
            "tool_call_budget": 8,
            "reuse_errored_agents": False,
            "model_route_schema": "court.office.model_route.v2",
            "codex_model_selection": {
                "gpt-5.6-sol": "ultra",
                "gpt-5.6-terra": "ultra",
                "gpt-5.6-luna": "max",
            },
            "model_selection_inputs": ["assignment", "task_focus", "complexity", "risk", "ambiguity"],
            "codex_spawn_metadata_policy": "host_managed_only_when_supported_by_reserved_schema",
            "model_visible_spawn_fields": ["message", "task_name", "fork_turns"],
            "reserved_schema_fallback": "inherit_parent_model_and_effort",
            "claude_code_model_policy": "inherit_main_thread_model",
            "hermes_model_policy": "inherit_main_profile_model_design_deferred",
            "fatal_provider_retry": False,
        },
        "subagent_host": {
            "status": "provided_by_current_codex_session_if_available",
            "host_native_probe_status": host_native_probe_status,
            "next_action_rule": (
                "when diagnostics conflict with the requested parallel workflow, run a minimal host "
                "spawn/reuse check and continue when it succeeds"
            ),
            "contract": "subagente may use standing profile only inside hierarchy, bounds, evidence contract, and active authority",
            "recommended_max_depth": RECOMMENDED_AGENT_MAX_DEPTH,
            "recommended_max_threads": RECOMMENDED_AGENT_MAX_THREADS,
            "static_wave_cap": None,
            "capacity_semantics": "configured threads are advisory and parameterized; actual host capacity/rejection, occupancy, retained nodes, depth, hierarchy, resources, and write-set gates remain authoritative",
            "depth_semantics": "validate every proposed next_depth <= 4; unknown depth fails closed",
        },
        "degraded_reasons": degraded,
    }
    return sanitize_probe_payload(payload, home=home, court_root=skill_root())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args()
    payload = probe()
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"agent_runtime={payload['runtime']} openclaw={payload['openclaw']}")
        print(f"config_compatibility={payload['config_compatibility']}")
        standing = payload["standing_profiles"]
        print(f"standing_profile_validation={standing['validation'].get('ok')}")
        print(f"installed_agent_malformed_count={standing.get('malformed_count')}")
        print(f"installed_agent_unsynced_count={standing.get('unsynced_count')}")
        for notice in payload["config_notices"]:
            print(f"notice: {notice}")
        for reason in payload["degraded_reasons"]:
            print(f"degraded: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
