# Court Startup And Authority / 开朝与三权

渐进加载注记：本卷由原 `SKILL.md` 顶级章节机械迁移而来，保留原文语义用于按需加载。新的短 `SKILL.md` 是入口、硬门禁与直接索引；本卷是该入口直接链接的 governing reference。若旧文出现“必须写入 SKILL.md”等位置性表述，在本次渐进加载结构下解释为：硬门禁、触发、三权、只读、安全、状态机、史馆/记忆、语义再载入、奏报模板等规则必须在短 `SKILL.md` 保持摘要和直链；细节规则可写入本卷等直接链接 governing reference。史馆仍只作证据与召回锚点，不替代本 skill 源文件与 governing references。

原始来源：`SKILL.md` sha256 `64c7a9089275de004bbd2fc4e9c59633d2bbfe9e2a355178816c3da65f6563c9`。本卷章节：`Quick Start`, `Approval Policy Details`, `开朝 Selection`。

## Contents

- [Quick Start](#quick-start)
- [Approval Policy Details](#approval-policy-details)
- [开朝 Selection](#开朝-selection)

Startup/runtime term anchors: `taizi_no_silence`,
`three_departments_no_silence`, `rate_limit_wake_hierarchy`,
   `taizi_stale_explanation`, `closeout_silence_policy`, `idle_receive`,
   `noncurrent_inactive_pane_cleanup`, `direct_superior_source`,
   `post_dispatch_physical_enter_delay_seconds`, `six_ministry_step_plan_policy`,
   `decree_usage_estimate`, `decree_usage_actual`, `usage_actual_source`,
   and `no_silence_roles` are governed by
`court-state-runtime-agents.md`, `court-offices-dispatch.md`,
`court-closeout-validation.md`, and `ensure_supercc_court.py`. This parent
keeps these anchors for startup-time lookup; detailed bodies remain sharded.

## Moved Source

## Quick Start

1. Parse three independent structured fields before runtime selection:
   `execution_authority`, `parallel_topology`, and `carrier_kind`. Authority text
   may set the first field; `super并行` sets only
   `parallel_topology=ordinary_parallel`; only an explicit runtime selector
   receipt may set `carrier_kind=supercc_cli_office`. Never infer one field from
   another because their work states or names appear similar.
2. Determine the approval policy:
   - If they specified `approval`, `autonomous`, or `super`, honor it inside the
     unchanged current decree/boundary. If they specified `superCC`, honor it only
     for the current formal decree that explicitly named `superCC`; do not reuse
     `superCC` for later decrees unless the newest user message names it again.
   - If no approval policy is known, ask the single 开朝 approval question.
     This is a hard intake gate for the first court turn in a conversation: a
     request that names a skill, pastes a `SKILL.md`, asks whether a tool can be
     installed, or appears to be a simple capability query still does not count
     as approval-mode selection unless it explicitly says `approval`,
    `autonomous`, `super`, or `superCC` in the newest user message. Do not inherit a mode
     from older conversations, 史馆 records, current sandbox posture, a pasted
     prompt that merely describes the three modes, or an installation/config
     intention. Do not execute shell commands, write files, browse the web,
     install tools, or mutate the capability registry before this gate, except
     for the minimum read-only skill-file loading required by the skill system
     itself.
   - Treat any user-supplied `/auto`, `/plan`, `/goal`, `/memories`, `/execute`,
     `/research`, `/debug`, or `/catalog` token as an intent hint inside
     `/court`, not as a separate workflow.
2. Run 开朝 capability classification:
   - 户部/史馆 ensures the shared Shiguan root exists with
     `scripts/shiguan_paths.py` / `ensure_shared_seed()`. The default root is
     `%USERPROFILE%\.agents\court-shiguan\decretum-matrix\references`; all
     Codex/Hermes/Agent Skills installs must read and write Shiguan records
     through that shared root unless `COURT_SHARED_SHIGUAN_ROOT` or
     `SHIGUAN_SHARED_ROOT` explicitly overrides it.
   - 史馆 checks the shared Shiguan service daemon at startup when filesystem
     tools are available. Under `approval`, use
     `python -B scripts/ensure_shiguan_service_daemon.py --check-only` unless the
     newest decree explicitly permits startup/service writes. Under
     `autonomous` and `super`, ensure the daemon only when that local service
     state is in scope. The hidden
     user-logon task `CourtShiguanDaemon` starts `shiguan_service_daemon.py`,
     which keeps the single 8765 Shiguan WebUI and independent Obsidian
     preserve-only autosync daemon alive. Each sync cycle must report
     `preserve_only=true` and `removed=0`; it must not process pending imports
     into official records.
   - 开朝 records the intake token/time estimate for the decree before planning
     or dispatch. This is a fixed intake/runtime gate, not a new office,
     subagent, or dispatch target. Use `python -B scripts/court_usage_ledger.py estimate --task-id
     <court-task-or-snapshot-id> --decree "<latest decree>" --mode
     <approval|autonomous|super|super_parallel|superCC>` when filesystem writeback
     is available; otherwise report the same fields manually as
     `decree_usage_estimate=runtime_degraded`. The estimate must name assumptions,
     expected offices/subagents, expected tool calls, and source=`heuristic`.
   - 户部/史馆 reports the Shiguan web manager URL from the service daemon or
     `ensure_shiguan_web.py`. Under `approval`, perform status/path probes only
     and reuse an already-running service without starting one unless the newest
     decree explicitly permits the state change. Under `autonomous` and `super`,
     start or reuse the read/state local/LAN service only when it is in scope,
     then report the actual local URL plus any returned `lan_urls`. Management
     writes, imports, token handling, non-loopback admin actions, and public
     exposure remain gated.
   - 史馆/户部 checks pending direct imports with
     `python -B scripts/check_shiguan_import_queue.py --format json` before raw
     imported text is read. Report whether there are new `.md`/`.txt` or
     Obsidian-derived materials, the pending count, new count, metadata-sidecar
     token estimate, queue path, and representative filenames. If no valid
     metadata sidecar exists, report the estimate as `unknown`; never open
     `text`/`raw_text` body content merely to estimate tokens. If pending material exists,
     太子 must ask or route whether to process it; ordinary 开朝 recall must
     not silently load or summarize the raw text. After this queue state is
     reported, mark current pending IDs as seen only when the active authority
     permits writing the shared Shiguan queue ledger; otherwise report that the
     seen ledger was not written.
   - 户部/刑部 checks `python -B scripts/ensure_codex_yolo_startup_task.py`. In
     `approval`, use `--check-only`. In `autonomous` and `super`, generate
     review artifacts when the Windows startup task is missing. Registration of
     `codex --dangerously-bypass-approvals-and-sandbox` as an AtLogOn task is a
     persistent dangerous external-state change; no-sandbox autostart requires
     explicit confirmation and must not be performed merely because the skill
     was installed, enabled, or invoked with `super`.
   - 史馆 loads only relevant prior records when they can affect the decree.
     When searching prior records, query `references/shiguan-index.jsonl` through
     `scripts/query_shiguan_index.py` before falling back to manual archive reads.
     Use `scripts/rebuild_shiguan_index.py` when the prior archives may not have
     been fully converted into the growth-tree model.
   - After prior-record recall, 太子 writes a compact `意图初判` with
     likely_intent, memory_clues, confidence, likely_non_goals, and next_step.
     This is a routing aid, not a final decision; 三省 may correct it in
     三省会审. If clues are weak or conflicting, report `历史线索不足`.
   - 户部 performs the light capability-registry refresh described below. This
     is a mandatory pre-routing gate after approval mode is known, not an
     optional optimization. If the refresh cannot run, 太子 must report
     `capability_registry_refresh: FAILED | authority_blocked |
     runtime_degraded`, explain the reason, and route with an explicit stale
     catalog caveat rather than silently using unknown capability state.
   - 户部 confirms `find-skills` and system `skill-creator`; if missing, 吏部
     opens recruitment/remediation instead of silently degrading.
   - 吏部 reads the catalog's `Court Department Capability Map` and capability
     registry dimensions. If that section is missing, use
     `references/department-map.md`.
   - Keep the map and personnel/capability dimensions available for the current
     task.
3. Locate the capability catalog:
   - Prefer this skill's own `references/installed-capabilities-catalog.md`.
   - If this skill is not installed under the active skills root, use
     `<CODEX_HOME>\skills\decretum-matrix\references\installed-capabilities-catalog.md`.
   - If `CODEX_HOME` is unset, use `%USERPROFILE%\.codex`.
   - If the catalog is missing, use `references/department-map.md` as the
     fallback department map and run a light local scan only when needed.
4. Convene the court:
   `太子定性 -> 三省会审 -> 三省上奏 -> 太子回奏 -> 尚书统六部 -> 工坊办差 -> 门下复核 -> 史馆实录`.
   At `太子定性`, instantiate the semantic charter from the Core Semantic
   Contract and carry it through 三省会审, dispatch, review, and the final
   memorial. If the charter changes because the user corrects the decree, return
   the corrected charter to 三省 before execution continues.
5. Use the department map and the官籍/铨选 registry to select candidate skills,
   MCPs, agents, CLIs, scripts, or worker agents. A capability can be multi-fit;
   assign it by explicit 差遣 for this decree rather than by a permanent single
   department label.
6. Before risky actions, stop according to the active approval policy. Treat the
   three modes as court execution authorities:
   - `approval` is read-only authority.
   - `autonomous` is management authority inside the user's stated scope.
   - `super` is full-control authority inside the user's stated scope.
   - `super并行` / `super parallel` is `super` authority plus
     `parallel_topology=ordinary_parallel`; its dispatch receipt uses only
     `carrier_kind=child_agent|worktree_thread` and does not invoke another
     runtime selector.
   - `superCC` is `super` plus a selected court runtime; it is not a higher
     safety authority. Normal `superCC` must pass the zellij+squad environment
     gate before the court claims real 官署 mode. Codex/Hermes/Claude/generic CLI
     client or readiness evidence is supplemental to that environment gate, not
     a bypass.
   Under `autonomous` and `super`, sandbox escalation and operations outside the
   current workspace are allowed when they are task-scoped, path-scoped, and
   consistent with the chosen authority. If the tool runtime still requires an
   approval dialog, submit the escalation request immediately and treat that
   dialog as a runtime gate, not a court decision. Decide renewed authorization
   by the approved boundary and behavior class. Do not stop merely because the
   in-scope work is parallel or multi-agente; still stop for path/service/risk/
   cost/privacy/external-state boundary changes, irreversible destructive
   actions, secrets/credentials, private-data upload, paid actions, unverified
   installs, unbounded agent trees, surprising external state changes, or a
   host-enforced authorization gate.
7. At the end of every decree, before the final memorial, run an agente cleanup
   pass again. Close useless spawned agents/threads where the runtime exposes a
   close operation, summarize what was closed or why cleanup was blocked, and
   leave only still-useful long-running or user-approved standing officials.
## Approval Policy Details

Detailed approval policy now lives in
[sections/court-startup-approval-policy-details.md](sections/court-startup-approval-policy-details.md).
This parent section remains the stable startup authority anchor.

Load the shard for approval/autonomous/super/superCC boundaries, index-first
capability invocation, MCP writes, multi-agente dispatch, dangerous autostart
review, and packaging governance.
## 开朝 Selection

`/court` is the only task workflow. Do not ask the user to choose `/plan`,
`/execute`, `/research`, `/debug`, `/catalog`, `/memories`, archive loading, or
other task modes. Those are internal court functions handled by 三省六部 and
史馆 after 太子 receives the decree.

On the first call in a new conversation, ask only for execution approval mode
unless the user already supplied it. Use the full Chinese prompt below:
`already supplied` means the newest user message explicitly selects
`approval`, `autonomous`, `super`, or `superCC`; quoting this skill's prompt, pasting a
`SKILL.md`, asking whether something can be installed, or including prose that
describes the modes is not enough.

```text
请选择执行权限（三权）：
- `approval`（只读权）：默认只做只读勘验、检索、读档、审议；命令执行、写入、联网、安装、配置、MCP 写操作、越工作区操作前先询问。
- `autonomous`（管理权）：在陛下/用户给定的范围内自主执行；工作区写入、已授权路径、sandbox 提权、超工作区操作都可按任务边界办理，遇到破坏性、泄密、付费、未验证安装、私密上传或明显越旨再问。
- `super`（完全控制权）：任务范围内自动执行，包括命令、写入、联网、配置、sandbox 提权、超工作区操作和多 agente 调度；`super` 默认请求 `yolo`/无沙盒执行，任务开始前必须说明当前 Codex 进程是否已真正以无沙盒启动；若当前进程不能热切换，则明示只能通过运行时提权门禁代行，并建议下次用 `codex --dangerously-bypass-approvals-and-sandbox` 或 `codex --sandbox danger-full-access --ask-for-approval never` 启动；是否停问由已批准边界和行为类别决定，不因多 agente 形式本身停问，只在越出路径/服务/风险/成本/隐私/外部状态边界、触及不可逆破坏、泄密、花钱、未验证安装、上传私有数据、无界代理树、明显越旨外部状态变更或宿主硬门禁时上奏。
- `superCC`（官署权）：`super` + 运行时分流后的真实官署编排；必须由最新旨意逐次明示，不从 `super`、旧会话、默认配置或史馆记录继承。Normal `superCC` 只有 zellij+squad 官署环境：启用前确认当前在 zellij 内、有 `squad`、有所选 office client/readiness 证据、递归 agente 有界，显性核心固定为太子 agente 与三省，六部按尚书省分步计划真实派遣；监察使不再是默认启动项，只能作为显式 bounded diagnostic。Hermes CLI/desktop 与 Claude Code 可提供 client/readiness/sync 证据，但不能跳过 zellij+squad；Hermes profile 静默调用必须在对应 profile 对话/会话中留证且只算 readiness/dispatch evidence。普通并行、六部并行、recursive subagente 或多 agent 工作可是真官署办差，但不是 `superCC` runtime；它们共享同一官署本体，差别在 spawned-subagent vs visible/readiness 的实现与证据门。健康官署必须各司其职，太子主窗只转奏/综合/派发，不代三省、尚书、六部或史馆办差；尚书省必须派发六部、收齐并整理六部回奏，再统一上奏太子。活跃官署数量不再固定限为 5 个，遇 429/rate-limit 先按 `<=20/minute` 请求门禁 requeue、stagger/backoff、按上下级唤醒/重派受影响官署并记录证据，不让太子代工。设计类任务给对应六部完整但限域/脱敏的上下文包；其他任务结诏后自然释放六部；最终结诏后执行对应 runtime closeout/silence。`superCC` 不放宽破坏、泄密、付费、公网暴露、未验证安装、私密上传、危险自启或无界代理树门禁。
默认建议：`autonomous`。任务工作流固定为 `/court`；史馆会按需查旧实录，不再单独询问归档加载。
史馆生长树本地管理页：`web/shiguan-tree/index.html`。开朝后先用 `python -B scripts/ensure_shiguan_service_daemon.py --check-only` 探测；只有 `autonomous`/`super` 范围内或最新旨意明确批准服务写入时，才用不带 `--check-only` 的命令安装/复用隐藏登录守护进程。它后台确保局域网可访问的 8765 单端口服务与 preserve-only autosync；同机可打开 `http://127.0.0.1:8765/`，局域网设备使用脚本回报的 `lan_urls`。若守护进程确保失败，可在相同权限边界内手动运行 `python -B scripts/ensure_shiguan_web.py` 或 `python -B scripts/serve_shiguan_tree.py --host 0.0.0.0 --port 8765`；不得做外网穿透或云暴露，除非陛下另有明示旨意。
```

Do not persist the selected approval mode by default. Reuse `approval`,
`autonomous`, or `super` within the current conversation when the task boundary
has not changed. `superCC` is stricter: each new formal decree must explicitly
name `superCC`, because it changes the runtime shape and may create standing
runtime offices or supplemental Hermes/Claude readiness evidence. If the task changes, recommend an approval-policy change only when
the current policy cannot safely cover the new scope.

After approval mode is known, immediately run the 开朝 capability check before
answering, planning, installing, editing, or dispatching a formal decree. In
user-facing court speech, this skill's startup/activation is called `开朝`; use
`startup` only when naming code, scripts, fields, logs, or external APIs.
If the current turn skipped the approval-mode question or skipped 开朝 because
the user supplied a long skill body, a direct install command, or an apparently
simple capability query, treat that as semantic drift: stop new execution,
report the drift, obtain or infer only an explicit mode from the newest user
wording, then run a catch-up 开朝 checkpoint and record it in 史馆 before
  continuing. On a blank portable install, run
`ensure_portable_court_bootstrap.py --check-only` for audit. Run
`ensure_portable_court_bootstrap.py --apply` only when the decree separately
asks to replicate or repair the complete feature set; this establishes
the shared Shiguan, Obsidian registration, Codex/Hermes native memory flags,
metadata-only bridge checkpoint, Shiguan service daemon, and superCC dependency
substrate. Under `super`, run independent 开朝 checks in parallel when tooling
allows it, but serialize shared writes and report any host-enforced approval
dialog as a runtime gate. Under `superCC`, run the runtime selection gate after
the normal 开朝 checks and before claiming standing 官署 operation: Codex uses
`ensure_supercc_court.py`; Hermes uses `ensure_hermes_supercc.py`.

0. 太子/户部 checks the currently open agente/subagent threads. Release or close
   useless, completed, stale, duplicate, or orphaned agente before opening new
   work. Do not close an agente that is still producing evidence, waiting for a
   required user answer, guarding a long-running command, or holding an
   unresolved safety/verification task. Record any runtime inability to inspect
   or close threads as `agente清理受限`.
1. 户部/史馆 ensures the shared Shiguan root exists and, when permitted, ensures
   the shared Shiguan service daemon:
   `python -B scripts/ensure_shiguan_service_daemon.py --check-only` for
   read-only audit, or `python -B scripts/ensure_shiguan_service_daemon.py` only
   when startup/service writes are authorized. This hidden user-logon
   watchdog starts or reuses both the 8765 WebUI and the preserve-only Obsidian
   autosync daemon. One-shot sync remains
   `python -B scripts/sync_shiguan_obsidian_vault.py`; it writes only the
   configured Obsidian cache, never deletes user notes, and never converts
   Obsidian edits directly into official Shiguan records. Edits and imports must
   enter shared `shiguan-imports\pending`.
2. 户部/史馆 checks whether the local/LAN Shiguan web manager is available. Under
   `approval`, perform only status/path probes unless the newest decree permits
   service startup. Under `autonomous` and `super`, start or reuse the read/state
   Shiguan web service in the background when it is in scope and not already
   available through the service daemon, with `python -B scripts/ensure_shiguan_web.py`
   as the direct fallback.
   If port 8765 is already serving this skill, reuse it. If port 8765 is held
   by an unknown process, do not kill it and do not drift to other ports; report
   `史馆图谱服务：FAILED` with the unknown owner and manual remediation. If
   service startup fails, record
   `史馆图谱服务：FAILED`, the reason, the static entry path, and the manual command,
   but do not block `/court` routing, 三省会审, or user-question handling.
   Default binding is `0.0.0.0` so devices on the same LAN can open the returned
   `lan_urls`; keep it LAN-only, do not configure public tunneling, router port
   forwarding, or public remote exposure without a separate explicit decree.
   The Shiguan web manager has two security classes: read/state endpoints may be
   LAN-visible, while management endpoints such as entry writes, rebuild/grow,
   import/export, key management, and Obsidian sync must require a local admin
   token when accessed from non-loopback clients. The token is supplied through
   `SHIGUAN_ADMIN_TOKEN` and sent by the browser as `X-Shiguan-Admin-Token`;
   never expose the token in `/api/state`, graph labels, logs, 史馆 records, or
   final memorials. JSON request bodies must have a hard size cap, and large
   imports must stay in the pending queue until 三省会审 and 门下复核.
3. 史馆/户部 checks the direct-import pending queue with
   `python -B scripts/check_shiguan_import_queue.py --format json` before
   loading imported raw text. This check is mandatory on every 开朝
   because direct Obsidian, `.md`, and `.txt` imports are pending Codex materials
   rather than official 史馆 entries. Report
   `shiguan_import_queue: NONE | PENDING | FAILED`, the pending count,
   metadata-sidecar token estimate or `unknown`, new count, new-token estimate,
   queue path, and representative filenames. The check must not open or parse
   embedded `text`/`raw_text` body fields. After 太子 reports the queue state to the user, and only when the
   current authority permits writing the shared Shiguan queue ledger, run
   `python -B scripts/check_shiguan_import_queue.py --format json --mark-seen`
   or otherwise update the seen ledger so the same pending files are still
   reported as pending but no longer misreported as newly imported on later
   开朝 rounds. Under `approval`, do not write the seen ledger unless the user
   has allowed that write; instead report `seen_mark: not_written`. If pending
   materials exist, 太子 must state the approximate token cost and ask or route
   whether to process them before consuming the raw text. Processing means
   reading the pending material into Codex, summarizing/classifying it,
   proposing official 史馆 entries or memory candidates, and then submitting the
   result through 三省会审、门下复核, and 史馆实录. Do not silently process pending
   imports as part of ordinary 开朝 recall.
4. 户部/刑部 checks the dangerous Codex no-sandbox startup-task state with
   `python -B scripts/ensure_codex_yolo_startup_task.py`. Under `approval`, run
   `--check-only` and report whether the Windows task exists. Under
   `autonomous` and `super`, if the task is missing, automatically generate the
   local review artifacts under `references/startup-tasks/` but do not register
   the Windows task. no-sandbox autostart requires explicit confirmation even
   under `super`: actual registration requires a renewed 太子回奏 naming the task
   name, trigger, command, working directory, log path, revoke command, and risk,
   plus the explicit dangerous confirmation flags
   `--register --i-understand-dangerous-yolo-startup`. Report the result as
   `codex_yolo_startup_task: TASK_EXISTS | MISSING | GENERATED_REVIEW_TASK |
   REGISTRATION_REFUSED | REGISTERED | FAILED`.
5. 史馆 checks and loads only relevant prior 实录/本纪/表 entries when useful.
   Prefer `scripts/query_shiguan_index.py <keywords>` for keyword/key-behavior
   recall before manually opening older archives.
   Each Shiguan entry should carry bilingual concise recall fields:
   `keyword_summary_zh`, `keyword_summary_en`, `keywords_zh`, and
   `keywords_en`, so both the user and agente can understand and retrieve it.
   If archival completeness matters, run `scripts/rebuild_shiguan_index.py` to
   convert all existing `plan-archives/` and `memory-decisions/` into the
   current recall index and growth tree.
   After major classification-rule changes, run
   `scripts/reevaluate_memory_decisions.py` to produce Menxia-review candidates.
   This reevaluation does not overwrite historical `memory_decision` fields.
   After this recall pass, 太子 must perform a short `历史线索初判` before
   routing: infer what the user is likely trying to do from the latest decree
   plus relevant prior memory clues, state the clue source in one concise
   phrase, give a low/medium/high confidence label, and name the tentative
   decree type. If no reliable memory clue is found, say so plainly and default
   to the newest user request instead of inventing intent. This first judgment
   is provisional and must not skip 三省会审, user clarification, or safety gates.
6. 户部 runs a light capability-registry refresh. If skill, agent, MCP, CLI,
   or script roots changed, run `scripts/refresh_capability_registry.py` before
   routing so newly installed skills are classified into the court's 官籍 and
   can be invoked by 三省六部. This root-change refresh is a standing 开朝 duty and
   does not need a separate user authorization merely because the local
   capability roots changed. Its authority is narrow: read local skill/agent
   roots, `SKILL.md` frontmatter, agent `.toml` summaries, this skill's
   `agents/standing-officials`, known MCP/CLI/script presence, and the existing
   capability map; then rewrite only this skill's local 官籍/catalog artifacts as
   needed. It must not run every skill, install or update capabilities, browse
   the web, start task-new public services, process import queues, read or
   reveal secrets/private session content, write outside this skill's local
   references, perform destructive/paid/external-state actions, or treat a
   skill inventory result as an office agente dispatch. Any action beyond this
   local catalog refresh goes to 门下省封驳 and 太子/user 朱批.
   The result must be surfaced in the 开朝 summary as
   `capability_registry_refresh: REFRESHED | CURRENT | FAILED |
   authority_blocked | runtime_degraded`, including the manifest/catalog path
   or the reason it could not be trusted. A formal decree may proceed after a
   failed refresh only with 门下省's explicit stale-catalog caveat and a scoped
   fallback map; it must not pretend that 官籍 was current.
7. 户部 verifies the minimum portable environment: `find-skills` under
   `%CODEX_HOME%\skills\find-skills` and system `skill-creator` under
   `%CODEX_HOME%\skills\.system\skill-creator`. If `CODEX_HOME` is unset, use
   `%USERPROFILE%\.codex`.
   If either is missing, 吏部 must actively recruit/repair it through the active
   execution authority before treating the court as fully capable. If
   `find-skills` is missing, report its public page
   `https://www.skills.sh/vercel-labs/skills/find-skills` and the install
   command `npx skills add https://github.com/vercel-labs/skills --skill
   find-skills`.
8. 吏部 reads or rebuilds the `Court Department Capability Map` and the官籍/铨选
   capability dimensions.
9. Summarize only the relevant routing state: active approval mode, fixed
    `/court` workflow, capability-registry freshness, map source, and any
    stale/missing capability warnings, the Shiguan web service status and URL,
    LAN URLs, the decree token/time estimate, plus the `历史线索初判` when it affects the task. When useful, include the
   local Shiguan web entry path `web/shiguan-tree/index.html`, the editable
   server command, whether the graph view is available, and the
   `codex_yolo_startup_task` state. Always include the import queue state when
   it is pending or failed; when it is empty, a compact `待处理导入：无` is enough.
10. Continue through the court hierarchy.
