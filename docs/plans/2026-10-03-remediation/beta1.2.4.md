# beta1.2.4 独立计划 · 安装恢复语义与首装说明

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：[beta1.2.3](./beta1.2.3.md)｜下一版：[beta1.2.5](./beta1.2.5.md)
> 依赖：[beta1.2.3](./beta1.2.3.md)｜被依赖：[beta1.3.2](./beta1.3.2.md)、[beta1.3.4](./beta1.3.4.md)（quickstart 引用首装路径）
> 工单：`11-f11-f21-recovery-semantics-first-install-docs`（本地工单 .scratch/remediation-2026-10/issues/）
> 权威依据：consolidated-review.md（仓库外只读，绝对路径见总纲文档地图；该类引用不参与仓库内链接校验）
> 条目：F11、F21

## 1. 版本目标

**恢复语义三态与实际状态一致**（F11）：只有核验恢复成功才标 `ROLLED_BACK`，否则 `RECOVERY_REQUIRED`；**首装说明可照做、可验收**（F21）：README/Wiki 的最快路径补上显式投影步骤，不改安装策略。

排期说明：F11 原属报告"统一绑定与结果事实"优先组，与同文件、同安装链的 F21（P3）合并本版，便于一次验收"恢复语义 + 首装说明"（偏移理由见总纲第二节）。

## 2. 修复条目

### 2.1 F11 · 可选配置修复未恢复仍返回 ROLLED_BACK（P2）

- 现象：可选配置修复未恢复或恢复失败时仍返回 `ROLLED_BACK`，实际变更保留。
- 位置：`scripts/install_current_agent_copy.py:2551`、`2724`。
- 修复要求：只有核验恢复成功才标回滚，否则 `RECOVERY_REQUIRED`（与 1.1.7 已建立的补偿语义一致，不新建框架）。
- 验收（可测）：
  - [ ] 恢复失败场景返回 `RECOVERY_REQUIRED` 并保留恢复材料；
  - [ ] 恢复成功场景返回 `ROLLED_BACK`；
  - [ ] 三态（ROLLED_BACK / RECOVERY_REQUIRED / INSTALLED）与实际状态逐例一致。
- 证据：故障注入对照（仅可选注入接缝；未发现默认公开生产 adapter 接入的事实须标注）。

### 2.2 F21 · 首次安装说明缺显式投影步骤（P3）

- 现象：`README.md:28` 与 Wiki Installation 的最快路径只有 `npm install` 后查 version；但 beta1.1.7 构建包没有自动 postinstall 投影，contract 要求显式安装器；普通命令要求已有 binding。
- 位置：`README.md:28`、`docs/wiki/Installation.md`。
- 修复要求：补对应包的显式投影步骤、参数与验收说明；**不改安装策略**；不把"后文原则"当作可执行步骤。
- 验收（可测）：
  - [ ] 按新说明在隔离环境照做可完成首装（附照做记录）；
  - [ ] 步骤与当前 CLI 实际参数一致（逐参数核对）；
  - [ ] 未回读远端 npm beta 时不得把该通道假定为 1.1.7。
- 证据：隔离环境照做记录 + 命令逐条对照。

## 3. 版本出口（Exit Criteria）

- [ ] 恢复三态逐例一致；首装说明照做通过；
- [ ] 与 1.2.3 的入口修复联合回归；
- [ ] 文档与命令面一致（无过期参数）。

## 4. 依赖与顺序

- 依赖 1.2.3（入口解析）；F21 的照做验证使用 1.2.3 修复后的入口。

## 5. 文档任务

- `README.md` + `docs/wiki/Installation.md`：首装显式投影步骤（本版核心交付）；
- `CHANGELOG.md`：beta1.2.4 条目；
- 执行记录与总纲。

## 6. 工单

| 工单 | 覆盖 |
| --- | --- |
| `11-f11-f21-recovery-semantics-first-install-docs` | F11、F21 |

## 7. 边界

- 全局边界按总纲第一节；不改安装策略、不改包内容；发布按总纲 26.1 在本版验收后执行；
- 首装照做在隔离 HOME/prefix/cache 中完成，不触用户现用安装。

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
