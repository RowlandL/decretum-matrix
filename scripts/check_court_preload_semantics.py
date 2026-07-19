"""RED checks for A02 pinned preload and same-task recovery semantics.

This checker is intentionally broader than the existing name/profile/skill
binding checker.  It specifies the remaining A02 contract without changing
production code:

* sufficient court semantics are pinned before the ordinary overview;
* all fourteen offices bind the exact profile, dossier, and court skill;
* persisted preload/binding paths are repository-relative;
* prompt-only or mismatched office identity is rejected;
* ministries cannot inherit Three-Departments audit or Taizi coordination;
* dispatch hierarchy remains Shangshu -> ministry -> ministry-owned worker;
* amended hard behaviors live in the pinned nucleus or one directly linked,
  uniquely owning governing reference, never MEMORY.md;
* create/correct/resume preserves one task, binds charter revisions, invalidates
  derived state, and re-enters Three Departments before ministry execution.

Run with ``python -B scripts/check_court_preload_semantics.py``.  During the RED
phase the command must exit non-zero and enumerate real contract gaps.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
import hashlib
import inspect
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from typing import Callable

sys.dont_write_bytecode = True

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None  # type: ignore[assignment]

import court_office_bootstrap
import court_runtime
from court_intake_gate import minimal_request_understanding_example
import check_capability_index_gate


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "SKILL.md"
PROFILE_ROOT = ROOT / "agents" / "standing-officials"
DOSSIER_ROOT = ROOT / "agents" / "office-dossiers"
CAPABILITY_REGISTRY_PATH = ROOT / "references" / "court-capability-registry.md"
CAPABILITY_INDEX_GATE_PATH = ROOT / "scripts" / "check_capability_index_gate.py"
REFRESH_CAPABILITY_REGISTRY_PATH = ROOT / "scripts" / "refresh_capability_registry.py"

MINISTRY_ROLES = ("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu")
ACTIVE_DERIVED_STATUSES = {"admitted", "starting", "running", "active", "assigned"}

DIRECT_GOVERNING_REFERENCE_RE = re.compile(
    r"\[[^\]]+\]\((references/[A-Za-z0-9_./-]+\.md)(?:#[^)]+)?\)"
)
AMENDED_BEHAVIOR_SOURCE_CONTRACTS: dict[
    str, tuple[tuple[str, ...], ...]
] = {
    "p05_hierarchical_budget_pool": (
        (r"\bhierarchical_budget_pool_gate\b",),
        (r"\bbudget_id\b",),
        (r"\bparent_budget_id\b",),
        (r"\blease\b",),
        (r"\breserve\b",),
        (r"\bdirect_superior\b",),
    ),
    "shangshu_ministry_owned_worker_chain": (
        (r"\bshangshu_six_ministries_hierarchy_gate\b",),
        (r"\bministry_craftsman_hierarchy_gate\b",),
        (r"direct_superior\s*=\s*shangshu",),
        (r"direct_superior\s*=\s*<owning_ministry_role>",),
        (r"\bworker\b", r"\bcraftsman\b", r"工匠"),
    ),
    "registry_first_libu_hr_maintenance": (
        (r"\bregistered_capability_first_gate\b",),
        (r"\blibu_hr_capability_registry_maintenance_gate\b",),
        (r"\bmissing\b",),
        (r"\bstale\b",),
        (r"\bcorrupt\b",),
        (r"\bno_sufficient_match\b",),
        (r"\bskill_install\b",),
        (r"\bskill_upgrade\b",),
        (r"\bhash_drift\b",),
        (r"\bversion_drift\b",),
        (r"\bdispatch_failure\b",),
        (r"\bphase_closeout\b",),
    ),
    "phase_level_tdd": (
        (r"\bphase_level_tdd_review_gate\b",),
        (r"\bRED\b",),
        (r"\bGREEN\s*/\s*SPEC\b",),
        (r"\bQUALITY\b",),
    ),
    "shared_shiguan_current_tool_install_boundary": (
        (r"\bcurrent_tool_only_install_gate\b",),
        (r"\bno_unrequested_tool_gate\b",),
        (r"\.agents",),
        (r"shared\s+Shiguan", r"共享史馆"),
        (r"current[- ]tool", r"当前工具"),
        (r"newest\s+explicit\s+user", r"最新.*明确.*用户"),
    ),
    "agent_tool_memory_obsidian_projection": (
        (r"\bagent_tool_memory_obsidian_projection_gate\b",),
        (r"\binstalled_tool_manifest_eligibility_gate\b",),
        (r"\bper_tool_memory_graph_isolation_gate\b",),
        (r"\bblank_host_memory_probe_before_write_gate\b",),
        (r"\bmetadata_index_only_projection_gate\b",),
        (r"\bsource_read_only\b",),
        (r"\bprompt_evidence_state\b",),
        (r"\bcanonical_tool_classes\b",),
        (r"\bcodex\b",),
        (r"\bhermes\b",),
        (r"\bclaude-code\b",),
        (r"other:<stable-id>",),
        (r"\btool_memory_state\b",),
        (r"\benabled\b",),
        (r"\bdisabled\b",),
        (r"\bunavailable\b",),
        (r"\bunknown\b",),
        (r"\bunknown_state_fail_closed\b",),
        (r"\bno_unrequested_tool_mutation_gate\b",),
    ),
    "blank_host_controller_config_remediation": (
        (r"\bblank_host_controller_config_remediation_gate\b",),
        (r"\bnormalized_controller_tool_classes\b",),
        (r"\bcodex\b",),
        (r"\bclaude-code\b",),
        (r"\bhermes\b",),
        (r"other:<stable-id>",),
        (r"\bREMINDER_ONLY\b",),
        (r"\breminder_only_nonblocking_gate\b",),
        (r"\bno_false_compliance\b",),
        (r"\bnewest_explicit_change_authority_gate\b",),
        (r"\bcc_switch_upstream_controller_first_gate\b",),
        (r"\breversible_backup_transaction_gate\b",),
        (r"\beffective_config_reread_parse_acceptance_gate\b",),
        (r"\bruntime_probe_when_available\b",),
        (r"\bdb_receipt_never_sufficient\b",),
        (r"\bcodex_dual_config_semantic_delta_gate\b",),
        (r"\bconfig\.toml\b",),
        (r"\bmanaged_config\.toml\b",),
        (r"\bsemantically_compatible_delta\b",),
        (r"\bhermes_controller_non_materialization_gate\b",),
        (r"\bexplicitly_authorized_certain_reversible_actual_file_fallback\b",),
        (r"\bNO_CHANGE_UNCERTAIN\b",),
        (r"\bno_change_uncertain_explanation_zero_writes_gate\b",),
        (r"\bpreserve_secrets_provider_unknown_keys_gate\b",),
    ),
    "verified_ccswitch_effective_config_macos_license_release": (
        (r"\bccswitch_version_schema_allowlist_gate\b",),
        (r"\bCC Switch 3\.16\.x\b",),
        (r"\buser_version\s*=\s*11\b",),
        (r"\bCC Switch 3\.17\.x\b",),
        (r"\buser_version\s*=\s*13\b",),
        (r"\bprofiles_six_columns_gate\b",),
        (
            r"\bprofiles_columns\s*=\s*id\s*[,/]\s*name\s*[,/]\s*payload"
            r"\s*[,/]\s*sort_order\s*[,/]\s*created_at\s*[,/]\s*updated_at\b",
        ),
        (r"\bproxy_request_logs_input_token_semantics\b",),
        (r"\busage_daily_rollups_input_token_semantics\b",),
        (r"\bversion_schema_mismatch_or_unknown_fail_closed_gate\b",),
        (r"\badapter_no_schema_migration_gate\b",),
        (r"\btool_blocks_synthetic_fixture_only_gate\b",),
        (r"\beffective_config_last_moment_per_file_semantic_reread_gate\b",),
        (r"\bcodex_dual_toml_no_permanent_byte_equality_gate\b",),
        (r"\bconfig\.toml\b",),
        (r"\bmanaged_config\.toml\b",),
        (r"\bhermes_platform_config_path_gate\b",),
        (r"\bhermes_config_dir\b",),
        (r"\bHERMES_HOME\b",),
        (r"%LOCALAPPDATA%\\hermes",),
        (r"<home>\\AppData\\Local\\hermes",),
        (r"\bDarwin/Linux\b",),
        (r"~/\.hermes",),
        (r"\bconfig\.yaml\b",),
        (r"\bfinal_macos_same_or_separate_package_gate\b",),
        (r"\bsame_release_package\b",),
        (r"\bseparate_macos_package\b",),
        (r"\brights_owner_exact_name_gate\b",),
        (r"孙华清",),
        (r"\bpublic_maintainer_identity_gate\b",),
        (r"@RowlandL",),
        (r"\bcommunity_agpl_3_0_only_release_gate\b",),
        (r"\bAGPL-3\.0-only\b",),
        (r"\bLICENSE\b",),
        (r"\bNOTICE\b",),
        (r"\bcommercial_license_separate_written_agreement_gate\b",),
        (r"\bCOMMERCIAL-LICENSE\.md\b",),
        (r"\bCLA\.md\b",),
        (r"\bTRADEMARKS\.md\b",),
        (r"\bupstream_mit_provenance_preserved_gate\b",),
        (r"\bPROVENANCE\.md\b",),
        (r"\bTHIRD_PARTY_NOTICES\.md\b",),
        (r"cft0808/edict",),
        (r"14a207557719c046af0f993a7bff1cc5a5015b33",),
        (r"\bhistorical_apache_grants_irrevocable_gate\b",),
        (r"\bApache-2\.0\b",),
        (r"\bno_contradictory_license_terms_gate\b",),
    ),
    "continuation_closeout": (
        (r"\bresume_correction_same_task_gate\b",),
        (r"\bsame\s+task\b",),
        (r"\bderived\s+state\b",),
        (r"\bThree\s+Departments\b", r"三省"),
        (r"\bphase\s+closeout\b", r"阶段结项"),
    ),
}

# This is deliberately a string fixture, not a path and not host memory input.
FAKE_MEMORY_MD = """
# MEMORY.md fixture only
hierarchical_budget_pool_gate budget_id parent_budget_id lease reserve direct_superior
shangshu_six_ministries_hierarchy_gate ministry_craftsman_hierarchy_gate
direct_superior=shangshu direct_superior=<owning_ministry_role> worker craftsman
registered_capability_first_gate libu_hr_capability_registry_maintenance_gate
missing stale corrupt no_sufficient_match skill_install skill_upgrade hash_drift
version_drift dispatch_failure phase_closeout
phase_level_tdd_review_gate RED GREEN/SPEC QUALITY
current_tool_only_install_gate no_unrequested_tool_gate .agents shared Shiguan
current-tool newest explicit user
agent_tool_memory_obsidian_projection_gate installed_tool_manifest_eligibility_gate
per_tool_memory_graph_isolation_gate blank_host_memory_probe_before_write_gate
metadata_index_only_projection_gate source_read_only prompt_evidence_state
canonical_tool_classes codex hermes claude-code other:<stable-id>
tool_memory_state enabled disabled unavailable unknown
unknown_state_fail_closed no_unrequested_tool_mutation_gate
blank_host_controller_config_remediation_gate normalized_controller_tool_classes
codex claude-code hermes other:<stable-id>
REMINDER_ONLY reminder_only_nonblocking_gate no_false_compliance
newest_explicit_change_authority_gate cc_switch_upstream_controller_first_gate
reversible_backup_transaction_gate effective_config_reread_parse_acceptance_gate
runtime_probe_when_available db_receipt_never_sufficient
codex_dual_config_semantic_delta_gate config.toml managed_config.toml
semantically_compatible_delta hermes_controller_non_materialization_gate
explicitly_authorized_certain_reversible_actual_file_fallback
NO_CHANGE_UNCERTAIN no_change_uncertain_explanation_zero_writes_gate
preserve_secrets_provider_unknown_keys_gate
ccswitch_version_schema_allowlist_gate CC Switch 3.16.x user_version=11
CC Switch 3.17.x user_version=13 profiles_six_columns_gate
profiles_columns=id/name/payload/sort_order/created_at/updated_at
proxy_request_logs_input_token_semantics usage_daily_rollups_input_token_semantics
version_schema_mismatch_or_unknown_fail_closed_gate adapter_no_schema_migration_gate
tool_blocks_synthetic_fixture_only_gate
effective_config_last_moment_per_file_semantic_reread_gate
codex_dual_toml_no_permanent_byte_equality_gate config.toml managed_config.toml
hermes_platform_config_path_gate hermes_config_dir HERMES_HOME
%LOCALAPPDATA%\\hermes <home>\\AppData\\Local\\hermes Darwin/Linux ~/.hermes config.yaml
final_macos_same_or_separate_package_gate same_release_package separate_macos_package
rights_owner_exact_name_gate 孙华清 public_maintainer_identity_gate @RowlandL
community_agpl_3_0_only_release_gate AGPL-3.0-only LICENSE NOTICE
commercial_license_separate_written_agreement_gate COMMERCIAL-LICENSE.md CLA.md
TRADEMARKS.md upstream_mit_provenance_preserved_gate PROVENANCE.md
THIRD_PARTY_NOTICES.md cft0808/edict
14a207557719c046af0f993a7bff1cc5a5015b33
historical_apache_grants_irrevocable_gate Apache-2.0
no_contradictory_license_terms_gate
resume_correction_same_task_gate same task derived state Three Departments
phase closeout
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def pinned_nucleus_text(skill_text: str) -> str:
    marker = re.search(r"(?m)^## Overview\s*$", skill_text)
    require(marker is not None, "SKILL.md has no bounded Overview marker")
    return skill_text[: marker.start()]


def text_satisfies_source_contract(
    text: str,
    required_pattern_groups: tuple[tuple[str, ...], ...],
) -> bool:
    return all(
        any(re.search(pattern, text, re.IGNORECASE) for pattern in alternatives)
        for alternatives in required_pattern_groups
    )


def direct_governing_reference_paths(skill_text: str) -> tuple[Path, ...]:
    reference_root = (ROOT / "references").resolve()
    paths: list[Path] = []
    for relative_text in sorted(set(DIRECT_GOVERNING_REFERENCE_RE.findall(skill_text))):
        relative = PurePosixPath(relative_text)
        require(".." not in relative.parts, f"governing reference escapes root: {relative_text}")
        path = ROOT.joinpath(*relative.parts).resolve()
        try:
            path.relative_to(reference_root)
        except ValueError as exc:
            raise AssertionError(
                f"governing reference is outside references/: {relative_text}"
            ) from exc
        require(path.is_file(), f"direct governing reference is missing: {relative_text}")
        paths.append(path)
    return tuple(paths)


def amended_behavior_sources(
    skill_text: str,
    direct_reference_texts: dict[str, str],
) -> dict[str, tuple[str, ...]]:
    candidates = {
        "SKILL.md#pinned-nucleus": pinned_nucleus_text(skill_text),
        **direct_reference_texts,
    }
    return {
        behavior: tuple(
            source
            for source, text in candidates.items()
            if text_satisfies_source_contract(text, required_pattern_groups)
        )
        for behavior, required_pattern_groups in AMENDED_BEHAVIOR_SOURCE_CONTRACTS.items()
    }


def check_amended_behavior_source_reachability() -> None:
    fixture_matches = {
        behavior
        for behavior, required in AMENDED_BEHAVIOR_SOURCE_CONTRACTS.items()
        if text_satisfies_source_contract(FAKE_MEMORY_MD, required)
    }
    require(
        fixture_matches == set(AMENDED_BEHAVIOR_SOURCE_CONTRACTS),
        "fake MEMORY.md fixture does not contain every amended behavior marker",
    )

    # MEMORY.md is intentionally ineligible: only the supplied SKILL text and its
    # direct project-reference mapping enter source resolution.
    fixture_sources = amended_behavior_sources("# Fixture\n\n## Overview\n", {})
    require(
        all(not sources for sources in fixture_sources.values()),
        "fake MEMORY.md satisfied a missing SKILL/reference source",
    )

    opened_paths: list[Path] = []

    def tracked_read(path: Path) -> str:
        resolved = path.resolve()
        opened_paths.append(resolved)
        return resolved.read_text(encoding="utf-8")

    skill_text = tracked_read(SKILL_PATH)
    reference_paths = direct_governing_reference_paths(skill_text)
    reference_texts = {
        path.relative_to(ROOT).as_posix(): tracked_read(path)
        for path in reference_paths
    }
    require(
        not any(path.name.casefold() == "memory.md" for path in opened_paths),
        "source reachability opened a host MEMORY.md",
    )

    resolved = amended_behavior_sources(skill_text, reference_texts)
    gaps: list[str] = []
    for behavior, sources in resolved.items():
        if not sources:
            gaps.append(f"{behavior}:missing")
        elif len(sources) != 1:
            gaps.append(f"{behavior}:not_unique[{','.join(sources)}]")
    require(
        not gaps,
        "amended hard behavior source drift: " + "; ".join(gaps),
    )


def normalized_relative_text(value: object) -> str:
    text = str(value or "").strip().replace("\\", "/")
    path = PurePosixPath(text)
    require(bool(text), "persisted path is empty")
    require(not path.is_absolute(), f"persisted path is absolute: {text}")
    require(not re.match(r"^[A-Za-z]:/", text), f"persisted path has a drive: {text}")
    require(".." not in path.parts, f"persisted path escapes the skill root: {text}")
    require(text == path.as_posix(), f"persisted path is not normalized: {text}")
    return text


def resolve_manifest_path(value: object) -> Path:
    text = str(value or "").strip()
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate.resolve()
    relative = PurePosixPath(text.replace("\\", "/"))
    return ROOT.joinpath(*relative.parts).resolve()


def skill_requirement_fixture() -> list[dict[str, str]]:
    digest = sha256_file(SKILL_PATH)
    source = str(SKILL_PATH.resolve())
    return [
        {
            "name": "decretum-matrix",
            "source": source,
            "sha256": digest,
            "purpose": "governing court workflow",
            "ack_name": "decretum-matrix",
            "ack_sha256": digest,
        }
    ]


def check_pinned_initial_semantics() -> None:
    lines = SKILL_PATH.read_text(encoding="utf-8").splitlines()
    try:
        overview_index = next(
            index for index, line in enumerate(lines) if line.strip() == "## Overview"
        )
    except StopIteration as exc:
        raise AssertionError("SKILL.md has no bounded Overview marker") from exc

    require(overview_index <= 160, "pinned initial semantics are not early")
    pinned = "\n".join(lines[:overview_index])
    missing: list[str] = []

    if not ("最新旨意" in pinned or "Newest user wording controls" in pinned):
        missing.append("newest_decree")
    if not all(token in pinned for token in ("approval", "autonomous", "super", "superCC")):
        missing.append("authority_classes")
    if not (
        ("super并行" in pinned or "ordinary_parallel" in pinned)
        and ("topology" in pinned.lower() or "拓扑" in pinned)
    ):
        missing.append("authority_topology_split")
    if not all(token in pinned for token in ("太子", "中书省", "门下省", "尚书省", "六部")):
        missing.append("taizi_three_departments_six_ministries")
    if not ("工坊" in pinned or "工匠" in pinned):
        missing.append("workshop_worker_duty")
    if "agent-admit" not in pinned:
        missing.append("agent_admit")
    if not (
        ("共享史馆" in pinned or "shared Shiguan" in pinned)
        and ".agents" in pinned
        and ("当前工具" in pinned or "current tool" in pinned.lower())
    ):
        missing.append("shared_shiguan_current_tool")
    if not (
        ("结诏" in pinned or "closeout" in pinned.lower())
        and ("门下复核" in pinned or "archive_checkpoint.py" in pinned)
    ):
        missing.append("closeout")

    require(
        not missing,
        "pinned initial semantic block is missing: " + ", ".join(missing),
    )


def check_pinned_capability_registry_contract() -> None:
    lines = SKILL_PATH.read_text(encoding="utf-8").splitlines()
    try:
        overview_index = next(
            index for index, line in enumerate(lines) if line.strip() == "## Overview"
        )
    except StopIteration as exc:
        raise AssertionError("SKILL.md has no bounded Overview marker") from exc

    pinned = "\n".join(lines[:overview_index])
    pinned_folded = pinned.casefold()
    missing: list[str] = []
    if not (
        "references/court-capability-registry.md" in pinned_folded
        and ("registry-first" in pinned_folded or "index-first" in pinned_folded)
    ):
        missing.append("existing_registry_index_first")
    if not ("current-tool" in pinned_folded or "当前工具" in pinned):
        missing.append("current_tool_compatibility")
    if not (
        ("libu-hr" in pinned_folded or "吏部" in pinned)
        and ("owner" in pinned_folded or "负责" in pinned or "维护" in pinned)
    ):
        missing.append("libu_hr_registry_owner")

    require(
        not missing,
        "pinned capability roster contract missing before Overview: "
        + ", ".join(missing),
    )


def check_governing_capability_registry_contract() -> None:
    problems: list[str] = []
    for path in (
        CAPABILITY_REGISTRY_PATH,
        CAPABILITY_INDEX_GATE_PATH,
        REFRESH_CAPABILITY_REGISTRY_PATH,
    ):
        if not path.is_file():
            problems.append(f"surface_missing:{path.relative_to(ROOT).as_posix()}")
    if problems:
        raise AssertionError("capability roster surfaces missing: " + ", ".join(problems))

    registry_text = CAPABILITY_REGISTRY_PATH.read_text(encoding="utf-8")
    registry_folded = registry_text.casefold()
    index_gate_source = CAPABILITY_INDEX_GATE_PATH.read_text(encoding="utf-8")
    refresh_source = REFRESH_CAPABILITY_REGISTRY_PATH.read_text(encoding="utf-8")

    if "index-first" not in registry_folded:
        problems.append("governing_registry_index_first_missing")
    if not ("current-tool" in registry_folded or "当前工具" in registry_text):
        problems.append("governing_registry_current_tool_compatibility_missing")
    if not ("吏部" in registry_text and "maintain" in registry_folded):
        problems.append("governing_registry_libu_hr_owner_missing")
    for heading in ("light refresh", "incremental update", "full refresh"):
        if heading not in registry_folded:
            problems.append(f"refresh_boundary_missing:{heading.replace(' ', '_')}")
    if not all(
        term in registry_folded
        for term in ("missing", "stale", "corrupt")
    ):
        problems.append("bounded_fallback_missing_missing_stale_corrupt")
    if not (
        "no_sufficient_match" in registry_folded
        or "no sufficient match" in registry_folded
        or "no suitable match" in registry_folded
    ):
        problems.append("bounded_fallback_missing_no_sufficient_match")

    event_terms = {
        "skill_install": ("install", "安装"),
        "skill_upgrade": ("upgrade", "升级"),
        "hash_drift": ("hash drift", "hash/version", "哈希"),
        "version_drift": ("version drift", "hash/version", "版本漂移"),
        "dispatch_failure": ("dispatch failure", "failed dispatch", "dispatch 失败"),
        "phase_closeout": ("phase close", "phase closeout", "阶段结项"),
    }
    for event, aliases in event_terms.items():
        if not any(alias.casefold() in registry_folded for alias in aliases):
            problems.append(f"governing_registry_event_missing:{event}")

    if not all(
        term in registry_folded
        for term in ("read-only", "authority_blocked", "staleness warning")
    ):
        problems.append("read_only_write_block_with_staleness_warning_missing")

    if "installed-capabilities-manifest.json" not in index_gate_source:
        problems.append("index_gate_installed_manifest_surface_missing")
    if "installed-capabilities-catalog.md" not in index_gate_source:
        problems.append("index_gate_installed_catalog_surface_missing")
    if "select_candidates" not in index_gate_source:
        problems.append("index_gate_bounded_selector_surface_missing")
    if "installed-capabilities-manifest.json" not in refresh_source:
        problems.append("refresh_installed_manifest_surface_missing")
    if "installed-capabilities-catalog.md" not in refresh_source:
        problems.append("refresh_installed_catalog_surface_missing")
    if "--daemon" in refresh_source or re.search(
        r"(?m)^\s*while\s+true\s*:", refresh_source, re.I
    ):
        problems.append("unbounded_registry_daemon_present")

    require(
        not problems,
        "governing capability roster drift: " + ", ".join(problems),
    )


def check_registry_first_routing_behavior() -> None:
    route = getattr(check_capability_index_gate, "route_registry_first", None)
    require(
        callable(route),
        "check_capability_index_gate.route_registry_first callable missing; expected "
        "pure signature (query, current_tool, manifest, manifest_state, "
        "source_roots, bounded_discovery)",
    )

    required_parameters = {
        "query",
        "current_tool",
        "manifest",
        "manifest_state",
        "source_roots",
        "bounded_discovery",
    }
    parameters = set(inspect.signature(route).parameters)
    missing_parameters = sorted(required_parameters - parameters)
    require(
        not missing_parameters,
        "route_registry_first signature missing parameters: "
        + ", ".join(missing_parameters),
    )

    def snapshot(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): sha256_file(path)
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def selected_candidate(result: dict[str, object]) -> dict[str, object] | None:
        selected = result.get("selected_candidate")
        return selected if isinstance(selected, dict) else None

    def assert_common_result(
        result: object,
        *,
        manifest: Path,
        case: str,
    ) -> dict[str, object]:
        require(isinstance(result, dict), f"{case}: route result is not a mapping")
        typed = result
        problems: list[str] = []
        if typed.get("owner") != "libu-hr":
            problems.append(f"owner={typed.get('owner') or 'missing'}")
        if typed.get("registry_path") != str(manifest):
            problems.append("registry_path_not_injected_manifest")
        if typed.get("second_registry") is not False:
            problems.append("second_registry_not_explicitly_false")
        if typed.get("daemon") is not False:
            problems.append("daemon_not_explicitly_false")
        require(not problems, f"{case}: route ownership drift: " + ", ".join(problems))
        return typed

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        skill_root = root / "codex-skills"
        skill_path = skill_root / "fixture-registry-skill" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text(
            "---\nname: fixture-registry-skill\n"
            "description: Verified registry-first fixture.\n---\n",
            encoding="utf-8",
        )
        digest = sha256_file(skill_path)
        manifest = root / "installed-capabilities-manifest.json"
        base_record: dict[str, object] = {
            "kind": "skill",
            "source": "codex_skills",
            "name": "fixture-registry-skill",
            "description": "Verified registry-first fixture.",
            "path": "fixture-registry-skill/SKILL.md",
            "relative_path": "fixture-registry-skill/SKILL.md",
            "court_units": ["Libu-HR"],
            "primary_fit": ["Libu-HR"],
            "secondary_fit": [],
            "requires_review": False,
            "enabled": True,
            "dispatchable": True,
            "verified": True,
            "evidence": ["fixture_sha256_verified"],
            "content_hash": digest,
            "immutable_ref": f"sha256:{digest}",
            "version": "fixture-v1",
            "compatible_tools": ["codex"],
        }

        def write_manifest(record: dict[str, object]) -> None:
            manifest.write_text(
                json.dumps({"capabilities": [record]}, sort_keys=True),
                encoding="utf-8",
            )

        discovery_calls: list[dict[str, object]] = []

        def bounded_discovery_spy(*args: object, **kwargs: object) -> list[object]:
            discovery_calls.append({"args": args, "kwargs": kwargs})
            return []

        source_roots = {"codex_skills": (skill_root,)}
        write_manifest(base_record)
        before = snapshot(root)
        valid = assert_common_result(
            route(
                query="fixture registry skill",
                current_tool="codex",
                manifest=manifest,
                manifest_state="current",
                source_roots=source_roots,
                bounded_discovery=bounded_discovery_spy,
            ),
            manifest=manifest,
            case="valid_codex_match",
        )
        require(
            len(discovery_calls) == 0,
            "valid_codex_match: bounded discovery callback ran for sufficient match",
        )
        require(
            valid.get("selection_source") == "registry",
            "valid_codex_match: registry was not the selection source",
        )
        candidate = selected_candidate(valid)
        require(candidate is not None, "valid_codex_match: selected candidate missing")
        require(
            candidate.get("name") == "fixture-registry-skill"
            and candidate.get("dispatchable") is True,
            "valid_codex_match: verified compatible registry candidate not selected",
        )
        require(
            snapshot(root) == before,
            "valid_codex_match: pure route wrote a second registry or other file",
        )

        incompatible = dict(base_record, compatible_tools=["claude"])
        write_manifest(incompatible)
        discovery_calls.clear()
        before = snapshot(root)
        incompatible_result = assert_common_result(
            route(
                query="fixture registry skill",
                current_tool="codex",
                manifest=manifest,
                manifest_state="current",
                source_roots=source_roots,
                bounded_discovery=bounded_discovery_spy,
            ),
            manifest=manifest,
            case="incompatible_tool",
        )
        require(
            selected_candidate(incompatible_result) is None
            and incompatible_result.get("dispatchable") is False,
            "incompatible_tool: Claude-only capability became Codex-dispatchable",
        )
        require(
            incompatible_result.get("fallback_reason") == "no_sufficient_match",
            "incompatible_tool: fallback reason is not no_sufficient_match",
        )
        require(
            len(discovery_calls) == 1,
            f"incompatible_tool: expected one bounded fallback, got {len(discovery_calls)}",
        )
        require(
            snapshot(root) == before,
            "incompatible_tool: pure route wrote a second registry or other file",
        )

        state_cases = {
            "missing": root / "missing-manifest.json",
            "stale": manifest,
            "corrupt": manifest,
        }
        for state, state_manifest in state_cases.items():
            if state == "stale":
                write_manifest(base_record)
            elif state == "corrupt":
                manifest.write_text("{", encoding="utf-8")
            discovery_calls.clear()
            before = snapshot(root)
            result = assert_common_result(
                route(
                    query="fixture registry skill",
                    current_tool="codex",
                    manifest=state_manifest,
                    manifest_state=state,
                    source_roots=source_roots,
                    bounded_discovery=bounded_discovery_spy,
                ),
                manifest=state_manifest,
                case=state,
            )
            require(
                result.get("fallback_reason") == state,
                f"{state}: fallback reason mismatch",
            )
            require(
                len(discovery_calls) == 1,
                f"{state}: expected one bounded fallback, got {len(discovery_calls)}",
            )
            require(
                snapshot(root) == before,
                f"{state}: pure route wrote a second registry or other file",
            )


def check_fourteen_office_dossier_profile_bindings() -> None:
    identities = court_office_bootstrap.OFFICE_ASSIGNMENT_IDENTITIES
    roles = tuple(identities)
    require(len(roles) == 14, f"expected 14 canonical offices, found {len(roles)}")
    require(tomllib is not None, "tomllib is required for standing profile checks")

    problems: list[str] = []
    for role in roles:
        profile_path = PROFILE_ROOT / f"{role}.toml"
        dossier_path = DOSSIER_ROOT / role / "AGENTS.md"
        if not profile_path.is_file():
            problems.append(f"{role}:profile_missing")
            continue
        if not dossier_path.is_file():
            problems.append(f"{role}:dossier_missing")
            continue

        document = tomllib.loads(profile_path.read_text(encoding="utf-8"))
        profile = document.get("profile")
        if not isinstance(profile, dict):
            problems.append(f"{role}:profile_table_missing")
            continue
        _, _, _, office_zh, direct_superior = identities[role]
        if profile.get("role_key") != role:
            problems.append(f"{role}:profile_role_mismatch")
        if profile.get("office_zh") != office_zh:
            problems.append(f"{role}:profile_office_zh_mismatch")
        if profile.get("direct_superior") != direct_superior:
            problems.append(f"{role}:profile_superior_mismatch")

        dossier = dossier_path.read_text(encoding="utf-8")
        if not re.search(rf"(?m)^- role: {re.escape(role)}\s*$", dossier):
            problems.append(f"{role}:dossier_role_mismatch")
        if not re.search(rf"(?m)^- office_zh: {re.escape(office_zh)}\s*$", dossier):
            problems.append(f"{role}:dossier_office_zh_mismatch")
        if not re.search(
            rf"(?m)^- direct_superior: {re.escape(direct_superior)}\s*$",
            dossier,
        ):
            problems.append(f"{role}:dossier_superior_mismatch")
        relative_profile = f"agents/standing-officials/{role}.toml"
        if not re.search(
            rf"(?m)^- profile_source: {re.escape(relative_profile)}\s*$",
            dossier,
        ):
            problems.append(f"{role}:dossier_profile_source_not_exact")
        expected_duty = str(profile.get("duty") or "").strip()
        if role == "patrol-inspector":
            expected_duty = expected_duty.split(" for superCC evidence;", 1)[0] + "."
        if not expected_duty or expected_duty not in dossier:
            problems.append(f"{role}:dossier_mandate_not_from_profile")
        normalized_dossier = " ".join(dossier.split())
        if role == "patrol-inspector":
            patrol_subset = (
                "Review bounded status evidence",
                "Do not repair directly",
                "Cite bounded status evidence",
            )
            if any(item not in normalized_dossier for item in patrol_subset):
                problems.append(f"{role}:ordinary_diagnostic_subset_missing")
        else:
            for field in ("can_do", "cannot_do", "evidence_contract"):
                expected = " ".join(str(profile.get(field) or "").split())
                if not expected or expected not in normalized_dossier:
                    problems.append(f"{role}:dossier_{field}_not_from_profile")
        for heading in ("Duty", "Allowed", "Forbidden", "Evidence", "Stop Conditions"):
            if f"## {heading}" not in dossier:
                problems.append(f"{role}:dossier_{heading.lower().replace(' ', '_')}_missing")
        if "carrier_scope: child_agent | worktree_thread" not in dossier:
            problems.append(f"{role}:ordinary_carrier_scope_missing")
        if re.search(r"(?mi)^- (?:profile|court_skill)_hash:\s*[0-9a-f]{64}\s*$", dossier):
            problems.append(f"{role}:volatile_hash_embedded")
        if "supercc" in dossier.lower():
            problems.append(f"{role}:supercc_semantics_leaked")
        if "governing_skill: decretum-matrix" not in dossier:
            problems.append(f"{role}:decretum_matrix_binding_missing")
        if "court-capability-router" not in dossier:
            problems.append(f"{role}:technical_locator_missing")

    require(not problems, "all-office binding drift: " + ", ".join(problems))


def check_ordinary_child_agent_manifest() -> None:
    manifest = court_office_bootstrap.build_preload_manifest(
        "gongbu",
        carrier_kind="child_agent",
    )
    require(
        manifest.profile_source == "agents/standing-officials/gongbu.toml",
        f"ordinary child profile locator is not repository-relative: {manifest.profile_source}",
    )
    require(
        manifest.dossier_path == "agents/office-dossiers/gongbu/AGENTS.md",
        f"ordinary child selected the wrong dossier: {manifest.dossier_path}",
    )
    require(
        manifest.court_skill_path == "SKILL.md",
        f"ordinary child skill locator is not repository-relative: {manifest.court_skill_path}",
    )


def check_ordinary_worktree_spawn_contract() -> None:
    contract = court_office_bootstrap.build_spawn_contract(
        "gongbu",
        carrier_kind="worktree_thread",
        assignment="implement one bounded worktree change",
        task_focus="ordinary worktree carrier contract",
        complexity="medium",
        risk="low",
        ambiguity="low",
        transport="codex",
        allowed_actions=["read", "edit owned files", "verify"],
        forbidden_actions=["cross repository ownership", "external publish"],
        evidence_contract="return changed paths and scoped verification",
        stop_conditions=["write-set overlap", "authority drift"],
    )
    require(contract.get("carrier_kind") == "worktree_thread", "worktree carrier was not persisted")
    require(
        contract.get("dossier_path") == "agents/office-dossiers/gongbu/AGENTS.md",
        f"worktree carrier selected the wrong dossier: {contract.get('dossier_path')}",
    )


def check_disabled_supercc_fails_before_path_resolution() -> None:
    class ExplodingRoot:
        def __fspath__(self) -> str:
            raise AssertionError("disabled superCC touched a filesystem root")

    require(
        court_office_bootstrap.SUPERCC_CLI_CARRIER == "supercc_cli_office",
        f"non-canonical superCC carrier enum: {court_office_bootstrap.SUPERCC_CLI_CARRIER}",
    )
    try:
        court_office_bootstrap.build_preload_manifest(
            "gongbu",
            carrier_kind="supercc_cli_office",
            supercc_enabled=False,
            skill_root=ExplodingRoot(),  # type: ignore[arg-type]
        )
    except ValueError as exc:
        require(
            str(exc) == "supercc_experimental_cli_explicit_enable_required",
            f"disabled superCC returned an ambiguous gate: {exc}",
        )
    else:
        raise AssertionError("disabled superCC preload was accepted")


def check_legacy_supercc_carrier_rejected() -> None:
    class ExplodingRoot:
        def __fspath__(self) -> str:
            raise AssertionError("legacy superCC carrier touched a filesystem root")

    try:
        court_office_bootstrap.build_preload_manifest(
            "gongbu",
            carrier_kind="supercc_cli",
            supercc_enabled=True,
            skill_root=ExplodingRoot(),  # type: ignore[arg-type]
        )
    except ValueError as exc:
        require(
            str(exc) == "unsupported office carrier: supercc_cli",
            f"legacy superCC carrier was aliased or ambiguously rejected: {exc}",
        )
    else:
        raise AssertionError("legacy superCC carrier enum was accepted")


def check_missing_ordinary_dossier_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        profile = root / "agents" / "standing-officials" / "gongbu.toml"
        profile.parent.mkdir(parents=True)
        profile.write_text(
            "[profile]\n"
            'role_key = "gongbu"\n'
            'office_zh = "工部"\n'
            'direct_superior = "shangshu"\n',
            encoding="utf-8",
        )
        (root / "SKILL.md").write_text("# fixture skill\n", encoding="utf-8")
        try:
            court_office_bootstrap.build_preload_manifest(
                "gongbu",
                carrier_kind="child_agent",
                skill_root=root,
            )
        except ValueError as exc:
            require(
                str(exc) == "ordinary_office_dossier_missing",
                f"missing ordinary dossier did not fail closed explicitly: {exc}",
            )
        else:
            raise AssertionError("missing ordinary dossier was accepted")


def check_fourteen_office_manifest_hashes() -> None:
    identities = court_office_bootstrap.OFFICE_ASSIGNMENT_IDENTITIES
    problems: list[str] = []
    for role, identity in identities.items():
        for carrier_kind in ("child_agent", "worktree_thread"):
            manifest = court_office_bootstrap.build_preload_manifest(
                role,
                carrier_kind=carrier_kind,
            )
            if manifest.carrier_kind != carrier_kind:
                problems.append(f"{role}:{carrier_kind}:manifest_carrier_mismatch")
            _check_manifest_hashes(role, identity, manifest, problems)

    require(not problems, "manifest binding drift: " + ", ".join(problems))


def _check_manifest_hashes(
    role: str,
    identity: tuple[str, str, str, str, str],
    manifest: court_office_bootstrap.OfficePreloadManifest,
    problems: list[str],
) -> None:
    _, _, _, office_zh, direct_superior = identity
    if manifest.role_key != role:
        problems.append(f"{role}:manifest_role_mismatch")
    if manifest.office_zh != office_zh:
        problems.append(f"{role}:manifest_office_zh_mismatch")
    if manifest.direct_superior != direct_superior:
        problems.append(f"{role}:manifest_superior_mismatch")

    profile_path = resolve_manifest_path(manifest.profile_source)
    dossier_path = resolve_manifest_path(manifest.dossier_path)
    skill_path = resolve_manifest_path(manifest.court_skill_path)
    if profile_path != (PROFILE_ROOT / f"{role}.toml").resolve():
        problems.append(f"{role}:manifest_profile_path_wrong")
    if dossier_path != (DOSSIER_ROOT / role / "AGENTS.md").resolve():
        problems.append(f"{role}:manifest_dossier_path_wrong")
    if skill_path != SKILL_PATH.resolve():
        problems.append(f"{role}:manifest_skill_path_wrong")
    if manifest.profile_hash != sha256_file(profile_path):
        problems.append(f"{role}:manifest_profile_hash_wrong")
    if manifest.dossier_hash != sha256_file(dossier_path):
        problems.append(f"{role}:manifest_dossier_hash_wrong")
    if manifest.court_skill_hash != sha256_file(skill_path):
        problems.append(f"{role}:manifest_skill_hash_wrong")
    if manifest.court_skill_name != "decretum-matrix":
        problems.append(f"{role}:manifest_skill_name_wrong")


def check_relative_persisted_preload_paths() -> None:
    identities = court_office_bootstrap.OFFICE_ASSIGNMENT_IDENTITIES
    skills = skill_requirement_fixture()
    problems: list[str] = []
    for role, identity in identities.items():
        _, task_prefix, agent_prefix, _, _ = identity
        manifest = court_office_bootstrap.build_preload_manifest(role)
        expected = {
            "profile_source": f"agents/standing-officials/{role}.toml",
            "dossier_path": f"agents/office-dossiers/{role}/AGENTS.md",
            "court_skill_path": "SKILL.md",
        }
        for field, expected_text in expected.items():
            value = getattr(manifest, field)
            try:
                actual_text = normalized_relative_text(value)
            except AssertionError as exc:
                problems.append(f"{role}:{field}:{exc}")
            else:
                if actual_text != expected_text:
                    problems.append(
                        f"{role}:{field}:expected={expected_text}:actual={actual_text}"
                    )

        binding = court_office_bootstrap.build_office_assignment_binding(
            role_key=role,
            collaboration_task_name=f"{task_prefix}_preload_semantics",
            court_agent_id=f"{agent_prefix}-preload-semantics",
            requires_gongjiang=False,
            skill_requirements=skills,
        )
        try:
            binding_profile = normalized_relative_text(binding.get("profile_source"))
        except AssertionError as exc:
            problems.append(f"{role}:binding_profile_source:{exc}")
        else:
            expected_profile = f"agents/standing-officials/{role}.toml"
            if binding_profile != expected_profile:
                problems.append(
                    f"{role}:binding_profile_source:expected={expected_profile}:actual={binding_profile}"
                )

    require(not problems, "absolute persisted preload paths: " + "; ".join(problems))


def check_preload_ack_rejections() -> None:
    manifest = court_office_bootstrap.build_preload_manifest("libu")
    other = court_office_bootstrap.build_preload_manifest("gongbu")
    valid = {
        "schema": manifest.preload_ack_schema,
        "preload_status": "PASSED",
        "role_key": manifest.role_key,
        "office_zh": manifest.office_zh,
        "direct_superior": manifest.direct_superior,
        "profile_hash": manifest.profile_hash,
        "dossier_hash": manifest.dossier_hash,
        "court_skill_hash": manifest.court_skill_hash,
        "agent_dossier_loaded": "YES",
        "loaded_skills": ["decretum-matrix"],
    }
    accepted = court_office_bootstrap.validate_preload_ack(manifest, valid)
    require(accepted["preload_status"] == "PASSED", "valid exact dossier ack failed")

    invalid_cases = {
        "wrong_role": {**valid, "role_key": "gongbu"},
        "wrong_profile_hash": {**valid, "profile_hash": "0" * 64},
        "wrong_role_dossier": {**valid, "dossier_hash": other.dossier_hash},
        "wrong_skill_hash": {**valid, "court_skill_hash": "f" * 64},
        "prompt_only_identity": {
            **valid,
            "agent_dossier_loaded": "NO",
            "loaded_skills": [],
        },
    }
    accepted_invalid: list[str] = []
    for name, ack in invalid_cases.items():
        try:
            court_office_bootstrap.validate_preload_ack(manifest, ack)
        except ValueError:
            continue
        accepted_invalid.append(name)

    try:
        court_office_bootstrap.build_preload_manifest("/root/libu")
    except ValueError:
        pass
    else:
        accepted_invalid.append("prompt_task_path_as_role")

    require(
        not accepted_invalid,
        "invalid or prompt-only office identity accepted: " + ", ".join(accepted_invalid),
    )


def spawn_contract(role: str, assignment: str) -> dict[str, object]:
    return court_office_bootstrap.build_spawn_contract(
        role,
        assignment=assignment,
        task_focus="bounded A02 office responsibility fixture",
        complexity="medium",
        risk="medium",
        ambiguity="low",
        transport="codex",
        allowed_actions=["read", "implement bounded assignment", "report evidence"],
        forbidden_actions=["cross office authority", "unbounded mutation"],
        evidence_contract="return exact file and behavioral evidence",
        stop_conditions=["scope overlap", "authority drift"],
    )


def check_ministries_cannot_absorb_three_department_or_taizi_duties() -> None:
    valid = spawn_contract("gongbu", "implement an isolated code module and its tests")
    require(valid["role_key"] == "gongbu", "valid Gongbu assignment was not preserved")

    forbidden_assignments = (
        "承担三省审计、门下最终复核并代太子统筹全局",
        "perform Three Departments audit and act as Taizi global coordinator",
    )
    accepted: list[str] = []
    for role in MINISTRY_ROLES:
        for assignment in forbidden_assignments:
            try:
                spawn_contract(role, assignment)
            except (ValueError, PermissionError):
                continue
            accepted.append(f"{role}:{assignment}")
    require(
        not accepted,
        "ministry responsibility drift was accepted: " + " | ".join(accepted),
    )


def check_strict_ministry_worker_dispatch_hierarchy() -> None:
    problems: list[str] = []
    forbidden_upper_dispatchers = {"taizi", "zhongshu", "menxia"}

    for role in MINISTRY_ROLES:
        manifest = court_office_bootstrap.build_preload_manifest(role)
        if manifest.direct_superior != "shangshu":
            problems.append(
                f"ministry:{role}:direct_superior={manifest.direct_superior}:expected=shangshu"
            )
        if manifest.direct_superior in forbidden_upper_dispatchers:
            problems.append(f"ministry:{role}:upper_office_bypass={manifest.direct_superior}")

    gongjiang = court_office_bootstrap.build_office_assignment_binding(
        role_key="gongbu",
        collaboration_task_name="gongbu_gongjiang_hierarchy_red",
        court_agent_id="gongbu-gongjiang-hierarchy-red",
        requires_gongjiang=True,
        skill_requirements=skill_requirement_fixture(),
    )
    if gongjiang.get("official_name_head") != "GongBu-GongJiang":
        problems.append("gongbu_worker:official_name_head_not_gongbu_gongjiang")

    worker_superior = str(gongjiang.get("direct_superior") or "")
    if worker_superior != "gongbu":
        problems.append(
            f"GongBu-GongJiang:direct_superior={worker_superior}:expected=gongbu"
        )
    if worker_superior in forbidden_upper_dispatchers | {"shangshu"}:
        problems.append(
            f"GongBu-GongJiang:owning_ministry_bypassed_by={worker_superior}"
        )

    require(
        not problems,
        "strict dispatch hierarchy drift: " + ", ".join(problems),
    )


def formal_gate_fixture() -> dict[str, object]:
    return {
        "schema": "court.conversation_gate.v1",
        "active_decree": False,
        "active_decree_state": "NONE",
        "message_class": "FORMAL_TASK",
        "confidence": "HIGH",
        "relation_to_active_decree": "NONE",
        "taskization_consent": "EXPLICIT",
        "requires_tools": True,
        "mutates_state": True,
        "risk_present": False,
        "next_route": "THREE_DEPARTMENTS",
        "question": "",
        "rationale": "A02 preload and recovery RED fixture",
        "understanding": minimal_request_understanding_example(),
    }


def continuation_gate_fixture(task_id: str) -> dict[str, object]:
    return {
        "schema": "court.conversation_gate.v1",
        "active_decree": True,
        "active_decree_state": "PAUSED",
        "message_class": "TASK_CONTINUATION",
        "confidence": "HIGH",
        "relation_to_active_decree": "CONTINUES",
        "taskization_consent": "NOT_REQUIRED",
        "requires_tools": True,
        "mutates_state": True,
        "risk_present": False,
        "next_route": "THREE_DEPARTMENTS",
        "question": "",
        "rationale": "continue the existing A02 task through Three Departments",
        "target_task_id": task_id,
    }


def correction_gate_fixture(task_id: str) -> dict[str, object]:
    return {
        "schema": "court.conversation_gate.v1",
        "active_decree": True,
        "active_decree_state": "ACTIVE",
        "message_class": "TASK_CORRECTION",
        "confidence": "HIGH",
        "relation_to_active_decree": "CORRECTS",
        "taskization_consent": "NOT_REQUIRED",
        "requires_tools": True,
        "mutates_state": True,
        "risk_present": False,
        "next_route": "THREE_DEPARTMENTS",
        "question": "",
        "rationale": "correct the existing A02 task and re-enter Three Departments",
        "target_task_id": task_id,
    }


def create_args(task_id: str, charter: str) -> Namespace:
    return Namespace(
        title=task_id,
        charter=charter,
        task_id=task_id,
        owner="taizi",
        report_tier="brief",
        evidence=f"create {task_id}",
        note="A02 preload semantics RED fixture",
        work_kind="implementation",
        intake_gate=formal_gate_fixture(),
        intake_file=None,
    )


def check_new_task_initializes_charter_binding() -> None:
    charter = "A02 initial charter revision fixture"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            created = court_runtime.create_task(create_args("a02-charter-init", charter))
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    task = created.task
    require(task.get("charter_revision") == 1, "new task charter_revision is not 1")
    require(
        task.get("charter_sha256") == sha256_text(charter),
        "new task charter_sha256 is absent or not bound to the charter bytes",
    )
    require(task.get("charter_revision_history") == [], "new task revision history is not empty")


def runtime_task_fixture(
    task_id: str,
    *,
    state: str,
    charter: str,
    charter_revision: int,
    paused_from: str | None = None,
) -> dict[str, object]:
    charter_sha256 = sha256_text(charter)
    semantic_binding = court_runtime.semantic_binding_for_revision(
        charter,
        charter_revision,
        {
            "schema": "court.semantic.invariant_capsule.v1",
            "latest_decree_anchor": charter,
            "latest_decree_sha256": charter_sha256,
            "non_goals": ["do not touch real runtime state"],
            "boundaries": ["TemporaryDirectory fixture only"],
            "allowed_actions": ["synthetic recovery check"],
            "forbidden_actions": ["real Shiguan access"],
            "acceptance": ["preload semantic checker reaches expected gate"],
            "evidence_requirements": ["machine-readable result"],
            "stop_gates": ["semantic drift"],
            "write_set": ["scripts/check_court_preload_semantics.py"],
            "governing_hashes": {"fixture": charter_sha256},
            "charter_sha256": charter_sha256,
        },
    )
    task: dict[str, object] = {
        "runtime_schema_version": court_runtime.RUNTIME_SCHEMA_VERSION,
        "task_id": task_id,
        "title": task_id,
        "charter": charter,
        **semantic_binding,
        "charter_revision_history": [],
        "state": state,
        "owner": "shangshu",
        "report_tier": "brief",
        "read_only": False,
        "work_kind": "implementation",
        "conversation_gate": continuation_gate_fixture(task_id),
        "created_at": "2026-07-14T00:00:00+00:00",
        "updated_at": "2026-07-14T00:00:00+00:00",
        "heartbeat": "paused" if state == "Paused" else "alive",
        "last_evidence": "A02 recovery fixture",
        "agent_runtime": court_runtime.default_agent_runtime(),
        "outcome_assessment": {
            "schema": "court.outcome_assessment.v1",
            "gate": "PASSED",
            "reasons": [],
            "outcome": {"status": "STALE_DERIVED_RESULT"},
        },
        "assessment_binding": {"status": "VERIFIED", "gate": "PASSED"},
        "shiguan_checkpoint": {"status": "VERIFIED"},
        "completion": {"status": "READY"},
        "dispatch_plan": {"status": "ACTIVE", "next_state": "SixMinistries"},
        "agents": {
            "gongbu-worker-1": {
                "role": "gongbu",
                "status": "running",
                "preload_status": "PASSED",
            }
        },
        "stop_condition": "",
        "unsafe_remaining": "",
        "evidence_preserved": "",
    }
    if paused_from is not None:
        task["paused_from"] = paused_from
    return task


def derived_state_problems(task: dict[str, object]) -> list[str]:
    problems: list[str] = []
    assessment = task.get("outcome_assessment")
    if not isinstance(assessment, dict) or assessment.get("gate") != "UNASSESSED":
        problems.append("outcome_assessment_not_invalidated")
    if task.get("assessment_binding") not in ({}, None):
        problems.append("assessment_binding_not_invalidated")
    if task.get("shiguan_checkpoint") not in ({}, None):
        problems.append("shiguan_checkpoint_not_invalidated")
    completion = task.get("completion")
    completion_status = completion.get("status") if isinstance(completion, dict) else None
    if not str(completion_status or "").startswith("INVALIDATED"):
        problems.append("completion_not_invalidated")

    dispatch_plan = task.get("dispatch_plan")
    if isinstance(dispatch_plan, dict) and dispatch_plan:
        if not str(dispatch_plan.get("status") or "").startswith("INVALIDATED"):
            problems.append("dispatch_plan_not_invalidated")

    agents = task.get("agents")
    if isinstance(agents, dict):
        for agent_id, raw in agents.items():
            if not isinstance(raw, dict):
                continue
            status = str(raw.get("status") or "").lower()
            final_status = str(raw.get("final_status") or "").lower()
            explicitly_invalidated = bool(
                raw.get("assignment_invalidated_by_charter_revision")
                or str(raw.get("assignment_status") or "").startswith("INVALIDATED")
                or str(raw.get("release_status") or "").lower() == "closed"
            )
            if (
                status in ACTIVE_DERIVED_STATUSES
                or final_status in ACTIVE_DERIVED_STATUSES
            ) and not explicitly_invalidated:
                problems.append(f"active_agent_not_invalidated:{agent_id}")
    return problems


def check_correction_reenters_three_departments() -> None:
    task_id = "a02-correction-same-task"
    old_charter = "old charter"
    new_charter = "corrected charter"
    new_capsule = runtime_task_fixture(
        "a02-correction-new-capsule",
        state="ThreeDepartments",
        charter=new_charter,
        charter_revision=2,
    )["invariant_capsule"]
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.write_tasks(
                {
                    task_id: runtime_task_fixture(
                        task_id,
                        state="SixMinistries",
                        charter=old_charter,
                        charter_revision=1,
                    )
                }
            )
            result = court_runtime.revise_charter_task(
                Namespace(
                    task_id=task_id,
                    correction_gate=correction_gate_fixture(task_id),
                    correction_file=None,
                    expected_revision=1,
                    expected_sha256=sha256_text(old_charter),
                    new_revision=2,
                    new_sha256=sha256_text(new_charter),
                    new_charter=new_charter,
                    new_charter_file=None,
                    new_invariant_capsule=new_capsule,
                    new_invariant_capsule_file=None,
                    actor="taizi",
                    evidence="A02 correction fixture",
                    note="correct existing task and re-enter Three Departments",
                )
            )
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    task = result.task
    problems: list[str] = []
    if task.get("task_id") != task_id:
        problems.append("correction_created_second_task")
    if task.get("charter_revision") != 2:
        problems.append("correction_revision_not_incremented")
    if task.get("charter_sha256") != sha256_text(new_charter):
        problems.append("correction_charter_hash_not_updated")
    if task.get("state") != "ThreeDepartments":
        problems.append(f"correction_state={task.get('state')}")
    problems.extend(derived_state_problems(task))
    require(not problems, "correction recovery drift: " + ", ".join(problems))


def semantic_context_fixture() -> dict[str, object]:
    return {
        "authority_revision": 1,
        "authority_sha256": sha256_text("preload-authority"),
        "plan_revision": 1,
        "plan_sha256": sha256_text("preload-plan"),
        "plan_cursor": "preload-resume",
        "git_fingerprint": "preload-fixture-head",
        "recovery_checkpoint_id": "preload-fixture-recovery",
        "shiguan_revision": 0,
        "shiguan_fingerprint": sha256_text("preload-synthetic-shiguan"),
    }


def make_fixture_dispatchable(task_id: str) -> dict[str, object]:
    context = semantic_context_fixture()
    common = dict(
        task_id=task_id,
        semantic_context=context,
        semantic_context_file=None,
        actor="taizi",
        evidence="preload resume semantic fixture",
        note="preload resume semantic fixture",
    )
    court_runtime.semantic_checkpoint_task(
        Namespace(**common, trigger="checkpoint")
    )
    return court_runtime.semantic_verify_task(
        Namespace(**common, trigger="verify")
    ).task


def resume_args(task: dict[str, object], *, to_state: str) -> Namespace:
    receipt = task["semantic_receipt"]
    return Namespace(
        task_id=task["task_id"],
        to_state=to_state,
        actor="shangshu",
        evidence="A02 same-task continuation fixture",
        note="resume through Three Departments",
        continuation_gate=continuation_gate_fixture(str(task["task_id"])),
        continuation_file=None,
        expected_semantic_epoch=task["semantic_epoch"],
        expected_charter_sha256=task["charter_sha256"],
        expected_invariant_capsule_sha256=task["invariant_capsule_sha256"],
        expected_checkpoint_id=receipt["checkpoint_id"],
        semantic_context=semantic_context_fixture(),
        semantic_context_file=None,
        trigger="resume",
    )


def check_resume_cannot_jump_directly_to_six_ministries() -> None:
    task_id = "a02-resume-no-direct-six"
    charter = "paused charter"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.write_tasks(
                {
                    task_id: runtime_task_fixture(
                        task_id,
                        state="Paused",
                        charter=charter,
                        charter_revision=1,
                        paused_from="ShangshuDispatch",
                    )
                }
            )
            task = make_fixture_dispatchable(task_id)
            try:
                result = court_runtime.semantic_resume_task(
                    resume_args(task, to_state="SixMinistries")
                )
            except ValueError:
                return
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    require(
        result.task.get("state") == "ThreeDepartments",
        "paused task resumed directly to SixMinistries",
    )


def check_valid_resume_reenters_three_departments_and_invalidates() -> None:
    task_id = "a02-resume-three-departments"
    charter = "paused charter"
    with tempfile.TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            court_runtime.write_tasks(
                {
                    task_id: runtime_task_fixture(
                        task_id,
                        state="Paused",
                        charter=charter,
                        charter_revision=1,
                        paused_from="ShangshuDispatch",
                    )
                }
            )
            task = make_fixture_dispatchable(task_id)
            try:
                result = court_runtime.semantic_resume_task(
                    resume_args(task, to_state="ThreeDepartments")
                )
            except ValueError as exc:
                raise AssertionError(
                    f"same-task ThreeDepartments resume was rejected: {exc}"
                ) from exc
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]

    task = result.task
    problems: list[str] = []
    if task.get("task_id") != task_id:
        problems.append("resume_created_second_task")
    if task.get("state") != "ThreeDepartments":
        problems.append(f"resume_state={task.get('state')}")
    if task.get("charter_revision") != 1:
        problems.append("resume_lost_charter_revision")
    if task.get("charter_sha256") != sha256_text(charter):
        problems.append("resume_lost_charter_hash")
    problems.extend(derived_state_problems(task))
    require(not problems, "resume recovery drift: " + ", ".join(problems))


CHECKS: tuple[tuple[str, Callable[[], None]], ...] = (
    ("ordinary_child_agent_manifest", check_ordinary_child_agent_manifest),
    ("ordinary_worktree_spawn_contract", check_ordinary_worktree_spawn_contract),
    (
        "disabled_supercc_fails_before_path_resolution",
        check_disabled_supercc_fails_before_path_resolution,
    ),
    ("legacy_supercc_carrier_rejected", check_legacy_supercc_carrier_rejected),
    ("missing_ordinary_dossier_fails_closed", check_missing_ordinary_dossier_fails_closed),
    ("pinned_initial_semantics", check_pinned_initial_semantics),
    ("amended_behavior_source_reachability", check_amended_behavior_source_reachability),
    (
        "pinned_capability_registry_contract",
        check_pinned_capability_registry_contract,
    ),
    (
        "governing_capability_registry_contract",
        check_governing_capability_registry_contract,
    ),
    (
        "registry_first_routing_behavior",
        check_registry_first_routing_behavior,
    ),
    ("fourteen_office_dossier_profile_bindings", check_fourteen_office_dossier_profile_bindings),
    ("fourteen_office_manifest_hashes", check_fourteen_office_manifest_hashes),
    ("relative_persisted_preload_paths", check_relative_persisted_preload_paths),
    ("preload_ack_rejections", check_preload_ack_rejections),
    (
        "ministry_responsibility_guard",
        check_ministries_cannot_absorb_three_department_or_taizi_duties,
    ),
    (
        "strict_ministry_worker_dispatch_hierarchy",
        check_strict_ministry_worker_dispatch_hierarchy,
    ),
    ("new_task_charter_binding", check_new_task_initializes_charter_binding),
    ("correction_three_departments", check_correction_reenters_three_departments),
    ("resume_no_direct_six_ministries", check_resume_cannot_jump_directly_to_six_ministries),
    (
        "resume_three_departments_invalidation",
        check_valid_resume_reenters_three_departments_and_invalidates,
    ),
)


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        choices=tuple(name for name, _ in CHECKS),
        help="run one focused contract check",
    )
    args = parser.parse_args()
    selected_checks = tuple(
        (name, check) for name, check in CHECKS if args.case is None or name == args.case
    )
    passed: list[str] = []
    gaps: list[dict[str, str]] = []
    for name, check in selected_checks:
        try:
            check()
        except Exception as exc:  # RED aggregator: report every independent gap.
            gaps.append(
                {
                    "check": name,
                    "error": type(exc).__name__,
                    "detail": str(exc),
                }
            )
        else:
            passed.append(name)

    print(
        json.dumps(
            {
                "schema": "court.a02.preload_semantics_red.v1",
                "status": "RED" if gaps else "PASSED",
                "checks_total": len(selected_checks),
                "checks_passed": passed,
                "gap_count": len(gaps),
                "gaps": gaps,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if gaps:
        print(f"COURT_PRELOAD_SEMANTICS_RED gap_count={len(gaps)}")
        return 1
    print("COURT_PRELOAD_SEMANTICS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
