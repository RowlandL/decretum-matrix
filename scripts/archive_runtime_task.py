"""Archive a court_runtime task snapshot into the Shiguan record."""

from __future__ import annotations

import argparse
import subprocess
import sys

sys.dont_write_bytecode = True
import court_runtime


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


def build_archive_command(task: dict[str, object], args: argparse.Namespace) -> list[str]:
    event_history = court_runtime.events_for_task(task.get("task_id"), limit=None)
    projection = court_runtime.completion_projection(task, event_history)
    memory_content = args.memory_content or (
        f"{args.task_id} is tracked by court_runtime.py and archived through archive_runtime_task.py"
    )
    memory_reason = args.memory_reason or "runtime-to-Shiguan bridge preserves audit continuity"
    return [
        sys.executable,
        str(court_runtime.skill_root() / "scripts" / "archive_checkpoint.py"),
        "--topic", args.topic or str(task.get("title") or args.task_id),
        "--phase", args.phase,
        "--status", str(projection["status"]),
        "--summary", runtime_summary(task, event_history),
        "--evidence", runtime_evidence(task, args.event_limit, event_history),
        "--next", args.next or "continue according to current court state",
        "--memory-decision", args.memory_decision,
        "--memory-content", memory_content,
        "--memory-reason", memory_reason,
        "--keywords", f"{args.task_id},court runtime,Shiguan bridge,audit trail",
        "--key-actions", "archive runtime task,connect runtime ledger to Shiguan",
    ]


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

    task = court_runtime.load_tasks().get(args.task_id)
    if not task:
        print(f"RUNTIME_TASK_NOT_FOUND {args.task_id}", file=sys.stderr)
        return 2
    task = court_runtime.normalize_task(task)
    command = build_archive_command(task, args)
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
