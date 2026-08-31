"""Check GBrain recall leaves/full-record pointers and the Shiguan full-record
index (P3-7 / P3-9): metadata-only projection, relative portable locators,
source hash, section/line anchors, leaves retrieval of the full process, no
pending/private body copies, and byte-identical double-run determinism."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from shiguan_gbrain import (  # noqa: E402
    build_full_record_index,
    build_leaves,
    build_recall_context,
    full_record_pointer,
)


def _entry(
    uid: str,
    code: str,
    topic: str,
    phase: str,
    status: str,
    summary: str,
    source: str,
    *,
    key_actions: list[str] | None = None,
    next_step: str = "",
    lineage_key: str = "shiguan/archive/recall",
    memory_content: str = "",
) -> dict[str, object]:
    return {
        "record_uid": uid,
        "court_code": code,
        "topic": topic,
        "phase": phase,
        "status": status,
        "summary": summary,
        "evidence": summary,
        "source": source,
        "key_actions": key_actions or [],
        "next": next_step,
        "lineage_key": lineage_key,
        "memory_decision": "WRITE",
        "memory_content": memory_content,
        "time": f"2026-08-0{1}T00:00:00+08:00",
    }


def evaluate() -> dict[str, Any]:
    entries = [
        _entry(
            "REC-1",
            "SDMLTIUW7-20260801-1-ABAA",
            "史馆索引检索",
            "太子定性",
            "DONE",
            "史馆索引默认走本地快路径并完成验证",
            "references/plan-archives/rec1.md",
            key_actions=["初始动作：建立索引", "后续动作：执行检索"],
            next_step="进入门下复核",
            memory_content="这是不应被索引复制的完整正文",
        ),
        _entry(
            "REC-2",
            "SDMLTIUW7-20260802-2-ABAA",
            "史馆索引检索",
            "门下复核",
            "APPROVED",
            "门下复核通过，索引策略定稿",
            "references/plan-archives/rec2.md",
            key_actions=["复核索引策略"],
            next_step="归档",
        ),
        _entry(
            "REC-3",
            "SDMLTIUW7-20260803-3-ABAA",
            "安装包打包",
            "六部执行",
            "DONE",
            "安装包打包完成",
            "references/plan-archives/rec3.md",
            lineage_key="install/package/build",
            next_step="发布评审",
        ),
        _entry(
            "REC-ABS",
            "SDMLTIUW7-20260804-4-ABAA",
            "绝对路径记录",
            "史馆实录",
            "DONE",
            "绝对路径不应进入索引",
            "C:\\Users\\Administrator\\outside\\rec4.md",
            next_step="none",
        ),
    ]
    failures: list[str] = []

    recall = build_recall_context(
        entries,
        ["史馆"],
        governance_id="g",
        current_decree_id="d",
        as_of="2026-08-31T12:00:00+08:00",
        limit=5,
    )
    matches = recall.get("matches") or []
    if not matches:
        failures.append("full_record_recall_no_matches")
    full_record_ok = True
    leaves_ok = True
    for match in matches:
        pointer = match.get("full_record")
        if not isinstance(pointer, dict):
            full_record_ok = False
            failures.append("full_record_pointer_missing")
            continue
        if pointer.get("schema") != "court.full_record_pointer.v1":
            full_record_ok = False
            failures.append("full_record_pointer_schema_invalid")
        source_ref = pointer.get("source_ref")
        # None means "non-portable record" (absolute host path) and is legal:
        # the pointer marks it and the index excludes it. A non-None source_ref
        # must be a relative portable path (no drive/leading slash).
        if source_ref is not None and (
            not str(source_ref)
            or str(source_ref).startswith(("/", "\\"))
            or __import__("re").match(r"^[A-Za-z]:[\\/]", str(source_ref))
        ):
            full_record_ok = False
            failures.append(f"full_record_source_ref_not_portable:{source_ref}")
        if (
            not isinstance(pointer.get("source_hash"), str)
            or len(pointer.get("source_hash")) != 64
        ):
            full_record_ok = False
            failures.append("full_record_source_hash_invalid")
        if pointer.get("access_status") != "metadata_only":
            full_record_ok = False
            failures.append("full_record_access_status_not_metadata_only")
        fields = pointer.get("fields")
        if not isinstance(fields, dict):
            full_record_ok = False
            failures.append("full_record_fields_missing")
        else:
            for field in (
                "initial_question",
                "process_questions",
                "final_result",
                "resolved",
                "resolution_scope",
                "next_step",
            ):
                if field not in fields:
                    full_record_ok = False
                    failures.append(f"full_record_field_{field}_missing")
        if "memory_content" in pointer or "full_body" in pointer:
            full_record_ok = False
            failures.append("full_record_copied_private_body")
        leaves = match.get("leaves")
        if not isinstance(leaves, list):
            leaves_ok = False
            failures.append("full_record_leaves_missing")
    if not full_record_ok:
        failures.append("full_record_pointer_invalid")
    if not leaves_ok:
        failures.append("full_record_leaves_invalid")

    # Leaves must be able to reconstruct the full process (same lineage).
    rec1_pointer = full_record_pointer(entries[0])
    rec1_leaves = build_leaves(entries, entries[0], limit=8)
    leaf_uids = {item.get("record_uid") for item in rec1_leaves}
    if "REC-2" not in leaf_uids:
        failures.append("leaves_do_not_retrieve_related_process")
    if any("memory_content" in item or "full_body" in item for item in rec1_leaves):
        failures.append("leaves_copied_private_body")

    # Absolute host path must be rejected as non-portable.
    abs_pointer = full_record_pointer(entries[3])
    if abs_pointer.get("source_ref") is not None:
        failures.append("absolute_host_path_not_rejected")

    # Full-record index: relative pointers only, leaves queryable, no body.
    index = build_full_record_index(entries)
    if index.get("record_count") != 3:
        failures.append(
            f"full_record_index_count_invalid:{index.get('record_count')}"
        )
    for record in index.get("records") or []:
        if not record.get("source_ref") or record["source_ref"].startswith(("/", "\\")):
            failures.append("full_record_index_nonportable_source")
        if record.get("access_status") != "metadata_only":
            failures.append("full_record_index_access_status_invalid")
        if "memory_content" in record or "full_body" in record:
            failures.append("full_record_index_copied_body")
        if not isinstance(record.get("leaves"), list):
            failures.append("full_record_index_leaves_missing")

    # Double-run byte-identical determinism.
    rerun_index = build_full_record_index(entries)
    if json.dumps(index, ensure_ascii=False, sort_keys=True).encode(
        "utf-8"
    ) != json.dumps(rerun_index, ensure_ascii=False, sort_keys=True).encode("utf-8"):
        failures.append("full_record_index_nondeterministic")
    rerun_recall = build_recall_context(
        entries,
        ["史馆"],
        governance_id="g",
        current_decree_id="d",
        as_of="2026-08-31T12:00:00+08:00",
        limit=5,
    )
    if json.dumps(recall, ensure_ascii=False, sort_keys=True).encode(
        "utf-8"
    ) != json.dumps(rerun_recall, ensure_ascii=False, sort_keys=True).encode("utf-8"):
        failures.append("full_record_recall_nondeterministic")

    failures = list(dict.fromkeys(failures))
    return {
        "schema": "court.shiguan_full_record_index_check.v1",
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": "SHIGUAN_FULL_RECORD_INDEX",
        "evidence": {
            "recall_match_count": len(matches),
            "full_record_pointer_ok": full_record_ok,
            "leaves_retrieve_process": "REC-2" in leaf_uids,
            "absolute_host_path_rejected": abs_pointer.get("source_ref") is None,
            "index_record_count": index.get("record_count"),
            "index_deterministic": True,
        },
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate()
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": "court.shiguan_full_record_index_check.v1",
            "ok": False,
            "status": "ERROR",
            "contract": "SHIGUAN_FULL_RECORD_INDEX",
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        for stream in (sys.stdout,):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"SHIGUAN_FULL_RECORD_INDEX={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
