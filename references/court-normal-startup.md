# Normal court startup

## Required reads by phase

| Phase | Read in full once | Defer |
| --- | --- | --- |
| Intake | Installed SKILL.md, this guide | Index, other volumes, source checks |
| Own duty | Own `agents/office-dossiers/<role>/AGENTS.md`, `agents/standing-officials/<role>.toml`, bounded packet | Other offices |
| Operation/dispute | Relevant SKILL.md volume | Unrelated volumes |
| Closeout | Closeout volume, memorial shard, Menxia result, archive receipt | Startup closeout services |

SKILL + guide + own materials + metadata must fit 20 KiB. Reuse unchanged reads.

Read `references/manifests/installed-preload-identity.v1.json` declarations for
preload/ack; never rehash files. Missing pins require installation update.

## Required tool routes

Validate intake/capsule/context/plan via MCP `court.intake_validate`,
`court.capsule_validate`, `court.semantic_context_validate`,
`court.dispatch_plan_validate`. Query state/case/history through `court.status`,
`court.workflow_status`, `shiguan.query` / `shiguan.entries_query`. At closeout
use `court.closeout_checklist`. Use CLI fallback if MCP is unavailable.
Mutation uses CLI; delivery uses the host. Check domain success, not just help.

## Operational sequence

Resolve user authority/behavior; ask if missing. Reuse the current task.

Use `decretum-matrix`; stale PATH uses `npm prefix -g`'s `decretum-matrix.cmd`,
never internal Python. write_set is worktree-relative; absolute/traversal fails.
Template `--worktree .` is cwd-relative, request-file worktree file-relative,
documents skill-relative. Host evidence may record resolved paths and bases.
New cases use `court create --session-id <host-id> --authority <authority>
--behavior <behavior>` plus intake fields to issue/reuse the official number
and decree transaction. Enter Taizi then ThreeDepartments before semantic
checkpoint/verify, open preparation and admission.

Cases begin BOOTSTRAP_UNPLANNED. After real reports, use `court plan template`
/ `submit` for Zhongshu's document, then Menxia/Shangshu each `review`.
Changes invalidate reviews. Ministries require reviewed plan and TaiziReply.
`plan show` resolves the document; capsules cannot replace it.

Generate context after state changes with `court semantic-context-template`;
validate payload.context. Checkpoint/verify require matching `--trigger
checkpoint` / `--trigger verify`, task id, context, actor and evidence.

Use `court open` / MCP request-template with actual authority/offices/host
facts; submit `--request-file <request.json>`.
After admission, run `office native-request --request-file <selector.json>`
using schema `court.office.native_request.v1`, task_id, wave_id and instance_id.
Execute the exact returned host_invocation, then call `office native-capture`
with the same selector (schema `court.office.native_capture.v1`). Submit its
office_request through the returned office_command. Receipts come from the
current host trace; never supply invented host IDs or results.
Opaque messages use call/activity/child metadata; capture proves spawn only.
Child reads installed SKILL, then profile/dossier, emits `child_acceptance` as
JSON-only commentary and waits for superior CLI ack before business tools.
Ack echoes the supplied request ID. Missing evidence stays retryable PENDING;
parent declarations and saved-trace replays cannot prove fresh acceptance.
Deliver admission once. Children perform assigned duty without root intake.

Record real office start/preload-ack/report/finish via CLI before plan/review.
Only Shangshu selects ministries. `ok` replies do not prove this runtime chain.
For latest history use `shiguan.query(terms=[], limit=1)`.
Formal closeout uses archive-runtime-task and its producer_receipt.closeout_identity;
standalone archive-checkpoint cannot complete a standard runtime case.

Write UTF-8 JSON without BOM. Fresh acceptance uses CLI/MCP and no old memory.
