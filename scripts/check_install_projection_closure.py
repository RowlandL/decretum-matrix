"""Verify installed projections contain every executable and local import dependency."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
PROJECTION_MANIFEST = ROOT / "references" / "manifests" / "install-projection.v1.json"
CLI_REGISTRY = ROOT / "scripts" / "court_cli_registry.py"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path.relative_to(ROOT).as_posix()}")
    return value


def _local_imports(path: Path, local_modules: dict[str, str]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    dependencies: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = (alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = (node.module.split(".", 1)[0],)
        else:
            continue
        for name in names:
            relative = local_modules.get(name)
            if relative:
                dependencies.add(relative)
    return dependencies


def _fast_open_handlers() -> set[str]:
    """Return repository-local handlers named by the canonical fast-open path."""

    tree = ast.parse(CLI_REGISTRY.read_text(encoding="utf-8"), filename=str(CLI_REGISTRY))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_capture_court_open":
            return {
                value.value
                for value in ast.walk(node)
                if isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and value.value.startswith("scripts/")
            }
    raise ValueError("canonical_fast_open_registry_function_missing")


def evaluate() -> dict[str, Any]:
    projection = _load_json(PROJECTION_MANIFEST)
    projections = projection.get("projections")
    if not isinstance(projections, dict):
        raise ValueError("install_projection_entries_invalid")
    fast_open_handlers = _fast_open_handlers()

    local_modules = {
        path.stem: path.relative_to(ROOT).as_posix()
        for path in (ROOT / "scripts").glob("*.py")
    }
    failures: list[str] = []
    evidence: dict[str, dict[str, list[str]]] = {}
    for target in ("shared_agents", "portable_current_tool"):
        raw_paths = projections.get(target)
        if not isinstance(raw_paths, list) or any(not isinstance(item, str) for item in raw_paths):
            failures.append(f"{target}:projection_list_invalid")
            continue
        projected = set(raw_paths)
        missing_handlers: list[str] = []
        for executable in sorted(fast_open_handlers):
            if executable not in projected:
                missing_handlers.append(f"court open --fast:{executable}")

        missing_imports: list[str] = []
        for relative in sorted(projected):
            path = ROOT / relative
            if path.suffix != ".py" or not path.is_file():
                continue
            for dependency in sorted(_local_imports(path, local_modules)):
                if dependency not in projected:
                    missing_imports.append(f"{relative}->{dependency}")

        evidence[target] = {
            "missing_cli_handlers": sorted(set(missing_handlers)),
            "missing_local_imports": sorted(set(missing_imports)),
        }
        failures.extend(
            f"{target}:cli_handler_not_projected:{item}"
            for item in evidence[target]["missing_cli_handlers"]
        )
        failures.extend(
            f"{target}:local_import_not_projected:{item}"
            for item in evidence[target]["missing_local_imports"]
        )

    return {
        "schema": "court.install_projection_closure_check.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": "INSTALL_PROJECTION_TRANSITIVE_CLOSURE",
        "evidence": evidence,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate()
    except (OSError, ValueError, json.JSONDecodeError, SyntaxError) as exc:
        result = {
            "schema": "court.install_projection_closure_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "INSTALL_PROJECTION_TRANSITIVE_CLOSURE",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"INSTALL_PROJECTION_TRANSITIVE_CLOSURE={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
