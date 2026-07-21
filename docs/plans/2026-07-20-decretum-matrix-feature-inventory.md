# Decretum Matrix 功能与脚本清单

状态：`CURRENT_TASK0_DRAFT`

本文件是任务 0 的功能保全和候选脚本清单。它不把 `beta1.0.1` 中新增文件的存在视为保留理由，也不把 `beta0.5.9` 的旧内部名称视为必须永久兼容。保留对象是 `beta0.5.9` 已有能力、用户明确新增功能、历史数据读取/迁移能力和当前有独有有效输出的功能。

## 1. Git 对象与规模统计

| 指标 | `beta0.5.9` | 当前 HEAD | 差异 |
| --- | ---: | ---: | ---: |
| tracked files | 206 | 325 | +119 |
| `scripts/` 文件 | 115 | 167 | +52 |
| `check_*` 脚本 | 43 | 69 | +26 |
| `references/manifests/` | 2 | 9 | +7 |
| Python scripts | 112 | 162 | +50 |
| Node scripts | 0 | 2 | +2 |

命令证据：

```powershell
git rev-list -n 1 beta0.5.9
git diff --name-status beta0.5.9..HEAD
```

当前确认：

```text
beta0.5.9 commit=040f707e5acc7c12cfcf50afcfc111a7e49a2f00
HEAD=9774a1415b906b357985e462e74efaf842f45602
```

## 2. `beta0.5.9` 受保护能力清单

| 能力组 | 0.5.9 证据 | 当前处置 |
| --- | --- | --- |
| 诏令/三省六部运行 | `SKILL.md`、`court_runtime.py`、`court_dispatch_policy.py`、`court_office_bootstrap.py` 已存在 | 保留全部行为能力；可减默认成本，不删除语义 |
| 太子场景与任务路由 | `court_runtime.py` 与 court references 已有正式/闲聊/历史召回描述 | 由 `court_intake_gate.py` 结构化承接，禁止文字特化 |
| 史馆 Markdown 归档 | `scripts/archive_checkpoint.py` 已存在 | 保留；普通路径不得强制额外 release/install 检查 |
| 史馆索引与召回 | `scripts/query_shiguan_index.py`、`shiguan-index.jsonl` 规则已存在 | 保留基础召回；GBrain 是默认智能查询层，基础 scorer 是 fallback |
| 记忆裁定 | `scripts/memory_decision.py`、`scripts/reevaluate_memory_decisions.py` 已存在 | 保留，GBrain 可整理但不替代 |
| 史馆整理 | `scripts/tidy_shiguan_records.py` 已存在 | 保留人工可读/可改前提 |
| 树/图派生层 | `scripts/grow_shiguan_tree.py`、`scripts/build_shiguan_knowledge_graph.py` 已存在 | 保留可重建能力；不得因提速删除 |
| Web/树浏览 | `scripts/serve_shiguan_tree.py`、`web/shiguan-tree/*` 已存在 | 保留显式 Web 能力 |
| Obsidian preserve-only 同步 | `scripts/sync_shiguan_obsidian_vault.py` 等已存在 | 保留显式同步，不进入闲聊/轻量路径 |
| superCC 独立运行 | `agents/supercc-dossiers/*`、superCC 脚本已存在 | 保留独立入口；桌面不作标准验收 |
| 安装/发布/隐私/法律检查 | release/check/package 脚本已存在 | 属项目级能力，不写入 Skill 功能定义 |

## 3. 用户明确新增或明确要求保留的功能

| 功能 | 证据 | 处置 |
| --- | --- | --- |
| GBrain | 用户明确附加；当前 `scripts/shiguan_gbrain.py` 新增 | `KEEP_EXPLICIT`；作为史馆智能查询、recall/advisory 与只读沉淀/整理候选层，不取代史馆记录本体 |
| Git 联邦 | 用户说明用于史馆管理；当前 `scripts/shiguan_git_federation.py` 新增 | `KEEP_EXPLICIT`；可由 GBrain 显式整理/管理模式触发，不进入普通轻量/开朝隐式链 |
| 官署名称与语义胶囊 | 用户明确说明其来源；当前 `agents/office-dossiers/*`、`court_office_bootstrap.py`、`court_office_config.py` | `KEEP_EXPLICIT`；可减文件/哈希成本，不删身份能力 |
| 诏令绑定 | 用户明确认可；当前 semantic continuity/admission 相关脚本 | `KEEP_EXPLICIT`；invalid revision 必须零差遣 |
| 单会话主动结诏 | 用户明确要求；当前 `court_session_closeout*` 已通过任务 3 focused RED/GREEN | `KEEP_EXPLICIT`；只汇总当前会话未结诏内容，cursor 由 session_id 派生，不接受公开 request 指定任意本地 cursor |
| 项目目录外运行 | 用户明确要求 | `KEEP_EXPLICIT`；需修 cwd/root/user-data 三根边界 |

## 4. 当前 HEAD 的关键变更事实

| 项 | 当前事实 |
| --- | --- |
| CLI surface | `references/manifests/cli-command-surface.v1.json` 当前有 129 entries；运行 registry 跳过 `root/decretum-matrix` 包装记录后有效记录为 128；日常 help 面为 32 行，完整 compatibility adapter 仍可显式调用 |
| Release gates | `references/manifests/release-gates.v1.json` 有 50 steps，timeout 合计 9180 秒 |
| Fast open / 尚书统六部 | 当前 focused gate 证明并行时尚书选择六部、向六部子/孙官署下达职责、汇总证据并回奏；六部 caller/direct_superior 均为尚书；capability snapshot 在三省审议前完成 |
| CLI cwd | `scripts/court_cli_registry.py` 当前按命令组区分 cwd：`court/shiguan/install` 使用调用者目录，`check/release` 使用代码根 |
| GBrain 召回/整理候选 | `scripts/query_shiguan_index.py` 默认通过 GBrain 做智能排序/召回，`shiguan_entry_utils.py` 保留基础 fallback；`shiguan_gbrain.py` 提供只读 settlement candidates，并可在显式整理/管理模式触发 Git 联邦 provenance |
| Archive receipt/hash | `scripts/archive_checkpoint.py` 仍计算 `archive_sha256` 和 `receipt_sha256`；普通会话结诏不得在未授权时额外富化 |
| npm launcher | `bin/decretum-matrix.py` 正常路径优先使用同版本 canonical runtime；仅 canonical 缺失/版本不符/不完整时才进入 verified TEMP fallback；`--npm-postinstall` 仍走 verified archive |

## 5. 新增或大幅改写候选集

### 5.1 新增运行/功能脚本

| 脚本 | 初始分类 | 处置 |
| --- | --- | --- |
| `scripts/court_intake_gate.py` | `VALUE_EXPLICIT` | `KEEP_EXPLICIT`，但需证明无文字特化、闲聊不自动结诏 |
| `scripts/court_open_fastpath.py` | `VALUE_EXPLICIT` | `MERGE_FUNCTION`，保留 fast open、尚书统六部和必要六部职责；并行 receipt 必须体现尚书统筹计划、六部子/孙官署下派以及六部 caller/direct_superior 均为尚书；清理错误 cwd、无关 Git/过量 hash，不删除六部能力 |
| `scripts/court_cli_registry.py` | `VALUE_EXPLICIT` | `MERGE_FUNCTION`，保留统一 CLI，收窄 public surface 和 cwd 语义 |
| `scripts/court_office_config.py` | `VALUE_EXPLICIT` | `KEEP_EXPLICIT`，保留中性官署配置 pointer |
| `scripts/court_dispatch_hierarchy.py` | `VALUE_EXPLICIT` | `KEEP_EXPLICIT`，保留层级约束 |
| `scripts/court_agent_admission.py` | `VALUE_EXPLICIT` | `MERGE_FUNCTION`，只用于真实并行/差遣，不进入闲聊/轻量 |
| `scripts/court_agent_admission_contract.py` | `VALUE_PROJECT_ONLY` | 保留为开发/验收合同，禁止普通运行前置 |
| `scripts/court_capability_recruitment.py` | `VALUE_EXPLICIT` | 保留能力建议；不自动派生 libu-hr |
| `scripts/court_native_execution.py` | `VALUE_EXPLICIT` | `KEEP_EXPLICIT`，native 与 superCC 分离 |
| `scripts/court_supercc_execution.py` | `VALUE_EXPLICIT` | `KEEP_EXPLICIT`，superCC 独立入口 |
| `scripts/court_result_semantics.py` | `VALUE_EXPLICIT` | `KEEP_EXPLICIT`，结果语义需保留 |
| `scripts/court_semantic_continuity.py` | `VALUE_EXPLICIT` | `KEEP_EXPLICIT`，invalid revision 零差遣 |
| `scripts/court_operation_journal.py` | `VALUE_HISTORY` | `KEEP_PER_TASK_ONLY`；运行历史能力保留，但不得成为共享 mutable ledger 或普通轻量路径前置 |
| `scripts/court_complexity_budget.py` | `VALUE_PROJECT_ONLY` | 项目维护面，不能是 Skill 启动条件 |
| `scripts/court_safe_fs.py` | `VALUE_PROJECT_ONLY` | 安全工具保留；按调用者决定 |
| `scripts/court_safe_fs_windows.py` | `VALUE_PROJECT_ONLY` | 安全工具保留；按调用者决定 |
| `scripts/governance_framework.py` | `VALUE_DUPLICATE` | 不进入默认三省六部；参考治理能力若无生产调用则下沉/移除 |
| `scripts/shiguan_gbrain.py` | `VALUE_EXPLICIT` | `KEEP_EXPLICIT`；GBrain 作为史馆默认智能查询层和只读整理/沉淀候选层，无当前任务执行/写入权 |
| `scripts/shiguan_git_federation.py` | `VALUE_EXPLICIT` | `KEEP_EXPLICIT`，显式史馆管理 |
| `scripts/shiguan_host_memory_projection.py` | `VALUE_HISTORY` | 只读/迁移职责待任务 2 确认 |
| `scripts/shiguan_migration_gate.py` | `VALUE_HISTORY` | 旧数据迁移职责待任务 2 确认 |
| `scripts/install_current_agent_copy.py` | `VALUE_PROJECT_ONLY` | 安装阶段保留，不进入普通 Skill |
| `scripts/build_npm_package.mjs` | `VALUE_PROJECT_ONLY` | npm 项目工程保留 |
| `scripts/supercc_dispatch_contract.py` | `VALUE_EXPLICIT` | superCC 显式路径保留 |
| `scripts/supercc_dispatch_delivery.py` | `VALUE_EXPLICIT` | superCC 显式路径保留 |

### 5.2 新增或大幅改写 checker 候选

以下候选默认不进入普通 Skill 运行链；其价值只在 RED/GREEN、维护或项目发布阶段判断。

| 类型 | 数量 | 当前处置 |
| --- | ---: | --- |
| `check_*` 总候选 | 58 个 diff 中 check 脚本 | `VALUE_PROJECT_ONLY` 或 `VALUE_EXPLICIT` focused；不得作为闲聊/开朝前置 |
| 新增 startup/fastpath checker | `check_startup_fastpath_contract.py`、`check_court_open_fastpath.py`、`check_cli_performance.py` | 用于任务 1/4/8 验收；性能 checker 不得使用替身结果代替真实场景 |
| 新增 CLI/npm checker | `check_unified_cli.py`、`check_npm_package.mjs` | 用于任务 5/9；普通 help 不应暴露全部 check 命令 |
| 新增 GBrain/Git checker | `check_shiguan_git_federation.py`、`check_shiguan_host_memory_and_child_trace.py`、`check_shiguan_migration_gate.py` | 显式史馆管理/迁移验收，不进入基础召回 |
| 新增 P00/semantic checker | `check_p00_semantic_dispatch_context.py`、`check_semantic_continuity.py` | 保留 revision fail-closed 能力；过量 hash/trace 不得进入轻量场景 |
| release/legal/privacy checker | `check_release_*`、`check_package_privacy.py`、`check_install_*` | 项目级能力，任务 9 才运行 |

### 5.3 新增 manifest 候选

| Manifest | 初始分类 | 处置 |
| --- | --- | --- |
| `references/manifests/cli-command-surface.v1.json` | `VALUE_EXPLICIT` | 保留 registry 数据，但 public surface 需收窄 |
| `references/manifests/court-dispatch-hierarchy.v1.json` | `VALUE_EXPLICIT` | 保留层级事实 |
| `references/manifests/direct-review-governance.v1.json` | `VALUE_DUPLICATE` | 不进入默认生产三省六部 |
| `references/manifests/governance-implementations.v1.json` | `VALUE_DUPLICATE` | 不得改变默认官方实现；任务 2 判定是否下沉 |
| `references/manifests/install-projection.v1.json` | `VALUE_PROJECT_ONLY` | 安装阶段保留 |
| `references/manifests/github-release-metadata.v1.json` | `VALUE_PROJECT_ONLY` | 发布阶段保留 |
| `references/manifests/skill-identity.v1.json` | `VALUE_PROJECT_ONLY` | 安装/发布身份验证；不进入普通启动 |
| `references/manifests/release-gates.v1.json` | `VALUE_PROJECT_ONLY` | 发布阶段保留 |
| `references/manifests/source-state-budget.v1.json` | `VALUE_PROJECT_ONLY` | 项目维护面 |

## 6. 当前隔离 diff 审查

| 文件 | 当前事实 | 任务 0 结论 |
| --- | --- | --- |
| `scripts/court_intake_gate.py` | 增加 `EXPLICIT_CLOSEOUT`、`SESSION_CLOSEOUT`，且 `require_new_formal_task_gate()` 当前仍要求 `understanding.score>=95` 与 `route=DIRECT_EXECUTION` | `KEEP_EXPLICIT`；`check_court_intake_gate.py` 与 `check_governance_framework.py` 均通过 |
| `scripts/check_court_intake_gate.py` | 增加 closeout positive/negative cases，并覆盖 formal understanding 负例 | `KEEP_FOCUSED_CHECK_ONLY`；不得进入普通 Skill 运行链 |
| `scripts/court_cli_registry.py` | `court closeout-session` 入口已进入 CLI manifest；cwd 已按调用者目录/代码根分层 | `KEEP_EXPLICIT`；`check_unified_cli.py --all --json` PASS |
| `scripts/court_session_closeout.py` | 新脚本包含会话聚合、session 派生 cursor、archive writer、CLI | `KEEP_EXPLICIT`；任务 3 focused gate 证明跨会话拒绝、任意 cursor 注入拒绝、stale draft 拒绝、并发同 draft 只归档一次 |
| `scripts/check_court_session_closeout.py` | 新 focused checker | `KEEP_FOCUSED_CHECK_ONLY`；只显式运行，不进入普通 Skill 运行链 |

## 7. 任务 1/2 待测量命令

| 场景 | 命令候选 | 目标证据 |
| --- | --- | --- |
| 低复杂度 canary | `court intake` 或当前等价结构化 gate；`OK`、闲聊变体、轻答变体 | 不启动三省/史馆/Git/发布检查；不按字符串特化 |
| 正式开朝 | `python -B scripts/court_open_fastpath.py --fast --request-file ... --format json` | Git 调用、文件读取、角色数、capability snapshot 顺序 |
| 史馆记录/结诏 | `archive_checkpoint.py --no-refresh` 与主动 closeout RED | 保留 Markdown、索引、无默认 tree/Obsidian 刷新 |
| 项目目录外 CLI | `python -B scripts/court_cli_registry.py court open --request-file .\request.json --format json` 从非 Git/中文/空格 cwd 运行 | 相对路径按 caller cwd；普通非 Git 不被拒 |
| CLI 帮助 | `python -B scripts/court_cli_registry.py --help` 与 group help | public 日常面不枚举无关 check/release |

## 8. 暂停线

以下情况不得继续产品修改：

- 任一 `beta0.5.9` 能力缺少当前替代入口。
- 候选脚本被判定为 `VALUE_UNKNOWN` 且需要修改或删除。
- 任何实现需要删除 GBrain、Git 联邦、官署预载、诏令绑定或史馆基础能力。
- 任何普通 Skill 路径把 release/install/legal/npm gate 作为前置。
- 任一测试或实现通过 `if text == "OK"`、关键词黑白名单、长度或测试环境变量实现快速路径。
