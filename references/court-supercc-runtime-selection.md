# superCC Runtime Selection / zellij+squad 官署门禁

## Unified Dynamic Dispatch Semantics

1. 官署按任务职责、依赖和证据价值动态分配。
2. 实时容量与请求预算是运行门禁，不是模式固定人数；整棵 agent tree 受 max_threads=16（含根线程）和 max_depth=4 约束，未知容量、占用或深度时 fail closed。
3. superCC 固定显性太子+三省，但这不限制尚书省非显性、真实派遣有用六部。
4. 普通 super并行不使用 superCC pane、office show delay、wake 或 closeout-silence；其普通 spawn 展示延时为 0。

本卷是 `superCC` 在 Codex、Hermes CLI/desktop readiness、Claude Code client/sync、generic CLI adapter 与可见 zellij+`squad` 官署环境之间分流的 governing reference。入口 `SKILL.md` 保持硬门禁摘要；本卷保存运行时选择、CLI adapter、Hermes profile/session 证据、Claude 同步、打包同步和验收字段。

## Contents

- [Runtime Families](#runtime-families)
- [Normal Environment Gate](#normal-environment-gate)
- [Validation Side Effects](#validation-side-effects)
- [Codex Client](#codex-client)
- [Hermes Client And Readiness](#hermes-client-and-readiness)
- [Claude Code Client And Sync](#claude-code-client-and-sync)
- [Generic CLI Adapter](#generic-cli-adapter)
- [Dispatch Evidence](#dispatch-evidence)
- [Packaging And Sync](#packaging-and-sync)
- [Closeout Fields](#closeout-fields)

## Runtime Families

`superCC` 不是高于 `super` 的安全权威；它是 `super` 权限内的一种官署运行形态。它和普通并行 spawned-subagent 官署指向同一个官署本体，但 `superCC` 选择了更强的可见 runtime、wake、identity、uniqueness 和 closeout 证据门禁。每次使用必须由最新旨意显式点名 `superCC`，并在开朝后先生成 `runtime_selector_result`：

```text
runtime_selection_gate: PASSED | runtime_degraded | authority_blocked
supercc_runtime_family: visible_zellij_squad
runtime_client: auto | codex | hermescli | hermes_desktop_readiness | claude | cli
source_agent_label: Codex | Hermes | Claude | GenericCLI
supercc_normal_env_requirement: zellij+squad
```

选择规则：

- `superCC` normal 环境只有一个：当前执行面能证明 zellij session/panes 与 active `squad` identities。缺任一项即 `runtime_degraded` 或 `authority_blocked`。
- Codex、Hermes CLI、Claude Code 和其他显式配置的 CLI 可以是 zellij+`squad` 可见官署里的 selected client 或同步面；client 证据不能替代环境门禁。
- `--office-client auto` 是默认入口：先尊重 `COURT_OFFICE_CLIENT` / `COURT_SOURCE_CLI` / `COURT_OFFICE_CLIENT_COMMAND` 等显式环境，再让 `CODEX_THREAD_ID` 等当前会话强信号优先于只表示 provider 可用性的 `ANTHROPIC_*` / `CLAUDE_*` 弱环境标记，随后才按 Windows 父进程链、skill 路径和其他信号推断当前 CLI。全局存在某供应商凭据或模型变量不等于当前控制线程就是该 CLI；无法识别时保持 host fallback，而不是冒充已知 client。
- Hermes desktop/profile/session evidence 是 readiness/supplemental evidence。它可以证明 Hermes profile、session、skills、taizi policy 是否可用，但不能单独把 desktop/profile-native 会话升格为 normal `superCC`。
- 不允许只靠旧史馆记录、旧计划、静态包名、普通并行任务、Hermes profile readiness、Claude 普通会话或 desktop 会话声称 normal `superCC`。
- 不允许为支持 Hermes 或 Claude 而放宽 visible pane、`squad`、profile hash、`ENTER_DISPATCH`、task evidence、office uniqueness、request-rate gate、层级监督与 closeout 规则。

## Normal Environment Gate

Normal `superCC` must pass:

```sh
python -B scripts/ensure_supercc_court.py --check-only --no-auto-install-deps --format json
```

Required evidence:

- `visible_display_gate=PASSED` and `display_transport_gate=PASSED` from current zellij panes plus active `squad` identities.
- `office_client_gate=PASSED` for the selected pane client (`codex`, `hermescli`, `claude`, or generic `cli` when an executable is configured and available).
- `supercc_env_gate=PASSED` only when the zellij+`squad` display transport and selected office client both pass.
- `office_uniqueness_gate=PASSED` before claiming standing or dispatched named offices.

When the controlling process is not inside zellij, use `--zellij-session <name>` or rely on the launcher auto-selecting the newest active session containing `S Taizi #0001`. `zellij action list-panes` output that asks the caller to specify a session is not pane evidence and must be `runtime_degraded`, not a display pass.

`--turn-start --reclaim-existing` is the live turn-start action, not the read-only gate. It may reopen panes, release/archive stale identities, send the squad wake/control note first, native-enter the generated wrapper receive command for 三省, and write court-runtime state; use it only after `superCC` is explicitly open and live runtime mutation is allowed.

`scripts/supercc_office_state.py` owns the v1/v2 office-state schemas, normalized
workspace+zellij-session context ids, fail-closed validation, atomic state
replacement, turn-health append, and selected-context reads. The launcher
re-exports the compatibility API and injects dossier enrichment; watchdogs and
tests must continue using that API rather than duplicating state parsing.

## Validation Side Effects

Functional validation is non-mutating unless the command explicitly asks for live mutation:

```sh
python -B scripts/check_supercc_functional.py --workspace .
python -B scripts/check_supercc_functional.py --workspace . --live-mutating
```

Default `check_supercc_functional.py` mode is `read_only_audit`. It may inspect gates, run watchdog status with `--no-apply`/`--dry-run`, and dry-run dispatch shape, but it must not launch panes, wake offices, archive identities, write office state, closeout-silence panes, or alter squad identities. The old live launch/turn-start/dispatch/closeout smoke is available only behind `--live-mutating` and only when the active decree allows runtime mutation.

Every `ensure_supercc_court.py` JSON result must carry `side_effects` with `schema=court.supercc.side_effects.v1`, `selected_action`, `dry_run`, `mutates_runtime`, `planned_if_live`, and `applied`. Read-only gates such as `--check-only`, `--super-entry check`, and dry-run dispatch must report `mutates_runtime=false` and empty `applied`. A missing side-effect manifest, a read-only command that reports applied runtime changes, or a live-mutating command run without an explicit live boundary is `runtime_degraded` / semantic drift evidence.

## Codex Client

Codex client evidence is required only when `runtime_client=codex`. The Codex client branch still uses the same zellij+`squad` normal environment gate, plus:

- Codex CLI availability.
- visible core panes: 太子 and 三省; legacy inspection identities are not part of the default runtime shape.
- office profile/soul hash.
- `ENTER_DISPATCH` `SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER`, native-entered `SUPERCC_SQUAD_RECEIVE_COMMAND`, one second delayed second Enter, and `squad` mirror.
- structured `task_evidence` or equivalent direct assignment evidence for execution claims.
- `model_triggering_requests <= 20/minute` with explicit total budgets for stress tests and provider queue/backoff evidence. `--office-show-delay` is presentation-only, defaults to one second, has a hard 0-5 second range, and never becomes a provider throttle. The first office has no artificial cooldown; ordinary spawned agents always use zero presentation delay. A wait beyond five seconds must be labeled `queued_rate_limit` or provider retry/backoff, never hidden as office stagger.
- At 结诏, superCC office usage is summarized from existing task/direct
  assignment evidence and any runtime/provider usage surfaced by the selected
  client. This summary is a closeout gate, not a dispatch payload. If a visible
  office client or provider exposes exact usage, record it as
  `provider_reported`; otherwise record `agent_reported`, `estimated_fallback`,
  or `unavailable`. These records feed the decree-level
  `usage_source_breakdown`, `token_usage_precision`, `wall_clock_actual`, and
  `worker_elapsed_sum` fields at closeout.
- closeout silence/release evidence.

Terminal-visible office panes use per-office `agents/supercc-dossiers/<role>/AGENTS.md` dossiers as the long standing mandate. `ensure_supercc_court.py --write-agent-dossiers` writes or refreshes these files. Every selected office client process starts from the role dossier directory so the local `scripts/supercc_squad.py` wrapper can be invoked through stable relative paths; the real task workspace is passed separately through launcher environment such as `SUPERCC_TASK_WORKSPACE` and through client-specific allow/add-dir mechanisms when available. Codex additionally starts with `-C` pointing at the role dossier directory so the launch prompt can stay a compact manifest plus fast-path action contract.

## Hermes Client And Readiness

Hermes has two evidence classes:

- Hermes CLI as a selected terminal client: use `ensure_supercc_court.py --office-client hermescli` so the same zellij+`squad` normal environment gate is proven while Hermes CLI supplies the client evidence.
- Hermes profile/desktop readiness: use `ensure_hermes_supercc.py --surface cli|desktop --format json` to inspect profile/session readiness, taizi profile policy, profile-local skill/config/state evidence, and `squad` availability. This readiness is supplemental until zellij+`squad` has also passed.

Hermes rules:

- Any superCC activation from `default` or `taizi` must activate the `taizi` profile for the court entry without rewriting the user's sticky default profile.
- Office profile calls are silent by default. Evidence must point to the corresponding Hermes profile/session/conversation surface, not to raw private transcript bodies.
- Profile records must include `profile_home`, skill copy presence, `SOUL.md`, `config.yaml`, `state.db`, and profile-specific skill path when available.
- `ensure_hermes_supercc.py` is read-only. Its `hermes_profile_readiness_evidence=PASSED` means readiness only; actual named office work additionally requires `hermes_profile_dispatch_evidence` or visible zellij dispatch evidence for each claimed role.
- If the only evidence is profile readiness, set `profile_native_evidence_scope=readiness_only_not_dispatch_not_normal_without_zellij_squad` and named office execution must be `NOT_RUN` or `runtime_degraded`, not `PASSED`.
- A single merged subagent, combined-office review, or plain `delegate_task` without per-role profile/session evidence is `office_duty_enforcement=PARTIAL|FAILED`.
- Memory/conversation bridge records remain metadata-only: path, profile, session id, hash, lineages, keywords, and status. Do not copy raw Hermes conversations, auth files, tokens, cookies, API keys, private vaults, or full memory bodies into Shiguan/package artifacts.

## Claude Code Client And Sync

Claude Code receives the same skill rules through the active Claude skill root. On this host `.claude\skills\court-capability-router` is expected to resolve to the Codex skill copy, so syncing `.codex` also updates Claude. Claude Code can also be a selected terminal-visible office client through `ensure_supercc_court.py --office-client claude`.

Claude rules:

- Claude Code has no separate normal `superCC` exception. A Claude surface may claim normal `superCC` only when the same zellij+`squad` normal environment gate passes.
- Claude skill availability or ordinary Claude conversation state is readiness/sync evidence only.
- `runtime_client=claude` requires `claude --version` evidence and a visible zellij pane launched with a matching `squad join ... --client claude --protocol-version 2`.
- Claude office panes must start the Claude process from the role dossier directory, not from the host user home. The launcher pre-seeds `.claude.json` project trust for the role dossier path and passes the real task workspace through `--add-dir`; this avoids the Claude Code workspace trust yes/no prompt that is not durably persisted for direct home-directory starts.
- The Claude office client path must use the same role dossier, direct-superior, one-assignment wrapper receive, and upward memorial contract as Codex/Hermes CLI offices.
- All Claude and generic CLI office prompts must include a per-role shell contract. The contract must point to the local `scripts/supercc_squad.py` wrapper, or its `.sh`/`.ps1`/`.cmd` thin wrappers, using paths relative to the role dossier directory. Offices must not invent `cd` commands or hand-convert workspace paths; the wrapper resolves `squad` across POSIX sh/bash/zsh on Linux/macOS, PowerShell/pwsh, Windows WSL Bash, Windows Git Bash/MSYS, Cygwin, and cmd. This applies to every office role, not only `zhongshu`.
- Claude logs, Claude memory notes, older role prompts, or copied shell snippets that show bare `squad` commands, `cd` into a host workspace, manually converted native/POSIX home paths, or controller-side `zellij write-chars` are drift evidence, not launch authority. The current role dossier and generated shell contract supersede them. The controlling pane uses `ensure_supercc_court.py --turn-start` or `--enter-dispatch`; office panes use only the wrapper contract for receive/send/task traffic.

## Generic CLI Adapter

Any local CLI can be used as the terminal-visible office runtime when it can accept a prompt either as the final argument or on stdin:

```sh
python -B scripts/ensure_supercc_court.py --launch-offices zhongshu --office-client cli --office-client-command <tool> --office-client-arg=<arg> --office-client-prompt-mode argument
python -B scripts/ensure_supercc_court.py --super-entry plan --office-client <tool>
python -B scripts/ensure_supercc_court.py --super-entry plan --office-client-map zhongshu=<tool>
```

Rules:

- Use `--office-client cli` with `--office-client-command <tool>` for an arbitrary executable, or name the executable directly as `--office-client <tool>`. Per-office maps may also name a future/third-party CLI directly; unknown map values are normalized to `client=cli` with that value as the command.
- `--office-client-prompt-mode argument` appends the office prompt as the final argument. `stdin` pipes the prompt to the process.
- Generic CLI office processes start in the role dossier directory, matching Codex, Hermes CLI, and Claude Code, so relative wrapper commands are valid. The task workspace is available through `SUPERCC_TASK_WORKSPACE`; generic tools that need additional filesystem permissions must receive them through their own explicit flags.
- Generic CLI tools do not get a fabricated `squad --client` enum. The launcher joins `squad` with `--protocol-version 2` and records `office_client=cli`, command, args, prompt mode, selection source, and `cli_probe` (resolution plus version/help attempts) as evidence.
- `COURT_SOURCE_CLI=<tool>` or `COURT_OFFICE_CLIENT_COMMAND=<tool>` lets `--office-client auto` select a non-built-in CLI without changing the skill copy.

## Dispatch Evidence

Every dispatch packet under `superCC` must add the runtime selector fields:

```text
office_instance_kind: terminal_visible_pane | readiness_only_profile_session
office_transport: zellij_squad_codex | zellij_squad_hermescli | zellij_squad_claude | zellij_squad_generic_cli | readiness_only_profile | single_process_degraded
runtime_client: auto | codex | hermescli | hermes_desktop_readiness | claude | cli
runtime_selector_result: ...
source_agent_label: Codex | Hermes | Claude
calling_office: ...
direct_superior_source: ...
task_evidence: ...
squad_fallback_gate: PASSED | runtime_degraded | authority_blocked
```

Terminal-visible panes use the canonical route `dispatch_delivery_channel=NATIVE_DOUBLE_ENTER_VISIBLE` with `squad_delivery_order=SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER`: the dispatcher first creates the structured `squad task` and sends the mirror payload, then writes only the generated `SUPERCC_SQUAD_RECEIVE_COMMAND` wrapper receive command to the pane and performs the native double-Enter wake. Legacy reports may still contain `NATIVE_ENTER_FIRST_WITH_SQUAD_MIRROR`; treat it as an alias for the older native-first terminal-visible route, not as the current policy.

Default non-visible ministry dispatch uses `dispatch_delivery_channel=SQUAD_STRUCTURED_TASK_WITH_AUDIT_MIRROR_NON_VISIBLE_MINISTRY`. The router must not report native double-Enter success for that path: success requires a structured task id, a mirror carrying that id, uniqueness evidence, and `native_enter_dispatch.skipped=true` / `ok=false`.

Manual native typing from a controller/main pane is not a valid dispatch route by itself. A controller may only deliver native text through `ensure_supercc_court.py --turn-start` or `--enter-dispatch`, because those paths bind pane selection, uniqueness, physical Enter byte `13`, delayed second Enter, structured `squad task` evidence, `squad` mirror evidence, and the receive-command wake into one reportable record. If a transcript only shows raw `zellij write-chars` or a pasted prompt with no `dispatch_uid`, task evidence, squad mirror, and `SUPERCC_SQUAD_RECEIVE_COMMAND`, close it as `runtime_degraded` / invalid dispatch evidence.

Hermes readiness probes use `dispatch_delivery_channel=NOT_RUN_READINESS_PROBE_ONLY`. Legacy profile-native fallback evidence is not sufficient for normal `superCC`; it must be reported as readiness/degraded unless zellij+`squad` normal environment evidence and per-role dispatch evidence are also present.

The dry-run dispatch router must prefer the visible route order for normal `superCC`:

```text
SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER_DRY_RUN
NATIVE_DOUBLE_ENTER_VISIBLE_RECEIVE_COMMAND_DRY_RUN
HERMES_PROFILE_NATIVE_READINESS_SUPPLEMENT_DRY_RUN
```

For default non-visible ministry dispatch, the dry-run route order is only:

```text
SQUAD_STRUCTURED_TASK_WITH_AUDIT_MIRROR_NON_VISIBLE_MINISTRY
```

## Packaging And Sync

The portable package must include the unified zellij+`squad` normal gate:

- `SKILL.md` hard gate summary.
- `references/court-supercc-runtime-selection.md`.
- `scripts/ensure_supercc_court.py` for zellij+`squad` and selected visible office-client gates (`auto`, built-in `codex`/`hermescli`/`claude`, or generic `cli`).
- `scripts/supercc_office_state.py` for the portable v1/v2 context-partitioned state store used by the launcher and watchdog.
- `scripts/ensure_hermes_supercc.py` for Hermes CLI/desktop readiness that does not pass normal `superCC` alone.
- `scripts/check_active_copy_hashes.py` including `.agents`, `.codex`, `.claude`, `.hermes`, and the platform user-data Hermes skill target when present.
- `agents/supercc-dossiers/<role>/AGENTS.md` for terminal-visible light bootstrap.
- package validation that excludes host-local Shiguan bodies, raw logs, private profile records, secrets, tokens, cookies, API keys, memory decisions, import queues, and generated local indexes.

Before claiming Codex, Hermes, and Claude are all synchronized, sync active installed copies or explicitly declare a single source-of-truth copy. Expected active targets are `.agents`, `.codex`, `.claude` junction/symlink, `.hermes`, and the Hermes skill copy under the current platform user-data directory.

## Closeout Fields

Complete Shiguan memorials for `superCC` must include:

- `runtime_selection_gate`
- `supercc_runtime_family`
- `runtime_client`
- `runtime_selector_result`
- `source_agent_label`
- `supercc_normal_env_requirement`
- `supercc_env_gate`
- `visible_display_gate`
- `display_transport_gate`
- `office_client_gate`
- `cli_probe`
- `hermes_supercc_gate`
- `hermes_surface`
- `hermes_forced_profile`
- `hermes_desktop_zellij_gate`
- `hermes_profile_native_evidence`
- `hermes_profile_readiness_evidence`
- `hermes_profile_dispatch_evidence`
- `profile_native_evidence_scope`
- `profile_session_activity`
- `squad_fallback_gate`
- `office_uniqueness_gate`
- `task_evidence`
- `supervision_channel`
- `supervision_evidence`
- `silent_supervisor`
- `supercc_watchdog`
- `watchdog_process`
- `watchdog_log_jsonl`
- `watchdog_pid_file`
- `watchdog_daemon_start`
- `watchdog_daemon_stop`
- `watchdog_no_visible_window`
- `watchdog_actions`
- `watchdog_abnormal_roles`
- `functional_check_mode`
- `supercc_side_effects_schema`
- `supercc_side_effects_mutates_runtime`
- `legacy_patrol_visible_pane`
- `package_ready_gate`
- `package_exclusion_check`
- `decree_usage_estimate`
- `usage_source_breakdown`
- `token_usage_precision`
- `wall_clock_actual`
- `worker_elapsed_sum`

If zellij+`squad` evidence is missing, if a generic CLI lacks `cli_probe`, if Hermes/Claude readiness evidence is reported as normal `superCC`, if provider usage is missing but reported as exact, or if a daemonized silent supervisor lacks closeout stop/persistence evidence, close as `DONE_WITH_CONCERNS`, `runtime_degraded`, `authority_blocked`, or return for repair. Do not close as `DONE`.
