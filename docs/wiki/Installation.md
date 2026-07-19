# Installation

## npm

```powershell
npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com
```

GitHub Packages 如要求认证，只授予 `read:packages`。使用进程级
`NODE_AUTH_TOKEN` 与临时 npmrc，不要把 token 写入仓库、命令历史或长期配置。

安装包不运行隐式 `postinstall`。统一入口与源码入口产生同一类结构化回执：

```powershell
decretum-matrix --format json --help
decretum-matrix --format json install update --request-file .\install-request.json
decretum-matrix --format json install rollback --request-file .\rollback-request.json
```

更新请求先以 `write=false` 生成计划；核对后改为 `write=true`，即可原子覆盖
manifest 管理的公开文件。每次覆盖前都会持久备份原文件；失败自动回滚，成功
回执给出可再次调用的 `backup_root`。目标独有文件、史馆实录与 private/pending
正文不进入覆盖集。

## ZIP

正式 ZIP 名称为 `decretum-matrix-<version>.zip`，内部 canonical 根为
`decretum-matrix/`。canonical 安装目录始终是：

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

安装与升级不得读取、打包或覆盖 private/pending 正文，也不得覆盖史馆实录。

## 验证

在安装后的 skill 根运行：

```powershell
python -B scripts/quick_validate.py .
python -B scripts/check_catalog.py --strict
python -B scripts/check_active_copy_hashes.py --json
```

正式发布还必须让 candidate、pre-install、install receipt 与 post-install 使用同一
ZIP SHA-256。
