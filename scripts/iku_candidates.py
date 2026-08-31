"""Read-only IKU placeholder candidate detection for plan-archive records.

Pure detection functions with no filesystem writes. Mirrors the three-state
semantics frozen in docs/plans/beta1.0.8/contracts/contract-a-iku-candidates.md
and references/fixtures/iku-candidates.json:

- NOOP: placeholder marker appears in a non-identity field or is ambiguous.
- REVIEW: identity field but no safe single source (missing receipt / conflict).
- REPAIR_CANDIDATE: identity field with a safe single nearest source to refill.

The detector never writes; repair is a separate authority-bound CLI path (A2).
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from shiguan_paths import ensure_shared_seed, reference_path

IKU_MARKER_PENDING_GENERATED = "待 archive_checkpoint 生成"
IKU_MARKER_PENDING_REFILL = "占位符由 archive_checkpoint 自动回填"
IKU_MARKER_LITERAL = "IKU"
IKU_LITERAL_RE = re.compile(r"(?<![A-Za-z0-9])IKU(?![A-Za-z0-9])")

FIELD_IDENTITY_PREFIXES = ("诏令编号：", "古制谱系：")

COURT_RE = re.compile(r"^- court_code: (\S.*)$", re.MULTILINE)
LINEAGE_RE = re.compile(r"^- ancient_lineage: (\S.*)$", re.MULTILINE)
RECORD_ID_RE = re.compile(r"^- (?:record_id|id): (\S.*)$", re.MULTILINE)
RECEIPT_RE = re.compile(r"archive_checkpoint[^\n]{0,120}")


def archive_root() -> Path:
    """Resolve the shared plan-archives root (read-only)."""
    ensure_shared_seed()
    return reference_path("plan-archives")


def fragment_sha256(fragment: str) -> str:
    return hashlib.sha256(fragment.encode("utf-8")).hexdigest()


def placeholder_kind(line: str) -> str | None:
    """Classify the placeholder marker inside a line (IKU/PENDING_GENERATED/PENDING_REFILL)."""
    if IKU_MARKER_PENDING_GENERATED in line:
        return "PENDING_GENERATED"
    if IKU_MARKER_PENDING_REFILL in line:
        return "PENDING_REFILL"
    if IKU_LITERAL_RE.search(line):
        return "IKU"
    return None


def field_kind(line: str) -> str:
    """Classify which record field a candidate line belongs to."""
    stripped = line.strip()
    for prefix in FIELD_IDENTITY_PREFIXES:
        if stripped.startswith(prefix):
            return "诏令编号" if prefix == "诏令编号：" else "古制谱系"
    return "正文"


def suggest_action(
    placeholder: str | None,
    field: str,
    nearest_court_code: str | None,
    nearest_lineage: str | None,
    receipt_hint: str | None,
) -> tuple[str, str]:
    """Return (suggested_action, reason) for a candidate line."""
    if field == "正文" or placeholder is None:
        return "NOOP", "iku_in_nonidentity_field"
    if nearest_court_code and nearest_lineage and receipt_hint:
        return "REPAIR_CANDIDATE", "safe_placeholder_identity_field"
    return "REVIEW", "missing_receipt_or_source_conflict"


def _record_projection(text: str, path: Path, root: Path) -> dict[str, object]:
    """Extract record-level metadata for a plan-archive file."""
    record_id = ""
    match = RECORD_ID_RE.search(text)
    if match:
        record_id = match.group(1).strip()
    if not record_id:
        record_id = path.stem
    nearest_court_code = None
    nearest_lineage = None
    court_match = COURT_RE.search(text)
    if court_match:
        nearest_court_code = court_match.group(1).strip()
    lineage_match = LINEAGE_RE.search(text)
    if lineage_match:
        nearest_lineage = lineage_match.group(1).strip()
    receipt_hint = None
    receipt_match = RECEIPT_RE.search(text)
    if receipt_match:
        receipt_hint = receipt_match.group(0).strip()[:160] or None
    try:
        record_path = str(path.relative_to(root.parents[1]))
    except ValueError:
        record_path = str(path.relative_to(root))
    return {
        "record_path": record_path,
        "record_id": record_id,
        "nearest_court_code": nearest_court_code,
        "nearest_lineage": nearest_lineage,
        "receipt_hint": receipt_hint,
    }


def detect_candidates(
    scope: str = "plan-archives",
    limit: int = 20,
    root: Path | None = None,
) -> list[dict[str, object]]:
    """Scan plan-archive records and return IKU candidate projections (read-only)."""
    if scope != "plan-archives":
        raise ValueError(f"unsupported_scope:{scope}")
    bounded = max(1, min(int(limit), 100))
    root = Path(root) if root is not None else archive_root()
    candidates: list[dict[str, object]] = []
    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        record = _record_projection(text, path, root)
        for line in text.splitlines():
            kind = placeholder_kind(line)
            if kind is None:
                continue
            field = field_kind(line)
            action, reason = suggest_action(
                kind,
                field,
                record["nearest_court_code"],
                record["nearest_lineage"],
                record["receipt_hint"],
            )
            fragment = line.strip()
            if not fragment:
                continue
            candidates.append(
                {
                    "record_path": record["record_path"],
                    "record_id": record["record_id"],
                    "field": field,
                    "fragment_sha256": fragment_sha256(fragment),
                    "placeholder_kind": kind,
                    "nearest_court_code": record["nearest_court_code"],
                    "nearest_lineage": record["nearest_lineage"],
                    "receipt_hint": record["receipt_hint"],
                    "suggested_action": action,
                    "reason": reason,
                }
            )
            if len(candidates) >= bounded:
                return candidates
    return candidates


def main() -> int:
    """Read-only CLI smoke entry: dump candidate projections as JSON."""
    import json

    print(json.dumps({"dry_run": True, "write_enabled": False, "candidates": detect_candidates()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
