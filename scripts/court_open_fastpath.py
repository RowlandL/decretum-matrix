"""Single-process Decretum Matrix court-open preparation path."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from threading import Lock
import time
import tomllib
from typing import Callable, Mapping, Sequence

sys.dont_write_bytecode = True

from court_native_execution import AUTHORITIES, BEHAVIORS, select_native_execution


ROOT = Path(__file__).resolve().parents[1]
REQUEST_SCHEMA = "court.open.fast.request.v2"
RECEIPT_SCHEMA = "court.open.fast.v2"
MINIMAL_PRELOAD_BYTES = 20 * 1024
DEFAULT_THREAD_CEILING = 16
THREE_DEPARTMENTS = ("zhongshu", "menxia", "shangshu")
SIX_MINISTRIES = ("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu")
CAPABILITY_KINDS = ("skill", "mcp", "plugin", "cli", "script")
AUTHORITY_SOURCE_VALUES = frozenset({
    "explicit_latest_user",
    "startup_question_answered",
    "same_conversation_same_boundary",
})
AGENT_REUSE_CONTEXT_OCCUPANCY_LIMIT = 0.80
TASK_REUSE_RELATED_VALUES = frozenset(
    {"same", "related", "continuation", "overlapping", "overlap"}
)
TASK_REUSE_UNRELATED_VALUES = frozenset(
    {"unrelated", "none", "different", "disjoint"}
)
ROLE_SUPERIORS = {
    **{role: "taizi" for role in THREE_DEPARTMENTS},
    **{role: "shangshu" for role in SIX_MINISTRIES},
}
_CAPABILITY_SNAPSHOT_CACHE: dict[tuple[object, ...], dict[str, object]] = {}
_CAPABILITY_SNAPSHOT_CACHE_LOCK = Lock()
_PRELOAD_CACHE: dict[tuple[object, ...], dict[str, "RolePreload"]] = {}
_PRELOAD_CACHE_LOCK = Lock()
_DEFAULT_CAPABILITY_MANIFEST: Path | None = None


class FastPathInvalid(ValueError):
    pass


class FastPathMiss(ValueError):
    def __init__(self, reason: str, *problems: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.problems = tuple(problems) or (reason,)


@dataclass(frozen=True)
class RolePreload:
    role: str
    direct_superior: str
    office_zh: str
    skill_path: str
    skill_sha256: str
    skill_bytes: int
    dossier_path: str
    dossier_sha256: str
    dossier_bytes: int
    profile_path: str
    profile_sha256: str
    profile_bytes: int
    metadata_sources: tuple[str, ...]
    metadata_json: str
    metadata_sha256: str
    metadata_bytes: int

    @property
    def loaded_bytes(self) -> int:
        return (
            self.skill_bytes
            + self.dossier_bytes
            + self.profile_bytes
            + self.metadata_bytes
        )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FastPathInvalid(f"{field}_required")
    return value.strip()


def _required_int(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FastPathInvalid(f"{field}_invalid")
    return value


def _optional_bool(value: object, field: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise FastPathInvalid(f"{field}_invalid")
    return value


def normalize_request(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise FastPathInvalid("request_must_be_object")
    if value.get("schema") != REQUEST_SCHEMA:
        raise FastPathInvalid("request_schema_invalid")
    task_id = _required_text(value.get("task_id"), "task_id")
    authority = _required_text(value.get("authority"), "authority")
    if authority not in AUTHORITIES:
        raise FastPathInvalid("authority_invalid")
    authority_source = _required_text(value.get("authority_source"), "authority_source").casefold()
    if authority_source not in AUTHORITY_SOURCE_VALUES:
        raise FastPathInvalid("authority_source_invalid")
    behavior = _required_text(value.get("behavior"), "behavior")
    if behavior not in BEHAVIORS:
        raise FastPathInvalid("behavior_invalid")
    if "runtime" in value:
        raise FastPathInvalid("native_runtime_fixed")
    worktree = str(Path(_required_text(value.get("worktree"), "worktree")).resolve())
    requested_offices = value.get("requested_offices", list(THREE_DEPARTMENTS))
    if not isinstance(requested_offices, list) or not requested_offices:
        raise FastPathInvalid("requested_offices_invalid")
    offices = tuple(_required_text(role, "requested_office").lower() for role in requested_offices)
    if len(offices) != len(set(offices)):
        raise FastPathInvalid("requested_offices_duplicate")
    ministry_assignments_value = value.get("ministry_assignments", [])
    if not isinstance(ministry_assignments_value, list):
        raise FastPathInvalid("ministry_assignments_invalid")
    ministry_assignments = tuple(
        _required_text(role, "ministry_assignment").lower()
        for role in ministry_assignments_value
    )
    if len(ministry_assignments) != len(set(ministry_assignments)):
        raise FastPathInvalid("ministry_assignments_duplicate")
    invalid_ministries = [
        role for role in ministry_assignments if role not in SIX_MINISTRIES
    ]
    if invalid_ministries:
        raise FastPathInvalid(
            "ministry_assignment_invalid:" + ",".join(invalid_ministries)
        )
    if ministry_assignments and "shangshu" not in offices:
        raise FastPathInvalid("ministry_assignments_require_shangshu")
    write_sets_value = value.get("write_sets", {})
    if not isinstance(write_sets_value, dict):
        raise FastPathInvalid("write_sets_invalid")
    write_sets: dict[str, list[str]] = {}
    for role in dict.fromkeys((*offices, *ministry_assignments)):
        raw = write_sets_value.get(role, [])
        if not isinstance(raw, list) or any(not isinstance(path, str) or not path.strip() for path in raw):
            raise FastPathInvalid(f"write_set_invalid:{role}")
        normalized_paths = [Path(path).as_posix() for path in raw]
        if len(normalized_paths) != len(set(normalized_paths)):
            raise FastPathInvalid(f"write_set_duplicate:{role}")
        write_sets[role] = normalized_paths
    expires_at = _required_text(value.get("expires_at_utc"), "expires_at_utc")
    try:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FastPathInvalid("expires_at_utc_invalid") from exc
    if expires.tzinfo is None:
        raise FastPathInvalid("expires_at_utc_timezone_required")
    capability_query = str(value.get("capability_query") or "").strip()
    capability_manifest = str(value.get("capability_manifest") or "").strip()
    capability_check_requested = _optional_bool(
        value.get("capability_check_requested"),
        "capability_check_requested",
    ) or bool(capability_query or capability_manifest)
    admission_precheck_requested = _optional_bool(
        value.get("admission_precheck_requested"),
        "admission_precheck_requested",
    )
    git_check_requested = _optional_bool(
        value.get("git_check_requested"),
        "git_check_requested",
    ) or bool(value.get("expected_branch") or value.get("expected_head"))
    normalized: dict[str, object] = {
        "schema": REQUEST_SCHEMA,
        "task_id": task_id,
        "authority": authority,
        "authority_source": authority_source,
        "behavior": behavior,
        "worktree": worktree,
        "skill_root": str(Path(str(value.get("skill_root") or ROOT)).resolve()),
        "host_capacity": _required_int(value.get("host_capacity"), "host_capacity", minimum=1),
        "host_active_agents": _required_int(value.get("host_active_agents"), "host_active_agents", minimum=1),
        "host_retained_agents": _required_int(value.get("host_retained_agents", 0), "host_retained_agents"),
        "host_reclamation_status": _required_text(value.get("host_reclamation_status"), "host_reclamation_status"),
        "system_memory_percent": float(value.get("system_memory_percent", 0.0)),
        "requested_offices": list(offices),
        "ministry_assignments": list(ministry_assignments),
        "write_sets": write_sets,
        "git_check_requested": git_check_requested,
        "expected_branch": value.get("expected_branch"),
        "expected_head": value.get("expected_head"),
        "expected_semantic_receipt_sha256": value.get("expected_semantic_receipt_sha256"),
        "expected_plan_sha256": value.get("expected_plan_sha256"),
        "transport": str(value.get("transport") or "codex"),
        "task_focus": _required_text(value.get("task_focus"), "task_focus"),
        "capability_check_requested": capability_check_requested,
        "admission_precheck_requested": admission_precheck_requested,
        "capability_query": capability_query,
        "capability_manifest": capability_manifest,
        "capability_manifest_state": str(value.get("capability_manifest_state") or "current").strip().casefold(),
        "expires_at_utc": expires.isoformat(),
    }
    operation_source = {key: item for key, item in normalized.items() if key != "operation_id"}
    normalized["operation_id"] = str(
        value.get("operation_id")
        or "court-open-" + _sha256_bytes(_canonical_bytes(operation_source))[:24]
    )
    return normalized


def clear_capability_snapshot_cache() -> None:
    with _CAPABILITY_SNAPSHOT_CACHE_LOCK:
        _CAPABILITY_SNAPSHOT_CACHE.clear()


def clear_preload_cache() -> None:
    with _PRELOAD_CACHE_LOCK:
        _PRELOAD_CACHE.clear()


def _canonical_capability_manifest(normalized: Mapping[str, object]) -> Path:
    global _DEFAULT_CAPABILITY_MANIFEST
    explicit = str(normalized.get("capability_manifest") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if _DEFAULT_CAPABILITY_MANIFEST is not None:
        return _DEFAULT_CAPABILITY_MANIFEST
    from shiguan_paths import reference_path

    _DEFAULT_CAPABILITY_MANIFEST = reference_path("installed-capabilities-manifest.json").resolve()
    return _DEFAULT_CAPABILITY_MANIFEST


def _capability_cache_key(
    normalized: Mapping[str, object],
    manifest: Path,
    capability_loader: Callable[..., dict[str, object]],
) -> tuple[object, ...]:
    try:
        stat = manifest.stat()
        fingerprint: tuple[object, ...] = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        fingerprint = ("missing",)
    query = str(normalized.get("capability_query") or normalized["task_focus"])
    return (
        id(capability_loader),
        str(manifest),
        *fingerprint,
        str(normalized.get("capability_manifest_state") or "current"),
        str(normalized.get("transport") or "codex"),
        query,
    )


def _bounded_maintenance_assignment(request: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema": "court.capability.maintenance_assignment.v1",
        "owner": "libu-hr",
        "action": "BOUNDED_INCREMENTAL_MAINTENANCE",
        "reason": request.get("reason"),
        "query": request.get("query"),
        "limit": 1,
        "offline": True,
        "allow_write": False,
    }


def _candidate_kind(candidate: Mapping[str, object]) -> str:
    kind = str(candidate.get("kind") or "").strip().casefold()
    source = str(candidate.get("source") or "").strip().casefold()
    if "plugin" in source:
        return "plugin"
    return kind if kind in CAPABILITY_KINDS else ""


def _allocation(candidate: Mapping[str, object]) -> dict[str, object]:
    digest = str(
        candidate.get("observed_content_hash")
        or candidate.get("declared_content_hash")
        or candidate.get("content_hash")
        or ""
    )
    risks: list[str] = []
    if candidate.get("dispatchable") is not True:
        risks.append("not_dispatchable")
    if candidate.get("hash_status") not in {None, "MATCH", "ACTUAL_ONLY"}:
        risks.append("hash_not_current")
    if candidate.get("version_status") == "MISMATCH":
        risks.append("version_drift")
    return {
        "kind": _candidate_kind(candidate),
        "name": candidate.get("name"),
        "source": candidate.get("source"),
        "relative_path": candidate.get("relative_path"),
        "content_sha256": digest,
        "freshness": "current" if not risks else "attention_required",
        "recommended_office": "libu-hr",
        "permissions": ["read", "invoke"] if candidate.get("dispatchable") is True else ["read_metadata"],
        "risks": risks,
        "dispatchable": candidate.get("dispatchable") is True,
    }


def _capability_snapshot(
    route: Mapping[str, object],
    *,
    query: str,
    manifest: Path,
) -> dict[str, object]:
    proposed: dict[str, list[dict[str, object]]] = {kind: [] for kind in CAPABILITY_KINDS}
    candidates: list[Mapping[str, object]] = []
    selected = route.get("selected_candidate")
    if isinstance(selected, Mapping):
        candidates.append(selected)
    considered = route.get("registry_candidates_considered")
    if isinstance(considered, list):
        candidates.extend(item for item in considered if isinstance(item, Mapping))
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        kind = _candidate_kind(candidate)
        identity = (kind, str(candidate.get("source") or ""), str(candidate.get("name") or ""))
        if not kind or identity in seen or len(proposed[kind]) >= 3:
            continue
        seen.add(identity)
        proposed[kind].append(_allocation(candidate))
    try:
        manifest_sha256 = _sha256_bytes(manifest.read_bytes())
    except OSError:
        manifest_sha256 = ""
    body: dict[str, object] = {
        "schema": "court.capability.snapshot.v1",
        "owner": "libu-hr",
        "query": query,
        "registry": {
            "path": str(manifest),
            "sha256": manifest_sha256,
            "state": route.get("manifest_state"),
        },
        "selection_source": route.get("selection_source"),
        "fallback_reason": route.get("fallback_reason"),
        "dispatchable": route.get("dispatchable") is True,
        "proposed_allocations": proposed,
        "maintenance": {
            "invoked": route.get("discovery_invoked") is True,
            "call_count": int(route.get("discovery_call_count") or 0),
            "assignment": route.get("discovery_result"),
            "second_registry": route.get("second_registry") is True,
            "daemon": route.get("daemon") is True,
        },
    }
    body["snapshot_sha256"] = _sha256_bytes(_canonical_bytes(body))
    return body


def resolve_capability_snapshot(
    normalized: Mapping[str, object],
    *,
    capability_loader: Callable[..., dict[str, object]] | None = None,
) -> tuple[dict[str, object], str, float]:
    started = time.perf_counter_ns()
    if capability_loader is None:
        from court_capability_recruitment import route_registry_first

        capability_loader = route_registry_first
    manifest = _canonical_capability_manifest(normalized)
    cache_key = _capability_cache_key(normalized, manifest, capability_loader)
    with _CAPABILITY_SNAPSHOT_CACHE_LOCK:
        cached = _CAPABILITY_SNAPSHOT_CACHE.get(cache_key)
    if cached is not None:
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        return deepcopy(cached), "HIT", elapsed

    from court_capability_recruitment import default_source_roots

    query = str(normalized.get("capability_query") or normalized["task_focus"])
    source_roots: dict[str, object] = dict(default_source_roots())
    source_roots["executable_inventory"] = {}
    route = capability_loader(
        query=query,
        current_tool=str(normalized.get("transport") or "codex"),
        manifest=manifest,
        manifest_state=normalized.get("capability_manifest_state") or "current",
        source_roots=source_roots,
        bounded_discovery=_bounded_maintenance_assignment,
    )
    if not isinstance(route, Mapping):
        raise FastPathMiss("capability_snapshot_invalid")
    snapshot = _capability_snapshot(route, query=query, manifest=manifest)
    with _CAPABILITY_SNAPSHOT_CACHE_LOCK:
        _CAPABILITY_SNAPSHOT_CACHE[cache_key] = deepcopy(snapshot)
    elapsed = (time.perf_counter_ns() - started) / 1_000_000
    return snapshot, "MISS", elapsed


def capability_snapshot_not_requested() -> dict[str, object]:
    body: dict[str, object] = {
        "schema": "court.capability.snapshot.v1",
        "owner": "libu-hr",
        "status": "NOT_REQUESTED",
        "query": "",
        "registry": None,
        "selection_source": None,
        "fallback_reason": None,
        "dispatchable": False,
        "proposed_allocations": {kind: [] for kind in CAPABILITY_KINDS},
        "maintenance": {
            "invoked": False,
            "call_count": 0,
            "assignment": None,
            "second_registry": False,
            "daemon": False,
        },
    }
    body["snapshot_sha256"] = _sha256_bytes(_canonical_bytes(body))
    return body


def _run_git(worktree: Path, arguments: Sequence[str], audit: list[list[str]]) -> str:
    command = ["git", "-C", str(worktree), *arguments]
    audit.append(command)
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise FastPathMiss("worktree_identity_unavailable", completed.stderr.strip())
    return completed.stdout.strip()


def live_worktree_identity(worktree: Path) -> tuple[dict[str, object], list[list[str]]]:
    audit: list[list[str]] = []
    branch = _run_git(worktree, ("branch", "--show-current"), audit)
    head = _run_git(worktree, ("rev-parse", "HEAD"), audit)
    index = _run_git(worktree, ("diff", "--cached", "--name-only"), audit)
    tracked = _run_git(worktree, ("status", "--short", "--untracked-files=no"), audit)
    return (
        {
            "path": str(worktree.resolve()),
            "branch": branch,
            "HEAD": head,
            "index_count": len([line for line in index.splitlines() if line.strip()]),
            "tracked_dirty_count": len([line for line in tracked.splitlines() if line.strip()]),
        },
        audit,
    )


def _role_preload(
    skill_root: Path,
    role: str,
    skill_bytes: bytes,
    hierarchy: Mapping[str, object],
) -> RolePreload:
    profile_relative = Path("agents") / "standing-officials" / f"{role}.toml"
    dossier_relative = Path("agents") / "office-dossiers" / role / "AGENTS.md"
    profile_path = skill_root / profile_relative
    dossier_path = skill_root / dossier_relative
    try:
        profile_bytes = profile_path.read_bytes()
        dossier_bytes = dossier_path.read_bytes()
        profile = tomllib.loads(profile_bytes.decode("utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise FastPathMiss("preload_unavailable", f"{role}:{type(exc).__name__}:{exc}") from exc
    identity = profile.get("profile")
    if not isinstance(identity, dict) or identity.get("role_key") != role:
        raise FastPathMiss("preload_identity_mismatch", role)
    direct_superior = str(identity.get("direct_superior") or "")
    if direct_superior != ROLE_SUPERIORS.get(role):
        raise FastPathMiss(
            "hierarchy_incomplete",
            f"{role}:expected={ROLE_SUPERIORS.get(role)}:actual={direct_superior}",
        )
    dossier_text = dossier_bytes.decode("utf-8")
    if f"- role: {role}" not in dossier_text:
        raise FastPathMiss("preload_identity_mismatch", f"dossier:{role}")
    canonical_roles = hierarchy.get("canonical_roles")
    allowed_edges = hierarchy.get("allowed_edges")
    if not isinstance(canonical_roles, dict) or not isinstance(allowed_edges, list):
        raise FastPathMiss("hierarchy_incomplete", "manifest_shape")
    manifest_role = canonical_roles.get(role)
    if not isinstance(manifest_role, dict) or manifest_role.get("direct_superior") != direct_superior:
        raise FastPathMiss("hierarchy_incomplete", f"manifest_role:{role}")
    direct_children = sorted(
        str(edge.get("target"))
        for edge in allowed_edges
        if isinstance(edge, dict)
        and edge.get("action") == "dispatch"
        and edge.get("caller") == role
        and isinstance(edge.get("target"), str)
    )
    metadata = {
        "schema": "court.office.compact_preload_metadata.v1",
        "role": role,
        "direct_superior": direct_superior,
        "direct_children": direct_children,
        "registry_policy": "registry-first",
        "registry_owner": "libu-hr",
    }
    metadata_payload = _canonical_bytes(metadata)
    return RolePreload(
        role=role,
        direct_superior=direct_superior,
        office_zh=str(identity.get("office_zh") or role),
        skill_path="SKILL.md",
        skill_sha256=_sha256_bytes(skill_bytes),
        skill_bytes=len(skill_bytes),
        dossier_path=dossier_relative.as_posix(),
        dossier_sha256=_sha256_bytes(dossier_bytes),
        dossier_bytes=len(dossier_bytes),
        profile_path=profile_relative.as_posix(),
        profile_sha256=_sha256_bytes(profile_bytes),
        profile_bytes=len(profile_bytes),
        metadata_sources=(
            "SKILL.md",
            "references/manifests/court-dispatch-hierarchy.v1.json",
        ),
        metadata_json=metadata_payload.decode("utf-8"),
        metadata_sha256=_sha256_bytes(metadata_payload),
        metadata_bytes=len(metadata_payload),
    )


def _preload_cache_key(skill_root: Path, roles: Sequence[str]) -> tuple[object, ...]:
    paths = [
        Path("SKILL.md"),
        Path("references") / "manifests" / "court-dispatch-hierarchy.v1.json",
    ]
    for role in roles:
        paths.extend(
            (
                Path("agents") / "standing-officials" / f"{role}.toml",
                Path("agents") / "office-dossiers" / role / "AGENTS.md",
            )
        )
    signatures: list[tuple[str, int, int, int]] = []
    for relative in paths:
        stat = (skill_root / relative).stat()
        signatures.append(
            (relative.as_posix(), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        )
    return str(skill_root), tuple(roles), tuple(signatures)


def load_preloads(
    skill_root: Path,
    roles: Sequence[str],
    *,
    concurrent: bool = True,
) -> dict[str, RolePreload]:
    skill_root = skill_root.resolve(strict=False)
    try:
        cache_key = _preload_cache_key(skill_root, roles)
        with _PRELOAD_CACHE_LOCK:
            cached = _PRELOAD_CACHE.get(cache_key)
        if cached is not None:
            return dict(cached)
        skill_bytes = (skill_root / "SKILL.md").read_bytes()
        hierarchy = json.loads(
            (skill_root / "references" / "manifests" / "court-dispatch-hierarchy.v1.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise FastPathMiss("preload_unavailable", f"SKILL.md:{exc}") from exc
    if not isinstance(hierarchy, dict) or hierarchy.get("schema") != "court.dispatch_hierarchy.v1":
        raise FastPathMiss("hierarchy_incomplete", "manifest_schema")
    if concurrent and len(roles) > 1:
        with ThreadPoolExecutor(max_workers=min(len(roles), 8)) as executor:
            values = list(
                executor.map(
                    lambda role: _role_preload(skill_root, role, skill_bytes, hierarchy),
                    roles,
                )
            )
    else:
        values = [
            _role_preload(skill_root, role, skill_bytes, hierarchy) for role in roles
        ]
    result = {value.role: value for value in values}
    with _PRELOAD_CACHE_LOCK:
        _PRELOAD_CACHE[cache_key] = dict(result)
    return result


def _preload_payload(value: RolePreload) -> dict[str, object]:
    return {
        "role": value.role,
        "direct_superior": value.direct_superior,
        "office_zh": value.office_zh,
        "court_skill_path": value.skill_path,
        "court_skill_hash": value.skill_sha256,
        "dossier_path": value.dossier_path,
        "dossier_hash": value.dossier_sha256,
        "profile_path": value.profile_path,
        "profile_hash": value.profile_sha256,
        "metadata_sources": list(value.metadata_sources),
        "metadata": json.loads(value.metadata_json),
        "metadata_hash": value.metadata_sha256,
        "metadata_bytes": value.metadata_bytes,
        "verified_source_paths": [
            value.skill_path,
            value.dossier_path,
            value.profile_path,
            *value.metadata_sources[1:],
        ],
        "preload_evidence_kind": "dispatcher_source_validation",
        "child_preload_ack_status": "NOT_AVAILABLE_PRE_SPAWN",
        "loaded_bytes": value.loaded_bytes,
        "target_bytes": MINIMAL_PRELOAD_BYTES,
        "target_met": value.loaded_bytes <= MINIMAL_PRELOAD_BYTES,
    }


def _validate_write_sets(write_sets: Mapping[str, Sequence[str]]) -> None:
    owners: dict[str, str] = {}
    for role, paths in write_sets.items():
        for path in paths:
            previous = owners.setdefault(path.casefold(), role)
            if previous != role:
                raise FastPathMiss("write_set_overlap", f"{path}:{previous}:{role}")


def _hierarchy_decision(caller: str, role: str) -> dict[str, object]:
    from court_dispatch_hierarchy import validate_dispatch_hierarchy

    decision = validate_dispatch_hierarchy(
        action="dispatch",
        calling_office=caller,
        target_role=role,
        target_direct_superior=ROLE_SUPERIORS[role],
        instance_kind="office",
        canonical_authority=True,
        owner_role=None,
    )
    if not decision.allowed:
        raise FastPathMiss("hierarchy_incomplete", role, *decision.reason_codes)
    return {
        "schema": "court.dispatch_hierarchy.v1",
        "allowed": True,
        "caller": caller,
        "target": role,
        "direct_superior": ROLE_SUPERIORS[role],
        "edge_class": decision.edge_class,
        "manifest_sha256": decision.hierarchy_manifest_sha256,
    }


def _lease(
    normalized: Mapping[str, object],
    role: str,
    caller: str,
    preload: RolePreload,
    wave_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    operation_id = str(normalized["operation_id"])
    task_id = str(normalized["task_id"])
    instance_id = f"{role}#{operation_id[-12:]}"
    write_set = list(normalized["write_sets"].get(role, []))  # type: ignore[union-attr]
    read_scope = ["SKILL.md", preload.dossier_path, preload.profile_path]
    access_mode = "read_write" if write_set else "read_only"
    binding = {
        "role": role,
        "instance_id": instance_id,
        "shard_id": f"{role}-{operation_id[-12:]}",
        "direct_superior": caller,
        "canonical_authority": True,
        "instance_kind": "office",
        "owner_role": None,
        "access_mode": access_mode,
        "read_scope": read_scope,
        "write_set": write_set,
        "mutation_allowed": bool(write_set),
        "integration_authority": False,
        "preload_hashes": {
            "court_skill_hash": preload.skill_sha256,
            "dossier_hash": preload.dossier_sha256,
            "profile_hash": preload.profile_sha256,
        },
    }
    budget_id = f"budget:{task_id}:FAST-OPEN:{wave_id}"
    lease = {
        "schema": "court.agent.admission_lease.v2",
        "task_id": task_id,
        "budget_id": budget_id,
        "lease_id": f"{budget_id}:lease",
        "parent_budget_id": f"{budget_id}:{caller}",
        "parent_id": caller,
        "status": "ACTIVE",
        "authority": normalized["authority"],
        "grantee_role": caller,
        "calling_office": caller,
        "direct_superior": "user" if caller == "taizi" else "taizi",
        "approved_by": "user" if caller == "taizi" else "taizi",
        "integration_domain": "court-open-fast",
        "lease_depth": 0 if caller == "taizi" else 1,
        "approved_next_depth": 1 if caller == "taizi" else 2,
        "expires_at_utc": normalized["expires_at_utc"],
        "approved_count": 1,
        "approved_roles": [role],
        "approved_instance_ids": [instance_id],
        "approved_shards": [binding["shard_id"]],
        "approved_write_sets": {instance_id: write_set},
        "approved_access_contracts": {
            instance_id: {
                "access_mode": access_mode,
                "integration_authority": False,
                "mutation_allowed": bool(write_set),
                "read_scope": read_scope,
            }
        },
        "approved_instance_shapes": {
            instance_id: {
                "canonical_authority": True,
                "direct_superior": caller,
                "instance_kind": "office",
                "owner_role": None,
            }
        },
        "approved_preload_hashes": {instance_id: binding["preload_hashes"]},
        "approved_binding_sha256s": {},
        "parent_write_scope": write_set,
    }
    return lease, binding


def _admission_request(
    runtime_api: object,
    task: Mapping[str, object],
    normalized: Mapping[str, object],
    role: str,
    caller: str,
    preload: RolePreload,
    ordinal: int,
) -> dict[str, object]:
    receipt = task.get("semantic_receipt")
    if not isinstance(receipt, Mapping):
        raise FastPathMiss("semantic_receipt_missing")
    wave_id = f"{normalized['operation_id']}:{ordinal:02d}:{role}"
    lease, binding = _lease(normalized, role, caller, preload, wave_id)
    return {
        "schema": "court.agent.admission_request.v1",
        "task_id": normalized["task_id"],
        "expected_semantic_epoch": receipt.get("semantic_epoch"),
        "expected_charter_sha256": receipt.get("charter_sha256"),
        "expected_invariant_capsule_sha256": receipt.get("invariant_capsule_sha256"),
        "expected_checkpoint_id": receipt.get("checkpoint_id"),
        "wave_id": wave_id,
        "execution_topology": "parallel",
        "protocol_mode": "v2",
        "active_session_protocol": "v2",
        "needs_parallel_tree": True,
        "requested_fork_turns": "none",
        "context_tokens": 12000,
        "message_chars": 2000,
        "message_required_chars": 2000,
        "message_optional_chars": 0,
        "requested_agents": 1,
        "requested_roles": [role],
        "host_active_agents": normalized["host_active_agents"],
        "host_capacity": normalized["host_capacity"],
        "host_retained_agents": normalized["host_retained_agents"],
        "host_reclamation_status": normalized["host_reclamation_status"],
        "next_depth": 1 if caller == "taizi" else 2,
        "max_depth": 4,
        "max_threads": DEFAULT_THREAD_CEILING,
        "user_agent_budget": 1,
        "provider_launch_budget": 1,
        "budget_lease": lease,
        "requested_bindings": [binding],
        "integration_domain": "court-open-fast",
        "authority": normalized["authority"],
        "calling_office": caller,
        "direct_superior": "user" if caller == "taizi" else "taizi",
        "assignment": f"Fast court-open preparation for {role}",
        "task_focus": "complete bounded dispatch packet",
        "complexity": "high" if role == "shangshu" else "medium",
        "risk": "medium",
        "ambiguity": "low",
        "transport": normalized["transport"],
        "actor": caller,
        "evidence": f"operation={normalized['operation_id']}",
        "dispatch_context_packet": runtime_api.public_dispatch_context_packet(task, wave_id),
        "context_budget_pool": runtime_api.public_context_budget_pool(task, wave_id),
        "context_result_mode": "bounded_structured_receipt",
        "context_tool_output_mode": "pointer",
        "context_override_source": None,
        "system_memory_percent": normalized["system_memory_percent"],
    }


def _validate_admission(runtime_api: object, task: Mapping[str, object], request: dict[str, object]) -> dict[str, object]:
    custom = getattr(runtime_api, "validate_fast_admission", None)
    if callable(custom):
        decision = custom(task, request)
    else:
        argv = runtime_api.public_admission_request_argv(request)
        args = runtime_api.build_parser().parse_args(argv)
        runtime_api._semantic_admission_expectations(task, args)
        runtime_api._validate_context_economy_request(task, args, wave_id=str(args.wave_id))
        runtime_api._validate_canonical_admission_preloads(args)
        decision = runtime_api.evaluate_agent_admission(task, args)
        if decision.get("allowed") is True:
            runtime_api._validate_admission_capsule_write_scope(task, decision.get("selected_bindings"))
    if not isinstance(decision, dict) or decision.get("allowed") is not True:
        reason = decision.get("decision") if isinstance(decision, dict) else "invalid_decision"
        raise FastPathMiss("admission_denied", str(reason))
    return decision


def _miss(reason: str, problems: Sequence[str] = ()) -> dict[str, object]:
    return {
        "schema": RECEIPT_SCHEMA,
        "ok": False,
        "status": f"FAST_PATH_MISS:{reason}",
        "reason": reason,
        "problems": list(problems) or [reason],
        "mutations": [],
        "dispatch_count": 0,
        "physical_child_dispatch_count": 0,
        "planned_office_count": 0,
        "admission_check_count": 0,
        "preparation_only": True,
        "host_spawn_performed": False,
        "manual_bypass_allowed": False,
        "python_child_processes": 0,
        "FAST_OPEN_SINGLE_PROCESS": "FAIL",
        "SHANGSHU_FIRST_DISPATCH": "FAIL",
        "SIX_MINISTRY_DIRECT_SUPERIOR": "FAIL",
        "pending_body_access": "NO",
    }


def _shangshu_ministry_coordination(
    normalized: Mapping[str, object],
    ministry_packets: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    selected_ministries = [str(packet.get("role")) for packet in ministry_packets]
    return {
        "schema": "court.shangshu_ministry_coordination.v1",
        "coordinator": "shangshu",
        "authority": normalized["authority"],
        "behavior": normalized["behavior"],
        "selection_policy": "bounded_ministries_selected_by_shangshu_after_taizi_reply",
        "selected_ministries": selected_ministries,
        "simple_shangshu_only_allowed": False,
        "simple_shangshu_only_reason": "",
        "dispatch_initiator": None,
        "planned_dispatch_initiator": "shangshu",
        "dispatch_target_kind": "six_ministry_child_offices",
        "host_dispatch_performed": False,
        "dispatch_status": "PREPARED_NOT_PERFORMED",
        "taizi_direct_ministry_dispatch_allowed": False,
        "direct_superior_policy": "six_ministries_only_direct_superior_is_shangshu",
        "integration_owner": "shangshu",
        "evidence_return": "shangshu_integrates_then_reports_to_taizi",
        "ministry_packet_count": len(selected_ministries),
    }


def _authority_selection_gate(normalized: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema": "court.startup.authority_selection_gate.v1",
        "authority_source": normalized["authority_source"],
        "source_policy": "latest_explicit_or_current_question_or_same_conversation_same_boundary",
        "semantic_owner": "SKILL.md",
        "selected_authority": normalized["authority"],
        "selected_behavior": normalized["behavior"],
        "authority_behavior_orthogonal": True,
        "super_parallel_contract": "authority=super, behavior=parallel, runtime=native",
    }


def _agent_hierarchy_tree(
    department_packets: Sequence[Mapping[str, object]],
    ministry_packets: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    nodes: list[dict[str, object]] = [
        {
            "role": str(packet.get("role")),
            "parent_role": "taizi",
            "level": 1,
            "relation": "taizi_child",
        }
        for packet in department_packets
    ]
    nodes.extend(
        {
            "role": str(packet.get("role")),
            "parent_role": "shangshu",
            "level": 2,
            "relation": "shangshu_child_ministry",
        }
        for packet in ministry_packets
    )
    return {
        "schema": "court.agent_hierarchy_tree.v1",
        "root_role": "taizi",
        "nodes": nodes,
        "three_department_parent": "taizi",
        "six_ministry_parent": "shangshu",
        "six_ministries_are_shangshu_child_agents": all(
            node["parent_role"] == "shangshu"
            for node in nodes
            if node["role"] in SIX_MINISTRIES
        ),
        "host_sidebar_may_flatten_display": True,
        "rendering_contract": "render_six_ministries_nested_under_shangshu_not_as_taizi_siblings",
    }


def agent_reuse_policy_payload() -> dict[str, object]:
    return {
        "schema": "court.agent.reuse_policy.v1",
        "default_action": "reuse_compatible_live_instance_first",
        "compatible_instance_policy": "REUSE_FIRST",
        "context_occupancy_limit": AGENT_REUSE_CONTEXT_OCCUPANCY_LIMIT,
        "do_not_reuse_if": [
            "context_occupancy_ratio >= 0.80",
            "next_task_relation in unrelated|none|different|disjoint",
            "large_scale_parallel and performance_allows_fresh_instance after the context and task-relation checks",
        ],
        "large_scale_parallel_rule": (
            "after checking context occupancy and task relatedness, prefer a fresh "
            "instance when large-scale parallelism and host performance allow it"
        ),
        "hierarchy_preserved": True,
    }


def evaluate_agent_reuse_candidate(
    candidate: Mapping[str, object],
    request: Mapping[str, object],
) -> dict[str, object]:
    """Decide whether an already-open office instance should be reused."""

    reasons: list[str] = []
    status = str(candidate.get("status") or "").strip().lower()
    if status in {"completed", "failed", "cancelled", "closed"}:
        reasons.append("candidate_not_live")
    candidate_role = str(candidate.get("role") or "").strip().lower()
    request_role = str(request.get("role") or "").strip().lower()
    if not candidate_role or candidate_role != request_role:
        reasons.append("role_mismatch")
    candidate_superior = str(candidate.get("direct_superior") or "").strip().lower()
    request_superior = str(request.get("direct_superior") or "").strip().lower()
    if request_superior and candidate_superior != request_superior:
        reasons.append("direct_superior_mismatch")
    raw_ratio = candidate.get("context_occupancy_ratio")
    if isinstance(raw_ratio, bool) or not isinstance(raw_ratio, (int, float)):
        reasons.append("context_occupancy_unknown")
    else:
        ratio = float(raw_ratio)
        if ratio >= AGENT_REUSE_CONTEXT_OCCUPANCY_LIMIT:
            reasons.append("context_occupancy_at_or_above_80_percent")
    relation = str(
        request.get("next_task_relation")
        or candidate.get("next_task_relation")
        or request.get("task_relation")
        or candidate.get("task_relation")
        or ""
    ).strip().casefold()
    if relation in TASK_REUSE_UNRELATED_VALUES:
        reasons.append("next_task_unrelated")
    elif relation and relation not in TASK_REUSE_RELATED_VALUES:
        reasons.append("task_relation_unknown")
    if (
        bool(request.get("large_scale_parallel"))
        and bool(request.get("performance_allows_fresh_instance"))
        and not reasons
    ):
        reasons.append("large_scale_parallel_fresh_instance_preferred")
    decision = "REUSE" if not reasons else "DO_NOT_REUSE"
    return {
        "schema": "court.agent.reuse_decision.v1",
        "decision": decision,
        "reuse": decision == "REUSE",
        "reason_codes": reasons or ["compatible_live_instance_reuse_first"],
        "policy": agent_reuse_policy_payload(),
    }


def prepare_fast_open(
    value: object,
    *,
    runtime_api: object | None = None,
    identity_loader: Callable[[Path], tuple[dict[str, object], list[list[str]]]] = live_worktree_identity,
    preload_loader: Callable[..., dict[str, RolePreload]] = load_preloads,
    capability_loader: Callable[..., dict[str, object]] | None = None,
    concurrent_preload: bool = True,
) -> dict[str, object]:
    try:
        normalized = normalize_request(value)
        skill_root = Path(str(normalized["skill_root"]))
        execution = select_native_execution(
            authority=str(normalized["authority"]),
            behavior=str(normalized["behavior"]),
            root=skill_root,
        ).as_dict()
        if normalized["host_reclamation_status"] != "verified":
            raise FastPathMiss("capacity_unknown", "host_reclamation_status")
        if float(normalized["system_memory_percent"]) >= 99.0:
            raise FastPathMiss("resource_pressure", "system_memory_percent")
        requested = tuple(normalized["requested_offices"])
        ministry_assignments = tuple(normalized["ministry_assignments"])
        if any(role not in THREE_DEPARTMENTS for role in requested):
            raise FastPathMiss("hierarchy_incomplete", "taizi_may_dispatch_only_three_departments")
        if normalized["behavior"] == "parallel":
            total_roles = len(requested) + len(ministry_assignments)
            effective_capacity = min(DEFAULT_THREAD_CEILING, int(normalized["host_capacity"]))
            available = effective_capacity - int(normalized["host_active_agents"])
            if available < total_roles:
                raise FastPathMiss("capacity_insufficient", f"available={available}:required={total_roles}")
        _validate_write_sets(normalized["write_sets"])

        worktree = Path(str(normalized["worktree"]))
        if normalized["git_check_requested"]:
            identity, process_audit = identity_loader(worktree)
            python_children = sum(
                1
                for command in process_audit
                if command and Path(command[0]).name.lower().startswith(("python", "py.exe"))
            )
            if python_children:
                raise FastPathMiss("python_subprocess_detected", str(python_children))
            if identity.get("path") != str(worktree.resolve()):
                raise FastPathMiss("worktree_identity_mismatch")
            if int(identity.get("index_count") or 0) != 0:
                raise FastPathMiss("index_not_empty")
            if normalized.get("expected_branch") and identity.get("branch") != normalized["expected_branch"]:
                raise FastPathMiss("branch_drift")
            if normalized.get("expected_head") and identity.get("HEAD") != normalized["expected_head"]:
                raise FastPathMiss("head_drift")
        else:
            identity = {
                "path": str(worktree.resolve()),
                "status": "NOT_REQUESTED",
            }
            process_audit = []
            python_children = 0

        if runtime_api is None:
            import court_runtime as runtime_api
        tasks = runtime_api.load_tasks()
        task = tasks.get(str(normalized["task_id"])) if isinstance(tasks, Mapping) else None
        if not isinstance(task, Mapping):
            raise FastPathMiss("task_missing")
        receipt = task.get("semantic_receipt")
        if not isinstance(receipt, Mapping) or receipt.get("verdict") != "DISPATCHABLE":
            raise FastPathMiss("semantic_not_dispatchable")
        if (
            normalized.get("expected_semantic_receipt_sha256")
            and receipt.get("receipt_sha256") != normalized["expected_semantic_receipt_sha256"]
        ):
            raise FastPathMiss("semantic_receipt_drift")
        if normalized.get("expected_plan_sha256") and receipt.get("plan_sha256") != normalized["expected_plan_sha256"]:
            raise FastPathMiss("plan_drift")

        roles = [*requested, *ministry_assignments]
        capability_requested = bool(
            normalized["capability_check_requested"] or capability_loader is not None
        )
        if concurrent_preload and capability_requested:
            with ThreadPoolExecutor(max_workers=2) as executor:
                capability_future = executor.submit(
                    resolve_capability_snapshot,
                    normalized,
                    capability_loader=capability_loader,
                )
                preload_future = executor.submit(
                    preload_loader,
                    skill_root,
                    roles,
                    concurrent=True,
                )
                capability_snapshot, capability_cache_status, capability_lookup_ms = capability_future.result()
                preloads = preload_future.result()
        elif capability_requested:
            capability_snapshot, capability_cache_status, capability_lookup_ms = resolve_capability_snapshot(
                normalized,
                capability_loader=capability_loader,
            )
            preloads = preload_loader(skill_root, roles, concurrent=False)
        else:
            capability_snapshot = capability_snapshot_not_requested()
            capability_cache_status = "NOT_REQUESTED"
            capability_lookup_ms = 0.0
            preloads = preload_loader(
                skill_root,
                roles,
                concurrent=concurrent_preload,
            )
        oversized = [role for role in roles if preloads[role].loaded_bytes > MINIMAL_PRELOAD_BYTES]
        if oversized:
            raise FastPathMiss("preload_budget_exceeded", *oversized)

        department_packets: list[dict[str, object]] = []
        ministry_packets: list[dict[str, object]] = []
        admission_decisions: list[dict[str, object]] = []
        admission_precheck = bool(normalized["admission_precheck_requested"]) and normalized["behavior"] == "parallel"
        execution_sha256 = _sha256_bytes(_canonical_bytes(execution))
        ordinal = 0
        for role in requested:
            ordinal += 1
            hierarchy = _hierarchy_decision("taizi", role)
            packet: dict[str, object] = {
                "role": role,
                "hierarchy": hierarchy,
                "execution_sha256": execution_sha256,
                "capability_snapshot_sha256": capability_snapshot["snapshot_sha256"],
                "preparation_only": True,
                "physical_child_agent_spawned": False,
                "host_spawn_status": "NOT_PERFORMED_PREPARATION_ONLY",
                "host_dispatch_required_for_done": normalized["behavior"] == "parallel",
                "admission_precheck_requested": admission_precheck,
            }
            if admission_precheck:
                admission = _admission_request(runtime_api, task, normalized, role, "taizi", preloads[role], ordinal)
                decision = _validate_admission(runtime_api, task, admission)
                packet["admission"] = admission
                packet["admission_status"] = "EXPLICIT_PRECHECK_ONLY"
                admission_decisions.append({"role": role, "decision": decision.get("decision", "admitted")})
            elif normalized["behavior"] == "serial":
                packet["admission"] = None
                packet["serial_action"] = "serial_inline_office_duty"
                packet["office_duty_preserved"] = True
                packet["dispatch_evidence_status"] = "serial_inline_no_physical_child"
            else:
                packet["admission"] = None
                packet["admission_status"] = "NOT_REQUESTED_PREPARATION_ONLY"
                packet["dispatch_evidence_status"] = "host_dispatch_required"
            department_packets.append(packet)
        for role in ministry_assignments:
            ordinal += 1
            hierarchy = _hierarchy_decision("shangshu", role)
            packet = {
                "role": role,
                "hierarchy": hierarchy,
                "execution_sha256": execution_sha256,
                "capability_snapshot_sha256": capability_snapshot["snapshot_sha256"],
                "preparation_only": True,
                "physical_child_agent_spawned": False,
                "host_spawn_status": "NOT_PERFORMED_PREPARATION_ONLY",
                "host_dispatch_required_for_done": normalized["behavior"] == "parallel",
                "admission_precheck_requested": admission_precheck,
            }
            if admission_precheck:
                admission = _admission_request(runtime_api, task, normalized, role, "shangshu", preloads[role], ordinal)
                decision = _validate_admission(runtime_api, task, admission)
                packet["admission"] = admission
                packet["admission_status"] = "EXPLICIT_PRECHECK_ONLY"
                admission_decisions.append({"role": role, "decision": decision.get("decision", "admitted")})
            elif normalized["behavior"] == "serial":
                packet["admission"] = None
                packet["serial_action"] = "serial_inline_office_duty"
                packet["office_duty_preserved"] = True
                packet["dispatch_evidence_status"] = "serial_inline_no_physical_child"
            else:
                packet["admission"] = None
                packet["admission_status"] = "NOT_REQUESTED_PREPARATION_ONLY"
                packet["dispatch_evidence_status"] = "host_dispatch_required"
            ministry_packets.append(packet)
        shangshu_ministry_coordination = (
            _shangshu_ministry_coordination(normalized, ministry_packets)
            if ministry_packets
            else None
        )
        authority_selection_gate = _authority_selection_gate(normalized)
        agent_hierarchy = _agent_hierarchy_tree(department_packets, ministry_packets)
        agent_reuse_policy = agent_reuse_policy_payload()

        packet_digest = _sha256_bytes(_canonical_bytes({
            "operation_id": normalized["operation_id"],
            "departments": department_packets,
            "ministries": ministry_packets,
            "shangshu_ministry_coordination": shangshu_ministry_coordination,
            "authority_selection_gate": authority_selection_gate,
            "agent_hierarchy": agent_hierarchy,
            "agent_reuse_policy": agent_reuse_policy,
            "preparation_only": True,
        }))
        planned_office_count = len(department_packets) + len(ministry_packets)
        return {
            "schema": RECEIPT_SCHEMA,
            "ok": True,
            "status": "READY_FOR_HOST_DISPATCH",
            "receipt_id": "court-open-" + _sha256_bytes(str(normalized["operation_id"]).encode("utf-8"))[:24],
            "operation_id": normalized["operation_id"],
            "request_sha256": _sha256_bytes(_canonical_bytes(normalized)),
            "packet_sha256": packet_digest,
            "task_id": normalized["task_id"],
            "execution": execution,
            "preparation_only": True,
            "host_spawn_performed": False,
            "host_dispatch_required_for_done": normalized["behavior"] == "parallel",
            "agent_admission_satisfies_office_work": False,
            "admission_precheck_requested": admission_precheck,
            "admission_scope": (
                "explicit_machine_precheck_only"
                if admission_precheck
                else "not_requested_preparation_only"
            ),
            "authority_selection_gate": authority_selection_gate,
            "semantic_receipt_id": receipt.get("receipt_id"),
            "semantic_receipt_sha256": receipt.get("receipt_sha256"),
            "plan_cursor": receipt.get("plan_cursor"),
            "worktree": identity,
            "capability_snapshot": capability_snapshot,
            "capability_check_requested": capability_requested,
            "capability_cache_status": capability_cache_status,
            "capability_lookup_ms": round(capability_lookup_ms, 3),
            "preloads": [_preload_payload(preloads[role]) for role in roles],
            "department_packets": department_packets,
            "shangshu_ministry_packets": ministry_packets,
            "shangshu_ministry_coordination": shangshu_ministry_coordination,
            "agent_hierarchy": agent_hierarchy,
            "agent_reuse_policy": agent_reuse_policy,
            "admission_decisions": admission_decisions,
            "mutations": [],
            "dispatch_count": 0,
            "physical_child_dispatch_count": 0,
            "planned_department_count": len(department_packets),
            "planned_ministry_count": len(ministry_packets),
            "planned_office_count": planned_office_count,
            "office_assignment_count": planned_office_count,
            "admission_check_count": len(admission_decisions),
            "serial_office_duty_count": planned_office_count if normalized["behavior"] == "serial" else 0,
            "manual_bypass_allowed": False,
            "git_check_requested": normalized["git_check_requested"],
            "process_audit": process_audit,
            "python_child_processes": python_children,
            "FAST_OPEN_SINGLE_PROCESS": "PASS",
            "SHANGSHU_FIRST_DISPATCH": (
                "NOT_PERFORMED_PREPARATION_ONLY" if ministry_packets else "NOT_REQUESTED"
            ),
            "SIX_MINISTRY_DIRECT_SUPERIOR": (
                "PASS"
                if ministry_packets
                and all(
                    packet["hierarchy"]["direct_superior"] == "shangshu"
                    for packet in ministry_packets
                )
                else "NOT_REQUESTED"
            ),
            "pending_body_access": "NO",
        }
    except FastPathMiss as exc:
        return _miss(exc.reason, exc.problems)


def _request_value(args: argparse.Namespace) -> object:
    if bool(args.request_json) == bool(args.request_file):
        raise FastPathInvalid("exactly_one_request_source_required")
    if args.request_json:
        try:
            return json.loads(args.request_json)
        except json.JSONDecodeError as exc:
            raise FastPathInvalid("request_json_invalid") from exc
    try:
        return json.loads(Path(args.request_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FastPathInvalid("request_file_invalid") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Optional compatibility marker; court open is always preparation-only.",
    )
    parser.add_argument("--request-json")
    parser.add_argument("--request-file")
    parser.add_argument("--serial-preload", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        result = prepare_fast_open(
            _request_value(args),
            concurrent_preload=not args.serial_preload,
        )
        exit_code = 0 if result["ok"] else 2
    except FastPathInvalid as exc:
        result = {
            "schema": RECEIPT_SCHEMA,
            "ok": False,
            "status": "INVALID",
            "problems": [str(exc)],
        }
        exit_code = 3
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        print(result["status"])
        for problem in result.get("problems", []):
            print(f"problem={problem}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
