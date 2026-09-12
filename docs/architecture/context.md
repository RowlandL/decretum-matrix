# Decretum Matrix 任务治理上下文

文档角色：稳定领域说明与阅读入口。维护日期：2026-09-12。此日期表示文档整理时间，不代表运行状态复测时间。

## 职责与边界

本项目提供任务理解、职责分配、执行、复核和记录的治理 skill，以及相关 CLI/MCP 接口。现有 Wiki 架构页承担项目框架说明，references 与安装 skill 承担各自适用的运行约束。

项目标识：`decretum-matrix`。由根清单登记、由 repo-control 管理工作副本；本项目保有独立 Git 历史。根治理入口与定位方法见 [AGENTS.md](../../AGENTS.md)。

## 领域术语

| 术语 | 本项目含义 |
| --- | --- |
| 三省六部 | 默认职责与差遣层级，不等同于一组事后命名的步骤。 |
| 任务章程 | 绑定用户目标、范围、权限、验收与停止条件的任务约束。 |
| 候选产物 | 待安装或发布验收的结果，不等同于已发布版本。 |
| 运行回执 | 记录当前任务的真实操作与结果；与源码测试、文档声明分别判断。 |
| 史馆 | 治理记录与知识引用入口；历史记录不自行授予当前执行权。 |

## 阅读入口与事实来源

先读适用指令，再读与本次工作有关的资料：

- [README.md](<../../README.md>)
- [docs/wiki/Architecture.md](<../../docs/wiki/Architecture.md>)
- [docs/architecture/README.md](<../../docs/architecture/README.md>)
- [SKILL.md](<../../SKILL.md>)
- [HANDOFF-decretum-matrix-2026-09-10.md](<../../HANDOFF-decretum-matrix-2026-09-10.md>)

完整分类目录见 [docs/INDEX.md](../../docs/INDEX.md)，工程 skill 的读取约定见 [domain.md](../../docs/agents/domain.md)，现有设计决策出处见 [ADR 索引](../../docs/adr/README.md)。

## 文档分工

- 本页说明稳定概念，不复制全部架构、计划或操作记录。
- 计划和任务书定义各自阶段目标，工单与交接保留原编号和权威记录。
- 设计依据保留原文，新的重要决策记录背景、选择、影响及证据。
- 日期化交接与验收记录只证明其所述范围和时间；知识摘要用于检索和解释。

## 承接与核验

当前工作以 VERSION、受管任务映射与该分支计划为准。beta1.1.3 的维护记录见 [本版计划](../plans/2026-09-12-beta1.1.3-rule-reuse.md)；HANDOFF-decretum-matrix-2026-09-10.md、docs/handoffs、handoff_packages 和旧 task-book 保留为各自版本的来源。不要因为索引新增而重建原任务编号或恢复暂停计划。

代码职责：court_public_api 提供公共操作边界；court_dispatch_policy 验证派遣结构与预载；court_runtime 组织状态与事件提交；court_operation_journal 承担中断恢复；shiguan_entry_utils 负责召回排序，shiguan_gbrain 组织知识输出。新增逻辑放入实际承担该职责的位置，安装与发布验证继续留在源码／安装阶段。

本页只概述领域，不宣称运行能力通过验收。受管任务必须完整读取当前安装的 decretum-matrix SKILL，按 AGENTS 中的精确路径和当前流程执行；仓库副本或本页不能替代。

## 维护方式

业务边界或术语实际改变时更新本页，并引用决策出处；增加、移动或替代文档时更新 docs/INDEX.md。历史证据不为整理目录而重写，资料缺少事实时明确标记未核实。新需求的记录方式见 [issue-tracker.md](../../docs/agents/issue-tracker.md)。
