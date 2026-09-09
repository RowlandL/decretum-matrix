# Installation

## npm

当前发布线为 `beta1.1.2`，GitHub Packages 的 `beta` dist-tag 指向 npm
`1.1.2-beta.0`。安装成功、远端包状态和活动运行身份仍以发布后回读与安装回执为准。

```sh
npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com
```

GitHub Packages 如要求认证，只授予 `read:packages`。使用进程级
`NODE_AUTH_TOKEN` 与临时 npmrc，不要把 token 写入仓库、命令历史或长期配置。

升级已存在的全局 npm 包时，外置安装事务必须显式选择替换路径。旧全局包移动到以 npm
prefix 和备份根为基准的相对路径备份清单，根 shim 只做快照记录；路径类字段优先使用
相对路径，避免主机目录变化造成安装识别或回滚失效。绝对路径只用于当次宿主证据。

已发行版本的安装、回滚与安装前检查须由对应的外置安装事务和独立回执确认；安装后的
skill 根不保留 release manifest、release gate、hash checker 或其他发布校验 helper。

beta1.1.2 不承诺自动安装或复用 `zellij`、`squad` 或其他额外依赖。任何额外依赖都必须
由明确授权的外置安装事务处理，并以独立回执确认。

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

安装后可从任意工作目录读取运行身份：

```sh
decretum-matrix --runtime-identity
```

外置安装事务须在所有投影完成后，由活动运行目录之外的既有工具执行一次验收并持久化
回执；普通 runtime 仅读取版本、修订、事务与回执元数据，不扫描或复算文件内容。
