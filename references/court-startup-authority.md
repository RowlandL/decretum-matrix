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

1. Parse three independent structured fields before startup:
   `authority=approval|autonomous|super`, `behavior=serial|parallel`, and
   `runtime=native|superCC`. `super并行` sets only `authority=super,
   behavior=parallel`; it never selects runtime. Native and superCC are mutually
   exclusive entry paths and share only the neutral standing-office
   configuration pointer/hash.
   User-facing 开朝 text must preserve the authority-selection question when the
   latest user message has not explicitly selected a current authority:
   `请选择执行权限（三权）：approval（审批/默认只读） | autonomous（自主/范围内实施）
   | super（超级执行/范围内连续推进）`. Behavior remains a separate field and
   must be rendered as `serial（串行） | parallel（并行）`.
2. Determine the approval policy:
   - If they specified `approval`, `autonomous`, or `super`, honor it inside the
     unchanged current decree/boundary. An explicit `superCC` selects the separate
     runtime entry and carries the separately selected three-authority value; it is not a fourth approval mode
     and is never inherited by a later decree.
   - If no approval policy is known, ask the single 开朝 approval question.
     This is a hard intake gate for the first court turn in a conversation: a
     request that names a skill, pastes a `SKILL.md`, asks whether a tool can be
     installed, or appears to be a simple capability query still does not count
     as approval-mode selection unless it explicitly says `approval`,
     `autonomous`, or `super` in the newest user message. Do not inherit a mode
     from older conversations, 史馆 records, memory records, current sandbox
     posture, a pasted prompt that merely describes the three modes, or an
     installation/config intention. Do not execute shell commands, write files,
     browse the web, install tools, or mutate the capability registry before
     this gate, except for the minimum read-only skill-file loading required by
     the skill system itself.
   - Treat any user-supplied `/auto`, `/plan`, `/goal`, `/memories`, `/execute`,
     `/research`, `/debug`, or `/catalog` token as an intent hint inside
     `/court`, not as a separate workflow.
3. Load only the current behavior path:
   - 普通开朝 reads this skill and the one governing reference selected by the
     Progressive Loading Map. It does not run Git probes, service checks, usage
     ledgers, pending-queue scans, YOLO checks, registry refreshes, or portable
     bootstrap merely because a conversation opened.
   - Read the current office profile/dossier only when that office is actually
     assigned. Query the capability registry only when the task needs a
     skill/MCP/CLI/script choice. Query Shiguan/GBrain only when prior evidence or
     memory can affect the decree.
   - Invoke admission, hierarchy, capacity, write-set, service, install, release,
     or migration scripts at their real I/O boundary. A script receipt proves the
     machine fact it checked; it does not replace semantic planning or host spawn
     evidence.
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
   - Behavior is independently `serial` or `parallel`; all six authority /
     behavior pairs are legal. `super并行` / `super parallel` means only
     `authority=super, behavior=parallel, runtime=native`.
   - `superCC` is a separate startup/runtime entry, not a higher or fourth
     safety authority. It carries the exact selected authority and must pass the zellij+squad
     environment gate. It cannot coexist with or fall back to the native runtime
     in one task/process.
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

Load the shard for the exact approval/autonomous/super authority boundary,
orthogonal behavior, the separate superCC runtime, index-first
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
`approval`, `autonomous`, or `super`; quoting this skill's prompt, pasting a
`SKILL.md`, asking whether something can be installed, or including prose that
describes the modes is not enough. A memory or 史馆 clue can remind the court to
ask; it cannot answer the question for the user.

```text
请选择执行权限（三权）：
- `approval（审批/默认只读）`：默认只做只读勘验、检索、读档、审议；命令执行、写入、联网、安装、配置、MCP 写操作、越工作区操作前先询问。
- `autonomous（自主/范围内实施）`：在陛下/用户给定的范围内自主执行；工作区写入、已授权路径、sandbox 提权、超工作区操作都可按任务边界办理，遇到破坏性、泄密、付费、未验证安装、私密上传或明显越旨再问。
- `super（超级执行/范围内连续推进）`：任务范围内自动执行，包括命令、写入、联网、配置、sandbox 提权、超工作区操作和多 agente 调度；`super` 默认请求 `yolo`/无沙盒执行，任务开始前必须说明当前 Codex 进程是否已真正以无沙盒启动；若当前进程不能热切换，则明示只能通过运行时提权门禁代行，并建议下次用 `codex --dangerously-bypass-approvals-and-sandbox` 或 `codex --sandbox danger-full-access --ask-for-approval never` 启动；是否停问由已批准边界和行为类别决定，不因多 agente 形式本身停问，只在越出路径/服务/风险/成本/隐私/外部状态边界、触及不可逆破坏、泄密、花钱、未验证安装、上传私有数据、无界代理树、明显越旨外部状态变更或宿主硬门禁时上奏。
行为另选 `serial（串行） | parallel（并行）`，与三权正交；`super并行` 仅表示 `authority=super, behavior=parallel, runtime=native`。
`superCC` 不是第四权。它必须由最新旨意明确并从独立 zellij+squad startup/runtime 入口启动，携带另行选择的三权 authority 与 behavior；与 native 只共享中性官署配置 pointer/hash，不共享 task state、dossier、transport、admission 或 lifecycle，也不在同一 task/process 内切换或回退。
默认建议：`autonomous`。任务工作流固定为 `/court`；史馆会按需查旧实录，不再单独询问归档加载。
史馆生长树本地管理页为 `web/shiguan-tree/index.html`；只有任务涉及史馆管理、同步或服务状态时，才按 `court-shiguan-memory.md` 探测或启动对应服务。普通开朝不探测端口、守护进程或 Obsidian。
```

Do not persist the selected approval mode by default. Reuse `approval`,
`autonomous`, or `super` only within the current conversation when the task
boundary has not changed and the receipt records
`authority_source=same_conversation_same_boundary`; otherwise ask the 开朝
question again. Runtime selection is fixed at task/process startup and is never
inherited or switched in place; each superCC task must explicitly enter the
superCC runtime. If the task changes, recommend an approval-policy change only
when the current policy cannot safely cover the new scope.

After authority is known, continue from the Progressive Loading Map. Ordinary
开朝 performs no blanket capability, Git, Shiguan service, pending queue, YOLO,
portable-bootstrap, install, release, or superCC check. The numbered items below
are a conditional trigger map, not a startup checklist; run only the item whose
named behavior is present in the newest decree. In user-facing court speech,
call skill activation `开朝`; reserve `startup` for code, fields, logs, or APIs.

0. Before a real parallel dispatch, 太子/户部 checks the currently open agente/subagent threads. Release or close
   useless, completed, stale, duplicate, or orphaned agente before opening new
   work. Do not close an agente that is still producing evidence, waiting for a
   required user answer, guarding a long-running command, or holding an
   unresolved safety/verification task. Record any runtime inability to inspect
   or close threads as `agente清理受限`.
1. When the decree uses Shiguan storage or service integration, 户部/史馆 ensures the shared Shiguan root exists and, when permitted, ensures
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
2. When the decree requests the Shiguan web manager, 户部/史馆 checks whether the local/LAN service is available. Under
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
3. When the decree asks to inspect/process imports or pending material is relevant, 史馆/户部 checks the direct-import pending queue with
   `python -B scripts/check_shiguan_import_queue.py --format json` before
   loading imported raw text. This check is not part of ordinary 开朝;
   direct Obsidian, `.md`, and `.txt` imports are pending Codex materials
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
4. Only for an explicit Codex startup/no-sandbox task, 户部/刑部 checks the dangerous startup-task state with
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
6. When the decree needs capability selection and skill, agent, MCP, CLI,
   or script roots may have changed, 户部 runs a light capability-registry refresh
   with `scripts/refresh_capability_registry.py`. This is a bounded capability
   lookup, not a standing 开朝 duty. Its narrow authority is to read local skill/agent
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
7. Only during capability recruitment, install, or portability repair, 户部 verifies the minimum portable environment: `find-skills` under
   `%CODEX_HOME%\skills\find-skills` and system `skill-creator` under
   `%CODEX_HOME%\skills\.system\skill-creator`. If `CODEX_HOME` is unset, use
   `%USERPROFILE%\.codex`.
   If either is missing, 吏部 must actively recruit/repair it through the active
   execution authority before treating the court as fully capable. If
   `find-skills` is missing, report its public page
   `https://www.skills.sh/vercel-labs/skills/find-skills` and the install
   command `npx skills add https://github.com/vercel-labs/skills --skill
   find-skills`.
8. When capability routing is active, 吏部 reads or rebuilds the `Court Department Capability Map` and the官籍/铨选
   capability dimensions.
9. Summarize only routing state actually used by the decree. Capability freshness,
   Shiguan URLs, usage estimates, history clues, YOLO state, and import-queue
   state appear only when their corresponding conditional step ran.
10. Continue through the court hierarchy.
