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

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from shiguan_paths import reference_path
from shiguan_entry_utils import court_code_requires_review

IKU_MARKER_PENDING_GENERATED = "待 archive_checkpoint 生成"
IKU_MARKER_PENDING_REFILL = "占位符由 archive_checkpoint 自动回填"
IKU_MARKER_LITERAL = "IKU"
IKU_LITERAL_RE = re.compile(r"(?<![A-Za-z0-9])IKU(?![A-Za-z0-9])")
REVIEW_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9])S(?:UIK){5}U[A-Z0-9]{2}"
    r"(?:-\d{8}-[A-Z0-9]+-[A-Z0-9-]+)?(?![A-Za-z0-9])",
    re.IGNORECASE,
)

FIELD_IDENTITY_PREFIXES = ("诏令编号：", "古制谱系：")

COURT_RE = re.compile(r"^- court_code: (\S.*)$", re.MULTILINE)
LINEAGE_RE = re.compile(r"^- ancient_lineage: (\S.*)$", re.MULTILINE)
RECORD_ID_RE = re.compile(r"^- (?:record_id|id): (\S.*)$", re.MULTILINE)
RECEIPT_RE = re.compile(r"^- (?:receipt|archive_receipt|receipt_hint|archive_receipt_json):\s*(\S.*)$", re.MULTILINE)


def archive_root() -> Path:
    """Resolve the shared plan-archives root (read-only, zero side effects).

    Detection must never create directories or seed files: the shared root is
    initialized by the installer, and a read-only probe (including the MCP
    ``shiguan.iku_candidates`` projection) has to stay byte-identical before
    and after a dry run (contract-a). Callers that need the shared seeds must
    initialize them through the install/apply path instead.
    """

    return reference_path("plan-archives")


def placeholder_kind(line: str) -> str | None:
    """Classify the placeholder marker inside a line (IKU/PENDING_GENERATED/PENDING_REFILL)."""
    if IKU_MARKER_PENDING_GENERATED in line:
        return "PENDING_GENERATED"
    if IKU_MARKER_PENDING_REFILL in line:
        return "PENDING_REFILL"
    if REVIEW_CODE_RE.search(line):
        return "LEGACY_REVIEW_CODE"
    if IKU_LITERAL_RE.search(line):
        return "IKU"
    return None


def field_kind(line: str) -> str:
    """Classify which record field a candidate line belongs to."""
    stripped = line.strip()
    if stripped.startswith("- court_code:"):
        return "诏令编号"
    if stripped.startswith(("- ancient_lineage:", "- lineage_display:")):
        return "古制谱系"
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
    *,
    receipt_verified: bool = False,
) -> tuple[str, str]:
    """Return (suggested_action, reason) for a candidate line."""
    if field == "正文" or placeholder is None:
        return "NOOP", "iku_in_nonidentity_field"
    if placeholder == "LEGACY_REVIEW_CODE":
        return "REVIEW", "legacy_review_code_requires_review"
    if court_code_requires_review(nearest_court_code) or "待审" in str(nearest_lineage or ""):
        return "REVIEW", "unresolved_lineage_source"
    valid_code = re.fullmatch(
        r"[A-Z0-9]+-\d{8}-[A-Z0-9]+-(?:[A-Z0-9]{4,6}-)?[A-Z0-9]{4}",
        str(nearest_court_code or ""),
        re.IGNORECASE,
    )
    if (
        valid_code and nearest_lineage
        and placeholder_kind(nearest_lineage) is None and receipt_hint and receipt_verified
    ):
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
    codes = set(value.strip() for value in COURT_RE.findall(text))
    lineages = set(value.strip() for value in LINEAGE_RE.findall(text))
    if len(codes) == 1:
        nearest_court_code = next(iter(codes))
    if len(lineages) == 1:
        nearest_lineage = next(iter(lineages))
    receipt_hint = None
    receipt_verified = False
    record_ref = None
    checkpoint_ref = None
    receipts = set(value.strip() for value in RECEIPT_RE.findall(text))
    if len(receipts) == 1:
        try:
            receipt = json.loads(receipts.pop())
        except (ValueError, TypeError):
            receipt = None
        times = {value.strip() for value in re.findall(r"(?m)^- time: (.+)$", text)}
        expected_source = path.relative_to(root.parent.parent).as_posix()
        if isinstance(receipt, dict):
            receipt_code = receipt.get("court_code")
            receipt_lineage = receipt.get("lineage_display")
            placeholder_types = {"IKU", "PENDING_GENERATED", "PENDING_REFILL"}
            receipt_verified = (
                receipt.get("schema") == "court.shiguan_archive_checkpoint_receipt.v1"
                and receipt.get("receipt_id") == f"shiguan:{receipt_code}"
                and all(value == receipt_code or placeholder_kind(value) in placeholder_types for value in codes)
                and all(value == receipt_lineage or placeholder_kind(value) in placeholder_types for value in lineages)
                and receipt.get("classification_status") != "review"
                and str(receipt.get("source") or "").replace("\\", "/") == expected_source
                and str(receipt.get("path") or "") == str(path)
                and len(times) == 1 and receipt.get("recorded_at") in times
                and str(receipt.get("record_ref") or "") == f"shiguan:{receipt_code}"
            )
            if receipt_verified:
                receipt_hint = str(receipt["receipt_id"])
                record_ref = str(receipt.get("record_ref") or receipt_hint)
                checkpoint_ref = str(receipt.get("receipt_id") or record_ref)
                nearest_court_code = str(receipt_code or "")
                nearest_lineage = str(receipt_lineage or "")
    try:
        record_path = path.relative_to(root.parent.parent).as_posix()
    except (ValueError, IndexError):
        record_path = path.relative_to(root).as_posix()
    return {
        "record_path": record_path,
        "record_id": record_id,
        "nearest_court_code": nearest_court_code,
        "nearest_lineage": nearest_lineage,
        "receipt_hint": receipt_hint,
        "receipt_verified": receipt_verified,
        "record_ref": record_ref,
        "checkpoint_ref": checkpoint_ref,
    }


def detect_record_candidates(text: str, path: Path, root: Path) -> list[dict[str, object]]:
    """Detect from one immutable text snapshot, shared with the repair writer."""
    candidates: list[dict[str, object]] = []
    line_offset = 0
    for block in re.split(r"(?m)(?=^## Checkpoint:)", text):
        record = _record_projection(block, path, root)
        for line_number, line in enumerate(block.splitlines(), start=line_offset + 1):
            # Structured receipt metadata is evidence, not another placeholder.
            if RECEIPT_RE.fullmatch(line):
                continue
            kind = placeholder_kind(line)
            if kind is None:
                continue
            field = field_kind(line)
            action, reason = suggest_action(
                kind, field, record["nearest_court_code"], record["nearest_lineage"],
                record["receipt_hint"], receipt_verified=bool(record["receipt_verified"]),
            )
            checkpoint = block.partition("\n")[0].strip()
            checkpoint_line_number = line_offset + 1
            checkpoint_ref = record.get("checkpoint_ref")
            if not checkpoint_ref and record.get("record_ref"):
                checkpoint_ref = f"{record['record_ref']}#checkpoint:{checkpoint_line_number}"
            candidates.append({
                **record,
                "checkpoint": checkpoint,
                "checkpoint_line_number": checkpoint_line_number,
                "field": field,
                "line_number": line_number,
                "line_coordinate": {
                    "record_ref": record.get("record_ref"),
                    "record_id": record.get("record_id"),
                    "record_path": record.get("record_path"),
                    "checkpoint_ref": checkpoint_ref,
                    "checkpoint": checkpoint,
                    "checkpoint_line_number": checkpoint_line_number,
                    "line_number": line_number,
                    "field": field,
                    "placeholder_kind": kind,
                },
                "placeholder_kind": kind,
                "suggested_action": action,
                "reason": reason,
            })
        line_offset += len(block.splitlines())
    return candidates


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
        candidates.extend(detect_record_candidates(text, path, root))
        if len(candidates) >= bounded:
            return candidates[:bounded]
    return candidates


def main() -> int:
    """Read-only CLI smoke entry: dump candidate projections as JSON."""
    import json

    print(json.dumps({"dry_run": True, "write_enabled": False, "candidates": detect_candidates()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
