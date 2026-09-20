# Decretum Matrix court open

## Required reads by phase

| Phase | Read in full once | Defer |
| --- | --- | --- |
| Intake | Installed SKILL.md, this guide | Index, other volumes, source checks |
| Own duty | Own `agents/office-dossiers/<role>/AGENTS.md`, `agents/standing-officials/<role>.toml`, bounded packet | Other offices |
| Operation/dispute | Relevant SKILL.md volume | Unrelated volumes |
| Closeout | Closeout volume, memorial shard, Menxia result, archive receipt | Startup closeout services |

Reuse unchanged reads; apply the entry/preload budget in SKILL.md.

Preload/ack use installation declarations; never rehash.
Fresh acceptance reads no past tasks/memory. No source scans or installation
checks at startup; load help only for the next command.

## Required tool routes

Validate intake/capsule/context/plan via MCP `court.intake_validate`,
`court.capsule_validate`, `court.semantic_context_validate`,
`court.dispatch_plan_validate`. If status is needed, use
`court.status(view="compact",limit=1)` or `court status --view compact --limit 1`.
For a known task use `court.workflow_status`; query history only when requested.
Closeout uses `court.closeout_checklist`. Use CLI when MCP is unavailable.
Mutation uses CLI; delivery uses the host. Check domain success, not just help.

## Operational sequence

Use current task and user authority/behavior; ask if absent.

Use `decretum-matrix`; stale PATH uses `npm prefix -g`'s `decretum-matrix.cmd`,
never internal Python. write_set is worktree-relative; absolute/traversal fails.
Template `--worktree .` is cwd-relative, request-file worktree file-relative,
documents skill-relative. Host evidence may record resolved paths and bases.
Within a task, keep parent `shangshu/` and child `ministries/<role>/` writes
disjoint; directory ownership includes descendants. Read scope is separate.
New cases use `court create --session-id <host-id> --authority <authority>
--behavior <behavior>` plus intake fields to issue/reuse the official number
and decree transaction. Enter Taizi then ThreeDepartments before semantic
checkpoint/verify, open preparation and admission.

After real reports, use `court plan template` / `submit` for Zhongshu's document,
then Menxia/Shangshu each `review`.
Changes invalidate reviews. Ministries require reviewed plan and TaiziReply.
`plan show` resolves the document; capsules cannot replace it.
For `plan review`, fill `template.review.producer`, role and decision. Submit the
`review` object or whole template; the submitted plan reference is prefilled.

Generate context after state changes with `court semantic-context-template`;
validate payload.context. Checkpoint/verify require matching `--trigger
checkpoint` / `--trigger verify`, task id, context, actor and evidence.

Use `court open` / MCP request-template with actual authority/offices/host
facts; submit `--request-file <request.json>`.
Submit admission JSON with `office admit`, then `office native-request --request-file <selector.json>`
using schema `court.office.native_request.v1`, task_id, wave_id and instance_id.
Execute the exact returned host_invocation, then call `office native-capture`
with the same selector (schema `court.office.native_capture.v1`). Submit its
office_request through the returned office_command. Receipts come from the
current host trace; never supply invented host IDs or results.
Opaque messages use call/activity/child metadata; capture proves spawn only.
Child reads installed SKILL, then profile/dossier, emits `child_acceptance` as
JSON-only commentary and waits for superior CLI ack before business tools.
The superior saves `office start`'s `preload_ack_request` and submits it with
`office preload-ack --request-file <ack.json>` after the child acceptance arrives.
On CLI success, the direct superior sends the acceptance to the child, which
then begins business work; the CLI does not notify the waiting child.
This request uses `office_instance.preload_manifest` identity values: keep
`court_skill_path`, `profile_source`, and `dossier_path` skill-relative, rather
than copying the absolute read locations from `native_request.role_ack`.
Public request `loaded_skills` is a comma/semicolon-separated string (normally
`"decretum-matrix"`); the internal validated ack uses an array. Neither object
replaces the child's `child_acceptance`. The generated request is a template,
not proof: current child trace and the matching request ID remain required.
Ack echoes the supplied request ID. Missing evidence stays retryable PENDING;
parent declarations and saved-trace replays cannot prove fresh acceptance.
Deliver admission once. Children perform assigned duty without root intake.

Record real office lifecycle via CLI before plan/review; only Shangshu dispatches
ministries. For closeout load the SKILL phase reference and use archive-runtime-task.

Write UTF-8 JSON without BOM. Fresh acceptance uses CLI/MCP and no old memory.
