"""Validate generated draft-reply fixtures for court response families."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from typing import Any

try:
    from check_response_fewshot_format import SAMPLE_FAMILIES
except Exception:  # pragma: no cover - reported by evaluate().
    SAMPLE_FAMILIES = []  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "references" / "fixtures" / "response-draft-families.json"

CLOSEOUT_LABELS = [
    "诏令编号：",
    "古制谱系：",
    "状态：",
    "作业AI：",
    "旨意与边界：",
    "执行门禁：",
    "门下裁定：",
    "实际动作：",
    "验收证据：",
    "运行态与并行：",
    "史馆：",
    "余险：",
    "太子回奏：",
    "下一步：",
]

REQUIRED_CLOSEOUT_IDENTIFIERS = ("诏令编号：", "古制谱系：")
FORBIDDEN_IDENTIFIER_VALUES = {"", "...", "…", "未生成", "pending_archive_assignment", "NOT_APPLICABLE"}
COURT_CODE_PATTERN = re.compile(
    r"^(?P<lineage_code>[0-9A-Z]{7,})-"
    r"(?P<date>[0-9]{8})-"
    r"(?P<daily_sequence>[0-9A-Z]+)-"
    r"(?P<status_grades>[0-9A-Z][SABCDEF]{3})$"
)
LINEAGE_LAYER_SUFFIXES = ("志", "门", "纲", "目", "条", "诏")
FORBIDDEN_LINEAGE_PROTOCOL_PATTERNS = (
    re.compile(r"(?:→|←|↔|->|=>)"),
    re.compile(
        r"(?:^|[^0-9A-Z])PHASE(?:[-_\s]*[0-9A-Z]+)?(?:$|[^0-9A-Z])",
        flags=re.IGNORECASE,
    ),
    re.compile(r"(?:^|[^0-9A-Z])RB(?:[-_]?[0-9A-Z]+)?(?:$|[^0-9A-Z])", flags=re.IGNORECASE),
    re.compile(r"(?:^|[^0-9A-Z])task(?:[_\s-]?id)?(?:$|[^0-9A-Z])", flags=re.IGNORECASE),
    re.compile(r"(?:^|[^0-9A-Z])CCR(?:-[0-9A-Z]+)+(?:$|[^0-9A-Z])", flags=re.IGNORECASE),
)
IDENTIFIER_CONTRACT_CASES = (
    ("internal_task_code", "court_code", "CCR-R2-SHIR-20260714-A02-RB3-20260717", False),
    ("invalid_calendar_date", "court_code", "SCGSDYJM-20260230-1Z-DAAA", False),
    ("lowercase_base36_sequence", "court_code", "SCGSDYJM-20260606-1z-DAAA", False),
    ("formal_court_code", "court_code", "SCGSDYJM-20260606-1Z-DAAA", True),
    ("protocol_path_lineage", "content_lineage", "总体执行书→Phase 2-3→RB3→autosync 残余复核", False),
    (
        "formal_content_lineage",
        "content_lineage",
        "史馆总纪·朝制志·官署门·三省六部纲·回复格式目·结诏标识条·内容谱系诏",
        True,
    ),
    (
        "content_word_with_phase_substring",
        "content_lineage",
        "史馆总纪·Metaphase研究志·官署门·三省六部纲·回复格式目·结诏标识条·内容谱系诏",
        True,
    ),
)

FAMILY_LINE_PREFIXES = {
    "direct_answer": ["太子回奏：", "证据：", "下一步："],
    "plan_start": ["太子回奏：", "中书省拟旨：", "门下省封驳：", "尚书省分派：", "下一步："],
    "progress_update": ["太子回奏：进展：", "当前判断：", "下一步："],
    "clarification_question": ["太子上奏下一项问题：", "原因："],
    "partial_or_not_run": ["太子回奏：", "验收证据：", "风险：", "下一步："],
    "authority_blocked": ["太子回奏：authority_blocked", "边界：", "受阻动作：", "需要朱批："],
    "office_report": ["上奏：", "身份：", "状态：", "要点：", "证据：", "请裁："],
    "handoff_or_pause": ["太子回奏：", "当前状态：", "未竟事项：", "恢复入口：", "风险："],
    "dispatch_local_candidate": ["太子回奏：", "状态：", "候选动作：", "证据：", "下一步："],
    "ask_user_create_skill": ["太子上奏下一项问题：", "状态：", "建议动作：", "证据：", "下一步："],
    "continue_after_user_rejects": ["太子回奏：", "状态：", "用户决定：", "原任务：", "下一步："],
    "discovery_authority_blocked": ["太子回奏：authority_blocked", "状态：", "发现结论：", "证据：", "下一步："],
    "discovery_failed_without_no-candidate_claim": ["太子回奏：", "状态：", "发现结论：", "证据：", "下一步："],
    "handoff_with_concerns": ["太子回奏：HANDOFF", "状态：", "当前结果：", "证据：", "下一步："],
    "partial_result": ["太子回奏：", "状态：", "当前结果：", "验收证据：PARTIAL", "下一步："],
    "verified_done": ["结诏：DONE", "状态：DONE", "完成核验：VERIFIED", "验收证据：VERIFIED", "下一步："],
}

FAMILY_EXACT_LABELS = {
    "dispatch_local_candidate": ["太子回奏：", "状态：", "候选动作：", "证据：", "下一步："],
    "ask_user_create_skill": ["太子上奏下一项问题：", "状态：", "建议动作：", "证据：", "下一步："],
    "continue_after_user_rejects": ["太子回奏：", "状态：", "用户决定：", "原任务：", "下一步："],
    "discovery_authority_blocked": ["太子回奏：", "状态：", "发现结论：", "证据：", "下一步："],
    "discovery_failed_without_no-candidate_claim": ["太子回奏：", "状态：", "发现结论：", "证据：", "下一步："],
    "handoff_with_concerns": ["太子回奏：", "状态：", "当前结果：", "证据：", "下一步："],
    "partial_result": ["太子回奏：", "状态：", "当前结果：", "验收证据：", "下一步："],
    "verified_done": ["结诏：", "状态：", "完成核验：", "验收证据：", "下一步："],
}

FAMILY_EXACT_VALUES = {
    "dispatch_local_candidate": {"状态：": {"IN_PROGRESS"}, "候选动作：": {"DISPATCH_LOCAL"}},
    "ask_user_create_skill": {"状态：": {"NEEDS_CONTEXT"}, "建议动作：": {"PROPOSE_CREATE_SKILL"}},
    "continue_after_user_rejects": {"状态：": {"IN_PROGRESS"}, "用户决定：": {"REJECTED"}, "原任务：": {"CONTINUES"}},
    "discovery_authority_blocked": {"太子回奏：": {"authority_blocked"}, "状态：": {"BLOCKED"}, "发现结论：": {"AUTHORITY_BLOCKED"}},
    "discovery_failed_without_no-candidate_claim": {"状态：": {"PARTIAL"}, "发现结论：": {"DISCOVERY_FAILED"}},
    "handoff_with_concerns": {"太子回奏：": {"HANDOFF"}, "状态：": {"HANDOFF"}},
    "partial_result": {"状态：": {"PARTIAL"}, "验收证据：": {"PARTIAL"}},
    "verified_done": {"结诏：": {"DONE"}, "状态：": {"DONE"}, "完成核验：": {"VERIFIED"}, "验收证据：": {"VERIFIED"}, "下一步：": {"无"}},
}

FORBIDDEN_GENERIC_VOICE = [
    "作为AI",
    "我是AI",
    "作为一个AI",
    "助手回复",
    "assistant",
    "我会",
    "我已经",
    "我将",
    "我认为",
    "I will",
    "I have",
    "I think",
]

LONG_ALLOWED_LABELS = {"余险：", "太子回奏：", "下一步："}
LOGIC_TERMS = ("因为", "所以", "因此", "若", "则", "先", "再", "证据", "门禁", "风险", "下一步", "回滚")
MAX_CONCISE_FIELD_CHARS = 180
MAX_ALLOWED_LONG_FIELD_CHARS = 520


def fixture_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "references" / "fixtures" / "response-draft-families.json"


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing_fixture"
    except json.JSONDecodeError as exc:
        return None, f"invalid_json:{exc}"
    if not isinstance(data, dict):
        return None, "fixture_root_not_object"
    return data, None


def _nonempty_lines(draft: str) -> list[str]:
    return [line.rstrip() for line in draft.splitlines() if line.strip()]


def _check_ordered_prefixes(family: str, lines: list[str], errors: list[str]) -> None:
    prefixes = FAMILY_LINE_PREFIXES[family]
    if len(lines) != len(prefixes):
        errors.append(f"{family}:line_count:{len(lines)}!={len(prefixes)}")
        return
    exact_labels = FAMILY_EXACT_LABELS.get(family)
    if exact_labels is None:
        for index, (line, prefix) in enumerate(zip(lines, prefixes), start=1):
            if not line.startswith(prefix):
                errors.append(f"{family}:line_{index}_prefix:{prefix}")
        return
    for index, (line, label) in enumerate(zip(lines, exact_labels), start=1):
        actual_label, separator, value = line.partition("：")
        actual_label = actual_label + separator
        if separator != "：" or actual_label != label:
            errors.append(f"{family}:line_{index}_label:{label}")
            continue
        allowed = FAMILY_EXACT_VALUES.get(family, {}).get(label)
        enum_value = re.split(r"[；;]", value, maxsplit=1)[0].strip()
        if allowed is not None and enum_value not in allowed:
            errors.append(f"{family}:line_{index}_value:{sorted(allowed)}")


def _check_closeout(
    lines: list[str],
    fixture: dict[str, Any],
    errors: list[str],
) -> None:
    if not lines or lines[0] != "结诏：":
        errors.append("implementation_closeout:first_line_not_closeout")
        return
    labels = lines[1:]
    if len(labels) != len(CLOSEOUT_LABELS):
        errors.append(f"implementation_closeout:label_count:{len(labels)}!={len(CLOSEOUT_LABELS)}")
        return
    for index, (line, label) in enumerate(zip(labels, CLOSEOUT_LABELS), start=1):
        if not line.startswith(label):
            errors.append(f"implementation_closeout:label_{index}:{label}")
    for label in REQUIRED_CLOSEOUT_IDENTIFIERS:
        matching = next((line for line in labels if line.startswith(label)), "")
        value = matching[len(label):].strip() if matching else ""
        if _is_forbidden_identifier_value(value):
            errors.append(f"implementation_closeout:identifier_required:{label}")
            continue
        if label == "诏令编号：" and not _is_formal_court_code(value):
            errors.append("implementation_closeout:court_code_shape")
        if label == "古制谱系：" and not _is_formal_content_lineage(value):
            errors.append("implementation_closeout:content_lineage_shape")
    receipt = fixture.get("archive_receipt")
    if not isinstance(receipt, dict):
        errors.append("implementation_closeout:archive_receipt_required")
        return
    if receipt.get("schema") != "court.shiguan_archive_checkpoint_receipt.v1":
        errors.append("implementation_closeout:archive_receipt_schema")
    for field in ("receipt_id", "receipt_sha256", "archive_sha256", "court_code", "lineage_display"):
        value = receipt.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"implementation_closeout:archive_receipt_missing:{field}")
    expected = {
        "诏令编号：": str(receipt.get("court_code") or ""),
        "古制谱系：": str(receipt.get("lineage_display") or ""),
    }
    for label, expected_value in expected.items():
        matching = next((line for line in labels if line.startswith(label)), "")
        actual = matching[len(label):].strip() if matching else ""
        if actual != expected_value:
            errors.append(f"implementation_closeout:archive_receipt_mismatch:{label}")


def _is_forbidden_identifier_value(value: str) -> bool:
    folded = value.strip().casefold()
    if folded in {item.casefold() for item in FORBIDDEN_IDENTIFIER_VALUES}:
        return True
    if folded.startswith("未生成"):
        return True
    return any(token.casefold() in folded for token in ("pending_archive_assignment", "not_applicable"))


def _is_formal_court_code(value: str) -> bool:
    match = COURT_CODE_PATTERN.fullmatch(value.strip())
    if match is None:
        return False
    try:
        datetime.strptime(match.group("date"), "%Y%m%d")
    except ValueError:
        return False
    return True


def _is_formal_content_lineage(value: str) -> bool:
    candidate = value.strip()
    if any(pattern.search(candidate) for pattern in FORBIDDEN_LINEAGE_PROTOCOL_PATTERNS):
        return False
    parts = candidate.split("·")
    if len(parts) != 7 or parts[0] != "史馆总纪":
        return False
    for part, suffix in zip(parts[1:], LINEAGE_LAYER_SUFFIXES):
        if not part.endswith(suffix):
            return False
        name = part[: -len(suffix)].strip()
        if not name or name + suffix != part:
            return False
    return True


def _identifier_contract_errors() -> list[str]:
    errors: list[str] = []
    validators = {
        "court_code": _is_formal_court_code,
        "content_lineage": _is_formal_content_lineage,
    }
    for case_name, value_kind, value, expected in IDENTIFIER_CONTRACT_CASES:
        validator = validators[value_kind]
        actual = validator(value)
        if actual != expected:
            errors.append(f"identifier_contract:{case_name}:{actual}!={expected}")
    return errors


def _check_partial_status(lines: list[str], errors: list[str]) -> None:
    if len(lines) < 2:
        return
    if "PARTIAL | NOT_RUN" in lines[1]:
        errors.append("partial_or_not_run:placeholder_status_literal")
    if not re.match(r"^验收证据：(PARTIAL|NOT_RUN)(?:；|;|$)", lines[1]):
        errors.append("partial_or_not_run:evidence_status")


def _check_handoff_status(lines: list[str], errors: list[str]) -> None:
    if not lines:
        return
    if not re.match(r"^太子回奏：(HANDOFF|PAUSED)$", lines[0]):
        errors.append("handoff_or_pause:status")


def _label_for_line(line: str) -> str:
    if "：" in line:
        return line.split("：", 1)[0] + "："
    return ""


def _check_voice_and_length(family: str, lines: list[str], errors: list[str]) -> None:
    joined = "\n".join(lines)
    for term in FORBIDDEN_GENERIC_VOICE:
        if re.search(re.escape(term), joined, flags=re.IGNORECASE):
            errors.append(f"{family}:generic_voice:{term}")
    if family not in {"implementation_closeout", "verified_done"}:
        allowed_starts = ("太子回奏：", "太子上奏下一项问题：", "门下省封驳：", "上奏：")
        if not lines or not lines[0].startswith(allowed_starts):
            errors.append(f"{family}:missing_office_self_reference")

    for line in lines:
        label = _label_for_line(line)
        value = line[len(label):] if label else line
        if label in LONG_ALLOWED_LABELS:
            if len(value) > MAX_ALLOWED_LONG_FIELD_CHARS:
                errors.append(f"{family}:{label}too_long:{len(value)}>{MAX_ALLOWED_LONG_FIELD_CHARS}")
            if len(value) > MAX_CONCISE_FIELD_CHARS and not any(term in value for term in LOGIC_TERMS):
                errors.append(f"{family}:{label}long_without_logic")
        elif len(value) > MAX_CONCISE_FIELD_CHARS:
            errors.append(f"{family}:{label or 'line'}too_long:{len(value)}>{MAX_CONCISE_FIELD_CHARS}")


def evaluate(root: Path | None = None) -> dict[str, object]:
    errors: list[str] = []
    identifier_contract_errors = _identifier_contract_errors()
    errors.extend(identifier_contract_errors)
    path = fixture_path(root)
    data, load_error = _load_json(path)
    if load_error:
        errors.append(load_error)
        return {
            "response_draft_fixture_gate": "FAILED",
            "identifier_contract_gate": "FAILED" if identifier_contract_errors else "PASSED",
            "identifier_contract_cases": len(IDENTIFIER_CONTRACT_CASES),
            "path": str(path),
            "families": 0,
            "errors": errors,
        }
    assert data is not None
    if data.get("schema") != "court_response_draft_fixtures.v1":
        errors.append("schema")
    fixtures = data.get("families")
    if not isinstance(fixtures, list):
        errors.append("families_not_list")
        fixtures = []

    expected_families = list(SAMPLE_FAMILIES)
    if not expected_families:
        errors.append("sample_families_unavailable")
    seen: set[str] = set()
    for item in fixtures:
        if not isinstance(item, dict):
            errors.append("fixture_not_object")
            continue
        family = item.get("family")
        if not isinstance(family, str):
            errors.append("fixture_missing_family")
            continue
        if family in seen:
            errors.append(f"{family}:duplicate")
        seen.add(family)
        if family not in expected_families:
            errors.append(f"{family}:unknown_family")
            continue
        if item.get("expected_gate") != "PASSED":
            errors.append(f"{family}:expected_gate_not_passed")
        draft = item.get("draft")
        if not isinstance(draft, str) or not draft.strip():
            errors.append(f"{family}:empty_draft")
            continue
        lines = _nonempty_lines(draft)
        if family == "implementation_closeout":
            _check_closeout(lines, item, errors)
        elif family == "code_review":
            if len(lines) < 4:
                errors.append("code_review:too_few_lines")
            if not lines[0].startswith("门下省封驳："):
                errors.append("code_review:missing_menxia_self_reference")
            if not any(line.startswith(("- 阻断 ", "- 高风险 ", "- 中风险 ", "- 低风险 ")) for line in lines[1:-2]):
                errors.append("code_review:missing_ordered_finding")
            if not lines[-2].startswith("余险："):
                errors.append("code_review:missing_余险")
            if not lines[-1].startswith("简要结论："):
                errors.append("code_review:missing_简要结论")
            for line in lines[1:-2]:
                if line and not line.startswith(("- 阻断 ", "- 高风险 ", "- 中风险 ", "- 低风险 ")):
                    errors.append("code_review:unexpected_line")
        else:
            if family not in FAMILY_LINE_PREFIXES:
                errors.append(f"{family}:missing_line_contract")
            else:
                _check_ordered_prefixes(family, lines, errors)
            if family == "partial_or_not_run":
                _check_partial_status(lines, errors)
            if family == "handoff_or_pause":
                _check_handoff_status(lines, errors)
        _check_voice_and_length(family, lines, errors)

    missing = sorted(set(expected_families) - seen)
    extra = sorted(seen - set(expected_families))
    for family in missing:
        errors.append(f"{family}:missing_fixture")
    for family in extra:
        errors.append(f"{family}:extra_fixture")
    if len(fixtures) != len(expected_families):
        errors.append(f"fixture_count:{len(fixtures)}!={len(expected_families)}")

    gate = "PASSED" if not errors else "FAILED"
    return {
        "response_draft_fixture_gate": gate,
        "identifier_contract_gate": "FAILED" if identifier_contract_errors else "PASSED",
        "identifier_contract_cases": len(IDENTIFIER_CONTRACT_CASES),
        "path": str(path),
        "families": len(fixtures),
        "closeout_labels": len(CLOSEOUT_LABELS),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["response_draft_fixture_gate"] == "PASSED":
        print(
            "RESPONSE_DRAFT_FIXTURES_OK "
            f"families={result['families']} "
            f"closeout_labels={result['closeout_labels']}"
        )
    else:
        print("RESPONSE_DRAFT_FIXTURES_FAILED")
        for error in result["errors"]:
            print(error)
    return 0 if result["response_draft_fixture_gate"] == "PASSED" else 2


if __name__ == "__main__":
    sys.exit(main())
