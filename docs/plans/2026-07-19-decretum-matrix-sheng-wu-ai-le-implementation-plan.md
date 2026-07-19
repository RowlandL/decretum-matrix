# Decretum Matrix《声无哀乐》Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This task is explicitly serial; do not dispatch subagents before the bounded loading smoke authorized after all source/install gates.

**Goal:** 将现有任务运行和史馆能力提升为治理无关的框架合同，使三省六部成为完整默认实现，并用一个有限替代治理场景证明可替换性与记忆连续性。

**Architecture:** 新增无持久化的治理协议模块与史馆 GBrain 召回模块。官方适配器读取现有唯一层级 manifest，现有差遣和查询入口分别委托通用引擎与 GBrain；非默认 `direct-review` manifest 只用于有限通用性验收。任务状态、语义 receipt、史馆存储和记忆裁定格式保持不变。

**Tech Stack:** Python 3 标准库、JSON manifests、现有文件型 court runtime、shared Shiguan index、仓库自带 checker/release gate。

**Commit Policy:** 任务书禁止中间提交。每项任务完成后只记录本地验证；全部阶段门、candidate、安装和最终索引门通过后才允许一次完成提交。

---

### Task 1: 固定治理协议 RED

**Files:**
- Create: `scripts/check_governance_framework.py`
- Test: `scripts/check_governance_framework.py`

- [ ] **Step 1: 写入最小失败导入与合同断言**

```python
from governance_framework import (
    DEFAULT_GOVERNANCE_ID,
    evaluate_dispatch,
    load_governance_registry,
    validate_semantic_trace,
)
from shiguan_gbrain import build_recall_context

def run_checks(root: Path) -> list[str]:
    registry = load_governance_registry(root)
    assert DEFAULT_GOVERNANCE_ID == "three-departments-six-ministries"
    assert registry["default_id"] == DEFAULT_GOVERNANCE_ID
    return ["registry_contract"]
```

- [ ] **Step 2: 运行检查并确认 RED**

Run: `python -B scripts/check_governance_framework.py --json`

Expected: non-zero，且错误明确指出 `governance_framework` 或 `shiguan_gbrain` 尚不存在。

- [ ] **Step 3: 记录 RED 证据**

保存命令、返回码和首个失败原因到阶段外部 receipt；不得 stage 或 commit。

### Task 2: 实现治理注册表与通用差遣

**Files:**
- Create: `scripts/governance_framework.py`
- Create: `references/manifests/governance-implementations.v1.json`
- Create: `references/manifests/direct-review-governance.v1.json`
- Test: `scripts/check_governance_framework.py`

- [ ] **Step 1: 建立纯数据类型和严格 token 校验**

```python
@dataclass(frozen=True)
class GovernanceImplementation:
    implementation_id: str
    version: str
    status: str
    roles: Mapping[str, str]
    capability_bindings: Mapping[str, tuple[str, ...]]
    allowed_edges: tuple[GovernanceEdge, ...]
    manifest_sha256: str

def exact_token(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or value != value.casefold():
        raise GovernanceContractError(f"invalid_{field}")
    return value
```

- [ ] **Step 2: 实现 registry 装载和唯一默认门**

注册表只接受 schema、default id 和 implementation entries。拒绝重复 id、多个默认、路径逃逸、未知 adapter、缺失七类能力绑定，以及 memory/state/evidence 指向新权威。

```python
FRAMEWORK_SERVICES = {
    "state": "court-runtime",
    "evidence": "court-runtime",
    "memory": "shiguan-gbrain",
}
REQUIRED_CAPABILITIES = {
    "intake", "interpretation", "ruling", "coordination",
    "action", "validation", "presentation",
}
```

- [ ] **Step 3: 适配现有官方 hierarchy manifest**

读取 `court-dispatch-hierarchy.v1.json` 的 `canonical_roles` 与 `allowed_edges`，使用 registry 中的 capability bindings 形成 `GovernanceImplementation`。不得在新文件复制官方 allowed edges。

- [ ] **Step 4: 实现 generic manifest 与 `direct-review`**

```json
{
  "schema": "decretum.governance.implementation.v1",
  "id": "direct-review",
  "version": "1.0.0",
  "deny_by_default": true,
  "roles": {
    "coordinator": {"direct_superior": "user"},
    "reviewer": {"direct_superior": "coordinator"},
    "executor": {"direct_superior": "coordinator"}
  },
  "allowed_edges": [
    {"edge_class": "entry", "caller": "user", "target": "coordinator", "target_direct_superior": "user"},
    {"edge_class": "review", "caller": "coordinator", "target": "reviewer", "target_direct_superior": "coordinator"},
    {"edge_class": "execution", "caller": "coordinator", "target": "executor", "target_direct_superior": "coordinator"}
  ]
}
```

- [ ] **Step 5: 实现 deny-by-default 差遣判断**

```python
def evaluate_dispatch(implementation, *, caller, target, target_direct_superior):
    for edge in implementation.allowed_edges:
        if (edge.caller, edge.target, edge.target_direct_superior) == (
            caller, target, target_direct_superior
        ):
            return GovernanceDecision(True, edge.edge_class, ())
    return GovernanceDecision(False, None, ("governance_edge_forbidden",))
```

- [ ] **Step 6: 运行治理装载与差遣 GREEN**

Run: `python -B scripts/check_governance_framework.py --json`

Expected: registry、official load、direct-review load、三条 direct-review 正向边及拒绝边通过；其余未实现检查仍保持失败。

### Task 3: 实现七类语义 trace

**Files:**
- Modify: `scripts/governance_framework.py`
- Modify: `scripts/check_governance_framework.py`

- [ ] **Step 1: 写完整正向 trace 与越权反例**

正向记录顺序固定为 latest decree fact、runtime fact、interpretation、ruling、action、validation、memory、presentation。反例至少包括：interpretation 无 fact、action 无 ruling、memory 有执行权、presentation 无 validation/ruling、actor 未绑定能力、无 controlling latest decree。

- [ ] **Step 2: 运行并确认语义 RED**

Run: `python -B scripts/check_governance_framework.py --only semantic-trace --json`

Expected: non-zero，失败于 `validate_semantic_trace` 尚未实现或未拒绝反例。

- [ ] **Step 3: 实现记录标准化与时效校验**

```python
SEMANTIC_KINDS = (
    "fact", "interpretation", "ruling", "action",
    "validation", "memory", "presentation",
)
REQUIRED_BASIS = {
    "interpretation": {"fact"},
    "ruling": {"fact", "interpretation"},
    "action": {"ruling"},
    "validation": {"action", "fact"},
    "memory": {"fact", "validation"},
    "presentation": {"ruling", "validation"},
}
```

所有 timestamp 必须带时区；`valid_until < valid_from` 拒绝。memory 与 presentation 的 `execution_authority` 必须为 false。action 的 true 只表示它仍需当前 task authority 执行，不生成新授权。

- [ ] **Step 4: 实现 actor capability 与依据关系校验**

对每个 derived kind 检查 actor 是否出现在 implementation capability binding；检查 basis id 存在且至少包含所需上游 kind。trace 必须有 `subject=latest_user_decree` 且 `authority=controlling` 的 fact。

- [ ] **Step 5: 运行官方与替代实现 trace GREEN**

Run: `python -B scripts/check_governance_framework.py --only semantic-trace --json`

Expected: 两个实现的正向 trace 通过，全部反例按稳定原因码失败。

### Task 3A: 实现请求理解充分度门

**Files:**
- Modify: `scripts/court_intake_gate.py`
- Modify: `scripts/check_court_intake_gate.py`
- Modify: `scripts/check_governance_framework.py`

- [ ] **Step 1: 写四维、95 阈值、单问题和 2–4 选项 RED**

在 `scripts/check_governance_framework.py` 构造 goal、usage scenario、key
requirements、acceptance criteria 四维 fixture，覆盖低分直接执行、多问题、单选项、
四维未清晰、复述后未确认即建任务等反例。

Run: `python -B scripts/check_governance_framework.py --only understanding --json`

Expected: 首次运行因缺少 `court.request_understanding.v1` 或相应稳定原因码而失败。

- [ ] **Step 2: 将 `court.request_understanding.v1` 作为 optional nested schema 加入历史兼容 gate**

对象固定携带 `score`、四维清晰度、`route`、单一 `question_target`、问题、0 或
2–4 个互斥选项以及 `confirmation_received`。历史 conversation gate 可不携带该
对象，避免破坏既有记录；所有新 fixture 使用同一最小 helper 生成。

- [ ] **Step 3: 让 `require_new_formal_task_gate()` 强制新正式任务达到直接执行态**

新正式任务必须同时满足 score >= 95、四维全部清晰且
`route=DIRECT_EXECUTION`。`RESTATE_CONFIRM` 只表示复述已给出、仍待用户确认，
不得创建任务；确认后才更新为 direct execution。明确且无需重复确认的初始旨意可
直接生成该完成态。

- [ ] **Step 4: 验证复述确认与 clear-request direct execution 两条达标路径**

Run: `python -B scripts/check_governance_framework.py --only understanding --json`

Run: `python -B scripts/check_court_intake_gate.py`

Expected: understanding 聚焦检查全部通过；intake 正向、反向与 confidence mutation
回归通过，且复述未确认反例稳定返回
`formal_understanding_confirmation_pending`。

### Task 4: 提升史馆为 GBrain 召回接口

**Files:**
- Create: `scripts/shiguan_gbrain.py`
- Modify: `scripts/query_shiguan_index.py`
- Modify: `scripts/check_governance_framework.py`

- [ ] **Step 1: 固定抽取前查询行为**

在检查器构造三条内存 entries，覆盖关键词权重、相同分数按时间降序、冲突与过期记录。用当前 `query_shiguan_index.score_entry/select_matches` 得到 preimage 排序。

- [ ] **Step 2: 运行 GBrain 检查并确认 RED**

Run: `python -B scripts/check_governance_framework.py --only gbrain --json`

Expected: non-zero，失败于 `shiguan_gbrain` 缺失。

- [ ] **Step 3: 搬移而非重写现有查询函数**

将 `load_entries`、`score_entry`、`select_matches` 原样移入 `shiguan_gbrain.py`。`query_shiguan_index.py` 从新模块导入这些函数，保留 CLI、compact/detail/json 输出和退出码。

- [ ] **Step 4: 实现 advisory recall envelope**

```python
return {
    "schema": "decretum.gbrain.recall.v1",
    "governance_id": governance_id,
    "current_decree_sha256": current_decree_sha256,
    "current_decree_precedence": True,
    "authority": "advisory",
    "execution_authority": False,
    "as_of": as_of,
    "matches": normalized_matches,
}
```

每个 match 保留 source、evidence、time、memory_decision、summary 与 score；根据 `valid_from`/`valid_until` 或记录 time 输出 `applicability=current|historical|undated`。若 entry 声明与最新旨意冲突，输出 `conflict=preserved`，不丢弃或提升它。

- [ ] **Step 5: 验证治理无关召回**

对 official 与 direct-review 使用相同 entries/terms/as_of；断言 match ids、顺序、summary、source 和 applicability 完全相同，仅 envelope 的 governance id 不同。

- [ ] **Step 6: 运行 GBrain 与旧 CLI GREEN**

Run: `python -B scripts/check_governance_framework.py --only gbrain --json`

Run: `python -B scripts/query_shiguan_index.py --help`

Expected: GBrain 全部通过；旧 CLI help/参数未变化。

### Task 5: 将现有官方差遣路径接入通用引擎

**Files:**
- Modify: `scripts/court_dispatch_hierarchy.py`
- Modify: `scripts/check_court_dispatch_hierarchy.py`
- Modify: `scripts/check_governance_framework.py`

- [ ] **Step 1: 写委托证明 RED**

检查器 monkeypatch `governance_framework.evaluate_dispatch`，调用 canonical `validate_dispatch_hierarchy()`，断言官方静态边经过通用函数；child office 分支不得经过 generic static edge。

- [ ] **Step 2: 运行委托检查并确认 RED**

Run: `python -B scripts/check_governance_framework.py --only official-adapter --json`

Expected: non-zero，报告 official path 未委托。

- [ ] **Step 3: 在官方 manifest 校验后建立 normalized implementation**

`court_dispatch_hierarchy.py` 继续负责官方 schema、固定角色集合、child profile 和原原因码。canonical static edge 的最后匹配改为调用从同一 validated manifest 构造的 `GovernanceImplementation`。

- [ ] **Step 4: 保持旧返回合同**

generic allowed 映射回 `DispatchHierarchyDecision.allowed/edge_class`；generic reject 映射回原 `dispatch_hierarchy_edge_forbidden`。不得新增或删除旧字段。

- [ ] **Step 5: 运行官方差遣回归**

Run: `python -B scripts/check_court_dispatch_hierarchy.py`

Run: `python -B scripts/check_governance_framework.py --only official-adapter --json`

Expected: 既有 hierarchy cases 全过，委托证明通过，child constraints 不变。

### Task 6: 纳入 source/release gates 与复杂度预算

**Files:**
- Modify: `scripts/release_gate_manifest.py`
- Modify: `references/manifests/release-gates.v1.json`
- Modify: `scripts/check_release_gate.py`
- Modify: `references/manifests/source-state-budget.v1.json`
- Modify: `release-manifest.json` (generated only)

- [ ] **Step 1: 将 `governance_framework` 加入 required source step**

命令固定为：

```json
{"name":"governance_framework","gate_class":"source","command":["$PYTHON","scripts/check_governance_framework.py","--json"],"condition":"always"}
```

放在 `court_dispatch_hierarchy` 之前，使通用协议先验、官方适配随后验。

- [ ] **Step 2: 扩展 release manifest tamper self-test**

将自测从只保护 hierarchy 抽象为保护 framework 与 hierarchy 两个必需步骤；分别验证删除、改名、换序、错误 gate class、条件化和错误命令均 fail closed。

- [ ] **Step 3: 登记新增 source line budgets**

为 `scripts/governance_framework.py`、`scripts/shiguan_gbrain.py`、`scripts/check_governance_framework.py` 设置紧约束，初始上限分别不超过 420、260、520 行；若实现更短，按实际行数向上保留不超过 10% 余量。

- [ ] **Step 4: 用临时 index 生成 release manifest**

使用临时 `GIT_INDEX_FILE` 注册全部新文件并运行 `scripts/check_release_manifest.py --write`；真实 child index 必须保持 0。

- [ ] **Step 5: 运行 gate 自测与预算**

Run: `python -B scripts/check_release_gate.py --self-test --json`

Run: `python -B scripts/check_source_state_budget.py --self-test --json`

Run: `python -B scripts/check_release_manifest.py --json`

Expected: manifest policy、source budget、tracked/generated projection 均通过。

### Task 7: 文档、迁移说明与语义清洗

**Files:**
- Modify: `docs/wiki/Architecture.md`
- Modify: `docs/wiki/Governance.md`
- Modify: `references/court-core-contract.md`
- Modify: `references/court-shiguan-memory.md`
- Modify: `references/court-offices-dispatch.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `RELEASE-LOG.md`
- Modify: `docs/logs/2026-07-19-beta1.0.0.md`

- [ ] **Step 1: 写正式架构边界**

统一使用“通用任务治理框架”“史馆 GBrain”“治理实现”“能力与运行适配层”“呈现层”。历史路径和旧名只出现在来源/兼容说明中。

- [ ] **Step 2: 写唯一权威与替换边界**

明确 registry 只选择语义实现；runtime state、evidence 和 shared Shiguan 仍是唯一服务。治理替换不得改变最新旨意、权限、安全、直接上级、pending body、writer 或发布授权。

- [ ] **Step 3: 写官方实现与 GBrain 合同**

三省六部仍是默认完整实现；史馆召回为 advisory，不取得执行权；memory decision 和 reevaluation 保留原门下裁定流程。

- [ ] **Step 4: 更新 beta1 release surfaces**

记录框架协议、GBrain、官方适配、direct-review 验收和无持久化迁移；不得宣称外部发布、tag、npm publish 或 Office Pack 已完成。

- [ ] **Step 5: 运行语义清洗检查**

Run: `rg -n "TBD|TODO|temporary workaround|临时凑合|beta0\.5\.14|SECOND_(STATE|LEDGER|MEMORY)" README.md docs/wiki references/court-*.md docs/logs/2026-07-19-beta1.0.0.md`

Expected: 无 placeholder、禁用中间版本或第二权威措辞；历史引用必须带兼容/来源语境。

### Task 8: 串行 source acceptance

**Files:**
- Verify only

- [ ] **Step 1: 运行聚焦检查**

Run: `python -B scripts/check_governance_framework.py --json`

Run: `python -B scripts/check_court_dispatch_hierarchy.py`

Run: `python -B scripts/check_semantic_continuity.py`

Run: `python -B scripts/check_court_result_semantics.py`

- [ ] **Step 2: 运行 privacy/legal/package source checks**

Run: `python -B scripts/check_package_privacy.py -q`

Run: `python -B scripts/check_release_legal.py --json`

Run: `python -B scripts/release_payload_manifest.py --self-test --check --json`

- [ ] **Step 3: 运行完整 source gate**

Run: `python -B scripts/check_release_gate.py --phase pre-install --json`

Expected: 所有 source steps 通过；在最终 commit/candidate 之前，仅 `package_validation` 因未提供包而保持任务书允许的 deferred/not-run 状态。

- [ ] **Step 4: 核验 Git 边界**

Run: `git diff --cached --quiet`

Expected: child index 0；root index 0；root dirty status hash 与激活时一致；无 `release/beta0.5.14`。

### Task 9: 最终单提交、candidate、安装与结项

**Files:**
- Modify: `release-manifest.json` (generated final projection)
- Create outside repository: final-stage receipts under `.repo-control/evidence/...`

- [ ] **Step 1: 最终预提交检查**

确认 A-G、semantic cleanliness、source gates、pending-body/no-office-pack boundaries 全部通过。使用真实 index stage 全部目标文件并再次生成/验证 manifest；不包含 root dirty 或 host-local Shiguan bodies。

- [ ] **Step 2: 创建唯一完成提交**

提交信息：`feat: complete beta1.0.0 governance architecture`

提交后 child clean/index 0，branch 仍为 `release/beta1.0.0`。不得 push/tag/release/publish。

- [ ] **Step 3: 从 accepted commit 生成唯一 candidate**

Run: `python -B scripts/build_release_artifacts.py --json`

Expected: artifact identity `decretum-matrix-beta1.0.0.zip`，embedded manifest 与 committed tree 一致。

- [ ] **Step 4: 运行 package + install gates**

Run: `python -B scripts/check_release_gate.py --phase pre-install --package <candidate> --json`

按 release-fastpath 将 candidate 安装到当前工具受控根，随后运行 post-install/source-install parity、skill identity、active-copy hashes、Shiguan no-body-read 和 rollback/recovery probes。

- [ ] **Step 5: 运行唯一允许的小规模并行加载 smoke**

仅在 source/install 全过后，用有界少量并发装载 official 与 direct-review manifests、同一 GBrain 元数据 fixture 和只读 CLI help。不得并行修复、写史馆正文或写 Git。

- [ ] **Step 6: 写完整史馆结诏与项目 receipt**

记录 A-G、版本、commit、candidate hash、安装根/hash、source/install counts、替代实现证据、GBrain 连续性、semantic cleanliness、root/child index、root dirty preimage、pending_body_access=NO、Office Pack deferred、外部发布未授权、`NEXT_MAJOR_STAGE=NONE`。

- [ ] **Step 7: 最终门**

最终 receipt 必须给出：

```text
SEMANTIC_CLEANLINESS_GATE=PASS
SHENG_WU_AI_LE_FINAL_STAGE=PASS
PROJECT_FINAL_CLOSEOUT=PASS
NEXT_MAJOR_STAGE=NONE
```

## Self-Review

- Spec coverage：A/B 由架构设计和 Tasks 1-3 覆盖；C 由 GBrain 与通用 trace 覆盖；D 由 official adapter 与既有全量回归覆盖；E 由调用点下沉和文档去重覆盖；F 由 direct-review + shared GBrain 覆盖；G 由语义清洗、release/install/史馆收口覆盖。
- Placeholder scan：计划不含 `TBD`、`TODO`、未定义的“后续处理”或无测试细节的步骤。
- Type consistency：`GovernanceImplementation`、`GovernanceDecision`、registry schema、semantic record schema 与 GBrain recall schema 在所有任务中使用同一命名。
- Scope：无第二持久化、无动态插件、无外部发布、无 Office Pack、无 pending body 读取。
