# Closeout Installation And Validation

Parent: [court-closeout-validation.md](../court-closeout-validation.md) -> `## Installation And Validation`

This shard owns installation, validation, and package-ready policy for closeout. Load it when a task needs concrete validation command classes, package-ready gates, or install/package evidence without opening the full closeout reference.

## Installation And Validation

For a portable install recipe, read `references/install.md`.

After installation or catalog changes, choose validation by side-effect class.

Read-only validation uses the active host Python executable (`python`,
`python3`, or Windows `py -3`). Prefer `python -B scripts/...` paths in examples;
Python accepts these paths in PowerShell/cmd, Linux shells, and macOS shells.

```sh
python -B scripts/check_catalog.py --strict
python -B scripts/check_portability.py
python -B scripts/ensure_portable_court_bootstrap.py --check-only --format text
python -B scripts/ensure_court_agent_config.py --check
python -B scripts/reevaluate_memory_decisions.py --dry-run --limit 20
python -B scripts/query_shiguan_index.py "self-test"
python -B scripts/check_supercc_functional.py --workspace .
python -B scripts/ensure_supercc_court.py --check-only --no-auto-install-deps --format json
python -B scripts/ensure_hermes_supercc.py --surface desktop --format json
python -B scripts/ensure_hermes_supercc.py --surface cli --format json
```

Writeback validation, only when local Shiguan/catalog artifacts may be regenerated:

```sh
python -B scripts/archive_checkpoint.py --topic "self-test" --phase "复核" --status "DONE" --summary "archive script works" --evidence "manual self-test" --next "none"
python -B scripts/rebuild_shiguan_index.py
python -B scripts/grow_shiguan_tree.py
python -B scripts/memory_decision.py --topic "self-test" --decision "SKIP" --content "no durable memory" --reason "self-test only"
```

Slow sync/export validation, only when Obsidian/export evidence is in scope:

```sh
python -B scripts/export_shiguan_obsidian.py --out "./Court Shiguan Export" --check --zip
python -B scripts/sync_shiguan_obsidian_vault.py --dry-run
```

The catalog check verifies whether this skill's catalog contains a readable
`Court Department Capability Map`, whether `find-skills` and system
`skill-creator` are present, and whether the standing court agents and recursive
agent settings are available. If the map is missing, use this skill's fallback
map. If `find-skills` or `skill-creator` is missing, 吏部 must recruit or repair
the missing prerequisite before full court routing is considered healthy. If
`find-skills` is missing, report
`https://www.skills.sh/vercel-labs/skills/find-skills` and
`npx skills add https://github.com/vercel-labs/skills --skill find-skills`. If
`agents.max_depth < 4`, V2 cannot be resolved, or the V2 mapping is invalid, run
`python -B scripts/ensure_court_agent_config.py --write --protocol v2` and
restart Codex to reach the intended startup target. Valid production V2 requires
total threads 16, hidden spawn metadata, and no legacy `agents.max_threads`.
The former bidirectional V1/V2 switch is deprecated; V1 validation fixtures and
backups are recovery evidence, not a routine production target. Any production
protocol write requires a byte-for-byte exclusive immutable backup first, with
only its path/hash/attributes recorded in shared Shiguan. Until a lower bounded but
otherwise coherent mapping is remediated, report `compatible_below_recommended`
and operate inside the smaller budget when the task does not require more.

Package validation semantics:

- `package-ready` is a report state, not permission to build a package. It may
  be claimed only after `quick_validate.py`, `check_catalog.py`,
  `check_codex_agent_roles.py`, `check_supercc_functional.py` when live
  superCC runtime testing is requested, relevant Codex/Hermes superCC/profile
  checks including `ensure_hermes_supercc.py --surface desktop` and
  `--surface cli` when Hermes support is in scope, semantic reload, and Shiguan
  closeout fields pass. When standing profiles are installed
  for Codex, run `sync_codex_agents_from_profiles.py --write` instead of copying
  structured `[profile]` templates directly into `%CODEX_HOME%\agents`.
- The package-ready hard gates must record `package_ready_gate` and
  `package_exclusion_check`. The exclusion check must confirm that no secrets,
  private vaults, raw private Shiguan bodies, raw logs, generated local
  artifacts, generated indexes/graphs, plan archives, memory decisions, import
  queues, peer state, Obsidian sync config/API keys, or unrelated projects are
  selected for packaging.
- Do not actually run `package_skill.py` unless a separate 太子回奏 authorizes
  packaging for the current decree. A validation-only decree records the
  intended validation path and stops before creating or replacing a release
  artifact.
