"""Schema, context partitioning, and file store for superCC office state."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from typing import Any, Callable

from court_file_lock import atomic_write_text, file_lock
from court_platform import user_data_base


SUPERCC_STATE_SCHEMA_V1 = "court.supercc.office_state.v1"
SUPERCC_STATE_SCHEMA = "court.supercc.office_state.v2"
SUPERCC_HEALTH_SCHEMA = "court.supercc.turn_start_health.v1"
StateEnricher = Callable[[str, dict[str, Any]], dict[str, Any]]
AtomicWriter = Callable[[Path, str], None]


def shiguan_runtime_path(*parts: str) -> Path:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        from shiguan_paths import reference_path  # type: ignore

        return reference_path("court-runtime", *parts)
    except Exception:
        fallback = (
            user_data_base()
            / "court-shiguan"
            / "court-capability-router"
            / "references"
            / "court-runtime"
        )
        return fallback.joinpath(*parts)


def office_state_path() -> Path:
    return shiguan_runtime_path("supercc-office-state.json")


def office_health_path() -> Path:
    return shiguan_runtime_path("supercc-turn-start-health.jsonl")


def supercc_runtime_lock_path() -> Path:
    return shiguan_runtime_path("supercc-runtime.lock")


def normalized_office_context(
    workspace: Path | str,
    zellij_session: str | None,
) -> tuple[str, str | None, str]:
    resolved = str(Path(workspace).expanduser().resolve())
    normalized_workspace = os.path.normcase(os.path.normpath(resolved))
    normalized_session = str(zellij_session).strip() if zellij_session is not None else ""
    normalized_session = normalized_session or None
    identity = json.dumps(
        {"workspace": normalized_workspace, "zellij_session": normalized_session},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    context_id = "ctx-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return resolved, normalized_session, context_id


def office_context_id(workspace: Path | str, zellij_session: str | None) -> str:
    return normalized_office_context(workspace, zellij_session)[2]


def office_v1_state_error(payload: dict[str, Any]) -> str:
    if not isinstance(payload.get("workspace"), str) or not str(payload["workspace"]).strip():
        return "v1 workspace must be a non-empty string"
    if payload.get("zellij_session") is not None and not isinstance(payload.get("zellij_session"), str):
        return "v1 zellij_session must be a string or null"
    roles = payload.get("roles")
    valid = isinstance(roles, dict) and all(
        isinstance(role, str) and role.strip() and isinstance(state, dict)
        for role, state in roles.items()
    )
    return "" if valid else "v1 roles must map non-empty strings to objects"


def office_context_error(context_id: object, context: object) -> str:
    if not isinstance(context_id, str) or not isinstance(context, dict):
        return "v2 context key and value must be strings/objects"
    workspace = context.get("workspace")
    session = context.get("zellij_session")
    roles = context.get("roles")
    if context.get("context_id") != context_id or not isinstance(workspace, str) or not workspace.strip():
        return f"v2 context identity is malformed: {context_id}"
    if session is not None and not isinstance(session, str):
        return f"v2 context session is malformed: {context_id}"
    roles_valid = isinstance(roles, dict) and all(
        isinstance(role, str) and role.strip() and isinstance(state, dict)
        for role, state in roles.items()
    )
    if not roles_valid or office_context_id(workspace, session) != context_id:
        return f"v2 context workspace/session/roles mismatch: {context_id}"
    return ""


def office_v2_state_error(payload: dict[str, Any]) -> str:
    contexts = payload.get("contexts")
    active_id = payload.get("active_context_id")
    if not isinstance(contexts, dict) or not isinstance(active_id, str) or active_id not in contexts:
        return "v2 contexts/active_context_id are malformed"
    for context_id, context in contexts.items():
        error = office_context_error(context_id, context)
        if error:
            return error
    active = contexts[active_id]
    if any(payload.get(field) != active.get(field) for field in ("workspace", "zellij_session", "roles")):
        return "v2 active compatibility projection mismatch"
    return ""


def write_office_state(
    workspace: Path,
    modes: dict[str, dict[str, Any]],
    *,
    zellij_session: str | None,
    dry_run: bool,
    state_enricher: StateEnricher | None = None,
    atomic_writer: AtomicWriter | None = None,
) -> dict[str, Any]:
    path = office_state_path()
    enrich = state_enricher or (lambda _role, state: dict(state))
    writer = atomic_writer or atomic_write_text

    def build_payload() -> dict[str, Any]:
        contexts: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid existing superCC office state: {exc}") from exc
            if not isinstance(existing, dict):
                raise ValueError("existing superCC office state must be an object")
            if existing.get("schema") == SUPERCC_STATE_SCHEMA:
                error = office_v2_state_error(existing)
                if error:
                    raise ValueError(error)
                contexts = dict(existing["contexts"])
            elif existing.get("schema") in (None, SUPERCC_STATE_SCHEMA_V1):
                error = office_v1_state_error(existing)
                if error:
                    raise ValueError(error)
                legacy_workspace, legacy_session, legacy_context_id = normalized_office_context(
                    str(existing["workspace"]), existing.get("zellij_session")
                )
                contexts[legacy_context_id] = {
                    "context_id": legacy_context_id,
                    "updated_at": existing.get("updated_at"),
                    "workspace": legacy_workspace,
                    "zellij_session": legacy_session,
                    "roles": existing["roles"],
                }
            else:
                raise ValueError("unsupported existing superCC office state schema")
        resolved_workspace, normalized_session, context_id = normalized_office_context(
            workspace, zellij_session
        )
        existing_context = contexts.get(context_id, {})
        if context_id in contexts and not isinstance(existing_context, dict):
            raise ValueError(f"superCC office context must be an object: {context_id}")
        existing_roles = existing_context.get("roles", {}) if isinstance(existing_context, dict) else {}
        if not isinstance(existing_roles, dict):
            raise ValueError(f"superCC office context roles must be an object: {context_id}")
        merged_roles = {
            role: enrich(role, state)
            for role, state in {**existing_roles, **modes}.items()
        }
        if any(not isinstance(state, dict) for state in merged_roles.values()):
            raise ValueError("superCC office state enricher must return objects")
        updated_at = dt.datetime.now(dt.timezone.utc).isoformat()
        contexts[context_id] = {
            "context_id": context_id,
            "updated_at": updated_at,
            "workspace": resolved_workspace,
            "zellij_session": normalized_session,
            "roles": merged_roles,
        }
        return {
            "schema": SUPERCC_STATE_SCHEMA,
            "updated_at": updated_at,
            "active_context_id": context_id,
            "workspace": resolved_workspace,
            "zellij_session": normalized_session,
            "roles": merged_roles,
            "contexts": contexts,
        }

    if dry_run:
        payload = build_payload()
        return {"ok": True, "dry_run": True, "path": str(path), "payload": payload}
    with file_lock(supercc_runtime_lock_path(), timeout=30.0):
        payload = build_payload()
        writer(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return {"ok": True, "path": str(path), "payload": payload}


def append_turn_health(
    payload: dict[str, Any],
    dry_run: bool,
    *,
    atomic_writer: AtomicWriter | None = None,
) -> dict[str, Any]:
    path = office_health_path()
    if dry_run:
        return {"ok": True, "dry_run": True, "path": str(path), "payload": payload}
    writer = atomic_writer or atomic_write_text
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    with file_lock(supercc_runtime_lock_path(), timeout=30.0):
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
        writer(path, existing + line)
    return {"ok": True, "path": str(path)}


def read_office_state(
    workspace: Path | str | None = None,
    zellij_session: str | None = None,
) -> dict[str, Any]:
    path = office_state_path()

    def read_state() -> dict[str, Any]:
        if not path.exists():
            return {"ok": False, "path": str(path), "roles": {}, "reason": "missing"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "path": str(path), "roles": {}, "reason": str(exc)}
        if not isinstance(payload, dict):
            return {"ok": False, "path": str(path), "roles": {}, "reason": "state payload must be an object"}
        requested_context_id = office_context_id(workspace, zellij_session) if workspace is not None else None
        schema = payload.get("schema")
        if schema == SUPERCC_STATE_SCHEMA:
            error = office_v2_state_error(payload)
            if error:
                return {"ok": False, "path": str(path), "roles": {}, "reason": error}
            contexts = payload.get("contexts")
            context_id = requested_context_id or payload.get("active_context_id")
            context = contexts.get(context_id) if context_id else None
            if not isinstance(context, dict):
                return {"ok": False, "path": str(path), "roles": {}, "reason": "context_missing", "context_id": context_id}
            roles = context.get("roles", {})
            if not isinstance(roles, dict):
                return {"ok": False, "path": str(path), "roles": {}, "reason": "context_roles_malformed", "context_id": context_id}
            projection = {
                "schema": schema,
                "active_context_id": context_id,
                "updated_at": context.get("updated_at"),
                "workspace": context.get("workspace"),
                "zellij_session": context.get("zellij_session"),
                "roles": roles,
            }
            return {
                "ok": True,
                "path": str(path),
                "context_id": context_id,
                "roles": projection["roles"],
                "payload": projection,
            }
        if schema not in (None, SUPERCC_STATE_SCHEMA_V1):
            return {"ok": False, "path": str(path), "roles": {}, "reason": "unsupported_schema", "schema": schema}
        error = office_v1_state_error(payload)
        if error:
            return {"ok": False, "path": str(path), "roles": {}, "reason": error}
        roles = payload["roles"]
        if requested_context_id is not None:
            legacy_workspace = payload.get("workspace")
            if not legacy_workspace or office_context_id(str(legacy_workspace), payload.get("zellij_session")) != requested_context_id:
                return {"ok": False, "path": str(path), "roles": {}, "reason": "context_missing", "context_id": requested_context_id}
        return {
            "ok": True,
            "path": str(path),
            "roles": roles,
            "payload": payload,
            "legacy_schema": schema or SUPERCC_STATE_SCHEMA_V1,
        }

    lock_path = supercc_runtime_lock_path()
    if lock_path.exists():
        with file_lock(lock_path, timeout=30.0):
            return read_state()
    return read_state()
