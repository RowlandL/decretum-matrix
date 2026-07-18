# Release Log

本文件逐条展开 README 的发布摘要。它是整理后的项目发布记录，不是运行日志，也不包含个人史馆记录。

## beta0.5.12 - 2026-07-18

### 发布结论

`release/beta0.5.12` 以已发布并验收的 beta0.5.11 为基线。当前源码、SBOM、
artifact 与 npm candidate 身份已经对齐 beta0.5.12；外部 tag、Release、npm、
资产和线上 Wiki 只有在对应回执完成后才可标记成功。

### 核心变更

1. shared Shiguan/Obsidian 默认根收敛到
   `.agents\court-shiguan\decretum-matrix\references`，旧 LocalAppData 根不再是
   活动 authority，daemon discovery 容忍已退出进程。
2. protected 四锚点恢复 exact length/hash；legacy runtime task 只在全部 binding
   key 缺失时原子 bootstrap，失败完整回滚。
3. host-memory/child-trace、source budget 与 synthetic-secret package fixtures
   收敛，不新增 store、daemon、DB、MQ、ledger 或第二状态机。
4. 宿主 root/global AGENTS、capability index 的旧 skill locator 与 repair hold
   收敛到 canonical `skills/decretum-matrix`。全新 ephemeral 只读 Codex 会话真实
   调用 `$decretum-matrix`，EOF/hash 和三省入口 smoke 通过。
5. README 缩为普通用户入口；详细安装、使用、治理、架构、排错和发布说明迁入
   `docs/wiki`，并提供只读线上/线下一致性检查。

### 边界

- Q0 只冻结 accepted baseline，不实现 Office Pack/DLC/scope/promotion。
- 14-role host projection 先裁定 source of truth，禁止旧 profile 覆盖较新
  `.codex/agents`。
- pending/private 正文保持未读、未哈希、未移动、未删除、未标记已读。
- GitHub Wiki 已启用但尚无线上首页；外部创建与同步需独立发布授权。

## beta0.5.11 — 2026-07-17

### 发布结论
`release/beta0.5.11` 从已发布的 `beta0.5.10` 精确提交顺延。当前显示身份逐字为 `Dercretum-Matrix`，`诏令矩阵` 仅是中文解释；machine/package/invocation 仍为 `decretum-matrix` / `$decretum-matrix`。本节记录源码合同，不预称候选包、安装、迁移或外部发布成功。

### 核心变更
1. RB1 admission：shared hierarchy/profile gate 在 state mutation 前统一裁决；零 mutation 拒绝保持状态不变，v2 lease 绑定 canonical preload，admission event anchor 只追加不回写。
2. RB2 `superCC`：正常 lifecycle 使用 shared delivery preflight；identity ACK、`preload_pending -> delivery success`、`ENTER_DISPATCH` P00 context、delivery/state atomic chain 与 correction gaps 均有 fail-closed 验证。
3. 史馆 Web/autosync：状态转换原子化；filesystem preserve-only daemon 为主通道，REST 可选且非阻塞；既有 daemon 只接收异步 `refresh-request.json`，WebUI 防重复提交并保留本机错误证据。
4. 正式结诏：编号合同是 `层级码串-YYYYMMDD-日内 uppercase base36 序号-四字码`，正例 `SCGSDYJM-20260606-1Z-DAAA`；七层内容谱系是 `史馆总纪·朝制志·官署门·三省六部纲·回复格式目·结诏标识条·内容谱系诏`。`CCR`、`Phase`、`RB`、task id 与 workflow path 均被拒绝。
5. Source split：dispatch context/identity/preload、delivery/state、admission shape 与 autosync public projection 分拆到独立 owning modules；focused gate 改为读取实时 source-state，而非固定 measured bytes。
6. Intervention baseline：fixture caller/direct-superior、bounded child ownership/write scope、serial no-mutation、canonical preload 与 16-slot tree cap 已和 production admission contract 对齐。
7. npm backfill：公开 GitHub Packages `beta` 当前仍是无 dependencies/lifecycle scripts 的 `0.5.10-beta.0` release-assets carrier；本地 version-neutral harness 可推导 `0.5.11-beta.0`，但 npm publish 为 `NOT_RUN`。
8. 安装与 ZIP：canonical physical authority 是 `skills/decretum-matrix`；ZIP internal root 仍为 `court-capability-router/`，旧安装 locator 只可解析到同一 authority，本机路径迁移为 `NOT_RUN`。
9. 发布门禁：42 步由 source 37、installation 4、runtime 1 组成；candidate pre-install 为 36 个 source steps，正常 post-install 为 5 步。`--skip-runtime` 不得声称完成 runtime step。
10. The beta0.5.11 release source tree measures 273 portable files / 6,138,661 bytes against the unchanged ceiling of 275 files / 6,200,000 bytes.

### 验收与发布边界
- `pending_body_access=NO`；pending 正文保持未读、未哈希、未移动、未删除。
- package gate 由 `--require-package` 单独强制，不计入上述 manifest step 数。
- GitHub Packages 如要求认证，只允许最小 `read:packages`，通过进程内 `NODE_AUTH_TOKEN` 和临时 npmrc 使用且不得持久化；发布后必须验证 dist-tag 与 online install。
- candidate SHA、pre/install/post SHA closure、本机安装/迁移以及外部 tag/Release/npm/assets 状态必须引用实际 receipt；缺失时保留 `NOT_RUN|BLOCKED|NOT_AUTHORIZED`。
- `beta0.5.10` 的发布、许可切点、安装和 handoff 记录保持不可变。

## beta0.5.10 — 2026-07-16

### 发布结论

`beta0.5.10` 是 Decretum Matrix（诏令矩阵）的首个新名称 beta 发行版本。
规范产品/skill/package 名为 `decretum-matrix`，调用入口为
`$decretum-matrix`，发行 ZIP 为 `decretum-matrix-beta0.5.10.zip`。为保持
既有安装与史馆连续性，ZIP 内根、物理安装目录和共享史馆 namespace 继续使用
受保护的技术 locator `court-capability-router`，不再把它作为当前产品显示名。

### 核心变更

1. P00 与语义连续性
   新任务、修订、恢复、dispatch、结果、quarantine 和 closeout 都绑定当前
   task、charter revision/semantic epoch、正文 SHA-256、2 KiB invariant capsule
   与紧凑 receipt。普通子官署默认 `fork_turns=none`，只携带必要 pointer/hash，
   不复制完整历史、diff、私密正文或 pending body。

2. 官署身份与 carrier
   十四官署绑定 standing-official TOML、ordinary office dossier、
   Decretum Matrix skill hash 和 preload acknowledgement。六部不得吸收三省审计、
   门下最终复核或太子统筹权限；工匠任务使用 role-prefixed 名称并保持直属链。

3. 许可、权属与来源
   当前社区发行使用 `AGPL-3.0-only`。商业权利只由孙华清另行签署的书面协议
   产生；贡献采用 DCO + CLA gate，CLA 仍标记 `LEGAL_REVIEW_REQUIRED`。
   `@RowlandL`（GitHub id `42199880`）仅作为公开维护者身份。上游
   `cft0808/edict` 固定提交的 MIT 文本、版权与 provenance 独立完整保留，
   不归入孙华清版权。

4. 本地更名与控制面连续性
   child repo、release worktree、managed worktree root、workspace manifest、
   task mount 与新 root refs 已收敛到 `decretum-matrix`。旧 state/events、旧 refs、
   历史 checkpoint 和受保护 locator 均 append-only 保留，没有删除或强推。

5. 打包与安装投影
   release manifest、SBOM、法律文件和新名称文档进入同一确定性 payload。
   Windows 8.3 临时目录别名通过文件身份校验，不再被误判为 root escape；
   stage 内无 `.git` 时只验证 payload/manifest，不伪造 source Git metadata。
   当前工具安装器使用同一 manifest、备份、迁移、索引与逐文件回读合同；真实
   本机安装只在 clean accepted package 后由正式工部工匠子官署执行。

### 验收状态

- Phase 1 P00/RC2/RC4/RC5/RC6：GREEN；门下 `SPEC PASS`；刑部
  `QUALITY READY YES`。
- package privacy：59/59；release manifest：40 steps；artifact builder
  deterministic/promotion self-test：21/21；legal checker real/self-test：PASS。
- 四个受保护史馆文件保持原路径、原长度、原 SHA-256；pending body access 为
  `NO`；Git index、`.pyc` 与 remote count 均为 `0`。
- 本文件记录发行内容与本地验收；remote push、tag、GitHub Release 与线上资产
  上传是否成功，只以对应外部回执为准，不从仓库文字或本地候选目录推定。
- 正式晋升必须显式传入已验候选 ZIP 的 SHA-256；builder 在创建最终版本目录前
  比较重建 ZIP，任何格式错误或字节不一致均 fail closed。

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
python -B scripts/build_release_artifacts.py --mode candidate --json
python -B scripts/check_release_gate.py --phase pre-install --package <zip> --require-package --json
# Install the exact candidate, then:
python -B scripts/check_release_gate.py --phase post-install --package <same-zip> --require-package --install-receipt <install-receipt.json> --skip-runtime --json
# After an annotated tag points to the accepted commit:
python -B scripts/build_release_artifacts.py --mode release --expected-candidate-sha256 <same-zip-sha256> --json
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
- 维护者必须先从干净的 canonical source tree 对无 tag 候选 ZIP 运行 `scripts/check_release_gate.py --phase pre-install --package <zip> --require-package --json`，把该 ZIP SHA256 作为 `source_package_sha256` 传给安装器并保存成功 receipt，安装同一 ZIP 后再运行 `--phase post-install --install-receipt <install-receipt.json>`；解压 release tree 自身包含预期的 portable seed，不作为 active-source budget 输入。只有 annotated tag final 才允许生成 release attestation。
