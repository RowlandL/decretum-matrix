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

Use each interface when needed. Prefer MCP; CLI fallback if unavailable.
Check domain success; help is discovery, not functional proof.

| Operation | Required interface |
| --- | --- |
| Intake | CLI `court intake-template --charter <exact-charter>`; MCP `court.intake_validate` |
| Capsule/context/plan validation | MCP `court.capsule_validate`, `court.semantic_context_validate`, `court.dispatch_plan_validate` respectively |
| State/semantic mutation | Existing receipt-bound CLI |
| Case/plan continuity | CLI `court plan`; MCP `court.workflow_status` |
| Admit and deliver | CLI `agent-admit`, then host-native spawn/reuse/wake |
| Relevant state/history | MCP `court.status`, `shiguan.query` or `shiguan.entries_query` |
| Closeout | MCP `court.closeout_checklist`, Menxia review, CLI `shiguan archive-runtime-task --task-id <id>` |

## Operational sequence

Resolve authority/behavior from the user; ask if missing. Reuse the current task.

Use the installed `decretum-matrix` CLI, not internal Python entry scripts.
For a new standard case, pass `--session-id <host-session-id> --authority
<selected-authority> --behavior <selected-behavior>` to `court create` along
with its intake fields. It issues/reuses the official number and opens the
existing decree transaction. `court.workflow_status` shows the shared identity.

Before drafting, the case is explicitly BOOTSTRAP_UNPLANNED. After real office
reports, use `court plan template` / `submit` for Zhongshu's actual document,
then separate Menxia/Shangshu `review`. Plan changes invalidate reviews.
Ministries require a reviewed plan and TaiziReply. `plan show` resolves the
stored document; capsules cannot replace it.

Use public templates/schemas, not source inspection or guessed hashes. Generate context
after state changes with `court semantic-context-template --task-id <id>`;
validate its `payload.context`. For checkpoint/verify, pass the corresponding
required `--trigger checkpoint` / `--trigger verify`, task id, context, actor
and evidence. `before_dispatch` is invalid.

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

Three Departments are separate planning, review and coordination offices;
Shangshu alone selects distinct ministries by duty. Real replies are required.
Latest history: `shiguan.query(terms=[], limit=1)`, only when requested.
Use archive-runtime-task for formal closeout to carry the original case binding.

Write UTF-8 JSON without BOM. Fresh acceptance uses CLI/MCP and no old memory.
