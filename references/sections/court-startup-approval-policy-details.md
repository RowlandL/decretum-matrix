# Startup Approval Policy Details

This shard owns the detailed authority rules for `court-startup-authority.md`.
Load it for the exact `approval|autonomous|super` authority domain, orthogonal
`serial|parallel` behavior, the separate superCC runtime boundary, packaging
authority, service startup, MCP calls, multi-agente dispatch, or dangerous
autostart review.

## Contents

- `## Authority Classes`
- `## Capability Invocation`
- `## SuperCC Runtime Boundaries`
- `## Dangerous Autostart`
- `## Packaging Governance`

## Authority Classes

Court approval mode is a skill-level execution authority. It should align with
Codex sandbox and approval settings where possible, but it does not silently
mutate global Codex configuration unless the task explicitly includes
configuration work or the active authority allows that change.

- `approval` / **只读权**: inspect only. Local file reads, catalog/archive reads,
  capability listing, and non-mutating reasoning are allowed. Ask before shell
  commands, file writes, installs, configuration changes, network/web access,
  high-risk MCP calls, MCP writes, operations outside the workspace, destructive
  operations, paid actions, or secret/private-data handling. Shiguan WebUI,
  LAN listener, autosync, daemon, and service watchdog startup are
  state-changing under `approval` unless the newest decree allows them.
- `autonomous` / **管理权**: execute and write inside the user's stated scope.
  Workspace writes, known skill/agent roots, explicitly named project paths,
  sandbox escalation, and work outside the current workspace are allowed when
  task-related, path-scoped, and recorded in Shiguan. Ask before destructive
  operations, paid actions, secret/private-data handling, unverified installs,
  private-data upload, broad scope changes, or surprising external application
  state changes.
- `super` / **完全控制权**: execute in-scope work automatically, including shell
  commands, writes, network/web access, MCP probes, configuration edits, sandbox
  escalation, package generation, and multi-agente dispatch. Do not ask merely
  because an in-scope task uses multiple agente; ask or report
  `authority_blocked` only when the action crosses an unapproved path, service,
  risk, cost, privacy, external-state, hard-stop, or host-enforced gate.
- `behavior=serial|parallel` is independent of authority, so all six authority /
  behavior pairs are valid. `super并行` / `super parallel` means only
  `authority=super, behavior=parallel, runtime=native`; it never starts or probes
  zellij/`squad`, visible standing offices, superCC state, wake rules, or closeout
  choreography.

`superCC` is not an authority class. It is a distinct startup/runtime entry that
carries one exact three-authority value and one explicit behavior. Normal superCC requires
zellij panes, `squad`, and selected client/readiness evidence. Native and superCC
may read the same neutral standing-office configuration pointer, but must
not share runtime state, dossiers, transports, admissions, or lifecycle paths.

## Capability Invocation

Capability selection is index-first. The court does not wait for the user to
name a specific local skill, agente, or MCP, and it must not invoke every
possibly related capability. 吏部/户部 first read the refreshed 官籍/catalog and
active index gate, select the smallest suitable skill/agent/MCP/CLI/script set,
then 尚书省 dispatches or calls the selected capability under the current
authority and evidence contract.

Use `references/sections/court-capability-verification-index.md` and
`scripts/check_capability_index_gate.py --query <need>` for capability
verification. If the selected capability requires a state-changing MCP write,
install, paid action, external service, secret, private upload, or broader
workspace change, stop according to the active authority; otherwise proceed
without an extra user prompt.

## SuperCC Runtime Boundaries

Before `superCC`, 太子/户部 must run the runtime selection gate from
`references/court-supercc-runtime-selection.md`.

Codex branch:

```sh
python -B scripts/ensure_supercc_court.py --check-only
```

Hermes branch:

```sh
python -B scripts/ensure_hermes_supercc.py --surface cli --format json
python -B scripts/ensure_hermes_supercc.py --surface desktop --format json
```

The normal gate confirms zellij, `squad`, selected client evidence, bounded
recursive agent settings, and role-wide uniqueness. Hermes confirms
profile/session readiness, taizi activation policy, and profile-local
skill/config/state evidence as supplemental evidence; Hermes desktop does not
skip zellij for normal `superCC`.

Healthy visible office panes must do their own office work through `squad`;
太子/main pane may relay and synthesize but must not perform 三省 deliberation,
尚书 dispatch, 六部 execution, or 史馆 recording on their behalf. The pressure gate
is request-rate based (`model_triggering_requests <= 20/minute`) plus any explicit
total request budget. 429/rate-limit pressure is repaired by reuse, queueing,
stagger, and backoff, not by launching duplicate panes or 太子代工.

`superCC` does not authorize raw secret logging, private vault ingestion,
unbounded descendants, paid actions, public tunneling, unverified downloads,
dangerous autostart registration, or irreversible destruction.

## Dangerous Autostart

A no-sandbox autostart task is not ordinary `super` execution. Installing or
enabling this skill authorizes only the startup check and, under `autonomous` or
`super`, generation of review artifacts. Actual Windows Task Scheduler
registration for `codex --dangerously-bypass-approvals-and-sandbox` requires
explicit dangerous confirmation after 太子回奏 names the task name, trigger,
command, working directory, log path, revoke command, and risk.

## Packaging Governance

- Do not package by default for routine edits, local inspections, small UI fixes,
  or ordinary checkpoints.
- Package when the user explicitly orders it, when a long-running delivery
  reaches final acceptance, or when the result is meant to be an installable
  skill release.
- Under `approval`, ask before generating or replacing an install package.
- Under `autonomous` and `super`, after 三省六部 review and 门下省 approval, may
  generate or replace the package automatically when packaging fits the decree,
  the target path is known, and validation evidence is available.
- Public release packages must be portable: do not include this host's Shiguan
  record bodies, private memory decisions, generated local capability catalogs,
  raw logs, import queues, or host-local knowledge graph/index data. Use
  `scripts/package_skill.py` so the zip ships only the core court framework,
  standing-official templates, scripts, web manager, empty Shiguan seed, and
  portable install notes.
