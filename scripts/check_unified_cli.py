#!/usr/bin/env python3
"""Validate the versioned unified CLI inventory, registry, and compatibility surface."""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from typing import Iterable, Mapping

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "references" / "manifests" / "cli-command-surface.v1.json"
INSTALL_PROJECTION_PATH = ROOT / "references" / "manifests" / "install-projection.v1.json"
MANIFEST_SCHEMA = "decretum.cli_command_surface.v1"
ENTRY_FIELDS = {
    "id",
    "domain",
    "legacy_path",
    "handler",
    "public",
    "side_effect",
    "authority_source",
    "receipt_schema",
    "compatibility_state",
    "group",
    "command",
}
REGISTRY_FIELDS = {
    "group",
    "command",
    "loader",
    "side_effect",
    "authority_requirement",
}
SCRIPT_SUFFIXES = {".py", ".mjs", ".js", ".ps1", ".sh", ".cmd"}
PUBLIC_GROUPS = ("court", "office", "shiguan", "supercc", "install", "release", "check")
MIN_PUBLIC_COMPATIBILITY_ENTRIES = 100
EXPECTED_MANIFEST_PUBLIC_GROUPS = frozenset(PUBLIC_GROUPS)
NON_PUBLIC_ENTRYPOINTS = frozenset(
    {
        "scripts/build_npm_package.mjs",
        "scripts/check_npm_package.mjs",
        "scripts/court_mcp_server.py",
        "scripts/install_codex_plugin_projection.py",
        "scripts/memory_pipeline_fixture.py",
        "scripts/check_doctor_debug_fix.py",
    }
)
CLI_SUPPORT_FILES = frozenset(
    {
        "AUTHORS.md",
        "CLA.md",
        "COMMERCIAL-LICENSE.md",
        "CONTRIBUTING.md",
        "PRIVACY.md",
        "PROVENANCE.md",
        "SBOM.spdx.json",
        "SECURITY.md",
        "THIRD_PARTY_NOTICES.md",
        "TRADEMARKS.md",
        "assets/brand",
        "references/manifests/direct-review-governance.v1.json",
        "references/manifests/github-release-metadata.v1.json",
        "references/manifests/release-gates.v1.json",
        "references/manifests/source-state-budget.v1.json",
        "release-manifest.json",
        "scripts/check_court_native_host_dispatch.py",
        "scripts/check_shiguan_git_federation.py",
        "scripts/codex_runtime_probe_support.py",
        "scripts/court_outcome_gate.py",
        "scripts/court_result_semantics.py",
        "scripts/memory_pipeline_fixture.py",
        "scripts/release_gate_manifest.py",
        "scripts/shiguan_host_memory_projection.py",
        "scripts/shiguan_pending_trust.py",
        "scripts/court_diagnostics.py",
    }
)
BOOTSTRAP_ENTRYPOINTS = (
    PurePosixPath("scripts/check_unified_cli.py"),
    PurePosixPath("scripts/court_open_fastpath.py"),
    PurePosixPath("scripts/check_court_open_fastpath.py"),
    PurePosixPath("scripts/court_session_closeout.py"),
    PurePosixPath("scripts/check_court_session_closeout.py"),
)
# These source-only maintenance tools deliberately have no public compatibility
# adapter. They remain callable by their owning maintenance workflow.
RETIRED_COMPATIBILITY_ENTRYPOINTS = frozenset(
    {
        "scripts/check_active_copy_hashes.py",
        "scripts/check_cli_cwd_invariance.py",
        "scripts/check_court_native_host_dispatch.py",
        "scripts/check_install_projection_closure.py",
        "scripts/check_runtime_identity_contract.py",
        "scripts/check_shiguan_lineage_rebuild_compatibility.py",
        "scripts/check_shiguan_lineage_taxonomy.py",
        "scripts/check_shiguan_git_federation.py",
        "scripts/ensure_shiguan_autosync.py",
        "scripts/ensure_shiguan_service_daemon.py",
        "scripts/ensure_shiguan_web.py",
        "scripts/export_shiguan_obsidian.py",
        "scripts/serve_shiguan_tree.py",
        "scripts/shiguan_git_federation.py",
        "scripts/shiguan_service_daemon.py",
        "scripts/sync_shiguan_obsidian_vault.py",
    }
)

# A+B layering: root-level compatibility shells (and retired real modules that
# moved into scripts/{checks,commands,services}) must not be discovered as
# second entrypoints; the canonical module under scripts/<layer>/ is the
# registered command.
COMPATIBILITY_SHELL_ENTRYPOINTS = frozenset(
    {
        "scripts/check_shiguan_recall_precision.py",
        "scripts/query_shiguan_index.py",
        "scripts/services/serve_shiguan_tree.py",
    }
)
VOLATILE_RECEIPT_FIELDS = {
    "created_at",
    "generated_at",
    "timestamp",
    "time",
}


def _domain_for(path: str) -> str:
    name = PurePosixPath(path).stem.lower()
    if (
        name.startswith(("check_", "probe_"))
        or name.endswith("_fixture")
        or name == "quick_validate"
    ):
        return "check"
    if "shiguan" in name or "obsidian" in name or name in {
        "archive_checkpoint",
        "archive_runtime_task",
        "memory_decision",
        "reevaluate_memory_decisions",
        "repair_archive_placeholders",
        "closeout_conflict_scan",
        "court_session_numbering",
        "iku_candidates",
    }:
        return "shiguan"
    if "supercc" in name or name.startswith("supercc-"):
        return "supercc"
    if name.startswith(("build_release", "release_", "package_", "build_npm")):
        return "release"
    if name.startswith(("install_", "migrate_", "sync_active_copies")) or name in {
        "fix_decretum_matrix",
        "ensure_codex_yolo_startup_task",
        "ensure_portable_court_bootstrap",
        "refresh_capability_registry",
    }:
        return "install"
    if "agent" in name or "office" in name:
        return "office"
    if name.startswith("court_") or name == "court_cli":
        return "court"
    return "dev"


def _side_effect_for(path: str) -> str:
    name = PurePosixPath(path).stem.lower()
    if name.startswith(("check_", "probe_", "query_", "report_")) or name.endswith("_probe"):
        return "read_only"
    if name in {"quick_validate", "court_cli", "court_runtime"}:
        return "request_dependent"
    return "bounded_mutation"


def _manifest_entry(path: str) -> dict[str, object]:
    pure = PurePosixPath(path)
    stem = pure.stem
    domain = _domain_for(path)
    is_root = path == "scripts/court_cli.py"
    direct_module = path in {
        "scripts/archive_checkpoint.py",
        "scripts/court_cli.py",
        "scripts/court_runtime.py",
        "scripts/court_session_closeout.py",
    }
    entry_name = stem.replace("_", "-").lower()
    if path == "scripts/court_session_closeout.py":
        entry_name = "closeout-session"
    elif path == "scripts/check_doctor.py":
        entry_name = "doctor"
    elif path == "scripts/check_debug.py":
        entry_name = "debug"
    elif path == "scripts/fix_decretum_matrix.py":
        entry_name = "fix"
    elif path == "scripts/check_doctor.py":
        entry_name = "doctor"
    elif path == "scripts/check_debug.py":
        entry_name = "debug"
    elif path == "scripts/fix_decretum_matrix.py":
        entry_name = "fix"
    if pure.suffix.lower() != ".py":
        entry_name = f"{entry_name}-{pure.suffix.lower().lstrip('.')}"
    public = path not in NON_PUBLIC_ENTRYPOINTS
    return {
        "id": f"{domain}.{entry_name}",
        "domain": domain,
        "legacy_path": path,
        "handler": (
            f"python_module:{stem}"
            if direct_module
            else f"isolated_subprocess:{path}"
        ),
        "public": public,
        "side_effect": _side_effect_for(path),
        "authority_source": "court_runtime" if path == "scripts/court_runtime.py" else path,
        "receipt_schema": (
            "decretum.cli.result.v1"
            if is_root
            else "court.session_closeout.receipt.v1"
            if path == "scripts/court_session_closeout.py"
            else "court.shiguan_archive_checkpoint_receipt.v1"
            if path == "scripts/archive_checkpoint.py"
            else "legacy.entrypoint.result.v1"
        ),
        "compatibility_state": (
            "canonical_public_root"
            if is_root
            else "unified_compatibility_adapter"
            if public
            else "source_only_entrypoint"
        ),
        "group": "root" if is_root else domain,
        "command": "decretum-matrix" if is_root else entry_name,
    }


def _tracked_script_paths() -> list[PurePosixPath]:
    completed = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "ls-files",
            "--cached",
            "--",
            "scripts",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"git inventory failed: {completed.stderr.strip()}")
    paths = {
        PurePosixPath(line.strip().replace("\\", "/"))
        for line in completed.stdout.splitlines()
        if line.strip()
    }
    # These explicitly named plan outputs must be testable before the final commit
    # without scanning any other untracked path.
    for relative in BOOTSTRAP_ENTRYPOINTS:
        if ROOT.joinpath(*relative.parts).is_file():
            paths.add(relative)
    return sorted(paths, key=str)


def _is_python_entrypoint(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            continue
        operands = [test.left, *test.comparators]
        names = {operand.id for operand in operands if isinstance(operand, ast.Name)}
        values = {
            operand.value
            for operand in operands
            if isinstance(operand, ast.Constant) and isinstance(operand.value, str)
        }
        if "__name__" in names and "__main__" in values:
            return True
    return False


def discover_executable_entrypoints() -> list[str]:
    entrypoints: list[str] = []
    for relative in _tracked_script_paths():
        if str(relative) in RETIRED_COMPATIBILITY_ENTRYPOINTS:
            continue
        if str(relative) in COMPATIBILITY_SHELL_ENTRYPOINTS:
            continue
        if relative.suffix.lower() not in SCRIPT_SUFFIXES:
            continue
        path = ROOT.joinpath(*relative.parts)
        if relative.suffix.lower() == ".py" and not _is_python_entrypoint(path):
            continue
        entrypoints.append(str(relative))
    return sorted(entrypoints)


def write_manifest() -> dict[str, object]:
    existing_projections: dict[str, object] = {}
    try:
        existing = _load_manifest()
    except (OSError, UnicodeError, json.JSONDecodeError, AssertionError):
        existing = None
    if isinstance(existing, dict) and isinstance(existing.get("entries"), list):
        existing_projections = {
            str(entry.get("id")): entry.get("mcp")
            for entry in existing["entries"]
            if isinstance(entry, dict) and entry.get("mcp") is not None
        }
    entries = [_manifest_entry(path) for path in discover_executable_entrypoints()]
    for entry in entries:
        projection = existing_projections.get(str(entry.get("id")))
        if projection is not None:
            entry["mcp"] = projection
    manifest: dict[str, object] = {
        "schema": MANIFEST_SCHEMA,
        "public_command": "decretum-matrix",
        "source_entry": "python -B scripts/court_cli.py",
        "generated_by": "scripts/check_unified_cli.py --write-manifest",
        "groups": list(PUBLIC_GROUPS),
        "entries": entries,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _write_cli_public_projection(entries)
    return manifest


def _write_cli_public_projection(entries: list[dict[str, object]]) -> None:
    value = json.loads(INSTALL_PROJECTION_PATH.read_text(encoding="utf-8"))
    projections = value.get("projections")
    if not isinstance(projections, dict):
        raise AssertionError("install projection entries unavailable")
    public_paths = sorted(
        {
            str(entry.get("legacy_path") or "")
            for entry in entries
            if entry.get("public") is True and entry.get("group") != "root"
        }
        - {""}
    )
    cli_projection = sorted(set(public_paths) | CLI_SUPPORT_FILES)
    projections["cli_public"] = cli_projection
    repository_only = projections.get("repository_only")
    if not isinstance(repository_only, list):
        raise AssertionError("install projection repository_only invalid")
    projections["repository_only"] = [
        item for item in repository_only if item not in set(cli_projection)
    ]
    INSTALL_PROJECTION_PATH.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _load_manifest() -> dict[str, object] | None:
    if not MANIFEST_PATH.is_file():
        return None
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError("CLI manifest root must be an object")
    return value


def _runtime_projection_paths() -> set[str]:
    value = json.loads(INSTALL_PROJECTION_PATH.read_text(encoding="utf-8"))
    projections = value.get("projections")
    if not isinstance(projections, dict):
        raise AssertionError("install projection entries unavailable")
    selected: list[set[str]] = []
    for name in ("shared_agents", "portable_current_tool"):
        raw = projections.get(name)
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            raise AssertionError(f"install projection {name} invalid")
        selected.append(set(raw))
    cli_public = projections.get("cli_public")
    if not isinstance(cli_public, list) or any(not isinstance(item, str) for item in cli_public):
        raise AssertionError("install projection cli_public invalid")
    return set.intersection(*selected) | set(cli_public)


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def evaluate_inventory() -> dict[str, object]:
    discovered = discover_executable_entrypoints()
    manifest = _load_manifest()
    problems: list[str] = []
    entries: list[dict[str, object]] = []
    missing: list[str] = []
    extra: list[str] = []
    duplicate_ids: list[str] = []
    duplicate_public: list[str] = []
    missing_groups: list[str] = []
    invalid_groups: list[str] = []
    public_not_projected: list[str] = []
    public_classification_drift: list[str] = []
    public_count = 0
    if manifest is None:
        missing = discovered
        problems.append("manifest_missing")
    else:
        if manifest.get("schema") != MANIFEST_SCHEMA:
            problems.append("manifest_schema_invalid")
        raw_entries = manifest.get("entries")
        if not isinstance(raw_entries, list):
            problems.append("manifest_entries_invalid")
            raw_entries = []
        for index, raw_entry in enumerate(raw_entries):
            if not isinstance(raw_entry, dict):
                problems.append(f"entry_not_object:{index}")
                continue
            entries.append(raw_entry)
            absent = sorted(ENTRY_FIELDS - set(raw_entry))
            if absent:
                problems.append(f"entry_fields_missing:{index}:{','.join(absent)}")
        manifest_paths = [
            str(entry.get("legacy_path") or "")
            for entry in entries
            if entry.get("legacy_path")
        ]
        missing = sorted(set(discovered) - set(manifest_paths))
        extra = sorted(set(manifest_paths) - set(discovered))
        if missing:
            problems.append("entrypoints_missing")
        if extra:
            problems.append("entrypoints_stale")
        duplicate_ids = _duplicates(str(entry.get("id") or "") for entry in entries)
        duplicate_paths = _duplicates(manifest_paths)
        public_tuples = [
            f"{entry.get('group')}\0{entry.get('command')}"
            for entry in entries
            if entry.get("public") is True
        ]
        duplicate_public = [value.replace("\0", " ") for value in _duplicates(public_tuples)]
        if duplicate_ids:
            problems.append("duplicate_entry_ids")
        if duplicate_paths:
            problems.append("duplicate_legacy_paths")
        if duplicate_public:
            problems.append("duplicate_public_commands")
        public_entries = [entry for entry in entries if entry.get("public") is True]
        public_count = len(public_entries)
        expected_public = {
            path: _manifest_entry(path).get("public") is True
            for path in discovered
        }
        public_classification_drift = sorted(
            path
            for path, expected in expected_public.items()
            if next(
                (
                    entry.get("public") is True
                    for entry in entries
                    if entry.get("legacy_path") == path
                ),
                None,
            )
            != expected
        )
        if public_classification_drift:
            problems.append("public_classification_drift")
        if public_count < MIN_PUBLIC_COMPATIBILITY_ENTRIES:
            problems.append(
                f"public_compatibility_surface_contracted:{public_count}"
            )
        try:
            runtime_projection = _runtime_projection_paths()
        except (OSError, UnicodeError, json.JSONDecodeError, AssertionError) as exc:
            problems.append(f"runtime_projection_unavailable:{type(exc).__name__}:{exc}")
            runtime_projection = set()
        public_not_projected = sorted(
            str(entry.get("legacy_path") or "")
            for entry in public_entries
            if entry.get("group") != "root"
            and str(entry.get("legacy_path") or "") not in runtime_projection
        )
        if public_not_projected:
            problems.append("public_entrypoints_not_in_runtime_projection")
        groups = {
            str(entry.get("group") or "")
            for entry in entries
            if entry.get("public") is True and entry.get("group") != "root"
        }
        missing_groups = sorted(EXPECTED_MANIFEST_PUBLIC_GROUPS - groups)
        if missing_groups:
            problems.append("public_groups_missing")
        invalid_groups = sorted(groups - set(PUBLIC_GROUPS))
        if invalid_groups:
            problems.append("public_groups_invalid")
    return {
        "schema": "decretum.cli_inventory_check.v1",
        "ok": not problems,
        "status": "PASS" if not problems else "FAIL",
        "CLI_ENTRYPOINT_COVERAGE": "PASS" if not problems else "FAIL",
        "manifest": str(MANIFEST_PATH.relative_to(ROOT)).replace("\\", "/"),
        "discovered_count": len(discovered),
        "registered_count": len(entries),
        "public_count": public_count,
        "public_minimum": MIN_PUBLIC_COMPATIBILITY_ENTRIES,
        "public_classification_drift": public_classification_drift,
        "source_only_count": len(entries) - public_count,
        "public_not_projected": public_not_projected,
        "missing": missing,
        "extra": extra,
        "duplicate_ids": duplicate_ids,
        "duplicate_public_commands": duplicate_public,
        "missing_groups": missing_groups,
        "invalid_groups": invalid_groups,
        "problems": problems,
        "pending_body_access": "NO",
    }


def _load_registry_module() -> object:
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return importlib.import_module("court_cli_registry")


def evaluate_registry() -> dict[str, object]:
    problems: list[str] = []
    forbidden_loaded: list[str] = []
    record_count = 0
    daily_help_command_count = 0
    daily_help_forbidden_hits: list[str] = []
    help_sha256 = ""
    try:
        registry = _load_registry_module()
        before = set(sys.modules)
        root_help = registry.render_root_help()
        group_help = "\n".join(registry.render_group_help(group) for group in PUBLIC_GROUPS)
        repeated = registry.render_root_help() + "\n" + "\n".join(
            registry.render_group_help(group) for group in PUBLIC_GROUPS
        )
        if root_help + "\n" + group_help != repeated:
            problems.append("help_order_nondeterministic")
        records = registry.load_registry()
        record_count = len(records)
        daily_help_text = "\n".join(
            registry.render_group_help(group)
            for group in ("court", "office", "shiguan", "supercc", "install", "release", "check")
        )
        daily_help_command_count = sum(
            1
            for line in daily_help_text.splitlines()
            if line.startswith("  ") and line.strip() and not line.strip().startswith("decretum-matrix")
        )
        forbidden_daily_commands = (
            "build-npm-package-mjs",
            "check-cli-performance",
            "check-release-metadata",
            "check-startup-fastpath-contract",
            "ensure-supercc-court",
            "package-skill",
            "release-payload-manifest",
            "supercc-squad-cmd",
        )
        daily_help_forbidden_hits = [
            command for command in forbidden_daily_commands if command in daily_help_text
        ]
        if daily_help_forbidden_hits:
            problems.append("daily_help_exposes_project_inventory")
        # Keep the daily surface bounded while allowing the explicit diagnostic
        # commands added to the public CLI.
        if daily_help_command_count > 36:
            problems.append(f"daily_help_command_count_too_high:{daily_help_command_count}")
        for key, record in records.items():
            absent = sorted(field for field in REGISTRY_FIELDS if not getattr(record, field, None))
            if absent:
                problems.append(f"registry_fields_missing:{key}:{','.join(absent)}")
        if tuple(registry.GROUP_ORDER) != PUBLIC_GROUPS:
            problems.append("registry_group_order_mismatch")
        forbidden_loaded = sorted(
            module
            for module in registry.FORBIDDEN_EAGER_MODULES
            if module in sys.modules and module not in before
        )
        if forbidden_loaded:
            problems.append("help_eager_import")
        import hashlib

        help_sha256 = hashlib.sha256(repeated.encode("utf-8")).hexdigest()
    except (ImportError, OSError, ValueError, AttributeError, json.JSONDecodeError) as exc:
        problems.append(f"registry_unavailable:{type(exc).__name__}:{exc}")
    return {
        "schema": "decretum.cli_registry_check.v1",
        "ok": not problems,
        "status": "PASS" if not problems else "FAIL",
        "CLI_LAZY_LOAD": "PASS" if not problems else "FAIL",
        "record_count": record_count,
        "daily_help_command_count": daily_help_command_count,
        "daily_help_forbidden_hits": daily_help_forbidden_hits,
        "help_sha256": help_sha256,
        "forbidden_eager_modules": forbidden_loaded,
        "problems": problems,
    }


def _run_cli(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts" / "court_cli.py"), *arguments],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        env=env,
    )


def _json_stdout(completed: subprocess.CompletedProcess[str]) -> object:
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"CLI JSON output invalid: {completed.stdout!r} {completed.stderr!r}") from exc


def _normalized_json(value: object) -> object:
    if isinstance(value, list):
        return [_normalized_json(item) for item in value]
    if isinstance(value, Mapping):
        return {
            str(key): _normalized_json(item)
            for key, item in value.items()
            if key not in VOLATILE_RECEIPT_FIELDS
        }
    return value


def evaluate_parity() -> dict[str, object]:
    problems: list[str] = []
    declared_adapters = 0
    parity_command = "probe"
    try:
        registry = _load_registry_module()
        manifest = _load_manifest()
        if manifest is None or not isinstance(manifest.get("entries"), list):
            raise AssertionError("manifest unavailable")
        records = registry.load_registry()
        manifest_records = {
            (str(entry.get("group")), str(entry.get("command"))): entry
            for entry in manifest["entries"]
            if isinstance(entry, dict)
            and entry.get("public") is True
            and entry.get("group") != "root"
        }
        declared_adapters = len(manifest_records)
        if set(records) != set(manifest_records):
            problems.append("registry_manifest_command_mismatch")
        for key, entry in manifest_records.items():
            record = records.get(key)
            if record is None:
                continue
            if record.legacy_path != entry.get("legacy_path"):
                problems.append(f"legacy_path_mismatch:{key[0]}:{key[1]}")
            if record.loader not in {"court_runtime.main", "isolated_subprocess"} and not record.loader.startswith("python_module:"):
                problems.append(f"undeclared_adapter:{key[0]}:{key[1]}")

        legacy = _run_cli(["--format", "json", parity_command])
        unified = _run_cli(["--format", "json", "court", parity_command])
        if legacy.returncode != 0 or unified.returncode != 0:
            problems.append(
                f"probe_exit_mismatch:legacy={legacy.returncode}:unified={unified.returncode}"
            )
        else:
            legacy_payload = _json_stdout(legacy)
            unified_envelope = _json_stdout(unified)
            if not isinstance(unified_envelope, dict):
                problems.append("unified_probe_envelope_invalid")
            elif _normalized_json(unified_envelope.get("payload")) != _normalized_json(legacy_payload):
                problems.append("probe_payload_mismatch")
    except (AssertionError, ImportError, OSError, ValueError, AttributeError) as exc:
        problems.append(f"parity_unavailable:{type(exc).__name__}:{exc}")
    return {
        "schema": "decretum.cli_parity_check.v1",
        "ok": not problems,
        "status": "PASS" if not problems else "FAIL",
        "CLI_LEGACY_PARITY": "PASS" if not problems else "FAIL",
        "declared_adapter_count": declared_adapters,
        "synthetic_pair": f"legacy:{parity_command}/unified:court {parity_command}",
        "problems": problems,
    }


def evaluate_external_cwd_contract() -> dict[str, object]:
    problems: list[str] = []
    relative_problem: str | None = None
    command_cwd_contract: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="decretum-cli-外部 cwd ") as temp_text:
        external_cwd = Path(temp_text)
        request_path = external_cwd / "request.json"
        request_path.write_text(
            json.dumps({"schema": "court.open.fast.request.v2"}, ensure_ascii=True),
            encoding="utf-8",
        )
        completed = _run_cli(
            [
                "--format",
                "json",
                "court",
                "open",
                "--fast",
                "--request-file",
                "request.json",
            ],
            cwd=external_cwd,
        )
        try:
            envelope = _json_stdout(completed)
        except AssertionError as exc:
            problems.append(str(exc))
            envelope = None
        if isinstance(envelope, dict):
            payload = envelope.get("payload")
            if isinstance(payload, dict):
                raw_problems = payload.get("problems")
                if isinstance(raw_problems, list) and raw_problems:
                    relative_problem = str(raw_problems[0])
            if relative_problem != "task_id_required":
                problems.append(f"relative_request_file_not_invocation_cwd:{relative_problem}")

        try:
            registry = _load_registry_module()
            for group in ("court", "shiguan", "install"):
                command_cwd_contract[group] = str(registry.command_cwd(group, external_cwd))
                if Path(command_cwd_contract[group]) != external_cwd:
                    problems.append(f"skill_group_cwd_not_invocation:{group}")
            for group in ("check", "release"):
                command_cwd_contract[group] = str(registry.command_cwd(group, external_cwd))
                if Path(command_cwd_contract[group]) != ROOT:
                    problems.append(f"project_group_cwd_not_code_root:{group}")
        except (ImportError, OSError, ValueError, AttributeError) as exc:
            problems.append(f"command_cwd_contract_unavailable:{type(exc).__name__}:{exc}")
    return {
        "schema": "decretum.cli_external_cwd_check.v1",
        "ok": not problems,
        "status": "PASS" if not problems else "FAIL",
        "CLI_EXTERNAL_CWD": "PASS" if not problems else "FAIL",
        "relative_request_file_problem": relative_problem,
        "command_cwd_contract": command_cwd_contract,
        "problems": problems,
    }


def evaluate_public_open_command() -> dict[str, object]:
    problems: list[str] = []
    court_help = ""
    open_markdown = ""
    fast_help = ""
    runtime_help = ""
    try:
        registry = _load_registry_module()
        court_help = registry.render_group_help("court")
        if "\n  open\n" not in court_help:
            problems.append("public_court_open_missing")
        if "decree-open" in court_help:
            problems.append("runtime_internal_decree_open_exposed_in_public_help")

        open_envelope = _json_stdout(_run_cli(["--format", "json", "court", "open"]))
        if open_envelope.get("command") != "court open":
            problems.append("court_open_envelope_command_drift")
        payload = open_envelope.get("payload")
        if not isinstance(payload, dict) or payload.get("schema") != "court.open.guidance.v1":
            problems.append("court_open_guidance_payload_missing")
            payload = {}
        open_markdown = str(payload.get("markdown") or "")
        if not open_markdown.startswith("# Decretum Matrix court open"):
            problems.append("court_open_markdown_missing")
        if payload.get("progressive_loading") is not True:
            problems.append("court_open_progressive_loading_missing")
        if payload.get("fastpath_executed") is not False:
            problems.append("court_open_unexpected_fastpath_execution")
        if payload.get("mutations") != []:
            problems.append("court_open_guidance_mutated_state")
        if payload.get("dispatch_count") != 0 or payload.get("physical_child_dispatch_count") != 0:
            problems.append("court_open_guidance_claimed_spawn")
        if "decree-open" in open_markdown:
            problems.append("court_open_guidance_mentions_decree_open")

        fast_envelope = _json_stdout(
            _run_cli(["--format", "json", "court", "open", "--fast", "--help"])
        )
        if fast_envelope.get("command") != "court open":
            problems.append("court_open_fast_envelope_command_drift")
        fast_help = str(fast_envelope.get("payload") or "")
        if "--request-json" not in fast_help or "--request-file" not in fast_help:
            problems.append("court_open_fast_help_missing_request_sources")

        runtime = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / "court_runtime.py"), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        runtime_help = runtime.stdout
        if runtime.returncode != 0:
            problems.append(f"runtime_help_failed:{runtime.returncode}")
        if "runtime-internal" not in runtime_help or "public startup is court open" not in runtime_help:
            problems.append("decree_open_internal_label_missing")
    except (AssertionError, ImportError, OSError, ValueError, AttributeError, subprocess.SubprocessError) as exc:
        problems.append(f"public_open_command_unavailable:{type(exc).__name__}:{exc}")
    return {
        "schema": "decretum.cli_public_open_command_check.v1",
        "ok": not problems,
        "status": "PASS" if not problems else "FAIL",
        "CLI_PUBLIC_OPEN_COMMAND": "PASS" if not problems else "FAIL",
        "court_help_has_open": "\n  open\n" in court_help,
        "public_help_exposes_decree_open": "decree-open" in court_help,
        "open_guidance_markdown": bool(open_markdown),
        "open_fast_help_bound": "--request-json" in fast_help,
        "runtime_help_labels_decree_open_internal": "runtime-internal" in runtime_help,
        "problems": problems,
    }


def evaluate_v2_normalization() -> dict[str, object]:
    problems: list[str] = []
    normalized_arguments: list[str] = []
    notes: tuple[str, ...] = ()
    selected_protocol: str | None = None
    model_override_applied: bool | None = None
    hierarchy_allowed: bool | None = None
    try:
        registry = _load_registry_module()
        binding = {
            "role": "zhongshu",
            "instance_id": "zhongshu#cli-regression",
            "direct_superior": "taizi",
            "canonical_authority": True,
            "instance_kind": "office",
            "owner_role": None,
        }
        original = [
            "agent-admit",
            "--protocol-mode",
            "v2",
            "--active-session-protocol",
            "v2",
            "--needs-parallel-tree",
            "--needs-fork-turns",
            "--needs-agent-type-override",
            "--requested-roles",
            "zhongshu",
            "--requested-bindings-json",
            json.dumps([binding], separators=(",", ":")),
        ]
        normalized_arguments, notes = registry.normalize_runtime_argv(original)
        if "--needs-agent-type-override" in normalized_arguments:
            problems.append("legacy_agent_type_flag_not_normalized")
        if "v2_reserved_agent_type_from_binding" not in notes:
            problems.append("normalization_receipt_missing")

        from court_multi_agent_protocol import ProtocolRequirements, select_protocol

        decision = select_protocol(
            "v2",
            ProtocolRequirements(
                child_agents_required=True,
                needs_parallel_tree=True,
                needs_fork_turns=True,
                needs_agent_type_override=False,
                active_session_protocol="v2",
            ),
        )
        selected_protocol = decision.selected_mode
        if decision.conflict or selected_protocol != "v2":
            problems.append("v2_protocol_not_selected")

        from court_dispatch_hierarchy import validate_dispatch_hierarchy

        hierarchy = validate_dispatch_hierarchy(
            action="dispatch",
            calling_office="taizi",
            target_role=binding["role"],
            target_direct_superior=binding["direct_superior"],
            instance_kind=binding["instance_kind"],
            canonical_authority=binding["canonical_authority"],
            owner_role=binding["owner_role"],
        )
        hierarchy_allowed = hierarchy.allowed
        if not hierarchy.allowed:
            problems.append("taizi_zhongshu_hierarchy_rejected")

        from court_model_router import route_office_model

        route = route_office_model(
            transport="codex",
            protocol="v2",
            role="zhongshu",
            assignment="bounded CLI regression",
            task_focus="V2 reserved-schema admission",
            complexity="medium",
            risk="low",
            ambiguity="low",
        )
        model_override_applied = bool(route["model_override_applied"])
        if model_override_applied:
            problems.append("model_override_was_applied")
        if route.get("inheritance_policy") != "inherit_main_thread_model_reserved_schema":
            problems.append("reserved_schema_inheritance_missing")
    except (ImportError, OSError, ValueError, AttributeError, KeyError) as exc:
        problems.append(f"v2_normalization_unavailable:{type(exc).__name__}:{exc}")
    return {
        "schema": "decretum.cli_v2_normalization_check.v1",
        "ok": not problems,
        "status": "PASS" if not problems else "FAIL",
        "CLI_V2_PROTOCOL_NORMALIZATION": "PASS" if not problems else "FAIL",
        "selected_protocol": selected_protocol,
        "model_override_applied": model_override_applied,
        "hierarchy_taizi_to_zhongshu": "PASS" if hierarchy_allowed else "FAIL",
        "normalization_notes": list(notes),
        "normalized_arguments": normalized_arguments,
        "problems": problems,
    }


def evaluate_install_core() -> dict[str, object]:
    problems: list[str] = []
    calls: list[dict[str, object]] = []
    rollback_calls: list[dict[str, object]] = []

    def fake_core(**kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        return {
            "schema": "court.install_current_agent_copy.v1",
            "ok": True,
            "status": "PLANNED",
            "reason": "projection_planned",
            "install_root_transitions": [],
            "pending_body_accessed": False,
        }

    def fake_rollback(**kwargs: object) -> dict[str, object]:
        rollback_calls.append(dict(kwargs))
        return {
            "schema": "court.install_projection_rollback.v1",
            "ok": True,
            "status": "ROLLED_BACK",
            "pending_body_accessed": False,
        }

    request = {
        "schema": "decretum.install.request.v1",
        "source_root": str(ROOT),
        "home_root": str(ROOT / ".fixture-home"),
        "current_tool": "codex",
        "explicit_tools": [],
        "tool_roots": {"codex": str(ROOT / ".fixture-home" / ".codex" / "skills")},
        "projection_manifest": str(ROOT / "release-manifest.json"),
        "write": False,
        "fanout": False,
    }
    try:
        registry = _load_registry_module()
        update = registry.invoke_install_core("update", request, core=fake_core)
        migrate = registry.invoke_install_core("migrate", request, core=fake_core)
        rollback = registry.invoke_install_rollback(
            {
                "schema": "decretum.install.rollback.request.v1",
                "home_root": str(ROOT / ".fixture-home"),
                "backup_root": str(ROOT / ".fixture-home" / ".agents" / "install-backups" / "decretum-matrix" / "fixture"),
            },
            core=fake_rollback,
        )
        if len(calls) != 2 or calls[0] != calls[1]:
            problems.append("install_operations_do_not_share_one_core_contract")
        if update.get("updater_core") != migrate.get("updater_core"):
            problems.append("install_core_identity_mismatch")
        if update.get("cli_operation") != "update" or migrate.get("cli_operation") != "migrate":
            problems.append("install_operation_receipt_missing")
        if any(call.get("write") is not False or call.get("fanout") is not False for call in calls):
            problems.append("install_plan_fixture_mutated")
        if len(rollback_calls) != 1 or rollback.get("status") != "ROLLED_BACK":
            problems.append("install_rollback_core_unavailable")
        install_help = registry.render_group_help("install")
        if any(command not in install_help for command in ("update", "migrate", "rollback")):
            problems.append("install_commands_not_discoverable")
    except (ImportError, OSError, ValueError, AttributeError) as exc:
        problems.append(f"install_core_unavailable:{type(exc).__name__}:{exc}")
    return {
        "schema": "decretum.install_cli_check.v1",
        "ok": not problems,
        "status": "PASS" if not problems else "FAIL",
        "UPDATER_SINGLE_CORE": "PASS" if not problems else "FAIL",
        "INSTALL_ROLLBACK": "PASS" if not problems else "FAIL",
        "core_calls": len(calls),
        "rollback_core_calls": len(rollback_calls),
        "problems": problems,
    }


def evaluate_archive_receipt() -> dict[str, object]:
    problems: list[str] = []
    payload: dict[str, object] | None = None
    with tempfile.TemporaryDirectory(prefix="decretum-cli-archive-receipt-") as temp_text:
        env = dict(os.environ)
        env["COURT_SHARED_SHIGUAN_ROOT"] = str(Path(temp_text) / "shared-shiguan")
        completed = _run_cli(
            [
                "--format",
                "json",
                "shiguan",
                "archive-checkpoint",
                "--topic",
                "unified-cli-receipt-fixture",
                "--phase",
                "receipt-binding",
                "--status",
                "DONE",
                "--summary",
                "fixture",
                "--evidence",
                "fixture",
                "--next",
                "none",
                "--no-refresh",
            ],
            env=env,
        )
        if completed.returncode != 0:
            problems.append(f"archive_command_exit:{completed.returncode}:{completed.stderr.strip()}")
        else:
            try:
                envelope = _json_stdout(completed)
            except AssertionError as exc:
                problems.append(str(exc))
            else:
                candidate = envelope.get("payload") if isinstance(envelope, dict) else None
                if not isinstance(candidate, dict):
                    problems.append("archive_receipt_payload_not_structured")
                else:
                    payload = candidate
                    if candidate.get("schema") != "court.shiguan_archive_checkpoint_receipt.v1":
                        problems.append("archive_receipt_schema")
                    for field in (
                        "receipt_id",
                        "path",
                        "court_code",
                        "lineage_display",
                        "closeout_identity",
                    ):
                        if not isinstance(candidate.get(field), str) or not str(candidate[field]).strip():
                            problems.append(f"archive_receipt_missing:{field}")
                    identity = str(candidate.get("closeout_identity") or "")
                    if f"诏令编号：{candidate.get('court_code', '')}" not in identity:
                        problems.append("archive_receipt_court_code_not_bound")
                    if f"古制谱系：{candidate.get('lineage_display', '')}" not in identity:
                        problems.append("archive_receipt_lineage_not_bound")
    return {
        "schema": "decretum.cli_archive_receipt_check.v1",
        "ok": not problems,
        "status": "PASS" if not problems else "FAIL",
        "CLI_ARCHIVE_RECEIPT_BINDING": "PASS" if not problems else "FAIL",
        "receipt_id": payload.get("receipt_id") if payload else None,
        "problems": problems,
    }


def evaluate_npm_launcher_stdio() -> dict[str, object]:
    problems: list[str] = []
    encoded = b""
    try:
        launcher_path = ROOT / "bin" / "decretum-matrix.py"
        spec = importlib.util.spec_from_file_location(
            "decretum_matrix_npm_launcher_stdio_check",
            launcher_path,
        )
        if spec is None or spec.loader is None:
            raise AssertionError("npm launcher import spec unavailable")
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="gbk", errors="strict")
        launcher._configure_standard_streams((stream,))
        stream.write(json.dumps({"replacement": "\ufffd"}, ensure_ascii=False))
        stream.flush()
        encoded = buffer.getvalue()
        stream.detach()
        if encoded.decode("utf-8") != '{"replacement": "\ufffd"}':
            problems.append("npm_launcher_utf8_payload_mismatch")
    except (AssertionError, ImportError, OSError, UnicodeError, AttributeError) as exc:
        problems.append(f"npm_launcher_stdio_unavailable:{type(exc).__name__}:{exc}")
    return {
        "schema": "decretum.cli_npm_stdio_check.v1",
        "ok": not problems,
        "status": "PASS" if not problems else "FAIL",
        "CLI_NPM_STDIO_UTF8": "PASS" if not problems else "FAIL",
        "encoded_sha256": __import__("hashlib").sha256(encoded).hexdigest() if encoded else None,
        "problems": problems,
    }


def evaluate_npm_launcher_runtime_selection() -> dict[str, object]:
    problems: list[str] = []
    calls: list[str] = []
    normal_cli: str | None = None
    fallback_cli: str | None = None
    postinstall_runtime: str | None = None
    probe_identity: dict[str, object] | None = None
    try:
        from contextlib import redirect_stdout
        import zipfile

        launcher_path = ROOT / "bin" / "decretum-matrix.py"
        spec = importlib.util.spec_from_file_location(
            "decretum_matrix_npm_launcher_runtime_selection_check",
            launcher_path,
        )
        if spec is None or spec.loader is None:
            raise AssertionError("npm launcher import spec unavailable")
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        with tempfile.TemporaryDirectory(prefix="decretum-npm-canonical-runtime-") as temp_text:
            home = Path(temp_text) / "home"
            package_root = Path(temp_text) / "package"
            canonical = home / ".agents" / "skills" / "decretum-matrix"
            version_payload = (ROOT / "VERSION").read_bytes()
            skill_payload = b"---\nname: decretum-matrix\n---\n"
            cli_payload = b"print('canonical')\n"

            def write_identity(root: Path) -> None:
                (root / "scripts").mkdir(parents=True, exist_ok=True)
                (root / "VERSION").write_bytes(version_payload)
                (root / "SKILL.md").write_bytes(skill_payload)
                (root / "scripts" / "court_cli.py").write_bytes(cli_payload)

            write_identity(package_root)
            write_identity(canonical)
            (package_root / "package.json").write_text(
                json.dumps(
                    {
                        "name": "@rowlandl/decretum-matrix",
                        "decretumMatrix": {
                            "releaseLabel": (ROOT / "VERSION").read_text(encoding="utf-8").strip()
                        },
                    }
                ),
                encoding="utf-8",
            )
            selected = launcher._canonical_runtime_root(package_root, home)
            if selected != canonical:
                problems.append("canonical_runtime_not_selected")
            probe_identity = launcher.runtime_identity_probe(
                package_root,
                home=home,
                cache_base=Path(temp_text) / "probe-cache",
            )
            if (
                probe_identity.get("schema") != "court.runtime_identity.v1"
                or probe_identity.get("root") != str(canonical.resolve())
                or probe_identity.get("source_kind") != "installed"
                or not probe_identity.get("content_digest")
            ):
                problems.append("canonical_runtime_identity_invalid")

            embedded_package_root = Path(temp_text) / "embedded-package"
            (embedded_package_root / "bin").mkdir(parents=True)
            release_root = embedded_package_root / "release"
            release_root.mkdir()
            embedded_version = version_payload.decode("utf-8").strip()
            embedded_package_json = embedded_package_root / "package.json"
            embedded_package_json.write_text(
                json.dumps(
                    {
                        "name": "@rowlandl/decretum-matrix",
                        "decretumMatrix": {"releaseLabel": embedded_version},
                    }
                ),
                encoding="utf-8",
            )
            embedded_archive = release_root / "decretum-matrix-beta-test.zip"
            with zipfile.ZipFile(embedded_archive, "w") as archive:
                archive.writestr("decretum-matrix/VERSION", version_payload)
                archive.writestr("decretum-matrix/SKILL.md", skill_payload)
                archive.writestr("decretum-matrix/scripts/court_cli.py", cli_payload)
            embedded_expected = launcher._expected_runtime_identity(embedded_package_root)
            if (
                launcher._canonical_runtime_root(embedded_package_root, home) != canonical
                or not isinstance(embedded_expected, dict)
                or embedded_expected.get("source_kind") != "embedded_package"
                or embedded_expected.get("version") != embedded_version
                or embedded_expected.get("content_digest") != probe_identity.get("content_digest")
            ):
                problems.append("embedded_package_identity_not_supported")
            embedded_package_json.write_text(
                json.dumps(
                    {
                        "name": "@rowlandl/decretum-matrix",
                        "decretumMatrix": {"releaseLabel": "beta-metadata-mismatch"},
                    }
                ),
                encoding="utf-8",
            )
            if (
                launcher._expected_runtime_identity(embedded_package_root) is not None
                or launcher._canonical_runtime_root(embedded_package_root, home) is not None
            ):
                problems.append("embedded_package_metadata_mismatch_not_rejected")
            embedded_package_json.write_text(
                json.dumps(
                    {
                        "name": "@rowlandl/decretum-matrix",
                        "decretumMatrix": {"releaseLabel": embedded_version},
                    }
                ),
                encoding="utf-8",
            )

            (canonical / "SKILL.md").write_text("divergent installed skill\n", encoding="utf-8")
            if launcher._canonical_runtime_root(package_root, home) is not None:
                problems.append("same_version_divergent_runtime_selected")
            (canonical / "SKILL.md").write_bytes(skill_payload)

            def fake_release_archive(root: Path) -> Path:
                calls.append("release_archive")
                return root / "release" / "fixture.zip"

            def fake_extract_runtime(_archive: Path, cache_root: Path, _archive_id: str) -> Path:
                calls.append("extract_runtime")
                runtime = cache_root / "runtime"
                write_identity(runtime)
                return runtime

            def fake_run_path(path: str, run_name: str | None = None) -> dict[str, object]:
                nonlocal fallback_cli, normal_cli
                calls.append("run_path")
                if "runtime" in path and str(canonical) not in path:
                    fallback_cli = path
                else:
                    normal_cli = path
                return {}

            def fake_postinstall(runtime_root: Path, digest: str) -> int:
                nonlocal postinstall_runtime
                calls.append("postinstall")
                postinstall_runtime = str(runtime_root)
                return 0

            original_release_archive = launcher._release_archive
            original_extract_runtime = launcher._extract_runtime
            original_postinstall_home = launcher._postinstall_home
            original_run_postinstall = launcher._run_postinstall
            original_run_path = launcher.runpy.run_path
            original_runtime_identity = launcher._runtime_identity
            original_launcher_file = launcher.__file__
            launcher._release_archive = fake_release_archive
            launcher._extract_runtime = fake_extract_runtime
            launcher._postinstall_home = lambda: home
            launcher._run_postinstall = fake_postinstall
            launcher.runpy.run_path = fake_run_path
            launcher.__file__ = str(package_root / "bin" / "decretum-matrix.py")
            try:
                original_expected_runtime_identity = launcher._expected_runtime_identity
                expected_a = original_expected_runtime_identity(package_root)
                if not isinstance(expected_a, dict):
                    raise AssertionError("package expected identity unavailable")
                expected_b = dict(expected_a)
                expected_b["content_digest"] = "f" * 64

                installed_expected_reads = 0

                def alternating_installed_expected(root: Path) -> dict[str, object] | None:
                    nonlocal installed_expected_reads
                    installed_expected_reads += 1
                    return expected_a if installed_expected_reads == 1 else expected_b

                launcher._expected_runtime_identity = alternating_installed_expected
                calls.clear()
                try:
                    selected_root, selected_identity = launcher._select_runtime(
                        package_root,
                        home=home,
                        cache_base=Path(temp_text) / "single-read-installed-cache",
                    )
                finally:
                    launcher._expected_runtime_identity = original_expected_runtime_identity
                if installed_expected_reads != 1:
                    problems.append(
                        f"expected_identity_installed_read_count:{installed_expected_reads}"
                    )
                if (
                    selected_root != canonical
                    or selected_identity.get("source_kind") != "installed"
                    or calls
                ):
                    problems.append("expected_identity_installed_snapshot_not_preserved")

                (canonical / "SKILL.md").write_text(
                    "divergent installed skill\n",
                    encoding="utf-8",
                )
                fallback_expected_reads = 0

                def alternating_fallback_expected(root: Path) -> dict[str, object] | None:
                    nonlocal fallback_expected_reads
                    fallback_expected_reads += 1
                    return expected_a if fallback_expected_reads == 1 else expected_b

                launcher._expected_runtime_identity = alternating_fallback_expected
                calls.clear()
                try:
                    selected_root, selected_identity = launcher._select_runtime(
                        package_root,
                        home=home,
                        cache_base=Path(temp_text) / "single-read-fallback-cache",
                    )
                finally:
                    launcher._expected_runtime_identity = original_expected_runtime_identity
                    (canonical / "SKILL.md").write_bytes(skill_payload)
                if fallback_expected_reads != 1:
                    problems.append(
                        f"expected_identity_fallback_read_count:{fallback_expected_reads}"
                    )
                if (
                    selected_root == canonical
                    or selected_identity.get("source_kind") != "embedded_cache"
                    or calls != ["release_archive", "extract_runtime"]
                ):
                    problems.append("expected_identity_fallback_snapshot_not_preserved")

                installed_a = original_runtime_identity(
                    canonical,
                    source_kind="installed",
                )
                if not isinstance(installed_a, dict):
                    raise AssertionError("installed runtime identity unavailable")
                installed_b = dict(installed_a)
                installed_b["content_digest"] = "e" * 64
                installed_candidate_reads = 0

                def alternating_installed_candidate(
                    root: Path,
                    *,
                    source_kind: str,
                ) -> dict[str, object] | None:
                    nonlocal installed_candidate_reads
                    if root.resolve() == canonical.resolve() and source_kind == "installed":
                        installed_candidate_reads += 1
                        return (
                            installed_a
                            if installed_candidate_reads == 1
                            else installed_b
                        )
                    return original_runtime_identity(root, source_kind=source_kind)

                launcher._runtime_identity = alternating_installed_candidate
                calls.clear()
                try:
                    selected_root, selected_identity = launcher._select_runtime(
                        package_root,
                        home=home,
                        cache_base=Path(temp_text) / "single-read-candidate-cache",
                    )
                finally:
                    launcher._runtime_identity = original_runtime_identity
                if installed_candidate_reads != 1:
                    problems.append(
                        f"installed_candidate_read_count:{installed_candidate_reads}"
                    )
                if (
                    selected_root != canonical
                    or selected_identity != installed_a
                    or calls
                ):
                    problems.append("installed_candidate_snapshot_not_preserved")

                calls.clear()
                normal_stdout = io.StringIO()
                with redirect_stdout(normal_stdout):
                    rc = launcher.main(["--help"])
                if rc != 0:
                    problems.append(f"normal_launcher_rc:{rc}")
                if normal_stdout.getvalue():
                    problems.append("normal_launcher_polluted_stdout")
                if calls != ["run_path"]:
                    problems.append("normal_launcher_used_archive_or_cache:" + ",".join(calls))
                if normal_cli != str(canonical / "scripts" / "court_cli.py"):
                    problems.append("normal_launcher_not_canonical_cli")

                calls.clear()
                probe_stdout = io.StringIO()
                with redirect_stdout(probe_stdout):
                    rc = launcher.main(["--runtime-identity"])
                if rc != 0:
                    problems.append(f"identity_probe_rc:{rc}")
                if calls:
                    problems.append("identity_probe_invoked_cli_or_fallback:" + ",".join(calls))
                try:
                    emitted_identity = json.loads(probe_stdout.getvalue())
                except json.JSONDecodeError:
                    emitted_identity = None
                if emitted_identity != probe_identity:
                    problems.append("identity_probe_payload_mismatch")

                (canonical / "SKILL.md").write_text("divergent installed skill\n", encoding="utf-8")
                calls.clear()
                fallback_stdout = io.StringIO()
                with redirect_stdout(fallback_stdout):
                    rc = launcher.main(["--help"])
                if rc != 0:
                    problems.append(f"fallback_launcher_rc:{rc}")
                if fallback_stdout.getvalue():
                    problems.append("fallback_launcher_polluted_stdout")
                if calls != ["release_archive", "extract_runtime", "run_path"]:
                    problems.append("divergent_runtime_did_not_fallback:" + ",".join(calls))
                if not fallback_cli or "runtime" not in fallback_cli:
                    problems.append("fallback_runtime_not_selected")
                (canonical / "SKILL.md").write_bytes(skill_payload)

                calls.clear()
                rc = launcher.main(["--npm-postinstall"])
                if rc != 0:
                    problems.append(f"postinstall_launcher_rc:{rc}")
                if calls != ["release_archive", "extract_runtime", "postinstall"]:
                    problems.append("postinstall_did_not_use_embedded_archive:" + ",".join(calls))
                if not postinstall_runtime or "runtime" not in postinstall_runtime:
                    problems.append("postinstall_runtime_not_embedded_fallback")
            finally:
                launcher._release_archive = original_release_archive
                launcher._extract_runtime = original_extract_runtime
                launcher._postinstall_home = original_postinstall_home
                launcher._run_postinstall = original_run_postinstall
                launcher.runpy.run_path = original_run_path
                launcher._expected_runtime_identity = original_expected_runtime_identity
                launcher._runtime_identity = original_runtime_identity
                launcher.__file__ = original_launcher_file
    except (AssertionError, ImportError, OSError, UnicodeError, AttributeError) as exc:
        problems.append(f"npm_launcher_runtime_selection_unavailable:{type(exc).__name__}:{exc}")
    return {
        "schema": "decretum.cli_npm_runtime_selection_check.v1",
        "ok": not problems,
        "status": "PASS" if not problems else "FAIL",
        "CLI_NPM_CANONICAL_RUNTIME": "PASS" if not problems else "FAIL",
        "normal_cli": normal_cli,
        "fallback_cli": fallback_cli,
        "runtime_identity": probe_identity,
        "postinstall_runtime": postinstall_runtime,
        "problems": problems,
    }


def _selected_reports(args: argparse.Namespace) -> list[dict[str, object]]:
    selected = []
    if args.inventory_only:
        selected.append(evaluate_inventory())
    if args.registry:
        selected.append(evaluate_registry())
    if args.parity:
        selected.append(evaluate_parity())
    if args.external_cwd:
        selected.append(evaluate_external_cwd_contract())
    if args.public_open:
        selected.append(evaluate_public_open_command())
    if args.v2_normalization:
        selected.append(evaluate_v2_normalization())
    if args.install_core:
        selected.append(evaluate_install_core())
    if args.archive_receipt:
        selected.append(evaluate_archive_receipt())
    if args.npm_runtime:
        selected.append(evaluate_npm_launcher_runtime_selection())
    if not selected or args.all:
        selected = [
            evaluate_inventory(),
            evaluate_registry(),
            evaluate_parity(),
            evaluate_external_cwd_contract(),
            evaluate_public_open_command(),
            evaluate_v2_normalization(),
            evaluate_install_core(),
            evaluate_archive_receipt(),
            evaluate_npm_launcher_stdio(),
            evaluate_npm_launcher_runtime_selection(),
        ]
    return selected


def _combined_report(reports: list[dict[str, object]]) -> dict[str, object]:
    combined: dict[str, object] = {
        "schema": "decretum.unified_cli_check.v1",
        "ok": all(bool(report.get("ok")) for report in reports),
        "status": "PASS" if all(bool(report.get("ok")) for report in reports) else "FAIL",
        "reports": reports,
        "pending_body_access": "NO",
    }
    for report in reports:
        for key, value in report.items():
            if key.startswith("CLI_"):
                combined[key] = value
    return combined


def _text_report(report: dict[str, object]) -> str:
    lines = [
        f"{key}={value}"
        for key, value in report.items()
        if key.startswith("CLI_")
    ]
    for child in report.get("reports", []):
        if isinstance(child, dict):
            lines.extend(f"problem={value}" for value in child.get("problems", []))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--registry", action="store_true")
    parser.add_argument("--parity", action="store_true")
    parser.add_argument("--external-cwd", action="store_true")
    parser.add_argument("--public-open", action="store_true")
    parser.add_argument("--v2-normalization", action="store_true")
    parser.add_argument("--install-core", action="store_true")
    parser.add_argument("--archive-receipt", action="store_true")
    parser.add_argument("--npm-runtime", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.write_manifest:
        write_manifest()
    report = _combined_report(_selected_reports(args))
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        print(_text_report(report))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
