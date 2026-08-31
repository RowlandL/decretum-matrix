# Phase 0 Handoff — 基线清偿（M0）

- protocol_version: draft-0.1
- phase: 0
- status: VERIFY_READY
- handoffer_session: hermes-codex-20260831 (本机接续会话)
- started_at: 2026-08-31T14:45:00+08:00
- finished_at: 2026-08-31T15:30:00+08:00 (approx)
- git_branch: release/beta1.0.8
- git_head_commit: b2de3710d11a37a8eff6a8b8bec384626faed5e2
- working_tree_clean: true（docs/plans/beta1.0.8/handoffs 本系列除外；提交后全空）

## 1. 目标达成
- E1 beta1.0.7 基线确认：完成（HEAD/锚点/脚本收尾核对；收尾文档评价保留）
- E2 check_read_only_contract：本机 ok:true（原始失败环境相关，见 evidence §4/§7）
- E3 skill-identity 重绑 + 绑定断言：完成（check_skill_identity.py PASSED + 自检 PASSED）
- E4 serve_shiguan_tree 白名单 + 落盘校验 + HTTP 回归：完成（check_shiguan_http.py ok:true，含本机 live 短启校验）
- E5 CLI --version：完成（--version/-V 输出 beta1.0.7，退出码 0）

## 2. 变更文件清单
- M scripts/check_skill_identity.py（E3）
- M references/manifests/skill-identity.v1.json（E3）
- M scripts/serve_shiguan_tree.py（E4）
- M scripts/check_shiguan_http.py（E4）
- M scripts/court_cli_registry.py（E5）
- A docs/plans/beta1.0.8/handoffs/（本文件；README.md；phase-0-evidence.md）

## 3. 验收命令与输出
见 phase-0-evidence.md §1/§2（quick_validate PASS；read_only ok:true；source_budget ok:true；release_manifest ok:true steps=49；skill_identity PASSED；shiguan_http ok:true；unified_cli 9/9 PASS）。

## 4. 遗留问题与风险
- canonical O: 仓本机不可提交（git 对象写受限）；本机为本地副本，产出需 bundle/patch 应用到权威仓库（R-8 相关）。
- .zcode 旧物理副本未升级（策略：仅显式目标）。
- 本机安装根存在非投影 host-data 残留（shiguan 运行时数据/历史 pyc）→ check_active_copy_hashes extra_files（非 Phase-0 门禁）。

## 5. 未决决策（需 REVIEWER 拍板）
1. bundle 应用的权威时机/账号；
2. .zcode 副本处置；
3. E2 原主机复验时机。

## 6. 下阶段入口指针
- 计划书：docs/plans/2026-08-28-decretum-matrix-beta1.0.8-execution-plan.md §3.3（Resume Protocol）
- 任务书：docs/plans/2026-08-28-decretum-matrix-beta1.0.8-task-book.md §3 阶段 1（P1-1 契约文档与 schema 定稿、P1-2 IKU 候选、P1-3 taxonomy_version）

## 7. 交接自检
- [x] phase-0-evidence.md 存在且与声明一致
- [x] git status --porcelain 提交后为空
- [x] 门禁三件套真实输出见 evidence
- [x] 无 push/tag/release/remote 操作
- [x] 本机 1.0.7 安装已更新到最新 1.0.7（receipt 见 evidence §6）
