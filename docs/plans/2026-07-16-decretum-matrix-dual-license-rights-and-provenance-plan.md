# Decretum Matrix 双许可、权属、来源与更名发布治理计划

计划编号：`DM-LPR-20260716-A02`

状态：`ACTIVE / P0_P5_PASS_WITH_LEGAL_REVIEW_REQUIRED / CLEAN_CANDIDATE_PENDING`

当前游标：`P5_ALL_SURFACES_AND_PACKAGE_CONTRACT`

执行工作树：`D:\project\decretum-matrix-beta0.5.10`

执行分支：`release/beta0.5.10`

权利主体、CLA licensor、商标 owner：`孙华清`

公开维护者身份：`@RowlandL`（GitHub ID `42199880`）。该账号与 numeric ID 只表示维护者身份，不替代、扩写或另行命名法定主体 `孙华清`。

远端目标：`https://github.com/RowlandL/decretum-matrix.git`；仓库为 PUBLIC、当前为空。本计划不允许从 dirty worktree 推送。

## 1. 目标与边界

本计划在同一 A02 major-stage 流程内完成以下收敛：

1. 正式产品名统一为 `Decretum Matrix（诏令矩阵）`，规范仓库、skill、package 与发布标识统一为 `decretum-matrix`。
2. 未来社区发行采用 `AGPL-3.0-only`；商业授权只能由 `孙华清` 另行书面授予。
3. 贡献治理从 DCO-only 升级为 `DCO + CLA gate`，使项目在权利充分时具备双重许可与商业许可所需授权链。
4. 保留 Decretum Matrix、`decretum-matrix`、官方 logo 与官方发行标识的商标及来源识别边界。
5. 永久保留 cft0808/edict 的 MIT 来源、原版权、固定 commit 与完整许可；不得因无整文件 blob 命中而声称不存在借鉴。
6. 先完成本地 repo/worktree/root mapping 更名，再按 major-stage 闭环、clean package、上一已完成版本终态、下一 release 分支的节奏逐步发布。

明确非目标：不重写 Git 历史；不撤销已经授予的 Apache-2.0 权利；不把上游 MIT 材料归入孙华清独占版权；不虚构公司、英文名、拼音、地址或邮箱；不创建复杂商业合同；不读取 pending body；不发布 `D:\project` 根控制仓库。

## 2. 永久硬门禁

- `pending_body_access=NO`；只允许 metadata/index/hash 白名单探针。
- root、primary、release 与所有受影响 linked worktree 在每个 gate 前后 `git diff --cached --name-only` 均为空。
- 单一 mainline writer；common-dir、目录移动、worktree repair、workspace、state/event、refs、remote 与最终集成严格串行。
- 历史 state/events/root refs/release artifacts 不删除、不改写、不 force；更正只追加 supersede/migration receipt。
- 四个受保护史馆文件及其技术 locator 保持原字节：
  - `references/shiguan-index.jsonl`
  - `references/shiguan-knowledge-graph.json`
  - `references/shiguan-tree/_index.md`
  - `references/shiguan-tree/capability-index/_index.md`
- 受保护安装 locator `~/.agents/skills/court-capability-router/references`、共享史馆旧 namespace、不可变历史/恢复记录及 deprecated `$court-capability-router` 输入按 allowlist 保留；不得全局盲替换。
- 无 submodule/subtree；不记录 token；remote/push/tag/PR/GitHub release/asset upload 分项验收与授权。

## 3. 已建立的恢复与本地更名前像

恢复点：`D:\project\recovery-points\CCR-R2-SHIR-20260714-A02-20260716-pre-decretum-matrix-local-rename`

- `preimage-fingerprint.json`：SHA-256 `4CE8CF0C97E8DAC92691B7D9DC55DAFA85C76389694B925B72F8DD49F60B471C`
- dirty release 快照：SHA-256 `F845D93DE1EFE5A1C719C173AA147EECE8AA77261E35D6AFBCA64D1B7CCED058`
- root control 快照：SHA-256 `9712B20D7295DEA54AA2843FD3BDE38DAE100AD5D041240BCF08446EEA1BCF05`
- 前像覆盖 15 个 worktree、四个受保护文件、root/child index=0、remote=0、pending body access=NO。

本地路径迁移已完成并通过 R0 最终复核：

- primary：`D:\project\decretum-matrix`
- 活动 release：`D:\project\decretum-matrix-beta0.5.10`
- 历史 release worktree：`D:\project\decretum-matrix-beta0.5.9`
- managed worktrees：`D:\project\worktrees\decretum-matrix\*`
- root refs：新增 `codex/decretum-matrix/*`；旧 `codex/court-capability-router/*` 原样保留。
- task mounts：活动映射使用 `attached/decretum-matrix`；旧 junction 在新目标验证后仅移除 junction 自身。
- root controller：`repo-control doctor=PASS`，现有标准库测试 `29/29 PASS`。
- post-fingerprint：15/15 worktree 的 mapped path、HEAD、branch/detached、index、unstaged diff 与 common-dir 均 PASS；beta0.5.9 的 untracked/working manifest 与 preimage 同算法 SHA-256 精确相同；beta0.5.10 唯一预期 delta 为本计划及两份 governing plan 指针。

## 4. 发行切点与既有授权

1. `beta0.5.9` 的 Git 前像明确声明 Apache-2.0；任何另有精确 artifact 证据证明已按 Apache-2.0 分发的历史版本，也继续受该既有授权约束，不能被本计划追溯撤回。`beta0.5.8` tag tree 本身没有 `LICENSE`、`NOTICE`、SBOM 或 manifest license 字段，因此仅凭 tag 不得把其许可状态写成已确证 Apache-2.0；必须取得 artifact-specific evidence 并经法律审阅。
2. `beta0.5.10` 是首个候选 `AGPL-3.0-only` + 新品牌发行切点。只有 P0 证明该精确版本从未按 Apache-2.0 对外分发，且 P1-P6 全部通过时才可签发该切点；否则切点自动顺延到下一未分发 release，不改历史。
3. cft0808/edict 及其他第三方材料继续按各自许可证；项目级 AGPL 不吞并或重标第三方 MIT 权利。
4. 法律文本与 CLA 均标注 `LEGAL_REVIEW_REQUIRED`，正式公开前需要法律专业审阅；技术 checker PASS 不等于法律意见。

权威法律文本：

- SPDX `AGPL-3.0-only`：`https://spdx.org/licenses/AGPL-3.0-only.html`
- GNU AGPLv3：`https://www.gnu.org/licenses/agpl-3.0.txt`
- Apache License 2.0：`https://www.apache.org/licenses/LICENSE-2.0.txt`
- ASF contributor agreement 参考：`https://www.apache.org/licenses/contributor-agreements.html`

## 4A. 当前可审计 gate ledger

本表只记录当前工作树、已存在 receipt 与已运行 checker 能证明的状态；合规文件、
commit author metadata、GitHub maintainer 身份和 checker PASS 均不得替代权属证明。
未知项保持 `UNKNOWN` 或 `LEGAL_REVIEW_REQUIRED`，不得据此虚构发行或交付事实。

| Gate | 当前状态 | 可审计依据与剩余条件 |
|---|---|---|
| P0 `LEGAL_PREIMAGE_INVENTORY_GATE` | `PASS / LEGAL_REVIEW_REQUIRED` | `docs/legal/2026-07-16-license-preimage-inventory.md` 已记录有界 local/GitHub preimage、`beta0.5.10_external_distribution_count=0` 的证据边界与自动顺延规则；该 receipt 明确不把合规文件、作者 metadata 或历史许可声明当作权属证明。 |
| P1 `UPSTREAM_MIT_PROVENANCE_GATE` | `PASS_WITH_LEGAL_REVIEW_REQUIRED` | `docs/legal/2026-07-16-cft0808-edict-bounded-similarity-and-rights-review.md` 固定 GitHub commit/tree/archive 与 MIT hash，记录 18×113 文件、1040 对的 normalized-text/token-shingle/structure 阈值、top hits 与人工裁定；exact-file intersection 为 0，但明确不把 0 match 写成 0 借鉴。MIT notice 永久独立保留。 |
| P2 `FUTURE_LICENSE_ARCHITECTURE_GATE` | `PASS_WITH_LEGAL_REVIEW_REQUIRED` | AGPL 原文/hash、`AGPL-3.0-only` metadata、商业授权说明和 Apache 历史边界已收敛；仅 `beta0.5.9` 为 Git 已确证 Apache-2.0 历史版本，`beta0.5.8` 保持 `LICENSE_NOT_ESTABLISHED_FROM_TAG`，除非出现 artifact-specific evidence。 |
| P3 `CLA_AND_RIGHTS_CHAIN_GATE` | `PASS_WITH_LEGAL_REVIEW_REQUIRED` | 同一 receipt 将当前 269 个 manifest 路径全部映射到 third-party、project-directed original/generated、upstream-inspired/locally implemented、generated local、original/local 或 modified-derived（当前 0 identified）；维护者声明精确记录 `孙华清` 为项目权利主体，`@RowlandL` 仅为 GitHub maintainer identity。29 个 reachable commit metadata 行仅出现 `RowlandL=12` 与自动化身份 `Court Release Bot=17`；metadata 和合规文件均不作为权属证明。 |
| P4 `TRADEMARK_AND_AFFILIATION_GATE` | `PASS_WITH_LEGAL_REVIEW_REQUIRED` | `TRADEMARKS.md` 精确记录 `Trademark policy owner: 孙华清`、指名性使用、no-affiliation 与未注册边界；`assets/brand/*` 已记录来源任务 `019f6691-258f-71a1-b63d-f7ad0b881d70`、latest v2 修正版及四个精确 hash，分类为 project-directed original/generated artwork，不归入 cft0808 MIT，法律权属仍需审阅。 |
| P5 `ALL_SURFACES_CONVERGED_GATE` | `PASS_WITH_LEGAL_REVIEW_REQUIRED` | 权威 manifest 已按最终 tracked preimage 再生；package staging 可在无 Git metadata 的 materialized payload 上直接校验而不重新生成；privacy `59/59`、payload self-test/check、builder self-test、source budget、legal 与 diff check 均通过。四个 brand assets、release manifest、benchmark 与 skill identity 均为机械 mandatory members。 |
| P6 `LEGAL_PROVENANCE_PACKAGE_ACCEPTANCE_GATE` | `BLOCKED / CLEAN_CANDIDATE_PENDING` | P0-P5 已通过；仍须从 clean accepted commit 构建 tagless candidate、通过 pre-install、安装同一 ZIP 并通过 post-install。无 annotated-tag 授权时 final promotion/attestation 保持 `NOT_RUN`，不阻断本地 candidate acceptance，也不得冒充正式 release。 |

当前最早未完成门禁为 P6；`current_cursor=P6_CLEAN_CANDIDATE_INSTALL_ACCEPTANCE`。
在 clean commit/candidate/install receipts 形成前，不得把 source/package checker green
解释为首次候选包已经签发。

## 5. 分阶段执行

### R0 — 本地更名与控制面迁移验收

1. 对 primary、两个 top-level release worktree、六个 managed worktree、六个 host-managed detached worktree做 pre/post 映射对账。
2. 全部 worktree 的 HEAD、branch/detached、index、unstaged diff、untracked manifest、working-file manifest 与 common-dir 指纹必须等价；common-dir 唯一为 `D:\project\decretum-matrix\.git`。
3. `workspace.yaml` 的 `id/path/worktree_directory` 同时为 `decretum-matrix`；schema 保持通用，不硬编码项目名。
4. 新 `.repo-control/state/decretum-matrix`、events、root refs 与 mounts 指向新路径；旧 namespace 冻结保留；追加 project-rename supersede receipt。
5. 更新根 README、project-memory、repository architecture、inventory 与 repo-control tests；不得覆盖根仓已有无关 dirty 修改。

Gate：`LOCAL_RENAME_AND_MAPPING_GATE=PASS`。历史游标随后进入 P0；当前游标以第 4A 节 gate ledger 为准。

### P0 — 只读 preimage 与发行面 inventory

枚举并记录 branch、HEAD、index、remote、字节数和 SHA-256：`LICENSE`、`NOTICE`、`THIRD_PARTY_NOTICES.md`、`README.md`、`CONTRIBUTING.md`、`CHANGELOG.md`、`RELEASE-LOG.md`、`SBOM.spdx.json`、`release-manifest.json`、install/prompt、package allowlist、legal/privacy checker、历史 tag/ZIP/release metadata。

既有合规文件只能证明当时的许可声明，不能单独证明作者身份、版权集中或重许可能力。P0 必须检查本地/可达 tags、archive 与 release artifact 目录、既有 remote 配置与 reflog 线索、GitHub repository/Releases/assets、已知交付目录及其 hash receipt；只有这些证据均未发现 `beta0.5.10` 对外分发且用户侧无已知交付时，才记录 `beta0.5.10_external_distribution_count=0`。无法证明时 fail closed，并把许可切点顺延到下一未分发 release。

Gate：`LEGAL_PREIMAGE_INVENTORY_GATE=PASS`。

### P1 — Provenance 与上游 MIT 永久保留

1. 新增 `PROVENANCE.md`，按模块/文件族标记：`original`、`upstream-inspired`、`modified-derived`、`third-party`、`unknown-needs-review`。
2. 固定 cft0808/edict commit `14a207557719c046af0f993a7bff1cc5a5015b33`、MIT 全文、原版权、benchmark purpose、`runtime_dependency=false`、`governing_source=false`。
3. 保存已完成的精确 blob 比对事实：当前工作树及可达本地对象与固定上游 222 blobs 整文件匹配为 0；同时明确这不能排除片段改写、结构或语义借鉴。
4. 执行有界相似性/结构审查，记录规则、阈值、命中与人工裁定；不得扫描或改写无关完整历史。
5. `THIRD_PARTY_NOTICES.md`、SBOM、manifest 与 package 必须含一致的 MIT provenance；不得把上游代码声明为孙华清独占版权。
6. 对官方 logo/图标逐文件记录来源、作者/权利主体、生成过程、路径和 SHA-256；在权属无法证明前不得主张商标专有权、不得纳入官方发行包或 GitHub branding。

Gate：`UPSTREAM_MIT_PROVENANCE_GATE=PASS`。

### P2 — 未来社区版与商业授权架构

1. 首个通过切点的社区发行根 `LICENSE` 使用完整 GNU AGPLv3，SPDX 精确为 `AGPL-3.0-only`。
2. Apache-2.0 只在历史版本/兼容说明中保留，不把既有授权描述为失效、撤销或改写。
3. 新增 `COMMERCIAL-LICENSE.md`：明确“本文件本身不授予商业许可，任何商业权利仅由 `孙华清` 另行签署的书面协议产生”，并标记 `LEGAL_REVIEW_REQUIRED`；不虚构价格、担保、赔偿、法域、地址或联系方式。
4. README、NOTICE、SBOM、manifest 清楚区分项目自有部分、第三方 MIT 与历史 Apache 版本。

Gate：`FUTURE_LICENSE_ARCHITECTURE_GATE=PASS`。

### P3 — CLA、权属与贡献治理

1. 新增 `CLA.md` 或等价 CLA 草案，主体精确写 `孙华清`，并标记 `LEGAL_REVIEW_REQUIRED`。
2. CLA 至少授予复制、修改、制作衍生作品、分发、再许可、双重许可和商业许可所需的非排他权利，并覆盖必要的专利授权/贡献声明；不得声称转让第三方或雇主无权转让的权利。
3. `CONTRIBUTING.md` 从 DCO-only 升级为 DCO + CLA gate；在自动化尚未接入前明确人工 gate，禁止假称已启用 GitHub CLA bot。
4. 新增 `AUTHORS.md`，分别写法定主体/权利人 `孙华清` 与维护者 `@RowlandL`（GitHub ID `42199880`），不得把账号或 numeric ID 写成另一法定主体；`.github/CODEOWNERS` 使用 `* @RowlandL`。
5. CLA 只约束未来/追认贡献，不能自动补齐既有权利链。按 commit/file/module 建立现有贡献权属矩阵；对无法证明孙华清拥有商业再许可权的内容，必须取得追认 CLA/书面许可、移除或洁净重写，否则 `CLA_AND_RIGHTS_CHAIN_GATE=BLOCKED`。

Gate：`CLA_AND_RIGHTS_CHAIN_GATE=PASS_WITH_LEGAL_REVIEW_REQUIRED`。

### P4 — 商标与来源识别

新增 `TRADEMARKS.md`：

- owner 为 `孙华清`；保留 `Decretum Matrix（诏令矩阵）`、`decretum-matrix`、官方 logo 与官方发行标识。
- 允许准确、必要的来源描述、兼容性说明与指名性使用。
- 不授权造成官方关联、赞助、认可或来源混淆；第三方不得把修改版标记为官方发行。
- 不声称已注册商标；不暗示 Apache、GNU、cft0808/edict 或其他上游对本项目背书。

Gate：`TRADEMARK_AND_AFFILIATION_GATE=PASS`。

### P5 — 全表面收敛与 package contract

互不重叠的只读/写集可并行审计，最终由单一集成 writer 串行吸收：

- 品牌/identity：SKILL、profiles、dossiers、registry、dispatch、README、install、中英文档、identity manifest。
- legal/provenance：LICENSE、NOTICE、THIRD_PARTY、PROVENANCE、COMMERCIAL-LICENSE、CLA、TRADEMARKS、AUTHORS、CONTRIBUTING。
- package/SBOM：SBOM、release manifest、payload generator、package allowlist、legal/privacy checker、deterministic build。
- GitHub metadata：CODEOWNERS、issue/PR/security templates 与 repository links；不得记录 token。
- root control：workspace、README、project-memory、architecture、inventory、repo-control tests/mappings。

旧 beta/已完成工件保持原字节。新策略只作用于通过 P0 切点的未来发行。package 必须包含 AGPL、商业授权说明、CLA/贡献政策、TRADEMARKS、THIRD_PARTY_NOTICES、PROVENANCE、AUTHORS、SBOM 与 release manifest。

精确实现映射：

- `scripts/package_skill.py`：`ROOT_ALLOWED_FILES`、`LEGAL_REQUIRED_MEMBERS`、`EXCLUDE_DIRS`、`validate_optional_release_metadata`。
- `scripts/release_payload_manifest.py`：`LEGAL_PATHS`、`build_manifest`、`shape_problems`、`self_tests`。
- `scripts/check_release_legal.py`：`REQUIRED_FILES`、`evaluate`、`run_self_test`。
- `scripts/check_package_privacy.py`：`LEGAL_REQUIRED` 与合法根文件 fixtures。
- `scripts/check_install_current_agent_copy.py`：移除旧 Apache/旧产品身份与未经授权邮箱断言，加入新主体/许可证/locator 分离的正反 fixtures。
- Phase 1 必须先补齐并验收 `scripts/install_current_agent_copy.py` 与 `references/manifests/install-projection.v1.json`；若前置 cluster 未交付，则作为 P5 实施项完成，禁止把不可达 checker 列为伪 PASS。

Gate：`ALL_SURFACES_CONVERGED_GATE=PASS`。

### P6 — 验收、阶段 commit、洁净包与发布循环

最低验证：

- `python -B scripts/check_release_legal.py --self-test --json`
- `python -B scripts/release_payload_manifest.py --self-test --check --json`
- `python -B scripts/check_release_manifest.py --json`
- `python -B scripts/check_package_privacy.py`
- `python -B scripts/check_skill_identity.py --json`
- `python -B scripts/quick_validate.py .`
- `python -B scripts/check_catalog.py --strict`
- `python -B scripts/check_portability.py`
- `python -B scripts/build_release_artifacts.py --self-test --json`
- `python -B scripts/check_install_prompt.py`、`python -B scripts/check_install_current_agent_copy.py`
- `python -B scripts/check_court_runtime.py`、`python -B scripts/check_semantic_continuity.py --json`
- 从同一 clean commit 分别运行 `python -B scripts/package_skill.py --out <run1b-no-clobber.zip>` 与 `python -B scripts/package_skill.py --out <run2b-no-clobber.zip>`，逐文件 manifest 和 ZIP SHA-256 必须相同
- `TAGLESS_CANDIDATE_GATE`：`build_release_artifacts.py --mode candidate` 在 full HEAD 目录生成或精确复用候选，不创建 tag/attestation；`check_release_gate.py --phase pre-install` 只跑 source/package，安装同一 ZIP 后再跑 `--phase post-install`
- `ANNOTATED_FINAL_TAG_GATE` 与 `BYTE_IDENTICAL_PROMOTION_GATE`：final attestation 仅在 annotated tag 指向 accepted HEAD 且 final ZIP 与候选 ZIP SHA-256 相同时通过
- 其余受影响的 Phase 1 runtime/dispatch/preload/assignment/result/outcome/completion/migration 全量回归
- `git diff --check`、`.pyc=0`、root/child/all affected index=0、protected hash unchanged、pending body access=NO

门下只批准精确 pathspec 后，才进入一次有界 stage commit 窗口；commit 后立即恢复 index=0。package 只能从该精确 commit 的 clean worktree 构建。

Gate：`LEGAL_PROVENANCE_PACKAGE_ACCEPTANCE_GATE=PASS`。

## 6. 新名称下的阶段发布循环

当前 major stage 仍遵循：阶段 RED/GREEN/SPEC/QUALITY 与全局回归通过 -> 有界本地 commit -> clean package -> 上一已完成版本取得上传终态 -> 创建下一 `release/beta0.5.(x+1)` -> compact handoff。

新远端为空且 `beta0.5.9` 是不可改写的旧品牌 Apache 历史版本，因此采用一次性 bootstrap 规则：

1. `beta0.5.9` 不伪装为新品牌 canonical release；其终态记为 `LEGACY_APACHE_ARTIFACT_RETAINED / CANONICAL_NEW_NAME_UPLOAD_NOT_APPLICABLE`。若未来要公开历史兼容包，必须单独说明旧身份与原许可，不能重打标签为 AGPL。
2. `beta0.5.10` 完成新品牌、AGPL 切点和本 major stage 后，创建 `release/beta0.5.11` 并交接；首次 canonical 上传候选仍为已完成的 `beta0.5.10`。
3. 当 `beta0.5.11` major stage 完成、其 commit/package 通过后，从独立 clean OSS-GOV worktree 发布上一已完成版本 `beta0.5.10`，然后创建 `beta0.5.12`。其后严格维持一版本滞后的逐阶段上传节奏。
4. 所有 branch、tag、GitHub Release title、asset name、SBOM package name、manifest 与文档使用 `Decretum Matrix / decretum-matrix`；历史证据与技术兼容 locator 例外必须明确标记。
5. 每次 receipt 分项列出 `add_remote`、`push_branch`、`push_tag`、`create_release`、`upload_assets`。当前 dirty stage 这些动作全部 `NOT_RUN`。
6. 首次外部动作前，remote 必须精确为 `https://github.com/RowlandL/decretum-matrix.git`；从 clean accepted commit 执行，不 push 根控制仓、不 force、不覆盖远端。

Gate：`NEW_NAME_STAGED_PUBLICATION_GATE=PASS`。

## 7. 计划审查与停止条件

计划审查必须确认：P0-P6 全覆盖；主体仅为 `孙华清`；`@RowlandL` 仅维护者身份；MIT carve-out 独立；Apache 历史不追溯撤销；商标不误导 affiliation；local rename/map 具备 recovery 与 append-only receipt；发布节奏只从 clean accepted commit 启动。

遇到下列任一项立即停止相应阶段：受保护哈希漂移、pending body 被访问、index 非空且不在批准 commit 窗口、来源分类无法裁定、beta0.5.10 已存在外部分发证据、remote 不匹配、包不确定、法律文本缺少 `LEGAL_REVIEW_REQUIRED`、或任何动作需要未列明的外部授权。

本计划完成结果只允许：`PASS`、`PASS_WITH_LEGAL_REVIEW_REQUIRED`、`BLOCKED_WITH_RECOVERY_RECEIPT`。
