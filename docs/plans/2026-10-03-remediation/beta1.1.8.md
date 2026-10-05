# beta1.1.8 独立计划 · 子智能体派遣链修复

> 总纲：[2026-10-03 修复与完善计划（总纲）](../2026-10-03-decretum-matrix-remediation-plan.md)
> 上一版：beta1.1.7（外部锚点·无独立计划）｜下一版：[beta1.1.9](./beta1.1.9.md)
> 依赖：无｜被依赖：无
> 工单：`01-f24-fastopen-instance-id`、`02-f25-empty-write-set`、`03-f26-native-selector-strict`、`04-f23-canonical-followup`、`05-f22-preload-to-business`（05 依赖 01–04；本地工单 .scratch/remediation-2026-10/issues/）
> 权威依据：consolidated-review.md（仓库外只读，绝对路径见总纲文档地图；该类引用不参与仓库内链接校验）
> 条目：F22、F23、F24、F25、F26

## 1. 版本目标

让"预载成功"真正转化为业务执行：**一项真实有界任务从真实入口走完 admit → native-request → host-native spawn → capture → start → 首个业务读取与结果提交 → 上级接受**（预载完成改隐式判定；ACK 不再是必需环节，见总纲 §26.0）。

本版是最终版报告 F22 P1 事故的链路级修复，也是用户锁定的第一优先；F23–F26 为事故相关的四项源码断点，必须在同一版本内一并收口，否则链路验收无法成立。

## 2. 背景与证据基线（摘自权威报告，不重新鉴定）

- 事故时间线（北京时间 2026-10-03）：12:36:57 首轮开始 → 13:18–13:19 三署 b4 建立 → 13:26 三份正式 ACK PASSED/running → 13:28–13:29 三次 `send_message`（不触发 idle 子智能体新 turn）→ 业务 admission `allowed=false/runtime_capacity_exhausted` → 13:42 尚书唯一 turn 结束仍回报 PRELOAD_ACCEPTED → 14:07 首轮中断；首轮 90 分 58 秒无 A1–A7 业务成果。
- 现场事实：三署 ACK 后仍绑定 `assignment/scope=Preload`、只读、空写集；P00 DISPATCHABLE 与业务进度不是同一指标。
- 归因边界（不扩大）：调用适配（trigger/压缩/唤醒工具）＋ F23–F26 实现断点 ＋ 测试与提示未约束"预载→第一项业务"整体路径；**不得**把停用矩阵后的普通协作恢复记为矩阵修复。
- 证据原件（仓库外只读，根工作区）：`D:\project\.repo-control\evidence\decretum-matrix\beta117-review-20260930\`、`D:\project\_diag\decretum-dispatch-incident-20261003\`、`D:\project\xiuxian-mod\.scratch\xianxia-framework-cicd\stage-3\evidence\S3-FND-06A\court-01a1000d\`。

## 3. 修复条目

### 3.1 F24 · fast-open 实例编号与生命周期不兼容（P2）

- 现象：`court open --fast` 默认产物生成 `role#<12hex>`（真实样例 `zhongshu#4defa014347b`）；生命周期消费者只接受 `role` + `#` 四位非零十进制编号或既有 `role-...` 形式；admission 仅检查非空，未在 spawn 前拦截。
- 位置：`scripts/commands/court_open_fastpath.py:937`（生产）；`scripts/court_runtime.py:1589`（消费）。
- 修复要求：
  - fast-open 复用既有合法编号 helper；真实生成包在准入与 spawn 前调用同一消费校验；
  - 保留历史编号与既有合法格式，不重建身份体系；
  - 调用方自拟非法编号（`#z1`/`#b2`）仍按调用错误处理，不因修复而放宽。
- 验收（可测）：
  - [ ] 真实 fast-open 默认产物直接通过 admit → native-request → spawn，无需人工改 id；
  - [ ] 正例 `#0001`、`role-12hex`、`role-b4` 通过；负例 `#12hex`、`#z1`、`#b2` 拒绝；
  - [ ] 生产者与消费者使用同一夹具来源（不得各手写）。
- 证据：fast-open 默认输出原文 + 消费校验逐例对照 + spawn 调用回执。

### 3.2 F25 · 只读空写集被传输层扩成读范围（P2）

- 现象：明确的 `write_set=[]` 被 `binding.get('write_set') or binding.get('read_scope')` 回填成读集合；底层 builder 又要求非空写列表，实际输出 `[SKILL.md]`，向子智能体发出误导性写权限提示（无证据表明实际写入发生）。
- 位置：`scripts/court_runtime.py:10316`–`10335`；`scripts/court_native_host_dispatch.py:110`、`248`。
- 修复要求：区分"字段缺失"与"字段明确为空"；在既有 contract 中表达合法只读任务；**不得**用读范围填写作集、不得删除写集绑定。
- 验收（可测）：
  - [ ] 空只读任务在 admission、native request、host message、office record 四处一致为空；
  - [ ] 非空写任务照常；缺失字段负例按契约处理；
  - [ ] 不存在"只读任务生成 `[SKILL.md]` 写提示"的路径。
- 证据：admission/native request/host message/office record 四份产物对照。

### 3.3 F26 · 公共 native selector 静默丢弃错误层级模型请求（P2）

- 现象：本案 `native-z.json` 在顶层放 `model_request`；公共路径先经 Namespace，再只投影四项身份与可见能力字段，未知键消失、返回成功却不带 override；直接 strict normalizer 本应报 `native_request_fields_invalid`。case-bound 模型权威实际来自 admission 当前选择。
- 位置：`scripts/court_runtime.py:12262`（Namespace）→ `10128`（投影）。
- 修复要求：公共边界先严格校验 raw keys，再做 Namespace 投影；保留"模型仅在正确 case-bound 层级选择"的约束；不得削弱模型验证。
- 验收（可测）：
  - [ ] 正确继承、合法显式选择通过；
  - [ ] 错误层级、未知参数被显式拒绝并提示正确字段；
  - [ ] 无静默 PASS 路径。
- 证据：四类用例的公共路径输出对照。

### 3.4 F23 · canonical 子智能体无法生成正式续派（P2）

- 现象：对既有 `native_host_identity_kind=canonical_agent_path` 的 target，续派构造器返回 `native_bridge:canonical_followup_issuer_unavailable`；宿主 `followup_task` 不能替代 Matrix capture/receipt 续派。
- 位置：`scripts/court_runtime.py:10347`；相关 `scripts/commands/court_native_bridge.py:241`–`282`（followup 仍生成初次读取/接纳/等待指令）。
- 修复要求：补齐 canonical target 的合法 host invocation / capture producer，接入既有 case、instance、直接上级、租约与 scope 校验；明确区分 fresh start 与已接纳 followup；**禁止**伪造 UUID、放宽身份校验、用连续重 spawn 代替复用。
- 验收（可测）：
  - [ ] 真实当前宿主完成一次有界复用对照（含真实 host dispatch 与状态写入证据）；
  - [ ] fresh start 与 followup 路径可区分；
  - [ ] 失败的复用给出可执行诊断（而非通用拒绝）。
- 证据：宿主调用回执（host call / child trace）+ 状态写入记录。

### 3.5 F22 · 预载成功未转成实际业务（P1，链路收口）

- 现象：见第 2 节时间线；三署 ACK 成功但差遣只有 Preload、空写集；唤醒工具与业务范围绑定双缺失。
- 修复要求：
  1. 初次 admission 即绑定真实有界业务 assignment / read_scope / write_set / expected result，预载作为其前置阶段；已有 Preload 差遣不得默默获得新写权限，业务变化走显式续派/范围更新；
  2. 业务 relay 由正确直接上级以可唤醒宿主的工具（`followup_task`）承载；**不要求 ACK / `preload_status` 作为前置**（用户 2026-10-05：ACK 限制优先废除，轻量替代见专项设计）；
  3. 容量拒绝或不支持续派时保留证据、给出下一步并停止无界重 spawn；**不得**移除安全、层级、身份与写集门禁换取表面进度（**ACK 前置除外**——按用户 2026-10-05 决策废除，见总纲 §26.0）。
- 验收（可测）：
  - [ ] 真实有界任务读到首个业务文件并产生可核验结果，上级完成接受；
  - [ ] 覆盖 child 已 idle、只读空写集、容量不足、业务范围变化四类场景；
  - [ ] 正例与拒绝例均不重复初始化、不误报已执行。
- 证据：任务绑定 + host call/child trace + 业务输入 locator + 产物 + report + finish。

## 4. 执行顺序与依赖

```
F24（编号生产/消费） ─┐
F25（写集投影）      ─┼→ F23（canonical 续派）→ F22（链路收口与真实验收）
F26（参数严格校验）  ─┘
```

- F24/F25/F26 相互独立，可并行实现与验证；F23 依赖真实宿主调用能力；F22 依赖前四项完成，且需一次真实有界业务派遣。
- 若无真实宿主可用：F24/F25/F26 可离线对照验收；F23/F22 明确标 PARTIAL，不得以离线结果替代。

## 5. 版本出口（Exit Criteria）

- [ ] 3.1–3.5 全部验收项达成（或按上述规则明确标注 PARTIAL 项与原因）；
- [ ] 六项原始失败对照转为受控结果并保留原始样本：`#12hex` 编号拒绝、空写集回填 `[SKILL.md]`、错误层级静默 PASS、canonical 续派拒绝、容量拒绝、`send_message` 排队不唤醒；
- [ ] 复核命令/路径与回执记录在"执行记录"节；
- [ ] 文档任务（第 7 节）完成；
- [ ] 未引入新身份体系、平行预载协议或第二套 tracker。

## 6. 回归与失败对照清单

| 对照项 | 原始样本位置 | 修复后预期 |
| --- | --- | --- |
| `#12hex` 编号被拒 | 权威报告 F24 与 `open-verified-result.json` | 默认产物直接消费；非法值仍拒绝 |
| 空写集回填 | 权威报告 F25 | 四处一致为空 |
| 错误层级静默 PASS | 权威报告 F26 | 显式拒绝 + 字段提示 |
| canonical 续派拒绝 | 权威报告 F23 | 有界复用通过 |
| 业务容量拒绝 | `biz-zhongshu` 拒绝回执 | 保留拒绝语义 + 给出下一步 |
| `send_message` 不唤醒 | 事故时间线 13:28–13:29 | 改用可唤醒工具并验证业务 turn |

## 7. 文档任务

- `scripts/commands/court_native_bridge.py` bootstrap 文案：**按 ACK 轻量替代口径改写（用户 2026-10-05）**——不再要求材料顺序、读取格式子集（`cat <单个静态路径>`）或 commentary JSON acceptance 契约（降级为兼容提示或移除；见专项设计 `.scratch/remediation-2026-10/evidence/ack-lightweight-replacement-design-20261005.md`）；不新增任何格式前置；
- `references/`：若 F23/F25 修复触及派遣/写集 contract 描述，同步对应 governing 文档；
- `CHANGELOG.md`：beta1.1.8 条目（含"未验证边界"声明）；
- 总纲"执行记录"与本文件第 10 节。

## 8. 工单

| 工单 | 覆盖 | 依赖 |
| --- | --- | --- |
| `01-f24-fastopen-instance-id` | 3.1 | 无 |
| `02-f25-empty-write-set` | 3.2 | 无 |
| `03-f26-native-selector-strict` | 3.3 | 无 |
| `04-f23-canonical-followup` | 3.4 | 无 |
| `05-f22-preload-to-business` | 3.5 + 版本出口 | 01–04 |

## 9. 边界

- 全局边界按总纲第一节（发布按总纲 26.1 在本版验收后执行；不替换安装、不新增哈希校验脚本、不动其他仓库）；
- 本版不改写历史 refs/tag；不宣称"所有同 scope reuse 路径已修"（仅按验收范围声明）；
- 无真实宿主证据时，F22/F23 标 PARTIAL，不以离线对照替代。

## 10. 执行记录（实施时填写）

| 日期 | 动作 | 证据位置 | 结果 |
| --- | --- | --- | --- |
| 2026-10-05 | F24 实施：`court_runtime.office_instance_id_from_suffix`（复用 `_require_role_prefixed` 生产 `role-<suffix>`）；`court_open_fastpath._lease/_admission_request` 改用它并在准入前校验 | `scripts/court_runtime.py`、`scripts/commands/court_open_fastpath.py`、`.scratch/remediation-2026-10/evidence/f24-verify.txt`（脚本 `f24-verify.py`） | 默认 fast-open 产物 instance_id `zhongshu/menxia/shangshu-open-fixture` 直接通过消费校验；`#0001`/`role-12hex`/`role-b4` 通过，`#12hex`/`#z1`/`#b2` 拒绝；调用方自拟非法编号 → `INVALID/fast_open_instance_id_invalid` |
| 2026-10-05 | F25 实施：`_native_bridge_request` 区分缺失/明确为空并禁止用读范围填写作集；`_native_host_request_binding_problems` 同源；`court_native_host_dispatch._string_list` 允许空 write_set | `scripts/court_runtime.py`、`scripts/court_native_host_dispatch.py`、`scripts/checks/check_court_intervention_matrix.py`（夹具不再回填）、`.scratch/remediation-2026-10/evidence/f25-verify.txt`（脚本 `f25-verify.py`） | 空只读任务在 admission/native request/host dispatch/host message/office record 五处一致为空；缺失 write_set → `native_bridge:binding_write_set_missing`；非空写任务照常；空 duty_scope 仍拒绝 |
| 2026-10-05 | F26 实施：`office_request_namespace` 在 Namespace 投影前严格校验 native selector raw keys，错误层级 `model_request` 与未知键显式拒绝 | `scripts/court_runtime.py`、`.scratch/remediation-2026-10/evidence/f26-verify.txt`（脚本 `f26-verify.py`） | 正确继承/合法显式选择 ACCEPTED；错误层级（含现场 `native-z.json` 样本）与未知参数 REJECTED 并提示 `model_request` 属于 conversation gate；无静默 PASS |
| 2026-10-05 | 既有检查回归（PYTHONPATH=scripts）：`check_court_open_fastpath`、`check_startup_fastpath_contract`、`check_court_intake_gate`、`check_court_native_host_dispatch`、`check_court_native_bridge`、`check_court_runtime`、`check_native_opaque_capture`、`check_court_agent_lifecycle`、`check_court_intervention_matrix`、`commands/quick_validate.py` | 上述命令输出（本表本行） | 全部 exit=0；`check_semantic_continuity` 与 `check_p00_semantic_dispatch_context` 在 HEAD 基线上同样失败（已做基线对照），与本次三项改动无关 |

| 2026-10-05 | F24/F25/F26 独立验收（验证子会话 9da27818，只读）：diff 审阅、12 项回归复跑、两红灯基线对照（git archive HEAD 复跑错误串一致）、夹具断言强度对比（84 vs 84 未降）、证据复现、边界核查 | 会话报告 + .scratch/remediation-2026-10/evidence/*verify.txt | 全 PASS；工单 01/02/03 可关闭；版本出口（VERSION/CHANGELOG/真实端到端）待 F23/F22 完成后收口。新发现：①office admit 额外 raw 键仍被 Namespace 接受（F26 范围外，待确认预期）；②ead_scope=[] 且 write_set 非空时 duty_scope 校验路径不同源（低，待对齐） |
| 2026-10-05 | F23 实施：请求侧按 identity kind 构造 canonical 候选（host_task_id=host_instance_id=native_host_instance_id、host_thread_id=native_child_thread_id、context_utilization 取宿主观测）；协议侧 canonical 一致性校验（path 相等 + activity 绑定的 child thread 相等 + host_thread_id 保持 null）；capture 侧 opaque followup 匹配、canonical followup producer（`SubAgentActivity(kind=interacted)`，允许空 output）、utilization producer（子线程 rollout 的 `last_token_usage.total_tokens`/`model_context_window`）；翻转 `check_court_native_bridge` 中固化缺陷的负例 | `scripts/court_runtime.py`、`scripts/court_native_host_dispatch.py`、`scripts/court_native_trace.py`、`scripts/commands/court_native_bridge.py`、`scripts/checks/check_court_native_bridge.py`、`.scratch/remediation-2026-10/evidence/f23-verify.txt`（脚本 `f23-verify.py`）、`f23-verify-head-baseline.txt`、`f23-assert-flip.txt` | 18 项离线对照全部达到预期（canonical 正例/负例、请求侧、协议侧、消费侧、legacy 不回归、spawn→record→复用闭环）；HEAD 快照对照：canonical 正例全部 REJECTED（`marked_host_action_missing` / `canonical_followup_issuer_unavailable` / KeyError）；真实验收需隔离 HOME + 真实 Codex 会话 → 标 PARTIAL 待真实宿主 |
| 2026-10-05 | F23 回归（工作树，含 F24/F25/F26 未提交改动）：`check_court_native_bridge`、`check_native_opaque_capture`、`check_court_native_host_dispatch`、`check_court_dispatch_policy`、`check_office_decree_startup`、`check_court_runtime`、`check_court_open_fastpath`、`check_court_agent_lifecycle`；HEAD 快照（git archive 导出）对照其中五项 | 命令输出（本表本行） | 全部 exit=0；HEAD 快照基线同样全部 exit=0（无基线红灯） |

| 2026-10-05 | F23 独立验收（验证子会话 fb88549a，只读）：diff/负例翻转（AST 49→57 无消失）/G producer 真实性（实测真实比值）/回归（工作树 8 项 + HEAD 5 项全绿）/证据 18/18 双向一致/边界与行尾全部核查 | 会话报告 + .scratch/remediation-2026-10/evidence/f23-verify*.txt、23-assert-flip.txt、23-regression.txt | **离线范围 PASS**；工单 04 离线部分可关闭；**验收项 1（真实宿主对照）挂起 → PARTIAL**；新发现 1 中（send_input 在 followup 工具集内，真实验收需加断言）+ 3 低（负例覆盖/thread_id 语义/文书差异），已列真实验收清单 |
| 2026-10-05 | F22 实施（按总纲 26.0 放开口径）：A1–A4 首次 admission 绑定业务范围（`court_open_fastpath._lease` 增 `dispatch_phase`/`bounded_mandate`/`expected_result`/`terminal_condition`，`read_scope`=业务写路径∪四份 preload 源；`_admission_request` assignment 业务化；`public_admission_template_payload` binding 同源）；A3 业务门（followup 需业务绑定，preload-only 拒绝并给 next_step）；B1 `canonical_host_message` 按 action 分支（spawn=bootstrap+phase=preload；followup=resume+phase=business，无 bootstrap 与等待语）；C1 容量拒绝 enrich（next_step/reuse_candidates/wave_block_hint）；C2 有界拒绝计数+显式继续（`capacity-refusal-ack`，非硬停）；C3 `office_instance_already_admitted` 可执行诊断（followup 续业务/新 instance_id 并行写者）。**ACK 放开（用户 2026-10-05）**：删除 B2 ACK 门，并放开 caller guard / identity context / reuse 候选 / plan producer / report / finish / completion source / result-recovery handoff 的 `preload_status`/`office_execution_ready` 依赖（保留层级、scope/write_set、容量事实、身份与终态校验）。**预算放宽（最小必要+记录）**：`ENTRY_PRELOAD_BUDGET_BYTES` 20480→20992（20 KiB→20.5 KiB，+512B）；写死断言仅 `check_court_native_bridge`（字面量 `20 * 1024 + 512`），`check_unified_cli` / `check_court_preload_semantics` 经 `ENTRY_PRELOAD_BUDGET_BYTES` 常量引用 | `scripts/court_runtime.py`、`scripts/commands/court_open_fastpath.py`、`scripts/commands/court_native_bridge.py`、`scripts/court_office_config.py`、`scripts/court_plan_artifacts.py`、`scripts/check_unified_cli.py`、`scripts/checks/check_court_native_bridge.py`、`scripts/checks/check_court_preload_semantics.py`、`scripts/checks/check_office_decree_startup.py`、`scripts/checks/check_court_agent_lifecycle.py`、`.scratch/remediation-2026-10/evidence/f22-verify.txt`（脚本 `f22-verify.py`）、`f23-verify-rerun-f22.txt` | U1–U9 全绿（U5 为 ACK 放开后的反向断言：未 ACK 不再拒绝；U6 未 ACK 但非终态有身份的候选仍可复用）；十项回归 + `quick_validate` + `check_source_state_budget`（清理运行产物后）全 exit=0；**未按字面实施项**：设计 A5 的 4 个业务字段回执绑定（host dispatch request 为 closed 白名单，`normalize_native_host_dispatch_request` 丢弃额外字段；照字面加入 expected 会令 binding 有值时全部回执不一致）→ 业务回执绑定由既有 `assignment`/`duty_scope`/`write_set` 承担；F23 独立证据脚本 8 项旧式 preload-only fixture 因 A3 业务门 REJECTED（预期交互，F23 侧需补业务绑定夹具），`check_court_native_bridge` 19 tests 仍 OK；真实宿主验收（隔离 HOME + 真实 Codex 会话）未做 → PARTIAL |

| 2026-10-06 | F22 独立验收（验证子会话 490b85ca，只读）：diff/复跑一致性/ACK 放开 8 处/预算放宽/边界全部核查 | 会话报告 + .scratch/remediation-2026-10/evidence/f22-verify.txt、f23-verify-rerun-f22.txt | 离线可关闭；整体 PARTIAL（真实验收/F23 夹具/版本出口待收口）；新发现 handoff→ACK 漂移（中，已列收尾修补）；预算 +512 接受（理论最小 +52，留有界余量） |
| 2026-10-06 | 收尾修补：①handoff→ACK 漂移——`_target_binding_from_record` 对齐权威字段集（补 `case_ref`/`plan_ref`，`write_set_sha256`→`write_set`），`_target_binding_sha256`、supplied 校验与 consume 逐字段比对豁免 `preload_status`/`office_execution_ready`（身份/scope/write_set/层级仍严格）；同步修 `_build_recovery_receipt` 的 `evidence_ref`→`evidence_sha256`（HEAD 级 schema 漂移，不修则 review/handoff/consume 全部不可用）；②F23 夹具补业务绑定 + 非零退出码；③f22-verify U1 断言口径修正；④`check_unified_cli` 错误码 `..._20kib`→`..._budget`；⑤`first_office_report_at` ACK 条件评估留待专项 | `scripts/court_runtime.py`、`scripts/check_unified_cli.py`、`.scratch/remediation-2026-10/evidence/f22b-verify.py`/`f22b-verify.txt`、`f23-verify.py`/`f23-verify.txt`、`f22-verify.txt`、`beta118-remediation-verify-20261006.md`、`first-office-report-ack-eval-20261006.md` | f22b 9/9（正例：未 ACK handoff→补 ACK→consume 成功；role/write_set/agent_id/carrier_proof/instance/hierarchy_gate/case_ref 漂移仍 `result_recovery_target_mismatch`）；f23 18/18 ACCEPTED（exit 0）；f22 U1–U9 全绿（exit 0）；12 项回归中 10 项 exit=0，`check_semantic_continuity` 与 `check_stage3_recovery_chain` 为 HEAD 预存在红灯（git archive 快照同错，已对照） |
| 2026-10-06 | 收尾修补（子会话 666864fe）：handoff→ACK 漂移修复（ACK 字段豁免集）+ 两处 HEAD 级 schema 漂移修复（target_binding 字段集 22→24 键、recovery receipt 键 evidence_sha256）+ 低项三项 | f22b-verify.py/.txt（9/9）、f23-verify.py/.txt（18/18）、first-office-report-ack-eval-20261006.md | f22b 9/9、f23 18/18、回归 11 项 + quick_validate exit=0；两红灯为 HEAD 预存在；未决：真实验收 PARTIAL、stage3 红灯待 F23/F24 收口、schema 漂移记入版本出口 |
| 2026-10-06 | **ACK 轻量替代专项（P1–P5，用户 2026-10-05 裁决候选 A「隐式完成 + 可选补录」）**：P1 生命周期门禁放开（report/finish/heartbeat/heartbeat-close 无 ACK 拒绝；`first_office_report_at` 拆分出 legacy `first_office_report_after_ack_at`，close 不再因未 ACK 改写身份证据）；P2 `agent_preload_ack` 降级为可选 legacy 补录（去 trace/`native_request_ref`/`cat` 形状前置，失败只写诊断、不改状态与 ready），`agent_start` 写 `preload_phase`（STARTED → IMPLICIT_AFTER_CAPTURE → COMPLETED_IMPLICIT + `preload_completed_at`）、`preload_ack_required=False`，`office preload-ack` 保留于命令面并标注 legacy optional / never a gate，仅从日常 help/hints 默认指引降级；P3 `exact_preload_contract_gate` 只删 `preload_ack` 项（保留路径/case_ref/profile/dossier/skill 同一性）、superCC gate 改 `NOT_REQUIRED`（身份校验保留，旧 ACK 标 `legacy_preload_ack_stale`）、史馆信任/容量租约去 preload 前置；P4 文档与 14×2 角色档按隐式完成改写、bootstrap 文案去材料顺序/读取格式/commentary acceptance 契约；P5 验收脚本六条全 PASSED（18 项检查串行全绿） | `scripts/court_runtime.py`、`scripts/court_office_bootstrap.py`、`scripts/court_dispatch_policy.py`、`scripts/supercc_dispatch_contract.py`、`scripts/supercc_dispatch_delivery.py`、`scripts/commands/ensure_supercc_court.py`、`scripts/shiguan_pending_trust.py`、`scripts/court_complexity_budget.py`、`scripts/commands/report_office_startup_latency.py`、`scripts/commands/sync_codex_agents_from_profiles.py`、`scripts/checks/**`、`references/**`、`SKILL.md`、`docs/wiki/**`、`agents/**` | 证据：`.scratch/remediation-2026-10/evidence/ack-lightweight-verify.py` / `.txt`（`status=PASSED`，六条 1–6 全 PASSED，18 项检查 exit=0）；`f22-verify.py` U9 十项串行 `U9_all_exit_zero=true`（exit 0）。预算未再放宽（P2 文案经压缩后 headroom 恢复，入口预载仍为 20992）。**预存在红灯（非本专项）**：`check_codex_agent_roles`（本机 `~/.codex/agents` 与 `~/.agents/skills/decretum-matrix` 环境不同步，14 unsynced）、`check_agente_terminal`（`intake-template` 的 `invariant_capsule` 模板字段数 10 ≠ 断言 13）、`check_semantic_continuity` / `check_stage3_recovery_chain`（HEAD 预存在，前次已对照） |
| 2026-10-06 | ACK 轻量替代专项 P1–P5（子会话 b5be0c8a）：生命周期门禁放开 + 命令轻量化/补录化 + 公开面/superCC/史馆/租约 + 文档与 28 角色档；headroom 靠压缩文案解决（未再放宽预算） | ack-lightweight-verify.py/.txt（六条 PASSED）、f22-verify.py（串行 exit 0） | P1–P5 全落地；六条验收 PASSED、18 项检查串行 exit=0；未决：真实验收 PARTIAL、4 项预存在红灯建议单列工单 |
| 2026-10-06 | ACK 专项独立验收（验证子会话 356e7759，只读）：六条验收与 18 项检查复跑、P3 同一性保留核查、门禁扫描、兼容回归、文档抽查 | 会话报告 + ack-lightweight-verify.py/.txt | **有条件可关闭**（无越界）；8 项发现（3 中：证据过期/角色档未同步/stage3 fixture 漂移；5 低）已派收尾修补 |
| 2026-10-06 | **ACK 专项收尾修补**（子会话 9cb2fcb1，实施）：①刷新 `f22-verify.txt`——最终工作区状态串行复跑（`python -B .scratch/remediation-2026-10/evidence/f22-verify.py`，exit 0、`U9_all_exit_zero=true`、10/10 检查 exit=0），文件头记刷新时间与「U9 必须串行」注记；②行尾归一化——按 HEAD 逐行行尾分布恢复 `scripts/court_runtime.py`（2879/2530→439/90）、`scripts/checks/check_court_agent_lifecycle.py`（911/878→114/81）、`SKILL.md`（2/2→1/1）、`scripts/court_complexity_budget.py`（5/5→4/4），只改行尾、逐行内容字节不变，全仓 `git diff --numstat` == `--ignore-cr-at-eol --numstat`；③`check_codex_agent_roles` 14 unsynced 归因=P4 改渲染器/模板后本机 `~/.codex/agents` 未同步（实测：HEAD 渲染器+本机模板=14 synced、当前渲染器=14 different），属 release-gates `steps` 的 installation 门禁（condition=always）、不在 CI source-contracts 集合，本机同步命令 `python scripts/commands/sync_codex_agents_from_profiles.py --write`（本次未写用户环境）；④`check_stage3_recovery_chain` 漂移归因=ACK P2 降级 `captured_child_read_order` pending 后推进至 `_native_followup_fixture`，暴露两处既存漂移（`semantic_receipt` 旧键、`recovery_binding` 被 closed 白名单丢弃），单点小修不能闭合→留待 F23/F24 专项；⑤文档修正 2 处（重复行、`legacy_optional` 键归属）；⑥表述修正（`office preload-ack` 保留且标注 legacy optional/never a gate；写死预算断言仅 `check_court_native_bridge`） | `f22-verify.py`/`f22-verify.txt`、`git diff --numstat` 对照、`references/court-normal-startup.md`、`references/sections/court-office-name-profile-skill-binding.md`、工单 05 Comments | 任务 1/2/5/6 完成；任务 3 结论=版本出口项（本机 `sync --write` 即绿，源码仓库无需改）；任务 4 结论=留待 F23/F24 专项；未决：真实验收 PARTIAL、`ensure_supercc_court.py:1845/3542` 的 `PRELOAD_PENDING` stale 命名（与 superCC 检查断言耦合，非小改） |
## 发布与 CI 验证（按总纲 26.1）

- 本版验收通过后执行：推送到 GitHub、GitHub Release、npm 包发布（版本号 = 本版号）；
- 以既有 GitHub Actions CI 验证；**CI 内容默认不改动**（不放宽门禁、不为过审修改检查集合）；
- 仅当 CI 验证确实不可行时提出调整并经用户同意；发布前核对 workspace.yaml 的 publication_gates；
- 发布证据（Release / npm / CI 回执）记入执行记录。

---

*本计划由总纲派生；修改需同步总纲第二节与交叉引用关系。*
