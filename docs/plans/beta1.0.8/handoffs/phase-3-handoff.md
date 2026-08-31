# Phase 3 Handoff — 分类、IKU 与 GBrain 记忆治理（M3）

- protocol_version: draft-0.1
- phase: 3
- status: VERIFY_READY
- handoffer_session: hermes-codex-20260831-3（阶段 3 接续会话，authority=super, behavior=parallel）
- started_at: 2026-08-31T19:00:00+08:00 (approx)
- finished_at: 2026-08-31T21:30:00+08:00 (approx)
- git_branch: release/beta1.0.8
- git_head_commit: 1035665
- working_tree_clean: true（提交后；index 空）

## 1. 目标达成

- P3-1 三层数据分离与编号生成器适配：完成。编号来源 receipt 可追溯（generator/authority/receipt_hint）；历史 court_code/lineage 不被覆盖；**附加旨意**：编号在**开始对话时分配**（`court_session_numbering.domain_court_code_issue`，统一生成器 + 会话内幂等 + 同日跨会话防碰撞），结诏时经 `--session-id` **逐字复用**（不再重新生成），无分配回退原逻辑。
- P3-2 版本化分类合同落地：完成。`content_lineage_parts` 输出 9 项合同字段（含新增 `positive_evidence`/`negative_evidence`/`candidates`），新增 `conflict` 状态；check 断言 tie/unknown/否定不贡献正向分、否定词不进 positive_evidence。
- P3-3 防过拟合验证集：完成。`classification-contract-validation.json` 5 类用例 + 双跑字节级一致。
- P3-4/P3-5 IKU 只读 + 幂等修复 + 回滚/receipt：完成。`repair_archive_placeholders` --dry-run 默认 / --apply 需 --yes / 回滚前像 + journal（原文指纹 + receipt 指针 + 快照路径）/ 幂等 / rollback；修复 IKU 字面误报（词边界）。
- P3-6 结诏冲突/过期处理范式：完成。`closeout_conflict_scan` 确定性 SUPERSEDED/DEGRADED + 非确定性 REVIEW，apply 经 domain ledger 每次写 revision + Git commit，before/after/reason/user_notice 全齐，`affected_topics` 增量接口。
- P3-7 GBrain recall 与史馆 leaves/full-record：完成。`build_recall_context` 每条命中附 `full_record` 指针 + `leaves`；`domain_gbrain_recall` 同步。
- P3-8 记忆反馈与增量再评估：接口完成。`closeout_conflict_scan.scan(affected_topics=...)` 只重算受影响集合（检查验证最小集）；记忆反馈经 domain ledger 记录（P3-6 链路复用）。
- P3-9 史馆实录 leaves 与完整上下文索引：完成。`build_full_record_index` 可查询 leaves + full-record 指针（相对 locator/section/line anchor/source hash/access_status），拒绝绝对宿主路径，不复制 pending/private 正文。

## 2. 变更文件清单

- A scripts/court_session_numbering.py（开始对话编号分配 + issue/show CLI）
- A scripts/check_court_code_session_numbering.py（分配→复用链路检查）
- A scripts/check_iku_repair.py（P3-4/5 检查）
- A scripts/closeout_conflict_scan.py（P3-6 范式）
- A scripts/check_closeout_conflict_scan.py（P3-6 检查）
- A scripts/check_shiguan_full_record_index.py（P3-7/9 检查）
- A references/fixtures/classification-contract-validation.json（P3-3）
- A references/fixtures/closeout-conflict-expiry.json（P3-6）
- M scripts/shiguan_entry_utils.py（分类合同字段 + conflict）
- M scripts/check_shiguan_lineage_taxonomy.py（验证集 + 合同/否定/未知/冲突断言）
- M scripts/check_shiguan_lineage_rebuild_compatibility.py（P3-1 编号 receipt 探针）
- M scripts/domain_ledger_api.py（preview traceability + gbrain recall full_record/leaves）
- M scripts/iku_candidates.py（词边界 IKU + root 参数）
- M scripts/repair_archive_placeholders.py（只读默认 + --apply/--yes + 快照/journal/回滚）
- M scripts/archive_checkpoint.py（--session-id + session_allocation 复用）
- M scripts/court_session_closeout.py（会话结诏传 session_id）
- M scripts/shiguan_gbrain.py（full_record/leaves/index）
- M scripts/check_court_mcp_server.py（commit_count 去 bash 依赖）
- M scripts/check_unified_cli.py（classifier 归域 shiguan）
- M references/manifests/cli-command-surface.v1.json（重生成，entries 140）
- M references/manifests/install-projection.v1.json（court_session_numbering 投影）
- M references/manifests/source-state-budget.v1.json（max_files 345 / max_bytes 7900000 / shiguan_gbrain 500 行）
- A docs/plans/beta1.0.8/handoffs/phase-3-evidence.md / phase-3-handoff.md（本文件）

## 3. 验收命令与输出

见 phase-3-evidence.md §1–§7。关键：
- `python -B scripts/check_court_code_session_numbering.py` → PASS（开始分配→结诏复用）
- `python -B scripts/check_shiguan_lineage_taxonomy.py` / `check_shiguan_lineage_rebuild_compatibility.py` → PASS
- `python -B scripts/check_iku_repair.py` → PASS（dry-run 零改动 / --yes / 幂等 / 回滚）
- `python -B scripts/check_closeout_conflict_scan.py` → PASS（冲突/过期 + Git revision + 增量最小集）
- `python -B scripts/check_shiguan_full_record_index.py` → PASS（leaves/full-record）
- `python -B scripts/check_court_mcp_server.py` → ok:true（58 探针）；`check_unified_cli.py` → 9/9；`check_release_manifest.py` → ok:true（49）；`check_source_state_budget.py` → ok:true；`quick_validate.py .` → PASS；`check_read_only_contract.py` → ok:true（本机）

## 4. 遗留问题与风险

- 权威 O: 仓 bundle 未应用；repo-control doctor 需权威环境（沿用）。
- check_read_only_contract 本机转绿；正式安装机仍建议复验 E2。
- 新增 4 个独立 check 未纳入 P5-1 发布清单（建议 P5 登记）。
- `court_session_numbering` 分配文件为会话状态（court-runtime/session-numbering），与 closeout cursor 同级，不触发 git；生产首次使用前确认 court-runtime 目录可写。
- 跨午夜会话：分配日期与结诏日期不同时，`resolve_session_allocation` 按 date 匹配会回退新编号；如需跨日复用需在 P5 决策（当前语义：编号绑定分配日）。

## 5. 未决决策（需 REVIEWER 拍板）

1. Phase 3 出口评审：9 任务 + 附加"开始对话编号"旨意全绿，可否转 VERIFIED/COMPLETED。
2. "开始对话分配"的宿主接线方式：当前为 `domain_court_code_issue` API + `shiguan court-session-numbering issue` CLI，由宿主在会话开始时调用；是否需要在 `court open --fast`/intake 自动接线（建议：P5 评审后再接线，避免改 fastpath 语义）。
3. 跨午夜会话编号复用策略（建议保持"分配日绑定"）。
4. 新增 4 个 check 纳入 P5-1 清单。
5. Phase 0/1/2 出口评审闭环（沿用）。

## 6. 下阶段入口指针

- 阶段 4（M4，P4-1..P4-4）Codex 模型适配：从 P4-1 agent_runtime_probe 扩展开始；基座 scripts/agent_runtime_probe.py、scripts/court_model_router.py、scripts/court_codex_office_worker.py。
- 恢复读取协议：计划书 §3.3（1→7）；本文件 + phase-3-evidence.md + 任务书阶段 4 + git log/status 一致确认。

## 7. 交接自检

- [x] phase-3-evidence.md 存在且与声明一致
- [x] 门禁输出真实（见 evidence §7）
- [x] git status --porcelain 提交后为空
- [x] 无 push/tag/release/remote 操作（本地领先 origin 20 提交未推送）
- [x] index 空（git diff --cached 无内容）
- [x] 本阶段结尾即为手动交接点：请用户在新会话加载本文件继续
