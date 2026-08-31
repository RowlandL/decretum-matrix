# Phase 3 Evidence — 分类、IKU 与 GBrain 记忆治理（M3）

> protocol_version: draft-0.1 · phase: 3 · branch: release/beta1.0.8（本地副本）
> 会话：hermes-codex-20260831-3（阶段 3 接续会话）· authority=super, behavior=parallel
> 附加旨意：诏令矩阵编号应在**开始对话时生成**、结诏时复用（用户补充，已并入 P3-1）

## 1. P3-1 三层数据分离与编号生成器适配（含"开始对话分配/结诏复用"）

- 编号来源 receipt 可追溯：`domain_court_code_preview` 输出新增 `generator=archive_checkpoint.next_daily_sequence`、`authority=unified_court_code_generator`、`receipt_hint=court.shiguan_archive_checkpoint_receipt.v1`；预览与 `archive_checkpoint.next_daily_sequence` 对同一 index 字节级一致、只读零改动。
- 开始对话分配：新增 `scripts/court_session_numbering.py`：
  - `domain_court_code_issue(session_id, topic, ...)`：会话开始时用统一生成器分配 court_code 并持久化到 `court-runtime/session-numbering/<quoted-session>.json`；逐会话幂等（重复 issue 返回同一 code）；同一日期跨会话分配防碰撞（`_next_sequence` 计入既有 allocation 的最大序号）；`preview_only=False`。
  - `issue`/`show` CLI 入口（unified CLI `shiguan court-session-numbering`）。
- 结诏复用：`archive_checkpoint.build_index_entry` 支持 `session_allocation`（`daily_sequence`/`court_code` 逐字复用，标记 `court_code_issued_at_start=true`）；`append_checkpoint` 按 `--session-id` 解析分配；`court_session_closeout._default_archive_writer` 传 `session_id`。无分配时回退原逻辑（不破坏直接 CLI 结诏）。
- 历史字段保留：`check_shiguan_lineage_rebuild_compatibility.py` 新增探针——有效存量 court_code 不被 enrich 覆盖；编号预览只读零改动。
- 验收：`python -B scripts/check_shiguan_lineage_rebuild_compatibility.py` → PASS（numbering_source.single_authority_traceable=true, preview_readonly_zero_mutation=true）；`python -B scripts/check_court_code_session_numbering.py` → PASS（issue→closeout 复用、幂等、并发防碰撞、回退、resolve 门禁、CLI 往返全绿）。

## 2. P3-2 版本化分类合同落地

- `shiguan_entry_utils.content_lineage_parts` 落地 contract-b B2 字段：`taxonomy_version` / `classification_status` / `classification_reason` / `classification_confidence` / `classification_score` / `classification_margin` / `positive_evidence` / `negative_evidence` / `candidates`（新增 contract 字段，既有 `classification_*` 字段保留兼容）。
- 新增 `conflict` 状态：top 候选同时含正向与否定证据（score>0 且 negated_score>0）→ status=review, reason=conflict（golden 9 例不受影响）。
- `check_shiguan_lineage_taxonomy.py` 新增断言：contract 字段存在；否定词永不进入 positive_evidence（disjoint）；unknown → score=0 且 positive_evidence 空；conflict → review。
- 验收：`python -B scripts/check_shiguan_lineage_taxonomy.py` → PASS（contract.evidence_fields_present=true, negated_terms_never_positive=true, unknown_contributes_no_positive=true）。

## 3. P3-3 防过拟合验证集

- 新增 `references/fixtures/classification-contract-validation.json`：5 类用例（清晰 / 并列 / 否定 / 未知 / 冲突）+ 重复运行字节级一致；`check_shiguan_lineage_taxonomy.py` 加载并断言（validation_set.all_five_classes_ok=true, double_run_byte_identical=true）。

## 4. P3-4 / P3-5 IKU 只读修复、幂等与回滚/receipt

- `repair_archive_placeholders.py` 重写：`--dry-run`（默认，零字节改动）→ `--apply`（需 `--yes`，先打印文件清单）→ 落盘前保存回滚前像到 court-runtime 备份目录 + 写 repair journal（原文指纹 original_sha256 / 每行 original_line_sha256 / 最近 archive_checkpoint receipt 指针 / 回滚快照路径 / 逐字 court_code+ancient_lineage）；两次 apply 幂等；`rollback()` 从快照恢复。
- `iku_candidates.py`：IKU 字面标记改为词边界匹配（消除 court_code 子串误报，如 `SUIKUIKUIKUIKUIKULD`）；`detect_candidates` 支持 `root` 隔离探测。
- `check_iku_repair.py` 全绿：dry-run 零改动、--yes 门禁、幂等、回滚恢复、journal receipt/快照指针、误报拒绝。

## 5. P3-6 结诏冲突/过期处理范式

- `scripts/closeout_conflict_scan.py`：只读 `scan()`（确定性 SUPERSEDED / DEGRADED，非确定性 REVIEW 转门下；新记忆优先，冲突双方进 REVIEW）；`apply_decisions()` 经 domain_ledger 每次写一个不可变 revision + 一次 Git commit；before/after、reason、user_notice 用户告知字段齐全；`affected_topics` 增量范围（P3-8 接口）。
- fixture：`references/fixtures/closeout-conflict-expiry.json`（SUPERSEDED/DEGRADED/REVIEW/clean）。
- `check_closeout_conflict_scan.py` 全绿：集合断言、确定性、Git revision、approval 拒绝、幂等 apply、增量最小集（仅受影响 topic 重算）。

## 6. P3-7 / P3-9 GBrain recall 与史馆 leaves/full-record

- `shiguan_gbrain.py`：`full_record_pointer`（metadata-only，相对可迁移 source_ref、section/line anchor、source hash、access_status=metadata_only、可查询 fields：initial_question/process_questions/initial_actions/subsequent_actions/final_result/resolved/resolution_scope/next_step、unindexed_fields 声明不复制正文）；`build_leaves`（同谱系/同主题相关记录元数据，无正文）；`build_full_record_index`（可查询 leaves + full-record 指针索引，拒绝绝对宿主路径）；`build_recall_context` 每条命中附加 full_record+leaves。
- `domain_ledger_api.domain_gbrain_recall`：entries 附加 full_record + leaves。
- `check_shiguan_full_record_index.py` 全绿：相对路径可迁移、绝对路径拒绝、leaves 可检索完整过程、无 pending/private 正文复制、双跑字节级一致。

## 7. 回归快照（本机 2026-08-31）

- quick_validate.py . → PASS
- check_release_manifest.py --json → ok:true（step_count=49）
- check_source_state_budget.py --json → ok:true（portable 341 files / 7,834,460 bytes；上限 345 / 7,900,000）
- check_governance_framework.py → PASS checks=48 errors=0
- check_skill_identity.py → PASSED（11 surfaces）
- check_install_projection_closure.py → PASS
- check_portability.py → ok:true
- check_unified_cli.py → 9/9 PASS（manifest 重生成，entries 140，12 MCP 投影保留）
- check_court_mcp_server.py → ok:true（58 探针）
- check_shiguan_lineage_taxonomy.py → PASS
- check_shiguan_lineage_rebuild_compatibility.py → PASS
- check_iku_repair.py → PASS
- check_closeout_conflict_scan.py → PASS
- check_shiguan_full_record_index.py → PASS
- check_court_code_session_numbering.py → PASS
- check_court_session_closeout.py → core/transaction/cli PASS
- check_read_only_contract.py → ok:true（13 项；E2 历史遗留本机不再触发，正式安装机仍建议复验）

## 8. 变更记录（阶段 3）

- b3630d6 P3-1..P3-3 编号来源 receipt + 分类合同 + 验证集
- 47f5807 P3-4/P3-5 IKU 只读修复 + 幂等 + 回滚/receipt + check_court_mcp_server bash 依赖修复（Windows 可移植）
- 93d8e09 P3-6 冲突/过期处理范式
- e9cb423 P3-7/P3-9 GBrain recall leaves/full-record + full-record index
- af8a793 附加旨意：court_code 开始对话分配/结诏复用 + classifier 修正 + manifest 重生成 + budget 重基线
- 1035665 manifest 纳入 session numbering 入口 + shiguan_gbrain 行数预算

## 9. 环境与风险更新

- check_court_mcp_server 的 `commit_count` 移除裸 bash 依赖（原 phase-2 代码用 `bash -c`，本 PowerShell 环境无 bash 而红；现为 Python 原生 git log 解析，Windows 可移植）。
- 权威 O: 仓 bundle 未应用；repo-control doctor 需权威环境（不变）。
- check_read_only_contract 本机转绿（历史 E2 环境遗留；正式安装机复验）。
- manifest 重生成后 iku_candidates/closeout_conflict_scan/court_session_numbering 归入 shiguan 域；12 MCP 工具投影保留；`check_unified_cli --write-manifest` 与手改语义一致（classifier 已对齐）。
- 新 check（check_iku_repair / check_closeout_conflict_scan / check_shiguan_full_record_index / check_court_code_session_numbering）为独立门禁脚本，P5-1 发布清单应纳入。
