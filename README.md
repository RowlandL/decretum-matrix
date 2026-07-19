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

当前源码候选为 `1.0.0-beta.0.hotfix.2`。安装命令解析到 registry 已发布的 `beta`；
实际 dist-tag 与发布时间只由发布回执证明。需要认证时只授予最小
`read:packages`，且不得持久化 token。

## 开始使用

在支持 skill 的会话中调用：

```text
$decretum-matrix
```

随后直接描述任务和边界。普通并行只写入 `ordinary_parallel` topology，并通过
`child_agent` / `worktree_thread` carrier 指向普通官署 dossier；可见 CLI/pane
运行面只能由独立的显式 runtime selector 选择。

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

当前源码分支为 `release/beta1.0.0-hotfix-v2`，发布身份以 [`VERSION`](VERSION) 和
[`release-manifest.json`](release-manifest.json) 为准。tag、GitHub Release、npm
以及线上 Wiki 的成功状态只由对应发布回执证明。

`hotfix-v1` 保留不可变发布证据；`hotfix-v2` 修复其 Windows GBK npm
`postinstall` 最终 JSON 输出失败。

## 许可

社区版使用 [GNU AGPLv3](LICENSE)（SPDX `AGPL-3.0-only`）。商业许可需由权利人
另行书面签署，详见 [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)。

`beta0.5.9` 是 Git 已确证的历史 `Apache-2.0` 版本。
`beta0.5.8` 的 tag 证据为 `LICENSE_NOT_ESTABLISHED_FROM_TAG`；其许可判断需要 artifact-specific evidence。

维护者：[@RowlandL](https://github.com/RowlandL)（GitHub id `42199880`）
