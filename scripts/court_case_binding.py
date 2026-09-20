"""Pure identity binding for standard session-backed court cases.

The binding is deliberately a projection of an existing runtime task and its
already-issued session allocation.  It owns no ledger, does no I/O, and never
allocates a court code.  Callers persist the returned task with the existing
runtime transaction.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import re
from typing import Any, Mapping

import sys

sys.dont_write_bytecode = True


CASE_BINDING_SCHEMA = "court.case_binding.v1"
ALLOCATION_SCHEMA = "court.session_court_code_allocation.v1"
PLAN_SCHEMA = "court.zhongshu_plan.v1"
PLAN_REVIEW_SCHEMA = "court.plan_review.v1"
AUTHORITIES = frozenset({"approval", "autonomous", "super"})
BEHAVIORS = frozenset({"serial", "parallel"})
REVIEW_ROLES = ("menxia", "shangshu")
OFFICE_CAPSULE_INITIALS = {
    "taizi": "TZ",
    "zhongshu": "ZSS",
    "menxia": "MXS",
    "shangshu": "SSS",
    "hubu": "HB",
    "libu": "LB",
    "libu-hr": "LBH",
    "bingbu": "BB",
    "xingbu": "XB",
    "gongbu": "GB",
    "shiguan": "SG",
    "shiguan-hermes": "SG",
    "zaochao": "ZC",
    "patrol-inspector": "JCS",
}
_DATE_RE = re.compile(r"\d{8}")
_SEQUENCE_RE = re.compile(r"[0-9A-Z]+")
_COURT_CODE_RE = re.compile(r"^[A-Z0-9]+-\d{8}-[0-9A-Z]+-[A-Z0-9]{4}$")
_BINDING_FIELDS = frozenset(
    {
        "schema",
        "task_id",
        "session_id",
        "court_code",
        "allocation_date",
        "daily_sequence",
        "charter_revision",
        "case_execution",
        "zhongshu_plan",
        "case_reviews",
    }
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value: object, field: str, limit: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"case_binding_{field}_required")
    text = value.strip()
    if len(text.encode("utf-8")) > limit or any(char in text for char in "\x00\r\n"):
        raise ValueError(f"case_binding_{field}_invalid")
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"case_binding_{field}_invalid")
    return value


def _case_execution(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"authority", "behavior"}:
        raise ValueError("case_binding_case_execution_invalid")
    authority = _text(value.get("authority"), "authority", 32).lower()
    behavior = _text(value.get("behavior"), "behavior", 32).lower()
    if authority not in AUTHORITIES:
        raise ValueError("case_binding_authority_invalid")
    if behavior not in BEHAVIORS:
        raise ValueError("case_binding_behavior_invalid")
    return {"authority": authority, "behavior": behavior}


def _allocation(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("case_binding_allocation_required")
    session_id = _text(value.get("session_id"), "session_id")
    candidate = dict(value)
    try:
        from court_session_numbering import validate_session_allocation

        validated = validate_session_allocation(candidate, session_id)
    except (TypeError, ValueError):
        validated = None
    if not isinstance(validated, dict):
        raise ValueError("case_binding_allocation_invalid")
    court_code = _text(validated.get("court_code"), "court_code", 128).upper()
    allocation_date = _text(validated.get("date"), "allocation_date", 8)
    daily_sequence = _text(validated.get("daily_sequence"), "daily_sequence", 64).upper()
    if (
        validated.get("schema") != ALLOCATION_SCHEMA
        or _DATE_RE.fullmatch(allocation_date) is None
        or _SEQUENCE_RE.fullmatch(daily_sequence) is None
        or _COURT_CODE_RE.fullmatch(court_code) is None
    ):
        raise ValueError("case_binding_allocation_invalid")
    return {
        "schema": ALLOCATION_SCHEMA,
        "session_id": session_id,
        "court_code": court_code,
        "date": allocation_date,
        "daily_sequence": daily_sequence,
    }


def _allocation_from_binding(binding: Mapping[str, object]) -> dict[str, str]:
    return _allocation(
        {
            "schema": ALLOCATION_SCHEMA,
            "session_id": binding.get("session_id"),
            "court_code": binding.get("court_code"),
            "date": binding.get("allocation_date"),
            "daily_sequence": binding.get("daily_sequence"),
        }
    )


def _plan_summary(task: Mapping[str, object]) -> dict[str, object] | None:
    raw = task.get("zhongshu_plan")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("case_binding_plan_invalid")
    required = {
        "schema",
        "task_id",
        "court_code",
        "charter_revision",
        "plan_id",
        "revision",
        "document",
        "producer",
    }
    if not required.issubset(raw) or raw.get("schema") != PLAN_SCHEMA:
        raise ValueError("case_binding_plan_invalid")
    task_id = _text(task.get("task_id"), "task_id")
    charter_revision = _positive_int(task.get("charter_revision"), "charter_revision")
    court_code = _text(task.get("court_code"), "court_code", 128).upper()
    if (
        raw.get("task_id") != task_id
        or raw.get("charter_revision") != charter_revision
        or _text(raw.get("court_code"), "plan_court_code", 128).upper() != court_code
        or not isinstance(raw.get("document"), Mapping)
        or not isinstance(raw.get("producer"), Mapping)
    ):
        raise ValueError("case_binding_plan_foreign_or_stale")
    return {
        "plan_id": _text(raw.get("plan_id"), "plan_id", 256),
        "revision": _positive_int(raw.get("revision"), "plan_revision"),
    }


def _producer_summary(value: object, role: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("case_binding_review_producer_invalid")
    kind = _text(value.get("kind"), "review_producer_kind", 32)
    producer_role = _text(value.get("role"), "review_producer_role", 32).lower()
    agent_id_value = value.get("agent_id")
    if not isinstance(agent_id_value, str) or len(agent_id_value.encode("utf-8")) > 256:
        raise ValueError("case_binding_review_producer_invalid")
    agent_id = agent_id_value.strip()
    if kind not in {"host_report", "serial_inline"} or producer_role != role:
        raise ValueError("case_binding_review_producer_invalid")
    if (kind == "serial_inline" and agent_id) or (kind == "host_report" and not agent_id):
        raise ValueError("case_binding_review_producer_invalid")
    return {"kind": kind, "role": producer_role, "agent_id": agent_id}


def _review_summaries(
    task: Mapping[str, object], plan: Mapping[str, object] | None
) -> dict[str, dict[str, object]]:
    raw = task.get("case_reviews", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping) or any(role not in REVIEW_ROLES for role in raw):
        raise ValueError("case_binding_reviews_invalid")
    if plan is None:
        if raw:
            raise ValueError("case_binding_reviews_without_plan")
        return {}
    task_id = _text(task.get("task_id"), "task_id")
    charter_revision = _positive_int(task.get("charter_revision"), "charter_revision")
    summaries: dict[str, dict[str, object]] = {}
    for role in REVIEW_ROLES:
        review = raw.get(role)
        if review is None:
            continue
        if not isinstance(review, Mapping):
            raise ValueError("case_binding_review_invalid")
        if (
            review.get("schema") != PLAN_REVIEW_SCHEMA
            or review.get("role") != role
            or review.get("task_id") != task_id
            or review.get("charter_revision") != charter_revision
            or _text(review.get("court_code"), "review_court_code", 128).upper()
            != _text(task.get("court_code"), "court_code", 128).upper()
            or review.get("plan_revision") != plan.get("revision")
        ):
            raise ValueError("case_binding_review_foreign_or_stale")
        summaries[role] = {
            "producer": _producer_summary(review.get("producer"), role),
            "plan_revision": plan["revision"],
            "review_id": _text(review.get("review_id"), "review_id", 256),
        }
    return summaries


def _binding_body(
    task: Mapping[str, object], allocation: Mapping[str, object]
) -> dict[str, object]:
    normalized_allocation = _allocation(allocation)
    task_id = _text(task.get("task_id"), "task_id")
    session_id = _text(task.get("session_id"), "session_id")
    court_code = _text(task.get("court_code"), "court_code", 128).upper()
    if (
        session_id != normalized_allocation["session_id"]
        or court_code != normalized_allocation["court_code"]
    ):
        raise ValueError("case_binding_task_allocation_mismatch")
    charter_revision = _positive_int(task.get("charter_revision"), "charter_revision")
    case_execution = _case_execution(task.get("case_execution"))
    plan = _plan_summary(task)
    reviews = _review_summaries(task, plan)
    return {
        "schema": CASE_BINDING_SCHEMA,
        "task_id": task_id,
        "session_id": session_id,
        "court_code": court_code,
        "allocation_date": normalized_allocation["date"],
        "daily_sequence": normalized_allocation["daily_sequence"],
        "charter_revision": charter_revision,
        "case_execution": case_execution,
        "zhongshu_plan": plan,
        "case_reviews": reviews,
    }


def build_case_binding(
    task: Mapping[str, object], allocation: Mapping[str, object]
) -> dict[str, object]:
    """Build the canonical persisted binding from one task and allocation."""

    return _binding_body(task, allocation)


def _normalize_binding(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise ValueError("case_binding_fields_invalid")
    binding = deepcopy(dict(value))
    if binding.get("schema") != CASE_BINDING_SCHEMA:
        raise ValueError("case_binding_schema_invalid")
    _text(binding.get("task_id"), "task_id")
    _text(binding.get("session_id"), "session_id")
    court_code = _text(binding.get("court_code"), "court_code", 128).upper()
    allocation_date = _text(binding.get("allocation_date"), "allocation_date", 8)
    daily_sequence = _text(binding.get("daily_sequence"), "daily_sequence", 64).upper()
    if (
        _COURT_CODE_RE.fullmatch(court_code) is None
        or _DATE_RE.fullmatch(allocation_date) is None
        or _SEQUENCE_RE.fullmatch(daily_sequence) is None
    ):
        raise ValueError("case_binding_allocation_invalid")
    _positive_int(binding.get("charter_revision"), "charter_revision")
    _case_execution(binding.get("case_execution"))
    plan = binding.get("zhongshu_plan")
    if plan is not None:
        if not isinstance(plan, Mapping) or set(plan) != {"plan_id", "revision"}:
            raise ValueError("case_binding_plan_summary_invalid")
        _text(plan.get("plan_id"), "plan_id", 256)
        _positive_int(plan.get("revision"), "plan_revision")
    reviews = binding.get("case_reviews")
    if not isinstance(reviews, Mapping) or any(role not in REVIEW_ROLES for role in reviews):
        raise ValueError("case_binding_reviews_invalid")
    if plan is None and reviews:
        raise ValueError("case_binding_reviews_without_plan")
    expected_plan_revision = plan.get("revision") if isinstance(plan, Mapping) else None
    for role, summary in reviews.items():
        if not isinstance(summary, Mapping) or set(summary) != {"producer", "plan_revision", "review_id"}:
            raise ValueError("case_binding_review_summary_invalid")
        if summary.get("plan_revision") != expected_plan_revision:
            raise ValueError("case_binding_review_foreign_or_stale")
        _producer_summary(summary.get("producer"), str(role))
    binding["court_code"] = court_code
    binding["allocation_date"] = allocation_date
    binding["daily_sequence"] = daily_sequence
    binding["case_execution"] = _case_execution(binding["case_execution"])
    return binding


def canonical_case_binding_json(binding: Mapping[str, object]) -> str:
    """Render an integrity-checked binding for archive transport."""

    return _canonical_json(_normalize_binding(binding))


def validate_case_binding(
    binding: object,
    task: Mapping[str, object],
    *,
    allocation: Mapping[str, object] | None = None,
    require_decree: bool = False,
) -> dict[str, object]:
    """Validate one stored binding against its live task and optional allocation."""

    normalized = _normalize_binding(binding)
    supplied_allocation = (
        _allocation(allocation)
        if allocation is not None
        else _allocation_from_binding(normalized)
    )
    if (
        supplied_allocation["session_id"] != normalized["session_id"]
        or supplied_allocation["court_code"] != normalized["court_code"]
        or supplied_allocation["date"] != normalized["allocation_date"]
        or supplied_allocation["daily_sequence"] != normalized["daily_sequence"]
    ):
        raise ValueError("case_binding_allocation_foreign")
    expected = build_case_binding(task, supplied_allocation)
    if normalized != expected:
        raise ValueError("case_binding_task_mismatch")
    if require_decree:
        _require_bound_decree(task, normalized)
    return normalized


def _require_bound_decree(task: Mapping[str, object], binding: Mapping[str, object]) -> None:
    from court_operation_journal import normalize_operation_binding

    if (
        not isinstance(task.get("decree_id"), str)
        or not task.get("decree_id")
        or task.get("main_court_code") != binding["court_code"]
        or task.get("parent_court_code") != binding["court_code"]
    ):
        raise ValueError("case_binding_decree_missing_or_foreign")
    operations = task.get("operations")
    if not isinstance(operations, Mapping):
        raise ValueError("case_binding_decree_missing_or_foreign")
    matching = []
    for operation in operations.values():
        if (not isinstance(operation, Mapping) or operation.get("kind") != "decree_open"
                or operation.get("status") != "COMMITTED"):
            continue
        receipt = operation.get("receipt")
        if not isinstance(receipt, Mapping):
            continue
        try:
            origin = normalize_operation_binding(operation.get("operation_binding"), operation_id=operation.get("operation_id"))
        except ValueError:
            continue
        revision = receipt.get("charter_revision")
        if type(revision) is not int or not 0 < revision <= binding["charter_revision"]:
            continue
        original_ref = {"court_code": binding["court_code"], "charter_revision": revision}
        if (
            receipt.get("task_id") == binding["task_id"]
            and receipt.get("decree_id") == task["decree_id"]
            and receipt.get("court_code") == binding["court_code"]
            and receipt.get("session_id") == binding["session_id"]
            # The creation receipt binds its original revision, not later corrections.
            and receipt.get("case_ref") == original_ref == origin["case_ref"]
            and origin["task_id"] == binding["task_id"]
            and origin["operation_kind"] == "decree_open"
            and receipt.get("operation_id") == origin["operation_id"]
        ):
            matching.append(receipt)
    if len(matching) != 1:
        raise ValueError("case_binding_decree_missing_or_foreign")


def validate_task_case_binding(
    task: Mapping[str, object],
    *,
    allocation: Mapping[str, object] | None = None,
    require_decree: bool = False,
) -> dict[str, object] | None:
    """Return a validated standard-case binding, or ``None`` for legacy tasks."""

    binding = task.get("case_binding")
    if binding is None:
        return None
    return validate_case_binding(
        binding,
        task,
        allocation=allocation,
        require_decree=require_decree,
    )


def refresh_case_binding(
    task: Mapping[str, object],
    allocation: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return a refreshed binding after a plan/review/charter update.

    The caller attaches the returned value to its copied task and commits it
    through the existing runtime transaction.  This function preserves and
    validates the immutable session/court allocation and execution selection;
    it does not write either ledger.
    """

    if not isinstance(task.get("case_binding"), Mapping):
        raise ValueError("case_binding_missing")
    old = _normalize_binding(task["case_binding"])
    if _text(task.get("task_id"), "task_id") != old["task_id"]:
        raise ValueError("case_binding_task_mismatch")
    if (
        _text(task.get("session_id"), "session_id") != old["session_id"]
        or _text(task.get("court_code"), "court_code", 128).upper()
        != old["court_code"]
    ):
        raise ValueError("case_binding_task_allocation_mismatch")
    if _case_execution(task.get("case_execution")) != old["case_execution"]:
        raise ValueError("case_binding_execution_mismatch")
    source_allocation = _allocation(allocation) if allocation is not None else _allocation_from_binding(old)
    if (
        source_allocation["session_id"] != old["session_id"]
        or source_allocation["court_code"] != old["court_code"]
        or source_allocation["date"] != old["allocation_date"]
        or source_allocation["daily_sequence"] != old["daily_sequence"]
    ):
        raise ValueError("case_binding_allocation_foreign")
    return build_case_binding(task, source_allocation)


def case_reference(task_or_binding: Mapping[str, object]) -> dict[str, object]:
    """Return the business reference without a content digest."""

    source = task_or_binding.get("case_binding")
    value = source if isinstance(source, Mapping) else task_or_binding
    court_code = _text(value.get("court_code"), "court_code", 128).upper()
    if _COURT_CODE_RE.fullmatch(court_code) is None:
        raise ValueError("case_reference_court_code_invalid")
    return {
        "court_code": court_code,
        "charter_revision": _positive_int(
            value.get("charter_revision"), "charter_revision"
        ),
    }


def plan_reference(task_or_plan: Mapping[str, object]) -> dict[str, object]:
    """Return the plan version under its existing case reference."""

    if "plan_revision" in task_or_plan:
        reference = case_reference(task_or_plan)
        return {
            **reference,
            "plan_revision": _positive_int(
                task_or_plan.get("plan_revision"), "plan_revision"
            ),
        }
    raw_plan = task_or_plan.get("zhongshu_plan")
    if isinstance(raw_plan, Mapping):
        reference = case_reference(task_or_plan)
        revision = raw_plan.get("revision")
    else:
        reference = case_reference(task_or_plan)
        revision = task_or_plan.get("revision")
    return {
        **reference,
        "plan_revision": _positive_int(revision, "plan_revision"),
    }


def office_capsule_reference(
    case_ref: Mapping[str, object],
    role_key: str,
    office_instance_id: str,
    issued_at: str,
) -> dict[str, object]:
    """Build an office capsule id from one recorded creation/admission time."""

    normalized_role = _text(role_key, "role_key", 64).lower()
    initials = OFFICE_CAPSULE_INITIALS.get(normalized_role)
    if initials is None:
        raise ValueError("office_capsule_role_unknown")
    normalized_instance = _text(office_instance_id, "office_instance_id", 256)
    normalized_time = _text(issued_at, "issued_at", 64)
    try:
        moment = datetime.fromisoformat(normalized_time.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("office_capsule_issued_at_invalid") from exc
    if moment.tzinfo is None:
        raise ValueError("office_capsule_issued_at_invalid")
    reference = case_reference(case_ref)
    return {
        "capsule_id": f"{reference['court_code']}-{moment.strftime('%H%M')}{initials}",
        "case_ref": reference,
        "office_instance_id": normalized_instance,
        "role_key": normalized_role,
        "issued_at": normalized_time,
    }


__all__ = [
    "ALLOCATION_SCHEMA",
    "AUTHORITIES",
    "BEHAVIORS",
    "CASE_BINDING_SCHEMA",
    "build_case_binding",
    "case_reference",
    "canonical_case_binding_json",
    "office_capsule_reference",
    "plan_reference",
    "refresh_case_binding",
    "validate_case_binding",
    "validate_task_case_binding",
]
