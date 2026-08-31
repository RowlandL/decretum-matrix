# 诏令矩阵 beta1.0.8 计划书（Execution Plan）

> 配套：开发文档 → docs/plans/2026-08-28-decretum-matrix-beta1.0.8-development-spec.md
> 任务书 → docs/plans/2026-08-28-decretum-matrix-beta1.0.8-task-book.md
> Handoff 协议草案 → docs/plans/2026-08-28-decretum-matrix-beta1.0.8-codex-handoff-protocol-draft.md
> 基线：release/beta1.0.7 · 日期：2026-08-28 · 建议工期：3 周 / 15 工作日（不含 stretch）
> beta1.0.7 已完成源码收尾；本计划从 `release/beta1.0.7` / HEAD `2571178` 基线起算。版本提升和任何外部发布动作仍要等 beta1.0.8 发布批准与对应回执。

---

## 1. 阶段总览

| 阶段 | 名称 | 里程碑 | 任务 | 建议工期 | 交接边界（详见 §3 与协议草案） |
| --- | --- | --- | --- | --- | --- |
| Phase 0 | 基线清偿 | M0 | E1–E5 | 2 天 | 工作树干净 + 门禁三件套绿 |
| Phase 1 | 合同与样本 | M1 | P1-1..3 | 2 天 | 契约/fixture 评审通过 |
| Phase 2 | 现有通用入口适配与自身 MCP 领域能力面 | M2 | P2-1..6 | 4 天 | 最终工具矩阵、Agent envelope、能力索引和领域写探针全绿 |
| Phase 3 | 分类、IKU 与 GBrain 记忆治理 | M3 | P3-1..9 | 5 天 | 编号/谱系防过拟合、冲突/过期、leaves/full-record、增量评估全绿 |
| Phase 4 | Codex 模型适配 | M4 | P4-1..4 | 3 天 | host proof + 回退测试绿 |
| Phase 5 | 发布 | M5 | P5-1..3 | 2 天 | 门禁全绿 + 收据 + 批准 |
| 非核心后续 | HTTP /mcp + Resources | — | 另立项 | — | 对当前 skill 不具实际意义，不进入 beta1.0.8 必需门禁 |

> 并行说明：Phase 2 与 Phase 3/4 可部分并行（P2 依赖 P1-1/2，P3 依赖 P1-3，P4 依赖 E）。默认串行推进以保证每阶段交接清晰；只有明确调度权时才并行。
> 执行前先读取 `decretum-matrix` skill，并优先从本机能力索引里筛出当前阶段有帮助的 skill，顺序建议是 `stop-that-shit` → `using-superpowers` / Superpowers → `ponytail`；交接时补用 handoff 相关 skill（如本机存在）与 `context-restore` / `context-save`。
> Q23 问卷审查采纳：A/B/C/E 能力均纳入 beta1.0.8 版本目标，内部按 Phase/P0/P1 分批交付；编号统一调用权威生成器并防谱系过拟合；史馆/记忆与能力索引支持领域化 Create/Read/Update；官署可在职责范围调用 MCP；现代协议优先并保留 legacy；HTTP/Resources 不进入当前 skill 核心。

## 2. 采纳后的阶段交付重点

| 阶段 | 交付重点 | 必须回写的验收证据 |
| --- | --- | --- |
| Phase 1 | 最终 MCP 工具矩阵、领域 API、Agent envelope、编号/谱系和记忆状态 schema | contract review、manifest diff、schema fixture |
| Phase 2 | 现有通用入口上的 A/B/C/E 工具族、能力索引主动查询、多 skill 加载、官署 dry-run/受控调用、领域化账册写入 | tools/list/tools/call、ACL/authority/write_set、Git commit、Agent envelope、legacy parity |
| Phase 3 | 编号生成器适配、谱系防过拟合、IKU、结诏冲突/过期范式、GBrain recall、leaves/full-record、增量 feedback | classification fixture、冲突/过期 fixture、full-record/leaves query、增量重算 receipt |
| Phase 5 | 全部 A/B/C/E 版本目标统一验收；HTTP/Resources 只做边界断言，不列必需门禁 | final gate summary、four evidence classes、Q23 adoption receipt |

### 2.1 依赖图

E(基线绿) → P1(合同) → P2(MCP 领域能力) ─┬→ P3(分类+IKU+GBrain) → P5(发布)
                                       └→ P4(Codex 适配) ────┘
非核心 HTTP/Resources 不作为当前依赖；未来另立项。

## 3. 每阶段 Codex 交接契约（Handoff Contract）

> 交接不是「写个说明」的行为，而是按协议草案（独立文件）执行的一组**有状态、可校验、幂等**的动作。本节给出每阶段必须满足的交接边界；协议细节（制品 schema、生命周期、校验、失败处理）见 Handoff 协议草案。

### 3.1 阶段边界通用要求（所有 Phase 通用）

每个阶段结束时，Codex 必须完成并满足：

1. **验收证据**：本阶段全部任务验收命令已执行，输出与期望一致；关键输出追加写入 docs/plans/beta1.0.8/handoffs/phase-N-evidence.md（或按协议草案的 evidence 制品格式）。
2. **代码状态**：本阶段相关改动已提交到 release/beta1.0.8 分支；git status --porcelain 无意外未提交项（docs/plans 系列文档除外，按协议允许）。
3. **交接文档**：按协议草案模板生成 phase-N-handoff.md（含：阶段目标达成、产出/变更文件清单、验收命令与输出、遗留问题与风险、下阶段入口指针、未决决策）。
4. **交接校验**：运行协议草案定义的 handoff-check（如存在）或等价校验：交接文档存在 + git 状态符合声明 + 门禁快照真实。
5. **状态登记**：在 docs/plans/beta1.0.8/handoffs/README.md（交接索引）登记本阶段状态为 COMPLETED（或 BLOCKED，含原因）。
6. **上下文续接**：阶段结束前先用 `context-save` 记录当前状态，阶段开始时先用 `context-restore` 找回上次工作点；handoff 解决阶段边界，context 解决会话边界。
7. **任务书回写**：每阶段完成后，在任务书对应阶段标记状态，并写入验收证据摘要；完整命令输出仍落 `phase-N-evidence.md`。

### 3.2 各阶段特殊交接边界

| Phase | 交接时必须为真（除 3.1 外） | 交接证据文件 |
| --- | --- | --- |
| 0 | 工作树干净；doctor 无 WARN；read_only/source_budget/release_manifest 三件套绿 | phase-0-evidence.md（三件套输出） |
| 1 | 契约文档 + fixtures 已提交；评审意见闭环（含 reviewer 与结论） | phase-1-evidence.md（评审记录） |
| 2 | load_public_tools()=12；check_court_mcp_server 45+ 探针全绿；journal 审计用例通过 | phase-2-evidence.md（探针输出 + 审计断言） |
| 3 | 分类验证集全过；IKU --dry-run 零字节变化且幂等 | phase-3-evidence.md（验证集 + 幂等输出） |
| 4 | host proof 正/反例通过；回退路径测试通过 | phase-4-evidence.md（probe 输出 + 回退日志） |
| 5 | 门禁清单全绿（任务书 P5-1 22 项）；收据重生成绑定 HEAD；版本锚点一致；发布批准记录 | phase-5-evidence.md（门禁汇总 + 批准记录） |

### 3.3 下阶段恢复读取协议（Resume Protocol）

下一阶段 Codex 会话开始工作时，必须按以下顺序读取（避免上下文漂移）：
1. 权威 SKILL（C:/Users/32893/.agents/skills/decretum-matrix/SKILL.md）；
2. 本机能力索引筛出的当前任务相关 skill，优先 `stop-that-shit`、`using-superpowers` / Superpowers、`ponytail`、可用 handoff skill；
3. 如需承接前一会话，先用 `context-restore` 补齐 saved context；
4. 本计划书（本节）+ 任务书（本阶段任务）；
5. docs/plans/beta1.0.8/handoffs/README.md 与上一阶段 handoff 文档、phase-N-evidence.md（确认 COMPLETED 且无未决阻塞）；
6. git log 最近 10 条 + git status，确认分支与工作树状态与交接声明一致。

读取后若发现交接声明与实际不符（如门禁实际红、文件缺失），立即按协议草案的失败处理流程：停止推进 → 记录 BLOCKED → 交由上级评审，不擅自"修复性继续"。

## 4. 风险登记册

| 风险 | 概率 | 影响 | 缓解 |
| --- | --- | --- | --- |
| R-1 工作树 5 文件为未完成实验，提交后破坏门禁 | 中 | 高 | E1 先评审定夺；发布前工作树必须干净 |
| R-2 IKU 历史值语义不明导致误改 | 中 | 高 | 只读发现先行；无 receipt/冲突/不明一律 REVIEW；门下复核为门 |
| R-3 Codex host proof 无法在目标环境复现 | 中 | 中 | 回退 inherit + degraded 兜底；证明字段版本绑定；不依赖 CI |
| R-4 领域化 MCP 适配破坏权限/只读/审计契约 | 低 | 高 | manifest side_effect、ACL、authority、write_set、Git receipt 和探针强制；零子进程回归 |
| R-5 court_runtime 拆分引入回归 | 中 | 中 | 拆分子模块先于特性；门禁全量回归；不追求一次拆完 |
| R-6 版本锚点再次漂移 | 低 | 中 | P5-2 统一检查；check_release_manifest 增加锚点断言 |
| R-7 无 CI 导致门禁漏跑 | 高 | 中 | 本版本至少落地一个 source-gate workflow（P0 增补项） |
| R-8 交接文档与实际状态漂移（Codex 自交接风险） | 中 | 高 | 协议草案强制 handoff-check 校验；恢复读取协议比对 git 状态；BLOCKED 走评审不擅自继续 |

## 5. 测试计划

1. 单元：public_* 纯函数、IKU 候选/修复、分类合同、模型路由——随任务提交（不新增巨型 check 文件）。
2. 集成：check_court_mcp_server（最终工具矩阵、Agent envelope、ACL/authority/write_set、Git commit、现代/legacy）；check_shiguan_lineage_*；GBrain/记忆 fixture；check_court_model_router；既有回归全量。
3. 门禁：P5-1 的 22 项清单。
4. 一致性：现有通用 MCP stdio 的现代/legacy 语义一致性；HTTP/Resources 不纳入当前 skill 核心。
5. 安全回归：shiguan_http（entry.id 穿越用例）、read_only_contract、package_privacy。
6. 交接回归：phase-N-handoff.md / phase-N-evidence.md / README 索引三件套一致；任务书阶段状态和验收证据摘要已回写；`context-save` / `context-restore` 流程可复核。

## 6. 发布门禁清单（P5-1 执行，全部勾选才发布）

- [ ] 工作树干净（子仓库与根）
- [ ] repo-control doctor 无 WARN
- [ ] quick_validate.py . PASS
- [ ] check_read_only_contract.py PASS
- [ ] check_source_state_budget.py --json ok:true
- [ ] check_release_manifest.py --json PASS
- [ ] check_governance_framework.py 48+ checks PASS
- [ ] check_court_mcp_server.py 全部探针 PASS
- [ ] check_skill_identity.py PASS 且声明 sha 绑定
- [ ] release-manifest / SBOM / VERSION / CHANGELOG / README / wiki 锚点一致 beta1.0.8
- [ ] source-final / install-host-closeout 收据重生成并绑定当前 HEAD
- [ ] 发布批准记录（门下复核）

## 7. 变更管理

- 本文档为基线；范围/排期/验收变更须更新本文并留版本行。Q23 问卷已审查采纳；HTTP/Resources 不进入本版核心。
- 任何「由 MCP 发起写操作」的提议必须先满足开发文档 A2 全部前置条件并单独立项评审。
- 版本号提升只在发布批准时进行（workspace.yaml + VERSION 同步）。
- Handoff 协议草案允许 Codex 按自身环境完善：完善须保持协议核心（状态模型、制品 schema、校验、失败处理）不变，扩展点以附录方式追加并记录理由。

## 8. 完成定义（DoD）复述

1. 四类证据（代码 / typed tests / 安装投影 / runtime receipt）绑定 release/beta1.0.8；
2. 门禁全绿、工作树干净、doctor 无 WARN；
3. 新能力条目从 [PLANNED_UNVERIFIED] 提升需走 evidence receipt 流程（AGENTS.md 契约）；

## 9. 交接加载与阶段回写

- 交接时加载：`decretum-matrix` skill、`stop-that-shit`、`using-superpowers` / Superpowers、`ponytail`、可用 handoff skill、`context-restore` / `context-save`，再读本计划书、任务书、上一阶段 handoff 文档与 evidence 文档。

- 每个阶段完成后，必须把任务书对应阶段状态标记为 `COMPLETED` 或 `BLOCKED:<原因>`，并把验收证据摘要回写任务书；完整输出仍写入 `phase-N-evidence.md`。

- 阶段开始和结束都要把上下文边界与交接边界分开处理，别把 saved context 当成正式交接证据。

## 10. MCP 访谈决策记录

- Q1（暂定）：保留现有 court_mcp_server 通用 MCP 入口，并在该入口上做适配与新增功能。
- 后续访谈可覆盖工具清单、读写边界、传输层、入口数量和排期；覆盖后须同步五份文档并更新交接证据。
