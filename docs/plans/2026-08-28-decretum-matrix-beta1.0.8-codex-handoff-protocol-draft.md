# Codex 阶段交接协议草案（Handoff Protocol Draft）

> 版本：draft-0.1 · 日期：2026-08-28 · 配套：beta1.0.8 计划书 §3
> 性质：**草案**。核心部分（状态模型 / 制品 schema / 生命周期 / 校验 / 失败处理）作为协议基线不可省略；Codex 承接实现时须按自身环境完善 §7 环境适配点，扩展以附录追加并记录理由，不得静默修改核心。
> 目标：让「阶段交接」从一次性行为升级为**可校验、幂等、可审计**的协议——交接双方（上一阶段 Codex 会话、下一阶段 Codex 会话、人工评审）无需对话即可通过仓库内制品完成状态确认与续接。
> 交接协议只负责阶段边界，不负责会话记忆。会话记忆由 `context-save` / `context-restore` 管，阶段交接由 handoff 文档、证据文件、任务书阶段标记和 git 状态共同证明。

---

## 1. 目的与原则

1. 每个阶段结束，工作状态必须能被下一个 Codex 会话**仅凭仓库内制品**恢复，不依赖对话历史。
2. 交接必须可机器校验：声明（handoff 文档）与事实（git 状态 / 门禁输出 / 文件存在性）一致才算有效交接。
3. 交接必须幂等：重复执行交接动作不产生重复制品、不破坏状态。
4. 交接失败（BLOCKED）必须显式登记，交由上级评审，任何会话不得"默默继续"。

## 2. 参与者与角色

| 角色 | 职责 |
| --- | --- |
| HANDOFFER（交接方） | 上一阶段 Codex 会话：执行验收、提交、生成交接制品、登记状态 |
| HANDOFFEE（承接方） | 下一阶段 Codex 会话：按 §5 恢复读取协议接管 |
| CONTEXTEE（会话接手方） | 下一阶段 Codex 会话：按上下文恢复步骤找回最近工作点，再按 handoff 协议继续 |
| REVIEWER（评审方） | 人工/门下复核：阶段出口评审、BLOCKED 处置、发布批准 |
| VERIFIER（校验器） | 协议定义的 handoff-check（脚本或等价校验），可由任一角色运行 |

## 3. 状态模型（交接状态机）

交接制品（每个 Phase 一份）状态流转：

```text
IN_PROGRESS → VERIFY_READY → VERIFIED → COMPLETED
     │              │            │
     └── BLOCKED ←──┘            └──→ (归档，只读)
```

- IN_PROGRESS：阶段执行中；交接制品创建但未完成。
- VERIFY_READY：验收与提交完成，制品待校验。
- VERIFIED：handoff-check 通过，声明与事实一致。
- COMPLETED：REVIEWER 确认出口，状态登记完成，可进入下一阶段。
- BLOCKED：验收失败 / 校验不一致 / 外部阻塞；含 blocked_reason，仅 REVIEWER 可解除或改道。

状态记录位置：docs/plans/beta1.0.8/handoffs/README.md（交接索引，每阶段一行，含 status/artifact/commit/verified_by/ts）。
上下文记录位置：gstack saved context 文件，与 handoff 索引并行存在；它只保存会话延续信息，不替代交接证据。

## 4. 交接制品

### 4.1 制品清单（每个 Phase N）

| 制品 | 路径 | 必填 |
| --- | --- | --- |
| 交接文档 | docs/plans/beta1.0.8/handoffs/phase-N-handoff.md | 是 |
| 验收证据 | docs/plans/beta1.0.8/handoffs/phase-N-evidence.md（或 evidence/ 目录） | 是 |
| 交接索引行 | docs/plans/beta1.0.8/handoffs/README.md | 是 |
| 机器校验结果 | docs/plans/beta1.0.8/handoffs/phase-N-check.json | 建议（VERIFIER 产物） |

### 4.2 交接文档 schema（phase-N-handoff.md 必需字段）

```text
# Phase N Handoff — <阶段名>
- protocol_version: draft-0.1
- phase: N
- status: IN_PROGRESS | VERIFY_READY | VERIFIED | COMPLETED | BLOCKED
- handoffer_session: <会话标识>
- started_at / finished_at: <ISO 时间>
- git_branch: release/beta1.0.8
- git_head_commit: <sha>
- working_tree_clean: true/false（不含允许的 docs 例外）
## 1. 目标达成
（逐条任务：完成 / 未完成 + 原因）
## 2. 变更文件清单
（新增/修改/删除，含简要说明）
## 3. 验收命令与输出
（命令 → 期望 → 实际；不一致必须标注）
## 4. 遗留问题与风险
## 5. 未决决策（需 REVIEWER 拍板）
## 6. 下阶段入口指针
（指向任务书下一阶段任务 ID 与本文 §5 恢复读取协议）
## 7. 交接自检
（对照 §6 校验项逐条：通过/不通过）
```

### 4.3 校验项（handoff-check 内容，VERIFIER 执行）

1. 交接文档存在且 status 与索引一致；
2. git 分支与 head commit 与文档声明一致；工作树状态与声明一致；
3. 文档声明的验收命令可复跑且输出与声明一致（至少抽检 3 条关键命令）；
4. 阶段出口边界（计划书 §3.2 该 Phase 的特殊条件）全部满足；
5. 无 BLOCKED 遗留（若有，须有 blocked_reason 与 REVIEWER 记录）。

## 5. 恢复读取协议（HANDOFFEE 接管步骤）

下一阶段 Codex 会话开始工作时，按序执行：
1. 读权威 SKILL（C:/Users/32893/.agents/skills/decretum-matrix/SKILL.md）；
2. 读取本机能力索引筛出的有用 skill，优先 `stop-that-shit`、`using-superpowers` / Superpowers、`ponytail`、可用 handoff skill；
3. 如要接手上个会话的工作点，先跑 `context-restore`；
4. 读计划书（§3 交接契约）与任务书（本阶段任务）；
5. 读 handoffs/README.md 确认上一阶段 status=COMPLETED；
6. 读上一阶段 phase-(N-1)-handoff.md 与 phase-(N-1)-evidence.md，核对 §6 校验项；
7. git log -10 与 git status 比对声明；
8. 任一不一致 → 按 §8 失败处理，不得继续。

## 6. 生命周期（一次完整交接）

1. HANDOFFER：完成阶段全部任务验收 → 提交代码 → 工作树干净。
2. HANDOFFER：生成 phase-N-handoff.md（status=VERIFY_READY）+ 证据文件。
3. VERIFIER：运行 handoff-check（§4.3）；通过 → 文档 status=VERIFIED + phase-N-check.json；不通过 → status=BLOCKED + blocked_reason。
4. REVIEWER：出口评审（必要时）；通过 → status=COMPLETED，登记索引，允许进入下一阶段。
5. 归档：COMPLETED 后交接文档只读（不修改历史交接）。
6. HANDOFFER：将阶段状态与验收证据摘要回写任务书，完整输出写入 phase-N-evidence.md；会话结束前运行 `context-save`。

## 7. 环境适配点（Codex 按自身环境完善，追加附录记录）

以下点允许按实际执行环境完善，但须以附录方式记录理由与差异：
- A1 handoff-check 的承载形式：独立脚本（建议 scripts/handoff_check.py）或等价命令序列；本仓库已有一批 check_* 可复用（如 check_release_manifest 输出作为证据）。
- A2 会话标识字段：Codex 会话 id / 终端标识 / 任务 id 的取值来源（本机 Codex 会话目录 ~/.codex/sessions）。
- A3 证据文件组织：单文件 vs evidence/ 目录（建议目录，按命令分类存输出）。
- A4 git 提交粒度与 message 规范（建议每任务一提交，message 前缀 phaseN-任务ID）。
- A5 验收命令的抽检比例与超时（建议每命令超时上限与失败重跑一次）。
- A6 与 repo-control 事件审计的对接：交接状态变更是否同步写 .repo-control/events（建议：REVIEWER 批准时写一条 result 事件）。
- A7 BLOCKED 的上报渠道与升级路径（本机：通过 de_session/广播通知 REVIEWER，或直接在本会话说明）。
- A8 上下文技能的使用边界：`context-save` / `context-restore` 只负责会话延续；任何阶段出口仍必须以 handoff 文档、验收证据、任务书阶段标记和 git 状态为准。
- A9 技能优先级：先读 `decretum-matrix`，再按当前问题优先调用 `stop-that-shit`、`using-superpowers` / Superpowers、`ponytail`；需要跨会话续接时补用 `context-restore` / `context-save`。
- A10 MCP 入口与范围记录：交接时记录当时已确认的 court_mcp_server 入口、工具清单、读写边界和传输层。Q1 当前暂定为“保留现有通用 MCP 入口，并在其上做适配与新增功能”，但该结论不冻结后续边界；后续访谈若调整，必须回写五份计划文档并更新 handoff/evidence，不得沿用旧假设。

## 8. 失败处理

- 校验不通过 / 门禁红 / 声明与事实不符 → HANDOFFER 记录 blocked_reason，status=BLOCKED，停止推进。
- 下一阶段发现上一阶段交接与实际不符 → 立即停止，按本节处理；不得"顺手修复"越界。
- BLOCKED 解除仅由 REVIEWER 决策（修复后重验，或变更范围）。
- 任何会话不得伪报 status（VERIFIED/COMPLETED 必须有校验与评审依据）。

## 9. 与 beta1.0.8 计划书的关系

- 本协议是计划书 §3「每阶段 Codex 交接契约」的细则与实现依据；
- Phase 0–5 每阶段结束时按本协议执行一次完整交接；
- 协议草案本身允许在首个 Phase（Phase 0）执行时按环境适配点完善并固化附录，之后阶段按固化版执行。

## 10. 开放问题（供 Codex 完善时回答）

- Q1 handoff-check 是否脚本化进 scripts/ 并纳入发布门禁？（建议：是，check_handoff_protocol.py）
- Q2 交接证据是否纳入 release-manifest / install-projection？（建议：docs/plans 不入运行时投影，保持 docs-only）
- Q3 多会话并行阶段（Phase 2/3/4 并行）时交接顺序如何仲裁？（建议：仍以索引行先后为准，同 Phase 多会话各自独立交接，冲突由 REVIEWER 仲裁）
