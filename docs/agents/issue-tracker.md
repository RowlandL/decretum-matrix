# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`, never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` (the Notes / Decisions-so-far / Fog body).
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.

本 tracker 只管理 `decretum-matrix` 项目事项。根工作区治理事项路由到根 tracker；其他项目事项先核对 `workspace.yaml`，不跨项目混写。

## 工作区治理与既有任务

- 本配置的路径均相对于当前项目 Git worktree 顶层；模块继承本项目配置，不在每个目录重复建立 tracker。
- 新需求默认使用上述本地 Markdown 约定。已有工单、计划、任务书、交接和编号继续在原位置维护，引用原记录，不复制成第二份权威任务。
- 本地工单记录需求、分类、处理结论；受管任务的 worktree 归属、运行状态与事件继续由根仓库 `repo-control` / `.repo-control` 管理。工单不授予执行、安装或发布权限，不代替验收证据。
- 普通工单的 `Status:` 使用 triage 角色；`wayfinder` 子票的 `Status:` 按上面的 `claimed` / `resolved` 协议使用，不将两种状态当作同一个字段的同时取值。
- “publish to the issue tracker”在本配置中仅指写本地文件。切换 GitHub/GitLab tracker 或向外部系统写入，须遵守当前用户授权；现有 remote 本身不构成授权。
- 不读取或迁移与当前任务无关的私密材料。提交工单前检查敏感内容，并确认本地 `.scratch/` 的 Git 忽略策略；不得自动强制添加被忽略的文件。
