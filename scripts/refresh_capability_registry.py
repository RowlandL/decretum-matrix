"""Refresh the court capability registry from local skills and agents.

This is a lightweight 吏部/户部 registry pass. It reads skill frontmatter and
standing-agent files, classifies each capability into likely court offices, and
rewrites the local catalogs used by Dercretum-Matrix（诏令矩阵）.
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
import tempfile
import tomllib
from unittest.mock import patch
import socket
import io
import hashlib

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

REGISTRY_MAINTENANCE_EVENTS = frozenset(
    {
        "skill_install",
        "skill_upgrade",
        "hash_drift",
        "version_drift",
        "dispatch_failure",
        "phase_closeout",
    }
)
READ_ONLY_AUTHORITIES = frozenset({"approval", "read-only", "read_only", "readonly", "no-write"})


def plan_registry_maintenance(
    event: str,
    *,
    authority: str = "autonomous",
    manifest_state: str = "current",
    changed_sources: tuple[str, ...] = (),
    broad_change: bool = False,
    registry_path: str = "references/installed-capabilities-manifest.json",
) -> dict[str, object]:
    """Return the local/offline refresh boundary for one registry event."""
    normalized_event = str(event).strip().casefold()
    if normalized_event not in REGISTRY_MAINTENANCE_EVENTS:
        raise ValueError(f"unsupported registry maintenance event: {event}")
    state = str(manifest_state or "corrupt").strip().casefold()
    sources = tuple(sorted({str(item).strip() for item in changed_sources if str(item).strip()}))
    if state in {"missing", "corrupt"} or broad_change:
        boundary = "full"
        scope = "all_declared_local_roots"
    elif normalized_event in {"dispatch_failure", "phase_closeout"}:
        boundary = "light"
        scope = "manifest_catalog_and_cheap_local_state"
    else:
        boundary = "incremental"
        scope = "changed_sources" if sources else "event_affected_entries"
    read_only = str(authority).strip().casefold() in READ_ONLY_AUTHORITIES
    return {
        "schema": "court.capability.registry_maintenance.v1",
        "owner": "libu-hr",
        "event": normalized_event,
        "registry_path": registry_path,
        "manifest_state": state,
        "refresh_boundary": boundary,
        "refresh_scope": scope,
        "changed_sources": list(sources),
        "status": "authority_blocked" if read_only else "READY",
        "mutation_allowed": not read_only,
        "staleness_warning": (
            "registry may remain stale because read-only authority forbids refresh writes"
            if read_only
            else None
        ),
        "network": False,
        "second_registry": False,
        "daemon": False,
    }


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
        records.append(_registry_record(
            kind="skill", source=source, name=name, description=description,
            path=public_relative_path(path, root), relative_path=public_relative_path(path, root),
            classification_path=Path(name),
        ))
    return normalize_records(records)


def public_relative_path(path: Path, root: Path, prefix: str = "") -> str:
    relative = path.relative_to(root).as_posix()
    return f"{prefix}/{relative}" if prefix else relative


def record_sort_key(record: dict[str, object]) -> tuple[str, str, str, str]:
    return (
        str(record.get("kind", "")),
        str(record.get("name", "")),
        str(record.get("source", "")),
        str(record.get("relative_path", "")),
    )


def _registry_record(
    *, kind: str, source: str, name: str, description: str, path: str,
    relative_path: str, classification_path: Path, enabled: bool = True,
    verified: bool = True, evidence: list[str] | None = None,
) -> dict[str, object]:
    return {
        "kind": kind,
        "source": source,
        "name": name,
        "description": short_description(description),
        "path": path,
        "relative_path": relative_path,
        "court_units": classify(name, description, classification_path),
        **fit_fields(name, description, classification_path),
        "enabled": enabled,
        "dispatchable": enabled,
        "verified": verified,
        "evidence": list(evidence or (["STRUCTURAL_LOCAL_METADATA_VERIFIED"] if verified else [])),
    }


MCP_DIRECT_KEYS = frozenset({"command", "url", "transport", "enabled", "disabled", "registered", "type"})
PLUGIN_DIRECT_KEYS = frozenset({"enabled", "disabled", "registered", "path", "version", "source"})


def _has_direct_declaration(settings: dict[str, object], allowed: frozenset[str]) -> bool:
    return any(key in settings and not isinstance(settings[key], dict) for key in allowed)


def _safe_component(value: str) -> bool:
    return bool(value) and value not in {".", ".."} and "/" not in value and "\\" not in value


def normalize_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for record in records:
        identity = tuple(str(record.get(key, "")).casefold() for key in ("kind", "name", "source"))
        grouped.setdefault(identity, []).append(record)
    output: list[dict[str, object]] = []
    for group in grouped.values():
        decorated: list[tuple[str, dict[str, object]]] = []
        for item in group:
            payload = {key: value for key, value in item.items() if not key.startswith("_")}
            semantic = {"record": payload, "metadata": item.get("_semantic", {})}
            normalized = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            decorated.append((normalized, item))
        variants = sorted({normalized for normalized, _item in decorated})
        canonical = dict(sorted(decorated, key=lambda pair: pair[0])[0][1])
        canonical.pop("_semantic", None)
        if len(variants) > 1:
            digests = [hashlib.sha256(value.encode("utf-8")).hexdigest() for value in variants]
            canonical["enabled"] = all(bool(item.get("enabled")) for _normalized, item in decorated)
            canonical["dispatchable"] = False
            canonical["verified"] = False
            canonical["evidence"] = ["LOCAL_METADATA_CONFLICT", "CONFLICT_DIGESTS:" + ",".join(digests)]
        output.append(canonical)
    return sorted(output, key=record_sort_key)


def validate_skill_identity_records(
    records: list[dict[str, object]],
    identity_manifest: dict[str, object],
) -> dict[str, object]:
    """Validate one canonical skill record without coupling name to its path."""

    findings: list[dict[str, object]] = []
    canonical_name = identity_manifest.get("canonical_skill_name")
    if not isinstance(canonical_name, str) or not canonical_name:
        findings.append(
            {
                "code": "IDENTITY_MANIFEST_CANONICAL_NAME_INVALID",
                "message": "canonical_skill_name must be a nonempty string",
            }
        )
        canonical_name = ""

    legacy_names = identity_manifest.get("legacy_names")
    legacy_skill_names = {
        str(item.get("name")).casefold()
        for item in legacy_names
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    } if isinstance(legacy_names, list) else set()
    withdrawn_names = identity_manifest.get("withdrawn_names")
    withdrawn_skill_names = {
        str(item).casefold() for item in withdrawn_names if isinstance(item, str)
    } if isinstance(withdrawn_names, list) else set()

    skill_records = [record for record in records if record.get("kind") == "skill"]
    canonical_records = [
        record
        for record in skill_records
        if str(record.get("name", "")).casefold() == canonical_name.casefold()
    ]
    if len(canonical_records) != 1:
        findings.append(
            {
                "code": "CANONICAL_SKILL_RECORD_COUNT_INVALID",
                "message": f"expected exactly one canonical record; got {len(canonical_records)}",
                "count": len(canonical_records),
            }
        )

    for record in skill_records:
        record_name = str(record.get("name", ""))
        normalized_name = record_name.casefold()
        if normalized_name in legacy_skill_names:
            findings.append(
                {
                    "code": "LEGACY_ALIAS_RECORD_FORBIDDEN",
                    "message": "deprecated compatibility input must not become a registry record",
                    "name": record_name,
                    "relative_path": str(record.get("relative_path", "")),
                }
            )
        if normalized_name in withdrawn_skill_names:
            findings.append(
                {
                    "code": "WITHDRAWN_SKILL_RECORD_FORBIDDEN",
                    "message": "withdrawn draft name must not become a registry record",
                    "name": record_name,
                    "relative_path": str(record.get("relative_path", "")),
                }
            )

    return {
        "schema": "court.skill_identity.registry_check.v1",
        "status": "PASSED" if not findings else "FAILED",
        "canonical_skill_name": canonical_name,
        "canonical_record_count": len(canonical_records),
        "canonical_relative_path": (
            str(canonical_records[0].get("relative_path", ""))
            if len(canonical_records) == 1
            else None
        ),
        "findings": findings,
    }


def _load_toml(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def collect_mcp_config(config_path: Path, source: str = "local_mcp") -> list[dict[str, object]]:
    """Collect only direct children of top-level mcp tables.

    Parsing TOML structurally prevents nested tables such as
    ``[mcp_servers.NAME.env]`` from being misregistered as MCP servers.
    """
    payload = _load_toml(config_path)
    records: list[dict[str, object]] = []
    for table_name in ("mcp_servers", "mcp"):
        table = payload.get(table_name)
        if not isinstance(table, dict):
            continue
        for name, settings in table.items():
            if not isinstance(settings, dict):
                continue
            if not _has_direct_declaration(settings, MCP_DIRECT_KEYS):
                continue
            enabled = settings.get("enabled") is not False and settings.get("disabled") is not True
            description = f"Codex MCP server `{name}` from local Codex configuration."
            record = _registry_record(
                    kind="mcp", source=source, name=str(name), description=description,
                    path="config.toml", relative_path=f"mcp:{name}",
                    classification_path=Path(str(name)), enabled=enabled,
                )
            record["_semantic"] = {
                key: settings.get(key) for key in sorted(MCP_DIRECT_KEYS) if key in settings
            }
            records.append(record)
    return normalize_records(records)


def _plugin_directory(plugin_id: str, roots: tuple[Path, ...]) -> Path | None:
    name, separator, marketplace = plugin_id.partition("@")
    if not _safe_component(name) or (separator and not _safe_component(marketplace)):
        return None
    candidates: list[Path] = []
    for root in roots:
        base = root / marketplace / name if separator else root / name
        try:
            base.resolve(strict=False).relative_to(root.resolve(strict=False))
        except (OSError, ValueError):
            continue
        if base.is_dir():
            candidates.extend(path for path in base.iterdir() if path.is_dir())
            if (base / ".codex-plugin").is_dir():
                candidates.append(base)
    return sorted(candidates, key=lambda path: path.as_posix().casefold())[-1] if candidates else None


def collect_plugins(config_path: Path, plugin_roots: tuple[Path, ...]) -> list[dict[str, object]]:
    payload = _load_toml(config_path)
    table = payload.get("plugins")
    if not isinstance(table, dict):
        return []
    records: list[dict[str, object]] = []
    for plugin_id, settings in sorted(table.items(), key=lambda item: str(item[0]).casefold()):
        settings = settings if isinstance(settings, dict) else {}
        if not _has_direct_declaration(settings, PLUGIN_DIRECT_KEYS):
            continue
        plugin_name, separator, marketplace = str(plugin_id).partition("@")
        if not _safe_component(plugin_name) or (separator and not _safe_component(marketplace)):
            continue
        enabled = settings.get("enabled") is not False
        directory = _plugin_directory(str(plugin_id), plugin_roots)
        owning_root = next(
            (root for root in plugin_roots if directory is not None and directory.is_relative_to(root)),
            None,
        )
        plugin_path = (
            directory.relative_to(owning_root).as_posix()
            if directory is not None and owning_root is not None
            else f"missing/{plugin_id}"
        )
        records.append(
            _registry_record(
                kind="plugin", source="local_plugin", name=str(plugin_id),
                description=f"Codex plugin `{plugin_id}` from the local plugin registry.",
                path=plugin_path, relative_path=f"plugin:{plugin_id}",
                classification_path=Path(str(plugin_id)), enabled=enabled and directory is not None,
                verified=directory is not None,
                evidence=["PLUGIN_ROOT_VERIFIED"] if directory is not None else ["PLUGIN_ROOT_MISSING"],
            )
        )
        if directory is None:
            continue
        skills_root = directory / "skills"
        for skill_path in find_skill_files(skills_root):
            frontmatter = parse_frontmatter(skill_path)
            name = frontmatter.get("name") or skill_path.parent.name
            description = frontmatter.get("description") or ""
            records.append(
                _registry_record(
                    kind="skill", source="codex_plugin", name=name, description=description,
                    path=f"{plugin_path}/{public_relative_path(skill_path, directory)}",
                    relative_path=f"plugin:{plugin_id}:{public_relative_path(skill_path, skills_root)}",
                    classification_path=Path(name), enabled=enabled,
                )
            )
    return normalize_records(records)


def collect_registry_records(
    *, codex_skills_root: Path, fallback_skills_root: Path, agents_root: Path,
    config_path: Path, plugin_roots: tuple[Path, ...],
    cli_inventory: dict[str, tuple[Path, ...]] | None = None, offline: bool = True,
) -> list[dict[str, object]]:
    """Collect a deterministic registry from explicitly injected local roots."""
    del cli_inventory  # Reserved for deterministic injected CLI inventory support.
    records: list[dict[str, object]] = []
    for root, source in ((codex_skills_root, "local_skill"), (fallback_skills_root, "local_skill")):
        for path in find_skill_files(root):
            frontmatter = parse_frontmatter(path)
            name = frontmatter.get("name") or path.parent.name
            description = frontmatter.get("description") or ""
            record = _registry_record(
                kind="skill", source=source, name=name, description=description,
                path=public_relative_path(path, root), relative_path=public_relative_path(path, root),
                classification_path=Path(name),
            )
            record["_semantic"] = {"content_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            records.append(record)
    del agents_root
    records.extend(collect_mcp_config(config_path))
    records.extend(collect_plugins(config_path, plugin_roots))
    del offline
    return normalize_records(records)


def collect_agents(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if not root.exists():
        return records
    for path in sorted(root.glob("*.toml")):
        text = read_text(path)
        name = path.stem
        match = re.search(r"(?m)^description\s*=\s*['\"](.+?)['\"]\s*$", text)
        description = match.group(1) if match else "Codex custom agent."
        records.append(_registry_record(
            kind="agent", source="codex_agents", name=name, description=description,
            path=path.name, relative_path=path.name, classification_path=Path(name),
        ))
    return normalize_records(records)


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
            records.append(_registry_record(
                kind="cli", source="path", name=command,
                description=f"{use_when} Version: {version or 'available'}.",
                path=Path(executable).name, relative_path=f"cli:{command}",
                classification_path=Path(command),
            ))
    return normalize_records(records)


def collect_mcp_state() -> list[dict[str, object]]:
    config = codex_home() / "config.toml"
    return collect_mcp_config(config, source="codex_mcp")


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
                "generator": "refresh_capability_registry.py",
                "roots": {
                    "codex_skills": "${CODEX_HOME}/skills",
                    "codex_system_skills": "${CODEX_HOME}/skills/.system",
                    "codex_agents": "${CODEX_HOME}/agents",
                    "agent_fallback_skills": "${USERPROFILE}/.agents/skills",
                    "codex_plugins": "${CODEX_HOME}/plugins/cache",
                },
                "counts": {
                    "skills": sum(1 for item in records if item.get("kind") == "skill"),
                    "agents": sum(1 for item in records if item.get("kind") == "agent"),
                    "mcp": sum(1 for item in records if item.get("kind") == "mcp"),
                    "cli": sum(1 for item in records if item.get("kind") == "cli"),
                },
                "capabilities": sorted(records, key=record_sort_key),
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
        "Generated deterministically from current local metadata.",
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
        caps = ", ".join(grouped.get(unit, [])[:80]) or "`decretum-matrix`"
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
                "# Dercretum-Matrix（诏令矩阵） capability index",
                "",
                f"generated_at: {generated_at}",
                "source_skill: current installed `decretum-matrix`",
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
    records.extend(collect_plugins(home / "config.toml", (home / "plugins" / "cache",)))
    records.extend(collect_cli_state())
    records = normalize_records(records)
    paths = [
        write_manifest(records),
        write_skills_catalog(records),
        write_capabilities_catalog(records),
        write_capability_index(records),
        write_shiguan_capability_index(records),
    ]
    return len(records), paths


def run_self_test() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        config = root / "config.toml"
        config.write_text(
            "\n".join(
                [
                    '[mcp_servers.alpha]',
                    'command = "alpha"',
                    '[mcp_servers.alpha.env]',
                    'FAKE_MCP = "must-not-become-a-server"',
                    '[mcp_servers.nested_only.env]',
                    'TOKEN = "not-a-server"',
                    '[mcp_servers.disabled_one]',
                    'command = "disabled"',
                    'enabled = false',
                    '[mcp_servers.neutral]',
                    'command = "server-command"',
                    'enabled = true',
                    '[mcp.neutral]',
                    'url = "https://example.invalid/mcp"',
                    'enabled = true',
                    '[mcp_servers.equivalent]',
                    'command = "same"',
                    'enabled = true',
                    '[mcp.equivalent]',
                    'command = "same"',
                    'enabled = true',
                    '[plugins."fixture@local"]',
                    'enabled = true',
                    '[plugins."off@local"]',
                    'enabled = false',
                    '[plugins."nested@local".settings]',
                    'theme = "not-a-plugin"',
                    '[plugins."../escape@local"]',
                    'enabled = true',
                ]
            ) + "\n",
            encoding="utf-8",
        )
        plugin = root / "plugins" / "local" / "fixture" / "v1"
        skill = plugin / "skills" / "embedded" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        (plugin / ".codex-plugin").mkdir()
        skill.write_text("---\nname: embedded\ndescription: Fixture skill.\n---\n", encoding="utf-8")
        duplicate_a = root / "skills-a" / "dup" / "SKILL.md"
        duplicate_b = root / "skills-b" / "dup" / "SKILL.md"
        duplicate_a.parent.mkdir(parents=True)
        duplicate_b.parent.mkdir(parents=True)
        duplicate_a.write_text("---\nname: duplicate\ndescription: A.\n---\n", encoding="utf-8")
        duplicate_b.write_text("---\nname: duplicate\ndescription: B.\n---\n", encoding="utf-8")
        identity_skill = root / "identity-skills" / "court-capability-router" / "SKILL.md"
        identity_skill.parent.mkdir(parents=True)
        identity_skill.write_text(
            "---\nname: decretum-matrix\ndescription: Decretum Matrix fixture.\n---\n",
            encoding="utf-8",
        )
        effects = {"network_calls": 0, "subprocess_calls": 0, "write_calls": 0, "cache_write_calls": 0}
        def blocked_socket(*args: object, **kwargs: object) -> object:
            effects["network_calls"] += 1
            raise AssertionError("network forbidden")
        def blocked_subprocess(*args: object, **kwargs: object) -> object:
            effects["subprocess_calls"] += 1
            raise AssertionError("subprocess forbidden")
        def blocked_write(*args: object, **kwargs: object) -> object:
            effects["write_calls"] += 1
            raise AssertionError("filesystem write forbidden")
        original_io_open = io.open
        def guarded_open(file: object, mode: str = "r", *args: object, **kwargs: object) -> object:
            if any(flag in mode for flag in ("w", "a", "x", "+")):
                key = "cache_write_calls" if str(file).casefold().endswith((".pyc", ".pyo")) else "write_calls"
                effects[key] += 1
                raise AssertionError("filesystem/cache write forbidden")
            return original_io_open(file, mode, *args, **kwargs)
        with patch.object(socket, "socket", blocked_socket), patch.object(subprocess, "run", blocked_subprocess), patch.object(Path, "write_text", blocked_write), patch.object(io, "open", guarded_open):
            records = collect_registry_records(
                codex_skills_root=root / "skills-a",
                fallback_skills_root=root / "skills-b",
                agents_root=root / "missing-agents",
                config_path=config,
                plugin_roots=(root / "plugins",),
                cli_inventory={},
                offline=True,
            )
            identity_records = collect_skills(root / "identity-skills", "local_skill")
        identities = [(item["kind"], item["source"], item["name"]) for item in records]
        assert ("mcp", "local_mcp", "alpha") in identities
        assert not any(item["name"] == "FAKE_MCP" for item in records)
        assert not any(item["name"] == "nested_only" for item in records)
        assert not any(item["name"] == "nested@local" for item in records)
        assert not any("escape" in str(item["name"]) for item in records)
        assert ("plugin", "local_plugin", "fixture@local") in identities
        assert ("skill", "codex_plugin", "embedded") in identities
        assert {item["kind"] for item in records} <= {"skill", "plugin", "mcp"}
        assert {item["source"] for item in records} <= {"local_skill", "codex_plugin", "local_plugin", "local_mcp"}
        assert not any(item["kind"] in {"agent", "cli"} for item in records)
        neutral = [item for item in records if item["name"] == "neutral"]
        assert len(neutral) == 1
        assert neutral[0]["enabled"] is True and neutral[0]["verified"] is False and neutral[0]["dispatchable"] is False
        assert "LOCAL_METADATA_CONFLICT" in neutral[0]["evidence"]
        assert any(item.startswith("CONFLICT_DIGESTS:") for item in neutral[0]["evidence"])
        equivalent = [item for item in records if item["name"] == "equivalent"]
        assert len(equivalent) == 1 and equivalent[0]["verified"] is True and equivalent[0]["dispatchable"] is True
        disabled = next(item for item in records if item["name"] == "disabled_one")
        assert disabled["enabled"] is False and disabled["dispatchable"] is False
        assert records == sorted(records, key=lambda item: (item["kind"], item["name"], item["source"], item["relative_path"]))
        assert len({(item["kind"], item["source"], item["name"], item["relative_path"]) for item in records}) == len(records)
        duplicate = [item for item in records if item["kind"] == "skill" and item["name"] == "duplicate"]
        assert len(duplicate) == 1 and duplicate[0]["verified"] is False and duplicate[0]["dispatchable"] is False
        assert "LOCAL_METADATA_CONFLICT" in duplicate[0]["evidence"]
        mandatory = {"kind", "source", "name", "description", "path", "relative_path", "court_units", "primary_fit", "secondary_fit", "requires_review", "fit_score", "enabled", "dispatchable", "verified", "evidence"}
        assert all(set(item) == mandatory for item in records)
        assert all(isinstance(item["verified"], bool) and isinstance(item["evidence"], list) for item in records)
        assert all("generated_at" not in item for item in records)
        assert all(str(root) not in json.dumps(item, ensure_ascii=False) for item in records)
        assert effects == {"network_calls": 0, "subprocess_calls": 0, "write_calls": 0, "cache_write_calls": 0}
        identity_manifest = {
            "canonical_skill_name": "decretum-matrix",
            "legacy_names": [{"name": "court-capability-router"}],
            "withdrawn_names": ["DecreeMatri", "decreematri"],
        }
        identity_result = validate_skill_identity_records(
            identity_records, identity_manifest
        )
        assert identity_result["status"] == "PASSED"
        assert identity_result["canonical_relative_path"] == "court-capability-router/SKILL.md"
        alias_result = validate_skill_identity_records(
            [
                *identity_records,
                {
                    "kind": "skill",
                    "source": "local_skill",
                    "name": "court-capability-router",
                    "relative_path": "court-capability-router-alias/SKILL.md",
                },
            ],
            identity_manifest,
        )
        assert alias_result["status"] == "FAILED"
        assert any(
            finding.get("code") == "LEGACY_ALIAS_RECORD_FORBIDDEN"
            for finding in alias_result["findings"]
        )
    expected_boundaries = {
        "skill_install": "incremental",
        "skill_upgrade": "incremental",
        "hash_drift": "incremental",
        "version_drift": "incremental",
        "dispatch_failure": "light",
        "phase_closeout": "light",
    }
    for event, expected in expected_boundaries.items():
        plan = plan_registry_maintenance(event, changed_sources=("fixture",))
        assert plan["refresh_boundary"] == expected
        assert plan["network"] is False and plan["second_registry"] is False and plan["daemon"] is False
    full = plan_registry_maintenance("hash_drift", manifest_state="corrupt")
    assert full["refresh_boundary"] == "full"
    blocked = plan_registry_maintenance("skill_install", authority="read-only")
    assert blocked["status"] == "authority_blocked"
    assert blocked["mutation_allowed"] is False and blocked["staleness_warning"]
    return {
        "ok": True,
        "offline": True,
        "maintenance_events": True,
        "read_only_authority_blocked": True,
        "skill_identity_records": True,
        **effects,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print a JSON summary.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(run_self_test(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
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
