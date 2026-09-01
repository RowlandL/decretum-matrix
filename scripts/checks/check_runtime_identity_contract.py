"""Verify runtime selection is content-bound and emits an explicit identity receipt."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = ROOT / "bin" / "decretum-matrix.py"
IDENTITY_SCHEMA = "court.runtime_identity.v1"


def _load_launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("decretum_matrix_runtime_identity_probe", LAUNCHER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("launcher_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_runtime(root: Path, *, version: str, skill: str, cli: str) -> None:
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "SKILL.md").write_text(skill, encoding="utf-8")
    (root / "scripts" / "court_cli.py").write_text(cli, encoding="utf-8")


def _digest(root: Path) -> str:
    digest = hashlib.sha256()
    for relative in ("VERSION", "SKILL.md", "scripts/court_cli.py"):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def evaluate() -> dict[str, Any]:
    launcher = _load_launcher()
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        package_root = temp / "package"
        home = temp / "home"
        installed_root = home / ".agents" / "skills" / "decretum-matrix"
        _write_runtime(
            package_root,
            version="beta-test",
            skill="source skill\n",
            cli="print('source runtime')\n",
        )
        _write_runtime(
            installed_root,
            version="beta-test",
            skill="divergent installed skill\n",
            cli="print('divergent installed runtime')\n",
        )
        source_digest = _digest(package_root)
        installed_digest = _digest(installed_root)
        selected = launcher._canonical_runtime_root(package_root, home=home)
        selected_root = str(selected) if selected is not None else None
        if selected is not None and Path(selected).resolve() == installed_root.resolve():
            failures.append("runtime_same_version_content_drift_accepted")

    launcher_source = LAUNCHER_PATH.read_text(encoding="utf-8")
    required_receipt_fields = ("root", "version", "source_kind", "content_digest")
    if IDENTITY_SCHEMA not in launcher_source or any(
        f'"{field}"' not in launcher_source for field in required_receipt_fields
    ):
        failures.append("runtime_identity_receipt_missing")

    return {
        "schema": "court.runtime_identity_contract_check.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": "RUNTIME_IDENTITY_SINGLE_AUTHORITY",
        "evidence": {
            "source_digest": source_digest,
            "installed_digest": installed_digest,
            "same_declared_version": True,
            "selected_root": selected_root,
            "required_receipt_schema": IDENTITY_SCHEMA,
            "required_receipt_fields": list(required_receipt_fields),
        },
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        result = {
            "schema": "court.runtime_identity_contract_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "RUNTIME_IDENTITY_SINGLE_AUTHORITY",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"RUNTIME_IDENTITY_SINGLE_AUTHORITY={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())



