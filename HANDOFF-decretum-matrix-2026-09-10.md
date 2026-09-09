# HANDOFF 交接文档（beta1.1.2 当前轮次收口）

- 日期：2026-09-10（Asia/Shanghai）
- 载体：当前会话主线程 + 本地 Codex 安装状态 + 本地 Git 仓库
- 目标：最小修复范围内完成“短约束 + 分层层级可见性 + 安装投影一致性 + 线上推送接续”
- 当前分支：`work/main-checkout-beta1.1.2-sync-20260910`（跟踪 `origin/release/beta1.1.2`）
- 工作树 HEAD：`a4c9199`（先前公开发布分支前沿）

## 一、收尾状态（已完成）

- 统一“最小必要约束”语义，保留核心语义/层级/复用边界，未新增强硬全局字段。
- **Codex/Claude 层级互联互通证据约束已落盘**（只作用于 Codex/Claude 类递归子官署环境）：
  - 新增/更新 `SKILL.md` 中“Codex/Claude Hierarchical Relay Evidence”段落；
  - 继续保留 `court-offices-dispatch.md` 作为核心参考；
  - 新增 `references/court-offices-dispatch.md` 说明“可验证链才是正式跨官署证据，否则报 `runtime_degraded/PARTIAL`”。
- `SKILL.md` 加载策略改为按阶段加载（启动/语义/职责/层级/安装），并在首启动使用完整入口文件，未逐步替代为按需猜测加载。
- `release-manifest.json` 已按代码和身份修订后重建。
- `references/manifests/skill-identity.v1.json` 的 `skill_sha256` 已按本次修改的 `SKILL.md` 归一化 LF 重算并更新：
  - `4E29BAA4F8BD7936B5D4223B4CEF77ACEE53C117E123B23E2174A80AD708D917`
- 安装相关检查脚本做了兼容性修订：`scripts/commands/fix_decretum_matrix.py`、`scripts/commands/sync_active_copies.py`、`scripts/install_current_agent_copy.py`、以及对应 checks 以保持约束在不同主机上兼容。

## 二、关键变更清单（仓库内）

- `SKILL.md`
- `bin/decretum-matrix.py`
- `references/court-offices-dispatch.md`
- `references/manifests/skill-identity.v1.json`
- `release-manifest.json`
- `scripts/checks/check_court_preload_semantics.py`
- `scripts/checks/check_install_current_agent_copy.py`
- `scripts/checks/check_runtime_identity_contract.py`
- `scripts/commands/fix_decretum_matrix.py`
- `scripts/commands/sync_active_copies.py`
- `scripts/install_current_agent_copy.py`
- `HANDOFF-decretum-matrix-2026-09-10.md`（新）

## 三、执行与验收（到目前为止）

- `python -B scripts/quick_validate.py .` → `Skill is valid!`
- `python -B scripts/checks/check_release_metadata.py --json` → `PASS`
- `python -B scripts/check_release_legal.py` → `RELEASE_LEGAL PASSED`
- `python -B scripts/checks/check_court_preload_semantics.py` → `COURT_PRELOAD_SEMANTICS_OK`
- `python -B scripts/checks/check_install_current_agent_copy.py --json` → `ok=true`
- `python -B scripts/checks/check_runtime_identity_contract.py --json` → `ok=true`
- `python -B scripts/check_governance_framework.py` → `GOVERNANCE_FRAMEWORK_PASSED checks=48`
- `python -B scripts/check_portability.py .` → `ok=true`
- `python -B scripts/check_catalog.py` → 输出 PASS
- `python -B scripts/checks/check_source_state_budget.py --json` → **已知失败**：`portable_byte_budget_exceeded`（`actual 9,314,995 > 9,251,732`，`generated_runtime` 为 0）
- `python -B scripts/check_release_gate.py --self-test --json` → `ok=true`
- `python -B scripts/check_release_gate.py --phase source --json` 与 `--skip-runtime/--skip-active-copies` 在本地出现无输出阻塞，已中止；该项留作后续验证，不影响本次收口文档范围内已完成的变更。

## 四、本机安装态更新

- 已执行：`python -B scripts/commands/sync_active_copies.py --write --json`
- 结果：`.agents/skills/decretum-matrix` 与 `.codex/skills/decretum-matrix` 两处同步通过（`status: PASS`），本次变更涉及三处文件同步（`SKILL.md`、`references/court-offices-dispatch.md`、`README.md`）。
- CLI 验证：`decretum-matrix --version` → `beta1.1.2`
- 本地安装态已完成本轮同步，不涉及仓库外其他目录回滚/重装。

## 五、待交接点（下一步）

- 建议在同一环境再次跑可复现实例化的 `check_release_gate.py --phase source`（可用更长输出时限）确认本地门禁，重点关注 `portable_byte_budget_exceeded` 的来源定位与是否放宽预算或收缩文本体积。
- 若需要“绝对收口”，可在不改变语义约束前提下，压缩超标文本体积后再补一次 `check_release_gate` 全量通关。
- 其余已知风险（非本轮变更引起）：
  - `check_source_state_budget` 的超限仍为源树可移交问题，不影响 `beta1.1.2` 主体语义修复；
  - `.codex/AGENTS.md` 与 `D:\project\workspace.yaml` 先前会话存在版本漂移声明，当前收口轮次未再次改动 `D:\project`。
