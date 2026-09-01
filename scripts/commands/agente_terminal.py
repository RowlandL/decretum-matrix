"""Manage visible agente terminal metadata, logs, and Shiguan summaries."""

from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True

from court_platform import sh_join, terminal_launch_plan
from court_file_lock import file_lock, shiguan_write_lock_path
import court_runtime
from shiguan_entry_utils import enrich_entry
from shiguan_paths import code_root, ensure_shared_seed, reference_path, relative_to_data


OFFICE_CODES = {
    "taizi": ("S", "TZ", "太子"),
    "zhongshu": ("A", "ZS", "中书省"),
    "menxia": ("A", "MX", "门下省"),
    "shangshu": ("A", "SS", "尚书省"),
    "hubu": ("B", "HB", "户部"),
    "libu": ("B", "LB", "礼部"),
    "bingbu": ("B", "BB", "兵部"),
    "xingbu": ("B", "XB", "刑部"),
    "gongbu": ("B", "GB", "工部"),
    "libu-hr": ("B", "HR", "吏部"),
    "workshop": ("C", "WS", "工坊"),
    "craftsman": ("C", "CM", "工匠"),
}

SENSITIVE_RE = re.compile(
    r'''(?ix)
    (["']?(?:api[_-]?key|authorization|bearer|cookie|token|secret|password)["']?\s*[:=]\s*)
    (?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,}]+)
    '''
)
BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
ATTENTION_STATES = {"blocked", "failed", "stale", "orphaned"}
COMPLETED_STATES = {"completed", "closed", "cancelled"}


def skill_root() -> Path:
    configured = os.environ.get("COURT_SKILL_ROOT")
    if configured:
        return Path(configured)
    return code_root()


def logs_root() -> Path:
    ensure_shared_seed()
    return reference_path("agente-logs")


def shiguan_index_path() -> Path:
    ensure_shared_seed()
    return reference_path("shiguan-index.jsonl")


def split_lineage(value: str) -> list[str]:
    return [part.strip().lower() for part in value.replace("\\", "/").split("/") if part.strip()]


def lineage_token(office: str) -> str:
    depth, code, _display = OFFICE_CODES.get(office, ("C", re.sub(r"[^A-Z0-9]", "", office.upper())[:3] or "AG", office))
    return f"{depth}{code}"


def lineage_display(office: str) -> str:
    return OFFICE_CODES.get(office, ("C", office.upper(), office))[2]


def next_sequence(court_code: str) -> int:
    root = reference_path("agente-logs")
    if not root.exists():
        return 1
    prefix = f"{court_code}-"
    count = sum(1 for path in root.glob(f"{prefix}*AGLOG-*.log") if path.is_file())
    return count + 1


def build_metadata(args: argparse.Namespace) -> dict[str, object]:
    lineage = split_lineage(args.agent_lineage_path)
    if not lineage:
        lineage = [args.office]
    sequence = int(args.sequence or next_sequence(args.court_code))
    tokens = "-".join(lineage_token(item) for item in lineage)
    log_id = f"{args.court_code}-{tokens}-AGLOG-{sequence:04d}"
    display_parts = [lineage_display(item) for item in lineage]
    short_title = f"{tokens} {display_parts[-1]} #{sequence:04d}"
    return {
        "record_type": "agente_log",
        "court_code": args.court_code,
        "log_id": log_id,
        "log_sequence": sequence,
        "short_title": short_title,
        "agent_id": args.agent_id,
        "parent_agent_id": args.parent_agent_id,
        "office": args.office,
        "agent_depth": max(0, len(lineage) - 1),
        "agent_lineage_path": "/".join(lineage),
        "agent_lineage_display": args.agent_lineage_display or " > ".join(display_parts),
        "terminal_window": "planned",
        "terminal_policy": "auto_visible_then_degrade",
    }


def redact(text: str) -> str:
    text = SENSITIVE_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    return BEARER_RE.sub("Bearer [REDACTED]", text)


def write_log(metadata: dict[str, object], body: str, full_archive: bool) -> Path:
    root = logs_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{metadata['log_id']}.log"
    # Compatibility accepts the historical flag, but ordinary agente logs are
    # always redacted. Raw-secret archiving requires a separate, isolated design
    # and is never enabled by this CLI flag.
    text = redact(body)
    path.write_text(
        "\n".join(
            [
                f"log_id: {metadata['log_id']}",
                f"court_code: {metadata['court_code']}",
                f"agent_lineage_path: {metadata['agent_lineage_path']}",
                f"agent_lineage_display: {metadata['agent_lineage_display']}",
                f"short_title: {metadata['short_title']}",
                "",
                text,
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    return path


def log_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def powershell_quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def release_behavior(agent_status: str) -> dict[str, object]:
    status = agent_status.lower()
    if status in ATTENTION_STATES:
        return {
            "agent_status": status,
            "highlight": "[ATTN]",
            "window_release": "preserve_and_highlight",
            "keep_window": True,
        }
    if status in COMPLETED_STATES:
        return {
            "agent_status": status,
            "highlight": "",
            "window_release": "auto_close_after_log_saved",
            "keep_window": False,
        }
    return {
        "agent_status": status or "running",
        "highlight": "",
        "window_release": "keep_until_release",
        "keep_window": True,
    }


def launch_terminal(
    metadata: dict[str, object],
    log_path: Path,
    dry_run: bool,
    auto_close_seconds: int,
) -> dict[str, object]:
    title = str(metadata["short_title"])
    if metadata.get("highlight"):
        title = f"{metadata['highlight']} {title}"
    command = (
        f"$Host.UI.RawUI.WindowTitle = {powershell_quote(title)}; "
        f"Write-Host {powershell_quote('agente log: ' + str(metadata['log_id']))}; "
        f"Get-Content -LiteralPath {powershell_quote(log_path)}"
    )
    if metadata.get("keep_window", True):
        command += " -Wait"
    else:
        command += f"; Start-Sleep -Seconds {max(0, int(auto_close_seconds))}; exit"
    if dry_run:
        return {"terminal_window": "DRY_RUN", "command": command}
    try:
        if sys.platform == "win32":
            plan = terminal_launch_plan(title, command, keep_open=bool(metadata.get("keep_window", True)))
        else:
            follow = sh_join(["tail", "-f", str(log_path)])
            plan = terminal_launch_plan(title, follow, keep_open=bool(metadata.get("keep_window", True)))
        if not plan.get("available"):
            return {
                "terminal_window": "degraded",
                "error": str(plan.get("reason", "terminal launch unavailable")),
                "command": command if sys.platform == "win32" else str(plan.get("args") or ""),
                "platform": plan.get("platform"),
            }
        popen_kwargs: dict[str, object] = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = int(plan.get("creationflags") or 0)
        subprocess.Popen([str(part) for part in plan["args"]], **popen_kwargs)
        return {"terminal_window": "STARTED", "command": command, "platform": plan.get("platform")}
    except Exception as exc:
        return {"terminal_window": "degraded", "error": str(exc), "command": command}


def merge_agent_facets(entry: dict[str, object], metadata: dict[str, object]) -> None:
    facets = dict(entry.get("facet_dimensions", {}))
    facets["agente谱系分面"] = [
        str(metadata["agent_lineage_path"]),
        str(metadata["agent_lineage_display"]),
        f"depth:{metadata['agent_depth']}",
        f"status:{metadata.get('agent_status', 'running')}",
    ]
    if metadata.get("highlight"):
        facets["agente注意分面"] = [str(metadata["highlight"]), str(metadata.get("agent_status", ""))]
    entry["facet_dimensions"] = facets


def append_shiguan_summary(metadata: dict[str, object], log_path: Path, full_archive: bool, summary: str) -> dict[str, object]:
    agent_facets = {
        "agent_lineage_path": metadata["agent_lineage_path"],
        "agent_lineage_display": metadata["agent_lineage_display"],
        "agent_depth": metadata["agent_depth"],
        "agent_status": metadata.get("agent_status", "running"),
        "window_release": metadata.get("window_release", ""),
    }
    entry = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "record_type": "agente_log",
        "topic": "agente-log",
        "phase": "agente日志",
        "status": "DONE",
        "agent_log_court_code": metadata["court_code"],
        "log_id": metadata["log_id"],
        "summary": redact(summary),
        "evidence": f"log_path={log_path}; sha256={log_hash(log_path)}",
        "source": relative_to_data(log_path),
        "memory_decision": "PROPOSE",
        "keywords": [
            str(metadata["log_id"]),
            str(metadata["agent_id"]),
            str(metadata["agent_lineage_path"]),
            str(metadata["agent_lineage_display"]),
            "agente_log",
        ],
        "key_actions": ["save agente terminal log", "archive agente log summary"],
        "agent_facets": agent_facets,
        "full_log_archived": False,
        "full_log_archive_requested": bool(full_archive),
        "sensitive_data_may_exist": False,
        "redaction_enforced": True,
    }
    entry = enrich_entry(entry)
    merge_agent_facets(entry, metadata)
    index_path = shiguan_index_path()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(shiguan_write_lock_path()):
        with index_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return entry


def _semantic_binding_fields(source: dict[str, object]) -> dict[str, object]:
    fields = (
        "semantic_epoch",
        "charter_sha256",
        "invariant_capsule_sha256",
        "checkpoint_id",
        "dispatch_uid",
        "attempt",
    )
    return {field: source.get(field) for field in fields}


def _structured_result_envelope(
    agent: dict[str, object],
    *,
    status: str,
    summary: str,
    evidence: str,
) -> dict[str, object]:
    return {
        "schema": "court.office.result.v1",
        "task_id": agent["task_id"],
        "semantic_epoch": agent["semantic_epoch"],
        "charter_sha256": agent["charter_sha256"],
        "invariant_capsule_sha256": agent["invariant_capsule_sha256"],
        "checkpoint_id": agent["checkpoint_id"],
        "dispatch_uid": agent["dispatch_uid"],
        "attempt": agent["attempt"],
        "office_instance_id": agent["office_instance_id"],
        "agent_id": agent["agent_id"],
        "role": agent["role"],
        "direct_superior": agent["direct_superior"],
        "worktree": agent["worktree"],
        "write_set_sha256": court_runtime.canonical_json_sha256(agent.get("write_set", [])),
        "status": status,
        "summary": summary,
        "evidence": [evidence],
        "produced_at": court_runtime.now_text(),
    }


def mirror_runtime_event(args: argparse.Namespace) -> dict[str, object]:
    if not args.runtime_task_id or args.runtime_action == "none":
        return {"runtime_mirror": "not_requested"}
    evidence = redact(
        args.runtime_evidence
        or f"{args.runtime_action} agente_terminal:{args.agent_id}"
    )
    task = court_runtime.load_tasks().get(args.runtime_task_id)
    if not isinstance(task, dict):
        raise ValueError(f"runtime task not found: {args.runtime_task_id}")
    start_fields: dict[str, object] = {}
    lifecycle_fields: dict[str, object] = {}
    if args.runtime_action in {"start", "spawn"}:
        wave_id = str(args.runtime_wave_id or "wave-default")
        admissions = task.get("agent_admissions") if isinstance(task, dict) else None
        admission = admissions.get(wave_id) if isinstance(admissions, dict) else None
        route_inputs = admission.get("model_route_inputs") if isinstance(admission, dict) else None
        if (
            not isinstance(admission, dict)
            or admission.get("allowed") is not True
            or not isinstance(route_inputs, dict)
        ):
            raise ValueError(f"runtime admission not found for wave: {wave_id}")
        selected = admission.get("selected_bindings")
        matching = [
            item
            for item in selected or []
            if isinstance(item, dict)
            and str(item.get("role") or "").strip().lower()
            == str(args.runtime_role or args.office).strip().lower()
        ]
        if len(matching) != 1:
            raise ValueError("runtime admission requires one matching instance")
        start_fields = {
            "wave_id": wave_id,
            "instance_id": matching[0].get("instance_id"),
            "dispatch_requested_at": admission.get("dispatch_requested_at"),
            "task_focus": route_inputs.get("task_focus"),
            "complexity": route_inputs.get("complexity"),
            "risk": route_inputs.get("risk"),
            "ambiguity": route_inputs.get("ambiguity"),
            "transport": route_inputs.get("transport"),
            "fork_turns": admission.get("recommended_fork_turns"),
            "context_tokens": admission.get("context_tokens"),
            "deadline_seconds": admission.get("deadline_seconds"),
            "tool_call_budget": admission.get("tool_call_budget"),
            "collaboration_task_name": args.collaboration_task_name,
            "requires_gongjiang": args.requires_gongjiang,
            "skill_requirements_json": args.skill_requirements_json,
            "dispatch_context_packet": court_runtime.public_dispatch_context_packet(
                task, wave_id
            ),
            "context_budget_pool": court_runtime.public_context_budget_pool(task, wave_id),
            "context_result_mode": admission.get("context_result_mode"),
            "context_tool_output_mode": admission.get("context_tool_output_mode"),
            "context_override_source": admission.get("context_override_source"),
            "system_memory_percent": admission.get("context_system_memory_percent", 0.0),
            **_semantic_binding_fields(admission),
        }
    else:
        agents = task.get("agents")
        existing = agents.get(args.agent_id) if isinstance(agents, dict) else None
        if not isinstance(existing, dict):
            raise ValueError(f"runtime agent not found: {args.agent_id}")
        lifecycle_fields = _semantic_binding_fields(existing)
        if args.runtime_action == "finish":
            status = args.agent_status if args.agent_status in {"completed", "failed", "cancelled"} else "failed"
            lifecycle_fields.update(
                result_envelope=_structured_result_envelope(
                    existing,
                    status=status,
                    summary=redact(args.result or args.summary or status),
                    evidence=evidence,
                ),
                result_envelope_file=None,
            )
    namespace_fields: dict[str, object] = {
        "task_id": args.runtime_task_id,
        "agent_id": args.agent_id,
        "role": args.runtime_role or args.office,
        "scope": redact(args.scope or args.summary),
        "actor": args.actor,
        "evidence": evidence,
        "note": redact(args.note or "agente_terminal mirror"),
        "result": "" if args.runtime_action == "finish" else redact(
            args.result or str(args.agent_status or "")
        ),
        "status": args.agent_status if args.agent_status in {"completed", "failed", "cancelled"} else "failed",
    }
    namespace_fields.update(start_fields)
    namespace_fields.update(lifecycle_fields)
    namespace = argparse.Namespace(**namespace_fields)
    if args.runtime_action in {"start", "spawn"}:
        result = court_runtime.agent_start(namespace)
    elif args.runtime_action == "heartbeat":
        result = court_runtime.agent_heartbeat(namespace)
    elif args.runtime_action == "finish":
        result = court_runtime.agent_finish(namespace)
    elif args.runtime_action == "close":
        result = court_runtime.agent_close(namespace)
    else:
        raise ValueError(f"unknown runtime action: {args.runtime_action}")
    return {
        "runtime_mirror": args.runtime_action,
        "runtime_task_id": args.runtime_task_id,
        "runtime_event": result.event,
    }


def validate_runtime_start_binding(args: argparse.Namespace) -> None:
    if args.runtime_action not in {"start", "spawn"}:
        return
    if not args.runtime_task_id:
        raise ValueError("runtime-task-id is required for start/spawn")
    collaboration_task_name = str(args.collaboration_task_name or "").strip()
    requirements_text = str(args.skill_requirements_json or "").strip()
    if not collaboration_task_name:
        raise ValueError("collaboration-task-name is required for start/spawn")
    if not requirements_text:
        raise ValueError("skill-requirements-json is required for start/spawn")
    try:
        requirements = json.loads(requirements_text)
    except json.JSONDecodeError as exc:
        raise ValueError("skill requirements JSON is invalid") from exc
    if not isinstance(requirements, list):
        raise ValueError("skill requirements JSON must contain an array")
    court_runtime.build_office_assignment_binding(
        role_key=str(args.runtime_role or args.office).strip(),
        collaboration_task_name=collaboration_task_name,
        court_agent_id=str(args.agent_id).strip(),
        requires_gongjiang=bool(args.requires_gongjiang),
        skill_requirements=requirements,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--court-code", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--office", required=True)
    parser.add_argument("--agent-lineage-path", required=True)
    parser.add_argument("--agent-lineage-display", default="")
    parser.add_argument("--parent-agent-id", default="")
    parser.add_argument("--sequence", type=int, default=0)
    parser.add_argument("--body", default="")
    parser.add_argument("--body-file", default="")
    parser.add_argument("--summary", default="agente terminal log saved")
    parser.add_argument(
        "--full-log-archive",
        action="store_true",
        help="Deprecated compatibility flag; ordinary logs remain redacted.",
    )
    parser.add_argument(
        "--agent-status",
        default="running",
        choices=["created", "running", "completed", "closed", "blocked", "failed", "stale", "orphaned", "cancelled"],
    )
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--auto-close-seconds", type=int, default=3)
    parser.add_argument("--runtime-task-id", default="")
    parser.add_argument("--runtime-wave-id", default="wave-default")
    parser.add_argument(
        "--runtime-action",
        default="none",
        choices=["none", "spawn", "start", "heartbeat", "finish", "close"],
    )
    parser.add_argument("--runtime-role", default="")
    parser.add_argument("--collaboration-task-name", default="")
    parser.add_argument("--requires-gongjiang", action="store_true")
    parser.add_argument("--skill-requirements-json", default="")
    parser.add_argument("--runtime-evidence", default="")
    parser.add_argument("--scope", default="")
    parser.add_argument("--actor", default="shangshu", choices=sorted(court_runtime.OFFICES))
    parser.add_argument("--result", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args()

    validate_runtime_start_binding(args)

    body = args.body
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8", errors="replace")
    metadata = build_metadata(args)
    metadata.update(release_behavior(args.agent_status))
    metadata["redaction_enforced"] = True
    metadata["full_log_archive_requested"] = bool(args.full_log_archive)
    runtime_mirror = mirror_runtime_event(args)
    log_path = write_log(metadata, body or "status: created", args.full_log_archive)
    terminal = (
        launch_terminal(metadata, log_path, args.dry_run, args.auto_close_seconds)
        if args.launch
        else {"terminal_window": "not_requested"}
    )
    metadata.update(terminal)
    entry = append_shiguan_summary(metadata, log_path, args.full_log_archive, args.summary)
    output = {
        "metadata": metadata,
        "log_path": str(log_path),
        "sha256": log_hash(log_path),
        "runtime_mirror": runtime_mirror,
        "shiguan_entry": entry,
    }
    if args.format == "json":
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{metadata['log_id']} {log_path} {metadata.get('terminal_window')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



