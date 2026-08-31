# 史馆分层索引算法设计（古制谱系 + 诏令编号基座）

> 文档状态：评审稿 · 日期：2026-08-31 · 分支：`release/beta1.0.8`
> 触发：用户指令——「三 P 可行，另外可以基于现行分类方法（古制谱系）与编号做一套
> 独立索引算法；现有史馆记录规则较完善，编号每一位有特定意义，应作为算法基础基座；
> 审查现状并联网调研先进方案与数学算法，给出详细方案。」
> 关联：`docs/plans/beta1.0.8/review/mcp-recall-review.md`（三要素评分与 P0/P1/P2 优化意见）
> `scripts/check_shiguan_recall_precision.py`（P0 回归门禁，本方案 P1/P2 验收基线）

---

## 1. 背景与目标

史馆召回链路（`shiguan.query` / `shiguan.entries_query` / `domain_gbrain_recall`）在
beta1.0.8 发布前评审中得分 **5/10**（准确率 5、无关信息 4、工程化 6）。P0 三件套
（P0-1 否定感知、P0-2 词条化+TF-IDF+阈值、P0-3 剔除低价值字段污染）已按 TDD 落地，
真实索引实测：`archive` 7→2、`史馆` 8→0、`IKU` 3→0、`super` 6→4。

本设计回答下一个层次的问题：**史馆拥有两套天然的结构化基座**——
古制谱系（受控词表的分层分类法）与诏令编号（可排序、可前缀、可段位过滤的复合键），
应当被显式建模为**分层索引**，而不是继续把全部召回压在一个纯文本评分器里。

设计目标（沿用三要素）：
- **准确率高**：结构化命中优先，文本召回只做补充；常用/结构性词条不再全量噪声。
- **无关信息少**：段位过滤 + 阈值/margin + 否定隔离 + 去重，可解释。
- **工程化强**：一次构建、增量更新、幂等可重放、只读查询、审计 journal、P95 ≤ 100ms。

---

## 2. 基座审查：古制谱系与诏令编号

### 2.1 古制谱系（lineage taxonomy）

每条史馆记录由分类器 `content_lineage_parts` 产出 7 层受控分类：

| 层 | 字段 | 示例 | 层码（LINEAGE_CODE_OVERRIDES） |
| --- | --- | --- | --- |
| root | `root` | 史馆总纪 | S |
| zhi | `zhi` | 朝制 / 官制 / 典藏 / 工艺 / 器用 | C / G / D / W / Q |
| men | `men` | 官署 / 权柄 / 官籍 / 史馆 | O / P / R / M |
| gang | `gang` | 三省六部 / 三权 / 铨选 / 实录 / 图谱 | S / P / R / L / GP |
| mu | `mu` | 政令流转 / 沙盒边界 / 差遣考课 / 生长树 | ZL / SH / CK / T |
| tiao | `tiao` | 上奏回奏 / 权限分级 / 能力调度 / 索引检索 | SZ / QX / ND / I |
| zhao | `zhao` | 记录级诏题（自由文本） | 段码或 U+base36 |

展示格式：`史馆总纪·朝制志·官署门·三省六部纲·政令流转目·上奏回奏条·…诏`；
键：`content_lineage_key` → `朝制/官署/三省六部/政令流转/上奏回奏`。
分类器同时输出 `classification_status/confidence/margin/negated_evidence`。

**结论**：谱系是**受控词表的分层分类法（taxonomy）**，天然支持前缀/祖先-后代/兄弟查询，
是 Dewey 式层级编码与 radix/trie 索引的直接适配对象。待审（`待审…`）记录为未分类
叶子，L0 需显式处理。

### 2.2 诏令编号 court_code

格式（`enrich_court_code` / `court_code_legend`）：

```
<层级码串>-<YYYYMMDD>-<日内36进制序号>-<四字码>
例：SCOSZLSZUMC-20260811-1-CFFF
```

| 段位 | 语义 | 性质 |
| --- | --- | --- |
| 层级码串 | 7 段谱系层码拼接（每段 1–2 字符，未知层 `U`+base36(2)） | 前缀=祖先，可前缀/范围查询 |
| 日期 | `YYYYMMDD`（取 time 或 source 内日期） | 可排序区间查询 |
| 日内序号 | `0-9A-Z` 36 进制，日内唯一 | 可转整数做数值区间 |
| 四字码[0] | 状态（离散执行结论：D/W/A/V/R/B/P/S/F/N） | 枚举过滤 |
| 四字码[1] | 风险（S/A/B/C/D/E/F 等级） | 枚举过滤 |
| 四字码[2] | 知识价值（S–F） | 枚举过滤 |
| 四字码[3] | 优先级（S–F） | 枚举过滤 |

独立标识 `kb_uid`(4)/`record_uid`(8)/`machine_uid` **不进入**诏令编号。
`court_code_parts` 已把上述段位拆为 `lineage/date/sequence/status/risk/
knowledge_value/priority` 结构化字段。

**结论**：编号是**可排序、可前缀、可段位过滤的复合键**，可直接作为主索引键与二级
段位桶的基座；每一位都有确定语义，是算法稳定性的根基。

### 2.3 基座审查结论

- 强项：层级受控、编号确定且可重放、语义每段可解释、分类器已有否定/置信度处理。
- 弱项：目前召回把结构化字段与自由文本混在同一 scorer（`_weighted_searchable_parts`），
  无倒排、无段位桶、无前缀树；P0 只是让文本评分不"伪命中"，并未利用结构信息。

---

## 3. 现状（P0 已落地）与剩余差距

已落地（提交 `b835768` / `0314e6b` / `7746f1f`，门禁 `check_shiguan_recall_precision.py`）：

| 项 | 实现 | 实测（真实 8 条） |
| --- | --- | --- |
| P0-3 字段污染 | `source/evidence/next/capability_source_paths/court_code_legend` 不参与召回 | archive 路径伪命中消除 |
| P0-1 否定 | 复用 `_taxonomy_match_is_negated` 子句否定 | "不涉及 archive" 不再命中 |
| P0-2 词条化+IDF | ASCII 精确/边界前缀 token、CJK run、BM25 IDF、`RECALL_MIN_SCORE=1.0`、`RECALL_MIN_IDF=0.4` | archive 7→2、史馆 8→0、IKU 3→0、super 6→4 |

剩余差距（即本设计的落地范围）：
- P1-1 去重 + `matched_terms/matched_fields` 可解释字段。
- P1-2 倒排索引 + 缓存 + 增量（本设计 L1；目标 P95 ≤ 100ms）。
- P1-3 召回精度回归集扩展为结构化 case（谱系前缀、段位过滤、日期区间）。
- P2-1 修正 gbrain/fallback 假分支命名（统一指向同一 scorer，GBrain 仅为元数据增强层）。
- P2-2 查询扩展：同义词 + 结构化过滤（谱系/段位/日期）——即本设计 L0。
- P2-3 空词/常用词显式化为 "latest N"（MCP 层固定上限并记录）。

---

## 4. 联网调研：先进方案与数学算法

### 4.1 倒排索引与布尔合取
倒排索引（inverted index）以 term→postings 支持 AND/OR 交集与并集；postings 有序
时用 merge 算法线性求交（IR-book，Stanford）。中文/日文无空格，常用 bigram 索引
（Whoosh n-gram 文档）。→ 用于 L1 文本层。

### 4.2 BM25 家族
BM25 概率排序模型：
`score(D,Q) = Σ idf(qi) · f(qi,D)·(k1+1) / (f(qi,D) + k1·(1-b + b·|D|/avgdl))`，
`idf = ln((N - df + 0.5)/(df + 0.5) + 1)`。Milvus 2.5+ 内置可配置 BM25 analyzer
（含 jieba tokenizer）；有 WAND / Block-Max WAND（BMW）用 term/block 上界做 top-k
动态剪枝（VectorChord-BM25、NodeDB）。→ 用于 L1 评分与 top-k 剪枝。

### 4.3 否定处理
TREC 2025 `bm25_negations`：检索后检查候选标题/前导窗口，若否定 span 落在标题窗口
（~128 字符）内则 score -= 2.0；BioGen 赛道用 NegEx 风格规则否定过滤器。
→ 佐证 P0-1 方向；可再加"否定扣分"而非仅"不贡献正分"。

### 4.4 层级编码索引
- **Dewey Decimal / J.Dewey**：编码前缀即祖先关系，`LCA(SLCA)` 可对前缀编码逐层求交
  （北大 LISA 算法）；XML 树形数据包含查询即前缀范围查询。
- **B-tree 前缀索引**（US20090112913 层级 orderkey）与 SQL Server `hierarchyid`：
  在有序键上做祖先/后代/区间。
- **radix tree / ART（Adaptive Radix Tree）**：按字节前缀压缩，O(查询长度)，
  支持前缀/范围查询（go-immutable-radix、gammazero/radixtree）。
→ 用于 L0 谱系前缀索引与编号复合键。

### 4.5 混合检索融合：RRF
Reciprocal Rank Fusion：`RRF(d) = Σ_i 1/(k + rank_i(d))`，k 通常 60；把稀疏/稠密/
结构化多路结果按排名融合（Chroma、微软 Azure AI Search、阿里云 PolarDB 均实现）。
无需归一化分数，抗分数尺度差异。→ 用于 L0+L1(+L2) 融合。

### 4.6 稀疏向量与汉明检索
- **MIH（multi-index hashing）**：把 64-bit 二进制码按 m 个分块建哈希表，汉明空间
  kNN 在 10M 条上比线性快 19–94×（mih-rs）。→ 若升级现有 `bucketed_sparse_vector`
  （当前为 `zlib.crc32 % 64` 的原始桶）为二进制签名，可用 MIH 做近似语义召回。
- 现有 `capability_vector_sparse` 已是 64 维稀疏桶（词袋加权），可作为向量层种子。

### 4.7 中文分词
MTEB 中文检索基线：自定义 jieba tokenizer 使 BM25 从约 0.56 → **0.641**；无依赖方案
是 CJK 字符 bigram/整 run 切分。→ 当前 TOKEN_RE 的 CJK run 是"无依赖简化版"；
如需更高精度再引入 jieba（注意依赖预算与安装面约束）。

---

## 5. 分层索引算法设计（详细方案）

### 5.1 总体架构（三层 + 融合）

```
                    ┌──────────────────────────────────────┐
   query ─────────▶ │  Query Planner（意图分派）            │
                    │  结构化词(谱系/段位/日期) → L0        │
                    │  自由词(非结构化)       → L1          │
                    │  常用词/空词           → latest-N     │
                    └──────────────┬───────────────────────┘
            ┌──────────────┬───────┴────────┬──────────────┐
            ▼              ▼                ▼              ▼
   L0a 谱系前缀树   L0b 编号复合键+段位桶   L1 文本倒排      L2 稀疏向量(可选)
   (radix/Dewey)   (B-tree/有序键)         (BM25+否定)     (bucketed→MIH)
            └──────────────┴───────┬────────┴──────────────┘
                                   ▼
                     RRF / 分层策略融合 → 阈值/margin → 去重 → 可解释投影
```

### 5.2 L0a：谱系前缀索引（radix/trie，Dewey 风格）

- **键**：逐层谱系码（root→tiao），每层码固定长度（1–2 字符，`LINEAGE_CODE_OVERRIDES`
  规范化），拼接为前缀串 `S/C/O/S/ZL/SZ/…`；`zhao` 为叶级自由码。
- **结构**：radix tree（ART 或 dict-of-prefix），节点存该前缀下的记录指针列表；
  或退化为有序前缀数组 + `bisect`（prefix range `[P, P+'\uffff')`）。
- **查询**：
  - 祖先/后代：`谱系 = 朝制/官署/三省六部` → 前缀 `C/O/S` 子树全部命中。
  - 兄弟：同一 `mu` 前缀下按 `tiao` 枚举。
  - "史馆" 语义 → root=`S`（史馆总纪）前缀子树 + 按 `date` 倒序取 latest-N
    （把 P0 的"史馆→0 命中"从文本层提升到结构层，得到正确结果）。
- **复杂度**：O(层数) 定位 + O(命中数)；构建 O(Σ 层码长)。
- **数学基础**：前缀编码的祖先关系（Dewey 性质：`u` 是 `v` 祖先 ⟺ `code(u)` 是
  `code(v)` 前缀）；包含查询 = 前缀范围查询。

### 5.3 L0b：编号复合键 + 段位桶

- **主键**：`(lineage_code, date, sequence)` 有序三元组（`date` 为 `YYYYMMDD` 整数、
  `sequence` 为 36 进制→整数），B-tree/有序数组支持：
  - 日期区间：`date ∈ [20260801, 20260831]`
  - 日内序号区间：`date=… AND sequence ∈ [1, 9]`
  - 前缀：`lineage_code LIKE 'SCOSZLSZU%'`
- **段位桶**：`status/risk/knowledge_value/priority` 各建枚举倒排桶
  （值域 ≤ 7，`status` ≤ 11），`bucket[value] = [record_ids]`，组合过滤 = 集合交。
  例：`status=DONE AND priority=A` → `bucket['D'] ∩ bucket['A']`。
- **查询示例**：
  - `risk=B`：待审/高风险记录清单（运营视图）。
  - `knowledge_value ∈ {S,A}`：高价值召回默认集（对齐 `VALUE_LEVEL_ZH` 语义）。
  - `priority=F`：不排期记录排除（P0-2 的"无长期价值不建议召回"落地为硬过滤）。
- **复杂度**：桶过滤 O(桶大小)；区间查询 O(log N + k)。
- **数学基础**：36 进制唯一性 → 无碰撞序号；等级序数映射（S>A>B>…）→ 可做
  加权/软过滤（如 priority 权重参与融合而不是硬切）。

### 5.4 L1：文本倒排索引（BM25 + 否定 + 阈值）

- **词条化**（复用 P0 规则）：ASCII token（精确/分隔符边界前缀）、CJK run；
  可选升级：CJK bigram（2-gram 倒排）或 jieba（依赖允许时）。
- **postings**：`token → [(record_uid, field_key, weight, tf, negated_hint)]`，
  load 时一次构建；字段权重沿用 `_weighted_searchable_parts`（不含 P0-3 剔除字段）。
- **评分**：BM25/TF-IDF（P0 公式 + `k1/b/avgdl` 可选）；否定沿用子句检测，
  可加 TREC 2025 式惩罚（否定 span 扣分而非仅零贡献）。
- **阈值/门控**：`RECALL_MIN_SCORE` + `RECALL_MIN_IDF`（已落地），结构层命中的
  记录可放宽文本阈值（分层策略）。
- **增量**：写路径（archive/rebuild/import）才更新 postings；更新写审计 journal，
  幂等（输入=jsonl 行，可重放）。

### 5.5 融合与排序（L0 + L1 + L2）

- **方案 A（推荐，先落地）分层策略**：
  1. 若 query 含结构化词（谱系名/段位/日期/编号前缀）→ L0 命中为**强候选**，
     按 `(L0 深度, date desc)` 排序；文本分仅在同层内微调。
  2. 否则 → L1 TF-IDF 排序（P0 现状）。
  3. 空词/全常用词 → latest-N（time desc），MCP 层固定上限。
- **方案 B（可选增强）RRF 融合**：L0 与 L1 各出 top-K，`score = Σ 1/(k + rank)`，
  k=60；抗分数尺度差异，无需归一化。
- **去重（P1-1）**：按 `normalized topic + summary sha` 合并同题记录
  （真实索引存在相邻同分重复），保留最新 time 一条并附 `duplicate_count`。
- **可解释（P1-1）**：结果附 `matched_terms` / `matched_fields` / `matched_structural`
  （命中的谱系前缀/段位桶）。

### 5.6 性能目标与缓存

- 目标：**P95 ≤ 100ms**（含 load + enrich + 查询；devspec 既定），万条级可用。
- 加载：一次 enrich + 一次构建倒排/前缀树；结果对象缓存 + 索引文件 mtime/哈希失效；
  写路径 `invalidate`。
- 剪枝：L1 命中数 > 阈值时用 WAND/BMW 思路（term 上界跳过）或直接 top-k 堆。
- 现状基线：8 条 load 17ms、查询 8–24ms（P0 后）；万条级预计 load ~2s → 必须缓存。

### 5.7 一致性与纪律（对齐既有契约）

- **只读**：query 路径零副作用；`ensure_* --check` 零副作用（R-02 契约）。
- **幂等/可重放**：索引构建只读 jsonl，输出可重放；receipt 带 `sha256`。
- **审计**：MCP 调用写 journal（R-03）；新增结构过滤参数同样记录。
- **门禁**：`check_shiguan_recall_precision.py` 扩展结构化 case（见 §6）。
- **环境受限项**：不触碰受保护史馆锚点（extra=4）与 `~/.codex/config.toml`；
  真实 Codex 检查显式 `CODEX_HOME`。

---

## 6. 实施路线与验收（P1/P2）

| 里程碑 | 内容 | 验收 |
| --- | --- | --- |
| P1-1 | 去重 + `matched_terms/matched_fields` | check 断言去重后无相邻同题；投影含可解释字段 |
| P1-2 | L1 倒排 + 缓存 + 增量（写路径 enrich） | P95 ≤ 100ms（基准集）；幂等重放一致 |
| P1-3 | 召回精度回归集扩展：谱系前缀/段位/日期区间/否定/路径污染 | `check_shiguan_recall_precision.py` 全绿 |
| P2-1 | gbrain/fallback 命名修正（统一 scorer + 元数据增强层） | 注释/导出明确，无假分支 |
| P2-2 | L0a/L0b 结构化过滤 + 同义词（史馆↔shiguan、记忆↔memory、编号↔court_code） | 结构化查询命中正确、常用词走 latest-N |
| P2-3 | 空词/常用词 = latest N 显式化 | MCP 层固定上限并记录 |

**三要素复测目标**：准确率 ≥ 8/10、无关信息 ≥ 8/10、工程化 ≥ 8/10（对真实索引 +
基准集评分，方法同 `mcp-recall-review.md` §3）。

---

## 7. 风险与开放问题

1. **中文分词**：CJK run 简洁但召回/精度有限；bigram 或 jieba 提升显著（MTEB
   0.641），但 jieba 引入依赖与安装面，需预算审批（source-state-budget / 依赖纪律）。
2. **待审（未分类）记录**：`待审/待审/…` 谱系无区分度，L0 前缀树会集中在一棵
   "待审"子树；需按 `classification_status` 分流（classified → L0；review →
   仅 L1 + 段位桶）。
3. **跨 store / gbrain 命名**：`shiguan_gbrain` 目前是 re-export；P2-1 需避免
   破坏 `check_governance_framework` 的等价断言（`gbrain==fallback` 保持不变，
   仅修正文档/命名）。
4. **缓存一致性**：daemon/autosync 写路径必须 invalidate 缓存，否则召回陈旧；
   用 mtime+sha 双重失效，与 `check_shiguan_concurrency` 纪律对齐。
5. **阈值标定**：`RECALL_MIN_SCORE/RECALL_MIN_IDF` 是经验值，随语料增长应做
   基准集标定（P1-3），避免新语料下误杀或放宽。

---

## 8. 结论

古制谱系与诏令编号是史馆天然的**层级索引基座**：谱系提供受控层级（Dewey/radix
适配），编号提供可排序复合键与段位语义（B-tree/桶过滤适配）。P0 已把文本召回
从"伪命中"纠正为"可判别"；下一步（P1/P2）按本设计落地 L0a/L0b/L1 三层与
RRF/分层融合，可在不破坏既有门禁与契约的前提下把三要素评分从 5/10 提升到
发布级（≥8/10），并保持只读、幂等、可审计的纪律。
