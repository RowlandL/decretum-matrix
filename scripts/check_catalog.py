"""Check whether the court router catalog and portable court assets are usable."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

from check_capability_index_gate import (
    catalog_path as capability_index_catalog_path,
    manifest_path as capability_index_manifest_path,
)
from shiguan_paths import reference_path, references_root as shared_references_root


REQUIRED_UNITS = [
    "Taizi",
    "Zhongshu",
    "Menxia",
    "Shangshu",
    "Hubu",
    "Libu",
    "Bingbu",
    "Xingbu",
    "Gongbu",
    "Libu-HR",
    "Shiguan",
    "Zaochao",
]

REQUIRED_DIMENSIONS = [
    "身",
    "言",
    "书",
    "判",
    "德行",
    "才用",
    "劳效",
]

REQUIRED_AGENTS = [
    "taizi.toml",
    "zhongshu.toml",
    "menxia.toml",
    "shangshu.toml",
    "libu-hr.toml",
    "hubu.toml",
    "libu.toml",
    "bingbu.toml",
    "xingbu.toml",
    "gongbu.toml",
    "shiguan.toml",
    "shiguan-hermes.toml",
    "zaochao.toml",
    "patrol-inspector.toml",
]

REQUIRED_SKILLS = [
    ("FIND_SKILLS", "find-skills"),
]

REQUIRED_SYSTEM_SKILLS = [
    ("SKILL_CREATOR", "skill-creator"),
]

REQUIRED_SYSTEM_FILES = [
    (
        "SKILL_CREATOR_VALIDATE",
        Path("skill-creator") / "scripts" / "quick_validate.py",
    ),
]

REQUIRED_COURT_SCRIPTS = [
    "archive_checkpoint.py",
    "court_file_lock.py",
    "court_usage_ledger.py",
    "check_court_usage_ledger.py",
    "check_shiguan_concurrency.py",
    "internal_memory_shiguan_bridge.py",
    "query_shiguan_index.py",
    "grow_shiguan_tree.py",
    "build_shiguan_knowledge_graph.py",
    "export_shiguan_obsidian.py",
    "rebuild_shiguan_index.py",
    "ensure_codex_yolo_startup_task.py",
    "ensure_court_agent_config.py",
    "check_court_agent_config.py",
    "court_model_router.py",
    "check_court_model_router.py",
    "court_office_bootstrap.py",
    "check_court_office_bootstrap.py",
    "ensure_portable_court_bootstrap.py",
    "ensure_supercc_court.py",
    "supercc_client_selection.py",
    "check_supercc_client_selection.py",
    "check_supercc_state_concurrency.py",
    "court_platform.py",
    "supercc_squad.py",
    "supercc-squad.sh",
    "supercc-squad.ps1",
    "supercc-squad.cmd",
    "check_supercc_squad_wrapper.py",
    "check_supercc_claude_hard_gates.py",
    "ensure_hermes_supercc.py",
    "ensure_shiguan_web.py",
    "ensure_shiguan_autosync.py",
    "ensure_shiguan_service_daemon.py",
    "ensure_obsidian_shared_vault.py",
    "obsidian_config_state.py",
    "serve_shiguan_tree.py",
    "shiguan_peer_downloads.py",
    "shiguan_peer_state.py",
    "shiguan_web_pending.py",
    "supercc_office_state.py",
    "shiguan_autosync_daemon.py",
    "shiguan_service_daemon.py",
    "register_agent_presence.py",
    "refresh_capability_registry.py",
    "package_skill.py",
    "court_runtime.py",
    "court_cli.py",
    "court_multi_agent_protocol.py",
    "court_codex_protocol_launcher.py",
    "court_codex_office_worker.py",
    "check_court_codex_office_worker.py",
    "court_codex_host_resolution.py",
    "check_court_codex_host_resolution.py",
    "check_court_runtime.py",
    "check_court_agent_lifecycle.py",
    "check_court_runtime_concurrency.py",
    "check_court_intervention_matrix.py",
    "check_supercc_functional.py",
    "check_supercc_ministry_dispatch.py",
    "check_supercc_no_silence_429_patrol.py",
    "check_supercc_super_entry.py",
    "check_supercc_profiles.py",
    "check_supercc_truth_gates.py",
    "supercc_watchdog.py",
    "sync_active_copies.py",

    "check_agente_terminal.py",
    "court_heartbeat_watch.py",
    "agente_terminal.py",
    "archive_runtime_task.py",
    "agent_runtime_probe.py",
    "check_shiguan_http.py",
    "check_shiguan_peer_state_transaction.py",
    "shiguan_security.py",
    "shiguan_entry_utils.py",
    "memory_decision.py",
    "check_active_copy_hashes.py",
    "check_portability.py",
    "check_release_gate.py",
    "release_gate_manifest.py",
    "check_release_manifest.py",
    "check_source_state_budget.py",
    "check_read_only_contract.py",
    "check_shiguan_import_queue.py",
    "check_shiguan_queue_and_autosync_safety.py",
    "sync_shiguan_obsidian_vault.py",
    "check_obsidian_sync_transaction.py",
    "plan_shiguan_pending_quarantine.py",
    "shiguan_pending_governance.py",
    "shiguan_pending_governance_cli.py",
    "shiguan_pending_trust.py",
    "check_shiguan_pending_quarantine_plan.py",
    "repair_archive_placeholders.py",
    "migrate_shared_shiguan.py",
    "shiguan_paths.py",
]

REQUIRED_COURT_WEB = [
    Path("web") / "shiguan-tree" / "index.html",
    Path("web") / "shiguan-tree" / "styles.css",
    Path("web") / "shiguan-tree" / "api.js",
    Path("web") / "shiguan-tree" / "app.js",
]

REQUIRED_COURT_REFERENCES = [
    Path("references") / "court-capability-registry.md",
    Path("references") / "court-closeout-validation.md",
    Path("references") / "court-core-contract.md",
    Path("references") / "court-host-platform-pitfalls.md",
    Path("references") / "court-offices-dispatch.md",
    Path("references") / "court-office-model-routing.md",
    Path("references") / "court-shiguan-memory.md",
    Path("references") / "court-startup-authority.md",
    Path("references") / "court-state-runtime-agents.md",
    Path("references") / "court-supercc-runtime-selection.md",
    Path("references") / "hermes-studio-super-gl.md",
    Path("references") / "obsidian-autosync-rest.md",
    Path("references") / "hermes-studio-group-chat.md",
    Path("references") / "sections" / "court-office-voice-fewshot.md",
    Path("references") / "benchmarks" / "cft0808-edict.yaml",
    Path("references") / "court-policy.yaml",
    Path("references") / "court-roles.yaml",
    Path("references") / "shiguan-ledger-policy.md",
    Path("references") / "complexity-budget.md",
    Path("references") / "manifests" / "release-gates.v1.json",
    Path("references") / "manifests" / "source-state-budget.v1.json",
]

REQUIRED_SHIGUAN_STATE = [
    Path("references") / "shiguan-index.jsonl",
    Path("references") / "shiguan-knowledge-graph.json",
    Path("references") / "shiguan-tree" / "_index.md",
]

REQUIRED_AGENT_ACCESS_TERMS = [
    "court-capability-router",
    "query_shiguan_index.py",
    "court-shiguan",
]

RECOMMENDED_AGENT_MAX_DEPTH = 4
RECOMMENDED_AGENT_MAX_THREADS = 16
FIND_SKILLS_URL = "https://www.skills.sh/vercel-labs/skills/find-skills"
FIND_SKILLS_INSTALL = "npx skills add https://github.com/vercel-labs/skills --skill find-skills"


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured)
    return Path.home() / ".codex"


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def catalog_path() -> Path:
    shared = shared_references_root() / "installed-capabilities-catalog.md"
    if shared.exists():
        return shared
    local = skill_root() / "references" / "installed-capabilities-catalog.md"
    if local.exists():
        return local
    installed = (
        codex_home()
        / "skills"
        / "court-capability-router"
        / "references"
        / "installed-capabilities-catalog.md"
    )
    if installed.exists():
        return installed
    return skill_root() / "references" / "department-map.md"


def require_path(label: str, path: Path) -> tuple[bool, str]:
    if path.exists():
        return True, f"{label}_OK {path}"
    return False, f"{label}_MISSING {path}"


def require_skill(label: str, root: Path, name: str) -> tuple[bool, str]:
    path = root / name / "SKILL.md"
    if path.exists():
        return True, f"{label}_OK {path}"
    remediation = "Recruit or install this prerequisite before relying on court routing."
    if name == "find-skills":
        remediation = (
            f"Install find-skills from {FIND_SKILLS_URL}; command: {FIND_SKILLS_INSTALL}"
        )
    return False, f"{label}_MISSING {path} {remediation}"


def require_relative_file(label: str, root: Path, relative_path: Path) -> tuple[bool, str]:
    path = root / relative_path
    if path.exists():
        return True, f"{label}_OK {path}"
    return False, (
        f"{label}_MISSING {path} "
        "Repair this system skill before relying on structure validation."
    )


def check_court_scripts() -> list[str]:
    scripts_dir = skill_root() / "scripts"
    return [
        name for name in REQUIRED_COURT_SCRIPTS if not (scripts_dir / name).exists()
    ]


def check_court_web() -> list[str]:
    root = skill_root()
    return [str(path) for path in REQUIRED_COURT_WEB if not (root / path).exists()]


def check_court_references() -> list[str]:
    root = skill_root()
    return [str(path) for path in REQUIRED_COURT_REFERENCES if not (root / path).exists()]


def check_shiguan_state() -> list[str]:
    root = shared_references_root()
    mapped = {
        Path("references") / "shiguan-index.jsonl": root / "shiguan-index.jsonl",
        Path("references") / "shiguan-knowledge-graph.json": root / "shiguan-knowledge-graph.json",
        Path("references") / "shiguan-tree" / "_index.md": root / "shiguan-tree" / "_index.md",
    }
    return [str(path) for relative, path in mapped.items() if relative in REQUIRED_SHIGUAN_STATE and not path.exists()]


def check_agent_capability_access(agents_root: Path) -> list[str]:
    missing: list[str] = []
    template_root = skill_root() / "agents" / "standing-officials"
    for root_label, root in (("installed", agents_root), ("template", template_root)):
        for agent_name in REQUIRED_AGENTS:
            path = root / agent_name
            if not path.exists():
                missing.append(f"{root_label}:{agent_name}:missing")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for term in REQUIRED_AGENT_ACCESS_TERMS:
                if term not in text:
                    missing.append(f"{root_label}:{agent_name}:{term}")
    return missing


def check_standing_profiles() -> list[str]:
    scripts_dir = skill_root() / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        import check_supercc_profiles  # type: ignore

        check_supercc_profiles.validate_all()
    except Exception as exc:
        return [f"SUPERCC_PROFILE_VALIDATION_FAILED {exc}"]
    return []


def check_installed_codex_agent_roles() -> list[str]:
    try:
        import tomllib

        agents_dir = codex_home() / "agents"
        for path in agents_dir.glob("*.toml"):
            tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"CODEX_AGENT_ROLE_VALIDATION_FAILED {exc}"]
    return []


def check_codex_config(path: Path) -> list[str]:
    if not path.exists():
        return [f"CONFIG_MISSING {path}"]

    text = path.read_text(encoding="utf-8")
    messages: list[str] = []
    try:
        import tomllib

        data = tomllib.loads(text)
    except Exception:
        return ["CONFIG_PARSE_FAILED"]
    agents = data.get("agents") if isinstance(data, dict) else None
    features = data.get("features") if isinstance(data, dict) else None
    agents = agents if isinstance(agents, dict) else {}
    features = features if isinstance(features, dict) else {}
    multi_agent_v2 = features.get("multi_agent_v2")
    multi_agent_v2 = multi_agent_v2 if isinstance(multi_agent_v2, dict) else {}
    if not agents:
        messages.append("AGENTS_CONFIG_MISSING [agents]")
    depth = agents.get("max_depth")
    legacy_threads = agents.get("max_threads")
    v2_enabled = multi_agent_v2.get("enabled") is True
    v2_threads = multi_agent_v2.get("max_concurrent_threads_per_session")
    if not isinstance(depth, int) or isinstance(depth, bool) or depth < RECOMMENDED_AGENT_MAX_DEPTH:
        messages.append(
            "AGENTS_MAX_DEPTH_BELOW_RECOMMENDED "
            f"recommended >= {RECOMMENDED_AGENT_MAX_DEPTH}; run "
            "python .\\scripts\\ensure_court_agent_config.py --write"
        )
    if v2_enabled:
        if legacy_threads is not None:
            messages.append("AGENTS_MAX_THREADS_FORBIDDEN_WITH_MULTI_AGENT_V2")
        if not isinstance(v2_threads, int) or isinstance(v2_threads, bool) or v2_threads < RECOMMENDED_AGENT_MAX_THREADS:
            messages.append(
                "MULTI_AGENT_V2_THREADS_BELOW_RECOMMENDED "
                f"recommended >= {RECOMMENDED_AGENT_MAX_THREADS}; run "
                "python .\\scripts\\ensure_court_agent_config.py --write"
            )
        if multi_agent_v2.get("hide_spawn_agent_metadata") is not True:
            messages.append("MULTI_AGENT_V2_RESERVED_SCHEMA_NOT_HIDDEN")
    else:
        if features.get("multi_agent") is not True:
            messages.append("MULTI_AGENT_V1_FEATURE_NOT_ENABLED")
        if not isinstance(legacy_threads, int) or isinstance(legacy_threads, bool) or legacy_threads < 15:
            messages.append(
                "AGENTS_MAX_THREADS_BELOW_RECOMMENDED "
                "recommended >= 15 for V1 child threads; run "
                "python .\\scripts\\ensure_court_agent_config.py --write --protocol v1"
            )
        if v2_threads != RECOMMENDED_AGENT_MAX_THREADS:
            messages.append("MULTI_AGENT_V1_INACTIVE_V2_THREADS_NOT_PRESERVED")
        if multi_agent_v2.get("hide_spawn_agent_metadata") is not True:
            messages.append("MULTI_AGENT_V1_INACTIVE_V2_SCHEMA_NOT_PRESERVED")
    return messages


def capability_index_path_contract() -> dict[str, object]:
    try:
        expected_manifest = reference_path("installed-capabilities-manifest.json")
        expected_catalog = reference_path("installed-capabilities-catalog.md")
        actual_manifest = capability_index_manifest_path()
        actual_catalog = capability_index_catalog_path()
    except (OSError, RuntimeError) as exc:
        return {
            "ok": False,
            "status": "FAILED",
            "reason": "shared_shiguan_path_error",
            "error_type": type(exc).__name__,
        }
    if actual_manifest != expected_manifest or actual_catalog != expected_catalog:
        return {
            "ok": False,
            "status": "FAILED",
            "reason": "capability_index_path_mismatch",
            "manifest_path": str(actual_manifest),
            "catalog_path": str(actual_catalog),
        }
    return {
        "ok": True,
        "status": "PASSED",
        "reason": "shared_shiguan_paths_match",
        "manifest_path": str(actual_manifest),
        "catalog_path": str(actual_catalog),
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on missing optional local agents/catalog state instead of warning.",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        original = globals()["capability_index_manifest_path"]

        def broken_manifest_path() -> Path:
            raise RuntimeError("simulated shared-root resolution loop")

        try:
            globals()["capability_index_manifest_path"] = broken_manifest_path
            result = capability_index_path_contract()
        finally:
            globals()["capability_index_manifest_path"] = original
        assert result["ok"] is False
        assert result["reason"] == "shared_shiguan_path_error"
        print(json.dumps({"ok": True, "shared_shiguan_path_error": True}, sort_keys=True))
        return 0

    path_contract = capability_index_path_contract()
    if not path_contract["ok"]:
        print(json.dumps(path_contract, ensure_ascii=False, sort_keys=True))
        return 2

    path = catalog_path()
    if not path.exists():
        print(f"MAP_SOURCE_MISSING {path}")
        return 2

    text = path.read_text(encoding="utf-8")
    if not re.search(r"(?m)^#{1,2} Court Department Capability Map\s*$", text):
        print(f"MAP_MISSING {path}")
        print("Use references/department-map.md as fallback.")
        return 3

    missing = [
        unit
        for unit in REQUIRED_UNITS
        if not re.search(rf"^\| {re.escape(unit)} \|", text, flags=re.MULTILINE)
    ]
    if missing:
        print(f"MAP_INCOMPLETE {path}")
        print("Missing: " + ", ".join(missing))
        return 4

    if "## Capability Registry Dimensions" not in text:
        print(f"DIMENSIONS_MISSING {path}")
        print("Missing: Capability Registry Dimensions")
        return 5

    missing_dimensions = [
        dimension
        for dimension in REQUIRED_DIMENSIONS
        if not re.search(rf"^\| {re.escape(dimension)} \|", text, flags=re.MULTILINE)
    ]
    if missing_dimensions:
        print(f"DIMENSIONS_INCOMPLETE {path}")
        print("Missing: " + ", ".join(missing_dimensions))
        return 6

    home = codex_home()
    required_roots = [("CODEX_SKILLS", home / "skills")]
    optional_roots = [
        ("AGENT_SKILLS", Path.home() / ".agents" / "skills"),
        ("CODEX_AGENTS", home / "agents"),
    ]
    for label, root in required_roots:
        ok, message = require_path(label, root)
        print(message)
        if not ok:
            return 7
    optional_warnings: list[str] = []
    for label, root in optional_roots:
        ok, message = require_path(label, root)
        print(message if ok else f"{label}_OPTIONAL_MISSING {root}")
        if not ok:
            optional_warnings.append(f"{label}_OPTIONAL_MISSING")

    for label, skill_name in REQUIRED_SKILLS:
        ok, message = require_skill(label, home / "skills", skill_name)
        print(message)
        if not ok:
            return 10

    for label, skill_name in REQUIRED_SYSTEM_SKILLS:
        ok, message = require_skill(label, home / "skills" / ".system", skill_name)
        print(message)
        if not ok:
            return 11

    for label, relative_path in REQUIRED_SYSTEM_FILES:
        ok, message = require_relative_file(label, home / "skills" / ".system", relative_path)
        print(message)
        if not ok:
            return 12

    missing_scripts = check_court_scripts()
    if missing_scripts:
        print("COURT_SCRIPTS_INCOMPLETE " + ", ".join(missing_scripts))
        return 13

    missing_web = check_court_web()
    if missing_web:
        print("COURT_WEB_INCOMPLETE " + ", ".join(missing_web))
        return 14

    missing_references = check_court_references()
    if missing_references:
        print("COURT_REFERENCES_INCOMPLETE " + ", ".join(missing_references))
        return 19

    missing_state = check_shiguan_state()
    if missing_state:
        print("SHIGUAN_STATE_INCOMPLETE " + ", ".join(missing_state))
        return 15

    missing_agents = [
        agent_name for agent_name in REQUIRED_AGENTS if not (home / "agents" / agent_name).exists()
    ]
    if missing_agents:
        message = "CODEX_AGENTS_OPTIONAL_INCOMPLETE " + ", ".join(missing_agents)
        print(message)
        optional_warnings.append(message)
        if args.strict:
            return 8

    missing_agent_access = check_agent_capability_access(home / "agents")
    if missing_agent_access:
        message = "AGENT_CAPABILITY_ACCESS_OPTIONAL_INCOMPLETE " + ", ".join(missing_agent_access)
        print(message)
        optional_warnings.append(message)
        if args.strict:
            return 16

    standing_profile_errors = check_standing_profiles()
    if standing_profile_errors:
        message = "STANDING_PROFILE_INCOMPLETE " + " | ".join(standing_profile_errors)
        print(message)
        return 17

    codex_agent_role_errors = check_installed_codex_agent_roles()
    if codex_agent_role_errors:
        message = "CODEX_AGENT_ROLES_INCOMPLETE " + " | ".join(codex_agent_role_errors)
        print(message)
        return 18

    managed = home / "managed_config.toml"
    config_errors = check_codex_config(managed if managed.exists() else home / "config.toml")
    if config_errors:
        for error in config_errors:
            print("CONFIG_OPTIONAL_NOTICE " + error)

    print(f"MAP_OK {path}")
    print("Units: " + ", ".join(REQUIRED_UNITS))
    print("Dimensions: " + ", ".join(REQUIRED_DIMENSIONS))
    print("Agents: " + ", ".join(REQUIRED_AGENTS))
    print(
        "Prerequisite skills: "
        + ", ".join([name for _, name in REQUIRED_SKILLS + REQUIRED_SYSTEM_SKILLS])
    )
    print("Court scripts: " + ", ".join(REQUIRED_COURT_SCRIPTS))
    print("Court web: " + ", ".join(str(path) for path in REQUIRED_COURT_WEB))
    print("Court references: " + ", ".join(str(path) for path in REQUIRED_COURT_REFERENCES))
    print(f"Shared Shiguan root: {shared_references_root()}")
    print("Shiguan state: " + ", ".join(str(path) for path in REQUIRED_SHIGUAN_STATE))
    print("Agent capability access: " + ", ".join(REQUIRED_AGENT_ACCESS_TERMS))
    print("Standing profile validation: check_supercc_profiles.py")
    print("Installed Codex agent role validation: tomllib parse of .codex/agents/*.toml")
    if optional_warnings:
        print("OPTIONAL_WARNINGS " + " | ".join(optional_warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
