# beta1.1.5 发布 · 任务规划

> 依据：`decretum-release-fastpath` 技能（发布阶段复用 receipt、Git/安装/发布 fail-closed、外部动作需动作级授权）。
> 本文件是**规划**，不是执行回执。

## 现状基线（已实测）

| 项 | 值 |
| --- | --- |
| 分支 / worktree | `work/laya-shiguan-training` @ `D:\project\worktrees\decretum-matrix\laya-shiguan-training` |
| 起点 | `release/beta1.1.5`（`7f63df1`）|
| 本次提交 | `f2bd9a5`（能力）、`96fffac`（派遣说明）|
| 工作区 | **clean** |
| remote | `origin` → `https://github.com/RowlandL/decretum-matrix.git` |
| CI | `.github/workflows/ci.yml`（30.7 KB）：`push` / `pull_request` / `workflow_dispatch`；jobs = source-contracts-{ubuntu,windows,macos} + source-contracts（汇总）+ package-entrypoint |
| VERSION | `beta1.1.5` |
| 法务门禁 | `check_release_legal` = **ok: true / problems: []**（13 个必需文件全部存在）|

## 资产盘点

| 资产 | 文件 | 体积 | 入库 | 安装态 | 处置建议 |
| --- | --- | --- | --- | --- | --- |
| 能力代码 | 8 | 0.1 MB | ✅ 已提交 | ✅ 已投影 | 保持 |
| 服务 | 4 | <0.1 MB | ✅ | ✅ | 保持 |
| 文档 / schema / SKILL.md | 4 | <0.1 MB | ✅ | ✅ | 保持 |
| **模型 `laya-multilingual`** | 5 | **646.8 MB** | ❌ gitignored | ❌ | **本次要纳入安装态** |
| 向量/训练产物 `runs` | 7 | **1,345.6 MB** | ❌ | ❌ | **建议清理**（仅 `recall-index.pt` 可重建）|
| 语料 `corpus` | 10 | 2.9 MB | ❌ 本地（用户拍板）| ❌ | 保持本地 |
| 环境 `.venv` | 20,832 | 3,172.9 MB | ❌ | ❌ | 本机 bootstrap |
| `torchinductor_32893` | 0 | 0 | — | — | **清理**（torch 编译缓存残留）|

## 许可与引用链（已核实）

| 组件 | 来源 | 许可 | 用途 |
| --- | --- | --- | --- |
| `convaiinnovations/laya-multilingual` | HuggingFace | **Apache-2.0** | 决策模型基座（322M）|
| `jhu-clsp/mmBERT-base` | HuggingFace | **MIT** | Laya 的主干编码器（`rl_agent_config.encoder` 明示；ModernBertForMaskedLM / 256k vocab / 768 hidden / 22 层）|
| 本仓库 | — | **AGPL-3.0-only** | 宿主 |

**合规结论**：Apache-2.0 与 MIT 均为宽松许可，**允许再分发与商用**；义务是**保留版权声明与许可全文**、标明修改。二者与 AGPL-3.0 宿主**不冲突**（AGPL 可包含宽松许可组件）。

## 阶段划分

### 阶段 0 · 资产盘点 ✅ 已完成
上表即产出。

### 阶段 1 · 许可与引用条款拟定
产出（全部为增量修改，不重写既有文件）：

1. `THIRD_PARTY_NOTICES.md` — 增补 Laya 与 mmBERT 条目：来源 repo、许可种类、完整许可文本（fence）、版权行。
2. `PROVENANCE.md` — 增补模型来源链：HF repo id + **固定 revision**、取用日期、文件清单与 sha256、主干替换说明。
3. `SBOM.spdx.json` — 增补 2 个 SPDX 包（`laya-multilingual`、`mmBERT-base`）及其 `licenseConcluded`，并把 `documentNamespace` 从 `…beta1.1.4-20260920` 升到 **beta1.1.5**。
4. `scripts/checks/check_release_legal.py` — `EXPECTED_SBOM_NAMESPACE` 同步升到 beta1.1.5。
5. 模型卡引用条款（`training/laya-shiguan/docs/model-provenance.md`）：面向使用者的引用说明——如何引用 Laya、如何标注本仓的二次开发。

**验收**：`python -B -m checks.check_release_legal --root <repo> --json` → `ok: true, problems: []`。

### 阶段 2 · 模型纳入安装态（用户要求：真实文件，非投影）
**决策点（需拍板）**：模型 646.8 MB 如何进入安装态？

| 方案 | 做法 | 优点 | 代价 |
| --- | --- | --- | --- |
| **A（推荐）安装时下载** | 仓库不含 blob；安装脚本按**固定 revision** 从 HF 拉取，校验 sha256，落为**真实文件**到安装根 | 仓库小、CI 三平台快、许可与来源清晰 | 安装需联网；需新增一个安装步骤 |
| B 仓库携带 blob | 直接进 git（需 Git LFS）| 离线可装 | 仓库 +647MB；CI 显著变慢；LFS 配额与克隆体验变差 |

**两方案下安装态都是真实文件**，均满足你的要求；差别在模型从哪来。

**验收**：安装根 `~/.agents/skills/decretum-matrix/training/laya-shiguan/models/laya-multilingual/` 存在**真实文件**；召回服务可从安装态启动；CLI/MCP 调通。

### 阶段 3 · 发布准备（本地）
1. 清理 `runs/` 大件与 `torchinductor_*` 残留。
2. 本地预跑 CI 等价门禁：`check_unified_cli`、`check_install_projection_closure`、`check_release_legal`、`check_package_privacy`、`git diff --check`。
3. 版本一致性：`VERSION` / `package.json` / `SBOM` / `EXPECTED_SBOM_NAMESPACE` 四处必须同为 beta1.1.5。
4. 构建 tagless candidate：`scripts/build_release_artifacts.py --mode candidate --json`。
5. 产出阶段回执（commit / manifest / 各门禁结果 / 索引计数）。

### 阶段 4 · GitHub 发布与 CI
1. **（需动作级授权）** push `work/laya-shiguan-training`（或经 release 分支）→ `origin`。
2. 触发并跑通 GitHub Actions：`source-contracts-{ubuntu,windows,macos}` + `source-contracts` 汇总 + `package-entrypoint`。
3. 失败则按失败层修复（不重跑已知下游失败）。

> ⚠️ 按 `decretum-release-fastpath`：「Never infer authority to add/change a remote, push, tag, open a PR, create a release, or upload an asset.」**push 与 CI 触发需要你当前的、动作级授权**——阶段 4 我不会自行启动，会在阶段 3 回执齐备后单独找你确认。

## 风险与边界

| 风险 | 处置 |
| --- | --- |
| CI 三平台可能不受支持新文件路径 | 阶段 3 本地预跑后再推；CI 失败按层修复 |
| `runs/` 1.3GB 若误入库会严重污染仓库 | `.gitignore` 已验证生效；阶段 3 再清一次 |
| 模型许可文本不完整会被法务门禁拒 | 阶段 1 验收判据即 `check_release_legal` |
| 安装态含 647MB 会让安装变慢 | 方案 A 下安装态仍是真实文件，但仓库与 CI 不受影响 |
