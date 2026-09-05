# Decretum Matrix 交接文档（2026-08-31 → 2026-09-06）

> 给后续会话 / 其他 agent：本文档汇总本工作区间**做了什么、在哪、现状如何、下一步**。
> 覆盖：beta1.0.8 发布前 review 闭环 → 召回算法全量落地 → A+B 脚本分层重构 →
> beta1.0.8 线上发布（GitHub Release + GitHub Packages npm）→ 安装核查与修复 →
> 真实开朝测试 → Taizi/三省语义纠正 → release/beta1.0.9 分支 + 本机安装。

## 0. 权威位置速览

| 项 | 值 |
| --- | --- |
| 当前分支 | `release/beta1.0.9`（HEAD `0003b38`，已推送 P: 与 GitHub） |
| beta1.0.8 发布分支 | `release/beta1.0.8`（HEAD `37df40d`，已发布并推送 P:/GitHub） |
| GitHub 仓库 | `https://github.com/RowlandL/decretum-matrix` |
| 镜像 remote | `origin = P:\decretum-matrix`；`o = O:\decretum-matrix`（备用）；`github`（HTTPS，走代理 192.168.3.110:7890） |
| 权威设计/评审文档 | `docs/plans/beta1.0.8/review/shiguan-hierarchical-index-design.md`、`mcp-recall-review.md`、`review-findings.md`、`release-review-beta1.0.8.md`、`scripts/README.md` |
| 本机安装 | canonical `.agents\skills\decretum-matrix` = **beta1.0.9**（active-copy PASS） |
| GitHub 线上 | Release `beta1.0.8`（含 ZIP/SHA/attestation/SBOM）；npm `@rowlandl/decretum-matrix@1.0.8-beta.0`（tag `beta`） |

---

## 1. 工作全景（按时间）

### 1.1 beta1.0.8 发布前 review 闭环（R-01..R-11 + R-13）
- R-01..R-11（更早会话，本区间接手时已闭环并签署）：安装 self-test 崩溃、IKU 只读、
  MCP 错误逃逸、ledger 裸异常、CLI 裸回溯、原子写、契约 B 措辞、registry 约束、
  session numbering 并发锁、MCP 错误回显、turn_context 会话限定。
- **R-13（本会话核心）**：MCP/CLI 召回算法三要素评分（准确率 5 / 无关信息 4 / 工程化 6）
  后按用户批准落地 P0→P1/P2→L0a/L0b→A+B+D 全量优化（见 §2）。
- REVIEWER 签署：task-book M0-M5 COMPLETED、release-review §8 发布就绪。

### 1.2 召回/分层索引算法全量落地（beta1.0.8）
见 §2 与 `docs/SOURCE-ANALYSIS-2026-09-06.md` §1。

### 1.3 A+B 脚本分层重构（beta1.0.8）
见 §3 与源码分析 §2。

### 1.4 beta1.0.8 线上发布（用户授权 GitHub + GitHub Packages npm）
见 §4。

### 1.5 本机安装核查与修复 + 真实开朝测试 + 语义纠正（beta1.0.9）
见 §5/§6/§7。

---

## 2. 召回算法（R-13 / 分层索引设计）做了什么

**设计文档**：`docs/plans/beta1.0.8/review/shiguan-hierarchical-index-design.md`
（P0/P1/P2/L0a/L0b/L2/RRF 全部落地，§3.1-3.3 记录）。

落地内容（全部在 `scripts/shiguan_entry_utils.py`，单核召回器）：

| 项 | 实现 | 提交 |
| --- | --- | --- |
| P0-3 字段污染 | 剔除 source/evidence/next/capability_source_paths/court_code_legend | b835768 |
| P0-1 否定 | 子句否定不贡献正分 | 0314e6b |
| P0-2 TF-IDF | 词条化 + BM25 IDF + 阈值；非判别查询回退 latest-N | 7746f1f / d0850f4 |
| A+D 四态断言 | affirmed/negated/uncertain/hypothetical + 作用窗口 + 软惩罚 | c71d22d |
| B 状态语义面 | 状态别名可查询（失败→REJECTED 等），绝不排除 | dc567cb |
| L0a 谱系面 | 谱系受控词前缀/子树命中 | fc4ff52 |
| L0b 编号段位面 | 四字码 risk/value/priority + 日期/编号前缀 | fc4ff52 |
| P1-1 去重/可解释 | 同题折叠；matched_terms/fields/structural + breakdown | 23e443c |
| P2-1 gbrain 命名 | GBrain=元数据增强层（docstring） | 23e443c |
| P2-2 同义词 | 中英直译等价扩展 | 913e48e |
| P1-2 倒排+缓存 | RecallIndex 候选剪枝；load_entries stat 缓存（16.8ms→0.1ms） | 20ea330 |
| L2+RRF | 向量面 + recall_rrf/select_matches_rrf | 20ea330 |

**回归门禁**：`scripts/checks/check_shiguan_recall_precision.py`（27 探针，PASSED）。

**关键决策**：召回/索引是**纯算法层**——数据权威始终是 md 派生 jsonl；倒排/缓存/去重
均为内存派生，不写回文档，源 mtime 变更即失效（兼容性原则已写入设计 §3.3）。

---

## 3. A+B 脚本分层重构做了什么

**分层契约文档**：`scripts/README.md`。

198 个 `scripts/*.py` 整理为：
```
L0 入口层   court_cli.py / court_mcp_server.py
L1 适配层   court_cli_registry / court_public_api / domain_ledger_api
L2 领域层   scripts/commands/（47 命令）· scripts/services/（12 服务）
L3 门禁层   scripts/checks/（86 check）
L4 库层     46 个无 __main__ 模块（保持 scripts/ 根，禁止移动）
```
- 入口脚本真身迁入子目录；**根目录 145 个兼容壳**经 `sys.modules` 替换 + `getattr(main)`
  + `runpy` fallback，直接 `python scripts/xxx.py` 与 `import xxx` 全部兼容。
- `check_unified_cli.py`：`COMPATIBILITY_SHELL_ENTRYPOINTS`（壳跳过重复发现）、
  `RETIRED_COMPATIBILITY_ENTRYPOINTS`（服务退役）、`NON_PUBLIC_ENTRYPOINTS`（真身化，
  source_only=6）；命令名/id 全部不变（manifest 145 条目）。
- 命令名/id 不变；CLI 直接跑真身（isolated_subprocess 指向子目录）。
- **相对路径纪律**：所有定位用 `Path(__file__).resolve().parents[N]`/`Path.home()`/
  环境变量；绝对路径仅允许注释标注的测试负例。
- 发布期追加修复：145 壳 main/runpy fallback（`unittest.main()` 入口）、7 处
  `with_name` 同目录假设、skill_identity 真身探针、NON_PUBLIC 真身化。

提交：01b1085（试点）→ 9f8e424（checks 批 86）→ 094fa6d（commands/services 批 57）→
6de192e（壳重建）→ 942ba3a（skill_identity/NON_PUBLIC）→ 5214e44（release-only 投影排除）。

---

## 4. beta1.0.8 线上发布（已完成，用户授权）

**GitHub**（https://github.com/RowlandL/decretum-matrix/releases/tag/beta1.0.8）：
- 分支 `release/beta1.0.8` + annotated tag `beta1.0.8`（66e6c14 → 5214e44）。
- 资产 4 件：`decretum-matrix-beta1.0.8.zip`（SHA256 `333e2773…`）+ `.zip.sha256` +
  `release-attestation.json` + `SBOM.spdx.json`。

**GitHub Packages npm**：
- `@rowlandl/decretum-matrix@1.0.8-beta.0`（tag `beta`，public）。
- fresh install 冒烟：`npm install @rowlandl/decretum-matrix@beta
  --registry=https://npm.pkg.github.com` → `decretum-matrix --version` = beta1.0.8。

**构建链修复（发布前抓到的真实问题）**：
1. PROVENANCE/权威文件 CRLF 漂移（manifest 归一化哈希 vs 工作副本）→ 全部 tracked
   恢复 LF（=HEAD blob）。
2. release-only validators（release-manifest.json、release_payload_manifest.py、
   check_release_gate.py）泄漏进安装面 → 从投影排除。
3. RELEASE-LOG.md 缺 beta1.0.8 章节（release-notes 资产来源）→ 补齐。

**凭据卫生**：gh device-flow 经代理 192.168.3.110:7890 完成授权（scope
repo+write:packages）；机器码/access token/临时 `.npmrc` 全部删除，无持久化、无回显。

---

## 5. 本机安装核查与修复

- Codex：`~/.codex\skills\decretum-matrix` = SymbolicLink → canonical；**已装最新**。
- Hermes / Hermes Studio：经 `.agents\skills`（r0）共享加载，**可用**。
- Claude：`.claude\skills` **无** decretum-matrix（未装，需单独补装）。
- 修复：`check_active_copy_hashes` 误读 npm-postinstall receipt（glob 限定
  install-*.json）；独立哈希校验器不得进入安装面（投影与副本排除）。
  提交 37df40d（beta1.0.8）。

---

## 6. 真实开朝流程测试（super 并行）

在 beta1.0.8 上执行：三权（super+parallel）→ `court create` → 三省定性
（semantic checkpoint/verify → DISPATCHABLE）→ `court open --fast` PASS →
`agent-admit`（六部 worker bindings + 官方 preload/budget lease）→ **真实派遣六部
worker**（6 个并行进程，各写 `court.open_court_worker_receipt.v1`，exit=0）。

**如实受限项**：
1. codex exec（LLM 级子 agent）在 Hermes 沙箱 runs 无响应 → 退化为本机进程级 worker；
2. `agent-admit` 最终 `approved_budget_not_active_exhausted`（budget ledger 激活属
   court 状态机内部门禁）；
3. **语义偏差（后续纠正）**：当时把"三省定性"做成 machine receipt 且 actor 标中书/门下，
   跳过了 Taizi（太子 intake）flow 阶段，且语义 receipt ≠ 三省官署派遣。

---

## 7. Taizi/三省语义纠正 + release/beta1.0.9 + 本机安装

**历史语义（查证锚定）**：
- 太子 = 受旨定性（intent inference / 历史线索初判 / 建立结果章程），在三省会审**前**
  （Legal state `Pending → Taizi → ThreeDepartments → …`）。
- 问题拆解（decomposition）= **中书省**拟旨阶段职责（court-offices-dispatch 官署表）。
- `semantic checkpoint/verify` 的 DISPATCHABLE = 三省会审的 **P00 语义门禁**，不构成
  中书/门下/尚书官署被派遣或履职；需官署回奏须 `agent-admit` + host-native
  spawn/reuse/wake 或显式 `serial_inline`，否则 `runtime_degraded`/`PARTIAL`。

**落地（不过拟合，仅文档/帮助）**：SKILL.md 职责链与"职责边界"、`court open` 帮助第 3 条、
`court_runtime` docstring。提交 735e746（beta1.0.9）。

**版本化**：VERSION/SKILL metadata/CHANGELOG/plugin.json → beta1.0.9。提交 0003b38。

**本机安装**：`sync_active_copies --write` → canonical=beta1.0.9（VERSION=beta1.0.9、
SKILL 含职责边界、`court open --help` 新语义）；Codex 链接环境=beta1.0.9；
active-copy PASS（drift=0/extra=0）。Hermes/Hermes Studio 经 r0 共享自动更新。

---

## 8. 当前状态与下一步

### 仓库
- `release/beta1.0.9` HEAD=`0003b38`，工作树干净，已推送 P: 与 GitHub。
- `release/beta1.0.8` HEAD=`37df40d`（已发布）；`release/beta1.0.7` 为 origin HEAD 基线。
- 发布锚点（release-manifest/SBOM/Release-Notes/github-metadata）仍锚定 **beta1.0.8**；
  beta1.0.9 完整发布锚点与对外发布在 **1.0.9 发布准备期**统一执行（沿用 beta1.0.8 先例）。

### 本机安装
- canonical + Codex + Hermes/Hermes Studio = **beta1.0.9**；Claude 未装。
- 权威复验遗留：clean install、`repo-control doctor`、config 门禁（max_depth/v2 bounds）、
  turn_context fresh worker 衔接、Claude 补装（如需）。

### 建议下一步
1. 用 beta1.0.9 语义重跑一次开朝（先真实派遣三省、再差遣六部），验证纠正生效；
2. 补齐 Claude 环境安装（如需）；
3. beta1.0.9 发布准备：锚点升版 → 门禁全量 → GitHub Release + npm `1.0.9-beta.0`。

---

## 9. 关键文档索引

| 文档 | 内容 |
| --- | --- |
| `docs/SOURCE-ANALYSIS-2026-09-06.md` | 本会话源码改动分析（推荐先读） |
| `scripts/README.md` | 脚本四层分层与纪律 |
| `docs/plans/beta1.0.8/review/shiguan-hierarchical-index-design.md` | 分层索引设计（全落地） |
| `docs/plans/beta1.0.8/review/mcp-recall-review.md` | 召回三要素评分与 P0 闭环 |
| `docs/plans/beta1.0.8/review/review-findings.md` | R-01..R-13 发现与闭环 |
| `docs/plans/beta1.0.8/release-review-beta1.0.8.md` | 发布评审/签署/线上发布闭环 |
| `docs/receipts/2026-08-31-beta1.0.8-source-final-receipt.json` | 源码终态收据 |
| `SKILL.md` | 诏令矩阵 skill（含 Taizi/三省职责边界） |

> 本文档为 append-only 交接记录；如后续继续推进，请在本文档追加新节并同步 HEAD。
