# CCR-R2-SHIR-20260714-A02 执行书

```text
INSERTION_CODE: CCR-R2-SHIR-20260714-A02
MAIN_THREAD_ID: 019f5e95-4852-7f31-98ef-1d0c70d5e1e4
MAIN_THREAD_ROLE: UNIQUE_TAIZI_INTEGRATION_LANE
STATUS: APPROVED_EXECUTION_ACTIVE
GOAL_MODE: ACTIVE
USER_CONFIRMATION: 确认执行 CCR-R2-SHIR-20260714-A02
AUTHORITY_AFTER_CONFIRMATION: super
TOPOLOGY_AFTER_CONFIRMATION: ordinary_parallel
RUNTIME: spawned subagents, not superCC
PARENT_PLAN_ID: 2026-07-14-court-capability-router-clean-iteration-plan
INSERT_AFTER: Task 2 R2 RED
INSERT_BEFORE: Task 3 R2 GREEN
DETAIL_PLAN: docs/plans/2026-07-14-court-capability-router-shiguan-install-remediation-plan.md
OFFICE_LOAD_PLAN: docs/plans/2026-07-15-court-office-selective-loading-remediation-plan.md
WORKTREE: .
INDEX_POLICY: always empty
NETWORK: zero
REMOTE_PUBLICATION: not run
PROPOSAL_A_MULTI_INSTANCE_DISPATCH: APPROVED
PROPOSAL_B_HOST_MEMORY_MAINTENANCE: APPROVED
PROPOSAL_C_COMPLEXITY_BUDGET: APPROVED
PROPOSAL_D_CHILD_TRACE_SUMMARY: APPROVED
CONTEXT_COMPRESSION_RESUME_ANCHOR: 对任务进度与执行书进行对照再度继续按执行书且调用三省六部skill super并行执行
TDD_REVIEW_GRANULARITY: PHASE
PRE_CHILD_RESOURCE_BUDGET_GATE: CCR-R2-SHIR-20260714-A02-P05-TB01
TEMPORARY_PROGRAM_PAUSE: CLEARED_REPOSITORY_GOVERNANCE_GATE_PASSED
ROOT_CONTROL_REPOSITORY: D:\project
ROOT_CONTROL_BASELINE: 58cd9f9 + de715f3
ROOT_CONTROL_LEDGER: 8d6b056 + b3eada2
RESUME_AFTER: PASSED_A02_PHASE1_CONTINUATION_ACTIVE
```

## 0.1 当前对话临时恢复锚点

```text
对任务进度与执行书进行对照再度继续按执行书且调用三省六部skill super并行执行
```

每次上下文压缩、摘要恢复、权限变化或中断恢复后必须：

1. 重新加载本执行书、A02 详细计划和 `court-capability-router` 必要语义。
2. 对照当前 goal/plan、已完成门禁、首个未完成步骤、Git index、活跃/残留 agente 与进程。
3. 不创建第二任务；以原 task/goal 的 continuation/correction 继续。
4. 再度按本执行书并调用三省六部 skill，以普通 `super并行` 执行。
5. 当前对话临时记忆仅用于本目标恢复；目标完成、取消或被新旨意替换后失效。
6. TDD 审查粒度固定为阶段级：保留测试先行，但不为每个单点单独召集审查。

## 0.2 Semantic Continuity Guard（PLANNED / RED）

本合同统一超长任务在 dispatch -> child result -> apply/commit -> compaction/resume -> closeout 之间的语义连续性，但不新增第二权威、第二数据库、第二状态机或无界 daemon。

- 唯一运行权威仍是现有 `tasks.json` 当前 task 与 append-only `court_events.jsonl`；史馆、长期记忆、Obsidian、Git/recovery 只提供证据、投影与恢复锚点，冲突时降级旧证据，不改写 runtime 权威。
- `semantic_epoch` 直接等同 `charter_revision`，不得另建独立计数权威。`authority_revision`、`plan_revision/plan_cursor`、`git_fingerprint`、`recovery_checkpoint_id` 分别描述权限、计划、工作树和恢复漂移，不得混装进 semantic epoch。
- 每个 task 保存小型 invariant capsule：最新旨意锚点、non-goals、边界、allowed/forbidden、acceptance、evidence、stop gates、write-set 与 governing bundle canonical hashes。目标 `<=2 KiB`。
- dispatch/admission/start/report/finish 必须绑定 `task_id, semantic_epoch, charter_sha256, invariant_capsule_sha256, dispatch_uid, attempt, office_instance_id, role, direct_superior, worktree, write_set, lease, preload hashes`。自由文本结果不能绕过这些字段。
- correction 在同一 runtime lock/CAS 下递增 charter revision/semantic epoch、写入新 charter/hash，失效旧 assessment/checkpoint/completion/dispatch/admission/active agents/capsules/attempts，并强制回 `ThreeDepartments`。旧 epoch/attempt/dispatch 的迟到结果只能 `QUARANTINED`，不得静默 rebase/apply。
- compaction 前（可行时）以及 compaction/resume/reboot/long-idle 后自动 checkpoint/verify；dispatch、apply、commit、closeout 前统一运行 drift detector。mutation 一律 fail closed；只有只读诊断可在已验证 current snapshot/capsule 上报告 `runtime_degraded`。
- 状态只允许 `UNVERIFIED -> VERIFIED -> DISPATCHABLE`；发现漂移进入 `DRIFTED -> QUARANTINED -> CORRECTED -> REVERIFY`。权限变化只增 `authority_revision`，计划推进只更新 `plan_cursor`，Git/worktree 只走 fingerprint gate。
- JSON receipt 至少含 `schema, checkpoint_id, task_id, semantic_epoch, charter_sha256, invariant_capsule_sha256, authority_revision/sha256, plan_revision/sha256/cursor, dispatch_uid, attempt, agent_id, write_set_sha256, git_fingerprint, recovery_checkpoint_id, event_head_sha256, trigger, gate, verdict, reason_codes, created_at`。
- agent-first API 为 `court semantic checkpoint|verify|correct|resume|quarantine|reconcile`，核心规则是纯函数、I/O 走现有 runtime/CLI/archive/result adapters；Python stdlib/pathlib/os.replace，Windows/macOS/Linux 一致。默认 gate 为 O(1) hash 比对，仅在输入 mtime/size/ref 变化或 correction 时重算；local verify p95 目标 `<250 ms`。
- Phase 9 reviewer 只消费同一 verified receipt 并输出 findings；V2 memory adjudication 只处理 durable memory candidates 并引用 verified semantic epoch 作 provenance。二者都不是 runtime 状态机。

## 0.3 史馆 CLI 多对话编号与谱系事务合同（PLANNED / RED）

本合同把多对话、child agent 与 worktree thread 的诏令编号、古制谱系、runtime event 和史馆 closeout 收敛到现有权威链；它不新建第二 cluster、第二账本、第二编号权威或第二数据库。

- 唯一 runtime authority 仍是 `tasks.json` 当前 task 加 append-only `court_events.jsonl`。允许新增一个最小 `scripts/court_operation_journal.py`，但它只能保存幂等 operation/recovery receipt，不能保存另一份 task 状态、event history、编号序列或每-worktree 独立 runtime ledger。最小绑定字段为 `operation_id, payload_sha256, expected_task_revision, decree_id/main_court_code, parent_court_code, child_no, lineage_key, lineage_version`。
- `court decree-open` 对同一旨意只分配一次主诏令编号并冻结 `main_court_code/lineage_key/lineage_version`；重试复用同一 `operation_id` 和已分配结果。只有显式 `reclassify` 操作可以产生下一 lineage version；不得改写历史 `court_code`，也不得因对话、carrier 或 worktree 改变而重编号。
- 通用 lifecycle API 固定为 `court office admit|start|report|finish|close`。现有 `agent-*` 命令继续作为 `carrier_kind=child_agent` 的兼容包装；`worktree_thread` 只在同构 receipt 上增加 `thread_id, worktree_fingerprint, branch, start_head` proof，不另建 task/event 文件。
- closeout 使用三段可恢复 saga：`PREPARED`（持 runtime lock，CAS 校验 `expected_task_revision` 并固化 compound intent） -> `ARCHIVE_COMMITTED`（持 Shiguan lock，提交唯一 archive/index side effect） -> `TASK_EVENT_COMMITTED`（重新持 runtime lock，提交 task/event paired receipt）。`court closeout-recover --operation-id <id>` 从最后一个已验证阶段继续；每个 allocation/archive/index/task/event killpoint 重放均必须 exactly-once。
- repair-cluster 映射固定而不新增 cluster：RC2 拥有 generic semantic/operation interface、CAS、compound receipt 和 closeout recovery；RC4 在 RC2 之后串行拥有 `office_instance` 的 `child_agent|worktree_thread` lifecycle 与冻结谱系；RC6 拥有 local authority realm/root fingerprint 与 root-mismatch fail-closed。既有 same-root file lock 和 32-process allocator uniqueness 只作为正回归，不重复实现。
- Phase 1 先在临时本地根完成 RC2 core，再串行接 RC4；RC6 fingerprint 纯函数/fixture 可同步进入 Phase 1，但真实 authority-root 绑定与 RC2 archive transaction 必须等待既有 pending/migration 门禁后串行接入。`pending_count=69` 不得反向阻塞不读取真实史馆的 Phase 1 core，也不得被 core 测试用于绕过真实迁移停止点。
- 支持边界仅为 Windows/macOS/Linux 本地文件系统。跨主机、NFS、SMB、分布式锁、SQLite、HTTP service、MQ 均为 `DEFERRED|UNSUPPORTED` 并 fail closed。CLI 只编排 Codex/Git/史馆既有适配器，不能替代 Codex task authority、Git provenance 或 Shiguan archive。
- dispatch/context 只携带 hash、相对 path 与 evidence pointer，不复制完整 prompt、diff、私密正文或 pending body。Phase 9 只复核本合同覆盖和回归，不得把应在 RC2/RC4/RC6 落地的整改推迟到最终审查。

## 0.4 项目记忆索引与子 agent 名称正交合同（PLANNED / RED）

- 当前裁定固定为 `PROJECT_MEMORY_CONTENT=PASS`、`GLOBAL_MEMORY_INDEX=FAIL_PENDING_INGESTION`。根权威 `D:\project\docs\project-memory.md` 存在且内容有效；失败原因是 global memory 尚未摄取既有 root-governance intake note、旧 current pointers 待 append-only supersede，不是搬迁或内容丢失。历史 MEMORY entries 必须保留，不删除、不原地改写。
- 后续仅在既有 RC3/project-memory 与 Phase 8 root-memory follow-up 获得执行顺位时，create-only 写一个小型 ad-hoc superseding note：更新当前 D 盘 common/integration/A-B-G 路径、checkpoint/progress，并请求 global ingestion；同时只微调 root project-memory 的 pause wording 与 global index status。不得直接覆盖全局 `MEMORY.md` 正文，也不得把该 note 或 MEMORY 文字当作项目行为实现证据。
- `task_name/collaboration address`、sidebar title、repo-control task/worktree id、office role 是四个正交表面。`task_name` 在首次 spawn 时固定，followup/reuse 不重命名；sidebar title 只是 UI，repo-control id 只是项目/工作树控制标识，二者都不授予官署语义。
- 新官署实例的 `task_name` 必须以规范 role prefix 开头；只允许同 role 复用。generic 或跨 role task_name 不得声明 `office_execution_ready`。同 role 的旧任务后缀即使过时仍可复用，不为美观重建实例或浪费谱系。
- 官署 readiness 的唯一证据是 `role + office_instance_id + assignment + direct_superior + ordinary dossier/profile/SKILL relative path/hash + preload ack`。collaboration address、task name 文案或 sidebar title 单独均不是 readiness 证据。
- 不新增 repair cluster：RC3 承接 project-memory/global-index append-only supersede；RC4 承接 carrier/task-name/role/readiness binding；RC5 承接 rollout 身份债务，统一 `README.md`、`references/sections/court-office-name-profile-skill-binding.md` 与 `court_office_bootstrap.py` 的 `required_skill/loaded_skill` 为 `decretum-matrix`，同时保留 `court-capability-router` 技术 locator。

## 1. 最新旨意汇总

1. 先修改并确认执行书；确认前不继续实现、迁移、Obsidian、安装或打包。
2. A02 固定插在父计划 Task 2 RED 之后、Task 3 GREEN 之前；A02 的 RED、GREEN、SPEC、QUALITY、整体验收全部通过后才恢复父 Task 3。
3. 第一项真实主机变更必须是史馆迁移；迁移前不处理 Obsidian、skill 安装或发布包。
4. 最终全机只有一个共享史馆物理库：`%USERPROFILE%\.agents\court-shiguan\court-capability-router\references`。
5. 旧 `%LOCALAPPDATA%\court-shiguan\court-capability-router\references` 只保留 junction 兼容入口，不得成为第二个物理库。
6. `.agents` 是必装共享 skill 根；默认只额外安装当前智能体工具。本机当前工具为 Codex，所以只安装 `.agents + Codex`。
7. 未经更新且明确的旨意，不安装或更新 Claude、Hermes 或其他工具；其现有字节只做前后哈希不变验证。
8. 四个跨对话史馆文件以 `.agents/skills/court-capability-router` 为基准保持原相对路径、长度和哈希，不移动、不覆盖、不作为迁移输入。
9. 持久化路径使用相对语义：普通官署为 `agents/standing-officials/<role>.toml`、`agents/office-dossiers/<role>/AGENTS.md`、`SKILL.md`、`.agents/court-shiguan/...`；只有显式 superCC receipt 才可记录 `agents/supercc-dossiers/<role>/AGENTS.md`。绝对路径只允许在内存中解析、打开和校验，不写入 dossier、runtime binding、manifest 或包。
10. 所有官署都应用一致的名称、profile、TOML、skill、上级、dossier、证据与释放语义，不只修一个官署。
11. 子线程官署身份必须来自实际加载对应 `AGENTS.md`，不能靠父 prompt 宣称。每次 spawn 必须携带 role、相对 dossier/profile/SKILL 路径和哈希，child 读取后回传 preload ack，方可进入 `running`。
12. 初次加载 `$decretum-matrix` 时，在 `SKILL.md` 顶部置顶一段短而充分的语义核：最新旨意、三权/普通 super并行、合法流程、官署职责、agent-admit、共享史馆/安装边界、收尾门禁。它引用既有治理语义，不另造第二套 skill 宪制。
13. 太子—三省—尚书—六部—工坊/工匠职责一一对应：
    - 太子：收旨、定性、转奏、综合、对用户回奏。
    - 中书省：拟旨、研究、拆解、验收标准。
    - 门下省：封驳、风险/范围/完整性审计、最终复核。
    - 尚书省：排依赖、统筹六部、序列化共享写入、整合部奏。
    - 六部：主要执行已批准的专业任务。
    - 工坊/工匠：最后的具体实现、测试、迁移、安装、打包执行层。
    - 史馆：三省共监、门下主审，负责证据记录，不是第七部。
    - 直属上级链不可跨级：六部的上级是尚书省；工匠/worker 的上级是其所属六部。太子、中书省、门下省不得绕过尚书省和所属六部直接派遣工匠。
14. “六部承担三省审计/太子统筹”属于加载/派遣漂移，不重写底层 skill 官制本体；修 preload、dispatch packet 和验证即可。
15. 中断、权限变化或用户纠正必须继续原 goal/task：检查遗留命令和 index，形成 `TASK_CONTINUATION`/`TASK_CORRECTION`，修订 charter，重新进入三省复议，再恢复尚书执行；不得为同一旨意新建第二任务。
16. 子线程不只审计。三省批准后，六部和工匠必须承担实际代码、测试、迁移、文档和包验证工作。
17. 允许更激进的并行，但只并行独立且文件所有权不重叠的工作；同一文件、真实迁移切换、Obsidian、安装、打包保持单写者串行。
18. 每次版本迭代由执行者主动更新 `README.md`、`CHANGELOG.md`、`RELEASE-LOG.md`、`docs/logs/README.md`、本轮日志和 `release-manifest.json`。
19. 保留 beta0.5.12 全部既有工件；保留 beta0.5.13 `run1/run2` 原字节；只新增 beta0.5.13 `run1b/run2b`。
20. 当前根治理仓与 Court 子仓每个 gate 前后都保持 Git index 为空；Court 项目提交只允许发生在 §3.1 的 major-stage 有界 commit 窗口，且只位于对应 `release/beta0.5.x` child worktree。Phase 3 明确规定的共享史馆与原生记忆 Git checkpoint 是宿主数据托管操作，只能按批准 pathspec 串行提交并在提交后恢复 clean index。根治理仓永不承载产品提交或上传；Court 子仓的 remote/push/tag/PR/release 默认禁止，唯一条件例外是 §3.2 对“紧邻上一已完成版本”及精确 action allowlist 的单次授权。
21. 将原二元 `scope_value_gate` 修订为 `complexity_budget_gate`：用户最新明确说明拥有最高优先级；用户未指定时，才由太子主持预算裁量。默认从简但不得盲目禁止必要复杂度，中书说明价值、门下审风险、尚书核预算与调度。
22. 保持最小、最优、最快、可恢复、可追溯、完整、可用；不做过度打磨或低边际价值目标。
23. 官署 `role_key` 不等于只能有一个执行实例；除太子外，可按适用面扩展同官署 worker instances。六部同官署多路执行亲和度最高，三省较低，尚书省除超级巨型任务外极低。
24. 史馆应主动维护当前宿主 agent 工具的长期记忆候选和投影队列，但不得静默直接改写任意工具的 `MEMORY.md`。史馆实录与长期记忆允许在迁移后的同一共享 Git 仓库和 Obsidian vault 中托管，但必须使用不同目录、schema、生命周期和写入门禁：实录追加不回改，记忆可经裁定更新/合并/废止，并以证据引用指回实录与 Git commit。
25. 每个子官署不把全量 prompt、正文或日志复制进史馆，但必须留下轻量的时间—事件—行为记录，保证完整追溯链。
26. `CCR-R2-SHIR-20260714-A02-P05-TB01` 固定插在 Phase 0 之后、Phase 1 RED 和任何 child agent 启动之前。所有子官署 wave 必须先由太子评估并明确批准资源预算；禁止先按最大规模启动，再靠中断多余 agent 回收预算。
27. 调用 `$decretum-matrix` 后需要选择其他 skill 时，必须先查询既有能力官籍账册 `references/court-capability-registry.md`，优先使用已登记、已验证、适配当前工具且未失效的能力；不得默认每次全盘扫描。吏部负责主动、事件驱动地维护账册。
28. 本执行书全部行为整改必须落入项目 `SKILL.md` 的必要语义核、其直接 governing reference 和对应生产实现/测试。`MEMORY.md`、临时记忆、史馆候选、update note 或旧对话只能作为召回线索，不能作为“行为已实现”的验收证据。
29. 史馆迁移与单一物理库验证成功后，在新的 `.agents\court-shiguan\court-capability-router\references` 权威根初始化或接管一个本地 Git 仓库；它同时托管通过隐私门禁的正式实录、记忆候选/裁定、共享批准记忆、分工具 metadata/index 投影和 Obsidian 派生树，但不成为第二数据库或第二权威。仓库默认无 remote、无 push；只允许单写者在阶段 checkpoint、结诏或记忆裁定时提交，禁止为 heartbeat/临时日志逐条提交，且每次提交前后 Git index 必须为空。
30. 史馆 Git 只跟踪 allowlist 中的正式/已净化内容；`court-runtime/`、`agente-logs/`、`shiguan-imports/pending/**`、SQLite、原始 transcript、私密 raw evidence、Obsidian API key/config、真实 host config/controller preimage、备份与 release package 必须 ignored/untracked。实录已提交后不得 amend/rebase/重写；纠正以新的 `supersedes` 实录追加。长期记忆可由新裁定更新、合并或废止，但必须保留 `derived_from_record`、`evidence_refs`、source commit 和当前状态。
31. `CUTOVER_VERIFIED` 只证明物理迁移，不等于整体迁移完成。对每个 `active_verified|installed_verified` 工具，必须在其运行态解析出的原生记忆入口顶部（若有工具强制 frontmatter/header，则紧随其后且先于普通正文）写入幂等、受标记管理的共享史馆链接，并在史馆该工具 namespace 写入指回原生记忆 source/repository HEAD 的反向链接。只有全部工具回读一致后才生成整体 `MIGRATION_LINKS_VERIFIED`；逐工具 `LINK_BINDING_BLOCKED` 只能精确报告并阻断整体完成，不能替代成功。该最新明确旨意只授权未来实现该导航链接，不授权启用、填充或改写非当前工具的其他记忆内容。
32. “各工具”是开放集合，`codex`、`claude-code`、`hermes` 只是内置适配示例，其他工具使用稳定 `other:<stable-id>`。每个已验证安装工具的原生记忆库必须保留实际 loader/controller 所需路径，不迁入共享史馆、不复制正文到共享史馆、不改写为统一格式；同时必须以独立 Git 仓库形式由史馆原地托管。优先登记既有 owning Git repo + memory pathspec；无 Git 时仅在兼容性探测通过后于原位初始化，原位 `.git` 不兼容时可用史馆管理区中的 separate git-dir 配原生 work tree。史馆新建的工具记忆仓库无 remote；既有工具自有 remote 只记录并原样保留，史馆不得新增、修改、fetch 或 push。工具记忆仓库不作为共享史馆仓库的 submodule/subtree/nested tracked repo；separate git-dir/objects 也必须被共享仓库、Obsidian 投影与发布包排除。
33. 共享史馆 Git 仓库是管理中枢，通过 registry 将若干原地工具记忆 Git 仓库逐一链接起来。每条稳定 `memory_store_id` 记录 `tool_class`、native root、repo root/git-dir、memory pathspec、loader/controller 证据、branch/HEAD、memory state、write policy、shared/native commit 和同一 `transaction_id`；原生仓库 pinned block 反向记录 shared repo id/namespace/commit。两仓库分别提交并以 receipt 互引，不能伪装为跨仓库原子提交；只暂存本轮批准的 managed-link/update-note 路径，不吸收已有未关联改动，提交前后所有受影响仓库 index 必须干净。非当前工具默认只登记、投影和写置顶 managed block，不写其记忆正文；当前工具记忆写回仍需最新明确授权和门下批准。
34. 史馆迁移成功后，Obsidian 必须为安装投影/manifest 已证明实际安装本 court skill 的每个 agent 工具类显示 MEMORY/memories 的 index-level 投影。每类使用隔离 namespace 和独立 graph，禁止跨工具合并 node/edge。
35. 安装投影/manifest 是运行态探测生成的审计收据，不是手工静态清单。判定顺位固定为当前运行进程/CLI -> 相关环境变量和 tool home -> CC Switch 当前 profile/target block/path override -> 实际有效配置与 loader 优先级 -> 解析出的 skill root、`SKILL.md` 版本/hash -> 可用 runtime probe。DB、目录名、环境变量或文件存在任一单项均不能独立证明安装。
36. 工具安装状态统一为 `active_verified|installed_verified|detected_unverified|not_installed_verified|unknown`。`active_verified` 与 `installed_verified` 必须各自拥有独立记忆 namespace/graph；即使原生记忆为空，也记录 `empty|disabled|unavailable|unknown` 等 memory state 而不伪造正文。`detected_unverified`/`unknown` 只显示探测证据，不自动投影、启用、Git 初始化或写入；只有核验了实际 loader 的全部有效根后才可裁定 `not_installed_verified`。
37. 原生记忆文件始终是工具侧权威来源；“Git 托管”不改变其 loader、格式和写入接口。默认投影只含相对 source id/path、repository HEAD/commit、hash/fingerprint、状态、headings/topics/relations 等 metadata/index，不复制私密 raw body，也不读取或写入 release package；除上述置顶 managed block、工具自身正常写入和另行批准的 current-tool update-note 外，史馆不得改写正文。任何 body mirroring 必须等待后续明确旨意和门下隐私复核。
38. 空白宿主在创建共享根、初始化任何史馆/工具记忆 Git、启用任何 memory feature 或进行任何安装写入之前，必须按上述运行态探测链对 detected/selected tools 做只读 memory-feature probe，向用户显示安装状态、`enabled|disabled|unavailable|unknown`、原生记忆路径/Git 兼容性、对应证据和下一步选择提示。probe 不得安装或启用任何内容；`unknown` 对自动启用 fail closed。对已验证安装的 Claude/Hermes/`other:<id>`，本次最新旨意只授权未来原地 Git 托管和 pinned managed block；安装、配置、启用或正文写回仍须另有最新明确授权。
39. 空白宿主配置目标统一为 `codex|claude-code|hermes|other:<stable-id>`，并且只在史馆迁移/空白无源证明和 current-tool/target 解析之后处理。先只读探测真实 source-of-truth/controller；标准未满足、未获最新明确 config-change 授权，或 DB schema、字段所有权、有效优先级、当前值、兼容语义不确定时，均不修改，返回不阻断其他任务的 `REMINDER_ONLY`，并明确 `compliance_claimed=false`。CC Switch 存在且其目标工具 block 已证明时优先备份并事务化更新上游；Codex 还必须把批准 delta 以等价/兼容语义合并到 `config.toml` 与 `managed_config.toml`，保留 secrets/provider/unknown keys，禁止盲目字节替换或只改会被 controller 回写的 leaf TOML。无 CC Switch 时走受控可回滚双文件路径。Hermes 的 CC Switch 管理失败须保留 attempt/result，随后只有在明确授权且语义确定时才可走实际文件路径。最终验收必须来自实际有效配置文件 reread/parse 和可用时的 runtime probe，绝不能只看 DB。实现复用现有 `ccswitch-codex-deep-reset.md` 与 `codex-ccswitch-recovery.md` 恢复证据，不另造框架。
40. 根级仓库治理已按后续最新明确旨意升级为项目级单入口模式：A02 先以双层恢复点暂停，`D:\project` 本身成为可执行的本地 Git 控制仓库和 Codex 唯一新增项目入口，只跟踪 `workspace.yaml`/schema、`repo-control`、治理文档、模板与选定证据元数据；独立子仓库、真实 release/recovery/staging bodies、实时 `.codex/config.toml` 与 `D:\project\worktrees` 均不进入根历史。`court-capability-router`、`uu-remote-cli` 及未来 manifest 新增项目继续拥有独立 common-dir、历史、分支、版本、CI、LICENSE 与发布生命周期。Codex 可见任务壳归属根项目，真实 child worktree 由项目级清单创建在 `D:\project\worktrees\<project-id>\<task-id>`，通过 task-local `attached/<project-id>` 入口访问，并只连接目标子仓库 common-dir；不得要求用户再次把每个子仓库登记为 Codex 项目。不得修改 Codex 全局 worktree root；不得采用 submodule superproject。根仓库和子仓库都不配置 remote、不 push、不发布；未来若获发布授权，只逐个发布 GitHub-ready 子仓库，绝不发布 `D:\project` 根控制仓库。
41. 子官署实例简记与 worktree 史馆实录是两层独立追溯证据。每一个由本 court 创建、接管、维护或用于任务的 Git worktree 都必须形成自己独立的史馆实录；本轮至少覆盖全部 A02 worktree。每条记录以稳定 `worktree_trace_id` 绑定 `repo_id/common-dir fingerprint`、worktree 身份、base/HEAD/branch 或 detached 状态、task/phase/lane、owner/direct superior、批准写集、开始/结束时间、index/pyc 状态、RED/GREEN/SPEC/QUALITY 证据、恢复点及最终 `integrated|retained|retired|blocked` 处置。不得只用“某 child 已记录”替代 worktree 实录，也不得复制完整 prompt、diff、源码正文、私密日志或 pending body；复用现有 append-only 史馆/checkpoint 路径，不新建数据库或后台服务。
42. 官署加载采用 `PURE_SKILL_REQUIRED` 单一路径整改：每个选用本 skill 的 routine child 必须完整读取经过瘦身的根 `SKILL.md`，再完整读取本 role 的精简 dossier/profile，并只附加 direct adjacency、bounded task/budget/worktree packet、registry hit 与行为触发的 governing references；实测 bytes/latency。根 skill 不得继续内嵌全部 references/14 官署扩展内容，也不得默认加载其他 role。最小官署加载合同必须完全在可移植 Skill 及其直接 governing references/生产检查器中落地。本轮不创建、打包、安装、测试或预留 Codex plugin、plugin-only MCP/UI/manifest/cache 路径；不插件化是通过结果，不是遗留缺口。
43. 记忆治理固定为三层正交：`semantic_adjudication` 由史馆做证据/隐私/去重/冲突/范围/时效分析并由门下裁定；`write_authority` 只回答最新用户是否授权写回及目标工具；`native_application` 只负责 adapter apply、native queue/reread 与 Git receipt。三权 `approval|autonomous|super` 只控制执行/写回权限，不等于门下语义裁定。
44. 主线审查采用 A-G 有界专项只读 fan-out，而不是单一宽泛 reviewer。每项 finding 必须用统一 schema 回报；门下是唯一去重/裁定 aggregator，尚书只派发 `ACCEPTED` repair clusters，同一文件/权威保持单写者。
45. RED/GREEN/SPEC/QUALITY 以 repair cluster 为最小完整闭环：专项发现 -> 门下裁定 -> 最小可复现 RED -> 单 owner GREEN -> 对应专项复核 -> cluster SPEC/QUALITY -> 全局回归。不得为每条微问题重启完整三省，也不得用批量文本替换制造假 GREEN。
46. 所有既定阶段、记忆裁定整改和平台验收完成后，必须执行一次全仓只读优先审查。若 `ACCEPTED findings=0`，输出 `FULL_AUDIT_PASS` 且不建空分支；若大于零，只在独立 child worktree/新分支修复并创建本地提交，报告 remaining findings，等待用户后续裁定。
47. 最新最终安装旨意仅在全部整改与全仓审查通过后生效：单一集成 writer 将全部 accepted changes 落到本地最新版本分支 `release/beta0.5.13`，从该分支重建最终确定性包，并把同一最新版 portable skill 同步到本机固定五个 canonical 物理目录：`~/.agents/skills/decretum-matrix`、`~/.codex/skills/decretum-matrix`、`~/.claude/skills/decretum-matrix`、`~/.hermes/skills/decretum-matrix`、`user_data_base()/hermes/skills/decretum-matrix`。目录 basename、machine name 与 canonical skill name 必须一致为 `decretum-matrix`，五根逐文件 SHA-256/版本必须一致。该授权只覆盖 skill 安装/升级，不授权工具配置、memory enable/body write、remote/push/PR/tag/release publication，也不扩展到未知工具。
48. 最终 `SHIGUAN_LATEST_SYSTEM_GATE` 必须证明本机史馆系统已按最新版完整迁移/重构：唯一物理权威根在 `.agents`，旧 LocalAppData 仅为正确 junction；runtime/CLI/checkers/schema/index/bridge/daemon/service/Obsidian vault/shared Git/native-memory links/worktree records/recovery receipts 均来自并匹配最终版本 manifest，旧代码/旧 schema/第二物理库/脏 index/失配服务均为失败。该 gate 仍要求 pending-body 与静默门禁合法通过，不得读取或绕过当前 `pending_count=69`。
49. 官署载体统一为 `child_agent|worktree_thread|supercc_cli_office`。`worktree_thread` 必须使用与 child agent 近似的 task/role/direct-superior/budget/lease/write-set/dossier/profile/SKILL/semantic receipt/dispatch/result/status/communication 合同，并通过根项目可见 task + `attached/<project>` 绑定项目级物理 worktree；worktree 是隔离载体，不是第二官署权威。不得让两个载体同时成为同一写集的 writer。
50. `superCC` 是实验性 CLI-only 载体，不是三权之一。在三权/拓扑选择阶段必须先显式告知其实验性、CLI/zellij+squad 依赖与 ordinary super 差异；只有最新明确 `superCC` 启用才可加载其 annex/profile/scripts/daemon/visible-office 语义。普通 `approval|autonomous|super`、普通并行、历史记忆或配置均不得隐式启用；未启用时 superCC 全部按需内容必须保持未加载。
51. 三省六部 skill 的正式用户侧品牌改为拉丁词根 `Decretum Matrix（诏令矩阵）`，规范 skill name/invocation 为 `decretum-matrix` / `$decretum-matrix`，最终授权安装根中的 canonical 物理目录统一为 `skills/decretum-matrix`。`court-capability-router` 可继续作为仓库 id、历史/恢复路径及 shared Shiguan runtime data namespace；旧 `skills/court-capability-router` 只可作为明确标注 deprecated、解析到同一物理 authority 的 compatibility locator/junction/router，不能成为第二 authority 或第二副本。旧 `$court-capability-router` 只可作为明确标注 deprecated 的兼容输入；撤回草案 `DecreeMatri` 不得出现在当前身份面。若宿主没有可证明的 alias 机制，宁可报告不支持，也不得复制第二份权威 skill。最终 manifest 必须固定 `display_name`、`canonical_skill_name`、`legacy_names`、`locator_policy`，所有用户可见文档、官籍、profile/dossier、包元数据、安装收据、史馆/Obsidian 标题与 loader probe 一致；历史日志、技术路径和兼容说明中的旧名按 allowlist 保留，禁止盲目全局替换。
52. 史馆 CLI 必须以一个主诏令编号、冻结 lineage、幂等 `operation_id` 和可恢复 compound receipt 解决多对话/child/worktree 编号与谱系一致性。它复用现有 `tasks.json + court_events.jsonl + archive/index` 权威链，不改历史 `court_code`，不创建每-worktree ledger；通用 office lifecycle、三段 closeout saga、local authority-root fingerprint 和 exactly-once killpoint 验收按 §0.3 与 RC2/RC4/RC6 既有 cluster 顺位执行。
53. 项目记忆与官署名称不得互相冒充权威：root project-memory 内容当前有效但 global index 尚待摄取；后续通过一个 append-only superseding note 修 current pointers。新官署使用 role-prefixed immutable task name，只在同 role 复用；最终 readiness 只认 ordinary dossier/profile/SKILL hash 与 preload ack。该整改并入 RC3/RC4/RC5 和 Phase 8 follow-up，不另建 cluster。

### 1.0.1 CC Switch 3.16/3.17 与有效配置验收硬契约

- 合法组合仅为 `CC Switch 3.16.x + SQLite user_version=11`，或 `CC Switch 3.17.x + SQLite user_version=13` 且 `profiles` 恰有 `id/name/payload/sort_order/created_at/updated_at` 六列、`proxy_request_logs` 与 `usage_daily_rollups` 均存在并满足已验证的 `input_token_semantics`。版本/schema 错配、未知版本或未知 schema 一律 fail closed，不修改、不声称合规。
- `settings.current_profile_id_<scope>` 是按需行；缺失不代表迁移失败。SQLite migration 只能由 CC Switch 自身完成，适配器不得创建、升级或修补 schema。`tool_blocks` 只可标为 `synthetic JSON fixture`，不得描述为真实 CC Switch SQLite。
- 最终裁定前最后一刻，逐一 reread/parse 本轮每个实际配置 target 的有效语义；controller/DB 收据或较早快照不能替代。Codex 的 `config.toml` 与 `managed_config.toml` 各自满足同一批准 delta 的等价/兼容语义即可，不要求两文件永久全字节相等。
- Hermes v3.17 路径顺位为显式 CC Switch `hermes_config_dir` override > 非空 `HERMES_HOME` > 平台默认目录，最后拼 `config.yaml`。Windows 默认 `%LOCALAPPDATA%\hermes`，缺失时 `<home>\AppData\Local\hermes`；Darwin/Linux 默认 `~/.hermes`。
- 本机 `features.multi_agent_v2.max_concurrent_threads_per_session` 当前尚未证明为 `16`，只作为真实未满足项保留；本波不得声称已修，除非后续获明确配置变更授权并由最后一刻 native reread 证明。

## 1.1 🟨 高亮待确认提案

> **🟨 提案 A：官署角色可扩容，太子唯一**
>
> **审查裁定：`APPROVE_WITH_REFINEMENT / ACTIVE`**
>
> **核心语义：官署角色不是单例；每个 agente 实例必须有唯一身份；太子始终单例。**
>
> - `taizi` 是唯一用户侧主线程、唯一朱批/回奏入口，禁止多开。
> - 每个官署保留一个 canonical authority/统合锚点；同一 `role_key` 可按独立任务分片创建多个 `office_worker_instance`。
> - 六部同官署 worker 扩容亲和度和优先度最高。例如多个工部实例可分别拥有互不重叠的代码模块、测试集或验证目标。
> - 中书省、门下省允许按独立研究源、方案支线或审查维度多开，但默认优先度较低；正式奏议仍由该省 canonical authority 统一签发。
> - 尚书省多开优先度极低。仅 `super_giant_task_gate=PASSED`、存在多个独立六部组合域时允许 portfolio deputy；`shangshu#0001` 始终是唯一全局派遣和最终统合者。
> - superCC 每个 role 的 canonical pane/`squad` identity 仍唯一；额外实例默认是 non-visible ordinary workers，不得伪装成第二 canonical 官署。
> - 同 role 不再因重复本身被拒绝；重复 `instance_key`、重复 task/shard、重叠写集、无统合者或无法归属证据仍必须拒绝。

极具复杂超巨型项目的判定包含但不限于以下相似场景：

- 小型、中型或大型游戏的完整开发与设计，包含多个可独立推进的系统、内容、美术、交互、测试或发布域。
- 批量处理对象超过 10 这个数量级，并且对象可按文件、模块、批次或验证目标独立分片。
- 极其复杂的资讯收集、交叉核验和判断任务，同时需要处理的独立信息项、来源或判断单元超过 30 这个数量级。
- 其他具有多个独立 orchestration domains、明显并行关键路径和足够证据价值的任务。

太子在判定 `super_giant_task_gate=PASSED` 后，必须对线程、六部/工匠实例、token、时间、文件写集、验证与恢复槽位形成明显且可解释的预算认知。预算不是固定开满，而是按独立 domain/shard 与关键路径分配。

额外降级条件：

1. **规模降级**：后续剩余任务已不再达到超巨型规模，立即停止新增尚书 deputy 和高密度 worker，回收已完成实例，恢复一个 canonical 尚书与必要六部 lanes。
2. **性能降级**：宿主留存性能不足以支撑当前拓扑时立即降级，包括但不限于系统运行内存接近 99% 占用、线程槽位/retained nodes 压力、明显交换/卡顿、请求预算不足或运行时无法证明安全余量。
3. 降级必须保存时间—事件—行为简记和证据，不丢失 task/shard 所有权；先停止扩容、再释放非必要实例、最后以较小并行度或串行单写者继续。

调度亲和度：

| 类别 | 同 role 扩容优先度 | 约束 |
|---|---:|---|
| 六部 / 工坊 / 工匠 | 最高 | 独立分片、写集不重叠、各自验收 |
| 中书省 / 门下省 | 较低 | 仅独立研究或复核维度；统一形成正式奏议 |
| 史馆只读采集实例 | 低 | 可分证据源；最终记录保持单一追加顺位 |
| 尚书省 | 极低 | 仅超级巨型任务；一个 chief、多个限域 deputy |
| 太子 | 禁止 | 全朝唯一用户侧主线程 |

每个实例的最小身份字段：

```text
role_key
canonical_role_id
office_instance_id
instance_key=<role_key>#<NNNN>
office_instance_kind
task_id
semantic_epoch=charter_revision
charter_sha256
invariant_capsule_sha256
authority_revision/sha256
plan_revision/sha256/cursor
dispatch_uid
shard_id
attempt
result_binding_verdict
git_fingerprint/recovery_checkpoint_id/event_head_sha256
direct_superior
owned_paths/write_set
dossier/profile/SKILL hashes
preload_ack
evidence_pointer
heartbeat/release_state
```

> **🟨 提案 B：史馆主动维护当前宿主 agent 的记忆投影**
>
> **审查裁定：`APPROVED / ACTIVE`**
>
> **核心语义：史馆主动识别、去重、校正和提出长期记忆候选；不得静默直接重写宿主 `MEMORY.md`。**
>
> - 三层必须正交：`semantic_adjudication` 形成门下 `APPROVE|REJECT|DEFER|SUPERSEDE`；`write_authority` 证明最新用户写回/target 授权；`native_application` 执行 adapter apply、native reread 与 paired Git receipt。Git commit、Obsidian 投影、native approval queue 或文件存在均不是门下裁定。
> - 保留 `memory_decision=WRITE|PROPOSE|SKIP|DEFERRED`，并同时记录 `adjudication_status`、`application_status`、`conflict_status`、`resolution`、`content_origin`、`decision_id`、`menxia_receipt`、`transaction_id`。只有 `adjudication_status=approved` 时 `WRITE` 才合法。
> - 历史裁定不得原地改写；纠正必须追加带 `supersedes` 的新 decision。当前工具仍需最新记忆写回授权和门下批准；非当前工具默认只索引/Git 托管/pinned link，正文写回另需最新明确 target authorization。
> - 权威顺位保持：最新旨意与 `SKILL.md`/governing references > 史馆证据 > 宿主记忆投影。
> - 史馆实录与长期记忆在迁移后的同一共享 Git 仓库/Obsidian vault 中分层托管：实录是追加式事实证据，长期记忆是可经裁定演进的当前知识；二者以 `derived_from_record`、`evidence_refs` 和 Git commit 相互追溯，但不得共用同一 schema 或把记忆更新伪装成历史实录改写。
> - 共享 Git 仓库就是单一 `.agents` 史馆物理根的版本控制层，不是第二数据库/第二 store；默认 local-only、无 remote。只提交 allowlist 中通过隐私门禁的正式实录、记忆候选/裁定、共享批准记忆、per-tool projection、manifest 与 Obsidian 派生树；pending、runtime、raw/private body、SQLite、凭据、配置 preimage 和包必须 ignored/untracked。
> - 史馆可主动发现稳定规则、冲突和过期记忆，默认形成 `PROPOSE`；只有最新用户旨意明确授权且门下批准时才可 `WRITE`。
> - 长期记忆候选、writeback 和 update-note 默认只维护当前工具。本机当前工具是 Codex；Claude、Hermes 和其他工具除已明确要求的原地 Git 托管与 pinned managed block 外，继续禁止安装、配置、启用或正文写回。
> - install projection/manifest 必须由运行态/环境/controller-aware 探测生成：运行进程/CLI -> tool-home 环境变量 -> CC Switch profile/block/path override -> 实际有效配置/loader -> skill root/version/hash -> runtime probe。状态只允许 `active_verified|installed_verified|detected_unverified|not_installed_verified|unknown`；DB 或目录存在不能单独证明安装。
> - 与 writeback 分离的 Obsidian 只读 index projection 覆盖 `active_verified|installed_verified` 工具类：`codex`、`hermes`、`claude-code`、稳定 `other:<id>`。每个已验证安装工具都必须有隔离 namespace 和独立 graph；原生记忆为空时保留空 namespace 与准确 state，不伪造内容。`detected_unverified|unknown` 只展示证据，任何跨工具 node/edge conflation 都失败。
> - 工具集合不是封闭三元组。每个已验证安装工具的原生记忆库保留官方/实际 loader 路径，并以独立 Git 仓库由史馆原地托管：复用已有 owning repo，或在兼容性证明后原位初始化/使用 separate git-dir + 原生 work tree。不得搬入共享史馆、做 submodule/subtree 或复制正文到共享史馆；新仓库无 remote，既有 tool-owned remote 原样保留但史馆不得新增、修改或使用。史馆 Git 只登记 repo/pathspec/HEAD/write-policy/link receipt，并排除 native git-dir/object history。
> - 迁移必须建立双向导航：每个已验证安装工具的 canonical memory entrypoint 顶部放置受 begin/end marker 管理的史馆首页和本工具 namespace 链接；史馆 namespace 记录原生 memory source、source Git HEAD/hash 和回链。实现只可替换该 managed block 并保持其余字节/换行/正文不变；若工具不允许安全置顶，则创建受支持的 `00-SHIGUAN.md`/等价 pinned entry，仍无法证明时 fail closed 为 `LINK_BINDING_BLOCKED`。
> - 投影只记录相对 source id/path、repository HEAD/hash 或 live-prefix fingerprint、memory state、headings/topics/relations。源 MEMORY/memories 保持工具侧权威；除置顶 managed block、工具自身写入和另行批准的 current-tool update-note 外，史馆不改正文。private raw bodies 和 release packages 均不进入投影或便携包；body mirroring 另需后续明确旨意与门下隐私复核。
> - Codex 无直接记忆写入接口时，只允许 create-only 写一份小型 update note 到 `.codex/memories/extensions/ad_hoc/notes/<timestamp>-<slug>.md`；禁止直接 patch、截断、覆盖或删除 `MEMORY.md`。
> - note 创建只能报告 `NOTE_CREATED_PENDING_INGESTION`；后续只读回查确认后才能报告 `APPLIED_VERIFIED`。
> - 不复制 pending bodies、原始 transcript、私有日志、凭据或整份宿主记忆正文；不新增后台轮询服务。

> **🟨 提案 C：“不要过度复杂化”改为太子预算裁量**
>
> **审查裁定：`APPROVE / ACTIVE`**
>
> **核心语义：默认最小化，但不把复杂度本身当作罪名。**
>
> - 用户最新明确说明优先：用户明确要求简单/最小则收紧，明确允许或要求充分复杂度则在安全硬门禁内放宽。
> - 用户没有明确说明时，才由太子结合三省意见和当前预算作裁量。
> - 中书省说明新增复杂度关闭了什么问题及预期价值。
> - 门下省判断是否存在更简单等价方案、风险和范围漂移。
> - 尚书省核算线程、时间、token、文件、测试和维护预算。
> - 太子不得覆盖用户已明确的复杂度边界；只对未明确部分作预算裁量。必要复杂度可批准，低价值打磨仍拒绝。
> - 结果枚举：`MINIMAL_PASS`、`NECESSARY_COMPLEXITY_APPROVED`、`LOW_VALUE_REJECTED`、`BUDGET_DEFERRED`。
> - 该裁量不能绕过安全、隐私、用户边界、空 index、pending-body 或其他硬门禁。

> **🟨 提案 D：每个子官署保留轻量追溯记录**
>
> **审查裁定：`APPROVE / ACTIVE`**
>
> **核心语义：不保存子官署全量内容，但每个实例至少留下时间、事件和行为简记。**
>
> - 复用现有 append-only runtime/agent lifecycle ledger，不新建数据库或每实例独立档案。
> - 每个实例至少记录 `spawn/start`、关键行为、`finish/fail`、`close/release`。
> - 最小字段：UTC 时间、task/dispatch/instance id、role、direct superior、事件、行为摘要、状态、证据指针/hash、下一步或释放原因。
> - 史馆最终 checkpoint 只汇总这些轻量事件和 ledger anchor，不复制 prompt、完整报告、原始日志或私密正文。
> - 同 role 多实例必须逐实例归属证据，不得只写“工部已完成”。

## 2. 当前前像与已发现漂移

```text
old Shiguan root: C:\Users\32893\AppData\Local\court-shiguan\court-capability-router\references
snapshot UTC: 2026-07-14T04:37:15.0409984Z
old root files: 18124
old root bytes: 213919596
old root newest mtime UTC: 2026-07-14T04:36:46.4789485Z
new .agents Shiguan references root: absent
pending real bodies: 69 files / 1129975 bytes / 69 unknown metadata
installed roots: .agents/.codex/.claude/.hermes/AppData-Hermes all beta0.5.12
rejected beta0.5.13 run1/run2 SHA256: 8F9A4C3DCD3966B47962638C2181AA8D650E3D1A9AF930B0AED1997E77683321
Git index: empty
```

四个保护文件当前基线：

| 相对路径 | 长度 | SHA256 |
|---|---:|---|
| `references/shiguan-index.jsonl` | 0 | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |
| `references/shiguan-knowledge-graph.json` | 338 | `2F0454EEC5355FB502624FB3658C477386DA668920836FD0E33FF9AD47EC4922` |
| `references/shiguan-tree/_index.md` | 268 | `CE5671B2DA87093F9B0D6A17D030BE39C5A0632DB98CFF6D3A0671A671FB4169` |
| `references/shiguan-tree/capability-index/_index.md` | 517 | `01BC65DF443E52103FC08B86DE8F5250B8630E13DDE4B3B6C5B5DC7ED09AEF7A` |

必须保留的发布工件基线：

| 相对路径组 | 长度 | SHA256 |
|---|---:|---|
| `release-packages/.../beta0.5.12/run1`、`run2` | 3575787 | `9482DB5231E37808DD88959A324FABBF62EF91A1A1BF4A19DF241F17B7A75C46` |
| `release-packages/.../beta0.5.12/run1b`、`run2b` | 3575790 | `8CE70CD7AE51D3F774DB69167273A9139A96483A2DF7E3E80358162399D6CBCB` |
| `release-packages/.../beta0.5.13/run1`、`run2` | 3580814 | `8F9A4C3DCD3966B47962638C2181AA8D650E3D1A9AF930B0AED1997E77683321` |

此前三省六部整改的当前判定是 `PARTIAL`，不能只凭旧验收记录视为仍然全绿：

- 14 个 standing TOML 和 14 个 dossier 均存在。
- A01 的 name/profile/skill 三证明实现与检查器仍存在。
- `libu-hr.toml` 后续变化导致其 dossier 中的 profile hash 已陈旧。
- 13 个官署 profile 仍含旧 `%LOCALAPPDATA%` 共享史馆说明。
- `court_office_bootstrap.py` 仍持久返回绝对 profile/dossier/SKILL 路径。
- 当前固定五根同步逻辑仍默认包含 Claude/Hermes。
- 新建 runtime task 未初始化 `charter_revision` / `charter_sha256`，导致纠正/恢复链不能直接使用既有 audited revision API。
- 当前 child identity 规则虽在 skill/A01 中存在，但本轮要把“实际加载 exact AGENTS.md”变成初载和运行硬门禁，消除 prompt-only 漂移。
- 当前 pending 队列有 69 份真实正文，且 69 份均无可信 metadata sidecar。现行治理禁止打开、读取、哈希、移动、删除或 mark-seen；因此迁移切换当前是已知硬停止点，不得以整根复制或目录改名绕过。
- 当前 `court_dispatch_policy.py` 明确拒绝 duplicate roles，superCC 又实行 role-wide canonical uniqueness；提案 A 已获批，必须改成“canonical authority 唯一 + worker instance 可扩容”，不能只改文案。
- 当前史馆记忆桥只做 metadata bridge，且史馆只能提出候选；提案 B 已批准并处于 ACTIVE，但其当前工具 update-note、门下语义裁定和 native application 闭环尚未实现。
- 当前 `scope_value_gate` 表述过于二元，缺少太子按任务预算批准必要复杂度的裁量结果。
- agent lifecycle 已有基础账本，但“每个子官署轻量事件必须进入最终史馆追溯链”尚未成为明确验收门禁。

## 3. 执行总顺位

```text
确认执行书
-> P00 Token Economy Guard：复用 Semantic Continuity Guard 的最小派发/恢复合同
-> P05-TB01 太子预启动资源预算评估与批准
-> A02 Phase 1 RED（已启动并形成双层恢复点）
-> 2026-07-15 临时暂停：Phase 8 根控制仓库/子仓库 GitHub-ready 恢复门禁
-> 从 20260715-175826 恢复点继续并完成 A02 RED
-> pending-body 元数据门禁
-> 活跃会话/记录静默门禁
-> 史馆物理迁移与 junction 切换
-> 迁移 GREEN
-> Obsidian 与 shared-root 语义
-> 当前工具安装投影 + 全官署加载语义 + 恢复/纠正语义
-> controller-first 空白宿主配置检查/获授权纠正
-> 已批准提案 A-D 与 V2 记忆裁定的 RED/GREEN
-> README/docs/logs/manifest
-> 统一无损 updater + 本地 npm `.tgz` 跨平台验证（不发布）
-> beta0.5.13 run1b/run2b
-> 本机 .agents + Codex 安装
-> SPEC
-> QUALITY
-> A-G 专项并行只读审查 + 门下唯一汇总裁定
-> accepted repair clusters 的 RED/GREEN/SPEC/QUALITY 与全局回归
-> 全仓只读审查；必要时独立 child worktree 本地整改提交
-> 按 §3.1 在 court 子仓完成本 major stage 的本地 commit 与 clean-worktree 包验证
-> 从最终已验收子仓 commit 的 clean worktree 重建并复验最终 run1b/run2b 包
-> §3.2 取得上一已完成版本上传终态；§3.3 创建下一 release child worktree 并自动交接到新本地 Codex 任务
-> 完成本机史馆系统最新版迁移/重构与 `SHIGUAN_LATEST_SYSTEM_GATE`
-> 将同一最终包同步安装到固定五根并验证逐文件哈希一致
-> 整体验收/史馆完整结诏
-> 恢复父计划 Task 3 GREEN
```

### 3.1 Major-stage 子仓 release 分支循环门禁

本执行书中阶段循环所称“分支”，只指独立 `decretum-matrix` 子仓的 `release/beta0.5.x` 分支及其当期 child worktree；不得为产品阶段创建根治理仓 release 分支。旧 `court-capability-router` 仅可保留为受保护 ZIP/install/Shiguan/history locator。根治理仓只镜像阶段、子仓 ref、commit、worktree 与本地包 receipt/hash 等台账元数据，不纳入子仓文件、历史或产物。

以下五项才是 major stage，不得把单个 micro RED、checker 或 repair cluster 各自升级成版本循环：

1. Phase 1：P00 与 RC2/RC4/RC5/RC6 的阶段聚合 RED/GREEN/SPEC/QUALITY；
2. Phase 1.5：tasks-ledger durability；
3. Shiguan migration；
4. Obsidian + install + updater；
5. final audit + package。

每个 major stage 严格执行同一闭环：当前工作分支记为 `release/beta0.5.x`，唯一写入面是 Decretum Matrix 独立 child repository 的当期 linked worktree `D:\project\decretum-matrix-beta0.5.x`；阶段 RED/GREEN/SPEC/QUALITY 与必要全局回归全部通过 -> 仅在该当期版本工作树对已批准 pathspec 做一次有界暂存事务并创建本地 commit -> 立即复核真实 index 为 `0` -> 从该精确 commit 创建 clean child worktree，仅由该 clean worktree执行 `TAGLESS_CANDIDATE_GATE`，在 `<release-staging>/<name>/<version>/<full-head>/` create-only 生成或精确复用 ZIP/sidecar/candidate receipt/release notes/SBOM -> `CANDIDATE_REUSE_GATE` 证明 receipt、commit、tree、manifest 与 ZIP 字节一致且不生成 attestation -> 安装并验证同一候选包，记录 commit/branch/worktree/package hash/install receipt -> 按 §3.2 对 `release/beta0.5.(x-1)` 取得 `UPLOADED` 或明确 `NOT_AUTHORIZED|NOT_RUN|BLOCKED` 终态 -> 从已验收 `x` commit 创建下一顺位 `release/beta0.5.(x+1)` 分支及受控 mapped worktree `D:\project\decretum-matrix-beta0.5.(x+1)` -> 按 §3.3 自动交接 -> 后续 major stage 只在新任务与新 release worktree 继续。只有上述闭环取得真实终态后，才在任务状态和 governing plan 游标中标记该 major stage `COMPLETED`，并绑定 commit、包 SHA-256、安装与上传回执；未执行项保持 `PENDING|NOT_RUN`。阶段无文件变化时以当前已验收 HEAD 作为 stage commit，禁止空提交。分支或 worktree 已存在且绑定不一致时 fail closed，禁止 force/reset/覆盖。

每个 gate 与每项 Git/包操作开始、结束均要求 `git diff --cached --name-only` 计数为 `0`。commit 窗口是唯一例外：只可暂存门下已批准的精确 pathspec，commit 前必须证明 cached set 与批准集合完全一致；commit 后立即复核 index 为 `0`。集合不符或 commit 失败时停止并只回滚该有界事务，禁止夹带、清理或暂存其他 dirty path。

clean package worktree 必须固定到刚验收的 commit，且无 tracked/untracked 构建输入漂移。既有 beta0.5.12 与 beta0.5.13 的 run1/run2 保持原路径、原字节、原哈希；对应新产物只使用 run1b/run2b 或唯一 no-clobber 后缀，并保存外置哈希。major-stage 的当前 `x` commit/package/install 必须先闭环；随后按 §3.2 处理上一完成版本 `x-1` 的上传终态，最后才创建并切入 `x+1` 分支与版本工作树。不得在 `x` 尚未验收时提前建 `x+1`，也不得把根控制仓纳入上传。

`ANNOTATED_FINAL_TAG_GATE` 与 `BYTE_IDENTICAL_PROMOTION_GATE` 独立于 tagless candidate：只有另获 tag 授权、annotated tag 精确指向 accepted commit，且 final ZIP SHA-256 等于已验收 candidate 时，才可生成 final release directory 与 release attestation；candidate receipt、manifest 的 `expected_final_tag` 或本地候选目录均不得冒充 tag 已存在。最终 builder 在实现并验收 `--candidate-dir` 或 `--expected-candidate-sha256` 前，`BYTE_IDENTICAL_PROMOTION_GATE=BLOCKED`：不得先创建 final 目录再比较，也不得仅凭重新构建的“应当相同”结论发布。

#### 3.1A 首次候选包快速路径（后续版本复用）

为避免在 dirty tree、陈旧 manifest 或错误阶段反复执行昂贵的完整打包，首次打包及后续每个版本必须复用以下固定顺序；任何步骤首错未绿前不得提前重复后续步骤：

1. 主线先冻结当期 `release/beta0.5.x` write set，确认 pending body access=`NO`、root/child index=`0`、无第二 mainline writer；互斥的法律、来源、预算和方案审查可用既有只读官署并行。
2. 在 dirty 主线只跑 source-level 首错检查；`release-manifest.json` 陈旧时先修源码/清单，不运行真实 candidate build，不运行 full gate。
3. payload write set 稳定后运行一次 `release_payload_manifest.py --write` 供自测；若存在新文件，优先用一次性 `GIT_INDEX_FILE` 执行 `git read-tree HEAD` 并只暂存该获准新文件，在不污染真实 index 的情况下生成最终 tracked preimage manifest。commit 窗口仍须用真实批准 pathspec 再复核一次 manifest 与 staged set。禁止在提交后才发现 untracked/tracked 分类漂移。
4. 依次通过 release manifest、source budget、legal/provenance、package privacy、source catalog/required-script 完整性、阶段 SPEC/QUALITY 与 `git diff --check`；dirty 主线不重复运行 deterministic builder self-test，后者只由 clean package worktree 的第 8 步/pre-install gate 执行一次。`check_catalog.py --strict` 若唯一失败为已安装 profile 尚缺新版本 access term，可精确记录为 `DEFERRED_TO_POST_INSTALL` 而不阻断 commit；任何 source catalog 缺项仍阻断。只保留首个失败及其 bounded repair cluster，禁止重复跑已知会失败的全量 gate。
5. 创建当期唯一有界 child commit，立即恢复 index=`0`；记录 branch、commit、tree、approved pathspec 和测试 receipt。无内容变化时复用已验收 HEAD，不建空提交。
6. 复用现有 clean detached package worktree；只将它移动到刚验收 commit，不创建第二 mainline writer。确认 clean tracked/untracked 状态后运行 `build_release_artifacts.py --mode candidate --json`。
7. candidate 固定写入 `<release-staging>/decretum-matrix/<version>/<full-head>/`；receipt 完全匹配时直接 `reused=true`，不重建、不覆盖。无 annotated tag 时不得生成 release attestation 或冒充正式 release。
8. 对该唯一 ZIP 运行 `check_release_gate.py --phase pre-install --package <zip> --require-package --json`；该 gate 是本轮 deterministic builder self-test 的唯一执行面。失败时回到对应 source/package 首错，禁止换包绕过。
9. 工部安装线程只安装该已验 SHA-256 的 ZIP到批准的 `.agents + current tool` 投影；随后由独立迁移/索引线程处理兼容数据并回读。三者必须引用同一 package hash，pending body 继续保持零访问。
10. 对同一 ZIP 运行 `--phase post-install`，并要求 `check_catalog.py --strict` 的 installed-profile access term 漂移转绿；记录 host projection、active-copy hash、迁移/index 与必要 runtime 结果，未运行项必须明确 `NOT_RUN|NOT_APPLICABLE|BLOCKED`。完成等式必须机械成立：从 `candidate_receipt.artifacts[]` 按 canonical `artifact_name` 精确选择的 `sha256 == pre_install.package_gate.sha256 == install_receipt.source_package_sha256 == post_install.package_gate.sha256`；安装 receipt 的 `source_package_sha256` 为必填，任一缺失或不等即阻断上传和完成标记，禁止通过重打包“修复”等式。
11. 当前 `x` 闭环后，仅按 §3.2 上传已完成的 `x-1`；取得上传终态后，从 `x` accepted commit 创建 `x+1` 分支与 `D:\project\decretum-matrix-beta0.5.(x+1)` 受控工作树。
12. 只有 commit、candidate、安装、上传终态和下一版本 mapping 都有真实 receipt 后，才在任务及 governing plan 标记阶段完成。recovery checkpoint 至少绑定 plan cursor/hash、开发与 package worktree path/common-dir/HEAD、最终 manifest SHA/payload-index、candidate dir/receipt SHA/ZIP SHA、pre/install/post receipt 路径与 hash、`x-1` upload outcome/authorized actions、`x+1` mapping state/event hashes、index=`0` 和 pending access=`NO`，使下一任务只预载 compact receipt 而不重放全历史。

#### 3.1B 子官署 Profile 与语义胶囊合同

所有 spawned、reused 或 follow-up 子官署均必须在办差前加载并确认：

- `role_key`、`direct_superior`、精确 `agents/office-dossiers/<role>/AGENTS.md`
  与 `agents/standing-officials/<role>.toml` 路径/hash；
- 当前 `SKILL.md` 路径/hash、模型路由 id 与
  `model_override_applied=NO`/继承策略；
- 有界语义胶囊：decree/task id、plan cursor/hash、真实 semantic epoch/charter/
  invariant capsule/checkpoint（若生产 runtime 已签发）；未签发时只能标记
  `controller_bounded_capsule`，不得伪造 production checkpoint；
- 当前不变量、允许 write/read scope、pending/secret/remote/index 门禁、停止条件、
  证据合同和 compact result envelope。

胶囊只携带本原子任务必需字段与指针，不复制全计划、全历史或 pending body，默认
`fork_turns=none`。子官署必须在首个回执中确认 profile/dossier/SKILL/capsule hash
后才可执行；任一 hash、semantic epoch、branch/worktree 或 write lease 漂移即停止并
重新加载。优先复用已有线程，但只允许复用同一 role、无未决状态且 profile/capsule
仍匹配的线程；不得为节省启动时间绕过身份或语义连续性门禁。

### 3.2 PREVIOUS_VERSION_GITHUB_UPLOAD_GATE 与 OSS-GOV 证据

当前 major stage 工作分支为 `release/beta0.5.x` 时，只有其 commit/package 已验收后，自动化才可把紧邻上一已完成版本 `release/beta0.5.(x-1)` 作为唯一上传候选。不得上传本轮刚完成、仍承担当前交接源的 `x`，不得跳级选择更早/其他版本，绝不得为 `D:\project` 根治理仓配置或执行上传。上传取得终态后才返回 §3.1 创建 `x+1`。

上传判定必须来自独立 clean `OSS-GOV` child worktree，例如 `D:\project\worktrees\decretum-matrix\oss-gov-beta0.5.(x-1)`。该 worktree 只连接 Decretum Matrix 子仓 common-dir、固定到上一版本精确 commit，index 为 `0`，无 dirty/untracked 构建输入；其 evidence 必须记录 worktree path/common-dir/ref/commit、验证命令与结果、package/manifest SHA-256，且不得复用当前开发 worktree 的未提交状态。

`PREVIOUS_VERSION_GITHUB_UPLOAD_GATE=PASS` 至少要求：Apache-2.0 或用户明确批准且与仓库文件一致的许可证；面向 GitHub 的中英双语 README/homepage；中英双语 CHANGELOG 与该版本 release notes；commit、包、manifest/hash、隐私/安全扫描和全部规定测试均 clean/pass；目标确为 Court 子仓且 remote fetch/push URL、目标 upstream/branch 均正确；以及一份显式上一版本 receipt，把候选/后继版本与 ref、commit、包/hash、安全/测试/文档/许可证证据、remote/upstream 和本次 `authorized_actions` 精确绑定。任一缺失即 fail closed。

receipt 未逐项授权的动作一律禁止。`push`、`tag`、`PR`、GitHub `release` 与资产上传分别裁定，不得由其中一项推定另一项；不得新增/修改 remote 或 upstream 来绕过门禁。当前 Decretum Matrix 子仓本地 `remote_count=0`，线上 `RowlandL/decretum-matrix` 已初始化为空仓；只有上一版本上传 gate 与对应授权动作同时通过后才可受检添加 canonical remote。本轮未到上传顺位时保持 `GITHUB_UPLOAD=NOT_RUN`。

### 3.3 MAJOR_STAGE_AUTO_HANDOFF_GATE

每个 future major-stage loop 都必须自动交接，但不得在当前已派发 subtasks/官署/lane 尚有 `running|pending|unreconciled` 状态、有效 write lease 或未回收结果时开始。先收齐并核对全部 terminal receipts；本轮计划更新不创建任务、分支或 worktree。

上传门禁已有终态后，使用 root `repo-control` 或同等 manifest-safe 操作，从当前已验收 commit 创建唯一下一顺位 Decretum Matrix child `release/beta0.5.(x+1)` worktree。随后同步 `.repo-control/state/decretum-matrix/<task-id>.json` 与 immutable events/root ref-only mapping；旧 `court-capability-router` state/events/refs 只作 append-only 历史 locator，不删除、不重写。根治理仓只同步映射元数据，不 checkout 子历史、不创建新的 mainline Codex worktree，也不复制或重建已经存在的 child worktree。

映射成功后，在同一个 `D:\project` Codex 项目下创建一个**新的本地任务**，可见标题精确使用 `codex/decretum-matrix/release/beta0.5.(x+1)`。该任务不是新的根 mainline worktree；它通过 root mapping/`attached/decretum-matrix` 指向刚创建且已经存在的 child release worktree。禁止两个任务同时持有同一 branch/write lease。

新任务首包只携带 compact handoff：诏令/任务编号、已完成 major stage、child branch/worktree/common-dir/commit、包与计划 hash、semantic receipt/plan cursor、上传终态、未决风险和下一原子动作；全量日志留在 `.repo-control/events/decretum-matrix/<old-task-id>/`，旧 namespace 日志保持原位并以 `full_log_path` 指针提供，不复制进上下文或共享 `tasks.json`。

新任务必须回传 `MAJOR_STAGE_HANDOFF_ACCEPTED` receipt，至少绑定新旧 task id、可见标题、root project、child path/common-dir/branch/HEAD、index=`0`、root mapping state/event hashes、compact-handoff hash、full-log path、plan cursor/hash 和 upload outcome。receipt 验证通过后才关闭旧任务；验证失败时旧任务保持 open/paused，新任务不得写入，禁止双 writer 或丢失恢复锚点。

当前已在 `release/beta0.5.10` 与 `D:\project\decretum-matrix-beta0.5.10`；首次后续交接目标因此是 `codex/decretum-matrix/release/beta0.5.11`。执行时必须从 beta0.5.10 accepted commit 创建并验证 `release/beta0.5.11`、`D:\project\decretum-matrix-beta0.5.11`、common-dir=`D:\project\decretum-matrix\.git` 和 index=`0`；不得另建第二 writer、覆盖既有不匹配 worktree 或回退旧产品 namespace。

## 4. 阶段计划

### Phase 0 — 确认门禁

- 用户明确确认本执行书后才进入 RED。
- 再核验 worktree、计划哈希、空 index、保护文件和版本工件前像。
- 将本轮后续消息绑定原 task/goal，不新建第二任务。

### Phase 0.1 — P00 Token Economy Guard（最高优先级）

**顺位/状态：`HIGHEST_PRIORITY / PLANNED_RED`。** 本门禁固定在 Phase 0 之后、P05-TB01、Phase 1 和任何后续新 agent/新 wave/新派发之前；`P00_TOKEN_ECONOMY_GATE=PASSED` 前不得启动新的 child。已在途且持有有效 lease 的 agent 不盲目中断，可完成当前有价值的原子工作；其下一次 follow-up、retry、redispatch 或新 assignment 立即适用 P00。

P00 不是新协议。低 token 派发与 compaction/resume 防丢失是既有 **Semantic Continuity Guard** 的两种消费方式，必须复用同一 `invariant_capsule_sha256`、`semantic_epoch == charter_revision`、authority path/hash/revision、plan path/hash/revision/cursor 和 semantic receipt。禁止第二胶囊、第二权威、第二 receipt authority、第二 ledger 或第二状态机。

- 默认 dispatch 仅携带 `task_id/sub_id`、现有 `<=2 KiB` runtime inline invariant capsule、精确 authority path/hash、plan path/hash/cursor、当前 semantic receipt、最小角色/直属上级/lease/write-set/worktree/preload hash 绑定和证据指针。`super并行` 只改变并行拓扑，不等于向每个 child 复制全文。
- 默认 `fork_turns=none`，并使用最小上下文：最小官署 preload、registry-first 命中、`reuse-compatible-instance-first`、P05 层级预算 lease、`child_agent|worktree_thread` 同一 receipt、未显式启用 superCC 时其 annex/dossier/profile/scripts/daemon `zero-load`，以及 bounded child trace。只有缺失、漂移或行为触发时才读取精确 authority 文件或 governing reference。
- child 默认只回 bounded JSON receipt：`verdict`、`first_error`、changed/verified paths 与 hashes、semantic/capsule/cursor 绑定和本地 evidence/log pointer。完整日志、完整 diff 和大输出留在本地，不塞回父线程。
- 默认禁止全量 `list_agents`、full diff、full file 和无界日志回传；仅在哈希漂移、证据歧义、故障定位确需或用户/太子依据已记录预算明确放宽时，才对命中的最小范围升级读取。放宽必须记录 source、scope、budget、reason 和 expiry。
- compaction/resume 只核对 capsule/semantic receipt、plan cursor、authority hashes 和 changed-path hashes；哈希未变时不全读文件，任一相关哈希/epoch/cursor 变化才精确重读对应来源并重新 verify。不得用 MEMORY、摘要或旧上下文替代当前 receipt。
- Phase 1 只使用现有 runtime inline capsule，不写真实史馆。真实 Shiguan task-point 持久化仍严格留在史馆迁移与 shared-root 验收后的 Phase 4，并复用同一 binding；P00 不改变先迁移史馆顺位。

**RED：** 先证明以下行为失败：默认复制全文或使用 `fork_turns=all`；capsule 超过 `2 KiB`；缺少 task/sub-id、authority hash、plan cursor 或 semantic receipt；默认执行 full `list_agents`/diff/file；hash 未变仍全量重载或 hash 已变却跳过重载；child/worktree 使用不同 receipt；未启用 superCC 仍加载其表面；绕过 registry/reuse/budget/trace 门禁；或建立第二 capsule/authority/state machine。当前 `court.agent.dispatch_message_budget.v1` 的 `6000` floor / `12000` ceiling 会把大消息当正常兼容面，必须作为明确 RED 漂移点，不能作为 P00 GREEN 证据。

**GREEN：** 在既有 Semantic Continuity core 上实现一个默认 bounded dispatch/context packet 和 bounded result receipt；把 P00 收紧落到生产 dispatch/admission/message-budget 路径，保持 O(1) unchanged-hash resume，并让显式用户/太子预算 override 只放宽当前 packet，不绕过安全、层级或 semantic binding。

**SPEC：** P00 只统一既有 `fork_turns=none`、registry-first、2 KiB capsule、worktree carrier、预算池、最小 preload、bounded trace 和后置 task-point 计划；不重复实现这些机制。`child_agent|worktree_thread` 同构，ordinary 与 super 并行均使用同一合同；未明确 superCC 时必须 zero-load。

**QUALITY：** 阶段级 checker 覆盖默认/显式 override、child/worktree、compaction unchanged/changed hash、首错回报、日志留本地、superCC zero-load、registry/reuse/budget/trace 组合及跨平台路径；保持 `pending_count=69` 正文未读、四保护文件原路径/原哈希、Git index 为空、`.pyc=0`、remote count `0`，不 stage/commit/publish。

**完成条件：** 计划、MEMORY、史馆文字或 fixture 单独都不算实现。只有根 `SKILL.md` 置顶必要语义、唯一直接 governing reference（`references/court-state-runtime-agents.md`）、生产 dispatch/budget enforcement（现有 runtime/CLI 路径）和行为 checker（复用 `scripts/check_semantic_continuity.py` 及必要 runtime 回归）四层同时通过，且 `6000/12000` 默认漂移关闭，才可签发 `P00_TOKEN_ECONOMY_GATE=PASSED` 并进入 P05/新派发。

### Phase 0.5 — `CCR-R2-SHIR-20260714-A02-P05-TB01` 太子预启动资源预算门禁

任何 child agent、同官署扩容实例或新 wave 在启动前都必须取得 `TAIZI_RESOURCE_BUDGET_APPROVED`。评估至少包含：

1. 当前任务剩余规模、阶段目标和可并行的独立写集；不按理论最大并发申请。
2. host live capacity、active/retained nodes、reclamation 状态、树深和 provider/user agent budget。
3. 系统内存压力、预计上下文/消息/工具/时间预算，以及 99% 内存降级条件。
4. 每个实例的 role、instance、direct superior、唯一写集、预期产出、边际价值、失败回滚和阶段统合点。
5. 同角色多实例是否确有独立 shard；三省/尚书扩容是否满足其更低优先级和超级巨型门禁。

太子只允许以下裁定：

- `APPROVED(count=N)`：只启动已批准的 N 个实例。
- `DOWNSIZED(count=N)`：先缩减再启动，不先启动后中断。
- `SERIALIZED`：共享写集、主机压力或边际价值不足时改为串行。
- `DEFERRED`：预算或必要性证据不足时不启动。

禁止行为：

- 不得“先最大启动、再中断多余 agent”。
- 不得以 `super并行`、`superCC` 或 host 尚有空槽替代太子预算批准。
- 尚书省只能派发已批准的 role/instance/write-set；不得自行扩大 wave。
- 任务规模、可用内存、写集或剩余价值变化后，必须重新评估，旧批准不得跨阶段自动复用。

最小证据字段：`task_id`、`phase`、`wave_id`、评估时间、requested/approved roles 与 count、host active/capacity/retained/reclamation、RAM 使用率、message/tool/time budget、独立写集、裁定、理由、失效条件、首个 child start 时间。

本轮 Phase 1 RED wave 的顺位证据：

- 太子预检：RAM `58.07%`，Git index 为空，live host active `1`，capacity `16`，retained terminal `15` 且 reclamation verified。
- 尚书 agent-admit：`A02-PHASE1-RED-W1` 于 `2026-07-14T14:03:11+08:00` 获 `allowed=true`，user/provider budget 均为 `6`，批准六个互斥写集，不采用最大 15 席。
- 首个本轮 child start：`2026-07-14T14:04:45+08:00`；晚于资源批准。
- 裁定：`TAIZI_RESOURCE_BUDGET_APPROVED / APPROVED(count=6)`。当前 wave 无需裁撤；后续任何 wave 必须重新过本门禁。

#### P05-TB01 补充说明：层级动态预算池

**简单审查裁定：`APPROVE_WITH_REFINEMENT / ACTIVE`。**

`100%` 表示太子持有的归一化调度总池，用于说明优先级、并行份额和责任边界；它不是把 RAM、并发槽、上下文、消息、工具次数和时限相互兑换的单一物理资源。各硬上限继续独立 fail closed。

预算按直属上下级逐层下派：

1. 太子持有总池 `100%`，根据当前阶段、三省任务复杂度、风险、边际价值和剩余规模，动态分给中书省、门下省、尚书省，并保留必要的太子 reserve；示例 `30/30/30 + 10 reserve` 仅是说明，不是固定比例。
2. 中书省、门下省、尚书省只能在各自额度内向直属 child agent 或下级官署分配；尚书省在其额度内向六部下派，六部再向同官署 worker/工匠实例分配。任何下级不得自造额度或越过直属上级直接占用总池。
   - 六部 lease 的 `direct_superior=shangshu`。
   - 工匠/worker lease 的 `direct_superior=<owning_ministry_role>`，不得继续写成 `shangshu`。
   - 预算、任务、preload、trace 和释放事件都必须沿同一直属链路由，不得只在文案中声明层级。
3. 每次分配形成一个可追踪 lease：`budget_id`、`parent_budget_id`、`task/phase/wave`、role/instance、归一化份额、独立硬上限、写集、预期产出、批准者、开始/失效/归还条件。
4. 任一父级满足 `已分配 + reserve <= 自有额度`；没有明确 lease 就不得启动 child。空闲 host 槽位不等于可分配预算。
5. 已启动 lease 默认持续到该实例完成并安全释放，不为了重新排满预算池而盲目中断。只有最新用户取消、硬安全/资源阈值、重复或冲突写集、不可恢复故障等有证据的例外，才可由太子或直属上级在安全边界撤销。
6. 实例完成、失败收口、取消或主动归还后，未用额度逐级回到直属父池；任务规模下降时先停止新分配，并让已批准实例完成当前有价值的原子工作，而不是先大规模启动再裁撤。
7. 每个新 wave、跨阶段切换或资源显著变化都重新计算分配；百分比可动态变化，已完成任务的额度不得继续占用。

本轮 Phase 1 RED 的初始归一化分配采用：太子 reserve `10%`，中书规划额度 `10%`，门下阶段级 RED 审查 reserve `20%`，尚书执行额度 `60%`；尚书只为六个互斥 RED 写集各签发 `10%` lease。该分配反映本阶段执行占比高、审查按阶段集中进行；它不成为后续阶段固定模板。已完成实例的 lease 自动归还，未完成实例继续执行，不因本补充说明而中断。

### Phase 1 — RED 与测试先行

并行编写互不重叠的失败检查：

1. 迁移门禁 RED：pending 非零/未知、活跃/陈旧/未知绑定、两次稳定扫描、源漂移、目标越出 `.agents`、junction/单一物理库、保护文件不变。
2. 安装投影 RED：`.agents + current tool`，未知工具只装 `.agents`，未点名工具拒绝，固定五根 fanout 失败。
3. 初载/官署 RED：置顶充分语义、exact `AGENTS.md` 加载、相对持久路径、14 官署一致、错误 dossier/hash/prompt-only identity 拒绝；六部必须直属尚书省，工匠/worker 必须直属所属六部，任何跨级派遣失败。
4. 恢复/纠正 RED：新 task 有 charter revision/hash；暂停/纠正继续原 task，派生状态失效，重新进入三省，不直接跳六部。
5. `complexity_budget_gate` RED：用户明确复杂度边界必须优先；未明确时必要复杂度不得被盲目拒绝，低价值目标不得因“可做”而自动放行。
6. 多实例调度 RED：重复 role 可在 instance/shard/写集/统合门禁齐全时通过；双太子、双 canonical authority、重复 shard 或重叠写集失败。所有数值都是 whole-tree ceiling 且 root 计数：默认 `16 = 1 root + 15 child`，最新明确 `17 = 1 root + 16 child`，最新明确 `18 = 1 root + 17 child`；不得把显式数重新解释为 child slots。未获当前明确 override 时第 17 个 whole-tree thread 不得启动；最新用户明确 `count>16` 或明确 `unlimited/解限` switch 可提高 ceiling，旧状态/记忆/隐式 host 配置必须 fail closed。override 不得绕过太子预算 lease、99% 内存降级、层级、写集、preload 或实例追溯，也不得自动开满。每个小波获批后复测，禁止先开满再中断多余实例。
7. 宿主记忆/Obsidian/Git 托管 RED：无最新明确授权或门下批准的 writeback、非当前工具超出 pinned-link managed block 的写入、直接重写 `MEMORY.md` 正文、包含私密正文、把 note 当作已摄取、把 release package 当作投影源/输出均失败；实录与记忆被混入同一 schema/lifecycle、已提交实录被 amend/rebase/覆盖、记忆缺少实录/commit 证据引用、共享史馆 Git 出现 remote、非 allowlist/private/runtime/pending/config/package 路径被跟踪、并发 writer 或提交后 index 非空也必须失败。工具集合被锁死为 Codex/Claude/Hermes、已验证原生记忆被迁移/复制、未形成独立 local-only Git、出现 remote/submodule/subtree/nested tracking、缺少 repo/pathspec/HEAD/state/write-policy、暂存无关 dirty path 或没有 paired commit receipt 均失败。每个已验证安装工具缺少置顶史馆链接/反向来源链接、重复 managed block、链接逃逸、链接目标不是迁移后共享根、本体正文或换行被连带改写、或把不安全 fallback 伪报成功同样失败。
8. 空白宿主 memory-feature/install-runtime probe RED：在 probe 前创建 shared root、初始化史馆或任何工具记忆 Git、启用 memory 或执行安装写入必须失败；probe 改变配置/安装状态、结果不属于 `enabled|disabled|unavailable|unknown`、缺少证据或用户提示、`unknown` 自动启用、或对 Claude/Hermes/`other:<id>` 做超出原地 Git/pinned managed block 的未授权安装、配置、启用、正文写回均失败。安装收据必须按 runtime/CLI -> env/tool home -> CC Switch -> effective config/loader -> skill root/version/hash -> runtime probe 顺位生成；DB-only、directory-only、env-only、静态手填 manifest、把 `detected_unverified|unknown` 当作已安装、或不给 `active_verified|installed_verified` 建立独立空/非空 namespace 均失败。
9. 子官署追溯 RED：任一 child 缺少实例级时间—事件—行为简记或证据指针时，整体验收失败。
10. 能力官籍 RED：已登记且有效的匹配 skill 必须先于全盘发现被选择；账册 `missing/stale/corrupt/no_sufficient_match`、哈希/版本漂移时才允许有界补充发现。使用临时 manifest 与注入的 discovery spy 行为证明“命中不扫描、回退才扫描”；工具不兼容的登记项不得 dispatch。发现结果须经吏部验证后更新既有账册；每次调用无条件全盘扫描、未登记能力越过合格登记项、或吏部不维护漂移均失败。
11. 行为来源 RED：P05 层级预算池、尚书→六部→所属工匠、官籍优先/吏部维护、阶段级 TDD、共享史馆/当前工具和恢复门禁必须能从 `SKILL.md` 顶部必要语义核或其直接 governing reference 到达，并有对应行为测试；仅在 `MEMORY.md`/史馆候选/临时记忆出现时仍判失败。
12. 空白宿主配置 RED：覆盖规范目标枚举、controller-first、最新明确 mutation authority、`REMINDER_ONLY` 非阻断且不得声称合规、CC Switch proven block 的备份/事务/回滚、Codex 双 TOML 语义兼容与 secrets/provider/unknown keys 保留、no-CC-Switch 双文件路径、Hermes 上游失败证据和授权 fallback，以及 schema/ownership/precedence/current-value/compatibility 不确定时零修改、继续无关任务；DB-only 或 leaf-only success 必须失败，实际文件 reread/parse 与可用 runtime probe 才可通过。正常配置默认 16；显式 `--threads N` 可保留大于 16 的当前明确 count，但仅改变运行容量，不等于 dispatch unlock 或预算批准。配置应用后固定报告 `restart_required=true`、`restart_deferred=true`、`tasks_continued=true`；没有最新明确重启旨意时，任何 stop/kill/restart、任务暂停或对话中断都必须失败。
13. worktree 史馆实录 RED：每个由 court 创建、接管、维护或用于任务的 worktree（本轮包括全部 A02 worktree）必须有唯一 `worktree_trace_id` 和独立史馆 record；缺少 repo/common-dir/worktree/base/HEAD/lane/owner/批准写集/index/pyc/验证/最终处置任一必要字段、只存在 child lifecycle 简记、多个 worktree 合并成一条无归属记录、把完整 diff/prompt/private log/pending body 写入实录、或 workspace 台账冒充史馆实录均失败。既有 worktree 的 backfill 只能读取 Git/文件系统 metadata 与既有验证证据，不得读取 pending 正文。
14. 官署选择性加载 RED：routine child 未完整读取精简根 `SKILL.md`，或根 skill 仍内嵌应按需加载的全部 references/全官署扩展内容；跨 role 默认加载、worker 缺 owning ministry、缺 common hard gate/直属链/task-budget-worktree-write-set/evidence-stop/hash、风险触发未升级 governing reference、loaded_paths/bytes 与实际不符、core hash 漂移，或 routine path 依赖 plugin/plugin cache/plugin-only manifest/MCP/UI 均失败。
15. 任务点胶囊 RED：纯史馆 pointer 不具授权力；使用临时 shared-root fixture，证明最小 inline authorization envelope 只能解析 create-only、immutable、SHA-256 绑定的 dispatch capsule，并与当前 runtime task/charter revision/state、`dispatch_uid`、role/instance/direct-superior/worktree/lease/write-set 及 preload hashes 逐项匹配，ack 前不得进入 `running`。missing/stale/expired/revoked/hash mismatch/path escape/旧 revision/错误绑定均 fail closed；correction 递增 revision 并撤销旧 capsule/admission/agent，retry 只递增 attempt 且不可复活旧 attempt。canonical `court_code` 不变，另用 `task_point_code` 绑定 lineage/`TP` sequence/`R` revision/`A` attempt；碰撞、排序不稳或把 pending/private body、完整 prompt/diff/private log 写入 capsule 均失败。Phase 1 不写真实史馆。
16. V2 记忆裁定 RED：`reevaluate_memory_decisions.py --dry-run` 当前前像必须固定为 `entries=1033`、`changed_candidates=493`，并证明 candidate-only 启发式不得直接推荐合法 `WRITE`；`tidy_shiguan_records.py --apply` 在缺少 `decision_id`/`menxia_receipt` 时不得原地重写历史 `memory_decision`，只能追加 superseding decision；`check_shiguan_host_memory_and_child_trace.py` 当前 `A02_RED_EXPECTED_FAILURES=43` 必须作为未实现生产 evaluator/projection/blank-host API 的 RED，而不能作为 GREEN 证据。
17. 专项审查合同 RED：A-G reviewer 默认只读且写集为空；finding 缺少统一字段、门下以外角色作最终 adjudication、未去重同根因 finding、尚书派发非 `ACCEPTED` cluster、同一文件出现多 writer、或当前 A02/release/main 分支在最终全仓审查阶段被直接修改，均必须失败。
18. Semantic Continuity RED：新 task 未初始化 `charter_revision/charter_sha256/invariant_capsule`；correction 未替换 charter 或未撤销旧 assessment/checkpoint/completion/dispatch/admission/active agents/capsules/attempts；旧 epoch/attempt/dispatch result 未 quarantine；`agent_finish` 接受缺少 task/epoch/hash/dispatch/attempt/worktree/write-set binding 的自由文本；compression capsule 丢失禁止项；resume 绑定旧 epoch 或直跳执行态；permission change 误增 semantic epoch；plan/Git/recovery/Shiguan 多源不一致；任一 semantic task/event paired-write crash point 不可恢复；或 Windows/macOS/Linux 路径/时钟 fixture 不一致，均失败。共享 `tasks.json` corruption/LKG/snapshot durability 仍唯一归 Phase 1.5，不作为 Phase 1 关闭的循环依赖。
19. 官署载体与 superCC 分割 RED：`child_agent` 与 `worktree_thread` 缺少同构 dispatch/communication/result receipt 任一字段、worktree 未加载 `agents/office-dossiers/<role>/AGENTS.md` 与 exact profile、普通载体回退到 `agents/supercc-dossiers`、载体切换导致重复 authority/writer/attempt、或 worktree 记录缺失均失败；三权/拓扑选择未明确提示 `superCC=EXPERIMENTAL_CLI_ONLY`、普通 `super` 被误映射为 superCC、未显式启用却加载 superCC dossier/annex/profile/scripts/daemon/visible-office 语义、或启用后缺少 CLI/zellij+squad 能力证明同样失败。
20. `Decretum Matrix（诏令矩阵）` 更名 RED：根 `SKILL.md` 的规范 name/invocation、用户可见产品名、官籍/profile/dossier、README/install/package/release manifest、五根安装收据、史馆/Obsidian 标题或 runtime loader 仍把 `court-capability-router` 当正式品牌，仍使用撤回草案 `DecreeMatri`，或各面使用不同新名时失败；旧名出现在未列入 allowlist 的非历史/非技术 locator 位置、兼容入口未标 deprecated、伪造宿主不支持的 alias、创建第二份 skill 权威/第二包、盲目批量替换路径、改变四个保护文件路径/字节/hash、破坏 Git/worktree/recovery/Shiguan lineage 同样失败。RED 必须先生成结构化 name-surface inventory 与 allowlist，不把文档改名当 GREEN。
21. 史馆 CLI 编号/谱系 RED 必须精确覆盖七类失败：① archive 已提交而 task/event 未提交的 orphan crash 后重试错误复用/跳过 sequence；② 同一 `operation_id + payload_sha256` 由 32 个并发 replay 产生重复副作用；③ `record_uid` collision 未 fail closed；④ `child_agent` 与 `worktree_thread` 对同一 decree/parent/child_no 产生 lineage drift；⑤ `tasks.json`、`court_events.jsonl`、archive/index 与 compound receipt divergence；⑥ worktree 缺少 admit/start/report/finish/close lifecycle 或 terminal disposition；⑦ local authority realm/root fingerprint split-brain。每项 RED 都必须先失败并输出稳定 reason code，不得以既有 same-root lock 或 32-process uniqueness PASS 冒充完整 GREEN。

RED 只证明预期缺失；生产代码保持不变，记录准确失败原因后才进入 GREEN。

TDD 阶段审查规则：

- 单个测试仍应清晰、最小，并且必须先看到符合预期的失败。
- 同一 Phase 内可并行编写多个互不重叠的 RED；待该阶段 RED 集合形成后，统一进行一次 RED 审查。
- 门下把 A-G 专项 findings 去重并裁定为 `ACCEPTED|REJECTED_FALSE_POSITIVE|DEFERRED|SUPERSEDED`，再按依赖/写集形成 repair clusters；尚书只派发 `ACCEPTED` clusters。
- 每个 accepted cluster 先补最小可复现 RED，由单一 owner 做 GREEN，对应专项 reviewer 只读复核，再做 cluster SPEC/QUALITY；该 Phase 的全部 clusters 通过全局回归后才关闭。
- 不为每个断言、函数或微小整改点分别启动三省会审、SPEC reviewer 或 QUALITY reviewer，也不得用批量文本替换替代行为级 GREEN。
- 任一阶段审查失败，只退回该阶段对应的实现/测试集合，不重开整个目标。

#### Phase 1 GREEN close contract

Phase 1 必须在进入 Phase 1.5 前完成 Semantic Continuity 的 semantic-binding core：new-task revision/hash/capsule、correction 全量失效与 ThreeDepartments re-entry、dispatch/result binding、stale-result quarantine、最小 `court semantic` JSON CLI/receipt 和 current task/event paired-write recovery。Phase 4 只接入 memory/task-point/install downstream consumers，不拥有该 core 的首次 GREEN。

Phase 1 不实现共享 ledger 的 corruption/LKG/stable-snapshot/CAS restore；这些唯一归属 Phase 1.5。按此 owner matrix 做无环依赖检查后，Phase 1 cluster GREEN/SPEC/QUALITY 通过才可开启 Lane G 剩余 ledger durability delta。

Phase 1 的编号/谱系 GREEN 继续沿既有 cluster 串行：

1. **RC2 first**：在现有 runtime lock/CAS 与 semantic receipt 上实现通用 operation interface、最小 `court_operation_journal.py`、decree-open 幂等分配、compound receipt、三段 closeout 与 `closeout-recover --operation-id`。Phase 1 只用临时 local roots 验证 allocation/task/event 和 synthetic archive/index killpoints，不读取真实史馆或 pending body。
2. **RC4 after RC2**：串行修改共享 `court_runtime.py`，统一 `office admit|start|report|finish|close`，冻结 `main_court_code/parent_court_code/child_no/lineage_key/version`；`agent-*` 保持 child-agent 兼容包装，worktree 只增加 thread/worktree/branch/start-head proof。至少两个 child 与两个 worktree 的 schema/lifecycle 必须同构。
3. **RC6 bounded**：Phase 1 实现 local authority realm/root fingerprint 的纯函数和 fixture，root mismatch fail closed；真实 `.agents` authority-root fingerprint 与 RC2 archive transaction 只能在 Phase 2/3 pending、quiescence、migration gate 通过后由单 writer 串行接入。
4. 既有 same-root file lock 与 32-process allocator uniqueness 保持正回归；新增 32-way same-operation replay、record_uid collision 和 allocation/archive/index/task/event killpoints，不重写已工作的锁或 allocator。

最新 cluster 裁定为 `RC1=APPROVED`、`RC5 core=APPROVED`；完整 runtime 当前只保留外部 RC4 `office-bound-wave` RED。RC5 rollout debt 仍须统一 `README.md`、`references/sections/court-office-name-profile-skill-binding.md` 与 `court_office_bootstrap.py` 的 `required_skill/loaded_skill` 为 `decretum-matrix`，同时保留 `court-capability-router` 技术 locator。上述局部批准不得表述为 Phase 1 整体 GREEN，仍须 RC4、阶段级 SPEC/QUALITY 与全局回归。

### Phase 1.5 — 共享 `tasks.json` 完整性与恢复门禁

该阶段固定插在 Phase 1 阶段级 GREEN/SPEC/QUALITY 之后、Phase 2 首次主机变更之前。`TASKS_LEDGER_INTEGRITY_GATE=PASSED` 前，Phase 2 与真实史馆迁移一律停止；当前 `pending_count=69` 硬门禁继续独立生效。

现场审查已确认：多对话共享同一 canonical `references/court-runtime/tasks.json`；当前快照可严格解析，现有正规写路径已有 lock、sibling tempfile、file `fsync`、`os.replace` 与 Windows sharing-violation 重试，因此不得把未捕获的瞬时错误武断归因于当前原子写。已确认的系统缺口是单一大 JSON 的读者缺少稳定快照重试、last-known-good、损坏隔离和统一的 sanitized diagnostics；稳定损坏还会阻断正规修复写入。

阶段顺位：

1. **RED**：仅在临时 `COURT_RUNTIME_ROOT` 构造截断、extra data、无效 UTF-8、BOM、v2/v3 混合、Windows sharing violation、并发多读多写、主文件损坏但 LKG 有效，以及错误不得泄露任务正文的失败 fixture。
2. **GREEN/core**：在现有 `court_runtime.py` / `court_file_lock.py` 内实现统一稳定 snapshot loader；所有读者走同一锁与有界重读，按 bytes 严格解码并核对 size/mtime/hash。正规写入继续 tempfile + fsync + replace，并原子维护 `tasks.json.lkg`；不得引入新数据库或后台服务。
3. **GREEN/recovery**：只读查询可从已验证 LKG 返回 `runtime_degraded`，避免其他任务整体失效；任何 mutation 对损坏主文件继续 fail closed。显式 CAS 恢复必须匹配 corrupt SHA-256，先隔离原件再恢复 LKG，禁止普通读取静默覆盖。
4. **SPEC**：保持现有根对象格式和 v2/v3 混合兼容，本轮不做破坏性 envelope 迁移；在 `court-state-runtime-agents.md` 固化 reader mode、LKG、隔离、sanitized diagnostics 与 Windows replace 契约。
5. **QUALITY**：运行 runtime/concurrency/agent/pending-trust 既有检查、Windows 长路径与 sharing-violation fixture，并对真实 ledger 只读复验；不得读取或哈希 pending bodies。

并行分支写集：

- `a02-tasks-ledger-red`：仅 runtime/concurrency checker 与失败 fixture。
- `a02-tasks-ledger-core`：仅 `court_runtime.py`、`court_file_lock.py`；依赖 RED 契约。
- `a02-tasks-ledger-consumers-spec`：仅外部 consumers、对应 checks、`court-state-runtime-agents.md` 与本执行书；依赖 core API。
- `a02-tasks-ledger-review-readonly`：零写集；集成后执行 source audit、全套测试、真实 ledger 只读复验与正文泄漏检查。

门禁必须证明 canonical path 唯一、读写链完整、稳定快照/LKG/隔离生效、并发 RED 转绿、错误不泄露正文、混合 schema 兼容、恢复 CAS 可追溯、Git index 为空。失败时只返回 `TASKS_LEDGER_INTEGRITY_BLOCKED`，不得借机另建第二 ledger、静默覆盖损坏文件或越过 Phase 2。

### Phase 2 — 史馆门禁与首次主机变更

- 只读扫描 presence/runtime/locks 元数据，不打开 pending 正文或占用记录正文。
- 先用 metadata-only queue checker 证明 pending body count 为 0。只要 count 非 0 或 binding 未知，就返回 `WAITING_FOR_PENDING_BODY_AUTHORITY`；不得打开、读取、哈希、复制、目录改名、移动、删除或 mark-seen。
- 当前预检为 `pending_count=69`，所以本执行书确认后可以完成 RED 和只读门禁，但不得声称迁移已可执行。不得为绕过此门禁创建新 capability、第二存储或临时分库。
- 未知记录绑定按 `*` 阻断。
- 活跃会话存在时只写 migration-control marker，50 秒有界等待后返回。
- 需要两次零活跃、至少间隔 30 秒、file count/bytes/newest mtime/inventory digest 完全一致。
- migration-control marker、transaction lock、receipt、临时文件和 rollback control 必须位于 content inventory 之外；每次 cutover 只有一个持锁 run owner，marker/receipt 都绑定同一 `migration_id`，其他 run 不得拆除或回滚其 junction。
- 两次稳定扫描和 cutover 当下快照必须同时绑定 source canonical path、volume serial、directory file-id、file count、total bytes、newest mtime、64 位十六进制 inventory digest 与明确的 exclusion-policy id；扫描时间必须是带时区且相对注入时钟新鲜，未来、陈旧、回拨、解析失败或重复证据一律阻断。`binding_snapshot.bindings` 必须为空；active、stale、unknown 或结构不明均不得伪装 READY。
- pending 为 0 后，验证源与目标位于同一 NTFS 卷、目标不存在、旧路径不是 reparse point、新路径规范化后仍在 `.agents` 下。
- Windows pending/source/target 根必须拒绝 symlink、junction 与任意 reparse point；路径校验复用现有 Windows 安全规范化与身份原语，拒绝 ADS、设备名、尾点/尾空格、跨卷、自迁移、未知 delete-share readiness 和 file-id/volume 缺失，不另造平行安全框架。
- 最终切换时短暂停 daemon，复核源目录 file-id 与元数据清单，然后将旧物理根同卷原子改名到新权威根；不做全量复制、不建立 `legacy-source` 第二副本。
- 在旧路径建立只指向新权威根的 junction；验证 canonical target、新旧路径同一 directory file-id、文件数/总字节/newest mtime 不变，再重启 daemon。
- 单一物理库与兼容入口的判断粒度固定为两个 `references` 根，而不是它们仍需共存的父目录；成功拓扑必须由 `_active_shared_root` 端到端验收，禁止父目录并存被误判为双物理库。
- 最终 `CUTOVER_VERIFIED` receipt 只能在 daemon 恢复成功且 live junction target、volume+directory-id、inventory 四元组、保护快照和 rollback terminal state 再验证后，写入 inventory 外控制面并原子回读。普通 consumer 只接受这一最终状态，并必须重新读取实际 junction/目录身份/inventory，不能只信 receipt 自报字段。
- `CUTOVER_VERIFIED` 是物理切换收据；A02 的整体 `SHIGUAN_MIGRATION_ACCEPTANCE` 还必须等待 Phase 3 的共享 Git 初始化、per-tool pinned link/反向 link 和 `MIGRATION_LINKS_VERIFIED`。不得以物理 receipt 跳过逻辑导航绑定。
- 失败回滚只处理本轮创建且 target 精确匹配的 junction：移除该 junction，将同一 directory file-id 的新根原子改回旧路径，恢复 daemon。任何预存目标、非预期 reparse point、跨卷、路径越界、锁冲突或 file-id 漂移均 fail closed。
- 任一 receipt 写入、回读、daemon 恢复或 final live-state 失败，都不得留下可消费的 `CUTOVER_VERIFIED`；必须在同一 run lock 下原子删除或改写为精确失败/回滚终态并回读。rollback 二次失败保守停机，consumer 必须拒绝 `rollback.applied=true`、`rollback.ok=false`、commit unknown 或缺字段。
- 用临时 fixture 做切换前、改名后、junction 后、daemon 恢复前四个注入失败点的幂等回滚测试；不在真实史馆做断电演练。
- checker 必须使用稳定 case id 与规格映射；汇总数量（例如 `39/39`）本身不是门禁。至少覆盖真实原子 helper 的 sibling temp/file fsync/replace/readback 事件、Windows sharing violation、错误 junction、实时 inventory 漂移、receipt terminal rollback、marker/run-owner 冲突和成功拓扑端到端解析。
- 四个保护文件始终留在 `.agents\skills\...\references` 原位，不参与迁移。

### Phase 3 — Obsidian 与共享根

- `shiguan_paths.py` 默认解析 `.agents/court-shiguan`；source-agent 检测与数据所有权解耦。
- 既有宿主只在 Phase 2 迁移与单一物理库验证成功后生成记忆投影；空白宿主则必须先完成下述只读 memory-feature probe 和用户提示，才允许创建 shared root 或 Obsidian 配置。
- 既有宿主只有在 `CUTOVER_VERIFIED` 后才可在新的权威 `references` 根初始化/接管本地 Git；空白宿主则在只读 probe 和用户选择之后、shared root 创建时一并初始化。`.gitignore`/tracking allowlist 必须先于第一次 `git add` 生效，且仓库保持无 remote。
- 同一仓库分层托管正式实录、记忆候选/裁定、共享批准记忆、per-tool projection、manifest 与 `shiguan-tree`。实录 commit 追加不重写，记忆 commit 通过新裁定演进；二者以 record id、`derived_from_record`、`evidence_refs` 和 commit id 互相追溯。runtime/pending/private/config/package 等排除路径不得进入 Git 历史。
- 共享根中的 decision 记录必须来自 `semantic_adjudication`：史馆先做 evidence/privacy/dedup/conflict/scope/freshness 纯分析，门下再签发 `APPROVE|REJECT|DEFER|SUPERSEDE` 与 `decision_id/menxia_receipt`。Git commit、Obsidian projection、native pending queue 和文件存在只属于 evidence/application，不得反推批准。
- 任何历史 decision 纠正都以 append-only superseding decision 追加；不得让 `tidy_shiguan_records.py --apply` 或其他整理器在缺少 decision/receipt 时原地改写历史 `memory_decision`。
- 史馆 Git 提交由共享锁保护的单写者串行执行，只在阶段 checkpoint、结诏或记忆裁定时提交；成功提交后记录 parent/commit id 和 tracked-path receipt，并恢复 clean index。Git 失败只阻断该记录/记忆持久化，不得静默声称已托管。
- 对 install receipt 证明的开放工具集合逐一解析 native memory root 与 owning repo。原生文件不迁移：已有 Git 仓库登记其 repo root + memory pathspec；无 Git 时只有在 loader/兼容性 probe 通过后原位初始化，原位 `.git` 不兼容时使用史馆管理区 separate git-dir + 原生 work tree。每个工具记忆库都是独立 Git 仓库；新仓库无 remote，既有 tool-owned remote 不变且史馆禁用任何 remote 操作。禁止 submodule/subtree、共享仓库嵌套跟踪和正文投影复制；native git-dir/objects 必须在共享史馆 allowlist 之外。
- 共享史馆 Git 是管理 hub：其 registry/namespace 保存 `memory_store_id/tool_class/native_root/repo_root|git_dir/pathspec/branch/HEAD/state/write_policy/shared_commit/native_commit/transaction_id`；原生仓库 pinned block 反向指向 shared repo id/namespace/commit。两侧分别提交并互引 receipt，只 stage 本轮批准的 managed link/update-note，已有无关改动一律保留且不纳入。repo id、pathspec、commit 或 transaction id 任一不匹配，或任一受影响 index 非空/HEAD 不可读，即不得声称 `MEMORY_REPO_MANAGED`。
- 对每个 `active_verified|installed_verified` 工具解析 canonical memory entrypoint 和可写/置顶能力；写入最多一个带版本 marker 的 pinned navigation block，链接到共享 `shiguan-tree/_index.md` 与 `memories/tools/<tool_class>/` namespace。只允许更新该 block，保留其余内容；不安全时使用工具支持的独立 `00-SHIGUAN.md`/等价 pinned entry，仍不确定则 `LINK_BINDING_BLOCKED`。
- 在对应史馆 namespace 写入反向 link、source relative id/path、工具记忆仓库 HEAD、paired commit/pathspec receipt 与 memory state。两端回读且两个 Git receipt 匹配后才记录 `MIGRATION_LINKS_VERIFIED`；空记忆也必须有 Git 仓库、pinned link 和 empty-state namespace。
- 用现有 field-level CAS 只替换旧史馆 vault 项，保留其他 vault/config 字段和 API key。
- 注册同一 Git 仓库内的 `.agents/.../shiguan-tree`，不强制打开；Obsidian 是管理视图，Git 是版本层，两者都不取代 `SKILL.md`/governing references 的行为权威。
- preserve-only dry run/real sync 均要求 `removed=0`；冲突立即停止。
- 复用现有 bridge/index/export/sync 路径，对 install projection/manifest 证明已安装本 skill 的每个规范工具类生成 index-level MEMORY/memories projection；每类一个隔离 namespace 和独立 graph，禁止任何跨工具 node/edge。源文件只读，投影仅含相对 source id/path、hash/fingerprint、state、headings/topics/relations，排除 private raw bodies 与 release packages；不新增数据库或后台服务。

### Phase 4 — 当前工具、初载和官署加载

- 安装投影只有 shared `.agents`、current-tool portable copy、repository-only 三类。
- 本机 skill/config 安装目标严格为 `.agents + Codex`；Claude/Hermes skill/config/正文只比对前后哈希，允许的差异仅为已验证原生记忆仓库的 Git metadata 与 pinned managed block。
- 配置分支排在 Phase 2 迁移（空白宿主为 no-source proof）、Phase 3 共享根和本 Phase current-tool 安装投影完成之后；不得提前修改任何 controller、DB 或实际配置文件。
- install projection/manifest 同时是 memory probe 候选集和 Obsidian projection eligibility 的唯一审计收据，但其内容必须由当前运行态、环境变量/tool home、CC Switch、实际 loader/config、skill root/version/hash 和 runtime probe 生成，禁止手工静态宣称或全宿主无界扫描。
- `active_verified|installed_verified` 的 `codex|hermes|claude-code|other:<stable-id>` 工具类都必须生成独立 memory namespace/graph；原生 store 缺失或为空时记录准确的 `empty|disabled|unavailable|unknown` 状态。`detected_unverified|unknown` 只进入探测报告，`not_installed_verified` 只有在全部有效 loader roots 被证明无合法 skill 后成立。
- 空白宿主的第一步必须是无副作用 probe：在任何 shared-root create、史馆/工具记忆 Git init、memory enable 或 install write 前输出每个候选工具的安装状态、`enabled|disabled|unavailable|unknown`、原生路径/Git 兼容性证据和用户选择提示。`unknown` 不得自动启用；Claude/Hermes/other 除已明确要求的原地 Git/pinned managed block 外不得修改。用户选择完成后仍按 `.agents + current tool` 默认规则执行，额外工具只能来自最新明确授权。
- current-tool/target 明确后先读探 CC Switch 或该工具真实 loader/source-of-truth。标准未满足但无最新明确 config-change 授权，或语义不确定时，只输出 `REMINDER_ONLY`、精确原因和 `compliance_claimed=false`，不阻断其他 Phase 4 工作。
- CC Switch 对应 target block 已证明时，先做敏感 preimage 备份和可回滚事务，再更新实际有效配置；Codex 同时对解析后的 `config.toml`、`managed_config.toml` 合并等价/兼容 delta，保留 secrets/provider/unknown keys。无 CC Switch 时采用同样可回滚的 Codex 双文件路径，禁止 blind byte replacement、leaf-only 修补或 DB-only 验收。
- Hermes 若无法由 CC Switch 管理，保留 upstream attempt/result；仅在最新明确授权且 loader/path/precedence/current values/compatibility 均确定时进入实际文件 fallback。`claude-code` 与 `other:<stable-id>` 同样遵循 controller-first、明确授权和实际文件验收。
- 完成后 reread/parse 实际有效配置文件，并在 runtime probe 可用时运行；任一 DB schema、字段所有权、有效优先级、当前值或兼容语义不确定即不改/回滚配置分支并继续无关任务。参考共享史馆 `references/recovery/ccswitch-codex-deep-reset.md` 与 `references/recovery/codex-ccswitch-recovery.md`，不新增 controller 或配置框架。
- 每次获准安装完成并更新 manifest 后，只刷新对应工具类的隔离 metadata/index graph；投影不构成 memory writeback，不修改源 MEMORY/memories 文件，body mirror 继续封存待后续旨意与门下隐私复核。
- `SKILL.md` 顶部增加最小 pinned initial semantics；现有 checker 验证其位置、必要字段与单一来源。
- 所有本轮新增硬门禁都写入 `SKILL.md` 必要语义核或由该核直接链接的唯一 governing reference，并由生产代码/行为测试证明。不得用 host `MEMORY.md`、史馆投影或 update note 替代 skill 源文件变更证据。
- `court_office_bootstrap.py` 解析绝对文件只用于读取/哈希，持久输出统一为相对路径。
- 每个 spawn 先读取 exact role `AGENTS.md`，验证 dossier/profile/SKILL 哈希并 ack；未 ack 不 running。
- 统一 `carrier_kind=child_agent|worktree_thread|supercc_cli_office` dispatch envelope。`worktree_thread` 通过根项目可见 task、项目级 child worktree 与 `attached/<project>` 通信/交接，仍须 exact-role preload、semantic receipt、budget/lease/write-set、status/result ack 和独立 worktree 史馆实录；载体不是 authority，不得重复同一 integration owner。
- 普通 `child_agent|worktree_thread` 的 exact-role `AGENTS.md` 固定来自 `agents/office-dossiers/<role>/AGENTS.md`；不得再把 `agents/supercc-dossiers` 当普通 dossier root。把 superCC 全部语义移到根 `SKILL.md` 直接按需链接的独立 annex 和 `supercc-dossiers`。三权/拓扑选择先报告 `supercc_experimental_cli_only=true`、依赖和差异；只有最新明确启用才加载/探测。ordinary super 路径不得 import/read/start superCC dossier/profile、annex、zellij/squad wrapper、watchdog/daemon 或 visible-office state。
- 以单一 identity manifest 完成 `Decretum Matrix（诏令矩阵）` 品牌迁移：根 skill 的规范 name 与最终物理安装目录 basename 均为 `decretum-matrix`，所有当前用户可见/机器可验证身份面同步；撤回草案 `DecreeMatri` 不得作为当前身份，`court-capability-router` 仅留在批准的 repository/Shiguan locator、历史证据、deprecated compatibility install locator 及兼容输入中。兼容解析只转到同一物理 skill/authority，不创建别名副本；宿主不支持真实 alias 时返回明确迁移提示。更名逐簇修改并逐面测试，禁止无差别文本替换。
- preload/dispatch 只加载既有职责：太子/三省审议统筹，六部/工匠执行，不重写官制本体。
- runtime task 创建时初始化 charter revision/hash； continuation/correction/resume 继续原 task、失效旧派生状态、回三省再执行。
- 消费已在 Phase 1 GREEN、Phase 1.5 durability 通过的 Semantic Continuity Guard；本 Phase 只把 memory/task-point/install/Obsidian downstream apply/commit/closeout 接到 current receipt，不重复实现 core 或另建状态系统。
- 消费已在 RC2/RC4 完成的 operation/office lifecycle contract；真实 archive/root 接入只补齐经 Phase 2/3 验证的 RC6 root receipt 与 RC2 closeout archive stage，不重新分配主编号、不改变冻结 lineage，也不创建 per-worktree tasks/events。
- task-point 复用同一 epoch/charter/capsule/dispatch/attempt binding；任何 downstream stale result 继续 quarantine，并按新 attempt 重派。
- 14 TOML 与 14 dossier 全量重生成/复核，修复 `libu-hr` stale hash 和旧 LocalAppData 说明。
- 能力选择先走 `references/court-capability-registry.md` 的有效官籍；只有 `missing/stale/corrupt/no_sufficient_match` 才触发有界补充发现。吏部在 skill 安装/升级、hash/version 漂移、dispatch 失败和阶段结项时刷新并校验账册，不启动无界常驻扫描，也不另建第二账册。
- 已批准提案 A：dispatch plan 以 `instance_key` 而非 `role_key` 判重；保留每 role 一个 canonical authority，允许六部优先扩展独立 workers；太子禁止扩容，尚书扩容须过 `super_giant_task_gate`。
- 已批准提案 B：实现 agent-first `court memory scan|adjudicate|apply|verify|reconcile` JSON CLI/API；核心 rubric 是无副作用纯函数，覆盖来源权威、证据质量、稳定性、复用价值、临时性、隐私、scope/freshness、duplicate/compatible_update/contradiction/scope_collision/stale 与 `keep|merge|replace|supersede|reject|defer`。当前工具 adapter apply 需要最新写回授权 + 门下批准；非当前工具正文另需最新 target authorization。
- 已批准提案 C：先读取用户最新明确复杂度边界；仅在未明确部分由太子主持 complexity budget 裁定，记录价值、最简替代、预算、风险、回滚与最终结果。
- 已批准提案 D：每个 child 生命周期事件写入现有 append-only ledger，最终史馆记录引用逐实例简记和证据 anchor，不保存全量内容。
- 每个 worktree 另行形成独立、metadata-first 的史馆实录；复用 `archive_checkpoint.py`/既有 plan-archive 与 runtime evidence，不另建数据库。创建/首次接管时记录 identity/base/lane/write-set，阶段验收时追加 index/pyc/tests/SPEC/QUALITY，集成、保留、阻断或正规退役时写 terminal disposition。child trace 可被引用，但不能替代该 worktree record。
- 官署 routine preload 完整读取精简后的根 `SKILL.md` 与本 role 精简 dossier/profile，再附加直属上下游 adjacency、bounded task/budget/worktree packet、命中的官籍项与按需 governing references；记录实际 loaded paths/hashes/bytes 与 ack/first-report latency。行为编辑、审计、发布、争议和最终语义重载扩大到全部直接相关 governing references/role annexes，但根 skill 始终完整读取。目标为 task packet 前上述固定加载面 `<=20 KiB` 且相对中书 76,990-byte 基线至少降低 70%，不足或越载都需准确报告。
- 上述优化只通过纯 Skill 的渐进加载、权威内容分片/索引和既有 bootstrap/dispatch/checker 完成；不得新增 plugin artifact、plugin-only 运行依赖或第二语义入口。
- 仅对结构化、可执行的 child assignment 建立任务点：先在既有 shared Shiguan archive create-only 写入 inert capsule，再把相对 path/detached SHA-256、独立 `task_point_code`、current task/charter revision/state 和 dispatch binding 写入既有 runtime/admission 并回读，最后才发送最小 envelope。wake/status/heartbeat 不创建任务点；史馆 capsule 只是证据/召回载体，不是第二权威。
- child 必须验证 capsule 位于 shared root、重算 hash、核对 envelope 重复字段与当前 runtime binding，然后完整重读精简根 `SKILL.md` 和 exact-role dossier/profile；回报 task-point、capsule、task/charter、role/instance/superior/worktree/lease/preload hashes 的匹配 ack 后才可 `running`。任何缺失、过期、撤销、错误绑定或旧 charter 一律拒绝，不得降级成纯 pointer。
- 真实 capsule 严格排在 Phase 2 迁移与 Phase 3 shared-root 验收之后；此前仅用临时 fixture。实现复用现有 `court_runtime.py`、`court_cli.py`、`archive_runtime_task.py`、`archive_checkpoint.py` 和 append-only court events/archive，不新增数据库、daemon、第二 store、plugin 或第二状态机。
- 量测目标为 envelope `<=800` UTF-8 bytes、capsule `<=1800` bytes、resolver return `<=250` bytes。只有 child resolve 后的有效总输入不超过原 inline bytes 的 `80%` 时才可声明 context saving；否则回退完整 inline assignment 或标记 `reliability_only`，不得用传输缩短冒充 token 归零。

### Phase 5 — 文档与离线包

- 更新 README、CHANGELOG、RELEASE-LOG、docs/logs、release-manifest。
- INSTALL-PROMPT 保持短，只说明验包、装 `.agents`、检测当前工具、只装当前工具、其他工具须明示、创建/检查共享史馆和 Obsidian。
- INSTALL-PROMPT 追加一句 controller-first 配置检查；不满足标准只报非阻断 `REMINDER_ONLY`，任何配置改动须最新明确授权并回读实际文件验证。
- 保留 beta0.5.12 与 beta0.5.13 run1/run2 原字节。
- 只新建 beta0.5.13 run1b/run2b；no-clobber；外置 SHA256 sidecar；两 ZIP 必须字节相同。
- 包内不得含真实史馆、私有 Obsidian 状态、凭据、raw logs、pending imports、memory bodies、runtime ledgers、自含 ZIP digest、主机实际配置、配置 preimage、CC Switch DB/sidecar/backup/journal/controller dump 或 provider/auth 值；配置测试仅用合成 fixture。

### Phase 5.1 — 统一无损 updater 与 npm 本地包（迁移后）

本阶段只能在 Phase 2 史馆迁移与 Phase 3 shared-root 验收通过后进入，不改变 P00 最高优先级或“先迁移史馆”顺位。实现一个 mutation core、两个薄入口：源码 skill 可调用 `update|migrate`，跨平台 npm CLI/package 调用同一 core/plan/receipt；禁止复制两套更新逻辑、状态机或安装权威。

- updater 识别 legacy `court-capability-router` 与 canonical `Decretum Matrix（诏令矩阵）`，并把每个授权安装根的 canonical 最终物理目录固定为 `skills/decretum-matrix`，使 folder basename、machine name 与 canonical skill name 对齐。旧 `skills/court-capability-router` 只能成为 deprecated compatibility locator/junction/router 并解析到同一物理 skill/authority，不能保留为第二 authority 或第二副本。
- 目录 cutover 与内容更新共用同一 mutation core，流程固定为 `backup -> staged atomic rename/move -> native loader reread -> five-root path/hash/identity proof -> rollback(on failure)`；任一步失败立即停止，按 receipt 原子恢复 preimage，并证明旧/新路径没有留下两个物理 authority。不得用先复制后长期并存、静默删旧目录或只改 manifest/path string 代替受检 rename/move。
- Phase 6 的本机 `.agents + Codex` 预安装和 Phase 10 的最终五根收敛必须调用同一 updater；默认仍只更新 `.agents + current tool`，只有既有 Phase 10 明确授权才 fanout 五根。源码 skill 的 `update/migrate`、本地包验证和未来单条 `npm exec|npx` 都执行同一 target/provenance/backup/apply/verify/rollback 逻辑。
- 新增 cross-platform npm CLI/package，但本轮 `npm publish`、remote、tag 和外部发布均为 `NOT_RUN`。先用 create-only local `.tgz` 做 Windows/macOS/Linux clean-home fixture，并证明 `npm exec --package <local.tgz>` / `npx --package <local.tgz>` 的显式命令入口；不得使用隐式或危险 `postinstall` 修改宿主。
- updater 永不覆盖、迁移或打包 shared Shiguan、`pending/**`、private/raw evidence、native memory bodies、Obsidian private state 或未授权配置。Skill 物理目录更名不得盲目迁移 shared Shiguan runtime data locator；`court-shiguan/court-capability-router` namespace 继续受独立 preimage、迁移与 lineage 门禁。controller/config 仍受既有 controller-first 与最新明确授权门禁；旧入口只作 deprecated compatibility router，不能产生第二份 skill、第二 updater 或第二 package authority。
- **本次增补状态：`PLAN_ONLY / NOT_IMPLEMENTED`。** 当前 updater branch 只允许更新本 execution book；不得热迁移任何宿主 skill 目录，不得触碰 root/mainline、release manifest、安装根、shared Shiguan 或 `pending/**`，也不得把本计划表述为 path cutover 已完成。

**GREEN：** 单一 updater core 生成可回放 JSON plan/receipt，验证 legacy/canonical 检测、备份、staged atomic rename/move、native loader reread、canonical `skills/decretum-matrix` 路径、逐文件 hash/identity、current-tool/五根授权矩阵、compatibility locator 单物理 authority 和失败回滚；源码入口与 npm CLI 对同一 fixture 产生语义等价 receipt。

**SPEC：** update 与 migrate 只是同一 core 的受控模式；target selection 继续遵守 `.agents + current tool` 默认、显式额外工具授权、Decretum Matrix 单一 authority、protected/shared/private exclusions 和 P00 bounded receipt。npm 是分发/调用入口，不是新行为来源。

**QUALITY：** 覆盖 Windows/macOS/Linux 路径、长路径/权限/文件占用、版本升降级/legacy migration、幂等重跑、killpoint rollback、损坏/错误包 hash、native reread 失败、五根部分失败和零危险 postinstall；local `.tgz` 与 ZIP privacy/no-clobber/determinism 门禁同时通过，index 为空、`.pyc=0`、remote/publish 未运行。

**FINAL ACCEPTANCE：** 本机最终安装与 Phase 10 五根最终同步都必须由该 updater receipt 证明；五根 canonical path 均精确为 `skills/decretum-matrix`，逐文件 hash、identity、native loader/version reread、rollback 可用性、`physical_authority_count=1`、shared Shiguan/pending/private/memory/config 不变和 legacy compatibility locator 受控解析全部通过。未来才允许提供一条 `npm exec|npx` 更新命令，且它必须调用同一已验 core；本轮只保留 local `.tgz` 证据，不发布 npm。

### Phase 6 — 本机 current-tool 预安装与整体验收

- 本阶段只备份 `.agents` 和 Codex，写 per-file SHA256 manifest；这是 Phase 9/10 前的 current-tool 预验，不是最终五根收敛。
- 只通过 Phase 5.1 的统一 updater 把已验证 staging payload 安装到 `.agents + Codex`；最终五根最新版安装严格留在 Phase 10，并继续使用同一 updater。
- 验证 `.agents`/Codex 为 beta0.5.13 且 portable hash 一致；Claude/Hermes skill/config/正文哈希不变，只有批准的 pinned managed block 和 Git metadata 可变化。
- 验证空白宿主配置 fixture：未满足/未授权/不确定返回非阻断 `REMINDER_ONLY` 且不声称合规；授权 Codex 路径通过 controller-aware backup/transaction、双 TOML 语义兼容和实际文件 reread/parse（可用时 runtime probe），而 leaf-only/DB-only 失败；Hermes 上游失败只在授权且语义确定时 fallback。
- 验证唯一物理史馆在 `.agents`；旧路径仅 junction；Obsidian 指向新树且 `removed=0`。
- 验证保护四文件、beta0.5.12、beta0.5.13 run1/run2 原哈希不变。
- 依次取得 `SPEC PASS`、`QUALITY READY YES`、`COMPLEXITY BUDGET PASS`、整体验收通过、空 index。
- Phase 6 完成既有整体验收；最终结诏和父 Task 3 恢复仍须等待下述最末 macOS 发布门禁。

### Phase 7 — 最末 macOS 发布门禁

- 本门禁严格排在既有 RED、GREEN、SPEC、QUALITY、整体验收之后，不得前移或破坏“先迁移史馆”的顺位。
- 优先以同一发布包和同一安装逻辑证明 macOS 兼容；若不能证明，则单独生成、命名并验收 macOS 包。
- 必须通过 Darwin clean-home fixture、POSIX 相对路径、无 Windows Registry/MSI/盘符假设、`.agents/court-shiguan/court-capability-router/references` 单一共享史馆、默认仅 `.agents + current tool`、包隐私排除项和逐文件/包 SHA-256 清单。
- 每次版本迭代的 README、发布文档和 `docs/logs` 必须记录实际 macOS 证据；本 C5 波只修改两份 A02 计划，不修改这些文件。
- 最终包署名固定为 `RowlandL <3289324701@qq.com>`。默认开源方案为 `Apache-2.0` 的 `LICENSE` 加 `COPYRIGHT`/`NOTICE`，保留署名、许可与 NOTICE，并附“学习交流、非官方售卖渠道、禁止冒充官方或移除署名”的说明；该说明不得被写成 Apache-2.0 之外可执行的禁止商业转卖附加限制。
- OSI 开源许可不能同时附加法律上的禁止商业转卖。若用户最终仍要求 enforceable no-resale，发布前必须取得最新明确选择并在必要时完成法律审查，切换为 noncommercial/source-available 自定义许可且醒目标记 `NOT_OPEN_SOURCE`；禁止把 `Apache-2.0` 与“禁止转卖”写成同时有效的矛盾条款。
- `FINAL_MACOS_RELEASE_GATE=PASS` 后还必须完成 Phase 9 与 Phase 10；只有 latest branch、final package、five roots 与 `SHIGUAN_LATEST_SYSTEM_GATE` 全部通过，才使用迁移后的共享史馆执行完整 `archive_checkpoint.py` 最终结诏并恢复父 Task 3。

### Phase 8 — 本地根控制仓库与子仓库治理恢复门禁（PASSED，含 8.3）

后续最新旨意明确暂停 A02、先完成本地仓库治理，再从 `20260715-175826` 双层恢复点继续。因此本阶段对 A02 业务语义仍是旁路治理，但在本次恢复顺位中临时成为恢复门禁；它不得改写 Phase 1-7 的先迁移史馆顺位，也不得借治理仓库读取 pending body 或修改安装根。唯一恢复例外是：保护锚点若缺失，只能从已验证快照原字节恢复到原路径并复核原 SHA-256，不能生成新内容或改变其基线。

参考技能固定为 `$github-init` 与 `$github:github`。它们只用于本地结构、检查清单和 GitHub-ready 语境；本阶段始终 `remote/push/tag/release/publish=NOT_RUN`。

- [x] 建立 `D:\project` 根控制 Git 仓库；本地基线 `58cd9f9`，项目级边界补充 `de715f3`，root remote count `0`、index clean。
- [x] 根仓库只跟踪控制面、治理文档、模板、canvas page 和选定 evidence metadata；child repos、真实 release/recovery/staging bodies、实时 `.codex/config.toml`、`.repo-control` 与 `worktrees` 均明确忽略并由 `inventory/workspace-assets.json` 治理。
- [x] `workspace.yaml` 使用 schema 驱动任意新增子项目；`repo-control` 不硬编码 Court/UU，可通用创建、绑定、列举、doctor 和资产 inventory。未来新项目只新增 manifest object，不改控制器路由代码。
- [x] 禁止 submodule/普通 nested tracking；每个 child worktree 只连接目标子仓库 common-dir。状态使用 `.repo-control/state/<project>/<task>.json` 与每事件独立 JSON，不使用共享可损坏 `tasks.json`。
- [x] 用唯一新增 Codex 根项目 `D:\project` 创建可见验收任务 `019f6585-fa75-7ec0-98dd-1011401b3dbe`；无需重新登记 UU 项目。任务壳 `C:\Users\32893\.codex\worktrees\30b2\project` 只作显示/控制，项目级真实工作树 `D:\project\worktrees\uu-remote-cli\root-ui-smoke-20260715` 仅连接 `D:\project\uu-remote-cli\.git`，root/main/child 三个 staged diff 均空。
- [x] 不修改 Codex 全局 managed-worktree 设置；`D:\project\worktrees` 只约束本项目真实 child code worktree。
- [x] `repo-control doctor=PASS`，标准库测试 `7/7 PASS`，`github-init inspect` 确认根仓库有提交、无 remote、无 tracked sensitive path。
- [x] 完成并复核两个最小 GitHub-ready 本地治理分支并分别集成到独立 `main`：Court `b7b2b440cb53bdc26ba53af676ef9c75f070183a`，UU `cb43a2d92acfed3030af00546b1d0056b90469ec`；两个子仓库 remote count `0`、index clean。
- [x] 刷新根项目版本/分支台账和资产 inventory；root `8d6b056412395c3dcd12fab5733b0d55cdb22f88` 的 `doctor=PASS`，Court=`beta0.5.9`、UU=`0.0.1`，并保留 Court `work/a02-baseline` 历史敏感信息发布阻断，禁止 push/mirror 该 ref。
- [x] 四个受保护史馆锚点一度在原路径缺失；仅从本机 `legacy-snapshots/20260715-active-root-generated-indexes` 逐字节恢复到原路径，恢复后长度与四项基线 SHA-256 全部精确匹配。未重新生成、未移动快照、未读取 `pending/**`。
- [x] 恢复包重新自校验 `92/92 PASS`，checkpoint SHA-256=`740C42C3021435794B02AFF3CFCEFF7C69755B6B2E0A92D1632DDCA092CC8060`；25 个参与 worktree 已各有独立 metadata-first 史馆实录，形成 25 个 archive、25 个有效 index JSONL entry、25 个唯一 `worktree_trace_id`，必要字段无缺口。主线另以 `rg --files` 验证 25 worktree `.pyc=0`、全部 index 为空，四保护锚点仍为原哈希；root closeout=`b3eada2a62922a9cd4a3538e6713c82565f5ea54`。门下裁定 `PHASE8_REPOSITORY_GOVERNANCE_VERDICT=PASS`、`A02_PHASE1_RESUME=ALLOWED`；现从原 task/恢复点继续 Phase 1，不把 workspace ledger 当史馆实录。

本阶段基础治理完成条件已满足。最新用户要求把仍位于 Codex 全局存储的 A/B/G 活跃 child worktree 迁入项目级物理根，因此追加 8.3 补充门禁；它只重新打开工作树移交，不推翻已通过的仓库架构、GitHub-ready、保护锚点或恢复包裁定。8.3 通过后立即恢复 A02，不继续做低边际价值治理。

## 5. 确认后的并行编排

### 三省会审波

- 中书省：验收标准、RED 拆解、非目标。
- 门下省：硬门禁、风险、complexity budget、最终审计。
- 尚书省：依赖图、文件所有权、六部执行波、共享写入序列。

专项发现不得交给一个宽泛 reviewer。默认并行 A-G 只读专项：A 重复/冗余，B 模糊语义，C 冲突语义，D 脚本/CLI，E 功能/实现可达性，F 测试与可恢复性，G 安全/隐私/发布/跨平台。可按证据价值增减专项，但每个 reviewer 写集必须为空。

每项 finding 统一输出：`finding_id, specialty, severity, confidence, source_path/line, conflicting_path/line, observed_behavior, expected_contract, minimal_RED, proposed_fix_scope, owned_paths, dependency, false_positive_notes`。门下是唯一 adjudication aggregator，负责跨专项去重并裁定 `ACCEPTED|REJECTED_FALSE_POSITIVE|DEFERRED|SUPERSEDED`；尚书只把 `ACCEPTED` findings 按依赖/写集组成 repair clusters，再派发给单一 owner。

### 六部/工匠执行波

在三省上奏和太子回奏 `APPROVED` 后执行：

- 兵部/工匠：迁移 gate/cutover 实现与并发静默策略。
- 工部/工匠：current-tool installer、relative preload、runtime resume、pinned load 的代码和测试；按文件所有权再拆分。
- 户部：真实路径、版本、容量、工件哈希与安装资源验证。
- 吏部：14 官署 profile/dossier 重生成、exact AGENTS.md preload 完整性，以及能力官籍账册的事件驱动刷新、验证、去重和失效标记。
- 礼部：README/docs/logs/INSTALL-PROMPT/release 文案，严格基于已验证事实。
- 刑部：迁移、junction、隐私、rollback、未授权工具和包排除的执行风险测试。
- 史馆：阶段证据与最终完整结诏；不作为六部执行者。

并行规则：独立文件可并行；六部可按同 role 独立 shards 优先扩容；同一文件只允许一个 writer；迁移切换、Obsidian、安装、打包由单一工匠按尚书顺位执行。太子始终唯一，尚书多开仅限获批的超级巨型任务。

## 6. 新增与既有门禁

```text
confirmation_gate
taizi_pre_spawn_resource_budget_gate
no_max_then_interrupt_gate
wave_budget_reassessment_gate
hierarchical_budget_pool_gate
parent_envelope_no_oversubscription_gate
allocated_lease_no_blind_termination_gate
budget_return_on_completion_gate
complexity_budget_gate
user_explicit_complexity_boundary_gate
git_index_empty_gate
protected_cross_conversation_files_gate
pending_body_no_read_gate
pending_body_zero_before_cutover_gate
two_stable_zero_active_scans_gate
source_inventory_unchanged_gate
target_under_agents_gate
single_physical_shiguan_gate
same_volume_atomic_relocation_gate
junction_target_and_rollback_gate
migration_run_owner_lock_gate
migration_inventory_scope_identity_gate
migration_receipt_terminal_state_gate
migration_live_consumer_revalidation_gate
windows_migration_root_reparse_gate
relative_persisted_path_gate
pinned_initial_semantics_gate
exact_agent_dossier_load_gate
office_responsibility_load_gate
registered_capability_first_gate
capability_registry_staleness_fallback_gate
libu_hr_capability_registry_maintenance_gate
no_unbounded_skill_rescan_gate
office_minimal_preload_gate
office_role_local_load_gate
office_direct_adjacency_gate
office_on_demand_reference_gate
office_preload_measurement_gate
office_escalation_full_load_gate
pure_skill_runtime_baseline_gate
no_plugin_dependency_or_artifact_gate
shangshu_six_ministries_hierarchy_gate
ministry_craftsman_hierarchy_gate
no_hierarchy_bypass_gate
single_taizi_gate
canonical_authority_uniqueness_gate
office_worker_instance_identity_gate
same_role_parallel_affinity_gate
default_parallel_16_gate
current_explicit_parallel_count_or_unlock_gate
parallel_override_provenance_gate
parallel_override_no_budget_bypass_gate
assignment_ownership_and_write_set_gate
single_integration_owner_gate
super_giant_shangshu_scale_gate
super_giant_scale_reassessment_gate
system_memory_pressure_downgrade_gate
resume_correction_same_task_gate
semantic_epoch_equals_charter_revision_gate
semantic_invariant_capsule_gate
semantic_dispatch_result_binding_gate
semantic_correction_full_revocation_gate
semantic_stale_result_quarantine_gate
semantic_compaction_resume_verify_gate
semantic_drift_detector_gate
semantic_receipt_multisource_consistency_gate
semantic_guard_cross_platform_recovery_gate
semantic_guard_performance_gate
current_tool_only_install_gate
no_unrequested_tool_gate
host_memory_projection_authority_gate
codex_update_note_contract_gate
memory_ingestion_verification_gate
shared_shiguan_git_repository_gate
record_memory_same_repo_separate_lifecycle_gate
shiguan_git_tracking_allowlist_privacy_gate
shiguan_git_append_only_record_gate
shiguan_git_single_writer_clean_index_gate
shiguan_git_no_remote_gate
native_memory_no_migration_gate
native_memory_git_repository_gate
native_memory_git_no_remote_mutation_or_use_gate
native_memory_repo_open_tool_class_gate
native_memory_repo_scoped_stage_clean_index_gate
cross_repo_commit_link_receipt_gate
shared_hub_native_repo_bidirectional_link_gate
installed_tool_memory_projection_eligibility_gate
runtime_controller_install_receipt_gate
install_state_evidence_order_gate
installed_tool_memory_namespace_gate
installed_tool_pinned_shiguan_link_gate
shiguan_namespace_reverse_memory_link_gate
memory_link_managed_block_idempotence_gate
migration_links_verified_gate
tool_class_memory_graph_isolation_gate
memory_projection_metadata_only_gate
memory_source_authority_and_scoped_write_gate
blank_host_memory_probe_before_write_gate
memory_probe_evidence_and_user_prompt_gate
unknown_memory_state_fail_closed_gate
no_unrequested_tool_memory_mutation_gate
blank_host_config_reminder_only_nonblocking_gate
config_change_newest_explicit_authority_gate
config_controller_source_of_truth_first_gate
ccswitch_target_block_proof_and_transaction_gate
codex_dual_toml_semantic_compatibility_gate
config_secret_provider_unknown_key_preservation_gate
config_uncertainty_no_mutation_gate
effective_config_reread_parse_gate
no_db_only_or_leaf_only_acceptance_gate
skill_behavior_source_of_truth_gate
memory_not_behavior_implementation_evidence_gate
semantic_adjudication_three_layer_gate
memory_decision_menxia_receipt_gate
append_only_memory_supersede_gate
specialist_review_fanout_gate
menxia_unique_aggregator_gate
repair_cluster_tdd_gate
full_repository_audit_gate
full_audit_remediation_branch_gate
local_only_audit_commit_gate
no_empty_audit_branch_gate
child_office_trace_summary_gate
obsidian_cas_preserve_only_gate
package_privacy_gate
deterministic_run1b_run2b_gate
SPEC
QUALITY
whole_insertion_acceptance
phase_level_tdd_review_gate
workspace_root_non_publish_gate
child_repository_publication_unit_gate
workspace_control_nonblocking_gate
no_nested_repository_tracking_gate
worktree_shiguan_record_gate
worktree_trace_identity_gate
worktree_terminal_disposition_gate
taskpoint_pointer_not_authority_gate
taskpoint_capsule_hash_runtime_binding_gate
taskpoint_role_superior_worktree_lease_gate
taskpoint_preload_ack_before_running_gate
taskpoint_correction_revocation_gate
taskpoint_code_collision_path_sort_gate
taskpoint_context_break_even_privacy_gate
taskpoint_no_second_authority_store_service_gate
office_carrier_equivalence_gate
worktree_thread_dispatch_communication_gate
carrier_single_authority_writer_gate
supercc_experimental_cli_disclosure_gate
supercc_explicit_enable_only_gate
supercc_semantic_annex_no_load_when_disabled_gate
court_operation_idempotency_gate
decree_lineage_freeze_gate
record_uid_collision_gate
archive_closeout_saga_recovery_gate
runtime_event_archive_compound_receipt_gate
office_carrier_lifecycle_isomorphism_gate
authority_realm_root_fingerprint_gate
local_filesystem_only_fail_closed_gate
```

任何门禁失败都停止后续依赖阶段，不用太子代工，不用额外抽象绕过。

额外立即停止条件：迁移未完成就尝试既有宿主投影；install projection/manifest 缺失、歧义、不能证明 skill installation 或把工具集合锁死为三类；任何跨工具 namespace/node/edge 合并；原生记忆被迁移/复制、未形成独立 Git 仓库、出现 remote/submodule/subtree/nested tracking、暂存无关 dirty path、缺少 repo/pathspec/HEAD/write-policy 或 paired-link receipt；任何超出 managed block/tool-native/current-tool-approved path 的 memory body 改写或 release-package 纳入；空白宿主在只读 probe 与用户提示前发生 shared-root、任何 Git init、memory-enable 或 install 写入；`unknown` 被自动启用；对 Claude/Hermes/other 做超出已批准原地 Git/pinned link 的未授权安装、配置、启用、正文写回；真实配置/controller preimage、CC Switch DB/sidecar/backup、provider/auth 值进入日志、fixture 或包。

配置分支的局部停止语义：若 controller ownership、DB schema、effective precedence、current values、兼容语义、backup/rollback、实际文件 reread/parse 或可用 runtime probe 不能证明，立即停止或回滚该配置分支，报告精确不确定项并输出 `REMINDER_ONLY`/`compliance_claimed=false`；其他互不依赖任务继续。只改 leaf TOML 或只验证 DB 永不构成合规。

编号/谱系分支立即停止条件：同一 operation 产生第二副作用；`record_uid` 碰撞；decree-open 重分配或历史 `court_code` 被改写；child/worktree lineage 漂移；task/event/archive/index receipt 分叉；worktree lifecycle 缺失；authority realm/root fingerprint 不匹配；运行于跨主机、NFS、SMB 或需要 distributed lock 的文件系统。此时返回稳定 `BLOCKED|UNSUPPORTED` reason code，只允许同一 `operation_id` 的只读 reconcile/恢复，不得另建 ledger、SQLite、HTTP/MQ service 或绕过 Git/Codex authority。

## 7. 最终验收命令族

```powershell
python -B scripts/check_shiguan_migration_gate.py
python -B scripts/quick_validate.py .
python -B scripts/check_catalog.py --strict
python -B scripts/check_portability.py
python -B scripts/check_install_prompt.py
python -B scripts/check_install_current_agent_copy.py
python -B scripts/check_court_office_assignment_binding.py
python -B scripts/check_court_intake_gate.py
python -B scripts/check_court_runtime.py
python -B scripts/check_court_capability_recruitment.py
python -B scripts/check_semantic_continuity.py --json
python -B scripts/check_court_memory.py --json
python -B scripts/check_full_repository_audit.py --json
python -B scripts/check_package_privacy.py
python -B scripts/release_payload_manifest.py --check --json
git diff --check
git diff --cached --name-only
```

最终必须同时得到：

```text
RED demonstrated
GREEN passed
SPEC PASS
QUALITY READY YES
COMPLEXITY BUDGET PASS
one physical shared Shiguan under .agents
protected files unchanged
Claude/Hermes skill, config, and memory bodies unchanged outside the approved pinned managed block and local Git metadata
run1b == run2b
single Taizi; canonical authorities unique
same-role workers traceable and write sets disjoint
pure Shiguan pointers cannot authorize execution; the hybrid envelope/capsule path is hash-bound to the current runtime revision and acknowledged before running
canonical court_code is unchanged; task-point sequence/revision/attempt are independently traceable and revoked revisions/attempts cannot reactivate
semantic_epoch equals charter_revision and the current invariant capsule/charter hashes bind every dispatch, result, apply, commit, resume, and closeout
correction revokes every stale binding/agent/capsule/attempt, returns to ThreeDepartments, and quarantines late results
compaction/resume/reboot/long-idle and multisource plan/Git/recovery evidence pass the same semantic receipt verification
SEMANTIC_CONTINUITY_GUARD PASS with cross-platform recovery and local verify p95 <250 ms
task-point false accept, post-revoke activity, unauthorized scope escape, and duplicate execution are all zero
with at least 30 fixture/accepted samples, capsule resolve+read+hash+binding p95 is <=1000 ms; every context-saving claim includes chars and UTF-8 bytes and satisfies the 80% break-even rule
task-point capsules exclude pending/private bodies, full prompts/diffs/private logs and add no plugin, daemon, database, second store, or authority
child_agent and worktree_thread carriers use equivalent dispatch/communication/result bindings without duplicate authority or writer
decree-open allocates one immutable main_court_code per decree; only explicit reclassify advances lineage_version and historical court_code values remain unchanged
default 16 means root plus 15 children, explicit 17 means root plus 16 children, and explicit 18 means root plus 17 children; explicit counts are never reinterpreted as child slots
32 concurrent allocator calls preserve uniqueness and 32 replays of one operation produce exactly one allocation/archive/index/task/event side effect
allocation, archive, index, task, and event killpoints recover exactly once through PREPARED -> ARCHIVE_COMMITTED -> TASK_EVENT_COMMITTED and closeout-recover --operation-id
two child_agent plus two worktree_thread fixtures have isomorphic admit/start/report/finish/close schemas; worktree adds only thread_id/worktree_fingerprint/branch/start_head proof
authority realm/root mismatch fails closed on Windows/macOS/Linux local filesystems; cross-host/NFS/SMB/distributed-lock operation is explicitly DEFERRED or UNSUPPORTED
operation and dispatch context contains only hashes, relative paths, and evidence pointers, with no full prompt/diff/private/pending body
superCC is disclosed as EXPERIMENTAL_CLI_ONLY, activates only from the newest explicit superCC choice, and no superCC annex/runtime semantics load while disabled
Decretum Matrix（诏令矩阵） is the single canonical user-facing skill identity; decretum-matrix is the canonical skill name, DecreeMatri is absent from current identity surfaces, and every remaining court-capability-router occurrence is allowlisted as a technical locator, history, or deprecated compatibility input
host MEMORY.md not directly rewritten
semantic_adjudication, write_authority, and native_application are independently evidenced
every WRITE has adjudication_status=approved, decision_id, menxia_receipt, transaction_id, and verified native application
historical memory decisions are append-only; corrections supersede instead of rewriting
specialist findings use the common schema and only Menxia issues the aggregate adjudication
FULL_AUDIT_PASS or FULL_AUDIT_REMEDIATION_COMMITTED_LOCAL
any audit remediation commit remains on the applicable child release branch; only a later Section 3.2 receipt may authorize exact previous-version remote actions
one local Git repository versions the shared Shiguan records and memory layers without creating a second shared store or remote
records and memories share the repository but keep distinct schemas and lifecycles; committed records are append-only and memories retain evidence/commit lineage
only allowlisted sanitized records, memory decisions/shared memory, per-tool projections, manifests, and Obsidian derived views are tracked; runtime/pending/private/config/package data is absent
every active_verified or installed_verified tool in the open tool-class set keeps its native memory path and is managed as an independent Git repository, with no migration, shared-repo body copy, submodule, subtree, or nested tracking; new repos have no remote and existing tool-owned remotes are preserved but never changed or used
the shared Shiguan Git repository links every native memory Git repository through one stable registry entry and reciprocal pinned link; repo ids, namespaces, pathspecs, commits, and transaction ids match on both sides
each native memory repository has a Shiguan registry receipt for repo/pathspec/HEAD/state/write policy; unrelated dirty paths are never staged and all affected repository indexes are clean after a linked checkpoint
install receipts are runtime/controller/effective-loader/hash/probe derived rather than static; active_verified and installed_verified tools each have an isolated namespace even when memory is empty
every active_verified or installed_verified native memory has one pinned Shiguan link and each Shiguan tool namespace has a verified reverse source link
physical CUTOVER_VERIFIED is not overall migration acceptance until every eligible tool passes MIGRATION_LINKS_VERIFIED; an exact per-tool blocker prevents false success but does not satisfy the gate
every manifest-eligible installed tool class has an isolated Obsidian metadata/index graph with no cross-tool nodes or edges
native memory sources remain tool-authoritative; outside the pinned managed block, tool-native writes, and separately approved current-tool update-note, Shiguan does not rewrite bodies; projections contain relative source ids/paths, repository HEADs, fingerprints, states, headings/topics/relations only
blank-host detected/selected tools are probed read-only before shared-root/Git/init/enable/install writes, with enum state, native-path/Git evidence, user prompt, unknown fail-closed, and no Claude/Hermes/other mutation beyond the approved in-place Git/pinned-link contract
blank-host config targets are codex|claude-code|hermes|other:<stable-id>; unmet, unauthorized, or uncertain standards yield nonblocking REMINDER_ONLY with no compliance claim
authorized Codex config is controller-aware/reversible, preserves secrets/provider/unknown keys, keeps config.toml and managed_config.toml semantically compatible, and passes on actual-file reread/parse plus an available runtime probe, never DB alone
packages exclude actual host configs, controller DB/sidecars/backups/journals/dumps, config preimages, and provider/auth values
all amended behaviors reachable from SKILL.md and behavior-tested; MEMORY.md is not implementation evidence
every child has a compact time-event-action trace
every participating worktree has a separate metadata-first Shiguan record with identity, write-set, verification, and terminal disposition
routine office loading meets the minimal contract through the pure Skill path, with measured role-local/on-demand loading and no plugin dependency or artifact
Git index empty
```

## 8. 当前执行态

- 用户已批准提案 A-D，并明确下达：`确认执行 CCR-R2-SHIR-20260714-A02`。
- goal 模式恢复；Phase 0 已完成，`CCR-R2-SHIR-20260714-A02-P05-TB01` 已用早于 child start 的真实资源证据通过，Phase 1 RED 仅按批准的 6 席继续。
- 当前已知 pending-body 硬门禁仍有效；确认执行不等于授权读取、哈希、移动、删除或 mark-seen pending 正文。
- Phase 1 首次门下复核的 memory-state 缺口已修正并局部复核通过；因新增“能力官籍优先/吏部主动维护”范围，旧阶段批准被标记为 `REVIEW_SUPERSEDED_BY_SCOPE_ADDITION`，须补 RED 后再做一次阶段级复核。
- 最新 Obsidian MEMORY/memories 分工具图谱与空白宿主只读 probe 范围同样属于 Phase 1 RED correction；补齐上述第 7/8 项 RED 并完成新的阶段级复核前，不得沿用旧批准进入 GREEN。
- 最新“实录与长期记忆同一共享 Git 仓库、分 schema/lifecycle 托管”、开放工具集合的原生记忆库保留原路径并各自以独立 Git 仓库由史馆原地托管、runtime/env/CC Switch/effective-loader 驱动安装收据、以及每个已验证安装工具的置顶史馆链接/史馆反向链接同属 Phase 1 RED correction；本次只修计划，不授权现在初始化任何史馆/工具记忆 Git、迁移工具记忆、读取 pending、实际改写任何工具记忆或变更 controller/config。
- 最新空白宿主 controller-first 配置语义同属 Phase 1 RED correction；补齐第 12 项 RED 并重新完成阶段级复核前，不得进入 GREEN。它不授权当前主机配置变更，且 `REMINDER_ONLY` 不阻断无关工作或代表合规。
- 若 pending 保持非零，必须在迁移前停在 `WAITING_FOR_PENDING_BODY_AUTHORITY`，不得继续 Obsidian、安装、打包或父 Task 3。
- 全程执行上下文压缩恢复锚点、复杂度预算、性能降级、逐子官署轻量追溯和 Git index 空门禁。
- Phase 8 已通过并清除临时暂停：root control、单项目可见任务、项目级 child worktree、Court/UU GitHub-ready 集成、根版本台账、四保护锚点原字节恢复、恢复包 `92/92` 和 25 条逐 worktree 史馆实录均已验收；门下裁定允许恢复既有 A02 Phase 1。父 Task 3 仍须等待 A02 的 RED/GREEN/SPEC/QUALITY/整体验收。
- Phase 8 使用 `$github-init` 与 `$github:github` 作为本地治理参考；当前始终禁止远程/connector 写入/publish。`D:\project` 根控制仓库永不发布，未来只逐个发布经另行授权且已验收的独立子仓库。
- 新增 `worktree_shiguan_record_gate`：当前所有 A02 worktree 必须在集成/保留/退役前逐一 backfill 独立史馆实录；child 简记或 workspace 台账不能代替。该 backfill 不解除 pending_count=69 门禁，也不得读取 pending body。
- 中书插件适配审查已由最新用户裁定收口为 `PURE_SKILL_REQUIRED`：保留最小官署加载合同，取消插件化实施/A-B/后置验收，不创建 plugin artifact；专项计划见 `docs/plans/2026-07-15-court-office-selective-loading-remediation-plan.md`。
- 中书任务点审查以 `confidence=0.87` 裁定 `RECOMMEND_AND_INSERT`；已按用户预授权插入 hybrid envelope + immutable/hash-bound Shiguan capsule 计划。当前只更新计划，尚未实施；Phase 1 仅可使用临时 fixture，真实记录继续受迁移优先与 pending-body 门禁约束。
- A/B/G 项目级 worktree 已完成本轮串行吸收边界：Lane A 四文件 SHA `4/4` 且 migration gate `22/22 PASS`；Lane B 四文件 SHA `4/4` 且两个离线 self-test PASS；Lane G 当前只吸收 20-role active lease/requested-bindings checker hunk，主树 `court_runtime.py` 与 concurrency checker 保留原 SHA，剩余 ledger core 严格留待 Phase 1.5。全程 index empty、diff-check PASS、no-pyc，pending body access 未运行；这仍不等于 Phase 1 整体 GREEN/SPEC/QUALITY。
- 最新 `CCR-A02-MEMORY-ADJUDICATION-PARALLEL-AUDIT` 已并入唯一主线：V2 当前 RED 前像为 `entries=1033`、`changed_candidates=493`、`A02_RED_EXPECTED_FAILURES=43`；Proposal B 统一为 `APPROVED/ACTIVE`，后续按 A-G 专项只读 fan-out、门下唯一聚合、repair-cluster TDD 与 Phase 9 最终全仓审查执行。
- 最新 Semantic Continuity Guard 已作为计划/RED 并入，不是 production GREEN：当前 `create_task/correction/resume/agent_finish/compression/task-point/CLI/archive` 尚未形成统一机器闭环；不得凭本计划、现有 fixture 或 semantic reload 文案声称已实现。
- 最新史馆 CLI 多对话编号/谱系合同已并入计划；当前 `RC1=APPROVED`、`RC5 core=APPROVED`，完整 runtime 仅外部 RC4 `office-bound-wave` 保持 RED，RC5 rollout identity debt 尚待清偿，Phase 1 仍非整体 GREEN。
- 记忆索引当前为 `PROJECT_MEMORY_CONTENT=PASS`、`GLOBAL_MEMORY_INDEX=FAIL_PENDING_INGESTION`；本轮只更新计划，实际 append-only superseding note、root wording 和 ingestion verification 留待 RC3/Phase 8 root writer。

### 8.1 Phase 1 单写者集成前恢复与预算裁定（2026-07-15）

- `CLUSTER_A_SPEC_QUALITY` 的一次性门下裁定位于内部复核任务 `/root/menxia_h_respec_w4`，结果为 `CLUSTER_A_SPEC_QUALITY_PASS`；Cluster B 对应结果为 `CLUSTER_B_SPEC_QUALITY_PASS`。二者仅证明组件 lane 可进入受控集成，不等于 Phase 1 整体 GREEN/SPEC/QUALITY 已通过。
- 集成前两层恢复点已完成：context-save 文件为 `C:\Users\32893\.gstack\projects\court-capability-router-beta0.5.10\checkpoints\20260715-141949-a02-pre-phase1-integration.md`，SHA-256 `35DD4373F7CD18DA552E3B8B5297111B742CDB2349BD3DBED36674FACF347BF8`；外置恢复包为 `D:\project\recovery-points\CCR-R2-SHIR-20260714-A02-20260715-141949-pre-phase1-integration`，`validation-report.json` 为 `OVERALL=PASS`，`SHA256SUMS.txt` 自校验 102 项且 SHA-256 为 `42520EE6845D74BF06DB0C5C8BC41485891CC7224354C5719E4754BF1FA68A76`。13 个捕获 worktree 的 index 全为空，pending body 未进入任何归档。
- 本 wave 启动前实测：物理内存总计 `31.90 GiB`、空闲 `7.91 GiB`、使用率 `75.20%`，系统进程 `633`，Codex/Node/Python/PowerShell 相关进程 `183`。未达到约 `99%` 的性能降级条件，但也不把硬件余量误当成共享文件可并写授权。
- 太子批准动态预算池：太子决策与回滚 reserve `15%`，门下最终阶段复核 reserve `15%`，尚书→工部单一集成 writer lease `45%`，户部只读阶段进度监视 `5%`，未分配缓冲 `20%`。lease 编号 `CCR-R2-SHIR-20260714-A02-P1-INT-W1`；同时写者上限为 `1`，原因是 `SKILL.md`、registry、runtime、Shiguan reference/checker 存在明确跨 lane 重叠，而非子 agent 数量或固定并行硬上限。
- 该 writer 必须先完整加载当前根 `SKILL.md`、尚书/工部对应 `AGENTS.md` 与 profile，再按中书集成图执行；直属链固定为 `太子 -> 尚书 -> 工部 -> integration worker`。只可写 `D:\project\court-capability-router-beta0.5.10` 的已批准 Phase 1 集成写集；不得修改其他 worktree、真实配置、安装根、受保护史馆文件或 pending body。
- 已分配 writer 除非完成、明确失败或触发 stop condition，不盲目中断。任何 batch 前后均须保留 preimage/reverse-patch 锚点、`git diff --check`、index-empty 与 no-pyc 证据；集成结束后再做一次全阶段 RED/GREEN、SPEC、QUALITY，禁止逐微点反复开审。
- U0 首批固定先于 A/B 集成：已用三个 fixture checker 证明 default 16、最新明确 count/unlock override、旧来源 fail closed、99% 降级、budget lease 不可绕过和配置显式 count 兼容；该批通过并形成 reverse anchor 后才恢复原 A/B 顺位。
- U0 实际结果为 `GREEN=PASS`：budget/dispatch/config 三 checker 均 RC 0，默认 whole-tree 16（root-only 时 child 15）、最新明确 count/unlock 可到 17、预算仅批 5 时仍只选 5、配置默认 16 且显式 48 保留；`git diff --check`、index-empty、no-pyc 与 17/17 postimage archive 均通过。恢复证据见 `D:\project\recovery-points\CCR-R2-SHIR-20260714-A02-20260715-141949-pre-phase1-integration\batches\EXTENSION-MANIFEST.md`，batch `SHA256SUMS.txt` 自校验 27 项；现恢复原 A/B 集成顺位，整体 Phase 1 SPEC/QUALITY 仍未裁定。

### 8.2 Phase 1 可见 worktree 分支并行（2026-07-15）

- 用户澄清本轮“分支”专指保存项目 `D:\project\court-capability-router` 下、在 Codex 左侧任务栏可见的 worktree 分支对话；隐藏 collaboration 子 agent 不作为该分支执行面。此前两批隐藏任务均停在只读 PRELOAD，写入数为 `0`。
- 重启后资源复测为 16 个逻辑处理器、物理内存 `31.90 GiB`、空闲 `17.04 GiB`、使用率 `46.58%`。太子据此批准 W4 三席预算池，已分配席位在完成前不盲目回收；未批准先最大启动再中断多余任务。
- 三个可见分支均从既有 ref `release/beta0.5.10` 的 `040f707e5acc7c12cfcf50afcfc111a7e49a2f00` 创建为独立 detached worktree：Lane A `019f6527-0396-7bc2-a24b-a7d7e20b6daf` / `dc8b`，Lane B `019f6527-03af-7fc0-91f3-1d6d0e5cf2ee` / `26c0`，Lane G `019f6527-039d-7582-964c-bf962fa4dafe` / `9455`；三者已置顶并处于 active。
- Lane A 仅写 4 个 migration 文件；Lane B 仅写 registry/dispatch 的 4 个非 `SKILL.md` 文件；Lane G 仅写 `court_runtime.py` 与两项 runtime checker。各分支不得写主恢复点、其他 worktree、真实配置、安装根、受保护史馆文件或 pending body，且始终保持 index 为空。
- 分支产出只作为可串行吸收的 unstaged diff。主线必须先核验写集、测试、`git diff --check`、index-empty、no-pyc，再逐分支串行吸收；分支通过不等于 Phase 1 整体 GREEN/SPEC/QUALITY 通过。

### 8.3 A/B/G 项目级 child worktree 物理根移交（PASSED）

- 本补充必须在 A/B/G 的任何新业务写入之前完成。Codex 可见任务壳继续由唯一根项目 `D:\project` 管理并可保留在 Codex 自身全局存储；实际 Court 代码工作树必须位于 `D:\project\worktrees\court-capability-router\<task>`，且只连接 `D:\project\court-capability-router\.git` common-dir。不得把 child 内容纳入根 Git、submodule、subtree 或全局配置。
- 迁移来源固定为 Lane A `C:\Users\32893\.codex\worktrees\dc8b\court-capability-router`、Lane B `C:\Users\32893\.codex\worktrees\26c0\court-capability-router`、Lane G `C:\Users\32893\.codex\worktrees\9455\court-capability-router`。每路先记录 source path、HEAD、common-dir、branch/detached、status、index、untracked、批准写集与文件 SHA-256；禁止先删除来源或以复制覆盖掩盖差异。
- 使用根 `repo-control` 的受检 relocation 路径：为每路绑定唯一 `work/a02-lane-a|b|g` 分支，目标分别为 `D:\project\worktrees\court-capability-router\CCR-R2-SHIR-20260714-A02-lane-A|B|G`。同卷使用 Git 原生 linked-worktree move；本机 `C:` 到 `D:` 的跨卷迁移使用受检目录 move，随后立即执行 `git worktree repair`，再做 pre/post fingerprint 判等并原子写 `.repo-control/state/<project>/<task>.json` 与独立 event。失败时保留旧路径或已落地的新路径与事件证据，不做自动清洗。
- 冻结令到达前 Lane A 已形成 `scripts/migrate_shared_shiguan.py`、`scripts/shiguan_paths.py`、`scripts/check_shiguan_migration_gate.py`、`scripts/shiguan_migration_gate.py` 四文件产物，Lane B 已形成 `references/court-capability-registry.md`、`references/court-offices-dispatch.md`、`scripts/check_capability_index_gate.py`、`scripts/refresh_capability_registry.py` 四文件产物，Lane G 已形成 `scripts/court_runtime.py`、`scripts/check_court_runtime.py`、`scripts/check_court_runtime_concurrency.py` 三文件产物；三路均只允许这些批准路径的 unstaged diff 随同一 linked worktree 原位迁移。迁移前后要求 HEAD、common-dir、文件 SHA-256、`git diff` 摘要、untracked 集合和 index 状态等价；不得 stage/commit/stash、不得运行 `Copy-Item`/`git apply` 重放差异。
- 三个新路径就绪后，在根项目 `D:\project` 创建三条新的可见 Codex task shell，并各自通过 `attached/court-capability-router` 绑定对应 child worktree。旧 A/B/G 对话只接收带新 task/path/state 的移交通知并停止写入，不再作为执行面；不得同时让新旧两路写同一 lane。
- 迁移后为每路追加 metadata-first 史馆 relocation/terminal-disposition 记录，引用原 `worktree_trace_id`、旧/新路径、同一 common-dir/HEAD、分支、index/no-pyc 与验收结果，不复制 prompt/diff/body，不读取 `pending/**`。旧记录保持 append-only，不因路径变化回写或删除。
- `WORKTREE_ROOT_HANDOFF_GATE=PASS` 仅在以下全部成立时签发：三个物理路径均在项目级根；三个 common-dir 唯一指向 Court 子仓库；三份 state/event 与三条可见根项目任务对应；A/B/G 各自批准差异等价；root/Court/三 worktree staged diff 全空；`repo-control doctor` 与测试通过；无 `.pyc`、remote、publish 或 pending-body access。通过后恢复 8.2 的 A/B/G 执行顺位。

实际结果：`WORKTREE_ROOT_HANDOFF_GATE=PASS`。

- 根控制器新增并验证 `relocate`、`adopt`、`refresh` 三个窄接口；同卷迁移、staged-source fail closed、修复后 adopt 与状态 fingerprint 均有测试，最终标准库测试 `10/10 PASS`，`repo-control doctor=PASS`。根仓库改动保持 unstaged，root remote count `0`。
- Lane A 新物理路径为 `D:\project\worktrees\court-capability-router\CCR-R2-SHIR-20260714-A02-lane-A`，分支 `work/a02-lane-a`。首次跨卷 move 在复制完成后因旧 Codex 终端句柄无法删除空源壳而停止；随后只对已完整落地的新路径执行 `git worktree repair`，四个文件与可信 `8f14` 源 SHA-256 `4/4` 精确相同。新可见 root task=`019f6614-3d34-7353-881a-da0756f2530f`，shell=`1fb8`，fingerprint `unstaged_diff_sha256=734c0c69464b0f41c7df5e0505a76a1bfb49932fa749fc2fe41429f6c0db2032`。
- Lane B 新物理路径为 `D:\project\worktrees\court-capability-router\CCR-R2-SHIR-20260714-A02-lane-B`，分支 `work/a02-lane-b`。旧 `26c0` 在 `HANDOFF_READY` 后随 Codex archive 生命周期被回收；恢复未凭描述重建，而是逐项读取原 session JSONL 的成功 `apply_patch` 输入/输出，并在新工作树按原顺位重放。四个最终 SHA-256 与旧 task `4/4` 精确相同。新可见 root task=`019f6614-3d69-7420-8227-d1f34ca43ea3`，shell=`7c48`，fingerprint `unstaged_diff_sha256=39986781f504ac863ea43d11d409cc41243fe3e66ea44500330d2cd448e70c8b`。
- Lane G 新物理路径为 `D:\project\worktrees\court-capability-router\CCR-R2-SHIR-20260714-A02-lane-G`，分支 `work/a02-lane-g`。旧 `9455` 回收后严格使用已封存且在 `SHA256SUMS.txt` 内的 `visible-lane-g-9455.patch`，仅通过内置 `apply_patch` 分 hunk 恢复；生成 diff 与恢复补丁归一化长度均为 `158422`，SHA-256 均为 `4585F1675893C3FF9F1D56AFBB616D28EC588850D7784708AB84DD49003C9A3A`。新可见 root task=`019f6614-3d76-7502-844f-fcae22a3cb6f`，shell=`87e7`。
- 三个 root task shell 均通过 `attached/court-capability-router` Junction 指向各自 D 盘 child worktree，并独立回报 `ATTACH_READY`；root shell/child/main/A02 九个 index 均空，三路 `git diff --check=PASS`、`.pyc=0`、unapproved changed path `0`。
- 三条 append-only 史馆 relocation 记录已写入并各在共享 index 中唯一出现一次：A `WT-42203FC82E555CCF78D48B9B` / `SQAGPCKNDUF8-20260715-Z-ABAA`，B `WT-A7908536DB74035D2FE1EDD8` / `SQAGPCKNDUF8-20260715-10-ABAA`，G `WT-5995A700296B39051E318CBC` / `SQAGPCKNDUF8-20260715-11-ABAA`。每条均以 `supersedes_worktree_trace_id` 引用旧记录并标记旧 terminal disposition；`pending_body_access=NOT_RUN`，知识图谱/Obsidian refresh=`none`。
- 四个受保护安装锚点在移交后仍保持原路径、原长度和原 SHA-256。未配置 remote，未 stage/commit/stash/push/publish，未读取 pending 正文。8.2 现可从三条新 root-project task 继续，旧 A/B/G task 不再作为 writer。

### Phase 9 — 最终全仓专项审查与 release-stage 整改门禁

本阶段位于全部既定 Phase/Task、V2 记忆裁定整改、RED/GREEN/SPEC/QUALITY、平台与包验收之后，最终接受/发布判断和父 Task 3 之前。发现阶段只读，不得直接修改当前 A02/release/main 工作分支。

1. A-G 专项 reviewer 并行覆盖根 `SKILL.md` 与直接 governing references、全部 standing TOML/supercc dossiers、scripts/CLI/wrappers/service/daemon/bridge/index/registry/migration/install/package、checkers/fixtures、README/install/CHANGELOG/release docs/manifest，以及 Windows/macOS/Linux 路径、shell、Python 行为。
2. 必须量化重复/近义规则复制、模糊主体/条件/默认/停止门禁、source-of-truth 冲突和旧规则残留、重复/孤立/不可达 CLI、声明未实现/实现未调用/只有 fixture 无 production/只有 production 无测试，以及安全/隐私/Git/Obsidian/native-memory/跨平台边界。
3. 每个 reviewer 只输出统一 finding schema，写集为空。门下去重并裁定；尚书只接收 `ACCEPTED` repair clusters。
4. 若 `ACCEPTED findings=0`，输出 `FULL_AUDIT_PASS` 和专项覆盖证据，不创建空分支、空 worktree 或空提交。
5. 若 `ACCEPTED findings>0`，经 root `repo-control` 进入当前 major stage 对应的 `D:\project\worktrees\court-capability-router\<task>` clean child worktree；其 branch 必须是当期 `release/beta0.5.x`，不得另建 `codex/...` 产品整改分支。
6. 在该 release worktree 按 cluster 执行最小 RED -> 单 owner GREEN -> 对应专项复核 -> SPEC -> QUALITY -> 全量回归；只 stage 批准 pathspec，保护既有 dirty state，每个 acceptance gate 前后 index 为空。
7. 完成后按 §3.1 创建该 final-audit major stage 的一个有界本地 commit，报告 branch、commit、测试和 remaining findings；无文件变化时复用当前 HEAD，不创建空提交。禁止 push、PR、tag、release、自动合并或快进；clean package 与下一顺位 release branch 由 Phase 10 继续完成同一 major-stage 闭环。
8. 本阶段只覆盖检查 §0.3/RC2/RC4/RC6 已在早期阶段完成的 operation、编号、谱系、closeout recovery、authority-root 和 carrier lifecycle 合同；若发现缺口，必须退回原 cluster 补 RED/GREEN/SPEC/QUALITY，禁止在 Phase 9 首次实现或把既定整改延迟到最后。

本阶段结果仅允许：`FULL_AUDIT_PASS`、`FULL_AUDIT_REMEDIATION_COMMITTED_LOCAL`、`FULL_AUDIT_BLOCKED`。没有该结果，不得最终结诏或恢复父 Task 3。

### Phase 10 — 最新版本分支、最终包、五根与本机史馆系统收敛

本阶段只在 Phase 9 通过且全部 accepted clusters 已完成后执行。它是本机最终安装授权，不改变一般空白机的 `.agents + current tool` 默认策略。

1. 在 Phase 9 已验收 commit 对应的 clean child worktree 上，由单一集成 writer 确认全部 accepted changes 已按裁定顺位收敛，并逐项复跑 cluster/全局回归。不得把 dirty worktree 整体覆盖进分支，不得 remote/push/PR/tag/publish。
2. 确认 README、CHANGELOG、RELEASE-LOG、docs/logs、release-manifest、LICENSE/COPYRIGHT/NOTICE 与实际代码/测试/版本一致；identity manifest 固定 `Decretum Matrix（诏令矩阵）` / `decretum-matrix` 以及旧 locator/兼容 allowlist；从该精确 commit 的 clean worktree 重建 no-clobber `run1b/run2b`，要求包字节相同、逐文件 manifest/包 SHA-256 通过、旧 run1/run2 与 beta0.5.12 原字节保留。包验证及 §3.2 上一版本上传终态完成后，才从同一 commit 创建下一顺位 `release/beta0.5.(x+1)` child branch/worktree、同步 root 映射并按 §3.3 自动交接。
3. 用最终 staging payload 通过 Phase 5.1 的统一 updater 对固定五个 canonical 物理目录执行可回滚 skill 安装/升级：`~/.agents/skills/decretum-matrix`、`~/.codex/skills/decretum-matrix`、`~/.claude/skills/decretum-matrix`、`~/.hermes/skills/decretum-matrix`、`user_data_base()/hermes/skills/decretum-matrix`。每处 folder basename/machine name、规范 skill name/display 必须分别是 `decretum-matrix`、`decretum-matrix` / `Decretum Matrix（诏令矩阵）`；旧 `skills/court-capability-router` 只能缺省不存在或作为 deprecated compatibility locator/junction/router 指向同一 authority。不得借此修改任一工具配置、启用 memory、写 memory body、复制第二份 alias skill 或扩装未知工具。
4. 五根必须报告同一 canonical path policy、`VERSION`、identity/release manifest 和 portable allowlist 的逐文件 SHA-256；`check_active_copy_hashes.py`、name-surface checker 与每工具实际 loader/runtime probe 均通过，并证明 `physical_authority_count=1`。缺 canonical 根、陈旧根、旧/新双物理目录、compatibility locator 指错、额外非 allowlist body、版本/hash/identity 不同或只看目录存在均失败。
5. 运行 `SHIGUAN_LATEST_SYSTEM_GATE`：唯一 `.agents` 物理史馆、LocalAppData junction、shared Git、schema/index、runtime/CLI/checkers、bridge/daemon/service、Obsidian、native-memory links、worktree records、recovery/paired receipts 均与最终 manifest/包匹配且可用；旧版本服务、第二物理库、脏 index、断链或迁移未完成均失败。
6. 最终复核不得绕过 `pending_count=69`、会话静默、隐私或授权门禁。只有取得 `LATEST_BRANCH_CONVERGED`、`DECRETUM_MATRIX_IDENTITY_GATE=PASS`、`FINAL_PACKAGE_VERIFIED`、`FIVE_ROOTS_LATEST_HASH_EQUAL`、`SHIGUAN_LATEST_SYSTEM_GATE=PASS` 后才可整体验收、完整结诏和恢复父 Task 3。

### 2026-07-16 Decretum Matrix 法律、来源与本地更名 overlay

- 详细执行权威：`docs/plans/2026-07-16-decretum-matrix-dual-license-rights-and-provenance-plan.md`。本指针 supersede 本执行书中“仓库/managed worktree/root mapping 永久保持 `court-capability-router`”的旧假设；受保护史馆 locator、deprecated compatibility install locator、历史记录与 deprecated 兼容输入仍按 allowlist 保留。
- 当前游标：`R0_LOCAL_RENAME_POST_FINGERPRINT -> P0_LEGAL_PREIMAGE_INVENTORY`；工作树为 `D:\project\decretum-matrix-beta0.5.10`，common-dir 为 `D:\project\decretum-matrix\.git`。
- 强制 acceptance：`LOCAL_RENAME_AND_MAPPING_GATE`、`UPSTREAM_MIT_PROVENANCE_GATE`、`LEGAL_PROVENANCE_PACKAGE_ACCEPTANCE_GATE` 与 `NEW_NAME_STAGED_PUBLICATION_GATE` 全部通过后，方可进入相应 package/remote 动作；dirty worktree 的 remote/push/tag/PR/release 均为 `NOT_RUN`。

#### PER_RELEASE_LOCAL_INSTALL_AND_MIGRATION_GATE（最新旨意）

- 每个 major-stage release 在 exact clean commit 的 deterministic package 通过后、该版本发布闭环结束前，必须把同一最新版安装到本机已验证的当前工具/批准安装根；不得继续只在最终大版本安装。
- 安装必须交给独立、规范命名的子线程：`task_name=gongbu_gongjiang_install_<version-token>`、`agent-id=gongbu-gongjiang-install-<version-token>`、`role_key=gongbu`、`official_name_head=GongBu-GongJiang`、`direct_superior=gongbu`。太子/主线程只派发、核验和吸收 receipt，不代为执行安装。
- 受安装影响的数据/schema 迁移使用独立 `gongbu_gongjiang_migrate_<version-token>` 写集；能力官籍/安装索引刷新使用 `libu_hr_registry_index_<version-token>`；史馆 metadata/index 更新使用规范 `shiguan_<bounded-suffix>` 载体并继续受三省共监、门下主审约束。不得用 generic task 名、跨官署代工或同一写集双 writer。
- 每路必须先做可回滚备份/preimage，随后只安装已验收包、执行该版本声明的有界迁移与索引，再回读 loader/runtime、版本、identity manifest 和逐文件 SHA-256。旧版本制品、旧 state/events、protected Shiguan 四文件与 pending body 均不得改写或读取。
- 只有 `PER_RELEASE_LOCAL_INSTALL=PASS`、`AFFECTED_DATA_MIGRATION=PASS|NOT_APPLICABLE`、`CAPABILITY_AND_SHIGUAN_INDEX=PASS|NOT_APPLICABLE`、五根/批准根 hash 等价、全部 index=0 后，才允许签发该版本 release closeout、上一版本上传终态和下一 release 分支交接。

#### FINAL_SKILL_INSTALL_PATH_RENAME_GATE（最新安装授权；当前提交 PLAN_ONLY）

- **授权生效游标：** `3.1A/steps-1-5=PASS -> TAGLESS_CANDIDATE_GATE=PASS -> CANDIDATE_REUSE_GATE=PASS -> check_release_gate(--phase pre-install)=PASS -> FINAL_SKILL_INSTALL_PATH_RENAME_GATE=AUTHORIZED_TO_EXECUTE`。只有 source/write-set/manifest/legal/SPEC/QUALITY、accepted commit、唯一候选包及安装前门禁全部有匹配 receipt 后，本机安装迁移授权才生效；届时按既有 `尚书 -> 工部 -> 安装工匠` 层级和已批准整体 install write set 直接执行，无需再逐文件询问。该授权不绕过阶段顺位、single writer、clean worktree/index、preimage、验收或首错停止门禁；任一前置项不为 PASS 时保持 `NOT_YET_EFFECTIVE`。
- **授权写集：** 覆盖全部 Decretum Matrix 安装代码、package/install metadata、native loader 与 path references、deprecated compatibility entrypoints、文件夹名称及五根受控投影。每个授权安装根的 canonical physical path 固定为 `skills/decretum-matrix`，folder、machine name 与 canonical skill name 均为 `decretum-matrix`，且必须证明 `physical_authority_count=1`；旧 `skills/court-capability-router` 仅可缺省不存在或作为指向同一 authority 的 deprecated compatibility locator/junction/router，禁止旧/新双物理 authority。
- **唯一排除面：史馆数据本身。** Shared Shiguan 的 `pending/body/index/evidence/data bytes` 一律 `NO_READ | NO_WRITE | NO_MOVE | NO_REWRITE`；本授权不给现有 Shiguan index/data branch 写权。安装代码只可更新并验证 locator/junction/router 本身，使其继续指向既有共享史馆数据，不得打开数据正文或改变数据字节。品牌迁移、Skill 目录迁移或 compatibility path cutover 均不得推定、夹带或触发 Shiguan 数据迁移。
- **强制事务：** 统一 updater 必须执行 `backup -> staged atomic rename/move/apply -> native loader reread -> five-root hash/path/identity proof -> rollback on any failure`。任何失败都必须恢复完整 preimage、移除不完整的新物理 authority、恢复受控 compatibility locator，并再次证明没有旧/新双物理 authority；禁止先复制后长期并存、静默覆盖、只改 manifest/path string 或跳过 native reread。
- **终态与恢复：** 成功终态为 `LOCAL_SKILL_PATH_MIGRATION=PASS`，随后游标进入 `check_release_gate(--phase post-install)=PASS -> PER_RELEASE_LOCAL_INSTALL=PASS`；事务失败但完整回滚为 `LOCAL_SKILL_PATH_MIGRATION=ROLLED_BACK`，游标退回首个失败的 source/candidate/pre-install gate；无法证明 preimage 恢复、残留清除或单物理 authority 时为 `LOCAL_SKILL_PATH_MIGRATION=BLOCKED_MANUAL_RECOVERY`，立即停止 post-install、release closeout 与下一分支交接，不得伪报 PASS。
- **外部动作边界：** 本授权只覆盖上述本机安装迁移，不新增或推定 remote、push、tag、PR、GitHub release、asset upload 或 publish 权限；这些动作继续为 `NOT_RUN`，除非另有独立、逐动作的最新明确授权。
- **当前提交边界：** 本次只在 updater branch 以 docs-only commit 记录授权，`AUTHORIZATION_RECORDED=YES`、`HOST_INSTALL_MUTATION=NOT_RUN`；root/mainline、release manifest、host install roots、shared Shiguan data 与 `pending/**` 均不得触碰。本提交不声称候选、pre-install 或迁移 gate 已实际通过。

### Post-A02 Office Identity Pack / DLC / Scope queue

- 详细后续计划：`docs/plans/2026-07-16-decretum-matrix-office-identity-pack-dlc-and-scope-plan.md`；本执行书不复制其正文。
- 排队游标：`A02_ACCEPTED_COMMIT -> CLEAN_PACKAGE -> PER_RELEASE_LOCAL_INSTALL/MIGRATION/INDEX -> NEXT_RELEASE_HANDOFF_ACCEPTED -> MAINLINE_ACCEPTED_BASELINE_GATE -> POST_MAINLINE_REBASE/P0 -> OFFICE_PACK_Q0`。
- Acceptance：P0 必须以最终 accepted baseline 重采 preimage；当前仅计划，不实施 pack/DLC/scope/knowledge promotion。
- Acceptance gate：当前 A02 与下一 release 交接完成前只允许保留计划；不得实现 pack/DLC/`.decretum`/promotion/office architect，不得建立第二 shared-config repo、ledger 或行为权威，pending body access 必须保持 `NO`。

### 2026-07-16 beta0.5.10 完成与 beta0.5.11 差遣层级指针

- 完成标记：beta0.5.10 已发布并完成本机安装及下一分支交接；release=https://github.com/RowlandL/decretum-matrix/releases/tag/beta0.5.10，publication_receipt=libu-beta0.5.10-publication-355183007，publication_receipt_sha256=b57602c20e514c9b7c77889591e2cd8d661ad8944efc66915946691ac2d867ae，install_receipt_sha256=df2a25519555265b0d657fe1aecfd61eee2a430571b015924b7fcdc8481bbf1a，next_branch=release/beta0.5.11，next_head=d79b083fc202d9dc8c89834460191b4da69ad082，handoff_index=0。
- 详细执行权威：docs/plans/2026-07-16-decretum-matrix-taizi-three-departments-and-shangshu-six-ministries-dispatch-plan.md；本执行书不复制正文。
- 游标：PLAN_LANDING_GATE=PASS -> VERSION_ALIGNMENT_GATE -> HIERARCHY_RED/GREEN -> ORDINARY_HIERARCHY -> CHILD_OFFICE_P00 -> SUPERCC_HIERARCHY -> SPEC -> QUALITY -> NEXT_RELEASE_PREPUBLICATION_GATE。
- Acceptance：beta0.5.11 发布前必须证明太子/主线程只向三省进行正常执行差遣、尚书省是六部唯一差遣者、六部仅能派生本部有界子官署；ordinary 与 superCC 使用同一 validator，子官署绑定 profile 与现有 P00 semantic capsule，且 NEXT_RELEASE_PREPUBLICATION_GATE=PASS。

### beta0.5.11 IMPLEMENTED / VERIFIED — 正式结诏编号与内容谱系修复

> 状态：`IMPLEMENTED / VERIFIED`。截图中的 `CCR-R2-SHIR-20260714-A02-RB3-20260717` 与 `总体执行书→Phase 2-3→RB3→autosync 残余复核` 来自结诏输出内容，不是应被 Web 隐藏的普通任务元数据；本整改修复输出源校验，不修改 `web/app.js` 或隐藏字段。

- **根因：** `scripts/check_response_draft_fixtures.py` 只拒绝空值、`未生成` 等占位符，没有验证正式 shape；因此内部 task/protocol 路径可作为非空 `诏令编号`/`古制谱系` 穿过 fixture gate。旧 `implementation_closeout` fixture 的谱系也只有四层，未能证明七层内容分类合同。
- **实现：** checker 现在要求 `诏令编号` 为 `层级码串-YYYYMMDD-日内36进制序号-四字码`，验证真实日期、uppercase base36 与四字码；`古制谱系` 必须为 `史馆总纪·<志>志·<门>门·<纲>纲·<目>目·<条>条·<诏>诏`，并拒绝箭头、`Phase`、`RB`、`task_id` 与 `CCR-*` 协议痕迹。fixture 与 `references/sections/court-closeout-memorial-format.md` 同步为同一规则。
- **RED：** 只加强 checker、保留旧 fixture 后运行 `python -B scripts/check_response_draft_fixtures.py --json`，稳定得到 `response_draft_fixture_gate=FAILED` 与 `implementation_closeout:content_lineage_shape`。
- **GREEN：** 更新 fixture 后，同一命令得到 `response_draft_fixture_gate=PASSED`、`identifier_contract_gate=PASSED`、`identifier_contract_cases=7` 与 `errors=[]`；并复跑 `python -B scripts/check_response_fewshot_format.py`、`python -B scripts/quick_validate.py .`、`git diff --check` 与全树 `.pyc=0`。
- **负例：** `诏令编号=CCR-R2-SHIR-20260714-A02-RB3-20260717`；`古制谱系=总体执行书→Phase 2-3→RB3→autosync 残余复核`。两者均被正式 shape 门禁拒绝。
- **正例：** `诏令编号=SCGSDYJM-20260606-1Z-DAAA`；`古制谱系=史馆总纪·朝制志·官署门·三省六部纲·回复格式目·结诏标识条·内容谱系诏`。两者通过 checker。
- **边界与保护：** 不批量改写历史 `court_code`，不隐藏 Web 字段，不修改 host/install/publish/root/mainline/manifest，不读取、哈希、移动、删除或标记 pending 正文；未调用宿主对话写入、删除或归档，只读 task 定位调用超时后终止且无状态改变，conversation delete/archive/write count=`0`，visible task 保持未归档。

### 2026-07-17 当前身份 superseding note

- 从 `release/beta0.5.11` 当前源码身份起，正式显示名逐字为 `Dercretum-Matrix`；`诏令矩阵` 仅作中文解释。machine/package/canonical skill name 与调用保持 `decretum-matrix` / `$decretum-matrix`。
- 本 note supersede 本执行书内所有面向当前产品状态的早期 display 拼写；既有日期化计划、历史 release/receipt、路径、兼容说明和审计证据保持原字节与原语境，不作追溯改写。
- Canonical physical install authority 是 `skills/decretum-matrix`，ZIP internal root 仍为 `court-capability-router/`；旧安装 locator 只可不存在或解析到同一物理 authority。本机 beta0.5.11 路径迁移仍为 `NOT_RUN`，本 note 不授权安装、迁移、candidate、build、publish 或任何 pending/史馆数据动作。

### Current-stage host messaging reliability blocker

- 状态：`CURRENT_STAGE_PASS`。重启前旧线程携带陈旧 `WorkspaceWrite` 权限枚举，向旧线程发送时被当前宿主枚举校验拒绝；磁盘 `managed_config.toml` 已是合法 `danger-full-access`。未修改宿主配置或 SQLite，改用当前项目线程创建链完成真实跨对话烟测，thread=`019f7193-52ec-7a22-80e2-196e8f6aa014` 返回 `MESSAGE_SMOKE_PASS`。旧线程保留为证据，不再阻断 beta0.5.11 handoff。

### beta0.5.12 release-stage README / Wiki requirement

> 排队约束：本节只在 beta0.5.12 到达发布阶段后执行，不改变当前 `MAINLINE_ACCEPTED_BASELINE_GATE -> POST_MAINLINE_REBASE/P0 -> OFFICE_PACK_Q0` 顺位，也不授权提前创建或发布线上 Wiki。

1. beta0.5.12 到达发布阶段时，为 GitHub 仓库建立并启用 Wiki。
2. 仓库首页 README 面向普通用户，尽可能简洁、直白；首屏优先说明产品是什么、最短安装命令和最短使用入口，不堆放内部治理细节。
3. 详细安装、治理、架构、排错和发布说明迁入或整理到 Wiki。
4. Wiki 必须线上线下同时建立：线上为 GitHub Wiki；线下在仓库内保留可版本化、可离线阅读的 Wiki 源或镜像，并建立同步或发布校验，禁止把线上内容作为唯一副本。
5. beta0.5.12 发布门增加四项验收：README 普通用户可读性、线上 Wiki 可访问、离线 Wiki 完整性、线上/线下一致性。
6. 未到 beta0.5.12 发布阶段，或既有外部发布授权/门禁未满足时，不得提前创建或发布线上 Wiki。
