# beta1.2.9 独立计划 · 归档回执契约

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：[beta1.2.8](./beta1.2.8.md)｜下一版：[beta1.3.0](./beta1.3.0.md)
> 依赖：无｜被依赖：[beta1.3.7](./beta1.3.7.md)（结项回执）、[beta1.3.9](./beta1.3.9.md)（v1.0.0 结诏门禁）
> 工单：`16-f27-archive-receipt-contract`（本地工单 .scratch/remediation-2026-10/issues/）
> 权威依据：consolidated-review.md（仓库外只读，绝对路径见总纲文档地图；该类引用不参与仓库内链接校验）
> 条目：F27

## 1. 版本目标

独立归档回执满足自身结诏契约：**两个强制摘要字段（`receipt_sha256`/`archive_sha256`）由 producer 产出**、**身份行使用合法完整内容（无省略号截断）**，使正式十四行结诏门禁可过；不手工补字段、不新增摘要工具。

排期说明：F27 原属报告"让报告表达实际执行"方向，安排在修复线末版，因其依赖结诏消费链、与归档实务同轮验收（偏移理由见总纲第二节）。

## 2. 修复条目

### 2.1 F27 · 独立归档回执不满足结诏契约（P2）

- 现象：实际公开 `shiguan archive-checkpoint` 返回 exit 0/PASS 并写入记录，但回执 schema `court.shiguan_archive_checkpoint_receipt.v1` 没有 `receipt_sha256` 与 `archive_sha256`；长 topic 的 `lineage_display` 含生成的省略号。同版 `court-closeout-memorial-format.md:67`–`73` 明确要求保留这两项摘要及 path，第 70–73 行要求无有效回执不能渲染正式结诏、身份行不得有省略号。
- 位置：`scripts/archive_checkpoint.py:692`（`build_archive_receipt` 不产生两字段）、`819`（直接写 result-json）；`references/sections/court-closeout-memorial-format.md:67`–`73`；`scripts/shiguan_entry_utils.py:1445`、`775`（限长 18 + `...`）、`1821`（传为 `lineage_display`）。
- 修复要求：明确并修复 producer/consumer 契约；复用已有摘要和档案收据机制（**不新增摘要实现**，遵守工作区禁令）；谱系身份采用合法完整内容，长 topic 可另存展示/索引字段；**不得在消费者手工伪造缺失字段**。
- 验收（可测，两个独立子项分别验收）：
  - [ ] 摘要子项：实际公开 CLI 输出的回执含两个摘要字段且值可核验（消费器接受）；
  - [ ] 身份子项：身份行无省略号，长 topic 走另存展示字段；
  - [ ] 短/长 topic、缺摘要负例、有效回执四类用例；
  - [ ] 消费器对缺字段回执仍拒绝（负例保留）；
  - [ ] 历史记录不重写（旧失败对照 `archive-receipt.json` 保留）。
- 证据：CLI 回执原文 + 消费器接受/拒绝对照 + 长 topic 样例。

## 3. 版本出口（Exit Criteria）

- [ ] 四类用例通过；两个子项分别有独立记录；
- [ ] 无手工补字段、无新增摘要工具；
- [ ] 正式结诏门禁从 `partial_or_not_run` 转为可判定状态（以消费器输出为证）。

## 4. 依赖与顺序

- 无前置；与 1.3.7 的结项回执存在引用关系（1.3.7 依赖本版）。

## 5. 文档任务

- `references/sections/court-closeout-memorial-format.md`：如契约措辞需与实现对齐则同步（保持第 67–73 行要求不弱化）；
- `CHANGELOG.md`：beta1.2.9 条目；
- 执行记录与总纲。

## 6. 工单

| 工单 | 覆盖 |
| --- | --- |
| `16-f27-archive-receipt-contract` | F27（摘要、身份两个子项） |

## 7. 边界

- 全局边界按总纲第一节；不新增哈希校验脚本（复用既有摘要机制）；
- 不宣称"所有标准 runtime receipts 都缺摘要"（本版只针对独立轻量归档路径）。

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
