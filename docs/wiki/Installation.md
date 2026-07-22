# Installation

## npm

```powershell
npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com
```

GitHub Packages 如要求认证，只授予 `read:packages`。使用进程级
`NODE_AUTH_TOKEN` 与临时 npmrc，不要把 token 写入仓库、命令历史或长期配置。

安装包运行受限且可回滚的 `postinstall`：先做内嵌 ZIP/sidecar 的包完整性校验，再备份并覆盖
manifest 管理的公开文件，把 canonical runtime 安装到
`%USERPROFILE%\.agents\skills\decretum-matrix`；随后创建真实物理共享史馆根，或把
旧物理目录以同卷原子改名迁移到新路径。canonical 根不得是 symlink/junction；旧
locator 只在迁移完成后创建 Windows junction 兼容定位，不以链接代替数据迁移。
全过程不读取、移动或删除 private/pending 正文。安装后只保留 manifest 投影内的
运行文件，旧校验 helper 作为非投影残留被剪除。

空白机须已有 Python 3。默认安装同时登记 Obsidian shared vault 与史馆 daemon
任务，但 npm 安装阶段不强制启动前台/后台 daemon。安装回执写入
`%USERPROFILE%\.agents\install-receipts\decretum-matrix\`，覆盖备份写入
`%USERPROFILE%\.agents\install-backups\decretum-matrix\`。若显式使用 npm
`--ignore-scripts`，上述宿主安装不会执行，需再通过统一入口运行安装请求。

统一入口与源码入口仍产生同一类结构化回执：

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
python -B scripts/sync_active_copies.py --json
```

正式发布还必须让 candidate、pre-install、install receipt 与 post-install 绑定同一
ZIP 包。
