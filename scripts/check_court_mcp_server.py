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
    "court.intake_validate",
    "court.capsule_validate",
    "court.semantic_context_validate",
    "court.dispatch_plan_validate",
    "court.closeout_checklist",
    "shiguan.entries_query",
    "shiguan.iku_candidates",
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
    "court.intake_validate": "court.court-runtime",
    "court.capsule_validate": "court.court-runtime",
    "court.semantic_context_validate": "court.court-runtime",
    "court.dispatch_plan_validate": "court.court-runtime",
    "court.closeout_checklist": "court.court-runtime",
    "shiguan.query": "shiguan.query-shiguan-index",
    "shiguan.entries_query": "shiguan.query-shiguan-index",
    "shiguan.iku_candidates": "shiguan.repair-archive-placeholders",
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
        tools_with_standard_meta = _rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": "legacy-standard-meta",
                "method": "tools/list",
                "params": {"_meta": {"progressToken": "legacy-progress"}},
            },
        )
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
        return {
            "initialize": initialize,
            "tools": tools,
            "tools_with_standard_meta": tools_with_standard_meta,
            "help": help_result,
            "fallback": fallback,
        }
    finally:
        _close(proc)


LEGAL_DISPATCH_ENTRY = {
    "role": "shangshu",
    "office_zh": "尚书省",
    "direct_superior": "taizi",
    "duty": "统合六部",
    "evidence_contract": "court.evidence.v1",
    "parallel_group": "default",
    "visibility": "non_visible",
    "instance_key": "shangshu#0001",
}
SEMANTIC_CONTEXT_VALUE = {
    "authority_revision": 1,
    "authority_sha256": "a" * 64,
    "plan_revision": 1,
    "plan_sha256": "b" * 64,
    "plan_cursor": "done@revision-1",
    "git_fingerprint": "c" * 64,
    "recovery_checkpoint_id": "event-head:test",
    "shiguan_revision": 1,
    "shiguan_fingerprint": "d" * 64,
}


def _structured(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result")
    return result.get("structuredContent", {}) if isinstance(result, dict) else {}


def _legal_intake_value() -> dict[str, Any]:
    """A conversation-gate payload that passes intake validation."""
    from court_intake_gate import minimal_formal_task_example

    return minimal_formal_task_example()


def _legal_capsule_value() -> dict[str, Any]:
    """An invariant capsule payload that passes capsule validation."""
    from court_semantic_continuity import invariant_capsule_template

    return invariant_capsule_template("测试旨意")


def _domain_probe_session() -> dict[str, Any]:
    """Modern-wire session exercising the final seven projected tools plus journal audit."""
    from pathlib import Path as _Path
    from shiguan_paths import reference_path

    journal_root = _Path(reference_path("court-runtime")) / "operation-journal"
    before = {p.name for p in journal_root.glob("*.json")} if journal_root.exists() else set()
    proc = _start()
    try:
        tools = _rpc(proc, _modern_request("domain-tools", "tools/list", params={"cursor": ""}))
        dispatch_pos = _rpc(
            proc,
            _modern_request(
                "domain-dispatch-pos",
                "tools/call",
                params={"name": "court.dispatch_plan_validate", "arguments": {"entries": [LEGAL_DISPATCH_ENTRY]}},
            ),
        )
        dispatch_neg = _rpc(
            proc,
            _modern_request(
                "domain-dispatch-neg",
                "tools/call",
                params={
                    "name": "court.dispatch_plan_validate",
                    "arguments": {
                        "entries": [
                            {
                                "role": "not-a-role",
                                "office_zh": "x",
                                "direct_superior": "y",
                                "duty": "d",
                                "evidence_contract": "e",
                                "parallel_group": "p",
                                "visibility": "non_visible",
                                "instance_key": "not-a-role#0001",
                            }
                        ]
                    },
                },
            ),
        )
        closeout = _rpc(
            proc,
            _modern_request(
                "domain-closeout",
                "tools/call",
                params={"name": "court.closeout_checklist", "arguments": {}},
            ),
        )
        entries = _rpc(
            proc,
            _modern_request(
                "domain-entries",
                "tools/call",
                params={"name": "shiguan.entries_query", "arguments": {"query": "结诏"}},
            ),
        )
        entries_empty = _rpc(
            proc,
            _modern_request(
                "domain-entries-empty",
                "tools/call",
                params={"name": "shiguan.entries_query", "arguments": {"query": "  "}},
            ),
        )
        iku = _rpc(
            proc,
            _modern_request(
                "domain-iku",
                "tools/call",
                params={"name": "shiguan.iku_candidates", "arguments": {}},
            ),
        )
        intake = _rpc(
            proc,
            _modern_request(
                "domain-intake",
                "tools/call",
                params={
                    "name": "court.intake_validate",
                    "arguments": {"charter": "测试旨意", "intake_value": _legal_intake_value()},
                },
            ),
        )
        capsule = _rpc(
            proc,
            _modern_request(
                "domain-capsule",
                "tools/call",
                params={
                    "name": "court.capsule_validate",
                    "arguments": {"charter": "测试旨意", "value": _legal_capsule_value()},
                },
            ),
        )
        semantic_pos = _rpc(
            proc,
            _modern_request(
                "domain-semantic-pos",
                "tools/call",
                params={"name": "court.semantic_context_validate", "arguments": {"value": SEMANTIC_CONTEXT_VALUE}},
            ),
        )
        semantic_neg = _rpc(
            proc,
            _modern_request(
                "domain-semantic-neg",
                "tools/call",
                params={"name": "court.semantic_context_validate", "arguments": {"value": {"plan_cursor": 1}}},
            ),
        )
    finally:
        _close(proc)
    after = {p.name for p in journal_root.glob("*.json")} if journal_root.exists() else set()
    new_journals = sorted(after - before)
    records = []
    for name in new_journals:
        try:
            records.append(json.loads((journal_root / name).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return {
        "tools": tools,
        "dispatch_pos": dispatch_pos,
        "dispatch_neg": dispatch_neg,
        "closeout": closeout,
        "entries": entries,
        "entries_empty": entries_empty,
        "iku": iku,
        "intake": intake,
        "capsule": capsule,
        "semantic_pos": semantic_pos,
        "semantic_neg": semantic_neg,
        "journal_records": records,
    }


def _domain_ledger_checks() -> list[tuple[str, bool]]:
    """Probes for domain write ACL/authority/write_set, revisions, Git commits."""
    import subprocess as _subprocess
    import tempfile as _tempfile
    from pathlib import Path as _Path

    from domain_ledger_api import (
        domain_court_code_preview,
        domain_gbrain_recall,
        domain_ledger_write,
        domain_skill_load_record,
    )
    from court_public_registry import load_public_tools

    tmp = _Path(_tempfile.mkdtemp(prefix="dm-check-ledger-"))
    _subprocess.run(["git", "init", "-q", str(tmp)], check=True)
    _subprocess.run(["git", "-C", str(tmp), "config", "user.email", "check@local"], check=True)
    _subprocess.run(["git", "-C", str(tmp), "config", "user.name", "check"], check=True)

    def commit_count() -> str:
        result = _subprocess.run(
            ["git", "-C", str(tmp), "log", "--oneline"],
            capture_output=True,
            text=True,
        )
        return str(
            len(
                [
                    line
                    for line in result.stdout.splitlines()
                    if line.strip()
                ]
            )
        )

    denied = domain_ledger_write(
        kind="memory", operation="create", topic="t-a", content="c", actor="shiguan",
        authority="approval", write_set=["memory"], root=tmp,
    )
    count_after_denied = commit_count()
    created = domain_ledger_write(
        kind="memory", operation="create", topic="t-a", content="c", actor="shiguan",
        authority="autonomous", write_set=["memory"], root=tmp,
    )
    idempotent = domain_ledger_write(
        kind="memory", operation="create", topic="t-a", content="c", actor="shiguan",
        authority="autonomous", write_set=["memory"], root=tmp,
    )
    updated = domain_ledger_write(
        kind="memory", operation="update", topic="t-a", content="c2", actor="shiguan",
        authority="super", write_set=["memory"], root=tmp, idempotency_key="k-1",
    )
    count_before_failure = commit_count()
    failed = domain_ledger_write(
        kind="memory", operation="update", topic="bad topic!", content="x", actor="shiguan",
        authority="super", write_set=["memory"], root=tmp,
    )
    after_failure = commit_count()
    gbrain = domain_gbrain_recall("结诏")
    preview = domain_court_code_preview("check-topic", "20260831")
    all_read_only = all(tool.side_effect == "read_only" for tool in load_public_tools().values())
    skill_record = domain_skill_load_record(
        actor="shiguan", role="libu", authority="autonomous", write_set=["capability-index"],
        skill_path="plugins/hermes/decretum-matrix", skill_hash="e" * 64,
        selection_reason="index-first: MCP domain capability match", root=tmp,
    )
    skill_bad_hash = domain_skill_load_record(
        actor="shiguan", role="libu", authority="autonomous", write_set=["capability-index"],
        skill_path="plugins/hermes/decretum-matrix", skill_hash="not-a-hash",
        selection_reason="bad hash gate", root=tmp,
    )
    agent_admit_ok = False
    try:
        from court_agent_admission import RoleAdmissionDecision

        decision = RoleAdmissionDecision(
            allowed=True,
            selected_roles=("shiguan",),
            deferred_roles=(),
            reason_codes=("probe",),
            effective_host_capacity=8,
            effective_max_threads=16,
            effective_max_depth=4,
            available_slots=8,
        )
        agent_admit_ok = decision.allowed is True and decision.selected_roles == ("shiguan",)
    except (ImportError, TypeError):
        agent_admit_ok = False
    index_gate_ok = False
    try:
        import subprocess as _sub
        import sys as _sys

        gate = _sub.run(
            [_sys.executable, "-B", "scripts/check_capability_index_gate.py", "--self-test"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        try:
            gate_payload = json.loads(gate.stdout or "{}")
        except json.JSONDecodeError:
            gate_payload = {}
        index_gate_ok = gate.returncode == 0 and gate_payload.get("ok") is True and gate_payload.get("unknown_not_searched") is True
    except (OSError, subprocess.TimeoutExpired):
        index_gate_ok = False
    return [
        ("domain_write_approval_denied", denied.get("ok") is False and any(e.get("code") == "authority_read_only" for e in denied.get("errors", []))),
        ("domain_write_approval_no_commit", count_after_denied == "0"),
        ("domain_write_create_commits", created.get("ok") is True and bool(created.get("record", {}).get("git_commit"))),
        ("domain_write_create_idempotent", idempotent.get("idempotent") is True and idempotent.get("record", {}).get("revision") == 1),
        ("domain_write_update_appends_revision", updated.get("ok") is True and updated.get("record", {}).get("revision") == 2),
        ("domain_write_failure_no_commit", failed.get("ok") is False and after_failure == count_before_failure),
        ("domain_gbrain_recall_readonly_idempotent", gbrain.get("ok") is True and "entries" in gbrain),
        ("domain_court_code_preview_readonly", preview.get("ok") is True and preview.get("preview_only") is True),
        ("domain_write_not_projected_to_mcp", all_read_only),
        (
            "skill_load_record_revision_and_metadata",
            skill_record.get("ok") is True
            and skill_record.get("record", {}).get("metadata", {}).get("skill_hash") == "e" * 64
            and skill_record.get("record", {}).get("metadata", {}).get("role") == "libu"
            and bool(skill_record.get("record", {}).get("git_commit")),
        ),
        ("skill_load_record_bad_hash_rejected", skill_bad_hash.get("ok") is False and any(e.get("code") == "invalid_skill_hash" for e in skill_bad_hash.get("errors", []))),
        ("agent_admit_gate_available", agent_admit_ok),
        ("index_first_gate_queryable", index_gate_ok),
    ]


def _robustness_probes() -> list[tuple[str, bool]]:
    """Fail-closed / audit robustness probes for the MCP facade and domain ledger."""

    from unittest import mock

    probes: list[tuple[str, bool]] = []
    # MCP fail-closed: an internal runtime failure (e.g. OSError) from the
    # shared public API must become an error result (not a bare exception), so
    # handle() still writes the audit journal and the request never crashes.
    with mock.patch.object(
        court_mcp_server,
        "invoke_public_tool",
        side_effect=OSError("synthetic-io"),
    ):
        result = court_mcp_server.call_tool("court.status", {}, modern=True)
    structured = result.get("structuredContent", {}) if isinstance(result, dict) else {}
    probes.append(
        (
            "mcp_call_tool_fails_closed_on_runtime_error",
            result.get("isError") is True
            and structured.get("ok") is False
            and "synthetic-io" in str(structured.get("problem") or ""),
        )
    )

    # Domain ledger: if persisting the git-commit receipt after a successful
    # commit fails, the write must return ok:false (never raise) and must not
    # claim success without the receipt binding.
    import tempfile as _tempfile
    import subprocess as _subprocess
    from pathlib import Path as _Path

    from domain_ledger_api import domain_ledger_write
    import domain_ledger_api

    tmp = _Path(_tempfile.mkdtemp(prefix="dm-check-ledger-flaky-"))
    _subprocess.run(["git", "init", "-q", str(tmp)], check=True)
    _subprocess.run(["git", "-C", str(tmp), "config", "user.email", "check@local"], check=True)
    _subprocess.run(["git", "-C", str(tmp), "config", "user.name", "check"], check=True)
    original_write = domain_ledger_api._atomic_write_text
    calls = {"n": 0}

    def flaky_write(path: object, text: object) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("synthetic-persist")
        return original_write(path, text)

    with mock.patch.object(domain_ledger_api, "_atomic_write_text", side_effect=flaky_write):
        flaky_result = domain_ledger_write(
            kind="memory",
            operation="create",
            topic="t-flaky",
            content="c",
            actor="shiguan",
            authority="autonomous",
            write_set=["memory"],
            root=tmp,
        )
    probes.append(
        (
            "domain_write_commit_receipt_persist_failure_returns_error",
            flaky_result.get("ok") is False
            and any(
                "commit_receipt_persist_failed" in str(item.get("code") or "")
                for item in flaky_result.get("errors", [])
            ),
        )
    )
    return probes


def run() -> dict[str, object]:
    modern = _modern_session()
    legacy = _legacy_session()
    domain = _domain_probe_session()
    modern_tools = _listed(modern["tools"])
    legacy_tools = _listed(legacy["tools"])
    legacy_standard_meta_tools = _listed(legacy["tools_with_standard_meta"])
    modern_status = modern["status"].get("result", {}).get("structuredContent", {})
    modern_memory = modern["memory"].get("result", {}).get("structuredContent", {})
    legacy_help = legacy["help"].get("result", {}).get("structuredContent", {})
    modern_server_info = modern["status"].get("result", {}).get("_meta", {}).get(SERVER_INFO_META_KEY)
    dispatch_pos = _structured(domain["dispatch_pos"])
    dispatch_neg = _structured(domain["dispatch_neg"])
    closeout = _structured(domain["closeout"])
    entries = _structured(domain["entries"])
    iku = _structured(domain["iku"])
    intake = _structured(domain["intake"])
    capsule = _structured(domain["capsule"])
    semantic_pos = _structured(domain["semantic_pos"])
    semantic_neg = _structured(domain["semantic_neg"])
    journal_records = domain["journal_records"]
    dispatch_pos_api = dispatch_pos.get("api", {}) if isinstance(dispatch_pos.get("api"), dict) else {}
    dispatch_neg_api = dispatch_neg.get("api", {}) if isinstance(dispatch_neg.get("api"), dict) else {}
    closeout_api = closeout.get("api", {}) if isinstance(closeout.get("api"), dict) else {}
    entries_api = entries.get("api", {}) if isinstance(entries.get("api"), dict) else {}
    iku_api = iku.get("api", {}) if isinstance(iku.get("api"), dict) else {}
    intake_api = intake.get("api", {}) if isinstance(intake.get("api"), dict) else {}
    capsule_api = capsule.get("api", {}) if isinstance(capsule.get("api"), dict) else {}
    semantic_pos_api = semantic_pos.get("api", {}) if isinstance(semantic_pos.get("api"), dict) else {}
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
            "legacy_standard_meta_does_not_switch_protocol_mode",
            legacy_standard_meta_tools == EXPECTED_TOOLS
            and "error" not in legacy["tools_with_standard_meta"]
            and "resultType" not in legacy["tools_with_standard_meta"].get("result", {}),
        ),
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
        (
            "tool_schemas_have_descriptions",
            all(
                isinstance(item.get("inputSchema", {}).get("properties"), dict)
                and all(
                    isinstance(prop, dict) and str(prop.get("description") or "").strip() and len(str(prop.get("description") or "")) <= 200
                    for prop in item["inputSchema"]["properties"].values()
                )
                for item in domain["tools"].get("result", {}).get("tools", [])
                if isinstance(item, dict)
            ),
        ),
        (
            "final_tool_matrix_visible_modern_and_legacy",
            modern_tools == EXPECTED_TOOLS and legacy_tools == EXPECTED_TOOLS,
        ),
        (
            "dispatch_plan_validate_positive_defaults_approval_serial",
            dispatch_pos_api.get("ok") is True
            and dispatch_pos_api.get("authority") == "approval"
            and dispatch_pos_api.get("behavior") == "serial"
            and dispatch_pos_api.get("entry_count") == 1,
        ),
        (
            "dispatch_plan_validate_negative_reports_violations",
            dispatch_neg_api.get("ok") is False
            and isinstance(dispatch_neg_api.get("errors"), list)
            and dispatch_neg_api["errors"]
            and any(e.get("code") == "dispatch_plan_invalid" for e in dispatch_neg_api["errors"]),
        ),
        (
            "closeout_checklist_fourteen_labels_two_receipt_missing",
            closeout_api.get("ok") is True
            and closeout_api.get("label_count") == 14
            and len(closeout_api.get("checklist", [])) == 14
            and len(closeout_api.get("missing", [])) == 2,
        ),
        (
            "entries_query_metadata_projection",
            entries_api.get("ok") is True
            and isinstance(entries_api.get("matches"), list)
            and all(not any(key in item for key in ("content", "evidence")) for item in entries_api.get("matches", []) if isinstance(item, dict)),
        ),
        (
            "entries_query_empty_query_rejected",
            domain["entries_empty"].get("error", {}).get("code") == -32602
            or (isinstance(entries_empty_api := _structured(domain["entries_empty"]).get("api"), dict) and entries_empty_api.get("ok") is False),
        ),
        (
            "iku_candidates_dry_run_read_only",
            iku_api.get("ok") is True and iku_api.get("dry_run") is True and iku_api.get("write_enabled") is False,
        ),
        (
            "intake_capsule_semantic_validators_positive",
            intake_api.get("ok") is True and capsule_api.get("ok") is True and semantic_pos_api.get("ok") is True,
        ),
        (
            "semantic_context_validator_negative",
            domain["semantic_neg"].get("error", {}).get("code") == -32602
            or (isinstance(semantic_neg_api := _structured(domain["semantic_neg"]).get("api"), dict) and semantic_neg_api.get("ok") is False),
        ),
        (
            "agent_envelope_fields_present",
            all(
                isinstance(_structured(resp), dict)
                and {"ok", "tool", "command_id", "api", "dry_run", "write_enabled"} <= set(_structured(resp))
                for resp in (
                    domain["dispatch_pos"],
                    domain["closeout"],
                    domain["entries"],
                    domain["iku"],
                )
            ),
        ),
        (
            "audit_journal_written_with_digest",
            len(journal_records) >= 4
            and all(rec.get("schema") == "court.operation_journal.v1" and rec.get("task_id") == "mcp" and rec.get("phase") == "mcp-call" for rec in journal_records),
        ),
        (
            "audit_journal_no_raw_args",
            all(
                "plan_cursor" not in json.dumps(rec, ensure_ascii=False)
                and "结诏" not in json.dumps(rec, ensure_ascii=False)
                for rec in journal_records
            ),
        ),
        (
            "audit_journal_unknown_tool_recorded",
            any(rec.get("receipt", {}).get("ok") is False and "missing_arguments" in str(rec.get("receipt", {}).get("error", "")) for rec in journal_records),
        ),
        (
            "audit_journal_actor_recorded",
            any(rec.get("receipt", {}).get("actor") == "decretum-modern-wire-probe" for rec in journal_records),
        ),
    ]
    checks.extend(_domain_ledger_checks())
    checks.extend(_robustness_probes())
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
