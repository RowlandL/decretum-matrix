"""Reevaluate Shiguan memory decisions as review candidates.

This script does not mutate historical `memory_decision` fields. It reads the
rebuilt Shiguan index, applies the current content-lineage and value/risk rules,
and writes a candidate report for Menxia review.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

from shiguan_entry_utils import enrich_entry
from shiguan_paths import code_root, reference_path


DECISIONS = {"WRITE", "PROPOSE", "SKIP", "DEFERRED"}
SENSITIVE_RE = re.compile(
    r"(?i)("
    r"api[_ -]?key\s*[:=]\s*[^\s;，；]+|"
    r"secret\s*[:=]\s*[^\s;，；]+|"
    r"password\s*[:=]\s*[^\s;，；]+|"
    r"passwd\s*[:=]\s*[^\s;，；]+|"
    r"cookie\s*[:=]\s*[^\s;，；]+|"
    r"authorization\s*[:=]\s*[^\s;，；]+|"
    r"bearer\s+[a-z0-9._~+/=-]{16,}|"
    r"private[_ -]?key\s*[:=]\s*[^\s;，；]+|"
    r"access[_ -]?token\s*[:=]\s*[^\s;，；]+|"
    r"refresh[_ -]?token\s*[:=]\s*[^\s;，；]+|"
    r"私密二维码\s*[:=：]\s*\S+|"
    r"二维码密钥\s*[:=：]\s*\S+|"
    r"微信\s*id\s*[:=：]\s*\S+|"
    r"wechat\s*id\s*[:=]\s*\S+"
    r")"
)
STABLE_RULE_TERMS = (
    "must",
    "should",
    "default",
    "remember",
    "rule",
    "policy",
    "always",
    "never",
    "应当",
    "必须",
    "默认",
    "记住",
    "以后",
    "规则",
    "不应",
    "不能",
)
SESSION_ONLY_TERMS = (
    "self-test",
    "session evidence",
    "task/session",
    "one-time",
    "本次",
    "临时",
    "一次性",
    "自测",
)


def skill_root() -> Path:
    return code_root()


def index_path() -> Path:
    return reference_path("shiguan-index.jsonl")


def default_report_path() -> Path:
    return reference_path("memory-decisions", "reevaluation-candidates.json")


def load_entries(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            enrich_entry(value)
            entries.append(value)
    return entries


def joined_text(entry: dict[str, object]) -> str:
    values: list[str] = []
    for key in (
        "topic",
        "phase",
        "status",
        "summary",
        "display_summary_zh",
        "memory_content",
        "memory_reason",
        "next",
        "evidence",
        "keywords",
        "keywords_zh",
        "key_actions",
    ):
        value = entry.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value or ""))
    return "\n".join(values).lower()


def grade_rank(value: object) -> int:
    text = str(value or "").strip().upper()[:1]
    return {"S": 7, "A": 6, "B": 5, "C": 4, "D": 3, "E": 2, "F": 1}.get(text, 0)


def recommend(entry: dict[str, object]) -> tuple[str, str]:
    current = str(entry.get("memory_decision") or entry.get("status") or "").upper()
    text = joined_text(entry)
    if SENSITIVE_RE.search(text):
        if current in {"WRITE", "PROPOSE"}:
            return "SKIP", "含具体凭据、私密标识或认证材料，不得写入长期记忆。"
        if current in DECISIONS:
            return current, "含具体凭据、私密标识或认证材料，保留非写入裁定。"
        return "DEFERRED", "含具体凭据、私密标识或认证材料，暂缓裁定。"
    value = grade_rank(entry.get("knowledge_value"))
    priority = grade_rank(entry.get("priority_level"))
    risk = grade_rank(entry.get("risk_level"))
    stable_rule = any(term in text for term in STABLE_RULE_TERMS)
    session_only = any(term in text for term in SESSION_ONLY_TERMS)
    source = str(entry.get("source") or "")

    if stable_rule and value >= 6:
        return "WRITE", "包含长期规则或默认行为，且知识价值较高。"
    if stable_rule:
        return "PROPOSE", "包含可复用规则，但需门下省复核后再正式写入。"
    if value >= 6 and priority >= 5 and not session_only:
        return "PROPOSE", "新分类后价值和优先级较高，适合列为记忆候选。"
    if risk >= 6 and not session_only:
        return "PROPOSE", "风险较高，后续任务可参考，但需门下省裁定边界。"
    if current == "SKIP" and ("plan-archives" in source or session_only):
        return "SKIP", "仍偏一次性过程证据，不建议写入长期记忆。"
    if current in DECISIONS:
        return current, "重评未发现足够理由改变原裁定。"
    return "DEFERRED", "缺少稳定规则或长期价值证据，暂缓裁定。"


def build_report(entries: list[dict[str, object]], limit: int | None = None) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    changed = 0
    for entry in entries:
        current = str(entry.get("memory_decision") or entry.get("status") or "DEFERRED").upper()
        proposed, reason = recommend(entry)
        if proposed != current:
            changed += 1
        candidates.append(
            {
                "court_code": entry.get("court_code"),
                "topic": entry.get("topic"),
                "phase": entry.get("phase"),
                "current_decision": current,
                "recommended_decision": proposed,
                "changed": proposed != current,
                "lineage_display": entry.get("lineage_display") or entry.get("ancient_lineage"),
                "display_summary_zh": entry.get("display_summary_zh") or entry.get("keyword_summary_zh"),
                "risk_level": entry.get("risk_level"),
                "knowledge_value": entry.get("knowledge_value"),
                "priority_level": entry.get("priority_level"),
                "reason_zh": reason,
                "source": entry.get("source"),
            }
        )
    candidates.sort(key=lambda item: (not item["changed"], str(item["court_code"] or "")))
    if limit is not None:
        candidates = candidates[: max(limit, 0)]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "candidate_only",
        "note": "候选报告不覆盖历史 memory_decision；需门下省复核后再正式改写。",
        "entries": len(entries),
        "changed_candidates": changed,
        "candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=index_path())
    parser.add_argument("--out", type=Path, default=default_report_path())
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    entries = load_entries(args.index)
    report = build_report(entries, args.limit)
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"MEMORY_REEVALUATION_OK {args.out} entries={report['entries']} "
        f"changed_candidates={report['changed_candidates']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
