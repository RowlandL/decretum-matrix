# beta1.2.2 独立计划 · 公共接口与审计

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：[beta1.2.1](./beta1.2.1.md)｜下一版：[beta1.2.3](./beta1.2.3.md)
> 依赖：无｜被依赖：[beta1.2.6](./beta1.2.6.md)、[beta1.2.8](./beta1.2.8.md)、[beta1.2.9](./beta1.2.9.md)、[beta1.3.1](./beta1.3.1.md)
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

## 2026-11-01 计划增补 · 统一决策契约与宿主回退

状态：**PLANNED_UNVERIFIED**。本次仅修订计划；新增项的实施与晋级按本版出口，不将历史发布条款当作本次发布授权。

详见[统一需求、架构与版本矩阵](../2026-11-01-memory-decision-gateway-roadmap.md)，本节和原F/E条目共同构成本版工作范围；原缺陷修复不因模型研究而被无界阻塞。

1. 在既有公共API定义决策位置、合法候选、provider、abstain、错误和回退原因的兼容投影，覆盖派遣、复用、能力、模型、流程及记忆判断。
2. 区分本地模型的业务否定、不能判断与服务故障；宿主接续使用相同契约，保持元数据白名单。
3. 本版只收口入口与契约，不借F16扩为数据模型或执行器重写。

增补验收：

- [ ] 规则正例、合法否定、abstain、宿主接续及非法候选的公开入口对照可回放；不以mock证明Laya质量。
- [ ] 新能力的源码、模型效果、真实宿主及缓存证据分别记录；尚未实施项不得填写成功结果。

## 职责与名称增补 · 职责与统一任务结构契约

状态：**PLANNED_UNVERIFIED**。依据用户最新澄清：具体职责参考历史史实，并必须适应现代智能体；此前口述职务与CEO/COO例子不构成固定映射。

共用[史实、现代职责与名称解耦计划](../2026-11-01-office-duties-and-name-decoupling-plan.md)，复用既有身份包设计；本节不增加新的版本依赖或当前实施/发布授权。

1. 按唐制史实分工定义现代职责、实际实例与显示名的分离投影；沿既有role_key/profile/assignment，不新建身份权威。
2. 中书需求/计划/文书共用目标、来源、职责边界、工作依赖、交付验收、交接恢复的语义骨架；按任务选择工程/研究/文书等扩展，不能覆盖授权。

- [ ] 公共契约兼容、任务扩展有界；标题/CEO/COO/人名不能生成角色或执行权。

## 8. 执行记录

| 日期 | 动作 | 证据位置 | 结果 |
| --- | --- | --- | --- |
| 2026-11-01 | F09 公共入口失败传播 | `scripts/court_public_api.py`（`_operation_result`、`_contract_failure`）、`scripts/court_mcp_server.py`（`_operation_failure`）；用例 `f09_recall_failure_propagates_to_tool_result`、`f09_recall_healthy_result_stays_success`、`f09_recall_transport_exception_fails_closed`、`f09_contract_error_is_journaled_as_error`、`f09_domain_negative_is_not_a_tool_error` | 源码级完成；故障为 mock 对照，未连接真实召回服务；未分类客户端异常在公共 API 内失败关闭，审计经 `handle()` 实际写入路径回放 |
| 2026-11-01 | 公共输入/契约错误与合法否定分离 | `court_public_api._contract_failure`；用例 `decision_illegal_candidate_rejected`（非法候选 → 非零 exit_status / isError / 审计 error）、`f09_domain_negative_is_not_a_tool_error`（规则否定 → 正常诊断） | 源码级完成；分类依据为"输入是否违反公共契约"，非法候选不再套用合法否定豁免 |
| 2026-11-01 | F16 旧 query 复用白名单投影 | `scripts/court_public_api.py`（`shiguan_query`）；用例 `f16_legacy_query_uses_metadata_whitelist`（夹具故意逆序，证明保留匹配顺序而非重排） | 源码级完成；排序与 envelope 不变，隔离夹具验证，未读真实正文 |
| 2026-11-01 | F18 status 严格参数解析 | `scripts/court_cli_registry.py`（`_parse_status_arguments`、`_court_status_help`）；`check_unified_cli.py --court-status` | 源码级完成；help 静态且不触达状态后端，compact/limit 正例保持 |
| 2026-11-02 | R1/R4 决策元数据严格化（Codex REQUEST_CHANGES 整改） | `court_public_api._strict_text`/`_strict_candidates`/`_strict_candidate`/`_strict_evidence_refs`；用例 `decision_candidate_object_rejected_without_public_body`、`decision_candidate_above_max_text_rejected`、`decision_candidate_non_string_rejected`、`decision_evidence_refs_preserved_verbatim`、`decision_evidence_ref_above_max_rejected`、`decision_evidence_ref_non_string_rejected` | 源码级完成；候选与固定文本必须为有界字符串，证据引用 512 字符上限且逐字保留，非法输入按契约错误传播 |
| 2026-11-02 | R2/R3 决策续办出口（同一整改） | `court_public_api._pause_exit`/`_host_continuation`；用例 `decision_host_model_failure_pauses_not_reroutes`、`decision_host_model_abstain_pauses`、`decision_uncalibrated_local_model_downgrades_to_abstain`、`decision_calibrated_local_and_rule_verdicts_unchanged` | 源码级完成；宿主失败/宿主 abstain 为有界暂停出口，未校准本地判决规范为 abstain+not_calibrated；规则与已校准本地正例不变 |
| 2026-11-01 | 决策契约增补 | `court.decision_contract` / `court.decision_project`；用例 `decision_rule_positive_projects_bounded_fields`、`decision_legal_negative_stays_diagnostic`、`decision_abstain_requires_host_continuation`、`decision_host_handoff_reason_projected`、`decision_illegal_candidate_rejected` | 源码级完成；模型效果/真实宿主/缓存均 `NOT_RUN`，保持 `PLANNED_UNVERIFIED` |
| 2026-11-01 | 职责与统一任务结构增补 | `court.office_duty` / `court.task_skeleton`；用例 `office_duty_reuses_existing_hierarchy_authority`、`office_duty_reads_standing_profile_authority`、`task_skeleton_keeps_six_semantic_slots`、`task_extension_is_bounded`、`title_or_person_name_confers_no_role_or_dispatch_edge` | 源码级完成；职责正文/官署名取自既有 standing profile，层级边取自既有派遣清单且漂移即失败关闭；不新建身份表；显示名/CEO/COO/人名不产生权限或派遣边 |
| 2026-11-02 | release-gate 报告层修复（Codex REQUEST_CHANGES 收尾） | `scripts/checks/check_release_gate.py`（`failed_entry_label`/`format_failure_line`/`exit_code_for`/`run_failure_report_self_test`）；`--self-test` 用例 `failure_report_name_only`/`id_only`/`no_label`/`no_detail`/`exit_code` | 失败文本同时容纳 step 的 `name` 与 required-check 的 `id`，不再 `KeyError`；判断逻辑与退出码语义（0/2）不变，自测 21 例通过 |
| 2026-11-02 | phase 失败矩阵与行尾收敛（同一收尾） | 回执 `<TEMP>/dm-beta122-gate-matrix-2026-11-02.json`（13 条 source 失败逐条 phase/name/gate_class/command/exit/problems/log）；日志 `<TEMP>/srcgate.json`、`<TEMP>/c2gate.json` | source 阶段 13 项已分类：6 项 installation binding 缺失、2 项步骤超时（300s/180s）、1 项控制台编码、1 项 git dubious ownership、1 项 UNC 冷启动性能、1 项字节码残留（清理 `__pycache__` 后单项 exit 0）；default full 的 package/install 缺失为未打包条件，不计源码断言 |
| 2026-11-02 | GitHub Packages publisher 工作流（Codex 阶段裁定后） | `.github/workflows/publish-packages.yml` | 仅 `release: published`（或手动 dispatch）触发；严格校验 tag/仓库/VERSION/SKILL/plugin/manifest/包名/registry/派生版本；要求同提交 `ci.yml` 全部 job 成功；消费 Release 既有资产（sidecar 校验 + tgz 身份校验），不重新构建；同版本已存在时仅 integrity 相同才跳过、不同即拒绝；发布限 `--tag beta` 到 npm.pkg.github.com；permissions 仅 contents:read/actions:read + 发布 job 的 packages:write；未改 ci.yml。本地仅静态校验（PyYAML 解析、run 块无表达式与 secrets），未运行、未提交 |
| 2026-11-02 | installer 深路径修复（Codex 授权整改） | `scripts/court_diagnostics.py`（原子临时名改为同目录 `.UUID.tmp`）、`scripts/checks/check_doctor_debug_fix.py`（`deep_event_path_atomic_write_succeeds`） | RED：event_dir 180 字符、旧临时名 281 字符 → FileNotFoundError；GREEN：final 246 字符内写入成功，intent/result 两事件 schema 正确、event_id 不同、payload 不覆盖、无临时残留；pristine fixture 基线同样 3 项失败，本次不扩大修复 |
| 2026-11-01 | 回归与门禁 | 见 `CHANGELOG.md` beta1.2.2「Validation boundary」：`check_court_mcp_server.py`（99 项）、`check_read_only_contract.py`、`check_unified_cli.py` 四项、`check_catalog.py`、`check_court_result_semantics.py`、`check_court_dispatch_hierarchy.py`、`check_court_office_assignment_binding.py`、`check_court_office_bootstrap.py`、`git diff --check` | 全部实际通过；未安装/未发布/未 push，索引保持为空待审查 |

> 上述条目均为 SOURCE 级实现与隔离回归。第二、三节的条目复选框按发布出口保留，需门下复核与 CI/发布回执后才能勾选；本节不代替发布验收。

## 发布与 CI 验证（按总纲 26.1）

- 本版验收通过后执行：推送到 GitHub、GitHub Release、npm 包发布（版本号 = 本版号）；
- 以既有 GitHub Actions CI 验证；**CI 内容默认不改动**（不放宽门禁、不为过审修改检查集合）；
- 仅当 CI 验证确实不可行时提出调整并经用户同意；发布前核对 workspace.yaml 的 publication_gates；
- 发布证据（Release / npm / CI 回执）记入执行记录。

---

*本计划由总纲派生；修改需同步总纲第二节与交叉引用关系。*
