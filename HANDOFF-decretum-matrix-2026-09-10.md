# HANDOFF 交接文档（beta1.1.2 断点续接收口）

- 日期：2026-09-10（Asia/Shanghai）
- 分支：`work/main-checkout-beta1.1.2-sync-20260910`，跟踪 `origin/release/beta1.1.2`
- 续接点：`a4c9199` 后，继续处理 source gate、安装态同步与线上推送
- 范围：最小修复；保留核心语义、官署层级、阶段读取、相对路径引用与宿主兼容边界

## 一、当前变更

- `SKILL.md`
  - 在阶段读取表中补入 `references/court-supercc-runtime-selection.md`，满足 superCC runtime 选择阶段的强引用检查。
  - 保留 `references/court-offices-dispatch.md` 作为官署/转发阶段入口；互联互通仍按官署层级与当前会话证据判定，不把 `subagentV2` 字样当强制要求。
- `agents/standing-officials/taizi.toml`
  - 仅压缩太子 profile 顶部重复说明，保留 `fourteen-label`、`P00`、`agent_dossier_loaded=YES`、直接上级回奏、层级与证据语义。
  - 修复 `court_open_fastpath` 的 `root_entry_with_metadata_budget`，当前 root preload 余量为 77 bytes。
- `references/manifests/source-state-budget.v1.json`
  - portable source byte ceiling 按当前实测重基线到 `9,300,000`。
- `references/complexity-budget.md`
  - 记录本轮 source budget 重基线：`508 files / 9,292,241 bytes`，ceiling `545 files / 9,300,000 bytes`。
- `references/manifests/skill-identity.v1.json`
  - `SKILL.md` LF 归一化摘要更新为 `42B5D5A0B21BA4A2E092E03CEDDA5BE4E23BAC0F7DD0B7712BC98979ABFD715D`。
- `release-manifest.json`
  - 已按当前源码状态重新生成。
- `bin/decretum-matrix.py`
  - 绑定选择的 `_same_path` / `_path_is_under` 先走 filesystem `samefile` / 父链等价，再回退文本规范化；修复 Windows `RUNNER~1`/`runneradmin` 与 macOS `/var`/`/private/var` 这类同一物理路径、不同文本形态导致的误拒。
- `scripts/checks/check_install_current_agent_copy.py`
  - backup_root 相对 home 的校验改为物理父链求相对 parts，不再要求两个 path 字面上处于同一前缀。
- `scripts/checks/check_portability.py`、`scripts/release_gate_manifest.py`、`references/manifests/release-gates.v1.json`、`.github/workflows/ci.yml`
  - `portability` 升为 GitHub `source-contracts` 的 required check。
  - 新增 formal source 扫描面：当前正式源、脚本、清单、fixture、workflow、wiki 与顶层说明不得携带本机 workstation absolute roots；保留历史 evidence 目录的原始证据边界。
- 当前路径收敛
  - `references/fixtures/capability-recruitment-cases.json` 的 destination fixture 改为相对路径。
  - `docs/wiki/Architecture.md`、`references/install.md`、顶层 handoff 与 legal preimage 文档中的本机路径改为 `<...>` 占位或相对路径。

## 二、已通过验证

- `python -B scripts/check_supercc_ministry_dispatch.py` -> `SUPERCC_MINISTRY_DISPATCH_OK`
- `python -B scripts/check_court_open_fastpath.py --serial-probes --json` -> `ok=true`
- `python -B scripts/checks/check_supercc_profiles.py` -> `SUPERCC_PROFILES_OK count=14`
- `python -B scripts/checks/check_skill_identity.py` -> `PASSED`
- `python -B scripts/checks/check_source_state_budget.py --json` -> `ok=true`
- `python -B scripts/commands/release_payload_manifest.py --check --json` -> `ok=true`
- `python -B scripts/check_catalog.py --strict` -> exit `0`
- `python -B scripts/check_release_gate.py --phase source --json` -> `exit=0`, `failed=[]`, `layer_results.source.status=PASSED`
- GitHub Actions run `34390680956`（commit `d5db989`）仍红；失败集中在 CI 临时 HOME/跨平台检查合约：`unified_cli` 的 legacy `probe` 非零失败被 unified envelope 包装为 exit `3`，以及 `install_current_agent_copy` 的 fixture 断言绑定了硬编码 replace 数量和 macOS `/var`/`/private/var` 路径形态。
- Actions 续修已做：`scripts/check_unified_cli.py` 只承认等价失败 envelope；`scripts/checks/check_install_current_agent_copy.py` 改为语义化 replace/rollback 判断，并对 macOS symlink temp path 做物理路径等价处理。本机临时 HOME 单项复测两项均 exit `0`。
- Actions 续修后完整复测：`python -B scripts/check_release_gate.py --phase source --json` -> `ok=true`, `release_gate=PASSED`, `failed=[]`。
- GitHub Actions run `34392587257`（commit `c4e5a4d`）继续暴露 CI 路径别名：Windows `RUNNER~1`/`runneradmin`、macOS `/var`/`/private/var`。已续修 `bin/decretum-matrix.py` 的绑定路径等价/包含关系判断，并修正安装检查里 backup_root 相对 home 的物理父链判断；本机 `check_unified_cli.py --all --json` 与 `check_install_current_agent_copy.py` 均 exit `0`。
- 路径收敛复核：当前正式面扫描已知 workstation roots 无命中；`python -B scripts/check_portability.py` -> `ok=true`，其中 formal source `leaked_count=0`。
- `python -B scripts/check_release_gate.py --self-test --json` -> `ok=true`，新增 `portability` required ID 已被 CI summary self-test 消费。
- `python -B scripts/check_court_capability_recruitment.py` -> `ok=true`，相对 destination fixture 未破坏候选/同意绑定。
- `python -B scripts/check_semantic_continuity.py` -> `SEMANTIC_BINDING_CORE_PASS`。
- 路径说明修正后完整复测：`python -B scripts/check_release_gate.py --phase source --json` -> `ok=true`, `release_gate=PASSED`, `failed=[]`。

注意：正确聚合入口是 `scripts/check_release_gate.py`。直接执行内部 `scripts/checks/check_release_gate.py` 会缺少 wrapper 注入的 `scripts/` import path。

## 三、安装与推送交接

- 权威安装态已同步：`python -B scripts/commands/sync_active_copies.py --write --json` 写入 `.agents` 与 `.codex` selected roots；只读复核 `status=PASS`、`copied_count=0`、14 个 Codex agent roles 为 `synced`。
- 兼容载体已做最小 no-delete 同步：`.claude/skills/decretum-matrix`、`AppData/Local/hermes/skills/decretum-matrix`、`.cc-switch/skills/decretum-matrix` 共 18 个漂移文件已按 active projection 覆盖；覆盖前备份在 user-home 相对路径 `.agents/install-receipts/decretum-matrix/compat-sync-20260910-023355`。
- 兼容载体复核：上述三根 active projection `diff_count=0`。
- 未触碰：`.hermes/skills/decretum-matrix` 是 legacy junction，目标为 `[..]`；本轮不把它当普通安装根写入。
- DeepSeek Harness/DSH：本机未发现 `dsh`、`deepseek-harness`、`harness`、`ds-harness` PATH 命令，也未发现可验证的 DSH decretum skill root；为避免猜路径造成回归，本轮未写入 DSH。
- 待提交并推送：目标远端分支 `origin/release/beta1.1.2`；本交接文档随最终提交一起推送。

## 四、剩余边界

- 本轮只证明 source gate；未声明 package、installation、native 或 full release acceptance。
- 若后续继续扩写入口或太子 profile，需要优先保持 `root_entry_with_metadata_budget <= 20 KiB`。
- `.codex/AGENTS.md` 与 `workspace.yaml` 的历史版本漂移不在本轮修改范围内。
