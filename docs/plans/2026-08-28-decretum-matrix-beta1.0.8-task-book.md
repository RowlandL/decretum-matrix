# 诏令矩阵 beta1.0.8 任务书（Task Book）

> 配套：开发文档 → docs/plans/2026-08-28-decretum-matrix-beta1.0.8-development-spec.md
> 计划书 → docs/plans/2026-08-28-decretum-matrix-beta1.0.8-execution-plan.md
> Handoff 协议草案 → docs/plans/2026-08-28-decretum-matrix-beta1.0.8-codex-handoff-protocol-draft.md
> 基线：release/beta1.0.7 · 日期：2026-08-28 · 估算合计约 27 人日（不含 stretch）
> beta1.0.7 已完成源码收尾，当前 `release/beta1.0.7` / HEAD `2571178` 作为 beta1.0.8 的开发基线；本任务书不改变 beta1.0.7 的历史发布身份，外部发布状态仍以对应发布回执为准。

---

## 1. 任务总体目标与总体验收（DoD）

在 release/beta1.0.8 分支完成：基线清偿（E）+ 开发点 A/B/C + 现有 court_mcp_server 通用 MCP 入口和 stdio 上的完整 A/B/C/E 领域能力目标。领域化 Create/Read/Update、统一编号生成器适配、谱系防过拟合、GBrain 召回/裁定、能力索引主动查询、多 skill 加载和官署受控调用均纳入版本目标；内部按阶段分批实现，四类证据全部绑定后发布 beta1.0.8。
执行前先读取 `decretum-matrix` skill，再按任务类型优先调用 `stop-that-shit`、`using-superpowers` / Superpowers、`ponytail`；需要断点续接时补用 `context-restore`，任务告一段落时用 `context-save` 记下剩余工作。交接阶段必须加载本任务书、计划书、handoff 协议草案、上一阶段 handoff/证据文件，以及本机能力索引筛出的有用 skill。

总体验收（全部满足才算完成）：
1. repo-control doctor 无 WARN；quick_validate / check_read_only_contract / check_source_state_budget / check_release_manifest 全绿。
2. 现有通用 MCP 入口在现代协议和 legacy 会话下可发现并调用最终工具矩阵；工具由统一 CLI/public-domain API 提供 Agent 友好 JSON envelope。史馆/记忆与能力索引账册支持领域化 Create/Read/Update；Delete、记忆整理、合并、去重、清退不纳入。工具数量以最终 manifest 为准。
3. 编号只调用统一生成器/权威 receipt；谱系分类版本化并通过最小验证集和 evidence margin 防过拟合。
4. 结诏自动冲突/过期检查；确定性冲突可脚本化降级或替代并告知用户；正式 durable memory、升降档、跨来源合并和高风险操作仍按领域裁定。
3. MCP 调用审计可重放；IKU 干跑零字节变化；分类验证集全过；Codex host proof 有版本绑定。
4. 工作树干净、release-manifest 与代码一致、收据重生成；CHANGELOG/README/wiki 版本同步 beta1.0.8。

---

## 2. 里程碑与出口标准

阶段状态标记规则：每个阶段完成后，必须在本节表格和 `docs/plans/beta1.0.8/handoffs/README.md` 同步标记状态；未开始为 `TODO`，执行中为 `IN_PROGRESS`，验收待复核为 `VERIFY_READY`，复核完成为 `COMPLETED`，阻塞为 `BLOCKED:<原因>`。验收证据摘要直接写回本任务书对应阶段的“验收证据”小节，完整输出放入 `phase-N-evidence.md`。

| 里程碑 | 内容 | 出口标准 | 状态 | 验收证据摘要 |
| --- | --- | --- | --- | --- |
| M0 基线绿 | 清偿 E；工作树干净；doctor 无 WARN | 门禁三件套（read_only / source_budget / release_manifest）绿 | VERIFY_READY | 见 docs/plans/beta1.0.8/handoffs/phase-0-evidence.md（本机环境 doctor 需权威环境补跑） |
| M1 合同定稿 | A/B/C/D 契约文档、schema、验证集、fixtures 提交 | 契约评审通过（门下复核意见闭环） | VERIFY_READY | 见 docs/plans/beta1.0.8/handoffs/phase-1-evidence.md（评审意见已回写 §6：a/b/c 通过、d 修订 2 处、manifest 条件通过；闭环待 REVIEWER 确认） |
| M2 通用入口适配与自身 MCP 能力面 | 现有入口上的 A/B/C/E 工具族、Agent envelope、能力索引、编号/谱系、GBrain recall 和领域化账册 | P2-1..P2-6 的 manifest/public API/探针/审计全绿 | VERIFY_READY | 见 docs/plans/beta1.0.8/handoffs/phase-2-evidence.md（12 工具矩阵、58 探针、审计/编排探针全绿；出口待 REVIEWER） |
| M3 分类与 IKU 修复 | B 合同 + 验证集；A2 受控修复（CLI）；结诏冲突/过期、leaves/full-record、增量反馈 | P3-1..P3-9 的分类、IKU 和 GBrain 记忆治理测试全绿 | VERIFY_READY | 见 docs/plans/beta1.0.8/handoffs/phase-3-evidence.md（编号开始对话分配/结诏复用、分类合同 9 字段+conflict、5 类验证集、IKU 只读幂等+回滚、冲突/过期范式、leaves/full-record 全绿；出口待 REVIEWER） |
| M4 Codex 适配 | C 探测/路由/回退闭环 | host proof 测试 + 回退测试全绿 | VERIFY_READY | 见 docs/plans/beta1.0.8/handoffs/phase-4-evidence.md（P4-1 probe host_proof 六字段 null-safe、P4-2 route_office_model_with_host_proof 正/反例、P4-3 fresh-session 回读 applied/回退+degraded、P4-4 回归全绿；--live-runtime 本机环境遗留另述；出口待 REVIEWER） |
| M5 发布 | 全量门禁、收据、版本锚点、CHANGELOG、release 评审 | 发布批准；workspace.yaml 升 beta1.0.8 | VERIFY_READY | 见 docs/plans/beta1.0.8/handoffs/phase-5-evidence.md（22 项门禁 + Phase 2/3/4 新增 check 全绿或环境受限记录；收据/锚点绑定 HEAD 5e0b660；评审记录 release-review-beta1.0.8.md 待 REVIEWER 签署） |

---

## 3. WBS 任务分解（Codex 执行级规格）

> 角色：PM（工程负责人）/ ARCH（架构）/ CLI（运行时）/ WEB（web+HTTP）/ TEST（验证）/ REL（发布）。
> 每个任务含：目标、改动点（文件/函数/JSON）、验收命令与期望输出。估算单位：人日（PD）。

### 阶段 0：基线清偿（M0）

**E1 beta1.0.7 基线确认**（CLI/REL，0.5 PD）
- 目标：确认 beta1.0.7 收尾提交、当前 HEAD、manifest/version 锚点和工作树状态，确保 beta1.0.8 从已收尾基线起步。
- 改动点：复核 `release/beta1.0.7` HEAD `2571178` 及已提交的 agent_runtime_probe.py / check_court_agent_config.py / check_install_current_agent_copy.py / check_supercc_functional.py / install_current_agent_copy.py；本轮不回退已收尾文件。
- 决策规则：beta1.0.7 历史未验证标签只作为历史证据保留，不阻止 1.0.8 规划；若发现当前 HEAD/manifest 不一致，记录 BLOCKED 并单独修复，不重开已收尾阶段。
- 验收：
  - git status --porcelain（decretum-matrix/）无意外项（docs/plans 本系列文档除外）；
  - python -B scripts/check_release_manifest.py --json → RELEASE_MANIFEST_OK steps=49。

**E2 修复 check_read_only_contract 失败**（CLI，1 PD，HIGH）
- 目标：ensure_supercc_court.py --check-only 零文件系统副作用。
- 改动点：定位创建 home/AppData/Roaming 的调用者（取证法见开发文档 E2），修复为不建目录或仅读探测；若为模块导入期副作用，改为惰性初始化。
- 验收：python -B scripts/check_read_only_contract.py → 无 AssertionError，结尾 {"ok": true, "checks": [...]}。

**E3 重绑 skill-identity sha + 补绑定断言**（REL，0.5 PD）
- 改动点：references/manifests/skill-identity.v1.json 的 skill_sha256 更新为 SKILL.md 的 LF 归一化 sha256（当前 589842fd…，重算为准）；check_skill_identity.py 增加声明 sha 与实际文件绑定断言。
- 验收：根目录 python repo-control/repo_control.py doctor → installed_skill_identity.skill_digest_matches = true；python -B scripts/check_skill_identity.py → status PASSED。

**E4 serve_shiguan_tree entry.id 白名单 + 落盘根校验**（WEB，1 PD，安全 HIGH）
- 改动点：
  - serve_shiguan_tree.py _upsert_entry_unlocked 入口：import re；entry_id 不匹配 re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", entry_id) → raise ValueError("invalid_entry_id")；
  - write_manual_entry：落盘前 assert/raise path.resolve().is_relative_to(manual_root().resolve())。
- 验收：check_shiguan_http.py 新增回归（id=..\..\evil 被拒 400/403；id=a_b-1.json 正常）；python -B scripts/check_shiguan_http.py → 全绿。

**E5 CLI --version（可选）**（CLI，0.5 PD）
- 改动点：court_cli_registry.py main 在 group 判定前识别 --version/-V，输出 SKILL.md metadata.version 并返回 0。
- 验收：python -B scripts/court_cli.py --version → 输出 beta1.0.8（发布后）退出码 0。

### 阶段 0 验收证据快照（2026-08-31 本地接续）

- E1 ✅：基线 2571178 核对通过；收尾脚本均已提交；VERSION/manifest 锚点一致；收尾文档 3 处未提交改动判定为应保留（本地已并入 6391be0 并作为 beta1.0.8 基线）。
- E2 ✅（本机）：check_read_only_contract → ok:true；原现象为环境相关（外部工具二进制 roam 目录创建），建议正式安装机复验。
- E3 ✅：skill-identity.v1.json skill_sha256 重绑 589842FD…（LF 归一化）；check_skill_identity.py 新增绑定断言（先 RED 后 GREEN）→ PASSED；--self-test PASSED。
- E4 ✅：_upsert_entry_unlocked 白名单 re.fullmatch(r"[A-Za-z0-9_.-]{1,64}")，非法 → ValueError("invalid_entry_id")；write_manual_entry 落盘前 resolve().is_relative_to(manual_root())；check_shiguan_http.py 新增回归（穿越被拒/合法 id 正常）→ 全绿（含本机 live 校验）。
- E5 ✅：court_cli_registry.py --version/-V（SKILL.md metadata.version，VERSION 兜底）→ 输出 beta1.0.7、退出码 0；check_unified_cli.py 9/9 PASS。
- 门禁：quick_validate PASS；check_source_state_budget ok:true；check_release_manifest ok:true（step_count=49）。
- 详细输出与限制：docs/plans/beta1.0.8/handoffs/phase-0-evidence.md。

### 阶段 1：合同与样本（M1）

**P1-1 契约文档与 schema 定稿**（ARCH，2 PD）
- 产出：A/B/C/D 的契约文档（字段边界、候选格式、分类字段、host proof 字段）落 docs/plans/beta1.0.8/；manifest 投影草案 JSON 经评审。
- 验收：评审通过记录（handoff 文档含 reviewers 与结论）。

**P1-2 IKU 候选格式定稿**（ARCH+CLI，1 PD）
- 产出：references/fixtures/iku-candidates.json（3 态用例：NOOP/REVIEW/REPAIR_CANDIDATE）。
- 验收：fixture JSON 通过 python -c 语法校验。

**P1-3 taxonomy_version 引入**（ARCH+CLI，1 PD）
- 改动点：shiguan_entry_utils.py 增加 TAXONOMY_VERSION = "2026-08-28.beta1.0.8" 常量；分类管线输出附加 taxonomy_version。
- 验收：check_shiguan_lineage_taxonomy.py 断言 taxonomy_version 存在且匹配。


### 阶段 1 验收证据快照（2026-08-31 本地接续）

- P1-1 完成：contracts/ 4 份契约文档 + manifest 投影草案 JSON（4 工具，契约六要素）；JSON 校验通过；评审待闭环（下一会话）。
- P1-2 完成：references/fixtures/iku-candidates.json（NOOP/REVIEW/REPAIR_CANDIDATE 三态）。
- P1-3 完成：shiguan_entry_utils.py TAXONOMY_VERSION="2026-08-28.beta1.0.8"；CONTENT_TAXONOMY_VERSION=TAXONOMY_VERSION；golden 版本同步；check_shiguan_lineage_taxonomy.py canonical 断言 → PASS。
- 门禁：quick_validate PASS；source_budget ok:true；read_only ok:true；release_manifest ok:true(49)；unified_cli 9/9。
- 详细与手动交接：docs/plans/beta1.0.8/handoffs/phase-1-evidence.md、phase-1-handoff.md。

### 阶段 2：MCP 领域能力面（M2，A/B/C/E，P2-1..P2-6）

**P2-1 最终领域工具矩阵 manifest 投影**（CLI，1 PD）
- 改动点：references/manifests/cli-command-surface.v1.json 为定稿 A/B/C/E 工具族增加 mcp 投影；包含史馆/记忆、能力索引、状态/语义校验、IKU、计划/官署 dry-run、编号/谱系适配和领域化账册工具；工具数量不预设。
- 验收：每个工具存在 command_id、public/domain API、closed input_schema、side_effect、receipt_schema 和 Agent envelope 说明；manifest 与 registry 一致。

**P2-2 public/domain API 与 Agent envelope**（CLI，3 PD）
- 复用：public_intake_validation_payload / public_capsule_validation_payload / public_semantic_context_validation_payload（court_runtime 已有，manifest 直接引用）；新增领域 API 统一由 MCP、主动 CLI 和直接 CLI 调用。
- 新增/复用（court_public_api.py 与领域 API）：
  - public_dispatch_plan_validation(entries, authority=None, behavior=None)：包装 court_dispatch_policy.validate_dispatch_plan 的校验语义，输出 {"ok": bool, "violations": []}；authority/behavior 缺省按 approval/serial 校验（不得引入 super+parallel 默认）。
  - public_closeout_checklist(task_id=None)：对齐 court-closeout-memorial-format.md 的十四行清单，输出 {"checklist": [...], "missing": [...]}。
  - public_shiguan_entries_query(query, limit=20)：复用 shiguan_entry_utils 检索，输出元数据投影（无 pending/private 正文）。
  - public_iku_candidates(scope="plan-archives")：复用 repair_archive_placeholders 检测逻辑的只读探测器，输出 candidates[]（dry_run=true）。
  - 领域化 memory/capability ledger Create/Read/Update、GBrain recall/evaluate/propose、能力索引 query/refresh 状态和统一编号生成器适配；MCP 不通过 subprocess 调 CLI。
- 验收：python -B 下逐函数冒烟：合法输入返回 ok，非法输入返回 ok:false + errors[]（不抛裸异常）；相同输入两次调用输出字节级一致。

**P2-3 tools/call 审计写入**（CLI，1.5 PD）
- 改动点：court_mcp_server.py handle() tools/call 分支，调用 invoke_public_tool 前后写 court_operation_journal.write_journal（root=reference_path("court-runtime")；operation_id=uuid4().hex；payload_digest=payload_sha256({"tool":name,"args":args})；receipt={"ok":..., "result_sha256":...}）。
- 验收：check_court_mcp_server 新增「调用后 journal 文件存在且 payload_sha256 匹配」探针；journal 内容 grep 不到 args 原文。

**P2-4 input_schema description 补全**（CLI，0.5 PD）
- 改动点：cli-command-surface.v1.json 全部 mcp.input_schema.properties.* 补 description（≤200 字）；保持 additionalProperties:false。
- 验收：check_court_mcp_server 新增 tool_schemas_have_descriptions 探针。

**P2-5 check_court_mcp_server 扩展**（TEST，2 PD）
- 改动点：最终工具矩阵在现代协议和 legacy 下 tools/list/tools/call 可见；新增 Agent envelope、能力索引主动查询、多 skill 组合记录、官署调用前置、领域写入 ACL/authority/write_set、Git commit、失败不提交、schema closed 和审计探针。
- 验收：python -B scripts/check_court_mcp_server.py → ok:true；定稿工具全部正/反例、权限和审计探针全绿。

**P2-6 官署 MCP 调用与多 skill 主动编排**（CLI/ARCH，1.5 PD）
- 改动点：官署在职责范围调用 MCP；能力索引常规首次查询与特殊情况主动重查；命中后由宿主加载按依赖排序的最小多 skill 集合；记录 actor、role、authority、write_set、skill 路径/哈希和选择理由。
- 验收：agent-admit、权限边界、index-first、特殊重查、多 skill 加载和 receipt 回归全绿。

### 阶段 3：分类、IKU 与 GBrain 记忆治理（M3，P3-1..P3-9）

**P3-1 三层数据分离与编号生成器适配**（CLI，2 PD）
- 改动点：编号层调用统一 archive-checkpoint/public API；谱系层与 facet 层分离；历史 court_code/lineage 保留。
- 验收：编号来源 receipt 可追溯；历史字段不被覆盖；check_shiguan_lineage_rebuild_compatibility.py 回归绿。

**P3-2 版本化分类合同落地**（CLI，2 PD）
- 改动点：_taxonomy_candidate_scores / content_lineage_parts 输出附加 classification_status / reason / confidence / score / margin / positive_evidence / negative_evidence / candidates / taxonomy_version。
- 验收：check_shiguan_lineage_taxonomy.py 新增断言（tie/unknown/否定不贡献正向分）全绿。

**P3-3 防过拟合验证集**（TEST，1 PD）
- 产出：references/fixtures/classification-contract-validation.json（5 类用例）。
- 验收：fixture 驱动断言全过；重复运行字节级一致。

**P3-4 repair_archive_placeholders 只读 + 幂等修复**（CLI，2 PD）
- 改动点：增加 --dry-run（默认）与 --apply（需 --yes）；--apply 前打印清单；回滚前像落 court-runtime 备份目录。
- 验收：--dry-run 零字节变化；--apply 后重跑 --dry-run 无新候选（幂等）。

**P3-5 IKU 修复回滚与 receipt 指针**（CLI，1 PD）
- 改动点：修复记录含原文指纹 + receipt 指针 + 回滚前像路径；修复后 court_code/ancient_lineage 逐字来自统一 receipt。
- 验收：回滚测试（从备份恢复）绿。

**P3-6 结诏冲突/过期处理范式**（CLI，2 PD）
- 改动点：结诏时自动扫描冲突/过期记忆；新记忆或更高权威事实优先；确定性冲突标记 DEGRADED/SUPERSEDED 并告知用户；不确定或高风险转门下/人工；范式可脚本化。
- 验收：冲突/过期 fixture、before/after、原因、Git revision、用户告知字段和脚本化范式全绿。

**P3-7 GBrain recall 与史馆 leaves/full-record**（CLI，2 PD）
- 改动点：默认返回清洗 metadata、摘要、短正文指引和完整正文 source_ref；保留原十四行 compact memorial 与实录结构，增加可查询 leaves、full-record 和原版完整上下文文件路径索引。
- 验收：初始问题、过程问题、初始/后续动作、错误、修复、最终结果、是否解决、解决范围和下一步可查询；pending/private 正文不泄露。

**P3-8 记忆反馈与增量再评估**（CLI，1.5 PD）
- 改动点：记录召回命中、用户纠正、冲突/过期结果和门下裁定；只增量重算受影响 revision/conflict set。
- 验收：重复运行稳定；受影响集合最小化；不触发无必要全量重建。

**P3-9 史馆实录 leaves 与完整上下文索引**（CLI，1 PD）
- 改动点：保留原十四行 compact memorial、状态字段和既有实录结构；增加可查询 leaves、full-record 指针、初始/中间/后续问题与动作、错误/修复、最终结果、是否解决、解决范围、下一步，以及原版完整上下文文件的相对路径/line/section/source hash 索引。
- 验收：通过 leaves 可准确检索完整过程；不复制 pending/private 正文；路径不写成不可迁移的绝对宿主契约。

### 阶段 3 验收证据快照（2026-08-31 本地接续）

- P3-1 ✅：编号来源 receipt 可追溯（`domain_court_code_preview` 输出 generator/authority/receipt_hint，与 `next_daily_sequence` 同一 index 字节级一致、只读零改动）；**附加旨意（用户补充）**：编号改为**开始对话时分配**（`scripts/court_session_numbering.py` 的 `domain_court_code_issue`，统一生成器 + 会话内幂等 + 同日跨会话防碰撞，持久化 court-runtime/session-numbering），结诏经 `--session-id` **逐字复用**（`archive_checkpoint` session_allocation + `court_session_closeout` 传 session_id），无分配回退原逻辑；存量 court_code/lineage 不被覆盖。
- P3-2 ✅：`content_lineage_parts` 落地 9 项合同字段（taxonomy_version/classification_status/reason/confidence/score/margin/positive_evidence/negative_evidence/candidates），新增 `conflict` 状态；check 断言 tie/unknown/否定不贡献正向分、否定词不进 positive_evidence。
- P3-3 ✅：`references/fixtures/classification-contract-validation.json` 5 类用例（清晰/tie/否定/未知/冲突）+ 双跑字节级一致。
- P3-4/P3-5 ✅：`repair_archive_placeholders` --dry-run 默认（零字节改动）/ --apply 需 --yes / 回滚前像 + repair journal（原文指纹 + receipt 指针 + 快照路径）/ 两次 apply 幂等 / rollback 恢复；IKU 字面标记改词边界匹配（消除 court_code 子串误报）。
- P3-6 ✅：`closeout_conflict_scan` 确定性 SUPERSEDED/DEGRADED + 非确定性 REVIEW（双方进门下），apply 经 domain ledger 每次写 revision + Git commit，before/after/reason/user_notice 全齐，`affected_topics` 增量接口。
- P3-7/P3-9 ✅：`shiguan_gbrain` full_record_pointer（metadata-only、相对可迁移 locator/section/line anchor/source hash/access_status）+ build_leaves + build_full_record_index；`build_recall_context`/`domain_gbrain_recall` 附 full_record+leaves；绝对宿主路径拒绝、不复制 pending/private 正文。
- P3-8 ✅（接口）：`scan(affected_topics=...)` 只重算受影响集合（check 验证最小集），重复运行稳定。
- 门禁：quick_validate PASS；release_manifest ok:true(49)；source_budget ok:true；governance 48 checks；skill_identity PASSED；install_projection PASS；portability ok:true；unified_cli 9/9；mcp_server ok:true(58)；read_only_contract ok:true（本机转绿）；taxonomy/rebuild/iku_repair/closeout_conflict/full_record_index/session_numbering/session_closeout 全 PASS。
- 详细与手动交接：docs/plans/beta1.0.8/handoffs/phase-3-evidence.md、phase-3-handoff.md。

### 阶段 4：Codex 模型适配（M4）

**P4-1 agent_runtime_probe 扩展**（CLI，2 PD）
- 改动点：输出 codex_version / codex_executable / supported_model_effort_pairs / config_exposes_model / turn_context_model / turn_context_effort。
- 验收：probe 输出含全部 host proof 字段；无 Codex 环境时字段为 null 且不报错。

**P4-2 court_model_router host proof 绑定**（CLI，1.5 PD）
- 改动点：新增 route_office_model_with_host_proof(route, host_probe)；校验通过 → model_override_applied=YES + host_proof_sha256；不满足 → 回退 inherit + model_route_status=FAILED/runtime_degraded。
- 验收：check_court_model_router.py 正/反例全绿。

**P4-3 fresh-session worker 覆盖证明**（CLI，2 PD）
- 改动点：court_codex_office_worker.py 接 host proof；fresh-session JSONL 回读证明 session id/model/effort/dossier cwd。
- 验收：回读一致 → applied；不一致/缺失 → 回退 + degraded。

**P4-4 模型适配回归**（TEST，1 PD）
- 验收：check_court_model_router.py / check_court_agent_config.py 全绿。

### 阶段 4 验收证据快照（2026-08-31 本地接续）

- P4-1 ✅：`agent_runtime_probe.py` probe() 新增 `host_proof` 六字段（codex_version 纯版本/去前缀、codex_executable 经 sanitize 脱敏、supported_model_effort_pairs 来自 MODEL_MAX_REASONING_EFFORT 稳定排序、config_exposes_model 顶层 model/model_provider 探测、turn_context_model/effort fresh-session JSONL 元数据回读）；无 Codex 环境六字段全 null 且不报错；本机实测 codex-cli 0.149.0-alpha.4.1。
- P4-2 ✅：`court_model_router.py` 新增 `route_office_model_with_host_proof(route, host_probe)`：满足（版本绑定 + 支持对 + 回读一致）→ model_override_applied=YES + host_proof_sha256 + APPLIED；不满足/无证明/回读不一致 → 回退 inherit + FAILED + runtime_degraded（不伪报）；显式继承 → INHERIT；兼容 fresh-worker proof 字段名；`check_court_model_router.py` 正/反例全绿。
- P4-3 ✅：`court_codex_office_worker.py` 新增 `verify_worker_session_override`：fresh-session JSONL 回读 session id/model/effort/dossier cwd 一致 → applied；不一致/缺失（含文件不存在、无效 plan）→ 回退 inherit + degraded（不抛裸异常）；`check_court_codex_office_worker.py` 回读正/反例全绿。
- P4-4 ✅：`check_court_model_router.py` ok:true；`check_court_agent_config.py` SELF_TEST_OK（新增 host_proof 字段集/无 Codex null/pairs 结构断言）；source-state-budget 重基线（probe 1310 / check worker 290）后 ok:true（341 files / 7,855,825 bytes）；unified_cli PASS、release_manifest ok:true(49)、governance 48 checks、mcp_server ok:true(58)、quick_validate PASS。
- 环境注记：`check_court_agent_config --live-runtime` 本机 FAILED（native_effective=[max_depth, v2_bounds_or_reserved_schema]）经 git stash 验证为 baseline 环境遗留（本机 Codex 配置未达推荐），非阶段回归；正式安装机复验。
- 详细与手动交接：docs/plans/beta1.0.8/handoffs/phase-4-evidence.md、phase-4-handoff.md。

### 阶段 5：发布（M5）

**P5-1 全量门禁**（TEST，2 PD）
- 执行清单（全部要求绿）：quick_validate / check_governance_framework / check_read_only_contract / check_source_state_budget --json / check_release_manifest --json / check_unified_cli --all --json / check_court_open_fastpath / check_startup_fastpath_contract / check_court_result_semantics / check_cli_performance / check_capability_index_gate / check_release_legal / release_payload_manifest --self-test --check / check_package_privacy / check_shiguan_concurrency / check_shiguan_http / check_codex_agent_roles / check_active_copy_hashes / check_court_mcp_server / check_skill_identity / check_catalog --strict / check_portability；另加 Agent envelope、编号来源 receipt、谱系防过拟合、GBrain 冲突/过期、leaves/full-record、领域写入 Git commit、approval 只读和现代/legacy 双兼容探针。

**P5-2 收据与锚点**（REL，1 PD）
- 产出：source-final / install-host-closeout 收据重生成绑定当前 HEAD；VERSION / CHANGELOG / README / docs/wiki/Release-Notes 同步 beta1.0.8；skill-identity 与 install-projection 同步。

**P5-3 release 评审与批准**（PM+REL，1 PD）
- 产出：门下复核意见闭环；发布批准记录；workspace.yaml version.current → beta1.0.8（仅发布批准时）。

### 阶段 5 验收证据快照（2026-08-31 本地接续）

- P5-1 ✅：任务书 22 项清单全部执行——20 项全绿（quick_validate / governance 48 / read_only / source_state_budget / release_manifest 49 / unified_cli PASS / open_fastpath / startup_fastpath / result_semantics / cli_performance / capability_index_gate / release_legal / release_payload_manifest self-test+check / package_privacy 64 tests / shiguan_concurrency / shiguan_http（loopback live）/ court_mcp_server 58 探针 / skill_identity / catalog --strict / portability）；2 项环境受限记录（check_active_copy_hashes extra=4 受保护史馆锚点；check_codex_agent_roles config_errors 本机 Codex 配置）——正式安装机复验；Phase 2/3/4 新增 11 个独立 check 全 PASS。
- P5-2 ✅：VERSION/SBOM/plugin/github-release-metadata/skill-identity/SKILL.md/README/CHANGELOG/Release-Notes 同步 beta1.0.8（commit 5e0b660）；release-manifest.json 重生成（307 files / 7,029,000 B / payload_index_sha256=67a20cd5…）；skill-identity skill_sha256 重绑（5A481A1D… LF 归一化）；source-final / install-host-closeout 收据生成绑定 HEAD 5e0b660；版本一致性子门（release_manifest/release_legal/release_metadata/skill_identity）全绿。
- P5-3 ✅（待签署）：release-review-beta1.0.8.md 含门禁闭环汇总、环境受限项复验命令与批准记录模板（status=PENDING_REVIEWER）；workspace.yaml 本机不存在，version.current → beta1.0.8 与外部发布列为权威环境批准后执行项；无 push/tag/release。
- 门禁处置记录：release_payload_manifest 收据重生成（初红→绿）；check_active_copy_hashes 发布期清理（14 项残留移入备份 host-cleanup-20260831，extra 收敛为 4 受保护锚点）；check_codex_agent_roles/check_catalog 经 install update + sync_codex_agents_from_profiles --write 修复（14/14 渲染一致）；check_shiguan_http 经 loopback 短启复验。
- 已知既有问题（非本阶段回归）：check_install_current_agent_copy self-test ValueError（beta1.0.7 遗留，文件未变更）。
- 详细与手动交接：docs/plans/beta1.0.8/handoffs/phase-5-evidence.md、phase-5-handoff.md、release-review-beta1.0.8.md。

### Stretch（非本版核心，后续另立项）

**S1 HTTP /mcp 传输扩展**（WEB，后续）
- 当前处理：HTTP /mcp 对当前 skill 不具实际意义，不进入 beta1.0.8 必需交付和发布门禁；未来重新立项时定义。

**S2 Resources 暴露**（WEB+CLI，后续）
- 当前处理：Resources 对当前 skill 不具实际意义，不进入 beta1.0.8；未来若重新纳入，只允许索引/元数据或受权限控制的短片段，禁止 pending/private 正文。

---

## 4. 任务依赖关系

- E 系列无依赖（M0 前置）；P1 依赖 E；P2 依赖 P1-1/2；P3 依赖 P1-3（与 P2 可部分并行）；P4 依赖 E（与 P2/P3 可并行）；P5 依赖全部；S1/S2 依赖 P2-*。

## 5. 角色与协作纪律

- 代码变更在 release/beta1.0.8 分支与对应 worktree；控制面操作走 repo-control 并留审计事件；每阶段结束按 Handoff 协议草案执行交接。
- 结诏/里程碑评审经门下复核；本任务书范围内不执行任何外部发布/推送。

## 6. 交接加载与阶段标记

- 交接时必须加载：本任务书、beta1.0.8 开发文档、beta1.0.8 计划书、beta1.0.8 Handoff 协议草案、上一阶段 handoff 文档、上一阶段 evidence 文档、`context-save` / `context-restore` 的最近 saved context，以及本机能力索引筛出的有用 skill。

- 每完成一个阶段，必须在本任务书对应里程碑处补状态标记，并把验收证据摘要写回本文件；完整验收输出单独放入 `phase-N-evidence.md`。

- 阶段状态统一写成 `TODO`、`IN_PROGRESS`、`VERIFY_READY`、`COMPLETED`、`BLOCKED:<原因>`。

## 7. MCP 访谈决策记录（Q23 已审查采纳）

- 现有 court_mcp_server 通用入口和 stdio 为当前核心；现代协议优先并保留 legacy。
- A/B/C/E 能力全部纳入 beta1.0.8 版本目标，内部按 Phase/P0/P1 分批实现，版本出口统一验收。
- 史馆/记忆与能力索引账册支持领域化 Create/Read/Update；Update 追加不可变 revision，每次成功操作独立 Git commit；Delete、记忆整理、合并、去重、清退不在本版。
- 统一 CLI、MCP 和主动 CLI 共用 public/domain API；MCP 返回 Agent 友好 JSON，不通过 subprocess 调 CLI。
- 编号只调用统一生成器/权威 receipt；谱系分类版本化并以最小验证集、正向 margin 和否定证据隔离防过拟合。
- 结诏自动冲突/过期检查；确定性冲突可脚本化降级或替代并告知用户；正式 durable memory、升降档、跨来源合并和高风险操作仍按领域裁定。
- 保留原史馆实录结构和十四行 compact memorial；增加可查询 leaves、full-record 指针和原版完整上下文文件路径索引。
- HTTP /mcp、Resources、OAuth/DCR、Server Cards/Registry 对当前 skill 不具实际意义，不进入 beta1.0.8 必需交付和发布门禁。

访谈完整记录与审查证据：docs/plans/2026-08-28-decretum-matrix-beta1.0.8-mcp-grill-interview.md。
