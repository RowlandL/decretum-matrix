# 新开史馆类 · 判定规则设计 v0.1

## 1. 原始需求表述

> 当前八节点从大到小没有相同的类似的即可判断为新分类（用户口述，自述"可能不太完全"）

## 2. 现状核实（实查结论）

| 事实 | 出处 |
| --- | --- |
| `classification_status` 是二值 `classified \| review` | `docs/plans/beta1.0.8/contracts/contract-b-lineage-taxonomy.md` §2 |
| 全新主题 → `review / unknown`，**不是**自动新开类 | `references/fixtures/shiguan-lineage-taxonomy-golden.json` 用例 `novel_unknown_topic` |
| 词表是硬编码常量，非动态增长 | `scripts/shiguan_entry_utils.py:180` `CONTENT_TAXONOMY` |
| 阈值 `CONTENT_TAXONOMY_MIN_SCORE = 2` | `scripts/shiguan_entry_utils.py:431` |
| 现存路径：旧记录带 `classification_reason` 则保留为 `stored_lineage` | `scripts/shiguan_entry_utils.py:1693` |

**结论：当前实现没有"自动新开类"的路径。** 新开类 = 人工/门下增补 `CONTENT_TAXONOMY` + bump `TAXONOMY_VERSION`。

本轮实查的 1129 条索引中：`taxonomy_version = historical_unversioned` 占 1066 条，当前版本仅 36 条，`v1` 27 条。

## 3. 业界同类规则（网上取证）

| 方向 | 代表 | 做法 |
| --- | --- | --- |
| Novel Intent Discovery（工业界） | Allegro, [arXiv 2305.05474](https://ar5iv.labs.arxiv.org/html/2305.05474) | **不是规则判定**：表示学习 + 约束聚类（CDAC）+ K 值选择 + 人工后处理。原文目标为 "automatically cluster utterances into ℐ classes, **which are not known a priori**"，且允许未标注样本同时属于已知意图 `ℐk` 与未知意图 `ℐu` |
| Open-Set Recognition + Novel Class Discovery | [MDPI 统一框架](https://www.mdpi.com/2076-3417/15/21/11468/pdf-vor) | 模型对未知给**拒绝选项（rejection option）**，人再裁定 |
| Ontology Expansion | [EMNLP 2024 综述](https://aclanthology.org/2024.emnlp-main.1006.pdf) | 本体扩展 = 把新术语挂到既有节点下 |
| 层级意图工程实践 | [HumanFirst Hierarchical Intents](https://docs.humanfirst.ai/docs/workspace/intents/hierarchical-intents/) | 父子层级的数据归属管理 |

**取证结论：不存在可直接照搬的"逐层无相似即新类"规则。** 用户思路需与"拒绝选项 + 聚类/相似度发现"两类既有机制组合才完整——其中**拒绝选项在本系统已实现**（`review`/待审）。

## 4. 修正后的规则：判据 A + B + C

### 判据 A —— 逐层相似度

对每一层 `L ∈ {志, 门, 纲, 目, 条}`：

```
sim_L(record) = max over existing nodes n∈L of cosine(embed(record_text), embed(n))
该层「有相似节点」 ⟺ sim_L ≥ θ_L
```

### 判据 B —— 由「最深匹配层 L\*」决定落点

| 情形 | 判定 | 动作 |
| --- | --- | --- |
| 不存在任何层满足 `sim_L ≥ θ_L` | **新一级类** | 新增 `志` |
| 存在 `L*`，但 `L*` 以下各层均无相似 | **既有类下的新子类** | 在 `L*` 的匹配节点下新增子节点 |
| `L*` 存在且更深层也有相似 | **归入既有最细节点** | 不新增 |

> 用户原话覆盖的是第 1 行。**第 2 行才是实际最高频的情形**——多数新主题是既有「志/门」下长出的新叶，而非全新分支。只按第 1 行判，会把大量"新子类"误报为"新一级类"。

### 判据 C —— 阈值按层递减

```
θ_志 < θ_门 < θ_纲 < θ_目 < θ_条
```

越靠上层节点越少、语义越粗，阈值应越宽松；越靠下层越应严格。

## 5. 与现有实现的衔接

1. 先用现有分类器取 `candidates[] / score / margin`（重推脚本：`scripts/reclassify.py`）。
2. 对 `classification_status = review` 的记录再计算 embedding 相似度，套判据 B。
3. 新类落定必须走**门下封驳** + bump `TAXONOMY_VERSION` + 增补 `CONTENT_TAXONOMY`，不得自动写入。
4. 相似度材料现成：索引已含 `embedding_text` / `capability_vector_sparse` / `vector_text`。
5. ⚠️ **当前"相似"是词面 needles 匹配**（`_taxonomy_term_evidence`），不是语义相似。这是"打分不太可用"的根因之一。

## 6. 可训练性映射（→ Laya 三原语）

| 决策 | Laya 原语 |
| --- | --- |
| 是否应开新类 | `noul`（二值） |
| 挂到哪个 `L*` 节点 | `choice` |
| 各层相似度/置信度 | `score`（校准概率） |

## 7. 动态增长架构（用户澄清 2026-09-29）

**原设计缺陷**：`CONTENT_TAXONOMY` 是 Python 常量（`scripts/shiguan_entry_utils.py:180`），把类写死了，与「类动态增长」的意图冲突。

**本机实测证据**（本轮审计）：

- 重推结果**无法产出 `项目` 志**（存量 7 条存在，重推 0 条）——词表里没有这个类。
- `待审` 志 24 条被重推清零——分类器不认识既有顶层类。
- R4 真分歧 18 条中 **7 条「存量与重推都错」**，逐条指向缺失的类：奏报/结诏格式规范、官籍语义治理、项目文档、工程实现、加载完整性/账册、基础设施/密钥存储。

**结论：类不能写死。新增类应由大模型生成，体系动态增长。**

### 修正后的链路

```text
记录
  → 判据 A：逐层相似度 sim_L
  → 判据 B：最深匹配层 L*
  → 若各层均无相似（或无可用 L*）：
       Laya noul 触发「需新类」
  → 大模型生成类名（志/门/纲/目/条 五段，或仅一级志）
  → 门下封驳
  → 追加进动态词表 + bump taxonomy_version
  → 后续记录即可归入该新类
```

### 三方分工（关键：Laya 不生成文本）

| 角色 | 职责 | 理由 |
| --- | --- | --- |
| **Laya** | 判定**是否需新类**（`noul`）+ **挂载点 L\***（`choice`）+ 各层置信度（`score`） | 非自回归，**不生成文本**；33ms 本地判定 |
| **大模型** | **生成类名**（含五段谱系与语义说明） | 生成任务，Laya 架构上做不了 |
| **门下** | 封驳 + 落表 + bump `taxonomy_version` | 治理闸门，类目变更需授权 |

### 八层全部动态（用户确认 2026-09-29）

**没有任何一层是固定的——「志」也允许动态增长。**

- 判据 B 第一行「各层均无相似 → **新增志**」是**活跃路径**，不是理论分支。
- 现有 5 个志（朝制/官制/典藏/工艺/器用）**不是封闭集合**；`项目` 等既有志可被恢复，全新志可由大模型生成并经门下封驳后加入。
- 因此「新增节点」的粒度由判据 B 决定：**能挂既有志就挂（新增门/纲/目/条），挂不上才开新志**——开新志的成本更高（顶层重划影响检索与树形），应作为最后手段。
- 推论：`should_new_class` 这个 `noul` **不应只问「是否新开志」**，而应问「**是否需要在任意层新增节点**」，并把「挂载层」作为 `choice` 一并输出。

### 新增优先级按层递减（用户补充 2026-09-29）

顶层大类的增长在实践中**很难覆盖**（毕竟是顶层大类），因此**新增「志」的优先级最低**：

| 层级 | 新增频率 | 优先级 | 说明 |
| --- | --- | --- | --- |
| 条 / 目 | **高** | **高** | 多数新内容只是既有类下长新叶 |
| 纲 / 门 | 中 | 中 | 需要跨既有目聚类 |
| **志** | **极低** | **最低** | 顶层大类重划，影响检索与树形，属例外 |

实证吻合：本轮 7 条「装不下」的记录，提案出的 6 个节点里 **5 个是「条/目」级、1 个是「门」级、0 个是「志」级**。

工程含义：

1. 语料中「需新增志」的正例应保持**极少数**，否则模型会过度预测顶层新增。
2. `should_new_class` 的标签需**按层加权**，或拆成「是否新增 + 挂载层」两个头（后者已是 `choice`）。
3. 运行时若模型判「需新增志」，应走**更高层裁定**，不能与「新增条/目」同权处理。


### 词表落盘形态（待实施）

从代码常量迁到版本化数据文件：

```text
references/shiguan-taxonomy.json
  taxonomy_version: "YYYY-MM-DD.<release>"
  nodes: [{ zhi, men, gang, mu, tiao, needles[], evidence[], court_code[], added_at }]
```

要求：可追加、可追溯（每个节点的来源诏令编号）、不写死在代码里、`shiguan_entry_utils` 改为读取该文件并保留常量作为回退。

### 与训练语料的衔接

- `should_new_class` 的 `noul` 正例 = R2 词表缺类 20 条 + R4 体系缺类 7 条。
- R4 那 7 条是本架构**唯一真实的检验对象**——它们正是「既有类都装不下」的实例，可用来验证「逐层相似度 + 最深匹配祖先」判据是否真的能把它们识别出来。

