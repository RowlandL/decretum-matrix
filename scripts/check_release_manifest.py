"""Validate release-gate policy plus Decretum Matrix package identity."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile

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
import package_skill
import release_payload_manifest


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
        == "decretum-matrix-beta0.5.11.zip",
        "canonical_release_label": release_payload_manifest.RELEASE_LABEL == "beta0.5.11",
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
            package_skill.ROOT_NAME == "court-capability-router"
            and release_payload_manifest.ARCHIVE_ROOT == "court-capability-router/"
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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        manifest = load_release_manifest()
        negative_cases = run_negative_contract_checks(manifest)
        surface_contract = release_surface_contract()
        if not all(surface_contract.values()):
            raise AssertionError(
                "release surface contract failed: "
                + ",".join(name for name, passed in surface_contract.items() if not passed)
            )
        install_receipt_contract = install_receipt_gate_fixture_contract()
        if not all(install_receipt_contract.values()):
            raise AssertionError(
                "install receipt gate fixture contract failed: "
                + ",".join(
                    name for name, passed in install_receipt_contract.items() if not passed
                )
            )
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
        if len(candidate_steps) != 34:
            raise AssertionError(f"candidate pre-install step count drifted: {len(candidate_steps)}")
        if not {"release_payload_manifest", "court_agent_config", "court_codex_host_resolution"}.issubset(
            candidate_names
        ):
            raise AssertionError("candidate pre-install required source gates are missing")
        forbidden_candidate = {
            "catalog_strict",
            "codex_privacy_contract",
            "codex_host_resolution_live",
            "codex_agent_roles",
            "active_copy_hashes",
            "supercc_runtime_truth",
        }
        if candidate_names.intersection(forbidden_candidate):
            raise AssertionError("candidate pre-install selected installed/runtime gates")
        post_install_steps = [
            step for step in all_steps if step.get("gate_class") in {"installation", "runtime"}
        ]
        if len(post_install_steps) != 5:
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
            "release_legal",
            "release_payload_manifest",
            "package_privacy_regressions",
            "release_artifact_builder",
        ],
        "release_surface_contract": surface_contract,
        "install_receipt_gate_fixture_contract": install_receipt_contract,
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
