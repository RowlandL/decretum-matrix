# Capability Registry / 官籍与能力账册

渐进加载注记：本卷由原 `SKILL.md` 顶级章节机械迁移而来，保留原文语义用于按需加载。新的短 `SKILL.md` 是入口、硬门禁与直接索引；本卷是该入口直接链接的 governing reference。若旧文出现“必须写入 SKILL.md”等位置性表述，在本次渐进加载结构下解释为：硬门禁、触发、三权、只读、安全、状态机、史馆/记忆、语义再载入、奏报模板等规则必须在短 `SKILL.md` 保持摘要和直链；细节规则可写入本卷等直接链接 governing reference。史馆仍只作证据与召回锚点，不替代本 skill 源文件与 governing references。

原始来源：`SKILL.md` sha256 `64c7a9089275de004bbd2fc4e9c59633d2bbfe9e2a355178816c3da65f6563c9`。本卷章节：`Capability Registry And Personnel System`, `Catalog Refresh`。

## Contents

- [Capability Registry And Personnel System](#capability-registry-and-personnel-system)
- [Capability Verification Index Skill Gate](#capability-verification-index-skill-gate)
- [Catalog Refresh](#catalog-refresh)

Runtime result and bounded recruitment governance is defined in
[Court Runtime Result And Recruitment Contract](sections/court-runtime-result-and-recruitment-contract.md).
Broader public discovery, creation, installation, or write behavior elsewhere in
this registry is outside the I1/C purified lane. For I1/C, the dedicated contract
governs: zero network calls, zero external writes, no capability mutation,
`ASK_USER` intent-only handoff, and `C2_FULL=HOLD_BY_AUTHORITY`.

## Moved Source

## Canonical Skill Identity

The authoritative identity contract is
[`manifests/skill-identity.v1.json`](manifests/skill-identity.v1.json).
The current display name is `Dercretum-Matrix`; `诏令矩阵` is its Chinese
explanation. The only canonical skill record and invocation are `decretum-matrix` and `$decretum-matrix`.

`court-capability-router` remains an allowlisted repository, install-directory,
Shiguan-namespace, Python/environment, and service locator. A canonical registry
record may therefore point to `court-capability-router/SKILL.md`, but its `name`
must remain `decretum-matrix`. The old `$court-capability-router` invocation is a
`deprecated` compatibility input with `alias_support=probe_required` and `compatibility_claimed=false` until
a native loader probe proves otherwise. Do not create a second skill directory,
package authority, or legacy-name registry record to simulate an alias.

## Capability Registry And Personnel System

The capability graph is not just a department lookup table. It is the court's
官籍: a personnel and capability registry used by 吏部, 户部, 尚书省, 刑部, and
史馆 to decide who may serve where.

Use this four-stage personnel model:

1. **官籍**: register each skill, MCP, CLI, script, custom agent, or worker agent
   with source, scope, tools, permissions, dependencies, risks, and evidence.
   Keep capability roots distinct:
   - `%USERPROFILE%\.codex\skills`: primary Codex skill / 工坊技艺 library.
   - `%USERPROFILE%\.agents\skills`: Agent Skills fallback and cross-host 工坊技艺 library.
   - `%USERPROFILE%\.codex\agents`: actual Codex custom agents / standing court officials.
     Installed Codex role files must be string-only TOML rendered by
     `scripts/sync_codex_agents_from_profiles.py`; do not copy structured
     `agents/standing-officials/*.toml` files with `[profile]` tables directly
     into this directory, and do not merge multiple agents into a single TOML
     because Codex role discovery expects separate role files. Treat each TOML
     as a compact discovery shim. Shared long-form standing rules may live in
     per-role `agents/supercc-dossiers/<role>/AGENTS.md` dossiers referenced by
     `agent_dossier_path` / `agent_dossier_hash`; ordinary `super` subagents use
     those dossiers only when the dispatcher attaches/reads the file or launches
     a child Codex session with that dossier directory as cwd. Standing officials
     must still have a structured
     profile/soul contract in the template source with
     `role_key`, `office_zh`, `direct_superior`, duty, allowed/prohibited
     actions, procedure, authority basis, report/evidence/heartbeat contracts,
     dispatch-channel policy, release policy, `profile_version`, and
     `profile_hash`. The profile is part of 官籍 evidence, not decorative prompt
     text.
   - `zellij`, `squad`, and `codex`: under `superCC`, the local court substrate
     for visible panes, 奏折/message traffic, and real Codex official sessions.
     They are registered as runtime capabilities, not as extra approval to
     bypass safety gates.
   - `supercc_watchdog.py`: silent local supervisor/planner for superCC
     429/rate-limit, abnormal close, and abnormal silence evidence. It uses
     packaged scripts, Python, PATH-resolved zellij/squad, optional CLI command
     probes, JSON/JSONL records, and explicit `--daemon` / `--stop-daemon`
     lifecycle controls. It must not open a visible monitor pane or require a
     GUI/backend service.
   - `patrol-inspector`: legacy 监察使 / 监察agente diagnostic identity retained
     for compatibility and archival evidence. It is not part of routine startup
     or the default visible core. Routine supervision must use the silent script
     path; correction remains owned by the direct hierarchy. It does not
     approve, dispatch 六部, replace 门下/尚书 judgment, or remain awake after
     closeout without a separate long-running hidden-supervision approval.
2. **铨选**: 吏部 evaluates ability dimensions before appointment. Do not assign
   by name alone.
3. **差遣**: 尚书省 grants a task-specific mandate. A capability may serve multiple
   offices over time, but each decree must state the current office, allowed
   actions, forbidden actions, and evidence required.
4. **考课**: after work, 史馆 records outcomes and 吏部 updates future fitness from
   verification, failures, user corrections, overreach, and useful discoveries.

Capability dimensions:

| Dimension | Codex meaning |
| --- | --- |
| 身 | Environment fit, permissions, dependencies, sandbox and path boundaries. |
| 言 | Clarification quality, report quality, user-facing and parent-agent communication. |
| 书 | Code/document structure, formatting discipline, maintainability, contract adherence. |
| 判 | Judgment, risk recognition, tradeoff quality, verifiable decision-making. |
| 德行 | Safety, honesty, respect for user changes, no unauthorized scope expansion. |
| 才用 | Domain skill, tool fluency, prior evidence, task match. |
| 劳效 | Delivery record, test evidence, reliability, defects and corrections. |

Authorities:

- 礼部 may define examination/rubric text and output contracts, but does not
  appoint workers.
- 吏部 registers candidates, scores capability dimensions, recommends office fit,
  and maintains官籍/考课 records.
- 吏部 is responsible for active recruitment. When the current environment lacks
  a needed skill, custom agent, MCP, CLI, script, or minimum court dependency,
  吏部 records the gap, evaluates candidates with the capability dimensions,
  proposes or performs recruitment under the active execution authority, and
  reports the appointment evidence before 尚书省 relies on it.
- 户部 verifies resource, dependency, budget, version, cap, and path capacity.
- 刑部 reviews safety, privacy, destructive actions, paid actions, installs,
  external writes, and rollback/test risk.
- 尚书省 issues the actual 差遣 under an approved decree and integrates results.
- 史馆 is not a seventh ministry under 尚书省. By standing rule it is 三省共监、
  门下主审: 中书省 supplies drafts and decree material, 尚书省 supplies execution
  evidence, and 门下省 performs primary review of records and memory decisions.
- 太子 must report to the user before creating or permanently installing a new
  standing official/agent, writing durable memory, or changing the court's
  standing registry rules.
- Subagente profile contract: when a standing profile or spawned subagente is
  used, 尚书省/上级 office must cite `profile_source`, `profile_hash`,
  `direct_superior`, allowed actions, forbidden actions, evidence contract,
  heartbeat contract, release policy, and the active dispatch channel. A
  subagente without a profile hash or evidence contract is not fully registered
  for successful court work.
- Registry entries are metadata-first under the token three-level optimization
  policy. A capability record should carry precise source/path/version/hash,
  office fit, permissions, risks, dependencies, and evidence handles; it should
  not inline entire skill bodies, raw logs, or full external docs. Load the full
  source only after the registry metadata is insufficient for the current
  dispatch, risk review, or validation.
- Capability invocation is index-first. Do not wait for the user to explicitly
  name the local skill, agente, or MCP when the task already implies a suitable
  capability. Also do not invoke every matching item. 吏部/户部 first use the
  refreshed catalog and active index gate to choose the smallest suitable
  skill/agent/MCP/CLI/script set; 尚书省 then dispatches or calls only the selected
  capability under the active authority and evidence contract.
- Codex plugin registry entries use `kind=plugin`; skills embedded under an
  enabled plugin remain separate `kind=skill`, `source=codex_plugin` records.
  Disabled plugins/MCPs stay visible for drift review but are never dispatchable.
  MCP discovery parses only direct children of top-level `[mcp_servers.NAME]`
  (or legacy `[mcp.NAME]`) tables; nested `.env` tables are metadata of that
  server and must never become invented MCP identities.
- The bounded C2 recruitment output is intentionally narrower than the legacy
  broad catalog: only `skill|plugin|mcp` kinds and
  `local_skill|codex_plugin|local_plugin|local_mcp` sources are serialized.
  Semantic-equivalent duplicates collapse; conflicting local metadata becomes
  one `LOCAL_METADATA_CONFLICT` fail-closed record rather than a trusted winner.
- Registry collection is deterministic and local-first: tests and offline audits
  receive explicit roots/inventories, perform zero network and zero writes, sort
  records by stable identity fields, omit generation timestamps from records,
  and expose source-relative public paths rather than host-private absolute paths.
- 吏部 may propose recruitment from local evidence; public metadata discovery is
  allowed only when explicitly permitted by the injected authority. Any
  create/install/write action returns `next_action=ASK_USER` as a structured request/report to 尚书省 under the
  active authority; 吏部 never performs direct mutation or forwards secrets,
  account data, API configuration, or active-copy details. Missing authority,
  failed discovery, identity conflicts, and unverifiable roots remain explicit
  `authority_blocked` / `runtime_degraded`, never silently dispatchable.

## Capability Verification Index Skill Gate

For capability verification, recruitment, skill repair, and registry-drift review,
load `references/sections/court-capability-verification-index.md`. The gate makes
`refresh_capability_registry.py`, `find-skills`, system `skill-creator`,
`quick_validate.py`, and `check_catalog.py --strict` part of the active index
layer instead of treating them as passive prerequisites. Use
`scripts/check_capability_index_gate.py --query <need>` to surface matching
skills, agents, MCPs, CLIs, and scripts before dispatch. Report
`capability_index_skill_gate=PASSED | PARTIAL | FAILED | authority_blocked |
runtime_degraded` before claiming that a missing, new, repaired, or stale
capability is dispatchable.

## Registry-First Routing And Maintenance

`registered_capability_first_gate` requires 吏部 to consult the injected
`installed-capabilities-manifest.json` before discovery. The pure
`route_registry_first(query, current_tool, manifest, manifest_state,
source_roots, bounded_discovery)` surface selects at most one verified,
non-stale, sufficient, current-tool-compatible record. Its result preserves
`owner=libu-hr`, the injected registry path, `selection_source`,
`fallback_reason`, verification/hash/version evidence, and `dispatchable`.
It never writes a second registry or starts a daemon.

Bounded discovery runs exactly once only for `missing`, `stale`, `corrupt`, or
`no_sufficient_match`. A sufficient registry hit does not invoke discovery.
Discovery is local/offline in this A02 lane and cannot install, upgrade, mutate
a capability, or write a replacement registry.

`libu_hr_capability_registry_maintenance_gate` is event-driven and maps events
to these refresh boundaries:

| Event | Refresh boundary |
| --- | --- |
| `dispatch_failure` (dispatch failure), `phase_closeout` (phase closeout) | Light refresh of manifest/catalog and cheap local state. |
| `skill_install`, `skill_upgrade` | Incremental update of affected capability entries and department rows. |
| Single-source `hash_drift`, `version_drift` | Incremental verification/update of affected entries. |
| Missing/corrupt manifest, untrusted manifest state, or broad unknown drift | Full refresh of declared local roots. |

All maintenance remains local/offline, preserves the one canonical registry,
and never starts a registry daemon. Under read-only authority, compute and
report the due boundary but do not mutate: return `authority_blocked` plus a
`staleness warning` so callers cannot mistake the cached manifest for current
evidence.

## Catalog Refresh

Match the original selector's two-level catalog behavior:

- **Light refresh**: Run at 开朝 and before routing. Check whether known
  catalog files exist, whether their mtimes changed, whether active Codex MCPs
  are readable, and whether cheap CLI/version state changed. Then read the
  cached `Court Department Capability Map` and classify the current task's
  likely departments. If nothing changed, use the cached catalog. If skill,
  agent, MCP, CLI, or script roots, frontmatter, agent `.toml`, this skill's
  `agents/standing-officials`, or catalog files changed, run
   `python -B scripts/refresh_capability_registry.py` automatically as a standing
   开朝 duty; no separate user authorization is required for this local 官籍/catalog
   refresh. This light refresh inherits the narrow 开朝 boundary above: read local
   capability roots and rewrite only this skill's local 官籍/catalog artifacts; do
   not execute every skill, install/update capabilities, browse, expose secrets,
   mutate external state, or write outside this skill's local references.
   If the newest decree explicitly says read-only, no file edits, no catalog
   writes, or no audit writes, do not run the refresh writer; report
   `authority_blocked` and use live root scans or the cached manifest with a
   staleness warning.
  The light refresh is a gate with evidence: every first court turn must either
  run it, prove the cached manifest is current, or report why it is
  `authority_blocked`/`runtime_degraded`. Skipping it because the user asked an
  apparently narrow question, supplied a raw command, pasted a skill body, or
  omitted the word `/court` is semantic drift. If drift is discovered later in
  the same conversation, perform the catch-up refresh immediately under the
  active authority, record the correction, and cite the corrected registry
  state in the next 太子回奏.
- **Skill recruitment refresh**: After any new skill is installed or copied into
  `%CODEX_HOME%\skills` or `%USERPROFILE%\.agents\skills`, 户部/吏部 must run
  `python -B scripts/refresh_capability_registry.py`. The script reads local
  `SKILL.md` frontmatter and agent files, assigns likely 三省六部 fits, and
  rewrites the local 官籍 catalogs. A new skill is not considered fully available
  to 尚书省 dispatch until this refresh or an equivalent manual registration
  has completed.
- **Incremental update**: If one known source changed, update only the affected
  catalog entries and the department map rows impacted by that source.
- **Full refresh**: Run only when the user asks for a full capability refresh
  (including legacy `/catalog full` wording), the catalog is missing/corrupt,
  the manifest cannot be trusted, or light refresh discovers broad unknown
  changes. Re-scan skills, MCPs, relevant CLI tools, custom agents, worker
  agents, and regenerate the 官籍/department view.

Never run every skill just to test it. Smoke-test skills by reading frontmatter
unless the user explicitly asks for real execution.
