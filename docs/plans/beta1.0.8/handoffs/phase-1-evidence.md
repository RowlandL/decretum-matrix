# Phase 1 Evidence — 合同与样本（M1）

> protocol_version: draft-0.1 · phase: 1 · branch: release/beta1.0.8（本地副本）

## 1. P1-1 契约文档与 schema 定稿（draft 提交）

- docs/plans/beta1.0.8/contracts/contract-a-iku-candidates.md（FR-A：候选字段/三态语义/MCP 边界/隐私约束）
- docs/plans/beta1.0.8/contracts/contract-b-lineage-taxonomy.md（FR-B：三层数据分离/版本化分类合同/margin 与否定与 tie/unknown/conflict/review 规则/验证集指针）
- docs/plans/beta1.0.8/contracts/contract-c-codex-host-proof.md（FR-C：host probe 字段表/路由契约/回退状态）
- docs/plans/beta1.0.8/contracts/contract-d-mcp-domain.md（FR-D：工具矩阵 manifest 契约/审计/账册/能力索引/GBrain/非核心边界）
- docs/plans/beta1.0.8/contracts/cli-command-surface-projection-draft.json（manifest 投影草案：4 工具，均含 command_id/api/closed input_schema/side_effect/receipt_schema/agent_envelope；JSON 校验通过）
- 评审状态：待 REVIEWER 闭环（本会话不代行门下复核）。

## 2. P1-2 IKU 候选格式定稿

- references/fixtures/iku-candidates.json：schema court.iku_candidates_fixture.v1；3 态样本
  NOOP（非编号字段）/ REVIEW（缺 receipt 或来源冲突）/ REPAIR_CANDIDATE（安全回填）；
  字段与 FR-A1 输出契约一致（record_path/record_id/field/fragment_sha256/placeholder_kind/
  nearest_court_code/nearest_lineage/receipt_hint/suggested_action/reason）。
- 校验：json.loads 语法通过；三态枚举覆盖断言通过。

## 3. P1-3 taxonomy_version 引入

- scripts/shiguan_entry_utils.py：新增 TAXONOMY_VERSION = "2026-08-28.beta1.0.8"；
  CONTENT_TAXONOMY_VERSION = TAXONOMY_VERSION（既有引用兼容）；分类管道输出绑定新值。
- references/fixtures/shiguan-lineage-taxonomy-golden.json：taxonomy_version v1 → 2026-08-28.beta1.0.8（9 例 golden 不变）。
- scripts/check_shiguan_lineage_taxonomy.py：新增 canonical 断言（golden 版本 == lineage.TAXONOMY_VERSION）。
- 结果：SHIGUAN_LINEAGE_TAXONOMY=PASS（9/9 + 版本绑定）。

## 4. 回归快照（本机）

- python -B scripts/quick_validate.py . → PASS
- python -B scripts/check_source_state_budget.py --json → ok:true, warnings:[]
- python -B scripts/check_read_only_contract.py → ok:true
- python -B scripts/check_release_manifest.py --json → ok:true（step_count=49）
- python -B scripts/check_unified_cli.py → 9/9 PASS
- python -B scripts/check_skill_identity.py → PASSED

## 5. 环境限制（同 Phase 0）

- 本地副本开发；权威 O: 仓待 bundle 应用。
- repo-control doctor 需权威环境补跑。
