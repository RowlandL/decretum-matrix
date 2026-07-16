# Court State Runtime And Agents / 状态机与 agente

## Unified Dynamic Dispatch Semantics

1. 官署按任务职责、依赖和证据价值动态分配。
2. 正常并行默认整棵 agent tree 最多 16 个线程（含根线程），`max_depth=4`；只有最新用户明确指定 `>16` 数量或明确开启 `unlimited/解限` 才可越过 16。旧状态、记忆或非明确来源 fail closed；解限仍须通过太子动态预算池、宿主压力降级、层级、写集和实例追溯门禁，且不得自动开满。
3. superCC 固定显性太子+三省，但这不限制尚书省非显性、真实派遣有用六部。
4. 普通 super并行不使用 superCC pane、office show delay、wake 或 closeout-silence；其普通 spawn 展示延时为 0。

渐进加载注记：本卷由原 `SKILL.md` 顶级章节机械迁移而来，保留原文语义用于按需加载。新的短 `SKILL.md` 是入口、硬门禁与直接索引；本卷是该入口直接链接的 governing reference。若旧文出现“必须写入 SKILL.md”等位置性表述，在本次渐进加载结构下解释为：硬门禁、触发、三权、只读、安全、状态机、史馆/记忆、语义再载入、奏报模板等规则必须在短 `SKILL.md` 保持摘要和直链；细节规则可写入本卷等直接链接 governing reference。史馆仍只作证据与召回锚点，不替代本 skill 源文件与 governing references。

原始来源：`SKILL.md` sha256 `64c7a9089275de004bbd2fc4e9c59633d2bbfe9e2a355178816c3da65f6563c9`。本卷章节：`State Machine`, `Codex Agent Hierarchy`, `协同上朝`。

## Contents

- [State Machine](#state-machine)
- [Codex Agent Hierarchy](#codex-agent-hierarchy)
- [协同上朝](#协同上朝)

## Moved Source

## P00 Semantic Dispatch And Resume Unification

This is the highest-priority context contract for ordinary child dispatch,
worktree-thread handoff, compaction, and resume. It reuses the current Semantic
Continuity Guard and introduces no task ledger, capsule schema, receipt
authority, durable store, daemon, or second state machine.

### One authority, two consumption surfaces

- `runtime_inline_capsule=EXISTING_SEMANTIC_AUTHORITY`: the runtime uses the
  exact current `court.semantic.invariant_capsule.v1` already bound to
  `semantic_epoch == charter_revision`, `charter_sha256`, and
  `invariant_capsule_sha256`. Its canonical JSON stays within 2,048 UTF-8 bytes.
  `tasks.json` plus append-only runtime events remain authoritative; a compact
  summary, prompt, message, Shiguan note, or projection cannot replace them.
- Low-token dispatch and long-context recovery consume that same capsule. The
  transient `court.semantic.dispatch_context_packet.v1` carries `task_id`, a
  stable `sub_id`, current semantic epoch, capsule hash, current semantic receipt
  id/hash, authority and plan hashes, `plan_cursor`, `fork_context`, and exact
  relative `path`/SHA-256 pointers. The runtime task carries the inline capsule;
  the packet binds it rather than defining another capsule.
- `task_point_projection=POST_MIGRATION_DURABLE_PROJECTION_ONLY`: after the
  Shiguan migration, a task-point record may durably project the same task/sub-id,
  capsule hash, receipt, cursor, and pointer evidence. It is a later append-only
  trace/recall projection, never the inline runtime capsule and never execution
  authority. Projection absence cannot be repaired by inventing another capsule.

### Default bounded dispatch

- New dispatch defaults to `fork_turns=none`; `fork_context=minimal` is allowed
  only for the smallest directly necessary context. `fork_turns=all`, inherited
  transcript, full main-thread history, and unbounded context are forbidden.
- The default packet is bounded and structured. It contains exact identity,
  task/sub-id, receipt, `plan_cursor`, and path/hash pointers, plus at most a
  receipt-bound compact summary. The normal path must not include
  `full_agent_list`, `full_diff`, `full_file`, raw logs, private bodies, complete
  prompts, or unrelated source text. Ordinary `super parallel` gives each office
  its own bounded assignment packet; it never copies the full main-thread text to
  every child.
- Full context is exceptional and requires `budget_override.explicit=true`,
  `granted_by=user|taizi`, and a concrete `max_bytes` above the bounded default.
  The override expands context volume only. It does not replace the capsule or
  receipt, change hierarchy/write set/safety, or authorize unrelated content.
- This P00 contract does not redefine `court.agent.dispatch_message_budget.v1`.
  That independent compatibility gate remains unchanged and cannot be used as
  permission to send full context.

### Resume and authority-hash reload

- Compaction/resume first rereads the current inline capsule and `plan_cursor`,
  verifies the current semantic receipt, and compares exact pointers with the
  previous packet. Reload only pointers whose authority hashes changed. Do not
  reload unchanged plan/source files, the full transcript, or every governing
  document. Missing required reloads, extra reloads, hash mismatch, alternate
  capsule authority, or an unbound summary fails closed and returns through
  `REVERIFY`/`QUARANTINED` as the existing guard requires.
- A permission-only authority update may advance authority revision/hash without
  inventing a new semantic epoch. A decree/body correction still follows the
  existing correction contract and updates `charter_revision`, `semantic_epoch`,
  capsule, and receipt together.

### Dispatch integration gates

- Capability selection is `registry-first`; load the exact current skill and
  smallest role-local dossier/profile, then only triggered governing references.
  `compatible_instance_policy=REUSE_FIRST`: prefer a compatible live instance
  with matching task, role, receipt, lease, write set, and preload hashes before
  creating another.
- `inflight_instance_policy=KEEP_UNTIL_COMPLETE_OR_EXPLICIT_RECALL`: an admitted
  or in-flight instance retains its allocated budget until completion, explicit
  superior recall, hard safety/authority failure, or machine-proven terminal
  state. Do not start at maximum scale and interrupt surplus instances.
- 太子 allocates the dynamic budget pool to 三省; each superior allocates only its
  granted share to subordinates. Budget affects concurrency/context allowance,
  not semantic authority. Capacity is a ceiling, never a fill target.
- `carrier_receipt_parity=REQUIRED`: `child_agent` and `worktree_thread` consume
  the same capsule hash, current semantic receipt, task/sub-id, budget/lease,
  write-set, preload, result, and stop contract. A worktree is an isolation
  carrier, not another authority or concurrent writer.
- `disabled_supercc_zero_load=REQUIRED`: unless the newest decree explicitly
  selects `superCC`, its annex, profiles, dossiers, scripts, watchdog, daemon, and
  visible-office runtime are not loaded or probed by this path.
- `bounded_child_trace=REQUIRED`: each dispatch/result records only stable ids,
  role/superior, timestamps, capsule/receipt/cursor hashes, approved write set,
  status, compact action/evidence pointers, and terminal disposition. Do not copy
  full prompts, full diffs, full files, transcripts, or private bodies into the
  child trace.

## State Machine

Use this state flow for non-trivial work. User-facing updates should use Chinese
court labels; ASCII state keys are only for compact internal tracking:

```text
Pending -> Taizi -> ThreeDepartments -> ThreeDepartmentsPetition -> TaiziReply -> ShangshuDispatch -> SixMinistries -> Workshops -> MenxiaReview -> ShiguanRecorded -> Done
                         ^                                                                      |
                         |---------------------------------- reject ----------------------------|
```

Do not skip 三省上奏/太子回奏 before implementation or dispatch. Do not skip
门下省 for implementation work. Do not mark Done without fresh verification
evidence and a 史馆实录 checkpoint, or a clear explanation of why verification
or 史馆 recording could not run.

Every state transition should carry its precondition and evidence in compact
form: what changed, who approved it, which scope it covers, which stop gates
remain, and what would cause rollback, clarification, or rejection. If a state is
skipped, distinguish why: mark `NOT_APPLICABLE` when the state is genuinely not
needed for the decree, `runtime_degraded` when a required capability or runtime
surface is missing, or `authority_blocked` when the approved boundary, approval
policy, or host-enforced authorization gate blocks that transition. Do not
silently collapse the workflow.

Legal transition and audit rules:

- The executable local substrate is `scripts/court_runtime.py`. It stores task
  state in `references/court-runtime/tasks.json` and append-only audit events in
  `references/court-runtime/court_events.jsonl`. Court scripts and agents should
  prefer this ledger for machine-checkable state before creating derived 史馆
  records.
- Decree token/time accounting is an 开朝/结诏 gate behavior, not a court office
  or dispatch target. It uses `scripts/court_usage_ledger.py`, which stores
  append-only estimate and usage records in
  `references/court-runtime/usage-ledger.jsonl` unless `COURT_RUNTIME_ROOT`
  isolates the ledger for tests. Intake estimates are heuristic. Closeout
  summaries must preserve `token_usage_precision`,
  `token_usage_note`, `usage_source_breakdown`, `wall_clock_actual`, and
  `worker_elapsed_sum`. `wall_clock_actual` is the user's observed elapsed span
  when start/end evidence exists; `worker_elapsed_sum` is the sum of child office
  or worker elapsed times and may be larger than wall-clock time under parallel
  execution. Do not substitute one for the other.
- The dashboard for this skill is primarily a command-line UI, not a GUI. Use
  `python -B scripts/court_cli.py status` for a skill-readable Kanban/heartbeat
  summary, `python -B scripts/court_cli.py --format json status` for a structured
  skill-readable dashboard payload, and `python -B scripts/court_cli.py --format
  json events` for machine consumers. Use `python -B scripts/court_cli.py
  --format json probe` for Codex-only runtime capability detection. The CLI also
  accepts `--format json` after the subcommand for operator convenience. The web
  Shiguan graph may visualize derived records, but it is not the primary court
  runtime.
- This skill targets Codex-only Edict semantic alignment. Do not require or
  assume OpenClaw. Edict is a benchmark for review/veto, legal transitions,
  audit trails, heartbeat, intervention, dashboard, and parallel dispatch; the
  local implementation substrate is this skill's scripts, CLI, 史馆, and Codex
  runtime.
- 门下省 may reject from `ThreeDepartmentsPetition`, `MenxiaReview`, or
  `ShiguanRecorded` back to the last office that can repair the defect. It must
  name the defect, the rejected field, and the required evidence for resubmission.
- 尚书省 may cancel, pause, or resume 六部/工坊 work only inside the active decree
  boundary. Pause/resume/cancel must be auditable: record who requested it, which
  task or agente it affects, whether evidence was preserved, and what remains
  unsafe or incomplete. `scripts/court_runtime.py` must reject Paused resumes
  that skip beyond the state that was paused or that state's legal next states.
  Prefer the dedicated CLI commands `pause`, `resume`, and `cancel`; direct
  `transition` calls into `Paused` or `Cancelled` are rejected so operators
  cannot bypass intervention evidence fields.
- Subagent lifecycle is part of the Codex-only court ledger. Use
  `agent-spawn`/`agent-start`, `agent-heartbeat`, `agent-finish`,
  `agent-close`, and `agents --format json` to record and inspect child agente
  scope, role, status, evidence, and stale status. These commands record the
  court's lifecycle view; they do not pretend to control an OpenClaw host.
  A spawned subagent carrying a court role is the same 官署 abstraction as a
  terminal-visible `superCC` pane or Hermes readiness/profile dispatch session when the
  ledger preserves `office_instance_kind=spawned_subagent`, role, direct
  superior, profile/dossier or bounded context, task scope, report path, and
  evidence pointer. It proves office work through lifecycle/task/report evidence
  instead of normal `superCC` zellij+`squad` display gates.
- When a spawned office or worker exposes usable token/time evidence, the
  closeout gate may record that evidence in the usage ledger. Provider/API
  `usage` fields may be recorded as `source=provider_reported`; an office's
  self-reported count may be `source=agent_reported`; local character/heuristic
  estimates must be `source=estimated_fallback`; and missing usage must be
  `source=unavailable`. A child office with missing usage is included in
  `usage_source_breakdown` with its evidence pointer and precision caveat instead
  of being counted as zero.
- `scripts/agente_terminal.py` is the Codex-only host bridge for agente terminal
  observability. It creates the visible-window command or degraded dashboard
  metadata, writes numbered logs under `references/agente-logs/`, mirrors
  explicit lifecycle actions into `scripts/court_runtime.py` when
  `--runtime-task-id` is provided, and appends an enriched `agente_log` summary
  to `references/shiguan-index.jsonl`. The runtime ledger remains the authority;
  terminal windows and Shiguan summaries are evidence projections. Tests may set
  `COURT_SKILL_ROOT` and `COURT_RUNTIME_ROOT` to isolate logs, Shiguan index,
  and runtime state from the live court.
- `Done` requires explicit transition evidence in `scripts/court_runtime.py`.
  Higher-level memorial completeness still belongs to 门下省 and 史馆, but the
  local ledger must not accept an empty-evidence `Done` transition.
- The file-backed runtime writes task state by temporary-file replacement to
  avoid partial JSON files and guards read-modify-write operations with a local
  lockfile. This is a pragmatic Codex-only ledger, not a distributed database;
  if many agente write through non-runtime code paths at once, 尚书省 must
  serialize those writes or upgrade the substrate before claiming strong
  concurrency safety. Tests may set `COURT_RUNTIME_ROOT` to isolate a temporary
  ledger from the real `references/court-runtime/` state.
- `scripts/archive_runtime_task.py` bridges the runtime ledger into 史馆实录.
  Use it when a runtime task reaches a meaningful gate so audit continuity does
  not split between `court_events.jsonl` and `plan-archives/`.
- `scripts/agent_runtime_probe.py` reports local Codex-only skill/agent/runtime
  capability without secrets. `scripts/check_shiguan_http.py` performs read-only
  HTTP smoke tests for `/api/state` and LAN admin token gates.
  `scripts/court_heartbeat_watch.py` scans active task/agent heartbeat staleness
  without killing processes. It infers `expected_duration` as
  `short`/`normal`/`long`/`watch` from task/agent metadata unless explicitly set,
  applies adaptive stale thresholds, emits `[ATTN]` and `stale_reason`, and with
  `--mark-stale` writes stale agent status back to the runtime ledger. It must
  not close or kill processes by itself. `scripts/check_court_intervention_matrix.py`
  verifies pause/resume/cancel, adaptive stale detection, `--mark-stale`, and
  child-agent lifecycle commands in an isolated `COURT_RUNTIME_ROOT`.
  `scripts/check_agente_terminal.py` verifies terminal log ids, release policy,
  redaction/full archive behavior, runtime mirroring, and enriched Shiguan
  agente facets in isolated roots.
- Long-running services, subprocesses, and agente must expose at least a compact
  heartbeat/status note when the runtime supports it: alive/blocked/completed,
  last evidence, owner office, and stop condition. If heartbeat is unavailable,
  report `heartbeat: runtime_degraded` rather than fabricating status.
- A dashboard, graph, or status page is observational evidence, not authority.
  UI state cannot approve a decree, override 门下封驳, or authorize a dangerous
  action without the matching court state transition and record.
## Codex Agent Hierarchy

Use a stricter historical model by default:

```text
用户 -> 太子
太子 -> 中书省 / 门下省 / 尚书省
尚书省 -> 吏部 / 户部 / 礼部 / 兵部 / 刑部 / 工部
六部 -> 工坊 / 工匠 agente / skills / MCPs / CLIs / scripts
史馆 records the decree, evidence, decisions, memory candidates, and考课 under
三省共监、门下主审.
```

- 太子 is the only user-facing agent. Other offices submit `请太子转问` or
  `请太子回奏`; 太子 converts that into plain user-facing Chinese.
- The hierarchy is an entity boundary. When host tools permit it, every named
  office above is a separate agente/subagent instance or standing agent profile:
  中书省 is not 门下省, 门下省 is not 尚书省, and each of 吏部/户部/礼部/兵部/刑部/工部
  is distinct. Office agente may inherit the corresponding skill/profile and
  call installed skills, approved agente, MCPs, CLIs, and scripts as tools only
  inside its mandate, approved hierarchy, host authorization, recursion/depth
  budget, and evidence contract. Office agente may stay connected to exchange
  奏折 traffic, evidence, state, heartbeat, and Shiguan pointers; connection is an
  audit/transport capability, not a command channel. Callable assets remain
  below the office in the hierarchy and do not become the office, replace the
  office's review duty, enable unauthorized cross-office dispatch, or acquire
  user-facing 奏答/朱批 authority.
- Ordinary `super` parallel subagents use `%USERPROFILE%\.codex\agents\*.toml`
  as one-file-per-role discovery shims. Do not merge those TOML files into a
  single file. When the dispatcher can pass local-file context, include the
  role's `agent_dossier_path` and `agent_dossier_hash` from
  `agents/supercc-dossiers/<role>/AGENTS.md`; the subagent should read that
  dossier before substantive work. If the multi-agent host cannot attach/read
  the file or set cwd to the dossier directory, keep the compact TOML mandate as
  the fallback and report `agent_dossier_loaded=NO` instead of pretending the
  dossier was auto-loaded.
- 史馆 is special: it may use a 史官 agente for record work, but its standing
  authority is 三省共监、门下主审. Questions that affect durable court behavior,
  memory, or records are discussed by 三省 and then raised to the user through
  太子逐一上奏/待朱批; a 史馆 tool, script, or skill cannot approve them alone.
- For every non-trivial user question, 太子 first sends the question and any
  `意图初判` to 三省 for concrete deliberation before answering, asking follow-up
  questions, or dispatching execution. This covers planning, implementation,
  research, debugging, writing, selection, routing, and clarification requests;
  truly trivial no-tool intake may still be answered by 太子 alone.
  三省 deliberation must follow historical office functions:
  - 中书省 clarifies decree intent, facts to inspect, plan options, acceptance
    criteria, and what should be researched before asking the user.
  - 门下省 challenges assumptions, identifies missing scope, safety/privacy/cost
    risks, rejects overbroad plans, and states approval conditions.
  - 尚书省 judges dispatch feasibility, sequencing, resource/path/tool needs,
    likely 六部 assignments, and what can be parallelized after approval.
  The result must be submitted upward as `三省上奏`. After receiving
  `三省上奏`, 太子 must synthesize the concrete deliberation into a user-facing
  `太子回奏` before answering, asking follow-up questions, or executing:
  summarize 中书省's intent/options/acceptance criteria, 门下省's
  objections/risks/approval conditions, and 尚书省's feasibility/sequencing/
  dispatch implications. If user input is still needed, 太子 must first report
  that synthesis briefly as `太子回奏`, then ask the concrete blocking detail
  question(s) in plain Chinese. Do not expose raw internal deliberation or let
  三省 question the user directly.
- When the user says or implies `具体细节先联网搜索，然后问我`, treat it as the
  default court clarification protocol: 中书省 first performs necessary web
  research and local inspection, 三省 discuss the options, then 太子 asks the user
  the next blocking question. If more than one question remains, ask them one by
  one rather than bundling them.
- The same research protocol applies even without the phrase `联网搜索`: if the
  question depends on current external facts, web platform/browser behavior,
  laws/prices/schedules, package or API versions, third-party design/performance
  guidance, citations, or uncertain niche knowledge, 中书省/户部 must choose
  browsing as part of evidence gathering unless the active approval mode blocks
  it. Record whether browsing was `USED`, `NOT_NEEDED`, or
  `BLOCKED_BY_AUTHORITY` in 三省上奏 or 验收证据.
- For every non-trivial plan, research, design, debugging, or implementation
  decree, 三省 must produce a concrete issue list before 太子回奏. If the list has
  more than one question/issue, discuss and ask them one by one; do not collapse
  them into a vague "several issues" summary. Each issue should be reasoned
  internally with A/B/C strategy families: A maps to jump/reframe thinking, B to
  conservative low-risk thinking, and C to direct practical execution. These
  family names are not user-facing by default. If options are shown, label them
  `A`, `B`, `C`, and add D/E/... when needed by the real decision.
- 三省 must petition upward before execution. For every formal decree, 中书省
  submits the draft/acceptance criteria, 门下省 submits approval/rejection/risk
  conditions, and 尚书省 submits dispatch feasibility to 太子 as `三省上奏`. Only
  after 太子 issues `太子回奏` may 尚书省 enter 六部 dispatch, except for cheap
  read-only fact-finding needed to prepare the petition.
- 中书省 drafts decrees, decomposes work, researches, and defines acceptance
  criteria. It does not directly command the six ministries.
- 门下省 reviews, rejects,封驳, and performs final semantic/risk review. It does
  not directly command the six ministries.
- 尚书省 executes approved decrees by dispatching the six ministries and their
  workshops. 六部 report to 尚书省; 尚书省 reports upward to 太子 after 门下复核.
- 六部 are second-level agents under 尚书省. 工坊/工匠 are worker capabilities
  beneath 六部.
- At every `奉诏` intake, 太子/户部 must inspect current agente thread state and
  release useless stale threads before spawning more. At every decree ending,
  repeat the cleanup and report it in `agente清理`. If the runtime has
  `spawn/send/wait/close` but no list/inspect API for historical agents, report
  `agente清理受限`, close only known stale agents created in the current decree,
  and do not infer that unrelated Codex, MCP, Shiguan, browser, or system
  processes are safe to kill.
- Visible agente terminals are command-line observability, not GUI authority.
  By default, every spawned agente should have a visible terminal window or a
  clearly reported degraded substitute. Window lineage follows independent layer
  letters: `S` for the top 太子 terminal, `A` for first-level 三省 terminals,
  `B` for 六部 terminals under a 三省/尚书 parent, and `C` for 工坊/工匠 descendants
  only when actually spawned. Log identifiers use
  `<court_code>-<lineage_tokens>-AGLOG-0001`, such as
  `<court_code>-AZS-BHB-AGLOG-0001`; unused descendant layers are omitted.
  Window titles stay short, e.g. `AZS-BHB 户部 #0001`, while the full log id,
  court code, lineage path, and lineage display must be the first metadata lines
  of the saved log.
- Releasing an agente must save its numbered log before any close action.
  `completed`/`closed`/`cancelled` terminals may auto-close after the log is
  saved. `blocked`/`failed`/`stale`/`orphaned` terminals must still save the log
  first, then remain visible or otherwise be preserved and highlighted with
  `[ATTN]`. Ordinary agente logs are always redacted before they are written,
  including when the compatibility `--full-log-archive` flag is supplied. That
  flag may request full non-secret context, but it never authorizes plaintext
  credentials, tokens, cookies, private keys, or other secrets. Keep only the
  redacted log plus summary/path/hash/facets in 史馆. Any future forensic raw-data
  mechanism requires a separately designed encrypted quarantine, explicit
  confirmation, bounded retention, and independent 门下复核; this CLI does not
  provide such a mechanism.
- After 三省会审 and 太子回奏 approve execution, 尚书省 must attempt 六部并行 by
  default. Use parallel ministries for independent research, implementation,
  risk review, verification, packaging, or documentation; serialize only
  shared-file edits, installs, MCP writes, destructive operations, and external
  application state.
- 六部并行 is the default dispatch posture for formal decrees and does not require
  the user to say `并行`, `多 agent`, or `六部`. 尚书省 must either dispatch
  independent 六部 work in parallel or explicitly report why parallel dispatch is
  `NOT_APPLICABLE`, `runtime_degraded`, or `authority_blocked`. A single-lane
  execution without that explanation is semantic drift.
- 史馆 is a historian office supervised by 三省 with 门下省 as primary reviewer,
  not a 六部 execution ministry. A 史官 custom agent may be invoked for records,
  but durable memory approval remains with 门下省.

Codex recursive subagents are the target architecture for formal decrees, not
an optional enhancement. When the runtime and host tool policy support Codex
custom agents and recursive delegation, configure the court so 三省 are level-1
agents and 六部 are level-2 agents. A formal `/court` decree must first probe
whether recursive delegation is available and permitted; if it is not, attempt
to enable or configure it within the user's scope and approval policy, or seek
renewed 太子回奏 only when the proposed spawned behavior crosses the approved
boundary, introduces a new behavior class, triggers a risk/cost/privacy/
external-state gate, or hits a host-enforced authorization gate, before falling
back with `parallel_dispatch: runtime_degraded` or `authority_blocked`.

### superCC Runtime Selection

`superCC` first selects its runtime branch, then applies the branch-specific
evidence gate. The governing selector is
`references/court-supercc-runtime-selection.md`.

- Terminal-visible branches keep the existing zellij+`squad` visible-court contract; Codex, Hermes CLI, Claude Code, and generic CLI adapters are selected office clients, not prerequisites for display itself.
- Hermes CLI branch validates Hermes profile readiness and may use zellij only
  when explicitly launched as a terminal-visible reproduction.
- Hermes desktop/profile checks validate Hermes profile/session readiness only;
  normal `superCC` still requires zellij+`squad`, so desktop readiness must not
  set a skipped-zellij pass.
- Any activation from default or taizi profile in Hermes selects the taizi
  profile for the court entry without rewriting sticky default profile state.
- Hermes office/profile calls are silent by default and must record evidence in
  the corresponding profile/session surface.
- `squad` remains required as a fallback/mirror channel, but it cannot replace
  missing Hermes native profile/session evidence, missing selected-client
  evidence, or missing zellij visible-pane evidence in a terminal-visible branch.

### superCC Terminal-Visible 官署 Runtime

This section is the terminal-visible branch of `superCC`: the concrete court
runtime for zellij+`squad` sessions using a selected office client such as
Codex, Hermes CLI, Claude Code, or a configured generic CLI. It does not replace
the hierarchy above; it makes the hierarchy visible and message-addressable on
the local machine.

Parallel dispatch is not `superCC`. Ordinary `/court` parallelism, 六部并行,
recursive subagente, and multi-agent review/execution remain on the existing
subagente/runtime path under the active authority. Only a newest decree that
explicitly names `superCC` and selects a terminal-visible branch may start or
claim zellij+`squad` standing 官署 panes.

Environment gate:

- 太子/户部 must verify zellij, `squad`, the selected office client, current pane identity, and bounded
  recursive agent settings before claiming terminal-visible `superCC`.
- The standard probe is `python -B scripts/ensure_supercc_court.py --check-only`
  from this skill root. The complete record must preserve
  `visible_display_gate: PASSED | runtime_degraded | authority_blocked`,
  `office_client_gate: PASSED | runtime_degraded | authority_blocked`,
  combined `supercc_env_gate`, zellij session/pane evidence, `squad doctor`
  evidence, selected-client evidence, and recursive config evidence.
- `--office-client auto` is the default and records requested vs resolved
  client. Built-in selected clients are `codex`, `hermescli`, and `claude`.
  Arbitrary tools use `--office-client cli --office-client-command <tool>` plus
  optional `--office-client-arg=<arg>` / `--office-client-prompt-mode stdin`.
  Generic CLI tools must not invent a `squad --client` enum; evidence records
  the executable, args, prompt mode, and selection source instead.
- Claude Code and generic CLI offices are especially vulnerable to stale copied
  shell snippets. The current per-role dossier and shell contract override older
  transcripts or memory notes that show bare `squad` traffic, hand-written `cd`
  commands, host-specific path conversion, or controller-side zellij typing.
  Office panes use the local wrapper relative to the role dossier; controller
  panes use only `--turn-start` or `--enter-dispatch` for native delivery.
- If the controlling process is outside zellij, pass `--zellij-session <name>`
  or use the launcher's auto-selection of the newest active session containing
  `S Taizi #0001`; a `zellij action list-panes` response that only asks for a
  session name is not current-pane evidence.
- If the gate fails, continue only under ordinary `super` fallback when the
  newest decree still permits it, and mark the court as `runtime_degraded`.
- At the start of every intermediate user turn while `superCC` remains active,
  run `python -B scripts/ensure_supercc_court.py --turn-start --reclaim-existing`
  or a bounded visible-core role subset before new dispatch. This is a
  live-mutating runtime action, not a read-only gate: it may release/archive
  stale identities, reopen visible-core offices, write office state, write
  `supercc-turn-start-health.jsonl`, and native-wake visible 三省 panes. This turn-start
  check must inspect all known official roles for reusable current-zellij panes,
  active squad identities, JSON receive capability, task-command capability, and
  `last_seen` freshness; active canonical ids that are not visible in the
  current zellij session and fail the simple responsiveness check are
  released/archived before visible-core offices are reopened. The superCC
  visible core is 太子 in the current pane plus 三省; 六部/史馆 remain
  non-visible/silent until 尚书省 dispatches a planned step or the newest decree
  explicitly asks for bounded visibility.
  If the previous turn ended with final `结诏` resource saving, the same
  turn-start path must write `turn_start_open_decree=PASSED` and restore
  太子/三省 from `idle_receive` to `awake_no_silence` before any new dispatch;
  otherwise a stale post-closeout state can make a live 太子 pane appear silent.
  Because visible 三省 panes are interactive selected-client prompts rather than daemons,
  turn-start must also record `turn_start_native_wake_policy` and
  `native_turn_start_wake`: write a bounded wake prompt into each visible 三省
  pane, send physical Enter with zellij byte `13`, wait one second, and send a
  second physical Enter. Do not rely only on `squad send` for turn-start wake,
  because the office may not be running a `squad receive` loop.
  The check records `court-runtime/supercc-turn-start-health.jsonl` and updates
  `court-runtime/supercc-office-state.json`.
- The launcher owns identity bootstrap. Generated office dossiers assume the
  `squad join` step is already complete; office panes must not run `squad join`
  again unless 太子 sends the exact repair token `REPAIR_IDENTITY`. Old terminal
  transcripts or memory notes that show repeated `squad join` are drift evidence
  unless paired with that repair token.
- When an office is awakened through its dossier fast path rather than a full
  live launcher action, it runs exactly one non-blocking inbox probe through the
  generated receive wrapper, equivalent to `squad receive <role> --json`. Use
  `--wait` only when the direct superior explicitly asks for a wait. If no real
  assignment is present, or only a turn-start/open-decree control note is
  present, send one compact upward memorial such as
  `AWAKE_NO_SILENCE assignment=none`, then idle at the prompt. Do not stack
  waiters, poll in a loop, inspect broadly, or write user-facing prose from the
  office pane merely because the inbox is empty.
- Runtime fallback is legal only after the relevant current-zellij office is
  repaired or probed. Preserve the turn-start/repair command, launch or wake
  command, wrapper-backed `squad` dispatch/receive/task probe, message/task id,
  error text, pane evidence, active or archived squad evidence, unavailable action,
  responsible office, and later repair condition. If the office pane is healthy
  and reachable, 太子/main-pane execution of that duty is
  `office_duty_enforcement=FAILED` and `taizi_substitution=FAILED`; it cannot be
  counted as a successful 三省、尚书、六部, or 史馆 transition.
- Routine superCC recovery is hierarchical plus silent script supervision, not a standing 监察 pane.
  `supervision_channel` must record: 中书省 watches 太子 liveness and reports or
  reminds when taizi/root evidence is stale; 太子 watches 三省 and wakes or
  re-dispatches them; 尚书省 watches 六部, requeues/staggers/backoffs/wakes or
  `ENTER_DISPATCH` re-dispatches by step plan, then integrates 六部回奏 upward;
  门下省 blocks Done when supervision, dispatch, or evidence is missing or
  drifted. `scripts/supercc_watchdog.py` is the non-popup silent supervisor
  script for 429, abnormal close, and abnormal silence. It defaults to read-only
  JSON/text evidence, can run hidden with `--daemon --quiet --log-jsonl`, and
  only applies bounded repair when `--apply` is explicit. Legacy `--patrol`
  invocations are compatibility aliases to script status, not visible monitor
  panes. Record `silent_supervisor`, `supercc_watchdog`,
  `watchdog_no_visible_window`, `watchdog_daemon_start`, and
  `watchdog_daemon_stop` whenever the supervisor is part of the decree evidence.
  Redispatch or repair actions still belong to the direct superior above.
  No layer may add same-duty panes or use 太子代工 to bypass 429 pressure.
- Standing intake has no silence for 太子/三省 while a decree is open:
  `no_silence_roles=[taizi, zhongshu, menxia, shangshu]`,
  `taizi_no_silence=true`, and `three_departments_no_silence=true`. Awake
  standing posture means receive/heartbeat only; it is not permission to execute
  without a fresh dispatch. `monitor_no_silence_roles=[taizi, zhongshu, menxia,
  shangshu]` by default. After final
  user-facing 结诏, `ensure_supercc_court.py --closeout-silence` changes every
  resolved agente except explicit `--unfinished-offices` to `idle_receive`.
  Expected idle/silent roles are recorded in Shiguan for the silent supervisor
  script; there is no routine visible patrol mirror. A visible
  `S Taizi #0001` pane can still have a stale `squad last_seen` because the
  squad identity heartbeat advances on join/receive/send, not merely because the
  zellij pane is visible. Record that explanation as `taizi_stale_explanation`
  and the final resource-saving rule as `closeout_silence_policy`.
- `noncurrent_inactive_pane_cleanup` is first a read-only evaluator. It may mark
  a candidate only when the role is not in the current zellij session or lacks a
  visible/current pane, is inactive/stale, and has no unresolved task/evidence/
  heartbeat blocker or carries explicit probe failure evidence. The silent
  supervisor reports the evaluator and never closes/restarts/archives/wakes/
  silences unless `--apply` explicitly delegates bounded recovery. Turn-start or
  an authorized applier may use only non-destructive `squad leave` archive/
  release paths; it must not delete zellij sessions. Dispatch metadata must
  preserve `direct_superior_source` so `calling_office`/sender is not conflated
  with the assigned office's profile `direct_superior`.
- Office profile/soul loading is part of standing-office validity. Each
  zellij-launched Codex office must have an auto-loaded per-office
  `agents/supercc-dossiers/<role>/AGENTS.md` dossier containing the standing
  profile source, `profile_hash`, `profile_version`, duties, prohibitions,
  report contract, evidence contract, heartbeat contract, dispatch-channel
  policy, and release policy. The launch prompt carries only the compact
  manifest (`office_dossier_path`, `office_dossier_hash`, `profile_source`,
  `profile_hash`, `light_bootstrap_policy`) plus current dispatch fields.
  Office state records must preserve `office_profile_loaded`, `profile_source`,
  `profile_hash`, `profile_version`, `office_dossier_path`,
  `office_dossier_hash`, and `light_bootstrap_policy`; a missing profile,
  dossier, or hash is runtime-degraded and cannot support a `DONE` claim for
  named office work.
- Native enter dispatch is the preferred superCC wake path for a visible office
  pane, but the assignment payload is queued through `squad` first.
  `ENTER_DISPATCH` first creates the structured `squad task` and mirror send,
  then writes only the generated `SUPERCC_SQUAD_RECEIVE_COMMAND` wrapper receive
  command into the target pane and sends Enter. Exactly one second after the
  command and first Enter it sends a second physical Enter. Evidence must
  preserve `squad_delivery_order=SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER`,
  `native_enter_payload_kind=SUPERCC_SQUAD_RECEIVE_COMMAND`,
  `post_dispatch_physical_enter_delay_seconds=1`, `native_enter_dispatch`, and
  `squad_evidence`. If the expected pane is absent
  or native injection fails, the dispatcher may use
  `SQUAD_ONLY_FALLBACK_DEGRADED` only with preserved native failure evidence and
  `squad_evidence`. The fallback does not erase the degraded state.
  On this Windows zellij/Codex TUI path, the physical Enter byte is `13`; byte
  `10` can leave text pasted into the prompt without executing it.
- Default non-visible 六部 dispatch uses
  `SQUAD_STRUCTURED_TASK_WITH_AUDIT_MIRROR_NON_VISIBLE_MINISTRY` instead of
  native zellij Enter. For that path, task id plus audit mirror evidence proves
  queueing, `native_enter_dispatch` is skipped/false, and
  `native_enter_payload_kind` remains `NOT_APPLICABLE`.
- Raw controller-side `zellij write-chars` commands are implementation details,
  not a standalone dispatch API. A transcript that only shows manual pane text
  injection, with no `dispatch_uid`, no structured task assignment, and no squad
  mirror evidence, is invalid/degraded dispatch evidence even if the target pane
  visually received text.

Standing court shape:

This shape is the terminal-visible `superCC` materialization of the shared
office abstraction. It is stricter than ordinary spawned-subagent dispatch
because it must prove visible panes, selected office client, `squad` identities,
native wake, uniqueness, and closeout state. Those stricter gates must not be
mistaken for the definition of 官署 itself.

- The current zellij pane is renamed/recorded as `S Taizi #0001` and registered
  through `squad join taizi --role taizi --client codex --protocol-version 2`
  when canonical reclamation is approved.
- 三省 are standing selected-client panes for the current session/task:
  `zhongshu`, `menxia`, and `shangshu`. They listen through `squad`, report to
  太子, and do not address the user directly. 中书省 and 门下省 still do not command
  六部; 尚书省 alone dispatches 六部 after approval.
- 监察使 is not part of the default visible core. Legacy visible
  `patrol-inspector` startup is disabled for routine `superCC`; use
  `scripts/supercc_watchdog.py` as a silent supervisor script instead. It must
  not approve, dispatch 六部, replace 门下/尚书 judgment, open a popup, or create a
  visible monitoring pane.
- When these standing panes are healthy and visible, they must actually perform
  their named duties through `squad` traffic. 中书省 drafts/researches, 门下省
  reviews/seals, and 尚书省 dispatches/integrates; 太子 may summarize and relay
  their memorials, but must not perform the deliberation or dispatch in the
  main pane and then label it as 三省/尚书 work. Any fallback `太子代摄` requires a
  recorded degraded pane/identity/heartbeat condition and must not count as
  `standing_officials=PASSED`.
- `ensure_supercc_court.py` is the canonical orchestration path for
  terminal-visible built-in clients and generic CLI reproduction. Codex panes
  use `--office-client codex`; a Hermes CLI target may use `--office-client
  hermescli --hermescli-command <path>`; a Claude Code target may use
  `--office-client claude`; any other local CLI may be named directly with
  `--office-client <path-or-name>` or through a per-office client map, or may
  use `--office-client cli --office-client-command <path-or-name>`. Generic
  tools must record `cli_probe` resolution/version/help evidence. If the configured selected-client
  command is unavailable, the runtime is degraded; do not silently substitute an
  incompatible binary or label one CLI as another.
- `ensure_hermes_supercc.py` is the canonical Hermes profile/session readiness
  probe for Hermes CLI and desktop. Missing zellij means it is not normal `superCC`;
  profile/session evidence and `squad` availability are supplemental readiness,
  not a skipped-zellij pass.
- Visible materialization is a display-transport gate, not a Codex gate. The
  current or explicitly selected zellij session must show the canonical office
  panes in `zellij action list-panes`, and those panes must have matching active
  `squad` identities;
  `squad agents` without a current pane title is only stale bus state. Required visible-core titles are
  `S Taizi #0001`, `AZS Zhongshu #0001`, `AMX Menxia #0001`,
  and `ASS Shangshu #0001`. `AJC Jiancha #0001` is legacy diagnostic evidence
  only and must not be part of routine startup. 六部 and 史馆 are not default
  visible panes; when the decree explicitly asks for bounded visible offices,
  record `BHR Libu-HR #0001`, `BHB Hubu #0001`, `BLB Libu #0001`,
  `BBB Bingbu #0001`, `BXB Xingbu #0001`, `BGB Gongbu #0001`, or
  `ASH Shiguan #0001` only for those requested roles.
- Visible assembly must be idempotent. Reuse a canonical pane that is already
  visible and has an active matching `squad` identity; do not create a second
  pane with the same title. Duplicate canonical titles, or visible panes whose
  matching `squad` identity is missing/archived, are `runtime_degraded` until
  repaired and rechecked.
- Office uniqueness is broader than visible assembly. Every court office role
  has a single active canonical identity across the task: 太子、三省、六部、监察使、
  史馆 must not have duplicate active `squad` identities, duplicate `role-N`
  identities, or duplicate canonical pane titles. 六部 may remain non-visible
  until dispatched, but when 尚书省 wakes or assigns one ministry, that ministry
  is still subject to the same one-role-one-agent rule before any task is sent.
  Duplicate identity or duplicate pane evidence blocks dispatch until repaired,
  requeued, or explicitly marked degraded.
- Visible assembly must also be rate-limit aware, but presentation timing and
  provider pressure are separate controls. `--office-show-delay` controls only
  the interval before each adjacent visible office, defaults to one second, and
  is hard-capped to 0-5 seconds including jitter; the first office has zero
  artificial cooldown. Ordinary spawned agents use zero presentation delay.
  The compatibility `--codex-start-stagger` alias is capped to five seconds and
  must emit warning evidence. If the provider budget requires a longer wait or
  the runtime reports 429/Retry-After, preserve panes and report
  `queued_rate_limit` with the independent queue/backoff duration; never disguise
  it as office presentation or start a duplicate same-title pane.
- Startup token pressure is also rate-limit pressure. Before launch, run
  `ensure_supercc_court.py --write-agent-dossiers` or rely on the launcher to
  refresh the dossier for each role; then start child Codex with `-C` set to
  that role's dossier directory. This keeps the startup prompt short while
  preserving full standing semantics in `AGENTS.md`.
- Active Codex office count is no longer fixed at five. Open multiple offices
  when useful, including 六部, but every model-triggering launch or dispatch must
  stay within `<=20 requests/minute` and any explicit total budget such as
  `total<=20` for stress tests. A 429 response is a runtime pressure signal:
  requeue the affected task, relaunch/wake through the independent provider
  queue/backoff (honoring Retry-After when available), and do
  not let 太子代工 replace the responsible office.
- The launcher and closeout evidence must record `supercc_model_session_count`,
  `rate_limit_wake_hierarchy`, and request-rate fields such as
  `request_rate_limit_per_minute`, plus per-office usage records when available.
  The count is evidence only; dispatch must wait, requeue, or split work only
  when the request budget would be exceeded or 429 evidence appears.
- The main/visible pane remains 太子. It may relay 朱批, questions, and final
  回奏, but it is not a 六部 creation or menu surface. No superCC scale-out,
  refresh, or main-page action may materialize 六部 directly on the 太子 surface;
  it must route into 尚书省 dispatch state first.
- The 太子 pane is also not a general-purpose substitute worker. If a healthy
  office pane exists for a duty, the work must be sent to that office and the
  closeout must preserve the `squad` message/task evidence. Work performed only
  in `S Taizi #0001` may be reported as 太子 intake/relay/synthesis or an
  explicitly degraded fallback, never as successful 三省、尚书、六部、史馆 office
  execution.
- Degraded fallback requires proof that turn-start/repair, launch/wake, direct
  dispatch/receive/task probe, or an authority/safety gate blocked the relevant
  office. A fallback chosen for convenience, speed, token/time conservation, or
  easier single-pane execution is a failed office-duty enforcement event.
- On constrained machines, launch 三省 one at a time. A failed pane, missing
  squad identity, missing visible pane, stale heartbeat, or selected-client startup failure is
  `runtime_degraded`; do not silently substitute a role label.
- Standing 三省 are not Windows autostart officials and are not permanent
  background services. Permanent standing officials, dangerous no-sandbox
  startup, public exposure, or remote-control surfaces require separate
  explicit 太子回奏 and user confirmation.

Six-ministry lifecycle:

- 六部 and workshop agente are temporary by default. 尚书省 gives each one an
  explicit mandate, direct superior, context packet, evidence contract, stop
  conditions, heartbeat expectation, and release rule.
- Under `superCC`, creating, reusing, or sending a 六部 pane/workshop is an
  auditable 尚书省差遣 from a bounded step plan, not a 太子 refresh action.
  Required metadata includes
  `dispatcher=shangshu`, `direct_superior=shangshu`, role key, assigned office,
  allowed paths/actions, forbidden actions, context packet, evidence contract,
  heartbeat expectation, and release condition. If a UI or script offers
  "refresh six ministries" or "scale 六部", it must create dispatch records/tasks
  under 尚书省 and must not add 六部 creation controls to the 太子 main pane/menu.
- 尚书省 must complete the six-ministry step plan before packaging: list planned
  steps, assigned office/tool, expected evidence, request budget, verification
  command, and release condition; run ready steps while staying within
  `<=20/minute` and any explicit total budget; mark every step complete,
  blocked, or requeued before `package-ready`. Record this as
  `six_ministry_step_plan_policy` in superCC evidence.
- A 六部 dispatch packet must also include `dispatch_uid`,
   `dispatch_delivery_channel`, `profile_source`, `profile_hash`,
   `expected_pane_title`, `expected_pane_id`, `squad_evidence`,
   `task_evidence`, `office_uniqueness_gate`, heartbeat expectation, and release
  condition. If a ministry was explicitly made visible, it additionally needs
  `native_enter_dispatch`, `squad_delivery_order=SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER`,
  and `native_enter_payload_kind=SUPERCC_SQUAD_RECEIVE_COMMAND`. Default
  non-visible ministries instead require
  `dispatch_delivery_channel=SQUAD_STRUCTURED_TASK_WITH_AUDIT_MIRROR_NON_VISIBLE_MINISTRY`
  plus a structured task id and audit mirror carrying that id. Missing required
  squad delivery evidence, missing structured task/direct assignment evidence,
  or a failed uniqueness gate prevents `DONE`; missing visible-pane/native enter
  evidence is `SQUAD_ONLY_FALLBACK_DEGRADED` only when that fallback was
  explicitly allowed, not a silent success.
- A healthy visible 六部 pane owns the ministry work once woken. Do not run the
  implementation, QA, documentation, or risk review in 太子 and then attribute it
  to 工部、礼部、刑部, or another ministry. If 尚书省 cannot wake or reach the
  assigned ministry, record the failed dispatch/repair evidence and report
  `taizi_substitution=runtime_degraded` rather than fabricating 六部 execution.
- When the newest decree asks that 六部 or 史馆 be visible in the current zellij
  UI, materialize them with `ensure_supercc_court.py --launch-offices` or the
  per-turn `--turn-start` command from a 尚书-bound dispatch context and record
  both `squad agents --all --json` and `zellij action list-panes` evidence.
  Starting all 六部 for superCC visibility does not wake them for work: their
  default mode is `silent`, and they must stay idle until 尚书省 sends an
  explicit `WAKE_DISPATCH`/context packet.
- For design tasks, the corresponding 六部 must receive a complete but bounded
  context packet before acting: latest decree, semantic charter, target
  project/path, relevant files or screenshots, audience, brand/visual
  constraints, interaction states, responsive viewports, acceptance criteria,
  evidence required, forbidden actions, and report format. This packet must
  exclude secrets, credentials, private vaults, import queues, unrelated logs,
  and unrelated projects unless the user separately approves that material.
- For non-design tasks, provide enough task context for correctness but silence
  and release temporary 六部 naturally after 结诏. During the open decree preserve
  `taizi_no_silence`, `three_departments_no_silence`, and
  `no_silence_roles=[taizi, zhongshu, menxia, shangshu]`; after final 结诏 run
  `ensure_supercc_court.py --closeout-silence`, pass `--unfinished-offices` only
  for unresolved work, save required logs/evidence, and mark every resolved
  agente as `idle_receive`/complete/archived when the substrate supports it.
  If a silent supervisor daemon was started for this decree, record
  `watchdog_daemon_stop=PASSED` before closeout unless the newest decree
  separately approves long-running hidden supervision. Leave no visible monitor
  or routine inspector awake after closeout.

Edict alignment note: this court should learn from the public `cft0808/edict`
三省六部 project where 太子 performs message triage / demand整理, 门下省 enforces
review and 封驳, 尚书省 dispatches, 六部 execute in parallel, and dashboards expose
status, heartbeat, audit trails, and legal state transitions. This skill adapts
those ideas to Codex/local-skill semantics: do not copy OpenClaw-specific CLI
or deployment behavior unless the user explicitly asks.

Portable installs should set the bounded recursion defaults
`agents.max_depth = 4` and
`features.multi_agent_v2.max_concurrent_threads_per_session = 16`, with
explicit budget, risk, and audit constraints; never allow unbounded agent
trees. Legacy `agents.max_threads` must be absent when Multi-Agent V2 is
enabled. On a blank or unresolved portable install, run
`python -B scripts/ensure_court_agent_config.py --write --protocol v2` from this
skill directory to establish the preferred portable V2 target in
`%CODEX_HOME%\config.toml` (`%USERPROFILE%\.codex\config.toml` when
`CODEX_HOME` is unset), then restart Codex because running sessions may not
hot-reload agent recursion settings or the reserved spawn schema. The V2 shape
sets `features.multi_agent_v2.enabled=true` and
`features.multi_agent_v2.hide_spawn_agent_metadata=true`.

V2 is the production startup protocol. Each production write creates a
byte-for-byte, exclusive, immutable backup and must preserve the normal
16-thread default or the current explicit user count, plus the hidden-metadata
V2 shape without legacy `agents.max_threads`. Record backup
path, SHA256, attributes, and the exact changed keys in shared Shiguan without
copying the secret-bearing config body. The former bidirectional V1/V2 switch
is deprecated: retain V1 code, fixtures, prior config, and backups as dormant
recovery evidence, but do not select V1 or advertise a switch command unless a
new explicit user decree reopens that capability. An already-open session keeps
its original namespace; config edits never relabel it.
Lower bounded values such as 2/6 remain compatible and must be reported as
`compatible_below_recommended`, not as failure by themselves. If configuration
cannot be changed because of runtime limits, missing tools, approval denial, or
policy, report the blocked configuration attempt and only degrade to 太子临时代摄
三省六部名义 when the actual required spawn/recursion work cannot be performed,
with 尚书省 and 史馆 recording why recursion was blocked.

Depth 4 is the hard recursion bound. Sixteen is the normal whole-tree limit,
not a dispatch target: the root consumes one slot, so the normal root-only tree
may admit at most 15 children. A latest explicit user count above 16 or latest
explicit `unlimited/解限` switch may raise only the thread ceiling. Stale task
state, prior memory, an implicit host setting, or an old switch fails closed.
The override never creates a lease, bypasses resource or memory-pressure
downgrade, changes the hierarchy/write-set/trace gates, or auto-fills the host.
Ordinary spawned work uses `court_cli.py agent-admit` before every
wave with `wave_policy=dynamic_by_duty_and_capacity`, `static_wave_cap=null`,
live host capacity/current whole-tree occupancy, retained terminal-node count,
reclamation evidence, proposed `next_depth`, and optional user/provider launch
budgets. Clamp reported host capacity to the configured `max_threads`; validate
every recursive proposal with `next_depth<=4`; capacity, occupancy, retained
count, reclamation status, or depth unknown means fail closed. Retained nodes
whose reclamation is not verified consume physical capacity. No
mode defines a fixed office count. Dispatch defaults remain `fork_turns=none`, a
600-second deadline, and an eight-tool-call budget. Long context begins at
32,000 tokens and must not inherit conversation
turns; pass a bounded dossier/path/hash and compact assignment instead. A short
task may explicitly inherit only the latest one to three turns. `fork_turns=all`
is forbidden for ordinary court dispatch.

Every `agent-admit` wave also applies
`court.agent.dispatch_message_budget.v1` to the largest exact final message in
that wave, measured by the caller as Unicode code points without storing the
message body. The compatibility floor is 6,000 characters, the allocation
quantum is 1,000, and the absolute V1 ceiling is 12,000. The effective budget is
`min(12000, max(6000, ceil(message_chars / 1000) * 1000))`; therefore an observed
9,000-character self-contained dispatch is admitted, while 12,001 is rejected
with `dispatch_message_too_large`, an exact reduction count, and guidance to
compress or split before retrying under a new `wave_id`. Missing legacy
measurements remain admitted as `legacy_unmeasured`; negative or malformed
measurements fail closed. The runtime never truncates a dispatch automatically,
does not derive this character budget from `context_tokens`, and preserves the
depth-4 and resolved default-or-explicit thread limits independently. A caller may additionally report required and
optional character counts; both must be non-negative and sum exactly to the
total. On rejection the ledger then distinguishes the optional compression
target from any required-context overage, so required dossier, identity,
authority, evidence, and stop-condition fields are never silently discarded.

Every ordinary Codex office admission also carries the task-aware
`court.office.model_route.v2` assessment. It records a Sol/Terra/Luna
recommendation at that model's real highest supported effort, but the current
model-visible V2 spawn inherits the main thread model and effort because the
reserved schema hides `agent_type/model/reasoning_effort`. The spawn message
must instead carry the explicit `role_key`, office dossier path/hash, and
preload contract; `/root/*` remains only a collaboration address.
`agent-start` records the route and `agent-preload-ack` must match
`model_route_id`, `model_override_applied=NO`, the reserved-schema inheritance
policy, and all office identity hashes before status changes to running. Claude
Code and Hermes likewise acknowledge main-thread/main-profile inheritance.
When actual model application is required, the separate fresh-session leaf
worker may apply a proved top-level route only with an exact native binary,
host-proof SHA256, matching dossier cwd, disabled multi-agent features, and
session `turn_context` evidence. It is not a V1/V2 child or same-session switch.
Full details and the pre-launched superCC boundary are in
[court-office-model-routing.md](court-office-model-routing.md).

Production routing is V2 or `serial`; `auto` binds to the active V2 namespace.
Codex 0.144.1 evidence showed that exact UUID resume retains the original tool
namespace, so the host cannot perform a same-session protocol switch. The old
V1 probe remains only a compatibility fixture and does not authorize production
selection. `court_codex_protocol_launcher.py` is retained for audit/recovery but
the bidirectional-switch path is deprecated and must remain fail closed unless
a newer explicit user decree and fresh capability proof reopen it. Its quiet-
point gate still rejects active/unfinished agents, unmerged messages, followups,
waits or tool calls, unpersisted goal/task state, unknown capacity or depth, and
unconfirmed one-time credentials.

Host thread capacity is authoritative even after the court ledger marks a child
closed. Some V2 hosts retain completed or interrupted collaboration nodes and
may still return `thread limit`; record this as `runtime_degraded`, stop the wave,
and do not reuse an errored/overgrown thread or fabricate a free slot. If the
host refuses the spawn before an agente lifecycle record exists, use
`agent-spawn-failed` to block the wave and defer its remaining roles without
creating a fake agent record. Ledger closure proves court lifecycle
reconciliation, not physical host reclamation.

The newest user instruction may select fully serial execution. In that case the
formal-decree parallel obligation is satisfied only by recording
`parallel_dispatch=NOT_APPLICABLE/user_serial_override`; no child may be spawned,
reused, awakened, or followed up. Before dispatch inspect live collaboration
occupancy; a configured `max_threads` value is not proof of an available slot.
On `thread limit`/capacity, stop expansion for that wave and do not reuse an
errored or long-history agent as a workaround. On fatal quota/auth/account/
billing errors, open the task circuit, do not retry in the same task, interrupt
remaining siblings, and immediately reconcile court ledger fields
`finished_at`, `closed_at`, `final_status`, and `release_status`. Provider URLs,
request ids, balances, credentials, and raw error bodies must not be persisted.
## 协同上朝

`/court` is the default multi-office court session, not 独办朝务. For any
formal decree, 尚书省 must first assess office separation, dependencies, and
useful parallelism, then dispatch only offices whose work materially improves
evidence, speed, risk review, or implementation. The
  intended Codex-native structure is recursive and entity-separated: 三省 are
  distinct level-1 office agente, 六部 are distinct level-2 office agente under
  尚书省, and 工坊/工匠 are worker capabilities under 六部.
Invoking this skill's default court workflow is the user's standing permission
for sub-agents, delegation, and parallel work inside the decree boundary, so do
not ask again merely to enable 多 agente/六部并行. This standing permission is not
an order to waste tokens or spawn useless workers when the task is read-only,
tiny, safely sequential, unsupported by runtime tools, or blocked by host tool
policy. A non-court path is allowed only for 太子收旨, small chat, or trivial
no-tool responses that do not open a formal decree; once a decree opens, the
court must either dispatch useful parallel work or explicitly record
`parallel_dispatch: USED | NOT_APPLICABLE | runtime_degraded |
authority_blocked` with the reason.

Court assembly:

1. **太子定性**：太子收束旨意；开朝后先结合史馆检索线索作简短
   `意图初判`，列明可能意图、依据、置信度、非目标和下一步；若需要开朝，
   拟定初始诏令。
2. **三省会审**：每次非琐碎用户提问均先入三省会审。中书省拟旨、拆解、
   考据和验收标准；门下省封驳假设、风险、缺口和批准条件；尚书省评估
   可分派性、资源、顺序、并行空间和六部差遣。三省必须讨论具体细节后
   向太子请示或回奏，不直接面对用户。
3. **尚书统六部**：门下批准后，尚书省按能力官籍和部门图谱派出吏部、户部、
   礼部、兵部、刑部、工部。严格历史制下六部归尚书省统辖，中书省和门下省
   不直接调六部。
4. **工坊办差**：六部按差遣调工坊/工匠 agente、skills、MCPs、CLIs、scripts。
   工坊工匠是实际办事层，必须有明确授权和证据要求。
5. **门下复核**：门下省复核六部结果、验收证据、风险和史馆状态。
6. **史馆实录**：史馆三省共监、门下主审，记录实录、本纪、表、书/志、列传、
   史官按语、记忆候选、记忆裁定和考课。

Agent group rules:

- Using this skill grants standing permission and standing obligation to attempt
  multiple parallel agents inside the user's stated task boundary for formal
  decrees. Do not ask again merely because the work can be parallelized; ask
  only when the proposed spawned work would cross the approved authority
  boundary, introduce a new behavior class, trigger a hard safety/cost/privacy/
  external-state gate, or meet a host-enforced authorization requirement. The
  three execution authorities still control installs, destructive actions,
  secret/private-data handling, paid actions, config writes, MCP writes, sandbox
  escalation, extra-workspace operations, and external app state.
- Treat the default court workflow as the user's explicit opt-in and direct
  request for `sub-agents`, `delegation`, and `parallel agent work`. Do not ask "是否启用多
  agente/多 agent/并行官署" again. Ask only for missing scope, risk, cost,
  privacy, or destructive-action approval.
- If the runtime does not expose a subagent/spawn-agent tool, does not expose
  recursion to spawned agents, or the host tool policy blocks the specific
  proposed spawned behavior, first judge whether a
  scoped capability/configuration remedy or renewed 太子回奏 is required by that
  boundary and behavior class. For major implementation, migration, or research decrees,
  inspect current Codex agent settings, consult official Codex docs when needed,
  and, if allowed by the approval policy and host tool policy, configure bounded
  recursive delegation with `scripts/ensure_court_agent_config.py` toward the
  normal 4/16 install target; a value above 16 requires a current explicit user
  count or unlock decision. If the settings are below 4/16 but the current task can
  still run with the available bounded depth/threads, report
  `compatible_below_recommended` and proceed inside the smaller budget instead
  of treating the runtime as failed. For read-only review, status correction, single-file
  repair, or tasks where recursion adds no useful evidence, record the
  limitation and proceed through 太子代摄/leaf-agent semantics. Only after that
  decision may the court continue in degraded mode and report:
  `尚书分派：递归朝廷为正式任务所必需；已尝试启用/配置递归但受运行时/权限/策略限制，暂由太子代摄官署流程，尚书省/史馆记录递归受阻原因。`
- Attempt multiple agents for formal decrees even when the subproblems are
  partly sequential; actually spawn 六部 or 工坊 only when there is meaningful
  execution, research, risk, or verification work that can advance in parallel
  or improve evidence. For truly trivial no-tool answers, 太子 may handle intake
  and response alone.
- In normal tool-limited sessions, spawned agents are leaf officials and must not
  spawn children, install tools, expand scope, approve dangerous work, or route
  other ministries.
- In explicit recursive Codex mode (`agents.max_depth >= 2` or equivalent),
  三省 may spawn only their approved child offices and 尚书省 may spawn 六部;
  六部 may request 工坊/工匠 only within budget, risk, and audit constraints.
  No office may create unbounded descendants or permanently install a standing
  official without 太子回奏 and user approval.
- Direct superiors control their direct subordinates inside the approved decree:
  六部 report to 尚书省, 工坊/工匠 report to their named ministry, and each direct
  superior may demand real-time reports, request evidence, narrow scope,
  correct, pause, recall, or reassign the subordinate. The report header must
  name the concrete receiving office, such as `上奏：尚书省` or `上奏：工部`;
  do not write only abstract `父级`/`parent` in user-facing subordinate reports.
- The execution chain and the gatekeeping chain have separate priority. A
  direct superior's correction, pause, recall, or reassignment takes immediate
  effect unless 门下省 has sealed/rejected that matter or 太子/user has marked it
  `待裁`; then execution must stop advancing and only preserve state, collect
  evidence, and wait for裁决.
- Peer offices may consult horizontally: 三省 peers or 六部 peers may exchange
  memorials, evidence, risk notices, corroboration requests, collaboration
  requests, and 史馆日志 pointers. Peer consultation never creates command,
  approval, rejection, pause, recall, or reassignment authority. Peer conflicts
  go to the common superior: 三省 conflicts to 太子, 六部 conflicts to 尚书省; safety,
  secrecy, overreach, destructive actions, paid actions, external-state changes,
  suppressed evidence, or semantic drift also go to 门下省 for封驳.
- Subordinates normally memorialize their direct superior. They may submit an
  emergency sealed memorial upward to 门下省 and 太子 when safety, secrecy,
  authority overreach, destructive action, paid action, external-state change,
  superior silence, suppressed evidence, or clear semantic drift is involved.
  Emergency escalation triggers review and裁决 only; it never authorizes the
  subordinate to bypass its direct superior and execute on its own.
- Agente lifecycle is part of the evidence contract. Formal decrees should
  prefer real agente, but each real agente must have identity, direct superior,
  duty boundary, evidence contract, heartbeat, stop condition, lifecycle state,
  and a 史馆日志/AGLOG pointer. Completion, staleness, loss of contact, overreach,
  duplication, lack of evidence value, or superior recall should close or
  degrade the agente and record the close/degrade reason in 史馆. Starting,
  closing, pausing, resuming, or degrading an agente requires 太子/user 朱批 first
  when that action would expand authority, lose evidence, affect external state,
  add cost, expose private/sensitive information, or change the approved task
  boundary.
- Recursive failure and partial failure must be reported as such. If any layer's
  spawn/wait/close, heartbeat, logging, 史馆 write, evidence contract, or
  authority gate fails, that layer must not be reported as executed. Continue
  usable layers when safe, and mark the unavailable layer as
  `runtime_degraded`, `authority_blocked`, `待裁`, or `退回补证` with the failing
  layer, concrete direct superior, preserved evidence, and actions not run.
  太子回奏 must distinguish real completion, partial completion, 太子代摄,
  runtime degradation, and authority blocking.
- Each office assignment must name: office, role key, scope, allowed
  paths/actions, forbidden actions, evidence required, stop conditions, and the
  official report contract.
- Ministries return reports to 尚书省. Workshops return reports to their named
  ministry. Ministries do not route each other. 门下省 can reject back to 中书省 or
  require 尚书省 to redispatch.
- Serialize shared-file edits, MCP writes, installs, config changes,
  destructive operations, and external application state.

## RC2 Semantic Continuity And Operation Authority

`tasks.json` current-task records and append-only `court_events.jsonl` remain
the only runtime authority. Runtime-schema v2/v3 records that lack a body-bound
semantic binding may be listed and diagnosed, but every mutation fails closed
with `legacy_semantic_binding_read_only`; normalization never upgrades their
stored bytes.

A writable task binds `charter_revision == semantic_epoch`, the exact charter
SHA-256, and an invariant capsule of at most 2 KiB. The capsule carries the
latest decree anchor, non-goals, boundaries, allowed/forbidden actions,
acceptance/evidence/stop gates, write set, and governing hashes. Checkpoint and
verification receipts keep authority, plan, Git/worktree, recovery, and
Shiguan evidence in separate fields. The supported JSON interface is:

```text
court semantic checkpoint|verify|correct|resume|quarantine|reconcile
```

Checkpoint/verify are required after restoration and before dispatch. Drift is
persisted as `QUARANTINED`; correction and resume return through
`ThreeDepartments` and `REVERIFY`. Reconcile may acknowledge restored sources
only to `REVERIFY`; it cannot directly restore `DISPATCHABLE`.

Admission and lifecycle receipts bind task id, semantic epoch, charter/capsule
hashes, checkpoint id, dispatch uid, attempt, office instance, direct superior,
worktree/write set/lease, and preload hashes. A current bound child result uses
`court.office.result.v1`; free text cannot bypass that envelope, and stale
results are quarantined rather than rebased.

`court_operation_journal.py` is a disposable idempotency/recovery artifact, not
a task ledger, event ledger, or sequence authority. `court decree-open` writes
the allocated main number and receipt into the current task under the runtime
lock; same-operation replay returns the original receipt, while a changed
payload fails closed. Allocation recovery is forward-only, so gaps are allowed
but an allocated number is never silently reused.

Phase-1 closeout validation uses only `court synthetic-closeout` and a
`synthetic-*` root beneath the temporary runtime root. It proves
`PREPARED -> ARCHIVE_COMMITTED -> TASK_EVENT_COMMITTED` and
`court closeout-recover --operation-id`; it is not a real Shiguan production
adapter and never authorizes access to pending import bodies.

## Hierarchical Budget Pool Gate

`hierarchical_budget_pool_gate` requires every parallel allocation to carry a
stable `budget_id`. A child allocation carries its `parent_budget_id`; its
`direct_superior` grants a bounded `lease`, retains a safety `reserve`, and may
reclaim only unused capacity. Capacity never grants authority, changes the
office hierarchy, or permits a wave merely to fill available slots.
