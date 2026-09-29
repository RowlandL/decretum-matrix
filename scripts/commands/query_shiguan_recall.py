"""Advisory Shiguan recall: similar historical records for a pending state.

Read-only. Returns the k most similar historical Shiguan records (court code,
five-segment lineage, memory decision, grades) so a pending record can be judged
against precedent. Never writes Shiguan data, never mutates the taxonomy, and
carries no execution authority.
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
from pathlib import Path

sys.dont_write_bytecode = True

from court_public_api import shiguan_recall, shiguan_recall_stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shiguan-recall",
        description="Advisory Shiguan recall over the shared archive (read-only).",
    )
    parser.add_argument("--state", help="Pending record text (topic/phase/summary/key actions).")
    parser.add_argument("--state-file", help="Read the pending record text from a UTF-8 file.")
    parser.add_argument("--k", type=int, default=5, help="Number of matches, 1..20.")
    parser.add_argument("--same-topic", action="store_true", help="Restrict matches to the same topic.")
    parser.add_argument("--stats", action="store_true", help="Print recall service statistics instead.")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def _unwrap(result: object) -> dict:
    if isinstance(result, dict) and "stdout" in result:
        inner = result.get("stdout")
        return inner if isinstance(inner, dict) else {"ok": False, "problem": "bad_public_api_payload"}
    return result if isinstance(result, dict) else {"ok": False, "problem": "bad_public_api_payload"}


def _render_text(payload: dict) -> str:
    if payload.get("ok") is not True:
        return f"failed: {payload.get('problem')}\n{payload.get('detail') or payload.get('hint') or ''}".strip()
    if "matches" not in payload:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    lines = [
        f"indexed={payload.get('stats', {}).get('indexed_records')} k={payload.get('stats', {}).get('k')}",
    ]
    for i, m in enumerate(payload["matches"], 1):
        lines.append(
            f"{i}. sim={m['similarity']} [{m['stored_path']}] {m['topic']}\n"
            f"   {m['court_code']}  memory={m['memory_decision']} "
            f"risk={m['risk_level']} value={m['knowledge_value']} priority={m['priority_level']}\n"
            f"   {m['summary']}"
        )
    lines.append("advisory: 对照参考；不得据以写入史馆或替代门下裁定")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.stats:
        payload = _unwrap(shiguan_recall_stats())
    else:
        state = args.state or ""
        if args.state_file:
            try:
                state = Path(args.state_file).read_text(encoding="utf-8")
            except OSError as exc:
                print(json.dumps({"ok": False, "problem": "state_file_unreadable", "detail": str(exc)}, ensure_ascii=False))
                return 2
        if not state.strip():
            print(json.dumps({"ok": False, "problem": "state_required"}, ensure_ascii=False))
            return 2
        payload = _unwrap(shiguan_recall(state, k=args.k, same_topic=args.same_topic))

    if args.format == "text":
        print(_render_text(payload))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
