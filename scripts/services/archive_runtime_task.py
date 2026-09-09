"""Archive a court_runtime task snapshot into the Shiguan record."""

from __future__ import annotations

# A+B layering: real module lives in scripts/services/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
from copy import deepcopy
import json
import subprocess
import sys
from urllib.parse import quote

sys.dont_write_bytecode = True
import court_runtime
from court_file_lock import file_lock
from court_case_binding import case_reference


def validate_child_trace_summaries(records: object) -> dict[str, object]:
    required = "time event behavior_summary task_id dispatch_uid office_instance_id role direct_superior status evidence_pointer".split()
    rejected = {"ok": False, "instance_ids": []}
    if not isinstance(records, list) or not records:
        return rejected
    groups = {}
    for record in records:
        values = [record.get(key) for key in required] if isinstance(record, dict) else []
        tail = record.get("next") or record.get("release_reason") if isinstance(record, dict) else None
        if not all(isinstance(value, str) and 0 < len(value) <= 1024 for value in values + [tail]):
            return rejected
        groups.setdefault(record["office_instance_id"], []).append(record)
    lifecycle = ["start", "key_action", "finish", "release"]
    stable = ("task_id", "dispatch_uid", "role", "direct_superior")
    ok = len({record["task_id"] for record in records}) == 1
    ok &= all([item["event"] for item in events] == lifecycle
              and len({tuple(item[key] for key in stable) for item in events}) == 1
              for events in groups.values())
    return {"ok": bool(ok), "instance_ids": sorted(groups) if ok else []}


def _trace_text(value: object) -> str:
    text = " ".join(str(value).split())
    secret = ("token", "secret", "password", "passwd", "api-key", "api_key", "api key",
              "bearer ", "authorization", "cookie")
    if any(key in text.casefold() for key in secret):
        return "[redacted]"
    return text.encode("utf-8")[:64].decode("utf-8", "ignore")


def _bounded(rendered: str, receipt: str = "") -> str:
    return rendered if len(rendered.encode("utf-8")) <= 4096 else "trace projection blocked: byte limit " + receipt


def _compact_child_events(events: list[dict[str, object]]) -> str:
    groups = {}
    for event in events:
        groups.setdefault(event["office_instance_id"], []).append(event)
    parts = []
    for instance, records in sorted(groups.items()):
        first = records[0]
        static = (first["task_id"], first["dispatch_uid"], instance, first["role"], first["direct_superior"])
        actions = []
        for record in records:
            action = (record["time"], record["event"], record["status"], record["behavior_summary"],
                      record["evidence_pointer"],
                      record.get("next") or record.get("release_reason"))
            actions.append(" ".join(_trace_text(value) for value in action))
        parts.append(" ".join(_trace_text(value) for value in static) + " | " + " > ".join(actions))
    first = events[0]
    receipt = " ".join(_trace_text(value) for value in
                       (first["task_id"], ",".join(sorted(groups)), first["evidence_pointer"]))
    return _bounded("; ".join(parts), receipt)


def compact_events(task_id: str, limit: int,
                   event_history: list[dict[str, object]] | None = None) -> str:
    history = event_history or []
    if not history:
        return "no runtime events"
    children = [event for event in history if event.get("office_instance_id")]
    selected = []
    for event in reversed(children):
        instance = event.get("office_instance_id")
        if instance not in selected:
            selected.append(instance)
    selected = selected[:max(1, limit // 4)]
    children = [event for event in children if event.get("office_instance_id") in selected]
    events = [event for event in history if not event.get("office_instance_id")][-max(1, limit):]
    parts = ([(_compact_child_events(children)
               if all(event.get("task_id") == task_id for event in children)
               and validate_child_trace_summaries(children)["ok"] else "invalid child trace")]
             if children else [])
    for event in events:
        action = event.get("event") or event.get("action")
        transition = f"{event.get('from_state')}->{event.get('to_state')} by {event.get('actor')}"
        parts.append(" ".join(_trace_text(value) for value in (event.get("time"), action, transition)))
    receipt = [task_id, *selected]
    if children:
        receipt.append(children[0].get("evidence_pointer"))
    return _bounded(f"{task_id}: " + "; ".join(parts), " ".join(_trace_text(value) for value in receipt))


def runtime_summary(
    task: dict[str, object],
    event_history: list[dict[str, object]] | None = None,
) -> str:
    completion = court_runtime.completion_projection(task, event_history)
    marker = "; VERIFIED_COMPLETE" if completion["verified"] else ""
    return (
        f"runtime task {task.get('task_id')}: state={task.get('state')}; "
        f"owner={task.get('owner')}; heartbeat={task.get('heartbeat')}; "
        f"completion_status={completion['status']}; "
        f"completion_verified={str(completion['verified']).lower()}; "
        f"title={task.get('title')}{marker}"
    )


def runtime_evidence(
    task: dict[str, object],
    event_limit: int,
    event_history: list[dict[str, object]] | None = None,
) -> str:
    return (
        f"runtime_schema_version={task.get('runtime_schema_version')}; "
        f"charter_revision={task.get('charter_revision')}; "
        f"last_evidence={task.get('last_evidence')}; "
        f"events={compact_events(str(task.get('task_id') or ''), event_limit, event_history)}"
    )


def build_archive_command(
    task: dict[str, object],
    args: argparse.Namespace,
    *,
    result_json_path: Path | None = None,
) -> list[str]:
    from court_case_binding import (
        canonical_case_binding_json,
        validate_task_case_binding,
    )

    case_binding = validate_task_case_binding(task, require_decree=True)
    event_history = court_runtime.events_for_task(task.get("task_id"), limit=None)
    projection = court_runtime.completion_projection(task, event_history)
    binding = task.get("assessment_binding")
    assessment_gate = binding.get("gate") if isinstance(binding, dict) else None
    residual_gaps = (
        list(binding["residual_gaps"])
        if isinstance(binding, dict) and isinstance(binding.get("residual_gaps"), list)
        else []
    )
    residual_gaps_json = json.dumps(
        residual_gaps, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    archive_status = str(
        args.status
        or (
            projection["status"]
            if task.get("state") == "Done"
            else (
                assessment_gate
                if assessment_gate in {"PASSED", "PASSED_WITH_CONCERNS"}
                else projection["status"]
            )
        )
    )
    memory_content = args.memory_content or (
        f"{args.task_id} is tracked by court_runtime.py and archived through archive_runtime_task.py"
    )
    memory_reason = args.memory_reason or "runtime-to-Shiguan bridge preserves audit continuity"
    command = [
        sys.executable,
        "-B",
        str(court_runtime.skill_root() / "scripts" / "archive_checkpoint.py"),
        "--topic", args.topic or str(task.get("title") or args.task_id),
        "--phase", args.phase,
        "--status", archive_status,
        "--summary", runtime_summary(task, event_history),
        "--evidence", runtime_evidence(task, args.event_limit, event_history),
        "--next", args.next or "continue according to current court state",
        "--memory-decision", args.memory_decision,
        "--memory-content", memory_content,
        "--memory-reason", memory_reason,
        "--keywords", f"{args.task_id},court runtime,Shiguan bridge,audit trail",
        "--key-actions", "archive runtime task,connect runtime ledger to Shiguan",
        "--residual-gaps-json", residual_gaps_json,
        "--format", "json",
    ]
    if result_json_path is not None:
        command.extend(("--result-json", str(result_json_path)))
    if case_binding is not None:
        command.extend(
            (
                "--session-id",
                str(case_binding["session_id"]),
                "--case-binding-json",
                canonical_case_binding_json(case_binding),
            )
        )
    return command


def _record_args(
    task: dict[str, object],
    producer_receipt: dict[str, object],
) -> argparse.Namespace:
    return argparse.Namespace(
        task_id=task["task_id"],
        expected_revision=task["charter_revision"],
        case_ref=case_reference(task),
        archive_receipt=producer_receipt,
        archive_receipt_file=None,
        actor="shiguan",
        evidence="archive_runtime_task verified producer receipt",
        note="record Shiguan runtime checkpoint",
        session_id=task.get("session_id", ""),
        case_binding=deepcopy(task.get("case_binding"))
        if isinstance(task.get("case_binding"), dict)
        else None,
    )


def _runtime_receipt(task: dict[str, object]) -> dict[str, object]:
    checkpoint = task.get("shiguan_checkpoint")
    binding = task.get("assessment_binding")
    if not isinstance(checkpoint, dict) or not isinstance(binding, dict):
        raise ValueError("archive_runtime_checkpoint_missing")
    receipt: dict[str, object] = {
        "schema": "court.shiguan_checkpoint_receipt.v1",
        "receipt_id": checkpoint["receipt_id"],
        "task_id": task["task_id"],
        "charter_revision": task["charter_revision"],
        "case_ref": case_reference(task),
        "assessment_ref": binding["assessment_ref"],
        "record_ref": checkpoint["record_ref"],
        "archive_path": checkpoint["archive_path"],
        "recorded_at": checkpoint["recorded_at"],
    }
    if binding.get("gate") == "PASSED_WITH_CONCERNS":
        receipt.update(
            residual_gaps=binding["residual_gaps"],
        )
    case_binding = task.get("case_binding")
    if isinstance(case_binding, dict):
        receipt.update(
            session_id=case_binding["session_id"],
            court_code=case_binding["court_code"],
            charter_revision=case_binding["charter_revision"],
        )
    return receipt


def _producer_receipt_from_stdout(stdout: str) -> dict[str, object]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("archive_runtime_producer_json_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("archive_runtime_producer_json_invalid")
    return value


def _receipt_cache_path(preflight: dict[str, object]) -> Path:
    task_id = preflight.get("task_id")
    assessment_ref = preflight.get("assessment_ref")
    revision = preflight.get("charter_revision")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("archive_runtime_cache_task_id_invalid")
    if not isinstance(assessment_ref, str) or not assessment_ref.strip():
        raise ValueError("archive_runtime_cache_assessment_ref_invalid")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ValueError("archive_runtime_cache_charter_revision_invalid")

    def reference_component(value: str, *, label: str) -> str:
        encoded = quote(value.strip(), safe="-._~")
        if encoded in {"", ".", ".."} or len(encoded) > 128:
            raise ValueError(f"archive_runtime_cache_{label}_invalid")
        return encoded

    assessment_component = reference_component(
        assessment_ref,
        label="assessment_ref",
    )
    return (
        court_runtime.runtime_root()
        / "archive-runtime-receipts"
        / "reference-v1"
        / reference_component(task_id, label="task_id")
        / f"r{revision}"
        / f"{assessment_component}.json"
    )


def _cached_producer_receipt(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("archive_runtime_receipt_cache_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("archive_runtime_receipt_cache_invalid")
    return value


def archive_and_record_task(args: argparse.Namespace) -> dict[str, object]:
    task = court_runtime.load_tasks().get(args.task_id)
    if not isinstance(task, dict):
        raise ValueError(f"task not found: {args.task_id}")
    checkpoint = task.get("shiguan_checkpoint")
    if str(task.get("state") or "") == "ShiguanRecorded":
        if not isinstance(checkpoint, dict) or not isinstance(
            checkpoint.get("producer_receipt"), dict
        ):
            raise ValueError("archive_runtime_replay_receipt_missing")
        recorded = court_runtime.record_shiguan_task(
            _record_args(task, dict(checkpoint["producer_receipt"]))
        )
        return {
            "status": "REPLAYED",
            "producer_receipt": checkpoint["producer_receipt"],
            "runtime_receipt": _runtime_receipt(recorded.task),
            "event": recorded.event,
        }

    preflight = court_runtime.record_shiguan_preflight(
        _record_args(task, {"preflight": "not-used"})
    )
    cache_path = _receipt_cache_path(preflight)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(cache_path.with_suffix(".lock"), timeout=30.0):
        if cache_path.is_file():
            producer_receipt = _cached_producer_receipt(cache_path)
        else:
            command = build_archive_command(
                task,
                args,
                result_json_path=cache_path,
            )
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "archive_runtime_producer_failed:"
                    + (result.stderr.strip() or result.stdout.strip() or str(result.returncode))
                )
            producer_receipt = _producer_receipt_from_stdout(result.stdout)
            cached_receipt = _cached_producer_receipt(cache_path)
            if cached_receipt != producer_receipt:
                raise ValueError("archive_runtime_receipt_cache_mismatch")
        recorded = court_runtime.record_shiguan_task(
            _record_args(task, producer_receipt)
        )
    return {
        "status": "COMMITTED",
        "producer_receipt": producer_receipt,
        "runtime_receipt": _runtime_receipt(recorded.task),
        "event": recorded.event,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--topic", default="")
    parser.add_argument("--phase", default="运行态归档")
    parser.add_argument("--status", default="")
    parser.add_argument("--next", default="")
    parser.add_argument("--memory-decision", default="PROPOSE")
    parser.add_argument("--memory-content", default="")
    parser.add_argument("--memory-reason", default="")
    parser.add_argument("--event-limit", type=int, default=12)
    args = parser.parse_args()

    try:
        result = archive_and_record_task(args)
    except (RuntimeError, ValueError) as exc:
        print(f"ARCHIVE_RUNTIME_ERROR {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
