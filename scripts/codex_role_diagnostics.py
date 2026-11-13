"""Read-only inspection of Codex configuration and projected role files."""

from __future__ import annotations

from pathlib import Path
import tomllib

from court_multi_agent_protocol import validate_protocol_config
from sync_codex_agents_from_profiles import (
    REQUIRED_PROFILE_FILES, codex_home, installed_agents_root, render_agent_toml, template_root,
)


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
        "court_skill_path",
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
        "native_v1_max_depth_must_equal_4": "agents.max_depth:must_equal_4",
        "native_v1_child_threads_must_be_positive": "agents.max_concurrent_threads_per_session:must_be_positive_for_native_v1",
    }
    errors = [error_aliases.get(str(error), str(error)) for error in contract.get("errors", [])]
    selected_protocol = contract.get("mode")
    return {
        "ok": not errors,
        "config_path": str(path),
        "base_config_path": str(base_path),
        "config_layer_source": "legacy_managed_overlay" if path == overlay_path else "user",
        "base_selected_protocol": base_contract.get("mode"),
        "auto_discovery_root": str((base_path.parent / "agents").resolve()),
        "selected_protocol": selected_protocol,
        "max_depth": contract.get("max_depth"),
        "max_threads": contract.get("max_threads"),
        "logical_total_threads": contract.get("logical_total_threads"),
        "legacy_max_threads": contract.get("legacy_max_threads"),
        "max_concurrent_threads_per_session": contract.get("max_concurrent_threads_per_session"),
        "effective_child_thread_limit": contract.get("effective_child_thread_limit"),
        "multi_agent_v2_enabled": contract.get("multi_agent_v2_enabled"),
        "multi_agent_enabled": contract.get("multi_agent_enabled"),
        "inactive_v2_config_preserved": contract.get("inactive_v2_config_preserved"),
        "spawn_agent_metadata_visible": contract.get("spawn_agent_metadata_visible"),
        "spawn_agent_metadata_hidden": contract.get("spawn_agent_metadata_hidden"),
        "spawn_agent_metadata_claim_scope": contract.get("spawn_agent_metadata_claim_scope"),
        "runtime_spawn_schema_visibility": contract.get("runtime_spawn_schema_visibility"),
        "runtime_spawn_schema_inferred_from_config": contract.get("runtime_spawn_schema_inferred_from_config"),
        "reserved_spawn_schema_compatible": contract.get("reserved_spawn_schema_compatible"),
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
        or agents.get("max_concurrent_threads_per_session") is not None
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


def validate_installed_agents(
    agents_dir: Path | None = None, templates_dir: Path | None = None,
    *, config_path: Path | None = None,
) -> dict[str, object]:
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
        content_matches = installed.is_file() and template.is_file() and installed.read_text(encoding="utf-8") == render_agent_toml(template)
        if not installed.exists():
            status = "missing_installed_agent"
        elif name in malformed_by_name:
            status = "malformed"
        elif content_matches:
            status = "synced"
        else:
            status = "different"
        row = {
            "agent": name,
            "template_exists": template.exists(),
            "installed_exists": installed.exists(),
            "status": status,
        }
        sync_rows.append(row)
        if status != "synced":
            unsynced.append(row)

    config_contract = validate_codex_multi_agent_config(config_path)
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
