"""Regression checks for bounded Codex court agent configuration rendering."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
from types import SimpleNamespace
import sys
from tempfile import TemporaryDirectory
import tomllib
from unittest.mock import patch

sys.dont_write_bytecode = True

import agent_runtime_probe as runtime_probe_module
from ensure_court_agent_config import (
    create_immutable_backup,
    desired_text,
    read_config_settings,
    write_config_update,
)
from check_codex_agent_roles import validate_codex_multi_agent_config
from agent_runtime_probe import (
    config_agent_summary,
    native_config_read_summary,
    parse_codex_wrapper_target,
    probe,
    resolve_codex_executable,
    run_store_false_probe,
    strict_config_file_probe,
    strict_config_text_probe,
    validate_codex_resolution,
    validate_store_false_evidence,
)
from internal_memory_shiguan_bridge import (
    bounded_redacted_excerpt,
    build_report,
    inspect_hermes,
    run_archive,
    select_agents,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-runtime", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    assert parse_codex_wrapper_target(
        '@ECHO off\n"node" "C:\\Users\\Example\\npm\\node_modules\\@openai\\codex\\bin\\codex.js" %*\n'
    ) == Path(r"C:\Users\Example\npm\node_modules\@openai\codex\bin\codex.js")
    nested_desktop_keys = runtime_probe_module._toml_key_names(
        r"""[desktop.open-in-target-preferences]
global = "vscode"
[desktop.open-in-target-preferences.perPath]
'C:\Users\private-user' = "vscode"
"""
    )
    assert all("\\" not in key and ":" not in key for key in nested_desktop_keys)
    assert "desktop.open-in-target-preferences.perPath.<entry>" in nested_desktop_keys
    tool_summary = runtime_probe_module._request_tool_summary(
        {
            "tools": [
                {
                    "type": "function",
                    "name": "spawn_agent",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"},
                            "agent_type": {"type": "string"},
                            "model": {"type": "string"},
                            "reasoning_effort": {"type": "string"},
                            "service_tier": {"type": "string"},
                        },
                        "required": ["message"],
                    },
                }
            ]
        }
    )
    assert tool_summary["tool_names"] == ["spawn_agent"]
    assert tool_summary["agent_tools"] == tool_summary["spawn_agent_tools"]
    assert tool_summary["spawn_agent_tools"][0]["property_keys"] == [
        "agent_type",
        "message",
        "model",
        "reasoning_effort",
        "service_tier",
    ]
    assert all(
        tool_summary["spawn_agent_tools"][0]["schema_marker_presence"][key]
        for key in ("agent_type", "model", "reasoning_effort", "service_tier")
    )
    valid_resolution = {
        "exact_native_executable": True,
        "version_match": True,
        "version": "codex-cli 0.144.1",
        "executable_name": "codex.exe",
    }
    assert validate_codex_resolution(valid_resolution)["ok"] is True
    for mutation in (
        {"exact_native_executable": False},
        {"version_match": False},
        {"version": ""},
        {"executable_name": "codex.cmd"},
    ):
        assert validate_codex_resolution({**valid_resolution, **mutation})["ok"] is False

    raced_stop = SimpleNamespace(returncode=1, stdout="", stderr="process already exited")
    with (
        patch.object(runtime_probe_module.os, "name", "nt"),
        patch.object(runtime_probe_module.shutil, "which", return_value="pwsh"),
        patch.object(runtime_probe_module, "_existing_pids", side_effect=[[1234], []]),
        patch.object(runtime_probe_module.subprocess, "run", return_value=raced_stop),
    ):
        assert runtime_probe_module._stop_owned_pids([1234]) is True

    with (
        patch.object(runtime_probe_module.os, "name", "nt"),
        patch.object(runtime_probe_module.shutil, "which", return_value="pwsh"),
        patch.object(runtime_probe_module, "_existing_pids", side_effect=[[1234], [1234], [1234], [1234]]),
        patch.object(runtime_probe_module.subprocess, "run", return_value=raced_stop),
        patch.object(runtime_probe_module.time, "sleep"),
    ):
        assert runtime_probe_module._stop_owned_pids([1234]) is False

    valid_store_evidence = {
        "client_exit_code": 0,
        "endpoint_loopback": True,
        "listener_bind": "127.0.0.1",
        "total_http_requests": 1,
        "responses_request_count": 1,
        "request_method": "POST",
        "request_path": "/v1/responses",
        "request_content_type": "application/json",
        "store_present": True,
        "store_type": "boolean",
        "store_value": False,
        "duplicate_store_keys": 0,
        "prompt_marker_in_request": True,
        "authorization_present": True,
        "raw_request_archived": False,
        "raw_response_archived": False,
        "headers_archived": False,
        "full_config_archived": False,
        "timeout_triggered": False,
        "cleanup_verified": True,
        "orphan_process_count": 0,
        "listener_closed": True,
        "session_file_count": 0,
        "prompt_marker_matches": 0,
        "response_marker_matches": 0,
        "credential_canary_matches": 0,
    }
    assert validate_store_false_evidence(valid_store_evidence)["ok"] is True
    invalid_mutations = (
        {"store_present": False},
        {"store_type": "string"},
        {"store_value": True},
        {"duplicate_store_keys": 1},
        {"prompt_marker_in_request": False},
        {"authorization_present": False},
        {"total_http_requests": 2},
        {"responses_request_count": 0},
        {"request_method": "GET"},
        {"request_path": "/v1/chat/completions"},
        {"request_content_type": "text/plain"},
        {"client_exit_code": 1},
        {"endpoint_loopback": False},
        {"timeout_triggered": True},
        {"cleanup_verified": False},
        {"orphan_process_count": 1},
        {"listener_closed": False},
        {"session_file_count": 1},
        {"prompt_marker_matches": 1},
        {"response_marker_matches": 1},
        {"credential_canary_matches": 1},
        {"raw_request_archived": True},
        {"raw_response_archived": True},
        {"headers_archived": True},
        {"full_config_archived": True},
    )
    for mutation in invalid_mutations:
        assert validate_store_false_evidence({**valid_store_evidence, **mutation})["ok"] is False

    original = """model = \"gpt-5.6-sol\"
private_marker = \"must-remain-byte-for-byte\"

[features]
goals = true

[agents]
max_depth = 2
max_threads = 6
"""
    rendered = desired_text(original, 4, 16)
    parsed = tomllib.loads(rendered)
    assert parsed["agents"]["max_depth"] == 4
    assert "max_threads" not in parsed["agents"]
    assert parsed["features"]["goals"] is True
    assert parsed["features"]["multi_agent_v2"]["enabled"] is True
    assert parsed["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"] == 16
    assert parsed["features"]["multi_agent_v2"]["hide_spawn_agent_metadata"] is True
    assert 'private_marker = "must-remain-byte-for-byte"' in rendered

    rendered_again = desired_text(rendered, 4, 16)
    assert rendered_again == rendered
    assert rendered.count("[features.multi_agent_v2]") == 1
    assert rendered.count("[agents]") == 1

    current = read_config_settings(rendered)
    assert current["max_depth"] == 4
    assert current["max_threads"] == 16
    assert current["legacy_max_threads"] is None
    assert current["v2_max_concurrent_threads_per_session"] == 16
    assert current["effective_child_thread_limit"] == 15
    assert current["config_conflict"] is False
    assert current["multi_agent_v2_enabled"] is True
    assert current["spawn_agent_metadata_visible"] is False
    assert current["spawn_agent_metadata_hidden"] is True
    assert current["reserved_spawn_schema_compatible"] is True

    v1_text = desired_text(rendered, 4, 16, protocol="v1")
    v1 = tomllib.loads(v1_text)
    assert v1["features"]["multi_agent"] is True
    assert v1["features"]["multi_agent_v2"]["enabled"] is False
    assert v1["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"] == 16
    assert v1["features"]["multi_agent_v2"]["hide_spawn_agent_metadata"] is True
    assert v1["agents"]["max_depth"] == 4
    assert v1["agents"]["max_threads"] == 15
    assert desired_text(v1_text, 4, 16, protocol="auto") == v1_text

    v1_current = read_config_settings(v1_text)
    assert v1_current["selected_protocol"] == "v1"
    assert v1_current["max_threads"] == 15
    assert v1_current["legacy_max_threads"] == 15
    assert v1_current["v2_max_concurrent_threads_per_session"] == 16
    assert v1_current["effective_child_thread_limit"] == 15
    assert v1_current["inactive_v2_config_preserved"] is True
    assert v1_current["reserved_spawn_schema_compatible"] is False

    unresolved_v1_text = v1_text.replace("enabled = false\n", "", 1)
    unresolved_v1 = read_config_settings(unresolved_v1_text)
    assert unresolved_v1["selected_protocol"] is None
    assert tomllib.loads(desired_text(unresolved_v1_text, 4, 16, protocol="auto"))["features"][
        "multi_agent_v2"
    ]["enabled"] is True

    existing = """[features.multi_agent_v2]
enabled = false
max_concurrent_threads_per_session = 4
hide_spawn_agent_metadata = true
min_wait_timeout_ms = 12000

[agents]
max_depth = 4
max_threads = 16
"""
    fixed_text = desired_text(existing, 4, 16)
    fixed = tomllib.loads(fixed_text)
    assert fixed["features"]["multi_agent_v2"]["enabled"] is True
    assert fixed["features"]["multi_agent_v2"]["max_concurrent_threads_per_session"] == 16
    assert fixed["features"]["multi_agent_v2"]["hide_spawn_agent_metadata"] is True
    assert fixed["features"]["multi_agent_v2"]["min_wait_timeout_ms"] == 12000
    assert "max_threads" not in fixed["agents"]
    assert desired_text(fixed_text, 4, 16) == fixed_text

    with TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "config.toml"
        backup_root = Path(temp_dir) / "shared-shiguan-backups"
        config_path.write_bytes(b"exact-config-backup\r\n")
        immutable_backup = create_immutable_backup(config_path, backup_root=backup_root)
        assert immutable_backup.read_bytes() == config_path.read_bytes()
        assert immutable_backup != config_path
        assert immutable_backup.parent == backup_root
        assert immutable_backup.stat().st_mode & stat.S_IWRITE == 0
        second_backup = create_immutable_backup(config_path, backup_root=backup_root)
        assert second_backup != immutable_backup
        assert second_backup.read_bytes() == config_path.read_bytes()
        assert immutable_backup.read_bytes() == b"exact-config-backup\r\n"

        expected = config_path.read_bytes()
        transaction_backup = write_config_update(
            config_path,
            expected,
            fixed_text,
            backup_root=backup_root,
        )
        assert transaction_backup is not None and transaction_backup.read_bytes() == expected
        assert config_path.read_bytes() == fixed_text.encode("utf-8")
        stale_expected = config_path.read_bytes()
        config_path.write_text(v1_text, encoding="utf-8", newline="\n")
        try:
            write_config_update(config_path, stale_expected, fixed_text, backup_root=backup_root)
        except RuntimeError as exc:
            assert "changed since read" in str(exc)
        else:
            raise AssertionError("stale config compare-and-swap was accepted")

        config_path.write_text(existing.replace("enabled = false", "enabled = true"), encoding="utf-8")
        invalid = validate_codex_multi_agent_config(config_path)
        assert invalid["ok"] is False
        assert "agents.max_threads:forbidden_when_multi_agent_v2_enabled" in invalid["errors"]

        config_path.write_text(fixed_text, encoding="utf-8")
        valid = validate_codex_multi_agent_config(config_path)
        assert valid["ok"] is True
        assert valid["legacy_max_threads"] is None
        assert valid["max_concurrent_threads_per_session"] == 16
        assert valid["effective_child_thread_limit"] == 15
        assert valid["spawn_agent_metadata_hidden"] is True
        assert valid["reserved_spawn_schema_compatible"] is True

        config_path.write_text(v1_text, encoding="utf-8")
        valid_v1 = validate_codex_multi_agent_config(config_path)
        assert valid_v1["ok"] is True
        assert valid_v1["selected_protocol"] == "v1"
        assert valid_v1["legacy_max_threads"] == 15
        assert valid_v1["max_concurrent_threads_per_session"] == 16
        assert valid_v1["effective_child_thread_limit"] == 15
        assert valid_v1["inactive_v2_config_preserved"] is True

        v1_probe = config_agent_summary(config_path)
        assert v1_probe["selected_protocol"] == "v1"
        assert v1_probe["max_threads"] == 15
        assert v1_probe["legacy_max_threads"] == 15
        assert v1_probe["max_concurrent_threads_per_session"] == 16
        assert v1_probe["effective_child_thread_limit"] == 15
        assert v1_probe["inactive_v2_config_preserved"] is True
        assert v1_probe["config_conflict"] is False

        config_path.write_text(fixed_text, encoding="utf-8")
        config_probe = config_agent_summary(config_path)
        assert config_probe["legacy_max_threads"] is None
        assert config_probe["max_concurrent_threads_per_session"] == 16
        assert config_probe["effective_child_thread_limit"] == 15
        assert config_probe["config_conflict"] is False
        assert config_probe["spawn_agent_metadata_hidden"] is True
        assert config_probe["reserved_spawn_schema_compatible"] is True
        assert config_probe["deprecated_disable_response_storage_present"] is False

        scoped_text = """# [agents]
[other]
max_depth = 99
max_threads = 99

[agents]
max_depth = 4

[features.multi_agent_v2]
enabled = true
max_concurrent_threads_per_session = 16
hide_spawn_agent_metadata = true
"""
        config_path.write_text(scoped_text, encoding="utf-8")
        scoped = config_agent_summary(config_path)
        assert scoped["parse_ok"] is True
        assert scoped["max_depth"] == 4
        assert scoped["legacy_max_threads"] is None
        assert scoped["config_conflict"] is False

        config_path.write_text("[agents\nmax_depth = 4\n", encoding="utf-8")
        malformed = config_agent_summary(config_path)
        assert malformed["parse_ok"] is False
        assert malformed["agents_section"] is False
        assert malformed["max_depth"] is None
        assert malformed["reserved_spawn_schema_compatible"] is False

        secret_file = Path(temp_dir) / "MEMORY.md"
        secret_file.write_text('{"token":"must-not-escape"}\nraw prompt text', encoding="utf-8")
        try:
            bounded_redacted_excerpt(secret_file, 500)
        except ValueError as exc:
            assert "metadata-only" in str(exc)
        else:
            raise AssertionError("generic redacted excerpts must fail closed")

        config_path.write_text(
            """[features]
memories = "FEATURE_SECRET_CANARY"
goals = "RAW_PROMPT_CANARY"
[memories]
generate_memories = "GENERATE_SECRET_CANARY"
use_memories = true
""",
            encoding="utf-8",
        )
        previous_codex_home = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = temp_dir
        try:
            bridge_report = build_report(
                argparse.Namespace(
                    agents="codex",
                    content_mode="metadata",
                    excerpt_chars=0,
                    hermes_config=None,
                )
            )
        finally:
            if previous_codex_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_codex_home
        bridge_json = json.dumps(bridge_report, ensure_ascii=False)
        assert temp_dir.casefold() not in bridge_json.casefold()
        assert "must-not-escape" not in bridge_json
        assert "raw prompt text" not in bridge_json
        for canary in (
            "FEATURE_SECRET_CANARY",
            "RAW_PROMPT_CANARY",
            "GENERATE_SECRET_CANARY",
        ):
            assert canary not in bridge_json
        codex_flags = bridge_report["agents"]["codex"]["feature_flags"]
        assert codex_flags["features.memories"] is None
        assert codex_flags["features.memories_status"] == "invalid_type"
        assert bridge_report["agents"]["codex"]["effective_internal_memory"] is False

        missing_hermes = inspect_hermes("metadata", 0, Path(temp_dir) / "missing-hermes.yaml")
        assert missing_hermes["built_in_provider"] == "unavailable"
        assert missing_hermes["effective_internal_memory"] is False

        hermes_config = Path(temp_dir) / "hermes-config.yaml"
        hermes_config.write_text(
            """memory:
  memory_enabled: "HERMES_SECRET_CANARY"
  user_profile_enabled: true
  provider: "HERMES_PROMPT_CANARY"
  nested:
    provider: "NESTED_SECRET_CANARY"
""",
            encoding="utf-8",
        )
        hermes_report = inspect_hermes("metadata", 0, hermes_config)
        hermes_json = json.dumps(hermes_report, ensure_ascii=False)
        assert "HERMES_SECRET_CANARY" not in hermes_json
        assert "HERMES_PROMPT_CANARY" not in hermes_json
        assert "NESTED_SECRET_CANARY" not in hermes_json
        assert hermes_report["memory_config"]["memory_enabled"] is None
        assert hermes_report["memory_config"]["memory_enabled_status"] == "invalid_type"
        assert hermes_report["memory_config"]["provider_configured"] is True
        assert hermes_report["effective_internal_memory"] is False

        try:
            select_agents("codxe")
        except ValueError as exc:
            assert "unknown agent" in str(exc)
        else:
            raise AssertionError("unknown bridge agent must fail closed")

        fake_archive = SimpleNamespace(
            returncode=1,
            stdout="ARCHIVE_SECRET_CANARY",
            stderr="ARCHIVE_PROMPT_CANARY",
        )
        archive_args = argparse.Namespace(
            source_agent="codex",
            refresh_mode="none",
            result_json=None,
        )
        with patch("internal_memory_shiguan_bridge.subprocess.run", return_value=fake_archive):
            archive_result = run_archive(bridge_report, archive_args)
        archive_json = json.dumps(archive_result, ensure_ascii=False)
        assert "ARCHIVE_SECRET_CANARY" not in archive_json
        assert "ARCHIVE_PROMPT_CANARY" not in archive_json
        assert str(sys.executable).casefold() not in archive_json.casefold()
        assert archive_result["stdout_archived"] is False
        assert archive_result["stderr_archived"] is False

        incompatible_text = fixed_text.replace(
            "hide_spawn_agent_metadata = true",
            "hide_spawn_agent_metadata = false",
        )
        config_path.write_text(incompatible_text, encoding="utf-8")
        incompatible = validate_codex_multi_agent_config(config_path)
        assert incompatible["ok"] is False
        assert (
            "features.multi_agent_v2.hide_spawn_agent_metadata:must_be_true_for_reserved_schema"
            in incompatible["errors"]
        )

    public_probe = probe()
    public_json = json.dumps(public_probe, ensure_ascii=False)
    assert str(Path.home()).casefold() not in public_json.casefold()

    def string_values(value: object) -> list[str]:
        if isinstance(value, dict):
            return [item for nested in value.values() for item in string_values(nested)]
        if isinstance(value, (list, tuple)):
            return [item for nested in value for item in string_values(nested)]
        return [value] if isinstance(value, str) else []

    assert all(
        re.search(r"(?i)(?:[a-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+)", value) is None
        for value in string_values(public_probe)
    )
    live_payload: dict[str, object] | None = None
    if args.live_runtime:
        resolution = resolve_codex_executable(include_binary_hash=True)
        assert validate_codex_resolution(resolution)["ok"] is True, resolution.get("errors")
        executable_path = Path(str(resolution["executable_path"]))
        unknown_top = strict_config_text_probe(executable_path, "unknown_court_key = true\n")
        assert unknown_top["accepted"] is False
        assert unknown_top["error_class"] == "unknown_configuration_field"
        unknown_provider = strict_config_text_probe(
            executable_path,
            """model_provider = "probe"
[model_providers.probe]
name = "Probe"
base_url = "http://127.0.0.1:9/v1"
wire_api = "responses"
requires_openai_auth = false
unknown_provider_key = true
""",
        )
        assert unknown_provider["accepted"] is False
        assert unknown_provider["error_class"] == "unknown_configuration_field"
        codex_home = Path.home() / ".codex"
        desktop_user_path = codex_home / "config.toml"
        managed_path = codex_home / "managed_config.toml"
        effective_strict_path = managed_path if managed_path.exists() else desktop_user_path
        production_config = strict_config_file_probe(executable_path, effective_strict_path)
        assert production_config["accepted"] is True, production_config["error_class"]
        assert production_config["cleanup_verified"] is True
        assert production_config["orphan_process_count"] == 0
        assert all(
            "\\" not in key and ":" not in key
            for key in production_config["config_key_names"]
        )
        desktop_user_config = strict_config_file_probe(executable_path, desktop_user_path)
        known_desktop_user_drift = False
        if managed_path.exists() and desktop_user_config["accepted"] is False:
            known_desktop_user_drift = desktop_user_config["error_class"] == "unknown_configuration_field"
            assert known_desktop_user_drift is True
        expected_protocol = read_config_settings(effective_strict_path.read_text(encoding="utf-8"))["selected_protocol"]
        native_effective = native_config_read_summary(executable_path, cwd=Path.home())
        assert native_effective["ok"] is True, native_effective.get("errors")
        assert native_effective["selected_protocol"] == expected_protocol
        store_proof = run_store_false_probe(executable_path, agent_protocol="v1")
        assert store_proof["overall_gate"] == "PASSED", store_proof["errors"]
        assert store_proof["multi_agent_protocol"] == "v1"
        assert store_proof["agent_schema_claim_scope"] == "v1_tool_name_and_field_marker_presence_only"
        assert store_proof["agent_tools"]
        v1_spawn = next(
            row for row in store_proof["agent_tools"] if row["name"] in {"multi_agent_v1", "spawn_agent"}
        )
        assert all(
            v1_spawn["schema_marker_presence"][key]
            for key in ("agent_type", "model", "reasoning_effort", "service_tier")
        )
        v2_store_proof = run_store_false_probe(executable_path, agent_protocol="v2")
        assert v2_store_proof["overall_gate"] == "PASSED", v2_store_proof["errors"]
        assert v2_store_proof["agent_schema_claim_scope"] == "v2_reserved_schema_exact"
        v2_spawn = next(
            row for row in v2_store_proof["spawn_agent_tools"]
            if row["name"] in {"collaboration", "spawn_agent"}
        )
        assert all(v2_spawn["schema_marker_presence"][key] for key in ("message", "task_name", "fork_turns"))
        assert not any(
            v2_spawn["schema_marker_presence"][key]
            for key in ("agent_type", "model", "reasoning_effort", "service_tier")
        )
        timeout_proof = run_store_false_probe(
            executable_path,
            timeout_seconds=3.0,
            response_delay_seconds=5.0,
        )
        assert timeout_proof["overall_gate"] == "FAILED"
        assert timeout_proof["timeout_triggered"] is True
        assert timeout_proof["total_http_requests"] == 1
        assert timeout_proof["cleanup_verified"] is True
        assert timeout_proof["orphan_process_count"] == 0
        assert timeout_proof["listener_closed"] is True
        assert timeout_proof["session_file_count"] == 0
        live_payload = {
            "schema": "court.codex-live-agent-config-gate.v1",
            "resolution": {
                key: resolution.get(key)
                for key in (
                    "ok",
                    "invocation_path_sha256",
                    "executable_path_sha256",
                    "executable_name",
                    "executable_sha256",
                    "version",
                    "version_match",
                    "exact_native_executable",
                    "resolution_source",
                )
            },
            "strict_config": production_config,
            "strict_config_source": "managed_overlay" if managed_path.exists() else "desktop_user_config",
            "desktop_user_config_strict": {
                "accepted": desktop_user_config.get("accepted"),
                "error_class": desktop_user_config.get("error_class"),
                "known_user_config_drift": known_desktop_user_drift,
                "cleanup_verified": desktop_user_config.get("cleanup_verified"),
                "orphan_process_count": desktop_user_config.get("orphan_process_count"),
                "full_config_archived": False,
            },
            "strict_negative_tests": {
                "unknown_top_level": unknown_top["error_class"],
                "unknown_provider_field": unknown_provider["error_class"],
            },
            "store_false": store_proof,
            "v2_reserved_schema": v2_store_proof,
            "native_effective_config": native_effective,
            "timeout_cleanup_negative": {
                key: timeout_proof.get(key)
                for key in (
                    "overall_gate",
                    "timeout_triggered",
                    "total_http_requests",
                    "orphan_process_count",
                    "listener_closed",
                    "session_file_count",
                )
            },
            "overall_gate": "PASSED",
        }
    if args.format == "json":
        print(json.dumps(live_payload or {"overall_gate": "PASSED", "live_runtime": False}, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("COURT_AGENT_CONFIG_LIVE_OK" if live_payload is not None else "COURT_AGENT_CONFIG_SELF_TEST_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
