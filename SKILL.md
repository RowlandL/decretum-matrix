---
name: decretum-matrix
description: Decretum Matrix（诏令矩阵） routes capabilities and agents through the Codex/Hermes 三省六部 hierarchy. Use when dispatching /court or $decretum-matrix work under approval/autonomous/super authority, or when starting the separate superCC runtime; it gates dispatch with P00, loads references progressively, and returns court-status receipts.
license: AGPL-3.0
metadata:
  version: beta1.1.0
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
6. 开朝、自检、复核或状态类任务先判官署履职回奏或机器事实；官署回奏须按层级 host-native spawn/reuse/wake 或 `serial_inline`，CLI/script 只辅助且不代替派遣或回奏。

开朝：未由最新消息明确选择 `approval|autonomous|super` 时，独立询问权力与 `serial|parallel`；不可从记忆、旧会话、sandbox、prompt 或安装意图继承。`approval` 默认只读，`autonomous` 范围内实施，`super` 范围内连续推进；`serial` 保留 `serial_inline`，`parallel` 按层级真实 spawn/reuse/wake。两组独立呈现；权力≠运行方式，六部直属尚书。

## Pinned Initial Court Anchors

- 最新旨意优先。独立解析 `authority`、`behavior`、`runtime`；新会话或边界变化未明选三权时必须先问，记忆/旧会话/运行权限不得代选。
- 固定层级：用户 -> 太子 -> 三省；尚书 -> 六部；六部 -> 工坊/工匠。UI 可平铺，但 receipt/奏报须标记六部为 Shangshu child agents；direct-superior 违规隔离。
- 普通开朝先做语义规划和上行/差遣路径；`agent-admit` 只在具体宿主投递或 mutation 前作最终门禁。
- 正确开局：三权已明 -> 太子受旨定性/结果章程 -> 中书拟旨/拆解、门下封驳、尚书可分派性评估 -> 三省上奏/太子回奏。`court semantic checkpoint/verify` 的 `VERIFIED/DISPATCHABLE` 只为 P00 语义门禁，不构成中书/门下/尚书履职或派遣证据；之后按层级 host-native spawn/reuse/wake；用户显式选择 `serial` 时可记录 `serial_inline`，否则仅宿主不能派遣时才记录该责任。父线程只读当前行为卷；被派官署按需读取材料并回奏。
- 能力 registry 只在确需选 skill/MCP/CLI/script 时读取；闲聊、直接回答和无需能力检索的规划不运行 registry 脚本。
- 默认治理实现是 `three-departments-six-ministries`；参考实现不得改变 runtime、证据、权限、直接上级或史馆权威。
- 治理实现清单锚点为 `references/manifests/governance-implementations.v1.json`；源码文档契约由 `scripts/check_governance_framework.py` 检查，检查通过本身不构成 VERIFIED_CAPABILITY。
- 共享史馆在受保护 `.agents` / shared Shiguan 边界。安装默认只投影 `.agents` 与 current-tool；外部工具、发布、推送须最新明确授权。
- 结诏须经门下复核；编号、谱系和作业 AI 只逐字复制统一 CLI `shiguan archive-checkpoint` 的 `payload.closeout_identity`，模型不得分配。MCP 不生成第二套编号；它只能读取同一公共 API 或 dry-run 边界。

## Overview

本 skill 默认用简体中文回奏；代码契约保持原文。官署履职状态为 `NOT_APPLICABLE`、`runtime_degraded` 或 `authority_blocked`。

普通入口只读本文件与当前行为卷，履职时再读当前 role profile/dossier。禁止全量 references、无关官署材料和 pending/private 正文；完整入口、当前 dossier/profile 与紧凑 metadata 合计须 `<=20 KiB`。

## Loading Procedure (effective on load; binding for blank Agents)

This memory-independent hard-gate entry binds blank and fresh installs:

1. **Trigger**: Load `SKILL.md` through the host Skill mechanism; entry, current dossier/profile, and compact metadata total `<=20 KiB`. Never use a large reference as entry.
2. **Hard gates**: Apply `P00` and `Common Hard Gates` first. Without latest-message `approval|autonomous|super`, ask and stop; memory, prior sessions, and runtime permission cannot select it.
3. **Authority × behavior**: They are independent; `super并行` means super + parallel + native. Present missing selections independently.
4. **References**: Load only the active `Progressive Loading Map` volume; a preview is not a full read.
5. **Evidence layers**: CLI (`scripts/court_cli.py` → `court_cli_registry.py`) is distinct from host spawn/reuse/wake and on-demand references. `court open --fast` only prepares; `agent-admit` precedes delivery/mutation and its receipt is not delivery.
6. **Hierarchy**: `太子 → 三省；尚书 → 六部；六部 → 工坊/工匠`. 中书/门下不调六部。
7. **Shiguan**: `shiguan_paths.py` resolves the shared root; `query_shiguan_index.py` is advisory.
8. **Closeout**: 门下复核后逐字复制 `shiguan archive-checkpoint` 的 `payload.closeout_identity`；无 receipt 不编号。

### Public Transport Contract

CLI and MCP share `scripts/court_public_api.py`; command surface follows [cli-command-surface.v1.json](references/manifests/cli-command-surface.v1.json). MCP never spawns `court_cli.py` or parses stdout. Lifecycle/Git hooks are withdrawn; `.codex-plugin` is metadata compatibility only. Mutations, archive, install/migration, release, and superCC remain receipt-bound CLI/script workflows.

## Progressive Loading Map

只读当前行为对应卷；行为修改、语义争议、审计、发布和最终再载入才读全部直接相关卷。

| Active behavior | Governing reference |
| --- | --- |
| 核心语义/最新旨意 | [court-core-contract.md](references/court-core-contract.md) |
| 三权/边界/只读 | [court-startup-authority.md](references/court-startup-authority.md) |
| superCC runtime | [court-supercc-runtime-selection.md](references/court-supercc-runtime-selection.md) |
| Hermes super GL | [hermes-studio-super-gl.md](references/hermes-studio-super-gl.md) |
| 官署职责/差遣 | [court-offices-dispatch.md](references/court-offices-dispatch.md) |
| P00/状态/预算 | [court-state-runtime-agents.md](references/court-state-runtime-agents.md) |
| Codex 模型路由 | [court-office-model-routing.md](references/court-office-model-routing.md) |
| 官籍/能力铨选 | [court-capability-registry.md](references/court-capability-registry.md) |
| 安装/host 风险 | [court-host-platform-pitfalls.md](references/court-host-platform-pitfalls.md) |
| 史馆/记忆 | [court-shiguan-memory.md](references/court-shiguan-memory.md) |
| Hermes group chat | [hermes-studio-group-chat.md](references/hermes-studio-group-chat.md) |
| 结诏/校验/包装 | [court-closeout-validation.md](references/court-closeout-validation.md) |

## Common Hard Gates

- Charter 绑定旨意、非目标、边界、动作、验收、证据、stop 与史馆策略。非平凡 intake 评估目标、使用场景、关键要求和验收标准；`court.request_understanding.v1` <95 时一次只问一个高影响问题并给 2–4 选项；>=95 简要复述后执行，不强行提问。
- 非平凡任务先经中书拟旨、门下封驳、尚书评估、三省上奏、太子回奏；六部只由尚书差遣。CLI/script receipt 只证机器事实，官署回奏须 delivery/reply 或 `serial_inline`。
- `approval` 只读；`autonomous` 范围内写；`super` 范围内连续执行。三权均不授权破坏、泄密、付费、私密上传、公网暴露、未验证安装或无界树。
- `superCC` 不是第四权，须最新旨意与 zellij+squad/client 证据；`super GL` 仅在已确认 room 用真实 `@profile`，不模拟、`@all` 或无限催促。
- 只读边界禁止写；时效/外部/冷门/高风险/需引用事实按需联网。skills/MCP/CLI/script 只是在 office 边界内办差的技艺。

## Court Flow And Roles

`太子定性 → 三省会审/上奏 → 太子回奏 → 尚书统合六部 → 工坊办差 → 门下复核 → 史馆实录`。太子只调三省；中书拟旨，门下封驳/终审，尚书统合六部；史馆记录证据且不是六部。

Legal state: `Pending → Taizi → ThreeDepartments → ThreeDepartmentsPetition → TaiziReply → ShangshuDispatch → SixMinistries → Workshops → MenxiaReview → ShiguanRecorded → Done`.

职责边界：太子受旨定性并建立结果章程，顶层拆解交中书；中书拟旨/拆解/考据/验收，门下封驳/终审，尚书统合资源并差遣六部。`court_runtime semantic checkpoint/verify` 只为 P00 门禁；官署回奏须 `agent-admit` 加 host-native 证据或显式 `serial_inline`，否则记为 `runtime_degraded`/`PARTIAL`，不得以语义 receipt 冒充。

## Dispatch, Preload, And Runtime

- 官署绑定 role/direct_superior、边界、P00、lease、必要 dossier/profile、证据和 stop；identity、scope、语义或 delivery 故障即退回。
- Child 默认 `fork_turns=none`，优先复用 context <80% 的相关 live instance；`serial` 禁物理 spawn/reuse/wake/follow-up 但保留 `serial_inline`。共享/外部写串行；拒绝、限流或语义漂移即停 wave。
- `court open --fast` 仅为三省规划后的 machine preflight，不证明派遣。只有 `runtime=superCC, entry_path=supercc` 可加载 superCC；普通 court 零加载，缺 identity/profile/task/wake/backoff/closeout-silence 证据即 degraded。

## Shiguan, Pending, And Memory

- `shiguan_paths.py` resolves the authority；`shiguan archive-checkpoint` v1 receipt 是唯一用户侧 id/lineage 源且不覆盖最新旨意。
- 史馆 GBrain 不取得当前任务执行权；其 query/index/Git/Obsidian 仅 advisory/preserve-only，普通 startup 不跑重型 Git。
- pending/private 只允许 metadata governance；未经不可伪造主机授权不得打开、移动、删除或标记正文，也不得保留 secrets、原始私密日志、瞬态输出、猜测或未获批个人数据。
- Closeout records `记忆裁定：WRITE | PROPOSE | SKIP | DEFERRED`; WRITE requires current scope and 门下 approval.

## Closeout Skeleton

终态前重载本文件/当前引用并经门下复核。轻量结诏记录请求、dispatch/reuse/wake 或 `serial_inline`、官署回奏、写入和 archive checkpoint，不启动无关服务/队列/全量树。十四行 memorial 与 package/install gate 见 [court-closeout-validation.md](references/court-closeout-validation.md)，顺序不变。仅门下接受者可标 `MenxiaReview`；最终为 `TaiziReply`，无 archive receipt 则用 `partial_or_not_run`、`authority_blocked` 或 `handoff_or_pause`。

## Validation And Packaging

安装/发布/包装的校验与硬门（安装时校验自删、sync_active_copies、package/release/portability gates、prune/备份/回滚）见 [validation-packaging.md](references/validation-packaging.md)。
最小本地结构验证命令：`python -B scripts/quick_validate.py .`。
