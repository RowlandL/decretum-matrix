"""Archive a court_runtime task snapshot into the Shiguan record."""

from __future__ import annotations

import argparse
import subprocess
import sys

sys.dont_write_bytecode = True

import court_runtime


def compact_events(
    task_id: str,
    limit: int,
    event_history: list[dict[str, object]] | None = None,
) -> str:
    events = event_history if event_history is not None else []
    events = events[-max(1, limit):]
    if not events:
        return "no runtime events"
    parts = []
    for event in events:
        parts.append(
            f"{event.get('time')} {event.get('action')} "
            f"{event.get('from_state')}->{event.get('to_state')} by {event.get('actor')}"
        )
    return "; ".join(parts)


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
