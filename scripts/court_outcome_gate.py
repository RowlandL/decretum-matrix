"""Pure, fail-closed validation for court outcome acceptance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
import sys

sys.dont_write_bytecode = True

from court_intake_gate import WORK_KINDS


OUTCOME_SCHEMA = "court.outcome_acceptance.v1"
ASSESSMENT_SCHEMA = "court.outcome_assessment.v1"

RESULT_STATUSES = frozenset({"USABLE", "USABLE_WITH_CONCERNS", "PARTIAL", "BLOCKED"})
SECTION_STATUSES = frozenset({"PASSED", "FAILED", "NOT_APPLICABLE"})
RISK_STATUSES = frozenset({"PASSED", "PASSED_WITH_RESIDUAL", "FAILED"})
VERIFICATION_STATES = frozenset({"VERIFIED", "PARTIAL", "NOT_RUN"})
EVIDENCE_SCOPES = frozenset(
    {
        "user_outcome",
        "functional_closure",
        "non_regression",
        "risk_boundary",
        "control_plane",
        "documentation",
    }
)
ASSESSMENT_GATES = frozenset(
    {
        "UNASSESSED",
        "PASSED",
        "PASSED_WITH_CONCERNS",
        "RETURN_FOR_REWORK",
        "PARTIAL",
        "BLOCKED",
    }
)

EXECUTION_WORK_KINDS = frozenset({"implementation", "operation", "release"})
NON_EXECUTION_WORK_KINDS = WORK_KINDS - EXECUTION_WORK_KINDS
EXECUTION_RESULT_SCOPES = frozenset(
    {"user_outcome", "functional_closure", "non_regression", "risk_boundary"}
)
NON_EXECUTION_RESULT_SCOPES = frozenset({"user_outcome"})
NON_RESULT_SCOPES = frozenset({"control_plane", "documentation"})


def default_outcome_assessment() -> dict[str, object]:
    return {
        "schema": ASSESSMENT_SCHEMA,
        "gate": "UNASSESSED",
        "reasons": [],
        "outcome": None,
    }


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _canonical_token(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        return ""
    return value


def _append_reason(reasons: list[str], code: str, detail: str = "") -> None:
    reason = f"{code}:{detail}" if detail else code
    if reason not in reasons:
        reasons.append(reason)


def _deduplicate_reasons(reasons: list[str]) -> list[str]:
    return list(dict.fromkeys(reasons))


def _assessment_has_rejection_or_failure_diagnostics(value: object) -> bool:
    if not isinstance(value, dict):
        return True

    reasons = value.get("reasons")
    definitive_reason_codes = {
        "evidence_result_not_passed",
        "functional_closure_failed",
        "non_regression_failed",
        "risk_boundary_failed",
    }
    if isinstance(reasons, list) and any(
        isinstance(reason, str) and reason.split(":", 1)[0] in definitive_reason_codes
        for reason in reasons
    ):
        return True

    outcome = value.get("outcome")
    if not isinstance(outcome, dict):
        return True
    for section_name in ("functional_closure", "non_regression", "risk_boundary"):
        section = outcome.get(section_name)
        if isinstance(section, dict) and section.get("status") == "FAILED":
            return True
    evidence = outcome.get("evidence")
    if not isinstance(evidence, list):
        return True
    for item in evidence:
        if not isinstance(item, dict):
            return True
        freshness = item.get("freshness")
        if not isinstance(freshness, dict) or freshness.get("status") != "FRESH":
            return True
    return False


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if candidate.endswith(("Z", "z")):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _normalize_digest(value: object) -> str:
    return value if isinstance(value, str) else ""


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _normalize_section(
    value: object,
    *,
    name: str,
    statuses: frozenset[str],
    shape_reasons: list[str],
) -> dict[str, object]:
    if not isinstance(value, dict):
        _append_reason(shape_reasons, "section_type", name)
        return {"status": "", "reason": "", "evidence_ids": []}

    status = _canonical_token(value.get("status"))
    raw_reason = value.get("reason")
    if not isinstance(raw_reason, str):
        _append_reason(shape_reasons, "section_reason_type", name)
    reason = _text(raw_reason)
    raw_ids = value.get("evidence_ids")
    if status not in statuses:
        _append_reason(shape_reasons, "section_status", name)
    if not isinstance(raw_ids, list):
        _append_reason(shape_reasons, "section_evidence_ids_type", name)
        evidence_ids: list[str] = []
    else:
        evidence_ids = []
        for raw_id in raw_ids:
            evidence_id = _canonical_token(raw_id)
            if not evidence_id:
                _append_reason(shape_reasons, "section_evidence_id", name)
            elif evidence_id in evidence_ids:
                _append_reason(shape_reasons, "duplicate_section_evidence_id", f"{name}/{evidence_id}")
            else:
                evidence_ids.append(evidence_id)
    if status == "NOT_APPLICABLE" and not reason:
        _append_reason(shape_reasons, "not_applicable_reason_required", name)
    return {"status": status, "reason": reason, "evidence_ids": evidence_ids}


def _normalize_registry(value: object) -> tuple[dict[str, dict[str, object]], set[str], bool]:
    entries: list[tuple[str | None, object, bool]]
    valid = True
    if isinstance(value, Mapping):
        entries = []
        for raw_key, item in value.items():
            key = _canonical_token(raw_key)
            if not key:
                valid = False
            entries.append((key or None, item, True))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        entries = [(None, item, False) for item in value]
    else:
        return {}, set(), False

    registry: dict[str, dict[str, object]] = {}
    duplicates: set[str] = set()
    for key, item, from_mapping in entries:
        if not isinstance(item, dict):
            valid = False
            continue
        entry = dict(item)
        if "id" in entry:
            entry_id = _canonical_token(entry.get("id"))
            if not entry_id:
                valid = False
                continue
        else:
            entry_id = key or ""
        if not entry_id or (from_mapping and (not key or key != entry_id)):
            valid = False
            continue
        if entry_id in registry:
            duplicates.add(entry_id)
            continue
        entry["id"] = entry_id
        registry[entry_id] = entry
    return registry, duplicates, valid


def _registry_identity_and_digest(entry: dict[str, object]) -> tuple[str, str, list[str]]:
    artifact_path = _text(entry.get("artifact_path"))
    artifact_digest = _normalize_digest(entry.get("artifact_sha256"))
    command_identity = (
        _text(entry.get("command_identity"))
        or _text(entry.get("normalized_command_identity"))
        or _text(entry.get("normalized_command"))
    )
    command_digest = _normalize_digest(entry.get("command_digest"))

    artifact_complete = bool(artifact_path and artifact_digest)
    command_complete = bool(command_identity and command_digest)
    errors: list[str] = []
    if bool(artifact_path) != bool(artifact_digest):
        errors.append("artifact_binding_incomplete")
    if bool(command_identity) != bool(command_digest):
        errors.append("command_binding_incomplete")
    if artifact_digest and not _is_sha256(artifact_digest):
        errors.append("digest_format_invalid")
    if command_digest and not _is_sha256(command_digest):
        errors.append("digest_format_invalid")
    if artifact_complete == command_complete:
        errors.append("registry_identity_digest_ambiguous")
    if artifact_complete and not command_complete:
        return artifact_path, artifact_digest, errors
    if command_complete and not artifact_complete:
        return command_identity, command_digest, errors
    return "", "", errors


def _freshness_context(
    *,
    expected_task_id: object,
    expected_charter_revision: object,
    expected_charter_sha256: object,
    evidence_registry: object,
    observed_digests: object,
    assessed_at: object,
    charter_effective_at: object,
    max_evidence_age_seconds: object,
) -> dict[str, object]:
    registry, duplicate_registry_ids, registry_shape_valid = _normalize_registry(evidence_registry)
    task_id = _canonical_token(expected_task_id)
    charter_hash = _normalize_digest(expected_charter_sha256)
    revision_valid = type(expected_charter_revision) is int and expected_charter_revision >= 1
    assessment_time = _parse_timestamp(assessed_at)
    effective_time = None
    effective_time_valid = charter_effective_at is None
    if charter_effective_at is not None:
        effective_time = _parse_timestamp(charter_effective_at)
        effective_time_valid = effective_time is not None
    max_age_valid = max_evidence_age_seconds is None or (
        type(max_evidence_age_seconds) is int and max_evidence_age_seconds >= 0
    )
    observed_valid = isinstance(observed_digests, Mapping)
    observed = dict(observed_digests) if observed_valid else {}
    complete = all(
        (
            bool(task_id),
            revision_valid,
            _is_sha256(charter_hash),
            registry_shape_valid,
            observed_valid,
            assessment_time is not None,
            effective_time_valid,
            max_age_valid,
        )
    )
    return {
        "complete": complete,
        "task_id": task_id,
        "charter_revision": expected_charter_revision if revision_valid else None,
        "charter_sha256": charter_hash,
        "registry": registry,
        "duplicate_registry_ids": duplicate_registry_ids,
        "observed_digests": observed,
        "assessed_at": assessment_time,
        "charter_effective_at": effective_time,
        "max_evidence_age_seconds": max_evidence_age_seconds if max_age_valid else None,
    }


def _compute_evidence_freshness(
    evidence: dict[str, object],
    *,
    raw_evidence: dict[str, object],
    context: dict[str, object],
) -> dict[str, object]:
    evidence_id = str(evidence["id"])
    failures: list[str] = []
    if "fresh" in raw_evidence:
        failures.append("self_reported_freshness_forbidden")
    if not context["complete"]:
        failures.append("runtime_freshness_context_missing")

    registry = context["registry"]
    registry_entry = registry.get(evidence_id) if isinstance(registry, dict) else None
    duplicate_registry_ids = context["duplicate_registry_ids"]
    if isinstance(duplicate_registry_ids, set) and duplicate_registry_ids:
        failures.append("registry_duplicate_ids_present")
    if isinstance(duplicate_registry_ids, set) and evidence_id in duplicate_registry_ids:
        failures.append("duplicate_registry_id")
    if registry_entry is None:
        failures.append("registry_entry_missing")
        return {
            "status": "REJECTED",
            "reasons": _deduplicate_reasons(failures),
            "registry_scope": None,
        }

    registry_scope = _canonical_token(registry_entry.get("scope"))
    if registry_scope not in EVIDENCE_SCOPES:
        failures.append("registry_scope_invalid")
    elif registry_scope != evidence["scope"]:
        failures.append("registry_scope_mismatch")

    if _canonical_token(registry_entry.get("task_id")) != context["task_id"]:
        failures.append("task_id_mismatch")
    registry_revision = registry_entry.get("charter_revision")
    if type(registry_revision) is not int or registry_revision < 1:
        failures.append("charter_revision_invalid")
    elif registry_revision != context["charter_revision"]:
        failures.append("charter_revision_mismatch")
    registry_charter_hash = _normalize_digest(registry_entry.get("charter_sha256"))
    if not _is_sha256(registry_charter_hash):
        failures.append("charter_sha256_invalid")
    elif registry_charter_hash != context["charter_sha256"]:
        failures.append("charter_sha256_mismatch")
    if _canonical_token(registry_entry.get("verification_status")) != "VERIFIED":
        failures.append("registry_not_verified")

    captured_at = _parse_timestamp(registry_entry.get("captured_at"))
    verified_at = _parse_timestamp(registry_entry.get("verified_at"))
    assessed_at = context["assessed_at"]
    if captured_at is None:
        failures.append("captured_at_invalid")
    if verified_at is None:
        failures.append("verified_at_invalid")
    if captured_at is not None and verified_at is not None and verified_at < captured_at:
        failures.append("verified_before_captured")
    if isinstance(assessed_at, datetime):
        if captured_at is not None and captured_at > assessed_at:
            failures.append("captured_after_assessment")
        if verified_at is not None and verified_at > assessed_at:
            failures.append("verified_after_assessment")

    effective_at = context["charter_effective_at"]
    if isinstance(effective_at, datetime):
        if captured_at is not None and captured_at < effective_at:
            failures.append("captured_before_current_charter")
        if verified_at is not None and verified_at < effective_at:
            failures.append("verified_before_current_charter")

    max_age = context["max_evidence_age_seconds"]
    if (
        type(max_age) is int
        and isinstance(assessed_at, datetime)
        and captured_at is not None
        and (assessed_at - captured_at).total_seconds() > max_age
    ):
        failures.append("evidence_expired")
    if "expires_at" in registry_entry:
        expires_at = _parse_timestamp(registry_entry.get("expires_at"))
        if expires_at is None:
            failures.append("expires_at_invalid")
        elif isinstance(assessed_at, datetime) and assessed_at > expires_at:
            failures.append("evidence_expired")

    identity, registry_digest, binding_errors = _registry_identity_and_digest(registry_entry)
    failures.extend(binding_errors)
    if identity and evidence["locator"] != identity:
        failures.append("evidence_identity_mismatch")
    observed = context["observed_digests"]
    observed_digest = _normalize_digest(observed.get(evidence_id)) if isinstance(observed, dict) else ""
    if not observed_digest:
        failures.append("observed_digest_missing")
    elif not _is_sha256(observed_digest):
        failures.append("digest_format_invalid")
    elif registry_digest and observed_digest != registry_digest:
        failures.append("digest_mismatch")
    if evidence["result"] != "PASSED":
        failures.append("evidence_result_not_passed")

    return {
        "status": "FRESH" if not failures else "REJECTED",
        "reasons": _deduplicate_reasons(failures),
        "registry_scope": registry_scope if registry_scope in EVIDENCE_SCOPES else None,
    }


def assess_outcome(
    value: object,
    *,
    expected_work_kind: str,
    expected_task_id: str | None = None,
    expected_charter_revision: int | None = None,
    expected_charter_sha256: str | None = None,
    evidence_registry: object = None,
    observed_digests: object = None,
    assessed_at: str | None = None,
    charter_effective_at: str | None = None,
    max_evidence_age_seconds: int | None = None,
) -> dict[str, object]:
    """Validate shape and return a deterministic, runtime-derived assessment."""

    if not isinstance(value, dict):
        return {
            "schema": ASSESSMENT_SCHEMA,
            "gate": "RETURN_FOR_REWORK",
            "reasons": ["outcome_type"],
            "outcome": None,
        }

    raw = dict(value)
    reasons: list[str] = []
    shape_reasons: list[str] = []
    schema = _canonical_token(raw.get("schema"))
    work_kind = _canonical_token(raw.get("work_kind"))
    expected_kind = _canonical_token(expected_work_kind)
    result_status = _canonical_token(raw.get("result_status"))
    final_usable_result = _text(raw.get("final_usable_result"))
    usable_for = _text(raw.get("usable_for"))
    verification_state = _canonical_token(raw.get("verification_state"))

    if schema != OUTCOME_SCHEMA:
        _append_reason(shape_reasons, "schema")
    if expected_kind not in WORK_KINDS:
        _append_reason(shape_reasons, "expected_work_kind")
    if work_kind not in WORK_KINDS:
        _append_reason(shape_reasons, "work_kind")
    elif work_kind != expected_kind:
        _append_reason(shape_reasons, "work_kind_mismatch")
    if result_status not in RESULT_STATUSES:
        _append_reason(shape_reasons, "result_status")
    if verification_state not in VERIFICATION_STATES:
        _append_reason(shape_reasons, "verification_state")

    functional = _normalize_section(
        raw.get("functional_closure"),
        name="functional_closure",
        statuses=SECTION_STATUSES,
        shape_reasons=shape_reasons,
    )
    non_regression = _normalize_section(
        raw.get("non_regression"),
        name="non_regression",
        statuses=SECTION_STATUSES,
        shape_reasons=shape_reasons,
    )
    risk = _normalize_section(
        raw.get("risk_boundary"),
        name="risk_boundary",
        statuses=RISK_STATUSES,
        shape_reasons=shape_reasons,
    )

    raw_gaps = raw.get("residual_gaps")
    residual_gaps: list[str] = []
    if not isinstance(raw_gaps, list):
        _append_reason(shape_reasons, "residual_gaps_type")
    else:
        for raw_gap in raw_gaps:
            gap = _text(raw_gap)
            if not gap:
                _append_reason(shape_reasons, "residual_gap_empty")
            else:
                residual_gaps.append(gap)

    context = _freshness_context(
        expected_task_id=expected_task_id,
        expected_charter_revision=expected_charter_revision,
        expected_charter_sha256=expected_charter_sha256,
        evidence_registry=evidence_registry,
        observed_digests=observed_digests,
        assessed_at=assessed_at,
        charter_effective_at=charter_effective_at,
        max_evidence_age_seconds=max_evidence_age_seconds,
    )
    if not context["complete"]:
        _append_reason(reasons, "runtime_freshness_context_missing")
    duplicate_registry_ids = context["duplicate_registry_ids"]
    if isinstance(duplicate_registry_ids, set):
        for duplicate_id in sorted(duplicate_registry_ids):
            _append_reason(reasons, "duplicate_registry_id", duplicate_id)

    raw_evidence = raw.get("evidence")
    normalized_evidence: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    if not isinstance(raw_evidence, list):
        _append_reason(shape_reasons, "evidence_type")
    else:
        for index, raw_item in enumerate(raw_evidence):
            if not isinstance(raw_item, dict):
                _append_reason(shape_reasons, "evidence_item_type", str(index))
                continue
            evidence_id = _canonical_token(raw_item.get("id"))
            scope = _canonical_token(raw_item.get("scope"))
            kind = _text(raw_item.get("kind"))
            locator = _text(raw_item.get("locator"))
            result = _canonical_token(raw_item.get("result"))
            structurally_valid = True
            if not evidence_id:
                _append_reason(shape_reasons, "evidence_id", str(index))
                structurally_valid = False
            elif evidence_id in seen_ids:
                _append_reason(shape_reasons, "duplicate_evidence_id", evidence_id)
                structurally_valid = False
            else:
                seen_ids.add(evidence_id)
            if scope not in EVIDENCE_SCOPES:
                _append_reason(shape_reasons, "evidence_scope", evidence_id or str(index))
                structurally_valid = False
            if not kind:
                _append_reason(shape_reasons, "evidence_kind", evidence_id or str(index))
                structurally_valid = False
            if not locator:
                _append_reason(shape_reasons, "evidence_locator", evidence_id or str(index))
                structurally_valid = False
            if not result:
                _append_reason(shape_reasons, "evidence_result", evidence_id or str(index))
                structurally_valid = False
            normalized = {
                "id": evidence_id,
                "scope": scope,
                "kind": kind,
                "locator": locator,
                "result": result,
            }
            if structurally_valid:
                freshness = _compute_evidence_freshness(
                    normalized,
                    raw_evidence=raw_item,
                    context=context,
                )
            else:
                freshness = {
                    "status": "REJECTED",
                    "reasons": ["evidence_shape_invalid"],
                    "registry_scope": None,
                }
            normalized["freshness"] = freshness
            normalized_evidence.append(normalized)
            for freshness_reason in freshness["reasons"]:
                _append_reason(reasons, str(freshness_reason), evidence_id or str(index))

    evidence_by_id = {
        str(item["id"]): item
        for item in normalized_evidence
        if isinstance(item.get("id"), str) and item["id"]
    }
    linked_fresh_scopes: set[str] = set()
    for section_name, section in (
        ("functional_closure", functional),
        ("non_regression", non_regression),
        ("risk_boundary", risk),
    ):
        section_links_fresh = bool(section["evidence_ids"])
        for evidence_id in section["evidence_ids"]:
            linked_evidence = evidence_by_id.get(str(evidence_id))
            if linked_evidence is None:
                section_links_fresh = False
                _append_reason(
                    shape_reasons,
                    "section_evidence_missing",
                    f"{section_name}/{evidence_id}",
                )
            elif linked_evidence.get("scope") != section_name:
                section_links_fresh = False
                _append_reason(
                    shape_reasons,
                    "section_evidence_scope_mismatch",
                    f"{section_name}/{evidence_id}",
                )
            else:
                freshness = linked_evidence.get("freshness")
                if not isinstance(freshness, dict) or freshness.get("status") != "FRESH":
                    section_links_fresh = False
        if section_links_fresh:
            linked_fresh_scopes.add(section_name)

    normalized_outcome: dict[str, object] = {
        "schema": schema,
        "work_kind": work_kind,
        "result_status": result_status,
        "final_usable_result": final_usable_result,
        "usable_for": usable_for,
        "functional_closure": functional,
        "non_regression": non_regression,
        "risk_boundary": risk,
        "verification_state": verification_state,
        "evidence": normalized_evidence,
        "residual_gaps": residual_gaps,
    }

    fresh_scopes = {
        str(item["freshness"]["registry_scope"])
        for item in normalized_evidence
        if isinstance(item.get("freshness"), dict)
        and item["freshness"].get("status") == "FRESH"
        and item["freshness"].get("registry_scope") == "user_outcome"
    }
    fresh_scopes.update(linked_fresh_scopes)
    required_scopes = (
        EXECUTION_RESULT_SCOPES if work_kind in EXECUTION_WORK_KINDS else NON_EXECUTION_RESULT_SCOPES
    )
    missing_scopes = sorted(required_scopes - fresh_scopes)

    functional_status = str(functional["status"])
    non_regression_status = str(non_regression["status"])
    risk_status = str(risk["status"])
    rework_reasons: list[str] = []
    if not final_usable_result:
        _append_reason(rework_reasons, "final_usable_result_required")
    if not usable_for:
        _append_reason(rework_reasons, "usable_for_required")
    if risk_status == "PASSED_WITH_RESIDUAL":
        if result_status != "USABLE_WITH_CONCERNS":
            _append_reason(rework_reasons, "risk_residual_requires_concerns_status")
        if not residual_gaps:
            _append_reason(rework_reasons, "risk_residual_requires_gaps")
    if result_status == "USABLE_WITH_CONCERNS" and not residual_gaps:
        _append_reason(rework_reasons, "concerns_require_residual_gaps")
    if (
        result_status != "PARTIAL"
        and residual_gaps
        and result_status != "USABLE_WITH_CONCERNS"
    ):
        _append_reason(rework_reasons, "residual_gaps_require_concerns_status")
    if functional_status == "FAILED":
        _append_reason(rework_reasons, "functional_closure_failed")
    if non_regression_status == "FAILED":
        _append_reason(rework_reasons, "non_regression_failed")
    if work_kind in EXECUTION_WORK_KINDS:
        if functional_status not in {"PASSED", "FAILED"}:
            _append_reason(rework_reasons, "functional_closure_required")
        if non_regression_status not in {"PASSED", "FAILED"}:
            _append_reason(rework_reasons, "non_regression_required")
    elif work_kind in NON_EXECUTION_WORK_KINDS and (
        (functional_status == "NOT_APPLICABLE" and not functional["reason"])
        or (non_regression_status == "NOT_APPLICABLE" and not non_regression["reason"])
    ):
        _append_reason(rework_reasons, "not_applicable_reason_required")

    diagnostics: list[str] = []
    for diagnostic in shape_reasons + reasons + rework_reasons:
        _append_reason(diagnostics, diagnostic)
    if result_status == "BLOCKED":
        _append_reason(diagnostics, "result_status_blocked")
    if risk_status == "FAILED":
        _append_reason(diagnostics, "risk_boundary_failed")
    if result_status == "PARTIAL":
        _append_reason(diagnostics, "result_status_partial")
    if verification_state in {"PARTIAL", "NOT_RUN"}:
        _append_reason(diagnostics, "verification_state_incomplete", verification_state)
    if missing_scopes:
        _append_reason(diagnostics, "missing_result_scopes", ",".join(missing_scopes))

    rejected_evidence = any(
        isinstance(item.get("freshness"), dict)
        and item["freshness"].get("status") == "REJECTED"
        for item in normalized_evidence
    )
    failed_declared_evidence = any(
        isinstance(item.get("freshness"), dict)
        and "evidence_result_not_passed" in item["freshness"].get("reasons", [])
        for item in normalized_evidence
    )
    blocked = result_status == "BLOCKED" or risk_status == "FAILED"
    rework = bool(shape_reasons or rework_reasons or failed_declared_evidence)
    partial = bool(
        result_status == "PARTIAL"
        or verification_state in {"PARTIAL", "NOT_RUN"}
        or missing_scopes
    )

    if blocked:
        gate = "BLOCKED"
    elif rework or (rejected_evidence and not partial):
        gate = "RETURN_FOR_REWORK"
    elif partial:
        gate = "PARTIAL"
    elif result_status == "USABLE_WITH_CONCERNS":
        gate = "PASSED_WITH_CONCERNS"
    else:
        gate = "PASSED"

    return {
        "schema": ASSESSMENT_SCHEMA,
        "gate": gate,
        "reasons": diagnostics,
        "outcome": normalized_outcome,
    }


def require_completable_assessment(
    value: object,
    *,
    expected_work_kind: str | None = None,
    expected_task_id: str | None = None,
    expected_charter_revision: int | None = None,
    expected_charter_sha256: str | None = None,
    evidence_registry: object = None,
    observed_digests: object = None,
    assessed_at: str | None = None,
    charter_effective_at: str | None = None,
    max_evidence_age_seconds: int | None = None,
) -> dict[str, object]:
    """Revalidate and return only a runtime-bound completable assessment."""

    if not isinstance(value, dict):
        raise ValueError("assessment_type")
    if value.get("schema") != ASSESSMENT_SCHEMA:
        raise ValueError("assessment_schema")
    gate = value.get("gate")
    if gate not in {"PASSED", "PASSED_WITH_CONCERNS"}:
        raise ValueError("assessment_not_completable")
    reasons = value.get("reasons")
    outcome = value.get("outcome")
    if not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons):
        raise ValueError("assessment_reasons")
    if not isinstance(outcome, dict) or outcome.get("schema") != OUTCOME_SCHEMA:
        raise ValueError("assessment_outcome")
    expected_kind = _canonical_token(expected_work_kind)
    runtime_context = _freshness_context(
        expected_task_id=expected_task_id,
        expected_charter_revision=expected_charter_revision,
        expected_charter_sha256=expected_charter_sha256,
        evidence_registry=evidence_registry,
        observed_digests=observed_digests,
        assessed_at=assessed_at,
        charter_effective_at=charter_effective_at,
        max_evidence_age_seconds=max_evidence_age_seconds,
    )
    if expected_kind not in WORK_KINDS or not runtime_context["complete"]:
        raise ValueError("assessment_runtime_context_required")

    revalidated = assess_outcome(
        outcome,
        expected_work_kind=expected_kind,
        expected_task_id=expected_task_id,
        expected_charter_revision=expected_charter_revision,
        expected_charter_sha256=expected_charter_sha256,
        evidence_registry=evidence_registry,
        observed_digests=observed_digests,
        assessed_at=assessed_at,
        charter_effective_at=charter_effective_at,
        max_evidence_age_seconds=max_evidence_age_seconds,
    )
    if revalidated["gate"] not in {"PASSED", "PASSED_WITH_CONCERNS"}:
        raise ValueError("assessment_not_completable")
    if _assessment_has_rejection_or_failure_diagnostics(revalidated):
        raise ValueError("assessment_not_completable")
    if _assessment_has_rejection_or_failure_diagnostics(value):
        raise ValueError("assessment_not_completable")
    if revalidated["gate"] != gate:
        raise ValueError("assessment_revalidation_mismatch")
    if revalidated["reasons"] != reasons:
        raise ValueError("assessment_revalidation_mismatch")
    return deepcopy(revalidated)
