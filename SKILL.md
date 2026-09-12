---
name: decretum-matrix
description: Decretum Matrix（诏令矩阵） routes /court and $decretum-matrix work through 三省六部, P00, explicit authority, CLI/MCP and Codex/Hermes host receipts. superCC is a separate runtime.
license: AGPL-3.0
metadata:
  version: beta1.1.3
  author: RowlandL
---

# Decretum Matrix（诏令矩阵）

## P00 Highest-Priority Semantic Dispatch And Resume Contract

`P00_HIGHEST_PRIORITY=REQUIRED`. Before dispatch/resume/handoff, bind the existing `court.semantic.invariant_capsule.v1`, semantic receipt, authority/plan pointers and `plan_cursor`; require `semantic_epoch == charter_revision`. Capsule and dispatch context packet are each at most 2,048 UTF-8 bytes.

- Carry exact ids, bounded scope/write set, receipt pointers, role/direct_superior and `fork_turns=none`; no full transcript/file/diff/agent list by default.
- `child_agent` and `worktree_thread` share capsule, receipt, hierarchy, role context and bounded trace; neither creates another authority.
- Reuse compatible live instances below 80% context; keep in-flight work until completion/recall. Unrelated or large parallel work may need a fresh instance. Full-context override never changes authority, safety or hierarchy.
- `task_point_projection=POST_MIGRATION_DURABLE_PROJECTION_ONLY`: durable Shiguan projections after migration are not inline runtime authority.

## Codex/Claude Hierarchical Relay Evidence

Codex/Claude-style recursive hosts need current-session delivery evidence before claiming 三省会审/尚书统合六部。主线程/太子可作中枢转发，但不得改变官署层级；`direct_superior=...`、计划图或 flat OK wave 不足以证明互联互通。缺证据标 `runtime_degraded/PARTIAL`。仅适用于 Codex/Claude 类递归子代理宿主；DeepSeek Harness、EAC/DSH、MCP-only、CLI/script 等非递归 runtime 按其宿主规则。

Ref: relay/parallel claims load [court-offices-dispatch.md](references/court-offices-dispatch.md).

## Unified Dynamic Dispatch Semantics

1. 官署按职责、依赖、风险和证据价值选择，不为填满容量派生。
2. 默认 whole-tree 上限 16（含 root），`max_depth=4`；只有最新用户明确给出更大数量或 `unlimited/解限` 才可提高 ceiling。预算、宿主容量/拒绝、资源压力、层级、写集、preload 与实例追溯仍须有效。
3. `execution_authority=approval|autonomous|super` 与 `behavior=serial|parallel` 独立。缺哪项分别询问；不得从记忆、旧会话、sandbox、安装意图或运行权限推定。
4. `super并行` = super + parallel + native。superCC 是独立 runtime/入口，不是第四权；native/superCC 互斥，不探测候选、不切换、不回退。
5. 普通生产路由优先使用宿主已证实兼容的层级子官署协议；`subagent`/`Multi-Agent V2` 只作兼容选项，不是强制字段或字样。若宿主无工具或证据链，则使用 serial 或中枢转发并标注 `runtime_degraded`；不得强设 model-reserved override fields。
6. serial 禁止物理 child 并发，保留 `serial_inline` 官署责任与证据；parallel 使用真实宿主派遣。共享/外部写串行；拒绝、限流或语义漂移即停当前 wave。

## Normal Startup Entry / Loading Procedure

首次读全本文件与 [court-normal-startup.md](references/court-normal-startup.md)，禁 preview；核心语义阶段读 [court-core-contract.md](references/court-core-contract.md)。版本/材料未变复用；恢复核对最新旨意/P00；结诏不重复读入口。

- 入口、当前官署 profile/dossier、启动指引及 metadata 合计 `<=20 KiB`。派遣前读本署材料，父级不预读全部子署。
- 已指定能力直接用 CLI/MCP；不全读能力索引，不翻源码猜参数。进入 core/dispatch/state/closeout 阶段读对应卷。
- 安装验收在安装阶段完成，随后移除安装专用检查。身份预载：先完整读取技能，再读本署 profile/dossier，以诏令编号关联实际读取、职责、直接上级与宿主证据；正常启动不重复安装验收。

## Common Hard Gates

- Charter 绑定最新旨意、非目标、边界、动作、验收、证据、stop 和史馆策略。非平凡 intake 使用 `court.request_understanding.v1`，对齐目标、使用场景、关键要求和验收标准：低于 95 时一次只问一个高影响问题、给 2–4 选项；达到 95 则简要复述后执行，不强行提问。
- `approval` 默认只读；`autonomous` 范围内实施；`super` 范围内连续推进。三权均不自动授权破坏、泄密、付费、私密上传、公网暴露、未验证安装或无界树；最新用户边界优先。
- 开朝、自检、复核、状态任务先区分官署履职与机器事实。前者必须按层级 host-native spawn/reuse/wake 或显式 serial_inline；CLI/script 只辅助，不替代派遣和回奏。
- 默认治理实现为 `three-departments-six-ministries`，清单为 `references/manifests/governance-implementations.v1.json`。参考实现不得改变 runtime、证据、权限、直接上级或史馆权威；源码规则/检查通过不等于 VERIFIED_CAPABILITY。
- 外部工具、额外安装目标、发布/推送须当前明确授权。安装默认只投影共享 .agents 与 current-tool。
- superCC 需要当前选择及 zellij+squad/client 证据；super GL 只在已确认 room 用真实 @profile，不模拟、@all 或无限催促。

## Court Flow And Roles

固定层级：用户→太子→三省；尚书→六部；六部→工坊/工匠。中书/门下不调六部；所有 create/reuse/wake/follow-up 都受直接上级约束。绑定 role/direct_superior、P00、lease、写集、dossier/profile、expected result 与宿主证据；身份或投递故障退回。

太子受旨定性/结果章程；中书拟旨、拆解、考据；门下封驳与终审；尚书评估可分派性并统合六部。顺序为：
`太子定性 → 三省会审/上奏 → 太子回奏 → 尚书统合六部 → 工坊办差 → 门下复核 → 史馆实录`。

Legal state: `Pending → Taizi → ThreeDepartments → ThreeDepartmentsPetition → TaiziReply → ShangshuDispatch → SixMinistries → Workshops → MenxiaReview → ShiguanRecorded → Done`.

`court semantic checkpoint/verify` 的 VERIFIED/DISPATCHABLE 仅证明 P00 门禁，不证明三省履职。按上行/差遣路径规划后才在具体 delivery/mutation 前执行 `agent-admit`。其 receipt 不是 delivery；`court open --fast` 也仅 preparation。官署回奏需要实际宿主证据或显式 serial_inline，否则标 `runtime_degraded/PARTIAL`。普通 native 不加载 superCC pane/watchdog/show-delay/closeout-silence 流程。

## Public Transport Contract

CLI (`scripts/court_cli.py` → `court_cli_registry.py`) 与 MCP 共用 `scripts/court_public_api.py`，命令权威为 [cli-command-surface.v1.json](references/manifests/cli-command-surface.v1.json)。MCP 不 spawn CLI、不解析 stdout；lifecycle/Git hooks 已撤回，.codex-plugin 仅兼容 metadata。

只读校验、状态和史馆检索优先调用对应 MCP；不可只调 help 后翻源码重写。生产和验收使用公开 `decretum-matrix` CLI；PATH 缺失时解析当前 npm prefix 下的命令入口，不降为内部 Python 业务脚本。状态变更走 receipt-bound CLI，真实派遣走宿主；检查 domain success，不凑调用次数。

## Progressive Loading Map

路径默认 skill-root 相对；绝对路径只作机器证据。阶段：启动 [court-normal-startup.md](references/court-normal-startup.md)；语义 [court-core-contract.md](references/court-core-contract.md)；官署/转发 [court-offices-dispatch.md](references/court-offices-dispatch.md)；P00/状态 [court-state-runtime-agents.md](references/court-state-runtime-agents.md)；能力 [court-capability-registry.md](references/court-capability-registry.md)；superCC [court-supercc-runtime-selection.md](references/court-supercc-runtime-selection.md)；史馆 [court-shiguan-memory.md](references/court-shiguan-memory.md)；安装 [court-host-platform-pitfalls.md](references/court-host-platform-pitfalls.md)；结诏 [court-closeout-validation.md](references/court-closeout-validation.md)。

## Shiguan, Pending, And Memory

`shiguan_paths.py` resolves shared authority；史馆 GBrain 与 query/index/Git/Obsidian 都是 advisory/preserve-only，无执行权。普通 startup 不运行重型 Git。

pending/private 仅允许 metadata governance；没有不可伪造主机授权不得读取、移动、删除或标记正文。不得保存 secrets、原始私密日志、瞬态输出、猜测或未获批个人数据。

## Closeout Skeleton

完成、暂停、阻塞、取消或 handoff 时按需读结诏卷并经门下复核。独立记录保留请求、派遣、回奏、写入和 checkpoint；标准 task 必须走 plan/review/lifecycle/assessment 归档链。十四行门禁见 [court-closeout-validation.md](references/court-closeout-validation.md)。

仅门下接受者可标 MenxiaReview。标准任务用 `shiguan archive-runtime-task`，编号/谱系/作业 AI 复制 `payload.producer_receipt.closeout_identity`；独立记录才用 `archive-checkpoint` 的 `payload.closeout_identity`。MCP 不另编号，无有效回执标 `partial_or_not_run`、`authority_blocked` 或 `handoff_or_pause`。

记忆裁定为 WRITE | PROPOSE | SKIP | DEFERRED；WRITE 需当前授权与门下接受。安装、备份、回滚和源码包装规则见 [validation-packaging.md](references/validation-packaging.md)。

## Local Validation

`python -B scripts/quick_validate.py .`
