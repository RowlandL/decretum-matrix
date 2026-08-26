# HANDOFF — decretum-matrix Loading-Procedure Fix (release/beta1.0.7)

> 状态：**本地分支，未推送远端，待交叉审查**。本文件为未追踪（untracked）交接文档，不纳入 git 版本控制。
> Status: **local branch, NOT pushed, awaiting cross-review.** This file is untracked and excluded from git.

---

## 0. Abstract（摘要）

本次将「诏令矩阵（decretum-matrix）正确调用/加载流程」从用户级全局记忆固化进 skill 本体（`SKILL.md`），使空白 Agent 与换机重装后加载即继承。改动落在本地分支 `release/beta1.0.7`（顺位自 `beta1.0.6`），提交 `98ccb02`，**未推送**。对应 GitHub issue **#1**。

---

## 1. Context（背景）

- 正确调用流程此前仅存于用户级全局记忆 `~/.workbuddy/MEMORY.md`，**不随 skill 分发**。
- 后果：空白 Agent / 换机重装加载 skill 时读不到该流程，只能自行推断 SKILL.md，导致重复误读——漏掉自带 CLI、误将三省排除出子官署、谎称读完全文而实仅取 2KB 预览。
- 决策：将流程写进 skill 本体。已作为 issue 提交（见 §6）。

## 2. Changes Made（已做改动）

| Item | Detail |
| --- | --- |
| 克隆镜像 | `RowlandL/decretum-matrix` → `\\TRUENAS\Omina\gitmirror\decretum-matrix`（`origin` 改名 `upstream`）|
| 网络约束 | git 全程 `-c http.version=HTTP/1.1`（沙箱默认 HTTP/2 直连 `github.com:443` 被阻断）|
| 属主白名单 | 网络共享仓库 SID 与当前用户不一致，已加 `git config --global --add safe.directory '%(prefix)///TRUENAS/Omina/gitmirror/decretum-matrix'` 解除 `dubious ownership` |
| 版号分支 | 顺位新建 **`release/beta1.0.7`**（基 `release/beta1.0.6`，HEAD `650d2c3`）|
| SKILL.md 改动 | `Overview` 之后、`Progressive Loading Map` 之前新增 **`## Loading Procedure`** 一节；英文为主，贴合原文件风格；八步 |
| 提交 | 本地 `98ccb02`（仅 `SKILL.md`，+18 行）；**未推送** |
| 局部身份 | 本仓库 `user.name=RowlandL` / `user.email=rowlandl@users.noreply.github.com`（未改全局）|

## 3. Embedded Loading Procedure（已固化之八步）

1. **Trigger load** — Load `SKILL.md` via host Skill mechanism (≤20 KiB). Do not treat 67–80 KiB `references/*.md` as entry.
2. **Pass top hard gates** — Satisfy `P00` contract + `Common Hard Gates`. If latest message does not select `approval|autonomous|super`, **ask first and stop**; memory/prior-session/runtime may not choose.
3. **Authority × behavior** — orthogonal; `super并行` = authority=super, behavior=parallel, runtime=native.
4. **Progressive reference loading** — read only the governing volume per `Progressive Loading Map`; no full-volume load; for large files use segmented reads / on-disk copy.
5. **Tool-layer triad** — (a) **CLI**: `scripts/court_cli.py` (→ `court_cli_registry.py`), schema `decretum.cli.result.v1`, `--format json`, groups `court/office/shiguan/supercc/install/release/check`; `bin/decretum-matrix.py` is release launcher (needs ZIP), not daily CLI. (b) **Agent/host dispatch**: real sub-office spawn/reuse/wake. (c) **Reference markdown**: semantic contract, on demand.
6. **Dispatch hierarchy** — `太子(router, not dispatchable) → 三省(L1: 中书/门下/尚书) → 六部(L2: 吏/户/礼/兵/刑/工, by 尚书省) → 工坊/工匠`; 中书/门下 = peer review, do not take 六部 dispatch; run `agent-admit` before real host spawn.
7. **Shared Shiguan index (built at install)** — root `%USERPROFILE%\.agents\court-shiguan\decretum-matrix\references`; recall via `scripts/query_shiguan_index.py`.
8. **Closeout** — pass 门下 review; copy `payload.closeout_identity` from `shiguan archive-checkpoint` verbatim; no self-assigned id without valid archive receipt.

## 4. Verified Technical Findings（已验证事实）

- **CLI 是机器操作正道入口**：`court_cli.py`（薄派发→`court_cli_registry.py`），输出 schema `decretum.cli.result.v1`，分组 `court/office/shiguan/supercc/install/release/check`；例 `court status` / `shiguan archive-checkpoint` / `court open --fast --request-file <request.json>`。`bin/decretum-matrix.py` = 发布启动器（须带发布 ZIP），**非**日常 CLI。
- **层级契约**：`太子 → 三省(L1) → 六部(L2,尚书省选定) → 工坊/工匠`。三省与六部**皆为子官署**（可真实 host-native spawn）；中书/门下为同级复核官署，不接管六部差遣。太子是主线程路由，不可差遣。
- **共享史馆索引根**：`%USERPROFILE%\.agents\court-shiguan\decretum-matrix\references`（经 `court status` 实证）；recall 走 `query_shiguan_index.py`。
- **子智能体真实派发可用**：Agent 工具 = 主机原生 spawn；12 官署实测全 OK；后端 503「号池已空」为瞬时账号池耗尽，非层级/契约问题。
- **Read 截断陷阱**：>~2KB 文件 Read 仅返 2KB 预览；大文件用 offset+limit 分段或读 `tool-results` 磁盘副本，不得谎称「已逐行读完」。

## 5. Open Items / For Reviewer（待审查项）

- [x] 确认 `Loading Procedure` 插入位置与措辞（Overview 之后、Progressive Loading Map 之前）。
- [x] 合规化 R2/R3/R4/R5 已落地：frontmatter（license/metadata）+ description 四要素 + token 瘦身（Closeout/Validation 迁 references）+ shiguan-imports 扁平化（2026-08-11，3 独立提交 `eede0ec`/`ebf5ed0`/`854a4e0`）。
- [x] **整改审查点（用户定调，2026-08-11）**：校验脚本不得带入 Skill 运行时；只在安装时从发布包校验、通过后自删。已落地（提交 `a3e8dee`）：安装投影移除 `scripts/quick_validate.py`；`package_skill.py` 新增 `PACKAGE_INSTALL_VALIDATION_FILES` 使校验脚本只随发布包分发；INSTALL-PROMPT/validation-packaging 措辞改为安装时校验自删；本机双目标无校验脚本。
- [x] C 线本地推进（2026-08-11，未推送）：VERSION/SBOM/manifest/RELEASE_LABEL 全部升 beta1.0.7（`057054c`）；package-only quick_validate（`062a22d`）；identity `skill_sha256` 重绑定当前 SKILL.md（`956f3e0`）；**candidate ZIP 构建成功**（`29bbf56e…`，CANDIDATE_NOT_RELEASED），ZIP 内 identity-哈希/版本/投影校验全部一致，安装时校验-自删模拟通过。
- [x] **发布完成（2026-08-11，用户授权 + 备注「仅为预修复」）**：tag `beta1.0.7`（annotated，无签名 → attestation tag_signature=UNAVAILABLE）已推送 upstream；Release https://github.com/RowlandL/decretum-matrix/releases/tag/beta1.0.7 已发布（body 顶部标注 ⚠️ 预修复 / Pre-fix release），5 资产（ZIP/sha256/attestation/release-notes/SBOM）全部上传，线上 ZIP sha256 `29bbf56e…` 与本地 release 包一致；分支 `release/beta1.0.7` 已推送 upstream（HEAD `956f3e0`）。
- [ ] 正式版本：交叉审查 + 完整发布回归通过后，另行发布正式 1.0.7（替代预修复语义）；关闭 issue #1。
- [ ] 可选：升级本机已装 skill（`~/.agents/skills/decretum-matrix/` 与 `~/.zcode/skills/decretum-matrix/` 已于 2026-08-11 同步至 1.0.7 本地分支投影；正式发布后可拉线上 ZIP 复核）。
- [ ] 机器配套（2026-08-11 已完成）：Python 3.14.7 用户级装 + PATH（`C:\Users\Administrator\AppData\Local\Programs\Python\Python314`），PyYAML 6.0.3（清华 PyPI）；`quick_validate.py .` 对 1.0.6 与 1.0.7 均 PASS。

## 6. References（引用）

- Issue #1: https://github.com/RowlandL/decretum-matrix/issues/1
- Local mirror: `\\TRUENAS\Omina\gitmirror\decretum-matrix`
- Branch: `release/beta1.0.7` · Commits: `956f3e0`（HEAD）· `062a22d` · `057054c` · `a3e8dee` · `5a5b4da` · `9f2e010` · `854a4e0` · `ebf5ed0` · `eede0ec` · `98ccb02` · Base: `release/beta1.0.6` (`650d2c3`)
- Release: https://github.com/RowlandL/decretum-matrix/releases/tag/beta1.0.7（预修复/pre-fix，body 已标注）
- ZIP sha256: `29bbf56e01cbf4d9731c416d426bd39d8853c5025f31d5bc27caf21fb2f0b28c`
- User-level memory (not shipped): `~/.workbuddy/MEMORY.md` → section 「诏令矩阵 · 正确调用正道」

## 7. Reproduction（复现命令）

```bash
git -c http.version=HTTP/1.1 clone --origin upstream https://github.com/RowlandL/decretum-matrix.git ./decretum-matrix
cd decretum-matrix
git checkout -b release/beta1.0.7 release/beta1.0.6
# edit SKILL.md: insert ## Loading Procedure between Overview and Progressive Loading Map
git add SKILL.md && git commit -m "docs(beta1.0.7): SKILL.md add 'Loading Procedure' section (close #1)"
# DO NOT push until review approved
```

## 8. Conventions Noted（约定）

- SKILL.md 编辑须保持原「大部分英文」风格，中文仅保留固有官署名。
- 此类改动留本地分支，未明示「推送」前不 push。
- git 至 `github.com` 必须 `-c http.version=HTTP/1.1`。
- 网络共享仓库属主 SID 不一致时需 `safe.directory` 白名单。
