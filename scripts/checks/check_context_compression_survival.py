"""Validate court context-compression survival rules and fixtures."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SHARD = ROOT / "references" / "sections" / "court-context-compression-survival.md"
FIXTURE = ROOT / "references" / "fixtures" / "context-compression-survival.json"

REQUIRED_SHARD_TERMS = [
    "Compression Survival Capsule",
    "Multi-Cycle Restore Procedure",
    "original_decree_anchor",
    "original_decree_sha256",
    "plan_anchor",
    "plan_sha256",
    "active_skill: court-capability-router",
    "court-response-fewshot-format.md",
    "court-closeout-memorial-format.md",
    "reply_voice_contract",
    "reply_voice_markers",
    "forbidden_reply_voice",
    "我会",
    "我已经",
    "I will",
    "closeout_identifier_contract",
    "archive_receipt",
    "court.shiguan_archive_checkpoint_receipt.v1",
    "forbidden_closeout_identifier_values",
    "closeout_label_hash",
    "closeout_shard_on_demand",
    "metadata_precision",
    "body_reference_policy",
    "on_demand_loading",
    "compression_survival_gate=FAILED",
]

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

TOKEN_POLICY = ["metadata_precision", "body_reference_policy", "on_demand_loading"]
COURT_FLOW = "太子定性 -> 三省会审 -> 三省上奏 -> 太子回奏 -> 尚书统六部 -> 工坊办差 -> 门下复核 -> 史馆实录"
REPLY_VOICE_CONTRACT = "court_office_self_reference"
REPLY_VOICE_MARKERS = ["作业AI：", "门下裁定：", "太子回奏："]
FORBIDDEN_REPLY_VOICE = [
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
REQUIRED_CLOSEOUT_IDENTIFIERS = ["诏令编号：", "古制谱系："]
FORBIDDEN_CLOSEOUT_IDENTIFIER_VALUES = ["", "...", "…", "未生成", "pending_archive_assignment", "NOT_APPLICABLE"]
CLOSEOUT_IDENTIFIER_CONTRACT = "archive_checkpoint_receipt_required_for_implementation_closeout"
ARCHIVE_RECEIPT_SCHEMA = "court.shiguan_archive_checkpoint_receipt.v1"
REQUIRED_RELOADS = [
    "SKILL.md",
    "references/sections/court-context-compression-survival.md",
    "references/sections/court-response-fewshot-format.md",
]
CLOSEOUT_SHARD_ON_DEMAND = "references/sections/court-closeout-memorial-format.md"
CLOSEOUT_RELOAD_CONDITION = "label_hash_missing_or_mismatch_or_final_closeout_repair"
CLOSEOUT_LABEL_HASH = hashlib.sha256("\n".join(CLOSEOUT_LABELS).encode("utf-8")).hexdigest()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"missing:{path}"
    except json.JSONDecodeError as exc:
        return None, f"invalid_json:{exc}"
    if not isinstance(data, dict):
        return None, "fixture_root_not_object"
    return data, None


def _line_value(text: str, label: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(label):
            return line[len(label):].strip()
    return None


def _is_forbidden_identifier_value(value: str) -> bool:
    folded = value.strip().casefold()
    if folded in {item.casefold() for item in FORBIDDEN_CLOSEOUT_IDENTIFIER_VALUES}:
        return True
    if folded.startswith("未生成"):
        return True
    return any(token.casefold() in folded for token in ("pending_archive_assignment", "not_applicable"))


def _case_errors(
    case: dict[str, Any],
    original: str,
    plan: str,
    original_hash: str,
    plan_hash: str,
    default_reply_preview: str,
    default_archive_receipt: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    name = str(case.get("name", "unnamed"))
    if int(case.get("cycle_count", 0)) < 3:
        errors.append(f"{name}:cycle_count")
    if case.get("active_skill") != "court-capability-router":
        errors.append(f"{name}:active_skill")
    reloads = case.get("required_reload")
    if not isinstance(reloads, list):
        errors.append(f"{name}:required_reload_not_list")
        reloads = []
    for required in REQUIRED_RELOADS:
        if required not in reloads:
            errors.append(f"{name}:missing_reload:{required}")
    if CLOSEOUT_SHARD_ON_DEMAND in reloads:
        errors.append(f"{name}:closeout_shard_forced_reload")
    original_anchor = case.get("original_decree_anchor")
    if not isinstance(original_anchor, str) or original_anchor not in original:
        errors.append(f"{name}:original_decree_anchor")
    if case.get("original_decree_sha256") != original_hash:
        errors.append(f"{name}:original_decree_sha256")
    plan_anchor = case.get("plan_anchor")
    if not isinstance(plan_anchor, str) or plan_anchor not in plan:
        errors.append(f"{name}:plan_anchor")
    if case.get("plan_sha256") != plan_hash:
        errors.append(f"{name}:plan_sha256")
    if case.get("court_flow_anchor") != COURT_FLOW:
        errors.append(f"{name}:court_flow_anchor")
    if case.get("reply_family") != "implementation_closeout":
        errors.append(f"{name}:reply_family")
    reply_preview = case.get("restored_reply_preview", default_reply_preview)
    if not isinstance(reply_preview, str) or not reply_preview.strip():
        errors.append(f"{name}:restored_reply_preview")
        reply_preview = ""
    for marker in REPLY_VOICE_MARKERS:
        if marker not in reply_preview:
            errors.append(f"{name}:reply_voice_marker:{marker}")
    folded_preview = reply_preview.casefold()
    for term in FORBIDDEN_REPLY_VOICE:
        if term.casefold() in folded_preview:
            errors.append(f"{name}:generic_reply_voice:{term}")
    for label in REQUIRED_CLOSEOUT_IDENTIFIERS:
        value = _line_value(reply_preview, label)
        if value is None:
            errors.append(f"{name}:missing_closeout_identifier:{label}")
        elif _is_forbidden_identifier_value(value):
            errors.append(f"{name}:invalid_closeout_identifier:{label}")
    receipt = case.get("archive_receipt", default_archive_receipt)
    if not isinstance(receipt, dict):
        errors.append(f"{name}:archive_receipt_required")
    else:
        if receipt.get("schema") != ARCHIVE_RECEIPT_SCHEMA:
            errors.append(f"{name}:archive_receipt_schema")
        for field in (
            "receipt_id",
            "receipt_sha256",
            "archive_sha256",
            "court_code",
            "lineage_display",
        ):
            if not isinstance(receipt.get(field), str) or not str(receipt[field]).strip():
                errors.append(f"{name}:archive_receipt_missing:{field}")
        expected_by_label = {
            "诏令编号：": str(receipt.get("court_code") or ""),
            "古制谱系：": str(receipt.get("lineage_display") or ""),
        }
        for label, expected in expected_by_label.items():
            actual = _line_value(reply_preview, label)
            if actual is not None and not _is_forbidden_identifier_value(actual) and actual != expected:
                errors.append(f"{name}:archive_receipt_mismatch:{label}")
    if case.get("closeout_labels") != CLOSEOUT_LABELS:
        errors.append(f"{name}:closeout_labels")
    if case.get("closeout_label_hash") != CLOSEOUT_LABEL_HASH:
        errors.append(f"{name}:closeout_label_hash")
    if case.get("closeout_shard_on_demand") != CLOSEOUT_SHARD_ON_DEMAND:
        errors.append(f"{name}:closeout_shard_on_demand")
    if case.get("closeout_reload_condition") != CLOSEOUT_RELOAD_CONDITION:
        errors.append(f"{name}:closeout_reload_condition")
    if case.get("token_policy") != TOKEN_POLICY:
        errors.append(f"{name}:token_policy")
    return errors


def evaluate(root: Path | None = None) -> dict[str, object]:
    root = root or ROOT
    errors: list[str] = []
    shard = root / "references" / "sections" / "court-context-compression-survival.md"
    fixture = root / "references" / "fixtures" / "context-compression-survival.json"

    if not shard.exists():
        errors.append("missing_shard")
    else:
        text = shard.read_text(encoding="utf-8", errors="replace")
        for term in REQUIRED_SHARD_TERMS:
            if term not in text:
                errors.append(f"missing_shard_term:{term}")

    data, load_error = _load_json(fixture)
    if load_error:
        errors.append(load_error)
        data = {}
    assert data is not None
    if data.get("schema") != "court_context_compression_survival.v1":
        errors.append("schema")
    original = data.get("original_decree_text")
    plan = data.get("plan_text")
    if not isinstance(original, str) or not original:
        errors.append("original_decree_text")
        original = ""
    if not isinstance(plan, str) or not plan:
        errors.append("plan_text")
        plan = ""
    if data.get("reply_voice_contract") != REPLY_VOICE_CONTRACT:
        errors.append("reply_voice_contract")
    if data.get("reply_voice_markers") != REPLY_VOICE_MARKERS:
        errors.append("reply_voice_markers")
    if data.get("forbidden_reply_voice") != FORBIDDEN_REPLY_VOICE:
        errors.append("forbidden_reply_voice")
    if data.get("closeout_identifier_contract") != CLOSEOUT_IDENTIFIER_CONTRACT:
        errors.append("closeout_identifier_contract")
    if data.get("forbidden_closeout_identifier_values") != FORBIDDEN_CLOSEOUT_IDENTIFIER_VALUES:
        errors.append("forbidden_closeout_identifier_values")
    default_reply_preview = data.get("restored_reply_preview")
    if not isinstance(default_reply_preview, str) or not default_reply_preview.strip():
        errors.append("restored_reply_preview")
        default_reply_preview = ""
    default_archive_receipt = data.get("archive_receipt")
    if not isinstance(default_archive_receipt, dict):
        errors.append("archive_receipt")
        default_archive_receipt = None
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("cases")
        cases = []

    original_hash = _sha256(original) if original else ""
    plan_hash = _sha256(plan) if plan else ""
    pass_cases = 0
    fail_cases = 0
    for item in cases:
        if not isinstance(item, dict):
            errors.append("case_not_object")
            continue
        name = str(item.get("name", "unnamed"))
        expected = item.get("expected_gate")
        case_errors = _case_errors(
            item,
            original,
            plan,
            original_hash,
            plan_hash,
            default_reply_preview,
            default_archive_receipt,
        )
        expected_errors = item.get("expected_errors")
        if not isinstance(expected_errors, list):
            expected_errors = None
        if expected == "PASSED":
            pass_cases += 1
            for error in case_errors:
                errors.append(error)
            if expected_errors != []:
                errors.append(f"{name}:expected_errors_must_be_empty")
        elif expected == "FAILED":
            fail_cases += 1
            if expected_errors is None:
                errors.append(f"{name}:expected_errors_missing")
            elif sorted(str(error) for error in expected_errors) != sorted(case_errors):
                errors.append(
                    f"{name}:expected_errors_mismatch:"
                    f"expected={sorted(str(error) for error in expected_errors)}:"
                    f"actual={sorted(case_errors)}"
                )
            elif not case_errors:
                errors.append(f"{name}:expected_failure_not_detected")
        else:
            errors.append(f"{name}:expected_gate")

    if pass_cases < 1:
        errors.append("missing_pass_case")
    if fail_cases < 2:
        errors.append("too_few_fail_cases")

    gate = "PASSED" if not errors else "FAILED"
    return {
        "compression_survival_gate": gate,
        "path": str(fixture),
        "shard": str(shard),
        "original_decree_sha256": original_hash,
        "plan_sha256": plan_hash,
        "cases": len(cases),
        "pass_cases": pass_cases,
        "fail_cases": fail_cases,
        "closeout_labels": len(CLOSEOUT_LABELS),
        "closeout_label_hash": CLOSEOUT_LABEL_HASH,
        "reply_voice_contract": REPLY_VOICE_CONTRACT,
        "closeout_identifier_contract": CLOSEOUT_IDENTIFIER_CONTRACT,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["compression_survival_gate"] == "PASSED":
        print(
            "CONTEXT_COMPRESSION_SURVIVAL_OK "
            f"cases={result['cases']} "
            f"pass_cases={result['pass_cases']} "
            f"fail_cases={result['fail_cases']} "
            f"closeout_labels={result['closeout_labels']}"
        )
    else:
        print("CONTEXT_COMPRESSION_SURVIVAL_FAILED")
        for error in result["errors"]:
            print(error)
    return 0 if result["compression_survival_gate"] == "PASSED" else 2


if __name__ == "__main__":
    sys.exit(main())



