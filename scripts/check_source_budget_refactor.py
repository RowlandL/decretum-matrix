"""Check the bounded source-budget module split."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

from check_source_state_budget import evaluate, load_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "references" / "manifests" / "source-state-budget.v1.json"
MODULES = {
    "scripts/supercc_dispatch_contract.py": (
        500,
        {
            "default_dispatch_calling_office",
            "validate_enter_dispatch_context",
            "_new_identity_generation_challenge",
            "active_office_identity_fingerprint",
            "active_office_preload_ack_gate",
        },
        {"ensure_supercc_court"},
    ),
    "scripts/supercc_dispatch_delivery.py": (
        1100,
        {"native_pane_enter_sequence", "_blocked_transport_preflight", "enter_dispatch"},
        {"ensure_supercc_court"},
    ),
    "scripts/court_agent_admission_contract.py": (
        300,
        {"scoped_hierarchy_denial", "validate_admission_instance_shape"},
        {"court_agent_admission"},
    ),
}
MAIN_MODULES = {
    "scripts/ensure_supercc_court.py": (
        5400,
        {"supercc_dispatch_contract", "supercc_dispatch_delivery"},
        MODULES["scripts/supercc_dispatch_contract.py"][1]
        | MODULES["scripts/supercc_dispatch_delivery.py"][1],
    ),
    "scripts/court_agent_admission.py": (
        820,
        {"court_agent_admission_contract"},
        MODULES["scripts/court_agent_admission_contract.py"][1],
    ),
    "scripts/serve_shiguan_tree.py": (
        2790,
        {"ensure_shiguan_autosync"},
        {"autosync_public_status"},
    ),
}
MANIFEST_LIMITS = {
    "scripts/ensure_supercc_court.py": 5700,
    "scripts/supercc_dispatch_contract.py": 500,
    "scripts/supercc_dispatch_delivery.py": 1100,
    "scripts/court_agent_admission.py": 850,
    "scripts/court_agent_admission_contract.py": 300,
    "scripts/serve_shiguan_tree.py": 2800,
    "scripts/ensure_shiguan_autosync.py": 600,
}
REQUIRED_PACKAGE_SCRIPTS = {
    "supercc_dispatch_contract.py",
    "supercc_dispatch_delivery.py",
    "court_agent_admission_contract.py",
}


def module_shape(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    definitions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return definitions, imports


def physical_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def assigned_string_list(path: Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
            and isinstance(node.value, (ast.List, ast.Tuple))
        ):
            return {
                item.value
                for item in node.value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
    return set()


def main() -> int:
    errors: list[str] = []
    for relative, (limit, required, forbidden_imports) in MODULES.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing_helper:{relative}")
            continue
        definitions, imports = module_shape(path)
        if required - definitions:
            errors.append(f"helper_ownership_missing:{relative}:{sorted(required - definitions)}")
        if imports & forbidden_imports:
            errors.append(f"helper_reverse_import:{relative}:{sorted(imports & forbidden_imports)}")
        if physical_lines(path) > limit:
            errors.append(f"helper_line_budget:{relative}:{physical_lines(path)}>{limit}")

    for relative, (limit, required_imports, moved_definitions) in MAIN_MODULES.items():
        path = ROOT / relative
        definitions, imports = module_shape(path)
        if required_imports - imports:
            errors.append(f"main_import_missing:{relative}:{sorted(required_imports - imports)}")
        if definitions & moved_definitions:
            errors.append(f"main_still_owns:{relative}:{sorted(definitions & moved_definitions)}")
        if physical_lines(path) > limit:
            errors.append(f"main_line_budget:{relative}:{physical_lines(path)}>{limit}")

    autosync_definitions, autosync_imports = module_shape(ROOT / "scripts/ensure_shiguan_autosync.py")
    if "autosync_public_status" not in autosync_definitions:
        errors.append("autosync_public_status_owner_missing")
    if "serve_shiguan_tree" in autosync_imports:
        errors.append("autosync_reverse_import:serve_shiguan_tree")
    if physical_lines(ROOT / "scripts/ensure_shiguan_autosync.py") > 600:
        errors.append("helper_line_budget:scripts/ensure_shiguan_autosync.py")

    manifest = load_manifest(MANIFEST)
    portable = manifest["hard_limits"]["portable_source"]
    limits = manifest["hard_limits"]["source_lines"]
    if portable != {"max_files": 275, "max_bytes": 6200000}:
        errors.append(f"portable_budget_contract:{portable!r}")
    for relative, expected in MANIFEST_LIMITS.items():
        if limits.get(relative) != expected:
            errors.append(f"manifest_line_budget:{relative}:{limits.get(relative)!r}!={expected}")

    packaged = assigned_string_list(ROOT / "scripts/package_skill.py", "REQUIRED_COURT_SCRIPTS")
    if REQUIRED_PACKAGE_SCRIPTS - packaged:
        errors.append(
            "package_required_scripts_missing:"
            + repr(sorted(REQUIRED_PACKAGE_SCRIPTS - packaged))
        )
    source_state = evaluate(ROOT, manifest)
    if source_state.get("ok") is not True:
        errors.append(f"source_state_ok:{source_state.get('ok')!r}")
    hard_fail = source_state.get("hard_fail")
    if hard_fail != []:
        errors.append(f"source_state_hard_fail:{hard_fail!r}")
    inspection_contract = source_state.get("inspection_contract")
    pending_body_reads = (
        inspection_contract.get("pending_body_reads")
        if isinstance(inspection_contract, dict)
        else None
    )
    if pending_body_reads != 0:
        errors.append(f"source_state_pending_body_reads:{pending_body_reads!r}")
    measured = source_state["categories"]["portable_source"]

    complexity = (ROOT / "references/complexity-budget.md").read_text(encoding="utf-8")
    revision = re.search(
        r"## 2026-07-17 Measured Revision\s+"
        r"The beta0\.5\.11 release source tree measures "
        r"([\d,]+) portable files / ([\d,]+) bytes "
        r"against the unchanged ceiling of 275 files / 6,200,000 bytes\.",
        complexity,
    )
    if revision is None:
        errors.append("complexity_budget_measured_revision_missing")
    else:
        documented = {
            "files": int(revision.group(1).replace(",", "")),
            "bytes": int(revision.group(2).replace(",", "")),
        }
        if documented != measured:
            errors.append(f"complexity_budget_measurement:{documented!r}!={measured!r}")

    result = {
        "schema": "court.source_budget_refactor.check.v1",
        "ok": not errors,
        "errors": errors,
        "portable_source": measured,
        "source_state_contract": {
            "ok": source_state.get("ok"),
            "hard_fail": hard_fail,
            "pending_body_reads": pending_body_reads,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
