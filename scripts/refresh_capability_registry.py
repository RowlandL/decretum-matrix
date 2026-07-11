"""Refresh the court capability registry from local skills and agents.

This is a lightweight 吏部/户部 registry pass. It reads skill frontmatter and
standing-agent files, classifies each capability into likely court offices, and
rewrites the local catalog files used by court-capability-router.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from io import StringIO
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True

from shiguan_paths import ensure_shared_seed, reference_path


UNIT_RULES: list[tuple[str, str, list[str]]] = [
    ("Taizi", "太子", ["intake", "triage", "approval", "approve", "charter", "status", "zoom"]),
    ("Zhongshu", "中书省", ["plan", "planning", "prd", "spec", "research", "strategy", "architecture", "brainstorm"]),
    ("Menxia", "门下省", ["review", "risk", "audit", "guard", "careful", "critique", "grill", "verify"]),
    ("Shangshu", "尚书省", ["execute", "execution", "dispatch", "handoff", "parallel", "subagent", "worktree"]),
    ("Hubu", "户部", ["setup", "install", "health", "benchmark", "sync", "config", "update", "budget", "dependency"]),
    ("Libu", "礼部", ["document", "docs", "writing", "article", "report", "ppt", "teach", "pdf", "citation"]),
    ("Bingbu", "兵部", ["debug", "diagnose", "incident", "migration", "triage", "search-code", "failure"]),
    ("Xingbu", "刑部", ["security", "safe", "guard", "compliance", "pre-commit", "git", "destructive", "secret"]),
    ("Gongbu", "工部", ["code", "build", "prototype", "tdd", "test", "deploy", "browser", "ui", "image", "excel", "davinci"]),
    ("Libu-HR", "吏部", ["skill", "agent", "agente", "recruit", "capability", "find", "install", "selector"]),
    ("Shiguan", "史馆", ["memory", "archive", "history", "context", "obsidian", "record", "shiguan"]),
    ("Zaochao", "早朝", ["retro", "brief", "summary", "health", "landing-report"]),
]

DIMENSIONS = [
    ("身", "Environment fit, permissions, dependencies, sandbox and path boundaries."),
    ("言", "Clarification quality, report quality, and user-facing communication."),
    ("书", "Code/document structure, formatting, maintainability, and contract adherence."),
    ("判", "Judgment, risk recognition, tradeoff quality, and verifiable decisions."),
    ("德行", "Safety, honesty, respect for user changes, and no unauthorized scope expansion."),
    ("才用", "Domain skill, tool fluency, prior evidence, and task match."),
    ("劳效", "Delivery record, test evidence, reliability, defects, and corrections."),
]


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


FOLDED_FRONTMATTER_MARKERS = {">", ">-", ">+", "|", "|-", "|+"}


def clean_frontmatter_value(value: str) -> str:
    value = value.strip()
    if value in FOLDED_FRONTMATTER_MARKERS:
        return ""
    return value.strip("\"'").strip()


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = read_text(path)
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("---")
    block, sep, _ = rest.partition("---")
    if not sep:
        return {}
    data: dict[str, str] = {}
    current_key: str | None = None
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if match:
            current_key = match.group(1)
            value = clean_frontmatter_value(match.group(2))
            data[current_key] = value
            continue
        if current_key and raw_line.startswith((" ", "\t")):
            chunk = clean_frontmatter_value(raw_line)
            if chunk:
                data[current_key] = (data[current_key] + " " + chunk).strip()
    return {key: re.sub(r"\s+", " ", value).strip() for key, value in data.items()}


def short_description(text: str, limit: int = 150) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def score_units(name: str, description: str, path: Path) -> list[tuple[int, str]]:
    haystack = f"{name} {description} {path.as_posix()}".lower()
    scores: list[tuple[int, str]] = []
    for unit_key, _unit_zh, needles in UNIT_RULES:
        score = sum(1 for needle in needles if needle.lower() in haystack)
        if score:
            scores.append((score, unit_key))
    if not scores:
        scores.append((1, "Gongbu"))
    scores.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scores


def classify(name: str, description: str, path: Path) -> list[str]:
    return [unit for _score, unit in score_units(name, description, path)[:3]]


def fit_fields(name: str, description: str, path: Path) -> dict[str, object]:
    scores = score_units(name, description, path)
    top_score = scores[0][0]
    primary = [unit for score, unit in scores if score == top_score]
    secondary = [unit for score, unit in scores if score < top_score][:4]
    return {
        "primary_fit": primary[:3],
        "secondary_fit": secondary,
        "requires_review": len(primary) > 1 or top_score <= 1,
        "fit_score": top_score,
    }


def find_skill_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    ignored = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        "capability-index",
    }
    output: list[Path] = []
    for path in root.rglob("SKILL.md"):
        if any(part in ignored for part in path.parts):
            continue
        output.append(path)
    return sorted(output)


def collect_skills(root: Path, source: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in find_skill_files(root):
        frontmatter = parse_frontmatter(path)
        name = frontmatter.get("name") or path.parent.name
        description = frontmatter.get("description") or ""
        records.append(
            {
                "kind": "skill",
                "source": source,
                "name": name,
                "description": short_description(description),
                "path": str(path),
                "relative_path": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
                "court_units": classify(name, description, path),
                **fit_fields(name, description, path),
            }
        )
    return records


def collect_agents(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if not root.exists():
        return records
    for path in sorted(root.glob("*.toml")):
        text = read_text(path)
        name = path.stem
        match = re.search(r"(?m)^description\s*=\s*['\"](.+?)['\"]\s*$", text)
        description = match.group(1) if match else "Codex custom agent."
        records.append(
            {
                "kind": "agent",
                "source": "codex_agents",
                "name": name,
                "description": short_description(description),
                "path": str(path),
                "relative_path": path.name,
                "court_units": classify(name, description, path),
                **fit_fields(name, description, path),
            }
        )
    return records


def command_output(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=8, check=False)
    except Exception:
        return ""
    return (result.stdout or result.stderr or "").strip()


def resolve_command(command: str) -> str:
    resolved = shutil.which(command)
    if resolved:
        return resolved
    script_roots = [
        Path.home() / "AppData" / "Roaming" / "Python" / "Python314" / "Scripts",
        Path.home() / "AppData" / "Roaming" / "Python" / "Scripts",
    ]
    for root in script_roots:
        for suffix in (".exe", ".cmd", ".bat", ".ps1", ""):
            candidate = root / f"{command}{suffix}"
            if candidate.exists():
                return str(candidate)
    return ""


def probe_command_version(executable: str, probe_args: list[list[str]]) -> str:
    for args in probe_args:
        output = command_output([executable, *args])
        if output:
            return output.splitlines()[0]
    return ""


def collect_cli_state() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for command, use_when, probe_args in (
        ("codex", "Run or inspect Codex CLI, sandbox, approvals, MCPs, and agents.", [["--version"]]),
        ("node", "JavaScript tooling runtime.", [["--version"]]),
        ("npm", "JavaScript package manager.", [["--version"]]),
        (
            "cli-anything-wps",
            "Agent CLI harness capability for WPS Office Writer/Calc/Impress, documents, spreadsheets, PPT, PDF export, and JSON-driven presentation builds.",
            [["--version"], ["--help"]],
        ),
        (
            "cli-anything-zotero",
            "Agent CLI harness capability for Zotero desktop, citation, bibliography, literature research, notes, collections, and academic workflow skills.",
            [["--version"], ["--help"]],
        ),
        (
            "cli-anything-photoshop",
            "Agent CLI harness capability for Adobe Photoshop COM automation, image editing, layers, text, selections, project export, and dry-run workflows.",
            [["--version"], ["--help"]],
        ),
    ):
        executable = resolve_command(command)
        if executable:
            version = probe_command_version(executable, probe_args)
            records.append(
                {
                    "kind": "cli",
                    "source": "path",
                    "name": command,
                    "description": use_when,
                    "version": version or "available",
                    "path": executable,
                    "relative_path": f"cli:{command}",
                    "court_units": classify(command, use_when, Path(command)),
                    **fit_fields(command, use_when, Path(command)),
                }
            )
    return records


def collect_mcp_state() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    config = codex_home() / "config.toml"
    names: set[str] = set()
    if config.exists():
        text = read_text(config)
        for match in re.finditer(r"(?m)^\[(?:mcp_servers|mcp)\.([^\]]+)\]\s*$", text):
            names.add(match.group(1).strip().strip("\"'"))
    output = command_output(["codex", "mcp", "list"])
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith(("name", "configured", "no ")):
            continue
        name = re.split(r"\s+", line, maxsplit=1)[0].strip()
        if name and re.match(r"^[A-Za-z0-9_.-]+$", name):
            names.add(name)
    for name in sorted(names):
        description = f"Codex MCP server `{name}` from local Codex MCP configuration/list."
        records.append(
            {
                "kind": "mcp",
                "source": "codex_mcp",
                "name": name,
                "description": short_description(description),
                "path": str(config),
                "relative_path": f"mcp:{name}",
                "court_units": classify(name, description, Path(name)),
                **fit_fields(name, description, Path(name)),
            }
        )
    return records


def department_table(records: list[dict[str, object]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {unit: [] for unit, _zh, _terms in UNIT_RULES}
    for record in records:
        label = f"`{record['name']}`"
        for unit in record.get("court_units", []):
            grouped.setdefault(str(unit), []).append(label)
    return {unit: sorted(set(values)) for unit, values in grouped.items()}


def write_manifest(records: list[dict[str, object]]) -> Path:
    path = reference_path("installed-capabilities-manifest.json")
    path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "generator": "refresh_capability_registry.py",
                "roots": {
                    "codex_home": str(codex_home()),
                    "codex_skills": str(codex_home() / "skills"),
                    "codex_system_skills": str(codex_home() / "skills" / ".system"),
                    "codex_agents": str(codex_home() / "agents"),
                    "agent_fallback_skills": str(Path.home() / ".agents" / "skills"),
                },
                "counts": {
                    "skills": sum(1 for item in records if item.get("kind") == "skill"),
                    "agents": sum(1 for item in records if item.get("kind") == "agent"),
                    "mcp": sum(1 for item in records if item.get("kind") == "mcp"),
                    "cli": sum(1 for item in records if item.get("kind") == "cli"),
                },
                "capabilities": records,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_skills_catalog(records: list[dict[str, object]]) -> Path:
    path = reference_path("installed-skills-catalog.md")
    skills = [record for record in records if record.get("kind") == "skill"]
    lines = [
        "# Installed Skills Catalog",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "This local catalog is regenerated from skill frontmatter. It is a routing aid, not a permission grant.",
        "",
        "| Skill | Source | Court fit | Description |",
        "| --- | --- | --- | --- |",
    ]
    for record in sorted(skills, key=lambda item: (str(item.get("source")), str(item.get("name")))):
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{record.get('name', '')}`",
                    str(record.get("source", "")),
                    ", ".join(str(item) for item in record.get("court_units", [])),
                    str(record.get("description", "")).replace("|", "\\|"),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def write_capabilities_catalog(records: list[dict[str, object]]) -> Path:
    path = reference_path("installed-capabilities-catalog.md")
    grouped = department_table(records)
    unit_lookup = {key: zh for key, zh, _terms in UNIT_RULES}
    lines = [
        "# Installed Capabilities Catalog",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "Mode: local refresh by `scripts/refresh_capability_registry.py`",
        "",
        "This catalog covers local skills, standing Codex agents, and selected CLI tools. It is regenerated when new skills are installed so 吏部 can classify and 尚书省 can dispatch them under `/court`.",
        "",
        "Index-first invocation rule: when a task implies a suitable local skill, agente, MCP, CLI, or script, consult this catalog and `scripts/check_capability_index_gate.py --query <need>` first, then call only the selected bounded capability under the active authority. Do not wait for the user to name the capability, and do not invoke every matching candidate.",
        "",
        "Minimum portable court prerequisites:",
        "",
        "- `%CODEX_HOME%\\skills\\find-skills\\SKILL.md`",
        "- `%CODEX_HOME%\\skills\\.system\\skill-creator\\SKILL.md`",
        "- `%CODEX_HOME%\\skills\\.system\\skill-creator\\scripts\\quick_validate.py`",
        "",
        "## Capability Verification Index Skill Gate",
        "",
        "Before reporting a capability as absent, stale, or dispatchable, validate the active index layer from `references/sections/court-capability-verification-index.md`: refreshed/current catalog state, `find-skills`, system `skill-creator`, `quick_validate.py`, and `check_catalog.py --strict`.",
        "",
        "Report `capability_index_skill_gate=PASSED | PARTIAL | FAILED | authority_blocked | runtime_degraded` when capability verification or recruitment depends on this catalog.",
        "",
        "## Court Department Capability Map",
        "",
        "A capability may fit several offices. 吏部 evaluates capability dimensions first, then 尚书省 grants a task-specific 差遣.",
        "",
        "| Court Unit | Responsibility | Primary Local Capabilities |",
        "| --- | --- | --- |",
    ]
    responsibility = {
        "Taizi": "User-facing intake, decree charter, clarification relay, final 回奏.",
        "Zhongshu": "Decree drafting, research, planning, decomposition, acceptance criteria.",
        "Menxia": "封驳, risk and completeness review, final semantic review.",
        "Shangshu": "Executes approved decrees, commands 六部, integrates results.",
        "Hubu": "Resources, dependencies, environment, path permissions, capability inventory.",
        "Libu": "Ritual and text: reports, docs, teaching, citations, output contract.",
        "Bingbu": "Tactical operations: debugging, incident response, migrations.",
        "Xingbu": "Safety, compliance, destructive/paid/install/external-write gates.",
        "Gongbu": "Engineering works: implementation, build, QA, browser and external app operations.",
        "Libu-HR": "官籍 and 铨选: discover, score, recruit, appoint, and review capabilities.",
        "Shiguan": "史馆实录, bilingual recall, growth tree, knowledge graph, memory decisions.",
        "Zaochao": "Briefings, retrospectives, health and status summaries.",
    }
    for unit, _zh, _terms in UNIT_RULES:
        caps = ", ".join(grouped.get(unit, [])[:80]) or "`court-capability-router`"
        lines.append(f"| {unit} | {responsibility[unit]} | {caps} |")
    lines.extend(
        [
            "",
            "## Capability Registry Dimensions",
            "",
            "| Dimension | Meaning |",
            "| --- | --- |",
        ]
    )
    for dimension, meaning in DIMENSIONS:
        lines.append(f"| {dimension} | {meaning} |")
    lines.extend(
        [
            "",
            "## Refresh Rule",
            "",
            "After any skill, agent, MCP, CLI, or script recruitment, run:",
            "",
            "```powershell",
            "python .\\scripts\\refresh_capability_registry.py",
            "```",
            "",
            "Then `/court` can select the new capability from the refreshed 官籍 and assign it by explicit 差遣.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def md_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def markdown_table(records: list[dict[str, object]], limit: int | None = None) -> list[str]:
    rows = sorted(records, key=lambda item: (str(item.get("kind")), str(item.get("name"))))
    if limit is not None:
        rows = rows[:limit]
    lines = [
        "| Kind | Name | Source | Court fit | Path | Description |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for record in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(record.get("kind", "")),
                    "`" + md_cell(record.get("name", "")) + "`",
                    md_cell(record.get("source", "")),
                    md_cell(", ".join(str(item) for item in record.get("court_units", []))),
                    "`" + md_cell(record.get("relative_path", "")) + "`",
                    md_cell(record.get("description", "")),
                ]
            )
            + " |"
        )
    return lines


def csv_text(records: list[dict[str, object]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "kind",
            "name",
            "source",
            "court_units",
            "primary_fit",
            "requires_review",
            "fit_score",
            "relative_path",
            "description",
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    for record in sorted(records, key=lambda item: (str(item.get("kind")), str(item.get("name")))):
        writer.writerow(
            {
                "kind": record.get("kind", ""),
                "name": record.get("name", ""),
                "source": record.get("source", ""),
                "court_units": ";".join(str(item) for item in record.get("court_units", [])),
                "primary_fit": ";".join(str(item) for item in record.get("primary_fit", [])),
                "requires_review": record.get("requires_review", ""),
                "fit_score": record.get("fit_score", ""),
                "relative_path": record.get("relative_path", ""),
                "description": record.get("description", ""),
            }
        )
    return output.getvalue()


def unit_fragments(records: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {unit: [] for unit, _zh, _terms in UNIT_RULES}
    for record in records:
        for unit in record.get("court_units", []) or []:
            grouped.setdefault(str(unit), []).append(record)
    return {unit: rows for unit, rows in grouped.items() if rows}


def kind_fragments(records: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in records:
        grouped.setdefault(str(record.get("kind", "unknown")), []).append(record)
    return {kind: rows for kind, rows in sorted(grouped.items()) if rows}


def write_table(path: Path, title: str, records: list[dict[str, object]], note: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# {title}",
                "",
                note,
                "",
                *markdown_table(records),
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )


def write_fragment_tables(root: Path, records: list[dict[str, object]], obsidian_links: bool) -> list[str]:
    links: list[str] = []
    for unit, rows in unit_fragments(records).items():
        relative = Path("by-unit") / f"{unit}.md"
        write_table(
            root / relative,
            f"{unit} Capability Fragment",
            rows,
            "Office-scoped capability fragment. Load this instead of the full table when the task already maps to this office.",
        )
        if obsidian_links:
            links.append(f"- [[capability-index/{relative.with_suffix('').as_posix()}|{unit}]] ({len(rows)})")
        else:
            links.append(f"- [{unit}]({relative.as_posix()}) ({len(rows)})")
    for kind, rows in kind_fragments(records).items():
        relative = Path("by-kind") / f"kind-{kind}.md"
        write_table(
            root / relative,
            f"{kind} Capability Fragment",
            rows,
            "Kind-scoped capability fragment. Load this when routing specifically to a skill, agent, MCP, CLI, or script family.",
        )
        if obsidian_links:
            links.append(f"- [[capability-index/{relative.with_suffix('').as_posix()}|kind:{kind}]] ({len(rows)})")
        else:
            links.append(f"- [kind:{kind}]({relative.as_posix()}) ({len(rows)})")
    return links


def write_capability_index(records: list[dict[str, object]]) -> Path:
    root = reference_path("capability-index")
    machine = root / "04-machine-readable"
    machine.mkdir(parents=True, exist_ok=True)
    fragment_links = write_fragment_tables(root, records, obsidian_links=False)
    counts = {
        kind: sum(1 for record in records if record.get("kind") == kind)
        for kind in sorted({str(record.get("kind", "")) for record in records})
    }
    generated_at = datetime.now().isoformat(timespec="seconds")
    (root / "README.md").write_text(
        "\n".join(
            [
                "# court-capability-router capability index",
                "",
                f"generated_at: {generated_at}",
                "source_skill: current installed `court-capability-router`",
                "",
                "This generated index is a routing aid, not a permission grant.",
                "Invocation is index-first: select the smallest suitable skill/agent/MCP/CLI/script set, then call the selected capability under the active authority.",
                "",
                "## Current counts",
                "",
                f"- capabilities: {len(records)}",
                f"- counts: `{json.dumps(counts, ensure_ascii=False, sort_keys=True)}`",
                "",
                "## Tables",
                "",
                "- `by-unit/*.md`: office-scoped fragments for on-demand loading",
                "- `by-kind/*.md`: capability-kind fragments for on-demand loading",
                "- `capabilities.md`: human-readable full capability table",
                "- `04-machine-readable/capabilities.csv`: machine-readable routing table",
                "- `04-machine-readable/index-meta.json`: generation metadata",
                "",
                "## Fragment Index",
                "",
                *fragment_links,
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    (root / "capabilities.md").write_text(
        "\n".join(
            [
                "# Capability Routing Table",
                "",
                "Use this table for index-first routing. Do not paste whole skill bodies into context; load the selected capability only when needed.",
                "",
                *markdown_table(records),
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    (machine / "capabilities.csv").write_text(csv_text(records), encoding="utf-8", newline="\n")
    (machine / "index-meta.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "generator": "refresh_capability_registry.py",
                "count": len(records),
                "counts": counts,
                "invocation_rule": "index_first_select_one_or_bounded_set; do_not_invoke_all_candidates",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return root / "README.md"


def write_shiguan_capability_index(records: list[dict[str, object]]) -> Path:
    ensure_shared_seed()
    root = reference_path("shiguan-tree", "capability-index")
    root.mkdir(parents=True, exist_ok=True)
    fragment_links = write_fragment_tables(root, records, obsidian_links=True)
    generated_at = datetime.now().isoformat(timespec="seconds")
    counts = {
        kind: sum(1 for record in records if record.get("kind") == kind)
        for kind in sorted({str(record.get("kind", "")) for record in records})
    }
    frontmatter = [
        "---",
        "type: shiguan_capability_index",
        f"generated_at: \"{generated_at}\"",
        f"capability_count: {len(records)}",
        "capability_index_skill_gate: \"PASSED\"",
        "---",
        "",
    ]
    (root / "_index.md").write_text(
        "\n".join(
            [
                *frontmatter,
                "# 能力官籍索引 / Capability Routing Index",
                "",
                "这是共享史馆树中的能力索引入口，Obsidian 可直接打开。它来自本机 `refresh_capability_registry.py`，用于 index-first capability routing。",
                "",
                "- 调用规则：先索引并选择最小合适 skill/agent/MCP/CLI/script 集合，再按当前权限调用；不要等待用户点名，也不要调用所有候选。",
                f"- generated_at: `{generated_at}`",
                f"- capabilities: `{len(records)}`",
                f"- counts: `{json.dumps(counts, ensure_ascii=False, sort_keys=True)}`",
                "",
                "## Tables",
                "",
                "- `by-unit/*.md`: 按官署拆分，任务已归口时优先打开。",
                "- `by-kind/*.md`: 按 skill/agent/MCP/CLI 等能力类型拆分。",
                "- [[capability-index/capabilities|Capability table]]",
                "",
                "## Fragment Index",
                "",
                *fragment_links,
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    (root / "capabilities.md").write_text(
        "\n".join(
            [
                *frontmatter,
                "# Capability Table",
                "",
                "Compact routing table for Shiguan/Obsidian visibility. Full machine-readable CSV is in shared `capability-index/04-machine-readable/`.",
                "",
                *markdown_table(records),
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    return root / "_index.md"


def refresh() -> tuple[int, list[Path]]:
    home = codex_home()
    records: list[dict[str, object]] = []
    records.extend(collect_skills(home / "skills", "codex_skills"))
    records.extend(collect_skills(Path.home() / ".agents" / "skills", "agent_fallback_skills"))
    records.extend(collect_agents(home / "agents"))
    records.extend(collect_mcp_state())
    records.extend(collect_cli_state())
    paths = [
        write_manifest(records),
        write_skills_catalog(records),
        write_capabilities_catalog(records),
        write_capability_index(records),
        write_shiguan_capability_index(records),
    ]
    return len(records), paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print a JSON summary.")
    args = parser.parse_args()
    count, paths = refresh()
    if args.json:
        print(json.dumps({"count": count, "paths": [str(path) for path in paths]}, ensure_ascii=False, indent=2))
    else:
        print(f"CAPABILITY_REGISTRY_REFRESHED count={count}")
        for path in paths:
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
