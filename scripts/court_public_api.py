"""Shared read-only public API used by both CLI and MCP adapters.

This module deliberately contains no transport code and no second ledger. The
CLI and MCP facades call these functions as peers, so neither adapter shells
out to the other or inherits the other's encoding boundary.
"""

from __future__ import annotations

from argparse import Namespace
import json
import sys
from typing import Any

sys.dont_write_bytecode = True

from court_runtime import (
    public_capsule_validation_payload,
    public_intake_validation_payload,
    public_semantic_context_validation_payload,
    status_payload,
)
from query_shiguan_index import load_entries, select_query_matches


def _api_result(payload: object, *, stderr: str = "", exit_status: int = 0) -> dict[str, object]:
    return {
        "exit_status": exit_status,
        "stdout": payload,
        "stderr": stderr,
    }


def court_status(limit: int = 12) -> dict[str, object]:
    """Return the canonical court status projection without a subprocess."""

    bounded_limit = max(1, min(int(limit), 100))
    return _api_result(status_payload(Namespace(limit=bounded_limit)))


def court_command_help() -> dict[str, object]:
    """Return the public court help projection without invoking the CLI."""

    from court_cli_registry import render_group_help

    return _api_result({"command": "court help", "help": render_group_help("court")})


def shiguan_query(terms: list[str] | None = None, limit: int = 5) -> dict[str, object]:
    """Return Shiguan query results through the shared query implementation."""

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
    """Structural dispatch-plan validation mirroring court_dispatch_policy rules.

    The full ``validate_dispatch_plan`` path additionally enforces the host-side
    exact preload contract gate (trusted_preload_manifest), which depends on
    internal host state. This structural path covers the same public plan rules
    (roles, superiors, required fields, visibility, instance identity) so MCP
    callers can validate a plan without host preload state.
    """

    if not isinstance(entries, (list, tuple)) or not entries:
        return ["dispatch_plan_must_contain_at_least_one_entry"]
    violations: list[str] = []
    seen_instances: set[str] = set()
    try:
        from court_dispatch_policy import OFFICE_SPECS, VISIBILITIES
    except ImportError:
        return ["dispatch_policy_unavailable"]
    for ordinal, raw in enumerate(entries, start=1):
        if not isinstance(raw, dict):
            violations.append(f"entry_{ordinal}_must_be_object")
            continue
        role = str(raw.get("role") or "").strip().lower()
        if role not in OFFICE_SPECS:
            violations.append(f"entry_{ordinal}_invalid_role:{role or '<empty>'}")
            continue
        office_zh, expected_superior = OFFICE_SPECS[role]
        if str(raw.get("office_zh") or "").strip() != office_zh:
            violations.append(f"entry_{ordinal}_office_zh_mismatch")
        if str(raw.get("direct_superior") or "").strip().lower() != expected_superior:
            violations.append(f"entry_{ordinal}_direct_superior_mismatch")
        for field in ("duty", "evidence_contract", "parallel_group"):
            if not str(raw.get(field) or "").strip():
                violations.append(f"entry_{ordinal}_missing_{field}")
        visibility = str(raw.get("visibility") or "").strip().lower()
        if visibility not in VISIBILITIES:
            violations.append(f"entry_{ordinal}_invalid_visibility:{visibility or '<empty>'}")
        elif visibility != "non_visible":
            violations.append(f"entry_{ordinal}_visibility_must_be_non_visible")
        instance_key = str(raw.get("instance_key") or f"<role>#{ordinal:04d}").strip().lower()
        import re as _re

        if not _re.fullmatch(rf"{_re.escape(role)}#\d{{4}}", instance_key):
            violations.append(f"entry_{ordinal}_invalid_instance_key:{instance_key}")
        elif instance_key in seen_instances:
            violations.append(f"entry_{ordinal}_duplicate_instance_key:{instance_key}")
        seen_instances.add(instance_key)
        dependencies = raw.get("dependency_roles", [])
        if isinstance(dependencies, (list, tuple)):
            roles = [str(item).strip().lower() for item in dependencies if str(item).strip()]
            if len(roles) != len(set(roles)):
                violations.append(f"entry_{ordinal}_duplicate_dependency")
            if role in roles:
                violations.append(f"entry_{ordinal}_self_dependency")
            for item in roles:
                if item not in OFFICE_SPECS:
                    violations.append(f"entry_{ordinal}_invalid_dependency:{item}")
    return violations


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
        "candidates": candidates,
        "count": len(candidates),
    }
