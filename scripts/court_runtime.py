"""Machine-checkable /court state and audit ledger.

This module is intentionally small and file-backed. It gives the skill a local
runtime substrate without depending on a GUI service or an external agent host.

Semantic checkpoint/verify (VERIFIED/DISPATCHABLE) are P00 semantic gates for
三省会审; they never prove that zhongshu/menxia/shangshu were dispatched or
replied as offices. Office work requires agent-admit plus host-native
spawn/reuse/wake, or an explicit serial_inline record; semantic receipts must
not be reported as office replies (runtime_degraded/PARTIAL otherwise).
"""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True

from court_office_config import ENTRY_PRELOAD_BUDGET_BYTES
from typing import Any, Mapping, Sequence

from stdio_encoding import configure_stdio

from court_agent_admission import budget_lease_access_contract_error
from court_complexity_budget import evaluate_context_economy, normalize_budget_pool
from court_dispatch_policy import MAX_AGENT_TREE_DEPTH, MAX_AGENT_TREE_THREADS, select_wave
from court_dispatch_hierarchy import validate_dispatch_hierarchy
from court_intake_gate import (
    INTAKE_SCHEMA,
    WORK_KINDS,
    conversation_gate_json_schema,
    legacy_conversation_gate,
    minimal_formal_task_example,
    require_new_formal_task_gate,
    require_task_correction_gate,
    validate_conversation_gate,
    validate_conversation_gate_diagnostics,
)
from court_office_bootstrap import (
    build_child_office_profile,
    build_office_assignment_binding,
    build_preload_manifest,
    validate_preload_ack,
)
from court_model_router import (
    EVALUATION_LEVELS,
    MODEL_MAX_REASONING_EFFORT,
    MODEL_ROUTE_SCHEMA,
    TRANSPORTS,
    route_office_model,
)
from court_native_host_dispatch import (
    normalize_native_host_dispatch_request,
    native_request_reference,
    native_task_suffix,
    validate_native_host_action_receipt,
)
from court_case_binding import case_reference, plan_reference, office_capsule_reference
from court_file_lock import atomic_write_text, file_lock
from court_multi_agent_protocol import (
    ProtocolRequirements,
    canonical_repo_relative_paths,
    repository_paths_overlap,
    select_protocol,
)
from court_codex_office_worker import validate_host_proof
from court_operation_journal import (
    ledger_pair_write, recover_ledger_pair, require_readable_ledgers,
    MARKER_SCHEMA,
    LEGACY_JOURNAL_SCHEMA,
    LEGACY_MARKER_SCHEMA,
    OPERATION_V2_NAMESPACE,
    canonical_operation_id,
    journal_path as operation_journal_path,
    load_json as load_operation_json,
    marker_path as operation_marker_path,
    normalize_operation_binding,
    remove_marker as remove_operation_marker,
    write_journal,
    write_json as write_operation_json,
)
from court_semantic_continuity import (
    build_semantic_receipt,
    canonical_json_sha256,
    derive_semantic_receipt,
    finalize_semantic_receipt,
    initial_semantic_binding,
    invariant_capsule_json_schema,
    invariant_capsule_template,
    normalize_consultation_refs,
    normalize_semantic_context,
    normalize_result_envelope,
    office_result_envelope_json_schema,
    build_result_quarantine_core,
    build_result_recovery_binding,
    build_result_recovery_projection,
    result_binding_problems,
    result_recovery_record_disposition,
    result_recovery_target_binding_fields,
    validate_result_recovery_binding,
    validate_result_recovery_head,
    validate_result_recovery_projection,
    result_quarantine_metadata,
    build_result_recovery_head,
    deterministic_result_recovery_event_id,
    source_result_payload_sha256,
    result_recovery_review_receipt_json_schema,
    result_recovery_handoff_receipt_json_schema,
    result_recovery_consume_receipt_json_schema,
    resume_context_problems,
    semantic_binding_problems,
    semantic_binding_for_revision,
    semantic_receipt_integrity_problems,
    validate_dispatch_context_packet,
    validate_invariant_capsule,
    verify_semantic_receipt,
)
from shiguan_paths import code_root, ensure_shared_seed, reference_path


STATES = {
    "Pending",
    "Taizi",
    "ThreeDepartments",
    "ThreeDepartmentsPetition",
    "TaiziReply",
    "ShangshuDispatch",
    "SixMinistries",
    "Workshops",
    "MenxiaReview",
    "ShiguanRecorded",
    "Done",
    "Paused",
    "Cancelled",
    "Rejected",
}

TRANSITIONS = {
    "Pending": {"Taizi", "Paused", "Cancelled"},
    "Taizi": {"ThreeDepartments", "Done", "Paused", "Cancelled"},
    "ThreeDepartments": {"ThreeDepartmentsPetition", "Taizi", "Paused", "Cancelled"},
    "ThreeDepartmentsPetition": {"TaiziReply", "ThreeDepartments", "Rejected", "Paused", "Cancelled"},
    "TaiziReply": {"ShangshuDispatch", "ThreeDepartments", "Done", "Paused", "Cancelled"},
    "ShangshuDispatch": {"SixMinistries", "MenxiaReview", "Paused", "Cancelled"},
    "SixMinistries": {"Workshops", "MenxiaReview", "Paused", "Cancelled"},
    "Workshops": {"MenxiaReview", "Paused", "Cancelled"},
    "MenxiaReview": {"ShiguanRecorded", "ThreeDepartments", "ShangshuDispatch", "Paused", "Rejected", "Cancelled"},
    "ShiguanRecorded": {"Done", "MenxiaReview"},
    "Done": set(),
    "Paused": {"Pending", "Taizi", "ThreeDepartments", "ThreeDepartmentsPetition", "TaiziReply", "ShangshuDispatch", "SixMinistries", "Workshops", "MenxiaReview", "Cancelled"},
    "Cancelled": set(),
    "Rejected": {"ThreeDepartments", "Cancelled"},
}

OFFICES = {
    "taizi",
    "zhongshu",
    "menxia",
    "shangshu",
    "hubu",
    "libu",
    "bingbu",
    "xingbu",
    "gongbu",
    "libu-hr",
    "shiguan",
    "zaochao",
}

REPORT_TIERS = {"brief", "standard", "full"}
READ_ONLY_RE = re.compile(r"(只读|不要改文件|review only|read[- ]?only)", re.IGNORECASE)
RUNTIME_SCHEMA_VERSION = 3
OUTCOME_ASSESSMENT_SCHEMA = "court.outcome_assessment.v1"
RUNTIME_ASSESSMENT_BINDING_SCHEMA = "court.runtime_assessment_binding.v1"
CHECKPOINT_RECEIPT_SCHEMA = "court.shiguan_checkpoint_receipt.v1"
ARCHIVE_PRODUCER_RECEIPT_SCHEMA = "court.shiguan_archive_checkpoint_receipt.v1"
COMPLETION_TRANSACTION_SCHEMA = "court.completion_transaction.v1"
COMPLETION_SOURCE_SCHEMA = "court.completion_source.v1"
COMPLETION_SOURCE_KINDS = {"host_report", "bounded_trace", "serial_inline"}
COMPLETION_SOURCE_MAX_ITEMS = 16
RESIDUAL_GAPS_MAX_ITEMS = 16
RESIDUAL_GAP_MAX_BYTES = 512
OUTCOME_ASSESSMENT_GATES = {"PASSED", "PASSED_WITH_CONCERNS", "PARTIAL", "BLOCKED"}
COMPLETABLE_OUTCOME_ASSESSMENT_GATES = {"PASSED", "PASSED_WITH_CONCERNS"}
RUNTIME_ASSESSMENT_BINDING_FIELDS = {
    "schema",
    "task_id",
    "charter_revision",
    "case_ref",
    "assessment_ref",
    "evidence_ref",
    "gate",
    "reasons",
    "completion_source",
    "completion_source_ref",
    "residual_gaps",
    "assessed_at",
}
CHECKPOINT_RECEIPT_FIELDS = {
    "schema",
    "receipt_id",
    "task_id",
    "charter_revision",
    "case_ref",
    "assessment_ref",
    "record_ref",
    "archive_path",
    "recorded_at",
}
CHECKPOINT_RECEIPT_CONCERN_FIELDS = {"residual_gaps"}
CONTROL_STATES = {"Paused", "Cancelled"}
SERIAL_OVERRIDE_RE = re.compile(
    r"(parallel_dispatch\s*=\s*NOT_APPLICABLE/user_serial_override|"
    r"完全串行|只允许串行|不得派生子|不派生子|no child spawn|serial override)",
    re.IGNORECASE,
)
TERMINAL_AGENT_STATUSES = {"completed", "failed", "cancelled", "closed"}
OFFICE_INSTANCE_KINDS = frozenset({"child_agent", "worktree_thread"})
OFFICE_LIFECYCLE_RECEIPT_SCHEMA = "court.office.lifecycle_receipt.v1"
RESULT_RECOVERY_OPERATION_SCHEMA = "court.result_recovery.operation.v1"
RESULT_RECOVERY_JOURNAL_SCHEMA = "court.result_recovery.journal.v1"
RESULT_RECOVERY_ZERO_SHA256 = "0" * 64
RESULT_RECOVERY_STATES = {
    "REVIEW_PENDING",
    "READY_FOR_HANDOFF",
    "REJECTED",
    "HANDED_OFF",
    "CONSUMED",
}
RESULT_RECOVERY_REASON_CODES = frozenset(
    {
        "ACCEPT_BOUNDED_EVIDENCE",
        "REJECT_OUT_OF_SCOPE",
        "REJECT_UNVERIFIABLE",
        "REJECT_PRIVACY",
        "REJECT_DUPLICATE",
        "REJECT_SEMANTIC_DRIFT",
        "SOURCE_HIERARCHY_INVALID",
        "HANDOFF_TARGET_BINDING_ACCEPTED",
        "TARGET_NOT_DISPATCHABLE",
        "TARGET_HIERARCHY_MISMATCH",
        "DELIVERY_BINDING_MISMATCH",
        "CONSUME_TARGET_RESULT_ACCEPTED",
        "TARGET_RESULT_BINDING_MISMATCH",
    }
)
RESULT_BINDING_REASON_CODES = {
    "task_id": "RESULT_BINDING_TASK_ID_MISMATCH",
    "semantic_epoch": "RESULT_BINDING_SEMANTIC_EPOCH_MISMATCH",
    "case_ref": "RESULT_BINDING_CASE_REF_MISMATCH",
    "checkpoint_id": "RESULT_BINDING_CHECKPOINT_ID_MISMATCH",
    "dispatch_uid": "RESULT_BINDING_DISPATCH_UID_MISMATCH",
    "attempt": "RESULT_BINDING_ATTEMPT_MISMATCH",
    "office_instance_id": "RESULT_BINDING_OFFICE_INSTANCE_ID_MISMATCH",
    "office_instance_kind": "RESULT_BINDING_OFFICE_INSTANCE_KIND_MISMATCH",
    "carrier_proof": "RESULT_BINDING_CARRIER_PROOF_MISMATCH",
    "agent_id": "RESULT_BINDING_AGENT_ID_MISMATCH",
    "role": "RESULT_BINDING_ROLE_MISMATCH",
    "direct_superior": "RESULT_BINDING_DIRECT_SUPERIOR_MISMATCH",
    "worktree": "RESULT_BINDING_WORKTREE_MISMATCH",
    "write_set_sha256": "RESULT_BINDING_WRITE_SET_SHA256_MISMATCH",
}
WORKTREE_PROOF_FIELDS = (
    "thread_id",
    "canonical_worktree_id",
    "canonical_worktree_path",
    "repo_id",
    "common_dir_fingerprint",
    "worktree_fingerprint",
    "branch",
    "start_head",
)
WORKTREE_GIT_READ_ONLY_COMMANDS = (
    ("rev-parse", "--show-toplevel"),
    ("rev-parse", "--absolute-git-dir"),
    ("rev-parse", "--path-format=absolute", "--git-common-dir"),
    ("rev-parse", "--is-bare-repository"),
    ("symbolic-ref", "--quiet", "--short", "HEAD"),
    ("rev-parse", "HEAD"),
)
AGENT_LONG_CONTEXT_TOKENS = 32_000
AGENT_MAX_RECENT_FORK_TURNS = 3
AGENT_DEFAULT_DEADLINE_SECONDS = None
AGENT_DEFAULT_TOOL_CALL_BUDGET = None
AGENT_EXECUTION_BUDGET_DEFAULTS = {
    "deadline_seconds": AGENT_DEFAULT_DEADLINE_SECONDS,
    "tool_call_budget": AGENT_DEFAULT_TOOL_CALL_BUDGET,
}
LEGACY_OPERATION_FILENAME_SCAN_LIMIT = 64
AGENT_MESSAGE_BUDGET_SCHEMA = "court.agent.dispatch_message_budget.v1"
AGENT_MESSAGE_BUDGET_FLOOR_CHARS = 6_000
AGENT_MESSAGE_BUDGET_QUANTUM_CHARS = 1_000
AGENT_MESSAGE_BUDGET_CEILING_CHARS = 12_000
CONTEXT_ECONOMY_EXPLICIT_OVERRIDE_SOURCES = {
    "latest_user_explicit",
    "current_user_explicit",
    "taizi_explicit_budget",
}
CONTEXT_ECONOMY_BINDING_FIELDS = (
    "dispatch_context_packet_ref",
    "dispatch_context_packet_bytes",
    "semantic_receipt_id",
    "context_budget_pool_ref",
    "context_budget_id",
    "context_economy_receipt_ref",
    "context_economy_decision",
    "context_fork_mode",
    "context_mode",
    "context_result_mode",
    "context_tool_output_mode",
    "context_override_source",
    "context_system_memory_percent",
)
PUBLIC_CONTEXT_HARD_LIMITS = {
    "ram_percent_max": 99.0,
    "memory_mb_max": 2_048,
    "context_tokens_max": 100_000,
    "message_chars_max": 12_000,
    "retained_agents_max": 15,
}
# Deprecated compatibility alias. New admission code uses the bounded V1 ceiling.
AGENT_MAX_MESSAGE_CHARS = AGENT_MESSAGE_BUDGET_FLOOR_CHARS
AGENT_MESSAGE_BUDGET_FIELDS = (
    "message_budget_schema",
    "message_budget_policy",
    "message_measurement",
    "message_scope",
    "message_chars",
    "message_budget_floor_chars",
    "message_budget_quantum_chars",
    "message_budget_ceiling_chars",
    "message_budget_effective_chars",
    "message_budget_status",
    "message_budget_basis",
    "message_required_chars",
    "message_optional_chars",
    "message_component_status",
    "message_component_reason",
    "message_budget_remaining_chars",
    "message_overage_chars",
    "required_reduction_chars",
    "optional_compression_target_chars",
    "required_message_overage_chars",
    "compression_possible_without_required_loss",
    "message_budget_retryable",
    "compression_guidance",
)


def now_text() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalize_optional_timestamp(value: object, field: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def skill_root() -> Path:
    return code_root()


def runtime_root() -> Path:
    configured = os.environ.get("COURT_RUNTIME_ROOT")
    if configured:
        return Path(configured)
    return reference_path("court-runtime")


def tasks_path() -> Path:
    return runtime_root() / "tasks.json"


def events_path() -> Path:
    return runtime_root() / "court_events.jsonl"


def lock_path() -> Path:
    return runtime_root() / "runtime.lock"


def completion_transaction_path(task_id: object) -> Path:
    digest = hashlib.sha256(str(task_id).encode("utf-8")).hexdigest()
    return runtime_root() / f"completion-transaction-{digest}.json"


def result_recovery_marker_path(operation_id: object) -> Path:
    """Return the disposable crash marker path for one recovery operation."""
    digest = hashlib.sha256(str(operation_id).encode("utf-8")).hexdigest()
    return runtime_root() / f"result-recovery-operation-{digest}.json"


def _operation_binding(
    task: Mapping[str, object],
    *,
    operation_id: object,
    operation_kind: str,
    request_schema: str,
    actor: str,
    expected_task_revision: int,
    target_ref: Mapping[str, object],
) -> dict[str, object]:
    """Build the server-owned binding used by v2 operation journals."""

    return normalize_operation_binding(
        {
            "operation_id": canonical_operation_id(operation_id),
            "task_id": str(task.get("task_id") or ""),
            "operation_kind": operation_kind,
            "case_ref": case_reference(task),
            "actor": str(actor or "").strip(),
            "role": str(actor or "").strip(),
            "expected_task_revision": expected_task_revision,
            "target_ref": dict(target_ref),
            "request_schema": request_schema,
        }
    )


def _operation_receipt_ref(receipt: object) -> str | None:
    if not isinstance(receipt, Mapping):
        return None
    for field in ("receipt_id", "record_ref", "event_id"):
        value = str(receipt.get(field) or "").strip()
        if value:
            return value
    return None


def _write_operation_journal(
    *,
    binding: Mapping[str, object],
    phase: str,
    receipt: Mapping[str, object] | None,
    updated_at: str,
    committed_task_revision: int | None = None,
    event_id: str | None = None,
) -> dict[str, object]:
    """Persist only v2 references; task/event records remain authoritative."""

    return write_journal(
        runtime_root(),
        operation_id=binding["operation_id"],
        operation_binding=binding,
        phase=phase,
        receipt_ref=_operation_receipt_ref(receipt),
        updated_at=updated_at,
        committed_task_revision=committed_task_revision,
        event_id=event_id,
    )


def _stored_operation_binding(operation: Mapping[str, object]) -> dict[str, object]:
    raw = operation.get("operation_binding")
    if raw is None:
        raise ValueError("LEGACY_READ_ONLY")
    try:
        return normalize_operation_binding(raw, operation_id=operation.get("operation_id"))
    except ValueError as exc:
        raise ValueError("operation_binding_conflict") from exc


def _require_operation_replay_mode(
    *,
    stored_binding: Mapping[str, object],
    incoming_binding: Mapping[str, object] | None,
    replay_only: bool,
    payload_present: bool,
) -> None:
    """Apply the no-body replay contract to an existing operation."""

    if incoming_binding is not None:
        if replay_only:
            comparable = set(stored_binding) - {"expected_task_revision"}
            if any(
                stored_binding.get(field) != incoming_binding.get(field)
                for field in comparable
            ):
                raise ValueError("operation_binding_conflict")
        elif dict(stored_binding) != dict(incoming_binding):
            raise ValueError("operation_binding_conflict")
    if not replay_only or payload_present:
        raise ValueError("operation_replay_requires_reference_only")


def _task_revision_value(task: Mapping[str, object]) -> int:
    raw = task.get("task_revision", 1)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ValueError("task_revision_corrupt")
    return raw


def _next_task_revision(task: dict[str, object]) -> tuple[int, int]:
    current = _task_revision_value(task)
    next_revision = current + 1
    task["task_revision"] = next_revision
    return current, next_revision


def _result_recovery_reason_codes(result_problems: Sequence[str]) -> list[str]:
    mapped: list[str] = []
    for problem in result_problems:
        field = str(problem).split(":", 1)[-1]
        code = RESULT_BINDING_REASON_CODES.get(field)
        if code is not None and code not in mapped:
            mapped.append(code)
    return mapped or ["RESULT_BINDING_TASK_ID_MISMATCH"]


def _result_recovery_evidence_pointer(args: argparse.Namespace) -> tuple[str, str]:
    pointer = str(
        getattr(args, "evidence_pointer", None)
        or getattr(args, "evidence", None)
        or ""
    ).strip()
    if not pointer or len(pointer.encode("utf-8")) > 512 or any(
        character in pointer for character in "\x00\r\n"
    ):
        raise ValueError("result_recovery_evidence_pointer_required")
    lowered = pointer.casefold()
    if any(token in lowered for token in ("pending/", "/pending/", "private/", "/private/")):
        raise ValueError("result_recovery_privacy_gate_failed")
    return pointer, hashlib.sha256(pointer.encode("utf-8")).hexdigest()


def _result_recovery_ledgers(task: dict[str, object]) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    history = task.get("result_recovery_history")
    operations = task.get("result_recovery_operations")
    projections = task.get("result_recovery_projections")
    if history is None:
        history = []
        task["result_recovery_history"] = history
    if operations is None:
        operations = {}
        task["result_recovery_operations"] = operations
    if projections is None:
        projections = {}
        task["result_recovery_projections"] = projections
    if not isinstance(history, list) or not isinstance(operations, dict) or not isinstance(projections, dict):
        raise ValueError("result_recovery_ledger_corrupt")
    for item in history:
        if not isinstance(item, dict) or result_recovery_record_disposition(item) != "CURRENT_RECOVERY_HEAD":
            raise ValueError("result_recovery_legacy_read_only")
    return history, operations, projections


def _result_recovery_core_for_task(
    task: Mapping[str, object],
    *,
    quarantine_id: str = "",
    payload_sha256: str = "",
) -> dict[str, object]:
    records = task.get("quarantined_results")
    if not isinstance(records, list):
        raise ValueError("result_quarantine_not_found")
    matches: list[dict[str, object]] = []
    legacy_match = False
    for record in records:
        if not isinstance(record, dict):
            continue
        core = record.get("core")
        if not isinstance(core, dict):
            if record.get("schema") == "court.office.result_quarantine.v1" or record.get("core_schema") != "court.office.result_quarantine.v2":
                if (
                    (quarantine_id and str(record.get("quarantine_id") or "") == quarantine_id)
                    or (payload_sha256 and str(record.get("payload_sha256") or "") == payload_sha256)
                    or (not quarantine_id and not payload_sha256)
                ):
                    legacy_match = True
                continue
            raise ValueError("result_recovery_legacy_read_only")
        if result_recovery_record_disposition(core) != "CURRENT_QUARANTINE_CORE":
            if (
                not quarantine_id
                or str(core.get("quarantine_id") or "") == quarantine_id
            ):
                legacy_match = True
            continue
        if quarantine_id and str(core.get("quarantine_id")) != quarantine_id:
            continue
        if payload_sha256 and str(core.get("payload_sha256")) != payload_sha256:
            continue
        matches.append(core)
    if legacy_match:
        raise ValueError("result_recovery_legacy_read_only")
    if len(matches) != 1:
        raise ValueError("result_quarantine_not_found")
    return dict(matches[0])


def _recovery_head_for_task(
    task: Mapping[str, object],
    recovery_id: str,
) -> dict[str, object] | None:
    history = task.get("result_recovery_history")
    if history is None:
        return None
    if not isinstance(history, list):
        raise ValueError("result_recovery_ledger_corrupt")
    matches = [
        item for item in history
        if isinstance(item, dict) and str(item.get("recovery_id") or "") == recovery_id
    ]
    if not matches:
        return None
    head = matches[-1]
    return validate_result_recovery_head(head)


def _result_recovery_receipt_digest(receipt: Mapping[str, object]) -> str:
    return canonical_json_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )


def ensure_runtime_root() -> None:
    if not os.environ.get("COURT_RUNTIME_ROOT"):
        ensure_shared_seed()
    runtime_root().mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value).strip("-")
    return value[:64] or "court-task"


def _load_raw_tasks() -> dict[str, dict[str, Any]]:
    require_readable_ledgers(runtime_root())
    path = tasks_path()
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("tasks.json must contain an object")
    raw_tasks: dict[str, dict[str, Any]] = {}
    for key, item in value.items():
        task_id = str(key)
        if not isinstance(item, dict):
            raise ValueError(f"tasks.json entry '{task_id}' must contain an object")
        _runtime_schema_version(item)
        raw_tasks[task_id] = item
    return raw_tasks


def load_tasks() -> dict[str, dict[str, Any]]:
    return {task_id: normalize_task(task) for task_id, task in _load_raw_tasks().items()}


def _task_document(tasks: dict[str, dict[str, Any]]) -> str:
    raw_tasks = _load_raw_tasks()
    persisted_tasks: dict[str, dict[str, Any]] = {}
    for task_id, task in tasks.items():
        if not isinstance(task, dict):
            raise ValueError(f"task entry '{task_id}' must contain an object")
        _runtime_schema_version(task)
        incoming = deepcopy(task)
        raw_task = raw_tasks.get(task_id)
        if raw_task is not None:
            normalized_raw = normalize_task(raw_task)
            if raw_task != normalized_raw and incoming == normalized_raw:
                persisted_tasks[task_id] = raw_task
                continue
        persisted_tasks[task_id] = incoming
    return json.dumps(persisted_tasks, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_tasks(tasks: dict[str, dict[str, Any]]) -> None:
    ensure_runtime_root()
    atomic_write_text(tasks_path(), _task_document(tasks))


def _commit_task_event(tasks: dict[str, dict[str, Any]], event: dict[str, Any]) -> None:
    line = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
    with ledger_pair_write(runtime_root(), _task_document(tasks), line):
        write_tasks(tasks)
        append_event(event)


@contextmanager
def runtime_lock(timeout: float = 10.0, poll: float = 0.05, *, recover: bool = True):
    ensure_runtime_root()
    with file_lock(lock_path(), timeout=timeout, poll_interval=poll):
        if recover:
            recover_ledger_pair(runtime_root())
        else:
            require_readable_ledgers(runtime_root())
        yield


def append_event(event: dict[str, Any]) -> None:
    ensure_runtime_root()
    with events_path().open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _reverse_event_lines(handle):
    """Read complete UTF-8 lines backwards without loading the event history."""
    position = handle.seek(0, os.SEEK_END)
    remainder = b""
    while position:
        size = min(position, 64 * 1024)
        position -= size
        handle.seek(position)
        lines = (handle.read(size) + remainder).split(b"\n")
        remainder = lines[0]
        yield from reversed(lines[1:])
    if remainder:
        yield remainder


def read_events(limit: int | None = 50, task_id: str = "") -> list[dict[str, Any]]:
    require_readable_ledgers(runtime_root())
    path = events_path()
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        lines = handle if limit is None else _reverse_event_lines(handle)
        for line in lines:
            try:
                event = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or (task_id and str(event.get("task_id")) != task_id):
                continue
            events.append(event)
            if limit is not None and len(events) >= max(1, limit):
                break
    if limit is not None:
        events.reverse()
    return events


def events_for_task(
    task_id: object,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Read one task's persisted history without a global recent-window eviction."""

    return read_events(limit=limit, task_id=str(task_id or ""))


def legal_transition(from_state: str, to_state: str) -> bool:
    return to_state in TRANSITIONS.get(from_state, set())


def validate_runtime_gate(
    task: dict[str, Any],
    from_state: str,
    to_state: str,
    evidence: str,
    control_context: bool = False,
) -> None:
    if not legal_transition(from_state, to_state):
        raise ValueError(f"illegal transition: {from_state} -> {to_state}")
    if _runtime_schema_version(task) >= 3 and to_state == "Done":
        raise ValueError("atomic_completion_required")
    if to_state in CONTROL_STATES and not control_context:
        raise ValueError(f"use dedicated {to_state.lower()} command for auditable control transitions")
    if from_state == "Paused" and to_state != "Cancelled":
        paused_from = str(task.get("paused_from") or "")
        allowed_resume_states = TRANSITIONS.get(paused_from, set()) | {paused_from}
        if to_state not in allowed_resume_states:
            raise ValueError(f"illegal paused resume: {paused_from} paused, cannot resume to {to_state}")
    if _runtime_schema_version(task) >= 3 and to_state == "ShiguanRecorded":
        revalidated_binding = _revalidate_stored_assessment_binding(task)
        if revalidated_binding.get("gate") not in COMPLETABLE_OUTCOME_ASSESSMENT_GATES:
            raise ValueError("outcome_assessment_not_completable")
        checkpoint = task.get("shiguan_checkpoint")
        if not isinstance(checkpoint, dict) or checkpoint.get("status") != "VERIFIED":
            raise ValueError("shiguan_checkpoint_not_verified")


def read_only_decree(text: str) -> bool:
    return bool(READ_ONLY_RE.search(text or ""))


def classify_agent_error(text: str) -> str:
    value = (text or "").lower()
    if re.search(r"\b401\b|unauthori[sz]ed|未授权|认证失败", value):
        return "fatal-auth"
    if re.search(r"\b(?:402|403)\b", value) and re.search(
        r"quota|billing|account|credit|额度|余额|账户|付费", value
    ):
        return "fatal-quota"
    if re.search(r"thread limit|at capacity|\b429\b|rate.?limit|并发上限|容量不足", value):
        return "capacity"
    if re.search(r"\b403\b|forbidden", value):
        return "fatal-auth"
    if re.search(r"\b5\d\d\b|timeout|temporar|connection reset|超时|暂时", value):
        return "retryable"
    return "unknown"


def scrub_agent_provider_detail(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"(?i)https?://\S+", "[provider-url-omitted]", value)
    value = re.sub(
        r"(?i)request[\s_-]*id\s*[:=]\s*[a-z0-9._-]+",
        "request_id=[omitted]",
        value,
    )
    value = re.sub(
        r"(?i)(?:balance|remaining credit|余额|剩余额度)\s*[:=]?\s*[¥$€]?\s*-?\d+(?:\.\d+)?",
        "provider_balance=[omitted]",
        value,
    )
    value = re.sub(
        r"(?i)(api[_-]?key|authorization|bearer|cookie|token|secret|password)\s*[:=]\s*\S+",
        lambda match: f"{match.group(1)}=[redacted]",
        value,
    )
    return value


def task_serial_override(task: dict[str, Any], execution_topology: str = "auto") -> bool:
    if execution_topology == "serial":
        return True
    text = " ".join(str(task.get(key) or "") for key in ("title", "charter", "heartbeat"))
    return bool(SERIAL_OVERRIDE_RE.search(text))


def parse_requested_fork_turns(value: object) -> tuple[bool, str]:
    normalized = str(value or "none").strip().lower()
    if normalized in {"none", "all"}:
        return True, normalized
    if normalized.isdigit() and 1 <= int(normalized) <= AGENT_MAX_RECENT_FORK_TURNS:
        return True, normalized
    return False, normalized


def parse_requested_roles(value: object, fallback_count: int = 1) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        raw = [str(item) for item in value]
    else:
        raw = re.split(r"[,;]", str(value or ""))
    roles = tuple(item.strip().lower() for item in raw if item.strip())
    if roles:
        return roles
    return tuple(f"unspecified-{index + 1}" for index in range(max(1, fallback_count)))


def agent_dispatch_message_budget(
    raw_message_chars: object,
    raw_required_chars: object = None,
    raw_optional_chars: object = None,
) -> dict[str, object]:
    common: dict[str, object] = {
        "message_budget_schema": AGENT_MESSAGE_BUDGET_SCHEMA,
        "message_budget_policy": "bounded_quantized_growth_v1",
        "message_measurement": "unicode_code_points",
        "message_scope": "max_single_final_message_per_wave",
        "message_budget_floor_chars": AGENT_MESSAGE_BUDGET_FLOOR_CHARS,
        "message_budget_quantum_chars": AGENT_MESSAGE_BUDGET_QUANTUM_CHARS,
        "message_budget_ceiling_chars": AGENT_MESSAGE_BUDGET_CEILING_CHARS,
    }
    required_supplied = raw_required_chars is not None
    optional_supplied = raw_optional_chars is not None
    components_supplied = required_supplied or optional_supplied
    message_value = (
        raw_message_chars
        if isinstance(raw_message_chars, int) and not isinstance(raw_message_chars, bool)
        else None
    )
    required_value = (
        raw_required_chars
        if isinstance(raw_required_chars, int)
        and not isinstance(raw_required_chars, bool)
        and raw_required_chars >= 0
        else None
    )
    optional_value = (
        raw_optional_chars
        if isinstance(raw_optional_chars, int)
        and not isinstance(raw_optional_chars, bool)
        and raw_optional_chars >= 0
        else None
    )
    component_fields: dict[str, object] = {
        "message_required_chars": required_value,
        "message_optional_chars": optional_value,
        "message_component_status": "unspecified",
        "message_component_reason": "not_supplied",
        "optional_compression_target_chars": None,
        "required_message_overage_chars": None,
        "compression_possible_without_required_loss": None,
    }
    if raw_message_chars is None and not components_supplied:
        return {
            **common,
            **component_fields,
            "message_chars": None,
            "message_budget_effective_chars": AGENT_MESSAGE_BUDGET_FLOOR_CHARS,
            "message_budget_status": "legacy_unmeasured",
            "message_budget_basis": "legacy_floor_without_measurement",
            "message_budget_remaining_chars": None,
            "message_overage_chars": 0,
            "required_reduction_chars": 0,
            "message_budget_retryable": False,
            "compression_guidance": "measure the exact final dispatch message before new integrations",
        }
    total_valid = message_value is not None and message_value >= 0
    component_reason = "not_supplied"
    if components_supplied:
        if not required_supplied or not optional_supplied:
            component_reason = "component_missing"
        elif any(
            isinstance(value, int) and not isinstance(value, bool) and value < 0
            for value in (raw_required_chars, raw_optional_chars)
        ):
            component_reason = "component_negative"
        elif required_value is None or optional_value is None:
            component_reason = "component_invalid"
        elif total_valid and required_value + optional_value != message_value:
            component_reason = "component_sum_mismatch"
        else:
            component_reason = "measured"
    components_valid = not components_supplied or component_reason == "measured"
    component_fields["message_component_reason"] = component_reason
    if not total_valid or not components_valid:
        component_fields["message_component_status"] = "invalid" if components_supplied else "unspecified"
        if not total_valid:
            guidance = "report a non-negative Unicode code-point count, then re-admit with a new wave_id"
        elif component_reason == "component_missing":
            guidance = (
                "provide both message_required_chars and message_optional_chars, "
                "then re-admit with a new wave_id"
            )
        elif component_reason == "component_negative":
            guidance = "report non-negative component counts, then re-admit with a new wave_id"
        elif component_reason == "component_sum_mismatch":
            guidance = (
                "make message_required_chars + message_optional_chars equal message_chars, "
                "then re-admit with a new wave_id"
            )
        else:
            guidance = "report integer component counts, then re-admit with a new wave_id"
        return {
            **common,
            **component_fields,
            "message_chars": message_value,
            "message_budget_effective_chars": AGENT_MESSAGE_BUDGET_FLOOR_CHARS,
            "message_budget_status": "invalid",
            "message_budget_basis": "invalid_measurement",
            "message_budget_remaining_chars": None,
            "message_overage_chars": None,
            "required_reduction_chars": None,
            "message_budget_retryable": True,
            "compression_guidance": guidance,
        }
    if components_supplied:
        component_fields["message_component_status"] = "measured"
    rounded = (
        (message_value + AGENT_MESSAGE_BUDGET_QUANTUM_CHARS - 1)
        // AGENT_MESSAGE_BUDGET_QUANTUM_CHARS
        * AGENT_MESSAGE_BUDGET_QUANTUM_CHARS
    )
    effective = min(
        AGENT_MESSAGE_BUDGET_CEILING_CHARS,
        max(AGENT_MESSAGE_BUDGET_FLOOR_CHARS, rounded),
    )
    overage = max(0, message_value - effective)
    exceeded = overage > 0
    if components_supplied:
        optional_target = min(optional_value, overage)
        required_overage = max(0, overage - optional_value)
        component_fields.update(
            optional_compression_target_chars=optional_target,
            required_message_overage_chars=required_overage,
            compression_possible_without_required_loss=required_overage == 0,
        )
    if not exceeded:
        guidance = "none"
    elif components_supplied and component_fields["compression_possible_without_required_loss"]:
        guidance = (
            f"remove at least {overage} optional characters, then re-admit with a new wave_id"
        )
    elif components_supplied:
        guidance = (
            "required context exceeds the ceiling; split without truncating required fields, "
            "then re-admit with a new wave_id"
        )
    else:
        guidance = "compress optional context or split the dispatch, then re-admit with a new wave_id"
    return {
        **common,
        **component_fields,
        "message_chars": message_value,
        "message_budget_effective_chars": effective,
        "message_budget_status": "exceeded" if exceeded else "within_budget",
        "message_budget_basis": "measured_quantized_and_hard_capped",
        "message_budget_remaining_chars": max(0, effective - message_value),
        "message_overage_chars": overage,
        "required_reduction_chars": overage,
        "message_budget_retryable": exceeded,
        "compression_guidance": guidance,
    }


def _optional_json_object(text: object, label: str) -> dict[str, object] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return dict(value)


def _optional_json_array(text: object, label: str) -> list[dict[str, object]] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be a JSON array of objects")
    return [dict(item) for item in value]


def _required_context_object(value: object, error_code: str) -> dict[str, object]:
    if isinstance(value, Mapping):
        return deepcopy(dict(value))
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(error_code) from exc
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(error_code)


def _tupleize_json_sequences(value: object) -> object:
    if isinstance(value, list):
        return tuple(_tupleize_json_sequences(item) for item in value)
    if isinstance(value, Mapping):
        return {
            str(key): _tupleize_json_sequences(item)
            for key, item in value.items()
        }
    return value


def _context_contract_required(args: argparse.Namespace) -> bool:
    if any(
        bool(getattr(args, field, False))
        for field in (
            "_context_contract_required",
            "_production_cli",
            "_office_lifecycle_explicit",
        )
    ):
        return True
    for field in (
        "dispatch_context_packet",
        "context_budget_pool",
        "context_result_mode",
        "context_tool_output_mode",
        "context_override_source",
    ):
        value = getattr(args, field, None)
        if value is not None and value != "":
            return True
    return False


def _context_budget_pool_for_evaluation(
    value: object,
    *,
    task_id: str,
    wave_id: str,
) -> tuple[dict[str, object], Mapping[str, object]]:
    pool = _required_context_object(value, "context_budget_pool_required")
    normalized = _tupleize_json_sequences(pool)
    if not isinstance(normalized, Mapping):
        raise ValueError("context_budget_pool_required")
    root_id = normalized.get("root_id")
    leases = normalized.get("leases")
    root = leases.get(root_id) if isinstance(leases, Mapping) else None
    if not isinstance(root, Mapping):
        raise ValueError("context_budget_pool_scope_mismatch")
    if root.get("task_id") != task_id:
        raise ValueError("context_budget_pool_task_mismatch")
    if root.get("wave_id") != wave_id:
        raise ValueError("context_budget_pool_wave_mismatch")
    if root.get("budget_id") != normalized.get("budget_id"):
        raise ValueError("context_budget_pool_id_mismatch")
    if root.get("status") != "ACTIVE":
        raise ValueError("context_budget_pool_not_active")
    return pool, normalized


def _validate_context_economy_request(
    task: dict[str, Any],
    args: argparse.Namespace,
    *,
    wave_id: str,
) -> dict[str, object]:
    receipt = task.get("semantic_receipt")
    if not isinstance(receipt, dict):
        raise ValueError("dispatch_context_current_receipt_required")
    packet_value = _required_context_object(
        getattr(args, "dispatch_context_packet", None),
        "dispatch_context_packet_required",
    )
    validated = validate_dispatch_context_packet(task, receipt, packet_value)
    packet = validated["packet"]
    if not isinstance(packet, dict):
        raise ValueError("dispatch_context_packet_required")
    pool, evaluation_pool = _context_budget_pool_for_evaluation(
        getattr(args, "context_budget_pool", None),
        task_id=str(task.get("task_id") or ""),
        wave_id=wave_id,
    )
    result_mode = str(getattr(args, "context_result_mode", "") or "").strip()
    tool_output_mode = str(
        getattr(args, "context_tool_output_mode", "") or ""
    ).strip()
    override_source = str(
        getattr(args, "context_override_source", "") or ""
    ).strip() or None
    if packet.get("context_mode") == "full":
        if override_source not in CONTEXT_ECONOMY_EXPLICIT_OVERRIDE_SOURCES:
            raise ValueError("implicit_full_context_forbidden")
        budget_override = packet.get("budget_override")
        if not isinstance(budget_override, dict):
            raise ValueError("dispatch_context_full_requires_explicit_budget_override")
        granted_by = budget_override.get("granted_by")
        if (
            granted_by == "user"
            and override_source not in {"latest_user_explicit", "current_user_explicit"}
        ) or (
            granted_by == "taizi" and override_source != "taizi_explicit_budget"
        ):
            raise ValueError("context_economy_override_authority_mismatch")
    if override_source is None:
        if result_mode != "bounded_structured_receipt":
            raise ValueError("bounded_structured_receipt_required")
        if tool_output_mode not in {"aggregate", "pointer"}:
            raise ValueError("aggregate_or_pointer_tool_output_required")
    system_memory_percent = float(
        getattr(args, "system_memory_percent", 0.0) or 0.0
    )
    economy_receipt = evaluate_context_economy(
        pool=evaluation_pool,
        semantic_receipt_id=str(receipt.get("receipt_id") or ""),
        case_ref=case_reference(task),
        capsule_bytes=int(validated["packet_bytes"]),
        fork_context=str(packet.get("fork_context") or ""),
        result_mode=result_mode,
        tool_output_mode=tool_output_mode,
        override_source=override_source,
        system_memory_percent=system_memory_percent,
    )
    binding = {
        "dispatch_context_packet_ref": f"context://{task.get('task_id')}/{wave_id}",
        "dispatch_context_packet_bytes": validated["packet_bytes"],
        "semantic_receipt_id": receipt.get("receipt_id"),
        "context_budget_pool_ref": deepcopy(pool),
        "context_budget_id": economy_receipt["budget_id"],
        "context_economy_receipt_ref": deepcopy(economy_receipt),
        "context_economy_decision": economy_receipt["decision"],
        "context_fork_mode": packet.get("fork_context"),
        "context_mode": packet.get("context_mode"),
        "context_result_mode": result_mode,
        "context_tool_output_mode": tool_output_mode,
        "context_override_source": override_source,
        "context_system_memory_percent": system_memory_percent,
    }
    return {
        **binding,
        "context_economy_receipt": economy_receipt,
    }


def _revalidate_context_economy_start(
    task: dict[str, Any],
    admission: dict[str, Any],
    binding: dict[str, object],
    args: argparse.Namespace,
    *,
    wave_id: str,
) -> dict[str, object] | None:
    has_contract = any(
        admission.get(field) is not None for field in CONTEXT_ECONOMY_BINDING_FIELDS
    )
    if not has_contract:
        if _context_contract_required(args):
            raise ValueError("context_economy_admission_binding_missing")
        return None
    revalidated = _validate_context_economy_request(task, args, wave_id=wave_id)
    _canonical_json = lambda value: json.dumps(  # noqa: E731
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    for field in CONTEXT_ECONOMY_BINDING_FIELDS:
        expected = revalidated.get(field)
        if (
            _canonical_json(admission.get(field)) != _canonical_json(expected)
            or _canonical_json(binding.get(field)) != _canonical_json(expected)
        ):
            mismatch_codes = {
                "dispatch_context_packet_ref": "dispatch_context_packet_ref_mismatch",
                "semantic_receipt_id": "semantic_receipt_id_mismatch",
                "context_budget_pool_ref": "context_budget_pool_ref_mismatch",
                "context_economy_receipt_ref": "context_economy_receipt_ref_mismatch",
            }
            raise ValueError(
                mismatch_codes.get(
                    field,
                    f"context_economy_binding_mismatch:{field}",
                )
            )
    return revalidated


_HIERARCHY_FORMAL_ROLES = frozenset(
    {
        "taizi",
        "zhongshu",
        "menxia",
        "shangshu",
        "libu-hr",
        "hubu",
        "libu",
        "bingbu",
        "xingbu",
        "gongbu",
        "shiguan",
        "shiguan-hermes",
        "zaochao",
        "patrol-inspector",
    }
)
_HIERARCHY_EVIDENCE_FIELDS = (
    "hierarchy_gate",
    "hierarchy_schema",
    "hierarchy_manifest_path",
    "hierarchy_edge_class",
    "hierarchy_calling_office",
    "hierarchy_target_role",
    "hierarchy_owner_role",
)


def _dispatch_hierarchy_evidence(
    calling_office: object,
    binding: Mapping[str, object],
) -> dict[str, object] | None:
    role = str(binding.get("role") or "").strip().lower()
    canonical_authority = binding.get("canonical_authority")
    child_profile = binding.get("child_profile")
    if not (
        (role in _HIERARCHY_FORMAL_ROLES and canonical_authority is True)
        or child_profile is not None
    ):
        return None
    decision = validate_dispatch_hierarchy(
        action="dispatch",
        calling_office=calling_office,
        target_role=binding.get("role"),
        target_direct_superior=binding.get("direct_superior"),
        instance_kind=(
            binding.get("instance_kind") or binding.get("office_instance_kind")
        ),
        canonical_authority=canonical_authority,
        owner_role=binding.get("owner_role"),
        child_profile=child_profile,
    )
    if not decision.allowed:
        raise ValueError(
            decision.reason_codes[0]
            if decision.reason_codes
            else "dispatch_hierarchy_edge_forbidden"
        )
    return {
        "hierarchy_gate": "PASSED",
        "hierarchy_schema": decision.hierarchy_schema,
        "hierarchy_manifest_path": decision.hierarchy_manifest_path,
        "hierarchy_edge_class": decision.edge_class,
        "hierarchy_calling_office": decision.normalized_caller,
        "hierarchy_target_role": decision.normalized_target,
        "hierarchy_owner_role": decision.normalized_owner,
    }


def _execution_budgets(values: Mapping[str, object]) -> dict[str, int | None]:
    budgets = {}
    for field, default in AGENT_EXECUTION_BUDGET_DEFAULTS.items():
        value = values.get(field, default)
        if value is not None and (type(value) is not int or value < 1):
            raise ValueError(f"admission_{field}_must_be_positive_integer")
        budgets[field] = value
    return budgets


def evaluate_agent_admission(task: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    execution_budgets = _execution_budgets(vars(args))
    dispatch_requested_at = now_text()
    wave_id = str(getattr(args, "wave_id", "") or "wave-default")
    context_tokens = max(0, int(getattr(args, "context_tokens", 0) or 0))
    requested_agents_compat = max(1, int(getattr(args, "requested_agents", 1) or 1))
    requested_roles = parse_requested_roles(getattr(args, "requested_roles", ""), requested_agents_compat)
    requested_agents = len(requested_roles)
    host_active_raw = getattr(args, "host_active_agents", None)
    host_capacity_raw = getattr(args, "host_capacity", None)
    host_retained_raw = getattr(args, "host_retained_agents", None)
    reclamation_status = str(getattr(args, "host_reclamation_status", "unknown") or "unknown").strip().lower()
    next_depth_raw = getattr(args, "next_depth", None)
    host_active = int(host_active_raw) if host_active_raw is not None else None
    host_capacity = int(host_capacity_raw) if host_capacity_raw is not None else None
    host_retained = int(host_retained_raw) if host_retained_raw is not None else None
    reclamation_verified = {
        "verified": True,
        "not-reclaimed": False,
        "unknown": None,
    }.get(reclamation_status)
    next_depth = int(next_depth_raw) if next_depth_raw is not None else None
    configured_max_threads = int(
        getattr(args, "max_threads", MAX_AGENT_TREE_THREADS) or MAX_AGENT_TREE_THREADS
    )
    configured_max_depth = min(
        MAX_AGENT_TREE_DEPTH,
        int(getattr(args, "max_depth", MAX_AGENT_TREE_DEPTH) or MAX_AGENT_TREE_DEPTH),
    )
    user_agent_budget = getattr(args, "user_agent_budget", None)
    provider_launch_budget = getattr(args, "provider_launch_budget", None)
    budget_lease = _optional_json_object(
        getattr(args, "budget_lease_json", ""), "budget-lease-json"
    )
    requested_bindings = _optional_json_array(
        getattr(args, "requested_bindings_json", ""), "requested-bindings-json"
    )
    integration_domain = str(getattr(args, "integration_domain", "") or "").strip()
    authority = str(getattr(args, "authority", "") or "").strip().lower()
    calling_office = str(getattr(args, "calling_office", "") or "").strip().lower()
    direct_superior = str(getattr(args, "direct_superior", "") or "").strip().lower()
    message_budget = agent_dispatch_message_budget(
        getattr(args, "message_chars", None),
        getattr(args, "message_required_chars", None),
        getattr(args, "message_optional_chars", None),
    )
    valid_fork, requested_fork = parse_requested_fork_turns(
        getattr(args, "requested_fork_turns", "none")
    )
    task_agents = task.get("agents", {})
    if not isinstance(task_agents, dict):
        task_agents = {}
    ledger_active = sum(
        1
        for agent in task_agents.values()
        if isinstance(agent, dict) and str(agent.get("status") or "") not in TERMINAL_AGENT_STATUSES
    )
    effective_active = max(1, host_active, ledger_active) if host_active is not None and host_active >= 0 else None
    wave = select_wave(
        requested_roles,
        host_capacity,
        effective_active,
        user_agent_budget,
        provider_launch_budget,
        host_retained=host_retained,
        host_reclamation_verified=reclamation_verified,
        next_depth=next_depth,
        max_threads=configured_max_threads,
        max_depth=configured_max_depth,
        explicit_parallel_count=getattr(args, "explicit_parallel_count", None),
        parallel_unlimited=bool(getattr(args, "parallel_unlimited", False)),
        parallel_control_source=str(
            getattr(args, "parallel_control_source", "") or ""
        ).strip()
        or None,
        system_memory_percent=float(getattr(args, "system_memory_percent", 0.0) or 0.0),
        budget_lease=budget_lease,
        task_id=str(task.get("task_id") or ""),
        calling_office=calling_office,
        direct_superior=direct_superior,
        requested_bindings=requested_bindings,
        integration_domain=integration_domain,
        authority=authority,
    )
    selected_bindings = tuple(
        dict(requested_bindings[index])
        for index in wave.selected_indices
        if requested_bindings is not None and 0 <= index < len(requested_bindings)
    )
    hierarchy_receipts: list[dict[str, object]] = []
    hierarchy_bound_bindings: list[dict[str, object]] = []
    for selected_binding in selected_bindings:
        hierarchy_evidence = _dispatch_hierarchy_evidence(
            calling_office,
            selected_binding,
        )
        bound_binding = dict(selected_binding)
        if hierarchy_evidence is not None:
            bound_binding.update(hierarchy_evidence)
            hierarchy_receipts.append(hierarchy_evidence)
        hierarchy_bound_bindings.append(bound_binding)
    selected_bindings = tuple(hierarchy_bound_bindings)
    selected_instance_ids = tuple(
        str(binding.get("instance_id") or "").strip().lower()
        for binding in selected_bindings
    )
    result: dict[str, Any] = {
        "kind": "court_agent_admission",
        "dispatch_requested_at": dispatch_requested_at,
        "task_id": task.get("task_id"),
        "wave_id": wave_id,
        "allowed": True,
        "decision": "admitted",
        "parallel_dispatch": "USED/admitted",
        "requested_fork_turns": requested_fork,
        "recommended_fork_turns": "none",
        "context_tokens": context_tokens,
        "long_context_threshold": AGENT_LONG_CONTEXT_TOKENS,
        "wave_policy": "dynamic_by_duty_and_capacity",
        "static_wave_cap": None,
        "ordinary_wave_cap": None,
        "requested_roles": requested_roles,
        "useful_roles": requested_roles,
        "selected_roles": wave.selected_roles,
        "selected_bindings": selected_bindings,
        "selected_instance_ids": selected_instance_ids,
        "deferred_roles": wave.deferred_roles,
        "selection_basis": wave.reason,
        "host_active_agents": host_active,
        "host_capacity": host_capacity,
        "host_retained_agents": host_retained,
        "host_reclamation_status": reclamation_status,
        "host_reclamation_verified": reclamation_verified,
        "effective_host_capacity": wave.effective_host_capacity,
        "configured_max_threads": wave.max_threads,
        "configured_max_depth": wave.max_depth,
        "ledger_active_agents": ledger_active,
        "effective_active_agents": effective_active,
        "global_live_active_threads": effective_active,
        "available_slots": wave.available_slots,
        "next_depth": next_depth,
        "max_depth": wave.max_depth,
        "max_threads": wave.max_threads,
        "explicit_parallel_count": getattr(args, "explicit_parallel_count", None),
        "parallel_unlimited": bool(getattr(args, "parallel_unlimited", False)),
        "parallel_control_source": str(
            getattr(args, "parallel_control_source", "") or ""
        ).strip(),
        "system_memory_percent": float(getattr(args, "system_memory_percent", 0.0) or 0.0),
        "root_thread_counts_toward_limit": True,
        "user_agent_budget": user_agent_budget,
        "provider_launch_budget": provider_launch_budget,
        "budget_lease": budget_lease,
        "budget_lease_id": str((budget_lease or {}).get("lease_id") or ""),
        "requested_bindings": requested_bindings,
        "integration_domain": integration_domain,
        "authority": authority,
        "calling_office": calling_office,
        "direct_superior": direct_superior,
        "requested_agents": requested_agents,
        "hierarchy_receipts": tuple(hierarchy_receipts),
        **execution_budgets,
        "reuse_errored_agents": False,
        **message_budget,
    }
    if len(hierarchy_receipts) == 1:
        result.update(hierarchy_receipts[0])

    def deny(decision: str, dispatch: str = "runtime_degraded") -> dict[str, Any]:
        result.update(
            allowed=False,
            decision=decision,
            parallel_dispatch=dispatch,
            selected_roles=(),
            selected_bindings=(),
            selected_instance_ids=(),
            deferred_roles=requested_roles,
            selection_basis=decision,
        )
        return result

    topology = str(getattr(args, "execution_topology", "auto") or "auto").lower()
    serial_override = task_serial_override(task, topology)
    protocol_requirements = ProtocolRequirements(
        child_agents_required=bool(requested_roles) and not serial_override,
        needs_parallel_tree=bool(
            not serial_override and getattr(args, "needs_parallel_tree", False)
        ),
        needs_fork_turns=bool(getattr(args, "needs_fork_turns", False)),
        needs_cross_branch_messages=bool(getattr(args, "needs_cross_branch_messages", False)),
        needs_agent_type_override=bool(getattr(args, "needs_agent_type_override", False)),
        needs_model_override=bool(getattr(args, "needs_model_override", False)),
        needs_reasoning_effort_override=bool(getattr(args, "needs_reasoning_effort_override", False)),
        active_session_protocol=getattr(args, "active_session_protocol", None),
    )
    protocol_decision = select_protocol(
        "serial" if serial_override else str(getattr(args, "protocol_mode", "auto") or "auto").lower(),
        protocol_requirements,
    )
    result["protocol_decision"] = asdict(protocol_decision)
    result["selected_protocol"] = protocol_decision.selected_mode
    if serial_override:
        return deny("user_serial_override", "NOT_APPLICABLE/user_serial_override")
    if protocol_decision.conflict:
        return deny("protocol_capability_conflict")
    if protocol_decision.selected_mode == "serial":
        return deny("protocol_serial", "NOT_APPLICABLE/protocol_serial")
    circuit = task.get("agent_circuit_breaker")
    if isinstance(circuit, dict) and circuit.get("state") == "open":
        result["circuit_breaker"] = dict(circuit)
        return deny("fatal_provider_circuit_open")
    wave_blocks = task.get("agent_wave_blocks")
    if isinstance(wave_blocks, dict) and wave_id in wave_blocks:
        result["wave_block"] = dict(wave_blocks[wave_id])
        return deny("capacity_wave_blocked")
    if not valid_fork or requested_fork == "all":
        return deny("unbounded_context_fork")
    if context_tokens >= AGENT_LONG_CONTEXT_TOKENS and requested_fork != "none":
        return deny("long_context_requires_no_fork")
    if result["message_budget_status"] == "invalid":
        return deny("invalid_dispatch_message_size")
    if result["message_budget_status"] == "exceeded":
        return deny("dispatch_message_too_large")
    invalid_roles = [role for role in requested_roles if not role.startswith("unspecified-") and role not in OFFICES]
    if invalid_roles:
        result["invalid_roles"] = invalid_roles
        return deny("invalid_requested_role")
    if not wave.selected_roles:
        return deny(wave.reason if wave.reason.endswith(("unknown", "invalid", "exceeded")) else f"{wave.reason}_exhausted")
    return result


AGENT_SEMANTIC_ARG_FIELDS = (
    "semantic_epoch",
    "case_ref",
    "checkpoint_id",
    "dispatch_uid",
    "attempt",
)


def _canonical_office_instance_kind(value: object) -> str:
    kind = str(value or "child_agent").strip().lower()
    if kind not in OFFICE_INSTANCE_KINDS:
        raise ValueError("unsupported_office_instance_kind")
    return kind


def _require_role_prefixed(value: object, role: str, field: str) -> str:
    text = str(value or "").strip().lower()
    # Admission templates issue stable office slots (role#NNNN). These are
    # distinct from native carrier agent IDs, which retain the role-... form.
    if (field == "office_instance_id"
            and re.fullmatch(re.escape(role.lower()) + r"#[0-9]{4}", text)
            and text.rsplit("#", 1)[1] != "0000"):
        return text
    if not text.startswith(f"{role.lower()}-") or not re.fullmatch(
        r"[a-z][a-z0-9-]*(?:-[a-z0-9]+)+",
        text,
    ):
        raise ValueError(f"{field}_not_role_prefixed")
    return text


def _portable_host_path_key(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").casefold()


def _git_read_only_output(
    worktree: Path,
    args: tuple[str, ...],
    *,
    error_code: str = "worktree_git_proof_failed",
) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(worktree), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(error_code) from exc
    if completed.returncode != 0 or not completed.stdout.strip():
        raise ValueError(error_code)
    return completed.stdout.strip()


def _actual_git_worktree_proof(path: Path, thread_id: str) -> dict[str, object]:
    top = Path(
        _git_read_only_output(path, WORKTREE_GIT_READ_ONLY_COMMANDS[0])
    ).resolve()
    if _portable_host_path_key(top) != _portable_host_path_key(path):
        raise ValueError("worktree_top_level_mismatch")
    git_dir = Path(
        _git_read_only_output(path, WORKTREE_GIT_READ_ONLY_COMMANDS[1])
    ).resolve()
    common_dir = Path(
        _git_read_only_output(path, WORKTREE_GIT_READ_ONLY_COMMANDS[2])
    ).resolve()
    if (
        _git_read_only_output(path, WORKTREE_GIT_READ_ONLY_COMMANDS[3]).lower()
        != "false"
    ):
        raise ValueError("worktree_repository_bare")
    if common_dir.name.casefold() != ".git":
        raise ValueError("worktree_repo_identity_unavailable")
    repo_id = common_dir.parent.name.casefold()
    git_dir_key = _portable_host_path_key(git_dir)
    common_dir_key = _portable_host_path_key(common_dir)
    if git_dir_key == common_dir_key:
        worktree_token = "main"
    else:
        common_worktrees_key = f"{common_dir_key}/worktrees/"
        if not git_dir_key.startswith(common_worktrees_key):
            raise ValueError("worktree_git_dir_mismatch")
        worktree_token = git_dir.name.casefold()
    branch = _git_read_only_output(
        path,
        WORKTREE_GIT_READ_ONLY_COMMANDS[4],
        error_code="worktree_branch_unavailable",
    )
    start_head = _git_read_only_output(
        path,
        WORKTREE_GIT_READ_ONLY_COMMANDS[5],
    ).lower()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", start_head):
        raise ValueError("worktree_start_head_invalid")
    normalized: dict[str, object] = {
        "thread_id": thread_id,
        "canonical_worktree_id": f"{repo_id}:{worktree_token}",
        "canonical_worktree_path": str(top),
        "repo_id": repo_id,
        "common_dir_fingerprint": hashlib.sha256(
            common_dir_key.encode("utf-8")
        ).hexdigest(),
        "branch": branch,
        "start_head": start_head,
    }
    normalized["worktree_fingerprint"] = canonical_json_sha256(normalized)
    return normalized


def _normalize_carrier_proof(
    kind: str,
    value: object,
    *,
    role: str,
    office_instance_id: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("office_carrier_proof_required")
    proof = dict(value)
    if kind == "child_agent":
        if set(proof) != {"agent_id"}:
            raise ValueError("child_agent_proof_fields_invalid")
        proof["agent_id"] = _require_role_prefixed(proof.get("agent_id"), role, "agent_id")
        return proof
    if set(proof) != set(WORKTREE_PROOF_FIELDS):
        raise ValueError("worktree_proof_fields_invalid")
    thread_id = str(proof.get("thread_id") or "").strip().lower()
    try:
        canonical_thread_id = str(uuid.UUID(thread_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("worktree_thread_id_invalid") from exc
    if canonical_thread_id != thread_id:
        raise ValueError("worktree_thread_id_invalid")
    path_text = str(proof.get("canonical_worktree_path") or "").strip()
    path = Path(path_text)
    if (
        not path.is_absolute()
        or not path.is_dir()
        or str(path.resolve()) != path_text
    ):
        raise ValueError("worktree_path_not_canonical")
    actual = _actual_git_worktree_proof(path, canonical_thread_id)
    provided = {
        "thread_id": canonical_thread_id,
        "canonical_worktree_id": require_text(
            proof.get("canonical_worktree_id"),
            "canonical_worktree_id",
        ).casefold(),
        "canonical_worktree_path": path_text,
        "repo_id": require_text(proof.get("repo_id"), "repo_id").casefold(),
        "common_dir_fingerprint": str(
            proof.get("common_dir_fingerprint") or ""
        ).strip().lower(),
        "branch": require_text(proof.get("branch"), "branch"),
        "start_head": str(proof.get("start_head") or "").strip().lower(),
        "worktree_fingerprint": str(
            proof.get("worktree_fingerprint") or ""
        ).strip().lower(),
    }
    mismatch_codes = {
        "canonical_worktree_id": "worktree_id_mismatch",
        "canonical_worktree_path": "worktree_path_mismatch",
        "repo_id": "worktree_repo_id_mismatch",
        "common_dir_fingerprint": "worktree_common_dir_fingerprint_mismatch",
        "branch": "worktree_branch_mismatch",
        "start_head": "worktree_start_head_mismatch",
        "worktree_fingerprint": "worktree_fingerprint_mismatch",
    }
    for field, error_code in mismatch_codes.items():
        if provided[field] != actual[field]:
            raise ValueError(error_code)
    if not re.fullmatch(r"[0-9a-f]{64}", str(actual["common_dir_fingerprint"])):
        raise ValueError("worktree_common_dir_fingerprint_invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(actual["worktree_fingerprint"])):
        raise ValueError("worktree_fingerprint_mismatch")
    return {field: actual[field] for field in WORKTREE_PROOF_FIELDS}


def _office_metadata_pointer(
    task_id: object,
    office_instance_id: str,
    kind: str,
    carrier_proof: dict[str, object],
) -> str:
    if kind != "worktree_thread":
        return ""
    digest = canonical_json_sha256(
        {
            "task_id": task_id,
            "office_instance_id": office_instance_id,
            "carrier_proof": carrier_proof,
        }
    )
    return f"shiguan-metadata://worktree/{task_id}/{office_instance_id}/{digest[:16]}"


def _prepare_explicit_office_admission(args: argparse.Namespace) -> None:
    kind = _canonical_office_instance_kind(getattr(args, "office_instance_kind", None))
    if not isinstance(getattr(args, "requested_roles", None), str):
        raise ValueError("office_admit_requires_single_role_text_and_explicit_instance_binding")
    role = require_text(getattr(args, "requested_roles", ""), "requested-roles").strip().lower()
    if "," in role:
        raise ValueError("office_admit_requires_single_instance")
    instance_id = _require_role_prefixed(
        getattr(args, "office_instance_id", ""),
        role,
        "office_instance_id",
    )
    task_name = require_text(
        getattr(args, "collaboration_task_name", ""),
        "collaboration-task-name",
    )
    task_prefix = role.replace("-", "_")
    if not re.fullmatch(rf"{re.escape(task_prefix)}_[a-z0-9]+(?:_[a-z0-9]+)*", task_name):
        raise ValueError("office_task_name_mismatch")
    carrier_proof = _normalize_carrier_proof(
        kind,
        getattr(args, "carrier_proof", None),
        role=role,
        office_instance_id=instance_id,
    )
    bindings = _optional_json_array(
        getattr(args, "requested_bindings_json", ""),
        "requested-bindings-json",
    )
    if not isinstance(bindings, list) or len(bindings) != 1:
        raise ValueError("office_admit_requires_single_instance")
    binding = dict(bindings[0])
    if str(binding.get("role") or "").strip().lower() != role:
        raise ValueError("office_admit_role_mismatch")
    if str(binding.get("instance_id") or "").strip().lower() != instance_id:
        raise ValueError("office_admit_instance_mismatch")
    binding.update(
        office_instance_kind=kind,
        office_instance_id=instance_id,
        collaboration_task_name=task_name,
        carrier_proof=carrier_proof,
        metadata_record_pointer=_office_metadata_pointer(
            getattr(args, "task_id", ""),
            instance_id,
            kind,
            carrier_proof,
        ),
    )
    if kind == "worktree_thread":
        binding["worktree"] = carrier_proof["canonical_worktree_path"]
    args.requested_bindings_json = json.dumps([binding], ensure_ascii=False)
    args._office_lifecycle_explicit = True


def _task_frozen_lineage(task: dict[str, Any]) -> dict[str, object]:
    parts = task.get("lineage_parts")
    lineage = {
        "decree_id": task.get("decree_id"),
        "main_court_code": task.get("main_court_code"),
        "parent_court_code": task.get("main_court_code"),
        "lineage_parts": deepcopy(parts),
        "lineage_key": task.get("lineage_key"),
        "lineage_version": task.get("lineage_version"),
    }
    if (
        not all(lineage.get(field) for field in ("decree_id", "main_court_code", "lineage_key"))
        or not isinstance(parts, list)
        or not parts
        or lineage.get("lineage_version") != 1
    ):
        raise ValueError("office_frozen_lineage_missing")
    return lineage


def _existing_office_instance_ids(task: dict[str, Any]) -> set[str]:
    instance_ids: set[str] = set()
    agents = task.get("agents")
    if isinstance(agents, dict):
        for record in agents.values():
            if isinstance(record, dict) and record.get("office_instance_id"):
                instance_ids.add(str(record["office_instance_id"]).lower())
    admissions = task.get("agent_admissions")
    if isinstance(admissions, dict):
        for admission in admissions.values():
            if not isinstance(admission, dict):
                continue
            for binding in admission.get("selected_bindings") or ():
                if isinstance(binding, dict) and binding.get("office_instance_id"):
                    instance_ids.add(str(binding["office_instance_id"]).lower())
    return instance_ids


def _active_office_write_claims(task: dict[str, Any]) -> set[str]:
    claims: set[str] = set()
    agents = task.get("agents")
    agent_records = agents if isinstance(agents, dict) else {}
    for record in agent_records.values():
        if not isinstance(record, dict):
            continue
        if str(record.get("status") or "") in TERMINAL_AGENT_STATUSES:
            continue
        if str(record.get("result_state") or "") == "QUARANTINED":
            continue
        write_set = record.get("write_set")
        if isinstance(write_set, list):
            normalized = canonical_repo_relative_paths(write_set, allow_empty=True)
            if normalized is None:
                raise ValueError("office_active_write_scope_invalid")
            claims.update(normalized)
    admissions = task.get("agent_admissions")
    if not isinstance(admissions, dict):
        return claims
    receipt = task.get("semantic_receipt")
    checkpoint_id = receipt.get("checkpoint_id") if isinstance(receipt, dict) else None
    for admission in admissions.values():
        if not isinstance(admission, dict) or admission.get("allowed") is not True:
            continue
        if str(admission.get("status") or "").upper().startswith("INVALIDATED"):
            continue
        if (checkpoint_id and admission.get("checkpoint_id")
                and admission["checkpoint_id"] != checkpoint_id):
            # Stale reservations cannot start; live writers were counted above.
            continue
        consumed = admission.get("consumed_instances")
        consumed_map = consumed if isinstance(consumed, dict) else {}
        failed = admission.get("failed_instances")
        for binding in admission.get("selected_bindings") or ():
            if not isinstance(binding, dict):
                continue
            instance_id = str(binding.get("instance_id") or "")
            if isinstance(failed, dict) and instance_id in failed:
                continue
            agent_id = consumed_map.get(instance_id)
            if agent_id:
                record = agent_records.get(str(agent_id))
                if isinstance(record, dict) and (
                    str(record.get("status") or "") in TERMINAL_AGENT_STATUSES
                    or str(record.get("result_state") or "") == "QUARANTINED"
                ):
                    continue
            write_set = binding.get("write_set")
            if isinstance(write_set, list):
                normalized = canonical_repo_relative_paths(write_set, allow_empty=True)
                if normalized is None:
                    raise ValueError("office_active_write_scope_invalid")
                claims.update(normalized)
    return claims


def _allocate_office_binding(
    task: dict[str, Any],
    binding: dict[str, object],
    *,
    require_lineage: bool,
    reserved_write_claims: set[str] | None = None,
) -> dict[str, object]:
    enriched = dict(binding)
    access_mode = str(enriched.get("access_mode") or "read_write").strip().lower()
    write_set = canonical_repo_relative_paths(
        enriched.get("write_set"),
        allow_empty=access_mode == "read_only",
    )
    if write_set is None:
        raise ValueError("office_write_set_invalid")
    read_scope_value = enriched.get("read_scope")
    read_scope = (
        write_set
        if access_mode == "read_write" and read_scope_value is None
        else canonical_repo_relative_paths(read_scope_value)
    )
    if read_scope is None:
        raise ValueError("office_read_scope_invalid")
    enriched["write_set"] = list(write_set)
    enriched["read_scope"] = list(read_scope)
    kind = _canonical_office_instance_kind(enriched.get("office_instance_kind"))
    enriched["office_instance_kind"] = kind
    instance_id = str(
        enriched.get("office_instance_id") or enriched.get("instance_id") or ""
    ).strip().lower()
    enriched["office_instance_id"] = instance_id
    requested_claims = set(write_set)
    active_claims = _active_office_write_claims(task)
    if reserved_write_claims:
        active_claims.update(reserved_write_claims)
    if any(
        repository_paths_overlap(requested, active)
        for requested in requested_claims
        for active in active_claims
    ):
        raise ValueError("office_writer_conflict")
    if reserved_write_claims is not None:
        reserved_write_claims.update(requested_claims)
    if require_lineage:
        if instance_id in _existing_office_instance_ids(task):
            raise ValueError("office_instance_already_admitted")
        lineage = _task_frozen_lineage(task)
        try:
            child_no = int(task.get("next_office_child_no") or 1)
        except (TypeError, ValueError) as exc:
            raise ValueError("office_child_sequence_corrupt") from exc
        if child_no < 1:
            raise ValueError("office_child_sequence_corrupt")
        task["next_office_child_no"] = child_no + 1
        enriched.update(lineage, child_no=child_no)
        proof = enriched.get("carrier_proof")
        if not isinstance(proof, dict):
            raise ValueError("office_carrier_proof_required")
        if kind == "worktree_thread":
            common_dir = str(proof.get("common_dir_fingerprint") or "")
            repo_id = str(proof.get("repo_id") or "")
            expected_common_dir = task.get("repository_common_dir_fingerprint")
            expected_repo_id = task.get("repository_repo_id")
            if expected_common_dir is None:
                task["repository_common_dir_fingerprint"] = common_dir
                task["repository_repo_id"] = repo_id
                task["repository_git_authority_source"] = "git-recomputed"
            elif expected_common_dir != common_dir:
                raise ValueError("office_common_dir_fingerprint_mismatch")
            elif expected_repo_id != repo_id:
                raise ValueError("office_repository_identity_mismatch")
    return enriched


def _office_event_id(event: dict[str, object], office_instance_id: str) -> str:
    existing = str(event.get("event_id") or "")
    if existing:
        return existing
    return "EVT-" + uuid.uuid4().hex[:24].upper()


def _office_lifecycle_receipt(
    task: dict[str, Any],
    record: dict[str, object],
    *,
    action: str,
    event_id: object,
) -> dict[str, object]:
    return {
        "schema": OFFICE_LIFECYCLE_RECEIPT_SCHEMA,
        "action": action,
        "status": record.get("status"),
        "task_id": task.get("task_id"),
        "task_revision": task.get("task_revision"),
        "semantic_epoch": record.get("semantic_epoch"),
        "checkpoint_id": record.get("checkpoint_id"),
        "dispatch_uid": record.get("dispatch_uid"),
        "attempt": record.get("attempt"),
        "event_id": event_id,
        "office_instance_id": record.get("office_instance_id"),
        "office_instance_kind": record.get("office_instance_kind"),
        "role": record.get("role"),
        "direct_superior": record.get("direct_superior"),
        "carrier_proof": deepcopy(record.get("carrier_proof")),
        "decree_id": record.get("decree_id"),
        "main_court_code": record.get("main_court_code"),
        "parent_court_code": record.get("parent_court_code"),
        "child_no": record.get("child_no"),
        "lineage_parts": deepcopy(record.get("lineage_parts")),
        "lineage_key": record.get("lineage_key"),
        "lineage_version": record.get("lineage_version"),
        "metadata_record_pointer": record.get("metadata_record_pointer") or "",
        **{
            field: record.get(field)
            for field in _HIERARCHY_EVIDENCE_FIELDS
        },
        **{
            field: record.get(field)
            for field in CONTEXT_ECONOMY_BINDING_FIELDS
        },
    }


def _native_host_receipt_value(
    args: argparse.Namespace,
    *,
    required: bool,
) -> dict[str, object] | None:
    value = getattr(args, "native_host_action_receipt", None)
    if value is None:
        if required:
            raise ValueError("native_host_action_receipt:required")
        return None
    if not isinstance(value, Mapping):
        raise ValueError("native_host_action_receipt:invalid")
    return deepcopy(dict(value))


def _native_host_receipt_ledger(task: dict[str, Any]) -> dict[str, object]:
    ledger = task.get("native_host_action_receipts")
    if ledger is None:
        ledger = {}
        task["native_host_action_receipts"] = ledger
    if not isinstance(ledger, dict):
        raise ValueError("native_host_action_receipt:ledger_corrupt")
    return ledger


def _reject_native_host_receipt_replay(
    task: Mapping[str, object],
    args: argparse.Namespace,
) -> None:
    value = getattr(args, "native_host_action_receipt", None)
    if not isinstance(value, Mapping):
        return
    receipt_id = str(value.get("receipt_id") or "")
    ledger = task.get("native_host_action_receipts")
    if ledger is not None and not isinstance(ledger, Mapping):
        raise ValueError("native_host_action_receipt:ledger_corrupt")
    if receipt_id and isinstance(ledger, Mapping) and receipt_id in ledger:
        raise ValueError("native_host_action_receipt:replay")


def _native_role_ack_sources(preload: Mapping[str, object]) -> dict[str, str]:
    from court_office_bootstrap import ROOT as office_root
    return {
        field: str((Path(office_root) / Path(str(preload[field]))).resolve())
        for field in ("profile_source", "dossier_path", "court_skill_path")
    }


def _native_host_request_binding_problems(request: Mapping[str, object], *, task: Mapping[str, object], admission: Mapping[str, object], binding: Mapping[str, object], args: argparse.Namespace, record: Mapping[str, object] | None, decision: str) -> list[str]:
    route_inputs = admission.get('model_route_inputs')
    expected_assignment = route_inputs.get('assignment') if isinstance(route_inputs, Mapping) else None
    requested_assignment = getattr(args, 'assignment', None)
    if isinstance(requested_assignment, str) and requested_assignment.strip():
        expected_assignment = requested_assignment
    requested_scope = getattr(args, 'duty_scope', None)
    expected_scope = list(requested_scope) if isinstance(requested_scope, (list, tuple)) and requested_scope else list(binding.get('read_scope') or binding.get('write_set') or [])
    preload = binding.get('preload_sources')
    expected_role_ack = None
    if isinstance(preload, Mapping):
        expected_role_ack = {
            'role': binding.get('role'),
            'direct_superior': binding.get('direct_superior'),
            **_native_role_ack_sources(preload),
        }
    expected = {
        'task_id': task.get('task_id'),
        'wave_id': admission.get('wave_id'),
        'dispatch_uid': admission.get('dispatch_uid'),
        'attempt': admission.get('attempt'),
        'role': binding.get('role'),
        'instance_id': binding.get('instance_id'),
        'direct_superior': binding.get('direct_superior'),
        'semantic_epoch': admission.get('semantic_epoch'),
        'case_ref': admission.get('case_ref'),
        'office_capsule_ref': deepcopy(binding.get('office_capsule_ref')),
        'lease_id': binding.get('lease_id'),
        'assignment': expected_assignment,
        'duty_scope': expected_scope,
        'write_set': list(binding.get('write_set') or binding.get('read_scope') or []),
        'role_ack': expected_role_ack,
        'admission_anchor': {
            'schema': 'court.agent.admission_receipt.v1',
            'receipt_id': _admission_event_id(task, admission),
        },
    }
    problems = [f'native_host_action_receipt:{field}_mismatch' for field, expected_value in expected.items() if request.get(field) != expected_value]
    candidates = request.get('compatible_live_instances')
    if decision == 'spawn':
        if candidates not in ([], ()):
            problems.append('native_host_action_receipt:spawn_candidate_mismatch')
    elif record is None or not isinstance(candidates, (list, tuple)) or len(candidates) != 1:
        problems.append('native_host_action_receipt:reuse_candidate_missing')
    else:
        candidate = candidates[0]
        if not isinstance(candidate, Mapping):
            problems.append('native_host_action_receipt:reuse_candidate_invalid')
        else:
            for request_field, record_field in (('host_task_id', 'native_host_task_id'), ('host_thread_id', 'native_host_thread_id'), ('host_instance_id', 'native_host_instance_id')):
                if candidate.get(request_field) != record.get(record_field):
                    problems.append(f'native_host_action_receipt:reuse_{request_field}_mismatch')
    return problems


def _validate_native_host_receipt_for_runtime(
    task: dict[str, Any],
    admission: Mapping[str, object],
    binding: Mapping[str, object],
    args: argparse.Namespace,
    *,
    decision: str,
    host_action: str,
    outcome: str,
    record: Mapping[str, object] | None = None,
) -> dict[str, object] | None:
    required = bool(getattr(args, "_production_cli", False))
    value = _native_host_receipt_value(args, required=required)
    if value is None:
        return None
    embedded_request = value.get("request")
    if not isinstance(embedded_request, Mapping):
        raise ValueError("native_host_action_receipt:embedded_request_required")
    request = normalize_native_host_dispatch_request(embedded_request)
    problems = _native_host_request_binding_problems(
        request,
        task=task,
        admission=admission,
        binding=binding,
        args=args,
        record=record,
        decision=decision,
    )
    if problems:
        raise ValueError(problems[0])
    receipt = validate_native_host_action_receipt(
        value,
        expected=request,
        replay_guard=set(_native_host_receipt_ledger(task)),
    )
    if (
        receipt.get("decision") != decision
        or receipt.get("host_action") != host_action
        or receipt.get("outcome") != outcome
    ):
        raise ValueError("native_host_action_receipt:runtime_action_mismatch")
    args._native_host_receipt_validated = True
    return receipt


def _record_native_host_receipt(task: dict[str, Any], receipt: Mapping[str, object], *, lifecycle_action: str, target_id: str) -> None:
    ledger = _native_host_receipt_ledger(task)
    receipt_id = str(receipt.get('receipt_id') or '')
    if receipt_id in ledger:
        raise ValueError('native_host_action_receipt:replay')
    ledger[receipt_id] = {
        'receipt_id': receipt_id,
        'request_ref': receipt.get('request_ref'),
        'decision': receipt.get('decision'),
        'host_action': receipt.get('host_action'),
        'outcome': receipt.get('outcome'),
        'lifecycle_action': lifecycle_action,
        'target_id': target_id,
        'acted_at': receipt.get('acted_at'),
        'recorded_at': now_text(),
    }


def _native_host_receipt_record_fields(receipt: Mapping[str, object]) -> dict[str, object]:
    return {
        'native_host_action_receipt': deepcopy(dict(receipt)),
        'native_host_action_receipt_id': receipt.get('receipt_id'),
        'native_host_request_ref': receipt.get('request_ref'),
        'native_host_task_id': receipt.get('host_task_id'),
        'native_host_thread_id': receipt.get('host_thread_id'),
        'native_host_instance_id': receipt.get('host_instance_id'),
        'native_host_identity_kind': receipt.get('host_identity_kind'),
        'native_trace_issuer_thread_id': receipt.get('trace_issuer_thread_id'),
        'native_trace_reader_thread_id': receipt.get('trace_reader_thread_id'),
        'native_trace_session_id': receipt.get('trace_session_id'),
        'native_host_action_id': receipt.get('host_action_id'),
        'native_host_spawn_evidence': deepcopy(receipt.get('host_spawn_evidence')),
        'native_child_thread_id': (receipt.get('host_spawn_evidence') or {}).get('child_thread_id'),
    }


def _semantic_admission_expectations(
    task: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, object]:
    return _expected_semantic_binding(task, args, require_dispatchable=True)


def _validate_admission_capsule_write_scope(
    task: Mapping[str, object],
    bindings: object,
) -> None:
    capsule = task.get("invariant_capsule")
    if not isinstance(capsule, Mapping):
        raise ValueError("agent_admission_capsule_scope_missing")
    allowed_raw = capsule.get("write_set")
    allowed = canonical_repo_relative_paths(allowed_raw, allow_empty=True)
    if allowed is None or not isinstance(bindings, (list, tuple)):
        raise ValueError("agent_admission_capsule_scope_invalid")
    no_writes_declared = any(
        isinstance(path, str) and path.strip().casefold() == "no_writes_declared"
        for path in allowed_raw
    )
    for binding in bindings:
        if not isinstance(binding, Mapping):
            raise ValueError("agent_admission_capsule_scope_invalid")
        requested = canonical_repo_relative_paths(
            binding.get("write_set"),
            allow_empty=True,
        )
        if requested is None:
            raise ValueError("agent_admission_capsule_scope_invalid")
        mutates = binding.get("mutation_allowed") is True or bool(requested)
        if no_writes_declared and mutates:
            raise ValueError("agent_admission_write_scope_exceeds_capsule")
        if any(
            not any(path == parent or path.startswith(f"{parent}/") for parent in allowed)
            for path in requested
        ):
            raise ValueError("agent_admission_write_scope_exceeds_capsule")


def _expected_semantic_binding(task, args, *, require_dispatchable):
    supplied = getattr(args, "case_ref", None)
    if isinstance(supplied, str):
        supplied = _optional_json_object(supplied, "case-ref")
    if not isinstance(supplied, Mapping) or case_reference(supplied) != case_reference(task):
        raise ValueError("agent_semantic_binding_mismatch:case_ref")
    if require_dispatchable and task.get("semantic_state") != "DISPATCHABLE":
        raise ValueError("semantic_mutation_not_dispatchable")
    receipt = task.get("semantic_receipt")
    if not isinstance(receipt, dict):
        raise ValueError("semantic_receipt_missing")
    problems = _semantic_receipt_runtime_integrity_problems(task, receipt)
    if problems:
        raise ValueError("semantic_receipt_integrity_failed:" + ",".join(problems))
    expected = {
        'semantic_epoch': task.get('semantic_epoch'),
        'case_ref': case_reference(task),
        'checkpoint_id': receipt.get('checkpoint_id'),
    }
    for field, argument in (("semantic_epoch", "expected_semantic_epoch"), ("checkpoint_id", "expected_checkpoint_id")):
        if getattr(args, argument, None) != expected[field]:
            raise ValueError("agent_semantic_binding_mismatch:" + field)
    return expected


def _semantic_preload_sources(role: str) -> dict[str, str]:
    manifest = build_preload_manifest(role)
    return {"profile_source": manifest.profile_source, "dossier_path": manifest.dossier_path, "court_skill_path": manifest.court_skill_path}


def _validate_canonical_admission_preloads(args: argparse.Namespace) -> None:
    bindings = _optional_json_array(
        getattr(args, "requested_bindings_json", ""),
        "requested-bindings-json",
    )
    budget_lease = _optional_json_object(
        getattr(args, "budget_lease_json", ""),
        "budget-lease-json",
    )
    if bindings is None or budget_lease is None:
        raise ValueError("agent_admission_canonical_preload_mismatch")
    approved_ids_raw = budget_lease.get("approved_instance_ids")
    approved_preloads = budget_lease.get("approved_preload_sources")
    if not isinstance(approved_ids_raw, (list, tuple)) or not isinstance(
        approved_preloads, Mapping
    ):
        raise ValueError("agent_admission_canonical_preload_mismatch")
    approved_ids = {
        str(value or "").strip().lower() for value in approved_ids_raw
    }
    bindings_by_id = {
        str(binding.get("instance_id") or "").strip().lower(): binding
        for binding in bindings
        if isinstance(binding, Mapping)
    }
    if (
        not approved_ids
        or "" in approved_ids
        or len(bindings_by_id) != len(bindings)
        or not approved_ids.issubset(bindings_by_id)
        or {str(key or "").strip().lower() for key in approved_preloads}
        != approved_ids
    ):
        raise ValueError("agent_admission_canonical_preload_mismatch")
    for instance_id in approved_ids:
        binding = bindings_by_id[instance_id]
        role = str(binding.get("role") or "").strip().lower()
        expected = _semantic_preload_sources(role)
        if binding.get("preload_sources") != expected:
            raise ValueError("agent_admission_canonical_preload_mismatch")
        lease_hashes = approved_preloads.get(instance_id)
        if lease_hashes is None:
            lease_hashes = next(
                (
                    value
                    for key, value in approved_preloads.items()
                    if str(key or "").strip().lower() == instance_id
                ),
                None,
            )
        if lease_hashes != expected:
            raise ValueError("agent_admission_canonical_preload_mismatch")


def _generate_missing_child_office_profiles(
    args: argparse.Namespace,
    *,
    task_id: str,
    dispatch_uid: str,
    attempt: int,
    generated_at: str,
    semantic_expectations: Mapping[str, object],
    context_economy: Mapping[str, object] | None,
) -> tuple[str, ...]:
    bindings = _optional_json_array(
        getattr(args, "requested_bindings_json", ""),
        "requested-bindings-json",
    )
    if bindings is None:
        return ()
    changed = False
    generated_instance_ids: list[str] = []
    generated_time = datetime.fromisoformat(generated_at).astimezone(timezone.utc)
    lease = _optional_json_object(getattr(args, "budget_lease_json", ""), "budget-lease-json")
    expires_at_utc = normalize_optional_timestamp((lease or {}).get("expires_at_utc"), "lease expiry")
    deadline_seconds = _execution_budgets(vars(args))["deadline_seconds"]
    if deadline_seconds is not None:
        deadline = (generated_time + timedelta(seconds=deadline_seconds)).isoformat(timespec="seconds")
        if expires_at_utc is None or datetime.fromisoformat(deadline) < datetime.fromisoformat(expires_at_utc):
            expires_at_utc = deadline
    for binding in bindings:
        role = str(binding.get("role") or "").strip().lower()
        instance_kind = str(
            binding.get("instance_kind")
            or binding.get("office_instance_kind")
            or ""
        ).strip().lower()
        child_shape = (
            binding.get("canonical_authority") is False
            or instance_kind in {"worker", "craftsman", "office_worker_instance"}
            or binding.get("owner_role") not in {None, ""}
        )
        if not child_shape or binding.get("child_profile") is not None:
            continue
        if context_economy is None:
            raise ValueError("dispatch_context_packet_required")
        profile_input = dict(binding)
        profile_input.update(
            task_id=task_id,
            dispatch_uid=dispatch_uid,
            attempt=attempt,
            bounded_mandate=str(
                binding.get("bounded_mandate")
                or getattr(args, "assignment", "")
                or ""
            ),
            expected_result=str(
                binding.get("expected_result")
                or getattr(args, "context_result_mode", "")
                or "bounded_structured_receipt"
            ),
            terminal_condition=str(
                binding.get("terminal_condition")
                or "stop after the bounded result is accepted"
            ),
        )
        preload_sources = _semantic_preload_sources(role)
        child_role = str(
            binding.get("child_role")
            or ("GongBu-GongJiang" if role == "gongbu" else f"{role}-worker")
        )
        binding.update(
            {
                field: profile_input[field]
                for field in (
                    "task_id",
                    "dispatch_uid",
                    "attempt",
                    "bounded_mandate",
                    "expected_result",
                    "terminal_condition",
                )
            },
            child_role=child_role,
            expires_at_utc=expires_at_utc,
        )
        binding["case_ref"] = deepcopy(semantic_expectations["case_ref"])
        binding["semantic_receipt_id"] = context_economy["semantic_receipt_id"]
        binding["child_profile"] = build_child_office_profile(
            profile_input, child_role=child_role, case_ref=binding["case_ref"],
            semantic_receipt_id=binding["semantic_receipt_id"], expires_at_utc=expires_at_utc,
        )
        generated_instance_ids.append(
            str(binding.get("instance_id") or "").strip().lower()
        )
        changed = True
    if changed:
        args.requested_bindings_json = json.dumps(bindings, ensure_ascii=False)
    return tuple(generated_instance_ids)


def _synchronize_approved_child_bindings(args, generated_instance_ids):
    bindings = _optional_json_array(getattr(args, "requested_bindings_json", ""), "requested-bindings-json")
    lease = _optional_json_object(getattr(args, "budget_lease_json", ""), "budget-lease-json")
    if bindings is None or lease is None:
        return
    approved_ids = lease.get("approved_instance_ids")
    if not isinstance(approved_ids, (list, tuple)):
        return
    expected = {str(binding.get("instance_id") or ""): deepcopy(binding) for binding in bindings if binding.get("instance_id") in approved_ids and isinstance(binding.get("child_profile"), Mapping)}
    declared = lease.get("approved_bindings")
    if declared is None and set(expected).issubset(set(generated_instance_ids)):
        lease["approved_bindings"] = expected
        args.budget_lease_json = json.dumps(lease, ensure_ascii=False)
    elif declared != expected:
        raise ValueError("approved_budget_binding_mismatch")


def _expected_child_office_profile(binding: Mapping[str, object]) -> dict[str, object] | None:
    if not isinstance(binding.get("child_profile"), Mapping):
        return None
    return build_child_office_profile(binding, child_role=str(binding.get("child_role") or ""), case_ref=case_reference(binding["case_ref"]), semantic_receipt_id=str(binding.get("semantic_receipt_id") or ""), expires_at_utc=str(binding.get("expires_at_utc") or ""))


def _validate_admission_binding_integrity(admission, bindings):
    expected = admission.get("admission_bindings", {})
    actual = {str(binding.get("instance_id") or ""): dict(binding) for binding in bindings if isinstance(binding.get("child_profile"), Mapping)}
    if not isinstance(expected, Mapping) or expected != actual:
        raise ValueError("agent_start_admission_binding_integrity_mismatch")


def _validated_lease_child_request_bindings(
    admission: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    budget_lease = admission.get("budget_lease")
    requested_bindings = admission.get("requested_bindings")
    if not isinstance(budget_lease, Mapping) or not isinstance(
        requested_bindings, (list, tuple)
    ):
        raise ValueError("agent_start_admission_binding_integrity_mismatch")
    approved_ids_raw = budget_lease.get("approved_instance_ids")
    if not isinstance(approved_ids_raw, (list, tuple)):
        raise ValueError("agent_start_admission_binding_integrity_mismatch")
    approved_ids = tuple(
        str(value or "").strip().lower() for value in approved_ids_raw
    )
    if (
        not approved_ids
        or any(not value for value in approved_ids)
        or len(set(approved_ids)) != len(approved_ids)
    ):
        raise ValueError("agent_start_admission_binding_integrity_mismatch")
    requested_by_id: dict[str, Mapping[str, object]] = {}
    for binding in requested_bindings:
        if not isinstance(binding, Mapping):
            raise ValueError("agent_start_admission_binding_integrity_mismatch")
        instance_id = str(binding.get("instance_id") or "").strip().lower()
        if not instance_id or instance_id in requested_by_id:
            raise ValueError("agent_start_admission_binding_integrity_mismatch")
        requested_by_id[instance_id] = binding
    if any(instance_id not in requested_by_id for instance_id in approved_ids):
        raise ValueError("agent_start_admission_binding_integrity_mismatch")

    worker_kinds = {"worker", "craftsman", "office_worker_instance"}
    child_bindings: dict[str, Mapping[str, object]] = {}
    for instance_id in approved_ids:
        binding = requested_by_id[instance_id]
        instance_kind = str(
            binding.get("instance_kind")
            or binding.get("office_instance_kind")
            or ""
        ).strip().lower()
        if (
            binding.get("canonical_authority") is False
            or instance_kind in worker_kinds
            or binding.get("owner_role") not in {None, ""}
            or binding.get("child_profile") is not None
        ):
            child_bindings[instance_id] = binding

    if budget_lease.get("approved_bindings", {}) != child_bindings:
        raise ValueError("agent_start_admission_binding_integrity_mismatch")
    return child_bindings


def _validate_admission_request_binding_anchors(
    admission: Mapping[str, object],
    bindings: Sequence[Mapping[str, object]],
) -> None:
    request_bindings = _validated_lease_child_request_bindings(admission)
    for binding in bindings:
        if not isinstance(binding.get("child_profile"), Mapping):
            continue
        instance_id = str(binding.get("instance_id") or "").strip().lower()
        request_binding = request_bindings.get(instance_id)
        if request_binding is None:
            raise ValueError("agent_start_admission_binding_integrity_mismatch")
        for field, expected in request_binding.items():
            if field in {"write_set", "read_scope"}:
                continue
            if field not in binding or binding.get(field) != expected:
                raise ValueError("agent_start_admission_binding_integrity_mismatch")


def _validate_admission_semantic_receipt_anchors(task: Mapping[str, object], admission: Mapping[str, object], bindings: Sequence[Mapping[str, object]]) -> None:
    receipt = task.get('semantic_receipt')
    if not isinstance(receipt, Mapping):
        raise ValueError('agent_start_admission_binding_integrity_mismatch')
    expected = {
        'task_id': task.get('task_id'),
        'semantic_epoch': task.get('semantic_epoch'),
        'case_ref': case_reference(task),
        'checkpoint_id': receipt.get('checkpoint_id'),
    }
    preimages = (admission, *bindings)
    if any((preimage.get('semantic_receipt_sha256') is not None for preimage in preimages)):
        expected['semantic_receipt_sha256'] = receipt.get('receipt_sha256')
    for preimage in preimages:
        for field, value in expected.items():
            if preimage.get(field) != value:
                raise ValueError('agent_start_admission_binding_integrity_mismatch')
        if preimage is not admission and (preimage.get('dispatch_uid') != admission.get('dispatch_uid') or preimage.get('attempt') != admission.get('attempt')):
            raise ValueError('agent_start_admission_binding_integrity_mismatch')


_ADMISSION_LIFECYCLE_MUTABLE_FIELDS = frozenset(
    {
        "admission_event_id",
        "consumed_roles",
        "consumed_instances",
        "failed_roles",
        "failed_instances",
        "deferred_roles",
        "effective_selected_instance_ids",
        "effective_selected_roles",
        "observed_available_slots",
        "spawn_failure",
    }
)


def _admission_bound_record(admission: Mapping[str, object]) -> dict[str, object]:
    return {
        field: deepcopy(value)
        for field, value in admission.items()
        if field not in _ADMISSION_LIFECYCLE_MUTABLE_FIELDS
    }


def _validate_admission_immutable_event_anchor(
    task: Mapping[str, object],
    admission: Mapping[str, object],
) -> None:
    if isinstance(task.get("case_binding"), dict):
        from court_case_binding import refresh_case_binding
        expected_task = deepcopy(task)
        previous = admission.get("case_binding")
        roles = set(admission.get("selected_roles") or [])
        if (isinstance(previous, dict) and previous.get("zhongshu_plan") is None
                and task.get("state") in {"Pending", "Taizi", "ThreeDepartments"}
                and roles <= {"zhongshu", "menxia", "shangshu"}):
            expected_task.pop("zhongshu_plan", None)
            expected_task["case_reviews"] = {}
        if previous != refresh_case_binding(expected_task):
            raise ValueError("case_admission_binding_stale_or_foreign")
    event_id = admission.get("admission_event_id")
    matches = [
        event for event in events_for_task(task.get("task_id"), limit=None)
        if event.get("action") == "agent_admit"
        and event.get("event_id") == event_id
        and event.get("wave_id") == admission.get("wave_id")
        and event.get("allowed") is True
    ]
    if (not event_id or len(matches) != 1
            or matches[0].get("admission_record") != _admission_bound_record(admission)):
        raise ValueError("agent_start_admission_immutable_anchor_mismatch")


def _admission_event_id(task, admission):
    event_id = admission.get("admission_event_id")
    matches = [
        event for event in events_for_task(task.get("task_id"), limit=None)
        if event.get("event_id") == event_id
        and event.get("action") == "agent_admit"
        and event.get("wave_id") == admission.get("wave_id")
        and event.get("allowed") is True
    ]
    return str(event_id) if event_id and len(matches) == 1 else None


def _validate_agent_semantic_args(
    args: argparse.Namespace,
    binding: dict[str, object],
) -> None:
    if not binding.get("dispatch_uid"):
        return
    for field in AGENT_SEMANTIC_ARG_FIELDS:
        if getattr(args, field, None) != binding.get(field):
            raise ValueError(f"agent_semantic_binding_mismatch:{field}")


def _validated_consultation_refs_for_task(
    task: Mapping[str, object],
    value: object,
    *,
    agent_id: str,
) -> list[dict[str, object]]:
    """Bind optional consultation evidence without creating an authority edge."""

    references = normalize_consultation_refs(value)
    agents = task.get("agents")
    reporter = agents.get(agent_id) if isinstance(agents, dict) else None
    if not isinstance(reporter, Mapping):
        raise ValueError("consultation_ref_sender_record_missing")

    def _is_invalidated(record: Mapping[str, object]) -> bool:
        if any(
            str(record.get(field) or "").upper().startswith("INVALIDATED")
            for field in ("status", "final_status", "assignment_status")
        ):
            return True
        return (
            record.get("invalidated_at") not in {None, ""}
            or record.get("assignment_invalidated_by_semantic_resume") is True
            or record.get("assignment_invalidated_by_charter_revision") not in {None, ""}
        )

    if _is_invalidated(reporter):
        raise ValueError("consultation_ref_sender_agent_invalidated")
    reporter_role = str(reporter.get("role") or "").strip().lower()
    if reporter_role not in OFFICES:
        raise ValueError("consultation_ref_sender_record_invalid")

    def _binding_has_invalidated_agent(binding: Mapping[str, object]) -> bool:
        if not isinstance(agents, Mapping):
            return False
        binding_role = str(binding.get("role") or "").strip().lower()
        binding_instance_id = str(binding.get("instance_id") or "").strip()
        if not binding_instance_id:
            return True
        for record in agents.values():
            if not isinstance(record, Mapping):
                continue
            if str(record.get("role") or "").strip().lower() != binding_role:
                continue
            if str(record.get("admission_instance_id") or "").strip() != binding_instance_id:
                continue
            if _is_invalidated(record):
                return True
        return False

    valid_bindings: list[tuple[str, Mapping[str, object]]] = []
    admissions = task.get("agent_admissions")
    if isinstance(admissions, Mapping):
        for wave_id, admission in admissions.items():
            if not isinstance(wave_id, str) or not isinstance(admission, Mapping):
                continue
            if admission.get("allowed") is not True or _is_invalidated(admission):
                continue
            selected_bindings = admission.get("selected_bindings")
            if not isinstance(selected_bindings, (list, tuple)):
                continue
            bindings = tuple(
                binding for binding in selected_bindings if isinstance(binding, Mapping)
            )
            if len(bindings) != len(selected_bindings):
                continue
            try:
                _validate_admission_immutable_event_anchor(task, admission)
                _validate_admission_semantic_receipt_anchors(
                    task, admission, bindings
                )
            except ValueError:
                continue
            for binding in bindings:
                role = str(binding.get("role") or "").strip().lower()
                direct_superior = str(
                    binding.get("direct_superior") or ""
                ).strip().lower()
                instance_id = str(binding.get("instance_id") or "").strip()
                if (
                    role in OFFICES
                    and direct_superior in OFFICES
                    and instance_id
                    and not _binding_has_invalidated_agent(binding)
                ):
                    valid_bindings.append((wave_id, binding))

    valid_recipient_roles = {
        str(binding.get("role") or "").strip().lower()
        for _, binding in valid_bindings
    }

    reporter_wave_id = str(reporter.get("wave_id") or "").strip()
    reporter_instance_id = str(
        reporter.get("admission_instance_id") or ""
    ).strip()
    reporter_direct_superior = str(
        reporter.get("direct_superior") or ""
    ).strip().lower()

    def is_evidence_backed_superior_relay(recipient_role: str) -> bool:
        if recipient_role != reporter_direct_superior:
            return False
        for wave_id, binding in valid_bindings:
            if wave_id != reporter_wave_id:
                continue
            if str(binding.get("role") or "").strip().lower() != reporter_role:
                continue
            if (
                str(binding.get("instance_id") or "").strip()
                != reporter_instance_id
            ):
                continue
            if (
                str(binding.get("direct_superior") or "").strip().lower()
                == recipient_role
            ):
                return True
        return False

    for reference in references:
        ref_case_ref = case_reference(reference["case_ref"])
        task_case_ref = case_reference(task)
        if ref_case_ref.get("court_code") != task_case_ref.get("court_code"):
            raise ValueError("consultation_ref_task_mismatch")
        if ref_case_ref.get("charter_revision") != task_case_ref.get("charter_revision"):
            raise ValueError("consultation_ref_charter_revision_mismatch")
        if reference.get("from_role") != reporter_role:
            raise ValueError("consultation_ref_sender_role_mismatch")
        recipient_role = str(reference.get("to_role") or "").strip().lower()
        if (
            recipient_role not in valid_recipient_roles
            and not is_evidence_backed_superior_relay(recipient_role)
        ):
            raise ValueError("consultation_ref_recipient_not_task_valid")
    return references


COMPLETION_PROOF_SCHEMA = "court.completion_proof.v1"
COMPLETION_PROOF_FIELDS = {
    "schema", "task_id", "receipt_id", "assessment_ref",
    "record_ref", "completion_source_ref", "residual_gaps",
    "outcome_status", "events", "proof_ref",
}


def _completion_proof_ref(proof: dict[str, object]) -> str:
    # Non-hash proof reference bound to the court code / record reference.
    receipt_id = str(proof.get("receipt_id") or "")
    return "proof:" + receipt_id if receipt_id else "proof:UNBOUND"


def _completion_proof(
    task: dict[str, object],
    receipt: dict[str, object],
    completion_event: dict[str, object],
) -> dict[str, object]:
    binding = task.get("assessment_binding")
    completion = task.get("completion")
    if not isinstance(binding, dict) or not isinstance(completion, dict):
        raise ValueError("completion_proof_binding_missing")
    proof: dict[str, object] = {
        "schema": COMPLETION_PROOF_SCHEMA,
        "task_id": task.get("task_id"),
        "receipt_id": receipt.get("receipt_id"),
        "assessment_ref": receipt.get("assessment_ref"),
        "record_ref": receipt.get("record_ref"),
        "completion_source_ref": binding.get("completion_source_ref"),
        "residual_gaps": deepcopy(binding.get("residual_gaps")),
        "residual_gaps": binding.get("residual_gaps"),
        "outcome_status": completion.get("outcome_status"),
        "events": [
            {
                "kind": "checkpoint",
                "sequence": 1,
                "event": {
                    "action": "record_shiguan",
                    "task_id": task.get("task_id"),
                    "receipt_id": receipt.get("receipt_id"),
                    "record_ref": receipt.get("record_ref"),
                    "recorded_at": receipt.get("recorded_at"),
                },
            },
            {"kind": "completion", "sequence": 2, "event": deepcopy(completion_event)},
        ],
    }
    proof["proof_ref"] = _completion_proof_ref(proof)
    return proof


def completion_projection(
    task: dict[str, object],
    event_history: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Return the sole fail-closed presentation view of task completion."""

    completion = task.get("completion")
    if not isinstance(completion, dict):
        completion = {}
    source_version = task.get("migrated_from_runtime_schema_version")
    if source_version is None:
        try:
            source_version = int(task.get("runtime_schema_version") or 2)
        except (TypeError, ValueError):
            source_version = 2
    try:
        legacy = int(source_version) < 3
    except (TypeError, ValueError):
        legacy = True

    assessment = task.get("assessment_binding")
    checkpoint = task.get("shiguan_checkpoint")
    assessment_valid = False
    assessment_ref_valid = False
    assessment_gate: str | None = None
    completion_source_ref = ""
    residual_gaps: list[str] = []
    if isinstance(assessment, dict):
        try:
            stored_assessment = assessment
            revalidated_assessment = _revalidate_stored_assessment_binding(task)
            assessment_ref = str(stored_assessment.get("assessment_ref") or "").strip()
            assessment_valid = (
                stored_assessment.get("status") == "VERIFIED"
                and revalidated_assessment.get("gate")
                in COMPLETABLE_OUTCOME_ASSESSMENT_GATES
            )
            assessment_ref_valid = bool(assessment_ref) and (
                assessment_ref == revalidated_assessment.get("assessment_ref")
            )
            assessment_gate = str(revalidated_assessment.get("gate") or "")
            completion_source_ref = str(
                revalidated_assessment.get("completion_source_ref") or ""
            )
            residual_gaps = list(revalidated_assessment.get("residual_gaps") or [])
        except ValueError:
            assessment_valid = False
    if not isinstance(checkpoint, dict):
        checkpoint = {}
    assessment_ref = (
        assessment.get("assessment_ref") if isinstance(assessment, dict) else None
    )

    receipt_id = completion.get("receipt_id")
    checkpoint_receipt_id = checkpoint.get("receipt_id")
    consumed_receipts = task.get("consumed_checkpoint_receipt_ids")
    receipt_current = (
        isinstance(receipt_id, str)
        and bool(receipt_id)
        and receipt_id == checkpoint_receipt_id
        and isinstance(consumed_receipts, list)
        and receipt_id in consumed_receipts
    )
    record_ref = str(checkpoint.get("record_ref") or "").strip()
    checkpoint_ref_valid = bool(record_ref)
    checkpoint_verified = (
        checkpoint.get("status") == "VERIFIED"
        and checkpoint_ref_valid
        and receipt_current
    )
    checkpoint_concerns_valid = assessment_gate != "PASSED_WITH_CONCERNS"
    if assessment_gate == "PASSED_WITH_CONCERNS":
        checkpoint_concerns_valid = (
            checkpoint.get("residual_gaps") == residual_gaps
        )
    expected_outcome_status = (
        "DONE_WITH_CONCERNS"
        if assessment_gate == "PASSED_WITH_CONCERNS"
        else "DONE"
    )
    completion_concerns_valid = (
        completion.get("outcome_status") == expected_outcome_status
        and completion.get("completion_source_ref") == completion_source_ref
        and completion.get("residual_gaps") == residual_gaps
    )

    proof = completion.get("proof")
    proof_valid = False
    external_event_valid = False
    try:
        checkpoint_recorded_at = _aware_timestamp(
            checkpoint.get("recorded_at"), "invalid_projection_checkpoint_time"
        )
    except ValueError:
        checkpoint_recorded_at = ""
    checkpoint_verified = checkpoint_verified and bool(checkpoint_recorded_at)
    if isinstance(proof, dict) and set(proof) == COMPLETION_PROOF_FIELDS:
        events = proof.get("events")
        if isinstance(events, list) and len(events) == 2:
            checkpoint_event, completion_event = events
            if isinstance(checkpoint_event, dict) and isinstance(completion_event, dict):
                checkpoint_payload = checkpoint_event.get("event")
                completion_payload = completion_event.get("event")
                try:
                    proof_checkpoint_recorded_at = _aware_timestamp(
                        checkpoint_payload.get("recorded_at") if isinstance(checkpoint_payload, dict) else None,
                        "invalid_projection_proof_checkpoint_time",
                    )
                except ValueError:
                    proof_checkpoint_recorded_at = ""
                proof_valid = (
                    proof.get("schema") == COMPLETION_PROOF_SCHEMA
                    and proof.get("task_id") == task.get("task_id")
                    and proof.get("receipt_id") == receipt_id
                    and proof.get("assessment_ref") == assessment_ref
                    and proof.get("record_ref") == record_ref
                    and proof.get("completion_source_ref") == completion_source_ref
                    and proof.get("residual_gaps") == residual_gaps
                    and proof.get("outcome_status") == expected_outcome_status
                    and proof.get("proof_ref") == _completion_proof_ref(proof)
                    and checkpoint_event.get("kind") == "checkpoint"
                    and completion_event.get("kind") == "completion"
                    and checkpoint_event.get("sequence") == 1
                    and completion_event.get("sequence") == 2
                    and isinstance(checkpoint_payload, dict)
                    and checkpoint_payload.get("action") == "record_shiguan"
                    and checkpoint_payload.get("task_id") == task.get("task_id")
                    and checkpoint_payload.get("receipt_id") == receipt_id
                    and checkpoint_payload.get("record_ref") == record_ref
                    and proof_checkpoint_recorded_at == checkpoint_recorded_at
                    and isinstance(completion_payload, dict)
                    and completion_payload.get("action") == "complete"
                    and completion_payload.get("task_id") == task.get("task_id")
                    and completion_payload.get("from_state") == "ShiguanRecorded"
                    and completion_payload.get("to_state") == "Done"
                    and completion_payload.get("receipt_id") == receipt_id
                )
                if proof_valid and isinstance(event_history, list):
                    completion_indexes = [
                        index for index, item in enumerate(event_history)
                        if isinstance(item, dict) and item == completion_payload
                    ]
                    if len(completion_indexes) == 1:
                        completion_index = completion_indexes[0]
                        checkpoint_indexes = [
                            index for index, item in enumerate(event_history)
                            if isinstance(item, dict)
                            and item.get("task_id") == task.get("task_id")
                            and item.get("receipt_id") == receipt_id
                            and (
                                item.get("action") in {
                                    "record_shiguan", "record-shiguan", "checkpoint_bound",
                                }
                                or item.get("to_state") == "ShiguanRecorded"
                            )
                        ]
                        external_event_valid = bool(checkpoint_indexes) and all(
                            index < completion_index for index in checkpoint_indexes
                        )
    verified = (
        not legacy
        and task.get("state") == "Done"
        and assessment_valid
        and assessment_ref_valid
        and checkpoint_verified
        and checkpoint_concerns_valid
        and completion_concerns_valid
        and proof_valid
        and external_event_valid
        and completion.get("status") == "COMPLETED"
    )
    if legacy:
        status = "LEGACY_UNVERIFIED"
    elif verified:
        status = (
            "DONE_WITH_CONCERNS"
            if assessment_gate == "PASSED_WITH_CONCERNS"
            else "COMPLETED"
        )
    elif completion.get("status") == "COMPLETED":
        status = "INVALID_UNVERIFIED" if (
            not assessment_valid or not assessment_ref_valid or not checkpoint_ref_valid
            or (isinstance(proof, dict) and not proof_valid)
        ) else "UNVERIFIED"
    elif str(completion.get("status") or "").endswith("COMPLETE"):
        status = "UNVERIFIED"
    elif assessment_gate in {"PARTIAL", "BLOCKED"}:
        status = str(assessment_gate)
    else:
        status = str(completion.get("status") or "UNASSESSED")
    return {
        "status": status,
        "verified": verified,
        "charter_revision": task.get("charter_revision"),
        "assessment_ref": assessment_ref,
        "record_ref": record_ref or checkpoint.get("record_ref"),
        "completion_source_ref": completion_source_ref or None,
        "residual_gaps": residual_gaps,
    }


def task_summary(
    task: dict[str, Any],
    event_history: list[dict[str, object]] | None = None,
) -> str:
    projection = completion_projection(task, event_history)
    marker = " | VERIFIED_COMPLETE" if projection["verified"] else ""
    return (
        f"{task.get('task_id')} | {task.get('state')} | {task.get('owner')} | "
        f"{task.get('report_tier')} | {task.get('title')} | "
        f"completion={projection['status']} | verified={str(projection['verified']).lower()}"
        f"{marker}"
    )


def default_agent_runtime() -> dict[str, object]:
    return {
        "kind": "codex-only",
        "capabilities": [
            "local_skill",
            "command_line_ui",
            "file_backed_ledger",
            "agent_lifecycle_ledger",
        ],
    }


def _runtime_schema_version(task: dict[str, Any]) -> int:
    try:
        source_version = int(task.get("runtime_schema_version") or 2)
    except (TypeError, ValueError) as exc:
        raise ValueError("runtime schema version must be an integer") from exc
    if source_version > RUNTIME_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported runtime schema version {source_version}; "
            f"maximum supported is {RUNTIME_SCHEMA_VERSION}"
        )
    return source_version


def normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(task)
    source_version = _runtime_schema_version(normalized)
    if source_version < RUNTIME_SCHEMA_VERSION:
        normalized["migrated_from_runtime_schema_version"] = source_version
    normalized["runtime_schema_version"] = RUNTIME_SCHEMA_VERSION
    normalized.setdefault("work_kind", "legacy")
    normalized.setdefault("conversation_gate", legacy_conversation_gate())
    normalized.setdefault("charter_revision_history", [])
    normalized.setdefault(
        "outcome_assessment",
        {
            "schema": "court.outcome_assessment.v1",
            "gate": "UNASSESSED",
            "reasons": [],
            "outcome": None,
        },
    )
    normalized.setdefault("shiguan_checkpoint", {})
    normalized.setdefault("completion", {"status": "UNASSESSED"})
    normalized.setdefault("agent_runtime", default_agent_runtime())
    normalized.setdefault("stop_condition", "")
    normalized.setdefault("unsafe_remaining", "")
    normalized.setdefault("evidence_preserved", "")
    normalized.setdefault("agents", {})
    agents = normalized["agents"]
    if isinstance(agents, dict):
        for agent_id, record in list(agents.items()):
            if not isinstance(record, dict):
                continue
            if "office_execution_ready" not in record:
                legacy_record = dict(record)
                legacy_record["legacy_assignment_binding_unenforced"] = True
                legacy_record["office_execution_ready"] = False
                agents[agent_id] = legacy_record
    return normalized


def require_semantic_mutation_binding(task: dict[str, Any]) -> None:
    """Keep legacy v2/v3 records readable but fail closed on mutation.

    Normalization is a diagnostic projection, not a migration receipt.  A task
    becomes mutable only when its charter body, revision/epoch, digest, and
    invariant capsule form one current semantic binding.
    """

    problems = semantic_binding_problems(task)
    if problems:
        raise ValueError("legacy_semantic_binding_read_only:" + ",".join(problems))


LEGACY_SEMANTIC_BINDING_FIELDS = (
    "charter_revision",
    "semantic_epoch",
    "invariant_capsule",
    "semantic_state",
    "semantic_receipt",
    "semantic_receipt_id",
    "semantic_receipts",
)


def _legacy_semantic_bootstrap(task: dict[str, object]) -> bool:
    return all(field not in task for field in LEGACY_SEMANTIC_BINDING_FIELDS)


@dataclass
class TransitionResult:
    task: dict[str, Any]
    event: dict[str, Any]


def _json_object_from_args(
    args: argparse.Namespace,
    direct_name: str,
    file_name: str,
    label: str,
) -> dict[str, object]:
    direct = getattr(args, direct_name, None)
    if direct is not None:
        if not isinstance(direct, dict):
            raise ValueError(f"{label} must be an object")
        return dict(direct)
    path = getattr(args, file_name, None)
    if not path:
        raise ValueError(f"{label} is required")
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} file must contain an object")
    return value


def _text_from_args(
    args: argparse.Namespace,
    direct_name: str,
    file_name: str,
    label: str,
) -> str:
    direct = getattr(args, direct_name, None)
    if direct is not None:
        if not isinstance(direct, str) or not direct.strip():
            raise ValueError(f"{label}_required")
        return direct
    path = getattr(args, file_name, None)
    if not path:
        raise ValueError(f"{label}_required")
    value = Path(path).read_text(encoding="utf-8")
    if not value.strip():
        raise ValueError(f"{label}_required")
    return value


def _legacy_court_code(task_id: str, title: str) -> str:
    """Official court code for a create without a caller-supplied session.

    Uses the standard session numbering (domain_court_code_issue) with a
    deterministic session identifier derived from the task, so every legacy
    create still receives the official ``<domain>-<date>-<seq>-<suffix>`` court
    code and the same suffix format used by standard session creates.
    """

    from court_session_numbering import domain_court_code_issue

    session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "dsh:legacy:" + task_id))
    issued = domain_court_code_issue(session_id, title)
    if issued.get("ok") is not True:
        raise ValueError("case_create_allocation_failed")
    return str(issued["court_code"])


def _case_create_selection(args: argparse.Namespace) -> dict[str, str] | None:
    """Read the opt-in standard-session identity without changing legacy create."""

    session_id = str(getattr(args, "session_id", "") or "").strip()
    if not session_id:
        return None
    authority = str(getattr(args, "authority", "") or "").strip().lower()
    behavior = str(getattr(args, "behavior", "") or "").strip().lower()
    if authority not in {"approval", "autonomous", "super"}:
        raise ValueError("case_create_authority_required")
    if behavior not in {"serial", "parallel"}:
        raise ValueError("case_create_behavior_required")
    return {
        "session_id": session_id,
        "authority": authority,
        "behavior": behavior,
    }


def _case_create_replay(
    tasks: Mapping[str, dict[str, Any]],
    selection: Mapping[str, str],
    *,
    requested_task_id: str,
    title: str,
    charter: str,
    work_kind: str,
) -> TransitionResult | None:
    """Return the one exact standard-session create replay, if present."""

    matches = [
        task
        for task in tasks.values()
        if isinstance(task.get("case_binding"), dict)
        and task["case_binding"].get("session_id") == selection["session_id"]
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("case_create_session_binding_ambiguous")
    task = matches[0]
    from court_case_binding import validate_task_case_binding

    binding = validate_task_case_binding(task)
    if binding is None:
        raise ValueError("case_create_session_binding_missing")
    if requested_task_id and task.get("task_id") != requested_task_id:
        raise ValueError("case_create_session_task_conflict")
    if (
        task.get("title") != title
        or task.get("charter") != charter
        or task.get("work_kind") != work_kind
        or binding.get("case_execution")
        != {"authority": selection["authority"], "behavior": selection["behavior"]}
    ):
        raise ValueError("case_create_session_replay_conflict")
    events = [
        event
        for event in events_for_task(str(task.get("task_id") or ""), limit=None)
        if event.get("action") == "create"
    ]
    if len(events) != 1:
        raise ValueError("case_create_replay_event_missing")
    return TransitionResult(deepcopy(task), deepcopy(events[0]))


def _standard_case_decree_operation_id(binding: Mapping[str, object]) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "court.standard_case.decree_open.v1:"
            + str(binding["session_id"])
            + ":"
            + str(binding["task_id"]),
        )
    )


def _ensure_standard_case_decree(created: TransitionResult) -> TransitionResult:
    """Run/replay the existing decree operation after the create lock is released."""

    from court_case_binding import validate_task_case_binding

    current_before = load_tasks().get(str(created.task.get("task_id") or ""))
    if not isinstance(current_before, dict):
        raise ValueError("case_create_task_missing_before_decree_open")
    binding = validate_task_case_binding(current_before)
    if binding is None:
        return created
    operation_id = _standard_case_decree_operation_id(binding)
    operation = (
        current_before.get("operations", {}).get(operation_id)
        if isinstance(current_before.get("operations"), dict)
        else None
    )

    def replay_or_recover_existing() -> None:
        latest = load_tasks().get(str(binding["task_id"]))
        latest_operation = (
            latest.get("operations", {}).get(operation_id)
            if isinstance(latest, dict) and isinstance(latest.get("operations"), dict)
            else None
        )
        if (
            isinstance(latest_operation, dict)
            and latest_operation.get("status") == "ALLOCATED"
        ):
            recover_decree_open_operation(operation_id)
            return
        decree_open_task(
            argparse.Namespace(
                task_id=binding["task_id"],
                operation_id=operation_id,
                expected_task_revision=int(
                    latest.get("task_revision")
                    if isinstance(latest, dict)
                    else current_before["task_revision"]
                ),
                payload=None,
                payload_file=None,
                replay_only=True,
                actor="taizi",
                evidence="standard session create decree-open replay",
                note="standard session create decree-open replay",
                killpoint="",
            )
        )

    if isinstance(operation, dict):
        if operation.get("status") == "ALLOCATED":
            recover_decree_open_operation(operation_id)
        elif operation.get("status") == "COMMITTED":
            replay_or_recover_existing()
        else:
            recover_decree_open_operation(operation_id)
    else:
        try:
            decree_open_task(
                argparse.Namespace(
                    task_id=binding["task_id"],
                    operation_id=operation_id,
                    expected_task_revision=int(current_before["task_revision"]),
                    payload={"lineage_parts": ["court", "standard-session"]},
                    payload_file=None,
                    actor="taizi",
                    evidence="standard session create decree-open",
                    note="standard session create decree-open",
                    killpoint="",
                )
            )
        except ValueError as exc:
            if str(exc) not in {
                "operation_binding_conflict",
                "operation_replay_requires_reference_only",
            }:
                raise
            replay_or_recover_existing()
    current = load_tasks().get(str(binding["task_id"]))
    if not isinstance(current, dict):
        raise ValueError("case_create_task_missing_after_decree_open")
    return TransitionResult(current, created.event)


def create_task(args: argparse.Namespace) -> TransitionResult:
    gate = require_new_formal_task_gate(
        _json_object_from_args(args, "intake_gate", "intake_file", "formal conversation gate")
    )
    work_kind = str(getattr(args, "work_kind", "") or "").strip()
    if work_kind not in WORK_KINDS:
        raise ValueError(f"invalid work kind: {work_kind}")
    charter = require_exact_text(args.charter, "charter")
    report_tier = args.report_tier or ("brief" if read_only_decree(charter) else "standard")
    if report_tier not in REPORT_TIERS:
        raise ValueError(f"invalid report tier: {report_tier}")
    invariant_capsule = None
    if getattr(args, "invariant_capsule", None) is not None or getattr(
        args,
        "invariant_capsule_file",
        None,
    ) is not None:
        invariant_capsule = _json_object_from_args(
            args,
            "invariant_capsule",
            "invariant_capsule_file",
            "invariant capsule",
        )
    case_selection = _case_create_selection(args)
    if case_selection is None:
        semantic_binding = initial_semantic_binding(
            charter,
            invariant_capsule,
            court_code=_legacy_court_code(str(args.task_id or ""), args.title),
        )
    else:
        semantic_binding = None
        if invariant_capsule is not None and canonical_repo_relative_paths(
            invariant_capsule.get("write_set", []), allow_empty=True
        ) is None:
            raise ValueError("standard_create_capsule_write_set_requires_relative_paths")
    result: TransitionResult | None = None
    with runtime_lock():
        tasks = load_tasks()
        if case_selection is not None:
            replay = _case_create_replay(
                tasks,
                case_selection,
                requested_task_id=str(args.task_id or ""),
                title=args.title,
                charter=charter,
                work_kind=work_kind,
            )
            if replay is not None:
                result = replay
        if result is None:
            task_id = args.task_id or f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{slugify(args.title)}"
            if task_id in tasks:
                raise ValueError(f"task already exists: {task_id}")
            session_allocation: dict[str, object] | None = None
            if case_selection is not None:
                from court_session_numbering import domain_court_code_issue

                issued = domain_court_code_issue(case_selection["session_id"], args.title)
                if issued.get("ok") is not True:
                    raise ValueError("case_create_allocation_failed")
                session_allocation = dict(issued)
                semantic_binding = initial_semantic_binding(charter, invariant_capsule, court_code=str(session_allocation["court_code"]))
            task = normalize_task({
                "runtime_schema_version": RUNTIME_SCHEMA_VERSION,
                "task_id": task_id,
                "title": args.title,
                "charter": charter,
                **semantic_binding,
                "task_revision": 1,
                "state": "Pending",
                "owner": args.owner,
                "report_tier": report_tier,
                "read_only": read_only_decree(charter),
                "created_at": now_text(),
                "updated_at": now_text(),
                "heartbeat": "created",
                "last_evidence": args.evidence,
                "work_kind": work_kind,
                "conversation_gate": gate,
                "agent_runtime": default_agent_runtime(),
                "stop_condition": "",
                "unsafe_remaining": "",
                "evidence_preserved": "",
                "agents": {},
                **(
                    {
                        "session_id": case_selection["session_id"],
                        "court_code": str(session_allocation["court_code"]),
                        "case_execution": {
                            "authority": case_selection["authority"],
                            "behavior": case_selection["behavior"],
                        },
                    }
                    if case_selection is not None and session_allocation is not None
                    else {}
                ),
            })
            if session_allocation is not None:
                from court_case_binding import build_case_binding
                from court_plan_artifacts import bootstrap_artifact

                task["case_bootstrap"] = bootstrap_artifact(task)
                task["case_binding"] = build_case_binding(task, session_allocation)
            tasks[task_id] = task
            event = make_event(task, "create", "", "Pending", args.owner, args.evidence, args.note)
            if session_allocation is not None:
                event.update(
                session_id=task["session_id"],
                court_code=task["court_code"],
                case_ref=case_reference(task),
                )
            _commit_task_event(tasks, event)
            result = TransitionResult(task, event)
    if result is None:
        raise ValueError("case_create_result_missing")
    return _ensure_standard_case_decree(result) if case_selection is not None else result


RECHARTERABLE_STATES = STATES - {"Done", "Cancelled", "Rejected"}


def _unassessed_outcome() -> dict[str, object]:
    return {
        "schema": "court.outcome_assessment.v1",
        "gate": "UNASSESSED",
        "reasons": [],
        "outcome": None,
    }


def _canonical_sha256(value: object, error: str) -> str:
    digest = str(value or "")
    if len(digest) != 64 or any(
        character not in "0123456789abcdefABCDEF" for character in digest
    ):
        raise ValueError(error)
    return digest.lower()


def _aware_timestamp(value: object, error: str) -> str:
    text = str(value or "").strip()
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(error) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(error)
    return parsed.isoformat()


def _source_envelope_ref(value: dict[str, object]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _bounded_completion_pointer(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"completion_source_{field}_required")
    pointer = value.strip()
    if len(pointer.encode("utf-8")) > 512 or any(
        character in pointer for character in "\x00\r\n"
    ):
        raise ValueError(f"completion_source_{field}_invalid")
    lowered = pointer.casefold()
    if any(token in lowered for token in ("pending/", "/pending/", "private/", "/private/")):
        raise ValueError("completion_source_privacy_gate_failed")
    return pointer


def _validated_completion_source(
    task: Mapping[str, object],
    value: object,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("completion_source_required")
    source = dict(value)
    expected_fields = {
        "schema", "task_id", "charter_revision", "case_ref", "sources"
    }
    if set(source) != expected_fields:
        raise ValueError("completion_source_fields_invalid")
    if source.get("schema") != COMPLETION_SOURCE_SCHEMA:
        raise ValueError("completion_source_schema_invalid")
    if source.get("task_id") != task.get("task_id"):
        raise ValueError("completion_source_task_mismatch")
    if source.get("charter_revision") != task.get("charter_revision"):
        raise ValueError("completion_source_charter_revision_mismatch")
    reference = case_reference(task)
    if not isinstance(source.get("case_ref"), Mapping) or case_reference(source["case_ref"]) != reference:
        raise ValueError("completion_source_case_reference_mismatch")
    raw_sources = source.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("completion_source_sources_required")
    if len(raw_sources) > COMPLETION_SOURCE_MAX_ITEMS:
        raise ValueError("completion_source_sources_exceed_limit")
    normalized_sources: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    serial_roles: set[str] = set()
    source_fields = {"kind", "role", "pointer"}
    raw_menxia_sources = [
        item
        for item in raw_sources
        if isinstance(item, dict)
        and str(item.get("role") or "").strip().lower() == "menxia"
    ]
    if not raw_menxia_sources:
        raise ValueError("completion_source_menxia_required")
    report_events = events_for_task(task.get("task_id"), limit=None)
    agents = task.get("agents")
    if not isinstance(agents, dict):
        agents = {}
    verified_menxia_source = False
    for item in raw_sources:
        if (not isinstance(item, dict) or not source_fields.issubset(item)
                or set(item) - source_fields - {"sha256", "event_id"}):
            raise ValueError("completion_source_item_fields_invalid")
        kind = str(item.get("kind") or "").strip()
        role = str(item.get("role") or "").strip().lower()
        if kind not in COMPLETION_SOURCE_KINDS:
            raise ValueError("completion_source_kind_invalid")
        if role not in OFFICES:
            raise ValueError("completion_source_role_invalid")
        normalized = {
            "kind": kind,
            "role": role,
            "pointer": _bounded_completion_pointer(item.get("pointer"), "pointer"),
        }
        if "sha256" in item:
            normalized["sha256"] = _canonical_sha256(
                item.get("sha256"), "completion_source_sha256_invalid"
            )
            if normalized["sha256"] != hashlib.sha256(
                str(normalized["pointer"]).encode("utf-8")
            ).hexdigest():
                raise ValueError("completion_source_report_sha256_mismatch")
        if "event_id" in item:
            normalized["event_id"] = _bounded_completion_pointer(item["event_id"], "event_id")
        identity = (kind, role, str(normalized["pointer"]))
        if identity in seen:
            raise ValueError("completion_source_duplicate")
        seen.add(identity)
        if kind == "serial_inline":
            if "event_id" in item:
                raise ValueError("completion_source_serial_event_forbidden")
            if "sha256" not in item and (task.get("case_execution") or {}).get("behavior") != "serial":
                raise ValueError("completion_source_serial_execution_required")
            if role in serial_roles:
                raise ValueError("completion_source_serial_role_duplicate")
            serial_roles.add(role)
            if role == "menxia":
                verified_menxia_source = True
        else:
            matches = [
                event
                for event in report_events
                if isinstance(event, dict)
                and event.get("action") == "agent_report"
                and event.get("agent_role") == role
                and event.get("evidence") == normalized["pointer"]
                and ("event_id" not in normalized or event.get("event_id") == normalized["event_id"])
            ]
            if len(matches) != 1:
                raise ValueError("completion_source_menxia_report_missing")
            agent_id = str(matches[0].get("agent_id") or "")
            agent = agents.get(agent_id)
            if (
                not isinstance(agent, dict)
                or agent.get("role") != role
                or agent.get("preload_status") != "PASSED"
                or agent.get("office_execution_ready") is not True
            ):
                raise ValueError("completion_source_menxia_report_missing")
            if role == "menxia":
                verified_menxia_source = True
        normalized_sources.append(normalized)
    if not verified_menxia_source:
        raise ValueError("completion_source_menxia_required")
    return {
        "schema": COMPLETION_SOURCE_SCHEMA,
        "task_id": task.get("task_id"),
        "charter_revision": task.get("charter_revision"),
        "case_ref": reference,
        "sources": normalized_sources,
    }


def _validated_residual_gaps(
    value: object,
    *,
    gate: str,
) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("residual_gaps_required")
    if len(value) > RESIDUAL_GAPS_MAX_ITEMS:
        raise ValueError("residual_gaps_exceed_limit")
    gaps: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("residual_gap_invalid")
        gap = item.strip()
        if len(gap.encode("utf-8")) > RESIDUAL_GAP_MAX_BYTES or any(
            character in gap for character in "\x00\r\n"
        ):
            raise ValueError("residual_gap_invalid")
        if gap in gaps:
            raise ValueError("residual_gap_duplicate")
        gaps.append(gap)
    if gate == "PASSED_WITH_CONCERNS" and not gaps:
        raise ValueError("concerns_assessment_requires_residual_gaps")
    if gate == "PASSED" and gaps:
        raise ValueError("passed_assessment_must_not_have_residual_gaps")
    return gaps


def _source_envelope_ref(value: dict[str, object]) -> str:
    reference = value.get("case_ref")
    try:
        from court_case_binding import case_reference

        court_code = case_reference(reference)["court_code"]
    except (TypeError, ValueError):
        court_code = "UNBOUND"
    return f"source_envelope:{court_code}:{str(value.get('charter_revision') or '')}"


def _validated_archive_producer_receipt(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("archive_producer_receipt_required")
    receipt = deepcopy(value)
    required = {
        "schema",
        "receipt_id",
        "path",
        "court_code",
        "recorded_at",
        "record_ref",
        "residual_gaps",
    }
    if not required.issubset(receipt):
        raise ValueError("archive_producer_receipt_fields_missing")
    if receipt.get("schema") != ARCHIVE_PRODUCER_RECEIPT_SCHEMA:
        raise ValueError("archive_producer_receipt_schema_invalid")
    receipt_id = str(receipt.get("receipt_id") or "")
    court_code = str(receipt.get("court_code") or "")
    if (
        not re.fullmatch(r"shiguan:[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", receipt_id)
        or not court_code
        or receipt_id != f"shiguan:{court_code}"
    ):
        raise ValueError("archive_producer_receipt_id_invalid")
    record_ref = str(receipt.get("record_ref") or "").strip()
    if record_ref != receipt_id:
        raise ValueError("archive_producer_record_ref_mismatch")
    archive_path = Path(str(receipt.get("path") or "")).resolve()
    shared_references = reference_path().resolve()
    try:
        archive_path.relative_to(shared_references)
    except ValueError as exc:
        raise ValueError("archive_producer_receipt_path_invalid") from exc
    if not archive_path.is_file():
        raise ValueError("archive_producer_receipt_path_invalid")
    recorded_at = _aware_timestamp(
        receipt.get("recorded_at"), "archive_producer_receipt_time_invalid"
    )
    raw_residual_gaps = receipt.get("residual_gaps")
    producer_gate = (
        "PASSED_WITH_CONCERNS"
        if isinstance(raw_residual_gaps, list) and raw_residual_gaps
        else "PASSED"
    )
    residual_gaps = _validated_residual_gaps(raw_residual_gaps, gate=producer_gate)
    index = reference_path("shiguan-index.jsonl")
    if not index.is_file():
        raise ValueError("archive_producer_index_missing")
    entries: list[dict[str, object]] = []
    for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("archive_producer_index_invalid") from exc
        if isinstance(entry, dict) and entry.get("court_code") == court_code:
            entries.append(entry)
    if len(entries) != 1:
        raise ValueError("archive_producer_record_missing")
    entry = entries[0]
    entry_ref = str(entry.get("record_ref") or "").strip()
    if entry_ref and entry_ref != record_ref:
        raise ValueError("archive_producer_record_ref_mismatch")
    if entry.get("residual_gaps") != residual_gaps:
        raise ValueError("archive_producer_residual_gaps_mismatch")
    if _aware_timestamp(
        entry.get("time"), "archive_producer_record_time_invalid"
    ) != recorded_at:
        raise ValueError("archive_producer_record_time_mismatch")
    archive_text = archive_path.read_text(encoding="utf-8", errors="replace")
    if f"- court_code: {court_code}" not in archive_text:
        raise ValueError("archive_producer_record_missing")
    residual_gaps_json = json.dumps(
        residual_gaps, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if f"- residual_gaps_json: {residual_gaps_json}" not in archive_text:
        raise ValueError("archive_producer_archive_evidence_missing")
    receipt["receipt_id"] = receipt_id
    receipt["path"] = str(archive_path)
    receipt["court_code"] = court_code
    receipt["recorded_at"] = recorded_at
    receipt["record_ref"] = record_ref
    receipt["residual_gaps"] = residual_gaps
    return receipt


def _validate_archive_producer_residual_gaps(
    producer_receipt: Mapping[str, object],
    binding: Mapping[str, object],
) -> None:
    if (
        producer_receipt.get("residual_gaps") != binding.get("residual_gaps")
        or producer_receipt.get("residual_gaps")
        != binding.get("residual_gaps")
    ):
        raise ValueError("archive_producer_residual_gaps_mismatch")


def _record_shiguan_preconditions(task: dict[str, object]) -> dict[str, object]:
    _require_case_reviewed(task)
    require_semantic_mutation_binding(task)
    if str(task.get("state") or "") != "MenxiaReview":
        raise ValueError("record_shiguan_requires_menxia_review")
    binding = _revalidate_stored_assessment_binding(task)
    stored_binding = task.get("assessment_binding")
    if (
        not isinstance(stored_binding, dict)
        or stored_binding.get("status") != "VERIFIED"
        or binding.get("gate") not in COMPLETABLE_OUTCOME_ASSESSMENT_GATES
    ):
        raise ValueError("outcome_assessment_not_completable")
    return binding


def _runtime_checkpoint_receipt(
    task: Mapping[str, object],
    binding: Mapping[str, object],
    producer_receipt: Mapping[str, object],
) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema": CHECKPOINT_RECEIPT_SCHEMA,
        "receipt_id": producer_receipt["receipt_id"],
        "task_id": task["task_id"],
        "charter_revision": task["charter_revision"],
        "case_ref": case_reference(task),
        "assessment_ref": binding["assessment_ref"],
        "record_ref": producer_receipt["record_ref"],
        "archive_path": producer_receipt["path"],
        "recorded_at": producer_receipt["recorded_at"],
    }
    if binding.get("gate") == "PASSED_WITH_CONCERNS":
        receipt.update(
            residual_gaps=deepcopy(binding["residual_gaps"]),
        )
    return receipt


def record_shiguan_preflight(args: argparse.Namespace, *, include_residual_gaps: bool = False) -> dict[str, object]:
    with runtime_lock(recover=False):
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not isinstance(task, dict):
            raise ValueError(f"task not found: {args.task_id}")
        if task.get("charter_revision") != args.expected_revision:
            raise ValueError("stale_charter_revision")
        supplied_case_ref = getattr(args, "case_ref", None)
        if not isinstance(supplied_case_ref, Mapping) or case_reference(supplied_case_ref) != case_reference(task):
            raise ValueError("record_shiguan_case_reference_mismatch")
        binding = _record_shiguan_preconditions(task)
        result: dict[str, object] = {
            "task_id": task["task_id"],
            "charter_revision": task["charter_revision"],
            "case_ref": case_reference(task),
            "assessment_ref": binding["assessment_ref"],
            "assessment_gate": binding["gate"],
        }
        if include_residual_gaps:
            result.update(residual_gaps=deepcopy(binding.get("residual_gaps", [])))
        from court_case_binding import validate_case_binding, validate_task_case_binding

        case_binding = validate_task_case_binding(task, require_decree=True)
        if case_binding is not None:
            supplied_full_binding = getattr(args, "case_binding", None)
            if supplied_full_binding is not None and supplied_full_binding != case_binding:
                raise ValueError("record_shiguan_case_binding_foreign")
            if str(getattr(args, "session_id", "") or "").strip() != case_binding["session_id"]:
                raise ValueError("record_shiguan_session_mismatch")
            result.update(
                session_id=case_binding["session_id"],
                court_code=case_binding["court_code"],
                case_ref=case_reference(case_binding),
            )
        return result


def record_shiguan_task(args: argparse.Namespace) -> TransitionResult:
    if args.actor not in OFFICES:
        raise ValueError("unknown_actor_office")
    producer_receipt = _validated_archive_producer_receipt(
        _json_object_from_args(
            args,
            "archive_receipt",
            "archive_receipt_file",
            "archive producer receipt",
        )
    )
    producer_receipt_ref = producer_receipt["record_ref"]
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not isinstance(task, dict):
            raise ValueError(f"task not found: {args.task_id}")
        if task.get("charter_revision") != args.expected_revision:
            raise ValueError("stale_charter_revision")
        supplied_case_ref = getattr(args, "case_ref", None)
        if not isinstance(supplied_case_ref, Mapping) or case_reference(supplied_case_ref) != case_reference(task):
            raise ValueError("record_shiguan_case_reference_mismatch")
        from court_case_binding import validate_case_binding, validate_task_case_binding

        case_binding = validate_task_case_binding(task, require_decree=True)
        if case_binding is not None:
            supplied_full_binding = getattr(args, "case_binding", None)
            if supplied_full_binding is not None and supplied_full_binding != case_binding:
                raise ValueError("record_shiguan_case_binding_foreign")
            if "case_binding" in producer_receipt and producer_receipt["case_binding"] != case_binding:
                raise ValueError("record_shiguan_producer_case_binding_mismatch")
            if str(getattr(args, "session_id", "") or "").strip() != case_binding["session_id"]:
                raise ValueError("record_shiguan_session_mismatch")
            required_case_receipt = {
                "task_id": case_binding["task_id"],
                "session_id": case_binding["session_id"],
                "court_code": case_binding["court_code"],
                "charter_revision": case_binding["charter_revision"],
                "case_ref": case_reference(case_binding),
            }
            if any(
                producer_receipt.get(field) != expected
                for field, expected in required_case_receipt.items()
            ):
                raise ValueError("record_shiguan_producer_case_binding_mismatch")
        checkpoint = task.get("shiguan_checkpoint")
        if str(task.get("state") or "") == "ShiguanRecorded":
            if not isinstance(checkpoint, dict):
                raise ValueError("record_shiguan_replay_conflict")
            if (
                checkpoint.get("producer_receipt_ref") != producer_receipt_ref
                or checkpoint.get("producer_receipt") != producer_receipt
            ):
                raise ValueError("record_shiguan_replay_conflict")
            matches = [
                event
                for event in events_for_task(args.task_id, limit=None)
                if event.get("action") == "record_shiguan"
                and event.get("receipt_id") == checkpoint.get("receipt_id")
            ]
            if len(matches) != 1:
                raise ValueError("record_shiguan_replay_event_missing")
            return TransitionResult(deepcopy(task), deepcopy(matches[0]))
        binding = _record_shiguan_preconditions(task)
        _validate_archive_producer_residual_gaps(producer_receipt, binding)
        runtime_receipt = _runtime_checkpoint_receipt(
            task, binding, producer_receipt
        )
        if case_binding is not None:
            runtime_receipt.update(
                session_id=case_binding["session_id"],
                court_code=case_binding["court_code"],
                case_ref=case_reference(case_binding),
            )
        recorded = deepcopy(task)
        recorded["state"] = "ShiguanRecorded"
        recorded["owner"] = args.actor
        recorded["updated_at"] = now_text()
        recorded["last_evidence"] = args.evidence
        recorded["shiguan_checkpoint"] = {
            "status": "VERIFIED",
            "receipt_id": runtime_receipt["receipt_id"],
            "record_ref": runtime_receipt["record_ref"],
            "archive_path": runtime_receipt["archive_path"],
            "recorded_at": runtime_receipt["recorded_at"],
            "producer_receipt": deepcopy(producer_receipt),
            "producer_receipt_ref": producer_receipt_ref,
        }
        if "residual_gaps" in runtime_receipt:
            recorded["shiguan_checkpoint"].update(
                residual_gaps=deepcopy(runtime_receipt["residual_gaps"]),
            )
        if case_binding is not None:
            recorded["shiguan_checkpoint"].update(
                session_id=case_binding["session_id"],
                court_code=case_binding["court_code"],
                charter_revision=case_binding["charter_revision"],
                case_ref=case_reference(case_binding),
            )
        recorded["completion"] = {
            "status": "READY",
            "outcome_status": (
                "DONE_WITH_CONCERNS"
                if binding.get("gate") == "PASSED_WITH_CONCERNS"
                else "DONE"
            ),
            "completion_source_ref": binding["completion_source_ref"],
            "residual_gaps": deepcopy(binding["residual_gaps"]),
        }
        event = make_event(
            recorded,
            "record_shiguan",
            "MenxiaReview",
            "ShiguanRecorded",
            args.actor,
            args.evidence,
            args.note,
        )
        event.update(
            receipt_id=runtime_receipt["receipt_id"],
            assessment_ref=runtime_receipt["assessment_ref"],
            record_ref=runtime_receipt["record_ref"],
            recorded_at=runtime_receipt["recorded_at"],
            producer_receipt_ref=producer_receipt_ref,
            outcome_status=recorded["completion"]["outcome_status"],
            residual_gaps=deepcopy(recorded["completion"]["residual_gaps"]),
        )
        if case_binding is not None:
            event.update(
                session_id=case_binding["session_id"],
                court_code=case_binding["court_code"],
                charter_revision=case_binding["charter_revision"],
                case_ref=case_reference(case_binding),
            )
        tasks[args.task_id] = recorded
        _commit_task_event(tasks, event)
    return TransitionResult(recorded, event)


def _revalidate_stored_assessment_binding(
    task: dict[str, object],
) -> dict[str, object]:
    binding = task.get("assessment_binding")
    if not isinstance(binding, dict) or not binding:
        raise ValueError("assessment_binding_integrity")
    source = binding.get("source_envelope")
    source_sha256 = binding.get("source_envelope_ref")
    if not isinstance(source, dict) or not isinstance(source_sha256, str):
        raise ValueError("assessment_binding_integrity")
    if _source_envelope_ref(source) != source_sha256:
        raise ValueError("assessment_binding_integrity")
    try:
        revalidated = validate_runtime_assessment_binding(task, source)
    except ValueError as exc:
        raise ValueError("assessment_binding_integrity") from exc
    stored_core = {
        key: deepcopy(binding[key])
        for key in RUNTIME_ASSESSMENT_BINDING_FIELDS
        if key in binding
    }
    if stored_core != revalidated:
        raise ValueError("assessment_binding_integrity")
    return revalidated


def validate_runtime_assessment_binding(
    task: dict[str, object],
    assessment: dict[str, object],
) -> dict[str, object]:
    """Validate and canonically bind an outcome assessment to one task revision."""

    if not isinstance(assessment, dict):
        raise ValueError("outcome_assessment_must_be_object")
    validated = deepcopy(assessment)
    unknown_fields = set(validated) - RUNTIME_ASSESSMENT_BINDING_FIELDS
    if unknown_fields:
        raise ValueError("assessment_unknown_fields")
    if validated.get("schema") != RUNTIME_ASSESSMENT_BINDING_SCHEMA:
        raise ValueError("invalid_runtime_assessment_binding_schema")
    gate = str(validated.get("gate") or "")
    if gate not in OUTCOME_ASSESSMENT_GATES:
        raise ValueError("invalid_outcome_assessment_gate")
    reasons = validated.get("reasons")
    if not isinstance(reasons, list):
        raise ValueError("invalid_outcome_assessment_reasons")
    if any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
        raise ValueError("invalid_outcome_assessment_reason")
    if gate == "PASSED" and reasons:
        raise ValueError("passed_assessment_must_not_have_reasons")
    if gate != "PASSED" and not reasons:
        raise ValueError("nonpassed_assessment_requires_reasons")
    if validated.get("task_id") != task.get("task_id"):
        raise ValueError("assessment_task_mismatch")
    if validated.get("charter_revision") != task.get("charter_revision"):
        raise ValueError("assessment_charter_revision_mismatch")
    reference = case_reference(task)
    if not isinstance(validated.get("case_ref"), Mapping) or case_reference(validated["case_ref"]) != reference:
        raise ValueError("assessment_case_reference_mismatch")
    evidence_ref = str(validated.get("evidence_ref") or "").strip()
    if not evidence_ref:
        raise ValueError("invalid_assessment_evidence_ref")
    assessment_ref = str(validated.get("assessment_ref") or "").strip()
    if not assessment_ref:
        raise ValueError("invalid_assessment_ref")
    completion_source = _validated_completion_source(
        task, validated.get("completion_source")
    )
    completion_source_ref = str(validated.get("completion_source_ref") or "").strip()
    if not completion_source_ref:
        raise ValueError("invalid_completion_source_ref")
    residual_gaps = _validated_residual_gaps(validated.get("residual_gaps"), gate=gate)
    assessed_at = _aware_timestamp(
        validated.get("assessed_at"),
        "invalid_assessment_timestamp",
    )
    validated["case_ref"] = reference
    validated["evidence_ref"] = evidence_ref
    validated["assessment_ref"] = assessment_ref
    validated["completion_source"] = completion_source
    validated["completion_source_ref"] = completion_source_ref
    validated["residual_gaps"] = residual_gaps
    validated["assessed_at"] = assessed_at
    return validated


def bind_assessment_record(
    task: dict[str, object],
    assessment: dict[str, object],
) -> dict[str, object]:
    """Return a deep-copied task with a validated, exact assessment binding."""

    if str(task.get("state") or "") != "MenxiaReview":
        raise ValueError("assessment_binding_requires_menxia_review")
    bound = deepcopy(task)
    source_envelope = deepcopy(assessment)
    validated = validate_runtime_assessment_binding(bound, source_envelope)
    source_envelope_ref = _source_envelope_ref(source_envelope)
    existing = bound.get("assessment_binding")
    if isinstance(existing, dict) and existing:
        _revalidate_stored_assessment_binding(bound)
        if (
            existing.get("source_envelope_ref") == source_envelope_ref
            and existing.get("source_envelope") == source_envelope
        ):
            return bound
        raise ValueError("assessment_binding_conflict")
    completable = validated["gate"] in COMPLETABLE_OUTCOME_ASSESSMENT_GATES
    bound["outcome_assessment"] = {
        "schema": OUTCOME_ASSESSMENT_SCHEMA,
        "gate": validated["gate"],
        "reasons": deepcopy(validated["reasons"]),
        "residual_gaps": deepcopy(validated["residual_gaps"]),
        "residual_gaps": validated["residual_gaps"],
        "outcome": None,
    }
    bound["assessment_binding"] = deepcopy(validated)
    bound["assessment_binding"]["status"] = (
        "VERIFIED" if completable else "NONCOMPLETABLE"
    )
    bound["assessment_binding"]["source_envelope"] = source_envelope
    bound["assessment_binding"]["source_envelope_ref"] = source_envelope_ref
    bound["completion"] = (
        {
            "status": "ASSESSMENT_BOUND",
            "outcome_status": (
                "DONE_WITH_CONCERNS"
                if validated["gate"] == "PASSED_WITH_CONCERNS"
                else "DONE"
            ),
            "residual_gaps": deepcopy(validated["residual_gaps"]),
            "residual_gaps": validated["residual_gaps"],
        }
        if completable
        else {"status": "NONCOMPLETABLE_ASSESSMENT"}
    )
    return bound


def validate_checkpoint_receipt(
    task: dict[str, object],
    receipt: dict[str, object],
) -> dict[str, object]:
    """Validate a checkpoint receipt against its exact stored task binding."""

    if not isinstance(receipt, dict):
        raise ValueError("checkpoint_receipt_must_be_object")
    validated = deepcopy(receipt)
    receipt_fields = set(validated)
    if receipt_fields - CHECKPOINT_RECEIPT_FIELDS - CHECKPOINT_RECEIPT_CONCERN_FIELDS:
        raise ValueError("checkpoint_receipt_unknown_fields")
    if CHECKPOINT_RECEIPT_FIELDS - receipt_fields:
        raise ValueError("checkpoint_receipt_missing_fields")
    if validated.get("schema") != CHECKPOINT_RECEIPT_SCHEMA:
        raise ValueError("invalid_checkpoint_receipt_schema")
    receipt_id = str(validated.get("receipt_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", receipt_id):
        raise ValueError("invalid_checkpoint_receipt_id")
    consumed = task.get("consumed_checkpoint_receipt_ids")
    if consumed is not None and not isinstance(consumed, list):
        raise ValueError("invalid_consumed_checkpoint_receipts")
    if receipt_id in (consumed or []):
        raise ValueError("checkpoint_receipt_already_consumed")
    if str(task.get("state") or "") != "ShiguanRecorded":
        raise ValueError("checkpoint_receipt_requires_shiguan_recorded")
    if validated.get("task_id") != task.get("task_id"):
        raise ValueError("checkpoint_receipt_task_mismatch")
    if validated.get("charter_revision") != task.get("charter_revision"):
        raise ValueError("checkpoint_receipt_revision_mismatch")
    if not isinstance(validated.get("case_ref"), Mapping) or case_reference(validated["case_ref"]) != case_reference(task):
        raise ValueError("checkpoint_receipt_case_reference_mismatch")
    binding = _revalidate_stored_assessment_binding(task)
    assessment_ref = str(validated.get("assessment_ref") or "").strip()
    if not assessment_ref:
        raise ValueError("invalid_checkpoint_assessment_ref")
    if assessment_ref != binding.get("assessment_ref"):
        raise ValueError("checkpoint_receipt_assessment_mismatch")
    checkpoint = task.get("shiguan_checkpoint")
    if not isinstance(checkpoint, dict) or checkpoint.get("status") != "VERIFIED":
        raise ValueError("shiguan_checkpoint_not_verified")
    if checkpoint.get("receipt_id") != receipt_id:
        raise ValueError("checkpoint_receipt_id_mismatch")
    record_ref = str(validated.get("record_ref") or "").strip()
    if not record_ref:
        raise ValueError("invalid_checkpoint_record_ref")
    if record_ref != str(checkpoint.get("record_ref") or ""):
        raise ValueError("checkpoint_receipt_record_mismatch")
    archive_path = str(validated.get("archive_path") or "")
    if not archive_path:
        raise ValueError("invalid_checkpoint_archive_path")
    if archive_path != checkpoint.get("archive_path"):
        raise ValueError("checkpoint_receipt_path_mismatch")
    recorded_at = _aware_timestamp(
        validated.get("recorded_at"), "invalid_checkpoint_recorded_at"
    )
    checkpoint_recorded_at = _aware_timestamp(
        checkpoint.get("recorded_at"), "invalid_checkpoint_recorded_at"
    )
    if recorded_at != checkpoint_recorded_at:
        raise ValueError("checkpoint_receipt_time_mismatch")
    concern_fields = receipt_fields & CHECKPOINT_RECEIPT_CONCERN_FIELDS
    if binding.get("gate") == "PASSED_WITH_CONCERNS":
        if concern_fields != CHECKPOINT_RECEIPT_CONCERN_FIELDS:
            raise ValueError("checkpoint_receipt_concerns_missing")
        residual_gaps = _validated_residual_gaps(
            validated.get("residual_gaps"), gate="PASSED_WITH_CONCERNS"
        )
        if residual_gaps != binding.get("residual_gaps"):
            raise ValueError("checkpoint_receipt_residual_gaps_mismatch")
        if checkpoint.get("residual_gaps") != residual_gaps:
            raise ValueError("shiguan_checkpoint_residual_gaps_mismatch")
        validated["residual_gaps"] = residual_gaps
    elif concern_fields:
        raise ValueError("checkpoint_receipt_unexpected_concerns")
    producer_receipt = checkpoint.get("producer_receipt")
    producer_receipt_ref = checkpoint.get("producer_receipt_ref")
    if not isinstance(producer_receipt, dict) or not isinstance(
        producer_receipt_ref, str
    ) or not producer_receipt_ref.strip():
        raise ValueError("archive_producer_evidence_missing")
    validated_producer_receipt = _validated_archive_producer_receipt(
        producer_receipt
    )
    if validated_producer_receipt.get("record_ref") != producer_receipt_ref:
        raise ValueError("archive_producer_receipt_ref_mismatch")
    if (
        validated_producer_receipt.get("receipt_id") != checkpoint.get("receipt_id")
        or validated_producer_receipt.get("record_ref")
        != checkpoint.get("record_ref")
        or validated_producer_receipt.get("path") != checkpoint.get("archive_path")
        or validated_producer_receipt.get("recorded_at")
        != checkpoint.get("recorded_at")
    ):
        raise ValueError("archive_producer_checkpoint_mismatch")
    _validate_archive_producer_residual_gaps(
        validated_producer_receipt, binding
    )
    validated["case_ref"] = case_reference(task)
    validated["assessment_ref"] = assessment_ref
    validated["record_ref"] = record_ref
    validated["recorded_at"] = recorded_at
    return validated


def _ledger_sha256(value: bytes | None) -> str:
    return hashlib.sha256(value if value is not None else b"").hexdigest()


def _encode_preimage(value: bytes | None) -> str:
    return base64.b64encode(value or b"").decode("ascii")


def _completion_marker_checksum(marker: dict[str, object]) -> str:
    core = {key: value for key, value in marker.items() if key != "marker_sha256"}
    payload = json.dumps(
        core, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_completion_transaction_marker(path: Path, marker: dict[str, object]) -> None:
    prepared = deepcopy(marker)
    prepared["marker_sha256"] = _completion_marker_checksum(prepared)
    atomic_write_text(
        path,
        json.dumps(prepared, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _remove_completion_transaction_marker(path: Path) -> None:
    path.unlink(missing_ok=True)


def _validated_completion_transaction_marker(path: Path) -> dict[str, object]:
    try:
        marker = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_completion_transaction_marker") from exc
    required = {
        "schema", "task_id", "receipt_id", "phase",
        "tasks_preimage_exists", "tasks_preimage_b64", "tasks_preimage_sha256",
        "events_preimage_exists", "events_preimage_b64", "events_preimage_sha256",
        "tasks_post_sha256", "events_post_sha256", "marker_sha256",
    }
    if not isinstance(marker, dict) or set(marker) != required:
        raise ValueError("invalid_completion_transaction_marker")
    if marker.get("schema") != COMPLETION_TRANSACTION_SCHEMA:
        raise ValueError("invalid_completion_transaction_marker")
    if marker.get("phase") not in {"PREPARED", "TASK_WRITTEN", "EVENT_WRITTEN"}:
        raise ValueError("invalid_completion_transaction_marker")
    if marker.get("marker_sha256") != _completion_marker_checksum(marker):
        raise ValueError("completion_transaction_marker_integrity")
    for prefix in ("tasks", "events"):
        exists = marker.get(f"{prefix}_preimage_exists")
        encoded = marker.get(f"{prefix}_preimage_b64")
        expected = marker.get(f"{prefix}_preimage_sha256")
        if not isinstance(exists, bool) or not isinstance(encoded, str):
            raise ValueError("invalid_completion_transaction_marker")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ValueError("completion_transaction_marker_integrity") from exc
        if not exists and decoded:
            raise ValueError("completion_transaction_marker_integrity")
        if not isinstance(expected, str) or _ledger_sha256(decoded) != expected:
            raise ValueError("completion_transaction_marker_integrity")
    if not isinstance(marker.get("task_id"), str) or not marker["task_id"]:
        raise ValueError("invalid_completion_transaction_marker")
    if not isinstance(marker.get("receipt_id"), str) or not marker["receipt_id"]:
        raise ValueError("invalid_completion_transaction_marker")
    return marker


def recover_completion_transaction(marker_path: Path) -> str:
    """Recover or finalize one durable completion marker without event-ledger help."""

    marker = _validated_completion_transaction_marker(marker_path)
    phase = marker["phase"]
    current_tasks = tasks_path().read_bytes() if tasks_path().exists() else None
    current_events = events_path().read_bytes() if events_path().exists() else None
    if (
        phase == "EVENT_WRITTEN"
        and marker.get("tasks_post_sha256") == _ledger_sha256(current_tasks)
        and marker.get("events_post_sha256") == _ledger_sha256(current_events)
    ):
        _remove_completion_transaction_marker(marker_path)
        return "FINALIZED"
    tasks_preimage = base64.b64decode(str(marker["tasks_preimage_b64"]), validate=True)
    events_preimage = base64.b64decode(str(marker["events_preimage_b64"]), validate=True)
    _restore_ledger_preimage(
        tasks_path(), tasks_preimage if marker["tasks_preimage_exists"] else None
    )
    _restore_ledger_preimage(
        events_path(), events_preimage if marker["events_preimage_exists"] else None
    )
    _remove_completion_transaction_marker(marker_path)
    return "ROLLED_BACK"


def complete_task_atomically(args: argparse.Namespace) -> TransitionResult:
    """Complete one task under one lock, with exact ledger rollback on failure."""

    if args.actor not in OFFICES:
        raise ValueError("unknown_actor_office")
    receipt = _json_object_from_args(
        args, "receipt", "receipt_file", "checkpoint receipt"
    )
    with runtime_lock():
        marker_path = completion_transaction_path(args.task_id)
        if marker_path.exists():
            recover_completion_transaction(marker_path)
        task_preimage = tasks_path().read_bytes() if tasks_path().exists() else None
        event_preimage = events_path().read_bytes() if events_path().exists() else None
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        if task.get("charter_revision") != args.expected_revision:
            raise ValueError("stale_charter_revision")
        supplied_case_ref = _required_context_object(getattr(args, "case_ref", None), "case_ref_required")
        if case_reference(supplied_case_ref) != case_reference(task):
            raise ValueError("stale_charter_case_reference")
        _revalidate_stored_assessment_binding(task)
        binding = task["assessment_binding"]
        if (
            binding.get("status") != "VERIFIED"
            or binding.get("gate") not in COMPLETABLE_OUTCOME_ASSESSMENT_GATES
        ):
            raise ValueError("outcome_assessment_not_completable")
        checkpoint = task.get("shiguan_checkpoint")
        if not isinstance(checkpoint, dict) or checkpoint.get("status") != "VERIFIED":
            raise ValueError("shiguan_checkpoint_not_verified")
        validated_receipt = validate_checkpoint_receipt(task, receipt)
        completion = task.get("completion")
        if not isinstance(completion, dict) or completion.get("status") != "READY":
            raise ValueError("completion_not_ready")
        completed = deepcopy(task)
        completed["state"] = "Done"
        completed["owner"] = args.actor
        completed["updated_at"] = now_text()
        completed["last_evidence"] = args.evidence
        completed["completion"] = {
            "status": "COMPLETED",
            "receipt_id": validated_receipt["receipt_id"],
            "completed_at": completed["updated_at"],
            "outcome_status": (
                "DONE_WITH_CONCERNS"
                if binding.get("gate") == "PASSED_WITH_CONCERNS"
                else "DONE"
            ),
            "completion_source_ref": binding.get("completion_source_ref"),
            "residual_gaps": deepcopy(binding.get("residual_gaps")),
            "residual_gaps": binding.get("residual_gaps"),
        }
        consumed = list(completed.get("consumed_checkpoint_receipt_ids") or [])
        consumed.append(validated_receipt["receipt_id"])
        completed["consumed_checkpoint_receipt_ids"] = consumed
        event = make_event(
            completed,
            "complete",
            "ShiguanRecorded",
            "Done",
            args.actor,
            args.evidence,
            args.note,
        )
        event["receipt_id"] = validated_receipt["receipt_id"]
        event["assessment_ref"] = validated_receipt["assessment_ref"]
        event["record_ref"] = validated_receipt["record_ref"]
        event["completion_sequence"] = 2
        event["outcome_status"] = completed["completion"]["outcome_status"]
        event["completion_source_ref"] = completed["completion"]["completion_source_ref"]
        event["residual_gaps"] = completed["completion"]["residual_gaps"]
        completed["completion"]["proof"] = _completion_proof(
            completed, validated_receipt, event
        )
        tasks[args.task_id] = completed
        marker: dict[str, object] = {
            "schema": COMPLETION_TRANSACTION_SCHEMA,
            "task_id": str(args.task_id),
            "receipt_id": str(validated_receipt["receipt_id"]),
            "phase": "PREPARED",
            "tasks_preimage_exists": task_preimage is not None,
            "tasks_preimage_b64": _encode_preimage(task_preimage),
            "tasks_preimage_sha256": _ledger_sha256(task_preimage),
            "events_preimage_exists": event_preimage is not None,
            "events_preimage_b64": _encode_preimage(event_preimage),
            "events_preimage_sha256": _ledger_sha256(event_preimage),
            "tasks_post_sha256": "",
            "events_post_sha256": "",
        }
        _write_completion_transaction_marker(marker_path, marker)
        try:
            write_tasks(tasks)
            marker["phase"] = "TASK_WRITTEN"
            marker["tasks_post_sha256"] = _ledger_sha256(tasks_path().read_bytes())
            _write_completion_transaction_marker(marker_path, marker)
            append_event(event)
            marker["phase"] = "EVENT_WRITTEN"
            marker["events_post_sha256"] = _ledger_sha256(events_path().read_bytes())
            _write_completion_transaction_marker(marker_path, marker)
            _remove_completion_transaction_marker(marker_path)
        except Exception:
            if marker_path.exists():
                recover_completion_transaction(marker_path)
            raise
    return TransitionResult(completed, event)


def _restore_ledger_preimage(path: Path, preimage: bytes | None) -> None:
    if preimage is None:
        if path.exists():
            path.unlink()
        return
    atomic_write_text(path, preimage.decode("utf-8"))


class SimulatedResultRecoveryCrash(RuntimeError):
    """Synthetic killpoint used only by isolated result-recovery checks."""


_RESULT_RECOVERY_PRIVATE_KEY_TOKENS = frozenset(
    {
        "raw", "raw_body", "body", "prompt", "transcript", "private",
        "private_body", "pending", "secret", "credential", "token", "password",
    }
)


def _journal_preimage_privacy_violation(payload: bytes | None) -> str | None:
    """Return the first private-key/path token found in a ledger preimage."""
    if payload is None:
        return None
    text = payload.decode("utf-8", errors="replace")
    if not text.strip():
        return None
    documents: list[object] = []
    try:
        documents.append(json.loads(text))
    except Exception:
        # tasks.json is one JSON document; the event ledger is JSONL with one
        # JSON object per line.  Scan every parseable line instead of treating
        # the whole JSONL file as a single undecodable document.
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                documents.append(json.loads(line))
            except Exception:
                continue
    for data in documents:
        found = _scan_ledger_preimage(data)
        if found is not None:
            return found
    return None


def _scan_ledger_preimage(value: object) -> str | None:
    def scan(node: object) -> str | None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                normalized = str(key).strip().casefold()
                if normalized in _RESULT_RECOVERY_PRIVATE_KEY_TOKENS:
                    return normalized
                if isinstance(child, str):
                    lowered = child.casefold()
                    if (
                        "pending/" in lowered
                        or "/private/" in lowered
                        or "private/" in lowered
                    ):
                        return normalized
                found = scan(child)
                if found is not None:
                    return found
        elif isinstance(node, (list, tuple)):
            for child in node:
                found = scan(child)
                if found is not None:
                    return found
        return None

    return scan(value)


def _result_recovery_commit_locked(
    *,
    operation_id: str,
    payload_digest: str,
    task_id: str,
    tasks: dict[str, dict[str, Any]],
    event: dict[str, Any],
    receipt: Mapping[str, object],
    killpoint: str = "",
) -> None:
    """Commit one recovery mutation with a disposable three-phase journal.

    The journal is deliberately separate from task/event authority.  It only
    preserves preimages and phase metadata needed to replay or roll back a
    single operation under the existing runtime lock.
    """
    marker_file = result_recovery_marker_path(operation_id)
    if marker_file.exists():
        raise ValueError("result_recovery_journal_corrupt")
    allowed_killpoints = {
        "", "PREPARED", "TASK_WRITTEN", "EVENT_WRITTEN",
        "after_prepared", "after_task_write", "after_event_write",
    }
    if killpoint not in allowed_killpoints:
        raise ValueError("result_recovery_killpoint_invalid")
    tasks_preimage = tasks_path().read_bytes() if tasks_path().exists() else None
    events_preimage = events_path().read_bytes() if events_path().exists() else None
    for label, payload in (("tasks", tasks_preimage), ("events", events_preimage)):
        violation = _journal_preimage_privacy_violation(payload)
        if violation is not None:
            raise ValueError(
                f"result_recovery_privacy_gate_failed:{label}:{violation}"
            )
    event = dict(event)
    event["note"] = scrub_agent_provider_detail(event.get("note"))
    marker: dict[str, object] = {
        "schema": RESULT_RECOVERY_OPERATION_SCHEMA,
        "operation_id": operation_id,
        "payload_sha256": payload_digest,
        "task_id": task_id,
        "phase": "PREPARED",
        "tasks_preimage_exists": tasks_preimage is not None,
        "tasks_preimage_b64": base64.b64encode(tasks_preimage or b"").decode("ascii"),
        "events_preimage_exists": events_preimage is not None,
        "events_preimage_b64": base64.b64encode(events_preimage or b"").decode("ascii"),
        "receipt": deepcopy(dict(receipt)),
        "event_id": event.get("event_id"),
        "created_at": now_text(),
    }
    write_operation_json(marker_file, marker)
    if killpoint in {"PREPARED", "after_prepared"}:
        raise SimulatedResultRecoveryCrash("PREPARED")
    write_tasks(tasks)
    marker["phase"] = "TASK_WRITTEN"
    marker["tasks_post_sha256"] = _ledger_sha256(tasks_path().read_bytes())
    write_operation_json(marker_file, marker)
    if killpoint in {"TASK_WRITTEN", "after_task_write"}:
        raise SimulatedResultRecoveryCrash("TASK_WRITTEN")
    append_event(event)
    marker["phase"] = "EVENT_WRITTEN"
    marker["events_post_sha256"] = _ledger_sha256(events_path().read_bytes())
    write_operation_json(marker_file, marker)
    if killpoint in {"EVENT_WRITTEN", "after_event_write"}:
        raise SimulatedResultRecoveryCrash("EVENT_WRITTEN")
    marker_file.unlink(missing_ok=True)


def recover_result_recovery_operation(operation_id: object) -> dict[str, object]:
    canonical = str(operation_id or "").strip()
    if not canonical:
        raise ValueError("result_recovery_operation_id_required")
    with runtime_lock():
        marker_file = result_recovery_marker_path(canonical)
        marker = load_operation_json(marker_file)
        if marker is None:
            tasks = load_tasks()
            for task in tasks.values():
                operations = task.get("result_recovery_operations")
                if isinstance(operations, dict) and canonical in operations:
                    operation = operations[canonical]
                    if isinstance(operation, dict) and isinstance(operation.get("receipt"), dict):
                        return {
                            "schema": RESULT_RECOVERY_JOURNAL_SCHEMA,
                            "operation_id": canonical,
                            "outcome": "REPLAYED",
                            "receipt": deepcopy(operation["receipt"]),
                        }
            raise ValueError("result_recovery_journal_missing")
        if marker.get("schema") != RESULT_RECOVERY_OPERATION_SCHEMA or marker.get("operation_id") != canonical:
            raise ValueError("result_recovery_journal_corrupt")
        phase = str(marker.get("phase") or "")
        try:
            tasks_preimage = base64.b64decode(str(marker.get("tasks_preimage_b64") or ""), validate=True)
            events_preimage = base64.b64decode(str(marker.get("events_preimage_b64") or ""), validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("result_recovery_journal_corrupt") from exc
        if phase == "EVENT_WRITTEN":
            current_tasks = tasks_path().read_bytes() if tasks_path().exists() else None
            current_events = events_path().read_bytes() if events_path().exists() else None
            if (
                marker.get("tasks_post_sha256") != _ledger_sha256(current_tasks)
                or marker.get("events_post_sha256") != _ledger_sha256(current_events)
                or not isinstance(marker.get("receipt"), dict)
            ):
                raise ValueError("result_recovery_journal_corrupt")
            marker_file.unlink(missing_ok=True)
            return {
                "schema": RESULT_RECOVERY_JOURNAL_SCHEMA,
                "operation_id": canonical,
                "outcome": "FINALIZE",
                "receipt": deepcopy(marker["receipt"]),
            }
        if phase not in {"PREPARED", "TASK_WRITTEN"}:
            raise ValueError("result_recovery_journal_corrupt")
        _restore_ledger_preimage(
            tasks_path(),
            tasks_preimage if marker.get("tasks_preimage_exists") else None,
        )
        _restore_ledger_preimage(
            events_path(),
            events_preimage if marker.get("events_preimage_exists") else None,
        )
        marker_file.unlink(missing_ok=True)
        return {
            "schema": RESULT_RECOVERY_JOURNAL_SCHEMA,
            "operation_id": canonical,
            "outcome": "ROLLBACK",
            "receipt": None,
        }


class SimulatedPairedLedgerCrash(RuntimeError):
    """Synthetic killpoint used only by isolated recovery checks."""


class SimulatedDecreeOpenCrash(RuntimeError):
    """Synthetic killpoint used only by isolated decree allocation checks."""


class SimulatedCloseoutCrash(RuntimeError):
    """Synthetic killpoint used only by isolated closeout recovery checks."""


def _operation_request_payload(
    args: argparse.Namespace,
    label: str,
) -> dict[str, object] | None:
    replay_only = bool(getattr(args, "replay_only", False))
    direct = getattr(args, "payload", None)
    payload_file = getattr(args, "payload_file", None)
    if replay_only:
        if direct is not None or payload_file:
            raise ValueError("operation_replay_requires_reference_only")
        return None
    return _json_object_from_args(args, "payload", "payload_file", label)


def _marker_bytes(value: object, field: str) -> bytes | None:
    if not isinstance(value, str):
        raise ValueError(f"operation_recovery_marker_{field}_invalid")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"operation_recovery_marker_{field}_invalid") from exc


def _marker_preimage(marker: Mapping[str, object], prefix: str) -> bytes | None:
    exists = marker.get(f"{prefix}_preimage_exists")
    encoded = marker.get(f"{prefix}_preimage_b64")
    if not isinstance(exists, bool):
        raise ValueError("operation_recovery_marker_corrupt")
    decoded = _marker_bytes(encoded, f"{prefix}_preimage_b64")
    if not exists and decoded:
        raise ValueError("operation_recovery_marker_corrupt")
    return decoded if exists else None


def _marker_postimage(marker: Mapping[str, object], prefix: str) -> bytes | None:
    exists = marker.get(f"{prefix}_postimage_exists")
    encoded = marker.get(f"{prefix}_postimage_b64")
    if not isinstance(exists, bool):
        raise ValueError("operation_recovery_marker_corrupt")
    decoded = _marker_bytes(encoded, f"{prefix}_postimage_b64")
    if not exists and decoded:
        raise ValueError("operation_recovery_marker_corrupt")
    return decoded if exists else None


def _marker_operation_state_matches(
    marker: Mapping[str, object],
    *,
    require_event: bool,
) -> bool:
    try:
        current_tasks = tasks_path().read_bytes() if tasks_path().exists() else None
        current_events = events_path().read_bytes() if events_path().exists() else None
        expected_tasks = _marker_postimage(marker, "tasks")
        expected_events = (
            _marker_postimage(marker, "events") if require_event else None
        )
    except (OSError, ValueError):
        return False
    if current_tasks != expected_tasks or (
        require_event and current_events != expected_events
    ):
        return False
    if not require_event:
        return True
    try:
        tasks_value = json.loads((current_tasks or b"{}").decode("utf-8"))
        if not isinstance(tasks_value, dict):
            return False
        task_id = str(marker.get("task_id") or "")
        operation_id = str(marker.get("operation_id") or "")
        task = tasks_value.get(task_id)
        if not isinstance(task, dict):
            return False
        operations = task.get("operations")
        operation = operations.get(operation_id) if isinstance(operations, dict) else None
        if not isinstance(operation, dict):
            return False
        if operation.get("operation_binding") != marker.get("operation_binding"):
            return False
        receipt = marker.get("receipt")
        if not isinstance(receipt, dict) or operation.get("receipt") != receipt:
            return False
        expected_revision = marker.get("committed_task_revision")
        if expected_revision is not None and task.get("task_revision") != expected_revision:
            return False
        events: list[dict[str, object]] = []
        for line in (current_events or b"").decode("utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                events.append(value)
        event_id = str(marker.get("event_id") or receipt.get("event_id") or "")
        matches = [
            event for event in events
            if event.get("task_id") == task_id
            and event.get("operation_id") == operation_id
            and event.get("event_id") == event_id
        ]
        return len(matches) == 1
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return False


def _operation_marker_for_recovery(
    operation_id: str,
    *,
    legacy_locator: object | None = None,
) -> tuple[Path | None, dict[str, object] | None]:
    """Resolve a marker only for an explicit recovery request.

    The v2 path is canonical.  Legacy records have no trustworthy operation-id
    filename, so an explicit relative locator is required before reading one.
    Without that locator, only names are enumerated under the same bounded
    legacy-store limit; startup never scans this directory and legacy records
    remain read-only.
    """

    canonical = canonical_operation_id(operation_id)
    current = operation_marker_path(runtime_root(), canonical)

    def load_requested(path: Path, *, locator_supplied: bool) -> tuple[Path, dict[str, object]]:
        try:
            if not path.resolve().is_relative_to(runtime_root().resolve()):
                raise ValueError("operation_recovery_marker_path_escape")
        except OSError as exc:
            raise ValueError("operation_recovery_marker_path_invalid") from exc
        try:
            value = load_operation_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("operation_recovery_marker_corrupt") from exc
        if value is None:
            raise ValueError(
                "legacy_marker_locator_missing"
                if locator_supplied
                else "operation_recovery_marker_missing"
            )
        if value.get("operation_id") != canonical:
            raise ValueError("legacy_marker_locator_operation_mismatch")
        return path, value

    if current.is_file():
        return load_requested(current, locator_supplied=False)
    legacy_root = runtime_root() / "operation-markers"
    if not legacy_root.is_dir():
        return None, None

    if legacy_locator is not None:
        raw_locator = str(legacy_locator).strip()
        locator = Path(raw_locator)
        if (
            not raw_locator
            or any(character in raw_locator for character in "\x00\r\n")
            or locator.is_absolute()
            or locator.name != raw_locator
            or locator.name in {".", ".."}
            or locator.suffix.casefold() != ".json"
        ):
            raise ValueError("legacy_marker_locator_invalid")
        locator_path = legacy_root / locator.name
        try:
            if locator_path.resolve().parent != legacy_root.resolve():
                raise ValueError("legacy_marker_locator_invalid")
        except OSError as exc:
            raise ValueError("legacy_marker_locator_invalid") from exc
        return load_requested(locator_path, locator_supplied=True)

    requested = legacy_root / f"{canonical}.json"
    if requested.is_file():
        return load_requested(requested, locator_supplied=False)

    scanned = 0
    try:
        for candidate in legacy_root.iterdir():
            if candidate.name == OPERATION_V2_NAMESPACE:
                continue
            scanned += 1
            if scanned >= LEGACY_OPERATION_FILENAME_SCAN_LIMIT:
                raise ValueError("legacy_marker_locator_required")
    except OSError as exc:
        raise ValueError("legacy_marker_locator_required") from exc
    if scanned:
        raise ValueError("legacy_marker_locator_required")
    return None, None


def _legacy_operation_artifact_for_mutation(
    operation_id: str,
    *,
    allow_reference: bool = False,
) -> tuple[Path, dict[str, object]] | None:
    """Reject a legacy store using names only, without reading other bodies.

    Historical markers/journals used SHA-derived filenames.  The migration
    cannot reimplement that naming algorithm, so a non-canonical JSON filename
    is conservatively treated as a legacy store and requires explicit recovery.
    Only the requested canonical path may be parsed for a legacy schema.
    """

    canonical = canonical_operation_id(operation_id)
    for directory, legacy_schema in ((
        "operation-markers", LEGACY_MARKER_SCHEMA
    ), ("operation-journal", LEGACY_JOURNAL_SCHEMA)):
        root = runtime_root() / directory
        if not root.is_dir():
            continue
        requested = root / f"{canonical}.json"
        if requested.is_file():
            if not allow_reference:
                return requested, {"schema": legacy_schema, "store_present": True}
            try:
                value = load_operation_json(requested)
            except (OSError, ValueError, json.JSONDecodeError):
                return requested, {"schema": "corrupt", "requested": True}
            if isinstance(value, dict) and value.get("schema") == legacy_schema:
                return requested, value
            if allow_reference:
                return None
        scanned = 0
        try:
            candidates = root.iterdir()
            for candidate in candidates:
                if candidate.name == OPERATION_V2_NAMESPACE:
                    continue
                scanned += 1
                if scanned >= LEGACY_OPERATION_FILENAME_SCAN_LIMIT:
                    return root, {
                        "schema": legacy_schema,
                        "store_present": True,
                        "scan_limit": LEGACY_OPERATION_FILENAME_SCAN_LIMIT,
                    }
                if candidate.name == requested.name:
                    continue
                if not candidate.is_file() or candidate.suffix.casefold() != ".json":
                    continue
                try:
                    candidate_operation_id = canonical_operation_id(candidate.stem)
                except ValueError:
                    candidate_operation_id = ""
                if candidate_operation_id != candidate.stem:
                    return candidate, {"schema": legacy_schema, "store_present": True}
        except OSError:
            return root, {"schema": legacy_schema, "store_present": True}
    return None


def _paired_ledger_commit(
    *,
    operation_binding: Mapping[str, object],
    tasks: dict[str, dict[str, Any]],
    event: dict[str, Any],
    receipt: dict[str, object],
    killpoint: str = "",
) -> None:
    binding = normalize_operation_binding(
        operation_binding,
        operation_id=operation_binding.get("operation_id"),
    )
    operation_id = str(binding["operation_id"])
    task_id = str(binding["task_id"])
    marker_file = operation_marker_path(runtime_root(), operation_id)
    if marker_file.exists():
        raise ValueError("operation_recovery_required")
    tasks_preimage = tasks_path().read_bytes() if tasks_path().exists() else None
    events_preimage = events_path().read_bytes() if events_path().exists() else None
    marker: dict[str, object] = {
        "schema": MARKER_SCHEMA,
        "operation_id": operation_id,
        "operation_binding": binding,
        "task_id": task_id,
        "phase": "PREPARED",
        "tasks_preimage_exists": tasks_preimage is not None,
        "tasks_preimage_b64": base64.b64encode(tasks_preimage or b"").decode("ascii"),
        "events_preimage_exists": events_preimage is not None,
        "events_preimage_b64": base64.b64encode(events_preimage or b"").decode("ascii"),
        "tasks_postimage_exists": False,
        "tasks_postimage_b64": "",
        "events_postimage_exists": False,
        "events_postimage_b64": "",
        "receipt": deepcopy(receipt),
        "receipt_ref": _operation_receipt_ref(receipt),
        "event_id": event.get("event_id"),
        "committed_task_revision": receipt.get("task_revision"),
        "created_at": now_text(),
    }
    write_operation_json(marker_file, marker)
    _write_operation_journal(binding=binding, phase="PREPARED", receipt=None, updated_at=now_text(), event_id=str(event.get("event_id") or ""))
    write_tasks(tasks)
    marker["phase"] = "TASK_WRITTEN"
    tasks_postimage = tasks_path().read_bytes() if tasks_path().exists() else None
    marker["tasks_postimage_exists"] = tasks_postimage is not None
    marker["tasks_postimage_b64"] = base64.b64encode(tasks_postimage or b"").decode("ascii")
    write_operation_json(marker_file, marker)
    _write_operation_journal(binding=binding, phase="TASK_WRITTEN", receipt=None, updated_at=now_text(), event_id=str(event.get("event_id") or ""))
    if killpoint == "after_task_write":
        raise SimulatedPairedLedgerCrash("after_task_write")
    append_event(event)
    marker["phase"] = "EVENT_WRITTEN"
    events_postimage = events_path().read_bytes() if events_path().exists() else None
    marker["events_postimage_exists"] = events_postimage is not None
    marker["events_postimage_b64"] = base64.b64encode(events_postimage or b"").decode("ascii")
    write_operation_json(marker_file, marker)
    _write_operation_journal(binding=binding, phase="EVENT_WRITTEN", receipt=None, updated_at=now_text(), event_id=str(event.get("event_id") or ""))
    if killpoint == "after_event_write":
        raise SimulatedPairedLedgerCrash("after_event_write")
    _write_operation_journal(
        binding=binding,
        phase="COMMITTED",
        receipt=receipt,
        updated_at=now_text(),
        committed_task_revision=receipt.get("task_revision")
        if isinstance(receipt.get("task_revision"), int)
        else None,
        event_id=str(event.get("event_id") or ""),
    )
    remove_operation_marker(runtime_root(), operation_id)


def recover_paired_operation(
    operation_id: object,
    *,
    legacy_locator: object | None = None,
) -> dict[str, object]:
    canonical = canonical_operation_id(operation_id)
    with runtime_lock():
        marker_file, marker = _operation_marker_for_recovery(
            canonical,
            legacy_locator=legacy_locator,
        )
        if marker is None:
            raise ValueError("operation_recovery_marker_missing")
        if marker_file is None:
            raise ValueError("operation_recovery_marker_missing")
        if marker.get("schema") == LEGACY_MARKER_SCHEMA:
            raise ValueError("LEGACY_READ_ONLY")
        if marker.get("schema") != MARKER_SCHEMA or marker.get("operation_id") != canonical:
            raise ValueError("operation_recovery_marker_corrupt")
        try:
            binding = normalize_operation_binding(
                marker.get("operation_binding"), operation_id=canonical
            )
        except ValueError as exc:
            raise ValueError("operation_recovery_marker_corrupt") from exc
        task_id = str(marker.get("task_id") or "")
        if task_id != str(binding.get("task_id") or ""):
            raise ValueError("RECOVERY_CONFLICT")
        phase = str(marker.get("phase") or "")
        receipt = marker.get("receipt")
        if phase == "EVENT_WRITTEN":
            if not isinstance(receipt, dict) or not _marker_operation_state_matches(marker, require_event=True):
                raise ValueError("RECOVERY_CONFLICT")
            _write_operation_journal(
                binding=binding,
                phase="COMMITTED",
                receipt=receipt,
                updated_at=now_text(),
                committed_task_revision=receipt.get("task_revision")
                if isinstance(receipt.get("task_revision"), int)
                else None,
                event_id=str(marker.get("event_id") or receipt.get("event_id") or ""),
            )
            marker_file.unlink(missing_ok=True)
            return {
                "operation_id": canonical,
                "outcome": "FINALIZE",
                "receipt": receipt,
            }
        if phase not in {"PREPARED", "TASK_WRITTEN"}:
            raise ValueError("operation_recovery_phase_invalid")
        tasks_preimage = _marker_preimage(marker, "tasks")
        events_preimage = _marker_preimage(marker, "events")
        if phase == "PREPARED":
            current_tasks = tasks_path().read_bytes() if tasks_path().exists() else None
            current_events = events_path().read_bytes() if events_path().exists() else None
            if current_tasks != tasks_preimage or current_events != events_preimage:
                raise ValueError("RECOVERY_CONFLICT")
        else:
            if not _marker_operation_state_matches(marker, require_event=False):
                raise ValueError("RECOVERY_CONFLICT")
            current_events = events_path().read_bytes() if events_path().exists() else None
            if current_events != events_preimage:
                raise ValueError("RECOVERY_CONFLICT")
        _restore_ledger_preimage(
            tasks_path(),
            tasks_preimage if marker.get("tasks_preimage_exists") else None,
        )
        _restore_ledger_preimage(
            events_path(),
            events_preimage if marker.get("events_preimage_exists") else None,
        )
        _write_operation_journal(binding=binding, phase="ROLLED_BACK", receipt=None, updated_at=now_text(), event_id=str(marker.get("event_id") or ""))
        marker_file.unlink(missing_ok=True)
        return {
            "operation_id": canonical,
            "outcome": "ROLLBACK",
            "receipt": None,
        }


def apply_synthetic_paired_operation(args: argparse.Namespace) -> dict[str, object]:
    operation_id = canonical_operation_id(args.operation_id)
    replay_only = bool(getattr(args, "replay_only", False))
    payload = _operation_request_payload(args, "operation payload")
    evidence = require_text(args.evidence, "evidence")
    if args.actor not in OFFICES:
        raise ValueError("unknown_actor_office")
    with runtime_lock():
        if operation_marker_path(runtime_root(), operation_id).exists():
            raise ValueError("operation_recovery_required")
        tasks = load_tasks()
        found = _find_task_operation(tasks, operation_id)
        if found is not None and found[0] != args.task_id:
            raise ValueError("operation_binding_conflict")
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        incoming_binding = _operation_binding(
            task,
            operation_id=operation_id,
            operation_kind="synthetic_paired",
            request_schema="court.operation.paired.v2",
            actor=args.actor,
            expected_task_revision=int(getattr(args, "expected_task_revision", 0) or 0),
            target_ref={"kind": "task_operation", "task_id": args.task_id},
        )
        operations = task.setdefault("operations", {})
        if not isinstance(operations, dict):
            raise ValueError("task_operation_ledger_corrupt")
        existing = operations.get(operation_id)
        if isinstance(existing, dict):
            stored_binding = _stored_operation_binding(
                {**existing, "operation_id": operation_id}
            )
            _require_operation_replay_mode(
                stored_binding=stored_binding,
                incoming_binding=incoming_binding,
                replay_only=replay_only,
                payload_present=payload is not None,
            )
            receipt = existing.get("receipt")
            if not isinstance(receipt, dict):
                raise ValueError("task_operation_receipt_corrupt")
            if existing.get("status") != "TASK_EVENT_COMMITTED":
                raise ValueError("operation_recovery_required")
            _write_operation_journal(
                binding=stored_binding,
                phase="COMMITTED",
                receipt=receipt,
                updated_at=now_text(),
                committed_task_revision=receipt.get("task_revision")
                if isinstance(receipt.get("task_revision"), int)
                else None,
                event_id=str(receipt.get("event_id") or ""),
            )
            return {
                "status": "REPLAYED",
                "operation_id": operation_id,
                "replay_reason": "REPLAYED_BODY_NOT_COMPARED",
                "receipt": receipt,
            }
        legacy_artifact = _legacy_operation_artifact_for_mutation(operation_id)
        if legacy_artifact is not None:
            raise ValueError(
                "legacy_store_present_requires_explicit_recovery"
                if legacy_artifact[1].get("store_present")
                else "LEGACY_READ_ONLY"
            )
        if replay_only:
            raise ValueError("operation_not_found")
        try:
            current_revision = int(task.get("task_revision") or 1)
        except (TypeError, ValueError) as exc:
            raise ValueError("task_revision_corrupt") from exc
        if current_revision != args.expected_task_revision:
            raise ValueError("expected_task_revision_conflict")
        next_revision = current_revision + 1
        created_at = now_text()
        event_id = "EVT-" + uuid.uuid4().hex.upper()
        receipt: dict[str, object] = {
            "schema": "court.operation.receipt.v1",
            "operation_id": operation_id,
            "task_id": args.task_id,
            "task_revision": next_revision,
            "event_id": event_id,
            "status": "TASK_EVENT_COMMITTED",
            "created_at": created_at,
        }
        operation_binding = _operation_binding(
            task,
            operation_id=operation_id,
            operation_kind="synthetic_paired",
            request_schema="court.operation.paired.v2",
            actor=args.actor,
            expected_task_revision=args.expected_task_revision,
            target_ref={"kind": "task_operation", "task_id": args.task_id},
        )
        operations[operation_id] = {
            "operation_id": operation_id,
            "operation_binding": operation_binding,
            "payload": deepcopy(payload),
            "status": "TASK_EVENT_COMMITTED",
            "receipt": deepcopy(receipt),
        }
        task["task_revision"] = next_revision
        task["updated_at"] = created_at
        task["last_evidence"] = evidence
        tasks[args.task_id] = task
        event = make_event(
            task,
            "synthetic_paired_operation",
            str(task.get("state") or "Pending"),
            str(task.get("state") or "Pending"),
            args.actor,
            evidence,
            args.note,
        )
        event.update(
            event_id=event_id,
            operation_id=operation_id,
            task_revision=next_revision,
        )
        _paired_ledger_commit(
            operation_binding=operation_binding,
            tasks=tasks,
            event=event,
            receipt=receipt,
            killpoint=str(getattr(args, "killpoint", "") or ""),
        )
    return {
        "status": "COMMITTED",
        "operation_id": operation_id,
        "receipt": receipt,
    }


def _find_task_operation(
    tasks: dict[str, dict[str, Any]],
    operation_id: str,
) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    found: tuple[str, dict[str, Any], dict[str, Any]] | None = None
    for task_id, task in tasks.items():
        operations = task.get("operations")
        if not isinstance(operations, dict):
            continue
        operation = operations.get(operation_id)
        if not isinstance(operation, dict):
            continue
        if found is not None:
            raise ValueError("operation_id_not_globally_unique")
        found = (task_id, task, operation)
    return found


def _decree_daily_sequence(
    tasks: dict[str, dict[str, Any]],
    date_key: str,
) -> int:
    maximum = 0
    for task in tasks.values():
        operations = task.get("operations")
        if not isinstance(operations, dict):
            continue
        for operation in operations.values():
            if not isinstance(operation, dict) or operation.get("kind") != "decree_open":
                continue
            receipt = operation.get("receipt")
            if not isinstance(receipt, dict) or receipt.get("date_key") != date_key:
                continue
            sequence = receipt.get("daily_sequence")
            if isinstance(sequence, int) and not isinstance(sequence, bool):
                maximum = max(maximum, sequence)
    return maximum + 1


def _decree_open_event(
    task: dict[str, Any],
    receipt: dict[str, object],
    *,
    actor: str,
    evidence: str,
    note: str,
) -> dict[str, Any]:
    event = make_event(
        task,
        "decree_open",
        str(task.get("state") or "Pending"),
        str(task.get("state") or "Pending"),
        actor,
        evidence,
        note,
    )
    event.update(
        event_id=receipt["event_id"],
        operation_id=receipt["operation_id"],
        task_revision=receipt["task_revision"],
        decree_id=receipt["decree_id"],
        main_court_code=receipt["main_court_code"],
        parent_court_code=receipt["parent_court_code"],
        court_code=receipt["court_code"],
        daily_sequence=receipt["daily_sequence"],
        lineage_parts=deepcopy(receipt["lineage_parts"]),
        lineage_key=receipt["lineage_key"],
        lineage_version=receipt["lineage_version"],
    )
    return event


def _ensure_decree_open_event(
    task: dict[str, Any],
    operation: dict[str, Any],
) -> dict[str, Any]:
    receipt = operation.get("receipt")
    if not isinstance(receipt, dict):
        raise ValueError("decree_open_receipt_corrupt")
    matches = [
        event
        for event in events_for_task(task.get("task_id"))
        if event.get("action") == "decree_open"
        and event.get("operation_id") == receipt.get("operation_id")
    ]
    if len(matches) > 1:
        raise ValueError("decree_open_event_not_unique")
    if matches:
        if matches[0].get("event_id") != receipt.get("event_id"):
            raise ValueError("decree_open_event_receipt_mismatch")
        return matches[0]
    event = _decree_open_event(
        task,
        receipt,
        actor=str(operation.get("actor") or "taizi"),
        evidence=str(operation.get("evidence") or "decree-open recovery"),
        note=str(operation.get("note") or "decree-open recovery"),
    )
    append_event(event)
    return event


def decree_open_task(args: argparse.Namespace) -> dict[str, object]:
    operation_id = canonical_operation_id(args.operation_id)
    replay_only = bool(getattr(args, "replay_only", False))
    payload = _operation_request_payload(args, "decree payload")
    evidence = require_text(args.evidence, "evidence")
    if args.actor not in OFFICES:
        raise ValueError("unknown_actor_office")
    killpoint = str(getattr(args, "killpoint", "") or "")
    if killpoint not in {"", "after_allocation", "after_event"}:
        raise ValueError("invalid_decree_open_killpoint")
    with runtime_lock():
        tasks = load_tasks()
        found = _find_task_operation(tasks, operation_id)
        if found is not None and found[0] != args.task_id:
            raise ValueError("operation_binding_conflict")
        if found is not None:
            existing_task_id, task, operation = found
            if existing_task_id != args.task_id:
                raise ValueError("operation_binding_conflict")
            if operation.get("kind") != "decree_open":
                raise ValueError("operation_binding_conflict")
            require_semantic_mutation_binding(task)
            stored_binding = _stored_operation_binding(
                {**operation, "operation_id": operation_id}
            )
            incoming_expected_revision = (
                int(stored_binding["expected_task_revision"])
                if replay_only
                else int(getattr(args, "expected_task_revision", 0) or 0)
            )
            stored_target_ref = stored_binding.get("target_ref")
            incoming_target_ref = (
                dict(stored_target_ref)
                if replay_only and isinstance(stored_target_ref, Mapping)
                else {"kind": "decree_open", "task_id": args.task_id}
            )
            incoming_binding = _operation_binding(
                task,
                operation_id=operation_id,
                operation_kind="decree_open",
                request_schema="court.decree_open.v2",
                actor=args.actor,
                expected_task_revision=incoming_expected_revision,
                target_ref=incoming_target_ref,
            )
            _require_operation_replay_mode(
                stored_binding=stored_binding,
                incoming_binding=incoming_binding,
                replay_only=replay_only,
                payload_present=payload is not None,
            )
            receipt = operation.get("receipt")
            if not isinstance(receipt, dict):
                raise ValueError("decree_open_receipt_corrupt")
            if operation.get("status") != "COMMITTED":
                raise ValueError("operation_recovery_required")
            from court_case_binding import validate_task_case_binding

            replay_binding = validate_task_case_binding(task, require_decree=True)
            if replay_binding is not None and (
                receipt.get("task_id") != replay_binding["task_id"]
                or receipt.get("court_code") != replay_binding["court_code"]
                or receipt.get("session_id") != replay_binding["session_id"]
                or receipt.get("case_ref") != case_reference(replay_binding)
            ):
                raise ValueError("case_binding_decree_receipt_mismatch")
            _ensure_decree_open_event(task, operation)
            _write_operation_journal(
                binding=stored_binding,
                phase="COMMITTED",
                receipt=receipt,
                updated_at=now_text(),
                committed_task_revision=receipt.get("task_revision")
                if isinstance(receipt.get("task_revision"), int)
                else None,
                event_id=str(receipt.get("event_id") or ""),
            )
            return {
                "status": "REPLAYED",
                "operation_id": operation_id,
                "replay_reason": "REPLAYED_BODY_NOT_COMPARED",
                "receipt": deepcopy(receipt),
            }
        legacy_artifact = _legacy_operation_artifact_for_mutation(
            operation_id,
            allow_reference=replay_only,
        )
        if legacy_artifact is not None:
            raise ValueError(
                "legacy_store_present_requires_explicit_recovery"
                if legacy_artifact[1].get("store_present")
                else "LEGACY_READ_ONLY"
            )
        if replay_only:
            raise ValueError("operation_not_found")
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        from court_case_binding import validate_task_case_binding

        case_binding = validate_task_case_binding(task)
        try:
            current_revision = int(task.get("task_revision") or 1)
        except (TypeError, ValueError) as exc:
            raise ValueError("task_revision_corrupt") from exc
        if current_revision != args.expected_task_revision:
            raise ValueError("expected_task_revision_conflict")
        created_at = now_text()
        date_key = created_at[:10].replace("-", "")
        if case_binding is not None:
            from court_session_numbering import resolve_session_allocation

            allocation = resolve_session_allocation(case_binding["session_id"], date_key)
            if not isinstance(allocation, dict):
                raise ValueError("case_binding_allocation_missing")
            case_binding = validate_task_case_binding(task, allocation=allocation)
            if case_binding is None:
                raise ValueError("case_binding_missing")
            daily_sequence = allocation["daily_sequence"]
            main_court_code = allocation["court_code"]
            date_key = allocation["date"]
        else:
            daily_sequence = _decree_daily_sequence(tasks, date_key)
            main_court_code = f"CCR-{date_key}-{daily_sequence:04d}"
        next_revision = current_revision + 1
        raw_lineage_parts = payload.get("lineage_parts")
        if raw_lineage_parts is None:
            raw_lineage_parts = ["court", "decree"]
        if (
            not isinstance(raw_lineage_parts, list)
            or not raw_lineage_parts
            or any(
                not isinstance(part, str)
                or not part.strip()
                or len(part.strip()) > 128
                for part in raw_lineage_parts
            )
        ):
            raise ValueError("decree_lineage_parts_invalid")
        lineage_parts = [part.strip() for part in raw_lineage_parts]
        if "lineage_key" in payload:
            supplied_lineage_key = payload.get("lineage_key")
            if not isinstance(supplied_lineage_key, str):
                raise ValueError("decree_lineage_key_invalid")
            lineage_key = supplied_lineage_key.strip()
            if (
                not lineage_key
                or len(lineage_key) > 244
                or any(character in lineage_key for character in "\x00\r\n")
            ):
                raise ValueError("decree_lineage_key_invalid")
        else:
            lineage_key = "LNG-" + uuid.uuid4().hex.upper()
        lineage_version = payload.get("lineage_version", 1)
        if lineage_version != 1:
            raise ValueError("decree_lineage_version_invalid")
        decree_id = "DEC-" + uuid.uuid4().hex.upper()
        event_id = "EVT-" + uuid.uuid4().hex.upper()
        receipt: dict[str, object] = {
            "schema": "court.decree_open.receipt.v1",
            "operation_id": operation_id,
            "task_id": args.task_id,
            "task_revision": next_revision,
            "event_id": event_id,
            "decree_id": decree_id,
            "main_court_code": main_court_code,
            "parent_court_code": main_court_code,
            "court_code": main_court_code,
            "date_key": date_key,
            "daily_sequence": daily_sequence,
            "lineage_parts": lineage_parts,
            "lineage_key": lineage_key,
            "lineage_version": lineage_version,
            "status": "DEGREE_OPEN_COMMITTED",
            "created_at": created_at,
        }
        if case_binding is not None:
            receipt.update(
                session_id=case_binding["session_id"],
                charter_revision=case_binding["charter_revision"],
                case_ref=case_reference(case_binding),
            )
        operation_binding = _operation_binding(
            task,
            operation_id=operation_id,
            operation_kind="decree_open",
            request_schema="court.decree_open.v2",
            actor=args.actor,
            expected_task_revision=args.expected_task_revision,
            target_ref={"kind": "decree_open", "task_id": args.task_id},
        )
        operations = task.setdefault("operations", {})
        if not isinstance(operations, dict):
            raise ValueError("task_operation_ledger_corrupt")
        operation = {
            "kind": "decree_open",
            "operation_id": operation_id,
            "operation_binding": operation_binding,
            "payload": deepcopy(payload),
            "expected_task_revision": args.expected_task_revision,
            "status": "ALLOCATED",
            "receipt": deepcopy(receipt),
            "actor": args.actor,
            "evidence": evidence,
            "note": args.note,
        }
        operations[operation_id] = operation
        task["task_revision"] = next_revision
        task["decree_id"] = decree_id
        task["main_court_code"] = main_court_code
        task["parent_court_code"] = main_court_code
        task["lineage_parts"] = deepcopy(lineage_parts)
        task["lineage_key"] = lineage_key
        task["lineage_version"] = lineage_version
        task["next_office_child_no"] = 1
        task["updated_at"] = created_at
        task["last_evidence"] = evidence
        tasks[args.task_id] = task
        write_tasks(tasks)
        _write_operation_journal(
            binding=operation_binding,
            phase="ALLOCATED",
            receipt=receipt,
            updated_at=created_at,
            committed_task_revision=next_revision,
            event_id=event_id,
        )
        if killpoint == "after_allocation":
            raise SimulatedDecreeOpenCrash("after_allocation")
        _ensure_decree_open_event(task, operation)
        operation["status"] = "COMMITTED"
        tasks[args.task_id] = task
        write_tasks(tasks)
        _write_operation_journal(
            binding=operation_binding,
            phase="COMMITTED",
            receipt=receipt,
            updated_at=now_text(),
            committed_task_revision=next_revision,
            event_id=event_id,
        )
        if killpoint == "after_event":
            raise SimulatedDecreeOpenCrash("after_event")
    return {
        "status": "COMMITTED",
        "operation_id": operation_id,
        "receipt": deepcopy(receipt),
    }


def recover_decree_open_operation(operation_id: object) -> dict[str, object]:
    canonical = canonical_operation_id(operation_id)
    with runtime_lock():
        legacy_artifact = _legacy_operation_artifact_for_mutation(
            operation_id,
            allow_reference=True,
        )
        if legacy_artifact is not None:
            raise ValueError(
                "legacy_store_present_requires_explicit_recovery"
                if legacy_artifact[1].get("store_present")
                else "LEGACY_READ_ONLY"
            )
        tasks = load_tasks()
        found = _find_task_operation(tasks, canonical)
        if found is None:
            raise ValueError("decree_open_operation_not_found")
        task_id, task, operation = found
        if operation.get("kind") != "decree_open":
            raise ValueError("operation_binding_conflict")
        binding = _stored_operation_binding(
            {**operation, "operation_id": canonical}
        )
        receipt = operation.get("receipt")
        if not isinstance(receipt, dict):
            raise ValueError("decree_open_receipt_corrupt")
        event = _ensure_decree_open_event(task, operation)
        operation["status"] = "COMMITTED"
        tasks[task_id] = task
        write_tasks(tasks)
        _write_operation_journal(
            binding=binding,
            phase="COMMITTED",
            receipt=receipt,
            updated_at=now_text(),
            committed_task_revision=receipt.get("task_revision")
            if isinstance(receipt.get("task_revision"), int)
            else None,
            event_id=str(event.get("event_id") or ""),
        )
    return {
        "status": "RECOVERED",
        "operation_id": canonical,
        "event_id": event.get("event_id"),
        "receipt": deepcopy(receipt),
    }


def _synthetic_closeout_root(value: object) -> tuple[Path, str]:
    runtime = runtime_root().resolve()
    root = Path(value).resolve()
    try:
        relative = root.relative_to(runtime)
    except ValueError as exc:
        raise ValueError("synthetic_archive_root_outside_runtime") from exc
    if not relative.parts or not relative.parts[0].startswith("synthetic-"):
        raise ValueError("synthetic_archive_root_not_fixture_scoped")
    return root, relative.as_posix()


def _synthetic_closeout_root_from_operation(operation: dict[str, Any]) -> Path:
    relative_text = str(operation.get("synthetic_archive_relpath") or "")
    relative = Path(relative_text)
    if not relative_text or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("synthetic_archive_relpath_corrupt")
    root, canonical_relative = _synthetic_closeout_root(runtime_root() / relative)
    if canonical_relative != relative.as_posix():
        raise ValueError("synthetic_archive_relpath_corrupt")
    return root


def _strict_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"synthetic_archive_jsonl_corrupt:{path.name}:{line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"synthetic_archive_jsonl_corrupt:{path.name}:{line_number}")
        rows.append(value)
    return rows


def _append_jsonl_durable(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _operation_row(
    path: Path,
    operation_id: str,
) -> dict[str, object] | None:
    matches = [
        row for row in _strict_jsonl(path) if row.get("operation_id") == operation_id
    ]
    if len(matches) > 1:
        raise ValueError(f"synthetic_side_effect_duplicate:{path.name}")
    return matches[0] if matches else None


def _closeout_archive_material(operation: dict[str, Any]) -> tuple[dict[str, object], dict[str, object]]:
    operation_id = str(operation.get("operation_id") or "")
    task_id = str(operation.get("task_id") or "")
    decree_id = str(operation.get("decree_id") or "")
    main_court_code = str(operation.get("main_court_code") or "")
    prepared_at = str(operation.get("prepared_at") or "")
    if not all((operation_id, task_id, decree_id, main_court_code, prepared_at)):
        raise ValueError("synthetic_closeout_intent_corrupt")
    suffix = operation_id.replace("-", "").upper()
    record_uid = "REC-" + suffix
    court_code = f"{main_court_code}-R{suffix[:8]}"
    archive_record: dict[str, object] = {
        "schema": "court.synthetic_archive.record.v1",
        "operation_id": operation_id,
        "task_id": task_id,
        "decree_id": decree_id,
        "main_court_code": main_court_code,
        "parent_court_code": main_court_code,
        "court_code": court_code,
        "record_uid": record_uid,
        "recorded_at": prepared_at,
        "status": "ARCHIVE_COMMITTED",
    }
    archive_record["record_ref"] = f"record:{record_uid}"
    index_record: dict[str, object] = {
        "schema": "court.synthetic_archive.index.v1",
        "operation_id": operation_id,
        "task_id": task_id,
        "decree_id": decree_id,
        "main_court_code": main_court_code,
        "parent_court_code": main_court_code,
        "court_code": court_code,
        "record_uid": record_uid,
        "record_ref": archive_record["record_ref"],
        "indexed_at": prepared_at,
        "status": "INDEX_COMMITTED",
    }
    return archive_record, index_record


def _ensure_synthetic_archive_side_effects(
    operation: dict[str, Any],
    *,
    killpoint: str = "",
) -> dict[str, object]:
    root = _synthetic_closeout_root_from_operation(operation)
    root.mkdir(parents=True, exist_ok=True)
    operation_id = str(operation.get("operation_id") or "")
    archive_record, index_record = _closeout_archive_material(operation)
    archive_path = root / "archive.jsonl"
    index_path = root / "index.jsonl"
    with file_lock(root / "synthetic-closeout.lock", timeout=30.0, poll_interval=0.02):
        existing_archive = _operation_row(archive_path, operation_id)
        if existing_archive is None:
            _append_jsonl_durable(archive_path, archive_record)
        elif existing_archive != archive_record:
            raise ValueError("synthetic_archive_operation_conflict")
        if killpoint == "after_archive":
            raise SimulatedCloseoutCrash("after_archive")
        existing_index = _operation_row(index_path, operation_id)
        if existing_index is None:
            _append_jsonl_durable(index_path, index_record)
        elif existing_index != index_record:
            raise ValueError("synthetic_index_operation_conflict")
        if killpoint == "after_index":
            raise SimulatedCloseoutCrash("after_index")
    return {
        "schema": "court.synthetic_archive.receipt.v1",
        "operation_id": operation_id,
        "task_id": operation["task_id"],
        "decree_id": operation["decree_id"],
        "main_court_code": operation["main_court_code"],
        "parent_court_code": archive_record["parent_court_code"],
        "court_code": archive_record["court_code"],
        "archive_record_uid": archive_record["record_uid"],
        "record_ref": archive_record["record_ref"],
        "status": "ARCHIVE_COMMITTED",
    }


def _closeout_event(
    task: dict[str, Any],
    operation: dict[str, Any],
    receipt: dict[str, object],
) -> dict[str, Any]:
    event = make_event(
        task,
        "closeout_commit",
        str(task.get("state") or "Pending"),
        str(task.get("state") or "Pending"),
        str(operation.get("actor") or "shiguan"),
        str(operation.get("evidence") or "synthetic closeout recovery"),
        str(operation.get("note") or "synthetic closeout recovery"),
    )
    event.update(
        event_id=receipt["event_id"],
        operation_id=receipt["operation_id"],
        task_revision=receipt["task_revision"],
        decree_id=receipt["decree_id"],
        main_court_code=receipt["main_court_code"],
        parent_court_code=receipt["parent_court_code"],
        court_code=receipt["court_code"],
        archive_record_uid=receipt["archive_record_uid"],
        closeout_status=receipt["status"],
    )
    return event


def _ensure_closeout_event(
    task: dict[str, Any],
    operation: dict[str, Any],
) -> dict[str, Any]:
    receipt = operation.get("receipt")
    if not isinstance(receipt, dict):
        raise ValueError("closeout_receipt_corrupt")
    operation_id = str(operation.get("operation_id") or "")
    matches = [
        event
        for event in events_for_task(task.get("task_id"))
        if event.get("action") == "closeout_commit"
        and event.get("operation_id") == operation_id
    ]
    if len(matches) > 1:
        raise ValueError("closeout_event_not_unique")
    if matches:
        if matches[0].get("event_id") != receipt.get("event_id"):
            raise ValueError("closeout_event_receipt_mismatch")
        return matches[0]
    event = _closeout_event(task, operation, receipt)
    append_event(event)
    return event


def _prepare_synthetic_closeout(
    args: argparse.Namespace,
) -> tuple[str, dict[str, object], dict[str, Any]]:
    operation_id = canonical_operation_id(args.operation_id)
    replay_only = bool(getattr(args, "replay_only", False))
    payload = _operation_request_payload(args, "closeout payload")
    synthetic_root, relative_root = _synthetic_closeout_root(args.synthetic_archive_root)
    del synthetic_root
    evidence = require_text(args.evidence, "evidence")
    if args.actor not in OFFICES:
        raise ValueError("unknown_actor_office")
    with runtime_lock():
        tasks = load_tasks()
        found = _find_task_operation(tasks, operation_id)
        if found is not None:
            existing_task_id, task, operation = found
            if existing_task_id != args.task_id:
                raise ValueError("operation_binding_conflict")
            if operation.get("kind") != "synthetic_closeout":
                raise ValueError("operation_binding_conflict")
            require_semantic_mutation_binding(task)
            stored_binding = _stored_operation_binding(
                {**operation, "operation_id": operation_id}
            )
            target_ref = stored_binding.get("target_ref")
            if (
                replay_only
                and isinstance(target_ref, Mapping)
                and target_ref.get("synthetic_archive_relpath") != relative_root
            ):
                raise ValueError("operation_binding_conflict")
            if replay_only:
                incoming_expected_revision = int(stored_binding["expected_task_revision"])
                incoming_target_ref = (
                    dict(target_ref) if isinstance(target_ref, Mapping) else {}
                )
            else:
                if not isinstance(payload, Mapping):
                    raise ValueError("closeout payload is required")
                incoming_expected_revision = int(
                    getattr(args, "expected_task_revision", 0) or 0
                )
                incoming_target_ref = {
                    "kind": "synthetic_closeout",
                    "task_id": args.task_id,
                    "decree_id": str(payload.get("decree_id") or ""),
                    "main_court_code": str(payload.get("main_court_code") or ""),
                    "synthetic_archive_relpath": relative_root,
                }
            incoming_binding = _operation_binding(
                task,
                operation_id=operation_id,
                operation_kind="synthetic_closeout",
                request_schema="court.synthetic_closeout.v2",
                actor=args.actor,
                expected_task_revision=incoming_expected_revision,
                target_ref=incoming_target_ref,
            )
            _require_operation_replay_mode(
                stored_binding=stored_binding,
                incoming_binding=incoming_binding,
                replay_only=replay_only,
                payload_present=payload is not None,
            )
            if operation.get("status") != "TASK_EVENT_COMMITTED":
                raise ValueError("operation_recovery_required")
            return operation_id, stored_binding, deepcopy(operation)
        legacy_artifact = _legacy_operation_artifact_for_mutation(
            operation_id,
            allow_reference=replay_only,
        )
        if legacy_artifact is not None:
            raise ValueError(
                "legacy_store_present_requires_explicit_recovery"
                if legacy_artifact[1].get("store_present")
                else "LEGACY_READ_ONLY"
            )
        if replay_only:
            raise ValueError("operation_not_found")
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        try:
            current_revision = int(task.get("task_revision") or 1)
        except (TypeError, ValueError) as exc:
            raise ValueError("task_revision_corrupt") from exc
        if current_revision != args.expected_task_revision:
            raise ValueError("expected_task_revision_conflict")
        decree_id = str(payload.get("decree_id") or "")
        main_court_code = str(payload.get("main_court_code") or "")
        if decree_id != str(task.get("decree_id") or ""):
            raise ValueError("closeout_decree_id_mismatch")
        if main_court_code != str(task.get("main_court_code") or ""):
            raise ValueError("closeout_main_court_code_mismatch")
        prepared_at = now_text()
        operation_binding = _operation_binding(
            task,
            operation_id=operation_id,
            operation_kind="synthetic_closeout",
            request_schema="court.synthetic_closeout.v2",
            actor=args.actor,
            expected_task_revision=args.expected_task_revision,
            target_ref={
                "kind": "synthetic_closeout",
                "task_id": args.task_id,
                "decree_id": decree_id,
                "main_court_code": main_court_code,
                "synthetic_archive_relpath": relative_root,
            },
        )
        operation = {
            "kind": "synthetic_closeout",
            "operation_id": operation_id,
            "operation_binding": operation_binding,
            "payload": deepcopy(payload),
            "expected_task_revision": args.expected_task_revision,
            "synthetic_archive_relpath": relative_root,
            "task_id": args.task_id,
            "decree_id": decree_id,
            "main_court_code": main_court_code,
            "status": "PREPARED",
            "prepared_at": prepared_at,
            "actor": args.actor,
            "evidence": evidence,
            "note": args.note,
        }
        operations = task.setdefault("operations", {})
        if not isinstance(operations, dict):
            raise ValueError("task_operation_ledger_corrupt")
        operations[operation_id] = operation
        task["task_revision"] = current_revision + 1
        task["updated_at"] = prepared_at
        task["last_evidence"] = evidence
        tasks[args.task_id] = task
        write_tasks(tasks)
        _write_operation_journal(
            binding=operation_binding,
            phase="PREPARED",
            receipt=None,
            updated_at=prepared_at,
        )
    return operation_id, operation_binding, deepcopy(operation)


def _commit_synthetic_closeout_task_event(
    operation_id: str,
    operation_binding: Mapping[str, object],
    archive_receipt: dict[str, object],
    *,
    killpoint: str = "",
) -> dict[str, object]:
    with runtime_lock():
        tasks = load_tasks()
        found = _find_task_operation(tasks, operation_id)
        if found is None:
            raise ValueError("closeout_operation_not_found")
        task_id, task, operation = found
        if operation.get("kind") != "synthetic_closeout":
            raise ValueError("operation_binding_conflict")
        stored_binding = _stored_operation_binding(
            {**operation, "operation_id": operation_id}
        )
        if dict(stored_binding) != dict(operation_binding):
            raise ValueError("operation_binding_conflict")
        existing_receipt = operation.get("receipt")
        if isinstance(existing_receipt, dict):
            event = _ensure_closeout_event(task, operation)
            _write_operation_journal(
                binding=stored_binding,
                phase="COMMITTED",
                receipt=existing_receipt,
                updated_at=now_text(),
                committed_task_revision=existing_receipt.get("task_revision")
                if isinstance(existing_receipt.get("task_revision"), int)
                else None,
                event_id=str(event.get("event_id") or ""),
            )
            return {
                "status": "REPLAYED",
                "event_id": event.get("event_id"),
                "replay_reason": "REPLAYED_BODY_NOT_COMPARED",
                "receipt": deepcopy(existing_receipt),
            }
        try:
            current_revision = int(task.get("task_revision") or 1)
        except (TypeError, ValueError) as exc:
            raise ValueError("task_revision_corrupt") from exc
        committed_at = now_text()
        next_revision = current_revision + 1
        event_id = "EVT-" + uuid.uuid4().hex.upper()
        receipt: dict[str, object] = {
            "schema": "court.closeout.receipt.v1",
            "operation_id": operation_id,
            "task_id": task_id,
            "task_revision": next_revision,
            "event_id": event_id,
            "decree_id": archive_receipt["decree_id"],
            "main_court_code": archive_receipt["main_court_code"],
            "parent_court_code": archive_receipt["parent_court_code"],
            "court_code": archive_receipt["court_code"],
            "archive_record_uid": archive_receipt["archive_record_uid"],
            "record_ref": archive_receipt["record_ref"],
            "status": "TASK_EVENT_COMMITTED",
            "committed_at": committed_at,
        }
        operation["archive_receipt"] = deepcopy(archive_receipt)
        operation["receipt"] = deepcopy(receipt)
        operation["status"] = "TASK_EVENT_COMMITTED"
        task["task_revision"] = next_revision
        task["closeout_receipt"] = deepcopy(receipt)
        task["updated_at"] = committed_at
        task["last_evidence"] = str(operation.get("evidence") or "synthetic closeout")
        tasks[task_id] = task
        write_tasks(tasks)
        if killpoint == "after_task":
            raise SimulatedCloseoutCrash("after_task")
        event = _ensure_closeout_event(task, operation)
        if killpoint == "after_event":
            raise SimulatedCloseoutCrash("after_event")
        _write_operation_journal(
            binding=stored_binding,
            phase="COMMITTED",
            receipt=receipt,
            updated_at=now_text(),
            committed_task_revision=next_revision,
            event_id=event_id,
        )
    return {
        "status": "COMMITTED",
        "event_id": event.get("event_id"),
        "receipt": deepcopy(receipt),
    }


def synthetic_closeout_task(args: argparse.Namespace) -> dict[str, object]:
    killpoint = str(getattr(args, "killpoint", "") or "")
    if killpoint not in {"", "after_archive", "after_index", "after_task", "after_event"}:
        raise ValueError("invalid_closeout_killpoint")
    operation_id, operation_binding, operation = _prepare_synthetic_closeout(args)
    if bool(getattr(args, "replay_only", False)):
        receipt = operation.get("receipt")
        if not isinstance(receipt, dict):
            raise ValueError("operation_recovery_required")
        return {
            "status": "REPLAYED",
            "operation_id": operation_id,
            "replay_reason": "REPLAYED_BODY_NOT_COMPARED",
            "event_id": receipt.get("event_id"),
            "receipt": deepcopy(receipt),
        }
    if isinstance(operation.get("receipt"), dict):
        archive_receipt = operation.get("archive_receipt")
        if not isinstance(archive_receipt, dict):
            raise ValueError("closeout_archive_receipt_corrupt")
        return _commit_synthetic_closeout_task_event(
            operation_id,
            operation_binding,
            archive_receipt,
        )
    archive_receipt = _ensure_synthetic_archive_side_effects(
        operation,
        killpoint=killpoint if killpoint in {"after_archive", "after_index"} else "",
    )
    _write_operation_journal(
        binding=operation_binding,
        phase="ARCHIVE_COMMITTED",
        receipt=archive_receipt,
        updated_at=now_text(),
    )
    return _commit_synthetic_closeout_task_event(
        operation_id,
        operation_binding,
        archive_receipt,
        killpoint=killpoint if killpoint in {"after_task", "after_event"} else "",
    )


def recover_closeout_operation(operation_id: object) -> dict[str, object]:
    canonical = canonical_operation_id(operation_id)
    with runtime_lock():
        tasks = load_tasks()
        found = _find_task_operation(tasks, canonical)
        if found is None:
            raise ValueError("closeout_operation_not_found")
        _, _, operation = found
        if operation.get("kind") != "synthetic_closeout":
            raise ValueError("operation_kind_conflict")
        operation_copy = deepcopy(operation)
    operation_binding = _stored_operation_binding(
        {**operation_copy, "operation_id": canonical}
    )
    archive_receipt = _ensure_synthetic_archive_side_effects(operation_copy)
    _write_operation_journal(
        binding=operation_binding,
        phase="ARCHIVE_COMMITTED",
        receipt=archive_receipt,
        updated_at=now_text(),
    )
    result = _commit_synthetic_closeout_task_event(
        canonical,
        operation_binding,
        archive_receipt,
    )
    return {
        "status": "RECOVERED",
        "operation_id": canonical,
        "receipt": result["receipt"],
    }


def revise_charter_record(
    task: dict[str, object],
    *,
    expected_revision: int,
    case_ref: Mapping[str, object],
    new_revision: int,
    new_charter: str,
    new_invariant_capsule: dict[str, object],
    event_head_id: str,
    actor: str,
    evidence: str,
    legacy_prior: bool = False,
) -> dict[str, object]:
    """Return a revised task without mutating the caller-owned record."""

    revised = deepcopy(task)
    if actor not in OFFICES:
        raise ValueError("unknown_actor_office")
    if str(revised.get("state") or "Pending") not in RECHARTERABLE_STATES:
        raise ValueError("task_state_cannot_be_rechartered")
    supplied_case_ref = case_reference(case_ref)
    if legacy_prior:
        prior_case_ref = {
            "court_code": supplied_case_ref["court_code"],
            "charter_revision": 1,
        }
        if supplied_case_ref != prior_case_ref:
            raise ValueError("stale_charter_case_reference")
    else:
        prior_case_ref = case_reference(revised)
        if supplied_case_ref != prior_case_ref:
            raise ValueError("stale_charter_case_reference")
        if revised.get("charter_revision") != expected_revision:
            raise ValueError("stale_charter_revision")
        if new_revision != expected_revision + 1:
            raise ValueError("invalid_charter_revision_increment")
    if legacy_prior and new_revision != 1:
        raise ValueError("invalid_charter_revision_increment")
    semantic_binding = semantic_binding_for_revision(
        new_charter,
        new_revision,
        new_invariant_capsule,
        court_code=prior_case_ref["court_code"],
    )
    binding_problems = semantic_binding_problems(
        {"charter": new_charter, **semantic_binding},
        require_complete=True,
    )
    if binding_problems:
        raise ValueError("semantic_binding_drift:" + ",".join(binding_problems))
    invalidated_at = now_text()
    prior_receipts = deepcopy(revised.get("semantic_receipts"))
    if not isinstance(prior_receipts, list):
        prior_current = revised.get("semantic_receipt")
        prior_receipts = [deepcopy(prior_current)] if isinstance(prior_current, dict) and prior_current else []
    prior_current = revised.get("semantic_receipt")
    if not isinstance(prior_current, dict):
        prior_current = {}
    invalidation_snapshot = {
        "schema": "court.semantic.invalidation.v1",
        "invalidated_revision": expected_revision,
        "replacement_revision": new_revision,
        "invalidated_at": invalidated_at,
        "actor": actor,
        "evidence": evidence,
        "outcome_assessment": deepcopy(revised.get("outcome_assessment")),
        "assessment_binding": deepcopy(revised.get("assessment_binding")),
        "shiguan_checkpoint": deepcopy(revised.get("shiguan_checkpoint")),
        "completion": deepcopy(revised.get("completion")),
        "dispatch_plan": deepcopy(revised.get("dispatch_plan")),
        "agent_admissions": deepcopy(revised.get("agent_admissions")),
        "agents": deepcopy(revised.get("agents")),
        "invariant_capsule": deepcopy(revised.get("invariant_capsule")),
        "case_ref": prior_case_ref,
        "semantic_receipt": deepcopy(revised.get("semantic_receipt")),
        "semantic_receipt_id": revised.get("semantic_receipt_id"),
        "semantic_receipts": deepcopy(prior_receipts),
        "semantic_dispatch_attempts": deepcopy(
            revised.get("semantic_dispatch_attempts")
        ),
        "task_point_capsules": deepcopy(revised.get("task_point_capsules")),
        "zhongshu_plan": deepcopy(revised.get("zhongshu_plan")),
        "case_reviews": deepcopy(revised.get("case_reviews")),
    }
    invalidations = list(revised.get("semantic_invalidations") or [])
    invalidations.append(invalidation_snapshot)
    history = list(revised.get("charter_revision_history") or [])
    history.append(
        {
            "revision": expected_revision,
            "case_ref": prior_case_ref,
            "actor": actor,
            "evidence": evidence,
        }
    )
    revised["charter_revision_history"] = history
    revised["charter"] = new_charter
    revised.update(semantic_binding)
    revised["semantic_receipts"] = deepcopy(prior_receipts)
    pending_checkpoint_id = "SC-PENDING-" + uuid.uuid4().hex.upper()
    correction_base = dict(prior_current)
    correction_base.update(
        schema="court.semantic.receipt.v1",
        checkpoint_id=pending_checkpoint_id,
        task_id=revised.get("task_id"),
        semantic_epoch=new_revision,
        case_ref=case_reference(semantic_binding),
        plan_ref=None,
        authority_revision=new_revision,
        plan_cursor=f"ThreeDepartments@revision-{new_revision}",
        dispatch_uid=None,
        attempt=None,
        agent_id=None,
        write_set=deepcopy(new_invariant_capsule.get("write_set", [])),
    )
    correction_receipt = derive_semantic_receipt(
        correction_base,
        receipt_sequence=len(prior_receipts) + 1,
        gate="semantic_correct",
        verdict="REVERIFY",
        trigger="correction",
        reason_codes=["charter_revision_corrected"],
        created_at=invalidated_at,
        event_head_id=event_head_id,
        updates={"corrected_at": invalidated_at},
    )
    _append_semantic_receipt(revised, correction_receipt)
    revised["semantic_invalidations"] = invalidations
    revised["outcome_assessment"] = _unassessed_outcome()
    revised["assessment_binding"] = {}
    revised["shiguan_checkpoint"] = {}
    revised["completion"] = {"status": "INVALIDATED_BY_CHARTER_REVISION"}
    dispatch_plan = revised.get("dispatch_plan")
    if isinstance(dispatch_plan, dict) and dispatch_plan:
        invalidated_dispatch = dict(dispatch_plan)
        invalidated_dispatch.update(
            status="INVALIDATED_BY_CHARTER_REVISION",
            invalidated_at=invalidated_at,
            invalidated_by_charter_revision=new_revision,
        )
        revised["dispatch_plan"] = invalidated_dispatch
    admissions = revised.get("agent_admissions")
    if isinstance(admissions, dict):
        invalidated_admissions: dict[str, object] = {}
        for wave_id, record in admissions.items():
            if isinstance(record, dict):
                invalidated_record = dict(record)
                invalidated_record.update(
                    status="INVALIDATED_BY_CHARTER_REVISION",
                    invalidated_at=invalidated_at,
                    invalidated_by_charter_revision=new_revision,
                )
                invalidated_admissions[str(wave_id)] = invalidated_record
            else:
                invalidated_admissions[str(wave_id)] = record
        revised["agent_admissions"] = invalidated_admissions
    agents = revised.get("agents")
    if isinstance(agents, dict):
        invalidated_agents: dict[str, object] = {}
        for agent_id, record in agents.items():
            if isinstance(record, dict):
                invalidated_record = dict(record)
                invalidated_record.update(
                    assignment_invalidated_by_charter_revision=new_revision,
                    assignment_status="INVALIDATED_BY_CHARTER_REVISION",
                    invalidated_at=invalidated_at,
                )
                if str(record.get("status") or "") not in TERMINAL_AGENT_STATUSES:
                    invalidated_record.update(
                        status="invalidated",
                        final_status="invalidated",
                        release_status="closed",
                        finished_at=record.get("finished_at") or invalidated_at,
                        closed_at=record.get("closed_at") or invalidated_at,
                    )
                invalidated_agents[str(agent_id)] = invalidated_record
            else:
                invalidated_agents[str(agent_id)] = record
        revised["agents"] = invalidated_agents
    attempts = revised.get("semantic_dispatch_attempts")
    if isinstance(attempts, list):
        revised["semantic_dispatch_attempts"] = [
            {
                **dict(record),
                "status": "INVALIDATED_BY_CHARTER_REVISION",
                "invalidated_at": invalidated_at,
                "invalidated_by_charter_revision": new_revision,
            }
            if isinstance(record, dict)
            else record
            for record in attempts
        ]
    capsules = revised.get("task_point_capsules")
    if isinstance(capsules, list):
        revised["task_point_capsules"] = [
            {
                **dict(record),
                "status": "INVALIDATED_BY_CHARTER_REVISION",
                "invalidated_at": invalidated_at,
                "invalidated_by_charter_revision": new_revision,
            }
            if isinstance(record, dict)
            else record
            for record in capsules
        ]
    revised["state"] = "ThreeDepartments"
    state_history = list(revised.get("semantic_state_history") or [])
    state_history.extend(
        (
            {
                "state": "CORRECTED",
                "semantic_epoch": new_revision,
                "created_at": invalidated_at,
            },
            {
                "state": "REVERIFY",
                "semantic_epoch": new_revision,
                "created_at": invalidated_at,
            },
        )
    )
    revised["semantic_state_history"] = state_history
    revised["semantic_state"] = "REVERIFY"
    if isinstance(revised.get("case_binding"), dict):
        from court_case_binding import refresh_case_binding
        from court_plan_artifacts import bootstrap_artifact
        revised.pop("zhongshu_plan", None)
        revised["case_reviews"] = {}
        revised["case_bootstrap"] = bootstrap_artifact(revised)
        revised["case_binding"] = refresh_case_binding(revised)
    return revised


def revise_charter_task(args: argparse.Namespace) -> TransitionResult:
    gate = require_task_correction_gate(
        _json_object_from_args(
            args,
            "correction_gate",
            "correction_file",
            "task correction gate",
        )
    )
    if gate.get("target_task_id") != args.task_id:
        raise ValueError("task_correction_target_mismatch")
    new_charter = _text_from_args(
        args,
        "new_charter",
        "new_charter_file",
        "charter_body",
    )
    if getattr(args, "new_invariant_capsule", None) is None and getattr(
        args,
        "new_invariant_capsule_file",
        None,
    ) is None:
        raise ValueError("new_invariant_capsule_required")
    new_invariant_capsule = _json_object_from_args(
        args,
        "new_invariant_capsule",
        "new_invariant_capsule_file",
        "new invariant capsule",
    )
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        legacy_bootstrap = _legacy_semantic_bootstrap(task)
        if not legacy_bootstrap:
            require_semantic_mutation_binding(task)
        revised = revise_charter_record(
            task,
            expected_revision=args.expected_revision,
            case_ref=_required_context_object(args.case_ref, "case_ref_required"),
            new_revision=args.new_revision,
            new_charter=new_charter,
            new_invariant_capsule=new_invariant_capsule,
            event_head_id=_event_head_id(str(task["task_id"])),
            actor=args.actor,
            evidence=args.evidence,
            legacy_prior=legacy_bootstrap,
        )
        revised["conversation_gate"] = deepcopy(gate)
        revised["updated_at"] = now_text()
        revised["last_evidence"] = args.evidence
        tasks[args.task_id] = revised
        event = make_event(
            revised,
            "revise_charter",
            str(task.get("state") or "Pending"),
            str(revised.get("state") or "Pending"),
            args.actor,
            args.evidence,
            args.note,
        )
        correction_receipt = revised.get("semantic_receipt")
        if isinstance(correction_receipt, dict):
            event.update(
                checkpoint_id=correction_receipt.get("checkpoint_id"),
                receipt_id=correction_receipt.get("receipt_id"),
                case_ref=case_reference(revised),
                event_head_id=correction_receipt.get("event_head_id"),
                semantic_epoch=correction_receipt.get("semantic_epoch"),
                semantic_verdict=correction_receipt.get("verdict"),
            )
        _commit_task_event(tasks, event)
    return TransitionResult(revised, event)


def _semantic_context_payload(value: object) -> object:
    if not isinstance(value, dict):
        return value
    if value.get("schema") != "court.semantic.context_template.v1":
        return value
    if set(value) != {"schema", "context"} or not isinstance(value.get("context"), dict):
        raise ValueError("semantic_context_template_invalid")
    return value["context"]


def _semantic_context_from_args(args: argparse.Namespace) -> dict[str, object]:
    value = _json_object_from_args(
        args,
        "semantic_context",
        "semantic_context_file",
        "semantic context",
    )
    return normalize_semantic_context(_semantic_context_payload(value))


def _event_head_id(task_id: str) -> str:
    history = events_for_task(task_id)
    return next((str(event["event_id"]) for event in reversed(history) if event.get("event_id")), f"court-runtime:tasks/{task_id}")


def _event_head_sha256() -> str:
    current = events_path().read_bytes() if events_path().exists() else b""
    return hashlib.sha256(current).hexdigest()


def _event_head_bytes() -> int:
    return len(events_path().read_bytes()) if events_path().exists() else 0


def _semantic_receipt_history(task: dict[str, Any]) -> list[dict[str, object]]:
    history = task.get("semantic_receipts")
    if history is None:
        current = task.get("semantic_receipt")
        if isinstance(current, dict) and current:
            history = [finalize_semantic_receipt(current)]
        else:
            history = []
        task["semantic_receipts"] = history
    if not isinstance(history, list) or any(
        not isinstance(receipt, dict) for receipt in history
    ):
        raise ValueError("semantic_receipt_history_corrupt")
    return history


def _append_semantic_receipt(
    task: dict[str, Any],
    receipt: dict[str, object],
) -> dict[str, object]:
    history = _semantic_receipt_history(task)
    canonical = finalize_semantic_receipt(receipt)
    for field in ("receipt_id",):
        if receipt.get(field) is not None and receipt.get(field) != canonical[field]:
            raise ValueError(f"semantic_receipt_integrity:{field}")
    expected_sequence = len(history) + 1
    if canonical.get("receipt_sequence") != expected_sequence:
        raise ValueError("semantic_receipt_sequence_conflict")
    receipt_id = canonical["receipt_id"]
    if any(existing.get("receipt_id") == receipt_id for existing in history):
        raise ValueError("semantic_receipt_id_conflict")
    history.append(deepcopy(canonical))
    task["semantic_receipts"] = history
    task["semantic_receipt"] = deepcopy(canonical)
    task["semantic_receipt_id"] = receipt_id
    return canonical


def semantic_receipt_by_checkpoint_id(
    task: dict[str, object],
    checkpoint_id: str,
) -> dict[str, object]:
    history = task.get("semantic_receipts")
    matches = [
        receipt
        for receipt in history or []
        if isinstance(receipt, dict)
        and receipt.get("checkpoint_id") == checkpoint_id
        and receipt.get("gate") == "semantic_checkpoint"
    ] if isinstance(history, list) else []
    if len(matches) > 1:
        raise ValueError("semantic_checkpoint_receipt_not_unique")
    if matches:
        return deepcopy(matches[0])
    current = task.get("semantic_receipt")
    if (
        isinstance(current, dict)
        and current.get("checkpoint_id") == checkpoint_id
        and current.get("gate") == "semantic_checkpoint"
    ):
        return deepcopy(current)
    raise ValueError("semantic_checkpoint_receipt_not_found")


def _current_checkpoint_receipt(task: dict[str, Any]) -> dict[str, object]:
    current = task.get("semantic_receipt")
    if not isinstance(current, dict):
        raise ValueError("semantic_receipt_missing")
    checkpoint_id = str(current.get("checkpoint_id") or "")
    if not checkpoint_id:
        raise ValueError("semantic_checkpoint_id_missing")
    history = task.get("semantic_receipts")
    matches = [
        receipt
        for receipt in history or []
        if isinstance(receipt, dict)
        and receipt.get("checkpoint_id") == checkpoint_id
    ] if isinstance(history, list) else []
    if matches:
        return deepcopy(matches[0])
    return deepcopy(current)


def _semantic_receipt_event_problems(
    task: dict[str, Any],
    receipt: dict[str, object],
) -> list[str]:
    if isinstance(receipt.get("case_ref"), Mapping):
        matching = [
            event for event in events_for_task(task.get("task_id"), limit=None)
            if event.get("receipt_id") == receipt.get("receipt_id")
        ]
        if len(matching) != 1:
            return ["semantic_receipt_event:missing_or_not_unique"]
        event = matching[0]
        expected_action = {
            "semantic_checkpoint": {"semantic_checkpoint"},
            "semantic_verify": {"semantic_verify", "semantic_quarantine"},
            "semantic_resume": {"semantic_resume"},
            "semantic_quarantine": {"semantic_quarantine"},
            "semantic_reconcile": {"semantic_reconcile"},
            "semantic_correct": {"revise_charter"},
        }.get(str(receipt.get("gate") or ""), set())
        problems = ["semantic_receipt_event:action"] if event.get("action") not in expected_action else []
        for field in ("task_id", "checkpoint_id", "receipt_id", "semantic_epoch", "case_ref"):
            if event.get(field) != receipt.get(field):
                problems.append("semantic_receipt_event:" + field)
        return problems
    problems: list[str] = []
    byte_count = receipt.get("event_head_bytes")
    if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
        return ["semantic_receipt_event:event_head_bytes"]
    ledger = events_path().read_bytes() if events_path().exists() else b""
    if byte_count > len(ledger):
        return ["semantic_receipt_event:event_head_out_of_range"]
    prefix = ledger[:byte_count]
    if hashlib.sha256(prefix).hexdigest() != receipt.get("event_head_sha256"):
        problems.append("semantic_receipt_event:event_head_sha256")
    tail_lines = ledger[byte_count:].splitlines()
    first_line = tail_lines[0] if tail_lines else b""
    try:
        event = json.loads(first_line.decode("utf-8")) if first_line else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        event = None
    if not isinstance(event, dict):
        return [*problems, "semantic_receipt_event:missing"]
    expected_actions = {
        "semantic_checkpoint": {"semantic_checkpoint"},
        "semantic_verify": {"semantic_verify", "semantic_quarantine"},
        "semantic_resume": {"semantic_resume"},
        "semantic_quarantine": {"semantic_quarantine"},
        "semantic_reconcile": {"semantic_reconcile"},
        "semantic_correct": {"revise_charter"},
    }.get(str(receipt.get("gate") or ""), set())
    if event.get("action") not in expected_actions:
        problems.append("semantic_receipt_event:action")
    for field in (
        "task_id",
        "checkpoint_id",
        "receipt_id",
        "receipt_sha256",
        "event_head_sha256",
        "event_head_bytes",
        "semantic_epoch",
    ):
        if event.get(field) != receipt.get(field):
            problems.append(f"semantic_receipt_event:{field}")
    return problems


def _semantic_receipt_runtime_integrity_problems(
    task: dict[str, Any],
    receipt: dict[str, object],
) -> list[str]:
    return [
        *semantic_receipt_integrity_problems(task, receipt),
        *_semantic_receipt_event_problems(task, receipt),
    ]


def semantic_checkpoint_task(args: argparse.Namespace) -> TransitionResult:
    evidence = require_text(args.evidence, "evidence")
    if args.actor not in OFFICES:
        raise ValueError("unknown_actor_office")
    context = _semantic_context_from_args(args)
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        _require_case_semantic_context(task, context)
        receipt_sequence = len(_semantic_receipt_history(task)) + 1
        receipt = build_semantic_receipt(
            task,
            context,
            event_head_id=_event_head_id(str(task["task_id"])),
            trigger=args.trigger,
            created_at=now_text(),
            receipt_sequence=receipt_sequence,
        )
        task["semantic_context"] = context
        receipt = _append_semantic_receipt(task, receipt)
        task["semantic_state"] = "VERIFIED"
        task["semantic_verified_at"] = receipt["created_at"]
        task["updated_at"] = now_text()
        task["last_evidence"] = evidence
        tasks[args.task_id] = task
        event = make_event(
            task,
            "semantic_checkpoint",
            str(task.get("state") or "Pending"),
            str(task.get("state") or "Pending"),
            args.actor,
            evidence,
            args.note,
        )
        event.update(
            checkpoint_id=receipt["checkpoint_id"],
            receipt_id=receipt["receipt_id"],
            case_ref=case_reference(task),
            event_head_id=receipt["event_head_id"],
            semantic_epoch=receipt["semantic_epoch"],
            semantic_verdict="VERIFIED",
        )
        _commit_task_event(tasks, event)
    return TransitionResult(task, event)


def semantic_verify_task(args: argparse.Namespace) -> TransitionResult:
    evidence = require_text(args.evidence, "evidence")
    if args.actor not in OFFICES:
        raise ValueError("unknown_actor_office")
    context = _semantic_context_from_args(args)
    drift_error = ""
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        _require_case_semantic_context(task, context)
        if task.get("semantic_state") not in {"VERIFIED", "DISPATCHABLE"}:
            raise ValueError("semantic_checkpoint_not_verified")
        checkpoint_receipt = _current_checkpoint_receipt(task)
        integrity_problems = _semantic_receipt_runtime_integrity_problems(
            task,
            checkpoint_receipt,
        )
        if integrity_problems:
            raise ValueError(
                "semantic_receipt_integrity_failed:" + ",".join(integrity_problems)
            )
        problems = verify_semantic_receipt(task, checkpoint_receipt, context)
        receipt_sequence = len(_semantic_receipt_history(task)) + 1
        receipt_time = now_text()
        if problems:
            receipt = derive_semantic_receipt(
                checkpoint_receipt,
                receipt_sequence=receipt_sequence,
                gate="semantic_verify",
                verdict="QUARANTINED",
                trigger=args.trigger,
                reason_codes=problems,
                created_at=receipt_time,
                event_head_id=_event_head_id(str(task["task_id"])),
                updates={"quarantined_at": receipt_time},
            )
            task["semantic_state"] = "QUARANTINED"
            task["semantic_quarantined_at"] = receipt_time
            action = "semantic_quarantine"
            verdict = "QUARANTINED"
            drift_error = "semantic_drift_quarantined:" + ",".join(problems)
        else:
            verified_at = receipt_time
            receipt = derive_semantic_receipt(
                checkpoint_receipt,
                receipt_sequence=receipt_sequence,
                gate="semantic_verify",
                verdict="DISPATCHABLE",
                trigger=args.trigger,
                reason_codes=[],
                created_at=verified_at,
                event_head_id=_event_head_id(str(task["task_id"])),
                updates={"verified_at": verified_at},
            )
            task["semantic_context"] = context
            task["semantic_state"] = "DISPATCHABLE"
            task.setdefault("semantic_dispatchable_at", verified_at)
            verifications = task.setdefault("semantic_verifications", [])
            if not isinstance(verifications, list):
                raise ValueError("semantic_verification_history_corrupt")
            verifications.append(
                {
                    "schema": "court.semantic.verification.v1",
                    "checkpoint_id": receipt.get("checkpoint_id"),
                    "semantic_epoch": receipt.get("semantic_epoch"),
                    "trigger": args.trigger,
                    "verdict": "DISPATCHABLE",
                    "receipt_id": receipt["receipt_id"],
                    "context": deepcopy(context),
                    "verified_at": verified_at,
                }
            )
            action = "semantic_verify"
            verdict = "DISPATCHABLE"
        receipt = _append_semantic_receipt(task, receipt)
        task["updated_at"] = now_text()
        task["last_evidence"] = evidence
        tasks[args.task_id] = task
        event = make_event(
            task,
            action,
            str(task.get("state") or "Pending"),
            str(task.get("state") or "Pending"),
            args.actor,
            evidence,
            args.note,
        )
        event.update(
            checkpoint_id=receipt["checkpoint_id"],
            receipt_id=receipt["receipt_id"],
            case_ref=case_reference(task),
            event_head_id=receipt["event_head_id"],
            semantic_epoch=receipt["semantic_epoch"],
            semantic_verdict=verdict,
            reason_codes=list(receipt.get("reason_codes") or []),
        )
        _commit_task_event(tasks, event)
    if drift_error:
        raise ValueError(drift_error)
    return TransitionResult(task, event)


def semantic_resume_task(args: argparse.Namespace) -> TransitionResult:
    if str(getattr(args, "to_state", "") or "") != "ThreeDepartments":
        raise ValueError("semantic_resume_requires_three_departments")
    evidence = require_text(args.evidence, "evidence")
    if args.actor not in OFFICES:
        raise ValueError("unknown_actor_office")
    gate = validate_conversation_gate(
        _json_object_from_args(
            args,
            "continuation_gate",
            "continuation_file",
            "task continuation gate",
        )
    )
    if (
        gate.get("message_class") != "TASK_CONTINUATION"
        or gate.get("relation_to_active_decree") != "CONTINUES"
        or gate.get("next_route") != "THREE_DEPARTMENTS"
    ):
        raise ValueError("task_continuation_gate_required")
    if gate.get("target_task_id") != args.task_id:
        raise ValueError("task_continuation_target_mismatch")
    context = _semantic_context_from_args(args)
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        if task.get("state") != "Paused":
            raise ValueError("semantic_resume_requires_paused_task")
        if task.get("semantic_epoch") != args.expected_semantic_epoch:
            raise ValueError("stale_semantic_epoch")
        supplied_case_ref = getattr(args, "case_ref", None)
        if supplied_case_ref is not None and case_reference(supplied_case_ref) != case_reference(task):
            raise ValueError("stale_charter_case_ref")
        receipt = task.get("semantic_receipt")
        if not isinstance(receipt, dict):
            raise ValueError("semantic_receipt_missing")
        integrity_problems = _semantic_receipt_runtime_integrity_problems(
            task,
            receipt,
        )
        if integrity_problems:
            raise ValueError(
                "semantic_receipt_integrity_failed:"
                + ",".join(integrity_problems)
            )
        if receipt.get("checkpoint_id") != args.expected_checkpoint_id:
            raise ValueError("stale_semantic_checkpoint")
        if task.get("semantic_state") != "DISPATCHABLE":
            raise ValueError("semantic_resume_receipt_not_dispatchable")
        normalized_context, problems = resume_context_problems(receipt, context)
        if problems:
            raise ValueError("semantic_resume_drift:" + ",".join(problems))
        now = now_text()
        authority_changed = any(
            receipt.get(field) != normalized_context.get(field)
            for field in ("authority_revision", "authority_sha256")
        )
        resumed_receipt = derive_semantic_receipt(
            receipt,
            receipt_sequence=len(_semantic_receipt_history(task)) + 1,
            gate="semantic_resume",
            verdict="REVERIFY",
            trigger=args.trigger,
            reason_codes=["authority_revision_updated"] if authority_changed else [],
            created_at=now,
            event_head_id=_event_head_id(str(task["task_id"])),
            updates={**normalized_context, "resumed_at": now},
        )
        invalidations = task.setdefault("semantic_invalidations", [])
        if not isinstance(invalidations, list):
            raise ValueError("semantic_invalidation_history_corrupt")
        invalidations.append(
            {
                "schema": "court.semantic.invalidation.v1",
                "reason": "semantic_resume_reverify",
                "semantic_epoch": task.get("semantic_epoch"),
                "invalidated_at": now,
                "actor": args.actor,
                "evidence": evidence,
                "outcome_assessment": deepcopy(task.get("outcome_assessment")),
                "assessment_binding": deepcopy(task.get("assessment_binding")),
                "shiguan_checkpoint": deepcopy(task.get("shiguan_checkpoint")),
                "completion": deepcopy(task.get("completion")),
                "dispatch_plan": deepcopy(task.get("dispatch_plan")),
                "agent_admissions": deepcopy(task.get("agent_admissions")),
                "agents": deepcopy(task.get("agents")),
                "semantic_dispatch_attempts": deepcopy(
                    task.get("semantic_dispatch_attempts")
                ),
                "task_point_capsules": deepcopy(task.get("task_point_capsules")),
            }
        )
        task["outcome_assessment"] = _unassessed_outcome()
        task["assessment_binding"] = {}
        task["shiguan_checkpoint"] = {}
        task["completion"] = {"status": "INVALIDATED_BY_SEMANTIC_RESUME"}
        dispatch_plan = task.get("dispatch_plan")
        if isinstance(dispatch_plan, dict) and dispatch_plan:
            task["dispatch_plan"] = {
                **dict(dispatch_plan),
                "status": "INVALIDATED_BY_SEMANTIC_RESUME",
                "invalidated_at": now,
            }
        admissions = task.get("agent_admissions")
        if isinstance(admissions, dict):
            task["agent_admissions"] = {
                str(wave_id): {
                    **dict(record),
                    "status": "INVALIDATED_BY_SEMANTIC_RESUME",
                    "invalidated_at": now,
                }
                if isinstance(record, dict)
                else record
                for wave_id, record in admissions.items()
            }
        agents = task.get("agents")
        if isinstance(agents, dict):
            invalidated_agents: dict[str, object] = {}
            for agent_id, record in agents.items():
                if not isinstance(record, dict):
                    invalidated_agents[str(agent_id)] = record
                    continue
                invalidated = dict(record)
                invalidated.update(
                    assignment_status="INVALIDATED_BY_SEMANTIC_RESUME",
                    assignment_invalidated_by_semantic_resume=True,
                    invalidated_at=now,
                )
                if str(record.get("status") or "") not in TERMINAL_AGENT_STATUSES:
                    invalidated.update(
                        status="invalidated",
                        final_status="invalidated",
                        release_status="closed",
                        finished_at=record.get("finished_at") or now,
                        closed_at=record.get("closed_at") or now,
                    )
                invalidated_agents[str(agent_id)] = invalidated
            task["agents"] = invalidated_agents
        for field in ("semantic_dispatch_attempts", "task_point_capsules"):
            records = task.get(field)
            if isinstance(records, list):
                task[field] = [
                    {
                        **dict(record),
                        "status": "INVALIDATED_BY_SEMANTIC_RESUME",
                        "invalidated_at": now,
                    }
                    if isinstance(record, dict)
                    else record
                    for record in records
                ]
        task["conversation_gate"] = deepcopy(gate)
        task["state"] = "ThreeDepartments"
        task["semantic_context"] = normalized_context
        resumed_receipt = _append_semantic_receipt(task, resumed_receipt)
        task["semantic_state"] = "REVERIFY"
        state_history = list(task.get("semantic_state_history") or [])
        state_history.append(
            {
                "state": "REVERIFY",
                "semantic_epoch": task.get("semantic_epoch"),
                "trigger": "resume",
                "created_at": now,
            }
        )
        task["semantic_state_history"] = state_history
        task["resumed_at"] = now
        task["updated_at"] = now
        task["last_evidence"] = evidence
        tasks[args.task_id] = task
        event = make_event(
            task,
            "semantic_resume",
            "Paused",
            "ThreeDepartments",
            args.actor,
            evidence,
            args.note,
        )
        event.update(
            checkpoint_id=resumed_receipt["checkpoint_id"],
            receipt_id=resumed_receipt["receipt_id"],
            semantic_epoch=resumed_receipt["semantic_epoch"],
            semantic_verdict="REVERIFY",
            authority_revision=normalized_context["authority_revision"],
            authority_changed=authority_changed,
        )
        _commit_task_event(tasks, event)
    return TransitionResult(task, event)


def semantic_quarantine_task(args: argparse.Namespace) -> TransitionResult:
    evidence = require_text(args.evidence, "evidence")
    if args.actor not in OFFICES:
        raise ValueError("unknown_actor_office")
    trigger = require_text(args.trigger, "trigger")
    raw_reasons = getattr(args, "reason_code", None)
    if not isinstance(raw_reasons, list) or not raw_reasons:
        raise ValueError("semantic_quarantine_reason_required")
    reason_codes = [str(reason).strip() for reason in raw_reasons]
    if any(not reason for reason in reason_codes):
        raise ValueError("semantic_quarantine_reason_required")
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        expectations = _semantic_admission_expectations(task, args)
        history = task.setdefault("semantic_quarantines", [])
        if not isinstance(history, list):
            raise ValueError("semantic_quarantine_history_corrupt")
        quarantined_at = now_text()
        current_receipt = task.get("semantic_receipt")
        if not isinstance(current_receipt, dict):
            raise ValueError("semantic_receipt_missing")
        quarantine_receipt = derive_semantic_receipt(
            current_receipt,
            receipt_sequence=len(_semantic_receipt_history(task)) + 1,
            gate="semantic_quarantine",
            verdict="QUARANTINED",
            trigger=trigger,
            reason_codes=reason_codes,
            created_at=quarantined_at,
            event_head_id=_event_head_id(str(task["task_id"])),
            updates={"quarantined_at": quarantined_at},
        )
        quarantine_receipt = _append_semantic_receipt(task, quarantine_receipt)
        metadata = {
            "schema": "court.semantic.quarantine.v1",
            "sequence": len(history) + 1,
            "task_id": args.task_id,
            **expectations,
            "trigger": trigger,
            "reason_codes": reason_codes,
            "actor": args.actor,
            "evidence": evidence,
            "quarantined_at": quarantined_at,
            "receipt_id": quarantine_receipt["receipt_id"],
        }
        history.append(metadata)
        task["semantic_quarantine"] = metadata
        task["semantic_state"] = "QUARANTINED"
        task["semantic_quarantined_at"] = quarantined_at
        task["updated_at"] = quarantined_at
        task["last_evidence"] = evidence
        tasks[args.task_id] = task
        event = make_event(
            task,
            "semantic_quarantine",
            str(task.get("state") or "Pending"),
            str(task.get("state") or "Pending"),
            args.actor,
            evidence,
            args.note,
        )
        event.update(
            checkpoint_id=expectations["checkpoint_id"],
            receipt_id=quarantine_receipt["receipt_id"],
            semantic_epoch=expectations["semantic_epoch"],
            semantic_verdict="QUARANTINED",
            trigger=trigger,
            reason_codes=reason_codes,
            quarantine_sequence=metadata["sequence"],
        )
        _commit_task_event(tasks, event)
    return TransitionResult(task, event)


def semantic_reconcile_task(args: argparse.Namespace) -> TransitionResult:
    evidence = require_text(args.evidence, "evidence")
    if args.actor not in OFFICES:
        raise ValueError("unknown_actor_office")
    resolution_code = require_text(args.resolution_code, "resolution-code")
    context = _semantic_context_from_args(args)
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        if task.get("semantic_state") != "QUARANTINED":
            raise ValueError("semantic_reconcile_requires_quarantine")
        expectations = _expected_semantic_binding(
            task,
            args,
            require_dispatchable=False,
        )
        receipt = task.get("semantic_receipt")
        if not isinstance(receipt, dict):
            raise ValueError("semantic_receipt_missing")
        checkpoint_receipt = _current_checkpoint_receipt(task)
        problems = verify_semantic_receipt(task, checkpoint_receipt, context)
        if problems:
            raise ValueError("semantic_reconcile_drift:" + ",".join(problems))
        history = task.setdefault("semantic_reconciliations", [])
        if not isinstance(history, list):
            raise ValueError("semantic_reconciliation_history_corrupt")
        reconciled_at = now_text()
        metadata = {
            "schema": "court.semantic.reconciliation.v1",
            "sequence": len(history) + 1,
            "task_id": args.task_id,
            **expectations,
            "context_sha256": hashlib.sha256(
                json.dumps(
                    context,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "resolution_code": resolution_code,
            "actor": args.actor,
            "evidence": evidence,
            "reconciled_at": reconciled_at,
            "next_gate": "semantic_checkpoint",
        }
        reconciled_receipt = derive_semantic_receipt(
            receipt,
            receipt_sequence=len(_semantic_receipt_history(task)) + 1,
            gate="semantic_reconcile",
            verdict="REVERIFY",
            trigger="reconcile",
            reason_codes=[],
            created_at=reconciled_at,
            event_head_id=_event_head_id(str(task["task_id"])),
            updates={
                **context,
                "reconciled_at": reconciled_at,
                "resolution_code": resolution_code,
            },
        )
        reconciled_receipt = _append_semantic_receipt(task, reconciled_receipt)
        metadata["receipt_id"] = reconciled_receipt["receipt_id"]
        history.append(metadata)
        task["semantic_reconciliation"] = metadata
        task["semantic_context"] = context
        task["semantic_state"] = "REVERIFY"
        task["updated_at"] = reconciled_at
        task["last_evidence"] = evidence
        tasks[args.task_id] = task
        event = make_event(
            task,
            "semantic_reconcile",
            str(task.get("state") or "Pending"),
            str(task.get("state") or "Pending"),
            args.actor,
            evidence,
            args.note,
        )
        event.update(
            checkpoint_id=expectations["checkpoint_id"],
            receipt_id=reconciled_receipt["receipt_id"],
            semantic_epoch=expectations["semantic_epoch"],
            semantic_verdict="REVERIFY",
            resolution_code=resolution_code,
            reconciliation_sequence=metadata["sequence"],
        )
        _commit_task_event(tasks, event)
    return TransitionResult(task, event)


def bind_assessment_task(args: argparse.Namespace) -> TransitionResult:
    if args.actor not in OFFICES:
        raise ValueError("unknown_actor_office")
    assessment = _json_object_from_args(
        args,
        "assessment",
        "assessment_file",
        "outcome assessment",
    )
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        if task.get("charter_revision") != args.expected_revision:
            raise ValueError("stale_charter_revision")
        supplied_case_ref = _required_context_object(getattr(args, "case_ref", None), "case_ref_required")
        if case_reference(supplied_case_ref) != case_reference(task):
            raise ValueError("stale_charter_case_reference")
        existing_binding = task.get("assessment_binding")
        source_envelope = deepcopy(assessment)
        validated = validate_runtime_assessment_binding(task, source_envelope)
        source_envelope_ref = _source_envelope_ref(source_envelope)
        incoming_sha256 = validated["assessment_ref"]
        if isinstance(existing_binding, dict) and existing_binding:
            _revalidate_stored_assessment_binding(task)
            if (
                existing_binding.get("source_envelope_ref") != source_envelope_ref
                or existing_binding.get("source_envelope") != source_envelope
            ):
                raise ValueError("assessment_binding_conflict")
            matching_events = [
                event
                for event in read_events(limit=1000, task_id=args.task_id)
                if event.get("action") == "bind_assessment"
                and event.get("assessment_ref") == incoming_sha256
            ]
            if not matching_events:
                raise ValueError("assessment_binding_event_missing")
            return TransitionResult(deepcopy(task), deepcopy(matching_events[-1]))
        bound = bind_assessment_record(task, source_envelope)
        bound["updated_at"] = now_text()
        bound["last_evidence"] = args.evidence
        tasks[args.task_id] = bound
        event = make_event(
            bound,
            "bind_assessment",
            str(task.get("state") or "MenxiaReview"),
            str(bound.get("state") or "MenxiaReview"),
            args.actor,
            args.evidence,
            args.note,
        )
        event["assessment_ref"] = bound["assessment_binding"]["assessment_ref"]
        event["assessment_gate"] = bound["assessment_binding"]["gate"]
        _commit_task_event(tasks, event)
    return TransitionResult(bound, event)


def make_event(
    task: dict[str, Any],
    action: str,
    from_state: str,
    to_state: str,
    actor: str,
    evidence: str,
    note: str,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        **({"case_ref": case_reference(task)} if task.get("court_code") else {}),
        "time": now_text(),
        "task_id": task.get("task_id"),
        "action": action,
        "from_state": from_state,
        "to_state": to_state,
        "actor": actor,
        "owner": task.get("owner"),
        "report_tier": task.get("report_tier"),
        "read_only": task.get("read_only", False),
        "evidence": evidence,
        "note": note,
    }


def apply_transition(
    args: argparse.Namespace,
    control_context: bool = False,
    extra_updates: dict[str, Any] | None = None,
) -> TransitionResult:
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        from_state = str(task.get("state") or "Pending")
        to_state = args.to_state
        if to_state not in STATES:
            raise ValueError(f"unknown state: {to_state}")
        if to_state in {"ThreeDepartmentsPetition", "TaiziReply", "ShangshuDispatch", "SixMinistries", "Workshops", "MenxiaReview", "ShiguanRecorded", "Done"}:
            _require_case_reviewed(task)
        validate_runtime_gate(task, from_state, to_state, args.evidence, control_context)
        actor = args.actor
        if actor not in OFFICES:
            raise ValueError(f"unknown actor office: {actor}")
        task.setdefault("runtime_schema_version", RUNTIME_SCHEMA_VERSION)
        task.setdefault("agent_runtime", default_agent_runtime())
        task["state"] = to_state
        task["owner"] = args.owner or actor
        task["updated_at"] = now_text()
        task["last_evidence"] = args.evidence
        if args.heartbeat:
            task["heartbeat"] = args.heartbeat
        if to_state == "Paused":
            task["paused_from"] = from_state
        if from_state == "Paused" and to_state != "Cancelled":
            task.pop("paused_from", None)
        if extra_updates:
            task.update(extra_updates)
        tasks[args.task_id] = task
        event = make_event(task, "transition", from_state, to_state, actor, args.evidence, args.note)
        _commit_task_event(tasks, event)
    return TransitionResult(task, event)


def transition_task(args: argparse.Namespace) -> TransitionResult:
    return apply_transition(args, control_context=False)


def require_text(value: str, name: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def require_exact_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value


def pause_task(args: argparse.Namespace) -> TransitionResult:
    reason = require_text(args.reason, "reason")
    evidence_preserved = require_text(args.evidence_preserved, "evidence-preserved")
    unsafe_remaining = require_text(args.unsafe_remaining, "unsafe-remaining")
    affected_scope = require_text(args.affected_scope, "affected-scope")
    evidence = (
        f"pause reason={reason}; affected_scope={affected_scope}; "
        f"evidence_preserved={evidence_preserved}; unsafe_remaining={unsafe_remaining}"
    )
    transition_args = argparse.Namespace(
        task_id=args.task_id,
        to_state="Paused",
        actor=args.actor,
        owner="",
        heartbeat="paused",
        evidence=evidence,
        note=args.note or "pause",
    )
    return apply_transition(
        transition_args,
        control_context=True,
        extra_updates={
            "paused_at": now_text(),
            "stop_condition": reason,
            "affected_scope": affected_scope,
            "evidence_preserved": evidence_preserved,
            "unsafe_remaining": unsafe_remaining,
        },
    )


def resume_task(args: argparse.Namespace) -> TransitionResult:
    resume_evidence = require_text(args.resume_evidence, "resume-evidence")
    affected_scope = require_text(args.affected_scope, "affected-scope")
    if args.to_state in {"Done", "ShiguanRecorded"}:
        raise ValueError("illegal paused resume target")
    if args.from_paused_state:
        task = load_tasks().get(args.task_id, {})
        paused_from = str(task.get("paused_from") or "")
        if paused_from != args.from_paused_state:
            raise ValueError(f"paused_from mismatch: expected {args.from_paused_state}, found {paused_from}")
    evidence = f"resume evidence={resume_evidence}; affected_scope={affected_scope}; to_state={args.to_state}"
    transition_args = argparse.Namespace(
        task_id=args.task_id,
        to_state=args.to_state,
        actor=args.actor,
        owner="",
        heartbeat="alive",
        evidence=evidence,
        note=args.note or "resume",
    )
    return apply_transition(
        transition_args,
        control_context=True,
        extra_updates={
            "resumed_at": now_text(),
            "resume_target_validated": True,
            "affected_scope": affected_scope,
            "stop_condition": "",
        },
    )


def cancel_task(args: argparse.Namespace) -> TransitionResult:
    reason = require_text(args.reason, "reason")
    evidence_preserved = require_text(args.evidence_preserved, "evidence-preserved")
    unsafe_remaining = require_text(args.unsafe_remaining, "unsafe-remaining")
    affected_scope = require_text(args.affected_scope, "affected-scope")
    evidence = (
        f"cancel reason={reason}; affected_scope={affected_scope}; "
        f"evidence_preserved={evidence_preserved}; unsafe_remaining={unsafe_remaining}"
    )
    transition_args = argparse.Namespace(
        task_id=args.task_id,
        to_state="Cancelled",
        actor=args.actor,
        owner="",
        heartbeat="cancelled",
        evidence=evidence,
        note=args.note or "cancel",
    )
    return apply_transition(
        transition_args,
        control_context=True,
        extra_updates={
            "cancelled_at": now_text(),
            "stop_condition": reason,
            "affected_scope": affected_scope,
            "evidence_preserved": evidence_preserved,
            "unsafe_remaining": unsafe_remaining,
        },
    )


def agent_admit(args: argparse.Namespace) -> dict[str, Any]:
    evidence = require_text(args.evidence, "evidence")
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        wave_id = str(getattr(args, "wave_id", "") or "wave-default")
        existing_admissions = task.get("agent_admissions")
        if existing_admissions is not None and not isinstance(existing_admissions, dict):
            raise ValueError("agent admission ledger is corrupt")
        if isinstance(existing_admissions, dict) and wave_id in existing_admissions:
            raise ValueError(f"agent admission wave already exists: {wave_id}")
        semantic_expectations = _semantic_admission_expectations(task, args)
        context_economy = (
            _validate_context_economy_request(task, args, wave_id=wave_id)
            if _context_contract_required(args)
            else None
        )
        execution_topology = str(
            getattr(args, "execution_topology", "auto") or "auto"
        ).lower()
        serial_override = task_serial_override(task, execution_topology)
        if not serial_override:
            _validate_canonical_admission_preloads(args)
        now = now_text()
        attempt: int | None = None
        dispatch_uid: str | None = None
        if semantic_expectations is not None and not serial_override:
            try:
                attempt = int(task.get("next_semantic_dispatch_attempt") or 1)
            except (TypeError, ValueError) as exc:
                raise ValueError("semantic_dispatch_attempt_corrupt") from exc
            if attempt < 1:
                raise ValueError("semantic_dispatch_attempt_corrupt")
            prior_dispatches = task.get("semantic_dispatch_attempts")
            if prior_dispatches is not None and not isinstance(prior_dispatches, list):
                raise ValueError("semantic_dispatch_attempts_corrupt")
            if any(
                isinstance(item, dict) and item.get("attempt") == attempt
                for item in prior_dispatches or ()
            ):
                raise ValueError("semantic_dispatch_attempt_conflict")
            dispatch_uid = "DSP-" + uuid.uuid4().hex
            generated_child_instance_ids = _generate_missing_child_office_profiles(
                args,
                task_id=str(args.task_id),
                dispatch_uid=dispatch_uid,
                attempt=attempt,
                generated_at=now,
                semantic_expectations=semantic_expectations,
                context_economy=context_economy,
            )
            _synchronize_approved_child_bindings(
                args,
                generated_child_instance_ids,
            )
        result = evaluate_agent_admission(task, args)
        if context_economy is not None:
            result.update(context_economy)
        model_routes = {
            str(binding["instance_id"]): route_office_model(
                transport=args.transport,
                protocol=str(result.get("selected_protocol") or "v2"),
                role=str(binding["role"]),
                assignment=args.assignment,
                task_focus=args.task_focus,
                complexity=args.complexity,
                risk=args.risk,
                ambiguity=args.ambiguity,
            )
            for binding in result.get("selected_bindings", ())
        }
        result["model_route_inputs"] = {
            "assignment": args.assignment,
            "task_focus": args.task_focus,
            "complexity": args.complexity,
            "risk": args.risk,
            "ambiguity": args.ambiguity,
            "transport": args.transport,
            "requested_protocol_mode": str(getattr(args, "protocol_mode", "auto") or "auto"),
            "selected_protocol": result.get("selected_protocol"),
        }
        result["model_routes"] = model_routes
        result["generated_at"] = now
        result["admission_bindings"] = {}
        if result.get("allowed") is not True:
            return result
        if isinstance(task.get("case_binding"), dict):
            from court_case_binding import refresh_case_binding
            from court_plan_artifacts import require_reviewed_plan
            _require_case_semantic_context(task, task.get("semantic_receipt", {}))
            selected_roles = set(result.get("selected_roles") or [])
            consultation = selected_roles <= {"zhongshu", "menxia", "shangshu"}
            if not consultation:
                plan = require_reviewed_plan(task)
                if task.get("state") not in {"ShangshuDispatch", "SixMinistries", "Workshops"}:
                    raise ValueError("case_ministry_dispatch_before_taizi_reply")
                planned_roles = {step["role"] for step in plan["document"]["steps"]}
                if not selected_roles <= planned_roles:
                    raise ValueError("case_dispatch_roles_outside_reviewed_plan")
            result["case_binding"] = refresh_case_binding(task)
        _validate_admission_capsule_write_scope(task, result.get("selected_bindings"))
        if semantic_expectations is not None:
            if attempt is None or dispatch_uid is None:
                raise ValueError("semantic_dispatch_identity_missing")
            enriched_bindings: list[dict[str, object]] = []
            reserved_write_claims: set[str] = set()
            for raw_binding in result.get("selected_bindings", ()):
                if not isinstance(raw_binding, dict):
                    raise ValueError("agent admission binding is invalid")
                binding = _allocate_office_binding(
                    task,
                    dict(raw_binding),
                    require_lineage=bool(
                        getattr(args, "_office_lifecycle_explicit", False)
                    ),
                    reserved_write_claims=reserved_write_claims,
                )
                role_key = str(binding.get("role") or "")
                binding.update(
                    task_id=args.task_id,
                    **semantic_expectations,
                    dispatch_uid=dispatch_uid,
                    attempt=attempt,
                    office_instance_id=str(binding.get("instance_id") or ""),
                    worktree=str(binding.get("worktree") or "."),
                    lease_id=str(result.get("budget_lease_id") or ""),
                    preload_sources=_semantic_preload_sources(role_key),
                )
                if context_economy is not None:
                    binding.update(
                        {
                            field: context_economy[field]
                            for field in CONTEXT_ECONOMY_BINDING_FIELDS
                        }
                    )
                binding["office_capsule_ref"] = office_capsule_reference(case_reference(task), role_key, str(binding["office_instance_id"]), now)
                enriched_bindings.append(binding)
            admission_bindings = {
                str(binding.get("instance_id") or "").strip().lower():
                deepcopy(binding)
                for binding in enriched_bindings
                if isinstance(binding.get("child_profile"), Mapping)
            }
            result.update(
                selected_bindings=tuple(enriched_bindings),
                admission_bindings=admission_bindings,
                dispatch_uid=dispatch_uid,
                attempt=attempt,
                **semantic_expectations,
            )
            task["next_semantic_dispatch_attempt"] = attempt + 1
            dispatches = task.setdefault("semantic_dispatch_attempts", [])
            if not isinstance(dispatches, list):
                raise ValueError("semantic_dispatch_attempts_corrupt")
            dispatches.append(
                {
                    "dispatch_uid": dispatch_uid,
                    "attempt": attempt,
                    "wave_id": result["wave_id"],
                    "semantic_epoch": semantic_expectations["semantic_epoch"],
                    "status": "ADMITTED",
                    "created_at": now,
                }
            )
        admission_record = {
            key: result[key]
            for key in (
                "dispatch_requested_at",
                "generated_at",
                "task_id",
                "wave_id",
                "allowed",
                "decision",
                "parallel_dispatch",
                "requested_fork_turns",
                "recommended_fork_turns",
                "context_tokens",
                "wave_policy",
                "static_wave_cap",
                "selection_basis",
                "useful_roles",
                "selected_roles",
                "selected_bindings",
                "admission_bindings",
                "selected_instance_ids",
                "deferred_roles",
                "host_capacity",
                "host_active_agents",
                "host_retained_agents",
                "host_reclamation_status",
                "host_reclamation_verified",
                "available_slots",
                "user_agent_budget",
                "provider_launch_budget",
                "budget_lease",
                "budget_lease_id",
                "requested_bindings",
                "integration_domain",
                "authority",
                "calling_office",
                "direct_superior",
                "hierarchy_receipts",
                *(
                    _HIERARCHY_EVIDENCE_FIELDS
                    if result.get("hierarchy_gate") == "PASSED"
                    else ()
                ),
                "deadline_seconds",
                "tool_call_budget",
                *AGENT_MESSAGE_BUDGET_FIELDS,
                "protocol_decision",
                "selected_protocol",
                "model_route_inputs",
                "model_routes",
                *(
                    (
                        "dispatch_uid",
                        "attempt",
                        "semantic_epoch",
                        "case_ref",
                        "checkpoint_id",
                    )
                    if semantic_expectations is not None
                    else ()
                ),
                *(
                    CONTEXT_ECONOMY_BINDING_FIELDS
                    if context_economy is not None
                    else ()
                ),
            )
        }
        if "case_binding" in result:
            admission_record["case_binding"] = deepcopy(result["case_binding"])
        admission_record["admission_event_id"] = str(uuid.uuid4())
        result["admission_event_id"] = admission_record["admission_event_id"]
        task["last_agent_admission"] = admission_record
        admissions = task.setdefault("agent_admissions", {})
        if not isinstance(admissions, dict):
            admissions = {}
            task["agent_admissions"] = admissions
        admissions[result["wave_id"]] = admission_record
        task["updated_at"] = now
        task["last_evidence"] = f"agent_admit {result['decision']}: {evidence}"
        tasks[args.task_id] = task
        event = make_event(
            task,
            "agent_admit",
            str(task.get("state")),
            str(task.get("state")),
            args.actor,
            evidence,
            args.note,
        )
        event.update(
            wave_id=result["wave_id"],
            allowed=result["allowed"],
            decision=result["decision"],
            requested_fork_turns=result["requested_fork_turns"],
            model_route_ids={role: route["model_route_id"] for role, route in model_routes.items()},
            selected_protocol=result.get("selected_protocol"),
            admission_record=_admission_bound_record(admission_record),
        )
        if semantic_expectations is not None:
            event.update(
                dispatch_uid=result["dispatch_uid"],
                attempt=result["attempt"],
                semantic_epoch=result["semantic_epoch"],
                case_ref=deepcopy(result["case_ref"]),
                checkpoint_id=result["checkpoint_id"],
            )
        if context_economy is not None:
            event.update(
                {
                    field: context_economy[field]
                    for field in CONTEXT_ECONOMY_BINDING_FIELDS
                }
            )
        primary_instance_id = str(
            (result.get("selected_instance_ids") or ("",))[0]
            if result.get("selected_instance_ids")
            else ""
        )
        event["event_id"] = admission_record["admission_event_id"]
        result["event_id"] = event["event_id"]
        event.update({key: result[key] for key in AGENT_MESSAGE_BUDGET_FIELDS})
        _commit_task_event(tasks, event)
    return result


def office_admit(args: argparse.Namespace) -> dict[str, Any]:
    if not hasattr(args, "note") or getattr(args, "note") is None:
        args.note = ""
    _prepare_explicit_office_admission(args)
    result = agent_admit(args)
    if result.get("allowed") is not True:
        return result
    selected = result.get("selected_bindings")
    if not isinstance(selected, (list, tuple)) or len(selected) != 1:
        raise ValueError("office_admit_requires_single_instance")
    binding = dict(selected[0])
    binding["status"] = "admitted"
    task = load_tasks().get(str(args.task_id))
    if not isinstance(task, dict):
        raise ValueError(f"task not found: {args.task_id}")
    result["receipt"] = _office_lifecycle_receipt(
        task,
        binding,
        action="admit",
        event_id=result.get("event_id"),
    )
    result["kind"] = "court_office_admission"
    return result


def agent_reconcile(args: argparse.Namespace) -> dict[str, Any]:
    evidence = scrub_agent_provider_detail(require_text(args.evidence, "evidence"))
    result_text = scrub_agent_provider_detail(require_text(args.result, "result"))
    agent_id = require_text(args.agent_id, "agent-id")
    role = require_text(args.role, "role")
    error_kind = require_text(args.error_kind, "error-kind")
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        agents = task.get("agents")
        if not isinstance(agents, dict) or not isinstance(agents.get(agent_id), dict):
            raise ValueError(f"agent not found: {agent_id}")
        current = dict(agents[agent_id])
        now = now_text()
        wave_id = str(current.get("wave_id") or args.wave_id or "wave-default")
        current.update(
            {
                "agent_id": agent_id,
                "role": role,
                "status": "failed",
                "final_status": "failed",
                "release_status": "closed",
                "error_kind": error_kind,
                "result": result_text,
                "last_evidence": evidence,
                "last_heartbeat": now,
                "finished_at": current.get("finished_at") or now,
                "closed_at": now,
                "updated_at": now,
                "wave_id": wave_id,
            }
        )
        agents[agent_id] = current
        cancel_requested: list[str] = []
        for sibling_id, sibling in agents.items():
            if sibling_id == agent_id or not isinstance(sibling, dict):
                continue
            if str(sibling.get("wave_id") or "wave-default") != wave_id:
                continue
            if str(sibling.get("status") or "") in TERMINAL_AGENT_STATUSES:
                continue
            sibling["cancel_requested_at"] = now
            sibling["release_status"] = "cancel_requested"
            sibling["last_evidence"] = f"wave {wave_id} stopped after {error_kind}"
            sibling["updated_at"] = now
            cancel_requested.append(str(sibling_id))

        if error_kind in {"fatal-quota", "fatal-auth"}:
            circuit = {
                "state": "open",
                "scope": "task",
                "error_kind": error_kind,
                "opened_at": now,
                "wave_id": wave_id,
                "retry_allowed": False,
            }
            task["agent_circuit_breaker"] = circuit
            task["heartbeat"] = f"AGENT_CIRCUIT_OPEN/{error_kind}"
        elif error_kind == "capacity":
            circuit = {
                "state": "open",
                "scope": "wave",
                "error_kind": error_kind,
                "opened_at": now,
                "wave_id": wave_id,
                "retry_allowed": False,
                "reuse_errored_agents": False,
            }
            blocks = task.setdefault("agent_wave_blocks", {})
            if not isinstance(blocks, dict):
                blocks = {}
                task["agent_wave_blocks"] = blocks
            blocks[wave_id] = circuit
            task["heartbeat"] = f"AGENT_WAVE_BLOCKED/{wave_id}/capacity"
        else:
            circuit = {
                "state": "closed",
                "scope": "none",
                "error_kind": error_kind,
                "retry_allowed": error_kind == "retryable",
            }
            task["heartbeat"] = f"AGENT_RECONCILED/{error_kind}"
        task["updated_at"] = now
        task["last_evidence"] = f"agent_reconcile {agent_id} {error_kind}: {evidence}"
        tasks[args.task_id] = task
        event = make_event(
            task,
            "agent_reconcile",
            "running",
            "failed",
            args.actor,
            evidence,
            args.note,
        )
        event.update(agent_id=agent_id, agent_role=role, wave_id=wave_id, error_kind=error_kind)
        _commit_task_event(tasks, event)
    return {
        "kind": "court_agent_reconcile",
        "task_id": args.task_id,
        "agent": current,
        "circuit_breaker": circuit,
        "cancel_requested_agent_ids": cancel_requested,
        "raw_provider_detail_stored": False,
    }


def agent_spawn_failed(args: argparse.Namespace) -> dict[str, Any]:
    """Record a host refusal that happened before an agent lifecycle record existed."""

    evidence = scrub_agent_provider_detail(require_text(args.evidence, "evidence"))
    result_text = scrub_agent_provider_detail(require_text(args.result, "result"))
    role = require_text(args.role, "role")
    error_kind = require_text(args.error_kind, "error-kind")
    wave_id = require_text(args.wave_id, "wave-id")
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        _reject_native_host_receipt_replay(task, args)
        admissions = task.get("agent_admissions")
        admission = admissions.get(wave_id) if isinstance(admissions, dict) else None
        if not isinstance(admission, dict) or admission.get("allowed") is not True:
            raise ValueError(f"allowed agent admission not found: {wave_id}")
        _validate_admission_immutable_event_anchor(task, admission)
        selected_roles = list(admission.get("selected_roles") or [])
        if role not in selected_roles:
            raise ValueError("spawn-failed role was not selected by the admission")
        selected_bindings = admission.get("selected_bindings")
        if selected_bindings is not None and not isinstance(selected_bindings, (list, tuple)):
            raise ValueError("spawn-failed admission instance bindings are corrupt")
        role_bindings = [
            binding
            for binding in selected_bindings or ()
            if isinstance(binding, dict)
            and str(binding.get("role") or "").strip().lower() == role.lower()
        ]
        matched_binding: dict[str, object] | None = None
        requested_instance_id = str(getattr(args, "instance_id", "") or "").strip().lower()
        if role_bindings:
            matching_bindings = (
                [
                    binding
                    for binding in role_bindings
                    if str(binding.get("instance_id") or "").strip().lower()
                    == requested_instance_id
                ]
                if requested_instance_id
                else role_bindings
            )
            if len(matching_bindings) != 1:
                raise ValueError("spawn-failed requires one admitted instance-id")
            matched_binding = matching_bindings[0]
            instance_id = str(matched_binding.get("instance_id") or "").strip().lower()
        else:
            if selected_roles.count(role) != 1:
                raise ValueError("spawn-failed requires one admitted instance-id")
            instance_id = requested_instance_id or role.lower()
        model_routes = admission.get("model_routes")
        route_key = instance_id if role_bindings else role
        model_route = model_routes.get(route_key) if isinstance(model_routes, dict) else None
        if not isinstance(model_route, dict) or not str(model_route.get("model_route_id") or "").strip():
            raise ValueError("spawn-failed instance does not have an admitted model route")

        refusal_native_host_receipt: dict[str, object] | None = None
        if matched_binding is not None:
            refusal_native_host_receipt = _validate_native_host_receipt_for_runtime(
                task,
                admission,
                matched_binding,
                args,
                decision="spawn",
                host_action="spawn",
                outcome="refused",
            )
        elif bool(getattr(args, "_production_cli", False)) or getattr(
            args, "native_host_action_receipt", None
        ) is not None:
            raise ValueError("native_host_action_receipt:binding_missing")

        legacy_consumed_roles = admission.get("consumed_roles")
        if legacy_consumed_roles is not None and not isinstance(legacy_consumed_roles, dict):
            raise ValueError("spawn-failed admission consumption ledger is corrupt")
        if isinstance(legacy_consumed_roles, dict) and role in legacy_consumed_roles:
            raise ValueError("spawn-failed role already has a started agent")
        legacy_failed_roles = admission.get("failed_roles")
        if legacy_failed_roles is not None and not isinstance(legacy_failed_roles, dict):
            raise ValueError("spawn-failed admission failure ledger is corrupt")
        if isinstance(legacy_failed_roles, dict) and role in legacy_failed_roles:
            raise ValueError("spawn failure was already recorded for this role")
        consumed_instances = admission.get("consumed_instances")
        if consumed_instances is None:
            consumed_instances = {}
        if not isinstance(consumed_instances, dict):
            raise ValueError("spawn-failed admission consumption ledger is corrupt")
        if instance_id in consumed_instances:
            raise ValueError("spawn-failed instance already has a started agent")
        failed_instances = admission.get("failed_instances")
        if failed_instances is None:
            failed_instances = {}
            admission["failed_instances"] = failed_instances
        if not isinstance(failed_instances, dict):
            raise ValueError("spawn-failed admission failure ledger is corrupt")
        if instance_id in failed_instances:
            raise ValueError("spawn failure was already recorded for this instance")
        now = now_text()
        failure = {
            "role": role,
            "instance_id": instance_id,
            "model_route_id": str(model_route["model_route_id"]),
            "error_kind": error_kind,
            "result": result_text,
            "evidence": evidence,
            "recorded_at": now,
        }
        if refusal_native_host_receipt is not None:
            failure.update(
                _native_host_receipt_record_fields(refusal_native_host_receipt)
            )
        failed_instances[instance_id] = failure
        failed_instance_ids = set(failed_instances)
        consumed_instance_ids = set(consumed_instances)
        remaining_roles = [
            str(binding.get("role") or "").strip().lower()
            for binding in selected_bindings or ()
            if isinstance(binding, dict)
            and str(binding.get("instance_id") or "").strip().lower()
            not in failed_instance_ids | consumed_instance_ids
        ]
        if not selected_bindings:
            remaining_roles = [
                item
                for item in selected_roles
                if item not in (legacy_consumed_roles or {})
                and item not in (legacy_failed_roles or {})
                and item != role
            ]
        deferred_roles = list(
            dict.fromkeys([*(admission.get("deferred_roles") or []), *remaining_roles])
        )
        admission["deferred_roles"] = deferred_roles
        admission["effective_selected_instance_ids"] = list(consumed_instances)
        admission["effective_selected_roles"] = [
            str(binding.get("role") or "").strip().lower()
            for binding in selected_bindings or ()
            if isinstance(binding, dict)
            and str(binding.get("instance_id") or "").strip().lower()
            in consumed_instance_ids
        ]
        admission["observed_available_slots"] = len(consumed_instances)
        admission["spawn_failure"] = failure

        if error_kind == "capacity":
            circuit = {
                "state": "open",
                "scope": "wave",
                "error_kind": "capacity",
                "opened_at": now,
                "wave_id": wave_id,
                "retry_allowed": False,
                "reuse_errored_agents": False,
                "prestart_failure": True,
            }
            blocks = task.setdefault("agent_wave_blocks", {})
            if not isinstance(blocks, dict):
                raise ValueError("agent wave block ledger is corrupt")
            blocks[wave_id] = circuit
            task["heartbeat"] = f"AGENT_WAVE_BLOCKED/{wave_id}/capacity"
        else:
            circuit = {
                "state": "closed",
                "scope": "none",
                "error_kind": error_kind,
                "retry_allowed": error_kind == "retryable",
                "prestart_failure": True,
            }
            task["heartbeat"] = f"AGENT_SPAWN_FAILED/{wave_id}/{error_kind}"
        task["updated_at"] = now
        task["last_evidence"] = (
            f"agent_spawn_failed {wave_id} {role} {instance_id} {error_kind}: {evidence}"
        )
        if refusal_native_host_receipt is not None:
            _record_native_host_receipt(
                task,
                refusal_native_host_receipt,
                lifecycle_action="spawn_failed",
                target_id=instance_id,
            )
        tasks[args.task_id] = task
        event = make_event(
            task,
            "agent_spawn_failed",
            "admitted",
            "failed",
            args.actor,
            evidence,
            args.note,
        )
        event.update(
            wave_id=wave_id,
            agent_role=role,
            agent_instance_id=instance_id,
            error_kind=error_kind,
        )
        if refusal_native_host_receipt is not None:
            event.update(
                native_host_action_receipt_id=refusal_native_host_receipt.get(
                    "receipt_id"
                ),
                native_host_action_receipt_sha256=refusal_native_host_receipt.get(
                    "receipt_sha256"
                ),
            )
        _commit_task_event(tasks, event)
    return {
        "kind": "court_agent_spawn_failed",
        "task_id": args.task_id,
        "wave_id": wave_id,
        "failed_role": role,
        "failed_instance_id": instance_id,
        "deferred_roles": deferred_roles,
        "circuit_breaker": circuit,
        "raw_provider_detail_stored": False,
    }


def _recovery_operation_identity(
    task: Mapping[str, object],
    operation_id: object,
    payload: Mapping[str, object],
) -> tuple[str, str, dict[str, object] | None]:
    operation = str(operation_id or "").strip()
    if not operation:
        raise ValueError("result_recovery_operation_id_required")
    if result_recovery_marker_path(operation).exists():
        raise ValueError("result_recovery_journal_corrupt")
    payload_digest = canonical_json_sha256(dict(payload))
    operations = task.get("result_recovery_operations")
    if operations is not None and not isinstance(operations, Mapping):
        raise ValueError("result_recovery_ledger_corrupt")
    existing = operations.get(operation) if isinstance(operations, Mapping) else None
    if existing is not None and not isinstance(existing, Mapping):
        raise ValueError("result_recovery_operation_corrupt")
    if isinstance(existing, Mapping):
        if existing.get("payload_sha256") != payload_digest:
            raise ValueError("result_recovery_operation_conflict")
        receipt = existing.get("receipt")
        if not isinstance(receipt, dict):
            raise ValueError("result_recovery_operation_corrupt")
        return operation, payload_digest, dict(receipt)
    return operation, payload_digest, None


def _recovery_args(value: argparse.Namespace | Mapping[str, object]) -> argparse.Namespace:
    if isinstance(value, argparse.Namespace):
        return value
    if isinstance(value, Mapping):
        return argparse.Namespace(**dict(value))
    raise ValueError("result_recovery_arguments_required")


def _recovery_operation_store(
    task: dict[str, object],
    operation_id: str,
    payload_digest: str,
    receipt: Mapping[str, object],
    payload: Mapping[str, object] | None = None,
) -> None:
    _, operations, _ = _result_recovery_ledgers(task)
    operations[operation_id] = {
        "schema": RESULT_RECOVERY_OPERATION_SCHEMA,
        "operation_id": operation_id,
        "payload_sha256": payload_digest,
        "payload": deepcopy(dict(payload)) if payload is not None else {},
        "receipt": deepcopy(dict(receipt)),
        "status": "TASK_EVENT_COMMITTED",
        "recorded_at": now_text(),
    }
    receipts = task.setdefault("result_recovery_receipts", {})
    if not isinstance(receipts, dict):
        raise ValueError("result_recovery_ledger_corrupt")
    receipt_id = str(receipt.get("receipt_id") or "")
    if receipt_id:
        receipts[receipt_id] = deepcopy(dict(receipt))


def _build_recovery_receipt(
    *,
    schema: str,
    operation_id: str,
    task_id: str,
    task_revision: int,
    quarantine_id: str,
    recovery_id: str,
    recovery_revision: int,
    previous_head_sha256: str,
    reason_codes: list[str],
    evidence_pointer: str,
    evidence_sha256: str,
    actor: str,
    timestamp_field: str,
    timestamp: str,
    event_id: str,
    **extra: object,
) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema": schema,
        "receipt_id": "RR-" + hashlib.sha256(
            f"{schema}|{operation_id}|{event_id}".encode("utf-8")
        ).hexdigest()[:24].upper(),
        "operation_id": operation_id,
        "task_id": task_id,
        "task_revision": task_revision,
        "quarantine_id": quarantine_id,
        "recovery_id": recovery_id,
        "recovery_revision": recovery_revision,
        "previous_head_sha256": previous_head_sha256,
        "reason_codes": list(reason_codes),
        "evidence_pointer": evidence_pointer,
        "evidence_ref": evidence_sha256,
        "actor": actor,
        timestamp_field: timestamp,
        "event_id": event_id,
    }
    receipt.update(extra)
    receipt["receipt_sha256"] = _result_recovery_receipt_digest(receipt)
    return receipt


def _recovery_quarantine_context(
    task: Mapping[str, object],
    args: argparse.Namespace,
    *,
    require_payload: bool = True,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    quarantine_id = str(getattr(args, "quarantine_id", "") or "").strip()
    if quarantine_id:
        records = task.get("quarantined_results")
        if isinstance(records, list):
            for legacy in records:
                if isinstance(legacy, dict) and str(legacy.get("quarantine_id") or "") == quarantine_id:
                    if legacy.get("schema") == "court.office.result_quarantine.v1" or legacy.get("core_schema") != "court.office.result_quarantine.v2":
                        raise ValueError("result_recovery_legacy_read_only")
                core_value = legacy.get("core") if isinstance(legacy, dict) else None
                if isinstance(core_value, dict) and str(core_value.get("quarantine_id") or "") == quarantine_id and result_recovery_record_disposition(core_value) != "CURRENT_QUARANTINE_CORE":
                    raise ValueError("result_recovery_legacy_read_only")
    payload_value = getattr(args, "result_envelope", None)
    if payload_value is None and getattr(args, "result_envelope_file", None) is not None:
        payload_value = _json_object_from_args(
            args, "result_envelope", "result_envelope_file", "source result envelope"
        )
    if payload_value is None and getattr(args, "source_result", None) is not None:
        payload_value = getattr(args, "source_result")
    if payload_value is None and getattr(args, "source_result_envelope", None) is not None:
        payload_value = getattr(args, "source_result_envelope")
    if payload_value is None and getattr(args, "original_result_envelope", None) is not None:
        payload_value = getattr(args, "original_result_envelope")
    source_envelope: dict[str, object] = {}
    if payload_value is None:
        if require_payload:
            raise ValueError("result_quarantine_payload_required")
        core = _result_recovery_core_for_task(task, quarantine_id=quarantine_id)
    else:
        source_envelope = normalize_result_envelope(payload_value)
        payload_sha = source_result_payload_sha256(source_envelope)
        core = _result_recovery_core_for_task(
            task,
            quarantine_id=quarantine_id,
            payload_sha256=payload_sha,
        )
        if str(core.get("payload_sha256")) != payload_sha:
            raise ValueError("result_quarantine_payload_mismatch")
    records = task.get("quarantined_results")
    if not isinstance(records, list):
        raise ValueError("result_quarantine_not_found")
    metadata = next(
        (
            item for item in records
            if isinstance(item, dict)
            and isinstance(item.get("core"), dict)
            and item["core"].get("quarantine_id") == core.get("quarantine_id")
        ),
        None,
    )
    if not isinstance(metadata, dict):
        raise ValueError("result_quarantine_not_found")
    if result_recovery_record_disposition(core) != "CURRENT_QUARANTINE_CORE":
        raise ValueError("result_recovery_legacy_read_only")
    return core, metadata, source_envelope


def _recovery_expected_cas(
    task: Mapping[str, object],
    current_head: Mapping[str, object] | None,
    args: argparse.Namespace,
) -> tuple[int, str, int]:
    current_task_revision = _task_revision_value(task)
    expected_task_revision = getattr(args, "expected_task_revision", None)
    if expected_task_revision is None:
        expected_task_revision = current_task_revision
    if expected_task_revision != current_task_revision:
        raise ValueError("result_recovery_task_revision_conflict")
    current_revision = int(current_head.get("revision")) if current_head else 0
    current_head_sha256 = str(current_head.get("head_sha256")) if current_head else RESULT_RECOVERY_ZERO_SHA256
    expected_recovery_revision = getattr(args, "expected_recovery_revision", None)
    if expected_recovery_revision is None:
        expected_recovery_revision = current_revision
    expected_head_sha256 = str(
        getattr(args, "expected_head_sha256", None) or current_head_sha256
    ).lower()
    if expected_recovery_revision != current_revision:
        raise ValueError("result_recovery_revision_conflict")
    if expected_head_sha256 != current_head_sha256:
        raise ValueError("result_recovery_head_conflict")
    return current_task_revision, expected_head_sha256, int(expected_recovery_revision)


def _validate_recovery_receipt(
    value: object,
    schema_factory: object,
    *,
    expected_actor: str | None = None,
    expected_schema: str | None = None,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("result_recovery_receipt_required")
    schema = schema_factory()
    required = set(schema.get("required", [])) if isinstance(schema, dict) else set()
    if expected_schema is not None and value.get("schema") != expected_schema:
        raise ValueError("result_recovery_receipt_schema_mismatch")
    if value.get("schema") not in {
        "court.office.result_recovery_review_receipt.v1",
        "court.office.result_recovery_handoff_receipt.v1",
        "court.office.result_recovery_consume_receipt.v1",
    } or set(value) != required:
        raise ValueError("result_recovery_receipt_schema_mismatch")
    if expected_actor is not None and str(value.get("actor") or "").strip().lower() != expected_actor:
        raise ValueError("result_recovery_receipt_actor_mismatch")
    for field in ("evidence_ref", "receipt_sha256"):
        digest = value.get(field)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("result_recovery_receipt_digest_invalid")
    if _result_recovery_receipt_digest(value) != value["receipt_sha256"]:
        raise ValueError("result_recovery_receipt_digest_mismatch")
    reasons = value.get("reason_codes")
    if not isinstance(reasons, list) or not reasons or len(set(reasons)) != len(reasons) or any(
        reason not in RESULT_RECOVERY_REASON_CODES for reason in reasons
    ):
        raise ValueError("result_recovery_reason_code_invalid")
    return dict(value)


def _target_binding_from_record(task: Mapping[str, object], record: Mapping[str, object]) -> dict[str, object]:
    binding: dict[str, object] = {
        "task_id": task.get("task_id"),
        "semantic_epoch": record.get("semantic_epoch"),
        "checkpoint_id": record.get("checkpoint_id"),
        "dispatch_uid": record.get("dispatch_uid"),
        "attempt": record.get("attempt"),
        "office_instance_id": record.get("office_instance_id"),
        "office_instance_kind": record.get("office_instance_kind"),
        "carrier_proof": deepcopy(record.get("carrier_proof")),
        "agent_id": record.get("agent_id"),
        "role": record.get("role"),
        "direct_superior": record.get("direct_superior"),
        "worktree": record.get("worktree"),
        "write_set_sha256": canonical_json_sha256(record.get("write_set", [])),
        "hierarchy_schema": record.get("hierarchy_schema"),
        "hierarchy_gate": record.get("hierarchy_gate"),
        "hierarchy_edge_class": record.get("hierarchy_edge_class"),
        "preload_status": record.get("preload_status"),
        "office_execution_ready": record.get("office_execution_ready"),
        "status": record.get("status"),
        "final_status": record.get("final_status"),
        "release_status": record.get("release_status"),
        "result_state": record.get("result_state"),
    }
    if set(binding) != set(result_recovery_target_binding_fields()):
        raise ValueError("result_recovery_target_binding_schema_mismatch")
    return binding


def _target_binding_sha256(binding: Mapping[str, object]) -> str:
    return canonical_json_sha256(dict(binding))


def _validate_target_binding(
    task: Mapping[str, object],
    record: Mapping[str, object],
    supplied: object = None,
) -> tuple[dict[str, object], str]:
    binding = _target_binding_from_record(task, record)
    digest = _target_binding_sha256(binding)
    if supplied is not None and (not isinstance(supplied, Mapping) or dict(supplied) != binding):
        raise ValueError("result_recovery_target_mismatch")
    return binding, digest


def review_quarantined_result(args: argparse.Namespace) -> dict[str, object]:
    """Menxia-only review that creates an immutable projection and recovery head."""
    args = _recovery_args(args)
    actor = str(getattr(args, "actor", "") or "").strip().lower()
    if actor != "menxia":
        raise ValueError("result_recovery_actor_forbidden")
    decision = str(getattr(args, "decision", "ACCEPT") or "ACCEPT").strip().upper()
    if decision not in {"ACCEPT", "REJECT"}:
        raise ValueError("result_recovery_review_decision_invalid")
    evidence_pointer, evidence_sha256 = _result_recovery_evidence_pointer(args)
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(str(getattr(args, "task_id", "")))
        if not isinstance(task, dict):
            raise ValueError("task not found")
        require_semantic_mutation_binding(task)
        core, _metadata, source_envelope = _recovery_quarantine_context(task, args)
        history, _operations, _projections = _result_recovery_ledgers(task)
        recovery_id = str(
            getattr(args, "recovery_id", "") or "REC-" + str(core["quarantine_id"])
        ).strip()
        current_head = _recovery_head_for_task(task, recovery_id)
        reason_codes = getattr(args, "reason_codes", None) or []
        if isinstance(reason_codes, str):
            reason_codes = [item.strip() for item in reason_codes.split(",") if item.strip()]
        reason_codes = list(reason_codes)
        if not reason_codes:
            reason_codes = ["ACCEPT_BOUNDED_EVIDENCE" if decision == "ACCEPT" else "REJECT_UNVERIFIABLE"]
        if any(code not in RESULT_RECOVERY_REASON_CODES for code in reason_codes):
            raise ValueError("result_recovery_reason_code_invalid")
        projection = None
        projection_sha256 = RESULT_RECOVERY_ZERO_SHA256
        if decision == "ACCEPT":
            projection = build_result_recovery_projection(
                source_result=source_envelope,
                recovery_id=recovery_id,
                quarantine_id=str(core["quarantine_id"]),
            )
            projection_sha256 = str(projection["projection_sha256"])
        payload = {
            "decision": decision,
            "reason_codes": reason_codes,
            "evidence_pointer": evidence_pointer,
            "evidence_ref": evidence_sha256,
            "projection_sha256": projection_sha256,
            "recovery_id": recovery_id,
            "quarantine_id": core["quarantine_id"],
        }
        operation_id, payload_digest, replay = _recovery_operation_identity(
            task, getattr(args, "operation_id", None), payload
        )
        if replay is not None:
            return {"status": "REPLAYED", "operation_id": operation_id, "receipt": replay}
        current_task_revision, expected_head_sha256, expected_recovery_revision = _recovery_expected_cas(
            task, current_head, args
        )
        if current_head is not None:
            raise ValueError("result_recovery_review_required")
        next_task_revision = current_task_revision + 1
        next_recovery_revision = expected_recovery_revision + 1
        event_id = deterministic_result_recovery_event_id(operation_id, "review", payload_digest)
        receipt = _build_recovery_receipt(
            schema="court.office.result_recovery_review_receipt.v1",
            operation_id=operation_id,
            task_id=str(task["task_id"]),
            task_revision=next_task_revision,
            quarantine_id=str(core["quarantine_id"]),
            recovery_id=recovery_id,
            recovery_revision=next_recovery_revision,
            previous_head_sha256=expected_head_sha256,
            reason_codes=reason_codes,
            evidence_pointer=evidence_pointer,
            evidence_sha256=evidence_sha256,
            actor=actor,
            timestamp_field="reviewed_at",
            timestamp=now_text(),
            event_id=event_id,
            decision=decision,
            quarantine_core_sha256=str(core["core_sha256"]),
            projection_sha256=projection_sha256,
        )
        _validate_recovery_receipt(
            receipt,
            result_recovery_review_receipt_json_schema,
            expected_actor=actor,
            expected_schema="court.office.result_recovery_review_receipt.v1",
        )
        new_head = build_result_recovery_head(
            quarantine_core=core,
            recovery_id=recovery_id,
            previous_head=None,
            state="READY_FOR_HANDOFF" if decision == "ACCEPT" else "REJECTED",
            projection_sha256=projection_sha256,
            target_binding_sha256=RESULT_RECOVERY_ZERO_SHA256,
            review_receipt_sha256=str(receipt["receipt_sha256"]),
            handoff_receipt_sha256=RESULT_RECOVERY_ZERO_SHA256,
            consume_receipt_sha256=RESULT_RECOVERY_ZERO_SHA256,
            operation_id=operation_id,
            event_id=event_id,
            created_at=str(receipt["reviewed_at"]),
        )
        history.append(new_head)
        if projection is not None:
            _projections[recovery_id] = projection
        _recovery_operation_store(task, operation_id, payload_digest, receipt, payload)
        task["task_revision"] = next_task_revision
        task["updated_at"] = now_text()
        task["last_evidence"] = f"result_recovery_review {recovery_id}: {evidence_pointer}"
        event = make_event(task, "result_recovery_review", str(task.get("state") or ""), str(task.get("state") or ""), actor, evidence_pointer, scrub_agent_provider_detail(str(getattr(args, "note", "") or "")))
        event.update(event_id=event_id, operation_id=operation_id, payload_sha256=payload_digest, quarantine_id=core["quarantine_id"], recovery_id=recovery_id, recovery_revision=next_recovery_revision, task_revision=next_task_revision, decision=decision, reason_codes=reason_codes, receipt_sha256=receipt["receipt_sha256"])
        _result_recovery_commit_locked(operation_id=operation_id, payload_digest=payload_digest, task_id=str(task["task_id"]), tasks=tasks, event=event, receipt=receipt, killpoint=str(getattr(args, "killpoint", "") or ""))
        return {"status": "COMMITTED", "operation_id": operation_id, "receipt": receipt, "head": new_head, "projection": projection}


def _target_agent_record(task: Mapping[str, object], args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    agents = task.get("agents")
    if not isinstance(agents, Mapping):
        raise ValueError("result_recovery_target_not_dispatchable")
    requested = str(
        getattr(args, "target_agent_id", "")
        or getattr(args, "agent_id", "")
        or ""
    ).strip()
    requested_instance = str(
        getattr(args, "target_office_instance_id", "")
        or getattr(args, "office_instance_id", "")
        or ""
    ).strip().lower()
    matches: list[tuple[str, dict[str, object]]] = []
    for internal_id, value in agents.items():
        if not isinstance(value, dict):
            continue
        if requested and str(internal_id) != requested:
            continue
        if requested_instance and str(value.get("office_instance_id") or "").lower() != requested_instance:
            continue
        matches.append((str(internal_id), value))
    if len(matches) != 1:
        raise ValueError("result_recovery_target_not_dispatchable")
    return matches[0]


def _validate_recovery_native_followup(
    task: Mapping[str, object],
    target: Mapping[str, object],
    args: argparse.Namespace,
    recovery_binding: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    value = getattr(args, "native_host_action_receipt", None)
    if not isinstance(value, Mapping):
        raise ValueError("result_recovery_delivery_receipt_required")
    raw_request = getattr(args, "native_host_request", None) or value.get("request")
    if not isinstance(raw_request, Mapping):
        raise ValueError("result_recovery_delivery_receipt_required")
    raw_binding = raw_request.get("recovery_binding")
    try:
        normalized_binding = validate_result_recovery_binding(raw_binding)
    except ValueError as exc:
        raise ValueError("result_recovery_delivery_binding_mismatch") from exc
    if normalized_binding != dict(recovery_binding):
        raise ValueError("result_recovery_delivery_binding_mismatch")
    try:
        normalized_request = normalize_native_host_dispatch_request(raw_request)
        receipt_request = value.get("request")
        if isinstance(receipt_request, Mapping) and normalize_native_host_dispatch_request(receipt_request) != normalized_request:
            raise ValueError("result_recovery_delivery_binding_mismatch")
    except ValueError as exc:
        raise ValueError("result_recovery_delivery_binding_mismatch") from exc
    if (
        value.get("decision") != "reuse"
        or value.get("host_action") != "followup"
        or value.get("outcome") != "succeeded"
        or normalized_request.get("task_id") != task.get("task_id")
        or normalized_request.get("role") != target.get("role")
        or normalized_request.get("instance_id") != str(target.get("office_instance_id") or "").lower()
        or normalized_request.get("direct_superior") != target.get("direct_superior")
    ):
        raise ValueError("result_recovery_delivery_binding_mismatch")
    request_ref = native_request_reference(normalized_request)
    if not isinstance(receipt_request, Mapping) or receipt_request.get("recovery_binding") != raw_binding:
        raise ValueError("result_recovery_delivery_binding_mismatch")
    try:
        validate_native_host_action_receipt(
            value,
            expected=normalized_request,
            replay_guard=set(),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("result_recovery_delivery_binding_mismatch") from exc
    return deepcopy(dict(value)), request_ref


def handoff_recovered_result(args: argparse.Namespace) -> dict[str, object]:
    """尚书-only handoff with target binding and native follow-up evidence."""
    args = _recovery_args(args)
    actor = str(getattr(args, "actor", "") or "").strip().lower()
    evidence_pointer, evidence_sha256 = _result_recovery_evidence_pointer(args)
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(str(getattr(args, "task_id", "")))
        if not isinstance(task, dict):
            raise ValueError("task not found")
        require_semantic_mutation_binding(task)
        requested_operation = str(getattr(args, "operation_id", "") or "").strip()
        existing_operations = task.get("result_recovery_operations")
        if requested_operation and isinstance(existing_operations, Mapping) and requested_operation in existing_operations:
            existing = existing_operations[requested_operation]
            if not isinstance(existing, Mapping) or not isinstance(existing.get("receipt"), dict):
                raise ValueError("result_recovery_operation_corrupt")
            stored_payload = existing.get("payload")
            if isinstance(stored_payload, Mapping) and stored_payload.get("evidence_pointer") not in {None, evidence_pointer}:
                raise ValueError("result_recovery_operation_conflict")
            supplied_receipt = getattr(args, "native_host_action_receipt", None)
            if isinstance(stored_payload, Mapping) and isinstance(supplied_receipt, Mapping) and stored_payload.get("native_host_action_receipt_id") not in {None, supplied_receipt.get("receipt_id")}:
                raise ValueError("result_recovery_operation_conflict")
            return {"status": "REPLAYED", "operation_id": requested_operation, "receipt": deepcopy(existing["receipt"])}
        core, _metadata, _source = _recovery_quarantine_context(task, args, require_payload=False)
        history, _operations, projections = _result_recovery_ledgers(task)
        recovery_id = str(getattr(args, "recovery_id", "") or "REC-" + str(core["quarantine_id"])).strip()
        current_head = _recovery_head_for_task(task, recovery_id)
        if current_head is None or current_head.get("state") != "READY_FOR_HANDOFF":
            raise ValueError("result_recovery_review_required")
        current_task_revision, expected_head_sha256, expected_recovery_revision = _recovery_expected_cas(task, current_head, args)
        projection = projections.get(recovery_id)
        if not isinstance(projection, dict):
            raise ValueError("result_recovery_projection_invalid")
        projection = validate_result_recovery_projection(projection, expected_core=core)
        target_id, target = _target_agent_record(task, args)
        if actor != str(target.get("direct_superior") or "").strip().lower():
            raise ValueError("result_recovery_actor_forbidden")
        if (
            task.get("semantic_state") != "DISPATCHABLE"
            or target.get("hierarchy_gate") != "PASSED"
            or target.get("preload_status") != "PASSED"
            or target.get("office_execution_ready") is not True
            or str(target.get("status") or "") in TERMINAL_AGENT_STATUSES
            or str(target.get("final_status") or "") in TERMINAL_AGENT_STATUSES
            or target.get("release_status") == "closed"
            or target.get("result_state") == "QUARANTINED"
        ):
            raise ValueError("result_recovery_target_not_dispatchable")
        target_binding, target_binding_sha256 = _validate_target_binding(
            task, target, getattr(args, "target_binding", None)
        )
        recovery_binding = build_result_recovery_binding(
            recovery_id=recovery_id,
            quarantine_id=str(core["quarantine_id"]),
            quarantine_core_sha256=str(core["core_sha256"]),
            recovery_head_sha256=str(current_head["head_sha256"]),
            projection_sha256=str(projection["projection_sha256"]),
            review_receipt_sha256=str(current_head["review_receipt_sha256"]),
            target_binding_sha256=target_binding_sha256,
        )
        native_receipt, native_request_ref = _validate_recovery_native_followup(
            task, target, args, recovery_binding
        )
        payload = {
            "recovery_id": recovery_id,
            "quarantine_id": core["quarantine_id"],
            "projection_sha256": projection["projection_sha256"],
            "target_binding_sha256": target_binding_sha256,
            "native_host_request_ref": native_request_ref,
            "native_host_action_receipt_id": native_receipt.get("receipt_id"),
            "native_host_action_receipt": deepcopy(native_receipt),
            "evidence_pointer": evidence_pointer,
            "evidence_ref": evidence_sha256,
        }
        operation_id, payload_digest, replay = _recovery_operation_identity(task, getattr(args, "operation_id", None), payload)
        if replay is not None:
            return {"status": "REPLAYED", "operation_id": operation_id, "receipt": replay}
        next_task_revision = current_task_revision + 1
        next_recovery_revision = expected_recovery_revision + 1
        event_id = deterministic_result_recovery_event_id(operation_id, "handoff", payload_digest)
        receipt = _build_recovery_receipt(
            schema="court.office.result_recovery_handoff_receipt.v1",
            operation_id=operation_id,
            task_id=str(task["task_id"]),
            task_revision=next_task_revision,
            quarantine_id=str(core["quarantine_id"]),
            recovery_id=recovery_id,
            recovery_revision=next_recovery_revision,
            previous_head_sha256=expected_head_sha256,
            reason_codes=["HANDOFF_TARGET_BINDING_ACCEPTED"],
            evidence_pointer=evidence_pointer,
            evidence_sha256=evidence_sha256,
            actor=actor,
            timestamp_field="handed_off_at",
            timestamp=now_text(),
            event_id=event_id,
            review_receipt_sha256=str(current_head["review_receipt_sha256"]),
            target_binding_sha256=target_binding_sha256,
            native_host_request_ref=native_request_ref,
            native_host_action_receipt_id=native_receipt.get("receipt_id"),
            native_host_action_receipt=deepcopy(native_receipt),
        )
        _validate_recovery_receipt(
            receipt,
            result_recovery_handoff_receipt_json_schema,
            expected_actor=actor,
            expected_schema="court.office.result_recovery_handoff_receipt.v1",
        )
        new_head = build_result_recovery_head(
            quarantine_core=core,
            recovery_id=recovery_id,
            previous_head=current_head,
            state="HANDED_OFF",
            projection_sha256=str(projection["projection_sha256"]),
            target_binding_sha256=target_binding_sha256,
            review_receipt_sha256=str(current_head["review_receipt_sha256"]),
            handoff_receipt_sha256=str(receipt["receipt_sha256"]),
            consume_receipt_sha256=RESULT_RECOVERY_ZERO_SHA256,
            operation_id=operation_id,
            event_id=event_id,
            created_at=str(receipt["handed_off_at"]),
        )
        history.append(new_head)
        inputs = target.setdefault("recovered_result_inputs", [])
        if not isinstance(inputs, list):
            raise ValueError("result_recovery_target_input_ledger_corrupt")
        inputs.append({
            "recovery_id": recovery_id,
            "quarantine_id": core["quarantine_id"],
            "projection_sha256": projection["projection_sha256"],
            "target_binding_sha256": target_binding_sha256,
            "handoff_receipt_sha256": receipt["receipt_sha256"],
            "received_at": receipt["handed_off_at"],
        })
        target["recovery_target_binding"] = deepcopy(target_binding)
        _record_native_host_receipt(task, native_receipt, lifecycle_action="recovery_handoff", target_id=target_id)
        _recovery_operation_store(task, operation_id, payload_digest, receipt, payload)
        task["task_revision"] = next_task_revision
        task["updated_at"] = now_text()
        task["last_evidence"] = f"result_recovery_handoff {recovery_id}: {evidence_pointer}"
        event = make_event(task, "result_recovery_handoff", str(task.get("state") or ""), str(task.get("state") or ""), actor, evidence_pointer, scrub_agent_provider_detail(str(getattr(args, "note", "") or "")))
        event.update(event_id=event_id, operation_id=operation_id, payload_sha256=payload_digest, recovery_id=recovery_id, target_agent_id=target_id, target_binding_sha256=target_binding_sha256, native_host_action_receipt_id=native_receipt.get("receipt_id"), receipt_sha256=receipt["receipt_sha256"], task_revision=next_task_revision)
        _result_recovery_commit_locked(operation_id=operation_id, payload_digest=payload_digest, task_id=str(task["task_id"]), tasks=tasks, event=event, receipt=receipt, killpoint=str(getattr(args, "killpoint", "") or ""))
        return {"status": "COMMITTED", "operation_id": operation_id, "receipt": receipt, "head": new_head, "projection": projection, "target_binding": target_binding, "recovery_binding": recovery_binding}


def _consume_recovery_for_finish_locked(
    task: dict[str, object],
    target: dict[str, object],
    envelope: Mapping[str, object],
    *,
    actor: str,
    evidence_pointer: str,
    target_finish_event_id: str,
    args: argparse.Namespace | None = None,
) -> list[dict[str, object]]:
    recovery_ids = envelope.get("recovery_input_ids")
    if recovery_ids is None:
        return []
    if not isinstance(recovery_ids, list) or not recovery_ids or any(
        not isinstance(value, str) or not value.strip() for value in recovery_ids
    ) or len(set(recovery_ids)) != len(recovery_ids):
        raise ValueError("result_recovery_target_mismatch")
    history, _operations, projections = _result_recovery_ledgers(task)
    frozen_binding = target.get("recovery_target_binding")
    if isinstance(frozen_binding, dict):
        target_binding = dict(frozen_binding)
        target_binding_sha256 = _target_binding_sha256(target_binding)
        current_identity = _target_binding_from_record(task, target)
        for field in result_recovery_target_binding_fields():
            if field in {"status", "final_status", "release_status", "result_state"}:
                continue
            if current_identity.get(field) != target_binding.get(field):
                raise ValueError("result_recovery_target_mismatch")
    else:
        target_binding, target_binding_sha256 = _validate_target_binding(task, target)
    if result_binding_problems(dict(envelope), target):
        raise ValueError("result_recovery_target_mismatch")
    consumed_receipts: list[dict[str, object]] = []
    for recovery_id in recovery_ids:
        recovery_id = recovery_id.strip()
        current_head = _recovery_head_for_task(task, recovery_id)
        if current_head is None or current_head.get("state") != "HANDED_OFF":
            raise ValueError("result_recovery_not_handed_off")
        if current_head.get("target_binding_sha256") != target_binding_sha256:
            raise ValueError("result_recovery_target_mismatch")
        projection = projections.get(recovery_id)
        if not isinstance(projection, dict):
            raise ValueError("result_recovery_projection_invalid")
        core = _result_recovery_core_for_task(
            task,
            quarantine_id=str(current_head["quarantine_id"]),
        )
        projection = validate_result_recovery_projection(projection, expected_core=core)
        target_result_sha256 = source_result_payload_sha256(envelope)
        payload = {
            "recovery_id": recovery_id,
            "target_binding_sha256": target_binding_sha256,
            "target_result_envelope_sha256": target_result_sha256,
            "target_finish_event_id": target_finish_event_id,
            "evidence_pointer": evidence_pointer,
        }
        requested_operation_id = getattr(args, "operation_id", None) if args is not None else None
        operation_id = requested_operation_id or f"consume-{recovery_id}-{target_finish_event_id}"
        operation_id, payload_digest, replay = _recovery_operation_identity(task, operation_id, payload)
        if replay is not None:
            consumed_receipts.append(replay)
            continue
        current_task_revision = _task_revision_value(task)
        next_task_revision = current_task_revision + 1
        next_recovery_revision = int(current_head["revision"]) + 1
        event_id = deterministic_result_recovery_event_id(operation_id, "consume", payload_digest)
        receipt = _build_recovery_receipt(
            schema="court.office.result_recovery_consume_receipt.v1",
            operation_id=operation_id,
            task_id=str(task["task_id"]),
            task_revision=next_task_revision,
            quarantine_id=str(current_head["quarantine_id"]),
            recovery_id=recovery_id,
            recovery_revision=next_recovery_revision,
            previous_head_sha256=str(current_head["head_sha256"]),
            reason_codes=["CONSUME_TARGET_RESULT_ACCEPTED"],
            evidence_pointer=evidence_pointer,
            evidence_sha256=hashlib.sha256(evidence_pointer.encode("utf-8")).hexdigest(),
            actor=actor,
            timestamp_field="consumed_at",
            timestamp=now_text(),
            event_id=event_id,
            handoff_receipt_sha256=str(current_head["handoff_receipt_sha256"]),
            target_binding_sha256=target_binding_sha256,
            target_result_envelope_sha256=target_result_sha256,
            target_finish_event_id=target_finish_event_id,
        )
        _validate_recovery_receipt(
            receipt,
            result_recovery_consume_receipt_json_schema,
            expected_actor=actor,
            expected_schema="court.office.result_recovery_consume_receipt.v1",
        )
        new_head = build_result_recovery_head(
            quarantine_core=core,
            recovery_id=recovery_id,
            previous_head=current_head,
            state="CONSUMED",
            projection_sha256=str(projection["projection_sha256"]),
            target_binding_sha256=target_binding_sha256,
            review_receipt_sha256=str(current_head["review_receipt_sha256"]),
            handoff_receipt_sha256=str(current_head["handoff_receipt_sha256"]),
            consume_receipt_sha256=str(receipt["receipt_sha256"]),
            operation_id=operation_id,
            event_id=event_id,
            created_at=str(receipt["consumed_at"]),
        )
        history.append(new_head)
        _recovery_operation_store(task, operation_id, payload_digest, receipt, payload)
        receipts = task.setdefault("result_recovery_receipts", {})
        if not isinstance(receipts, dict):
            raise ValueError("result_recovery_ledger_corrupt")
        receipts[str(receipt["receipt_id"])] = deepcopy(receipt)
        task["task_revision"] = next_task_revision
        consumed = target.setdefault("recovery_consumed_ids", [])
        if not isinstance(consumed, list):
            raise ValueError("result_recovery_target_input_ledger_corrupt")
        consumed.append(recovery_id)
        consumed_receipts.append(receipt)
    return consumed_receipts


def consume_recovered_result(args: argparse.Namespace) -> dict[str, object]:
    """Consume a handed-off recovery input after a normal target finish."""
    args = _recovery_args(args)
    actor = str(getattr(args, "actor", "") or "").strip().lower()
    evidence_pointer, _evidence_sha256 = _result_recovery_evidence_pointer(args)
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(str(getattr(args, "task_id", "")))
        if not isinstance(task, dict):
            raise ValueError("task not found")
        require_semantic_mutation_binding(task)
        requested_operation = str(getattr(args, "operation_id", "") or "").strip()
        existing_operations = task.get("result_recovery_operations")
        if requested_operation and isinstance(existing_operations, Mapping) and requested_operation in existing_operations:
            existing = existing_operations[requested_operation]
            if not isinstance(existing, Mapping) or not isinstance(existing.get("receipt"), dict):
                raise ValueError("result_recovery_operation_corrupt")
            return {"status": "REPLAYED", "operation_id": requested_operation, "receipts": [deepcopy(existing["receipt"])]}
        target_id, target = _target_agent_record(task, args)
        if target.get("final_status") != "completed" or not isinstance(target.get("result_envelope"), dict):
            raise ValueError("result_recovery_target_result_required")
        envelope = normalize_result_envelope(target["result_envelope"])
        finish_event_id = str(getattr(args, "target_finish_event_id", "") or f"finish-{target_id}")
        receipts = _consume_recovery_for_finish_locked(task, target, envelope, actor=actor, evidence_pointer=evidence_pointer, target_finish_event_id=finish_event_id, args=args)
        if not receipts:
            raise ValueError("result_recovery_not_handed_off")
        task["updated_at"] = now_text()
        task["last_evidence"] = f"result_recovery_consume {target_id}: {evidence_pointer}"
        tasks[str(task["task_id"])] = task
        event = make_event(task, "result_recovery_consume", str(task.get("state") or ""), str(task.get("state") or ""), actor, evidence_pointer, scrub_agent_provider_detail(str(getattr(args, "note", "") or "")))
        event.update(target_agent_id=target_id, recovery_receipt_ids=[receipt.get("receipt_id") for receipt in receipts], task_revision=task.get("task_revision"))
        _commit_task_event(tasks, event)
        return {"status": "COMMITTED", "target_agent_id": target_id, "receipts": receipts, "event": event}


def result_review(args: argparse.Namespace) -> dict[str, object]:
    return review_quarantined_result(args)


def result_handoff(args: argparse.Namespace) -> dict[str, object]:
    return handoff_recovered_result(args)


def result_consume(args: argparse.Namespace) -> dict[str, object]:
    return consume_recovered_result(args)


office_result_review = review_quarantined_result
office_result_handoff = handoff_recovered_result
office_result_consume = consume_recovered_result


def agent_event(
    args: argparse.Namespace,
    lifecycle_action: str,
    status: str,
    required_evidence_name: str,
) -> TransitionResult:
    if lifecycle_action not in {
        "agent_start",
        "agent_heartbeat",
        "agent_report",
        "agent_finish",
        "agent_close",
    }:
        raise ValueError(f"unknown agent lifecycle action: {lifecycle_action}")
    evidence = require_text(args.evidence, required_evidence_name)
    agent_id = require_text(args.agent_id, "agent-id")
    role = require_text(args.role, "role")
    with runtime_lock():
        if lifecycle_action == "agent_start":
            binding_inputs = getattr(args, "_office_assignment_binding_inputs", None)
            prelock_binding = getattr(args, "_office_assignment_binding", None)
            if not isinstance(binding_inputs, dict) or not isinstance(prelock_binding, dict):
                raise ValueError("agent start assignment binding was not validated")
            try:
                fresh_binding = build_office_assignment_binding(**binding_inputs)
            except (OSError, ValueError) as exc:
                raise ValueError("stale_profile_or_skill") from exc
            if fresh_binding != prelock_binding:
                raise ValueError("stale_profile_or_skill")
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        if (
            lifecycle_action in {"agent_start", "agent_report", "agent_finish"}
            and task.get("semantic_state") != "DISPATCHABLE"
        ):
            raise ValueError("semantic_mutation_not_dispatchable")
        actor = args.actor
        if actor not in OFFICES:
            raise ValueError(f"unknown actor office: {actor}")
        consultation_refs: list[dict[str, object]] | None = None
        if lifecycle_action == "agent_report":
            raw_consultation_refs = getattr(args, "consultation_refs", None)
            if raw_consultation_refs is not None:
                consultation_refs = _validated_consultation_refs_for_task(
                    task, raw_consultation_refs, agent_id=agent_id
                )
        elif lifecycle_action == "agent_finish":
            result_envelope = getattr(args, "_result_envelope", None)
            if isinstance(result_envelope, dict) and "consultation_refs" in result_envelope:
                consultation_refs = _validated_consultation_refs_for_task(
                    task, result_envelope["consultation_refs"], agent_id=agent_id
                )
                result_envelope["consultation_refs"] = deepcopy(consultation_refs)
        agents = task.setdefault("agents", {})
        if not isinstance(agents, dict):
            agents = {}
            task["agents"] = agents
        start_admission: dict[str, Any] | None = None
        start_model_route: dict[str, Any] | None = None
        start_instance_id: str | None = None
        start_office_kind = "child_agent"
        start_context_economy: dict[str, object] | None = None
        start_hierarchy_evidence: dict[str, object] | None = None
        start_native_host_receipt: dict[str, object] | None = None
        captured_carrier: dict[str, object] | None = None
        if lifecycle_action == "agent_start":
            _reject_native_host_receipt_replay(task, args)
            if agent_id in agents:
                raise ValueError(f"agent already exists: {agent_id}")
            wave_id = str(getattr(args, "wave_id", "") or "wave-default")
            admissions = task.get("agent_admissions")
            admission = admissions.get(wave_id) if isinstance(admissions, dict) else None
            if not isinstance(admission, dict):
                raise ValueError(f"agent start admission not found: {wave_id}")
            if admission.get("allowed") is not True:
                raise ValueError(f"agent start admission was not allowed: {wave_id}")
            _validate_admission_immutable_event_anchor(task, admission)
            selected_bindings = admission.get("selected_bindings")
            if not isinstance(selected_bindings, (list, tuple)):
                raise ValueError("agent start admission is missing instance bindings")
            lease_access_error = budget_lease_access_contract_error(
                admission.get("budget_lease"),
                selected_bindings,
            )
            if lease_access_error is not None:
                raise ValueError(
                    "agent_start_budget_lease_access_contract_mismatch:"
                    f"{lease_access_error}"
                )
            from court_agent_admission import _admission_lease_metadata_error
            lease = admission["budget_lease"]
            lease_error = _admission_lease_metadata_error(
                lease, calling_office=str(admission.get("calling_office") or ""),
                direct_superior=str(admission.get("direct_superior") or ""),
                next_depth=lease.get("approved_next_depth"))
            if lease_error:
                raise ValueError(f"agent_start_budget_lease_invalid:{lease_error}")
            _validate_admission_request_binding_anchors(
                admission,
                selected_bindings,
            )
            _validate_admission_semantic_receipt_anchors(
                task,
                admission,
                selected_bindings,
            )
            _validate_admission_binding_integrity(admission, selected_bindings)
            role_bindings = [
                binding
                for binding in selected_bindings
                if isinstance(binding, dict)
                and str(binding.get("role") or "").strip().lower() == role.lower()
            ]
            requested_instance_id = str(getattr(args, "instance_id", "") or "").strip().lower()
            if requested_instance_id:
                matching_bindings = [
                    binding
                    for binding in role_bindings
                    if str(binding.get("instance_id") or "").strip().lower()
                    == requested_instance_id
                ]
            else:
                matching_bindings = role_bindings
            if len(matching_bindings) != 1:
                raise ValueError("agent start requires one admitted instance-id")
            matched_binding = matching_bindings[0]
            expected_child_profile = _expected_child_office_profile(matched_binding)
            if (
                expected_child_profile is not None
                and matched_binding.get("child_profile") != expected_child_profile
            ):
                raise ValueError(
                    "dispatch_hierarchy_child_semantic_authority_mismatch"
                )
            start_hierarchy_evidence = _dispatch_hierarchy_evidence(
                admission.get("calling_office"),
                matched_binding,
            )
            if start_hierarchy_evidence is not None:
                hierarchy_preimages: list[Mapping[str, object]] = [matched_binding]
                if admission.get("hierarchy_gate") == "PASSED":
                    hierarchy_preimages.append(admission)
                for hierarchy_preimage in hierarchy_preimages:
                    for field in _HIERARCHY_EVIDENCE_FIELDS:
                        if (
                            field not in hierarchy_preimage
                            or hierarchy_preimage.get(field)
                            != start_hierarchy_evidence.get(field)
                        ):
                            raise ValueError(
                                "dispatch_hierarchy_manifest_invalid"
                                if field
                                in {
                                    "hierarchy_gate",
                                    "hierarchy_schema",
                                    "hierarchy_manifest_path",
                                }
                                else "dispatch_hierarchy_edge_forbidden"
                            )
            if isinstance(matching_bindings[0], dict):
                _validate_agent_semantic_args(args, matching_bindings[0])
                start_context_economy = _revalidate_context_economy_start(
                    task,
                    admission,
                    matching_bindings[0],
                    args,
                    wave_id=wave_id,
                )
            start_instance_id = str(matching_bindings[0].get("instance_id") or "").strip().lower()
            start_office_kind = _canonical_office_instance_kind(
                matching_bindings[0].get("office_instance_kind")
            )
            if getattr(args, "_office_lifecycle_explicit", False):
                requested_kind = _canonical_office_instance_kind(
                    getattr(args, "office_instance_kind", None)
                )
                requested_office_id = str(
                    getattr(args, "office_instance_id", "") or ""
                ).strip().lower()
                if requested_kind != start_office_kind:
                    raise ValueError("office_instance_kind_mismatch")
                if requested_office_id != str(
                    matching_bindings[0].get("office_instance_id") or ""
                ).strip().lower():
                    raise ValueError("office_instance_id_mismatch")
                admitted_proof = matching_bindings[0].get("carrier_proof")
                admitted_task_name = str(matching_bindings[0].get("collaboration_task_name") or "")
                # Public admission reserves an office before its host carrier
                # exists. Bind that carrier from the validated capture without
                # rewriting the immutable admission or changing its office ID.
                if admitted_proof is None and not admitted_task_name and requested_kind == "child_agent":
                    start_native_host_receipt = _validate_native_host_receipt_for_runtime(
                        task, admission, matched_binding, args,
                        decision="spawn", host_action="spawn", outcome="succeeded")
                    if not start_native_host_receipt or not start_native_host_receipt.get("host_spawn_evidence"):
                        raise ValueError("native_carrier_capture_required")
                    request_suffix = native_task_suffix(start_native_host_receipt["request"])
                    admitted_task_name = f"{role.replace('-', '_')}_native_{request_suffix}"
                    if str(start_native_host_receipt.get("host_instance_id", "")).rsplit("/", 1)[-1] != admitted_task_name:
                        raise ValueError("native_carrier_capture_name_mismatch")
                    admitted_proof = {"agent_id": f"{role}-native-{request_suffix}"}
                    captured_carrier = {"carrier_proof": admitted_proof, "collaboration_task_name": admitted_task_name}
                requested_proof = _normalize_carrier_proof(
                    requested_kind,
                    getattr(args, "carrier_proof", None),
                    role=role,
                    office_instance_id=requested_office_id,
                )
                if admitted_proof != requested_proof:
                    raise ValueError("office_carrier_proof_mismatch")
                if requested_kind == "child_agent":
                    if requested_proof.get("agent_id") != agent_id:
                        raise ValueError("office_child_agent_id_mismatch")
                elif agent_id != requested_office_id:
                    raise ValueError("office_worktree_storage_id_mismatch")
                if admitted_task_name != str(
                    getattr(args, "collaboration_task_name", "") or ""
                ):
                    raise ValueError("office_task_name_mismatch")
                task_name_bindings = task.setdefault("office_task_name_bindings", {})
                if not isinstance(task_name_bindings, dict):
                    raise ValueError("office_task_name_binding_corrupt")
                existing_task_name = task_name_bindings.get(admitted_task_name)
                if isinstance(existing_task_name, dict):
                    if existing_task_name.get("role") != role:
                        raise ValueError("office_task_name_cross_role_reuse")
                elif existing_task_name is not None:
                    raise ValueError("office_task_name_binding_corrupt")
                else:
                    task_name_bindings[admitted_task_name] = {
                        "role": role,
                        "first_office_instance_id": requested_office_id,
                        "bound_at": now_text(),
                    }
            admitted_dispatch_requested_at = normalize_optional_timestamp(
                admission.get("dispatch_requested_at"),
                "admitted dispatch-requested-at",
            )
            admitted_generated_at = normalize_optional_timestamp(
                admission.get("generated_at"),
                "admitted generated-at",
            )
            dispatch_requested_at = normalize_optional_timestamp(
                getattr(args, "dispatch_requested_at", None),
                "dispatch-requested-at",
            )
            if (
                admitted_dispatch_requested_at is None
                or dispatch_requested_at != admitted_dispatch_requested_at
            ):
                raise ValueError("agent start dispatch_requested_at does not match admission")
            if admitted_generated_at is None:
                raise ValueError("agent start admission is missing generated_at")
            admitted_budgets = _execution_budgets(admission)
            admission_deadline_seconds = admitted_budgets["deadline_seconds"]
            current_time = datetime.now(timezone.utc)
            for timestamp_name, timestamp_value in (
                ("dispatch_requested_at", admitted_dispatch_requested_at),
                ("generated_at", admitted_generated_at),
            ):
                timestamp_time = datetime.fromisoformat(timestamp_value).astimezone(timezone.utc)
                timestamp_age = (current_time - timestamp_time).total_seconds()
                if timestamp_age < -1:
                    raise ValueError(f"agent start admission {timestamp_name} is in the future")
                if admission_deadline_seconds is not None and timestamp_age > admission_deadline_seconds:
                    raise ValueError(f"agent start admission {timestamp_name} has expired")
            route_inputs = admission.get("model_route_inputs")
            if not isinstance(route_inputs, dict):
                raise ValueError("agent start admission is missing routing inputs")
            start_route_inputs = {
                "assignment": args.scope,
                "task_focus": args.task_focus,
                "complexity": args.complexity,
                "risk": args.risk,
                "ambiguity": args.ambiguity,
                "transport": args.transport,
            }
            for field, value in start_route_inputs.items():
                if route_inputs.get(field) != value:
                    raise ValueError(f"agent start {field} does not match admission")
            admitted_fork_turns = admission.get("recommended_fork_turns")
            start_fork_turns = str(getattr(args, "fork_turns", "none") or "none")
            if not isinstance(admitted_fork_turns, str) or start_fork_turns != admitted_fork_turns:
                raise ValueError("agent start fork_turns does not match admission")
            for field, minimum in (("context_tokens", 0),):
                admitted_value = admission.get(field)
                start_value = getattr(args, field, None)
                if (
                    isinstance(admitted_value, bool)
                    or not isinstance(admitted_value, int)
                    or isinstance(start_value, bool)
                    or not isinstance(start_value, int)
                ):
                    raise ValueError(f"agent start {field} budget is invalid")
                if start_value < minimum or start_value > admitted_value:
                    raise ValueError(f"agent start {field} exceeds admission")
            for field, start_value in _execution_budgets(vars(args)).items():
                admitted_value = admitted_budgets[field]
                if start_value is None:
                    start_value = admitted_value
                if admitted_value is not None and start_value > admitted_value:
                    raise ValueError(f"agent start {field} exceeds admission")
                setattr(args, field, start_value)
            model_routes = admission.get("model_routes")
            model_route = (
                model_routes.get(start_instance_id)
                if isinstance(model_routes, dict) and start_instance_id is not None
                else None
            )
            if not isinstance(model_route, dict):
                raise ValueError("agent start instance does not have an admitted model route")
            consumed_instances = admission.get("consumed_instances")
            if consumed_instances is not None and not isinstance(consumed_instances, dict):
                raise ValueError("agent start admission consumption ledger is corrupt")
            if isinstance(consumed_instances, dict) and start_instance_id in consumed_instances:
                raise ValueError(f"agent start admitted instance already consumed: {start_instance_id}")
            failed_roles = admission.get("failed_roles")
            if failed_roles is not None and not isinstance(failed_roles, dict):
                raise ValueError("agent start admission failure ledger is corrupt")
            if isinstance(failed_roles, dict) and role in failed_roles:
                raise ValueError(f"agent start admitted role already failed: {role}")
            wave_blocks = task.get("agent_wave_blocks")
            if isinstance(wave_blocks, dict) and wave_id in wave_blocks:
                raise ValueError(f"agent start wave is blocked: {wave_id}")
            start_native_host_receipt = _validate_native_host_receipt_for_runtime(
                task,
                admission,
                matched_binding,
                args,
                decision="spawn",
                host_action="spawn",
                outcome="succeeded",
            )
            start_admission = admission
            start_model_route = dict(model_route)
        else:
            existing_agent = agents.get(agent_id)
            if not isinstance(existing_agent, dict):
                raise ValueError(f"agent not found: {agent_id}")
            if existing_agent.get("role") != role:
                raise ValueError("agent role does not match lifecycle record")
            if lifecycle_action in {"agent_heartbeat", "agent_report", "agent_finish"} and (
                str(existing_agent.get("status") or "") in TERMINAL_AGENT_STATUSES
                or str(existing_agent.get("final_status") or "") in TERMINAL_AGENT_STATUSES
                or existing_agent.get("release_status") == "closed"
            ):
                raise ValueError("terminal agent cannot accept lifecycle events")
            if lifecycle_action == "agent_finish" and existing_agent.get("result_state") == "QUARANTINED":
                raise ValueError("terminal agent cannot accept lifecycle events")
            if lifecycle_action == "agent_finish" and existing_agent.get("dispatch_uid"):
                result_envelope = getattr(args, "_result_envelope", None)
                if not isinstance(result_envelope, dict):
                    raise ValueError("structured_result_envelope_required")
                result_problems = result_binding_problems(result_envelope, existing_agent)
                if result_problems:
                    now = now_text()
                    original_envelope = getattr(args, "_original_result_envelope", None)
                    source_for_digest = (
                        original_envelope
                        if isinstance(original_envelope, dict)
                        else result_envelope
                    )
                    payload_sha256 = (
                        str(getattr(args, "_source_result_payload_sha256", "") or "")
                        or source_result_payload_sha256(result_envelope)
                    )
                    source_enriched = deepcopy(result_envelope)
                    if (
                        "office_instance_kind" not in source_enriched
                        and "carrier_proof" not in source_enriched
                    ):
                        kind = existing_agent.get("office_instance_kind") or "child_agent"
                        proof = existing_agent.get("carrier_proof")
                        if proof is None and kind == "child_agent":
                            proof = {"agent_id": str(agent_id)}
                        if proof is not None:
                            source_enriched["office_instance_kind"] = kind
                            source_enriched["carrier_proof"] = proof
                    quarantined = task.setdefault("quarantined_results", [])
                    if not isinstance(quarantined, list):
                        raise ValueError("quarantined_result_ledger_corrupt")
                    for prior in quarantined:
                        if isinstance(prior, dict) and prior.get("payload_sha256") == payload_sha256:
                            prior_event_id = str(prior.get("quarantine_event_id") or "")
                            prior_events = [
                                event
                                for event in events_for_task(args.task_id, limit=None)
                                if event.get("action") == "agent_result_quarantine"
                                and event.get("payload_sha256") == payload_sha256
                            ]
                            if prior_events:
                                return TransitionResult(task, prior_events[-1])
                    metadata = result_quarantine_metadata(
                        result_envelope,
                        result_problems,
                        received_at=now,
                    )
                    metadata["payload_sha256"] = payload_sha256
                    metadata["source_status"] = "failed"
                    metadata["source_final_status"] = "failed"
                    metadata["source_release_status"] = "closed"
                    metadata["source_result_state"] = "QUARANTINED"
                    metadata["failure_kind"] = "result_binding_quarantine"
                    metadata["office_instance_kind"] = existing_agent.get("office_instance_kind", "child_agent")
                    metadata["direct_superior"] = existing_agent.get("direct_superior")
                    metadata["worktree"] = existing_agent.get("worktree")
                    core_reason_codes = _result_recovery_reason_codes(result_problems)
                    quarantine_core = build_result_quarantine_core(
                        source_result=source_enriched,
                        payload_sha256=payload_sha256,
                        source_final_status="failed",
                        source_release_status="closed",
                        source_result_state="QUARANTINED",
                        reason_codes=core_reason_codes,
                        received_at=now,
                    )
                    metadata["core_schema"] = quarantine_core["schema"]
                    metadata["core_sha256"] = quarantine_core["core_sha256"]
                    metadata["core"] = quarantine_core
                    metadata["core_reason_codes"] = core_reason_codes
                    metadata["quarantine_event_id"] = quarantine_core["quarantine_event_id"]
                    previous_status = str(existing_agent.get("status") or "running")
                    existing_agent.update(
                        {
                            "status": "failed",
                            "final_status": "failed",
                            "release_status": "closed",
                            "result_state": "QUARANTINED",
                            "failure_kind": "result_binding_quarantine",
                            "office_execution_ready": False,
                            "finished_at": now,
                            "closed_at": now,
                        }
                    )
                    agents[agent_id] = existing_agent
                    quarantined.append(metadata)
                    _next_task_revision(task)
                    task["updated_at"] = now
                    task["last_evidence"] = f"agent_result_quarantine {agent_id}: {evidence}"
                    tasks[args.task_id] = task
                    event = make_event(
                        task,
                        "agent_result_quarantine",
                        previous_status,
                        "failed",
                        args.actor,
                        evidence,
                        scrub_agent_provider_detail(str(args.note or "")),
                    )
                    event.update(
                        agent_id=agent_id,
                        agent_role=role,
                        payload_sha256=metadata["payload_sha256"],
                        reason_codes=result_problems,
                        core_reason_codes=core_reason_codes,
                        semantic_epoch=metadata["semantic_epoch"],
                        dispatch_uid=metadata["dispatch_uid"],
                        attempt=metadata["attempt"],
                        quarantine_id=quarantine_core["quarantine_id"],
                        quarantine_event_id=quarantine_core["quarantine_event_id"],
                        core_sha256=quarantine_core["core_sha256"],
                        task_revision=task.get("task_revision"),
                    )
                    event["event_id"] = quarantine_core["quarantine_event_id"]
                    _commit_task_event(tasks, event)
                    return TransitionResult(task, event)
                _validate_agent_semantic_args(args, existing_agent)
            else:
                _validate_agent_semantic_args(args, existing_agent)
            existing_status = str(existing_agent.get("status") or "")
            existing_final_status = str(existing_agent.get("final_status") or "")
            existing_release_status = str(existing_agent.get("release_status") or "")
            if lifecycle_action == "agent_close":
                if existing_status == "closed" or existing_release_status == "closed":
                    raise ValueError("agent is already closed")
                if not (
                    existing_status in {"completed", "failed", "cancelled"}
                    or existing_final_status in {"completed", "failed", "cancelled"}
                ):
                    raise ValueError("agent must finish before close")
            elif (
                existing_status in TERMINAL_AGENT_STATUSES
                or existing_final_status in TERMINAL_AGENT_STATUSES
                or existing_release_status == "closed"
                or str(existing_agent.get("result_state") or "") == "QUARANTINED"
            ):
                raise ValueError("terminal agent cannot accept lifecycle events")
            if (
                lifecycle_action == "agent_report"
                and existing_agent.get("preload_status") != "PASSED"
            ):
                raise ValueError("office_preload_not_passed")
        now = now_text()
        current = dict(agents.get(agent_id, {})) if isinstance(agents.get(agent_id), dict) else {}
        recovery_consumed_receipts: list[dict[str, object]] = []
        recovery_finish_event_id = ""
        previous_status = str(current.get("final_status") or current.get("status") or "")
        if lifecycle_action == "agent_heartbeat" and current.get("preload_status") != "PASSED":
            status = "starting"
        if lifecycle_action == "agent_finish" and current.get("preload_status") != "PASSED":
            status = "failed"
            current["failure_kind"] = "preload_ack_missing"
            current["office_identity_evidence"] = "FAILED"
        current.update(
            {
                "agent_id": agent_id,
                "role": role,
                "status": status,
                "last_heartbeat": now,
                "last_evidence": evidence,
                "updated_at": now,
            }
        )
        if lifecycle_action == "agent_start":
            manifest = build_preload_manifest(role, carrier_kind=start_office_kind, court_code=case_reference(task)["court_code"])
            wave_id = str(getattr(args, "wave_id", "") or "wave-default")
            if start_admission is None or start_model_route is None:
                raise ValueError("agent start admission binding was not validated")
            model_route = start_model_route
            route_binding_source = "agent_admit"
            if model_route["transport"] == "codex" and str(getattr(args, "fork_turns", "none")) != "none":
                raise ValueError("ordinary Codex V2 court dispatch requires fork_turns=none for bounded context isolation")
            current.setdefault("started_at", now)
            current.setdefault("host_session_started_at", now)
            if start_native_host_receipt is not None:
                current["host_session_started_at"] = start_native_host_receipt["acted_at"]
                current.update(
                    _native_host_receipt_record_fields(start_native_host_receipt)
                )
            dispatch_requested_at = normalize_optional_timestamp(
                getattr(args, "dispatch_requested_at", None),
                "dispatch-requested-at",
            )
            if dispatch_requested_at is not None:
                current.setdefault("dispatch_requested_at", dispatch_requested_at)
            current["scope"] = args.scope
            current["task_focus"] = args.task_focus
            current["task_evaluation"] = {
                "complexity": args.complexity,
                "risk": args.risk,
                "ambiguity": args.ambiguity,
            }
            current["transport"] = model_route["transport"]
            current["model_route"] = model_route
            current["model_route_binding"] = {
                "source": route_binding_source,
                "wave_id": wave_id,
                "role": role,
                "instance_id": start_instance_id,
                "model_route_id": model_route["model_route_id"],
            }
            current["model_route_status"] = "PENDING"
            current["wave_id"] = wave_id
            current["admission_instance_id"] = start_instance_id
            current["fork_turns"] = str(getattr(args, "fork_turns", "none") or "none")
            current["context_tokens"] = max(0, int(getattr(args, "context_tokens", 0) or 0))
            current.update(_execution_budgets(vars(args)))
            current["preload_manifest"] = asdict(manifest)
            current["preload_contract_version"] = manifest.preload_ack_schema
            current["preload_ack_required"] = True
            current["preload_status"] = "PENDING"
            current["office_identity_evidence"] = "PENDING"
            assignment_binding = getattr(args, "_office_assignment_binding", None)
            if not isinstance(assignment_binding, dict):
                raise ValueError("agent start assignment binding was not validated")
            current.update(deepcopy(assignment_binding))
            if isinstance(matching_bindings[0], dict) and matching_bindings[0].get("dispatch_uid"):
                current.update(deepcopy(matching_bindings[0]))
            if captured_carrier is not None:
                current.update(deepcopy(captured_carrier))
            current['charter_revision'] = task['charter_revision']
            if start_hierarchy_evidence is not None:
                current.update(start_hierarchy_evidence)
            current["assignment_binding_ready"] = bool(
                assignment_binding.get("office_execution_ready")
            )
            current["office_execution_ready"] = False
            current["legacy_assignment_binding_unenforced"] = False
            consumed_instances = start_admission.get("consumed_instances")
            if not isinstance(consumed_instances, dict):
                consumed_instances = {}
                start_admission["consumed_instances"] = consumed_instances
            if start_instance_id is None:
                raise ValueError("agent start instance binding was not validated")
            consumed_instances[start_instance_id] = agent_id
        if lifecycle_action == "agent_report" and current.get("preload_status") == "PASSED":
            current.setdefault("first_office_report_at", now)
        if lifecycle_action == "agent_report" and consultation_refs is not None:
            current["consultation_refs"] = deepcopy(consultation_refs)
        if lifecycle_action == "agent_finish":
            current["finished_at"] = now
            result_envelope = getattr(args, "_result_envelope", None)
            if isinstance(result_envelope, dict):
                current["result_envelope"] = deepcopy(result_envelope)
                current["result"] = result_envelope["summary"]
                if result_envelope.get("recovery_input_ids"):
                    recovery_finish_event_id = deterministic_result_recovery_event_id(
                        f"finish|{args.task_id}|{agent_id}|{current.get('attempt') or 1}",
                        "finish",
                        source_result_payload_sha256(
                            getattr(args, "_original_result_envelope", None)
                            or result_envelope
                        ),
                    )
                    recovery_consumed_receipts = _consume_recovery_for_finish_locked(
                        task,
                        current,
                        result_envelope,
                        actor=actor,
                        evidence_pointer=evidence,
                        target_finish_event_id=recovery_finish_event_id,
                        args=args,
                    )
            else:
                current["result"] = args.result
            current["final_status"] = status
        if lifecycle_action == "agent_close":
            current.setdefault("finished_at", now)
            current["closed_at"] = now
            current["release_status"] = "closed"
            if current.get("preload_status") != "PASSED":
                current["office_identity_evidence"] = "FAILED"
            current["final_status"] = previous_status if previous_status not in {"", "starting", "running"} else "closed"
            current["result"] = args.result
        if lifecycle_action == "agent_start" and start_native_host_receipt is not None:
            _record_native_host_receipt(
                task,
                start_native_host_receipt,
                lifecycle_action="start",
                target_id=agent_id,
            )
        agents[agent_id] = current
        task["updated_at"] = now
        task["last_evidence"] = f"{lifecycle_action} {agent_id}: {evidence}"
        tasks[args.task_id] = task
        event = make_event(task, lifecycle_action, status, str(task.get("state")), actor, evidence, args.note)
        event["agent_id"] = agent_id
        event["agent_role"] = role
        event['charter_revision'] = current.get('charter_revision', current.get('semantic_epoch'))
        for field in AGENT_SEMANTIC_ARG_FIELDS:
            if current.get(field) is not None:
                event[field] = current[field]
        if any(current.get(field) is not None for field in CONTEXT_ECONOMY_BINDING_FIELDS):
            event.update(
                {
                    field: current.get(field)
                    for field in CONTEXT_ECONOMY_BINDING_FIELDS
                }
            )
        if current.get("hierarchy_gate") == "PASSED":
            event.update(
                {
                    field: current.get(field)
                    for field in _HIERARCHY_EVIDENCE_FIELDS
                }
            )
        if consultation_refs is not None:
            event["consultation_refs"] = deepcopy(consultation_refs)
        event["event_id"] = _office_event_id(
            event,
            str(current.get("office_instance_id") or agent_id),
        )
        if recovery_finish_event_id:
            event["event_id"] = recovery_finish_event_id
            event["recovery_consume_receipt_ids"] = [
                receipt.get("receipt_id") for receipt in recovery_consumed_receipts
            ]
        _commit_task_event(tasks, event)
    return TransitionResult(task, event)


def _prepare_office_start_args(args: argparse.Namespace) -> None:
    kind = _canonical_office_instance_kind(getattr(args, "office_instance_kind", None))
    role = require_text(getattr(args, "role", ""), "role").strip().lower()
    office_instance_id = _require_role_prefixed(
        getattr(args, "office_instance_id", ""),
        role,
        "office_instance_id",
    )
    carrier_proof = _normalize_carrier_proof(
        kind,
        getattr(args, "carrier_proof", None),
        role=role,
        office_instance_id=office_instance_id,
    )
    args.agent_id = str(
        carrier_proof.get("agent_id")
        if kind == "child_agent"
        else office_instance_id
    )
    args.instance_id = office_instance_id
    args.office_instance_kind = kind
    args.office_instance_id = office_instance_id
    args.carrier_proof = carrier_proof
    args._office_lifecycle_explicit = True


def _prepare_office_action_args(
    args: argparse.Namespace,
    *,
    validate_semantic: bool = True,
) -> tuple[dict[str, Any], dict[str, object], str]:
    kind = _canonical_office_instance_kind(getattr(args, "office_instance_kind", None))
    role = require_text(getattr(args, "role", ""), "role").strip().lower()
    office_instance_id = _require_role_prefixed(
        getattr(args, "office_instance_id", ""),
        role,
        "office_instance_id",
    )
    carrier_proof = _normalize_carrier_proof(
        kind,
        getattr(args, "carrier_proof", None),
        role=role,
        office_instance_id=office_instance_id,
    )
    internal_id = str(
        carrier_proof.get("agent_id")
        if kind == "child_agent"
        else office_instance_id
    )
    task = load_tasks().get(str(getattr(args, "task_id", "")))
    if not isinstance(task, dict):
        raise ValueError(f"task not found: {getattr(args, 'task_id', '')}")
    agents = task.get("agents")
    record = agents.get(internal_id) if isinstance(agents, dict) else None
    if not isinstance(record, dict):
        raise ValueError(f"office instance not found: {office_instance_id}")
    if record.get("office_instance_id") != office_instance_id:
        raise ValueError("office_instance_id_mismatch")
    if record.get("office_instance_kind") != kind:
        raise ValueError("office_instance_kind_mismatch")
    if record.get("role") != role:
        raise ValueError("office_instance_role_mismatch")
    if record.get("carrier_proof") != carrier_proof:
        raise ValueError("office_carrier_proof_mismatch")
    if validate_semantic:
        _validate_agent_semantic_args(args, record)
    args.agent_id = internal_id
    args.office_instance_kind = kind
    args.office_instance_id = office_instance_id
    args.carrier_proof = carrier_proof
    args._office_lifecycle_explicit = True
    return task, record, internal_id


def _office_transition_payload(
    command: str,
    result: TransitionResult,
    internal_id: str,
) -> dict[str, object]:
    agents = result.task.get("agents")
    record = agents.get(internal_id) if isinstance(agents, dict) else None
    if not isinstance(record, dict):
        raise ValueError("office_instance_receipt_missing")
    return {
        "schema": "court.office.cli.v1",
        "ok": True,
        "command": command,
        "receipt": _office_lifecycle_receipt(
            result.task,
            record,
            action=command,
            event_id=result.event.get("event_id"),
        ),
        "office_instance": deepcopy(record),
        "event": deepcopy(result.event),
    }


def agent_start(args: argparse.Namespace) -> TransitionResult:
    require_text(args.scope, "scope")
    collaboration_task_name = require_text(
        getattr(args, "collaboration_task_name", ""),
        "collaboration-task-name",
    )
    requirements_text = require_text(
        getattr(args, "skill_requirements_json", ""),
        "skill-requirements-json",
    )
    try:
        skill_requirements = json.loads(requirements_text)
    except json.JSONDecodeError as exc:
        raise ValueError("skill requirements JSON is invalid") from exc
    if not isinstance(skill_requirements, list):
        raise ValueError("skill requirements JSON must contain an array")
    requires_gongjiang = getattr(args, "requires_gongjiang", False)
    if not isinstance(requires_gongjiang, bool):
        raise ValueError("requires-gongjiang must be boolean")
    binding_inputs = {
        "role_key": require_text(args.role, "role"),
        "collaboration_task_name": collaboration_task_name,
        "court_agent_id": require_text(args.agent_id, "agent-id"),
        "requires_gongjiang": requires_gongjiang,
        "skill_requirements": skill_requirements,
    }
    args._office_assignment_binding = build_office_assignment_binding(
        **binding_inputs,
    )
    args._office_assignment_binding_inputs = binding_inputs
    return agent_event(args, "agent_start", "starting", "evidence")


def agent_preload_ack(args: argparse.Namespace) -> dict[str, Any]:
    from commands.court_native_bridge import captured_child_read_order, NativeEvidencePending
    evidence = require_text(args.evidence, "evidence")
    if isinstance(getattr(args, "native_request_ref", None), str) and args.native_request_ref:
        args.native_request_ref = _required_context_object(args.native_request_ref, "native_request_ref_required")
    agent_id = require_text(args.agent_id, "agent-id")
    role = require_text(args.role, "role")
    loaded_skills = [item.strip() for item in re.split(r"[,;]", args.loaded_skills) if item.strip()]
    explicit_office_zh = str(getattr(args, "office_zh", "") or "").strip()
    ack = {
        "schema": args.schema,
        "preload_status": args.preload_status,
        "role_key": role,
        "office_zh": None,
        "direct_superior": args.direct_superior,
        "profile_source": getattr(args, "profile_source", None),
        "dossier_path": getattr(args, "dossier_path", None),
        "court_skill_path": getattr(args, "court_skill_path", None),
        "profile_loaded": getattr(args, "profile_loaded", None),
        "court_skill_loaded": getattr(args, "court_skill_loaded", None),
        "court_code": getattr(args, "court_code", None),
        "agent_dossier_loaded": args.agent_dossier_loaded,
        "loaded_skills": loaded_skills,
        "model_route_id": args.model_route_id,
        "active_model": args.active_model or None,
        "active_reasoning_effort": args.active_reasoning_effort or None,
        "model_override_applied": args.model_override_applied == "YES",
        "inheritance_policy": args.inheritance_policy or None,
    }
    failure = ""
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        agents = task.get("agents")
        if not isinstance(agents, dict) or not isinstance(agents.get(agent_id), dict):
            raise ValueError(f"agent not started: {agent_id}")
        current = dict(agents[agent_id])
        if current.get("role") != role:
            raise ValueError("preload ack role does not match started agent")
        current_status = str(current.get("status") or "")
        final_status = str(current.get("final_status") or "")
        release_status = str(current.get("release_status") or "")
        if (
            current_status in TERMINAL_AGENT_STATUSES
            or final_status in TERMINAL_AGENT_STATUSES
            or release_status == "closed"
        ):
            raise ValueError("terminal agent cannot accept a preload acknowledgement")
        now = now_text()
        try:
            manifest = build_preload_manifest(
                role,
                carrier_kind=_canonical_office_instance_kind(
                    current.get("office_instance_kind")
                ),
                court_code=case_reference(task)["court_code"],
            )
            ack["office_zh"] = manifest.office_zh
            if explicit_office_zh and explicit_office_zh != manifest.office_zh:
                raise ValueError("preload ack office_zh does not match role manifest")
            model_route = current.get("model_route")
            if not isinstance(model_route, dict):
                raise ValueError("started agent is missing model route")
            validated = validate_preload_ack(manifest, ack, model_route=model_route)
            if isinstance(current.get('native_host_spawn_evidence'), dict):
                if not getattr(args, 'native_request_ref', None):
                    raise NativeEvidencePending('native_spawn_child_request_acknowledgement_missing')
                if (getattr(args, 'native_request_ref', None)
                        != current.get('native_host_request_ref')):
                    raise ValueError('native_spawn_requires_child_request_acknowledgement')
            read_order = captured_child_read_order(current, manifest, task_id=args.task_id)
        except NativeEvidencePending as exc:
            # An incomplete host trace is retryable; it does not close the office
            # or credit a parent-supplied declaration as child acceptance.
            raise ValueError(f'preload_pending: {exc}') from exc
        except ValueError as exc:
            failure = str(exc)
            current.update(
                status="failed",
                final_status="failed",
                release_status="closed",
                preload_status="FAILED",
                model_route_status="FAILED",
                failure_kind="preload_contract_failed",
                office_identity_evidence="FAILED",
                office_execution_ready=False,
                finished_at=now,
                closed_at=now,
            )
        else:
            if read_order is not None:
                current['child_skill_read_order'] = read_order
                current['native_request_delivery'] = 'PRELOAD_ACKNOWLEDGED'
                current['preload_ack_request_ref'] = args.native_request_ref
            current.update(
                status="running",
                preload_status="PASSED",
                model_route_status="PASSED",
                preload_ack_at=now,
                office_identity_evidence="PASSED",
                office_execution_ready=True,
                loaded_skills=validated["loaded_skills"],
                profile_source=validated["profile_source"],
                dossier_path=validated["dossier_path"],
                court_skill_path=validated["court_skill_path"],
                profile_loaded=validated["profile_loaded"],
                court_skill_loaded=validated["court_skill_loaded"],
                court_code=validated["court_code"],
                agent_dossier_loaded=validated["agent_dossier_loaded"],
                model_route_id=validated["model_route_id"],
                active_model=validated.get("active_model"),
                active_reasoning_effort=validated.get("active_reasoning_effort"),
                model_override_applied=validated["model_override_applied"],
                inheritance_policy=validated.get("inheritance_policy"),
            )
        current.update(last_heartbeat=now, last_evidence=evidence, updated_at=now)
        agents[agent_id] = current
        task["updated_at"] = now
        task["last_evidence"] = f"agent_preload_ack {agent_id}: {evidence}"
        tasks[args.task_id] = task
        event = make_event(
            task,
            "agent_preload_ack",
            "starting",
            "failed" if failure else "running",
            args.actor,
            evidence,
            args.note,
        )
        event.update(
            agent_id=agent_id,
            agent_role=role,
            preload_status=current["preload_status"],
            model_route_status=current["model_route_status"],
            model_route_id=current.get("model_route_id") or current.get("model_route", {}).get("model_route_id"),
        )
        event["event_id"] = _office_event_id(
            event,
            str(current.get("office_instance_id") or agent_id),
        )
        _commit_task_event(tasks, event)
    if failure:
        raise ValueError(f"preload_contract_failed: {failure}")
    return {
        "kind": "court_agent_preload_ack",
        "task_id": args.task_id,
        "agent": current,
        "ack": ack,
        "event": event,
    }


def agent_heartbeat(args: argparse.Namespace) -> TransitionResult:
    return agent_event(args, "agent_heartbeat", "running", "evidence")


def agent_report(args: argparse.Namespace) -> TransitionResult:
    return agent_event(args, "agent_report", "running", "evidence")


def agent_finish(args: argparse.Namespace) -> TransitionResult:
    direct_envelope = getattr(args, "result_envelope", None)
    envelope_file = getattr(args, "result_envelope_file", None)
    has_semantic_binding = any(
        getattr(args, field, None) is not None for field in AGENT_SEMANTIC_ARG_FIELDS
    )
    if direct_envelope is not None or envelope_file is not None:
        envelope = normalize_result_envelope(
            _json_object_from_args(
                args,
                "result_envelope",
                "result_envelope_file",
                "structured result envelope",
            )
        )
        if str(getattr(args, "result", "") or "").strip():
            raise ValueError("free_text_result_not_allowed_with_envelope")
        if getattr(args, "status", envelope["status"]) != envelope["status"]:
            raise ValueError("result_envelope_status_mismatch")
        args._result_envelope = envelope
        args.status = envelope["status"]
    elif has_semantic_binding:
        raise ValueError("structured_result_envelope_required")
    else:
        require_text(args.result, "result")
    return agent_event(args, "agent_finish", args.status, "evidence")


def agent_close(args: argparse.Namespace) -> TransitionResult:
    require_text(args.result, "result")
    args.status = "closed"
    return agent_event(args, "agent_close", "closed", "evidence")


def _native_bridge_selector(
    args: argparse.Namespace,
    *,
    capture: bool,
) -> dict[str, str]:
    from commands.court_native_bridge import (
        normalize_native_capture_input,
        normalize_native_request_input,
    )

    raw = {
        field: getattr(args, field, None)
        for field in ("schema", "task_id", "wave_id", "instance_id")
    }
    return (
        normalize_native_capture_input(raw)
        if capture
        else normalize_native_request_input(raw)
    )


def _native_bridge_task_binding(
    selector: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, object], dict[str, object]]:
    task_id = selector["task_id"]
    wave_id = selector["wave_id"]
    instance_id = selector["instance_id"]
    task = load_tasks().get(task_id)
    if not isinstance(task, dict):
        raise ValueError(f"task not found: {task_id}")
    require_semantic_mutation_binding(task)
    admissions = task.get("agent_admissions")
    admission = admissions.get(wave_id) if isinstance(admissions, Mapping) else None
    if not isinstance(admission, dict) or admission.get("allowed") is not True:
        raise ValueError("native_bridge:allowed_admission_required")
    _validate_admission_immutable_event_anchor(task, admission)
    selected = admission.get("selected_bindings")
    if not isinstance(selected, (list, tuple)):
        raise ValueError("native_bridge:admission_bindings_invalid")
    matches = [
        dict(binding)
        for binding in selected
        if isinstance(binding, Mapping)
        and str(binding.get("instance_id") or "").strip().lower() == instance_id
    ]
    if len(matches) != 1:
        raise ValueError("native_bridge:admitted_instance_not_unique")
    binding = matches[0]
    if str(binding.get("role") or "").strip().lower() not in OFFICES:
        raise ValueError("native_bridge:binding_role_invalid")
    if not str(binding.get("direct_superior") or "").strip():
        raise ValueError("native_bridge:binding_superior_missing")
    return task, admission, binding


def _native_bridge_identity_context(
    task: Mapping[str, object], binding: Mapping[str, object],
) -> dict[str, object] | None:
    """Trusted ancestry for capture, not a claim about the CLI caller's role.

    A read-only request may be prepared before its caller identity is known.
    Only the actual host-issued child path proves who spawned it. Shared
    session IDs cannot prove a child thread or a followup sender.
    """
    from commands.court_native_bridge import current_host_identity
    from court_case_binding import validate_case_binding

    identity = current_host_identity()
    case = task.get("case_binding")
    if not isinstance(case, Mapping):
        return None
    validate_case_binding(case, task)
    if str(case.get("session_id") or "").lower() != identity["session_id"]:
        raise ValueError("native_bridge:case_root_binding_invalid")
    superior = binding.get("direct_superior")
    parents = []
    if superior == "taizi":
        parents.append({"path": "/root", "kind": "taizi_root"})
    elif superior == "shangshu":
        for record in task.get("agents", {}).values():
            if (isinstance(record, Mapping) and record.get("role") == "shangshu"
                    and record.get("direct_superior") == "taizi"
                    and record.get("native_host_identity_kind") == "canonical_agent_path"
                    and record.get("native_trace_session_id") == identity["session_id"]
                    and record.get("semantic_epoch") == task.get("semantic_epoch")
                    and record.get("case_ref") == case_reference(task)
                    and record.get("preload_status") == "PASSED"
                    and record.get("office_execution_ready") is True
                    and record.get("status") not in TERMINAL_AGENT_STATUSES
                    and record.get("release_status") not in {"closed", "cancel_requested"}
                    and not any(str(record.get(field) or "").upper().startswith("INVALIDATED")
                                for field in ("status", "final_status", "assignment_status"))
                    and not record.get("invalidated_at")
                    and record.get("assignment_invalidated_by_semantic_resume") is not True
                    and not record.get("assignment_invalidated_by_charter_revision")
                    and record.get("native_host_action_receipt_id")):
                parent = {"path": record.get("native_host_instance_id"),
                          "kind": "same_case_ready_shangshu"}
                if record.get('native_child_thread_id'):
                    parent['thread_id'] = record['native_child_thread_id']
                parents.append(parent)
    return {"case_session_id": identity["session_id"],
            "semantic_epoch": task.get("semantic_epoch"),
            "trusted_parent_paths": parents}


def _native_bridge_caller_guard(
    task: Mapping[str, object],
    binding: Mapping[str, object],
) -> None:
    from commands.court_native_bridge import current_host_identity

    identity = current_host_identity()
    current_thread = identity["thread_id"]
    current_session = identity["session_id"]
    context = _native_bridge_identity_context(task, binding)
    if context and context["trusted_parent_paths"]:
        # No mutation is admitted here. Capture must verify exact host ancestry.
        return
    case_binding = task.get("case_binding")
    if isinstance(case_binding, Mapping):
        try:
            from court_case_binding import validate_case_binding

            validate_case_binding(case_binding, task)
        except (ImportError, TypeError, ValueError) as exc:
            raise ValueError("native_bridge:case_root_binding_invalid") from exc
        if (
            str(case_binding.get("session_id") or "").strip().lower()
            == current_session
            and str(binding.get("direct_superior") or "").strip().lower()
            == "taizi"
        ):
            return

    expected_role = str(binding.get("direct_superior") or "").strip().lower()
    agents = task.get("agents")
    if not isinstance(agents, Mapping):
        raise ValueError("native_bridge:caller_native_actor_required")
    for record in agents.values():
        if not isinstance(record, Mapping):
            continue
        if str(record.get("role") or "").strip().lower() != expected_role:
            continue
        if record.get("native_host_identity_kind") == "canonical_agent_path":
            continue
        if str(record.get("native_host_thread_id") or "").strip() != current_thread:
            continue
        if not str(record.get("native_host_action_receipt_id") or "").strip():
            continue
        if record.get("preload_status") != "PASSED" or record.get(
            "office_execution_ready"
        ) is not True:
            continue
        if str(record.get("status") or "").strip().lower() in TERMINAL_AGENT_STATUSES:
            continue
        return
    raise ValueError("native_bridge:caller_native_actor_required")


def _native_bridge_target_record(
    task: Mapping[str, object],
    binding: Mapping[str, object],
) -> dict[str, object] | None:
    agents = task.get("agents")
    if not isinstance(agents, Mapping):
        return None
    instance_id = str(binding.get("instance_id") or "").strip().lower()
    role = str(binding.get("role") or "").strip().lower()
    matches = [
        dict(record)
        for record in agents.values()
        if isinstance(record, Mapping)
        and str(record.get("office_instance_id") or "").strip().lower()
        == instance_id
        and str(record.get("role") or "").strip().lower() == role
    ]
    if len(matches) > 1:
        raise ValueError("native_bridge:target_native_actor_ambiguous")
    return matches[0] if matches else None


def _native_bridge_request(task: Mapping[str, object], admission: Mapping[str, object], binding: Mapping[str, object]) -> dict[str, object]:
    from court_native_host_dispatch import normalize_native_host_dispatch_request
    preload = binding.get('preload_sources')
    model_inputs = admission.get('model_route_inputs')
    admission_event_id = _admission_event_id(task, admission)
    if not isinstance(preload, Mapping) or not isinstance(model_inputs, Mapping) or (not admission_event_id):
        raise ValueError('native_bridge:admission_facts_incomplete')
    assignment = require_text(model_inputs.get('assignment'), 'assignment')
    read_scope = binding.get('read_scope') or binding.get('write_set')
    write_set = binding.get('write_set') or binding.get('read_scope')
    if not isinstance(read_scope, (list, tuple)) or not isinstance(write_set, (list, tuple)):
        raise ValueError('native_bridge:binding_scope_invalid')
    request: dict[str, object] = {
        'schema': 'court.native_host_dispatch_request.v1',
        'task_id': task.get('task_id'),
        'wave_id': admission.get('wave_id'),
        'dispatch_uid': admission.get('dispatch_uid'),
        'attempt': admission.get('attempt'),
        'role': binding.get('role'),
        'instance_id': binding.get('instance_id'),
        'direct_superior': binding.get('direct_superior'),
        'semantic_epoch': admission.get('semantic_epoch'),
        'case_ref': admission.get('case_ref'),
        'office_capsule_ref': deepcopy(binding.get('office_capsule_ref')),
        'lease_id': binding.get('lease_id'),
        'assignment': assignment,
        'duty_scope': list(read_scope),
        'write_set': list(write_set),
        'role_ack': {
            'role': binding.get('role'),
            'direct_superior': binding.get('direct_superior'),
            **_native_role_ack_sources(preload),
        },
        'admission_anchor': {
            'schema': 'court.agent.admission_receipt.v1',
            'receipt_id': admission_event_id,
        },
        'compatible_live_instances': [],
    }
    target = _native_bridge_target_record(task, binding)
    if target is not None:
        if target.get('native_host_identity_kind') == 'canonical_agent_path':
            raise ValueError('native_bridge:canonical_followup_issuer_unavailable')
        if str(target.get('status') or '').strip().lower() in TERMINAL_AGENT_STATUSES:
            raise ValueError('native_bridge:target_native_actor_terminal')
        raw_ratio = target.get('native_host_context_utilization')
        if isinstance(raw_ratio, bool) or not isinstance(raw_ratio, (int, float)):
            raise ValueError('native_bridge:reuse_context_unavailable')
        host_fields = {
            'host_task_id': target.get('native_host_task_id'),
            'host_thread_id': target.get('native_host_thread_id'),
            'host_instance_id': target.get('native_host_instance_id'),
        }
        if not all((isinstance(value, str) and value.strip() for value in host_fields.values())):
            raise ValueError('native_bridge:target_host_identity_missing')
        request['compatible_live_instances'] = [{
            **host_fields,
            'task_id': request['task_id'],
            'role': request['role'],
            'direct_superior': request['direct_superior'],
            'assignment': request['assignment'],
            'duty_scope': deepcopy(request['duty_scope']),
            'semantic_receipt': {
                'semantic_epoch': request['semantic_epoch'],
                'case_ref': request['case_ref'],
            },
            'lease_id': request['lease_id'],
            'write_set': deepcopy(request['write_set']),
            'role_ack': deepcopy(request['role_ack']),
            'context_utilization': float(raw_ratio),
            'status': str(target.get('status') or '').strip().lower(),
        }]
    return normalize_native_host_dispatch_request(request)


def _native_bridge_host_message_inputs(
    task: Mapping[str, object],
    admission: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    from court_native_execution import AUTHORITIES

    case_binding = task.get("case_binding")
    if not isinstance(case_binding, Mapping):
        raise ValueError("native_bridge:case_execution_required")
    execution = case_binding.get("case_execution")
    if not isinstance(execution, Mapping):
        raise ValueError("native_bridge:case_execution_required")
    normalized_execution = {
        "authority": str(execution.get("authority") or "").strip().lower(),
        "behavior": str(execution.get("behavior") or "").strip().lower(),
    }
    if (normalized_execution["authority"] not in AUTHORITIES
            or normalized_execution["behavior"] != "parallel"):
        raise ValueError("native_bridge:native_topology_required")
    return normalized_execution, public_dispatch_context_packet(
        task, str(admission.get("wave_id") or "")
    )


def _native_bridge_bound_agent_type(
    admission: Mapping[str, object],
    binding: Mapping[str, object],
) -> str | None:
    """Use the admitted model-route spawn contract; never accept free overrides."""

    instance_id = str(binding.get("instance_id") or "").strip().lower()
    role = str(binding.get("role") or "").strip().lower()
    selected_protocol = str(admission.get("selected_protocol") or "").strip().lower()
    routes = admission.get("model_routes")
    route = routes.get(instance_id) if isinstance(routes, Mapping) else None
    if not isinstance(route, Mapping):
        raise ValueError("native_bridge:model_route_binding_missing")
    if (
        str(route.get("transport") or "").strip().lower() != "codex"
        or str(route.get("protocol") or "").strip().lower() != selected_protocol
        or str(route.get("role") or "").strip().lower() != role
    ):
        raise ValueError("native_bridge:model_route_binding_mismatch")
    metadata = route.get("spawn_metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("native_bridge:spawn_metadata_missing")
    if any(field in metadata for field in ("model", "reasoning_effort")):
        raise ValueError("native_bridge:model_override_rejected")
    if metadata.get("fork_turns") != "none":
        raise ValueError("native_bridge:spawn_fork_turns_mismatch")
    value = metadata.get("agent_type")
    if selected_protocol == "v1":
        if not isinstance(value, str) or value.strip().lower() != role:
            raise ValueError("native_bridge:bound_agent_type_missing_or_mismatch")
        return role
    if selected_protocol == "v2":
        if value is not None:
            raise ValueError("native_bridge:reserved_agent_type_override_rejected")
        return None
    raise ValueError("native_bridge:selected_protocol_invalid")


NATIVE_BRIDGE_ENTRY_PRELOAD_BUDGET_BYTES = ENTRY_PRELOAD_BUDGET_BYTES


def _native_bridge_preload_input_budget(
    binding: Mapping[str, object],
    host_message: str,
) -> dict[str, object]:
    """Measure one selected office's verified preload plus compact host input."""

    from court_office_bootstrap import ROOT as office_root

    role = require_text(binding.get("role"), "role").strip().lower()
    carrier_kind = str(binding.get("office_instance_kind") or "child_agent").strip()
    if carrier_kind != "child_agent":
        raise ValueError("native_bridge:ordinary_child_carrier_required")
    manifest = build_preload_manifest(role, carrier_kind=carrier_kind)
    expected_sources = _semantic_preload_sources(role)
    if binding.get("preload_sources") != expected_sources:
        raise ValueError("native_bridge:preload_source_binding_mismatch")
    root = Path(office_root).resolve()
    relative_paths = {
        "profile_bytes": manifest.profile_source,
        "dossier_bytes": manifest.dossier_path,
        "court_skill_bytes": manifest.court_skill_path,
    }
    measured: dict[str, int] = {}
    for label, locator in relative_paths.items():
        source = root / Path(locator)
        if source.is_symlink() or not source.is_file():
            raise ValueError("native_bridge:preload_source_invalid")
        candidate = source.resolve(strict=True)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("native_bridge:preload_path_outside_root") from exc
        if not candidate.is_file():
            raise ValueError("native_bridge:preload_source_invalid")
        measured[label] = candidate.stat().st_size
    host_input_bytes = len(host_message.encode("utf-8"))
    preload_bytes = sum(measured.values())
    total_bytes = preload_bytes + host_input_bytes
    if total_bytes > NATIVE_BRIDGE_ENTRY_PRELOAD_BUDGET_BYTES:
        raise ValueError(f"native_bridge:entry_preload_budget_exceeded:{total_bytes}>{NATIVE_BRIDGE_ENTRY_PRELOAD_BUDGET_BYTES}")
    return {
        "schema": "court.native_host_input_budget.v1",
        "limit_bytes": NATIVE_BRIDGE_ENTRY_PRELOAD_BUDGET_BYTES,
        **measured,
        "preload_bytes": preload_bytes,
        "host_input_bytes": host_input_bytes,
        "total_bytes": total_bytes,
        "status": "within_budget",
    }


def _native_bridge_request_result(
    task: Mapping[str, object],
    admission: Mapping[str, object],
    binding: Mapping[str, object],
    request: Mapping[str, object],
) -> dict[str, object]:
    from commands.court_native_bridge import native_request_result

    execution, p00_context = _native_bridge_host_message_inputs(task, admission)
    agent_type = _native_bridge_bound_agent_type(admission, binding)
    result = native_request_result(
        request,
        execution=execution,
        p00_context=p00_context,
        agent_type=agent_type,
    )
    message = result.get("host_message")
    if not isinstance(message, str):
        raise ValueError("native_bridge:host_message_missing")
    result["host_input_budget"] = _native_bridge_preload_input_budget(
        binding,
        message,
    )
    result["bound_agent_type"] = agent_type
    return result


def _native_bridge_model_inputs(admission: Mapping[str, object]) -> dict[str, object]:
    value = admission.get("model_route_inputs")
    if not isinstance(value, Mapping):
        raise ValueError("native_bridge:model_route_inputs_missing")
    required = ("assignment", "task_focus", "complexity", "risk", "ambiguity", "transport")
    result = {field: value.get(field) for field in required}
    if any(not isinstance(item, str) or not item.strip() for item in result.values()):
        raise ValueError("native_bridge:model_route_inputs_invalid")
    return result


def _native_bridge_start_request(task: Mapping[str, object], admission: Mapping[str, object], binding: Mapping[str, object], request: Mapping[str, object], capture: Mapping[str, object]) -> dict[str, object]:
    request_ref = capture.get('request_ref')
    if request_ref != native_request_reference(request):
        raise ValueError('native_bridge:request_reference_mismatch')
    suffix = native_task_suffix(request)
    role = require_text(binding.get('role'), 'role').strip().lower()
    instance_id = require_text(binding.get('instance_id'), 'instance-id').strip().lower()
    inputs = _native_bridge_model_inputs(admission)
    agent_id = f'{role}-native-{suffix}'
    collaboration_task_name = f"{role.replace('-', '_')}_native_{suffix}"
    preload = build_preload_manifest(role)
    required_skill = {
        'name': 'decretum-matrix',
        'source': str((skill_root() / 'SKILL.md').resolve()),
        'purpose': 'native office lifecycle',
        'ack_name': 'decretum-matrix',
    }
    office_request = {
        'task_id': task.get('task_id'),
        'semantic_epoch': admission.get('semantic_epoch'),
        'case_ref': admission.get('case_ref'),
        'checkpoint_id': admission.get('checkpoint_id'),
        'dispatch_uid': admission.get('dispatch_uid'),
        'attempt': admission.get('attempt'),
        'role': role,
        'collaboration_task_name': collaboration_task_name,
        'requires_gongjiang': False,
        'skill_requirements_json': json.dumps([required_skill]),
        'scope': inputs['assignment'],
        'task_focus': inputs['task_focus'],
        'complexity': inputs['complexity'],
        'risk': inputs['risk'],
        'ambiguity': inputs['ambiguity'],
        'transport': inputs['transport'],
        'wave_id': admission.get('wave_id'),
        'dispatch_requested_at': admission.get('dispatch_requested_at'),
        'fork_turns': 'none',
        'context_tokens': admission.get('context_tokens', 0),
        'dispatch_context_packet': public_dispatch_context_packet(task, str(admission.get('wave_id') or '')),
        'context_budget_pool': deepcopy(admission['context_budget_pool_ref'])
            if isinstance(admission.get('context_budget_pool_ref'), Mapping)
            else public_context_budget_pool(task, str(admission.get('wave_id') or '')),
        'context_result_mode': admission.get('context_result_mode', 'bounded_structured_receipt'),
        'context_tool_output_mode': admission.get('context_tool_output_mode', 'pointer'),
        'context_override_source': admission.get('context_override_source'),
        'system_memory_percent': admission.get('context_system_memory_percent', 0.0),
        'deadline_seconds': admission.get('deadline_seconds', AGENT_DEFAULT_DEADLINE_SECONDS),
        'tool_call_budget': admission.get('tool_call_budget', AGENT_DEFAULT_TOOL_CALL_BUDGET),
        'office_instance_kind': 'child_agent',
        'office_instance_id': instance_id,
        'carrier_proof': {
            'agent_id': agent_id,
        },
        'native_host_action_receipt': deepcopy(capture['native_host_action_receipt']),
        'actor': binding.get('direct_superior'),
        'evidence': 'native_host_capture request_ref=' + json.dumps(request_ref, sort_keys=True),
        'note': 'current-session native host capture',
    }
    try:
        _revalidate_context_economy_start(dict(task), dict(admission), dict(binding), argparse.Namespace(**office_request), wave_id=str(admission.get('wave_id') or ''))
    except ValueError as exc:
        raise ValueError(f'native_bridge:office_start_context_reconstruction_failed:{exc}') from exc
    return office_request


def _native_bridge_followup_request(task: Mapping[str, object], binding: Mapping[str, object], request: Mapping[str, object], capture: Mapping[str, object]) -> dict[str, object]:
    record = _native_bridge_target_record(task, binding)
    if not isinstance(record, Mapping):
        raise ValueError('native_bridge:followup_target_missing')
    carrier_proof = record.get('carrier_proof')
    if not isinstance(carrier_proof, Mapping):
        raise ValueError('native_bridge:followup_carrier_proof_missing')
    return {
        'task_id': task.get('task_id'),
        'semantic_epoch': record.get('semantic_epoch'),
        'case_ref': record.get('case_ref'),
        'checkpoint_id': record.get('checkpoint_id'),
        'dispatch_uid': record.get('dispatch_uid'),
        'attempt': record.get('attempt'),
        'role': binding.get('role'),
        'office_instance_kind': record.get('office_instance_kind'),
        'office_instance_id': record.get('office_instance_id'),
        'carrier_proof': deepcopy(dict(carrier_proof)),
        'assignment': request.get('assignment'),
        'duty_scope': deepcopy(request.get('duty_scope')),
        'native_host_action_receipt': deepcopy(capture['native_host_action_receipt']),
        'actor': binding.get('direct_superior'),
        'evidence': 'native_host_capture request_ref=' + json.dumps(capture.get('request_ref'), sort_keys=True),
        'note': 'current-session native host capture',
    }


def office_native_request(args: argparse.Namespace) -> dict[str, object]:
    """Build a host-native request from admitted runtime facts without mutation."""

    selector = _native_bridge_selector(args, capture=False)
    task, admission, binding = _native_bridge_task_binding(selector)
    _native_bridge_caller_guard(task, binding)
    request = _native_bridge_request(task, admission, binding)
    return _native_bridge_request_result(task, admission, binding, request)


def office_native_capture(args: argparse.Namespace) -> dict[str, object]:
    """Derive one existing office lifecycle request from current-session evidence."""

    from commands.court_native_bridge import capture_current_native_delivery

    selector = _native_bridge_selector(args, capture=True)
    task, admission, binding = _native_bridge_task_binding(selector)
    _native_bridge_caller_guard(task, binding)
    request = _native_bridge_request(task, admission, binding)
    native_request = _native_bridge_request_result(task, admission, binding, request)
    execution, p00_context = _native_bridge_host_message_inputs(task, admission)
    captured = capture_current_native_delivery(
        request,
        execution=execution,
        p00_context=p00_context,
        agent_type=native_request.get("bound_agent_type"),
        identity_context=_native_bridge_identity_context(task, binding),
    )
    command = captured.get("office_command")
    if command == "start":
        office_request = _native_bridge_start_request(
            task, admission, binding, request, captured
        )
    elif command == "followup":
        office_request = _native_bridge_followup_request(
            task, binding, request, captured
        )
    else:
        raise ValueError("native_bridge:office_command_invalid")
    result = dict(captured)
    result["host_message"] = native_request["host_message"]
    result["host_input_budget"] = native_request["host_input_budget"]
    result["office_request"] = office_request
    return result


def office_start(args: argparse.Namespace) -> dict[str, object]:
    _prepare_office_start_args(args)
    result = agent_start(args)
    return _office_transition_payload("start", result, str(args.agent_id))


def office_followup(args: argparse.Namespace) -> dict[str, object]:
    args._production_cli = True
    _, _, internal_id = _prepare_office_action_args(args)
    evidence = require_text(args.evidence, "evidence")
    role = require_text(args.role, "role").strip().lower()
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(str(args.task_id))
        if not isinstance(task, dict):
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        _reject_native_host_receipt_replay(task, args)
        if args.actor not in OFFICES:
            raise ValueError(f"unknown actor office: {args.actor}")
        agents = task.get("agents")
        record = agents.get(internal_id) if isinstance(agents, dict) else None
        if not isinstance(record, dict):
            raise ValueError(f"office instance not found: {args.office_instance_id}")
        if record.get("role") != role:
            raise ValueError("office_instance_role_mismatch")
        if record.get("office_instance_id") != args.office_instance_id:
            raise ValueError("office_instance_id_mismatch")
        if record.get("carrier_proof") != args.carrier_proof:
            raise ValueError("office_carrier_proof_mismatch")
        _validate_agent_semantic_args(args, record)
        if (
            str(record.get("status") or "") in TERMINAL_AGENT_STATUSES
            or str(record.get("final_status") or "") in TERMINAL_AGENT_STATUSES
            or record.get("release_status") == "closed"
        ):
            raise ValueError("terminal office instance cannot accept followup")

        wave_id = str(record.get("wave_id") or "")
        admissions = task.get("agent_admissions")
        admission = admissions.get(wave_id) if isinstance(admissions, dict) else None
        if not isinstance(admission, dict) or admission.get("allowed") is not True:
            raise ValueError(f"allowed agent admission not found: {wave_id}")
        _validate_admission_immutable_event_anchor(task, admission)
        selected_bindings = admission.get("selected_bindings")
        if not isinstance(selected_bindings, (list, tuple)):
            raise ValueError("office followup admission bindings are corrupt")
        instance_id = str(record.get("admission_instance_id") or "").strip().lower()
        matched_bindings = [
            binding
            for binding in selected_bindings
            if isinstance(binding, dict)
            and str(binding.get("instance_id") or "").strip().lower()
            == instance_id
        ]
        if len(matched_bindings) != 1:
            raise ValueError("office followup requires one admitted instance-id")
        consumed_instances = admission.get("consumed_instances")
        if (
            not isinstance(consumed_instances, dict)
            or consumed_instances.get(instance_id) != internal_id
        ):
            raise ValueError("office followup instance is not live")

        native_host_receipt = _validate_native_host_receipt_for_runtime(
            task,
            admission,
            matched_bindings[0],
            args,
            decision="reuse",
            host_action="followup",
            outcome="succeeded",
            record=record,
        )
        if native_host_receipt is None:
            raise ValueError("native_host_action_receipt:required")

        now = now_text()
        current = dict(record)
        followups = current.get("native_host_followups")
        if followups is None:
            followups = []
        if not isinstance(followups, list):
            raise ValueError("native_host_followup_ledger_corrupt")
        request = native_host_receipt["request"]
        if not isinstance(request, Mapping):
            raise ValueError("native_host_action_receipt:embedded_request_required")
        followups = list(followups)
        followups.append(
            {
                "receipt_id": native_host_receipt.get("receipt_id"),
                "receipt_sha256": native_host_receipt.get("receipt_sha256"),
                "request_sha256": native_host_receipt.get("request_sha256"),
                "result_sha256": native_host_receipt.get("result_sha256"),
                "assignment": request.get("assignment"),
                "duty_scope": deepcopy(request.get("duty_scope")),
                "host_task_id": native_host_receipt.get("host_task_id"),
                "host_thread_id": native_host_receipt.get("host_thread_id"),
                "host_instance_id": native_host_receipt.get("host_instance_id"),
                "host_action_id": native_host_receipt.get("host_action_id"),
                "acted_at": native_host_receipt.get("acted_at"),
                "recorded_at": now,
            }
        )
        current["native_host_followups"] = followups
        current["last_heartbeat"] = now
        current["last_evidence"] = evidence
        current["updated_at"] = now
        _record_native_host_receipt(
            task,
            native_host_receipt,
            lifecycle_action="followup",
            target_id=internal_id,
        )
        agents[internal_id] = current
        task["updated_at"] = now
        task["last_evidence"] = f"office_followup {internal_id}: {evidence}"
        tasks[str(args.task_id)] = task
        status = str(current.get("status") or "running")
        event = make_event(
            task,
            "office_followup",
            status,
            status,
            args.actor,
            evidence,
            args.note,
        )
        event.update(
            agent_id=internal_id,
            agent_role=role,
            office_instance_id=current.get("office_instance_id"),
            native_host_action_receipt_id=native_host_receipt.get("receipt_id"),
            native_host_action_receipt_sha256=native_host_receipt.get(
                "receipt_sha256"
            ),
        )
        event["event_id"] = _office_event_id(
            event,
            str(current.get("office_instance_id") or internal_id),
        )
        _commit_task_event(tasks, event)
    return _office_transition_payload(
        "followup",
        TransitionResult(task, event),
        internal_id,
    )


def office_preload_ack(args: argparse.Namespace) -> dict[str, object]:
    _, _, internal_id = _prepare_office_action_args(args)
    result = agent_preload_ack(args)
    task = load_tasks()[str(args.task_id)]
    agents = task.get("agents")
    record = agents.get(internal_id) if isinstance(agents, dict) else None
    if not isinstance(record, dict):
        raise ValueError("office_instance_receipt_missing")
    event = result.get("event")
    if not isinstance(event, dict):
        raise ValueError("office_preload_event_missing")
    return {
        "schema": "court.office.cli.v1",
        "ok": True,
        "command": "preload_ack",
        "receipt": _office_lifecycle_receipt(
            task,
            record,
            action="preload_ack",
            event_id=event.get("event_id"),
        ),
        "office_instance": deepcopy(record),
        "event": deepcopy(event),
    }


def office_report(args: argparse.Namespace) -> dict[str, object]:
    _, _, internal_id = _prepare_office_action_args(args)
    return _office_transition_payload("report", agent_report(args), internal_id)


def _adapt_office_result_envelope(
    args: argparse.Namespace,
    record: dict[str, object],
    internal_id: str,
) -> None:
    envelope = _json_object_from_args(
        args,
        "result_envelope",
        "result_envelope_file",
        "structured result envelope",
    )
    args._original_result_envelope = deepcopy(envelope)
    args._source_result_payload_sha256 = source_result_payload_sha256(envelope)
    carrier_matches = (
        envelope.get("office_instance_kind") == record.get("office_instance_kind")
        and envelope.get("carrier_proof") == record.get("carrier_proof")
    )
    envelope["agent_id"] = internal_id if carrier_matches else f"{internal_id}-stale-proof"
    envelope["worktree"] = str(record.get("worktree") or ".")
    args.result_envelope = envelope
    args.result_envelope_file = None


def office_finish(args: argparse.Namespace) -> dict[str, object]:
    _, record, internal_id = _prepare_office_action_args(args, validate_semantic=False)
    _adapt_office_result_envelope(args, record, internal_id)
    return _office_transition_payload("finish", agent_finish(args), internal_id)


def office_close(args: argparse.Namespace) -> dict[str, object]:
    _, _, internal_id = _prepare_office_action_args(args)
    return _office_transition_payload("close", agent_close(args), internal_id)


def update_heartbeat(args: argparse.Namespace) -> TransitionResult:
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        require_semantic_mutation_binding(task)
        actor = args.actor
        if actor not in OFFICES:
            raise ValueError(f"unknown actor office: {actor}")
        previous = str(task.get("heartbeat") or "")
        task["heartbeat"] = args.heartbeat
        task["updated_at"] = now_text()
        task["last_evidence"] = args.evidence
        tasks[args.task_id] = task
        event = make_event(task, "heartbeat", previous, str(task.get("state")), actor, args.evidence, args.note)
        _commit_task_event(tasks, event)
    return TransitionResult(task, event)


def list_tasks(args: argparse.Namespace) -> list[dict[str, Any]]:
    tasks = [normalize_task(task) for task in load_tasks().values()]
    state = getattr(args, "state", "")
    if state:
        tasks = [task for task in tasks if str(task.get("state")) == state]
    tasks.sort(key=lambda task: str(task.get("updated_at", "")), reverse=True)
    return tasks[: args.limit]


def render_cli(tasks: list[dict[str, Any]], events: list[dict[str, Any]]) -> str:
    events_by_task: dict[str, list[dict[str, object]]] = {}
    for event in events:
        events_by_task.setdefault(str(event.get("task_id") or ""), []).append(event)
    lines = ["COURT RUNTIME"]
    if not tasks:
        lines.append("tasks: none")
    else:
        lines.append("tasks:")
        for task in tasks:
            task_events = events_by_task.get(str(task.get("task_id") or ""), [])
            lines.append(f"- {task_summary(task, task_events)}")
            lines.append(f"  heartbeat: {task.get('heartbeat', '')}; evidence: {task.get('last_evidence', '')}")
    lines.append("recent_events:")
    if not events:
        lines.append("- none")
    for event in events[-12:]:
        lines.append(
            f"- {event.get('time')} | {event.get('task_id')} | {event.get('action')} | "
            f"{event.get('from_state')} -> {event.get('to_state')} | {event.get('actor')}"
        )
    return "\n".join(lines)


def status_payload(args: argparse.Namespace) -> dict[str, Any]:
    view = getattr(args, 'view', 'full')
    if view not in {'compact', 'full'}:
        raise ValueError('status_view_invalid: expected compact or full')
    tasks = list_tasks(args)
    if view == 'compact':
        return {'kind':'court_runtime_status', 'view':'compact',
                'runtime_schema_version':RUNTIME_SCHEMA_VERSION, 'generated_at':now_text(),
                'task_count':len(tasks), 'history_included':False,
                'tasks':[{key:task.get(key) for key in ('task_id','state','owner','updated_at','charter_revision','semantic_state')} for task in tasks],
                'details':'court workflow-status --task-id <task-id>; status --view full for history'}
    events = read_events(limit=None)
    events_by_task: dict[str, list[dict[str, object]]] = {}
    for event in events:
        events_by_task.setdefault(str(event.get("task_id") or ""), []).append(event)
    projected_tasks = []
    for task in tasks:
        projected = dict(task)
        completion = completion_projection(
            task, events_by_task.get(str(task.get("task_id") or ""), [])
        )
        projected["completion_status"] = completion["status"]
        projected["completion_verified"] = completion["verified"]
        projected["completion_projection"] = completion
        projected_tasks.append(projected)
    return {
        "kind": "court_runtime_status",
        "runtime_schema_version": RUNTIME_SCHEMA_VERSION,
        "generated_at": now_text(),
        "runtime_root": str(runtime_root()),
        "lock_path": str(lock_path()),
        "task_count": len(tasks),
        "tasks": projected_tasks,
        "recent_events": events[-12:],
        "dashboard": render_cli(tasks, events),
    }


def list_agents_payload(args: argparse.Namespace) -> dict[str, Any]:
    stale_after = max(1, int(args.stale_after))
    now = datetime.now().astimezone()
    agents: list[dict[str, Any]] = []
    for task in load_tasks().values():
        task = normalize_task(task)
        task_agents = task.get("agents", {})
        if not isinstance(task_agents, dict):
            continue
        for agent_id, agent in task_agents.items():
            if not isinstance(agent, dict):
                continue
            item = dict(agent)
            item["task_id"] = task.get("task_id")
            item["agent_id"] = str(agent_id)
            stale = False
            if item.get("status") not in {"completed", "failed", "cancelled", "closed"}:
                try:
                    stale = (now - datetime.fromisoformat(str(item.get("last_heartbeat")))).total_seconds() > stale_after
                except (TypeError, ValueError):
                    stale = True
            item["stale"] = stale
            agents.append(item)
    return {
        "kind": "court_agents",
        "generated_at": now_text(),
        "stale_after": stale_after,
        "count": len(agents),
        "agents": agents,
    }


def probe_payload() -> dict[str, Any]:
    root = runtime_root()
    tasks = tasks_path()
    events = events_path()
    degraded_reasons: list[str] = []
    if not root.exists():
        degraded_reasons.append("runtime_root_missing_until_first_write")
    fresh_worker_proof_path = reference_path(
        "private-runtime",
        "host-capabilities",
        "codex-fresh-worker-model-routing-v1.json",
    )
    fresh_worker_status = "host_proof_missing"
    fresh_worker_host_proof = None
    if fresh_worker_proof_path.is_file():
        try:
            proof = validate_host_proof(json.loads(fresh_worker_proof_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError):
            fresh_worker_status = "host_proof_invalid"
        else:
            fresh_worker_status = "verified"
            fresh_worker_host_proof = deepcopy(proof)
    return {
        "kind": "court_runtime_probe",
        "runtime_schema_version": RUNTIME_SCHEMA_VERSION,
        "generated_at": now_text(),
        "runtime_root": str(root),
        "tasks_path": str(tasks),
        "events_path": str(events),
        "lock_path": str(lock_path()),
        "ledger_readable": (not tasks.exists()) or os.access(tasks, os.R_OK),
        "ledger_writable": root.exists() and os.access(root, os.W_OK),
        "supported_commands": [
            "create",
            "bind-assessment",
            "transition",
            "heartbeat",
            "pause",
            "resume",
            "cancel",
            "office admit|start|followup|preload-ack|report|finish|close",
            "office native-request|native-capture",
            "agent-admit",
            "agent-spawn",
            "agent-start",
            "agent-preload-ack",
            "agent-heartbeat",
            "agent-report",
            "agent-finish",
            "agent-close",
            "agent-reconcile",
            "agent-spawn-failed",
            "agents",
            "list",
            "events",
            "status",
            "probe",
        ],
        "states": sorted(STATES),
        "transitions": {state: sorted(targets) for state, targets in sorted(TRANSITIONS.items())},
        "agent_runtime": {
            "kind": "codex-only",
            "capabilities": [
                "local_skill_files",
                "command_line_ui",
                "file_backed_ledger",
                "auditable_pause_resume_cancel",
            ],
            "subagent_host": "external_to_this_cli",
        },
        "heartbeat_capability": "manual_cli",
        "agent_dispatch_policy": {
            "topology": "ordinary_parallel",
            "wave_policy": "dynamic_by_duty_and_capacity",
            "static_wave_cap": None,
            "ordinary_wave_cap": None,
            "host_capacity_required": True,
            "host_occupancy_required": True,
            "host_retained_agents_required": True,
            "terminal_reclamation_evidence_required_when_retained": True,
            "next_depth_required": True,
            "active_session_protocol_required_for_auto": True,
            "max_threads": MAX_AGENT_TREE_THREADS,
            "max_depth": MAX_AGENT_TREE_DEPTH,
            "root_thread_counts_toward_limit": True,
            "unknown_capacity_occupancy_reclamation_or_depth": "fail_closed",
            "long_context_threshold_tokens": AGENT_LONG_CONTEXT_TOKENS,
            "long_context_fork_turns": "none",
            "max_recent_fork_turns": AGENT_MAX_RECENT_FORK_TURNS,
            "deadline_seconds": AGENT_DEFAULT_DEADLINE_SECONDS,
            "tool_call_budget": AGENT_DEFAULT_TOOL_CALL_BUDGET,
            "message_budget_schema": AGENT_MESSAGE_BUDGET_SCHEMA,
            "message_budget_policy": "bounded_quantized_growth_v1",
            "message_measurement": "unicode_code_points",
            "message_scope": "max_single_final_message_per_wave",
            "message_budget_floor_chars": AGENT_MESSAGE_BUDGET_FLOOR_CHARS,
            "message_budget_quantum_chars": AGENT_MESSAGE_BUDGET_QUANTUM_CHARS,
            "message_budget_ceiling_chars": AGENT_MESSAGE_BUDGET_CEILING_CHARS,
            "message_component_contract": "optional required+optional metadata must equal total",
            "message_body_storage": "forbidden",
            "oversize_action": "compress_or_split_then_new_wave_id",
            "reuse_errored_agents": False,
            "fatal_provider_retry": False,
        },
        "agent_model_routing": {
            "schema": MODEL_ROUTE_SCHEMA,
            "codex_models": dict(sorted(MODEL_MAX_REASONING_EFFORT.items())),
            "selection_inputs": ["assignment", "task_focus", "complexity", "risk", "ambiguity"],
            "codex_enforcement": "protocol_bound_child_inheritance_required",
            "model_visible_spawn_fields": ["message", "task_name", "fork_turns"],
            "host_override_status": "fresh_session_worker_verified" if fresh_worker_status == "verified" else "fresh_session_worker_requires_host_proof",
            "v1_v2_child_override_status": "unavailable_in_current_reserved_spawn_path",
            "fresh_worker_override_status": fresh_worker_status,
            "fresh_worker_script": "scripts/court_codex_office_worker.py",
            "fresh_worker_host_proof_path": str(fresh_worker_proof_path),
            "fresh_worker_host_proof": fresh_worker_host_proof,
            "fresh_worker_binary_pin_required": True,
            "fresh_worker_same_session": False,
            "fork_turns": "none",
            "claude_code": "inherit_main_thread_model",
            "hermes": "inherit_main_profile_model_design_deferred",
        },
        "degraded_reasons": degraded_reasons,
    }


def _case_plan_view(task: Mapping[str, Any]) -> dict[str, object]:
    from court_plan_artifacts import current_plan, require_reviewed_plan
    from court_case_binding import refresh_case_binding
    if not isinstance(task.get("case_binding"), dict):
        return {"schema": "court.workflow_status.v1", "ok": True, "task_id": task.get("task_id"),
                "state": task.get("state"), "case_status": "LEGACY_UNBOUND", "standard_workflow_ready": False}
    problems: list[str] = []
    try:
        binding = refresh_case_binding(task)
    except ValueError as exc:
        binding = None
        problems.append(str(exc))
    try:
        plan = current_plan(task)
    except ValueError as exc:
        plan = None
        problems.append(str(exc))
    reviewed = False
    if plan is not None:
        try:
            require_reviewed_plan(task)
            reviewed = True
        except ValueError as exc:
            problems.append(str(exc))
    return {"schema": "court.workflow_status.v1", "ok": True, "task_id": task.get("task_id"),
            "state": task.get("state"), "case_status": "BOUND" if binding else "NEEDS_REVIEW", "case_binding": binding,
            "plan_status": "REVIEWED" if reviewed else "DRAFTED" if plan else "BOOTSTRAP_UNPLANNED",
            "plan": {**{k: plan[k] for k in ("schema", "plan_id", "revision", "producer")},
                     "plan_ref": plan_reference(plan)} if plan else None,
            "case_reviews": deepcopy(task.get("case_reviews", {})), "problems": problems,
            "next_operations": ["court plan --help", "court semantic-context-template --task-id " + str(task.get("task_id"))],
            "standard_workflow_ready": reviewed and binding is not None}


def _case_semantic_plan(task: Mapping[str, Any]) -> dict[str, object]:
    from court_plan_artifacts import bootstrap_artifact, current_plan
    plan = current_plan(task)
    if plan:
        return {"status": "DRAFTED", "revision": plan["revision"], "plan_ref": plan_reference(plan), "field": "zhongshu_plan"}
    bootstrap = task.get("case_bootstrap")
    if bootstrap != bootstrap_artifact(task):
        raise ValueError("case_bootstrap_missing_or_stale")
    return {"status": "BOOTSTRAP_UNPLANNED", "revision": 0, "plan_ref": None, "field": "case_bootstrap"}


def _require_case_semantic_context(task: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    if not isinstance(task.get("case_binding"), dict):
        return
    expected = _case_semantic_plan(task)
    if context.get("case_ref") != case_reference(task) or context.get("plan_ref") != expected["plan_ref"]:
        raise ValueError("case_semantic_plan_binding_mismatch")


def _require_case_reviewed(task: Mapping[str, Any]) -> None:
    if isinstance(task.get("case_binding"), dict):
        from court_plan_artifacts import require_reviewed_plan
        from court_case_binding import validate_case_binding
        validate_case_binding(task["case_binding"], task)
        require_reviewed_plan(task)


def workflow_status_payload(task_id: str) -> dict[str, object]:
    task = load_tasks().get(require_text(task_id, "task-id"))
    if not isinstance(task, dict):
        raise ValueError("task not found: " + task_id)
    return _case_plan_view(task)


def case_plan_operation(args: argparse.Namespace) -> dict[str, object]:
    from court_plan_artifacts import submit_plan, record_review
    from court_case_binding import refresh_case_binding
    if args.action == "status":
        return workflow_status_payload(args.task_id)
    if args.action == "show":
        from court_plan_artifacts import current_plan
        task = load_tasks().get(args.task_id)
        if not isinstance(task, dict):
            raise ValueError("task not found: " + args.task_id)
        plan = current_plan(task)
        return {"schema": "court.plan_artifact_projection.v1", "ok": True,
                "task_id": args.task_id, "plan": plan,
                "bootstrap": deepcopy(task.get("case_bootstrap")) if plan is None else None,
                "storage": {"path": str(tasks_path()), "json_pointer": "/" + args.task_id.replace("~", "~0").replace("/", "~1")}}
    if args.action == "template":
        task = load_tasks().get(args.task_id, {})
        if not task:
            raise ValueError("task not found: " + args.task_id)
        plan = task.get('zhongshu_plan') or {}
        producer = {"kind":"host_report", "agent_id":"<actual admitted agent id>", "evidence":"<actual agent_report evidence>"}
        return {"schema": "court.plan_request_template.v1", "task_id": args.task_id,
                "expected_plan_revision": plan.get("revision", 0),
                "document": {"goal": "<goal>", "non_goals": [], "steps": [{"id": "step-1", "role": "gongbu", "action": "<action>"}], "acceptance": ["<acceptance>"], "write_set": []},
                "producer": producer,
                "review": {"role": "menxia", "decision": "approved", "plan_ref": plan_reference(plan) if plan else None, "producer":dict(producer)},
                "notes": ["Template is not a plan or an office reply.", "Shangshu uses decision dispatchable|blocked; Menxia uses approved|rejected.", "serial_inline is allowed only for explicitly selected serial execution.", "host_report may include event_id to select one actual report when an evidence pointer was reused."]}
    request = _json_object_from_args(args, "request", "request_file", "plan request")
    expected = {"document", "producer", "expected_plan_revision"} if args.action == "submit" else {"role", "decision", "plan_ref", "producer"}
    if request.get('schema') == 'court.plan_request_template.v1':
        if set(request) != {'document','producer','expected_plan_revision','schema','task_id','review','notes'}:
            raise ValueError('case_plan_template_fields_invalid')
        if request['task_id'] != args.task_id:
            raise ValueError('case_plan_template_task_mismatch')
        if args.action == 'submit':
            request = {key: request[key] for key in expected}
        else:
            review = request.get('review')
            if not isinstance(review, dict):
                raise ValueError('case_plan_review_template_fields_invalid')
            request = {**review, 'producer':review.get('producer', request['producer'])}
    if set(request) != expected:
        raise ValueError("case_plan_request_fields_invalid: expected " + ','.join(sorted(expected))
                         + "; submit/review also accept the complete plan template payload")
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not isinstance(task, dict) or not isinstance(task.get("case_binding"), dict):
            raise ValueError("case_plan_standard_task_required")
        require_semantic_mutation_binding(task)
        if task.get("case_execution", {}).get("authority") not in {"autonomous", "super"}:
            raise ValueError("case_plan_write_authority_required")
        history = events_for_task(args.task_id)
        if args.action == "submit":
            revision = request["expected_plan_revision"]
            if isinstance(revision, bool) or not isinstance(revision, int) or revision != task.get("zhongshu_plan", {}).get("revision", 0):
                raise ValueError("case_plan_revision_conflict")
        updated = (submit_plan(task, request["document"], request["producer"], history)
                   if args.action == "submit" else record_review(task, request["role"], request["decision"], request["plan_ref"], request["producer"], history))
        updated["case_binding"] = refresh_case_binding(updated)
        view = _case_plan_view(updated)
        if updated == task:
            return {"ok": True, "status": "REPLAYED", **view}
        actor = "zhongshu" if args.action == "submit" else request["role"]
        evidence = request["producer"]["evidence"]
        event = make_event(updated, "case_plan_" + args.action, task["state"], task["state"], actor, evidence, "bounded plan artifact")
        event["plan_ref"] = plan_reference(updated["zhongshu_plan"])
        event["case_ref"] = case_reference(updated)
        updated["last_evidence"] = evidence
        updated["updated_at"] = now_text()
        tasks[args.task_id] = updated
        _commit_task_event(tasks, event)
        return {"ok": True, "status": "COMMITTED", "event": event, **view}


def public_intake_contract_payload() -> dict[str, object]:
    return {
        "schema": "court.runtime.public_contract.v1",
        "conversation_gate_schema": conversation_gate_json_schema(),
        "invariant_capsule_schema": invariant_capsule_json_schema(),
        "office_result_envelope_schema": office_result_envelope_json_schema(),
        "runtime_assessment_binding_contract": {
            "schema": RUNTIME_ASSESSMENT_BINDING_SCHEMA,
            "required_fields": sorted(RUNTIME_ASSESSMENT_BINDING_FIELDS),
            "gates": sorted(OUTCOME_ASSESSMENT_GATES),
            "completion_source": {
                "schema": COMPLETION_SOURCE_SCHEMA,
                "required_fields": ["schema", "task_id", "charter_revision", "case_ref", "sources"],
                "source_fields": ["kind", "role", "pointer"],
                "optional_source_fields": ["event_id"],
                "kinds": sorted(COMPLETION_SOURCE_KINDS),
                "maximum_sources": COMPLETION_SOURCE_MAX_ITEMS,
            },
            "residual_gaps": "Unique nonempty one-line strings; required for PASSED_WITH_CONCERNS.",
            "references": "Use stable document/event references, not caller-computed hashes.",
        },
        "minimal_formal_task": minimal_formal_task_example(),
        "workflow": [
            {"step": 1, "command": "intake-template --charter <exact UTF-8 charter>"},
            {"step": 2, "command": "create --task-id <task-id> --session-id <host-session-id> --authority <selected-authority> --behavior <selected-behavior> --title <title> --work-kind <kind> --charter <same charter> --intake-file <gate.json> --invariant-capsule-file <capsule.json>"},
            {"step": 3, "command": "transition --task-id <task-id> --to-state Taizi --actor taizi --evidence <evidence>"},
            {"step": 4, "command": "transition --task-id <task-id> --to-state ThreeDepartments --actor taizi --evidence <evidence>"},
            {"step": 5, "command": "semantic-context-template --task-id <task-id>"},
            {"step": 6, "command": "semantic checkpoint --task-id <task-id> --context-file <context.json> --trigger checkpoint --actor taizi --evidence <evidence>"},
            {"step": 7, "command": "semantic verify --task-id <task-id> --context-file <same context.json> --trigger verify --actor taizi --evidence <evidence>"},
            {"step": 8, "command": "admission-template --task-id <task-id> ..."},
            {"step": 9, "command": "agent-admit <argv from admission-template>"},
        ],
    }


def public_intake_template_payload(charter: str) -> dict[str, object]:
    charter = require_exact_text(charter, "charter")
    return {
        "schema": "court.runtime.intake_template.v1",
        "charter": charter,
        "conversation_gate": minimal_formal_task_example(),
        "invariant_capsule": invariant_capsule_template(charter),
        "write_set_contract": {
            "base": "active worktree",
            "paths": "relative paths only; absolute paths and parent traversal are rejected before standard case allocation",
            "example": [".codex/tmp/<task-id>"],
            "read_only": ["NO_WRITES_DECLARED"],
        },
    }


def _read_public_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}_invalid_json:{exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}_must_be_object")
    return value


def public_capsule_validation_payload(charter: str, value: object) -> dict[str, object]:
    try:
        normalized = validate_invariant_capsule(require_exact_text(charter, "charter"), value)
    except ValueError as exc:
        return {
            "schema": "court.semantic.invariant_capsule.validation.v1",
            "ok": False,
            "errors": [{"field": "invariant_capsule", "kind": "contract", "code": str(exc)}],
        }
    return {
        "schema": "court.semantic.invariant_capsule.validation.v1",
        "ok": True,
        "errors": [],
        "value": normalized,
    }


def public_intake_validation_payload(
    charter: str,
    intake_value: object,
    capsule_value: object | None = None,
) -> dict[str, object]:
    gate = validate_conversation_gate_diagnostics(intake_value)
    capsule = (
        public_capsule_validation_payload(charter, capsule_value)
        if capsule_value is not None
        else public_capsule_validation_payload(charter, invariant_capsule_template(charter))
    )
    errors: list[dict[str, object]] = []
    for scope, result in (("conversation_gate", gate), ("invariant_capsule", capsule)):
        for error in result.get("errors", []):
            if isinstance(error, dict):
                errors.append({"scope": scope, **error})
    return {
        "schema": "court.runtime.intake_validation.v1",
        "ok": not errors,
        "errors": errors,
        "conversation_gate": gate,
        "invariant_capsule": capsule,
    }


def semantic_context_json_schema() -> dict[str, object]:
    properties = {
        "authority_revision": {"type": "integer", "minimum": 1},
        "case_ref": {"type": "object"},
        "plan_ref": {"type": ["object", "null"]},
        "plan_cursor": {"type": "string", "minLength": 1},
        "recovery_checkpoint_id": {"type": "string", "minLength": 1},
        "shiguan_revision": {"type": "integer", "minimum": 0},
    }
    return {
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'court.semantic.context.v1',
        'type': 'object',
        'required': sorted(properties),
        'properties': properties,
        'additionalProperties': False,
    }


def public_semantic_context_template_payload(task_id: str) -> dict[str, object]:
    task_id = require_text(task_id, "task-id")
    task = load_tasks().get(task_id)
    if not isinstance(task, dict):
        raise ValueError(f"task not found: {task_id}")
    reference = case_reference(task)
    history = events_for_task(task_id)
    last_event = next((event for event in reversed(history) if event.get("event_id")), None)
    checkpoint = str(last_event["event_id"]) if last_event else f"court-runtime:tasks/{task_id}"
    plan = task.get("zhongshu_plan")
    plan_ref = plan_reference(plan) if isinstance(plan, Mapping) else None
    result = {
        "schema": "court.semantic.context_template.v1",
        "context": {
            "authority_revision": reference["charter_revision"],
            "case_ref": reference,
            "plan_ref": plan_ref,
            "plan_cursor": f"{task.get('state')}@revision-{reference['charter_revision']}",
            "recovery_checkpoint_id": checkpoint,
            "shiguan_revision": len(history),
        },
    }
    if isinstance(task.get("case_binding"), dict):
        status = _case_semantic_plan(task)
        result["plan_status"] = status["status"]
        result["case_binding"] = deepcopy(task["case_binding"])
    return result


def public_semantic_context_validation_payload(value: object) -> dict[str, object]:
    try:
        normalized = normalize_semantic_context(_semantic_context_payload(value))
    except ValueError as exc:
        return {
            "schema": "court.semantic.context_validation.v1",
            "ok": False,
            "errors": [{"field": "semantic_context", "kind": "contract", "code": str(exc)}],
        }
    return {
        "schema": "court.semantic.context_validation.v1",
        "ok": True,
        "errors": [],
        "value": normalized,
    }


def public_dispatch_context_packet(task: Mapping[str, object], wave_id: str) -> dict[str, object]:
    receipt = task.get("semantic_receipt")
    if not isinstance(receipt, Mapping):
        raise ValueError("semantic_receipt_missing")
    reference = case_reference(task)
    current_plan = task.get("zhongshu_plan")
    plan_ref = plan_reference(current_plan) if isinstance(current_plan, Mapping) else None
    from urllib.parse import quote
    escaped = quote(str(task["task_id"]), safe="")
    plan_pointer = {"path": f"court-runtime:tasks/{escaped}/zhongshu_plan", "plan_ref": plan_ref} if plan_ref else {"path": f"court-runtime:tasks/{escaped}/case_bootstrap", "case_ref": reference}
    return {
        "schema": "court.semantic.dispatch_context_packet.v1",
        "task_id": task.get("task_id"),
        "sub_id": require_text(wave_id, "wave-id"),
        "semantic_epoch": receipt.get("semantic_epoch"),
        "case_ref": reference,
        "plan_ref": plan_ref,
        "semantic_receipt_id": receipt.get("receipt_id"),
        "plan_cursor": receipt.get("plan_cursor"),
        "fork_context": "none",
        "context_mode": "bounded",
        "pointers": [
            {"path": f"court-runtime:tasks/{escaped}/charter", "case_ref": reference},
            plan_pointer,
        ],
        "summary": {
            "text": "Official court_code=" + reference["court_code"] + "; resolve existing task and plan records.",
            "semantic_receipt_id": receipt.get("receipt_id"),
        },
    }


def public_context_budget_pool(
    task: Mapping[str, object],
    wave_id: str,
    *,
    execution_budgets: Mapping[str, object] | None = None,
) -> dict[str, object]:
    receipt = task.get("semantic_receipt")
    if not isinstance(receipt, Mapping):
        raise ValueError("semantic_receipt_missing")
    limits = dict(PUBLIC_CONTEXT_HARD_LIMITS)
    budgets = _execution_budgets(execution_budgets or {})
    for field, cap in (("deadline_seconds", "time_seconds_max"), ("tool_call_budget", "tool_calls_max")):
        if budgets[field] is not None:
            limits[cap] = budgets[field]
    return normalize_budget_pool(
        total_share=100.0,
        root_id="taizi",
        reserve_share=10.0,
        hard_limits=limits,
        task_id=require_text(str(task.get("task_id") or ""), "task-id"),
        phase="P00-PUBLIC-ADMISSION",
        wave_id=require_text(wave_id, "wave-id"),
        approved_by="taizi",
        approved_at=str(receipt.get("created_at") or now_text()),
        expected_output="bounded structured dispatch receipt",
        return_conditions=("COMPLETED", "FAILED_CLOSED", "CANCELLED"),
    )


PUBLIC_ADMISSION_REQUEST_FIELDS = frozenset(
    {
        "schema", "task_id", "case_ref", "expected_semantic_epoch", "expected_checkpoint_id", "wave_id",
        "execution_topology", "protocol_mode", "active_session_protocol",
        "needs_parallel_tree", "requested_fork_turns", "context_tokens",
        "message_chars", "message_required_chars", "message_optional_chars",
        "requested_agents", "requested_roles", "host_active_agents", "host_capacity",
        "host_retained_agents", "host_reclamation_status", "next_depth", "max_depth",
        "max_threads", "user_agent_budget", "provider_launch_budget", "budget_lease",
        "requested_bindings", "integration_domain", "authority", "calling_office",
        "direct_superior", "assignment", "task_focus", "complexity", "risk",
        "ambiguity", "transport", "actor", "evidence", "dispatch_context_packet",
        "context_budget_pool", "context_result_mode", "context_tool_output_mode",
        "context_override_source", "system_memory_percent",
    }
)


def public_admission_request_json_schema() -> dict[str, object]:
    object_fields = {
        "budget_lease", "dispatch_context_packet", "context_budget_pool", "case_ref"
    }
    array_fields = {"requested_roles", "requested_bindings"}
    boolean_fields = {"needs_parallel_tree"}
    integer_fields = {
        "expected_semantic_epoch", "context_tokens", "message_chars",
        "message_required_chars", "message_optional_chars", "requested_agents",
        "host_active_agents", "host_capacity", "host_retained_agents", "next_depth",
        "max_depth", "max_threads", "user_agent_budget", "provider_launch_budget",
    }
    properties: dict[str, object] = {}
    for field in PUBLIC_ADMISSION_REQUEST_FIELDS:
        if field in object_fields:
            properties[field] = {"type": "object"}
        elif field in array_fields:
            properties[field] = {"type": "array"}
        elif field in boolean_fields:
            properties[field] = {"type": "boolean"}
        elif field in integer_fields:
            properties[field] = {"type": "integer"}
        elif field == "system_memory_percent":
            properties[field] = {"type": "number"}
        elif field == "context_override_source":
            properties[field] = {"type": ["string", "null"]}
        else:
            properties[field] = {"type": "string"}
    for field, default in AGENT_EXECUTION_BUDGET_DEFAULTS.items():
        properties[field] = {"type": ["integer", "null"], "minimum": 1, "default": default}
    properties["schema"] = {"type": "string", "const": "court.agent.admission_request.v1"}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "court.agent.admission_request.v1",
        "type": "object",
        "required": sorted(PUBLIC_ADMISSION_REQUEST_FIELDS),
        "properties": properties,
        "additionalProperties": False,
    }


def public_admission_request_argv(value: object) -> list[str]:
    if not isinstance(value, dict):
        raise ValueError("admission_request_must_be_object")
    missing = sorted(PUBLIC_ADMISSION_REQUEST_FIELDS - set(value))
    unknown = sorted(set(value) - PUBLIC_ADMISSION_REQUEST_FIELDS - AGENT_EXECUTION_BUDGET_DEFAULTS.keys())
    if missing:
        raise ValueError("admission_request_fields_missing:" + ",".join(missing))
    if unknown:
        raise ValueError("admission_request_fields_unknown:" + ",".join(unknown))
    if value.get("schema") != "court.agent.admission_request.v1":
        raise ValueError("invalid_admission_request_schema")
    roles = value.get("requested_roles")
    if (
        not isinstance(roles, list)
        or not roles
        or any(not isinstance(role, str) or not role.strip() for role in roles)
    ):
        raise ValueError("admission_request_roles_invalid")
    if type(value.get("needs_parallel_tree")) is not bool:
        raise ValueError("admission_request_parallel_flag_invalid")
    scalar_fields = (
        "task_id", "expected_semantic_epoch", "expected_checkpoint_id", "wave_id",
        "execution_topology", "protocol_mode", "active_session_protocol",
        "requested_fork_turns", "context_tokens", "message_chars",
        "message_required_chars", "message_optional_chars", "requested_agents",
        "host_active_agents", "host_capacity", "host_retained_agents",
        "host_reclamation_status", "next_depth", "max_depth", "max_threads",
        "user_agent_budget", "provider_launch_budget", "integration_domain",
        "authority", "calling_office", "direct_superior", "assignment", "task_focus",
        "complexity", "risk", "ambiguity", "transport", "actor", "evidence",
        "context_result_mode", "context_tool_output_mode", "system_memory_percent",
    )
    argv = ["agent-admit", "--case-ref", json.dumps(value["case_ref"], ensure_ascii=False)]
    for field in scalar_fields:
        argv.extend((f"--{field.replace('_', '-')}", str(value[field])))
    for field, budget in _execution_budgets(value).items():
        if field in value and budget is not None:
            argv.extend((f"--{field.replace('_', '-')}", str(budget)))
    argv.extend(("--requested-roles", ",".join(roles)))
    for field in (
        "budget_lease", "requested_bindings", "dispatch_context_packet",
        "context_budget_pool",
    ):
        argv.extend(
            (f"--{field.replace('_', '-')}-json", json.dumps(value[field], ensure_ascii=False))
        )
    argv.extend(("--format", "json"))
    if value["needs_parallel_tree"]:
        argv.append("--needs-parallel-tree")
    override = value.get("context_override_source")
    if override is not None:
        argv.extend(("--context-override-source", str(override)))
    return argv


def public_admission_validation_payload(value: object) -> dict[str, object]:
    try:
        argv = public_admission_request_argv(value)
        args = build_parser().parse_args(argv)
        task = load_tasks().get(str(args.task_id))
        if not isinstance(task, dict):
            raise ValueError(f"task not found: {args.task_id}")
        _semantic_admission_expectations(task, args)
        if _context_contract_required(args):
            _validate_context_economy_request(task, args, wave_id=str(args.wave_id))
        _validate_canonical_admission_preloads(args)
        decision = evaluate_agent_admission(task, args)
        if decision.get("allowed") is not True:
            raise ValueError(f"agent_admission_denied:{decision.get('decision')}")
        _validate_admission_capsule_write_scope(task, decision.get("selected_bindings"))
    except (CourtCliArgumentError, ValueError) as exc:
        return {
            "schema": "court.agent.admission_request.validation.v1",
            "ok": False,
            "errors": [{"field": "admission_request", "kind": "contract", "code": str(exc)}],
        }
    return {
        "schema": "court.agent.admission_request.validation.v1",
        "ok": True,
        "errors": [],
        "value": value,
        "argv": argv,
    }


def public_admission_template_payload(args: argparse.Namespace) -> dict[str, object]:
    task = load_tasks().get(str(args.task_id))
    if not isinstance(task, dict):
        raise ValueError(f"task not found: {args.task_id}")
    role = require_text(args.role, "role").lower()
    calling_office = require_text(args.calling_office, "calling-office").lower()
    manifest = build_preload_manifest(role)
    if manifest.direct_superior != calling_office:
        raise ValueError("admission_template_hierarchy_mismatch")
    caller_manifest = build_preload_manifest(calling_office)
    normalized_write_set = canonical_repo_relative_paths([args.write_path])
    if normalized_write_set is None or len(normalized_write_set) != 1:
        raise ValueError("admission_template_write_path_invalid")
    write_path = normalized_write_set[0]
    instance_id = f"{role}#0001"
    shard_id = f"{role}-shard-0001"
    preload_sources = _semantic_preload_sources(role)
    binding = {
        "role": role,
        "instance_id": instance_id,
        "shard_id": shard_id,
        "direct_superior": calling_office,
        "instance_kind": "office",
        "canonical_authority": True,
        "owner_role": None,
        "write_set": [write_path],
        "access_mode": "read_write",
        "read_scope": [write_path],
        "mutation_allowed": True,
        "integration_authority": False,
        "preload_sources": preload_sources,
    }
    _validate_admission_capsule_write_scope(task, [binding])
    next_depth = int(args.next_depth)
    if next_depth < 1:
        raise ValueError("admission_template_next_depth_invalid")
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    budget_id = f"budget:{args.task_id}:P00-PUBLIC-ADMISSION:{args.wave_id}"
    direct_superior = caller_manifest.direct_superior
    lease = {
        "schema": "court.agent.admission_lease.v2",
        "budget_id": budget_id,
        "status": "ACTIVE",
        "lease_id": f"{budget_id}:lease",
        "parent_budget_id": f"{budget_id}:{direct_superior}",
        "parent_id": direct_superior,
        "approved_by": direct_superior,
        "grantee_role": calling_office,
        "lease_depth": next_depth - 1,
        "approved_next_depth": next_depth,
        "expires_at_utc": expires_at,
        "parent_write_scope": [write_path.split("/", 1)[0]],
        "approved_count": 1,
        "task_id": str(args.task_id),
        "calling_office": calling_office,
        "direct_superior": direct_superior,
        "integration_domain": require_text(args.integration_domain, "integration-domain"),
        "authority": "super",
        "approved_roles": [role],
        "approved_instance_ids": [instance_id],
        "approved_shards": [shard_id],
        "approved_write_sets": {instance_id: [write_path]},
        "approved_access_contracts": {
            instance_id: {
                "access_mode": "read_write", "read_scope": [write_path],
                "mutation_allowed": True, "integration_authority": False,
            }
        },
        "approved_instance_shapes": {
            instance_id: {
                "instance_kind": "office", "canonical_authority": True,
                "owner_role": None, "direct_superior": calling_office,
            }
        },
        "approved_bindings": {},
        "approved_preload_sources": {instance_id: preload_sources},
    }
    receipt = task.get("semantic_receipt")
    if not isinstance(receipt, Mapping):
        raise ValueError("semantic_receipt_missing")
    request = {
        "schema": "court.agent.admission_request.v1",
        "task_id": str(args.task_id),
        "expected_semantic_epoch": task.get("semantic_epoch"),
        "case_ref": case_reference(task),
        "expected_checkpoint_id": receipt.get("checkpoint_id"),
        "wave_id": require_text(args.wave_id, "wave-id"),
        "execution_topology": "parallel",
        "protocol_mode": "v2",
        "active_session_protocol": "v2",
        "needs_parallel_tree": True,
        "requested_fork_turns": "none",
        "context_tokens": int(args.context_tokens),
        **_execution_budgets(vars(args)),
        "message_chars": int(args.message_chars),
        "message_required_chars": int(args.message_chars),
        "message_optional_chars": 0,
        "requested_agents": 1,
        "requested_roles": [role],
        "host_active_agents": int(args.host_active_agents),
        "host_capacity": int(args.host_capacity),
        "host_retained_agents": int(args.host_retained_agents),
        "host_reclamation_status": str(args.host_reclamation_status),
        "next_depth": next_depth,
        "max_depth": MAX_AGENT_TREE_DEPTH,
        "max_threads": MAX_AGENT_TREE_THREADS,
        "user_agent_budget": int(args.user_agent_budget),
        "provider_launch_budget": int(args.provider_launch_budget),
        "budget_lease": lease,
        "requested_bindings": [binding],
        "integration_domain": str(args.integration_domain),
        "authority": "super",
        "calling_office": calling_office,
        "direct_superior": direct_superior,
        "assignment": require_text(args.assignment, "assignment"),
        "task_focus": require_text(args.task_focus, "task-focus"),
        "complexity": str(args.complexity),
        "risk": str(args.risk),
        "ambiguity": str(args.ambiguity),
        "transport": str(args.transport),
        "actor": calling_office,
        "evidence": require_text(args.evidence, "evidence"),
        "dispatch_context_packet": public_dispatch_context_packet(task, str(args.wave_id)),
        "context_budget_pool": public_context_budget_pool(
            task, str(args.wave_id), execution_budgets=_execution_budgets(vars(args))),
        "context_result_mode": "bounded_structured_receipt",
        "context_tool_output_mode": "pointer",
        "context_override_source": None,
        "system_memory_percent": float(args.system_memory_percent),
    }
    validated = public_admission_validation_payload(request)
    if validated.get("ok") is not True:
        raise ValueError(str(validated.get("errors")))
    return {
        "schema": "court.agent.admission_request.template.v1",
        "request": request,
        "argv": validated["argv"],
    }


def output(value: Any, fmt: str) -> None:
    if fmt == "json":
        if isinstance(value, TransitionResult):
            value = {"task": value.task, "event": value.event}
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if isinstance(value, TransitionResult):
        history = events_for_task(value.task.get("task_id"))
        print(task_summary(value.task, history))
        print(f"event: {value.event['action']} {value.event['from_state']} -> {value.event['to_state']}")
        return
    if isinstance(value, list):
        print(render_cli(value, read_events(limit=None)))
        return
    print(str(value))


def semantic_cli_payload(command: str, value: object) -> dict[str, object]:
    if isinstance(value, TransitionResult):
        result: object = {"task": value.task, "event": value.event}
    else:
        result = value
    return {
        "schema": "court.semantic.cli.v1",
        "ok": True,
        "command": command,
        "result": result,
    }


def operation_cli_payload(command: str, value: object) -> dict[str, object]:
    return {
        "schema": "court.operation.cli.v1",
        "ok": True,
        "command": command,
        "result": value,
    }


def office_cli_payload(command: str, value: object) -> dict[str, object]:
    return {
        "schema": "court.office.cli.v1",
        "ok": True,
        "command": command,
        "result": value,
    }


OFFICE_CLI_COMMANDS = (
    "admit",
    "native-request",
    "native-capture",
    "start",
    "followup",
    "preload-ack",
    "report",
    "finish",
    "close",
)


class CourtCliArgumentError(ValueError):
    pass


class CourtArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CourtCliArgumentError(message)


def _raw_top_level_command(argv: list[str]) -> tuple[str, int]:
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == "--format":
            index += 2
            continue
        if value.startswith("--format="):
            index += 1
            continue
        if not value.startswith("-"):
            return value, index
        index += 1
    return "", -1


def _raw_office_command(argv: list[str]) -> str:
    command, index = _raw_top_level_command(argv)
    if command != "office" or index < 0 or index + 1 >= len(argv):
        return ""
    candidate = argv[index + 1]
    return "" if candidate.startswith("-") else candidate


def _office_parse_error_code(argv: list[str]) -> str:
    command = _raw_office_command(argv)
    if command and command not in OFFICE_CLI_COMMANDS:
        return "office_cli_unknown_subcommand"
    if "--request-json" in argv:
        index = argv.index("--request-json")
        if index + 1 >= len(argv):
            return "office_cli_missing_arguments"
        try:
            value = json.loads(argv[index + 1])
        except json.JSONDecodeError:
            return "office_cli_invalid_json"
        if not isinstance(value, dict):
            return "office_cli_invalid_json"
    if not command or ("--request-json" not in argv and "--request-file" not in argv):
        return "office_cli_missing_arguments"
    return "office_cli_invalid_arguments"


def _office_cli_error_payload(
    command: str,
    error: object,
    *,
    error_code: str,
) -> dict[str, object]:
    return {
        "schema": "court.office.cli.v1",
        "ok": False,
        "command": command,
        "fail_closed": True,
        "error_code": error_code,
        "error": str(error),
    }


def office_request_namespace(args: argparse.Namespace) -> argparse.Namespace:
    request = _json_object_from_args(
        args,
        "request_json",
        "request_file",
        "office lifecycle request",
    )
    for field in tuple(request):
        if field.endswith("_file") and request[field]:
            request[field] = Path(str(request[field]))
    return argparse.Namespace(**request)


def build_parser() -> argparse.ArgumentParser:
    parser = CourtArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    sub = parser.add_subparsers(dest="command", required=True)

    case_plan = sub.add_parser("plan", help="Record a real Zhongshu plan and independent Menxia/Shangshu reviews")
    case_plan.add_argument("action", choices=("template", "submit", "review", "status", "show"))
    case_plan.add_argument("--task-id", required=True)
    case_plan.add_argument("--request-file", type=Path)
    case_plan.add_argument("--format", choices=("text", "json"), default="json")
    workflow_status = sub.add_parser("workflow-status", help="Read the shared task/code/plan/review binding")
    workflow_status.add_argument("--task-id", required=True)
    workflow_status.add_argument("--format", choices=("text", "json"), default="json")

    def accept_format_after_command(command: argparse.ArgumentParser) -> None:
        command.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)

    def add_expected_semantic_binding(command: argparse.ArgumentParser) -> None:
        command.add_argument("--expected-semantic-epoch", type=int)
        command.add_argument("--case-ref")
        command.add_argument("--expected-checkpoint-id")

    def add_agent_semantic_binding(command: argparse.ArgumentParser) -> None:
        command.add_argument("--semantic-epoch", type=int)
        command.add_argument("--case-ref", type=json_object_argument)
        command.add_argument("--checkpoint-id")
        command.add_argument("--dispatch-uid")
        command.add_argument("--attempt", type=int)

    def json_object_argument(value: str) -> dict[str, object]:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise argparse.ArgumentTypeError("JSON object is invalid") from exc
        if not isinstance(parsed, dict):
            raise argparse.ArgumentTypeError("JSON value must be an object")
        return parsed

    def json_array_argument(value: str) -> list[object]:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise argparse.ArgumentTypeError("JSON array is invalid") from exc
        if not isinstance(parsed, list):
            raise argparse.ArgumentTypeError("JSON value must be an array")
        return parsed

    def add_context_economy_request(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--dispatch-context-packet-json",
            dest="dispatch_context_packet",
            type=json_object_argument,
        )
        command.add_argument(
            "--context-budget-pool-json",
            dest="context_budget_pool",
            type=json_object_argument,
        )
        command.add_argument("--context-result-mode")
        command.add_argument("--context-tool-output-mode")
        command.add_argument("--context-override-source")

    intake_schema = sub.add_parser(
        "intake-schema",
        help="print the machine-readable conversation and invariant-capsule schemas",
    )
    intake_schema.set_defaults(format="json")
    accept_format_after_command(intake_schema)

    intake_template = sub.add_parser(
        "intake-template",
        help="generate a minimal FORMAL_TASK gate and invariant capsule from an exact charter",
    )
    intake_template.set_defaults(format="json")
    accept_format_after_command(intake_template)
    intake_template.add_argument("--charter", required=True, help="required nonempty exact UTF-8 charter")

    intake_validate = sub.add_parser(
        "intake-validate",
        help="validate intake JSON and optional invariant capsule without runtime mutation",
    )
    intake_validate.set_defaults(format="json")
    accept_format_after_command(intake_validate)
    intake_validate.add_argument("--charter", required=True, help="required nonempty exact UTF-8 charter")
    intake_validate.add_argument("--intake-file", type=Path, required=True, help="court.conversation_gate.v1 JSON object")
    intake_validate.add_argument("--invariant-capsule-file", type=Path)

    capsule_template = sub.add_parser(
        "capsule-template",
        help="generate a 13-field court.semantic.invariant_capsule.v1 JSON object",
    )
    capsule_template.set_defaults(format="json")
    accept_format_after_command(capsule_template)
    capsule_template.add_argument("--charter", required=True, help="required nonempty exact UTF-8 charter")

    capsule_validate = sub.add_parser(
        "capsule-validate",
        help="validate capsule hashes, UTF-8 anchor, fields, and 2048-byte canonical limit",
    )
    capsule_validate.set_defaults(format="json")
    accept_format_after_command(capsule_validate)
    capsule_validate.add_argument("--charter", required=True, help="required nonempty exact UTF-8 charter")
    capsule_validate.add_argument("--invariant-capsule-file", type=Path, required=True)

    semantic_context_schema = sub.add_parser(
        "semantic-context-schema",
        help="print the machine-readable semantic checkpoint context schema",
    )
    semantic_context_schema.set_defaults(format="json")
    accept_format_after_command(semantic_context_schema)

    semantic_context_template = sub.add_parser(
        "semantic-context-template",
        help="generate a complete semantic checkpoint context",
    )
    semantic_context_template.set_defaults(format="json")
    accept_format_after_command(semantic_context_template)
    semantic_context_template.add_argument("--task-id", required=True)

    semantic_context_validate = sub.add_parser(
        "semantic-context-validate",
        help="validate semantic checkpoint context without runtime mutation",
    )
    semantic_context_validate.set_defaults(format="json")
    accept_format_after_command(semantic_context_validate)
    semantic_context_validate.add_argument("--context-file", type=Path, required=True)

    admission_schema = sub.add_parser(
        "admission-schema",
        help="print the complete machine-readable agent admission request schema",
    )
    admission_schema.set_defaults(format="json")
    accept_format_after_command(admission_schema)

    admission_template = sub.add_parser(
        "admission-template",
        help="generate a complete executable single-office agent admission request",
    )
    admission_template.set_defaults(format="json")
    accept_format_after_command(admission_template)
    for name in (
        "task-id", "wave-id", "integration-domain", "write-path", "assignment",
        "task-focus", "evidence",
    ):
        admission_template.add_argument(f"--{name}", required=True)
    for name in ("role", "calling-office"):
        admission_template.add_argument(f"--{name}", required=True, choices=sorted(OFFICES))
    for name in (
        "host-active-agents", "host-capacity", "host-retained-agents", "next-depth",
        "user-agent-budget", "provider-launch-budget",
    ):
        admission_template.add_argument(f"--{name}", type=int, required=True)
    admission_template.add_argument(
        "--host-reclamation-status",
        required=True,
        choices=["verified", "not-reclaimed", "unknown"],
    )
    admission_template.add_argument("--context-tokens", type=int, default=1000)
    admission_template.add_argument("--message-chars", type=int, default=256)
    admission_template.add_argument("--system-memory-percent", type=float, default=0.0)
    for field, default in AGENT_EXECUTION_BUDGET_DEFAULTS.items():
        admission_template.add_argument(f"--{field.replace('_', '-')}", type=int, default=default)
    for name in ("complexity", "risk", "ambiguity"):
        admission_template.add_argument(
            f"--{name}", required=True, choices=sorted(EVALUATION_LEVELS)
        )
    admission_template.add_argument("--transport", required=True, choices=sorted(TRANSPORTS))

    admission_validate = sub.add_parser(
        "admission-validate",
        help="validate a complete admission request without ledger mutation",
    )
    admission_validate.set_defaults(format="json")
    accept_format_after_command(admission_validate)
    admission_validate.add_argument("--request-file", type=Path, required=True)

    create = sub.add_parser(
        "create",
        help="create a court task in Pending from documented JSON intake",
        description=(
            "Create from court.conversation_gate.v1 JSON with a minimal FORMAL_TASK example from "
            "intake-template. New formal work includes court.request_understanding.v1 with goal, "
            "usage scenario, key requirements, acceptance criteria, and a minimum score of 95. "
            "--charter is a required nonempty exact UTF-8 charter. An omitted "
            "capsule is safely generated; a custom court.semantic.invariant_capsule.v1 preserves "
            "the complete body lists, exact decree anchor, write scope and 2048-byte limit. "
            "The issued court_code and charter_revision bind its case reference. Use intake-schema, "
            "intake-validate, capsule-template, and capsule-validate for machine-readable contracts."
        ),
    )
    accept_format_after_command(create)
    create.add_argument("--title", required=True)
    create.add_argument("--charter", required=True, help="required nonempty exact UTF-8 charter")
    create.add_argument("--task-id", default="")
    create.add_argument("--legacy-compatibility", action="store_true", help="Explicitly create an unbound legacy record; never a standard workflow acceptance")
    create.add_argument(
        "--session-id",
        default="",
        help="opt into a standard session-backed case; requires --authority and --behavior",
    )
    create.add_argument(
        "--authority",
        choices=["approval", "autonomous", "super"],
        default="",
        help="required with --session-id; persisted in case_execution",
    )
    create.add_argument(
        "--behavior",
        choices=["serial", "parallel"],
        default="",
        help="required with --session-id; persisted in case_execution",
    )
    create.add_argument("--owner", default="taizi", choices=sorted(OFFICES))
    create.add_argument("--report-tier", default="", choices=sorted(REPORT_TIERS) + [""])
    create.add_argument("--evidence", default="")
    create.add_argument("--note", default="")
    create.add_argument("--work-kind", required=True, choices=sorted(WORK_KINDS))
    create.add_argument(
        "--intake-file",
        type=Path,
        required=True,
        help=(
            "court.conversation_gate.v1 JSON with court.request_understanding.v1 score >= 95; "
            "see intake-schema and intake-template"
        ),
    )
    create_capsule = create.add_mutually_exclusive_group()
    create_capsule.add_argument(
        "--invariant-capsule-file",
        type=Path,
        help="optional documented 13-field capsule JSON; omitted means safe generation",
    )
    create_capsule.add_argument(
        "--invariant-capsule-json",
        dest="invariant_capsule",
        type=json_object_argument,
    )

    revise = sub.add_parser("revise-charter", help="apply an audited charter revision")
    accept_format_after_command(revise)
    revise.add_argument("--task-id", required=True)
    revise.add_argument("--expected-revision", type=int, required=True)
    revise.add_argument("--case-ref", required=True)
    revise.add_argument("--new-revision", type=int, required=True)
    new_charter_group = revise.add_mutually_exclusive_group(required=True)
    new_charter_group.add_argument("--new-charter")
    new_charter_group.add_argument("--new-charter-file", type=Path)
    new_capsule_group = revise.add_mutually_exclusive_group(required=True)
    new_capsule_group.add_argument(
        "--new-invariant-capsule-file",
        type=Path,
    )
    new_capsule_group.add_argument(
        "--new-invariant-capsule-json",
        dest="new_invariant_capsule",
        type=json_object_argument,
    )
    revise.add_argument("--correction-file", type=Path, required=True)
    revise.add_argument("--actor", required=True, choices=sorted(OFFICES))
    revise.add_argument("--evidence", required=True)
    revise.add_argument("--note", required=True)

    bind_assessment = sub.add_parser(
        "bind-assessment",
        help="bind a reviewed outcome assessment to the current charter revision",
    )
    accept_format_after_command(bind_assessment)
    bind_assessment.add_argument("--task-id", required=True)
    bind_assessment.add_argument("--expected-revision", type=int, required=True)
    bind_assessment.add_argument("--case-ref", required=True)
    bind_assessment.add_argument("--assessment-file", type=Path, required=True)
    bind_assessment.add_argument("--actor", required=True, choices=sorted(OFFICES))
    bind_assessment.add_argument("--evidence", required=True)
    bind_assessment.add_argument("--note", required=True)

    complete = sub.add_parser(
        "complete",
        help="consume a verified Shiguan receipt and complete under one runtime lock",
    )
    accept_format_after_command(complete)
    complete.add_argument("--task-id", required=True)
    complete.add_argument("--expected-revision", type=int, required=True)
    complete.add_argument("--case-ref", required=True)
    complete.add_argument("--receipt-file", type=Path, required=True)
    complete.add_argument("--actor", default="taizi", choices=sorted(OFFICES))
    complete.add_argument("--evidence", required=True)
    complete.add_argument("--note", required=True)

    transition = sub.add_parser("transition", help="apply a legal state transition")
    accept_format_after_command(transition)
    transition.add_argument("--task-id", required=True)
    transition.add_argument("--to-state", required=True, choices=sorted(STATES))
    transition.add_argument("--actor", required=True, choices=sorted(OFFICES))
    transition.add_argument("--owner", default="")
    transition.add_argument("--heartbeat", default="")
    transition.add_argument("--evidence", default="")
    transition.add_argument("--note", default="")

    heartbeat = sub.add_parser("heartbeat", help="update task heartbeat")
    accept_format_after_command(heartbeat)
    heartbeat.add_argument("--task-id", required=True)
    heartbeat.add_argument("--heartbeat", required=True)
    heartbeat.add_argument("--actor", required=True, choices=sorted(OFFICES))
    heartbeat.add_argument("--evidence", default="")
    heartbeat.add_argument("--note", default="")

    pause = sub.add_parser("pause", help="auditable pause for active execution work")
    accept_format_after_command(pause)
    pause.add_argument("--task-id", required=True)
    pause.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    pause.add_argument("--reason", required=True)
    pause.add_argument("--affected-scope", required=True)
    pause.add_argument("--evidence-preserved", required=True)
    pause.add_argument("--unsafe-remaining", required=True)
    pause.add_argument("--note", default="")

    resume = sub.add_parser("resume", help="auditable resume from Paused")
    accept_format_after_command(resume)
    resume.add_argument("--task-id", required=True)
    resume.add_argument("--to-state", required=True, choices=sorted(STATES - {"Paused", "Cancelled", "Done"}))
    resume.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    resume.add_argument("--resume-evidence", required=True)
    resume.add_argument("--affected-scope", required=True)
    resume.add_argument("--from-paused-state", default="")
    resume.add_argument("--note", default="")

    cancel = sub.add_parser("cancel", help="auditable cancellation")
    accept_format_after_command(cancel)
    cancel.add_argument("--task-id", required=True)
    cancel.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    cancel.add_argument("--reason", required=True)
    cancel.add_argument("--affected-scope", required=True)
    cancel.add_argument("--evidence-preserved", required=True)
    cancel.add_argument("--unsafe-remaining", required=True)
    cancel.add_argument("--note", default="")

    semantic = sub.add_parser(
        "semantic",
        help="semantic-continuity checkpoint, verification, and recovery commands",
    )
    semantic.set_defaults(format="json")
    semantic_sub = semantic.add_subparsers(dest="semantic_command", required=True)

    semantic_checkpoint = semantic_sub.add_parser(
        "checkpoint",
        help="persist a verified semantic checkpoint receipt",
    )
    semantic_checkpoint.add_argument("--task-id", required=True)
    semantic_checkpoint.add_argument(
        "--context-file",
        dest="semantic_context_file",
        type=Path,
        required=True,
    )
    semantic_checkpoint.add_argument("--trigger", required=True)
    semantic_checkpoint.add_argument("--actor", default="taizi", choices=sorted(OFFICES))
    semantic_checkpoint.add_argument("--evidence", required=True)
    semantic_checkpoint.add_argument("--note", default="")

    semantic_verify = semantic_sub.add_parser(
        "verify",
        help="verify the current sources against a persisted semantic checkpoint",
    )
    semantic_verify.add_argument("--task-id", required=True)
    semantic_verify.add_argument(
        "--context-file",
        dest="semantic_context_file",
        type=Path,
        required=True,
    )
    semantic_verify.add_argument("--trigger", required=True)
    semantic_verify.add_argument("--actor", default="taizi", choices=sorted(OFFICES))
    semantic_verify.add_argument("--evidence", required=True)
    semantic_verify.add_argument("--note", default="")

    semantic_correct = semantic_sub.add_parser(
        "correct",
        help="apply a body-bound audited semantic correction",
    )
    semantic_correct.add_argument("--task-id", required=True)
    semantic_correct.add_argument("--expected-revision", type=int, required=True)
    semantic_correct.add_argument("--case-ref", required=True)
    semantic_correct.add_argument("--new-revision", type=int, required=True)
    semantic_correct_body = semantic_correct.add_mutually_exclusive_group(required=True)
    semantic_correct_body.add_argument("--new-charter")
    semantic_correct_body.add_argument("--new-charter-file", type=Path)
    semantic_correct_capsule = semantic_correct.add_mutually_exclusive_group(required=True)
    semantic_correct_capsule.add_argument(
        "--new-invariant-capsule-file",
        type=Path,
    )
    semantic_correct_capsule.add_argument(
        "--new-invariant-capsule-json",
        dest="new_invariant_capsule",
        type=json_object_argument,
    )
    semantic_correct.add_argument("--correction-file", type=Path, required=True)
    semantic_correct.add_argument("--actor", default="taizi", choices=sorted(OFFICES))
    semantic_correct.add_argument("--evidence", required=True)
    semantic_correct.add_argument("--note", default="")

    semantic_resume = semantic_sub.add_parser(
        "resume",
        help="resume a paused task through ThreeDepartments semantic re-verification",
    )
    semantic_resume.add_argument("--task-id", required=True)
    semantic_resume.add_argument("--continuation-file", type=Path, required=True)
    semantic_resume.add_argument("--expected-semantic-epoch", type=int, required=True)
    semantic_resume.add_argument("--case-ref", type=json_object_argument)
    semantic_resume.add_argument("--expected-checkpoint-id", required=True)
    semantic_resume.add_argument(
        "--context-file",
        dest="semantic_context_file",
        type=Path,
        required=True,
    )
    semantic_resume.add_argument("--actor", default="taizi", choices=sorted(OFFICES))
    semantic_resume.add_argument("--evidence", required=True)
    semantic_resume.add_argument("--note", default="")
    semantic_resume.set_defaults(to_state="ThreeDepartments", trigger="resume")

    semantic_quarantine = semantic_sub.add_parser(
        "quarantine",
        help="explicitly quarantine a current semantic binding before mutation",
    )
    semantic_quarantine.add_argument("--task-id", required=True)
    semantic_quarantine.add_argument("--expected-semantic-epoch", type=int, required=True)
    semantic_quarantine.add_argument("--case-ref", type=json_object_argument)
    semantic_quarantine.add_argument("--expected-checkpoint-id", required=True)
    semantic_quarantine.add_argument("--reason-code", action="append", required=True)
    semantic_quarantine.add_argument("--trigger", required=True)
    semantic_quarantine.add_argument("--actor", default="menxia", choices=sorted(OFFICES))
    semantic_quarantine.add_argument("--evidence", required=True)
    semantic_quarantine.add_argument("--note", default="")

    semantic_reconcile = semantic_sub.add_parser(
        "reconcile",
        help="confirm restored sources and route a quarantine back through re-verification",
    )
    semantic_reconcile.add_argument("--task-id", required=True)
    semantic_reconcile.add_argument("--expected-semantic-epoch", type=int, required=True)
    semantic_reconcile.add_argument("--case-ref", type=json_object_argument)
    semantic_reconcile.add_argument("--expected-checkpoint-id", required=True)
    semantic_reconcile.add_argument(
        "--context-file",
        dest="semantic_context_file",
        type=Path,
        required=True,
    )
    semantic_reconcile.add_argument("--resolution-code", required=True)
    semantic_reconcile.add_argument("--actor", default="menxia", choices=sorted(OFFICES))
    semantic_reconcile.add_argument("--evidence", required=True)
    semantic_reconcile.add_argument("--note", default="")

    decree_open = sub.add_parser(
        "decree-open",
        help="runtime-internal idempotent main decree number allocation; public startup is court open",
    )
    decree_open.set_defaults(format="json")
    decree_open.add_argument("--task-id", required=True)
    decree_open.add_argument("--operation-id", required=True)
    decree_open.add_argument("--expected-task-revision", type=int, required=True)
    decree_open.add_argument("--payload-file", type=Path)
    decree_open.add_argument(
        "--replay-only",
        action="store_true",
        help="reference-only replay; no operation body is accepted",
    )
    decree_open.add_argument("--actor", default="taizi", choices=sorted(OFFICES))
    decree_open.add_argument("--evidence", required=True)
    decree_open.add_argument("--note", default="")

    synthetic_closeout = sub.add_parser(
        "synthetic-closeout",
        help="Phase-1 temporary-root closeout adapter; never targets the real Shiguan",
    )
    synthetic_closeout.set_defaults(format="json")
    synthetic_closeout.add_argument("--task-id", required=True)
    synthetic_closeout.add_argument("--operation-id", required=True)
    synthetic_closeout.add_argument("--expected-task-revision", type=int, required=True)
    synthetic_closeout.add_argument("--payload-file", type=Path)
    synthetic_closeout.add_argument(
        "--replay-only",
        action="store_true",
        help="reference-only replay; no closeout body is accepted",
    )
    synthetic_closeout.add_argument("--synthetic-archive-root", type=Path, required=True)
    synthetic_closeout.add_argument("--actor", default="shiguan", choices=sorted(OFFICES))
    synthetic_closeout.add_argument("--evidence", required=True)
    synthetic_closeout.add_argument("--note", default="")

    closeout_recover = sub.add_parser(
        "closeout-recover",
        help="resume a prepared Phase-1 closeout operation by operation id",
    )
    closeout_recover.set_defaults(format="json")
    closeout_recover.add_argument("--operation-id", required=True)

    office_parser = sub.add_parser(
        "office",
        help="apply the shared child-agent/worktree-thread lifecycle through JSON requests",
    )
    office_parser.set_defaults(format="json")
    office_sub = office_parser.add_subparsers(dest="office_command", required=True)
    for office_command_name in OFFICE_CLI_COMMANDS:
        office_command_parser = office_sub.add_parser(office_command_name)
        request_group = office_command_parser.add_mutually_exclusive_group(required=True)
        request_group.add_argument("--request-json", type=json_object_argument)
        request_group.add_argument("--request-file", type=Path)

    agent_admit_parser = sub.add_parser("agent-admit", help="evaluate and record child-agent admission")
    accept_format_after_command(agent_admit_parser)
    agent_admit_parser.add_argument("--task-id", required=True)
    add_expected_semantic_binding(agent_admit_parser)
    add_context_economy_request(agent_admit_parser)
    agent_admit_parser.add_argument("--wave-id", required=True)
    agent_admit_parser.add_argument("--execution-topology", choices=["auto", "serial", "parallel"], default="auto")
    agent_admit_parser.add_argument("--protocol-mode", choices=["auto", "v1", "v2", "serial"], default="auto")
    agent_admit_parser.add_argument("--active-session-protocol", choices=["v1", "v2"])
    agent_admit_parser.add_argument("--needs-parallel-tree", action="store_true")
    agent_admit_parser.add_argument("--needs-fork-turns", action="store_true")
    agent_admit_parser.add_argument("--needs-cross-branch-messages", action="store_true")
    agent_admit_parser.add_argument("--needs-agent-type-override", action="store_true")
    agent_admit_parser.add_argument("--needs-model-override", action="store_true")
    agent_admit_parser.add_argument("--needs-reasoning-effort-override", action="store_true")
    agent_admit_parser.add_argument("--requested-fork-turns", default="none")
    agent_admit_parser.add_argument("--context-tokens", type=int, default=0)
    for field, default in AGENT_EXECUTION_BUDGET_DEFAULTS.items():
        agent_admit_parser.add_argument(f"--{field.replace('_', '-')}", type=int, default=default)
    agent_admit_parser.add_argument(
        "--message-chars",
        type=int,
        default=None,
        help="Unicode code-point count of the largest exact final dispatch message in the wave.",
    )
    agent_admit_parser.add_argument(
        "--message-required-chars",
        type=int,
        default=None,
        help="Optional non-compressible portion of --message-chars; requires --message-optional-chars.",
    )
    agent_admit_parser.add_argument(
        "--message-optional-chars",
        type=int,
        default=None,
        help="Optional compressible portion of --message-chars; required+optional must equal total.",
    )
    agent_admit_parser.add_argument("--requested-agents", type=int, default=1)
    agent_admit_parser.add_argument("--requested-roles", default="", help="Comma/semicolon-separated useful office roles.")
    agent_admit_parser.add_argument("--host-active-agents", type=int, help="Live occupied slots for the whole agent tree, including the root thread; omitted means unknown and fails closed.")
    agent_admit_parser.add_argument("--host-capacity", type=int, help="Live collaboration capacity; omitted or zero means unknown and fails closed.")
    agent_admit_parser.add_argument("--host-retained-agents", type=int, help="Terminal/historical collaboration nodes still visible to the host; omitted means unknown and fails closed.")
    agent_admit_parser.add_argument(
        "--host-reclamation-status",
        choices=["verified", "not-reclaimed", "unknown"],
        default="unknown",
        help="Whether the host has machine-verified that retained terminal nodes no longer consume capacity.",
    )
    agent_admit_parser.add_argument("--next-depth", type=int, help="Depth of the proposed child thread; omitted means unknown and fails closed.")
    agent_admit_parser.add_argument("--max-depth", type=int, default=MAX_AGENT_TREE_DEPTH, help="Configured tree depth ceiling, hard-clamped to 4.")
    agent_admit_parser.add_argument("--max-threads", type=int, default=MAX_AGENT_TREE_THREADS, help="Configured whole-tree concurrency ceiling; defaults to 16 unless a current explicit override authorizes more.")
    agent_admit_parser.add_argument("--explicit-parallel-count", type=int)
    agent_admit_parser.add_argument("--parallel-unlimited", action="store_true")
    agent_admit_parser.add_argument("--parallel-control-source", default="")
    agent_admit_parser.add_argument("--system-memory-percent", type=float, default=0.0)
    agent_admit_parser.add_argument("--user-agent-budget", type=int)
    agent_admit_parser.add_argument("--provider-launch-budget", type=int)
    agent_admit_parser.add_argument("--budget-lease-json", default="")
    agent_admit_parser.add_argument("--requested-bindings-json", default="")
    agent_admit_parser.add_argument("--integration-domain", default="")
    agent_admit_parser.add_argument(
        "--authority", choices=["approval", "autonomous", "super"], default=""
    )
    agent_admit_parser.add_argument("--calling-office", choices=sorted(OFFICES), default="")
    agent_admit_parser.add_argument("--direct-superior", default="")
    agent_admit_parser.add_argument("--assignment", required=True)
    agent_admit_parser.add_argument("--task-focus", required=True)
    agent_admit_parser.add_argument("--complexity", choices=sorted(EVALUATION_LEVELS), required=True)
    agent_admit_parser.add_argument("--risk", choices=sorted(EVALUATION_LEVELS), required=True)
    agent_admit_parser.add_argument("--ambiguity", choices=sorted(EVALUATION_LEVELS), required=True)
    agent_admit_parser.add_argument("--transport", choices=sorted(TRANSPORTS), required=True)
    agent_admit_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    agent_admit_parser.add_argument("--evidence", required=True)
    agent_admit_parser.add_argument("--note", default="")

    for command_name in ("agent-start", "agent-spawn"):
        agent_start_parser = sub.add_parser(command_name, help="record a child agent start")
        accept_format_after_command(agent_start_parser)
        agent_start_parser.add_argument("--task-id", required=True)
        add_agent_semantic_binding(agent_start_parser)
        add_context_economy_request(agent_start_parser)
        agent_start_parser.add_argument("--system-memory-percent", type=float, default=0.0)
        agent_start_parser.add_argument("--agent-id", required=True)
        agent_start_parser.add_argument("--instance-id", default="")
        agent_start_parser.add_argument("--role", required=True)
        agent_start_parser.add_argument("--collaboration-task-name", required=True)
        agent_start_parser.add_argument("--requires-gongjiang", action="store_true")
        agent_start_parser.add_argument("--skill-requirements-json", required=True)
        agent_start_parser.add_argument("--scope", required=True)
        agent_start_parser.add_argument("--task-focus", required=True)
        agent_start_parser.add_argument("--complexity", choices=sorted(EVALUATION_LEVELS), required=True)
        agent_start_parser.add_argument("--risk", choices=sorted(EVALUATION_LEVELS), required=True)
        agent_start_parser.add_argument("--ambiguity", choices=sorted(EVALUATION_LEVELS), required=True)
        agent_start_parser.add_argument("--transport", choices=sorted(TRANSPORTS), required=True)
        agent_start_parser.add_argument("--wave-id", default="wave-default")
        agent_start_parser.add_argument("--dispatch-requested-at", help="ISO-8601 timestamp returned by agent-admit; omitted remains unavailable.")
        agent_start_parser.add_argument("--fork-turns", default="none")
        agent_start_parser.add_argument("--context-tokens", type=int, default=0)
        agent_start_parser.add_argument("--deadline-seconds", type=int, default=AGENT_DEFAULT_DEADLINE_SECONDS)
        agent_start_parser.add_argument("--tool-call-budget", type=int, default=AGENT_DEFAULT_TOOL_CALL_BUDGET)
        agent_start_parser.add_argument(
            "--native-host-action-receipt-json",
            dest="native_host_action_receipt",
            type=json_object_argument,
        )
        agent_start_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
        agent_start_parser.add_argument("--evidence", required=True)
        agent_start_parser.add_argument("--note", default="")

    preload_parser = sub.add_parser("agent-preload-ack", help="validate office profile/dossier/skill preload acknowledgement")
    accept_format_after_command(preload_parser)
    preload_parser.add_argument("--task-id", required=True)
    add_agent_semantic_binding(preload_parser)
    preload_parser.add_argument("--agent-id", required=True)
    preload_parser.add_argument("--role", required=True)
    preload_parser.add_argument(
        "--office-zh",
        default="",
        help="Optional consistency check; the canonical value is derived from the role preload manifest.",
    )
    preload_parser.add_argument("--direct-superior", required=True)
    preload_parser.add_argument("--profile-source", required=True)
    preload_parser.add_argument("--dossier-path", required=True)
    preload_parser.add_argument("--court-skill-path", required=True)
    preload_parser.add_argument("--court-code", required=True)
    preload_parser.add_argument("--profile-loaded", default="")
    preload_parser.add_argument("--court-skill-loaded", default="")
    preload_parser.add_argument('--native-request-ref', default='',
                                help='Echo the received request id for opaque host capture; never hash a file.')
    preload_parser.add_argument("--loaded-skills", required=True)
    preload_parser.add_argument("--agent-dossier-loaded", choices=["YES", "NO"], required=True)
    preload_parser.add_argument("--model-route-id", required=True)
    preload_parser.add_argument("--active-model", default="")
    preload_parser.add_argument("--active-reasoning-effort", default="")
    preload_parser.add_argument("--model-override-applied", choices=["YES", "NO"], required=True)
    preload_parser.add_argument("--inheritance-policy", default="")
    preload_parser.add_argument("--schema", default="court.office.preload_ack.v1")
    preload_parser.add_argument("--preload-status", choices=["PASSED", "FAILED"], default="PASSED")
    preload_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    preload_parser.add_argument("--evidence", required=True)
    preload_parser.add_argument("--note", default="")

    agent_heartbeat_parser = sub.add_parser("agent-heartbeat", help="record a child agent heartbeat")
    accept_format_after_command(agent_heartbeat_parser)
    agent_heartbeat_parser.add_argument("--task-id", required=True)
    add_agent_semantic_binding(agent_heartbeat_parser)
    agent_heartbeat_parser.add_argument("--agent-id", required=True)
    agent_heartbeat_parser.add_argument("--role", required=True)
    agent_heartbeat_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    agent_heartbeat_parser.add_argument("--evidence", required=True)
    agent_heartbeat_parser.add_argument("--note", default="")

    agent_report_parser = sub.add_parser("agent-report", help="record the first or later substantive office report")
    accept_format_after_command(agent_report_parser)
    agent_report_parser.add_argument("--task-id", required=True)
    add_agent_semantic_binding(agent_report_parser)
    agent_report_parser.add_argument("--agent-id", required=True)
    agent_report_parser.add_argument("--role", required=True)
    agent_report_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    agent_report_parser.add_argument("--evidence", required=True)
    agent_report_parser.add_argument("--consultation-refs-json", dest="consultation_refs", type=json_array_argument)
    agent_report_parser.add_argument("--note", default="")

    agent_finish_parser = sub.add_parser("agent-finish", help="record a child agent completion")
    accept_format_after_command(agent_finish_parser)
    agent_finish_parser.add_argument("--task-id", required=True)
    add_agent_semantic_binding(agent_finish_parser)
    agent_finish_parser.add_argument("--agent-id", required=True)
    agent_finish_parser.add_argument("--role", required=True)
    agent_finish_parser.add_argument("--status", default="completed", choices=["completed", "failed", "cancelled"])
    agent_finish_parser.add_argument("--result", default="")
    agent_finish_parser.add_argument("--result-envelope-file", type=Path)
    agent_finish_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    agent_finish_parser.add_argument("--evidence", required=True)
    agent_finish_parser.add_argument("--note", default="")

    agent_close_parser = sub.add_parser("agent-close", help="record a child agent closure")
    accept_format_after_command(agent_close_parser)
    agent_close_parser.add_argument("--task-id", required=True)
    add_agent_semantic_binding(agent_close_parser)
    agent_close_parser.add_argument("--agent-id", required=True)
    agent_close_parser.add_argument("--role", required=True)
    agent_close_parser.add_argument("--result", required=True)
    agent_close_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    agent_close_parser.add_argument("--evidence", required=True)
    agent_close_parser.add_argument("--note", default="")

    agent_reconcile_parser = sub.add_parser("agent-reconcile", help="reconcile a terminal child-agent error")
    accept_format_after_command(agent_reconcile_parser)
    agent_reconcile_parser.add_argument("--task-id", required=True)
    add_agent_semantic_binding(agent_reconcile_parser)
    agent_reconcile_parser.add_argument("--agent-id", required=True)
    agent_reconcile_parser.add_argument("--role", required=True)
    agent_reconcile_parser.add_argument("--wave-id", default="")
    agent_reconcile_parser.add_argument(
        "--error-kind",
        required=True,
        choices=["fatal-quota", "fatal-auth", "capacity", "retryable", "unknown"],
    )
    agent_reconcile_parser.add_argument("--result", required=True)
    agent_reconcile_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    agent_reconcile_parser.add_argument("--evidence", required=True)
    agent_reconcile_parser.add_argument("--note", default="")

    agent_spawn_failed_parser = sub.add_parser(
        "agent-spawn-failed",
        help="record a host spawn refusal before an agent lifecycle record exists",
    )
    accept_format_after_command(agent_spawn_failed_parser)
    agent_spawn_failed_parser.add_argument("--task-id", required=True)
    add_agent_semantic_binding(agent_spawn_failed_parser)
    agent_spawn_failed_parser.add_argument("--wave-id", required=True)
    agent_spawn_failed_parser.add_argument("--role", required=True)
    agent_spawn_failed_parser.add_argument("--instance-id", default="")
    agent_spawn_failed_parser.add_argument(
        "--error-kind",
        required=True,
        choices=["capacity", "retryable", "unknown"],
    )
    agent_spawn_failed_parser.add_argument("--result", required=True)
    agent_spawn_failed_parser.add_argument(
        "--native-host-action-receipt-json",
        dest="native_host_action_receipt",
        type=json_object_argument,
    )
    agent_spawn_failed_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    agent_spawn_failed_parser.add_argument("--evidence", required=True)
    agent_spawn_failed_parser.add_argument("--note", default="")

    agents_parser = sub.add_parser("agents", help="list child agent lifecycle records")
    accept_format_after_command(agents_parser)
    agents_parser.add_argument("--stale-after", type=int, default=900)

    listing = sub.add_parser("list", help="list tasks")
    accept_format_after_command(listing)
    listing.add_argument("--state", default="")
    listing.add_argument("--limit", type=int, default=20)

    events = sub.add_parser("events", help="list recent audit events")
    accept_format_after_command(events)
    events.add_argument("--task-id", default="")
    events.add_argument("--limit", type=int, default=30)

    status = sub.add_parser("status", help="render a command-line court dashboard")
    accept_format_after_command(status)
    status.add_argument("--limit", type=int, default=12)
    status.add_argument('--view', choices=('compact','full'), default='full')

    probe = sub.add_parser("probe", help="machine-readable runtime capabilities")
    accept_format_after_command(probe)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        args = parser.parse_args(raw_argv)
    except CourtCliArgumentError as exc:
        command, _ = _raw_top_level_command(raw_argv)
        if command == "office":
            output(
                _office_cli_error_payload(
                    _raw_office_command(raw_argv),
                    exc,
                    error_code=_office_parse_error_code(raw_argv),
                ),
                "json",
            )
            return 2
        parser.print_usage(sys.stderr)
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return 2
    try:
        if args.command == "plan":
            output(case_plan_operation(args), "json")
        elif args.command == "workflow-status":
            output(workflow_status_payload(args.task_id), "json")
        elif args.command == "intake-schema":
            output(public_intake_contract_payload(), "json")
        elif args.command == "intake-template":
            output(public_intake_template_payload(args.charter), "json")
        elif args.command == "intake-validate":
            intake_value = _read_public_json_object(args.intake_file, "intake")
            capsule_value = (
                _read_public_json_object(args.invariant_capsule_file, "invariant_capsule")
                if args.invariant_capsule_file
                else None
            )
            result = public_intake_validation_payload(
                args.charter,
                intake_value,
                capsule_value,
            )
            output(result, "json")
            return 0 if result["ok"] else 2
        elif args.command == "capsule-template":
            output(invariant_capsule_template(require_exact_text(args.charter, "charter")), "json")
        elif args.command == "capsule-validate":
            result = public_capsule_validation_payload(
                args.charter,
                _read_public_json_object(args.invariant_capsule_file, "invariant_capsule"),
            )
            output(result, "json")
            return 0 if result["ok"] else 2
        elif args.command == "semantic-context-schema":
            output(semantic_context_json_schema(), "json")
        elif args.command == "semantic-context-template":
            output(public_semantic_context_template_payload(args.task_id), "json")
        elif args.command == "semantic-context-validate":
            result = public_semantic_context_validation_payload(
                _read_public_json_object(args.context_file, "semantic_context")
            )
            output(result, "json")
            return 0 if result["ok"] else 2
        elif args.command == "admission-schema":
            output(public_admission_request_json_schema(), "json")
        elif args.command == "admission-template":
            output(public_admission_template_payload(args), "json")
        elif args.command == "admission-validate":
            result = public_admission_validation_payload(
                _read_public_json_object(args.request_file, "admission_request")
            )
            output(result, "json")
            return 0 if result["ok"] else 2
        elif args.command == "create":
            if not getattr(args, "session_id", "") and not args.legacy_compatibility:
                raise ValueError("standard_create_requires_session_id_authority_behavior")
            output(create_task(args), args.format)
        elif args.command == "revise-charter":
            output(revise_charter_task(args), args.format)
        elif args.command == "bind-assessment":
            output(bind_assessment_task(args), args.format)
        elif args.command == "complete":
            output(complete_task_atomically(args), args.format)
        elif args.command == "transition":
            output(transition_task(args), args.format)
        elif args.command == "heartbeat":
            output(update_heartbeat(args), args.format)
        elif args.command == "pause":
            output(pause_task(args), args.format)
        elif args.command == "resume":
            output(resume_task(args), args.format)
        elif args.command == "cancel":
            output(cancel_task(args), args.format)
        elif args.command == "semantic":
            if args.semantic_command == "checkpoint":
                output(
                    semantic_cli_payload("checkpoint", semantic_checkpoint_task(args)),
                    "json",
                )
            elif args.semantic_command == "verify":
                output(
                    semantic_cli_payload("verify", semantic_verify_task(args)),
                    "json",
                )
            elif args.semantic_command == "correct":
                output(
                    semantic_cli_payload("correct", revise_charter_task(args)),
                    "json",
                )
            elif args.semantic_command == "resume":
                output(
                    semantic_cli_payload("resume", semantic_resume_task(args)),
                    "json",
                )
            elif args.semantic_command == "quarantine":
                output(
                    semantic_cli_payload("quarantine", semantic_quarantine_task(args)),
                    "json",
                )
            elif args.semantic_command == "reconcile":
                output(
                    semantic_cli_payload("reconcile", semantic_reconcile_task(args)),
                    "json",
                )
            else:
                parser.error("unknown semantic command")
        elif args.command == "decree-open":
            output(
                operation_cli_payload("decree-open", decree_open_task(args)),
                "json",
            )
        elif args.command == "synthetic-closeout":
            output(
                operation_cli_payload(
                    "synthetic-closeout",
                    synthetic_closeout_task(args),
                ),
                "json",
            )
        elif args.command == "closeout-recover":
            output(
                operation_cli_payload(
                    "closeout-recover",
                    recover_closeout_operation(args.operation_id),
                ),
                "json",
            )
        elif args.command == "office":
            office_request = office_request_namespace(args)
            standard_admission = (args.office_command == "admit" and
                                  getattr(office_request, "schema", None) == "court.agent.admission_request.v1")
            if standard_admission:
                office_request = parser.parse_args(public_admission_request_argv(vars(office_request)))
            office_request._production_cli = True
            office_request._context_contract_required = True
            office_handlers = {
                "admit": office_admit,
                "native-request": office_native_request,
                "native-capture": office_native_capture,
                "start": office_start,
                "followup": office_followup,
                "preload-ack": office_preload_ack,
                "report": office_report,
                "finish": office_finish,
                "close": office_close,
            }
            handler = agent_admit if standard_admission else office_handlers.get(args.office_command)
            if handler is None:
                parser.error("unknown office command")
            output(
                office_cli_payload(args.office_command, handler(office_request)),
                "json",
            )
        elif args.command == "agent-admit":
            args._production_cli = True
            args._context_contract_required = True
            output(agent_admit(args), args.format)
        elif args.command in {"agent-start", "agent-spawn"}:
            args._production_cli = True
            args._context_contract_required = True
            output(agent_start(args), args.format)
        elif args.command == "agent-preload-ack":
            output(agent_preload_ack(args), args.format)
        elif args.command == "agent-heartbeat":
            output(agent_heartbeat(args), args.format)
        elif args.command == "agent-report":
            output(agent_report(args), args.format)
        elif args.command == "agent-finish":
            output(agent_finish(args), args.format)
        elif args.command == "agent-close":
            output(agent_close(args), args.format)
        elif args.command == "agent-reconcile":
            output(agent_reconcile(args), args.format)
        elif args.command == "agent-spawn-failed":
            args._production_cli = True
            output(agent_spawn_failed(args), args.format)
        elif args.command == "agents":
            output(list_agents_payload(args), args.format)
        elif args.command == "list":
            output(list_tasks(args), args.format)
        elif args.command == "events":
            output(read_events(args.limit, args.task_id), args.format)
        elif args.command == "status":
            if args.format == "json":
                output(status_payload(args), args.format)
            else:
                print(status_payload(args)["dashboard"])
        elif args.command == "probe":
            output(probe_payload(), args.format)
        else:
            parser.error("unknown command")
    except ValueError as exc:
        if getattr(args, "command", "") in {
            "semantic",
            "decree-open",
            "synthetic-closeout",
            "closeout-recover",
            "office",
        }:
            command = getattr(args, "semantic_command", "")
            schema = "court.semantic.cli.v1"
            if getattr(args, "command", "") == "office":
                command = getattr(args, "office_command", "")
                schema = "court.office.cli.v1"
            elif getattr(args, "command", "") != "semantic":
                command = getattr(args, "command", "")
                schema = "court.operation.cli.v1"
            payload: dict[str, object] = {
                "schema": schema,
                "ok": False,
                "command": command,
                "fail_closed": True,
                "error": str(exc),
            }
            if schema == "court.office.cli.v1":
                payload["error_code"] = "office_business_error"
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return 2
        print(f"COURT_RUNTIME_ERROR {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"COURT_RUNTIME_ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
