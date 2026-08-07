# Decretum Matrix beta1.0.6 执行书

## 1. 执行身份

- 状态：`HOST_NATIVE_DISPATCH_PROVEN / GREEN_B_READY`，Stage 3 GREEN-A 纯层已通过；Entry 0014 的 host blocker 已由 Entry 0015 纠正，GREEN-B 继续在同一 child worktree 与 bounded write set 下推进。
- 当前唯一游标：`stage-3/result-recovery-chain`。
- 中书计划书：`docs/plans/2026-08-03-decretum-matrix-beta1.0.6-remediation-plan.md`。
- 本执行书：`docs/plans/2026-08-03-decretum-matrix-beta1.0.6-execution-book.md`。
- 阶段日志：`docs/logs/2026-08-03-beta1.0.6.md`。
- 工作树：`D:/project/worktrees/decretum-matrix/beta106-local-stage-019fb7f5`。
- 分支：`release/beta1.0.6`；发布基线：`release/beta1.0.5@40ba6c4`。
- 治理 skill：每个附着到 `decretum-matrix` 的任务和官署在实质工作前，必须完整读取 `C:/Users/32893/.agents/skills/decretum-matrix/SKILL.md` 及本官署 profile/dossier。

本书只规定 beta1.0.6 的执行顺序、证据门和停止条件。它不单独证明产品能力，不替代中书计划书、门下裁定、史馆 receipt 或 workspace capability evidence。

## 2. 固定执行循环

每个阶段必须完整执行以下循环，顺序不得省略或倒置：

```text
P00恢复核验
  -> 中书拟制
  -> 门下审核
  -> 尚书派部执行
  -> 聚焦验证
  -> 门下验收
  -> log回写
  -> 阶段游标推进 / STOP
```

循环规则：

1. `P00恢复核验` 必须绑定当前计划书、执行书、阶段 log、游标、语义 capsule/receipt、authority 与 hierarchy；旧线程、摘要或 handoff 不能自行产生新执行权。
2. 三省链路优先于普通并行便利：太子只调三省；尚书只调六部；六部只调本部工坊/工匠。错误上级产生的结果不得直接集成，必须进入合法的结果恢复链。
3. 中书给出本阶段目标、非目标、验收和停止门；门下明确 `APPROVE | RETURN | REJECT` 后，尚书才可授予 bounded write set。
4. 尚书按依赖串行共享写入，可并行派发独立只读审查；每项差遣必须有 direct superior、路径边界、证据、停止条件和回奏路径。
5. 聚焦验证先于全量门。测试失败、证据不全、作用域扩张或索引污染时，本阶段立即 `STOP`，游标不得前移。
6. 门下验收只接受当前代码、测试输出、Git 状态和绑定 receipt；计划文字、脚本名称或 `ok` 回显不构成验收。
7. 每轮无论通过、退回或停止，都向 append-only 阶段 log 追加记录；不得回写或抹除旧条目。

## 3. 控制面硬门

- 所有 Git/工作树选择以 `D:/project/workspace.yaml` 为准；根仓与子仓保持隔离。
- 修改前必须由 `repo-control` 或等价受管流程确认当前 child worktree、分支、HEAD 和阶段 write set。
- 每个阶段开始和交接时，根索引与 child 索引都必须为空。既有根工作树和 child 工作树脏内容必须保留，不能借本阶段清理、重置或混入提交。
- 共享文件写入串行；只读审查可以并行。任何官署不得自行扩大 write set。
- 阶段失败、超时、进程中断或证据不完整时，记录当前 cursor、已完成命令、首错与下一条精确命令，然后 `STOP`。
- 每个阶段完成后的交接载体固定为本机 `D:\project` 下的新 local conversation task（`environment=local`）；禁止把阶段交接实现为 worktree task，禁止创建/物化/挂载新的 root 或 child worktree、分支或 attached mapping。新对话只接收有界 handoff packet，并继续使用本执行书绑定的现有 child worktree、branch、HEAD、P00 capsule、semantic receipt 和 `plan_cursor`。
- 阶段完成、门下复核、append-only log 回写和新 conversation task 创建必须按此顺序发生；新 conversation task 不产生第二执行权或第二语义权威。local conversation 创建失败时保持当前阶段 `handoff_or_pause` 并停止，不能用新工作树替代。
- 禁止在未完成本书全部本地验收前安装、同步 active copies、构建候选包、发布、push、tag、PR、GitHub Release、upload 或 npm publish。
- “安装版缺少 shard”保留为后续独立 P0 阶段；不得用当前源码恢复链的完成状态覆盖或降级该问题。

### 3.1 辅助模型工具授权（2026-08-06 用户补充旨意）

- QoderCLI（Qwen3.8-Max/DeepSeek-V4-Pro/DeepSeek-V4-Flash）、Hermes CLI（deepseek-chat/deepseek-reasoner/deepseek-v4-pro/deepseek-v4-flash）与 squad 协作，用途限只读辅助审查，输出仅 advisory。
- 辅助工具不授予写权与回奏权：不替代官署履职与派遣证据，输出不构成验收依据，不参与任何 write set。

## 4. 当前已建立的恢复基线

以下均为当前工作树的本地命令证据；它们只证明对应门已通过，不代表 beta1.0.6 完成或可发布：

| 门 | 命令 | 当前结果 |
| --- | --- | --- |
| hierarchy | `python -B scripts/check_court_dispatch_hierarchy.py` | `PASSED`; 29 fixtures、58 adapter evaluations、6 个 invalid manifests 全部拒绝 |
| P00 | `python -B scripts/check_p00_semantic_dispatch_context.py` | `PASSED`; single capsule 接受，second capsule authority 拒绝 |
| dispatch policy | `python -B scripts/check_court_dispatch_policy.py` | exit `0` |
| assignment binding | `python -B scripts/check_court_office_assignment_binding.py` | exit `0`; `COURT_OFFICE_ASSIGNMENT_BINDING_OK` |

附加基线：

- child-profile hierarchy required fields 已对齐为六个 digest：`profile_sha256`、`dossier_sha256`、`skill_sha256`、`dispatch_context_packet_sha256`、`semantic_receipt_sha256`、`invariant_capsule_sha256`；不得伪造 packet/capsule identity。
- JSON CLI lifecycle fixture 已通过现有 bridge mint/validate 路径生成合法 native-host spawn receipt，未放宽生产门。
- `python -B scripts/check_court_agent_lifecycle.py` 已输出 `COURT_AGENT_LIFECYCLE_OK`。
- `python -B scripts/check_court_runtime.py` 已输出 `COURT_RUNTIME_SELF_TEST_OK`。
- 上述改动仍须在后续阶段完成最终 diff、全量门、门下验收与提交边界审查。

## 5. Stage 3 / `stage-3/result-recovery-chain`

### 5.1 不可变来源 core 与独立 recovery head

错误层级或陈旧绑定结果不再“隔离即丢弃”，也不得通过改写身份直接集成。Stage 3 固定为两条互不混写的链：

```text
source transaction:
RESULT_MISMATCH -> QUARANTINE_CORE_COMMITTED + SOURCE_TERMINAL_CLOSED

recovery head:
REVIEW_PENDING -> READY_FOR_HANDOFF | REJECTED -> HANDED_OFF -> CONSUMED
```

- 来源写入 exact-schema `court.office.result_quarantine.v2`。core 至少绑定 `quarantine_id`、pre-adapt `payload_sha256`、task/semantic/checkpoint/dispatch/attempt/instance/carrier/agent/role/superior/worktree/write-set、固定 reason、source terminal fields、deterministic event 和 `core_sha256`；未知字段拒绝。
- quarantine core 一经提交永不修改，不追加 review、target、handoff 或 consume 字段。相同 source/payload/reasons 重放只返回原 core、原事件和原 digest。
- recovery 状态只存在于独立 append-only `court.office.result_recovery_head.v1` 历史；每个 head 绑定 `previous_head_sha256`、单调 revision、state、projection/target/receipt digests、operation/event 和 `head_sha256`，不得原地更新旧 head。
- 每次转换在同一 runtime lock 内校验 `expected_task_revision + expected_recovery_revision + expected_head_sha256`。`REJECTED`、`CONSUMED` 为终态。

### 5.2 source 精确终态与 writer claim

quarantine core 成功提交的同一 transaction 必须把来源实例固定为：

```text
status=failed
final_status=failed
release_status=closed
result_state=QUARANTINED
failure_kind=result_binding_quarantine
office_execution_ready=false
finished_at=<transaction time>
closed_at=<transaction time>
```

- source 此后不得 report、follow-up、finish、reuse、wake、reopen 或复活；恢复工作只能交给一个不同的合法 target 实例。
- `_active_office_write_claims` 必须显式排除 terminal status/final_status/release_status 以及 `result_state=QUARANTINED` 的来源，使 writer claim 在同一 transaction 后立即释放。
- 任一 source 后续动作被拒绝时，task、event、operation journal 和 receipt 字节必须保持不变。

### 5.3 source hash 与 result exact whitelist

- `source_payload_sha256` 必须在 `_adapt_office_result_envelope` 之前，对原始请求 JSON object 的 canonical form 计算；键序或 JSON 空白不影响 digest，但任何原始键值差异都必须改变 digest。原对象只在内存中短暂存在，不能进入 ledger、event、receipt、日志或异常文本。
- 适配/规范化后的 digest 使用独立字段名，禁止与 source digest 混称。
- `court.office.result.v1` required fields 只允许：`schema`、`task_id`、`semantic_epoch`、`charter_sha256`、`invariant_capsule_sha256`、`checkpoint_id`、`dispatch_uid`、`attempt`、`office_instance_id`、`agent_id`、`role`、`direct_superior`、`worktree`、`write_set_sha256`、`status`、`summary`、`evidence`、`produced_at`。
- optional fields 只允许 `office_instance_kind`、exact-shape `carrier_proof`、flat unique `recovery_input_ids`。除 exact carrier proof 外，unknown、private/body 字段及任意嵌套 dict/list 在产生 quarantine/recovery side effect 前拒绝。
- review projection 使用 strict-whitelist、bounded、scrubbed、metadata-only schema。递归 privacy sentinel 必须证明 task/event/journal/receipt/stdout/stderr/exception 均不泄露 raw/private body。

### 5.4 review、handoff、target exact binding 与 consume

- `result-review` actor 固定为门下；门下只生成 scrubbed projection 并裁 `ACCEPT | REJECT`，不取得 dispatch 或集成权。输出必须是 exact-schema `court.office.result_recovery_review_receipt.v1`，绑定 quarantine core、recovery revision/head、projection、固定 reason、evidence pointer+digest、Menxia identity、event 和 receipt digest；未知字段拒绝。
- `result-handoff` actor 由 source managed binding 与 hierarchy manifest 推导为 target 的合法 direct superior；request/envelope/quarantine 自报的 actor、role、superior 不产生授权。
- target 只接受 ID 输入，其 exact binding 必须在锁内逐字段重算并匹配：`task_id`、`semantic_epoch`、`charter_sha256`、`invariant_capsule_sha256`、`checkpoint_id`、`dispatch_uid`、`attempt`、`office_instance_id`、`office_instance_kind`、`carrier_proof`、`agent_id`、`role`、`direct_superior`、`worktree`、`write_set_sha256`、`hierarchy_schema`、`hierarchy_gate`、`hierarchy_edge_class`、`preload_status`、`office_execution_ready`、`status`、`final_status`、`release_status`、`result_state`，并计算 `target_binding_sha256`。
- target 必须同 task、合法同角色/同上级且不同于 source，已 admit/start/preload，`hierarchy_gate=PASSED`、`preload_status=PASSED`、`office_execution_ready=true`、nonterminal、非 `QUARANTINED`、语义绑定 current。
- native host request 使用 typed `court.office.result_recovery_binding.v1`，不能把 recovery identity 塞入 `assignment`、`duty_scope`、`note` 或其他自由文本。host action receipt 必须 `succeeded`，并绑定 quarantine、head、projection、review receipt 与 target exact binding。
- handoff 输出 exact-schema `court.office.result_recovery_handoff_receipt.v1`；target 只收到 `recovered_result_inputs` metadata，不因 handoff 变成 completed。
- target 必须重新生成自己的 exact-whitelist `court.office.result.v1` 并引用 `recovery_input_ids`。consume 不是旁路 CLI；仅当既有 finish 完成 envelope whitelist、binding problems、target exact binding 和 recovery CAS 后，才在同一锁内产生 exact-schema `court.office.result_recovery_consume_receipt.v1` 并把新 head 置为 `CONSUMED`。

### 5.5 typed receipts、crash journal、重放与 legacy

- review、handoff、consume receipt 均为 exact schema，必须有 typed evidence pointer 与 evidence digest；unknown 字段、自由文本身份或 enum 外 reason 一律拒绝。
- 每项 operation 使用 `court.result_recovery.operation.v1` marker，阶段固定 `PREPARED -> TASK_WRITTEN -> EVENT_WRITTEN`。replay/recover 必须从 marker 与 ledger preimage 前向完成或安全回滚，不能生成第二 receipt、head 或 event。
- recovery event ID 必须确定性生成：`EVT-RR-` 加 `SHA256(operation_id + "|" + action + "|" + payload_sha256)` 前 24 个大写十六进制字符。
- 相同 operation ID + 相同 payload 返回原 receipt；相同 ID + 不同 payload/verdict/target 返回 operation conflict。并发 CAS 只能有一个成功，失败者零字节突变。
- legacy `court.office.result_quarantine.v1`、缺 `core_sha256` 的 core、缺 `head_sha256/previous_head_sha256` 的 recovery 记录仅可只读诊断；禁止补 digest、自动升级、review、handoff 或 consume。

### 5.6 RED -> GREEN 顺序

1. RED：先覆盖 pre-adapt hash、quarantine core immutability、source 精确终态与 write-claim 释放、result exact whitelist、wrong actor/target、target 全字段、receipt refusal/replay、CAS race、三段 crash、legacy read-only、privacy sentinel 和成功 consume。
2. GREEN-A：在 semantic continuity 层实现 exact schema、canonical digest、projection、core/head/receipt pure helpers。
3. GREEN-B：在 runtime、operation journal 与 native-host 层实现 source transaction、review/handoff、typed request/receipt、finish consume CAS 与 recovery replay ledger。
4. GREEN-C：更新当前真实运行合同 `references/court-state-runtime-agents.md`；若中书计划 Stage 3 指定的其他公开合同或 CLI manifest 确需同步，必须先取得 repo-control 精确 write set，不得自行扩大。
5. 验证：按中书计划 Stage 3 的聚焦命令运行 semantic、lifecycle、native-host、intervention、unified CLI 与 `git diff --check`，再由刑部只读复查、门下验收。

### 5.7 当前状态与停止门

- 当前状态：`M3_STAGE_CHARTER_APPROVED_DISPATCH_PENDING`；唯一 cursor=`stage-4/semantic-lineage`（依太子裁决自 `stage-3/result-recovery-chain` 推进至 M2 宏阶段首子门，见 log Entry 0032；charter 裁定见 Entry 0033；相二 RED/GREEN、D6 聚焦验证、D7 刑部复查与 D8 回写见 Entry 0034/0035；门下验收见 Entry 0039（独立只读复验 E1-E8 全绿、F 停止门未触发、写集符合、R-07 转绿、R1 记载在位）；archive receipt=`shiguan:SCOSZLSZU9T-20260807-1-DCBB`（path=`C:/Users/32893/.agents/court-shiguan/decretum-matrix/references/plan-archives/plan-20260807-stage4-semantic-lineage-subgate-1.md`；closeout_identity 逐字复制：诏令编号：SCOSZLSZU9T-20260807-1-DCBB / 古制谱系：史馆总纪·朝制志·官署门·三省六部纲·政令流转目·上奏回奏条·源摘要为英文；原文保留在源字段...诏 / 作业AI：workbuddy-root-serial-inline）；**M2 三子门（语义/投影/迁移）全部闭合**（投影：Entry 0040-0043 + `SCOSZLSZU9T-20260807-3-DCBB`；迁移：Entry 0044-0047 + `SCOSZLSZU9T-20260807-4-DCBB`）；**M3 阶段 charter 裁定见 Entry 0048**（太子授权「保留可回滚基准」裁定：默认源码 acceptance+候选包构建+fixture 验证，受控安装通道保留；D3 有界派发后工部 RED 定界中）。
- 2026-08-06 serial_inline 整改：刑部 FAIL 1-4 已修复并通过聚焦门（semantic/lifecycle/runtime/native-host/intervention/unified CLI/`git diff --check`）；FAIL 5 已由 Entry 0019 闭合（`scripts/check_stage3_recovery_chain.py` 真实调用 production review/handoff/consume 链并产出 typed receipts，同时修复 `_journal_preimage_privacy_violation` 的 JSONL 解析缺陷）；FAIL 6 已由门下复核并回写 Entry 0019。
- 辅助模型工具授权见 `3.1 辅助模型工具授权（2026-08-06 用户补充旨意）`：QoderCLI/Hermes/squad 仅作 advisory，不授予写权或回奏权。
- Entry 0009 已记录门下 `APPROVE`；Entry 0012 已由尚书正式接收 RED。工部已回报 GREEN-B runtime/recovery pass；刑部只读复查与门下验收已完成（Entry 0018/0019）；本阶段 archive receipt 待交接 checkpoint 生成。
- Entry 0014 中 `protocol_mode_unresolved` / `multi_agent_v2_enabled=false` 是仓库探针对空 managed overlay 的 false negative，不再作为真实 host blocker；Entry 0015 已记录本线程原生 `spawn_agent` 成功创建并运行只读 `/root/host_probe`。
- 2026-08-06 CB1 闭合批终更：stage-3 恢复链三条 typed receipt 编号与 archive receipt 编号逐字载入——review=`RR-D77A47C17EDDDDDE5FAC258E`、handoff=`RR-0C24600999E8AB628D0CB870`、consume=`RR-721329068BB3710AA924142D`、archive=`shiguan:SCOSZLSZU3B-20260806-7-DCBB`（满足计划书 L233「由执行书记载真实 receipt」字面要求）；CB1-1—CB1-5 依序完成并记载于 Entry 0021—0029；cursor 保持 `stage-3/result-recovery-chain`，M2 进入以门下终验裁定为准。
- 任一 schema、target、receipt、journal、privacy、source terminal 或 CAS 条件不满足，保持当前 cursor 并 `STOP`；不得回退 stage 0—2，也不得跳到 stage 4。

## 6. 宏阶段 M0—M4 直接绑定

- 宏阶段 M0—M4 的名称、顺序、验收边界和停止门，以 `docs/plans/2026-08-03-decretum-matrix-beta1.0.6-remediation-plan.md` 为唯一阶段定义；旧 `stage-0` 至 `stage-10` 只作为 evidence/receipt 的兼容子门别名，本执行书不再建立第二套细分阶段表。
- Stage 0—2 的本地 prerequisite gates 已形成当前恢复基线；发现证据漂移时在 `stage-3/result-recovery-chain` 记录 `prerequisite_drift` 并停止，不把唯一 cursor 重置为 stage 0。
- 当前只执行宏阶段 M1 的旧子门 `stage-3/result-recovery-chain`。M2—M4 必须在 M1 经刑部风险复查、门下验收并完成 log 回写后，按宏阶段进入；不得把子门别名当作额外执行权。
- 任一阶段失败都保持计划定义的当前 cursor，不得为追求版本完成而跳过、合并或降级 P0。

### 6.1 M2/M3 安装根与发布旁路审查门（旧 stage-5/6/9）

声明分类：以下 delegated snapshot、package/root identity、目标行为和后续 RED 合同统一属于 `[PLANNED_UNVERIFIED]`，不是当前 live registry、安装、发布事实或已实现能力。只有停止、live 重验、禁止误报和禁止在无证据时改变归因/结论的规则属于 `[CONTROL_PLANE]`。

- `[PLANNED_UNVERIFIED]` 候选包身份按 scoped package `@rowlandl/decretum-matrix`、registry=`https://npm.pkg.github.com` 设计。`[CONTROL_PLANE]` 后续发布门必须使用当前 manifest 派生的精确命令并实时复核，不能把本书当作远端事实：

  ```text
  npm view @rowlandl/decretum-matrix@beta version --registry=https://npm.pkg.github.com
  npm view @rowlandl/decretum-matrix dist-tags --json --registry=https://npm.pkg.github.com
  ```

- `[PLANNED_UNVERIFIED]` delegated observation：`2026-08-03` 时 `beta` 指向 `1.0.5-beta.0`。`[CONTROL_PLANE]` 该快照会漂移，只能待 M3 live 重验；未联网核验时不得报告为当前事实，也不得误用 unscoped package 或默认 npmjs registry。
- `[PLANNED_UNVERIFIED]` shared primary 规则为 `~/.agents`（复数）；`~/.agent`（单数）被视为笔误，不形成产品根、兼容 alias 或新增安装目标。
- `[PLANNED_UNVERIFIED]` 当前 worktree 的 fixed-five checker/sync 与 `INSTALL-PROMPT.md` 的 fanout-forbidden/current-tool-only 合同存在待验证 P0 冲突；目标行为不得继续沿用“默认五根”作为写入授权。
- `[PLANNED_UNVERIFIED]` root selection 目标合同为 receipt-driven exact schema：`~/.agents` 是共享主根；current-tool root 只有在 verified host/install receipt 证明当前工具后才可选；其他工具根和 Qoder 由最新用户明确列为目标，并为每根绑定 path identity、host/tool provenance、opt-in、preimage、backup/rollback 和 post-write proof。
- `[PLANNED_UNVERIFIED]` `.codex`、`.claude`、`.hermes`、platform Hermes user-data root 或 Qoder 不因属于某个集合而默认写入；`--include-qoder` 不替代最新用户授权和逐根 proof。
- `[PLANNED_UNVERIFIED]` checker、sync、installer、`INSTALL-PROMPT.md` 与 post-install gate 目标上消费同一份 target-selection receipt；任一组件自行枚举更多根应 fail closed。
- `[PLANNED_UNVERIFIED]` RED 至少覆盖 receipt/provenance 缺失、非 current-tool fanout、Qoder 未 opt-in、根别名/物理路径不一致、旧 beta、错误 registry/package scope、candidate hash 后 package mutator 改包、receipt 与实际写根不一致。
- `[PLANNED_UNVERIFIED]` package/release gate 目标上证明产物来自已提交 HEAD，hash 后不可再由 package mutator 改写，并在发布前重验 scoped package、dist-tag、registry、artifact digest 和远端结果。
- `[CONTROL_PLANE]` proxy `502` 只记录为外部 runtime/network 错误；没有本机可重复证据时，不得据此改变本机源码、候选包、安装根或同步结论，也不得触发破坏性修复。
- `[CONTROL_PLANE]` 上述 P0 合同未有 RED/GREEN、门下验收和逐根 receipt 前，M2/M3 保持停止，不得安装、同步活动根或发布。

## 7. Handoff 与结诏

- handoff 必须记录：两书路径、阶段 log、cursor、worktree/branch/HEAD、根与 child index、脏文件边界、已过命令、首个未过门、未完成风险和下一条精确命令。
- 阶段完成后的交接必须创建新的本机 local conversation task，且不得创建或使用新的 worktree task；新任务运行在 `D:\project` 的 `environment=local`，通过有界 packet 引用同一受管 child worktree，不复制完整 transcript/diff/file/private body，也不改变 task/branch/write set 语义。
- 暂停或 handoff 不是模型自行分配编号的许可。必须先由统一 CLI `shiguan archive-checkpoint` 产生有效 receipt。
- 诏令编号、handoff 编号、结诏编号、谱系和十四行内容只能逐字复制该 receipt 的 `payload.closeout_identity`；无有效 receipt 时只能报告 `handoff_or_pause` 或 `partial_or_not_run`，不得发送自造十四行。
- 结诏必须经门下复核。handoff 与结诏绑定完成后才可停止；恢复时必须同时核验 receipt、两书、log 和 cursor。

## 8. 下一步

1. 唯一 cursor 依太子裁决推进为 `stage-4/semantic-lineage`（M2 宏阶段首子门，log Entry 0032），不创建新工作树。
2. 已收取工部 GREEN-B 回报；刑部只读复查（source terminal、target exact binding、typed receipt、crash journal、legacy read-only、result exact-whitelist、pre-adapt source digest）已由 Entry 0018/0019 内联完成并全部通过。
3. 门下复核已通过并回写阶段 log（Entry 0019）；本阶段交接 archive receipt 由交接 checkpoint 生成；无门下接受和有效 archive receipt 不推进 M2，也不生成结诏。
4. 每个阶段完成并经门下复核、log 回写后，只创建下一个本机 local conversation task 进行 handoff；不创建新工作树任务，直至本执行书达到终态。
5. CB1 闭合批（CB1-1—CB1-5）已按门下裁定完成并回写 log（Entry 0021—0029）；stage-3 恢复链 typed receipts review=`RR-D77A47C17EDDDDDE5FAC258E`、handoff=`RR-0C24600999E8AB628D0CB870`、consume=`RR-721329068BB3710AA924142D` 与 archive receipt `shiguan:SCOSZLSZU3B-20260806-7-DCBB` 已在 `5.7 当前状态与停止门` 逐字记载（计划书 L233 字面满足）。
6. 门下 CB1 终验裁定 `CB1_ACCEPTED`（status=`FINAL_ACCEPTANCE_ISSUED`）已出具并逐字载入（log Entry 0031），cursor 依太子裁决推进至 M2 宏阶段首子门；M2 进入须经门下 charter 裁定与尚书有界派发；不得安装、同步活动根或发布。
7. M2 语义子门相二已闭合待门下验收（log Entry 0034/0035）：R-01 至 R-09 全集落笔，R-07 由 RED FAIL 转绿（候选1(d) 条件启用，`--apply` 路径存储 lineage 还原取代硬置空/重推导，列入 M4 handoff 传递项）；E1-E8 聚焦验证与 E8 双跑 digest 全绿，HEAD=48ddc910 钉定、staged=0、pyc=0；子门闭合≠宏阶段闭合，M2 尚余投影/迁移子门，未经门下 charter 裁定与尚书有界派发不得开展。
8. M2 语义子门门下验收 `ACCEPT`（log Entry 0039，独立只读复验 E1-E8 全绿、F 停止门未触发、写集符合、R-07 转绿、R1 记载在位）；archive receipt=`shiguan:SCOSZLSZU9T-20260807-1-DCBB`（plan-archives/plan-20260807-stage4-semantic-lineage-subgate-1.md，closeout_identity 逐字复制载入 §5.7）；下一动作=中书省拟制 M2 投影子门 charter（计划书 L187）呈门下裁定；未经门下 charter 裁定与尚书有界派发不得开展投影子门实施。
9. M2 投影子门闭合：charter 门下 APPROVE（Entry 0040）、RED 落笔与实跑 R-P1~R-P4 全 FAIL（Entry 0041）、GREEN 转绿 + D6/D7（Entry 0042）、门下验收 `ACCEPT`（Entry 0043，独立复验 E1-E7 全绿、写集仅落两文件）；archive receipt=`shiguan:SCOSZLSZU9T-20260807-3-DCBB`（plan-archives/plan-20260807-stage4-projection-subgate-1.md）；下一动作=中书省拟制 M2 迁移子门 charter（计划书 L188）呈门下裁定；未经门下 charter 裁定与尚书有界派发不得开展迁移子门实施。
