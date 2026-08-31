# Phase 0 Evidence — 基线清偿（M0）

> protocol_version: draft-0.1 · phase: 0 · handoff: phase-0-handoff.md
> 执行机：本地临时 git 副本（C:\Users\Administrator\a02-takeover\dm-dev）
> 基线：release/beta1.0.7 @ 2571178 + 源码收尾文档（本地提交 6391be0）；分支 release/beta1.0.8

## 1. 门禁三件套（M0 出口标准）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 源验证 | `python -B scripts/quick_validate.py .` | PASS（"Skill is valid! …"） |
| 只读契约 | `python -B scripts/check_read_only_contract.py` | ok:true（10+ 项全部通过；详见 §4） |
| 源状态预算 | `python -B scripts/check_source_state_budget.py --json` | ok:true，warnings:[] |
| 发布清单 | `python -B scripts/check_release_manifest.py --json` | ok:true，RELEASE_MANIFEST_OK，step_count=49 |

## 2. E1–E5 验收证据

### E1 beta1.0.7 基线确认 ✅
- 复核：`release/beta1.0.7` HEAD `2571178`；收尾脚本（agent_runtime_probe.py / check_court_agent_config.py / check_install_current_agent_copy.py / check_supercc_functional.py / install_current_agent_copy.py）均已提交（fc3ea9a / 2571178）。
- 锚点：VERSION=beta1.0.7；release-manifest release_label=beta1.0.7、version_core=1.0.7。
- 工作树：canonical O:\decretum-matrix 含未提交的 beta1.0.7 源码收尾文档（README.md、docs/plans/2026-08-26-…-beta1.0.7-phased-execution-plan.md、docs/wiki/Release-Notes.md）+ 未跟踪 beta1.0.8 规划文档（属预期）；本地副本已把收尾文档提交为 6391be0（rel107-final），并把 6391be0 收编进 release/beta1.0.8 基线。
- 判决：3 处未提交改动均为 beta1.0.7 收尾记录文档，与 HEAD/锚点一致，无 BLOCKED。

### E2 修复 check_read_only_contract 失败 ✅（本机全绿）
- 本机运行 `python -B scripts/check_read_only_contract.py` → ok:true（未见任务书所述 supercc_check_only mutated home/AppData/Roaming）。
- 取证（对本机与源码）：`ensure_supercc_court.py --check-only` 全程无 AppData 目录创建（唯一 mkdir L918 属 ensure_office_dossier 写路径，check-only 不触发；ensure_court_agent_config.py --check 子进程运行无副作用）；全仓唯一 "home/AppData/Roaming" 模式是 refresh_capability_registry.resolve_command（只读 exists()）与 check_install_current_agent_copy 自身的 fixture。
- 结论：任务书所述失败为原主机环境相关（外部工具二进制按 Windows roam 约定在临时 USERPROFILE 下建目录）；本机 AC 满足。建议在正式安装验收机复验一次（等发布后 1.0.8 安装时）。

### E3 重绑 skill-identity sha + 绑定断言 ✅
- `references/manifests/skill-identity.v1.json` skill_sha256：c2d21360… → `589842FD69A976ADD688EB23EE6A6078FCD6C1582E6B8B3339F2D0A2AA940A54`（SKILL.md LF 归一化）。
- `scripts/check_skill_identity.py`：新增 `_check_skill_digest_binding`（声明 sha == SKILL.md LF 归一化 sha；先 RED 复现：旧 manifest 报 SKILL_IDENTITY_DIGEST_MISMATCH，重绑后 status=PASSED）。
- 自检 `--self-test` → PASSED；（repo-control doctor 因本环境 .repo-control 不可写无法执行——见 §5）。

### E4 serve_shiguan_tree entry.id 白名单 + 落盘根校验 ✅
- `scripts/serve_shiguan_tree.py`：
  - `_upsert_entry_unlocked`：entry_id 非空时 `re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", entry_id)`，不匹配 → `ValueError("invalid_entry_id")`（Handler 映射为 HTTP 400）。
  - `write_manual_entry`：落盘前 `path.resolve().is_relative_to(manual_root().resolve())`，不满足 → `ValueError("invalid_entry_id")`。
- `scripts/check_shiguan_http.py` 新增回归：`id="..\\..\\evil"` 被拒（ValueError→400）；`id="a_b-1.json"` / `id="a_b-1"` 正常写入 manual/。先 RED（穿越被接受），修复后全绿。
- `python -B scripts/check_shiguan_http.py`（本机 loopback 服务 127.0.0.1:8765 短启后测试）→ ok:true（36 项 static 全 true + live health/state/安全头/CSRF/DNS-rebinding 全绿）；测试后已停止服务。

### E5 CLI --version ✅
- `scripts/court_cli_registry.py`：main 在 group 判定前识别 `--version`/`-V`（json/text 两态），输出 SKILL.md metadata.version（VERSION 文件兜底）并返回 0。
- `python -B scripts/court_cli.py --version` → beta1.0.7（发布升版后为 beta1.0.8），退出码 0；`-V` 同。`check_unified_cli.py` 全部 PASS（CLI_ENTRYPOINT_COVERAGE / LAZY_LOAD / LEGACY_PARITY / NPM 等 9 项）。

## 3. 变更文件清单（release/beta1.0.8）

- M scripts/check_skill_identity.py（E3 断言）
- M references/manifests/skill-identity.v1.json（E3 重绑）
- M scripts/serve_shiguan_tree.py（E4 白名单 + 落盘校验）
- M scripts/check_shiguan_http.py（E4 回归）
- M scripts/court_cli_registry.py（E5 --version）
- A docs/plans/beta1.0.8/handoffs/{README.md,phase-0-evidence.md,phase-0-handoff.md}

## 4. 只读契约明细（本机）

check_read_only_contract 本次运行：catalog_shared_state_probe、query_shiguan_index、check_import_queue、reevaluate_memory_dry_run、shiguan_web_check_only、service_daemon_check_only、autosync_check_only、obsidian_vault_dry_run、obsidian_sync_dry_run_missing_tree、supercc_check_only、supercc_watchdog_no_apply、pending_metadata_only、obsidian_sync_dry_run_existing_tree —— 全部通过且无隔离状态变异；`"ok": true`。

## 5. 环境限制说明（本机接续）

- Canonical 镜像 O:\（TRUENAS/Omina/gitmirror）对本机 git 对象写入受限（`git add` → insufficient permission；.repo-control/events 与 O:\worktrees 不可写）。因此本阶段开发落在本地 git 副本 C:\Users\Administrator\a02-takeover\dm-dev，并视为"接续临时路径"（用户已授权本地临时路径）。
- `repo-control doctor`（E3 AC 之一）与 canonical 事件写入在本机不可执行；等价替代：check_skill_identity.py PASSED + 证据本文件。需在可写权威环境补跑 doctor。
- 本机 1.0.7 安装已同步到最新 1.0.7（见 §6）。

## 6. 本机 1.0.7 更新（安装收据）

- 通过 `install_current_agent_copy`（schema court.install_current_agent_copy.result.v1）从最新 1.0.7 源（6391be0 树）更新本机：targets=[[user] .agents\skills\decretum-matrix]（.codex\skills\decretum-matrix 为指向 .agents 的 symlink，随物理库同步），projection_counts create=122/replace=79/identical=84，backup CREATED（.agents\install-backups\decretum-matrix\projection-d2ef6563…，manifest_sha256=3cec09df…，rollback_supported）。
- 安装后 SKILL.md LF sha=589842FD…（最新 1.0.7）；VERSION=beta1.0.7；install-receipts\decretum-matrix\install-0cfa81c4…json 写入（selected_roots=[.agents]）。
- 备注：skill-identity.v1.json 安装拷贝中的 skill_sha256 仍为旧值（c2d21360）——这是 1.0.7 已知问题，E3 已在 1.0.8 源码修复；1.0.8 发布安装时会随投影重绑。
- 已知非门禁项：check_active_copy_hashes.py 对含运行时史馆数据/__pycache__ 的活动副本报 extra_files（本机安装根含受保护史馆锚点与历史 pyc；该检查不属 Phase-0 门禁，属 host-data 残留，待发布期清理策略处理；四个受保护史馆锚点未动）。

## 7. 未决事项（REVIEWER 拍板）

1. Canonical O:\ 仓无法本地提交：本机产出为 git bundle/patch + 证据，需在可写权威环境应用（bundle 位于本机临时区）。
2. .zcode\skills\decretum-matrix 为 1.0.7 旧物理副本（非 junction）：策略"单一物理库 + 仅显式授权扩展目标"，未更新；是否转为 junction/清除请裁定。
3. E2 原始失败环境（原主机）建议 1.0.8 安装验收时复验。
