"""Validate structured court result semantics for recruitment responses."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

sys.dont_write_bytecode = True

import court_result_semantics


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "references" / "fixtures" / "response-draft-families.json"
REQUIRED_FAMILIES = [
    "dispatch_local_candidate",
    "ask_user_create_skill",
    "continue_after_user_rejects",
    "discovery_authority_blocked",
    "discovery_failed_without_no-candidate_claim",
    "handoff_with_concerns",
    "partial_result",
    "verified_done",
]

INCONCLUSIVE_DISCOVERY_CONCLUSIONS = {
    "UNKNOWN",
    "NOT_EVALUATED",
    "AUTHORITY_BLOCKED",
    "DISCOVERY_FAILED",
}


def _error(errors: list[str], family: str, message: str) -> None:
    errors.append(f"{family}:{message}")


def _draft_fields(draft: str) -> tuple[dict[str, str], list[str]]:
    fields: dict[str, str] = {}
    duplicates: list[str] = []
    for line in (line.strip() for line in draft.splitlines() if line.strip()):
        label, separator, value = line.partition("：")
        if separator != "：":
            continue
        key = label + separator
        if key in fields:
            duplicates.append(key)
        fields[key] = value.strip()
    return fields, duplicates


def _enum(value: str) -> str:
    return value.replace(";", "；").split("；", 1)[0].strip()


def _claims_candidate_absence(draft: str) -> bool:
    claim_text = draft.replace("不能据此断言不存在候选", "")
    chinese_claim = re.search(
        r"(?:已)?确认(?:不存在|没有|无)(?:可用|合格)?候选|不存在候选|没有候选|无候选",
        claim_text,
    )
    return bool(chinese_claim) or any(
        term in claim_text.casefold()
        for term in ("confirmed no candidate", "no candidate exists")
    )


def _validate(family: str, semantics: dict[str, Any], errors: list[str], draft: str = "") -> None:
    status = semantics.get("status")
    completion = semantics.get("completion")
    assessment = semantics.get("assessment")
    receipt = semantics.get("checkpoint_receipt")
    if not isinstance(completion, dict):
        _error(errors, family, "missing_completion")
        completion = {}
    if not isinstance(assessment, dict):
        _error(errors, family, "missing_assessment")
        assessment = {}
    if not isinstance(receipt, dict):
        _error(errors, family, "missing_checkpoint_receipt")
        receipt = {}

    if status == "DONE":
        if completion.get("verified") is not True:
            _error(errors, family, "done_requires_verified_completion")
        if receipt.get("verified") is not True or not receipt.get("evidence"):
            _error(errors, family, "done_requires_verified_checkpoint_receipt")
        if assessment.get("binding") != "PASSED":
            _error(errors, family, "done_requires_passed_assessment_binding")
    if status in {"HANDOFF", "PARTIAL"} and completion.get("rendered_completed") is not False:
        _error(errors, family, f"{status.lower()}_must_not_render_completed")

    discovery = semantics.get("discovery")
    if isinstance(discovery, dict):
        if discovery.get("status") in {"AUTHORITY_BLOCKED", "FAILED"} and discovery.get("no_candidate_exists") is not False:
            _error(errors, family, "inconclusive_discovery_cannot_claim_no_candidate")
        if discovery.get("no_candidate_exists") is False and discovery.get("conclusion") not in INCONCLUSIVE_DISCOVERY_CONCLUSIONS:
            _error(errors, family, "inconclusive_discovery_requires_allowed_conclusion")

    creation = semantics.get("creation")
    if isinstance(creation, dict):
        if creation.get("action") == "PROPOSE" and creation.get("performed") is not False:
            _error(errors, family, "creation_proposal_cannot_claim_performed")

    user_decision = semantics.get("user_decision")
    original_task = semantics.get("original_task")
    if isinstance(user_decision, dict) and user_decision.get("status") == "REJECTED":
        if not isinstance(original_task, dict) or original_task.get("continues") is not True:
            _error(errors, family, "user_rejection_must_continue_original_task")

    fields, duplicates = _draft_fields(draft)
    if duplicates:
        _error(errors, family, f"duplicate_draft_labels:{','.join(duplicates)}")
    if family == "verified_done":
        if _enum(fields.get("结诏：", "")) != "DONE" or _enum(fields.get("状态：", "")) != "DONE":
            _error(errors, family, "done_draft_status_mismatch")
        if _enum(fields.get("完成核验：", "")) != "VERIFIED":
            _error(errors, family, "done_draft_completion_mismatch")
        evidence = fields.get("验收证据：", "")
        receipt_evidence = str(receipt.get("evidence") or "")
        if _enum(evidence) != "VERIFIED" or not receipt_evidence or receipt_evidence not in evidence:
            _error(errors, family, "done_draft_checkpoint_evidence_mismatch")
    elif family == "ask_user_create_skill":
        if _enum(fields.get("状态：", "")) != "NEEDS_CONTEXT" or _enum(fields.get("建议动作：", "")) != "PROPOSE_CREATE_SKILL":
            _error(errors, family, "proposal_draft_field_mismatch")
        if creation.get("performed") is False and any(term in draft.casefold() for term in ("已创建", "已经创建", "创建完成", "created", "performed")):
            _error(errors, family, "proposal_draft_claims_creation_performed")
    elif family == "continue_after_user_rejects":
        if _enum(fields.get("用户决定：", "")) != "REJECTED" or _enum(fields.get("原任务：", "")) != "CONTINUES":
            _error(errors, family, "rejection_draft_field_mismatch")
        if original_task.get("continues") is True and any(term in draft.casefold() for term in ("abandoned", "cancel", "no longer", "已取消", "不再继续", "放弃原任务")):
            _error(errors, family, "rejection_draft_abandons_original_task")
    elif family == "discovery_authority_blocked":
        if _enum(fields.get("太子回奏：", "")) != "authority_blocked" or _enum(fields.get("状态：", "")) != "BLOCKED":
            _error(errors, family, "authority_blocked_draft_field_mismatch")
        draft_conclusion = _enum(fields.get("发现结论：", ""))
        if draft_conclusion != discovery.get("conclusion") or draft_conclusion != "AUTHORITY_BLOCKED":
            _error(errors, family, "authority_blocked_discovery_conclusion_mismatch")
        if discovery.get("no_candidate_exists") is False and _claims_candidate_absence(draft):
            _error(errors, family, "authority_blocked_draft_claims_no_candidate")
    elif family == "discovery_failed_without_no-candidate_claim":
        draft_conclusion = _enum(fields.get("发现结论：", ""))
        if draft_conclusion != discovery.get("conclusion") or draft_conclusion != "DISCOVERY_FAILED":
            _error(errors, family, "discovery_failed_conclusion_mismatch")
        if discovery.get("no_candidate_exists") is False and _claims_candidate_absence(draft):
            _error(errors, family, "discovery_failed_draft_claims_no_candidate")


def evaluate(root: Path | None = None) -> dict[str, object]:
    errors: list[str] = []
    path = (root or ROOT) / "references" / "fixtures" / "response-draft-families.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        data = {}
        errors.append(f"fixture_load:{exc}")
    fixtures = data.get("families", []) if isinstance(data, dict) else []
    by_family: dict[str, dict[str, Any]] = {}
    if not isinstance(fixtures, list):
        errors.append("families_not_list")
        fixtures = []
    for item in fixtures:
        if isinstance(item, dict) and isinstance(item.get("family"), str):
            family = item["family"]
            if family in by_family:
                errors.append(f"{family}:duplicate")
            by_family[family] = item
    for family in REQUIRED_FAMILIES:
        item = by_family.get(family)
        if item is None:
            errors.append(f"{family}:missing")
            continue
        semantics = item.get("semantics")
        if not isinstance(semantics, dict):
            errors.append(f"{family}:missing_semantics")
            continue
        draft = item.get("draft")
        if not isinstance(draft, str):
            errors.append(f"{family}:missing_draft")
            continue
        _validate(family, semantics, errors, draft)
    attribution_cases = data.get("attribution_cases", []) if isinstance(data, dict) else []
    if not isinstance(attribution_cases, list):
        errors.append("attribution_cases_not_list")
        attribution_cases = []
    menxia_cases = 0
    taizi_cases = 0
    for case in attribution_cases:
        if not isinstance(case, dict) or not isinstance(case.get("case"), str):
            errors.append("attribution_case_invalid")
            continue
        name = case["case"]
        request = case.get("request")
        if not isinstance(request, dict):
            errors.append(f"{name}:request_invalid")
            continue
        try:
            result = court_result_semantics.classify_attribution(**request)
        except (TypeError, ValueError) as exc:
            errors.append(f"{name}:classification_failed:{exc}")
            continue
        if result.get("label") != case.get("expected_label"):
            errors.append(f"{name}:label_mismatch")
        if result.get("requires_final_followup") is not case.get("requires_final_followup", False):
            errors.append(f"{name}:followup_mismatch")
        expected_problem = case.get("expected_problem")
        if expected_problem and expected_problem not in result.get("menxia_problems", []):
            errors.append(f"{name}:problem_missing:{expected_problem}")
        if case.get("expected_label") == "MenxiaReview":
            menxia_cases += 1
        if case.get("expected_label") in {"TaiziSynthesis", "TaiziReply"}:
            taizi_cases += 1
    menxia_gate = not any(
        error.startswith(("accepted_menxia", "taizi_impersonation", "stale_menxia", "pre_ministry"))
        for error in errors
    ) and menxia_cases >= 1
    taizi_gate = not any(
        error.startswith(("root_synthesis", "user_reply", "missing_final_followup"))
        for error in errors
    ) and taizi_cases >= 3
    result = {
        "schema": "court.result_semantics_gate.v1",
        "gate": "PASSED" if not errors else "FAILED",
        "MENXIA_REVIEW_ATTRIBUTION": "PASS" if menxia_gate else "FAIL",
        "TAIZI_LABEL_SEMANTICS": "PASS" if taizi_gate else "FAIL",
        "families": len(REQUIRED_FAMILIES),
        "cases": len(fixtures),
        "attribution_cases": len(attribution_cases),
        "errors": errors,
    }
    return result


def main() -> int:
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["gate"] == "PASSED" else 2


if __name__ == "__main__":
    sys.exit(main())
