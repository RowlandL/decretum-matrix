"""Verify installed projections contain every executable and local import dependency."""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
PROJECTION_MANIFEST = ROOT / "references" / "manifests" / "install-projection.v1.json"
CLI_REGISTRY = ROOT / "scripts" / "court_cli_registry.py"
INSTALL_CHECKER_MODULE = "check_active_copy_hashes"
INSTALL_CHECKER_RELATIVE = "scripts/check_active_copy_hashes.py"
SCRIPT_COUPLING_SUFFIXES = {".bat", ".cmd", ".ps1", ".sh"}
RUNTIME_LOADING_CALLS = {
    "__import__",
    "exec",
    "importlib.import_module",
    "os.popen",
    "os.posix_spawn",
    "os.posix_spawnp",
    "os.execl",
    "os.execle",
    "os.execlp",
    "os.execlpe",
    "os.execv",
    "os.execve",
    "os.execvp",
    "os.execvpe",
    "os.spawnl",
    "os.spawnle",
    "os.spawnlp",
    "os.spawnlpe",
    "os.spawnv",
    "os.spawnve",
    "os.spawnvp",
    "os.spawnvpe",
    "os.system",
    "runpy.run_module",
    "runpy.run_path",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
    "subprocess.run",
}


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _checker_reference(value: str) -> bool:
    normalized = value.replace("\\", "/").casefold()
    return (
        normalized == INSTALL_CHECKER_MODULE
        or normalized == f"{INSTALL_CHECKER_MODULE}.py"
        or normalized == f"scripts.{INSTALL_CHECKER_MODULE}"
        or normalized.endswith(f".{INSTALL_CHECKER_MODULE}")
        or normalized.endswith(f"/{INSTALL_CHECKER_MODULE}")
        or normalized == INSTALL_CHECKER_RELATIVE
        or normalized.endswith(f"/{INSTALL_CHECKER_RELATIVE}")
        or normalized.endswith(f"/{INSTALL_CHECKER_MODULE}.py")
    )


def _static_string_values(
    node: ast.AST,
    static_names: dict[str, set[str]] | None = None,
) -> set[str]:
    names = static_names or {}
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Name):
        return set(names.get(node.id, set()))
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        values: set[str] = set()
        for item in node.elts:
            values.update(_static_string_values(item, names))
        return values
    if isinstance(node, ast.JoinedStr):
        values = [""]
        for item in node.values:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                values = [prefix + item.value for prefix in values]
                continue
            if isinstance(item, ast.FormattedValue):
                nested = _static_string_values(item.value, names)
                if not nested:
                    return set()
                values = [prefix + value for prefix in values for value in nested]
                continue
            return set()
        return set(values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Div)):
        left = _static_string_values(node.left, names)
        right = _static_string_values(node.right, names)
        if not left or not right:
            return set()
        separator = "/" if isinstance(node.op, ast.Div) else ""
        return {
            f"{left_value}{separator}{right_value}"
            for left_value in left
            for right_value in right
        }
    if isinstance(node, ast.Call):
        name = _call_name(node.func)
        if name in {"str", "os.fspath"} and len(node.args) == 1:
            return _static_string_values(node.args[0], names)
        if name in {"Path", "PurePath", "PurePosixPath", "PureWindowsPath", "os.path.join"}:
            parts = [_static_string_values(arg, names) for arg in node.args]
            if not parts or any(not item for item in parts):
                return set()
            values = {""}
            for part in parts:
                values = {
                    f"{prefix}/{value}".strip("/")
                    for prefix in values
                    for value in part
                }
            return values
    return set()


def _node_contains_checker_reference(
    node: ast.AST,
    static_names: dict[str, set[str]] | None = None,
) -> bool:
    if any(
        _checker_reference(value)
        for value in _static_string_values(node, static_names)
    ):
        return True
    try:
        source = ast.unparse(node)
    except (AttributeError, ValueError):
        return False
    return _checker_reference(source) or INSTALL_CHECKER_MODULE.casefold() in source.casefold()


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    supported = {item.rsplit(".", 1)[0] for item in RUNTIME_LOADING_CALLS if "." in item}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                root = item.name.split(".", 1)[0]
                if root in supported:
                    aliases[item.asname or root] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root not in supported:
                continue
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"
    return aliases


def _canonical_call_name(node: ast.AST, aliases: dict[str, str]) -> str:
    raw = _call_name(node)
    if not raw:
        return raw
    first, separator, remainder = raw.partition(".")
    replacement = aliases.get(first)
    if replacement is None:
        return raw
    return f"{replacement}.{remainder}" if separator else replacement


def _assignment_targets(node: ast.Assign | ast.AnnAssign) -> set[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {
        item.id
        for target in targets
        for item in ast.walk(target)
        if isinstance(item, ast.Name)
    }


def _checker_couplings_from_text(source: str, *, filename: str) -> list[str]:
    suffix = Path(filename).suffix.casefold()
    if suffix in SCRIPT_COUPLING_SUFFIXES:
        findings: set[str] = set()
        for raw_line in source.splitlines():
            line = raw_line.strip()
            folded = line.casefold()
            if not line:
                continue
            if suffix in {".bat", ".cmd"}:
                if folded.startswith("rem ") or folded.startswith("::"):
                    continue
            elif line.startswith("#"):
                continue
            normalized = line.replace("\\", "/").casefold()
            if INSTALL_CHECKER_RELATIVE in normalized:
                findings.add(f"script_reference:{INSTALL_CHECKER_RELATIVE}")
        return sorted(findings)

    tree = ast.parse(source, filename=filename)
    findings: set[str] = set()
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None
    ]
    static_names: dict[str, set[str]] = {}
    for _ in range(max(1, len(assignments))):
        changed = False
        for node in assignments:
            value = node.value
            assert value is not None
            values = _static_string_values(value, static_names)
            if not values:
                continue
            for target in _assignment_targets(node):
                previous = static_names.get(target, set())
                combined = previous | values
                if combined != previous:
                    static_names[target] = combined
                    changed = True
        if not changed:
            break
    checker_bound_names: set[str] = set()
    for node in assignments:
        value = node.value
        if value is None or not _node_contains_checker_reference(value, static_names):
            continue
        checker_bound_names.update(_assignment_targets(node))
    aliases = _import_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _checker_reference(alias.name):
                    findings.add(f"static_import:{alias.name}")
            continue
        if isinstance(node, ast.ImportFrom) and node.module:
            if _checker_reference(node.module):
                findings.add(f"static_import:{node.module}")
            continue
        if not isinstance(node, ast.Call):
            continue
        call_name = _canonical_call_name(node.func, aliases)
        if call_name not in RUNTIME_LOADING_CALLS:
            continue
        values = [*node.args, *(item.value for item in node.keywords)]
        for value in values:
            static_values = _static_string_values(value, static_names)
            references = sorted(
                item for item in static_values if _checker_reference(item)
            )
            if references:
                for reference in references:
                    findings.add(f"dynamic_call:{call_name}:{reference}")
                continue
            for nested in ast.walk(value):
                if isinstance(nested, ast.Name) and nested.id in checker_bound_names:
                    findings.add(f"dynamic_call:{call_name}:bound:{nested.id}")
    return sorted(findings)


def _checker_couplings(path: Path) -> list[str]:
    return _checker_couplings_from_text(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )


def _self_test() -> dict[str, Any]:
    cases = {
        "legitimate_preload_identity": (
            "import hashlib\n"
            "profile_hash = hashlib.sha256(b'profile').hexdigest()\n"
            "court_skill_hash = hashlib.sha256(b'skill').hexdigest()\n",
            set(),
            ".py",
        ),
        "static_import": (
            "from check_active_copy_hashes import check\n",
            {"static_import:check_active_copy_hashes"},
            ".py",
        ),
        "static_dotted_import": (
            "import scripts.check_active_copy_hashes\n",
            {"static_import:scripts.check_active_copy_hashes"},
            ".py",
        ),
        "static_dotted_from": (
            "from scripts.check_active_copy_hashes import check\n",
            {"static_import:scripts.check_active_copy_hashes"},
            ".py",
        ),
        "dynamic_import": (
            "import importlib\nimportlib.import_module('check_active_copy_hashes')\n",
            {"dynamic_call:importlib.import_module:check_active_copy_hashes"},
            ".py",
        ),
        "runpy_path": (
            "import runpy\nrunpy.run_path('scripts/check_active_copy_hashes.py')\n",
            {"dynamic_call:runpy.run_path:scripts/check_active_copy_hashes.py"},
            ".py",
        ),
        "subprocess_call": (
            "import subprocess\nsubprocess.run(['python', 'scripts/check_active_copy_hashes.py'])\n",
            {"dynamic_call:subprocess.run:scripts/check_active_copy_hashes.py"},
            ".py",
        ),
        "bound_subprocess_call": (
            "from pathlib import Path\n"
            "import subprocess\n"
            "checker = Path('scripts/check_active_copy_hashes.py')\n"
            "subprocess.run(['python', str(checker)])\n",
            {"dynamic_call:subprocess.run:scripts/check_active_copy_hashes.py"},
            ".py",
        ),
        "concatenated_subprocess_call": (
            "import subprocess\n"
            "subprocess.run(['python', 'scripts/' + 'check_active_copy_hashes.py'])\n",
            {"dynamic_call:subprocess.run:scripts/check_active_copy_hashes.py"},
            ".py",
        ),
        "path_join_subprocess_call": (
            "from pathlib import Path\n"
            "import subprocess\n"
            "checker = Path('scripts') / 'check_active_copy_hashes.py'\n"
            "subprocess.run(['python', str(checker)])\n",
            {"dynamic_call:subprocess.run:scripts/check_active_copy_hashes.py"},
            ".py",
        ),
        "aliased_subprocess_call": (
            "import subprocess as sp\n"
            "sp.run(['python', 'scripts/check_active_copy_hashes.py'])\n",
            {"dynamic_call:subprocess.run:scripts/check_active_copy_hashes.py"},
            ".py",
        ),
        "two_level_path_binding": (
            "from pathlib import Path\n"
            "import subprocess\n"
            "name = 'check_active_copy_hashes'\n"
            "checker = Path('scripts') / (name + '.py')\n"
            "subprocess.run(['python', str(checker)])\n",
            {"dynamic_call:subprocess.run:scripts/check_active_copy_hashes.py"},
            ".py",
        ),
        "spawnv_call": (
            "import os\n"
            "os.spawnv(0, 'python', ['python', 'scripts/check_active_copy_hashes.py'])\n",
            {"dynamic_call:os.spawnv:scripts/check_active_copy_hashes.py"},
            ".py",
        ),
        "powershell_call": (
            "& python -B scripts/check_active_copy_hashes.py --json\n",
            {"script_reference:scripts/check_active_copy_hashes.py"},
            ".ps1",
        ),
        "cmd_call": (
            "@python -B scripts\\check_active_copy_hashes.py --json\n",
            {"script_reference:scripts/check_active_copy_hashes.py"},
            ".cmd",
        ),
        "shell_call": (
            "python -B scripts/check_active_copy_hashes.py --json\n",
            {"script_reference:scripts/check_active_copy_hashes.py"},
            ".sh",
        ),
        "shell_comment_only": (
            "# scripts/check_active_copy_hashes.py is repository-only\n",
            set(),
            ".sh",
        ),
    }
    failures: list[str] = []
    evidence: dict[str, list[str]] = {}
    for name, (source, expected, suffix) in cases.items():
        try:
            actual = set(
                _checker_couplings_from_text(source, filename=f"{name}{suffix}")
            )
        except SyntaxError as exc:
            failures.append(f"{name}:unexpected_syntax_error:{exc.msg}")
            evidence[name] = []
            continue
        evidence[name] = sorted(actual)
        if actual != expected:
            failures.append(
                f"{name}:expected={sorted(expected)!r}:actual={sorted(actual)!r}"
            )
    return {
        "schema": "court.install_checker_isolation_self_test.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "evidence": evidence,
        "failures": failures,
    }


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


def _safe_projection_relative(value: str) -> Path:
    relative = Path(value)
    if (
        relative == Path(".")
        or relative.is_absolute()
        or bool(relative.anchor)
        or bool(relative.drive)
        or ".." in relative.parts
    ):
        raise ValueError(f"unsafe projected path:{value}")
    return relative


def _is_link_or_reparse(value: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(value.st_mode) or bool(
        reparse_flag and getattr(value, "st_file_attributes", 0) & reparse_flag
    )


def _safe_projected_path(relative: Path) -> Path:
    path = ROOT
    for part in relative.parts:
        path = path / part
        try:
            value = path.lstat()
        except FileNotFoundError as exc:
            raise ValueError(f"projected path missing:{relative.as_posix()}") from exc
        if _is_link_or_reparse(value):
            raise ValueError(f"projected path contains a link or reparse point:{path}")
    return path


def _safe_projected_tree(root: Path) -> set[str]:
    files: set[str] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                path = Path(entry.path)
                value = entry.stat(follow_symlinks=False)
                if _is_link_or_reparse(value):
                    raise ValueError(
                        f"projected path contains a link or reparse point:{path}"
                    )
                if stat.S_ISDIR(value.st_mode):
                    stack.append(path)
                elif stat.S_ISREG(value.st_mode):
                    relative = path.relative_to(ROOT)
                    if "__pycache__" not in relative.parts and path.suffix.lower() != ".pyc":
                        files.add(relative.as_posix())
                else:
                    raise ValueError(f"projected path is not regular:{path}")
    return files


def _projected_files(raw_paths: list[str]) -> set[str]:
    files: set[str] = set()
    for value in raw_paths:
        relative = _safe_projection_relative(value)
        path = _safe_projected_path(relative)
        metadata = path.lstat()
        if stat.S_ISREG(metadata.st_mode):
            files.add(relative.as_posix())
        elif stat.S_ISDIR(metadata.st_mode):
            files.update(_safe_projected_tree(path))
        else:
            raise ValueError(f"projected path is not regular:{relative.as_posix()}")
    return files


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
    repository_only = projections.get("repository_only")
    if (
        not isinstance(repository_only, list)
        or INSTALL_CHECKER_RELATIVE not in repository_only
    ):
        failures.append("checker_repository_only_declaration_missing")
    if not (ROOT / INSTALL_CHECKER_RELATIVE).is_file():
        failures.append("checker_source_missing")
    cli_public = projections.get("cli_public")
    if not isinstance(cli_public, list) or any(not isinstance(item, str) for item in cli_public):
        failures.append("cli_public:projection_list_invalid")
        cli_public = []
    for target in ("shared_agents", "portable_current_tool"):
        raw_paths = projections.get(target)
        if not isinstance(raw_paths, list) or any(not isinstance(item, str) for item in raw_paths):
            failures.append(f"{target}:projection_list_invalid")
            continue
        combined_paths = [*raw_paths, *cli_public]
        projected = set(combined_paths)
        projected_files = _projected_files(combined_paths)
        projected_coverage = projected | projected_files
        checker_projected = (
            [INSTALL_CHECKER_RELATIVE]
            if INSTALL_CHECKER_RELATIVE in projected_files
            else []
        )
        missing_handlers: list[str] = []
        for executable in sorted(fast_open_handlers):
            if executable not in projected_coverage:
                missing_handlers.append(f"court open --fast:{executable}")

        missing_imports: list[str] = []
        checker_couplings: list[str] = []
        for relative in sorted(projected_files):
            path = ROOT / relative
            suffix = path.suffix.casefold()
            if not path.is_file():
                continue
            if suffix == ".py":
                for dependency in sorted(_local_imports(path, local_modules)):
                    if dependency not in projected_coverage:
                        missing_imports.append(f"{relative}->{dependency}")
            if suffix == ".py" or suffix in SCRIPT_COUPLING_SUFFIXES:
                for coupling in _checker_couplings(path):
                    checker_couplings.append(f"{relative}->{coupling}")

        evidence[target] = {
            "missing_cli_handlers": sorted(set(missing_handlers)),
            "missing_local_imports": sorted(set(missing_imports)),
            "checker_projected": checker_projected,
            "forbidden_checker_couplings": sorted(set(checker_couplings)),
        }
        failures.extend(
            f"{target}:cli_handler_not_projected:{item}"
            for item in evidence[target]["missing_cli_handlers"]
        )
        failures.extend(
            f"{target}:local_import_not_projected:{item}"
            for item in evidence[target]["missing_local_imports"]
        )
        failures.extend(
            f"{target}:install_checker_projected:{item}"
            for item in evidence[target]["checker_projected"]
        )
        failures.extend(
            f"{target}:install_checker_runtime_coupling:{item}"
            for item in evidence[target]["forbidden_checker_couplings"]
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
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        result = _self_test()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
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
