"""Archive a court_runtime task snapshot into the Shiguan record."""

from __future__ import annotations

import argparse
import subprocess
import sys

sys.dont_write_bytecode = True

import court_runtime


def compact_events(task_id: str, limit: int) -> str:
    events = court_runtime.read_events(limit=limit, task_id=task_id)
    if not events:
        return "no runtime events"
    parts = []
    for event in events:
        parts.append(
            f"{event.get('time')} {event.get('action')} "
            f"{event.get('from_state')}->{event.get('to_state')} by {event.get('actor')}"
        )
    return "; ".join(parts)


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
    topic = args.topic or str(task.get("title") or args.task_id)
    status = args.status or str(task.get("state") or "UNKNOWN")
    events = compact_events(args.task_id, args.event_limit)
    summary = (
        f"runtime task {args.task_id}: state={task.get('state')}; "
        f"owner={task.get('owner')}; heartbeat={task.get('heartbeat')}; "
        f"title={task.get('title')}"
    )
    evidence = (
        f"runtime_schema_version={task.get('runtime_schema_version')}; "
        f"last_evidence={task.get('last_evidence')}; events={events}"
    )
    memory_content = args.memory_content or (
        f"{args.task_id} is tracked by court_runtime.py and archived through archive_runtime_task.py"
    )
    memory_reason = args.memory_reason or "runtime-to-Shiguan bridge preserves audit continuity"
    command = [
        sys.executable,
        str(court_runtime.skill_root() / "scripts" / "archive_checkpoint.py"),
        "--topic",
        topic,
        "--phase",
        args.phase,
        "--status",
        status,
        "--summary",
        summary,
        "--evidence",
        evidence,
        "--next",
        args.next or "continue according to current court state",
        "--memory-decision",
        args.memory_decision,
        "--memory-content",
        memory_content,
        "--memory-reason",
        memory_reason,
        "--keywords",
        f"{args.task_id},court runtime,Shiguan bridge,audit trail",
        "--key-actions",
        "archive runtime task,connect runtime ledger to Shiguan",
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
