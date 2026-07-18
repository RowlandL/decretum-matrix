#!/usr/bin/env python
"""Register the shared Shiguan tree as a local Obsidian vault."""

from __future__ import annotations

from datetime import datetime
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Callable

sys.dont_write_bytecode = True
import time

from court_platform import user_config_base
from court_file_lock import atomic_write_text, file_lock
from obsidian_config_state import RESERVED_FIELDS, patch_config, public_config, read_config_snapshot
from shiguan_paths import (
    default_obsidian_cache_vault,
    default_obsidian_inbox,
    default_obsidian_parent_vault,
    default_obsidian_shared_vault,
    ensure_shared_seed,
    reference_path,
    references_root,
)


def obsidian_config_path() -> Path:
    return user_config_base() / "obsidian" / "obsidian.json"


def vault_id(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).lower().encode("utf-8")).hexdigest()[:16]


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def ensure_shared_vault_files(shared_vault: Path, local_url: str) -> None:
    (shared_vault / ".obsidian").mkdir(parents=True, exist_ok=True)
    (shared_vault / "Obsidian 回传").mkdir(parents=True, exist_ok=True)
    app_json = shared_vault / ".obsidian" / "app.json"
    if not app_json.exists():
        write_json(app_json, {"attachmentFolderPath": "附件", "showLineNumber": False})
    inbox_readme = shared_vault / "Obsidian 回传" / "README.md"
    if not inbox_readme.exists():
        inbox_readme.write_text(
            "# Obsidian 回传\n\n"
            "把需要交给 Codex/Hermes 会审的新增或修改材料放在这里。"
            "独立 autosync 后台会复制到共享 `shiguan-imports/pending`，不会直接覆盖正式史馆记录。\n",
            encoding="utf-8",
            newline="\n",
        )
    entry = shared_vault / "史馆共享库入口.md"
    body = [
        "---",
        "type: shiguan_shared_vault_entry",
        "tags: [\"shiguan\", \"court-shiguan\", \"shared-source\", \"obsidian-vault\"]",
        "---",
        "",
        "# 史馆共享库入口",
        "",
        "这是 Obsidian 直接打开的权威共享史馆树 vault。",
        "",
        f"- 权威共享史馆根：`{references_root()}`",
        f"- 当前共享树：`{shared_vault}`",
        f"- WebUI：{local_url}",
        f"- 回传目录：[[Obsidian 回传/README|Obsidian 回传]]",
        f"- 兼容缓存 vault：`{default_obsidian_cache_vault()}`",
        "",
        "直接修改生成的 leaves/branches 可能会在下次生长树刷新时被重生成内容覆盖。"
        "需要交给朝廷处理的 Obsidian 编辑，应放入 `Obsidian 回传/`，由后台 autosync 送入 pending 队列，再经三省会审和门下复核。",
        "",
    ]
    entry.write_text("\n".join(body), encoding="utf-8", newline="\n")


def ensure_cache_vault_files(cache_vault: Path) -> None:
    obsidian_dir = cache_vault / ".obsidian"
    obsidian_dir.mkdir(parents=True, exist_ok=True)
    app_json = obsidian_dir / "app.json"
    if not app_json.exists():
        write_json(app_json, {"attachmentFolderPath": "附件", "showLineNumber": False})
    community_plugins = obsidian_dir / "community-plugins.json"
    if not community_plugins.exists():
        write_json(community_plugins, [])


def build_sync_config(shared_vault: Path, current: object) -> dict[str, object]:
    config = dict(current) if isinstance(current, dict) else {}
    api_key = str(config.get("api_key") or "")
    config.update(
        {
            "sync_mode": "filesystem_preserve_only",
            "auto_enabled": True,
            "autosync_enabled": True,
            "autosync_interval_seconds": int(config.get("autosync_interval_seconds") or 20),
            "output_folder": str(config.get("output_folder") or "Court Shiguan"),
            "vault_path": str(config.get("vault_path") or default_obsidian_cache_vault()),
            "cache_vault_path": str(config.get("cache_vault_path") or config.get("vault_path") or default_obsidian_cache_vault()),
            "source_vault_path": str(shared_vault),
            "parent_vault_path": str(default_obsidian_parent_vault()),
            "watch_paths": [
                str(config.get("cache_vault_path") or config.get("vault_path") or default_obsidian_cache_vault()),
                str(default_obsidian_inbox()),
            ],
            "autosync_script": str(Path(__file__).with_name("shiguan_autosync_daemon.py")),
            "filesystem_sync_script": str(Path(__file__).with_name("sync_shiguan_obsidian_vault.py")),
            "service_daemon_script": str(Path(__file__).with_name("shiguan_service_daemon.py")),
            "service_ensure_script": str(Path(__file__).with_name("ensure_shiguan_service_daemon.py")),
            "shared_shiguan_root": str(references_root()),
            "api_key": api_key,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    return config


def update_sync_config(shared_vault: Path) -> dict[str, object]:
    base = read_config_snapshot()
    config = {
        key: value
        for key, value in build_sync_config(shared_vault, base).items()
        if key not in RESERVED_FIELDS
    }
    result = patch_config(config, base_snapshot=base)
    if result.get("conflict"):
        raise RuntimeError("Obsidian sync config changed concurrently: " + ", ".join(result.get("conflict_fields", [])))
    return public_config(read_config_snapshot())


def obsidian_config_lock_path(config_path: Path) -> Path:
    return config_path.with_name(f"{config_path.name}.court-shiguan.lock")


def _read_obsidian_config_strict(config_path: Path) -> dict[str, object]:
    if not config_path.exists():
        return {"vaults": {}}
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Obsidian config is unreadable or malformed") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Obsidian config root must be an object")
    vaults = value.get("vaults")
    if vaults is None:
        value["vaults"] = {}
    elif not isinstance(vaults, dict):
        raise RuntimeError("Obsidian config vaults field must be an object")
    return dict(value)


def _config_digest(value: dict[str, object]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _merge_vault_registration(
    base: dict[str, object],
    current: dict[str, object],
    shared_vault: Path,
    set_open: bool,
    now_ms: int,
) -> tuple[dict[str, object], list[str]]:
    merged = copy.deepcopy(current)
    base_vaults = base.get("vaults") if isinstance(base.get("vaults"), dict) else {}
    current_vaults = merged.get("vaults") if isinstance(merged.get("vaults"), dict) else {}
    merged["vaults"] = current_vaults
    vid = vault_id(shared_vault)
    desired_path = str(shared_vault)
    conflicts: list[str] = []

    def field_value(vaults: dict[str, object], vault: str, field: str) -> object:
        record = vaults.get(vault)
        return record.get(field) if isinstance(record, dict) and field in record else None

    intended_open: dict[str, bool] = {vid: bool(set_open)}
    if set_open:
        for vault in set(base_vaults) | set(current_vaults):
            intended_open[str(vault)] = str(vault) == vid

    base_path = field_value(base_vaults, vid, "path")
    current_path = field_value(current_vaults, vid, "path")
    if current_path != base_path and current_path != desired_path:
        conflicts.append(f"vaults.{vid}.path")
    for vault, desired_open in intended_open.items():
        base_open = field_value(base_vaults, vault, "open")
        current_open = field_value(current_vaults, vault, "open")
        if current_open != base_open and current_open != desired_open:
            conflicts.append(f"vaults.{vault}.open")
    if conflicts:
        return merged, sorted(set(conflicts))

    for vault, desired_open in intended_open.items():
        raw_record = current_vaults.get(vault)
        record = dict(raw_record) if isinstance(raw_record, dict) else {}
        record["open"] = desired_open
        current_vaults[vault] = record
    raw_target = current_vaults.get(vid)
    target = dict(raw_target) if isinstance(raw_target, dict) else {}
    target["path"] = desired_path
    target["open"] = bool(set_open)
    target["ts"] = target.get("ts") or now_ms
    current_vaults[vid] = target
    return merged, []


def _exclusive_backup(config_path: Path) -> Path:
    stem = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    for index in range(1000):
        suffix = "" if index == 0 else f"-{index}"
        candidate = config_path.with_suffix(f".json.court-shiguan-{stem}{suffix}.bak")
        try:
            with candidate.open("xb") as handle:
                handle.write(config_path.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError("unable to create non-overwriting Obsidian config backup")


def register_obsidian_vault(
    shared_vault: Path,
    set_open: bool,
    dry_run: bool,
    *,
    precommit_hook: Callable[[Path], None] | None = None,
) -> dict[str, object]:
    config_path = obsidian_config_path()
    vid = vault_id(shared_vault)
    now_ms = int(time.time() * 1000)
    if dry_run:
        base = _read_obsidian_config_strict(config_path)
        data, conflicts = _merge_vault_registration(base, base, shared_vault, set_open, now_ms)
        vaults = data.get("vaults") if isinstance(data.get("vaults"), dict) else {}
        return {
            "obsidian_config": str(config_path),
            "backup": "",
            "vault_id": vid,
            "shared_vault_path": str(shared_vault),
            "set_open": set_open,
            "changed": data != base,
            "dry_run": True,
            "registered_vaults": len(vaults),
            "conflict": bool(conflicts),
            "conflict_fields": conflicts,
            "written": False,
            "post_write_verified": False,
            "config_lock": str(obsidian_config_lock_path(config_path)),
        }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    backup = ""
    with file_lock(obsidian_config_lock_path(config_path)):
        base = _read_obsidian_config_strict(config_path)
        if precommit_hook is not None:
            precommit_hook(config_path)
        current = _read_obsidian_config_strict(config_path)
        data, conflicts = _merge_vault_registration(base, current, shared_vault, set_open, now_ms)
        if conflicts:
            vaults = current.get("vaults") if isinstance(current.get("vaults"), dict) else {}
            return {
                "obsidian_config": str(config_path),
                "backup": "",
                "vault_id": vid,
                "shared_vault_path": str(shared_vault),
                "set_open": set_open,
                "changed": False,
                "dry_run": False,
                "registered_vaults": len(vaults),
                "conflict": True,
                "conflict_fields": conflicts,
                "written": False,
                "post_write_verified": False,
                "base_revision": _config_digest(base),
                "current_revision": _config_digest(current),
                "config_lock": str(obsidian_config_lock_path(config_path)),
            }
        if config_path.exists():
            backup = str(_exclusive_backup(config_path))
        atomic_write_text(
            config_path,
            json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
        )
        committed = _read_obsidian_config_strict(config_path)
        post_write_verified = committed == data
    vaults = data.get("vaults") if isinstance(data.get("vaults"), dict) else {}
    return {
        "obsidian_config": str(config_path),
        "backup": backup,
        "vault_id": vid,
        "shared_vault_path": str(shared_vault),
        "set_open": set_open,
        "changed": data != current,
        "dry_run": dry_run,
        "registered_vaults": len(vaults),
        "conflict": False,
        "conflict_fields": [],
        "written": True,
        "post_write_verified": post_write_verified,
        "base_revision": _config_digest(base),
        "current_revision": _config_digest(current),
        "committed_revision": _config_digest(committed),
        "config_lock": str(obsidian_config_lock_path(config_path)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-url", default="http://127.0.0.1:8765/")
    parser.add_argument("--no-set-open", action="store_true", help="Register the shared vault but do not mark it as the open vault.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    shared_vault = default_obsidian_shared_vault().resolve()
    if args.dry_run:
        config_path = reference_path("obsidian-sync", "config.json")
        planned = build_sync_config(shared_vault, read_json(config_path, {}))
        sync_config = {key: value for key, value in planned.items() if key != "api_key"}
    else:
        ensure_shared_seed()
        ensure_shared_vault_files(shared_vault, args.local_url)
        ensure_cache_vault_files(default_obsidian_cache_vault().resolve())
        sync_config = update_sync_config(shared_vault)
    registration = register_obsidian_vault(shared_vault, not args.no_set_open, args.dry_run)
    print(json.dumps({"ok": True, "dry_run": args.dry_run, "registration": registration, "sync_config": sync_config}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
