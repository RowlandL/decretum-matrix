# beta1.0.9 与项目框架的实现对照

- 观察日期：2026-09-05。
- 源码分支：`release/beta1.0.9`。
- 被审查提交：`0003b3800cd245abf870a82ff464a802cc0faeaf`。
- 依据：[项目框架](../wiki/Architecture.md)及[原始 Markdown](README.md)。
- 证据来源：同一会话的串行源码审查、仓库检查和临时目录内的合成探针。

本文记录该提交的观察结果，供实现与验收定位。架构文档归位本身不修复这些问题，
也不构成当前宿主完整官署履职或发布就绪证明。后续代码变更应更新对照结论与验证
证据，保留历史观察的提交边界。

用户后续裁定：核心架构大方向不变时，以新版本细节为准，包含 MCP 与三省细化。
A02 的中间状态可推进不单独构成修复理由，须检查最终履职表达是否虚报；A03 的
三类内部枚举也不直接判为错误，须先查新版本是否有保留余险／返工语义的适配路径。
两项在计划中作为语义衔接裁定，不预设恢复旧状态机或旧接口。A01、A04–A07 则以
实际失败、数据一致性或错误传播证据决定整改。

## 已对齐的部分

| 框架要求 | 已观察实现 |
| --- | --- |
| 太子受旨定性在三省会审之前 | `SKILL.md`、`court open` 帮助与 runtime docstring 已纠正职责表述；1.0.9 直接变更为文档／帮助层 |
| 太子→三省、尚书→六部的直接上级关系 | `check_court_dispatch_hierarchy.py` 正反例通过 |
| 会话分类与不一致输入拒绝 | `check_court_intake_gate.py` 通过，包含 11 个通过例、32 个拒绝例与置信度变异检查 |
| P00 有界语义上下文 | `check_p00_semantic_dispatch_context.py` 通过 |
| 泛化自由文本不能直接完成 schema v3 任务 | `check_court_runtime_completion.py` 18 项检查通过，包含结果绑定、完成事务和恢复 |
| 只读探针不改共享状态 | `check_read_only_contract.py` 通过，包含临时共享根和 pending metadata-only 验证 |
| MCP 公共面与召回基线 | `check_court_mcp_server.py` 与 `check_shiguan_recall_precision.py` 通过 |

中书的“问题拆解／拟旨”与尚书的“从结果倒推执行差遣”同时成立。不能把 1.0.9
对太子职责的纠正解释成取消尚书的差遣拆解与系统级统合责任。

## 仍存在的差异与健壮性问题

### A01：1.0.9 文档增长使官署预载超限

- 定位：`SKILL.md`；`scripts/commands/court_open_fastpath.py` 的 `prepare_fast_open`。
- 分类：1.0.9 新回归。
- 预期：入口、dossier/profile 与紧凑 metadata 合计不超过 20,480 字节。
- 观察：相对 `37df40d`，`SKILL.md` 从 13,532 增至 14,668 字节，增加 1,136 字节；
  九个官署全部超限，中书 20,918、门下 20,986、尚书 21,232 字节，其他六部为
  21,111–21,236 字节。`check_court_open_fastpath.py` 的 `source_preload_target`
  失败；准备路径会返回 `preload_budget_exceeded`。
- 验收方向：保持完整职责语义与 20 KiB 合同，按需分层加载后验证实际官署预载。

### A02：中间流程状态不足以证明官署履职

- 定位：`scripts/court_runtime.py` 的 `validate_runtime_gate` / `apply_transition`。
- 分类：待按新版本语义裁定的职责证据衔接点，不因中间状态可记录就新增门禁。
- 预期：三省上奏、六部办差和门下复核有实际回奏或明确的 `serial_inline` 依据。
- 观察：在临时 runtime 中创建合法任务并取得语义 `DISPATCHABLE` 后，全部使用
  `actor=taizi`、空 evidence，可以依次推进至 `ThreeDepartmentsPetition`、
  `ShangshuDispatch`、`SixMinistries`、`Workshops`、`MenxiaReview`，没有官署投递、
  回奏或 `serial_inline` 记录。该探针只证明中间状态可推进，不证明能绕过 `Done`。
- 验收方向：明确中间状态的机器事实边界，绑定官署履职证据或如实报告降级，避免
  将状态名当成原流程已经执行的证据。

### A03：五类门下裁定未完整贯通运行时

- 定位：`scripts/court_outcome_gate.py`；`scripts/court_runtime.py` 的
  `OUTCOME_ASSESSMENT_GATES` / `validate_runtime_assessment_binding`。
- 分类：已确认的内部接口差异；是否属于用户行为缺陷须检查新版本映射。
- 原始要求：详细实施方案 §1.3 明确 `PASSED_WITH_CONCERNS` 可归档并形成
  `DONE_WITH_CONCERNS`；`RETURN_FOR_REWORK` 返回复核、尚书或三省路径。
- 观察：结果评估模块保留五类裁定；runtime 只接受 `PASSED / PARTIAL / BLOCKED`。
  同一合法绑定分别使用另两类时，均得到 `invalid_outcome_assessment_gate`。
  使用 `Pending` 状态绑定评定则被 `assessment_binding_requires_menxia_review`
  正确拒绝，不能将 A02 扩大描述为任何阶段都可完成结果绑定。
- 验收方向：在复用现有状态机的前提下，贯通五类裁定的绑定、回退、归档和最终表达。

### A04：领域账册 Git 事务未隔离既有暂存内容

- 定位：`scripts/domain_ledger_api.py` 的 `_git_commit` / `domain_ledger_write`。
- 分类：继承的事务健壮性问题。
- 观察：临时 Git 仓库中预先暂存 `unrelated.txt`，一次合法账册写入把该文件与
  `domain-ledger/memory.json` 一起提交。强制下一次 commit 失败后，工作文件恢复
  旧 revision，但索引中仍含失败的新 revision。成功路径写回 `git_commit` 后，
  账册工作文件也留有未提交变更。
- 验收方向：以授权写集为单位隔离 Git 提交，失败恢复文件与索引，明确 receipt
  持久化和仓库状态的一致性。

### A05：冲突裁定写失败被顶层成功状态掩盖

- 定位：`scripts/commands/closeout_conflict_scan.py` 的 `apply_decisions` / `main`。
- 分类：继承的错误传播问题。
- 观察：`authority=approval` 的一次确定性裁定写入被底层正确拒绝，顶层却返回
  `ok:true, applied:0, receipt_count:1`；CLI 在 apply 后固定返回退出码 0。
- 验收方向：完整传播拒绝、部分成功和失败，使调用者不会把未落地裁定视作已完成。

### A06：主运行时回归测试的路径定位错误

- 定位：`scripts/checks/check_court_runtime.py` 的 `_instance_start_args`。
- 分类：继承的测试路径回归。
- 观察：以 `court_runtime.__file__` 的 `parents[2]` 定位 `SKILL.md`，实际越出产品
  根目录，发生 `FileNotFoundError`。测试在 instance-keyed consumption 检查中退出。
- 验收方向：从实际模块位置解析产品根，整项运行时检查执行到结束。

### A07：公开命令与安装投影不闭合

- 定位：`references/manifests/cli-command-surface.v1.json`、
  `references/manifests/install-projection.v1.json`、
  `scripts/checks/check_release_manifest.py`、`scripts/commands/build_release_artifacts.py`。
- 分类：继承的入口分类与依赖投影差异。
- 观察：统一 CLI 检查发现公开的 `scripts/checks/check_active_copy_hashes.py`
  不在运行投影中；投影闭包检查报告两种安装目标均遗漏被投影脚本依赖的
  `check_release_gate.py` / `release_payload_manifest.py`。按安装清单在临时目录
  投影 Python 文件后，`check_release_manifest.py --help` 因缺少
  `release_payload_manifest` 发生 `ModuleNotFoundError`。
- 验收方向：统一 source-only 与 installed public 的分类，并使实际安装入口的依赖闭合。

## 检查摘要

以下为上述提交的本地审查结果，共 13 项，9 项通过、4 项失败。
所有命令从产品仓根运行，以 `python -B scripts/` 加下列脚本名调用。

| 检查 | 结果 |
| --- | --- |
| `quick_validate.py .` | 通过 |
| `check_context_compression_survival.py --json` | 通过 |
| `check_court_intake_gate.py` | 通过 |
| `check_court_dispatch_hierarchy.py` | 通过 |
| `check_court_runtime.py` | 失败，A06 |
| `check_court_runtime_completion.py` | 通过 |
| `check_read_only_contract.py` | 通过 |
| `check_court_mcp_server.py` | 通过 |
| `check_shiguan_recall_precision.py --json` | 通过 |
| `check_court_open_fastpath.py` | 失败，A01；串行探针定位到同一预载问题 |
| `check_p00_semantic_dispatch_context.py` | 通过 |
| `check_unified_cli.py --all` | 失败，A07 |
| `check_install_projection_closure.py` | 失败，A07 |

框架符合度结论：主干职责说明基本对齐，结构化完成较原始整改前已有实质改善；
官署履职证据、五类裁定衔接及上述健壮性问题仍需完成对应实现和验收。
