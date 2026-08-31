"""Closeout conflict/expiry scan with scripted deterministic downgrade (D2a / P3-6).

Read-only by default: ``scan`` returns conflicts and expiries with a
deterministic decision (SUPERSEDED / DEGRADED) or a non-deterministic REVIEW
(menxia). ``apply_decisions`` records only deterministic decisions through the
domain ledger (one immutable revision + one Git commit per write) so every
downgrade keeps a before/after, reason, Git revision and user-notice field.
Newer records / higher-authority facts win; ambiguous or high-risk cases stay
in REVIEW for menxia. ``affected_topics`` limits the scan to an affected set so
feedback-driven incremental re-evaluation (P3-8) never triggers a full rebuild.
"""
from __future__ import annotations

import argparse
import json
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from shiguan_entry_utils import index_path, load_entries


SCHEMA = "court.closeout_conflict_scan.v1"
DURABLE_DECISIONS = {"WRITE", "PROPOSE"}
DETERMINISTIC_ACTIONS = {"SUPERSEDED", "DEGRADED"}


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _applicability(entry: dict[str, object], as_of: datetime) -> str:
    valid_from = _timestamp(entry.get("valid_from"))
    valid_until = _timestamp(entry.get("valid_until"))
    if valid_from is None and valid_until is None:
        return "undated"
    if valid_from is not None and as_of < valid_from:
        return "future"
    if valid_until is not None and as_of > valid_until:
        return "historical"
    return "current"


def _record_uid(entry: dict[str, object]) -> str:
    for field in ("record_uid", "court_code"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    material = json.dumps(
        {
            "time": entry.get("time"),
            "topic": entry.get("topic"),
            "source": entry.get("source"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"recall-{zlib.crc32(material.encode('utf-8')):08x}"


def _normalized_topic(entry: dict[str, object]) -> str:
    return " ".join(str(entry.get("topic") or "").casefold().split())


def _content_fingerprint(entry: dict[str, object]) -> str:
    for key in ("content_sha256", "memory_content", "summary", "evidence"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _decision(
    *,
    record_uid: str,
    action: str,
    deterministic: bool,
    reason: str,
    before: object,
    after: str,
    as_of: str,
    user_notice: str,
    superseded_by: object = None,
    topic: str = "",
) -> dict[str, object]:
    return {
        "record_uid": record_uid,
        "topic": topic,
        "action": action,
        "deterministic": deterministic,
        "reason": reason,
        "before": before,
        "after": after,
        "as_of": as_of,
        "user_notice": user_notice,
        "notify_user": True,
        "superseded_by": superseded_by,
    }


def scan(
    entries: list[dict[str, object]],
    as_of: str,
    affected_topics: list[str] | None = None,
) -> dict[str, Any]:
    """Return a read-only conflict/expiry report (never writes)."""
    instant = _timestamp(as_of)
    if instant is None:
        raise ValueError("as_of_invalid")
    affected = {str(item).strip().casefold() for item in (affected_topics or []) if str(item).strip()}
    decisions: list[dict[str, object]] = []

    def _in_scope(entry: dict[str, object]) -> bool:
        return not affected or _normalized_topic(entry).casefold() in affected

    # Expiry pass (deterministic DEGRADED / future REVIEW).
    for entry in entries:
        if not _in_scope(entry):
            continue
        applicability = _applicability(entry, instant)
        if applicability == "historical":
            decisions.append(
                _decision(
                    record_uid=_record_uid(entry),
                    topic=str(entry.get("topic") or ""),
                    action="DEGRADED",
                    deterministic=True,
                    reason="record_expired",
                    before=str(entry.get("memory_decision") or ""),
                    after="DEGRADED",
                    as_of=as_of,
                    user_notice=f"记忆记录已过期（valid_until 早于 {as_of}），标记 DEGRADED 并告知用户。",
                )
            )
        elif applicability == "future":
            decisions.append(
                _decision(
                    record_uid=_record_uid(entry),
                    topic=str(entry.get("topic") or ""),
                    action="REVIEW",
                    deterministic=False,
                    reason="future_record_not_yet_active",
                    before=str(entry.get("memory_decision") or ""),
                    after="REVIEW",
                    as_of=as_of,
                    user_notice="记忆记录尚未生效（valid_from 晚于当前），转门下复核。",
                )
            )

    # Conflict pass (deterministic SUPERSEDED / ambiguous REVIEW).
    groups: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        if _in_scope(entry):
            groups.setdefault(_normalized_topic(entry), []).append(entry)
    for topic_key, group in groups.items():
        if len(group) < 2:
            continue
        ordered = sorted(
            group,
            key=lambda item: _timestamp(item.get("time"))
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        newest = ordered[0]
        newest_decision = str(newest.get("memory_decision") or "").upper()
        newest_content = _content_fingerprint(newest)
        for older in ordered[1:]:
            older_decision = str(older.get("memory_decision") or "").upper()
            older_content = _content_fingerprint(older)
            both_durable = (
                newest_decision in DURABLE_DECISIONS
                and older_decision in DURABLE_DECISIONS
            )
            if (
                both_durable
                and newest_content
                and older_content
                and newest_content != older_content
            ):
                decisions.append(
                    _decision(
                        record_uid=_record_uid(older),
                        topic=str(older.get("topic") or ""),
                        action="SUPERSEDED",
                        deterministic=True,
                        reason="newer_record_supersedes_contradictory",
                        before=older_decision,
                        after="SUPERSEDED",
                        as_of=as_of,
                        user_notice=(
                            "同一主题存在更新的持久记忆且内容矛盾，旧记录标记 SUPERSEDED。"
                        ),
                        superseded_by=_record_uid(newest),
                    )
                )
            elif newest_decision != older_decision:
                # Ambiguous conflict: both the newer and the older record go to
                # menxia review (no scripted winner), staying advisory.
                for conflicted, conflicted_decision in (
                    (older, older_decision),
                    (newest, newest_decision),
                ):
                    decisions.append(
                        _decision(
                            record_uid=_record_uid(conflicted),
                            topic=str(conflicted.get("topic") or ""),
                            action="REVIEW",
                            deterministic=False,
                            reason="ambiguous_decision_conflict",
                            before=conflicted_decision,
                            after="REVIEW",
                            as_of=as_of,
                            user_notice="同一主题存在裁定冲突（如 WRITE 与 SKIP 并存），转门下复核。",
                            superseded_by=_record_uid(newest),
                        )
                    )

    # Deduplicate identical (record_uid, action, reason) review entries produced
    # when a record participates in multiple conflicting pairs.
    seen: set[tuple[str, str, str]] = set()
    unique_decisions: list[dict[str, object]] = []
    for item in decisions:
        key = (
            str(item["record_uid"]),
            str(item["action"]),
            str(item["reason"]),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_decisions.append(item)
    decisions = unique_decisions

    decisions.sort(
        key=lambda item: (not bool(item["deterministic"]), str(item["record_uid"]))
    )
    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "decision_count": len(decisions),
        "deterministic_count": sum(
            1 for item in decisions if item["deterministic"]
        ),
        "review_count": sum(1 for item in decisions if not item["deterministic"]),
        "decisions": decisions,
    }


def apply_decisions(
    decisions: list[dict[str, object]],
    *,
    actor: str,
    authority: str,
    write_set: list[str],
    root: Path | None = None,
    idempotency_keys: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record deterministic decisions through the domain ledger (P3-6).

    Each deterministic SUPERSEDED / DEGRADED decision becomes one immutable
    domain-ledger revision with its own Git commit (base:
    domain_ledger_api revision + git commit). REVIEW decisions stay advisory.
    """
    from domain_ledger_api import domain_ledger_write

    idempotency_keys = idempotency_keys or {}
    receipts: list[dict[str, object]] = []
    applied = 0
    for decision in decisions:
        if decision.get("action") not in DETERMINISTIC_ACTIONS:
            continue
        topic = str(decision.get("record_uid") or "").strip()
        if not topic:
            continue
        content = f"closeout-{str(decision.get('action')).lower()}-record"
        metadata = {
            "decision": decision.get("action"),
            "before": decision.get("before"),
            "after": decision.get("after"),
            "reason": decision.get("reason"),
            "user_notice": decision.get("user_notice"),
            "notify_user": True,
            "deterministic": True,
            "superseded_by": decision.get("superseded_by"),
            "as_of": decision.get("as_of"),
        }
        result = domain_ledger_write(
            kind="memory",
            operation="update",
            topic=topic,
            content=content,
            actor=actor,
            authority=authority,
            write_set=write_set,
            root=root,
            idempotency_key=idempotency_keys.get(topic),
            metadata=metadata,
        )
        receipts.append(result)
        if result.get("ok"):
            applied += 1
    return {
        "schema": SCHEMA,
        "ok": True,
        "applied": applied,
        "receipt_count": len(receipts),
        "receipts": receipts,
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--affected-topic", action="append", default=None)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--actor", default="shiguan")
    parser.add_argument("--authority", default="super")
    parser.add_argument("--write-set", default="memory")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    index = args.index or index_path()
    entries = load_entries(index)
    if args.limit is not None:
        entries = entries[: max(int(args.limit), 0)]
    as_of = args.as_of or datetime.now(timezone.utc).isoformat(timespec="seconds")
    report = scan(entries, as_of, affected_topics=args.affected_topic)
    if not args.apply:
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                f"CLOSEOUT_CONFLICT_SCAN decisions={report['decision_count']} "
                f"deterministic={report['deterministic_count']} "
                f"review={report['review_count']}"
            )
            for item in report["decisions"]:
                print(
                    f"  {item['action']:10} {item['record_uid']:20} "
                    f"{item['reason']} (deterministic={item['deterministic']})"
                )
        return 0

    if not args.yes:
        print("CLOSEOUT_CONFLICT_APPLY_REFUSED requires --yes", file=sys.stderr)
        return 2
    write_set = [item.strip() for item in args.write_set.split(",") if item.strip()]
    result = apply_decisions(
        report["decisions"],
        actor=args.actor,
        authority=args.authority,
        write_set=write_set,
        root=args.root,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"CLOSEOUT_CONFLICT_APPLY_OK applied={result['applied']} "
            f"receipts={result['receipt_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
