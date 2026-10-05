# beta1.2.7 独立计划 · 前言解析一致性

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：[beta1.2.6](./beta1.2.6.md)｜下一版：[beta1.2.8](./beta1.2.8.md)
> 依赖：无｜被依赖：[beta1.3.5](./beta1.3.5.md)（去 PyYAML 评估的一致性基线）
> 工单：`14-f17-frontmatter-parser-parity`（本地工单 .scratch/remediation-2026-10/issues/）
> 权威依据：consolidated-review.md（仓库外只读，绝对路径见总纲文档地图；该类引用不参与仓库内链接校验）
> 条目：F17

## 1. 版本目标

同一前言（frontmatter）在**有无 PyYAML** 的环境下判定一致：重复键等边界规则两后端统一；复杂 YAML 的支持边界保持不变并明确提示。

## 2. 修复条目

### 2.1 F17 · 两后端重复键规则相反（P2）

- 现象：PyYAML 覆盖重复键、精简 parser 拒绝，同一普通前言随可选依赖得到相反结果。
- 位置：`scripts/commands/quick_validate.py:50`。
- 修复要求：两后端统一重复键规则（建议统一为拒绝并给出明确诊断，与精简 parser 的既有安全边界一致）；保持复杂 YAML 的支持边界（复杂语法仍提示需 PyYAML）；无需另写完整 YAML 引擎。
- 验收（可测）：
  - [ ] 重复键、错误缩进、空描述、非法 metadata 等负例在两后端结果一致；
  - [ ] 复杂 YAML 在无 PyYAML 时给出"需 PyYAML"的明确提示，不误报通过；
  - [ ] 合法前言（含 `metadata.author/version`、`compatibility`）两后端均通过。
- 证据：同一夹具在两后端（有/无 PyYAML）的判定对照表。

## 3. 版本出口（Exit Criteria）

- [ ] 两后端判定一致（逐例对照）；
- [ ] 支持边界文档化（哪些语法需要 PyYAML）；
- [ ] 不引入新的 YAML 实现。

## 4. 依赖与顺序

- 无前置；本版是 1.3.5 评估的一致性基线。

## 5. 文档任务

- `CHANGELOG.md`：beta1.2.7 条目；
- 若 `quick_validate` 的说明散落于 references，统一补"两后端一致 + 复杂 YAML 需 PyYAML"的边界句；
- 执行记录与总纲。

## 6. 工单

| 工单 | 覆盖 |
| --- | --- |
| `14-f17-frontmatter-parser-parity` | F17 |

## 7. 边界

- 全局边界按总纲第一节；不做完整 YAML 引擎（属 1.3.5 评估范围）。

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
