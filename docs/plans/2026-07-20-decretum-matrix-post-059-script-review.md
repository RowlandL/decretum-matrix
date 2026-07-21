# Decretum Matrix beta0.5.9 后增脚本、校验和门禁审查

状态：`TASK2_REVIEW_RECORDED`

对应计划任务 2。本文件只记录审查与处置边界；它不表示清理已经完成，也不把任何未实现整改标为 PASS。

机器可读证据：`.repo-control/evidence/decretum-matrix/objective-remediation/post-059-script-review.json`

## 1. 审查输入

| 项 | 内容 |
| --- | --- |
| 历史基线 | `beta0.5.9^{commit}=040f707e5acc7c12cfcf50afcfc111a7e49a2f00` |
| 当前接受基线 | `9774a1415b906b357985e462e74efaf842f45602` |
| 当前分支 | `release/beta1.0.2` |
| 目标版本 | `beta1.0.2` |
| 运行基线 | `docs/plans/2026-07-20-decretum-matrix-runtime-baseline.md` |
| 功能清单 | `docs/plans/2026-07-20-decretum-matrix-feature-inventory.md` |

复现命令：

```powershell
git diff --name-status -M --find-renames beta0.5.9..9774a1415b906b357985e462e74efaf842f45602 -- scripts references/manifests bin package.json release-manifest.json
python -B scripts/check_unified_cli.py --inventory-only --json
rg -n "def _legacy_runtime|def _capture_subprocess|cwd=ROOT|def _structured_request|def render_group_help|def _resolve_and_run" scripts/court_cli_registry.py
rg -n "def prepare_fast_open|check_capability_index_gate|live_worktree_identity|include_shangshu_ministries" scripts/court_open_fastpath.py
rg -n "from shiguan_gbrain|recall_provenance|governance_id" scripts/query_shiguan_index.py scripts/shiguan_gbrain.py scripts/shiguan_git_federation.py
```

## 2. 规模事实

| 指标 | 数值 |
| --- | ---: |
| `scripts/` 新增 | 52 |
| `scripts/` 修改 | 65 |
| `scripts/` 删除 | 0 |
| 新增 `check_*` | 26 |
| 大幅改写脚本（变更行数 ≥ 500） | 19 |
| 新增 `references/manifests/` | 7 |
| CLI manifest entries | 127 |
| CLI public entries | 127 |
| 运行 registry 有效记录 | 126 |
| 新增脚本中被 CLI 包装 | 31 |
| release gate steps | 50 |
| release gate `always` steps | 48 |
| release gate timeout 合计 | 9180 秒 |
| release manifest files | 299 |
| release manifest scripts | 165 |
| generated portable seed paths | 8 |

这些数字只说明审查范围，不构成功能删除或保留理由。

## 3. 价值分类规则执行结果

| 价值分类 | 数量 | 处置含义 |
| --- | ---: | --- |
| `VALUE_BASELINE` | 4 | 承接 `beta0.5.9` 既有能力；只能做等价重构。 |
| `VALUE_EXPLICIT` | 27 | 用户明确新增或要求保留；必须保留正式能力。 |
| `VALUE_HISTORY` | 7 | 读取、迁移或维护旧记录/安装/史馆历史；保留能力。 |
| `VALUE_PROJECT_ONLY` | 27 | 项目开发、安装、打包、发布阶段保留；不得进入闲聊、轻量或普通开朝路径。 |
| `VALUE_DUPLICATE` | 4 | 有参考或测试价值，但不得改变默认三省六部运行；先下沉，再决定是否合并。 |
| `VALUE_NONE` | 0 | 本轮未判定可直接删除。 |
| `VALUE_UNKNOWN` | 0 | 本轮候选集均已给出当前处置；未完成清理前仍不得宣称 PASS。 |

说明：`VALUE_UNKNOWN=0` 仅适用于本轮候选集，不是全仓库无限审计结论。

## 4. 五类运行路径审查

| 路径 | 当前调用 | 问题 | Task2 处置 |
| --- | --- | --- | --- |
| 低复杂度结构化 intake | `court_cli.py -> court_cli_registry.py -> court_runtime.py -> court_intake_gate.py` | 未发现 `OK` 精确文本特化；但仍经过统一 adapter 和隔离子进程，约 0.46–0.57 秒。 | 保留太子场景判定和诏令绑定；后续优化 adapter/进程成本，不删功能。 |
| 正式开朝 | `court_cli.py -> court_cli_registry.py -> court_open_fastpath.py -> check_capability_index_gate.py` | 生产 fast open 直接导入 checker 模块，且无条件做 Git 身份探测；外部/非 Git 场景易误伤。 | 保留 capability snapshot 和 fail-closed；拆出普通 runtime 所需最小库，checker 只留项目验收。 |
| 史馆查询 | `query_shiguan_index.py -> shiguan_gbrain.py -> shiguan_entry_utils.py` | 查询层应有机使用 GBrain，基础 scorer 保留为 fallback。 | GBrain 是史馆默认智能查询/召回层；基础史馆查询仍可退化运行。 |
| GBrain / Git 联邦 | `shiguan_gbrain.py` 可显式触发 Git Federation provenance | Git 联邦可被 GBrain 在整理/沉淀/管理模式触发；不得在普通轻量/开朝路径隐式运行重型 Git 管理。 | 保留二者；触发边界改为显式参数和 focused gate。 |
| 项目工程 | `check_release_gate.py`、`build_npm_package.mjs`、`check_npm_package.mjs` 等 | release/install/legal/npm gate 有价值，但不属于 Skill 普通运行。 | 转入任务 9；从日常帮助和 Skill runtime 中下沉。 |
| 项目目录外 CLI | HEAD 基线中 `court_cli_registry.py` 的子进程 `cwd=ROOT` | HEAD 外部目录相对 `request-file` 失败；绝对路径可读。当前工作树已有 cwd 候选修复且 focused GREEN。 | 任务 5 保留 RED/GREEN 证据；继续做完整 CLI/public surface 验收。 |

## 5. 新增脚本候选处置表

| 脚本 | 价值 | 处置 |
| --- | --- | --- |
| `scripts/build_npm_package.mjs` | `VALUE_PROJECT_ONLY` | 保留项目级 npm 打包；不进入 Skill runtime。 |
| `scripts/check_cli_performance.py` | `VALUE_PROJECT_ONLY` | 保留为显式性能验收；不得普通运行。 |
| `scripts/check_court_capability_recruitment.py` | `VALUE_PROJECT_ONLY` | focused checker，仅验收阶段使用。 |
| `scripts/check_court_complexity_budget.py` | `VALUE_PROJECT_ONLY` | 项目维护预算，不作为启动门。 |
| `scripts/check_court_dispatch_hierarchy.py` | `VALUE_EXPLICIT` | 验证直接上级规则；只作 focused checker。 |
| `scripts/check_court_intake_gate.py` | `VALUE_EXPLICIT` | 保留场景分流/主动结诏测试；正式任务低分放行需重审。 |
| `scripts/check_court_multi_instance_dispatch.py` | `VALUE_PROJECT_ONLY` | 并发验收，不进入 ordinary。 |
| `scripts/check_court_office_assignment_binding.py` | `VALUE_EXPLICIT` | 验证官署名称和语义绑定。 |
| `scripts/check_court_open_fastpath.py` | `VALUE_EXPLICIT` | 验证开朝 fastpath；不作前置运行。 |
| `scripts/check_court_outcome_gate.py` | `VALUE_EXPLICIT` | 验证五级结果门。 |
| `scripts/check_court_preload_semantics.py` | `VALUE_EXPLICIT` | 验证预载语义。 |
| `scripts/check_court_result_semantics.py` | `VALUE_EXPLICIT` | 验证结果语义。 |
| `scripts/check_court_runtime_completion.py` | `VALUE_PROJECT_ONLY` | runtime 完成度验收。 |
| `scripts/check_governance_framework.py` | `VALUE_DUPLICATE` | 通用治理参考验收；默认三省六部不依赖它。 |
| `scripts/check_install_current_agent_copy.py` | `VALUE_PROJECT_ONLY` | 安装阶段。 |
| `scripts/check_install_prompt.py` | `VALUE_PROJECT_ONLY` | 安装提示阶段。 |
| `scripts/check_npm_package.mjs` | `VALUE_PROJECT_ONLY` | npm 项目级。 |
| `scripts/check_p00_semantic_dispatch_context.py` | `VALUE_EXPLICIT` | 语义连续和 revision focused checker。 |
| `scripts/check_release_metadata.py` | `VALUE_PROJECT_ONLY` | 发布元数据阶段。 |
| `scripts/check_semantic_continuity.py` | `VALUE_EXPLICIT` | revision fail-closed focused checker。 |
| `scripts/check_shiguan_git_federation.py` | `VALUE_EXPLICIT` | Git 联邦显式功能验收。 |
| `scripts/check_shiguan_host_memory_and_child_trace.py` | `VALUE_HISTORY` | host memory / child trace 历史支持验收。 |
| `scripts/check_shiguan_migration_gate.py` | `VALUE_HISTORY` | 史馆迁移验收。 |
| `scripts/check_skill_identity.py` | `VALUE_PROJECT_ONLY` | 安装/发布身份验收。 |
| `scripts/check_source_budget_refactor.py` | `VALUE_PROJECT_ONLY` | 源码维护预算。 |
| `scripts/check_startup_fastpath_contract.py` | `VALUE_EXPLICIT` | authority/behavior/superCC 分离 focused checker。 |
| `scripts/check_unified_cli.py` | `VALUE_EXPLICIT` | CLI 验收；需补外部 cwd RED。 |
| `scripts/court_agent_admission.py` | `VALUE_EXPLICIT` | 保留真实差遣 admission；不进入闲聊/轻量。 |
| `scripts/court_agent_admission_contract.py` | `VALUE_PROJECT_ONLY` | 合同/测试支持。 |
| `scripts/court_capability_recruitment.py` | `VALUE_EXPLICIT` | 保留能力分配建议；按需加载。 |
| `scripts/court_cli_registry.py` | `VALUE_EXPLICIT` | 保留统一 CLI；修 cwd，拆日常 public 与兼容库存。 |
| `scripts/court_complexity_budget.py` | `VALUE_PROJECT_ONLY` | 项目维护面。 |
| `scripts/court_dispatch_hierarchy.py` | `VALUE_EXPLICIT` | 保留层级约束。 |
| `scripts/court_intake_gate.py` | `VALUE_EXPLICIT` | 保留场景分流；正式清楚度/授权边界需重审。 |
| `scripts/court_native_execution.py` | `VALUE_EXPLICIT` | native 运行入口保留。 |
| `scripts/court_office_config.py` | `VALUE_EXPLICIT` | 中性官署配置保留。 |
| `scripts/court_open_fastpath.py` | `VALUE_EXPLICIT` | 保留开朝 fastpath；拆 checker/Git/全量预载耦合。 |
| `scripts/court_operation_journal.py` | `VALUE_HISTORY` | 仅 per-task durable journal；不得成为共享 mutable ledger。 |
| `scripts/court_outcome_gate.py` | `VALUE_EXPLICIT` | 五级结果语义保留。 |
| `scripts/court_result_semantics.py` | `VALUE_EXPLICIT` | 结果语义保留。 |
| `scripts/court_safe_fs.py` | `VALUE_PROJECT_ONLY` | 安全库按需使用。 |
| `scripts/court_safe_fs_windows.py` | `VALUE_PROJECT_ONLY` | Windows 安全库按需使用。 |
| `scripts/court_semantic_continuity.py` | `VALUE_EXPLICIT` | 语义连续与 invalid revision 零差遣保留。 |
| `scripts/court_supercc_execution.py` | `VALUE_EXPLICIT` | superCC 独立入口保留。 |
| `scripts/governance_framework.py` | `VALUE_DUPLICATE` | 通用治理参考实现下沉，不改默认 runtime。 |
| `scripts/install_current_agent_copy.py` | `VALUE_PROJECT_ONLY` | 安装/回滚阶段。 |
| `scripts/shiguan_gbrain.py` | `VALUE_EXPLICIT` | GBrain 保留；作为史馆智能查询/召回、advisory 和只读整理/沉淀候选层，可显式触发 Git 联邦 provenance。 |
| `scripts/shiguan_git_federation.py` | `VALUE_EXPLICIT` | Git 联邦保留，显式史馆管理。 |
| `scripts/shiguan_host_memory_projection.py` | `VALUE_HISTORY` | 历史投影/迁移阶段。 |
| `scripts/shiguan_migration_gate.py` | `VALUE_HISTORY` | 迁移阶段。 |
| `scripts/supercc_dispatch_contract.py` | `VALUE_EXPLICIT` | superCC 显式路径。 |
| `scripts/supercc_dispatch_delivery.py` | `VALUE_EXPLICIT` | superCC 显式路径。 |

## 6. 大幅改写脚本处置

| 脚本 | 变更行数 | 价值 | 处置 |
| --- | ---: | --- | --- |
| `scripts/court_runtime.py` | 6863 | `VALUE_BASELINE` | 保留运行能力，只做有 RED 的局部重构。 |
| `scripts/check_court_agent_lifecycle.py` | 2510 | `VALUE_PROJECT_ONLY` | focused checker。 |
| `scripts/check_court_dispatch_policy.py` | 1850 | `VALUE_PROJECT_ONLY` | focused checker。 |
| `scripts/check_supercc_ministry_dispatch.py` | 1799 | `VALUE_EXPLICIT` | superCC checker，不作 native 标准。 |
| `scripts/check_court_runtime.py` | 1599 | `VALUE_PROJECT_ONLY` | focused checker。 |
| `scripts/migrate_shared_shiguan.py` | 1443 | `VALUE_HISTORY` | 迁移阶段保留。 |
| `scripts/ensure_supercc_court.py` | 1238 | `VALUE_EXPLICIT` | superCC 显式环境。 |
| `scripts/shiguan_paths.py` | 1193 | `VALUE_BASELINE` | 保留路径解析，进入项目外运行审查。 |
| `scripts/check_package_privacy.py` | 1071 | `VALUE_PROJECT_ONLY` | 发布/包隐私阶段。 |
| `scripts/ensure_portable_court_bootstrap.py` | 828 | `VALUE_HISTORY` | 安装/迁移阶段。 |
| `scripts/check_capability_index_gate.py` | 824 | `VALUE_BASELINE` | 拆分“运行库函数”和“checker 门禁”。 |
| `scripts/check_court_intervention_matrix.py` | 759 | `VALUE_PROJECT_ONLY` | focused checker。 |
| `scripts/refresh_capability_registry.py` | 636 | `VALUE_BASELINE` | 显式维护命令，不在普通启动刷新。 |
| `scripts/check_release_manifest.py` | 569 | `VALUE_PROJECT_ONLY` | 发布阶段。 |
| `scripts/build_release_artifacts.py` | 531 | `VALUE_PROJECT_ONLY` | 发布阶段。 |
| `scripts/check_court_agent_config.py` | 518 | `VALUE_PROJECT_ONLY` | focused checker。 |
| `scripts/check_release_gate.py` | 508 | `VALUE_PROJECT_ONLY` | 发布阶段。 |

## 7. Manifest 和 adapter 审查

| 文件 | 价值 | 处置 |
| --- | --- | --- |
| `references/manifests/cli-command-surface.v1.json` | `VALUE_EXPLICIT` | 保留 registry，但分离“兼容库存”和“日常 public help”。 |
| `references/manifests/court-dispatch-hierarchy.v1.json` | `VALUE_EXPLICIT` | 保留。 |
| `references/manifests/direct-review-governance.v1.json` | `VALUE_DUPLICATE` | 参考实现，下沉。 |
| `references/manifests/governance-implementations.v1.json` | `VALUE_DUPLICATE` | 不改变默认三省六部运行。 |
| `references/manifests/install-projection.v1.json` | `VALUE_PROJECT_ONLY` | 安装阶段。 |
| `references/manifests/github-release-metadata.v1.json` | `VALUE_PROJECT_ONLY` | 发布阶段。 |
| `references/manifests/skill-identity.v1.json` | `VALUE_PROJECT_ONLY` | 安装/发布阶段。 |
| `references/manifests/release-gates.v1.json` | `VALUE_PROJECT_ONLY` | 项目工程阶段，不进入 Skill runtime。 |
| `references/manifests/source-state-budget.v1.json` | `VALUE_PROJECT_ONLY` | 项目维护面。 |

CLI adapter 当前事实：

- manifest 有 127 个 entries，全部 `public=true`。
- 分组为：office 7、shiguan 26、release 4、check 70、root 1、court 7、install 4、supercc 8。
- HEAD 基线中，`scripts/court_cli_registry.py` 的 `_legacy_runtime()` 和 `_capture_subprocess()` 固定 `cwd=ROOT`。
- 当前隔离 diff 已新增 `command_cwd()` / `resolve_user_path()`，并让 `court|shiguan|install` 使用调用者 cwd，`check|release` 使用代码根。
- 当前隔离 diff 也给 `scripts/check_unified_cli.py` 增加了 `--external-cwd` focused checker；实测 `python -B scripts/check_unified_cli.py --external-cwd --json` 返回 `CLI_EXTERNAL_CWD=PASS`。
- 该 PASS 只证明当前 dirty 候选修复了外部 cwd focused 场景，不等于 Task5 全部验收完成。

处置原则：

- 不新增第二个 umbrella CLI。
- 保留正式功能入口。
- 日常帮助只展示用户/维护者高频入口；完整兼容库存可通过显式 inventory 或 legacy 脚本定位。
- `check`、`release`、安装/发布工程项默认不出现在普通 Skill 路径。

## 8. 当前隔离 closeout 候选

以下文件不属于 `beta0.5.9..9774a141` 的 HEAD diff，而是当前工作树隔离候选：

| 文件 | 状态 | 当前结论 |
| --- | --- | --- |
| `scripts/court_session_closeout.py` | untracked | `KEEP_EXPLICIT`；任务 3 RED/GREEN 已证明会话边界、cursor 安全、幂等、跨会话拒绝和普通 closeout 不刷新派生树。 |
| `scripts/check_court_session_closeout.py` | untracked | `KEEP_FOCUSED_CHECK_ONLY`；只作为显式 focused checker，不进入普通 Skill 运行链。 |
| `scripts/court_cli_registry.py` | modified | `court closeout-session` 已进入 CLI manifest；cwd 分层已修复并通过外部 cwd GREEN。 |
| `scripts/check_unified_cli.py` | modified | 外部 cwd、日常 help 面、manifest/registry 一致性、npm canonical runtime 均通过当前 focused GREEN。 |
| `scripts/court_intake_gate.py` | modified | closeout 分类保留；formal clarity gate 已恢复机器约束。 |
| `scripts/check_court_intake_gate.py` | modified | closeout 正反例和 formal understanding 负例通过；只作为 focused checker。 |

## 9. 允许的清理方向

1. 保留 `beta0.5.9` 全部能力、GBrain、Git 联邦、官署预载、语义胶囊、诏令绑定、native/superCC 分离。
2. 保留项目级工程能力，但从闲聊、轻量任务和普通开朝链中移除。
3. 对 checker/gate 的处理是“下沉到显式验收阶段”，不是删除功能。
4. 对 GBrain/Git 联邦的处理是“职责边界和触发边界修复”，不是删除。
5. 对 CLI 的处理是“统一入口保留、兼容库存保留、日常 public 收窄、cwd 修复”，不是另造总入口。
6. 对 receipt/hash/tree/graph/Obsidian 的处理必须以后续史馆任务证据为准；本任务不直接删除。

## 10. Task2 当前状态

```text
POST_059_SCRIPT_REVIEW=PASS
beta059_capability_lost=0
explicit_feature_lost=0
historical_data_unreadable=0
value_unknown=0
lightweight_unrelated_script_calls=0
literal_input_special_cases=0
user_output_changed=0
```

### 10.1 已完成的当前工作树整改

| 项 | 修改 | 验证 |
| --- | --- | --- |
| 外部 cwd | `scripts/court_cli_registry.py` 增加 `command_cwd()` 和 `resolve_user_path()`；`court/shiguan/install` 保留调用者目录，`check/release` 显式使用代码根。 | `python -B scripts/check_unified_cli.py --registry --external-cwd --json`：`CLI_EXTERNAL_CWD=PASS`，相对 `request.json` 到达 `task_id_required`。 |
| 日常 help 面 | `scripts/court_cli_registry.py` 以 `DAILY_HELP_COMMANDS` 展示日常 Skill 面；完整 compatibility adapter 仍保留并可显式调用。 | `daily_help_command_count=32`，`daily_help_forbidden_hits=[]`，`record_count=128`。 |
| 正式任务 understanding 门 | `scripts/court_intake_gate.py` 恢复 `require_new_formal_task_gate()` 对 `understanding.score>=95` 和 `route=DIRECT_EXECUTION` 的要求；`minimal_formal_task_example()` 恢复 schema-complete 示例。 | `python -B scripts/check_court_intake_gate.py` PASS；`python -B scripts/check_governance_framework.py --json` PASS。 |
| fastpath 能力选择 | `scripts/court_open_fastpath.py` 使用 production `court_capability_recruitment.route_registry_first/default_source_roots`，不再从 `check_capability_index_gate.py` 导入运行依赖。 | `python -B scripts/check_court_open_fastpath.py --json`：`production_capability_not_checker_import=true`。 |
| 主动结诏 | `scripts/court_session_closeout.py` 由 session_id 派生 cursor，不信任公开 request 的 cursor_path；同一 cursor 锁内复核 stale draft；不建第二 ledger。 | `python -B scripts/check_court_session_closeout.py`：`COURT_SESSION_CLOSEOUT_OK core=PASS transaction=PASS cli=PASS`。 |
| GBrain/基础召回边界 | `query_shiguan_index.py` 默认经 GBrain 调用共享查询核心，`--query-mode fallback` 保留基础退化路径；GBrain 提供只读 settlement candidates，并可在显式模式触发 Git 联邦 provenance。 | `python -B scripts/check_governance_framework.py --json` PASS；`python -B scripts/check_governance_framework.py --only gbrain --json` PASS；`python -B scripts/query_shiguan_index.py --help` PASS。 |
| manifest/registry 闭环 | `check_unified_cli.py` 将任务 3 新增脚本加入提交前 allowlist，并把 `court_session_closeout.py` 映射为 `court closeout-session`。 | `python -B scripts/check_unified_cli.py --all --json`：`CLI_ENTRYPOINT_COVERAGE=PASS`，registered=129，record=128。 |

剩余未声明范围：

- 项目级发布、安装、包产物、远端 tag/release/npm 不在本 Task2 PASS 中。
- `archive_checkpoint.py` 既有 receipt/hash/tree/graph/Obsidian 触发关系保持现状；本任务未删除这些功能。
- superCC 只作为独立可选 smoke；当前桌面环境不作为统一验收标准。
