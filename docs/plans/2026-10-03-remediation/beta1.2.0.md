# beta1.2.0 独立计划 · 语义与计划绑定

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：[beta1.1.9](./beta1.1.9.md)｜下一版：[beta1.2.1](./beta1.2.1.md)
> 依赖：无｜被依赖：无
> 工单：`07-f04-f05-f06-semantic-binding`（本地工单 .scratch/remediation-2026-10/issues/）
> 权威依据：consolidated-review.md（仓库外只读，绝对路径见总纲文档地图；该类引用不参与仓库内链接校验）
> 条目：F04、F05、F06

## 阶段预验收审核位（2026-10-13 追加）

- **审核位：阶段精简审核（门下职责）**；实施启动时在原任务记录绑定实际审核者。每个小阶段预验收同时审查功能证据、过度繁杂治理和过度严苛门禁，复用原 reviewer 与记录；执行者不自签独立审核。
- **本版触发点：** F04、F05、F06 每项交付及合法结果/门下路径；本版出口汇总。已结束的历史阶段不补造审核、不重新开工。
- **本版聚焦：** 语义绑定的单一验证边界、正常路径误拒绝与路由结构化衔接；D1/D2/D5。删除/合并/诊断化/按需触发的判断及必要保护回归依[总纲 §26.3–§26.5](../2026-10-03-decretum-matrix-remediation-plan.md)；未论证的新治理不能因名称或格式默认成为硬门禁。
- **最小记录：** 在原阶段表、工单 Comments 或既有 review 中写阶段、审核者、具体发现/正反例、处置、证据和下一步；无发现可一行通过，不新增平行账册或每阶段仪式。

## 1. 版本目标

P00 持久化、结果封套、复核职责三类绑定校验对齐——**"写了什么"与"该写什么"必须一致**，不一致必须被显式拒绝而非静默接受。

## 2. 修复条目

### 2.0 最新优先工作包 · 派遣显示与隐式预载（2026-10-13）

用户以当前真实子署卡片与尚书 JSON 回执指出复发问题：子智能体名称应表达官署职责，不带技术编号串；内部派遣对象、预载回执不应显性。本版先用 5 Why 修复这一生产者/消费者断点，再继续 F04/F05/F06。修复靠数据、传递和展示分工，不以追加“禁止类”规则、过滤审计或删除身份保护代替。

- 已确认：`court_native_bridge._host_invocation` 将 UID/attempt 后缀用作宿主名称，`canonical_host_message` 将完整机器对象用作真实消息，并仍生成 acceptance 模板与等待动作；runtime 两处 start 消费者重复推导该名称。当前 implicit preload 状态和 normal-startup 已变更，但消息生产者及其旧结构检查未同步。
- 最小范围：native bridge 生产者、runtime 对应消费者、直接受影响的原 checker；复用 `collaboration_task_name`、实际宿主 identity、既有 P00/request/receipt 和业务 summary/evidence。完整技术对象继续留在机器记录中，人类差遣/上奏从事实生成简明投影。旧 UID 实例继续按已捕获身份合法复用。
- 验收：保留本轮实际失败和纯生成器 RED；职责名称、简明任务、完整读取后继续已准业务通过；预载回执留机器侧；同 role 并发/retry、旧实例 followup、明文精确匹配及 opaque 捕获与 P00/角色/上级/写集保护通过；真实 native 正例读回宿主名称、实际加载和业务回奏。仅源码检查不能宣称 UI 已修复。
- 执行/审核：尚书→工部→单工坊，同一 owner 串行修改相交文件；门下复用阶段精简审核。实际差遣、精确写集和证据见 `tasks/items/TASK-002.md`。本轮仍为本地源码/直接验证，安装替换、root accepted version 与外部发布另按已授权边界处理。

### 2.1 F04 · P00 持久化绑定漏验 capsule.schema（P2）

- 现象：正常规范化器会拒绝未知/空/非文本 schema，但持久化 P00 绑定的 continuity 检查却不校验 `capsule.schema`，checkpoint/verify 仍给出 `DISPATCHABLE`。
- 位置：`scripts/court_semantic_continuity.py:493`。
- 修复要求：复用已有 schema/shape 规范进行校验；同一负例覆盖输入、持久化、checkpoint/verify 三处。
- 验收（可测）：
  - [x] 非法/缺失/非文本 schema 在输入、持久化、checkpoint/verify 三处一致被拒（SOURCE，见原门下 review）；
  - [x] 合法 capsule 不受影响（既有正例回归，SOURCE）。
- 证据：负例与正例的三处对照输出。
- 边界：仅临时存储反例，不得声称证明真实派遣或外部攻击权限。

### 2.2 F05 · result envelope 未与目标绑定比较（P2）

- 现象：result envelope 存在 `task_id`、`plan_ref`，却未与目标绑定比较；真实临时 `agent_finish` 持久化了不同任务 ID / 未签发计划引用并标 `completed`。
- 位置：`scripts/court_semantic_continuity.py:2065`。
- 修复要求：补任务/受 admission 或 current plan 约束的相等校验；沿用既有隔离/重试路径。
- 验收（可测）：
  - [x] 不同 task_id 或未签发 plan_ref 的结果被拒绝（SOURCE，沿原隔离路径）；
  - [x] 与目标一致的正常完成路径不受影响（含显式 null、历史缺字段兼容，SOURCE）。
- 证据：负例/正例对照；office 状态为夹具的事实须标注（未证明真实宿主冒名或 Done）。

### 2.3 F06 · 非门下 actor 可写 MenxiaReview（P2）

- 现象：非门下 actor 可通过公开 transition 把标准 case 写为 `MenxiaReview`，owner 也归该 actor；状态边合法性没有保护接受者职责。
- 位置：`scripts/court_runtime.py:7395`。
- 修复要求：约束复核阶段的接受者、owner 与门下证据；保持合法门下流程与暂停/恢复。
- 验收（可测）：
  - [x] 非门下 actor 的 `MenxiaReview` 转移被拒绝（同时覆盖显式错误 owner、空证据及工坊暂停态首入，SOURCE）；
  - [x] 合法门下复核与暂停/恢复路径不受影响（原门下暂停阶段恢复 owner 归门下，SOURCE）。
- 证据：负例/正例对照；标注起始阶段由临时夹具布置，未证明真实业务全流转或最终 assessment/Done 绕过。

## 3. 版本出口（Exit Criteria）

- [x] 四项绑定校验（capsule.schema、task_id、plan_ref、复核职责）均有负例与正例（本地 SOURCE）；
- [x] 合法门下与合法结果路径回归通过（本地 SOURCE）；
- [x] 保留四项必要绑定校验；确认冗余的重复校验按总纲 §26.3 合并，不把“全部原校验不变”当成独立验收要求（门下本地出口审核，调用内复用已验证 anchor，I/O/mutation 保护保持）。

本地出口已接受；优先项的安装候选、真实 native/UI 及正式全流转仍待验证。当前安装未替换，发布、根 accepted version 与本版总体完成未由上述 SOURCE 勾选证明。

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
| 2026-10-13 | 用户最新优先项：5 Why、派遣职责名、业务差遣/回奏、COMMITTED 安装根选择；原两工坊停写后由门下定向独立复核 | `tasks/reviews/TASK-002-20261013-menxia-review.md`；`.scratch/TASK-002-20261013/dispatch-5why.md`；各坊最终 RED/GREEN | SOURCE_PRIORITY_ACCEPTED；真实安装候选/UI NOT_RUN；正式生命周期 PARTIAL |
| 2026-10-13 | 复用尚书→工部→原单 owner 串行接续 F04/F05/F06，先保留消费者失败，再验证合法路径 | `tasks/items/TASK-002.md` 与同一门下 review | IN_PROGRESS；未提前接受本版 |
| 2026-10-14 | F04：持久化消费者复用 schema 常量补两行；21 漏项 RED→GREEN，八类输入/持久/checkpoint/verify 对照及合法胶囊回归；门下独立审核 | `.scratch/TASK-002-20261013/gongbu_presentation/f04-f05-f06/f04-stage.txt`、`f04-command.txt`、`f04-red.txt`、`f04-green.txt`；同一门下 review | F04_SOURCE_ACCEPTED；安装/UI 未由此证明 |
| 2026-10-14 | F05/F06 及最终本地出口：原单 owner 串行，直接关联 fixture 两字段与 completion SOURCE 上下文同步；原七文件停写，门下逐项及最终审核 | `.scratch/TASK-002-20261013/gongbu_presentation/f04-f05-f06/README.md`、`final-suite-command.txt`、各项 RED/GREEN、`batch-final-delta.diff`；同一门下 review | LOCAL_SOURCE_ACCEPTED；runtime/lifecycle/completion 24/关联 7 均 exit 0；T08/stage3 原失败与安装/UI 未验保留 |

## 发布与 CI 验证（按总纲 26.1）

- 本版验收通过后执行：推送到 GitHub、GitHub Release、npm 包发布（版本号 = 本版号）；
- 以既有 GitHub Actions CI 验证；**CI 内容默认不改动**（不为过审降低必要保护；经阶段审核确认的冗余门禁精简及对应检查同步按总纲 §26.3 执行）；
- 仅当 CI 验证确实不可行时提出调整并经用户同意；发布前核对 workspace.yaml 的 publication_gates；
- 发布证据（Release / npm / CI 回执）记入执行记录。

---

*本计划由总纲派生；修改需同步总纲第二节与交叉引用关系。*
