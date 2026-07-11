"""Check pending Shiguan md/txt imports for court startup."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True

from court_file_lock import atomic_write_text, file_lock
from shiguan_paths import code_root, reference_path


PENDING_SUFFIXES = {".json", ".md", ".markdown", ".txt"}
SIDECAR_SUFFIXES = (".metadata.json", ".meta.json")
MAX_SIDECAR_BYTES = 256 * 1024
SIDECAR_FIELDS = {
    "id",
    "filename",
    "source_type",
    "status",
    "imported_at",
    "char_count",
    "estimated_tokens",
    "sha256",
    "suggested_processor",
}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def valid_sidecar_record(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != SIDECAR_FIELDS:
        return False
    filename = value.get("filename")
    return bool(
        isinstance(value.get("id"), str)
        and str(value.get("id")).strip()
        and isinstance(filename, str)
        and filename.strip()
        and Path(filename).name == filename
        and isinstance(value.get("source_type"), str)
        and str(value.get("source_type")).strip()
        and value.get("status") == "pending"
        and isinstance(value.get("imported_at"), str)
        and str(value.get("imported_at")).strip()
        and type(value.get("char_count")) is int
        and int(value.get("char_count")) >= 0
        and type(value.get("estimated_tokens")) is int
        and int(value.get("estimated_tokens")) >= 0
        and isinstance(value.get("sha256"), str)
        and SHA256_RE.fullmatch(str(value.get("sha256")))
        and isinstance(value.get("suggested_processor"), str)
        and str(value.get("suggested_processor")).strip()
    )


def skill_root() -> Path:
    return code_root()


def pending_root() -> Path:
    return reference_path("shiguan-imports", "pending")


def seen_path() -> Path:
    return reference_path("shiguan-imports", "startup-seen.json")


def seen_lock_path() -> Path:
    return reference_path("court-runtime", "shiguan-import-seen.lock")


def is_sidecar(path: Path) -> bool:
    lowered = path.name.lower()
    return any(lowered.endswith(suffix) for suffix in SIDECAR_SUFFIXES)


def sidecar_candidates(path: Path) -> tuple[Path, ...]:
    return (
        path.with_name(f"{path.stem}.metadata.json"),
        path.with_name(f"{path.stem}.meta.json"),
        path.with_name(f"{path.name}.metadata.json"),
    )


def load_sidecar(path: Path) -> tuple[dict[str, object] | None, Path | None, str]:
    for candidate in sidecar_candidates(path):
        if not candidate.is_file():
            continue
        try:
            if candidate.is_symlink() or candidate.lstat().st_size > MAX_SIDECAR_BYTES:
                return None, candidate, "invalid_sidecar"
            value = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, candidate, "invalid_sidecar"
        if not valid_sidecar_record(value):
            return None, candidate, "invalid_sidecar"
        return value, candidate, "sidecar"
    return None, None, "unknown"


def pending_records() -> list[tuple[Path, dict[str, object] | None, Path | None, str]]:
    root = pending_root()
    if not root.exists():
        return []
    records: list[tuple[Path, dict[str, object] | None, Path | None, str]] = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path == seen_path() or is_sidecar(path):
            continue
        if path.suffix.lower() not in PENDING_SUFFIXES:
            continue
        metadata, sidecar, status = load_sidecar(path)
        records.append((path, metadata, sidecar, status))
    return records


def load_seen_ids() -> set[str]:
    path = seen_path()
    if not path.exists():
        return set()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(value, dict):
        return set()
    raw_ids = value.get("seen_ids")
    if not isinstance(raw_ids, list):
        return set()
    return {str(item) for item in raw_ids if str(item).strip()}


def write_seen_ids(ids: set[str]) -> None:
    """Merge announced ids into the shared seen ledger without lost updates."""

    normalized = {str(item) for item in ids if str(item).strip()}
    if not normalized:
        return
    path = seen_path()
    with file_lock(seen_lock_path(), timeout=30.0):
        # Re-read only after acquiring the cross-process lock.  Reading before
        # the lock and replacing the file would let concurrent --mark-seen
        # processes overwrite each other's ids.
        merged = load_seen_ids() | normalized
        payload = {
            "seen_ids": sorted(merged),
            "note": "Tracks md/txt imports already reported during court startup.",
        }
        atomic_write_text(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )


def optional_nonnegative_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def public_record(
    path: Path,
    record: dict[str, object] | None,
    sidecar: Path | None,
    metadata_status: str,
) -> dict[str, object]:
    metadata = record or {}
    file_stat = path.stat()
    estimated_tokens = optional_nonnegative_int(metadata.get("estimated_tokens"))
    char_count = optional_nonnegative_int(metadata.get("char_count"))
    return {
        "id": metadata.get("id") or path.stem,
        "filename": metadata.get("filename") or path.name,
        "source_type": metadata.get("source_type") or path.suffix.lower().lstrip("."),
        "status": metadata.get("status") or "pending",
        "imported_at": metadata.get("imported_at") or "",
        "char_count": char_count,
        "estimated_tokens": estimated_tokens,
        "sha256": metadata.get("sha256") or "",
        "suggested_processor": metadata.get("suggested_processor") or "codex",
        "record_path": str(path),
        "metadata_status": metadata_status,
        "metadata_sidecar": str(sidecar) if sidecar else "",
        "file_size_bytes": file_stat.st_size,
        "file_mtime_ns": file_stat.st_mtime_ns,
    }


def aggregate_known(items: list[dict[str, object]], key: str) -> tuple[int | None, int, str]:
    known = [value for item in items if isinstance((value := item.get(key)), int)]
    total = sum(known)
    if len(known) == len(items):
        return total, total, "complete"
    if known:
        return None, total, "partial"
    return None, 0, "unknown"


def queue_summary(limit: int) -> dict[str, object]:
    seen_ids = load_seen_ids()
    publics: list[dict[str, object]] = []
    scan_skipped_count = 0
    for path, record, sidecar, status in pending_records():
        try:
            publics.append(public_record(path, record, sidecar, status))
        except OSError:
            # A concurrent reviewer may move a queue item after enumeration.
            # Treat that transient as a skipped snapshot row, not a CLI crash.
            scan_skipped_count += 1
    for item in publics:
        item["is_new"] = str(item.get("id") or "") not in seen_ids
    new_items = [item for item in publics if item.get("is_new")]
    total_tokens, known_tokens, token_status = aggregate_known(publics, "estimated_tokens")
    total_chars, known_chars, char_status = aggregate_known(publics, "char_count")
    new_tokens, new_known_tokens, new_token_status = aggregate_known(new_items, "estimated_tokens")
    new_chars, new_known_chars, new_char_status = aggregate_known(new_items, "char_count")
    pending_count = len(publics)
    unknown_metadata_count = sum(1 for item in publics if item.get("metadata_status") != "sidecar")
    unknown_estimated_tokens_count = sum(1 for item in publics if not isinstance(item.get("estimated_tokens"), int))
    unknown_char_count_count = sum(1 for item in publics if not isinstance(item.get("char_count"), int))
    token_phrase = (
        f"约 {total_tokens} tokens"
        if total_tokens is not None
        else (
            f"token 估算 {token_status}（{unknown_estimated_tokens_count} 份缺少可用 estimated_tokens；"
            f"其中 {unknown_metadata_count} 份缺少有效 metadata sidecar）"
        )
    )
    return {
        "pending_count": pending_count,
        "new_count": len(new_items),
        "estimated_tokens": total_tokens,
        "new_estimated_tokens": new_tokens,
        "known_estimated_tokens": known_tokens,
        "new_known_estimated_tokens": new_known_tokens,
        "estimated_tokens_status": token_status,
        "new_estimated_tokens_status": new_token_status,
        "char_count": total_chars,
        "new_char_count": new_chars,
        "known_char_count": known_chars,
        "new_known_char_count": new_known_chars,
        "char_count_status": char_status,
        "new_char_count_status": new_char_status,
        "unknown_metadata_count": unknown_metadata_count,
        "unknown_estimated_tokens_count": unknown_estimated_tokens_count,
        "unknown_char_count_count": unknown_char_count_count,
        "scan_skipped_count": scan_skipped_count,
        "queue_root": str(pending_root()),
        "seen_path": str(seen_path()),
        "_pending_ids": [str(item.get("id") or "") for item in publics],
        "samples": publics[:limit],
        "new_samples": new_items[:limit],
        "has_pending": bool(publics),
        "has_new": bool(new_items),
        "startup_message": (
            f"发现 {pending_count} 份待 Codex 处理导入材料，其中新增 {len(new_items)} 份；"
            f"{token_phrase}。"
            if publics
            else "没有待 Codex 处理的导入材料。"
        ),
    }


def print_text(summary: dict[str, object]) -> None:
    print(summary["startup_message"])
    print(f"queue_root: {summary['queue_root']}")
    if not summary.get("has_pending"):
        return
    print(f"pending_count: {summary['pending_count']}")
    print(f"new_count: {summary['new_count']}")
    print(f"estimated_tokens: {summary['estimated_tokens'] if summary['estimated_tokens'] is not None else 'unknown'}")
    print(f"estimated_tokens_status: {summary['estimated_tokens_status']}")
    print(f"new_estimated_tokens: {summary['new_estimated_tokens'] if summary['new_estimated_tokens'] is not None else 'unknown'}")
    print(f"char_count: {summary['char_count'] if summary['char_count'] is not None else 'unknown'}")
    print(f"seen_path: {summary['seen_path']}")
    print("samples:")
    for item in summary.get("samples", []):
        if not isinstance(item, dict):
            continue
        print(
            "- "
            f"{item.get('filename')} "
            f"new={item.get('is_new')} "
            f"tokens={item.get('estimated_tokens') if item.get('estimated_tokens') is not None else 'unknown'} "
            f"chars={item.get('char_count') if item.get('char_count') is not None else 'unknown'} "
            f"metadata={item.get('metadata_status')} "
            f"path={item.get('record_path')}"
        )
    print("processing_gate: ask_user_before_loading_raw_text")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument(
        "--mark-seen",
        action="store_true",
        help="After reporting, remember current pending import ids as already announced.",
    )
    args = parser.parse_args()

    summary = queue_summary(max(0, args.limit))
    public_summary = {key: value for key, value in summary.items() if not key.startswith("_")}
    if args.format == "json":
        json.dump(public_summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_text(public_summary)
    if args.mark_seen:
        all_ids = {str(item) for item in summary.get("_pending_ids", []) if str(item).strip()}
        write_seen_ids(all_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
