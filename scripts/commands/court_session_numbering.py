"""Start-of-conversation court_code allocation with closeout reuse (P3-1 fix).

The Shiguan court_code is normally issued when a conversation starts, not when
it is closed: the host calls ``domain_court_code_issue`` (or the ``issue`` CLI
entry) at session start, the allocation is persisted per session under
``court-runtime/session-numbering/``, and the closeout path
(``archive_checkpoint`` with ``--session-id``) reuses that allocation verbatim
instead of generating a second number.

Single-authority guarantee: the allocation still uses
``archive_checkpoint.next_daily_sequence`` (the unified generator) and is
collision-aware across concurrent session allocations for the same date, so no
second numbering set is created. ``domain_court_code_preview`` remains the
read-only preview; this module is the allocation (persistent, idempotent).
"""


from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import quote

sys.dont_write_bytecode = True

from shiguan_entry_utils import base36, enrich_entry
from shiguan_paths import reference_path


ALLOCATION_SCHEMA = "court.session_court_code_allocation.v1"
_DATE_RE = re.compile(r"\d{8}")
_SEQUENCE_RE = re.compile(r"[0-9A-Z]+")
_COURT_CODE_RE = re.compile(
    r"^[A-Z0-9]+-(?P<date>\d{8})-(?P<sequence>[0-9A-Z]+)-[A-Z0-9]{4}$"
)


def default_numbering_root() -> Path:
    return reference_path("court-runtime", "session-numbering")


def numbering_file(root: Path, session_id: str) -> Path:
    directory = quote(str(session_id).strip(), safe="")
    if directory in {"", ".", ".."}:
        raise ValueError("invalid_session_id")
    return Path(root) / f"{directory}.json"


def validate_session_allocation(
    allocation: object,
    session_id: str,
) -> dict[str, Any] | None:
    """Return a valid persisted allocation for ``session_id`` or ``None``.

    ``date_text`` supplied at closeout is deliberately not part of this gate:
    an allocation belongs to the session that issued it. Its own allocation
    date, sequence, and court-code segments must still agree so removing the
    closeout-date equality check cannot admit a malformed allocation.
    """
    expected_session = str(session_id or "").strip()
    if not expected_session or not isinstance(allocation, dict):
        return None
    if allocation.get("schema") != ALLOCATION_SCHEMA:
        return None
    if str(allocation.get("session_id") or "").strip() != expected_session:
        return None

    allocation_date = str(allocation.get("date") or "").strip()
    if not _DATE_RE.fullmatch(allocation_date):
        return None
    try:
        datetime.strptime(allocation_date, "%Y%m%d")
    except ValueError:
        return None

    sequence = str(allocation.get("daily_sequence") or "").strip().upper()
    if not _SEQUENCE_RE.fullmatch(sequence):
        return None
    try:
        if int(sequence, 36) < 1 or base36(int(sequence, 36)) != sequence:
            return None
    except ValueError:
        return None

    court_code = str(allocation.get("court_code") or "").strip()
    match = _COURT_CODE_RE.fullmatch(court_code)
    if not match:
        return None
    if match.group("date") != allocation_date or match.group("sequence") != sequence:
        return None
    return dict(allocation)


def _load_allocations(
    root: Path,
    date_text: str,
) -> list[dict[str, Any]]:
    allocations: list[dict[str, Any]] = []
    if not Path(root).exists():
        return allocations
    for path in sorted(Path(root).glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        candidate_session = (
            str(value.get("session_id") or "").strip()
            if isinstance(value, dict)
            else ""
        )
        validated = validate_session_allocation(value, candidate_session)
        if validated is not None and validated.get("date") == date_text:
            allocations.append(validated)
    return allocations


def _next_sequence(
    index: Path,
    date_text: str,
    root: Path,
) -> str:
    """Unified daily sequence with allocation-aware collision avoidance."""
    from archive_checkpoint import next_daily_sequence

    index_sequence = (
        next_daily_sequence(index, date_text) if index.exists() else "1"
    )
    allocated_numbers: list[int] = []
    for allocation in _load_allocations(root, date_text):
        raw = str(allocation.get("daily_sequence") or "").strip().upper()
        if raw and raw.isalnum():
            try:
                allocated_numbers.append(int(raw, 36))
            except ValueError:
                continue
    sequence_number = int(index_sequence, 36)
    if allocated_numbers:
        sequence_number = max(sequence_number, max(allocated_numbers) + 1)
    return base36(sequence_number)


def domain_court_code_issue(
    session_id: str,
    topic: str,
    date_text: str | None = None,
    index: Path | None = None,
    numbering_root: Path | None = None,
) -> dict[str, Any]:
    """Issue (allocate) a court_code at conversation start (idempotent).

    Persists one allocation per session; a second issue for the same session
    returns the same code (idempotent). The code is composed through the
    unified generator (``enrich_entry`` on ``next_daily_sequence``) so the
    closeout reuses it verbatim, never generating a second number.
    """
    session_id = str(session_id or "").strip()
    topic = str(topic or "").strip()
    if not session_id:
        return {
            "schema": ALLOCATION_SCHEMA,
            "ok": False,
            "errors": [{"field": "session_id", "kind": "contract", "code": "missing_session_id"}],
        }
    if not topic:
        return {
            "schema": ALLOCATION_SCHEMA,
            "ok": False,
            "errors": [{"field": "topic", "kind": "contract", "code": "missing_topic"}],
        }
    if len(topic) > 200:
        return {
            "schema": ALLOCATION_SCHEMA,
            "ok": False,
            "errors": [{"field": "topic", "kind": "contract", "code": "topic_too_long"}],
        }
    try:
        root = Path(numbering_root) if numbering_root is not None else default_numbering_root()
        path = numbering_file(root, session_id)
    except (OSError, ValueError) as exc:
        return {
            "schema": ALLOCATION_SCHEMA,
            "ok": False,
            "errors": [{"field": "session_id", "kind": "contract", "code": str(exc)}],
        }
    from court_file_lock import atomic_write_text, file_lock

    lock_path = root / ".allocation.lock"
    try:
        # Serialize the read-compute-write so concurrent issuers for the same
        # date can never compute the same daily_sequence from the same
        # allocation set (R-09). The idempotency re-check runs inside the lock
        # so a racing issuer observes the committed allocation.
        with file_lock(lock_path, timeout=30.0, poll_interval=0.02):
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    existing = None
                validated = validate_session_allocation(existing, session_id)
                if validated is not None:
                    return {**validated, "ok": True, "errors": [], "idempotent": True}
                return {
                    "schema": ALLOCATION_SCHEMA,
                    "ok": False,
                    "errors": [
                        {
                            "field": "allocation",
                            "kind": "contract",
                            "code": "invalid_existing_allocation",
                        }
                    ],
                }
            selected_date = date_text or datetime.now(timezone.utc).strftime("%Y%m%d")
            if index is not None:
                selected_index = Path(index)
            else:
                from archive_checkpoint import index_path

                selected_index = index_path()
            root.mkdir(parents=True, exist_ok=True)
            try:
                sequence = _next_sequence(selected_index, selected_date, root)
                synthetic: dict[str, object] = {
                    "record_type": "checkpoint",
                    "topic": topic,
                    "phase": "会话开始",
                    "status": "DRAFT",
                    "summary": f"会话开始编号分配：{topic}",
                    "time": f"{selected_date}T00:00:00+08:00",
                    "source": f"references/plan-archives/session-{quote(session_id, safe='')}-allocation.md",
                    "daily_sequence": sequence,
                }
                enrich_entry(synthetic)
                court_code = str(synthetic.get("court_code") or "")
            except (OSError, TypeError, ValueError) as exc:
                return {
                    "schema": ALLOCATION_SCHEMA,
                    "ok": False,
                    "errors": [{"field": "topic", "kind": "runtime", "code": str(exc)}],
                }
            if not court_code:
                return {
                    "schema": ALLOCATION_SCHEMA,
                    "ok": False,
                    "errors": [{"field": "court_code", "kind": "runtime", "code": "court_code_generation_failed"}],
                }
            allocation: dict[str, Any] = {
                "schema": ALLOCATION_SCHEMA,
                "ok": True,
                "errors": [],
                "session_id": session_id,
                "topic": topic,
                "date": selected_date,
                "daily_sequence": sequence,
                "court_code": court_code,
                "issued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "generator": "archive_checkpoint.next_daily_sequence",
                "authority": "unified_court_code_generator",
                "receipt_hint": "court.shiguan_archive_checkpoint_receipt.v1",
                "preview_only": False,
                "idempotent": False,
            }
            try:
                atomic_write_text(
                    path,
                    json.dumps(allocation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                )
            except OSError as exc:
                return {
                    "schema": ALLOCATION_SCHEMA,
                    "ok": False,
                    "errors": [{"field": "root", "kind": "runtime", "code": str(exc)}],
                }
            return allocation
    except (OSError, TimeoutError, ValueError) as exc:
        return {
            "schema": ALLOCATION_SCHEMA,
            "ok": False,
            "errors": [{"field": "root", "kind": "runtime", "code": str(exc)}],
        }


def resolve_session_allocation(
    session_id: str,
    date_text: str,
    numbering_root: Path | None = None,
) -> dict[str, Any] | None:
    """Read a valid persisted allocation for a session (closeout reuse).

    ``date_text`` is retained for callers using the original signature. The
    allocation date is intentionally checked against its court code instead
    of the closeout date, so a valid session survives a cross-day closeout.
    """
    session_id = str(session_id or "").strip()
    if not session_id:
        return None
    try:
        root = Path(numbering_root) if numbering_root is not None else default_numbering_root()
        path = numbering_file(root, session_id)
    except (OSError, ValueError):
        return None
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return validate_session_allocation(value, session_id)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    issue = sub.add_parser("issue", help="Allocate a court_code at conversation start.")
    issue.add_argument("--session-id", required=True)
    issue.add_argument("--topic", required=True)
    issue.add_argument("--date", default=None)
    issue.add_argument("--index", type=Path, default=None)
    issue.add_argument("--root", type=Path, default=None)
    issue.add_argument("--json", action="store_true")
    show = sub.add_parser("show", help="Show the persisted allocation for a session.")
    show.add_argument("--session-id", required=True)
    show.add_argument("--date", required=True)
    show.add_argument("--root", type=Path, default=None)
    show.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "issue":
        result = domain_court_code_issue(
            args.session_id,
            args.topic,
            date_text=args.date,
            index=args.index,
            numbering_root=args.root,
        )
        if not result.get("ok"):
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 1
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                f"COURT_CODE_ISSUE_OK {result['court_code']} "
                f"session={result['session_id']} date={result['date']} "
                f"sequence={result['daily_sequence']}"
            )
        return 0
    if args.command == "show":
        allocation = resolve_session_allocation(
            args.session_id, args.date, numbering_root=args.root
        )
        if allocation is None:
            print("COURT_CODE_ALLOCATION_NOT_FOUND", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(allocation, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"COURT_CODE_ALLOCATION {allocation['court_code']}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
