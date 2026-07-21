# Release Notes

## beta1.0.2

- Skill 定义收敛为围绕“诏令”的多-agent 协作体系；正式任务默认三省六部，
  闲聊、轻量交流、正式任务、纠正、延续和主动结诏按场景分流。
- `beta0.5.9` 已有能力和用户明确新增功能不得因提速被删除；项目级发布/安装/
  法律/package gate 不进入普通 Skill 启动链。
- 史馆基础记忆、GBrain 整理沉淀、Git 联邦管理分层保留；GBrain 不替代基础召回，
  Git 联邦只作为显式史馆管理面。
- `approval|autonomous|super` 与 `serial|parallel` 分开记录和验证；尚书统筹六部
  仍要求按层级下派必要六部。
- CLI 外部目录运行修复为调用者相对路径解析；项目 check/release 命令仍使用代码根。
- npm 版本为 `1.0.2-beta.0`，继续使用 `beta` dist-tag；远端状态以后续回读为准。

## beta1.0.1

- authority 精确为 `approval|autonomous|super`，behavior 精确为
  `serial|parallel`；两者正交，六种组合均有结构化回归。
- 普通 super parallel 只走 native；superCC 使用独立入口、task store、dossier、
  transport、admission 和 lifecycle，不与 native 共存、切换或回退。
- 修复 semantic template 生产者/消费者不一致；无效 authority revision 在准入前
  fail closed，保持零 dispatch 与无手工绕过。
- capability snapshot 在三省审议前解析并缓存，覆盖 skill、MCP、plugin、CLI 和
  script 建议，无需为只读 snapshot 派生吏部官署。
- npm 版本为 `1.0.1-beta.0`，继续使用 `beta` dist-tag。

## beta1.0.0-hotfix-v2

状态：Windows npm online-install 修复候选；最终状态由新 tag、Release、npm 与
空白机回执证明。

### 主要修复

- npm Python launcher 在入口统一使用 UTF-8 stdout/stderr，避免 GBK 控制台打印
  结构化 postinstall receipt 时触发 `UnicodeEncodeError`。
- 新增严格 GBK stream 行为回归，直接验证 `U+FFFD` 能以 UTF-8 输出。
- npm 版本为 `1.0.0-beta.0.hotfix.2`；已发布 v1 保留不可变并由 v2 取代。

### 保持不变

- ordinary/superCC carrier pointer 与 CLI archive receipt 修复沿用 v1。
- 安装命令、五根、许可、pending/private 零访问与史馆保护边界不变。

## beta1.0.0-hotfix-v1

状态：hotfix source candidate；安装、tag、GitHub Release 与 npm 由最终发布回执证明。

### 主要修复

- 普通 `super并行` 与 superCC 改为独立结构化选择：共享官署 profile 不拆分，
  carrier pointer 分别指向普通 dossier 与显式可见 dossier。
- 普通 Codex role/probe 不再加载或回显 superCC、squad、zellij 与可见拓扑。
- 统一 CLI 的 `shiguan archive-checkpoint` 输出带哈希的结构化回执；诏令编号、
  古制谱系和作业 AI 只能逐字取自该回执。
- 完整 root+dossier+profile 预载最大 20,173 bytes；cold/warm p50 提升
  88.60%/99.33%，保持单解释器快速路径。
- hotfix npm 版本为 `1.0.0-beta.0.hotfix.1`，不覆盖 `1.0.0-beta.0`。

### 保持不变

- 安装命令：`npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com`。
- canonical skill/invocation：`decretum-matrix` / `$decretum-matrix`。
- pending/private 正文保持零访问，史馆实录不被安装覆盖。

## beta1.0.0

状态：已发布基线 + coverage revision source accepted。原 tag、五项 GitHub 资产与
npm `1.0.0-beta.0` 保持首次发布证据；覆盖候选、安装和再次发布由新回执证明。

### 覆盖修订

- shared `references` 增加 local-only Git 管理 hub，严格 allowlist 且无 remote。
- Codex/Claude Code/Hermes 原生记忆保持独立仓库，通过 registry、双向 link、
  native/shared commit 和 paired receipt 形成可验证联邦。
- 空白机只读探测不写入；显式授权后创建三类 canonical memory root 并统一纳入史馆。
- GBrain recall 携带路径裁剪后的 Git provenance，仍为 advisory、无执行权。
- GitHub 每版 Release 改为简短说明，beta1.0.0 设为 Latest；README 恢复品牌图标。

### 当前边界

- 当前源码分支：`release/beta1.0.0`。
- 已接受前序版本：`beta0.5.13`。
- 版本直接从 `beta0.5.13` 跳至 `beta1.0.0`；未创建任何中间 beta0.5.x
  release 或第二 worktree。
- 43 项 candidate source step 均有 PASS 证据；live install/runtime 仍由后续门验证。
- 当前 GitHub Release metadata 已更新；覆盖 tag/资产/npm 尚未执行。
- pending/private 正文保持零访问。

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
