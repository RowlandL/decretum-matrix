# Phase 2 Handoff — 通用入口适配与自身 MCP 领域能力面（M2）

- protocol_version: draft-0.1
- phase: 2
- status: VERIFY_READY
- handoffer_session: hermes-codex-20260831-2（阶段 2 接续会话，authority=super, behavior=parallel）
- started_at: 2026-08-31T17:00:00+08:00 (approx)
- finished_at: 2026-08-31T18:30:00+08:00 (approx)
- git_branch: release/beta1.0.8
- git_head_commit: 3da58a8
- working_tree_clean: true（提交后）

## 1. 目标达成

- P2-1 最终领域工具矩阵 manifest 投影：完成（load_public_tools()=12；write_manifest 生成器兼容；entrypoint/projection 同步）
- P2-2 public/domain API 与 Agent envelope：完成（4 新 + 3 复用 + domain ledger API + GBrain recall + 编号预览；24 项冒烟 PASS）
- P2-3 tools/call 审计写入：完成（三路径 journal；digest 匹配；无原文泄漏）
- P2-4 input_schema description 补全：完成（12 工具全属性 description；探针绿）
- P2-5 check_court_mcp_server 扩展：完成（29 → 58 探针全绿；45+ 出口达标）
- P2-6 官署 MCP 调用与多 skill 编排：完成（actor 审计、skill_load_record、agent-admit、index-first 探针全绿）

## 2. 变更文件清单

- M references/manifests/cli-command-surface.v1.json（12 工具投影 + description + iku entrypoint）
- M references/manifests/install-projection.v1.json（shared_agents/portable_current_tool/cli_public 同步）
- M references/manifests/source-state-budget.v1.json（max_bytes 7800000）
- A scripts/court_public_api.py 扩展（4 新函数 + 3 复用导入 + 结构校验）
- A scripts/iku_candidates.py（IKU 只读探测器，纯函数 + CLI main）
- A scripts/domain_ledger_api.py（领域账册：ACL/authority/write_set/revision/Git commit/skill 记录/GBrain/编号预览）
- M scripts/court_mcp_server.py（审计 journal + actor 注入）
- M scripts/check_court_mcp_server.py（58 探针）
- A docs/plans/beta1.0.8/handoffs/phase-2-evidence.md / phase-2-handoff.md / README.md（更新）

## 3. 验收命令与输出

见 phase-2-evidence.md §1–§7。关键：
- `python -B scripts/check_court_mcp_server.py` → ok:true（58 探针）
- `python -B scripts/quick_validate.py .` / `check_release_manifest.py --json`（ok:true, 49）/ `check_unified_cli.py`（9/9）/ `check_source_state_budget.py --json`（ok:true）/ `check_skill_identity.py`（PASSED）/ `check_governance_framework.py`（48 checks）/ `check_install_projection_closure.py`（PASS）/ `check_portability.py`（ok:true）全绿
- `check_read_only_contract.py` 红 = E2 已知环境遗留（stash 验证与本阶段无关）

## 4. 遗留问题与风险

- check_read_only_contract 本机红（E2 环境遗留，正式安装机复验）。
- 权威 O: 仓 bundle 未应用；repo-control doctor 需权威环境。
- 契约评审闭环（phase-1 §6 结论）待 REVIEWER 最终确认 M1 VERIFIED/COMPLETED；M2 同理。
- domain ledger 的 Git commit 依赖 ledger root 为 git 仓库（默认共享史馆 court-runtime）；探针在隔离 temp git 验证，生产 root 首次使用前需确认史馆 git 就绪。

## 5. 未决决策（需 REVIEWER 拍板）

1. Phase 1 契约评审结论确认（evidence §6：a/b/c 通过、d 修订 2 处、manifest 条件通过）。
2. bundle 应用节奏（Phase 0+1 合并 or 每阶段单独；现累计 Phase 0/1/2 待应用）。
3. Phase 2 出口评审：58 探针 + 12 工具矩阵 + 审计/编排探针全绿，可否转 VERIFIED/COMPLETED。

## 6. 下阶段入口指针

- 阶段 3（M3，P3-1..P3-9）分类、IKU 与 GBrain 记忆治理：从 P3-1 三层数据分离与编号生成器适配开始（本阶段已提供 domain_court_code_preview 与 taxonomy_version 基础）。
- 恢复读取协议：计划书 §3.3（1→7）；本文件 + phase-2-evidence.md + 任务书阶段 3 + git log/status 一致确认。
- 阶段 3 依赖本阶段的 iku_candidates.py（P3-4/5 在其上做 --dry-run/--apply）、domain_ledger_api.py（P3-6/8 冲突/增量复用账册）、check_court_mcp_server 探针框架（P3 探针追加）。

## 7. 交接自检

- [x] phase-2-evidence.md 存在且与声明一致
- [x] 门禁输出真实（见 evidence §7）
- [x] git status --porcelain 提交后为空
- [x] 无 push/tag/release/remote 操作（本地领先 origin 8 提交未推送）
- [x] index 空（git diff --cached 无内容）
- [x] 本阶段结尾即为手动交接点：请用户在新会话加载本文件继续
