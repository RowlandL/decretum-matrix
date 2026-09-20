# Decretum Matrix（诏令矩阵）

<p align="center">
  <img src="assets/brand/decretum-matrix-icon.svg" alt="Decretum Matrix icon" width="160">
</p>

Decretum Matrix（诏令矩阵）是一个通用任务治理 skill：它把事实、解释、裁定、行动、
验证、记忆和呈现组织成可追溯关系，让 Agent 在空白环境中也能明确「谁判断、谁执行、
谁复核、留下什么证据」。它在 Codex、Agent Skills、Claude Code 与 Hermes 的本地
skill 环境中运行。内置的分层治理实现是完整默认治理；GBrain 记忆中枢为不同治理实现
提供共享但无执行权的长期认知。

| 项目 | 值 |
| --- | --- |
| 规范调用 | `$decretum-matrix` |
| 当前 GitHub 发布线 | `beta1.1.4` |
| npm beta 渠道 | `1.1.2-beta.0`（独立发布通道，以远端回读为准） |
| 接口面 | 统一 CLI `decretum-matrix` + 只读 stdio MCP（13 个工具） |
| 许可 | AGPL-3.0-only（商业许可需另行书面签署） |

---

## 1. 安装

### 1.1 最快路径

```sh
npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com
decretum-matrix --version
```

GitHub Packages 要求认证时只授予最小 `read:packages`；使用进程级
`NODE_AUTH_TOKEN` 与临时 npmrc，不要把 token 写入仓库、命令历史或长期配置。

`npm install` 返回 0 只证明命令完成。安装成功、远端包状态与活动运行身份分别以
发布后回读和安装回执为准。

### 1.2 安装到哪些目录

canonical runtime 根始终是：

| 平台 | canonical skill root |
| --- | --- |
| Windows | `%USERPROFILE%\.agents\skills\decretum-matrix` |
| macOS | `~/.agents/skills/decretum-matrix` |
| Linux | `~/.agents/skills/decretum-matrix` |

受治理的同步目标共五根：

```text
<home>/.agents/skills/decretum-matrix
<home>/.codex/skills/decretum-matrix
<home>/.claude/skills/decretum-matrix
<home>/.hermes/skills/decretum-matrix
<hermes-user-data>/skills/decretum-matrix
```

Hermes user-data 根：Windows 为 `%LOCALAPPDATA%\hermes`，macOS/Linux 为
`~/.hermes`。旧 `skills/court-capability-router` 只能不存在，或作为指向同一物理
authority 的受控兼容 locator；不能保留第二份可写副本。

### 1.3 升级与回滚

升级已存在的全局 npm 包时，安装事务必须显式选择替换路径：默认 fail-closed 拒绝覆盖，
只有调用方明确选择替换时才移动旧包并安装候选包。旧包移动到以 npm prefix 和备份根为
基准的相对路径备份清单，根 shim 只做快照记录；路径类字段优先使用相对路径，避免主机
目录变化导致安装识别或回滚失效，绝对路径只作为当次运行的宿主证据。

已发行版本的安装、回滚与安装前检查由对应的外置安装事务和独立回执确认。安装后的
skill 根不保留 release manifest、release gate、hash checker 或其他发布校验 helper。
`beta1.1.4` 不承诺自动安装或复用 `zellij`、`squad` 或其他额外依赖；任何额外依赖
都必须由明确授权的外置安装事务处理，并以独立回执确认。

### 1.4 安装后验证

从任意工作目录读取运行身份：

```sh
decretum-matrix --runtime-identity
decretum-matrix --help
```

外置安装事务须在所有投影完成后，由活动运行目录之外的既有工具执行一次验收并持久化
回执；普通 runtime 仅读取版本、修订、事务与回执元数据，不扫描或复算文件内容。

---

## 2. 快速开始

在支持 skill 的会话中调用：

```text
$decretum-matrix
```

随后直接描述任务和边界。新会话首次初始化或边界变化时，若最新用户消息没有显式选择
`approval`、`autonomous` 或 `super`，先问授权级别：

```text
approval（审批/默认只读） | autonomous（自主/范围内实施） | super（超级执行/范围内连续推进）
```

授权级别是权限边界；执行方式另选 `serial（串行）` / `parallel（并行）`。二者独立：

- `serial` 不并行派生物理子 agent，但保留分层责任链。
- `parallel` 按层级派生子/孙 agent。
- 普通 `super parallel` 固定走 native 运行时。super-execution（superCC）只由独立
  显式入口启动，两种 runtime 不在同一 task/process 中切换或回退。

常用表达：

```text
$decretum-matrix，以 autonomous 模式修复当前分支，禁止发布，完成后给出验证证据。
```

```text
$decretum-matrix，使用 super并行做只读审查，pending_body_access=NO。
```

---

## 3. 功能大模块

模块划分对应 CLI 的七个命令组，与五层架构一一落位。

| 模块 | 用途 | 日常入口 |
| --- | --- | --- |
| `court` | 任务治理主线：开朝、受理、语义门禁、计划/复核、状态、结诏 | `court open/status/plan/closeout-session` |
| `office` | 官署生命周期：派遣准入、预载确认、回奏、原生派遣与捕获 | `office start/admit/report/finish/native-request` |
| `shiguan` | 史馆与记忆：归档、索引检索、记忆裁定、台账整理 | `shiguan archive-runtime-task/query-shiguan-index` |
| `supercc` | 独立 superCC runtime（zellij + squad 协作面） | `supercc supercc-squad` |
| `install` | 安装、迁移、更新与修复 | `install update/migrate/rollback/fix` |
| `release` | 打包与发布产物构建（源码阶段） | `release package-skill/build-release-artifacts` |
| `check` | 只读门禁与诊断（源码阶段） | `check doctor/debug/all` |

五层架构对应关系：

1. **通用任务治理框架** —— `court` / `office`，默认实现为三省六部。
2. **史馆 GBrain** —— `shiguan`，为治理实现提供共享但无执行权的长期认知。
3. **治理实现** —— 可替换，清单为 `references/manifests/governance-implementations.v1.json`。
4. **能力与运行适配层** —— `install` / `check`，负责投影、迁移与宿主适配。
5. **呈现层** —— `release` 与 `docs/`，负责对外文档与发布产物。

---

## 4. 接口：CLI 与 MCP

### 4.1 CLI

统一入口为 `decretum-matrix`，`court_cli.py` 与 `court_cli_registry.py` 提供命令
权威，清单为 `references/manifests/cli-command-surface.v1.json`。

```sh
decretum-matrix [--format text|json] <group> <command> [args...]
```

默认帮助只展示日常 Skill 面（`court`、`office`、`shiguan`、`supercc`、
`install`、`check`、`release`）；其余 156 条兼容适配器仍可显式调用。生产和验收
使用公开 `decretum-matrix` CLI；PATH 缺失时解析当前 npm prefix 下的命令入口，不降为
内部 Python 业务脚本。

### 4.2 MCP

MCP 与 CLI 共用 `scripts/court_public_api.py`，从 CLI 命令清单投影，全部为
`read_only`，不 spawn CLI、不解析 stdout。当前线为官方 `2026-07-28` 修订，同时保留
`2025-11-25` 兼容路径。

13 个只读工具：

| 工具 | 用途 |
| --- | --- |
| `court.capsule_validate` | 校验 P00 不变量胶囊 |
| `court.closeout_checklist` | 返回十四行结诏清单与缺失项 |
| `court.command_help` | 返回公开 court 命令帮助 |
| `court.dispatch_plan_validate` | 只读校验派遣计划 |
| `court.intake_validate` | 校验受理载荷（会话门禁 + 胶囊） |
| `court.semantic_context_validate` | 校验绑定诏令编号的语义上下文 |
| `court.status` | 读取当前 court 运行时状态 |
| `court.workflow_status` | 读取任务/会话/编号与计划复核绑定 |
| `memory.scan` | 报告记忆扫描边界（不读私有正文） |
| `shiguan.archive_dry_run` | 报告归档边界，不写史馆 |
| `shiguan.entries_query` | 元数据投影查询史馆条目 |
| `shiguan.iku_candidates` | 扫描 IKU 占位候选（只读 dry-run） |
| `shiguan.query` | 查询公开史馆索引记录 |

只读校验、状态和史馆检索优先调用对应 MCP；不可只调 help 后翻源码重写。状态变更走
receipt-bound CLI，真实派遣走宿主。

---

## 5. 文档

安装副本使用[普通启动指南](references/court-normal-startup.md)和
[技能入口](SKILL.md)。以下离线 Wiki、架构原稿和发布资料属于源码仓库文档，
安装运行副本不提供这些源码文件，也不要求在启动时读取或执行源码校验。

- [功能模块说明](docs/wiki/Modules.md)
- [CLI 与 MCP 说明书](docs/wiki/CLI-and-MCP.md)
- [项目架构框架：结果导向的三省六部流程](docs/wiki/Architecture.md)
- [原始架构文档、设计来源与版本实现差异](docs/architecture/README.md)
- [安装](docs/wiki/Installation.md)
- [使用](docs/wiki/Usage.md)
- [治理](docs/wiki/Governance.md)
- [排错](docs/wiki/Troubleshooting.md)
- [发布说明](docs/wiki/Release-Notes.md)
- [GitHub Wiki](https://github.com/RowlandL/decretum-matrix/wiki)

离线 Wiki 源位于 [`docs/wiki`](docs/wiki)。线上 Wiki 在发布门内从这组文件同步，
并由 [`check-sync.ps1`](docs/wiki/check-sync.ps1) 校验一致性。

---

## 6. 版本

当前源码活动版本为 `beta1.1.4`，并以 [`VERSION`](VERSION)、技能元数据、发布清单和
安装/发布回执为准；分支名只是当前工作载体，tag、GitHub Release、npm 以及线上 Wiki
的成功状态只由对应发布回读证明。

本版发布当前宿主适配、默认横向直投、显式 model/effort 路由、已提交诏令门禁和
跨平台预载预算修复。必读 UTF-8 文本按逻辑换行计量，20 KiB 总预算与普通官署
768-byte 余量均未放宽；NIUbash 继续只是可选兼容入口。

`beta1.1.4` 是当前 GitHub 发布版本；npm beta 是独立发布通道。根 `package.json`
继续保持 version-neutral 的 `0.0.0-private`，历史版本和历史发布说明继续保留。

- `beta1.0.8` 曾完成发布阶段全量门禁与收据/锚点同步（领域化账册、统一编号、谱系防
  过拟合、IKU 受控修复、GBrain 治理、Codex host proof 路由与 MCP 工具矩阵）；外部
  tag、GitHub Release、npm 远端状态和宿主实际加载仍由对应回执证明。
- `beta1.0.7` 完成源码收尾，收敛安装收据、宿主/运行验证和只读 MCP 入口。
- `beta1.0.6` 收口原生宿主运行身份与入口证据、分层 dispatch/reuse 的真实证据，
  以及记忆分类中的置信度、并列、否定和未知待审路径。

安装后的运行投影继续保持窄面；独立副本哈希校验器只存在于源码和发布门禁，不进入
skill 加载链。`beta1.0.5`、`beta1.0.4` 与更早 tag 保留为不可变历史证据。

---

## 7. 许可

社区版使用 [GNU AGPLv3](LICENSE)（SPDX `AGPL-3.0-only`）。商业许可需由权利人
另行书面签署，详见 [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)。

`beta0.5.9` 是 Git 已确证的历史 `Apache-2.0` 版本。
`beta0.5.8` 的 tag 证据为 `LICENSE_NOT_ESTABLISHED_FROM_TAG`；其许可判断需要
artifact-specific evidence。

维护者：[@RowlandL](https://github.com/RowlandL)（GitHub id `42199880`）

## 文档导航

[上下文](CONTEXT.md) · [文档目录](docs/INDEX.md) · [beta1.1.3 实施与验收记录](docs/plans/2026-09-12-beta1.1.3-rule-reuse.md)
