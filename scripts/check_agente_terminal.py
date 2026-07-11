"""Integration-test agente terminal logs, Shiguan facets, and runtime mirroring."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run_cli(script: Path, env: dict[str, str], *args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([sys.executable, str(script), *args], text=True, capture_output=True, env=env, check=False)
    if result.returncode != expect:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise AssertionError(f"command {args} returned {result.returncode}, expected {expect}")
    return result


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    scripts = Path(__file__).resolve().parent
    terminal = scripts / "agente_terminal.py"
    cli = scripts / "court_cli.py"
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        skill_root = temp_root / "skill"
        runtime_root = temp_root / "runtime"
        shared_root = temp_root / "shared-shiguan"
        env = dict(os.environ)
        env["COURT_SKILL_ROOT"] = str(skill_root)
        env["COURT_RUNTIME_ROOT"] = str(runtime_root)
        env["COURT_SHARED_SHIGUAN_ROOT"] = str(shared_root)

        run_cli(cli, env, "create", "--task-id", "terminal", "--title", "terminal", "--evidence", "create")
        admission = json.loads(
            run_cli(
                cli,
                env,
                "agent-admit",
                "--task-id", "terminal",
                "--wave-id", "wave-default",
                "--execution-topology", "parallel",
                "--protocol-mode", "v2",
                "--active-session-protocol", "v2",
                "--needs-parallel-tree",
                "--requested-fork-turns", "none",
                "--context-tokens", "1000",
                "--message-chars", "256",
                "--message-required-chars", "256",
                "--message-optional-chars", "0",
                "--requested-agents", "1",
                "--requested-roles", "hubu",
                "--host-active-agents", "1",
                "--host-capacity", "4",
                "--host-retained-agents", "0",
                "--host-reclamation-status", "verified",
                "--next-depth", "1",
                "--max-depth", "4",
                "--max-threads", "16",
                "--user-agent-budget", "3",
                "--provider-launch-budget", "3",
                "--assignment", "terminal test",
                "--task-focus", "agente terminal regression",
                "--complexity", "low",
                "--risk", "low",
                "--ambiguity", "low",
                "--transport", "codex",
                "--actor", "shangshu",
                "--evidence", "terminal fixture admission",
                "--format", "json",
            ).stdout
        )
        json_secret = "secret" + "-value"
        quoted_secret = "quoted" + "-secret"
        api_key_name = "api_" + "key"
        password_name = "pass" + "word"
        json_line = json.dumps({api_key_name: json_secret, password_name: quoted_secret})
        first = json.loads(
            run_cli(
                terminal,
                env,
                "--court-code",
                "COURT",
                "--agent-id",
                "agent-1",
                "--office",
                "hubu",
                "--agent-lineage-path",
                "zhongshu/hubu",
                "--sequence",
                "1",
                "--body",
                f"token=secret123\nBearer abc.def\n{json_line}\nnormal line",
                "--summary",
                "户部窗口日志测试",
                "--agent-status",
                "blocked",
                "--launch",
                "--dry-run",
                "--runtime-task-id",
                "terminal",
                "--runtime-action",
                "start",
                "--scope",
                "terminal test",
                "--format",
                "json",
            ).stdout
        )
        metadata = first["metadata"]
        assert metadata["log_id"] == "COURT-AZS-BHB-AGLOG-0001"
        assert metadata["short_title"] == "AZS-BHB 户部 #0001"
        assert metadata["highlight"] == "[ATTN]"
        assert metadata["window_release"] == "preserve_and_highlight"
        assert metadata["terminal_window"] == "DRY_RUN"
        assert "[ATTN]" in metadata["command"]
        first_log = Path(first["log_path"])
        first_text = first_log.read_text(encoding="utf-8")
        assert first_text.splitlines()[0] == "log_id: COURT-AZS-BHB-AGLOG-0001"
        assert "token=[REDACTED]" in first_text
        assert "Bearer [REDACTED]" in first_text
        assert "secret123" not in first_text
        assert json_secret not in first_text
        assert quoted_secret not in first_text
        assert f'"{api_key_name}": [REDACTED]' in first_text
        assert f'"{password_name}": [REDACTED]' in first_text
        assert first["runtime_mirror"]["runtime_mirror"] == "start"

        def sha256(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        route_id = admission["model_routes"]["hubu"]["model_route_id"]
        repo_root = scripts.parent
        run_cli(
            cli,
            env,
            "agent-preload-ack",
            "--task-id", "terminal",
            "--agent-id", "agent-1",
            "--role", "hubu",
            "--office-zh", "户部",
            "--direct-superior", "shangshu",
            "--profile-hash", sha256(repo_root / "agents" / "standing-officials" / "hubu.toml"),
            "--dossier-hash", sha256(repo_root / "agents" / "supercc-dossiers" / "hubu" / "AGENTS.md"),
            "--court-skill-hash", sha256(repo_root / "SKILL.md"),
            "--loaded-skills", "court-capability-router",
            "--agent-dossier-loaded", "YES",
            "--model-route-id", route_id,
            "--model-override-applied", "NO",
            "--inheritance-policy", "inherit_main_thread_model_reserved_schema",
            "--schema", "court.office.preload_ack.v1",
            "--preload-status", "PASSED",
            "--actor", "shangshu",
            "--evidence", "terminal fixture preload",
            "--format", "json",
        )

        second = json.loads(
            run_cli(
                terminal,
                env,
                "--court-code",
                "COURT",
                "--agent-id",
                "agent-1",
                "--office",
                "hubu",
                "--agent-lineage-path",
                "zhongshu/hubu",
                "--sequence",
                "2",
                "--body",
                "token=visible-secret",
                "--summary",
                "户部 token=summary-secret",
                "--agent-status",
                "completed",
                "--full-log-archive",
                "--launch",
                "--dry-run",
                "--auto-close-seconds",
                "0",
                "--runtime-task-id",
                "terminal",
                "--runtime-action",
                "finish",
                "--result",
                "done",
                "--format",
                "json",
            ).stdout
        )
        second_metadata = second["metadata"]
        assert second_metadata["log_id"] == "COURT-AZS-BHB-AGLOG-0002"
        assert second_metadata["window_release"] == "auto_close_after_log_saved"
        assert second_metadata["keep_window"] is False
        assert "Start-Sleep" in second_metadata["command"]
        second_text = Path(second["log_path"]).read_text(encoding="utf-8")
        assert "token=[REDACTED]" in second_text
        assert "visible-secret" not in second_text
        assert second["shiguan_entry"]["full_log_archived"] is False
        assert second["shiguan_entry"]["full_log_archive_requested"] is True
        assert second["shiguan_entry"]["sensitive_data_may_exist"] is False
        assert second["shiguan_entry"]["redaction_enforced"] is True
        assert "summary-secret" not in str(second["shiguan_entry"]["summary"])
        assert "token=[REDACTED]" in str(second["shiguan_entry"]["summary"])

        third = json.loads(
            run_cli(
                terminal,
                env,
                "--court-code",
                "COURT",
                "--agent-id",
                "agent-1",
                "--office",
                "hubu",
                "--agent-lineage-path",
                "zhongshu/hubu",
                "--sequence",
                "3",
                "--summary",
                "户部释放日志测试",
                "--agent-status",
                "closed",
                "--runtime-task-id",
                "terminal",
                "--runtime-action",
                "close",
                "--result",
                "released",
                "--format",
                "json",
            ).stdout
        )
        assert third["metadata"]["log_id"] == "COURT-AZS-BHB-AGLOG-0003"
        assert third["runtime_mirror"]["runtime_mirror"] == "close"

        tasks = json.loads((runtime_root / "tasks.json").read_text(encoding="utf-8"))
        assert "summary-secret" not in json.dumps(tasks, ensure_ascii=False)
        assert tasks["terminal"]["agents"]["agent-1"]["status"] == "closed"
        entries = read_jsonl(shared_root / "references" / "shiguan-index.jsonl")
        assert len(entries) == 3
        first_entry = entries[0]
        assert first_entry["record_type"] == "agente_log"
        assert first_entry["agent_log_court_code"] == "COURT"
        assert first_entry["log_id"] == "COURT-AZS-BHB-AGLOG-0001"
        assert first_entry["keyword_summary_zh"]
        assert "agente谱系分面" in first_entry["facet_dimensions"]
        assert "zhongshu/hubu" in first_entry["facet_dimensions"]["agente谱系分面"]
        assert first_entry["agent_facets"]["agent_status"] == "blocked"
    print("AGENTE_TERMINAL_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
