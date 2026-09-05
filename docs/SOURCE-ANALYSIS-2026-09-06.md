# Decretum Matrix 源码分析（2026-08-31 → 2026-09-06）

> 面向后续 agent：本文件按子系统分析本工作区间**改动的源码**：改动位置、关键函数、
> 设计意图、验证方式。仓库状态：`release/beta1.0.9` HEAD `0003b38`。

---

## 1. 召回核心：`scripts/shiguan_entry_utils.py`（单核召回器）

本文件是 MCP `shiguan.query` / `shiguan.entries_query` / `domain_gbrain_recall` 与 CLI
`query-shiguan-index` 共用的召回唯一实现（beta1.0.8 收敛目标）。

### 1.1 关键常量
- `RECALL_EXCLUDED_FIELDS`：source/evidence/next/capability_source_paths/
  court_code_legend 不参与召回（P0-3，防路径子串伪命中）。
- `RECALL_MIN_SCORE=1.0`、`RECALL_MIN_IDF=0.4`：文本准入阈值与判别性下限。
- `ASSERTION_AFFIRMED/NEGATED/UNCERTAIN/HYPOTHETICAL` + `ASSERTION_WEIGHT`
  （1.0/-1.0/0.5/0.3）：四态断言（NegEx/ConText 风格；否定为软惩罚）。
- `CONTENT_UNCERTAINTY_MARKERS` / `CONTENT_HYPOTHETICAL_MARKERS` + 作用窗口
  `ASSERTION_SCOPE_CHARS=60`。
- `STATUS_SEMANTICS` + `COURT_CODE_FACET_ALIASES` + `LINEAGE_TERMS`：状态语义面与
  编号/谱系结构面词表。
- `RECALL_SYNONYMS`：直译等价（史馆↔shiguan、记忆↔memory、编号↔court_code、索引↔index）。
- `RECALL_DEDUPE_FIELDS`：同题去重键字段。

### 1.2 关键函数（按调用链）
| 函数 | 职责 |
| --- | --- |
| `_weighted_searchable_parts` | 参与召回的字段+权重（不含被剔除字段） |
| `_taxonomy_assertion_status` / `_taxonomy_match_is_negated` | 四态断言 / 二值否定（分类器兼容保留） |
| `_recall_query_tokens` | 查询词条化 + 同义词扩展（大小写 fold） |
| `recall_idf` | BM25 IDF（`ln((N-df+0.5)/(df+0.5)+1)`） |
| `score_entry_recall` / `score_entry_recall_breakdown` | 单条 TF-IDF 分 / 可解释分项 |
| `_status_facet_score` / `_court_code_facet_score` / `_lineage_facet_score` | 结构面加分 |
| `_recall_vector_facet_score` | L2 词袋向量重叠（仅排序） |
| `_is_structural_token` | 结构词判定（谱系/段位/日期 ≥4 位/编号前缀 ≥6 位） |
| `RecallIndex.candidates` / `build_inverted_index` | 倒排候选剪枝 |
| `recall_rrf` / `select_matches_rrf` | RRF 融合（`1/(k+rank)`） |
| `select_matches` | 主入口：非判别+非结构→latest-N；文本/结构混合准入；去重 |
| `load_entries` | stat-keyed 内存缓存（path,mtime_ns,size），cap 8 |

### 1.3 验证
`scripts/checks/check_shiguan_recall_precision.py`：27 探针（路径污染负例、否定负例、
常见词 latest-N、断言权重序、状态面 失败/打断、L0b 高风险/高价值、L0a 朝制前缀、
去重、matched_fields、同义词、倒排等价、RRF、load 缓存复用）。

---

## 2. 脚本分层（scripts/ 目录结构）

### 2.1 目录
```
scripts/
  court_cli.py / court_mcp_server.py / court_cli_registry.py  根驻留（L0/L1）
  check_unified_cli.py / court_runtime.py / court_session_closeout.py
  / archive_checkpoint.py                                       根驻留（自举/特殊 handler）
  <145 个入口兼容壳>                                             sys.modules 替换壳
  checks/   86 个 check_* 真身（L3 门禁）
  commands/ 47 个命令真身（L2）
  services/ 12 个守护/服务真身（RETIRED，不注册命令）
  README.md                                                    分层契约
```

### 2.2 兼容壳机制（根文件，如 `scripts/check_package_privacy.py`）
```python
from checks import check_package_privacy as _real
sys.modules[__name__] = _real          # import 壳名即得真身
if __name__ == "__main__":
    _main = getattr(_real, "main", None)
    if callable(_main): sys.exit(_main())
    import runpy                         # 无 main（unittest.main() 等）时以 __main__ 跑真身
    runpy.run_path(str(.../真身.py), run_name="__main__")
```

### 2.3 `scripts/check_unified_cli.py`（入口覆盖门禁）
- `COMPATIBILITY_SHELL_ENTRYPOINTS`：壳路径 → discover 跳过（避免重复注册）。
- `RETIRED_COMPATIBILITY_ENTRYPOINTS`：服务/退役工具真身。
- `NON_PUBLIC_ENTRYPOINTS`：维护工具保持 source_only（真身路径，=6）。
- `_tracked_script_paths` 用 `git ls-files -- scripts`（递归，含子目录）。
- `--write-manifest` 重生成 `cli-command-surface.v1.json` + install-projection cli_public。

---

## 3. 安装/发布面修复

### 3.1 `scripts/checks/check_active_copy_hashes.py`
- `_load_latest_install_receipt`：glob 由 `*.json` 改为 `install-*.json`（排除
  npm-postinstall 收条污染 → 修复误报 receipt 缺字段）。

### 3.2 `references/manifests/install-projection.v1.json`
- 从 shared_agents/portable_current_tool/cli_public 排除：
  release-only validators（release-manifest.json、scripts/release_payload_manifest.py、
  scripts/check_release_gate.py）与独立哈希校验器（scripts/check_active_copy_hashes.py
  根壳 + checks 真身）——满足 npm postinstall 契约"安装面不含校验器/发布工具"。

### 3.3 `references/manifests/source-state-budget.v1.json`
- source_lines 键随迁移指向真身路径；portable_source 重基线（520 files / 8.6MB，
  壳是薄转发层）；个别文件迁移注入行数重基线（intake 620/governance 785/codex_office_worker 470）。

---

## 4. 语义层（Taizi / 三省 / court 开朝）

### 4.1 `SKILL.md`
- "Pinned Initial Court Anchors"：普通官署履职正确开局改写为
  `三权已明 → 太子定性(Taizi) → 三省会审(中书拟旨/拆解·门下封驳·尚书评估；DISPATCHABLE
  仅语义门禁) → host-native dispatch/serial_inline`。
- "Court Flow And Roles" 下新增**职责边界**：太子=受旨定性；中书=拟旨+拆解；门下=封驳；
  尚书=评估/差遣；语义 receipt 不得冒充官署回奏（否则 runtime_degraded/PARTIAL）。

### 4.2 `scripts/court_cli_registry.py`（COURT_OPEN_GUIDANCE_MARKDOWN）
- `court open` 帮助第 3 条：`Taizi intake first … then convene 三省会审 …
  Semantic DISPATCHABLE is a P00 gate, never a three-department office dispatch or reply.`

### 4.3 `scripts/court_runtime.py`（模块 docstring）
- 注明 semantic checkpoint/verify 为 P00 语义门禁，不证明三省官署派遣/回奏。

### 4.4 开朝真实链路（流程理解，非改动）
`court create`（charter+conversation_gate+capsule）→ `semantic checkpoint`（VERIFIED）
→ `semantic verify`（DISPATCHABLE）→ `court open --fast`（READY_FOR_HOST_DISPATCH）
→ `agent-admit`（六部 worker bindings + preload_hashes + budget lease +
context_budget_pool + dispatch_context_packet）→ host-native spawn。

---

## 5. 门禁/回归清单（本区间全绿或环境受限）

| 门禁 | 状态 |
| --- | --- |
| `check_shiguan_recall_precision.py`（27 探针） | PASSED |
| `check_governance_framework.py`（48） | PASSED |
| `check_court_mcp_server.py`（62） | ok:true |
| `check_unified_cli.py --all` | PASS（145 条目/source_only=6） |
| `check_skill_identity.py`（11 surfaces） | PASSED |
| `release_payload_manifest.py --self-test --check` | ok（beta1.0.8 收据；beta1.0.9 开发分支内容漂移预期） |
| `check_active_copy_hashes.py` | PASS（beta1.0.9 canonical：444 files drift=0 extra=0） |
| `check_codex_agent_roles.py` | 14/14；config_errors=2（环境受限） |
| quick_validate / release_legal / release_metadata / release_manifest / portability / package_privacy(64) / concurrency / http / taxonomy / full_record / git_federation / session_numbering / iku_repair / closeout / model_router / codex_office_worker / agent_config / projection_closure | 全绿 |

---

## 6. 环境要点（后续会话必读）

- Python 一律 `-B`，stdout 用 `PYTHONIOENCODING=utf-8`；子进程避免 cp1252（用 bytes+utf-8）。
- 真实 Codex 检查用 `$env:CODEX_HOME='C:\Users\Administrator\.codex'`；
  Hermes 沙箱 CODEX_HOME 指向 runs（勿当真实）。
- GitHub HTTPS 推送走代理：`git -c http.proxy=http://192.168.3.110:7890 push github ...`；
  GitHub Packages npm 读取需临时 `~/.npmrc`（`//npm.pkg.github.com/:_authToken`），用后删除。
- Windows CRLF：`release_payload_manifest` 用 LF 归一化哈希；对发布关键文件（PROVENANCE/
  package.json 等）工作副本需与 HEAD blob 一致（LF），否则 build_npm/authority 校验漂移。
