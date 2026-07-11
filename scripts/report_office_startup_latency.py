"""Report segmented ordinary-office startup latency without inventing timestamps."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Any

sys.dont_write_bytecode = True


TIMESTAMP_FIELDS = (
    "dispatch_requested_at",
    "host_session_started_at",
    "preload_ack_at",
    "first_office_report_at",
    "finished_at",
)
SEGMENT_FIELDS = {
    "host_spawn_queue_ms": ("dispatch_requested_at", "host_session_started_at"),
    "preload_ms": ("host_session_started_at", "preload_ack_at"),
    "first_report_ms": ("preload_ack_at", "first_office_report_at"),
    "execution_ms": ("preload_ack_at", "finished_at"),
}
HIGH_THRESHOLDS_MS = {
    "host_spawn_queue_ms": 10_000,
    "preload_ms": 5_000,
    "first_report_ms": 10_000,
    "execution_ms": 30_000,
}
LEGACY_FIXTURES: dict[str, dict[str, Any]] = {
    "CCR-20260710-183747-AGENT-AUDIT": {
        "role": "xingbu",
        "dispatch_to_start_ms": 43_601,
        "execution_ms": 20_504,
        "topology": "ordinary_super",
        "fork_turns": "none",
        "supercc_show_delay": "NOT_APPLICABLE",
    }
}


def parse_timestamp(value: object) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def segment_milliseconds(record: dict[str, Any], start_field: str, end_field: str) -> int | str:
    start = parse_timestamp(record.get(start_field))
    end = parse_timestamp(record.get(end_field))
    if start is None or end is None:
        return "unavailable"
    milliseconds = round((end - start).total_seconds() * 1000)
    return milliseconds if milliseconds >= 0 else "invalid"


def classify_segments(segments: dict[str, int | str]) -> list[dict[str, str]]:
    rules = {
        "host_spawn_queue_ms": (
            "host_or_provider_startup_queue_high",
            "host session/model/provider startup; do not attribute to the office dossier",
        ),
        "preload_ms": (
            "office_preload_high",
            "profile/dossier/SKILL loading or hash validation",
        ),
        "first_report_ms": (
            "first_office_report_high",
            "task understanding or first bounded tool/report work",
        ),
        "execution_ms": (
            "office_execution_high",
            "actual office workload or execution stall",
        ),
    }
    findings: list[dict[str, str]] = []
    for name, threshold in HIGH_THRESHOLDS_MS.items():
        value = segments.get(name)
        if isinstance(value, int) and value >= threshold:
            code, attribution = rules[name]
            findings.append({"segment": name, "classification": code, "attribution": attribution})
    if not findings and all(isinstance(value, int) for value in segments.values()):
        findings.append(
            {
                "segment": "all",
                "classification": "within_default_thresholds",
                "attribution": "no high-latency segment detected",
            }
        )
    return findings


def build_agent_latency_report(record: dict[str, Any]) -> dict[str, Any]:
    segments = {
        name: segment_milliseconds(record, start_field, end_field)
        for name, (start_field, end_field) in SEGMENT_FIELDS.items()
    }
    missing = [field for field in TIMESTAMP_FIELDS if parse_timestamp(record.get(field)) is None]
    invalid_segments = [name for name, value in segments.items() if value == "invalid"]
    status = "COMPLETE" if not missing and not invalid_segments else "PARTIAL"
    return {
        "agent_id": record.get("agent_id"),
        "role": record.get("role"),
        "status": status,
        "timestamps": {field: record.get(field) or "unavailable" for field in TIMESTAMP_FIELDS},
        "segments": segments,
        "missing_timestamps": missing,
        "invalid_segments": invalid_segments,
        "classifications": classify_segments(segments),
        "policy": "missing timestamps stay unavailable; no zero-fill and no presentation-delay inference",
    }


def legacy_fixture_report(task_id: str) -> dict[str, Any]:
    fixture = LEGACY_FIXTURES.get(task_id)
    if fixture is None:
        raise KeyError(task_id)
    return {
        "kind": "court_office_startup_latency",
        "task_id": task_id,
        "status": "PARTIAL",
        "source": "archived_anonymous_fixture",
        "legacy_evidence": dict(fixture),
        "segments": {name: "unavailable" for name in SEGMENT_FIELDS},
        "classifications": [
            {
                "classification": "legacy_combined_startup_latency_unattributed",
                "attribution": "dispatch-to-start predates host-session/preload segmentation; ordinary super show delay is not applicable",
            }
        ],
        "policy": "preserve archived values but do not fabricate missing timestamps or assign presentation-delay causality",
    }


def task_latency_report(task_id: str) -> dict[str, Any]:
    if task_id in LEGACY_FIXTURES:
        return legacy_fixture_report(task_id)
    from court_runtime import load_tasks  # Imported lazily to avoid circular self-tests.

    task = load_tasks().get(task_id)
    if not isinstance(task, dict):
        return {
            "kind": "court_office_startup_latency",
            "task_id": task_id,
            "status": "NOT_FOUND",
            "agents": [],
        }
    agents = task.get("agents")
    rows = [
        build_agent_latency_report(dict(agent))
        for agent in (agents.values() if isinstance(agents, dict) else [])
        if isinstance(agent, dict)
    ]
    if not rows:
        status = "PARTIAL"
    elif all(row["status"] == "COMPLETE" for row in rows):
        status = "COMPLETE"
    else:
        status = "PARTIAL"
    return {
        "kind": "court_office_startup_latency",
        "task_id": task_id,
        "task_state": task.get("state"),
        "status": status,
        "agents": rows,
        "policy": "segment host queue, preload, first report, and execution; missing timestamps remain unavailable",
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        f"task_id: {payload.get('task_id')}",
        f"status: {payload.get('status')}",
    ]
    for row in payload.get("agents", []):
        lines.append(f"{row.get('agent_id')} role={row.get('role')} status={row.get('status')} segments={row.get('segments')}")
    if payload.get("legacy_evidence"):
        lines.append(f"legacy_evidence: {payload['legacy_evidence']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)
    payload = task_latency_report(args.task_id)
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(payload))
    return 2 if payload.get("status") == "NOT_FOUND" else 0


if __name__ == "__main__":
    raise SystemExit(main())
