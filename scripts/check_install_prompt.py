#!/usr/bin/env python3
"""Validate the portable, current-tool-only installation prompt."""

from __future__ import annotations

from pathlib import Path
import sys


sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "INSTALL-PROMPT.md"

REQUIRED = (
    "required_target = .agents",
    "default_optional_target = current_agent_tool_only",
    "extra_targets = explicit_latest_user_request_only",
    "fanout = forbidden",
    "CURRENT_AGENT_TOOL",
    "CURRENT_TOOL_SKILL_ROOT",
    "CURRENT_TOOL_ROOT_UNPROVEN",
    "当前是 Codex：只安装 `.agents` 和 Codex；不得安装 Claude 或 Hermes。",
    "当前是 Claude：只安装 `.agents` 和 Claude；不得安装 Codex 或 Hermes。",
    "当前是 Hermes：只安装 `.agents` 和 Hermes；不得安装 Codex 或 Claude。",
    "只有用户最新指令明确点名其他工具时",
    "不得扫描后自动向所有工具分发",
    "不得运行会向未点名工具扩散的 `sync_active_copies.py --write`",
    "无删除覆盖",
    "SOURCE_MISSING",
)

FORBIDDEN = (
    "C:\\Users\\",
    "$HOME\\.codex",
    "$HOME\\.claude",
    "$HOME\\.hermes",
)


def evaluate() -> list[str]:
    if not PROMPT.is_file():
        return ["missing:INSTALL-PROMPT.md"]
    text = PROMPT.read_text(encoding="utf-8")
    errors = [f"missing:{item}" for item in REQUIRED if item not in text]
    errors.extend(f"hardcoded-path:{item}" for item in FORBIDDEN if item in text)
    if text.count("```text") != 1 or text.count("```") != 2:
        errors.append("install-policy-block:invalid")
    return errors


def main() -> int:
    errors = evaluate()
    if errors:
        print("INSTALL_PROMPT_FAILED")
        for error in errors:
            print(error)
        return 2
    print("INSTALL_PROMPT_OK required=.agents optional=current_agent_tool_only extra=explicit_only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
