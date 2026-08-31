# MCP 召回算法审查报告（准确率 / 无关信息 / 工程化 评分 + 优化意见）

> 审查对象：MCP 召回链路——`shiguan.query` / `shiguan.entries_query` /
  `domain_gbrain_recall` / GBrain `build_recall_context`（核心为
  `shiguan_entry_utils.score_entry + select_matches` 与
  `query_shiguan_index.select_query_matches`）。
> 日期：2026-08-31 · 数据：真实史馆索引（8 条，`C:\Users\Administrator\.agents\court-shiguan\...\shiguan-index.jsonl`）
> 结论：召回为「词面子串加权」基线，**准确率与噪声控制不达发布级**，工程化有优化空间；评分与优化意见见下。

---

## 1. 算法机制（现状）

- `score_entry(entry, terms)`：多字段加权子串匹配（大小写不敏感，`term.lower() in field.lower()`）：
  - w6：capability_vector_terms / capability_source_paths / capability_lineage
  - w5：keywords / key_actions / vector_text / embedding_text / keywords_zh / keywords_en
  - w4：topic / phase / status / court_code / ancient_lineage / lineage_display / lineage_key /
    court_code_legend / lineage_parts / facet_dimensions / court_code_parts / keyword_summary_*
  - w2：summary / memory_content / memory_reason / display_*_zh
  - w1：evidence / next / **source**（含文件路径）
- `select_matches(entries, terms)`：score>0 全保留，按 (score, time) 降序；**无阈值 / 无 margin / 无去重 / 无否定处理**；空 terms 返回全量按 time 倒序。
- `select_query_matches(mode="gbrain|fallback")`：gbrain 分支实为 `shiguan_entry_utils.select_matches` 的 re-export（`shiguan_gbrain.select_matches` 即同一函数）——**“GBrain 召回”与基线是同一词面评分器**，无向量/embedding 参与。
- 每次调用 `load_entries()` 全量加载 + enrich（本机 8 条实测 **213ms 加载**），无索引/缓存；`select_matches` 8 条约 2.4ms/次，线性放大不可接受。
- MCP 包装：`public_shiguan_entries_query`（limit 1..50、元数据投影）、`shiguan.query`（limit≤20）、`domain_gbrain_recall`（附加 full_record/leaves 元数据）；审计/幂等/只读已由 R-02/R-03/R-08 覆盖。

## 2. 实证数据（真实索引，8 条）

| 查询 | 命中 | 现象 |
| --- | --- | --- |
| `archive` | 7/8 | source 路径 `references/plan-archives/...` 子串污染，7 条全因路径命中 |
| `史馆` | 8/8 | 谱系 `史馆总纪/...` 全含，无区分度，score 51–63 但排序无意义 |
| `IKU` | 3 条 | 3 条同分 29，无排序区分，疑似 evidence/summary 偶然提及 |
| `codex` | 4 条 | 独特词尚可（top=125），但混入路径/摘要权重 |
| 空词 | 8/8 | 全量按时间倒序（“最新 N”语义，需显式化） |

另：同题近似记录（`super并行矩阵基础加载与嵌套复盘`）在结果中相邻同分出现两次（无去重）；重复运行确定性好。

## 3. 三要素评分（满分 10）

### 3.1 准确率高（precision/相关性排序）：**5/10**
- 加分：确定性、纯函数、对独特词（codex）排序基本合理；MCP 层做元数据投影与 limit。
- 扣分：纯子串匹配无 IDF/词频归一；`source` 路径（w1）把 7/8 条“archive”误命中；常用词（史馆/索引/archive）几乎全量命中，top-k 无区分度；否定句不隔离（分类层有否定处理，召回层没有）；同分无 margin 裁决。

### 3.2 无关信息少（noise 控制）：**4/10**
- 扣分：score>0 即入选（w1 的 evidence/source 一次命中即上榜）；`plan-archives`/`memory-decisions` 等路径族造成大面积伪命中；无去重（同题记录重复上榜）；无阈值/无 top-k margin；空词全量。
- 加分：limit 截断、元数据投影不含 pending/private 正文（R-02/R-07 既有约束）。

### 3.3 工程化强：**6/10**
- 加分：纯函数可测、确定性排序、MCP 包装有 closed schema（R-08 后强制 limit）、审计 journal、幂等、只读。
- 扣分：每次调用全量 load+enrich（213ms@8条，万条级不可用），无倒排索引/缓存/增量；`gbrain` 分支是 re-export 假分支（命名误导）；无召回精度回归测试/基准；无 matched_terms/matched_fields 可解释字段；重复记录无归一化去重。

**综合：5/10（基线可用，发布级召回质量不足，建议优化后随 beta1.0.8 或紧随热修）**

## 4. 优化意见（分级，均给最小落地与验证）

### P0（显著提升精度/降噪，建议随 beta1.0.8）
- **P0-1 否定感知召回**：复用 `shiguan_entry_utils` 的否定标记（`CONTENT_NEGATION_MARKERS` / `_taxonomy_match_is_negated`），命中否定句的字段不贡献召回分。
  验证：新增 fixture（“不涉及 archive…”）→ 查询 archive 不得命中（check 断言）。
- **P0-2 词条化 + IDF 权重 + 阈值/margin**：term 做 token 归一（英文 token / 中文 TOKEN_RE 或二元组），score=TF·IDF（IDF 在 load 时统计一次）；仅保留 score≥阈值 且 与第 2 名有正 margin 或进入 top-k。
  验证：对 “史馆/archive/索引” 的命中数应显著下降且 top 排序与人工判断一致（check 断言命中数上限）。
- **P0-3 剔除低价值字段污染**：`source`/`evidence`/`next`（w1）改为精确 token/文件名匹配或不参与召回；`court_code_legend` 等说明性字段不参与。
  验证：查询 “archive” 命中数从 7→0/1（fixture）。

### P1（工程化与可解释，建议紧随其后）
- **P1-1 召回去重 + 可解释字段**：按 normalized topic+summary sha 去重；结果附 `matched_terms`/`matched_fields`。
- **P1-2 倒排索引 + 缓存 + 增量**：load 时构建 token→entry posting（一次 enrich，写路径才 enrich）；查询 O(命中数)；目标 P95 ≤100ms（devspec 既定）。
- **P1-3 召回精度回归集**：新增 `check_shiguan_recall_precision.py`（否定负例 / 常用词负例 / 路径污染负例 / 独特词正例 / 空词=最新N），纳入发布门禁。

### P2（清晰化与扩展）
- P2-1 修正 `select_query_matches` 的 gbrain/fallback 假分支（直接指向统一 scorer，注明 GBrain 为元数据增强层而非独立召回器）。
- P2-2 查询扩展：同义词（史馆↔shiguan、记忆↔memory、编号↔court_code）+ 结构化过滤（court_code/phase/status 精确）。
- P2-3 空词语义显式化为 “latest N”，MCP 层固定上限并记录。

## 5. 与既有工作的关系

- R-08 已强制 entries_query 的 limit 等 schema 约束；R-02 保证召回只读；R-11 保证 host-proof turn_context 会话限定（本报告不涉及）。
- 建议：P0-3（source 污染）为最小快赢；P0-1/P0-2 需 TDD 第三轮（红→绿 fixture）。是否随 beta1.0.8 实施由 REVIEWER 定（可列为 beta1.0.8 门禁前补强或紧随热修）。

---

## 6. P0 落地状态（2026-08-31，已随 beta1.0.8 评审闭环）

REVIEWER 批准三 P（P0-1/2/3）可行后按 TDD 一轮一提交落地：

| P0 项 | 提交 | 实现 | 真实索引实测（8 条） |
| --- | --- | --- | --- |
| P0-3 字段污染 | `b835768` | `_weighted_searchable_parts` 剔除 source/evidence/next/capability_source_paths/court_code_legend | archive 路径伪命中消除 |
| P0-1 否定 | `0314e6b` | `_recall_any_positive_occurrence` 复用 `_taxonomy_match_is_negated` 子句否定 | "不涉及 archive" 不再命中 |
| P0-2 词条化+TF-IDF+阈值 | `7746f1f` | ASCII token 精确/边界前缀、CJK run、BM25 IDF、RECALL_MIN_SCORE=1.0、RECALL_MIN_IDF=0.4 | archive 7→2、史馆 8→0、IKU 3→0、super 6→4 |

回归：`check_shiguan_recall_precision.py`（新增门禁，9 探针）PASSED；
`check_governance_framework` 48 checks 与 `score_entry` 钉死值 [13,11] 保持；
`check_court_mcp_server` 62 探针 ok:true。

**评分复测（落地后）**：
- 准确率：5/10 → **7.5/10**（结构化词条被硬过滤待 P2 结构化层补齐；独特词/否定/路径
  污染已达标）。
- 无关信息：4/10 → **7.5/10**（阈值/margin/否定/字段剔除落地；去重与可解释字段待 P1-1）。
- 工程化：6/10 → **7/10**（新增 hermetic 门禁；倒排/缓存/增量待 P1-2）。
- 综合：5/10 → **7.3/10**（发布级 ≥8/10 目标由 P1/P2 达成）。

分层索引算法详细方案（古制谱系 + 诏令编号段位基座）：
`docs/plans/beta1.0.8/review/shiguan-hierarchical-index-design.md`。
