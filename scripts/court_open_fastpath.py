"""Single-process Decretum Matrix court-open preparation path."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib
from typing import Callable, Mapping, Sequence

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
REQUEST_SCHEMA = "court.open.fast.request.v1"
RECEIPT_SCHEMA = "court.open.fast.v1"
MINIMAL_PRELOAD_BYTES = 20 * 1024
DEFAULT_THREAD_CEILING = 16
THREE_DEPARTMENTS = ("zhongshu", "menxia", "shangshu")
SIX_MINISTRIES = ("libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu")
ROLE_SUPERIORS = {
    **{role: "taizi" for role in THREE_DEPARTMENTS},
    **{role: "shangshu" for role in SIX_MINISTRIES},
}


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


def normalize_request(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise FastPathInvalid("request_must_be_object")
    if value.get("schema") != REQUEST_SCHEMA:
        raise FastPathInvalid("request_schema_invalid")
    task_id = _required_text(value.get("task_id"), "task_id")
    authority = _required_text(value.get("authority"), "authority")
    if authority not in {"approval", "autonomous", "super"}:
        raise FastPathInvalid("authority_invalid")
    worktree = str(Path(_required_text(value.get("worktree"), "worktree")).resolve())
    requested_offices = value.get("requested_offices", list(THREE_DEPARTMENTS))
    if not isinstance(requested_offices, list) or not requested_offices:
        raise FastPathInvalid("requested_offices_invalid")
    offices = tuple(_required_text(role, "requested_office").lower() for role in requested_offices)
    if len(offices) != len(set(offices)):
        raise FastPathInvalid("requested_offices_duplicate")
    write_sets_value = value.get("write_sets", {})
    if not isinstance(write_sets_value, dict):
        raise FastPathInvalid("write_sets_invalid")
    write_sets: dict[str, list[str]] = {}
    for role in (*offices, *SIX_MINISTRIES):
        raw = write_sets_value.get(role, [])
        if not isinstance(raw, list) or any(not isinstance(path, str) or not path.strip() for path in raw):
            raise FastPathInvalid(f"write_set_invalid:{role}")
        normalized = [Path(path).as_posix() for path in raw]
        if len(normalized) != len(set(normalized)):
            raise FastPathInvalid(f"write_set_duplicate:{role}")
        write_sets[role] = normalized
    expires_at = _required_text(value.get("expires_at_utc"), "expires_at_utc")
    try:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FastPathInvalid("expires_at_utc_invalid") from exc
    if expires.tzinfo is None:
        raise FastPathInvalid("expires_at_utc_timezone_required")
    normalized: dict[str, object] = {
        "schema": REQUEST_SCHEMA,
        "task_id": task_id,
        "authority": authority,
        "worktree": worktree,
        "skill_root": str(Path(str(value.get("skill_root") or ROOT)).resolve()),
        "host_capacity": _required_int(value.get("host_capacity"), "host_capacity", minimum=1),
        "host_active_agents": _required_int(value.get("host_active_agents"), "host_active_agents", minimum=1),
        "host_retained_agents": _required_int(value.get("host_retained_agents", 0), "host_retained_agents"),
        "host_reclamation_status": _required_text(value.get("host_reclamation_status"), "host_reclamation_status"),
        "system_memory_percent": float(value.get("system_memory_percent", 0.0)),
        "requested_offices": list(offices),
        "include_shangshu_ministries": bool(value.get("include_shangshu_ministries", True)),
        "write_sets": write_sets,
        "expected_branch": value.get("expected_branch"),
        "expected_head": value.get("expected_head"),
        "expected_semantic_receipt_sha256": value.get("expected_semantic_receipt_sha256"),
        "expected_plan_sha256": value.get("expected_plan_sha256"),
        "transport": str(value.get("transport") or "codex"),
        "expires_at_utc": expires.isoformat(),
    }
    operation_source = {key: item for key, item in normalized.items() if key != "operation_id"}
    normalized["operation_id"] = str(
        value.get("operation_id")
        or "court-open-" + _sha256_bytes(_canonical_bytes(operation_source))[:24]
    )
    return normalized


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


def load_preloads(
    skill_root: Path,
    roles: Sequence[str],
    *,
    concurrent: bool = True,
) -> dict[str, RolePreload]:
    try:
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
    return {value.role: value for value in values}


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
        "loaded_paths": [
            value.skill_path,
            value.dossier_path,
            value.profile_path,
            *value.metadata_sources[1:],
        ],
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
    read_scope = ["SKILL.md", preload.dossier_path, preload.profile_path, "references"]
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
        "python_child_processes": 0,
        "FAST_OPEN_SINGLE_PROCESS": "FAIL",
        "SHANGSHU_FIRST_DISPATCH": "FAIL",
        "SIX_MINISTRY_DIRECT_SUPERIOR": "FAIL",
        "pending_body_access": "NO",
    }


def prepare_fast_open(
    value: object,
    *,
    runtime_api: object | None = None,
    identity_loader: Callable[[Path], tuple[dict[str, object], list[list[str]]]] = live_worktree_identity,
    preload_loader: Callable[..., dict[str, RolePreload]] = load_preloads,
    concurrent_preload: bool = True,
) -> dict[str, object]:
    try:
        normalized = normalize_request(value)
        if normalized["host_reclamation_status"] != "verified":
            raise FastPathMiss("capacity_unknown", "host_reclamation_status")
        if float(normalized["system_memory_percent"]) >= 99.0:
            raise FastPathMiss("resource_pressure", "system_memory_percent")
        requested = tuple(normalized["requested_offices"])
        if any(role not in THREE_DEPARTMENTS for role in requested):
            raise FastPathMiss("hierarchy_incomplete", "taizi_may_dispatch_only_three_departments")
        total_roles = len(requested) + (len(SIX_MINISTRIES) if normalized["include_shangshu_ministries"] else 0)
        effective_capacity = min(DEFAULT_THREAD_CEILING, int(normalized["host_capacity"]))
        available = effective_capacity - int(normalized["host_active_agents"])
        if available < total_roles:
            raise FastPathMiss("capacity_insufficient", f"available={available}:required={total_roles}")
        _validate_write_sets(normalized["write_sets"])

        worktree = Path(str(normalized["worktree"]))
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

        roles = list(requested)
        if normalized["include_shangshu_ministries"]:
            roles.extend(SIX_MINISTRIES)
        preloads = preload_loader(
            Path(str(normalized["skill_root"])),
            roles,
            concurrent=concurrent_preload,
        )
        oversized = [role for role in roles if preloads[role].loaded_bytes > MINIMAL_PRELOAD_BYTES]
        if oversized:
            raise FastPathMiss("preload_budget_exceeded", *oversized)

        department_packets: list[dict[str, object]] = []
        ministry_packets: list[dict[str, object]] = []
        admission_decisions: list[dict[str, object]] = []
        ordinal = 0
        for role in requested:
            ordinal += 1
            hierarchy = _hierarchy_decision("taizi", role)
            admission = _admission_request(runtime_api, task, normalized, role, "taizi", preloads[role], ordinal)
            decision = _validate_admission(runtime_api, task, admission)
            department_packets.append({"role": role, "hierarchy": hierarchy, "admission": admission})
            admission_decisions.append({"role": role, "decision": decision.get("decision", "admitted")})
        if normalized["include_shangshu_ministries"]:
            for role in SIX_MINISTRIES:
                ordinal += 1
                hierarchy = _hierarchy_decision("shangshu", role)
                admission = _admission_request(runtime_api, task, normalized, role, "shangshu", preloads[role], ordinal)
                decision = _validate_admission(runtime_api, task, admission)
                ministry_packets.append({"role": role, "hierarchy": hierarchy, "admission": admission})
                admission_decisions.append({"role": role, "decision": decision.get("decision", "admitted")})

        packet_digest = _sha256_bytes(_canonical_bytes({
            "operation_id": normalized["operation_id"],
            "departments": department_packets,
            "ministries": ministry_packets,
        }))
        return {
            "schema": RECEIPT_SCHEMA,
            "ok": True,
            "status": "READY",
            "receipt_id": "court-open-" + _sha256_bytes(str(normalized["operation_id"]).encode("utf-8"))[:24],
            "operation_id": normalized["operation_id"],
            "request_sha256": _sha256_bytes(_canonical_bytes(normalized)),
            "packet_sha256": packet_digest,
            "task_id": normalized["task_id"],
            "semantic_receipt_id": receipt.get("receipt_id"),
            "semantic_receipt_sha256": receipt.get("receipt_sha256"),
            "plan_cursor": receipt.get("plan_cursor"),
            "worktree": identity,
            "preloads": [_preload_payload(preloads[role]) for role in roles],
            "department_packets": department_packets,
            "shangshu_ministry_packets": ministry_packets,
            "admission_decisions": admission_decisions,
            "mutations": [],
            "process_audit": process_audit,
            "python_child_processes": python_children,
            "FAST_OPEN_SINGLE_PROCESS": "PASS",
            "SHANGSHU_FIRST_DISPATCH": "PASS" if len(ministry_packets) == len(SIX_MINISTRIES) else "NOT_REQUESTED",
            "SIX_MINISTRY_DIRECT_SUPERIOR": "PASS" if all(
                packet["hierarchy"]["direct_superior"] == "shangshu" for packet in ministry_packets
            ) else "FAIL",
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
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--request-json")
    parser.add_argument("--request-file")
    parser.add_argument("--serial-preload", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    if not args.fast:
        result: dict[str, object] = {
            "schema": RECEIPT_SCHEMA,
            "ok": False,
            "status": "INVALID",
            "problems": ["--fast is required"],
        }
        exit_code = 3
    else:
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
