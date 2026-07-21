# Decretum Matrix 语义边界矩阵

状态：`CURRENT_TASK0_DRAFT`

本文件只记录任务 0 的当前证据，不声明产品整改已经完成。证据来源仅限用户明确要求 `U`、`beta0.5.9` Git 对象 `H`、上一问题基线 `beta1.0.1@9774a1415b906b357985e462e74efaf842f45602` 及当前 `release/beta1.0.2` 工作树源码 `C`。没有证据的项标为 `X`，不得进入产品源修改。

## 0. 当前证据锚点

| 项 | 当前证据 |
| --- | --- |
| 工作树 | `D:\project\worktrees\decretum-matrix\decretum-matrix-beta1.0.1-startup-fastpath` |
| branch | `release/beta1.0.2` |
| target version | `beta1.0.2` |
| 当前 HEAD | `9774a1415b906b357985e462e74efaf842f45602` |
| `beta0.5.9` tag 类型 | annotated tag |
| `beta0.5.9` commit | `040f707e5acc7c12cfcf50afcfc111a7e49a2f00` |
| 精确 Skill | `C:\Users\32893\.agents\skills\decretum-matrix\SKILL.md` 已在本轮完整读取 |
| 当前隔离 diff | `scripts/check_court_intake_gate.py`、`scripts/court_cli_registry.py`、`scripts/court_intake_gate.py` 已修改；`scripts/court_session_closeout.py`、`scripts/check_court_session_closeout.py` 未跟踪 |
| 计划书 | `docs/plans/2026-07-20-decretum-matrix-objective-remediation-plan.md` SHA256 `00E71BF75614125A9A6EAC80DF0AA102D3D3137CB0CE322D086B5113CF534825` |

## 1. S-01 至 S-62 矩阵

| 编号 | 来源 | 语义边界 | 当前实现证据 | 验收方式 |
| --- | --- | --- | --- | --- |
| S-01 | U | Decretum Matrix 是围绕“诏令”的多-agent 协作体系。 | `SKILL.md` 定义为 Decretum Matrix/三省六部语义路由器。 | 文档同步检查；正式任务路径输出包含诏令/任务章程。 |
| S-02 | U | 正式任务默认表现为三省六部流程。 | `SKILL.md` 有 `太子定性 -> 三省会审 -> 三省上奏 -> 太子回奏 -> 尚书统六部 -> 工坊办差 -> 门下复核 -> 史馆实录`。 | 正式任务 RED/GREEN 覆盖三省、尚书、门下五级复核。 |
| S-03 | U | 史馆/知识库为跨-agent 协作提供记忆能力。 | `references/court-shiguan-memory.md` 记录 archive/index/tree/recall/Obsidian/GBrain。 | 史馆基础记录、查询、树图、可读 Markdown 验收。 |
| S-04 | U | 任务分配遵循适用场景原则。 | 当前 `scripts/court_intake_gate.py` 有 `CASUAL_CHAT`、`TRIVIAL_DIRECT`、`FORMAL_TASK` 等分类；仍需任务 1 测调用链成本。 | 场景变体测试，不按 `OK` 字符串特化。 |
| S-05 | U | 增加功能不等于增加运行复杂度。 | `beta0.5.9 -> HEAD` 文件/脚本/check/manifest 均显著增加，进入整改候选。 | 脚本价值评估和场景成本验收。 |
| S-06 | U | 加载目标是路径清晰和首次正确加载；不是一味短而快。若需分两次加载，入口必须写明阶段边界。 | 当前短 `SKILL.md` 有 progressive map，但需补足“第一次/第二次加载”语义说明。 | 文档验收：入口说明分阶段加载；普通路径不误载全部 reference。 |
| S-10 | U | 太子负责语义差分和场景定性。 | `scripts/court_intake_gate.py` 当前为结构化 conversation gate。 | intake focused 测试。 |
| S-11 | U | 场景至少包括闲聊/轻量交流、正式任务、任务延续、任务纠正、主动结诏。 | 当前隔离 diff 增加 `EXPLICIT_CLOSEOUT`；尚未被接受为正式实现。 | 任务 3 RED 先失败，再决定正式入口。 |
| S-12 | U | 闲聊适用于随便的轻量任务或聊天。 | `CASUAL_CHAT`、`SIDE_CHAT`、`TRIVIAL_DIRECT` 当前存在。 | 闲聊/轻答变体测试。 |
| S-13 | U | 闲聊不自动结诏。 | 当前隔离 diff 未证明完整会话游标；旧实现需任务 1/3 测量。 | 运行路径不得调用史馆写入。 |
| S-14 | U | 主动结诏汇总单会话未结诏内容。 | `court_session_closeout*` 是隔离候选，不是已接受实现。 | 任务 3 验证 chat/light/task/correction/result 全收集且不跨会话。 |
| S-15 | U | 会话结诏不得额外富化。 | 隔离候选 `render_session_closeout_markdown()` 只渲染会话内容；仍需审查 receipt/hash/refresh。 | 输出只包含会话内容、必要游标和史馆路径。 |
| S-20 | U | 三省在太子授权前审议。 | `SKILL.md`、流程图、`court_open_fastpath.py` 均含三省路径；当前 fastpath 会预载过多。 | 正式流程顺序验收。 |
| S-21 | U | 尚书授权后统筹六部；一般正式任务由尚书下派对应六部子/孙官署，不得由尚书代替六部执行六部职责。 | 当前 `court_open_fastpath.py`/formal open 需验证 ministry packet/dispatch 是否真实体现尚书下派。 | 正式任务 RED：必要六部不缺席；简单任务可单尚书但须有理由。 |
| S-22 | U/C | 门下五级结果复核保留五类结果。 | 当前源码含 `court_outcome_gate.py` 与对应 checker。 | 五类结果 focused 测试。 |
| S-23 | U | 返工、补证、阻断、通过后史馆与太子结语。 | 流程图与 outcome gate 表达该路径。 | 结果门转移测试。 |
| S-24 | U | 只有很简单、单个尚书子线程即可完成且无必要六部专责的任务，才允许尚书单独执行。 | 当前实现未证明该豁免判断。 | RED：简单任务有豁免理由；一般任务不得单尚书。 |
| S-25 | U | “派遣对应六部”是职责分解；`behavior=serial|parallel` 只决定执行形态，不得省略六部职责或由太子/root 直派六部。 | 当前 focused open 需区分职责记录、并行派生和直接上级。 | RED：serial 不并行但保留尚书下派职责；parallel 有尚书下派六部差遣。 |
| S-26 | U | 六部唯一直属上级是尚书；并行时六部必须表现为尚书下派的子/孙官署。 | 当前 open receipt 需要审查是否只有自动 ministry admission，而缺少尚书统筹计划/汇总字段。 | RED：parallel receipt 含 `shangshu_ministry_coordination`，且六部 hierarchy、admission、binding 均指向 `shangshu`。 |
| S-27 | U | 三权介绍必须说明 `approval`、`autonomous`、`super` 的中文含义；串行/并行必须作为独立运行方式说明。 | 当前文档多处仅写枚举词，需要补充用户侧说明。 | 文档验收：三权与 behavior 分章/分表，不混写。 |
| S-30 | U | 官署预载最初用于解决官署分配名称不正确。 | 当前有 `agents/office-dossiers/*`、`agents/standing-officials/*`、`court_office_bootstrap.py`。 | 官署名/职责/上级一致性测试。 |
| S-31 | U | 规范官署名称和语义胶囊维持身份及语义。 | 当前 `court_office_bootstrap.py`、`court_semantic_continuity.py`、`court_open_fastpath.py` 有绑定与 digest。 | 保留结构化身份；减少不必要读写。 |
| S-32 | U | 官署预载必须保留，不得因提速删除。 | 当前预载存在且过重。 | 修改后仍能构造有效官署 role card/必要 dossier。 |
| S-33 | U | 诏令绑定必须保留，防止编造和语义漂移。 | 当前 `court_semantic_continuity.py`、`court_open_fastpath.py` 有 revision/hash 绑定。 | invalid revision fail-closed，零差遣。 |
| S-34 | U/C | authority 为 `approval|autonomous|super`；behavior 为 `serial|parallel`；二者正交。 | `court_open_fastpath.py` 有 `AUTHORITIES`/`BEHAVIORS`；`check_startup_fastpath_contract.py` 有 cartesian 检查。 | authority x behavior 矩阵。 |
| S-35 | U/C | invalid revision 阻止差遣，零 dispatch，无手工旁路。 | `check_startup_fastpath_contract.py` 有 invalid semantic zero-dispatch 测试；需重跑当前证据。 | RED/GREEN 输出 admission_calls=0。 |
| S-40 | U/H | 史馆既有脚本和流程已具备基础记录、索引和召回。 | `beta0.5.9` 已有 `archive_checkpoint.py`、`query_shiguan_index.py`、`memory_decision.py`、`grow_shiguan_tree.py`、`build_shiguan_knowledge_graph.py`。 | 0.5.9 与当前功能保全对照。 |
| S-41 | U | 史馆内容面向人阅读，并允许人工整理和修改。 | archive 为 Markdown；`tidy_shiguan_records.py` 已存在。 | 手改 Markdown 后仍能查询/重建索引。 |
| S-42 | U | GBrain 是史馆查询、召回和整理/沉淀候选层，无当前任务执行权或写权。 | 当前 `query_shiguan_index.py` 接入 `shiguan_gbrain.py`，需要明确默认智能层与基础 fallback 的边界。 | 查询默认走 GBrain 智能召回；基础 scorer 作为显式 fallback；GBrain 输出 advisory，整理候选不写入。 |
| S-43 | U | GBrain 属于明确追加功能，必须保留。 | 当前 `scripts/shiguan_gbrain.py` 是新增脚本。 | GBrain 功能验收，不进入普通开朝。 |
| S-44 | U | Git 联邦用于史馆管理，必须保留。 | 当前 `scripts/shiguan_git_federation.py` 是新增脚本。 | 显式 probe/verify 功能验收。 |
| S-45 | U/H/C | `beta0.5.9` 史馆记录、索引、树、图、Web、Obsidian 等全部能力为底线。 | 多个 beta0.5.9 史馆脚本仍存在，部分 blob 相同，部分变更。 | 功能清单逐项保全。 |
| S-46 | U/C | 候选脚本只有不承担 0.5.9 任一能力、明确新增功能、历史职责或当前独有输出，且无调用者，才可合并/移除。 | 当前候选集包括新增 52 个 scripts、7 个新增 manifest、npm/发布工程文件、隔离 closeout 脚本。 | 脚本价值评估，不按文件数量直接删除。 |
| S-50 | U | CLI 初衷是简化调用、提升速度和兼容性。 | 当前 `cli-command-surface.v1.json` 有 129 entries，运行 registry 记录 128 个 compatibility adapter；日常 help 面 32 行。 | CLI 可见面和外部 cwd 验收。 |
| S-51 | U | CLI 不应成为治理、准入、发布或审计中心。 | 当前完整 adapter 仍可显式调用，但日常 help 不枚举项目级检查。 | 日常 help 不枚举项目级检查。 |
| S-52 | U | 复用现有 CLI，不新增竞争总入口。 | 当前有 `scripts/court_cli.py` 和 `scripts/court_cli_registry.py`。 | 修改现有入口，不新增 umbrella CLI。 |
| S-53 | U | 项目内正常、项目外异常必须整改。 | 当前 `court/shiguan/install` 使用调用者 cwd，`check/release` 使用代码根；外部相对 request-file GREEN。 | 非 Git、中文/空格路径、无关 Git cwd 测试。 |
| S-54 | U | 无关 Git、非 Git、空格/中文路径、全局安装均是验收场景。 | 当前 focused CLI 覆盖含中文/空格外部 cwd 与 canonical npm runtime；更完整 install 面留到项目级验收。 | 任务 5 RED/GREEN。 |
| S-55 | U | 0.5.9 全部能力和明确新增功能保留正式入口；1.0.1 新增脚本按价值评估。 | 当前 manifest 保留完整 compatibility inventory，daily help 区分正式日常面和兼容库存。 | `KEEP_*` 功能可发现，冗余入口可合并。 |
| S-56 | U | `OK` 是 canary，不是特化场景。 | 当前静态搜索与轻量变体基线均未发现按 `OK` 或关键词/长度特化。 | literal special cases 为 0。 |
| S-60 | U/C | native super 与 superCC 是不同启动/运行环境。 | 当前有 `court_native_execution.py`、`court_supercc_execution.py`、`check_startup_fastpath_contract.py`。 | native 不加载/probe superCC；superCC 独立 entry_path。 |
| S-61 | U | 当前桌面不支持 superCC 标准验收。 | 用户明确说明。 | superCC 结果标 `NOT_STANDARD_ENVIRONMENT`，不阻塞 native。 |
| S-62 | U | superCC 可尝试，但不能作为普通 Skill 统一标准。 | 计划任务 8 已设为可选 smoke。 | native Skill 验收独立完成。 |

## 2. 当前 Task 0 判定

| 项 | 判定 |
| --- | --- |
| 是否新建 `scripts/check_skill_feature_preservation.py` | 当前任务 0 不新建。门下只读审查认为现有测试不能覆盖 `beta0.5.9` 全部能力保全，存在客观缺口；但用户已明确反对无价值校验，故本项进入任务 1/2 后复评。若后续创建，必须只读、离线、显式运行，且不得进入开朝、闲聊、轻量任务或普通 Skill 运行链。 |
| 当前隔离 Task 1 diff 是否可接受为 Skill 级候选实现 | 是，限当前已验证范围。`court_session_closeout*` 已通过任务 3 focused RED/GREEN；CLI manifest/package surface 与 cwd 分层已通过任务 5 focused GREEN；发布/安装/远端不在本判定内。 |
| 是否允许产品源修改 | 任务 0 完成本文件和功能清单后，允许进入任务 1 的 RED/基线；产品源修改仍须以任务 1/2 证据为前置。 |

## 3. 当前隔离 diff 风险补记

| 文件 | 风险 |
| --- | --- |
| `scripts/court_intake_gate.py` | 当前实现保留 `require_new_formal_task_gate()` 对 `understanding >= 95` 和 `DIRECT_EXECUTION` 的硬要求；闲聊/轻答不被强制进入 formal gate。 |
| `scripts/check_court_intake_gate.py` | 当前覆盖 closeout 正反例、formal understanding 负例和 confidence mutation；只作为 focused checker。 |
| `scripts/court_cli_registry.py` | `court closeout-session` 已纳入 CLI manifest；`court/shiguan/install` 使用调用者 cwd，`check/release` 使用代码根；日常 help 面收窄但 compatibility adapter 仍可显式调用。 |
| `scripts/court_session_closeout.py` | 会写 shared Shiguan archive 与 cursor；cursor 由 session_id 派生，公开 request 不接受任意 cursor_path；不新增第二 ledger；stale draft 和跨会话内容 fail closed。archive/cursor crash gap 仍作为余险记录。 |
| `scripts/check_court_session_closeout.py` | 作为任务 3 focused test 保留；只允许显式运行，不进入普通 Skill 运行链。 |

## 4. 任务 0 验收命令

当前不新增 checker。任务 0 的验收采用以下只读/聚焦命令：

```powershell
git diff --name-status beta0.5.9..HEAD
python -B scripts/check_court_intake_gate.py
python -B scripts/check_unified_cli.py --inventory-only --json
python -B scripts/check_court_open_fastpath.py --json
python -B scripts/check_startup_fastpath_contract.py --json
```

后续任务 1/2 会补充真实运行基线和候选脚本价值报告。
