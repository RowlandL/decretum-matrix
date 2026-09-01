"""Validate installed Codex agent role files rendered from standing profiles."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import json
from pathlib import Path
import stat
import sys
import tempfile

sys.dont_write_bytecode = True

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None  # type: ignore[assignment]

from sync_codex_agents_from_profiles import (
    REQUIRED_PROFILE_FILES,
    backup_toml_tree,
    expected_rendered_hash,
    installed_agents_root,
    render_agent_toml,
    sha256_file,
    template_root,
    codex_home,
)
from court_multi_agent_protocol import validate_protocol_config


REQUIRED_STRING_KEYS = ("name", "description", "developer_instructions")


def read_toml(path: Path) -> dict[str, object]:
    if tomllib is None:
        raise RuntimeError("tomllib unavailable; Python 3.11+ required")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def schema_errors(path: Path) -> list[str]:
    try:
        data = read_toml(path)
    except Exception as exc:
        return [f"invalid_toml:{exc}"]
    errors: list[str] = []
    for key in REQUIRED_STRING_KEYS:
        if not isinstance(data.get(key), str) or not str(data.get(key, "")).strip():
            errors.append(f"{key}:missing_or_not_string")
    for key, value in data.items():
        if not isinstance(value, str):
            errors.append(f"{key}:not_string")
    if "profile" in data:
        errors.append("TEMPLATE_COPIED_DIRECTLY:profile_table_present")
    for forbidden_model_key in ("model", "model_reasoning_effort", "reasoning_effort"):
        if forbidden_model_key in data:
            errors.append(f"{forbidden_model_key}:must_be_dynamic_spawn_metadata")
    instructions = str(data.get("developer_instructions") or "")
    for term in (
        "preload_contract_version",
        "court_skill_hash",
        "preload_ack",
        "agent_dossier_loaded",
        "loaded_skills",
        "/root/*",
        "Codex model route",
        "Claude Code model route",
        "Hermes model route",
    ):
        if term not in instructions:
            errors.append(f"developer_instructions:missing_{term}")
    return errors


def validate_codex_multi_agent_config(
    config_path: Path | None = None,
    managed_path: Path | None = None,
) -> dict[str, object]:
    base_path = config_path or (codex_home() / "config.toml")
    overlay_path = managed_path or base_path.with_name("managed_config.toml")
    path = _effective_config_path(base_path, overlay_path)
    text = path.read_text(encoding="utf-8")
    data = read_toml(path)
    agents = data.get("agents")
    features = data.get("features")
    agents = agents if isinstance(agents, dict) else {}
    features = features if isinstance(features, dict) else {}
    multi_agent = features.get("multi_agent_v2")
    multi_agent = multi_agent if isinstance(multi_agent, dict) else {}
    contract = validate_protocol_config(text)
    base_contract = validate_protocol_config(base_path.read_text(encoding="utf-8"))
    error_aliases = {
        "v2_enabled_with_legacy_max_threads": "agents.max_threads:forbidden_when_multi_agent_v2_enabled",
        "v2_max_depth_must_equal_4": "agents.max_depth:must_equal_4",
        "v2_total_threads_must_be_at_least_2": "features.multi_agent_v2.max_concurrent_threads_per_session:must_be_at_least_2",
        "v2_reserved_spawn_schema_must_be_hidden": "features.multi_agent_v2.hide_spawn_agent_metadata:must_be_true_for_reserved_schema",
        "v1_max_depth_must_equal_4": "agents.max_depth:must_equal_4",
        "v1_child_threads_must_be_positive": "agents.max_threads:must_be_positive_for_v1",
        "v1_inactive_v2_total_threads_must_be_at_least_2": "features.multi_agent_v2.max_concurrent_threads_per_session:must_be_at_least_2_when_v1",
        "v1_child_threads_exceed_inactive_v2_capacity": "agents.max_threads:exceeds_inactive_v2_capacity",
        "v1_inactive_v2_reserved_schema_must_remain_hidden": "features.multi_agent_v2.hide_spawn_agent_metadata:must_remain_true_when_v1",
    }
    errors = [error_aliases.get(str(error), str(error)) for error in contract.get("errors", [])]
    selected_protocol = contract.get("mode")
    legacy_max_threads = agents.get("max_threads")
    v2_max_threads = multi_agent.get("max_concurrent_threads_per_session")
    spawn_agent_metadata_hidden = multi_agent.get("hide_spawn_agent_metadata") is True
    effective_child_thread_limit = contract.get("effective_child_thread_limit")
    configured_thread_limit = v2_max_threads if selected_protocol == "v2" else legacy_max_threads
    return {
        "ok": not errors,
        "config_path": str(path),
        "base_config_path": str(base_path),
        "config_layer_source": "legacy_managed_overlay" if path == overlay_path else "user",
        "base_selected_protocol": base_contract.get("mode"),
        "auto_discovery_root": str((codex_home() / "agents").resolve()),
        "selected_protocol": selected_protocol,
        "max_depth": contract.get("max_depth"),
        "max_threads": configured_thread_limit,
        "logical_total_threads": v2_max_threads if selected_protocol in {"v1", "v2"} else None,
        "legacy_max_threads": legacy_max_threads,
        "max_concurrent_threads_per_session": v2_max_threads,
        "effective_child_thread_limit": effective_child_thread_limit,
        "multi_agent_v2_enabled": multi_agent.get("enabled"),
        "multi_agent_enabled": features.get("multi_agent"),
        "inactive_v2_config_preserved": contract.get("inactive_v2_config_preserved"),
        "spawn_agent_metadata_visible": multi_agent.get("hide_spawn_agent_metadata") is False,
        "spawn_agent_metadata_hidden": spawn_agent_metadata_hidden,
        "reserved_spawn_schema_compatible": bool(
            multi_agent.get("enabled") is True and spawn_agent_metadata_hidden
        ),
        "errors": errors,
    }


def _has_protocol_material(data: dict[str, object]) -> bool:
    agents = data.get("agents") if isinstance(data, dict) else None
    features = data.get("features") if isinstance(data, dict) else None
    agents = agents if isinstance(agents, dict) else {}
    features = features if isinstance(features, dict) else {}
    return bool(
        isinstance(features.get("multi_agent_v2"), dict)
        or features.get("multi_agent") is not None
        or agents.get("max_threads") is not None
    )


def _effective_config_path(base_path: Path, overlay_path: Path) -> Path:
    if not overlay_path.exists():
        return base_path
    overlay_text = overlay_path.read_text(encoding="utf-8")
    if not overlay_text.strip():
        return base_path
    try:
        overlay_data = tomllib.loads(overlay_text)
    except tomllib.TOMLDecodeError:
        return overlay_path
    if isinstance(overlay_data, dict) and _has_protocol_material(overlay_data):
        return overlay_path
    return base_path


def validate_installed_agents(agents_dir: Path | None = None, templates_dir: Path | None = None) -> dict[str, object]:
    agents = agents_dir or installed_agents_root()
    templates = templates_dir or template_root()
    installed_files = sorted(agents.glob("*.toml")) if agents.exists() else []
    schema_rows: list[dict[str, object]] = []
    malformed: list[dict[str, object]] = []
    for path in installed_files:
        errors = schema_errors(path)
        row = {
            "agent": path.name,
            "path": str(path),
            "schema_status": "ok" if not errors else "malformed",
            "errors": errors,
        }
        schema_rows.append(row)
        if errors:
            malformed.append(row)

    sync_rows: list[dict[str, object]] = []
    unsynced: list[dict[str, object]] = []
    malformed_by_name = {str(row["agent"]): row for row in malformed}
    for name in REQUIRED_PROFILE_FILES:
        template = templates / name
        installed = agents / name
        expected_hash = expected_rendered_hash(template) if template.exists() else None
        installed_hash = sha256_file(installed) if installed.exists() else None
        if not installed.exists():
            status = "missing_installed_agent"
        elif name in malformed_by_name:
            status = "malformed"
        elif installed_hash == expected_hash:
            status = "synced"
        else:
            status = "different"
        row = {
            "agent": name,
            "template_exists": template.exists(),
            "installed_exists": installed.exists(),
            "expected_rendered_hash": expected_hash,
            "installed_hash": installed_hash,
            "status": status,
        }
        sync_rows.append(row)
        if status != "synced":
            unsynced.append(row)

    config_contract = validate_codex_multi_agent_config()
    return {
        "ok": not malformed and not unsynced and bool(config_contract["ok"]),
        "agents_dir": str(agents),
        "template_root": str(templates),
        "installed_count": len(installed_files),
        "required_count": len(REQUIRED_PROFILE_FILES),
        "malformed_count": len(malformed),
        "unsynced_count": len(unsynced),
        "schema_rows": schema_rows,
        "sync_rows": sync_rows,
        "config_contract": config_contract,
    }


def validate_immutable_backup_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="court-agent-backup-check-") as temp_dir:
        root = Path(temp_dir)
        source = root / "source"
        destination = root / "backup"
        source.mkdir()
        original = source / "taizi.toml"
        original.write_text('name = "taizi"\n', encoding="utf-8")
        assert backup_toml_tree(source, destination) == 1
        backed_up = destination / original.name
        assert backed_up.read_bytes() == original.read_bytes()
        assert not backed_up.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        try:
            backup_toml_tree(source, destination)
        except FileExistsError:
            pass
        else:
            raise AssertionError("backup destination must be non-overwrite")
        backed_up.chmod(stat.S_IREAD | stat.S_IWRITE)


def validate_managed_overlay_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="court-agent-overlay-check-") as temp_dir:
        root = Path(temp_dir)
        base = root / "config.toml"
        managed = root / "managed_config.toml"
        base.write_text(
            "[agents]\nmax_depth=4\n\n[features.multi_agent_v2]\nenabled=true\n"
            "max_concurrent_threads_per_session=16\nhide_spawn_agent_metadata=true\n",
            encoding="utf-8",
        )
        managed.write_text(
            "[agents]\nmax_depth=4\nmax_threads=15\n\n[features]\nmulti_agent=true\n\n"
            "[features.multi_agent_v2]\nenabled=false\nmax_concurrent_threads_per_session=16\n"
            "hide_spawn_agent_metadata=true\n",
            encoding="utf-8",
        )
        result = validate_codex_multi_agent_config(base, managed)
        assert result["ok"] is True
        assert result["selected_protocol"] == "v1"
        assert result["base_selected_protocol"] == "v2"
        assert result["config_layer_source"] == "legacy_managed_overlay"


def validate_ordinary_carrier_projection_contract() -> None:
    templates = template_root()
    for name in ("zhongshu.toml", "patrol-inspector.toml"):
        role = Path(name).stem
        rendered = render_agent_toml(templates / name)
        assert tomllib is not None
        parsed = tomllib.loads(rendered)
        normalized = (
            str(parsed.get("description") or "")
            + "\n"
            + str(parsed.get("developer_instructions") or "")
        ).replace("\\", "/").casefold()
        expected_dossier = f"agents/office-dossiers/{role}/agents.md"
        assert expected_dossier in normalized, f"{role}: ordinary dossier pointer missing"
        assert "agents/supercc-dossiers/" not in normalized, f"{role}: visible carrier dossier leaked"
        for forbidden in ("supercc", "squad", "zellij"):
            assert forbidden not in normalized, f"{role}: ordinary projection leaked {forbidden}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()
    try:
        validate_immutable_backup_contract()
        validate_managed_overlay_contract()
        validate_ordinary_carrier_projection_contract()
        result = validate_installed_agents()
    except Exception as exc:
        print(f"CODEX_AGENT_ROLES_FAILED {exc}")
        return 1
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print(
            "CODEX_AGENT_ROLES_OK "
            f"installed_count={result['installed_count']} required_count={result['required_count']} "
            f"malformed_count={result['malformed_count']} unsynced_count={result['unsynced_count']} "
            f"reserved_spawn_schema_compatible={result['config_contract']['reserved_spawn_schema_compatible']}"
        )
    else:
        print(
            "CODEX_AGENT_ROLES_FAILED "
            f"installed_count={result['installed_count']} required_count={result['required_count']} "
            f"malformed_count={result['malformed_count']} unsynced_count={result['unsynced_count']} "
            f"config_errors={','.join(result['config_contract']['errors'])}"
        )
        for row in result["schema_rows"]:
            if row["schema_status"] != "ok":
                print(f"malformed {row['agent']}: {', '.join(row['errors'])}")
        for row in result["sync_rows"]:
            if row["status"] != "synced":
                print(f"unsynced {row['agent']}: {row['status']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())



