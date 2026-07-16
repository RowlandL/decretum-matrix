"""Validate release-gate policy plus Decretum Matrix package identity."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import sys

sys.dont_write_bytecode = True

from release_gate_manifest import (
    MANIFEST_SCHEMA,
    ReleaseGateManifestError,
    load_release_manifest,
    validate_release_manifest,
)
import build_release_artifacts
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
        == "decretum-matrix-beta0.5.10.zip",
        "canonical_release_label": release_payload_manifest.RELEASE_LABEL == "beta0.5.10",
        "agpl_only": getattr(release_payload_manifest, "LICENSE_ID", None) == "AGPL-3.0-only",
        "artifact_builder_identity": build_release_artifacts.NAME == "decretum-matrix",
        "stable_locator": (
            package_skill.ROOT_NAME == "court-capability-router"
            and release_payload_manifest.ARCHIVE_ROOT == "court-capability-router/"
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
