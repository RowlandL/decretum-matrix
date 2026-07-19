"""Validate governance-neutral framework and Shiguan GBrain contracts."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Callable

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ID = "three-departments-six-ministries"
DIRECT_REVIEW_ID = "direct-review"
COURT_ROLE_TOKENS = {
    "taizi",
    "zhongshu",
    "menxia",
    "shangshu",
    "libu-hr",
    "hubu",
    "libu",
    "bingbu",
    "xingbu",
    "gongbu",
    "shiguan",
}


def _load_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        raise AssertionError(f"required_module_missing:{name}") from exc


def _check_registry_and_dispatch() -> list[str]:
    framework = _load_module("governance_framework")
    registry = framework.load_governance_registry(ROOT)
    assert framework.DEFAULT_GOVERNANCE_ID == DEFAULT_ID
    assert registry["schema"] == "decretum.governance.registry.v1"
    assert registry["default_id"] == DEFAULT_ID

    implementations = registry["implementations"]
    assert set(implementations) == {DEFAULT_ID, DIRECT_REVIEW_ID}
    official = implementations[DEFAULT_ID]
    direct = implementations[DIRECT_REVIEW_ID]
    assert official.status == "default"
    assert direct.status == "reference"
    assert official.framework_services == {
        "state": "court-runtime",
        "evidence": "court-runtime",
        "memory": "shiguan-gbrain",
    }
    assert direct.framework_services == official.framework_services

    required_capabilities = {
        "intake",
        "interpretation",
        "ruling",
        "coordination",
        "action",
        "validation",
        "presentation",
    }
    assert set(official.capability_bindings) == required_capabilities
    assert set(direct.capability_bindings) == required_capabilities

    positive = (
        ("user", "coordinator", "user", "entry"),
        ("coordinator", "reviewer", "coordinator", "review"),
        ("coordinator", "executor", "coordinator", "execution"),
    )
    for caller, target, superior, edge_class in positive:
        decision = framework.evaluate_dispatch(
            direct,
            caller=caller,
            target=target,
            target_direct_superior=superior,
        )
        assert decision.allowed is True
        assert decision.edge_class == edge_class
        assert decision.reason_codes == ()

    rejected = framework.evaluate_dispatch(
        direct,
        caller="reviewer",
        target="executor",
        target_direct_superior="coordinator",
    )
    assert rejected.allowed is False
    assert rejected.edge_class is None
    assert rejected.reason_codes == ("governance_edge_forbidden",)

    direct_path = ROOT / "references" / "manifests" / "direct-review-governance.v1.json"
    direct_text = direct_path.read_text(encoding="utf-8").casefold()
    leaked = sorted(token for token in COURT_ROLE_TOKENS if token in direct_text)
    assert not leaked, f"direct_review_court_role_leak:{','.join(leaked)}"
    return [
        "registry_unique_default",
        "framework_authority_reuse",
        "direct_review_dispatch",
        "direct_review_deny_by_default",
        "direct_review_role_neutrality",
    ]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _semantic_trace(governance_id: str, actors: dict[str, str]) -> list[dict[str, object]]:
    base = {
        "schema": "decretum.semantic.record.v1",
        "scope": "fixture/task-1",
        "valid_from": "2026-07-19T10:00:00+08:00",
        "governance_id": governance_id,
        "execution_authority": False,
    }

    def record(
        record_id: str,
        kind: str,
        subject: str,
        actor: str,
        basis: list[str],
        authority: str,
        *,
        execution_authority: bool = False,
    ) -> dict[str, object]:
        return {
            **base,
            "record_id": record_id,
            "kind": kind,
            "subject": subject,
            "actor": actor,
            "basis": basis,
            "authority": authority,
            "content_sha256": _digest(record_id),
            "execution_authority": execution_authority,
        }

    return [
        record("decree", "fact", "latest_user_decree", "user", [], "controlling"),
        record("observed", "fact", "runtime_state", "runtime", ["decree"], "evidence"),
        record(
            "interpretation",
            "interpretation",
            "task_intent",
            actors["interpretation"],
            ["decree", "observed"],
            "derived",
        ),
        record(
            "ruling",
            "ruling",
            "approved_boundary",
            actors["ruling"],
            ["decree", "interpretation"],
            "derived",
        ),
        record(
            "action",
            "action",
            "bounded_change",
            actors["action"],
            ["ruling"],
            "current_task",
            execution_authority=True,
        ),
        record(
            "validation",
            "validation",
            "acceptance_result",
            actors["validation"],
            ["observed", "action"],
            "evidence",
        ),
        record(
            "memory",
            "memory",
            "future_recall",
            "shiguan-gbrain",
            ["decree", "validation"],
            "advisory",
        ),
        record(
            "presentation",
            "presentation",
            "user_report",
            actors["presentation"],
            ["ruling", "validation"],
            "derived",
        ),
    ]


def _check_semantic_trace() -> list[str]:
    framework = _load_module("governance_framework")
    registry = framework.load_governance_registry(ROOT)
    implementations = registry["implementations"]
    actor_sets = {
        DEFAULT_ID: {
            "interpretation": "zhongshu",
            "ruling": "menxia",
            "action": "gongbu",
            "validation": "menxia",
            "presentation": "taizi",
        },
        DIRECT_REVIEW_ID: {
            "interpretation": "coordinator",
            "ruling": "reviewer",
            "action": "executor",
            "validation": "reviewer",
            "presentation": "coordinator",
        },
    }
    for implementation_id, actors in actor_sets.items():
        result = framework.validate_semantic_trace(
            _semantic_trace(implementation_id, actors),
            implementations[implementation_id],
        )
        assert result["gate"] == "PASSED", result["errors"]
        assert result["record_count"] == 8

    direct = implementations[DIRECT_REVIEW_ID]
    valid = _semantic_trace(DIRECT_REVIEW_ID, actor_sets[DIRECT_REVIEW_ID])
    cases: list[tuple[str, list[dict[str, object]], str]] = []

    no_decree = deepcopy(valid)
    no_decree.pop(0)
    cases.append(("latest_decree", no_decree, "latest_user_decree_missing"))

    interpretation_without_fact = deepcopy(valid)
    interpretation_without_fact[2]["basis"] = []
    cases.append(
        (
            "interpretation_basis",
            interpretation_without_fact,
            "basis_kind_missing:interpretation:fact",
        )
    )

    action_without_ruling = deepcopy(valid)
    action_without_ruling[4]["basis"] = ["interpretation"]
    cases.append(("action_basis", action_without_ruling, "basis_kind_missing:action:ruling"))

    memory_exec = deepcopy(valid)
    memory_exec[6]["execution_authority"] = True
    cases.append(("memory_authority", memory_exec, "memory_execution_authority_forbidden"))

    wrong_actor = deepcopy(valid)
    wrong_actor[3]["actor"] = "executor"
    cases.append(("actor_capability", wrong_actor, "actor_capability_mismatch:ruling"))

    invalid_window = deepcopy(valid)
    invalid_window[6]["valid_until"] = "2026-07-18T10:00:00+08:00"
    cases.append(("validity_window", invalid_window, "validity_window_invalid:memory"))

    for name, trace, expected in cases:
        result = framework.validate_semantic_trace(trace, direct)
        assert result["gate"] == "FAILED", f"negative_case_passed:{name}"
        assert expected in result["errors"], f"negative_reason_missing:{name}:{result['errors']}"
    return [
        "official_semantic_trace",
        "direct_review_semantic_trace",
        "latest_decree_precedence",
        "semantic_basis_chain",
        "semantic_actor_authority",
        "memory_no_execution_authority",
        "semantic_validity_window",
    ]


def _check_gbrain() -> list[str]:
    gbrain = _load_module("shiguan_gbrain")
    query = _load_module("query_shiguan_index")
    entries = [
        {
            "record_uid": "r-current",
            "time": "2026-07-19T11:00:00+08:00",
            "topic": "governance",
            "keywords": ["adapter"],
            "summary": "current governance adapter evidence",
            "source": "references/plan-archives/current.md",
            "evidence": "sha256:current",
            "memory_decision": "WRITE",
            "valid_from": "2026-07-01T00:00:00+08:00",
            "valid_until": "2026-08-01T00:00:00+08:00",
            "memory_content": "private body must not be projected",
        },
        {
            "record_uid": "r-expired",
            "time": "2026-06-19T11:00:00+08:00",
            "topic": "governance",
            "keywords": ["adapter", "framework"],
            "summary": "historical conflicting adapter evidence",
            "source": "references/plan-archives/historical.md",
            "evidence": "sha256:historical",
            "memory_decision": "PROPOSE",
            "valid_from": "2026-05-01T00:00:00+08:00",
            "valid_until": "2026-07-01T00:00:00+08:00",
            "conflict_state": "conflicts_with_current_decree",
            "raw_body": "must not be projected",
        },
        {
            "record_uid": "r-unrelated",
            "time": "2026-07-19T11:30:00+08:00",
            "topic": "unrelated",
            "keywords": ["other"],
            "summary": "not selected",
            "source": "references/plan-archives/other.md",
        },
    ]
    terms = ["governance", "adapter"]
    legacy_order = [item["record_uid"] for item in query.select_matches(deepcopy(entries), terms)]
    assert legacy_order == ["r-current", "r-expired"]
    assert [item["record_uid"] for item in gbrain.select_matches(deepcopy(entries), terms)] == legacy_order
    assert [gbrain.score_entry(item, terms) for item in entries[:2]] == [13, 11]

    common = {
        "entries": deepcopy(entries),
        "terms": terms,
        "current_decree_sha256": _digest("decree"),
        "as_of": "2026-07-19T12:00:00+08:00",
        "limit": 5,
        "memory_git_provenance": {
            "schema": "decretum.gbrain.memory_git_provenance.v1",
            "registry_available": True,
            "migration_links_verified": True,
            "managed_store_count": 3,
            "shared_registry_commit": "a" * 40,
            "transaction_id": "fixture-transaction-001",
            "stores": [
                {
                    "memory_store_id": "codex-native-memory",
                    "tool_class": "codex",
                    "memory_state": "present",
                    "native_commit": "b" * 40,
                    "shared_commit": "c" * 40,
                    "transaction_id": "fixture-transaction-001",
                    "native_root": "must-not-leak",
                }
            ],
        },
    }
    official = gbrain.build_recall_context(governance_id=DEFAULT_ID, **common)
    direct = gbrain.build_recall_context(governance_id=DIRECT_REVIEW_ID, **common)
    assert official["schema"] == "decretum.gbrain.recall.v1"
    assert official["authority"] == "advisory"
    assert official["execution_authority"] is False
    assert official["current_decree_precedence"] is True
    assert [item["record_uid"] for item in official["matches"]] == legacy_order
    assert official["matches"][0]["applicability"] == "current"
    assert official["matches"][1]["applicability"] == "historical"
    assert official["matches"][1]["conflict"] == "preserved"
    assert all("memory_content" not in item and "raw_body" not in item for item in official["matches"])
    assert official["memory_git"]["migration_links_verified"] is True
    assert official["memory_git"]["managed_store_count"] == 3
    assert official["memory_git"]["stores"][0]["memory_store_id"] == "codex-native-memory"
    assert "native_root" not in json.dumps(official["memory_git"], ensure_ascii=False)
    official_without_id = {key: value for key, value in official.items() if key != "governance_id"}
    direct_without_id = {key: value for key, value in direct.items() if key != "governance_id"}
    assert official_without_id == direct_without_id
    return [
        "gbrain_query_compatibility",
        "gbrain_metadata_only_recall",
        "gbrain_advisory_authority",
        "gbrain_current_decree_precedence",
        "gbrain_applicability",
        "gbrain_conflict_preservation",
        "gbrain_memory_git_provenance",
        "gbrain_memory_git_path_privacy",
        "gbrain_cross_governance_continuity",
    ]


def _check_official_adapter() -> list[str]:
    framework = _load_module("governance_framework")
    hierarchy = _load_module("court_dispatch_hierarchy")
    calls: list[tuple[str, str, str, str]] = []
    original = framework.evaluate_dispatch

    def spy(
        implementation,
        *,
        caller: str,
        target: str,
        target_direct_superior: str,
    ):
        calls.append(
            (
                implementation.implementation_id,
                caller,
                target,
                target_direct_superior,
            )
        )
        return original(
            implementation,
            caller=caller,
            target=target,
            target_direct_superior=target_direct_superior,
        )

    framework.evaluate_dispatch = spy
    try:
        decision = hierarchy.validate_dispatch_hierarchy(
            action="dispatch",
            calling_office="user",
            target_role="taizi",
            target_direct_superior="user",
            instance_kind="canonical_authority",
            canonical_authority=True,
        )
    finally:
        framework.evaluate_dispatch = original
    assert decision.allowed is True
    assert decision.edge_class == "court_entry"
    assert calls == [(DEFAULT_ID, "user", "taizi", "user")], f"official_adapter_calls:{calls}"
    return [
        "official_adapter_generic_dispatch",
        "official_adapter_result_compatibility",
    ]


def _check_release_gate_registration() -> list[str]:
    release_manifest = _load_module("release_gate_manifest")
    release_check = _load_module("check_release_gate")
    manifest = release_manifest.load_release_manifest()
    steps = manifest["steps"]
    names = [step["name"] for step in steps]
    release_metadata_index = names.index("release_metadata")
    federation_index = names.index("shiguan_git_federation")
    framework_index = names.index("governance_framework")
    hierarchy_index = names.index("court_dispatch_hierarchy")
    assert release_metadata_index + 1 == federation_index
    assert federation_index + 1 == framework_index
    assert framework_index + 1 == hierarchy_index
    assert steps[release_metadata_index] == {
        "name": "release_metadata",
        "gate_class": "source",
        "command": ["$PYTHON", "scripts/check_release_metadata.py", "--json"],
        "timeout": 120,
        "condition": "always",
        "allowed_returncodes": [0],
    }
    assert steps[federation_index] == {
        "name": "shiguan_git_federation",
        "gate_class": "source",
        "command": ["$PYTHON", "scripts/check_shiguan_git_federation.py", "--json"],
        "timeout": 180,
        "condition": "always",
        "allowed_returncodes": [0],
    }
    assert steps[framework_index] == {
        "name": "governance_framework",
        "gate_class": "source",
        "command": ["$PYTHON", "scripts/check_governance_framework.py", "--json"],
        "timeout": 120,
        "condition": "always",
        "allowed_returncodes": [0],
    }
    cases = release_check.run_hierarchy_release_gate_self_test(manifest)
    expected = {
        f"{prefix}_{case}"
        for prefix in ("governance_framework", "court_dispatch_hierarchy")
        for case in (
            "missing",
            "renamed",
            "reordered",
            "outside_source_phase",
            "conditionalized",
            "wrong_command",
        )
    }
    assert set(cases) == expected, f"release_manifest_self_test_cases:{cases}"
    return [
        "governance_release_gate_mandatory",
        "governance_release_gate_order",
        "governance_release_gate_tamper_detection",
        "release_metadata_gate_mandatory",
        "shiguan_git_federation_gate_mandatory",
    ]


def _check_documentation_contract() -> list[str]:
    paths = [
        "SKILL.md",
        "README.md",
        "docs/wiki/Architecture.md",
        "docs/wiki/Governance.md",
        "references/court-core-contract.md",
        "references/court-shiguan-memory.md",
        "references/court-offices-dispatch.md",
        "CHANGELOG.md",
        "RELEASE-LOG.md",
        "docs/logs/2026-07-19-beta1.0.0.md",
    ]
    texts = {path: (ROOT / path).read_text(encoding="utf-8") for path in paths}
    canonical_terms = (
        "通用任务治理框架",
        "史馆 GBrain",
        "治理实现",
        "能力与运行适配层",
        "呈现层",
    )
    architecture = texts["docs/wiki/Architecture.md"]
    for term in canonical_terms:
        assert term in architecture, f"architecture_term_missing:{term}"
    assert "three-departments-six-ministries" in architecture
    assert "direct-review" in architecture
    assert "decretum.semantic.record.v1" in architecture
    assert "decretum.gbrain.recall.v1" in architecture

    skill = texts["SKILL.md"]
    assert "governance-implementations.v1.json" in skill
    assert "史馆 GBrain" in skill and "不取得当前任务执行权" in skill
    assert "scripts/check_governance_framework.py" in skill
    understanding_terms = (
        "目标、使用场景、关键要求和验收标准",
        "95",
        "一次只问一个",
        "2–4",
        "简要复述",
        "不强行提问",
    )
    for term in understanding_terms:
        assert term in skill, f"understanding_language_missing:{term}"
    assert "court.request_understanding.v1" in texts["references/court-core-contract.md"]

    joined = "\n".join(texts.values())
    for term in canonical_terms:
        assert term in joined
    assert "最新用户旨意" in joined
    assert "published baseline" in joined or "已发布基线" in joined
    assert "Latest" in joined
    assert "覆盖" in joined and ("尚未" in joined or "不冒充" in joined)
    assert "OFFICE_PACK_Q1_Q8" in texts["docs/logs/2026-07-19-beta1.0.0.md"]
    for forbidden in ("TBD", "TODO", "beta0.5.14", "SECOND_STATE", "SECOND_LEDGER"):
        assert forbidden not in joined, f"formal_language_forbidden:{forbidden}"
    return [
        "canonical_architecture_language",
        "governance_boundary_documented",
        "gbrain_authority_documented",
        "official_default_documented",
        "reference_replacement_documented",
        "understanding_sufficiency_documented",
        "published_baseline_and_coverage_boundary",
        "semantic_cleanliness",
    ]


def _check_understanding_gate() -> list[str]:
    intake = _load_module("court_intake_gate")
    direct = {
        "schema": "court.request_understanding.v1",
        "score": 98,
        "threshold": 95,
        "dimensions": {
            "goal": "CLEAR",
            "usage_scenario": "CLEAR",
            "key_requirements": "CLEAR",
            "acceptance_criteria": "CLEAR",
        },
        "route": "DIRECT_EXECUTION",
        "question_target": "NONE",
        "question": "",
        "options": [],
        "restatement": "目标、场景、要求和验收标准已经明确。",
        "confirmation_required": False,
    }
    normalized = intake.validate_request_understanding(deepcopy(direct))
    assert normalized == direct

    confirm = deepcopy(direct)
    confirm.update(
        route="RESTATE_CONFIRM",
        question_target="CONFIRMATION",
        question="以上理解是否有偏差？",
        confirmation_required=True,
    )
    assert intake.validate_request_understanding(confirm)["route"] == "RESTATE_CONFIRM"

    clarify = deepcopy(direct)
    clarify.update(
        score=82,
        route="SINGLE_QUESTION",
        question_target="acceptance_criteria",
        question="最终以哪一项结果作为验收标准？",
        options=["通过自动化检查", "完成本机安装", "取得外部发布回执"],
        restatement="",
    )
    clarify["dimensions"]["acceptance_criteria"] = "MISSING"
    assert intake.validate_request_understanding(clarify)["route"] == "SINGLE_QUESTION"

    def rejected(value: dict[str, object], expected: str) -> None:
        try:
            intake.validate_request_understanding(value)
        except ValueError as exc:
            assert str(exc) == expected, f"understanding_error:{exc}:{expected}"
        else:
            raise AssertionError(f"understanding_negative_case_passed:{expected}")

    low_direct = deepcopy(clarify)
    low_direct.update(route="DIRECT_EXECUTION", question_target="NONE", question="", options=[])
    rejected(low_direct, "understanding_below_threshold_requires_question")

    too_many_questions = deepcopy(clarify)
    too_many_questions["question"] = "目标是什么？验收是什么？"
    rejected(too_many_questions, "understanding_single_question_required")

    one_option = deepcopy(clarify)
    one_option["options"] = ["只选这一项"]
    rejected(one_option, "understanding_option_count")

    unclear_direct = deepcopy(direct)
    unclear_direct["dimensions"]["usage_scenario"] = "PARTIAL"
    rejected(unclear_direct, "understanding_clear_dimensions_required")

    example = intake.minimal_formal_task_example()
    assert intake.require_new_formal_task_gate(example)["understanding"]["score"] >= 95
    confirmation_pending = deepcopy(example)
    confirmation_pending["understanding"] = confirm
    try:
        intake.require_new_formal_task_gate(confirmation_pending)
    except ValueError as exc:
        assert str(exc) == "formal_understanding_confirmation_pending"
    else:
        raise AssertionError("formal_task_created_before_understanding_confirmation")
    without_understanding = deepcopy(example)
    without_understanding.pop("understanding")
    try:
        intake.require_new_formal_task_gate(without_understanding)
    except ValueError as exc:
        assert str(exc) == "formal_understanding_required"
    else:
        raise AssertionError("formal_understanding_missing_accepted")
    return [
        "understanding_four_dimensions",
        "understanding_threshold_95",
        "understanding_single_high_value_question",
        "understanding_two_to_four_options",
        "understanding_restatement_confirmation",
        "understanding_confirmation_precedes_task_creation",
        "understanding_clear_request_direct_execution",
        "formal_task_understanding_required",
    ]


CHECKS: dict[str, Callable[[], list[str]]] = {
    "registry-dispatch": _check_registry_and_dispatch,
    "semantic-trace": _check_semantic_trace,
    "gbrain": _check_gbrain,
    "official-adapter": _check_official_adapter,
    "release-registration": _check_release_gate_registration,
    "documentation": _check_documentation_contract,
    "understanding": _check_understanding_gate,
}


def evaluate(only: str | None = None) -> dict[str, object]:
    selected = [only] if only else list(CHECKS)
    passed: list[str] = []
    errors: list[str] = []
    for name in selected:
        check = CHECKS.get(name)
        if check is None:
            errors.append(f"unknown_check:{name}")
            continue
        try:
            passed.extend(check())
        except (AssertionError, AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
            errors.append(f"{name}:{exc}")
    return {
        "schema": "decretum.governance_framework_gate.v1",
        "gate": "PASSED" if not errors else "FAILED",
        "SEMANTIC_CLEANLINESS_GATE": (
            "PASS" if "semantic_cleanliness" in passed else "NOT_EVALUATED"
        ),
        "checks": passed,
        "check_count": len(passed),
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=sorted(CHECKS))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate(args.only)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"GOVERNANCE_FRAMEWORK_{result['gate']} "
            f"checks={result['check_count']} errors={len(result['errors'])}"
        )
        for error in result["errors"]:
            print(error)
    return 0 if result["gate"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
