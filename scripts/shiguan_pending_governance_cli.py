"""Command-line surface for authenticated pending-governance metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

from shiguan_pending_governance import ACTORS, PendingGovernanceLedger


def _add_transition_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--actor", required=True, choices=sorted(ACTORS))
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--rollback-hint", required=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect-metadata")
    inspect_parser.add_argument("--pending-root", type=Path)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--candidate-id", required=True)
    metadata_parser = sub.add_parser("mark-metadata-reviewed")
    _add_transition_args(metadata_parser)
    authorize_parser = sub.add_parser("authorize-body")
    authorize_parser.add_argument("--candidate-id", action="append", required=True)
    authorize_parser.add_argument("--batch-id")
    authorize_parser.add_argument("--review-id", required=True)
    authorize_parser.add_argument("--actor", required=True, choices=sorted(ACTORS))
    authorize_parser.add_argument("--task-id", required=True)
    authorize_parser.add_argument("--agent-id", required=True)
    authorize_parser.add_argument("--evidence", required=True)
    authorize_parser.add_argument("--target", required=True)
    authorize_parser.add_argument("--rollback-hint", required=True)
    authorize_parser.add_argument(
        "--binding-json",
        action="append",
        required=True,
        help="Exact metadata-only governance binding JSON; repeat once per candidate.",
    )
    reviewed_parser = sub.add_parser("mark-reviewed")
    _add_transition_args(reviewed_parser)
    reviewed_parser.add_argument("--review-result-sha256", required=True)
    for name in ("promote", "reject", "quarantine"):
        _add_transition_args(sub.add_parser(name))
    args = parser.parse_args(argv)

    if args.command == "inspect-metadata":
        from plan_shiguan_pending_quarantine import build_plan, default_pending_root

        result: object = build_plan(args.pending_root or default_pending_root())
    else:
        ledger = PendingGovernanceLedger()
        if args.command == "status":
            result = ledger.latest(args.candidate_id)
        elif args.command == "authorize-body":
            scope_kind = "batch" if args.batch_id else "candidate"
            if not args.batch_id and len(args.candidate_id) != 1:
                parser.error("multiple candidates require --batch-id")
            scope_id = args.batch_id or args.candidate_id[0]
            bindings: dict[str, dict[str, object]] = {}
            for raw in args.binding_json:
                value = json.loads(raw)
                if not isinstance(value, dict):
                    parser.error("--binding-json must be a JSON object")
                candidate = str(value.get("candidate_id") or "")
                if not candidate or candidate in bindings:
                    parser.error("--binding-json candidate_id is missing or duplicated")
                bindings[candidate] = value
            if set(bindings) != set(args.candidate_id):
                parser.error("--binding-json must cover exactly the authorized candidates")
            result = ledger.authorize_body(
                candidate_ids=tuple(args.candidate_id),
                review_id=args.review_id,
                actor=args.actor,
                task_id=args.task_id,
                agent_id=args.agent_id,
                evidence=args.evidence,
                scope_kind=scope_kind,
                scope_id=scope_id,
                target=args.target,
                rollback_hint=args.rollback_hint,
                candidate_bindings=bindings,
            )
        else:
            state = {
                "mark-metadata-reviewed": "metadata_reviewed",
                "mark-reviewed": "reviewed",
                "promote": "promoted",
                "reject": "rejected",
                "quarantine": "quarantined",
            }[args.command]
            result = ledger.transition(
                candidate_id=args.candidate_id,
                review_id=args.review_id,
                actor=args.actor,
                task_id=args.task_id,
                agent_id=args.agent_id,
                to_state=state,
                evidence=args.evidence,
                target=args.target,
                rollback_hint=args.rollback_hint,
                review_result_sha256=getattr(args, "review_result_sha256", None),
            )
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
