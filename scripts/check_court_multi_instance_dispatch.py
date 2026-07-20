"""Regression checks for Proposal A multi-instance court dispatch.

Proposal A keeps one canonical authority per role while allowing bounded worker
instances with unique instance/shard identity and disjoint ownership. This
checker also proves that total instance count above sixteen is not itself a
rejection gate.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any

sys.dont_write_bytecode = True

from court_dispatch_policy import validate_dispatch_plan


OFFICES = {
    "taizi": ("太子", "user"),
    "zhongshu": ("中书省", "taizi"),
    "menxia": ("门下省", "taizi"),
    "shangshu": ("尚书省", "taizi"),
    "libu-hr": ("吏部", "shangshu"),
    "hubu": ("户部", "shangshu"),
    "libu": ("礼部", "shangshu"),
    "bingbu": ("兵部", "shangshu"),
    "xingbu": ("刑部", "shangshu"),
    "gongbu": ("工部", "shangshu"),
}
TRUSTED_PRELOAD_BY_ROLE: dict[str, dict[str, str]] = {}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _initialize_preload_fixture(root: Path) -> None:
    TRUSTED_PRELOAD_BY_ROLE.clear()
    skill_path = root / "SKILL.md"
    skill_path.write_text("fixture court skill\n", encoding="utf-8")
    skill_hash = _sha256(skill_path)
    for role in OFFICES:
        profile_rel = f"agents/standing-officials/{role}.toml"
        dossier_rel = f"agents/office-dossiers/{role}/AGENTS.md"
        profile_path = root / profile_rel
        dossier_path = root / dossier_rel
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        dossier_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(f"role = {role!r}\n", encoding="utf-8")
        dossier_path.write_text(f"# {role} fixture dossier\n", encoding="utf-8")
        TRUSTED_PRELOAD_BY_ROLE[role] = {
            "profile_path": profile_rel,
            "dossier_path": dossier_rel,
            "skill_path": "SKILL.md",
            "profile_hash": _sha256(profile_path),
            "dossier_hash": _sha256(dossier_path),
            "court_skill_hash": skill_hash,
            "preload_ack": "PASSED",
        }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def value(record: object, field: str) -> object:
    if isinstance(record, Mapping):
        return record.get(field)
    return getattr(record, field, None)


def entries_of(plan: object) -> tuple[object, ...]:
    entries = value(plan, "entries")
    require(isinstance(entries, Sequence), "validated plan must expose entries")
    return tuple(entries)


def dispatch_instance(
    role: str,
    number: int,
    *,
    kind: str,
    shard_id: str,
    owned_paths: Sequence[str] = (),
    write_set: Sequence[str] = (),
    canonical_authority: bool = False,
    global_integration_owner: bool = False,
    task_id: str | None = None,
    visibility: str = "non_visible",
    runtime_family: str = "spawned_subagent",
    super_giant_task_gate: str = "NOT_APPLICABLE",
    remaining_super_giant: bool = False,
    system_memory_percent: float = 40.0,
) -> dict[str, object]:
    office_zh, direct_superior = OFFICES[role]
    instance_key = f"{role}#{number:04d}"
    preload = TRUSTED_PRELOAD_BY_ROLE[role]
    return {
        "role": role,
        "office_zh": office_zh,
        "duty": f"bounded {role} shard {shard_id}",
        "direct_superior": direct_superior,
        "dependency_roles": [],
        "parallel_group": f"{role}-multi-instance",
        "allowed_actions": ["read", "report"],
        "forbidden_actions": ["mutate_unowned_paths"],
        "evidence_contract": "return instance-owned evidence with source pointers",
        "stop_conditions": ["ownership_conflict", "scale_or_memory_downgrade"],
        "visibility": visibility,
        "runtime_family": runtime_family,
        "role_key": role,
        "canonical_role_id": f"{role}#canonical",
        "office_instance_id": f"office-{instance_key}",
        "instance_key": instance_key,
        "office_instance_kind": kind,
        "canonical_authority": canonical_authority,
        "global_integration_owner": global_integration_owner,
        "task_id": task_id or f"task-{role}-{shard_id}-{number:04d}",
        "dispatch_uid": f"dispatch-{role}-{number:04d}",
        "shard_id": shard_id,
        "attempt": 1,
        "owned_paths": list(owned_paths),
        "write_set": list(write_set),
        "profile_path": preload["profile_path"],
        "dossier_path": preload["dossier_path"],
        "skill_path": preload["skill_path"],
        "profile_hash": preload["profile_hash"],
        "dossier_hash": preload["dossier_hash"],
        "court_skill_hash": preload["court_skill_hash"],
        "preload_ack": preload["preload_ack"],
        "evidence_pointer": f"ledger://{instance_key}",
        "heartbeat_state": "ready",
        "release_state": "active",
        "super_giant_task_gate": super_giant_task_gate,
        "remaining_super_giant": remaining_super_giant,
        "system_memory_percent": system_memory_percent,
    }


def canonical(role: str, number: int = 1, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "kind": "canonical_authority",
        "shard_id": "canonical-integration",
        "canonical_authority": True,
        "global_integration_owner": True,
    }
    values.update(overrides)
    return dispatch_instance(role, number, **values)  # type: ignore[arg-type]


def worker(role: str, number: int, shard_id: str, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "kind": "office_worker_instance",
        "shard_id": shard_id,
        "canonical_authority": False,
        "global_integration_owner": False,
    }
    values.update(overrides)
    return dispatch_instance(role, number, **values)  # type: ignore[arg-type]


def trusted_manifest(entries: Sequence[dict[str, object]]) -> dict[str, dict[str, str]]:
    return {
        str(entry["instance_key"]): dict(TRUSTED_PRELOAD_BY_ROLE[str(entry["role"])])
        for entry in entries
    }


def validate(
    entries: Sequence[dict[str, object]],
    *,
    authority: str = "super",
    behavior: str = "parallel",
) -> object:
    return validate_dispatch_plan(
        list(entries),
        authority=authority,
        behavior=behavior,
        trusted_preload_manifest=trusted_manifest(entries),
    )


def check_missing_trusted_manifest_rejected() -> None:
    try:
        validate_dispatch_plan(
            [canonical("gongbu")],
            authority="super",
            behavior="parallel",
        )
    except ValueError as exc:
        require("exact_preload_contract_gate" in str(exc), f"unexpected missing-manifest gate: {exc!s}")
    else:
        raise AssertionError("dispatch plan passed without a trusted preload manifest")


def require_instance_contract(
    plan: object,
    *,
    expected_keys: Sequence[str],
    expected_priority: str,
) -> None:
    normalized = entries_of(plan)
    require(
        tuple(value(item, "instance_key") for item in normalized) == tuple(expected_keys),
        "validated plan did not preserve unique instance_key identity",
    )
    require(
        all(value(item, "scale_out_priority") == expected_priority for item in normalized),
        f"role did not derive scale_out_priority={expected_priority}",
    )
    require(
        sum(value(item, "canonical_authority") is True for item in normalized) == 1,
        "role must retain exactly one canonical authority",
    )
    require(
        sum(value(item, "global_integration_owner") is True for item in normalized) == 1,
        "role must retain exactly one integration owner",
    )


def check_ministry_workers_parallelize() -> None:
    plan = validate(
        [
            canonical("gongbu"),
            worker(
                "gongbu",
                2,
                "module-a",
                owned_paths=("src/module_a",),
                write_set=("src/module_a/worker.py", "tests/test_module_a.py"),
            ),
            worker(
                "gongbu",
                3,
                "module-b",
                owned_paths=("src/module_b",),
                write_set=("src/module_b/worker.py", "tests/test_module_b.py"),
            ),
        ]
    )
    require_instance_contract(
        plan,
        expected_keys=("gongbu#0001", "gongbu#0002", "gongbu#0003"),
        expected_priority="HIGHEST",
    )


def check_more_than_sixteen_distinct_ministry_instances() -> None:
    entries = [canonical("gongbu")]
    entries.extend(
        worker(
            "gongbu",
            index,
            f"module-{index:02d}",
            owned_paths=(f"src/module_{index:02d}",),
            write_set=(f"src/module_{index:02d}/worker.py",),
        )
        for index in range(2, 22)
    )
    plan = validate(entries)
    normalized = entries_of(plan)
    require(len(normalized) == 21, "total instance count above sixteen was rejected")
    require(
        len({value(item, "instance_key") for item in normalized}) == 21,
        "distinct instance identities were not preserved above sixteen",
    )


def check_three_department_affinity_is_lower() -> None:
    plan = validate(
        [
            canonical("zhongshu"),
            worker(
                "zhongshu",
                2,
                "research-source-b",
                owned_paths=("evidence/source-b",),
            ),
        ]
    )
    require_instance_contract(
        plan,
        expected_keys=("zhongshu#0001", "zhongshu#0002"),
        expected_priority="LOW",
    )


def check_shangshu_super_giant_deputy() -> None:
    common = {
        "super_giant_task_gate": "PASSED",
        "remaining_super_giant": True,
        "system_memory_percent": 70.0,
    }
    plan = validate(
        [
            canonical("shangshu", **common),
            worker("shangshu", 2, "portfolio-domain-b", **common),
        ]
    )
    require_instance_contract(
        plan,
        expected_keys=("shangshu#0001", "shangshu#0002"),
        expected_priority="EXTREMELY_LOW",
    )
    require(
        value(entries_of(plan)[0], "global_integration_owner") is True,
        "shangshu#0001 must remain the global integration owner",
    )


def check_supercc_extra_worker_stays_ordinary_non_visible() -> None:
    require_rejected(
        "native dispatch must remain non-visible",
        [
            canonical(
                "zhongshu",
                visibility="visible_core",
                runtime_family="visible_zellij_squad",
            ),
            worker("zhongshu", 2, "research-source-b"),
        ],
    )


def check_pressure_allows_only_degraded_canonical_shape() -> None:
    plan = validate(
        [
            canonical(
                "gongbu",
                remaining_super_giant=False,
                system_memory_percent=99.0,
            )
        ]
    )
    require(len(entries_of(plan)) == 1, "degraded topology must retain only the canonical office")


def require_rejected(
    gate: str,
    entries: Sequence[dict[str, object]],
) -> None:
    try:
        validate(entries)
    except ValueError as exc:
        require(gate in str(exc), f"expected {gate}, got {exc!s}")
    else:
        raise AssertionError(f"invalid multi-instance plan bypassed {gate}")


def rejection_check(
    gate: str,
    entries: Sequence[dict[str, object]],
) -> Callable[[], None]:
    def check() -> None:
        require_rejected(gate, entries)

    return check


def rejection_checks() -> tuple[tuple[str, Callable[[], None]], ...]:
    duplicate_instance = worker("gongbu", 3, "module-b")
    duplicate_instance["instance_key"] = "gongbu#0002"
    missing_preload_ack = worker("gongbu", 2, "preload-missing")
    missing_preload_ack["preload_ack"] = ""
    invalid_profile_hash = worker("gongbu", 2, "profile-hash-invalid")
    invalid_profile_hash["profile_hash"] = "not-a-sha256"
    missing_dossier_hash = worker("gongbu", 2, "dossier-hash-missing")
    missing_dossier_hash["dossier_hash"] = ""
    missing_court_skill_hash = worker("gongbu", 2, "court-skill-hash-missing")
    missing_court_skill_hash["court_skill_hash"] = ""
    random_profile_hash = worker("gongbu", 2, "profile-hash-random")
    random_profile_hash["profile_hash"] = "0" * 64
    random_dossier_hash = worker("gongbu", 2, "dossier-hash-random")
    random_dossier_hash["dossier_hash"] = "f" * 64
    random_court_skill_hash = worker("gongbu", 2, "court-skill-hash-random")
    random_court_skill_hash["court_skill_hash"] = "a" * 64
    wrong_profile_path = worker("gongbu", 2, "profile-path-wrong")
    wrong_profile_path["profile_path"] = "agents/standing-officials/menxia.toml"
    wrong_dossier_path = worker("gongbu", 2, "dossier-path-wrong")
    wrong_dossier_path["dossier_path"] = "../outside/AGENTS.md"
    wrong_skill_path = worker("gongbu", 2, "skill-path-wrong")
    wrong_skill_path["skill_path"] = "references/SKILL.md"
    cases: tuple[
        tuple[str, str, Sequence[dict[str, object]], str], ...
    ] = (
        (
            "reject_second_taizi",
            "single_taizi_gate",
            [canonical("taizi"), worker("taizi", 2, "second-user-entry")],
            "super并行",
        ),
        (
            "reject_second_canonical_authority",
            "canonical_authority_uniqueness_gate",
            [
                canonical("gongbu"),
                canonical(
                    "gongbu",
                    2,
                    shard_id="second-canonical",
                    global_integration_owner=False,
                ),
            ],
            "super并行",
        ),
        (
            "reject_duplicate_instance_key",
            "office_worker_instance_identity_gate",
            [canonical("gongbu"), worker("gongbu", 2, "module-a"), duplicate_instance],
            "super并行",
        ),
        (
            "reject_duplicate_shard",
            "assignment_ownership_and_write_set_gate",
            [
                canonical("gongbu"),
                worker("gongbu", 2, "same-shard", write_set=("src/a.py",)),
                worker("gongbu", 3, "same-shard", write_set=("src/b.py",)),
            ],
            "super并行",
        ),
        (
            "reject_duplicate_task",
            "assignment_ownership_and_write_set_gate",
            [
                canonical("gongbu"),
                worker(
                    "gongbu",
                    2,
                    "module-a",
                    task_id="task-shared",
                    write_set=("src/a.py",),
                ),
                worker(
                    "gongbu",
                    3,
                    "module-b",
                    task_id="task-shared",
                    write_set=("src/b.py",),
                ),
            ],
            "super并行",
        ),
        (
            "reject_overlapping_write_set",
            "assignment_ownership_and_write_set_gate",
            [
                canonical("gongbu"),
                worker("gongbu", 2, "module-a", write_set=("src/shared.py",)),
                worker("gongbu", 3, "module-b", write_set=("src/shared.py",)),
            ],
            "super并行",
        ),
        (
            "reject_missing_integration_owner",
            "single_integration_owner_gate",
            [
                worker("gongbu", 2, "module-a", write_set=("src/a.py",)),
                worker("gongbu", 3, "module-b", write_set=("src/b.py",)),
            ],
            "super并行",
        ),
        (
            "reject_non_super_giant_shangshu_deputy",
            "super_giant_shangshu_scale_gate",
            [canonical("shangshu"), worker("shangshu", 2, "portfolio-domain-b")],
            "super并行",
        ),
        (
            "reject_second_global_integration_owner",
            "single_integration_owner_gate",
            [
                canonical(
                    "shangshu",
                    super_giant_task_gate="PASSED",
                    remaining_super_giant=True,
                ),
                worker(
                    "shangshu",
                    2,
                    "portfolio-domain-b",
                    global_integration_owner=True,
                    super_giant_task_gate="PASSED",
                    remaining_super_giant=True,
                ),
            ],
            "super并行",
        ),
        (
            "reject_scale_after_super_giant_ends",
            "super_giant_scale_reassessment_gate",
            [
                canonical(
                    "shangshu",
                    super_giant_task_gate="PASSED",
                    remaining_super_giant=False,
                ),
                worker(
                    "shangshu",
                    2,
                    "portfolio-domain-b",
                    super_giant_task_gate="PASSED",
                    remaining_super_giant=False,
                ),
            ],
            "super并行",
        ),
        (
            "reject_scale_at_99_percent_memory",
            "system_memory_pressure_downgrade_gate",
            [
                canonical("gongbu", remaining_super_giant=True, system_memory_percent=99.0),
                worker(
                    "gongbu",
                    2,
                    "module-a",
                    remaining_super_giant=True,
                    system_memory_percent=99.0,
                ),
            ],
            "super并行",
        ),
        (
            "reject_second_supercc_visible_canonical",
            "native dispatch must remain non-visible",
            [
                canonical(
                    "zhongshu",
                    visibility="visible_core",
                    runtime_family="visible_zellij_squad",
                ),
                worker(
                    "zhongshu",
                    2,
                    "research-source-b",
                    visibility="visible_core",
                    runtime_family="visible_zellij_squad",
                ),
            ],
            "superCC",
        ),
        (
            "reject_missing_preload_ack",
            "exact_preload_contract_gate",
            [canonical("gongbu"), missing_preload_ack],
            "super并行",
        ),
        (
            "reject_invalid_profile_hash",
            "exact_preload_contract_gate",
            [canonical("gongbu"), invalid_profile_hash],
            "super并行",
        ),
        (
            "reject_missing_dossier_hash",
            "exact_preload_contract_gate",
            [canonical("gongbu"), missing_dossier_hash],
            "super并行",
        ),
        (
            "reject_missing_court_skill_hash",
            "exact_preload_contract_gate",
            [canonical("gongbu"), missing_court_skill_hash],
            "super并行",
        ),
        (
            "reject_random_profile_hash",
            "exact_preload_contract_gate",
            [canonical("gongbu"), random_profile_hash],
            "super并行",
        ),
        (
            "reject_random_dossier_hash",
            "exact_preload_contract_gate",
            [canonical("gongbu"), random_dossier_hash],
            "super并行",
        ),
        (
            "reject_random_court_skill_hash",
            "exact_preload_contract_gate",
            [canonical("gongbu"), random_court_skill_hash],
            "super并行",
        ),
        (
            "reject_wrong_profile_path",
            "exact_preload_contract_gate",
            [canonical("gongbu"), wrong_profile_path],
            "super并行",
        ),
        (
            "reject_wrong_dossier_path",
            "exact_preload_contract_gate",
            [canonical("gongbu"), wrong_dossier_path],
            "super并行",
        ),
        (
            "reject_wrong_skill_path",
            "exact_preload_contract_gate",
            [canonical("gongbu"), wrong_skill_path],
            "super并行",
        ),
    )
    return tuple(
        (name, rejection_check(gate, entries))
        for name, gate, entries, _mode in cases
    )


def run_case(name: str, check: Callable[[], None]) -> dict[str, object]:
    try:
        check()
    except Exception as exc:  # RED aggregation must expose every missing gate.
        return {
            "case": name,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    return {"case": name, "ok": True}


def _run_checks() -> int:
    positive_checks: tuple[tuple[str, Callable[[], None]], ...] = (
        ("missing_trusted_manifest_rejected", check_missing_trusted_manifest_rejected),
        ("ministry_workers_parallelize", check_ministry_workers_parallelize),
        ("more_than_sixteen_distinct_ministry_instances", check_more_than_sixteen_distinct_ministry_instances),
        ("three_department_affinity_lower", check_three_department_affinity_is_lower),
        ("shangshu_super_giant_deputy", check_shangshu_super_giant_deputy),
        ("supercc_worker_non_visible", check_supercc_extra_worker_stays_ordinary_non_visible),
        ("pressure_degraded_canonical_shape", check_pressure_allows_only_degraded_canonical_shape),
    )
    checks = positive_checks + rejection_checks()
    results = [run_case(name, check) for name, check in checks]
    failures = [item for item in results if item["ok"] is False]
    payload: dict[str, Any] = {
        "ok": not failures,
        "schema": "court.multi_instance_dispatch.check.v1",
        "red_expected_until_green": False,
        "results": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


def main() -> int:
    with TemporaryDirectory(prefix="court-preload-fixture-") as temp_dir:
        _initialize_preload_fixture(Path(temp_dir))
        return _run_checks()


if __name__ == "__main__":
    raise SystemExit(main())
