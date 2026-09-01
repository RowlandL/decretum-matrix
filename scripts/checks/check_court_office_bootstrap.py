"""Regression checks for mode-neutral court office identity preload."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import json
import sys

sys.dont_write_bytecode = True

from court_office_bootstrap import build_preload_manifest, build_spawn_contract, validate_preload_ack


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    manifest = build_preload_manifest("xingbu")
    require(manifest.role_key == "xingbu", "xingbu role identity missing")
    require(manifest.office_zh == "刑部", "xingbu Chinese office mismatch")
    require(manifest.direct_superior == "shangshu", "xingbu superior mismatch")
    require(bool(manifest.profile_hash and manifest.dossier_hash), "profile/dossier hashes missing")
    require(manifest.court_skill_name == "decretum-matrix", "court skill name mismatch")
    require(manifest.court_skill_path == "SKILL.md", "technical skill locator changed")
    require(bool(manifest.court_skill_hash), "court skill hash missing")
    gongbu_manifest = build_preload_manifest("gongbu")
    require(
        gongbu_manifest.direct_superior == "shangshu",
        "ordinary Gongbu superior drifted away from shangshu",
    )
    require(
        manifest.dossier_path == "agents/office-dossiers/xingbu/AGENTS.md",
        "ordinary carrier did not resolve the ordinary dossier pointer",
    )
    visible_manifest = build_preload_manifest(
        "xingbu",
        carrier_kind="supercc_cli_office",
        supercc_enabled=True,
    )
    require(
        visible_manifest.dossier_path == "agents/supercc-dossiers/xingbu/AGENTS.md",
        "explicit visible carrier did not resolve its dossier pointer",
    )
    require(
        visible_manifest.profile_source == manifest.profile_source,
        "carrier selection split the shared standing profile",
    )

    try:
        build_preload_manifest("/root/xingbu_wave3")
    except ValueError:
        task_path_rejected = True
    else:
        raise AssertionError("canonical collaboration task path was accepted as office identity")

    contract = build_spawn_contract(
        "xingbu",
        assignment="review bounded safety risk",
        task_focus="security and privacy review",
        complexity="medium",
        risk="high",
        ambiguity="medium",
        transport="codex",
        allowed_actions=["read", "report"],
        forbidden_actions=["mutate"],
        evidence_contract="return file/line evidence",
        stop_conditions=["scope change"],
    )
    require(contract["preload_ack_required"] is True, "spawn contract did not require preload ack")
    require(contract["role_key"] == "xingbu", "spawn contract lost explicit role identity")
    require(contract["model_route"]["recommended_model"] == "gpt-5.6-sol", "spawn contract lost model recommendation")
    require(contract["model_route"]["recommended_reasoning_effort"] == "ultra", "spawn contract lost highest supported effort recommendation")
    require(contract["model_route"]["model_override_applied"] is False, "reserved V2 schema applied a forbidden override")

    ack = {
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
        "model_route_id": contract["model_route"]["model_route_id"],
        "model_override_applied": False,
        "inheritance_policy": "inherit_main_thread_model_reserved_schema",
    }
    validated = validate_preload_ack(manifest, ack, model_route=contract["model_route"])
    require(validated["preload_status"] == "PASSED", "valid preload ack did not pass")
    try:
        validate_preload_ack(manifest, {**ack, "profile_hash": "wrong"}, model_route=contract["model_route"])
    except ValueError:
        mismatch_rejected = True
    else:
        raise AssertionError("mismatched preload ack was accepted")

    print(
        json.dumps(
            {
                "ok": True,
                "role_key": manifest.role_key,
                "task_path_rejected": task_path_rejected,
                "mismatch_rejected": mismatch_rejected,
                "preload_ack_schema": manifest.preload_ack_schema,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



