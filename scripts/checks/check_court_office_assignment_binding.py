"""Focused offline checks for canonical office/name/profile/skill assignment binding."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from typing import get_type_hints

sys.dont_write_bytecode = True

import court_office_bootstrap
import court_dispatch_hierarchy


CANONICAL_OFFICES = (
    ("taizi", "TaiZi", "taizi", "taizi", "太子", "user"),
    ("zhongshu", "ZhongShu", "zhongshu", "zhongshu", "中书省", "taizi"),
    ("menxia", "MenXia", "menxia", "menxia", "门下省", "taizi"),
    ("shangshu", "ShangShu", "shangshu", "shangshu", "尚书省", "taizi"),
    ("libu-hr", "LiBuHR", "libu_hr", "libu-hr", "吏部", "shangshu"),
    ("libu", "LiBu", "libu", "libu", "礼部", "shangshu"),
    ("hubu", "HuBu", "hubu", "hubu", "户部", "shangshu"),
    ("gongbu", "GongBu", "gongbu", "gongbu", "工部", "shangshu"),
    ("xingbu", "XingBu", "xingbu", "xingbu", "刑部", "shangshu"),
    ("bingbu", "BingBu", "bingbu", "bingbu", "兵部", "shangshu"),
    ("shiguan", "ShiGuan", "shiguan", "shiguan", "史馆", "taizi/menxia"),
    ("shiguan-hermes", "ShiGuanHermes", "shiguan_hermes", "shiguan-hermes", "史馆", "taizi/menxia"),
    ("zaochao", "ZaoChao", "zaochao", "zaochao", "早朝", "taizi"),
    ("patrol-inspector", "PatrolInspector", "patrol_inspector", "patrol-inspector", "监察使", "taizi"),
)

DISPATCH_REFERENCE = Path(__file__).resolve().parents[2] / "references" / "court-offices-dispatch.md"
BINDING_REFERENCE = Path(__file__).resolve().parents[2] / "references" / "sections" / "court-office-name-profile-skill-binding.md"
EXACT_BINDING_LINK = "[court-office-name-profile-skill-binding.md](sections/court-office-name-profile-skill-binding.md)"
EXACT_TASK_NAME_STATEMENT = "task_name is routing metadata; name_binding does not prove profile_binding or skill_binding."






def write_profile(root: Path, role: str, *, role_key: str | None = None, office_zh: str = "官署", direct_superior: str = "shangshu") -> Path:
    path = root / f"{role}.toml"
    path.write_text(
        "[profile]\n"
        f'role_key = "{role_key if role_key is not None else role}"\n'
        f'office_zh = "{office_zh}"\n'
        f'direct_superior = "{direct_superior}"\n',
        encoding="utf-8",
    )
    return path


def fixture_skill_requirements(root: Path) -> list[dict[str, str]]:
    court = court_office_bootstrap.SKILL_PATH.resolve()
    tdd = root / "test-driven-development" / "SKILL.md"
    tdd.parent.mkdir(parents=True, exist_ok=True)
    tdd.write_text("# tdd fixture\n", encoding="utf-8")
    return [
        {"name": "decretum-matrix", "source": str(court), "purpose": "governing court workflow", "ack_name": "decretum-matrix"},
        {"name": "test-driven-development", "source": str(tdd.resolve()), "purpose": "bounded implementation", "ack_name": "test-driven-development"},
    ]


def rejection_reason(action: object) -> str:
    try:
        action()  # type: ignore[operator]
    except ValueError as exc:
        return str(exc)
    raise AssertionError("invalid assignment binding was accepted")


def assert_reason(action: object, expected: str) -> None:
    actual = rejection_reason(action)
    assert expected in actual, (expected, actual)


def check_canonical_table(build: object, profile_root: Path, skills: list[dict[str, str]]) -> None:
    for role, head, task_prefix, agent_prefix, office_zh, direct_superior in CANONICAL_OFFICES:
        binding = build(  # type: ignore[operator]
            role_key=role,
            collaboration_task_name=f"{task_prefix}_runtime_r2",
            court_agent_id=f"{agent_prefix}-worker-1",
            requires_gongjiang=False,
            skill_requirements=skills,
            profile_root=profile_root,
        )
        assert binding["role_key"] == role
        assert binding["official_name_head"] == head
        assert binding["task_name_prefix"] == task_prefix
        assert binding["agent_id_prefix"] == agent_prefix
        assert binding["office_zh"] == office_zh
        assert binding["direct_superior"] == direct_superior
        assert binding["name_binding"] == "PASSED"
        assert binding["profile_binding"] == "PASSED"
        assert binding["skill_binding"] == "PASSED"
        assert binding["office_execution_ready"] is True
        fixture_profile = (profile_root / f"{role}.toml").resolve()
        assert binding["profile_source"] == str(fixture_profile)
        returned_skills = binding["required_skill_bindings"]
        assert isinstance(returned_skills, list)
        assert [item["ack_name"] for item in returned_skills] == [item["name"] for item in skills]

    workshop = build(  # type: ignore[operator]
        role_key="gongbu",
        collaboration_task_name="gongbu_gongjiang_runtime_r2",
        court_agent_id="gongbu-gongjiang-1",
        requires_gongjiang=True,
        skill_requirements=skills,
        profile_root=profile_root,
    )
    assert workshop["official_name_head"] == "GongBu-GongJiang"
    assert workshop["office_name_token"] == "gongbu_gongjiang"
    assert workshop["task_name_prefix"] == "gongbu_gongjiang"
    assert workshop["agent_id_prefix"] == "gongbu-gongjiang"
    assert workshop["direct_superior"] == "gongbu"
    assert workshop["office_execution_ready"] is True

    cross_office_description = build(  # type: ignore[operator]
        role_key="gongbu",
        collaboration_task_name="gongbu_menxia_quality",
        court_agent_id="gongbu-review-1",
        requires_gongjiang=False,
        skill_requirements=skills,
        profile_root=profile_root,
    )
    assert cross_office_description["name_binding"] == "PASSED"


def check_name_rejects(build: object, profile_root: Path, skills: list[dict[str, str]]) -> None:
    rejected = (
        ("gongbu", "notgongbu_runtime", "gongbu-1", False, "office_name_mismatch"),
        ("gongbu", "gongbuild_runtime", "gongbu-1", False, "office_name_mismatch"),
        ("gongbu", "gongbu_runtime", "gongbu-worker-1", True, "missing_gongjiang"),
        ("gongbu", "gongbu_gongjiangish_runtime", "gongbu-gongjiang-1", True, "missing_gongjiang"),
        ("gongbu", "gongbu_gongjiang_runtime", "gongbuish-worker-1", True, "office_name_mismatch"),
        ("libu-hr", "libu_runtime", "libu-1", False, "office_name_mismatch"),
        ("gongbu", "gongbu_", "gongbu-worker-1", False, "office_name_mismatch"),
        ("gongbu", "gongbu_runtime", "gongbu-", False, "office_name_mismatch"),
        ("gongbu", "gongbu_../runtime", "gongbu-worker-1", False, "office_name_mismatch"),
        ("gongbu", "gongbu_runtime/path", "gongbu-worker-1", False, "office_name_mismatch"),
        ("gongbu", "gongbu_runtime\\path", "gongbu-worker-1", False, "office_name_mismatch"),
        ("gongbu", "gongbu_runtime", "gongbu-../worker", False, "office_name_mismatch"),
        ("gongbu", "gongbu_runtime", "gongbu-worker/path", False, "office_name_mismatch"),
        ("gongbu", "gongbu_runtime", "gongbu-worker\\path", False, "office_name_mismatch"),
    )
    for role, task, agent, workshop, reason in rejected:
        assert_reason(lambda role=role, task=task, agent=agent, workshop=workshop: build(  # type: ignore[operator]
            role_key=role, collaboration_task_name=task, court_agent_id=agent,
            requires_gongjiang=workshop, skill_requirements=skills, profile_root=profile_root,
        ), reason)


def check_profile_rejects(build: object, root: Path, skills: list[dict[str, str]]) -> None:
    def call(profile_root: Path, role: str = "gongbu") -> object:
        return build(  # type: ignore[operator]
            role_key=role, collaboration_task_name="gongbu_runtime", court_agent_id="gongbu-1",
            requires_gongjiang=False, skill_requirements=skills, profile_root=profile_root,
        )

    missing = root / "missing"
    missing.mkdir()
    assert_reason(lambda: call(missing), "standing_profile_missing")
    invalid = root / "invalid"; invalid.mkdir(); (invalid / "gongbu.toml").write_text("[profile\n", encoding="utf-8")
    assert_reason(lambda: call(invalid), "standing_profile_invalid")
    mismatch = root / "mismatch"; mismatch.mkdir(); write_profile(mismatch, "gongbu", role_key="hubu")
    assert_reason(lambda: call(mismatch), "standing_profile_identity_mismatch")
    wrong_zh = root / "wrong-zh"; wrong_zh.mkdir(); write_profile(wrong_zh, "gongbu", office_zh="户部")
    assert_reason(lambda: call(wrong_zh), "standing_profile_identity_mismatch")
    wrong_superior = root / "wrong-superior"; wrong_superior.mkdir(); write_profile(wrong_superior, "gongbu", direct_superior="taizi")
    assert_reason(lambda: call(wrong_superior), "standing_profile_identity_mismatch")
    no_zh = root / "no-zh"; no_zh.mkdir(); write_profile(no_zh, "gongbu", office_zh="")
    assert_reason(lambda: call(no_zh), "standing_profile_fields_missing")
    no_superior = root / "no-superior"; no_superior.mkdir(); write_profile(no_superior, "gongbu", direct_superior="")
    assert_reason(lambda: call(no_superior), "standing_profile_fields_missing")
    assert_reason(lambda: call(root, "../gongbu"), "standing_profile_path_escape")


def check_skill_rejects(build: object, profile_root: Path, skills: list[dict[str, str]], root: Path) -> None:
    def call(requirements):
        return build(role_key="gongbu", collaboration_task_name="gongbu_runtime", court_agent_id="gongbu-1", requires_gongjiang=False, skill_requirements=requirements, profile_root=profile_root)
    assert_reason(lambda: call(skills[1:]), "required_court_skill_missing")
    attacker = root / "attacker" / "SKILL.md"
    attacker.parent.mkdir(parents=True)
    attacker.write_text("# attacker", encoding="utf-8")
    assert_reason(lambda: call([{**skills[0], "source": str(attacker.resolve())}, skills[1]]), "court_skill_source_mismatch")
    conflict = [dict(skills[0]), {**skills[0], "purpose": "different request"}]
    assert_reason(lambda: call(conflict), "skill_binding_conflict")
    assert_reason(lambda: call([skills[0], {**skills[1], "source": str((root / "absent.md").resolve())}]), "required_skill_missing")
    assert_reason(lambda: call([skills[0], {**skills[1], "ack_name": "wrong"}]), "skill_ack_incomplete")
    incomplete = [dict(item) for item in skills]
    incomplete[1].pop("ack_name")
    assert_reason(lambda: call(incomplete), "skill_ack_incomplete")
    assert_reason(lambda: call(tuple(skills)), "skill_binding_invalid")
    assert all(set(item) == {"name", "source", "purpose", "ack_name"} for item in call(skills)["required_skill_bindings"])


def check_public_signatures() -> None:
    load = court_office_bootstrap.load_standing_profile_binding
    assert list(inspect.signature(load).parameters) == ["role_key", "profile_root"]
    assert get_type_hints(load)["profile_root"] is Path
    validate = court_office_bootstrap.validate_skill_requirements
    assert get_type_hints(validate)["requirements"] == list[dict[str, str]]
    build = court_office_bootstrap.build_office_assignment_binding
    assert get_type_hints(build)["skill_requirements"] == list[dict[str, str]]
    assert list(inspect.signature(court_office_bootstrap.build_child_office_profile).parameters) == ["binding", "child_role", "case_ref", "semantic_receipt_id", "expires_at_utc"]


def check_child_office_profile_builder() -> None:
    build = court_office_bootstrap.build_child_office_profile
    binding = {"role": "gongbu", "instance_id": "gongbu-worker-0001", "instance_kind": "office_worker_instance", "canonical_authority": False, "owner_role": "gongbu", "direct_superior": "gongbu", "bounded_mandate": "bounded shard", "expected_result": "return report", "read_scope": ["work/input.txt"], "write_set": ["work/output.txt"], "task_id": "child-profile-builder-check", "dispatch_uid": "DSP-CHILD-PROFILE-BUILDER-0001", "shard_id": "gongbu-worker-0001", "attempt": 1, "terminal_condition": "stop after accepted report"}
    options = {"child_role": "GongBu-GongJiang", "case_ref": {"court_code": "COURT-FIXTURE-1", "charter_revision": 1}, "semantic_receipt_id": "SEM-FIXTURE-1", "expires_at_utc": "2099-01-01T00:00:00Z"}
    profile = build(binding, **options)
    assert profile["schema"] == "court.child_office_profile.v1"
    assert profile["case_ref"] == options["case_ref"] and profile["semantic_receipt_id"] == options["semantic_receipt_id"]
    rebuilt = build(dict(reversed(tuple(binding.items()))), **options)
    assert rebuilt == profile
    original_profile = json.loads(json.dumps(profile))
    binding["read_scope"].append("work/changed.txt")
    assert profile == original_profile
    assert_reason(lambda: build({**binding, "read_scope": ["../outside"]}, **options), "read_scope_unbounded")
    assert_reason(lambda: build({**binding, "owner_role": "hubu"}, **options), "child_profile_owner_mismatch")
    assert_reason(lambda: build({**binding, "child_charter": "second authority"}, **options), "child_profile_semantic_authority_override")
    assert_reason(lambda: build(binding, **{**options, "case_ref": {"court_code": "", "charter_revision": 1}}), "child_profile_case_ref_invalid")
    decision = court_dispatch_hierarchy.validate_dispatch_hierarchy(action="dispatch", calling_office="gongbu", target_role="gongbu", target_direct_superior="gongbu", instance_kind="office_worker_instance", canonical_authority=False, owner_role="gongbu", child_profile=profile)
    assert decision.allowed is True, decision.reason_codes


def check_governing_references() -> None:
    dispatch = DISPATCH_REFERENCE.read_text(encoding="utf-8")
    binding = BINDING_REFERENCE.read_text(encoding="utf-8")
    normalized_binding = " ".join(binding.split())
    assert dispatch.count(EXACT_BINDING_LINK) == 1
    assert EXACT_TASK_NAME_STATEMENT in dispatch
    assert (
        "execution-ready when the assignment identity, direct superior, scope, "
        "and host delivery evidence all match the same task."
        in normalized_binding
    )
    assert "| `patrol-inspector` | `PatrolInspector` | `patrol_inspector` | `patrol-inspector` |" in binding
    assert "`GongBu-GongJiang`" in binding
    assert "declarative TOML" in binding
    assert "required_skill_names?" in binding
    assert "ordinary `super并行`, `superCC`, and supported Hermes transports." in normalized_binding
    assert "`legacy_false_ready`" in binding
    assert "`context_drift`" in binding
    assert "`office_assignment_accepted=true`" in binding
    assert "`host_delivery_missing`" in binding
    assert "fails closed before task/event bytes change." in normalized_binding
    assert (
        "Reconfirm role, direct superior, scope, and expected result immediately "
        "before mutation or final acceptance."
        in normalized_binding
    )


def run_office_assignment_binding_checks() -> None:
    check_public_signatures()
    check_governing_references()
    build = getattr(court_office_bootstrap, "build_office_assignment_binding", None)
    assert callable(build), "build_office_assignment_binding is missing"
    check_child_office_profile_builder()
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        profiles = root / "agents" / "standing-officials"; profiles.mkdir(parents=True)
        for role, _, _, _, office_zh, direct_superior in CANONICAL_OFFICES:
            write_profile(profiles, role, office_zh=office_zh, direct_superior=direct_superior)
        skill = root / "SKILL.md"
        skill.write_text("# Isolated court fixture\n", encoding="utf-8")
        with patch.object(court_office_bootstrap, "SKILL_PATH", skill), patch.object(Path, "read_bytes", side_effect=AssertionError("runtime file bytes read")), patch.object(hashlib, "sha256", side_effect=AssertionError("runtime identity calculation")):
            skills = fixture_skill_requirements(root / "skills")
            check_canonical_table(build, profiles, skills[:1])
            check_name_rejects(build, profiles, skills[:1])
            check_profile_rejects(build, root, skills[:1])
            check_skill_rejects(build, profiles, skills, root)


def main() -> int:
    run_office_assignment_binding_checks()
    print("COURT_OFFICE_ASSIGNMENT_BINDING_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
