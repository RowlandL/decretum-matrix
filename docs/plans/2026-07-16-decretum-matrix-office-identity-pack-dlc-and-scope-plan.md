# Decretum Matrix Office Identity Pack、DLC 与作用域治理计划

状态：`QUEUED_POST_MAINLINE_REBASE / PLAN_ONLY`

日期：2026-07-16

产品：Decretum Matrix（诏令矩阵） / `decretum-matrix`

本计划只定义主线结项后的后续工作。本轮不得实现 Office Identity Pack、
DLC、`.decretum` 作用域、promotion 或 `$decretum-office-architect`，不得改变
当前版本行为，也不得创建第二仓库、第二 ledger、第二执行权威或任何 remote。

当前审查前像仅为中间提交 `6f97c91`；它不是最终实现基线。所有目录、CLI、
schema、shared Shiguan Git 状态与 carrier 细节必须在主线最终闭环后由
`POST_MAINLINE_REBASE/P0` 重新采集和裁定。

## 1. 排队与基线

执行游标固定为：

```text
A02 current work
-> accepted local commit
-> clean deterministic package
-> required local install/migration/index receipts
-> next release branch/worktree/task handoff accepted
-> MAINLINE_ACCEPTED_BASELINE_GATE
-> POST_MAINLINE_REBASE/P0
-> this plan Q0
```

`MAINLINE_ACCEPTED_BASELINE_GATE` 只有在以下证据全部来自同一精确主线基线时
才通过：

- clean accepted child commit、branch、common-dir 与 clean worktree；
- deterministic package、release manifest、SBOM、identity manifest 与逐文件
  SHA-256；
- Decree Kernel schema/hash、standing profile/dossier schema/hash；
- 本机安装、受影响数据迁移、能力/史馆索引回读 receipt；
- root mapping/task handoff receipt，root/child/managed data repo index 均为 `0`；
- protected Shiguan 四文件原路径/原长度/原 SHA-256；
- `pending_body_access=NO`。

任何 dirty worktree、未验包、漂移 schema、未完成 handoff 或仅凭当前 A02
工作副本启动本计划，均返回 `BASELINE_NOT_ACCEPTED`。

### POST_MAINLINE_REBASE/P0 — 最终主线重定

本阶段只允许修改本计划本身及 root controller 正常生成的本 task
`.repo-control/state|events` 映射元数据；不得修改产品代码。必须：

1. 重新读取 root authority、当前 project memory、A02 execution/recovery receipt；
2. 固定 accepted child branch/HEAD/common-dir、clean package、安装/迁移/index 与
   next-release handoff；
3. 对本计划全部路径、schema、CLI、shared Git 与 carrier 假设输出
   `UNCHANGED|RENAMED|SUPERSEDED|CONFLICT` 矩阵；
4. 原位更新本计划并移除过时中间态事实；
5. 通过 `MAINLINE_ACCEPTED_BASELINE_GATE`、
   `ROOT_CHILD_TASK_IDENTITY_GATE` 与
   `NO_INTERMEDIATE_FACT_PROMOTION_GATE`。

任一项缺失即停止，不进入 Q0。

## 2. 权威拓扑

### 2.1 Decree Kernel

不可变行为内核仍由已安装 Decretum Matrix 的以下表面共同定义：

- `SKILL.md` 与唯一直接 governing references；
- intake/authority/state/semantic continuity/evidence/privacy/pending gates；
- role invariants、pack/DLC/overlay schema 与 override allowlist；
- runtime task/event、operation receipt、closeout 和 recovery 合同。

Office pack、DLC、项目绑定、共享默认、Git commit、史馆实录、长期记忆、
Obsidian 或工具原生记忆都不得覆盖最新旨意或 Decree Kernel。

### 2.2 三类 Git 权威边界

1. `D:\project` 是本机 root control repo，只管理 workspace、task shell、
   `.repo-control` per-task state/events 与 child mapping，不发布产品。
2. `decretum-matrix` child repo/common-dir 及 release worktree 管理产品代码、
   内置默认、schema、checker、package 与 release 历史。
3. 迁移后的 `.agents` shared Shiguan 是一个 local-only Git hub，分层托管
   append-only records、memory candidates/decisions、shared approved memory、
   per-tool metadata projections、manifests、registry 与 `shiguan-tree`。

各工具 native memory 保留在实际 loader 路径，并由独立 owning repo 或
separate git-dir 管理。Shared Shiguan 只登记 repo/pathspec/HEAD/write-policy/
paired receipt，不复制正文或 Git objects，不使用 submodule/subtree/nested
tracking。Obsidian 只是 preserve-only 派生视图。

Root `.repo-control` 的 per-task state/events 是工作树和任务控制面；Decretum
Matrix 产品内 `references/court-runtime/tasks.json + court_events.jsonl` 是当前
诏令运行态。两者职责、schema 与锁域必须分离，不得双写成同一个 ledger，也不得
由 Office Pack 配置替代其中任一权威。

### 2.3 全局官署配置唯一可变权威

全局默认复用 shared Shiguan Git，不创建第二 config repo。逻辑域固定为
kernel 声明并校验的 manifest 域，例如：

```text
manifests/office-identity/
  registry.v1.json
  current.v1.json
  pack-lock.v1.json
  snapshots/<content-sha256>.json
```

该域的边界：

- `current.v1.json` 是单一 effective global-default materialization，携带
  generation、parent generation、content digest、kernel compatibility hash；
- `pack-lock.v1.json` 只锁定 pack/DLC id、version、dependency、payload hash，
  不是进程锁、CAS 或第二权威；
- snapshot 是 content-addressed checkpoint/recovery evidence，不是可独立选择的
  LKG authority；
- change event 复用现有 Shiguan formal checkpoint/record 与 Git commit receipt，
  绑定同一 `operation_id`/`transaction_id`，不得新增全局 events ledger；
- records、memory、projection 与 config manifest 使用不同 schema/lifecycle，
  禁止互相冒充。

## 3. Office Identity Pack

Office Identity Pack 是可安装、可验证、可组合的官署身份包。最小内容：

```text
pack manifest
standing-official TOML
office dossier/AGENTS.md
optional presentation assets
provenance/license/author metadata
payload inventory and SHA-256 lock
kernel/schema compatibility declaration
```

Manifest 至少包含：

- `pack_id`、`version`、`pack_type`、`publisher`、`provenance`、`license`；
- supported Decretum Matrix/kernel/schema version range；
- role keys、profile/dossier paths、hashes、optional assets；
- reserved invariant claims 与 requested graph mutations；
- dependencies/conflicts/replaces/augments；
- project/global eligibility、migration/rollback contract；
- privacy class、external-origin disclosure 与 verification evidence。

Pack 安装只进入已批准 package/config domain。它不得写 runtime ledger、pending、
records、memory body、tool config、remote 或未批准项目文件。

内置身份的规范源固定为
`agents/standing-officials/<role>.toml` 与
`agents/office-dossiers/<role>/AGENTS.md`。
`agents/supercc-dossiers/<role>/AGENTS.md` 只能由规范身份、carrier 模板和
shell contract 确定性生成，不再成为独立可编辑身份权威。所有 carrier preload
必须同时绑定 canonical profile/dossier hash、carrier projection hash、
Decree Kernel digest 与 effective identity digest。

每次子官署/专家载入还必须绑定有界 semantic capsule：decree/task id、最终 plan
cursor/hash、semantic epoch/charter/invariant checkpoint（若真实存在）、resolved
pack/scope/kernel digest、允许 write/read scope、pending/privacy/remote/index
门禁、停止条件与 compact result schema。Identity Pack 只能补充身份与 presentation，
不得生成、覆盖或降级语义胶囊；carrier 只能传输同一 capsule，不能自行改写。
profile/capsule hash 漂移时必须拒绝 preload。

## 4. 类型化 DLC

### 4.1 `skin`

只允许显示名、称谓、语气、格式、图标和其他 presentation metadata。不得改变
role key、权限、直属链、write policy、evidence、semantic 或 closeout 行为。

“史馆”显示名称可由 skin 替换；但 canonical `role_key=shiguan` 及
`evidence_archive`、`memory_adjudication`、`git_stewardship` 必备能力不可移除、
降级或重定向到第二机制。

### 4.2 `augmentation`

在 kernel allowlist 内增加可选技能、报告字段、路由提示、presentation 或
非排他能力。不得删除基础禁止项、扩大安全权限、绕过门下/太子、改变 pending/
privacy/remote policy，或把工具能力变成新官署权威。

### 4.3 `replacement`

可替换一个或多个 role 的 profile/dossier 默认，或提出 Collaboration Graph
变体。替换必须重新证明所有 kernel invariants，不得删除唯一用户侧入口、三省
审议/复核语义、尚书执行统合、史馆证据与记忆治理职责，也不得让六部吸收上级
批准/最终复核。不能证明时 fail closed。

### 4.4 组合顺序

组合顺序固定为：

```text
built-in base
-> resolved global pack-lock
-> project binding
-> explicit current-decree/task selection
-> type-aware composition
-> kernel invariant validation
-> immutable effective receipt
```

同一字段冲突按 schema 的 `merge_policy` 处理；未声明、循环依赖、版本冲突、
hash drift、replacement 竞争或越权字段一律阻断，不采用 last-writer-wins。

## 5. 作用域解析

### 5.1 优先级

在最新旨意和 runtime task authority 之下，配置优先级为：

```text
project .decretum binding
> shared Shiguan Git global default
> built-in default
```

建议项目入口为真实 child Git top-level 下的：

```text
.decretum/office-packs.v1.json
```

它必须随项目 repo 版本化，不写入 root task shell 或 shared global defaults。

### 5.2 项目绑定边界

项目 binding 只能引用 registry 中已验证的 pack/DLC 和 kernel allowlist 字段，
不得包含绝对 host path、git-dir、secret、credential、runtime state、remote
action、pending/private body 或全局回写指令。未知字段、path escape、错误 repo
root、common-dir/HEAD 漂移或未锁 hash 均 fail closed。

### 5.3 跨工具一致性

Codex、Hermes、Claude Code、superCC 与 generic CLI/`other:<stable-id>` 必须调用
同一 packaged resolver library，并对同一 project root/global commit/pack lock
产生相同 canonical effective JSON 与 `semantic_effective_digest`。工具 adapter
只负责定位实际 project root、loader、transport 和可用 UI，不得实现自己的
merge/override 语义。

未绑定项目使用 shared global default；shared root 未就绪或 default 不可验证时，
回退到内置默认并明确记录 degraded reason，绝不猜测或静默写回。

## 6. 可变 Collaboration Graph 与不可变 Kernel

Collaboration Graph 可描述：

- active role/office instance；
- direct-superior/consultation/report edge；
- carrier、worktree、lease、write set、dispatch/result route；
- pack/DLC-derived presentation 与 optional capability bindings。

其 active authority 仍落在当前 Decretum runtime task/event 与已验 semantic receipt；
root `.repo-control` 只管理 task shell/worktree mapping。Shared Shiguan graph 与
Obsidian graph仅保存 checkpoint/projection，不可驱动未确认的 active dispatch。

Kernel validator 至少保持：最新旨意优先、唯一用户侧入口、权限类、语义连续性、
审批/复核职责、不越权执行、证据/记忆/史馆边界、pending/privacy、P00、closeout、
remote 与 index gates。Graph 可变不等于 kernel 可变。

## 7. Overlapping Mutation Integrity Gate

固定 write-set single-writer 不再是唯一并发形态，但每个 mutable target 的最终
commit point 仍必须有唯一 writer。允许模式：

- `exclusive`：默认；一个 writer 独占目标；
- `partitioned`：精确 path/object partitions 互不相交；
- `proposal-integrator`：多 reviewer/worker 只产 proposal，由单 integrator 写入；
- `cas`：同一结构化对象按 generation/digest compare-and-swap；
- `transactional`：跨文件/跨 repo 使用已批准 marker、backup、paired receipt、
  reread、reconcile/rollback。

硬规则：

- shared Shiguan Git commit/index/current/registry/pack-lock 始终单写串行；
- 同文件、同 registry entry、同 native memory store 或 pathspec overlap 未选择
  proposal/CAS/transactional 合同时不得并行写；
- paired shared/native commits 不宣称原子；partial transaction 在 reconcile 或
  rollback 前阻断该 store 下一次写；
- 复用 `court_file_lock`、field-level three-way CAS、atomic replace/fsync、
  operation marker/receipt 与 post-write reread；不新增 DB/lock service/MQ。

## 8. `$decretum-office-architect`

后续版本可内置引导 skill `$decretum-office-architect`，用于：

- 访谈 pack/DLC 目标与作用域；
- 生成 schema-valid 草案、provenance 清单、冲突/迁移/rollback 计划；
- 预览 effective graph、kernel invariant diff 与跨工具解析结果；
- 运行 RED/check/package lint 并输出 proposal。

它是受 Decretum Matrix 调用的工坊方法，不是新官署、第二 kernel 或自动安装器。
没有显式 apply authority、合法 baseline、门下复核和 mutation gate 时只能输出
草案，不能修改 global/project config 或安装 pack。

## 9. 项目知识选择性提升全局

可提升对象仅为明确选择且适合复用的：

- project pack/DLC 或 scope binding template；
- 已裁定 memory candidate；
- 对 append-only record 的 sanitized reference/derived lesson；
- 可复用 decree template，不是当前 task authority 或硬门禁覆盖。

流程固定为：project proposal -> provenance/privacy/dedup/conflict/scope review ->
Menxia adjudication -> explicit global-write authority -> CAS/transaction -> shared Git
commit/reread -> project/global paired receipt。历史 record 不改写，memory correction
只追加 `supersedes`，pending body 永不成为 promotion 输入。

## 10. 资料导入、候选知识图谱与晋升隔离

现有 md/txt/Obsidian 待审队列、metadata sidecar、JSON 索引/图谱与正文授权边界
必须在 P0 重新核验。后续可规划可插拔 parser/schema/extractor/resolver/retriever，
但默认图谱保持本地、零外部依赖；插件不得直接读取 pending 路径。

知识权威至少分为：

```text
official_record
approved_knowledge
candidate
rejected
historical_evidence
```

默认查询和 `shiguan-knowledge-graph.json` 只返回正式记录与已批准知识。候选项
必须进入独立 `shiguan-candidate-knowledge-graph.json` 生成视图，携带
`candidate_id`、claim hash、scope、source anchors、confidence、conflict set、
privacy/provenance 与 adjudication status；只有显式 `--include-candidates` 或
reviewer API 可见。候选不得自动成为事实、记忆或 global default。

导入流程固定为 metadata preflight -> 真实 body authority -> bounded extraction ->
provenance/license/privacy -> candidate claims -> dedup/conflict -> Menxia adjudication
-> explicit promotion -> target transaction -> reread/paired receipt。本计划不授权
真实 pending body；host 仍无不可伪造 body capability 时，该步骤保持 BLOCKED。

## 11. 实施阶段

### Q0 — Accepted baseline inventory

冻结 baseline commit/package/schema/hash；枚举 built-in profile/dossier、shared Git
topology、native tool repos、resolver consumers 与现有 mutation primitives。只读。

### Q1 — RED 与 schema

先建立 pack、DLC、scope binding、effective config、graph、mutation receipt、promotion
schema 和负例。证明第二 repo/ledger/authority、kernel override、跨工具解析漂移、
pending 输入和 uncoordinated overlap 必须失败。

### Q2 — Pure pack registry/composition

实现纯解析、hash lock、dependency/conflict、typed merge、kernel invariant validator，
只使用临时 fixture，不接真实 shared root。

### Q3 — Project/global/built-in resolver parity

实现 `.decretum` project binding 与 shared-global materialization 的只读 resolver；
Codex/Hermes/Claude/other fixture 必须输出相同 effective digest。

### Q4 — Shared Shiguan Git integration

仅在既有 Shiguan migration/Git/link gates 已通过后，把 global manifest 域接入同一
shared repo。精确 pathspec、single commit writer、CAS generation、checkpoint/
paired receipt、clean index；不创建新 repo/event ledger。

### Q5 — Office Identity Pack 与 architect UX

实现 pack install/inspect/preview/rollback 和 `$decretum-office-architect` 只提案
流程；随后接显式 apply gate。不得隐式联网下载或安装第三方 pack。

### Q6 — Mutation integrity modes

实现 exclusive/partitioned/proposal-integrator/CAS/transactional gate 与 crash/
contention/reconcile tests。默认仍为 exclusive。

### Q7 — Promotion and cross-tool lifecycle

实现 candidate/approved knowledge authority separation、默认检索隔离、
project-to-global promotion、memory adjudication、sanitized record reference、
per-tool reread 与 paired receipts。保持 native memory body/tool repo authority。

### Q8 — Package, migration and release acceptance

更新 docs/SBOM/release manifest/package allowlist/installer；从 clean commit 构建
deterministic package，执行正式本机安装/有界迁移/索引，并交接下一 release。

### 11.1 阶段 write sets

| 阶段 | 允许 write set |
| --- | --- |
| P0 | 本计划；root controller 生成的当前 task mapping state/events |
| Q1 | Kernel lock、pack/scope/effective-receipt schema、fixtures、RED checkers |
| Q2 | pure resolver/CLI、resolver fixtures；不得接真实 shared root |
| Q3 | resolver scope、`.decretum` fixtures、global generation fixtures |
| Q4 | 同一 shared Shiguan Git 的 `manifests/office-identity/**` 与既有 formal receipt 路径 |
| Q5 | `bundled-skills/decretum-office-architect/**`、proposal fixtures、同一 resolver CLI |
| Q6 | mutation transaction/concurrency/recovery fixtures；root repo-control 产品代码默认不改 |
| Q7 | index/query/knowledge-graph/memory/promotion 模块与 synthetic/authorized non-pending fixtures |
| Q8 | installer/package/release manifest/SBOM/docs/checkers 与受控安装投影 |

任一阶段共享 current/registry/index/pack-lock/manifest 的最终写入仍由唯一 integrator
串行完成；overlap 只能采用 exclusive、partitioned、proposal-integrator、CAS 或
transactional 合同。

## 12. Acceptance gates

必须全部通过：

```text
POST_MAINLINE_REBASE_GATE
MAINLINE_ACCEPTED_BASELINE_GATE
OFFICE_IDENTITY_PACK_SCHEMA_GATE
DLC_TYPED_COMPOSITION_GATE
SCOPE_RESOLUTION_PARITY_GATE
CROSS_HOST_EFFECTIVE_DIGEST_PARITY_GATE
DECRETUM_KERNEL_INVARIANT_GATE
SHIGUAN_SINGLE_CONFIG_AUTHORITY_GATE
COLLABORATION_GRAPH_RECEIPT_GATE
OVERLAPPING_MUTATION_INTEGRITY_GATE
OFFICE_ARCHITECT_BOUNDARY_GATE
KNOWLEDGE_CANDIDATE_AUTHORITY_SEPARATION_GATE
DEFAULT_QUERY_EXCLUDES_CANDIDATES_GATE
PROJECT_TO_GLOBAL_PROMOTION_GATE
PACKAGE_MIGRATION_ROLLBACK_GATE
```

最终还必须满足：无第二 repo/ledger/authority；无 submodule/subtree/nested body
tracking；pending body access=`NO`；protected bytes/hash 不变；精确 pathspec；
所有受影响 index=`0`；`.pyc=0`；remote/push/tag/PR/release 仅在后续明确发布
门禁内执行。

## 13. 本轮停止点

本轮只允许创建本计划与 governing-plan 指针。本计划状态保持
`QUEUED_POST_A02_HANDOFF`，不得把任何 Q0-Q8 实现吸收到当前 beta0.5.10 行为、
当前 A02 write set 或当前 release/package acceptance。

## 14. 2026-07-18 P0 preflight（append-only superseding note）

状态：`P0_PREFLIGHT / BASELINE_NOT_ACCEPTED`

本节只冻结 beta0.5.11 已发布基线与 beta0.5.12 Handoff 的现场证据，不改写
前文历史事实，不进入 Q0，不修改产品代码、root 仓、安装根、shared Shiguan、
Obsidian、native memory、remote 或 pending。正式显示名按最新旨意为
`Dercretum-Matrix`；`诏令矩阵` 仅作中文解释。

### 14.1 已绑定的同源证据

- accepted source：`release/beta0.5.11`，commit/tag source
  `726a89e2a5aad94c207fc133f2677670eb83903d`；beta0.5.12 worktree 从该
  commit 创建，branch=`release/beta0.5.12`，common-dir=
  `D:\project\decretum-matrix\.git`，child clean/index=`0`。
- release candidate receipt SHA-256：
  `144AED6F50F6A04F763AEEA5CEBDF112B7F28F25C92AA5E1361DAC6C3360EBF6`；
  deterministic ZIP SHA-256：
  `00C92455975E982B72FB80D82AC0EBB20F5718B30522B65D8D43590A027C5370`。
- release-manifest SHA-256：
  `6090C414B65BBA7FBAE1899DBB31BD1F167F1F6240C37BF67B2C303F5FA321B2`；
  SBOM SHA-256：
  `21E1E449DF238F0CFBDA16883F8272EE4A6745300117059C5364F12986454984`；
  skill identity manifest SHA-256：
  `F11F9793E001D245282E81514C7D3B5BEC04AC1482F154A4737E554CF33BCFDF`。
- current Decree Kernel inventory：14 files，canonical set SHA-256
  `F778ADB96C5BF0D4A590B976385E83A57EAF21AA3DD6E4E795D656E8B0B4283C`；
  standing profiles：14 files，set SHA-256
  `9FD737092276C95C966D531C761B49CB94D18D10A57884D4BCCAB8E7601BA319`；
  ordinary office dossiers：14 files，set SHA-256
  `188DA8145BB18B91FA8B3B849C0A8F9298050A7E9855AD36E142A2C8D3B4306C`；
  dispatch hierarchy manifest SHA-256：
  `2CD590CCBD6FF1A386B32BEB9AA4D354E017CAE9C76C191550EAC70D30BAE5C6`。
- install receipt SHA-256：
  `40C1F90CB1691E0F0687E8E11275CAEFA41B8EAC182EE47A91C74E8D1143F93F`；
  receipt 绑定同一 ZIP，`status=INSTALLED`、`pending_body_accessed=false`。
- npm publication receipt SHA-256：
  `306BFA70C56CEAE3CD2F6258253EDD4F690FE0A4ACA7FEA2D13726AD559A5432`；
  `@rowlandl/decretum-matrix@0.5.11-beta.0`、`beta` dist-tag、public、online
  install 均为 `PASS`，内嵌 ZIP hash 与 release 相同。
- final Handoff record SHA-256：
  `2F05B11CF1D8AE844D9E8E548B408B36BBE09E4371EA328E696A9A7FA3EAFFC9`；
  本会话已回报 `HANDOFF_ACCEPTED`。
- root repo-control state SHA-256：
  `AE1068A71B890CEE60D0B217BB79A02654C76E2F73A4295D1AAC0F421C1A0E99`；
  create event SHA-256：
  `2E0DED0B728F08D2F42E14B8BBC1D03AF0A0DCCDD02D3D9169A098D858666CC6`；
  map-branch event SHA-256：
  `5118FE533CFB9F1CBF20FABFABC45D160898A0DC6492B64499B1A83582C1CA7E`；
  mapping=`ref_only_no_checkout`，root technical ref=
  `codex/decretum-matrix/release/beta0.5.12`，root/child index 均为 `0`。

### 14.2 最终基线假设矩阵

| 假设域 | 裁定 | 2026-07-18 现场事实 |
|---|---|---|
| 中间审查前像 `6f97c91` | `SUPERSEDED` | accepted source 已为 `726a89e2a5aad94c207fc133f2677670eb83903d`。 |
| next-release carrier | `SUPERSEDED` | 最新旨意要求 D:\project 本地分支会话；不是新的 Codex worktree task。受管 child worktree 与 ref-only root mapping 保留为 Git carrier。 |
| repository/common-dir | `RENAMED` | 当前 child repo/common-dir 已是 `decretum-matrix`；旧 `court-capability-router` 仅保留历史、ZIP internal root、shared Shiguan namespace 与 deprecated locator 语境。 |
| display identity | `RENAMED` | 当前正式显示名逐字为 `Dercretum-Matrix`；machine/package/skill name 仍为 `decretum-matrix`。 |
| installed skill authority | `RENAMED` | canonical path 为 `C:\Users\32893\.agents\skills\decretum-matrix\SKILL.md`；309 lines / 67148 bytes / SHA-256 `24D19C0A40CA3887ECF91E78C868FB264C748FF88762057CF88D6A7AF60F94F1`。 |
| capability index locator | `CONFLICT` | strict catalog 通过，但 active index 仍解析旧 `court-capability-router/SKILL.md`，`dispatchable=0`；本 P0 只记录，不刷新安装根。 |
| runtime task authority | `CONFLICT` | shared `tasks.json` 的 A02 旧条目缺 semantic epoch/capsule/receipt，按 P00 只读；当前项目合同以 per-task `.repo-control` state/events 管理 carrier，不得把旧 shared ledger 升格为可写权威。 |
| shared Shiguan topology | `CONFLICT` | LocalAppData `court-shiguan\court-capability-router` 仍是普通目录而非指向 `.agents` 的 junction；canonical `.agents` skill root 也没有 shared-data Git。 |
| managed data repo | `CONFLICT` | 未找到 shared Shiguan owning repo 或 separate git-dir，故没有可证明为 `0` 的 managed-data index。不得为过门禁擅自初始化。 |
| protected four anchors | `CONFLICT` | 既有 snapshot 基线仍可定位，但 canonical `.agents\skills\decretum-matrix\references` 下四个 anchor 当前不存在；LocalAppData 同名文件是已演进的 shared indexes，不能冒充原路径/长度/hash 不变。 |
| pending/private body | `UNCHANGED` | `pending_body_access=NO`；本 P0 未枚举、读取、哈希、移动、删除或 mark-seen pending 正文。 |
| remote/main/root mutation | `UNCHANGED` | 本 P0 不进入 Git `main`，不执行 PR/force/push/tag/release，不提交或发布 root。 |

### 14.3 P0 门禁裁定与恢复游标

```text
ROOT_CHILD_TASK_IDENTITY_GATE=PASS_WITH_EXPLICIT_BRANCH_SESSION_SUPERSESSION
NO_INTERMEDIATE_FACT_PROMOTION_GATE=PASS
MAINLINE_ACCEPTED_BASELINE_GATE=BASELINE_NOT_ACCEPTED
POST_MAINLINE_REBASE_GATE=BLOCKED
OFFICE_PACK_Q0=NOT_STARTED
pending_body_access=NO
```

首个阻断为 `SHIGUAN_LATEST_SYSTEM_GATE` 的 one-root/junction/shared-Git/protected-
anchor 合同未满足；这是原 A02 gate，不是 Office Pack Q0 的实现内容。恢复游标固定为：

```text
A02_SHIGUAN_LATEST_SYSTEM_REPAIR
-> MAINLINE_ACCEPTED_BASELINE_GATE_RETRY
-> POST_MAINLINE_REBASE/P0
-> OFFICE_PACK_Q0
```

修复必须回到原 A02 governing plan，先形成最小 RED/GREEN/SPEC/QUALITY 与独立门下
复核；不得在本计划内临时发明第二 repo/ledger/authority，不得触碰 pending/private
body，也不得重做 beta0.5.11 的 intake、hierarchy、installer、candidate、install、
GitHub 或 npm 发布工作。
