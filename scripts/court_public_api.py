"""Shared read-only public API used by both CLI and MCP adapters.

This module deliberately contains no transport code and no second ledger. The
CLI and MCP facades call these functions as peers, so neither adapter shells
out to the other or inherits the other's encoding boundary.
Backends load at their endpoint; metadata-only calls do not need workflow state.
"""

from __future__ import annotations

from argparse import Namespace
import json
import sys
from typing import Mapping

sys.dont_write_bytecode = True


def public_capsule_validation_payload(charter: str, value: object) -> dict[str, object]:
    from court_runtime import public_capsule_validation_payload as validate
    return validate(charter, value)


def public_intake_validation_payload(
    charter: str, intake_value: object, capsule_value: object | None = None,
) -> dict[str, object]:
    from court_runtime import public_intake_validation_payload as validate
    return validate(charter, intake_value, capsule_value)


def public_semantic_context_validation_payload(value: object) -> dict[str, object]:
    from court_runtime import public_semantic_context_validation_payload as validate
    return validate(value)


def _api_result(payload: object, *, stderr: str = "", exit_status: int = 0) -> dict[str, object]:
    return {
        "exit_status": exit_status,
        "stdout": payload,
        "stderr": stderr,
    }


def _operation_result(body: object) -> dict[str, object]:
    """Lift an advisory backend explicit failure into the operation envelope.

    A body reporting ok:false (service unreachable, HTTP error, bad payload,
    explicit refusal) is an operation failure: it has to reach the caller exit
    status, the MCP isError flag and the audit outcome. A legitimate domain
    verdict never routes through here -- those keep ok:false inside an
    otherwise successful envelope, so a negative conclusion stays a normal
    diagnostic (beta1.2.2 F09).
    """

    if not isinstance(body, dict):
        return _api_result(
            {"ok": False, "problem": "advisory_bad_payload"},
            stderr="advisory_bad_payload",
            exit_status=1,
        )
    if body.get("ok") is True:
        return _api_result(body)
    problem = str(body.get("problem") or "operation_failed")
    return _api_result(body, stderr=problem, exit_status=1)


def _contract_failure(payload: Mapping[str, object], code: str) -> dict[str, object]:
    """Lift a rejected public input onto the operation failure envelope.

    An argument that violates the public contract -- an unknown role key, a
    candidate outside the allowed set, an unknown decision position -- is a
    caller error, not a domain verdict: it has to reach the caller exit status,
    the MCP isError flag and the audit outcome. A well-formed negative verdict
    (a plan that fails its rules, a deny decision, an abstain) keeps its own ok
    field inside a successful envelope instead (beta1.2.2 F09).
    """

    return _api_result(dict(payload), stderr=str(code), exit_status=1)


def _client_failure(exc: BaseException) -> str:
    """Reduce an unclassified client exception to a bounded problem code.

    The exception message can carry a local path or a URL, so only the
    exception type is published; the exit status and audit still record the
    failure (beta1.2.2 F09).
    """

    return "recall_client_failure_" + type(exc).__name__.strip().lower()[:64]


def court_status(limit: int = 12, view: str = 'full') -> dict[str, object]:
    """Return the canonical court status projection without a subprocess."""

    from court_runtime import status_payload

    bounded_limit = max(1, min(int(limit), 100))
    return _api_result(status_payload(Namespace(limit=bounded_limit, view=view)))


def court_command_help() -> dict[str, object]:
    """Return the public court help projection without invoking the CLI."""

    from court_cli_registry import normal_startup_guidance, render_group_help

    return _api_result({"command": "court help", "help": render_group_help("court"),
                        "startup": normal_startup_guidance()})


def court_workflow_status(task_id: str) -> dict[str, object]:
    """Read the same canonical identity/plan/review view exposed by the CLI."""
    from court_runtime import workflow_status_payload
    return _api_result(workflow_status_payload(task_id))


def shiguan_query(terms: list[str] | None = None, limit: int = 5) -> dict[str, object]:
    """Return Shiguan query results through the shared query implementation.

    The payload reuses the same metadata whitelist as the entries_query
    projection, so this legacy entry point cannot return synthetic or
    non-metadata fields. Match order and the _api_result envelope are
    unchanged (beta1.2.2 F16).
    """

    from query_shiguan_index import load_entries, select_query_matches

    bounded_limit = max(1, min(int(limit), 20))
    entries = load_entries()
    matches = select_query_matches(entries, [term for term in (terms or []) if term.strip()])
    return _api_result([_metadata_projection(entry) for entry in matches[:bounded_limit]])


def shiguan_archive_dry_run() -> dict[str, object]:
    """Expose the archive boundary without creating a checkpoint."""

    return _api_result(
        {
            "dry_run": True,
            "write_enabled": False,
            "command": "archive-checkpoint",
        }
    )


def memory_scan() -> dict[str, object]:
    """Expose the public memory-scan boundary without reading private bodies."""

    return _api_result(
        {
            "dry_run": True,
            "write_enabled": False,
            "private_body_access": False,
            "command": "internal-memory-shiguan-bridge",
        }
    )


def has_replacement_characters(value: object) -> bool:
    """Detect transport corruption in a structured public result."""

    return "\ufffd" in json.dumps(value, ensure_ascii=False)


DISPATCH_AUTHORITIES = ("approval", "autonomous", "super")
DISPATCH_BEHAVIORS = ("serial", "parallel")
DISPATCH_DEFAULT_AUTHORITY = "approval"
DISPATCH_DEFAULT_BEHAVIOR = "serial"


def _validate_dispatch_plan_structure(entries: object) -> list[str]:
    try:
        from court_dispatch_policy import dispatch_plan_structure_errors
    except ImportError:
        return ["dispatch_policy_unavailable"]
    return [problem.code for problem in dispatch_plan_structure_errors(entries)]


def public_dispatch_plan_validation(
    entries: list[dict[str, object]],
    authority: str | None = None,
    behavior: str | None = None,
    trusted_preload_manifest: object = None,
) -> dict[str, object]:
    """Validate a dispatch plan without dispatching.

    Defaults to approval+serial so callers can never fall into an implicit
    super+parallel default (devspec FR-D / P2-2). When ``trusted_preload_manifest``
    is supplied the full host preload contract gate runs; otherwise the structural
    plan rules are validated (MCP callers have no host preload state).
    """

    selected_authority = authority or DISPATCH_DEFAULT_AUTHORITY
    selected_behavior = behavior or DISPATCH_DEFAULT_BEHAVIOR
    if selected_authority not in DISPATCH_AUTHORITIES:
        return {
            "schema": "court.dispatch_plan_validation.result.v1",
            "ok": False,
            "errors": [{"field": "authority", "kind": "contract", "code": "invalid_authority"}],
        }
    if selected_behavior not in DISPATCH_BEHAVIORS:
        return {
            "schema": "court.dispatch_plan_validation.result.v1",
            "ok": False,
            "errors": [{"field": "behavior", "kind": "contract", "code": "invalid_behavior"}],
        }
    from court_dispatch_hierarchy import _manifest_bundle
    hierarchy = _manifest_bundle()
    special = set(hierarchy['role_sets']['special_lifecycle'])
    unsupported = sorted({str(entry.get('role', '')).strip().lower()
                          for entry in entries if isinstance(entry, dict)} & special) if isinstance(entries, (list, tuple)) else []
    if unsupported:
        return {'schema':'court.dispatch_plan_validation.result.v1', 'ok':False,
                'errors':[{'field':'entries','kind':'contract','code':'ordinary_native_dispatch_not_supported',
                           'roles':unsupported}],
                'role_recognition':'known_special_lifecycle',
                'guidance':'These roles have no ordinary native dispatch edge; record unsupported coverage, never an OK reply.'}
    if trusted_preload_manifest is not None:
        try:
            from court_dispatch_policy import validate_dispatch_plan

            plan = validate_dispatch_plan(
                entries,
                authority=selected_authority,
                behavior=selected_behavior,
                trusted_preload_manifest=trusted_preload_manifest,
            )
        except (ImportError, OSError, TypeError, ValueError) as exc:
            return {
                "schema": "court.dispatch_plan_validation.result.v1",
                "ok": False,
                "errors": [{"field": "entries", "kind": "contract", "code": str(exc)}],
            }
        return {
            "schema": "court.dispatch_plan_validation.result.v1",
            "ok": True,
            "errors": [],
            "authority": selected_authority,
            "behavior": selected_behavior,
            "roles": list(plan.roles),
            "entry_count": len(plan.entries),
            "unjustified_roles": list(plan.unjustified_roles),
        }
    violations = _validate_dispatch_plan_structure(entries)
    if violations:
        return {
            "schema": "court.dispatch_plan_validation.result.v1",
            "ok": False,
            "errors": [
                {
                    "field": "entries",
                    "kind": "contract",
                    "code": "dispatch_plan_invalid",
                    "violations": violations,
                }
            ],
        }
    roles = []
    for raw in entries:
        role = str(raw.get("role") or "").strip().lower()
        if role and role not in roles:
            roles.append(role)
    return {
        "schema": "court.dispatch_plan_validation.result.v1",
        "ok": True,
        "errors": [],
        "authority": selected_authority,
        "behavior": selected_behavior,
        "roles": roles,
        "entry_count": len(entries),
        "unjustified_roles": [],
    }


CLOSEOUT_MEMORIAL_LABELS: tuple[tuple[str, bool], ...] = (
    ("诏令编号", True),
    ("古制谱系", True),
    ("状态", False),
    ("作业AI", False),
    ("旨意与边界", False),
    ("执行门禁", False),
    ("门下裁定", False),
    ("实际动作", False),
    ("验收证据", False),
    ("运行态与并行", False),
    ("史馆", False),
    ("余险", False),
    ("太子回奏", False),
    ("下一步", False),
)


def public_closeout_checklist(task_id: str | None = None) -> dict[str, object]:
    """Return the fourteen-label closeout memorial checklist and missing items.

    Labels and order follow references/sections/court-closeout-memorial-format.md.
    The first two identity labels are receipt-bound and counted missing until an
    archive-checkpoint receipt exists for the closeout.
    """

    checklist = [
        {
            "label": label,
            "receipt_bound": receipt_bound,
            "ok": not receipt_bound,
            "note": "需 archive_checkpoint receipt 后逐字填写" if receipt_bound else "结诏时填写",
        }
        for label, receipt_bound in CLOSEOUT_MEMORIAL_LABELS
    ]
    result: dict[str, object] = {
        "schema": "court.closeout_checklist.result.v1",
        "ok": True,
        "errors": [],
        "checklist": checklist,
        "missing": [item for item in checklist if not item["ok"]],
        "label_count": len(checklist),
    }
    if task_id is not None:
        result["task_id"] = str(task_id)
    return result


SHIGUAN_ENTRY_PROJECTION_FIELDS = (
    "time",
    "court_code",
    "lineage_display",
    "ancient_lineage",
    "classification_status",
    "classification_reason",
    "taxonomy_version",
    "court_code_review_required",
    "topic",
    "phase",
    "status",
    "summary",
    "keyword_summary_zh",
    "source",
    "keywords",
    "memory_decision",
    "capability_vector_terms",
)


def _metadata_projection(entry: dict[str, object]) -> dict[str, object]:
    """Project a Shiguan entry to metadata only (no pending/private bodies)."""

    projection: dict[str, object] = {}
    for field in SHIGUAN_ENTRY_PROJECTION_FIELDS:
        value = entry.get(field)
        if value is None:
            continue
        if isinstance(value, str) and len(value) > 140:
            value = value[:137].rstrip() + "..."
        projection[field] = value
    return projection


def public_shiguan_entries_query(query: str, limit: int = 20) -> dict[str, object]:
    """Query Shiguan entries and return a metadata-only projection."""

    bounded = max(1, min(int(limit), 50))
    term = str(query or "").strip()
    if not term:
        return {
            "schema": "court.shiguan_entries_query.result.v1",
            "ok": False,
            "errors": [{"field": "query", "kind": "contract", "code": "empty_query"}],
        }
    try:
        from query_shiguan_index import load_entries, select_query_matches

        entries = load_entries()
        matches = select_query_matches(entries, [term])
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "schema": "court.shiguan_entries_query.result.v1",
            "ok": False,
            "errors": [{"field": "query", "kind": "runtime", "code": str(exc)}],
        }
    projection = [_metadata_projection(entry) for entry in matches[:bounded]]
    return {
        "schema": "court.shiguan_entries_query.result.v1",
        "ok": True,
        "errors": [],
        "query": term,
        "matches": projection,
        "count": len(projection),
    }


IKU_PUBLIC_CANDIDATE_FIELDS = (
    "record_path",
    "record_id",
    "record_ref",
    "checkpoint",
    "checkpoint_ref",
    "checkpoint_line_number",
    "field",
    "line_number",
    "line_coordinate",
    "placeholder_kind",
    "suggested_action",
    "reason",
    "nearest_court_code",
    "nearest_lineage",
    "receipt_hint",
    "receipt_verified",
)
IKU_LINE_COORDINATE_FIELDS = (
    "record_ref",
    "record_id",
    "record_path",
    "checkpoint_ref",
    "checkpoint",
    "checkpoint_line_number",
    "line_number",
    "field",
    "placeholder_kind",
)


def _public_iku_candidate(candidate: object) -> dict[str, object]:
    """Project only structured IKU coordinates through the public boundary."""

    if not isinstance(candidate, Mapping):
        return {}
    projection: dict[str, object] = {}
    for field in IKU_PUBLIC_CANDIDATE_FIELDS:
        if field not in candidate:
            continue
        value = candidate[field]
        if field == "line_coordinate":
            if isinstance(value, Mapping):
                value = {
                    key: value[key]
                    for key in IKU_LINE_COORDINATE_FIELDS
                    if key in value
                }
            else:
                continue
        projection[field] = value
    return projection


def public_iku_candidates(scope: str = "plan-archives", limit: int = 20) -> dict[str, object]:
    """Read-only IKU placeholder candidate discovery (dry_run, never writes)."""

    bounded = max(1, min(int(limit), 100))
    try:
        from iku_candidates import detect_candidates

        candidates = detect_candidates(scope=scope, limit=bounded)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "schema": "court.iku_candidates.result.v1",
            "ok": False,
            "errors": [{"field": "scope", "kind": "contract", "code": str(exc)}],
        }
    return {
        "schema": "court.iku_candidates.result.v1",
        "ok": True,
        "errors": [],
        "dry_run": True,
        "write_enabled": False,
        "scope": scope,
        "candidates": [_public_iku_candidate(candidate) for candidate in candidates],
        "count": len(candidates),
    }


def shiguan_recall(state: str, k: int = 5, same_topic: bool = False) -> dict[str, object]:
    """Advisory: return the k most similar historical Shiguan records.

    Read-only proxy to the local laya-recall service. Never writes Shiguan data
    and never mutates the taxonomy; results are advisory only.
    """

    from court_shiguan_recall_client import recall as _recall

    try:
        body = _recall(state, k=k, same_topic=same_topic)
    except Exception as exc:  # noqa: BLE001 - service boundary must fail closed
        # Any failure the client did not classify -- transport, decode, or an
        # unexpected payload shape (KeyError) -- has to fail closed here: no
        # exception may escape the public API, because the CLI peer has no
        # adapter to turn it into an exit status and only the type is published.
        return _api_result(
            {"ok": False, "problem": _client_failure(exc)},
            stderr=_client_failure(exc),
            exit_status=1,
        )
    return _operation_result(body)


def shiguan_recall_stats() -> dict[str, object]:
    """Advisory: return laya-recall service and index statistics."""

    from court_shiguan_recall_client import stats as _stats

    try:
        body = _stats()
    except Exception as exc:  # noqa: BLE001 - service boundary must fail closed
        return _api_result(
            {"ok": False, "problem": _client_failure(exc)},
            stderr=_client_failure(exc),
            exit_status=1,
        )
    return _operation_result(body)


# --- Unified decision contract (beta1.2.2) -------------------------------
# One compatible projection shared by every decision position. It carries
# bounded metadata only: a raw private body never enters a decision record.

DECISION_CONTRACT_SCHEMA = "court.decision_projection.v1"
DECISION_POSITIONS: tuple[str, ...] = (
    "intake_decomposition",
    "agent_lifecycle",
    "office_capability_tool",
    "model_execution_route",
    "process_result",
    "memory_write_classification",
    "recall_context",
    "maintenance_forgetting",
)
DECISION_OUTCOMES: tuple[str, ...] = ("allow", "deny", "abstain", "error")
DECISION_PROVIDER_KINDS: tuple[str, ...] = ("rule", "local_model", "host_model", "cache")
DECISION_FALLBACK_REASONS: tuple[str, ...] = (
    "rules_sufficient",
    "cache_hit",
    "local_model_unavailable",
    "local_model_timeout",
    "queue_overloaded",
    "not_calibrated",
    "low_coverage",
    "out_of_distribution",
    "input_truncated",
    "invalid_output",
    "candidate_conflict",
    "host_unavailable",
    "gateway_unreachable",
)
# Conditions that must hand the judgement to the host model instead of
# standing on a local score (roadmap 3.2).
DECISION_HOST_HANDOFF_REASONS: tuple[str, ...] = (
    "local_model_unavailable",
    "local_model_timeout",
    "queue_overloaded",
    "not_calibrated",
    "low_coverage",
    "out_of_distribution",
    "input_truncated",
    "invalid_output",
    "candidate_conflict",
    "gateway_unreachable",
)
DECISION_MAX_CANDIDATES = 16
DECISION_MAX_EVIDENCE_REFS = 16
DECISION_MAX_TEXT = 96
DECISION_MAX_REFERENCE = 512
# A host that already failed or that cannot judge may not be routed to again:
# the projection has to name a pause exit with a resume condition (roadmap 3.2).
DECISION_PAUSE_RESUME: dict[str, tuple[str, ...]] = {
    "host_unavailable": ("host_reachable", "rule_path_only_actions"),
    "host_model_cannot_judge": ("new_evidence", "explicit_user_redecision"),
}


class _ContractError(ValueError):
    """A field-level contract rejection that carries its public code."""

    def __init__(self, field: str, code: str) -> None:
        super().__init__(code)
        self.field = field
        self.code = code


def _bounded_text(value: object, limit: int = DECISION_MAX_TEXT) -> str | None:
    """Reduce a value to bounded, non-body text; None when absent."""

    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return text[:limit]


def _strict_text(
    record: Mapping, field: str, limit: int = DECISION_MAX_TEXT, *, required: bool = False,
) -> str | None:
    """Return a bounded string field, never coercing a non-string value.

    Identifiers and fixed metadata are declared metadata: a dict, list, bool or
    number is a caller contract error, and an over-long value is rejected
    instead of being silently truncated into a different identifier (R1/R4).
    """

    value = record.get(field)
    if value is None or value == "":
        if required:
            raise _ContractError(field, field + "_required")
        return None
    if not isinstance(value, str):
        raise _ContractError(field, field + "_must_be_string")
    text = value.strip()
    if not text:
        if required:
            raise _ContractError(field, field + "_required")
        return None
    if len(text) > limit:
        raise _ContractError(field, field + "_above_max_length")
    return text


def _strict_candidates(record: Mapping) -> list[str]:
    """Return bounded string candidate identifiers, rejecting anything else."""

    raw = record.get("allowed_candidates")
    if not isinstance(raw, (list, tuple)):
        raise _ContractError("allowed_candidates", "allowed_candidates_required")
    allowed: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise _ContractError(
                "allowed_candidates", "allowed_candidates_must_be_string_identifiers"
            )
        text = item.strip()
        if not text:
            raise _ContractError("allowed_candidates", "allowed_candidates_empty_identifier")
        if len(text) > DECISION_MAX_TEXT:
            raise _ContractError("allowed_candidates", "allowed_candidates_above_max_text")
        if text not in allowed:
            allowed.append(text)
    if not allowed:
        raise _ContractError("allowed_candidates", "allowed_candidates_required")
    if len(allowed) > DECISION_MAX_CANDIDATES:
        raise _ContractError("allowed_candidates", "allowed_candidates_above_max_items")
    return allowed


def _strict_candidate(record: Mapping, outcome: str, allowed: list[str]) -> str | None:
    """Return the chosen candidate identifier, or reject the record."""

    raw = record.get("candidate")
    if raw is None or raw == "":
        candidate = None
    else:
        if not isinstance(raw, str):
            raise _ContractError("candidate", "candidate_must_be_string")
        candidate = raw.strip()
        if not candidate:
            raise _ContractError("candidate", "candidate_required")
        if len(candidate) > DECISION_MAX_TEXT:
            raise _ContractError("candidate", "candidate_above_max_text")
    if candidate is None and outcome in {"allow", "deny"}:
        raise _ContractError("candidate", "candidate_required")
    if candidate is not None and candidate not in allowed:
        raise _ContractError("candidate", "candidate_not_in_allowed_candidates")
    return candidate


def _strict_evidence_refs(record: Mapping) -> list[str]:
    """Return evidence references verbatim; an unfittable pointer is rejected."""

    raw = record.get("evidence_refs")
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise _ContractError("evidence_refs", "evidence_refs_must_be_list")
    if len(raw) > DECISION_MAX_EVIDENCE_REFS:
        raise _ContractError("evidence_refs", "evidence_refs_above_max_items")
    refs: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise _ContractError("evidence_refs", "evidence_ref_not_string")
        if not item.strip():
            raise _ContractError("evidence_refs", "evidence_ref_empty")
        if len(item) > DECISION_MAX_REFERENCE:
            raise _ContractError("evidence_refs", "evidence_ref_above_max_length")
        refs.append(item)
    return refs


def _bounded_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(0, min(value, 86_400_000))


def public_decision_contract() -> dict[str, object]:
    """Return the bounded decision-contract vocabulary shared by CLI and MCP.

    Source contract is implemented; model effect, real-host routing and cache
    evidence are not measured here and stay NOT_RUN (never a success claim).
    """

    return _api_result({
        "schema": "court.decision_contract.v1",
        "ok": True,
        "errors": [],
        "projection_schema": DECISION_CONTRACT_SCHEMA,
        "positions": list(DECISION_POSITIONS),
        "outcomes": list(DECISION_OUTCOMES),
        "provider_kinds": list(DECISION_PROVIDER_KINDS),
        "fallback_reasons": list(DECISION_FALLBACK_REASONS),
        "host_handoff_reasons": list(DECISION_HOST_HANDOFF_REASONS),
        "limits": {
            "max_candidates": DECISION_MAX_CANDIDATES,
            "max_candidate_text": DECISION_MAX_TEXT,
            "max_evidence_refs": DECISION_MAX_EVIDENCE_REFS,
            "max_evidence_ref_length": DECISION_MAX_REFERENCE,
            "max_text": DECISION_MAX_TEXT,
        },
        "pause_reasons": sorted(DECISION_PAUSE_RESUME),
        "host_continuation": {
            "route": "host_native",
            "reenters_local_route": False,
            "requires_extra_credentials": False,
            "silently_replaces_user_model": False,
        },
        "verification": {
            "state": "PLANNED_UNVERIFIED",
            "source_contract": "IMPLEMENTED",
            "model_effect": "NOT_RUN",
            "real_host": "NOT_RUN",
            "cache": "NOT_RUN",
        },
    })


def _pause_exit(pause_reason: str) -> dict[str, object]:
    """Project a bounded pause exit with an explicit resume condition."""

    return {
        "required": False,
        "state": "paused",
        "route": None,
        "reason": pause_reason,
        "pause_reason": pause_reason,
        "resume_when": list(DECISION_PAUSE_RESUME[pause_reason]),
        "reenters_local_route": False,
    }


def _host_continuation(
    provider_kind: str, outcome: str, fallback_reason: str | None,
) -> dict[str, object]:
    """Report the continuation exit: host hand-off, pause, or resolved.

    A host that is already unusable may not be handed the judgement again, and
    a host model that abstains cannot be its own adjudicator: both become a
    bounded pause with a resume condition instead of a host_native route
    (roadmap 3.2). Local-model and rule hand-offs are unchanged.
    """

    host_unavailable = provider_kind == "host_model" or fallback_reason == "host_unavailable"
    if outcome == "abstain" and provider_kind == "host_model":
        return _pause_exit("host_model_cannot_judge")
    if outcome in {"abstain", "error"} and host_unavailable:
        return _pause_exit("host_unavailable")
    required = outcome in {"abstain", "error"} or (
        provider_kind == "local_model" and fallback_reason in DECISION_HOST_HANDOFF_REASONS
    )
    if not required:
        return {"required": False, "state": "resolved", "reason": fallback_reason, "route": None,
                "reenters_local_route": False}
    reason = fallback_reason or ("abstain" if outcome == "abstain" else "provider_error")
    return {"required": True, "state": "host_continuation", "reason": reason, "route": "host_native",
            "reenters_local_route": False}


def public_decision_projection(record: object) -> dict[str, object]:
    """Project one decision record onto the bounded public contract.

    A legal negative verdict (deny) and an abstain are valid decisions, so they
    project with ok true and never become a tool error. Only a record that
    cannot be projected at all -- an unknown position, an outcome outside the
    vocabulary, a non-string or over-long identifier, or a candidate outside the
    allowed set -- is rejected, and that rejection is a contract error: it must
    surface as a failed operation, never be excused as a legitimate negative. An
    "error" outcome is different: it classifies an upstream failure that already
    happened, so the projection still succeeds while keeping the error code and
    the continuation exit visible.

    Every identifier is a bounded metadata string: nothing is stringified or
    truncated into a different identity. Evidence references are carried
    verbatim and rejected when they cannot fit, because a silently rewritten
    receipt pointer is not locatable (R1/R4). The continuation exit is one of
    resolved, host_continuation, or a bounded pause with a resume condition
    (R2), and an uncalibrated local verdict is normalized to a local abstain
    that the host still judges (R3).
    """

    def rejected(field: str, code: str) -> dict[str, object]:
        return _contract_failure(
            {
                "schema": DECISION_CONTRACT_SCHEMA,
                "ok": False,
                "errors": [{"field": field, "kind": "contract", "code": code}],
            },
            code,
        )

    if not isinstance(record, Mapping):
        return rejected("record", "record_must_be_object")
    try:
        position = _strict_text(record, "decision_position", required=True)
        if position not in DECISION_POSITIONS:
            raise _ContractError("decision_position", "invalid_decision_position")
        allowed = _strict_candidates(record)
        outcome = _strict_text(record, "outcome", required=True)
        if outcome not in DECISION_OUTCOMES:
            raise _ContractError("outcome", "invalid_outcome")
        provider = _strict_text(record, "decision_provider", required=True)
        provider_kind = _strict_text(record, "provider_kind", required=True)
        if provider_kind not in DECISION_PROVIDER_KINDS:
            raise _ContractError("provider_kind", "invalid_provider_kind")
        candidate = _strict_candidate(record, outcome, allowed)
        fallback_reason = _strict_text(record, "fallback_reason")
        if fallback_reason is not None and fallback_reason not in DECISION_FALLBACK_REASONS:
            raise _ContractError("fallback_reason", "invalid_fallback_reason")
        error_code = _strict_text(record, "error_code")
        if outcome == "error" and not error_code:
            raise _ContractError("error_code", "error_code_required")
        refs = _strict_evidence_refs(record)
        input_scope = _strict_text(record, "input_scope")
        provider_version = _strict_text(record, "provider_version")
    except _ContractError as exc:
        return rejected(exc.field, exc.code)
    calibrated = record.get("confidence_calibrated") is True
    normalized: list[str] = []
    if provider_kind == "local_model" and not calibrated:
        # An uncalibrated local score may not stand as a final verdict: it
        # becomes a local abstain that the host still has to judge (roadmap
        # 3.2). Rule and cache verdicts are untouched by calibration.
        if outcome in {"allow", "deny"}:
            outcome = "abstain"
            normalized.append("uncalibrated_local_model_downgraded_to_abstain")
        if fallback_reason is None:
            fallback_reason = "not_calibrated"
            normalized.append("uncalibrated_local_model_reason_not_calibrated")
    decision: dict[str, object] = {
        "decision_position": position,
        "input_scope": input_scope,
        "allowed_candidates": allowed,
        "candidate": candidate,
        "decision_provider": provider,
        "provider_kind": provider_kind,
        "provider_version": provider_version,
        "confidence_calibrated": calibrated,
        "outcome": outcome,
        "evidence_refs": refs,
        "fallback_reason": fallback_reason,
        "elapsed_ms": _bounded_count(record.get("elapsed_ms")),
        "cost_units": _bounded_count(record.get("cost_units")),
        "host_continuation": _host_continuation(provider_kind, outcome, fallback_reason),
        "normalized": normalized,
        "verification_state": "PLANNED_UNVERIFIED",
    }
    if error_code is not None:
        decision["error_code"] = error_code
    return _api_result(
        {"schema": DECISION_CONTRACT_SCHEMA, "ok": True, "errors": [], "decision": decision}
    )


# --- Duty, instance and display separation (beta1.2.2) -------------------
# The duty contract reuses the existing role_key / direct_superior authority.
# No second identity table, state ledger or resolver is created here.

DUTY_PROJECTION_SCHEMA = "court.office_duty_projection.v1"
TASK_SKELETON_SCHEMA = "court.task_skeleton.v1"
TASK_SKELETON_SLOTS: tuple[str, ...] = (
    "goal_intent",
    "inputs_sources",
    "duty_boundary",
    "work_dependency",
    "delivery_acceptance",
    "handoff_recovery",
)
TASK_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "engineering": ("interface_compatibility", "verification"),
    "research": ("question", "source_standard", "uncertainty"),
    "document": ("audience", "structure", "expression"),
    "operations": ("reproduction", "impact", "recovery"),
    "review": ("scope", "finding", "acceptance_reason"),
}
DUTY_SOURCE = "references/manifests/court-dispatch-hierarchy.v1.json"
DUTY_ASSIGNMENT_SOURCE = "court_office_bootstrap.build_office_assignment_binding"


def _canonical_roles() -> dict[str, object]:
    """Read the existing hierarchy authority instead of introducing a new one."""

    from court_dispatch_hierarchy import _manifest_bundle

    roles = _manifest_bundle().get("canonical_roles")
    if not isinstance(roles, dict):
        raise ValueError("canonical_roles_unavailable")
    return roles


def _standing_duty(role_key: str, canonical_superior: str) -> dict[str, object]:
    """Read the standing profile authority and refuse a drifted superior edge.

    The profile TOML and the hierarchy manifest are two existing authorities;
    the projection consumes both and fails closed when they disagree, so this
    layer can never become a second, drifting identity table.
    """

    from court_office_bootstrap import _profile, load_standing_profile_binding

    binding = load_standing_profile_binding(role_key)
    _, profile = _profile(role_key)
    if binding["direct_superior"] != canonical_superior:
        raise ValueError("duty_authority_drift:" + role_key)
    return {
        "office_zh": binding["office_zh"],
        "direct_superior": binding["direct_superior"],
        "profile_source": binding["profile_source"],
        "duty": _bounded_text(profile.get("duty"), limit=512),
        "duty_boundary": _bounded_text(profile.get("cannot_do"), limit=512),
    }


def public_office_duty_projection(role_key: str | None = None) -> dict[str, object]:
    """Project the duty, real-instance and display layers for standing offices.

    Duty text, office name and profile pointer come from the existing standing
    profile plus the hierarchy manifest; no second identity, hierarchy or role
    table is created here. The instance layer stays unbound until a real
    assignment id exists, and the display layer never carries authority: a
    title, a person name, CEO or COO can neither create a role nor a dispatch
    edge (beta1.2.2 duty contract).
    """

    try:
        roles = _canonical_roles()
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return _contract_failure(
            {
                "schema": DUTY_PROJECTION_SCHEMA,
                "ok": False,
                "errors": [{"field": "role_key", "kind": "runtime", "code": str(exc)}],
            },
            str(exc),
        )
    selected = None if role_key is None else str(role_key).strip()
    if selected is not None and selected not in roles:
        return _contract_failure(
            {
                "schema": DUTY_PROJECTION_SCHEMA,
                "ok": False,
                "errors": [{"field": "role_key", "kind": "contract", "code": "unknown_role_key"}],
            },
            "unknown_role_key",
        )
    projections: list[dict[str, object]] = []
    for key in ([selected] if selected else sorted(roles)):
        entry = roles.get(key)
        entry = entry if isinstance(entry, Mapping) else {}
        superior = str(entry.get("direct_superior") or "").strip()
        try:
            duty = _standing_duty(str(key), superior)
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            return _contract_failure(
                {
                    "schema": DUTY_PROJECTION_SCHEMA,
                    "ok": False,
                    "errors": [{"field": "role_key", "kind": "runtime", "code": str(exc)}],
                },
                str(exc),
            )
        projections.append(
            {
                "duty": {
                    "role_key": str(key),
                    "office_zh": duty["office_zh"],
                    "direct_superior": duty["direct_superior"],
                    "duty": duty["duty"],
                    "duty_boundary": duty["duty_boundary"],
                    "profile_source": duty["profile_source"],
                    "hierarchy_source": DUTY_SOURCE,
                },
                "instance": {
                    "assignment_id": None,
                    "host_instance": None,
                    "binding": "assignment_required",
                    "assignment_source": DUTY_ASSIGNMENT_SOURCE,
                },
                "display": {
                    "display_name": None,
                    "honorific": None,
                    "bound_to_person": False,
                    "display_authority": False,
                },
            }
        )
    return _api_result(
        {
            "schema": DUTY_PROJECTION_SCHEMA,
            "ok": True,
            "errors": [],
            "roles": projections,
            "count": len(projections),
            "display_name_grants_authority": False,
            "note": "a title, person name, CEO or COO never creates a role, an authority or a dispatch edge",
        }
    )


def public_task_skeleton(
    goal_intent: str,
    inputs_sources: str,
    role_key: str,
    work_dependency: str,
    delivery_acceptance: str,
    handoff_recovery: str,
    extension: str | None = None,
    extension_fields: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the unified semantic task skeleton with a bounded extension.

    The six stable slots carry the same meaning for every task; a task-type
    extension may add detail but can never override a core slot or confer
    authority. The duty binding must name an existing role_key, so a display
    name cannot stand in for a function.
    """

    def rejected(field: str, code: str) -> dict[str, object]:
        return _contract_failure(
            {
                "schema": TASK_SKELETON_SCHEMA,
                "ok": False,
                "errors": [{"field": field, "kind": "contract", "code": code}],
            },
            code,
        )

    supplied = {
        "goal_intent": goal_intent,
        "inputs_sources": inputs_sources,
        "work_dependency": work_dependency,
        "delivery_acceptance": delivery_acceptance,
        "handoff_recovery": handoff_recovery,
    }
    for slot, value in supplied.items():
        if not str(value or "").strip():
            return rejected(slot, "missing_" + slot)
    try:
        roles = _canonical_roles()
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return rejected("role_key", str(exc))
    selected = str(role_key or "").strip()
    if selected not in roles:
        return rejected("role_key", "unknown_role_key")
    entry = roles.get(selected)
    entry = entry if isinstance(entry, Mapping) else {}
    superior = str(entry.get("direct_superior") or "").strip()
    try:
        duty = _standing_duty(selected, superior)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return rejected("role_key", str(exc))
    supplied["duty_boundary"] = (
        "role_key=" + selected + "; direct_superior=" + superior
        + "; boundary=" + str(duty["duty_boundary"] or duty["duty"] or "")
    )
    slots: dict[str, object] = {}
    for slot in TASK_SKELETON_SLOTS:
        slots[slot] = _bounded_text(supplied.get(slot), limit=2048)
    selected_extension = None if extension in (None, "") else str(extension).strip()
    projection: dict[str, object] | None = None
    if selected_extension is not None:
        fields = TASK_EXTENSIONS.get(selected_extension)
        if fields is None:
            return rejected("extension", "unknown_task_extension")
        requested = {} if extension_fields is None else dict(extension_fields)
        for name in requested:
            if str(name) in TASK_SKELETON_SLOTS:
                return rejected("extension_fields", "core_slot_override_rejected")
            if str(name) not in fields:
                return rejected("extension_fields", "extension_field_not_allowed")
        projection = {
            name: _bounded_text(requested.get(name), limit=2048)
            for name in fields
            if requested.get(name) is not None
        }
    return _api_result(
        {
            "schema": TASK_SKELETON_SCHEMA,
            "ok": True,
            "errors": [],
            "slots": slots,
            "slot_order": list(TASK_SKELETON_SLOTS),
            "extension": {
                "name": selected_extension,
                "fields": projection or {},
                "overrides_core_slots": False,
                "confers_authority": False,
            },
            "duty": {"role_key": selected, "direct_superior": superior},
        }
    )
