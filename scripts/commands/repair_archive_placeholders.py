

#!/usr/bin/env python
"""Authorized IKU placeholder repair for Shiguan archive records (FR-A / A2).

Read-only by default: ``--dry-run`` (default) reports what would change with
zero byte mutations. ``--apply`` requires an explicit ``--yes``, prints the
file list first, saves a rollback snapshot (original bytes) plus a repair
journal/receipt (original fragment fingerprint + nearest archive-checkpoint
receipt pointer) before writing, and is idempotent (a second ``--apply`` or
``--dry-run`` finds no new REPAIR_CANDIDATE).

Only REPAIR_CANDIDATE identity-field placeholders are repaired (safe single
nearest source, no conflict), matching contract-a three-state semantics. The
repaired ``court_code`` / ``ancient_lineage`` come verbatim from the nearest
checkpoint identity inside the same record (the unified receipt source), never
from a second numbering set.
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
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

sys.dont_write_bytecode = True

from court_file_lock import atomic_write_text, file_lock, shiguan_write_lock_path
from shiguan_paths import code_root, ensure_shared_seed, reference_path
from iku_candidates import detect_record_candidates


def skill_root() -> Path:
    return code_root()


def archive_root() -> Path:
    """Resolve the shared plan-archives root (read-only).

    The dry-run detector must not create directories or seed files: seeding is
    the installer/apply path's responsibility. Keeping this resolution pure
    guarantees ``--dry-run`` and the MCP read-only probe stay byte-identical.
    """

    return reference_path("plan-archives")


def default_backup_root() -> Path:
    ensure_shared_seed()
    return reference_path("court-runtime") / "shiguan-backups"


def _replacement_line(candidate: dict[str, object], line: str) -> str | None:
    """Compute the repaired line for a REPAIR_CANDIDATE identity field."""
    field = str(candidate.get("field") or "")
    if field == "诏令编号":
        code = str(candidate.get("nearest_court_code") or "").strip()
        if not code:
            return None
        prefix = "- court_code: " if line.lstrip().startswith("- court_code:") else "诏令编号："
        return f"{prefix}{code}"
    if field == "古制谱系":
        lineage = str(candidate.get("nearest_lineage") or "").strip()
        if not lineage:
            return None
        for prefix in ("- ancient_lineage:", "- lineage_display:"):
            if line.lstrip().startswith(prefix):
                return f"{prefix} {lineage}"
        return f"古制谱系：{lineage}"
    return None


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Durably write bytes via a sibling temp file, then atomically replace."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def plan_repairs(
    root: Path | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    """Return a read-only repair plan (REPAIR_CANDIDATE identity fields only)."""
    selected_root = Path(root) if root is not None else archive_root()
    plan: list[dict[str, object]] = []
    for path in sorted(selected_root.glob("*.md")):
        text = path.read_bytes().decode("utf-8")
        plan.extend(_plan_record_repairs(text, path, selected_root))
        if len(plan) >= max(1, min(int(limit), 100)):
            break
    return plan[:max(1, min(int(limit), 100))]


def _plan_record_repairs(text: str, path: Path, root: Path) -> list[dict[str, object]]:
    lines = text.splitlines(keepends=True)
    plan: list[dict[str, object]] = []
    for candidate in detect_record_candidates(text, path, root):
        if candidate["suggested_action"] != "REPAIR_CANDIDATE":
            continue
        line = lines[int(candidate["line_number"]) - 1]
        replacement = _replacement_line(candidate, line)
        if replacement is not None:
            plan.append({
                **candidate,
                "original_line_sha256": hashlib.sha256(line.encode("utf-8")).hexdigest(),
                "replacement_line": replacement,
            })
    return plan


def _grouped_repairs(
    plan: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in plan:
        grouped.setdefault(str(item["record_path"]), []).append(item)
    return grouped


def apply_repairs(
    plan: list[dict[str, object]],
    *,
    root: Path | None = None,
    backup_root: Path | None = None,
    yes: bool = False,
) -> dict[str, Any]:
    """Apply under the shared archive lock; explicit roots use an isolated lock."""
    if not yes:
        raise ValueError("repair_requires_yes")
    if not plan:
        return {"ok": True, "files": 0, "replacements": 0, "journal_path": None}
    lock = shiguan_write_lock_path() if root is None else Path(root).parent / "court-runtime" / "shiguan-write.lock"
    with file_lock(lock):
        return _apply_repairs_locked(plan, root=root, backup_root=backup_root, yes=yes)


def _apply_repairs_locked(
    plan: list[dict[str, object]], *, root: Path | None, backup_root: Path | None, yes: bool,
) -> dict[str, Any]:
    """Apply a repair plan with rollback snapshots + journal/receipt (P3-4/P3-5).

    Requires ``yes=True`` (the CLI ``--yes`` gate). Returns a journal with one
    entry per repaired file containing the original fingerprint, rollback
    snapshot path and the nearest archive-checkpoint receipt pointer. Raises
    ValueError when confirmation is missing.
    """
    if not yes:
        raise ValueError("repair_requires_yes")
    if not plan:
        return {"ok": True, "files": 0, "replacements": 0, "journal_path": None}
    selected_root = Path(root) if root is not None else archive_root()
    current_plan = plan_repairs(root=selected_root)
    if any(item not in current_plan for item in plan):
        raise ValueError("repair_plan_source_changed")
    selected_backup_root = (
        Path(backup_root) if backup_root is not None else default_backup_root()
    )
    selected_backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex
    journal: dict[str, Any] = {
        "schema": "court.iku_repair_journal.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": False,
        "write_enabled": True,
        "files": [],
    }
    files_changed = 0
    replacements_changed = 0
    journal_path = selected_backup_root / f"repair-journal-{timestamp}.json"
    journal["journal_path"] = str(journal_path)

    def persist_journal() -> None:
        atomic_write_text(journal_path, json.dumps(journal, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    for record_path, items in _grouped_repairs(plan).items():
        path = selected_root / Path(record_path).name
        if not path.exists():
            raise ValueError("repair_source_missing")
        original_bytes = path.read_bytes()
        original_text = original_bytes.decode("utf-8")
        snapshot_plan = _plan_record_repairs(original_text, path, selected_root)
        if any(item not in snapshot_plan for item in items):
            raise ValueError("repair_plan_source_changed")
        lines = original_text.splitlines(keepends=True)
        used: set[tuple[int, str]] = set()
        replaced_lines: list[dict[str, object]] = []
        for index, line in enumerate(lines):
            fragment_sha = hashlib.sha256(line.strip().encode("utf-8")).hexdigest()
            for item in items:
                if item.get("line_number") != index + 1:
                    continue
                key = str(item.get("fragment_sha256") or "")
                if key != fragment_sha or (index + 1, key) in used:
                    continue
                replacement = str(item.get("replacement_line") or "")
                newline = line[len(line.rstrip("\r\n")) :]
                lines[index] = replacement + newline
                used.add((index + 1, key))
                replaced_lines.append(
                    {
                        "field": item.get("field"),
                        "fragment_sha256": key,
                        "original_line_sha256": item.get("original_line_sha256"),
                        "replacement_line": replacement,
                        "line_number": int(item.get("line_number") or index + 1),
                        **{key: item.get(key) for key in (
                            "checkpoint", "checkpoint_line_number", "record_id", "receipt_hint",
                            "nearest_court_code", "nearest_lineage",
                        )},
                    }
                )
                break
        if not replaced_lines:
            continue
        repaired_text = "".join(lines)
        backup_name = f"{timestamp}-{path.name}.bak"
        backup_path = selected_backup_root / backup_name
        _atomic_write_bytes(backup_path, original_bytes)

        def single_source(field: str) -> object:
            values = {item.get(field) for item in items}
            return next(iter(values)) if len(values) == 1 else None

        file_journal = {
                "record_path": record_path,
                "record_id": single_source("record_id"),
                "beforeimage_verification": "exact_bytes",
                "original_size_bytes": len(original_bytes),
                "repaired_size_bytes": len(repaired_text.encode("utf-8")),
                "backup_path": str(backup_path),
                "receipt_hint": single_source("receipt_hint"),
                "nearest_court_code": single_source("nearest_court_code"),
                "nearest_lineage": single_source("nearest_lineage"),
                "source_scope": "per_replacement",
                "replacements": replaced_lines,
                "write_status": "PREPARED",
        }
        journal["files"].append(file_journal)
        persist_journal()
        try:
            if path.read_bytes() != original_bytes:
                raise ValueError("repair_beforeimage_changed")
            atomic_write_text(path, repaired_text, encoding="utf-8", newline="")
        except BaseException as exc:
            file_journal["write_status"] = "FAILED"
            file_journal["error"] = type(exc).__name__
            persist_journal()
            raise
        file_journal["write_status"] = "APPLIED"
        files_changed += 1
        replacements_changed += len(replaced_lines)
        persist_journal()
    return {
        "ok": True,
        "files": files_changed,
        "replacements": replacements_changed,
        "journal_path": str(journal_path),
    }


def rollback(backup_path: Path, target_path: Path) -> bool:
    """Restore a file from a rollback snapshot (P3-5)."""
    source = Path(backup_path)
    target = Path(target_path)
    if not source.exists():
        raise FileNotFoundError(f"rollback_snapshot_missing:{source}")
    _atomic_write_bytes(target, source.read_bytes())
    return True


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--backup-root", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = args.root or archive_root()
    plan = plan_repairs(root=root, limit=args.limit)
    if not args.apply:
        payload = {
            "dry_run": True,
            "write_enabled": False,
            "candidate_count": len(plan),
            "candidates": plan,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"IKU_REPAIR_DRY_RUN candidates={len(plan)}")
            for item in plan:
                print(
                    f"  {item['record_path']} line={item['line_number']} "
                    f"{item['field']} -> {item['replacement_line']}"
                )
        return 0

    if not args.yes:
        print("IKU_REPAIR_REFUSED requires --yes", file=sys.stderr)
        return 2
    if plan:
        print("IKU_REPAIR_PLAN files to change:")
        for record_path, items in _grouped_repairs(plan).items():
            print(f"  {record_path} ({len(items)} replacement(s))")
    try:
        result = apply_repairs(
            plan,
            root=root,
            backup_root=args.backup_root or default_backup_root(),
            yes=True,
        )
    except (OSError, ValueError) as exc:
        print(f"IKU_REPAIR_FAILED {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"IKU_REPAIR_OK files={result['files']} "
            f"replacements={result['replacements']} "
            f"journal={result['journal_path']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
