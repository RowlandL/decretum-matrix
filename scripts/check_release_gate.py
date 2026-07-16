"""Read-only release gate for court-capability-router source and package state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True
from typing import Iterable

from release_gate_manifest import (
    ReleaseGateManifestError,
    expand_step_command,
    load_release_manifest,
    selected_release_steps,
)

INSTALL_RECEIPT_SCHEMA = "court.install_current_agent_copy.result.v1"


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
        import package_skill  # type: ignore

        entry_count, problems = package_skill.validate_zip(path)
        with zipfile.ZipFile(path, "r") as archive:
            manifest_member = f"{package_skill.ROOT_NAME}/release-manifest.json"
            manifest_bytes = archive.read(manifest_member)
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
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "embedded_release_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "problems": problems,
    }


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def validate_install_receipt(
    path: Path,
    package_gate: dict[str, object],
) -> dict[str, object]:
    package_sha256 = package_gate.get("sha256")
    result: dict[str, object] = {
        "name": "install_receipt_validation",
        "gate_class": "installation",
        "status": "FAILED",
        "path": str(path),
        "source_package_sha256": None,
        "package_sha256": package_sha256,
        "problems": [],
    }
    problems = result["problems"]
    assert isinstance(problems, list)
    if not path.is_file():
        problems.append("install_receipt_missing")
        return result
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        problems.append("install_receipt_invalid_encoding")
        return result
    except json.JSONDecodeError:
        problems.append("install_receipt_invalid_json")
        return result
    except OSError:
        problems.append("install_receipt_read_error")
        return result
    if not isinstance(receipt, dict):
        problems.append("install_receipt_not_object")
        return result
    if receipt.get("schema") != INSTALL_RECEIPT_SCHEMA:
        problems.append("install_receipt_schema_invalid")
    if receipt.get("ok") is not True:
        problems.append("install_receipt_not_successful")
    if receipt.get("status") != "INSTALLED":
        problems.append("install_receipt_status_not_installed")
    source_package_sha256 = receipt.get("source_package_sha256")
    result["source_package_sha256"] = source_package_sha256
    if source_package_sha256 is None:
        problems.append("source_package_sha256_missing")
    elif not _is_sha256(source_package_sha256):
        problems.append("source_package_sha256_invalid")
    if not _is_sha256(package_sha256):
        problems.append("package_sha256_unavailable")
    elif _is_sha256(source_package_sha256) and source_package_sha256 != package_sha256:
        problems.append("source_package_sha256_mismatch")
    if not problems:
        result["status"] = "PASSED"
    return result


def evaluate_install_receipt_gate(
    *,
    phase: str,
    require_package: bool,
    install_receipt: Path | None,
    package_gate: dict[str, object],
) -> dict[str, object]:
    if phase != "post-install":
        return {
            "name": "install_receipt_validation",
            "gate_class": "installation",
            "status": "NOT_RUN",
            "path": None,
            "source_package_sha256": None,
            "package_sha256": package_gate.get("sha256"),
            "problems": [],
            "reason": "install_receipt_not_required",
        }
    if install_receipt is None:
        return {
            "name": "install_receipt_validation",
            "gate_class": "installation",
            "status": "FAILED",
            "path": None,
            "source_package_sha256": None,
            "package_sha256": package_gate.get("sha256"),
            "problems": ["install_receipt_required_but_not_supplied"],
        }
    return validate_install_receipt(install_receipt.resolve(), package_gate)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    parser.add_argument("--package", type=Path, help="Optional package zip to validate without building a new package.")
    parser.add_argument("--require-package", action="store_true", help="Fail if --package is not supplied.")
    parser.add_argument(
        "--install-receipt",
        type=Path,
        help="Post-install receipt JSON binding the installed source_package_sha256 to --package.",
    )
    parser.add_argument("--skip-active-copies", action="store_true", help="Skip active copy hash validation.")
    parser.add_argument("--skip-runtime", action="store_true", help="Skip read-only superCC runtime diagnose.")
    parser.add_argument(
        "--phase",
        choices=("pre-install", "post-install", "full"),
        default="full",
        help="Select source/package, installed-host, or complete release gates.",
    )
    parser.add_argument(
        "--candidate",
        action="store_true",
        help="Alias for --phase pre-install; requires a package and skips installed-host gates.",
    )
    args = parser.parse_args()
    if args.candidate and args.phase not in {"full", "pre-install"}:
        parser.error("--candidate conflicts with --phase post-install")
    phase = "pre-install" if args.candidate else args.phase

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
            "gate_mode": phase,
            "release_gate": "FAILED",
            "source_gate": "FAILED",
            "installation_gate": "NOT_EVALUATED",
            "runtime_gate": "NOT_EVALUATED",
            "runtime_reason": "release_manifest_invalid",
            "package_gate": {
                "name": "package_validation",
                "status": "NOT_RUN",
                "path": None,
                "problems": [],
                "reason": "release_manifest_invalid",
            },
            "install_receipt_gate": {
                "name": "install_receipt_validation",
                "gate_class": "installation",
                "status": "NOT_RUN",
                "path": None,
                "problems": [],
                "reason": "release_manifest_invalid",
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
        include_active_copies=phase != "pre-install" and not args.skip_active_copies,
        include_runtime=phase != "pre-install" and not args.skip_runtime,
    )
    if phase == "pre-install":
        manifest_steps = [
            step
            for step in manifest_steps
            if step.get("gate_class") == "source" and step.get("name") != "catalog_strict"
        ]
    elif phase == "post-install":
        manifest_steps = [
            step
            for step in manifest_steps
            if step.get("gate_class") in {"installation", "runtime"}
        ]
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
    elif args.require_package or phase in {"pre-install", "post-install"}:
        package_gate = {
            "name": "package_validation",
            "status": "FAILED",
            "path": None,
            "problems": ["package_required_but_not_supplied"],
        }
    else:
        package_gate = {
            "name": "package_validation",
            "status": "NOT_RUN",
            "path": None,
            "problems": [],
            "reason": "package_not_supplied",
        }

    install_receipt_gate = evaluate_install_receipt_gate(
        phase=phase,
        require_package=args.require_package,
        install_receipt=args.install_receipt,
        package_gate=package_gate,
    )

    failed = [step for step in steps if step["status"] != "PASSED"]
    source_failed = [step for step in failed if step.get("gate_class") == "source"]
    installation_failed = [step for step in failed if step.get("gate_class") == "installation"]
    runtime_failed = [step for step in failed if step.get("gate_class") == "runtime"]
    if package_gate["status"] == "FAILED":
        failed.append(package_gate)
    if install_receipt_gate["status"] == "FAILED":
        failed.append(install_receipt_gate)
        installation_failed.append(install_receipt_gate)
    result = {
        "ok": not failed,
        "schema": "court.release_gate.v1",
        "gate_mode": phase,
        "release_gate": "PASSED" if not failed else "FAILED",
        "source_gate": (
            "NOT_APPLICABLE"
            if phase == "post-install"
            else ("PASSED" if not source_failed else "FAILED")
        ),
        "installation_gate": (
            "NOT_APPLICABLE"
            if phase == "pre-install"
            else ("PASSED" if not installation_failed else "FAILED")
        ),
        "runtime_gate": (
            "NOT_APPLICABLE"
            if phase == "pre-install" or args.skip_runtime
            else ("PASSED" if not runtime_failed else "FAILED")
        ),
        "runtime_reason": (
            "candidate_preinstall"
            if phase == "pre-install"
            else ("runtime_not_selected" if args.skip_runtime else "runtime_selected")
        ),
        "package_gate": package_gate,
        "install_receipt_gate": install_receipt_gate,
        "steps": steps,
        "failed": failed,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"RELEASE_GATE_{result['release_gate']} "
            f"steps={len(steps)} failed={len(failed)} package_gate={package_gate['status']} "
            f"install_receipt_gate={install_receipt_gate['status']}"
        )
        for item in failed:
            print(f"FAILED {item['name']}: {item.get('output') or item.get('problems')}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
