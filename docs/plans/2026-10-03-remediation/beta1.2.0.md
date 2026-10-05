# beta1.2.0 独立计划 · 语义与计划绑定

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：[beta1.1.9](./beta1.1.9.md)｜下一版：[beta1.2.1](./beta1.2.1.md)
> 依赖：无｜被依赖：无
> 工单：`07-f04-f05-f06-semantic-binding`（本地工单 .scratch/remediation-2026-10/issues/）
> 权威依据：consolidated-review.md（仓库外只读，绝对路径见总纲文档地图；该类引用不参与仓库内链接校验）
> 条目：F04、F05、F06

## 1. 版本目标

P00 持久化、结果封套、复核职责三类绑定校验对齐——**"写了什么"与"该写什么"必须一致**，不一致必须被显式拒绝而非静默接受。

## 2. 修复条目

### 2.1 F04 · P00 持久化绑定漏验 capsule.schema（P2）

- 现象：正常规范化器会拒绝未知/空/非文本 schema，但持久化 P00 绑定的 continuity 检查却不校验 `capsule.schema`，checkpoint/verify 仍给出 `DISPATCHABLE`。
- 位置：`scripts/court_semantic_continuity.py:493`。
- 修复要求：复用已有 schema/shape 规范进行校验；同一负例覆盖输入、持久化、checkpoint/verify 三处。
- 验收（可测）：
  - [ ] 非法/缺失/非文本 schema 在输入、持久化、checkpoint/verify 三处一致被拒；
  - [ ] 合法 capsule 不受影响（既有正例回归）。
- 证据：负例与正例的三处对照输出。
- 边界：仅临时存储反例，不得声称证明真实派遣或外部攻击权限。

### 2.2 F05 · result envelope 未与目标绑定比较（P2）

- 现象：result envelope 存在 `task_id`、`plan_ref`，却未与目标绑定比较；真实临时 `agent_finish` 持久化了不同任务 ID / 未签发计划引用并标 `completed`。
- 位置：`scripts/court_semantic_continuity.py:2065`。
- 修复要求：补任务/受 admission 或 current plan 约束的相等校验；沿用既有隔离/重试路径。
- 验收（可测）：
  - [ ] 不同 task_id 或未签发 plan_ref 的结果被拒绝；
  - [ ] 与目标一致的正常完成路径不受影响。
- 证据：负例/正例对照；office 状态为夹具的事实须标注（未证明真实宿主冒名或 Done）。

### 2.3 F06 · 非门下 actor 可写 MenxiaReview（P2）

- 现象：非门下 actor 可通过公开 transition 把标准 case 写为 `MenxiaReview`，owner 也归该 actor；状态边合法性没有保护接受者职责。
- 位置：`scripts/court_runtime.py:7395`。
- 修复要求：约束复核阶段的接受者、owner 与门下证据；保持合法门下流程与暂停/恢复。
- 验收（可测）：
  - [ ] 非门下 actor 的 `MenxiaReview` 转移被拒绝；
  - [ ] 合法门下复核与暂停/恢复路径不受影响。
- 证据：负例/正例对照；标注起始阶段由临时夹具布置，未证明真实业务全流转或最终 assessment/Done 绕过。

## 3. 版本出口（Exit Criteria）

- [ ] 四项绑定校验（capsule.schema、task_id、plan_ref、复核职责）均有负例与正例；
- [ ] 合法门下与合法结果路径回归通过；
- [ ] 未放宽任何既有校验。

## 4. 依赖与顺序

- 无前置；F04/F05 同文件（`court_semantic_continuity.py`），建议同批实现一次回归；F06 独立于 `court_runtime.py`。

## 5. 文档任务

- `CHANGELOG.md`：beta1.2.0 条目；
- 若绑定校验进入 `references/court-core-contract.md` 或相关验证卷，同步更新；
- 执行记录与总纲。

## 6. 工单

| 工单 | 覆盖 |
| --- | --- |
| `07-f04-f05-f06-semantic-binding` | F04、F05、F06 |

## 7. 边界

- 全局边界按总纲第一节；不扩大为"安全性整体审计"；
- 反例均为隔离夹具，不得表述为真实越权事故。

## 8. 执行记录（实施时填写）

| 日期 | 动作 | 证据位置 | 结果 |
| --- | --- | --- | --- |
| — | — | — | — |

## 发布与 CI 验证（按总纲 26.1）

- 本版验收通过后执行：推送到 GitHub、GitHub Release、npm 包发布（版本号 = 本版号）；
- 以既有 GitHub Actions CI 验证；**CI 内容默认不改动**（不放宽门禁、不为过审修改检查集合）；
- 仅当 CI 验证确实不可行时提出调整并经用户同意；发布前核对 workspace.yaml 的 publication_gates；
- 发布证据（Release / npm / CI 回执）记入执行记录。

---

*本计划由总纲派生；修改需同步总纲第二节与交叉引用关系。*
