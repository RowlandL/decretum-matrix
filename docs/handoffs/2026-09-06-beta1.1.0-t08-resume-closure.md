# T08 Red-Line Resume Closure — beta1.1.0

- Resumed thread: `codex://threads/01a0715e-8957-7910-9800-eb19ed5d1437`
- Handoff authority: `docs/handoff_packages/handoff.MD`
- Branch: `release/beta1.1.0`
- Source head: `c7115ed` (working tree carries the T08 gate fixes; **not yet committed**)
- Scope: the four named beta1.1.0 T08 red-line gates only.

## Result

All four T08 red-line gates are **GREEN**.

| Gate | Status | Verifying check |
|---|---|---|
| `CONSULTATION_INVALID_SENDER_ACCEPTED` | GREEN | `check_consultation_refs_stay_on_existing_report_and_result_evidence` |
| `CONSULTATION_UNADMITTED_OFFICE_ACCEPTED` | GREEN | `check_consultation_refs_stay_on_existing_report_and_result_evidence` |
| `KeyError: 'residual_gaps'` (archive producer) | GREEN | `check_archive_receipt_records_runtime_replays_and_completes_with_concerns` |
| `CHECKPOINT_PRODUCER_MISSING_BOTH_ACCEPTED` | GREEN | `check_archive_receipt_records_runtime_replays_and_completes_with_concerns` |

## Fixes

1. **Consultation refs fail closed** (`scripts/court_runtime.py`):
   - `_validated_consultation_refs_for_task` now compares a reference's normalized `case_ref` (court_code + charter_revision) against the task's own case reference instead of the obsolete `charter_sha256`/`task_id` fields. Sender-role mismatch, unadmitted/invalid recipients, foreign/stale plan references, and write-authority grants are all rejected.
   - `agent-start` CLI `--case-ref` is parsed as a JSON object (`type=json_object_argument`) so the semantic binding comparison sees a dict, not a raw string.

2. **Legacy (non-case) create still binds a court code** (`scripts/court_runtime.py`):
   - `create_task` now generates a deterministic, contract-valid court code when no standard-session identity is supplied, so the invariant capsule, case reference, and archive receipts all agree.

3. **Archive producer residual gaps** (`scripts/services/archive_runtime_task.py`, already present):
   - The producer receipt carries `residual_gaps` + `residual_gaps_sha256` and they are cross-checked against the assessment binding; `_validated_archive_producer_receipt` requires them.

4. **Checkpoint producer evidence is mandatory** (`scripts/court_runtime.py`, already present + verified):
   - `complete_task_atomically` → `validate_checkpoint_receipt` rejects a `shiguan_checkpoint` that is missing `producer_receipt` or `producer_receipt_sha256` with `archive_producer_evidence_missing`.

5. **Check fixtures reconciled to the current contract** (`scripts/checks/check_semantic_continuity.py`, `scripts/checks/check_court_runtime_completion.py`):
   - T08 consultation check builds a reviewed/dispatchable case before admission; report args carry `case_ref`; stale-consultation fixture mutates the normalized `case_ref` (and matching plan ref) rather than an obsolete top-level `charter_revision`.
   - Completion check uses a `court_code` when building revision bindings, drops legacy capsule digest fields, and supplies `case_ref` to completion args.

## Evidence

- `D:\project\.staging\dm110-20260905\t08-bingbu\t08-gate-status.json` — gate-by-gate status.
- `D:\project\.staging\dm110-20260905\t08-bingbu\green-consultation.txt` — `CONSULTATION_GREEN_OK`.
- `D:\project\.staging\dm110-20260905\t08-bingbu\green-archive-producer.txt` — `ARCHIVE_PRODUCER_GREEN_OK`.
- `D:\project\.staging\dm110-20260905\t08-bingbu\lastfix\green-consultation-unadmitted-office.txt` — `CONSULTATION_UNADMITTED_OFFICE_REJECTED`.
- `D:\project\.staging\dm110-20260905\t08-bingbu\lastfix\green-checkpoint-producer-missing-both.txt` — `CHECKPOINT_PRODUCER_MISSING_BOTH_REJECTED`.
- Reproducer `reproduce_missing_both.py` now raises `archive_producer_evidence_missing` (was `CHECKPOINT_PRODUCER_MISSING_BOTH_ACCEPTED`).
- Updated `docs/reports/beta110-20260905/evidence-summary.json` (`t08` block and new `t08_resume_evidence`).

## Honest boundary

The four T08 gates are verified green in isolation. The broader beta1.1.0 required suite is **not** yet fully green on this working tree: `check_semantic_continuity` stops at `SEMANTIC_RESULT_ENVELOPE` and `check_court_runtime_completion` at `check_assessment_validation_and_deep_copy`, both due to **separate, non-T08** stale-fixture remnants of the in-progress `court_code`/`semantic-binding` refactor (e.g. obsolete `charter_sha256` references, out-of-date plan-referred admission fixtures). Those must be reconciled before a full release-gate closure; they are outside the four named T08 gates and are recorded here so no success is overstated.

## Next steps (for the release office)

1. Reconcile the remaining stale fixtures in `check_semantic_continuity.py` and `check_court_runtime_completion.py` to the current `court_code`/`invariant_capsule` contract (no `charter_sha256`, plan-backed admission).
2. Re-run the full `run_checks` required suite on a clean HEAD, then update `suite-summary.json` and `evidence-summary.json` `required_checks`/`tested_source_head` to the final commit.
3. Commit the bounded T08 gate fixes; do not publish or tag until the full suite is green.
