# Phase 2 Evidence — 通用入口适配与自身 MCP 领域能力面（M2）

> protocol_version: draft-0.1 · phase: 2 · branch: release/beta1.0.8（本地副本）
> 会话：hermes-codex-20260831-2（阶段 2 接续会话）· authority=super, behavior=parallel

## 1. P2-1 最终领域工具矩阵 manifest 投影定稿

- `references/manifests/cli-command-surface.v1.json`：**load_public_tools() = 12**（DoD 精确命中）。
  - 既有 5：court.status / court.command_help / shiguan.query / shiguan.archive_dry_run / memory.scan
  - 新增 4（契约草案）：shiguan.iku_candidates（挂 shiguan.repair-archive-placeholders entry）/
    court.dispatch_plan_validate + court.closeout_checklist（挂 court.court-runtime）/ shiguan.entries_query（挂 shiguan.query-shiguan-index）
  - 复用 3：court.intake_validate / court.capsule_validate / court.semantic_context_validate（public_api 在 court_runtime，manifest 直接引用）
- 投影全部 read_only + closed input_schema + required + description（对齐 court_public_registry 硬约束与评审修订后的契约 D）。
- 一致性验证：
  - `check_unified_cli.py --write-manifest` 重生成后 entries/mcp 投影集合与手改版**完全一致**（ids 133、mcp diffs NONE）——与生成器兼容，无漂移。
  - 新 entrypoint `scripts/iku_candidates.py`（带 main）已登记 manifest entry `shiguan.iku-candidates` + install-projection（shared_agents/portable_current_tool/cli_public 同步）。

## 2. P2-2 public/domain API 与 Agent envelope

- `scripts/court_public_api.py` 新增 4 函数（全部「合法 ok / 非法 ok:false+errors / 字节级幂等」冒烟 PASS）：
  - public_dispatch_plan_validation：**缺省 approval+serial**（不引入 super+parallel 默认）；提供 trusted_preload_manifest 时走完整 exact_preload_contract_gate，否则走结构校验（MCP 无宿主 preload 状态）
  - public_closeout_checklist：十四行清单（label_count=14，前两行 receipt_bound → missing=2）
  - public_shiguan_entries_query：元数据投影白名单（无 pending/private 正文、无 content/evidence）
  - public_iku_candidates：只读探测器（dry_run=true, write_enabled=false），三态语义与 fixture 一致
- 复用 3 函数经 court_runtime import 转发（invoke_public_tool 全链路可达）。
- 新增 `scripts/domain_ledger_api.py`（领域账册，D2a 最小可验证版）：
  - ACL：authority=approval 拒绝写（authority_read_only）；write_set ⊆ 允许集；topic 白名单正则（防穿越）；content ≤2048
  - Create 幂等（topic 去重）；Update 追加不可变 revision（idempotency_key 幂等）；**每次成功写一次 Git commit，失败回滚不提交**
  - domain_skill_load_record（P2-6 多 skill 记录落点）、domain_gbrain_recall（GBrain 公共查询层，只读幂等）、domain_court_code_preview（统一编号生成器只读预览）
  - metadata 支持结构化记录（actor/role/authority/write_set/skill_path/skill_hash/selection_reason）
- 冒烟：24 项 PASS（含幂等、非法输入、approval 拒绝、traversal 拒绝、oversize 拒绝、capability ledger、read 投影无正文）。

## 3. P2-3 tools/call 审计写入

- `court_mcp_server.py` tools/call 分支：调用前后写 `court_operation_journal.write_journal`（root=reference_path("court-runtime")；operation_id=str(uuid4())；payload_digest=payload_sha256({"tool","args"})；receipt={"ok","result_sha256"}）。
- 成功 / 未知工具（-32602）/ 参数校验失败（-32602）三条路径均写 journal；best-effort（审计失败不破坏调用面）。
- e2e 验证（真实 MCP 子进程）：journal 文件生成、digest 与调用 payload 精确匹配、**journal 内容 grep 不到 args 原文与 task_id 明文**。
- 修复记录：初版 uuid4().hex 被 canonical_operation_id 拒绝（要求标准带连字符形式）→ 改 str(uuid.uuid4())。

## 4. P2-4 input_schema description 补全

- 全部 12 工具 mcp.input_schema.properties.* 有 description（≤200 字）；补齐既有 2 处（court.status.limit / shiguan.query.limit）。
- 探针 tool_schemas_have_descriptions 全绿（P2-5 内）。

## 5. P2-5 check_court_mcp_server 扩展 — 58 探针全绿

- `python -B scripts/check_court_mcp_server.py` → **ok:true，58 项探针**（从 29 扩展；45+ 出口达标）。
- 新增探针族：
  - 工具矩阵：EXPECTED_TOOLS=12 在现代/legacy tools/list 可见；command_id 映射 12；manifest 派生（无硬编码 TOOLS）
  - 新工具正/反例：dispatch_plan_validate 正（approval+serial 默认）反（violations）、closeout 14 标签、entries 元数据投影 + 空 query 拒绝、iku dry_run、intake/capsule/semantic 正反例
  - Agent envelope：ok/tool/command_id/api/dry_run/write_enabled 六字段
  - 审计：journal 写入 + digest + 无原文 + 失败记录 + actor 记录
  - 领域写：approval 拒绝不提交、create 提交、create 幂等、update revision 追加、失败不提交、GBrain 只读、编号预览只读、写工具不投影 MCP
  - P2-6：skill_load_record revision+metadata、坏 hash 拒绝、agent-admit 门禁可用、index-first gate 可查

## 6. P2-6 官署 MCP 调用与多 skill 编排

- MCP 审计 receipt 增加 actor（从现代协议 params._meta.clientInfo.name 提取，不信任自报权限）。
- domain_skill_load_record：宿主按 index-first 命中后记录 actor/role/authority/write_set/skill 路径+sha256/选择理由（capability ledger revision + Git commit）。
- 本会话编排演示（evidence 记录）：index-first 查询（check_capability_index_gate --self-test PASS）→ 最小 skill 集加载（decretum-matrix 1.0.7 + using-superpowers）→ agent-admit（RoleAdmissionDecision）→ MCP 调用（本阶段 court.* 工具探针调用）→ ledger 记录。

## 7. 回归快照（本机）

- python -B scripts/quick_validate.py . → PASS
- python -B scripts/check_release_manifest.py --json → ok:true（step_count=49）
- python -B scripts/check_unified_cli.py → 9/9 PASS
- python -B scripts/check_source_state_budget.py --json → ok:true, warnings:[]（预算 7700000 → 7800000 收尾重基线，见 §8）
- python -B scripts/check_skill_identity.py → PASSED
- python -B scripts/check_governance_framework.py → PASS checks=48 errors=0
- python -B scripts/check_install_projection_closure.py → PASS
- python -B scripts/check_portability.py → ok:true
- python -B scripts/check_court_mcp_server.py → ok:true（58 探针）
- python -B scripts/check_read_only_contract.py → 红（E2 已知环境遗留，stash 验证与本阶段改动无关；正式安装机复验）

## 8. 变更记录（阶段 2）

- 提交序列：942910d（P2-1 manifest 12 工具）→ 93c9cc4（P2-2 public API）→ 6232717（domain ledger API）→ P2-3（审计 journal）→ 3f8291b（P2-5 58 探针）→ 722692a（iku entrypoint + runtime projection）→ 2f5d0f6（P2-6 编排）→ 3da58a8（source budget 重基线）。
- source-state-budget.v1.json：max_bytes 7700000 → 7800000（本阶段新增 ~1260 行 portable 脚本；先例 b300946）。
- 环境限制：read_only_contract（E2 遗留）、repo-control doctor 需权威环境、权威 O: 仓待 bundle 应用。
