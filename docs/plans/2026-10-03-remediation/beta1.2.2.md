# beta1.2.2 独立计划 · 公共接口与审计

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：[beta1.2.1](./beta1.2.1.md)｜下一版：[beta1.2.3](./beta1.2.3.md)
> 依赖：无｜被依赖：[beta1.2.8](./beta1.2.8.md)（F09 修复后 MCP 断言预期才稳定）
> 工单：`09-f09-f16-f18-public-surface-audit`（本地工单 .scratch/remediation-2026-10/issues/）
> 权威依据：consolidated-review.md（仓库外只读，绝对路径见总纲文档地图；该类引用不参与仓库内链接校验）
> 条目：F09、F16、F18

## 1. 版本目标

公共边界三条一致成立：**失败要可见**（操作失败传播到外层与审计）、**查询要白名单**（不返回合成/非元数据字段）、**参数要严格**（未知参数与缺值被拒绝，help 不访问状态后端）。

## 2. 修复条目

### 2.1 F09 · 召回故障时 MCP 外层仍报成功（P2）

- 现象：召回服务不可用或 API 明确操作失败时，MCP 外层仍 `ok=true`/`isError=false`，审计为 `succeeded`。
- 位置：`scripts/court_public_api.py:416`、`scripts/court_mcp_server.py:164`。
- 修复要求：传播操作失败与审计状态；**不**把所有 domain 否定结论都转为工具错误（合法负结论保留正常诊断）。
- 验收（可测）：
  - [ ] HTTP/服务故障时外层 `ok/isError` 与审计状态一致反映失败；
  - [ ] 合法领域负结论（如验证返回否）不被转为工具错误；
  - [ ] 无真实服务时以 mock 对照并标注。
- 证据：故障 mock 与合法负结论两组对照。

### 2.2 F16 · 旧 shiguan.query 回整条 entry（P2）

- 现象：旧 `shiguan.query` 返回整条 entry，包含合成/非元数据字段；新 `entries_query` 已有白名单。
- 位置：`scripts/court_public_api.py:68`。
- 修复要求：复用现有 metadata 投影与白名单；保留排序与 envelope 形状。
- 验收（可测）：
  - [ ] 旧查询输出仅含白名单字段（与 `entries_query` 投影一致）；
  - [ ] 排序与 envelope 不变；
  - [ ] 未读取或暴露真实私密正文（以夹具验证并标注）。
- 证据：字段清单前后对照。

### 2.3 F18 · court status 参数解析不严格（P2）

- 现象：`court status` 忽略未知参数和缺值；`help` 查询实际访问状态后端。真实 backend 正确拒绝非法 view（不能把早期 mock 转发当接受）。
- 位置：`scripts/court_cli_registry.py:478`。
- 修复要求：明确解析/拒绝未知参数与缺值；`help` 不访问状态后端；保留 `compact/limit` 正例。
- 验收（可测）：
  - [ ] 未知参数、缺值被显式拒绝（含非法 view）；
  - [ ] help 调用不触达状态后端（可观测）；
  - [ ] compact/limit 正例不变。
- 证据：CLI 输出对照（现有探针在 `_diag/.../zhongshu-contract-probes.json`）。

## 3. 版本出口（Exit Criteria）

- [ ] 失败时外层 `ok/isError` 与审计状态一致（操作失败被传播）；
- [ ] 合法领域负结论样本不被转为工具错误；
- [ ] 查询输出仅含白名单字段；参数严格解析；
- [ ] 无真实私密数据被读取或泄露的证据要求满足（夹具 + 标注）。

## 4. 依赖与顺序

- 无前置；F09/F16 同属公共 API 面，建议同批；F18 独立。

## 5. 文档任务

- `CHANGELOG.md`：beta1.2.2 条目；
- `docs/wiki/CLI-and-MCP.md` 若涉及 status 参数/失败语义说明则同步；
- 执行记录与总纲。

## 6. 工单

| 工单 | 覆盖 |
| --- | --- |
| `09-f09-f16-f18-public-surface-audit` | F09、F16、F18 |

## 7. 边界

- 全局边界按总纲第一节；HTTP 故障以 mock 验证，不接真实外部服务；
- 不得借 F16 修复扩展为史馆数据模型重构。

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
