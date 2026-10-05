# beta1.2.8 独立计划 · 门禁与夹具隔离

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：[beta1.2.7](./beta1.2.7.md)｜下一版：[beta1.2.9](./beta1.2.9.md)
> 依赖：[beta1.2.2](./beta1.2.2.md)（F09 修复后 MCP 断言预期才稳定）｜被依赖：[beta1.3.3](./beta1.3.3.md)（测试入口接续 gate）
> 工单：`15-f19-f20-gate-fixture-isolation`（本地工单 .scratch/remediation-2026-10/issues/）
> 权威依据：consolidated-review.md（仓库外只读，绝对路径见总纲文档地图；该类引用不参与仓库内链接校验）
> 条目：F19、F20

## 1. 版本目标

**当前"真的红却没进 gate"的测试进入门禁**（F19）：MCP 完整检查的预期与实际一致并接入现有 gate；**夹具与源环境不再互相污染**（F20）：alternate-index 保护下 builder 独立 Git 夹具可自洽运行。

## 2. 修复条目

### 2.1 F19 · MCP 检查预期过期且未进门禁（P2）

- 现象：完整 MCP 检查期待 13 工具/旧 command IDs，实际 15；实际执行 73 断言、7 失败；该 suite 未被 48 步 source gate 选中。
- 位置：`scripts/checks/check_court_mcp_server.py:27`、`48`。
- 修复要求：更新独立预期与新增工具用例；**接入现有 gate/CI**；保留严格断言（不以放宽换绿）；不直接自生产 manifest 复制全部预期（避免自证）。
- 验收（可测）：
  - [ ] MCP suite 全绿并接入 gate（在本地 gate 可执行）；
  - [ ] 新增工具（13→15 的增量）逐项有断言；
  - [ ] 预期来源独立于被检对象（写明来源与理由）。
- 证据：suite 输出 + gate 配置 diff + 逐断言清单。

### 2.2 F20 · source gate 的 alternate-index 与独立 Git 夹具冲突（P2）

- 现象：source gate 支持保护性的 alternate index，但 builder 独立 Git 夹具继承源 index，缺对应 object store，导致测试失败；只移除该变量的同环境对照通过。
- 位置：`scripts/commands/build_release_artifacts.py:107`、`578`。
- 修复要求：仅隔离独立 fixture 的 Git 定位环境；保留真实 source index 视图契约；不得为让测试过而取消保护。
- 验收（可测）：
  - [ ] 独立夹具在 alternate-index 环境自洽通过；
  - [ ] 真实 source index 视图契约保留（负例仍拒绝）；
  - [ ] 同环境对照（移除变量）仍与预期一致。
- 证据：夹具运行日志 + 对照结果（现有对照见 `_diag/.../source-gate/artifact-builder-control.summary.json`）。

## 3. 版本出口（Exit Criteria）

- [ ] 本地 gate 全绿且 scope 显式（47/48 → 48/48 或明确标注余项）；
- [ ] `required_summary` 绿不再掩盖整体失败（失败项必须在汇总可见）；
- [ ] 报告/结果显式列 scope、实际执行与缺失项。

## 4. 依赖与顺序

- 需 1.2.2（F09）先完成，否则 MCP 断言预期不稳定；
- F19/F20 相互独立。

## 5. 文档任务

- `CHANGELOG.md`：beta1.2.8 条目；
- 验收范围说明：CI / source / 安装 / 真实宿主四类集合的显式区分（本版落地该说明的初版）；
- 执行记录与总纲。

## 6. 工单

| 工单 | 覆盖 |
| --- | --- |
| `15-f19-f20-gate-fixture-isolation` | F19、F20 |

## 7. 边界

- 全局边界按总纲第一节；本版不新建 CI 触发方式（既有 CI 按 26.1 随本版发布流程执行）；
- 不删除失败日志、不隐藏警告、不放宽检查。

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
