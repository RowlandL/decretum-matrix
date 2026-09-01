"""Install or roll back the optional Decretum Matrix Codex plugin projection.

The plugin projection carries metadata only. beta1.0.7 ships the skill and
read-only MCP; no lifecycle or Git hooks are installed. CC Switch remains the
owner of the direct ``mcp_servers.decretum_matrix`` registration, so this
installer never creates a duplicate MCP server entry.
"""



from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True


NAME = "decretum-matrix"
PLUGIN_ID = "decretum-matrix@personal"
PLUGIN_FILES = (
    ".codex-plugin/plugin.json",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def root_from_source() -> Path:
    return Path(__file__).resolve().parents[2]


def plugin_root(home: Path) -> Path:
    return home / "plugins" / NAME


def codex_config(home: Path) -> Path:
    return home / ".codex" / "config.toml"


def backup_root(home: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = home / ".agents" / "install-backups" / NAME / f"codex-plugin-{stamp}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def ensure_enabled(config: Path) -> tuple[bool, str]:
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    marker = f'[plugins."{PLUGIN_ID}"]'
    if marker in text:
        return False, text
    suffix = "\n" if text.endswith("\n") or not text else "\n\n"
    return True, text + suffix + marker + '\nenabled = true\n'


def mcp_configured(config: Path) -> bool:
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    return '[mcp_servers.decretum_matrix]' in text


def install(home: Path, source: Path) -> dict[str, object]:
    target = plugin_root(home)
    config = codex_config(home)
    backup = backup_root(home)
    target_backup = backup / "plugin-preimage"
    if target.exists():
        shutil.copytree(target, target_backup)
    config_preimage = backup / "config.toml.preimage"
    config_preimage.write_text(config.read_text(encoding="utf-8") if config.exists() else "", encoding="utf-8")

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for relative in PLUGIN_FILES:
        src = source / relative
        if not src.is_file():
            raise FileNotFoundError(src)
        dst = target / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied[relative] = sha256(dst)

    changed, updated_config = ensure_enabled(config)
    if changed:
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(updated_config, encoding="utf-8", newline="\n")
    receipt = {
        "schema": "decretum.codex_plugin_projection_receipt.v1",
        "status": "INSTALLED",
        "plugin_id": PLUGIN_ID,
        "source_root": str(source),
        "plugin_root": str(target),
        "plugin_files": copied,
        "config_path": str(config),
        "config_changed": changed,
        "mcp_registry_present": mcp_configured(config),
        "backup_root": str(backup),
        "rollback_command": f'python -B scripts/install_codex_plugin_projection.py rollback --receipt "{backup / "receipt.json"}"',
    }
    (backup / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def rollback(home: Path, receipt_path: Path) -> dict[str, object]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    backup = Path(str(receipt["backup_root"]))
    target = Path(str(receipt["plugin_root"]))
    config = Path(str(receipt["config_path"]))
    target_backup = backup / "plugin-preimage"
    if target.exists():
        shutil.rmtree(target)
    if target_backup.exists():
        shutil.copytree(target_backup, target)
    config_preimage = backup / "config.toml.preimage"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(config_preimage.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    return {
        "schema": "decretum.codex_plugin_projection_receipt.v1",
        "status": "ROLLED_BACK",
        "plugin_id": receipt.get("plugin_id"),
        "plugin_root": str(target),
        "config_path": str(config),
        "backup_root": str(backup),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    install_parser = sub.add_parser("install")
    install_parser.add_argument("--home", type=Path, default=Path.home())
    install_parser.add_argument("--source", type=Path, default=root_from_source())
    rollback_parser = sub.add_parser("rollback")
    rollback_parser.add_argument("--receipt", type=Path, required=True)
    rollback_parser.add_argument("--home", type=Path, default=Path.home())
    args = parser.parse_args(argv)
    result = install(args.home, args.source) if args.command == "install" else rollback(args.home, args.receipt)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

