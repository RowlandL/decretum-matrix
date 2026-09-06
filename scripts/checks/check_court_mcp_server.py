"""Validate the Decretum Matrix stdio MCP facade against modern and legacy wire shapes."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

sys.dont_write_bytecode = True

from court_public_api import court_command_help, court_status, memory_scan, shiguan_archive_dry_run, shiguan_query
from court_public_registry import load_public_tools
import court_mcp_server


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "scripts" / "court_mcp_server.py"
EXPECTED_TOOLS = {
    "court.workflow_status",
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
    "court.workflow_status": "court.court-runtime",
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
    "case_ref": {"court_code": "COURT-20260906-1-AAAA", "charter_revision": 1},
    "plan_ref": None,
    "plan_cursor": "done@revision-1",
    "recovery_checkpoint_id": "event-head:test",
    "shiguan_revision": 1,
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


def _domain_ledger_transaction_checks() -> list[tuple[str, bool]]:
    """Exercise Git write-set isolation and rollback against real temporary repos."""
    from concurrent.futures import ThreadPoolExecutor
    import hashlib
    import tempfile as _tempfile
    from unittest import mock

    import domain_ledger_api
    from domain_ledger_api import domain_ledger_read, domain_ledger_write, ledger_file

    def git_result(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {(result.stderr or result.stdout).strip()}")
        return result

    def git_output(repo: Path, *args: str) -> str:
        return git_result(repo, *args).stdout.strip()

    def git_bytes(repo: Path, *args: str) -> bytes:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed")
        return result.stdout

    def initialize_repo(repo: Path) -> None:
        git_result(repo, "init", "-q")
        git_result(repo, "config", "user.email", "check@local")
        git_result(repo, "config", "user.name", "check")
        (repo / "baseline.txt").write_text("baseline\n", encoding="utf-8")
        git_result(repo, "add", "--", "baseline.txt")
        git_result(repo, "commit", "-q", "-m", "baseline")

    with _tempfile.TemporaryDirectory(prefix="dm-check-ledger-transaction-") as temp_dir:
        repo = Path(temp_dir)
        initialize_repo(repo)
        (repo / "unrelated.txt").write_text("preserve\n", encoding="utf-8")
        git_result(repo, "add", "--", "unrelated.txt")
        created = domain_ledger_write(
            kind="memory",
            operation="create",
            topic="transaction-fixture",
            content="revision one",
            actor="shiguan",
            authority="autonomous",
            write_set=["memory"],
            root=repo,
        )
        ledger_path = ledger_file(repo, "memory")
        created_record = created.get("record", {})
        commit_sha = str(created_record.get("git_commit") or "")
        receipt_ref = created_record.get("git_receipt", {})
        receipt_relative = str(receipt_ref.get("path") or "") if isinstance(receipt_ref, dict) else ""
        receipt_path = repo / receipt_relative
        receipt_value = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else {}
        committed_paths = set(git_output(repo, "show", "--format=", "--name-only", "HEAD").splitlines())
        success_isolated = (
            created.get("ok") is True
            and commit_sha == git_output(repo, "rev-parse", "HEAD")
            and committed_paths == {"domain-ledger/memory.json", receipt_relative}
            and "unrelated.txt" not in committed_paths
            and git_output(repo, "diff", "--cached", "--name-only").splitlines() == ["unrelated.txt"]
            and git_output(repo, "diff", "--name-only") == ""
        )
        success_receipt_consistent = (
            receipt_value.get("ledger_path") == "domain-ledger/memory.json"
            and receipt_value.get("ledger_sha256") == hashlib.sha256(ledger_path.read_bytes()).hexdigest()
            and git_bytes(repo, "show", f"HEAD:domain-ledger/memory.json") == ledger_path.read_bytes()
            and git_bytes(repo, "show", f"HEAD:{receipt_relative}") == receipt_path.read_bytes()
            and git_result(repo, "diff", "--quiet", "HEAD", "--", "domain-ledger/memory.json", receipt_relative, check=False).returncode == 0
            and git_result(repo, "diff", "--cached", "--quiet", "HEAD", "--", "domain-ledger/memory.json", receipt_relative, check=False).returncode == 0
        )

        index_path = Path(git_output(repo, "rev-parse", "--git-path", "index"))
        if not index_path.is_absolute():
            index_path = repo / index_path
        before_head = git_output(repo, "rev-parse", "HEAD")
        before_index = index_path.read_bytes()
        before_ledger = ledger_path.read_bytes()
        real_run = domain_ledger_api.subprocess.run

        def reject_commit(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if command[:3] == ["git", "-C", str(repo)] and len(command) > 3 and command[3] == "commit":
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="fixture commit rejected")
            return real_run(command, **kwargs)

        with mock.patch.object(domain_ledger_api.subprocess, "run", side_effect=reject_commit):
            failed = domain_ledger_write(
                kind="memory",
                operation="update",
                topic="transaction-fixture",
                content="revision two",
                actor="shiguan",
                authority="autonomous",
                write_set=["memory"],
                root=repo,
            )
        failed_commit_restored = (
            failed.get("ok") is False
            and git_output(repo, "rev-parse", "HEAD") == before_head
            and index_path.read_bytes() == before_index
            and ledger_path.read_bytes() == before_ledger
            and git_output(repo, "diff", "--cached", "--name-only").splitlines() == ["unrelated.txt"]
        )

    with _tempfile.TemporaryDirectory(prefix="dm-check-ledger-receipt-") as temp_dir:
        repo = Path(temp_dir)
        initialize_repo(repo)
        receipt_ledger_path = ledger_file(repo, "memory")
        receipt_index_path = Path(git_output(repo, "rev-parse", "--git-path", "index"))
        if not receipt_index_path.is_absolute():
            receipt_index_path = repo / receipt_index_path
        receipt_before_head = git_output(repo, "rev-parse", "HEAD")
        receipt_before_index = receipt_index_path.read_bytes()
        original_write = domain_ledger_api._atomic_write_text
        calls = {"count": 0}

        def fail_receipt_write(path: object, text: object) -> None:
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("fixture receipt persistence failure")
            original_write(path, text)

        with mock.patch.object(domain_ledger_api, "_atomic_write_text", side_effect=fail_receipt_write):
            receipt_failed = domain_ledger_write(
                kind="memory",
                operation="create",
                topic="receipt-fixture",
                content="receipt content",
                actor="shiguan",
                authority="autonomous",
                write_set=["memory"],
                root=repo,
            )
        receipt_failure_atomic = (
            receipt_failed.get("ok") is False
            and "commit_receipt_persist_failed" in str(receipt_failed.get("errors", [{}])[0].get("code") or "")
            and git_output(repo, "rev-parse", "HEAD") == receipt_before_head
            and receipt_index_path.read_bytes() == receipt_before_index
            and not receipt_ledger_path.exists()
            and not list((repo / "domain-ledger" / "receipts").glob("*.json"))
            and git_output(repo, "status", "--porcelain") == ""
        )

    with _tempfile.TemporaryDirectory(prefix="dm-check-ledger-concurrency-") as temp_dir:
        repo = Path(temp_dir)
        initialize_repo(repo)
        shared = {
            "kind": "memory",
            "actor": "shiguan",
            "authority": "autonomous",
            "write_set": ["memory"],
            "root": repo,
        }
        first = domain_ledger_write(operation="create", topic="idempotent", content="one", **shared)
        repeated = domain_ledger_write(operation="create", topic="idempotent", content="one", **shared)
        updated = domain_ledger_write(operation="update", topic="idempotent", content="two", idempotency_key="same-key", **shared)
        repeated_update = domain_ledger_write(operation="update", topic="idempotent", content="two", idempotency_key="same-key", **shared)

        def concurrent_create(topic: str) -> dict[str, Any]:
            return domain_ledger_write(operation="create", topic=topic, content=topic, **shared)

        with ThreadPoolExecutor(max_workers=2) as pool:
            concurrent = list(pool.map(concurrent_create, ("concurrent-a", "concurrent-b")))
        projected = domain_ledger_read("memory", root=repo)
        idempotency_preserved = (
            first.get("ok") is True
            and repeated.get("idempotent") is True
            and repeated.get("record", {}).get("git_commit") == first.get("record", {}).get("git_commit")
            and updated.get("ok") is True
            and repeated_update.get("idempotent") is True
            and repeated_update.get("record", {}).get("git_commit") == updated.get("record", {}).get("git_commit")
        )
        concurrency_serialized = (
            all(result.get("ok") is True for result in concurrent)
            and sorted(int(result.get("record", {}).get("revision") or 0) for result in concurrent) == [3, 4]
            and projected.get("count") == 4
            and all(bool(item.get("git_commit")) for item in projected.get("revisions", []))
            and git_output(repo, "status", "--porcelain") == ""
        )
        sidecar_anchor = domain_ledger_write(operation="create", topic="sidecar-anchor", content="anchor", **shared)
        original_commit = str(sidecar_anchor.get("record", {}).get("git_commit") or "")
        anchor_receipt = sidecar_anchor.get("record", {}).get("git_receipt", {})
        anchor_receipt_relative = str(anchor_receipt.get("path") or "") if isinstance(anchor_receipt, dict) else ""
        anchor_ledger_relative = str(anchor_receipt.get("ledger_path") or "") if isinstance(anchor_receipt, dict) else ""
        anchor_receipt_path = repo / anchor_receipt_relative
        anchor_receipt_path.write_text('{"tampered":true}\n', encoding="utf-8")
        git_result(repo, "add", "--", anchor_receipt_relative)
        git_result(repo, "commit", "-q", "-m", "fixture receipt sidecar change", "--", anchor_receipt_relative)
        later_commit = git_output(repo, "rev-parse", "HEAD")
        projected_after_change = domain_ledger_read("memory", root=repo)
        repeated_after_change = domain_ledger_write(operation="create", topic="sidecar-anchor", content="anchor", **shared)
        original_receipt = json.loads(git_bytes(repo, "show", f"{original_commit}:{anchor_receipt_relative}").decode("utf-8"))
        original_ledger = git_bytes(repo, "show", f"{original_commit}:{anchor_ledger_relative}")
        original_projection = next(
            (item for item in projected_after_change.get("revisions", []) if item.get("topic") == "sidecar-anchor"),
            {},
        )
        sidecar_change_does_not_retarget = (
            original_commit
            and original_commit != later_commit
            and original_projection.get("git_commit") == original_commit
            and repeated_after_change.get("idempotent") is True
            and repeated_after_change.get("record", {}).get("git_commit") == original_commit
            and original_receipt.get("schema") == domain_ledger_api.GIT_RECEIPT_SCHEMA
            and original_receipt.get("transaction_id") == anchor_receipt.get("transaction_id")
            and original_receipt.get("ledger_sha256") == hashlib.sha256(original_ledger).hexdigest()
            and git_output(repo, "status", "--porcelain") == ""
        )

    return [
        ("domain_ledger_commit_isolated_from_unrelated_staged", success_isolated),
        ("domain_ledger_success_receipt_matches_repository", success_receipt_consistent),
        ("domain_ledger_failed_commit_restores_head_file_index", failed_commit_restored),
        ("domain_ledger_receipt_persist_failure_is_atomic", receipt_failure_atomic),
        ("domain_ledger_idempotency_receipts_preserved", idempotency_preserved),
        ("domain_ledger_concurrent_writes_serialized", concurrency_serialized),
        ("domain_ledger_receipt_sidecar_change_cannot_retarget_commit", sidecar_change_does_not_retarget),
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

    # R-08: wire-level schema constraints (minLength/maxLength/minItems/maxItems/
    # enum) declared in the manifest must be enforced by the public registry,
    # not only by the public functions (fail-closed at the boundary).
    from court_public_registry import validate_public_tool_arguments

    tools = load_public_tools()
    constraint_failures: list[str] = []
    cases = [
        ("court.dispatch_plan_validate", {"entries": [{}] * 17}, "entries_above_max_items"),
        ("court.dispatch_plan_validate", {"entries": [], "authority": "approval", "behavior": "serial"}, "entries_below_min_items"),
        ("court.dispatch_plan_validate", {"entries": [LEGAL_DISPATCH_ENTRY], "authority": "evil"}, "authority_must_be_one_of"),
        ("court.dispatch_plan_validate", {"entries": [LEGAL_DISPATCH_ENTRY], "behavior": "evil"}, "behavior_must_be_one_of"),
        ("shiguan.entries_query", {"query": ""}, "query_below_min_length"),
        ("court.intake_validate", {"charter": "x" * 2049, "intake_value": {}}, "charter_above_max_length"),
        ("shiguan.iku_candidates", {"scope": "evil"}, "scope_must_be_one_of"),
        ("court.closeout_checklist", {"task_id": ""}, "task_id_below_min_length"),
    ]
    for name, args, expected in cases:
        tool = tools.get(name)
        if tool is None:
            constraint_failures.append(f"{expected}:tool_missing")
            continue
        try:
            validate_public_tool_arguments(tool, args)
        except (TypeError, ValueError) as exc:
            if expected in str(exc):
                continue
            constraint_failures.append(f"{expected}:wrong_error:{exc}")
        else:
            constraint_failures.append(f"{expected}:not_enforced")
    probes.append(
        (
            "wire_schema_constraints_enforced",
            not constraint_failures,
        )
    )

    # R-10: an internal server exception must produce a generic -32603 message;
    # exception text / internal paths must never be echoed to the MCP client.
    with mock.patch.object(
        court_mcp_server,
        "handle",
        side_effect=RuntimeError("secret-detail"),
    ):
        internal = court_mcp_server._dispatch(
            {"jsonrpc": "2.0", "id": "internal-x", "method": "tools/list", "params": {}},
            {"legacy_initialized": False},
        )
    probes.append(
        (
            "mcp_internal_error_generic_message",
            internal is not None
            and internal.get("error", {}).get("code") == -32603
            and "secret-detail" not in str(internal.get("error", {}).get("message") or ""),
        )
    )
    return probes


def _compact_startup_checks() -> list[tuple[str, bool]]:
    from unittest.mock import patch
    import court_runtime
    from court_public_api import public_dispatch_plan_validation
    task={'task_id':'compact-fixture','state':'ThreeDepartments','owner':'taizi',
          'agent_admissions':{'private_bulk':'x'*100000},'agents':{'bulk':'x'*100000}}
    with patch.object(court_runtime,'list_tasks',return_value=[task]), patch.object(
            court_runtime,'read_events',side_effect=AssertionError('compact status read history')):
        compact=court_status(1,view='compact')['stdout']
        result=court_mcp_server.call_tool('court.status',{'limit':1,'view':'compact'},modern=True)
    assert compact['view']=='compact' and len(json.dumps(compact))<1500
    assert 'agent_admissions' not in json.dumps(compact) and 'recent_events' not in compact
    assert result.get('isError') is not True and result['structuredContent']['api']['stdout']['view']=='compact'
    invalid=court_mcp_server.call_tool('court.status',{'view':'unknown'},modern=True)
    assert invalid.get('isError') is True
    for role in ('shiguan','shiguan-hermes','zaochao','patrol-inspector'):
        result=public_dispatch_plan_validation([{'role':role}],authority='super',behavior='parallel')
        assert result['ok'] is False and result['errors'][0]['code']=='ordinary_native_dispatch_not_supported'
    return [('compact_status_without_history_or_bulk',True),('known_special_lifecycle_not_claimed_as_native',True)]


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
    checks.extend(_domain_ledger_transaction_checks())
    checks.extend(_robustness_probes())
    checks.extend(_compact_startup_checks())
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
