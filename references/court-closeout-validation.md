# Closeout And Validation / 结诏与校验

## Unified Dynamic Dispatch Semantics

1. 官署按任务职责、依赖和证据价值动态分配。
2. 实时容量与请求预算是运行门禁，不是模式固定人数；整棵 agent tree 受 max_threads=16（含根线程）和 max_depth=4 约束，未知容量、占用、终态节点保留数、回收状态或深度时 fail closed。
3. superCC 固定显性太子+三省，但这不限制尚书省非显性、真实派遣有用六部。
4. 普通 super并行不使用 superCC pane、office show delay、wake 或 closeout-silence；其普通 spawn 展示延时为 0。

渐进加载注记：本卷由原 `SKILL.md` 顶级章节机械迁移而来，保留原文语义用于按需加载。新的短 `SKILL.md` 是入口、硬门禁与直接索引；本卷是该入口直接链接的 governing reference。若旧文出现“必须写入 SKILL.md”等位置性表述，在本次渐进加载结构下解释为：硬门禁、触发、三权、只读、安全、状态机、史馆/记忆、语义再载入、奏报模板等规则必须在短 `SKILL.md` 保持摘要和直链；细节规则可写入本卷等直接链接 governing reference。史馆仍只作证据与召回锚点，不替代本 skill 源文件与 governing references。

本卷章节：`Long Conversation Drift Guard`, `Completion/Pause Semantic Reload`, `Official Report Contract`, `Memorial Format`, `Installation And Validation`。

## Contents

- [Long Conversation Drift Guard](#long-conversation-drift-guard)
- [Completion/Pause Semantic Reload](#completionpause-semantic-reload)
- [Official Report Contract](#official-report-contract)
- [Memorial Format](#memorial-format)
- [Installation And Validation](#installation-and-validation)

## Moved Source

## Long Conversation Drift Guard

Use this guard before any final answer after a long-running task, interruption,
resume, context compaction, or multi-stage 史馆 chain:

1. Reconstruct the active decree from the latest user request, current approval
   mode, fixed `/court` state, non-goals, and the most recent relevant 史馆
   record.
2. Run a 门下语义复核 against the draft final answer: it must answer the newest
   user request, preserve the active `/court` state, use the court labels, and
   avoid generic project-manager or installer-style closing language.
3. Do not copy a 史馆 record's `next` field verbatim into the final answer if it
   would violate the Memorial Format, the user's latest request, or higher-level
   response rules. The record is evidence; the final answer is a court memorial.
4. If the final answer drifts into task-specific prose such as "the user can copy
   this file" without the court framing, rewrite it before sending.
5. In Windows PowerShell, read skill files and 史馆 files with explicit UTF-8
   when possible, e.g. `Get-Content -Encoding UTF8 -LiteralPath ...`. If Chinese
   court labels appear as mojibake during a plain terminal read, treat that as an
   encoding display issue unless the UTF-8 read confirms file corruption.
## Completion/Pause Semantic Reload

This is mandatory for `/court` whenever a decree is completed, paused, blocked,
cancelled, handed off, interrupted, or about to emit a final memorial after a
long context. It counters context drift by reloading the court's bottom-layer
semantics immediately before the user-facing close or pause report.

Light closeout: no-write exact short-reply and connectivity tests may use a
compact two-layer closeout, but they still reach `结诏`, `史馆实录`, and
`记忆裁定`. The compact user-facing record contains the requested offices,
actual host dispatch/reuse/wake evidence, exact replies, any degraded host
reason, and the fact that no durable target file or external state was changed.
The Shiguan layer writes a small archive checkpoint with `memory_decision=SKIP`
unless filesystem writing is unavailable or the newest decree explicitly blocks
audit writes; in that case report `史馆实录：FAILED` or
`史馆实录：authority_blocked` with the reason. Keep this light path cheap: do not
start Shiguan Web services, inspect pending queues, run Obsidian/GBrain/tree
refresh, reload all closeout shards, or require the full fourteen-line memorial
merely to report the short probe result.

Semantic reload source:

```text
<this skill>/SKILL.md
```

Reload only the semantic nucleus needed for the closeout unless a dispute
requires more:

- `Core Semantic Contract`
- `三省六部 Semantic Bedrock`
- `State Machine`
- `Long Conversation Drift Guard`
- `Completion/Pause Semantic Reload`
- `Dispatch Rules`
- `Official Report Contract`
- `Memorial Format`

Procedure:

1. 太子/户部 reads the current `SKILL.md` with explicit UTF-8 when tools are
   available. Prefer targeted section reads/searches over dumping the whole file.
2. 太子 reconstructs the active semantic charter from the latest user decree:
   `旨意`, `非目标`, `任务边界`, `允许动作`, `禁止动作`, `验收标准`,
   `证据要求`, `停止门禁`, and `史馆记录策略`.
3. 门下省 performs a semantic reload review against the combined closeout: the
   user-facing short memorial plus the complete Shiguan memorial. Office labels
   must carry their actual duties, state gates must not be skipped silently,
   execution authority must not expand scope, verification and 史馆 evidence must
   be present or explicitly unavailable, and the newest user correction must
   override older memories. For a skill-behavior correction, 门下省 must also
   confirm that the corrected durable rule is present in this `SKILL.md` and
   that the complete Shiguan memorial cites the changed path/line or validation
   evidence before Done or packaging is allowed.
4. 门下省 applies the hard memorial gate below. `semantic_reload: RELOADED` is
   allowed only when the final/pause/blocked/handoff report itself follows
   三省六部 semantics through the two-layer closeout. If the user-facing draft is
   a generic summary, a terse completion note, lacks a Shiguan anchor, or if the
   complete Shiguan memorial omits hard-gate fields, mark the result
   `DRIFT_CORRECTED`, rewrite the report in court form, and only then send it.
   Semantic audits, skill edits, one-by-one 朱批 rounds, and "nothing changed"
   findings are not exempt when they actually close, pause, block, cancel, or
   hand off work: that closeout still uses the two-layer memorial. The pending
   朱批 question itself is not a closeout and must use `太子上奏下一项问题：...`
   instead of the `结诏` template.
   `brief` may compress user-facing field content, but it must still render the
   approved fourteen `用户侧短结诏` labels in order. It must not replace the court
   template with prose summary, bullets, renamed labels, omitted labels, extra
   top-level labels, a misplaced Shiguan note, or missing hard-gate fields from
   the complete Shiguan memorial.
5. If drift is detected, revise the closeout or return to the appropriate court
   state (`三省会审`, `尚书分派`, `门下复核`, or clarification) before answering.
6. If `SKILL.md` cannot be read because the runtime lacks filesystem access or a
   tool is unavailable, report `semantic_reload: FAILED/runtime_degraded`, use
   the most recent loaded skill excerpt as a fallback, and do not pretend the
   reload succeeded.
7. Record compact evidence and the complete process/memorial body in 史馆 when
   filesystem writing is available. Use `archive_checkpoint.py` with
   `--full-record` or `--full-record-file` whenever the checkpoint closes a
   decree, changes behavior, records packaging, or otherwise has replay value;
   `summary` and `evidence` are only index fields. The full body must include
   stage checkpoint anchors or a compact replay of prior stages, sections
   reloaded, result (`RELOADED`, `DRIFT_CORRECTED`, or `FAILED`), changed wording
   or state decision, complete gate fields, and any memory decision. Do not paste
   long `SKILL.md` excerpts into the user-facing short memorial.
8. After the checkpoint succeeds and before the user-facing closeout, prefer the
   fast closeout path: `archive_checkpoint.py` returns the current
   `court_code`/lineage and writes an async refresh request for the Shiguan
   daemon. Do not block ordinary final answers on full `grow_shiguan_tree.py` or
   Obsidian filesystem sync. When release validation, migration acceptance, or
   the newest user decree explicitly requires the vault to be current before
   final output, run `python -B scripts/shiguan_autosync_daemon.py --once
   --force-sync` and require `ok=true`, `preserve_only=true`, and `removed=0`.
   Otherwise, report the refresh as `async_requested` rather than claiming the
   Obsidian cache was already refreshed.

Hard memorial gate:

Before any closeout leaves 太子, 门下省 must check the complete Shiguan memorial
for these required semantic fields. Missing fields are a rejection condition
unless explicitly marked `NOT_APPLICABLE` with a reason grounded in the decree.
The user-facing short memorial may project only the approved key fields listed
in `Memorial Format`. Its first `诏令编号` line is the user-facing Shiguan
record anchor; `source` and `record_uid` are auxiliary indexes for the complete
Shiguan record, not user-facing anchors. The user-side `史馆` line shows only
the usable Shiguan Web address: `local_url` plus any `lan_urls` reported by
the source-tree Shiguan web extension when explicitly requested. If the service is unavailable or unknown, show
the ensure command, the manual LAN server command, and the static fallback path
instead of silently omitting the Web address.
Showing a Web address does not approve public exposure, tunneling, management
writes, imports, or token/admin operations; those still require separate
approval unless already covered by the active decree.

- `太子定性`: newest decree, semantic charter, and non-goals.
- `三省会审`: concrete 中书省 intent/acceptance criteria, 门下省 risks/approval
  conditions, and 尚书省 dispatch/feasibility judgment.
- `三省上奏`: the petition or reviewed finding submitted upward.
- `太子回奏`: the user-facing synthesis, not a raw internal note.
- `执行门禁` and `门下裁定`: approved/rejected/needs-context with reason.
- `尚书分派` and `六部并行办差`: performed offices and evidence, or
  `NOT_APPLICABLE`/`runtime_degraded`/`authority_blocked` with reason.
- `门下复核`: semantic drift, safety, verification, and record review.
- `验收证据`: `VERIFIED`, `PARTIAL`, or `NOT_RUN` with evidence/reason.
- `语义再载入`: `RELOADED`, `DRIFT_CORRECTED`, or `FAILED`, including reloaded
  sections and whether the hard memorial gate passed.
- `史馆实录`, `agente清理`, `记忆裁定`, and any relevant service/开朝 state
  required by the active decree.
- `decree_usage_estimate`, `usage_actuals`, `usage_rollup`,
  `usage_source_breakdown`, `token_usage_precision`, `token_usage_note`,
  `wall_clock_actual`, and `worker_elapsed_sum`. Exact token usage may be
  labeled `provider_reported` only when provider/runtime evidence exists;
  heuristic counts must be labeled `estimated`/`estimated_fallback`, and missing
  child office usage must remain `unavailable` or `PARTIAL`, not zero. These are
  开朝/结诏 gate fields, not a separate office, subagent, or dispatch obligation.
- When `superCC` is active, `runtime_selection_gate`, `supercc_runtime_family`,
  `runtime_client`, `runtime_selector_result`, `source_agent_label`,
  `hermes_supercc_gate`, `hermes_surface`, `hermes_forced_profile`,
  `hermes_desktop_zellij_gate`, `hermes_profile_native_evidence`,
  `squad_fallback_gate`, `supercc_env_gate`, `visible_display_gate`,
  `display_transport_gate`, `office_client_gate`, `standing_officials`,
  `turn_start_health`, `turn_start_open_decree`, `turn_start_native_wake_policy`,
  `native_turn_start_wake`, `visible_zellij_panes`, `supercc_visible_core_roles`,
  `supervision_channel`, `supervision_evidence`,
  `silent_supervisor`, `supercc_watchdog`, `watchdog_process`,
  `watchdog_log_jsonl`, `watchdog_pid_file`, `watchdog_daemon_start`,
  `watchdog_daemon_stop`, `watchdog_no_visible_window`, `watchdog_actions`,
  `watchdog_abnormal_roles`, `functional_check_mode`, `supercc_side_effects`,
  `taizi_history_roundtrip_evidence`, `active_copy_sync`,
  `legacy_patrol_visible_pane`,
  `taizi_stale_explanation`,
  `supercc_concurrency_limit`,
  `office_duty_enforcement`, `taizi_substitution`, `context_packet_complete`,
  `six_ministry_step_plan_policy`, `ministry_silent_until_dispatch`,
  `closeout_silence`, `closeout_silence_policy`, `expected_silenced_roles`, and
  `temporary_ministry_release`, plus
  `rate_limit_wake_hierarchy`, `redispatch_actions`,
  `recommended_cleanup`, `noncurrent_inactive_pane_cleanup`,
  `office_profile_loaded`, `profile_source`, `office_dossier_path`,
  `light_bootstrap_policy`,
  `office_uniqueness_gate`, `task_evidence`, `direct_superior_source`, `dispatch_delivery_channel`,
  `native_enter_dispatch`, `post_dispatch_physical_enter_delay_seconds`,
  `squad_evidence`, `taizi_no_silence`, `three_departments_no_silence`,
  `no_silence_roles=[taizi, zhongshu, menxia, shangshu]`,
  `monitor_no_silence_roles`, `supercc_model_session_count`,
  `visible_active_office_count`, and `supercc_session_cap` are required closeout fields. Missing
  zellij+`squad` display evidence where a terminal-visible branch is selected,
  missing selected office-client evidence where Codex, Hermes CLI, or Claude Code panes are selected, missing
  zellij+`squad` normal-environment evidence for any normal superCC claim, missing
  Hermes profile/session evidence where Hermes readiness or profile dispatch is claimed, missing
  三省 standing pane evidence, missing native-enter/squad delivery evidence, missing second
  physical Enter evidence, missing message/task/reply/heartbeat evidence for a
  named office result, failed office uniqueness gate, duplicate active office
  identity, duplicate canonical pane, missing structured task/direct assignment
  evidence for execution dispatch,
  429/rate-limit pressure without `rate_limit_wake_hierarchy` / `supervision_channel` and
  requeue/stagger/backoff evidence, incomplete design context packets, attempted
  太子代工, unreleased/unsilenced temporary 六部, missing post-closeout
  `expected_silenced_roles` when closeout silence is claimed, an unexplained 太子 `last_seen` stale despite a
  visible `S Taizi #0001` pane, or Hermes/Claude readiness evidence reported as normal
  superCC without zellij+`squad` must be marked
  `runtime_degraded`, `authority_blocked`, or `DONE_WITH_CONCERNS` with
  preserved evidence and next action. If `office_duty_enforcement=FAILED` or
  `taizi_substitution=FAILED`, the closeout status must not be `DONE`. If
  `office_profile_loaded=FAILED` for a task that needed that profile, or required
  dispatch delivery evidence is missing, the closeout status must not be
  `DONE`.

If token budget is tight, keep the user-facing short memorial concise and put
the complete field set in 史馆; do not omit the complete field set. A short court
memorial with a Shiguan anchor is preferable to a fluent generic summary that
drops the 三省六部 contract.

Reload budget:

- Keep the reload compact and bounded; do not recursively reload after the
  reload checkpoint itself unless the user issues a new correction.
- Reload is not a replacement for 开朝 classification, 三省会审, verification,
  or 史馆实录. It is the last semantic gate that checks those duties survived the
  long context.
## Official Report Contract

Recursive subordinate reports use a short-memorial layer plus a full Shiguan
log layer:

For non-final replies, interim progress, clarification questions, code review
findings, blocked responses, or office-report samples, use
[sections/court-response-fewshot-format.md](sections/court-response-fewshot-format.md).
Final substantial closeout still uses the Memorial Format shard below.

- Recursive status labels are mandatory where the report is in Chinese court
  traffic: `草拟`, `审驳`, `奉行`, `部奏`, `待裁`, or `已决`. A report whose
  status label conflicts with its action is returned for correction by the
  direct superior or sealed/rejected by 门下省.
- A subordinate short memorial should stay compact and name the concrete direct
  superior. Use this shape unless a more specific office contract says
  otherwise:

```text
上奏：尚书省
身份：工部 agente
状态：部奏
要点：...
证据：...
史馆日志：AGLOG-...
请裁：...
```

- Full reasoning, command output, tool calls, long logs, failure traces, and
  corroborating materials belong in 史馆详录, not in the short memorial. The
  direct superior may request the subordinate's logs or inspect the Shiguan
  detailed record. Shiguan log inspection is normally approved as an internal
  evidence check; if the requested record contains secrets, private/sensitive
  information, credentials, paid/commercial exposure, or other gated material,
  the inspection request must be memorialized upward for裁决.
- If a subordinate, ministry, or department conclusion lacks traceable evidence,
  a Shiguan log pointer, execution boundary, concrete direct superior, status
  label, or evidence matching the requested action, it must not be marked
  `已决` or completed `奉行`. Mark it `待裁` or return it for补证. The direct
  superior may request evidence, narrow scope, or pause execution; 门下省 may
  seal/reject it; 太子 reports only the pending reason and missing evidence to
  the user and must not substitute judgment for absent evidence.

Every official or subagent report must include:

```text
report_tier: brief | standard | full
status: DONE | DONE_WITH_CONCERNS | REJECTED | NEEDS_CONTEXT | BLOCKED
court_status_label: 草拟 | 审驳 | 奉行 | 部奏 | 待裁 | 已决, when the report is recursive court traffic
direct_superior: concrete receiving office, such as 尚书省 or 工部, not abstract parent
role: taizi | zhongshu | menxia | shangshu | hubu | libu | bingbu | xingbu | gongbu | libu-hr | shiguan | zaochao
scope: what was inspected or changed
evidence: files, commands, MCP calls, observations
shiguan_log_pointer: AGLOG/shiguan source pointer, or why unavailable
skills_invoked: for each skill/tool asset called by a real office agente, list skill_name, purpose, input_boundary, allowed_actions, forbidden_actions, risk_level, evidence_output, and shiguan pointer; use NONE when no skill/tool asset was invoked
skill_call_contract: calling_office, skill_name, mandate, evidence_contract, stop_conditions, and escalation path; use NOT_APPLICABLE when no skill/tool asset was invoked
semantic_charter: 旨意, 非目标, 任务边界, 允许动作, 禁止动作, 验收标准, 证据要求, 停止门禁, 史馆记录策略
state_transition: from_state -> to_state, legal_basis, reject/pause/resume/cancel reason if applicable
office_semantics: which named duties were actually performed, delegated, skipped as NOT_APPLICABLE, runtime_degraded, or authority_blocked
historical_clue_judgment: likely_intent, memory_clues, confidence, likely_non_goals, next_step, or `历史线索不足`
edict_lineage: for 圣旨/诏书/敕书 work, the chosen model and document family, or NOT_APPLICABLE
edict_action_class: for edict work, the execution behavior class that drives document type, or NOT_APPLICABLE
edict_format_basis: for edict work, source basis and unresolved format choices, or NOT_APPLICABLE
three_departments_discussion: concrete 中书/门下/尚书 deliberation details before petitioning 太子
taizi_synthesis: 太子整理三省讨论后的 user-facing 回奏，包括计划、分歧/共识、余险、非目标和待问细节
detail_questions: concrete follow-up questions 太子 asks the user after整理回奏, or "none"
clarification_round_review: 本轮第 N 问、上一答复如何交三省复议、为何下一问仍必要、是否遵守超过两问逐轮回奏
parallel_dispatch: USED | NOT_APPLICABLE | runtime_degraded | authority_blocked, with reason
dispatch_plan_validation: NOT_APPLICABLE | PASSED | FAILED, with selected office roles, concrete duties, direct superiors, dependencies/parallel groups, evidence contracts, stop conditions, and visibility decisions
agent_dispatch_policy: NOT_APPLICABLE | PASSED | runtime_degraded, with topology, selection_basis, useful_roles, selected_roles, deferred_roles, host_capacity, effective_host_capacity, host_active, host_retained_agents, host_reclamation_status, available_slots, max_threads=16 including root, next_depth, max_depth=4, user_budget, provider_budget, preload_contract, fork_turns, context tokens, deadline, tool-call budget, no-reuse rule, and `court.agent.dispatch_message_budget.v1` evidence (`message_chars`, optional required/optional component counts, 6000 floor, 1000 quantum, 12000 ceiling, effective budget, status, overage/reduction, optional compression target, required-context overage, retryability, and compression/split guidance); no mode-fixed wave cap is permitted, unknown capacity/occupancy/retained-count/reclamation/depth must fail closed, malformed or inconsistent message measurements must fail closed, and no dispatch body may be stored or automatically truncated
multi_agent_protocol: NOT_APPLICABLE | serial | v1 | v2 | capability_conflict, with requested mode, selected mode, reason codes, schema/config mapping, and confirmation that one active tree never mixed protocols
protocol_switch_capability: NOT_APPLICABLE | VERIFIED | UNSUPPORTED_FAIL_CLOSED | FAILED, with exact SESSION_ID evidence, tool-namespace evidence, quiet-point fields, credential gate, operation idempotency, and whether the production engine was left untouched
agent_startup_latency: COMPLETE | PARTIAL | NOT_APPLICABLE, with dispatch_requested_at, host_session_started_at, preload_ack_at, first_office_report_at, finished_at, host_spawn_queue_ms, preload_ms, first_report_ms, and execution_ms. Missing timestamps must remain `unavailable`, never zero-filled. High host queue is attributed to host/model/provider startup; high preload to profile/dossier/SKILL validation; high first-report to task understanding/initial work; high execution to actual office work or stall. Ordinary-super records must not be attributed to SuperCC presentation delay.
agent_lifecycle_reconciliation: NOT_APPLICABLE | PASSED | PARTIAL | FAILED, with collaboration terminal state, court ledger final_status/release_status/finished_at/closed_at, circuit or wave block, interrupted siblings, and confirmation that raw provider details were not stored
heartbeat: alive/blocked/completed/runtime_degraded for long-running agente, services, or subprocesses
court_runtime: task_id, current_state, last_event, and whether `court_cli.py status` is current
decree_usage_estimate: NOT_APPLICABLE | PASSED | runtime_degraded, with estimated input/output/total tokens, estimated wall-clock range, mode, expected offices/subagents, expected tool calls, assumptions, and ledger/evidence path
usage_actuals: NOT_APPLICABLE | PASSED | PARTIAL | unavailable, with aggregated tokens/time at closeout and reason for missing exact counts
usage_rollup: provider_reported | agent_reported | estimated | mixed | unavailable, with total input/output/total tokens when known and `actual_source` values
usage_source_breakdown: list of per-office/subagent records containing office, office_instance_kind, office_transport, source, precision, input_tokens, output_tokens, elapsed_ms, task_evidence, and provider/runtime evidence pointer when exact
token_usage_precision: provider_reported | estimated | mixed | unavailable
token_usage_note: local estimates are not provider billing or exact model token counts unless source=provider_reported
wall_clock_actual: elapsed user-visible decree time when start/end evidence exists, or unavailable
worker_elapsed_sum: sum of elapsed office/subagent worker times; do not present it as wall-clock time under parallel execution
shiguan_web_service: RUNNING | REUSED | STARTED | NOT_STARTED | CHECK_ONLY | FAILED, with URL or fallback command; NOT_STARTED means the newest user boundary forbids service startup, while CHECK_ONLY means runtime/host limits allowed only probing
shiguan_import_queue: NONE | PENDING | FAILED, with pending_count, new_count, estimated_tokens, new_estimated_tokens, queue_root, samples, and whether 太子 asked/routed processing before raw text was loaded
pending_governance: NOT_APPLICABLE | METADATA_ONLY | HOST_CAPABILITY_REQUIRED_FAIL_CLOSED | AUTHORIZED, with ledger schema, trusted actor evidence, event/head verification, independently recomputed binding, body-operation counters, and explicit source-retention/no-delete result
obsidian_config_transaction: NOT_APPLICABLE | PASSED | FAILED | runtime_degraded, with config lock, base/current/committed revisions, three-way CAS conflicts, unrelated-field merge, secret-free public projection, post-write verification, and staging/parent durability evidence
peer_credential_lifecycle: NOT_APPLICABLE | PASSED | FAILED | runtime_degraded, with durable-view requirement, delivery state, plaintext/nonce persistence count, expiry validation, revoke-before-regenerate, duplicate replacement gate, protocol-switch credential gate, and confirmation that renew/extend/permanent cannot reactivate a revoked key
codex_yolo_startup_task: TASK_EXISTS | MISSING | GENERATED_REVIEW_TASK | REGISTRATION_REFUSED | REGISTERED | FAILED, with task name, generated review artifacts, log path, revoke command, or refusal reason
token_optimization_policy: PASSED | PARTIAL | FAILED | authority_blocked, with the three-level verdict for metadata precision, concise body references, and on-demand loading
metadata_precision: PASSED | PARTIAL | FAILED | NOT_APPLICABLE, with exact lineage/court_code/keywords/key_actions/source paths/task ids/evidence pointers needed for retrieval
body_reference_policy: PASSED | PARTIAL | FAILED | NOT_APPLICABLE, confirming bodies, quotes, logs, transcripts, and imported materials were summarized or cited compactly instead of copied wholesale
on_demand_loading: PASSED | PARTIAL | FAILED | NOT_APPLICABLE, confirming the court loaded only the needed governing references, compact Shiguan hits, source ranges, imports, or runtime artifacts
runtime_selection_gate: NOT_APPLICABLE | PASSED | runtime_degraded | authority_blocked, with selected visible zellij+squad branch and client/readiness evidence
execution_authority: approval | autonomous | super
execution_behavior: serial | parallel
execution_runtime: native | superCC, selected only by the distinct startup entry
execution_receipt: court.execution.native.v1 | court.execution.supercc.v1, with entry_path, transport, state_namespace, and neutral office_config pointer; native and superCC values must never appear as candidates or coexist in one task/process
court_open_capability_snapshot: NOT_APPLICABLE | PASSED | FAILED, with snapshot schema, registry path/state, cache HIT|MISS, lookup milliseconds, proposed skill/MCP/plugin/CLI/script allocations, and proof that the selected office context completed before Three Departments deliberation
court_open_dispatch_count: integer, required to be zero for serial behavior and every fail-closed semantic rejection
court_open_manual_bypass_allowed: false for every fail-closed semantic rejection
supercc_runtime_family: NOT_APPLICABLE | visible_zellij_squad
runtime_client: NOT_APPLICABLE | auto | codex | hermescli | hermes_desktop_readiness | claude | cli
runtime_selector_result: NOT_APPLICABLE or structured selector output path/summary
source_agent_label: Codex | Hermes | Claude | GenericCLI | Agents, matching the actual runtime writer
supercc_normal_env_requirement: NOT_APPLICABLE | zellij+squad
hermes_supercc_gate: NOT_APPLICABLE | PASSED | runtime_degraded | authority_blocked, with Hermes CLI/desktop readiness evidence plus zellij+squad if claimed as normal superCC
hermes_surface: NOT_APPLICABLE | cli | desktop
hermes_forced_profile: NOT_APPLICABLE | taizi | FAILED, with non-persistent activation evidence
hermes_desktop_zellij_gate: NOT_APPLICABLE | REQUIRED_FOR_SUPERCC_DESKTOP_PASSED | REQUIRED_FOR_SUPERCC_DESKTOP_FAILED | REQUIRED_FOR_SUPERCC_CLI_PASSED | REQUIRED_FOR_SUPERCC_CLI_FAILED | runtime_degraded, proving desktop/profile readiness did not bypass zellij+squad
hermes_profile_native_evidence: NOT_APPLICABLE | PROFILE_READINESS_PASSED | PASSED | PARTIAL | FAILED | runtime_degraded, with profile_home, skill/config/state/session evidence and no raw transcript bodies
squad_fallback_gate: NOT_APPLICABLE | PASSED | runtime_degraded | authority_blocked, with squad help/doctor or fallback/mirror evidence
supercc_env_gate: NOT_APPLICABLE | PASSED | runtime_degraded | authority_blocked, with the combined selected-runtime result
visible_display_gate: NOT_APPLICABLE | PASSED | runtime_degraded | authority_blocked, with current zellij pane/session evidence plus matching active squad identities for terminal-visible display
display_transport_gate: NOT_APPLICABLE | PASSED | runtime_degraded | authority_blocked, alias/evidence for zellij+squad terminal display transport
office_client_gate: NOT_APPLICABLE | PASSED | runtime_degraded | authority_blocked, with Codex CLI evidence when runtime_client=codex, Hermes CLI evidence when runtime_client=hermescli, Claude Code evidence when runtime_client=claude, or generic executable/args/prompt-mode plus cli_probe evidence when runtime_client=cli
office_identity_model: SAME_OFFICE_ABSTRACTION_DIFFERENT_TRANSPORTS | NOT_APPLICABLE, confirming spawned subagents, terminal-visible superCC panes, and Hermes/Claude readiness sessions are implementation variants of the same court office only when role/direct-superior/profile-or-dossier/task/report evidence is preserved
office_instance_kind: NOT_APPLICABLE | spawned_subagent | terminal_visible_pane | hermes_profile_session | taizi_single_process_degraded, with one value per claimed named office
office_transport: NOT_APPLICABLE | codex_subagent | zellij_squad_codex | zellij_squad_hermescli | zellij_squad_claude | zellij_squad_generic_cli | readiness_only_profile | single_process_degraded, with the proof path used for each claimed named office
office_identity_evidence: NOT_APPLICABLE | PASSED | PARTIAL | FAILED | runtime_degraded, with role, direct_superior, dossier/profile/context, task/direct assignment id, report path, and evidence pointer
standing_officials: NOT_APPLICABLE | PASSED | PARTIAL | runtime_degraded, with 太子 pane and 三省 squad/pane/heartbeat state when terminal-visible superCC was claimed
turn_start_health: NOT_APPLICABLE | PASSED | PARTIAL | runtime_degraded | authority_blocked, with `ensure_supercc_court.py --turn-start` evidence and repair result
visible_zellij_panes: NOT_APPLICABLE | PASSED | PARTIAL | runtime_degraded, with pane ids/titles for every named office whose terminal-visible superCC work is claimed
supercc_visible_core_roles: NOT_APPLICABLE or [zhongshu, menxia, shangshu], confirming visible core excludes 六部 and legacy inspection roles by default
zellij_visible_layout_policy: NOT_APPLICABLE or current visible-layout evidence; terminal-visible Codex/Hermes CLI reproduction keeps 太子 left and opens all other visible offices in the right-side column
supervision_channel: NOT_APPLICABLE or direct-superior watch map, normally 中书省->太子, 太子->三省, 尚书省->六部, 门下省->final evidence/drift review
supervision_evidence: NOT_APPLICABLE | PASSED | PARTIAL | FAILED | runtime_degraded, with owner/action proof for liveness, requeue/stagger/backoff/wake/re-dispatch, and report aggregation
silent_supervisor: NOT_APPLICABLE | PASSED | runtime_degraded, with non-popup script evidence when routine abnormal-close/429/silence supervision is claimed
supercc_watchdog: NOT_APPLICABLE | read_only | daemon | stopped | runtime_degraded, with `scripts/supercc_watchdog.py` command/evidence and whether recovery was read-only, daemonized, or stopped
watchdog_process: NOT_APPLICABLE | PASSED | FAILED | runtime_degraded, with process start/stop result when daemon mode is used
watchdog_log_jsonl: NOT_APPLICABLE or local JSONL path used for silent supervisor records
watchdog_pid_file: NOT_APPLICABLE or local PID record path used for daemon shutdown
watchdog_daemon_start: NOT_APPLICABLE | PASSED | FAILED, with hidden/non-popup startup evidence
watchdog_daemon_stop: NOT_APPLICABLE | PASSED | FAILED, required before closeout when this decree started a daemon that is not meant to persist
watchdog_no_visible_window: NOT_APPLICABLE | PASSED | FAILED, confirming no visible monitor pane, popup console, or GUI dependency was introduced
watchdog_actions: none, planned, applied, or runtime_degraded, with bounded recovery command evidence
watchdog_abnormal_roles: none, list, or runtime_degraded, with 429/abnormal-close/abnormal-silence classification evidence
functional_check_mode: NOT_APPLICABLE | read_only_audit | live_mutating | runtime_degraded, with `check_supercc_functional.py` command evidence when superCC validation is part of the decree
supercc_side_effects: NOT_APPLICABLE | PASSED | FAILED | runtime_degraded, with `court.supercc.side_effects.v1` schema evidence, selected_action, dry_run, mutates_runtime, planned_if_live, and applied; read-only checks must have `mutates_runtime=false` and no applied runtime changes
taizi_history_roundtrip_evidence: NOT_APPLICABLE | PASSED | PARTIAL | unavailable, using `squad history taizi --since <timestamp>` as the preferred end-to-end proof when terminal-visible Taizi-to-office roundtrips are claimed; pane output alone is weaker and must be labeled partial when history is available but not checked
active_copy_sync: NOT_APPLICABLE | PASSED | FAILED | runtime_degraded, with `scripts/sync_active_copies.py --json` evidence for `.agents`, `.codex`, `.claude`, `.hermes`, and the platform Hermes user-data copy when present
legacy_patrol_visible_pane: disabled
taizi_stale_explanation: NOT_APPLICABLE or explanation distinguishing visible S Taizi pane activity from stale squad last_seen heartbeat
supercc_concurrency_limit: NOT_APPLICABLE | PASSED | PARTIAL | runtime_degraded, with live Codex office session count, max allowed, 429 evidence, and requeue/stagger/backoff actions
office_duty_enforcement: NOT_APPLICABLE | PASSED | PARTIAL | FAILED | runtime_degraded, with each named office's implementation-specific evidence (spawned-agent lifecycle/dossier/task/report, visible pane plus squad task/message, or Hermes profile/session dispatch) and whether it performed its own duty
taizi_substitution: NOT_APPLICABLE | NONE | EXPLICIT_DEGRADED_FALLBACK | FAILED, with any 太子代摄/代工 reason and why it was or was not allowed
context_packet_complete: NOT_APPLICABLE | YES | PARTIAL | NO, with design-task context scope and redaction boundary when applicable
six_ministry_step_plan_policy: NOT_APPLICABLE | PASSED | PARTIAL | FAILED, with 尚书省 step plan, per-step verification, and packaging gate status
ministry_silent_until_dispatch: NOT_APPLICABLE | PASSED | PARTIAL | FAILED | runtime_degraded, with 六部/史馆 silence state and wake-dispatch evidence
closeout_silence: NOT_APPLICABLE | PASSED | PARTIAL | FAILED | runtime_degraded, with closeout-silence command/evidence and unfinished-office exceptions
closeout_silence_policy: NOT_APPLICABLE or final-结诏 rule that resolved agente except unfinished roles enter idle_receive
expected_silenced_roles: NOT_APPLICABLE or roles recorded as intentionally idle/silent after closeout; script supervisors may read this evidence but must not create visible monitor panes
temporary_ministry_release: NOT_APPLICABLE | RELEASED | RETAINED_BY_APPROVAL | runtime_degraded, with 六部/workshop release evidence
rate_limit_wake_hierarchy: NOT_APPLICABLE or zhongshu/taizi/three_departments/ministries/menxia owner/action map for 429 and stale wake responsibility
redispatch_actions: none, or 中书/太子/尚书-directed report/reminder/requeue/stagger/backoff/wake/repair or SQUAD_ONLY_FALLBACK_DEGRADED actions with evidence
recommended_cleanup: none, or read-only cleanup recommendations with mutation policy
noncurrent_inactive_pane_cleanup: NOT_APPLICABLE or dry-run evaluator results; candidates must be non-current or not visible/current, inactive/stale, and free of unresolved task/evidence/heartbeat or probe-failure blockers
office_profile_loaded: NOT_APPLICABLE | PASSED | PARTIAL | FAILED | runtime_degraded, with every claimed office's profile source/version when profile detail was needed
profile_source: NOT_APPLICABLE or standing-official TOML path(s) used for claimed offices
office_dossier_path: NOT_APPLICABLE or per-office `agents/supercc-dossiers/<role>/AGENTS.md` path(s) auto-loaded by the selected office client
light_bootstrap_policy: NOT_APPLICABLE or confirmation that long standing mandates are loaded from per-office AGENTS.md and launch prompts carry only compact manifest/current dispatch fields
office_uniqueness_gate: NOT_APPLICABLE | PASSED | FAILED | runtime_degraded, with active squad identities for the role, duplicate role-N identities, current-session canonical pane count, and whether dispatch was blocked or repaired
task_evidence: NOT_APPLICABLE | PASSED | FAILED | runtime_degraded, with structured squad task id or equivalent direct assignment evidence for execution dispatch; freeform squad messages alone are insufficient for claimed office execution
calling_office_source: NOT_APPLICABLE | explicit | role_default, proving whether the sender was user/script-specified or derived from 三省/六部 hierarchy
direct_superior_source: NOT_APPLICABLE or standing_profile/fallback evidence proving `calling_office` did not overwrite the assigned office hierarchy
dispatch_delivery_channel: NOT_APPLICABLE | NATIVE_DOUBLE_ENTER_VISIBLE | SQUAD_STRUCTURED_TASK_WITH_AUDIT_MIRROR_NON_VISIBLE_MINISTRY | SQUAD_TASK_AND_SEND | NOT_RUN_READINESS_PROBE_ONLY | SQUAD_ONLY_FALLBACK_DEGRADED | FAILED; current terminal-visible policy additionally requires `squad_delivery_order=SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER` and `native_enter_payload_kind=SUPERCC_SQUAD_RECEIVE_COMMAND`; default non-visible ministry success requires structured task id plus audit mirror and does not claim native-enter success; legacy `NATIVE_ENTER_FIRST_WITH_SQUAD_MIRROR` is accepted only as a compatibility alias for older terminal-visible native-first evidence, and legacy Hermes profile-native fallback wording is readiness/degraded unless zellij+squad and per-role dispatch evidence also exist
squad_delivery_order: NOT_APPLICABLE | SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER | SQUAD_NOTICE_BEFORE_NATIVE_ENTER | FAILED, proving the assignment/control note was queued before the pane receive-command Enter
native_enter_payload_kind: NOT_APPLICABLE | SUPERCC_SQUAD_RECEIVE_COMMAND | FAILED, proving the visible pane received the wrapper receive command rather than the full task packet
native_enter_dispatch: NOT_APPLICABLE | PASSED | FAILED | runtime_degraded, with pane id/title and zellij native-enter evidence
post_dispatch_physical_enter_delay_seconds: NOT_APPLICABLE | 1, confirming the delayed second physical Enter after the receive command
physical_enter_byte: NOT_APPLICABLE | 13, confirming zellij physical Enter uses byte 13 rather than byte 10 on this Windows Codex TUI path
squad_evidence: NOT_APPLICABLE | PASSED | FAILED | runtime_degraded, with squad message/task id or command evidence
taizi_no_silence: NOT_APPLICABLE | true, confirming 太子 remains awake for receive/heartbeat only
three_departments_no_silence: NOT_APPLICABLE | true, confirming 中书省/门下省/尚书省 remain awake for receive/heartbeat only
no_silence_roles: NOT_APPLICABLE or [taizi, zhongshu, menxia, shangshu]
monitor_no_silence_roles: NOT_APPLICABLE or [taizi, zhongshu, menxia, shangshu] by default; explicit diagnostics may append patrol-inspector
supercc_model_session_count: NOT_APPLICABLE or integer count of active visible Codex office model sessions
supercc_session_cap: NOT_APPLICABLE | null | legacy integer cap; current rule removes the fixed 5-agent cap and uses request-rate evidence instead
request_rate_limit_per_minute: NOT_APPLICABLE or integer, normally 20
model_request_budget_gate: NOT_APPLICABLE | PASSED | BLOCKED_TOTAL_REQUEST_LIMIT | runtime_degraded
usage_ledger_path: NOT_APPLICABLE or local `court-runtime/usage-ledger.jsonl` path used for estimate/actual records
usage_children_included: YES | PARTIAL | NO | NOT_APPLICABLE, with missing child/office usage names and why
package_ready_gate: NOT_APPLICABLE | PASSED | FAILED | NOT_RUN, with validation result and exclusion basis
package_exclusion_check: NOT_APPLICABLE | PASSED | FAILED | NOT_RUN, confirming no secrets/private vault/raw private Shiguan bodies/raw logs/generated local artifacts/plan archives/memory decisions/import queues are selected for packaging
runtime_degradation: none | runtime_degraded | authority_blocked, with the blocked/missing runtime capability, authorization gate, and chosen safe fallback
recursive_failure: none, or failing_layer/direct_superior/preserved_evidence/actions_not_run
verification_state: VERIFIED | PARTIAL | NOT_RUN, with command/output/source evidence or reason
semantic_reload: NOT_APPLICABLE | RELOADED | DRIFT_CORRECTED | FAILED, with SKILL.md sections reloaded and the outcome
hard_memorial_gate: PASSED | DRIFT_CORRECTED | FAILED, with missing fields or correction summary
petition_to_taizi: 三省上奏 text when the official is one of 三省 or requests execution
taizi_reply: 太子回奏 text or "pending"
execution_gate: APPROVED | REJECTED | NEEDS_CONTEXT | NOT_APPLICABLE
decision: approval, rejection, finding, or change summary
risks: unresolved issues and permission concerns
next: requested superior_office_action / 请上级官署裁处或分派
```
## Memorial Format

Detailed memorial format policy now lives in
[sections/court-closeout-memorial-format.md](sections/court-closeout-memorial-format.md).
This parent section remains the stable closeout anchor.

Load the shard for the exact fourteen-line user-facing memorial, the complete
Shiguan memorial template, `hard_memorial_gate`, Shiguan Web URL requirements,
and final drift checks.
## Installation And Validation

Detailed installation, validation, and package-ready policy now lives in
[sections/court-closeout-installation-validation.md](sections/court-closeout-installation-validation.md).
This parent section remains the stable closeout anchor.

Load the shard for concrete read-only validation, writeback validation,
Obsidian/export validation, catalog prerequisite handling, and package-ready
hard gates including `package_ready_gate`, `package_exclusion_check`, and the
rule that `package_skill.py` requires separate 太子回奏 authorization for the
current decree.

## Phase Review And Continuation Gates

`phase_level_tdd_review_gate` is mandatory at each material phase: first preserve
the failing `RED` proof, then reach `GREEN / SPEC`, and finally pass an independent
`QUALITY` review before declaring the phase closed.

`resume_correction_same_task_gate` keeps a continuation or correction on the
same task. It invalidates stale derived state, returns through Three Departments
（三省）, and requires a new phase closeout / 阶段结项 before packaging or handoff.
