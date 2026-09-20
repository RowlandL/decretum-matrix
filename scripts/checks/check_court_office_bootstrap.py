"""Regression checks for mode-neutral court office identity preload."""

from __future__ import annotations

from dataclasses import asdict

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
import tempfile
from unittest.mock import patch
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import json
import hashlib
import sys

sys.dont_write_bytecode = True

from court_office_bootstrap import build_preload_manifest, build_spawn_contract, validate_preload_ack
from checks.installed_identity_fixture import write_skill


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_checks() -> int:
    manifest = build_preload_manifest("xingbu", court_code="COURT-FIXTURE-1")
    require(
        asdict(manifest).get("startup_guide_path")
        == "references/court-normal-startup.md",
        "preload manifest/asdict omitted exact portable startup guide path",
    )
    require(manifest.role_key == "xingbu", "xingbu role identity missing")
    require(manifest.office_zh == "刑部", "xingbu Chinese office mismatch")
    require(manifest.direct_superior == "shangshu", "xingbu superior mismatch")
    require(bool(manifest.profile_source and manifest.dossier_path), "profile/dossier paths missing")
    require(manifest.court_skill_name == "decretum-matrix", "court skill name mismatch")
    require(manifest.court_skill_path == "SKILL.md", "technical skill locator changed")
    require(manifest.court_code == "COURT-FIXTURE-1", "dispatched court code missing")
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
        "profile_source": manifest.profile_source,
        "dossier_path": manifest.dossier_path,
        "court_skill_path": manifest.court_skill_path,
        "startup_guide_path": manifest.startup_guide_path,
        "startup_guide_loaded": "YES",
        "court_code": manifest.court_code,
        "agent_dossier_loaded": "YES",
        "loaded_skills": ["decretum-matrix"],
        "model_route_id": contract["model_route"]["model_route_id"],
        "model_override_applied": False,
        "inheritance_policy": "inherit_main_thread_model_reserved_schema",
    }
    validated = validate_preload_ack(manifest, ack, model_route=contract["model_route"])
    require(validated["preload_status"] == "PASSED", "valid preload ack did not pass")
    for field in ("profile_source", "dossier_path", "court_skill_path"):
        try:
            validate_preload_ack(manifest, {**ack, field: "wrong/source/path"}, model_route=contract["model_route"])
        except ValueError:
            pass
        else:
            raise AssertionError(f"wrong {field} accepted by validate_preload_ack")
    try:
        validate_preload_ack(manifest, {**ack, "court_code": "WRONG-CASE"}, model_route=contract["model_route"])
    except ValueError:
        mismatch_rejected = True
    else:
        raise AssertionError("mismatched preload ack was accepted")
    invalid_startup = {
        "missing_path": {key: value for key, value in ack.items() if key != "startup_guide_path"},
        "wrong_path": {**ack, "startup_guide_path": "references/wrong-startup.md"},
        "missing_loaded": {key: value for key, value in ack.items() if key != "startup_guide_loaded"},
        "loaded_no": {**ack, "startup_guide_loaded": "NO"},
        "loaded_boolean": {**ack, "startup_guide_loaded": True},
    }
    accepted_invalid = []
    for name, candidate in invalid_startup.items():
        try:
            validate_preload_ack(manifest, candidate, model_route=contract["model_route"])
        except ValueError:
            continue
        accepted_invalid.append(name)
    require(
        not accepted_invalid,
        "startup preload acknowledgement gaps accepted: " + ", ".join(accepted_invalid),
    )

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


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        write_skill(root)
        startup = root / "references" / "court-normal-startup.md"
        startup.parent.mkdir(parents=True, exist_ok=True)
        startup.write_text("# Isolated startup fixture\n", encoding="utf-8")
        with patch.dict(build_preload_manifest.__kwdefaults__, skill_root=root), patch.object(Path, "read_bytes", side_effect=AssertionError("runtime file bytes read")), patch.object(hashlib, "sha256", side_effect=AssertionError("runtime identity calculation")):
            return run_checks()


if __name__ == "__main__":
    raise SystemExit(main())
