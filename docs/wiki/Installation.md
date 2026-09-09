# Installation

本页是安装说明书。**只想尽快用起来的话，看第 1 节即可**；第 2 节起是安装位置、验证、
升级与回滚的完整口径。

当前发布线为 `beta1.1.2`，GitHub Packages 的 `beta` dist-tag 指向 npm
`1.1.2-beta.0`。安装成功、远端包状态和活动运行身份仍以发布后回读与安装回执为准。

> 口径说明：当前源码 `beta1.1.2` 属于未发行的本地开发版本；本页命令与目标不构成对
> `beta1.1.2` 的安装授权，其安装需要后续显式授权的外置安装事务与匹配回执。

---

## 1. 最快路径（三步）

### 第 1 步：安装

```sh
npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com
```

### 第 2 步：确认命令可用

```sh
decretum-matrix --version
```

### 第 3 步：在会话中调用

```text
$decretum-matrix
```

`npm install` 返回 0 只说明命令执行完成，不等于安装已被验证——真正的验收见第 4 节。

---

## 2. 认证

GitHub Packages 如要求认证，只授予最小 `read:packages`。使用进程级
`NODE_AUTH_TOKEN` 与临时 npmrc：

```sh
# 只在当前进程生效，不落盘
export NODE_AUTH_TOKEN=<你的 read:packages token>
npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com
unset NODE_AUTH_TOKEN
```

不要把 token 写入仓库、命令历史或长期配置。

---

## 3. 安装位置

### 3.1 canonical 运行根

canonical runtime 根始终是：

| 平台 | canonical skill root |
| --- | --- |
| Windows | `%USERPROFILE%\.agents\skills\decretum-matrix` |
| macOS | `~/.agents/skills/decretum-matrix` |
| Linux | `~/.agents/skills/decretum-matrix` |

### 3.2 五根同步目标

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

额外目标 `<home>/.qoder/skills/decretum-matrix` 只有在显式 `--include-qoder`
授权下才允许；它不改变默认五根契约。

旧 `skills/court-capability-router` 只能不存在，或作为指向同一物理 authority 的受控
兼容 locator；不能保留第二份可写副本。

### 3.3 共享史馆数据根

技能代码与共享数据分离。默认数据根为：

```text
<home>/.agents/court-shiguan/decretum-matrix/references
```

安装与升级不得读取、打包或覆盖 private/pending 正文，也不得覆盖史馆实录。
Windows 可创建受控 junction 作为旧 locator；macOS/Linux 直接使用 canonical 物理目录。

---

## 4. 安装后验证

从任意工作目录读取运行身份：

```sh
decretum-matrix --runtime-identity
```

外置安装事务须在所有投影完成后，由活动运行目录之外的既有工具执行一次验收并持久化
回执；普通 runtime 仅读取版本、修订、事务与回执元数据，不扫描或复算文件内容。

安装后的 skill 根**不保留** release manifest、release gate、hash checker 或其他发布
校验 helper。

---

## 5. 升级

升级已存在的全局 npm 包时，外置安装事务必须显式选择替换路径。默认 fail-closed 拒绝
覆盖，只有调用方明确选择替换时才移动旧包并安装候选包。

旧全局包移动到以 npm prefix 和备份根为基准的相对路径备份清单，根 shim 只做快照记录；
路径类字段优先使用相对路径，避免主机目录变化造成安装识别或回滚失效。绝对路径只用于
当次宿主证据。

`beta1.1.2` 不承诺自动安装或复用 `zellij`、`squad` 或其他额外依赖。任何额外依赖
都必须由明确授权的外置安装事务处理，并以独立回执确认。

---

## 6. 回滚与迁移

### 6.1 旧 locator 冲突

如果物理 `court-capability-router` locator 与 canonical 目录冲突，不要手工删除或覆盖。
先跑只读计划：

```powershell
python -B scripts/migrate_legacy_skill_locator.py plan --json
```

拿到明确书面授权后应用，并保留返回的 `receipt_path`：

```powershell
python -B scripts/migrate_legacy_skill_locator.py apply --write --json
```

回滚同样绑定回执：

```powershell
python -B scripts/migrate_legacy_skill_locator.py rollback --receipt <receipt_path> --write --json
```

### 6.2 current-tool 根被拒绝

若回执绑定安装器以 `protected_anchor_wrong_target` 拒绝 current-tool 根，说明它是携带
shared-only 史馆锚点的旧完整副本。不要手工修剪或覆盖，从源码检出先做可回滚的目录级迁移：

```powershell
python -B scripts/migrate_current_tool_replica.py plan  --package <release_zip> --json
python -B scripts/migrate_current_tool_replica.py apply --package <release_zip> --write --json
```

该工具会原子归档整个旧 current-tool 根到
`~/.agents/install-backups/decretum-matrix/`，归档安装器及其 SHA-256，再以事务方式
应用包投影。回滚用同一个 ZIP 与回执：

```powershell
python -B scripts/migrate_current_tool_replica.py rollback --receipt <receipt_path> --package <release_zip> --write --json
```

---

## 7. ZIP 安装

正式 ZIP 名称为 `decretum-matrix-<version>.zip`，内部 canonical 根为
`decretum-matrix/`。macOS/Linux 专用发布包与 Windows 包共享同一 skill 结构，
差异只在安装说明、平台资产和宿主路径解释；不改变官署、史馆或五根投影结构。

---

## 8. 安装边界

- 本地同步**不是**发布：不得推送 Git 分支、创建 tag、上传资产、开 PR、启动公共服务、
  读取 private pending 正文或改动无关项目。
- 文件差异是正常的待复制工作，不是任务阻塞；报告 copied / unchanged / removed 数量，
  除非源投影缺失或目标路径不安全才停止。
- 安装验收在安装阶段一次完成，随后移除安装专用检查。正常启动不重复安装验收。

---

## 9. 下一步

- 想了解怎么用：看 [Usage](Usage.md)。
- 想知道有哪些功能模块：看 [Modules](Modules.md)。
- 想直接用 CLI/MCP：看 [CLI and MCP](CLI-and-MCP.md)。
- 安装出问题：看 [Troubleshooting](Troubleshooting.md)。
