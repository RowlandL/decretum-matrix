"""Build a metadata-only, permanently dry-run Shiguan quarantine plan.

The planner never opens pending bodies.  It may list the pending directory,
read body ``stat`` metadata, and read bounded metadata sidecars.  It exposes no
apply mode and performs no queue writes, moves, deletes, or directory creation.
"""



from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True

from shiguan_paths import reference_path


SCHEMA = "court.shiguan_pending_quarantine_plan.v1"
PENDING_SUFFIXES = {".json", ".md", ".markdown", ".txt"}
SIDECAR_SUFFIXES = (".metadata.json", ".meta.json")
MAX_SIDECAR_BYTES = 256 * 1024
REQUIRED_SIDECAR_FIELDS = {
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
ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9._:+-]{1,64}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def default_pending_root() -> Path:
    """Return the shared queue path without creating it."""

    return reference_path("shiguan-imports", "pending")


def is_sidecar_name(name: str) -> bool:
    lowered = name.lower()
    return any(lowered.endswith(suffix) for suffix in SIDECAR_SUFFIXES)


def is_pending_body(path: Path) -> bool:
    return not is_sidecar_name(path.name)


def sidecar_candidates(path: Path) -> tuple[Path, ...]:
    return (
        path.with_name(f"{path.stem}.metadata.json"),
        path.with_name(f"{path.stem}.meta.json"),
        path.with_name(f"{path.name}.metadata.json"),
    )


def absolute_text(path: Path) -> str:
    """Render an absolute path without resolving a possible symlink target."""

    return str(path.expanduser().absolute())


def is_reparse_point_stat(value: object) -> bool:
    attributes = getattr(value, "st_file_attributes", 0)
    return isinstance(attributes, int) and bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def stat_fingerprint(path: Path) -> dict[str, object]:
    """Fingerprint a directory entry without opening or following it."""

    value = path.lstat()
    if stat.S_ISLNK(value.st_mode) or is_reparse_point_stat(value):
        entry_type = "reparse_point"
    elif stat.S_ISREG(value.st_mode):
        entry_type = "regular_file"
    elif stat.S_ISDIR(value.st_mode):
        entry_type = "directory"
    else:
        entry_type = "other"
    return {
        "schema": "court.file_stat_fingerprint.v1",
        "size_bytes": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "mtime_utc": datetime.fromtimestamp(value.st_mtime, timezone.utc).isoformat(),
        "mode": int(value.st_mode),
        "device": int(value.st_dev),
        "inode": int(value.st_ino),
        "entry_type": entry_type,
        "is_symlink": stat.S_ISLNK(value.st_mode),
        "is_reparse_point": is_reparse_point_stat(value),
    }


def fingerprint_sha256(value: dict[str, object]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_sidecar(value: object, expected_filename: str | None = None) -> list[str]:
    if not isinstance(value, dict):
        return ["sidecar_not_object"]

    errors: list[str] = []
    keys = {str(key) for key in value}
    missing = sorted(REQUIRED_SIDECAR_FIELDS - keys)
    unexpected = sorted(keys - REQUIRED_SIDECAR_FIELDS)
    if missing:
        errors.append("missing_fields:" + ",".join(missing))
    if unexpected:
        errors.append("unexpected_fields:" + ",".join(unexpected))
    if any(field in value for field in ("text", "raw_text", "body", "content")):
        errors.append("body_like_field_forbidden")

    metadata_id = value.get("id")
    if not isinstance(metadata_id, str) or not ID_RE.fullmatch(metadata_id.strip()):
        errors.append("invalid_id")

    filename = value.get("filename")
    if (
        not isinstance(filename, str)
        or not filename.strip()
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
    ):
        errors.append("invalid_filename")
    elif expected_filename is not None and filename != expected_filename:
        errors.append("filename_mismatch")

    if not isinstance(value.get("source_type"), str) or not TOKEN_RE.fullmatch(str(value.get("source_type") or "")):
        errors.append("invalid_source_type")
    if value.get("status") != "pending":
        errors.append("status_not_pending")
    imported_at = str(value.get("imported_at") or "")
    try:
        imported_time = datetime.fromisoformat(imported_at)
    except ValueError:
        imported_time = None
    if imported_time is None or imported_time.tzinfo is None:
        errors.append("invalid_imported_at")
    if not nonnegative_int(value.get("char_count")):
        errors.append("invalid_char_count")
    if not nonnegative_int(value.get("estimated_tokens")):
        errors.append("invalid_estimated_tokens")
    if not isinstance(value.get("sha256"), str) or not SHA256_RE.fullmatch(str(value.get("sha256") or "")):
        errors.append("invalid_sha256")
    if not isinstance(value.get("suggested_processor"), str) or not ID_RE.fullmatch(str(value.get("suggested_processor") or "")):
        errors.append("invalid_suggested_processor")
    return errors


def load_sidecar(
    path: Path,
    expected_filename: str | None = None,
) -> tuple[dict[str, object] | None, list[str], dict[str, object], str]:
    """Read one bounded sidecar, never a pending body."""

    fingerprint = stat_fingerprint(path)
    if path.is_symlink() or fingerprint.get("is_reparse_point") is True:
        return None, ["sidecar_reparse_point_not_read"], fingerprint, ""
    if fingerprint.get("entry_type") != "regular_file":
        return None, ["sidecar_not_regular_file"], fingerprint, ""
    if int(fingerprint["size_bytes"]) > MAX_SIDECAR_BYTES:
        return None, ["sidecar_too_large"], fingerprint, ""

    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | int(getattr(os, "O_BINARY", 0) or 0) | int(getattr(os, "O_NOFOLLOW", 0) or 0)
        descriptor = os.open(str(path), flags)
        before = os.fstat(descriptor)
        expected_identity = (
            int(fingerprint.get("device") or 0),
            int(fingerprint.get("inode") or 0),
            int(fingerprint.get("size_bytes") or 0),
            int(fingerprint.get("mtime_ns") or 0),
        )
        opened_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if opened_identity != expected_identity or is_reparse_point_stat(before):
            return None, ["sidecar_identity_changed_before_read"], fingerprint, ""
        raw = os.read(descriptor, MAX_SIDECAR_BYTES + 1)
        after = os.fstat(descriptor)
    except OSError:
        return None, ["sidecar_read_failed"], fingerprint, ""
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(raw) > MAX_SIDECAR_BYTES:
        return None, ["sidecar_too_large"], fingerprint, ""
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        return None, ["sidecar_changed_during_read"], fingerprint, ""
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, ["sidecar_invalid_utf8_or_json"], fingerprint, ""
    errors = validate_sidecar(value, expected_filename)
    if errors:
        return None, errors, fingerprint, hashlib.sha256(raw).hexdigest()
    return dict(value), [], fingerprint, hashlib.sha256(raw).hexdigest()


def quarantine_target(root: Path, category: str, source: Path) -> Path:
    return root.parent / "quarantine" / "planned-v1" / category / source.name


def rollback_hint(
    source_paths: list[tuple[Path, dict[str, object]]],
    targets: list[Path],
) -> dict[str, object]:
    if not targets:
        return {
            "required": False,
            "instruction": "No mutation is planned or performed for this item.",
            "source_retention_required": True,
            "append_only_copies": [],
        }
    copies = []
    for (source, fingerprint), target in zip(source_paths, targets):
        copies.append(
            {
                "original_source": absolute_text(source),
                "suggested_copy_target": absolute_text(target),
                "original_source_fingerprint": fingerprint,
            }
        )
    return {
        "required": "only_if_a_separately_authorized_tool_later_applies_the_plan",
        "instruction": (
            "This planner made no change. A later authorized action may append a verified copy and provenance record; "
            "the original source remains in place and retained."
        ),
        "source_retention_required": True,
        "append_only_copies": copies,
    }


def body_item(path: Path) -> dict[str, object]:
    source_fp = stat_fingerprint(path)
    candidates = list(dict.fromkeys(sidecar_candidates(path)))
    existing: list[Path] = []
    for candidate in candidates:
        try:
            candidate.lstat()
        except OSError:
            continue
        existing.append(candidate)
    metadata: dict[str, object] = {
        "status": "missing",
        "id": "",
        "sidecar_paths": [],
        "sidecar_fingerprints": [],
        "validation_errors": [],
    }
    classification = "missing_sidecar"
    reason_codes = ["metadata_sidecar_missing"]

    if source_fp.get("is_symlink") is True or source_fp.get("is_reparse_point") is True:
        classification = "unsafe_reparse_point"
        reason_codes = ["pending_body_reparse_point_not_followed"]
    elif source_fp.get("entry_type") != "regular_file":
        classification = "unknown_entry_type"
        reason_codes = ["pending_entry_not_proven_regular_file"]
    elif path.suffix.lower() not in PENDING_SUFFIXES:
        classification = "unsupported_body_type"
        reason_codes = ["pending_body_type_not_metadata_safe"]
    elif len(existing) > 1:
        fingerprints = []
        for candidate in existing:
            try:
                fingerprints.append(stat_fingerprint(candidate))
            except OSError:
                fingerprints.append({"schema": "court.file_stat_fingerprint.v1", "error": "stat_failed"})
        metadata.update(
            {
                "status": "invalid",
                "sidecar_paths": [absolute_text(candidate) for candidate in existing],
                "sidecar_fingerprints": fingerprints,
                "validation_errors": ["multiple_sidecars"],
            }
        )
        classification = "invalid_sidecar"
        reason_codes = ["multiple_sidecars"]
    elif existing:
        candidate = existing[0]
        value, errors, sidecar_fp, sidecar_content_sha256 = load_sidecar(candidate, path.name)
        metadata.update(
            {
                "status": "valid" if value is not None else "invalid",
                "id": str((value or {}).get("id") or ""),
                "sidecar_paths": [absolute_text(candidate)],
                "sidecar_fingerprints": [sidecar_fp],
                "sidecar_metadata_sha256": sidecar_content_sha256,
                "declared_body_sha256": str((value or {}).get("sha256") or ""),
                "validation_errors": errors,
            }
        )
        if value is not None:
            classification = "valid_sidecar"
            reason_codes = ["sidecar_contract_valid"]
        else:
            classification = "invalid_sidecar"
            reason_codes = errors or ["sidecar_invalid"]

    return {
        "kind": "pending_body",
        "classification": classification,
        "reason_codes": reason_codes,
        "recommendation": "retain_pending_review" if classification == "valid_sidecar" else "quarantine_recommended",
        "source": {
            "filename": path.name,
            "path": absolute_text(path),
            "source_fingerprint": source_fp,
        },
        "metadata": metadata,
    }


def orphan_sidecar_item(path: Path, root: Path) -> dict[str, object]:
    fingerprint = stat_fingerprint(path)
    target = quarantine_target(root, "orphan-sidecar", path)
    return {
        "kind": "metadata_sidecar",
        "classification": "orphan_sidecar",
        "reason_codes": ["no_pending_body_claims_sidecar"],
        "recommendation": "quarantine_recommended",
        "source": {
            "filename": path.name,
            "path": absolute_text(path),
            "source_fingerprint": fingerprint,
        },
        "metadata": {
            "status": "orphan",
            "id": "",
            "sidecar_paths": [absolute_text(path)],
            "sidecar_fingerprints": [fingerprint],
            "validation_errors": ["orphan_sidecar_not_read"],
        },
        "suggested_quarantine": {
            "category": "orphan-sidecar",
            "copy_targets": [absolute_text(target)],
            "source_retention_required": True,
            "execution_semantics": "append_verified_copy_and_provenance_only",
        },
        "rollback_hint": rollback_hint([(path, fingerprint)], [target]),
    }


def attach_quarantine_plan(item: dict[str, object], root: Path) -> None:
    source = item["source"]
    metadata = item["metadata"]
    if not isinstance(source, dict) or not isinstance(metadata, dict):
        raise TypeError("internal item schema drift")
    source_path = Path(str(source["path"]))
    source_fp = source["source_fingerprint"]
    if not isinstance(source_fp, dict):
        raise TypeError("internal fingerprint schema drift")

    if item["recommendation"] != "quarantine_recommended":
        item["suggested_quarantine"] = None
        item["rollback_hint"] = rollback_hint([], [])
        return

    category = str(item["classification"]).replace("_", "-")
    paths: list[tuple[Path, dict[str, object]]] = [(source_path, source_fp)]
    targets = [quarantine_target(root, category, source_path)]
    raw_paths = metadata.get("sidecar_paths")
    raw_fingerprints = metadata.get("sidecar_fingerprints")
    if isinstance(raw_paths, list) and isinstance(raw_fingerprints, list):
        for raw_path, fingerprint in zip(raw_paths, raw_fingerprints):
            if isinstance(fingerprint, dict):
                sidecar_path = Path(str(raw_path))
                paths.append((sidecar_path, fingerprint))
                targets.append(quarantine_target(root, category, sidecar_path))
    item["suggested_quarantine"] = {
        "category": category,
        "copy_targets": [absolute_text(target) for target in targets],
        "source_retention_required": True,
        "execution_semantics": "append_verified_copy_and_provenance_only",
    }
    item["rollback_hint"] = rollback_hint(paths, targets)


def mark_duplicate_ids(items: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for item in items:
        metadata = item.get("metadata")
        if item.get("kind") != "pending_body" or not isinstance(metadata, dict):
            continue
        if metadata.get("status") != "valid":
            continue
        metadata_id = str(metadata.get("id") or "").strip()
        if metadata_id:
            groups.setdefault(metadata_id, []).append(item)

    duplicate_groups = []
    for metadata_id, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        member_paths = sorted(str(member["source"]["path"]) for member in members if isinstance(member.get("source"), dict))
        duplicate_groups.append({"id": metadata_id, "member_count": len(members), "members": member_paths})
        for member in members:
            member["classification"] = "duplicate_id"
            member["reason_codes"] = ["metadata_id_not_unique"]
            member["recommendation"] = "quarantine_recommended"
            metadata = member.get("metadata")
            if isinstance(metadata, dict):
                metadata["duplicate_group_size"] = len(members)
                metadata["duplicate_paths"] = member_paths
    return duplicate_groups


def plan_snapshot_fingerprint(items: list[dict[str, object]]) -> dict[str, object]:
    basis = []
    for item in items:
        source = item.get("source")
        metadata = item.get("metadata")
        if not isinstance(source, dict) or not isinstance(metadata, dict):
            continue
        basis.append(
            {
                "filename": source.get("filename"),
                "fingerprint": source.get("source_fingerprint"),
                "classification": item.get("classification"),
                "metadata_status": metadata.get("status"),
                "metadata_id": metadata.get("id"),
                "sidecar_fingerprints": metadata.get("sidecar_fingerprints"),
                "sidecar_metadata_sha256": metadata.get("sidecar_metadata_sha256"),
                "declared_body_sha256": metadata.get("declared_body_sha256"),
            }
        )
    encoded = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema": "court.pending_queue_snapshot_fingerprint.v1",
        "algorithm": "sha256",
        "basis": "filenames_plus_stat_and_sidecar_metadata_only",
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def build_plan(pending_root: Path) -> dict[str, object]:
    root = pending_root.expanduser().absolute()
    entries: list[Path] = []
    errors: list[str] = []
    root_before: os.stat_result | None = None
    try:
        root_before = root.lstat()
    except FileNotFoundError:
        errors.append("pending_root_missing")
    except OSError:
        errors.append("pending_root_stat_failed")
    if root_before is not None and (stat.S_ISLNK(root_before.st_mode) or is_reparse_point_stat(root_before)):
        errors.append("pending_root_reparse_point_rejected")
    elif root_before is not None and not stat.S_ISDIR(root_before.st_mode):
        errors.append("pending_root_not_directory")
    elif root_before is not None:
        try:
            entries = sorted(root.iterdir(), key=lambda path: (path.name.casefold(), path.name))
            root_after = root.lstat()
            if (
                root_after.st_dev,
                root_after.st_ino,
                root_after.st_mtime_ns,
                root_after.st_mode,
            ) != (
                root_before.st_dev,
                root_before.st_ino,
                root_before.st_mtime_ns,
                root_before.st_mode,
            ):
                entries = []
                errors.append("pending_root_changed_during_listing")
        except OSError:
            errors.append("pending_root_list_failed")

    body_paths = [
        path
        for path in entries
        if is_pending_body(path)
    ]
    sidecar_paths = [
        path
        for path in entries
        if is_sidecar_name(path.name)
    ]
    claimed_sidecars = {
        absolute_text(candidate)
        for body in body_paths
        for candidate in sidecar_candidates(body)
    }

    items = [body_item(path) for path in body_paths]
    duplicate_groups = mark_duplicate_ids(items)
    for item in items:
        attach_quarantine_plan(item, root)
    for path in sidecar_paths:
        if absolute_text(path) not in claimed_sidecars:
            items.append(orphan_sidecar_item(path, root))
    items.sort(key=lambda item: (str(item["source"]["filename"]).casefold(), str(item["source"]["filename"])))

    classifications: dict[str, int] = {}
    for item in items:
        key = str(item.get("classification") or "unknown")
        classifications[key] = classifications.get(key, 0) + 1
    quarantine_count = sum(1 for item in items if item.get("recommendation") == "quarantine_recommended")
    if errors:
        status = "queue_unavailable"
    elif quarantine_count:
        status = "review_required"
    elif body_paths:
        status = "clear"
    else:
        status = "empty"

    snapshot_fingerprint = plan_snapshot_fingerprint(items)
    snapshot_sha256 = str(snapshot_fingerprint["sha256"])
    for item in items:
        metadata = item.get("metadata")
        source = item.get("source")
        if item.get("classification") != "valid_sidecar" or not isinstance(metadata, dict) or not isinstance(source, dict):
            item["governance_binding"] = None
            continue
        source_fingerprint = source.get("source_fingerprint")
        if not isinstance(source_fingerprint, dict):
            item["governance_binding"] = None
            continue
        item["governance_binding"] = {
            "candidate_id": str(metadata.get("id") or ""),
            "filename": str(source.get("filename") or ""),
            "source_fingerprint_sha256": fingerprint_sha256(source_fingerprint),
            "sidecar_metadata_sha256": str(metadata.get("sidecar_metadata_sha256") or ""),
            "declared_body_sha256": str(metadata.get("declared_body_sha256") or ""),
            "plan_snapshot_sha256": snapshot_sha256,
        }

    return {
        "schema": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "dry_run_only",
        "status": status,
        "queue_root": absolute_text(root),
        "suggested_quarantine_root": absolute_text(root.parent / "quarantine" / "planned-v1"),
        "inspection_contract": {
            "body_content_reads": 0,
            "body_access": ["filename", "lstat"],
            "sidecar_access": ["filename", "lstat", f"bounded_read_max_{MAX_SIDECAR_BYTES}_bytes"],
            "queue_mutations": 0,
            "apply_supported": False,
            "writes_moves_deletes_or_mkdir": False,
            "separate_authorization_required_for_any_future_apply": True,
        },
        "counts": {
            "directory_entries": len(entries),
            "pending_bodies": len(body_paths),
            "sidecar_files": len(sidecar_paths),
            "plan_items": len(items),
            "quarantine_recommended": quarantine_count,
            "classifications": dict(sorted(classifications.items())),
        },
        "snapshot_fingerprint": snapshot_fingerprint,
        "duplicate_id_groups": duplicate_groups,
        "errors": errors,
        "items": items,
    }


def print_text(plan: dict[str, object]) -> None:
    counts = plan["counts"]
    print(f"status: {plan['status']}")
    print(f"mode: {plan['mode']}")
    print(f"queue_root: {plan['queue_root']}")
    print(f"pending_bodies: {counts['pending_bodies']}")
    print(f"quarantine_recommended: {counts['quarantine_recommended']}")
    print(f"classifications: {json.dumps(counts['classifications'], ensure_ascii=False, sort_keys=True)}")
    print("mutation_gate: dry_run_only; apply_not_supported")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pending-root",
        type=Path,
        default=None,
        help="Pending directory to inspect. Defaults to the shared Shiguan pending queue.",
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args()

    plan = build_plan(args.pending_root or default_pending_root())
    if args.format == "text":
        print_text(plan)
    else:
        json.dump(plan, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

