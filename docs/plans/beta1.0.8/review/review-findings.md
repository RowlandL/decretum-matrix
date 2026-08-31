# beta1.0.8 发布前 Coding Review + 鲁棒性审计 发现与闭环

> protocol_version: draft-0.1 · 会话：hermes-codex-20260831-review（发布前 review 会话；第二轮 TDD 整改 2026-08-31）
> 分支：release/beta1.0.8 · 审查基线 b2de371..HEAD（E1-E5 / P1.x-P4.x / P5 锚点收据）
> 修复后 HEAD：见 §3 提交列表（第一轮 R-01..R-06 + 第二轮 TDD R-07..R-11，叠加在 d3a7f7d 之上）
> 门禁日志：docs/plans/beta1.0.8/review/review-gates.log
> 结论摘要：6 类问题（4 类已修复含回归断言；2 类记录为既有/环境受限）；P5-1 22 项门禁复跑全绿或环境受限记录；Phase 2/3/4 新增独立 check 全 PASS；check_install_current_agent_copy self-test 由「抛 ValueError 崩溃」转为 32/32 + 31/31 全绿。

---

## 1. 审查范围与方法

- 代码审查：`b2de371..HEAD` 全部改动（27 提交，+6704/-224）+ 关键既有脚本。
- 对照契约：contract-a（IKU 三态/只读）、contract-b（编号/谱系/分类 9 字段）、contract-c（host proof 六字段/路由）、contract-d（MCP 工具矩阵/审计/领域写入）。
- 对照任务书：P1-1..P2-6 / P3-1..P3-9 / P4-1..P4-4 / P5-1..P5-3 逐项验收。
- 开发规范：docs/plans/2026-08-28-decretum-matrix-beta1.0.8-development-spec.md（只读边界、原子写、失败闭合、幂等、隐私）。
- 重点：不伪报（runtime_degraded/FAILED 语义）、fail-closed、ensure_* --check 零副作用、编号/谱系 receipt 权威、审计可重放、ACL/authority/write_set、安装投影一致性、Windows 路径/编码、并发/幂等、配置/环境敏感点。

---

## 2. 发现清单（编号 / 严重度 / 证据 → 处置）

### R-01 [HIGH, 已修复] check_install_current_agent_copy.py self-test 崩溃（Windows MAX_PATH + 隔离性）

- 现象（beta1.0.7 遗留，任务书明列候选修复）：
  `_case_hermes_alias_commit_failure_restores_legacy_junction` 抛
  `ValueError: 'alias_prepare' is not in list`。
- 根因（本会话取证）：描述性 fixture label（50+ 字符）叠加
  `home/.agents/install-backups/decretum-matrix/projection-<32hex>/preimages/0000-<tool>/...`
  深层嵌套后，真实 temp 路径超过 Windows 260 字符上限；
  `_atomic_create` 的 `NamedTemporaryFile`/`os.replace` 在 `_backup_projection_writes`
  内抛 `FileNotFoundError`（对 `.SKILL.md.install-<hex>` 临时文件）。安装器在到达
  alias 处理前即失败，`adapter.events` 为空 → 事件索引崩溃。同一根因还使
  `frozen_reference_replaced_and_refrozen` / `legacy_locator_migrates_atomically_to_canonical`
  / `canonical_existing_root_updates_through_staged_transaction` / `npm_blank_host_...`
  多个用例在完整自测序列中误报失败（此前被 alias 崩溃掩盖）。
- 次级隔离问题：`_check_npm_postinstall_fixture` 未隔离 `CODEX_HOME`，把
  `sync_active_copies` 写到了环境 CODEX_HOME（本会话为 Hermes 沙箱 runs 目录，
  实测生成 14 个官署 agent toml）；`_install_supercc_dependencies` 在
  `DECRETUM_MATRIX_SKIP_SUPERCC_DEPS` 未设时尝试向 `C:\Tools\bin` 安装 zellij/squad
  （真实安装尝试）。与 `temporary_fixtures_only=true`、`real_cc_switch_or_codex_accessed=false`
  的声明不符。
- 修复（提交 4c290f3）：
  1. `_fixture_slug()`：对每个 fixture 用短 CRC-32 子目录；覆盖 `_case_fixture`、
     npm fixture、blank-host config、hermes config path 用例；并把
     `TemporaryDirectory` 前缀缩短为 `ctr-`/`cbr-`。
  2. npm fixture 增加 `CODEX_HOME=home/.codex`、`COURT_TOOL_INSTALL_DIR=home/.tools`、
     `DECRETUM_MATRIX_SKIP_SUPERCC_DEPS=1` 隔离（写路径全部落入临时目录）。
  3. alias 事件断言改为缺步时干净失败（不再裸 `ValueError`）。
- 回归：`check_install_current_agent_copy.py --self-test` → `ok:true`，
  `passed_cases=32/32`、`passed_configuration_cases=31/31`、`errors=[]`
  （修复前：崩溃于 alias 用例，且 4 个用例 FileNotFoundError）。

### R-02 [HIGH, 已修复] IKU 只读探测路径存在共享史馆播种副作用（契约 A 违反）

- 证据（本会话隔离环境复现）：`public_iku_candidates()`（MCP `shiguan.iku_candidates`
  投影）→ `detect_candidates()` → `archive_root()` → `ensure_shared_seed()`，
  在共享根缺失时创建 `references/` 目录、种子 README、`shiguan-index.jsonl`、
  `shiguan-knowledge-graph.json`、写锁文件等（实测 20+ 项变更）。
- 影响：契约 A「dry-run 前后目录字节级不变 / 不执行任何写入」被破坏；
  只读 MCP 工具产生写副作用；`check_read_only_contract` 未覆盖该路径（盲区）。
- 修复（提交 b9dc9a9）：`iku_candidates.archive_root()` 与
  `repair_archive_placeholders.archive_root()` 改为纯 `reference_path("plan-archives")`
  解析（播种归安装/apply 路径）。
- 回归（新增断言）：`check_read_only_contract.py` 新增
  `iku_candidates_public_api_dry_run` 探针——隔离 env 下运行
  `public_iku_candidates`，断言零文件系统变更（修复前该探针必红）。

### R-03 [MEDIUM, 已修复] MCP 内部运行时错误逃逸且不写审计 journal（契约 D2）

- 证据：`court_mcp_server.call_tool` 仅捕获 `(ImportError, TypeError, ValueError)`；
  public API 抛 `OSError`（如 load_entries 失败）时逃逸到 `handle()` 的
  `-32603` 兜底，且不产生 journal 条目，违反「成功与失败均产生 journal」。
- 修复（提交 1366eee）：捕获集扩为 `(ImportError, OSError, RuntimeError, TypeError, ValueError)`，
  返回 JSON-RPC 错误结果并继续走 `_write_mcp_audit`。
- 回归：`check_court_mcp_server.py` 新增 `mcp_call_tool_fails_closed_on_runtime_error`
  探针（mock `invoke_public_tool` 抛 OSError → 断言 isError=true / ok=false）。

### R-04 [MEDIUM, 已修复] domain_ledger_write 提交后 receipt 持久化裸异常

- 证据：Git commit 成功后，把 `git_commit` 写回 ledger 文件的第二次
  `_atomic_write_text` 未包 try/except；`OSError` 时抛裸异常（此时 commit 已存在，
  属「已提交却返回失败」的半一致状态）。
- 修复（提交 1366eee）：包 try/except，失败返回 `ok:false` +
  `commit_receipt_persist_failed`（不谎称成功、不破坏 auditability 绑定）。
- 回归：`check_court_mcp_server.py` 新增
  `domain_write_commit_receipt_persist_failure_returns_error` 探针（mock 第二次原子写抛 OSError）。

### R-05 [LOW, 已修复] closeout_conflict_scan CLI 对非法 --as-of 裸回溯

- 证据：`main()` 将用户 `--as-of` 直接传入 `scan()`；非法值抛
  `ValueError("as_of_invalid")` 并以 traceback 终止。
- 修复（提交 6a3b43f）：`main()` 捕获 ValueError，stderr 输出
  `CLOSEOUT_CONFLICT_SCAN_INVALID`，返回码 2。
- 回归：`check_closeout_conflict_scan.py` 新增 CLI 探针
  （`--as-of garbage` → 断言 exit 2 + 无 traceback）。

### R-06 [MEDIUM, 已修复] repair_archive_placeholders apply/rollback 非原子写（规范违反）

- 证据：`apply_repairs` 用 `Path.write_text/write_bytes`、`rollback` 用
  `target.write_bytes` 直接覆写；中断时可能截断记录。违反 devspec「不新增裸 open(w) /
  沿用 court_file_lock 原子写」。
- 修复（提交 b9dc9a9）：目标文件与 journal 改用 `atomic_write_text`；备份与 rollback
  改用新增 `_atomic_write_bytes`（temp + os.replace + fsync）。
- 回归：既有 `check_iku_repair`（apply 后字节、备份、journal、rollback 恢复、幂等）全绿。

### R-07 [LOW, 已修复（TDD 第二轮, docs-only）] 契约 B 文档与实现的状态枚举漂移

- 证据：contract-b §2 声明 `classification_status` 枚举
  `classified | tie | unknown | conflict | review`；实现仅输出 `classified | review`，
  tie/unknown/conflict 通过 `classification_reason` 区分。
  `classification-contract-validation.json` 五类用例也以 `status=review + reason`
  断言。内部一致、check 全绿，但契约措辞与实现不符。
- 修复（提交 584ebfc）：契约文档改为实现语义——`classification_status ∈ {classified, review}`，
  `classification_reason ∈ {matched, tie, conflict, unknown, low_confidence, negated_evidence}`；
  验收指针同步（tie/unknown/negated/conflict → status=review + reason）。
- 回归：check_shiguan_lineage_taxonomy / rebuild_compatibility 保持 PASS。

### R-08 [LOW, 已修复（TDD 第二轮）] court_public_registry._validate_value 不强制 string/array 约束

- 证据：`_validate_value` 只强制 type / additionalProperties / required / 数值 min-max；
  不强制 minLength/maxLength/minItems/maxItems/enum/pattern。例如
  `dispatch_plan_validate` 的 `entries` maxItems=16 在 wire 层不生效（由 public 函数
  内部处理）。
- 修复（提交 b450f39）：`_validate_value` 补 string minLength/maxLength/pattern/enum 与
  array minItems/maxItems + 任意类型 enum 强制。
- 回归（TDD）：check_court_mcp_server 新增 `wire_schema_constraints_enforced` 探针
  （8 例：entries maxItems/minItems、authority/behavior/scope enum、query/charter/task_id
  长度）——RED（8 例未强制）→ GREEN。

### R-09 [MEDIUM, 已修复（TDD 第二轮）] court_session_numbering 并发分配竞态

- 证据：`domain_court_code_issue` 的 read-compute-write（读存量 allocations →
  `_next_sequence` → 写 allocation 文件）未持文件锁；同日期并发会话可能取到相同
  `daily_sequence`（碰撞 court_code）。
- 修复（提交 4008307）：整个 read-compute-write（含幂等重查）由
  `court_file_lock.file_lock` 串行化（`<numbering_root>/.allocation.lock`）。
- 回归（TDD）：check_court_code_session_numbering 新增确定性并发探针
  （patched `_next_sequence` 放大窗口，两线程同时进入读算区）——
  RED（overlap 检测 + 序列碰撞 '1','1'）→ GREEN（无 overlap、序列互异）。

### R-10 [LOW, 已修复（TDD 第二轮）] MCP -32603 内部错误向客户端回显异常文本

- 证据：`handle()` 兜底 `_error(-32603, str(exc))` 会回显内部路径/异常信息。
- 修复（提交 b450f39）：main() 的逐消息分发抽为 `_dispatch()`，内部异常统一返回
  `-32603 "Internal error"`，详情写 stderr（服务端可查，客户端不回显）。
- 回归（TDD）：check_court_mcp_server 新增 `mcp_internal_error_generic_message`
  探针——RED（回显 secret-detail）→ GREEN（code=-32603、无 detail）。

### R-11 [LOW, 已修复（TDD 第二轮）] agent_runtime_probe `_latest_turn_context` 取最近会话回读

- 证据：`_latest_turn_context(home)` 读取最近 5 个 Codex session JSONL 的
  `turn_context` 事件作为 host proof 的 turn-context 证据，可能来自其他 agent/session。
  缺失/不一致时 fail-closed（不会误报 APPLIED），但理论上可能满足校验。
- 修复（提交 fda5e71）：新增可选 `session_id` 过滤，指定时仅读取该 session JSONL
  （精确证据）；未指定时保持 host 级最近会话近似（兼容既有调用）。
- 回归（TDD）：check_court_agent_config 新增会话限定探针（两个 session JSONL，
  断言按 session_id 回读对应 model/effort）——RED（TypeError unexpected keyword）→ GREEN。

### R-12 [INFO] 环境受限项复核（按任务书登记，不得擅动，仅记录）

- `check_active_copy_hashes`：本机安装副本 `~/.agents/skills/decretum-matrix` 仍为
  **beta1.0.7**（与 repo beta1.0.8 全面漂移：README/SKILL/VERSION/SBOM/版本锚点 +
  本次 review 修改的脚本）；另有 `extra=4` 受保护史馆锚点。属本机安装状态遗留，
  需权威环境 `install update` / `sync_active_copies` 后复验；本会话未做安装/同步。
- `check_codex_agent_roles`：`CODEX_HOME=C:\Users\Administrator\.codex` 下
  agents 14/14 同步、malformed=0、unsynced=0；`config_errors=2`
  （`agents.max_depth=4`、`features.multi_agent_v2.hide_spawn_agent_metadata=true`
  未设，`ensure_court_agent_config --check → REMINDER_ONLY`）。环境受限，正式安装机复验。
- `check_catalog --strict`：需显式 `CODEX_HOME=C:\Users\Administrator\.codex` →
  PASS（默认沙箱 CODEX_HOME 缺 find-skills 属会话环境）。
- `repo-control doctor`：需权威 O:\ 仓环境，本机沿用 phase-0..4 记录。
- 本会话沙箱 CODEX_HOME 曾被 R-01 修复前的 npm fixture 写入 14 个官署 agent toml
  （20:07，修复后已隔离）；属会话 ephemeral 目录，不影响正式环境。

---

## 3. 修复提交列表

| 提交 | 主题 | 关联发现 |
| --- | --- | --- |
| 4c290f3 | fix(beta1.0.8): install-current-agent-copy self-test on Windows MAX_PATH + hermetic npm fixture | R-01 |
| b9dc9a9 | fix(beta1.0.8): make IKU detection read-only (no shared-root seeding) and atomic repair writes | R-02, R-06 |
| 1366eee | fix(beta1.0.8): fail closed on MCP/domain-ledger runtime errors and keep audit + receipt binding | R-03, R-04 |
| 6a3b43f | fix(beta1.0.8): closeout conflict scan CLI fails closed on invalid as_of | R-05 |
| d18d167 | chore(beta1.0.8): regenerate release payload manifest after review fixes | R-01..R-06 源码漂移收据 |
| 221e122 | docs(beta1.0.8): publish pre-release coding review + robustness audit closure | 回写（findings/log/task-book/release-review/handoffs） |
| 754552b | chore(beta1.0.8): refresh release payload manifest after review docs commit | docs 提交后 repository_only 漂移收据 |
| c0c8fa6 | docs(beta1.0.8): phase-5 VERIFIER handoff-check artifact (phase-5-check.json) | 交接校验产物 |
| b450f39 | fix(beta1.0.8): enforce wire schema constraints and generic MCP internal errors (R-08/R-10, TDD) | R-08, R-10 |
| 4008307 | fix(beta1.0.8): serialize session-numbering allocation read-compute-write (R-09, TDD) | R-09 |
| fda5e71 | fix(beta1.0.8): scope host-proof turn-context read-back to a session (R-11, TDD) | R-11 |
| 584ebfc | docs(beta1.0.8): align contract B classification_status wording with implementation (R-07) | R-07 |

---

## 4. 回归结果（修复后，本机 2026-08-31）

### 4.1 P5-1 任务书 22 项门禁

| # | 门禁 | 结果 | 说明 |
| --- | --- | --- | --- |
| 1 | quick_validate.py . | PASS | |
| 2 | check_governance_framework.py --json | PASSED (48 checks) | |
| 3 | check_read_only_contract.py | ok:true | 含新增 iku 只读探针 |
| 4 | check_source_state_budget.py --json | ok:true | 341 files / 7,866,857 B，预算内 |
| 5 | check_release_manifest.py --json | ok:true (49 steps) | |
| 6 | check_unified_cli.py --all --json | PASS | |
| 7 | check_court_open_fastpath.py | PASS | |
| 8 | check_startup_fastpath_contract.py | PASS | |
| 9 | check_court_result_semantics.py | PASSED | |
| 10 | check_cli_performance.py | PASS | |
| 11 | check_capability_index_gate.py --self-test | ok:true | |
| 12 | check_release_legal.py | PASSED | |
| 13 | release_payload_manifest.py --self-test --check --json | ok:true | 修复后重生成（7,036,543 B） |
| 14 | check_package_privacy.py | OK (64 tests) | |
| 15 | check_shiguan_concurrency.py | SELF_TEST_OK | |
| 16 | check_shiguan_http.py | ok:true | loopback 8765 短启后停止，36 static + live |
| 17 | check_codex_agent_roles.py | 14/14 synced；config_errors=2（环境） | CODEX_HOME=.codex |
| 18 | check_active_copy_hashes.py --json | drift（安装副本 beta1.0.7 遗留）+ extra=4（环境） | 见 R-12 |
| 19 | check_court_mcp_server.py | ok:true | 58+2 探针 |
| 20 | check_skill_identity.py | PASSED | |
| 21 | check_catalog.py --strict | PASS | CODEX_HOME=.codex |
| 22 | check_portability.py | ok:true | |

### 4.2 Phase 2/3/4 新增独立 check（全部 PASS）

- check_court_code_session_numbering / check_iku_repair / check_closeout_conflict_scan /
  check_shiguan_full_record_index / check_shiguan_lineage_taxonomy /
  check_shiguan_lineage_rebuild_compatibility / check_shiguan_git_federation /
  check_court_model_router / check_court_codex_office_worker / check_court_agent_config /
  check_install_projection_closure → 全部 EXIT=0。

### 4.3 新增回归断言

- check_read_only_contract：`iku_candidates_public_api_dry_run`（R-02）。
- check_court_mcp_server：`mcp_call_tool_fails_closed_on_runtime_error`（R-03）、
  `domain_write_commit_receipt_persist_failure_returns_error`（R-04）。
- check_closeout_conflict_scan：`cli_invalid_as_of_fail_closed`（R-05）。
- check_install_current_agent_copy：self-test 32/32 + 31/31（R-01）。
- check_court_mcp_server（第二轮）：`wire_schema_constraints_enforced`（R-08）、
  `mcp_internal_error_generic_message`（R-10）。
- check_court_code_session_numbering（第二轮）：并发 overlap + 序列互异探针（R-09）。
- check_court_agent_config（第二轮）：turn_context session 限定探针（R-11）。

### 4.4 第二轮 TDD 整改后回归（2026-08-31，review-gates-r2.log）

- 23 项复跑全绿（quick_validate / read_only / source_budget / release_manifest /
  release_payload_manifest / release_legal / release_metadata / skill_identity /
  governance / unified_cli / court_mcp_server / portability / projection_closure /
  session_numbering / iku_repair / closeout_conflict / full_record_index /
  lineage_taxonomy / rebuild_compatibility / git_federation / model_router /
  codex_office_worker / agent_config）。

---

## 5. 遗留项（后续版本候选 / 需 REVIEWER 拍板）

1. R-07..R-11 已在第二轮 TDD 整改中闭环（见 §2/§3），不再列入遗留。
2. 环境受限项（R-12）正式安装机复验：install update 到 beta1.0.8、config.toml 门禁、
   repo-control doctor。
