# 诏令矩阵下一版本（beta1.0.8）总纲与文档索引

 > 日期：2026-08-28 · 基线：release/beta1.0.7 / VERSION=beta1.0.7 / HEAD=2571178
 > beta1.0.7 已完成源码收尾；本索引进入 beta1.0.8 开发准备阶段。
 > 这是 beta1.0.8 的规划与预研总纲，不代表版本已提升。

## 1. 文档结构（三书 + 协议草案）

| 文档 | 路径 | 内容 |
| --- | --- | --- |
| 开发文档 | docs/plans/2026-08-28-decretum-matrix-beta1.0.8-development-spec.md | 版本决策、现状锚点、FR+AC、架构、接口契约、安全约束、DoD |
| 任务书 | docs/plans/2026-08-28-decretum-matrix-beta1.0.8-task-book.md | 里程碑 M0–M5、WBS 详细任务（含验收命令）、依赖、估算 |
| 计划书 | docs/plans/2026-08-28-decretum-matrix-beta1.0.8-execution-plan.md | Phase 0–5 排期、依赖图、风险、门禁清单、每阶段交接契约 |
| Handoff 协议草案 | docs/plans/2026-08-28-decretum-matrix-beta1.0.8-codex-handoff-protocol-draft.md | 交接状态机、制品 schema、生命周期、校验、失败处理、环境适配点 |

配套文档：decretum-matrix-code-review-report.md（beta1.0.7 全量审查报告）、decretum-matrix-mcp-roadmap.md（MCP 联网调研路线）。

## 2. 版本范围速览

- 范围（当前访谈暂定）：基线清偿 E（工作树 / read_only_contract 门禁 / skill-identity sha / entry.id 白名单）+ 开发点 A（IKU 治理）+ B（编号/谱系/分类防过拟合）+ C（Codex 指定模型适配）+ D-MCP（以现有 court_mcp_server 通用 MCP 入口为起点，适配并新增诏令矩阵自身工具；具体工具清单、读写边界和传输层由后续逐题访谈确认）。
- 候选扩展（未冻结）：D-P1a（Streamable HTTP /mcp + 只读 Resources）；是否纳入、拆分或改写，待访谈确认。
- 当前未纳入候选：MRTR 审批流、OAuth/DCR、Server Cards/Registry、MCP 写通道、第二个 MCP 入口、版本号提升（发布批准时才动）、任何外部发布/推送；其中 MCP 相关项仅为当前假设，不构成最终否决。
- 访谈记录 Q1（暂定）：用户确认保留现有通用 MCP 入口，并在该入口上做适配与新增功能；后续问题允许覆盖本记录，最终范围以访谈收敛后的评审记录为准。

## 3. 原预备开发文档要点（已并入开发文档）

1. 编号不是模型可编造的文本：诏令编号必须继续由统一 shiguan archive-checkpoint 的 receipt 提供，MCP 不生成第二套编号。
2. 内容谱系不等于编号或工作阶段：史馆总纪 -> 志 -> 门 -> 纲 -> 目 -> 条 -> 诏 为主干；phase/status/memory_decision 等是 facet，不得成为谱系父节点。
3. 适配现有分类不能退化成过拟合：分类结果须版本化、可复验，最小验证集防过拟合。
4. IKU 先按疑似占位/非法片段处理：由候选检测、来源 receipt 和人工/门下复核共同确认，不批量改写。
5. MCP 分层（当前假设）：通用协议入口沿用现有 court_mcp_server，并优先在该入口内接入诏令矩阵自身能力；是否另增入口、传输或写能力不在本条提前冻结，交由后续访谈确认。
5. Codex 模型适配：先探测再路由；生产 V2/串行子官署保持继承语义；指定模型走 fresh-session worker + 精确 host proof，无证明即回退并标 runtime_degraded。

## 4. 使用方式（Codex 承接）

1. 读本索引 → 读开发文档（规格）→ 读任务书（本阶段任务）→ 读计划书（阶段与交接契约）→ 读协议草案（交接细则）。
2. 动手前加载权威 SKILL：C:/Users/32893/.agents/skills/decretum-matrix/SKILL.md。
3. 每阶段结束按 Handoff 协议草案执行交接；状态登记于 docs/plans/beta1.0.8/handoffs/README.md。
 4. 所有新能力保持 [PLANNED_UNVERIFIED]，四类证据闭环后提升。
 5. 承接本套文档时，优先读取并按序调用 `stop-that-shit`、`superpowers`、`ponytail`、`decretum-matrix` 相关 skill，再结合 `context-restore` / `context-save` 恢复或保存当前上下文；先用本机能力索引筛选最贴合当前任务的技能，再开始动手。

## 5. 版本提升纪律

- workspace.yaml version.current 仅在发布批准时提升（beta1.0.7 → beta1.0.8）；当前保持 beta1.0.7，本文件不构成版本变更授权。
