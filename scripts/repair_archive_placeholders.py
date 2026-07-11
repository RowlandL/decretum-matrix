#!/usr/bin/env python
"""Replace stale archive_checkpoint placeholders in Shiguan archive records.

Preserve-only repair: edits only the placeholder text inside existing archive
records by using the nearest preceding checkpoint's generated court_code and
ancient_lineage. It does not delete records or other user/source text.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import re
from pathlib import Path

from shiguan_paths import code_root, ensure_shared_seed, reference_path


def skill_root() -> Path:
    return code_root()


def archive_root() -> Path:
    ensure_shared_seed()
    return reference_path("plan-archives")


COURT_RE = re.compile(r"^- court_code: (\S.*)$", re.MULTILINE)
LINEAGE_RE = re.compile(r"^- ancient_lineage: (\S.*)$", re.MULTILINE)


def repair_text(text: str) -> tuple[str, int]:
    changed = 0
    output: list[str] = []
    current_code = ""
    current_lineage = ""
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        newline = line[len(stripped):]
        if stripped.startswith("- court_code: "):
            current_code = stripped.split(": ", 1)[1].strip()
        elif stripped.startswith("- ancient_lineage: "):
            current_lineage = stripped.split(": ", 1)[1].strip()
        if stripped.startswith("诏令编号：") and current_code:
            replacement = f"诏令编号：{current_code}{newline}"
            output.append(replacement)
            changed += int(line != replacement)
            continue
        if stripped.startswith("古制谱系：") and current_lineage:
            replacement = f"古制谱系：{current_lineage}{newline}"
            output.append(replacement)
            changed += int(line != replacement)
            continue
        if "待 archive_checkpoint 生成" in stripped or "占位符由 archive_checkpoint 自动回填" in stripped:
            line = line.replace("待 archive_checkpoint 生成", "archive_checkpoint 生成前占位符")
            line = line.replace("占位符由 archive_checkpoint 自动回填", "archive_checkpoint 生成前占位符")
            changed += 1
        output.append(line)
    return "".join(output), changed


def main() -> int:
    total = 0
    files = 0
    for path in sorted(archive_root().glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        repaired, changed = repair_text(text)
        if changed:
            path.write_text(repaired, encoding="utf-8", newline="\n")
            total += changed
            files += 1
            print(f"REPAIRED {path} placeholders={changed}")
    print(f"PLACEHOLDER_REPAIR_OK files={files} placeholders={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
