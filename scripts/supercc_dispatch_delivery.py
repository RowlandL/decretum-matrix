"""Atomic superCC transport preflight, delivery, and state transition chain."""

from __future__ import annotations

import argparse
import datetime as dt
from functools import wraps
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping

sys.dont_write_bytecode = True

from court_dispatch_hierarchy import (
    DispatchHierarchyDecision,
    validate_dispatch_hierarchy,
)


RuntimeProvider = Callable[[], Mapping[str, Any]]
_RUNTIME_PROVIDER: RuntimeProvider | None = None


def configure_runtime(provider: RuntimeProvider) -> None:
    """Bind the launcher namespace without importing the launcher in reverse."""

    global _RUNTIME_PROVIDER
    _RUNTIME_PROVIDER = provider


def _refresh_runtime() -> None:
    if _RUNTIME_PROVIDER is None:
        raise RuntimeError("supercc dispatch delivery runtime is not configured")
    for name, value in _RUNTIME_PROVIDER().items():
        if not name.startswith("__"):
            globals()[name] = value


def _bound(function):
    @wraps(function)
    def call(*args, **kwargs):
        _refresh_runtime()
        return function(*args, **kwargs)

    return call


@_bound
def native_pane_enter_sequence(
    workspace: Path,
    pane_id: str,
    text: str,
    *,
    dry_run: bool,
    zellij_session: str | None = None,
    payload_kind: str = "TEXT_PROMPT",
    squad_delivery_order: str = "UNSPECIFIED",
) -> dict[str, Any]:
    commands = [
        zellij_command_args("action", "write-chars", "-p", pane_id, text, session=zellij_session),
        zellij_command_args("action", "write", "-p", pane_id, PHYSICAL_ENTER_BYTE, session=zellij_session),
        ["sleep", f"{POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS:g}s"],
        zellij_command_args("action", "write", "-p", pane_id, PHYSICAL_ENTER_BYTE, session=zellij_session),
    ]
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "commands": commands,
            "native_enter_payload_kind": payload_kind,
            "squad_delivery_order": squad_delivery_order,
            "physical_enter_byte": PHYSICAL_ENTER_BYTE,
            "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
            "post_dispatch_physical_enter": "planned",
        }
    write_result = run_command(commands[0], cwd=workspace, timeout=10, stdout_limit=4000, stderr_limit=4000)
    if not write_result.get("ok"):
        return {
            "ok": False,
            "reason": "native_write_chars_failed_before_enter",
            "write": write_result,
            "enter": {"ok": False, "skipped": True, "reason": "write_chars_failed"},
            "native_enter_payload_kind": payload_kind,
            "squad_delivery_order": squad_delivery_order,
            "physical_enter_byte": PHYSICAL_ENTER_BYTE,
            "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
            "post_dispatch_physical_enter": {
                "ok": False,
                "skipped": True,
                "reason": "write_chars_failed",
            },
            "commands": commands,
        }
    enter_result = run_command(commands[1], cwd=workspace, timeout=10, stdout_limit=4000, stderr_limit=4000)
    if not enter_result.get("ok"):
        return {
            "ok": False,
            "reason": "native_first_enter_failed_before_delay",
            "write": write_result,
            "enter": enter_result,
            "native_enter_payload_kind": payload_kind,
            "squad_delivery_order": squad_delivery_order,
            "physical_enter_byte": PHYSICAL_ENTER_BYTE,
            "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
            "post_dispatch_physical_enter": {
                "ok": False,
                "skipped": True,
                "reason": "first_enter_failed",
            },
            "commands": commands,
        }
    time.sleep(max(0.0, POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS))
    post_enter_result = run_command(commands[3], cwd=workspace, timeout=10, stdout_limit=4000, stderr_limit=4000)
    return {
        "ok": bool(write_result.get("ok")) and bool(enter_result.get("ok")) and bool(post_enter_result.get("ok")),
        "write": write_result,
        "enter": enter_result,
        "native_enter_payload_kind": payload_kind,
        "squad_delivery_order": squad_delivery_order,
        "physical_enter_byte": PHYSICAL_ENTER_BYTE,
        "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
        "post_dispatch_physical_enter": post_enter_result,
        "commands": commands,
    }


@_bound
def dispatch_target_profile_gate(role: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Prove the canonical target profile/dossier before transport probing."""

    fields = profile.get("profile_fields")
    fields = fields if isinstance(fields, dict) else {}
    profile_source = profile.get("profile_source")
    dossier_path = office_dossier_path(role)
    reasons: list[str] = []
    if profile.get("office_profile_loaded") is not True:
        reasons.append("standing_profile_not_loaded")
    if fields.get("role_key") != role:
        reasons.append("standing_profile_role_mismatch")
    if fields.get("direct_superior") != fallback_direct_superior(role):
        reasons.append("standing_profile_direct_superior_mismatch")
    if not isinstance(profile_source, str) or not profile_source:
        reasons.append("standing_profile_source_missing")
    if not dossier_path.is_file():
        reasons.append("supercc_dossier_missing")
    return {
        "ok": not reasons,
        "role": role,
        "profile_source": profile.get("profile_source"),
        "office_dossier_path": str(office_dossier_path(role)),
        "reason": "ok" if not reasons else ",".join(reasons),
        "reason_codes": reasons,
    }


@_bound
def _blocked_transport_preflight(
    *,
    reason: str,
    transport_action: str,
    entries: list[dict[str, Any]],
    entry: dict[str, Any],
) -> dict[str, Any]:
    skipped = {"ok": False, "skipped": True, "reason": reason}
    return {
        "ok": False,
        "dispatch_blocked": True,
        "dispatch_block_reason": reason,
        "dispatch_hierarchy_reason": (
            reason if reason.startswith("dispatch_hierarchy_") else None
        ),
        "transport_action": transport_action,
        **entry,
        "transport_preflight": entries,
        "special_lifecycle_preflight": [
            item for item in entries if item.get("role") in SPECIAL_LIFECYCLE_OFFICES
        ],
        "task_evidence": dict(skipped),
        "squad_evidence": dict(skipped),
        "native_enter_dispatch": dict(skipped),
        "state": dict(skipped),
    }


@_bound
def special_lifecycle_dispatch_authority(
    role: str,
    calling_office: str,
    superior: dict[str, str],
    profile: dict[str, Any],
    target_profile_gate: dict[str, Any],
) -> tuple[DispatchHierarchyDecision, dict[str, Any]]:
    """Resolve explicit special-role authority on top of the shared deny graph."""

    shared = validate_dispatch_hierarchy(
        action="dispatch",
        calling_office=calling_office,
        target_role=role,
        target_direct_superior=superior["direct_superior"],
        instance_kind="office",
        canonical_authority=True if target_profile_gate["ok"] else None,
        owner_role=None,
        child_profile=None,
    )
    manifest_path = skill_root() / "references" / "manifests" / "court-dispatch-hierarchy.v1.json"
    roles_path = skill_root() / "references" / "court-roles.yaml"
    action = SPECIAL_LIFECYCLE_ACTIONS.get(role)
    profile_fields = profile.get("profile_fields")
    profile_fields = profile_fields if isinstance(profile_fields, dict) else {}
    authority: dict[str, Any] = {
        "schema": "court.supercc.special_lifecycle_authority.v1",
        "role": role,
        "action": action,
        "calling_office": calling_office,
        "direct_superior": superior["direct_superior"],
        "allowed_callers": [],
        "hierarchy_manifest_path": str(manifest_path),
        "hierarchy_manifest_path": shared.hierarchy_manifest_path,
        "court_roles_path": str(roles_path),
        "standing_profile_path": profile.get("profile_source"),
        "court_roles_entry": "unknown",
        "gate": "FAILED",
    }
    if shared.reason_codes == ("dispatch_hierarchy_manifest_invalid",):
        authority["reason"] = "dispatch_hierarchy_manifest_invalid"
        return shared, authority
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        roles_text = roles_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        decision = DispatchHierarchyDecision(
            allowed=False,
            edge_class=None,
            normalized_caller=calling_office,
            normalized_target=role,
            normalized_owner=None,
            reason_codes=("dispatch_hierarchy_manifest_invalid",),
            hierarchy_schema=shared.hierarchy_schema,
            hierarchy_manifest_path=shared.hierarchy_manifest_path,
        )
        authority["reason"] = "dispatch_hierarchy_manifest_invalid"
        return decision, authority
    role_sets = manifest.get("role_sets") if isinstance(manifest, dict) else None
    special_roles = role_sets.get("special_lifecycle") if isinstance(role_sets, dict) else None
    canonical_roles = manifest.get("canonical_roles") if isinstance(manifest, dict) else None
    canonical_target = canonical_roles.get(role) if isinstance(canonical_roles, dict) else None
    manifest_superior = canonical_target.get("direct_superior") if isinstance(canonical_target, dict) else None
    authority["court_roles_entry"] = "present" if f"  {role}:" in roles_text else "absent_uses_manifest_and_profile"
    if (
        not isinstance(special_roles, list)
        or role not in special_roles
        or action is None
        or manifest_superior != superior["direct_superior"]
        or profile_fields.get("direct_superior") != manifest_superior
    ):
        decision = DispatchHierarchyDecision(
            allowed=False,
            edge_class=None,
            normalized_caller=calling_office,
            normalized_target=role,
            normalized_owner=None,
            reason_codes=("dispatch_hierarchy_manifest_invalid",),
            hierarchy_schema=shared.hierarchy_schema,
            hierarchy_manifest_path=shared.hierarchy_manifest_path,
        )
        authority["reason"] = "special_lifecycle_authority_mismatch"
        return decision, authority
    allowed_callers = tuple(part for part in str(manifest_superior).split("/") if part)
    authority["allowed_callers"] = list(allowed_callers)
    if not target_profile_gate["ok"]:
        authority["reason"] = "dispatch_hierarchy_target_profile_required"
        return shared, authority
    if calling_office not in allowed_callers:
        authority["reason"] = "dispatch_hierarchy_edge_forbidden"
        return shared, authority
    decision = DispatchHierarchyDecision(
        allowed=True,
        edge_class="special_lifecycle_dispatch",
        normalized_caller=calling_office,
        normalized_target=role,
        normalized_owner=None,
        reason_codes=(),
        hierarchy_schema=shared.hierarchy_schema,
        hierarchy_manifest_path=shared.hierarchy_manifest_path,
    )
    authority["gate"] = "PASSED"
    authority["reason"] = "ok"
    return decision, authority


@_bound
def supercc_transport_preflight(
    args: argparse.Namespace,
    roles: tuple[str, ...] | list[str],
    *,
    transport_action: str,
    sender: str | None = None,
    allow_missing_identity_roles: tuple[str, ...] | set[str] = (),
    validate_active_preload: bool = True,
    check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate shared profile/hierarchy and current-identity preload evidence."""

    entries: list[dict[str, Any]] = []
    for role in roles:
        if role not in (*OFFICES, "taizi"):
            entry = {"role": role, "transport_action": transport_action}
            entries.append(entry)
            return _blocked_transport_preflight(
                reason="unknown_supercc_office_role",
                transport_action=transport_action,
                entries=entries,
                entry=entry,
            )
        profile = profile_metadata(role)
        profile_gate = dispatch_target_profile_gate(role, profile)
        superior = direct_superior_metadata(role)
        calling_office = "user" if role == "taizi" else sender or resolved_calling_office(args, role)
        authority: dict[str, Any] | None = None
        decision: DispatchHierarchyDecision | None
        if role in (*THREE_OFFICES, *MINISTRY_OFFICES):
            decision = validate_dispatch_hierarchy(
                action="dispatch",
                calling_office=calling_office,
                target_role=role,
                target_direct_superior=superior["direct_superior"],
                instance_kind="office",
                canonical_authority=True if profile_gate["ok"] else None,
                owner_role=None,
                child_profile=None,
            )
        elif role in SPECIAL_LIFECYCLE_OFFICES:
            decision, authority = special_lifecycle_dispatch_authority(
                role, calling_office, superior, profile, profile_gate
            )
        else:
            decision = None
        entry = {
            "role": role,
            "transport_action": transport_action,
            "calling_office": calling_office,
            "direct_superior": superior["direct_superior"],
            "target_profile_gate": profile_gate,
            "special_lifecycle_action": SPECIAL_LIFECYCLE_ACTIONS.get(role),
            "special_lifecycle_authority": authority,
            "hierarchy_gate": (
                "PASSED"
                if decision is None and profile_gate["ok"]
                else "PASSED"
                if decision is not None and decision.allowed
                else "REJECTED"
            ),
            "hierarchy_schema": decision.hierarchy_schema if decision else None,
            "hierarchy_manifest_path": decision.hierarchy_manifest_path if decision else None,
            "hierarchy_edge_class": decision.edge_class if decision else None,
            "hierarchy_calling_office": decision.normalized_caller if decision else calling_office,
            "hierarchy_target_role": decision.normalized_target if decision else role,
            "hierarchy_owner_role": decision.normalized_owner if decision else None,
        }
        entries.append(entry)
        if not profile_gate["ok"] or (decision is not None and not decision.allowed):
            reason = (
                decision.reason_codes[0]
                if decision is not None and decision.reason_codes
                else "dispatch_hierarchy_edge_forbidden"
            )
            if not profile_gate["ok"] and decision is None:
                reason = "dispatch_hierarchy_target_profile_required"
            return _blocked_transport_preflight(
                reason=reason,
                transport_action=transport_action,
                entries=entries,
                entry=entry,
            )
    if validate_active_preload:
        workspace = Path(args.workspace).resolve()
        check = check or supercc_check_for_args(args, workspace)
        allow_missing = set(allow_missing_identity_roles)
        for entry in entries:
            role = str(entry["role"])
            ack_gate = active_office_preload_ack_gate(
                args,
                check,
                role,
                require_visible=role in (*THREE_OFFICES, "taizi"),
                allow_missing_identity=role in allow_missing,
            )
            entry["active_office_preload_ack_gate"] = ack_gate
            if not ack_gate["ok"]:
                return _blocked_transport_preflight(
                    reason=str(ack_gate["reason"]),
                    transport_action=transport_action,
                    entries=entries,
                    entry=entry,
                )
    return {
        "ok": True,
        "transport_action": transport_action,
        "transport_preflight": entries,
        "special_lifecycle_preflight": [
            item for item in entries if item.get("role") in SPECIAL_LIFECYCLE_OFFICES
        ],
        "check": check,
    }


@_bound
def special_lifecycle_transport_preflight(
    args: argparse.Namespace,
    roles: tuple[str, ...] | list[str],
    *,
    transport_action: str,
    sender: str | None = None,
) -> dict[str, Any]:
    return supercc_transport_preflight(
        args,
        tuple(role for role in roles if role in SPECIAL_LIFECYCLE_OFFICES),
        transport_action=transport_action,
        sender=sender,
        validate_active_preload=False,
    )


@_bound
def build_native_receive_command_prompt(
    role: str,
    *,
    action: str,
    dispatch_uid: str | None = None,
    task_id: str | None = None,
) -> str:
    commands = supercc_squad_relative_commands("receive", role, "--json")
    return commands["native"]


@_bound
def build_dispatch_payload(
    args: argparse.Namespace,
    role: str,
    pane: dict[str, str] | None,
    profile: dict[str, Any],
    calling_office: str | None = None,
    hierarchy: DispatchHierarchyDecision | None = None,
    dispatch_context: dict[str, Any] | None = None,
) -> str:
    dispatch_uid = args.dispatch_uid or f"manual-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{role}"
    superior = direct_superior_metadata(role)
    calling_office = calling_office or resolved_calling_office(args, role)
    lines = [
        f"ENTER_DISPATCH dispatch_uid={dispatch_uid}",
        "delivery_channel=NATIVE_DOUBLE_ENTER_VISIBLE_OR_NON_VISIBLE_STRUCTURED_TASK",
        f"assigned_office={role}",
        f"calling_office={calling_office}",
        f"calling_office_source={'explicit' if getattr(args, 'calling_office', None) else 'role_default'}",
        f"direct_superior={superior['direct_superior']}",
        f"direct_superior_source={superior['direct_superior_source']}",
        f"physical_enter_byte={PHYSICAL_ENTER_BYTE}",
        f"post_dispatch_physical_enter_delay_seconds={POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS:g}",
        f"squad_delivery_order={SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER}",
        f"native_enter_payload_kind={NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND}",
        f"physical_enter_sequence=squad_task_and_send_then_write_receive_command_then_enter_then_sleep_{POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS:g}s_then_enter",
        f"expected_pane_title={OFFICES[role]['title'] if role not in (*MINISTRY_OFFICES, *SPECIAL_LIFECYCLE_OFFICES) else ('NON_VISIBLE_MINISTRY_BY_CONTRACT' if role in MINISTRY_OFFICES else 'NON_VISIBLE_SPECIAL_LIFECYCLE_BY_CONTRACT')}",
        f"expected_pane_id={(pane or {}).get('pane_id', 'non_visible_structured_dispatch' if role in (*MINISTRY_OFFICES, *SPECIAL_LIFECYCLE_OFFICES) else 'missing')}",
        f"profile_source={profile['profile_source']}",
        f"profile_version={profile.get('profile_version')}",
        f"office_dossier_path={office_dossier_path(role)}",
        f"light_bootstrap_policy={SUPERCC_LIGHT_BOOTSTRAP_POLICY}",
        f"six_ministry_step_plan_required={'true' if role in MINISTRY_OFFICES else 'false'}",
    ]
    if dispatch_context is not None:
        lines.extend(
            [
                f"dispatch_context_packet_schema={dispatch_context['schema']}",
                f"dispatch_context_packet_id={dispatch_context['packet_id']}",
                f"dispatch_context_packet_bytes={dispatch_context['packet_bytes']}",
                f"semantic_dispatch_context_packet_id={dispatch_context['semantic_packet_id']}",
                f"bounded_scope_id={dispatch_context['scope_id']}",
                "dispatch_context_packet_json="
                + json.dumps(
                    dispatch_context["packet"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ]
        )
    if hierarchy is not None:
        lines.extend(
            [
                "hierarchy_gate=PASSED",
                f"hierarchy_schema={hierarchy.hierarchy_schema}",
                f"hierarchy_manifest_path={hierarchy.hierarchy_manifest_path}",
                f"hierarchy_edge_class={hierarchy.edge_class}",
                f"hierarchy_calling_office={hierarchy.normalized_caller}",
                f"hierarchy_target_role={hierarchy.normalized_target}",
                f"hierarchy_owner_role={hierarchy.normalized_owner or ''}",
            ]
        )
    if role in SPECIAL_LIFECYCLE_OFFICES:
        lines.extend(
            [
                f"special_lifecycle_action={SPECIAL_LIFECYCLE_ACTIONS[role]}",
                "special_lifecycle_visibility=non_visible_by_default",
            ]
        )
    lines.extend(["message:", args.message])
    return "\n".join(lines)


@_bound
def enter_dispatch(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace).resolve()
    role = args.role
    if role not in OFFICES:
        raise ValueError(f"unknown role for --enter-dispatch: {role}")
    if not args.message:
        raise ValueError("--enter-dispatch requires --message")

    profile = profile_metadata(role)
    target_profile_gate = dispatch_target_profile_gate(role, profile)
    superior = direct_superior_metadata(role)
    calling_office = resolved_calling_office(args, role)
    special_lifecycle_authority: dict[str, Any] | None = None
    if role in (*THREE_OFFICES, *MINISTRY_OFFICES):
        hierarchy = validate_dispatch_hierarchy(
            action="dispatch",
            calling_office=calling_office,
            target_role=role,
            target_direct_superior=superior["direct_superior"],
            instance_kind="office",
            canonical_authority=True if target_profile_gate["ok"] else None,
            owner_role=None,
            child_profile=None,
        )
    elif role in SPECIAL_LIFECYCLE_OFFICES:
        hierarchy, special_lifecycle_authority = special_lifecycle_dispatch_authority(
            role,
            calling_office,
            superior,
            profile,
            target_profile_gate,
        )
    else:
        hierarchy = None
    if hierarchy is not None and not hierarchy.allowed:
        reason = (
            hierarchy.reason_codes[0]
            if hierarchy.reason_codes
            else "dispatch_hierarchy_edge_forbidden"
        )
        skipped = {"ok": False, "skipped": True, "reason": reason}
        return {
            "ok": False,
            "dispatch_uid": getattr(args, "dispatch_uid", None),
            "role": role,
            "calling_office": calling_office,
            "calling_office_source": (
                "explicit" if getattr(args, "calling_office", None) else "role_default"
            ),
            "direct_superior": superior["direct_superior"],
            "direct_superior_source": superior["direct_superior_source"],
            "target_profile_gate": target_profile_gate,
            "special_lifecycle_action": SPECIAL_LIFECYCLE_ACTIONS.get(role),
            "special_lifecycle_authority": special_lifecycle_authority,
            "dispatch_blocked": True,
            "dispatch_block_reason": reason,
            "dispatch_hierarchy_reason": reason,
            "hierarchy_gate": "REJECTED",
            "hierarchy_schema": hierarchy.hierarchy_schema,
            "hierarchy_manifest_path": hierarchy.hierarchy_manifest_path,
            "hierarchy_edge_class": hierarchy.edge_class,
            "hierarchy_calling_office": hierarchy.normalized_caller,
            "hierarchy_target_role": hierarchy.normalized_target,
            "hierarchy_owner_role": hierarchy.normalized_owner,
            "task_evidence": dict(skipped),
            "squad_evidence": dict(skipped),
            "native_enter_dispatch": dict(skipped),
            "state": dict(skipped),
        }
    hierarchy_evidence = (
        {
            "hierarchy_gate": "PASSED",
            "hierarchy_schema": hierarchy.hierarchy_schema,
            "hierarchy_manifest_path": hierarchy.hierarchy_manifest_path,
            "hierarchy_edge_class": hierarchy.edge_class,
            "hierarchy_calling_office": hierarchy.normalized_caller,
            "hierarchy_target_role": hierarchy.normalized_target,
            "hierarchy_owner_role": hierarchy.normalized_owner,
        }
        if hierarchy is not None
        else {
            "hierarchy_gate": "NOT_APPLICABLE_SPECIAL_LIFECYCLE",
            "hierarchy_schema": None,
            "hierarchy_manifest_path": None,
            "hierarchy_edge_class": None,
            "hierarchy_calling_office": calling_office,
            "hierarchy_target_role": role,
            "hierarchy_owner_role": None,
        }
    )
    special_lifecycle_evidence = {
        "special_lifecycle_action": SPECIAL_LIFECYCLE_ACTIONS.get(role),
        "special_lifecycle_authority": special_lifecycle_authority,
    }

    dispatch_context = validate_enter_dispatch_context(
        args,
        role,
        calling_office,
        superior["direct_superior"],
    )
    if not dispatch_context["ok"]:
        reason = str(dispatch_context["reason"])
        skipped = {"ok": False, "skipped": True, "reason": reason}
        return {
            "ok": False,
            "dispatch_uid": getattr(args, "dispatch_uid", None),
            "role": role,
            "calling_office": calling_office,
            "direct_superior": superior["direct_superior"],
            "target_profile_gate": target_profile_gate,
            **hierarchy_evidence,
            **special_lifecycle_evidence,
            "dispatch_blocked": True,
            "dispatch_block_reason": reason,
            "dispatch_context_packet": dispatch_context,
            "task_evidence": dict(skipped),
            "squad_evidence": dict(skipped),
            "native_enter_dispatch": dict(skipped),
            "state": dict(skipped),
        }
    transport_preflight = supercc_transport_preflight(
        args,
        (role,),
        transport_action="enter_dispatch",
        sender=calling_office,
        allow_missing_identity_roles=set(
            (*MINISTRY_OFFICES, *SPECIAL_LIFECYCLE_OFFICES)
        ),
    )
    if not transport_preflight["ok"]:
        transport_preflight["dispatch_context_packet"] = dispatch_context
        return transport_preflight
    check = transport_preflight.get("check") or supercc_check_for_args(args, workspace)
    zellij_session = current_zellij_session(check)
    visible = visible_office_panes(check)
    uniqueness = office_uniqueness_gate(
        check,
        visible,
        role,
        require_visible=role not in (*MINISTRY_OFFICES, *SPECIAL_LIFECYCLE_OFFICES),
    )
    pane_selection = uniqueness["visible_pane_selection"]
    pane = pane_selection.get("pane") if pane_selection.get("ok") else None
    active_ids_for_role = uniqueness.get("active_squad_ids_for_role") or []
    duplicate_ids_for_role = uniqueness.get("duplicate_identity_ids") or []
    visible_pane_count_for_role = int(uniqueness.get("visible_pane_count") or 0)
    non_visible_structured_dispatch = bool(
        role in (*MINISTRY_OFFICES, *SPECIAL_LIFECYCLE_OFFICES)
        and visible_pane_count_for_role == 0
        and len(active_ids_for_role) <= 1
        and not duplicate_ids_for_role
    )
    ministry_non_visible_dispatch = bool(
        role in MINISTRY_OFFICES and non_visible_structured_dispatch
    )
    special_lifecycle_non_visible_dispatch = bool(
        role in SPECIAL_LIFECYCLE_OFFICES and non_visible_structured_dispatch
    )
    payload_text = build_dispatch_payload(
        args,
        role,
        pane,
        profile,
        calling_office,
        hierarchy,
        dispatch_context,
    )
    dispatch_uid = str(args.dispatch_uid)
    native_commands: list[list[str]] = []
    native_enter_dispatch: dict[str, Any]
    delivery_channel = "NATIVE_DOUBLE_ENTER_VISIBLE"
    dispatch_blocked = False
    dispatch_block_reason: str | None = None
    if not uniqueness.get("ok") and not non_visible_structured_dispatch:
        dispatch_blocked = True
        dispatch_block_reason = uniqueness.get("reason") or "office_uniqueness_gate_failed"
        delivery_channel = "FAILED_OFFICE_UNIQUENESS_GATE"
        native_enter_dispatch = {
            "ok": False,
            "reason": dispatch_block_reason,
            "commands": [],
            "visible_pane_selection": pane_selection,
            "office_uniqueness_gate": uniqueness,
        }
    elif ministry_non_visible_dispatch:
        delivery_channel = NON_VISIBLE_MINISTRY_DISPATCH_CHANNEL
        native_enter_dispatch = {
            "ok": False,
            "skipped": True,
            "reason": "ministry_non_visible_by_contract; structured squad task plus shangshu supervision is the dispatch channel",
            "commands": [],
            "visible_pane_selection": pane_selection,
            "office_uniqueness_gate": uniqueness,
            "visible_window_contract": "six_ministries_must_not_be_visible_by_default",
            "squad_delivery_order": SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER,
        }
    elif special_lifecycle_non_visible_dispatch:
        delivery_channel = NON_VISIBLE_SPECIAL_LIFECYCLE_DISPATCH_CHANNEL
        native_enter_dispatch = {
            "ok": False,
            "skipped": True,
            "reason": "special_lifecycle_non_visible_by_contract; structured squad task plus direct-superior review is the dispatch channel",
            "commands": [],
            "visible_pane_selection": pane_selection,
            "office_uniqueness_gate": uniqueness,
            "visible_window_contract": "special_lifecycle_roles_must_not_be_visible_by_default",
            "squad_delivery_order": SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER,
        }
    elif not pane:
        if not getattr(args, "allow_squad_only_fallback", False):
            dispatch_blocked = True
            dispatch_block_reason = "expected_visible_pane_missing_and_squad_only_fallback_not_allowed"
            delivery_channel = "FAILED_VISIBLE_PANE_GATE"
            native_enter_dispatch = {
                "ok": False,
                "reason": dispatch_block_reason,
                "commands": [],
                "visible_pane_selection": pane_selection,
                "office_uniqueness_gate": uniqueness,
            }
        else:
            delivery_channel = "SQUAD_ONLY_FALLBACK_DEGRADED"
            native_enter_dispatch = {
                "ok": False,
                "reason": "expected visible pane missing; explicit --allow-squad-only-fallback used",
                "commands": [],
                "visible_pane_selection": pane_selection,
                "office_uniqueness_gate": uniqueness,
            }
    squad_message = f"[ENTER_DISPATCH_MIRROR] dispatch_uid={dispatch_uid}; delivery_channel={delivery_channel}\n{payload_text}"
    task_title = getattr(args, "task_title", None) or f"ENTER_DISPATCH {dispatch_uid} -> {role}"
    task_required = not dispatch_blocked
    if args.dry_run:
        task_evidence = (
            create_squad_task_assignment(
                workspace,
                calling_office,
                role,
                title=task_title,
                body=payload_text,
                dispatch_uid=dispatch_uid,
                dry_run=True,
            )
            if task_required
            else {"ok": False, "skipped": True, "reason": dispatch_block_reason}
        )
        squad_command = ["squad", "send"]
        if task_evidence.get("task_id"):
            squad_command.extend(["--task-id", str(task_evidence["task_id"])])
        squad_command.extend([calling_office, role, squad_message])
        if task_required and not isinstance(task_evidence.get("task_id"), str):
            squad_evidence = {
                "ok": False,
                "dry_run": True,
                "skipped": True,
                "reason": "task_id_parse_failed_before_squad_mirror",
                "command": squad_command,
                "task_id": task_evidence.get("task_id"),
            }
        else:
            squad_evidence = {
                "ok": task_required,
                "dry_run": True,
                "command": squad_command,
                "task_id": task_evidence.get("task_id"),
            }
    elif task_required:
        task_evidence = create_squad_task_assignment(
            workspace,
            calling_office,
            role,
            title=task_title,
            body=payload_text,
            dispatch_uid=dispatch_uid,
            dry_run=False,
        )
        task_id = task_evidence.get("task_id")
        if not bool(task_evidence.get("ok")):
            squad_evidence = {
                "ok": False,
                "skipped": True,
                "reason": "task_create_failed_before_squad_mirror",
                "task_id": task_id,
            }
        elif not isinstance(task_id, str):
            squad_evidence = {
                "ok": False,
                "skipped": True,
                "reason": "task_id_parse_failed_before_squad_mirror",
                "task_id": task_id,
                "task_id_parse_ok": False,
            }
        else:
            squad_evidence = send_squad_notice(
                workspace,
                calling_office,
                role,
                squad_message,
                dry_run=False,
                task_id=task_id,
            )
    else:
        task_evidence = {"ok": False, "skipped": True, "reason": dispatch_block_reason}
        squad_evidence = {"ok": False, "skipped": True, "reason": dispatch_block_reason}

    task_id_for_cc = (
        task_evidence.get("task_id")
        if isinstance(task_evidence.get("task_id"), str)
        else None
    )
    squad_delivery_ok = (not task_required) or (
        bool(task_evidence.get("ok"))
        and bool(task_id_for_cc)
        and bool(squad_evidence.get("ok"))
    )
    if not dispatch_blocked and pane:
        pane_id = pane["pane_id"]
        command_prompt = build_native_receive_command_prompt(
            role,
            action="enter_dispatch",
            dispatch_uid=dispatch_uid,
            task_id=task_id_for_cc,
        )
        native_commands = [
            zellij_command_args("action", "write-chars", "-p", pane_id, command_prompt, session=zellij_session),
            zellij_command_args("action", "write", "-p", pane_id, PHYSICAL_ENTER_BYTE, session=zellij_session),
            ["sleep", f"{POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS:g}s"],
            zellij_command_args("action", "write", "-p", pane_id, PHYSICAL_ENTER_BYTE, session=zellij_session),
        ]
        if not squad_delivery_ok:
            native_enter_dispatch = {
                "ok": False,
                "skipped": True,
                "reason": "squad_delivery_failed_before_native_enter",
                "commands": native_commands,
                "native_enter_payload_kind": NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND,
                "squad_delivery_order": SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER,
                "physical_enter_byte": PHYSICAL_ENTER_BYTE,
                "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
                "task_evidence": task_evidence,
                "squad_evidence": squad_evidence,
            }
        else:
            native_enter_dispatch = native_pane_enter_sequence(
                workspace,
                pane_id,
                command_prompt,
                dry_run=bool(args.dry_run),
                zellij_session=zellij_session,
                payload_kind=NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND,
                squad_delivery_order=SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER,
            )
    dispatch_ok = (not dispatch_blocked) and (
        squad_delivery_ok
        if non_visible_structured_dispatch or delivery_channel.startswith("SQUAD_ONLY")
        else (squad_delivery_ok and bool(native_enter_dispatch.get("ok")))
    )
    phase_cycle = supercc_phase_for_roles((role,), sender=calling_office)
    inspector_wake_cc = (
        maybe_send_inspector_wake_cc(
            args,
            workspace,
            calling_office,
            (role,),
            reason="enter_dispatch",
            expected_mode=("task_queued_non_visible" if ministry_non_visible_dispatch else "awake"),
            dispatch_uid=dispatch_uid,
            task_id=task_id_for_cc,
        )
        if dispatch_ok
        else {
            "ok": True,
            "skipped": True,
            "reason": "dispatch_delivery_failed_before_inspector_mirror",
        }
    )

    state_mode = "runtime_degraded" if dispatch_blocked else (
        "task_queued_non_visible" if non_visible_structured_dispatch else "awake"
    )
    state_reason = (
        f"enter_dispatch_blocked:{dispatch_block_reason}"
        if dispatch_blocked
        else (
            "enter_dispatch_non_visible_structured_task"
            if non_visible_structured_dispatch
            else "enter_dispatch"
        )
    )
    native_enter_role = (
        "not_used_non_visible_structured_dispatch"
        if non_visible_structured_dispatch
        else "receive_command_wake_after_squad_task_and_send"
    )
    dispatch_route_policy = (
        [delivery_channel]
        if non_visible_structured_dispatch
        else [
            "SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER",
            "NATIVE_DOUBLE_ENTER_VISIBLE receive-command wake",
            "HERMES_PROFILE_NATIVE_READINESS_SUPPLEMENT if Hermes",
        ]
    )
    preflight_entry = transport_preflight["transport_preflight"][0]
    ack_gate = preflight_entry.get("active_office_preload_ack_gate") or {}
    state_record = {
        **build_mode_records((role,), default_mode=state_mode, reason=state_reason)[role],
        "preload_status": (
            "PASSED"
            if ack_gate.get("gate") == "PASSED"
            else "NOT_APPLICABLE_NO_ACTIVE_IDENTITY"
        ),
        "preload_contract_version": OFFICE_PRELOAD_ACK_SCHEMA,
        "identity_id": (ack_gate.get("identity") or {}).get("identity_id"),
        "identity_generation": (ack_gate.get("identity") or {}).get(
            "identity_generation"
        ),
        "preload_ack": ack_gate.get("preload_ack"),
        "dispatch_uid": dispatch_uid,
        "dispatch_context_packet_schema": dispatch_context["schema"],
        "dispatch_context_packet_id": dispatch_context["packet_id"],
        "dispatch_context_packet_bytes": dispatch_context["packet_bytes"],
        "semantic_dispatch_context_packet_id": dispatch_context[
            "semantic_packet_id"
        ],
        "bounded_scope_id": dispatch_context["scope_id"],
        "bounded_scope_allowed_paths": dispatch_context["allowed_paths"],
        "office_uniqueness_gate": uniqueness,
        "dispatch_delivery_channel": delivery_channel,
        "dispatch_router_phase": "phase2_structured_task_required_non_visible_ministry_supported",
        "squad_delivery_order": (
            SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER if not dispatch_blocked else None
        ),
        "native_enter_payload_kind": NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND if pane else None,
        "ministry_non_visible_dispatch": ministry_non_visible_dispatch,
        "special_lifecycle_non_visible_dispatch": special_lifecycle_non_visible_dispatch,
        "non_visible_structured_dispatch": non_visible_structured_dispatch,
        "visible_window_contract": "visible_windows_only_taizi_three_departments; six_ministries_and_special_lifecycle_roles_non_visible_by_default",
        "supercc_phase_cycle": phase_cycle,
        "inspector_wake_cc_policy": INSPECTOR_WAKE_CC_POLICY,
        "inspector_wake_cc": inspector_wake_cc,
        "wake_cc_to_patrol_inspector": inspector_enabled(args),
        "supervision_channel": SUPERVISION_CHANNEL,
        "supervision_evidence": "PASSED",
        "shangshu_ministry_report_integration": "REQUIRED",
        "squad_active_wake_capability": "not_guaranteed_probe_20260629_stale_agent_remained_queued_unleased",
        "squad_role": "structured_task_and_audit_mirror_not_sole_wake",
        "native_enter_role": native_enter_role,
        "hermes_profile_native_policy": "supplemental_readiness_only_for_Hermes; normal_superCC_requires_zellij_squad_visible_route; readiness_only_is_not_dispatch_success",
        "calling_office": calling_office,
        "calling_office_source": "explicit" if args.calling_office else "role_default",
        "direct_superior": superior["direct_superior"],
        "direct_superior_source": superior["direct_superior_source"],
        "target_profile_gate": target_profile_gate,
        **hierarchy_evidence,
        **special_lifecycle_evidence,
        "native_enter_dispatch": native_enter_dispatch,
        "physical_enter_byte": PHYSICAL_ENTER_BYTE,
        "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
        "task_evidence": task_evidence,
        "squad_evidence": squad_evidence,
        "expected_pane_title": OFFICES[role]["title"],
        "expected_pane_id": (pane or {}).get("pane_id"),
    }
    if args.dry_run:
        state = {"ok": True, "skipped": True, "reason": "dry-run"}
    elif not dispatch_ok:
        state = {
            "ok": True,
            "skipped": True,
            "reason": "dispatch_delivery_failed_before_awake_or_queued_state",
        }
    else:
        state = write_office_state(
            workspace,
            {role: state_record},
            zellij_session=current_zellij_session(check),
            dry_run=False,
        )

    return {
        "ok": dispatch_ok,
        "dispatch_uid": dispatch_uid,
        "role": role,
        "calling_office": calling_office,
        "calling_office_source": "explicit" if args.calling_office else "role_default",
        "direct_superior": superior["direct_superior"],
        "direct_superior_source": superior["direct_superior_source"],
        "target_profile_gate": target_profile_gate,
        "transport_preflight": transport_preflight["transport_preflight"],
        "dispatch_context_packet": dispatch_context,
        **hierarchy_evidence,
        **special_lifecycle_evidence,
        "office_uniqueness_gate": uniqueness,
        "dispatch_blocked": dispatch_blocked,
        "dispatch_block_reason": dispatch_block_reason,
        "dispatch_delivery_channel": delivery_channel,
        "dispatch_router_phase": "phase2_structured_task_required_non_visible_ministry_supported",
        "squad_delivery_order": (
            SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER if not dispatch_blocked else None
        ),
        "native_enter_payload_kind": NATIVE_ENTER_PAYLOAD_KIND_RECEIVE_COMMAND if pane else None,
        "ministry_non_visible_dispatch": ministry_non_visible_dispatch,
        "special_lifecycle_non_visible_dispatch": special_lifecycle_non_visible_dispatch,
        "non_visible_structured_dispatch": non_visible_structured_dispatch,
        "visible_window_contract": "visible_windows_only_taizi_three_departments; six_ministries_and_special_lifecycle_roles_non_visible_by_default",
        "supercc_phase_cycle": phase_cycle,
        "supercc_request_limit_policy": SUPERCC_REQUEST_LIMIT_POLICY,
        "request_rate_limit_per_minute": SUPERCC_REQUEST_RATE_LIMIT_PER_MINUTE,
        "inspector_wake_cc_policy": INSPECTOR_WAKE_CC_POLICY,
        "inspector_wake_cc": inspector_wake_cc,
        "wake_cc_to_patrol_inspector": inspector_enabled(args),
        "supervision_channel": SUPERVISION_CHANNEL,
        "supervision_evidence": "PASSED",
        "shangshu_ministry_report_integration": "REQUIRED",
        "squad_active_wake_capability": "not_guaranteed_probe_20260629_stale_agent_remained_queued_unleased",
        "squad_role": "structured_task_and_audit_mirror_not_sole_wake",
        "native_enter_role": native_enter_role,
        "hermes_profile_native_policy": "supplemental_readiness_only_for_Hermes; normal_superCC_requires_zellij_squad_visible_route; readiness_only_is_not_dispatch_success",
        "dispatch_route_policy_phase1": dispatch_route_policy,
        "expected_pane_title": (
            "NON_VISIBLE_MINISTRY_BY_CONTRACT"
            if ministry_non_visible_dispatch
            else (
                "NON_VISIBLE_SPECIAL_LIFECYCLE_BY_CONTRACT"
                if special_lifecycle_non_visible_dispatch
                else OFFICES[role]["title"]
            )
        ),
        "expected_pane_id": None if non_visible_structured_dispatch else (pane or {}).get("pane_id"),
        "office_profile_loaded": profile["office_profile_loaded"],
        "profile_source": profile["profile_source"],
        "profile_version": profile["profile_version"],
        "office_dossier_path": str(office_dossier_path(role)),
        "light_bootstrap_policy": SUPERCC_LIGHT_BOOTSTRAP_POLICY,
        "native_enter_dispatch": native_enter_dispatch,
        "physical_enter_byte": PHYSICAL_ENTER_BYTE,
        "post_dispatch_physical_enter_delay_seconds": POST_DISPATCH_PHYSICAL_ENTER_DELAY_SECONDS,
        "task_evidence": task_evidence,
        "squad_evidence": squad_evidence,
        "state": state,
        "supercc_env_gate": check.get("supercc_env_gate"),
        "visible_display_gate": check.get("visible_display_gate"),
        "display_transport_gate": check.get("display_transport_gate"),
        "office_client_gate": check.get("office_client_gate"),
        "check": check,
    }
