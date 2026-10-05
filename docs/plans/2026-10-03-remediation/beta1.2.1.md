# beta1.2.1 独立计划 · superCC 事实回执

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：[beta1.2.0](./beta1.2.0.md)｜下一版：[beta1.2.2](./beta1.2.2.md)
> 依赖：无｜被依赖：[beta1.3.1](./beta1.3.1.md)（superCC 治理验收引用本版回执语义）
> 工单：`08-f07-f08-supercc-truth-receipts`（本地工单 .scratch/remediation-2026-10/issues/）
> 权威依据：consolidated-review.md（仓库外只读，绝对路径见总纲文档地图；该类引用不参与仓库内链接校验）
> 条目：F07、F08

## 1. 版本目标

superCC 的成功/失败报告**以真实动作结果为准**：不以环境健康替代动作结果，不把发送/状态写失败记为"已静默、已应用"，退出码语义在 cmd 与 Python wrapper 间一致。

## 2. 修复条目

### 2.1 F07 · 环境健康替代动作结果 / closeout-silence 误判（P2）

- 现象：`ensure_supercc_court.py:3700` 的聚合用环境健康替代动作结果，rename/join 失败仍报成功；`4428` 的 closeout-silence 把发送/状态写失败当"全部已静默、已应用"。
- 位置：`scripts/commands/ensure_supercc_court.py:3700`、`4428`。
- 修复要求：从真实动作结果生成成功与副作用记录；保留"部分成功"状态，不将失败折叠为成功；同根因合并登记，不另计数量。
- 验收（可测）：
  - [ ] 成功/失败/部分成功三类回执均可从真实动作结果生成；
  - [ ] rename/join 失败场景不报成功；发送失败不被记为已静默；
  - [ ] 无真实 pane/squad 操作时以合成/隔离对照标注限制。
- 证据：三类回执对照输出（现有证据指针见报告 F07；无真实 pane/squad 操作，须标注）。

### 2.2 F08 · Windows supercc-squad.cmd 退出码被吞（P2）

- 现象：`supercc-squad.cmd` 把真实外部退出 17 变为 0；Python wrapper 同参返回 17。根因是括号块提前展开 `ERRORLEVEL`。
- 位置：`scripts/supercc-squad.cmd:9`、15、21（同模式）。
- 修复要求：调整读取退出码的时机（延迟展开/分支内读取）；保持参数转发不变；该入口为公开注册且被 dossier 实际消费。
- 验收（可测）：
  - [ ] cmd 与 Python wrapper 对同一外部命令返回相同退出码（含 17）；
  - [ ] 参数转发逐参对照不变；
  - [ ] 不改变入口注册与调用面。
- 证据：cmd/wrapper 退出码对照（现有 repro 在 `_diag/.../shangshu-squad-cmd-exit-repro.json`）。

## 3. 版本出口（Exit Criteria）

- [ ] 三类回执语义成立；退出码一致；
- [ ] 未运行真实 squad/room 的部分明确标注未验；
- [ ] 不新建 superCC 平行框架。

## 4. 依赖与顺序

- 无前置；F07/F08 相互独立。

## 5. 文档任务

- `CHANGELOG.md`：beta1.2.1 条目；
- superCC 相关 references 如有回执语义说明则同步；
- 执行记录与总纲。

## 6. 工单

| 工单 | 覆盖 |
| --- | --- |
| `08-f07-f08-supercc-truth-receipts` | F07、F08 |

## 7. 边界

- 全局边界按总纲第一节；不承诺 superCC 标准环境（该主题见 beta1.3.1）；
- 无真实 pane/squad 环境时，验收限隔离对照并标注。

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
