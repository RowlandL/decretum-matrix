# Court Runtime Result And Recruitment Contract

For ordinary native tasks, use the current SKILL, active decree, and public
schemas; the current result-envelope contract is specified below. Historical R/C
and sealed-program exclusions in this reference apply to those named programs,
not automatically to unrelated tasks. Those program boundaries remain intact,
and this reference grants no authority beyond the active decree.

## Conversation Intake

A runtime task may be created only from an intake classified as `FORMAL_TASK`.
Questions, corrections, continuations, approvals, pauses, and cancellations are
control messages rather than new tasks. A correction or continuation must name
one existing target task unambiguously; otherwise intake fails closed and asks
for clarification. Task creation records the accepted charter and its digest so
later operations can prove which decree they serve.

## Runtime Schema And Office Identity

New and writable records use runtime schema v3. Older records may be normalized
only into a read-only compatibility view; normalization must not invent readiness,
upgrade stored bytes, or authorize a transition.

Every child execution is bound to an office identity before the runtime lock,
write, or event. The accepted NPSB contract requires canonical `role_key`,
`office_zh`, and `direct_superior`; verified profile and dossier hashes; a
canonical skill path and skill hash with explicit preload acknowledgement; and
the task/agent naming evidence required by the office assignment. The binding is
rechecked inside the lock to prevent stale pre-lock evidence. Missing, mismatched,
spoofed, or legacy-incomplete evidence remains fail-closed; historical false-ready
records stay read-only and never become execution-ready through normalization.

## Charter Revision

Each accepted correction creates the next charter revision and a new charter
digest while preserving revision history. A revision invalidates assessment
bindings and checkpoint state derived from the prior charter. Every later bind,
checkpoint, completion, or presentation operation must match the current task,
revision, and charter digest; stale callers are rejected rather than silently
rebased.

## Neutral Assessment Binding

`bind-assessment` accepts `court.runtime_assessment_binding.v1`; a raw
`court.outcome_assessment.v1` or an office result envelope is not this request.
The existing `court intake-schema` / MCP public contract exposes
`runtime_assessment_binding_contract` with the complete required field list.
The agent supplies its actual judgment; the runtime validates and binds it,
without executing a separate evaluator or substituting for Menxia review.

Use this shape with values from the current task and actual review evidence:

```json
{
  "schema": "court.runtime_assessment_binding.v1",
  "task_id": "<current task id>",
  "charter_revision": 1,
  "case_ref": {"court_code": "<issued code>", "charter_revision": 1},
  "assessment_ref": "<stable assessment document reference>",
  "evidence_ref": "<actual review evidence reference>",
  "gate": "PASSED_WITH_CONCERNS",
  "reasons": ["<actual concern>"],
  "completion_source": {
    "schema": "court.completion_source.v1",
    "task_id": "<same task id>",
    "charter_revision": 1,
    "case_ref": {"court_code": "<same issued code>", "charter_revision": 1},
    "sources": [{"kind": "host_report", "role": "menxia", "pointer": "<exact agent-report evidence>", "event_id": "<actual report event id>"}]
  },
  "completion_source_ref": "<stable source reference>",
  "residual_gaps": ["<one-line actual residual concern>"],
  "assessed_at": "<actual ISO timestamp with timezone>"
}
```

`residual_gaps` is a flat list of strings, not nested lists or objects.
`PASSED` requires empty reasons/gaps; `PASSED_WITH_CONCERNS` requires both.
Normal source items need no pointer hash. They bind a real, preloaded office's
report by exact pointer and optional event ID; ambiguity or a missing Menxia
report remains rejected. Existing digest-bearing records remain compatible.
Identical replay is idempotent and conflicting assessment bindings are rejected.

## Checkpoint Receipt And Completion

Completion requires a verified Shiguan checkpoint receipt bound to the exact
task, current charter, accepted assessment, record digest, archive path, receipt
identifier, and recorded time. A receipt is single-use. Completion uses a
recoverable, sequential two-ledger protocol rather than an atomic transaction.
A durable recovery marker records the exact phase before and between the task
ledger write and event-ledger write. Recovery from `PREPARED` or `TASK_WRITTEN`
rolls the task ledger back to the marker's preserved preimage and clears the
incomplete attempt. Recovery from `EVENT_WRITTEN` first proves the task and event
records are mutually consistent, then finalizes and clears the marker without
rolling back the completed pair. The runtime recovery outcome is `ROLLED_BACK`
for a successfully reverted incomplete attempt or `FINALIZED` for a proven,
consistent completed pair. Recovery-protocol evidence may be verified separately,
but `RECOVERY_VERIFIED` is not a returned runtime status. Neither outcome is an
atomicity claim, a blanket snapshot restore claim, or evidence that an external
archive write shared the transaction.

## Verified Presentation

R7-RC is a projection of actual persisted task and event history. Dashboard and
archive summaries must derive their status, digests, receipt, checkpoint, and
completion proof from task-scoped events, require the checkpoint event to precede
the unique completion event, and fail closed on missing, duplicate, reordered,
or inconsistent evidence. Raw `Done`, requested state, dry-run output, or an
unverified archive claim must never be presented as verified completion.

## Capability Recruitment

Recruitment is local-first. C1 records the capability gap and decision boundary;
C2-RC then evaluates only the bounded local `skill`, `plugin`, and `mcp` registry
with deterministic identities, explicit injected roots and authority, no ambient
fallback, and fail-closed conflict handling. Disabled or unverifiable candidates
remain non-dispatchable. This task performs zero network calls and zero external writes,
with no capability mutation. Where a wider evaluator recognizes a need
for public metadata discovery, creation, installation, or writing, it may return
only a structured intent/request with `next_action=ASK_USER` for the C1/C2
handoff to Shangshu; it must not initiate or describe an external flow here.
`C2_FULL` remains `HOLD_BY_AUTHORITY`, and no discovery, installation, write, or
other external authority is reopened by this contract.

## Purified Scope Exclusions

The purified lane does not execute, import, modify, test, review, retry, or claim
PASS for sealed R4; only hash verification is allowed. It does not semantically
inspect historical S1-S8/network-security bodies, perform network calls, probes,
scans, threat or attack work, fuzzing, penetration testing, or a security release
gate. It does not implement P1-P8, P4-CFG, CFG-0..9, U1-U5, C2-FULL,
`beta0.5.13`, queued insertions, SuperCC/visible-core bodies, mixed startup or
dispatch surfaces, OpenAI/Codex/account configuration, credentials, host
services, daemons, scheduled tasks, registry state, or active installed copies.

It does not package, install, or perform release work in the I1/C lane. Release
workflow is governed separately and is neither linked nor detailed here. It does
not modify product/release metadata, release policy, install documents, the
sealed concurrency/privacy preimage files, the Git index, commits, tags, or
remote publication, and it does not use destructive Git or recursive deletion.
If required work crosses any remaining boundary, record
`BLOCKED_BY_PURIFIED_SCOPE` and leave excluded bytes unchanged.

## RC2 Bound Result Envelope

For a semantic-bound dispatch, admission, start, report, and finish carry the
admitted checkpoint binding. The current `court.office.result.v1` contract is
published as `office_result_envelope_schema` by `court intake-schema` and MCP
`court.intake_schema`; both reuse the runtime's existing schema generator.
Use that schema instead of probing one missing field at a time.

Copy `task_id`, `semantic_epoch`, `case_ref`, `checkpoint_id`, `dispatch_uid`,
`attempt`, `office_instance_id`, `agent_id`, `role`, `direct_superior`,
`worktree`, and `write_set` from the admitted agent record. Carry the actual
`plan_ref` for the work; null is allowed when no plan exists. If the record has
`office_instance_kind` and `carrier_proof`, copy both without inventing host IDs.
Supply the actual `status` (`completed`, `failed`, or `cancelled`), a nonempty
`summary`, an array of evidence pointers, and `produced_at` as an ISO timestamp.
The `schema` value is `court.office.result.v1`; `write_set` and `evidence` are
arrays, not joined strings. Submit through the existing result-envelope argument
of report/finish. A free-text `--result` does not replace this envelope.

Ordinary result callers use `case_ref`, `plan_ref`, and `write_set`; do not add
the charter/capsule/write-set hash fields mentioned in historical R/C descriptions.
No caller-side file hashing is required. Missing or conflicting binding fields
remain rejected or quarantined and cannot advance the agent or task.

Legacy records and agents remain available for read-only diagnosis. They do not
become recruitable or mutable because a schema-normalized projection supplied
defaults. New admission callers must echo the expected semantic checkpoint;
new lifecycle callers must echo the admitted binding.

Operation receipts use canonical UUID `operation_id`, canonical
`payload_sha256`, and `expected_task_revision` CAS. Same id plus same payload is
an idempotent replay; same id plus a different payload is a conflict. The
operation journal may rehydrate a receipt after a caller loses the response,
but the current task operation remains authoritative.

## RC4 Unified Office Instance Lifecycle

`child_agent` and `worktree_thread` are transport carriers for one office
instance state machine, not separate authorities. Both use
`office admit|start|followup|preload-ack|report|finish|close`, the same RC2 current
semantic binding, the same structured result/quarantine rules, and the same
`task["agents"]` lifecycle ledger. Existing `agent-*` commands are
`child_agent` compatibility aliases.

`start`, formal `report`, and `finish` require the current task semantic state
to remain `DISPATCHABLE`. `QUARANTINED`, `REVERIFY`, or any other state fails
before task or event bytes change. A formal report also requires a passed exact
preload acknowledgement and otherwise fails with zero task/event writes.
`close` and terminal `reconcile` remain release-only operations governed by the
existing terminal/release contract; they do not restore dispatch authority.

Each lifecycle receipt uses `court.office.lifecycle_receipt.v1` and preserves
task/revision, semantic epoch and hashes, checkpoint, dispatch uid, attempt,
office instance id/kind, role/superior, event id, status, frozen decree lineage,
and carrier proof. Child proof contains only `agent_id`. Worktree proof contains
`thread_id`, canonical worktree id/path, repo id, common-dir/worktree
fingerprints, branch, and start head. Worktree receipts carry a unique
metadata-first Shiguan pointer only; they do not create a second task/event
ledger, store a transcript body, or give the CLI thread/process/Git control.

Public startup uses unified `court open` / `court open --fast`; the
runtime-internal `decree-open` operation only freezes `main_court_code`,
`lineage_parts`, `lineage_key`, and `lineage_version=1`. Admission atomically
allocates one monotonic `child_no` and inherits
`parent_court_code=main_court_code`. Summary/topic changes never reclassify this
lineage. Duplicate instance ids, active/unconsumed write claims, dispatch
attempts, wrong task/epoch/dispatch, invalid worktree proof, or a different
repository common-dir fail closed; stale structured results are quarantined
without advancing the office instance.

Lifecycle event ids are independently generated per append, so multiple legal
reports from the same instance in the same timestamp second remain distinct.
The canonical JSON CLI returns `court.office.cli.v1` for success and every
failure class. Malformed JSON, missing arguments, unknown office subcommands,
and business rejection use stable `error_code` values, exit status 2, and no
argparse usage leakage.

Write/read scopes accept repository-relative canonical paths only and persist a
case-folded `/`-separated key. Equal, ancestor, and descendant writer claims
conflict. Worktree proof is re-derived through read-only Git commands from an
existing worktree top/common-dir/branch/HEAD; asserted repo/worktree ids and
fingerprints must match. The focused lifecycle checker sets synthetic runtime
and shared-Shiguan roots before importing the runtime and proves that no real
pending root is touched.

## P00 Dispatch Context Economy Wiring

Production `agent-admit` and generic `office admit` require one current
`court.semantic.dispatch_context_packet.v1`, one active task/wave-bound budget
pool, and explicit result/tool-output modes. The normal packet is measured from
its canonical JSON bytes, remains at or below 2,048 bytes without padding, uses
`fork_context=none|minimal`, `bounded_structured_receipt`, and aggregate or
pointer tool output. Full context is rejected unless both the packet budget
override and the current user/Taizi override source are explicit and agree.

The packet and budget pool remain transient inputs. Admission persists their
canonical hashes, the current semantic receipt id/hash, and the context-economy
receipt hash/decision in the admission, each selected office binding, and the
admission event. Start must resubmit the packet and pool, revalidate them against
the still-current semantic receipt/capsule, and exactly match the admitted
hashes before an instance or event is written. The same hashes then accompany
the instance and lifecycle events for both `child_agent` and
`worktree_thread`.

Missing or stale packets, a second capsule field, implicit full context,
over-budget packets, missing/stale budget pools, unbounded result/tool-output
modes, or start-time hash drift fail before task/event bytes change. The older
`dispatch_message_budget` remains only the outer final-message measurement; it
does not authorize context and never pads the packet to its floor or quantum.
