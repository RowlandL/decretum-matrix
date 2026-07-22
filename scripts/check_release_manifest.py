"""Validate release-gate policy plus Decretum Matrix（诏令矩阵） package identity."""

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
from types import MappingProxyType

sys.dont_write_bytecode = True

from release_gate_manifest import (
    MANIFEST_SCHEMA,
    ReleaseGateManifestError,
    load_release_manifest,
    selected_release_steps,
    validate_release_manifest,
)
import build_release_artifacts
import check_release_gate
import check_release_legal
import package_skill
import release_payload_manifest


ROOT = Path(__file__).resolve().parents[1]
NPM_HARNESS_SCRIPT = ROOT / "scripts" / "check_npm_package.mjs"
NPM_HARNESS_MODE_ARGS = MappingProxyType(
    {
        "check": (),
        "self-test": ("--self-test",),
    }
)
NPM_HARNESS_ENVIRONMENT = MappingProxyType(
    {
        "GH_TOKEN": "",
        "GITHUB_TOKEN": "",
        "NODE_AUTH_TOKEN": "",
        "NPM_TOKEN": "",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "ALL_PROXY": "",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "npm_config_ignore_scripts": "true",
        "npm_config_offline": "true",
        "npm_config_provenance": "false",
        "npm_config_registry": "https://registry.invalid/",
        "npm_config_update_notifier": "false",
    }
)
SENSITIVE_ENV_RE = re.compile(r"(?:token|password|passwd|secret|_auth)", re.IGNORECASE)
URL_USERINFO_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^/@\s]+@")


def _sanitize_subprocess_text(value: str) -> str:
    return URL_USERINFO_RE.sub(r"\1[REDACTED]@", value)


def _resolve_node_executable() -> str:
    override = os.environ.get("DECRETUM_NODE_EXECUTABLE", "").strip()
    candidate = override or shutil.which("node")
    if not candidate:
        raise AssertionError("Node.js executable is unavailable")
    resolved = Path(candidate).resolve(strict=True)
    probe = subprocess.run(
        [str(resolved), "--version"],
        cwd=ROOT.resolve(strict=True),
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
        check=False,
    )
    if probe.returncode != 0 or re.fullmatch(r"v\d+\.\d+\.\d+", probe.stdout.strip()) is None:
        label = "configured" if override else "discovered"
        raise AssertionError(f"{label} Node.js executable failed validation")
    return str(resolved)


def npm_harness_invocation_contract() -> dict[str, object]:
    base = ("$NODE", "scripts/check_npm_package.mjs")
    production = (*base, *NPM_HARNESS_MODE_ARGS["check"])
    self_test = (*base, *NPM_HARNESS_MODE_ARGS["self-test"])
    environment_json = json.dumps(
        dict(NPM_HARNESS_ENVIRONMENT),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return {
        "production_argv": list(production),
        "self_test_argv": list(self_test),
        "shared_immutable_prefix": list(production),
        "mode_only_delta": list(self_test[len(production) :]),
        "environment_sha256": hashlib.sha256(environment_json).hexdigest(),
        "offline": True,
        "python_override": "$PYTHON",
        "shell": False,
    }


def _npm_harness_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if SENSITIVE_ENV_RE.search(key) is None
    }
    environment.update(NPM_HARNESS_ENVIRONMENT)
    environment["DECRETUM_PYTHON_EXECUTABLE"] = str(Path(sys.executable).resolve(strict=True))
    return environment


def run_npm_harness(mode: str) -> dict[str, object]:
    if mode not in NPM_HARNESS_MODE_ARGS:
        raise AssertionError(f"unsupported npm harness mode: {mode}")
    root = ROOT.resolve(strict=True)
    script = NPM_HARNESS_SCRIPT.resolve(strict=True)
    try:
        script.relative_to(root / "scripts")
    except ValueError as exc:
        raise AssertionError("npm harness script resolves outside scripts/") from exc
    command = [
        _resolve_node_executable(),
        str(script),
        *NPM_HARNESS_MODE_ARGS[mode],
    ]
    completed = subprocess.run(
        command,
        cwd=root,
        env=_npm_harness_environment(),
        capture_output=True,
        text=True,
        timeout=900,
        shell=False,
        check=False,
    )
    if completed.returncode != 0:
        detail = _sanitize_subprocess_text(
            "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        )
        raise AssertionError(
            f"npm harness {mode} failed with exit {completed.returncode}"
            + (f": {detail[-4000:]}" if detail else "")
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError("npm harness did not return one JSON report") from exc
    expected_schema = (
        "decretum.npm_self_test.v3"
        if mode == "self-test"
        else "decretum.npm_package_check.v2"
    )
    if report.get("schema") != expected_schema or report.get("status") != "PASS":
        raise AssertionError("npm harness report schema/status mismatch")
    if mode == "self-test":
        validation = report.get("validation") or {}
        required = {
            "origin_userinfo_rejected",
            "origin_userinfo_redacted",
            "receipt_canonical_origin_only",
            "python_interpreter_contract",
            "strict_offline_install",
        }
        failed = sorted(name for name in required if validation.get(name) != "PASS")
        python_evidence = (report.get("evidence") or {}).get("python_invocation") or {}
        if failed:
            raise AssertionError(f"npm harness required validations failed: {failed}")
        if python_evidence.get("source") != "override":
            raise AssertionError("strict wrapper did not bind the Python interpreter override")
        if report.get("repository_output") != "NOT_WRITTEN":
            raise AssertionError("npm harness wrote output inside the repository")
    contract = npm_harness_invocation_contract()
    return {
        "ok": True,
        "schema": "decretum.npm_release_harness_wrapper.v1",
        "mode": mode,
        "command": " ".join(
            contract["self_test_argv"] if mode == "self-test" else contract["production_argv"]
        ),
        "contract": contract,
        "report_schema": report["schema"],
        "report_sha256": hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest(),
        "network_dependency": "NONE",
        "pending_body_access": "NO",
    }


def expect_invalid(manifest: dict[str, object], expected_text: str) -> None:
    try:
        validate_release_manifest(manifest)
    except ReleaseGateManifestError as exc:
        if expected_text not in str(exc):
            raise AssertionError(f"expected {expected_text!r} in validation error, got {exc!r}") from exc
    else:
        raise AssertionError(f"invalid manifest unexpectedly passed: {expected_text}")


def run_negative_contract_checks(manifest: dict[str, object]) -> list[str]:
    cases: list[tuple[str, dict[str, object], str]] = []

    duplicate = deepcopy(manifest)
    duplicate["steps"].append(deepcopy(duplicate["steps"][0]))  # type: ignore[index,union-attr]
    cases.append(("duplicate_name", duplicate, "duplicate release step name"))

    invalid_gate = deepcopy(manifest)
    invalid_gate["steps"][0]["gate_class"] = "package"  # type: ignore[index]
    cases.append(("invalid_gate_class", invalid_gate, "invalid gate_class"))

    invalid_timeout = deepcopy(manifest)
    invalid_timeout["steps"][0]["timeout"] = 0  # type: ignore[index]
    cases.append(("invalid_timeout", invalid_timeout, "timeout must be"))

    invalid_codes = deepcopy(manifest)
    invalid_codes["steps"][0]["allowed_returncodes"] = [0, 0]  # type: ignore[index]
    cases.append(("duplicate_returncode", invalid_codes, "must be unique"))

    shell_string = deepcopy(manifest)
    shell_string["steps"][0]["command"] = "$PYTHON scripts/quick_validate.py ."  # type: ignore[index]
    cases.append(("shell_string", shell_string, "argv list"))

    absolute_script = deepcopy(manifest)
    absolute_script["steps"][0]["command"] = ["$PYTHON", r"C:\\temp\\outside.py"]  # type: ignore[index]
    cases.append(("absolute_script", absolute_script, "absolute script paths"))

    traversal = deepcopy(manifest)
    traversal["steps"][0]["command"] = ["$PYTHON", "scripts/../outside.py"]  # type: ignore[index]
    cases.append(("parent_traversal", traversal, "parent traversal"))

    bad_placeholder = deepcopy(manifest)
    bad_placeholder["steps"][0]["command"] = ["python", "scripts/quick_validate.py", "."]  # type: ignore[index]
    cases.append(("python_placeholder", bad_placeholder, "must use $PYTHON"))

    missing_required = deepcopy(manifest)
    missing_required["steps"].pop()  # type: ignore[union-attr]
    cases.append(("missing_required_step", missing_required, "external required-step policy"))

    missing_builder = deepcopy(manifest)
    missing_builder["steps"] = [  # type: ignore[index]
        step for step in missing_builder["steps"] if step.get("name") != "release_artifact_builder"  # type: ignore[union-attr]
    ]
    cases.append(("missing_release_artifact_builder", missing_builder, "external required-step policy"))

    mutating_command = deepcopy(manifest)
    mutating_command["steps"][0]["command"] = [  # type: ignore[index]
        "$PYTHON",
        "scripts/ensure_supercc_court.py",
        "--turn-start",
    ]
    cases.append(("mutating_command_substitution", mutating_command, "command drifted from required policy"))

    condition_drift = deepcopy(manifest)
    condition_drift["steps"][0]["condition"] = "runtime_enabled"  # type: ignore[index]
    cases.append(("required_condition_drift", condition_drift, "condition drifted from required policy"))

    returncode_expansion = deepcopy(manifest)
    returncode_expansion["steps"][0]["allowed_returncodes"] = [0, 2, 255]  # type: ignore[index]
    cases.append(("returncode_expansion", returncode_expansion, "allowed_returncodes drifted from required policy"))

    passed: list[str] = []
    for name, value, expected in cases:
        expect_invalid(value, expected)
        passed.append(name)
    return passed


def release_surface_contract() -> dict[str, bool]:
    return {
        "canonical_product_name": release_payload_manifest.NAME == "decretum-matrix",
        "canonical_display_name": getattr(release_payload_manifest, "DISPLAY_NAME", None)
        == "Decretum Matrix（诏令矩阵）",
        "canonical_artifact_name": release_payload_manifest.ARTIFACT_NAME
        == "decretum-matrix-beta1.0.4.zip",
        "canonical_release_label": release_payload_manifest.RELEASE_LABEL
        == "beta1.0.4",
        "agpl_only": getattr(release_payload_manifest, "LICENSE_ID", None) == "AGPL-3.0-only",
        "artifact_builder_identity": build_release_artifacts.NAME == "decretum-matrix",
        "tagless_candidate_builder": (
            callable(getattr(build_release_artifacts, "build_candidate", None))
            and build_release_artifacts.CANDIDATE_RECEIPT_SCHEMA
            == "court.release_candidate_receipt.v1"
        ),
        "post_install_receipt_package_binding": callable(
            getattr(check_release_gate, "evaluate_install_receipt_gate", None)
        ),
        "stable_locator": (
            package_skill.ROOT_NAME == "decretum-matrix"
            and release_payload_manifest.ARCHIVE_ROOT == "decretum-matrix/"
        ),
    }


def release_identity_parity_contract(root: Path = ROOT) -> dict[str, bool]:
    try:
        version = (root / "VERSION").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        version = ""
    try:
        raw_sbom = json.loads((root / "SBOM.spdx.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raw_sbom = None
    sbom_is_object = isinstance(raw_sbom, dict)
    sbom = raw_sbom if sbom_is_object else {}

    packages = sbom.get("packages") if isinstance(sbom, dict) else None
    package = packages[0] if isinstance(packages, list) and packages and isinstance(packages[0], dict) else {}
    creation_info = sbom.get("creationInfo") if isinstance(sbom, dict) else None
    created = creation_info.get("created") if isinstance(creation_info, dict) else None
    legal_created = getattr(check_release_legal, "EXPECTED_SBOM_CREATED", None)
    date_compact = (
        legal_created[:10].replace("-", "")
        if isinstance(legal_created, str) and len(legal_created) >= 10
        else ""
    )
    expected_artifact = f"{release_payload_manifest.NAME}-{version}.zip"
    expected_sbom_name = f"{release_payload_manifest.NAME}-{version}"
    expected_sbom_namespace = (
        f"https://spdx.org/spdxdocs/{expected_sbom_name}-{date_compact}"
        if version and date_compact
        else ""
    )
    return {
        "version_readable": bool(version),
        "sbom_is_object": sbom_is_object,
        "payload_release_matches_version": release_payload_manifest.RELEASE_LABEL == version,
        "payload_artifact_matches_version": release_payload_manifest.ARTIFACT_NAME == expected_artifact,
        "package_release_matches_version": package_skill.RELEASE_LABEL == version,
        "package_artifact_matches_version": package_skill.default_out().name == expected_artifact,
        "legal_release_matches_version": check_release_legal.EXPECTED_RELEASE == version,
        "legal_sbom_name_matches_version": check_release_legal.EXPECTED_SBOM_NAME == expected_sbom_name,
        "legal_sbom_namespace_matches_version_and_date": (
            check_release_legal.EXPECTED_SBOM_NAMESPACE == expected_sbom_namespace
        ),
        "sbom_name_matches_version": sbom.get("name") == expected_sbom_name,
        "sbom_package_name_matches_payload": (
            package.get("name")
            == release_payload_manifest.NAME
            == check_release_legal.EXPECTED_PACKAGE_NAME
        ),
        "sbom_package_version_matches_version": package.get("versionInfo") == version,
        "sbom_namespace_matches_version_and_date": (
            sbom.get("documentNamespace") == expected_sbom_namespace
        ),
        "sbom_created_matches_legal_release_date": bool(legal_created) and created == legal_created,
        "release_license_matches_across_surfaces": (
            release_payload_manifest.LICENSE_ID
            == package_skill.LICENSE_ID
            == check_release_legal.EXPECTED_LICENSE
            == package.get("licenseDeclared")
        ),
    }


def release_identity_parity_fixture_contract() -> dict[str, bool]:
    expected_keys = set(release_identity_parity_contract())
    with tempfile.TemporaryDirectory(prefix="decretum-release-identity-parity-") as tmp_text:
        fixture = Path(tmp_text)
        (fixture / "VERSION").write_bytes((ROOT / "VERSION").read_bytes())
        (fixture / "SBOM.spdx.json").write_text("[]\n", encoding="utf-8")
        malformed = release_identity_parity_contract(fixture)
    return {
        "non_object_sbom_returns_complete_failed_contract": (
            set(malformed) == expected_keys and not all(malformed.values())
        ),
    }


def install_receipt_gate_fixture_contract() -> dict[str, bool]:
    package_sha256 = "a" * 64
    package_gate = {"status": "PASSED", "sha256": package_sha256}
    with tempfile.TemporaryDirectory(prefix="court-install-receipt-gate-") as raw:
        root = Path(raw)
        missing_field = root / "missing-field.json"
        invalid_format = root / "invalid-format.json"
        mismatch = root / "mismatch.json"
        matching = root / "matching.json"
        invalid_encoding = root / "invalid-encoding.json"
        hash_only = root / "hash-only.json"
        planned = root / "planned.json"
        missing_field.write_text("{}\n", encoding="utf-8")
        invalid_format.write_text(
            json.dumps({"source_package_sha256": "A" * 64}) + "\n",
            encoding="utf-8",
        )
        mismatch.write_text(
            json.dumps({"source_package_sha256": "b" * 64}) + "\n",
            encoding="utf-8",
        )
        matching.write_text(
            json.dumps(
                {
                    "schema": check_release_gate.INSTALL_RECEIPT_SCHEMA,
                    "ok": True,
                    "status": "INSTALLED",
                    "source_package_sha256": package_sha256,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        invalid_encoding.write_bytes(b"\xff")
        hash_only.write_text(
            json.dumps({"source_package_sha256": package_sha256}) + "\n",
            encoding="utf-8",
        )
        planned.write_text(
            json.dumps(
                {
                    "schema": check_release_gate.INSTALL_RECEIPT_SCHEMA,
                    "ok": True,
                    "status": "PLANNED",
                    "source_package_sha256": package_sha256,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        pre_install = check_release_gate.evaluate_install_receipt_gate(
            phase="pre-install",
            require_package=True,
            install_receipt=None,
            package_gate=package_gate,
        )
        post_missing = check_release_gate.evaluate_install_receipt_gate(
            phase="post-install",
            require_package=True,
            install_receipt=None,
            package_gate=package_gate,
        )
        post_missing_without_require_package = (
            check_release_gate.evaluate_install_receipt_gate(
                phase="post-install",
                require_package=False,
                install_receipt=None,
                package_gate=package_gate,
            )
        )
        post_missing_field = check_release_gate.evaluate_install_receipt_gate(
            phase="post-install",
            require_package=True,
            install_receipt=missing_field,
            package_gate=package_gate,
        )
        post_invalid = check_release_gate.evaluate_install_receipt_gate(
            phase="post-install",
            require_package=True,
            install_receipt=invalid_format,
            package_gate=package_gate,
        )
        post_mismatch = check_release_gate.evaluate_install_receipt_gate(
            phase="post-install",
            require_package=True,
            install_receipt=mismatch,
            package_gate=package_gate,
        )
        post_matching = check_release_gate.evaluate_install_receipt_gate(
            phase="post-install",
            require_package=True,
            install_receipt=matching,
            package_gate=package_gate,
        )
        post_invalid_encoding = check_release_gate.evaluate_install_receipt_gate(
            phase="post-install",
            require_package=True,
            install_receipt=invalid_encoding,
            package_gate=package_gate,
        )
        post_hash_only = check_release_gate.evaluate_install_receipt_gate(
            phase="post-install",
            require_package=True,
            install_receipt=hash_only,
            package_gate=package_gate,
        )
        post_planned = check_release_gate.evaluate_install_receipt_gate(
            phase="post-install",
            require_package=True,
            install_receipt=planned,
            package_gate=package_gate,
        )
    return {
        "pre_install_behavior_unchanged": pre_install.get("status") == "NOT_RUN",
        "post_install_missing_receipt_rejected": (
            "install_receipt_required_but_not_supplied"
            in post_missing.get("problems", [])
        ),
        "post_install_receipt_required_without_redundant_flag": (
            "install_receipt_required_but_not_supplied"
            in post_missing_without_require_package.get("problems", [])
        ),
        "missing_top_level_package_sha_rejected": (
            "source_package_sha256_missing"
            in post_missing_field.get("problems", [])
        ),
        "invalid_top_level_package_sha_rejected": (
            "source_package_sha256_invalid" in post_invalid.get("problems", [])
        ),
        "mismatched_package_sha_rejected": (
            "source_package_sha256_mismatch" in post_mismatch.get("problems", [])
        ),
        "matching_package_sha_passes": (
            post_matching.get("status") == "PASSED"
            and post_matching.get("source_package_sha256") == package_sha256
            and post_matching.get("package_sha256") == package_sha256
        ),
        "invalid_utf8_receipt_rejected_stably": (
            "install_receipt_invalid_encoding"
            in post_invalid_encoding.get("problems", [])
        ),
        "hash_only_receipt_rejected": (
            "install_receipt_schema_invalid" in post_hash_only.get("problems", [])
            and "install_receipt_not_successful"
            in post_hash_only.get("problems", [])
            and "install_receipt_status_not_installed"
            in post_hash_only.get("problems", [])
        ),
        "planned_receipt_rejected": (
            "install_receipt_status_not_installed"
            in post_planned.get("problems", [])
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    harness_mode = parser.add_mutually_exclusive_group()
    harness_mode.add_argument("--npm-harness-self-test", action="store_true")
    harness_mode.add_argument("--npm-harness-check", action="store_true")
    args = parser.parse_args()
    selected_harness_mode = (
        "self-test"
        if args.npm_harness_self_test
        else "check"
        if args.npm_harness_check
        else None
    )
    if selected_harness_mode is not None:
        try:
            result = run_npm_harness(selected_harness_mode)
        except (AssertionError, OSError, subprocess.SubprocessError) as exc:
            result = {"ok": False, "error": str(exc)}
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"NPM_RELEASE_HARNESS_FAILED {exc}")
            return 2
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                "NPM_RELEASE_HARNESS_OK "
                f"mode={result['mode']} report_sha256={result['report_sha256']}"
            )
        return 0
    try:
        manifest = load_release_manifest()
        negative_cases = run_negative_contract_checks(manifest)
        surface_contract = release_surface_contract()
        if not all(surface_contract.values()):
            raise AssertionError(
                "release surface contract failed: "
                + ",".join(name for name, passed in surface_contract.items() if not passed)
            )
        identity_parity = release_identity_parity_contract(args.root)
        if not all(identity_parity.values()):
            raise AssertionError(
                "release identity parity failed: "
                + ",".join(name for name, passed in identity_parity.items() if not passed)
            )
        identity_parity_fixture = release_identity_parity_fixture_contract()
        if not all(identity_parity_fixture.values()):
            raise AssertionError(
                "release identity parity fixture failed: "
                + ",".join(
                    name for name, passed in identity_parity_fixture.items() if not passed
                )
            )
        install_receipt_contract = install_receipt_gate_fixture_contract()
        if not all(install_receipt_contract.values()):
            raise AssertionError(
                "install receipt gate fixture contract failed: "
                + ",".join(
                    name for name, passed in install_receipt_contract.items() if not passed
                )
            )
        npm_harness_contract = npm_harness_invocation_contract()
        if (
            npm_harness_contract["production_argv"]
            != npm_harness_contract["shared_immutable_prefix"]
            or npm_harness_contract["mode_only_delta"] != ["--self-test"]
            or npm_harness_contract["offline"] is not True
            or npm_harness_contract["python_override"] != "$PYTHON"
            or npm_harness_contract["shell"] is not False
        ):
            raise AssertionError("npm harness production/self-test invocation contract drifted")
        all_steps = selected_release_steps(
            manifest,
            include_active_copies=True,
            include_runtime=True,
        )
        candidate_steps = [
            step
            for step in all_steps
            if step.get("gate_class") == "source" and step.get("name") != "catalog_strict"
        ]
        candidate_names = {str(step["name"]) for step in candidate_steps}
        if len(candidate_steps) != 44:
            raise AssertionError(f"candidate pre-install step count drifted: {len(candidate_steps)}")
        if not {
            "npm_release_harness",
            "unified_cli",
            "court_open_fastpath",
            "startup_semantic_fastpath",
            "court_result_semantics",
            "cli_performance",
            "release_payload_manifest",
            "release_metadata",
            "shiguan_git_federation",
            "governance_framework",
            "court_agent_config",
            "court_codex_host_resolution",
        }.issubset(
            candidate_names
        ):
            raise AssertionError("candidate pre-install required source gates are missing")
        forbidden_candidate = {
            "catalog_strict",
            "codex_privacy_contract",
            "codex_host_resolution_live",
            "codex_agent_roles",
            "supercc_runtime_truth",
        }
        if candidate_names.intersection(forbidden_candidate):
            raise AssertionError("candidate pre-install selected installed/runtime gates")
        post_install_steps = [
            step for step in all_steps if step.get("gate_class") in {"installation", "runtime"}
        ]
        if len(post_install_steps) != 4:
            raise AssertionError(f"post-install step count drifted: {len(post_install_steps)}")
    except (ReleaseGateManifestError, AssertionError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"RELEASE_MANIFEST_FAILED {exc}")
        return 2

    steps = manifest["steps"]
    gate_counts = {
        gate_class: sum(1 for step in steps if step["gate_class"] == gate_class)  # type: ignore[index]
        for gate_class in ("source", "installation", "runtime")
    }
    result = {
        "ok": True,
        "schema": MANIFEST_SCHEMA,
        "release_identity": {
            "name": release_payload_manifest.NAME,
            "display_name": release_payload_manifest.DISPLAY_NAME,
            "release_label": release_payload_manifest.RELEASE_LABEL,
            "artifact_name": release_payload_manifest.ARTIFACT_NAME,
            "license": release_payload_manifest.LICENSE_ID,
            "archive_root": release_payload_manifest.ARCHIVE_ROOT,
        },
        "step_count": len(steps),  # type: ignore[arg-type]
        "gate_counts": gate_counts,
        "expanded_release_steps": [
            "capability_index",
            "npm_release_harness",
            "unified_cli",
            "court_open_fastpath",
            "startup_semantic_fastpath",
            "court_result_semantics",
            "cli_performance",
            "release_legal",
            "release_payload_manifest",
            "package_privacy_regressions",
            "release_artifact_builder",
        ],
        "release_surface_contract": surface_contract,
        "release_identity_parity_contract": identity_parity,
        "release_identity_parity_fixture_contract": identity_parity_fixture,
        "install_receipt_gate_fixture_contract": install_receipt_contract,
        "npm_harness_invocation_contract": npm_harness_contract,
        "candidate_preinstall_step_count": len(candidate_steps),
        "post_install_step_count": len(post_install_steps),
        "negative_contract_cases": negative_cases,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "RELEASE_MANIFEST_OK "
            f"steps={result['step_count']} source={gate_counts['source']} "
            f"installation={gate_counts['installation']} runtime={gate_counts['runtime']} "
            f"negative_cases={len(negative_cases)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
