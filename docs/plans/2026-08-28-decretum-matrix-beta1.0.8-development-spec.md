# 诏令矩阵 beta1.0.8 开发文档（Development Specification）

> 配套：任务书 → docs/plans/2026-08-28-decretum-matrix-beta1.0.8-task-book.md
> 计划书 → docs/plans/2026-08-28-decretum-matrix-beta1.0.8-execution-plan.md
> Handoff 协议草案 → docs/plans/2026-08-28-decretum-matrix-beta1.0.8-codex-handoff-protocol-draft.md
> 总纲/索引 → docs/plans/2026-08-28-decretum-matrix-next-version-iku-lineage-codex-model-predevelopment.md
> 基线：release/beta1.0.7 / VERSION=beta1.0.7 / HEAD=2571178 · 日期：2026-08-28
> beta1.0.7 已完成源码收尾；本文只定义其后的 beta1.0.8 开发准备，不重开 beta1.0.7 历史阶段。
> 文档性质：开发规格（Spec），供 Codex 承接实现。当前是 beta1.0.8 开发准备，不是 beta1.0.8 已发布结论。所有新能力保持 [PLANNED_UNVERIFIED]，只有四类证据（代码 / typed tests / 安装投影 / runtime receipt）绑定后才能提升为已验证能力。

---

## 0. Codex 承接须知（先读）

1. 动手前完整读取安装的权威 SKILL：C:/Users/32893/.agents/skills/decretum-matrix/SKILL.md（127 行），遵守 P00 / 三权 / 层级语义；仓库内 docs/plans 与 scripts 仅为配套材料，不替代该文件。
2. 工作区：仓库镜像根 = O:/gitmirror（同 UNC 192.168.3.133/Omina/gitmirror），子仓库 decretum-matrix 独立 git（当前分支 release/beta1.0.7）。所有代码改动在子仓库内；文档改动（本系列）在 docs/plans/ 下。
3. MCP 纪律：保持「manifest 单一权威 + public/domain API + 零子进程」三角；读取、建议和领域化 Create/Read/Update 由统一 API 提供；不得暴露任意表、SQL 或第二套 ledger。
4. 读取返回 Agent 友好的结构化 JSON envelope；写入必须通过角色 ACL、当前会话 authority、write_set、领域裁定和 Git revision/receipt。
5. 新增工具一律三步走（manifest 投影 → public/domain API → 探针）。
6. 验收即门禁：每个任务末尾给出精确验收命令（python -B scripts/check_xxx.py ...），输出须与文档标注一致；工作树每阶段结束必须干净（见计划书 §Handoff 引用协议草案）。
7. 禁止：改版本号、发布/推送、改宿主配置、加第二套 ledger、批量重编号/重分类、任意表级 CRUD、未经授权的 MCP 写入；允许的领域化写入必须受本规格约束。
8. 承接实现前先读取本机能力索引，优先筛选这些 skill：`decretum-matrix`（层级与交接语义）、`stop-that-shit`（收束范围）、`using-superpowers` / Superpowers（技能与流程选择）、`ponytail`（最小实现）。需要断点续接时补读 `context-restore` / `context-save`；若本机索引中存在 handoff 相关 skill，也在交接阶段优先加载。

---

## 1. 背景、版本决策与范围

### 1.1 背景（beta1.0.7 已收尾后的历史审查锚点 + 2026-08-28 联网调研要点）

- 代码质量高，但存在：①发布阻塞（工作树 5 文件未提交；check_read_only_contract 红；skill-identity 声明 sha 过期）；②安全 HIGH（serve_shiguan_tree entry.id 路径穿越写）；③MCP 面停留在「5 个只读 stdio 工具」；④无 CI；⑤court_runtime 单文件巨兽。
- MCP 2026-07-28 规范：无状态化 / Streamable HTTP / MRTR / OAuth2 / 完整 JSON Schema / Server Cards / 端到端审计（路线图工作组）。beta1.0.8 以现有通用 MCP 入口和 stdio 为核心，交付领域化读、建议和受控 Create/Read/Update；HTTP/Resources/OAuth 不属于当前 skill 核心。

### 1.2 版本决策

| 项 | 值 |
| --- | --- |
| 目标版本 | beta1.0.8（court-beta，增量、无破坏性变更） |
| 范围（Q23 已审查采纳） | 基线清偿 E + 开发点 A（IKU）/ B（编号、谱系、分类防过拟合）/ C（Codex 模型）/ D-MCP（现有 court_mcp_server 通用入口和 stdio 上的史馆/记忆、能力索引、状态、语义校验、IKU、计划/官署调用与领域化账册能力；内部按阶段交付，版本出口统一验收） |
| 非核心后续 | HTTP /mcp、Resources、OAuth/DCR、Server Cards/Registry 等传输/注册扩展；不进入当前 skill 核心和 beta1.0.8 必需门禁 |
| 分支 | release/beta1.0.8（从 release/beta1.0.7 创建） |

### 1.3 范围（In / Out）

In：§3 需求清单 FR-A/B/C/D/E 全部；court_runtime 拆出 1 个职责子模块；在现有通用 MCP 入口和 stdio 上交付最终定稿的 A/B/C/E 能力族，包括史馆/记忆与能力索引的领域化 Create/Read/Update，结诏冲突检查、编号生成器适配、谱系防过拟合、Agent 友好 envelope 和官署受控调用。
Out：任意表或 SQL 的通用 CRUD、第二套编号/谱系、未经 ACL/authority/write_set/领域裁定的 MCP 写入、Delete/记忆整理/合并/去重/清退、HTTP/Resources/OAuth 等当前 skill 不适用的传输扩展、版本号提升（发布批准时才动）、任何外部发布/推送。
访谈采纳：Q23 问卷已审查并采纳；全部 A/B/C/E 能力纳入 beta1.0.8 版本目标，内部仍按 Phase 分批交付；现代协议优先并保留既有 legacy 兼容。

---

## 2. 现状锚点（Codex 代码地图，实现前核对；行号以 beta1.0.7 为准）

| 文件 | 关键符号（行号参考） | 本版本作用 |
| --- | --- | --- |
| scripts/court_public_api.py | 既有状态/查询/记忆函数 + 编号生成器适配、GBrain recall/evaluate/propose、能力索引、领域化账册和 Agent envelope 函数 | MCP 与直接 CLI 共用的 public/domain API；不通过 subprocess |
| scripts/court_public_registry.py | PublicTool(name/description/command_id/public_api/input_schema/side_effect/dry_run), load_public_tools(), _validate_value, invoke_public_tool | 不改逻辑；manifest 加投影即生效 |
| scripts/court_mcp_server.py | CURRENT_PROTOCOL_VERSION="2026-07-28", LEGACY="2025-11-25", _modern_meta, handle(), list_tools(), _tool_result/_modern_tool_result | 现有通用 MCP 协议入口；现代协议优先、legacy 兼容；接入领域工具、Agent envelope 与 tools/call 审计；HTTP/Resources 不属当前核心 |
| scripts/check_court_mcp_server.py | EXPECTED_TOOLS, EXPECTED_COMMAND_IDS, _modern_session()/_legacy_session(), run() 的 checks=[...]（29 项） | 新增探针（D1/D2/D3） |
| scripts/court_runtime.py | public_capsule_validation_payload(charter, value) L8981, public_intake_validation_payload(charter, intake_value, capsule_value=None) L8999, public_semantic_context_validation_payload(value) L9080, semantic_context_json_schema() | 3 个复用；status_payload 供 court.status |
| scripts/court_operation_journal.py | write_journal(root, operation_id, payload_digest, task_id, phase, receipt, updated_at), journal_path/marker_path, payload_sha256 | MCP 审计写入（D2） |
| 本机 skill 能力索引 | `decretum-matrix`、`stop-that-shit`、`using-superpowers`、`ponytail`、`context-restore`、`context-save`、可用 handoff skill | 承接前筛选并加载；交接时明确记录实际加载的 skill 与路径 |
| scripts/serve_shiguan_tree.py | _upsert_entry_unlocked L2254, write_manual_entry L695, /api/entry L2637, /api/peer/entry L2641, client_is_local, require_admin L2337 | entry.id 白名单 + 落盘根校验（E4）；不承担当前 MCP 核心传输 |
| scripts/repair_archive_placeholders.py | repair_text(text), archive_root(), COURT_RE/LINEAGE_RE | IKU 只读发现复用（A1） |
| scripts/shiguan_entry_utils.py | _taxonomy_match_is_negated L1196, _taxonomy_term_evidence L1213, _taxonomy_candidate_scores L1240, content_lineage_parts L1280 | 分类合同（B） |
| scripts/court_model_router.py | route_office_model(...), validate_model_route_ack(route, ack), MODEL_MAX_REASONING_EFFORT | Codex host proof 绑定层（C） |
| scripts/agent_runtime_probe.py | run_store_false_probe, v1/v2 schema 标记 | 探测扩展（C） |
| scripts/ensure_supercc_court.py | maybe_bootstrap_supercc_dependencies L1136（--check-only 已跳过）, check_zellij/check_squad/check_codex/check_office_client | E2 根因定位 |
| references/manifests/cli-command-surface.v1.json | 133 entries；mcp 投影样例见 shiguan.archive-checkpoint 条目 | 投影最终 A/B/C/E 工具族、领域化写工具和编号/谱系适配工具；数量以定稿 manifest 为准 |
| references/manifests/skill-identity.v1.json | skill_sha256（过期值 c2d213…） | E3 重绑 |

---

## 3. 需求规格（FR + AC）

> 约定：AC = 验收标准（可机器验证）；所有 check 运行环境 python -B，工作目录 decretum-matrix/。

### 3.1 FR-E 基线清偿（先行）

**E1 工作树收敛**
- 现状：git status 5 修改 + 1 未跟踪（agent_runtime_probe.py、check_court_agent_config.py、check_install_current_agent_copy.py、check_supercc_functional.py、install_current_agent_copy.py、docs/plans/2026-08-28-…-iku-lineage-codex-model-predevelopment.md）。
- 处理：评审 diff（+130/-22，Codex v2 门禁与冻结引用修复，进行中）。若功能完成 → 提交；若半成品 → 先回退到 HEAD，待本版本重做。不得带着未提交改动进入阶段 1。
- AC：git status --porcelain 为空（除文档变更外）；python -B scripts/check_release_manifest.py --json 通过。

**E2 修复 check_read_only_contract 失败（HIGH）**
- 现象：python -B scripts/check_read_only_contract.py 报 AssertionError: supercc_check_only mutated isolated state: ['home','home/AppData','home/AppData/Roaming']。
- 定位路径（已排除）：maybe_bootstrap_supercc_dependencies 对 --check-only 已跳过；configure_runtime 仅绑闭包不建目录；court_platform.appdata_dir() 读 env 不建目录。剩余嫌疑：模块导入期副作用 / check_zellij|squad|codex|office_client 的 run_command 或 PATH 探测（如 Path.home()/AppData/Roaming/Python/Scripts 类扫描）在隔离 env（HOME=<tmp>/home）下 mkdir(parents=True)。
- 取证方法：复制 check_read_only_contract.isolated_env 语义建临时 HOME，monkeypatch pathlib.Path.mkdir 打印调用栈后运行 python -B scripts/ensure_supercc_court.py --workspace <tmp>/blank --check-only --no-auto-install-deps --format json，定位首个 AppData mkdir 的调用者。
- 修复原则：check-only 路径不得有任何文件系统副作用；若为 PATH/目录探测，改为只读 os.path.exists/不建目录，或探测后不落盘。
- AC：python -B scripts/check_read_only_contract.py 全绿（10 项 check 全过）。

**E3 重绑 skill-identity 声明 sha**
- 现状：skill-identity.v1.json skill_sha256=c2d213…；仓库 SKILL.md 原始 sha=33c276fe（CRLF）、LF 归一化=589842fd；doctor 报 skill_digest_matches:false。根因：956f3e0 绑定后 SKILL.md 又经多次提交修改未重绑；check_skill_identity.py 不校验该字段（自查盲区）。
- 修复：①重算 skill_sha256（LF 归一化 sha）并更新 manifest；②check_skill_identity.py 增加断言：manifest 声明 sha == 实际 SKILL.md 的 LF 归一化 sha。
- AC：python repo-control/repo_control.py doctor（根目录）无 skill 相关 WARN；python -B scripts/check_skill_identity.py PASS。

**E4 serve_shiguan_tree entry.id 路径穿越写（安全 HIGH）**
- 现状：_upsert_entry_unlocked 对 payload["id"] 仅 str().strip()，write_manual_entry 拼 manual_root()/f"{id}.json" 落盘 → id="..\..\x" 可写数据根外任意 .json；配合 loopback 无条件管理员（require_admin 对 127.* 直接放行）可被任何本机进程触发。
- 修复：①_upsert_entry_unlocked 入口加 re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", entry_id)，不匹配 → ValueError("invalid_entry_id")；②write_manual_entry 落盘前校验 path.resolve() 位于 manual_root().resolve() 之下。
- AC：新增回归用例（check_shiguan_http.py）：id="..\..\evil" 被拒；id="a_b-1.json" 正常。

**E5 CLI --version 旗标（可选，低优先级）**
- 现状：court_cli_registry.py main 的 group 判定不识别 --version，实测退出码 3。
- 修复：main 在 --format 提取后、group 判定前，若 argv 含 --version/-V → 打印 SKILL.md metadata.version（或 VERSION 文件）并返回 0。
- AC：python -B scripts/court_cli.py --version 输出 beta1.0.8（发布后）且退出码 0。

### 3.2 FR-A IKU 占位符治理

**A1 只读候选发现（MCP 工具 shiguan.iku_candidates）**
- 语义：扫描 repair_archive_placeholders.archive_root()（reference_path("plan-archives")）下 *.md，检出含 IKU、待 archive_checkpoint 生成、占位符由 archive_checkpoint 自动回填 的记录；对每个命中输出结构化候选。
- 输出字段（草案，manifest 定稿为准）：
  { "dry_run": true, "write_enabled": false, "candidates": [{
    "record_path": "references/plan-archives/xxx.md", "record_id": "...",
    "field": "诏令编号|古制谱系|正文", "fragment_sha256": "...",
    "placeholder_kind": "IKU|PENDING_GENERATED|PENDING_REFILL",
    "nearest_court_code": "...", "nearest_lineage": "...",
    "receipt_hint": "...", "suggested_action": "NOOP|REVIEW|REPAIR_CANDIDATE", "reason": "..." }] }
- 规则：无最近有效 receipt / 来源冲突 / 语义不明 → REVIEW；可安全回填 → REPAIR_CANDIDATE；IKU 出现在非编号字段或语义不明 → NOOP/REVIEW。不执行任何写入。
- 复用：repair_archive_placeholders.repair_text 的检测逻辑改造为只读探测器（不写文件）；新函数放 scripts/court_public_api.py（薄封装）或新建 scripts/iku_candidates.py（纯函数 + public 封装）。
- AC：①dry_run 调用前后 plan-archives 目录字节级不变；②相同输入两次调用结果 JSON 字节级一致；③探针覆盖 NOOP/REVIEW/REPAIR_CANDIDATE 三态。

**A2 受控修复（CLI 受权路径，本版本只做能力预留，不接 MCP 写）**
- repair_archive_placeholders.py 增加 --dry-run（默认）与 --apply（显式）；--apply 前打印将改文件清单并要求 --yes。
- 写入约束：只改占位文本；保存原文指纹与回滚前像（references/shiguan-backups/ 或 court-runtime 下）；两次 --apply 幂等。
- AC：--dry-run 零字节变化；--apply 后重跑 --dry-run 无新候选（幂等）。

### 3.3 FR-B 编号/谱系/分类防过拟合

**B1 三层数据分离**（契约层）
- 编号层：court_code / 日期 / 日内序号 / 四字码（shiguan_entry_utils 的 base36/daily_sequence/stable_base36_code 系列）。
- 内容谱系层：lineage_parts / lineage_key / lineage_display（content_lineage_parts 产出）。
- Facet 层：phase / status / memory_decision / risk / value / priority / 行为谱系 / keywords / source。
- AC：重建/整理（rebuild_shiguan_index.py、tidy_shiguan_records.py 路径）保留已有合法谱系与 court_code；新增回归用例在 check_shiguan_lineage_rebuild_compatibility.py。

**B2 版本化分类合同**
- 新增输出字段（在 _taxonomy_candidate_scores / 分类管线末端附加）：taxonomy_version（="2026-08-28.beta1.0.8"）、classification_status（classified|tie|unknown|conflict|review）、classification_reason、classification_confidence、classification_score、classification_margin、positive_evidence[]、negative_evidence[]、candidates[]。
- 规则：分数不足 / 并列 / 仅负证据 / 完全未知 → review/待审；必须有对第二候选的正 margin 才 classified。
- AC：check_shiguan_lineage_taxonomy.py 增加断言：tie → status=tie；否定句不贡献正向分；unknown 无关键词 → unknown。

**B3 防过拟合最小验证集**
- 新增 references/fixtures/classification-contract-validation.json：5 类用例（清晰 / tie / 否定 / 未知 / 冲突 + 重复运行）。
- AC：fixture 用例全过；重复运行输出规范化 JSON 字节级一致（纳入 check）。

**B4 编号生成器 MCP 适配与史馆谱系保护**
- MCP 只调用统一 shiguan archive-checkpoint 或其权威 public/domain API 获取 court_code、lineage 和 closeout identity，不生成第二套编号。
- 谱系分类继续使用版本化 taxonomy、最小验证集、正向 evidence margin、否定证据隔离、tie/unknown/conflict/review 状态；历史合法 court_code 和 lineage 不被重建过程覆盖。
- AC：编号来源 receipt 可追溯；重复调用结果稳定；过拟合 fixture、否定句、未知项、并列项和历史字段保留回归全绿。

### 3.4 FR-C 新版 Codex 指定模型能力适配

**C1 host proof 探测与绑定**
- agent_runtime_probe.py 扩展输出：codex_version、codex_executable、supported_model_effort_pairs[]、config_exposes_model（bool）、turn_context_model、turn_context_effort（fresh-session 回读）。
- court_model_router.py 新增 route_office_model_with_host_proof(route, host_probe)：校验 host_probe 满足 route 的 recommended_model/effort（或显式继承），返回 model_override_applied（YES/NO）+ host_proof_sha256；不满足 → 回退 inherit_parent_model_and_effort 并标 model_route_status=FAILED / runtime_degraded。
- AC：①每个组合有版本绑定 host proof；②无证明 / 回读不一致 → 回退 + FAILED（不伪报）；③check_court_model_router.py 增加 host-proof 正/反例。

### 3.5 FR-D MCP 领域能力面（本版本主体）

**D1 在现有通用 MCP 入口适配并新增诏令矩阵自身工具族**（manifest 三步走；最终矩阵按 Q23 审查结果定稿）

| # | name | public_api | input_schema 要点 | 说明 |
| --- | --- | --- | --- | --- |
| 1 | court.intake_validate | public_intake_validation_payload（复用） | charter:string(≤2048, minLength 1); intake_value:object; capsule_value?:object | 对白纸旨意做 intake 校验 |
| 2 | court.capsule_validate | public_capsule_validation_payload（复用） | charter:string; value:object | P00 capsule 校验 |
| 3 | court.semantic_context_validate | public_semantic_context_validation_payload（复用） | value:object（closed，字段见 semantic_context_json_schema） | 语义上下文校验 |
| 4 | court.dispatch_plan_validate | public_dispatch_plan_validation（新增） | entries:array(1..16, items=object closed); authority?:enum[approval,autonomous,super]; behavior?:enum[serial,parallel] | 校验派发计划（不派发）；缺省按 approval+serial 校验或要求显式，避免落默认 super+parallel 的坑 |
| 5 | court.closeout_checklist | public_closeout_checklist（新增） | task_id?:string | 输出十四行结诏 checklist 与 missing[]（对齐 references/sections/court-closeout-memorial-format.md） |
| 6 | shiguan.entries_query | public_shiguan_entries_query（新增） | query:string(minLength 1); limit:integer(1..50, default 20) | 元数据投影检索（不读 pending/private 正文） |
| 7 | shiguan.iku_candidates | public_iku_candidates（新增） | scope?:enum[plan-archives]（默认） | A1 只读发现 |

- 每个投影 JSON 结构（仿 shiguan.archive-checkpoint 条目）：
  {
    "id": "court.dispatch-plan-validate", "command": "dispatch-plan-validate", "group": "court",
    "domain": "court", "public": true, "side_effect": "read_only",
    "handler": "python_module:court_public_api",
    "authority_source": "scripts/court_public_api.py",
    "legacy_path": "scripts/court_public_api.py",
    "receipt_schema": "court.cli.result.v1",
    "mcp": {
      "name": "court.dispatch_plan_validate",
      "description": "Validate a dispatch plan without dispatching (dry-run, read-only).",
      "public_api": "public_dispatch_plan_validation",
      "side_effect": "read_only", "dry_run": false,
      "input_schema": {
        "type": "object", "additionalProperties": false, "required": ["entries"],
        "properties": {
          "entries": {"type": "array", "minItems": 1, "maxItems": 16, "items": {"type": "object", "additionalProperties": false}},
          "authority": {"type": "string", "enum": ["approval", "autonomous", "super"]},
          "behavior": {"type": "string", "enum": ["serial", "parallel"]}
        }
      }
    }
  }
 - AC：最终 manifest 工具集合在现代协议和既有 legacy 会话下可发现；每个工具具备 public/domain API、Agent 友好 envelope、正/反例探针和审计覆盖；工具数量以最终 manifest 为准。

- 领域工具族至少覆盖：史馆/记忆 recall、evaluate、conflict/expiry scan、candidate/propose、decision status；能力索引 query/refresh 状态；状态与语义契约校验；IKU 候选；计划与官署调用 dry-run；领域化账册 Create/Read/Update；统一编号生成器适配；full-record/leaves 查询指针。
- 领域化写工具必须同时满足角色 ACL、当前会话 authority、write_set、领域裁定和 Git revision/commit；Delete、记忆整理、合并、去重、清退不在本版。

**D2 MCP 调用审计（史馆接入）**
- 实现点：court_mcp_server.handle() 中 tools/call 分支，调用 invoke_public_tool 前后各一次 court_operation_journal.write_journal：
  - root = shiguan_paths.reference_path("court-runtime")；
  - operation_id = uuid4().hex（每次调用唯一；另存 call_ref = sha256(tool + canonical args) 便于去重）；
  - payload_digest = payload_sha256({"tool": name, "args": args})（只存摘要，不存正文/密钥）；
  - task_id = "mcp"、phase = "mcp-call"、receipt = {"ok": ..., "result_sha256": ...}、updated_at = ISO 时间。
- AC：成功与失败（含参数校验失败）均产生 journal 条目；journal 中不出现 args 原始文本；check_court_mcp_server 增加「调用后 journal 文件存在且 digest 匹配」断言。

**D2a 领域化账册写入与记忆裁定**
- 统一 CLI、MCP 和主动 CLI 共用领域 API；史馆记忆和能力索引账册支持 Create/Read/Update，Update 追加不可变 revision，每次成功操作单独 Git commit。
- 持久角色 ACL 与当前 authority/write_set 取更严格者；approval 只读；低风险确定性操作可自动裁定，高风险正式 durable memory、升降档、跨来源合并和冲突裁定进入门下/人工。
- 结诏自动执行冲突/过期检查；新记忆或更高权威事实优先，确定性冲突可标记 DEGRADED/SUPERSEDED 并告知用户；所有操作记录 before/after、原因、revision、Git commit 和 receipt。
- AC：ACL/authority 反例、approval 写拒绝、领域写入 Git commit、memory_decision、冲突降级告知和失败不提交全绿。

**D2b 能力索引主动查询与多 skill 加载**
- 非平凡任务首次选能力时查询本机能力索引；跨域、匹配不足、索引 stale/corrupt、权限变化、记忆冲突/过期、投影降级、PostgreSQL/sidecar 状态变化、迁移、阶段边界或 Handoff 时主动重查。
- 命中后由宿主 Skill 机制主动加载按依赖排序的最小 skill 集合，可多选；不自动安装/升级。receipt 记录实际路径、版本/哈希、选择顺序、冲突和未选原因。
- AC：index-first、特殊触发重查、多 skill 组合加载、identity 校验和未选候选审计全绿。

**D2c GBrain 召回、清洗与生命周期**
- 采用 CANDIDATE → REVIEW → APPROVED → ACTIVE；ACTIVE → DEGRADED/STALE/SUPERSEDED；普通 recall/query 先走本地 metadata/摘要快路径，深度 evaluate/propose 不阻塞。
- 默认 envelope 返回清洗后的 metadata、摘要、短正文指引和完整正文定位指针；保留 leaves、source_ref、line_anchor、source hash 和原版完整上下文文件路径索引。
- 结诏自动冲突/过期扫描；确定性冲突可脚本化降级或替代并向用户报告；非确定性、高风险或正式记忆转换按领域裁定。
- AC：召回字段清洗、冲突/过期发现、增量 revision/conflict set 重算、Agent envelope、P95 ≤100ms 优化目标和 P95 ≤200ms 发布门禁全绿。

**D3 input_schema 补全**
- manifest 中所有 mcp.input_schema.properties.* 补 description（≤200 字）；保持 additionalProperties:false。
- AC：check_court_mcp_server 增加 tool_schemas_have_descriptions 探针（所有属性 description 非空）。

**D4（非本版核心，保留为后续备注）Streamable HTTP /mcp + Resources**
- serve_shiguan_tree.py 增加 POST /mcp：复用 request_host_allowed + 令牌模型；消息处理复用 court_mcp_server.handle（抽出纯 handle_message(message, state) 复用）；默认 127.0.0.1。
- resources 只读投影：shiguan://entry/{id}、shiguan://receipt/{id}（仅索引/元数据；pending/private 正文不读）。
- 当前处理：HTTP /mcp 与 Resources 对当前 skill 不具实际意义，不进入 beta1.0.8 必需交付、核心工具矩阵或发布门禁；未来重新立项时再定义 AC。

### 3.6 Q23 采纳的 MCP 扩展契约

1. **全量版本目标**：A/B/C/E 能力均纳入 beta1.0.8 版本目标，内部可按 Phase/P0/P1 子任务分批实现和验收，不把“同批交付”解释为同一阶段完成。
2. **编号与谱系**：MCP 调用统一 shiguan archive-checkpoint 或权威 public API 的编号生成器；不生成第二套编号。谱系分类必须使用版本化 taxonomy、正向 evidence margin、否定证据隔离、tie/unknown/conflict/review 状态和最小验证集，保留历史合法 court_code/lineage，避免过拟合。
3. **CLI/API 双入口**：领域化记忆、能力索引和其他受管账册能力由统一 CLI 与 public/domain API 提供；MCP 和主动 CLI 共用该能力，不通过 MCP subprocess 调 CLI。MCP 读取返回 Agent 友好的结构化 envelope，至少包含 schema、ok、data、state、source_ref、revision、errors、next_action 和 receipt_ref。
4. **官署调用**：官署可以在职责范围内调用 MCP；计划验证、边界检查、Handoff 准备和 dry-run 可由 MCP 提供；真实 spawn/reuse/wake、权限变更和写集执行仍须经过 role/direct_superior、agent-admit、authority、write_set 和 receipt。
5. **记忆自动范式**：结诏时自动执行冲突/过期快检查。对新记忆或更高权威事实，确定性冲突可脚本化标记冲突记忆为 DEGRADED 或 SUPERSEDED，并在 Agent envelope 和用户侧回奏中告知 before/after、原因、证据和 Git revision；语义不确定、跨域、高风险或正式 durable-memory 转换仍进入门下/人工裁定。
6. **史馆实录与 leaves**：保留现有十四行 compact memorial、状态字段和原史馆实录结构；在其上增加可查询 leaves 与 full-record 指针。full-record 记录初始问题、初始动作、后续动作、中间问题、错误、错误解决、最终结果、是否解决、解决范围和下一步；完整上下文不复制进索引，只记录受权限控制的原版完整上下文文件路径、相对 locator、line/section 指针、source hash 和访问状态。
7. **召回默认内容**：默认返回清洗后的 metadata、摘要、短正文指引和完整正文定位指针；完整正文按权限、pending/private 边界和 source_ref 按需读取。召回快路径自动提供冲突/过期标记，不阻塞普通 recall。
8. **协议边界**：现有通用 MCP 入口、现代协议和 legacy 兼容为当前核心；HTTP /mcp、Resources、OAuth/DCR、Server Cards/Registry 对当前 skill 不具实际意义，不进入 beta1.0.8 必需交付或发布门禁。
9. **领域写入与 Git**：史馆记忆和能力索引账册支持领域化 Create/Read/Update；Update 追加不可变 revision；每次成功领域写操作独立 Git commit，并在 receipt 绑定 memory/domain decision、revision、Git commit、actor、authority、write_set、task/phase。Delete、记忆整理、合并、去重、清退不在本版。
10. **投影与 Obsidian**：Git/JSONL 是唯一权威源；现有稀疏能力向量/JSON 图为 C-lite 底座；SQLite/FTS、PostgreSQL + pgvector/pg_search 只作可重建 B/C 投影，缺失时自动降级。Obsidian 继续遵循“Git → 史馆索引/图/树 → preserve-only 派生同步”，投影不得反向覆盖史馆或用户笔记。

---

## 4. 架构与技术方案（约束重申）

1. MCP 三角按最终定稿结构：cli-command-surface.v1.json（命令源）→ court_public_registry（派生 + closed-schema 校验）→ court_public_api（public/domain 纯函数）；现有 court_mcp_server 作为当前通用协议入口，只做协议适配与审计，零 subprocess。现代协议优先并保留 legacy；HTTP/Resources 不属本版核心。
2. 新增工具三步走：manifest 加 mcp 投影 → court_public_api 或领域 API 实现/复用 → check_court_mcp_server 探针；读取/建议保持纯函数，领域化写入单独通过 ACL、authority、write_set、领域裁定和 Git 提交。

MCP 输出统一 Agent 友好 JSON envelope：schema、ok、data、state、source_ref、revision、errors、next_action、receipt_ref；不通过 subprocess 调 CLI 或解析人类文本。
3. 读取与隐私：pending/private 正文默认不读；完整正文只通过受权限控制的 source_ref/line_anchor 指引按需读取；审计只存摘要；密钥/正文不入日志、receipt、文档。
4. 失败闭合：校验失败返回 ok:false + errors[]；未知工具或参数返回 JSON-RPC error（-32602）；领域写入失败不得产生 Git commit。
5. 幂等：所有新增 public_* 相同输入重复调用输出字节级一致。

---

## 5. 安全与隐私约束（强制）

- 新增代码沿用 court_safe_fs / court_file_lock 原子写；不新增裸 open(w)。
- entry.id 白名单（E4）先于一切新写路径落地（防止新工具被同款穿越利用）。
- MCP 审计不记录：args 原文、返回正文、token/密钥、宿主路径。
- 不新增 shell=True / os.system / pickle / unsafe yaml.load（全仓 grep 保持零命中）。

---

## 6. 完成定义（DoD）

1. 全部 FR 的 AC 通过（验收命令见任务书 WBS 各任务）；check_read_only_contract / check_source_state_budget / check_release_manifest / check_skill_identity（含绑定断言）/ check_governance_framework / check_court_mcp_server 全绿。
2. load_public_tools() = 12 个；MCP 审计可重放；IKU 干跑零字节变化；分类验证集全过；Codex host proof 有版本绑定。
3. 工作树干净；release-manifest 与代码一致；收据重生成；CHANGELOG/README/wiki 同步 beta1.0.8；doctor 无 WARN。
4. 新能力条目按 AGENTS.md 契约经 evidence receipt 提升（[PLANNED_UNVERIFIED] → VERIFIED 需四类证据）。
