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

## 6. 契约评审记录（2026-08-31，HANDOFFEE 代办评审；最终闭环待 REVIEWER 确认）

> 评审对象：contracts/contract-a|b|c|d-*.md + cli-command-surface-projection-draft.json。
> 评审基线：devspec §3.2–3.6 + 任务书 P1-1 验收 + court_public_registry.py 契约 + 既有 manifest 投影样例。

| 对象 | 结论 | 说明 |
| --- | --- | --- |
| contract-a-iku-candidates.md | 通过（附 2 注记） | 字段表与 devspec A1 输出一致；三态语义与 fixture 对齐；MCP 永不写入 ✅。注记①：placeholder_kind 检测规则以 fixture 为准（IKU 字样→IKU；"待 archive_checkpoint 生成"/"占位符由 archive_checkpoint 自动回填"→PENDING_GENERATED/PENDING_REFILL）；注记②：fixture 提供 fragment 明文，输出契约用 fragment_sha256，P2-2 实现时哈希映射。 |
| contract-b-lineage-taxonomy.md | 通过（附 1 注记） | 三层分离/版本化分类/正 margin 规则与 devspec B 一致；taxonomy_version 已落地（P1-3）。注记：classification_confidence 取值域（建议 0..1）留阶段 3 实现时冻结。 |
| contract-c-codex-host-proof.md | 通过 | host probe 六字段与 devspec C1 一致；路由契（YES+host_proof_sha256 / 回退 inherit+FAILED）正确；验收指针指向阶段 4 ✅。 |
| contract-d-mcp-domain.md | **需修订（2 处，已修订）** | ①§1 side_effect 枚举含 write/request_dependent 与 registry 硬约束冲突（court_public_registry.py:78 强制 read_only）→ 修订为：本版本 MCP 投影全部 read_only；领域化 Create/Read/Update 由统一 CLI/主动 CLI 受权路径承担（与 A2 能力预留一致），MCP 不投影写工具。②§1 工具矩阵补"required/嵌套 closed"定稿要求（dispatch_plan_validate.entries 与 entries_query.query 须 required；entries.items 须 additionalProperties:false）。 |
| cli-command-surface-projection-draft.json | 通过（条件：按定稿要求合并） | JSON 语法 ✅；4 工具全部 read_only ✅、closed schema ✅、public_api 指向待实现函数名 ✅；status 从 DRAFT_PENDING_REVIEW 转入定稿条件（P2-1）：required 补全 + 合并进 cli-command-surface.v1.json entries + registry 加载冒烟。 |

评审结论：四份契约方向一致、无契约间冲突；contract-d 2 处修订已回写契约文档；manifest 草案按定稿条件进入 P2-1。待 REVIEWER 确认后 M1 转 VERIFIED/COMPLETED。
