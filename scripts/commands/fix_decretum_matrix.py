

#!/usr/bin/env python3
"""Plan or apply Decretum Matrix update, migration, and rollback repairs."""

from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
import importlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from court_diagnostics import (
    NAME,
    PROJECTION_PATH,
    resolve_user_path,
    select_source,
    write_audit_event,
)


SCHEMA = "decretum.fix.v1"


def _home_root(value: str | None) -> Path:
    return resolve_user_path(value, default=Path.home())


def _sync_codex_agent_roles(home: Path, *, write: bool) -> dict[str, object]:
    """Reuse the existing renderer for native Codex role files."""

    module = importlib.import_module("sync_codex_agents_from_profiles")
    previous = os.environ.get("CODEX_HOME")
    os.environ["CODEX_HOME"] = str(home / ".codex")
    try:
        result = module.sync_agents(write=write)
    finally:
        if previous is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = previous
    return result if isinstance(result, dict) else {"ok": False, "status": "INVALID"}


def _install_update(source_selection: dict[str, object], home: Path, *, write: bool) -> dict[str, object]:
    selected = source_selection.get("selected_root")
    if not isinstance(selected, str):
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "reason": "source_unavailable",
        }
    module = importlib.import_module("install_current_agent_copy")
    result = module.install_current_agent_copy(
        source_root=Path(selected),
        home_root=home,
        current_tool="codex",
        explicit_tools=[],
        tool_roots={"codex": home / ".codex" / "skills" / NAME},
        projection_manifest=Path(selected) / PROJECTION_PATH,
        write=write,
        fanout=False,
    )
    if not isinstance(result, dict) or result.get("ok") is not True:
        return result if isinstance(result, dict) else {"ok": False, "status": "INVALID"}
    role_result = _sync_codex_agent_roles(home, write=write)
    result = {**result, "codex_agent_roles": role_result}
    if role_result.get("ok") is not True:
        result.update(
            {
                "ok": False,
                "status": "PARTIAL",
                "reason": "codex_agent_roles_sync_failed",
            }
        )
    return result


def _legacy_migration(home: Path, roots: list[str], receipt: str | None, *, write: bool) -> dict[str, object]:
    if receipt:
        return {
            "schema": "court.legacy_skill_locator_migration.v1",
            "ok": False,
            "status": "BLOCKED",
            "write": write,
            "reason": "migration_receipt_requires_explicit_legacy_rollback_entrypoint",
        }
    module = importlib.import_module("migrate_legacy_skill_locator")
    selected = [
        resolve_user_path(value, default=home)
        for value in roots
    ] if roots else [
        home / ".agents" / "skills" / NAME,
        home / ".codex" / "skills" / NAME,
    ]
    return module.apply_migration(selected, write=write)


def _projection_rollback(home: Path, backup_root: str | None) -> dict[str, object]:
    if not backup_root:
        return {"ok": False, "status": "BLOCKED", "reason": "backup_root_required"}
    resolved = resolve_user_path(backup_root, default=home)
    if not resolved.is_dir():
        return {
            "ok": False,
            "status": "BLOCKED",
            "reason": "backup_root_missing",
            "backup_root": str(resolved),
        }
    module = importlib.import_module("install_current_agent_copy")
    return module.rollback_install_backup(
        home_root=home,
        backup_root=resolved,
    )


def _legacy_rollback(home: Path, receipt: str, *, write: bool) -> dict[str, object]:
    module = importlib.import_module("migrate_legacy_skill_locator")
    resolved = resolve_user_path(receipt, default=home)
    return module.rollback_receipt(resolved, write=write)


def run(argv: list[str] | None = None) -> dict[str, object]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("update", "migrate", "rollback"))
    parser.add_argument("--apply", action="store_true", help="Apply the requested repair. Default is a read-only plan.")
    parser.add_argument("--source-root")
    parser.add_argument("--mapped-root")
    parser.add_argument("--home-root")
    parser.add_argument("--root", action="append", default=[])
    parser.add_argument("--receipt")
    parser.add_argument("--backup-root")
    parser.add_argument("--format", choices=("text", "json"), default="json")
    args = parser.parse_args(argv)
    audit_intent = write_audit_event(
        task="fix-current-thread",
        operation=f"fix_{args.operation}",
        phase="intent",
        status="started",
        payload={
            "operation": args.operation,
            "apply": bool(args.apply),
            "source_root": args.source_root,
            "mapped_root": args.mapped_root,
            "home_root": args.home_root,
        },
    )
    home = _home_root(args.home_root)
    source_selection = select_source(source_root=args.source_root, mapped_root=args.mapped_root)
    backup = resolve_user_path(args.backup_root, default=home) if args.backup_root else None
    try:
        if args.operation == "update":
            result = _install_update(source_selection, home, write=args.apply)
        elif args.operation == "migrate":
            result = _legacy_migration(home, args.root, args.receipt, write=args.apply)
        elif args.receipt:
            result = _legacy_rollback(home, args.receipt, write=args.apply)
        else:
            result = (
                _projection_rollback(home, args.backup_root)
                if args.apply
                else {
                    "schema": "court.install_projection_rollback.v1",
                    "ok": backup is not None and backup.is_dir(),
                    "status": "ROLLBACK_PLANNED" if backup is not None and backup.is_dir() else "BLOCKED",
                    "write": False,
                    "backup_root": str(backup) if backup is not None else None,
                    "rollback_supported": backup is not None and backup.is_dir(),
                }
            )
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        result = {
            "schema": SCHEMA,
            "ok": False,
            "status": "BLOCKED",
            "write": bool(args.apply),
            "reason": f"fix_operation_failed:{type(exc).__name__}",
        }
    payload = {
        "schema": SCHEMA,
        "ok": result.get("ok") is True,
        "status": result.get("status", "INVALID"),
        "operation": args.operation,
        "write": bool(args.apply),
        "source_selection": source_selection,
        "home_root": str(home),
        "result": result,
        "private_body_accessed": False,
        "secret_values_exposed": False,
    }
    payload["audit_intent"] = audit_intent
    payload["audit_result"] = write_audit_event(
        task="fix-current-thread",
        operation=f"fix_{args.operation}",
        phase="result",
        status="succeeded" if payload["ok"] else "failed",
        payload={
            "operation": args.operation,
            "write": bool(args.apply),
            "status": payload["status"],
            "source_selection": source_selection,
            "result_status": result.get("status"),
        },
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    result = run(argv)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

