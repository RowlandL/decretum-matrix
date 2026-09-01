# beta1.0.8 Release 评审与批准记录（P5-3）

> protocol_version: draft-0.1 · 阶段 5（M5 发布）· branch: release/beta1.0.8
> 评审人：门下 REVIEWER（本机开发路径 C:\Users\Administrator\a02-takeover\dm-dev）
> 状态：REVIEWER_SIGNED（用户授权 2026-08-31）· 批准后于权威环境执行 workspace.yaml 升版与外部发布动作（另行授权）

## 1. 门禁闭环汇总（P5-1，2026-08-31 本机）

### 1.1 任务书 22 项清单

| # | 门禁 | 结果 |
| --- | --- | --- |
| 1 | quick_validate.py . | PASS |
| 2 | check_governance_framework.py | PASSED（48 checks / errors=0） |
| 3 | check_read_only_contract.py | ok:true |
| 4 | check_source_state_budget.py --json | ok:true |
| 5 | check_release_manifest.py --json | ok:true（step_count=49） |
| 6 | check_unified_cli.py --all --json | status PASS |
| 7 | check_court_open_fastpath.py | PASS |
| 8 | check_startup_fastpath_contract.py | PASS |
| 9 | check_court_result_semantics.py | PASSED |
| 10 | check_cli_performance.py | PASS（warm fast p50=2.8ms / cold p50 改善 49.3%） |
| 11 | check_capability_index_gate.py | PASS（--self-test 门禁语义） |
| 12 | check_release_legal.py | RELEASE_LEGAL PASSED |
| 13 | release_payload_manifest.py --self-test --check | PASS（收据重生成后；见 §2） |
| 14 | check_package_privacy.py | OK（64 tests） |
| 15 | check_shiguan_concurrency.py | SELF_TEST_OK |
| 16 | check_shiguan_http.py | ok:true（36 static + live loopback 8765 短启后停止） |
| 17 | check_codex_agent_roles.py | 14/14 agents 已渲染同步；config_errors 2 项=本机 Codex 配置环境遗留（见 §3） |
| 18 | check_active_copy_hashes.py | 293/293 一致，drift=0；extra=4 受保护史馆锚点（见 §3） |
| 19 | check_court_mcp_server.py | ok:true（58 探针，含 Agent envelope/ACL/authority/write_set/现代+legacy） |
| 20 | check_skill_identity.py | PASSED（11 surfaces；skill_sha256 重绑 LF 归一化摘要） |
| 21 | check_catalog.py --strict | PASS（CODEX_HOME=.codex，14 agents + find-skills 在位） |
| 22 | check_portability.py | ok:true |

### 1.2 Phase 2/3/4 新增独立 check（任务书"另加"项）

| check | 结果 |
| --- | --- |
| check_court_code_session_numbering | PASS（开始分配→结诏复用） |
| check_iku_repair | PASS（dry-run 零改动 / --yes / 幂等 / 回滚） |
| check_closeout_conflict_scan | PASS（冲突/过期 + Git revision） |
| check_shiguan_full_record_index | PASS（leaves/full-record） |
| check_shiguan_lineage_taxonomy | PASS（合同 9 字段 + 否定/未知/冲突断言） |
| check_shiguan_lineage_rebuild_compatibility | PASS（编号 receipt 探针） |
| check_shiguan_git_federation | PASS（20 checks / errors=0，领域写入 Git commit） |
| check_court_model_router | ok:true（host-proof 正/反例 APPLIED/INHERIT/FAILED+degraded） |
| check_court_codex_office_worker | COURT_CODEX_OFFICE_WORKER_OK（回读正/反例） |
| check_court_agent_config | COURT_AGENT_CONFIG_SELF_TEST_OK（host_proof 字段集/null 断言） |
| check_install_projection_closure | PASS（transitive closure） |

## 2. P5-1 门禁处置记录

- `release_payload_manifest --self-test --check` 初跑红：release-manifest.json 自 beta1.0.7 收尾后未刷新（missing-payload:scripts/iku_candidates.py、payload-drift 24 项、stale integrity）。按收据重生成（P5-2 前以 beta1.0.7 身份、P5-2 锚点同步后以 beta1.0.8 身份）→ 全绿。
- `check_active_copy_hashes` 初跑红：18 项 extra（bin/ 2、startup-tasks、example catalog、shiguan-tree 种子 README 10、pyc 4）。执行发布期清理策略：14 项非保护残留移入备份 `C:\Users\Administrator\.agents\install-backups\decretum-matrix\host-cleanup-20260831`（可回滚），pyc 清除；剩余 4 项受保护史馆锚点按契约不动。
- `check_codex_agent_roles` / `check_catalog --strict` 初跑红：`$CODEX_HOME\agents` 14 个官署角色缺失。执行 `sync_codex_agents_from_profiles.py --write`（CODEX_HOME=.codex）→ 14/14 synced、hash 一致；check_catalog 转绿。
- `check_shiguan_http` 初跑红：live 探针无服务。`ensure_shiguan_web.py` 短启 127.0.0.1:8765 → 全绿 → 测试后停止服务、端口释放。

## 3. 环境受限项（正式安装机复验，本机不作为阻塞）

| 项 | 现状 | 复验/关闭命令（权威环境） |
| --- | --- | --- |
| check_active_copy_hashes extra=4 | 受保护史馆锚点（shiguan-index.jsonl / shiguan-knowledge-graph.json / shiguan-tree/_index.md / capability-index/_index.md）契约 NO_MOVE；干净安装根应无 extra | `python -B scripts/check_active_copy_hashes.py`（干净安装后） |
| check_codex_agent_roles config_errors | ~/.codex/config.toml 未达 agents.max_depth=4、features.multi_agent_v2.hide_spawn_agent_metadata=true；ensure_court_agent_config --check → REMINDER_ONLY blocking=false（非阻塞） | `python -B scripts/ensure_court_agent_config.py --apply --threads N` 后复验 `check_codex_agent_roles.py` / `check_court_agent_config.py --live-runtime` |
| repo-control doctor | 本机开发路径无法写权威 O:\ 仓；与 phase-0..4 沿用 | 权威环境补跑 `repo-control doctor` |

## 4. 已知既有问题（非本阶段回归，不在 P5-1 清单）

- `check_install_current_agent_copy.py` self-test 在 `_case_hermes_alias_commit_failure_restores_legacy_junction` 抛 `ValueError: 'alias_prepare' is not in list`：文件自 beta1.0.7 收尾（2571178）未变更，beta1.0.7 遗留，建议后续版本修复。

## 4.1 发布前 review 意见闭环（2026-08-31 独立 review 会话）

- 发现与修复详见 docs/plans/beta1.0.8/review/review-findings.md（R-01..R-12）：
  - R-01 [HIGH] check_install_current_agent_copy self-test：根因为 Windows MAX_PATH
    （长 fixture label × 深层 temp 嵌套 >260 字符 → 原子写 FileNotFoundError → alias
    ValueError 崩溃），另含 npm fixture 未隔离 CODEX_HOME / 尝试真实 superCC 安装。
    修复 4c290f3 → self-test 32/32 + 31/31 全绿。
  - R-02 [HIGH] IKU 只读探测经 ensure_shared_seed 产生共享史馆写副作用（契约 A 违反）。
    修复 b9dc9a9 + check_read_only_contract 新增只读探针。
  - R-03/R-04 [MEDIUM] MCP 内部运行时错误逃逸且漏写审计 journal；领域账本 commit
    receipt 持久化裸异常。修复 1366eee + check_court_mcp_server 两条新探针。
  - R-05 [LOW] closeout CLI 非法 as_of 裸回溯。修复 6a3b43f + CLI 探针。
  - R-06 [MEDIUM] repair/rollback 非原子写。修复 b9dc9a9（atomic_write_text/_bytes）。
  - R-07..R-12 记录为既有/建议项或环境受限（见 review-findings §2/§5）。
- 修复后门禁复跑：P5-1 22 项——20 项全绿 + 2 项环境受限记录（check_active_copy_hashes
  安装副本 beta1.0.7 遗留 + extra=4 受保护锚点；check_codex_agent_roles config_errors 2 项
  =本机 Codex 配置，14/14 已同步）；Phase 2/3/4 新增 11 个独立 check 全 PASS；
  release_payload_manifest 收据已重生成（d18d167）。
- 【第二轮 TDD 整改】用户指示继续 review + 鲁棒性整改（TDD），R-07..R-11 全部闭环：
  R-07 contract-b 措辞对齐（584ebfc）、R-08 registry 约束强制（b450f39）、
  R-09 session numbering 并发锁（4008307）、R-10 MCP 通用内部错误（b450f39）、
  R-11 turn_context 会话限定（fda5e71）；每项带 RED→GREEN 探针；
  第二轮回归 23 项全绿（review-gates-r2.log）；manifest 重生成（0d668094…）。
- 状态：review 意见已闭环（修复 + 回归断言 + 证据）；出口仍待 REVIEWER 签署（含 §7 未决决策）。

## 5. P5-2 收据与锚点（已完成）

- VERSION / SBOM / .codex-plugin/plugin.json / github-release-metadata / skill-identity / SKILL.md / README / CHANGELOG / docs/wiki/Release-Notes 全部同步 beta1.0.8（commit `5e0b660`）。
- release-manifest.json 重生成绑定 beta1.0.8（307 payload files / 7,029,000 bytes；payload_index_sha256=67a20cd5…）。
- skill-identity skill_sha256 重绑 LF 归一化 SKILL.md 摘要（5A481A1D…）。
- 收据：docs/receipts/2026-08-31-beta1.0.8-source-final-receipt.json、2026-08-31-beta1.0.8-install-host-closeout.json（绑定 HEAD `5e0b660`）。
- 版本一致性：check_release_manifest（49 steps）/ check_release_legal / check_release_metadata（4 checks）/ check_skill_identity 全绿。

## 6. 发布批准记录（待 REVIEWER 签署）

```json
{
  "schema": "decretum.beta108.release_approval.v1",
  "version": "beta1.0.8",
  "branch": "release/beta1.0.8",
  "head": "b8f2cd8",
  "gate_closure": "PASS_WITH_ENVIRONMENT_NOTES",
  "status": "REVIEWER_SIGNED",
  "approved_by": "REVIEWER（用户授权 2026-08-31，经发布前 review R-01..R-11 闭环 + 复验确认）",
  "approved_at_utc": "2026-08-31T14:40:00Z",
  "approval_actions": [
    "已复验（本机）：安装副本同步 beta1.0.8（drift=0）、check_catalog --strict PASS、check_codex_agent_roles 14/14；check_active_copy_hashes extra=4 受保护史馆锚点 + repo-control doctor 需权威环境（环境受限，见 §3/R-12）",
    "workspace.yaml version.current -> beta1.0.8：权威环境批准后执行（本机无此文件）",
    "外部 tag / GitHub Release / npm 发布：另行单独授权，本任务书范围不执行"
  ]
}
```

## 7. 未决决策（REVIEWER 拍板）

1. Phase 5（M5）出口评审：门禁 22 项 + 新增 check 全绿（含 2 项环境受限记录），收据/锚点绑定 HEAD，可否转 VERIFIED/COMPLETED。
2. Phase 0/1/2/3/4 出口评审闭环（沿用，待 REVIEWER）。
3. `--live-runtime` / check_codex_agent_roles 的 config 门禁归口：本机环境遗留是否记入 P5 已关闭清单（建议：正式安装机复验，本机不作为阻塞）。
4. turn_context 为 null 时路由语义（P4-2 无回读环境回退 FAILED 不伪报）在真实 fresh worker 运行后的衔接确认。

## 8. 最终收尾（2026-09-01，HEAD 942ba3a）——发布就绪

REVIEWER 指示"彻底收尾 beta1.0.8 并准备线上发布"。收尾动作与结果：

### 8.1 本阶段追加工作（全部闭环）
- R-13 召回算法按 `shiguan-hierarchical-index-design.md` **全量落地**：
  P0-1/2/3（四态断言/TF-IDF/字段剔除）、A+B+D（状态语义面/假设轴）、L0a 谱系面、
  L0b 编号段位面、P1-1 去重+可解释、P1-2 倒排+缓存（load 16.8ms→0.1ms）、P2-1 gbrain
  命名、P2-2 同义词、L2 向量面、RRF 融合；`check_shiguan_recall_precision` 27 探针全绿。
- A+B 脚本分层全量迁移（checks 86 / commands 47 / services 12 / 根壳 ~145 /
  库 46 保持根），命令名/id 不变，`check_unified_cli --all` PASS（145 条目）。
- **收尾抓取并修复的迁移回归**：`check_skill_identity` 指向根壳导致
  registry_api/legacy_migration 检查失败（11 surfaces 一度 FAILED）→ 修复为指向
  `scripts/commands/` 真身，11 surfaces PASSED；`NON_PUBLIC_ENTRYPOINTS` 更新为真身
  路径，维护工具恢复 source_only（source_only=6）。

### 8.2 门禁最终状态（2026-09-01 本机复跑）
- 全绿：quick_validate / release_legal / release_metadata(4) / release_manifest(49) /
  release_payload_manifest self-test(7,472,502 B) / skill_identity(11) / unified_cli(145) /
  governance(48) / court_mcp_server(62) / recall_precision(27) / lineage_taxonomy /
  full_record_index / git_federation(20) / session_numbering / iku_repair / closeout /
  model_router / codex_office_worker / agent_config / projection_closure / concurrency /
  http / portability / budget(431 files / 7,988,100 B) / package_privacy(64)。
- 环境受限（正式安装机复验，本机不作为阻塞）：check_active_copy_hashes drift=0、
  **extra=4 受保护史馆锚点**；check_codex_agent_roles 14/14、config_errors=2。

### 8.3 发布就绪结论
- 版本锚点：VERSION=beta1.0.8、CHANGELOG/Release-Notes/plugin.json/SBOM/skill-identity/
  release-manifest 一致；source-final receipt 已更新绑定 **HEAD 942ba3a**。
- §7 未决决策 1/2/3 已在 REVIEWER_SIGNED（2026-08-31）闭环；第 4 项 turn_context
  由 R-11 修复 + check_court_agent_config 探针覆盖，本机无 fresh worker 环境，
  记入正式安装机复验项。
- **外部发布动作（另行单独授权）**：权威环境 workspace.yaml 升版 →
  正式安装机复验（clean install + repo-control doctor + config 门禁）→
  打 tag（建议 `beta1.0.8` 或 `v1.0.8`）→ GitHub Release / npm 发布 →
  镜像分支同步（P:/O:）。本任务书范围不执行上述外部动作。

### 8.4 线上发布闭环（2026-09-01，用户授权 GitHub + GitHub Packages npm）

用户指示"线上 GitHub 发布 + GitHub 自带 npm，发布对象 release/beta1.0.8"，全部完成：

1. **发布产物构建链**（连续修复 5 个发布前回归/契约问题）：
   - PROVENANCE.md 及全部 tracked 文本恢复 LF（与 HEAD blob 一致，消除
     manifest 归一化哈希 vs 工作副本 CRLF 的漂移）；
   - 145 个兼容壳重建为 `getattr(main)` + `runpy.run_path(run_name="__main__")`
     fallback（修复 `check_package_privacy` 等 `unittest.main()` 入口无 `main` 的崩溃）；
   - 7 处 `Path(__file__).with_name(...)` 同目录假设改指权威路径；
   - 从 CLI_SUPPORT_FILES / install-projection 排除 release-only validators
     （release-manifest.json、scripts/release_payload_manifest.py、
     scripts/check_release_gate.py），满足 npm postinstall 契约；
   - RELEASE-LOG.md 补 beta1.0.8 章节（release-notes 资产来源）。
2. **GitHub 线上**（已推送并验证）：
   - 分支 `release/beta1.0.8`（HEAD `5214e44`）；annotated tag `beta1.0.8`（`66e6c14`）；
   - GitHub Release：https://github.com/RowlandL/decretum-matrix/releases/tag/beta1.0.8
     （prerelease，body 版本摘要）；
   - 资产 4 件：`decretum-matrix-beta1.0.8.zip`（7,683,559 B，SHA256 `333e2773…`）、
     `.zip.sha256`、`release-attestation.json`、`SBOM.spdx.json`。
3. **GitHub Packages npm**（已发布并验证）：
   - 包 `@rowlandl/decretum-matrix@1.0.8-beta.0`，tag `beta`，access public；
   - 认证：gh device flow（机器码经局域网代理 192.168.3.110:7890 完成授权，
     scope `repo,write:packages`；token 仅临时 `~/.npmrc`，用后即删、不回显）；
   - fresh install 冒烟：`npm install @rowlandl/decretum-matrix@beta
     --registry=https://npm.pkg.github.com` → `added 1 package`，
     `decretum-matrix --version` → `beta1.0.8`。
4. **镜像**：P:\decretum-matrix 已同步分支与 tag beta1.0.8；O:\ 备用镜像未动。
5. **凭据卫生**：device code / access token / 临时 .npmrc 全部删除，无持久化。

遗留（正式安装机/权威环境）：workspace.yaml 升版、clean install 复验、
repo-control doctor、config 门禁（max_depth/v2 bounds）、turn_context fresh
worker 衔接。
