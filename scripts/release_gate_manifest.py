"""Load and validate the machine-readable court release-gate manifest."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = (ROOT / "scripts").resolve()
DEFAULT_MANIFEST_PATH = ROOT / "references" / "manifests" / "release-gates.v1.json"
MANIFEST_SCHEMA = "court.release_gates.v1"
ALLOWED_GATE_CLASSES = {"source", "installation", "runtime"}
ALLOWED_CONDITIONS = {"always", "active_copies_enabled", "runtime_enabled"}
ALLOWED_REQUIRED_PHASES = {
    "source",
    "candidate",
    "pre-install",
    "post-install",
    "full",
    "native",
}
STEP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
REQUIRED_STEP_CONTRACTS: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("quick_validate", "source", ("$PYTHON", "scripts/quick_validate.py", "."), "always"),
    ("catalog_strict", "source", ("$PYTHON", "scripts/check_catalog.py", "--strict"), "always"),
    ("portability", "source", ("$PYTHON", "scripts/check_portability.py"), "always"),
    ("release_manifest", "source", ("$PYTHON", "scripts/check_release_manifest.py", "--json"), "always"),
    (
        "npm_release_harness",
        "source",
        (
            "$PYTHON",
            "scripts/check_release_manifest.py",
            "--npm-harness-self-test",
            "--json",
        ),
        "always",
    ),
    (
        "unified_cli",
        "source",
        ("$PYTHON", "scripts/check_unified_cli.py", "--all", "--json"),
        "always",
    ),
    (
        "court_open_fastpath",
        "source",
        (
            "$PYTHON",
            "scripts/check_court_open_fastpath.py",
            "--serial-probes",
            "--json",
        ),
        "always",
    ),
    (
        "startup_semantic_fastpath",
        "source",
        ("$PYTHON", "scripts/check_startup_fastpath_contract.py", "--json"),
        "always",
    ),
    (
        "court_result_semantics",
        "source",
        ("$PYTHON", "scripts/check_court_result_semantics.py"),
        "always",
    ),
    (
        "cli_performance",
        "source",
        ("$PYTHON", "scripts/check_cli_performance.py", "--samples", "10", "--json"),
        "always",
    ),
    (
        "capability_index",
        "source",
        (
            "$PYTHON",
            "scripts/check_capability_index_gate.py",
            "--self-test",
            "--json",
        ),
        "always",
    ),
    (
        "release_legal",
        "source",
        ("$PYTHON", "scripts/check_release_legal.py", "--self-test", "--json"),
        "always",
    ),
    (
        "release_payload_manifest",
        "source",
        ("$PYTHON", "scripts/release_payload_manifest.py", "--self-test", "--check", "--json"),
        "always",
    ),
    (
        "package_privacy_regressions",
        "source",
        ("$PYTHON", "scripts/check_package_privacy.py", "-q"),
        "always",
    ),
    (
        "release_artifact_builder",
        "source",
        ("$PYTHON", "scripts/build_release_artifacts.py", "--self-test", "--json"),
        "always",
    ),
    (
        "source_state_budget",
        "source",
        ("$PYTHON", "scripts/check_source_state_budget.py", "--self-test", "--json"),
        "always",
    ),
    (
        "release_metadata",
        "source",
        ("$PYTHON", "scripts/check_release_metadata.py", "--json"),
        "always",
    ),
    (
        "shiguan_git_federation",
        "source",
        ("$PYTHON", "scripts/check_shiguan_git_federation.py", "--json"),
        "always",
    ),
    (
        "governance_framework",
        "source",
        ("$PYTHON", "scripts/check_governance_framework.py", "--json"),
        "always",
    ),
    (
        "court_dispatch_hierarchy",
        "source",
        ("$PYTHON", "scripts/check_court_dispatch_hierarchy.py"),
        "always",
    ),
    ("supercc_profiles", "source", ("$PYTHON", "scripts/check_supercc_profiles.py"), "always"),
    ("supercc_truth_gates", "source", ("$PYTHON", "scripts/check_supercc_truth_gates.py"), "always"),
    (
        "supercc_ministry_dispatch",
        "source",
        ("$PYTHON", "scripts/check_supercc_ministry_dispatch.py"),
        "always",
    ),
    (
        "supercc_squad_wrapper",
        "source",
        ("$PYTHON", "scripts/check_supercc_squad_wrapper.py"),
        "always",
    ),
    (
        "supercc_claude_hard_gates",
        "source",
        ("$PYTHON", "scripts/check_supercc_claude_hard_gates.py"),
        "always",
    ),
    ("supercc_super_entry", "source", ("$PYTHON", "scripts/check_supercc_super_entry.py"), "always"),
    (
        "supercc_client_selection",
        "source",
        ("$PYTHON", "scripts/check_supercc_client_selection.py"),
        "always",
    ),
    (
        "supercc_state_concurrency",
        "source",
        ("$PYTHON", "scripts/check_supercc_state_concurrency.py", "--json"),
        "always",
    ),
    ("court_runtime", "source", ("$PYTHON", "scripts/check_court_runtime.py"), "always"),
    ("court_agent_lifecycle", "source", ("$PYTHON", "scripts/check_court_agent_lifecycle.py"), "always"),
    ("court_dispatch_policy", "source", ("$PYTHON", "scripts/check_court_dispatch_policy.py"), "always"),
    (
        "court_codex_office_worker",
        "source",
        ("$PYTHON", "scripts/check_court_codex_office_worker.py"),
        "always",
    ),
    (
        "court_codex_host_resolution",
        "source",
        ("$PYTHON", "scripts/check_court_codex_host_resolution.py"),
        "always",
    ),
    (
        "court_agent_config",
        "source",
        ("$PYTHON", "scripts/check_court_agent_config.py"),
        "always",
    ),
    (
        "codex_privacy_contract",
        "installation",
        ("$PYTHON", "scripts/check_court_agent_config.py", "--live-runtime", "--format", "json"),
        "always",
    ),
    (
        "codex_host_resolution_live",
        "installation",
        ("$PYTHON", "scripts/court_codex_host_resolution.py", "--json"),
        "always",
    ),
    (
        "court_model_router",
        "source",
        ("$PYTHON", "scripts/check_court_model_router.py"),
        "always",
    ),
    (
        "court_office_bootstrap",
        "source",
        ("$PYTHON", "scripts/check_court_office_bootstrap.py"),
        "always",
    ),
    (
        "court_runtime_concurrency",
        "source",
        ("$PYTHON", "scripts/check_court_runtime_concurrency.py"),
        "always",
    ),
    (
        "court_intervention_matrix",
        "source",
        ("$PYTHON", "scripts/check_court_intervention_matrix.py"),
        "always",
    ),
    ("read_only_contract", "source", ("$PYTHON", "scripts/check_read_only_contract.py"), "always"),
    ("shiguan_concurrency", "source", ("$PYTHON", "scripts/check_shiguan_concurrency.py"), "always"),
    (
        "shiguan_http_security",
        "source",
        ("$PYTHON", "scripts/check_shiguan_http.py", "--static-only"),
        "always",
    ),
    (
        "shiguan_peer_state_transaction",
        "source",
        ("$PYTHON", "scripts/check_shiguan_peer_state_transaction.py"),
        "always",
    ),
    (
        "shiguan_queue_autosync_safety",
        "source",
        ("$PYTHON", "scripts/check_shiguan_queue_and_autosync_safety.py"),
        "always",
    ),
    (
        "obsidian_sync_transaction",
        "source",
        ("$PYTHON", "scripts/check_obsidian_sync_transaction.py", "--json"),
        "always",
    ),
    (
        "shiguan_pending_quarantine_plan",
        "source",
        ("$PYTHON", "scripts/check_shiguan_pending_quarantine_plan.py", "--format", "json"),
        "always",
    ),
    (
        "codex_agent_roles",
        "installation",
        ("$PYTHON", "scripts/check_codex_agent_roles.py", "--format", "json"),
        "always",
    ),
    (
        "supercc_runtime_truth",
        "runtime",
        ("$PYTHON", "scripts/check_supercc_functional.py", "--workspace", ".", "--json", "--strict"),
        "runtime_enabled",
    ),
)

# Stable evidence IDs are deliberately kept separate from the historical
# 49-step execution list.  This lets the gate add the required candidate/CI
# evidence contract without invalidating the existing candidate (44) and
# post-install (4) step projections consumed by adjacent source checks.
REQUIRED_CHECK_CONTRACTS: tuple[dict[str, object], ...] = (
    {
        "id": "supercc_truth_gates",
        "scope": "source",
        "phases": ["source", "candidate", "pre-install", "full"],
        "ci_job": "source-contracts",
        "entrypoint": "scripts/check_supercc_truth_gates.py",
        "command": ["$PYTHON", "scripts/check_supercc_truth_gates.py"],
        "timeout": 120,
        "domain_contract": {"kind": "sentinel", "success": "SUPERCC_TRUTH_GATES_OK"},
    },
    {
        "id": "runtime_no_file_rehash",
        "scope": "source",
        "phases": ["source", "candidate", "pre-install", "full"],
        "ci_job": "source-contracts",
        "entrypoint": "scripts/checks/check_runtime_no_file_rehash.py",
        "command": ["$PYTHON", "scripts/checks/check_runtime_no_file_rehash.py"],
        "timeout": 120,
        "domain_contract": {"kind": "sentinel", "success": "RUNTIME_NO_FILE_REHASH_OK ordinary_anchors=14 schema_preserved=true wrong_case_rejected=true reads_required=true"},
    },
    {
        "id": "portability",
        "scope": "source",
        "phases": ["source", "candidate", "pre-install", "full"],
        "ci_job": "source-contracts",
        "entrypoint": "scripts/check_portability.py",
        "command": ["$PYTHON", "scripts/check_portability.py"],
        "timeout": 120,
        "domain_contract": {"kind": "json", "required_fields": ["ok", "checks"]},
    },
    {
        "id": "court_preload_semantics",
        "scope": "source",
        "phases": ["source", "candidate", "pre-install", "full"],
        "ci_job": "source-contracts",
        "entrypoint": "scripts/check_court_preload_semantics.py",
        "command": ["$PYTHON", "scripts/check_court_preload_semantics.py"],
        "timeout": 180,
        "domain_contract": {"kind": "sentinel", "success": "COURT_PRELOAD_SEMANTICS_OK"},
    },
    {
        "id": "office_decree_startup",
        "scope": "source",
        "phases": ["source", "candidate", "pre-install", "full"],
        "ci_job": "source-contracts",
        "entrypoint": "scripts/checks/check_office_decree_startup.py",
        "command": ["$PYTHON", "scripts/checks/check_office_decree_startup.py"],
        "timeout": 180,
        "domain_contract": {"kind": "sentinel", "success": "OK"},
    },
    {
        "id": "runtime_identity_contract",
        "scope": "source",
        "phases": ["source", "candidate", "pre-install", "full"],
        "ci_job": "source-contracts",
        "entrypoint": "scripts/check_runtime_identity_contract.py",
        "command": ["$PYTHON", "scripts/check_runtime_identity_contract.py", "--json"],
        "timeout": 180,
        "domain_contract": {"kind": "json", "required_fields": ["ok", "status", "contract"]},
    },
    {
        "id": "unified_cli",
        "scope": "source",
        "phases": ["source", "candidate", "pre-install", "full"],
        "ci_job": "source-contracts",
        "entrypoint": "scripts/check_unified_cli.py",
        "command": ["$PYTHON", "scripts/check_unified_cli.py", "--all", "--json"],
        "timeout": 300,
        "domain_contract": {"kind": "json", "required_fields": ["ok", "status", "reports"]},
    },
    {
        "id": "install_projection_closure",
        "scope": "source",
        "phases": ["source", "candidate", "pre-install", "full"],
        "ci_job": "source-contracts",
        "entrypoint": "scripts/check_install_projection_closure.py",
        "command": ["$PYTHON", "scripts/check_install_projection_closure.py", "--self-test", "--json"],
        "timeout": 180,
        "domain_contract": {"kind": "json", "required_fields": ["ok", "status"]},
    },
    {
        "id": "install_current_agent_copy",
        "scope": "installation",
        "phases": ["candidate", "pre-install", "full"],
        "ci_job": "source-contracts",
        "entrypoint": "scripts/check_install_current_agent_copy.py",
        "command": ["$PYTHON", "scripts/check_install_current_agent_copy.py"],
        "timeout": 180,
        "domain_contract": {"kind": "json", "required_fields": ["ok", "schema"]},
    },
    {
        "id": "release_gate_policy_selftest",
        "scope": "source",
        "phases": ["source", "candidate", "pre-install", "full"],
        "ci_job": "source-contracts",
        "entrypoint": "scripts/check_release_gate.py",
        "command": ["$PYTHON", "scripts/check_release_gate.py", "--self-test", "--json"],
        "timeout": 180,
        "execution": "self_test",
        "domain_contract": {"kind": "json", "required_fields": ["ok", "schema", "manifest_self_test"]},
    },
    {
        "id": "package_entrypoint_isolated",
        "scope": "candidate/install",
        "phases": ["candidate", "pre-install", "full"],
        "ci_job": "package-entrypoint",
        "entrypoint": "same-source-candidate-isolated-public-entrypoint",
        "timeout": 300,
        "domain_contract": {"kind": "json", "required_fields": ["ok", "status"]},
    },
    {
        "id": "required_summary",
        "scope": "CI",
        "phases": ["source", "candidate", "pre-install", "post-install", "full", "native"],
        "ci_job": "required-summary",
        "entrypoint": "github-actions:required-summary",
        "timeout": 120,
        "domain_contract": {"kind": "json", "required_fields": ["status", "consumed_ids", "blocking"]},
    },
)
REQUIRED_CHECK_IDS = tuple(str(item["id"]) for item in REQUIRED_CHECK_CONTRACTS)


class ReleaseGateManifestError(ValueError):
    """Raised when the release-gate manifest violates its safety contract."""


def _fail(message: str) -> None:
    raise ReleaseGateManifestError(message)


def _has_parent_segment(value: str) -> bool:
    return ".." in value.replace("\\", "/").split("/")


def _is_absolute_path(value: str) -> bool:
    return (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )


def _validate_script_path(step_name: str, value: str) -> str:
    if not value or "\x00" in value or "\n" in value or "\r" in value:
        _fail(f"step {step_name}: invalid script path")
    if _is_absolute_path(value):
        _fail(f"step {step_name}: absolute script paths are forbidden")
    if _has_parent_segment(value):
        _fail(f"step {step_name}: parent traversal is forbidden")
    normalized = value.replace("\\", "/")
    if not normalized.startswith("scripts/") or not normalized.endswith(".py"):
        _fail(f"step {step_name}: script must be a relative scripts/*.py path")
    candidate = (ROOT / Path(normalized)).resolve()
    try:
        candidate.relative_to(SCRIPTS_ROOT)
    except ValueError:
        _fail(f"step {step_name}: script resolves outside the skill scripts root")
    if not candidate.is_file():
        _fail(f"step {step_name}: script is missing: {normalized}")
    return normalized


def _validate_command(step_name: str, value: object) -> list[str]:
    if isinstance(value, str) or not isinstance(value, list):
        _fail(f"step {step_name}: command must be an argv list, not a shell string")
    if len(value) < 2:
        _fail(f"step {step_name}: command must contain $PYTHON and a script path")
    command: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item or "\x00" in item or "\n" in item or "\r" in item:
            _fail(f"step {step_name}: command argv[{index}] must be a non-empty single-line string")
        if _has_parent_segment(item):
            _fail(f"step {step_name}: parent traversal is forbidden in command argv[{index}]")
        command.append(item)
    if command[0] != "$PYTHON":
        _fail(f"step {step_name}: command must use $PYTHON as argv[0]")
    command[1] = _validate_script_path(step_name, command[1])
    return command


def _validate_package_gate(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail("package_gate must be an object")
    expected = {
        "optional_by_default": True,
        "require_flag": "--require-package",
        "validator": "package_skill.validate_zip",
    }
    if value != expected:
        _fail("package_gate contract drifted from the existing optional package semantics")
    return dict(expected)


def _validate_required_checks(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        _fail("required_checks must be a list")
    if len(value) != len(REQUIRED_CHECK_CONTRACTS):
        _fail(
            "required_checks must contain each stable ID exactly once "
            f"(expected {len(REQUIRED_CHECK_CONTRACTS)}, got {len(value)})"
        )
    normalized: list[dict[str, object]] = []
    for index, (raw, expected) in enumerate(zip(value, REQUIRED_CHECK_CONTRACTS)):
        if not isinstance(raw, dict):
            _fail(f"required_checks[{index}] must be an object")
        if raw != expected:
            _fail(
                f"required check {raw.get('id', index)!r} drifted from the "
                "stable evidence contract"
            )
        normalized.append(dict(raw))
    actual_ids = [str(item["id"]) for item in normalized]
    if len(set(actual_ids)) != len(actual_ids):
        _fail("required_checks IDs must be unique")
    return normalized


def validate_release_manifest(value: object) -> dict[str, object]:
    """Validate and normalize an already parsed release-gate manifest."""

    if not isinstance(value, dict):
        _fail("release manifest must be a JSON object")
    unknown_top = set(value) - {"schema", "package_gate", "required_checks", "steps"}
    if unknown_top:
        _fail(f"unknown top-level manifest fields: {sorted(unknown_top)}")
    if value.get("schema") != MANIFEST_SCHEMA:
        _fail(f"manifest schema must be {MANIFEST_SCHEMA}")
    package_gate = _validate_package_gate(value.get("package_gate"))
    required_checks = _validate_required_checks(value.get("required_checks"))
    raw_steps = value.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        _fail("manifest steps must be a non-empty list")

    normalized_steps: list[dict[str, object]] = []
    names: set[str] = set()
    allowed_fields = {"name", "gate_class", "command", "timeout", "allowed_returncodes", "condition"}
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            _fail(f"step[{index}] must be an object")
        unknown = set(raw_step) - allowed_fields
        if unknown:
            _fail(f"step[{index}] has unknown fields: {sorted(unknown)}")
        name = raw_step.get("name")
        if not isinstance(name, str) or not STEP_NAME_RE.fullmatch(name):
            _fail(f"step[{index}] has an invalid name")
        if name in names:
            _fail(f"duplicate release step name: {name}")
        names.add(name)

        gate_class = raw_step.get("gate_class")
        if gate_class not in ALLOWED_GATE_CLASSES:
            _fail(f"step {name}: invalid gate_class {gate_class!r}")
        timeout = raw_step.get("timeout")
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            _fail(f"step {name}: timeout must be an integer from 1 to 3600 seconds")
        allowed_returncodes = raw_step.get("allowed_returncodes")
        if not isinstance(allowed_returncodes, list) or not allowed_returncodes:
            _fail(f"step {name}: allowed_returncodes must be a non-empty list")
        if any(type(code) is not int or not 0 <= code <= 255 for code in allowed_returncodes):
            _fail(f"step {name}: allowed_returncodes must contain integers from 0 to 255")
        if len(set(allowed_returncodes)) != len(allowed_returncodes):
            _fail(f"step {name}: allowed_returncodes must be unique")
        condition = raw_step.get("condition", "always")
        if condition not in ALLOWED_CONDITIONS:
            _fail(f"step {name}: invalid condition {condition!r}")

        normalized_steps.append(
            {
                "name": name,
                "gate_class": gate_class,
                "command": _validate_command(name, raw_step.get("command")),
                "timeout": timeout,
                "allowed_returncodes": list(allowed_returncodes),
                "condition": condition,
            }
        )
    actual_names = [str(step["name"]) for step in normalized_steps]
    expected_names = [contract[0] for contract in REQUIRED_STEP_CONTRACTS]
    if actual_names != expected_names:
        _fail(
            "manifest steps must exactly match the external required-step policy "
            f"(expected {expected_names}, got {actual_names})"
        )
    for step, (name, gate_class, command, condition) in zip(normalized_steps, REQUIRED_STEP_CONTRACTS):
        if step["gate_class"] != gate_class:
            _fail(f"step {name}: gate_class drifted from required policy")
        if step["command"] != list(command):
            _fail(f"step {name}: command drifted from required policy")
        if step["condition"] != condition:
            _fail(f"step {name}: condition drifted from required policy")
        if step["allowed_returncodes"] != [0]:
            _fail(f"step {name}: allowed_returncodes drifted from required policy")
    return {
        "schema": MANIFEST_SCHEMA,
        "package_gate": package_gate,
        "required_checks": required_checks,
        "steps": normalized_steps,
    }


def load_release_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, object]:
    """Read, validate, and normalize the release-gate manifest."""

    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReleaseGateManifestError(f"cannot read release manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseGateManifestError(f"invalid release manifest JSON {path}: {exc}") from exc
    return validate_release_manifest(value)


def selected_release_steps(
    manifest: dict[str, object],
    *,
    include_active_copies: bool,
    include_runtime: bool,
) -> list[dict[str, object]]:
    """Return validated steps in manifest order for the requested gate mode."""

    selected: list[dict[str, object]] = []
    for step in manifest["steps"]:  # type: ignore[index]
        condition = step["condition"]
        if condition == "active_copies_enabled" and not include_active_copies:
            continue
        if condition == "runtime_enabled" and not include_runtime:
            continue
        selected.append(dict(step))
    return selected


def expand_step_command(step: dict[str, object], python_executable: str = sys.executable) -> list[str]:
    """Replace the sole executable placeholder without invoking a shell."""

    command = list(step["command"])  # type: ignore[arg-type]
    if not command or command[0] != "$PYTHON":  # defensive after validation
        _fail(f"step {step.get('name')}: validated command lost its $PYTHON placeholder")
    command[0] = python_executable
    return command
