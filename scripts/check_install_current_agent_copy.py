#!/usr/bin/env python3
"""Deterministic install/config checks using isolated injected fixtures."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None  # type: ignore[assignment]


sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PATH = ROOT / "scripts" / "install_current_agent_copy.py"
PROJECTION_MANIFEST_PATH = ROOT / "references" / "manifests" / "install-projection.v1.json"
IDENTITY_MANIFEST_RELATIVE = "references/manifests/skill-identity.v1.json"
IDENTITY_MANIFEST_PATH = ROOT / Path(IDENTITY_MANIFEST_RELATIVE)

RESULT_SCHEMA = "court.install_current_agent_copy.result.v1"
CHECK_SCHEMA = "court.install_current_agent_copy.check.v1"
PROJECTION_SCHEMA = "court.install_projection.v1"
CONFIG_REQUEST_SCHEMA = "court.blank_host_configuration.request.v1"
CONFIG_RESULT_KEY = "configuration_remediation"

PROFILES_REQUIRED_COLUMNS = (
    "id",
    "name",
    "payload",
    "sort_order",
    "created_at",
    "updated_at",
)
V13_INPUT_TOKEN_TABLES = (
    "proxy_request_logs",
    "usage_daily_rollups",
)
DIRECT_FAILURE_STEPS = (
    "backup_effective_file",
    "begin_effective_files_transaction",
    "write_effective_config",
    "commit_effective_files_transaction",
)
ARTIFACT_PORTABILITY_RED_INTERFACE = {
    "portable_package_compatibility": "evidence_required",
    "separate_macos_package": "evidence_required_if_portable_package_incompatible",
    "community_license": "AGPL-3.0-only",
    "license_class": "osi_open_source",
    "required_license_artifacts": (
        "LICENSE",
        "NOTICE",
        "COMMERCIAL-LICENSE.md",
        "THIRD_PARTY_NOTICES.md",
        "PROVENANCE.md",
    ),
    "rights_owner": "孙华清",
    "maintainer_github": "@RowlandL",
    "maintainer_github_id": 42199880,
    "commercial_license_notice": "COMMERCIAL-LICENSE.md",
    "historical_apache_rights_preserved": True,
    "NOT_OPEN_SOURCE": False,
}

LOADED_IDENTITY_EXPECTED = {
    "display_name": "Dercretum-Matrix",
    "canonical_skill_name": "decretum-matrix",
    "canonical_invocation": "$decretum-matrix",
    "community_license": "AGPL-3.0-only",
    "rights_owner": "孙华清",
    "maintainer_github": "@RowlandL",
    "maintainer_github_id": 42199880,
}
LOCATOR_POLICY_EXPECTED = {
    "install_directory_name": "decretum-matrix",
    "legacy_install_directory_name": "court-capability-router",
    "legacy_install_locator_policy": "absent_or_same_physical_authority",
    "shiguan_namespace": "court-capability-router",
    "directory_basename_may_differ_from_skill_name": False,
    "rename_policy": "rename_install_directory_preserve_shiguan_namespace",
}
LEGACY_INSTALL_DIRECTORY_NAME = "court-capability-router"

CANONICAL_TOOL_CLASSES = (
    "codex",
    "claude-code",
    "hermes",
    "other:fixture-cli",
)
UNCERTAINTY_KINDS = (
    "db_schema",
    "field_ownership",
    "precedence",
    "current_value",
    "compatibility",
)
CODEX_NORMALIZED_SEMANTIC_DELTA = {
    "set": {
        "agents.max_depth": 4,
        "features.multi_agent_v2.enabled": True,
        "features.multi_agent_v2.max_concurrent_threads_per_session": 16,
        "features.multi_agent_v2.hide_spawn_agent_metadata": True,
    },
    "remove": ["agents.max_threads"],
}
GENERIC_NORMALIZED_SEMANTIC_DELTA = {
    "set": {"court.blank_host.ready": True},
    "remove": [],
}
CONFIG_UNEXERCISED_GAPS = (
    "blank_host_config_public_planner_unexercised:install_current_agent_copy unavailable",
    "blank_host_config_public_executor_unexercised:install_current_agent_copy unavailable",
    "blank_host_config_tool_class_matrix_unexercised:install_current_agent_copy unavailable",
    "blank_host_config_reminder_nonblocking_unexercised:install_current_agent_copy unavailable",
    "blank_host_config_controller_first_unexercised:install_current_agent_copy unavailable",
    "blank_host_config_effective_file_verification_unexercised:install_current_agent_copy unavailable",
    "blank_host_config_direct_transaction_unexercised:install_current_agent_copy unavailable",
    "blank_host_config_uncertainty_fail_closed_unexercised:install_current_agent_copy unavailable",
    "blank_host_config_hermes_fallback_gate_unexercised:install_current_agent_copy unavailable",
    "cc_switch_synthetic_json_fixture_contract_unexercised:install_current_agent_copy unavailable",
    "cc_switch_version_schema_matrix_unexercised:install_current_agent_copy unavailable",
    "hermes_config_path_precedence_unexercised:install_current_agent_copy unavailable",
    "hermes_step_failure_rollback_unexercised:install_current_agent_copy unavailable",
)
INSTALL_UNEXERCISED_GAPS = (
    "macos_darwin_clean_home_portability_unexercised:install_current_agent_copy unavailable",
    "artifact_portability_evidence_interface_unexercised:install_current_agent_copy unavailable",
)

POLICY_EXPECTED = {
    "required_target": ".agents",
    "default_optional_target": "current_agent_tool_only",
    "extra_targets": "explicit_latest_user_request_only",
    "fanout": "forbidden",
}
PROJECTION_NAMES = (
    "shared_agents",
    "portable_current_tool",
    "repository_only",
)
BINDING_FIELDS = (
    "profile_source",
    "dossier_path",
    "court_skill_path",
)
PORTABLE_FILES = (
    "SKILL.md",
    "VERSION",
    "agents/standing-officials/gongbu.toml",
    "agents/supercc-dossiers/gongbu/AGENTS.md",
    IDENTITY_MANIFEST_RELATIVE,
    "scripts/portable-helper.py",
)
REPOSITORY_ONLY_FILES = (
    "docs/internal-plan.md",
)


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or candidate.drive:
        return False
    return all(part not in {"", ".", ".."} for part in candidate.parts)


def _same_filesystem_path(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
            os.path.abspath(str(right))
        )


def _validate_loaded_identity(
    identity: object,
    *,
    label: str,
    errors: list[str],
) -> bool:
    before = len(errors)
    if not isinstance(identity, dict):
        errors.append(f"{label}:identity_not_object")
        return False
    for field, expected in LOADED_IDENTITY_EXPECTED.items():
        if identity.get(field) != expected:
            errors.append(
                f"{label}:{field}:{identity.get(field)!r}!={expected!r}"
            )
    locator_policy = identity.get("locator_policy")
    if not isinstance(locator_policy, dict):
        errors.append(f"{label}:locator_policy_not_object")
    else:
        for field, expected in LOCATOR_POLICY_EXPECTED.items():
            if locator_policy.get(field) != expected:
                errors.append(
                    f"{label}:locator_policy:{field}:"
                    f"{locator_policy.get(field)!r}!={expected!r}"
                )
    forbidden_contact_fields = [
        str(key)
        for key in identity
        if "email" in str(key).casefold()
    ]
    if forbidden_contact_fields:
        errors.append(
            f"{label}:forbidden_contact_fields:"
            f"{','.join(sorted(forbidden_contact_fields))}"
        )
    return len(errors) == before


def _validate_manifest(
    manifest: object,
    *,
    label: str,
    errors: list[str],
) -> bool:
    before = len(errors)
    if not isinstance(manifest, dict):
        errors.append(f"{label}:manifest_not_object")
        return False
    if manifest.get("schema") != PROJECTION_SCHEMA:
        errors.append(
            f"{label}:schema:{manifest.get('schema')!r}!={PROJECTION_SCHEMA!r}"
        )

    if manifest.get("identity_manifest") != IDENTITY_MANIFEST_RELATIVE:
        errors.append(
            f"{label}:identity_manifest:{manifest.get('identity_manifest')!r}!="
            f"{IDENTITY_MANIFEST_RELATIVE!r}"
        )

    policy = manifest.get("policy")
    if not isinstance(policy, dict):
        errors.append(f"{label}:policy_not_object")
    else:
        for key, expected in POLICY_EXPECTED.items():
            if policy.get(key) != expected:
                errors.append(
                    f"{label}:policy:{key}:{policy.get(key)!r}!={expected!r}"
                )

    projections = manifest.get("projections")
    if not isinstance(projections, dict):
        errors.append(f"{label}:projections_not_object")
    else:
        for name in PROJECTION_NAMES:
            values = projections.get(name)
            if not isinstance(values, list) or any(
                not _safe_relative(item) for item in values
            ):
                errors.append(f"{label}:projection_invalid:{name}")
        repository_only = projections.get("repository_only")
        if isinstance(repository_only, list):
            portable = set()
            for name in ("shared_agents", "portable_current_tool"):
                values = projections.get(name)
                if isinstance(values, list):
                    portable.update(item for item in values if isinstance(item, str))
            overlap = portable & {
                item for item in repository_only if isinstance(item, str)
            }
            if overlap:
                errors.append(
                    f"{label}:repository_only_overlap:{','.join(sorted(overlap))}"
                )

    bindings = manifest.get("persistent_bindings")
    if not isinstance(bindings, list) or not bindings:
        errors.append(f"{label}:persistent_bindings_missing")
    else:
        seen_roles: set[str] = set()
        for index, binding in enumerate(bindings):
            if not isinstance(binding, dict):
                errors.append(f"{label}:binding:{index}:not_object")
                continue
            role_key = binding.get("role_key")
            if not isinstance(role_key, str) or not role_key:
                errors.append(f"{label}:binding:{index}:role_key")
            elif role_key in seen_roles:
                errors.append(f"{label}:binding:{index}:duplicate_role:{role_key}")
            else:
                seen_roles.add(role_key)
            for field in BINDING_FIELDS:
                if not _safe_relative(binding.get(field)):
                    errors.append(f"{label}:binding:{index}:{field}:not_relative")

    return len(errors) == before


def _load_json(path: Path, *, label: str, errors: list[str]) -> object | None:
    if not path.is_file():
        errors.append(f"missing_{label}:{path.relative_to(ROOT).as_posix()}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label}_load_error:{type(exc).__name__}:{exc}")
        return None


def _load_production(errors: list[str]) -> object | None:
    if not PRODUCTION_PATH.is_file():
        errors.append("missing_module:scripts/install_current_agent_copy.py")
        return None
    spec = importlib.util.spec_from_file_location(
        "install_current_agent_copy_red_target",
        PRODUCTION_PATH,
    )
    if spec is None or spec.loader is None:
        errors.append("module_spec_unavailable:scripts/install_current_agent_copy.py")
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - deterministic RED evidence
        errors.append(f"module_import_error:{type(exc).__name__}:{exc}")
        return None
    return module


def _fixture_manifest() -> dict[str, object]:
    return {
        "schema": PROJECTION_SCHEMA,
        "identity_manifest": IDENTITY_MANIFEST_RELATIVE,
        "policy": dict(POLICY_EXPECTED),
        "projections": {
            "shared_agents": list(PORTABLE_FILES),
            "portable_current_tool": list(PORTABLE_FILES),
            "repository_only": list(REPOSITORY_ONLY_FILES),
        },
        "persistent_bindings": [
            {
                "role_key": "gongbu",
                "profile_source": "agents/standing-officials/gongbu.toml",
                "dossier_path": "agents/supercc-dossiers/gongbu/AGENTS.md",
                "court_skill_path": "SKILL.md",
            }
        ],
    }


def _write_files(root: Path, contents: dict[str, str]) -> None:
    for relative, text in contents.items():
        path = root / Path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _write_fixture_source(
    source_root: Path,
    *,
    manifest: dict[str, object] | None = None,
) -> Path:
    contents = {
        "SKILL.md": "# fixture court skill\n",
        "VERSION": "beta0.5.11\n",
        "agents/standing-officials/gongbu.toml": (
            '[profile]\nrole_key = "gongbu"\noffice_zh = "工部"\n'
        ),
        "agents/supercc-dossiers/gongbu/AGENTS.md": (
            "# Fixture dossier\n"
            "- profile_source: agents/standing-officials/gongbu.toml\n"
            "- dossier_path: agents/supercc-dossiers/gongbu/AGENTS.md\n"
            "- court_skill_path: SKILL.md\n"
        ),
        "scripts/portable-helper.py": "VALUE = 'portable'\n",
        "docs/internal-plan.md": "# repository only\n",
    }
    _write_files(source_root, contents)
    identity_path = source_root / Path(IDENTITY_MANIFEST_RELATIVE)
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_identity = {
        "schema": "court.skill_identity.v1",
        "schema_version": 1,
        **LOADED_IDENTITY_EXPECTED,
        "commercial_license_notice": "COMMERCIAL-LICENSE.md",
        "legacy_names": [
            {
                "name": "court-capability-router",
                "status": "deprecated",
                "compatibility_claimed": False,
            }
        ],
        "locator_policy": {
            **LOCATOR_POLICY_EXPECTED,
            "repository_id": "decretum-matrix",
        },
    }
    identity_path.write_text(
        json.dumps(fixture_identity, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    manifest_path = (
        source_root / "references" / "manifests" / "install-projection.v1.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            manifest if manifest is not None else _fixture_manifest(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _case_fixture(
    temp_root: Path,
    label: str,
    manifest_data: dict[str, object] | None = None,
) -> tuple[object, ...]:
    case_root = temp_root / label
    source, home = case_root / "source", case_root / "home"
    manifest = _write_fixture_source(source, manifest=manifest_data)
    return source, home, manifest, _target_roots(home)


def _target_roots(home_root: Path) -> dict[str, Path]:
    return {
        "codex": home_root / ".codex" / "skills" / "decretum-matrix",
        "claude": home_root / ".claude" / "skills" / "decretum-matrix",
        "hermes": home_root / ".hermes" / "skills" / "decretum-matrix",
        "other": home_root / ".other-agent" / "skills" / "decretum-matrix",
    }


def _agents_root(home_root: Path) -> Path:
    return home_root / ".agents" / "skills" / "decretum-matrix"


def _legacy_root(root: Path) -> Path:
    return root.with_name(LEGACY_INSTALL_DIRECTORY_NAME)


def _physical_authority_count(canonical: Path, legacy: Path) -> int:
    return len(
        {
            path.resolve(strict=False)
            for path in (canonical, legacy)
            if path.exists() or path.is_symlink()
        }
    )


class _MigrationFailureAdapter:
    def __init__(self, fail_step: str | None = None) -> None:
        self.fail_step = fail_step
        self.events: list[str] = []

    def checkpoint(self, step: str, evidence: dict[str, object]) -> None:
        self.events.append(step)
        if step == self.fail_step:
            raise RuntimeError(f"fixture install transaction failure: {step}")


def _prime_existing_roots(home_root: Path, tool_roots: dict[str, Path]) -> None:
    roots = [_agents_root(home_root), *tool_roots.values()]
    for index, root in enumerate(roots):
        root.mkdir(parents=True, exist_ok=True)
        (root / "target-only.txt").write_text(
            f"preserve-{index}\n",
            encoding="utf-8",
        )


def _snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _snapshot_many(roots: list[Path]) -> dict[str, dict[str, bytes]]:
    return {str(root.resolve(strict=False)): _snapshot(root) for root in roots}


_MISSING = object()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _nested_get(data: object, dotted_key: str) -> object:
    current = data
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _nested_set(data: dict[str, object], dotted_key: str, value: object) -> None:
    current = data
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = deepcopy(value)


def _nested_remove(data: dict[str, object], dotted_key: str) -> None:
    current: object = data
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict):
            return
        current = current.get(part)
    if isinstance(current, dict):
        current.pop(parts[-1], None)


def _apply_semantic_delta(
    data: dict[str, object],
    delta: dict[str, object],
) -> dict[str, object]:
    updated = deepcopy(data)
    set_values = delta.get("set")
    if isinstance(set_values, dict):
        for dotted_key, value in set_values.items():
            if isinstance(dotted_key, str):
                _nested_set(updated, dotted_key, value)
    remove_values = delta.get("remove")
    if isinstance(remove_values, list):
        for dotted_key in remove_values:
            if isinstance(dotted_key, str):
                _nested_remove(updated, dotted_key)
    return updated


def _without_delta_fields(
    data: dict[str, object],
    delta: dict[str, object],
) -> dict[str, object]:
    projected = deepcopy(data)
    set_values = delta.get("set")
    if isinstance(set_values, dict):
        for dotted_key in set_values:
            if isinstance(dotted_key, str):
                _nested_remove(projected, dotted_key)
    remove_values = delta.get("remove")
    if isinstance(remove_values, list):
        for dotted_key in remove_values:
            if isinstance(dotted_key, str):
                _nested_remove(projected, dotted_key)
    return projected


def _toml_scalar(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"unsupported fixture TOML scalar: {value!r}")


def _render_fixture_toml(data: dict[str, object]) -> str:
    lines: list[str] = []

    def emit_table(table: dict[str, object], prefix: tuple[str, ...]) -> None:
        scalar_items = [
            (key, value) for key, value in table.items() if not isinstance(value, dict)
        ]
        nested_items = [
            (key, value) for key, value in table.items() if isinstance(value, dict)
        ]
        if prefix:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"[{'.'.join(prefix)}]")
        for key, value in scalar_items:
            lines.append(f"{key} = {_toml_scalar(value)}")
        for key, value in nested_items:
            assert isinstance(value, dict)
            emit_table(value, (*prefix, key))

    emit_table(data, ())
    return "\n".join(lines).rstrip() + "\n"


def _parse_fixture_config(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".toml":
        if tomllib is None:
            raise RuntimeError("tomllib unavailable")
        parsed = tomllib.loads(text)
    else:
        parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"fixture config is not an object: {path}")
    return parsed


def _write_fixture_config(path: Path, data: dict[str, object]) -> None:
    if path.suffix.lower() == ".toml":
        text = _render_fixture_toml(data)
    else:
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def _delta_gaps(
    path: Path,
    data: dict[str, object],
    delta: dict[str, object],
) -> list[str]:
    gaps: list[str] = []
    set_values = delta.get("set")
    if isinstance(set_values, dict):
        for dotted_key, expected in set_values.items():
            if not isinstance(dotted_key, str):
                continue
            actual = _nested_get(data, dotted_key)
            if actual != expected:
                actual_text = "<missing>" if actual is _MISSING else repr(actual)
                gaps.append(
                    f"{path.name}:{dotted_key}:expected={expected!r}:actual={actual_text}"
                )
    remove_values = delta.get("remove")
    if isinstance(remove_values, list):
        for dotted_key in remove_values:
            if not isinstance(dotted_key, str):
                continue
            actual = _nested_get(data, dotted_key)
            if actual is not _MISSING:
                gaps.append(
                    f"{path.name}:{dotted_key}:expected=<absent>:actual={actual!r}"
                )
    return gaps


def _fixture_hermes_config_path(
    home_root: Path,
    *,
    platform_system: str,
    environment: dict[str, Path],
    explicit_config_dir: Path | None,
) -> tuple[Path, str]:
    if explicit_config_dir is not None:
        return explicit_config_dir / "config.yaml", "ccs_hermes_config_dir_override"
    hermes_home = environment.get("HERMES_HOME")
    if hermes_home is not None:
        return hermes_home / "config.yaml", "HERMES_HOME"
    if platform_system == "Windows":
        local_app_data = environment.get("LOCALAPPDATA")
        if local_app_data is None:
            local_app_data = home_root / "AppData" / "Local"
            return (
                local_app_data / "hermes" / "config.yaml",
                "windows_home_localappdata_fallback",
            )
        return local_app_data / "hermes" / "config.yaml", "LOCALAPPDATA"
    return home_root / ".hermes" / "config.yaml", "posix_home_default"


class _FixtureConfigurationAdapter:
    def __init__(
        self,
        root: Path,
        *,
        tool_class: str,
        controller_present: bool,
        controller_materializes: bool = True,
        controller_version: str = "3.17.0",
        controller_user_version: int = 13,
        controller_schema_complete: bool = True,
        current_profile_settings_present: bool = False,
        uncertainty: str | None = None,
        fail_direct_write_number: int | None = None,
        fail_direct_step: str | None = None,
        hermes_platform_system: str = "Linux",
        hermes_environment: dict[str, Path] | None = None,
        hermes_config_dir_override: Path | None = None,
    ) -> None:
        if tool_class not in CANONICAL_TOOL_CLASSES:
            raise ValueError(f"unsupported fixture tool class: {tool_class}")
        if uncertainty is not None and uncertainty not in UNCERTAINTY_KINDS:
            raise ValueError(f"unsupported fixture uncertainty: {uncertainty}")
        if fail_direct_step is not None and fail_direct_step not in DIRECT_FAILURE_STEPS:
            raise ValueError(f"unsupported direct failure step: {fail_direct_step}")
        self.root = root.resolve()
        self.tool_class = tool_class
        self.controller_present = controller_present
        self.controller_materializes = controller_materializes
        self.controller_version = controller_version
        self.controller_user_version = controller_user_version
        self.controller_schema_complete = controller_schema_complete
        self.current_profile_settings_present = current_profile_settings_present
        self.uncertainty = uncertainty
        self.fail_direct_write_number = fail_direct_write_number
        self.fail_direct_step = fail_direct_step
        self.events: list[str] = []
        self.mutation_events: list[str] = []
        self.migration_attempts = 0
        self.controller_deltas: list[dict[str, object]] = []
        self.direct_deltas: list[tuple[str, dict[str, object]]] = []
        self._direct_write_count = 0
        self._controller_original: bytes | None = None
        self._controller_effective_originals: dict[Path, bytes] = {}
        self._direct_originals: dict[Path, bytes] = {}
        self._backups: dict[Path, Path] = {}

        home = self.root / "home"
        self.controller_fixture_path = (
            self.root / "fixtures" / "cc-switch-controller.json"
        )
        if tool_class == "codex":
            self.effective_paths = [
                home / ".codex" / "config.toml",
                home / ".codex" / "managed_config.toml",
            ]
            self.expected_delta = deepcopy(CODEX_NORMALIZED_SEMANTIC_DELTA)
        elif tool_class == "claude-code":
            self.effective_paths = [home / ".claude" / "settings.json"]
            self.expected_delta = deepcopy(GENERIC_NORMALIZED_SEMANTIC_DELTA)
        elif tool_class == "hermes":
            hermes_path, hermes_path_source = _fixture_hermes_config_path(
                home,
                platform_system=hermes_platform_system,
                environment=dict(hermes_environment or {}),
                explicit_config_dir=hermes_config_dir_override,
            )
            self.effective_paths = [hermes_path]
            self.hermes_path_source = hermes_path_source
            self.expected_delta = deepcopy(GENERIC_NORMALIZED_SEMANTIC_DELTA)
        else:
            self.effective_paths = [home / ".fixture-cli" / "config.json"]
            self.expected_delta = deepcopy(GENERIC_NORMALIZED_SEMANTIC_DELTA)

        self._create_effective_fixtures()
        if controller_present:
            self.controller_fixture_path.parent.mkdir(parents=True, exist_ok=True)
            profile_columns = list(PROFILES_REQUIRED_COLUMNS)
            if not controller_schema_complete:
                profile_columns.remove("updated_at")
            schema_evidence = {
                "profiles": {
                    "exists": controller_schema_complete,
                    "columns": profile_columns,
                    "required_columns_present": controller_schema_complete,
                },
                "proxy_request_logs": {
                    "exists": controller_schema_complete,
                    "input_token_semantics": controller_schema_complete,
                },
                "usage_daily_rollups": {
                    "exists": controller_schema_complete,
                    "input_token_semantics": controller_schema_complete,
                },
            }
            self.controller_fixture_path.write_text(
                json.dumps(
                    {
                        "schema": "fixture.cc_switch.v1",
                        "storage_kind": "json_fixture",
                        "synthetic": True,
                        "controller_version": controller_version,
                        "app_version": controller_version,
                        "user_version": controller_user_version,
                        "schema_evidence": schema_evidence,
                        "settings": {
                            "current_profile_id_codex": "fixture-profile"
                        }
                        if current_profile_settings_present
                        else {},
                        "provider_secret": "fixture",
                        "unknown_controller_key": "preserve-controller",
                        "fixture_tool_blocks": {
                            tool_class: {
                                "semantic_delta": {},
                                "unknown_block_key": "preserve-tool-block",
                            }
                        },
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            fixture = json.loads(
                self.controller_fixture_path.read_text(encoding="utf-8")
            )
            if (
                fixture.get("storage_kind") != "json_fixture"
                or fixture.get("synthetic") is not True
                or "tool_blocks" in fixture
            ):
                raise AssertionError("controller JSON fixture masquerades as SQLite")
        self.initial_surface_snapshot = self.surface_snapshot()
        self.initial_parsed = {
            path: _parse_fixture_config(path) for path in self.effective_paths
        }

    def _controller_schema_evidence(self) -> dict[str, object]:
        if not self.controller_present:
            return {}
        fixture = json.loads(
            self.controller_fixture_path.read_text(encoding="utf-8")
        )
        evidence = fixture.get("schema_evidence")
        if not isinstance(evidence, dict):
            raise AssertionError("synthetic controller schema evidence missing")
        return deepcopy(evidence)

    def _controller_compatibility(self) -> tuple[bool, str]:
        parts = self.controller_version.split(".")
        recognized = len(parts) == 3 and all(part.isdigit() for part in parts)
        if not recognized:
            return False, "unknown_controller_version"
        major, minor, _patch = (int(part) for part in parts)
        if (major, minor) == (3, 16):
            if self.controller_user_version == 11:
                return True, "cc_switch_3_16_user_version_11"
            return False, "controller_version_user_version_mismatch"
        if (major, minor) == (3, 17):
            if self.controller_user_version != 13:
                return False, "controller_version_user_version_mismatch"
            schema = self._controller_schema_evidence()
            profiles = schema.get("profiles")
            profiles_ok = isinstance(profiles, dict) and (
                profiles.get("exists") is True
                and profiles.get("columns") == list(PROFILES_REQUIRED_COLUMNS)
                and profiles.get("required_columns_present") is True
            )
            token_tables_ok = all(
                isinstance(schema.get(table), dict)
                and schema[table].get("exists") is True
                and type(schema[table].get("input_token_semantics")) is bool
                and schema[table].get("input_token_semantics") is True
                for table in V13_INPUT_TOKEN_TABLES
            )
            if profiles_ok and token_tables_ok:
                return True, "cc_switch_3_17_user_version_13"
            return False, "required_v13_table_or_column_evidence_missing"
        return False, "unknown_controller_version"

    def _maybe_fail_direct_step(self, step: str) -> None:
        if self.fail_direct_step == step:
            raise RuntimeError(f"fixture direct step failure: {step}")

    def _create_effective_fixtures(self) -> None:
        for path in self.effective_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
        if self.tool_class == "codex":
            base = {
                "model_provider": "fixture-base-provider",
                "api_key": "fixture",
                "unknown_top": "preserve-config-top",
                "agents": {
                    "max_depth": 1,
                    "max_threads": 3,
                    "base_agent_unknown": "preserve-base-agent",
                },
                "features": {
                    "goals": True,
                    "multi_agent_v2": {
                        "enabled": False,
                        "max_concurrent_threads_per_session": 2,
                        "hide_spawn_agent_metadata": False,
                        "base_overlay_unknown": "preserve-base-overlay",
                    },
                },
                "providers": {
                    "fixture": {
                        "base_url": "https://base.fixture.invalid",
                        "token": "fixture",
                    }
                },
                "unknown": {"base": {"keep": "base-unknown"}},
            }
            managed = {
                "model_provider": "fixture-managed-provider",
                "api_key": "fixture",
                "unknown_top": "preserve-managed-top",
                "agents": {
                    "max_depth": 2,
                    "max_threads": 5,
                    "managed_agent_unknown": "preserve-managed-agent",
                },
                "features": {
                    "multi_agent": False,
                    "multi_agent_v2": {
                        "enabled": False,
                        "max_concurrent_threads_per_session": 7,
                        "hide_spawn_agent_metadata": False,
                        "managed_overlay_unknown": "preserve-managed-overlay",
                    },
                },
                "providers": {
                    "managed": {
                        "base_url": "https://managed.fixture.invalid",
                        "token": "fixture",
                    }
                },
                "unknown": {"managed": {"keep": "managed-unknown"}},
            }
            _write_fixture_config(self.effective_paths[0], base)
            _write_fixture_config(self.effective_paths[1], managed)
            return
        generic = {
            "court": {"blank_host": {"ready": False}},
            "secret": "fixture",
            "provider": {"id": f"fixture-{self.tool_class}"},
            "unknown": {"keep": f"preserve-{self.tool_class}"},
        }
        _write_fixture_config(self.effective_paths[0], generic)

    def _require_tool(self, tool_class: str) -> None:
        if tool_class != self.tool_class:
            raise AssertionError(
                f"adapter tool mismatch: {tool_class!r}!={self.tool_class!r}"
            )

    def _require_path(self, path: Path) -> Path:
        resolved = Path(path).resolve(strict=False)
        if resolved not in [item.resolve(strict=False) for item in self.effective_paths]:
            raise AssertionError(f"non-fixture effective path requested: {path}")
        if self.root not in resolved.parents:
            raise AssertionError(f"path escaped TemporaryDirectory: {path}")
        return resolved

    def _require_delta(self, delta: object) -> dict[str, object]:
        if delta != self.expected_delta:
            raise AssertionError(
                f"semantic delta drift: {delta!r}!={self.expected_delta!r}"
            )
        if not isinstance(delta, dict):
            raise AssertionError("semantic delta must be structured")
        return deepcopy(delta)

    def surface_snapshot(self) -> dict[str, bytes | None]:
        paths = [self.controller_fixture_path, *self.effective_paths]
        return {
            str(path.resolve(strict=False)): path.read_bytes() if path.exists() else None
            for path in paths
        }

    def list_effective_files(self, tool_class: str) -> list[Path]:
        self._require_tool(tool_class)
        self.events.append(f"list_effective_files:{tool_class}")
        return list(self.effective_paths)

    def probe_controller(self, tool_class: str) -> dict[str, object]:
        self._require_tool(tool_class)
        self.events.append(f"probe_controller:{tool_class}")
        certainty = {kind: kind != self.uncertainty for kind in UNCERTAINTY_KINDS}
        compatible, compatibility_reason = self._controller_compatibility()
        if self.controller_present and not compatible:
            certainty["compatibility"] = False
        uncertainty = [self.uncertainty] if self.uncertainty else []
        if self.controller_present and not compatible:
            uncertainty.append(compatibility_reason)
        explanation = (
            "fixture uncertainty: " + ", ".join(uncertainty) + " is not proven"
            if uncertainty
            else "all controller/config semantics proven by fixture adapter"
        )
        return {
            "present": self.controller_present,
            "kind": "synthetic-json-controller-fixture"
            if self.controller_present
            else "none",
            "storage_kind": "json_fixture" if self.controller_present else "none",
            "synthetic": True,
            "db_path": None,
            "fixture_path": self.controller_fixture_path
            if self.controller_present
            else None,
            "tool_class": tool_class,
            "controller_version": self.controller_version
            if self.controller_present
            else None,
            "app_version": self.controller_version if self.controller_present else None,
            "user_version": self.controller_user_version
            if self.controller_present
            else None,
            "schema_evidence": self._controller_schema_evidence(),
            "current_profile_setting_required": False,
            "database_migration_allowed": False,
            "compatibility": {
                "supported": compatible if self.controller_present else None,
                "reason": compatibility_reason if self.controller_present else "not_present",
            },
            "tool_block_proven": bool(
                self.controller_present
                and compatible
                and self.uncertainty not in {"db_schema", "field_ownership"}
            ),
            "certainty": certainty,
            "uncertainty": uncertainty,
            "explanation": explanation,
            "evidence": f"fixture://controller/{tool_class}",
        }

    def migrate_controller_database(self, *_args: object, **_kwargs: object) -> None:
        self.migration_attempts += 1
        raise AssertionError("configuration adapter must not migrate controller databases")

    def read_effective_config(
        self,
        tool_class: str,
        path: Path,
    ) -> dict[str, object]:
        self._require_tool(tool_class)
        resolved = self._require_path(path)
        self.events.append(f"read_effective_config:{tool_class}:{resolved.name}")
        try:
            parsed = _parse_fixture_config(resolved)
        except Exception as exc:
            return {
                "path": resolved,
                "parse_ok": False,
                "parsed": None,
                "error": f"{type(exc).__name__}:{exc}",
                "evidence": f"fixture://effective/{tool_class}/{resolved.name}",
            }
        return {
            "path": resolved,
            "parse_ok": True,
            "parsed": parsed,
            "sha256": _sha256_bytes(resolved.read_bytes()),
            "evidence": f"fixture://effective/{tool_class}/{resolved.name}",
        }

    def runtime_probe(self, tool_class: str) -> dict[str, object]:
        self._require_tool(tool_class)
        self.events.append(f"runtime_probe:{tool_class}")
        gaps = self.expected_gaps()
        return {
            "available": True,
            "tool_class": tool_class,
            "standard_requirements_met": not gaps,
            "evidence": f"fixture://runtime/{tool_class}",
        }

    def backup_controller_database(self, tool_class: str) -> dict[str, object]:
        self._require_tool(tool_class)
        if not self.controller_present or not self.controller_fixture_path.is_file():
            raise AssertionError("controller backup requested without controller")
        self.events.append(f"backup_controller_database:{tool_class}")
        self.mutation_events.append(f"backup_controller_database:{tool_class}")
        payload = self.controller_fixture_path.read_bytes()
        backup = self.root / "backups" / "cc-switch.db.before"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(payload)
        self._controller_original = payload
        self._controller_effective_originals = {
            path: path.read_bytes() for path in self.effective_paths
        }
        return {
            "path": backup,
            "sha256": _sha256_bytes(payload),
            "verified": backup.read_bytes() == payload,
        }

    def begin_controller_transaction(self, tool_class: str) -> dict[str, object]:
        self._require_tool(tool_class)
        self.events.append(f"begin_controller_transaction:{tool_class}")
        self.mutation_events.append(f"begin_controller_transaction:{tool_class}")
        return {"transaction_id": f"fixture-controller-{tool_class}"}

    def update_controller_tool_block(
        self,
        transaction: dict[str, object],
        tool_class: str,
        semantic_delta: dict[str, object],
    ) -> dict[str, object]:
        self._require_tool(tool_class)
        delta = self._require_delta(semantic_delta)
        if transaction.get("transaction_id") != f"fixture-controller-{tool_class}":
            raise AssertionError("wrong controller transaction")
        self.events.append(f"update_controller_tool_block:{tool_class}")
        self.mutation_events.append(f"update_controller_tool_block:{tool_class}")
        self.controller_deltas.append(delta)
        database = json.loads(
            self.controller_fixture_path.read_text(encoding="utf-8")
        )
        block = database["fixture_tool_blocks"][tool_class]
        block["semantic_delta"] = delta
        self.controller_fixture_path.write_text(
            json.dumps(database, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if self.controller_materializes:
            for path in self.effective_paths:
                updated = _apply_semantic_delta(_parse_fixture_config(path), delta)
                _write_fixture_config(path, updated)
        return {
            "updated": True,
            "tool_class": tool_class,
            "block": tool_class,
            "semantic_delta": delta,
        }

    def commit_controller_transaction(
        self,
        transaction: dict[str, object],
        tool_class: str,
    ) -> dict[str, object]:
        self._require_tool(tool_class)
        self.events.append(f"commit_controller_transaction:{tool_class}")
        self.mutation_events.append(f"commit_controller_transaction:{tool_class}")
        return {
            "receipt_id": f"fixture-controller-receipt-{tool_class}",
            "transaction_id": transaction.get("transaction_id"),
            "committed": True,
            "controller_store_sha256": _sha256_bytes(
                self.controller_fixture_path.read_bytes()
            ),
        }

    def rollback_controller_transaction(
        self,
        transaction: dict[str, object],
        tool_class: str,
        reason: str,
    ) -> dict[str, object]:
        self._require_tool(tool_class)
        self.events.append(f"rollback_controller_transaction:{tool_class}")
        self.mutation_events.append(f"rollback_controller_transaction:{tool_class}")
        if self._controller_original is None:
            raise AssertionError("controller rollback missing verified backup")
        self.controller_fixture_path.write_bytes(self._controller_original)
        for path, payload in self._controller_effective_originals.items():
            path.write_bytes(payload)
        return {
            "rollback_id": f"fixture-controller-rollback-{tool_class}",
            "transaction_id": transaction.get("transaction_id"),
            "restored": True,
            "reason": reason,
        }

    def backup_effective_file(
        self,
        tool_class: str,
        path: Path,
    ) -> dict[str, object]:
        self._require_tool(tool_class)
        resolved = self._require_path(path)
        self.events.append(f"backup_effective_file:{tool_class}:{resolved.name}")
        self.mutation_events.append(
            f"backup_effective_file:{tool_class}:{resolved.name}"
        )
        self._maybe_fail_direct_step("backup_effective_file")
        payload = resolved.read_bytes()
        backup = self.root / "backups" / f"{resolved.name}.before"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(payload)
        self._backups[resolved] = backup
        return {
            "path": resolved,
            "backup_path": backup,
            "sha256": _sha256_bytes(payload),
            "verified": backup.read_bytes() == payload,
        }

    def begin_effective_files_transaction(
        self,
        tool_class: str,
        paths: list[Path],
    ) -> dict[str, object]:
        self._require_tool(tool_class)
        resolved = [self._require_path(path) for path in paths]
        if resolved != [path.resolve(strict=False) for path in self.effective_paths]:
            raise AssertionError("effective transaction did not bind all actual files")
        self.events.append(f"begin_effective_files_transaction:{tool_class}")
        self.mutation_events.append(f"begin_effective_files_transaction:{tool_class}")
        self._maybe_fail_direct_step("begin_effective_files_transaction")
        self._direct_originals = {path: path.read_bytes() for path in resolved}
        return {"transaction_id": f"fixture-effective-{tool_class}"}

    def write_effective_config(
        self,
        transaction: dict[str, object],
        tool_class: str,
        path: Path,
        semantic_delta: dict[str, object],
    ) -> dict[str, object]:
        self._require_tool(tool_class)
        resolved = self._require_path(path)
        delta = self._require_delta(semantic_delta)
        if transaction.get("transaction_id") != f"fixture-effective-{tool_class}":
            raise AssertionError("wrong effective-files transaction")
        self._direct_write_count += 1
        self.events.append(f"write_effective_config:{tool_class}:{resolved.name}")
        self.mutation_events.append(
            f"write_effective_config:{tool_class}:{resolved.name}"
        )
        self.direct_deltas.append((resolved.name, delta))
        self._maybe_fail_direct_step("write_effective_config")
        if self.fail_direct_write_number == self._direct_write_count:
            raise RuntimeError(f"fixture direct write failure {self._direct_write_count}")
        updated = _apply_semantic_delta(_parse_fixture_config(resolved), delta)
        _write_fixture_config(resolved, updated)
        return {
            "path": resolved,
            "written": True,
            "sha256": _sha256_bytes(resolved.read_bytes()),
        }

    def commit_effective_files_transaction(
        self,
        transaction: dict[str, object],
        tool_class: str,
    ) -> dict[str, object]:
        self._require_tool(tool_class)
        self.events.append(f"commit_effective_files_transaction:{tool_class}")
        self.mutation_events.append(
            f"commit_effective_files_transaction:{tool_class}"
        )
        self._maybe_fail_direct_step("commit_effective_files_transaction")
        return {
            "receipt_id": f"fixture-effective-receipt-{tool_class}",
            "transaction_id": transaction.get("transaction_id"),
            "committed": True,
        }

    def rollback_effective_files_transaction(
        self,
        transaction: dict[str, object],
        tool_class: str,
        reason: str,
    ) -> dict[str, object]:
        self._require_tool(tool_class)
        self.events.append(f"rollback_effective_files_transaction:{tool_class}")
        self.mutation_events.append(
            f"rollback_effective_files_transaction:{tool_class}"
        )
        if not self._direct_originals:
            raise AssertionError("effective rollback missing transaction snapshot")
        for path, payload in self._direct_originals.items():
            path.write_bytes(payload)
        return {
            "rollback_id": f"fixture-effective-rollback-{tool_class}",
            "transaction_id": transaction.get("transaction_id"),
            "restored": True,
            "reason": reason,
        }

    def expected_gaps(self) -> list[str]:
        gaps: list[str] = []
        for path in self.effective_paths:
            gaps.extend(
                _delta_gaps(path, _parse_fixture_config(path), self.expected_delta)
            )
        return gaps

    def expected_evidence(self) -> list[str]:
        return [
            f"fixture://effective/{self.tool_class}/{path.name}"
            for path in self.effective_paths
        ]

    def non_delta_projection(self) -> dict[str, dict[str, object]]:
        return {
            path.name: _without_delta_fields(
                _parse_fixture_config(path), self.expected_delta
            )
            for path in self.effective_paths
        }


def _normalize_targets(result: dict[str, object]) -> list[Path]:
    raw_targets = result.get("targets")
    if not isinstance(raw_targets, list):
        raise AssertionError("result targets must be a list")
    normalized: list[Path] = []
    for index, item in enumerate(raw_targets):
        value: object = item
        if isinstance(item, dict):
            value = item.get("root", item.get("path", item.get("target")))
        if isinstance(value, Path):
            path = value
        elif isinstance(value, str) and value:
            path = Path(value)
        else:
            raise AssertionError(f"result target {index} is invalid: {item!r}")
        normalized.append(path.resolve(strict=False))
    if len(normalized) != len(set(normalized)):
        raise AssertionError("result targets contain duplicate resolved roots")
    return normalized


def _result_reason(result: object) -> str:
    if isinstance(result, dict):
        parts: list[str] = []
        for key in ("status", "reason", "reason_code"):
            value = result.get(key)
            if isinstance(value, str):
                parts.append(value)
        for key in ("reason_codes", "errors"):
            value = result.get(key)
            if isinstance(value, list):
                parts.extend(str(item) for item in value)
        return "|".join(parts)
    return str(result)


def _invoke(
    install: Callable[..., object],
    *,
    source_root: Path,
    home_root: Path,
    current_tool: str,
    explicit_tools: list[str],
    tool_roots: dict[str, Path],
    projection_manifest: Path,
    write: bool,
    fanout: bool = False,
    blank_host_configuration: dict[str, object] | None = None,
    configuration_adapter: object | None = None,
    install_transaction_adapter: object | None = None,
    platform_context: dict[str, object] | None = None,
    source_package_sha256: object | None = None,
) -> tuple[dict[str, object] | None, str | None]:
    optional: dict[str, object] = {}
    if blank_host_configuration is not None:
        optional["blank_host_configuration"] = blank_host_configuration
    if configuration_adapter is not None:
        optional["configuration_adapter"] = configuration_adapter
    if install_transaction_adapter is not None:
        optional["install_transaction_adapter"] = install_transaction_adapter
    if platform_context is not None:
        optional["platform_context"] = platform_context
    if source_package_sha256 is not None:
        optional["source_package_sha256"] = source_package_sha256
    try:
        raw = install(
            source_root=source_root,
            home_root=home_root,
            current_tool=current_tool,
            explicit_tools=explicit_tools,
            tool_roots=tool_roots,
            projection_manifest=projection_manifest,
            write=write,
            fanout=fanout,
            **optional,
        )
    except Exception as exc:
        return None, f"{type(exc).__name__}:{exc}"
    if not isinstance(raw, dict):
        return None, f"result_not_object:{raw!r}"
    if raw.get("schema") != RESULT_SCHEMA:
        return None, f"result_schema:{raw.get('schema')!r}!={RESULT_SCHEMA!r}"
    if type(raw.get("ok")) is not bool:
        return None, "result_ok_not_boolean"
    if not raw["ok"]:
        return raw, _result_reason(raw)
    return raw, None


def _require_success(
    install: Callable[..., object],
    *,
    name: str,
    expected_targets: list[Path],
    errors: list[str],
    **kwargs: Any,
) -> dict[str, object] | None:
    result, rejection = _invoke(install, **kwargs)
    if result is None or rejection is not None:
        errors.append(f"{name}:unexpected_rejection:{rejection}")
        return None
    try:
        actual = _normalize_targets(result)
    except AssertionError as exc:
        errors.append(f"{name}:{exc}")
        return None
    expected = [path.resolve(strict=False) for path in expected_targets]
    if actual != expected:
        errors.append(
            f"{name}:targets:{[str(item) for item in actual]!r}!="
            f"{[str(item) for item in expected]!r}"
        )
        return None
    if any(
        path.name != LOCATOR_POLICY_EXPECTED["install_directory_name"]
        for path in actual
    ):
        errors.append(f"{name}:physical_install_locator_drift")
        return None
    _validate_loaded_identity(
        result.get("loaded_identity"),
        label=f"{name}:loaded_identity",
        errors=errors,
    )
    return result


def _require_rejection(
    install: Callable[..., object],
    *,
    name: str,
    reason: str,
    errors: list[str],
    **kwargs: Any,
) -> bool:
    result, rejection = _invoke(install, **kwargs)
    text = rejection or _result_reason(result)
    if result is not None and result.get("ok") is True:
        errors.append(f"{name}:unexpected_success")
        return False
    if reason not in text:
        errors.append(f"{name}:reason:{text!r}:missing:{reason!r}")
        return False
    return True


def _assert_projection(
    target_root: Path,
    *,
    name: str,
    errors: list[str],
) -> None:
    for relative in PORTABLE_FILES:
        if not (target_root / Path(relative)).is_file():
            errors.append(f"{name}:portable_missing:{relative}")
    for relative in REPOSITORY_ONLY_FILES:
        if (target_root / Path(relative)).exists():
            errors.append(f"{name}:repository_only_installed:{relative}")


def _tx_fixture(temp_root: Path, label: str, legacy: bool) -> tuple[object, ...]:
    source, home, manifest, roots = _case_fixture(temp_root, label)
    targets = [_agents_root(home), roots["codex"]]
    old = [_legacy_root(root) for root in targets]
    seeded = old if legacy else targets
    sentinel = "legacy-only.txt" if legacy else "canonical-only.txt"
    marker = f"{label}-preimage"
    for index, root in enumerate(seeded):
        _write_files(
            root,
            {
                "SKILL.md": f"# {marker} court skill\n",
                "VERSION": "beta0.5.10\n",
                "scripts/portable-helper.py": f"VALUE = {marker!r}\n",
                sentinel: f"{marker}-{index}\n",
            },
        )
    return source, home, manifest, roots, targets, old, seeded, sentinel, marker


def _tx_order_ok(events: list[str]) -> bool:
    try:
        marks = (
            len(events) - 1 - events[::-1].index("source_root_backed_up"),
            events.index("projection_file_applied"),
            events.index("before_commit"),
            events.index("canonical_published"),
        )
        return marks == tuple(sorted(marks))
    except ValueError:
        return False


def _tx_kwargs(fixture: tuple[object, ...], adapter: object) -> dict[str, object]:
    source, home, manifest, roots = fixture[:4]
    return {
        "source_root": source,
        "home_root": home,
        "current_tool": "codex",
        "explicit_tools": [],
        "tool_roots": roots,
        "projection_manifest": manifest,
        "write": True,
        "install_transaction_adapter": adapter,
    }


def _tx_state(targets: list[Path], old: list[Path]) -> tuple[list[str], list[int]]:
    leftovers = [
        str(path)
        for root in targets
        for path in root.parent.glob(".*.install-migration-*")
    ]
    counts = [
        _physical_authority_count(current, previous)
        for current, previous in zip(targets, old)
    ]
    return leftovers, counts


def _check_tx_cases(
    install: Callable[..., object],
    temp_root: Path,
    errors: list[str],
    *,
    legacy: bool,
) -> int:
    name = (
        "legacy_locator_migrates_atomically_to_canonical"
        if legacy
        else "canonical_existing_root_updates_through_staged_transaction"
    )
    fixture = _tx_fixture(temp_root, name, legacy)
    source, _, _, _, targets, old, _, sentinel, marker = fixture
    adapter = _MigrationFailureAdapter()
    result = _require_success(
        install,
        name=name,
        expected_targets=targets,
        errors=errors,
        **_tx_kwargs(fixture, adapter),
    )
    passed = 0
    if result is not None:
        receipts = result.get(
            "legacy_migrations" if legacy else "install_root_transitions"
        )
        if not isinstance(receipts, list) or len(receipts) != 2:
            receipt_error = "receipt_missing" if legacy else "receipt_invalid"
        elif legacy and not all(
            isinstance(item, dict) and item.get("status") == "APPLIED"
            for item in receipts
        ):
            receipt_error = "receipt_not_applied"
        elif not legacy and not all(
            isinstance(item, dict)
            and item.get("mode") == "CANONICAL_UPDATE"
            and item.get("status") == "APPLIED"
            and item.get("source_root") == item.get("restore_root")
            for item in receipts
        ):
            receipt_error = "receipt_invalid"
        else:
            receipt_error = None
        leftovers, counts = _tx_state(targets, old)
        checks = (
            (not legacy or not any(root.exists() or root.is_symlink() for root in old), "legacy_remains"),
            (
                all(
                    (root / relative).read_bytes() == (source / relative).read_bytes()
                    for root in targets
                    for relative in ("SKILL.md", "VERSION", "scripts/portable-helper.py")
                ),
                "projection_not_updated",
            ),
            (
                all(
                    (root / sentinel).read_text(encoding="utf-8") == f"{marker}-{index}\n"
                    for index, root in enumerate(targets)
                ),
                "sentinel_not_preserved",
            ),
            (legacy or not leftovers, f"stage_leftovers:{leftovers}"),
            (not legacy or counts == [1, 1], f"physical_authority_count:{counts!r}"),
            (_tx_order_ok(adapter.events), f"checkpoint_order:{adapter.events!r}"),
        )
        failure = receipt_error or next((message for ok, message in checks if not ok), None)
        if failure:
            errors.append(f"{name}:{failure}")
        else:
            passed += 1

    for step in (
        "source_root_backed_up",
        "projection_file_applied",
        "before_commit",
        "canonical_published",
    ):
        prefix = "legacy_migration" if legacy else "canonical_update"
        case_name = f"{prefix}_{step}_restores_preimage"
        fixture = _tx_fixture(temp_root, case_name, legacy)
        _, _, _, _, targets, old, seeded, _, _ = fixture
        before = _snapshot_many(seeded)
        adapter = _MigrationFailureAdapter(step)
        if _require_rejection(
            install,
            name=case_name,
            reason="install_transaction_failed",
            errors=errors,
            **_tx_kwargs(fixture, adapter),
        ):
            leftovers, counts = _tx_state(targets, old)
            checks = (
                (
                    _snapshot_many(seeded) == before
                    and (not legacy or not any(root.exists() for root in targets)),
                    "rollback_drift",
                ),
                (not leftovers, f"stage_leftovers:{leftovers}"),
                (counts == [1, 1], f"physical_authority_count:{counts!r}"),
            )
            failure = next((message for ok, message in checks if not ok), None)
            if failure:
                errors.append(f"{case_name}:{failure}")
            else:
                passed += 1
    return passed


def _check_cases(
    install: Callable[..., object],
    temp_root: Path,
    errors: list[str],
) -> int:
    passed = 0

    source, home, manifest, roots = _case_fixture(temp_root, "codex-default")
    _prime_existing_roots(home, roots)
    before = _snapshot_many([_agents_root(home), *roots.values()])
    if _require_success(
        install,
        name="codex_default_agents_plus_current",
        expected_targets=[_agents_root(home), roots["codex"]],
        errors=errors,
        source_root=source,
        home_root=home,
        current_tool="codex",
        explicit_tools=[],
        tool_roots=roots,
        projection_manifest=manifest,
        write=False,
    ) is not None:
        after = _snapshot_many([_agents_root(home), *roots.values()])
        if after != before:
            errors.append("codex_default_agents_plus_current:plan_mutated_targets")
        else:
            passed += 1

    source, home, manifest, roots = _case_fixture(temp_root, "unknown-default")
    _prime_existing_roots(home, roots)
    if _require_success(
        install,
        name="unknown_tool_agents_only",
        expected_targets=[_agents_root(home)],
        errors=errors,
        source_root=source,
        home_root=home,
        current_tool="unknown",
        explicit_tools=[],
        tool_roots=roots,
        projection_manifest=manifest,
        write=False,
    ) is not None:
        passed += 1

    source, home, manifest, roots = _case_fixture(temp_root, "explicit-hermes")
    _prime_existing_roots(home, roots)
    if _require_success(
        install,
        name="codex_explicit_hermes",
        expected_targets=[
            _agents_root(home),
            roots["codex"],
            roots["hermes"],
        ],
        errors=errors,
        source_root=source,
        home_root=home,
        current_tool="codex",
        explicit_tools=["hermes"],
        tool_roots=roots,
        projection_manifest=manifest,
        write=False,
    ) is not None:
        passed += 1

    source, home, manifest, roots = _case_fixture(temp_root, "write-and-repeat")
    _prime_existing_roots(home, roots)
    forbidden_before = _snapshot_many(
        [roots["claude"], roots["hermes"], roots["other"]]
    )
    first = _require_success(
        install,
        name="default_write_excludes_unrequested_tools",
        expected_targets=[_agents_root(home), roots["codex"]],
        errors=errors,
        source_root=source,
        home_root=home,
        current_tool="codex",
        explicit_tools=[],
        tool_roots=roots,
        projection_manifest=manifest,
        write=True,
    )
    if first is not None:
        _assert_projection(
            _agents_root(home),
            name="default_write_agents_projection",
            errors=errors,
        )
        _assert_projection(
            roots["codex"],
            name="default_write_codex_projection",
            errors=errors,
        )
        forbidden_after = _snapshot_many(
            [roots["claude"], roots["hermes"], roots["other"]]
        )
        if forbidden_after != forbidden_before:
            errors.append(
                "default_write_excludes_unrequested_tools:forbidden_target_mutated"
            )
        else:
            passed += 1

        repeat_before = _snapshot_many([_agents_root(home), roots["codex"]])
        if _require_success(
            install,
            name="repeated_identical_write_is_idempotent",
            expected_targets=[_agents_root(home), roots["codex"]],
            errors=errors,
            source_root=source,
            home_root=home,
            current_tool="codex",
            explicit_tools=[],
            tool_roots=roots,
            projection_manifest=manifest,
            write=True,
        ) is not None:
            repeat_after = _snapshot_many([_agents_root(home), roots["codex"]])
            if repeat_after != repeat_before:
                errors.append(
                    "repeated_identical_write_is_idempotent:bytes_changed"
                )
            else:
                passed += 1

        conflict_path = _agents_root(home) / "SKILL.md"
        conflict_path.write_text("# conflicting target bytes\n", encoding="utf-8")
        if _require_success(
            install,
            name="stale_projected_bytes_update_transactionally",
            expected_targets=[_agents_root(home), roots["codex"]],
            errors=errors,
            source_root=source,
            home_root=home,
            current_tool="codex",
            explicit_tools=[],
            tool_roots=roots,
            projection_manifest=manifest,
            write=True,
        ) is not None:
            if conflict_path.read_bytes() != (source / "SKILL.md").read_bytes():
                errors.append("stale_projected_bytes_update_transactionally:not_updated")
            else:
                passed += 1

    source, home, manifest, roots = _case_fixture(temp_root, "fanout")
    _prime_existing_roots(home, roots)
    fanout_before = _snapshot_many([_agents_root(home), *roots.values()])
    if _require_rejection(
        install,
        name="fixed_five_root_fanout_rejected",
        reason="fanout_forbidden",
        errors=errors,
        source_root=source,
        home_root=home,
        current_tool="codex",
        explicit_tools=[],
        tool_roots=roots,
        projection_manifest=manifest,
        write=True,
        fanout=True,
    ):
        fanout_after = _snapshot_many([_agents_root(home), *roots.values()])
        if fanout_after != fanout_before:
            errors.append("fixed_five_root_fanout_rejected:partial_mutation")
        else:
            passed += 1

    passed += _check_tx_cases(install, temp_root, errors, legacy=True)
    passed += _check_tx_cases(install, temp_root, errors, legacy=False)

    source, home, manifest, roots = _case_fixture(temp_root, "escaped-target")
    roots["codex"] = home.parent / "outside-home" / "decretum-matrix"
    _prime_existing_roots(home, roots)
    escape_before = _snapshot_many([_agents_root(home), *roots.values()])
    if _require_rejection(
        install,
        name="target_outside_home_rejected",
        reason="target_outside_home",
        errors=errors,
        source_root=source,
        home_root=home,
        current_tool="codex",
        explicit_tools=[],
        tool_roots=roots,
        projection_manifest=manifest,
        write=True,
    ):
        escape_after = _snapshot_many([_agents_root(home), *roots.values()])
        if escape_after != escape_before:
            errors.append("target_outside_home_rejected:partial_mutation")
        else:
            passed += 1

    bad_manifest = _fixture_manifest()
    bindings = bad_manifest["persistent_bindings"]
    assert isinstance(bindings, list)
    binding = bindings[0]
    assert isinstance(binding, dict)
    binding["profile_source"] = "C:/Users/example/absolute-profile.toml"
    source, home, manifest, roots = _case_fixture(
        temp_root, "absolute-binding", bad_manifest
    )
    _prime_existing_roots(home, roots)
    invalid_before = _snapshot_many([_agents_root(home), *roots.values()])
    if _require_rejection(
        install,
        name="absolute_persisted_binding_rejected",
        reason="persisted_path_invalid",
        errors=errors,
        source_root=source,
        home_root=home,
        current_tool="codex",
        explicit_tools=[],
        tool_roots=roots,
        projection_manifest=manifest,
        write=True,
    ):
        invalid_after = _snapshot_many([_agents_root(home), *roots.values()])
        if invalid_after != invalid_before:
            errors.append(
                "absolute_persisted_binding_rejected:partial_mutation"
            )
        else:
            passed += 1

    case_root = temp_root / "relocation"
    source_a = case_root / "copy-a"
    source_b = case_root / "copy-b"
    manifest_a = _write_fixture_source(source_a)
    shutil.copytree(source_a, source_b)
    manifest_b = source_b / manifest_a.relative_to(source_a)
    relocation_ok = True
    installed_snapshots: list[dict[str, bytes]] = []
    for label, source_root, projection_manifest in (
        ("a", source_a, manifest_a),
        ("b", source_b, manifest_b),
    ):
        home = case_root / f"home-{label}"
        roots = _target_roots(home)
        _prime_existing_roots(home, roots)
        if _require_success(
            install,
            name=f"relative_binding_relocates_{label}",
            expected_targets=[_agents_root(home), roots["codex"]],
            errors=errors,
            source_root=source_root,
            home_root=home,
            current_tool="codex",
            explicit_tools=[],
            tool_roots=roots,
            projection_manifest=projection_manifest,
            write=True,
        ) is None:
            relocation_ok = False
            continue
        for target in (_agents_root(home), roots["codex"]):
            _assert_projection(
                target,
                name=f"relative_binding_relocates_{label}",
                errors=errors,
            )
        installed_snapshots.append(_snapshot(_agents_root(home)))
    if relocation_ok and len(installed_snapshots) == 2:
        if installed_snapshots[0] != installed_snapshots[1]:
            errors.append("relative_binding_relocation:installed_bytes_differ")
        else:
            passed += 1

    name = "darwin_clean_home_portable_current_tool_only"
    before_errors = len(errors)
    source, home, manifest, roots = _case_fixture(temp_root, "darwin-clean-home")
    all_roots = [_agents_root(home), *roots.values()]
    before = _snapshot_many(all_roots)
    platform_context = {
        "system": "Darwin",
        "clean_home": True,
        "home_display": "/Users/fixture",
        "persistent_path_style": "posix_relative",
        "windows_registry_available": False,
        "msi_available": False,
        "drive_letters_available": False,
        "forbid_real_host_access": True,
        "artifact_portability_evidence_request": dict(
            ARTIFACT_PORTABILITY_RED_INTERFACE
        ),
    }
    result = _require_success(
        install,
        name=name,
        expected_targets=[_agents_root(home), roots["codex"]],
        errors=errors,
        source_root=source,
        home_root=home,
        current_tool="codex",
        explicit_tools=[],
        tool_roots=roots,
        projection_manifest=manifest,
        write=True,
        platform_context=platform_context,
    )
    if result is not None:
        _assert_projection(_agents_root(home), name=name, errors=errors)
        _assert_projection(roots["codex"], name=name, errors=errors)
        targets = _normalize_targets(result)
        shared_targets = [path for path in targets if ".agents" in path.parts]
        if shared_targets != [_agents_root(home).resolve(strict=False)]:
            errors.append(f"{name}:shared_agents_not_unique:{shared_targets!r}")
        for target in (roots["claude"], roots["hermes"], roots["other"]):
            if _snapshot(target) != before[str(target.resolve(strict=False))]:
                errors.append(f"{name}:unrequested_tool_mutated:{target}")
        portability = result.get("portability_evidence")
        if not isinstance(portability, dict):
            errors.append(f"{name}:portability_evidence_missing")
        else:
            expected_portability = {
                "platform_system": "Darwin",
                "persistent_path_style": "posix_relative",
                "shared_agents_unique": True,
                "default_current_tool_only": True,
                "windows_registry_used": False,
                "msi_used": False,
                "drive_letter_required": False,
            }
            for field, expected in expected_portability.items():
                if portability.get(field) != expected:
                    errors.append(
                        f"{name}:portability:{field}:"
                        f"{portability.get(field)!r}!={expected!r}"
                    )
            if portability.get("artifact_portability") != (
                ARTIFACT_PORTABILITY_RED_INTERFACE
            ):
                errors.append(f"{name}:artifact_portability_interface_missing")
        fixture = _fixture_manifest()
        bindings = fixture["persistent_bindings"]
        assert isinstance(bindings, list)
        for binding in bindings:
            assert isinstance(binding, dict)
            if any(not _safe_relative(binding.get(field)) for field in BINDING_FIELDS):
                errors.append(f"{name}:persistent_binding_not_posix_relative")
                break
    if len(errors) == before_errors:
        passed += 1

    name = "source_package_sha256_receipt_round_trip"
    before_errors = len(errors)
    source, home, manifest, roots = _case_fixture(
        temp_root, "source-package-sha256"
    )
    _prime_existing_roots(home, roots)
    source_package_sha256 = "a" * 64
    result = _require_success(
        install,
        name=name,
        expected_targets=[_agents_root(home), roots["codex"]],
        errors=errors,
        source_root=source,
        home_root=home,
        current_tool="codex",
        explicit_tools=[],
        tool_roots=roots,
        projection_manifest=manifest,
        write=True,
        source_package_sha256=source_package_sha256,
    )
    if result is not None and result.get("source_package_sha256") != source_package_sha256:
        errors.append(f"{name}:top_level_source_package_sha256_missing")
    if len(errors) == before_errors:
        passed += 1

    name = "invalid_source_package_sha256_rejected"
    before_errors = len(errors)
    source, home, manifest, roots = _case_fixture(
        temp_root, "invalid-source-package-sha256"
    )
    _prime_existing_roots(home, roots)
    invalid_values: tuple[object, ...] = ("", "A" * 64, "g" * 64, 7)
    rejected = all(
        _require_rejection(
            install,
            name=f"{name}:{index}",
            reason="source_package_sha256_invalid",
            errors=errors,
            source_root=source,
            home_root=home,
            current_tool="codex",
            explicit_tools=[],
            tool_roots=roots,
            projection_manifest=manifest,
            write=False,
            source_package_sha256=value,
        )
        for index, value in enumerate(invalid_values)
    )
    if rejected and len(errors) == before_errors:
        passed += 1

    return passed


def _canonical_tool_roots(home_root: Path) -> dict[str, Path]:
    return {
        "codex": home_root / ".codex" / "skills" / "decretum-matrix",
        "claude-code": home_root
        / ".claude"
        / "skills"
        / "decretum-matrix",
        "hermes": home_root / ".hermes" / "skills" / "decretum-matrix",
        "other:fixture-cli": home_root
        / ".fixture-cli"
        / "skills"
        / "decretum-matrix",
    }


def _configuration_request(
    adapter: _FixtureConfigurationAdapter,
    *,
    explicit_permission: bool,
    direct_actual_file_authority: bool = False,
) -> dict[str, object]:
    request = {
        "schema": CONFIG_REQUEST_SCHEMA,
        "blank_host": True,
        "tool_class": adapter.tool_class,
        "normalized_semantic_delta": deepcopy(adapter.expected_delta),
        "newest_explicit_change_permission": explicit_permission,
        "direct_actual_file_change_authority": direct_actual_file_authority,
        "controller_probe_requirements": {
            "storage_kind": "json_fixture",
            "synthetic": True,
            "controller_version": True,
            "user_version": True,
            "database_migration_allowed": False,
        },
    }
    if adapter.tool_class == "hermes":
        request["config_path_fixture"] = {
            "effective_path": str(adapter.effective_paths[0]),
            "source": adapter.hermes_path_source,
        }
    return request


def _configuration_result(
    result: dict[str, object] | None,
    *,
    name: str,
    errors: list[str],
) -> dict[str, object] | None:
    if result is None:
        return None
    value = result.get(CONFIG_RESULT_KEY)
    if not isinstance(value, dict):
        errors.append(f"{name}:{CONFIG_RESULT_KEY}_missing")
        return None
    return value


def _invoke_configuration_case(
    install: Callable[..., object],
    *,
    case_root: Path,
    name: str,
    tool_class: str,
    write: bool,
    explicit_permission: bool,
    controller_present: bool,
    controller_materializes: bool = True,
    controller_version: str = "3.17.0",
    controller_user_version: int = 13,
    controller_schema_complete: bool = True,
    current_profile_settings_present: bool = False,
    direct_actual_file_authority: bool = False,
    uncertainty: str | None = None,
    fail_direct_write_number: int | None = None,
    fail_direct_step: str | None = None,
    hermes_platform_system: str = "Linux",
    hermes_environment: dict[str, Path] | None = None,
    hermes_config_dir_override: Path | None = None,
    errors: list[str],
) -> tuple[
    dict[str, object] | None,
    dict[str, object] | None,
    _FixtureConfigurationAdapter,
]:
    source = case_root / "source"
    home = case_root / "home"
    manifest = _write_fixture_source(source)
    roots = _canonical_tool_roots(home)
    _prime_existing_roots(home, roots)
    adapter = _FixtureConfigurationAdapter(
        case_root,
        tool_class=tool_class,
        controller_present=controller_present,
        controller_materializes=controller_materializes,
        controller_version=controller_version,
        controller_user_version=controller_user_version,
        controller_schema_complete=controller_schema_complete,
        current_profile_settings_present=current_profile_settings_present,
        uncertainty=uncertainty,
        fail_direct_write_number=fail_direct_write_number,
        fail_direct_step=fail_direct_step,
        hermes_platform_system=hermes_platform_system,
        hermes_environment=hermes_environment,
        hermes_config_dir_override=hermes_config_dir_override,
    )
    result, rejection = _invoke(
        install,
        source_root=source,
        home_root=home,
        current_tool=tool_class,
        explicit_tools=[],
        tool_roots=roots,
        projection_manifest=manifest,
        write=write,
        blank_host_configuration=_configuration_request(
            adapter,
            explicit_permission=explicit_permission,
            direct_actual_file_authority=direct_actual_file_authority,
        ),
        configuration_adapter=adapter,
    )
    if result is None:
        errors.append(f"{name}:call_failed:{rejection}")
        return None, None, adapter
    try:
        targets = _normalize_targets(result)
    except AssertionError as exc:
        errors.append(f"{name}:{exc}")
    else:
        expected = [
            _agents_root(home).resolve(strict=False),
            roots[tool_class].resolve(strict=False),
        ]
        if targets != expected:
            errors.append(f"{name}:targets:{targets!r}!={expected!r}")
    config = _configuration_result(result, name=name, errors=errors)
    return result, config, adapter


def _require_config_fields(
    config: dict[str, object],
    *,
    name: str,
    tool_class: str,
    errors: list[str],
) -> None:
    required = (
        "tool_class",
        "standard_requirements_met",
        "status",
        "compliance_claimed",
        "mutation_authorized",
        "controller_probe",
        "mutation_path",
        "upstream_attempt",
        "upstream_result",
        "uncertainty",
        "effective_files",
        "semantic_delta_verified",
        "runtime_probe",
        "unrelated_install_blocked",
        "unrelated_task_blocked",
    )
    missing = [field for field in required if field not in config]
    if missing:
        errors.append(f"{name}:result_fields_missing:{','.join(missing)}")
    if config.get("tool_class") != tool_class:
        errors.append(
            f"{name}:tool_class:{config.get('tool_class')!r}!={tool_class!r}"
        )


def _require_controller_probe_contract(
    config: dict[str, object],
    adapter: _FixtureConfigurationAdapter,
    *,
    name: str,
    expected_compatible: bool,
    errors: list[str],
) -> None:
    probe = config.get("controller_probe")
    if not isinstance(probe, dict):
        errors.append(f"{name}:controller_probe_missing")
        return
    expected = {
        "storage_kind": "json_fixture",
        "synthetic": True,
        "db_path": None,
        "controller_version": adapter.controller_version,
        "user_version": adapter.controller_user_version,
        "current_profile_setting_required": False,
        "database_migration_allowed": False,
    }
    for field, value in expected.items():
        if probe.get(field) != value:
            errors.append(
                f"{name}:controller_probe:{field}:{probe.get(field)!r}!={value!r}"
            )
    compatibility = probe.get("compatibility")
    if not isinstance(compatibility, dict) or (
        compatibility.get("supported") is not expected_compatible
    ):
        errors.append(f"{name}:controller_compatibility_not_{expected_compatible}")
    if adapter.controller_version.startswith("3.17.") and (
        adapter.controller_user_version == 13
        and expected_compatible
    ):
        schema = probe.get("schema_evidence")
        if not isinstance(schema, dict):
            errors.append(f"{name}:v13_schema_evidence_missing")
            return
        profiles = schema.get("profiles")
        if not isinstance(profiles, dict) or (
            profiles.get("exists") is not True
            or profiles.get("columns") != list(PROFILES_REQUIRED_COLUMNS)
            or profiles.get("required_columns_present") is not True
        ):
            errors.append(f"{name}:profiles_required_columns_not_proven")
        for table in V13_INPUT_TOKEN_TABLES:
            table_evidence = schema.get(table)
            if not isinstance(table_evidence, dict) or (
                table_evidence.get("exists") is not True
                or type(table_evidence.get("input_token_semantics")) is not bool
                or table_evidence.get("input_token_semantics") is not True
            ):
                errors.append(f"{name}:{table}:input_token_semantics_not_proven")


def _require_no_controller_migration(
    adapter: _FixtureConfigurationAdapter,
    *,
    name: str,
    errors: list[str],
) -> None:
    if adapter.migration_attempts:
        errors.append(f"{name}:controller_database_migration_attempted")


def _require_reversibility(
    config: dict[str, object],
    *,
    name: str,
    errors: list[str],
) -> None:
    evidence = config.get("reversibility")
    if not isinstance(evidence, dict):
        errors.append(f"{name}:reversibility_missing")
        return
    missing = [
        key
        for key in ("backup", "transaction", "receipt", "rollback")
        if not evidence.get(key)
    ]
    if missing:
        errors.append(f"{name}:reversibility_incomplete:{','.join(missing)}")


def _require_actual_files_verified(
    adapter: _FixtureConfigurationAdapter,
    *,
    name: str,
    after_event: str,
    errors: list[str],
) -> None:
    try:
        boundary = adapter.events.index(after_event)
    except ValueError:
        errors.append(f"{name}:verification_boundary_missing:{after_event}")
        return
    later = adapter.events[boundary + 1 :]
    reread_positions: list[int] = []
    for path in adapter.effective_paths:
        event = f"read_effective_config:{adapter.tool_class}:{path.name}"
        if event not in later:
            errors.append(f"{name}:actual_effective_file_not_reread:{path.name}")
        else:
            reread_positions.append(later.index(event))
        gaps = _delta_gaps(path, _parse_fixture_config(path), adapter.expected_delta)
        if gaps:
            errors.append(f"{name}:target_fields_not_satisfied:{path.name}:{gaps!r}")
    runtime_event = f"runtime_probe:{adapter.tool_class}"
    if runtime_event not in later:
        errors.append(f"{name}:runtime_probe_not_after_effective_reread")
    elif reread_positions and later.index(runtime_event) < max(reread_positions):
        errors.append(f"{name}:runtime_probe_preceded_effective_reread")


def _check_blank_host_configuration_cases(
    install: Callable[..., object],
    temp_root: Path,
    errors: list[str],
) -> int:
    passed = 0

    for tool_class in CANONICAL_TOOL_CLASSES:
        name = f"reminder_plan_{tool_class.replace(':', '_')}"
        before_errors = len(errors)
        result, config, adapter = _invoke_configuration_case(
            install,
            case_root=temp_root / name,
            name=name,
            tool_class=tool_class,
            write=False,
            explicit_permission=False,
            controller_present=True,
            errors=errors,
        )
        expected_gaps = adapter.expected_gaps()
        if result is not None and result.get("ok") is not True:
            errors.append(f"{name}:planner_blocked_install_contract")
        if config is not None:
            _require_config_fields(
                config, name=name, tool_class=tool_class, errors=errors
            )
            if config.get("status") != "REMINDER_ONLY":
                errors.append(f"{name}:status:{config.get('status')!r}")
            if config.get("gaps") != expected_gaps:
                errors.append(f"{name}:gaps_not_exact:{config.get('gaps')!r}")
            if config.get("evidence") != adapter.expected_evidence():
                errors.append(f"{name}:evidence_not_exact:{config.get('evidence')!r}")
            for field in (
                "standard_requirements_met",
                "compliance_claimed",
                "mutation_authorized",
                "unrelated_install_blocked",
                "unrelated_task_blocked",
            ):
                if config.get(field) is not False:
                    errors.append(f"{name}:{field}_must_be_false")
        if adapter.mutation_events:
            errors.append(f"{name}:planner_mutated:{adapter.mutation_events!r}")
        if adapter.surface_snapshot() != adapter.initial_surface_snapshot:
            errors.append(f"{name}:planner_changed_fixture_surfaces")
        _require_no_controller_migration(adapter, name=name, errors=errors)
        if len(errors) == before_errors:
            passed += 1

    name = "reminder_execute_does_not_block_install_or_task"
    before_errors = len(errors)
    result, config, adapter = _invoke_configuration_case(
        install,
        case_root=temp_root / name,
        name=name,
        tool_class="codex",
        write=True,
        explicit_permission=False,
        controller_present=True,
        errors=errors,
    )
    if result is not None and result.get("ok") is not True:
        errors.append(f"{name}:unrelated_install_reported_failed")
    if config is not None:
        _require_config_fields(config, name=name, tool_class="codex", errors=errors)
        if config.get("status") != "REMINDER_ONLY":
            errors.append(f"{name}:status:{config.get('status')!r}")
        if config.get("compliance_claimed") is not False:
            errors.append(f"{name}:claimed_compliant")
        if config.get("unrelated_install_blocked") is not False:
            errors.append(f"{name}:install_blocked")
        if config.get("unrelated_task_blocked") is not False:
            errors.append(f"{name}:task_blocked")
    if adapter.mutation_events:
        errors.append(f"{name}:configuration_writes:{adapter.mutation_events!r}")
    if adapter.surface_snapshot() != adapter.initial_surface_snapshot:
        errors.append(f"{name}:configuration_surface_changed")
    _require_no_controller_migration(adapter, name=name, errors=errors)
    home = temp_root / name / "home"
    _assert_projection(_agents_root(home), name=name, errors=errors)
    if len(errors) == before_errors:
        passed += 1

    for uncertainty in UNCERTAINTY_KINDS:
        name = f"uncertain_{uncertainty}_changes_nothing"
        before_errors = len(errors)
        _result, config, adapter = _invoke_configuration_case(
            install,
            case_root=temp_root / name,
            name=name,
            tool_class="codex",
            write=True,
            explicit_permission=True,
            controller_present=True,
            uncertainty=uncertainty,
            errors=errors,
        )
        if config is not None:
            _require_config_fields(
                config, name=name, tool_class="codex", errors=errors
            )
            if config.get("status") != "NO_CHANGE_UNCERTAIN":
                errors.append(f"{name}:status:{config.get('status')!r}")
            if config.get("compliance_claimed") is not False:
                errors.append(f"{name}:claimed_compliant")
            if uncertainty not in str(config.get("uncertainty")):
                errors.append(f"{name}:uncertainty_not_explained")
            if uncertainty not in str(config.get("explanation")):
                errors.append(f"{name}:explanation_missing")
        if adapter.mutation_events:
            errors.append(f"{name}:mutated:{adapter.mutation_events!r}")
        if adapter.surface_snapshot() != adapter.initial_surface_snapshot:
            errors.append(f"{name}:surface_changed")
        _require_no_controller_migration(adapter, name=name, errors=errors)
        if len(errors) == before_errors:
            passed += 1

    name = "cc_switch_3_16_5_user_version_11_is_supported"
    before_errors = len(errors)
    _result, config, adapter = _invoke_configuration_case(
        install,
        case_root=temp_root / name,
        name=name,
        tool_class="codex",
        write=True,
        explicit_permission=True,
        controller_present=True,
        controller_materializes=True,
        controller_version="3.16.5",
        controller_user_version=11,
        controller_schema_complete=False,
        errors=errors,
    )
    if config is not None:
        _require_config_fields(config, name=name, tool_class="codex", errors=errors)
        _require_controller_probe_contract(
            config,
            adapter,
            name=name,
            expected_compatible=True,
            errors=errors,
        )
        if config.get("status") != "PASSED":
            errors.append(f"{name}:status:{config.get('status')!r}")
    _require_no_controller_migration(adapter, name=name, errors=errors)
    _require_actual_files_verified(
        adapter,
        name=name,
        after_event="commit_controller_transaction:codex",
        errors=errors,
    )
    if len(errors) == before_errors:
        passed += 1

    incompatible_fixtures = (
        ("cc_switch_3_16_5_user_version_13_mismatch", "3.16.5", 13, False),
        ("cc_switch_3_17_0_user_version_11_mismatch", "3.17.0", 11, True),
        ("cc_switch_3_17_9_user_version_14_mismatch", "3.17.9", 14, True),
        ("cc_switch_unknown_3_18_0_fails_closed", "3.18.0", 13, True),
        ("cc_switch_3_17_0_missing_v13_schema_fails_closed", "3.17.0", 13, False),
    )
    for name, version, user_version, schema_complete in incompatible_fixtures:
        before_errors = len(errors)
        _result, config, adapter = _invoke_configuration_case(
            install,
            case_root=temp_root / name,
            name=name,
            tool_class="codex",
            write=True,
            explicit_permission=True,
            controller_present=True,
            controller_version=version,
            controller_user_version=user_version,
            controller_schema_complete=schema_complete,
            errors=errors,
        )
        compatibility_reason = adapter._controller_compatibility()[1]
        if config is not None:
            _require_config_fields(
                config, name=name, tool_class="codex", errors=errors
            )
            _require_controller_probe_contract(
                config,
                adapter,
                name=name,
                expected_compatible=False,
                errors=errors,
            )
            if config.get("status") != "NO_CHANGE_UNCERTAIN":
                errors.append(f"{name}:status:{config.get('status')!r}")
            if config.get("compliance_claimed") is not False:
                errors.append(f"{name}:claimed_compliant")
            if compatibility_reason not in str(config.get("uncertainty")):
                errors.append(f"{name}:compatibility_uncertainty_missing")
            if compatibility_reason not in str(config.get("explanation")):
                errors.append(f"{name}:compatibility_explanation_missing")
        if adapter.mutation_events:
            errors.append(f"{name}:mutated:{adapter.mutation_events!r}")
        if adapter.surface_snapshot() != adapter.initial_surface_snapshot:
            errors.append(f"{name}:surface_changed")
        _require_no_controller_migration(adapter, name=name, errors=errors)
        if len(errors) == before_errors:
            passed += 1

    name = "codex_controller_first_then_effective_files_verified"
    before_errors = len(errors)
    _result, config, adapter = _invoke_configuration_case(
        install,
        case_root=temp_root / name,
        name=name,
        tool_class="codex",
        write=True,
        explicit_permission=True,
        controller_present=True,
        controller_materializes=True,
        errors=errors,
    )
    if config is not None:
        _require_config_fields(config, name=name, tool_class="codex", errors=errors)
        _require_controller_probe_contract(
            config,
            adapter,
            name=name,
            expected_compatible=True,
            errors=errors,
        )
        _require_reversibility(config, name=name, errors=errors)
        if config.get("status") != "PASSED":
            errors.append(f"{name}:status:{config.get('status')!r}")
        if config.get("standard_requirements_met") is not True:
            errors.append(f"{name}:standard_not_met")
        if config.get("semantic_delta_verified") is not True:
            errors.append(f"{name}:semantic_delta_not_verified")
        if config.get("mutation_path") != "cc_switch_upstream_then_effective_files":
            errors.append(f"{name}:mutation_path:{config.get('mutation_path')!r}")
    expected_order = [
        "backup_controller_database:codex",
        "begin_controller_transaction:codex",
        "update_controller_tool_block:codex",
        "commit_controller_transaction:codex",
    ]
    positions = [adapter.events.index(item) for item in expected_order if item in adapter.events]
    if len(positions) != len(expected_order) or positions != sorted(positions):
        errors.append(f"{name}:controller_transaction_order:{adapter.events!r}")
    if adapter.direct_deltas:
        errors.append(f"{name}:leaf_only_write_attempted:{adapter.direct_deltas!r}")
    if adapter.controller_deltas != [CODEX_NORMALIZED_SEMANTIC_DELTA]:
        errors.append(f"{name}:controller_delta:{adapter.controller_deltas!r}")
    _require_no_controller_migration(adapter, name=name, errors=errors)
    _require_actual_files_verified(
        adapter,
        name=name,
        after_event="commit_controller_transaction:codex",
        errors=errors,
    )
    initial_projection = {
        path.name: _without_delta_fields(
            adapter.initial_parsed[path], adapter.expected_delta
        )
        for path in adapter.effective_paths
    }
    if adapter.non_delta_projection() != initial_projection:
        errors.append(f"{name}:secret_provider_or_unknown_key_changed")
    if adapter.expected_gaps():
        errors.append(f"{name}:actual_effective_files_noncompliant")
    if adapter.effective_paths[0].read_bytes() == adapter.effective_paths[1].read_bytes():
        errors.append(f"{name}:overlays_were_forced_byte_identical")
    controller_fixture = json.loads(
        adapter.controller_fixture_path.read_text(encoding="utf-8")
    )
    if any(key.startswith("current_profile_id_") for key in controller_fixture["settings"]):
        errors.append(f"{name}:optional_current_profile_setting_was_required")
    if len(errors) == before_errors:
        passed += 1

    name = "codex_db_receipt_without_materialization_rolls_back"
    before_errors = len(errors)
    _result, config, adapter = _invoke_configuration_case(
        install,
        case_root=temp_root / name,
        name=name,
        tool_class="codex",
        write=True,
        explicit_permission=True,
        controller_present=True,
        controller_materializes=False,
        errors=errors,
    )
    if config is not None:
        _require_controller_probe_contract(
            config,
            adapter,
            name=name,
            expected_compatible=True,
            errors=errors,
        )
        if config.get("status") == "PASSED" or config.get("compliance_claimed") is True:
            errors.append(f"{name}:db_receipt_claimed_success")
    if adapter.direct_deltas:
        errors.append(f"{name}:leaf_only_fallback_used:{adapter.direct_deltas!r}")
    if "rollback_controller_transaction:codex" not in adapter.events:
        errors.append(f"{name}:controller_rollback_missing")
    if adapter.surface_snapshot() != adapter.initial_surface_snapshot:
        errors.append(f"{name}:rollback_did_not_restore_surfaces")
    _require_no_controller_migration(adapter, name=name, errors=errors)
    if len(errors) == before_errors:
        passed += 1

    name = "codex_without_controller_dual_file_transaction"
    before_errors = len(errors)
    _result, config, adapter = _invoke_configuration_case(
        install,
        case_root=temp_root / name,
        name=name,
        tool_class="codex",
        write=True,
        explicit_permission=True,
        controller_present=False,
        errors=errors,
    )
    if config is not None:
        _require_reversibility(config, name=name, errors=errors)
        if config.get("status") != "PASSED":
            errors.append(f"{name}:status:{config.get('status')!r}")
        if config.get("mutation_path") != "direct_reversible_effective_files":
            errors.append(f"{name}:mutation_path:{config.get('mutation_path')!r}")
    if [item[0] for item in adapter.direct_deltas] != [
        "config.toml",
        "managed_config.toml",
    ]:
        errors.append(f"{name}:dual_file_delta_missing:{adapter.direct_deltas!r}")
    if any(delta != CODEX_NORMALIZED_SEMANTIC_DELTA for _, delta in adapter.direct_deltas):
        errors.append(f"{name}:normalized_delta_drift")
    _require_actual_files_verified(
        adapter,
        name=name,
        after_event="commit_effective_files_transaction:codex",
        errors=errors,
    )
    if adapter.expected_gaps():
        errors.append(f"{name}:dual_file_result_noncompliant")
    if adapter.effective_paths[0].read_bytes() == adapter.effective_paths[1].read_bytes():
        errors.append(f"{name}:dual_toml_files_were_forced_byte_identical")
    if len(errors) == before_errors:
        passed += 1

    name = "codex_dual_file_failure_rolls_back_atomically"
    before_errors = len(errors)
    _result, config, adapter = _invoke_configuration_case(
        install,
        case_root=temp_root / name,
        name=name,
        tool_class="codex",
        write=True,
        explicit_permission=True,
        controller_present=False,
        fail_direct_write_number=2,
        errors=errors,
    )
    if config is not None and (
        config.get("status") == "PASSED" or config.get("compliance_claimed") is True
    ):
        errors.append(f"{name}:partial_write_claimed_success")
    if "rollback_effective_files_transaction:codex" not in adapter.events:
        errors.append(f"{name}:rollback_missing")
    if adapter.surface_snapshot() != adapter.initial_surface_snapshot:
        errors.append(f"{name}:rollback_did_not_restore_both_files")
    if len(errors) == before_errors:
        passed += 1

    for direct_authority in (False, True):
        suffix = "authorized" if direct_authority else "unauthorized"
        name = f"hermes_controller_nonmaterialization_{suffix}_fallback"
        before_errors = len(errors)
        _result, config, adapter = _invoke_configuration_case(
            install,
            case_root=temp_root / name,
            name=name,
            tool_class="hermes",
            write=True,
            explicit_permission=True,
            controller_present=True,
            controller_materializes=False,
            direct_actual_file_authority=direct_authority,
            errors=errors,
        )
        if not direct_authority:
            if config is not None and (
                config.get("status") == "PASSED"
                or config.get("compliance_claimed") is True
            ):
                errors.append(f"{name}:claimed_success")
            if adapter.direct_deltas:
                errors.append(f"{name}:unauthorized_direct_fallback")
            if adapter.surface_snapshot() != adapter.initial_surface_snapshot:
                errors.append(f"{name}:unauthorized_surface_change")
        else:
            if config is not None:
                _require_reversibility(config, name=name, errors=errors)
                if config.get("status") != "PASSED":
                    errors.append(f"{name}:status:{config.get('status')!r}")
            if not adapter.direct_deltas:
                errors.append(f"{name}:authorized_fallback_not_used")
            controller_index = adapter.events.index(
                "update_controller_tool_block:hermes"
            ) if "update_controller_tool_block:hermes" in adapter.events else -1
            direct_events = [
                index
                for index, event in enumerate(adapter.events)
                if event.startswith("write_effective_config:hermes:")
            ]
            if controller_index < 0 or not direct_events or controller_index >= direct_events[0]:
                errors.append(f"{name}:fallback_not_controller_first")
            if adapter.expected_gaps():
                errors.append(f"{name}:fallback_not_effective")
            _require_actual_files_verified(
                adapter,
                name=name,
                after_event="commit_effective_files_transaction:hermes",
                errors=errors,
            )
        _require_no_controller_migration(adapter, name=name, errors=errors)
        if len(errors) == before_errors:
            passed += 1

    hermes_path_cases = (
        "explicit_override",
        "hermes_home",
        "windows_localappdata",
        "windows_home_localappdata_fallback",
        "darwin_posix_home_default",
    )
    for path_case in hermes_path_cases:
        name = f"hermes_config_path_{path_case}"
        before_errors = len(errors)
        case_root = temp_root / name
        home = case_root / "home"
        environment: dict[str, Path] = {}
        explicit_config_dir: Path | None = None
        platform_system = "Windows"
        if path_case == "explicit_override":
            explicit_config_dir = case_root / "override"
            environment = {
                "HERMES_HOME": case_root / "ignored-hermes-home",
                "LOCALAPPDATA": case_root / "ignored-localappdata",
            }
            expected = explicit_config_dir / "config.yaml"
            expected_source = "ccs_hermes_config_dir_override"
        elif path_case == "hermes_home":
            environment = {
                "HERMES_HOME": case_root / "hermes-home",
                "LOCALAPPDATA": case_root / "ignored-localappdata",
            }
            expected = environment["HERMES_HOME"] / "config.yaml"
            expected_source = "HERMES_HOME"
        elif path_case == "windows_localappdata":
            environment = {"LOCALAPPDATA": case_root / "localappdata"}
            expected = environment["LOCALAPPDATA"] / "hermes" / "config.yaml"
            expected_source = "LOCALAPPDATA"
        elif path_case == "windows_home_localappdata_fallback":
            expected = home / "AppData" / "Local" / "hermes" / "config.yaml"
            expected_source = "windows_home_localappdata_fallback"
        else:
            platform_system = "Darwin"
            expected = home / ".hermes" / "config.yaml"
            expected_source = "posix_home_default"
        _result, config, adapter = _invoke_configuration_case(
            install,
            case_root=case_root,
            name=name,
            tool_class="hermes",
            write=False,
            explicit_permission=False,
            controller_present=False,
            hermes_platform_system=platform_system,
            hermes_environment=environment,
            hermes_config_dir_override=explicit_config_dir,
            errors=errors,
        )
        expected = expected.resolve(strict=False)
        if len(adapter.effective_paths) != 1 or not _same_filesystem_path(
            adapter.effective_paths[0], expected
        ):
            errors.append(f"{name}:effective_path:{adapter.effective_paths!r}!={[expected]!r}")
        if adapter.hermes_path_source != expected_source:
            errors.append(
                f"{name}:path_source:{adapter.hermes_path_source!r}!={expected_source!r}"
            )
        if platform_system == "Windows" and adapter.effective_paths == [
            (home / ".hermes" / "config.yaml").resolve(strict=False)
        ]:
            errors.append(f"{name}:windows_defaulted_to_dot_hermes")
        if config is not None:
            _require_config_fields(
                config, name=name, tool_class="hermes", errors=errors
            )
            if config.get("status") != "REMINDER_ONLY":
                errors.append(f"{name}:status:{config.get('status')!r}")
            effective_files = config.get("effective_files")
            if not isinstance(effective_files, list) or not any(
                isinstance(item, (str, Path))
                and _same_filesystem_path(Path(item), expected)
                for item in effective_files
            ):
                errors.append(f"{name}:effective_file_evidence_missing")
        if "list_effective_files:hermes" not in adapter.events:
            errors.append(f"{name}:adapter_path_fixture_not_used")
        if adapter.mutation_events:
            errors.append(f"{name}:planner_mutated:{adapter.mutation_events!r}")
        if adapter.surface_snapshot() != adapter.initial_surface_snapshot:
            errors.append(f"{name}:planner_changed_fixture_surfaces")
        _require_no_controller_migration(adapter, name=name, errors=errors)
        if len(errors) == before_errors:
            passed += 1

    for failure_step in DIRECT_FAILURE_STEPS:
        name = f"hermes_direct_fallback_{failure_step}_failure_rolls_back"
        before_errors = len(errors)
        _result, config, adapter = _invoke_configuration_case(
            install,
            case_root=temp_root / name,
            name=name,
            tool_class="hermes",
            write=True,
            explicit_permission=True,
            controller_present=True,
            controller_materializes=False,
            direct_actual_file_authority=True,
            fail_direct_step=failure_step,
            errors=errors,
        )
        if config is not None and (
            config.get("status") == "PASSED"
            or config.get("compliance_claimed") is True
        ):
            errors.append(f"{name}:step_failure_claimed_success")
        controller_event = "update_controller_tool_block:hermes"
        failure_events = [
            index
            for index, event in enumerate(adapter.events)
            if event.startswith(f"{failure_step}:hermes")
        ]
        if controller_event not in adapter.events or not failure_events:
            errors.append(f"{name}:controller_or_failure_step_missing")
        elif adapter.events.index(controller_event) >= failure_events[0]:
            errors.append(f"{name}:direct_failure_not_after_controller_first")
        if failure_step in {
            "write_effective_config",
            "commit_effective_files_transaction",
        } and "rollback_effective_files_transaction:hermes" not in adapter.events:
            errors.append(f"{name}:effective_rollback_missing")
        if adapter.surface_snapshot() != adapter.initial_surface_snapshot:
            errors.append(f"{name}:failure_did_not_restore_all_surfaces")
        _require_no_controller_migration(adapter, name=name, errors=errors)
        if len(errors) == before_errors:
            passed += 1

    return passed


def evaluate() -> dict[str, object]:
    errors: list[str] = []
    actual_manifest = _load_json(
        PROJECTION_MANIFEST_PATH,
        label="manifest",
        errors=errors,
    )
    manifest_ok = False
    if actual_manifest is not None:
        manifest_ok = _validate_manifest(
            actual_manifest,
            label="repository_manifest",
            errors=errors,
        )
        identity_manifest = _load_json(
            IDENTITY_MANIFEST_PATH,
            label="identity_manifest",
            errors=errors,
        )
        if identity_manifest is None or not _validate_loaded_identity(
            identity_manifest,
            label="repository_identity",
            errors=errors,
        ):
            manifest_ok = False

    module = _load_production(errors)
    passed = 0
    configuration_passed = 0
    if module is not None:
        target = getattr(module, "install_current_agent_copy", None)
        if not callable(target):
            errors.append("missing_callable:install_current_agent_copy")
            errors.extend(INSTALL_UNEXERCISED_GAPS)
            errors.extend(CONFIG_UNEXERCISED_GAPS)
        else:
            with tempfile.TemporaryDirectory(
                prefix="court-install-current-agent-red-"
            ) as temp_dir:
                passed = _check_cases(target, Path(temp_dir), errors)
            with tempfile.TemporaryDirectory(
                prefix="court-blank-host-config-red-"
            ) as temp_dir:
                configuration_passed = _check_blank_host_configuration_cases(
                    target,
                    Path(temp_dir),
                    errors,
                )
    else:
        errors.extend(INSTALL_UNEXERCISED_GAPS)
        errors.extend(CONFIG_UNEXERCISED_GAPS)

    return {
        "ok": not errors,
        "schema": CHECK_SCHEMA,
        "production_module": str(PRODUCTION_PATH),
        "projection_manifest": str(PROJECTION_MANIFEST_PATH),
        "identity_manifest": str(IDENTITY_MANIFEST_PATH),
        "canonical_loaded_identity": dict(LOADED_IDENTITY_EXPECTED),
        "preserved_locator_policy": dict(LOCATOR_POLICY_EXPECTED),
        "declared_cases": 23,
        "passed_cases": passed,
        "declared_configuration_cases": 31,
        "passed_configuration_cases": configuration_passed,
        "declared_artifact_portability_evidence_interfaces": len(
            ARTIFACT_PORTABILITY_RED_INTERFACE
        ),
        "artifact_portability_red_interface": dict(
            ARTIFACT_PORTABILITY_RED_INTERFACE
        ),
        "temporary_fixtures_only": True,
        "configuration_adapter_injected": True,
        "controller_fixture_storage_kind": "json_fixture",
        "controller_fixture_synthetic": True,
        "real_cc_switch_or_codex_accessed": False,
        "pending_body_accessed": False,
        "errors": errors,
    }


def main() -> int:
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
