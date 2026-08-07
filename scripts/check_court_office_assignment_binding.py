"""Focused offline checks for canonical office/name/profile/skill assignment binding."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import sys
import tempfile
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

DISPATCH_REFERENCE = Path(__file__).resolve().parents[1] / "references" / "court-offices-dispatch.md"
BINDING_REFERENCE = Path(__file__).resolve().parents[1] / "references" / "sections" / "court-office-name-profile-skill-binding.md"
EXACT_BINDING_LINK = "[court-office-name-profile-skill-binding.md](sections/court-office-name-profile-skill-binding.md)"
EXACT_TASK_NAME_STATEMENT = "task_name is routing metadata; name_binding does not prove profile_binding or skill_binding."


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
        {"name": "decretum-matrix", "source": str(court.resolve()), "sha256": sha256(court), "purpose": "governing court workflow", "ack_name": "decretum-matrix", "ack_sha256": sha256(court)},
        {"name": "test-driven-development", "source": str(tdd.resolve()), "sha256": sha256(tdd), "purpose": "RED-GREEN implementation discipline", "ack_name": "test-driven-development", "ack_sha256": sha256(tdd)},
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
        assert binding["profile_hash"] == sha256(fixture_profile)
        assert binding["profile_hash"] == str(binding["profile_hash"]).lower()
        returned_skills = binding["required_skill_bindings"]
        assert isinstance(returned_skills, list)
        assert [(item["ack_name"], item["ack_sha256"]) for item in returned_skills] == [
            (item["name"], item["sha256"]) for item in skills
        ]

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
    def call(requirements: list[dict[str, str]]) -> object:
        return build(  # type: ignore[operator]
            role_key="gongbu", collaboration_task_name="gongbu_runtime", court_agent_id="gongbu-1",
            requires_gongjiang=False, skill_requirements=requirements, profile_root=profile_root,
        )

    assert_reason(lambda: call(skills[1:]), "required_court_skill_missing")
    attacker = root / "attacker" / "court-capability-router" / "SKILL.md"
    attacker.parent.mkdir(parents=True)
    attacker.write_text("# attacker court skill\n", encoding="utf-8")
    alternate_court = dict(skills[0])
    alternate_court.update(source=str(attacker.resolve()), sha256=sha256(attacker), ack_sha256=sha256(attacker))
    assert_reason(lambda: call([alternate_court, skills[1]]), "court_skill_source_mismatch")
    conflict = [dict(skills[0]), dict(skills[0])]
    other = root / "other-skill.md"; other.write_text("other\n", encoding="utf-8")
    conflict[1].update(source=str(other.resolve()), sha256=sha256(other), ack_sha256=sha256(other))
    assert_reason(lambda: call(conflict), "skill_binding_conflict")
    missing = dict(skills[1]); missing["source"] = str((root / "absent" / "SKILL.md").resolve())
    assert_reason(lambda: call([skills[0], missing]), "required_skill_missing")
    wrong = dict(skills[1]); wrong["sha256"] = "0" * 64
    assert_reason(lambda: call([skills[0], wrong]), "required_skill_hash_mismatch")
    incomplete = [dict(item) for item in skills]; incomplete[1].pop("ack_sha256")
    assert_reason(lambda: call(incomplete), "skill_ack_incomplete")
    wrong_ack_hash = [dict(item) for item in skills]; wrong_ack_hash[1]["ack_sha256"] = "f" * 64
    assert_reason(lambda: call(wrong_ack_hash), "skill_ack_incomplete")
    wrong_ack_name = [dict(item) for item in skills]; wrong_ack_name[1]["ack_name"] = "writing-plans"
    assert_reason(lambda: call(wrong_ack_name), "skill_ack_incomplete")
    assert_reason(lambda: call(tuple(skills)), "skill_binding_invalid")  # type: ignore[arg-type]


def check_public_signatures() -> None:
    load = court_office_bootstrap.load_standing_profile_binding
    load_signature = inspect.signature(load)
    assert list(load_signature.parameters) == ["role_key", "profile_root"]
    assert load_signature.parameters["profile_root"].kind is inspect.Parameter.KEYWORD_ONLY
    assert load_signature.parameters["profile_root"].default == court_office_bootstrap.PROFILE_ROOT
    assert get_type_hints(load)["profile_root"] is Path

    validate = court_office_bootstrap.validate_skill_requirements
    assert get_type_hints(validate)["requirements"] == list[dict[str, str]]
    build = court_office_bootstrap.build_office_assignment_binding
    assert get_type_hints(build)["skill_requirements"] == list[dict[str, str]]
    digest = court_office_bootstrap.canonical_child_office_binding_sha256
    digest_signature = inspect.signature(digest)
    assert list(digest_signature.parameters) == ["binding"]
    assert get_type_hints(digest)["return"] is str


def check_child_office_profile_builder() -> None:
    build = getattr(court_office_bootstrap, "build_child_office_profile", None)
    assert callable(build), "build_child_office_profile is missing"
    binding = {
        "role": "gongbu",
        "instance_id": "gongbu-worker-0001",
        "instance_kind": "office_worker_instance",
        "canonical_authority": False,
        "owner_role": "gongbu",
        "direct_superior": "gongbu",
        "bounded_mandate": "implement one bounded Gongbu shard",
        "expected_result": "return one structured implementation receipt",
        "read_scope": ["work/gongbu/input.txt"],
        "write_set": ["work/gongbu/worker-0001.txt"],
        "task_id": "child-profile-builder-check",
        "dispatch_uid": "DSP-CHILD-PROFILE-BUILDER-0001",
        "shard_id": "gongbu-worker-0001",
        "attempt": 1,
        "terminal_condition": "stop after the bounded receipt is accepted",
    }
    build_kwargs = {
        "child_role": "GongBu-GongJiang",
        "profile_sha256": "A" * 64,
        "dossier_sha256": "B" * 64,
        "skill_sha256": "C" * 64,
        "dispatch_context_packet_sha256": "D" * 64,
        "semantic_receipt_sha256": "E" * 64,
        "invariant_capsule_sha256": "F" * 64,
        "expires_at_utc": "2099-01-01T00:00:00Z",
    }
    profile = build(binding, **build_kwargs)
    required_fields = {
        "schema",
        "child_role",
        "role_key",
        "office_instance_id",
        "owner_role",
        "direct_superior",
        "canonical_authority",
        "instance_kind",
        "bounded_mandate",
        "expected_result",
        "read_scope",
        "write_set",
        "task_id",
        "dispatch_uid",
        "shard_id",
        "attempt",
        "profile_sha256",
        "dossier_sha256",
        "skill_sha256",
        "expires_at_utc",
        "terminal_condition",
        "dispatch_context_packet_schema",
        "dispatch_context_packet_sha256",
        "semantic_receipt_sha256",
        "invariant_capsule_schema",
        "invariant_capsule_sha256",
    }
    assert required_fields == set(profile)
    assert all(
        profile[field] == expected
        for field, expected in (
            ("profile_sha256", "a" * 64),
            ("dossier_sha256", "b" * 64),
            ("skill_sha256", "c" * 64),
            ("dispatch_context_packet_sha256", "d" * 64),
            ("semantic_receipt_sha256", "e" * 64),
            ("invariant_capsule_sha256", "f" * 64),
        )
    )
    canonical_digest = canonical_json_sha256(profile)
    reordered_binding = {
        key: binding[key]
        for key in reversed(tuple(binding))
    }
    reordered_binding["read_scope"] = tuple(binding["read_scope"])
    reordered_binding["write_set"] = tuple(binding["write_set"])
    rebuilt = build(reordered_binding, **build_kwargs)
    assert rebuilt == profile
    assert canonical_json_sha256(rebuilt) == canonical_digest
    full_binding = {
        **reordered_binding,
        "access_mode": "write",
        "mutation_allowed": True,
        "integration_authority": False,
        "worktree": ".",
        "child_profile": profile,
    }
    digest_binding = court_office_bootstrap.canonical_child_office_binding_sha256
    full_binding_digest = digest_binding(full_binding)
    assert full_binding_digest == canonical_json_sha256(full_binding)
    assert digest_binding(dict(reversed(tuple(full_binding.items())))) == full_binding_digest
    persisted_round_trip = json.loads(json.dumps(full_binding, ensure_ascii=False))
    assert digest_binding(persisted_round_trip) == full_binding_digest

    binding["bounded_mandate"] = "silently widened after profile generation"
    binding["read_scope"][0] = "work/gongbu/widened-input.txt"
    binding["write_set"].append("work/gongbu/widened-output.txt")
    assert profile["bounded_mandate"] == "implement one bounded Gongbu shard"
    assert profile["read_scope"] == ["work/gongbu/input.txt"]
    assert profile["write_set"] == ["work/gongbu/worker-0001.txt"]
    assert canonical_json_sha256(profile) == canonical_digest

    tampered = dict(profile)
    tampered["write_set"] = ["work/gongbu/widened-output.txt"]
    assert canonical_json_sha256(tampered) != canonical_digest
    synchronized_tamper = dict(full_binding)
    synchronized_tamper["write_set"] = ["work/gongbu/widened-output.txt"]
    synchronized_tamper["child_profile"] = tampered
    assert digest_binding(synchronized_tamper) != full_binding_digest
    future_field = dict(full_binding)
    future_field["future_bound_evidence"] = {"sequence": 1}
    assert digest_binding(future_field) != full_binding_digest
    missing_profile = dict(full_binding)
    missing_profile.pop("child_profile")
    assert_reason(
        lambda: digest_binding(missing_profile),
        "child_office_binding_digest_child_profile_required",
    )
    non_canonical_value = dict(full_binding)
    non_canonical_value["unsupported"] = object()
    assert_reason(
        lambda: digest_binding(non_canonical_value),
        "child_office_binding_digest_non_canonical_value",
    )

    nul_scope = dict(reordered_binding)
    nul_scope["read_scope"] = ["work/gongbu/input\x00.txt"]
    assert_reason(
        lambda: build(nul_scope, **build_kwargs),
        "read_scope_unbounded",
    )
    semantic_override = dict(reordered_binding)
    semantic_override["child_charter"] = "second authority"
    assert_reason(
        lambda: build(semantic_override, **build_kwargs),
        "child_profile_semantic_authority_override",
    )
    cross_owner = dict(reordered_binding)
    cross_owner["owner_role"] = "hubu"
    assert_reason(
        lambda: build(cross_owner, **build_kwargs),
        "child_profile_owner_mismatch",
    )

    profile = build(
        reordered_binding,
        child_role="GongBu-GongJiang",
        profile_sha256="1" * 64,
        dossier_sha256="2" * 64,
        skill_sha256="3" * 64,
        dispatch_context_packet_sha256="4" * 64,
        semantic_receipt_sha256="5" * 64,
        invariant_capsule_sha256="6" * 64,
        expires_at_utc="2099-01-01T00:00:00Z",
    )
    assert profile["schema"] == "court.child_office_profile.v1"
    assert profile["child_role"] == "GongBu-GongJiang"
    assert profile["role_key"] == "gongbu"
    assert profile["owner_role"] == "gongbu"
    assert profile["direct_superior"] == "gongbu"
    assert profile["canonical_authority"] is False
    assert profile["dispatch_context_packet_schema"] == "court.semantic.dispatch_context_packet.v1"
    assert profile["invariant_capsule_schema"] == "court.semantic.invariant_capsule.v1"
    decision = court_dispatch_hierarchy.validate_dispatch_hierarchy(
        action="dispatch",
        calling_office="gongbu",
        target_role="gongbu",
        target_direct_superior="gongbu",
        instance_kind="office_worker_instance",
        canonical_authority=False,
        owner_role="gongbu",
        child_profile=profile,
    )
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
        profiles = root / "profiles"; profiles.mkdir()
        for role, _, _, _, office_zh, direct_superior in CANONICAL_OFFICES:
            write_profile(profiles, role, office_zh=office_zh, direct_superior=direct_superior)
        skills = fixture_skill_requirements(root / "skills")
        check_canonical_table(build, profiles, skills)
        check_name_rejects(build, profiles, skills)
        check_profile_rejects(build, root, skills)
        check_skill_rejects(build, profiles, skills, root)


def main() -> int:
    run_office_assignment_binding_checks()
    print("COURT_OFFICE_ASSIGNMENT_BINDING_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
