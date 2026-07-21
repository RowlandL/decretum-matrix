"""Data-backed, mode-neutral court dispatch hierarchy validation."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Mapping, Sequence

sys.dont_write_bytecode = True


HIERARCHY_SCHEMA = "court.dispatch_hierarchy.v1"
MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "references"
    / "manifests"
    / "court-dispatch-hierarchy.v1.json"
)

_EXPECTED_ROLE_SETS = {
    "taizi": ("taizi",),
    "three_departments": ("zhongshu", "menxia", "shangshu"),
    "six_ministries": ("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"),
    "special_lifecycle": ("shiguan", "shiguan-hermes", "zaochao", "patrol-inspector"),
}
_EXPECTED_CANONICAL_SUPERIORS = {
    "taizi": "user",
    "zhongshu": "taizi",
    "menxia": "taizi",
    "shangshu": "taizi",
    "libu-hr": "shangshu",
    "hubu": "shangshu",
    "libu": "shangshu",
    "bingbu": "shangshu",
    "xingbu": "shangshu",
    "gongbu": "shangshu",
    "shiguan": "taizi/menxia",
    "shiguan-hermes": "taizi/menxia",
    "zaochao": "taizi",
    "patrol-inspector": "taizi",
}
_EXPECTED_STATIC_EDGES = {
    ("court_entry", "dispatch", "user", "taizi", "user"),
    *{
        ("deliberation_dispatch", "dispatch", "taizi", role, "taizi")
        for role in _EXPECTED_ROLE_SETS["three_departments"]
    },
    *{
        ("ministry_execution_dispatch", "dispatch", "shangshu", role, "shangshu")
        for role in _EXPECTED_ROLE_SETS["six_ministries"]
    },
}
_EXPECTED_CHILD_KINDS = ("worker", "craftsman", "office_worker_instance")
_CANONICAL_INSTANCE_KINDS = frozenset({"office", "canonical_authority"})
_REQUIRED_REASON_CODES = frozenset(
    {
        "dispatch_hierarchy_action_required",
        "dispatch_hierarchy_unknown_action",
        "dispatch_hierarchy_caller_required",
        "dispatch_hierarchy_target_required",
        "dispatch_hierarchy_unknown_caller",
        "dispatch_hierarchy_unknown_target",
        "dispatch_hierarchy_edge_forbidden",
        "dispatch_hierarchy_target_superior_mismatch",
        "dispatch_hierarchy_target_profile_required",
        "dispatch_hierarchy_child_profile_required",
        "dispatch_hierarchy_child_owner_mismatch",
        "dispatch_hierarchy_child_scope_unbounded",
        "dispatch_hierarchy_child_semantic_authority_mismatch",
        "dispatch_hierarchy_manifest_invalid",
    }
)


@dataclass(frozen=True)
class DispatchHierarchyDecision:
    """Stable result shared by ordinary and superCC adapters."""

    allowed: bool
    edge_class: str | None
    normalized_caller: str | None
    normalized_target: str | None
    normalized_owner: str | None
    reason_codes: tuple[str, ...]
    hierarchy_schema: str
    hierarchy_manifest_path: str


class _ManifestInvalid(ValueError):
    pass


def _exact_lower_token(value: object) -> tuple[str | None, bool]:
    if not isinstance(value, str):
        return None, False
    if not value.strip():
        return None, False
    if value != value.strip() or value != value.casefold():
        return None, True
    return value, True


def _require_exact_string_list(
    value: object,
    *,
    field: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise _ManifestInvalid(f"{field} must be a non-empty array")
    normalized: list[str] = []
    for item in value:
        token, supplied = _exact_lower_token(item)
        if not supplied or token is None:
            raise _ManifestInvalid(f"{field} must contain exact lowercase tokens")
        normalized.append(token)
    if len(normalized) != len(set(normalized)):
        raise _ManifestInvalid(f"{field} contains duplicates")
    return tuple(normalized)


def _validate_manifest(manifest: object) -> dict[str, object]:
    if not isinstance(manifest, dict):
        raise _ManifestInvalid("manifest root must be an object")
    if manifest.get("schema") != HIERARCHY_SCHEMA:
        raise _ManifestInvalid("unsupported hierarchy schema")
    if manifest.get("deny_by_default") is not True:
        raise _ManifestInvalid("deny_by_default must be true")

    role_sets = manifest.get("role_sets")
    if not isinstance(role_sets, dict) or set(role_sets) != set(_EXPECTED_ROLE_SETS):
        raise _ManifestInvalid("role_sets keys mismatch")
    normalized_role_sets: dict[str, tuple[str, ...]] = {}
    all_roles: list[str] = []
    for name, expected in _EXPECTED_ROLE_SETS.items():
        roles = _require_exact_string_list(role_sets.get(name), field=f"role_sets.{name}")
        if roles != expected:
            raise _ManifestInvalid(f"role_sets.{name} mismatch")
        normalized_role_sets[name] = roles
        all_roles.extend(roles)
    if len(all_roles) != len(set(all_roles)):
        raise _ManifestInvalid("canonical role sets overlap")

    canonical_roles = manifest.get("canonical_roles")
    if not isinstance(canonical_roles, dict) or set(canonical_roles) != set(all_roles):
        raise _ManifestInvalid("canonical_roles mismatch")
    for role, expected_superior in _EXPECTED_CANONICAL_SUPERIORS.items():
        profile = canonical_roles.get(role)
        if (
            not isinstance(profile, dict)
            or set(profile) != {"direct_superior"}
            or profile.get("direct_superior") != expected_superior
        ):
            raise _ManifestInvalid(f"canonical role direct superior mismatch: {role}")

    raw_edges = manifest.get("allowed_edges")
    if not isinstance(raw_edges, list) or not raw_edges:
        raise _ManifestInvalid("allowed_edges must be a non-empty array")
    normalized_edges: set[tuple[str, str, str, str, str]] = set()
    for raw in raw_edges:
        if not isinstance(raw, dict):
            raise _ManifestInvalid("allowed edge must be an object")
        required = {
            "edge_class",
            "action",
            "caller",
            "target",
            "target_direct_superior",
        }
        if set(raw) != required:
            raise _ManifestInvalid("allowed edge shape mismatch")
        values: list[str] = []
        for field in (
            "edge_class",
            "action",
            "caller",
            "target",
            "target_direct_superior",
        ):
            token, supplied = _exact_lower_token(raw.get(field))
            if not supplied or token is None:
                raise _ManifestInvalid(f"allowed edge {field} must be exact lowercase")
            values.append(token)
        edge = tuple(values)
        if edge in normalized_edges:
            raise _ManifestInvalid("duplicate allowed edge")
        normalized_edges.add(edge)
    if normalized_edges != _EXPECTED_STATIC_EDGES:
        raise _ManifestInvalid("allowed edge coverage mismatch")

    child = manifest.get("child_office_constraints")
    if not isinstance(child, dict):
        raise _ManifestInvalid("child_office_constraints missing")
    if child.get("edge_class") != "bounded_child_office" or child.get("action") != "dispatch":
        raise _ManifestInvalid("child edge contract mismatch")
    owners = _require_exact_string_list(
        child.get("owner_roles"),
        field="child_office_constraints.owner_roles",
    )
    if owners != normalized_role_sets["six_ministries"]:
        raise _ManifestInvalid("child owner roles mismatch")
    kinds = _require_exact_string_list(
        child.get("allowed_instance_kinds"),
        field="child_office_constraints.allowed_instance_kinds",
    )
    if kinds != _EXPECTED_CHILD_KINDS:
        raise _ManifestInvalid("child instance kinds mismatch")
    required_fields = _require_exact_string_list(
        child.get("required_fields"),
        field="child_office_constraints.required_fields",
    )
    portable_fields = _require_exact_string_list(
        child.get("portable_scope_fields"),
        field="child_office_constraints.portable_scope_fields",
    )
    if set(portable_fields) != {"read_scope", "write_set"}:
        raise _ManifestInvalid("portable scope fields mismatch")

    reasons = _require_exact_string_list(
        manifest.get("rejection_reason_codes"),
        field="rejection_reason_codes",
    )
    if not _REQUIRED_REASON_CODES.issubset(reasons):
        raise _ManifestInvalid("required rejection reason missing")

    return {
        "role_sets": normalized_role_sets,
        "canonical_roles": canonical_roles,
        "allowed_edges": normalized_edges,
        "child": {
            "edge_class": child["edge_class"],
            "profile_schema": child.get("profile_schema"),
            "owner_roles": owners,
            "allowed_instance_kinds": kinds,
            "required_fields": required_fields,
        },
    }


@lru_cache(maxsize=1)
def _manifest_bundle() -> dict[str, object]:
    try:
        parsed = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _ManifestInvalid("hierarchy manifest is not valid JSON") from exc
    return _validate_manifest(parsed)


def _decision(
    *,
    allowed: bool,
    edge_class: str | None,
    caller: str | None,
    target: str | None,
    owner: str | None,
    reasons: Sequence[str] = (),
) -> DispatchHierarchyDecision:
    return DispatchHierarchyDecision(
        allowed=allowed,
        edge_class=edge_class,
        normalized_caller=caller,
        normalized_target=target,
        normalized_owner=owner,
        reason_codes=tuple(reasons),
        hierarchy_schema=HIERARCHY_SCHEMA,
        hierarchy_manifest_path=str(MANIFEST_PATH),
    )


def _portable_paths(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, (list, tuple)) or not value:
        return None
    normalized: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            return None
        candidate = raw.strip()
        if (
            not candidate
            or candidate != raw
            or "\\" in candidate
            or candidate.startswith("/")
            or re.match(r"^[A-Za-z]:", candidate)
            or "\x00" in candidate
        ):
            return None
        parts = PurePosixPath(candidate).parts
        if not parts or any(part in {"", ".", ".."} or ":" in part for part in parts):
            return None
        normalized.append("/".join(parts))
    if len(normalized) != len(set(path.casefold() for path in normalized)):
        return None
    return tuple(normalized)


def _has_forbidden_semantic_authority(value: object) -> bool:
    forbidden = {
        "authority_revision",
        "authority_source",
        "plan_revision",
        "plan_source",
        "semantic_receipt_id",
        "invariant_capsule_id",
    }
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            if str(raw_key) in forbidden:
                return True
            if _has_forbidden_semantic_authority(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_has_forbidden_semantic_authority(item) for item in value)
    return False


def _validate_child_profile(
    *,
    manifest: dict[str, object],
    caller: str,
    target: str,
    target_direct_superior: object,
    instance_kind: object,
    canonical_authority: object,
    owner: str | None,
    child_profile: object,
) -> DispatchHierarchyDecision:
    child = manifest["child"]
    assert isinstance(child, dict)
    if not isinstance(child_profile, Mapping):
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_child_profile_required",),
        )
    required_fields = child["required_fields"]
    assert isinstance(required_fields, tuple)
    if any(field not in child_profile or child_profile.get(field) in (None, "") for field in required_fields):
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_child_profile_required",),
        )
    if _has_forbidden_semantic_authority(child_profile):
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_child_semantic_authority_mismatch",),
        )

    profile_owner, profile_owner_supplied = _exact_lower_token(child_profile.get("owner_role"))
    profile_superior, profile_superior_supplied = _exact_lower_token(
        child_profile.get("direct_superior")
    )
    profile_role, profile_role_supplied = _exact_lower_token(child_profile.get("role_key"))
    profile_kind, profile_kind_supplied = _exact_lower_token(child_profile.get("instance_kind"))
    requested_kind, requested_kind_supplied = _exact_lower_token(instance_kind)
    if not all(
        (
            profile_owner_supplied,
            profile_superior_supplied,
            profile_role_supplied,
            profile_kind_supplied,
            requested_kind_supplied,
        )
    ) or None in (profile_owner, profile_superior, profile_role, profile_kind, requested_kind):
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_child_profile_required",),
        )
    owner_roles = frozenset(child["owner_roles"])
    allowed_kinds = frozenset(child["allowed_instance_kinds"])
    if (
        owner is None
        or owner not in owner_roles
        or profile_owner != owner
        or profile_superior != owner
        or profile_role != owner
        or target != owner
        or caller != owner
    ):
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_child_owner_mismatch",),
        )
    target_superior, target_superior_supplied = _exact_lower_token(target_direct_superior)
    if not target_superior_supplied or target_superior != owner:
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_target_superior_mismatch",),
        )
    if (
        requested_kind not in allowed_kinds
        or profile_kind != requested_kind
        or canonical_authority is not False
        or child_profile.get("canonical_authority") is not False
    ):
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_child_profile_required",),
        )

    canonical_roles = manifest["canonical_roles"]
    assert isinstance(canonical_roles, dict)
    child_role = child_profile.get("child_role")
    if (
        not isinstance(child_role, str)
        or not child_role.strip()
        or child_role != child_role.strip()
        or child_role.casefold() in canonical_roles
        or child_role.casefold() == "user"
    ):
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_child_profile_required",),
        )
    bounded_text_fields = ("bounded_mandate", "expected_result", "terminal_condition")
    if (
        any(
            not isinstance(child_profile.get(field), str)
            or not str(child_profile.get(field)).strip()
            for field in bounded_text_fields
        )
        or _portable_paths(child_profile.get("read_scope")) is None
        or _portable_paths(child_profile.get("write_set")) is None
    ):
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_child_scope_unbounded",),
        )
    if child_profile.get("schema") != child["profile_schema"]:
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_child_semantic_authority_mismatch",),
        )
    return _decision(
        allowed=True,
        edge_class=str(child["edge_class"]),
        caller=caller,
        target=target,
        owner=owner,
    )


def validate_dispatch_hierarchy(
    *,
    action: object,
    calling_office: object,
    target_role: object,
    target_direct_superior: object,
    instance_kind: object,
    canonical_authority: object,
    owner_role: object = None,
    child_profile: object = None,
) -> DispatchHierarchyDecision:
    """Validate one normalized court dispatch edge without transport side effects."""

    try:
        manifest = _manifest_bundle()
    except _ManifestInvalid:
        return _decision(
            allowed=False,
            edge_class=None,
            caller=None,
            target=None,
            owner=None,
            reasons=("dispatch_hierarchy_manifest_invalid",),
        )

    normalized_action, action_supplied = _exact_lower_token(action)
    if not action_supplied:
        return _decision(
            allowed=False,
            edge_class=None,
            caller=None,
            target=None,
            owner=None,
            reasons=("dispatch_hierarchy_action_required",),
        )
    if normalized_action != "dispatch":
        return _decision(
            allowed=False,
            edge_class=None,
            caller=None,
            target=None,
            owner=None,
            reasons=("dispatch_hierarchy_unknown_action",),
        )

    caller, caller_supplied = _exact_lower_token(calling_office)
    if not caller_supplied:
        return _decision(
            allowed=False,
            edge_class=None,
            caller=None,
            target=None,
            owner=None,
            reasons=("dispatch_hierarchy_caller_required",),
        )
    target, target_supplied = _exact_lower_token(target_role)
    if not target_supplied:
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=None,
            owner=None,
            reasons=("dispatch_hierarchy_target_required",),
        )
    owner, owner_supplied = _exact_lower_token(owner_role)

    canonical_roles = manifest["canonical_roles"]
    assert isinstance(canonical_roles, dict)
    known_callers = {"user", *canonical_roles}
    if caller is None or caller not in known_callers:
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_unknown_caller",),
        )
    if target is None or target not in canonical_roles:
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_unknown_target",),
        )

    normalized_kind, kind_supplied = _exact_lower_token(instance_kind)
    child_kinds = frozenset(manifest["child"]["allowed_instance_kinds"])
    is_child = (
        canonical_authority is False
        or (kind_supplied and normalized_kind in child_kinds)
        or child_profile is not None
        or owner_supplied
    )
    if is_child:
        return _validate_child_profile(
            manifest=manifest,
            caller=caller,
            target=target,
            target_direct_superior=target_direct_superior,
            instance_kind=instance_kind,
            canonical_authority=canonical_authority,
            owner=owner,
            child_profile=child_profile,
        )

    target_superior, target_superior_supplied = _exact_lower_token(target_direct_superior)
    expected_superior = canonical_roles[target].get("direct_superior")
    if not target_superior_supplied or target_superior != expected_superior:
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=None,
            reasons=("dispatch_hierarchy_target_superior_mismatch",),
        )
    if (
        not kind_supplied
        or normalized_kind not in _CANONICAL_INSTANCE_KINDS
        or canonical_authority is not True
        or owner_supplied
        or child_profile is not None
    ):
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=owner,
            reasons=("dispatch_hierarchy_target_profile_required",),
        )

    edge = next(
        (
            candidate
            for candidate in manifest["allowed_edges"]
            if candidate[1] == "dispatch"
            and candidate[2] == caller
            and candidate[3] == target
            and candidate[4] == target_superior
        ),
        None,
    )
    if edge is None:
        return _decision(
            allowed=False,
            edge_class=None,
            caller=caller,
            target=target,
            owner=None,
            reasons=("dispatch_hierarchy_edge_forbidden",),
        )
    return _decision(
        allowed=True,
        edge_class=edge[0],
        caller=caller,
        target=target,
        owner=None,
    )
