# Decretum Matrix（诏令矩阵）

<p align="center">
  <img src="assets/brand/decretum-matrix-icon.svg" alt="Decretum Matrix icon" width="160">
</p>

Decretum Matrix 是通用任务治理框架：它把事实、解释、裁定、行动、
验证、记忆和呈现组织成可追溯关系，并在 Codex、Agent Skills、Claude Code 与
Hermes 的本地 skill 环境中运行。内置的分层治理实现是完整默认治理；GBrain
记忆中枢为不同治理实现提供共享但无执行权的长期认知。

## 安装

```sh
npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com
decretum-matrix --format json --help
```

当前源码候选为 `1.0.6-beta.0`。安装命令解析到 registry 已发布的 `beta`；
实际 dist-tag 与发布时间只由发布回执证明。需要认证时只授予最小
`read:packages`，且不得持久化 token。

首次 npm 安装会安装或复用高级执行（super-execution）依赖 `zellij` 与 `squad`，并在安装回执中写明
对 Zellij 与 squad 开源项目的感谢和链接。

## 开始使用

在支持 skill 的会话中调用：

```text
$decretum-matrix
```

随后直接描述任务和边界。新会话首次初始化或边界变化时，若最新用户消息没有
显式选择 `approval`、`autonomous` 或 `super`，先问授权级别：
`approval（审批/默认只读） | autonomous（自主/范围内实施） |
super（超级执行/范围内连续推进）`。授权级别是权限边界；执行方式另选
`serial（串行）` / `parallel（并行）`。`serial（串行）` 不并行派生物理子
agent，但保留分层责任链；`parallel（并行）` 按层级派生子/孙
agent。授权不是执行方式；二者独立。
普通 `super parallel` 固定走 native 运行时。super-execution（superCC）只由独立显式入口启动，两种
runtime 不在同一 task/process 中切换或回退。

## 能做什么

- 按职责路由规划、实现、审查、证据和收口。
- 在详细计划前评估真实目标、使用场景、关键要求和最终验收标准，避免表层理解。
- 通过有界治理实现承载不同角色语义，同时保持统一任务与证据权威。
- 由 GBrain 记忆中枢提供来源、范围与时效明确的 metadata-first 召回。
- 以本地无 remote 的共享记忆 Git 管理 hub 连接 Codex、Claude Code 与 Hermes 原生记忆仓库；空白机仅在显式授权后创建 canonical memory roots，并保留双向来源与提交证据。
- 调用已登记的本地 skills、MCP、CLI、脚本与 agents。
- 保持任务语义、权限、隐私和 Git 写集边界。
- 提供可验证的安装、迁移、回滚、打包与发布流程。

## 文档

- [安装](docs/wiki/Installation.md)
- [使用](docs/wiki/Usage.md)
- [治理](docs/wiki/Governance.md)
- [架构](docs/wiki/Architecture.md)
- [排错](docs/wiki/Troubleshooting.md)
- [发布说明](docs/wiki/Release-Notes.md)
- [GitHub Wiki](https://github.com/RowlandL/decretum-matrix/wiki)

离线 Wiki 源位于 [`docs/wiki`](docs/wiki)。线上 Wiki 在发布门内从这组文件同步，
并由 [`check-sync.ps1`](docs/wiki/check-sync.ps1) 校验一致性。

## 当前版本

当前源码发布身份以 [`VERSION`](VERSION) 和
[`release-manifest.json`](release-manifest.json) 为准；分支名只是当前工作载体。
tag、GitHub Release、npm 以及线上 Wiki 的成功状态只由对应发布回执证明。

`beta1.0.6` 收口原生宿主运行身份与入口证据、分层 dispatch/reuse 的真实证据，
以及记忆分类中的置信度、并列、否定和未知待审路径。安装后的
运行投影继续保持窄面；独立副本哈希校验器只存在于源码和发布门禁，不进入 skill
加载链。`beta1.0.5`、`beta1.0.4` 与更早 tag 保留为不可变历史证据。

## 许可

社区版使用 [GNU AGPLv3](LICENSE)（SPDX `AGPL-3.0-only`）。商业许可需由权利人
另行书面签署，详见 [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)。

`beta0.5.9` 是 Git 已确证的历史 `Apache-2.0` 版本。
`beta0.5.8` 的 tag 证据为 `LICENSE_NOT_ESTABLISHED_FROM_TAG`；其许可判断需要 artifact-specific evidence。

维护者：[@RowlandL](https://github.com/RowlandL)（GitHub id `42199880`）
