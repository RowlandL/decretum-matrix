"""Pure result-attribution rules for Menxia review and Taizi delivery."""

from __future__ import annotations

from typing import Mapping


RESULT_SCHEMA = "court.result.attribution.v1"
POST_MINISTRY_STAGES = {"post_ministry", "final"}


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def valid_menxia_report(
    report: object,
    *,
    current_semantic_receipt_sha256: str,
    stage: str,
) -> tuple[bool, tuple[str, ...]]:
    problems: list[str] = []
    if not isinstance(report, Mapping):
        return False, ("menxia_report_missing",)
    if _text(report.get("role")).lower() != "menxia":
        problems.append("menxia_role_mismatch")
    if report.get("accepted") is not True:
        problems.append("menxia_report_not_accepted")
    if stage not in POST_MINISTRY_STAGES:
        problems.append("menxia_review_before_ministries")
    evidence = report.get("evidence_binding")
    if not isinstance(evidence, Mapping):
        problems.append("menxia_evidence_missing")
    else:
        if not _text(evidence.get("report_id")):
            problems.append("menxia_report_id_missing")
        if not _text(evidence.get("task_id")):
            problems.append("menxia_task_id_missing")
        if _text(evidence.get("semantic_receipt_sha256")) != current_semantic_receipt_sha256:
            problems.append("menxia_evidence_stale")
    return not problems, tuple(problems)


def classify_attribution(
    *,
    actor_role: str,
    stage: str,
    delivery: str,
    current_semantic_receipt_sha256: str,
    menxia_report: object = None,
) -> dict[str, object]:
    actor = _text(actor_role).lower()
    normalized_stage = _text(stage).lower()
    normalized_delivery = _text(delivery).lower()
    if actor != "taizi":
        raise ValueError("result_actor_must_be_taizi")
    if normalized_stage not in {"pre_ministry", "post_ministry", "final"}:
        raise ValueError("result_stage_invalid")
    if normalized_delivery not in {"internal", "user"}:
        raise ValueError("result_delivery_invalid")
    current_hash = _text(current_semantic_receipt_sha256).lower()
    if len(current_hash) != 64 or any(char not in "0123456789abcdef" for char in current_hash):
        raise ValueError("semantic_receipt_sha256_invalid")

    menxia_valid, menxia_problems = valid_menxia_report(
        menxia_report,
        current_semantic_receipt_sha256=current_hash,
        stage=normalized_stage,
    )
    if normalized_delivery == "user":
        label = "TaiziReply"
    elif menxia_valid:
        label = "MenxiaReview"
    else:
        label = "TaiziSynthesis"
    return {
        "schema": RESULT_SCHEMA,
        "actor_role": actor,
        "stage": normalized_stage,
        "delivery": normalized_delivery,
        "label": label,
        "menxia_report_accepted": menxia_valid,
        "menxia_problems": list(menxia_problems),
        "requires_final_followup": normalized_stage == "final" and normalized_delivery != "user",
    }
