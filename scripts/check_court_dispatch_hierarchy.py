#!/usr/bin/env python3
"""Check the future shared court dispatch hierarchy contract."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import importlib
import json
from pathlib import Path
import sys
from typing import Mapping

sys.dont_write_bytecode = True


SCHEMA = "court.dispatch.hierarchy.check.v1"
DISPATCH_PACKET_SCHEMA = "court.semantic.dispatch_context_packet.v1"
INVARIANT_CAPSULE_SCHEMA = "court.semantic.invariant_capsule.v1"
CHILD_PROFILE_SCHEMA = "court.child_office_profile.v1"
EXISTING_CAPSULE_SHA256 = "a" * 64
MINISTRIES = ("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu")
DIRECT_SUPERIORS = {
    "taizi": "user",
    "zhongshu": "taizi",
    "menxia": "taizi",
    "shangshu": "taizi",
    **{role: "shangshu" for role in MINISTRIES},
}


@dataclass(frozen=True)
class HierarchyCase:
    name: str
    calling_office: str | None
    target_role: str | None
    target_direct_superior: str | None
    instance_kind: str | None
    canonical_authority: bool | None
    owner_role: str | None
    child_profile: Mapping[str, object] | None
    expected_allowed: bool
    expected_reason_codes: tuple[str, ...] = ()


def child_profile(
    role_key: str,
    owner_role: str,
    *,
    child_role: str,
) -> dict[str, object]:
    """Return the complete future child binding carried by the one P00 capsule."""

    return {
        "schema": CHILD_PROFILE_SCHEMA,
        "child_role": child_role,
        "role_key": role_key,
        "office_instance_id": f"{role_key}#worker-0001",
        "owner_role": owner_role,
        "direct_superior": owner_role,
        "canonical_authority": False,
        "instance_kind": "office_worker_instance",
        "bounded_mandate": "perform one bounded hierarchy-check fixture",
        "expected_result": "return structured evidence to the owning ministry",
        "read_scope": [f"work/{owner_role}/input.txt"],
        "write_set": [f"work/{owner_role}/worker-0001.txt"],
        "task_id": "hierarchy-check-task",
        "dispatch_uid": f"hierarchy-check-{owner_role}-worker-0001",
        "shard_id": f"{owner_role}-worker-0001",
        "attempt": 1,
        "profile_sha256": "b" * 64,
        "dossier_sha256": "c" * 64,
        "skill_sha256": "d" * 64,
        "expires_at_utc": "2099-01-01T00:00:00Z",
        "terminal_condition": "stop after the expected result is returned",
        "dispatch_context_packet_schema": DISPATCH_PACKET_SCHEMA,
        "dispatch_context_packet_sha256": "e" * 64,
        "semantic_receipt_sha256": "f" * 64,
        "invariant_capsule_schema": INVARIANT_CAPSULE_SCHEMA,
        "invariant_capsule_sha256": EXISTING_CAPSULE_SHA256,
    }


def _cases() -> tuple[HierarchyCase, ...]:
    cases: list[HierarchyCase] = []
    for role in ("zhongshu", "menxia", "shangshu"):
        cases.append(
            HierarchyCase(
                name=f"allow-taizi-{role}",
                calling_office="taizi",
                target_role=role,
                target_direct_superior="taizi",
                instance_kind="office",
                canonical_authority=True,
                owner_role=None,
                child_profile=None,
                expected_allowed=True,
            )
        )
    for role in MINISTRIES:
        cases.append(
            HierarchyCase(
                name=f"allow-shangshu-{role}",
                calling_office="shangshu",
                target_role=role,
                target_direct_superior="shangshu",
                instance_kind="office",
                canonical_authority=True,
                owner_role=None,
                child_profile=None,
                expected_allowed=True,
            )
        )
        cases.append(
            HierarchyCase(
                name=f"deny-taizi-{role}",
                calling_office="taizi",
                target_role=role,
                target_direct_superior="shangshu",
                instance_kind="office",
                canonical_authority=True,
                owner_role=None,
                child_profile=None,
                expected_allowed=False,
                expected_reason_codes=("dispatch_hierarchy_edge_forbidden",),
            )
        )
    cases.extend(
        (
            HierarchyCase(
                "deny-zhongshu-hubu",
                "zhongshu",
                "hubu",
                "shangshu",
                "office",
                True,
                None,
                None,
                False,
                ("dispatch_hierarchy_edge_forbidden",),
            ),
            HierarchyCase(
                "deny-menxia-libu",
                "menxia",
                "libu",
                "shangshu",
                "office",
                True,
                None,
                None,
                False,
                ("dispatch_hierarchy_edge_forbidden",),
            ),
            HierarchyCase(
                "deny-gongbu-canonical-xingbu",
                "gongbu",
                "xingbu",
                "shangshu",
                "office",
                True,
                None,
                None,
                False,
                ("dispatch_hierarchy_edge_forbidden",),
            ),
        )
    )

    gongbu_child = child_profile("gongbu", "gongbu", child_role="GongBu-GongJiang")
    hubu_child = child_profile("hubu", "hubu", child_role="HuBu-Worker")
    missing_owner = {**gongbu_child, "owner_role": None, "direct_superior": None}
    missing_instance = {key: value for key, value in gongbu_child.items() if key != "office_instance_id"}
    unbounded_child = deepcopy(gongbu_child)
    for field in ("bounded_mandate", "expected_result", "read_scope", "write_set", "terminal_condition"):
        unbounded_child.pop(field, None)
    canonical_role_child = deepcopy(gongbu_child)
    canonical_role_child["child_role"] = "gongbu"
    non_ministry_child = child_profile(
        "zhongshu",
        "zhongshu",
        child_role="Zhongshu-Worker",
    )
    cases.extend(
        (
            HierarchyCase(
                "allow-gongbu-bounded-gongjiang",
                "gongbu",
                "gongbu",
                "gongbu",
                "office_worker_instance",
                False,
                "gongbu",
                gongbu_child,
                True,
            ),
            HierarchyCase(
                "deny-gongbu-hubu-owned-child",
                "gongbu",
                "hubu",
                "hubu",
                "office_worker_instance",
                False,
                "hubu",
                hubu_child,
                False,
                ("dispatch_hierarchy_child_owner_mismatch",),
            ),
            HierarchyCase(
                "deny-caller-profile-mismatch",
                "hubu",
                "gongbu",
                "gongbu",
                "office_worker_instance",
                False,
                "gongbu",
                gongbu_child,
                False,
                ("dispatch_hierarchy_child_owner_mismatch",),
            ),
            HierarchyCase(
                "deny-target-direct-superior-mismatch",
                "shangshu",
                "gongbu",
                "taizi",
                "office",
                True,
                None,
                None,
                False,
                ("dispatch_hierarchy_target_superior_mismatch",),
            ),
            HierarchyCase(
                "deny-missing-caller",
                None,
                "gongbu",
                "shangshu",
                "office",
                True,
                None,
                None,
                False,
                ("dispatch_hierarchy_caller_required",),
            ),
            HierarchyCase(
                "deny-missing-target",
                "shangshu",
                None,
                None,
                "office",
                True,
                None,
                None,
                False,
                ("dispatch_hierarchy_target_required",),
            ),
            HierarchyCase(
                "deny-missing-child-owner",
                "gongbu",
                "gongbu",
                "gongbu",
                "office_worker_instance",
                False,
                None,
                missing_owner,
                False,
                ("dispatch_hierarchy_child_profile_required",),
            ),
            HierarchyCase(
                "deny-missing-child-instance",
                "gongbu",
                "gongbu",
                "gongbu",
                "office_worker_instance",
                False,
                "gongbu",
                missing_instance,
                False,
                ("dispatch_hierarchy_child_profile_required",),
            ),
            HierarchyCase(
                "deny-unbounded-child-scope",
                "gongbu",
                "gongbu",
                "gongbu",
                "office_worker_instance",
                False,
                "gongbu",
                unbounded_child,
                False,
                ("dispatch_hierarchy_child_scope_unbounded",),
            ),
            HierarchyCase(
                "deny-canonical-role-used-as-child",
                "gongbu",
                "gongbu",
                "gongbu",
                "office_worker_instance",
                False,
                "gongbu",
                canonical_role_child,
                False,
                ("dispatch_hierarchy_child_profile_required",),
            ),
            HierarchyCase(
                "deny-non-ministry-child-owner",
                "zhongshu",
                "zhongshu",
                "zhongshu",
                "office_worker_instance",
                False,
                "zhongshu",
                non_ministry_child,
                False,
                ("dispatch_hierarchy_child_owner_mismatch",),
            ),
        )
    )
    return tuple(cases)


CASES = _cases()


def _validator_kwargs(case: HierarchyCase) -> dict[str, object]:
    return {
        "action": "dispatch",
        "calling_office": case.calling_office,
        "target_role": case.target_role,
        "target_direct_superior": case.target_direct_superior,
        "instance_kind": case.instance_kind,
        "canonical_authority": case.canonical_authority,
        "owner_role": case.owner_role,
        "child_profile": deepcopy(case.child_profile),
    }


def _capsule_hashes(value: object) -> set[str]:
    hashes: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "invariant_capsule_sha256" and isinstance(item, str):
                hashes.add(item)
            hashes.update(_capsule_hashes(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            hashes.update(_capsule_hashes(item))
    return hashes


def _check_fixture_table(errors: list[str]) -> dict[str, object]:
    names = [case.name for case in CASES]
    if len(names) != len(set(names)):
        errors.append("HIERARCHY_FIXTURE_NAMES_DUPLICATE")
    expected_names = {
        "allow-taizi-zhongshu",
        "allow-taizi-menxia",
        "allow-taizi-shangshu",
        "deny-zhongshu-hubu",
        "deny-menxia-libu",
        "deny-gongbu-canonical-xingbu",
        "allow-gongbu-bounded-gongjiang",
        "deny-gongbu-hubu-owned-child",
        "deny-caller-profile-mismatch",
        "deny-target-direct-superior-mismatch",
        "deny-missing-caller",
        "deny-missing-target",
        "deny-missing-child-owner",
        "deny-missing-child-instance",
        "deny-unbounded-child-scope",
        "deny-canonical-role-used-as-child",
        "deny-non-ministry-child-owner",
        *{f"allow-shangshu-{role}" for role in MINISTRIES},
        *{f"deny-taizi-{role}" for role in MINISTRIES},
    }
    missing = sorted(expected_names - set(names))
    if missing:
        errors.append("HIERARCHY_FIXTURE_COVERAGE_MISSING:" + ",".join(missing))
    for case in CASES:
        if case.child_profile is None:
            continue
        hashes = _capsule_hashes(case.child_profile)
        if hashes != {EXISTING_CAPSULE_SHA256}:
            errors.append(f"HIERARCHY_P00_CAPSULE_AUTHORITY_DRIFT:{case.name}")
    return {
        "case_count": len(CASES),
        "allowed_count": sum(case.expected_allowed for case in CASES),
        "denied_count": sum(not case.expected_allowed for case in CASES),
        "adapter_projection_calls": ["ordinary", "supercc"],
        "public_api": (
            "validate_dispatch_hierarchy(*, action, calling_office, target_role, "
            "target_direct_superior, instance_kind, canonical_authority, "
            "owner_role=None, child_profile=None)"
        ),
        "single_existing_capsule_sha256": EXISTING_CAPSULE_SHA256,
    }


def _decision_projection(decision: object) -> tuple[object, tuple[object, ...], object]:
    raw_reasons = getattr(decision, "reason_codes", ())
    reasons = tuple(raw_reasons) if isinstance(raw_reasons, (list, tuple)) else (raw_reasons,)
    return (
        getattr(decision, "allowed", None),
        reasons,
        getattr(decision, "edge_class", None),
    )


def _check_manifest_fail_closed(hierarchy: object, errors: list[str]) -> dict[str, object]:
    manifest_path = getattr(hierarchy, "MANIFEST_PATH", None)
    validate_manifest = getattr(hierarchy, "_validate_manifest", None)
    if not isinstance(manifest_path, Path) or not callable(validate_manifest):
        errors.append("HIERARCHY_MANIFEST_VALIDATOR_MISSING")
        return {"status": "MISSING", "invalid_cases_rejected": 0}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutations: dict[str, dict[str, object]] = {}

    duplicate_role = deepcopy(manifest)
    duplicate_role["role_sets"]["three_departments"].append("zhongshu")
    mutations["duplicate_role"] = duplicate_role

    overlapping_role_sets = deepcopy(manifest)
    overlapping_role_sets["role_sets"]["special_lifecycle"][0] = "taizi"
    mutations["overlapping_role_sets"] = overlapping_role_sets

    unsupported_schema = deepcopy(manifest)
    unsupported_schema["schema"] = "court.dispatch_hierarchy.v999"
    mutations["unsupported_schema"] = unsupported_schema

    duplicate_edge = deepcopy(manifest)
    duplicate_edge["allowed_edges"].append(deepcopy(duplicate_edge["allowed_edges"][0]))
    mutations["duplicate_edge"] = duplicate_edge

    non_ministry_child_owner = deepcopy(manifest)
    non_ministry_child_owner["child_office_constraints"]["owner_roles"].append("zhongshu")
    mutations["non_ministry_child_owner"] = non_ministry_child_owner

    superior_mismatch = deepcopy(manifest)
    superior_mismatch["allowed_edges"][1]["target_direct_superior"] = "shangshu"
    mutations["edge_superior_mismatch"] = superior_mismatch

    rejected: list[str] = []
    for name, invalid_manifest in mutations.items():
        try:
            validate_manifest(invalid_manifest)
        except Exception:
            rejected.append(name)
        else:
            errors.append(f"HIERARCHY_INVALID_MANIFEST_ACCEPTED:{name}")
    return {
        "status": "PASSED" if len(rejected) == len(mutations) else "FAILED",
        "invalid_cases_rejected": len(rejected),
        "cases": sorted(rejected),
    }


def _check_shared_validator(errors: list[str]) -> dict[str, object]:
    try:
        hierarchy = importlib.import_module("court_dispatch_hierarchy")
    except Exception as exc:
        raise AssertionError(
            "missing shared enforcement: production module court_dispatch_hierarchy is unavailable"
        ) from exc
    validate = getattr(hierarchy, "validate_dispatch_hierarchy", None)
    if not callable(validate):
        raise AssertionError(
            "missing shared enforcement: court_dispatch_hierarchy.validate_dispatch_hierarchy is unavailable"
        )

    evaluated = 0
    manifest_schemas: set[str] = set()
    manifest_paths: set[str] = set()
    for case in CASES:
        projections: dict[str, tuple[object, tuple[object, ...], object]] = {}
        for adapter_label in ("ordinary", "supercc"):
            try:
                decision = validate(**_validator_kwargs(case))
            except Exception as exc:
                errors.append(
                    f"HIERARCHY_CASE_ERROR:{case.name}:{adapter_label}:"
                    f"{type(exc).__name__}:{exc}"
                )
                continue
            projection = _decision_projection(decision)
            projections[adapter_label] = projection
            manifest_schema = getattr(decision, "hierarchy_schema", None)
            manifest_path = getattr(decision, "hierarchy_manifest_path", None)
            if isinstance(manifest_schema, str):
                manifest_schemas.add(manifest_schema)
            if isinstance(manifest_path, str):
                manifest_paths.add(manifest_path)
            allowed, reason_codes, _edge_class = projection
            if allowed is not case.expected_allowed:
                errors.append(
                    f"HIERARCHY_DECISION_MISMATCH:{case.name}:{adapter_label}:"
                    f"expected={case.expected_allowed}:actual={allowed}"
                )
            if not case.expected_allowed and reason_codes != case.expected_reason_codes:
                errors.append(
                    f"HIERARCHY_REASON_MISMATCH:{case.name}:{adapter_label}:"
                    f"expected={case.expected_reason_codes}:actual={reason_codes}"
                )
            evaluated += 1
        if projections.get("ordinary") != projections.get("supercc"):
            errors.append(f"HIERARCHY_ADAPTER_PARITY_MISMATCH:{case.name}:{projections}")
    if manifest_schemas != {"court.dispatch_hierarchy.v1"}:
        errors.append(f"HIERARCHY_SCHEMA_DRIFT:{sorted(manifest_schemas)}")
    if manifest_paths != {str(hierarchy.MANIFEST_PATH)}:
        errors.append(f"HIERARCHY_MANIFEST_PATH_DRIFT:{sorted(manifest_paths)}")
    manifest_validation = _check_manifest_fail_closed(hierarchy, errors)
    return {
        "module": str(Path(hierarchy.__file__).resolve()),
        "status": "LOADED",
        "evaluated_adapter_cases": evaluated,
        "hierarchy_schema": next(iter(manifest_schemas), None),
        "hierarchy_manifest_path": next(iter(manifest_paths), None),
        "manifest_validation": manifest_validation,
    }


def evaluate() -> dict[str, object]:
    errors: list[str] = []
    fixture_evidence = _check_fixture_table(errors)
    if errors:
        raise AssertionError("invalid hierarchy fixture table: " + "; ".join(errors))
    validator_evidence = _check_shared_validator(errors)
    return {
        "schema": SCHEMA,
        "status": "PASSED" if not errors else "FAILED",
        "first_error": errors[0] if errors else None,
        "errors": errors,
        "evidence": {
            "fixtures": fixture_evidence,
            "shared_validator": validator_evidence,
        },
    }


def main() -> int:
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
