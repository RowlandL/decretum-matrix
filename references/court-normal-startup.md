# Normal court startup

## Required reads by phase

| Phase | Read in full once | Defer |
| --- | --- | --- |
| Root intake | Exact installed SKILL.md and this guide | Capability index, other reference volumes, source/install checks |
| Own office duty | Own `agents/office-dossiers/<role>/AGENTS.md`, `agents/standing-officials/<role>.toml`, current bounded packet | Other offices' materials |
| Specialized operation/dispute | The relevant volume in SKILL.md's map | Unrelated volumes |
| Closeout | Closeout volume and required memorial shard, Menxia result, archive receipt | Closeout reads/services during startup |

SKILL + guide + own materials + metadata must fit 20 KiB. Reuse unchanged reads.

## Required tool routes

Validate intake/capsule/context/dispatch plan with MCP `court.intake_validate`,
`court.capsule_validate`, `court.semantic_context_validate`,
`court.dispatch_plan_validate`. Query state/case/history through `court.status`,
`court.workflow_status`, `shiguan.query` / `shiguan.entries_query`. At closeout
use `court.closeout_checklist`. Use CLI fallback if MCP is unavailable.
Mutation uses CLI; delivery uses the host. Check domain success, not just help.

## Operational sequence

Resolve authority/behavior from the user; ask if missing. Reuse the current task.

Use `decretum-matrix`. If Windows PATH is stale, resolve `npm prefix -g` and
invoke that prefix's `decretum-matrix.cmd`; never substitute internal Python.
Use relative write_set paths from the worktree, e.g. `.codex/tmp/<task-id>`;
absolute/traversal paths fail before standard allocation. `--worktree .` in a
template resolves from current cwd; relative worktree in a request file resolves
from that file. Documents resolve from the skill root. Do not hardcode a drive
or username. Resolved host evidence may carry absolute paths with its basis.
For a new standard case, pass `--session-id <host-session-id> --authority
<selected-authority> --behavior <selected-behavior>` to `court create` along
with its intake fields. It issues/reuses the official number and opens the
existing decree transaction. Transition to Taizi then ThreeDepartments before
semantic checkpoint/verify, open preparation and admission.

Before drafting, the case is explicitly BOOTSTRAP_UNPLANNED. After real office
reports, use `court plan template` / `submit` for Zhongshu's actual document,
then separate Menxia/Shangshu `review`. Plan changes invalidate reviews.
Ministries require a reviewed plan and TaiziReply. `plan show` resolves the
stored document; capsules cannot replace it.

Generate context after state changes with `court semantic-context-template`;
validate payload.context. Checkpoint/verify require matching `--trigger
checkpoint` / `--trigger verify`, task id, context, actor and evidence.

Use the request-template command from `court open` / MCP help with actual
authority, offices and host facts; submit `--request-file <request.json>`.
After admission, run `office native-request --request-file <selector.json>`
using schema `court.office.native_request.v1`, task_id, wave_id and instance_id.
Execute the exact returned host_invocation, then call `office native-capture`
with the same selector (schema `court.office.native_capture.v1`). Submit its
office_request through the returned office_command. Receipts come from the
current host trace; never supply invented host IDs or results.
Preparation never proves office duty; deliver the original admission once.
Bounded children perform their assigned duty, without repeating root intake.

Record real office start/preload-ack/report/finish via CLI before plan/review.
Only Shangshu selects ministries. `ok` replies do not prove this runtime chain.
For latest history use `shiguan.query(terms=[], limit=1)`.
Formal closeout uses archive-runtime-task and its producer_receipt.closeout_identity;
standalone archive-checkpoint cannot complete a standard runtime case.

Write UTF-8 JSON without BOM. Fresh acceptance uses CLI/MCP and no old memory.
