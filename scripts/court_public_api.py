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
    """Return Shiguan query results through the shared query implementation."""

    from query_shiguan_index import load_entries, select_query_matches

    bounded_limit = max(1, min(int(limit), 20))
    entries = load_entries()
    matches = select_query_matches(entries, [term for term in (terms or []) if term.strip()])
    return _api_result(matches[:bounded_limit])


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
