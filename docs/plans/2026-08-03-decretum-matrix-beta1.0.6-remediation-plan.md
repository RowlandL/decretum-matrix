# Decretum Matrix beta1.0.6 P0 整改计划书

状态：ACTIVE_PLAN / PLANNED_UNVERIFIED  
日期：2026-08-03  
适用范围：仅限本文件绑定的 beta1.0.6 子仓任务  

## 一、承接身份与不可变锚点

本文件是独立计划书，只定义整改目标、合同、阶段计划、验收和停止门。其逐字绑定的独立执行书路径是 docs/plans/2026-08-03-decretum-matrix-beta1.0.6-execution-book.md；阶段事实、命令回执和游标推进以该执行书及其绑定阶段 log 为准。本计划当前唯一恢复游标是 stage-3/result-recovery-chain，stage 0—2 已通过本地门，不得回退到 stage 0。本文件不自行分配诏令编号，不生成或模拟结诏十四行，也不把计划文字声明为已实现能力。

| 字段 | 绑定值 |
| --- | --- |
| task | beta106-local-stage-019fb7f5 |
| child repository | decretum-matrix |
| worktree | D:/project/worktrees/decretum-matrix/beta106-local-stage-019fb7f5 |
| branch | release/beta1.0.6 |
| accepted source baseline | 40ba6c4 |
| current plan head | 48ddc910abc1829f04ac23f0430b55a1d3f0fea8 |
| current plan head short | 48ddc910 |
| authority | super |
| behavior | parallel |
| runtime | native |
| bound execution book | docs/plans/2026-08-03-decretum-matrix-beta1.0.6-execution-book.md |
| current unique cursor | stage-3/result-recovery-chain |
| inherited local gates | stage 0—2 = LOCAL_GATE_PASSED |
| parallel hierarchy | 用户 -> 太子/root -> 三省；尚书省 -> 六部；六部 -> 自属工坊/工匠 |
| governing installed skill | C:/Users/32893/.agents/skills/decretum-matrix/SKILL.md |

任何恢复如果发现 task、child repository、branch、baseline、当前承接 head、authority、behavior、runtime、执行书路径或当前唯一 cursor 与上表不一致，必须停止并在 stage-3/result-recovery-chain 记录 blocker，不得把其他线程、其他 worktree、其他 runtime 或旧安装根状态混入本计划，也不得把游标重置为 stage 0。

## 二、声明分类

- [CONTROL_PLANE] 本文件中的仓库隔离、分支、索引清洁、三省链路、写集、停止门、handoff 方式和外部发布授权检查，约束的是工作如何进行。
- [PLANNED_UNVERIFIED] 本文件要求实现或修复的层级校验、结果恢复、P00 语义绑定、史馆谱系、安装投影、安装版 shard、同步、回滚、CLI 和发布能力，当前均为待实现或待重新证明，不得表述为已实现。
- 本文件不包含 VERIFIED_CAPABILITY 声明。只有符合 workspace.capability_evidence.v1、绑定准确版本和 release commit、且同时覆盖代码、类型化测试、安装投影和运行时回执的 VERIFIED receipt，才能在控制面提升能力声明。
- 源码、计划、测试名称、脚本存在、一次 ok 输出或当前脏工作树都不能单独证明产品能力。

## 三、P0 整改优先级

以下顺序是本任务的硬优先级；后项不得绕过前项的停止门。

1. [CONTROL_PLANE] 三省链路优先级最高。太子/root 只调三省；中书省、门下省不得直接调六部；尚书省独占六部差遣；六部只调自属工坊/工匠。create、spawn、reuse、follow-up、wake、restart、recovery、reassignment 和结果恢复全部适用。
2. [PLANNED_UNVERIFIED] 修复 court.child_office_profile.v1 生成器与 court.dispatch_hierarchy.v1 manifest 的六字段契约，并恢复“第二语义权威”拒绝门。
3. [PLANNED_UNVERIFIED] 错误层级或陈旧绑定结果不得丢弃，也不得直接整合。固定链路为：隔离锁定 -> 有界结果提取 -> 门下省审核 -> 合法直属上级交接 -> 目标官署重新生成自己的 court.office.result.v1 -> 经现有正常 finish 通路集成。
4. [PLANNED_UNVERIFIED] handoff 与结诏必须绑定同一份统一 CLI 归档身份。编号、谱系和 closeout identity 只能逐字复制 shiguan archive-checkpoint 的 payload.closeout_identity；模型、计划文件和人工文本不得自造。
5. [PLANNED_UNVERIFIED] “安装版缺少 shard”列为后续阶段 P0。先形成源树、包、安装投影和已安装根的精确 shard 清单，再修复；本文件不猜测缺失 shard 名称。
6. [PLANNED_UNVERIFIED] npm beta 与安装选根列为 P0：~/.agents 是唯一 shared primary；current tool 必须 proven；每个 explicit extra 必须逐根有最新 authority/proof；五根+Qoder 只能来自 receipt selected set，禁止默认 fanout。beta1.0.6 未完成远端发布核验前不得声称 npm @beta 已指向本地版本。
7. [PLANNED_UNVERIFIED] 安装哈希 checker 必须保持 source-only。它不得进入安装投影、运行时 loader、CLI runtime import、postinstall 运行链、active skill root 或任何自动加载脚本；只能由源码发布/安装验收显式调用。
8. [CONTROL_PLANE] 任一 P0 门失败时停止向后推进，保留证据和可恢复游标，不以赶进度为由降低层级、隐私、回滚、安装或发布门。

## 四、全程不变量

### 4.1 层级与调度

- [CONTROL_PLANE] direct_superior 是执行边界，不是展示标签。宿主 UI 即使平铺线程，也不得改变 receipt 中的层级。
- [CONTROL_PLANE] 发生越级派遣时，立即停止该结果的直接集成；保留来源和 payload hash，并通过合法直属上级进入结果恢复链。
- [CONTROL_PLANE] 并行只用于独立、无共享写冲突的工作。共享文件、安装、同步、配置、Git 索引、外部发布和 closeout 必须串行。
- [CONTROL_PLANE] 不再采用“隔离即丢弃”。隔离的含义是冻结执行权和完成权，随后允许受审、有界、可追踪地提取为 advisory input。

### 4.2 结果恢复

- [PLANNED_UNVERIFIED] 原错误结果永远不能通过改写 agent_id、role、direct_superior、dispatch_uid、attempt 或 checkpoint 被“重基线”为有效结果。
- [PLANNED_UNVERIFIED] 一旦结果进入 quarantine，来源实例必须在同一 runtime lock 内固定写入 status=failed、final_status=failed、release_status=closed、result_state=QUARANTINED、failure_kind=result_binding_quarantine、office_execution_ready=false，并写 finished_at 与 closed_at。此后 report、follow-up、finish、reuse、wake 和复活全部拒绝，只能创建合法的新 target 实例承接 recovered input。
- [PLANNED_UNVERIFIED] _active_office_write_claims 必须显式排除所有 terminal 实例以及 result_state=QUARANTINED 的来源实例，使 quarantine transaction 在同一锁内释放 active write claim；不得靠调用方约定或后续 close 才释放。
- [PLANNED_UNVERIFIED] 隔离结果只可形成 metadata-only quarantine record 和经过隐私门的 recovered result projection；raw body、完整日志、transcript、prompt、private/pending body 不得落入 task/event ledger。
- [PLANNED_UNVERIFIED] 门下审核只决定 ACCEPT 或 REJECT，不产生六部差遣权。
- [PLANNED_UNVERIFIED] handoff 只由目标官署的真实直属上级执行，并绑定当前 hierarchy、semantic checkpoint、preload、carrier proof 和 native host follow-up receipt。
- [PLANNED_UNVERIFIED] 目标官署收到 recovered input 后必须重新核验，并以自身当前绑定生成新 envelope；只有该 envelope 通过现有 agent_finish 或 office finish 才能完成正常集成。

### 4.3 handoff 与结诏

- [CONTROL_PLANE] 每一阶段停止都必须留下：task、branch、HEAD、stage、plan_cursor、已完成检查、未解 blocker、root/child Git 状态、未执行动作和下一条精确命令。
- [CONTROL_PLANE] 每一阶段完成后的继续载体固定为本机 `D:\project` 下的新 local conversation task；新任务必须使用 `environment=local`，不得创建或切换到 worktree task，不得 materialize、attach、创建 child/root worktree、创建分支或改变现有受管 child worktree。新对话只携带有界 handoff packet，并继续引用本计划绑定的现有 child worktree、branch、HEAD、P00 capsule、semantic receipt 和 `plan_cursor`。
- [CONTROL_PLANE] 阶段交接不得把新对话任务误报为新执行权或第二语义权威；必须复用同一 task/child repository/write set 语义，先完成当前阶段的门下复核和 log 回写，再创建下一阶段 conversation task。若本机无法创建 local conversation task，保持当前阶段 `handoff_or_pause` 并停止，不回退或另建工作树。
- [PLANNED_UNVERIFIED] 正式 handoff/结诏必须先经门下复核，再执行统一 CLI 的 shiguan archive-checkpoint；handoff 记录逐字复制有效 archive receipt 的 closeout_identity，并记录 receipt 路径和 digest。
- [CONTROL_PLANE] 没有有效 archive receipt 时，只能报告 handoff_or_pause、partial_or_not_run 或 authority_blocked；不得输出十四行，不得自造编号。
- [CONTROL_PLANE] 恢复时必须同时核验 handoff 中的 task/branch/head/plan_cursor、独立执行书路径和所绑定的 archive receipt；任何一项漂移都在当前 stage-3/result-recovery-chain fail closed 并上报门下，不得回退 stage 0 或重新解释 stage 0—2 的本地门。

### 4.4 安装与哈希隔离

- [PLANNED_UNVERIFIED] 统一 root-selection contract 固定为：shared primary root=~/.agents；current tool 只有在 current_tool_root_proof 通过后才可加入；每一个 explicit extra target 都必须有最新逐根 authority 与 proof。
- [CONTROL_PLANE] ~/.agent（单数）是用户笔误，不是产品根、兼容 alias 或新增目标；产品 shared primary 始终为 ~/.agents（复数）。
- [PLANNED_UNVERIFIED] 用户目标“五根 + Qoder”只能作为 install/root-selection receipt 中逐根显式 selected set；不得硬编码为 installer、sync 或 active checker 的默认 fanout，也不得从历史安装、目录存在或 include-qoder 旧开关推导授权。
- [PLANNED_UNVERIFIED] install receipt 至少增加 selection_policy、primary_root、current_tool、current_tool_root、current_tool_root_proof、status、explicit_extra_targets、selected_roots、authority 和 receipt_sha256。unproven current tool 或任一 extra 缺 authority/proof 必须在写入前 fail closed，不得静默省略后继续报告安装成功。
- [PLANNED_UNVERIFIED] active-copy hash checker 只验证安装结果，不成为安装结果的一部分。
- [PLANNED_UNVERIFIED] active-copy hash checker 默认从已验证 receipt 读取 selected_roots；无 receipt 时不得回退到硬编码五根。显式单根诊断必须重复提供 target-root、authority 和 proof，并在输出中标记非完整安装验收。
- [PLANNED_UNVERIFIED] legacy locator 迁移必须先备份、后原子迁移/别名、失败回滚；不得直接递归删除活动根。
- [PLANNED_UNVERIFIED] package 可以携带受控 sync mutator，但包内 mutator 在没有合法 selection receipt，或没有逐根重复 target-root + authority + proof 时必须零写入；INSTALL-PROMPT 的 .agents + current proven tool 与 fanout forbidden 继续是安装入口硬门。
- [CONTROL_PLANE] 安装、同步和 legacy 迁移前必须已完成源码提交、候选包构建、pre-install gate 和恢复点；任一写入失败立即停止后续根写入并执行既定回滚/部分应用报告。

2026-08-03 只读证据快照：

- [PLANNED_UNVERIFIED] delegated read-only evidence 显示 GitHub Packages beta 安装命令为 npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com。
- [PLANNED_UNVERIFIED] 该时点证据为 beta dist-tag=1.0.5-beta.0 / beta1.0.5（npm version / product version）。该信息是时间点证据，不是当前远端事实；发布阶段必须重新联网核验 dist-tag 与 package identity。
- [CONTROL_PLANE] beta1.0.6 尚未完成远端发布核验前，不得把本地 VERSION、release metadata、package candidate 或计划文字表述为 npm beta dist-tag 已指向 beta1.0.6。
- [PLANNED_UNVERIFIED] 当前工作树旁路证据显示 check_active_copy_hashes 与 sync_active_copies 仍默认硬编码五根；INSTALL-PROMPT 规定 .agents + current proven tool 且 fanout forbidden；install_current_agent_copy 对 unproven current tool 会静默省略且 receipt 缺 proof；release gate receipt validation 只验证 schema/status/package hash；package 仍含 sync mutator，而 active checker 已是 repository-only。以上均是 P0 red evidence，不是能力通过证据。
- [PLANNED_UNVERIFIED] delegated observation：custom-model-502 与 ECONNRESET 出现在外部 runtime 日志中，作为分离诊断线索保留。
- [CONTROL_PLANE] 无本机可重复证据不得把 custom-model-502/ECONNRESET 归因为本机 root-selection、install 或 package 行为，也不得据此改变 root-selection/install/release 结论。

### 4.5 Git 与发布

- [CONTROL_PLANE] 只修改本 task 的 child worktree；不吸收根控制面或其他项目的无关脏状态。
- [CONTROL_PLANE] 每个验收/handoff 门要求 root 和受影响 child 的 index 为空。未提交 worktree 修改必须被明确列入 handoff，不能假称 clean。
- [CONTROL_PLANE] 外部 push、tag、PR、release、upload 和 package publish 仅在所有本地门通过且最新明确授权仍有效时执行；否则停止在本地验收点。

## 五、计划书

### 5.1 目标

- [PLANNED_UNVERIFIED] 使 beta1.0.6 的 native parallel court 路径严格遵守三省六部直接上级链。
- [PLANNED_UNVERIFIED] 使 P00 capsule、semantic receipt、dispatch context、child profile、result envelope 和 recovery handoff 形成单一语义权威链。
- [PLANNED_UNVERIFIED] 使错误层级结果能够在不绕过审核、不伪造身份、不泄露 raw body 的前提下回到正常执行流。
- [PLANNED_UNVERIFIED] 使源码包、安装投影、receipt-selected roots、显式五根+Qoder 目标、legacy locator、installed shards 和 source-only checker 的边界一致。
- [PLANNED_UNVERIFIED] 使 handoff、暂停和最终结诏都绑定统一 CLI 归档身份，并可从明确 plan_cursor 恢复。

### 5.2 非目标

- 不以本计划替代实现、测试、安装回执或 capability receipt。
- 不切换到 superCC，不探测或回退到其他 runtime。
- 不在本阶段打开 pending/private body，不启动 Shiguan Web、Obsidian 或重型索引。
- 不创建第二个 task ledger、共享 mutable tasks.json 或第二套结果完成状态机。
- 不把 source-only 安装 checker 复制到安装根或 loader。
- 不猜测 shard 名称、诏令编号、handoff 编号或十四行字段。
- 不降低 workspace.yaml 的 accepted version 来迎合旧 checkout；版本漂移应在阶段 10 受控修复。

### 5.3 总体验收

只有以下各项全部满足，beta1.0.6 才能进入最终 release/closeout 候选：

1. 三省/尚书/六部/工坊层级在 ordinary native parallel 的 create、reuse、follow-up、wake、recovery 和 result handoff 上一致 fail closed。
2. child profile 六字段合同、P00 single-authority、runtime omitted-capsule、dispatch policy 和 lifecycle 检查全部通过。
3. stale/wrong-hierarchy result 被唯一隔离，raw body 不落盘；门下审核和合法上级交付可审计；目标新 envelope 经正常 finish 才产生完成效果。
4. lineage taxonomy 对 confidence、tie、negation、unknown/new-lineage 有显式结果和兼容性证据。
5. source/package/install projection/installed root 的 shard 清单一致；缺失、额外、陈旧或错误投影均 fail closed。
6. active-copy checker 在源码树可运行，在所有安装根和 loader/import/handler 图中均不存在。
7. 候选包、pre-install、root-selection receipt、install、post-install、显式 selected-root sync、rollback 和 receipt-driven hash verification 形成可追踪闭环。
8. release manifest、SBOM、VERSION、release metadata、source budget、privacy、portability、CLI 和 release gates 全部通过。
9. root control plane 在不覆盖用户无关修改的前提下与 accepted child release 对齐，并通过 repo-control doctor 和所需 capability evidence 验证。
10. 门下最终复核通过；handoff/结诏使用有效 archive receipt 的 closeout_identity；root 和 child index 清洁。

## 六、阶段计划：五个宏阶段（保留旧游标别名）

本节只定义可验收的阶段边界，不把当前实现文件、夹具数量或某一次 CLI 参数当作长期合同。旧 `stage-0` 至 `stage-10` 仍作为 evidence/receipt 的兼容别名；它们是宏阶段内的子门，不再单独形成新的执行阶段。阶段事实、命令回执和游标推进仍以绑定执行书及阶段 log 为准。

| 宏阶段 | 覆盖旧别名 | 目的 | 当前状态 |
| --- | --- | --- | --- |
| M0 基线与执行契约 | stage-0—2 | 恢复锚点、三省六部层级、P00/native admission | LOCAL_GATE_PASSED（历史前置） |
| M1 运行时结果恢复 | stage-3 | quarantine、review、handoff、target finish、consume、replay | CURRENT_CURSOR |
| M2 语义与安装边界 | stage-4—7 | lineage、projection、root receipt、legacy locator、shard inventory | PLANNED_UNVERIFIED |
| M3 源码与候选包验收 | stage-8—9 | source acceptance、候选包、selected-root install/rollback | PLANNED_UNVERIFIED |
| M4 控制面与终审 | stage-10 | doctor、capability evidence、外部发布核验、门下终审、archive handoff | PLANNED_UNVERIFIED |

### M0：基线与执行契约（旧 stage-0—2）

分类：[CONTROL_PLANE] + [PLANNED_UNVERIFIED]

M0 只保留为历史前置门：验证精确安装 skill、workspace/child/worktree/branch/HEAD、root/child index、三省六部直属边界、P00 capsule/semantic receipt、runtime=native 和 native host receipt。任何 anchor、层级、second-authority 或 omitted-capsule 漂移，都在当前唯一游标记录 `prerequisite_drift`，不得回退或重跑旧阶段。

验收：M0 的既有 local gates 继续以原 evidence/receipt 为准；本计划不再重复列出实现文件和命令清单。

停止门：任务、分支、HEAD、skill、层级、P00、runtime 或 index 不匹配即停止；不得用新增伪字段、弱化 forbidden gate 或 superCC fallback 获得 PASS。

### M1：运行时结果恢复链（旧 stage-3）

分类：[PLANNED_UNVERIFIED]

阶段状态：CURRENT_CURSOR。唯一恢复游标固定为 `stage-3/result-recovery-chain`，只有本宏阶段的 typed receipts 和停止门全部通过后，执行书才能推进到 M2。

固定状态机：

    source: RESULT_MISMATCH -> QUARANTINE_CORE_COMMITTED + SOURCE_TERMINAL_CLOSED
    recovery: REVIEW_PENDING -> READY_FOR_HANDOFF | REJECTED -> HANDED_OFF -> CONSUMED

验收只看以下合同，不绑定具体实现形态：immutable `court.office.result_quarantine.v2` core；source terminal/write-claim 同锁关闭；`court.office.result.v1` exact whitelist 与 pre-adapt source digest；scrubbed projection；门下 typed review；合法直属上级 typed handoff；target exact binding/native receipt；target 自己的正常 finish 与 typed consume；CAS、append-only recovery head、三段 crash journal/replay、legacy read-only、privacy sentinel。未知字段、raw/private body、自由文本身份、越级 handoff、旁路 consume 或任一零字节失败门均停止。

验证：使用执行书规定的 semantic、lifecycle、native-host、intervention、unified CLI 和 diff 检查；实际命令以当前 CLI help/manifest 为准。

停止门：任何 schema、source terminal、target binding、receipt、journal、privacy、legacy 或 CAS 失败均保持 `stage-3/result-recovery-chain`，记录 blocker 和 evidence，不推进 M2。

### M2：语义与安装边界（旧 stage-4—7）

分类：[PLANNED_UNVERIFIED]

按三个子门顺序完成：

1. **语义子门**：lineage 对 confidence、tie、negation、unknown/new-lineage 给出确定性结果；旧记录只读兼容，不以 normalization 赋予执行权。
2. **投影子门**：install projection、source-only checker、runtime/import/loader closure 和 root-selection receipt 形成一致边界；shared primary、current tool、explicit extras 必须逐根有 authority/proof，未经证明零写。
3. **迁移子门**：legacy locator 迁移、selected-root sync、alias 分组和 installed shard inventory 以同一 receipt 为依据；缺失/额外/陈旧 shard 必须有 consumer 与 evidence，部分写入可回滚，禁止默认 fanout 或递归删除。

验收：每个子门分别留下 typed evidence，但宏阶段只在三者均通过后闭合。命令、文件清单和具体 checker 由当前 manifest/CLI 解析，不在计划中预造。

停止门：unknown 强制归类、receipt 外根写入、unproven target 被省略、source-only checker 进入安装、selected set 漂移、shard 无 consumer/evidence、迁移或回滚丢字节，立即停止并记录 `blocked_stage=M2/<subgate>`。

### M3：源码与候选包验收（旧 stage-8—9）

分类：[CONTROL_PLANE] + [PLANNED_UNVERIFIED]

先完成源码 acceptance：完整 release/CLI/runtime/privacy/portability/legal/lineage/projection gates、diff 归属审查和 child index 门；再从已验收 child HEAD 构建候选包，执行 package/provenance/root-selection/install/rollback/post-install 检查。安装写入只允许在明确授权、已验证 selected-root receipt、备份和回滚证据后发生；本宏阶段不自动获得发布授权。

停止门：源码门未闭合、候选包非已验收 HEAD、receipt/provenance/selected set 篡改或缺失、安装首字节前无法 fail closed、部分应用无法回滚、checker/shard/root 集合漂移，保持 `blocked_stage=M3/<subgate>`，不得进入 M4。

### M4：控制面、发布与终审（旧 stage-10）

分类：[CONTROL_PLANE] + [PLANNED_UNVERIFIED]

仅在 M3 闭合后，受控对齐 root catalog/version/doctor 和 capability evidence；重新核验外部发布授权、远端 package identity/dist-tag/provenance、安装 receipt；尚书统合后交门下终审。只有门下接受、有效 archive receipt 和逐字 `payload.closeout_identity` 才能形成 handoff/结诏；没有这些证据只能 `handoff_or_pause`、`partial_or_not_run` 或 `authority_blocked`。

停止门：root/child index、doctor、capability evidence、release commit、授权、远端事实、门下 verdict 或 archive receipt 任一不满足即停止；不得把本地 VERSION、计划文字或命令 exit 0 当远端发布事实。

## 七、每阶段 handoff 最小载荷

每次暂停、超时、阻塞、切换 task 或准备结诏时，handoff 至少包含：

- task、child repository、worktree、branch、baseline、current HEAD。
- authority=super、behavior=parallel、runtime=native。
- 独立执行书路径 docs/plans/2026-08-03-decretum-matrix-beta1.0.6-execution-book.md、current stage、唯一 plan_cursor、最后成功 gate、首个未通过 gate。
- root 和 child 的 git status、index 状态及所有未提交文件列表。
- 已执行命令、退出状态、receipt/evidence 路径与 digest。
- 未执行的安装、同步、发布、归档和外部动作。
- 当前 blocker、风险、恢复前置条件和唯一下一条精确命令。
- 若为正式 handoff/结诏：有效 shiguan archive-checkpoint receipt、逐字复制的 payload.closeout_identity、门下复核结果及二者绑定证据。
- 记忆裁定：WRITE、PROPOSE、SKIP 或 DEFERRED；无授权不得写 durable memory。

handoff 不得包含 secret、raw private logs、pending/private body、完整 transcript、整份 diff 或无关 agent 列表。

## 八、当前执行起点

- 当前唯一恢复游标：stage-3/result-recovery-chain。
- 继承状态：stage 0—2 已通过本地门；不得退回 stage 0，不得以重复 stage 0—2 替代当前 P0 修复。
- 当前计划书逐字绑定独立执行书：docs/plans/2026-08-03-decretum-matrix-beta1.0.6-execution-book.md。
- 当前动作：Entry 0009 三省批准、Entry 0012 尚书正式接收 RED；Entry 0013 的 GREEN-A 纯层与 semantic/lifecycle/runtime/native-host/intervention 聚焦门已通过；Entry 0015 已纠正 Entry 0014 的 host false blocker。工部已回报 GREEN-B runtime/recovery pass，但刑部只读复查与门下验收尚未完成，因此不得宣称 P0 已修复。
- 下一条最小动作：保持 `stage-3/result-recovery-chain`；由尚书接收刑部只读复查，随后交门下验收并回写阶段 log。当前不进入 M2/旧 Stage 4。
- 下一阶段入口：仅当 stage 3 全部停止门、crash recovery、zero-bypass 和 typed receipt checks 通过，并由执行书记载真实 receipt 后，才允许推进后续阶段。
- 当前禁止动作：安装、活动根同步、legacy 实写、Qoder 实写、push、tag、PR、release、upload、package publish、史馆正式结诏和十四行输出。
