# Phase 5 Evidence — 发布（M5）

> protocol_version: draft-0.1 · phase: 5 · branch: release/beta1.0.8（本地开发路径）
> 会话：hermes-codex-20260831-5（阶段 5 接续会话，authority=super, behavior=serial_inline）
> 门禁日志：docs/plans/beta1.0.8/phase-5-gates.log（含全部命令退出码与尾行输出）

## 1. P5-1 全量门禁

### 1.1 任务书 22 项（全部绿或环境受限记录）

| # | 门禁 | 结果 |
| --- | --- | --- |
| 1 | quick_validate.py . | PASS |
| 2 | check_governance_framework.py --json | PASSED checks=48 errors=0 |
| 3 | check_read_only_contract.py | ok:true |
| 4 | check_source_state_budget.py --json | ok:true |
| 5 | check_release_manifest.py --json | ok:true step_count=49 |
| 6 | check_unified_cli.py --all --json | status PASS |
| 7 | check_court_open_fastpath.py | PASS |
| 8 | check_startup_fastpath_contract.py | PASS |
| 9 | check_court_result_semantics.py | PASSED |
| 10 | check_cli_performance.py | PASS（warm fast p50=2.829ms；cold p50 改善 49.27%） |
| 11 | check_capability_index_gate.py --self-test | ok:true |
| 12 | check_release_legal.py | RELEASE_LEGAL PASSED |
| 13 | release_payload_manifest.py --self-test --check --json | ok:true self_test_ok=true（收据重生成后） |
| 14 | check_package_privacy.py | OK（64 tests / 56.17s） |
| 15 | check_shiguan_concurrency.py | SELF_TEST_OK（32 writers 原子替换） |
| 16 | check_shiguan_http.py | ok:true（36 static + live；loopback 127.0.0.1:8765 短启后停止） |
| 17 | check_codex_agent_roles.py | agents 14/14 synced、malformed=0、unsynced=0；config_errors=[max_depth, hide_spawn_agent_metadata]（环境） |
| 18 | check_active_copy_hashes.py --json | checked=293 drift=0 missing=0；extra=4 受保护史馆锚点（环境） |
| 19 | check_court_mcp_server.py | ok:true（58 探针） |
| 20 | check_skill_identity.py | PASSED（11 surfaces） |
| 21 | check_catalog.py --strict | PASS（CODEX_HOME=C:\Users\Administrator\.codex） |
| 22 | check_portability.py | ok:true |

### 1.2 Phase 2/3/4 新增独立 check（全部 PASS）

- check_court_code_session_numbering → COURT_CODE_SESSION_NUMBERING=PASS
- check_iku_repair → IKU_REPAIR=PASS（dry-run 零改动 / 幂等 / 回滚）
- check_closeout_conflict_scan → CLOSEOUT_CONFLICT_SCAN=PASS
- check_shiguan_full_record_index → SHIGUAN_FULL_RECORD_INDEX=PASS
- check_shiguan_lineage_taxonomy → SHIGUAN_LINEAGE_TAXONOMY=PASS
- check_shiguan_lineage_rebuild_compatibility → PASS
- check_shiguan_git_federation → SHIGUAN_GIT_FEDERATION_PASSED checks=20 errors=0
- check_court_model_router → ok:true（host-proof 正/反例）
- check_court_codex_office_worker → COURT_CODEX_OFFICE_WORKER_OK
- check_court_agent_config → COURT_AGENT_CONFIG_SELF_TEST_OK
- check_install_projection_closure → PASS（transitive closure）

## 2. 门禁处置与修复记录

1. **release_payload_manifest --check 初红**（missing-payload:scripts/iku_candidates.py；payload-drift 24 项；stale integrity）：release-manifest.json 自 beta1.0.7 收尾未刷新。处置：P5-1 先以 beta1.0.7 身份重生成（`--write`，ok:true），P5-2 锚点同步后以 beta1.0.8 身份重生成（307 files / 7,029,000 bytes），check 全绿。
2. **check_active_copy_hashes 初红**（18 项 extra）：执行发布期清理策略——14 项非保护残留（bin/decretum-matrix.js/.py、references/startup-tasks/README.md、installed-capabilities-catalog.example.md、shiguan-tree 种子 README×6、__pycache__ pyc×4）移入备份 `C:\Users\Administrator\.agents\install-backups\decretum-matrix\host-cleanup-20260831`（pyc 清除，可回滚）；4 项受保护史馆锚点按契约（NO_READ_NO_WRITE_NO_MOVE_NO_REWRITE）保留 → extra 收敛为 4。
3. **check_codex_agent_roles / check_catalog --strict 初红**：`$CODEX_HOME\agents` 缺 14 个官署角色。处置：`install update`（receipt d700750b…，create=0 replace=0 identical=293，STATUS=INSTALLED）+ `sync_codex_agents_from_profiles.py --write`（CODEX_HOME=.codex；written=14，hash 一致）→ check_catalog 转绿；check_codex_agent_roles 仅剩 config_errors（~/.codex/config.toml：agents.max_depth=4、features.multi_agent_v2.hide_spawn_agent_metadata=true 未设），ensure_court_agent_config --check → AGENT_CONFIG_REMINDER_ONLY blocking=false。
4. **check_shiguan_http 初红**（live 探针 connection refused）：`ensure_shiguan_web.py --port 8765` 短启服务 → ok:true（health_projection_ok / local_private_health_ok 全绿）→ 停止进程（pid 9976 pythonw），端口释放。
5. **check_install_current_agent_copy.py** self-test ValueError（'alias_prepare' not in list）：文件自 beta1.0.7 收尾 2571178 未变更（git diff 空），属既有问题，不在 P5-1 清单，记录不改。

## 3. P5-2 收据与锚点

- commit `5e0b660`（chore(beta1.0.8): P5-1 payload manifest receipt refresh + P5-2 version anchor sync to beta1.0.8）：
  VERSION=beta1.0.8；SBOM（documentNamespace=…beta1.0.8-20260811，冻结 EXPECTED_SBOM_CREATED=2026-08-11T00:00:00Z）；.codex-plugin/plugin.json；github-release-metadata latest_tag=beta1.0.8；skill-identity skill_sha256=5A481A1D…（LF 归一化）；SKILL.md version；README；CHANGELOG（beta1.0.8 - 2026-08-31）；docs/wiki/Release-Notes（beta1.0.8）；release-manifest.json 重生成（307 files / 7,029,000 B；payload_index_sha256=67a20cd5…）。
- 版本一致性子门：check_release_manifest（49 steps）、check_release_legal（SBOM 名称/namespace/license 对齐）、check_release_metadata（4 checks）、check_skill_identity（11 surfaces）全绿。
- 收据（绑定 HEAD `5e0b660`）：
  - docs/receipts/2026-08-31-beta1.0.8-source-final-receipt.json（schema decretum.beta108.source_final_receipt.v1）
  - docs/receipts/2026-08-31-beta1.0.8-install-host-closeout.json（schema decretum.beta108_closeout.v1）

## 4. P5-3 release 评审与批准

- 评审记录：docs/plans/beta1.0.8/release-review-beta1.0.8.md（门禁闭环汇总 + 环境受限项复验命令 + 批准记录模板，status=PENDING_REVIEWER）。
- workspace.yaml：本机开发路径不存在该文件；version.current → beta1.0.8 与外部发布动作列为权威环境批准后执行项（任务书范围内未执行任何 push/tag/release）。
- 未决决策：见 release-review §7（M5 出口评审、Phase 0-4 出口闭环、config 门禁归口、turn_context 路由语义衔接）。

## 5. 回归快照（2026-08-31 本机，锚点同步后最终复跑）

- quick_validate.py . → PASS；check_read_only_contract → ok:true；check_source_state_budget → ok:true
- check_release_manifest → ok:true(49)；release_payload_manifest --self-test --check → ok:true；check_release_legal → PASSED；check_release_metadata → PASSED(4)
- check_governance_framework → PASSED(48)；check_unified_cli → PASS；check_court_mcp_server → ok:true(58)；check_skill_identity → PASSED
- check_portability → ok:true；check_install_projection_closure → PASS
- check_active_copy_hashes → 293 一致 / extra=4（受保护锚点）；check_catalog --strict → PASS；check_codex_agent_roles → 14/14 + config_errors（环境）

## 6. 变更记录（阶段 5）

- 5e0b660 chore(beta1.0.8): P5-1 payload manifest receipt refresh + P5-2 version anchor sync to beta1.0.8
- （后续 docs commit：本 evidence + handoff + release-review + 收据 + 任务书/索引回写）
