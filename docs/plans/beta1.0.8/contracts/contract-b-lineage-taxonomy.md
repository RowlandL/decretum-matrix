# 契约 B — 编号/谱系/分类防过拟合（FR-B，draft-0.1 · 2026-08-28.beta1.0.8）

> 权威：devspec §3.3 FR-B；实现：shiguan_entry_utils（TAXONOMY_VERSION）。

## 1. 三层数据分离

1. 编号层：court_code / 日期 / 日内序号 / 四字码（base36 / daily_sequence / stable_base36_code）。
2. 内容谱系层：lineage_parts / lineage_key / lineage_display（content_lineage_parts）。
3. Facet 层：phase / status / memory_decision / risk / value / priority / 行为谱系 / keywords / source。

约束：重建/整理路径（rebuild_shiguan_index.py、tidy_shiguan_records.py）保留既有合法 court_code 与谱系；MCP 使用统一 authority（archive-checkpoint / public API），不生成第二套编号。

## 2. 版本化分类合同（B2，阶段 3 完整落地；阶段 1 已固定契约）

- taxonomy_version：`TAXONOMY_VERSION = "2026-08-28.beta1.0.8"`（shiguan_entry_utils；管道输出携带，check 校验匹配）。
- classification_status 二值：`classified | review`（实现语义，R-07 对齐）。
  - `classified`：唯一候选命中且 positive margin 对第二候选 > 0（matched）。
  - `review`：其余全部（tie / conflict / unknown / low_confidence / negated_evidence），
    由 `classification_reason` 精确区分：`matched | tie | conflict | unknown | low_confidence | negated_evidence`。
- 规则：positive margin 对第二候选（>0）才 classified；分数不足 / 并列 / 仅负证据 / 完全未知 /
  否定词为正候选同时出现 → review/待审；tie 状态单独可判（margin==0 且多候选同分 top）；
  否定句不得贡献正向分（positive_evidence 与 negative_evidence 互斥）。
- 输出字段（content_lineage_parts）：taxonomy_version、classification_status、classification_reason、classification_confidence、classification_score、classification_margin、positive_evidence[]、negative_evidence[]、candidates[]。
- 稳定：规范化 JSON 字节级一致（double-run 回归）。

## 3. 最小验证集（B3，阶段 3）

- references/fixtures/classification-contract-validation.json：清晰 / tie / 否定 / 未知 / 冲突五类 + 重复运行。
- 现 golden：references/fixtures/shiguan-lineage-taxonomy-golden.json（9 例，taxonomy_version=2026-08-28.beta1.0.8）。

## 4. 验收指针

- check_shiguan_lineage_taxonomy.py：golden 版本 == TAXONOMY_VERSION；tie/unknown/negated/conflict →
  status=review + 对应 reason（阶段 3 扩展断言）；否定不贡献正分；unknown 无关键词→unknown。
- check_shiguan_lineage_rebuild_compatibility.py（阶段 3）：历史 court_code/lineage 保留。
