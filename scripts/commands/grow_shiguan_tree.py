"""Grow the built-in Shiguan memory tree from the recall index."""

from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True

from shiguan_entry_utils import enrich_entry
from shiguan_paths import code_root, ensure_shared_seed, reference_path, references_root, resolve_source


def skill_root() -> Path:
    return code_root()


def index_path() -> Path:
    ensure_shared_seed()
    return reference_path("shiguan-index.jsonl")


def tree_root() -> Path:
    ensure_shared_seed()
    return reference_path("shiguan-tree")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = value.strip("-")
    return value[:64] or "leaf"


def quote_yaml(value: object) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def yaml_list(values: object) -> str:
    if not isinstance(values, list) or not values:
        return "[]"
    return "[" + ", ".join(quote_yaml(value) for value in values) + "]"


def list_text(values: object) -> str:
    if isinstance(values, list):
        return ", ".join(str(value) for value in values if str(value).strip())
    return str(values or "")


def load_entries() -> list[dict[str, object]]:
    path = index_path()
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


def lineage_parts(entry: dict[str, object]) -> dict[str, str]:
    parts = entry.get("lineage_parts")
    if isinstance(parts, dict):
        return {str(key): str(value) for key, value in parts.items()}
    enrich_entry(entry)
    return {str(key): str(value) for key, value in entry.get("lineage_parts", {}).items()}


def branch_for(entry: dict[str, object]) -> tuple[str, str]:
    parts = lineage_parts(entry)
    key = str(entry.get("lineage_key") or "/".join(slugify(parts.get(name, "")) for name in ("zhi", "men", "gang", "mu", "tiao")))
    title = "·".join(parts.get(name, "") for name in ("zhi", "men", "gang", "mu", "tiao") if parts.get(name))
    return key or "unclassified", title or "未分类"


def leaf_name(entry: dict[str, object]) -> str:
    time_text = str(entry.get("time", "unknown")).replace(":", "").replace("-", "")
    topic = slugify(str(entry.get("topic", "shiguan")))
    phase = slugify(str(entry.get("phase", "checkpoint")))
    return f"{time_text}-{topic}-{phase}.md"


def leaf_title(entry: dict[str, object]) -> str:
    parts = lineage_parts(entry)
    topic = str(parts.get("zhao") or entry.get("topic") or "史馆叶")
    phase = str(entry.get("phase", "checkpoint"))
    return f"{topic} / {phase}"


def mirrored_source_path(source_path: Path) -> Path | None:
    source_path = source_path.resolve()
    refs = references_root().resolve()
    tree = tree_root().resolve()
    try:
        relative = source_path.relative_to(refs)
    except ValueError:
        relative = None
    if relative and relative.parts:
        if relative.parts[0] in {"plan-archives", "memory-decisions"}:
            return tree / "sources" / relative
        if len(relative.parts) >= 2 and relative.parts[0] == "shiguan-tree" and relative.parts[1] == "manual":
            return tree / "sources" / relative
    return None


def source_link_for_leaf(source: str, leaf_path: Path) -> str:
    if not source:
        return ""
    source_path = resolve_source(source)
    if not source_path.exists() or not source_path.is_file():
        return ""
    mirror = mirrored_source_path(source_path)
    if mirror is not None:
        mirror.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source_path, mirror)
            return os.path.relpath(mirror, leaf_path.parent).replace("\\", "/")
        except OSError:
            return os.path.relpath(source_path, leaf_path.parent).replace("\\", "/")
    return os.path.relpath(source_path, leaf_path.parent).replace("\\", "/")


def write_leaf(entry: dict[str, object], branch_key: str, branch_title: str) -> Path:
    leaves_dir = tree_root() / "leaves"
    leaves_dir.mkdir(parents=True, exist_ok=True)
    path = leaves_dir / leaf_name(entry)
    title = leaf_title(entry)
    source = str(entry.get("source", ""))
    source_link = source_link_for_leaf(source, path)
    lines = [
        "---",
        "type: shiguan_leaf",
        f"title: {quote_yaml(title)}",
        f"topic: {quote_yaml(entry.get('topic', ''))}",
        f"display_title: {quote_yaml(title)}",
        f"phase: {quote_yaml(entry.get('phase', ''))}",
        f"status: {quote_yaml(entry.get('status', ''))}",
        f"time: {quote_yaml(entry.get('time', ''))}",
        f"branch: {quote_yaml(branch_key)}",
        f"lineage: {quote_yaml(entry.get('lineage_display') or entry.get('ancient_lineage', ''))}",
        f"court_code: {quote_yaml(entry.get('court_code', ''))}",
        f"memory_decision: {quote_yaml(entry.get('memory_decision', ''))}",
        f"keywords: {yaml_list(entry.get('keywords', []))}",
        f"key_actions: {yaml_list(entry.get('key_actions', []))}",
        f"capability_vector_kind: {quote_yaml(entry.get('capability_vector_kind', ''))}",
        f"capability_vector_terms: {yaml_list(entry.get('capability_vector_terms', []))}",
        f"capability_source_paths: {yaml_list(entry.get('capability_source_paths', []))}",
        f"source: {quote_yaml(source)}",
        "---",
        "",
        f"# {title}",
        "",
        f"谱系: {entry.get('lineage_display') or entry.get('ancient_lineage', '')}",
        f"诏令编号: `{entry.get('court_code', '')}`",
        f"Branch: [[branches/{branch_key}|{branch_title}]]",
        "",
        "## 关键词",
        "",
        "- 中文: " + list_text(entry.get("keywords_zh", [])),
        "- English: " + list_text(entry.get("keywords_en", [])),
        "",
        "## 能力谱系向量",
        "",
        f"- kind: {entry.get('capability_vector_kind', '')}",
        "- terms: " + list_text(entry.get("capability_vector_terms", [])),
        "- paths: " + list_text(entry.get("capability_source_paths", [])),
        "",
        "## 摘要",
        "",
        str(entry.get("display_summary_zh") or entry.get("keyword_summary_zh") or "未记录中文摘要。"),
        "",
        "## 理由",
        "",
        str(entry.get("display_reason_zh") or entry.get("memory_reason") or entry.get("next") or "未记录长期记忆理由。"),
        "",
        "## 源字段/原文",
        "",
        f"- zh: {entry.get('keyword_summary_zh', '')}",
        f"- en: {entry.get('keyword_summary_en', '')}",
        "",
        "原始 summary:",
        "",
        str(entry.get("summary", "")),
        "",
        "## Keywords",
        "",
        "- zh: " + ", ".join(str(item) for item in entry.get("keywords_zh", [])),
        "- en: " + ", ".join(str(item) for item in entry.get("keywords_en", [])),
        "",
        "## Key Actions",
        "",
    ]
    for action in entry.get("key_actions", []):
        lines.append(f"- {action}")
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            str(entry.get("evidence", "")),
            "",
            "## Memory",
            "",
            f"- decision: {entry.get('memory_decision', '')}",
            f"- content: {entry.get('memory_content', '')}",
            f"- reason: {entry.get('memory_reason', '')}",
            "",
            "## Source",
            "",
            f"- [{source}]({source_link})" if source_link else "- none",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return path


def write_branch(branch_key: str, title: str, entries: list[dict[str, object]], leaf_paths: list[Path]) -> Path:
    branches_dir = tree_root() / "branches"
    branches_dir.mkdir(parents=True, exist_ok=True)
    path = branches_dir / f"{branch_key}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    lines = [
        "---",
        "type: shiguan_branch",
        f"branch: {quote_yaml(branch_key)}",
        f"title: {quote_yaml(title)}",
        f"updated_at: {quote_yaml(now)}",
        f"leaf_count: {len(entries)}",
        "---",
        "",
        f"# {title}",
        "",
        "## 分类规则",
        "",
        "此分支按记录内容进入史馆谱系，不按执行阶段、记忆裁定或部门动作分类。树叶仍是证据，稳定成例仍须门下封驳。",
        "",
        "## 树叶",
        "",
    ]
    for entry, leaf_path in zip(entries, leaf_paths):
        rel = leaf_path.relative_to(tree_root()).as_posix()
        link = leaf_path.relative_to(tree_root()).with_suffix("").as_posix()
        lines.append(f"- [[{link}|{leaf_title(entry)}]] (`{rel}`)")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def write_root(branch_paths: list[Path], leaf_paths: list[Path]) -> None:
    root = tree_root()
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    lines = [
        "---",
        "type: shiguan_root",
        f"updated_at: {quote_yaml(now)}",
        f"branch_count: {len(branch_paths)}",
        f"leaf_count: {len(leaf_paths)}",
        "---",
        "",
        "# 史馆生长树",
        "",
        "这是 Decretum Matrix 内置史馆记忆树。它使用内容谱系组织，Markdown 优先并兼容 Obsidian。",
        "",
        "谱系层级：史馆总纪 -> 志 -> 门 -> 纲 -> 目 -> 条 -> 诏 -> 实录。",
        "",
        "每片树叶至少提供中文关键词、摘要和理由；原始 summary、evidence、memory_content 仍保留为原文字段。",
        "",
    ]
    if (root / "capability-index" / "_index.md").exists():
        lines.extend(
            [
                "## Capability Index",
                "",
                "- [[capability-index/_index|能力官籍索引]]",
                "",
            ]
        )
    lines.extend(
        [
        "## Branches",
        "",
        ]
    )
    for path in branch_paths:
        rel = path.relative_to(root).with_suffix("").as_posix()
        lines.append(f"- [[{rel}|{rel.replace('branches/', '')}]]")
    lines.extend(
        [
            "",
            "## Latest Leaves",
            "",
        ]
    )
    for path in sorted(leaf_paths, key=lambda value: value.name, reverse=True)[:20]:
        rel = path.relative_to(root).with_suffix("").as_posix()
        lines.append(f"- [[{rel}|{path.stem}]]")
    (root / "_index.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_schema() -> None:
    meta_dir = tree_root() / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "schema.md").write_text(
        "\n".join(
            [
                "---",
                "type: shiguan_schema",
                "---",
                "",
                "# Shiguan Growth Tree Schema",
                "",
                "- raw layer: `references/plan-archives/` and `references/memory-decisions/`",
                "- Obsidian source mirror: `sources/plan-archives/`, `sources/memory-decisions/`, and `sources/shiguan-tree/manual/` inside this vault",
                "- recall layer: `references/shiguan-index.jsonl`",
                "- growth layer: this Markdown tree",
                "- lineage: `史馆总纪 -> 志 -> 门 -> 纲 -> 目 -> 条 -> 诏 -> 实录`",
                "- branch: content lineage, never workflow phase or memory decision",
                "- leaf: one checkpoint or memory decision with evidence and source links",
                "- required display: Chinese keywords, summary, and reason",
                "- growth actions: add leaf, merge branch, promote stable rule, prune stale claim, graft cross-project evidence",
                "- Obsidian compatibility: Markdown frontmatter, wikilinks, relative source links",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )


def prune_generated_tree(branch_paths: list[Path], leaf_paths: list[Path]) -> None:
    expected = {path.resolve() for path in branch_paths + leaf_paths}
    for folder in (tree_root() / "branches", tree_root() / "leaves"):
        if not folder.exists():
            continue
        for path in folder.rglob("*.md"):
            if path.resolve() not in expected:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        for path in sorted(folder.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            try:
                if path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
            except FileNotFoundError:
                pass


def grow_tree() -> tuple[int, Path]:
    entries = load_entries()
    root = tree_root()
    root.mkdir(parents=True, exist_ok=True)
    write_schema()
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for entry in entries:
        grouped[branch_for(entry)].append(entry)

    branch_paths: list[Path] = []
    leaf_paths: list[Path] = []
    for (branch_key, title), branch_entries in sorted(grouped.items()):
        paths = [write_leaf(entry, branch_key, title) for entry in branch_entries]
        leaf_paths.extend(paths)
        branch_paths.append(write_branch(branch_key, title, branch_entries, paths))
    prune_generated_tree(branch_paths, leaf_paths)
    write_root(branch_paths, leaf_paths)
    return len(entries), root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    count, root = grow_tree()
    if not args.quiet:
        print(f"SHIGUAN_TREE_OK {root} entries={count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())



