#!/usr/bin/env python3
"""Validate the versioned unified CLI inventory, registry, and compatibility surface."""

from __future__ import annotations

import argparse
import ast
import importlib
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
BOOTSTRAP_ENTRYPOINTS = (
    PurePosixPath("scripts/check_unified_cli.py"),
    PurePosixPath("scripts/court_open_fastpath.py"),
    PurePosixPath("scripts/check_court_open_fastpath.py"),
)
VOLATILE_RECEIPT_FIELDS = {
    "created_at",
    "generated_at",
    "timestamp",
    "time",
}


def _domain_for(path: str) -> str:
    name = PurePosixPath(path).stem.lower()
    if name.startswith("check_") or name == "quick_validate":
        return "check"
    if "shiguan" in name or "obsidian" in name or name in {
        "archive_checkpoint",
        "archive_runtime_task",
        "memory_decision",
        "reevaluate_memory_decisions",
        "repair_archive_placeholders",
    }:
        return "shiguan"
    if "supercc" in name or name.startswith("supercc-"):
        return "supercc"
    if name.startswith(("build_release", "release_", "package_", "build_npm")):
        return "release"
    if name.startswith(("install_", "migrate_", "sync_active_copies")) or name in {
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
    if name.startswith(("check_", "query_", "report_")) or name.endswith("_probe"):
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
    }
    entry_name = stem.replace("_", "-").lower()
    if pure.suffix.lower() != ".py":
        entry_name = f"{entry_name}-{pure.suffix.lower().lstrip('.')}"
    return {
        "id": f"{domain}.{entry_name}",
        "domain": domain,
        "legacy_path": path,
        "handler": (
            f"python_module:{stem}"
            if direct_module
            else f"isolated_subprocess:{path}"
        ),
        "public": True,
        "side_effect": _side_effect_for(path),
        "authority_source": "court_runtime" if path == "scripts/court_runtime.py" else path,
        "receipt_schema": (
            "decretum.cli.result.v1"
            if is_root
            else "court.shiguan_archive_checkpoint_receipt.v1"
            if path == "scripts/archive_checkpoint.py"
            else "legacy.entrypoint.result.v1"
        ),
        "compatibility_state": "canonical_public_root" if is_root else "unified_compatibility_adapter",
        "group": "root" if is_root else domain,
        "command": "decretum-matrix" if is_root else entry_name,
    }


def _tracked_script_paths() -> list[PurePosixPath]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--", "scripts"],
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
        if relative.suffix.lower() not in SCRIPT_SUFFIXES:
            continue
        path = ROOT.joinpath(*relative.parts)
        if relative.suffix.lower() == ".py" and not _is_python_entrypoint(path):
            continue
        entrypoints.append(str(relative))
    return sorted(entrypoints)


def write_manifest() -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema": MANIFEST_SCHEMA,
        "public_command": "decretum-matrix",
        "source_entry": "python -B scripts/court_cli.py",
        "generated_by": "scripts/check_unified_cli.py --write-manifest",
        "groups": list(PUBLIC_GROUPS),
        "entries": [_manifest_entry(path) for path in discover_executable_entrypoints()],
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def _load_manifest() -> dict[str, object] | None:
    if not MANIFEST_PATH.is_file():
        return None
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError("CLI manifest root must be an object")
    return value


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
        groups = {
            str(entry.get("group") or "")
            for entry in entries
            if entry.get("public") is True and entry.get("group") != "root"
        }
        missing_groups = sorted(set(PUBLIC_GROUPS) - groups)
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
        "help_sha256": help_sha256,
        "forbidden_eager_modules": forbidden_loaded,
        "problems": problems,
    }


def _run_cli(
    arguments: list[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts" / "court_cli.py"), *arguments],
        cwd=ROOT,
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
            if isinstance(entry, dict) and entry.get("group") != "root"
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
                        "receipt_sha256",
                        "archive_sha256",
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


def _selected_reports(args: argparse.Namespace) -> list[dict[str, object]]:
    selected = []
    if args.inventory_only:
        selected.append(evaluate_inventory())
    if args.registry:
        selected.append(evaluate_registry())
    if args.parity:
        selected.append(evaluate_parity())
    if args.v2_normalization:
        selected.append(evaluate_v2_normalization())
    if args.install_core:
        selected.append(evaluate_install_core())
    if args.archive_receipt:
        selected.append(evaluate_archive_receipt())
    if not selected or args.all:
        selected = [
            evaluate_inventory(),
            evaluate_registry(),
            evaluate_parity(),
            evaluate_v2_normalization(),
            evaluate_install_core(),
            evaluate_archive_receipt(),
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
    parser.add_argument("--v2-normalization", action="store_true")
    parser.add_argument("--install-core", action="store_true")
    parser.add_argument("--archive-receipt", action="store_true")
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
