# Release Notes

## beta0.5.13

状态：source candidate。外部 tag、GitHub Release、npm、资产和最终安装只在
对应发布回执完成后标记成功。

### 主要变化

- 新增 `decretum-matrix` npm 可执行入口和惰性统一 CLI，保留既有命令兼容。
- 新增单解释器 `court open --fast`、门下/太子结果归属和正式性能门禁。
- 覆盖安装改为受管公开文件的持久备份、原子替换、失败自动回滚和显式恢复。
- 根 skill/role preload 最大 19,360 bytes；cold/warm p50 分别提升 88.55%/99.34%。
- 清理当前产品显示名、canonical package root、legacy help 与 release policy 漂移。

### 保持不变

- 安装命令：`npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com`。
- canonical skill/invocation：`decretum-matrix` / `$decretum-matrix`。
- 史馆实录与 private/pending 正文不被覆盖或读取。
- beta0.5.12 已发布工件保持不可变。

## beta0.5.12

状态：release preparation。外部 tag、GitHub Release、npm 与线上 Wiki 只在各自
发布回执完成后标记成功。

### 主要变化

- 修复 shared Shiguan 与 Obsidian 迁移后的 canonical 路径和 daemon discovery。
- 恢复 protected Shiguan anchors，并保持 legacy runtime semantic bootstrap 可恢复。
- 收敛 host-memory/child-trace 验收和 synthetic-secret package fixtures。
- 把源码、SBOM、artifact 和 npm candidate 身份对齐到 beta0.5.12。
- 修复宿主旧 skill locator/repair hold，并增加全新会话的真实 invocation smoke。
- README 收缩为普通用户入口，详细资料迁到版本化离线 Wiki 源。

### 保持不变

- canonical skill/invocation：`decretum-matrix` / `$decretum-matrix`。
- ZIP internal compatibility root：`court-capability-router/`。
- community license：`AGPL-3.0-only`。
- pending/private body access：`NO`。

## beta0.5.11

GitHub prerelease、npm `0.5.11-beta.0`、dist-tag 与 online install smoke 均已完成。
该版本的上传资产保持不可变；beta0.5.12 通过新 candidate 和新发布回执交付。
