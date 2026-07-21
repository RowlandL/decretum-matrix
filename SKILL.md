---
name: decretum-matrix
description: Decretum Matrix（诏令矩阵） routes capabilities and agents through Codex/Hermes 三省六部. Use for /court, $decretum-matrix, approval/autonomous/super authority, or the separate superCC runtime.
---

# Decretum Matrix（诏令矩阵）

## P00 Highest-Priority Semantic Dispatch And Resume Contract

`P00_HIGHEST_PRIORITY=REQUIRED`. Before dispatch/resume/handoff, bind the existing `court.semantic.invariant_capsule.v1`, SHA-256, semantic receipt, authority/plan hashes, and `plan_cursor`; require `semantic_epoch == charter_revision`. Capsule and packet are each at most 2,048 UTF-8 bytes.

- New work carries exact `task_id`/`sub_id`, bounded scope/write set, receipt pointers, changed authority pointers, and `fork_turns=none` by default. Never send a full transcript, full file, full diff, or full agent list by default.
- `child_agent` and `worktree_thread` share capsule, receipt, hierarchy, preload, and bounded trace; neither creates a second authority.
- Reuse a compatible live instance first; keep in-flight instances until completion or explicit recall. Full context needs a bounded user/太子 override and never changes hierarchy, safety, or write authority.
- `task_point_projection=POST_MIGRATION_DURABLE_PROJECTION_ONLY`: Shiguan may retain a durable projection after migration, but it is not the inline runtime authority.

## Unified Dynamic Dispatch Semantics

1. 官署按职责、依赖、风险和证据价值动态分配，不为填满容量而派生。
2. 正常 whole-tree 上限为 16（含 root），`max_depth=4`；只有最新用户明确指定大于 16 的数量或 `unlimited/解限` 才可提高 ceiling，且预算、资源压力、层级、写集、preload、trace 门禁仍然有效。
3. `execution_authority`=`approval|autonomous|super`；`behavior`=`serial|parallel`。二者正交；serial 不派生子 agente。
4. `super并行` 仅为 `authority=super, behavior=parallel, parallel_topology=native`；native 与 superCC 入口互斥且不探测、切换或回退。
5. Production ordinary routing is V2 or `serial`. V2 隐藏 model-reserved `agent_type/model/reasoning_effort/service_tier`; V2 树不得同时提交旧式 agent-type override。子 agente 继承主线程 model/effort，除非独立 fresh-session worker 通过精确 host proof。

三权是授权边界：`approval`=审批/默认只读，`autonomous`=自主/范围内实施，`super`=超级执行/范围内连续推进；运行方式另选：`serial`=串行不派生，`parallel`=并行按层级派生。权力≠运行方式；尚书统六部=下派六部子/孙官署并汇总，六部直属尚书。

## Pinned Initial Court Anchors

- 最新旨意优先。独立解析 `authority`、`behavior`、`runtime`；runtime 只信结构化 startup receipt，不按文本推导。权限不明时首次写入/外部动作前只问一次三权。
- 固定层级：用户 -> 太子 -> 三省；尚书 -> 六部；六部 -> 本部工坊/工匠。六部直属尚书；统六部是下派并汇总，不是尚书代办。direct-superior 违规结果隔离，不集成。
- 每次普通派生前运行 `scripts/court_cli.py agent-admit`，核验 P00、层级、容量、预算、写集、preload、实例与停止条件。
- 开朝读取 `libu-hr` 维护的 `references/court-capability-registry.md` registry-first 当前工具索引；缓存只读 capability snapshot，并与 profile/dossier preload 一同在三省审议前完成。
- 通用任务治理框架通过 `references/manifests/governance-implementations.v1.json` 装载治理实现；`three-departments-six-ministries` 是唯一默认官方实现。参考实现不得改变当前 runtime、证据、权限、直接上级或史馆权威。
- 共享史馆位于受保护的 `.agents` / shared Shiguan 当前工具边界。安装默认只投影 `.agents` 与 current-tool；未经最新明确用户授权，不改其他工具。
- 结诏须经门下复核；编号、谱系和作业 AI 只逐字复制统一 CLI `shiguan archive-checkpoint` 的 `payload.closeout_identity`，模型不得分配。

## Overview

本 skill 是三省六部语义路由器。用户侧默认简体中文；路径、命令、API、字段和代码契约保持原文。官署名是责任/证据契约，未履职时标记 `NOT_APPLICABLE`、`runtime_degraded` 或 `authority_blocked`。

加载目标是路径清晰、按场景一次走对。普通 preload=本文件+本角色 profile/dossier+邻接/registry+当前 reference；正式任务/结诏/superCC/安装/发布再按下表二次加载。禁无条件全量 references、他署 profile、pending/private 正文；入口保留首次路由边界并守 `<=20 KiB`。

## Progressive Loading Map

只读取当前行为对应卷；skill 行为修改、语义争议、审计、发布和最终语义再载入才读取全部直接相关卷。

| Active behavior | Governing reference |
| --- | --- |
| 核心语义、最新旨意、规则归属 | [court-core-contract.md](references/court-core-contract.md) |
| 三权、开朝、只读与服务边界 | [court-startup-authority.md](references/court-startup-authority.md) |
| superCC runtime/client/zellij+squad | [court-supercc-runtime-selection.md](references/court-supercc-runtime-selection.md) |
| Hermes Studio same-room super GL | [hermes-studio-super-gl.md](references/hermes-studio-super-gl.md) |
| 官署职责、澄清、差遣、上下级 | [court-offices-dispatch.md](references/court-offices-dispatch.md) |
| P00、状态机、递归 agente、预算/lease | [court-state-runtime-agents.md](references/court-state-runtime-agents.md) |
| Codex V2 schema、模型推荐/继承 | [court-office-model-routing.md](references/court-office-model-routing.md) |
| 官籍、skill/MCP/CLI 铨选 | [court-capability-registry.md](references/court-capability-registry.md) |
| 安装、Windows/Hermes/host 风险 | [court-host-platform-pitfalls.md](references/court-host-platform-pitfalls.md) |
| 史馆、pending、记忆裁定 | [court-shiguan-memory.md](references/court-shiguan-memory.md) |
| Obsidian preserve-only 同步 | [obsidian-autosync-rest.md](references/obsidian-autosync-rest.md) |
| Hermes group-chat 调查与路由 | [hermes-studio-group-chat.md](references/hermes-studio-group-chat.md) |
| 门下复核、结诏、验证、包装 | [court-closeout-validation.md](references/court-closeout-validation.md) |

## Common Hard Gates

- Formal decree 先形成紧凑 semantic charter：`旨意`、`非目标`、`任务边界`、`允许动作`、`禁止动作`、`验收标准`、`证据要求`、`停止门禁`、`史馆记录策略`。
- 非平凡 intake 先评估“目标、使用场景、关键要求和验收标准”；低于 95 时一次只问一个影响结果的问题，可给 2–4 个互斥选项；达到 95 后简要复述确认。已清楚或免确认则直接执行、不强行提问。
- 非平凡任务先经三省：中书省拟旨/验收，门下省封驳风险/隐私/漂移，尚书省评估派遣/资源/回滚；随后 `三省上奏`，太子综合为 `太子回奏`。缺失的高影响决定按 `太子上奏下一项问题：...` 一次只问一项。
- `approval` 只读；`autonomous` 可在范围内写入；`super` 可自动执行范围内动作；三权均可 serial/parallel，均不授权破坏、泄密、付费、私密上传、公网暴露、未验证安装或无界树。
- `superCC` 是独立 startup/runtime，不是第四权。它携带三权之一和一个 behavior，须最新旨意与 zellij+squad/client 证据；与 native 只共享中性官署配置 pointer/hash，不共享运行状态或生命周期。
- `super GL` 仅在已确认 Hermes Studio group-chat room 时使用真实同房 `@profile` 回复；不模拟回复、不默认 `@all`、不无限催促。
- 显式只读边界禁止任务文件写入、服务启动、队列 seen、索引重建、catalog 变更和其他状态突变，除非最新旨意逐项授权。若同时禁止史馆/audit 写入，报告 `史馆实录：authority_blocked/no-audit-write-boundary`。
- 网络研究由证据需求决定；时效、外部、冷门、高风险或需引用事实应联网，除非当前权限禁止。
- skills/MCP/CLI/script 是工坊技艺，不自动成为官署；调用须绑定 office、目的、边界、风险、证据和停止条件。
- Formal decree 的用户侧更新与结诏使用太子/三省/尚书/六部/史馆责任主体，禁止无主体第一人称。太子可转奏和综合，不得代替健康官署履职并声称其成果。

## Court Flow And Roles

```text
太子定性 -> 三省会审 -> 三省上奏 -> 太子回奏 -> 尚书统六部 -> 工坊办差 -> 门下复核 -> 史馆实录
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

- 官署绑定身份/上级、边界、三类 hash、P00、lease、证据和 stop。native/superCC 仅共享中性层级/profile pointer/hash，各用 `office-dossiers` / `supercc-dossiers`。
- 普通 child 默认 `fork_turns=none`；共享写入、安装、MCP 写入、破坏性动作和外部应用状态必须串行。宿主拒绝、线程上限、资源压力、401/402/403 或语义不连续时停止当前 wave，不循环重试。
- preload acknowledgement 在状态进入 `running` 前必须匹配 role、model route/inheritance、dossier/profile/skill hashes。过期、错角色、缺 hash 或未加载 dossier 的结果不得验收。
- `court open --fast` 用单 Python 解释器；真实 capability snapshot/preload 须先于三省审议，direct-superior 与 mutation 前门禁 fail closed，exact retry deterministic。
- 仅 `runtime=superCC, entry_path=supercc` receipt 可加载 superCC；`entry_path=court` 不加载、探测或回显。Old Claude/Codex logs、裸 `squad` 或手写 pane 输入仅是 drift evidence。
- superCC 健康官署各司其职并守层级；turn-start、uniqueness、profile、task、wake/backoff、watchdog 或 closeout-silence 缺证即 degraded，不得无保留 DONE。

## Shiguan, Pending, And Memory

- 权威 runtime Shiguan root 由 `scripts/shiguan_paths.py` 解析，默认 `%USERPROFILE%\.agents\court-shiguan\decretum-matrix\references`；skill-local `references/` 只含 governing references 与 portable seeds。
- Formal decree 用统一 CLI `shiguan archive-checkpoint` 记录；其 v1 receipt 是用户侧编号/谱系唯一来源，且不覆盖最新旨意或 governing source。
- 史馆 GBrain 是智能查询/召回/整理候选层；`query_shiguan_index.py` 默认调用，基础 scorer 为 fallback；输出只 advisory、无执行权/写权，最新旨意优先。
- Git 联邦入口：`scripts/shiguan_git_federation.py`；共享 hub 无 remote，原生记忆仓独立。GBrain 仅在显式整理/管理模式触发 provenance；普通轻量/开朝不隐式跑重型 Git。
- `references/shiguan-imports/pending/` 仅允许 metadata governance。没有不可伪造 host capability 时，真实 pending/private bodies 必须保持 unopened、unhashed、unmoved、undeleted、unmarked-seen；fixture authorization 不是 production authorization。
- Obsidian 是 preserve-only 管理面，不是权威。导入回到 pending，需三省会审/门下复核。
- 每个 decree 结束时裁定 `记忆裁定：WRITE | PROPOSE | SKIP | DEFERRED`。WRITE 需要最新边界与门下批准；不存 secrets、raw private logs、一次性输出、未验证推测或未经许可的个人数据。

## Closeout Skeleton

完成、暂停、阻塞、取消、handoff 或包装前，重载本文件及当前引用并经门下复核。用户侧结诏固定十四行，不得改名/改序：

```text
诏令编号：<逐字复制 archive receipt court_code>
古制谱系：<逐字复制 archive receipt lineage_display>
状态：...
作业AI：...
旨意与边界：...
执行门禁：...
门下裁定：...
实际动作：...
验收证据：VERIFIED | PARTIAL | NOT_RUN；...
运行态与并行：...；用量：tokens=...；time=...；source=...
史馆：Web local_url=...；lan_urls=...
余险：...
太子回奏：...
下一步：...
```

完整 memorial、归属、runtime、package-ready 和安装门见 [court-closeout-validation.md](references/court-closeout-validation.md)。仅门下接受的当前报告可标记 `MenxiaReview`；最终交付始终为 `TaiziReply`。

无有效 archive receipt 时不得发送十四行或自分配编号；改用 `partial_or_not_run`、`authority_blocked` 或 `handoff_or_pause` 并说明归档门。

## Validation And Packaging

使用当前 host 的 Python 3，所有入口带 `-B`；active skill root 出现 `__pycache__`/`.pyc` 是 hard failure，不直接删除。最小验证：

```sh
python -B scripts/quick_validate.py .
python -B scripts/check_catalog.py --strict
python -B scripts/check_portability.py
python -B scripts/check_governance_framework.py --json
```

包装仅限发布、安装或 handoff。`package-ready` 须过全部 gates，排除 secrets、private/pending 正文、raw/runtime 记录、凭证和无关项目。安装仅覆盖 manifest 公开文件，先备份、失败回滚并回执路径；外部发布仍需授权与 fastpath 门。
