# beta1.2.6 独立计划 · 召回刷新与 LAN 下载

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：[beta1.2.5](./beta1.2.5.md)｜下一版：[beta1.2.7](./beta1.2.7.md)
> 依赖：无｜被依赖：[beta1.3.7](./beta1.3.7.md)（治理收益度量引用本版召回路径）
> 工单：`13-f14-f15-recall-refresh-lan-download`（本地工单 .scratch/remediation-2026-10/issues/）
> 权威依据：consolidated-review.md（仓库外只读，绝对路径见总纲文档地图；该类引用不参与仓库内链接校验）
> 条目：F14、F15

## 1. 版本目标

**动态索引刷新语义明确**（F14）：warm 召回与索引更新保持一致或明确快照语义；**LAN 下载走鉴权通道**（F15）：下载请求携带与列表一致的鉴权，失败时 UI 如实提示而非"正在下载"。

## 2. 修复条目

### 2.1 F14 · Laya warm recall 不检查 size/mtime stamp（P2）

- 现象：warm 召回不检查已存在的 size/mtime stamp；合成索引 1→2 行后仍查到旧 1 行，显式 rebuild 后才更新，与"自动失效/实时索引"说明不符。
- 位置：`training/laya-shiguan/service/shiguan_recall.py:207`、`258`。
- 修复要求：warm 查询复用已有 stamp 刷新；或明确快照语义（二选一并写入文档）；**不加 hash 机制**。
- 验收（可测）：
  - [ ] 索引文件更新（size/mtime 变化）后 warm 查询返回新结果，或按声明的快照语义给出稳定结果；
  - [ ] 文档与实现一致（把语义写进 service README）；
  - [ ] 不引入摘要/校验脚本。
- 证据：索引更新前后查询结果对照（ML 为桩，不得宣称模型效果）。

### 2.2 F15 · LAN 导出下载不带 admin header（P2）

- 现象：LAN 导出列表 fetch 带 admin header，但下载用普通 anchor 无法携带同一 header；后端仍要求该 header，导致列表成功、下载被拒绝，而 UI 提示"正在下载"。
- 位置：`web/shiguan-tree/app.js:4730`；`scripts/services/serve_shiguan_tree.py:2441`。
- 修复要求：授权 fetch 取得 Blob 再触发下载，保留后端鉴权；失败路径给出明确提示（区分"无权限"与"下载中"）。
- 验收（可测）：
  - [ ] 无鉴权时下载被明确拒绝且 UI 显示真实原因；
  - [ ] 有鉴权时下载成功（隔离后端对照）；
  - [ ] 不降低后端鉴权要求。
- 证据：前后端分层夹具对照（现有 repro 有 `shangshu-key-download-*` 两组）；无真实密钥/浏览器 LAN 验证时标注。

## 3. 版本出口（Exit Criteria）

- [ ] F14：索引更新后查询正确（或快照语义成文）；
- [ ] F15：鉴权下载路径成立、失败可见；
- [ ] 两项均不含 hash 机制新增。

## 4. 依赖与顺序

- 无前置；F14 属训练/服务目录，F15 属 web + 服务，相互独立。

## 5. 文档任务

- `training/laya-shiguan/service/README.md`：快照/刷新语义说明；
- `CHANGELOG.md`：beta1.2.6 条目；
- 执行记录与总纲。

## 6. 工单

| 工单 | 覆盖 |
| --- | --- |
| `13-f14-f15-recall-refresh-lan-download` | F14、F15 |

## 7. 边界

- 全局边界按总纲第一节；不跑真实模型训练；不接真实 LAN 外部环境（隔离对照）。

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
