# Capability Verification Index Skill Gate

This shard governs the active index skill layer for `court-capability-registry.md`.
Load it when capability verification, 官籍 refresh, recruitment, or dispatch depends
on whether an existing skill/agent/tool should be considered available.

For the accepted C1/C2-RC handoff and its runtime/result boundary, see
[Court Runtime Result And Recruitment Contract](court-runtime-result-and-recruitment-contract.md).
Broader public discovery, creation, installation, or write behavior below is
outside the I1/C purified lane. For I1/C, the dedicated contract governs:
zero network calls, zero external writes, no capability mutation,
`ASK_USER` intent-only handoff, and `C2_FULL=HOLD_BY_AUTHORITY`.

## Required Gate

Capability verification must not stop at a static file scan or wait for the user
to explicitly name a local capability. Before reporting a capability as absent,
stale, or ready for dispatch, 吏部/户部 must prove the active index layer:

1. `refresh_capability_registry.py` has refreshed the local 官籍/catalog, proved it
   current, or reported `authority_blocked` / `runtime_degraded`.
2. `find-skills` is present and usable as the discovery/recruitment index skill
   for missing or candidate skills.
3. `skill-creator` and `.system/skill-creator/scripts/quick_validate.py` are
   present for skill format validation and repair.
4. `check_catalog.py --strict` validates the registry, index shard, token policy,
   prerequisites, and package-critical file list.
5. `check_capability_index_gate.py --query <need>` or equivalent catalog lookup
   has selected the smallest suitable skill/agent/MCP/CLI/script set for the
   current decree.

Report the result as `capability_index_skill_gate=PASSED | PARTIAL | FAILED |
authority_blocked | runtime_degraded`. Do not claim a new or repaired capability
is fully dispatchable until this gate is at least `PASSED`, or until 门下 explicitly
accepts a stale-catalog caveat for the current decree.

## Recruitment Order

When the requested capability is missing or ambiguous, use this order:

1. Search existing local roots through the refreshed catalog:
   `%USERPROFILE%\.codex\skills`, `%USERPROFILE%\.agents\skills`, and
   `%USERPROFILE%\.codex\agents`.
2. Use `find-skills` for public skill discovery and candidate comparison when a
   reusable skill may exist.
3. Use `skill-installer` or the explicit install command only under the active
   execution authority.
4. Use `skill-creator` only when no suitable existing skill exists or when an
   installed skill needs format/structure repair.
5. Re-run `refresh_capability_registry.py` and `check_catalog.py --strict` after
   installation, copying, or repair.

## Invocation Rule

Use the refreshed index to call the best matching capability without requiring
the user to name it. This is not permission to call every candidate. Selection
must stay bounded by task fit, authority class, path/service/risk/cost/privacy
scope, and the evidence contract. If the selected capability requires a
state-changing MCP write, install, paid action, secret, private upload, external
service, or broader workspace change, stop according to the active authority;
otherwise proceed with the indexed skill/agent/MCP/CLI/script directly.

## Registry Record Contract

- MCP names come only from direct top-level `mcp_servers`/legacy `mcp` entries;
  the server node must contain a direct declaration key (`command`, `url`,
  `transport`, `enabled`, `disabled`, or explicit marker). Nested-only
  environment tables cannot create candidates. Plugin nodes follow the same
  direct-declaration rule; nested-only settings do not register a plugin.
- Plugins use `kind=plugin`. Their embedded skills use `kind=skill` with
  `source=codex_plugin` so selection can distinguish the container from the
  callable skill.
- The deterministic C2 recruitment registry serializes only
  `kind=skill|plugin|mcp` and
  `source=local_skill|codex_plugin|local_plugin|local_mcp`. Both standalone
  skill roots map to `local_skill`; agents and CLIs remain only in the separate
  legacy broad catalog path.
- Disabled capabilities remain indexed with `enabled=false` and
  `dispatchable=false`; selection must fail closed even when query fit is strong.
- Offline fixtures inject all roots and executable inventories. They must make
  no network calls, no catalog writes, and no ambient-host fallback reads.
- Public metadata discovery runs only when the injected authority permits it.
  Every create/install/write outcome is `ASK_USER` and a structured handoff to
  尚书省; authority or verification failures preserve blocked/runtime-degraded
  reason codes and never trigger direct 吏部 mutation.
- Records use stable fields and sorting, contain no per-record timestamp, secret,
  environment value, account identifier, or private absolute host path.
- Plugin ID components must be path-safe. Resolve candidates relative to each
  injected root and reject traversal/escape before reading. Deduplicate by full
  `(kind, source, name, relative_path)` identity; cross-source `(kind, name)`
  conflicts are compared using the full normalized semantic payload. Equivalent
  duplicates collapse; differing relative paths, content, command/URL, enabled
  state, or evidence emit one fail-closed record with `verified=false`,
  `dispatchable=false`, `LOCAL_METADATA_CONFLICT`, and deterministic conflict
  digests. Sort exactly by
  `(kind, name, source, relative_path)`. Every emitted record has the exact
  mandatory schema including boolean `verified` and list `evidence`.

## Token Policy

This gate follows the three-level token policy:

- `metadata_precision`: record exact source roots, paths, mtimes/hashes when useful,
  catalog paths, and whether `find-skills`, `skill-creator`, `quick_validate.py`,
  `refresh_capability_registry.py`, `check_capability_index_gate.py`, and
  `check_catalog.py` were used.
- `body_reference_policy`: cite catalog rows, shard paths, and compact evidence
  handles. Do not paste whole skill bodies, full generated catalogs, raw Shiguan
  logs, or private memory text into dispatch context.
- `on_demand_loading`: load this shard only for capability verification,
  recruitment, skill repair, registry drift, or package/index audit. Otherwise use
  the center metadata in `SKILL.md` and `references/README.md`.
