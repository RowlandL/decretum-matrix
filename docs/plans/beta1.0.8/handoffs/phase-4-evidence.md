# Phase 4 Evidence — Codex 模型适配（M4）

> protocol_version: draft-0.1 · phase: 4 · branch: release/beta1.0.8（本地副本）
> 会话：hermes-codex-20260831-4（阶段 4 接续会话）· authority=super, behavior=parallel
> 契约：docs/plans/beta1.0.8/contracts/contract-c-codex-host-proof.md（FR-C，devspec §3.4）

## 1. P4-1 agent_runtime_probe 扩展（host proof 六字段）

- `scripts/agent_runtime_probe.py` probe() 新增顶层 `host_proof` 子对象，契约 C 六字段齐全：
  `codex_version`（codex --version 纯版本号，去 `codex-cli ` 前缀，与 fresh-worker host proof 的 `codex-cli {version}` 回拼兼容）、
  `codex_executable`（解析到的可执行路径，经 sanitize 脱敏）、
  `supported_model_effort_pairs`（list[{model,effort}]，来源 `court_model_router.MODEL_MAX_REASONING_EFFORT`，排序稳定）、
  `config_exposes_model`（bool，有效配置顶层 `model`/`model_provider` 探测）、
  `turn_context_model` / `turn_context_effort`（fresh-session JSONL 回读，仅取元数据字段，不读正文/凭据）。
- 无 Codex 环境（resolve ok=false）→ 六字段全 null 且不报错（`check_court_agent_config` 内 monkeypatch 断言）。
- 回读辅助 `_latest_turn_context`：只扫最近 5 个 `~/.codex/sessions/*.jsonl`（≤64MB、前 2000 行、禁符号链接），`turn_context` 事件取 payload.model/effort；任何失败 → (None, None) fail-closed。
- 本机实测（codex-cli 0.149.0-alpha.4.1）：

```json
{
  "codex_executable": "$CODEX_HOME\\plugins\\.plugin-appserver\\codex.exe",
  "codex_version": "0.149.0-alpha.4.1",
  "config_exposes_model": true,
  "supported_model_effort_pairs": [
    {"effort": "max",  "model": "gpt-5.6-luna"},
    {"effort": "ultra","model": "gpt-5.6-sol"},
    {"effort": "ultra","model": "gpt-5.6-terra"}
  ],
  "turn_context_effort": null,
  "turn_context_model": null
}
```

- 合成验证：最新 session JSONL 回读 → (gpt-5.6-sol, ultra)；`_config_exposes_model` 无配置 → None、有 `model` key → True、无 → False；monkeypatch resolve ok=false → 六字段全 null。
- 脱敏回归：`check_court_agent_config` 的 home 不泄露 + 无 Windows 绝对路径断言通过（codex_executable 输出为 `$CODEX_HOME/...`）。

## 2. P4-2 court_model_router host proof 绑定

- `scripts/court_model_router.py` 新增 `route_office_model_with_host_proof(route, host_probe)`（契约 C §2）：
  - 满足（codex_version 版本绑定 + supported_model_effort_pairs 含 (recommended_model, recommended_effort) + turn_context 回读一致）→ `model_override_applied=True` + `host_proof_sha256`（对版本/对集/回读的规范化 sha256，确定性）+ `model_route_status=APPLIED` + `runtime_degraded=False`。
  - 不满足 / 无证明 / 回读不一致 / 缺失 → 回退 `inherit_parent_model_and_effort` + `model_route_status=FAILED` + `runtime_degraded=True` + `errors[]`（不伪报；失败不带 digest）。
  - 显式继承（claude-code/hermes 或 codex 无推荐）→ `model_route_status=INHERIT`，非失败。
  - 兼容 fresh-worker proof 的 `model_effort_pairs` 字段名（`court.codex_fresh_worker_host_proof.v1` 子集）。
- `check_court_model_router.py` 新增 host-proof 正/反例全绿：
  - 正例：sol 路由 + 完整 host_probe → APPLIED + sha256（64 hex）+ 版本绑定；重复调用 digest 一致；worker 风格 proof 同样 APPLIED。
  - 反例（全部回退 inherit + FAILED + runtime_degraded）：host_probe=None / 空 / codex_version 缺失 / pairs 不含推荐对 / turn_context 缺失 / turn_context 不一致；claude 显式继承 → INHERIT 不降级；非法 route → ValueError。
- `python -B scripts/check_court_model_router.py` → `{"ok": true, "routes": {security/balanced/lightweight/claude/hermes}}`，exit 0。

## 3. P4-3 fresh-session worker 覆盖证明

- `scripts/court_codex_office_worker.py` 新增 `verify_worker_session_override(plan, session_path, *, expected_session_id, expected_cwd)`：
  - 回读 fresh-session JSONL（session_meta.id / turn_context.model / turn_context.effort / cwd）与 plan 一致 → `model_override_applied=True` + `model_route_status=APPLIED` + `runtime_degraded=False` + `status=completed`（复用既有 `verify_session_metadata`）。
  - 任一不一致 / 缺失（含文件不存在、无效 plan）→ `model_override_applied=False` + `model_route_status=FAILED` + `runtime_degraded=True` + `fallback=inherit_parent_model_and_effort` + `errors[]` + `status=degraded`；此证明路径不抛裸异常、不伪报。
- `check_court_codex_office_worker.py` 新增回读正/反例全绿：一致 → applied；model 不一致 / effort 不一致 / session id 不一致 / dossier cwd 不一致 / turn_context 缺失 / session 文件缺失 / 无效 plan → 全部 degraded + FAILED + fallback inherit。
- `python -B scripts/check_court_codex_office_worker.py` → `COURT_CODEX_OFFICE_WORKER_OK`，exit 0。

## 4. P4-4 模型适配回归

- `check_court_model_router.py` → ok:true（含 P4-2 正/反例）。
- `check_court_agent_config.py` → `COURT_AGENT_CONFIG_SELF_TEST_OK`（self-test 全量；新增 host_proof 字段集断言 + 无 Codex 全 null 断言 + pairs 结构断言）。
- `check_court_codex_office_worker.py` → OK。
- `check_source_state_budget.py --json` → ok:true（portable 341 files / 7,855,825 bytes；上限 345 / 7,900,000；probe 1310 行上限 / check worker 290 行上限——本次重基线）。
- `check_unified_cli.py --all --json` → status PASS；`check_release_manifest.py --json` → ok:true；`check_governance_framework.py` → PASSED checks=48 errors=0；`check_court_mcp_server.py` → ok:true（58 探针）；`quick_validate.py .` → PASS。
- `check_court_agent_config.py --live-runtime` → 本机 FAILED（native_effective errors=[max_depth, v2_bounds_or_reserved_schema]）：git stash 验证 baseline（f771afe）同样 FAILED，属本机 Codex 配置环境遗留（max_depth/v2 边界未达推荐），非本次回归破坏；正式安装机复验。

## 5. 回归快照（本机 2026-08-31）

- quick_validate.py . → PASS
- check_source_state_budget.py --json → ok:true（341 / 7,855,825；上限 345 / 7,900,000）
- check_release_manifest.py --json → ok:true（step_count=49）
- check_governance_framework.py → PASSED checks=48 errors=0
- check_unified_cli.py --all --json → status PASS
- check_court_mcp_server.py → ok:true（58 探针）
- check_court_model_router.py → ok:true（host-proof 正/反例含）
- check_court_codex_office_worker.py → COURT_CODEX_OFFICE_WORKER_OK
- check_court_agent_config.py → COURT_AGENT_CONFIG_SELF_TEST_OK（--live-runtime 环境遗留见 §4）

## 6. 变更记录（阶段 4）

- 3c3460c P4-1 agent_runtime_probe host proof 扩展（六字段 + null-safe + 回读/配置探测辅助）
- 7b7f50b P4-2 route_office_model_with_host_proof 绑定 + check 正/反例
- 448e9ec P4-3 fresh-session 回读覆盖证明（applied vs 回退 inherit + degraded）+ check 回读正/反例
- 8325be4 P4-4 回归断言（probe host_proof 字段/无 Codex null）+ source line budget 重基线

## 7. 环境与风险更新

- 本机 Codex：codex-cli 0.149.0-alpha.4.1（$CODEX_HOME/plugins/.plugin-appserver/codex.exe）；config_exposes_model=true；本机无 fresh-session turn_context 记录（turn_context_* 为 null，属正常探测结果）。
- `check_court_agent_config --live-runtime` 本机红（max_depth / v2_bounds_or_reserved_schema）为基线环境遗留（stash 验证），建议正式安装机按推荐配置（ensure_court_agent_config --apply --threads N）后复验。
- host proof 版本绑定闭环：probe 输出 `codex_version`（纯版本）↔ fresh-worker host proof 校验回拼 `codex-cli {version}` ↔ router `host_proof_codex_version` 绑定。
- 本阶段未新增 CLI 入口（4 个既有入口均已在 manifest），无需重生成 cli-command-surface / install-projection；仅 source-state-budget 行数重基线。
