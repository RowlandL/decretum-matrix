# Hermes Delegation Feasibility

Use this reference when configuring Dercretum-Matrix（诏令矩阵） (`decretum-matrix`,
invoked as `$decretum-matrix`) for Hermes Agent `delegate_task`, standing court
agents, startup hooks, or nested smoke tests.

## Runtime facts

- Hermes can run court offices through `delegate_task` when the parent passes each office's role contract in `goal`/`context`.
- Hermes does not natively load Codex custom-agent `.toml` personas as subagent system prompts. Treat `.toml` files as source material and mirror them into a Hermes-readable registry.
- The local neutral registry is `references/hermes-standing-agents/registry.json`; prompt text is also rendered in `references/hermes-standing-agents/role-prompts.md`.
- The Hermes config may contain `delegation.court_standing_agents` as a local routing hint, but the actual runtime proof is a `delegate_task` smoke test.

## Safe setup sequence

1. Avoid interactive diagnostics such as bare `hermes tools`; use non-interactive checks (`hermes config check`, scripts, direct file reads) unless PTY/input is provided.
2. Back up `config.yaml`, `SOUL.md`, `%USERPROFILE%\.codexgents`, and this skill's `agents/standing-officials` under `$HERMES_HOME/backups/<task>-<timestamp>/`; include a restore script.
3. Sync only meaningful mirror drift from this skill's `agents/standing-officials/*.toml` into `%USERPROFILE%\.codexgents`.
4. Generate/update `references/hermes-standing-agents/registry.json` from the `.toml` files.
5. Ensure Hermes delegation has bounded recursion and bounded child runtime: `max_concurrent_children >= 8`, `max_async_children >= 8`, `max_spawn_depth >= 3`, `orchestrator_enabled: true`, `subagent_auto_approve: true`, and `child_timeout_seconds` set to a finite value such as `300` when the user has granted the appropriate authority. A zero child timeout can make smoke-test subagents appear dead indefinitely.
6. Add or preserve `SOUL.md` startup rules requiring `$decretum-matrix` loading and autonomous `delegate_task` use for non-trivial court work.
7. Run non-interactive validation: config parse/assertions, `check_catalog.py`, `refresh_capability_registry.py`, `ensure_court_agent_config.py --check`, `check_court_runtime.py`, and Shiguan import queue check.
8. Verify with real `delegate_task`: one leaf role, parallel 三省 leaves, and 尚书省 as `role='orchestrator'` attempting nested 六部 dispatch.

## Loop safeguards

- If `skill_view` or `skill_manage` fails on linked files because it resolves to another skill root, stop retrying that shape. Use `read_file`/terminal Python with the absolute Hermes skill path.
- If `write_file` unexpectedly resolves a Hermes skill path into `%USERPROFILE%\.codex\skills`, stop using it for this path and write with terminal Python after verifying the destination.
- If a command opens an interactive menu or repeats output, stop it and switch to a non-interactive command or PTY with explicit input.
- Do not claim a role ran unless a real subagent returned evidence, or mark it `runtime_degraded`.


## Dispatch safety gate

When delegation health is uncertain, do not start with broad 三省+尚书 nested batches. First launch one minimal leaf health probe with no tools and an immediate-return report contract. If it does not return promptly, mark `parallel_dispatch: runtime_degraded`, stop launching more children in that decree, and continue with main-agent court synthesis plus local non-interactive validation. Do not wait indefinitely for background delegation children; record their delegation ids and the fallback.

