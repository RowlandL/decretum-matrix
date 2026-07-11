"""Validate the court response few-shot format shard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SHARD = ROOT / "references" / "sections" / "court-response-fewshot-format.md"
OFFICE_VOICE_SHARD = ROOT / "references" / "sections" / "court-office-voice-fewshot.md"

REQUIRED_SECTIONS = [
    "# Court Response Few-Shot Format",
    "## Response Prompt",
    "## Universal Field Contract",
    "## Few-Shot Samples",
    "## Repair Rules",
]

REQUIRED_TOKEN_TERMS = [
    "metadata_precision",
    "body_reference_policy",
    "on_demand_loading",
]

CANONICAL_FIELDS = [
    "`意图`",
    "`边界`",
    "`状态`",
    "`动作`",
    "`证据`",
    "`风险`",
    "`下一步`",
]

SAMPLE_FAMILIES = [
    "direct_answer",
    "plan_start",
    "progress_update",
    "clarification_question",
    "implementation_closeout",
    "partial_or_not_run",
    "authority_blocked",
    "code_review",
    "office_report",
    "handoff_or_pause",
]

REQUIRED_SAMPLE_TERMS = [
    "太子回奏",
    "太子上奏下一项问题",
    "结诏",
    "Draft Reply Fixture Lint",
    "check_response_draft_fixtures.py",
    "response-draft-families.json",
    "验收证据：PARTIAL",
    "验收证据：NOT_RUN",
    "authority_blocked",
    "门下省封驳",
    "上奏：<direct_superior>",
    "response_fewshot_gate=PASSED",
    "response_fewshot_gate=PARTIAL",
    "response_fewshot_gate=DRIFT_CORRECTED",
    "court-office-voice-fewshot.md",
]

OFFICE_VOICE_REQUIRED_TERMS = [
    "Court Office Voice Few-Shot",
    "## Should Do",
    "## Counterexamples",
    "first_person_progress_counterexample",
    "generic_assistant_counterexample",
    "fake_office_counterexample",
    "user_direct_office_counterexample",
    "Repair Checklist",
    "太子代摄官署流程",
]

REQUIRED_FAMILY_BLOCK_TERMS = {
    "direct_answer": ["太子回奏", "证据", "下一步"],
    "plan_start": ["太子回奏", "中书省拟旨", "门下省封驳", "尚书省分派", "下一步"],
    "progress_update": ["进展", "当前判断", "下一步"],
    "clarification_question": ["太子上奏下一项问题", "原因"],
    "implementation_closeout": [
        "结诏",
        "诏令编号",
        "古制谱系",
        "状态",
        "作业AI",
        "旨意与边界",
        "执行门禁",
        "门下裁定",
        "实际动作",
        "验收证据",
        "运行态与并行",
        "史馆",
        "余险",
        "太子回奏",
        "下一步",
    ],
    "partial_or_not_run": ["太子回奏", "验收证据：PARTIAL", "风险", "下一步"],
    "authority_blocked": ["太子回奏：authority_blocked", "边界", "受阻动作", "需要朱批"],
    "code_review": ["门下省封驳", "余险", "简要结论"],
    "office_report": ["上奏：<direct_superior>", "身份", "状态", "要点", "证据", "请裁"],
    "handoff_or_pause": ["太子回奏：HANDOFF | PAUSED", "当前状态", "未竟事项", "恢复入口", "风险"],
}


def shard_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "references" / "sections" / "court-response-fewshot-format.md"


def office_voice_shard_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "references" / "sections" / "court-office-voice-fewshot.md"


def read_text(root: Path | None = None) -> str:
    return shard_path(root).read_text(encoding="utf-8", errors="replace")


def code_blocks(text: str) -> list[str]:
    return re.findall(r"```(?:text)?\n(.*?)\n```", text, flags=re.DOTALL)


def family_body(text: str, family: str) -> str | None:
    pattern = rf"^### {re.escape(family)}\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return None
    next_heading = re.search(r"^### |\n## ", text[match.end():], flags=re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end():end]


def evaluate(root: Path | None = None) -> dict[str, object]:
    errors: list[str] = []
    path = shard_path(root)
    if not path.exists():
        return {
            "response_fewshot_gate": "FAILED",
            "path": str(path),
            "errors": ["missing_shard"],
        }

    text = read_text(root)
    for term in REQUIRED_SECTIONS + REQUIRED_TOKEN_TERMS + CANONICAL_FIELDS + REQUIRED_SAMPLE_TERMS:
        if term not in text:
            errors.append(f"missing:{term}")
    for family in SAMPLE_FAMILIES:
        body = family_body(text, family)
        if body is None:
            errors.append(f"missing_sample_family:{family}")
            continue
        blocks_for_family = code_blocks(body)
        if not blocks_for_family:
            errors.append(f"missing_sample_code_block:{family}")
            continue
        block_text = "\n".join(blocks_for_family)
        for term in REQUIRED_FAMILY_BLOCK_TERMS[family]:
            if term not in block_text:
                errors.append(f"missing_sample_block_term:{family}:{term}")

    blocks = code_blocks(text)
    if len(blocks) < len(SAMPLE_FAMILIES):
        errors.append(f"too_few_code_blocks:{len(blocks)}")
    if "Prompt:" not in text:
        errors.append("missing_prompt_label")
    if len(text.splitlines()) > 260:
        errors.append(f"oversized_shard_lines:{len(text.splitlines())}")

    voice_path = office_voice_shard_path(root)
    if not voice_path.exists():
        errors.append("missing_office_voice_fewshot_shard")
    else:
        voice_text = voice_path.read_text(encoding="utf-8", errors="replace")
        for term in OFFICE_VOICE_REQUIRED_TERMS:
            if term not in voice_text:
                errors.append(f"office_voice_missing:{term}")

    gate = "PASSED" if not errors else "FAILED"
    return {
        "response_fewshot_gate": gate,
        "path": str(path),
        "sample_family_count": len(SAMPLE_FAMILIES),
        "code_block_count": len(blocks),
        "line_count": len(text.splitlines()),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["response_fewshot_gate"] == "PASSED":
        print(
            "RESPONSE_FEWSHOT_FORMAT_OK "
            f"families={result['sample_family_count']} "
            f"blocks={result['code_block_count']} "
            f"lines={result['line_count']}"
        )
    else:
        print("RESPONSE_FEWSHOT_FORMAT_FAILED")
        for error in result["errors"]:
            print(error)
    return 0 if result["response_fewshot_gate"] == "PASSED" else 2


if __name__ == "__main__":
    sys.exit(main())
