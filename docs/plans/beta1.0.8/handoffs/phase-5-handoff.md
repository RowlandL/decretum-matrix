# Phase 5 Handoff — 发布（M5）

- protocol_version: draft-0.1
- phase: 5
- status: COMPLETED（REVIEWER 用户授权 2026-08-31；见 handoffs/README 索引与 release-review §6 REVIEWER_SIGNED）
- handoffer_session: hermes-codex-20260831-5（阶段 5 接续会话，authority=super, behavior=serial_inline）
- started_at: 2026-08-31T19:00:00+08:00 (approx)
- finished_at: 2026-08-31T20:20:00+08:00 (approx)
- git_branch: release/beta1.0.8
- git_head_commit: 5e0b660（内容提交）；发布前 review（R-01..R-06 + TDD 第二轮 R-07..R-11）后 HEAD=3bd2d5a（本 handoff 文档随后续 docs commit 提交）
- working_tree_clean: true（提交后；index 空）

## 1. 目标达成

- P5-1 全量门禁：任务书 22 项清单 + Phase 2/3/4 新增独立 check 全部执行；20 项全绿，2 项环境受限记录（check_active_copy_hashes extra=4 受保护史馆锚点；check_codex_agent_roles config_errors 本机 Codex 配置）——均为契约保护或本机环境遗留，正式安装机复验。
- P5-2 收据与锚点：VERSION / SBOM / plugin / github-release-metadata / skill-identity / SKILL.md / README / CHANGELOG / Release-Notes 全部同步 beta1.0.8（commit 5e0b660）；release-manifest.json 重生成绑定 beta1.0.8（307 files / 7,029,000 B）；source-final 与 install-host-closeout 收据生成绑定 HEAD 5e0b660；版本一致性子门（release_manifest/release_legal/release_metadata/skill_identity）全绿。
- P5-3 release 评审与批准：评审记录 docs/plans/beta1.0.8/release-review-beta1.0.8.md 已生成（含批准记录模板，status=PENDING_REVIEWER）；workspace.yaml 本机不存在，升版列为权威环境批准后执行项；任务书范围内未执行任何 push/tag/release。

## 2. 变更文件清单

- M release-manifest.json（P5-1 收据重生成：beta1.0.7→beta1.0.8 身份，307 files）
- M VERSION / SBOM.spdx.json / .codex-plugin/plugin.json / references/manifests/github-release-metadata.v1.json（beta1.0.8）
- M references/manifests/skill-identity.v1.json（skill_sha256 重绑 LF 归一化 5A481A1D…）
- M SKILL.md（version: beta1.0.8） / README.md / CHANGELOG.md / docs/wiki/Release-Notes.md（beta1.0.8 条目）
- M scripts/package_skill.py / release_payload_manifest.py / build_release_artifacts.py / check_release_legal.py（RELEASE_LABEL/VERSION_CORE/SBOM 常量）
- A docs/receipts/2026-08-31-beta1.0.8-source-final-receipt.json / 2026-08-31-beta1.0.8-install-host-closeout.json
- A docs/plans/beta1.0.8/release-review-beta1.0.8.md
- A docs/plans/beta1.0.8/phase-5-gates.log（门禁日志）
- A docs/plans/beta1.0.8/handoffs/phase-5-evidence.md / phase-5-handoff.md（本文件）
- M docs/plans/2026-08-28-decretum-matrix-beta1.0.8-task-book.md（M5 状态回写）
- M docs/plans/beta1.0.8/handoffs/README.md（Phase 5 索引行）

## 3. 验收命令与输出

| 命令 | 期望 | 实际 |
| --- | --- | --- |
| `python -B scripts/release_payload_manifest.py --self-test --check --json` | ok:true | ok:true（307 files；self_test 26 项） |
| `python -B scripts/check_release_manifest.py --json` | ok:true steps=49 | ok:true |
| `python -B scripts/check_release_legal.py` | PASSED | PASSED |
| `python -B scripts/check_release_metadata.py` | PASSED | PASSED checks=4 |
| `python -B scripts/check_skill_identity.py` | PASSED | PASSED（11 surfaces） |
| `python -B scripts/check_source_state_budget.py --json` | ok:true | ok:true |
| `python -B scripts/check_catalog.py --strict` | PASS | PASS（CODEX_HOME=.codex） |
| `python -B scripts/check_codex_agent_roles.py` | 14/14 + 无 config errors | 14/14 synced；config_errors 2 项=环境 |
| `python -B scripts/check_active_copy_hashes.py` | 全绿（干净安装） | 293 一致 / extra=4 受保护锚点（环境） |
| `python -B scripts/check_court_mcp_server.py` | ok:true | ok:true（58 探针） |
| `python -B scripts/quick_validate.py .` | PASS | PASS |

## 4. 遗留问题与风险

- 【发布前 review 已闭环】docs/plans/beta1.0.8/review/review-findings.md：
  R-01..R-06 修复（4c290f3/b9dc9a9/1366eee/6a3b43f/d18d167），R-07..R-12 记录为
  既有/建议项或环境受限。修复后 P5-1 复跑：20 项全绿 + 2 项环境受限；Phase 2/3/4
  新增独立 check 全 PASS；check_install_current_agent_copy self-test 32/32 + 31/31。
- 权威 O: 仓 bundle 未应用；repo-control doctor 需权威环境（沿用 phase-0..4）。
- check_active_copy_hashes：本机安装副本 `~/.agents/skills/decretum-matrix` 仍为
  beta1.0.7（与 repo beta1.0.8 全面漂移）+ extra=4 受保护史馆锚点（契约 NO_MOVE）；
  需权威环境 `install update` / `sync_active_copies` 后复验；本会话未做安装/同步。
- check_codex_agent_roles / check_court_agent_config --live-runtime：~/.codex/config.toml 需 agents.max_depth=4、features.multi_agent_v2.hide_spawn_agent_metadata=true；正式安装机建议先 `ensure_court_agent_config.py --apply --threads N` 再复验（本机未改用户配置，保持 REMINDER_ONLY 语义）。
- check_install_current_agent_copy.py self-test：已由发布前 review 修复
  （4c290f3），32/32 + 31/31 全绿（此前 ValueError 崩溃）。
- 本机安装副本已按发布期清理策略收敛（14 项残留移入备份 host-cleanup-20260831，可回滚）。
- turn_context 为 null 的路由语义（P4-2）：真实 fresh worker 运行后回读即转 APPLIED；当前无回读环境回退 FAILED 不伪报（设计语义）。

## 5. 未决决策（需 REVIEWER 拍板）

1. Phase 5（M5）出口评审：门禁闭环 + 收据/锚点绑定，可否转 VERIFIED/COMPLETED。
2. 发布批准签署（release-review §6 批准记录）：批准后于权威环境执行 workspace.yaml version.current → beta1.0.8。
3. Phase 0/1/2/3/4 出口评审闭环（沿用，待 REVIEWER）。
4. check_active_copy_hashes extra=4 受保护锚点的处置口径：保留为环境受限项（建议）或另行授权迁移。
5. 本机 Codex 配置（max_depth/v2 bounds）是否由用户在正式安装机应用。

## 6. 下阶段指针

- beta1.0.8 开发阶段全部完成（M0-M5）；REVIEWER 评审闭环后：权威环境应用 bundle → repo-control doctor → 干净安装复验（§4 命令）→ 发布批准签署 → workspace.yaml 升版 → 外部发布另行授权。
- 后续版本候选：修复 check_install_current_agent_copy self-test；turn_context 实际运行衔接验证。
  发布前 review 追加候选：R-07 契约 B 措辞对齐、R-08 registry 约束强制、
  R-09 session numbering 并发锁、R-10 MCP 错误回显、R-11 turn_context 会话限定。

## 6.1 第三轮 TDD 补充（R-13：MCP 召回 P0 优化 + 分层索引设计，2026-08-31）

- 用户批准三 P（P0-1/2/3）可行，并指示基于古制谱系 + 诏令编号做独立分层索引算法
  （联网调研先进方案与数学算法后出详细方案）。
- 修复提交（HEAD 已推进到 9cd6384，已推送 P:\decretum-matrix）：
  - `b835768` P0-3 剔除 source/evidence/next/capability_source_paths/court_code_legend
  - `0314e6b` P0-1 否定感知召回
  - `7746f1f` P0-2 词条化 + BM25 IDF + 阈值/判别性准入
  - `d0850f4` P0-2 补丁：非判别性查询回退 latest-N（保住 check_shiguan_full_record_index）
  - `a27fb43` CLI 表面注册新 check；`22e4218` 设计文档 + 证据回写；`9cd6384` payload 收据重生成
- 实测（真实索引 8 条）：archive 7→2、史馆 8→latest-N、IKU 3→0、super 6→4、codex 4、
  find-skills 2、结诏 3；排序与人工判断一致。
- 门禁：新增 `check_shiguan_recall_precision.py`（9 探针）PASSED；check_governance 48、
  check_court_mcp_server 62、full_record_index、lineage_taxonomy/rebuild/git_federation 全绿；
  check_unified_cli PASS（清单注册后）；release_payload_manifest --self-test --check ok:true；
  source-state-budget ok（342 files / 7,889,248 B）；install 副本已重同步（drift=0；
  extra=4 受保护史馆锚点，环境受限）。
- 分层索引设计：`docs/plans/beta1.0.8/review/shiguan-hierarchical-index-design.md`
  （谱系前缀索引 L0a + 编号复合键/段位桶 L0b + 文本倒排 L1 + RRF 融合；P1/P2 落地路线）。

## 6.2 A+B+D 断言感知召回追加（2026-08-31，用户批准；HEAD 68632c0）

- 否定判定升级为**四态断言**（NegEx/ConText 风格）：affirmed/negated/uncertain/
  hypothetical + 作用窗口；否定为软惩罚（负分）而非零贡献/硬过滤（TREC 2025 风格）。
- 记录**状态成为可查询相关性语义面**（STATUS_SEMANTICS 中英别名：失败→REJECTED、
  打断→BLOCKED、余险→DONE_WITH_CONCERNS、部分→PARTIAL…）：查询命中状态语义即
  加分召回，普通查询零贡献、绝不排除（用户明确：状态本身有意义，按相关性分析判断）。
- 提交：`c71d22d`（A+D 四态断言）、`dc567cb`（B 状态语义面）、`b69daa1`（docs）、
  `68632c0`（payload 收据）。真实索引：`部分`→3×PARTIAL、`余险`→DONE_WITH_CONCERNS、
  普通查询不变。门禁：recall_precision 14 探针 PASSED、governance 48、lineage_taxonomy
  （否定 golden 兼容）、full_record、mcp_server 62、unified_cli、budget、payload
  self-test 全绿。

## 7. 交接自检

- [x] phase-5-evidence.md 存在且与声明一致
- [x] release-review-beta1.0.8.md / 两份收据存在且绑定 HEAD 5e0b660
- [x] 门禁输出真实（见 evidence §1/§2 与 phase-5-gates.log）
- [x] 发布前 review 闭环：review-findings.md + review-gates.log；修复后门禁复跑记录
- [x] git status --porcelain 提交后为空
- [x] 第三轮 TDD（R-13）已推送镜像 P:\decretum-matrix（dae8bfb..9cd6384）；无 tag/release/外部发布
- [x] index 空（git diff --cached 无内容）
- [x] 本阶段结尾即为手动交接点：请用户在新会话加载本文件继续（评审/批准）
