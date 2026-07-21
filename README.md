# Decretum Matrix（诏令矩阵）

<p align="center">
  <img src="assets/brand/decretum-matrix-icon.svg" alt="Decretum Matrix icon" width="160">
</p>

Decretum Matrix（诏令矩阵）是通用任务治理框架：它把事实、解释、裁定、行动、
验证、记忆和呈现组织成可追溯关系，并在 Codex、Agent Skills、Claude Code 与
Hermes 的本地 skill 环境中运行。三省六部是完整的默认官方治理实现，史馆
GBrain 为不同治理实现提供共享但无执行权的长期认知。

## 安装

```powershell
npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com
decretum-matrix --format json --help
```

当前源码候选为 `1.0.2-beta.0`。安装命令解析到 registry 已发布的 `beta`；
实际 dist-tag 与发布时间只由发布回执证明。需要认证时只授予最小
`read:packages`，且不得持久化 token。

## 开始使用

在支持 skill 的会话中调用：

```text
$decretum-matrix
```

随后直接描述任务和边界。三权是授权边界：`approval` 为审批权，默认只读和等
待批准；`autonomous` 为自主权，在给定范围内本地实施；`super` 为超级执行权，
可在明确边界内连续推进。运行方式另选：`serial` 为串行，不并行开子 agente；
`parallel` 为并行，按层级派生子/孙 agente。权力不是运行方式；二者独立。
普通 `super parallel` 固定走 native。superCC 只由独立显式入口启动，两种
runtime 不在同一 task/process 中切换或回退。

## 能做什么

- 按职责路由规划、实现、审查、证据和收口。
- 在详细计划前评估真实目标、使用场景、关键要求和最终验收标准，避免表层理解。
- 通过有界治理实现承载不同角色语义，同时保持统一任务与证据权威。
- 由史馆 GBrain 提供来源、范围与时效明确的 metadata-first 召回。
- 以本地无 remote 的共享史馆 Git 管理 hub 连接 Codex、Claude Code 与 Hermes 原生记忆仓库；空白机仅在显式授权后创建 canonical memory roots，并保留双向来源与提交证据。
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

当前源码分支为 `release/beta1.0.2`，发布身份以 [`VERSION`](VERSION) 和
[`release-manifest.json`](release-manifest.json) 为准。tag、GitHub Release、npm
以及线上 Wiki 的成功状态只由对应发布回执证明。

`beta1.0.2` 整改启动语义、场景成本、目录外 CLI 和尚书统六部语义；`beta1.0.1`
作为上一问题基线保留历史证据，`beta1.0.0` 及两个
hotfix tag 继续保留不可变历史证据。

## 许可

社区版使用 [GNU AGPLv3](LICENSE)（SPDX `AGPL-3.0-only`）。商业许可需由权利人
另行书面签署，详见 [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)。

`beta0.5.9` 是 Git 已确证的历史 `Apache-2.0` 版本。
`beta0.5.8` 的 tag 证据为 `LICENSE_NOT_ESTABLISHED_FROM_TAG`；其许可判断需要 artifact-specific evidence。

维护者：[@RowlandL](https://github.com/RowlandL)（GitHub id `42199880`）
