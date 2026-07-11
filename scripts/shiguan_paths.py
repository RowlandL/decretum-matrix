"""Shared Shiguan data-path helpers for court-capability-router.

The skill code can be installed in Codex, Agent Skills, or Hermes roots. Shiguan
records are local evidence shared across those runtimes, so their writable
database lives outside any one skill installation by default.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from datetime import datetime
import json
import os
from pathlib import Path
import socket

from court_platform import user_data_base


ROOT_ENV_KEYS = ("COURT_SHARED_SHIGUAN_ROOT", "SHIGUAN_SHARED_ROOT")
SOURCE_AGENT_ENV_KEYS = ("COURT_SOURCE_AGENT", "SHIGUAN_SOURCE_AGENT", "SOURCE_AGENT")
CLAUDE_CODE_ENV_KEYS = (
    "CLAUDE_CODE",
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_EFFORT_LEVEL",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
    "CLAUDE_CODE_SESSION_ID",
)
AGENT_LABELS = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "hermes": "Hermes",
    "agents": "Agents",
    "unknown": "Unknown",
}
AGENT_ALIASES = {
    "agent": "agents",
    "agent-skills": "agents",
    "claude": "claude-code",
    "claude-code": "claude-code",
    "claudecode": "claude-code",
    "claude_code": "claude-code",
}


def code_root() -> Path:
    return Path(__file__).parents[1]


def resolved_code_root() -> Path:
    return code_root().resolve()


def canonical_source_agent(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "-")
    return AGENT_ALIASES.get(normalized, normalized)


def is_claude_code_context(root_texts: tuple[str, ...]) -> bool:
    if any("/.claude/skills/" in text.replace("\\", "/").lower() for text in root_texts):
        return True
    return any(os.environ.get(key) for key in CLAUDE_CODE_ENV_KEYS)


def _default_base() -> Path:
    return user_data_base()


def shared_root() -> Path:
    for key in ROOT_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            root = Path(value).expanduser()
            if root.name.lower() == "references":
                return root.parent.resolve()
            return root.resolve()
    return (_default_base() / "court-shiguan" / "court-capability-router").resolve()


def references_root() -> Path:
    return shared_root() / "references"


def reference_path(*parts: str) -> Path:
    return references_root().joinpath(*parts)


def default_obsidian_parent_vault() -> Path:
    return Path.home() / "Documents" / "Obsidian Vault"


def default_obsidian_cache_vault() -> Path:
    return default_obsidian_parent_vault() / "Court Shiguan"


def default_obsidian_shared_vault() -> Path:
    return reference_path("shiguan-tree")


def default_obsidian_inbox() -> Path:
    return default_obsidian_shared_vault() / "Obsidian 回传"


def _create_text_exclusive(path: Path, text: str) -> bool:
    """Create a seed file exactly once without truncating a concurrent writer."""

    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        return False
    return True


def ensure_shared_seed() -> Path:
    """Explicitly initialize shared seed files without registering agent presence."""

    # Imported lazily so court_file_lock can expose shiguan_write_lock_path()
    # without creating a module-import cycle back into this file.
    from court_file_lock import atomic_write_text, file_lock

    refs = references_root()
    tree = refs / "shiguan-tree"
    for directory in (
        refs,
        refs / "plan-archives",
        refs / "memory-decisions",
        refs / "court-runtime",
        refs / "agente-logs",
        refs / "shiguan-imports" / "pending",
        refs / "shiguan-imports" / "processed",
        refs / "shiguan-peers",
        refs / "obsidian-sync",
        tree,
        tree / "capability-index",
        tree / "branches",
        tree / "leaves",
        tree / "manual",
        tree / "meta",
        tree / "sources",
        tree / "sources" / "plan-archives",
        tree / "sources" / "memory-decisions",
        tree / "sources" / "shiguan-tree" / "manual",
        tree / ".obsidian",
        tree / "Obsidian 回传",
        refs / "court-runtime" / "agente-presence",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    write_lock = refs / "court-runtime" / "shiguan-write.lock"
    with file_lock(write_lock):
        readmes = {
            refs / "README.md": "# Shared Court Shiguan\n\nThis directory is the local shared Shiguan database used by Codex, Agent Skills, and Hermes court-capability-router installations.\n",
            refs / "plan-archives" / "README.md": "# Shiguan Plan Archives\n\nLocal court checkpoints are written here.\n",
            refs / "memory-decisions" / "README.md": "# Shiguan Memory Decisions\n\nDurable memory decisions are recorded here after Menxia approval.\n",
            tree / "README.md": "# 史馆生长树\n\nGenerated Markdown tree for Obsidian and the Shiguan Web UI.\n",
            tree / "capability-index" / "README.md": "# Capability Index\n\nGenerated skill/agent/MCP/CLI/script routing index for Obsidian-visible court capability selection.\n",
            tree / "capability-index" / "_index.md": "---\ntype: shiguan_capability_index_seed\ncapability_index_skill_gate: \"seed\"\n---\n\n# 能力官籍索引 / Capability Routing Index\n\nRun `python scripts/refresh_capability_registry.py` to generate the host-local capability routing table.\n\nInvocation rule: index first, select the smallest suitable bounded capability set, then call under the active authority. Do not wait for the user to name the capability and do not invoke every matching candidate.\n",
            tree / "branches" / "README.md": "# Branches\n\nGenerated content-lineage branches.\n",
            tree / "leaves" / "README.md": "# Leaves\n\nGenerated Shiguan leaves.\n",
            tree / "manual" / "README.md": "# Manual Entries\n\nManual Web UI entries are stored here as JSON.\n",
            tree / "meta" / "schema.md": "# Shiguan Growth Tree Schema\n\nSeed schema; rebuilt by `grow_shiguan_tree.py`.\n",
            tree / "sources" / "README.md": "# Source Mirrors\n\nGenerated in-vault copies of raw Shiguan sources used by Obsidian links.\n",
            tree / "sources" / "plan-archives" / "README.md": "# Plan Archive Sources\n\nGenerated in-vault copies of linked Shiguan plan archive records.\n",
            tree / "sources" / "memory-decisions" / "README.md": "# Memory Decision Sources\n\nGenerated in-vault copies of linked Shiguan memory decision records.\n",
            tree / "Obsidian 回传" / "README.md": "# Obsidian 回传\n\n在 Obsidian 中新增或编辑需要交给 Codex/Hermes 会审的材料时，放在本目录。后台 autosync 会把变更复制到共享 `shiguan-imports/pending`，不会直接覆盖正式史馆记录。\n",
            refs / "obsidian-sync" / "README.md": "# Obsidian Sync\n\nHost-local sync config lives here. API keys must never be packaged or printed.\n",
        }
        for path, text in readmes.items():
            _create_text_exclusive(path, text)

        _create_text_exclusive(refs / "shiguan-index.jsonl", "")
        graph_text = (
            json.dumps(
                {
                    "schema": {
                        "name": "shiguan-multidimensional-knowledge-graph",
                        "version": 1,
                        "portable_seed": True,
                    },
                    "counts": {"entries": 0, "nodes": 1, "edges": 0},
                    "nodes": [{"id": "root:史馆总纪", "kind": "root", "label": "史馆总纪", "count": 1}],
                    "edges": [],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        _create_text_exclusive(refs / "shiguan-knowledge-graph.json", graph_text)

        config = refs / "obsidian-sync" / "config.json"
        initial_config = {
            "endpoint": "https://127.0.0.1:27124",
            "verify_ssl": False,
            "sync_mode": "filesystem_preserve_only",
            "auto_enabled": True,
            "output_folder": "Court Shiguan",
            "vault_path": str(default_obsidian_cache_vault()),
            "cache_vault_path": str(default_obsidian_cache_vault()),
            "source_vault_path": str(default_obsidian_shared_vault()),
            "parent_vault_path": str(default_obsidian_parent_vault()),
            "watch_paths": [str(default_obsidian_cache_vault()), str(default_obsidian_inbox())],
            "autosync_enabled": True,
            "autosync_interval_seconds": 20,
            "service_daemon_script": str(code_root() / "scripts" / "shiguan_service_daemon.py"),
            "service_ensure_script": str(code_root() / "scripts" / "ensure_shiguan_service_daemon.py"),
            "autosync_script": str(code_root() / "scripts" / "shiguan_autosync_daemon.py"),
            "filesystem_sync_script": str(code_root() / "scripts" / "sync_shiguan_obsidian_vault.py"),
            "shared_shiguan_root": str(references_root()),
            "api_key": "",
        }
        created = _create_text_exclusive(
            config,
            json.dumps(initial_config, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        if not created:
            try:
                current = json.loads(config.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = None
            if isinstance(current, dict):
                defaults = {
                    "service_daemon_script": initial_config["service_daemon_script"],
                    "service_ensure_script": initial_config["service_ensure_script"],
                    "autosync_script": initial_config["autosync_script"],
                    "filesystem_sync_script": initial_config["filesystem_sync_script"],
                    "source_vault_path": initial_config["source_vault_path"],
                    "shared_shiguan_root": initial_config["shared_shiguan_root"],
                }
                changed = False
                for key, value in defaults.items():
                    if not current.get(key):
                        current[key] = value
                        changed = True
                if changed:
                    atomic_write_text(
                        config,
                        json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    )
    return refs


def detect_runtime_agent(explicit: str | None = None) -> dict[str, str]:
    value = (explicit or "").strip()
    if not value:
        for key in SOURCE_AGENT_ENV_KEYS:
            env_value = os.environ.get(key, "").strip()
            if env_value:
                value = env_value
                break

    root = code_root()
    root_texts = (
        "/" + str(root).replace("\\", "/").strip("/").lower() + "/",
        "/" + str(resolved_code_root()).replace("\\", "/").strip("/").lower() + "/",
    )
    if value:
        agent_id = canonical_source_agent(value)
    elif os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_MANAGED_BY_NPM"):
        agent_id = "codex"
    elif is_claude_code_context(root_texts):
        agent_id = "claude-code"
    elif any("/appdata/local/hermes/skills/" in text or "/.hermes/skills/" in text for text in root_texts):
        agent_id = "hermes"
    elif any("/.codex/skills/" in text for text in root_texts):
        agent_id = "codex"
    elif any("/.agents/skills/" in text for text in root_texts):
        agent_id = "agents"
    else:
        agent_id = "unknown"

    display = AGENT_LABELS.get(agent_id, value or agent_id)
    return {
        "source_agent": agent_id,
        "source_agent_label": display,
        "source_agent_skill_root": str(root),
        "shared_shiguan_root": str(references_root()),
    }


def register_agent_presence(event: str = "skill-use", explicit: str | None = None) -> dict[str, object]:
    if os.environ.get("COURT_DISABLE_AGENT_PRESENCE"):
        return {}
    agent = detect_runtime_agent(explicit)
    now = datetime.now().isoformat(timespec="seconds")
    record: dict[str, object] = {
        **agent,
        "agent_id": agent["source_agent"],
        "label": agent["source_agent_label"],
        "status": "online",
        "event": event,
        "last_seen": now,
        "updated_at": now,
        "ttl_seconds": 180,
        "host": socket.gethostname(),
        "pid": os.getpid(),
    }
    root = references_root() / "court-runtime" / "agente-presence"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{agent['source_agent']}.json"
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return record


def relative_to_data(path: Path) -> str:
    resolved = path.resolve()
    for root in (shared_root(), code_root()):
        try:
            return resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
    try:
        return resolved.relative_to(references_root().resolve()).as_posix()
    except ValueError:
        return str(resolved)


def resolve_source(source: str) -> Path:
    text = str(source or "").replace("/", os.sep)
    if not text:
        return references_root()
    path = Path(text)
    if path.is_absolute():
        return path
    shared_candidate = shared_root() / path
    if shared_candidate.exists() or text.startswith("references" + os.sep):
        return shared_candidate
    return code_root() / path


def legacy_reference_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / ".agents" / "skills" / "court-capability-router" / "references",
        home / ".codex" / "skills" / "court-capability-router" / "references",
        home / ".hermes" / "skills" / "court-capability-router" / "references",
        user_data_base() / "hermes" / "skills" / "court-capability-router" / "references",
    ]
    current = code_root() / "references"
    shared_refs = references_root()
    output: list[Path] = []
    seen: set[str] = set()
    for root in [current, *roots]:
        try:
            if root.resolve() == shared_refs.resolve():
                continue
        except OSError:
            pass
        key = str(root.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        if root.exists():
            output.append(root)
    return output
