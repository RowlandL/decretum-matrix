#!/usr/bin/env python3
"""Check the highest-priority semantic dispatch and resume contract."""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


SCHEMA = "court.p00.semantic_dispatch_context.check.v1"
P00_HEADING = "## P00 Highest-Priority Semantic Dispatch And Resume Contract"
NEXT_HEADING = "## Unified Dynamic Dispatch Semantics"
REF_RELATIVE_PATH = Path("references/court-state-runtime-agents.md")
REF_HEADING = "## P00 Semantic Dispatch And Resume Unification"
HIERARCHY_MODULE_RELATIVE_PATH = Path("scripts/court_dispatch_hierarchy.py")


def _check_skill(root: Path, errors: list[str]) -> None:
    path = root / "SKILL.md"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"P00_SKILL_UNREADABLE:{type(exc).__name__}:{exc}")
        return
    p00_offset = text.find(P00_HEADING)
    next_offset = text.find(NEXT_HEADING)
    if p00_offset < 0 or next_offset < 0 or p00_offset > next_offset:
        errors.append("P00_SKILL_PRIORITY_MISSING")
    required = (
        "P00_HIGHEST_PRIORITY=REQUIRED",
        "court.semantic.invariant_capsule.v1",
        "semantic_epoch == charter_revision",
        "task_point_projection=POST_MIGRATION_DURABLE_PROJECTION_ONLY",
        "child_agent",
        "worktree_thread",
    )
    missing = [term for term in required if term not in text]
    if missing:
        errors.append("P00_SKILL_CONTRACT_INCOMPLETE:" + ",".join(missing))


def _check_reference(root: Path, errors: list[str]) -> None:
    path = root / REF_RELATIVE_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"P00_GOVERNING_REF_UNREADABLE:{type(exc).__name__}:{exc}")
        return
    required = (
        REF_HEADING,
        "runtime_inline_capsule=EXISTING_SEMANTIC_AUTHORITY",
        "task_point_projection=POST_MIGRATION_DURABLE_PROJECTION_ONLY",
        "court.semantic.dispatch_context_packet.v1",
        "fork_turns=none",
        "registry-first",
        "compatible_instance_policy=REUSE_FIRST",
        "context_occupancy_ratio >= 0.80",
        "parent_role=shangshu",
        "inflight_instance_policy=KEEP_UNTIL_COMPLETE_OR_EXPLICIT_RECALL",
        "carrier_receipt_parity=REQUIRED",
        "disabled_supercc_zero_load=REQUIRED",
        "bounded_child_trace=REQUIRED",
        "granted_by=user|taizi",
        "full_agent_list",
        "full_diff",
        "full_file",
    )
    missing = [term for term in required if term not in text]
    if missing:
        errors.append("P00_GOVERNING_REF_CONTRACT_MISSING:" + ",".join(missing))


def _check_production_api(root: Path, errors: list[str]) -> dict[str, object]:
    scripts_path = str(root / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    try:
        import court_semantic_continuity as continuity
        from check_semantic_continuity import (
            check_p00_bounded_context_packet_preserves_semantic_continuity,
        )
    except Exception as exc:
        errors.append(f"P00_CONTINUITY_API_UNAVAILABLE:{type(exc).__name__}:{exc}")
        return {}
    try:
        check_p00_bounded_context_packet_preserves_semantic_continuity()
    except Exception as exc:
        errors.append(f"P00_PRODUCTION_CHECK_FAILED:{type(exc).__name__}:{exc}")
    if continuity.INVARIANT_CAPSULE_MAX_BYTES != 2048:
        errors.append("P00_INVARIANT_CAPSULE_LIMIT_DRIFT")
    if continuity.DISPATCH_CONTEXT_PACKET_MAX_BYTES != 2048:
        errors.append("P00_DISPATCH_PACKET_LIMIT_DRIFT")
    return {
        "production_check": (
            "check_semantic_continuity."
            "check_p00_bounded_context_packet_preserves_semantic_continuity"
        ),
        "invariant_capsule_schema": continuity.INVARIANT_CAPSULE_SCHEMA,
        "dispatch_packet_schema": continuity.DISPATCH_CONTEXT_PACKET_SCHEMA,
        "max_bytes": 2048,
    }


def _check_hierarchy_child_binding(root: Path, errors: list[str]) -> dict[str, object]:
    """Behaviorally require one existing P00 capsule for a bounded child."""

    scripts_path = str(root / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    try:
        hierarchy = importlib.import_module("court_dispatch_hierarchy")
    except ModuleNotFoundError:
        errors.append("P00_HIERARCHY_CHILD_BINDING_API_MISSING:scripts/court_dispatch_hierarchy.py")
        return {
            "path": HIERARCHY_MODULE_RELATIVE_PATH.as_posix(),
            "status": "MISSING",
        }
    except Exception as exc:
        errors.append(f"P00_HIERARCHY_CHILD_BINDING_API_UNREADABLE:{type(exc).__name__}:{exc}")
        return {
            "path": HIERARCHY_MODULE_RELATIVE_PATH.as_posix(),
            "status": "UNREADABLE",
        }
    validate = getattr(hierarchy, "validate_dispatch_hierarchy", None)
    if not callable(validate):
        errors.append("P00_HIERARCHY_CHILD_BINDING_PUBLIC_API_MISSING")
        return {
            "path": HIERARCHY_MODULE_RELATIVE_PATH.as_posix(),
            "status": "API_MISSING",
        }

    child_profile: dict[str, object] = {
        "schema": "court.child_office_profile.v1",
        "child_role": "GongBu-GongJiang",
        "role_key": "gongbu",
        "office_instance_id": "gongbu#worker-0001",
        "owner_role": "gongbu",
        "direct_superior": "gongbu",
        "canonical_authority": False,
        "instance_kind": "office_worker_instance",
        "bounded_mandate": "perform one bounded P00 hierarchy fixture",
        "expected_result": "return structured evidence to Gongbu",
        "read_scope": ["work/gongbu/input.txt"],
        "write_set": ["work/gongbu/worker-0001.txt"],
        "task_id": "p00-hierarchy-child-task",
        "dispatch_uid": "p00-hierarchy-child-dispatch",
        "shard_id": "gongbu-worker-0001",
        "attempt": 1,
        "profile_sha256": "b" * 64,
        "dossier_sha256": "c" * 64,
        "skill_sha256": "d" * 64,
        "expires_at_utc": "2099-01-01T00:00:00Z",
        "terminal_condition": "stop after the expected result is returned",
        "dispatch_context_packet_schema": "court.semantic.dispatch_context_packet.v1",
        "dispatch_context_packet_sha256": "e" * 64,
        "semantic_receipt_sha256": "f" * 64,
        "invariant_capsule_schema": "court.semantic.invariant_capsule.v1",
        "invariant_capsule_sha256": "a" * 64,
    }
    kwargs = {
        "action": "dispatch",
        "calling_office": "gongbu",
        "target_role": "gongbu",
        "target_direct_superior": "gongbu",
        "instance_kind": "office_worker_instance",
        "canonical_authority": False,
        "owner_role": "gongbu",
    }
    try:
        allowed = validate(**kwargs, child_profile=deepcopy(child_profile))
        second_capsule_profile = deepcopy(child_profile)
        second_capsule_profile["second_invariant_capsule"] = {
            "schema": "court.semantic.invariant_capsule.v1",
            "sha256": "1" * 64,
        }
        denied = validate(**kwargs, child_profile=second_capsule_profile)
    except Exception as exc:
        errors.append(f"P00_HIERARCHY_CHILD_BINDING_BEHAVIOR_FAILED:{type(exc).__name__}:{exc}")
        return {
            "path": HIERARCHY_MODULE_RELATIVE_PATH.as_posix(),
            "status": "BEHAVIOR_ERROR",
        }
    allowed_reasons = tuple(getattr(allowed, "reason_codes", ()) or ())
    denied_reasons = tuple(getattr(denied, "reason_codes", ()) or ())
    if getattr(allowed, "allowed", None) is not True:
        errors.append(
            "P00_HIERARCHY_VALID_SAME_OWNER_CHILD_REJECTED:" + ",".join(map(str, allowed_reasons))
        )
    if getattr(denied, "allowed", None) is not False:
        errors.append("P00_SECOND_CAPSULE_CHILD_PROFILE_ACCEPTED")
    return {
        "path": HIERARCHY_MODULE_RELATIVE_PATH.as_posix(),
        "status": "BEHAVIOR_CHECKED",
        "valid_same_owner_child_allowed": getattr(allowed, "allowed", None),
        "valid_reason_codes": list(allowed_reasons),
        "second_capsule_child_rejected": getattr(denied, "allowed", None) is False,
        "second_capsule_reason_codes": list(denied_reasons),
        "single_capsule_sha256": child_profile["invariant_capsule_sha256"],
    }


def evaluate(root: Path) -> dict[str, object]:
    errors: list[str] = []
    _check_skill(root, errors)
    _check_reference(root, errors)
    evidence = _check_production_api(root, errors)
    evidence["hierarchy_child_binding"] = _check_hierarchy_child_binding(root, errors)
    return {
        "schema": SCHEMA,
        "status": "PASSED" if not errors else "FAILED",
        "first_error": errors[0] if errors else None,
        "errors": errors,
        "evidence": evidence,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Skill root to validate.",
    )
    args = parser.parse_args(argv)
    result = evaluate(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
