# Court Runtime Result And Recruitment Contract

This governing reference joins the accepted intake, runtime, result-presentation,
and bounded recruitment semantics for the purified R/C lane. It does not grant
execution authority beyond the active decree.

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

R5-RC only validates and binds an externally produced assessment envelope to the
current task, charter revision, charter digest, evidence digest, and assessment
digest. It preserves the source envelope, validates exact fields and gate/reason
consistency, and makes identical replay idempotent while rejecting conflicts.
It does not import, execute, inspect, reproduce, or claim acceptance of R4, and
it does not independently evaluate the outcome.

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

For a semantic-bound dispatch, admission, start, report, and finish all carry
the same current checkpoint binding. Completion accepts only a structured
`court.office.result.v1` envelope containing the task/epoch, charter and capsule
hashes, checkpoint, dispatch uid, attempt, office instance, agent/role,
hierarchy, worktree, write-set hash, status, summary, evidence, and produced
time. Missing envelopes fail closed. A stale or conflicting envelope is stored
only as bounded quarantine metadata plus payload hash and reason codes; it does
not advance the agent or task.

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
