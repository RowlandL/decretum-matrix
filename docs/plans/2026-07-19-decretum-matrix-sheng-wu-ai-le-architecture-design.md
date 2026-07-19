# Decretum Matrix《声无哀乐》架构设计

## 状态与输入

- 阶段：`SHENG_WU_AI_LE_FINAL_STAGE`
- 目标版本：`beta1.0.0`
- 唯一输入基线：A02 accepted source 与 `release/beta1.0.0`
- 设计原则：事实与解释分离；框架承载治理而不垄断治理语义；解释、裁定和记忆都保留主体、依据、范围与时效。
- 硬边界：不建立第二状态机、第二账本、第二记忆权威或第二执行权威；不读取 pending body；不改变默认三省六部核心行为。

## 完成态职责调查

| 边界 | 现有权威与实现 | 本阶段职责 | 不得取得的权力 |
| --- | --- | --- | --- |
| 通用任务治理框架 | `court_runtime.py`、`court_semantic_continuity.py`、operation journal、release/install gates | 任务接收、语义绑定、生命周期、差遣协议、证据、验收、暂停、恢复、回放、治理实现选择 | 不固化某一套官署名称、表达或历史记忆为唯一任务语义 |
| 史馆 GBrain | shared Shiguan root、`query_shiguan_index.py`、`memory_decision.py`、`reevaluate_memory_decisions.py` | 经历实录、元数据召回、长期记忆候选、冲突保留、时效判断、再裁定与来源追踪 | 不取得当前任务执行权；不覆盖最新用户旨意；不复制原生私有正文 |
| 三省六部官方治理实现 | `court-dispatch-hierarchy.v1.json`、standing profiles、office dossiers、governing references | 默认治理语义、角色层级、会审、回奏、差遣、复核和古制表达 | 不成为框架状态、证据或记忆存储的第二权威 |
| 能力与运行适配层 | Codex/Hermes/CLI adapters、superCC、skills/MCP/scripts | 将治理实现的有界差遣映射到可用运行载体并回传结构化结果 | 不改变治理层级，不自行授予权限，不生成第二语义胶囊 |
| 呈现层 | CLI、用户侧短结诏、史馆 Web/Obsidian 派生视图 | 按治理实现渲染用户语言与证据摘要 | 不把展示文本反向当作事实、裁定或任务状态 |

不可分离的硬性约束：最新用户旨意优先；单 writer；直接上级关系；结构化语义胶囊和 receipt；证据绑定；pending body fail-closed；共享史馆唯一写入根；root/child 仓隔离；发布外部动作单独授权。

## 方案比较

### 方案 A：小型协议层并复用现有权威（采用）

新增纯函数治理协议与史馆召回接口。三省六部通过适配器读取既有唯一层级 manifest；现有差遣校验委托通用引擎完成静态边验证。史馆查询 CLI 委托 GBrain 接口完成召回。增加一个非默认的直接复核实现，仅用于证明同一框架、同一史馆和同一能力边界可承载不同治理语义。

优点：实际进入生产调用路径；没有第二状态机或持久化；默认行为不变；替代场景可机器验证。代价：新增两个小模块、两个 manifest 和一个完整检查器。

### 方案 B：只写架构文档（拒绝）

文档可以描述边界，但不能证明框架脱离三省六部名称仍可装载、差遣和使用史馆，也不能防止后续代码重新耦合。

### 方案 C：重写 `court_runtime.py` 并抽取全部官署逻辑（拒绝）

这会扩大回归面，容易形成并行状态模型，也违背本阶段“保持 A02 核心行为”和有限通用性的约束。

## 目标结构

```text
current task authority and runtime state
                |
                v
scripts/governance_framework.py
  - registry/implementation validation
  - generic dispatch-edge validation
  - seven-kind semantic trace validation
                |
        +-------+------------------+
        |                          |
        v                          v
official court adapter       direct-review reference
existing hierarchy manifest  generic implementation manifest
        |
        v
existing runtime adapters and result envelopes

scripts/shiguan_gbrain.py
  - metadata-first recall
  - source/scope/time/conflict projection
  - advisory-only authority
        |
        v
existing shared Shiguan index and memory-decision tools
```

## 治理实现合同

注册表 schema 为 `decretum.governance.registry.v1`。每个条目必须声明：

- 稳定 `id`、显示名、版本、状态和适配器类型；
- 唯一 manifest 路径；
- `intake`、`interpretation`、`ruling`、`coordination`、`action`、`validation`、`presentation` 的角色绑定；
- 框架服务绑定，其中 memory 必须是 `shiguan-gbrain`，state/evidence 必须继续指向现有 runtime；
- 是否为默认实现。注册表必须恰有一个默认实现。

官方条目不复制层级边。其 `adapter=court_dispatch_hierarchy`，角色和边从 `court-dispatch-hierarchy.v1.json` 读取，注册表只补充通用能力到官方角色的映射。

替代条目 `direct-review` 使用通用 manifest：`coordinator` 接收、解释、协调和呈现；`reviewer` 裁定与验证；`executor` 行动。它不是默认实现，不改变 `$decretum-matrix` 的默认官署语义，也不提供远程插件发现、动态代码加载或市场能力。

通用差遣结果只回答：实现身份、调用者、目标、直接上级、边类别、允许/拒绝和原因码。它不写任务状态，不启动 agente，不授予工具权限。

## 七类语义关系

通用记录 schema 为 `decretum.semantic.record.v1`，只在既有任务/证据记录之上提供可验证关系，不成为新账本。记录具有：

- `record_id`、`kind`、`subject`、`actor`；
- `basis`（同一 trace 中的上游记录 id）；
- `scope`、`valid_from`、可选 `valid_until`；
- `content_sha256`、`governance_id`；
- `execution_authority`，仅当前任务权威下的 action 可为 true。

关系约束：

| kind | 必需依据 | 主体约束 |
| --- | --- | --- |
| `fact` | 可为空或指向外部证据摘要 | 不由治理解释冒充；不得取得执行权 |
| `interpretation` | 至少一个 fact | actor 绑定 interpretation 能力 |
| `ruling` | fact 或 interpretation | actor 绑定 ruling 能力 |
| `action` | 至少一个 ruling | actor 绑定 action 能力；执行仍受当前任务权威控制 |
| `validation` | action 与 fact | actor 绑定 validation 能力 |
| `memory` | fact 或 validation | actor 固定为 `shiguan-gbrain`；永远无执行权 |
| `presentation` | ruling 或 validation | actor 绑定 presentation 能力；永远无执行权 |

trace 必须包含控制性的最新用户旨意 fact。任何 memory 与该 fact 冲突时保留来源并标记冲突，不得提升权威；过期记录仍可召回，但必须携带时效状态。

## 理解充分度门

`court.request_understanding.v1` 作为现有 conversation gate 的嵌套纯合同，评估
goal、usage scenario、key requirements 与 acceptance criteria。历史 task 可继续
读取缺少该字段的 v1 gate；所有新正式任务通过 `require_new_formal_task_gate()`
时必须携带 score >= 95 且 `route=DIRECT_EXECUTION` 的 assessment。低于阈值只
允许一个问题，可附 2–4 个选项；`RESTATE_CONFIRM` 仍是等待用户确认的前置态，
确认后才能更新为 direct execution。初始旨意清楚时可直接进入该完成态。

## 史馆 GBrain 合同

`scripts/shiguan_gbrain.py` 复用现有 `shiguan-index.jsonl` 和 `shiguan_entry_utils.enrich_entry()`，不创建新的存储。公共接口：

```python
load_entries(path: Path | None = None) -> list[dict[str, object]]
score_entry(entry: dict[str, object], terms: list[str]) -> int
select_matches(entries: list[dict[str, object]], terms: list[str]) -> list[dict[str, object]]
build_recall_context(
    entries: list[dict[str, object]],
    terms: list[str],
    *,
    governance_id: str,
    current_decree_sha256: str,
    as_of: str,
    limit: int = 5,
) -> dict[str, object]
```

召回 envelope 为 `decretum.gbrain.recall.v1`，固定：

- `authority=advisory`；
- `execution_authority=false`；
- `current_decree_precedence=true`；
- 每个候选保留 source、证据、记录时间、适用状态和原 memory decision；
- 同一候选可被不同治理实现召回，结果正文与排序不因治理名称改变。

`query_shiguan_index.py` 只负责参数与呈现，装载、评分和选择下沉到 GBrain。`memory_decision.py` 继续写候选，`reevaluate_memory_decisions.py` 继续生成不覆盖历史的再裁定报告。

## 迁移与兼容

1. 先以失败检查固定注册表、替代实现、七类 trace、GBrain 权限和现有调用路径要求。
2. 新增协议模块和 manifests，不改任何持久化格式。
3. `court_dispatch_hierarchy.py` 仅把 canonical static edge 判定委托通用引擎；child-office 约束、原因码和返回结构保持原样。
4. `query_shiguan_index.py` 改为导入 GBrain 的同名函数；CLI 参数和输出保持原样。
5. 将新检查器纳入 release source gate，并更新 source budget、release manifest 和文档。
6. 用官方与 direct-review 两个实现跑同一 trace 与同一 GBrain 召回；再运行全部既有 source gates。
7. 只在最终完成门通过后生成一次 candidate、进行本机安装验证并提交一次。

无需迁移现有 runtime task、event、semantic receipt、Shiguan archive、memory decision、office profile 或历史证据。默认治理 id 在未显式选择时固定为官方实现。

## 验收映射

| 任务书要求 | 机器证据 |
| --- | --- |
| 框架不依赖三省六部名称才能运行 | `direct-review` 无官署名称仍通过装载、差遣与 trace |
| 史馆跨治理实现连续 | 两个治理 id 对同一 entries 得到相同候选顺序和摘要 |
| 三省六部完整默认且独立 | 默认注册表指向唯一既有 hierarchy manifest；既有 hierarchy/runtime tests 全过 |
| 七类边界清楚可追溯 | trace validator 正向链通过，缺依据、越权 actor、memory 执行权均失败 |
| 最新旨意高于记忆 | recall 固定 advisory/no-execution/current-decree-precedence，冲突测试通过 |
| 无第二权威 | 无新持久化路径；manifest framework services 指回现有 runtime 与 shared Shiguan |
| 有限通用性 | 仅一个本地 reference implementation；无动态代码、网络发现或插件市场 |
| 历史连续 | 原 task/event/receipt/index schema 不变，旧 CLI 与全量 source gate 通过 |

## 风险与回滚

- 风险：官方适配与既有 manifest 漂移。控制：运行时读取同一 manifest，禁止复制边；hash 随结果返回。
- 风险：GBrain 抽取改变查询排序。控制：搬移原函数实现并用固定 entries 比较抽取前后结果。
- 风险：通用合同被误当成第二任务账本。控制：模块纯函数、无 write API、无默认存储路径；文档和检查器均拒绝持久化权威声明。
- 回滚：移除两个纯函数模块与 reference manifests，恢复两个调用点即可；既有任务、史馆和安装数据无需迁移。
