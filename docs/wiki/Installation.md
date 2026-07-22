# Installation

## npm

```sh
npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com
```

GitHub Packages 如要求认证，只授予 `read:packages`。使用进程级
`NODE_AUTH_TOKEN` 与临时 npmrc，不要把 token 写入仓库、命令历史或长期配置。

安装包运行受限且可回滚的 `postinstall`：先做内嵌 ZIP/sidecar 的结构性完整性
检查，再备份并覆盖 manifest 管理的公开文件，随后创建真实物理共享史馆根。该
检查只属于安装前基础校验；安装后的 skill 根不保留 release manifest、release
gate、hash checker 或其他发布校验 helper。

首次安装会安装或复用 superCC 所需的两个开源依赖：

| 依赖 | 用途 | 项目 |
| --- | --- | --- |
| `zellij` | 可见 superCC pane 的终端工作区 | https://github.com/zellij-org/zellij |
| `squad` | superCC 结构化任务与消息证据通道 | https://github.com/mco-org/squad |

安装回执会写入对 Zellij 与 squad 项目的感谢和链接。若二者已在 PATH 或
`COURT_TOOL_INSTALL_DIR` 中可用，安装器只记录复用，不重复下载；否则按当前平台
选择 GitHub Release 资产并在解包前做发布资产摘要校验。

默认工具目录：

| 平台 | 默认目录 |
| --- | --- |
| Windows | `C:\Tools\bin` |
| macOS | `~/.local/bin` |
| Linux | `~/.local/bin` |

可用 `COURT_TOOL_INSTALL_DIR` 覆盖工具目录。macOS 使用
`*-apple-darwin.tar.gz` 资产；Linux 使用 `*-unknown-linux-musl.tar.gz` 资产；
Windows 使用 `*-pc-windows-msvc.zip` 资产。

## 安装根

canonical runtime 根始终是：

| 平台 | canonical skill root |
| --- | --- |
| Windows | `%USERPROFILE%\.agents\skills\decretum-matrix` |
| macOS | `~/.agents/skills/decretum-matrix` |
| Linux | `~/.agents/skills/decretum-matrix` |

五根同步目标：

```text
<home>/.agents/skills/decretum-matrix
<home>/.codex/skills/decretum-matrix
<home>/.claude/skills/decretum-matrix
<home>/.hermes/skills/decretum-matrix
<hermes-user-data>/skills/decretum-matrix
```

Hermes user-data 根：

| 平台 | Hermes user-data |
| --- | --- |
| Windows | `%LOCALAPPDATA%\hermes` |
| macOS | `~/.hermes` |
| Linux | `~/.hermes` |

旧 `skills/court-capability-router` 只能不存在，或作为指向同一物理 authority 的
受控兼容 locator；不能保留第二份可写副本。

## 共享史馆

技能代码与共享数据分离。默认数据根为：

```text
<home>/.agents/court-shiguan/decretum-matrix/references
```

安装与升级不得读取、打包或覆盖 private/pending 正文，也不得覆盖史馆实录。
Windows 可创建受控 junction 作为旧 locator；macOS/Linux 不需要 Windows
locator，直接使用 canonical 物理目录。

## ZIP

正式 ZIP 名称为 `decretum-matrix-<version>.zip`，内部 canonical 根为
`decretum-matrix/`。macOS/Linux 专用发布包与 Windows 包共享同一 skill 结构，
差异只在安装说明、平台资产和宿主路径解释；不改变官署、史馆或五根投影结构。

## 验证

在安装后的 skill 根运行：

```sh
python -B scripts/quick_validate.py .
python -B scripts/sync_active_copies.py --json
decretum-matrix --format json --help
```

正式发布还必须让 candidate、pre-install、install receipt 与 post-install 绑定同一
ZIP/npm 载体；安装后不再运行文件哈希校验。
