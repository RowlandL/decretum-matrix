# Court Context Compression Survival

This shard owns the rules that keep 三省六部 behavior intact across repeated
context compaction, resume, interruption, and semantic compression. Load it when
a court task survives one or more compactions, when a summary replaces the live
conversation, or when a reply risks losing court format.

Token policy:

- `metadata_precision`: preserve hashes, short anchors, active plan id, active
  skill name, reference paths, court code, and reply family.
- `body_reference_policy`: store exact short anchors plus hashes instead of
  copying the full conversation or private Shiguan bodies.
- `on_demand_loading`: reload `SKILL.md` and this shard after
  compaction/resume; reload the selected response family before a substantial
  reply; load the closeout memorial shard only when the closeout label hash is
  missing/mismatched or a final closeout repair requires the owning source.

## Contents

- `## Compression Survival Capsule`
- `## Multi-Cycle Restore Procedure`
- `## Drift Repair`
- `## Fixture Lint`

## Compression Survival Capsule

Every non-trivial court task that may cross context compaction must maintain a
small capsule. The capsule is not a prose summary; it is the authority-preserving
index for restoring the task:

```text
compression_survival_gate: PASSED | PARTIAL | FAILED
cycle_count: <integer, incremented after each compaction/resume>
original_decree_anchor: <short exact user-wording anchor>
original_decree_sha256: <sha256 of the preserved original decree text when available>
plan_anchor: <short exact plan wording or plan id>
plan_sha256: <sha256 of the active plan text when available>
active_skill: court-capability-router
required_reload: SKILL.md; references/sections/court-context-compression-survival.md; references/sections/court-response-fewshot-format.md
court_flow_anchor: 太子定性 -> 三省会审 -> 三省上奏 -> 太子回奏 -> 尚书统六部 -> 工坊办差 -> 门下复核 -> 史馆实录
reply_family: <selected family from court-response-fewshot-format.md>
reply_voice_contract: court_office_self_reference
reply_voice_markers: 作业AI：; 门下裁定：; 太子回奏：
forbidden_reply_voice: 作为AI; 我是AI; 作为一个AI; 助手回复; assistant; 我会; 我已经; 我将; 我认为; I will; I have; I think
closeout_identifier_contract: archive_checkpoint_receipt_required_for_implementation_closeout
archive_receipt: court.shiguan_archive_checkpoint_receipt.v1; receipt_id; receipt_sha256; archive_sha256; court_code; lineage_display
forbidden_closeout_identifier_values: empty; ...; …; 未生成; pending_archive_assignment; NOT_APPLICABLE
closeout_format: fourteen-label 结诏
closeout_label_hash: 2389ce4aa9b5b9b4a71a5ab5a1b0be78a843f07b5cfd7c4fcd998fd9b106cc41
closeout_shard_on_demand: references/sections/court-closeout-memorial-format.md only if label hash/labels are missing, mismatched, or final closeout repair needs source text
token_policy: metadata_precision -> body_reference_policy -> on_demand_loading
```

`original_decree_anchor` and `plan_anchor` must not be paraphrased after the
first capsule write. Later summaries may compress surrounding rationale, but
they must carry these anchors unchanged or report `compression_survival_gate:
FAILED` before proceeding.

## Multi-Cycle Restore Procedure

After each compaction or resume:

1. 太子 reloads `SKILL.md` first and confirms the task still belongs to
   `court-capability-router` when the active work is 三省六部, /court, 官署,
   reply-format, Shiguan, capability routing, or court closeout work.
2. 中书省 reconstructs the semantic charter from the newest user decree plus the
   immutable anchors, without rewriting the user's original plan into a new
   objective.
3. 门下省 compares the restored plan against `plan_sha256` or the exact
   `plan_anchor`. If the plan changed without a newer user decree, mark
   `DRIFT_CORRECTED` and restore the prior plan.
4. 尚书省 resumes execution only after the active skill, authority class,
   allowed actions, stop conditions, and validation evidence are still present.
5. Before any substantial reply, select the smallest response family from
   `court-response-fewshot-format.md`. Final closeout must render the fourteen
   labels preserved in the capsule and validated by `closeout_label_hash`.
   Load `court-closeout-memorial-format.md` only if the capsule lacks those
   fields, the hash mismatches, or closeout-specific repair needs the source.
   An implementation closeout additionally requires the current unified CLI
   archive receipt; compaction may preserve its exact fields and hashes but may
   not recreate or paraphrase them.

## Drift Repair

The following are hard drift conditions:

- the restored summary drops `court-capability-router` or 三省六部 while the task
  is still a court task;
- the original user wording or approved plan is paraphrased into a different
  goal without a newer decree;
- the final answer loses 官署自称, uses generic assistant voice, or omits the
  selected response family;
- the restored reply preview lacks `reply_voice_markers` or contains
  `forbidden_reply_voice`;
- any `结诏` lacks a valid `court.shiguan_archive_checkpoint_receipt.v1`, or its
  `诏令编号` / `古制谱系` differ from receipt `court_code` / `lineage_display`;
- the closeout becomes prose summary instead of the fourteen-label `结诏`;
- the closeout shard is treated as a mandatory full-body reload instead of an
  on-demand source behind `closeout_label_hash`;
- token compression keeps long bodies but drops anchors, hashes, paths, or
  validation evidence.

Repair by reloading the capsule and governing shard, restoring the anchor/plan,
checking `closeout_label_hash`, and rewriting the reply before sending. Load the
closeout memorial shard only when the capsule cannot prove the label contract.
If the missing source cannot be recovered, report `compression_survival_gate=FAILED`
and ask one highest-impact recovery question.

## Fixture Lint

`scripts/check_context_compression_survival.py` validates the synthetic fixture
`references/fixtures/context-compression-survival.json`. The lint gate verifies
multi-cycle preservation of original decree anchors, plan anchors, mandatory
skill reload, response family selection, `reply_voice_contract`, fourteen-label
closeout fields, archive-receipt-bound `诏令编号` / `古制谱系`,
`closeout_label_hash`, on-demand closeout source policy, expected negative-case
errors, and the three-level token policy.
