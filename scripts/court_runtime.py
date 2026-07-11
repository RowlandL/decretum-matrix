"""Machine-checkable /court state and audit ledger.

This module is intentionally small and file-backed. It gives the skill a local
runtime substrate without depending on a GUI service or an external agent host.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from typing import Any

from court_dispatch_policy import MAX_AGENT_TREE_DEPTH, MAX_AGENT_TREE_THREADS, select_wave
from court_office_bootstrap import build_preload_manifest, validate_preload_ack
from court_model_router import (
    EVALUATION_LEVELS,
    MODEL_MAX_REASONING_EFFORT,
    MODEL_ROUTE_SCHEMA,
    TRANSPORTS,
    route_office_model,
)
from court_file_lock import atomic_write_text, file_lock
from court_multi_agent_protocol import ProtocolRequirements, select_protocol
from court_codex_office_worker import validate_host_proof
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
    "Pending": {"Taizi", "Cancelled"},
    "Taizi": {"ThreeDepartments", "Done", "Cancelled"},
    "ThreeDepartments": {"ThreeDepartmentsPetition", "Taizi", "Cancelled"},
    "ThreeDepartmentsPetition": {"TaiziReply", "ThreeDepartments", "Rejected", "Cancelled"},
    "TaiziReply": {"ShangshuDispatch", "ThreeDepartments", "Done", "Cancelled"},
    "ShangshuDispatch": {"SixMinistries", "MenxiaReview", "Paused", "Cancelled"},
    "SixMinistries": {"Workshops", "MenxiaReview", "Paused", "Cancelled"},
    "Workshops": {"MenxiaReview", "Paused", "Cancelled"},
    "MenxiaReview": {"ShiguanRecorded", "ThreeDepartments", "ShangshuDispatch", "Rejected", "Cancelled"},
    "ShiguanRecorded": {"Done", "MenxiaReview"},
    "Done": set(),
    "Paused": {"TaiziReply", "ShangshuDispatch", "SixMinistries", "Workshops", "Cancelled"},
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
RUNTIME_SCHEMA_VERSION = 2
CONTROL_STATES = {"Paused", "Cancelled"}
SERIAL_OVERRIDE_RE = re.compile(
    r"(parallel_dispatch\s*=\s*NOT_APPLICABLE/user_serial_override|"
    r"完全串行|只允许串行|不得派生子|不派生子|no child spawn|serial override)",
    re.IGNORECASE,
)
TERMINAL_AGENT_STATUSES = {"completed", "failed", "cancelled", "closed"}
AGENT_LONG_CONTEXT_TOKENS = 32_000
AGENT_MAX_RECENT_FORK_TURNS = 3
AGENT_DEFAULT_DEADLINE_SECONDS = 600
AGENT_DEFAULT_TOOL_CALL_BUDGET = 8
AGENT_MESSAGE_BUDGET_SCHEMA = "court.agent.dispatch_message_budget.v1"
AGENT_MESSAGE_BUDGET_FLOOR_CHARS = 6_000
AGENT_MESSAGE_BUDGET_QUANTUM_CHARS = 1_000
AGENT_MESSAGE_BUDGET_CEILING_CHARS = 12_000
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


def ensure_runtime_root() -> None:
    if not os.environ.get("COURT_RUNTIME_ROOT"):
        ensure_shared_seed()
    runtime_root().mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value).strip("-")
    return value[:64] or "court-task"


def load_tasks() -> dict[str, dict[str, Any]]:
    path = tasks_path()
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("tasks.json must contain an object")
    return {str(key): dict(item) for key, item in value.items() if isinstance(item, dict)}


def write_tasks(tasks: dict[str, dict[str, Any]]) -> None:
    ensure_runtime_root()
    path = tasks_path()
    atomic_write_text(
        path,
        json.dumps(tasks, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


@contextmanager
def runtime_lock(timeout: float = 10.0, poll: float = 0.05):
    ensure_runtime_root()
    with file_lock(lock_path(), timeout=timeout, poll_interval=poll):
        yield


def append_event(event: dict[str, Any]) -> None:
    ensure_runtime_root()
    with events_path().open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def read_events(limit: int = 50, task_id: str = "") -> list[dict[str, Any]]:
    path = events_path()
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if task_id and str(event.get("task_id")) != task_id:
            continue
        events.append(event)
    return events[-max(1, limit) :]


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
    if to_state in CONTROL_STATES and not control_context:
        raise ValueError(f"use dedicated {to_state.lower()} command for auditable control transitions")
    if from_state == "Paused" and to_state != "Cancelled":
        paused_from = str(task.get("paused_from") or "")
        allowed_resume_states = TRANSITIONS.get(paused_from, set()) | {paused_from}
        if to_state not in allowed_resume_states:
            raise ValueError(f"illegal paused resume: {paused_from} paused, cannot resume to {to_state}")
    if to_state == "Done" and not evidence.strip():
        raise ValueError("Done transition requires evidence")


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
    roles = tuple(dict.fromkeys(item.strip().lower() for item in raw if item.strip()))
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
    components_supplied = raw_required_chars is not None or raw_optional_chars is not None
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
    components_valid = (
        not components_supplied
        or (
            required_value is not None
            and optional_value is not None
            and total_valid
            and required_value + optional_value == message_value
        )
    )
    if not total_valid or not components_valid:
        component_fields["message_component_status"] = "invalid" if components_supplied else "unspecified"
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
            "message_budget_retryable": False,
            "compression_guidance": "report a non-negative Unicode code-point count",
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


def evaluate_agent_admission(task: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
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
    configured_max_threads = min(
        MAX_AGENT_TREE_THREADS,
        int(getattr(args, "max_threads", MAX_AGENT_TREE_THREADS) or MAX_AGENT_TREE_THREADS),
    )
    configured_max_depth = min(
        MAX_AGENT_TREE_DEPTH,
        int(getattr(args, "max_depth", MAX_AGENT_TREE_DEPTH) or MAX_AGENT_TREE_DEPTH),
    )
    user_agent_budget = getattr(args, "user_agent_budget", None)
    provider_launch_budget = getattr(args, "provider_launch_budget", None)
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
        "root_thread_counts_toward_limit": True,
        "user_agent_budget": user_agent_budget,
        "provider_launch_budget": provider_launch_budget,
        "requested_agents": requested_agents,
        "deadline_seconds": AGENT_DEFAULT_DEADLINE_SECONDS,
        "tool_call_budget": AGENT_DEFAULT_TOOL_CALL_BUDGET,
        "reuse_errored_agents": False,
        **message_budget,
    }

    def deny(decision: str, dispatch: str = "runtime_degraded") -> dict[str, Any]:
        result.update(
            allowed=False,
            decision=decision,
            parallel_dispatch=dispatch,
            selected_roles=(),
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


def task_summary(task: dict[str, Any]) -> str:
    return (
        f"{task.get('task_id')} | {task.get('state')} | {task.get('owner')} | "
        f"{task.get('report_tier')} | {task.get('title')}"
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


def normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(task)
    normalized.setdefault("runtime_schema_version", RUNTIME_SCHEMA_VERSION)
    normalized.setdefault("agent_runtime", default_agent_runtime())
    normalized.setdefault("stop_condition", "")
    normalized.setdefault("unsafe_remaining", "")
    normalized.setdefault("evidence_preserved", "")
    normalized.setdefault("agents", {})
    return normalized


@dataclass
class TransitionResult:
    task: dict[str, Any]
    event: dict[str, Any]


def create_task(args: argparse.Namespace) -> TransitionResult:
    with runtime_lock():
        tasks = load_tasks()
        task_id = args.task_id or f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{slugify(args.title)}"
        if task_id in tasks:
            raise ValueError(f"task already exists: {task_id}")
        report_tier = args.report_tier or ("brief" if read_only_decree(args.charter) else "standard")
        if report_tier not in REPORT_TIERS:
            raise ValueError(f"invalid report tier: {report_tier}")
        task = {
            "runtime_schema_version": RUNTIME_SCHEMA_VERSION,
            "task_id": task_id,
            "title": args.title,
            "charter": args.charter,
            "state": "Pending",
            "owner": args.owner,
            "report_tier": report_tier,
            "read_only": read_only_decree(args.charter),
            "created_at": now_text(),
            "updated_at": now_text(),
            "heartbeat": "created",
            "last_evidence": args.evidence,
            "agent_runtime": default_agent_runtime(),
            "stop_condition": "",
            "unsafe_remaining": "",
            "evidence_preserved": "",
            "agents": {},
        }
        tasks[task_id] = task
        write_tasks(tasks)
        event = make_event(task, "create", "", "Pending", args.owner, args.evidence, args.note)
        append_event(event)
    return TransitionResult(task, event)


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
        from_state = str(task.get("state") or "Pending")
        to_state = args.to_state
        if to_state not in STATES:
            raise ValueError(f"unknown state: {to_state}")
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
        write_tasks(tasks)
        event = make_event(task, "transition", from_state, to_state, actor, args.evidence, args.note)
        append_event(event)
    return TransitionResult(task, event)


def transition_task(args: argparse.Namespace) -> TransitionResult:
    return apply_transition(args, control_context=False)


def require_text(value: str, name: str) -> str:
    value = (value or "").strip()
    if not value:
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
        wave_id = str(getattr(args, "wave_id", "") or "wave-default")
        existing_admissions = task.get("agent_admissions")
        if existing_admissions is not None and not isinstance(existing_admissions, dict):
            raise ValueError("agent admission ledger is corrupt")
        if isinstance(existing_admissions, dict) and wave_id in existing_admissions:
            raise ValueError(f"agent admission wave already exists: {wave_id}")
        result = evaluate_agent_admission(task, args)
        model_routes = {
            str(role): route_office_model(
                transport=args.transport,
                protocol=str(result.get("selected_protocol") or "v2"),
                role=str(role),
                assignment=args.assignment,
                task_focus=args.task_focus,
                complexity=args.complexity,
                risk=args.risk,
                ambiguity=args.ambiguity,
            )
            for role in result.get("selected_roles", [])
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
        now = now_text()
        result["generated_at"] = now
        admission_record = {
            key: result[key]
            for key in (
                "dispatch_requested_at",
                "generated_at",
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
                "deferred_roles",
                "host_capacity",
                "host_active_agents",
                "host_retained_agents",
                "host_reclamation_status",
                "host_reclamation_verified",
                "available_slots",
                "user_agent_budget",
                "provider_launch_budget",
                "deadline_seconds",
                "tool_call_budget",
                *AGENT_MESSAGE_BUDGET_FIELDS,
                "protocol_decision",
                "selected_protocol",
                "model_route_inputs",
                "model_routes",
            )
        }
        task["last_agent_admission"] = admission_record
        admissions = task.setdefault("agent_admissions", {})
        if not isinstance(admissions, dict):
            admissions = {}
            task["agent_admissions"] = admissions
        admissions[result["wave_id"]] = admission_record
        task["updated_at"] = now
        task["last_evidence"] = f"agent_admit {result['decision']}: {evidence}"
        tasks[args.task_id] = task
        write_tasks(tasks)
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
        )
        event.update({key: result[key] for key in AGENT_MESSAGE_BUDGET_FIELDS})
        append_event(event)
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
        write_tasks(tasks)
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
        append_event(event)
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
        admissions = task.get("agent_admissions")
        admission = admissions.get(wave_id) if isinstance(admissions, dict) else None
        if not isinstance(admission, dict) or admission.get("allowed") is not True:
            raise ValueError(f"allowed agent admission not found: {wave_id}")
        selected_roles = list(admission.get("selected_roles") or [])
        if role not in selected_roles:
            raise ValueError("spawn-failed role was not selected by the admission")
        consumed_roles = admission.get("consumed_roles")
        if consumed_roles is None:
            consumed_roles = {}
            admission["consumed_roles"] = consumed_roles
        if not isinstance(consumed_roles, dict):
            raise ValueError("spawn-failed admission consumption ledger is corrupt")
        if role in consumed_roles:
            raise ValueError("spawn-failed role already has a started agent")
        failed_roles = admission.get("failed_roles")
        if failed_roles is None:
            failed_roles = {}
            admission["failed_roles"] = failed_roles
        if not isinstance(failed_roles, dict):
            raise ValueError("spawn-failed admission failure ledger is corrupt")
        if role in failed_roles:
            raise ValueError("spawn failure was already recorded for this role")
        now = now_text()
        failure = {
            "role": role,
            "error_kind": error_kind,
            "result": result_text,
            "evidence": evidence,
            "recorded_at": now,
        }
        failed_roles[role] = failure
        remaining_roles = [
            item for item in selected_roles if item not in consumed_roles
        ]
        deferred_roles = list(
            dict.fromkeys([*(admission.get("deferred_roles") or []), *remaining_roles])
        )
        admission["deferred_roles"] = deferred_roles
        admission["effective_selected_roles"] = list(consumed_roles)
        admission["observed_available_slots"] = len(consumed_roles)
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
        task["last_evidence"] = f"agent_spawn_failed {wave_id} {role} {error_kind}: {evidence}"
        tasks[args.task_id] = task
        write_tasks(tasks)
        event = make_event(
            task,
            "agent_spawn_failed",
            "admitted",
            "failed",
            args.actor,
            evidence,
            args.note,
        )
        event.update(wave_id=wave_id, agent_role=role, error_kind=error_kind)
        append_event(event)
    return {
        "kind": "court_agent_spawn_failed",
        "task_id": args.task_id,
        "wave_id": wave_id,
        "failed_role": role,
        "deferred_roles": deferred_roles,
        "circuit_breaker": circuit,
        "raw_provider_detail_stored": False,
    }


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
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        actor = args.actor
        if actor not in OFFICES:
            raise ValueError(f"unknown actor office: {actor}")
        agents = task.setdefault("agents", {})
        if not isinstance(agents, dict):
            agents = {}
            task["agents"] = agents
        start_admission: dict[str, Any] | None = None
        start_model_route: dict[str, Any] | None = None
        if lifecycle_action == "agent_start":
            if agent_id in agents:
                raise ValueError(f"agent already exists: {agent_id}")
            wave_id = str(getattr(args, "wave_id", "") or "wave-default")
            admissions = task.get("agent_admissions")
            admission = admissions.get(wave_id) if isinstance(admissions, dict) else None
            if not isinstance(admission, dict):
                raise ValueError(f"agent start admission not found: {wave_id}")
            if admission.get("allowed") is not True:
                raise ValueError(f"agent start admission was not allowed: {wave_id}")
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
            try:
                admission_deadline_seconds = int(admission.get("deadline_seconds"))
            except (TypeError, ValueError) as exc:
                raise ValueError("agent start admission deadline is invalid") from exc
            if admission_deadline_seconds < 1:
                raise ValueError("agent start admission deadline is invalid")
            current_time = datetime.now(timezone.utc)
            for timestamp_name, timestamp_value in (
                ("dispatch_requested_at", admitted_dispatch_requested_at),
                ("generated_at", admitted_generated_at),
            ):
                timestamp_time = datetime.fromisoformat(timestamp_value).astimezone(timezone.utc)
                timestamp_age = (current_time - timestamp_time).total_seconds()
                if timestamp_age < -1:
                    raise ValueError(f"agent start admission {timestamp_name} is in the future")
                if timestamp_age > admission_deadline_seconds:
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
            for field, minimum in (
                ("context_tokens", 0),
                ("deadline_seconds", 1),
                ("tool_call_budget", 1),
            ):
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
            model_routes = admission.get("model_routes")
            model_route = model_routes.get(role) if isinstance(model_routes, dict) else None
            if not isinstance(model_route, dict):
                raise ValueError("agent start role does not have an admitted model route")
            consumed_roles = admission.get("consumed_roles")
            if consumed_roles is not None and not isinstance(consumed_roles, dict):
                raise ValueError("agent start admission consumption ledger is corrupt")
            if isinstance(consumed_roles, dict) and role in consumed_roles:
                raise ValueError(f"agent start admitted role already consumed: {role}")
            failed_roles = admission.get("failed_roles")
            if failed_roles is not None and not isinstance(failed_roles, dict):
                raise ValueError("agent start admission failure ledger is corrupt")
            if isinstance(failed_roles, dict) and role in failed_roles:
                raise ValueError(f"agent start admitted role already failed: {role}")
            wave_blocks = task.get("agent_wave_blocks")
            if isinstance(wave_blocks, dict) and wave_id in wave_blocks:
                raise ValueError(f"agent start wave is blocked: {wave_id}")
            start_admission = admission
            start_model_route = dict(model_route)
        else:
            existing_agent = agents.get(agent_id)
            if not isinstance(existing_agent, dict):
                raise ValueError(f"agent not found: {agent_id}")
            if existing_agent.get("role") != role:
                raise ValueError("agent role does not match lifecycle record")
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
            ):
                raise ValueError("terminal agent cannot accept lifecycle events")
        now = now_text()
        current = dict(agents.get(agent_id, {})) if isinstance(agents.get(agent_id), dict) else {}
        previous_status = str(current.get("final_status") or current.get("status") or "")
        if lifecycle_action == "agent_heartbeat" and current.get("preload_status") != "PASSED":
            status = "starting"
        if lifecycle_action == "agent_report" and current.get("preload_status") != "PASSED":
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
            manifest = build_preload_manifest(role)
            wave_id = str(getattr(args, "wave_id", "") or "wave-default")
            if start_admission is None or start_model_route is None:
                raise ValueError("agent start admission binding was not validated")
            model_route = start_model_route
            route_binding_source = "agent_admit"
            if model_route["transport"] == "codex" and str(getattr(args, "fork_turns", "none")) != "none":
                raise ValueError("ordinary Codex V2 court dispatch requires fork_turns=none for bounded context isolation")
            current.setdefault("started_at", now)
            current.setdefault("host_session_started_at", now)
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
                "model_route_id": model_route["model_route_id"],
            }
            current["model_route_status"] = "PENDING"
            current["wave_id"] = wave_id
            current["fork_turns"] = str(getattr(args, "fork_turns", "none") or "none")
            current["context_tokens"] = max(0, int(getattr(args, "context_tokens", 0) or 0))
            current["deadline_seconds"] = max(
                1, int(getattr(args, "deadline_seconds", AGENT_DEFAULT_DEADLINE_SECONDS) or AGENT_DEFAULT_DEADLINE_SECONDS)
            )
            current["tool_call_budget"] = max(
                1, int(getattr(args, "tool_call_budget", AGENT_DEFAULT_TOOL_CALL_BUDGET) or AGENT_DEFAULT_TOOL_CALL_BUDGET)
            )
            current["preload_manifest"] = asdict(manifest)
            current["preload_contract_version"] = manifest.preload_ack_schema
            current["preload_ack_required"] = True
            current["preload_status"] = "PENDING"
            current["office_identity_evidence"] = "PENDING"
            consumed_roles = start_admission.get("consumed_roles")
            if not isinstance(consumed_roles, dict):
                consumed_roles = {}
                start_admission["consumed_roles"] = consumed_roles
            consumed_roles[role] = agent_id
        if lifecycle_action == "agent_report" and current.get("preload_status") == "PASSED":
            current.setdefault("first_office_report_at", now)
        if lifecycle_action == "agent_finish":
            current["finished_at"] = now
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
        agents[agent_id] = current
        task["updated_at"] = now
        task["last_evidence"] = f"{lifecycle_action} {agent_id}: {evidence}"
        tasks[args.task_id] = task
        write_tasks(tasks)
        event = make_event(task, lifecycle_action, status, str(task.get("state")), actor, evidence, args.note)
        event["agent_id"] = agent_id
        event["agent_role"] = role
        append_event(event)
    return TransitionResult(task, event)


def agent_start(args: argparse.Namespace) -> TransitionResult:
    require_text(args.scope, "scope")
    return agent_event(args, "agent_start", "starting", "evidence")


def agent_preload_ack(args: argparse.Namespace) -> dict[str, Any]:
    evidence = require_text(args.evidence, "evidence")
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
        "profile_hash": args.profile_hash,
        "dossier_hash": args.dossier_hash,
        "court_skill_hash": args.court_skill_hash,
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
            manifest = build_preload_manifest(role)
            ack["office_zh"] = manifest.office_zh
            if explicit_office_zh and explicit_office_zh != manifest.office_zh:
                raise ValueError("preload ack office_zh does not match role manifest")
            model_route = current.get("model_route")
            if not isinstance(model_route, dict):
                raise ValueError("started agent is missing model route")
            validated = validate_preload_ack(manifest, ack, model_route=model_route)
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
                finished_at=now,
                closed_at=now,
            )
        else:
            current.update(
                status="running",
                preload_status="PASSED",
                model_route_status="PASSED",
                preload_ack_at=now,
                office_identity_evidence="PASSED",
                loaded_skills=validated["loaded_skills"],
                profile_hash=validated["profile_hash"],
                dossier_hash=validated["dossier_hash"],
                court_skill_hash=validated["court_skill_hash"],
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
        write_tasks(tasks)
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
        append_event(event)
    if failure:
        raise ValueError(f"preload_contract_failed: {failure}")
    return {"kind": "court_agent_preload_ack", "task_id": args.task_id, "agent": current, "ack": ack}


def agent_heartbeat(args: argparse.Namespace) -> TransitionResult:
    return agent_event(args, "agent_heartbeat", "running", "evidence")


def agent_report(args: argparse.Namespace) -> TransitionResult:
    return agent_event(args, "agent_report", "running", "evidence")


def agent_finish(args: argparse.Namespace) -> TransitionResult:
    require_text(args.result, "result")
    return agent_event(args, "agent_finish", args.status, "evidence")


def agent_close(args: argparse.Namespace) -> TransitionResult:
    require_text(args.result, "result")
    args.status = "closed"
    return agent_event(args, "agent_close", "closed", "evidence")


def update_heartbeat(args: argparse.Namespace) -> TransitionResult:
    with runtime_lock():
        tasks = load_tasks()
        task = tasks.get(args.task_id)
        if not task:
            raise ValueError(f"task not found: {args.task_id}")
        actor = args.actor
        if actor not in OFFICES:
            raise ValueError(f"unknown actor office: {actor}")
        previous = str(task.get("heartbeat") or "")
        task["heartbeat"] = args.heartbeat
        task["updated_at"] = now_text()
        task["last_evidence"] = args.evidence
        tasks[args.task_id] = task
        write_tasks(tasks)
        event = make_event(task, "heartbeat", previous, str(task.get("state")), actor, args.evidence, args.note)
        append_event(event)
    return TransitionResult(task, event)


def list_tasks(args: argparse.Namespace) -> list[dict[str, Any]]:
    tasks = [normalize_task(task) for task in load_tasks().values()]
    state = getattr(args, "state", "")
    if state:
        tasks = [task for task in tasks if str(task.get("state")) == state]
    tasks.sort(key=lambda task: str(task.get("updated_at", "")), reverse=True)
    return tasks[: args.limit]


def render_cli(tasks: list[dict[str, Any]], events: list[dict[str, Any]]) -> str:
    lines = ["COURT RUNTIME"]
    if not tasks:
        lines.append("tasks: none")
    else:
        lines.append("tasks:")
        for task in tasks:
            lines.append(f"- {task_summary(task)}")
            lines.append(f"  heartbeat: {task.get('heartbeat', '')}; evidence: {task.get('last_evidence', '')}")
    lines.append("recent_events:")
    if not events:
        lines.append("- none")
    for event in events:
        lines.append(
            f"- {event.get('time')} | {event.get('task_id')} | {event.get('action')} | "
            f"{event.get('from_state')} -> {event.get('to_state')} | {event.get('actor')}"
        )
    return "\n".join(lines)


def status_payload(args: argparse.Namespace) -> dict[str, Any]:
    tasks = list_tasks(args)
    events = read_events(limit=12)
    return {
        "kind": "court_runtime_status",
        "runtime_schema_version": RUNTIME_SCHEMA_VERSION,
        "generated_at": now_text(),
        "runtime_root": str(runtime_root()),
        "lock_path": str(lock_path()),
        "task_count": len(tasks),
        "tasks": tasks,
        "recent_events": events,
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
    fresh_worker_proof_sha256 = None
    if fresh_worker_proof_path.is_file():
        try:
            proof = validate_host_proof(json.loads(fresh_worker_proof_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError):
            fresh_worker_status = "host_proof_invalid"
        else:
            fresh_worker_status = "verified"
            fresh_worker_proof_sha256 = proof["proof_sha256"]
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
            "transition",
            "heartbeat",
            "pause",
            "resume",
            "cancel",
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
            "fresh_worker_host_proof_sha256": fresh_worker_proof_sha256,
            "fresh_worker_binary_pin_required": True,
            "fresh_worker_same_session": False,
            "fork_turns": "none",
            "claude_code": "inherit_main_thread_model",
            "hermes": "inherit_main_profile_model_design_deferred",
        },
        "degraded_reasons": degraded_reasons,
    }


def output(value: Any, fmt: str) -> None:
    if fmt == "json":
        if isinstance(value, TransitionResult):
            value = {"task": value.task, "event": value.event}
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if isinstance(value, TransitionResult):
        print(task_summary(value.task))
        print(f"event: {value.event['action']} {value.event['from_state']} -> {value.event['to_state']}")
        return
    if isinstance(value, list):
        print(render_cli(value, read_events(limit=10)))
        return
    print(str(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    sub = parser.add_subparsers(dest="command", required=True)

    def accept_format_after_command(command: argparse.ArgumentParser) -> None:
        command.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)

    create = sub.add_parser("create", help="create a court task in Pending")
    accept_format_after_command(create)
    create.add_argument("--title", required=True)
    create.add_argument("--charter", default="")
    create.add_argument("--task-id", default="")
    create.add_argument("--owner", default="taizi", choices=sorted(OFFICES))
    create.add_argument("--report-tier", default="", choices=sorted(REPORT_TIERS) + [""])
    create.add_argument("--evidence", default="")
    create.add_argument("--note", default="")

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

    agent_admit_parser = sub.add_parser("agent-admit", help="evaluate and record child-agent admission")
    accept_format_after_command(agent_admit_parser)
    agent_admit_parser.add_argument("--task-id", required=True)
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
    agent_admit_parser.add_argument("--max-threads", type=int, default=MAX_AGENT_TREE_THREADS, help="Configured whole-tree concurrency ceiling, hard-clamped to 16.")
    agent_admit_parser.add_argument("--user-agent-budget", type=int)
    agent_admit_parser.add_argument("--provider-launch-budget", type=int)
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
        agent_start_parser.add_argument("--agent-id", required=True)
        agent_start_parser.add_argument("--role", required=True)
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
        agent_start_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
        agent_start_parser.add_argument("--evidence", required=True)
        agent_start_parser.add_argument("--note", default="")

    preload_parser = sub.add_parser("agent-preload-ack", help="validate office profile/dossier/skill preload acknowledgement")
    accept_format_after_command(preload_parser)
    preload_parser.add_argument("--task-id", required=True)
    preload_parser.add_argument("--agent-id", required=True)
    preload_parser.add_argument("--role", required=True)
    preload_parser.add_argument(
        "--office-zh",
        default="",
        help="Optional consistency check; the canonical value is derived from the role preload manifest.",
    )
    preload_parser.add_argument("--direct-superior", required=True)
    preload_parser.add_argument("--profile-hash", required=True)
    preload_parser.add_argument("--dossier-hash", required=True)
    preload_parser.add_argument("--court-skill-hash", required=True)
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
    agent_heartbeat_parser.add_argument("--agent-id", required=True)
    agent_heartbeat_parser.add_argument("--role", required=True)
    agent_heartbeat_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    agent_heartbeat_parser.add_argument("--evidence", required=True)
    agent_heartbeat_parser.add_argument("--note", default="")

    agent_report_parser = sub.add_parser("agent-report", help="record the first or later substantive office report")
    accept_format_after_command(agent_report_parser)
    agent_report_parser.add_argument("--task-id", required=True)
    agent_report_parser.add_argument("--agent-id", required=True)
    agent_report_parser.add_argument("--role", required=True)
    agent_report_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    agent_report_parser.add_argument("--evidence", required=True)
    agent_report_parser.add_argument("--note", default="")

    agent_finish_parser = sub.add_parser("agent-finish", help="record a child agent completion")
    accept_format_after_command(agent_finish_parser)
    agent_finish_parser.add_argument("--task-id", required=True)
    agent_finish_parser.add_argument("--agent-id", required=True)
    agent_finish_parser.add_argument("--role", required=True)
    agent_finish_parser.add_argument("--status", default="completed", choices=["completed", "failed", "cancelled"])
    agent_finish_parser.add_argument("--result", required=True)
    agent_finish_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    agent_finish_parser.add_argument("--evidence", required=True)
    agent_finish_parser.add_argument("--note", default="")

    agent_close_parser = sub.add_parser("agent-close", help="record a child agent closure")
    accept_format_after_command(agent_close_parser)
    agent_close_parser.add_argument("--task-id", required=True)
    agent_close_parser.add_argument("--agent-id", required=True)
    agent_close_parser.add_argument("--role", required=True)
    agent_close_parser.add_argument("--result", required=True)
    agent_close_parser.add_argument("--actor", default="shangshu", choices=sorted(OFFICES))
    agent_close_parser.add_argument("--evidence", required=True)
    agent_close_parser.add_argument("--note", default="")

    agent_reconcile_parser = sub.add_parser("agent-reconcile", help="reconcile a terminal child-agent error")
    accept_format_after_command(agent_reconcile_parser)
    agent_reconcile_parser.add_argument("--task-id", required=True)
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
    agent_spawn_failed_parser.add_argument("--wave-id", required=True)
    agent_spawn_failed_parser.add_argument("--role", required=True)
    agent_spawn_failed_parser.add_argument(
        "--error-kind",
        required=True,
        choices=["capacity", "retryable", "unknown"],
    )
    agent_spawn_failed_parser.add_argument("--result", required=True)
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

    probe = sub.add_parser("probe", help="machine-readable runtime capabilities")
    accept_format_after_command(probe)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            output(create_task(args), args.format)
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
        elif args.command == "agent-admit":
            output(agent_admit(args), args.format)
        elif args.command in {"agent-start", "agent-spawn"}:
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
    except Exception as exc:
        print(f"COURT_RUNTIME_ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
