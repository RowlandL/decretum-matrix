# Court Office Model Routing And V1/V2 Schema Compatibility

This volume governs task-aware model recommendations for ordinary Codex office
agents while preserving the model-reserved Multi-Agent V2 tool schema. It does
not turn a collaboration task path into an office identity and does not rewrite
Claude Code or Hermes model configuration.

## Scope

- Applies to ordinary Codex V1 or V2 child spawns created for a named office.
- A path such as `/root/xingbu_wave3` is only the collaboration address. It is
  never proof that the child loaded the 刑部 office dossier.
- Current model-reserved `collaboration.spawn_agent` exposes only the compatible
  task fields (`message`, `task_name`, and `fork_turns`). It hides
  `agent_type`, `model`, `reasoning_effort`, and `service_tier`.
- The parent must put the explicit `role_key`, direct superior, assignment,
  expected result, and useful dossier/skill source pointers in the bounded task
  message. The child acknowledges the office identity from that assignment and
  reads the office dossier only when the current duty needs its detail.
- Role files under `%CODEX_HOME%/agents/*.toml` remain model-neutral. They are
  retained for native role discovery on compatible host-managed or legacy
  paths, but current model-visible V2 spawn must not claim that `agent_type`
  selected one of them.
- Claude Code office copies receive no office-level model override and inherit
  the main Claude thread model.
- Hermes receives no office-level model override in this phase, inherits the
  active Hermes profile model, and remains a separate future design item.
- Terminal-visible pre-launched `superCC` sessions are not silently relabeled as
  dynamically rerouted. Per-dispatch model switching for an already-running
  pane requires a separate lifecycle design.
- A host-managed fresh Codex worker is a separate leaf process/session. It may
  apply a proved top-level model/effort route, but it is neither a V1/V2 child
  spawn nor evidence of a same-session protocol switch.

## Required Evaluation

Before admission and again at the concrete spawn, record:

- `assignment`
- `task_focus`
- `complexity = low | medium | high | critical`
- `risk = low | medium | high | critical`
- `ambiguity = low | medium | high | critical`
- `transport = codex | claude-code | hermes`

Missing evaluation is not permission to invent a fixed per-office model.

## Codex Recommendation

| Decision | Recommended model | Highest supported reasoning effort |
| --- | --- | --- |
| Critical/high-risk, deep architecture, security/privacy, destructive work, semantic-drift review, or final integration | `gpt-5.6-sol` | `ultra` |
| Low complexity, low risk, low ambiguity, and explicitly light clerical/status/formatting/indexing work | `gpt-5.6-luna` | `max` |
| Balanced general work not captured above | `gpt-5.6-terra` | `ultra` |

`court.office.model_route.v2` records this recommendation and the selected
model's real highest supported effort. `ultra` is not fabricated for Luna; its
maximum is `max`.

The recommendation is not a claim that a V1/V2 child applied an override.
Both inherit the main thread model and effort. The verified fresh-session
worker below may apply the recommendation at top level; it is not a child.

## Compatible V2 Spawn Contract

The model-visible call is limited to:

```text
message = <bounded assignment plus role/dossier context pointers>
task_name = <unique collaboration task name>
fork_turns = none
```

The following fields must not be exposed in the model-visible reserved tool:

```text
agent_type
model
reasoning_effort
service_tier
```

The required host configuration is:

```toml
[agents]
max_depth = 4

[features.multi_agent_v2]
enabled = true
max_concurrent_threads_per_session = 16
hide_spawn_agent_metadata = true
```

Do not set legacy `[agents].max_threads` while Multi-Agent V2 is enabled. V2
counts the root inside the 16-slot session ceiling and internally allows at
most 15 child threads. A running session may require restart before a changed
tool schema appears.

## Verified V1 And Resume Limits On Codex 0.144.1

Disposable loopback probes against native Codex 0.144.1 established the exact
current boundary:

- A fresh V1 session exposes `agent_type`, `model`, `reasoning_effort`, and
  `service_tier`; `agent_type` was observed in the child request.
- `[agents].max_threads=15` provides fifteen child slots while the root remains
  active, matching the logical sixteen-thread court ceiling.
- A valid V1 spawn carrying `gpt-5.6-luna` and `max` still produced a child
  request that inherited the parent model and had no applied reasoning value.
  Schema presence is therefore not proof of model/effort application.
- Resuming the same exact session UUID after changing V2→V1→V2 configuration
  preserved the initial `collaboration` namespace in all three phases. The
  current host cannot perform the proposed same-session protocol switch.

Consequently, V2 is the production startup protocol. The former command-
selectable or bidirectional V1/V2 switch is deprecated; V1 code, fixtures,
historical configuration, and immutable backups remain only as dormant recovery
evidence and do not authorize production selection. The protocol launcher stays
fail closed and must not stop the production backend unless a newer explicit
user decree reopens the capability with fresh proof. Editing startup config
never relabels an already-open session.

## Verified Fresh-Session Worker Boundary

`scripts/court_codex_office_worker.py` provides a separate host-managed leaf
transport for tasks whose model recommendation must actually be applied. Its
execution gate requires all of the following:

- a host proof covering the exact Codex version and each allowed model/effort
  pair;
- an exact native `codex.exe` path that matches that proof's path evidence;
- `-C` set to the selected office dossier directory and a role context packet for
  that role;
- both `multi_agent_v2` and legacy `multi_agent` disabled for the worker;
- no `resume`, `--last`, or `--ephemeral` selector;
- post-run session JSONL evidence whose `turn_context` matches the selected
  model, highest supported effort, and dossier cwd.

The worker may report `model_override_applied=YES` only after those checks pass.
It creates a new session and does not receive the current collaboration tree or
claim a `/root/*` task address. Current V1/V2 children remain inheritance-only.
Raw stderr is not persisted.

## Acknowledgement And Failure

Before an ordinary Codex office enters substantive `running`, its role
acknowledgement must match:

- `model_route_id`
- `model_override_applied=NO`
- V2: `inheritance_policy=inherit_main_thread_model_reserved_schema`
- V1: `inheritance_policy=inherit_main_thread_model_v1_agent_type`
- the explicit `role_key`, `direct_superior`, task boundary, expected result,
  and `agent_dossier_loaded=YES|NO|NOT_NEEDED`.

For exact short reply connectivity tests, the parent sends a compact assignment
with role_key, direct_superior, task boundary, expected exact reply, and
skill/dossier pointers only when already useful. Host acceptance plus the child
office's exact reply is sufficient for the light duty. Missing optional dossier
context must be recorded as `agent_dossier_loaded=NOT_NEEDED`, not inflated into
a failure or a reason to run bulk validation first.

The active model and effort may be recorded as evidence when the host exposes
them, but they are not accepted as proof of a model override. Claude Code and
Hermes acknowledge their own exact inheritance policies. Any mismatch sets
`model_route_status=FAILED`, fails role acknowledgement, closes that agent record, and must
not be reported as completed office work.

## Implementation Surfaces

- `scripts/court_model_router.py`
- `scripts/court_office_bootstrap.py`
- `scripts/court_runtime.py`
- `scripts/court_codex_office_worker.py`
- `scripts/check_court_codex_office_worker.py`
- `scripts/ensure_court_agent_config.py`
- `scripts/sync_codex_agents_from_profiles.py`
- `scripts/check_court_model_router.py`
- `scripts/check_court_agent_config.py`
- `scripts/check_codex_agent_roles.py`
