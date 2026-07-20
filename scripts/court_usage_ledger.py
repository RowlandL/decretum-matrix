"""Estimate and record decree-level token/time usage for /court work."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
import re
import sys

sys.dont_write_bytecode = True
from pathlib import Path
from typing import Any

from court_file_lock import file_lock, shiguan_write_lock_path
from shiguan_paths import ensure_shared_seed, reference_path


SOURCES = {"provider_reported", "agent_reported", "estimated_fallback", "unavailable"}
AUTHORITIES = {"approval", "autonomous", "super"}
BEHAVIORS = {"serial", "parallel"}
RUNTIMES = {"native", "superCC"}


def now_text() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def runtime_root() -> Path:
    configured = os.environ.get("COURT_RUNTIME_ROOT")
    if configured:
        return Path(configured)
    return reference_path("court-runtime")


def ledger_path() -> Path:
    return runtime_root() / "usage-ledger.jsonl"


def ledger_lock_path() -> Path:
    configured = os.environ.get("COURT_RUNTIME_ROOT")
    if configured:
        return Path(configured) / "usage-ledger.lock"
    return shiguan_write_lock_path()


def split_values(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,;，；\s]+", value) if item.strip()]


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    asciiish = sum(1 for char in text if ord(char) < 128 and not char.isspace())
    other = max(0, len(text) - cjk - asciiish)
    return max(1, math.ceil(cjk * 1.15 + asciiish / 4.0 + other / 2.0))


def write_event(event: dict[str, Any]) -> None:
    line = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
    with file_lock(ledger_lock_path()):
        if not os.environ.get("COURT_RUNTIME_ROOT"):
            ensure_shared_seed()
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        needs_newline = False
        if path.exists() and path.stat().st_size:
            with path.open("rb") as existing:
                existing.seek(-1, os.SEEK_END)
                needs_newline = existing.read(1) != b"\n"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            if needs_newline:
                handle.write("\n")
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())


def read_events(task_id: str = "") -> list[dict[str, Any]]:
    path = ledger_path()
    lock_path = ledger_lock_path()
    if lock_path.exists():
        with file_lock(lock_path):
            if not path.exists():
                return []
            text = path.read_text(encoding="utf-8", errors="replace")
    else:
        # Legacy ledgers may predate the persistent lock marker. Preserve
        # read-only behavior rather than creating one merely for a summary.
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if task_id and str(event.get("task_id")) != task_id:
            continue
        events.append(event)
    return events


def build_estimate(args: argparse.Namespace) -> dict[str, Any]:
    roles = split_values(args.roles)
    office_count = max(int(args.office_count or 0), len(roles))
    subagent_count = max(0, int(args.subagent_count or 0))
    expected_tool_calls = max(0, int(args.expected_tool_calls or 0))
    request_tokens = estimate_text_tokens(args.decree)
    context_tokens = max(0, int(args.context_tokens or 0))
    authority = args.authority
    behavior = args.behavior
    runtime = args.runtime

    input_expected = request_tokens + context_tokens + office_count * 500 + subagent_count * 650
    output_expected = max(250, 350 + expected_tool_calls * 250 + office_count * 350 + subagent_count * 400)
    if runtime == "superCC":
        input_expected += 1200
        output_expected += 600
    total_expected = input_expected + output_expected

    minutes_expected = 4.0 + expected_tool_calls * 1.5 + office_count * 1.5 + subagent_count * 2.0
    if runtime == "superCC":
        minutes_expected += 5.0
    if behavior == "parallel":
        minutes_expected += max(1.0, subagent_count * 0.75)

    return {
        "kind": "estimate",
        "recorded_at": now_text(),
        "task_id": args.task_id,
        "authority": authority,
        "behavior": behavior,
        "runtime": runtime,
        "roles": roles,
        "office_count": office_count,
        "subagent_count": subagent_count,
        "expected_tool_calls": expected_tool_calls,
        "source": "heuristic",
        "precision": "estimate",
        "request_tokens_estimated": request_tokens,
        "context_tokens_estimated": context_tokens,
        "token_estimate": {
            "input_tokens": input_expected,
            "output_tokens": output_expected,
            "total_tokens": total_expected,
            "range_low": max(1, math.floor(total_expected * 0.7)),
            "range_high": max(1, math.ceil(total_expected * 1.6)),
        },
        "time_estimate": {
            "minutes": round(minutes_expected, 1),
            "range_low_minutes": round(max(1.0, minutes_expected * 0.6), 1),
            "range_high_minutes": round(max(minutes_expected + 3.0, minutes_expected * 1.8), 1),
        },
        "assumptions": [
            "heuristic estimate from decree length, expected roles, subagents, and tool calls",
            "actual closeout must label provider-reported usage separately from estimated fallback",
        ],
    }


def estimate_command(args: argparse.Namespace) -> dict[str, Any]:
    event = build_estimate(args)
    if not args.no_write:
        write_event(event)
    return event


def numeric_or_none(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return max(0, int(value))


def seconds_from_range(started_at: str, ended_at: str) -> float | None:
    if not started_at or not ended_at:
        return None
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (end - start).total_seconds())


def record_command(args: argparse.Namespace) -> dict[str, Any]:
    source = args.source if args.source in SOURCES else "unavailable"
    input_tokens = numeric_or_none(args.input_tokens)
    output_tokens = numeric_or_none(args.output_tokens)
    total_tokens = numeric_or_none(args.total_tokens)
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    if total_tokens is None and args.estimate_from_text:
        total_tokens = estimate_text_tokens(args.estimate_from_text)
        source = "estimated_fallback" if source == "unavailable" else source

    wall_seconds: float | None
    if args.wall_seconds not in (None, ""):
        wall_seconds = max(0.0, float(args.wall_seconds))
    else:
        wall_seconds = seconds_from_range(args.started_at, args.ended_at)

    event = {
        "kind": "record",
        "recorded_at": now_text(),
        "task_id": args.task_id,
        "role": args.role,
        "agent_id": args.agent_id,
        "source": source,
        "precision": "exact_or_reported" if source in {"provider_reported", "agent_reported"} else source,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "wall_seconds": wall_seconds,
        "started_at": args.started_at,
        "ended_at": args.ended_at,
        "note": args.note,
    }
    write_event(event)
    return event


def add_number(current: float, value: Any) -> float:
    if isinstance(value, (int, float)):
        return current + float(value)
    return current


def summarize(events: list[dict[str, Any]], task_id: str) -> dict[str, Any]:
    estimates = [event for event in events if event.get("kind") == "estimate"]
    records = [event for event in events if event.get("kind") == "record"]
    by_role: dict[str, dict[str, Any]] = {}
    usage_source_breakdown: list[dict[str, Any]] = []
    total_input = 0.0
    total_output = 0.0
    total_tokens = 0.0
    worker_elapsed_sum = 0.0
    input_record_count = 0
    output_record_count = 0
    token_record_count = 0
    elapsed_record_count = 0
    sources: set[str] = set()
    start_times: list[datetime] = []
    end_times: list[datetime] = []

    for record in records:
        role = str(record.get("role") or "unknown")
        role_item = by_role.setdefault(
            role,
            {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "wall_seconds": None,
                "sources": [],
                "records": 0,
                "token_record_count": 0,
                "elapsed_record_count": 0,
            },
        )
        role_item["records"] += 1
        source = str(record.get("source") or "unavailable")
        if source not in role_item["sources"]:
            role_item["sources"].append(source)
        sources.add(source)
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = record.get(key)
            if isinstance(value, (int, float)):
                if role_item[key] is None:
                    role_item[key] = 0
                role_item[key] += int(value)
                if key == "total_tokens":
                    role_item["token_record_count"] += 1
        wall = record.get("wall_seconds")
        if isinstance(wall, (int, float)):
            if role_item["wall_seconds"] is None:
                role_item["wall_seconds"] = 0.0
            role_item["wall_seconds"] = round(float(role_item["wall_seconds"]) + float(wall), 3)
            role_item["elapsed_record_count"] += 1
        for source_key, target in (("started_at", start_times), ("ended_at", end_times)):
            value = str(record.get(source_key) or "")
            if not value:
                continue
            try:
                target.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
            except ValueError:
                pass

        if isinstance(record.get("input_tokens"), (int, float)):
            input_record_count += 1
            total_input = add_number(total_input, record.get("input_tokens"))
        if isinstance(record.get("output_tokens"), (int, float)):
            output_record_count += 1
            total_output = add_number(total_output, record.get("output_tokens"))
        if isinstance(record.get("total_tokens"), (int, float)):
            token_record_count += 1
            total_tokens += float(record["total_tokens"])
        if isinstance(record.get("wall_seconds"), (int, float)):
            elapsed_record_count += 1
            worker_elapsed_sum += float(record["wall_seconds"])
        usage_source_breakdown.append(
            {
                "office": role,
                "agent_id": record.get("agent_id") or "",
                "source": source,
                "precision": record.get("precision") or source,
                "input_tokens": record.get("input_tokens"),
                "output_tokens": record.get("output_tokens"),
                "total_tokens": record.get("total_tokens"),
                "elapsed_ms": round(float(record.get("wall_seconds")) * 1000) if isinstance(record.get("wall_seconds"), (int, float)) else None,
                "task_evidence": record.get("note") or "",
            }
        )

    if not records:
        precision = "unavailable"
    elif sources <= {"provider_reported", "agent_reported"} and token_record_count == len(records):
        precision = "provider_reported" if sources == {"provider_reported"} else "mixed"
    elif "estimated_fallback" in sources:
        precision = "estimated" if sources == {"estimated_fallback"} else "mixed"
    else:
        precision = "unavailable" if sources == {"unavailable"} else "mixed"

    wall_clock_actual = None
    if start_times and end_times:
        wall_clock_actual = max(0.0, (max(end_times) - min(start_times)).total_seconds())

    return {
        "kind": "usage_summary",
        "generated_at": now_text(),
        "task_id": task_id,
        "ledger_path": str(ledger_path()),
        "latest_estimate": estimates[-1] if estimates else None,
        "record_count": len(records),
        "actual": {
            "input_tokens": int(total_input) if input_record_count else None,
            "output_tokens": int(total_output) if output_record_count else None,
            "total_tokens": int(total_tokens) if token_record_count else None,
            "wall_clock_actual_seconds": round(wall_clock_actual, 3) if wall_clock_actual is not None else None,
            "worker_elapsed_sum_seconds": round(worker_elapsed_sum, 3) if elapsed_record_count else None,
            "input_record_count": input_record_count,
            "output_record_count": output_record_count,
            "token_record_count": token_record_count,
            "elapsed_record_count": elapsed_record_count,
            "sources": sorted(sources),
            "precision": precision,
            "token_usage_precision": precision,
            "token_usage_note": "local estimates are not provider billing or exact model token counts unless source=provider_reported",
        },
        "by_role": by_role,
        "usage_source_breakdown": usage_source_breakdown,
    }


def summary_command(args: argparse.Namespace) -> dict[str, Any]:
    return summarize(read_events(args.task_id), args.task_id)


def output(value: dict[str, Any], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if value.get("kind") == "usage_summary":
        actual = value.get("actual", {})
        estimate = value.get("latest_estimate") or {}
        token_estimate = estimate.get("token_estimate") if isinstance(estimate, dict) else {}
        time_estimate = estimate.get("time_estimate") if isinstance(estimate, dict) else {}
        print(f"task_id: {value.get('task_id')}")
        print(f"estimate_tokens: {token_estimate.get('total_tokens', 'unavailable')}")
        print(f"estimate_time_minutes: {time_estimate.get('minutes', 'unavailable')}")
        print(
            "actual_tokens: "
            f"{actual.get('total_tokens', 0)}; precision={actual.get('precision')}; sources={','.join(actual.get('sources', []))}"
        )
        print(f"wall_clock_actual_seconds: {actual.get('wall_clock_actual_seconds', 'unavailable')}")
        print(f"worker_elapsed_sum_seconds: {actual.get('worker_elapsed_sum_seconds', 0)}")
        return
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    sub = parser.add_subparsers(dest="command", required=True)

    estimate = sub.add_parser("estimate", help="record a decree token/time estimate")
    estimate.add_argument("--task-id", required=True)
    estimate.add_argument("--decree", required=True)
    estimate.add_argument("--authority", choices=sorted(AUTHORITIES), required=True)
    estimate.add_argument("--behavior", choices=sorted(BEHAVIORS), required=True)
    estimate.add_argument("--runtime", choices=sorted(RUNTIMES), required=True)
    estimate.add_argument("--roles", default="")
    estimate.add_argument("--office-count", type=int, default=0)
    estimate.add_argument("--subagent-count", type=int, default=0)
    estimate.add_argument("--expected-tool-calls", type=int, default=0)
    estimate.add_argument("--context-tokens", type=int, default=0)
    estimate.add_argument("--no-write", action="store_true")
    estimate.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)

    record = sub.add_parser("record", help="record actual or fallback token/time usage")
    record.add_argument("--task-id", required=True)
    record.add_argument("--role", default="taizi")
    record.add_argument("--agent-id", default="")
    record.add_argument("--source", choices=sorted(SOURCES), default="unavailable")
    record.add_argument("--input-tokens", default="")
    record.add_argument("--output-tokens", default="")
    record.add_argument("--total-tokens", default="")
    record.add_argument("--estimate-from-text", default="")
    record.add_argument("--wall-seconds", default="")
    record.add_argument("--started-at", default="")
    record.add_argument("--ended-at", default="")
    record.add_argument("--note", default="")
    record.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)

    summary = sub.add_parser("summary", help="summarize usage for a decree/task")
    summary.add_argument("--task-id", required=True)
    summary.add_argument("--format", choices=["text", "json"], default=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "estimate":
            output(estimate_command(args), args.format)
        elif args.command == "record":
            output(record_command(args), args.format)
        elif args.command == "summary":
            output(summary_command(args), args.format)
        else:
            parser.error("unknown command")
    except Exception as exc:
        print(f"COURT_USAGE_LEDGER_ERROR {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
