"""Build a portable court-capability-router skill package.

The package is staged from the local skill directory but intentionally excludes
host-local Shiguan record bodies, plan archives, memory decisions, generated
leaves/source mirrors, runtime ledgers, sharing/import state, local backups,
startup task drafts, Obsidian return queues, and capability catalogs. The
installed skill starts with a portable empty Shiguan seed and rebuilds local
records and knowledge on the target machine.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile


ROOT_NAME = "court-capability-router"
SECRET_PATTERNS = [
    re.compile(rb'(?i)"api_key"\s*:\s*"(?!\s*")[^"]{8,}"'),
    re.compile(rb"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,2048}"),
    re.compile(rb"(?i)_authToken\s*=\s*[A-Za-z0-9._~+/=-]{12,2048}"),
    re.compile(rb"(?i)\b[A-Z0-9_]*API_KEY\s*[:=]\s*['\"]?sk-[A-Za-z0-9._~+/=-]{16,2048}"),
    re.compile(rb"(?i)\bOPENAI_API_KEY\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{16,2048}"),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"(?i)\baws_access_key_id\s*=\s*[A-Z0-9]{16,}"),
    re.compile(rb"(?i)\baws_secret_access_key\s*=\s*[A-Za-z0-9/+=]{20,2048}"),
    re.compile(rb'(?i)"private_key"\s*:\s*"-----BEGIN [A-Z ]*PRIVATE KEY-----'),
    re.compile(rb'(?i)"auths?"\s*:\s*\{'),
    re.compile(rb"(?i)\b(token|secret|password|cookie)\s*[:=]\s*['\"]?[A-Za-z0-9_~+/=-]{16,2048}"),
    re.compile(rb"[A-Za-z0-9_-]{20,2048}\.[A-Za-z0-9_-]{20,2048}\.[A-Za-z0-9_-]{20,2048}"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,255}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,255}\b"),
    re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,255}\b"),
    re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(rb"(?i)\b(?:https?|ftp|smb)://[^/\s:@]+:[^@\s/]{8,255}@"),
]
TEXT_SUFFIXES = {
    ".cfg",
    ".cmd",
    ".conf",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
BINARY_SUFFIXES = {
    ".7z",
    ".bin",
    ".bmp",
    ".dll",
    ".docx",
    ".exe",
    ".gif",
    ".ico",
    ".jpg",
    ".jpeg",
    ".pdf",
    ".png",
    ".pptx",
    ".pyc",
    ".so",
    ".webp",
    ".xlsx",
    ".zip",
}
NESTED_PACKAGE_SUFFIXES = {
    ".7z",
    ".bz2",
    ".gz",
    ".jar",
    ".rar",
    ".tar",
    ".tgz",
    ".txz",
    ".whl",
    ".xz",
    ".zip",
}
SECRET_BEARING_NAMES = {".npmrc", ".pypirc", ".netrc", "_netrc", "netrc"}
SECRET_BEARING_DIRS = {".ssh", ".aws", ".docker", ".gcloud", ".azure"}
ROOT_ALLOWED_FILES = {
    ".gitignore",
    "changelog.md",
    "readme.md",
    "release-log.md",
    "release-manifest.json",
    "skill.md",
    "version",
}
ROOT_TEXT_BASENAMES = {".gitignore", "version"}
SENSITIVE_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".obsidian",
    ".pytest_cache",
    ".ruff_cache",
    ".ssh",
    ".aws",
    ".azure",
    ".docker",
    ".gcloud",
    "__pycache__",
    "agente-logs",
    "audits",
    "backups",
    "court-runtime",
    "hermes-standing-agents",
    "imports",
    "logs",
    "memory-decisions",
    "obsidian-sync",
    "peers",
    "plan-archives",
    "runtime",
    "sessions",
    "shiguan-backups",
    "shiguan-imports",
    "shiguan-peers",
    "shiguan-tidy-reports",
}
SOURCE_REGENERATED_DIRS = {
    "references/shiguan-tree",
    "references/startup-tasks",
}
SOURCE_ALLOWED_DIRS = {
    "agents",
    "agents/standing-officials",
    "agents/supercc-dossiers",
    "agents/supercc-dossiers/bingbu",
    "agents/supercc-dossiers/gongbu",
    "agents/supercc-dossiers/hubu",
    "agents/supercc-dossiers/libu",
    "agents/supercc-dossiers/libu-hr",
    "agents/supercc-dossiers/menxia",
    "agents/supercc-dossiers/patrol-inspector",
    "agents/supercc-dossiers/shangshu",
    "agents/supercc-dossiers/shiguan",
    "agents/supercc-dossiers/shiguan-hermes",
    "agents/supercc-dossiers/taizi",
    "agents/supercc-dossiers/xingbu",
    "agents/supercc-dossiers/zaochao",
    "agents/supercc-dossiers/zhongshu",
    "development-manual",
    "references",
    "references/benchmarks",
    "references/fixtures",
    "references/manifests",
    "references/sections",
    "scripts",
    "web",
    "web/shiguan-tree",
}
ARCHIVE_ALLOWED_DIRS = SOURCE_ALLOWED_DIRS | {
    "references/shiguan-tree",
    "references/shiguan-tree/branches",
    "references/shiguan-tree/capability-index",
    "references/shiguan-tree/leaves",
    "references/shiguan-tree/manual",
    "references/shiguan-tree/sources",
    "references/startup-tasks",
}
ARCHIVE_EXACT_REGENERATED_FILES = {
    "references/shiguan-index.jsonl",
    "references/shiguan-knowledge-graph.json",
    "references/shiguan-tree/_index.md",
    "references/shiguan-tree/branches/readme.md",
    "references/shiguan-tree/capability-index/_index.md",
    "references/shiguan-tree/capability-index/readme.md",
    "references/shiguan-tree/leaves/readme.md",
    "references/shiguan-tree/manual/readme.md",
    "references/shiguan-tree/readme.md",
    "references/shiguan-tree/sources/readme.md",
    "references/startup-tasks/readme.md",
}
EXCLUDED_BINARY_PATHS = {"references/user-manual-zh.docx"}
REQUIRED_PACKAGED_README_TERMS = [
    "department-map.md",
    "supercc-phase-cycling-model.md",
    "静默监督",
]
DEPRECATED_PACKAGE_TEXT_PATTERNS = [
    re.compile(b"Court" + rb"\s+OS", re.IGNORECASE),
]
EXCLUDE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    "manual",
}
EXCLUDE_REFERENCE_DIRS = {
    "agente-logs",
    "capability-index",
    "court-runtime",
    "hermes-standing-agents",
    "memory-decisions",
    "obsidian-sync",
    "plan-archives",
    "shiguan-backups",
    "shiguan-imports",
    "shiguan-peers",
    "shiguan-tidy-reports",
}
EXCLUDE_FILES = {
    ".DS_Store",
    "Thumbs.db",
    "agent-source-registry.json",
    "installed-capabilities-catalog.md",
    "installed-skills-catalog.md",
    "installed-capabilities-manifest.json",
    "shiguan-index.jsonl",
    "shiguan-knowledge-graph.json",
}
HOST_ABSOLUTE_PATH_PATTERNS = [
    re.compile(
        rb"\b[A-Z]:[\\/]Users[\\/]"
        rb"(?!(?:Example|user|private-user|<name>)[\\/])"
        rb"[A-Za-z0-9][A-Za-z0-9._-]*[\\/]",
        re.IGNORECASE,
    ),
    re.compile(
        rb"(?:/mnt/[a-z]/Users|/Users|/home)/"
        rb"(?!(?:Example|user|private-user|<name>)/)[A-Za-z0-9][A-Za-z0-9._-]*/",
        re.IGNORECASE,
    ),
    re.compile(
        rb"(?<![:/\\A-Za-z0-9])(?:\\\\(?!\\)|//(?!/))[A-Za-z0-9][A-Za-z0-9._-]*"
        rb"(?:\\(?!\\)|/(?!/))[A-Za-z0-9$._-]+(?:\\(?!\\)|/(?!/))",
        re.IGNORECASE,
    ),
    re.compile(rb"\b(?:file|smb)://[A-Za-z0-9][A-Za-z0-9._-]+/[^/\s]+/", re.IGNORECASE),
]

MAX_ARCHIVE_ENTRIES = 4096
MAX_MEMBER_UNCOMPRESSED_BYTES = 16 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MIN_COMPRESSION_RATIO_BYTES = 1024 * 1024
MAX_COMPRESSION_RATIO = 200.0
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

REQUIRED_COURT_SCRIPTS = [
    "quick_validate.py",
    "archive_checkpoint.py",
    "court_file_lock.py",
    "court_usage_ledger.py",
    "check_court_usage_ledger.py",
    "check_shiguan_concurrency.py",
    "internal_memory_shiguan_bridge.py",
    "query_shiguan_index.py",
    "grow_shiguan_tree.py",
    "build_shiguan_knowledge_graph.py",
    "export_shiguan_obsidian.py",
    "rebuild_shiguan_index.py",
    "ensure_codex_yolo_startup_task.py",
    "ensure_court_agent_config.py",
    "check_court_agent_config.py",
    "court_model_router.py",
    "check_court_model_router.py",
    "court_office_bootstrap.py",
    "check_court_office_bootstrap.py",
    "ensure_portable_court_bootstrap.py",
    "ensure_supercc_court.py",
    "supercc_client_selection.py",
    "check_supercc_client_selection.py",
    "check_supercc_state_concurrency.py",
    "court_platform.py",
    "supercc_squad.py",
    "supercc-squad.sh",
    "supercc-squad.ps1",
    "supercc-squad.cmd",
    "check_supercc_squad_wrapper.py",
    "check_supercc_claude_hard_gates.py",
    "stress_supercc_rate_limit.py",
    "ensure_hermes_supercc.py",
    "ensure_shiguan_web.py",
    "ensure_shiguan_autosync.py",
    "ensure_shiguan_service_daemon.py",
    "ensure_obsidian_shared_vault.py",
    "obsidian_config_state.py",
    "serve_shiguan_tree.py",
    "shiguan_peer_downloads.py",
    "shiguan_peer_state.py",
    "shiguan_web_pending.py",
    "supercc_office_state.py",
    "shiguan_autosync_daemon.py",
    "shiguan_service_daemon.py",
    "register_agent_presence.py",
    "refresh_capability_registry.py",
    "check_capability_index_gate.py",
    "check_response_fewshot_format.py",
    "check_response_draft_fixtures.py",
    "check_context_compression_survival.py",
    "check_package_privacy.py",
    "package_skill.py",
    "court_runtime.py",
    "court_cli.py",
    "court_multi_agent_protocol.py",
    "court_codex_protocol_launcher.py",
    "court_codex_office_worker.py",
    "check_court_codex_office_worker.py",
    "court_codex_host_resolution.py",
    "check_court_codex_host_resolution.py",
    "check_court_runtime.py",
    "check_court_agent_lifecycle.py",
    "check_court_runtime_concurrency.py",
    "check_court_intervention_matrix.py",
    "check_supercc_functional.py",
    "check_supercc_ministry_dispatch.py",
    "check_supercc_no_silence_429_patrol.py",
    "check_supercc_super_entry.py",
    "check_supercc_profiles.py",
    "check_supercc_truth_gates.py",
    "supercc_watchdog.py",
    "sync_active_copies.py",
    "sync_codex_agents_from_profiles.py",
    "check_codex_agent_roles.py",
    "check_agente_terminal.py",
    "court_heartbeat_watch.py",
    "agente_terminal.py",
    "archive_runtime_task.py",
    "agent_runtime_probe.py",
    "check_shiguan_http.py",
    "check_shiguan_peer_state_transaction.py",
    "shiguan_security.py",
    "shiguan_entry_utils.py",
    "memory_decision.py",
    "check_active_copy_hashes.py",
    "check_portability.py",
    "check_release_gate.py",
    "release_gate_manifest.py",
    "check_release_manifest.py",
    "check_source_state_budget.py",
    "check_read_only_contract.py",
    "check_shiguan_import_queue.py",
    "check_shiguan_queue_and_autosync_safety.py",
    "sync_shiguan_obsidian_vault.py",
    "check_obsidian_sync_transaction.py",
    "plan_shiguan_pending_quarantine.py",
    "shiguan_pending_governance.py",
    "shiguan_pending_governance_cli.py",
    "shiguan_pending_trust.py",
    "check_shiguan_pending_quarantine_plan.py",
    "repair_archive_placeholders.py",
    "migrate_shared_shiguan.py",
    "shiguan_paths.py",
]


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_out() -> Path:
    return Path.home() / "court-capability-router-skill.zip"


class PackagePolicyError(ValueError):
    """Raised when a source tree is not safe to package."""


def relative_key(relative: Path) -> str:
    return relative.as_posix().casefold()


def has_sensitive_directory(relative: Path) -> bool:
    return any(part.casefold() in SENSITIVE_DIR_NAMES for part in relative.parts)


def is_regenerated_source_path(relative: Path) -> bool:
    key = relative_key(relative)
    return any(key == prefix or key.startswith(prefix + "/") for prefix in SOURCE_REGENERATED_DIRS)


def is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PackagePolicyError(f"cannot lstat source entry: {path}: {exc}") from exc
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def should_skip(relative: Path, is_dir: bool) -> bool:
    del is_dir
    lower_parts = {part.casefold() for part in relative.parts}
    lower_name = relative.name.casefold()
    key = relative_key(relative)
    if has_sensitive_directory(relative):
        return True
    if lower_parts & SECRET_BEARING_DIRS:
        return True
    if lower_name in SECRET_BEARING_NAMES:
        return True
    if is_regenerated_source_path(relative):
        return True
    if any(part.casefold().startswith("references.imported-") for part in relative.parts):
        return True
    if len(relative.parts) >= 2 and relative.parts[0].casefold() == "references" and relative.parts[1].casefold() in {
        item.casefold() for item in EXCLUDE_REFERENCE_DIRS
    }:
        return True
    if any(part.casefold() == "obsidian 回传".casefold() for part in relative.parts):
        return True
    if lower_name in {item.casefold() for item in EXCLUDE_FILES}:
        return True
    if key in EXCLUDED_BINARY_PATHS:
        return True
    if lower_name.startswith(".tmp-") or lower_name.endswith((".tmp", ".bak", ".backup", ".log", ".sqlite", ".sqlite3", ".db", ".pyc")):
        return True
    if lower_name in {".env", "auth.json", "config.yaml", "config.yml"} or lower_name.startswith(".env"):
        return True
    if any(token in lower_name for token in ("token", "secret", "credential", "cookie")):
        return True
    return False


def validate_source_directory(relative: Path) -> None:
    key = relative_key(relative)
    if key not in SOURCE_ALLOWED_DIRS:
        raise PackagePolicyError(f"unknown-directory:{relative.as_posix()}")


def validate_source_file(path: Path, relative: Path) -> None:
    key = relative_key(relative)
    lower_name = relative.name.casefold()
    if len(relative.parts) == 1 and lower_name not in ROOT_ALLOWED_FILES:
        raise PackagePolicyError(f"root-file-not-allowed:{relative.as_posix()}")
    suffix = relative.suffix.casefold()
    if suffix in NESTED_PACKAGE_SUFFIXES:
        raise PackagePolicyError(f"nested-package:{relative.as_posix()}")
    if not (suffix in TEXT_SUFFIXES or (len(relative.parts) == 1 and lower_name in ROOT_TEXT_BASENAMES)):
        raise PackagePolicyError(f"unsupported-binary:{relative.as_posix()}")
    try:
        size = path.stat(follow_symlinks=False).st_size
    except OSError as exc:
        raise PackagePolicyError(f"cannot stat source file:{relative.as_posix()}:{exc}") from exc
    if size > MAX_MEMBER_UNCOMPRESSED_BYTES:
        raise PackagePolicyError(f"source-file-too-large:{relative.as_posix()}:{size}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PackagePolicyError(f"cannot read portable source file:{relative.as_posix()}:{exc}") from exc
    if b"\x00" in data:
        raise PackagePolicyError(f"unsupported-binary:{relative.as_posix()}:nul-byte")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackagePolicyError(f"unsupported-binary:{relative.as_posix()}:not-utf8") from exc
    if key in ARCHIVE_EXACT_REGENERATED_FILES:
        raise PackagePolicyError(f"regenerated-file-selected-from-source:{relative.as_posix()}")


def copy_portable_tree(src: Path, dst: Path) -> None:
    if is_link_or_reparse(src):
        raise PackagePolicyError(f"symlink-or-reparse:{src}")
    source_root = src.resolve(strict=True)
    destination = Path(os.path.abspath(dst))
    try:
        destination.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise PackagePolicyError(f"destination-inside-source:{destination}")

    def visit(current: Path, relative_dir: Path) -> None:
        try:
            entries = sorted(os.scandir(current), key=lambda entry: (entry.name.casefold(), entry.name))
        except OSError as exc:
            raise PackagePolicyError(f"cannot scan source directory:{relative_dir.as_posix()}:{exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            relative = relative_dir / entry.name
            if is_link_or_reparse(path):
                raise PackagePolicyError(f"symlink-or-reparse:{relative.as_posix()}")
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except OSError as exc:
                raise PackagePolicyError(f"cannot classify source entry:{relative.as_posix()}:{exc}") from exc
            if should_skip(relative, is_dir):
                continue
            target = destination / relative
            if is_dir:
                validate_source_directory(relative)
                target.mkdir(parents=True, exist_ok=True)
                visit(path, relative)
                continue
            if not is_file:
                raise PackagePolicyError(f"unsupported-special-file:{relative.as_posix()}")
            validate_source_file(path, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target, follow_symlinks=False)

    destination.mkdir(parents=True, exist_ok=True)
    visit(source_root, Path())


def write_core_shiguan_files(root: Path) -> None:
    references = root / "references"
    startup_tasks = references / "startup-tasks"
    tree = references / "shiguan-tree"
    capability_index = tree / "capability-index"
    for directory in (
        references,
        startup_tasks,
        tree,
        capability_index,
        tree / "branches",
        tree / "leaves",
        tree / "manual",
        tree / "meta",
        tree / "sources",
        tree / "sources" / "shiguan-tree" / "manual",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    source_readme = skill_root() / "references" / "README.md"
    if source_readme.exists():
        shutil.copy2(source_readme, references / "README.md")
    else:
        raise FileNotFoundError(f"missing source reference index: {source_readme}")
    (startup_tasks / "README.md").write_text(
        "# Startup Task Drafts\n\nThis directory receives local review artifacts generated by `ensure_codex_yolo_startup_task.py`. Portable packages ship it empty except for this README. Do not register no-sandbox autostart without explicit dangerous confirmation.\n",
        encoding="utf-8",
        newline="\n",
    )
    (references / "shiguan-index.jsonl").write_text("", encoding="utf-8", newline="\n")
    (references / "shiguan-knowledge-graph.json").write_text(
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
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (tree / "README.md").write_text(
        "\n".join(
            [
                "# 史馆生长树",
                "",
                "Portable seed tree. Local leaves, branches, and the knowledge graph grow from this host's own Shiguan records.",
                "",
                "- `leaves/`: local record leaves",
                "- `branches/`: content-lineage branches",
                "- `manual/`: web-manager manual entries",
                "- `meta/schema.md`: field and lineage notes",
                "- `sources/`: generated in-vault source mirrors for Obsidian Source links",
                "- `capability-index/`: generated capability routing index visible in Obsidian",
                "- `Obsidian 回传/`: Obsidian-created notes queued for court review by autosync",
                "",
                "Run `python scripts/rebuild_shiguan_index.py` after install or archive import.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    (capability_index / "README.md").write_text(
        "# Capability Index\n\nPortable seed for the Obsidian-visible capability routing index. Run `python -B scripts/refresh_capability_registry.py` to generate this host's table.\n",
        encoding="utf-8",
        newline="\n",
    )
    (capability_index / "_index.md").write_text(
        "\n".join(
            [
                "---",
                "type: shiguan_capability_index_seed",
                "portable_seed: true",
                "capability_index_skill_gate: \"seed\"",
                "---",
                "",
                "# 能力官籍索引 / Capability Routing Index",
                "",
                "Portable seed. Run `python -B scripts/refresh_capability_registry.py` after install to generate the host-local skill/agent/MCP/CLI/script routing table.",
                "",
                "Invocation rule: index first, select the smallest suitable bounded capability set, then call under the active authority. Do not wait for the user to name the capability and do not invoke every matching candidate.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    (tree / "_index.md").write_text(
        "\n".join(
            [
                "---",
                "type: shiguan_root",
                "portable_seed: true",
                "branch_count: 0",
                "leaf_count: 0",
                "---",
                "",
                "# 史馆生长树",
                "",
                "通用安装包只保留核心骨架；本机实录、记忆裁定、树叶和图谱会在目标环境中自行生长。",
                "",
                "- [[capability-index/_index|能力官籍索引]]",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    (tree / "branches" / "README.md").write_text(
        "# Branches\n\nContent-lineage branches are generated locally from this host's Shiguan records.\n",
        encoding="utf-8",
        newline="\n",
    )
    (tree / "leaves" / "README.md").write_text(
        "# Leaves\n\nShiguan leaves are generated locally from host-local records and are not included in portable packages.\n",
        encoding="utf-8",
        newline="\n",
    )
    (tree / "manual" / "README.md").write_text(
        "# Manual Entries\n\nThe local web manager writes manual JSON entries here.\n",
        encoding="utf-8",
        newline="\n",
    )
    (tree / "sources" / "README.md").write_text(
        "# Source Mirrors\n\nGenerated source mirrors are created locally for Obsidian links and are not included in portable packages.\n",
        encoding="utf-8",
        newline="\n",
    )
    (references / "installed-capabilities-catalog.example.md").write_text(
        "\n".join(
            [
                "# Installed Capabilities Catalog Example",
                "",
                "Run `python -B scripts/refresh_capability_registry.py` after installation. The generated `installed-capabilities-catalog.md`, `installed-skills-catalog.md`, and `installed-capabilities-manifest.json` are local to the host and are not shipped in portable packages.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )


def deterministic_zip_info(name: str, mode: int = 0o100644) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (mode & 0xFFFF) << 16
    return info


def make_zip(stage_root: Path, out: Path) -> int:
    if out.exists():
        raise PackagePolicyError(f"output-already-exists:{out}")
    files = [
        path
        for path in sorted(
            stage_root.rglob("*"),
            key=lambda item: item.relative_to(stage_root.parent).as_posix().encode("utf-8"),
        )
        if path.is_file()
    ]
    with out.open("xb") as raw:
        with zipfile.ZipFile(
            raw,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for path in files:
                name = path.relative_to(stage_root.parent).as_posix()
                archive.writestr(
                    deterministic_zip_info(name),
                    path.read_bytes(),
                    compress_type=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                )
    return len(files)


def archive_member_chunks(
    archive: zipfile.ZipFile,
    member: str | zipfile.ZipInfo,
    *,
    chunk_size: int,
):
    total = 0
    with archive.open(member) as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                return
            total += len(chunk)
            if total > MAX_MEMBER_UNCOMPRESSED_BYTES:
                name = member.filename if isinstance(member, zipfile.ZipInfo) else member
                raise PackagePolicyError(f"compression-bomb:{name}:stream-limit")
            yield chunk


def has_secret_like_content(archive: zipfile.ZipFile, name: str | zipfile.ZipInfo) -> bool:
    tail = b""
    for chunk in archive_member_chunks(archive, name, chunk_size=1024 * 1024):
        data = tail + chunk
        for pattern in SECRET_PATTERNS:
            if pattern.search(data):
                return True
        tail = data[-4096:]
    return False


def has_host_absolute_path_content(archive: zipfile.ZipFile, name: str | zipfile.ZipInfo) -> bool:
    tail = b""
    for data in archive_member_chunks(archive, name, chunk_size=1024 * 256):
        scan = tail + data
        for pattern in HOST_ABSOLUTE_PATH_PATTERNS:
            if pattern.search(scan):
                return True
        tail = data[-4096:]
    return False


def deprecated_package_text_hits(archive: zipfile.ZipFile, name: str | zipfile.ZipInfo) -> list[str]:
    hits: list[str] = []
    tail = b""
    for data in archive_member_chunks(archive, name, chunk_size=1024 * 256):
        scan = tail + data
        for index, pattern in enumerate(DEPRECATED_PACKAGE_TEXT_PATTERNS, start=1):
            if pattern.search(scan):
                hits.append(f"deprecated-text-{index}")
        tail = data[-4096:]
    return hits


def should_scan_content(name: str) -> bool:
    path = Path(name.replace("\\", "/"))
    lower_name = path.name.casefold()
    if lower_name in SECRET_BEARING_NAMES:
        return True
    suffix = path.suffix.casefold()
    return suffix in TEXT_SUFFIXES or lower_name in ROOT_TEXT_BASENAMES


def zipinfo_is_link_or_reparse(info: zipfile.ZipInfo) -> bool:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(unix_mode):
        return True
    file_type = stat.S_IFMT(unix_mode)
    if file_type and not (stat.S_ISREG(unix_mode) or stat.S_ISDIR(unix_mode)):
        return True
    dos_attributes = info.external_attr & 0xFFFF
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(dos_attributes & reparse_flag)


def normalized_zip_member(name: str) -> tuple[str | None, str | None]:
    if not name or "\x00" in name or "\\" in name:
        return None, "unsafe-member-path"
    if name.startswith("/") or "//" in name:
        return None, "unsafe-member-path"
    posix = PurePosixPath(name)
    windows = PureWindowsPath(name)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        return None, "unsafe-member-path"
    raw_parts = name.rstrip("/").split("/")
    if not raw_parts or any(part in {"", ".", ".."} or ":" in part for part in raw_parts):
        return None, "unsafe-member-path"
    if raw_parts[0] != ROOT_NAME:
        return None, "unsafe-member-path"
    return "/".join(raw_parts), None


def archive_member_policy_problem(normalized: str, is_dir: bool) -> str | None:
    parts = normalized.split("/")
    relative_parts = parts[1:]
    if not relative_parts:
        return None if is_dir else "root-file-not-allowed"
    relative = "/".join(relative_parts)
    lower_relative = relative.casefold()
    lower_parts = [part.casefold() for part in relative_parts]
    if any(part in SENSITIVE_DIR_NAMES for part in lower_parts[:-1] if not is_dir) or any(
        part in SENSITIVE_DIR_NAMES for part in lower_parts if is_dir
    ):
        return "sensitive-directory"
    if any(part in SECRET_BEARING_DIRS for part in lower_parts):
        return "sensitive-directory"

    directory = relative if is_dir else "/".join(relative_parts[:-1])
    if directory and directory.casefold() not in ARCHIVE_ALLOWED_DIRS:
        return "unknown-directory"
    if is_dir:
        return None

    lower_name = relative_parts[-1].casefold()
    if len(relative_parts) == 1 and lower_name not in ROOT_ALLOWED_FILES:
        return "root-file-not-allowed"
    if lower_name in SECRET_BEARING_NAMES:
        return "secret-bearing-name"
    if lower_name in {".env", "auth.json", "config.yaml", "config.yml"} or lower_name.startswith(".env"):
        return "secret-bearing-name"
    if any(token in lower_name for token in ("token", "secret", "credential", "cookie")):
        return "secret-bearing-name"
    if lower_name.startswith(".tmp-") or lower_name.endswith(
        (".tmp", ".bak", ".backup", ".log", ".sqlite", ".sqlite3", ".db", ".pyc")
    ):
        return "sensitive-file"

    suffix = PurePosixPath(relative).suffix.casefold()
    if suffix in NESTED_PACKAGE_SUFFIXES:
        return "nested-package"
    if not (suffix in TEXT_SUFFIXES or (len(relative_parts) == 1 and lower_name in ROOT_TEXT_BASENAMES)):
        return "unsupported-binary"

    if lower_relative.startswith("references/shiguan-tree/") or lower_relative.startswith(
        "references/startup-tasks/"
    ):
        if lower_relative not in ARCHIVE_EXACT_REGENERATED_FILES:
            return "regenerated-path-not-allowed"
    return None


def validate_optional_release_metadata(name: str, data: bytes) -> str | None:
    if name == f"{ROOT_NAME}/VERSION":
        try:
            value = data.decode("utf-8").strip()
        except UnicodeDecodeError:
            return "invalid-version"
        if not value or len(value) > 128 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", value):
            return "invalid-version"
    if name == f"{ROOT_NAME}/release-manifest.json":
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "invalid-release-manifest"
        if not isinstance(value, dict) or not value:
            return "invalid-release-manifest"
    return None


def validate_zip(path: Path) -> tuple[int, list[str]]:
    forbidden: list[str] = []
    required = {
        f"{ROOT_NAME}/SKILL.md",
        f"{ROOT_NAME}/development-manual/README.md",
        f"{ROOT_NAME}/development-manual/court-capability-router-development-manual-zh.md",
        f"{ROOT_NAME}/web/shiguan-tree/app.js",
        f"{ROOT_NAME}/references/README.md",
        f"{ROOT_NAME}/references/reference-section-index.md",
        f"{ROOT_NAME}/references/department-map.md",
        f"{ROOT_NAME}/references/sections/court-capability-verification-index.md",
        f"{ROOT_NAME}/references/sections/court-closeout-installation-validation.md",
        f"{ROOT_NAME}/references/sections/court-closeout-memorial-format.md",
        f"{ROOT_NAME}/references/sections/court-startup-approval-policy-details.md",
        f"{ROOT_NAME}/references/sections/court-response-fewshot-format.md",
        f"{ROOT_NAME}/references/sections/court-office-voice-fewshot.md",
        f"{ROOT_NAME}/references/sections/court-context-compression-survival.md",
        f"{ROOT_NAME}/references/fixtures/response-draft-families.json",
        f"{ROOT_NAME}/references/fixtures/context-compression-survival.json",
        f"{ROOT_NAME}/references/court-capability-registry.md",
        f"{ROOT_NAME}/references/court-closeout-validation.md",
        f"{ROOT_NAME}/references/court-core-contract.md",
        f"{ROOT_NAME}/references/court-host-platform-pitfalls.md",
        f"{ROOT_NAME}/references/court-offices-dispatch.md",
        f"{ROOT_NAME}/references/court-office-model-routing.md",
        f"{ROOT_NAME}/references/court-shiguan-memory.md",
        f"{ROOT_NAME}/references/court-startup-authority.md",
        f"{ROOT_NAME}/references/court-state-runtime-agents.md",
        f"{ROOT_NAME}/references/court-supercc-runtime-selection.md",
        f"{ROOT_NAME}/references/hermes-studio-super-gl.md",
        f"{ROOT_NAME}/references/obsidian-autosync-rest.md",
        f"{ROOT_NAME}/references/hermes-studio-group-chat.md",
        f"{ROOT_NAME}/references/benchmarks/cft0808-edict.yaml",
        f"{ROOT_NAME}/references/court-policy.yaml",
        f"{ROOT_NAME}/references/court-roles.yaml",
        f"{ROOT_NAME}/references/shiguan-ledger-policy.md",
        f"{ROOT_NAME}/references/complexity-budget.md",
        f"{ROOT_NAME}/references/manifests/release-gates.v1.json",
        f"{ROOT_NAME}/references/manifests/source-state-budget.v1.json",
        f"{ROOT_NAME}/references/supercc-phase-cycling-model.md",
        f"{ROOT_NAME}/references/shiguan-index.jsonl",
        f"{ROOT_NAME}/references/shiguan-knowledge-graph.json",
        f"{ROOT_NAME}/references/startup-tasks/README.md",
        f"{ROOT_NAME}/references/shiguan-tree/_index.md",
        f"{ROOT_NAME}/references/shiguan-tree/capability-index/README.md",
        f"{ROOT_NAME}/references/shiguan-tree/capability-index/_index.md",
        f"{ROOT_NAME}/references/shiguan-tree/sources/README.md",
    }
    required.update({f"{ROOT_NAME}/scripts/{name}" for name in REQUIRED_COURT_SCRIPTS})
    required.update(
        {
            f"{ROOT_NAME}/agents/supercc-dossiers/{role}/AGENTS.md"
            for role in (
                "taizi",
                "zhongshu",
                "menxia",
                "shangshu",
                "patrol-inspector",
                "libu-hr",
                "hubu",
                "libu",
                "bingbu",
                "xingbu",
                "gongbu",
                "shiguan",
                "shiguan-hermes",
                "zaochao",
            )
        }
    )
    names: set[str] = set()
    data_by_name: dict[str, bytes] = {}
    entry_count = 0
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            entry_count = len(infos)
            if entry_count > MAX_ARCHIVE_ENTRIES:
                forbidden.append(f"compression-bomb:too-many-entries:{entry_count}")

            raw_counts = Counter(info.filename for info in infos)
            for name, count in sorted(raw_counts.items()):
                if count > 1:
                    forbidden.append(f"{name}:duplicate-member:{count}")

            case_names: dict[str, str] = {}
            total_uncompressed = 0
            safe_infos: list[tuple[zipfile.ZipInfo, str]] = []
            for info in infos:
                normalized, path_problem = normalized_zip_member(info.filename)
                if path_problem or normalized is None:
                    forbidden.append(f"{info.filename}:{path_problem or 'unsafe-member-path'}")
                    continue

                collision_key = normalized.casefold()
                previous = case_names.get(collision_key)
                if previous is not None and previous != normalized:
                    forbidden.append(f"{normalized}:case-collision:{previous}")
                else:
                    case_names[collision_key] = normalized

                is_dir = info.is_dir() or info.filename.endswith("/")
                names.add(normalized + ("/" if is_dir else ""))
                member_problem = archive_member_policy_problem(normalized, is_dir)
                if member_problem:
                    forbidden.append(f"{normalized}:{member_problem}")
                if zipinfo_is_link_or_reparse(info):
                    forbidden.append(f"{normalized}:symlink-or-reparse")
                    member_problem = member_problem or "symlink-or-reparse"
                if info.flag_bits & 0x1:
                    forbidden.append(f"{normalized}:encrypted-member")
                    member_problem = member_problem or "encrypted-member"
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    forbidden.append(f"{normalized}:unsupported-compression:{info.compress_type}")
                    member_problem = member_problem or "unsupported-compression"
                if is_dir:
                    continue

                total_uncompressed += info.file_size
                if info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                    forbidden.append(f"{normalized}:compression-bomb:member-too-large:{info.file_size}")
                    member_problem = member_problem or "compression-bomb"
                if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    forbidden.append(f"compression-bomb:archive-too-large:{total_uncompressed}")
                    member_problem = member_problem or "compression-bomb"
                if info.file_size >= MIN_COMPRESSION_RATIO_BYTES:
                    ratio = info.file_size / max(info.compress_size, 1)
                    if ratio > MAX_COMPRESSION_RATIO:
                        forbidden.append(f"{normalized}:compression-bomb:ratio:{ratio:.1f}")
                        member_problem = member_problem or "compression-bomb"
                if member_problem or raw_counts[info.filename] > 1:
                    continue
                safe_infos.append((info, normalized))

            for info, normalized in safe_infos:
                try:
                    data = b"".join(archive_member_chunks(archive, info, chunk_size=1024 * 1024))
                except (OSError, RuntimeError, zipfile.BadZipFile, PackagePolicyError) as exc:
                    forbidden.append(f"{normalized}:member-read-failed:{type(exc).__name__}")
                    continue
                if len(data) != info.file_size:
                    forbidden.append(f"{normalized}:member-size-mismatch:{len(data)}:{info.file_size}")
                    continue
                if b"\x00" in data:
                    forbidden.append(f"{normalized}:unsupported-binary:nul-byte")
                    continue
                try:
                    data.decode("utf-8")
                except UnicodeDecodeError:
                    forbidden.append(f"{normalized}:unsupported-binary:not-utf8")
                    continue
                data_by_name[normalized] = data
                if any(pattern.search(data) for pattern in SECRET_PATTERNS):
                    forbidden.append(f"{normalized}:secret-like-content")
                if any(pattern.search(data) for pattern in HOST_ABSOLUTE_PATH_PATTERNS):
                    forbidden.append(f"{normalized}:host-absolute-path-content")
                for index, pattern in enumerate(DEPRECATED_PACKAGE_TEXT_PATTERNS, start=1):
                    if pattern.search(data):
                        forbidden.append(f"{normalized}:deprecated-text-{index}")
                metadata_problem = validate_optional_release_metadata(normalized, data)
                if metadata_problem:
                    forbidden.append(f"{normalized}:{metadata_problem}")
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        return entry_count, [f"invalid-zip:{type(exc).__name__}"]

    canonical_names = {name for name in names if not name.endswith("/")}
    missing = sorted(required - canonical_names)
    index_name = f"{ROOT_NAME}/references/shiguan-index.jsonl"
    graph_name = f"{ROOT_NAME}/references/shiguan-knowledge-graph.json"
    readme_name = f"{ROOT_NAME}/references/README.md"
    index_bytes = data_by_name.get(index_name, b"")
    graph_bytes = data_by_name.get(graph_name, b"")
    readme_bytes = data_by_name.get(readme_name, b"")
    readme_text = readme_bytes.decode("utf-8", errors="replace")
    for term in REQUIRED_PACKAGED_README_TERMS:
        if term not in readme_text:
            forbidden.append(f"{readme_name}:missing:{term}")
    if index_bytes.strip():
        forbidden.append(f"{index_name}:not-empty")
    if graph_bytes:
        try:
            graph = json.loads(graph_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            forbidden.append(f"{graph_name}:invalid-json")
        else:
            schema = graph.get("schema") if isinstance(graph, dict) else {}
            if not isinstance(schema, dict) or schema.get("portable_seed") is not True:
                forbidden.append(f"{graph_name}:not-portable-seed")
    return entry_count, missing + sorted(set(forbidden))


def run_stage_validation(stage: Path) -> list[str]:
    problems: list[str] = []
    readme = stage / "references" / "README.md"
    readme_text = readme.read_text(encoding="utf-8", errors="replace") if readme.exists() else ""
    for term in REQUIRED_PACKAGED_README_TERMS:
        if term not in readme_text:
            problems.append(f"stage:references/README.md:missing:{term}")

    for script, args in (
        ("quick_validate.py", []),
        ("check_response_fewshot_format.py", []),
        ("check_response_draft_fixtures.py", []),
        ("check_context_compression_survival.py", []),
        ("check_package_privacy.py", []),
    ):
        command = [sys.executable, "-B", str(stage / "scripts" / script), *args]
        env = os.environ.copy()
        if script == "check_package_privacy.py":
            env["COURT_PACKAGE_STAGE_VALIDATION"] = "1"
        completed = subprocess.run(
            command,
            cwd=stage,
            env=env,
            text=True,
            capture_output=True,
            timeout=60,
        )
        if completed.returncode != 0:
            output = (completed.stdout + completed.stderr).strip().replace("\n", " | ")
            problems.append(f"stage_validation_failed:{script}:{output[:500]}")
    return problems


def cleanup_stage_transients(stage: Path) -> None:
    for path in sorted(stage.rglob("__pycache__"), reverse=True):
        if path.is_dir():
            shutil.rmtree(path)
    for path in stage.rglob("*.pyc"):
        if path.is_file():
            path.unlink()


def build(out: Path) -> tuple[int, int, list[str]]:
    if out.exists():
        return 0, 0, [f"output-already-exists:{out}"]
    src = skill_root()
    try:
        out.resolve(strict=False).relative_to(src.resolve(strict=True))
    except ValueError:
        pass
    else:
        return 0, 0, [f"nested-package-output-inside-source:{out}"]
    with tempfile.TemporaryDirectory(prefix="court-router-package-") as tmp_text:
        tmp = Path(tmp_text)
        stage = tmp / ROOT_NAME
        candidate = tmp / f"{out.name}.candidate.zip"
        try:
            copy_portable_tree(src, stage)
        except PackagePolicyError as exc:
            return 0, 0, [f"source-policy:{exc}"]
        write_core_shiguan_files(stage)
        stage_problems = run_stage_validation(stage)
        if stage_problems:
            return 0, 0, stage_problems
        cleanup_stage_transients(stage)
        entry_count = make_zip(stage, candidate)
        zip_count, problems = validate_zip(candidate)
        if problems:
            return entry_count, zip_count, problems
        shutil.move(str(candidate), str(out))
    return entry_count, zip_count, []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=default_out())
    args = parser.parse_args()
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    entry_count, zip_count, problems = build(out)
    if problems:
        print("PACKAGE_VALIDATION_FAILED")
        for problem in problems:
            print(problem)
        return 2
    print(f"PACKAGE_OK {out} entries={zip_count} staged_files={entry_count} built_at={datetime.now().isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
