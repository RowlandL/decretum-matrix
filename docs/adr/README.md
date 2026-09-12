# Decretum Matrix 任务治理：决策索引

## 已有决策出处

下表将现有文档接入 ADR 阅读入口，保留原文编号、日期与状态。列入索引不表示重新批准，也不把建议书的 DRAFT 升为 Accepted。

| 来源 | 记录内容与适用边界 |
| --- | --- |
| [docs/architecture/README.md](<../architecture/README.md>) | Wiki 架构主文档与历史来源分离，避免两份竞争正文 |
| [HANDOFF-decretum-matrix-2026-09-10.md](<../../HANDOFF-decretum-matrix-2026-09-10.md>) | 源码、安装、包和宿主验收分别报告；该结论适用其记录时间 |

## 新决策如何记录

只在实际形成重要选择时新建 `NNNN-主题.md`，沿用已存在的 ADR 编号并使用下一个未占用编号。写清状态（Proposed / Accepted / Superseded）、日期、问题、选择、依据、影响和替代关系；Accepted 必须注明真实的决定来源。小型文字修正不单独创建 ADR。

原决策不迁移或复制成第二份权威正文。若新决策替代旧决策，双方保留相互引用；历史执行结果仍以原证据为准。通用格式由控制根 `docs/templates/adr.md` 提供，迁移工作区时按项目治理入口重新定位。

返回 [项目上下文](../../CONTEXT.md) 或 [文档目录](../INDEX.md)。
