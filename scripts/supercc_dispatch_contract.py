"""Bounded context and active-office preload contracts for superCC dispatch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import secrets
import sys
from typing import Any, Callable, Mapping

sys.dont_write_bytecode = True


RuntimeProvider = Callable[[], Mapping[str, Any]]
_RUNTIME_PROVIDER: RuntimeProvider | None = None


def configure_runtime(provider: RuntimeProvider) -> None:
    """Bind the launcher namespace without importing the launcher in reverse."""

    global _RUNTIME_PROVIDER
    _RUNTIME_PROVIDER = provider


def _runtime() -> Mapping[str, Any]:
    if _RUNTIME_PROVIDER is None:
        raise RuntimeError("supercc dispatch contract runtime is not configured")
    return _RUNTIME_PROVIDER()


def default_dispatch_calling_office(role: str) -> str:
    return "shangshu" if role in _runtime()["MINISTRY_OFFICES"] else "taizi"


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _structured_reference(kind: str, **fields: object) -> str:
    """Return a readable reference bound to existing task/dispatch records."""

    selected = {
        key: value
        for key, value in fields.items()
        if value is not None and value != ""
    }
    if not selected:
        raise ValueError(f"{kind} reference requires an existing binding")
    return f"{kind}:" + json.dumps(
        selected,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _validate_dispatch_context_packet(
    task: object,
    receipt: object,
    packet: object,
) -> dict[str, object]:
    if not isinstance(task, Mapping) or not isinstance(packet, Mapping):
        raise ValueError("semantic dispatch context requires task and packet objects")
    if packet.get("schema") != "court.semantic.dispatch_context_packet.v1":
        raise ValueError("semantic dispatch context schema mismatch")
    task_id = task.get("task_id") or task.get("id")
    if task_id is not None and packet.get("task_id") != task_id:
        raise ValueError("semantic dispatch context task mismatch")
    authority_problems: list[str] = []
    if not isinstance(receipt, Mapping):
        authority_problems.append("semantic_receipt_missing")
    else:
        capsule = task.get("invariant_capsule")
        if capsule is None:
            authority_problems.append("semantic_task_invariant_capsule_missing")
        elif not isinstance(capsule, Mapping):
            authority_problems.append("semantic_task_invariant_capsule_invalid")
        receipt_id = receipt.get("receipt_id")
        receipt_epoch = receipt.get("semantic_epoch")
        packet_receipt_id = packet.get("semantic_receipt_id")
        packet_epoch = packet.get("semantic_epoch")
        if not isinstance(receipt_id, str) or not receipt_id.strip():
            authority_problems.append("semantic_receipt_id_missing")
        elif packet_receipt_id != receipt_id:
            authority_problems.append("semantic_receipt_id_not_current")
        if (
            type(receipt_epoch) is not int
            or receipt_epoch < 1
            or receipt_epoch != task.get("semantic_epoch")
        ):
            authority_problems.append("semantic_receipt_epoch_invalid")
        if packet_epoch != receipt_epoch:
            authority_problems.append("semantic_epoch_not_current")
        if not isinstance(receipt.get("plan_cursor"), str) or not receipt.get("plan_cursor", "").strip():
            authority_problems.append("semantic_receipt_revision_missing")
        elif packet.get("plan_cursor") != receipt.get("plan_cursor"):
            authority_problems.append("semantic_receipt_revision_not_current")
        try:
            from court_case_binding import case_reference, plan_reference

            task_case = task.get("case_ref")
            if task_case is None and isinstance(capsule, Mapping):
                task_case = capsule.get("case_ref")
            expected_case = case_reference(task_case)
            receipt_case = case_reference(receipt.get("case_ref"))
            packet_case = case_reference(packet.get("case_ref"))
            if receipt_case != expected_case:
                authority_problems.append("semantic_receipt_case_not_current")
            if packet_case != receipt_case:
                authority_problems.append("semantic_packet_case_not_current")
            task_revision = task.get("charter_revision")
            if task_revision is not None and (
                type(task_revision) is not int or task_revision != expected_case["charter_revision"]
            ):
                authority_problems.append("task_charter_revision_invalid")
            authority_revision = receipt.get("authority_revision")
            if authority_revision is not None and (
                type(authority_revision) is not int
                or authority_revision != expected_case["charter_revision"]
            ):
                authority_problems.append("semantic_receipt_authority_revision_invalid")
            receipt_plan = receipt.get("plan_ref")
            packet_plan = packet.get("plan_ref")
            if receipt_plan is None:
                if packet_plan is not None:
                    authority_problems.append("semantic_packet_plan_not_current")
            elif not isinstance(receipt_plan, Mapping):
                authority_problems.append("semantic_receipt_plan_invalid")
            elif packet_plan is None or plan_reference(packet_plan) != plan_reference(receipt_plan):
                authority_problems.append("semantic_packet_plan_not_current")
        except (AttributeError, TypeError, ValueError, KeyError):
            authority_problems.append("semantic_receipt_case_invalid")
        try:
            from court_semantic_continuity import verify_semantic_receipt

            context = {
                field: receipt.get(field)
                for field in (
                    "authority_revision",
                    "case_ref",
                    "plan_ref",
                    "plan_cursor",
                    "recovery_checkpoint_id",
                    "shiguan_revision",
                )
            }
            authority_problems.extend(
                f"semantic_receipt_validator:{problem}"
                for problem in verify_semantic_receipt(dict(task), dict(receipt), context)
            )
        except (AttributeError, ImportError, TypeError, ValueError, KeyError) as exc:
            authority_problems.append(f"semantic_receipt_validator_error:{exc}")
    if authority_problems:
        raise ValueError(
            "semantic dispatch context authority mismatch:"
            + ",".join(dict.fromkeys(authority_problems))
        )
    if packet.get("context_mode") != "bounded":
        raise ValueError("semantic dispatch context must be bounded")
    return {"packet": dict(packet)}


def _portable_repo_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().replace("\\", "/")
    parts = candidate.split("/")
    if (
        not candidate
        or candidate.startswith("/")
        or re.match(r"^[A-Za-z]:", candidate)
        or any(part in {"", ".", ".."} or ":" in part for part in parts)
    ):
        return None
    return "/".join(parts)


def _nonempty_string_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return None
    return [item.strip() for item in value]


def validate_enter_dispatch_context(
    args: argparse.Namespace,
    role: str,
    calling_office: str,
    direct_superior: str,
) -> dict[str, Any]:
    runtime = _runtime()
    context_fields = runtime["ENTER_DISPATCH_CONTEXT_FIELDS"]
    context_schema = runtime["ENTER_DISPATCH_CONTEXT_SCHEMA"]
    context_max_bytes = runtime["ENTER_DISPATCH_CONTEXT_MAX_BYTES"]
    scope_fields = runtime["ENTER_DISPATCH_SCOPE_FIELDS"]
    raw = getattr(args, "dispatch_context_packet_json", None)
    if not isinstance(raw, str) or not raw.strip():
        return {"ok": False, "reason": "enter_dispatch_context_packet_required"}
    try:
        packet = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "reason": "enter_dispatch_context_packet_invalid_json",
            "error": str(exc),
        }
    if not isinstance(packet, dict) or set(packet) != context_fields:
        return {"ok": False, "reason": "enter_dispatch_context_packet_fields_invalid"}
    dispatch_uid = str(getattr(args, "dispatch_uid", "") or "").strip()
    message = str(getattr(args, "message", "") or "")
    if (
        packet.get("schema") != context_schema
        or not dispatch_uid
        or packet.get("dispatch_uid") != dispatch_uid
        or packet.get("role_key") != role
        or packet.get("calling_office") != calling_office
        or packet.get("direct_superior") != direct_superior
        or not isinstance(packet.get("message_id"), str)
        or not packet.get("message_id")
    ):
        return {"ok": False, "reason": "enter_dispatch_context_binding_mismatch"}
    task_id = packet.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        return {"ok": False, "reason": "enter_dispatch_context_task_invalid"}

    semantic = packet.get("semantic_packet")
    if not isinstance(semantic, dict):
        return {"ok": False, "reason": "enter_dispatch_semantic_packet_required"}
    if semantic.get("task_id") != task_id or semantic.get("sub_id") != dispatch_uid:
        return {
            "ok": False,
            "reason": "enter_dispatch_semantic_packet_binding_mismatch",
        }
    scope = packet.get("scope")
    if not isinstance(scope, dict) or set(scope) != scope_fields:
        return {"ok": False, "reason": "enter_dispatch_scope_fields_invalid"}
    normalized_scope: dict[str, list[str]] = {}
    for field in scope_fields:
        values = _nonempty_string_list(scope.get(field))
        if values is None:
            return {"ok": False, "reason": f"enter_dispatch_scope_invalid:{field}"}
        normalized_scope[field] = values
    portable_paths = [
        normalized
        for value in normalized_scope["allowed_paths"]
        if (normalized := _portable_repo_path(value)) is not None
    ]
    if len(portable_paths) != len(normalized_scope["allowed_paths"]):
        return {"ok": False, "reason": "enter_dispatch_scope_invalid:allowed_paths"}
    normalized_scope["allowed_paths"] = portable_paths
    if set(normalized_scope["allowed_actions"]) & set(
        normalized_scope["forbidden_actions"]
    ):
        return {"ok": False, "reason": "enter_dispatch_scope_action_conflict"}
    task_loader = runtime.get("load_supercc_tasks")
    if not callable(task_loader):
        return {"ok": False, "reason": "enter_dispatch_supercc_task_loader_unavailable"}
    try:
        current_task = task_loader().get(task_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "reason": "enter_dispatch_supercc_task_unavailable",
            "error": str(exc),
        }
    if not isinstance(current_task, dict):
        return {"ok": False, "reason": "enter_dispatch_supercc_task_not_found"}
    try:
            semantic_validation = _validate_dispatch_context_packet(
            current_task,
            current_task.get("semantic_receipt"),
            semantic,
        )
    except ValueError as exc:
        return {
            "ok": False,
            "reason": "enter_dispatch_semantic_authority_invalid",
            "semantic_authority_error": str(exc),
        }
    normalized_semantic = semantic_validation.get("packet")
    if not isinstance(normalized_semantic, dict):
        return {"ok": False, "reason": "enter_dispatch_semantic_authority_invalid"}
    if normalized_semantic.get("context_mode") != "bounded":
        return {"ok": False, "reason": "enter_dispatch_semantic_packet_not_bounded"}

    normalized_packet = dict(packet)
    normalized_packet["semantic_packet"] = normalized_semantic
    normalized_packet["scope"] = normalized_scope
    packet_bytes = len(canonical_json_bytes(normalized_packet))
    if packet_bytes > context_max_bytes:
        return {"ok": False, "reason": "enter_dispatch_context_packet_too_large"}
    task_ref = task_id
    dispatch_ref = dispatch_uid
    semantic_receipt_ref = normalized_semantic.get("semantic_receipt_id")
    semantic_revision = normalized_semantic.get("semantic_epoch")
    authority_ref = normalized_packet.get("calling_office")
    direct_superior_ref = normalized_packet.get("direct_superior")
    return {
        "ok": True,
        "schema": context_schema,
        "packet": normalized_packet,
        "packet_id": _structured_reference(
            "dispatch-packet",
            task_id=task_ref,
            dispatch_uid=dispatch_ref,
            semantic_receipt_id=semantic_receipt_ref,
            semantic_revision=semantic_revision,
            authority=authority_ref,
            direct_superior=direct_superior_ref,
        ),
        "packet_bytes": packet_bytes,
        "semantic_packet_id": _structured_reference(
            "semantic-packet",
            task_id=task_ref,
            dispatch_uid=normalized_semantic.get("sub_id"),
            semantic_receipt_id=semantic_receipt_ref,
            semantic_revision=semantic_revision,
        ),
        "scope_id": _structured_reference(
            "dispatch-scope",
            task_id=task_ref,
            dispatch_uid=dispatch_ref,
            semantic_receipt_id=semantic_receipt_ref,
            authority=authority_ref,
            direct_superior=direct_superior_ref,
        ),
        "task_id": task_id,
        "allowed_paths": portable_paths,
        "validation_scope": "current_runtime_task_and_semantic_receipt",
    }


def _new_identity_generation_challenge() -> str:
    return "idg-" + secrets.token_hex(12)


def active_office_identity_binding(
    check: dict[str, Any],
    role: str,
    *,
    require_visible: bool,
    workspace: Path | None = None,
) -> dict[str, Any]:
    runtime = _runtime()
    row = runtime["active_canonical_agent_row"](check, role)
    visible = runtime["visible_office_panes"](check)
    pane_selection = runtime["select_unique_visible_pane"](visible, role)
    pane = pane_selection.get("pane") if pane_selection.get("ok") else None
    if row is None:
        return {
            "ok": False,
            "role": role,
            "reason": "active_office_identity_missing",
            "visible_pane_selection": pane_selection,
        }
    if require_visible and pane is None:
        return {
            "ok": False,
            "role": role,
            "identity_id": row.get("id"),
            "reason": "active_office_visible_identity_binding_missing",
            "visible_pane_selection": pane_selection,
        }
    persisted_role: dict[str, Any] = {}
    if workspace is not None:
        persisted = runtime["read_office_state"](
            workspace,
            runtime["current_zellij_session"](check),
        )
        persisted_roles = persisted.get("roles") if isinstance(persisted, dict) else None
        candidate = (
            persisted_roles.get(role)
            if isinstance(persisted_roles, dict)
            else None
        )
        if isinstance(candidate, dict):
            persisted_role = candidate
    identity_generation = persisted_role.get("identity_generation")
    if (
        not isinstance(identity_generation, str)
        or not identity_generation.strip()
    ):
        return {
            "ok": False,
            "role": role,
            "identity_id": row.get("id"),
            "reason": "active_office_identity_generation_required",
            "visible_pane_selection": pane_selection,
        }
    persisted_identity_id = persisted_role.get("identity_id")
    if persisted_identity_id is not None and persisted_identity_id != row.get("id"):
        return {
            "ok": False,
            "role": role,
            "identity_id": row.get("id"),
            "reason": "active_office_identity_generation_binding_mismatch",
            "visible_pane_selection": pane_selection,
        }
    row_binding = {
        key: row.get(key)
        for key in (
            "id",
            "role",
            "effective_client_type",
            "client_type",
            "protocol_version",
            "joined_at",
            "created_at",
            "session_id",
        )
        if row.get(key) is not None
    }
    identity = {
        "schema": "court.supercc.active_office_identity.v1",
        "role": role,
        "identity_generation": identity_generation,
        "zellij_session": runtime["current_zellij_session"](check),
        "squad_identity": row_binding,
        "pane": (
            {"pane_id": pane.get("pane_id"), "title": pane.get("title")}
            if pane is not None
            else None
        ),
    }
    return {
        "ok": True,
        "role": role,
        "identity_id": row.get("id"),
        "identity_generation": identity_generation,
        "identity_binding_id": _structured_reference(
            "office-identity",
            role=identity.get("role"),
            identity_id=row.get("id"),
            identity_generation=identity_generation,
            session_id=row_binding.get("session_id"),
            pane_id=(identity.get("pane") or {}).get("pane_id")
            if isinstance(identity.get("pane"), dict)
            else None,
        ),
        "identity": identity,
        "visible_pane_selection": pane_selection,
    }


def _supplied_preload_acks(
    args: argparse.Namespace,
) -> tuple[dict[str, object], str | None]:
    raw = getattr(args, "office_preload_acks_json", None)
    if raw is None or raw == "":
        return {}, None
    if isinstance(raw, Mapping):
        return {str(key): value for key, value in raw.items()}, None
    if not isinstance(raw, str):
        return {}, "active_office_preload_ack_invalid"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}, "active_office_preload_ack_invalid"
    if not isinstance(parsed, dict):
        return {}, "active_office_preload_ack_invalid"
    return {str(key): value for key, value in parsed.items()}, None


def active_office_preload_ack_gate(
    args: argparse.Namespace,
    check: dict[str, Any],
    role: str,
    *,
    require_visible: bool,
    allow_missing_identity: bool,
) -> dict[str, Any]:
    runtime = _runtime()
    identity = active_office_identity_binding(
        check,
        role,
        require_visible=require_visible,
        workspace=Path(args.workspace).resolve(),
    )
    if not identity.get("ok"):
        pending_reason = identity.get("reason")
        new_identity_allowed = pending_reason == "active_office_identity_missing" or (
            pending_reason == "active_office_identity_generation_required"
            and bool(getattr(args, "reclaim_existing", False))
        )
        if allow_missing_identity and new_identity_allowed:
            return {
                "ok": True,
                "role": role,
                "gate": "PRELOAD_PENDING",
                "reason": "new_identity_requires_office_preload_ack",
                "identity": identity,
                "identity_generation_challenge": _new_identity_generation_challenge(),
                "preload_ack": None,
            }
        return {
            "ok": False,
            "role": role,
            "gate": "FAILED",
            "reason": str(identity.get("reason") or "active_office_identity_missing"),
            "identity": identity,
            "preload_ack": None,
        }
    supplied, supplied_error = _supplied_preload_acks(args)
    if supplied_error is not None:
        return {
            "ok": False,
            "role": role,
            "gate": "FAILED",
            "reason": supplied_error,
            "identity": identity,
            "preload_ack": None,
        }
    workspace = Path(args.workspace).resolve()
    persisted = runtime["read_office_state"](
        workspace,
        runtime["current_zellij_session"](check),
    )
    persisted_roles = persisted.get("roles") if isinstance(persisted, dict) else None
    persisted_role = (
        persisted_roles.get(role)
        if isinstance(persisted_roles, dict)
        and isinstance(persisted_roles.get(role), dict)
        else {}
    )
    ack = supplied.get(role)
    source = "current_invocation"
    if ack is None:
        ack = persisted_role.get("preload_ack")
        source = "selected_context_office_state"
    profile = runtime["profile_metadata"](role)
    expected = {
        "schema": runtime["OFFICE_PRELOAD_ACK_SCHEMA"],
        "preload_status": "PASSED",
        "identity_id": identity.get("identity_id"),
        "identity_generation": identity.get("identity_generation"),
        "identity_binding_id": identity.get("identity_binding_id"),
        "role_key": role,
        "direct_superior": runtime["direct_superior_metadata"](role)[
            "direct_superior"
        ],
        "profile_source": profile.get("profile_source"),
        "dossier_path": str(runtime["office_dossier_path"](role)),
        "court_skill_path": str(runtime["skill_root"]() / "SKILL.md"),
        "agent_dossier_loaded": "YES",
    }
    loaded_skills = ack.get("loaded_skills") if isinstance(ack, Mapping) else None
    valid = (
        isinstance(ack, Mapping)
        and runtime["OFFICE_PRELOAD_ACK_REQUIRED_FIELDS"].issubset(ack)
        and all(ack.get(field) == value for field, value in expected.items())
        and isinstance(loaded_skills, list)
        and "decretum-matrix"
        in {str(item).strip().lower() for item in loaded_skills}
    )
    return {
        "ok": bool(valid),
        "role": role,
        "gate": "PASSED" if valid else "FAILED",
        "reason": "ok" if valid else "active_office_preload_ack_required",
        "identity": identity,
        "preload_ack": dict(ack) if isinstance(ack, Mapping) else None,
        "preload_ack_source": source,
        "expected": expected,
    }
