# Changelog

## beta1.1.4 - 2026-09-20

### Fixed

- 当前 Codex 宿主按实时 capability 传递精确官署角色和用户显式 model/effort；未指定字段保持继承或宿主默认，followup 不重复发送 spawn override。
- 横向消息在用户未禁止时默认直投 canonical target；只有宿主不可达或无法形成 delivery/read-ack 证据时才降级为太子中转。
- 官署启动、上级 ACK 与正式派遣要求已提交诏令和同一预载材料链，避免中途中断后把半完成状态当成可继续执行。
- Windows CRLF checkout 不再挤占预载预算：四份必读 UTF-8 文本按逻辑换行计量，无效文本 fail-closed；20 KiB 与 768-byte 门槛不变。

### Changed

- NIUbash 保持可选兼容，不成为 Windows、PowerShell 或现有工作流的安装前提。
- 最终安装收据绑定同一候选 ZIP、提交、artifact、installation 和 transaction；GitHub 发布、本机资产与安装态分别由远端回读和安装回执证明。
- 为容纳本版版本化说明与发布元数据，便携源码 byte 上限从 9,590,000 有界调整为 9,593,000；文件数和所有模块行限不变。

## beta1.1.3 - 2026-09-12

### Fixed

- 当前 Codex 宿主适配改为 capability-driven：`agent_type` 只从已准入官署派生并由 child session metadata/receipt 复核；未选择 model/effort 时继续继承，create/revise 的 `current_user_explicit` model-only、effort-only 或 pair 才能经可见宿主字段下沉。字段可见性只描述 schema，未选字段仍不进入 invocation。正式 receipt 同时绑定 admission 原始授权和 parent/child `turn_context`；effort-only 证明 model 继承，model-only 则省略 effort 并记录当前宿主实际默认值，不误称父级继承或用户选择。followup 只复用已证明选择，不重复发送 spawn override；空白模型名不构成显式选择。
- `court-normal-startup.md` 进入 manifest、admission、fastpath、native message/trace、child acceptance、正式 ACK、state/event/receipt 与 20 KiB 预算同一链；普通三省六部另保留 768-byte 动态余量，旧 v1 ACK 缺新证据时保持可重试 pending。
- NIUbash 仅增加可选的窄 literal-`cat` trace 兼容与 business-before-preload 检测；PowerShell 主路径保留，包装器只信任当前 fallback 路径，不安装或强依赖 NIUbash。
- 横向 message/evidence/state/heartbeat 在无最新用户明确禁令时默认投递真实 canonical target；仅宿主不可达或无法留存 delivery/read-ack 证据链时才降级 root/太子 transport relay，且不改变 dispatch、wake、reassign、approval 或直属上级权限。
- 候选安装在外部投影验收后生成最终 `INSTALLED` receipt：复用候选 receipt 校验的同一 ZIP 摘要，并把提交、artifact、build、installation 与 transaction 来源提升为 release gate 可直接消费的顶层字段；中间 `PENDING_VALIDATION` receipt 继续保留，不再被误作最终验收证据。
- 本版维护：官署启动回执提供后续上级确认请求，复用本次 manifest、模型路由与宿主引用；公开 JSON 确认入口处理可选默认值并结构化拒绝错误类型。身份路径、真实子署证据和终态保护保持严格。
- 本版维护：标准案件只有已提交的 decree-open 才能进入正式派遣；复用案件绑定校验，保留中断后的原样创建重放及暂停／取消。
- 普通任务创建、状态转换、心跳、计划评审和官署生命周期共用任务／事件事务；异常与进程中断可回滚重试，冲突时保留现场。新增路径不计算文件摘要。
- 多实例测试迁移到已有 case_ref 契约，恢复 29 项正反例；缺失／畸形引用得到明确拒绝。
- 召回结果携带实际排序分数；同名发布检查重跑使用独立日志目录，保留先前证据。
- 启动复用已准入预算；过期预留不再占写集；预载确认允许附加说明。取消默认 8 次／600 秒截止，保留显式执行预算和资源约束。

### Changed

- 当前宿主能力不再由历史 Codex 0.144.1 或 `hide_spawn_agent_metadata` 配置单独推定；配置检查明确标注 config-only，native request/capture 使用当前工具 schema capability。内部 `task_name` 保持路由身份，禁止以通用 `set_thread_title` 修补官署身份。
- 便携源码实测 9,589,322 bytes / 509 files；为容纳宿主调用、turn-context/receipt、启动顺序、安装 receipt 交接及危险语法正反例，将 byte 上限有界调整为 9,590,000，并仅将 intake source/check 行限调整为 620/730。文件数及其余模块行限不变。
- 复用预载预算与派遣结构规则，保持授权、可信预载和独立测试边界。
- 公共 API 按需加载后端；court open 帮助以现有启动说明为唯一正文，保留兼容导出与标题。
- 有限事件查询从尾部按需读取，完整历史查询逐行解析；不新增索引或缓存服务。
- 接入已有 CONTEXT、文档／交接／决策索引与工程配置。源码预算从 9,300,000 调整为 9,340,000 字节，容纳恢复逻辑及真实 CLI 发现的接口断点回归；文件数和模块行数上限不变。
- 本条记录本地开发候选；源码验证、候选包、活动安装、宿主验收与外部发布分别记录。

## beta1.1.2 - 2026-09-08

### Added

- 新增已存在全局 npm 包的显式替换安装路径；默认仍 fail-closed 拒绝覆盖，只有调用方明确选择替换时才移动旧包并安装候选包。
- 全局 npm 替换备份清单使用相对 npm prefix / 备份根的路径字段，根 shim 只做快照记录，绝对路径仅保留为当次宿主证据。

### Fixed

- 安装投影清理会依据当前源码清单处理 repository-only/source-only 的精确残留文件，并继续保留未知用户文件和目录型私有数据。

### Changed

- 将本地版本标记统一至 `beta1.1.2`，同步 VERSION、SKILL 元数据、README 当前说明、发布记录、SBOM、插件与 GitHub release metadata。
- 保留 beta1.1.1 及更早历史条目；根 `package.json` 继续保持 version-neutral 的 `0.0.0-private`。
- beta1.1.2 的候选构建、安装、tag、GitHub Release、npm 发布和活动安装分别由独立回执或远端回读证明；本条目不替代这些证据。

### Docs

- 说明文档改为说明书式：README 增加「安装 / 快速开始 / 功能大模块 / 接口：CLI 与 MCP / 版本 / 许可」六个编号章节，并给出五根投影、升级回滚与安装后验证口径。
- 新增离线 Wiki 页面 `docs/wiki/Modules.md`（七个功能大模块用途）与 `docs/wiki/CLI-and-MCP.md`（CLI 命令面与 13 个 MCP 只读工具矩阵），并同步 `Home.md`、`_Sidebar.md`、`docs/wiki/README.md` 与 `check-sync.ps1` 的页面清单。
- 重写 `docs/wiki/Installation.md` 为三步快速安装加完整口径；扩充 `Usage.md` 与 `Troubleshooting.md`（新增 CLI 入口、`source_checkout_required`、MCP 可见性与参数错误章节）；修复 `Release-Notes.md` 的重复 H1。
- 文档改版不改变运行时、命令面、MCP 工具集、状态机或发布门禁；相关能力声明仍以对应回执为准。

## beta1.0.9 - 2026-09-02

### Changed

- 语义纠正（不过拟合）：明确 **太子受旨定性**（Taizi intake：意图初判、历史线索初判、
  建立结果章程）在三省会审**之前**由太子完成；问题拆解（decomposition）归属**中书省**
  拟旨阶段，太子不代中书拆解；`court semantic checkpoint/verify` 的
  VERIFIED/DISPATCHABLE 仅为三省会审的 P00 **语义门禁**，不构成中书/门下/尚书官署被
  派遣或履职的证据；需要三省官署回奏时与六部同规则（`agent-admit` + host-native
  spawn/reuse/wake，或显式 `serial_inline`），否则如实记录 `runtime_degraded`/`PARTIAL`。
 仅文档/帮助层落地，未新增状态机、命令或门禁（SKILL.md、`court open` 帮助、
  `court_runtime` docstring）。

## beta1.0.8 - 2026-08-31

### Added

- Added the domain ledger API (`scripts/domain_ledger_api.py`): 领域化史馆/记忆与能力索引账册
  Create/Read/Update，Update 追加不可变 revision，每次成功操作独立 Git commit。
- MCP 与统一 CLI / 主动 CLI 共用 public/domain API，MCP 返回 Agent 友好 JSON envelope；
  最终 12 工具矩阵（check_court_mcp_server 58 探针全绿），现代 `2026-07-28` 与 legacy
  `2025-11-25` 双协议兼容探针。
- 统一编号只调用统一生成器/权威 receipt：会话开始分配、结诏复用（check_court_code_session_numbering）。
- 谱系分类版本化并带最小验证集与 evidence margin 防过拟合（content_lineage_parts 9 项合同字段
  含 positive_evidence/negative_evidence/candidates 与 conflict 状态）。
- IKU 候选/修复（`scripts/iku_candidates.py`）：只读发现先行、`--dry-run` 零字节变化、幂等与回滚。
- 结诏自动冲突/过期检查（`scripts/closeout_conflict_scan.py`）：确定性冲突脚本化降级或替代并告知用户。
- 史馆 leaves/full-record 指针与完整上下文文件路径索引（check_shiguan_full_record_index），
  保留原版实录结构与十四行 compact memorial。
- GBrain 记忆治理：召回 leaves/full-record 与 full-record 索引。
- Codex host proof（`agent_runtime_probe.py` host_proof 六字段，null-safe）与模型路由绑定
  （`route_office_model_with_host_proof`：APPLIED/INHERIT/FAILED+degraded 不伪报）以及
  fresh-session worker 回读证明（`verify_worker_session_override`）。

### Fixed

- `check_read_only_contract` 修复为零文件系统副作用（E2：惰性初始化，不创建 home/AppData 目录）。
- `serve_shiguan_tree` 目录穿越回归（E4：`id="..\..\evil"` 拒绝；36 项 static + live 全绿）。
- 版本锚点统一并重绑定：release-manifest / SBOM / VERSION / CHANGELOG / README / wiki 同步
  beta1.0.8；source-final 与 install-host-closeout 收据绑定当前 HEAD。

# Changelog

## beta1.0.7 - 2026-08-26

### Added

- Added the read-only stdio MCP transport with `2026-07-28` as the primary
  protocol and `2025-11-25` as the compatibility path.
- Derived the MCP allowlist, schemas, command identity, and read-only/dry-run
  flags from the same public registry used by the CLI.
- Added `scripts/migrate_legacy_skill_locator.py` as a dedicated plan/apply/
  rollback entrypoint for migrating old physical `court-capability-router`
  skill locators to the canonical `decretum-matrix` root while preserving a
  compatibility alias and rollback receipt.

### Fixed

- Made active-copy installation render and verify the 14 native Codex role
  files after syncing profiles, dossiers, and `SKILL.md`; stale preload hashes
  now fail the post-install gate.
- Made repository and npm checks work from a network git mirror with an exact
  per-command `safe.directory`, without changing global Git configuration.
- Bound the blank-agent loading procedure directly in `SKILL.md`, covering the
  load entry, hard gates, authority/behavior split, CLI/Agent/reference triad,
  dispatch hierarchy, shared Shiguan index, and closeout.
- Clarified the canonical identity boundary: current skill, package, install
  root, archive root, and invocation are `decretum-matrix` /
  `$decretum-matrix`; `court-capability-router` remains legacy-only as a
  compatibility locator or protected Shiguan namespace.
- Guarded identity checks against older release-note wording that could make
  `court-capability-router/` look like the current ZIP internal root.
- Rebound active Hermes/superCC skill paths and generated office capability
  records to canonical `decretum-matrix`; the old name remains legacy-only for
  explicit locator migration and Shiguan namespace compatibility.
- Withdrew the incompatible Codex lifecycle and Git-hook implementation from
  the shipped beta1.0.7 surface; the optional plugin metadata carries no hooks.

## beta1.0.6 - 2026-08-01

### Added

- Bound native runtime identity, entrypoint selection, and host lifecycle evidence to the accepted request path.
- Added real Shangshu-to-ministry dispatch/reuse coverage and lineage taxonomy review gates for confidence, ties, negation, and unknown inputs.
- Added a source-only post-install hash checker for the five governed roots plus explicitly authorized Qoder projection.

### Fixed

- Kept release/install checkers outside the installed runtime surface and blocked static or dynamic checker coupling from startup code.
- Made active-copy synchronization preflight every target before writes and recognize only declared canonical junction aliases.

## beta1.0.5 - 2026-07-23

### Added

- Reissued the npm carrier as `1.0.5-beta.0` on the `beta` dist-tag.
- Kept first-install `zellij` and `squad` bootstrap plus the open-source acknowledgements on the
  install receipt.
- Refreshed macOS and Linux install-path and dependency selection in the new carrier while keeping the installed
  surface free of post-install hash checkers.

## beta1.0.4-hotfix-v1 - 2026-07-22

### Fixed

- Restored `references/benchmarks/cft0808-edict.yaml` to the release ZIP, npm
  carrier, and all five installation projections as a frozen reference.
- The installer makes that reference read-only after each sync and temporarily
  unfreezes it only to apply a later release replacement.
- The frozen reference remains outside runtime loading and does not restore any
  post-install hash-validation behavior.
- Replaced stale hierarchy-receipt hash references with the existing manifest
  path provenance, restoring the fast startup and admission paths without
  reintroducing runtime hash checks.
- Retired nine source-only Shiguan service and checker compatibility adapters
  from the public CLI surface.
- Updated superCC profile/dossier regression evidence to use declared paths and
  identity bindings instead of obsolete profile or dossier digest fields.
- Kept archive closeout verification on its objective receipt id, path, lineage,
  and closeout identity; it no longer expects retired receipt or archive digests.
- Replaced Windows-only installation wording with Windows/macOS/Linux path
  matrices and platform-specific Hermes/tool roots.
- First npm install now installs or reuses the superCC `zellij` and `squad`
  dependencies, records upstream acknowledgements and links, and keeps that
  pre-activation dependency verification out of the installed startup surface.

### Release identity

- Product/tag/artifact version: `beta1.0.4-hotfix-v1`.
- npm version: `1.0.4-beta.0.hotfix.1` on the `beta` dist-tag.
- `beta1.0.4` and `1.0.4-beta.0` remain immutable predecessor evidence.

## beta1.0.4 - 2026-07-22

### Fixed

- Restored short no-write closeout as a real `结诏` path: even compact probes now
  carry `史馆实录` and `记忆裁定`, with a lightweight archive checkpoint when
  the host can write.
- Restored the opening choice surface to authority plus explanation, with a
  separate `serial/parallel` selector that can be driven from keyboard or mouse
  in the supported client surfaces.
- Kept the installed runtime surface narrow and removed the old active-copy
  hash-check gate from release manifests and install-facing guidance.
- Accepted an already-migrated shared Shiguan topology when legacy locators are
  junctions to the canonical root, so Hermes closeout can generate `court_code`
  and `ancient_lineage` instead of reporting missing cutover evidence.
- Blank-host npm installation now accepts only structural ZIP checks at runtime;
  any future temporary bootstrap validator must be removed before activation, and
  the installed skill keeps no release manifest or release-validation helper.

### Release identity

- Product/tag/artifact version: `beta1.0.4`.
- npm version: `1.0.4-beta.0` on the `beta` dist-tag.
- Published as the `beta1.0.4` prerelease with its matching branch, tag, assets,
  and npm package on the `beta` dist-tag.

## beta1.0.3 - 2026-07-21

### Fixed

- Kept the established progressive court flow while removing blanket startup
  probes for Git, Shiguan services, pending imports, YOLO, capability refresh,
  portable bootstrap, install, and release tooling.
- Reframed `court open --fast` as optional pre-dispatch preparation. It no
  longer selects every ministry by default or reports packet/admission checks as
  physical child dispatch.
- Kept the Three Departments flow intact and moved Six Ministry selection to
  Shangshu's result-driven, bounded subset after the Taizi reply.

### Release identity

- Product/tag/artifact version: `beta1.0.3`.
- npm version: `1.0.3-beta.0` on the `beta` dist-tag.
- This branch is a local candidate; publication requires separate authorization.

## beta1.0.2 - 2026-07-21

### Changed

- Reframed Decretum Matrix as an edict-centered multi-agent collaboration
  skill whose default formal path is Three Departments and Six Ministries, with
  scene-appropriate routing for casual chat, light tasks, formal tasks,
  corrections, continuations, and explicit closeout.
- Preserved beta0.5.9 capabilities and explicit later additions while
  separating ordinary skill runtime from project-level release, install, legal,
  manifest, and package gates.
- Restored Shiguan base memory as the normal record/query layer, kept GBrain as
  a consolidation/organization layer, and kept Shiguan Git Federation as an
  explicit management function.
- Tightened authority/behavior wording so `approval|autonomous|super` remain
  authorization boundaries and `serial|parallel` remain execution modes.
- Repaired external-CWD CLI behavior so user relative paths are resolved from
  the caller directory while project check/release commands still run from the
  code root.

### Release identity

- Product/tag/artifact version: `beta1.0.2`.
- npm version: `1.0.2-beta.0` on the `beta` dist-tag.
- Remote publication status is proven only by later remote rereads.

## beta1.0.1 - 2026-07-20

### Fixed

- Made `approval|autonomous|super` authority independent from
  `serial|parallel` behavior across native and superCC execution receipts.
- Split native and superCC startup, imports, task stores, dossiers, transport,
  admission, and lifecycle; only neutral office configuration hashes are shared.
- Repaired the semantic-context producer/consumer boundary so an invalid
  authority revision fails closed with zero dispatch and no manual bypass.
- Resolved and cached a skill/MCP/plugin/CLI/script capability snapshot before
  Three Departments deliberation without spawning libu-hr for a read.
- Kept warm court-open p50 inside the accepted 10% regression budget while
  preserving one-process startup and the 20 KiB preload ceiling.

### Release identity

- Product/tag/artifact version: `beta1.0.1`.
- npm version: `1.0.1-beta.0` on the `beta` dist-tag.

## beta1.0.0-hotfix-v2 - 2026-07-20

### Fixed

- Forced the packaged Python launcher to reconfigure stdout/stderr as UTF-8,
  preventing Windows GBK `npm postinstall` from failing while printing a
  structured receipt containing replacement characters.
- Added a behavioral GBK stream regression to the unified CLI gate so the
  launcher must encode `U+FFFD` as UTF-8 rather than relying on host code pages.

### Release boundary

- Product/tag/artifact version: `beta1.0.0-hotfix-v2`.
- npm version: `1.0.0-beta.0.hotfix.2` on the existing `beta` dist-tag.
- Published `hotfix-v1` remains immutable evidence and is superseded rather
  than overwritten.

## beta1.0.0-hotfix-v1 - 2026-07-20

### Fixed

- Decoupled ordinary super parallelism from the explicit superCC runtime at the
  carrier layer. Shared standing profiles remain single-source, while ordinary
  Codex roles resolve only `agents/office-dossiers` and explicit visible carriers
  resolve only `agents/supercc-dossiers`.
- Removed superCC validation and topology fields from the ordinary runtime probe,
  so the ordinary path no longer imports, probes, or reports the visible runtime.
- Made `decretum-matrix shiguan archive-checkpoint` return a UTF-8 structured
  receipt with archive/receipt hashes and exact closeout identity lines.
- Rejected model-allocated decree identifiers and lineages: a fourteen-line
  closeout now requires the current CLI archive receipt, otherwise a non-closeout
  response family must be used.
- Re-compacted the root skill without relaxing the 20 KiB preload ceiling;
  maximum role preload is 20,173 bytes and measured cold/warm p50 improvements
  remain 88.60%/99.33%.

### Release boundary

- Product/tag/artifact version: `beta1.0.0-hotfix-v1`.
- npm version: `1.0.0-beta.0.hotfix.1`, preserving the existing
  `1.0.0-beta.0` package as immutable registry evidence.
- Publication, tag, assets, installation, and Latest status are asserted only by
  the final hotfix receipts.

## beta1.0.0 - 2026-07-19

### Added

- Added a local-only shared Shiguan Git management hub with an explicit tracking
  allowlist, independent Codex/Claude Code/Hermes native memory repositories,
  reciprocal managed links, stable registry entries, and paired commit receipts.
- Added authorized blank-host bootstrap for canonical Codex, Claude Code, and
  Hermes memory roots while keeping probe mode read-only.
- Added concise GitHub release metadata as a mandatory source gate and restored
  the packaged brand icon to the repository README.

### Changed

- Aligned VERSION, SBOM, release manifest inputs, package artifacts, npm
  candidate identity, and release-facing documentation to beta1.0.0.
- Added a governance-neutral framework contract, shared Shiguan GBrain recall,
  and a default official 三省六部 adapter backed by the existing hierarchy.
- Added one non-default direct-review reference implementation to validate
  replacement without adding runtime, evidence, or memory authorities.
- Added a four-dimension request-understanding gate with a 95 sufficiency
  threshold, one-question clarification, bounded options, and clear-request
  direct execution.
- Activated the single final-stage branch from the accepted beta0.5.13 baseline
  and jumped directly to beta1.0.0 without creating an intermediate beta0.5.x
  release branch or another worktree.
- Extended GBrain recall with path-private Git provenance while preserving
  advisory authority, current-decree precedence, and cross-governance ordering.

### Fixed

- Closed the deferred shared-Shiguan managed-Git and native-memory reciprocal
  link gap without reading pending bodies or introducing a remote/service/DB.
- Fixed non-ASCII Shiguan filenames being misclassified by Git quoted-path output.
- Fixed empty native-memory glob pathspecs and same-transaction recovery for an
  initialized repository that had not yet created its first commit.

### Release boundary

- The original beta1.0.0 tag, GitHub assets, and npm `1.0.0-beta.0` package are
  published baseline evidence. This coverage revision does not claim to have
  replaced them until a new candidate/install/publication receipt closes.
- All 43 candidate source steps now have passing evidence, including concise
  release metadata, Shiguan Git federation, governance, privacy, and measured
  CLI performance. Live install and publication remain separately gated.
- GitHub release bodies were shortened and beta1.0.0 was marked Latest without
  changing the existing tag or five release assets.

## beta0.5.13 - 2026-07-19

### Added

- Added the `decretum-matrix` npm executable and lazy unified CLI registry while
  retaining verified compatibility adapters for existing entrypoints.
- Added single-process `court open --fast`, structured result attribution, and
  deterministic cold/warm performance gates.
- Added managed-file install backups plus explicit rollback for direct atomic
  overwrite updates.
- Added a bounded npm `postinstall` that verifies the embedded release ZIP,
  installs the canonical `.agents` runtime, creates or atomically migrates the
  physical Shiguan root, and emits durable rollback receipts.

### Changed

- Compacted root skill and role preloads to stay below 20 KiB while resolving
  detailed behavior through direct governing references.
- Expanded release gates to cover unified CLI, fast-open, result semantics, and
  measured performance; source audit steps now isolate temporary Git indexes.
- Aligned VERSION, SBOM, package, payload, artifact, and npm candidate identity
  to beta0.5.13.

### Fixed

- Removed the V2/legacy agent-type protocol conflict at the CLI boundary.
- Kept protected Shiguan record, index, evidence, and data paths outside install
  reads and writes while retaining managed-file backup and rollback coverage.
- Added the current `release-manifest.json` to every managed skill projection so
  installed VERSION, identity, payload index, and release identity converge.
- Made successful legacy skill-directory migrations explicitly rollbackable,
  including the zero-file-delta case, and reject canonical Shiguan links or
  dual physical roots before mutation.
- Bound autosync sidecars to the generated pending filename and timezone-aware
  import timestamp without reading pending bodies.
- Restored discovery of public legacy court commands in unified top-level help.
- Corrected remaining current-product naming, canonical package-root, bytecode,
  fixture-index, and release-builder contract drift.

External push, tag, GitHub Release, npm publication, assets, and final host
installation remain receipt-gated and are not asserted by this source entry.

## beta0.5.12 - 2026-07-18

### Added

- Added versioned offline Wiki pages for installation, usage, governance,
  architecture, troubleshooting, and release notes, plus a read-only
  online/offline consistency checker.

### Changed

- Aligned VERSION, SBOM, package, manifest, artifact, and npm candidate identity
  to beta0.5.12.
- Reduced README to the product, shortest install command, shortest invocation,
  and documentation entry points.
- Converged shared Shiguan and Obsidian paths on the canonical
  `.agents/court-shiguan/decretum-matrix/references` root.

### Fixed

- Restored protected Shiguan anchors and legacy semantic bootstrap recovery.
- Fixed host-memory/child-trace gates and package synthetic-secret fixtures.
- Fixed stale host skill locators and repair holds that blocked native
  `$decretum-matrix` discovery after the install-directory migration.

External tag, GitHub Release, npm publication, assets, and online Wiki remain
receipt-gated and are not asserted by this source entry.

## beta0.5.11 — 2026-07-17

### Added
- RB1 added atomic admission around the shared hierarchy/profile gate, rejects zero-mutation denials without state writes, and binds v2 lease/preload evidence to an append-only admission event anchor.
- RB2 added the normal `superCC` shared delivery preflight, identity ACK, `preload_pending -> delivery success`, `ENTER_DISPATCH` P00 context, and an atomic delivery/state chain with correction-gap coverage.
- Added formal closeout identifier validation: `SCGSDYJM-20260606-1Z-DAAA` is the positive decree-code example, and lineage is exactly `史馆总纪·朝制志·官署门·三省六部纲·回复格式目·结诏标识条·内容谱系诏`; `CCR`, `Phase`, `RB`, task ids, and workflow paths are rejected as lineage.
- Added the bounded source split for dispatch contract, delivery, admission contract, and autosync projection modules, plus a live source-state focused checker.

### Changed
- The current display identity is exactly `Decretum Matrix（诏令矩阵）`; `诏令矩阵` is explanatory only, while machine/package/invocation remain `decretum-matrix` / `$decretum-matrix`.
- Shiguan Web/autosync uses atomic state transitions, a filesystem preserve-only primary channel, optional non-blocking REST, and asynchronous refresh requests for an existing daemon.
- Expanded the release policy to 42 manifest steps: 37 source, 4 installation, and 1 conditional runtime step; candidate pre-install selects 36 source steps and normal post-install selects 5.
- Historical compatibility note: the canonical physical install authority is
  `skills/decretum-matrix`; current release builders use `decretum-matrix/` as
  the archive root, while legacy install locators must resolve to the same
  authority.
- The beta0.5.11 release source tree measures 273 portable files / 6,138,661 bytes against the unchanged ceiling of 275 files / 6,200,000 bytes.

### Fixed
- Aligned the intervention baseline with production caller/direct-superior edges, bounded child ownership/write scopes, serial no-mutation behavior, canonical preloads, and the 16-slot tree cap.
- Closed admission-to-start and `superCC` delivery TOCTOU gaps before any persistent state transition.
- Repaired Shiguan WebUI autosync controls, busy-state handling, local-only errors, daemon freshness, and preserve-only refresh transitions.

### npm backfill and release boundaries
- The public GitHub Packages `beta` dist-tag currently resolves to the immutable `0.5.10-beta.0` release-assets carrier. It has no dependencies or lifecycle scripts and does not modify skill directories.
- `0.5.11-beta.0` npm publication is `NOT_RUN`; after release, the dist-tag and online install must be verified before that state changes. Any required authentication is limited to `read:packages` through process-scoped `NODE_AUTH_TOKEN` and a temporary npmrc, with no token persistence.
- `pending_body_access=NO`; no pending body was opened, hashed, moved, deleted, or marked seen.
- `beta0.5.10` remains immutable historical release/lineage evidence.
- Candidate, installation, tag, push, GitHub Release, npm publication, and asset success require their own later receipts and are not asserted here.

## beta0.5.10 — 2026-07-16

### Added

- Added the canonical Decretum Matrix（诏令矩阵） identity, `decretum-matrix`
  skill/package name, `$decretum-matrix` invocation, and role-prefixed ordinary
  office dossier/preload contracts.
- Added body-bound semantic continuity, P00 bounded dispatch/resume packets,
  idempotent decree/closeout operation receipts, office-carrier lifecycle
  checks, capability recruitment, and current-tool install projection tests.
- Added `AGPL-3.0-only` community licensing, separate commercial-license
  notice, DCO + CLA governance, trademark policy, authorship metadata, and
  explicit upstream MIT provenance.

### Changed

- Renamed the local repository, managed worktree namespace, release artifacts,
  documentation, SBOM, and release manifest to `decretum-matrix`; the protected
  `court-capability-router` install/archive/Shiguan locators remain explicit
  compatibility surfaces.
- Updated the release artifact contract to
  `decretum-matrix-beta0.5.10.zip`; `court-capability-router/` is retained only
  as a protected legacy install/archive/Shiguan locator namespace, not as the
  current package archive root.
- Decoupled the Decretum Matrix kernel from any named Superpowers methodology;
  optional workflow skills remain ordinary bounded tool invocations.

### Fixed

- Closed semantic-binding fixture drift, ministry authority overreach,
  preload-source reachability, Windows 8.3 temporary-root false positives,
  stage validation without Git metadata, portable bytecode ordering, and
  deterministic package privacy regressions.

### Release and compatibility notes

- `beta0.5.9` remains an immutable historical Apache-2.0 release. Its grants are
  not withdrawn; the AGPL cutover applies to the new `beta0.5.10` community
  release.
- The `cft0808/edict` MIT notice and fixed commit provenance remain independent
  and complete. Zero whole-file blob matches are not represented as zero
  influence or zero borrowing.
- This entry records the release payload and local acceptance. Remote
  publication is proven only by its external tag, release and asset receipts;
  repository text alone never claims those actions succeeded.
- Tagless candidates now use a reusable, no-clobber commit directory with an
  external candidate receipt. Final release attestation remains annotated-tag-only.
- Final promotion requires the exact accepted candidate SHA-256 and rejects a
  mismatch before creating the final version directory.

## beta0.5.9 — 2026-07-12

### Added

- Imported `COURT-DYNMSG-BUDGET-V1-20260712`: dispatch-message budget floor 6000, allocation quantum 1000, and ceiling 12000.
- Added Apache-2.0 project licensing, `NOTICE`, contributor/provenance rules, security and privacy policies, an SPDX 2.3 SBOM, and the complete upstream MIT notice for `cft0808/edict` commit `14a207557719c046af0f993a7bff1cc5a5015b33`.
- Added a strict v2 payload manifest, legal gate, capability-index gate, package regression gate, and immutable artifact-builder gate.
- Added exclusive final release directories containing the ZIP, SHA256 sidecar, source/tag/tree attestation, release notes, and SBOM.

### Changed

- Resolved capability-index checks through the shared Shiguan root instead of a stale skill-local catalog.
- Made ZIP output byte-reproducible with stored entries, a fixed timestamp and mode, UTF-8 path ordering, stable source reads, and no-clobber publication.
- Made Shiguan Web services loopback-only by default. LAN binding now requires explicit `--host 0.0.0.0`; non-loopback peers require HTTPS, reject redirects and embedded credentials, and never forward bearer tokens to another origin.
- Classified the strict superCC runtime truth check as conditional runtime evidence. Ordinary `super` release checks report `NOT_APPLICABLE` with reason `runtime_not_selected` when runtime checks are not selected.

### Fixed

- Rejected malformed release manifests without uncaught exceptions and detected missing, extra, reordered, or hash-drifted package payloads.
- Closed quoted-JSON secret-redaction gaps and documented that `.shiguan-key` obfuscation is not encryption.
- Hardened source copying and package publication against symlink/reparse traversal, source replacement races, late competing outputs, and accidental overwrite.

### Release and compatibility notes

- `beta0.5.8`, its tag, and every historical artifact remain immutable; this release neither overwrites nor deletes them.
- The package embeds no Git remote, GitHub account, access token, credential helper state, or authenticated publication configuration.
- Physical host child-thread reclamation remains unverified and is not claimed fixed in this release.
- Apache-2.0 applies only to material the contributors have the right to license. Publication must stop if ownership, copied material, trademarks, privacy consent, or third-party provenance is unresolved.

## beta0.5.8 — 2026-07-11

### Changed

- Standardized production configuration on Multi-Agent V2 with 16 whole-tree slots, including the root, and maximum depth 4.
- Clarified that the Six Ministries are non-visible and silent until bounded Shangshu dispatch.

### Fixed

- Removed legacy `[agents].max_threads` from recommended V2 configuration.
- Corrected package documentation: `plan-archives` and `memory-decisions`, including placeholder READMEs, are not ZIP contents.
- Replaced the fail-open package denylist with a case-insensitive, fail-closed portable path policy.
- Rejected unknown directories, symlink/junction/reparse entries, nested archives, Zip Slip paths, duplicate/case-colliding members, binary payloads and compression bombs.
- Promoted historical/generated-runtime zero budgets from warnings to release hard failures.
- Removed a secret-like test fixture false positive while preserving the original transaction test.

### Added

- Added `VERSION`, `RELEASE-LOG.md`, root `release-manifest.json`, an external SHA256 sidecar and Git-tree-to-ZIP verification.
- Added 20 package privacy regression tests.

### Privacy

- This release contains no personal Shiguan records, plan archives, memory decisions, raw logs, sessions, credentials, Obsidian secrets, peer/import/runtime state, backups or host-local generated indexes.
