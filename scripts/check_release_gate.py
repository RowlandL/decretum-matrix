"""Read-only release gate for court-capability-router source and package state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from typing import Iterable

from release_gate_manifest import (
    ReleaseGateManifestError,
    expand_step_command,
    load_release_manifest,
    selected_release_steps,
)


ROOT = Path(__file__).resolve().parents[1]


def run_step(
    name: str,
    command: list[str],
    *,
    gate_class: str = "source",
    timeout: int = 120,
    allowed_returncodes: Iterable[int] = (0,),
) -> dict[str, object]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = f"step timed out after {timeout} seconds"
        if exc.stdout:
            output += f"; stdout={str(exc.stdout)[-2000:]}"
        if exc.stderr:
            output += f"; stderr={str(exc.stderr)[-2000:]}"
        return {
            "name": name,
            "gate_class": gate_class,
            "status": "FAILED",
            "exit_code": None,
            "command": " ".join(command),
            "output": output,
            "failure_kind": "timeout",
        }
    except OSError as exc:
        return {
            "name": name,
            "gate_class": gate_class,
            "status": "FAILED",
            "exit_code": None,
            "command": " ".join(command),
            "output": str(exc),
            "failure_kind": "process_start_error",
        }
    allowed = set(allowed_returncodes)
    output = (completed.stdout + completed.stderr).strip()
    return {
        "name": name,
        "gate_class": gate_class,
        "status": "PASSED" if completed.returncode in allowed else "FAILED",
        "exit_code": completed.returncode,
        "command": " ".join(command),
        "output": output[:4000],
    }


def validate_package(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "name": "package_validation",
            "status": "FAILED",
            "path": str(path),
            "problems": ["package_missing"],
        }
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from package_skill import validate_zip  # type: ignore

        entry_count, problems = validate_zip(path)
    except Exception as exc:  # pragma: no cover - defensive CLI reporting
        return {
            "name": "package_validation",
            "status": "FAILED",
            "path": str(path),
            "problems": [f"package_validation_error:{exc}"],
        }
    return {
        "name": "package_validation",
        "status": "PASSED" if not problems else "FAILED",
        "path": str(path),
        "entry_count": entry_count,
        "problems": problems,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    parser.add_argument("--package", type=Path, help="Optional package zip to validate without building a new package.")
    parser.add_argument("--require-package", action="store_true", help="Fail if --package is not supplied.")
    parser.add_argument("--skip-active-copies", action="store_true", help="Skip active copy hash validation.")
    parser.add_argument("--skip-runtime", action="store_true", help="Skip read-only superCC runtime diagnose.")
    args = parser.parse_args()

    try:
        manifest = load_release_manifest()
    except ReleaseGateManifestError as exc:
        failure = {
            "name": "release_manifest_policy",
            "gate_class": "source",
            "status": "FAILED",
            "exit_code": None,
            "command": "",
            "output": str(exc),
            "failure_kind": "manifest_invalid",
        }
        result = {
            "ok": False,
            "schema": "court.release_gate.v1",
            "release_gate": "FAILED",
            "source_gate": "FAILED",
            "installation_gate": "NOT_EVALUATED",
            "runtime_gate": "NOT_EVALUATED",
            "package_gate": {
                "name": "package_validation",
                "status": "NOT_EVALUATED",
                "path": None,
                "problems": [],
            },
            "steps": [],
            "failed": [failure],
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"RELEASE_GATE_FAILED steps=0 failed=1 package_gate=NOT_EVALUATED")
            print(f"FAILED {failure['name']}: {failure['output']}")
        return 2
    manifest_steps = selected_release_steps(
        manifest,
        include_active_copies=not args.skip_active_copies,
        include_runtime=not args.skip_runtime,
    )
    steps = [
        run_step(
            str(step["name"]),
            expand_step_command(step),
            gate_class=str(step["gate_class"]),
            timeout=int(step["timeout"]),
            allowed_returncodes=step["allowed_returncodes"],  # type: ignore[arg-type]
        )
        for step in manifest_steps
    ]

    package_gate: dict[str, object]
    if args.package:
        package_gate = validate_package(args.package.resolve())
    elif args.require_package:
        package_gate = {
            "name": "package_validation",
            "status": "FAILED",
            "path": None,
            "problems": ["package_required_but_not_supplied"],
        }
    else:
        package_gate = {
            "name": "package_validation",
            "status": "NOT_EVALUATED",
            "path": None,
            "problems": [],
        }

    failed = [step for step in steps if step["status"] != "PASSED"]
    source_failed = [step for step in failed if step.get("gate_class") == "source"]
    installation_failed = [step for step in failed if step.get("gate_class") == "installation"]
    runtime_failed = [step for step in failed if step.get("gate_class") == "runtime"]
    if package_gate["status"] == "FAILED":
        failed.append(package_gate)
    result = {
        "ok": not failed,
        "schema": "court.release_gate.v1",
        "release_gate": "PASSED" if not failed else "FAILED",
        "source_gate": "PASSED" if not source_failed else "FAILED",
        "installation_gate": "PASSED" if not installation_failed else "FAILED",
        "runtime_gate": (
            "NOT_EVALUATED"
            if args.skip_runtime
            else ("PASSED" if not runtime_failed else "FAILED")
        ),
        "package_gate": package_gate,
        "steps": steps,
        "failed": failed,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"RELEASE_GATE_{result['release_gate']} "
            f"steps={len(steps)} failed={len(failed)} package_gate={package_gate['status']}"
        )
        for item in failed:
            print(f"FAILED {item['name']}: {item.get('output') or item.get('problems')}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
