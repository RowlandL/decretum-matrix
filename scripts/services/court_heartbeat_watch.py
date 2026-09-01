"""Watch court_runtime tasks and agent lifecycle records for stale heartbeats."""

from __future__ import annotations

# A+B layering: real module lives in scripts/services/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
from datetime import datetime
import json
import sys

sys.dont_write_bytecode = True

import court_runtime


BASELINE_SECONDS = {
    "short": 300,
    "normal": 900,
    "long": 1800,
    "watch": 3600,
}


TERMINAL_STATES = {"Done", "Cancelled", "Rejected"}
TERMINAL_AGENT_STATES = {"completed", "failed", "cancelled", "closed"}


def parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def age_seconds(value: object, now: datetime) -> float | None:
    parsed = parse_time(value)
    if not parsed:
        return None
    return max(0.0, (now - parsed).total_seconds())


def infer_expected_duration(text: str) -> str:
    value = text.lower()
    if any(token in value for token in ("watch", "daemon", "serve", "tail", "monitor", "守护", "监听", "服务")):
        return "watch"
    if any(token in value for token in ("batch", "long", "render", "大量", "批处理", "长任务")):
        return "long"
    if any(token in value for token in ("quick", "smoke", "probe", "短", "快速", "自测")):
        return "short"
    return "normal"


def threshold_for(record: dict[str, object], default_seconds: int) -> tuple[int, str]:
    expected = str(record.get("expected_duration") or "").strip().lower()
    if expected not in BASELINE_SECONDS:
        expected = infer_expected_duration(
            " ".join(str(record.get(key, "")) for key in ("title", "scope", "last_evidence", "charter"))
        )
    return max(1, int(record.get("stale_seconds") or BASELINE_SECONDS.get(expected, default_seconds))), expected


def mark_agent_stale(task_id: str, agent_id: str, reason: str) -> None:
    with court_runtime.runtime_lock():
        tasks = court_runtime.load_tasks()
        task = tasks.get(task_id)
        if not task:
            return
        agents = task.get("agents")
        if not isinstance(agents, dict):
            return
        agent = agents.get(agent_id)
        if not isinstance(agent, dict):
            return
        agent["status"] = "stale"
        agent["stale_reason"] = reason
        agent["updated_at"] = court_runtime.now_text()
        task["last_evidence"] = f"agent {agent_id} stale: {reason}"
        tasks[task_id] = task
        court_runtime.write_tasks(tasks)
        event = court_runtime.make_event(
            task,
            "agent_stale",
            "running",
            str(task.get("state")),
            "menxia",
            reason,
            "heartbeat watcher",
        )
        event["agent_id"] = agent_id
        court_runtime.append_event(event)


def watch(default_stale_seconds: int, mark_stale: bool = False) -> dict[str, object]:
    now = datetime.now().astimezone()
    tasks = [court_runtime.normalize_task(task) for task in court_runtime.load_tasks().values()]
    stale_tasks: list[dict[str, object]] = []
    stale_agents: list[dict[str, object]] = []
    for task in tasks:
        if task.get("state") in TERMINAL_STATES:
            continue
        task_age = age_seconds(task.get("updated_at"), now)
        threshold, expected = threshold_for(task, default_stale_seconds)
        if task_age is not None and task_age > threshold:
            stale_tasks.append(
                {
                    "task_id": task.get("task_id"),
                    "state": task.get("state"),
                    "heartbeat": task.get("heartbeat"),
                    "age_seconds": round(task_age, 1),
                    "stale_threshold_seconds": threshold,
                    "expected_duration": expected,
                    "stale_reason": f"task heartbeat age {round(task_age, 1)}s > threshold {threshold}s",
                    "highlight": "[ATTN]",
                }
            )
        agents = task.get("agents", {})
        if not isinstance(agents, dict):
            continue
        for agent_id, agent in agents.items():
            if not isinstance(agent, dict) or agent.get("status") in TERMINAL_AGENT_STATES:
                continue
            agent_age = age_seconds(agent.get("last_heartbeat"), now)
            threshold, expected = threshold_for(agent, default_stale_seconds)
            if agent_age is not None and agent_age > threshold:
                reason = f"agent heartbeat age {round(agent_age, 1)}s > threshold {threshold}s"
                stale_agents.append(
                    {
                        "task_id": task.get("task_id"),
                        "agent_id": agent_id,
                        "role": agent.get("role"),
                        "status": agent.get("status"),
                        "age_seconds": round(agent_age, 1),
                        "stale_threshold_seconds": threshold,
                        "expected_duration": expected,
                        "stale_reason": reason,
                        "highlight": "[ATTN]",
                    }
                )
                if mark_stale:
                    mark_agent_stale(str(task.get("task_id")), str(agent_id), reason)
    return {
        "kind": "court_heartbeat_watch",
        "generated_at": court_runtime.now_text(),
        "default_stale_seconds": default_stale_seconds,
        "mark_stale": mark_stale,
        "active_task_count": sum(1 for task in tasks if task.get("state") not in TERMINAL_STATES),
        "stale_tasks": stale_tasks,
        "stale_agents": stale_agents,
        "ok": not stale_tasks and not stale_agents,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stale-seconds", type=int, default=900)
    parser.add_argument("--mark-stale", action="store_true")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args()
    payload = watch(args.stale_seconds, args.mark_stale)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"ok={payload['ok']} stale_tasks={len(payload['stale_tasks'])} stale_agents={len(payload['stale_agents'])}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())



