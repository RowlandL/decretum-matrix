"""Integration-test agente terminal logs, Shiguan facets, and runtime mirroring."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

def run_cli(script: Path, env: dict[str, str], *args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([sys.executable, str(script), *args], text=True, capture_output=True, env=env, check=False)
    if result.returncode != expect:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise AssertionError(f"command {args} returned {result.returncode}, expected {expect}")
    return result


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def create_dispatchable_task(
    cli: Path,
    env: dict[str, str],
    temp_root: Path,
    *,
    task_id: str,
    title: str,
    charter: str,
    gate: dict[str, object],
    capsule: dict[str, object],
) -> dict[str, object]:
    intake = temp_root / f"{task_id}-intake.json"
    capsule_file = temp_root / f"{task_id}-capsule.json"
    intake.write_text(json.dumps(gate), encoding="utf-8")
    capsule_file.write_text(json.dumps(capsule), encoding="utf-8")
    created = json.loads(
        run_cli(
            cli, env, "create", "--task-id", task_id, "--title", title,
            "--charter", charter, "--evidence", "public CLI create",
            "--work-kind", "implementation", "--intake-file", str(intake),
            "--invariant-capsule-file", str(capsule_file), "--format", "json",
        ).stdout
    )
    assert created["task"]["invariant_capsule"] == capsule
    context_payload = json.loads(
        run_cli(
            cli, env, "semantic-context-template", "--task-id", task_id,
            "--format", "json",
        ).stdout
    )
    context_file = temp_root / f"{task_id}-context.json"
    context_file.write_text(json.dumps(context_payload), encoding="utf-8")
    validated = json.loads(
        run_cli(
            cli, env, "semantic-context-validate", "--context-file", str(context_file),
            "--format", "json",
        ).stdout
    )
    assert validated["ok"] is True
    run_cli(
        cli, env, "semantic", "checkpoint", "--task-id", task_id,
        "--context-file", str(context_file), "--trigger", "checkpoint",
        "--actor", "taizi", "--evidence", "public CLI semantic checkpoint",
    )
    verified = json.loads(
        run_cli(
            cli, env, "semantic", "verify", "--task-id", task_id,
            "--context-file", str(context_file), "--trigger", "verify",
            "--actor", "taizi", "--evidence", "public CLI semantic verify",
        ).stdout
    )
    task = verified["result"]["task"]
    assert task["semantic_state"] == "DISPATCHABLE"
    return task


def public_admission_template(
    cli: Path,
    env: dict[str, str],
    temp_root: Path,
    *,
    task_id: str,
    wave_id: str,
    assignment: str,
    task_focus: str,
) -> dict[str, object]:
    payload = json.loads(
        run_cli(
            cli, env,
            "admission-template",
            "--task-id", task_id,
            "--wave-id", wave_id,
            "--role", "hubu",
            "--calling-office", "shangshu",
            "--integration-domain", f"{task_id}-terminal-e2e",
            "--write-path", "work/hubu/0001.txt",
            "--assignment", assignment,
            "--task-focus", task_focus,
            "--evidence", "public CLI admission template",
            "--host-active-agents", "1",
            "--host-capacity", "4",
            "--host-retained-agents", "0",
            "--host-reclamation-status", "verified",
            "--next-depth", "1",
            "--user-agent-budget", "3",
            "--provider-launch-budget", "3",
            "--complexity", "low",
            "--risk", "low",
            "--ambiguity", "low",
            "--transport", "codex",
            "--format", "json",
        ).stdout
    )
    request_file = temp_root / f"{task_id}-{wave_id}-admission.json"
    request_file.write_text(json.dumps(payload["request"]), encoding="utf-8")
    validated = json.loads(
        run_cli(
            cli, env, "admission-validate", "--request-file", str(request_file),
            "--format", "json",
        ).stdout
    )
    assert validated["ok"] is True
    payload["argv"] = validated["argv"]
    return payload


def skill_requirements(repo_root: Path, root: Path) -> str:
    task_skill = root / "task-specific-skill" / "SKILL.md"
    task_skill.parent.mkdir(parents=True)
    task_skill.write_text("# task-specific fixture\n", encoding="utf-8")
    court = repo_root / "SKILL.md"
    items = []
    for name, source in (("decretum-matrix", court), ("task-specific-fixture", task_skill)):
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        items.append({"name": name, "source": str(source.resolve()), "sha256": digest,
                      "purpose": "agente terminal integration", "ack_name": name, "ack_sha256": digest})
    return json.dumps(items)


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

        charter = "isolated public CLI agente terminal fixture"
        host_spawn_marker = temp_root / "host-spawn.marker"
        env["COURT_TEST_HOST_SPAWN_MARKER"] = str(host_spawn_marker)
        invalid_intake = temp_root / "invalid-intake.json"
        invalid_intake.write_text(
            json.dumps({"message_class": "INVALID", "unknown_field": True}),
            encoding="utf-8",
        )
        invalid = json.loads(
            run_cli(
                cli, env, "intake-validate", "--charter", charter,
                "--intake-file", str(invalid_intake), "--format", "json", expect=2,
            ).stdout
        )
        assert invalid["ok"] is False and len(invalid["errors"]) > 4
        assert not runtime_root.exists()
        assert not shared_root.exists()
        assert not host_spawn_marker.exists()

        public_template = json.loads(
            run_cli(cli, env, "intake-template", "--charter", charter, "--format", "json").stdout
        )
        assert public_template["charter"] == charter
        generated_gate = public_template["conversation_gate"]
        generated_capsule = dict(public_template["invariant_capsule"])
        generated_capsule["write_set"] = ["work/hubu/0001.txt"]
        assert generated_gate["message_class"] == "FORMAL_TASK"
        assert len(generated_capsule) == 13

        repo_root = scripts.parent
        requirements_json = skill_requirements(repo_root, temp_root)

        def runtime_snapshot() -> dict[str, bytes]:
            return {
                path.relative_to(runtime_root).as_posix(): path.read_bytes()
                for path in runtime_root.rglob("*")
                if path.is_file()
            }

        for sequence, (action, agent_status) in enumerate(
            (
                ("start", "running"),
                ("spawn", "running"),
                ("heartbeat", "running"),
                ("finish", "completed"),
                ("close", "closed"),
            ),
            start=90,
        ):
            case_env = dict(env)
            case_shared = temp_root / f"invalid-{action}-shared"
            case_host_marker = temp_root / f"invalid-{action}-host.marker"
            case_env["COURT_SHARED_SHIGUAN_ROOT"] = str(case_shared)
            case_env["COURT_TEST_HOST_SPAWN_MARKER"] = str(case_host_marker)
            command = [
                "--court-code", "COURT",
                "--agent-id", f"hubu-invalid-{action}",
                "--office", "hubu",
                "--agent-lineage-path", "zhongshu/hubu",
                "--sequence", str(sequence),
                "--runtime-task-id", f"missing-runtime-{action}",
                "--runtime-action", action,
                "--runtime-role", "hubu",
                "--scope", f"invalid {action} must fail before write",
                "--agent-status", agent_status,
                "--launch", "--dry-run",
                "--format", "json",
            ]
            if action in {"start", "spawn"}:
                command.extend(
                    [
                        "--collaboration-task-name", f"hubu_invalid_{action}",
                        "--skill-requirements-json", requirements_json,
                    ]
                )
            before = runtime_snapshot()
            run_cli(terminal, case_env, *command, expect=1)
            assert runtime_snapshot() == before, f"invalid {action} mutated runtime"
            assert not case_shared.exists(), f"invalid {action} wrote logs or Shiguan evidence"
            assert not case_host_marker.exists(), f"invalid {action} attempted a host spawn"

        create_dispatchable_task(
            cli, env, temp_root, task_id="terminal", title="terminal", charter=charter,
            gate=generated_gate, capsule=generated_capsule,
        )
        admission_payload = public_admission_template(
            cli, env, temp_root,
            task_id="terminal", wave_id="wave-default",
            assignment="terminal test", task_focus="agente terminal regression",
        )
        admission = json.loads(run_cli(cli, env, *admission_payload["argv"]).stdout)
        assert admission["allowed"] is True
        missing_body_env = dict(env)
        missing_body_shared = temp_root / "missing-body-shared"
        missing_body_env["COURT_SHARED_SHIGUAN_ROOT"] = str(missing_body_shared)
        before_missing_body = runtime_snapshot()
        missing_body_result = run_cli(
            terminal, missing_body_env,
            "--court-code", "COURT",
            "--agent-id", "hubu-missing-body",
            "--office", "hubu",
            "--agent-lineage-path", "zhongshu/hubu",
            "--sequence", "89",
            "--body-file", str(temp_root / "does-not-exist.log"),
            "--runtime-task-id", "terminal",
            "--runtime-action", "start",
            "--runtime-role", "hubu",
            "--collaboration-task-name", "hubu_missing_body",
            "--skill-requirements-json", requirements_json,
            "--scope", "terminal test",
            "--launch", "--dry-run",
            "--format", "json",
            expect=1,
        )
        assert "does-not-exist.log" in missing_body_result.stderr, missing_body_result.stderr
        assert runtime_snapshot() == before_missing_body, "missing body mutated runtime"
        assert not missing_body_shared.exists(), "missing body wrote logs or Shiguan evidence"
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
                "hubu-terminal-1",
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
                "--collaboration-task-name",
                "hubu_terminal",
                "--skill-requirements-json",
                requirements_json,
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
        started_binding = json.loads((runtime_root / "tasks.json").read_text(encoding="utf-8"))["terminal"]["agents"]["hubu-terminal-1"]
        assert started_binding["collaboration_task_name"] == "hubu_terminal"
        assert started_binding["role_key"] == "hubu"
        assert started_binding["office_zh"] == "户部"
        assert started_binding["direct_superior"] == "shangshu"
        expected_requirements = {
            item["name"]: item["sha256"] for item in json.loads(requirements_json)
        }
        stored_requirements = {
            item["name"]: item["sha256"]
            for item in started_binding["required_skill_bindings"]
        }
        assert stored_requirements == expected_requirements, (
            stored_requirements,
            expected_requirements,
        )

        create_dispatchable_task(
            cli, env, temp_root, task_id="terminal-spawn", title="terminal spawn", charter=charter,
            gate=generated_gate, capsule=generated_capsule,
        )
        spawn_payload = public_admission_template(
            cli, env, temp_root,
            task_id="terminal-spawn", wave_id="spawn-wave",
            assignment="terminal spawn test",
            task_focus="agente terminal spawn regression",
        )
        spawn_admission = json.loads(run_cli(cli, env, *spawn_payload["argv"]).stdout)
        assert spawn_admission["allowed"] is True
        spawn = json.loads(run_cli(
            terminal, env, "--court-code", "COURT", "--agent-id", "hubu-spawn-1", "--office", "hubu",
            "--agent-lineage-path", "zhongshu/hubu", "--sequence", "4", "--summary", "户部 spawn 镜像",
            "--runtime-task-id", "terminal-spawn", "--runtime-wave-id", "spawn-wave",
            "--runtime-action", "spawn", "--collaboration-task-name", "hubu_spawn",
            "--skill-requirements-json", requirements_json, "--scope", "terminal spawn test", "--format", "json",
        ).stdout)
        assert spawn["runtime_mirror"]["runtime_mirror"] == "spawn"
        spawned_binding = json.loads((runtime_root / "tasks.json").read_text(encoding="utf-8"))["terminal-spawn"]["agents"]["hubu-spawn-1"]
        assert spawned_binding["collaboration_task_name"] == "hubu_spawn"
        assert spawned_binding["office_zh"] == "户部"

        def sha256(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        route_id = admission["model_routes"][
            admission["selected_instance_ids"][0]
        ]["model_route_id"]
        run_cli(
            cli,
            env,
            "agent-preload-ack",
            "--task-id", "terminal",
            "--agent-id", "hubu-terminal-1",
            "--role", "hubu",
            "--office-zh", "户部",
            "--direct-superior", "shangshu",
            "--profile-hash", sha256(repo_root / "agents" / "standing-officials" / "hubu.toml"),
            "--dossier-hash", sha256(repo_root / "agents" / "office-dossiers" / "hubu" / "AGENTS.md"),
            "--court-skill-hash", sha256(repo_root / "SKILL.md"),
            "--loaded-skills", "decretum-matrix",
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
                "hubu-terminal-1",
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
                "hubu-terminal-1",
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
        assert tasks["terminal"]["agents"]["hubu-terminal-1"]["status"] == "closed"
        entries = read_jsonl(shared_root / "references" / "shiguan-index.jsonl")
        assert len(entries) == 4
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
