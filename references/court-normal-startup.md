# Decretum Matrix court open

## Reads

Read installed SKILL.md and this guide fully; then own
`agents/office-dossiers/<role>/AGENTS.md`,
`agents/standing-officials/<role>.toml` and bounded packet.
Reuse unchanged reads; load phase volumes on demand. Defer other offices/indexes
and closeout services. Closeout needs its volume, memorial shard, Menxia result
and archive receipt. Obey SKILL.md's preload budget.

Preload/ack use installation declarations; never rehash.
Fresh acceptance reads no past tasks/memory.
Startup: no source scans/install checks; next-command help only.

## Tools

Validate via MCP `court.intake_validate`, `court.capsule_validate`,
`court.semantic_context_validate`, `court.dispatch_plan_validate`.
Status: `court.status(view="compact",limit=1)`; known task: `court.workflow_status`.
History only on request; closeout: `court.closeout_checklist`.
CLI fallback for MCP; CLI mutates, host delivers. Require domain success.

## Flow

Bind current task, authority and behavior independently; ask if absent.
Use `decretum-matrix`; stale PATH uses `npm prefix -g`'s
`decretum-matrix.cmd`, never internal Python.
write_set is worktree-relative; absolute/traversal fails.
Keep parent/child writes disjoint, including descendants; separate read scope.

`court create` with `--session-id`, `--authority`, `--behavior` and intake
fields issues/reuses the official number and decree transaction.
Enter Taizi, then ThreeDepartments before checkpoint/verify, open or admit.
After real reports: Zhongshu `court plan template` / `submit`, then
Menxia/Shangshu `review`. Changes invalidate reviews; ministries need reviewed
plan and TaiziReply. `plan show` resolves it; no capsule substitute.

After changes: `court semantic-context-template`; validate payload.context.
Checkpoint/verify bind current task/context/actor/evidence; use
`--trigger checkpoint` / `--trigger verify`.

`court open` / MCP request-template uses actual authority/offices/host;
submit `--request-file`.
`office admit` precedes `office native-request`; execute the exact host_invocation,
then `office native-capture` and its returned office_command/office_request.
Use current host trace, never invented IDs/results. Opaque messages:
call/activity/child metadata; capture proves spawn only.
Child reads installed SKILL before profile/dossier; emits JSON-only commentary
`child_acceptance` and waits. Submit `office start`'s `preload_ack_request` via
`office preload-ack --request-file`. Direct superior must relay CLI success
before child business tools run; CLI does not notify children.
[Path/ACK details](sections/court-office-name-profile-skill-binding.md).
Echo the request ID. Missing evidence stays retryable PENDING;
parent claims/replays are not acceptance.
Deliver admission once; no child root intake.
Record CLI lifecycle before plan/review; only Shangshu dispatches ministries.
Closeout: `archive-runtime-task`.
Write UTF-8 JSON without BOM.
