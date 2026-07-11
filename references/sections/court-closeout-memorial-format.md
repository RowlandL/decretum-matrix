# Closeout Memorial Format

## Unified Dynamic Dispatch Semantics

1. 官署按任务职责、依赖和证据价值动态分配。
2. 实时容量与请求预算是运行门禁，不是模式固定人数；整棵 agent tree 受 max_threads=16（含根线程）和 max_depth=4 约束，未知容量、占用、终态节点保留数、回收状态或深度时 fail closed。
3. superCC 固定显性太子+三省，但这不限制尚书省非显性、真实派遣有用六部。
4. 普通 super并行不使用 superCC pane、office show delay、wake 或 closeout-silence；其普通 spawn 展示延时为 0。

This shard owns the detailed closeout memorial rules for
`court-closeout-validation.md`. Load it for final `/court` answers, Shiguan
complete records, `hard_memorial_gate`, `semantic_reload`, or `superCC` closeout.

Token policy:

- `metadata_precision`: keep the user-facing memorial to the fourteen stable labels.
- `body_reference_policy`: cite Shiguan anchors or Web URLs instead of pasting full records.
- `on_demand_loading`: load this shard only for final closeout/report formatting.

## Contents

- `## User-Facing Short Memorial`
- `## Complete Shiguan Memorial`
- `## Semantic Reload`
- `## Web Address Rules`
- `## Gate Outcomes`

## User-Facing Short Memorial

End `/court` work with a two-layer Chinese court memorial only for closeout states
such as DONE, DONE_WITH_CONCERNS, PAUSED, BLOCKED, CANCELED, REJECTED, or
HANDOFF. Do not use it for a pending one-by-one clarification question; that
stage uses `太子上奏下一项问题：...` and omits the closeout block.

The user-facing closeout must render these fourteen labels in this exact order,
with no omitted labels, renamed labels, or extra top-level fields:

```text
诏令编号：...
古制谱系：...
状态：...
作业AI：<source_agent_label from archive_checkpoint.py, e.g. Codex/Hermes/Claude Code/Agents>
旨意与边界：...
执行门禁：...
门下裁定：...
实际动作：...
验收证据：VERIFIED | PARTIAL | NOT_RUN；...
运行态与并行：...；用量=tokens/time/source 摘要（详细 `decree_usage_estimate` 与 `usage_source_breakdown` 入完整史馆）
史馆：Web local_url=<current ensure_shiguan_web.py local_url>；lan_urls=<current ensure_shiguan_web.py lan_urls>
余险：...
太子回奏：...
下一步：...
```

If a draft collapses fields into prose, omits `诏令编号` / `古制谱系` / `作业AI`,
moves `史馆` outside the fourteen-label projection, repeats the Shiguan code in
the `史馆` line instead of a usable Web address, or appends ad-hoc fields, 门下省
must mark `hard_memorial_gate: DRIFT_CORRECTED` and rewrite before 太子 sends the
final answer.

Every `结诏` is a snapshot closeout. It must carry a non-placeholder
`诏令编号` and `古制谱系` even when the work is paused, blocked, partially verified,
or not yet archived into a final Shiguan checkpoint. If a checkpoint has already
been written, use its `court_code` and `ancient_lineage` / `lineage_display`. If
the closeout is an intermediate snapshot, allocate a snapshot identifier and
ancient lineage before sending. Never write `未生成`, empty, `...`, `…`,
`pending_archive_assignment`, or `NOT_APPLICABLE` in these two lines.

`作业AI` is the runtime writer label from `archive_checkpoint.py`. The first
`诏令编号` line is the user-facing Shiguan record anchor. The `史馆` line must show
only the usable Shiguan Web address from `scripts/ensure_shiguan_web.py`
(`local_url` plus any `lan_urls`). If service state is unavailable or unknown,
include the ensure command, manual LAN server command, and static fallback path in
that same line. Displaying the Web address does not authorize public exposure,
tunneling, management writes, imports, token use, or admin operations.

## Complete Shiguan Memorial

The complete Shiguan record preserves the full evidence chain, 三省/六部 details,
service/agente state, token policy, decree usage accounting, and memory decision. The user-facing answer
still uses the fourteen-label short memorial; the complete record may be
represented to the user by its Shiguan anchor instead of being pasted in full.

```text
诏令编号：...
古制谱系：...（填当前 lineage_display/ancient_lineage；中途截照则填已分配的 snapshot lineage）
状态：...
作业AI：<source_agent_label from archive_checkpoint.py, e.g. Codex/Hermes/Claude Code/Agents>
旨意：...
非目标：...
语义契约：任务边界、允许动作、禁止动作、验收标准、证据要求、停止门禁...
朝廷流程：太子定性 -> 三省会审 -> 三省上奏 -> 太子回奏 -> 尚书统六部 -> 工坊办差 -> 门下复核 -> 史馆实录
历史线索初判：...
诏令谱系：...（圣旨/诏书/敕书适用；否则 NOT_APPLICABLE）
执行行为类：...（据此分流文种，并进入史馆诏令行为谱系分面；否则 NOT_APPLICABLE）
格式依据：...（文种、用途、公开范围、套语/用宝/朱批依据；否则 NOT_APPLICABLE）
三省会审：中书拟旨；门下封驳；尚书评估分派
三省具体会审：...
三省上奏：...
太子回奏：...
太子整理回奏与细节追问：...
回问轮次与三省复议：本轮第 N 问；上一答复如何交三省复议；为何下一问仍必要；若超过两问，是否逐轮回奏。
执行门禁：APPROVED | REJECTED | NEEDS_CONTEXT
门下裁定：APPROVED | REJECTED | APPROVED_WITH_CAVEATS
尚书分派：...
六部并行办差：...
门下复核：...
验收证据：VERIFIED | PARTIAL | NOT_RUN；证据或未运行原因...
令牌优化：PASSED | PARTIAL | FAILED | authority_blocked；元数据精准、正文精简引用、按需加载裁定...
用量估算：decree_usage_estimate；开朝 token/time 估算、假设、模式、预期官署/subagent、证据路径；这是开朝门禁行为，不是附属官署。
用量结算：usage_actuals / usage_rollup / usage_source_breakdown / token_usage_precision / token_usage_note / wall_clock_actual / worker_elapsed_sum；只在 provider/runtime/agent 证据存在时标 provider_reported，估算与缺失必须明示。
运行态限制：none | runtime_degraded | authority_blocked；缺失能力、授权门禁与安全降级...
语义再载入：NOT_APPLICABLE | RELOADED | DRIFT_CORRECTED | FAILED；重载章节与门下复核结果...
刚性奏报门禁：PASSED | DRIFT_CORRECTED | FAILED；缺失字段或修正结果...
史馆实录：...
agente清理：开局...；收尾...
史馆图谱服务：RUNNING | REUSED | STARTED | NOT_STARTED | CHECK_ONLY | FAILED，URL/原因/备用命令；NOT_STARTED=最新旨意禁止启动服务，CHECK_ONLY=运行时/宿主限制只能探测...
史馆图谱：<ensure_shiguan_web.py 报告的实际 URL；同机 local_url 通常为 http://127.0.0.1:8765/，局域网设备使用 lan_urls> （若服务未启动：python -B scripts/serve_shiguan_tree.py --host 0.0.0.0 --port 8765；静态入口：web/shiguan-tree/index.html）
史馆导入队列：NONE | PENDING | FAILED；待处理数/新增数/token 估算/队列路径/是否已询问处理...
Codex YOLO 自启任务：TASK_EXISTS | MISSING | GENERATED_REVIEW_TASK | REGISTRATION_REFUSED | REGISTERED | FAILED；任务名/草案/日志/撤销命令/拒绝原因...
记忆裁定：WRITE | PROPOSE | SKIP | DEFERRED
余险：...
下一步：...
```

Final `/court` memorials and intermediate snapshot closeouts must autonomously
show `诏令编号` and `古制谱系`. If no checkpoint was written in the current work,
allocate a snapshot code and lineage before sending; never mark either field
`未生成`.

Before sending, compare the response against the Long Conversation Drift Guard.
If there is a conflict, the guard wins over shorter Shiguan wording or ad-hoc
task prose.
