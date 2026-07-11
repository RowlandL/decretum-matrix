# Release Log

本文件逐条展开 README 的发布摘要。它是整理后的项目发布记录，不是运行日志，也不包含个人史馆记录。

## beta0.5.8 — 2026-07-11

### 能做什么

1. 三省六部责任路由
   太子负责收旨与回奏，中书省拟旨，门下省封驳，尚书省差遣，六部按职责执行，史馆保存经过脱敏的证据链。

2. 本地能力调度
   可按任务边界选择 skills、MCP、CLI、脚本与 agente。每次调度受职责、依赖、证据价值、容量、深度、请求预算和安全门禁约束。

3. Portable 运行与审计
   提供目标机 bootstrap、共享史馆 seed、metadata-only 记忆桥、本地/LAN Web 管理以及安装和发布检查。

### 更新了什么

1. Multi-Agent V2 配置统一
   V2 使用 `features.multi_agent_v2.max_concurrent_threads_per_session = 16`。该值覆盖整棵会话树，根线程占一槽，因此仅根活动时最多有 15 个 child 槽位；`max_depth = 4`，实际并发仍按可证容量收紧。

2. 官署显性语义
   六部默认 `non-visible`、`silent`。只有尚书省按已批准步骤差遣后才启用；显性六部还需最新旨意明确授权 bounded role set。

3. 发布身份
   版本固定为 `beta0.5.8`，ZIP 固定为 `court-capability-router-beta0.5.8.zip`，ZIP 内根固定为 `court-capability-router/`。

### 修复了什么

1. Legacy 配置漂移
   不再把 `[agents].max_threads` 当作 V2 推荐配置。V2 使用整树并发字段，根线程计槽。

2. Portable 史馆边界
   ZIP 不包含 `references/plan-archives/`、`references/memory-decisions/`，也不包含这两个目录的占位 README。目标机首次初始化共享史馆根时才创建这些私有目录。

3. Fail-open 打包策略
   原大小写敏感 denylist 已改为精确结构 allowlist。未知顶层、未知 `references` 目录、未知史馆 seed 路径直接阻断，而不是静默收入包内。

4. 文件系统与归档攻击面
   源复制拒绝 symlink、junction、reparse point 和特殊文件；ZIP 复验拒绝绝对路径、UNC、`..`、反斜杠成员、重复名、大小写碰撞、链接、加密成员、嵌套归档、异常单文件/总大小与压缩炸弹。

5. 内容隐私
   二进制默认拒绝；带作者元数据的 DOCX 被排除，保留 Markdown 手册。文本扫描扩展到常见 token、URI 凭据、真实宿主用户路径、UNC/NAS 与 home 路径，同时允许明确的 generic 测试示例。

6. Source-state 门禁
   历史副本与 generated runtime 的 0 文件/0 字节目标从 warning 提升为 release hard fail。新增回归保证 pending body 仍只做 metadata/stat 检查，不读取正文。

### 新增了什么

1. 隐私回归
   新增 20 项 package privacy 测试，覆盖路径策略、reparse、归档结构、压缩阈值、host path、token 与安全 fixture。

2. 发布元数据
   新增 `VERSION`、`CHANGELOG.md`、`RELEASE-LOG.md` 和根 `release-manifest.json`。

3. 完整性证据
   ZIP 外附 `court-capability-router-beta0.5.8.zip.sha256`。根 manifest 记录除自身外每个 payload 文件的 Git mode、字节数和 SHA256，并提供排序后的 payload index 摘要。

4. Git 发布来源
   专用仓库仅使用 repository-local identity，不设置 remote；最终 ZIP 从 annotated tag `beta0.5.8` 生成，并与 Git tree 逐路径、大小和 SHA256 比对。

### 隐私边界

本版本不包含个人史馆正文、plan archives、memory decisions、sessions、logs、backups、Obsidian 配置/API key、peer/import/runtime 状态、私密凭据、本机绝对路径或宿主生成索引。

### 校验契约

- SHA256 sidecar 必须与 ZIP 实际哈希一致。
- `VERSION`、README 与 manifest 的 release label、artifact name 必须一致。
- manifest inventory 必须等于 Git tree 与 ZIP payload（排除 manifest 自身）。
- `references/manifests/release-gates.v1.json` 是门禁策略，不是发行物清单。
- 维护者必须从干净的 canonical source tree 对最终 ZIP 运行 `scripts/check_release_gate.py --package <zip> --require-package --skip-runtime --json`；解压 release tree 自身包含预期的 portable seed，不作为 active-source budget 输入。
