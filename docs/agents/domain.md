# Domain docs

## 读取顺序与权威

本机控制根为 `D:/project`；以该根的 `workspace.yaml` 和 `repo-control` 任务映射确认工作副本。此绑定只用于当前受管工作区，迁移时重新核实，不作为产品运行路径。

本项目上下文已补齐：先读 [CONTEXT.md](../../CONTEXT.md)，再按 [文档目录](../INDEX.md) 选择所需资料，并查看 [决策索引](../adr/README.md)。

先读取当前项目的 `AGENTS.md`（如已有 `CLAUDE.md`，也遵守适用指令），以及其中声明的根治理入口。根清单定义项目归属，项目资料定义本项目业务；旧计划、交接与记忆中的版本、路径和完成状态属于历史背景，使用前核对当前证据，不覆盖当前清单和用户要求。

本项目已存在的资料入口如下；仅阅读与当前任务有关的章节或文件：

- [README.md](../../README.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
- [SKILL.md](../../SKILL.md)
- [docs/plans](../../docs/plans)
- [HANDOFF-decretum-matrix-2026-09-10.md](../../HANDOFF-decretum-matrix-2026-09-10.md)

## 布局与领域文档

默认采用 single-context：项目根 `CONTEXT.md` 与 `docs/adr/`。若已有 `CONTEXT-MAP.md`，先按该映射读取本次涉及的上下文与局部 ADR，保留既有布局。模块数量或受管子仓库数量本身不要求 multi-context。

- `CONTEXT.md` 记录稳定的术语和业务边界；已有架构说明继续保留并被引用，避免两份同义正文。
- `docs/adr/` 记录真实形成的重要设计决策及理由；已有设计决策引用原文，不为形式重写历史。
- 本项目 CONTEXT 与决策索引已存在；新增领域或决策时按实际需要补充，不批量创建空文档。
- 输出使用已有词汇。发现 ADR 或当前指令冲突时明确指出来源，不静默覆盖。
- 日期化计划、交接、项目记忆用于定位历史和恢复点，不自动恢复其暂停任务。
- 领域文档和配置不证明产品已实现、已安装或已验收；相关结论仍须遵守项目证据规则。

开始本项目任务必须完整读取安装权威 `C:/Users/32893/.agents/skills/decretum-matrix/SKILL.md`；上面的仓库 SKILL 与交接入口不能替代安装 skill 的读取门禁。
