---
name: decretum-matrix
description: Decretum Matrix（诏令矩阵） routes capabilities and agents through the Codex/Hermes 三省六部 hierarchy. Use when dispatching /court or $decretum-matrix work under approval/autonomous/super authority, or when starting the separate superCC runtime; it gates dispatch with P00, loads references progressively, and returns court-status receipts.
license: AGPL-3.0
metadata:
  version: beta1.0.7
  author: RowlandL
---

# Decretum Matrix（诏令矩阵）

## P00 Highest-Priority Semantic Dispatch And Resume Contract

`P00_HIGHEST_PRIORITY=REQUIRED`. Before dispatch/resume/handoff, bind the existing `court.semantic.invariant_capsule.v1`, semantic receipt, authority/plan pointers, and `plan_cursor`; require `semantic_epoch == charter_revision`. Capsule and packet are each at most 2,048 UTF-8 bytes.

- New work carries exact ids, bounded scope/write set, receipt/authority pointers, and `fork_turns=none`. Never send full transcript/file/diff/agent list by default.
- `child_agent` and `worktree_thread` share capsule, receipt, hierarchy, role context, and bounded trace; neither creates a second authority.
- Reuse compatible live instances; keep in-flight work until completion/recall. Do not reuse near 80% context, unrelated next task, or large-scale parallel where fresh is safe. Full context needs user/太子 override and never changes hierarchy, safety, or write authority.
- `task_point_projection=POST_MIGRATION_DURABLE_PROJECTION_ONLY`: Shiguan may retain a durable projection after migration, but it is not the inline runtime authority.

## Unified Dynamic Dispatch Semantics

1. 官署按职责、依赖、风险和证据价值动态分配，不为填满容量而派生。
2. 正常 whole-tree 上限为 16（含 root），`max_depth=4`；只有最新用户明确指定大于 16 的数量或 `unlimited/解限` 才可提高 ceiling，且预算、资源压力、层级、写集、preload、trace 门禁仍然有效。
3. `execution_authority`=`approval|autonomous|super`；`behavior`=`serial|parallel`。serial 只禁物理 child 并发；官署责任与 `serial_inline` 证据仍保留。
4. `super并行` 仅为 `authority=super, behavior=parallel, parallel_topology=native`；native 与 superCC 入口互斥且不探测、切换或回退。
5. Production ordinary routing is V2 or `serial`; V2 hides model-reserved override fields. 子 agente 继承主线程 model/effort，除非 fresh-session worker 有精确 host proof。
6. 开朝、自检、复核或状态类任务先判定目标是“官署履职回奏”还是“机器事实核验”。需要官署回奏时，主线是按层级形成真实 host-native spawn/reuse/wake 或明确 `serial_inline` 责任；CLI/script 只是对应官署在职责内调用的工具，不能替代官署履职、派遣证据或回奏。

开朝三权：最新消息未明选 `approval|autonomous|super` 时先问三权，并以“权力 + 解释”的可选项呈现：`approval（审批/默认只读）：只读勘验，执行/写入/联网/安装前上奏`、`autonomous（自主/范围内实施）：按用户给定边界自主办理，越界再问`、`super（超级执行/范围内连续推进）：范围内连续推进，高风险或越旨时上奏`。随后单独呈现行为选择：`serial（串行）：不物理并发，保留官署责任链与 serial_inline 证据`、`parallel（并行）：按层级真实 spawn/reuse/wake`。每个选项独立成行，以便 Codex/Claude/Hermes 用方向键或鼠标提交；不从旧会话、史馆/记忆、sandbox、prompt 或安装意图继承。权力≠运行方式；六部直属尚书。

## Pinned Initial Court Anchors

- 最新旨意优先。独立解析 `authority`、`behavior`、`runtime`；新会话或边界变化未明选三权时必须先问，记忆/旧会话/运行权限不得代选。
- 固定层级：用户 -> 太子 -> 三省；尚书 -> 六部；六部 -> 工坊/工匠。UI 可平铺，但 receipt/奏报须标记六部为 Shangshu child agents；direct-superior 违规隔离。
- 普通开朝先做语义规划和正确上行/差遣路径。官署履职下一步应是宿主原生 spawn/reuse/wake 或说明原因的 `serial_inline`；`agent-admit` 只在具体宿主投递或 mutation 前作最终门禁。
- 普通官署履职的正确开局是：三权已明 -> 三省定性 -> 按层级 host-native spawn/reuse/wake，或在宿主不能派遣时明确 `serial_inline` 责任与原因。父线程只读取当前行为卷；被派官署按自己的职责与当前任务需要读取相应材料并回奏。
- 能力 registry 只在确需选 skill/MCP/CLI/script 时读取；闲聊、直接回答和无需能力检索的规划不运行 registry 脚本。
- 默认治理实现是 `three-departments-six-ministries`；参考实现不得改变 runtime、证据、权限、直接上级或史馆权威。
- 治理实现清单锚点为 `references/manifests/governance-implementations.v1.json`；源码文档契约由 `scripts/check_governance_framework.py` 检查，检查通过本身不构成 VERIFIED_CAPABILITY。
- 共享史馆在受保护 `.agents` / shared Shiguan 边界。安装默认只投影 `.agents` 与 current-tool；外部工具、发布、推送须最新明确授权。
- 结诏须经门下复核；编号、谱系和作业 AI 只逐字复制统一 CLI `shiguan archive-checkpoint` 的 `payload.closeout_identity`，模型不得分配。MCP 不生成第二套编号；它只能读取同一公共 API 或 dry-run 边界。

## Overview

本 skill 是三省六部语义路由器。用户侧默认简体中文；路径、命令、API、字段和代码契约保持原文。官署名是责任/证据契约，未履职时标记 `NOT_APPLICABLE`、`runtime_degraded` 或 `authority_blocked`。

加载目标是路径清晰、按场景一次走对。普通入口=本文件+当前行为卷；只有实际承担官署职责时再读本角色 profile/dossier，能力检索、正式差遣、结诏、superCC、安装和发布各自在触发后按表加载。禁全量 references、无关官署 profile、pending/private 正文；入口守 `<=20 KiB`。

## Loading Procedure (effective on load; binding for blank Agents)

This file is the load entry and hard-gate map. It is not distributed with any external user-level global memory. Follow the steps below so a blank Agent or a fresh reinstall loads correctly on first attempt:

1. **Trigger load**: Load `SKILL.md` via the host Skill mechanism (compact entry, ≤20 KiB). Do not treat the 67–80 KiB `references/*.md` as the entry.
2. **Pass top hard gates**: Satisfy the `P00` contract and `Common Hard Gates` first. If the latest message does not explicitly select `approval|autonomous|super`, **ask first and stop**; do not let memory / prior session / runtime permission choose for the user (constraint: `Pinned Initial Court Anchors`).
3. **Authority × behavior**: The three authorities are orthogonal to behavior; `super并行` = authority=super, behavior=parallel, runtime=native. When authority is unselected, present options independently per `Unified Dynamic Dispatch Semantics`.
4. **Progressive reference loading**: Read only the governing volume for the active behavior per `Progressive Loading Map`; full-volume load is forbidden. For large files use segmented reads or the on-disk copy; do not claim "read in full" while only a preview was taken.
5. **Tool-layer triad**:
   - **CLI**: `scripts/court_cli.py` (thin dispatcher → `court_cli_registry.py`) performs machine operations; output schema `decretum.cli.result.v1`, supports `--format json`; groups `court/office/shiguan/supercc/install/release/check`. Examples: `court status`, `shiguan archive-checkpoint`, `court open --fast --request-file <request.json>`. `bin/decretum-matrix.py` is a release launcher (requires a release ZIP), not the daily CLI. The maintenance aliases `doctor`, `debug`, and `fix update|migrate|rollback` use the same registry; `doctor`/`debug` are read-only, and `fix` plans by default and requires explicit `--apply` for writes.
   - **Agent / host dispatch**: Real sub-office spawn/reuse/wake (三省 and 六部 are all sub-offices, genuinely host-native derivable); `court open --fast` is only a machine preflight, not a substitute for real dispatch evidence.
   - **Reference markdown**: Semantic contract, load on demand.
6. **Dispatch hierarchy**: `太子 (main-thread router, not dispatchable) → 三省 (L1: 中书/门下/尚书) → 六部 (L2: 吏/户/礼/兵/刑/工, selected by 尚书省) → 工坊/工匠`. 中书/门下 are peer review offices and do not take over 六部 dispatch. Before a real host spawn, run `agent-admit` machine admission immediately; packets/admission checks alone are not spawn evidence.
7. **Shared Shiguan index (built at install)**: runtime root resolved by `scripts/shiguan_paths.py`, default `%USERPROFILE%\.agents\court-shiguan\decretum-matrix\references`; recall via `scripts/query_shiguan_index.py`, heavy rebuild via `rebuild_shiguan_index.py`; does not replace this file.
8. **Closeout**: Pass 门下 review; copy `payload.closeout_identity` from `shiguan archive-checkpoint` verbatim; without a valid archive receipt, do not self-assign an id (see `Closeout Skeleton`).

### Public Transport Contract

The unified CLI and the local MCP facade are **peer transports**, not a chain.
Both use the read-only functions in `scripts/court_public_api.py` for the
allowlisted projections; MCP must never spawn `court_cli.py` or parse CLI
stdout. The CLI remains the human/automation surface, while MCP remains the
structured host surface. They share runtime data and receipt rules, but neither
transport becomes the other's authority.

Codex lifecycle hooks are an optional advisory projection of this same
contract. A loaded `.codex-plugin` may surface session context and remind the
agent to use `mcp__decretum_matrix`; hooks must never write the court ledger,
memory, MCP configuration, Git configuration, or closeout receipts. The
absence of a hook process is a configuration gap, not evidence that the court
runtime or MCP transport is authoritative by itself.

MCP currently replaces only the read-only CLI subset: status, command help,
Shiguan query, archive dry-run, and memory scan. Court/office mutations,
archive checkpoints, install/migration, release, and superCC actions remain
CLI/script workflows because they require authority-bound receipts, host-native
probes, rollback, or controlled writes. Never infer those write capabilities
from a successful MCP read-only probe.

This procedure is fixed in the skill body, independent of any external memory; it is inherited on load with no extra configuration.

## Progressive Loading Map

只读当前行为对应卷；行为修改、语义争议、审计、发布和最终再载入才读全部直接相关卷。

| Active behavior | Governing reference |
| --- | --- |
| 核心语义、最新旨意、规则归属 | [court-core-contract.md](references/court-core-contract.md) |
| 三权争议、边界变化、只读与服务细则 | [court-startup-authority.md](references/court-startup-authority.md) |
| superCC runtime/client/zellij+squad | [court-supercc-runtime-selection.md](references/court-supercc-runtime-selection.md) |
| Hermes Studio same-room super GL | [hermes-studio-super-gl.md](references/hermes-studio-super-gl.md) |
| 官署职责、澄清、差遣、上下级 | [court-offices-dispatch.md](references/court-offices-dispatch.md) |
| P00、状态机、递归 agente、预算/lease | [court-state-runtime-agents.md](references/court-state-runtime-agents.md) |
| Codex V2 schema、模型推荐/继承 | [court-office-model-routing.md](references/court-office-model-routing.md) |
| 官籍、skill/MCP/CLI 铨选 | [court-capability-registry.md](references/court-capability-registry.md) |
| 安装、Windows/Hermes/host 风险 | [court-host-platform-pitfalls.md](references/court-host-platform-pitfalls.md) |
| 史馆、pending、记忆裁定 | [court-shiguan-memory.md](references/court-shiguan-memory.md) |
| Hermes group-chat 调查与路由 | [hermes-studio-group-chat.md](references/hermes-studio-group-chat.md) |
| 门下复核、结诏、验证、包装 | [court-closeout-validation.md](references/court-closeout-validation.md) |

## Common Hard Gates

- Formal decree 先形成紧凑 charter：旨意、非目标、边界、动作、验收、证据、停止门禁、史馆策略。
- 非平凡 intake 使用 `court.request_understanding.v1` 评估目标、使用场景、关键要求和验收标准；<95 一次只问一个高影响问题并给 2–4 选项，>=95 简要复述后执行，不强行提问。
- 非平凡任务先经三省：中书拟旨/验收，门下封驳风险/隐私/漂移，尚书评估派遣/资源/回滚；再 `三省上奏`、`太子回奏`。缺失的高影响决定按 `太子上奏下一项问题：...` 一次只问一项。
- `approval` 只读，`autonomous` 范围内写入，`super` 范围内自动执行；三权均可 `serial`/`parallel`，均不授权破坏、泄密、付费、私密上传、公网暴露、未验证安装或无界树。
- `superCC` 是独立 startup/runtime，不是第四权；须最新旨意与 zellij+squad/client 证据，且与 native 只共享中性官署配置指针。
- `super GL` 仅在已确认 Hermes Studio group-chat room 时使用真实同房 `@profile` 回复；不模拟回复、不默认 `@all`、不无限催促。
- 显式只读边界禁止写任务文件、启动服务、队列 seen、索引重建、catalog 变更等状态突变，除非最新旨意逐项授权。
- 网络研究按证据需求；时效/外部/冷门/高风险/需引用事实应联网，除非权限禁止。
- skills/MCP/CLI/script 是工坊技艺，不自动成为官署；调用须绑定 office、目的、边界、风险、证据和停止条件。
- 脚本 receipt 只证明机器事实。官署响应、三省/六部回奏或联通自检必须有真实官署实例、宿主投递/接收证据或明确 `serial_inline` 降级理由；缺失时回奏 `runtime_degraded`/`PARTIAL`。
- 用户侧更新与结诏使用太子/三省/尚书/六部/史馆责任主体；太子可转奏综合，不代替健康官署履职并声称其成果。

## Court Flow And Roles

```text
太子定性 -> 三省会审 -> 三省上奏 -> 太子回奏 -> 尚书倒推必要六部 -> 工坊办差 -> 尚书统合 -> 门下复核 -> 史馆实录
```

- 太子：唯一用户侧路由与综合面，只调三省。
- 中书省：拟旨、意图、研究、拆解、缺口和验收，不调六部。
- 门下省：风险、范围、隐私、成本、语义漂移、最终复核与史馆/记忆主审。
- 尚书省：派遣六部、串行共享突变、整合证据并向太子回奏。
- 吏/户/礼/兵/刑/工部：官籍；资源；文书；运行；安全/回滚；实现/验证。
- 史馆：三省共监、门下主审，记录证据、谱系与记忆裁定；不是六部。

Legal state flow:

```text
Pending -> Taizi -> ThreeDepartments -> ThreeDepartmentsPetition -> TaiziReply -> ShangshuDispatch -> SixMinistries -> Workshops -> MenxiaReview -> ShiguanRecorded -> Done
```

## Dispatch, Preload, And Runtime

- 官署绑定身份/上级、边界、P00、lease、证据和 stop。native/superCC 仅共享中性层级/profile pointer，各用 `office-dossiers`/`supercc-dossiers`。
- 普通 child 默认 `fork_turns=none`；兼容 live 三省/六部优先复用，但约 80% 上下文、任务无关或大规模并行可 fresh。`serial` 禁物理 spawn/reuse/wake/follow-up，不抹除职责；receipt 记 `serial_inline`、主体和原因。共享写入、安装、MCP 写入、破坏性动作和外部应用状态必须串行；宿主拒绝/限流/语义不连续时停 wave。
- 官署进入 `running` 前只需确认 role、direct_superior、model route/inheritance、任务边界和必要 dossier/profile 语义来源。文件变化或未读到非必要档案不得阻断任务；只有错角色、越级、越界、缺少当前任务必需语义或真实投递失败才降级或退回。
- `court open --fast` 只是三省规划完成后的可选机器预检，不是普通开朝前置，也不负责提问三权、选择六部或声称真实派遣。它只检查明确请求的角色和机器事实；真实 spawn/reuse/wake 仍以宿主回执为准。
- 仅 `runtime=superCC, entry_path=supercc` receipt 可加载 superCC；`entry_path=court` 不加载、探测或回显。Old Claude/Codex logs、裸 `squad` 或手写 pane 输入仅是 drift evidence。
- superCC 健康官署各司其职并守层级；turn-start、uniqueness、profile、task、wake/backoff、watchdog 或 closeout-silence 缺证即 degraded，不得无保留 DONE。

## Shiguan, Pending, And Memory

- 权威 runtime Shiguan root 由 `scripts/shiguan_paths.py` 解析，默认 `%USERPROFILE%\.agents\court-shiguan\decretum-matrix\references`；skill-local `references/` 只含 governing references 与 portable seeds。
- Formal decree 用统一 CLI `shiguan archive-checkpoint` 记录；其 v1 receipt 是用户侧编号/谱系唯一来源，且不覆盖最新旨意或 governing source。
- 史馆 GBrain 是智能查询/召回/整理候选层；`query_shiguan_index.py` 默认调用，基础 scorer 为 fallback；输出只 advisory、无执行权/写权，最新旨意优先。
- Git 联邦是源码树维护扩展；共享 hub 无 remote，原生记忆仓独立。GBrain 普通轻量/开朝不隐式跑重型 Git。
- pending/private 导入区仅允许 metadata governance。没有不可伪造 host capability 时，真实 pending/private bodies 必须保持 unopened、unmoved、undeleted、unmarked-seen；fixture authorization 不是 production authorization。
- Obsidian 是 preserve-only 管理面，不是权威。导入回到 pending，需三省会审/门下复核。
- 每个 decree 结束时裁定 `记忆裁定：WRITE | PROPOSE | SKIP | DEFERRED`。WRITE 需要最新边界与门下批准；不存 secrets、raw private logs、一次性输出、未验证推测或未经许可的个人数据。

## Closeout Skeleton

完成、暂停、阻塞、取消、handoff 或包装前，重载本文件及当前引用并经门下复核；结诏是客观终态行为，decree 进入终态即形成史馆实录与记忆裁定。轻量结诏（无写入、无外部状态变化的短回奏）说明请求、实际 host dispatch/reuse/wake 或 `serial_inline` 原因、官署回奏、未做持久写入，并写入紧凑 archive checkpoint；不启动 Shiguan Web、Obsidian、GBrain、pending 队列或全量树。完整十四行 memorial、归属、runtime、package-ready 和安装门见 [court-closeout-validation.md](references/court-closeout-validation.md)；行名/顺序不得改。仅门下接受的当前报告可标记 `MenxiaReview`；最终交付始终为 `TaiziReply`。无有效 archive receipt 时不得发送十四行或自分配编号，改用 `partial_or_not_run`、`authority_blocked` 或 `handoff_or_pause` 并说明归档门。

## Validation And Packaging

安装/发布/包装的校验与硬门（安装时校验自删、sync_active_copies、package/release/portability gates、prune/备份/回滚）见 [validation-packaging.md](references/validation-packaging.md)。
最小本地结构验证命令：`python -B scripts/quick_validate.py .`。
