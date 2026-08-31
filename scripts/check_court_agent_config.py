"""Regression checks for bounded Codex court agent configuration rendering."""

from __future__ import annotations

import argparse
from contextlib import closing, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from types import SimpleNamespace
import sys
from tempfile import TemporaryDirectory
import tomllib
from unittest.mock import patch

sys.dont_write_bytecode = True

import agent_runtime_probe as runtime_probe_module
import ensure_court_agent_config as agent_config_module
from ensure_court_agent_config import (
    create_immutable_backup,
    desired_text,
    read_config_settings,
    write_config_update,
)
from check_codex_agent_roles import validate_codex_multi_agent_config
from check_catalog import check_codex_config
from agent_runtime_probe import (
    config_agent_summary,
    effective_config_agent_summary,
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


def _write_cc_switch_fixture(
    path: Path,
    *,
    version: str | None,
    token_semantics_column: str = "input_token_semantics",
) -> None:
    connection = sqlite3.connect(path)
    try:
        is_317 = bool(version and version.startswith("3.17."))
        is_316 = bool(version and version.startswith("3.16."))
        user_version = 13 if is_317 else 11 if is_316 else 99
        connection.execute(f"PRAGMA user_version = {user_version}")
        if is_317:
            connection.execute(
                "CREATE TABLE profiles ("
                "id TEXT PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL, "
                "sort_order INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute(
                f"CREATE TABLE proxy_request_logs (id INTEGER PRIMARY KEY, {token_semantics_column} TEXT NOT NULL)"
            )
            connection.execute(
                f"CREATE TABLE usage_daily_rollups (id INTEGER PRIMARY KEY, {token_semantics_column} TEXT NOT NULL)"
            )
        elif is_316:
            connection.execute("CREATE TABLE profiles (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            connection.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        else:
            connection.execute("CREATE TABLE profiles (id TEXT PRIMARY KEY, payload BLOB)")

        if is_316 or is_317:
            payload = {
                "tool": "codex",
                "config_toml": "[agents]\nmax_depth = 2\nmax_threads = 6\n",
                "provider_secret": "CONTROLLER_SECRET_CANARY",
                "unknown_controller_key": "preserve-controller",
            }
            if is_317:
                connection.execute(
                    "INSERT INTO profiles VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        "fixture-codex",
                        "Fixture Codex",
                        json.dumps(payload, sort_keys=True),
                        0,
                        "2026-07-15T00:00:00Z",
                        "2026-07-15T00:00:00Z",
                    ),
                )
            else:
                connection.execute(
                    "INSERT INTO profiles(id, payload) VALUES (?, ?)",
                    ("fixture-codex", json.dumps(payload, sort_keys=True)),
                )
            connection.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?)",
                ("current_profile_id_codex", "fixture-codex"),
            )
        connection.commit()
    finally:
        connection.close()


def _write_effective_pair(root: Path) -> tuple[Path, Path]:
    config_path = root / "home" / ".codex" / "config.toml"
    managed_path = root / "home" / ".codex" / "managed_config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        'model_provider = "fixture"\napi_key = "CONFIG_SECRET_CANARY"\n'
        'unknown_top = "preserve-config"\n[agents]\nmax_depth = 2\nmax_threads = 6\n',
        encoding="utf-8",
    )
    managed_path.write_text(
        'managed_unknown = "preserve-managed"\n[agents]\nmax_depth = 2\n'
        '[features.multi_agent_v2]\nenabled = true\n'
        'max_concurrent_threads_per_session = 8\nhide_spawn_agent_metadata = true\n',
        encoding="utf-8",
    )
    return config_path, managed_path


def _run_agent_config_main(arguments: list[str]) -> tuple[int, str]:
    output = StringIO()
    with redirect_stdout(output):
        result = agent_config_module.main(arguments)
    return result, output.getvalue()


def _lane_e_config_contract() -> None:
    errors: list[str] = []
    parser_factory = getattr(agent_config_module, "build_parser", None)
    reconcile = getattr(agent_config_module, "reconcile_agent_config", None)
    if not callable(parser_factory):
        errors.append("missing build_parser for parameterized --threads N")
    else:
        parsed_default = parser_factory().parse_args(["--check"])
        parsed_explicit = parser_factory().parse_args(["--check", "--threads", "48"])
        if parsed_default.threads != 16:
            errors.append(f"default normal parallel limit was {parsed_default.threads!r}, expected 16")
        if parsed_explicit.threads != 48:
            errors.append("--threads 48 was not preserved")

    rendered_48 = desired_text("[agents]\nmax_depth = 2\nmax_threads = 6\n", 4, 48)
    rendered_settings = read_config_settings(rendered_48)
    if rendered_settings.get("v2_max_concurrent_threads_per_session") != 48:
        errors.append("desired_text hard-clamped explicit threads above 16")

    if callable(reconcile):
        with TemporaryDirectory(prefix="court-lane-e-config-") as temp_dir:
            root = Path(temp_dir)
            config_path, managed_path = _write_effective_pair(root)
            backup_root = root / "backups"
            original_config = config_path.read_bytes()
            original_managed = managed_path.read_bytes()

            legacy_root = root / "legacy-bypass"
            legacy_config, legacy_managed = _write_effective_pair(legacy_root)
            legacy_before = (legacy_config.read_bytes(), legacy_managed.read_bytes())
            legacy_code, legacy_output = _run_agent_config_main(
                [
                    "--config",
                    str(legacy_config),
                    "--managed-config",
                    str(legacy_managed),
                    "--backup-root",
                    str(legacy_root / "backups"),
                    "--managed-overlay",
                    "--apply",
                    "--protocol",
                    "v1",
                    "--threads",
                    "32",
                ]
            )
            legacy_after = (legacy_config.read_bytes(), legacy_managed.read_bytes())
            if legacy_code == 0 or "AGENT_CONFIG_UPDATED" in legacy_output:
                errors.append("legacy --managed-overlay --apply still reports a single-layer update")
            if legacy_before != legacy_after:
                errors.append("legacy --managed-overlay --apply mutated a single effective layer")

            v1_root = root / "v1-apply"
            v1_config, v1_managed = _write_effective_pair(v1_root)
            v1_before = (v1_config.read_bytes(), v1_managed.read_bytes())
            v1_code, v1_output = _run_agent_config_main(
                [
                    "--config",
                    str(v1_config),
                    "--managed-config",
                    str(v1_managed),
                    "--backup-root",
                    str(v1_root / "backups"),
                    "--apply",
                    "--protocol",
                    "v1",
                    "--threads",
                    "32",
                ]
            )
            if v1_code == 0 or "AGENT_CONFIG_UPDATED" in v1_output:
                errors.append("V1 apply did not fail closed")
            if v1_before != (v1_config.read_bytes(), v1_managed.read_bytes()):
                errors.append("V1 apply changed effective config files")

            v1_catalog = root / "v1-catalog.toml"
            v1_catalog.write_text(desired_text("", 2, 4, protocol="v1"), encoding="utf-8")
            v1_notices = check_codex_config(v1_catalog)
            if any("--managed-overlay --apply" in notice or "--managed-overlay --write" in notice for notice in v1_notices):
                errors.append("check_catalog still recommends the legacy single-layer apply bypass")

            reminder = reconcile(
                config_path=config_path,
                managed_config_path=managed_path,
                threads=32,
                max_depth=4,
                apply=False,
                backup_root=backup_root,
            )
            if reminder.get("status") != "REMINDER_ONLY":
                errors.append(f"low parallel check was blocking or silent: {reminder!r}")
            if reminder.get("blocking") is not False or reminder.get("compliance_claimed") is not False:
                errors.append("low parallel reminder did not remain explicit and nonblocking")
            if config_path.read_bytes() != original_config or managed_path.read_bytes() != original_managed:
                errors.append("check mode mutated effective config fixtures")
            low_notices = check_codex_config(managed_path)
            if not any("THREADS_BELOW_RECOMMENDED" in notice for notice in low_notices):
                errors.append("low parallel config did not produce an explicit optional notice")

            controller = root / "cc-switch.db"
            _write_cc_switch_fixture(controller, version="3.17.0")
            native_calls: list[int] = []

            def native_read(_config: Path, _managed: Path) -> dict[str, object]:
                native_calls.append(1)
                return {
                    "ok": True,
                    "max_depth": 4,
                    "max_concurrent_threads_per_session": 48,
                }

            applied = reconcile(
                config_path=config_path,
                managed_config_path=managed_path,
                threads=48,
                max_depth=4,
                apply=True,
                backup_root=backup_root,
                controller_db=controller,
                controller_version="3.17.0",
                native_read=native_read,
            )
            if applied.get("status") != "UPDATED" or applied.get("compliance_claimed") is not True:
                errors.append(f"known controller apply did not complete: {applied!r}")
            for field in ("restart_required", "restart_deferred", "tasks_continued"):
                if applied.get(field) is not True:
                    errors.append(f"post-apply {field} was not true")
            if applied.get("process_control_calls") != 0:
                errors.append("apply invoked process control")
            if native_calls != [1] or applied.get("native_read_verified") is not True:
                errors.append("apply did not finish with injected native-read verification")
            for path in (config_path, managed_path):
                parsed = tomllib.loads(path.read_text(encoding="utf-8"))
                features = parsed.get("features") if isinstance(parsed, dict) else None
                multi_agent_v2 = features.get("multi_agent_v2") if isinstance(features, dict) else None
                if (
                    not isinstance(multi_agent_v2, dict)
                    or multi_agent_v2.get("max_concurrent_threads_per_session") != 48
                ):
                    errors.append(f"effective file did not preserve --threads 48: {path.name}")
                agents = parsed.get("agents") if isinstance(parsed, dict) else None
                if isinstance(agents, dict) and "max_threads" in agents:
                    errors.append(f"legacy max_threads survived in {path.name}")
            runtime_summary = config_agent_summary(config_path)
            if (
                runtime_summary.get("selected_protocol") != "v2"
                or runtime_summary.get("max_concurrent_threads_per_session") != 48
                or runtime_summary.get("protocol_config_ok") is not True
            ):
                errors.append(f"runtime probe did not preserve threads=48: {runtime_summary!r}")
            if check_codex_config(config_path):
                errors.append("config above the 32-thread recommendation was treated as invalid")
            effective_text = config_path.read_text(encoding="utf-8") + managed_path.read_text(encoding="utf-8")
            for canary in ("CONFIG_SECRET_CANARY", "preserve-config", "preserve-managed"):
                if canary not in effective_text:
                    errors.append(f"effective config lost preserved field {canary}")
            with closing(
                sqlite3.connect(f"file:{controller.as_posix()}?mode=ro", uri=True)
            ) as connection:
                payload = json.loads(
                    connection.execute(
                        "SELECT payload FROM profiles WHERE id = ?", ("fixture-codex",)
                    ).fetchone()[0]
                )
            if read_config_settings(payload["config_toml"]).get("max_threads") != 48:
                errors.append("controller profile was not updated before effective files")
            for canary in ("CONTROLLER_SECRET_CANARY", "preserve-controller"):
                if canary not in json.dumps(payload, sort_keys=True):
                    errors.append(f"controller update lost preserved field {canary}")
            events = list(applied.get("events") or [])
            required_order = [
                "controller_probed",
                "controller_backup_created",
                "controller_updated",
                "effective_files_updated",
                "effective_files_verified",
                "native_read_verified",
            ]
            positions = [events.index(item) for item in required_order if item in events]
            if len(positions) != len(required_order) or positions != sorted(positions):
                errors.append(f"controller/effective/native order invalid: {events!r}")

            before_second = (config_path.read_bytes(), managed_path.read_bytes(), controller.read_bytes())
            second = reconcile(
                config_path=config_path,
                managed_config_path=managed_path,
                threads=48,
                max_depth=4,
                apply=True,
                backup_root=backup_root,
                controller_db=controller,
                controller_version="3.17.0",
                native_read=native_read,
            )
            after_second = (config_path.read_bytes(), managed_path.read_bytes(), controller.read_bytes())
            if second.get("status") != "ALREADY_COMPLIANT" or before_second != after_second:
                errors.append("one-click apply was not idempotent")

            unknown = root / "cc-switch-unknown.db"
            _write_cc_switch_fixture(unknown, version=None)
            unknown_before = unknown.read_bytes()
            refused = reconcile(
                config_path=config_path,
                managed_config_path=managed_path,
                threads=64,
                max_depth=4,
                apply=True,
                backup_root=backup_root,
                controller_db=unknown,
                controller_version="3.18.0",
                native_read=native_read,
            )
            if refused.get("status") != "REMINDER_ONLY" or refused.get("compliance_claimed") is not False:
                errors.append("unknown CC Switch schema did not fail closed")
            if unknown.read_bytes() != unknown_before:
                errors.append("unknown CC Switch schema was guessed or mutated")

            for label, semantics_column in (
                ("legacy-input-tokens", "input_tokens"),
                ("wrong-semantics-column", "token_semantics"),
            ):
                semantic_root = root / label
                semantic_config, semantic_managed = _write_effective_pair(semantic_root)
                semantic_controller = semantic_root / "cc-switch.db"
                _write_cc_switch_fixture(
                    semantic_controller,
                    version="3.17.0",
                    token_semantics_column=semantics_column,
                )
                semantic_before = (
                    semantic_config.read_bytes(),
                    semantic_managed.read_bytes(),
                    semantic_controller.read_bytes(),
                )
                semantic_result = reconcile(
                    config_path=semantic_config,
                    managed_config_path=semantic_managed,
                    threads=48,
                    max_depth=4,
                    apply=True,
                    backup_root=semantic_root / "backups",
                    controller_db=semantic_controller,
                    controller_version="3.17.0",
                    native_read=native_read,
                )
                semantic_after = (
                    semantic_config.read_bytes(),
                    semantic_managed.read_bytes(),
                    semantic_controller.read_bytes(),
                )
                if (
                    semantic_result.get("status") != "REMINDER_ONLY"
                    or semantic_result.get("compliance_claimed") is not False
                    or semantic_before != semantic_after
                ):
                    errors.append(
                        f"CC Switch 3.17 {label} did not fail closed on unproven input_token_semantics"
                    )

            locator = getattr(agent_config_module, "default_cc_switch_db_path", None)
            if not callable(locator):
                errors.append("ordinary apply has no automatic CC Switch discovery contract")
            else:
                for version, requested_threads in (("3.16.5", 36), ("3.17.0", 48)):
                    auto_root = root / f"auto-{version}"
                    auto_config, auto_managed = _write_effective_pair(auto_root)
                    auto_controller = auto_root / ".cc-switch" / "cc-switch.db"
                    auto_controller.parent.mkdir(parents=True)
                    _write_cc_switch_fixture(auto_controller, version=version)
                    auto_native_calls: list[int] = []

                    def auto_native_read(
                        _config: Path,
                        _managed: Path,
                        *,
                        expected: int = requested_threads,
                    ) -> dict[str, object]:
                        auto_native_calls.append(expected)
                        return {
                            "ok": True,
                            "max_depth": 4,
                            "max_concurrent_threads_per_session": expected,
                        }

                    with patch.object(
                        agent_config_module,
                        "default_cc_switch_db_path",
                        return_value=auto_controller,
                    ):
                        auto_applied = reconcile(
                            config_path=auto_config,
                            managed_config_path=auto_managed,
                            threads=requested_threads,
                            max_depth=4,
                            apply=True,
                            backup_root=auto_root / "backups",
                            controller_version=version,
                            native_read=auto_native_read,
                        )
                    if auto_applied.get("status") != "UPDATED":
                        errors.append(f"auto-discovered CC Switch {version} did not apply safely: {auto_applied!r}")
                    if auto_native_calls != [requested_threads]:
                        errors.append(f"auto-discovered CC Switch {version} skipped native read")
                    auto_events = list(auto_applied.get("events") or [])
                    required_auto_order = [
                        "controller_auto_discovered",
                        "controller_probed",
                        "controller_updated",
                        "effective_files_updated",
                        "native_read_verified",
                    ]
                    auto_positions = [auto_events.index(item) for item in required_auto_order if item in auto_events]
                    if len(auto_positions) != len(required_auto_order) or auto_positions != sorted(auto_positions):
                        errors.append(f"auto-discovered controller-first order invalid for {version}: {auto_events!r}")

                unversioned_root = root / "auto-unversioned-known-schema"
                unversioned_config, unversioned_managed = _write_effective_pair(unversioned_root)
                unversioned_controller = unversioned_root / ".cc-switch" / "cc-switch.db"
                unversioned_controller.parent.mkdir(parents=True)
                _write_cc_switch_fixture(unversioned_controller, version="3.17.0")
                unversioned_before = (
                    unversioned_config.read_bytes(),
                    unversioned_managed.read_bytes(),
                    unversioned_controller.read_bytes(),
                )
                unversioned_native_calls: list[int] = []

                def unversioned_native_read(_config: Path, _managed: Path) -> dict[str, object]:
                    unversioned_native_calls.append(1)
                    return {
                        "ok": True,
                        "max_depth": 4,
                        "max_concurrent_threads_per_session": 48,
                    }

                with patch.object(
                    agent_config_module,
                    "default_cc_switch_db_path",
                    return_value=unversioned_controller,
                ):
                    unversioned_result = reconcile(
                        config_path=unversioned_config,
                        managed_config_path=unversioned_managed,
                        threads=48,
                        max_depth=4,
                        apply=True,
                        backup_root=unversioned_root / "backups",
                        native_read=unversioned_native_read,
                    )
                unversioned_after = (
                    unversioned_config.read_bytes(),
                    unversioned_managed.read_bytes(),
                    unversioned_controller.read_bytes(),
                )
                if (
                    unversioned_result.get("status") != "REMINDER_ONLY"
                    or unversioned_result.get("reason") != "unknown_controller_version"
                    or unversioned_result.get("compliance_claimed") is not False
                    or unversioned_before != unversioned_after
                    or unversioned_native_calls
                ):
                    errors.append("auto-discovered controller schema substituted for missing app-version evidence")

                auto_unknown_root = root / "auto-unknown"
                auto_unknown_config, auto_unknown_managed = _write_effective_pair(auto_unknown_root)
                auto_unknown_controller = auto_unknown_root / ".cc-switch" / "cc-switch.db"
                auto_unknown_controller.parent.mkdir(parents=True)
                _write_cc_switch_fixture(auto_unknown_controller, version=None)
                auto_unknown_before = (
                    auto_unknown_config.read_bytes(),
                    auto_unknown_managed.read_bytes(),
                    auto_unknown_controller.read_bytes(),
                )
                with patch.object(
                    agent_config_module,
                    "default_cc_switch_db_path",
                    return_value=auto_unknown_controller,
                ):
                    auto_refused = reconcile(
                        config_path=auto_unknown_config,
                        managed_config_path=auto_unknown_managed,
                        threads=48,
                        max_depth=4,
                        apply=True,
                        backup_root=auto_unknown_root / "backups",
                        native_read=native_read,
                    )
                auto_unknown_after = (
                    auto_unknown_config.read_bytes(),
                    auto_unknown_managed.read_bytes(),
                    auto_unknown_controller.read_bytes(),
                )
                if auto_refused.get("status") != "REMINDER_ONLY" or auto_unknown_before != auto_unknown_after:
                    errors.append("auto-discovered unknown CC Switch schema did not fail closed with zero writes")
    else:
        errors.append("missing reconcile_agent_config one-click check/apply API")

    install_text = (Path(__file__).resolve().parents[1] / "references" / "install.md").read_text(encoding="utf-8")
    install_contract = (
        "shared_root=%USERPROFILE%\\.agents\\court-shiguan\\decretum-matrix\\references",
        "probe_before_write=true",
        "install_current_tool_only=true",
        "unapproved_other_tools=REMINDER_ONLY",
        "auto_start_obsidian=false",
        "auto_start_daemon=false",
        "auto_install_dependencies=false",
        "restart_required=true",
        "restart_deferred=true",
        "tasks_continued=true",
        "restart_requires_latest_explicit_authority=true",
        "input_token_semantics",
        "Schema alone is not application-version evidence",
    )
    missing_install_contract = [token for token in install_contract if token not in install_text]
    if missing_install_contract:
        errors.append(f"install blank-host/current-tool/restart contract missing: {missing_install_contract!r}")

    if errors:
        raise AssertionError("LANE_E_CONFIG_RED\n- " + "\n- ".join(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-runtime", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    _lane_e_config_contract()
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
        assert immutable_backup.parent == backup_root.resolve()
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

        codex_home = Path(temp_dir) / "home" / ".codex"
        codex_home.mkdir(parents=True)
        (codex_home / "config.toml").write_text(fixed_text, encoding="utf-8")
        (codex_home / "managed_config.toml").write_text("", encoding="utf-8")
        effective_probe = effective_config_agent_summary(codex_home)
        assert effective_probe["effective_config_source"] == "config.toml"
        assert effective_probe["selected_protocol"] == "v2"
        assert effective_probe["multi_agent_v2_enabled"] is True
        assert effective_probe["reserved_spawn_schema_compatible"] is True
        assert effective_probe["managed_overlay"]["used"] is False
        assert effective_probe["managed_overlay"]["reason"] == "empty_overlay"
        role_config_probe = validate_codex_multi_agent_config(
            codex_home / "config.toml",
            codex_home / "managed_config.toml",
        )
        assert role_config_probe["selected_protocol"] == "v2"
        assert role_config_probe["multi_agent_v2_enabled"] is True

        for managed_text, expected_reason in (
            ("[ui]\ntheme = 'dark'\n", "no_protocol_material"),
            ("[agents]\nmax_depth = 4\n", "no_protocol_material"),
        ):
            (codex_home / "config.toml").write_text(fixed_text, encoding="utf-8")
            (codex_home / "managed_config.toml").write_text(managed_text, encoding="utf-8")
            effective_probe = effective_config_agent_summary(codex_home)
            assert effective_probe["effective_config_source"] == "config.toml"
            assert effective_probe["selected_protocol"] == "v2"
            assert effective_probe["managed_overlay"]["used"] is False
            assert effective_probe["managed_overlay"]["reason"] == expected_reason
            role_config_probe = validate_codex_multi_agent_config(
                codex_home / "config.toml",
                codex_home / "managed_config.toml",
            )
            assert role_config_probe["selected_protocol"] == "v2"
            assert role_config_probe["multi_agent_v2_enabled"] is True

        (codex_home / "managed_config.toml").write_text("[features.multi_agent_v2\n", encoding="utf-8")
        malformed_overlay = effective_config_agent_summary(codex_home)
        assert malformed_overlay["effective_config_source"] == "managed_config.toml"
        assert malformed_overlay["managed_overlay"]["used"] is True
        assert malformed_overlay["managed_overlay"]["reason"] == "nonempty_parse_failure"

        (codex_home / "config.toml").write_text(fixed_text, encoding="utf-8")
        (codex_home / "managed_config.toml").write_text("", encoding="utf-8")
        previous_codex_home_for_probe = os.environ.get("CODEX_HOME")
        try:
            os.environ["CODEX_HOME"] = str(codex_home)
            payload = probe()
        finally:
            if previous_codex_home_for_probe is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_codex_home_for_probe
        assert payload["config"]["effective_config_source"] == "config.toml"
        assert payload["config"]["selected_protocol"] == "v2"
        assert payload["subagent_host"]["host_native_probe_status"] == "config_preferred"

        (codex_home / "config.toml").write_text("", encoding="utf-8")
        (codex_home / "managed_config.toml").write_text("", encoding="utf-8")
        previous_codex_home_for_probe = os.environ.get("CODEX_HOME")
        try:
            os.environ["CODEX_HOME"] = str(codex_home)
            diagnostic_payload = probe()
        finally:
            if previous_codex_home_for_probe is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_codex_home_for_probe
        assert diagnostic_payload["subagent_host"]["host_native_probe_status"] == "verify_with_minimal_host_action"
        assert any(
            "minimal host spawn/reuse" in notice
            for notice in diagnostic_payload["config_notices"]
        )

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

    host_proof = public_probe.get("host_proof")
    assert isinstance(host_proof, dict), "probe must expose host_proof"
    assert set(host_proof) == {
        "codex_version",
        "codex_executable",
        "supported_model_effort_pairs",
        "config_exposes_model",
        "turn_context_model",
        "turn_context_effort",
    }, "host_proof field set mismatch"
    if host_proof["codex_version"] is not None:
        pairs = host_proof["supported_model_effort_pairs"]
        assert isinstance(pairs, list) and pairs, "codex-present probe must list supported pairs"
        assert all(
            isinstance(pair, dict) and pair.get("model") and pair.get("effort")
            for pair in pairs
        ), "supported pair entries must carry model and effort"
    saved_resolve = runtime_probe_module.resolve_codex_executable
    runtime_probe_module.resolve_codex_executable = lambda *args, **kwargs: {
        "ok": False,
        "errors": ["command_not_found"],
        "command": "codex",
    }
    try:
        no_codex_probe = probe()
    finally:
        runtime_probe_module.resolve_codex_executable = saved_resolve
    no_codex_host_proof = no_codex_probe.get("host_proof")
    assert isinstance(no_codex_host_proof, dict), "no-codex probe must still expose host_proof"
    assert all(
        value is None for value in no_codex_host_proof.values()
    ), "no-codex host_proof fields must be null (never raise, never fake)"

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
        effective_config = effective_config_agent_summary(codex_home)
        effective_source = str(effective_config["effective_config_source"])
        effective_strict_path = (
            managed_path if effective_source == "managed_config.toml" else desktop_user_path
        )
        production_config = strict_config_file_probe(executable_path, effective_strict_path)
        assert production_config["cleanup_verified"] is True
        assert production_config["orphan_process_count"] == 0
        assert all(
            "\\" not in key and ":" not in key
            for key in production_config["config_key_names"]
        )
        desktop_user_config = (
            production_config
            if effective_strict_path == desktop_user_path
            else strict_config_file_probe(executable_path, desktop_user_path)
        )
        known_desktop_user_drift = bool(
            effective_source == "config.toml"
            and production_config["accepted"] is False
            and production_config["error_class"] == "unknown_configuration_field"
        )
        native_effective = native_config_read_summary(executable_path, cwd=Path.home())
        assert native_effective["ok"] is True, native_effective.get("errors")
        assert effective_config["protocol_config_ok"] is True
        expected_protocol = effective_config["selected_protocol"]
        assert native_effective["selected_protocol"] == expected_protocol
        assert production_config["accepted"] is True or known_desktop_user_drift is True, production_config["error_class"]
        store_proof = run_store_false_probe(executable_path, agent_protocol="v1")
        assert store_proof["overall_gate"] == "PASSED", store_proof["errors"]
        assert store_proof["multi_agent_protocol"] == "v1"
        assert store_proof["agent_schema_claim_scope"] == "v1_tool_name_and_field_marker_presence_only"
        assert store_proof["agent_tools"]
        v1_spawn = next(
            row for row in store_proof["agent_tools"] if row["name"] in {"multi_agent_v1", "spawn_agent"}
        )
        v1_markers = v1_spawn["schema_marker_presence"]
        assert v1_markers["message"]
        v2_store_proof = run_store_false_probe(executable_path, agent_protocol="v2")
        assert v2_store_proof["overall_gate"] == "PASSED", v2_store_proof["errors"]
        assert (
            v2_store_proof["agent_schema_claim_scope"]
            == "v2_core_fields_and_optional_field_presence"
        )
        v2_spawn = next(
            row for row in v2_store_proof["spawn_agent_tools"]
            if row["name"] in {"collaboration", "spawn_agent"}
        )
        v2_markers = v2_spawn["schema_marker_presence"]
        assert all(v2_markers[key] for key in ("message", "task_name", "fork_turns"))
        v2_model_override_fields = [
            key for key in ("model", "reasoning_effort", "service_tier") if v2_markers[key]
        ]
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
            "evidence_scope": {
                "codex_protocol_schema": "GENERIC_HOST_COMPATIBILITY_ONLY",
                "decretum_office_dispatch": "NOT_EVALUATED",
            },
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
            "strict_config_source": effective_source,
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
            "v1_agent_type_metadata_supported": v1_markers["agent_type"],
            "v1_agent_schema_markers": dict(v1_markers),
            "v2_model_override_fields_present": v2_model_override_fields,
            "v2_reserved_schema_markers": dict(v2_markers),
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
