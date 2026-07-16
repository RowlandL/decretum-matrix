#!/usr/bin/env python3
"""Validate the canonical skill identity contract.

The checker separates the canonical repository/product identity from protected
install and Shiguan directory locators. The manifest owns both boundaries.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Any

sys.dont_write_bytecode = True


SCHEMA = "court.skill_identity.check.v1"
MANIFEST_RELATIVE_PATH = Path("references/manifests/skill-identity.v1.json")
EXPECTED_IDENTITY = {
    "schema": "court.skill_identity.v1",
    "schema_version": 1,
    "display_name": "Decretum Matrix（诏令矩阵）",
    "canonical_skill_name": "decretum-matrix",
    "canonical_invocation": "$decretum-matrix",
    "community_license": "AGPL-3.0-only",
    "commercial_license_notice": "COMMERCIAL-LICENSE.md",
    "rights_owner": "孙华清",
    "github_repository": "https://github.com/RowlandL/decretum-matrix",
    "maintainer_github": "@RowlandL",
    "maintainer_github_id": 42199880,
}
EXPECTED_LOCATORS = {
    "repository_id": "decretum-matrix",
    "install_directory_name": "court-capability-router",
    "shiguan_namespace": "court-capability-router",
    "python_locator_pattern": "court.*",
    "environment_locator_pattern": "COURT_*",
    "service_name": "CourtShiguanDaemon",
    "directory_basename_may_differ_from_skill_name": True,
    "rename_policy": "rename_repository_preserve_install_and_shiguan_locators",
}
EXPECTED_ROLES = (
    "bingbu",
    "gongbu",
    "hubu",
    "libu",
    "libu-hr",
    "menxia",
    "patrol-inspector",
    "shangshu",
    "shiguan",
    "shiguan-hermes",
    "taizi",
    "xingbu",
    "zaochao",
    "zhongshu",
)
DISPLAY_NAME = EXPECTED_IDENTITY["display_name"]
CANONICAL_NAME = EXPECTED_IDENTITY["canonical_skill_name"]
CANONICAL_INVOCATION = EXPECTED_IDENTITY["canonical_invocation"]
WITHDRAWN_PATTERN = re.compile(r"DecreeMatri|decreematri")
HOST_METHODOLOGY_PATTERN = re.compile(r"super[\s_:-]*power(?:s)?", re.IGNORECASE)
HOST_METHODOLOGY_CURRENT_SURFACES = (
    Path("SKILL.md"),
    Path("references/court-offices-dispatch.md"),
    Path("scripts/check_court_agent_lifecycle.py"),
    Path("scripts/check_court_office_assignment_binding.py"),
    Path("docs/plans/2026-07-14-ccr-r2-shir-a02-execution-book.md"),
    Path("docs/plans/2026-07-14-court-capability-router-shiguan-install-remediation-plan.md"),
)


def _add_finding(
    findings: list[dict[str, str]],
    *,
    code: str,
    surface: str,
    path: Path | str,
    message: str,
) -> None:
    findings.append(
        {
            "code": code,
            "surface": surface,
            "path": Path(path).as_posix(),
            "message": message,
        }
    )


def _frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\r?\n(?P<body>.*?)\r?\n---(?:\r?\n|$)", text, re.DOTALL)
    if not match:
        return {}
    values: dict[str, str] = {}
    for line in match.group("body").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip().strip("\"'")
    return values


def _check_core_surfaces(root: Path, findings: list[dict[str, str]]) -> None:
    skill_relative = Path("SKILL.md")
    skill_path = root / skill_relative
    try:
        skill_text = skill_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        _add_finding(
            findings,
            code="IDENTITY_SKILL_UNREADABLE",
            surface="skill",
            path=skill_relative,
            message=f"{type(exc).__name__}: {exc}",
        )
    else:
        metadata = _frontmatter(skill_text)
        expected_fields = {
            "name": CANONICAL_NAME,
            "description": None,
        }
        for field, expected in expected_fields.items():
            actual = metadata.get(field)
            if actual is None or (expected is not None and actual != expected):
                _add_finding(
                    findings,
                    code="IDENTITY_SKILL_FRONTMATTER_MISMATCH",
                    surface="skill",
                    path=skill_relative,
                    message=f"frontmatter {field} must match canonical identity",
                )
        description = metadata.get("description", "")
        if DISPLAY_NAME not in description or CANONICAL_INVOCATION not in description:
            _add_finding(
                findings,
                code="IDENTITY_SKILL_DESCRIPTION_MISMATCH",
                surface="skill",
                path=skill_relative,
                message="description must contain canonical display name and invocation",
            )
        if not re.search(rf"(?m)^# {re.escape(DISPLAY_NAME)}\s*$", skill_text):
            _add_finding(
                findings,
                code="IDENTITY_SKILL_HEADING_MISMATCH",
                surface="skill",
                path=skill_relative,
                message="top-level skill heading must use the canonical display name",
            )
        if WITHDRAWN_PATTERN.search(skill_text):
            _add_finding(
                findings,
                code="IDENTITY_WITHDRAWN_NAME_CURRENT",
                surface="skill",
                path=skill_relative,
                message="withdrawn draft name is present on a current skill surface",
            )

    openai_relative = Path("agents/openai.yaml")
    openai_path = root / openai_relative
    try:
        openai_text = openai_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        _add_finding(
            findings,
            code="IDENTITY_OPENAI_UNREADABLE",
            surface="openai",
            path=openai_relative,
            message=f"{type(exc).__name__}: {exc}",
        )
    else:
        required_fragments = (
            f'display_name: "{DISPLAY_NAME}"',
            CANONICAL_INVOCATION,
        )
        if any(fragment not in openai_text for fragment in required_fragments):
            _add_finding(
                findings,
                code="IDENTITY_OPENAI_METADATA_MISMATCH",
                surface="openai",
                path=openai_relative,
                message="OpenAI metadata must expose the canonical display and invocation",
            )
        if WITHDRAWN_PATTERN.search(openai_text):
            _add_finding(
                findings,
                code="IDENTITY_WITHDRAWN_NAME_CURRENT",
                surface="openai",
                path=openai_relative,
                message="withdrawn draft name is present on current OpenAI metadata",
            )


def _check_profiles(root: Path, findings: list[dict[str, str]]) -> None:
    profile_root = root / "agents" / "standing-officials"
    actual_roles = {path.stem for path in profile_root.glob("*.toml")}
    if actual_roles != set(EXPECTED_ROLES):
        _add_finding(
            findings,
            code="IDENTITY_PROFILE_SET_MISMATCH",
            surface="profiles",
            path=Path("agents/standing-officials"),
            message=f"expected roles {list(EXPECTED_ROLES)!r}; got {sorted(actual_roles)!r}",
        )
    for role in EXPECTED_ROLES:
        relative = Path("agents/standing-officials") / f"{role}.toml"
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
            value = tomllib.loads(text)
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            _add_finding(
                findings,
                code="IDENTITY_PROFILE_INVALID",
                surface="profiles",
                path=relative,
                message=f"{type(exc).__name__}: {exc}",
            )
            continue
        profile = value.get("profile")
        if not isinstance(profile, dict):
            _add_finding(
                findings,
                code="IDENTITY_PROFILE_INVALID",
                surface="profiles",
                path=relative,
                message="[profile] table is required",
            )
            continue
        expected = {
            "governing_skill": CANONICAL_NAME,
            "governing_skill_invocation": CANONICAL_INVOCATION,
            "governing_skill_display_name": DISPLAY_NAME,
        }
        mismatches = [field for field, wanted in expected.items() if profile.get(field) != wanted]
        if mismatches or DISPLAY_NAME not in text or CANONICAL_INVOCATION not in text:
            _add_finding(
                findings,
                code="IDENTITY_PROFILE_BINDING_MISMATCH",
                surface="profiles",
                path=relative,
                message=f"canonical profile identity missing or stale: {mismatches!r}",
            )
        if WITHDRAWN_PATTERN.search(text):
            _add_finding(
                findings,
                code="IDENTITY_WITHDRAWN_NAME_CURRENT",
                surface="profiles",
                path=relative,
                message="withdrawn draft name is present on a current profile",
            )


def _check_dossiers(root: Path, findings: list[dict[str, str]]) -> None:
    dossier_root = root / "agents" / "office-dossiers"
    actual_roles = {
        path.parent.name for path in dossier_root.glob("*/AGENTS.md") if path.is_file()
    }
    if actual_roles != set(EXPECTED_ROLES):
        _add_finding(
            findings,
            code="IDENTITY_DOSSIER_SET_MISMATCH",
            surface="dossiers",
            path=Path("agents/office-dossiers"),
            message=f"expected roles {list(EXPECTED_ROLES)!r}; got {sorted(actual_roles)!r}",
        )
    expected_lines = (
        f"- governing_skill: {CANONICAL_NAME}",
        f"- governing_invocation: {CANONICAL_INVOCATION}",
        f"- governing_display_name: {DISPLAY_NAME}",
    )
    for role in EXPECTED_ROLES:
        relative = Path("agents/office-dossiers") / role / "AGENTS.md"
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            _add_finding(
                findings,
                code="IDENTITY_DOSSIER_UNREADABLE",
                surface="dossiers",
                path=relative,
                message=f"{type(exc).__name__}: {exc}",
            )
            continue
        missing = [line for line in expected_lines if line not in text]
        if missing:
            _add_finding(
                findings,
                code="IDENTITY_DOSSIER_BINDING_MISMATCH",
                surface="dossiers",
                path=relative,
                message=f"canonical dossier identity fields missing: {missing!r}",
            )
        if WITHDRAWN_PATTERN.search(text):
            _add_finding(
                findings,
                code="IDENTITY_WITHDRAWN_NAME_CURRENT",
                surface="dossiers",
                path=relative,
                message="withdrawn draft name is present on a current dossier",
            )


def _check_registry_surfaces(root: Path, findings: list[dict[str, str]]) -> None:
    map_relative = Path("references/department-map.md")
    try:
        map_text = (root / map_relative).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        _add_finding(
            findings,
            code="IDENTITY_DEPARTMENT_MAP_UNREADABLE",
            surface="department_map",
            path=map_relative,
            message=f"{type(exc).__name__}: {exc}",
        )
    else:
        capability_tokens: list[str] = []
        for line in map_text.splitlines():
            if line.startswith("|") and line.count("|") >= 3:
                capability_tokens.extend(re.findall(r"`([^`]+)`", line.split("|")[-2]))
        if CANONICAL_NAME not in capability_tokens:
            _add_finding(
                findings,
                code="IDENTITY_DEPARTMENT_MAP_CANONICAL_MISSING",
                surface="department_map",
                path=map_relative,
                message="department capability rows must register the canonical skill name",
            )
        if "court-capability-router" in capability_tokens:
            _add_finding(
                findings,
                code="IDENTITY_DEPARTMENT_MAP_LEGACY_CURRENT",
                surface="department_map",
                path=map_relative,
                message="legacy technical locator is still registered as a current skill name",
            )

    registry_relative = Path("references/court-capability-registry.md")
    try:
        registry_text = (root / registry_relative).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        _add_finding(
            findings,
            code="IDENTITY_CAPABILITY_REGISTRY_UNREADABLE",
            surface="capability_registry",
            path=registry_relative,
            message=f"{type(exc).__name__}: {exc}",
        )
    else:
        required = (
            "## Canonical Skill Identity",
            DISPLAY_NAME,
            CANONICAL_NAME,
            CANONICAL_INVOCATION,
            "skill-identity.v1.json",
            "deprecated",
            "probe_required",
        )
        missing = [fragment for fragment in required if fragment not in registry_text]
        if missing:
            _add_finding(
                findings,
                code="IDENTITY_CAPABILITY_REGISTRY_CONTRACT_MISSING",
                surface="capability_registry",
                path=registry_relative,
                message=f"canonical identity registry contract missing: {missing!r}",
            )

    manifest_path = root / MANIFEST_RELATIVE_PATH
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _add_finding(
            findings,
            code="IDENTITY_REGISTRY_API_BLOCKED",
            surface="registry_api",
            path=MANIFEST_RELATIVE_PATH,
            message=f"identity manifest unavailable: {type(exc).__name__}: {exc}",
        )
        return

    generator_relative = Path("scripts/refresh_capability_registry.py")
    generator_path = root / generator_relative
    scripts_path = str(generator_path.parent)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    try:
        spec = importlib.util.spec_from_file_location(
            "_court_identity_registry_probe", generator_path
        )
        if spec is None or spec.loader is None:
            raise ImportError("module spec unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:  # The checker reports a structured production-surface failure.
        _add_finding(
            findings,
            code="IDENTITY_REGISTRY_API_UNAVAILABLE",
            surface="registry_api",
            path=generator_relative,
            message=f"{type(exc).__name__}: {exc}",
        )
        return
    evaluator = getattr(module, "validate_skill_identity_records", None)
    if not callable(evaluator):
        _add_finding(
            findings,
            code="IDENTITY_REGISTRY_API_MISSING",
            surface="registry_api",
            path=generator_relative,
            message="validate_skill_identity_records(records, manifest) is required",
        )
        return

    canonical_record = {
        "kind": "skill",
        "source": "local_skill",
        "name": CANONICAL_NAME,
        "relative_path": "court-capability-router/SKILL.md",
    }
    passing = evaluator([canonical_record], manifest)
    duplicate_alias = evaluator(
        [
            canonical_record,
            {
                "kind": "skill",
                "source": "local_skill",
                "name": "court-capability-router",
                "relative_path": "court-capability-router-alias/SKILL.md",
            },
        ],
        manifest,
    )
    if not isinstance(passing, dict) or passing.get("status") != "PASSED":
        _add_finding(
            findings,
            code="IDENTITY_REGISTRY_OLD_LOCATOR_REJECTED",
            surface="registry_api",
            path=generator_relative,
            message="one canonical record pointing to the stable old locator must pass",
        )
    duplicate_codes = {
        item.get("code")
        for item in duplicate_alias.get("findings", [])
        if isinstance(item, dict)
    } if isinstance(duplicate_alias, dict) else set()
    if (
        not isinstance(duplicate_alias, dict)
        or duplicate_alias.get("status") != "FAILED"
        or "LEGACY_ALIAS_RECORD_FORBIDDEN" not in duplicate_codes
    ):
        _add_finding(
            findings,
            code="IDENTITY_REGISTRY_ALIAS_ACCEPTED",
            surface="registry_api",
            path=generator_relative,
            message="a second legacy-name skill record must fail closed",
        )


def _check_host_methodology_decoupling(
    root: Path,
    findings: list[dict[str, str]],
) -> None:
    for relative in HOST_METHODOLOGY_CURRENT_SURFACES:
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            _add_finding(
                findings,
                code="HOST_METHODOLOGY_SURFACE_UNREADABLE",
                surface="host_methodology",
                path=relative,
                message=f"{type(exc).__name__}: {exc}",
            )
            continue
        if HOST_METHODOLOGY_PATTERN.search(text):
            _add_finding(
                findings,
                code="HOST_METHODOLOGY_COUPLING_PRESENT",
                surface="host_methodology",
                path=relative,
                message="project authority must not name or depend on a host methodology family",
            )


def check_identity(root: Path) -> dict[str, Any]:
    """Return structured identity findings for ``root`` without side effects."""

    manifest_path = root / MANIFEST_RELATIVE_PATH
    findings: list[dict[str, str]] = []
    if not manifest_path.is_file():
        findings.append(
            {
                "code": "IDENTITY_MANIFEST_MISSING",
                "surface": "manifest",
                "path": MANIFEST_RELATIVE_PATH.as_posix(),
                "message": "canonical skill identity manifest is required",
            }
        )
    else:
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            findings.append(
                {
                    "code": "IDENTITY_MANIFEST_INVALID",
                    "surface": "manifest",
                    "path": MANIFEST_RELATIVE_PATH.as_posix(),
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
        else:
            if not isinstance(value, dict):
                findings.append(
                    {
                        "code": "IDENTITY_MANIFEST_INVALID",
                        "surface": "manifest",
                        "path": MANIFEST_RELATIVE_PATH.as_posix(),
                        "message": "manifest root must be a JSON object",
                    }
                )
            else:
                for field, expected in EXPECTED_IDENTITY.items():
                    actual = value.get(field)
                    if actual != expected:
                        findings.append(
                            {
                                "code": "IDENTITY_MANIFEST_VALUE_MISMATCH",
                                "surface": "manifest",
                                "path": MANIFEST_RELATIVE_PATH.as_posix(),
                                "message": (
                                    f"{field} must be {expected!r}; got {actual!r}"
                                ),
                            }
                        )

                withdrawn = value.get("withdrawn_names")
                if withdrawn != ["DecreeMatri", "decreematri"]:
                    findings.append(
                        {
                            "code": "IDENTITY_WITHDRAWN_NAMES_INVALID",
                            "surface": "manifest",
                            "path": MANIFEST_RELATIVE_PATH.as_posix(),
                            "message": "withdrawn_names must identify both withdrawn spellings",
                        }
                    )

                legacy_names = value.get("legacy_names")
                legacy = legacy_names[0] if isinstance(legacy_names, list) and len(legacy_names) == 1 else None
                if not isinstance(legacy, dict) or any(
                    (
                        legacy.get("name") != "court-capability-router",
                        legacy.get("invocation") != "$court-capability-router",
                        legacy.get("status") != "deprecated",
                        legacy.get("alias_support") not in {"probe_required", "unsupported"},
                        legacy.get("compatibility_claimed") is not False,
                    )
                ):
                    findings.append(
                        {
                            "code": "IDENTITY_LEGACY_POLICY_INVALID",
                            "surface": "manifest",
                            "path": MANIFEST_RELATIVE_PATH.as_posix(),
                            "message": (
                                "legacy identity must be one deprecated compatibility input "
                                "with unclaimed alias support"
                            ),
                        }
                    )

                locators = value.get("locator_policy")
                if not isinstance(locators, dict):
                    findings.append(
                        {
                            "code": "IDENTITY_LOCATOR_POLICY_INVALID",
                            "surface": "manifest",
                            "path": MANIFEST_RELATIVE_PATH.as_posix(),
                            "message": "locator_policy must be an object",
                        }
                    )
                else:
                    for field, expected in EXPECTED_LOCATORS.items():
                        actual = locators.get(field)
                        if actual != expected:
                            findings.append(
                                {
                                    "code": "IDENTITY_LOCATOR_VALUE_MISMATCH",
                                    "surface": "manifest",
                                    "path": MANIFEST_RELATIVE_PATH.as_posix(),
                                    "message": (
                                        f"locator_policy.{field} must be {expected!r}; "
                                        f"got {actual!r}"
                                    ),
                                }
                            )

    _check_core_surfaces(root, findings)
    _check_profiles(root, findings)
    _check_dossiers(root, findings)
    _check_registry_surfaces(root, findings)
    _check_host_methodology_decoupling(root, findings)
    surface_names = (
        "manifest",
        "skill",
        "openai",
        "profiles",
        "dossiers",
        "department_map",
        "capability_registry",
        "registry_api",
        "host_methodology",
    )
    surface_status = {
        surface: (
            "FAILED"
            if any(finding["surface"] == surface for finding in findings)
            else "PASSED"
        )
        for surface in surface_names
    }
    return {
        "schema": SCHEMA,
        "status": "PASSED" if not findings else "FAILED",
        "root": str(root),
        "surfaces": surface_status,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON (the default output format; retained for explicit callers).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Skill root to validate; defaults to the checker parent skill.",
    )
    args = parser.parse_args(argv)
    result = check_identity(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
