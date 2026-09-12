# AGENTS.md（根仓库同步强制约束）

本文件为根仓库口径的同步约束，所有子仓库必须保持一致；本仓库内任何 agent/任务均应遵守。

## 哈希校验脚本禁令（全局强制 / Global Hard Ban）

禁止重复开发或新增任何哈希校验类脚本（SHA-1/SHA-256/MD5/CRC/checksum 等摘要、比对或完整性校验），
无论以何种语言（bash/Python/PowerShell/Node/batch/Go 等）、何种形式（独立脚本文件、内联命令、一次性工具、临时函数/模块、被调用的辅助实现）存在。
唯一允许的场景：

1. 安装时的校验（安装/部署流程中验证安装包或产物完整性的必要校验）；
2. Debug（明确用于定位问题的调试性校验，用完即弃，不得沉淀为常规脚本）。

除上述两类外，一律不允许新建、复制、改写或重新实现哈希校验类脚本；
已有校验工具、脚本与命令必须直接复用，不得另起炉灶。
本条款由根仓库强制同步覆盖所有子仓库，违反视为工作区控制面失约。


## Agent skills

本项目标识为 `decretum-matrix`，受已登记控制根的工作区治理，Git 历史与索引属于本项目。开始工作先读取控制根的 `AGENTS.md`、`workspace.yaml` 和 `docs/agents/README.md`，再读取本项目配置及适用的局部指令。

根定位使用已验证的任务控制面路径；本机绑定见 [领域配置](docs/agents/domain.md)。在 worktree / `attached` 中不得仅靠父目录或目录名推断归属，应以清单和 `repo-control` 任务映射核对。本项目配置路径相对于当前项目 Git worktree 顶层。根治理不可读或映射不符时，先解决定位问题再进行受管写操作，不静默降为非受管项目。

根规则约束管理、授权和仓库边界，项目规则补充产品行为与专用流程；冲突时遵循上位指令和最新用户要求。普通模块继承本项目配置，只有明确的领域边界才补充局部上下文。

Decretum Matrix 任务仍须完整读取根治理指定的已安装 `decretum-matrix/SKILL.md` 并遵守其专用流程；确切本机路径见领域配置，不以仓库副本替代。通用工程配置不替代原计划、官署层级、运行回执或发布验收，不自动恢复任何暂停任务。

### Issue tracker

新需求默认使用本项目的本地 Markdown 工单；已有任务保留原编号与权威记录。见 [issue-tracker.md](docs/agents/issue-tracker.md)。

### Triage labels

使用五种默认 triage 角色；分类状态不等同于运行或验收状态。见 [triage-labels.md](docs/agents/triage-labels.md)。

### Domain docs

采用 single-context 布局，先读 [CONTEXT.md](CONTEXT.md)，再按 [文档目录](docs/INDEX.md) 与 [决策索引](docs/adr/README.md) 定位既有资料。见 [domain.md](docs/agents/domain.md)。
