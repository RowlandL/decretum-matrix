# Phase 4 Handoff — Codex 模型适配（M4）

- protocol_version: draft-0.1
- phase: 4
- status: VERIFY_READY
- handoffer_session: hermes-codex-20260831-4（阶段 4 接续会话，authority=super, behavior=parallel）
- started_at: 2026-08-31T22:10:00+08:00 (approx)
- finished_at: 2026-08-31T23:05:00+08:00 (approx)
- git_branch: release/beta1.0.8
- git_head_commit: 8325be4
- working_tree_clean: true（提交后；index 空）

## 1. 目标达成

- P4-1 agent_runtime_probe 扩展：完成。`probe()` 输出契约 C 六字段（`host_proof` 子对象）：codex_version / codex_executable / supported_model_effort_pairs / config_exposes_model / turn_context_model / turn_context_effort；无 Codex 环境时六字段全 null 且不报错；回读仅取 fresh-session 元数据（不读正文/凭据）；路径过 sanitize 脱敏。
- P4-2 court_model_router host proof 绑定：完成。`route_office_model_with_host_proof(route, host_probe)`：满足 → model_override_applied=YES + host_proof_sha256 + model_route_status=APPLIED；不满足/无证明/回读不一致 → 回退 inherit_parent_model_and_effort + FAILED + runtime_degraded（不伪报）；显式继承 → INHERIT；check_court_model_router.py 正/反例全绿。
- P4-3 fresh-session worker 覆盖证明：完成。`court_codex_office_worker` 接 host proof（既有 validate_host_proof/build_worker_plan/run_worker 不变），新增 `verify_worker_session_override`：fresh-session JSONL 回读 session id/model/effort/dossier cwd 一致 → applied；不一致/缺失 → 回退 inherit + degraded（不抛裸异常）；check_court_codex_office_worker.py 回读正/反例全绿。
- P4-4 模型适配回归：完成。check_court_model_router.py → ok:true；check_court_agent_config.py → SELF_TEST_OK（新增 probe host_proof 字段集/无 Codex null 断言）；source-state-budget 重基线后全绿；unified_cli/release_manifest/governance/mcp_server/quick_validate 全绿。

## 2. 变更文件清单

- M scripts/agent_runtime_probe.py（P4-1：host_proof 六字段 + _latest_turn_context/_config_exposes_model 辅助）
- M scripts/court_model_router.py（P4-2：route_office_model_with_host_proof + _canonical_json）
- M scripts/check_court_model_router.py（P4-2：host-proof 正/反例断言）
- M scripts/court_codex_office_worker.py（P4-3：verify_worker_session_override + _degraded_override）
- M scripts/check_court_codex_office_worker.py（P4-3：回读正/反例断言）
- M scripts/check_court_agent_config.py（P4-4：probe host_proof 字段集/无 Codex null/pairs 结构断言）
- M references/manifests/source-state-budget.v1.json（P4-4：probe 1310 / check worker 290 行数重基线）
- A docs/plans/beta1.0.8/handoffs/phase-4-evidence.md / phase-4-handoff.md（本文件）

## 3. 验收命令与输出

| 命令 | 期望 | 实际 |
| --- | --- | --- |
| `python -B scripts/agent_runtime_probe.py --format json` | 含 host_proof 六字段；本机 codex 0.149.0-alpha.4.1 | 六字段齐全（见 evidence §1） |
| `python -B scripts/check_court_model_router.py` | ok:true + host-proof 正/反例 | ok:true，exit 0 |
| `python -B scripts/check_court_codex_office_worker.py` | COURT_CODEX_OFFICE_WORKER_OK | 一致，exit 0 |
| `python -B scripts/check_court_agent_config.py` | SELF_TEST_OK（live 另述） | 一致，exit 0 |
| `python -B scripts/check_source_state_budget.py --json` | ok:true | ok:true（341 / 7,855,825） |
| `python -B scripts/check_unified_cli.py --all --json` | status PASS | PASS |
| `python -B scripts/check_release_manifest.py --json` / `check_governance_framework.py` / `check_court_mcp_server.py` / `quick_validate.py .` | 全绿 | 全绿（49 / 48 checks / 58 探针 / PASS） |

不一致标注：`check_court_agent_config.py --live-runtime` 本机 FAILED（native_effective errors=[max_depth, v2_bounds_or_reserved_schema]）；git stash 验证 baseline 同样 FAILED，属本机 Codex 配置环境遗留，非本阶段回归。

## 4. 遗留问题与风险

- 权威 O: 仓 bundle 未应用；repo-control doctor 需权威环境（沿用）。
- check_read_only_contract 本机已转绿；正式安装机仍建议复验（沿用）。
- `check_court_agent_config --live-runtime` 需本机 Codex 配置达标（max_depth≥4、v2 bounds/保留 schema）方可全绿；正式安装机建议先 `ensure_court_agent_config.py --apply --threads N` 再复验。
- 本机无 fresh-session turn_context 记录（turn_context_model/effort=null）：P4-2 正例在真实无回读环境下会回退 FAILED——这是"不伪报"的设计语义；有实际 fresh worker 运行后回读即转 APPLIED。
- 新增/修改的 check 无新 CLI 入口，manifest 无需重生成；source-state-budget 行数已重基线（probe 1310 / check worker 290）。

## 5. 未决决策（需 REVIEWER 拍板）

1. Phase 4 出口评审：P4-1..P4-4 全绿（含 host proof 正/反例 + 回退路径），可否转 VERIFIED/COMPLETED。
2. `--live-runtime` 环境门禁的归口：本机环境遗留（max_depth/v2 bounds）是否记入 P5-1 门禁前置条件（建议：正式安装机复验，本机不作为阻塞）。
3. turn_context 为 null 时的路由语义（当前：无回读证明 → FAILED 回退，不伪报）：是否在 P5 评审确认与 fresh worker 实际运行后的回读衔接。
4. Phase 0/1/2/3 出口评审闭环（沿用，待 REVIEWER）。

## 6. 下阶段入口指针

- 阶段 5（M5，P5-1..P5-3）发布：从 P5-1 全量门禁开始（任务书 P5-1 22 项清单 + 本阶段新增 check：check_court_model_router / check_court_codex_office_worker / check_court_agent_config + Phase 3 新增 4 个独立 check 建议纳入）。
- 恢复读取协议：计划书 §3.3（1→7）；本文件 + phase-4-evidence.md + 任务书阶段 5 + git log/status 一致确认。

## 7. 交接自检

- [x] phase-4-evidence.md 存在且与声明一致
- [x] 门禁输出真实（见 evidence §5）
- [x] git status --porcelain 提交后为空
- [x] 无 push/tag/release/remote 操作（本地领先 origin 24 提交未推送）
- [x] index 空（git diff --cached 无内容）
- [x] 本阶段结尾即为手动交接点：请用户在新会话加载本文件继续
