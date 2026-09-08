"""Read-only release gate for Decretum Matrix source and package state."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from unittest.mock import patch

sys.dont_write_bytecode = True
from typing import Iterable

from release_gate_manifest import (
    REQUIRED_CHECK_CONTRACTS,
    REQUIRED_CHECK_IDS,
    ReleaseGateManifestError,
    expand_step_command,
    load_release_manifest,
    selected_release_steps,
    validate_release_manifest,
)

INSTALL_RECEIPT_SCHEMA = "court.install_current_agent_copy.result.v1"
NATIVE_CAPTURE_RESULT_SCHEMA = "court.office.native_capture.result.v1"
NATIVE_EVIDENCE_CONTRACT_PASSED = "NATIVE_EVIDENCE_CONTRACT_PASSED"
NATIVE_EVIDENCE_AUTHORITY = "host_native_capture"


ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE_RELEASE_GATE_NAME = "governance_framework"
GOVERNANCE_RELEASE_GATE_CLASS = "source"
GOVERNANCE_RELEASE_GATE_COMMAND = ["$PYTHON", "scripts/check_governance_framework.py", "--json"]
GOVERNANCE_RELEASE_GATE_CONDITION = "always"
HIERARCHY_RELEASE_GATE_NAME = "court_dispatch_hierarchy"
HIERARCHY_RELEASE_GATE_CLASS = "source"
HIERARCHY_RELEASE_GATE_COMMAND = ["$PYTHON", "scripts/check_court_dispatch_hierarchy.py"]
HIERARCHY_RELEASE_GATE_CONDITION = "always"
MANDATORY_ARCHITECTURE_GATES = (
    (
        GOVERNANCE_RELEASE_GATE_NAME,
        GOVERNANCE_RELEASE_GATE_CLASS,
        GOVERNANCE_RELEASE_GATE_COMMAND,
        GOVERNANCE_RELEASE_GATE_CONDITION,
    ),
    (
        HIERARCHY_RELEASE_GATE_NAME,
        HIERARCHY_RELEASE_GATE_CLASS,
        HIERARCHY_RELEASE_GATE_COMMAND,
        HIERARCHY_RELEASE_GATE_CONDITION,
    ),
)
GIT_INDEX_VIEW_STEPS = frozenset(
    {
        "git_index_fixture",
        "unified_cli",
        "release_payload_manifest",
        "package_privacy_regressions",
        "release_artifact_builder",
    }
)
MAX_CAPTURED_OUTPUT_CHARS = 4000
DOMAIN_PASS_STATUSES = frozenset({"PASS", "PASSED", "OK", "SUCCESS", "CI_SCOPE_PASSED"})
DOMAIN_FAIL_STATUSES = frozenset(
    {
        "FAIL",
        "FAILED",
        "CANCELLED",
        "MISSING",
        "NEUTRAL",
        "NOT_APPLICABLE",
        "NOT_CONFIGURED",
        "NOT_RUN",
        "SKIPPED",
        "STALE",
        "TIMEOUT",
    }
)
PROVENANCE_FIELDS = (
    "source_commit",
    "artifact_ref",
    "build_id",
    "release_label",
    "installation_id",
    "transaction_id",
)
SOURCE_REQUIRED_IDS = tuple(
    str(check["id"])
    for check in REQUIRED_CHECK_CONTRACTS
    if check["ci_job"] == "source-contracts"
)


def _unwrap_domain_result(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    nested = value.get("domain_result")
    if isinstance(nested, dict):
        return nested
    nested = value.get("result")
    if isinstance(nested, dict) and (
        "ok" in nested or "status" in nested or "result" in nested
    ):
        return nested
    return value


def parse_domain_result(stdout: str, stderr: str) -> dict[str, object] | None:
    """Extract an optional structured result without treating plain text as JSON."""

    for stream in (stdout, stderr):
        text = stream.strip()
        if not text:
            continue
        candidates = [text, *reversed(text.splitlines())]
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            domain = _unwrap_domain_result(parsed)
            if domain is not None:
                return domain
    return None


def domain_result_status(domain_result: dict[str, object] | None) -> str:
    """Classify a structured result; absent domain JSON remains unknown."""

    if domain_result is None:
        return "UNAVAILABLE"
    if "ok" in domain_result:
        value = domain_result["ok"]
        if type(value) is not bool:
            return "MALFORMED"
        return "PASSED" if value else "FAILED"
    status = domain_result.get("status")
    if isinstance(status, str):
        normalized = status.strip().upper()
        if normalized in DOMAIN_PASS_STATUSES:
            return "PASSED"
        if normalized in DOMAIN_FAIL_STATUSES:
            return normalized
    return "UNKNOWN"


def validate_domain_contract(
    stdout: str,
    stderr: str,
    contract: dict[str, object] | None = None,
) -> dict[str, object]:
    """Validate a declared domain shape without treating unknown output as success."""

    domain_result = parse_domain_result(stdout, stderr)
    active_contract = contract
    if active_contract is None:
        if domain_result is None:
            return {
                "status": "UNAVAILABLE",
                "enforced": False,
                "reason": "non_json_legacy_output",
                "domain_result": None,
            }
        active_contract = {"kind": "json", "required_fields": ["ok"]}
    kind = active_contract.get("kind")
    if kind == "sentinel":
        success = active_contract.get("success")
        lines = [line.strip() for line in (stdout + "\n" + stderr).splitlines()]
        if isinstance(success, str) and any(line == success for line in lines):
            return {
                "status": "PASSED",
                "enforced": True,
                "reason": "success_sentinel",
                "domain_result": domain_result,
            }
        return {
            "status": "FAILED",
            "enforced": True,
            "reason": "domain_success_sentinel_missing",
            "domain_result": domain_result,
        }
    if kind != "json":
        return {
            "status": "FAILED",
            "enforced": True,
            "reason": "domain_contract_unknown",
            "domain_result": domain_result,
        }
    if domain_result is None:
        return {
            "status": "FAILED",
            "enforced": True,
            "reason": "domain_result_unparseable_or_missing",
            "domain_result": None,
        }
    required_fields = active_contract.get("required_fields", [])
    if not isinstance(required_fields, list) or any(
        not isinstance(field, str) or field not in domain_result
        for field in required_fields
    ):
        return {
            "status": "FAILED",
            "enforced": True,
            "reason": "domain_required_field_missing",
            "domain_result": domain_result,
        }
    if "ok" in domain_result:
        if type(domain_result.get("ok")) is not bool:
            reason = "domain_ok_not_boolean"
        elif domain_result.get("ok") is not True:
            reason = "domain_ok_false"
        else:
            reason = ""
        if reason:
            return {
                "status": "FAILED",
                "enforced": True,
                "reason": reason,
                "domain_result": domain_result,
            }
    if "status" in domain_result:
        status = domain_result.get("status")
        if not isinstance(status, str) or status.strip().upper() not in DOMAIN_PASS_STATUSES:
            return {
                "status": "FAILED",
                "enforced": True,
                "reason": "domain_status_not_success",
                "domain_result": domain_result,
            }
    return {
        "status": "PASSED",
        "enforced": True,
        "reason": "structured_success",
        "domain_result": domain_result,
    }


def validate_evidence_provenance(
    record: object,
    *,
    required: Iterable[str] = (),
    expected: dict[str, str] | None = None,
) -> list[str]:
    """Return stable, source-safe provenance failures for a domain record."""

    if not isinstance(record, dict):
        return ["provenance_record_not_object"]
    provenance = record.get("provenance", record)
    if not isinstance(provenance, dict):
        return ["provenance_not_object"]
    problems: list[str] = []
    for field in required:
        value = provenance.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{field}_missing")
    for field, value in (expected or {}).items():
        actual = provenance.get(field)
        if actual != value:
            problems.append(f"{field}_mismatch")
    return problems


def _log_capture_root(step_name: str) -> Path:
    configured = os.environ.get("COURT_RELEASE_GATE_LOG_ROOT")
    if configured:
        root = Path(configured)
        root.mkdir(parents=True, exist_ok=True)
        return root
    return Path(tempfile.mkdtemp(prefix=f"decretum-release-gate-{step_name}-"))


def _write_log_capture(step_name: str, stdout: str, stderr: str) -> dict[str, object]:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", step_name)
    root = _log_capture_root(safe_name)
    stdout_path = root / f"{safe_name}.stdout.log"
    stderr_path = root / f"{safe_name}.stderr.log"
    try:
        stdout_path.write_bytes(stdout.encode("utf-8"))
        stderr_path.write_bytes(stderr.encode("utf-8"))
    except OSError as exc:
        return {
            "complete": False,
            "error": f"log_capture_write_failed:{exc}",
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
    capture = {
        "complete": True,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_bytes": len(stdout.encode("utf-8")),
        "stderr_bytes": len(stderr.encode("utf-8")),
    }
    if not _log_capture_complete(capture):
        capture["complete"] = False
        capture["error"] = "log_capture_readback_failed"
    return capture


def _log_capture_complete(capture: object) -> bool:
    if not isinstance(capture, dict):
        return False
    for stream in ("stdout", "stderr"):
        path_value = capture.get(f"{stream}_path")
        byte_count = capture.get(f"{stream}_bytes")
        if not isinstance(path_value, str) or type(byte_count) is not int:
            return False
        path = Path(path_value)
        try:
            if not path.is_file() or path.stat().st_size != byte_count:
                return False
        except OSError:
            return False
    return capture.get("complete") is True


def log_evidence_is_complete(result: object) -> bool:
    if not isinstance(result, dict) or result.get("log_complete") is not True:
        return False
    if "log_capture" not in result:
        return result.get("scope") != "candidate/install"
    return _log_capture_complete(result.get("log_capture"))


def _ci_log_capture_metadata_complete(value: object) -> bool:
    """Check the read-back metadata emitted by a CI source-contract job."""

    if not isinstance(value, dict) or value.get("complete") is not True:
        return False
    for field in ("stdout_path", "stderr_path"):
        path = value.get(field)
        if not isinstance(path, str) or not path.strip():
            return False
    for field in ("stdout_bytes", "stderr_bytes"):
        count = value.get(field)
        if type(count) is not int or count < 0:
            return False
    return True


def _expect_manifest_invalid(manifest: dict[str, object], expected_text: str) -> None:
    try:
        validate_release_manifest(manifest)
    except ReleaseGateManifestError as exc:
        if expected_text not in str(exc):
            raise AssertionError(
                f"expected {expected_text!r} in manifest validation error, got {exc!r}"
            ) from exc
    else:
        raise AssertionError(f"tampered architecture release gate unexpectedly passed: {expected_text}")


def _required_release_gate_self_test(
    manifest: dict[str, object],
    *,
    name: str,
    gate_class: str,
    command: list[str],
    condition: str,
) -> list[str]:
    steps = manifest.get("steps")
    if not isinstance(steps, list):
        raise AssertionError("release manifest steps are unavailable for architecture self-test")
    matching = [
        (index, step)
        for index, step in enumerate(steps)
        if isinstance(step, dict) and step.get("name") == name
    ]
    if len(matching) != 1:
        raise AssertionError(f"mandatory {name} release step must exist exactly once")
    step_index, required_step = matching[0]
    expected_contract = {
        "name": name,
        "gate_class": gate_class,
        "command": command,
        "condition": condition,
        "allowed_returncodes": [0],
    }
    for field, expected in expected_contract.items():
        if required_step.get(field) != expected:
            raise AssertionError(
                f"mandatory {name} release step {field} drifted: "
                f"expected {expected!r}, got {required_step.get(field)!r}"
            )

    cases: list[tuple[str, dict[str, object], str]] = []

    missing = deepcopy(manifest)
    missing["steps"].pop(step_index)  # type: ignore[index,union-attr]
    cases.append(("missing", missing, "external required-step policy"))

    renamed = deepcopy(manifest)
    renamed["steps"][step_index]["name"] = f"{name}_renamed"  # type: ignore[index]
    cases.append(("renamed", renamed, "external required-step policy"))

    reordered = deepcopy(manifest)
    reordered_steps = reordered["steps"]  # type: ignore[index]
    assert isinstance(reordered_steps, list)
    moved = reordered_steps.pop(step_index)
    reordered_steps.insert(max(0, step_index - 1), moved)
    cases.append(("reordered", reordered, "external required-step policy"))

    outside_source_phase = deepcopy(manifest)
    outside_source_phase["steps"][step_index]["gate_class"] = "installation"  # type: ignore[index]
    cases.append(("outside_source_phase", outside_source_phase, "gate_class drifted"))

    conditionalized = deepcopy(manifest)
    conditionalized["steps"][step_index]["condition"] = "active_copies_enabled"  # type: ignore[index]
    cases.append(("conditionalized", conditionalized, "condition drifted"))

    wrong_command = deepcopy(manifest)
    wrong_command["steps"][step_index]["command"] = [  # type: ignore[index]
        "$PYTHON",
        "scripts/check_court_dispatch_policy.py",
    ]
    cases.append(("wrong_command", wrong_command, "command drifted"))

    passed: list[str] = []
    for case_name, value, expected in cases:
        _expect_manifest_invalid(value, expected)
        passed.append(f"{name}_{case_name}")
    return passed


def run_hierarchy_release_gate_self_test(manifest: dict[str, object]) -> list[str]:
    passed: list[str] = []
    for name, gate_class, command, condition in MANDATORY_ARCHITECTURE_GATES:
        passed.extend(
            _required_release_gate_self_test(
                manifest,
                name=name,
                gate_class=gate_class,
                command=command,
                condition=condition,
            )
        )
    return passed


def run_required_check_contract_self_test(manifest: dict[str, object]) -> list[str]:
    """Verify that every stable T11/T13 evidence ID is present exactly once."""

    cases: list[tuple[str, dict[str, object], str]] = []
    missing = deepcopy(manifest)
    missing.pop("required_checks", None)
    cases.append(("missing", missing, "required_checks must be a list"))

    duplicate = deepcopy(manifest)
    checks = duplicate["required_checks"]
    assert isinstance(checks, list)
    checks.append(deepcopy(checks[0]))
    cases.append(("duplicate", duplicate, "exactly once"))

    wrong_id = deepcopy(manifest)
    checks = wrong_id["required_checks"]
    assert isinstance(checks, list)
    checks[0]["id"] = "supercc_truth_gates_duplicate"  # type: ignore[index]
    cases.append(("wrong_id", wrong_id, "stable evidence contract"))

    wrong_command = deepcopy(manifest)
    checks = wrong_command["required_checks"]
    assert isinstance(checks, list)
    checks[0]["command"] = ["$PYTHON", "scripts/check_release_gate.py"]  # type: ignore[index]
    cases.append(("wrong_command", wrong_command, "stable evidence contract"))

    passed: list[str] = []
    for name, value, expected in cases:
        _expect_manifest_invalid(value, expected)
        passed.append(f"required_checks_{name}")
    return passed


def run_domain_contract_self_test() -> dict[str, bool]:
    """Keep unknown, missing, and unparseable domain results fail-closed."""

    mystery = validate_domain_contract('{"status":"MYSTERY"}', "")
    missing_ok = validate_domain_contract('{"status":"PASS"}', "")
    unparseable_json = validate_domain_contract(
        "not-json",
        "",
        {"kind": "json", "required_fields": ["ok"]},
    )
    wrong_sentinel = validate_domain_contract(
        "OTHER_OK\n",
        "",
        {"kind": "sentinel", "success": "EXPECTED_OK"},
    )
    exact_sentinel = validate_domain_contract(
        "EXPECTED_OK\n",
        "",
        {"kind": "sentinel", "success": "EXPECTED_OK"},
    )
    valid_json = validate_domain_contract(
        '{"ok":true,"status":"PASS"}',
        "",
        {"kind": "json", "required_fields": ["ok", "status"]},
    )
    return {
        "mystery_rejected": mystery.get("status") == "FAILED",
        "missing_ok_rejected": missing_ok.get("status") == "FAILED",
        "unparseable_json_rejected": unparseable_json.get("status") == "FAILED",
        "wrong_sentinel_rejected": wrong_sentinel.get("status") == "FAILED",
        "exact_sentinel_accepted": exact_sentinel.get("status") == "PASSED",
        "valid_json_accepted": valid_json.get("status") == "PASSED",
    }


def run_log_capture_self_test() -> dict[str, bool]:
    """Keep summary truncation separate from complete external log evidence."""

    with tempfile.TemporaryDirectory(prefix="decretum-release-gate-logs-") as temp_text:
        previous = os.environ.get("COURT_RELEASE_GATE_LOG_ROOT")
        os.environ["COURT_RELEASE_GATE_LOG_ROOT"] = temp_text
        try:
            long_output = run_step(
                "long_output_fixture",
                [sys.executable, "-B", "-c", "print('x' * 5001)"],
                timeout=10,
            )
            if (
                long_output.get("status") != "PASSED"
                or long_output.get("summary_truncated") is not True
                or long_output.get("log_complete") is not True
                or not _log_capture_complete(long_output.get("log_capture"))
            ):
                raise AssertionError("long output with complete external logs was rejected")
            capture = long_output.get("log_capture")
            assert isinstance(capture, dict)
            stdout_path = capture.get("stdout_path")
            assert isinstance(stdout_path, str)
            Path(stdout_path).unlink()
            missing_log_rejected = not log_evidence_is_complete(long_output)

            with patch.object(subprocess, "run", side_effect=KeyboardInterrupt):
                interrupted = run_step(
                    "interrupted_fixture",
                    [sys.executable, "-B", "-c", "print('unreachable')"],
                )
            timeout = run_step(
                "timeout_fixture",
                [sys.executable, "-B", "-c", "import time; time.sleep(1)"],
                timeout=0.1,
            )
            if interrupted.get("failure_kind") != "interrupted":
                raise AssertionError("interrupted step did not remain a failure")
            if timeout.get("failure_kind") != "timeout":
                raise AssertionError("timeout step did not remain a failure")
            return {
                "long_output_summary_truncated": True,
                "long_output_log_complete": True,
                "missing_log_rejected": missing_log_rejected,
                "interrupted_failed": interrupted.get("status") == "FAILED",
                "timeout_failed": timeout.get("status") == "FAILED",
            }
        finally:
            if previous is None:
                os.environ.pop("COURT_RELEASE_GATE_LOG_ROOT", None)
            else:
                os.environ["COURT_RELEASE_GATE_LOG_ROOT"] = previous


def run_step(
    name: str,
    command: list[str],
    *,
    gate_class: str = "source",
    timeout: int = 120,
    allowed_returncodes: Iterable[int] = (0,),
    domain_contract: dict[str, object] | None = None,
) -> dict[str, object]:
    def failure_result(
        *,
        status: str,
        exit_code: int | None,
        output: str,
        stdout: str,
        stderr: str,
        failure_kind: str,
    ) -> dict[str, object]:
        combined = stdout + stderr
        log_capture = _write_log_capture(name, stdout, stderr)
        log_complete = _log_capture_complete(log_capture)
        domain_validation = validate_domain_contract(stdout, stderr, domain_contract)
        if not log_complete and failure_kind not in {"timeout", "interrupted"}:
            failure_kind = "log_capture_failed"
        return {
            "name": name,
            "gate_class": gate_class,
            "status": status,
            "exit_code": exit_code,
            "command": " ".join(command),
            "output": output[:MAX_CAPTURED_OUTPUT_CHARS],
            "stdout": stdout,
            "stderr": stderr,
            "domain_result": domain_validation.get("domain_result"),
            "domain_status": (
                domain_validation["status"]
                if domain_validation.get("enforced") is True
                else domain_result_status(domain_validation.get("domain_result"))
            ),
            "domain_contract": domain_contract,
            "domain_validation": domain_validation,
            "output_truncated": len(combined) > MAX_CAPTURED_OUTPUT_CHARS,
            "summary_truncated": len(combined) > MAX_CAPTURED_OUTPUT_CHARS,
            "log_complete": log_complete,
            "log_capture": log_capture,
            "failure_kind": failure_kind,
            "git_index_isolated": isolated_git_index is not None,
        }

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    isolated_git_index: Path | None = None
    source_git_index = env.get("GIT_INDEX_FILE")
    if source_git_index and name not in GIT_INDEX_VIEW_STEPS:
        env.pop("GIT_INDEX_FILE", None)
    elif source_git_index:
        try:
            source_path = Path(source_git_index).resolve(strict=True)
            if not source_path.is_file():
                raise OSError("GIT_INDEX_FILE is not a regular file")
            descriptor, isolated_text = tempfile.mkstemp(
                prefix=f"decretum-{name}-",
                suffix=".index",
                dir=source_path.parent,
            )
            os.close(descriptor)
            isolated_git_index = Path(isolated_text)
            shutil.copyfile(source_path, isolated_git_index)
            env["GIT_INDEX_FILE"] = str(isolated_git_index)
        except OSError as exc:
            return failure_result(
                status="FAILED",
                exit_code=None,
                output=str(exc),
                stdout="",
                stderr="",
                failure_kind="git_index_isolation_error",
            )
    try:
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
            stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
            combined = stdout + stderr
            return failure_result(
                status="FAILED",
                exit_code=None,
                output=f"step timed out after {timeout} seconds; {combined[-2000:]}",
                stdout=stdout,
                stderr=stderr,
                failure_kind="timeout",
            )
        except OSError as exc:
            return failure_result(
                status="FAILED",
                exit_code=None,
                output=str(exc),
                stdout="",
                stderr="",
                failure_kind="process_start_error",
            )
        except KeyboardInterrupt:
            return failure_result(
                status="FAILED",
                exit_code=None,
                output="step interrupted",
                stdout="",
                stderr="",
                failure_kind="interrupted",
            )
    finally:
        if isolated_git_index is not None:
            isolated_git_index.unlink(missing_ok=True)

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    combined = stdout + stderr
    output = combined.strip()
    output_truncated = len(combined) > MAX_CAPTURED_OUTPUT_CHARS
    domain_result = parse_domain_result(stdout, stderr)
    domain_status = domain_result_status(domain_result)
    domain_validation = validate_domain_contract(stdout, stderr, domain_contract)
    allowed = set(allowed_returncodes)
    failure_kind: str | None = None
    if completed.returncode not in allowed:
        status = "FAILED"
        failure_kind = "exit_code_not_allowed"
    elif domain_status in DOMAIN_FAIL_STATUSES or domain_status == "FAILED":
        status = "FAILED"
        failure_kind = "domain_result_failed"
    elif domain_status == "MALFORMED":
        status = "FAILED"
        failure_kind = "domain_result_malformed"
    elif domain_validation.get("enforced") is True and domain_validation.get("status") != "PASSED":
        status = "FAILED"
        failure_kind = str(domain_validation.get("reason") or "domain_contract_failed")
    else:
        status = "PASSED"
    log_capture = _write_log_capture(name, stdout, stderr)
    log_complete = _log_capture_complete(log_capture)
    if not log_complete:
        status = "FAILED"
        failure_kind = "log_capture_failed"
    return {
        "name": name,
        "gate_class": gate_class,
        "status": status,
        "exit_code": completed.returncode,
        "command": " ".join(command),
        "output": output[:MAX_CAPTURED_OUTPUT_CHARS],
        "stdout": stdout,
        "stderr": stderr,
        "domain_result": domain_result,
        "domain_status": (
            domain_validation["status"]
            if domain_validation.get("enforced") is True
            else domain_status
        ),
        "domain_contract": domain_contract,
        "domain_validation": domain_validation,
        "output_truncated": output_truncated,
        "summary_truncated": output_truncated,
        "log_complete": log_complete,
        "log_capture": log_capture,
        "failure_kind": failure_kind,
        "git_index_isolated": isolated_git_index is not None,
    }


def run_git_index_isolation_self_test() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="decretum-release-gate-index-") as temp_text:
        source = Path(temp_text) / "authority.index"
        source.write_bytes(b"authority-index")
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        previous = os.environ.get("GIT_INDEX_FILE")
        os.environ["GIT_INDEX_FILE"] = str(source)
        try:
            step = run_step(
                "git_index_fixture",
                [
                    sys.executable,
                    "-B",
                    "-c",
                    (
                        "from pathlib import Path; import os; "
                        "Path(os.environ['GIT_INDEX_FILE']).write_bytes(b'mutated')"
                    ),
                ],
            )
        finally:
            if previous is None:
                os.environ.pop("GIT_INDEX_FILE", None)
            else:
                os.environ["GIT_INDEX_FILE"] = previous
        after = hashlib.sha256(source.read_bytes()).hexdigest()
        if step.get("status") != "PASSED" or step.get("git_index_isolated") is not True:
            raise AssertionError("release step did not use an isolated Git index")
        if before != after:
            raise AssertionError("release step mutated the authoritative Git index")
        return {
            "status": "PASSED",
            "source_sha256": after,
            "step_git_index_isolated": True,
        }


def validate_package(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "name": "package_validation",
            "status": "FAILED",
            "path": str(path),
            "provenance": {},
            "problems": ["package_missing"],
        }
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import package_skill  # type: ignore

        entry_count, problems = package_skill.validate_zip(path)
        with zipfile.ZipFile(path, "r") as archive:
            manifest_member = f"{package_skill.ROOT_NAME}/release-manifest.json"
            manifest_bytes = archive.read(manifest_member)
        embedded_manifest = json.loads(manifest_bytes.decode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive CLI reporting
        return {
            "name": "package_validation",
            "status": "FAILED",
            "path": str(path),
            "provenance": {},
            "problems": [f"package_validation_error:{exc}"],
        }
    provenance = (
        {field: embedded_manifest.get(field) for field in PROVENANCE_FIELDS if field in embedded_manifest}
        if isinstance(embedded_manifest, dict)
        else {}
    )
    return {
        "name": "package_validation",
        "status": "PASSED" if not problems else "FAILED",
        "path": str(path),
        "entry_count": entry_count,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "embedded_release_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "provenance": provenance,
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
    *,
    required_provenance: Iterable[str] = (),
    expected_provenance: dict[str, str] | None = None,
) -> dict[str, object]:
    package_sha256 = package_gate.get("sha256")
    result: dict[str, object] = {
        "name": "install_receipt_validation",
        "gate_class": "installation",
        "status": "FAILED",
        "path": str(path),
        "source_package_sha256": None,
        "package_sha256": package_sha256,
        "provenance": {},
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
    provenance = {
        field: receipt.get(field)
        for field in PROVENANCE_FIELDS
        if field in receipt
    }
    result["provenance"] = provenance
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
    problems.extend(
        validate_evidence_provenance(
            provenance,
            required=required_provenance,
            expected=expected_provenance,
        )
    )
    package_provenance = package_gate.get("provenance")
    if isinstance(package_provenance, dict):
        for field in ("source_commit", "artifact_ref", "build_id", "release_label"):
            package_value = package_provenance.get(field)
            receipt_value = provenance.get(field)
            if (
                isinstance(package_value, str)
                and package_value
                and isinstance(receipt_value, str)
                and receipt_value
                and package_value != receipt_value
            ):
                problems.append(f"{field}_mismatch")
    if not problems:
        result["status"] = "PASSED"
    return result


def evaluate_install_receipt_gate(
    *,
    phase: str,
    require_package: bool,
    install_receipt: Path | None,
    package_gate: dict[str, object],
    required_provenance: Iterable[str] = (),
    expected_provenance: dict[str, str] | None = None,
) -> dict[str, object]:
    if phase not in {"post-install", "full"}:
        return {
            "name": "install_receipt_validation",
            "gate_class": "installation",
            "status": "NOT_RUN",
            "path": None,
            "source_package_sha256": None,
            "package_sha256": package_gate.get("sha256"),
            "provenance": {},
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
            "provenance": {},
            "problems": ["install_receipt_required_but_not_supplied"],
        }
    return validate_install_receipt(
        install_receipt.resolve(),
        package_gate,
        required_provenance=required_provenance,
        expected_provenance=expected_provenance,
    )


def _load_candidate_evidence(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"status": "FAILED", "reason": "candidate_evidence_unreadable"}
    return value if isinstance(value, dict) else {"status": "FAILED", "reason": "candidate_evidence_not_object"}


def _load_native_evidence(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"status": "FAILED", "reason": "native_evidence_unreadable"}
    return value if isinstance(value, dict) else {"status": "FAILED", "reason": "native_evidence_not_object"}


def _current_source_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and re.fullmatch(r"[0-9a-fA-F]{40}", value) else None


def _native_contract_problems(
    record: object,
    *,
    expected_provenance: dict[str, str] | None = None,
) -> list[str]:
    if not isinstance(record, dict):
        return ["native_evidence_not_object"]
    problems: list[str] = []
    domain_result = record.get("domain_result")
    if not isinstance(domain_result, dict):
        problems.append("native_domain_result_missing")
    else:
        validation = validate_domain_contract(
            json.dumps(domain_result, ensure_ascii=False),
            "",
            {"kind": "json", "required_fields": ["ok", "status"]},
        )
        if validation.get("status") != "PASSED":
            problems.append("native_domain_result_invalid")
    problems.extend(
        validate_evidence_provenance(
            record,
            required=("source_commit", "artifact_ref", "transaction_id"),
            expected=expected_provenance,
        )
    )
    for field in ("host_trace_ref", "capture_ref", "receipt_ref"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{field}_missing")
    if not log_evidence_is_complete(record):
        problems.append("native_log_incomplete")
    return problems


def _native_authority_problems(record: object) -> list[str]:
    """Validate native evidence through the existing host trace/receipt validators."""

    if not isinstance(record, dict):
        return ["native_evidence_not_object"]
    if record.get("evidence_kind") != NATIVE_EVIDENCE_AUTHORITY:
        return ["native_host_authority_unverified"]
    capture = record.get("native_capture_result")
    receipt = record.get("native_host_action_receipt")
    problems: list[str] = []
    if not isinstance(capture, dict):
        problems.append("native_capture_result_missing")
    elif capture.get("schema") != NATIVE_CAPTURE_RESULT_SCHEMA:
        problems.append("native_capture_result_schema_invalid")
    if not isinstance(receipt, dict):
        problems.append("native_host_action_receipt_missing")
    if isinstance(capture, dict) and isinstance(receipt, dict):
        if capture.get("native_host_action_receipt") != receipt:
            problems.append("native_capture_receipt_mismatch")
        for field in (
            "request_ref",
            "host_task_id",
            "host_thread_id",
            "host_instance_id",
            "host_action_id",
        ):
            if capture.get(field) != receipt.get(field):
                problems.append(f"native_capture_{field}_mismatch")
        trace = capture.get("trace")
        if not isinstance(trace, dict):
            problems.append("native_capture_trace_missing")
        elif (
            trace.get("source") != "host_managed_current_session_metadata"
            or not isinstance(trace.get("session_id"), str)
            or not trace.get("session_id", "").strip()
            or not isinstance(trace.get("tool_name"), str)
            or not trace.get("tool_name", "").strip()
            or not isinstance(trace.get("call_id"), str)
            or not trace.get("call_id", "").strip()
        ):
            problems.append("native_capture_trace_unverified")
        if capture.get("host_spawn_evidence") != receipt.get("host_spawn_evidence"):
            if "host_spawn_evidence" in capture or "host_spawn_evidence" in receipt:
                problems.append("native_capture_spawn_evidence_mismatch")
        request = receipt.get("request")
        if not isinstance(request, dict):
            problems.append("native_host_action_request_missing")
        else:
            try:
                from court_native_host_dispatch import validate_native_host_action_receipt

                validate_native_host_action_receipt(
                    receipt,
                    expected=request,
                    replay_guard=set(),
                )
                spawn_evidence = capture.get("host_spawn_evidence")
                host_result = receipt.get("host_result")
                if isinstance(spawn_evidence, dict) and isinstance(host_result, dict):
                    from court_native_trace import validate_spawn_evidence

                    validate_spawn_evidence(spawn_evidence, host_result)
            except (ImportError, TypeError, ValueError, KeyError) as exc:
                problems.append(f"native_host_action_receipt_invalid:{exc}")
    return problems


def validate_native_evidence(
    record: object,
    *,
    expected_provenance: dict[str, str] | None = None,
) -> list[str]:
    return [
        *_native_contract_problems(record, expected_provenance=expected_provenance),
        *_native_authority_problems(record),
    ]


def _required_check_result(
    check: dict[str, object],
    *,
    phase: str,
    step_results: dict[str, dict[str, object]],
    manifest_self_test: dict[str, object],
    package_gate: dict[str, object],
    candidate_evidence: dict[str, object] | None,
    expected_provenance: dict[str, str] | None,
) -> dict[str, object]:
    check_id = str(check["id"])
    result: dict[str, object] = {
        "id": check_id,
        "scope": check["scope"],
        "ci_job": check["ci_job"],
        "required": phase in check["phases"],  # type: ignore[operator]
        "status": "NOT_SELECTED",
        "reason": "phase_not_selected",
    }
    if phase not in check["phases"]:  # type: ignore[operator]
        return result

    if check_id == "required_summary":
        return result
    if check_id == "package_entrypoint_isolated":
        if candidate_evidence is None:
            result.update(status="NOT_RUN", reason="candidate_entrypoint_evidence_required")
            return result
        result.update(candidate_evidence)
        result["id"] = check_id
        result["scope"] = check["scope"]
        result["ci_job"] = check["ci_job"]
        candidate_contract = check.get("domain_contract")
        if result.get("status") == "PASSED":
            if isinstance(candidate_contract, dict):
                encoded_domain = json.dumps(result.get("domain_result"), ensure_ascii=False)
                domain_validation = validate_domain_contract(encoded_domain, "", candidate_contract)
                result["domain_validation"] = domain_validation
                if domain_validation.get("status") != "PASSED":
                    result.update(status="FAILED", reason="candidate_domain_result_failed")
            elif result.get("domain_result") is not None and domain_result_status(result.get("domain_result")) != "PASSED":
                result.update(status="FAILED", reason="candidate_domain_result_failed")
        if result.get("status") == "PASSED":
            provenance_problems = validate_evidence_provenance(
                result,
                required=("source_commit", "artifact_ref", "build_id"),
                expected={
                    field: value
                    for field, value in (expected_provenance or {}).items()
                    if field in {"source_commit", "artifact_ref"}
                },
            )
            if provenance_problems:
                result.update(
                    status="FAILED",
                    reason="candidate_provenance_invalid",
                    provenance_problems=provenance_problems,
                )
        if result.get("status") == "PASSED" and not log_evidence_is_complete(result):
            result.update(status="FAILED", reason="candidate_log_incomplete")
        return result
    if check_id == "release_gate_policy_selftest":
        result.update(
            status="PASSED" if manifest_self_test.get("status") == "PASSED" else "FAILED",
            reason="manifest_self_test",
            domain_result={"ok": manifest_self_test.get("status") == "PASSED"},
            output_truncated=False,
            log_complete=True,
        )
        return result

    step = step_results.get(check_id)
    if step is None:
        command = check.get("command")
        if not isinstance(command, list):
            result.update(status="NOT_RUN", reason="required_entrypoint_not_executable")
            return result
        step = run_step(
            check_id,
            expand_step_command({"name": check_id, "command": command}),
            gate_class=str(check["scope"]),
            timeout=int(check["timeout"]),
            domain_contract=(
                check.get("domain_contract")
                if isinstance(check.get("domain_contract"), dict)
                else None
            ),
        )
    elif isinstance(check.get("domain_contract"), dict):
        step = dict(step)
        domain_validation = validate_domain_contract(
            str(step.get("stdout") or ""),
            str(step.get("stderr") or ""),
            check["domain_contract"],
        )
        step["domain_validation"] = domain_validation
        step["domain_status"] = domain_validation.get("status")
        if domain_validation.get("status") != "PASSED":
            step["status"] = "FAILED"
            step["failure_kind"] = str(
                domain_validation.get("reason") or "domain_contract_failed"
            )
    result.update(step)
    result["id"] = check_id
    result["scope"] = check["scope"]
    result["ci_job"] = check["ci_job"]
    result["required"] = True
    return result


def evaluate_required_checks(
    manifest: dict[str, object],
    *,
    phase: str,
    step_results: list[dict[str, object]],
    manifest_self_test: dict[str, object],
    package_gate: dict[str, object],
    candidate_evidence: dict[str, object] | None = None,
    expected_provenance: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    contracts = manifest.get("required_checks")
    if not isinstance(contracts, list):
        raise ReleaseGateManifestError("required_checks missing from release manifest")
    step_by_name = {
        str(step["name"]): step
        for step in step_results
        if isinstance(step, dict) and isinstance(step.get("name"), str)
    }
    results = [
        _required_check_result(
            check,
            phase=phase,
            step_results=step_by_name,
            manifest_self_test=manifest_self_test,
            package_gate=package_gate,
            candidate_evidence=candidate_evidence,
            expected_provenance=expected_provenance,
        )
        for check in contracts
        if isinstance(check, dict)
    ]
    if [str(item["id"]) for item in results] != list(REQUIRED_CHECK_IDS):
        raise ReleaseGateManifestError("required_checks were not consumed exactly once")
    applicable = [
        item
        for item in results
        if item.get("required") is True and item.get("id") != "required_summary"
    ]
    blocking = [
        item
        for item in applicable
        if item.get("status") != "PASSED"
        or not log_evidence_is_complete(item)
    ]
    summary = next(item for item in results if item["id"] == "required_summary")
    summary.update(
        {
            "required": True,
            "status": "FAILED" if blocking else "PASSED",
            "reason": "required_check_failure" if blocking else "all_required_checks_passed",
            "consumed_ids": list(REQUIRED_CHECK_IDS),
            "blocking_ids": [str(item["id"]) for item in blocking],
            "domain_result": {"ok": not blocking},
        }
    )
    return results


def evaluate_ci_required_summary(
    *,
    os_results: dict[str, object],
    os_job_results: dict[str, object],
    source_aggregate_result: object,
    source_aggregate_status: object,
    package_job_result: object,
    package_status: object,
    package_domain_ok: object,
) -> dict[str, object]:
    """Consume each OS/ID result and keep CI scope separate from native/full."""

    blocking: list[str] = []
    consumed_os_ids: dict[str, list[str]] = {}
    expected_ids = list(SOURCE_REQUIRED_IDS)
    for label in ("ubuntu", "windows", "macos"):
        job_result = os_job_results.get(label)
        if job_result != "success":
            blocking.append(f"{label}:job_not_success:{job_result or 'missing'}")
        rows = os_results.get(label)
        if not isinstance(rows, list):
            blocking.append(f"{label}:result_missing_or_unparseable")
            continue
        ids = [row.get("id") for row in rows if isinstance(row, dict)]
        consumed_os_ids[label] = [str(item) for item in ids]
        if ids != expected_ids or len(set(ids)) != len(expected_ids):
            blocking.append(f"{label}:missing_or_duplicate_required_id")
            continue
        for row in rows:
            if (
                row.get("status") != "PASSED"
                or row.get("domain_ok") is not True
                or row.get("domain_status") != "PASSED"
                or row.get("log_complete") is not True
                or not _ci_log_capture_metadata_complete(row.get("log_capture"))
            ):
                blocking.append(f"{label}:{row.get('id')}:not_passed")
    if source_aggregate_result != "success" or source_aggregate_status != "PASSED":
        blocking.append("source-contracts:aggregate_not_passed")
    if package_job_result != "success":
        blocking.append(f"package-entrypoint:job_not_success:{package_job_result or 'missing'}")
    if package_status != "PASSED" or not (
        package_domain_ok is True or package_domain_ok == "true"
    ):
        blocking.append("package_entrypoint_isolated:not_passed")
    return {
        "id": "required_summary",
        "scope": "CI",
        "status": "CI_SCOPE_PASSED" if not blocking else "FAILED",
        "consumed_ids": [*SOURCE_REQUIRED_IDS, "package_entrypoint_isolated", "required_summary"],
        "consumed_os_ids": consumed_os_ids,
        "blocking": blocking,
        "native_host": "NOT_RUN",
        "full_acceptance": False,
        "domain_result": {"ok": not blocking},
    }


def run_ci_summary_self_test() -> dict[str, bool]:
    """Exercise the same per-OS summary path used by the CI workflow."""

    rows = [
        {
            "id": check_id,
            "status": "PASSED",
            "domain_status": "PASSED",
            "domain_ok": True,
            "log_capture": {
                "complete": True,
                "stdout_path": f"ci://{check_id}/stdout",
                "stderr_path": f"ci://{check_id}/stderr",
                "stdout_bytes": 0,
                "stderr_bytes": 0,
            },
            "log_complete": True,
        }
        for check_id in SOURCE_REQUIRED_IDS
    ]
    all_os = {label: list(rows) for label in ("ubuntu", "windows", "macos")}
    all_jobs = {label: "success" for label in ("ubuntu", "windows", "macos")}
    valid = evaluate_ci_required_summary(
        os_results=all_os,
        os_job_results=all_jobs,
        source_aggregate_result="success",
        source_aggregate_status="PASSED",
        package_job_result="success",
        package_status="PASSED",
        package_domain_ok="true",
    )
    missing_os = dict(all_os)
    missing_os.pop("macos")
    missing_os_result = evaluate_ci_required_summary(
        os_results=missing_os,
        os_job_results=all_jobs,
        source_aggregate_result="success",
        source_aggregate_status="PASSED",
        package_job_result="success",
        package_status="PASSED",
        package_domain_ok="true",
    )
    missing_id = {label: list(value) for label, value in all_os.items()}
    missing_id["windows"].pop()
    missing_id_result = evaluate_ci_required_summary(
        os_results=missing_id,
        os_job_results=all_jobs,
        source_aggregate_result="success",
        source_aggregate_status="PASSED",
        package_job_result="success",
        package_status="PASSED",
        package_domain_ok="true",
    )
    missing_capture = {label: list(value) for label, value in all_os.items()}
    missing_capture["ubuntu"][0] = dict(missing_capture["ubuntu"][0])
    missing_capture["ubuntu"][0].pop("log_capture")
    missing_capture_result = evaluate_ci_required_summary(
        os_results=missing_capture,
        os_job_results=all_jobs,
        source_aggregate_result="success",
        source_aggregate_status="PASSED",
        package_job_result="success",
        package_status="PASSED",
        package_domain_ok="true",
    )
    return {
        "all_os_passes_ci_scope": valid.get("status") == "CI_SCOPE_PASSED" and valid.get("native_host") == "NOT_RUN",
        "missing_os_rejected": missing_os_result.get("status") == "FAILED",
        "missing_id_rejected": missing_id_result.get("status") == "FAILED",
        "missing_capture_rejected": missing_capture_result.get("status") == "FAILED",
        "all_ids_consumed_once": valid.get("consumed_ids") == [*SOURCE_REQUIRED_IDS, "package_entrypoint_isolated", "required_summary"],
    }


def _phase_failure(name: str, reason: str, *, gate_class: str = "source") -> dict[str, object]:
    return {
        "name": name,
        "gate_class": gate_class,
        "status": "FAILED",
        "exit_code": None,
        "command": "",
        "output": reason,
        "stdout": "",
        "stderr": "",
        "domain_result": {"ok": False, "reason": reason},
        "domain_status": "FAILED",
        "output_truncated": False,
        "log_complete": True,
        "failure_kind": reason,
        "git_index_isolated": False,
    }


def _skipped_required_checks(
    manifest: dict[str, object],
    *,
    phase: str,
    reason: str,
) -> list[dict[str, object]]:
    contracts = manifest.get("required_checks")
    if not isinstance(contracts, list):
        return []
    results: list[dict[str, object]] = []
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        check_id = str(contract["id"])
        results.append(
            {
                "id": check_id,
                "scope": contract["scope"],
                "ci_job": contract["ci_job"],
                "required": phase in contract["phases"],
                "status": "FAILED" if check_id == "required_summary" else "NOT_RUN",
                "reason": reason,
            }
        )
    return results


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the mandatory hierarchy release-gate manifest tamper checks.",
    )
    parser.add_argument("--package", type=Path, help="Optional package zip to validate without building a new package.")
    parser.add_argument("--require-package", action="store_true", help="Fail if --package is not supplied.")
    parser.add_argument(
        "--install-receipt",
        type=Path,
        help="Post-install receipt JSON binding the installed source_package_sha256 to --package.",
    )
    parser.add_argument(
        "--candidate-evidence",
        "--candidate-result",
        dest="candidate_evidence",
        type=Path,
        help="Structured result from the same-source isolated candidate public entrypoint.",
    )
    parser.add_argument(
        "--native-evidence",
        "--native-host-evidence",
        dest="native_evidence",
        type=Path,
        help="Structured, current native host trace/capture/receipt evidence.",
    )
    parser.add_argument("--source-commit", help="Expected source revision for candidate/install evidence.")
    parser.add_argument("--artifact-ref", help="Expected immutable candidate artifact reference.")
    parser.add_argument(
        "--install-transaction-id",
        help="Expected installation transaction identifier for post-install/full evidence.",
    )
    parser.add_argument("--skip-active-copies", action="store_true", help="Skip active copy hash validation.")
    parser.add_argument("--skip-runtime", action="store_true", help="Skip read-only superCC runtime diagnose.")
    parser.add_argument(
        "--phase",
        choices=("source", "candidate", "pre-install", "post-install", "full", "native"),
        default="full",
        help="Select source, candidate, pre-install, post-install, full, or native release gates.",
    )
    parser.add_argument(
        "--candidate",
        action="store_true",
        help="Alias for --phase pre-install; requires a package and skips installed-host gates.",
    )
    args = parser.parse_args()
    if args.candidate and args.phase not in {"full", "pre-install"}:
        parser.error("--candidate conflicts with the selected phase")
    phase = "pre-install" if args.candidate else args.phase

    try:
        manifest = load_release_manifest()
        manifest_self_test_cases = run_hierarchy_release_gate_self_test(manifest)
        manifest_self_test_cases.extend(run_required_check_contract_self_test(manifest))
    except (ReleaseGateManifestError, AssertionError) as exc:
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
    manifest_self_test = {
        "status": "PASSED",
        "cases": manifest_self_test_cases,
        "case_count": len(manifest_self_test_cases),
    }
    if args.self_test:
        try:
            git_index_self_test = run_git_index_isolation_self_test()
            domain_contract_self_test = run_domain_contract_self_test()
            ci_summary_self_test = run_ci_summary_self_test()
            log_capture_self_test = run_log_capture_self_test()
            result = {
                "ok": (
                    all(domain_contract_self_test.values())
                    and all(ci_summary_self_test.values())
                    and all(log_capture_self_test.values())
                ),
                "schema": "court.release_gate.self_test.v1",
                "manifest_self_test": manifest_self_test,
                "git_index_self_test": git_index_self_test,
                "domain_contract_self_test": domain_contract_self_test,
                "ci_summary_self_test": ci_summary_self_test,
                "log_capture_self_test": log_capture_self_test,
            }
        except AssertionError as exc:
            result = {
                "ok": False,
                "schema": "court.release_gate.self_test.v1",
                "manifest_self_test": manifest_self_test,
                "git_index_self_test": {"status": "FAILED", "error": str(exc)},
                "domain_contract_self_test": {"status": "FAILED", "error": str(exc)},
                "ci_summary_self_test": {"status": "FAILED", "error": str(exc)},
                "log_capture_self_test": {"status": "FAILED", "error": str(exc)},
            }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                f"RELEASE_GATE_SELF_TEST_{'PASSED' if result['ok'] else 'FAILED'} "
                f"cases={len(manifest_self_test_cases)} "
                f"names={','.join(manifest_self_test_cases)}"
            )
        return 0 if result["ok"] else 2
    runtime_skip = phase in {"full", "native", "post-install"} and args.skip_runtime
    active_copies_skip = phase == "full" and args.skip_active_copies
    if runtime_skip or active_copies_skip:
        skip_reason = (
            f"{phase}_runtime_required_cannot_be_skipped"
            if runtime_skip
            else "full_active_copies_required_cannot_be_skipped"
        )
        failure = _phase_failure(
            "supercc_runtime_truth" if runtime_skip else "active_copies",
            skip_reason,
            gate_class="runtime" if runtime_skip else "source",
        )
        result = {
            "ok": False,
            "schema": "court.release_gate.v1",
            "gate_mode": phase,
            "release_gate": "FAILED",
            "source_gate": "NOT_RUN",
            "candidate_gate": "NOT_RUN",
            "pre_install_gate": "NOT_RUN",
            "installation_gate": "NOT_RUN",
            "runtime_gate": "FAILED",
            "native_gate": "NOT_RUN",
            "full_acceptance": False,
            "native_host": "NOT_RUN",
            "runtime_reason": skip_reason,
            "layer_results": {
                "source": {"status": "NOT_RUN", "reason": skip_reason},
                "candidate": {"status": "NOT_RUN", "reason": skip_reason},
                "pre_install": {"status": "NOT_RUN", "reason": skip_reason},
                "full": {"status": "FAILED", "reason": skip_reason},
                "native": {"status": "NOT_RUN", "reason": skip_reason},
            },
            "required_checks": _skipped_required_checks(
                manifest,
                phase=phase,
                reason=skip_reason,
            ),
            "manifest_self_test": manifest_self_test,
            "package_gate": {"name": "package_validation", "status": "NOT_RUN", "problems": []},
            "install_receipt_gate": {"name": "install_receipt_validation", "status": "NOT_RUN", "problems": []},
            "steps": [],
            "failed": [failure],
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print("RELEASE_GATE_FAILED steps=0 failed=1 package_gate=NOT_RUN install_receipt_gate=NOT_RUN manifest_self_test=PASSED")
            print(f"FAILED {failure['name']}: {failure['output']}")
        return 2

    expected_provenance = {
        field: value
        for field, value in (
            ("source_commit", args.source_commit or _current_source_commit()),
            ("artifact_ref", args.artifact_ref),
            ("transaction_id", args.install_transaction_id),
        )
        if isinstance(value, str) and value.strip()
    }
    candidate_evidence = _load_candidate_evidence(args.candidate_evidence)
    native_evidence = _load_native_evidence(args.native_evidence)
    manifest_steps = selected_release_steps(
        manifest,
        include_active_copies=phase not in {"source", "candidate", "pre-install", "native"}
        and not args.skip_active_copies,
        include_runtime=phase in {"post-install", "full", "native"} and not args.skip_runtime,
    )
    if phase in {"source", "candidate", "pre-install"}:
        manifest_steps = [
            step
            for step in manifest_steps
            if step.get("gate_class") == "source" and step.get("name") != "catalog_strict"
        ]
    elif phase in {"post-install", "native"}:
        manifest_steps = [
            step
            for step in manifest_steps
            if (
                step.get("gate_class") in {"installation", "runtime"}
                if phase == "post-install"
                else step.get("gate_class") == "runtime"
            )
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

    package_required = phase in {"candidate", "pre-install", "post-install", "full"} or args.require_package
    if args.package:
        package_gate = validate_package(args.package.resolve())
    elif package_required:
        package_gate = {
            "name": "package_validation",
            "status": "FAILED",
            "path": None,
            "provenance": {},
            "problems": ["package_required_but_not_supplied"],
        }
    else:
        package_gate = {
            "name": "package_validation",
            "status": "NOT_SELECTED",
            "path": None,
            "provenance": {},
            "problems": [],
            "reason": "package_not_required_for_phase",
        }

    expected_package_provenance = {
        field: value
        for field, value in expected_provenance.items()
        if field in {"source_commit", "artifact_ref"}
    }
    package_provenance_problems: list[str] = []
    if phase in {"post-install", "full"} and package_gate.get("status") == "PASSED":
        package_provenance_problems = validate_evidence_provenance(
            package_gate,
            required=("source_commit", "artifact_ref", "build_id", "release_label"),
            expected=expected_package_provenance,
        )
        if package_provenance_problems:
            problems = package_gate.setdefault("problems", [])
            assert isinstance(problems, list)
            problems.extend(f"package_{problem}" for problem in package_provenance_problems)
            package_gate["status"] = "FAILED"

    # A validated package is the authority for source/artifact identity.  CLI
    # expectations may narrow that authority, but never replace it.
    package_provenance = package_gate.get("provenance")
    candidate_expected_provenance = dict(expected_provenance)
    receipt_expected_provenance = dict(expected_provenance)
    if phase in {"post-install", "full"} and package_gate.get("status") == "PASSED":
        if isinstance(package_provenance, dict):
            for field in ("source_commit", "artifact_ref"):
                value = package_provenance.get(field)
                if isinstance(value, str) and value.strip():
                    candidate_expected_provenance[field] = value
                    receipt_expected_provenance[field] = value

    install_receipt_gate = evaluate_install_receipt_gate(
        phase=phase,
        require_package=args.require_package,
        install_receipt=args.install_receipt,
        package_gate=package_gate,
        required_provenance=(
            ("source_commit", "artifact_ref", "installation_id", "transaction_id")
            if phase in {"post-install", "full"}
            else ()
        ),
        expected_provenance=receipt_expected_provenance,
    )

    authoritative_expected_provenance: dict[str, str] = {}
    binding_problems: list[str] = []
    if phase in {"post-install", "full"}:
        receipt_provenance = install_receipt_gate.get("provenance")
        if package_gate.get("status") != "PASSED":
            binding_problems.append("authoritative_package_not_validated")
        if install_receipt_gate.get("status") != "PASSED":
            binding_problems.append("authoritative_install_receipt_not_validated")
        if not isinstance(package_provenance, dict):
            binding_problems.append("authoritative_package_provenance_missing")
        if not isinstance(receipt_provenance, dict):
            binding_problems.append("authoritative_install_receipt_provenance_missing")
        if isinstance(package_provenance, dict) and isinstance(receipt_provenance, dict):
            for field in ("source_commit", "artifact_ref"):
                package_value = package_provenance.get(field)
                receipt_value = receipt_provenance.get(field)
                if not isinstance(package_value, str) or not package_value.strip():
                    binding_problems.append(f"authoritative_package_{field}_missing")
                elif receipt_value != package_value:
                    binding_problems.append(f"authoritative_{field}_mismatch")
                if field == "artifact_ref" and args.artifact_ref and package_value != args.artifact_ref:
                    binding_problems.append("authoritative_artifact_ref_cli_mismatch")
            transaction_id = receipt_provenance.get("transaction_id")
            if not isinstance(transaction_id, str) or not transaction_id.strip():
                binding_problems.append("authoritative_transaction_id_missing")
            elif args.install_transaction_id and transaction_id != args.install_transaction_id:
                binding_problems.append("authoritative_transaction_id_cli_mismatch")
            if not binding_problems:
                authoritative_expected_provenance = {
                    "source_commit": str(package_provenance["source_commit"]),
                    "artifact_ref": str(package_provenance["artifact_ref"]),
                    "transaction_id": str(transaction_id),
                }
        if binding_problems:
            receipt_problems = install_receipt_gate.setdefault("problems", [])
            if isinstance(receipt_problems, list):
                for problem in binding_problems:
                    if problem not in receipt_problems:
                        receipt_problems.append(problem)
            install_receipt_gate["status"] = "FAILED"
    required_checks = evaluate_required_checks(
        manifest,
        phase=phase,
        step_results=steps,
        manifest_self_test=manifest_self_test,
        package_gate=package_gate,
        candidate_evidence=candidate_evidence,
        expected_provenance=candidate_expected_provenance,
    )

    failed: list[dict[str, object]] = [
        step for step in steps if step.get("status") != "PASSED"
    ]
    if package_gate.get("status") == "FAILED":
        failed.append(package_gate)
    if install_receipt_gate.get("status") == "FAILED":
        failed.append(install_receipt_gate)
    failed.extend(
        item
        for item in required_checks
        if item.get("required") is True and item.get("status") != "PASSED"
    )
    native_expected_provenance = (
        authoritative_expected_provenance
        if phase in {"post-install", "full"}
        else expected_provenance
    )
    native_contract_problems = (
        ["native_host_evidence_not_run"]
        if native_evidence is None
        else _native_contract_problems(
            native_evidence,
            expected_provenance=native_expected_provenance,
        )
    )
    native_authority_problems = (
        []
        if native_evidence is None
        else _native_authority_problems(native_evidence)
    )
    if phase in {"post-install", "full"} and native_evidence is not None:
        if not authoritative_expected_provenance:
            native_authority_problems.append("native_authoritative_binding_unavailable")
    native_problems = [*native_contract_problems, *native_authority_problems]
    native_result = "NOT_SELECTED"
    if phase in {"post-install", "full", "native"}:
        if native_evidence is None:
            native_result = "NOT_RUN"
        elif native_contract_problems:
            native_result = "FAILED"
        elif native_authority_problems:
            native_result = NATIVE_EVIDENCE_CONTRACT_PASSED
        else:
            native_result = "PASSED"
        if native_result != "PASSED":
            failed.append(
                _phase_failure(
                    "native_host",
                    ";".join(native_problems),
                    gate_class="runtime",
                )
            )
    source_failed = [
        step
        for step in failed
        if step.get("gate_class") == "source" or step.get("scope") == "source"
    ]
    installation_failed = [
        step
        for step in failed
        if step.get("gate_class") == "installation"
        or step.get("scope") == "installation"
        or step.get("name") in {"package_validation", "install_receipt_validation"}
    ]
    runtime_failed = [
        step
        for step in failed
        if (
            (step.get("gate_class") == "runtime" or step.get("scope") == "runtime")
            and step.get("name") != "native_host"
        )
    ]

    def layer_status(ids: Iterable[str]) -> str:
        id_set = set(ids)
        selected = [
            item
            for item in required_checks
            if item.get("id") in id_set and item.get("required") is True
        ]
        if not selected:
            return "NOT_SELECTED"
        return "PASSED" if all(item.get("status") == "PASSED" for item in selected) else "FAILED"

    source_result = layer_status(
        item["id"]
        for item in required_checks
        if item.get("scope") == "source"
    )
    candidate_result = (
        "NOT_SELECTED"
        if phase not in {"candidate", "pre-install", "full"}
        else (
            "PASSED"
            if package_gate.get("status") == "PASSED"
            and next(
                item for item in required_checks if item.get("id") == "package_entrypoint_isolated"
            ).get("status")
            == "PASSED"
            else "FAILED"
        )
    )
    pre_install_result = (
        "NOT_SELECTED"
        if phase not in {"candidate", "pre-install", "full"}
        else ("PASSED" if source_result == candidate_result == "PASSED" else "FAILED")
    )
    runtime_gate = (
        "NOT_SELECTED"
        if phase in {"source", "candidate", "pre-install"}
        else ("PASSED" if not runtime_failed else "FAILED")
    )
    full_result = "PASSED" if phase == "full" and not failed else "FAILED" if phase == "full" else "NOT_SELECTED"
    layer_results = {
        "source": {"status": source_result},
        "candidate": {"status": candidate_result},
        "pre_install": {"status": pre_install_result},
        "full": {"status": full_result},
        "native": {"status": native_result},
    }
    required_summary = next(
        item for item in required_checks if item.get("id") == "required_summary"
    )
    result = {
        "ok": not failed,
        "schema": "court.release_gate.v1",
        "gate_mode": phase,
        "release_gate": "PASSED" if not failed else "FAILED",
        "source_gate": (
            "NOT_APPLICABLE"
            if phase in {"post-install", "native"}
            else ("PASSED" if not source_failed else "FAILED")
        ),
        "candidate_gate": candidate_result,
        "pre_install_gate": pre_install_result,
        "installation_gate": (
            "NOT_APPLICABLE"
            if phase in {"source", "candidate", "pre-install", "native"}
            else ("PASSED" if not installation_failed else "FAILED")
        ),
        "runtime_gate": runtime_gate,
        "native_gate": native_result,
        "full_acceptance": full_result == "PASSED" and native_result == "PASSED",
        "native_host": (
            "PASSED"
            if native_result == "PASSED"
            else (
                "NOT_RUN"
                if native_evidence is None
                or native_result == NATIVE_EVIDENCE_CONTRACT_PASSED
                else "FAILED"
            )
        ),
        "native_evidence": native_evidence,
        "runtime_reason": (
            "candidate_preinstall"
            if phase in {"candidate", "pre-install"}
            else (
                "runtime_not_selected"
                if phase == "source"
                else ("runtime_skipped" if args.skip_runtime else "runtime_selected")
            )
        ),
        "layer_results": layer_results,
        "manifest_self_test": manifest_self_test,
        "package_gate": package_gate,
        "install_receipt_gate": install_receipt_gate,
        "authoritative_provenance": authoritative_expected_provenance,
        "native_evidence_contract": (
            "NOT_RUN"
            if native_evidence is None
            else "FAILED"
            if native_contract_problems
            else NATIVE_EVIDENCE_CONTRACT_PASSED
        ),
        "required_checks": required_checks,
        "required_summary": required_summary,
        "steps": steps,
        "failed": failed,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"RELEASE_GATE_{result['release_gate']} "
            f"steps={len(steps)} failed={len(failed)} package_gate={package_gate['status']} "
            f"install_receipt_gate={install_receipt_gate['status']} "
            f"manifest_self_test={manifest_self_test['status']}"
        )
        for item in failed:
            print(f"FAILED {item['name']}: {item.get('output') or item.get('problems')}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
