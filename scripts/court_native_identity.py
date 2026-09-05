"""Pure L4 identity adapter for Codex canonical child task paths.

This module converts a host-returned canonical ``/root/...`` task handle only
after the caller supplies a task-bound trust context.  It deliberately does not
infer a child thread identifier from ``CODEX_THREAD_ID``.
"""

from __future__ import annotations

import re
from typing import Mapping


CANONICAL_AGENT_PATH_IDENTITY_KIND = "canonical_agent_path"
IDENTITY_CONTEXT_SCHEMA = "court.native_host_identity_context.v1"
_SESSION_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_PATH_RE = re.compile(r"^/root(?:/[a-z0-9_]+)+$")


def _text(value: object, field: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str):
        raise ValueError(f"native_identity:{field}_invalid")
    text = value.strip()
    if not text or len(text) > maximum or "\x00" in text:
        raise ValueError(f"native_identity:{field}_invalid")
    return text


def _session_id(value: object, field: str) -> str:
    session_id = _text(value, field, maximum=64).lower()
    if _SESSION_RE.fullmatch(session_id) is None:
        raise ValueError(f"native_identity:{field}_invalid")
    return session_id


def canonical_agent_path(value: object, field: str = "canonical_agent_path") -> str:
    path = _text(value, field)
    if _PATH_RE.fullmatch(path) is None:
        raise ValueError(f"native_identity:{field}_invalid")
    return path


def _positive_epoch(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("native_identity:semantic_epoch_invalid")
    return value


def normalize_identity_context(
    value: object,
    *,
    expected_epoch: int,
) -> dict[str, object]:
    """Validate the minimal root-projected parent trust context."""

    if not isinstance(value, Mapping) or set(value) != {
        "case_session_id",
        "semantic_epoch",
        "trusted_parent_paths",
    }:
        raise ValueError("native_identity:context_fields_invalid")
    epoch = _positive_epoch(value.get("semantic_epoch"))
    if epoch != expected_epoch:
        raise ValueError("native_identity:context_epoch_mismatch")
    parents = value.get("trusted_parent_paths")
    if not isinstance(parents, (list, tuple)) or not parents:
        raise ValueError("native_identity:trusted_parents_invalid")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in parents:
        if not isinstance(raw, Mapping) or set(raw) != {"path", "kind"}:
            raise ValueError("native_identity:trusted_parents_invalid")
        kind = _text(raw.get("kind"), "trusted_parent.kind", maximum=64)
        path = _text(raw.get("path"), "trusted_parent.path")
        if kind == "taizi_root":
            if path != "/root":
                raise ValueError("native_identity:taizi_root_path_invalid")
        elif kind == "same_case_ready_shangshu":
            path = canonical_agent_path(path, "trusted_parent.path")
        else:
            raise ValueError("native_identity:trusted_parent_kind_invalid")
        if path in seen:
            raise ValueError("native_identity:trusted_parent_duplicate")
        seen.add(path)
        normalized.append({"path": path, "kind": kind})
    return {
        "schema": IDENTITY_CONTEXT_SCHEMA,
        "case_session_id": _session_id(value.get("case_session_id"), "case_session_id"),
        "semantic_epoch": epoch,
        "trusted_parent_paths": normalized,
    }


def canonical_agent_path_identity(
    task_handle: object,
    *,
    expected_leaf: object,
    context: object,
    expected_epoch: int,
    trace_reader_thread_id: object,
    trace_session_id: object,
    host_action_id: object,
) -> dict[str, object]:
    """Bind a returned canonical child path without inventing a child thread."""

    path = canonical_agent_path(task_handle, "task_handle")
    leaf = _text(expected_leaf, "expected_leaf", maximum=256)
    actual_leaf = path.rsplit("/", 1)[-1]
    if actual_leaf != leaf:
        raise ValueError("native_identity:canonical_leaf_mismatch")
    normalized = normalize_identity_context(context, expected_epoch=expected_epoch)
    normalized_trace_session = _session_id(trace_session_id, "trace_session_id")
    if normalized["case_session_id"] != normalized_trace_session:
        raise ValueError("native_identity:case_session_trace_mismatch")
    parent = path.rsplit("/", 1)[0]
    matching = [
        item
        for item in normalized["trusted_parent_paths"]
        if isinstance(item, Mapping) and item.get("path") == parent
    ]
    if len(matching) != 1:
        raise ValueError("native_identity:canonical_parent_untrusted")
    parent_kind = str(matching[0]["kind"])
    return {
        "host_identity_kind": CANONICAL_AGENT_PATH_IDENTITY_KIND,
        "host_task_id": path,
        "host_instance_id": path,
        "host_thread_id": None,
        "trace_issuer_thread_id": None,
        "trace_reader_thread_id": _text(
            trace_reader_thread_id,
            "trace_reader_thread_id",
        ),
        "trace_session_id": normalized_trace_session,
        "case_session_id": normalized["case_session_id"],
        "trusted_parent_kind": parent_kind,
        "host_action_id": _text(host_action_id, "host_action_id"),
    }
