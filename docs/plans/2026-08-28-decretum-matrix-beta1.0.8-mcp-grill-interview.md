# beta1.0.8 MCP 开发访谈记录（全量问题）

> 状态：进行中，逐题确认，未定稿
> 日期：2026-08-28
> 用途：记录本次基于诏令矩阵项目与五份计划文档的全部 MCP 需求问题、用户回答、暂定判断、影响面和变更原因。

## 访谈控制规则

- 本文件覆盖本次访谈的全部问题，不只记录下一题。
- 每次只提出一个高影响问题；新问题先写入本文件，再向用户提问。
- 用户回答后，补写原意、暂定判断和影响面；后续回答可以覆盖暂定判断，但必须保留旧判断和变更原因。
- 访谈期间不回写或撤销已经合并进五份计划文档的内容；那些内容保持现状。
- 访谈结束后，以本文件的最终定稿为依据，统一整理合并到开发文档、执行计划书和任务书。
- 总纲索引与 Handoff 协议草案不作为本轮最终合并目标；如最终需求影响它们，再单独记录同步项。

## 输入背景与最终合并目标

本访谈以诏令矩阵项目及以下五份既有文档为背景：

1. 2026-08-28-decretum-matrix-next-version-iku-lineage-codex-model-predevelopment.md
2. 2026-08-28-decretum-matrix-beta1.0.8-development-spec.md
3. 2026-08-28-decretum-matrix-beta1.0.8-task-book.md
4. 2026-08-28-decretum-matrix-beta1.0.8-execution-plan.md
5. 2026-08-28-decretum-matrix-beta1.0.8-codex-handoff-protocol-draft.md

访谈完成后，最终定稿只合并到：开发文档、执行计划书、任务书。

## Q1：首轮范围理解

**问题**：1.0.8 的 MCP 是先只做只读工具面，还是连 HTTP /mcp 传输入口一起做？

**用户回答**：现在应该只需要做诏令矩阵它自身的工具即可。

**暂定判断**：首轮范围理解偏向诏令矩阵自身工具；是否涉及 HTTP /mcp、Resources、写能力等，不能由本题单独定稿。

**状态**：已回答，暂定。

## Q2：现有通用 MCP 入口

**问题**：是否保留现有通用 MCP 入口，并在这个入口上做适配和新增功能？

**用户回答**：肯定是保留这个现有的通用接口，并且在这个通用接口做适配，以及新增功能。

**暂定判断**：现有通用 MCP 入口是当前实现起点；诏令矩阵自身工具通过该入口适配和扩展。

**影响面**：会影响 FR-D、court_mcp_server、manifest 投影、public API、探针、Phase 2 和 P2 任务；具体工具清单仍待确认。

**状态**：已回答，暂定。

## Q3：边界是否冻结

**问题**：是否把“保留现有通用入口、只扩展自身工具、暂不扩展其他传输或能力”写成 1.0.8 的固定边界？

**用户回答**：后续提问中这个边界有可能改变，暂时不要先写死。

**暂定判断**：Q1 和 Q2 只作为访谈中的当前假设；工具清单、读写边界、传输层、入口数量和排期均可被后续回答覆盖。

**已合并文档处理**：此前已经写入五份文档的内容不撤销、不回滚；访谈结束后以最终定稿统一校正三份目标文档。

**状态**：已回答，暂定，不冻结。

## Q4：首批能力优先级

**问题**：在保留现有通用 MCP 入口作为当前起点的前提下，1.0.8 首批要优先适配哪些诏令矩阵自身能力？请按优先级回答，可多选并排序：

- A：状态与查询（court status、命令帮助、基础只读查询）
- B：语义与契约校验（intake、capsule、semantic context、dispatch plan）
- C：官署调度与计划能力（只读计划检查、任务边界检查、交接准备）
- D：史馆与记忆能力（entries 查询、archive dry-run、memory scan）
- E：IKU 候选发现与治理辅助
- F：其他能力（请直接写名称）

**用户回答**：史馆与记忆查询肯定要接入 MCP；A、B、C、E 也可以接入，但需要判断哪些更适合。重点是接入史馆此前提到的能力索引查询，让 MCP 可以主动调用，从而更积极地调用 skill。MCP 不应局限于只读，部分场景需要与数据库操作等同的能力。

**暂定判断与推荐**：

| 能力 | 推荐 | 原因 |
| --- | --- | --- |
| D 史馆与记忆查询 | P0，最高优先 | 已有明确需求；可作为能力索引、历史证据和上下文恢复的统一查询面，直接支撑 MCP 主动选择 skill。默认仍需遵守 pending/private 和 advisory 边界。 |
| A 状态与查询 | P0 | 低风险、确定性强，适合 MCP 工具；可作为其它工具的状态前置检查。 |
| B 语义与契约校验 | P0 | 与诏令矩阵核心治理规则直接对应，适合纯函数化、结构化错误和可复验探针。 |
| E IKU 候选发现与治理辅助 | P1 | 适合先做只读候选发现，能复用现有扫描逻辑；任何实际修复必须另走授权路径。 |
| C 官署调度与计划能力 | P1，限制接入 | 适合接入计划验证、边界检查、交接准备和 dry-run；真实调度、spawn、写入和权限变更不能由普通 MCP 调用绕过三省六部与 agent-admit。 |
| 数据库等同操作 | P1/P2，受控写能力 | 需求合理，但不能直接做无边界 CRUD；应按操作分级、权限、事务、幂等、审计、回滚和 approval/autonomous/super 约束设计。先定义安全最小子集，再决定是否进入 1.0.8。 |

推荐顺序：D（含能力索引查询）→ A/B → E → C（只读/预览）→ 受控数据库操作。

**能力索引主动调用建议**：新增能力索引查询工具，至少支持按 skill 名称、任务语义、触发条件和路径返回候选；MCP 调用前先查询能力索引，再由调用方记录实际加载的 skill、路径和理由。该工具只提供选择依据，不自动突破 skill 的加载、权限或项目边界。

**现有实现锚点**：复用 `scripts/check_capability_index_gate.py --query <need>` 的查询语义与 `scripts/refresh_capability_registry.py` 生成的本机能力官籍，不建立第二套能力索引。MCP 工具负责返回有界候选、匹配理由、来源与 skill 路径；真正加载 skill 仍由宿主 Skill 机制执行。能力索引刷新属于受控变更，不能伪装成只读查询。

**影响面**：需要重新审视 FR-D 的工具分层、能力索引 manifest、MCP 主动调用机制、C 的调度权限边界、数据库操作的写入授权与审计，以及 Phase 2/3 的任务拆分和验收证据。

**状态**：已回答，推荐待用户确认。

## Q5：数据库四类操作的首批数据域

**问题**：你所说的数据库四类操作（Create / Read / Update / Delete），1.0.8 首批主要要作用于哪类数据？可多选，但请指出第一优先级：

- A：史馆条目与记忆记录
- B：能力官籍 / skill、MCP、CLI、agent 能力索引
- C：任务、阶段、handoff 状态与验收证据
- D：诏令编号、谱系与分类元数据
- E：通用数据库对象，由调用时指定表或集合
- F：其他，请直接写数据对象

**推荐**：优先 A 和 C；B 只允许通过注册/刷新流程更新生成源，不直接 CRUD 生成索引；D 的编号禁止任意创建或修改，只允许统一史馆 receipt 路径；不推荐 E，因为通用表级 CRUD 会绕过领域校验、权限和审计。

**用户回答**：上述列出的数据域都应当作为作用域。

**暂定判断**：A–E 全部纳入 MCP 数据能力的需求作用域，包括史馆条目与记忆、能力官籍、任务/阶段/handoff/验收证据、诏令编号/谱系/分类元数据，以及将来需要接入的其他数据库对象。

**设计建议**：作用域可以覆盖全部数据域，但不建议暴露一个可传入任意表名、集合名或 SQL 的通用 CRUD 工具。应按领域提供 Create / Read / Update / Delete 的同等能力，并复用各自权威写入路径：

- 史馆与记忆：通过史馆受控写入、记忆裁定和 archive receipt；pending/private 继续受保护。
- 能力官籍：读取生成索引；创建、更新和删除通过注册、招募、刷新和退役流程修改权威源，再重建投影，不直接改生成索引。
- 任务、阶段、handoff 与验收证据：通过状态机、阶段标记和 evidence/handoff 制品更新，禁止跳跃状态。
- 诏令编号、谱系与分类元数据：允许领域化查询和受控修正；诏令编号只能由统一 shiguan archive-checkpoint receipt 产生，MCP 不分配第二套编号。
- 其他数据库对象：先登记数据域、主键、允许操作、授权规则、幂等键、事务/回滚和审计 schema，再进入 MCP 工具清单。

**边界说明**：这里确认的是“需求作用域包含全部数据域”，不是确认每个数据域在 beta1.0.8 都一次性实现完整 CRUD；版本内交付批次仍需后续访谈排序。

**影响面**：决定是否新增 MCP 写工具、每个工具的授权级别、幂等键、事务/回滚、软删除与审计 receipt，以及是否必须拆出独立写入阶段。

**状态**：已回答，全部数据域纳入作用域；实现批次与授权模型待确认。

## Q6：MCP 写操作授权模型

**问题**：对上述全部数据域的 Create / Update / Delete，你希望采用哪种授权模型？

- A（推荐）：读取在普通只读边界可用；Create/Update 只有在当前会话明确选择 autonomous 或 super、且操作命中声明的 write_set 时执行；Delete 默认软删除并要求门下/人工批准，硬删除不通过 MCP 开放。
- B（最保守）：所有 Create/Update/Delete 每次都必须人工批准；MCP 只负责生成变更计划和确认后的执行令牌。
- C（更自动）：按数据域和官署角色授予持久权限；命中角色权限即可写入，只有高风险删除再批准。
- D：其他授权方式，请说明。

**推荐原因**：A 与诏令矩阵现有 approval/autonomous/super 三权和 write_set 契约一致，既能让 MCP 真正执行受控数据库操作，也不会让一次工具调用绕过当前会话的授权、门下复核、审计和回滚边界。

**用户回答**：选择 C。按数据域和官署角色授予持久权限；命中角色权限即可写入，只有高风险删除再批准。

**暂定判断**：采用基于官署角色与数据域的持久权限模型。权限至少绑定 role、data_domain、operation（Create / Read / Update / Delete）、风险等级和适用写集；普通已授权操作可直接执行，高风险删除进入额外批准流程。不得用通用数据库凭据或任意表级权限替代领域授权。

**设计约束**：持久权限只表示某官署对某数据域操作的资格，不自动证明当前调用者身份、当前任务边界或操作审计已经满足。每次调用仍须验证官署身份、直接上级、数据域、操作类型、目标主键/写集、幂等键，并产生可追溯 receipt。

**影响面**：决定 MCP 写工具的调用前门禁、令牌/receipt、软删除与硬删除语义、事务回滚、审计字段和反例测试。

**状态**：已回答，选择 C；与当前会话三权的优先关系待确认。

## Q7：持久角色权限与当前会话三权的优先关系

**问题**：当某官署拥有持久写权限，但当前会话选择的是 approval（只读）时，MCP 是否仍可执行写操作？

- A（推荐）：不可执行。持久角色权限决定“有资格做什么”，当前会话的 approval / autonomous / super 决定“这次最多能做什么”；两者取更严格者。approval 始终只读。
- B：可以执行。只要角色持久权限命中，即使当前会话是 approval 也可写入。
- C：按数据域例外；低风险域可写，高风险域仍受当前会话三权限制。
- D：其他规则，请说明。

**推荐原因**：A 保留现有三权契约，使持久 ACL 不会把用户本次明确选择的只读会话悄悄升级成写会话，同时仍让 autonomous / super 下的合格官署自动执行已授权操作。

**用户回答**：同意 A。持久角色权限与当前会话三权取更严格者，approval 始终只读。另外，史馆记忆和能力索引账册正常应当同时具备读写权限；删除需要另一套尚未完成的记忆整理能力，本期暂不考虑。

**暂定判断**：采用双重门禁。持久角色权限定义官署对数据域和操作的资格；当前会话的 approval / autonomous / super 定义本次调用上限。两者取更严格者：approval 只读；autonomous / super 仅可在角色 ACL、data_domain、operation 和 write_set 同时命中时执行写入。

**本期操作边界**：

- 史馆记忆账册：开放领域化 Create / Read / Update；Delete 不进入 beta1.0.8。
- 能力索引账册：开放领域化 Create / Read / Update；生成索引建议通过权威登记源写入后刷新投影，不直接篡改生成文件；Delete/退役流程不进入 beta1.0.8。
- 删除能力、记忆整理、合并、去重、清退和硬删除作为独立后续能力设计；本期 MCP 不提供伪删除或绕过路径。
- 对未开放的 Delete 调用应结构化拒绝并返回 operation_not_supported / cleanup_capability_not_available，不产生数据变更。

**影响面**：决定权限判定公式、MCP 调用前门禁、角色 ACL schema、approval 只读回归测试，以及是否需要为低风险写操作定义例外层。

**状态**：已回答；approval 只读，史馆记忆与能力索引账册本期开放 Create / Read / Update，Delete 与记忆整理顺延。

## Q8：账册 Update 的历史保留语义

**问题**：史馆记忆和能力索引账册执行 Update 时，应当直接覆盖原记录，还是保留旧版本并追加新修订？

- A（推荐）：追加不可变修订，保留旧版本和 revision 链，由 current 指针指向最新版本；支持审计、回退和解释“为何改变”。
- B：原地覆盖，但写入前保存 before-image 和审计 receipt；实现较简单，但查询历史和恢复更依赖备份。
- C：按数据域区分；史馆记忆追加修订，能力索引原地更新后重建投影。
- D：其他方式，请说明。

**推荐原因**：A 最符合史馆可追溯性，也适合能力官籍变更；在删除/记忆整理尚未实现时，追加修订可以避免 Update 变成事实上的数据丢失。生成投影仍可覆盖重建，但权威账册保留版本链。

**用户回答**：选择 A。并补充确认：整个史馆，包括记忆库和能力索引，都应由 Git 仓库进行治理。

**暂定判断**：权威账册采用追加不可变修订，保留旧版本、revision 链和 current 指针；能力索引的生成投影可以覆盖重建，但权威登记源和修订历史必须保留。

**Git 治理判断**：史馆、记忆库和能力索引属于 Git 治理范围。Git 提供版本历史、差异、回退和跨机器 provenance；MCP 数据操作仍必须通过领域写入函数和现有史馆 Git federation/事务边界，不直接操作任意 Git 对象或任意仓库路径。Git 提交是治理证据，不等于自动授予 MCP 写权限。

**当前已核实的项目依据**：

- `references/court-shiguan-memory.md` 将 shared Shiguan、`plan-archives/`、`memory-decisions/`、`shiguan-tree/` 和 native memory stores 纳入 Git federation 语义。
- `references/court-capability-registry.md` 将 skill、MCP、CLI、script 和 agent 登记为官籍，并要求通过 `refresh_capability_registry.py` 刷新能力索引。
- `scripts/shiguan_git_federation.py` 已有 shared/native store、pathspec、transaction、commit、branch/HEAD 和 dirty-state 校验。

**边界说明**：本题确认 Git 是这些账册的治理与审计底座；尚未确认 MCP 写入后的提交时机、提交者身份、批次策略和冲突处理方式。

**影响面**：决定账册 schema、revision_id、supersedes/current 指针、并发冲突检测、回滚、查询默认版本和审计验收。

**状态**：已回答；采用不可变修订，并确认史馆、记忆库、能力索引由 Git 治理；提交策略待确认。

## Q9：MCP 写入后的 Git 提交时机

**问题**：当 MCP 对史馆记忆或能力索引账册执行 Create / Update 后，Git 应如何提交？

- A（推荐）：每次成功的领域写操作形成一个独立 Git commit，并在 receipt 中绑定 commit、revision、actor、task、phase 和 operation；失败不提交。
- B：同一任务/阶段内先累计多个成功操作，阶段验收或 handoff 时批量提交；中间状态只保留事务日志。
- C：按数据域区分；史馆记忆每次提交，能力索引在刷新完成后批量提交。
- D：其他策略，请说明。

**推荐原因**：A 最容易审计和回滚，也与史馆现有 transaction、branch/HEAD、dirty-state 和 receipt 绑定契约一致；若提交频率过高，再在实现阶段用明确的批次键扩展，而不是先丢失操作级 provenance。

**用户回答**：选择 A。每次成功的领域写操作单独提交 Git commit。

**暂定判断**：每次成功的领域写操作形成独立 Git commit，并在 receipt 中绑定 commit、revision、actor、task、phase 和 operation；失败不提交。MCP 不留下无法归属的未提交账册变更。

**关于“记忆裁定”的判断**：这属于记忆裁定相关能力，但 Git 提交本身不等同于记忆裁定。

- **仓库生效**：领域写入成功并完成 Git commit，表示该账册修订进入受管仓库状态，可被版本历史、差异和回滚机制识别。
- **记忆生效**：必须另有 `memory_decision`（`WRITE | PROPOSE | SKIP | DEFERRED`）及对应授权/评审证据；只有允许 durable writeback 的裁定，才能把内容视为正式记忆。
- **能力索引生效**：应绑定权威登记源的修订、Git commit 和索引刷新 receipt；生成索引是投影，不以直接修改生成文件作为权威。
- **组合 receipt**：MCP 写操作应同时记录 `memory_decision` 或数据域对应的治理决策、domain revision、Git commit、actor、authority、write_set、task/phase 和审计摘要。没有裁定的内容可以作为候选或证据提交，但不得声称已成为正式记忆。

因此，建议把 MCP 的写入流程建模为“候选/变更意图 → 记忆或领域裁定 → 领域写入 → 单操作 Git commit → receipt 绑定”，而不是把 commit 当作裁定。

**影响面**：决定 Git commit 粒度、MCP receipt schema、并发冲突、失败回滚、handoff 阶段边界，以及是否允许 MCP 留下未提交工作树。

**状态**：已回答；每次成功领域写操作单独提交。Git 持久化与记忆裁定相关但不等同，是否每次写入都必须先有显式裁定待确认。

## Q10：MCP 写入是否强制显式记忆裁定

**问题**：对于 MCP 对史馆记忆账册、能力索引账册和其他史馆受管数据的 Create / Update，是否每次都必须先产生显式治理裁定，再允许写入和 Git commit？

- A（推荐）：史馆记忆内容每次必须有 `memory_decision`；能力索引和任务/元数据使用各自领域裁定，不强行套用 `memory_decision`；低风险领域写可在命中持久 ACL 与当前会话权限后直接执行，但 receipt 必须记录领域决策。
- B：所有受管数据每次统一要求门下/人工裁定后才写入和提交。
- C：只有涉及 durable memory 的写入需要显式裁定，能力索引和任务元数据可直接按 ACL 写入并提交。
- D：其他方式，请说明。

**推荐原因**：A 能保留史馆记忆的语义审查，同时不把能力索引、任务状态等非记忆数据硬套成记忆；所有领域仍有可审计的决策字段和 Git receipt。

**用户回答**：选择 A/B 混合。部分操作必须经过人工授权和裁定。另外，当前记忆库应当属于 GBrain 模式架构，虽然可能不是标准实现，但可以作为参考；记忆的升降级以及如何允许内容成为正式记忆，应当更深入地接入 MCP；同时要求查找现有的类 GBrain 案例。

**暂定判断**：采用按数据域、风险和记忆生命周期分层的 A/B 混合裁定，而不是所有写入统一走同一个门。

**裁定分层**：

- 低风险、非 durable-memory 的领域写入：命中持久 ACL、当前会话权限和 write_set 后可自动执行；receipt 必须记录领域决策。
- 史馆 durable memory 的 Create / Update：必须产生 memory_decision，并按候选、待审、批准、已生效、降级、替代等状态治理。
- 记忆升档、降档、成为正式记忆、跨来源合并、冲突裁定和影响范围扩张：必须人工/门下授权；MCP 负责生成候选、评分、差异和裁定请求，不得静默升档或降档。
- Delete、记忆整理、合并、去重和清退：继续不进入 beta1.0.8，待独立记忆整理能力完成后再接入。
- Git commit 表示修订已持久化；memory_decision=WRITE 或等价领域裁定表示允许成为正式记忆；两者必须在 receipt 中绑定。

**GBrain 现状判断**：当前项目已经具备 GBrain 风格的参考架构，但不宣称兼容某个外部标准。query_shiguan_index.py 提供 advisory recall；memory_decision.py 管理 WRITE / PROPOSE / SKIP / DEFERRED；court-shiguan-memory.md 与 Architecture 文档定义 metadata-first、来源保留、冲突保留、时效判断、Git federation 和 execution_authority=false。因此本轮称其为“Decretum Matrix 的 GBrain-mode 史馆记忆架构（项目内参考实现）”，不把它描述为标准 GBrain 产品或已完成的端到端记忆闭环。

**MCP 接入建议**：将记忆生命周期拆为可审计工具族：memory.candidate_propose、memory.recall、memory.evaluate、memory.promote、memory.demote、memory.revise、memory.decision_status。recall / candidate / evaluate 可按权限自动运行；promote / demote / revise 在命中人工/门下授权后执行；每次调用绑定 candidate_id、revision_id、decision_id、Git commit 和 receipt。名称只是当前设计候选，尚未冻结。

**类 GBrain 案例对照（已检索）**：

| 案例 | 可借鉴机制 | 对本项目的启示 |
| --- | --- | --- |
| Graphiti / Zep | 面向 agent 的时间知识图谱；支持 episode 写入、实体/事实检索、时间有效性、来源 provenance 和 MCP server | 借鉴事件/事实、时间窗口、来源和 MCP 检索/写入；不替代本项目的 Git 账册和门下裁定。 |
| Letta Memory | 将 memory blocks 与 archival memory 分层，并让 agent 通过工具读写持久记忆 | 借鉴工作记忆/归档记忆分层和显式 memory 工具；本项目仍叠加角色 ACL、三权和 Git receipt。 |
| Mem0 | 提供记忆新增、更新、检索等生命周期接口，并处理记忆抽取与更新 | 借鉴生命周期工具化；本项目的更新、升降级和未来删除仍受领域裁定、版本链和记忆整理能力约束。 |

这些案例仅用于架构对照，不证明本项目已实现同等能力；最终仍以代码、typed test、安装投影和 runtime receipt 四类证据为准。

**影响面**：决定 MCP 写工具的前置流程、领域裁定 schema、receipt 字段、门下审批范围、低风险自动写入边界和回归测试。

**状态**：已回答；采用 A/B 混合裁定。当前 GBrain 为项目内参考架构；记忆升降级与成为正式记忆的流程纳入 MCP 设计重点，具体状态机和人工门禁待继续确认。

## Q11：GBrain 记忆状态机与升降级触发

**问题**：记忆从候选到正式记忆，以及后续升档/降档，首批希望采用哪种状态与触发模型？

- A：全部人工裁定。MCP 只生成候选、评分和差异；任何成为正式记忆、升档或降档都由人工/门下批准。
- B：评分自动裁定。达到阈值自动成为正式记忆，低于阈值自动降级；仅高风险项人工复核。
- C（推荐）：混合状态机。MCP 自动执行召回、评估和提出升降级建议；CANDIDATE → REVIEW → APPROVED → ACTIVE，以及 ACTIVE → DEGRADED / SUPERSEDED 的正式转换必须人工/门下批准；纯证据补充和评分更新可自动提交新 revision。
- D：其他方式，请说明。

**推荐原因**：C 能让 MCP 积极参与记忆治理，同时保留门下对正式记忆身份和升降级的最终裁定权；评分是证据，不单独取得 durable-memory 写入权。

**用户回答**：同意混合状态机，但要求进一步细化。MCP 的召回、查询和建议必须极高效；召回字段需要分层数据清洗；冲突察觉、过期察觉、升档和降档均应高效。本轮设计只作为参考，要求继续调查现有案例。

**暂定判断**：采用可审计的混合状态机，并将高频召回与深度治理拆成两条路径：

```text
CANDIDATE → REVIEW → APPROVED → ACTIVE
ACTIVE → DEGRADED | STALE | SUPERSEDED
DEGRADED/STALE → REVIEW
```

**细化设计（当前候选）**：

1. **召回快路径**：先查本地、确定性、元数据索引，不先读正文，不启动 LLM、网络或完整 Git 扫描；按 task/domain/keyword/lineage/time/status 过滤，返回有界 top-k。只有快路径不足或发生争议时，才进入深查询。
2. **召回字段清洗**：每条结果至少返回 `memory_id`、`record_type`、`summary_zh`、`summary_en`、`keywords`、`lineage`、`decision_state`、`confidence`、`source_ref`、`valid_at`、`invalid_at`、`expired_at`、`stale_state`、`conflict_set_id`、`supersedes`、`revision_id`、`git_commit` 和 `evidence_ref`。正文、私密字段和 pending body 默认不返回。
3. **分层清洗**：写入或索引刷新时完成 UTF-8/替换字符检查、字段规范化、时间标准化、敏感信息与私密正文边界检查、重复指纹、摘要与关键词生成、来源和 revision 绑定。清洗失败进入 `REVIEW` 或 `DEGRADED`，不得静默成为 ACTIVE。
4. **冲突察觉**：以 subject/key/relation 和有效时间窗口建立 conflict set；相互矛盾的修订并列保留，显示来源、时间、置信度与 supersedes 关系，不直接覆盖。最新用户旨意优先；冲突集合只能生成裁定建议，不能自动取得正式记忆写入权。
5. **过期察觉**：依据 `valid_at`、`invalid_at`、`expired_at`、来源新鲜度和最新 revision 生成 ACTIVE、STALE、EXPIRED 或 SUPERSEDED 建议；检测只更新建议或索引状态，正式降档仍按人工/门下裁定执行。
6. **升降档建议**：MCP 自动计算证据数量、来源一致性、时间新鲜度、召回命中、冲突数量和用户/门下反馈，生成 promote/demote proposal；成为正式记忆、升档、降档、冲突裁定和跨域扩张必须人工/门下批准。
7. **增量与追溯**：只重算受影响的 revision、subject、conflict set 和时间桶；每次建议、裁定、领域写入和 Git commit 均绑定 candidate_id、decision_id、revision_id、actor、authority、task/phase 和 receipt。普通召回不得依赖全量 Git status 扫描。

**效率建议**：采用“本地元数据索引 → 词法/关键词候选 → 可选语义或图关系重排 → 结构化裁定建议”的渐进路径。默认返回小 top-k、稳定排序、摘要缓存和增量失效标记；深度抽取、冲突解释和升降档建议放入显式 evaluate/propose 工具，不阻塞普通 recall。

**案例复核（官方资料）**：

- [Graphiti / Zep 概览](https://help.getzep.com/graphiti/getting-started/overview)：时间知识图谱支持实体、关系和事实随时间演化。
- [Zep Facts](https://help.getzep.com/facts)：事实带 `created_at`、`valid_at`、`invalid_at`、`expired_at`，用于保留有效区间和失效历史。
- [Graphiti Searching](https://help.getzep.com/graphiti/working-with-data/searching)：采用语义相似度、BM25、Reciprocal Rank Fusion 和可选节点距离重排。
- [Zep Concepts](https://help.getzep.com/concepts)：强调 token-efficient context 与亚 200ms 级受治理检索；该数值仅作外部性能参考，不是本项目当前实测。
- [Zep/Graphiti 论文](https://arxiv.org/abs/2501.13956)：给出时间知识图谱记忆与 LongMemEval/DMR 评估，可作为召回质量和延迟基准设计参考。

**案例启示**：可借鉴时间有效性、事实失效、混合检索、冲突保留和 token-efficient context，但继续使用本项目自己的 Git 账册、memory_decision、三权/ACL、门下裁定和四类证据门禁。外部案例不证明 Decretum Matrix 已实现同等能力。

**影响面**：决定 memory lifecycle schema、MCP promote/demote 工具、评分与证据字段、人工审批点、Git receipt、冲突处理和回归 fixture。

**状态**：已回答并同意；状态机已细化为当前候选设计，性能 SLO、索引介质和清洗阈值待确认。

## Q12：MCP 召回与建议的性能基线

**问题**：1.0.8 是否要为 MCP 的普通召回、查询和建议接口设定明确性能基线？

- A（推荐）：快路径本地化、无网络、无 LLM 阻塞；top-k ≤ 20 时目标 P95 ≤ 200ms；深度冲突解释和升降档建议异步或显式调用，不阻塞普通 recall。
- B（严格）：快路径目标 P95 ≤ 100ms，并将常用元数据索引常驻内存；准确性不足时再降级到深查询。
- C（优先正确性）：本期不设硬延迟，只要求结果稳定、字段清洗完整、冲突和过期不漏报。
- D：其他性能目标，请说明数据规模、并发量和可接受延迟。

**推荐原因**：A 能把高频召回与高成本治理解耦，给出可验收的效率目标，又不迫使首版引入新的向量数据库或后台服务；B 可作为后续压测达标后的优化目标。

**用户回答**：同意双层性能基线：普通召回以 P95 ≤ 100ms 为优化目标，以 P95 ≤ 200ms 为 beta1.0.8 发布硬门禁；深度冲突解释、过期深查和升降档建议走独立工具，不阻塞普通召回。

**暂定判断**：普通 recall/query 快路径必须本地化、无网络、无 LLM 阻塞、无完整 Git 扫描；在约定基准数据集上，top-k ≤ 20 时 P95 ≤ 100ms 为优化目标，P95 ≤ 200ms 为发布硬门禁。深度 evaluate/propose 工具以正确、可取消、可审计为首版门禁，暂不设置未经实测支撑的固定延迟上限。

**验收建议**：性能测试必须固定数据规模、冷/热缓存状态、并发度、查询类型和重复次数；报告 P50/P95/max、召回结果稳定性、冲突/过期检测正确率及是否触发深查询。不得用空索引或单条 fixture 证明性能达标。

**影响面**：决定索引结构、缓存策略、并发模型、MCP 工具拆分、benchmark/typed test、阶段门禁和是否允许引入额外存储依赖。

**状态**：已回答并同意；双层性能基线确认，索引介质与基准数据规模待确认。

## Q13：快路径索引介质（待回答）

**问题**：为满足普通 MCP 召回的 100ms 优化目标和 200ms 发布门禁，beta1.0.8 首批采用哪种索引实现？

- A（推荐）：Git 治理的 JSONL/结构化账册继续作为权威源；MCP 进程启动或 revision 变化时构建紧凑的进程内倒排索引与元数据缓存，按 Git commit/mtime/revision 增量失效；不新增数据库依赖。
- B：新增 SQLite/FTS 派生索引作为本地查询层；Git 仍治理权威账册，SQLite 只作为可重建缓存，不提交到 Git。
- C：直接引入向量数据库或图数据库，使用混合检索；Git 保存权威账册和 provenance。
- D：其他索引介质，请说明。

**推荐原因**：A 最贴合当前 `shiguan-index.jsonl`、能力索引和长驻 MCP 进程，改动最小，能先用确定性词法/字段过滤验证 100/200ms 基线；只有基准证明 A 无法满足规模与准确性时，再升级到 B。C 对 beta1.0.8 过重，也会引入新的服务、同步和故障边界。

**用户回答**：A、B、C 三个方案混合采用。当前项目本身已经有一定的类向量数据库形式，应当继续优化；即使使用 SQLite，也不能打乱 Obsidian 的同步模式。用户确认记得的 P 开头项目应是 PostgreSQL，并要求继续完善 ABC 整合方案。

**暂定判断与整合方案**：采用三层混合检索，但只保留一个权威源：

| 层 | 组件 | 权威级别 | 作用 |
| --- | --- | --- | --- |
| A 源与快路径 | Git 治理的 Markdown/JSONL 账册、shiguan-index.jsonl、现有稀疏能力向量、进程内倒排/元数据缓存 | 权威 | 稳定、低延迟、无服务依赖的普通 recall/query；按 Git commit、revision 和 mtime 增量失效。 |
| B 结构化查询投影 | SQLite/FTS 或 PostgreSQL relational/FTS 投影 | 派生缓存 | 结构化过滤、审计查询和较大数据量检索；可重建、可丢弃，不得成为第二账册。 |
| C 语义与图检索投影 | capability_vector_sparse、shiguan-knowledge-graph.json，以及可选 PostgreSQL + pgvector / ParadeDB pg_search | 派生增强 | 能力谱系、实体关系、语义相似度、BM25 与混合重排；只返回带 source revision 的候选。 |

当前项目已有 capability_vector_terms、capability_vector_text、capability_vector_sparse、embedding_text 和轻量多维 JSON 图；这属于确定性稀疏向量/图索引，不是完整通用 embedding 数据库。

**影响面**：决定缓存生命周期、索引重建与增量更新、Git revision 失效规则、冷启动性能、并发安全、部署依赖和 benchmark fixture。

**状态**：已回答并同意 ABC 混合；A 层必选，B 层可重建，C 层先优化现有稀疏向量/图索引，可选 PostgreSQL + pgvector/pg_search 增强。PostgreSQL 是否作为 beta1.0.8 可选运行依赖，待确认。

**PostgreSQL 核查结果**：PostgreSQL 是关系数据库；开源 pgvector 扩展提供向量检索与 HNSW/IVFFlat 索引，ParadeDB 的 pg_search 扩展提供 BM25，可与 pgvector 组成混合检索。它们适合统一结构化过滤、全文、向量和事务边界，但会引入服务、连接、迁移和部署依赖。

**Obsidian 不变式**：MCP 与所有检索投影不得直接写 Obsidian。唯一方向保持“Git 权威账册 → 史馆 JSONL/图/树重建 → Obsidian preserve-only 派生同步”。SQLite、PostgreSQL、向量/图投影只能读取带 source_commit 的权威快照；投影失败只标记 stale/degraded，保留上一个可用投影，不得反向覆盖 Git、史馆或用户笔记。

**同步与 receipt**：领域写入先完成 Git commit，再按该 commit 增量重建 A/B/C 投影；receipt 绑定 source_commit、revision_id、projection_kind、projection_revision、projection_status 和 obsidian_sync_status。投影或 Obsidian 同步完成不能反向证明记忆裁定已通过。

**官方资料对照**：

- pgvector 官方仓库：https://github.com/pgvector/pgvector
- PostgreSQL GIN 文档：https://www.postgresql.org/docs/current/gin.html
- ParadeDB BM25 文档：https://www.paradedb.com/learn/search-in-postgresql/bm25
- ParadeDB 混合检索说明：https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual

这些资料只支持“PostgreSQL + pgvector/pg_search 可作为统一派生检索层”的判断，不证明当前项目已安装、部署或达到既定延迟目标。

## Q14：PostgreSQL 投影的运行依赖级别（待回答）

**问题**：beta1.0.8 对 PostgreSQL + pgvector/pg_search 采用哪种运行依赖级别？

- A（推荐）：可选增强依赖。没有 PostgreSQL 时，A 层本地索引和现有 JSON 图仍必须完整工作；有受治理 PostgreSQL 时启用投影并纳入 benchmark，投影不可用自动降级且不改变权威源。
- B：beta1.0.8 必须部署 PostgreSQL，并把 pgvector/pg_search 纳入发布门禁。
- C：本期只完成接口与投影 schema，不要求部署 PostgreSQL；待真实数据规模压测后再决定。
- D：其他运行依赖策略，请说明。

**推荐原因**：A 保留当前本地、Git 治理和无服务依赖的可用基线，同时给 PostgreSQL 提供明确的加速位置；C 可以作为 A 的前置阶段，但不能替代性能验证。

**用户回答**：选择 A。PostgreSQL + pgvector/pg_search 作为可选增强依赖；没有 PostgreSQL 时，本地索引和现有 JSON 图仍必须完整工作。用户进一步询问 PostgreSQL 是否可以做便携版，或在安装 skill 时一键部署，以避免破坏一键安装体验。

**暂定判断**：采用可选 PostgreSQL 侧车和本地无服务回退。PostgreSQL 不成为 skill 的硬依赖，也不改变 Git/JSONL 权威源和 Obsidian preserve-only 同步链。

**便携性判断**：Windows 可使用 PostgreSQL ZIP 二进制、独立 data 目录和 `initdb`/`pg_ctl` 管理用户态实例；官方 Windows 页面提供不带图形安装器的 ZIP 二进制，`pg_ctl` 支持指定 data 目录的 init/start/stop/status。

**扩展安装现实**：pgvector 是 PostgreSQL 扩展，Windows 构建需要匹配 PostgreSQL、Visual Studio C++ 和 nmake；不能假定安装时总能现场编译。应优先提供与 PostgreSQL 主版本绑定、带 SHA256 的预构建扩展包；缺少匹配包时降级到本地索引和现有稀疏向量/图索引。ParadeDB `pg_search` 需要额外验证主版本、ABI 和包来源，首版不应作为强制安装项。

**一键部署约束**：skill 安装器可以编排 PostgreSQL sidecar，但必须是显式可选步骤：默认只探测，不下载、不启动、不注册服务；仅用户明确授权的 `--apply` 或等价动作才联网下载、校验、解包、初始化和启动；固定版本与 SHA256，失败可回滚；sidecar 只存 B/C 派生投影；凭据、端口、data 目录和生命周期受控；Obsidian 仍只从 Git 权威账册同步。

**官方资料对照**： [PostgreSQL Windows installers](https://www.postgresql.org/download/windows/) 提供 ZIP 二进制；[`pg_ctl`](https://www.postgresql.org/docs/current/app-pg-ctl.html) 支持用户态初始化与启停；[pgvector Windows 安装](https://github.com/pgvector/pgvector#installation) 说明扩展构建依赖；[PGlite](https://pglite.dev/) 是未来可研究的嵌入式替代，不等于当前 sidecar。

**影响面**：决定发布依赖、安装投影、运行时降级、benchmark 环境、连接凭据管理、Obsidian 同步和四类证据绑定。

**状态**：已回答；采用可选增强依赖。便携 PostgreSQL 和 skill 一键部署可行，但必须显式授权、固定版本校验、用户态 sidecar、可回滚、只承载派生投影，不改变 Git 权威源与 Obsidian 同步。部署触发方式待确认。

## Q15：PostgreSQL 一键部署触发方式（待回答）

**问题**：你希望 PostgreSQL 便携 sidecar 在什么情况下部署？

- A（推荐）：安装时默认只探测；用户明确选择“启用 PostgreSQL 增强”并执行带 `--apply` 的一步安装后才下载、解包、初始化和启动；之后按需启动，失败自动降级到本地 A/C-lite。
- B：首次安装 skill 时自动下载并启动 PostgreSQL sidecar，用户只在失败时处理。
- C：skill 安装只提供 sidecar 包和配置，不自动部署；用户另行执行一次 bootstrap 命令。
- D：优先连接已有 PostgreSQL；不存在时再询问是否启用便携 sidecar。
- E：其他触发方式，请说明。

**推荐原因**：A 兼顾一键体验和当前项目的“无未授权联网、安装或宿主写入”门禁；D 可作为 A 的探测顺序。B 会把网络下载、进程和数据目录写入变成隐式 postinstall 副作用。

**用户回答**：史馆 PostgreSQL 必须具备强可迁移性，例如从 C 盘迁移到其他盘；需要审查便携版和连接已有实例哪种更合适。迁移应有专属 CLI 工具，路径不能绝对依赖。对于部署触发采用 B 和 D 混合，默认便携式更符合可迁移需求。

**暂定判断与审查结论**：采用“连接已有 PostgreSQL 优先 + 史馆管理的可迁移便携 sidecar 兜底”，两者共享同一逻辑 store locator 和投影 schema。

| 路线 | 优点 | 风险/限制 | 推荐定位 |
| --- | --- | --- | --- |
| 连接已有 PostgreSQL | 不重复安装，复用现有备份、权限、运维和硬件；更适合长期运行 | 连接凭据、版本、网络/端口和管理员策略不可控；跨盘迁移由外部运维负责 | 首选后端 |
| 便携 sidecar | data 目录可放 C/D/其他盘，生命周期和版本由史馆控制，适合一键增强与离线环境 | 需要携带 PostgreSQL 与扩展包；升级、端口、权限、杀进程和安全更新由项目负责 | 可迁移兜底 |

**迁移方法审查**：`pg_dump/pg_restore` 更适合跨机器、跨架构和版本迁移；`pg_basebackup` 适合同主版本的物理复制，但 plain 格式遇到 tablespace 时会保留绝对路径，迁移必须使用 `--tablespace-mapping`。因此迁移 CLI 默认走逻辑导出/恢复，物理复制只作为经过版本和 tablespace 预检后的加速模式。

**专属 CLI（名称候选）**：建议新增 `court_shiguan_store.py` 或统一 CLI 的 `court shiguan store` 子命令，至少提供 `probe`、`status`、`export`、`import`、`relocate`、`verify`、`rollback`、`start`、`stop`；所有动作输出结构化 receipt，并绑定 `store_id`、source/target locator、source_commit、projection_revision、schema_version、Git commit、校验摘要和回滚点。名称待访谈定稿。

**路径与 locator 约束**：

- 业务和 receipt 只记录逻辑 `store_id`、`backend`、`repository_mode`、相对 `data_locator`、`git_dir_locator`、`projection_kind` 和版本指纹；不把 `C:\`、用户目录、固定端口或绝对宿主路径写入跨机契约。
- 实际绝对路径只存在于本机受控配置/运行时解析结果，由 `shiguan_paths.py`、环境变量或用户显式参数解析；解析后必须做 containment、存在性、权限和 reparse 检查。
- 便携 sidecar 的 data、WAL、扩展和日志目录应位于同一 managed root 或由显式 locator 管理；避免未登记 tablespace。若存在 tablespace，迁移前必须枚举并建立 old→new 映射，不能只移动主 data 目录。
- 配置迁移使用临时目标、锁定源、校验后原子切换 locator；失败保留源、目标和 rollback receipt，不能留下半迁移状态。

**Obsidian 与 Git 不变式**：迁移只改变 PostgreSQL 投影的位置或连接 locator；Git 账册、史馆 JSONL/图/树仍是权威源。迁移完成后先验证 `source_commit` 与 projection revision，再按原有 preserve-only 方向同步 Obsidian；不得从 PostgreSQL 反向覆盖 Obsidian。

**可行性结论**：便携 PostgreSQL 比“只连接已有实例”更适合史馆的强迁移需求，但不应取代已有实例复用。最小可靠方案是：已有实例优先；无实例时由显式 bootstrap 创建 sidecar；专属迁移 CLI 负责跨盘/跨实例迁移与回滚；所有路径通过逻辑 locator 解析。

**官方迁移依据**： [pg_dump/pg_restore 说明](https://www.postgresql.org/docs/current/backup-dump.html) 强调逻辑归档可重载到更新版本并适合跨架构；[pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) 提供 plain/tar 备份及 `--tablespace-mapping`；[tablespaces](https://www.postgresql.org/docs/current/manage-ag-tablespaces.html) 明确 tablespace 与主集群元数据绑定、不能独立搬运；[`pg_ctl`](https://www.postgresql.org/docs/current/app-pg-ctl.html) 支持指定 data 目录的 init/start/stop/status。

**影响面**：决定安装器参数、权限确认、下载与校验、sidecar 生命周期、回滚、安装投影、运行时降级和发布门禁。

**状态**：已回答需求；部署触发采用 B+D 混合，默认准备/使用便携 sidecar，已有 PostgreSQL 可复用。专属迁移 CLI、逻辑 locator、tablespace 处理、回滚和 Obsidian 不变式已明确；迁移默认模式待确认。

## Q16：史馆 PostgreSQL 迁移默认模式（待回答）

**问题**：专属迁移 CLI 默认采用哪种迁移模式？

- A（推荐）：默认逻辑迁移（dump/restore），跨盘、跨机器和跨主版本均适用；同主版本且通过 tablespace/版本预检时可显式选择物理迁移加速。
- B：默认物理迁移，失败时再回退逻辑迁移。
- C：只支持逻辑迁移，物理迁移另行开发。
- D：其他策略，请说明。

**推荐原因**：A 把可迁移性和正确性放在默认路径，把物理复制作为有明确前提的优化；不会因绝对 tablespace 路径或主版本差异导致“看似复制成功、启动后不可用”。

**用户回答**：选择 B。迁移 CLI 默认物理迁移，失败时再回退逻辑迁移。

**暂定判断**：接受 B，但物理迁移不是无条件复制。CLI 必须先通过同主版本或兼容二进制、tablespace 枚举与 old→new 映射、目标目录 containment、源端 quiescence、完整性校验和回滚预检；任一条件不满足则直接走逻辑迁移，不得先执行危险的物理复制。物理迁移失败后保留失败 receipt 和源数据，再使用 pg_dump/pg_restore 完成逻辑迁移。

**影响面**：决定 CLI 默认行为、迁移耗时、停机窗口、跨版本能力、tablespace 检查、回滚策略和验收 fixture。

**状态**：已回答；默认物理迁移，失败或预检不满足时回退逻辑迁移。迁移模式、停机窗口和物理预检字段待继续确认。

## Q17：迁移静默与切换策略

**问题**：执行物理迁移时，史馆 PostgreSQL 采用哪种静默策略？

- A：迁移前完整暂停写入，停止源实例后复制和切换。
- B：源实例在线，用 `pg_basebackup`/流复制复制到目标，迁移期间继续服务，完成后再切换。
- C：迁移期间允许两个实例同时写入，迁移后再通过 revision/冲突检测合并。

**用户回答**：可以，接受 B+ 方案：在线复制、短暂切换、禁止双写、失败回退。

**审查结论**：A 不满足无感目标；C 会引入数据库级双写、顺序和冲突合并风险，不建议用于史馆账册。B 最接近需求，但必须增强为“在线复制 + 极短原子切换”，而不是在线复制后无保护地改路径。

**推荐方案（B+）**：

1. 预检阶段确认源/目标 PostgreSQL 主版本、平台、扩展 ABI、tablespace、目标目录 containment、权限和回滚点。
2. 目标 sidecar 由 `pg_basebackup`/流复制在线建立，源端继续提供服务；通过 WAL 追平判断目标已接近 source LSN。
3. 切换窗口只执行短暂写入冻结：拒绝新的 MCP 写操作，等待已接受事务完成，确认目标追平并完成 source_commit/revision 校验。
4. 原子切换逻辑 locator/连接目标，提升目标实例并恢复 MCP 写入；整个窗口不允许双写。
5. 切换失败保留源实例为唯一写入点，记录 receipt 并回滚 locator；跨主版本、跨平台、tablespace 无法映射或扩展不兼容时，不执行物理复制，改走逻辑迁移/逻辑复制。

**为什么这样选**：`pg_basebackup` 可以在源端在线时生成集群备份；PostgreSQL logical replication 支持实时传输变更，并可用于不同主版本或平台之间，但会增加复制槽、DDL/序列和冲突处理复杂度；`pg_rewind` 可在同一集群分叉后快速回退/重同步。

**Obsidian/Git 不变式**：迁移期间 Git 权威账册不变；locator 切换和 projection status 写入 receipt；Obsidian 仍只从 Git → 史馆树的 preserve-only 方向同步。

**官方依据**： [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) 支持在线基准备份；[Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) 支持实时复制并可跨主版本/平台；[pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html) 用于分叉集群的快速重同步。

**暂定判断**：采用 B+ 作为满足“无感、迅速、可回滚”的首选；A 仅作故障/低规模 fallback，C 不纳入。

**影响面**：决定迁移 CLI 的在线复制、LSN 追平、短切换锁、MCP 写入闸门、locator 原子切换、回滚和跨版本逻辑迁移分支。

**状态**：已确认，采用 B+；迁移触发和用户确认边界待确认。

## Q18：迁移 CLI 的触发与切换授权（待回答）

**问题**：史馆 PostgreSQL 跨盘或跨实例迁移，迁移 CLI 应采用哪种触发方式？

- A（推荐）：默认 `probe`/`plan` 只读；用户显式执行带 `--apply` 的迁移命令后开始在线复制。预检通过时可在同一次授权内自动完成短暂切换；用户也可用 `--prepare` 与 `--cutover` 分两步执行。
- B：由后台服务自动发现目标盘或实例并自动迁移、自动切换，用户只接收结果通知。
- C：所有迁移必须分成 `prepare → review → cutover` 三步，切换永远需要单独人工确认。
- D：其他触发方式，请说明。

**推荐原因**：A 同时保留“无感且迅速”和高风险迁移的明确授权；普通探测不写入，显式 `--apply` 才产生网络、进程、数据目录或 locator 变化。C 可作为高风险数据域的强制模式，B 不适合作为默认，因为后台自动搬迁可能在用户不知情时改变数据位置和连接目标。

**用户回答**：迁移以无感和稳定为最高目标；迁移触发的细节不再继续拆分为大量 QA。

**暂定判断**：B+ 是实现手段，不是最终产品目标。迁移设计的硬优先级为：用户侧尽量无感、服务连续、数据稳定、Git/locator 一致、失败可回滚。物理复制、LSN 追平和短暂切换只为满足这组目标服务；无法满足稳定性时宁可延迟切换或回退逻辑迁移，也不追求表面零停顿。

**影响面**：决定迁移 CLI 的在线复制、短切换实现、稳定性门禁、审计 receipt 和回滚入口；具体触发交互归入实现设计，不再单独扩展访谈问题。

**状态**：已回答目标；无感和稳定优先，B+ 作为实现路径保留，触发细节转实现设计。

## Q19：MCP 的主要调用者（跳过）

**问题**：除具体工具能力外，1.0.8 的 MCP 首要服务哪类调用者？

- A（推荐）：Codex / Hermes / Claude 等智能体，MCP 作为诏令矩阵的机器能力层；人工界面和 CLI 作为辅助入口。
- B：诏令矩阵内部官署运行时，重点服务三省六部调度、史馆和记忆管线。
- C：人类操作员或 Web/桌面界面，智能体调用作为次要适配。
- D：三类都要，按 A → B → C 优先。
- E：其他调用者，请说明。

**推荐原因**：A 能直接承接“主动查询能力索引并积极调用 skill”的目标，同时保留 B 的内部治理职责；C 需要更完整的交互、会话和审计设计，不宜默认成为首要契约。

**用户回答**：这是明显问题，不需要继续提问。

**暂定判断**：MCP 主要服务 Codex、Hermes、Claude 等智能体，同时服务诏令矩阵内部官署运行时；不将调用者类型作为独立需求决策。具体工具只需记录 actor、role、authority、task 和调用来源。

**影响面**：保留为工具契约的上下文字段，不新增访谈分支。

**状态**：已跳过，无需决策。

## Q20：能力索引主动调用触发策略（待回答）

**问题**：MCP 何时必须主动查询本机能力索引，并据此选择 skill、MCP、CLI 或 script？

- A（推荐）：每个非平凡任务首次需要选择能力时必须先查能力索引；同一任务复用带 hash/revision 的 snapshot，只有索引变化、匹配不足或阶段边界变化时才刷新；随后只调用最小合适集合，并记录实际加载的 skill、路径和理由。
- B：只有匹配置信度不足或调用失败时才查能力索引。
- C：只在阶段开始或 Handoff 时查能力索引，任务中不主动查。
- D：其他触发策略，请说明。

**推荐原因**：A 最符合“积极调用 skill”的目标，同时避免每次工具调用都重复扫描；它与项目现有 index-first、缓存 snapshot、staleness warning 和有界刷新契约一致。

**用户回答**：采用 ABC 三个触发路径的混合方式；在任务出现特殊情况时，MCP 也要主动查询本机能力索引。

**暂定判断**：能力索引采用“常规首次查询 + 特殊情况主动重查”的混合策略：

- 常规：每个非平凡任务第一次需要选择 skill、MCP、CLI 或 script 时查询一次，并在同一任务内复用带 hash/revision 的 snapshot。
- ABC 混合任务特殊情况：跨数据域、能力匹配不足或冲突、索引 stale/corrupt、权限或 authority/write_set 变化、记忆冲突或过期、投影降级、PostgreSQL/sidecar 状态变化、迁移、阶段边界或 Handoff 时，MCP 必须主动重查能力索引。
- 重查后只选择最小合适集合，不调用全部候选；实际加载的 skill、路径、版本/哈希、选择理由和调用结果写入 receipt。
- 能力索引查询仍是选择依据，不自动授予权限；skill 的真正加载、安装或宿主变更必须经过对应宿主机制和当前 authority。

**影响面**：决定 MCP 调用前置链、能力索引 snapshot/cache、ABC 混合任务的特殊触发器、skill 主动选择、刷新频率、工具调用预算、receipt 字段和阶段交接行为。

**状态**：已回答；采用常规首次查询与特殊情况主动重查的混合策略。命中 skill 后由 MCP 自动触发宿主加载还是仅返回推荐，待确认。

## Q21：命中 skill 后的主动加载方式（待回答）

**问题**：MCP 查询能力索引命中合适 skill 后，是否应主动触发该 skill 的宿主加载？

- A（推荐）：主动触发宿主 Skill 机制加载，但不自动安装、升级或修改 skill；加载前仍验证 authority、项目边界和 skill identity，加载结果记录路径、哈希和状态。
- B：MCP 只返回 skill 推荐、路径和理由，由上层智能体决定是否加载。
- C：低风险任务自动加载，高风险或写任务只返回推荐并等待人工或上级官署决定。
- D：其他方式，请说明。

**推荐原因**：A 最符合“积极调用 skill”的目标，同时保留宿主加载机制、权限和项目边界；C 可作为高风险写入流程的进一步收紧。

**用户回答**：选择 A。加载 skill 时不必单选，可以根据任务组合加载多个 skill。

**暂定判断**：MCP 命中能力索引后，主动触发宿主 Skill 机制加载；一次任务允许加载多个 skill，但必须是按依赖排序的最小合适集合，不是把所有匹配候选全部加载。加载前验证 authority、项目边界和 skill identity；receipt 记录选择顺序、依赖/冲突、实际路径、哈希、加载状态和未选择候选及原因。MCP 不自动安装、升级或修改 skill。

**影响面**：决定 MCP 与宿主 Skill loader 的接口、主动调用链、权限边界、安装/升级隔离、skill identity 校验、调用延迟和审计 receipt。

**状态**：已回答；采用主动宿主加载，支持多 skill 组合，遵守最小集合和依赖排序。后续访谈先确认大问题主轴，再进入细节。

## Q22：剩余访谈的大问题主轴（待确认）

**问题**：在继续细问前，下面哪些大问题需要保留为后续访谈主轴？可以删减、合并或补充；确认后我只按主轴推进，不再问显而易见的问题。

1. **MCP 能力版图**：史馆/记忆、能力索引、状态查询、语义校验、IKU、调度计划、领域化 Create/Read/Update/Delete 的最终工具分组和优先级。
2. **主动能力编排**：能力索引查询、多个 skill 组合加载、调用顺序、特殊情况重查、失败降级、循环防护和宿主 Skill loader 边界。
3. **记忆与 GBrain 生命周期**：召回、字段清洗、冲突/过期检测、候选、升降档、正式记忆裁定、人工/门下节点和反馈闭环。
4. **数据与持久化底座**：Git 权威账册、JSONL/稀疏向量/图索引、PostgreSQL/pgvector/pg_search 投影、revision、receipt 和一致性。
5. **权限与安全**：角色 ACL、当前会话三权、write_set、人工批准、高风险删除、私密/pending 边界和审计。
6. **协议与工具契约**：现有通用 MCP 入口、stdio/HTTP/Resources、工具 schema、错误语义、客户端兼容和是否扩展入口。
7. **安装、迁移与交接**：便携 PostgreSQL、已有实例复用、B+ 迁移、逻辑 locator、专属 CLI、skill 安装、阶段标记、验收证据和 handoff/context。
8. **性能与可观测性**：召回 SLO、索引缓存、冲突检测效率、工具调用预算、Git/投影状态、迁移窗口和 benchmark。
9. **用户体验与默认策略**：默认只读/写入提示、主动建议呈现、失败解释、降级可见性和人工干预入口。

**用户回答**：保留九个主轴，但需要筛选：有些问题已经问完，有些在以前开发过程中已经有标准答案，不要重复提问。

**暂定判断与筛选结果**：

| 主轴 | 处理 | 依据 |
| --- | --- | --- |
| MCP 能力版图 | 保留，待继续确认 | Q4 已有优先级建议，但最终 1.0.8 工具分组、批次和纳入边界尚未定稿。 |
| 主动能力编排 | 已基本确认，不再重复问 | Q20 已确认首次查询与特殊情况主动重查；Q21 已确认主动宿主加载和多 skill 组合。 |
| 记忆与 GBrain 生命周期 | 保留，限问未决落地契约 | Q10-Q12 已确认混合裁定、GBrain-mode 参考架构和性能目标；只在状态字段、召回 envelope、升降级工具边界仍有实质歧义时提问。 |
| 数据与持久化底座 | 已确认，不再重复问 | Q8-Q18 已确认 Git 权威、不可变 revision、ABC 投影、PostgreSQL 可选 sidecar、locator 和 B+ 迁移。 |
| 权限与安全 | 已基本确认，不再重复问 | Q6-Q7、Q10 已确认角色 ACL、会话三权取更严格者、approval 只读、删除/记忆整理顺延。 |
| 协议与工具契约 | 默认沿用既有标准，仅在边界变化时再问 | 现有通用 MCP 入口、manifest → public API → probe、JSON-RPC 错误和审计契约已有标准；只在用户要改变传输范围时再问。 |
| 安装、迁移与交接 | 已确认，不再重复问 | Q14-Q18 已覆盖 sidecar、专属 CLI、逻辑 locator、B+ 在线切换、无感/稳定优先；Handoff/context-save/context-restore 已有标准契约。 |
| 性能与可观测性 | 已确认，不再重复问 | Q12 已确认召回 P95 目标/硬门禁；Q11、Q17 已确认冲突/过期检测、迁移和 receipt 追踪方向。 |
| 用户体验与默认策略 | 暂不单列 | 当前由 authority、ACL、降级和 receipt 契约约束；除非出现实际交互歧义，不新增问题。 |

**筛选后的后续主轴**：只保留 ①最终 MCP 能力版图；②记忆/GBrain 未决落地契约；③协议/传输范围是否改变。其余主轴直接沿用既有标准答案和已确认记录。

**影响面**：缩小访谈问题数量，避免重复确认既有契约；最终只把筛选后的新增决策合并到开发文档、执行计划书和任务书。

**状态**：已回答，筛选结果待用户确认。

## Q23：beta1.0.8 MCP 未决事项一次性选择问卷

填写方式：一次性提交各题编号和选项，例如 Q23.1-A、Q23.2-C。可以在选项后补充文字。未选择题目按“暂缓、不纳入本版本”处理。提交后停止继续拆分提问。

### A. 最终 MCP 能力版图

Q23.1 首批工具批次

- A（推荐）：P0 交付史馆/记忆召回、能力索引查询、状态查询、语义/契约校验；P1 交付 IKU 候选、计划验证、记忆评估/建议；受控写入和升降档随后按权限交付。
- B：史馆/记忆与能力索引全部优先，其他工具顺延。
- C：A/B/C/E 全部在 1.0.8 同批交付，统一验收后发布。
- D：自定义批次，请写顺序。

Q23.2 领域化写工具范围

- A（推荐）：纳入史馆记忆和能力索引账册的 Create/Read/Update；Delete、记忆整理、合并、去重、清退不纳入。
- B：本版本只做读和建议，写工具顺延。
- C：全部数据域纳入领域化 Create/Read/Update，按 ACL 和当前会话三权执行。
- D：自定义范围。

Q23.3 官署调度类 MCP 能力

- A（推荐）：提供计划验证、边界检查、Handoff 准备和 dry-run；真实 spawn/reuse/wake 仍由宿主和三省六部链路执行。
- B：允许 MCP 触发已授权官署调度，但必须经过 agent-admit 和 receipt。
- C：本版本不接入官署调度，仅保留查询和校验。
- D：自定义范围。

### B. 记忆与 GBrain 落地契约

Q23.4 记忆状态机最终形态

- A（推荐）：CANDIDATE → REVIEW → APPROVED → ACTIVE；ACTIVE → DEGRADED、STALE 或 SUPERSEDED；正式转换由人工/门下批准，评分和证据更新可自动产生新 revision。
- B：简化为 CANDIDATE → ACTIVE → ARCHIVED，冲突和过期只作为字段。
- C：按数据域分别定义状态机。
- D：自定义状态机。

Q23.5 召回 envelope 默认内容

- A（推荐）：默认返回清洗后的 metadata 和摘要，包括 memory_id、类型、摘要、关键词、谱系、decision_state、confidence、时间有效性、stale、conflict_set、supersedes、revision、source_ref、Git commit、evidence_ref；正文按需且受权限控制。
- B：默认返回摘要加短正文片段。
- C：默认返回完整正文，私密和 pending 仍过滤。
- D：自定义字段策略。

Q23.6 冲突与过期检测自动化

- A（推荐）：快路径自动标记冲突/过期并生成建议，不自动改变正式记忆状态；深度解释由显式 evaluate/propose 工具执行。
- B：检测到冲突或过期后自动降级为 DEGRADED/STALE，恢复需人工批准。
- C：仅生成报告，不改变索引状态。
- D：自定义策略。

Q23.7 记忆升降档和正式生效审批主体

- A（推荐）：普通低风险候选由具备域 ACL 的官署执行；正式 durable memory、跨来源合并、冲突裁定、升档和降档由门下/人工批准。
- B：所有升降档都由人工批准。
- C：达到评分阈值自动升降档，高风险项才人工批准。
- D：按数据域指定不同审批主体。

Q23.8 记忆反馈与再评估

- A（推荐）：记录召回命中、用户纠正、冲突/过期结果和门下裁定作为 feedback；只增量重算受影响 revision/conflict set。
- B：只在人工发起时重新评估。
- C：按固定周期全量评估。
- D：自定义触发。

### C. 协议与传输边界

Q23.9 是否扩展现有通用 MCP 传输

- A（推荐）：保留现有通用入口和 stdio；HTTP /mcp、Resources 作为可选 Stretch，不影响核心发布。
- B：beta1.0.8 同时交付 stdio 与 HTTP /mcp。
- C：本版本只做 stdio，HTTP/Resources 明确顺延。
- D：其他传输安排。

Q23.10 Resources 暴露范围（仅在纳入 HTTP/Resources 时回答）

- A（推荐）：只暴露史馆 entry/receipt 的索引和元数据，不读 pending/private 正文。
- B：允许受权限控制的摘要或短片段。
- C：不提供 Resources。
- D：自定义资源 URI 和字段。

Q23.11 MCP 工具协议兼容策略

- A（推荐）：现代协议与 legacy 会话双兼容，领域语义一致，协议差异只在适配层处理。
- B：只维护现代协议。
- C：现代协议为主，legacy 只保留已有五个工具。
- D：自定义兼容策略。

### 问卷提交区

- Q23.1：C。A/B/C/E 全部作为 1.0.8 目标同批交付；增加编号生成器的 MCP 适配，并要求谱系分类严格防过拟合。
- Q23.2：A。领域化写工具应有统一 CLI；MCP 和主动 CLI 都可以调用同一能力。MCP 读取结果要采用 Agent 友好的结构化格式。
- Q23.3：A+B 混合。提供计划验证、边界检查、Handoff 准备和 dry-run；官署可以调用 MCP，已授权调度仍需 agent-admit 和 receipt。
- Q23.4：A。一般情况自动批准，沿用原先的记忆裁定行为；结诏时自动查找冲突记忆，以新记忆或权威情况为准，将冲突记忆降级；全部操作告知用户，并将该范式脚本化。
- Q23.5：A+B。默认提供清洗后的 metadata、摘要和短正文指引，并对完整正文提供受权限控制的定位/读取指引。史馆实录应改版，记录初始问题、中间问题、初始与后续动作、错误及解决、最终结果、问题是否解决和解决了什么；已有状态字段含义可复用，不必重复展开。
- Q23.6：A；冲突和过期处理与 Q23.4 的结诏自动检查联动。
- Q23.7：A。普通低风险候选由具备域 ACL 的官署处理；正式 durable memory、跨来源合并、冲突裁定、升档和降档由门下/人工批准。
- Q23.8：A。记录召回命中、用户纠正、冲突/过期结果和门下裁定，增量重算受影响 revision/conflict set。
- Q23.9：A；保留现有通用 MCP 入口和 stdio，但 HTTP 对当前 skill 本身没有实际意义，不作为当前核心能力。
- Q23.10：如 Q23.9；当前不提供 Resources，HTTP/Resources 不纳入当前 skill 核心范围。
- Q23.11：A；现代协议优先，同时保持既有 legacy 兼容。
- 补充意见：上述结论先进行问题审查，不急于合并到开发文档、执行计划书和任务书。

状态：用户已一次性提交；问题审查完成，结论已采纳并合并到开发文档、执行计划书和任务书。

## Q23 答案审查（已采纳）

### 1. 总体结论

 - 问卷答案已经足够形成 beta1.0.8 MCP 的主体方向，但还不能直接机械合并。
 - 可直接采纳的主线：史馆/记忆和能力索引优先、领域化 CLI/API、官署可调用 MCP、混合 GBrain 状态机、高效召回与增量再评估、现代协议优先且保留 legacy。
 - 需要在最终合并前校正的主线：同批交付的阶段含义、自动记忆裁定的权限语义、史馆实录的 full-record 改版、编号生成器的权威来源、HTTP/Resources 的不适用边界。

### 2. 逐题审查

| 题目 | 审查结论 | 处理意见 |
| --- | --- | --- |
| Q23.1 | 有条件通过 | 将 C 解释为全部纳入 beta1.0.8 发布目标，不解释为同一阶段一次性实现。内部仍可按 P0/P1 或 Phase 子任务分批交付，但版本出口必须统一验收。编号生成器只能适配统一 shiguan archive-checkpoint 或权威 public API，不得由 MCP 另造编号；谱系继续使用版本化分类、最小验证集、正向 margin、否定证据隔离和历史 court_code 保留规则，防止过拟合。 |
| Q23.2 | 通过 | 统一 CLI 是领域能力入口；直接 CLI 和 MCP 都调用同一 public/domain API。MCP 不通过 subprocess 调 CLI，不解析人类文本；读取返回 Agent 友好的结构化 JSON envelope，含稳定字段、状态、来源、revision、错误和下一步指针。 |
| Q23.3 | 有条件通过 | A+B 混合成立：官署可以在职责范围内调用 MCP；计划验证、边界检查、Handoff 和 dry-run 可直接提供；真实调度仍必须经过 role/direct_superior、agent-admit、当前 authority、write_set 和 receipt，不能因官署调用绕过层级。 |
| Q23.4 | 需要政策校正 | 一般情况自动批准只能覆盖既有低风险、确定性记忆裁定和结诏时的自动冲突检查；不能把所有 WRITE、正式 ACTIVE、跨来源合并或高风险降档都变成无审批准入。新记忆或权威事实导致的确定性冲突可脚本化标记为 DEGRADED/SUPERSEDED 建议或受控状态转换，并告知用户；跨域、高风险或语义不确定时仍转门下/人工裁定。所有操作必须有 before/after、原因、receipt 和 Git revision。 |
| Q23.5 | 通过，作为补充 | 采用 A+B：默认 metadata、摘要和短正文指引；完整正文只通过受权限控制的 source_ref、line_anchor 或读取指针访问，不默认泄露正文。在原史馆实录结构和十四行 compact memorial 之上补充可查询 leaves、full-record 指针及原版完整上下文路径索引；full-record 记录初始问题、初始动作、后续动作、中间问题、错误、错误解决、最终结果、是否解决、解决范围和下一步，不替换既有状态语义。 |
| Q23.6 | 通过，依赖 Q23.4 | 快路径自动发现冲突/过期并生成建议；结诏时可触发确定性冲突处理范式；正式记忆状态的自动改变必须遵守 Q23.4 的风险和裁定分层。 |
| Q23.7 | 通过 | 普通低风险候选由域 ACL 官署处理；正式 durable memory、升档、降档、冲突裁定、跨来源合并和影响范围扩张由门下/人工批准，除非 Q23.4 明确定义为低风险确定性自动转换。 |
| Q23.8 | 通过 | 记录召回命中、用户纠正、冲突/过期结果和门下裁定作为 feedback；只增量重算受影响 revision/conflict set，不进行无必要的全量重建。 |
| Q23.9 | 需要边界重述 | 保留现有通用 MCP 入口和 stdio；用户同时明确 HTTP 对当前 skill 没有实际意义，因此 HTTP /mcp 不作为当前 skill 核心，也不进入 beta1.0.8 必需门禁。原计划中的 HTTP 方向只能保留为非核心后续备注，不能继续写成默认 Stretch 交付项。 |
| Q23.10 | 通过 | 按 Q23.9 处理为当前不提供 Resources；如未来重新纳入，只允许索引/元数据或受权限控制的短片段，禁止 pending/private 正文。 |
| Q23.11 | 通过 | 现代协议优先；保留既有 legacy 兼容。领域语义、权限、审计和 receipt 不因协议版本分叉。 |

### 3. 必须纳入最终合并的新增条目

1. 编号与谱系：MCP 调用统一编号生成器或权威 public API；不生成第二套编号；谱系分类版本化并以验证集和 margin 防过拟合。
2. CLI/API 双入口：领域化能力由统一 CLI 与 public/domain API 提供；MCP 和主动 CLI 共用该入口；MCP 返回 Agent 友好 JSON。
3. 官署调用：官署可在职责范围调用 MCP；真实调度保留三省六部、agent-admit、authority、write_set 和 receipt。
4. 自动记忆范式：结诏自动冲突扫描；新记忆或权威情况优先；确定性冲突可脚本化降级或替代并告知用户；不确定或高风险情况转人工或门下。
5. 史馆 full-record：compact memorial 之外增加可追溯 full-record，记录问题、动作、错误、修复、结果和解决范围；完整正文仍按 source_ref 或权限指引读取。
6. 协议边界：stdio 和现有通用入口为当前核心；HTTP/Resources 对当前 skill 不适用，不进入本版必需交付。

### 4. 当前不应合并的内容

- 不应把 Q23.1 的 C 写成所有功能在同一阶段完成，否则与已有阶段拆分和风险控制冲突。
- 不应把自动批准写成绕过门下、三权或 memory_decision 的全局写权限。
- 不应把 PostgreSQL、SQLite、向量投影或 Obsidian 派生物当作史馆权威源。
- 不应把 HTTP/Resources 继续当作当前 skill 的必做能力。

审查状态：问卷答案已记录并完成审查；审查结论已采纳并合并到开发文档、执行计划书和任务书。

## Q23.5 注释采纳说明

用户补充：Q23.5 的 full-record 只能作为原史馆实录结构的补充，不能替换原结构；关键要求是可查询、准确、以 leaves 作为查询落点，并额外体现原版完整上下文文件路径索引。

最终处理：保留原十四行 compact memorial、原史馆实录字段和状态语义；新增可查询 leaves、full-record 指针、原版完整上下文文件的相对 locator、line/section 指针、source hash 和访问状态。索引不复制完整正文，完整正文按权限和 source_ref 按需读取。

## 决策变更记录

| 记录 | 变化 | 原因 | 最终同步位置 |
| --- | --- | --- | --- |
| Q1-Q2 | 从“只读工具面”的初步理解，补充为“保留现有通用 MCP 入口并在其上适配、新增” | 用户澄清现有系统已经具备通用 MCP 入口 | 访谈结束后同步开发文档、执行计划书、任务书 |
| Q3 | 将入口与能力范围标为暂定，不提前冻结 | 用户明确后续问答可能改变边界 | 访谈定稿时统一判断 |
| Q4 | 史馆/记忆与能力索引查询列为最高优先；A/B 适合直接接入；E 次之；C 限制为验证/预览；数据库等同操作列为受控写能力候选 | 用户要求 MCP 积极调用 skill，并指出部分场景需要非只读能力 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q5 | 史馆、能力官籍、任务/handoff、编号/谱系/分类和其他数据库对象全部纳入需求作用域；实现采用领域化操作，不暴露任意表/SQL 接口 | 用户确认上述数据域都应作为作用域 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q6 | 采用按数据域与官署角色授予的持久权限；命中权限即可执行，只有高风险删除再批准 | 用户选择授权模型 C | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q7 | 持久角色权限与当前会话三权取更严格者；approval 始终只读；史馆记忆和能力索引账册本期开放 Create / Read / Update，Delete 与记忆整理顺延 | 用户同意双重门禁，并明确账册读写需求及删除能力尚未完成 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q8 | Update 采用追加不可变修订；史馆、记忆库和能力索引由 Git 仓库治理 | 用户选择 A，并补充 Git 治理记忆 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q9 | 每次成功的领域写操作单独提交 Git commit；失败不提交；Git 持久化与记忆裁定分离但在 receipt 中绑定 | 用户选择 A，并追问提交是否属于记忆裁定能力 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q10 | 采用 A/B 混合裁定；GBrain 作为项目内参考架构；记忆升降级和成为正式记忆纳入 MCP 工具族，高风险流程需人工/门下授权 | 用户要求部分人工裁定，并要求核对类 GBrain 案例 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q11 | 同意混合状态机；要求细化高效召回、分层字段清洗、冲突/过期察觉、升降档建议，并继续参考时间知识图谱案例 | 用户同意并要求继续细化与查找案例 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q12 | 普通召回 P95 ≤ 100ms 为优化目标、P95 ≤ 200ms 为发布硬门禁；深度治理工具不阻塞 recall | 用户同意双层性能基线 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q13 | 采用 A/B/C 混合：Git/JSONL 为唯一权威源，进程内索引为快路径，SQLite/PostgreSQL 为可重建结构化投影，现有稀疏向量/图与可选 pgvector/pg_search 为语义增强；Obsidian 继续 preserve-only | 用户要求混合方案、优化现有类向量能力、核查 PostgreSQL 且不打乱 Obsidian 同步 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q14 | PostgreSQL + pgvector/pg_search 为可选增强；可采用用户态便携 sidecar；一键部署必须显式授权、固定版本校验、可回滚且只承载派生投影，不改变 Git/Obsidian 权威链 | 用户选择 A 并询问便携版/一键部署 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q15 | 部署触发采用 B+D 混合，默认便携 PostgreSQL sidecar，已有兼容实例可复用；仍需显式授权、固定包校验、用户态目录、回滚和不改写 Git/Obsidian 权威链 | 用户要求默认便携以强化可迁移性，同时保留已有 PostgreSQL 连接路径 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q16 | 迁移 CLI 默认物理迁移，预检不满足或执行失败时回退逻辑迁移；物理路径必须受版本、tablespace、路径 containment、quiescence、完整性和回滚门禁约束 | 用户选择 B | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q17 | 采用 B+：在线物理复制/流复制，切换瞬间短暂冻结 MCP 新写入，确认 WAL/LSN 追平后原子切换 locator；不允许双写；不满足物理条件则转逻辑迁移 | 用户确认该方案满足无感、迅速、可回滚目标 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q18 | 迁移以无感和稳定为最高目标；B+ 仅为实现路径，触发交互不再拆分访谈 | 用户明确不希望继续扩展迁移 QA | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q19 | 调用者问题明显，跳过独立决策；具体工具记录 actor/role/authority | 用户要求不要再问显而易见的问题 | 访谈定稿时作为通用字段处理 |
| Q20 | 常规首次选能力时查索引；ABC 混合任务在跨域、匹配不足、冲突/过期、权限变化、投影降级、迁移或阶段边界等特殊情况主动重查 | 用户要求 ABC 混合任务特殊情况也主动查询能力索引 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q21 | MCP 命中能力索引后主动触发宿主 Skill 加载；支持多个 skill 组合，但按依赖排序选择最小集合，记录实际加载和未选原因 | 用户选择 A，并明确加载 skill 可以不是单选 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q22 | 九个主轴保留为背景，但主动编排、持久化、权限、迁移、性能、交接等已问完或有既有标准答案；后续只保留 MCP 能力版图、记忆/GBrain 未决契约、协议/传输边界三条主轴 | 用户要求筛选明显问题和已有标准答案，避免重复提问 | 访谈定稿后同步开发文档、执行计划书、任务书 |
| Q23 | 一次性问卷已提交、审查并采纳；确认全量能力目标、领域化 CLI/API、官署 MCP 调用、混合记忆裁定、保留原实录结构并补 leaves/full-record 路径索引、stdio 核心和现代协议优先；自动裁定、编号生成器和 HTTP 边界已按审查意见校正 | 用户要求先审查，再按结论采纳 | 已同步开发文档、执行计划书、任务书 |

## 访谈完成判定

- 所有高影响 MCP 决策均有问题、回答、暂定判断和影响面记录。
- 最终结论与暂定判断明确区分，未回答项不得写成已确认需求。
- 访谈记录完成后，只回写开发文档、执行计划书和任务书。
- 回写完成后，三份目标文档的任务、验收、排期和交接证据引用保持一致。
