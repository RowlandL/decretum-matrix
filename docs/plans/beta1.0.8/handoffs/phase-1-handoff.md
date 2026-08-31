# Phase 1 Handoff — 合同与样本（M1）

- protocol_version: draft-0.1
- phase: 1
- status: VERIFY_READY
- handoffer_session: hermes-codex-20260831 (本机接续会话，阶段 1)
- started_at: 2026-08-31T15:40:00+08:00
- finished_at: 2026-08-31T16:05:00+08:00 (approx)
- git_branch: release/beta1.0.8
- git_head_commit: 34240e4
- working_tree_clean: true（提交后）

## 1. 目标达成

- P1-1 A/B/C/D 契约文档 + manifest 投影草案：完成（draft-0.1）
- P1-2 IKU 候选 fixture：完成（3 态 NOOP/REVIEW/REPAIR_CANDIDATE）
- P1-3 taxonomy_version：完成（TAXONOMY_VERSION=2026-08-28.beta1.0.8；管道输出绑定；check 断言；9/9 golden PASS）

## 2. 变更文件清单

- A docs/plans/beta1.0.8/contracts/（contract-a|b|c|d-*.md + cli-command-surface-projection-draft.json）
- A references/fixtures/iku-candidates.json
- M references/fixtures/shiguan-lineage-taxonomy-golden.json（taxonomy_version）
- M scripts/shiguan_entry_utils.py（TAXONOMY_VERSION）
- M scripts/check_shiguan_lineage_taxonomy.py（canonical 断言）
- A docs/plans/beta1.0.8/handoffs/phase-1-evidence.md / phase-1-handoff.md / README.md（更新）

## 3. 验收命令与输出

见 phase-1-evidence.md §1–§4。

## 4. 遗留问题与风险

- P1-1 契约评审未闭环 → 下一会话先评审再进 M2。
- manifest 草案为 DRAFT_PENDING_REVIEW；P2-1 定稿以 registry 一致性为准。
- 权威仓 bundle 待用户/权威环境应用。

## 5. 未决决策（需 REVIEWER 拍板）

1. 四份契约 + manifest 草案评审结论。
2. bundle 应用节奏（Phase 0+1 合并 or 每阶段单独）。

## 6. 下阶段入口指针

- 阶段 2（M2，P2-1..P2-6）MCP 领域能力面：从 manifest 投影草案定稿开始（P2-1）。
- 恢复读取协议：计划书 §3.3（1→7）；本机 SKILL 已更新为最新 1.0.7。
- 新会话读取：本文件 + phase-1-evidence.md + 任务书阶段 2 + git log/status 一致确认。

## 7. 交接自检

- [x] phase-1-evidence.md 存在且与声明一致
- [x] 门禁输出真实（见 evidence）
- [x] git status --porcelain 提交后为空
- [x] 无 push/tag/release/remote 操作
- [x] 本阶段结尾即为手动交接点：请用户在新会话加载本文件继续
