# Court Office Selective Loading Pure-Skill Remediation Plan

```text
PLAN_CODE: CCR-R2-SHIR-20260714-A02-OFFICE-LOAD-SKILL
STATUS: APPROVED_INSERTED_INTO_A02
IMPLEMENTATION_BASELINE: PURE_SKILL_REQUIRED
MINIMAL_OFFICE_LOADING_CONTRACT: REQUIRED
PLUGIN_DECISION: REJECTED_BY_NEWEST_USER_DECREE
REMOTE_PUBLICATION: NOT_RUN
GIT_INDEX: ALWAYS_EMPTY
```

## 1. Goal

Reduce routine sub-office preload cost without weakening the 三省六部 hierarchy, newest-decree authority, direct-superior chain, evidence/stop gates, shared-Shiguan boundary, or cross-tool portability.

The portable `.agents` court skill remains the only semantic authority, implementation baseline, and shared Shiguan owner. This remediation does not create, package, install, test, or reserve a Codex plugin path. Any future reconsideration requires a newer explicit user decree and a separate plan; it is not an A02 acceptance dependency.

## 2. Current measured problem

The read-only audit measured one routine Zhongshu preload as:

```text
SKILL.md                 61,479 bytes
zhongshu/AGENTS.md        9,888 bytes
zhongshu.toml             5,623 bytes
baseline total           76,990 bytes
```

This excludes the current task packet and any governing references. Loading all 14 profiles/dossiers is larger still. The optimization must therefore come from progressive loading inside the pure Skill contract, not from changing the distribution format.

## 3. Required core loading contract

Routine office start loads only:

1. the complete, deliberately compact root `SKILL.md`, containing only the common hard gates and progressive-loading map: newest decree precedence, authority/topology, legal court flow, hierarchy/no-bypass, shared Shiguan/current-tool boundary, evidence/stop/closeout gates;
2. the complete, deliberately compact current office dossier and profile, with path/hash acknowledgement;
3. direct adjacency only: direct superior, allowed direct children, upward report and downward dispatch edges relevant to that role;
4. the current bounded task packet, budget lease, worktree/write-set and evidence contract;
5. the selected capability-registry entry or bounded fallback result;
6. only the governing reference(s) triggered by the current behavior.

The compact common gates include the normal whole-tree limit of 16 (root included). A newest explicit user `count>16` or `unlimited/解限` switch may raise only the ceiling; stale/implicit sources fail closed, and budget, resource-pressure, hierarchy, write-set, preload, and trace gates remain mandatory without auto-fill.

Routine preload must not load all 14 offices, all governing references, unrelated history, full Shiguan bodies, pending bodies, or other tools' profiles.

Expanded loading is mandatory only when the role needs it:

- Menxia: privacy, safety, cost, scope, semantic drift, SPEC/QUALITY and closeout review.
- Shangshu: cross-lane dependency integration, shared writes, install/config/daemon/package sequencing.
- Zhongshu: cross-domain planning or research needed to draft the decree.
- Ministries/workers: only their own mandate, direct chain, task packet and relevant capability/reference.
- Extended governing references/role annexes: behavior edits, semantic disputes, audits, releases, long-context final reload, or explicit escalation. The compact root `SKILL.md` itself is always read in full when this skill is selected.

Missing common hard gates, role identity, direct chain, task/budget/write-set, evidence/stop fields, or required hashes blocks `running`.

## 4. TDD and implementation order

### RED

- routine child does not read the complete compact root `SKILL.md`, or the root `SKILL.md` still embeds extended references/all-office detail that belongs behind progressive loading;
- a ministry loads another ministry's dossier/profile by default;
- a worker omits its owning ministry or claims `direct_superior=shangshu`;
- an office starts without common hard gates, exact dossier/profile/SKILL authority hash, task packet, budget lease, worktree/write-set, evidence or stop contract;
- all references or all offices are eagerly loaded;
- a required risk/behavior trigger fails to load its governing reference;
- reported preload bytes/paths do not match actual loaded files;
- routine operation depends on a plugin, plugin cache, plugin-only manifest, or plugin-only MCP/UI path.
- a seventeenth normal thread starts without a newest explicit count/unlock, an old or implicit override is accepted, or unlock bypasses budget/resource/hierarchy/write-set/trace gates.

### GREEN

- extend the existing preload manifest/ack and bootstrap/dispatch contracts; do not add a database or daemon;
- compact the root `SKILL.md` into the single common hard-gate/progressive-loading shard and resolve one role-local adjacency manifest from the authoritative dossier/profile sources;
- persist only normalized relative paths, hashes, byte counts, load reason and escalation reason;
- record `loaded_paths`, `loaded_bytes`, governing-reference count, preload ack latency and first-report latency;
- keep current task content bounded and private-body-free;
- preserve exact-role dossier loading and the hierarchy `Taizi -> Three Departments`, `Shangshu -> ministries`, `ministry -> workers`.
- resolve one canonical parallel ceiling: normal default 16, newest explicit count/unlock override only, with no automatic maximum launch.

### SPEC / QUALITY

- representative routine office preload target for complete compact root `SKILL.md` + complete compact role dossier/profile + adjacency/registry metadata: `<= 20 KiB` before the task packet and at least `70%` below the 76,990-byte Zhongshu baseline;
- exact provider/session input tokens are reported only when available; otherwise use bytes/chars and label token estimates;
- escalation fixtures must load 100% of required governing references and never silently remain on the compact path;
- compare p50/p95 `dispatch_requested_at -> preload_ack_at -> first_office_report_at`;
- test wrong-role, stale-hash, omitted-gate, over-eager-load, under-load, duplicate projection and correction/resume cases;
- run existing profile, dispatch, preload, registry, runtime and package privacy checks.

## 5. Pure-Skill decision boundary

- The installed/shared `.agents` Skill and its portable current-tool projection are the complete runtime surface.
- The minimal office loading contract is implemented by compacting the fully read root `SKILL.md`, compacting each fully read role-local dossier/profile, and resolving only adjacency-local, task-local, and behavior-triggered extended references.
- No plugin manifest, plugin cache, plugin adapter skill, marketplace metadata, plugin-only MCP server, or plugin-specific fallback is created in A02.
- The absence of a plugin is a passing result, not deferred work and not a release defect.
- A newer explicit user decree is required before plugin feasibility can re-enter planning; that future work must remain separate from this plan and cannot retroactively block A02.

## 6. Files and integration ownership

Expected core surfaces:

- `SKILL.md` and the unique governing preload reference;
- `agents/standing-officials/*.toml` and `agents/supercc-dossiers/*/AGENTS.md`;
- `scripts/court_office_bootstrap.py`, `court_multi_agent_protocol.py`, `court_dispatch_policy.py` and their existing checkers;
- capability-registry and catalog checks;
- README/docs/logs/release manifest only after behavior is accepted.

Reuse the existing A02 B/E/K profile/dispatch/preload work during integration. Do not start a second competing implementation on overlapping files, and do not create plugin adapter files.

## 7. Gates

```text
office_minimal_preload_gate
office_role_local_load_gate
office_direct_adjacency_gate
office_on_demand_reference_gate
office_preload_measurement_gate
office_escalation_full_load_gate
pure_skill_runtime_baseline_gate
no_plugin_dependency_or_artifact_gate
```

These selective-loading gates are part of A02 Phase 1/4 and final acceptance. They do not weaken the migration-first order. Passing acceptance requires the pure-Skill path to remain complete and plugin-independent.
