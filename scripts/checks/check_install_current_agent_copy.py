

#!/usr/bin/env python3
"""Deterministic install/config checks using isolated injected fixtures."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
import runpy
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable
from unittest import mock
import zlib
import zipfile

sys.dont_write_bytecode = True
Payload = dict[str, object]
Installer = Callable[..., object]

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_PATH = ROOT / "scripts" / "install_current_agent_copy.py"
PROJECTION_MANIFEST_PATH = ROOT / "references" / "manifests" / "install-projection.v1.json"
IDENTITY_MANIFEST_RELATIVE = "references/manifests/skill-identity.v1.json"
IDENTITY_MANIFEST_PATH = ROOT / Path(IDENTITY_MANIFEST_RELATIVE)

RESULT_SCHEMA = "court.install_current_agent_copy.result.v1"
CHECK_SCHEMA = "court.install_current_agent_copy.check.v1"
PROJECTION_SCHEMA = "court.install_projection.v1"
ACTIVE_RENDER_SCHEMA = "court.install_projection.active_render.v1"
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
    "display_name": "Decretum Matrix（诏令矩阵）",
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
CONFIG_UNEXERCISED_GAPS = tuple(
    f"{stem}_unexercised:install_current_agent_copy unavailable"
    for stem in (
        "blank_host_config_public_planner",
        "blank_host_config_public_executor",
        "blank_host_config_tool_class_matrix",
        "blank_host_config_reminder_nonblocking",
        "blank_host_config_controller_first",
        "blank_host_config_effective_file_verification",
        "blank_host_config_direct_transaction",
        "blank_host_config_uncertainty_fail_closed",
        "blank_host_config_hermes_fallback_gate",
        "cc_switch_synthetic_json_fixture_contract",
        "cc_switch_version_schema_matrix",
        "hermes_config_path_precedence",
        "hermes_step_failure_rollback",
    )
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
    "cli_public",
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
    "release-manifest.json",
    "agents/standing-officials/gongbu.toml",
    "agents/supercc-dossiers/gongbu/AGENTS.md",
    IDENTITY_MANIFEST_RELATIVE,
    "references/manifests/install-projection.v1.json",
    "references/manifests/cli-command-surface.v1.json",
    "scripts/portable-helper.py",
)
PROTECTED_SEEDS = {
    "references/shiguan-index.jsonl": "",
    "references/shiguan-knowledge-graph.json": "{}",
    "references/shiguan-tree/_index.md": "tree seed",
    "references/shiguan-tree/capability-index/_index.md": "capability seed",
}
REPOSITORY_ONLY_FILES = (
    "docs/internal-plan.md",
)
SOURCE_ONLY_CHECKER = "scripts/checks/check_fixture.py"
A_B_ROOT_COMPATIBILITY_SHELL = "scripts/sync_active_copies.py"
A_B_COMMAND_BODY = "scripts/commands/sync_active_copies.py"
A_B_SERVICE_BODY = "scripts/services/serve_shiguan_tree.py"
A_B_ROOT_SOURCE_ONLY_CHECKER = "scripts/check_active_copy_hashes.py"
A_B_CHECKS_SOURCE_ONLY_CHECKER = "scripts/checks/check_active_copy_hashes.py"


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
        return os.path.normcase(os.path.realpath(os.path.abspath(str(left)))) == os.path.normcase(
            os.path.realpath(os.path.abspath(str(right)))
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

    if manifest.get("protected_shared_agents_seeds") != []:
        errors.append(f"{label}:protected_shared_agents_seeds")

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


def _fixture_manifest() -> Payload:
    return {
        "schema": PROJECTION_SCHEMA,
        "schema_version": 1,
        "identity_manifest": IDENTITY_MANIFEST_RELATIVE,
        "policy": dict(POLICY_EXPECTED),
        "protected_shared_agents_seeds": [],
        "frozen_install_references": [],
        "active_render": {
            "schema": ACTIVE_RENDER_SCHEMA,
            "path_matcher": "posix_glob.v1",
            "exclude_path_globs": ["scripts/check_*.py", "scripts/checks/**"],
            "excluded_cli_groups": ["check", "release"],
        },
        "projections": {
            "shared_agents": list(PORTABLE_FILES),
            "portable_current_tool": list(PORTABLE_FILES),
            "cli_public": [],
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
    manifest: Payload | None = None,
) -> Path:
    contents = {
        "SKILL.md": "# fixture court skill\n",
        "VERSION": "beta1.0.1\n",
        "release-manifest.json": '{"schema":"court.release_manifest.v2"}\n',
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
        SOURCE_ONLY_CHECKER: "CHECKER = 'source-only'\n",
        "references/manifests/cli-command-surface.v1.json": json.dumps(
            {
                "schema": "court.cli.command_surface.v1",
                "groups": ["court", "check", "release"],
                "entries": [
                    {"group": "court", "command": "status", "mcp": {"name": "court.status"}},
                    {"group": "check", "command": "fixture-check"},
                    {"group": "release", "command": "fixture-release"},
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        "docs/internal-plan.md": "# repository only\n",
    }
    contents.update(PROTECTED_SEEDS)
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
    manifest_data: Payload | None = None,
) -> tuple[object, ...]:
    case_root = temp_root / _fixture_slug(label)
    source, home = case_root / "source", case_root / "home"
    manifest = _write_fixture_source(source, manifest=manifest_data)
    return source, home, manifest, _target_roots(home)


def _fixture_slug(label: str) -> str:
    """Short stable fixture subdirectory name (Windows MAX_PATH guard).

    Fixture labels are descriptive but can be long (50+ chars); combined with
    the deep ``home/.agents/install-backups/...`` nesting they push real temp
    paths past Windows' 260-char limit, which surfaces as spurious
    ``FileNotFoundError`` on NamedTemporaryFile/os.replace. A short stable
    CRC-32 slug keeps every fixture path well under the limit while staying
    deterministic and collision-resistant for the ~30 fixed labels.
    """

    return f"c{zlib.crc32(str(label).encode('utf-8')) & 0xFFFFFFFF:08x}"


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

    def checkpoint(self, step: str, evidence: Payload) -> None:
        self.events.append(step)
        if step == self.fail_step:
            raise RuntimeError(f"fixture install transaction failure: {step}")


class _AliasFailureAdapter(_MigrationFailureAdapter):
    def __init__(self, legacy: Path, canonical: Path, physical: Path) -> None:
        super().__init__()
        self.initial = {str(legacy): str(physical)}
        self.aliases = dict(self.initial)
        self.prepared: dict[str, str] = {}
        self.physical = physical

    def prepare_alias(self, *, legacy_alias: Path, canonical_alias: Path, physical_root: Path) -> dict[str, str]:
        self.events.append("alias_prepare")
        receipt = {
            "legacy_alias": str(legacy_alias),
            "canonical_alias": str(canonical_alias),
            "physical_root": str(physical_root),
            "prepared_alias": str(canonical_alias.with_name(f".{canonical_alias.name}.alias-prepared")),
        }
        self.prepared[receipt["prepared_alias"]] = receipt["physical_root"]
        return receipt

    def commit_alias(self, receipt: dict[str, str]) -> None:
        self.events.append("alias_commit")
        self.aliases.pop(receipt["legacy_alias"], None)
        self.aliases[receipt["canonical_alias"]] = receipt["physical_root"]
        self.prepared.pop(receipt["prepared_alias"], None)
        raise RuntimeError("fixture alias commit failure")

    def rollback_alias(self, receipt: dict[str, str]) -> None:
        if not self.physical.is_dir():
            raise AssertionError("alias_rollback_before_physical_restore")
        self.events.append("alias_rollback")
        self.aliases = dict(self.initial)
        self.prepared.clear()


def _prime_roots(home_root: Path, tool_roots: dict[str, Path]) -> None:
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


def _snapshots(roots: list[Path]) -> dict[str, dict[str, bytes]]:
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


def _nested_set(data: Payload, dotted_key: str, value: object) -> None:
    current = data
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = deepcopy(value)


def _nested_remove(data: Payload, dotted_key: str) -> None:
    current: object = data
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict):
            return
        current = current.get(part)
    if isinstance(current, dict):
        current.pop(parts[-1], None)


def _apply_semantic_delta(
    data: Payload,
    delta: Payload,
) -> Payload:
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
    data: Payload,
    delta: Payload,
) -> Payload:
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


def _render_fixture_toml(data: Payload) -> str:
    lines: list[str] = []

    def emit_table(table: Payload, prefix: tuple[str, ...]) -> None:
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


def _parse_fixture_config(path: Path) -> Payload:
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


def _write_fixture_config(path: Path, data: Payload) -> None:
    if path.suffix.lower() == ".toml":
        text = _render_fixture_toml(data)
    else:
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def _delta_gaps(
    path: Path,
    data: Payload,
    delta: Payload,
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


class _ConfigFixture:
    def __init__(
        self,
        root: Path,
        *,
        tool_class: str,
        has_controller: bool,
        **options: object,
    ) -> None:
        values = {
            "controller_materializes": True,
            "controller_version": "3.17.0",
            "controller_user_version": 13,
            "controller_schema_complete": True,
            "current_profile_settings_present": False,
            "uncertainty": None,
            "fail_direct_write_number": None,
            "fail_direct_step": None,
            "hermes_platform_system": "Linux",
            "hermes_environment": None,
            "hermes_config_dir_override": None,
        }
        values.update(options)
        uncertainty = values["uncertainty"]
        fail_direct_step = values["fail_direct_step"]
        if tool_class not in CANONICAL_TOOL_CLASSES:
            raise ValueError(f"unsupported fixture tool class: {tool_class}")
        if uncertainty is not None and uncertainty not in UNCERTAINTY_KINDS:
            raise ValueError(f"unsupported fixture uncertainty: {uncertainty}")
        if fail_direct_step is not None and fail_direct_step not in DIRECT_FAILURE_STEPS:
            raise ValueError(f"unsupported direct failure step: {fail_direct_step}")
        self.root = root.resolve()
        self.tool_class = tool_class
        self.has_controller = has_controller
        self.__dict__.update(values)
        self.events: list[str] = []
        self.mutation_events: list[str] = []
        self.migration_attempts = 0
        self.controller_deltas: list[Payload] = []
        self.direct_deltas: list[tuple[str, Payload]] = []
        self._direct_write_count = 0
        self._controller_original: bytes | None = None
        self._controller_effective_originals: dict[Path, bytes] = {}
        self._direct_originals: dict[Path, bytes] = {}
        self._backups: dict[Path, Path] = {}

        home = self.root / "home"
        self.controller_path = (
            self.root / "fixtures" / "cc-switch-controller.json"
        )
        if tool_class == "hermes":
            hermes_path, hermes_path_source = _fixture_hermes_config_path(
                home,
                platform_system=values["hermes_platform_system"],
                environment=dict(values["hermes_environment"] or {}),
                explicit_config_dir=values["hermes_config_dir_override"],
            )
            self.paths = [hermes_path]
            self.hermes_path_source = hermes_path_source
        else:
            relatives = {
                "codex": (".codex/config.toml", ".codex/managed_config.toml"),
                "claude-code": (".claude/settings.json",),
                "other:fixture-cli": (".fixture-cli/config.json",),
            }
            self.paths = [home / relative for relative in relatives[tool_class]]
        delta = (
            CODEX_NORMALIZED_SEMANTIC_DELTA
            if tool_class == "codex"
            else GENERIC_NORMALIZED_SEMANTIC_DELTA
        )
        self.expected_delta = deepcopy(delta)

        self._create_effective_fixtures()
        if has_controller:
            self.controller_path.parent.mkdir(parents=True, exist_ok=True)
            profile_columns = list(PROFILES_REQUIRED_COLUMNS)
            if not self.controller_schema_complete:
                profile_columns.remove("updated_at")
            schema_evidence = {
                "profiles": {
                    "exists": self.controller_schema_complete,
                    "columns": profile_columns,
                    "required_columns_present": self.controller_schema_complete,
                },
                **{
                    table: {
                        "exists": self.controller_schema_complete,
                        "input_token_semantics": self.controller_schema_complete,
                    }
                    for table in V13_INPUT_TOKEN_TABLES
                },
            }
            self.controller_path.write_text(
                json.dumps(
                    {
                        "schema": "fixture.cc_switch.v1",
                        "storage_kind": "json_fixture",
                        "synthetic": True,
                        "controller_version": self.controller_version,
                        "app_version": self.controller_version,
                        "user_version": self.controller_user_version,
                        "schema_evidence": schema_evidence,
                        "settings": {
                            "current_profile_id_codex": "fixture-profile"
                        }
                        if self.current_profile_settings_present
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
                self.controller_path.read_text(encoding="utf-8")
            )
            if (
                fixture.get("storage_kind") != "json_fixture"
                or fixture.get("synthetic") is not True
                or "tool_blocks" in fixture
            ):
                raise AssertionError("controller JSON fixture masquerades as SQLite")
        self.initial_snapshot = self.surface_snapshot()
        self.initial_parsed = {
            path: _parse_fixture_config(path) for path in self.paths
        }

    def _controller_schema_evidence(self) -> Payload:
        if not self.has_controller:
            return {}
        fixture = json.loads(
            self.controller_path.read_text(encoding="utf-8")
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
        for path in self.paths:
            path.parent.mkdir(parents=True, exist_ok=True)
        if self.tool_class == "codex":
            layers = (
                ("base", "fixture", "config", 1, 3, 2, "goals", True),
                ("managed", "managed", "managed", 2, 5, 7, "multi_agent", False),
            )
            for path, row in zip(self.paths, layers):
                layer, provider, top, depth, threads, concurrency, flag, value = row
                _write_fixture_config(
                    path,
                    {
                        "model_provider": f"fixture-{layer}-provider",
                        "api_key": "fixture",
                        "unknown_top": f"preserve-{top}-top",
                        "agents": {
                            "max_depth": depth,
                            "max_threads": threads,
                            f"{layer}_agent_unknown": f"preserve-{layer}-agent",
                        },
                        "features": {
                            flag: value,
                            "multi_agent_v2": {
                                "enabled": False,
                                "max_concurrent_threads_per_session": concurrency,
                                "hide_spawn_agent_metadata": False,
                                f"{layer}_overlay_unknown": f"preserve-{layer}-overlay",
                            },
                        },
                        "providers": {
                            provider: {
                                "base_url": f"https://{layer}.fixture.invalid",
                                "token": "fixture",
                            }
                        },
                        "unknown": {layer: {"keep": f"{layer}-unknown"}},
                    },
                )
            return
        generic = {
            "court": {"blank_host": {"ready": False}},
            "secret": "fixture",
            "provider": {"id": f"fixture-{self.tool_class}"},
            "unknown": {"keep": f"preserve-{self.tool_class}"},
        }
        _write_fixture_config(self.paths[0], generic)

    def _require_tool(self, tool_class: str) -> None:
        if tool_class != self.tool_class:
            raise AssertionError(
                f"adapter tool mismatch: {tool_class!r}!={self.tool_class!r}"
            )

    def _require_path(self, path: Path) -> Path:
        resolved = Path(path).resolve(strict=False)
        if resolved not in [item.resolve(strict=False) for item in self.paths]:
            raise AssertionError(f"non-fixture effective path requested: {path}")
        if self.root not in resolved.parents:
            raise AssertionError(f"path escaped TemporaryDirectory: {path}")
        return resolved

    def _require_delta(self, delta: object) -> Payload:
        if delta != self.expected_delta:
            raise AssertionError(
                f"semantic delta drift: {delta!r}!={self.expected_delta!r}"
            )
        if not isinstance(delta, dict):
            raise AssertionError("semantic delta must be structured")
        return deepcopy(delta)

    def _record(
        self, tool_class: str, action: str, *, mutation: bool = False
    ) -> None:
        self._require_tool(tool_class)
        event = f"{action}:{self.tool_class}"
        self.events.append(event)
        if mutation:
            self.mutation_events.append(event)

    @staticmethod
    def _backup(source: Path, backup: Path) -> tuple[bytes, Payload]:
        payload = source.read_bytes()
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(payload)
        return payload, {
            "sha256": _sha256_bytes(payload),
            "verified": backup.read_bytes() == payload,
        }

    @staticmethod
    def _commit_receipt(transaction: Payload, kind: str, tool_class: str) -> Payload:
        return {
            "receipt_id": f"fixture-{kind}-receipt-{tool_class}",
            "transaction_id": transaction.get("transaction_id"),
            "committed": True,
        }

    @staticmethod
    def _rollback_receipt(
        transaction: Payload, kind: str, tool_class: str, reason: str
    ) -> Payload:
        return {
            "rollback_id": f"fixture-{kind}-rollback-{tool_class}",
            "transaction_id": transaction.get("transaction_id"),
            "restored": True,
            "reason": reason,
        }

    def surface_snapshot(self) -> dict[str, bytes | None]:
        paths = [self.controller_path, *self.paths]
        return {
            str(path.resolve(strict=False)): path.read_bytes() if path.exists() else None
            for path in paths
        }

    def list_effective_files(self, tool_class: str) -> list[Path]:
        self._record(tool_class, "list_effective_files")
        return list(self.paths)

    def probe_controller(self, tool_class: str) -> Payload:
        self._record(tool_class, "probe_controller")
        certainty = {kind: kind != self.uncertainty for kind in UNCERTAINTY_KINDS}
        compatible, compatibility_reason = self._controller_compatibility()
        if self.has_controller and not compatible:
            certainty["compatibility"] = False
        uncertainty = [self.uncertainty] if self.uncertainty else []
        if self.has_controller and not compatible:
            uncertainty.append(compatibility_reason)
        explanation = (
            "fixture uncertainty: " + ", ".join(uncertainty) + " is not proven"
            if uncertainty
            else "all controller/config semantics proven by fixture adapter"
        )
        return {
            "present": self.has_controller,
            "kind": "synthetic-json-controller-fixture"
            if self.has_controller
            else "none",
            "storage_kind": "json_fixture" if self.has_controller else "none",
            "synthetic": True,
            "db_path": None,
            "fixture_path": self.controller_path
            if self.has_controller
            else None,
            "tool_class": tool_class,
            "controller_version": self.controller_version
            if self.has_controller
            else None,
            "app_version": self.controller_version if self.has_controller else None,
            "user_version": self.controller_user_version
            if self.has_controller
            else None,
            "schema_evidence": self._controller_schema_evidence(),
            "current_profile_setting_required": False,
            "database_migration_allowed": False,
            "compatibility": {
                "supported": compatible if self.has_controller else None,
                "reason": compatibility_reason if self.has_controller else "not_present",
            },
            "tool_block_proven": bool(
                self.has_controller
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
    ) -> Payload:
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

    def runtime_probe(self, tool_class: str) -> Payload:
        self._record(tool_class, "runtime_probe")
        gaps = self.expected_gaps()
        return {
            "available": True,
            "tool_class": tool_class,
            "standard_requirements_met": not gaps,
            "evidence": f"fixture://runtime/{tool_class}",
        }

    def backup_controller_database(self, tool_class: str) -> Payload:
        self._require_tool(tool_class)
        if not self.has_controller or not self.controller_path.is_file():
            raise AssertionError("controller backup requested without controller")
        self._record(tool_class, "backup_controller_database", mutation=True)
        backup = self.root / "backups" / "cc-switch.db.before"
        payload, receipt = self._backup(self.controller_path, backup)
        self._controller_original = payload
        self._controller_effective_originals = {
            path: path.read_bytes() for path in self.paths
        }
        return {"path": backup, **receipt}

    def begin_controller_transaction(self, tool_class: str) -> Payload:
        self._record(tool_class, "begin_controller_transaction", mutation=True)
        return {"transaction_id": f"fixture-controller-{tool_class}"}

    def update_controller_tool_block(
        self,
        transaction: Payload,
        tool_class: str,
        semantic_delta: Payload,
    ) -> Payload:
        self._require_tool(tool_class)
        delta = self._require_delta(semantic_delta)
        if transaction.get("transaction_id") != f"fixture-controller-{tool_class}":
            raise AssertionError("wrong controller transaction")
        self._record(tool_class, "update_controller_tool_block", mutation=True)
        self.controller_deltas.append(delta)
        database = json.loads(
            self.controller_path.read_text(encoding="utf-8")
        )
        block = database["fixture_tool_blocks"][tool_class]
        block["semantic_delta"] = delta
        self.controller_path.write_text(
            json.dumps(database, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if self.controller_materializes:
            for path in self.paths:
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
        transaction: Payload,
        tool_class: str,
    ) -> Payload:
        self._record(tool_class, "commit_controller_transaction", mutation=True)
        return {
            **self._commit_receipt(transaction, "controller", tool_class),
            "controller_store_sha256": _sha256_bytes(self.controller_path.read_bytes()),
        }

    def rollback_controller_transaction(
        self,
        transaction: Payload,
        tool_class: str,
        reason: str,
    ) -> Payload:
        self._record(tool_class, "rollback_controller_transaction", mutation=True)
        if self._controller_original is None:
            raise AssertionError("controller rollback missing verified backup")
        self.controller_path.write_bytes(self._controller_original)
        for path, payload in self._controller_effective_originals.items():
            path.write_bytes(payload)
        return self._rollback_receipt(transaction, "controller", tool_class, reason)

    def backup_effective_file(
        self,
        tool_class: str,
        path: Path,
    ) -> Payload:
        self._require_tool(tool_class)
        resolved = self._require_path(path)
        self.events.append(f"backup_effective_file:{tool_class}:{resolved.name}")
        self.mutation_events.append(
            f"backup_effective_file:{tool_class}:{resolved.name}"
        )
        self._maybe_fail_direct_step("backup_effective_file")
        backup = self.root / "backups" / f"{resolved.name}.before"
        payload, receipt = self._backup(resolved, backup)
        self._backups[resolved] = backup
        return {"path": resolved, "backup_path": backup, **receipt}

    def begin_effective_files_transaction(
        self,
        tool_class: str,
        paths: list[Path],
    ) -> Payload:
        self._require_tool(tool_class)
        resolved = [self._require_path(path) for path in paths]
        if resolved != [path.resolve(strict=False) for path in self.paths]:
            raise AssertionError("effective transaction did not bind all actual files")
        self._record(tool_class, "begin_effective_files_transaction", mutation=True)
        self._maybe_fail_direct_step("begin_effective_files_transaction")
        self._direct_originals = {path: path.read_bytes() for path in resolved}
        return {"transaction_id": f"fixture-effective-{tool_class}"}

    def write_effective_config(
        self,
        transaction: Payload,
        tool_class: str,
        path: Path,
        semantic_delta: Payload,
    ) -> Payload:
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
        transaction: Payload,
        tool_class: str,
    ) -> Payload:
        self._record(tool_class, "commit_effective_files_transaction", mutation=True)
        self._maybe_fail_direct_step("commit_effective_files_transaction")
        return self._commit_receipt(transaction, "effective", tool_class)

    def rollback_effective_files_transaction(
        self,
        transaction: Payload,
        tool_class: str,
        reason: str,
    ) -> Payload:
        self._record(tool_class, "rollback_effective_files_transaction", mutation=True)
        if not self._direct_originals:
            raise AssertionError("effective rollback missing transaction snapshot")
        for path, payload in self._direct_originals.items():
            path.write_bytes(payload)
        return self._rollback_receipt(transaction, "effective", tool_class, reason)

    def expected_gaps(self) -> list[str]:
        gaps: list[str] = []
        for path in self.paths:
            gaps.extend(
                _delta_gaps(path, _parse_fixture_config(path), self.expected_delta)
            )
        return gaps

    def expected_evidence(self) -> list[str]:
        return [
            f"fixture://effective/{self.tool_class}/{path.name}"
            for path in self.paths
        ]

    def non_delta_projection(self) -> dict[str, Payload]:
        return {
            path.name: _without_delta_fields(
                _parse_fixture_config(path), self.expected_delta
            )
            for path in self.paths
        }


def _normalize_targets(result: Payload) -> list[Path]:
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
    install: Installer,
    *,
    source_root: Path,
    home_root: Path,
    current_tool: str,
    explicit_tools: list[str],
    tool_roots: dict[str, Path],
    projection_manifest: Path,
    write: bool,
    fanout: bool = False,
    blank_host_configuration: Payload | None = None,
    configuration_adapter: object | None = None,
    install_transaction_adapter: object | None = None,
    platform_context: Payload | None = None,
    source_package_sha256: object | None = None,
    installation_binding: Payload | None = None,
) -> tuple[Payload | None, str | None]:
    optional: Payload = {}
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
    if installation_binding is not None:
        optional["installation_binding"] = installation_binding
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
    install: Installer,
    *,
    name: str,
    expected_targets: list[Path],
    errors: list[str],
    **kwargs: Any,
) -> Payload | None:
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
    install: Installer,
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
    for relative in PROTECTED_SEEDS:
        path = target_root / Path(relative)
        if path.exists() or path.is_symlink():
            errors.append(f"{name}:protected_shiguan_path_installed:{relative}")


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


def _tx_kwargs(fixture: tuple[object, ...], adapter: object) -> Payload:
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


def _four_root_fixture(
    temp_root: Path,
    label: str,
) -> tuple[object, ...]:
    source, home, manifest, roots = _case_fixture(temp_root, label)
    roots = {
        "codex": home / ".codex" / "skills" / "decretum-matrix",
        "claude": home / ".claude" / "skills" / "decretum-matrix",
        "hermes": home / "localappdata" / "hermes" / "skills" / "decretum-matrix",
    }
    targets = [_agents_root(home), *roots.values()]
    old = [_legacy_root(root) for root in targets]
    for index, root in enumerate(old):
        _write_files(
            root,
            {
                "SKILL.md": "# legacy projected skill\n",
                "VERSION": "beta0.5.10\n",
                "scripts/portable-helper.py": "VALUE = 'legacy'\n",
                "data-only.txt": f"legacy-data-{index}\n",
            },
        )
    return source, home, manifest, roots, targets, old


def _four_root_kwargs(fixture: tuple[object, ...], adapter: object) -> Payload:
    source, home, manifest, roots = fixture[:4]
    return {
        "source_root": source,
        "home_root": home,
        "current_tool": "codex",
        "explicit_tools": ["claude", "hermes"],
        "tool_roots": roots,
        "projection_manifest": manifest,
        "write": True,
        "install_transaction_adapter": adapter,
    }


def _case_hermes_alias_commit_failure_restores_legacy_junction(
    install: Installer,
    temp_root: Path,
) -> str | None:
    name = "hermes_alias_commit_failure_restores_legacy_junction"
    fixture = _four_root_fixture(temp_root, name)
    _, home, _, _, targets, old = fixture
    legacy_alias = home / ".hermes" / "skills" / LEGACY_INSTALL_DIRECTORY_NAME
    canonical_alias = home / ".hermes" / "skills" / "decretum-matrix"
    adapter = _AliasFailureAdapter(legacy_alias, canonical_alias, old[-1])
    before = _snapshots(old)
    result, rejection = _invoke(install, **_four_root_kwargs(fixture, adapter))
    if result is not None and result.get("ok") is True:
        return f"{name}:unexpected_success"
    prepared_alias = canonical_alias.with_name(f".{canonical_alias.name}.alias-prepared")
    leftovers, _ = _tx_state(targets, old)
    checks = (
        "install_transaction_failed" in (rejection or _result_reason(result)),
        _snapshots(old) == before,
        not any(root.exists() or root.is_symlink() for root in targets),
        adapter.aliases == adapter.initial and not adapter.prepared,
        str(canonical_alias) not in adapter.aliases,
        not canonical_alias.exists() and not prepared_alias.exists(),
        not leftovers,
        (
            all(step in adapter.events for step in ("alias_prepare", "alias_commit", "alias_rollback"))
            and [adapter.events.index(step) for step in ("alias_prepare", "alias_commit", "alias_rollback")]
            == sorted(adapter.events.index(step) for step in ("alias_prepare", "alias_commit", "alias_rollback"))
            and adapter.events[-1] == "alias_rollback"
        ),
    )
    return None if all(checks) else f"{name}:alias_failure_rollback_incomplete"


def _check_tx_cases(
    install: Installer,
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
    source, home, _, _, targets, old, _, sentinel, marker = fixture
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
            if legacy:
                backup = result.get("backup")
                backup_root = (
                    Path(str(backup.get("backup_root")))
                    if isinstance(backup, dict) and backup.get("backup_root")
                    else None
                )
                rollback = (
                    install.__globals__["rollback_install_backup"](
                        home_root=home,
                        backup_root=backup_root,
                    )
                    if backup_root is not None
                    else None
                )
                rollback_checks = (
                    isinstance(backup, dict)
                    and backup.get("rollback_supported") is True,
                    isinstance(rollback, dict)
                    and rollback.get("ok") is True
                    and rollback.get("legacy_locator_restored_count") == 2,
                    not any(root.exists() or root.is_symlink() for root in targets),
                    all(root.is_dir() and not root.is_symlink() for root in old),
                    all(
                        (root / "VERSION").read_text(encoding="utf-8")
                        == "beta0.5.10\n"
                        and (root / sentinel).read_text(encoding="utf-8")
                        == f"{marker}-{index}\n"
                        for index, root in enumerate(old)
                    ),
                )
                if not all(rollback_checks):
                    errors.append(
                        f"{name}:explicit_legacy_rollback_failed:{rollback}"
                    )
                else:
                    passed += 1

    if legacy:
        exact_name = "exact_version_legacy_locator_still_backs_up_and_rolls_back"
        exact_fixture = _tx_fixture(temp_root, exact_name, True)
        exact_source, exact_home, _, _, exact_targets, exact_old = exact_fixture[:6]
        for root in exact_old:
            for relative in PORTABLE_FILES:
                source_path = exact_source / Path(relative)
                target_path = root / Path(relative)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
        exact_result = _require_success(
            install,
            name=exact_name,
            expected_targets=exact_targets,
            errors=errors,
            **_tx_kwargs(exact_fixture, _MigrationFailureAdapter()),
        )
        exact_backup = exact_result.get("backup") if exact_result else None
        exact_backup_root = (
            Path(str(exact_backup.get("backup_root")))
            if isinstance(exact_backup, dict) and exact_backup.get("backup_root")
            else None
        )
        exact_rollback = (
            install.__globals__["rollback_install_backup"](
                home_root=exact_home,
                backup_root=exact_backup_root,
            )
            if exact_backup_root is not None
            else None
        )
        rendered_metadata_replacements = len(exact_targets) * 3
        if (
            not isinstance(exact_result, dict)
            or exact_result.get("projection_counts", {}).get("create") != 0
            or exact_result.get("projection_counts", {}).get("replace")
            != rendered_metadata_replacements
            or exact_result.get("projection_counts", {}).get("delete") != 0
            or not isinstance(exact_backup, dict)
            or exact_backup.get("status") != "CREATED"
            or exact_backup.get("operation_count") != rendered_metadata_replacements
            or exact_backup.get("replace_count") != rendered_metadata_replacements
            or exact_backup.get("delete_count") != 0
            or not isinstance(exact_rollback, dict)
            or exact_rollback.get("ok") is not True
            or exact_rollback.get("legacy_locator_restored_count") != 2
            or any(root.exists() or root.is_symlink() for root in exact_targets)
            or not all(root.is_dir() for root in exact_old)
        ):
            errors.append(
                f"{exact_name}:contract_failed:{exact_result}:{exact_rollback}"
            )
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
        before = _snapshots(seeded)
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
                    _snapshots(seeded) == before
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


def _check_npm_postinstall_fixture(temp_root: Path, errors: list[str]) -> int:
    name = "npm_postinstall_is_explicitly_disabled_without_mutation"
    launcher_path = ROOT / "bin" / "decretum-matrix.py"
    spec = importlib.util.spec_from_file_location(
        "decretum_matrix_npm_postinstall_fixture", launcher_path
    )
    if spec is None or spec.loader is None:
        errors.append(f"{name}:launcher_spec_unavailable")
        return 0
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        errors.append(f"{name}:launcher_import_failed:{type(exc).__name__}:{exc}")
        return 0
    home = temp_root / _fixture_slug(name) / "home"
    local = home / "AppData" / "Local"
    roaming = home / "AppData" / "Roaming"
    for path in (home, local, roaming):
        path.mkdir(parents=True, exist_ok=True)
    keys = (
        "APPDATA",
        "CODEX_HOME",
        "COURT_TOOL_INSTALL_DIR",
        "DECRETUM_MATRIX_POSTINSTALL_ACTIVATE_SERVICES",
        "DECRETUM_MATRIX_SKIP_SUPERCC_DEPS",
        "HOME",
        "LOCALAPPDATA",
        "PYTHONDONTWRITEBYTECODE",
        "USERPROFILE",
    )
    saved = {key: os.environ.get(key) for key in keys}
    try:
        os.environ.update(
            {
                "APPDATA": str(roaming),
                "CODEX_HOME": str(home / ".codex"),
                "COURT_TOOL_INSTALL_DIR": str(home / ".tools"),
                "DECRETUM_MATRIX_POSTINSTALL_ACTIVATE_SERVICES": "0",
                "DECRETUM_MATRIX_SKIP_SUPERCC_DEPS": "1",
                "HOME": str(home),
                "LOCALAPPDATA": str(local),
                "PYTHONDONTWRITEBYTECODE": "1",
                "USERPROFILE": str(home),
            }
        )
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                module.main(["--npm-postinstall"])
            except Exception as exc:
                if type(exc).__name__ != "LauncherError" or str(exc) != "npm_postinstall_disabled":
                    errors.append(
                        f"{name}:wrong_rejection:{type(exc).__name__}:{exc}"
                    )
            else:
                errors.append(f"{name}:postinstall_was_accepted")
    except Exception as exc:
        errors.append(f"{name}:execution_failed:{type(exc).__name__}:{exc}")
        return 0
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    canonical = home / ".agents" / "skills" / "decretum-matrix"
    references = home / ".agents" / "court-shiguan" / "decretum-matrix"
    tool_dir = home / ".tools"
    receipt_dir = home / ".agents" / "install-receipts"
    if any(path.exists() or path.is_symlink() for path in (canonical, references, tool_dir, receipt_dir)):
        errors.append(f"{name}:postinstall_mutated_host")
        return 0
    return 1


def _check_candidate_binding_provenance_cases(
    temp_root: Path,
    errors: list[str],
) -> int:
    """Require a clean, candidate-backed source before producing binding metadata."""

    name = "candidate_binding_provenance_contract"
    try:
        from commands import fix_decretum_matrix as fix
    except Exception as exc:
        errors.append(f"{name}:import:{type(exc).__name__}:{exc}")
        return 0

    root = temp_root / _fixture_slug(name)
    source = root / "source"
    package_root = root / "npm-prefix" / "node_modules" / "@rowlandl" / "decretum-matrix"
    release_root = package_root / "release"
    source.mkdir(parents=True, exist_ok=True)
    release_root.mkdir(parents=True, exist_ok=True)
    release_label = "beta1.1.2"
    artifact_name = f"decretum-matrix-{release_label}.zip"
    receipt_name = f"decretum-matrix-{release_label}.candidate-receipt.json"
    _write_files(
        source,
        {
            "VERSION": f"{release_label}\n",
            "SKILL.md": "# candidate source\n",
            "release-manifest.json": json.dumps(
                {
                    "schema": "court.release_manifest.v2",
                    "release_label": release_label,
                    "version_core": "1.1.2",
                    "channel": "beta",
                    "artifact_name": artifact_name,
                    "expected_final_tag": f"refs/tags/{release_label}",
                },
                sort_keys=True,
            )
            + "\n",
        },
    )
    source_git_environment = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
    }

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=source,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=source_git_environment,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)}:{result.stderr.strip()}")
        return result.stdout.strip()

    try:
        git("init", "-q")
        git("config", "user.name", "Decretum Candidate Fixture")
        git("config", "user.email", "candidate@example.invalid")
        git("add", ".")
        git("commit", "-q", "-m", "candidate source")
        source_commit = git("rev-parse", "HEAD")
        source_tree = git("rev-parse", "HEAD^{tree}")
        (source / "SKILL.md").write_text("# dirty candidate source\n", encoding="utf-8")
    except Exception as exc:
        errors.append(f"{name}:git_fixture:{type(exc).__name__}:{exc}")
        return 0

    def package_json(
        *,
        package_release_label: str = release_label,
        artifact_ref: str | None = None,
    ) -> Payload:
        resolved_artifact_ref = artifact_ref or f"release/{artifact_name}@{source_commit}"
        build_id = f"{package_release_label}:{source_commit}:{source_tree}"
        return {
            "name": "@rowlandl/decretum-matrix",
            "version": "1.1.2-beta.0.local",
            "bin": {"decretum-matrix": "bin/decretum-matrix.js"},
            "decretumMatrix": {
                "schema": "decretum.npm_local_install_candidate.v1",
                "candidate": "local-install",
                "payloadKind": "runtime",
                "private": True,
                "publication": "FORBIDDEN",
                "releaseLabel": package_release_label,
                "artifactRef": resolved_artifact_ref,
                "buildId": build_id,
                "candidateReceipt": f"release/{receipt_name}",
                "source": {
                    "commit": source_commit,
                    "tree": source_tree,
                    "tag": None,
                    "tagRef": None,
                },
                "installationBinding": {
                    "schema": "court.installation_binding.v2",
                    "source_commit": source_commit,
                    "release_label": package_release_label,
                    "artifact_ref": resolved_artifact_ref,
                    "build_id": build_id,
                },
                "cli": {
                    "entrypoint": "bin/decretum-matrix.js",
                    "pythonBootstrap": "bin/decretum-matrix.py",
                    "installLifecycleScripts": False,
                    "postinstallContract": "disabled_explicit_installer_required",
                },
            },
        }

    (package_root / "bin").mkdir(parents=True, exist_ok=True)
    (package_root / "bin" / "decretum-matrix.js").write_text(
        "#!/usr/bin/env node\n", encoding="utf-8"
    )
    (package_root / "bin" / "decretum-matrix.py").write_text(
        "print('candidate')\n", encoding="utf-8"
    )
    with zipfile.ZipFile(release_root / artifact_name, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            "decretum-matrix/release-manifest.json",
            json.dumps(
                {"files": [{"path": "bin/decretum-matrix.py"}]},
                sort_keys=True,
            ),
        )
        archive.writestr("decretum-matrix/bin/decretum-matrix.py", "print('candidate')\n")
    candidate_receipt = {
        "schema": "court.release_candidate_receipt.v1",
        "state": "CANDIDATE_NOT_RELEASED",
        "name": "decretum-matrix",
        "package_name": "decretum-matrix",
        "release_label": release_label,
        "candidate_id": source_commit,
        "source": {
            "kind": "commit",
            "head_commit": source_commit,
            "tree": source_tree,
            "worktree_clean": True,
            "expected_tag_ref": f"refs/tags/{release_label}",
            "tag_ref": None,
            "tag_object": None,
            "tag_commit": None,
            "tag_signature": "NOT_APPLICABLE",
        },
        "release_manifest": {
            "path": "release-manifest.json",
            "expected_final_tag": f"refs/tags/{release_label}",
        },
        "artifacts": [{"name": artifact_name}],
    }
    candidate_receipt_path = release_root / receipt_name
    candidate_receipt_path.write_text(
        json.dumps(candidate_receipt, sort_keys=True) + "\n", encoding="utf-8"
    )

    def call_metadata() -> str:
        try:
            value = fix._installation_binding_metadata(
                source,
                candidate_package_root=package_root,
                candidate_receipt=candidate_receipt_path,
                transaction_id="transaction-a",
                installation_id="installation-a",
            )
        except Exception as exc:
            return f"{type(exc).__name__}:{exc}"
        return f"accepted:{value!r}"

    passed = 0
    dirty_result = call_metadata()
    if "candidate_source_tracked_worktree_dirty" in dirty_result:
        passed += 1
    else:
        errors.append(f"{name}:dirty_source:{dirty_result}")

    git("checkout", "--", "SKILL.md")
    valid_package = package_json()
    (package_root / "package.json").write_text(
        json.dumps(valid_package, sort_keys=True) + "\n", encoding="utf-8"
    )
    (source / "preserved-untracked.md").write_text("preserve\n", encoding="utf-8")
    untracked_result = call_metadata()
    if untracked_result.startswith("accepted:"):
        passed += 1
    else:
        errors.append(f"{name}:preserved_untracked:{untracked_result}")
    (source / "preserved-untracked.md").unlink()

    mismatched_version = package_json(package_release_label="beta9.9.9")
    (package_root / "package.json").write_text(
        json.dumps(mismatched_version, sort_keys=True) + "\n", encoding="utf-8"
    )
    version_result = call_metadata()
    if "candidate_release_label_mismatch" in version_result:
        passed += 1
    else:
        errors.append(f"{name}:candidate_version:{version_result}")

    mismatched_artifact = package_json(artifact_ref=f"release/wrong.zip@{source_commit}")
    (package_root / "package.json").write_text(
        json.dumps(mismatched_artifact, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifact_result = call_metadata()
    if "candidate_artifact_ref_mismatch" in artifact_result:
        passed += 1
    else:
        errors.append(f"{name}:candidate_artifact:{artifact_result}")

    valid_package = package_json()
    (package_root / "package.json").write_text(
        json.dumps(valid_package, sort_keys=True) + "\n", encoding="utf-8"
    )
    with zipfile.ZipFile(release_root / artifact_name, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            "decretum-matrix/release-manifest.json",
            json.dumps(
                {"files": [{"path": "scripts/checks/forbidden.py"}]},
                sort_keys=True,
            ),
        )
        archive.writestr("decretum-matrix/scripts/checks/forbidden.py", "print('source-only')\n")
    payload_result = call_metadata()
    if "candidate_payload_checker_entries" in payload_result:
        passed += 1
    else:
        errors.append(f"{name}:candidate_payload_checker:{payload_result}")
    return passed


def _check_fix_role_failure_compensation(
    temp_root: Path,
    errors: list[str],
) -> int:
    """A role write failure must compensate the preceding skill projection."""

    name = "fix_role_failure_compensates_projection"
    try:
        from commands import fix_decretum_matrix as fix
    except Exception as exc:
        errors.append(f"{name}:import:{type(exc).__name__}:{exc}")
        return 0
    source, home, manifest, roots = _case_fixture(temp_root, name)
    _prime_roots(home, roots)
    targets = [_agents_root(home), roots["codex"]]
    before = _snapshots(targets)
    role_path = home / ".codex" / "agents" / "gongbu.toml"
    role_path.parent.mkdir(parents=True, exist_ok=True)
    role_preimage = "name = 'preimage'\n"
    role_path.write_text(role_preimage, encoding="utf-8")

    def failing_role_sync(*_args: object, **_kwargs: object) -> Payload:
        role_path.write_text("name = 'partial-role-write'\n", encoding="utf-8")
        return {"ok": False, "status": "FAIL", "error": "role fixture"}

    metadata: Payload = {
        "source_commit": "commit-a",
        "source_tree": "tree-a",
        "release_label": "beta1.0.1",
        "artifact_ref": "candidate/beta1.0.1/commit-a.zip",
        "build_id": "beta1.0.1:commit-a:tree-a",
        "installation_id": "installation-a",
        "transaction_id": "transaction-a",
        "provenance_receipt_ref": "candidate-receipt-a",
        "candidate_package_root": str(temp_root),
        "candidate_receipt_ref": "candidate-receipt-a",
    }
    try:
        with mock.patch.object(
            fix,
            "_installation_binding_metadata",
            side_effect=lambda *_args, **_kwargs: dict(metadata),
        ), mock.patch.object(
            fix,
            "_sync_codex_agent_roles",
            side_effect=failing_role_sync,
        ):
            result = fix._install_update(
                {"selected_root": str(source)},
                home,
                write=True,
                candidate_package_root=temp_root,
                transaction_id="transaction-a",
                installation_id="installation-a",
                caller_cwd=temp_root,
            )
    except Exception as exc:
        errors.append(f"{name}:unexpected:{type(exc).__name__}:{exc}")
        return 0
    compensation = result.get("compensation") if isinstance(result, dict) else None
    binding_path = (
        home
        / ".agents"
        / "install-receipts"
        / "decretum-matrix"
        / "installation-binding-v2.json"
    )
    binding_state_ok = True
    if binding_path.is_file():
        try:
            binding_state_ok = (
                json.loads(binding_path.read_text(encoding="utf-8")).get("completion")
                == "PENDING_VALIDATION"
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            binding_state_ok = False
    checks = (
        isinstance(result, dict)
        and result.get("ok") is False
        and result.get("status") == "ROLLED_BACK"
        and result.get("reason") == "codex_agent_roles_sync_failed"
        and isinstance(compensation, dict)
        and compensation.get("ok") is True
        and _snapshots(targets) == before
        and role_path.read_text(encoding="utf-8") == role_preimage
        and binding_state_ok
    )
    if not checks:
        errors.append(f"{name}:contract_failed:{result}")
        return 0
    return 1


def _check_one_shot_post_projection_acceptance(
    temp_root: Path,
    errors: list[str],
) -> int:
    """The explicit update path must persist one producer receipt before commit."""

    name = "one_shot_post_projection_acceptance"
    try:
        from commands import fix_decretum_matrix as fix
        from install_current_agent_copy import INSTALLATION_ACCEPTANCE_SCHEMA
        from install_current_agent_copy import INSTALLATION_BINDING_SCHEMA
        import install_current_agent_copy as installer
    except Exception as exc:
        errors.append(f"{name}:import:{type(exc).__name__}:{exc}")
        return 0
    root = temp_root / _fixture_slug(name)
    source = root / "source"
    home = root / "home"
    source.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    counter = root / "checker-count.txt"
    producer = {
        "schema": "court.active_copy_hashes.v2",
        "ok": True,
        "status": "PASS",
        "contract": "POST_INSTALL_STANDALONE_HASH_CHECK",
        "source": str(source),
        "source_version": "beta1.1.2",
        "projection": "shared_agents",
        "root_contract": "RECEIPT_SELECTED_ROOTS",
        "roots": [
            str((home / ".agents" / "skills" / "decretum-matrix").resolve()),
            str((home / ".codex" / "skills" / "decretum-matrix").resolve()),
        ],
        "physical_authorities": [],
        "physical_authority_count": 0,
        "checked_files": 1,
        "missing_roots": [],
        "drift": [],
        "extra_files": [],
        "unsafe_paths": [],
        "forbidden_checker_copies": [],
        "codex_agent_roles": {"required": False, "ok": True, "status": "NOT_APPLICABLE"},
        "root_evidence": [],
        "pending_body_access": "NO",
        "projection_sha256": "external-projection",
        "receipt_sha256": "external-receipt",
    }
    checker = source / "scripts" / "checks" / "check_active_copy_hashes.py"
    checker.parent.mkdir(parents=True, exist_ok=True)
    checker.write_text(
        "import json, os, pathlib\n"
        "counter = pathlib.Path(os.environ['GONGbu_CHECKER_COUNTER'])\n"
        "counter.write_text(str(int(counter.read_text() or '0') + 1), encoding='utf-8')\n"
        f"print(json.dumps({producer!r}))\n",
        encoding="utf-8",
    )
    binding = {
        "schema": INSTALLATION_BINDING_SCHEMA,
        "source_commit": "commit-a",
        "release_label": "beta1.1.2",
        "artifact_ref": "release/decretum-matrix-beta1.1.2.zip@commit-a",
        "build_id": "beta1.1.2:commit-a:tree-a",
        "installation_id": "installation-a",
        "generation": 1,
        "canonical_root": str((home / ".agents" / "skills" / "decretum-matrix").resolve()),
        "selected_roots": producer["roots"],
        "completion": "PENDING_VALIDATION",
        "provenance_receipt_ref": "candidate:receipt@commit-a",
        "transaction_id": "transaction-a",
        "rollback_ref": "rollback-a",
    }
    candidate = {
        "source_commit": "commit-a",
        "source_tree": "tree-a",
        "release_label": "beta1.1.2",
        "artifact_ref": binding["artifact_ref"],
        "build_id": binding["build_id"],
        "candidate_receipt_ref": binding["provenance_receipt_ref"],
    }
    binding_path = home / ".agents" / "install-receipts" / "decretum-matrix" / "installation-binding-v2.json"
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    binding_path.write_text(json.dumps(binding, sort_keys=True) + "\n", encoding="utf-8")
    counter.write_text("0", encoding="utf-8")
    prior_environment = os.environ.get("GONGbu_CHECKER_COUNTER")
    os.environ["GONGbu_CHECKER_COUNTER"] = str(counter)
    try:
        with mock.patch.object(
            fix,
            "_acceptance_environment",
            side_effect=lambda _home: {
                **os.environ,
                "PYTHONPATH": "",
                "GONGbu_CHECKER_COUNTER": str(counter),
            },
        ):
            result = fix._run_post_projection_acceptance(
                source=source,
                home=home,
                binding=binding,
                candidate=candidate,
                installer_module=installer,
            )
    except Exception as exc:
        errors.append(f"{name}:unexpected:{type(exc).__name__}:{exc}")
        return 0
    finally:
        if prior_environment is None:
            os.environ.pop("GONGbu_CHECKER_COUNTER", None)
        else:
            os.environ["GONGbu_CHECKER_COUNTER"] = prior_environment
    receipt_path = home / ".agents" / "install-receipts" / "decretum-matrix" / "post-validation-transaction-a.json"
    try:
        persisted = json.loads(binding_path.read_text(encoding="utf-8"))
        persisted_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        count = counter.read_text(encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{name}:evidence_unreadable:{type(exc).__name__}:{exc}:result={result}")
        return 0
    checks = (
        result.get("ok") is True
        and result.get("status") == "COMMITTED"
        and count == "1"
        and persisted.get("completion") == "COMMITTED"
        and persisted.get("provenance_receipt_ref") == "candidate:receipt@commit-a"
        and persisted_receipt.get("schema") == INSTALLATION_ACCEPTANCE_SCHEMA
        and persisted_receipt.get("binding", {}).get("transaction_id") == "transaction-a"
        and result.get("commit_result", {}).get("post_projection_receipt_ref") == str(receipt_path)
    )
    if not checks:
        errors.append(f"{name}:contract_failed:{result}:{persisted}:{persisted_receipt}:{count}")
        return 0
    return 1


def _check_candidate_npm_failure_compensation(
    temp_root: Path,
    errors: list[str],
) -> int:
    """A failed candidate preflight removes an npm carrier installed by this transaction."""

    name = "candidate_npm_failure_compensation"
    try:
        from commands import fix_decretum_matrix as fix
    except Exception as exc:
        errors.append(f"{name}:import:{type(exc).__name__}:{exc}")
        return 0
    caller = temp_root / "caller"
    prefix = temp_root / "npm-prefix"
    home = temp_root / "home"
    tgz = temp_root / "candidate.tgz"
    caller.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    tgz.write_bytes(b"candidate")
    rollback_calls: list[tuple[Path, Path]] = []

    def fake_install(**_kwargs: object) -> Payload:
        return {
            "ok": True,
            "status": "INSTALLED",
            "package_root": str(prefix / "node_modules" / "@rowlandl" / "decretum-matrix"),
        }

    def fake_rollback(**kwargs: object) -> Payload:
        rollback_calls.append((Path(str(kwargs["npm_prefix"])), Path(str(kwargs["caller_cwd"]))))
        return {"ok": True, "status": "ROLLED_BACK", "removed": True}

    try:
        with mock.patch.object(fix, "_install_candidate_npm", side_effect=fake_install), mock.patch.object(
            fix,
            "_rollback_candidate_npm",
            side_effect=fake_rollback,
        ), mock.patch.object(
            fix,
            "_installation_binding_metadata",
            side_effect=RuntimeError("candidate_payload_checker_entries:fixture"),
        ):
            result = fix._install_update(
                {"selected_root": str(temp_root)},
                home,
                write=True,
                candidate_tgz=tgz,
                npm_prefix=prefix,
                transaction_id="transaction-a",
                installation_id="installation-a",
                caller_cwd=caller,
            )
    except Exception as exc:
        errors.append(f"{name}:unexpected:{type(exc).__name__}:{exc}")
        return 0
    if not (
        result.get("ok") is False
        and result.get("reason") == "candidate_payload_checker_entries:fixture"
        and result.get("npm_candidate_compensation", {}).get("ok") is True
        and rollback_calls == [(prefix, caller)]
    ):
        errors.append(f"{name}:contract_failed:{result}:rollback_calls={rollback_calls!r}")
        return 0
    return 1


def _check_candidate_npm_partial_failure_compensation(
    temp_root: Path,
    errors: list[str],
) -> int:
    """A nonzero npm attempt must compensate before any success flag exists."""

    name = "candidate_npm_partial_failure_compensation"
    try:
        from commands import fix_decretum_matrix as fix
    except Exception as exc:
        errors.append(f"{name}:import:{type(exc).__name__}:{exc}")
        return 0
    caller = temp_root / "caller"
    prefix = temp_root / "npm-prefix"
    home = temp_root / "home"
    tgz = temp_root / "candidate.tgz"
    package_root = prefix / "node_modules" / "@rowlandl" / "decretum-matrix"
    caller.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    tgz.write_bytes(b"candidate")
    rollback_calls: list[tuple[Path, Path]] = []

    def fake_install(**_kwargs: object) -> Payload:
        package_root.mkdir(parents=True, exist_ok=True)
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": "npm_candidate_install_failed",
            "mutation_attempted": True,
            "residual_targets": [str(package_root)],
        }

    def fake_rollback(**kwargs: object) -> Payload:
        rollback_calls.append((Path(str(kwargs["npm_prefix"])), Path(str(kwargs["caller_cwd"]))))
        return {"ok": True, "status": "ROLLED_BACK", "removed": True}

    try:
        with mock.patch.object(fix, "_install_candidate_npm", side_effect=fake_install), mock.patch.object(
            fix,
            "_rollback_candidate_npm",
            side_effect=fake_rollback,
        ):
            result = fix._install_update(
                {"selected_root": str(temp_root)},
                home,
                write=True,
                candidate_tgz=tgz,
                npm_prefix=prefix,
                transaction_id="transaction-partial",
                installation_id="installation-partial",
                caller_cwd=caller,
            )
    except Exception as exc:
        errors.append(f"{name}:unexpected:{type(exc).__name__}:{exc}")
        return 0
    if not (
        result.get("ok") is False
        and result.get("status") == "ROLLED_BACK"
        and result.get("reason") == "npm_candidate_install_failed"
        and result.get("npm_candidate_install", {}).get("mutation_attempted") is True
        and result.get("npm_candidate_compensation", {}).get("ok") is True
        and rollback_calls == [(prefix, caller)]
    ):
        errors.append(f"{name}:contract_failed:{result}:rollback_calls={rollback_calls!r}")
        return 0
    sentinel = prefix / "node_modules" / "unrelated" / "x"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("x", encoding="utf-8")

    def npm_prune(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        shutil.rmtree(prefix / "node_modules")
        return subprocess.CompletedProcess(args=[], returncode=0)

    with mock.patch.object(fix.subprocess, "run", side_effect=npm_prune):
        scoped = fix._rollback_candidate_npm(
            npm_prefix=prefix,
            home=home,
            caller_cwd=caller,
        )
    if not (
        scoped.get("ok") is True
        and sentinel.is_file()
        and sentinel.read_text(encoding="utf-8") == "x"
    ):
        errors.append(f"{name}:rollback_scope_failed")
        return 0
    return 1


def _check_candidate_npm_partial_attempt_metadata(
    temp_root: Path,
    errors: list[str],
) -> int:
    """The real npm producer must report the owned residue of a failed run."""

    name = "candidate_npm_partial_attempt_metadata"
    try:
        from commands import fix_decretum_matrix as fix
    except Exception as exc:
        errors.append(f"{name}:import:{type(exc).__name__}:{exc}")
        return 0
    caller = temp_root / "caller"
    prefix = temp_root / "npm-prefix"
    home = temp_root / "home"
    tgz = temp_root / "candidate.tgz"
    package_root = prefix / "node_modules" / "@rowlandl" / "decretum-matrix"
    caller.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    tgz.write_bytes(b"candidate")

    def partial_npm(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        package_root.mkdir(parents=True, exist_ok=True)
        return subprocess.CompletedProcess(
            args=["npm"],
            returncode=7,
            stdout="partial stdout",
            stderr="partial stderr",
        )

    try:
        with mock.patch.object(fix.subprocess, "run", side_effect=partial_npm):
            result = fix._install_candidate_npm(
                candidate_tgz=tgz,
                npm_prefix=prefix,
                home=home,
                caller_cwd=caller,
            )
    except Exception as exc:
        errors.append(f"{name}:unexpected:{type(exc).__name__}:{exc}")
        return 0
    if not (
        result.get("ok") is False
        and result.get("reason") == "npm_candidate_install_failed"
        and result.get("mutation_attempted") is True
        and str(package_root) in result.get("residual_targets", [])
        and result.get("exit_code") == 7
        and result.get("stdout") == "partial stdout"
        and result.get("stderr") == "partial stderr"
    ):
        errors.append(f"{name}:contract_failed:{result}")
        return 0
    return 1


def _check_candidate_npm_replace_existing_relative_backup(
    temp_root: Path,
    errors: list[str],
) -> int:
    """Explicit npm replacement backs up owned targets with relative coordinates."""

    name = "candidate_npm_replace_existing_relative_backup"
    try:
        from commands import fix_decretum_matrix as fix
    except Exception as exc:
        errors.append(f"{name}:import:{type(exc).__name__}:{exc}")
        return 0
    passed = 0
    home = temp_root / "home"
    caller = temp_root / "caller"
    prefix = temp_root / "npm-prefix"
    tgz = temp_root / "candidate.tgz"
    package_root = prefix / "node_modules" / "@rowlandl" / "decretum-matrix"
    local_bin = prefix / "node_modules" / ".bin"
    global_shim = prefix / "decretum-matrix.cmd"
    caller.mkdir(parents=True, exist_ok=True)
    package_root.mkdir(parents=True, exist_ok=True)
    local_bin.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    (package_root / "old-marker.txt").write_text("old package\n", encoding="utf-8")
    (local_bin / "decretum-matrix.cmd").write_text("old local shim\n", encoding="utf-8")
    global_shim.write_text("old global shim\n", encoding="utf-8")
    tgz.write_bytes(b"candidate")

    default_result = fix._install_candidate_npm(
        candidate_tgz=tgz,
        npm_prefix=prefix,
        home=home,
        caller_cwd=caller,
    )
    if default_result.get("reason") == "candidate_package_preexisting":
        passed += 1
    else:
        errors.append(f"{name}:default_rejection:{default_result}")

    try:
        backup = fix._prepare_candidate_npm_replacement(prefix.resolve(), home.resolve())
    except Exception as exc:
        errors.append(f"{name}:prepare:{type(exc).__name__}:{exc}")
        return passed
    manifest_path = Path(str(backup["backup_root"])) / "backup-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{name}:manifest:{type(exc).__name__}:{exc}")
        return passed
    moved = manifest.get("moved_targets")
    snapshots = manifest.get("unmoved_global_shim_snapshots")
    moved_relatives = {
        item.get("target_relative")
        for item in moved
        if isinstance(item, dict)
    } if isinstance(moved, list) else set()
    snapshot_relatives = {
        item.get("target_relative")
        for item in snapshots
        if isinstance(item, dict)
    } if isinstance(snapshots, list) else set()
    absolute_item_paths = [
        value
        for collection in (moved or [], snapshots or [])
        for item in collection
        if isinstance(item, dict)
        for value in (item.get("target_relative"), item.get("backup_relative"))
        if isinstance(value, str) and Path(value).is_absolute()
    ]
    if not (
        manifest.get("schema") == "decretum.npm_global_replace_backup.v1"
        and manifest.get("path_style") == "relative_to_npm_prefix"
        and "node_modules/@rowlandl/decretum-matrix" in moved_relatives
        and "node_modules/.bin/decretum-matrix.cmd" in moved_relatives
        and "decretum-matrix.cmd" in snapshot_relatives
        and not absolute_item_paths
        and not package_root.exists()
        and not (local_bin / "decretum-matrix.cmd").exists()
        and global_shim.read_text(encoding="utf-8") == "old global shim\n"
    ):
        errors.append(f"{name}:relative_backup_contract:{manifest}")
        return passed

    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "new-marker.txt").write_text("new package\n", encoding="utf-8")
    (local_bin / "decretum-matrix.cmd").write_text("new local shim\n", encoding="utf-8")
    rollback = fix._rollback_candidate_npm(
        npm_prefix=prefix,
        home=home,
        caller_cwd=caller,
        replacement_backup=manifest,
    )
    if (
        rollback.get("ok") is True
        and (package_root / "old-marker.txt").read_text(encoding="utf-8") == "old package\n"
        and (local_bin / "decretum-matrix.cmd").read_text(encoding="utf-8") == "old local shim\n"
        and global_shim.read_text(encoding="utf-8") == "old global shim\n"
        and rollback.get("replacement_restore", {}).get("status") == "RESTORED"
    ):
        passed += 1
    else:
        errors.append(f"{name}:rollback_restore:{rollback}")
    return passed


def _check_candidate_public_shim_mismatch(
    temp_root: Path,
    errors: list[str],
) -> int:
    """The actual npm .bin shim, not the package-local JS file, gates completion."""

    name = "candidate_public_shim_mismatch_is_rejected"
    try:
        from commands import fix_decretum_matrix as fix
    except Exception as exc:
        errors.append(f"{name}:import:{type(exc).__name__}:{exc}")
        return 0
    root = temp_root / _fixture_slug(name)
    source = root / "source"
    caller = root / "caller"
    home = root / "home"
    package_root = (
        root
        / "npm-prefix"
        / "node_modules"
        / "@rowlandl"
        / "decretum-matrix"
    )
    candidate_entry = package_root / "bin" / "decretum-matrix.js"
    public_bin = package_root.parents[1] / ".bin"
    for path in (source, caller, home, candidate_entry.parent, public_bin):
        path.mkdir(parents=True, exist_ok=True)
    binding = {
        "schema": "court.installation_binding.v2",
        "source_commit": "candidate-commit",
        "release_label": "beta1.1.2",
        "artifact_ref": "release/decretum-matrix-beta1.1.2.zip@candidate-commit",
        "build_id": "beta1.1.2:candidate-commit:tree-a",
        "installation_id": "installation-a",
        "generation": 1,
        "canonical_root": str((home / ".agents" / "skills" / "decretum-matrix").resolve()),
        "selected_roots": [str((home / ".agents" / "skills" / "decretum-matrix").resolve())],
        "completion": "COMMITTED",
        "transaction_id": "transaction-a",
        "rollback_ref": "rollback-a",
    }
    candidate_entry.write_text(
        "#!/usr/bin/env node\n"
        + f"process.stdout.write({json.dumps(json.dumps(binding))} + '\\n');\n",
        encoding="utf-8",
    )
    stale = {**binding, "source_commit": "old-public-shim-commit"}
    stale_json = json.dumps(stale, sort_keys=True)
    if os.name == "nt":
        public_shim = public_bin / "decretum-matrix.cmd"
        public_shim.write_text("@echo off\r\necho " + stale_json + "\r\n", encoding="utf-8")
    else:
        public_shim = public_bin / "decretum-matrix"
        public_shim.write_text(
            "#!/bin/sh\n" + "printf '%s\\n' '" + stale_json + "'\n",
            encoding="utf-8",
        )
        public_shim.chmod(public_shim.stat().st_mode | stat.S_IXUSR)
    try:
        result = fix._run_public_shim_probe(
            candidate_package_root=package_root,
            source=source,
            home=home,
            binding=binding,
            caller_cwd=caller,
        )
    except Exception as exc:
        errors.append(f"{name}:unexpected:{type(exc).__name__}:{exc}")
        return 0
    if not (
        result.get("ok") is False
        and result.get("reason") == "public_shim_binding_mismatch"
    ):
        errors.append(f"{name}:contract_failed:{result}")
        return 0
    return 1


def _check_cases(
    install: Installer,
    temp_root: Path,
    errors: list[str],
) -> int:
    passed = 0

    def install_args(
        source: Path,
        home: Path,
        manifest: Path,
        roots: dict[str, Path],
        *,
        write: bool,
        **extra: object,
    ) -> Payload:
        return {
            "source_root": source,
            "home_root": home,
            "current_tool": "codex",
            "explicit_tools": [],
            "tool_roots": roots,
            "projection_manifest": manifest,
            "write": write,
            **extra,
        }

    source, home, manifest, roots = _case_fixture(temp_root, "codex-default")
    _prime_roots(home, roots)
    before = _snapshots([_agents_root(home), *roots.values()])
    if _require_success(
        install,
        name="codex_default_agents_plus_current",
        expected_targets=[_agents_root(home), roots["codex"]],
        errors=errors,
        **install_args(source, home, manifest, roots, write=False),
    ) is not None:
        after = _snapshots([_agents_root(home), *roots.values()])
        if after != before:
            errors.append("codex_default_agents_plus_current:plan_mutated_targets")
        else:
            passed += 1

    source, home, manifest, roots = _case_fixture(temp_root, "unknown-default")
    _prime_roots(home, roots)
    if _require_success(
        install,
        name="unknown_tool_agents_only",
        expected_targets=[_agents_root(home)],
        errors=errors,
        **install_args(
            source, home, manifest, roots, write=False, current_tool="unknown"
        ),
    ) is not None:
        passed += 1

    source, home, manifest, roots = _case_fixture(temp_root, "explicit-hermes")
    _prime_roots(home, roots)
    if _require_success(
        install,
        name="codex_explicit_hermes",
        expected_targets=[
            _agents_root(home),
            roots["codex"],
            roots["hermes"],
        ],
        errors=errors,
        **install_args(
            source, home, manifest, roots, write=False, explicit_tools=["hermes"]
        ),
    ) is not None:
        passed += 1

    source, home, manifest, roots = _case_fixture(temp_root, "write-and-repeat")
    _prime_roots(home, roots)
    forbidden_before = _snapshots(
        [roots["claude"], roots["hermes"], roots["other"]]
    )
    first = _require_success(
        install,
        name="default_write_excludes_unrequested_tools",
        expected_targets=[_agents_root(home), roots["codex"]],
        errors=errors,
        **install_args(source, home, manifest, roots, write=True),
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
        forbidden_after = _snapshots(
            [roots["claude"], roots["hermes"], roots["other"]]
        )
        if forbidden_after != forbidden_before:
            errors.append(
                "default_write_excludes_unrequested_tools:forbidden_target_mutated"
            )
        else:
            passed += 1

        repeat_before = _snapshots([_agents_root(home), roots["codex"]])
        if _require_success(
            install,
            name="repeated_identical_write_is_idempotent",
            expected_targets=[_agents_root(home), roots["codex"]],
            errors=errors,
            **install_args(source, home, manifest, roots, write=True),
        ) is not None:
            repeat_after = _snapshots([_agents_root(home), roots["codex"]])
            if repeat_after != repeat_before:
                errors.append(
                    "repeated_identical_write_is_idempotent:bytes_changed"
                )
            else:
                passed += 1

        conflict_path = _agents_root(home) / "SKILL.md"
        conflict_preimage = b"# conflicting target bytes\n"
        conflict_path.write_bytes(conflict_preimage)
        overlay = _require_success(
            install,
            name="stale_projected_bytes_update_transactionally",
            expected_targets=[_agents_root(home), roots["codex"]],
            errors=errors,
            **install_args(source, home, manifest, roots, write=True),
        )
        if overlay is not None:
            if conflict_path.read_bytes() != (source / "SKILL.md").read_bytes():
                errors.append("stale_projected_bytes_update_transactionally:not_updated")
            else:
                backup = overlay.get("backup")
                backup_root = (
                    Path(str(backup.get("backup_root")))
                    if isinstance(backup, dict) and backup.get("backup_root")
                    else None
                )
                manifest_path = backup_root / "manifest.json" if backup_root else None
                backup_ok = (
                    isinstance(backup, dict)
                    and backup.get("status") == "CREATED"
                    and backup.get("rollback_supported") is True
                    and backup_root is not None
                    and manifest_path is not None
                    and manifest_path.is_file()
                    and not any(
                        part.casefold() in {"pending", "private"}
                        for part in backup_root.parts
                    )
                )
                rollback = install.__globals__["rollback_install_backup"](
                    home_root=home,
                    backup_root=backup_root,
                ) if backup_ok else None
                if (
                    not backup_ok
                    or not isinstance(rollback, dict)
                    or rollback.get("ok") is not True
                    or rollback.get("pending_body_accessed") is not False
                    or conflict_path.read_bytes() != conflict_preimage
                ):
                    errors.append(
                        "stale_projected_bytes_update_transactionally:backup_or_rollback_failed"
                    )
                else:
                    passed += 1

    cleanup_name = "active_projection_cleanup_backup_and_rollback"
    cleanup_manifest = _fixture_manifest()
    cleanup_projections = cleanup_manifest["projections"]
    assert isinstance(cleanup_projections, dict)
    for projection_name in ("shared_agents", "portable_current_tool"):
        projection = cleanup_projections[projection_name]
        assert isinstance(projection, list)
        projection.append(SOURCE_ONLY_CHECKER)
    cleanup_old_manifest = deepcopy(cleanup_manifest)
    cleanup_old_projections = cleanup_old_manifest["projections"]
    assert isinstance(cleanup_old_projections, dict)
    cleanup_old_projections["repository_only"] = []
    cleanup_old_manifest_bytes = (
        json.dumps(cleanup_old_manifest, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    source, home, manifest, roots = _case_fixture(
        temp_root,
        cleanup_name,
        cleanup_manifest,
    )
    cleanup_targets = [_agents_root(home), roots["codex"]]
    for target in cleanup_targets:
        for relative in (*PORTABLE_FILES, SOURCE_ONLY_CHECKER):
            source_path = source / Path(relative)
            target_path = target / Path(relative)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
        repository_only = target / Path(REPOSITORY_ONLY_FILES[0])
        repository_only.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / Path(REPOSITORY_ONLY_FILES[0]), repository_only)
        (
            target / "references" / "manifests" / "install-projection.v1.json"
        ).write_bytes(cleanup_old_manifest_bytes)
        (target / "nonmanaged.txt").write_text("preserve\n", encoding="utf-8")
    cleanup_result = _require_success(
        install,
        name=cleanup_name,
        expected_targets=cleanup_targets,
        errors=errors,
        **install_args(source, home, manifest, roots, write=True),
    )
    if cleanup_result is not None:
        backup = cleanup_result.get("backup")
        backup_root = (
            Path(str(backup.get("backup_root")))
            if isinstance(backup, dict) and backup.get("backup_root")
            else None
        )
        backup_manifest = (
            _load_json(
                backup_root / "manifest.json",
                label="cleanup_backup_manifest",
                errors=errors,
            )
            if backup_root is not None
            else None
        )
        entries = (
            backup_manifest.get("entries")
            if isinstance(backup_manifest, dict)
            else None
        )
        delete_entries = [
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("action") == "DELETE"
        ] if isinstance(entries, list) else []
        source_checker_sha256 = hashlib.sha256(
            (source / SOURCE_ONLY_CHECKER).read_bytes()
        ).hexdigest()
        active_manifest_ok = True
        for target in cleanup_targets:
            target_manifest = _load_json(
                target / "references" / "manifests" / "install-projection.v1.json",
                label="cleanup_active_manifest",
                errors=errors,
            )
            active_manifest_ok = active_manifest_ok and isinstance(
                target_manifest,
                dict,
            ) and "active_render" not in target_manifest
            active_manifest_ok = active_manifest_ok and isinstance(
                target_manifest.get("projections") if isinstance(target_manifest, dict) else None,
                dict,
            ) and target_manifest["projections"].get("repository_only") == []
        applied_checks = (
            cleanup_result.get("projection_counts", {}).get("delete")
            == len(cleanup_targets) * 2,
            isinstance(backup, dict)
            and backup.get("delete_count") == len(cleanup_targets) * 2,
            len(delete_entries) == len(cleanup_targets) * 2,
            all(
                entry.get("path") in {SOURCE_ONLY_CHECKER, REPOSITORY_ONLY_FILES[0]}
                and entry.get("installed_sha256") is None
                and (
                    entry.get("previous_sha256") == source_checker_sha256
                    if entry.get("path") == SOURCE_ONLY_CHECKER
                    else isinstance(entry.get("previous_sha256"), str)
                )
                and isinstance(entry.get("backup_path"), str)
                for entry in delete_entries
            ),
            all(
                not (target / SOURCE_ONLY_CHECKER).exists()
                and not (target / Path(REPOSITORY_ONLY_FILES[0])).exists()
                and not (target / "scripts" / "checks").exists()
                and (target / "nonmanaged.txt").read_text(encoding="utf-8")
                == "preserve\n"
                for target in cleanup_targets
            ),
            active_manifest_ok,
        )
        rollback = (
            install.__globals__["rollback_install_backup"](
                home_root=home,
                backup_root=backup_root,
            )
            if backup_root is not None
            else None
        )
        rollback_checks = (
            isinstance(rollback, dict)
            and rollback.get("ok") is True,
            all(
                (target / SOURCE_ONLY_CHECKER).read_bytes()
                == (source / SOURCE_ONLY_CHECKER).read_bytes()
                and (target / "scripts" / "checks").is_dir()
                and (target / "nonmanaged.txt").read_text(encoding="utf-8")
                == "preserve\n"
                for target in cleanup_targets
            ),
        )
        if not all(applied_checks) or not all(rollback_checks):
            errors.append(
                f"{cleanup_name}:contract_failed:{cleanup_result}:{rollback}"
            )
        else:
            passed += 1

    cross_version_name = "active_projection_cleanup_cross_version_rollback"
    cross_version_manifest = _fixture_manifest()
    cross_version_projections = cross_version_manifest["projections"]
    assert isinstance(cross_version_projections, dict)
    for projection_name in ("shared_agents", "portable_current_tool"):
        projection = cross_version_projections[projection_name]
        assert isinstance(projection, list)
        projection.append(SOURCE_ONLY_CHECKER)
    source, home, manifest, roots = _case_fixture(
        temp_root,
        cross_version_name,
        cross_version_manifest,
    )
    cross_version_targets = [_agents_root(home), roots["codex"]]
    previous_checker_bytes = b"CHECKER = 'prior-release'\n"
    for target in cross_version_targets:
        for relative in (*PORTABLE_FILES, SOURCE_ONLY_CHECKER):
            source_path = source / Path(relative)
            target_path = target / Path(relative)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
        (target / SOURCE_ONLY_CHECKER).write_bytes(previous_checker_bytes)
    cross_version_result = _require_success(
        install,
        name=cross_version_name,
        expected_targets=cross_version_targets,
        errors=errors,
        **install_args(source, home, manifest, roots, write=True),
    )
    if cross_version_result is not None:
        backup = cross_version_result.get("backup")
        backup_root = (
            Path(str(backup.get("backup_root")))
            if isinstance(backup, dict) and backup.get("backup_root")
            else None
        )
        backup_manifest = (
            _load_json(
                backup_root / "manifest.json",
                label="cross_version_backup_manifest",
                errors=errors,
            )
            if backup_root is not None
            else None
        )
        entries = (
            backup_manifest.get("entries")
            if isinstance(backup_manifest, dict)
            else None
        )
        delete_entries = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("action") == "DELETE"
            and entry.get("path") == SOURCE_ONLY_CHECKER
        ] if isinstance(entries, list) else []
        rollback = (
            install.__globals__["rollback_install_backup"](
                home_root=home,
                backup_root=backup_root,
            )
            if backup_root is not None
            else None
        )
        cross_version_checks = (
            cross_version_result.get("projection_counts", {}).get("delete")
            == len(cross_version_targets),
            len(delete_entries) == len(cross_version_targets),
            all(
                entry.get("previous_sha256")
                == hashlib.sha256(previous_checker_bytes).hexdigest()
                and entry.get("previous_sha256")
                != hashlib.sha256(
                    (source / SOURCE_ONLY_CHECKER).read_bytes()
                ).hexdigest()
                for entry in delete_entries
            ),
            isinstance(rollback, dict)
            and rollback.get("ok") is True,
            all(
                (target / SOURCE_ONLY_CHECKER).read_bytes() == previous_checker_bytes
                and (target / "scripts" / "checks").is_dir()
                for target in cross_version_targets
            ),
        )
        if not all(cross_version_checks):
            errors.append(
                f"{cross_version_name}:contract_failed:"
                f"{cross_version_result}:{rollback}"
            )
        else:
            passed += 1

    hierarchy_name = "legacy_flat_a_b_hierarchy_upgrade_and_rollback"
    hierarchy_manifest = _fixture_manifest()
    hierarchy_projections = hierarchy_manifest["projections"]
    assert isinstance(hierarchy_projections, dict)
    for projection_name in ("shared_agents", "portable_current_tool"):
        projection = hierarchy_projections[projection_name]
        assert isinstance(projection, list)
        projection.extend(
            (
                A_B_ROOT_COMPATIBILITY_SHELL,
                A_B_COMMAND_BODY,
                A_B_SERVICE_BODY,
                A_B_ROOT_SOURCE_ONLY_CHECKER,
                A_B_CHECKS_SOURCE_ONLY_CHECKER,
            )
        )
    source, home, manifest, roots = _case_fixture(
        temp_root,
        hierarchy_name,
        hierarchy_manifest,
    )
    new_root_shell = b"from commands import sync_active_copies as _real\n"
    new_command_body = b"COMMAND_BODY = 'new-hierarchy'\n"
    new_service_body = b"SERVICE_BODY = 'new-hierarchy'\n"
    source_root_checker = b"ROOT_CHECKER = 'source-only'\n"
    source_checks_checker = b"CHECKS_CHECKER = 'source-only'\n"
    for relative, payload in (
        (A_B_ROOT_COMPATIBILITY_SHELL, new_root_shell),
        (A_B_COMMAND_BODY, new_command_body),
        (A_B_SERVICE_BODY, new_service_body),
        (A_B_ROOT_SOURCE_ONLY_CHECKER, source_root_checker),
        (A_B_CHECKS_SOURCE_ONLY_CHECKER, source_checks_checker),
    ):
        path = source / Path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    old_manifest = deepcopy(hierarchy_manifest)
    old_projections = old_manifest["projections"]
    assert isinstance(old_projections, dict)
    for projection_name in ("shared_agents", "portable_current_tool"):
        projection = old_projections[projection_name]
        assert isinstance(projection, list)
        for relative in (A_B_COMMAND_BODY, A_B_SERVICE_BODY):
            projection.remove(relative)
    historical_managed_paths = {
        A_B_ROOT_COMPATIBILITY_SHELL,
        A_B_ROOT_SOURCE_ONLY_CHECKER,
        A_B_CHECKS_SOURCE_ONLY_CHECKER,
    }
    old_manifest_bytes = (
        json.dumps(old_manifest, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    hierarchy_targets = [_agents_root(home), roots["codex"]]
    old_root_shell = b"OLD_FLAT_ROOT_COMMAND = True\n"
    old_root_checker = b"OLD_FLAT_ROOT_CHECKER = True\n"
    old_checks_checker = b"OLD_FLAT_CHECKS_CHECKER = True\n"
    for target in hierarchy_targets:
        for relative in (*PORTABLE_FILES, *historical_managed_paths):
            source_path = source / Path(relative)
            target_path = target / Path(relative)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
        (target / A_B_ROOT_COMPATIBILITY_SHELL).write_bytes(old_root_shell)
        (target / A_B_ROOT_SOURCE_ONLY_CHECKER).write_bytes(old_root_checker)
        (target / A_B_CHECKS_SOURCE_ONLY_CHECKER).write_bytes(old_checks_checker)
        manifest_target = (
            target / "references" / "manifests" / "install-projection.v1.json"
        )
        manifest_target.write_bytes(old_manifest_bytes)
        unknown_user_file = target / "scripts" / "checks" / "user-owned.txt"
        unknown_user_file.parent.mkdir(parents=True, exist_ok=True)
        unknown_user_file.write_text("preserve user ownership\n", encoding="utf-8")
    hierarchy_result = _require_success(
        install,
        name=hierarchy_name,
        expected_targets=hierarchy_targets,
        errors=errors,
        **install_args(source, home, manifest, roots, write=True),
    )
    if hierarchy_result is not None:
        backup = hierarchy_result.get("backup")
        backup_root = (
            Path(str(backup.get("backup_root")))
            if isinstance(backup, dict) and backup.get("backup_root")
            else None
        )
        backup_manifest = (
            _load_json(
                backup_root / "manifest.json",
                label="hierarchy_backup_manifest",
                errors=errors,
            )
            if backup_root is not None
            else None
        )
        entries = (
            backup_manifest.get("entries")
            if isinstance(backup_manifest, dict)
            else None
        )
        action_by_path = {
            str(entry.get("path")): str(entry.get("action"))
            for entry in entries
            if isinstance(entry, dict)
        } if isinstance(entries, list) else {}
        delete_paths = {
            str(entry.get("path"))
            for entry in entries
            if isinstance(entry, dict) and entry.get("action") == "DELETE"
        } if isinstance(entries, list) else set()
        hierarchy_apply_checks = (
            hierarchy_result.get("projection_counts", {}).get("delete")
            == len(hierarchy_targets) * 2,
            action_by_path.get(A_B_ROOT_COMPATIBILITY_SHELL) == "REPLACE",
            action_by_path.get(A_B_COMMAND_BODY) == "CREATE",
            action_by_path.get(A_B_SERVICE_BODY) == "CREATE",
            delete_paths
            == {
                A_B_ROOT_SOURCE_ONLY_CHECKER,
                A_B_CHECKS_SOURCE_ONLY_CHECKER,
            },
            delete_paths.issubset(historical_managed_paths),
            all(
                (target / A_B_ROOT_COMPATIBILITY_SHELL).read_bytes()
                == new_root_shell
                and (target / A_B_COMMAND_BODY).read_bytes() == new_command_body
                and (target / A_B_SERVICE_BODY).read_bytes() == new_service_body
                and not (target / A_B_ROOT_SOURCE_ONLY_CHECKER).exists()
                and not (target / A_B_CHECKS_SOURCE_ONLY_CHECKER).exists()
                and (target / "scripts" / "checks" / "user-owned.txt").is_file()
                for target in hierarchy_targets
            ),
            (source / A_B_CHECKS_SOURCE_ONLY_CHECKER).is_file(),
        )
        rollback = (
            install.__globals__["rollback_install_backup"](
                home_root=home,
                backup_root=backup_root,
            )
            if backup_root is not None
            else None
        )
        hierarchy_rollback_checks = (
            isinstance(rollback, dict) and rollback.get("ok") is True,
            all(
                (target / A_B_ROOT_COMPATIBILITY_SHELL).read_bytes()
                == old_root_shell
                and not (target / A_B_COMMAND_BODY).exists()
                and not (target / A_B_SERVICE_BODY).exists()
                and (target / A_B_ROOT_SOURCE_ONLY_CHECKER).read_bytes()
                == old_root_checker
                and (target / A_B_CHECKS_SOURCE_ONLY_CHECKER).read_bytes()
                == old_checks_checker
                and (
                    target
                    / "references"
                    / "manifests"
                    / "install-projection.v1.json"
                ).read_bytes()
                == old_manifest_bytes
                and (target / "scripts" / "checks" / "user-owned.txt").is_file()
                for target in hierarchy_targets
            ),
        )
        if not all(hierarchy_apply_checks) or not all(hierarchy_rollback_checks):
            errors.append(
                f"{hierarchy_name}:contract_failed:"
                f"{hierarchy_result}:{rollback}"
            )
        else:
            passed += 1

    frozen_relative = "references/benchmarks/cft0808-edict.yaml"
    frozen_manifest = _fixture_manifest()
    projections = frozen_manifest["projections"]
    assert isinstance(projections, dict)
    for projection_name in ("shared_agents", "portable_current_tool"):
        projection = projections[projection_name]
        assert isinstance(projection, list)
        projection.append(frozen_relative)
    frozen_manifest["frozen_install_references"] = [frozen_relative]
    source, home, manifest, roots = _case_fixture(
        temp_root, "frozen_reference_replaced_and_refrozen", frozen_manifest
    )
    source_frozen = source / Path(frozen_relative)
    source_frozen.parent.mkdir(parents=True, exist_ok=True)
    source_frozen.write_text("current reference\n", encoding="utf-8")
    _prime_roots(home, roots)
    frozen_targets = [_agents_root(home), roots["codex"]]
    frozen_preimage = b"stale reference\n"
    for target in frozen_targets:
        destination = target / Path(frozen_relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(frozen_preimage)
        destination.chmod(
            destination.stat().st_mode
            & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        )
    frozen_result = _require_success(
        install,
        name="frozen_reference_replaced_and_refrozen",
        expected_targets=frozen_targets,
        errors=errors,
        **install_args(source, home, manifest, roots, write=True),
    )
    if frozen_result is not None:
        backup = frozen_result.get("backup")
        backup_root = (
            Path(str(backup.get("backup_root")))
            if isinstance(backup, dict) and backup.get("backup_root")
            else None
        )
        applied_ok = all(
            (target / Path(frozen_relative)).read_bytes() == source_frozen.read_bytes()
            and not (
                (target / Path(frozen_relative)).stat().st_mode & stat.S_IWUSR
            )
            for target in frozen_targets
        )
        rollback = (
            install.__globals__["rollback_install_backup"](
                home_root=home,
                backup_root=backup_root,
            )
            if backup_root is not None
            else None
        )
        rollback_ok = all(
            (target / Path(frozen_relative)).read_bytes() == frozen_preimage
            and not (
                (target / Path(frozen_relative)).stat().st_mode & stat.S_IWUSR
            )
            for target in frozen_targets
        )
        if (
            not applied_ok
            or not isinstance(rollback, dict)
            or rollback.get("ok") is not True
            or not rollback_ok
        ):
            errors.append("frozen_reference_replaced_and_refrozen:contract_failed")
        else:
            passed += 1

    source, home, manifest, roots = _case_fixture(temp_root, "fanout")
    _prime_roots(home, roots)
    fanout_before = _snapshots([_agents_root(home), *roots.values()])
    if _require_rejection(
        install,
        name="fixed_five_root_fanout_rejected",
        reason="fanout_forbidden",
        errors=errors,
        **install_args(source, home, manifest, roots, write=True, fanout=True),
    ):
        fanout_after = _snapshots([_agents_root(home), *roots.values()])
        if fanout_after != fanout_before:
            errors.append("fixed_five_root_fanout_rejected:partial_mutation")
        else:
            passed += 1

    relative = next(iter(PROTECTED_SEEDS))
    source, home, manifest, roots = _case_fixture(
        temp_root, "protected-anchor-no-read"
    )
    protected_target = _agents_root(home) / Path(relative)
    _write_files(_agents_root(home), {relative: "existing private record\n"})
    protected_before = protected_target.read_bytes()
    original_read_bytes = Path.read_bytes

    def reject_protected_read(path: Path) -> bytes:
        if path.resolve(strict=False) == protected_target.resolve(strict=False):
            raise AssertionError("protected Shiguan bytes were read")
        return original_read_bytes(path)

    with mock.patch.object(Path, "read_bytes", reject_protected_read):
        protected_result = _require_success(
            install,
            name="protected_anchor_bytes_not_read_or_written",
            expected_targets=[_agents_root(home), roots["codex"]],
            errors=errors,
            **install_args(source, home, manifest, roots, write=True),
        )
    protected_contract = (
        protected_result.get("protected_shiguan_data")
        if isinstance(protected_result, dict)
        else None
    )
    if (
        not isinstance(protected_contract, dict)
        or protected_contract.get("status")
        != "NO_READ_NO_WRITE_NO_MOVE_NO_REWRITE"
        or protected_contract.get("operation_count") != 0
        or protected_target.read_bytes() != protected_before
    ):
        errors.append("protected_anchor_bytes_not_read_or_written:contract_failed")
    else:
        passed += 1

    source, home, manifest, roots = _case_fixture(
        temp_root, "protected-source-no-read"
    )
    protected_source = source / Path(relative)
    protected_source.write_text("source drift\n", encoding="utf-8")
    source_before = protected_source.read_bytes()

    def reject_protected_source_read(path: Path) -> bytes:
        if path.resolve(strict=False) == protected_source.resolve(strict=False):
            raise AssertionError("protected package seed bytes were read")
        return original_read_bytes(path)

    with mock.patch.object(Path, "read_bytes", reject_protected_source_read):
        source_result = _require_success(
            install,
            name="protected_anchor_source_bytes_not_read",
            expected_targets=[_agents_root(home), roots["codex"]],
            errors=errors,
            **install_args(source, home, manifest, roots, write=False),
        )
    if source_result is None or protected_source.read_bytes() != source_before:
        errors.append("protected_anchor_source_bytes_not_read:contract_failed")
    else:
        passed += 1

    source, home, manifest, roots = _case_fixture(
        temp_root, "protected-anchor-wrong-target"
    )
    _write_files(roots["codex"], {relative: "second physical record\n"})
    before = _snapshots([_agents_root(home), roots["codex"]])
    if _require_rejection(
        install,
        name="protected_anchor_wrong_target_rejected",
        reason="protected_anchor_wrong_target",
        errors=errors,
        **install_args(source, home, manifest, roots, write=True),
    ):
        if _snapshots([_agents_root(home), roots["codex"]]) != before:
            errors.append("protected_anchor_wrong_target_rejected:partial_mutation")
        else:
            passed += 1

    bad_manifest = _fixture_manifest()
    bad_manifest["protected_shared_agents_seeds"] = ["unexpected-anchor"]
    source, home, manifest, roots = _case_fixture(temp_root, "protected-contract", bad_manifest)
    if _require_rejection(
        install, name="protected_contract_drift_rejected",
        reason="projection_manifest_invalid", errors=errors,
        **install_args(source, home, manifest, roots, write=False),
    ):
        passed += 1

    passed += _check_tx_cases(install, temp_root, errors, legacy=True)
    passed += _check_tx_cases(install, temp_root, errors, legacy=False)
    passed += _check_npm_postinstall_fixture(temp_root, errors)
    failure = _case_hermes_alias_commit_failure_restores_legacy_junction(
        install, temp_root
    )
    if failure:
        errors.append(failure)
    else:
        passed += 1

    source, home, manifest, roots = _case_fixture(temp_root, "escaped-target")
    roots["codex"] = home.parent / "outside-home" / "decretum-matrix"
    _prime_roots(home, roots)
    escape_before = _snapshots([_agents_root(home), *roots.values()])
    if _require_rejection(
        install,
        name="target_outside_home_rejected",
        reason="target_outside_home",
        errors=errors,
        **install_args(source, home, manifest, roots, write=True),
    ):
        escape_after = _snapshots([_agents_root(home), *roots.values()])
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
    _prime_roots(home, roots)
    invalid_before = _snapshots([_agents_root(home), *roots.values()])
    if _require_rejection(
        install,
        name="absolute_persisted_binding_rejected",
        reason="persisted_path_invalid",
        errors=errors,
        **install_args(source, home, manifest, roots, write=True),
    ):
        invalid_after = _snapshots([_agents_root(home), *roots.values()])
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
        _prime_roots(home, roots)
        if _require_success(
            install,
            name=f"relative_binding_relocates_{label}",
            expected_targets=[_agents_root(home), roots["codex"]],
            errors=errors,
            **install_args(
                source_root, home, projection_manifest, roots, write=True
            ),
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
    before = len(errors)
    source, home, manifest, roots = _case_fixture(temp_root, "darwin-clean-home")
    all_roots = [_agents_root(home), *roots.values()]
    root_snapshots = _snapshots(all_roots)
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
        **install_args(
            source,
            home,
            manifest,
            roots,
            write=True,
            platform_context=platform_context,
        ),
    )
    if result is not None:
        _assert_projection(_agents_root(home), name=name, errors=errors)
        _assert_projection(roots["codex"], name=name, errors=errors)
        targets = _normalize_targets(result)
        shared_targets = [path for path in targets if ".agents" in path.parts]
        if shared_targets != [_agents_root(home).resolve(strict=False)]:
            errors.append(f"{name}:shared_agents_not_unique:{shared_targets!r}")
        for target in (roots["claude"], roots["hermes"], roots["other"]):
            if _snapshot(target) != root_snapshots[str(target.resolve(strict=False))]:
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
    if len(errors) == before:
        passed += 1

    name = "source_package_sha256_receipt_round_trip"
    before = len(errors)
    source, home, manifest, roots = _case_fixture(
        temp_root, "source-package-sha256"
    )
    _prime_roots(home, roots)
    source_package_sha256 = "a" * 64
    result = _require_success(
        install,
        name=name,
        expected_targets=[_agents_root(home), roots["codex"]],
        errors=errors,
        **install_args(
            source,
            home,
            manifest,
            roots,
            write=True,
            source_package_sha256=source_package_sha256,
        ),
    )
    if result is not None and result.get("source_package_sha256") != source_package_sha256:
        errors.append(f"{name}:top_level_source_package_sha256_missing")
    if result is not None:
        receipt = result.get("install_receipt")
        if (
            not isinstance(receipt, dict)
            or receipt.get("ok") is not True
            or receipt.get("source_package_sha256") != source_package_sha256
        ):
            errors.append(f"{name}:install_receipt_package_binding_missing")
        receipt_path = result.get("install_receipt_path")
        try:
            persisted_receipt = json.loads(Path(str(receipt_path)).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(f"{name}:persisted_install_receipt_unreadable")
        else:
            if (
                persisted_receipt.get("ok") is not True
                or persisted_receipt.get("source_package_sha256") != source_package_sha256
            ):
                errors.append(f"{name}:persisted_install_receipt_package_binding_missing")
    if len(errors) == before:
        passed += 1

    name = "invalid_source_package_sha256_rejected"
    before = len(errors)
    source, home, manifest, roots = _case_fixture(
        temp_root, "invalid-source-package-sha256"
    )
    _prime_roots(home, roots)
    invalid_values: tuple[object, ...] = ("", "A" * 64, "g" * 64, 7)
    rejected = all(
        _require_rejection(
            install,
            name=f"{name}:{index}",
            reason="source_package_sha256_invalid",
            errors=errors,
            **install_args(
                source,
                home,
                manifest,
                roots,
                write=False,
                source_package_sha256=value,
            ),
        )
        for index, value in enumerate(invalid_values)
    )
    if rejected and len(errors) == before:
        passed += 1

    name = "installation_binding_v2_stays_pending_until_external_acceptance"
    before = len(errors)
    source, home, manifest, roots = _case_fixture(
        temp_root, "installation-binding-v2"
    )
    binding_metadata: Payload = {
        "source_commit": "commit-a",
        "release_label": "beta1.0.1",
        "artifact_ref": "candidate/beta1.0.1/commit-a.zip",
        "build_id": "beta1.0.1:commit-a:tree-a",
        "installation_id": "installation-a",
        "transaction_id": "transaction-a",
        "provenance_receipt_ref": "candidate-receipt-a",
    }
    binding_result, binding_rejection = _invoke(
        install,
        **install_args(
            source,
            home,
            manifest,
            roots,
            write=True,
            installation_binding=binding_metadata,
        ),
    )
    if binding_result is None or binding_rejection is not None:
        errors.append(f"{name}:unexpected_rejection:{binding_rejection}")
    else:
        if binding_result.get("status") != "PENDING_VALIDATION":
            errors.append(
                f"{name}:install_status_must_be_pending:{binding_result.get('status')!r}"
            )
        binding = binding_result.get("installation_binding")
        if not isinstance(binding, dict):
            errors.append(f"{name}:binding_missing")
        else:
            expected_fields = {
                "source_commit",
                "release_label",
                "artifact_ref",
                "build_id",
                "installation_id",
                "generation",
                "canonical_root",
                "selected_roots",
                "completion",
                "provenance_receipt_ref",
                "transaction_id",
                "rollback_ref",
            }
            if binding.get("schema") != "court.installation_binding.v2":
                errors.append(f"{name}:schema:{binding.get('schema')!r}")
            if not expected_fields.issubset(binding):
                errors.append(f"{name}:required_fields_missing")
            if binding.get("completion") != "PENDING_VALIDATION":
                errors.append(
                    f"{name}:completion_must_be_pending:{binding.get('completion')!r}"
                )
            if binding.get("canonical_root") != str(_agents_root(home).resolve(strict=False)):
                errors.append(f"{name}:canonical_root_mismatch")
            if binding.get("selected_roots") != [
                str(_agents_root(home).resolve(strict=False)),
                str(roots["codex"].resolve(strict=False)),
            ]:
                errors.append(f"{name}:selected_roots_mismatch")
            binding_path = binding_result.get("installation_binding_path")
            if not isinstance(binding_path, str) or not Path(binding_path).is_file():
                errors.append(f"{name}:binding_persistence_missing")
            else:
                install_receipt = binding_result.get("install_receipt")
                if (
                    not isinstance(install_receipt, dict)
                    or install_receipt.get("status") != "PENDING_VALIDATION"
                    or install_receipt.get("installation_binding") != binding
                ):
                    errors.append(f"{name}:install_receipt_binding_mismatch")
                commit_binding = install.__globals__["commit_installation_binding"]
                generic = commit_binding(
                    home_root=home,
                    external_validation={
                        "ok": True,
                        "status": "PASS",
                        "scope": "post_projection",
                        "receipt_ref": "external-check-a",
                    },
                )
                if (
                    isinstance(generic, dict) and generic.get("ok") is True
                ):
                    errors.append(f"{name}:generic_receipt_was_accepted:{generic}")
                else:
                    persisted_pending = json.loads(
                        Path(binding_path).read_text(encoding="utf-8")
                    )
                    if (
                        persisted_pending.get("completion") != "PENDING_VALIDATION"
                        or persisted_pending.get("provenance_receipt_ref")
                        != "candidate-receipt-a"
                    ):
                        errors.append(f"{name}:generic_receipt_changed_pending_binding")
                    producer_receipt: Payload = {
                        "schema": "court.active_copy_hashes.v2",
                        "ok": True,
                        "status": "PASS",
                        "contract": "POST_INSTALL_STANDALONE_HASH_CHECK",
                        "source": str(source),
                        "source_version": "beta1.0.1",
                        "projection": "shared_agents",
                        "root_contract": "RECEIPT_SELECTED_ROOTS",
                        "roots": list(binding["selected_roots"]),
                        "physical_authorities": list(binding["selected_roots"]),
                        "physical_authority_count": len(binding["selected_roots"]),
                        "checked_files": 1,
                        "missing_roots": [],
                        "drift": [],
                        "extra_files": [],
                        "unsafe_paths": [],
                        "forbidden_checker_copies": [],
                        "codex_agent_roles": {
                            "required": False,
                            "ok": True,
                            "status": "NOT_APPLICABLE",
                        },
                        "root_evidence": [],
                        "pending_body_access": "NO",
                        "projection_sha256": "external-projection-receipt",
                        "receipt_sha256": "external-receipt",
                    }
                    validation: Payload = {
                        "schema": "court.installation_acceptance.v1",
                        "producer_receipt": producer_receipt,
                        "candidate": {
                            "source_root": str(source),
                            "source_commit": binding["source_commit"],
                            "source_tree": "tree-a",
                            "release_label": binding["release_label"],
                            "artifact_ref": binding["artifact_ref"],
                            "build_id": binding["build_id"],
                            "candidate_receipt_ref": "candidate-receipt-a",
                        },
                        "binding": deepcopy(binding),
                        "post_projection_receipt_ref": str(
                            home
                            / ".agents"
                            / "install-receipts"
                            / "decretum-matrix"
                            / "post-validation-transaction-a.json"
                        ),
                    }
                    validation_path = Path(str(validation["post_projection_receipt_ref"]))
                    validation_path.parent.mkdir(parents=True, exist_ok=True)
                    validation_path.write_text(
                        json.dumps(validation, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    mismatched = deepcopy(validation)
                    mismatched["binding"]["transaction_id"] = "wrong-transaction"
                    mismatch_result = commit_binding(
                        home_root=home,
                        external_validation=mismatched,
                    )
                    if isinstance(mismatch_result, dict) and mismatch_result.get("ok") is True:
                        errors.append(f"{name}:mismatched_binding_was_accepted")
                    committed = commit_binding(
                        home_root=home,
                        external_validation=validation,
                    )
                    if (
                        not isinstance(committed, dict)
                        or committed.get("ok") is not True
                        or committed.get("status") != "COMMITTED"
                        or committed.get("post_projection_receipt_ref")
                        != str(validation_path)
                    ):
                        errors.append(f"{name}:external_acceptance_did_not_commit:{committed}")
                    else:
                        persisted_binding = json.loads(
                            Path(binding_path).read_text(encoding="utf-8")
                        )
                        if (
                            persisted_binding.get("completion") != "COMMITTED"
                            or persisted_binding.get("provenance_receipt_ref")
                            != "candidate-receipt-a"
                            or "court_code" in persisted_binding
                            or any(
                                key.endswith("sha256")
                                for key in persisted_binding
                            )
                        ):
                            errors.append(f"{name}:committed_binding_contract_failed")
                        replay = commit_binding(
                            home_root=home,
                            external_validation=validation,
                        )
                        if isinstance(replay, dict) and replay.get("ok") is True:
                            errors.append(f"{name}:external_acceptance_replayed")
    if len(errors) == before:
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


def _invoke_configuration_case(
    install: Installer,
    *,
    case_root: Path,
    name: str,
    tool_class: str,
    errors: list[str],
    **options: object,
) -> tuple[Payload | None, Payload | None, _ConfigFixture]:
    source, home = case_root / "source", case_root / "home"
    manifest = _write_fixture_source(source)
    roots = _canonical_tool_roots(home)
    _prime_roots(home, roots)
    write = options.pop("write", True)
    explicit_permission = options.pop("explicit_permission", True)
    has_controller = options.pop("has_controller", True)
    direct_authority = options.pop("direct_authority", False)
    adapter = _ConfigFixture(
        case_root, tool_class=tool_class, has_controller=has_controller, **options
    )
    request = {
        "schema": CONFIG_REQUEST_SCHEMA,
        "blank_host": True,
        "tool_class": adapter.tool_class,
        "normalized_semantic_delta": deepcopy(adapter.expected_delta),
        "newest_explicit_change_permission": explicit_permission,
        "direct_actual_file_change_authority": direct_authority,
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
            "effective_path": str(adapter.paths[0]),
            "source": adapter.hermes_path_source,
        }
    result, rejection = _invoke(
        install,
        source_root=source,
        home_root=home,
        current_tool=tool_class,
        explicit_tools=[],
        tool_roots=roots,
        projection_manifest=manifest,
        write=write,
        blank_host_configuration=request,
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
    config = result.get(CONFIG_RESULT_KEY)
    if not isinstance(config, dict):
        errors.append(f"{name}:{CONFIG_RESULT_KEY}_missing")
        config = None
    return result, config, adapter


def _require_config_fields(
    config: Payload,
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
    config: Payload,
    adapter: _ConfigFixture,
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
    adapter: _ConfigFixture,
    *,
    name: str,
    errors: list[str],
) -> None:
    if adapter.migration_attempts:
        errors.append(f"{name}:controller_database_migration_attempted")


def _require_reversibility(
    config: Payload,
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
    adapter: _ConfigFixture,
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
    for path in adapter.paths:
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


def _check_source_only_registry_gate(temp_root: Path, errors: list[str]) -> int:
    name = "source_only_cli_registry_gate"
    registry_path = ROOT / "scripts" / "court_cli_registry.py"
    spec = importlib.util.spec_from_file_location(
        "source_only_cli_registry_fixture",
        registry_path,
    )
    if spec is None or spec.loader is None:
        errors.append(f"{name}:module_spec_unavailable")
        return 0
    module = importlib.util.module_from_spec(spec)
    previous_module = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        errors.append(f"{name}:module_import_failed:{type(exc).__name__}:{exc}")
        if previous_module is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous_module
        return 0

    root = temp_root / "registry-root"
    manifest_path = root / "references" / "manifests" / "cli-command-surface.v1.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "public": True,
                        "group": "check",
                        "command": "fixture-check",
                        "legacy_path": "scripts/check_fixture.py",
                        "handler": "isolated_subprocess:scripts/check_fixture.py",
                        "side_effect": "read_only",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    module.ROOT = root
    module.MANIFEST_PATH = manifest_path

    missing_stdout, missing_stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(missing_stdout), redirect_stderr(missing_stderr):
        missing_rc = module._resolve_and_run(
            "check",
            "fixture-check",
            [],
            "json",
            invocation_cwd=root,
        )
    try:
        missing_payload = json.loads(missing_stdout.getvalue())
    except json.JSONDecodeError:
        missing_payload = {}

    handler = root / "scripts" / "check_fixture.py"
    handler.parent.mkdir(parents=True)
    handler.write_text("print('fixture check')\n", encoding="utf-8")
    (root / ".git").mkdir()
    directory_stdout, directory_stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(directory_stdout), redirect_stderr(directory_stderr):
        directory_rc = module._resolve_and_run(
            "check",
            "fixture-check",
            [],
            "text",
            invocation_cwd=root,
        )
    (root / ".git").rmdir()
    (root / ".git").write_text("gitdir: ../fixture-worktree\n", encoding="utf-8")
    worktree_stdout, worktree_stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(worktree_stdout), redirect_stderr(worktree_stderr):
        worktree_rc = module._resolve_and_run(
            "check",
            "fixture-check",
            [],
            "text",
            invocation_cwd=root,
        )

    checks = (
        missing_rc == 3,
        "source_checkout_required" in " ".join(
            str(item) for item in missing_payload.get("problems", [])
        ),
        directory_rc == 0,
        "source_checkout_required" not in directory_stderr.getvalue(),
        worktree_rc == 0,
        "source_checkout_required" not in worktree_stderr.getvalue(),
    )
    if not all(checks):
        errors.append(
            f"{name}:contract_failed:"
            f"missing={missing_stdout.getvalue()!r}:{missing_stderr.getvalue()!r};"
            f"directory={directory_rc}:{directory_stderr.getvalue()!r};"
            f"worktree={worktree_rc}:{worktree_stderr.getvalue()!r}"
        )
        return 0
    return 1


def _check_sanitized_cache_receipt_transaction(
    install: Installer,
    temp_root: Path,
    errors: list[str],
) -> int:
    name = "sanitized_cache_receipt_selected_transaction"
    try:
        from commands import sync_active_copies as sync_active
        from install_projection_renderer import render_active_projection
    except Exception as exc:
        errors.append(f"{name}:imports:{type(exc).__name__}:{exc}")
        return 0
    root = temp_root / _fixture_slug(name)
    cache, home = root / "npm-runtime", root / "home"
    local = home / "AppData" / "Local"
    try:
        rendered = {
            kind: render_active_projection(source_root=ROOT, target_class=kind)
            for kind in ("shared_agents", "portable_current_tool")
        }
        for value in rendered.values():
            for relative, payload in value.files.items():
                path = cache / Path(relative.as_posix())
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
        cache_manifest = cache / "references" / "manifests" / "install-projection.v1.json"
        cache_manifest.write_bytes(PROJECTION_MANIFEST_PATH.read_bytes())
        cache_manifest_value = json.loads(cache_manifest.read_text(encoding="utf-8"))
        roots = [
            home / ".agents" / "skills" / "decretum-matrix",
            home / ".codex" / "skills" / "decretum-matrix",
            local / "hermes" / "skills" / "decretum-matrix",
        ]
        old_manifest = json.loads(PROJECTION_MANIFEST_PATH.read_text(encoding="utf-8"))
        projections = old_manifest["projections"]
        assert isinstance(projections, dict)
        for projection_name in ("shared_agents", "portable_current_tool"):
            projection = projections[projection_name]
            assert isinstance(projection, list)
            projection.extend(
                (
                    A_B_ROOT_SOURCE_ONLY_CHECKER,
                    A_B_CHECKS_SOURCE_ONLY_CHECKER,
                )
            )
        old_manifest_bytes = (
            json.dumps(old_manifest, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        old_shell = b"OLD_FLAT_CACHE_SHELL = True\n"
        for index, target in enumerate(roots):
            source_files = rendered[
                "shared_agents" if index == 0 else "portable_current_tool"
            ].files
            for relative, payload in source_files.items():
                path = target / Path(relative.as_posix())
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            (
                target / "references" / "manifests" / "install-projection.v1.json"
            ).write_bytes(old_manifest_bytes)
            (target / A_B_ROOT_COMPATIBILITY_SHELL).write_bytes(old_shell)
            for relative in (
                A_B_ROOT_SOURCE_ONLY_CHECKER,
                A_B_CHECKS_SOURCE_ONLY_CHECKER,
            ):
                path = target / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("historical checker\n", encoding="utf-8")
            (target / "scripts" / "checks" / "user-owned.txt").write_text(
                "user-owned\n",
                encoding="utf-8",
            )
        receipt = {
            "selection_policy": "receipt",
            "primary_root": str(roots[0]),
            "current_tool": "codex",
            "current_tool_root": str(roots[1]),
            "current_tool_root_proof": "fixture",
            "status": "INSTALLED",
            "explicit_extra_targets": [str(roots[2])],
            "selected_roots": [str(path) for path in roots],
            "authority": "installer",
            "receipt_sha256": "fixture",
        }
        receipt_path = home / ".agents" / "install-receipts" / "decretum-matrix" / "install-fixture.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        binding_path = home / ".agents" / "install-receipts" / "decretum-matrix" / "installation-binding-v2.json"
        binding_path.write_text(
            json.dumps(
                {
                    "schema": "court.installation_binding.v2",
                    "source_commit": "fixture-commit",
                    "release_label": "fixture-release",
                    "artifact_ref": "fixture-artifact",
                    "build_id": "fixture-build",
                    "installation_id": "fixture-installation",
                    "generation": 1,
                    "canonical_root": str(roots[0]),
                    "selected_roots": [str(path) for path in roots],
                    "completion": "COMMITTED",
                    "provenance_receipt_ref": "fixture-provenance",
                    "transaction_id": "fixture-transaction",
                    "rollback_ref": "fixture-rollback",
                }
            ),
            encoding="utf-8",
        )
        environment = {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "LOCALAPPDATA": str(local),
            "APPDATA": str(home / "AppData" / "Roaming"),
            "XDG_DATA_HOME": str(local),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
        }
        output = io.StringIO()
        with mock.patch.dict(os.environ, environment, clear=False), mock.patch.object(
            sys,
            "argv",
            [
                "sync_active_copies.py",
                "--source",
                str(cache),
                "--write",
                "--prune-obsolete",
                "--json",
            ],
        ), redirect_stdout(output):
            returncode = sync_active.main()
        result = json.loads(output.getvalue())
        transaction = result.get("installer_transaction")
        backup = transaction.get("backup") if isinstance(transaction, dict) else None
        applied = (
            isinstance(cache_manifest_value.get("active_render"), dict)
            and not (cache / A_B_ROOT_SOURCE_ONLY_CHECKER).exists()
            and not (cache / A_B_CHECKS_SOURCE_ONLY_CHECKER).exists()
            and returncode == 0
            and result.get("ok") is True
            and isinstance(transaction, dict)
            and transaction.get("ok") is True
            and isinstance(backup, dict)
            and transaction.get("projection_counts", {}).get("delete")
            == len(roots) * 3
            and backup.get("delete_count") == len(roots) * 3
            and all(
                not (target / A_B_ROOT_COMPATIBILITY_SHELL).exists()
                and not (target / A_B_ROOT_SOURCE_ONLY_CHECKER).exists()
                and not (target / A_B_CHECKS_SOURCE_ONLY_CHECKER).exists()
                and (target / "scripts" / "checks" / "user-owned.txt").is_file()
                for target in roots
            )
        )
        rollback = (
            install.__globals__["rollback_install_backup"](
                home_root=home,
                backup_root=Path(str(backup.get("backup_root"))),
            )
            if isinstance(backup, dict) and backup.get("backup_root")
            else None
        )
        restored = (
            isinstance(rollback, dict)
            and rollback.get("ok") is True
            and all(
                (target / A_B_ROOT_COMPATIBILITY_SHELL).read_bytes() == old_shell
                and (target / A_B_ROOT_SOURCE_ONLY_CHECKER).is_file()
                and (target / A_B_CHECKS_SOURCE_ONLY_CHECKER).is_file()
                and (target / "scripts" / "checks" / "user-owned.txt").is_file()
                for target in roots
            )
        )
    except Exception as exc:
        errors.append(f"{name}:unexpected_error:{type(exc).__name__}:{exc}")
        return 0
    if not applied or not restored:
        errors.append(f"{name}:contract_failed:{result}:{rollback}")
        return 0
    return 1


def _check_blank_host_configuration_cases(
    install: Installer,
    temp_root: Path,
    errors: list[str],
) -> int:
    passed = 0

    def fail(condition: object, detail: str) -> None:
        if condition:
            errors.append(f"{name}:{detail}")

    @contextmanager
    def run_case(
        case_name: str,
        tool_class: str = "codex",
        *,
        status: str | None = None,
        probe: bool | None = None,
        unchanged: tuple[str, str] | None = None,
        check_migration: bool = True,
        **options: object,
    ):
        nonlocal passed
        before = len(errors)
        result, config, adapter = _invoke_configuration_case(
            install,
            case_root=temp_root / _fixture_slug(case_name),
            name=case_name,
            tool_class=tool_class,
            errors=errors,
            **options,
        )
        if config is not None:
            if status is not None:
                _require_config_fields(
                    config, name=case_name, tool_class=tool_class, errors=errors
                )
                if config.get("status") != status:
                    errors.append(
                        f"{case_name}:status:{config.get('status')!r}"
                    )
            if probe is not None:
                _require_controller_probe_contract(
                    config,
                    adapter,
                    name=case_name,
                    expected_compatible=probe,
                    errors=errors,
                )
        yield result, config, adapter
        if unchanged is not None:
            mutation_label, surface_label = unchanged
            if adapter.mutation_events:
                errors.append(
                    f"{case_name}:{mutation_label}:{adapter.mutation_events!r}"
                )
            if adapter.surface_snapshot() != adapter.initial_snapshot:
                errors.append(f"{case_name}:{surface_label}")
        if check_migration:
            _require_no_controller_migration(adapter, name=case_name, errors=errors)
        passed += len(errors) == before

    for tool_class in CANONICAL_TOOL_CLASSES:
        name = f"reminder_plan_{tool_class.replace(':', '_')}"
        with run_case(
            name,
            tool_class,
            status="REMINDER_ONLY",
            unchanged=("planner_mutated", "planner_changed_fixture_surfaces"),
            write=False,
            explicit_permission=False,
        ) as (result, config, adapter):
            expected_gaps = adapter.expected_gaps()
            fail(result is not None and result.get("ok") is not True, "planner_blocked_install_contract")
            if config is not None:
                fail(config.get("gaps") != expected_gaps, f"gaps_not_exact:{config.get('gaps')!r}")
                fail(config.get("evidence") != adapter.expected_evidence(), f"evidence_not_exact:{config.get('evidence')!r}")
                for field in (
                    "standard_requirements_met",
                    "compliance_claimed",
                    "mutation_authorized",
                    "unrelated_install_blocked",
                    "unrelated_task_blocked",
                ):
                    fail(config.get(field) is not False, f"{field}_must_be_false")

    name = "reminder_execute_does_not_block_install_or_task"
    with run_case(
        name,
        status="REMINDER_ONLY",
        unchanged=("configuration_writes", "configuration_surface_changed"),
        explicit_permission=False,
    ) as (result, config, _adapter):
        fail(result is not None and result.get("ok") is not True, "unrelated_install_reported_failed")
        if config is not None:
            fail(config.get("compliance_claimed") is not False, "claimed_compliant")
            fail(config.get("unrelated_install_blocked") is not False, "install_blocked")
            fail(config.get("unrelated_task_blocked") is not False, "task_blocked")
        _assert_projection(_agents_root(temp_root / _fixture_slug(name) / "home"), name=name, errors=errors)

    name = "cc_switch_3_16_5_user_version_11_is_supported"
    with run_case(
        name,
        status="PASSED",
        probe=True,
        controller_materializes=True,
        controller_version="3.16.5",
        controller_user_version=11,
        controller_schema_complete=False,
    ) as (_result, _config, adapter):
        _require_actual_files_verified(
            adapter,
            name=name,
            after_event="commit_controller_transaction:codex",
            errors=errors,
        )

    fail_closed_cases = [
        (
            f"uncertain_{uncertainty}_changes_nothing",
            {"uncertainty": uncertainty},
            uncertainty,
            ("uncertainty_not_explained", "explanation_missing"),
            None,
        )
        for uncertainty in UNCERTAINTY_KINDS
    ] + [
        (name, {
            "controller_version": version,
            "controller_user_version": user_version,
            "controller_schema_complete": schema_complete,
        }, None, (
            "compatibility_uncertainty_missing",
            "compatibility_explanation_missing",
        ), False)
        for name, version, user_version, schema_complete in (
            ("cc_switch_3_16_5_user_version_13_mismatch", "3.16.5", 13, False),
            ("cc_switch_3_17_0_user_version_11_mismatch", "3.17.0", 11, True),
            ("cc_switch_3_17_9_user_version_14_mismatch", "3.17.9", 14, True),
            ("cc_switch_unknown_3_18_0_fails_closed", "3.18.0", 13, True),
            ("cc_switch_3_17_0_missing_v13_schema_fails_closed", "3.17.0", 13, False),
        )
    ]
    for name, options, reason, labels, probe in fail_closed_cases:
        with run_case(
            name,
            status="NO_CHANGE_UNCERTAIN",
            probe=probe,
            unchanged=("mutated", "surface_changed"),
            **options,
        ) as (_result, config, adapter):
            reason = reason or adapter._controller_compatibility()[1]
            if config is not None:
                fail(config.get("compliance_claimed") is not False, "claimed_compliant")
                for field, label in zip(("uncertainty", "explanation"), labels):
                    fail(reason not in str(config.get(field)), label)

    name = "codex_controller_first_then_effective_files_verified"
    with run_case(
        name,
        status="PASSED",
        probe=True,
        controller_materializes=True,
    ) as (_result, config, adapter):
        if config is not None:
            _require_reversibility(config, name=name, errors=errors)
            fail(config.get("standard_requirements_met") is not True, "standard_not_met")
            fail(config.get("semantic_delta_verified") is not True, "semantic_delta_not_verified")
            fail(
                config.get("mutation_path") != "cc_switch_upstream_then_effective_files",
                f"mutation_path:{config.get('mutation_path')!r}",
            )
        expected_order = [
            "backup_controller_database:codex",
            "begin_controller_transaction:codex",
            "update_controller_tool_block:codex",
            "commit_controller_transaction:codex",
        ]
        positions = [adapter.events.index(item) for item in expected_order if item in adapter.events]
        fail(len(positions) != len(expected_order) or positions != sorted(positions), f"controller_transaction_order:{adapter.events!r}")
        fail(adapter.direct_deltas, f"leaf_only_write_attempted:{adapter.direct_deltas!r}")
        fail(adapter.controller_deltas != [CODEX_NORMALIZED_SEMANTIC_DELTA], f"controller_delta:{adapter.controller_deltas!r}")
        _require_actual_files_verified(adapter, name=name, after_event="commit_controller_transaction:codex", errors=errors)
        initial_projection = {
            path.name: _without_delta_fields(adapter.initial_parsed[path], adapter.expected_delta)
            for path in adapter.paths
        }
        fail(adapter.non_delta_projection() != initial_projection, "secret_provider_or_unknown_key_changed")
        fail(adapter.expected_gaps(), "actual_effective_files_noncompliant")
        fail(adapter.paths[0].read_bytes() == adapter.paths[1].read_bytes(), "overlays_were_forced_byte_identical")
        controller_fixture = json.loads(adapter.controller_path.read_text(encoding="utf-8"))
        fail(any(key.startswith("current_profile_id_") for key in controller_fixture["settings"]), "optional_current_profile_setting_was_required")

    name = "codex_db_receipt_without_materialization_rolls_back"
    with run_case(
        name,
        probe=True,
        controller_materializes=False,
    ) as (_result, config, adapter):
        if config is not None:
            fail(config.get("status") == "PASSED" or config.get("compliance_claimed") is True, "db_receipt_claimed_success")
        fail(bool(adapter.direct_deltas), f"leaf_only_fallback_used:{adapter.direct_deltas!r}")
        fail("rollback_controller_transaction:codex" not in adapter.events, "controller_rollback_missing")
        fail(adapter.surface_snapshot() != adapter.initial_snapshot, "rollback_did_not_restore_surfaces")

    name = "codex_without_controller_dual_file_transaction"
    with run_case(
        name,
        status="PASSED",
        check_migration=False,
        has_controller=False,
    ) as (_result, config, adapter):
        if config is not None:
            _require_reversibility(config, name=name, errors=errors)
            fail(config.get("mutation_path") != "direct_reversible_effective_files", f"mutation_path:{config.get('mutation_path')!r}")
        fail([item[0] for item in adapter.direct_deltas] != ["config.toml", "managed_config.toml"], f"dual_file_delta_missing:{adapter.direct_deltas!r}")
        fail(any(delta != CODEX_NORMALIZED_SEMANTIC_DELTA for _, delta in adapter.direct_deltas), "normalized_delta_drift")
        _require_actual_files_verified(adapter, name=name, after_event="commit_effective_files_transaction:codex", errors=errors)
        fail(bool(adapter.expected_gaps()), "dual_file_result_noncompliant")
        fail(adapter.paths[0].read_bytes() == adapter.paths[1].read_bytes(), "dual_toml_files_were_forced_byte_identical")

    name = "codex_dual_file_failure_rolls_back_atomically"
    with run_case(
        name,
        check_migration=False,
        has_controller=False,
        fail_direct_write_number=2,
    ) as (_result, config, adapter):
        fail(config is not None and (config.get("status") == "PASSED" or config.get("compliance_claimed") is True), "partial_write_claimed_success")
        fail("rollback_effective_files_transaction:codex" not in adapter.events, "rollback_missing")
        fail(adapter.surface_snapshot() != adapter.initial_snapshot, "rollback_did_not_restore_both_files")

    for direct_authority in (False, True):
        suffix = "authorized" if direct_authority else "unauthorized"
        name = f"hermes_controller_nonmaterialization_{suffix}_fallback"
        with run_case(
            name,
            "hermes",
            status="PASSED" if direct_authority else None,
            controller_materializes=False,
            direct_authority=direct_authority,
        ) as (_result, config, adapter):
            if not direct_authority:
                fail(config is not None and (config.get("status") == "PASSED" or config.get("compliance_claimed") is True), "claimed_success")
                fail(bool(adapter.direct_deltas), "unauthorized_direct_fallback")
                fail(adapter.surface_snapshot() != adapter.initial_snapshot, "unauthorized_surface_change")
            else:
                if config is not None:
                    _require_reversibility(config, name=name, errors=errors)
                fail(not adapter.direct_deltas, "authorized_fallback_not_used")
                controller_index = adapter.events.index("update_controller_tool_block:hermes") if "update_controller_tool_block:hermes" in adapter.events else -1
                direct_events = [
                    index for index, event in enumerate(adapter.events)
                    if event.startswith("write_effective_config:hermes:")
                ]
                fail(controller_index < 0 or not direct_events or controller_index >= direct_events[0], "fallback_not_controller_first")
                fail(bool(adapter.expected_gaps()), "fallback_not_effective")
                _require_actual_files_verified(adapter, name=name, after_event="commit_effective_files_transaction:hermes", errors=errors)

    hermes_path_cases = (
        (
            "explicit_override", "Windows", "override",
            (("HERMES_HOME", "ignored-hermes-home"), ("LOCALAPPDATA", "ignored-localappdata")),
            "override/config.yaml", "ccs_hermes_config_dir_override",
        ),
        (
            "hermes_home", "Windows", None,
            (("HERMES_HOME", "hermes-home"), ("LOCALAPPDATA", "ignored-localappdata")),
            "hermes-home/config.yaml", "HERMES_HOME",
        ),
        (
            "windows_localappdata", "Windows", None,
            (("LOCALAPPDATA", "localappdata"),),
            "localappdata/hermes/config.yaml", "LOCALAPPDATA",
        ),
        (
            "windows_home_localappdata_fallback", "Windows", None, (),
            "home/AppData/Local/hermes/config.yaml", "windows_home_localappdata_fallback",
        ),
        (
            "darwin_posix_home_default", "Darwin", None, (),
            "home/.hermes/config.yaml", "posix_home_default",
        ),
    )
    for path_case, platform_system, override, environment_rows, expected_relative, expected_source in hermes_path_cases:
        name = f"hermes_config_path_{path_case}"
        case_root = temp_root / _fixture_slug(name)
        home = case_root / "home"
        environment = {key: case_root / suffix for key, suffix in environment_rows}
        explicit_config_dir = case_root / override if override else None
        expected = (case_root / expected_relative).resolve(strict=False)
        with run_case(
            name,
            "hermes",
            status="REMINDER_ONLY",
            unchanged=("planner_mutated", "planner_changed_fixture_surfaces"),
            write=False,
            explicit_permission=False,
            has_controller=False,
            hermes_platform_system=platform_system,
            hermes_environment=environment,
            hermes_config_dir_override=explicit_config_dir,
        ) as (_result, config, adapter):
            fail(len(adapter.paths) != 1 or not _same_filesystem_path(adapter.paths[0], expected), f"effective_path:{adapter.paths!r}!={[expected]!r}")
            fail(adapter.hermes_path_source != expected_source, f"path_source:{adapter.hermes_path_source!r}!={expected_source!r}")
            fail(platform_system == "Windows" and adapter.paths == [(home / ".hermes" / "config.yaml").resolve(strict=False)], "windows_defaulted_to_dot_hermes")
            if config is not None:
                effective_files = config.get("effective_files")
                fail(
                    not isinstance(effective_files, list)
                    or not any(isinstance(item, (str, Path)) and _same_filesystem_path(Path(item), expected) for item in effective_files),
                    "effective_file_evidence_missing",
                )
            fail("list_effective_files:hermes" not in adapter.events, "adapter_path_fixture_not_used")

    for failure_step in DIRECT_FAILURE_STEPS:
        name = f"hermes_direct_fallback_{failure_step}_failure_rolls_back"
        with run_case(
            name,
            "hermes",
            controller_materializes=False,
            direct_authority=True,
            fail_direct_step=failure_step,
        ) as (_result, config, adapter):
            fail(config is not None and (config.get("status") == "PASSED" or config.get("compliance_claimed") is True), "step_failure_claimed_success")
            controller_event = "update_controller_tool_block:hermes"
            failure_events = [
                index for index, event in enumerate(adapter.events)
                if event.startswith(f"{failure_step}:hermes")
            ]
            missing_event = controller_event not in adapter.events or not failure_events
            fail(missing_event, "controller_or_failure_step_missing")
            fail(not missing_event and adapter.events.index(controller_event) >= failure_events[0], "direct_failure_not_after_controller_first")
            fail(
                failure_step in {"write_effective_config", "commit_effective_files_transaction"}
                and "rollback_effective_files_transaction:hermes" not in adapter.events,
                "effective_rollback_missing",
            )
            fail(adapter.surface_snapshot() != adapter.initial_snapshot, "failure_did_not_restore_all_surfaces")

    return passed


def evaluate() -> Payload:
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
        with tempfile.TemporaryDirectory(prefix='court-batch-retirement-') as tmp:
            root = Path(tmp)
            selected = [('fixture', root, 'shared_agents')]
            operations = [(root / 'scripts/checks' / name, None, b'old source checker\n')
                          for name in ('check_one.py', 'check_two.py')]
            for path, _, previous in operations:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(previous)
            try:
                applied = module._apply_projection_writes(operations, selected)
                assert not (root / 'scripts/checks').exists()
                module._rollback_projection_writes(applied, selected)
                assert all(path.read_bytes() == previous for path, _, previous in operations)
            except Exception as exc:
                errors.append('multi_file_empty_directory_retirement:' + str(exc))
    if module is not None:
        target = getattr(module, "install_current_agent_copy", None)
        if not callable(target):
            errors.append("missing_callable:install_current_agent_copy")
            errors.extend(INSTALL_UNEXERCISED_GAPS)
            errors.extend(CONFIG_UNEXERCISED_GAPS)
        else:
            with tempfile.TemporaryDirectory(
                prefix="ctr-"
            ) as temp_dir:
                passed = _check_cases(target, Path(temp_dir), errors)
            with tempfile.TemporaryDirectory(
                prefix="ctg-"
            ) as temp_dir:
                passed += _check_source_only_registry_gate(
                    Path(temp_dir),
                    errors,
                )
            with tempfile.TemporaryDirectory(
                prefix="cts-"
            ) as temp_dir:
                passed += _check_sanitized_cache_receipt_transaction(
                    target,
                    Path(temp_dir),
                    errors,
                )
            with tempfile.TemporaryDirectory(
                prefix="cpc-"
            ) as temp_dir:
                passed += _check_candidate_binding_provenance_cases(
                    Path(temp_dir),
                    errors,
                )
            with tempfile.TemporaryDirectory(
                prefix="cfc-"
            ) as temp_dir:
                passed += _check_fix_role_failure_compensation(
                    Path(temp_dir),
                    errors,
                )
            with tempfile.TemporaryDirectory(
                prefix="csa-"
            ) as temp_dir:
                passed += _check_one_shot_post_projection_acceptance(
                    Path(temp_dir),
                    errors,
                )
            with tempfile.TemporaryDirectory(
                prefix="cnf-"
            ) as temp_dir:
                passed += _check_candidate_npm_failure_compensation(
                    Path(temp_dir),
                    errors,
                )
            with tempfile.TemporaryDirectory(
                prefix="cnp-"
            ) as temp_dir:
                passed += _check_candidate_npm_partial_failure_compensation(
                    Path(temp_dir),
                    errors,
                )
            with tempfile.TemporaryDirectory(
                prefix="cnm-"
            ) as temp_dir:
                passed += _check_candidate_npm_partial_attempt_metadata(
                    Path(temp_dir),
                    errors,
                )
            with tempfile.TemporaryDirectory(
                prefix="cnr-"
            ) as temp_dir:
                passed += _check_candidate_npm_replace_existing_relative_backup(
                    Path(temp_dir),
                    errors,
                )
            passed += runpy.run_path(str(ROOT / ".github/test-support/candidate-install-regression.py"))["verify"](errors)
            with tempfile.TemporaryDirectory(
                prefix="cps-"
            ) as temp_dir:
                passed += _check_candidate_public_shim_mismatch(
                    Path(temp_dir),
                    errors,
                )
            with tempfile.TemporaryDirectory(
                prefix="cbr-"
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
        "declared_cases": 57,
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
        "protected_shiguan_data_accessed": False,
        "pending_body_accessed": False,
        "errors": errors,
    }


def main() -> int:
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
