# Release Log

本文件逐条展开 README 的发布摘要。它是整理后的项目发布记录，不是运行日志，也不包含个人史馆记录。

## beta0.5.9 — 2026-07-12

### 发布结论

`beta0.5.9` 是面向公开 GitHub 仓库的本地发布候选：源码、法律/隐私文件、严格 payload manifest、完整门禁、不可覆盖构建器和版本化安装包目录均纳入同一发布契约。GitHub 推送和 Release 创建仍是外部门禁；仓库没有内嵌 remote、账号或凭据，不能据此声称已经在线发布。

### 核心变更

1. 动态消息预算
   正式纳入 `COURT-DYNMSG-BUDGET-V1-20260712`：dispatch message 的 floor 为 6000、quantum 为 1000、ceiling 为 12000。预算诊断明确区分实际分配、上限夹紧和主机证据，避免把不可证明的容量写成已验证事实。

2. 共享能力索引
   capability-index 门禁改从共享史馆根解析当前目录，不再依赖可能过期的 skill-local catalog；路径错误转为结构化失败，不向外泄露未处理 traceback。

3. 开源许可与上游边界
   项目原创材料采用 Apache License 2.0，并提供 `NOTICE`、`CONTRIBUTING.md`、`SECURITY.md`、`PRIVACY.md` 与 SPDX 2.3 SBOM。选择 Apache-2.0 的主要工程理由是明确的专利许可、贡献与 NOTICE 治理更适合长期协作；前提始终是贡献者确有授权这些材料的权利。

   `cft0808/edict` 在审查提交 `14a207557719c046af0f993a7bff1cc5a5015b33` 使用 MIT License。MIT 允许使用、修改、再发布和再许可，但分发其软件或实质部分时必须保留版权及许可文本。本项目把它限定为工程语义 benchmark，无 runtime dependency、无 governing authority；为保守合规，`THIRD_PARTY_NOTICES.md` 仍保留完整 MIT notice。该记录不替代作者身份、商标、素材来源或实质相似性方面的人工法律判断。

4. 确定性、不可覆盖打包
   ZIP 使用 stored entries、固定 `1980-01-01T00:00:00Z` 时间戳、`100644` mode 与 UTF-8 路径字节排序。源读取检查文件身份和 reparse/symlink 边界，候选文件经复验后以同目录 hard-link no-replace 方式发布。已有输出、已有版本目录或竞态创建的资产一律拒绝，不提供 `--force`。

5. 严格发布清单与门禁
   `release-manifest.json` 升级为 `court.release_manifest.v2`，记录除自身外的精确 payload 路径、mode、size、SHA256、排序摘要、generated portable seeds 与 source/package 计数。发布门禁扩展为 40 步，其中 35 个 source、4 个 installation、1 个 conditional runtime，并新增法律、能力索引、payload、隐私回归和 artifact builder 自检。

6. 本地服务与 peer 安全
   Web 和 daemon 默认只绑定 `127.0.0.1`，LAN 必须显式传入 `--host 0.0.0.0`。peer URL 禁止凭据、query、fragment 和 base path；非回环 peer 必须 HTTPS，重定向被拒绝，bearer token 不跨 origin 转发。quoted JSON secret 已纳入脱敏；`.shiguan-key` 明确为 bearer secret 的混淆容器而非加密格式。

### 不可变版本与发布资产

- `beta0.5.8` commit、annotated tag、原始散落资产和版本目录保持原样；新流程只复制历史证据，不移动、不删除、不覆盖。
- `beta0.5.9` 最终目录必须一次性创建，并包含 ZIP、SHA256 sidecar、release attestation、release notes 和 SBOM；重复运行在写入任何资产前失败。
- attestation 绑定 HEAD commit、annotated tag object/commit、Git tree、payload manifest 摘要和每个外部资产摘要。无签名标签记为 `tag_signature=UNAVAILABLE`，不得写成 `PASSED`。

### 已知限制与停止门禁

- Multi-Agent V2 的物理宿主 child-thread 回收仍未得到完整证明，本版本不宣称修复；容量未知或终态节点未释放时继续 fail closed。
- GitHub owner/repository remote 与认证客户端必须由真实外部状态提供。缺少任一项时，push、tag push 和 GitHub Release 均为 `BLOCKED/NOT_RUN`，不得猜测 remote 或伪造成功。
- 开源许可不能修复来源不明、未经授权的复制、个人信息、秘密、第三方商标或贡献权属缺口；这些问题出现时必须停止公开发布并取得权利人/法律专业人士确认。

### 验证入口

```powershell
python -B scripts/check_release_legal.py --self-test --json
python -B scripts/release_payload_manifest.py --self-test --check --json
python -B scripts/check_release_manifest.py --json
python -B scripts/build_release_artifacts.py --self-test --json
python -B scripts/check_release_gate.py --package <zip> --require-package --skip-runtime --json
```

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
