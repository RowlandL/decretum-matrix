"""Governance-neutral contracts layered over the existing court runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping


REGISTRY_SCHEMA = "decretum.governance.registry.v1"
IMPLEMENTATION_SCHEMA = "decretum.governance.implementation.v1"
COURT_HIERARCHY_SCHEMA = "court.dispatch_hierarchy.v1"
DEFAULT_GOVERNANCE_ID = "three-departments-six-ministries"
REQUIRED_CAPABILITIES = frozenset(
    {
        "intake",
        "interpretation",
        "ruling",
        "coordination",
        "action",
        "validation",
        "presentation",
    }
)
REQUIRED_FRAMEWORK_SERVICES = {
    "state": "court-runtime",
    "evidence": "court-runtime",
    "memory": "shiguan-gbrain",
}
SEMANTIC_RECORD_SCHEMA = "decretum.semantic.record.v1"
SEMANTIC_KINDS = frozenset(
    {"fact", "interpretation", "ruling", "action", "validation", "memory", "presentation"}
)
_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class GovernanceContractError(ValueError):
    """Raised when a governance implementation violates framework boundaries."""


@dataclass(frozen=True)
class GovernanceEdge:
    edge_class: str
    caller: str
    target: str
    target_direct_superior: str


@dataclass(frozen=True)
class GovernanceImplementation:
    implementation_id: str
    display_name: str
    version: str
    status: str
    adapter: str
    roles: Mapping[str, str]
    capability_bindings: Mapping[str, tuple[str, ...]]
    allowed_edges: tuple[GovernanceEdge, ...]
    framework_services: Mapping[str, str]
    manifest_path: Path
    manifest_sha256: str


@dataclass(frozen=True)
class GovernanceDecision:
    allowed: bool
    edge_class: str | None
    reason_codes: tuple[str, ...]


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise GovernanceContractError(f"invalid_{field}")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise GovernanceContractError(f"invalid_{field}")
    return value


def _load_json(path: Path) -> tuple[dict[str, object], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GovernanceContractError(f"manifest_unreadable:{path.name}") from exc
    if not isinstance(value, dict):
        raise GovernanceContractError(f"manifest_root_invalid:{path.name}")
    return value, hashlib.sha256(raw).hexdigest()


def _manifest_path(root: Path, value: object) -> Path:
    relative = Path(_text(value, "manifest_path"))
    if relative.is_absolute() or ".." in relative.parts:
        raise GovernanceContractError("manifest_path_escape")
    manifest_root = (root / "references" / "manifests").resolve()
    path = (manifest_root / relative).resolve()
    try:
        path.relative_to(manifest_root)
    except ValueError as exc:
        raise GovernanceContractError("manifest_path_escape") from exc
    return path


def _roles(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise GovernanceContractError("roles_required")
    roles: dict[str, str] = {}
    for raw_role, raw_profile in value.items():
        role = _token(raw_role, "role")
        if not isinstance(raw_profile, dict):
            raise GovernanceContractError(f"role_profile_invalid:{role}")
        superior = _text(raw_profile.get("direct_superior"), "direct_superior")
        roles[role] = superior
    return roles


def _edges(value: object, roles: Mapping[str, str]) -> tuple[GovernanceEdge, ...]:
    if not isinstance(value, list) or not value:
        raise GovernanceContractError("allowed_edges_required")
    edges: list[GovernanceEdge] = []
    seen: set[tuple[str, str, str, str]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise GovernanceContractError("allowed_edge_invalid")
        edge = GovernanceEdge(
            edge_class=_token(raw.get("edge_class"), "edge_class"),
            caller=_token(raw.get("caller"), "edge_caller"),
            target=_token(raw.get("target"), "edge_target"),
            target_direct_superior=_text(
                raw.get("target_direct_superior"),
                "edge_target_direct_superior",
            ),
        )
        identity = (
            edge.edge_class,
            edge.caller,
            edge.target,
            edge.target_direct_superior,
        )
        if identity in seen:
            raise GovernanceContractError("duplicate_allowed_edge")
        if edge.target not in roles:
            raise GovernanceContractError("edge_target_unknown")
        if edge.caller != "user" and edge.caller not in roles:
            raise GovernanceContractError("edge_caller_unknown")
        if roles[edge.target] != edge.target_direct_superior:
            raise GovernanceContractError("edge_superior_mismatch")
        seen.add(identity)
        edges.append(edge)
    return tuple(edges)


def _bindings(value: object, roles: Mapping[str, str]) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict) or set(value) != REQUIRED_CAPABILITIES:
        raise GovernanceContractError("capability_bindings_mismatch")
    bindings: dict[str, tuple[str, ...]] = {}
    for capability in sorted(REQUIRED_CAPABILITIES):
        raw_roles = value.get(capability)
        if not isinstance(raw_roles, list) or not raw_roles:
            raise GovernanceContractError(f"capability_binding_required:{capability}")
        normalized = tuple(_token(role, "capability_role") for role in raw_roles)
        if len(normalized) != len(set(normalized)):
            raise GovernanceContractError(f"capability_binding_duplicate:{capability}")
        if any(role not in roles for role in normalized):
            raise GovernanceContractError(f"capability_role_unknown:{capability}")
        bindings[capability] = normalized
    return bindings


def _implementation(
    *,
    root: Path,
    entry: dict[str, object],
    framework_services: Mapping[str, str],
) -> GovernanceImplementation:
    implementation_id = _token(entry.get("id"), "implementation_id")
    adapter = _token(entry.get("adapter"), "adapter")
    if adapter not in {"court-dispatch-hierarchy", "generic"}:
        raise GovernanceContractError(f"unsupported_adapter:{adapter}")
    path = _manifest_path(root, entry.get("manifest"))
    manifest, digest = _load_json(path)
    if adapter == "court-dispatch-hierarchy":
        if manifest.get("schema") != COURT_HIERARCHY_SCHEMA:
            raise GovernanceContractError("court_hierarchy_schema_mismatch")
        roles = _roles(manifest.get("canonical_roles"))
    else:
        if manifest.get("schema") != IMPLEMENTATION_SCHEMA:
            raise GovernanceContractError("implementation_schema_mismatch")
        if manifest.get("id") != implementation_id or manifest.get("deny_by_default") is not True:
            raise GovernanceContractError("implementation_identity_mismatch")
        roles = _roles(manifest.get("roles"))
    edges = _edges(manifest.get("allowed_edges"), roles)
    bindings = _bindings(entry.get("capability_bindings"), roles)
    return GovernanceImplementation(
        implementation_id=implementation_id,
        display_name=_text(entry.get("display_name"), "display_name"),
        version=_text(entry.get("version"), "version"),
        status=_token(entry.get("status"), "status"),
        adapter=adapter,
        roles=roles,
        capability_bindings=bindings,
        allowed_edges=edges,
        framework_services=dict(framework_services),
        manifest_path=path,
        manifest_sha256=digest,
    )


def load_governance_registry(root: Path | None = None) -> dict[str, object]:
    skill_root = (root or Path(__file__).resolve().parents[1]).resolve()
    path = skill_root / "references" / "manifests" / "governance-implementations.v1.json"
    value, _ = _load_json(path)
    if set(value) != {"schema", "default_id", "framework_services", "implementations"}:
        raise GovernanceContractError("registry_shape_mismatch")
    if value.get("schema") != REGISTRY_SCHEMA:
        raise GovernanceContractError("registry_schema_mismatch")
    default_id = _token(value.get("default_id"), "default_id")
    services = value.get("framework_services")
    if services != REQUIRED_FRAMEWORK_SERVICES:
        raise GovernanceContractError("framework_authority_mismatch")
    entries = value.get("implementations")
    if not isinstance(entries, list) or not entries:
        raise GovernanceContractError("implementations_required")
    implementations: dict[str, GovernanceImplementation] = {}
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            raise GovernanceContractError("implementation_entry_invalid")
        implementation = _implementation(
            root=skill_root,
            entry=raw_entry,
            framework_services=REQUIRED_FRAMEWORK_SERVICES,
        )
        if implementation.implementation_id in implementations:
            raise GovernanceContractError("duplicate_implementation_id")
        implementations[implementation.implementation_id] = implementation
    defaults = [item for item in implementations.values() if item.status == "default"]
    if len(defaults) != 1 or defaults[0].implementation_id != default_id:
        raise GovernanceContractError("registry_default_mismatch")
    return {
        "schema": REGISTRY_SCHEMA,
        "default_id": default_id,
        "implementations": implementations,
    }


def evaluate_dispatch(
    implementation: GovernanceImplementation,
    *,
    caller: str,
    target: str,
    target_direct_superior: str,
) -> GovernanceDecision:
    identity = (caller, target, target_direct_superior)
    for edge in implementation.allowed_edges:
        if identity == (edge.caller, edge.target, edge.target_direct_superior):
            return GovernanceDecision(True, edge.edge_class, ())
    return GovernanceDecision(False, None, ("governance_edge_forbidden",))


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def validate_semantic_trace(
    records: object,
    implementation: GovernanceImplementation,
) -> dict[str, object]:
    """Validate fact-to-presentation relations without storing a second ledger."""

    errors: list[str] = []
    if not isinstance(records, list) or not records:
        return {
            "schema": "decretum.semantic.trace_validation.v1",
            "gate": "FAILED",
            "record_count": 0,
            "errors": ["semantic_trace_required"],
        }

    normalized: dict[str, dict[str, object]] = {}
    time_windows: dict[str, tuple[datetime, datetime | None]] = {}
    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            errors.append(f"semantic_record_invalid:{index}")
            continue
        record_id = raw.get("record_id")
        kind = raw.get("kind")
        if not isinstance(record_id, str) or not _TOKEN_RE.fullmatch(record_id):
            errors.append(f"record_id_invalid:{index}")
            continue
        if record_id in normalized:
            errors.append(f"record_id_duplicate:{record_id}")
            continue
        if raw.get("schema") != SEMANTIC_RECORD_SCHEMA:
            errors.append(f"record_schema_invalid:{record_id}")
        if kind not in SEMANTIC_KINDS:
            errors.append(f"record_kind_invalid:{record_id}")
            continue
        for field in ("subject", "actor", "scope", "authority"):
            if not isinstance(raw.get(field), str) or not str(raw[field]).strip():
                errors.append(f"record_field_invalid:{record_id}:{field}")
        if raw.get("governance_id") != implementation.implementation_id:
            errors.append(f"record_governance_mismatch:{record_id}")
        if not isinstance(raw.get("execution_authority"), bool):
            errors.append(f"record_execution_authority_invalid:{record_id}")
        digest = raw.get("content_sha256")
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            errors.append(f"record_digest_invalid:{record_id}")
        basis = raw.get("basis")
        if not isinstance(basis, list) or any(
            not isinstance(item, str) or not _TOKEN_RE.fullmatch(item) for item in basis
        ):
            errors.append(f"record_basis_invalid:{record_id}")
            basis = []
        valid_from = _timestamp(raw.get("valid_from"))
        valid_until = _timestamp(raw.get("valid_until")) if "valid_until" in raw else None
        if valid_from is None:
            errors.append(f"valid_from_invalid:{record_id}")
        elif "valid_until" in raw and valid_until is None:
            errors.append(f"valid_until_invalid:{record_id}")
        elif valid_until is not None and valid_until < valid_from:
            errors.append(f"validity_window_invalid:{kind}")
        if valid_from is not None:
            time_windows[record_id] = (valid_from, valid_until)
        normalized[record_id] = {**raw, "basis": basis}

    if not any(
        record.get("kind") == "fact"
        and record.get("subject") == "latest_user_decree"
        and record.get("authority") == "controlling"
        for record in normalized.values()
    ):
        errors.append("latest_user_decree_missing")

    requirements = {
        "interpretation": (frozenset({"fact"}), "all"),
        "ruling": (frozenset({"fact", "interpretation"}), "any"),
        "action": (frozenset({"ruling"}), "all"),
        "validation": (frozenset({"action", "fact"}), "all"),
        "memory": (frozenset({"fact", "validation"}), "any"),
        "presentation": (frozenset({"ruling", "validation"}), "any"),
    }
    for record_id, record in normalized.items():
        kind = str(record["kind"])
        basis_kinds: set[str] = set()
        for basis_id in record["basis"]:
            upstream = normalized.get(str(basis_id))
            if upstream is None:
                errors.append(f"basis_record_missing:{record_id}:{basis_id}")
            else:
                basis_kinds.add(str(upstream["kind"]))
        requirement = requirements.get(kind)
        if requirement is not None:
            required, mode = requirement
            missing = required - basis_kinds
            failed = bool(missing) if mode == "all" else not bool(required & basis_kinds)
            if failed:
                label = sorted(missing if mode == "all" else required)[0]
                errors.append(f"basis_kind_missing:{kind}:{label}")

        execution_authority = record.get("execution_authority")
        if execution_authority is True and kind != "action":
            errors.append(f"{kind}_execution_authority_forbidden")
        if kind == "memory":
            if record.get("actor") != "shiguan-gbrain":
                errors.append("memory_actor_mismatch")
        elif kind not in {"fact"}:
            allowed_actors = implementation.capability_bindings.get(kind, ())
            if record.get("actor") not in allowed_actors:
                errors.append(f"actor_capability_mismatch:{kind}")

    return {
        "schema": "decretum.semantic.trace_validation.v1",
        "gate": "PASSED" if not errors else "FAILED",
        "record_count": len(records),
        "errors": errors,
    }
