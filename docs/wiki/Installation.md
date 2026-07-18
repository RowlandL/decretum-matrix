# Installation

## npm

```powershell
npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com
```

GitHub Packages 如要求认证，只授予 `read:packages`。使用进程级
`NODE_AUTH_TOKEN` 与临时 npmrc，不要把 token 写入仓库、命令历史或长期配置。

## ZIP

正式 ZIP 名称为 `decretum-matrix-<version>.zip`，内部兼容根保持
`court-capability-router/`。canonical 安装目录始终是：

```text
%USERPROFILE%\.agents\skills\decretum-matrix
%USERPROFILE%\.codex\skills\decretum-matrix
%USERPROFILE%\.claude\skills\decretum-matrix
%USERPROFILE%\.hermes\skills\decretum-matrix
%LOCALAPPDATA%\hermes\skills\decretum-matrix
```

旧 `skills/court-capability-router` 只能不存在，或作为指向同一物理 authority 的
受控兼容 locator；不能保留第二份可写副本。

## 共享史馆

技能代码与共享数据分离。默认数据根为：

```text
%USERPROFILE%\.agents\court-shiguan\decretum-matrix\references
```

安装与升级不得读取、打包或覆盖 private/pending 正文。

## 验证

在安装后的 skill 根运行：

```powershell
python -B scripts/quick_validate.py .
python -B scripts/check_catalog.py --strict
python -B scripts/check_active_copy_hashes.py --json
```

正式发布还必须让 candidate、pre-install、install receipt 与 post-install 使用同一
ZIP SHA-256。
