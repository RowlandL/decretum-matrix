"""Merge legacy court Shiguan records into the shared Shiguan data root."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True

from shiguan_paths import (
    code_root,
    ensure_shared_seed,
    legacy_reference_roots,
    reference_path,
    references_root,
    shared_root,
)
from obsidian_config_state import patch_config, read_config_snapshot


COPY_DIRS = (
    ("plan-archives", "*.md"),
    ("memory-decisions", "*.md"),
    ("shiguan-tree/manual", "*.json"),
    ("shiguan-imports/pending", "*.json"),
    ("shiguan-imports/processed", "*.json"),
)


def source_label(root: Path) -> str:
    text = str(root).lower()
    if "\\appdata\\local\\hermes\\" in text:
        return "hermes-appdata"
    if "\\.hermes\\" in text:
        return "hermes-home"
    if "\\.codex\\" in text:
        return "codex"
    if "\\.agents\\" in text:
        return "agents"
    return rekey(root.name or "legacy")


def rekey(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "legacy"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_unique(src: Path, dst: Path, label: str, dry_run: bool) -> tuple[str, Path]:
    if not dst.exists():
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return "copied", dst
    if digest(src) == digest(dst):
        return "duplicate", dst
    renamed = dst.with_name(f"{dst.stem}-{label}-{digest(src)[:8]}{dst.suffix}")
    if renamed.exists() and digest(src) == digest(renamed):
        return "duplicate", renamed
    if not dry_run:
        renamed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, renamed)
    return "conflict_renamed", renamed


def merge_files(root: Path, dry_run: bool) -> dict[str, object]:
    label = source_label(root)
    stats = {"root": str(root), "label": label, "copied": 0, "duplicates": 0, "conflicts": 0}
    for directory, pattern in COPY_DIRS:
        source_dir = root / directory
        if not source_dir.exists():
            continue
        target_dir = references_root() / directory
        for src in sorted(source_dir.glob(pattern)):
            if src.name == "README.md":
                continue
            status, _target = copy_unique(src, target_dir / src.name, label, dry_run)
            if status == "copied":
                stats["copied"] += 1
            elif status == "duplicate":
                stats["duplicates"] += 1
            elif status == "conflict_renamed":
                stats["conflicts"] += 1
    return stats


def read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def candidate_configs() -> list[tuple[Path, dict[str, object]]]:
    configs: list[tuple[Path, dict[str, object]]] = []
    for root in legacy_reference_roots():
        path = root / "obsidian-sync" / "config.json"
        if path.exists():
            value = read_json(path)
            if value:
                configs.append((path, value))
    return configs


def merge_obsidian_config(dry_run: bool) -> dict[str, object]:
    configs = candidate_configs()
    current_path = reference_path("obsidian-sync", "config.json")
    base = read_config_snapshot(current_path)
    merged = dict(base)
    selected_path = ""
    for path, value in sorted(
        configs,
        key=lambda item: (
            bool(item[1].get("api_key")),
            bool(item[1].get("vault_path") or item[1].get("filesystem_vault_path")),
            str(item[0]),
        ),
        reverse=True,
    ):
        selected_path = str(path)
        merged.update({key: val for key, val in value.items() if key != "updated_at"})
        break
    merged.setdefault("endpoint", "https://127.0.0.1:27124")
    merged.setdefault("verify_ssl", False)
    merged.setdefault("sync_mode", "filesystem_preserve_only")
    merged.setdefault("output_folder", "Court Shiguan")
    merged.setdefault("auto_enabled", True)
    merged.setdefault("vault_path", str(Path.home() / "Documents" / "Obsidian Vault" / "Court Shiguan"))
    merged["filesystem_sync_script"] = str(code_root() / "scripts" / "sync_shiguan_obsidian_vault.py")
    merged["shared_shiguan_root"] = str(references_root())
    for reserved in ("schema", "revision", "transaction_id", "updated_at"):
        merged.pop(reserved, None)
    if not dry_run:
        result = patch_config(merged, config_path=current_path, base_snapshot=base)
        if result.get("conflict"):
            raise RuntimeError("Obsidian sync config changed during migration")
    return {
        "config_path": str(current_path),
        "source_config": selected_path,
        "has_api_key": bool(merged.get("api_key")),
        "vault_path": str(merged.get("vault_path") or ""),
    }


def rebuild_outputs(dry_run: bool) -> dict[str, object]:
    if dry_run:
        return {"rebuilt": False, "reason": "dry_run"}
    from rebuild_shiguan_index import rebuild_index
    from grow_shiguan_tree import grow_tree
    from build_shiguan_knowledge_graph import build_and_write

    count, index = rebuild_index()
    grow_tree()
    graph = build_and_write()
    return {
        "rebuilt": True,
        "entries": count,
        "index": str(index),
        "graph_nodes": len(graph.get("nodes", [])) if isinstance(graph, dict) else 0,
    }


def migrate(dry_run: bool = False) -> dict[str, object]:
    ensure_shared_seed()
    roots = legacy_reference_roots()
    file_stats = [merge_files(root, dry_run) for root in roots]
    obsidian = merge_obsidian_config(dry_run)
    rebuild = rebuild_outputs(dry_run)
    return {
        "ok": True,
        "dry_run": dry_run,
        "shared_root": str(shared_root()),
        "shared_references_root": str(references_root()),
        "legacy_roots": [str(root) for root in roots],
        "file_stats": file_stats,
        "obsidian_config": obsidian,
        "rebuild": rebuild,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        report = migrate(args.dry_run)
    except Exception as exc:
        print(f"SHIGUAN_MIGRATION_FAILED {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
