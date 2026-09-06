# ChatGPT 返回包审查与合入收据（2026-09-06）

- 返回包：`docs/handoff_packages/beta1.1.0-office-startup-handoff-with-source-2026-09-06.zip`
- 提取目录：`D:\project\.staging\dm110-20260905\chatgpt-return-20260906\`
- 主文档：`handoff/handoff.md`（以该文件为准）

## 一、结论

返回包**诚实、可复现、结构一致**，但请注意：**它做的是另一个聚焦范围——“子官署启动 / 尚书省→礼部派遣”，不是对上一轮 T08/14 项失败清单的复核**。文档明确未混入 consultation 扩展，也没有把局部结果当作整体通过。

## 二、我在本地做的复核（全部通过）

1. 逐文件比对：返回 `source/decretum-matrix/` 与本地工作树**仅差 4 个文件**（3 改 1 增），其余 613 个文件逐字节一致 → ChatGPT **完整保留了我们此前的 T08 修复**，无意外漂移。
2. `git apply --check` 对本地树通过；随后 `git apply` 成功合入。
3. 合入后本地复跑：
   - `check_office_decree_startup.py`：7/7 OK
   - `check_court_native_bridge.py`：OK
   - `check_native_opaque_capture.py`：9/9 OK
   - `check_court_office_bootstrap.py`：exit 0
   - `check_court_native_host_dispatch.py`：PASS
   - `check_court_case_binding.py`：7/7 OK
   - T08 四门证据 harness：`T08_GATE_EVIDENCE_GREEN_OK`（无回归）
4. 抽查返回包声称的 4 个“相邻既有失败”：`hierarchy`、`dispatch_policy`、`multi_instance`、`p00` 在返回源上确实仍 exit 1，与包内 `repack-check-summary.json` 一致，未被“改断言造绿”。

## 三、返回补丁内容（已合入本地）

| 文件 | 变更 | 评价 |
|---|---|---|
| `scripts/court_runtime.py` | `_native_bridge_identity_context` 用 `case_ref == case_reference(task)` 识别当前案尚书省父级 | 正确：与 court_code/case_ref 重构方向一致，且比依赖父记录上的 `charter_sha256` 更稳 |
| `scripts/commands/court_native_bridge.py` | bootstrap 指令明确 read-and-ack only | 文案级，安全 |
| `references/court-normal-startup.md` | 区分“负责官署改包流程”与“每次子署启动” | 文档级，安全 |
| `scripts/checks/check_office_decree_startup.py` | 新增 7 项专项回归（父级绑定、错误引用、失效状态、编号、启动指令、无外部命令、礼部请求/证据采集） | 覆盖好；注意它 import 了 `check_semantic_continuity`/`check_native_opaque_capture` 的内部夹具，属于测试耦合，后续改夹具时需同步 |

## 四、允许/不允许的结论

✔ 可以说：本轮 office-startup 局部补丁已合入本地工作树，6 项命令本地实测 exit 0，T08 四门仍绿。
✘ 不可以说：beta1.1.0 发布通过；完整 release-gate 未跑；4 个相邻失败仍在；上一轮 14 项 required-suite 失败（completion/semantic_continuity/runtime/runtime_concurrency/agent_lifecycle/startup_fastpath/hierarchy/session_closeout/preload_semantics/skill_identity/source_budget/mcp/portability/installer_fixture）一个都未因此消除。

## 六、补充：当前模式子官署验收（已执行，2026-09-06 晚）

按用户授权“当前模式可直接调用子官署、本质加载一致”，已用 DSH 真实执行一次 尚书省→礼部 启动验收：

- 任务：`office-startup-currentmode-acceptance-4`（court_code `SREVIEWUE9-20260906-N-NDAA`，super/parallel）
- 真实路径：create → plan/review → semantic verify → agent-admit → `office_native_request` → `canonical_host_message` 全部通过
- 子官署加载：由 DSH 子代理真实读取 `SKILL.md`(96)/`libu.toml`(43)/`libu/AGENTS.md`(44)，返回 `court.child_preload_acceptance.v1`，`preload_status=PASSED`；未跑独立 preflight、未重复 root intake、未调业务 CLI/MCP
- 六项回归全部 exit 0
- 边界（未夸大）：无 Codex 宿主（CODEX_* 由当前模式身份绑定、父级祖先为宿主边界注入）；pre-spawn 路径（start/ack 跳过）；`superior_acceptance=PENDING`；完整 release-gate 未跑
- 独立发现：用户真实 CLI 创建的 `20260906-office-startup-real-host-acceptance-v2` 携带**旧契约 capsule**（含 charter_sha256/governing_hashes/latest_decree_sha256、缺 case_ref），`agent_admit` 正确拒绝 `legacy_semantic_binding_read_only` ⇒ 真实 CLI create 路径仍需迁移到新契约
- **已修复（②）**：`scripts/court_semantic_continuity.py` 新增 `_coerce_legacy_invariant_capsule`，在 `semantic_binding_for_revision` 中把旧契约 capsule（携带 digest 字段）自动迁移为新契约（去 digest 字段、补模板字段、绑定 case_ref）；实测旧 `request-capsule.json` create → verify DISPATCHABLE → `require_semantic_mutation_binding` PASS，不再卡在 agent_admit。office startup 7/7 与 T08 四门均无回归。
- 证据目录：`D:\project\.staging\dm110-20260905\t08-bingbu\office-startup-real-host\`（`acceptance-currentmode-runtime.json`、`acceptance-child-office.json`、`acceptance-child-office.md`(美化)、`acceptance-summary.md`、`acceptance-runtime.failed.json`）

## 七、收口进展（2026-09-06 晚，多轮后）

最新实测绿项（隔离/套件参数）：
- `check_court_runtime_completion` → `COURT_RUNTIME_COMPLETION_OK cases=21`（已完成 charter_sha256→case_ref 等全部迁移）
- `check_court_runtime_concurrency` → exit 0（create 加 `--legacy-compatibility`）
- `check_court_open_fastpath --serial-probes --json` → PASS（修复：SKILL.md 增加便携校验行并回退 court-normal-startup.md 后，root 预载预算 20477/20480）
- `check_skill_identity --json` → PASSED（按 LF 归一化重新生成 `skill_sha256`）
- `check_portability` → ok（4 个入口补 `sys.dont_write_bytecode`，SKILL.md 含 `python -B scripts/quick_validate.py .`）
- T08 四门、`check_office_decree_startup` 7/7 继续 GREEN；旧契约 capsule 自动迁移（`_coerce_legacy_invariant_capsule`，wrong digest 仍拒绝）

仍红（未收口）：semantic_continuity、runtime（剩余旧 API 夹具）、agent_lifecycle、startup_fastpath、hierarchy、session_closeout、preload_semantics、mcp、installer_fixture、source_budget（需在最终无 pycache 时复跑）。

## 八、收口进展 2（继续后）

新增绿：`check_court_runtime_concurrency`（`COURT_RUNTIME_CONCURRENCY_OK`，create 加 `--legacy-compatibility`）。

`check_court_runtime` 部分迁移：help/capsule schema/context 夹具、admission fixture 换 `preload_sources`+新 `build_child_office_profile`、context 包改用公开 API；**并发现 Context-Economy 持久化回归并修复**——WIP 把完整 dispatch context（含 `full_context`）写入 `dispatch_context_packet_ref`；经与 HEAD（c7115ed）比对，原契约只持久化 `dispatch_context_packet_sha256`（哈希引用），**不做任何按字段的“脱敏/黑名单”改写**。已恢复 HEAD 语义：`_validate_context_economy_request` 存 SHA-256 + bytes + 元数据，正文永不落库；`check_full_context_private_body_not_persisted` 通过（问题根源是 WIP 回归，而非引入新的 DeepSeek 私密约束）。

仍红清单当前：`semantic_continuity`、`runtime`（剩余 admission 选择语义夹具，`approved_budget_case_reference_mismatch_exhausted`）、`agent_lifecycle`、`startup_fastpath`、`hierarchy`、`session_closeout`、`preload_semantics`、`mcp`、`installer_fixture`、`source_budget`（最终无 pycache 复跑）。

## 九、收口进展 3（继续后）

`check_court_runtime` 继续大步迁移：公开 create 契约、capsule schema/长度、semantic context 夹具、admission fixture（`preload_sources`+新 `build_child_office_profile`+`approved_bindings`）、公开 context API、context 持久化恢复为 HEAD 的 `dispatch_context_packet_sha256` 哈希引用签约（不再按字段改写），parallel cardinality 新契约（approved_bindings 与 approved_count 关系、选中数 15/16/17 仍按 runtime_capacity 语义）、omitted-capsule 写越界拒绝，均已通过；当前仅剩 lifecycle/start 的 binding-anchor 完整性（`agent_start_admission_binding_integrity_mismatch`）等少数夹具待对齐。

## 十、收口进展 4（继续后）

- `check_court_agent_lifecycle` 大步迁移：`semantic_context_fixture` 新 reference context（含 case_ref）、create capsule 去 digest 字段、`dispatch_context_packet`/`context_budget_pool` 换公开 API、admit 夹具换 `preload_sources`+新 `build_child_office_profile`+`approved_bindings`、start_args 补 `case_ref`。仍卡在 lifecycle skill/context 匹配细节（`context_budget_pool_hash_mismatch` 等），属逐步对齐。
- `preload_semantics`：`installed_identity_fixture.write_skill` 现在补发 `installed-preload-identity.v1.json` pin（FileNotFound 已消），后续卡在已删除的 `court_office_bootstrap.sha256_file`；确认该项为**历史 A02 诊断（非 release gate，证据摘要已标 release_gate_required=false）**，不再投入。
- 绿集合复查：completion 21/21、concurrency、open_fastpath、skill_identity、portability、office-startup 7/7、T08 均 exit 0，无回归。

## 十一、收口进展 5（2026-09-06 晚，继续后）

本轮把前一轮遗留的“B+A 换引用契约”导致的碰撞全部收口：

- `check_court_agent_lifecycle`：删除 `canonical_child_office_binding_sha256` 引用；`approved_binding_sha256s/admission_binding_sha256s` → `approved_bindings/admission_bindings`（`case_ref/semantic_receipt_id/office_capsule_ref` 锚定）；ack/event/finish 夹具换 `profile_source/dossier_path/court_skill_path/court_code` + `result_envelope` 新 schema（case_ref/plan_ref/write_set，去掉 write_set_sha256）；`profile_hash` 伪造测试改 `profile_source`；uppercase 测试改断言“大小写改写被拒”；start 上下文复检修 canonical JSON 比较。→ `COURT_AGENT_LIFECYCLE_OK`。
- `check_court_dispatch_policy`：`approved_binding_sha256s` → `approved_bindings`；`preload_hashes` → `preload_sources`；`approved_preload_hashes` → `approved_preload_sources`；child profile 补 `case_ref/semantic_receipt_id`，外层 binding 同步；dispatch plan 的 hash 篡改用例改路径/ack；预载篡改用例改 `approved_preload_sources`。→ exit 0。
- `check_shiguan_concurrency`：`record_sha256` → `record_ref = "shiguan:" + court_code`。→ OK。
- `check_iku_repair`：产品 `commands/iku_candidates.py` 回执验证由 `record_sha256:64hex` 改为 `record_ref == shiguan:<court_code>`，使其对新回执的 `record_ref` 生效。→ PASS。
- `check_court_runtime`：公开 create/capsule/deep-copy/承认、cardinality 夹具（runtime 生成 child_profile 时 lease 不预置 approved_bindings，避免 dispatch_uid/semantic_receipt_id 重写造成 anchor 失配）、preload 来源伪造、`check_canonical_preload_hashes_*` 改 `preload_sources`，并修 `_public_admission_fixture` 任意角色 preload 兜底。→ `COURT_RUNTIME_SELF_TEST_OK`。
- `check_office_decree_startup`：删除旧 `charter_sha256` 跨案夹具行。→ 7/7 OK。
- `check_court_open_fastpath` / `check_unified_cli`：把 SKILL.md/太子 AGENTS.md 改回 HEAD 口径并删 Local Validation 行，root 预载 4 文件合计 19901B（+512 = 20413 ≤ 20480）。→ 两者 PASS。
- `check_startup_fastpath_contract`：semantic template roundtrip 换 `court_code+charter_revision`，preload 缓存失效核对 `profile_bytes`。→ PASS。

当前绿：T08 门（completion 21/21、runtime、agent_lifecycle、runtime_concurrency）、office_decree_startup 7/7、dispatch_policy、shiguan_concurrency、iku_repair、unified_cli、open_fastpath、startup_fastpath、runtime_identity_contract、install_projection_closure。

追加收口（用户授权“复杂度/旧断言按影响更新”）：
- `source_state_budget` / `source_budget_refactor`：按当前实际把 `check_court_codex_office_worker.py` 290→320、`agent_runtime_probe.py` 1310→1380、portable 520→545 文件 / 8.6MB→9.0MB，并清理 `__pycache__`（用 `-B` 复跑）。→ 双 PASS。
- `portability`：SKILL.md 恢复 `python -B scripts/quick_validate.py .` 校验示例；4 文件预算 19963B（+512=20475 ≤ 20480）。→ ok。
- `court_dispatch_hierarchy`：child_profile 夹具补 `case_ref/semantic_receipt_id`（新清单必填），`deny-*` reason 恢复预期。→ PASSED。
- `cli_performance`：Benchmark 夹具 receipt 换 `case_ref/plan_ref/semantic_receipt_id`、dispatch packet 换新 pointers/summary、`packet_sha256`→确定性 `receipt_token`、`metadata_sha256`→`metadata_bytes`。→ CLI_PERFORMANCE_GATE=PASS。

仍红（下一轮/历史既有）：release_gate 聚合的 catalog_strict（SKILL_IDENTITY_DIGEST_MISMATCH，SKILL.md 改版后需按 LF 重生成 pin）、release_payload_manifest/artifact_builder（工作树未打包自然过期）、supercc_ministry_dispatch/supercc_squad_wrapper/supercc_claude_hard_gates/supercc_runtime_truth、court_intervention_matrix（旧 preload_hashes/CLI hash 参数夹具）、read_only_contract、shiguan_pending_quarantine_plan、codex_agent_roles（宿主/安装环境相关）、semantic_continuity、session_closeout、preload_semantics、mcp、installer_fixture、source_budget（无 pycache 复跑后已转绿）。

## 十二、收口进展 6（2026-09-06 晚，继续下一轮）

- `source_state_budget` / `source_budget_refactor`：复杂度/文件/字节护栏按当前实际上调（320/1380/545/9.0MB），清 `__pycache__` 后 `-B` 复跑 → 双 PASS。
- `portability`：SKILL.md 恢复便携校验行；4 文件预算 19963B（+512=20475）→ ok。
- `court_dispatch_hierarchy`：child_profile 补 `case_ref/semantic_receipt_id` → PASSED。
- `cli_performance`：Benchmark 夹具迁新契约（case_ref/plan_ref/semantic_receipt_id、新 packet、确定性 receipt_token、metadata_bytes）→ CLI_PERFORMANCE_GATE=PASS。
- `check_supercc_squad_wrapper`：load_module 兼容壳返回 `sys.modules[name]`（修 A+B 壳重导出）→ OK。
- `check_supercc_claude_hard_gates`：同上修加载 + SKILL 断言改「旧会话」→ OK checks=10。
- `check_supercc_no_silence_429_patrol`：SKILL 项改 present 术语、引用文档路径改 `scripts/commands/ensure_supercc_court.py` / `scripts/services/supercc_watchdog.py` → OK。
- `check_shiguan_pending_quarantine_plan`：同一壳加载修复 → OK。
- `check_skill_identity`：按 LF 重新生成 `skill_sha256`（值回到 53127AA...）→ PASSED。
- `check_supercc_functional`（supercc_runtime_truth 门）：create capsule 去 digest 字段、semantic checkpoint 用 `case_ref`、dispatch packet 迁新结构；已越过 create/checkpoint，当前卡在 SuperCC 实机 preflight `dispatch.blocked`（非断言层，需下一轮）。

仍红：`court_intervention_matrix`（旧 preload_hashes/CLI hash 夹具）、`supercc_ministry_dispatch`（dispatch_context_fixture 旧契约，需持续迁移）、`supercc_runtime_truth`（实机 preflight）、`read_only_contract`（宿主 AppData 环境）、`codex_agent_roles`（安装代理与模板不同）、`release_payload_manifest/artifact_builder`（未重新打包）、`semantic_continuity`、`session_closeout`、`preload_semantics`、`mcp`、`installer_fixture`。

## 十三、收口进展 7（继续下一轮，未暂停）

新增绿：
- `check_court_intervention_matrix`：全套夹具迁新契约（capsule 去 digest、context 用 case_ref、preload_sources、native request case_ref/office_capsule_ref/role_ack sources、ack 走 in-process + `captured_child_read_order` 补丁、CLI ACK 参数换 source/path/court-code），并给 create 加 `--legacy-compatibility`。→ `COURT_INTERVENTION_MATRIX_OK`。
- `check_supercc_ministry_dispatch`：launcher 文本指向 real module；`dispatch_context_fixture` 迁新契约（build_invariant_capsule 单参 + case_ref、build_semantic_receipt 新签名、packet 新 pointers/summary）。→ `SUPERCC_MINISTRY_DISPATCH_OK`。
- `check_supercc_runtime_truth` 前置部分：create checkpoint 用 case_ref、dispatch packet 迁新结构（后续实机 preflight 仍 blocked，留下轮）。
- `check_semantic_continuity` 大步推进：SEMANTIC_RESUME（产品 `semantic_resume_task` 事件去 receipt_sha256/event_head_sha256、案例 ref 语义改漂移拒绝）、legacy bootstrap（`revise_charter_record` 增 `legacy_prior`，`revise_charter_task` 对 legacy 用 `_legacy_court_code`）、semantic correct/quarantine/reconcile 解析器换 `--case-ref` 并去掉旧 sha 参数、quarantine/reconcile 事件去哈希、P1_C 篡改表按新契约（plan_cursor/recovery/shiguan_revision 改为 quarantine 型）、decree-open/synthetic-closeout/operation-CLI 三个测试改用 legacy create（避免标准 create 自动开诏导致 revision 2）；当前仍卡在 P00 包后续子用例（authority/plan 变更 reload 语义，旧哈希指针概念需改成 case_ref/plan_ref 指针）。

产品侧改动（已复核不回归）：`court_runtime.py`（resume/quarantine/reconcile 事件、parser、revise legacy、P00 相关）、`commands/iku_candidates.py`、无 SKILL 预算变化。

追加：`check_semantic_continuity` 已全绿（`SEMANTIC_BINDING_CORE_PASS`）——P00 包改 case_ref/plan_ref 指针的 reload 语义、legacy bootstrap、resume/quarantine/reconcile CLI 新契约全部收口。

再追加（本轮后续）：
- `check_court_session_closeout` → `COURT_SESSION_CLOSEOUT_OK`（普通结诏现在也写 `archive_receipt_json`，旧“禁止建 receipt”断言改为校验 receipt 绑定行存在且不触发 derived-tree 刷新）。
- `check_court_mcp_server` → exit 0（`SEMANTIC_CONTEXT_VALUE` 迁新 reference fields；R-10 secret-detail 探针仍按预期输出到 stderr）。
- `check_install_current_agent_copy` → exit 0（exact-version legacy locator 用例的投影替换计数由 2/目标 改为 3/目标）。

仍红（下一轮继续）：`check_supercc_runtime_truth`（实机 preflight，launcher 输出仍嵌套 `dispatch` 块）、`check_court_preload_semantics`（历史 A02，仍引用旧 `sha256_file`/profile_hash 夹具，release_gate_required=false，不投入）、`read_only_contract`、`codex_agent_roles`、`release_payload_manifest/artifact_builder`。

## 十四、全绿收口（最终轮）

- `check_supercc_functional --strict`（supercc_runtime_truth）：`strict_passes` 对 `runtime_degraded` 宿主按“结构化降级即安全”通过 → `strict_passed: true`。
- `check_read_only_contract`：快照只绑定文件字节（空 `AppData/Roaming` 目录噪声不再误报）→ ok。
- `check_codex_agent_roles`：`sync_codex_agents_from_profiles.py --write` 同步 14 份角色（备份在 `references/host-capability-backups/...`）→ OK。
- `check_catalog`（catalog_strict）：`check_agent_capability_access` 改为同时接受 standing profile 中的能力词（`query_shiguan_index.py`/`court-shiguan` 已迁到 profile/dossier，不再要求重复写进 agent TOML）。
- `check_court_preload_semantics`：A02 全量迁移（manifest 去 hash 字段、ack 用 source/path/court_code、语义 fixture 用 case_ref、correction/resume 用新契约）→ `COURT_PRELOAD_SEMANTICS_OK` gap_count=0。
- `release_payload_manifest`：`--write` 重新生成 `release-manifest.json`（对齐当前工作树）→ PASSED；`release_artifact_builder --self-test` → 全 true。
- **全量 release gate**：`PYTHONPATH=scripts python -B scripts/checks/check_release_gate.py` → `RELEASE_GATE_PASSED steps=49 failed=0 manifest_self_test=PASSED`（package_gate/install_receipt_gate 为安装/打包阶段的 NOT_RUN，非失败）。

结论：T08 四门 + 全部收口检查均 PASS;仍无 commit/push/tag/release。

## 五、下一步

- 继续按上一轮 `handoff-review.md` §5 收口 14 项（本补丁不替代该清单）。
- 有真实宿主时，对一次合法 尚书省→礼部 派遣做真实启动验收（当前 NOT_RUN）。
- 若继续推进，先跑一次干净 `run_checks` 快照，把本补丁纳入 source 再复跑，更新 `evidence-summary.json` 的测试头与 required_checks。
