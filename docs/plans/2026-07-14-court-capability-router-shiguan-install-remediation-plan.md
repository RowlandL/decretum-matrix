# Court Capability Router Shiguan Path Remediation Implementation Plan

> **For agentic workers:** Use the host-selected execution workflow when a later decree authorizes execution. Keep Shiguan migration/cutover and other shared mutations serialized; parallelize independent checks, reviews, and disjoint execution work with explicit file ownership.

**Goal:** Move the one authoritative Shiguan data root from `%LOCALAPPDATA%` to `%USERPROFILE%\.agents`, wait for conversations that still occupy records, register the migrated tree as the default Obsidian vault, change installation to `.agents + current agent tool only`, apply office name/profile/TOML/skill binding semantics to every office, then rebuild and install the corrected `beta0.5.13` release.

**Execution status:** `APPROVED_EXECUTION_ACTIVE`. The user confirmed `CCR-R2-SHIR-20260714-A02` and approved proposals A-D. Execute from RED in the stated order; confirmation does not waive pending-body or other hard stops.

**Main thread:** `019f5e95-4852-7f31-98ef-1d0c70d5e1e4` is the unique Taizi/integration lane for this plan. Other A02 lanes provide bounded evidence or diffs only and do not supersede this plan or commit integration decisions independently.

**Memory/Git plan revision:** `V2_SHIGUAN_ADJUDICATION_GIT_FEDERATION_20260715`. This revision supersedes earlier wording that treated every tool as if it had the same native memory-judgment capability.

**Office-loading subplan:** `docs/plans/2026-07-15-court-office-selective-loading-remediation-plan.md`. Its newest controlling decision is `PURE_SKILL_REQUIRED`: retain the minimal office loading contract and do not implement or reserve a plugin path.

**Architecture:** `.agents` owns shared writable Shiguan data. Tool-specific skill roots contain portable skill files only. The old `%LOCALAPPDATA%` location becomes a compatibility junction after verified migration. After cutover, the authoritative Shiguan `references` root is one local Git management hub: formal records and shared long-term memory are co-hosted but separated by directory, schema, lifecycle, privacy gate, and commit policy. Shiguan performs candidate normalization, evidence/conflict analysis, and application verification; Menxia makes the semantic memory verdict. Every runtime-verified installed tool keeps its native memory at the effective loader path and exposes it through an independent Git repository linked to the hub by registry plus paired receipts. Native tools remain responsible for their own storage/recall format, while adapter-specific writeback applies only an approved decision. Installation remains `.agents + current tool`; Obsidian renders one isolated metadata/index namespace and graph per `codex|hermes|claude-code|other:<stable-id>`.

**Tech Stack:** Python 3 standard library, PowerShell, JSON/TOML, SHA-256, Windows junctions, existing Obsidian CAS helpers, deterministic ZIP packaging.

Managed-repository topology:

```text
shared Shiguan Git (management hub)
  memory-store registry + tool namespace + shared commit receipt
                 <== same transaction_id ==>
native tool memory Git at its original path (one independent repo per tool)
  canonical pinned link + native commit receipt + tool-owned memory
```

The shared repository links and governs the native repositories through registry and paired commit receipts; it does not absorb them as submodules, subtrees, linked worktrees, nested tracked repos, or copied bodies.

---

## 0. Boundary and current state

The drafting/review confirmation gate has passed. Execution is authorized only inside this plan and the consolidated execution book. Keep migration/cutover, Obsidian, installation, packaging, and other shared mutations serialized. Root and child indexes stay clean before/after every gate; Court project commits are authorized only by the Section 2.2 major-stage bounded transaction on the corresponding child `release/beta0.5.x` worktree. Task 4 host-data Git checkpoints are scoped runtime operations, not publication. The root never carries product commits or uploads. Child remote/push/tag/PR/release actions remain denied unless Section 2.3 authorizes exact actions for the immediately previous completed version.

Current audited state:

```text
repository worktree: .
accepted installed version: beta0.5.12
version being corrected: beta0.5.13
old authoritative Shiguan: %LOCALAPPDATA%\court-shiguan\court-capability-router\references
new authoritative Shiguan: %USERPROFILE%\.agents\court-shiguan\court-capability-router\references
rejected beta0.5.13 SHA256: 8F9A4C3DCD3966B47962638C2181AA8D650E3D1A9AF930B0AED1997E77683321
metadata-only pending preflight: 69 real bodies / 1129975 bytes / 69 unknown metadata
```

Hard boundaries:

- Shiguan migration is the first operational change. Installation and packaging remain blocked until migration and Obsidian verification pass.
- Preserve the four cross-conversation files already present under `%USERPROFILE%\.agents\skills\court-capability-router\references` at their current relative paths, lengths, and hashes. Do not move, overwrite, or classify them as migration input.
- Real pending-import bodies remain unopened, unread, unhashed, uncopied, unmoved, undeleted, and unmarked-seen. Migration cutover is blocked while the metadata-only pending count is nonzero; do not create a new capability or split store to bypass this rule.
- Preserve accepted `beta0.5.12` artifacts and rejected `beta0.5.13\run1` and `run2` artifacts.
- Keep the root control and current Court child release indexes empty. Shared-Shiguan and native-memory Git commits are allowed only by the Task 4 scoped checkpoint contract. Court project commits occur only in the Section 2.2 major-stage window on the applicable `release/beta0.5.x` child worktree; staging is limited to approved pathspecs and every gate begins/ends with an empty index. No root product commit/upload is authorized; child remote actions require the separate Section 2.3 previous-version receipt.
- No network or remote publication runs now. The only later conditional path is Section 2.3, which cannot pass while the Court child remote is absent.
- On an existing host, no Obsidian memory projection runs before the verified Shiguan migration. Projection eligibility comes only from the bounded install projection/manifest and requires proof that the tool class actually has this court skill installed; full-host tool or memory scanning is forbidden.
- The install projection/manifest is a generated audit receipt, not a static list. Its proof order is current runtime process/CLI, relevant environment/tool home, CC Switch selected profile/target block/path override, actual effective config and loader precedence, resolved skill root plus `SKILL.md` version/hash, then an available runtime probe. A DB row, directory, environment variable, or file existence alone never proves installation.
- The only accepted installation states are `active_verified`, `installed_verified`, `detected_unverified`, `not_installed_verified`, and `unknown`. Every `active_verified|installed_verified` tool receives its own memory namespace/graph even when the native memory store is empty or disabled; the namespace records an accurate state rather than fabricated content. `detected_unverified|unknown` remain probe-only and cannot authorize projection, enablement, or writeback.
- `codex`, `claude-code`, and `hermes` are examples, not a closed list. Every other verified tool receives a stable `other:<stable-id>` and the same adapter contract. Its native memory directory remains at the effective loader/controller path; no tool memory store is moved, merged, normalized into a shared format, or copied into Shiguan.
- Every `active_verified|installed_verified` native memory store must be a separate Git repository managed in place by Shiguan. Reuse an existing owning repository and scoped pathspec; otherwise initialize at the native root only after compatibility proof, or use a separate git-dir with the native root as work tree when an in-place `.git` is incompatible. Shiguan-created repositories have no remote; an existing tool-owned remote is preserved but Shiguan may not add, change, fetch, or push it. Native repositories and separate git-dir/object history are never submodules, subtrees, or nested tracked content of the shared Shiguan repository and never enter Obsidian projections or release packages.
- The shared Shiguan Git repository is the management hub. Its registry stores only `memory_store_id`, tool class, native/repo/git-dir path identities, pathspec, loader/controller evidence, branch/HEAD, state, write policy, shared/native commit ids, one `transaction_id`, and paired-link receipts. The native repo's managed block points back to the shared repo id/namespace/commit. It never copies a full native memory body. Stage only approved managed-link/current-tool update-note paths; preserve unrelated dirty files and require clean indexes after each managed checkpoint.
- After migration, initialize/adopt Git only inside the one authoritative `.agents` Shiguan root. The repository is local-only by default, has no remote, and is a version-control layer rather than another data store or behavior authority. It tracks only allowlisted, privacy-reviewed formal records, memory decisions/shared approved memory, per-tool projections, manifests, and Obsidian derived views.
- Git must ignore runtime state, agente logs, `shiguan-imports/pending/**`, SQLite, raw transcripts, private evidence/bodies, Obsidian API keys/config, actual host/controller configuration and backups, credentials, and release packages. Committed records are never amended/rebased/rewritten; corrections append a `supersedes` record. Memory updates retain `derived_from_record`, `evidence_refs`, source/tool commit, and decision status.
- A shared lock and one integration writer serialize Shiguan Git commits. Commit only meaningful checkpoints, closeouts, or memory decisions, never heartbeat/log churn. Every commit receipt records parent/commit id and tracked paths, and the repository index is clean before and after handoff.
- Projection/probe paths treat native MEMORY/memories files as tool-authoritative. Outside the pinned managed-link block, tool-native writes, and a separately authorized current-tool update-note, Shiguan does not rewrite memory bodies. Default artifacts contain only relative source id/path, repository HEAD/hash or stable fingerprint, feature state, headings/topics/relations; they exclude private raw bodies and release packages. Body mirroring remains sealed until a later explicit decree and Menxia privacy review.
- On a blank host, before shared-root creation, any Shiguan/native-memory Git initialization, memory enablement, or install write, run a read-only memory-feature/Git-compatibility probe for every manifest-detected/selected tool and show `enabled|disabled|unavailable|unknown`, native path/repository evidence, and a user-facing choice prompt. The probe changes nothing; `unknown` fails closed for automatic enablement. Verified Claude/Hermes/other may receive only the newly authorized in-place Git stewardship and pinned managed-link block; all other mutation still needs separate newest explicit authorization.
- Blank-host standard-config assessment is advisory until the newest user instruction explicitly authorizes configuration change for the normalized target `codex|claude-code|hermes|other:<stable-id>`. Probe the effective source of truth/controller first. An unmet requirement, missing authority, or uncertain ownership/precedence/compatibility emits `REMINDER_ONLY`, does not stop unrelated work, changes nothing, and must not be reported as compliance.
- Root workspace governance was later explicitly activated as a temporary A02 resume gate. `D:\project` is now the local Git control repository and single new Codex project entry, but it tracks only the control plane and selected evidence metadata. Child repositories, real artifact/recovery bodies, live host config, runtime state, and child worktrees remain untracked and autonomous. Real child worktrees use the project-scoped `D:\project\worktrees` root and connect only to their child common-dir; Codex global worktree settings stay unchanged. The latest explicit worktree-handoff decree supersedes the earlier no-move hold only for active A/B/G: before further Phase 1 writes, relocate those three linked child worktrees through the root controller, preserving every lane's approved unstaged diff exactly; same-volume relocation uses Git's native move, while this host's `C:` to `D:` transfer uses a traced directory move followed immediately by `git worktree repair` and fingerprint verification. Attach replacement visible task shells under the single root project and append path-transition Shiguan evidence. If publication is later authorized, publish only each GitHub-ready child repository, never the root control repository. This run creates no remote, push, or publication.
- Every Git worktree created, adopted, maintained, or used by the court needs its own Shiguan record in addition to child-office lifecycle summaries; this run covers every A02 worktree. The record is metadata-first and binds a stable `worktree_trace_id`, repo/common-dir/worktree identity, base/HEAD/branch state, lane/owner/direct superior, approved write set, index/pyc and validation evidence, recovery anchor, and final integration/retention/retirement/block disposition. Reuse the existing append-only checkpoint/archive path; do not add a database or copy full prompts, diffs, source bodies, private logs, or pending bodies.
- The active A/B/G handoff has passed: all three code worktrees now live under `D:\project\worktrees\court-capability-router`, use `work/a02-lane-a|b|g`, attach to three visible `D:\project` root-task shells, and retain exact approved diffs. A was verified 4/4 against its trusted source after cross-volume repair; B was replayed only from its original successful session tool calls and matched all four old final hashes; G is byte-equivalent to the sealed `visible-lane-g-9455.patch` at SHA-256 `4585F1675893C3FF9F1D56AFBB616D28EC588850D7784708AB84DD49003C9A3A`. Three new append-only Shiguan records supersede the old path traces; indexes remain empty and pending-body access was not run.
- After handoff, A and B passed their focused GREEN/SPEC/QUALITY and were absorbed into the integration tree at exact 4/4 file hashes. G added one accepted active-lease/requested-bindings capacity fixture; only that checker hunk was absorbed for Phase 1. Its remaining ledger/runtime/concurrency delta is sealed for Phase 1.5 after Phase 1 cluster acceptance. Integration and lane indexes remain empty, diff-check/no-pyc pass, and pending-body access remains not run.
- Routine office loading remains a pure-Skill capability. Do not create, package, install, test, or reserve a Codex plugin, plugin-only manifest/cache/MCP/UI path, or second semantic entrypoint. Plugin absence is an accepted end state, not deferred work.
- A Shiguan task-point capsule is evidence and bounded dispatch recall, never standalone authority. Pure pointers cannot start a child. Real capsules are forbidden until the shared-root migration and Obsidian/shared-root topology gates pass; Phase 1 uses temporary fixtures only. Reuse the existing runtime/admission/archive path and add no database, daemon, second store, plugin, or second state machine.

Protected-file baseline relative to `.agents/skills/court-capability-router`:

| Relative path | Length | SHA-256 |
|---|---:|---|
| `references/shiguan-index.jsonl` | 0 | `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855` |
| `references/shiguan-knowledge-graph.json` | 338 | `2F0454EEC5355FB502624FB3658C477386DA668920836FD0E33FF9AD47EC4922` |
| `references/shiguan-tree/_index.md` | 268 | `CE5671B2DA87093F9B0D6A17D030BE39C5A0632DB98CFF6D3A0671A671FB4169` |
| `references/shiguan-tree/capability-index/_index.md` | 517 | `01BC65DF443E52103FC08B86DE8F5250B8630E13DDE4B3B6C5B5DC7ED09AEF7A` |

### 0.1 Controlling execution addendum: `CCR-R2-SHIR-20260714-A02`

The newest user corrections below are part of this insertion and override any conflicting older plan detail:

- The end state is **one shared Shiguan**, not merely several portable-looking paths. The only physical writable store is `.agents\court-shiguan\court-capability-router\references`; tool-specific skill copies contain code only. The old LocalAppData path is a compatibility junction to the same physical store, never a second store.
- Persisted portable paths are skill-root/user-root relative. Ordinary carriers store `agents/standing-officials/<role>.toml`, `agents/office-dossiers/<role>/AGENTS.md`, and `.agents/court-shiguan/...`; only an explicitly active superCC receipt may name `agents/supercc-dossiers/<role>/AGENTS.md`. An absolute path may be used transiently to open/verify a file but must not be persisted in a dossier, runtime binding, manifest, or package.
- Keep the solution minimal: one shared-root resolver, one migration gate/cutover path, one current-tool install projection, and one all-office loading/binding gate. Do not add another service, database, generalized installer framework, or parallel state machine.
- Apply `complexity_budget_gate`. The newest explicit user complexity boundary controls; when unspecified, 太子 decides from 中书 value, 门下 risk, 尚书 budget/dispatch, verification, and rollback evidence. Necessary complexity may be approved; low-value polishing may be rejected or deferred.
- This is a loading/dispatch correction, not a rewrite of the underlying court constitution. Initial skill load must pin the sufficient semantics already governed by the skill: newest decree, authority/topology, legal court flow, real office duties, agent admission, shared Shiguan/install boundaries, and closeout gates.
- After court load, skill routing is registry-first: consult the existing `references/court-capability-registry.md` and prefer a verified, current-tool-compatible, non-stale entry over a full filesystem scan. Only `missing`, `stale`, `corrupt`, or `no_sufficient_match` may trigger bounded supplementary discovery. 吏部 owns event-driven refresh/verification of this existing roster; do not create a second registry or an unbounded background scanner.
- Every amended behavior in this plan must be durable in project `SKILL.md`, a directly linked governing reference, and the corresponding production/test contract. Host `MEMORY.md`, temporary thread memory, Shiguan candidates, update notes, or old conversations are recall/evidence pointers only and never prove behavior implementation.
- Office responsibility remains one-to-one: 太子 receives/synthesizes; 中书省 drafts/decomposes; 门下省 reviews/audits/rejects; 尚书省 sequences, dispatches, and integrates; 六部 primarily execute approved specialist work; 工坊/工匠 are the final hands-on execution layer; 史馆 records evidence under 三省共监、门下主审. The direct chain is mandatory: 尚书省 is the superior of 六部, and each 六部 is the superior of its own workers/craftsmen. Do not bypass a ministry by assigning its craftsman directly from 太子 or another Three-Department office.
- A child office identity is established by loading its exact dossier, not by prompt paraphrase. Every ordinary spawn carries the explicit `role_key`, relative `agents/office-dossiers/<role>/AGENTS.md` path and SHA-256, standing profile path/hash, court `SKILL.md` path/hash, and preload contract. The child must read that `AGENTS.md` and acknowledge matching hashes before `running`; a task name or parent-supplied semantic summary alone is never sufficient. `agents/supercc-dossiers` is valid only after the newest explicit superCC selection.
- After interruption, permission change, or user correction, bind the message to the existing goal/task as `TASK_CONTINUATION` or `TASK_CORRECTION`, inspect residual commands/index state, rebuild the newest charter, return through 三省复议, and only then resume 尚书 execution. Do not create a second task for the same decree.
- The same continuation/correction path must pass the Section 0.4 Semantic Continuity Guard. `semantic_epoch` equals charter revision; permission, plan cursor, Git/worktree, recovery, and memory evidence keep separate revisions/fingerprints. Stale child results are quarantined rather than silently applied.
- Subagents are not audit-only. After 三省 petition and 太子 reply, 六部/工匠 perform real implementation and verification. Independent, disjoint files may be edited in parallel; shared files, migration cutover, Obsidian mutation, installation, and packaging remain single-writer operations.
- Proposal A is active: each office keeps one canonical authority while bounded same-role worker instances may scale by independent shard. Six-ministry affinity is highest, Three-Departments affinity lower, Shangshu scale-out extremely low and only after `super_giant_task_gate`; Taizi remains unique.
- Super-giant examples include complete small/medium/large game development and design, independent batch work above roughly 10 items, or complex concurrent information collection/judgment above roughly 30 independent units. Reassess each wave; downgrade when remaining work no longer meets scale or host retention/performance is insufficient, including memory pressure near 99%.
- Proposal B is active under its gates: Shiguan proactively maintains current-tool memory candidates and Codex update-note writeback only after newest explicit memory authorization and Menxia approval; it never directly rewrites `MEMORY.md` or writes unrequested tools beyond the explicitly required pinned managed-link block. Formal records, memory candidates/decisions, shared approved memory, per-tool projections and the Obsidian tree share one local Git repository after migration, but records remain append-only evidence while memory remains explicitly curated current knowledge. Every verified tool's native memory remains in its own original-path Git repository and is federated through Shiguan repo/HEAD/pathspec receipts rather than migrated, nested, or copied. Obsidian receives metadata/index projections for every runtime/controller-verified `active_verified|installed_verified` tool class (`codex`, `hermes`, `claude-code`, stable `other:<id>`), one isolated namespace/graph per class with no cross-tool node/edge conflation; empty/disabled memories still receive an accurate empty-state namespace and Git repository receipt. Body mirroring remains separately gated.
- Blank-host config correction runs only after migration/no-source proof and current-tool/target resolution. Probe source-of-truth/controller ownership first. When CC Switch is present and its target tool block is proven, prefer its reversible upstream transaction/backup; for Codex, update the corresponding proven DB/config block and then apply one semantically equivalent/compatible delta to both effective `config.toml` and `managed_config.toml`. Without CC Switch, use the same controlled reversible dual-file Codex path. Parse and merge structurally, preserve secrets, provider fields, and unknown keys, and never use blind byte replacement. Final acceptance is actual effective-file reread/parse plus a runtime probe when available, never DB state alone. A failed Hermes CC Switch attempt is preserved as evidence and may fall back to the reversible actual-file path only under newest explicit config-change authority and certain semantics. If DB schema, field ownership, effective precedence, current values, or compatibility is uncertain, change nothing, report the exact uncertainty as non-blocking `REMINDER_ONLY`, and continue unaffected work.
- Reuse the existing recovery evidence at `%LOCALAPPDATA%\court-shiguan\court-capability-router\references\recovery\ccswitch-codex-deep-reset.md` and `%LOCALAPPDATA%\court-shiguan\court-capability-router\references\recovery\codex-ccswitch-recovery.md`; do not add a second config controller, database, or generalized framework.
- Apply the minimum office loading contract through the pure Skill: fully read one compact root `SKILL.md`, fully read the compact exact-role dossier/profile, then add direct adjacency, bounded task/budget/worktree packet, one verified registry result, and behavior-triggered governing references. Extended reference/role-annex loading is reserved for behavior edits, semantic disputes, audits, release/final reload, or explicit escalation; the selected root `SKILL.md` itself is always read completely.
- Normal parallel capacity defaults to 16 whole-tree threads including root. Only a newest explicit user count above 16 or newest explicit `unlimited/解限` switch may raise that ceiling; prior memory/task state and implicit host configuration fail closed. An override never supplies a Taizi lease, bypasses memory/resource/hierarchy/write-set/trace gates, or auto-fills capacity.

### 0.2 Verified CC Switch 3.16/3.17 and effective-config contract

- Accept only `CC Switch 3.16.x + SQLite user_version=11`, or `CC Switch 3.17.x + SQLite user_version=13` with exactly the six `profiles` columns `id/name/payload/sort_order/created_at/updated_at` and verified `input_token_semantics` for both `proxy_request_logs` and `usage_daily_rollups`. Version/schema mismatch or unknown evidence fails closed with no mutation or compliance claim.
- `settings.current_profile_id_<scope>` rows are demand-created; absence is not migration failure. CC Switch owns and runs its SQLite migrations; the adapter must never migrate or repair the controller schema. `tool_blocks` is synthetic JSON-fixture vocabulary only and must never be described as a real SQLite table or structure.
- Immediately before the final verdict, reread and parse every target actually configured in this run. Each Codex TOML independently satisfies the approved equivalent/compatible delta; permanent whole-file byte equality is not required. Earlier controller/DB receipts do not replace this last-moment semantic proof.
- Hermes v3.17 resolves the config directory as explicit CC Switch `hermes_config_dir` override > nonempty `HERMES_HOME` > platform default, then appends `config.yaml`: Windows `%LOCALAPPDATA%\hermes` with `<home>\AppData\Local\hermes` fallback, Darwin/Linux `~/.hermes`.
- The host's `features.multi_agent_v2.max_concurrent_threads_per_session` is not yet proven as `16`; keep it as the real unmet item and do not claim it fixed without later explicit configuration authority and a last-moment native reread.
- Proposal C is active: user-explicit complexity instructions outrank Taizi budget judgment.
- Proposal D is active: every child office/worker gets a compact append-only time-event-action trace with instance and evidence pointers; do not copy full prompts, reports, logs, or private bodies into Shiguan.
- TDD remains test-first, but RED/GREEN/SPEC/QUALITY review granularity is phase-level rather than one reviewer round per micro-point.
- On every context compression or resume, reload: `对任务进度与执行书进行对照再度继续按执行书且调用三省六部skill super并行执行`; compare progress to the execution book and continue the existing goal/task.

### 0.3 Controlling V2 memory-adjudication and Git-federation contract

No supported tool may be assumed to provide complete native adjudication merely because it can store, recall, auto-generate, or approve a memory write. Current official surfaces are heterogeneous:

| Tool class | Native surface used by the adapter | V2 conclusion |
|---|---|---|
| `codex` | Local generated memories, task-level use/generation controls, background extraction, evidence-bearing files | Auto-memory surface; no documented complete per-candidate conflict/supersede verdict API. Use the supported local memory/update-note path and verify later ingestion. |
| `claude-code` | `CLAUDE.md`, per-repository Auto Memory, `/memory` audit/edit | Auto-memory surface; native instruction conflict may remain nondeterministic. Never treat a stored note as a Menxia-approved verdict. |
| `hermes` | Persistent memory, background review, optional `write_approval`, pending/approve/reject | Native approval gate; map it as a second application gate, while Shiguan still owns evidence, deduplication, conflict, scope, and supersession. |
| `other:<stable-id>` | Runtime-probed adapter | Default `unknown`; no Git initialization, projection, enablement, or writeback until capability evidence is complete. |

Primary capability references: [Codex memories](https://developers.openai.com/codex/memories), [Claude Code memory](https://code.claude.com/docs/en/memory), and [Hermes persistent memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory).

Keep the existing compatibility decision field:

```text
memory_decision = WRITE | PROPOSE | SKIP | DEFERRED
```

Add orthogonal fields rather than replacing history or creating another authority:

Three control planes are independently evaluated and receipted:

1. `semantic_adjudication`: Shiguan performs evidence, privacy, deduplication, conflict, scope, and freshness analysis; Menxia alone returns `APPROVE|REJECT|DEFER|SUPERSEDE`.
2. `write_authority`: proves the newest user memory-write boundary and the authorized target tool. `approval|autonomous|super` controls execution/writeback permission, not semantic truth.
3. `native_application`: the tool adapter performs apply/pending, native reread, and paired Git receipts. A native queue verdict changes application status only.

```text
adjudication_status = candidate | review_required | approved | rejected | skipped | deferred | superseded
application_status = not_requested | apply_pending | applied_verified | apply_blocked | rolled_back
conflict_status = none | duplicate | compatible_update | contradiction | scope_collision | stale
resolution = keep | merge | replace | supersede | reject | defer
content_origin = user_decree | tool_native | shiguan_candidate
decision_id = stable append-only decision identity
menxia_receipt = signed aggregate adjudication receipt
transaction_id = linked shared/native application transaction
```

The legal flow is:

```text
tool/user/Shiguan candidate
  -> Shiguan evidence + privacy + duplicate/conflict/scope review
  -> Menxia APPROVE | REJECT | DEFER | SUPERSEDE
  -> tool adapter apply/pending queue
  -> native-store reread
  -> scoped native Git checkpoint
  -> shared Shiguan receipt checkpoint
  -> APPLIED_VERIFIED
```

`WRITE` is legal only with `adjudication_status=approved`. A Git commit, Obsidian projection, native pending approval, or the mere presence of a memory file never upgrades a candidate to approved. Historical records are not mutated; a later correction appends a superseding decision.

The agent-first surface is one JSON CLI/API family: `court memory scan`, `court memory adjudicate`, `court memory apply`, `court memory verify`, and `court memory reconcile`. Core policy is implemented as side-effect-free pure functions; adapters own I/O. The adjudication rubric covers source authority, evidence quality, stability, reuse value, temporariness, privacy, scope, freshness, `duplicate|compatible_update|contradiction|scope_collision|stale`, and `keep|merge|replace|supersede|reject|defer`.

Current-tool application requires newest explicit writeback authority plus an approved Menxia receipt. A non-current tool defaults to index/Git stewardship/pinned link; its memory body requires newest explicit target authorization. Corrections append a new decision with `supersedes`; no tidy/re-evaluation tool may rewrite a historical verdict in place.

Every install receipt also carries a native capability matrix:

```text
storage = read_write | read_only | none | unknown
auto_candidate = yes | no | unknown
approval = queue | inline | none | unknown
conflict_resolution = native | none | unknown
writeback = native_api | update_note | managed_file | none | unknown
git_mode = existing_owner_repo | in_place_repo | separate_git_dir | blocked | unknown
```

Content authority and repository authority are separate. A native tool may write its own memory body. Shiguan may checkpoint that tool-originated change after privacy/pathspec review without claiming authorship. Shiguan-authored content defaults to the current tool and requires Menxia approval plus the newest memory-write authority; a non-current tool requires newest explicit target authorization. The user's pinned-link decree is the sole standing cross-tool body exception.

The committed hub registry stores portable locators and fingerprints, never machine-private absolute paths. Runtime-resolved absolute bindings stay under ignored `court-runtime/` state. One linked transaction carries `memory_store_id`, `tool_class`, native repo/pathspec/HEAD, shared namespace/HEAD, `decision_id`, and `transaction_id`; the two commits are independently durable and must not be described as atomic. A partial transaction is reconciled or rolled back before another write to that store.

### 0.4 Semantic Continuity Guard contract (`PLANNED_RED`)

Keep existing `tasks.json` current-task state plus append-only `court_events.jsonl` as the sole runtime authority. Do not create another database, counter authority, state machine, or unbounded daemon. Shiguan/memory/Obsidian/Git/recovery are evidence and projections only.

- `semantic_epoch` is exactly `charter_revision`. Keep `authority_revision`, `plan_revision/plan_cursor`, `git_fingerprint`, and `recovery_checkpoint_id` separate so intent correction is not confused with permission, progress, worktree, or recovery drift.
- Persist a small invariant capsule containing newest-decree anchor, non-goals, boundaries, allowed/forbidden actions, acceptance/evidence/stop gates, write set, and governing-bundle canonical hashes.
- Bind dispatch/admission/start/report/finish to task, epoch, charter/capsule hashes, dispatch uid, attempt, office identity/hierarchy, worktree/write set/lease, and preload hashes. Reject unbound free-text results.
- Under the existing runtime lock/CAS, correction writes the next charter/epoch and invalidates prior assessment/checkpoint/completion/dispatch/admission/active agents/capsules/attempts, then returns the task to `ThreeDepartments`. Late stale results are quarantined and never silently rebased/applied.
- Checkpoint/verify before compaction when feasible and after compaction/resume/reboot/long idle. Run one drift detector before dispatch, apply, commit, and closeout. Mutation fails closed; only read-only diagnosis may return `runtime_degraded` from a verified current snapshot/capsule.
- States are `UNVERIFIED -> VERIFIED -> DISPATCHABLE` and `DRIFTED -> QUARANTINED -> CORRECTED -> REVERIFY`. The JSON receipt uses the field set in the execution book and is appended through the existing event/runtime/archive paths.
- Provide `court semantic checkpoint|verify|correct|resume|quarantine|reconcile` as agent-first JSON CLI/API backed by pure policy functions and existing I/O adapters. Use Python stdlib/pathlib/os.replace on Windows/macOS/Linux; target invariant capsule `<=2 KiB`, O(1) unchanged-input hash checks, and local verify p95 `<250 ms`.
- Phase 9 review consumes this verified receipt; V2 memory decisions cite the verified epoch as provenance. Neither may mutate or advance runtime state.

### 0.5 Controlling Shiguan CLI multi-conversation numbering and lineage contract (`PLANNED_RED`)

This contract resolves decree numbering and lineage across concurrent conversations, child agents, and worktree threads without adding another cluster, authority, ledger, database, or per-worktree runtime state.

- `tasks.json` current-task state plus append-only `court_events.jsonl` remain the sole runtime authority. A minimal `scripts/court_operation_journal.py` is allowed only as an idempotency/recovery receipt adapter. Its minimum binding is `operation_id`, `payload_sha256`, `expected_task_revision`, `decree_id/main_court_code`, `parent_court_code`, `child_no`, `lineage_key`, and `lineage_version`; it must not own task state, event history, a second sequence, or a second archive index.
- `court decree-open` allocates the main decree number exactly once and freezes `main_court_code/lineage_key/lineage_version`. Replay reuses the original operation/result. Only an explicit `reclassify` may advance the lineage version; historical `court_code` values are immutable and a carrier/worktree change never renumbers the decree.
- The generic lifecycle is `court office admit|start|report|finish|close`. Existing `agent-*` commands remain compatibility wrappers for `carrier_kind=child_agent`. A `worktree_thread` uses the same schema and adds only `thread_id`, `worktree_fingerprint`, `branch`, and `start_head` proof; it does not receive a private `tasks.json` or event stream.
- Closeout is a recoverable saga: `PREPARED` under the runtime lock and expected-revision CAS; `ARCHIVE_COMMITTED` under the Shiguan lock with one archive/index side effect; `TASK_EVENT_COMMITTED` under the runtime lock with the paired task/event receipt. `court closeout-recover --operation-id <id>` resumes from the last verified stage. Allocation, archive, index, task, and event crash points must replay exactly once.
- Keep the accepted repair-cluster map: RC2 owns generic semantic/operation interfaces, CAS, compound receipts, and closeout recovery; RC4 runs after RC2 and owns `office_instance` child/worktree lifecycle plus frozen lineage; RC6 owns local authority-realm/root fingerprint and root-mismatch fail-closed behavior. Existing same-root file locking and 32-process allocator uniqueness are positive regressions only and must not be reimplemented.
- Phase 1 implements RC2 core against temporary local roots before RC4 touches shared `court_runtime.py`. RC6 pure fingerprint fixtures may run in Phase 1, while the real authority-root binding and RC2 archive transaction wait for the existing pending/quiescence/migration gates and then run serially. The current `pending_count=69` blocks real Shiguan access/cutover, not Phase 1 core that uses no real archive or pending body.
- Concurrency numbers are whole-tree ceilings and include root: default `16` means 15 child slots, explicit `17` means 16, and explicit `18` means 17. Never reinterpret an explicit count as child slots.
- Acceptance includes the existing 32-process allocator regression, 32 concurrent replays of one operation producing one side effect, all five killpoint families, Windows/macOS/Linux local-filesystem fixtures, root mismatch fail closed, and two child plus two worktree lifecycle fixtures with isomorphic schemas. Context carries hashes, relative paths, and evidence pointers only.
- SQLite, HTTP services, message queues, distributed locks, cross-host coordination, NFS, and SMB are out of the first implementation. Return `DEFERRED|UNSUPPORTED` and fail closed. The CLI orchestrates existing Codex, Git, runtime, and Shiguan adapters; it never replaces them.
- Task 10/Phase 9 only verifies coverage and regression. Missing RC2/RC4/RC6 behavior must return to its original cluster for RED/GREEN/SPEC/QUALITY and may not be deferred for first implementation during the final audit.

### 0.6 Project-memory pointer and office task-name contract (`PLANNED_RED`)

- Current adjudication is `PROJECT_MEMORY_CONTENT=PASS` and `GLOBAL_MEMORY_INDEX=FAIL_PENDING_INGESTION`. `D:\project\docs\project-memory.md` is present and authoritative; the global failure is an uningested root-governance note plus stale current pointers, not migration loss. Preserve all historical MEMORY entries and supersede current pointers append-only.
- In the later authorized RC3/Task 9 root-memory step, one root writer creates a small ad-hoc superseding note containing the current D-drive common/integration/A-B-G paths, checkpoint, progress, and ingestion request; it minimally updates project-memory pause wording and verifies global ingestion. Do not directly overwrite global `MEMORY.md`, and do not treat the note as project implementation evidence.
- `task_name/collaboration address`, sidebar title, repo-control id, and office role are orthogonal. The first-spawn role-prefixed task name is immutable; followup may reuse only the same role. A generic or cross-role name cannot report `office_execution_ready`, while an obsolete suffix on the correct role is reusable and is not rebuilt for appearance.
- Readiness is proven only by `role`, `office_instance_id`, assignment, direct superior, ordinary dossier/profile/SKILL relative paths and hashes, and preload acknowledgement. Sidebar title is independent and never evidence.
- Reuse existing clusters: RC3 owns project-memory/global-pointer ingestion, RC4 owns carrier/name/readiness binding, and RC5 owns rollout identity debt. RC5 must align README, `court-office-name-profile-skill-binding.md`, and bootstrap `required_skill/loaded_skill` to `decretum-matrix` while preserving `court-capability-router` as a technical locator.

## 1. Fixed behavior after remediation

1. Required shared installation root:

   ```text
   %USERPROFILE%\.agents\skills\court-capability-router
   ```

2. Only writable Shiguan root:

   ```text
   %USERPROFILE%\.agents\court-shiguan\court-capability-router\references
   ```

3. Default Obsidian vault:

   ```text
   %USERPROFILE%\.agents\court-shiguan\court-capability-router\references\shiguan-tree
   ```

4. Default installation targets:

   ```text
   .agents + current agent tool
   ```

   The general and blank-host default remains `.agents + current tool`. The newest explicit final-host instruction adds one late exception after Task 10: install/upgrade the same accepted portable skill to the fixed five proven roots (`.agents`, `.codex`, `.claude`, `.hermes`, and `user_data_base()/hermes`) and require version plus allowlisted per-file hash equality. This does not authorize tool configuration, memory enablement/body writes, unknown-tool installation, or remote publication.

5. All office agents receive the same name/profile/TOML/skill-binding contract through every file under:

   ```text
   agents/standing-officials/*.toml
   agents/office-dossiers/*/AGENTS.md
   ```

   Explicit superCC additionally binds `agents/supercc-dossiers/*/AGENTS.md`; ordinary carriers must not load it.

6. Every accepted version iteration updates:

   ```text
   README.md
   CHANGELOG.md
   RELEASE-LOG.md
   docs/logs/README.md
   docs/logs/2026-07-14-shiguan-install-remediation.md
   release-manifest.json
   ```

   This is an executor self-maintenance duty: update README and Log before declaring the iteration complete, without waiting for another user reminder. `docs/logs` is a short sanitized maintenance log, not a copy of raw runtime logs or Shiguan bodies.

7. Initial court loading pins a compact sufficient semantic block near the top of `SKILL.md`. The block is validated in place; it references existing governing semantics and does not create a second constitutional source.

8. A newly created runtime task initializes `charter_revision`, `charter_sha256`, and the invariant capsule; `semantic_epoch == charter_revision`. Resume/correction updates the existing task under the same lock/CAS, invalidates assessment/checkpoint/completion plus every stale dispatch/admission/agent/capsule/attempt binding, quarantines late results, verifies the current receipt, and re-enters 三省 review before execution resumes.

9. After verified migration, the authoritative Shiguan root is one local Git repository. It co-hosts formal records and long-term memory layers with separate schemas/lifecycles: records append and may only be corrected by a later `supersedes` record; memory candidates/decisions/shared approved memory may evolve but preserve record and commit lineage. Tracking is allowlist-based and privacy-gated; runtime/pending/private/config/package paths remain untracked, and no remote is configured.

10. The tool set is open: `codex`, `claude-code`, and `hermes` are built-in examples and every additional tool receives a stable `other:<stable-id>`. Each verified native memory store stays at its loader-required path and is managed by Shiguan as an independent Git repository. Reuse an existing owner repo/pathspec or, after compatibility proof, initialize in place/use a separate git-dir with the original work tree. Never migrate it into Shiguan, copy its body into the shared repository, or add it as a submodule/subtree/nested tracked repo. New repos have no remote; existing tool-owned remotes remain unchanged and unused by Shiguan.

11. The shared Shiguan Git repository links every managed native memory Git repository through a registry entry keyed by stable `memory_store_id`. Each link carries native repo/pathspec/branch/HEAD, shared repo/namespace/HEAD, write policy, and the same `transaction_id` across paired commits. The native canonical entrypoint has exactly one versioned pinned block, immediately after any mandatory tool frontmatter/header and before ordinary content, linking back to the shared Shiguan home, tool namespace, and shared commit; the namespace links to the native path and commit. `CUTOVER_VERIFIED` is physical only; overall migration requires every eligible tool to pass `MIGRATION_LINKS_VERIFIED`. An exact per-tool `LINK_BINDING_BLOCKED` result prevents false success and blocks completion rather than satisfying the gate. Outside that block, non-current tools remain body-read-only.

12. Shiguan and Menxia provide the complete semantic adjudication layer using the V2 compatibility/status fields. Tool-native approval is an application gate, not the court verdict; Git is version evidence, not the verdict; Obsidian is a view, not the verdict.

13. Tool-originated body changes may be privacy-reviewed and checkpointed without Shiguan claiming authorship. Shiguan-authored memory defaults to the current tool and requires newest memory-write authority plus Menxia approval. A non-current body write requires newest explicit target authorization; Git stewardship and the managed pinned link do not authorize any other body mutation.

14. Memory projection eligibility is the install projection/manifest's runtime-derived proven installed-skill set, never a static list or host scan. Generate the receipt from runtime/CLI -> environment/tool home -> CC Switch -> effective config/loader -> skill root/version/hash -> runtime probe. Each `active_verified|installed_verified` canonical `tool_class` owns a separate Obsidian namespace and graph even when memory is empty; `detected_unverified|unknown` remain probe-only. Projection records contain relative source id/path, native repository HEAD, hash/fingerprint, decision/application state, headings/topics/relations only and exclude private raw bodies and release packages.

15. Blank-host setup begins with a no-write install/memory-feature/native-capability/Git-compatibility probe over runtime-selected tools. It reports the installation enum, the V2 capability matrix, native path/repository evidence, and a user-facing choice before creating the shared root, initializing any Shiguan/native-memory Git, enabling memory, or installing. `unknown` is never auto-enabled or initialized. This preflight does not change the default `.agents + current tool` install rule.

16. After migration/no-source proof and normalized target resolution, blank-host config handling probes the effective controller first. Noncompliance without newest explicit config-change authority, or any semantic uncertainty, returns non-blocking `REMINDER_ONLY` with `compliance_claimed=false`. Authorized Codex mutation is reversible and controller-aware, keeps `config.toml` and `managed_config.toml` semantically compatible while preserving unrelated/provider/secret/unknown fields, and is accepted only after actual-file reread/parse plus an available runtime probe.

17. Every participating worktree has its own metadata-first Shiguan record. Child lifecycle summaries and the optional workspace ledger may point to that record, but neither substitutes for its worktree identity, approved write set, verification chain, recovery anchor, and terminal disposition.

18. Routine child preload is role-local and on-demand through the pure Skill path. It fully reads the compact root `SKILL.md` and compact exact-role dossier/profile, while extended references/other roles remain trigger-based. Before the task packet this fixed loading surface targets `<=20 KiB` and at least 70% reduction from the measured 76,990-byte Zhongshu baseline, while still loading every triggered governing reference. It records actual paths, hashes, bytes, acknowledgement latency, and first-report latency; a plugin dependency or artifact fails acceptance.
19. Office carriers normalize to `child_agent|worktree_thread|supercc_cli_office`. Child-agent and worktree-thread carriers use an equivalent dispatch/communication/result receipt and exact-role preload; the worktree remains an isolation/visibility carrier, never a second office authority, and owns an independent Shiguan worktree record.
20. `superCC` is an experimental CLI-only carrier, not an authority class. The authority/topology selection must disclose that status and its zellij+squad dependency before use. Only the newest explicit `superCC` choice loads the superCC annex/profile/scripts/watchdog/daemon/visible-office semantics; ordinary `approval|autonomous|super` and ordinary parallel keep that entire surface unloaded.
21. The formal user-facing skill identity uses the Latin roots `Decretum Matrix（诏令矩阵）`; the canonical skill name/invocation is `decretum-matrix` / `$decretum-matrix`. For A02, `court-capability-router` remains only an allowlisted technical locator for the existing repository, install directories, Shiguan namespace, protected-file paths, historical evidence, and an explicitly deprecated compatibility input; the withdrawn draft `DecreeMatri` is not a current identity. This avoids moving the four protected files or breaking Git/worktree/recovery lineage. One identity manifest owns `display_name`, `canonical_skill_name`, `legacy_names`, and `locator_policy`; no duplicate alias skill, second package authority, or blind path rename is allowed. If the host cannot prove native alias support, report that limitation instead of claiming the old invocation works.
22. The Shiguan CLI allocates one immutable main decree number, freezes lineage, and binds every child/worktree/archive closeout to one idempotent operation and compound receipt. It reuses the existing task/event/archive/index authorities, preserves historical court codes, and applies the Section 0.5 RC2 -> RC4 -> RC6 sequence rather than creating a second ledger or database.
23. Project-memory/global indexing and office naming follow Section 0.6. Historical memory is preserved through append-only pointer supersession; immutable role-prefixed task names permit same-role reuse only, and office readiness comes from ordinary preload receipts rather than sidebar labels.

## 2. Files in scope

Create:

- `scripts/shiguan_migration_gate.py`
- `scripts/check_shiguan_migration_gate.py`
- `scripts/install_current_agent_copy.py`
- `scripts/check_install_current_agent_copy.py`
- `scripts/check_shiguan_host_memory_and_child_trace.py`
- `scripts/court_semantic_continuity.py`
- `scripts/check_semantic_continuity.py`
- `scripts/court_operation_journal.py`
- `scripts/court_memory.py`
- `scripts/check_court_memory.py`
- `scripts/check_full_repository_audit.py`
- `scripts/shiguan_memory_repositories.py`
- `scripts/check_shiguan_memory_repositories.py`
- `scripts/check_skill_identity.py`
- `references/manifests/install-projection.v1.json`
- `references/manifests/memory-store-registry.v1.json`
- `references/manifests/skill-identity.v1.json`
- every ordinary `agents/office-dossiers/*/AGENTS.md`
- `docs/logs/README.md`
- `docs/logs/2026-07-14-shiguan-install-remediation.md`

Modify:

- `scripts/migrate_shared_shiguan.py`
- `scripts/shiguan_paths.py`
- `scripts/ensure_obsidian_shared_vault.py`
- `scripts/ensure_portable_court_bootstrap.py`
- `scripts/sync_shiguan_obsidian_vault.py`
- `scripts/internal_memory_shiguan_bridge.py`
- `scripts/memory_decision.py`
- `scripts/reevaluate_memory_decisions.py`
- `scripts/tidy_shiguan_records.py`
- `scripts/court_cli.py`
- `scripts/sync_active_copies.py`
- `scripts/check_active_copy_hashes.py`
- `scripts/package_skill.py`
- `scripts/release_payload_manifest.py`
- `INSTALL-PROMPT.md`
- `scripts/check_install_prompt.py`
- `scripts/court_intake_gate.py`
- `scripts/check_court_intake_gate.py`
- `scripts/court_runtime.py`
- `scripts/check_court_runtime.py`
- `scripts/archive_checkpoint.py`
- `scripts/archive_runtime_task.py`
- `scripts/court_office_bootstrap.py`
- `scripts/court_multi_agent_protocol.py`
- `scripts/court_dispatch_policy.py`
- `scripts/check_court_dispatch_policy.py`
- `scripts/check_court_preload_semantics.py`
- `scripts/check_court_office_assignment_binding.py`
- `scripts/check_context_compression_survival.py`
- `scripts/check_court_result_semantics.py`
- `scripts/check_catalog.py`
- `SKILL.md`
- `references/court-shiguan-memory.md`
- `references/court-state-runtime-agents.md`
- `references/court-offices-dispatch.md`
- `references/court-closeout-validation.md`
- `references/court-supercc-runtime-selection.md`
- `references/sections/court-context-compression-survival.md`
- `references/sections/court-runtime-result-and-recruitment-contract.md`
- `references/obsidian-autosync-rest.md`
- `references/install.md`
- `references/sections/court-closeout-installation-validation.md`
- every `agents/standing-officials/*.toml`
- every corresponding `agents/supercc-dossiers/*/AGENTS.md`
- `README.md`
- `CHANGELOG.md`
- `RELEASE-LOG.md`
- `release-manifest.json`

---

### 2.1 Bounded specialist review and cluster repair contract

Discovery uses several bounded read-only specialists, never one catch-all reviewer: A duplicate/redundancy; B ambiguous semantics; C cross-source conflicts; D scripts/CLI/schema/exit codes/platform paths; E feature implementation and caller reachability; F tests/recovery/clean-index/append-only receipts; G security/privacy/publication/cross-platform. Each reviewer has an empty write set.

Every finding uses one schema: `finding_id, specialty, severity, confidence, source_path/line, conflicting_path/line, observed_behavior, expected_contract, minimal_RED, proposed_fix_scope, owned_paths, dependency, false_positive_notes`. Menxia is the only aggregate adjudicator: deduplicate common causes and return `ACCEPTED|REJECTED_FALSE_POSITIVE|DEFERRED|SUPERSEDED`. Shangshu dispatches only `ACCEPTED` findings grouped into dependency/write-set repair clusters, with one writer per file or semantic authority.

Each accepted cluster follows minimal RED -> single-owner GREEN -> matching specialist rereview -> cluster SPEC -> cluster QUALITY -> whole-repository regression. Do not restart the full court for every micro-finding and do not use bulk text replacement as evidence of behavioral GREEN.

### 2.2 Major-stage child-repository release branch loop

Every branch in this stage loop belongs only to the independent `court-capability-router` child repository and uses `release/beta0.5.x`; it is never a root-governance release branch. The root control repository may mirror only ledger metadata for stage, child ref, commit, worktree, and local-package receipt/hash. It must not absorb child files, history, or artifacts.

Treat only these aggregates as major stages: (1) Phase 1 covering P00 plus RC2/RC4/RC5/RC6 and its aggregate RED/GREEN/SPEC/QUALITY; (2) Phase 1.5 tasks-ledger durability; (3) Shiguan migration; (4) Obsidian/install/updater; and (5) final audit/package. A micro RED, checker, finding, or repair cluster does not independently advance the release branch.

At each major-stage gate, call the current working branch `release/beta0.5.x`. Complete the stage RED/GREEN/SPEC/QUALITY and all necessary global regression first. Then, in the child repository only, stage exactly the Menxia-approved pathspec as one bounded transaction, prove that the cached set exactly equals that approval, and create a local commit. Immediately prove the real index is `0`. Create a clean child worktree pinned to that exact commit; build and verify the local package only there; record commit, branch, worktree, package hash, and receipt. Obtain a terminal Section 2.3 outcome for previous `release/beta0.5.(x-1)` (`UPLOADED|NOT_AUTHORIZED|NOT_RUN|BLOCKED`), create the exact next sequential child branch/worktree `release/beta0.5.(x+1)` from accepted `x`, and complete Section 2.4 auto-handoff. Continue the next major stage only in that new task and release worktree. If the stage has no file delta, use the accepted current HEAD as the stage commit and do not create an empty commit. An existing incompatible ref or worktree fails closed; never force, reset, reuse, or overwrite it.

Before and after every gate, Git action, and package action, `git diff --cached --name-only` must count `0`. The bounded pre-commit window is the sole exception. If the cached set differs or commit fails, stop and unwind only that transaction; never stage, clean, or absorb unrelated dirty paths. The package worktree must be clean and contain no dirty or untracked build input.

Preserve beta0.5.12 and beta0.5.13 run1/run2 at their original paths, bytes, and hashes. New corresponding artifacts use run1b/run2b or a unique no-clobber suffix and external hashes. The major-stage commit/package/branch loop remains local; only after the next child release branch exists may Section 2.3 separately adjudicate an upload of the immediately previous completed version.

### 2.3 Previous-version GitHub upload gate and OSS-GOV evidence

When the current major-stage branch is `release/beta0.5.x`, automation may nominate only the immediately previous completed `release/beta0.5.(x-1)`, and only after current `x` commit/package acceptance. Never upload the just-completed handoff source `x`, skip to another version, or configure/upload the `D:\project` root control repository. Return a terminal outcome before Section 2.2 creates `x+1`.

Run the decision from a separate clean `OSS-GOV` child worktree such as `D:\project\worktrees\court-capability-router\oss-gov-beta0.5.(x-1)`, connected only to the Court common-dir and pinned to the previous version's exact commit. Its index must be `0` and it must have no dirty or untracked build input. Record worktree/common-dir/ref/commit, commands/results, package and manifest SHA-256, and do not consume uncommitted state from the active development worktree.

`PREVIOUS_VERSION_GITHUB_UPLOAD_GATE=PASS` requires all of: Apache-2.0 or another user-approved license matching repository files; bilingual Chinese/English GitHub README/homepage; bilingual CHANGELOG and version release notes; clean commit plus verified package/hash/manifest, privacy/security checks, and required tests; the correct Court child remote fetch/push URLs and target upstream/branch; and an explicit previous-version receipt binding candidate/successor versions and refs, commit, package/hash, security/tests/docs/license evidence, remote/upstream, and the exact `authorized_actions`. Any missing or mismatched field fails closed.

Authorize `push`, `tag`, PR, GitHub release, and asset upload separately; one action never implies another. Do not add or change a remote/upstream to bypass this gate. The current Court child has `remote_count=0`, so this run records `GITHUB_UPLOAD=NOT_RUN / REMOTE_ABSENT` and performs no upload.

### 2.4 Major-stage automatic local-task handoff gate

Every future major-stage loop auto-handoffs, but no handoff operation may start while any currently dispatched subtask, office, or lane is `running|pending|unreconciled`, holds a valid write lease, or has an uncollected result. Reconcile all terminal receipts first. This plan-only edit creates no task, branch, or worktree.

After package acceptance and the terminal Section 2.3 previous-version upload outcome, use root repo-control or a manifest-safe equivalent to create the one next Court child `release/beta0.5.(x+1)` worktree from accepted `x`. Synchronize `.repo-control/state/court-capability-router/<task-id>.json`, immutable task events, and the root ref-only mapping. The root stores mapping metadata only: do not check out child history, create a new mainline Codex worktree, copy the child repository, or duplicate an existing child worktree.

Then create a **new local Codex task** inside the existing `D:\project` project, with visible title exactly `release/beta0.5.(x+1)`. Point its root mapping/`attached/court-capability-router` to the already-created child release worktree. The old and new tasks must never concurrently own the same branch/write lease.

The new task receives only a compact handoff containing decree/task ids, completed major stage, child branch/worktree/common-dir/commit, package and plan hashes, semantic receipt/plan cursor, upload outcome, residual risks, and next atomic action. Keep full logs under `.repo-control/events/court-capability-router/<old-task-id>/` and provide that directory as `full_log_path`; never copy full logs into the prompt or reintroduce shared mutable `tasks.json`.

Require a `MAJOR_STAGE_HANDOFF_ACCEPTED` receipt binding old/new task ids, visible title, root project, child path/common-dir/branch/HEAD, index=`0`, root mapping state/event hashes, compact-handoff hash, full-log path, plan cursor/hash, and upload outcome. Close the old task only after the receipt verifies. On failure keep the old task open/paused and prohibit writes from the new task, preserving one writer and a recoverable anchor.

The first target is a `D:\project` local task titled `release/beta0.5.10`, reusing existing child worktree `D:\project\court-capability-router-beta0.5.10`. At execution time first prove branch=`release/beta0.5.10`, common-dir=`D:\project\court-capability-router\.git`, and index=`0`; do not create, move, or overwrite that child worktree. Do not sync mapping or create the task until all current subtasks have closed.

### Task 0.1: P00 Token Economy Guard (highest priority)

**Status/order:** `HIGHEST_PRIORITY / PLANNED_RED`. This task runs after Phase 0 confirmation and before Task 0.5, Task 1, or any later new agent, wave, retry, redispatch, or assignment. No new child starts until `P00_TOKEN_ECONOMY_GATE=PASSED`. Do not blindly interrupt agents already running under valid leases; they may finish the current valuable atomic unit, but their next dispatch must use P00.

P00 is the dispatch/recovery consumption profile of the existing Section 0.4 Semantic Continuity Guard, not another protocol. Low-token dispatch and compaction/resume recovery reuse the same `invariant_capsule_sha256`, `semantic_epoch == charter_revision`, authority path/hash/revision, plan path/hash/revision/cursor, and semantic receipt. Do not create a second capsule, authority, receipt authority, ledger, or state machine.

- The default packet carries only `task_id/sub_id`, the existing `<=2 KiB` runtime inline invariant capsule, exact authority path/hash, plan path/hash/cursor, current semantic receipt, minimal role/superior/lease/write-set/worktree/preload-hash bindings, and evidence pointers. `super parallel` changes topology; it does not copy the full parent context into every child.
- Default to `fork_turns=none` and the minimum context needed by the existing gates: minimal office preload, registry-first selection, `reuse-compatible-instance-first`, the hierarchical P05 budget lease, one isomorphic receipt for `child_agent|worktree_thread`, superCC-disabled zero-load, and bounded child trace.
- The default result is a bounded JSON receipt containing verdict, first error, changed/verified paths and hashes, semantic/capsule/cursor bindings, and local evidence/log pointers. Keep full logs, full diffs, and large outputs local.
- Do not run or return full `list_agents`, full diff, or full file by default. Escalate only the smallest matching source when a hash changes, evidence is ambiguous, diagnosis requires it, or the user/Taizi explicitly relaxes the packet from a recorded budget. Record override source, scope, budget, reason, and expiry.
- Compaction/resume compares only the current capsule/semantic receipt, plan cursor, authority hashes, and changed-path hashes. Unchanged hashes do not trigger full-file reads; changed epoch/hash/cursor values require an exact-source reread and re-verification. MEMORY or summaries never replace the current receipt.
- Phase 1 uses only the existing runtime inline capsule. Real Shiguan task-point persistence remains after Shiguan migration and shared-root acceptance in execution-book Phase 4 / this plan's Task 5, reusing the same binding. P00 does not move task-point writes ahead of migration.

**RED:** Fail default full-context copying, `fork_turns=all`, capsule size over 2 KiB, missing task/sub-id or authority/plan/receipt binding, default full `list_agents`/diff/file, unchanged hashes causing full reload, changed hashes bypassing reload, different child/worktree receipts, superCC surface loading while disabled, registry/reuse/budget/trace bypass, unbounded child trace, or any second capsule/authority/state machine. The current `court.agent.dispatch_message_budget.v1` 6,000-character floor and 12,000-character ceiling are an explicit drift RED because they normalize large default dispatches instead of enforcing the bounded P00 packet.

**GREEN:** Reuse the Semantic Continuity core to enforce one bounded dispatch/context packet and bounded result receipt in the existing production dispatch/admission/message-budget path. Preserve O(1) unchanged-hash resume. A recorded user/Taizi budget override may widen only the current packet and cannot bypass semantic, safety, hierarchy, lease, or write-set gates.

**SPEC:** Unify and tighten the existing `fork_turns=none`, registry-first, 2 KiB capsule, worktree carrier, budget-pool, minimal-preload, bounded-trace, and post-migration task-point contracts. Do not duplicate them. Child and worktree carriers use the same receipt; ordinary/super parallel use the same packet; superCC-disabled paths load zero superCC annex/dossier/profile/script/daemon surfaces.

**QUALITY:** The phase-level behavior checker covers default and explicit override, child/worktree parity, compaction unchanged/changed hashes, first-error receipts, local-log pointers, superCC zero-load, registry/reuse/budget/trace composition, and Windows/macOS/Linux path handling. Preserve `pending_count=69` without body access, the four protected paths/bytes/hashes, empty Git indexes, `.pyc=0`, and remote count `0`; do not stage, commit, push, or publish.

**Completion:** Plan text, MEMORY, Shiguan notes, or fixtures alone are not implementation. P00 completes only when the root `SKILL.md` pins the necessary semantics, one directly linked governing reference (`references/court-state-runtime-agents.md`) owns the details, the existing production runtime/CLI dispatch and budget path enforces them, and a behavior checker reusing `scripts/check_semantic_continuity.py` plus required runtime regressions passes with the 6000/12000 default drift closed.

### Task 0.5: `CCR-R2-SHIR-20260714-A02-P05-TB01` pre-child resource budget approval

Only after Task 0.1 P00 passes, and before Task 1 RED or any later child-agent wave, apply the authoritative Phase 0.5 contract in `docs/plans/2026-07-14-ccr-r2-shir-a02-execution-book.md`:

- Taizi evaluates the remaining task, independent write sets, host active/capacity/retained/reclamation state, RAM pressure, and message/tool/time budgets.
- Record the requested and approved roles/count and issue `TAIZI_RESOURCE_BUDGET_APPROVED`, `DOWNSIZED`, `SERIALIZED`, or `DEFERRED` before the first child start.
- Start only the approved count. Never start the maximum wave and then interrupt surplus agents.
- Reassess for every later wave or material scale/resource change; approval does not carry forward automatically.
- Run the approval as a hierarchical normalized `100%` pool: Taizi allocates dynamic envelopes to the Three Departments, each parent sub-allocates only within its envelope to direct child offices/instances, and every lease records parent id, share, hard caps, write set, output, and return conditions.
- Preserve the same direct-superior chain in every lease and preload record: `shangshu -> ministry -> ministry worker/craftsman`; a craftsman record with `direct_superior=shangshu` is a hierarchy failure.
- A percentage is scheduling share, not permission to exchange independent RAM/concurrency/context/tool hard limits. Allocated leases remain with useful running work until completion or an evidenced safety/cancellation exception; completion returns the unused share upward.

For `A02-PHASE1-RED-W1`, the recorded approval at `2026-07-14T14:03:11+08:00` limited the wave to six disjoint write sets with RAM at `58.07%`; the first child start followed at `2026-07-14T14:04:45+08:00`. This satisfies the new ordering without cancelling approved agents.

### Task 1: Capture RED and execution-time preimage

**Files:** create `scripts/check_shiguan_migration_gate.py`; inspect current roots and Git index.

- [ ] Recount files/bytes/newest mtime under the old Shiguan root without opening record bodies.
- [ ] Record the exact path, length, and SHA-256 for the four protected cross-conversation files.
- [ ] Add a deterministic RED proving that any nonzero/unknown pending-body count returns `MIGRATION_BLOCKED_PENDING_BODIES` before traversal, hashing, copy, rename, deletion, or mark-seen.
- [ ] Record `.agents` and the bounded runtime/controller-detected open tool set, including `codex|claude-code|hermes|other:<stable-id>` versions/hashes and installation states; this is evidence only and does not authorize installing every detected tool.
- [ ] Assert `git diff --cached --name-only` is empty.
- [ ] Add RED cases for active conversation, stale conversation, missing record binding, source mutation, target outside `.agents`, fixed multi-tool fanout, absolute persisted profile/dossier/skill paths, missing pinned initial semantics, child dispatch that does not load the exact role `AGENTS.md`, and a resumed/corrected task that skips charter revision or 三省 re-entry.
- [ ] Add RED proving whole-tree counts include root: default `16 = root + 15 children`, explicit `17 = root + 16 children`, and explicit `18 = root + 17 children`; never reinterpret the explicit number as child slots. The normal 16 ceiling rejects the seventeenth whole-tree thread; newest explicit `count>16` and newest explicit unlock pass only within configured capacity; stale/non-explicit override sources fail closed; 99% memory pressure still downgrades; and no override bypasses the hierarchical budget lease or launches beyond its approved count.
- [ ] Add behavioral RED with temporary manifest records and an injected discovery spy proving a valid current-tool-compatible registered capability is selected without discovery; `missing/stale/corrupt/no_sufficient_match` may invoke bounded fallback, incompatible records are not dispatchable, and 吏部 must validate/update the existing roster after install, upgrade, hash/version drift, dispatch failure, or phase closeout.
- [ ] Add RED that fails when any amended hard behavior exists only in memory/Shiguan text and is not reachable from the pinned `SKILL.md` nucleus or a unique directly linked governing reference with a behavioral checker.
- [ ] Add shared/native Git RED proving: the shared Shiguan root is one local-only allowlisted repository; records and memories have distinct schemas/lifecycles; record corrections append `supersedes`; runtime/pending/private/config/package paths and any shared-repo remote fail. Every eligible native memory remains at its loader-required path and is an independent Git repository through an existing owner repo/pathspec, compatible in-place init, or separate git-dir + native work tree. Reject migration/shared-repo body copy, submodule/subtree/nested tracking, any Shiguan-created remote or Shiguan add/change/fetch/push against an existing remote, unverified Git initialization, staging unrelated dirty paths, missing repo/HEAD/write-policy receipt, native git-dir/object leakage into shared/Obsidian/package output, or a dirty index after checkpoint.
- [ ] Add memory-projection/link RED proving that manifest-ineligible or host-scan-discovered tools are rejected; `codex`, `hermes`, and `claude-code` are examples while stable `other:<id>` keeps the set open; every eligible class has an isolated namespace/graph and native-memory Git receipt; cross-tool nodes/edges fail. Require exactly one idempotent pinned managed block in each canonical memory entrypoint and a reverse Shiguan link carrying the native repo HEAD/pathspec; reject missing/duplicate/escaping links, body or line-ending drift outside the block, unmatched cross-repo receipts, and false `MIGRATION_LINKS_VERIFIED`. Projected fields are limited to relative source id/path, repository HEAD/hash/fingerprint, state, headings/topics/relations; private raw bodies and release packages are absent; body mirroring requires a later explicit decree plus Menxia privacy approval.
- [ ] Add blank-host RED proving the read-only memory-feature/Git-compatibility probe runs before shared-root creation, any Shiguan/native-memory Git initialization, memory enablement, or install write; every detected/selected manifest tool returns `enabled|disabled|unavailable|unknown` with native path/repository evidence and a user-facing prompt; probe side effects fail; `unknown` cannot auto-enable; Claude/Hermes/other install/config/enable/body mutations beyond the approved in-place Git/pinned block fail without newest explicit authorization.
- [ ] Freeze the current V2 adjudication RED preimage: `python -B scripts/reevaluate_memory_decisions.py --dry-run` reports `entries=1033` and `changed_candidates=493`. Prove this candidate-only heuristic cannot create a legal `WRITE`, approval receipt, or native application claim.
- [ ] Add RED proving `tidy_shiguan_records.py --apply` and every maintenance/re-evaluation path reject in-place historical `memory_decision` rewrites without `decision_id` and `menxia_receipt`; corrections must append a new decision carrying `supersedes`.
- [ ] Preserve `python -B scripts/check_shiguan_host_memory_and_child_trace.py` as an expected RED at `A02_RED_EXPECTED_FAILURES=43` until production host-memory evaluator, projection, blank-host, adapter, and receipt APIs exist. Fixture/plan text or an expected-failure count is not implementation evidence.
- [ ] Add V2 layer RED proving semantic adjudication, write authority, and native application cannot impersonate one another; Git commit, Obsidian projection, native approval queue, or file existence never promotes a candidate to approved.
- [ ] Add Semantic Continuity RED proving: new tasks initialize revision/hash/capsule; correction revokes all stale derived/binding/agent/capsule/attempt state and returns to ThreeDepartments; old epoch/attempt/dispatch results quarantine; unbound `agent_finish` text is rejected; forbidden capsule fields survive compaction; stale resume/direct execution-state jumps fail; permission-only changes do not increment semantic epoch; plan/Git/recovery/Shiguan inconsistencies are detected; every ledger-write crash point recovers; and Windows/macOS/Linux path/time fixtures agree.
- [ ] Add office-carrier RED proving `child_agent` and `worktree_thread` accept the same bounded task/role/hierarchy/budget/lease/write-set/preload/semantic/communication/result contract; reject missing exact-role preload, duplicate authority/writer/attempt, wrong worktree/common-dir, or absent independent worktree record.
- [ ] Add superCC separation RED proving authority/topology selection discloses `EXPERIMENTAL_CLI_ONLY` plus CLI/zellij+squad requirements; ordinary `approval|autonomous|super` resolves exact-role AGENTS only from `agents/office-dossiers` and never activates or loads `agents/supercc-dossiers`, superCC annex/profile/scripts/watchdog/daemon/visible-office state; only a newest explicit `superCC` choice may load/probe that surface.
- [ ] Add Decretum Matrix identity RED from a structured name-surface inventory. Fail when root `SKILL.md`, current user-facing docs, registry/profile/dossier, package/release metadata, install receipts, Shiguan/Obsidian titles, or runtime loader disagree with `Decretum Matrix（诏令矩阵）` / `decretum-matrix`; when the withdrawn `DecreeMatri` remains on a current identity surface; when a non-allowlisted current surface still presents `court-capability-router` as the product; when compatibility is not deprecated or is falsely claimed; or when renaming creates a second skill/package authority, mutates protected paths/bytes/hashes, or breaks repository/worktree/recovery/Shiguan lineage. Historical logs and approved technical locators remain byte/path stable.
- [ ] Add blank-host config RED over `codex|claude-code|hermes|other:<stable-id>` proving: controller/source-of-truth probe precedes mutation; unmet standards return non-blocking `REMINDER_ONLY` with no compliance claim; every mutation requires newest explicit config-change authority; a proven CC Switch target block uses reversible upstream backup/transaction and cannot pass from DB evidence alone; Codex applies an equivalent/compatible semantic delta to parsed `config.toml` and `managed_config.toml` while preserving secrets/provider/unknown keys; no-CC-Switch Codex uses the reversible dual-file path; a failed Hermes upstream attempt is recorded before any authorized/certain actual-file fallback; and uncertain schema, ownership, precedence, current values, or compatibility causes no mutation while unrelated work continues.
- [ ] Add worktree-trace RED proving every participating worktree has one separate `worktree_trace_id`/Shiguan record with repo/common-dir/worktree/base/HEAD/lane/owner/write-set/index/pyc/verification/recovery/terminal-disposition fields. Reject child-summary-only evidence, merged multi-worktree records, workspace-ledger substitution, full prompt/diff/private-log capture, and any pending-body read during metadata backfill.
- [ ] Add office-load RED proving routine children reject an unread/partial compact root `SKILL.md`, a bloated root that still embeds all-reference/all-office extended content, wrong-role loads, missing owning-ministry/direct-adjacency/task-budget-worktree/evidence-stop/hash fields, untriggered cross-role content, missed governing-reference escalation, false loaded-path/byte reports, and any plugin/plugin-cache/plugin-only manifest/MCP/UI dependency or artifact.
- [ ] Add task-point RED using only temporary roots. Reject pure pointer authority and every missing/stale/expired/revoked/hash/path/current-runtime/task/charter/dispatch/role/instance/superior/worktree/lease/write-set/preload mismatch before `running`; prove correction revokes old capsule/admission/agent state and retry cannot revive an old attempt. Preserve canonical `court_code`; use an independent lineage-bound `task_point_code` with monotonic sequence/revision/attempt, and reject collisions or sensitive/full-body capsule content.
- [ ] Add the seven exact Shiguan CLI numbering/lineage RED families: (1) archive-orphan crash followed by sequence reuse or a second archive; (2) 32 replays of the same operation producing duplicate side effects; (3) `record_uid` collision; (4) child/worktree lineage drift; (5) tasks/event/archive/index/compound-receipt divergence; (6) absent worktree admit/start/report/finish/close lifecycle or terminal disposition; and (7) authority-realm/root-fingerprint split brain. Each case must fail first with a stable reason code. Existing same-root lock and 32-process uniqueness passes are regression evidence, not substitutes for these RED cases.
- [ ] Reproduce the current all-office drift: the `libu-hr` dossier profile hash is stale after its TOML changed, and legacy `%LOCALAPPDATA%` wording remains in office preload surfaces.

Run:

```powershell
python -B scripts/check_shiguan_migration_gate.py
python -B scripts/check_install_current_agent_copy.py
python -B scripts/check_shiguan_host_memory_and_child_trace.py
python -B scripts/check_court_preload_semantics.py
```

Current command outcomes are explicit and independently tracked:

| Command | Current expected result | Meaning |
| --- | --- | --- |
| `check_shiguan_migration_gate.py` | exit 0; `22/22`, `pending_body_accessed=false` | Lane A synthetic migration contract is GREEN; real cutover remains blocked by metadata pending/quiescence gates. |
| `check_install_current_agent_copy.py` | exit 1; `ok=false`, missing production module/manifest, `passed_cases=0` | Install/config/package branch remains RED. |
| `check_shiguan_host_memory_and_child_trace.py` | exit 1; `A02_RED_EXPECTED_FAILURES=43` | Host-memory/projection/blank-host/child-trace production APIs remain RED. |
| `check_court_preload_semantics.py` | exit 1; `gap_count=11` | Pinned semantics, relative paths, office duties/hierarchy, charter/correction/resume remain RED. |

A changed exit code or sentinel must be explained by the owning cluster; do not summarize this four-command matrix as “both fail.”

Current cluster status is `RC1=APPROVED` and `RC5 core=APPROVED`; the full runtime keeps only the external RC4 `office-bound-wave` RED. RC5 rollout debt remains in README, the office-name/profile/skill binding reference, and bootstrap `required_skill/loaded_skill` identity. These local approvals do not make Phase 1 aggregate GREEN.

### Task 1.1: Close Phase 1 semantic-binding GREEN

Before Phase 1 aggregate GREEN/SPEC/QUALITY, implement the Semantic Continuity core on the existing task/event authority: new-task revision/hash/capsule, correction full invalidation and ThreeDepartments re-entry, dispatch/result binding, stale-result quarantine, minimal JSON `court semantic` commands/receipts, and semantic task/event paired-write recovery. Use the existing lock/CAS and no second store/state machine.

Apply the accepted numbering/lineage cluster order inside this task:

1. **RC2 first:** add the generic operation interface, minimal recovery journal, expected-task-revision CAS, decree-open idempotency, compound receipt, `PREPARED -> ARCHIVE_COMMITTED -> TASK_EVENT_COMMITTED`, and `closeout-recover --operation-id`. Use temporary local roots for the Phase 1 archive/index adapters so the real pending queue is never accessed.
2. **RC4 after RC2:** serially update shared `court_runtime.py` for generic office admit/start/report/finish/close and frozen decree/parent/child lineage. Preserve `agent-*` as child-agent wrappers; worktree adds only thread/worktree/branch/start-head proof. Require at least two child and two worktree fixtures with matching lifecycle/result schemas.
3. **RC6 bounded:** implement the local authority-realm/root-fingerprint pure contract and fixtures in Phase 1. The real `.agents` root fingerprint and RC2 archive transaction attach only after Tasks 2-4 satisfy pending, quiescence, cutover, and shared-root gates.
4. Keep existing same-root locking and 32-process allocator uniqueness as positive regressions. Add 32-way same-operation replay, `record_uid` collision, and allocation/archive/index/task/event killpoint recovery without rewriting those working primitives.

Required local acceptance is exactly-once operation replay, immutable main numbering, explicit-only reclassification, isomorphic child/worktree lifecycle, local-root mismatch fail closed, and metadata-only context. Cross-host/NFS/SMB/distributed coordination remains `DEFERRED|UNSUPPORTED`.

Run `python -B scripts/check_semantic_continuity.py --json` plus the relevant runtime/result/context-compression checks. Required result: `SEMANTIC_BINDING_CORE_PASS`. Phase 4 only attaches downstream memory/task-point/install consumers and cannot provide this first GREEN.

### Task 1.2: Complete Phase 1.5 ledger durability

Only after Task 1.1 and Phase 1 cluster GREEN/SPEC/QUALITY pass, absorb the sealed Lane G ledger/runtime/concurrency delta. This task exclusively owns `tasks.json` stable snapshot retries, LKG, corruption quarantine, sanitized diagnostics, Windows replace behavior, and explicit CAS recovery. It must not redefine semantic epoch or charter authority.

Required result: `TASKS_LEDGER_INTEGRITY_GATE=PASSED` with runtime/concurrency/consumer SPEC/QUALITY, clean indexes, no `.pyc`, and no pending-body access. Task 2 metadata waiting may continue read-only, but Phase 3 migration cannot start first.

### Task 2: Wait for conversations that occupy Shiguan records

**Files:** create `scripts/shiguan_migration_gate.py`; reuse existing runtime/presence metadata and file locks.

- [ ] Scan presence/runtime metadata only.
- [ ] Run the metadata-only pending queue checker. Require `pending_count == 0`; otherwise return `MIGRATION_BLOCKED_PENDING_BODIES` and stop. The current preflight is 69, so cutover is presently blocked.
- [ ] Treat unknown record bindings as `"*"` and block migration.
- [ ] When active conversations exist, write only this metadata marker:

  ```text
  %USERPROFILE%\.agents\court-shiguan\migration-control\CCR-SHIGUAN-AGENTS-20260714.json
  ```

- [ ] Do not edit, move, or mark the occupied record itself.
- [ ] Return `WAITING_FOR_ACTIVE_CONVERSATIONS` and stop after a bounded 50-second check window.
- [ ] Resume later and require two zero-active scans at least 30 seconds apart with unchanged file count, byte count, newest mtime, and inventory digest.

Run:

```powershell
python -B scripts/shiguan_migration_gate.py scan `
  --source-root "$env:LOCALAPPDATA\court-shiguan\court-capability-router\references" `
  --target-root "$HOME\.agents\court-shiguan\court-capability-router\references" `
  --migration-id CCR-SHIGUAN-AGENTS-20260714 `
  --format json
```

Stop unless the result is `READY_TO_MIGRATE` with pending count zero and two stable scans.

### Task 3: Migrate the authoritative Shiguan path

**Files:** modify `scripts/migrate_shared_shiguan.py` and `scripts/shiguan_paths.py`.

- [ ] Require pending count zero, two stable scans, source and target on the same NTFS volume, target absent, old source not a reparse point, and normalized target under `%USERPROFILE%\.agents`.
- [ ] Reject a pre-existing target, unexpected reparse point, cross-volume move, path escape, junction loop, process lock, or stale migration marker. Do not fall back to a full copy.
- [ ] Stop the Shiguan daemon only for final cutover; reread the source directory file-id and metadata inventory.
- [ ] Atomically rename the old physical root to the new authoritative root on the same volume. This preserves one physical store and avoids a `legacy-source` duplicate.
- [ ] Create a directory junction at the old `%LOCALAPPDATA%` path pointing to the new `.agents` root.
- [ ] Verify the junction canonical target, matching directory file-id through both paths, unchanged file count/bytes/newest mtime, then restart the daemon.
- [ ] On failure, remove only the junction created by this run after verifying its exact target; atomically rename the matching directory file-id back to the old path; restore the daemon. Never recurse through or delete a pre-existing junction.
- [ ] Validate idempotence and rollback with temporary fixtures and injected failure points before rename, after rename, after junction creation, and before daemon restart. Do not perform a destructive power-loss test against the real Shiguan.
- [ ] Emit `CUTOVER_VERIFIED` only for this physical shared-root move. Do not claim overall migration complete until Task 4 has created/adopted the Git repositories and verified every required bidirectional memory link as `MIGRATION_LINKS_VERIFIED`.

Run GREEN:

```powershell
python -B scripts/check_shiguan_migration_gate.py
python -B scripts/quick_validate.py .
```

Expected: exit `0`; one physical Shiguan store; protected files unchanged.

### Task 4: Rebind Obsidian and shared-root semantics

**Files:** modify the Shiguan/Obsidian/bootstrap scripts and governing references listed above.

- [ ] Make `.agents\court-shiguan` the default root in `scripts/shiguan_paths.py` and `SKILL.md`.
- [ ] Keep source-agent detection independent from Shiguan ownership.
- [ ] Replace only the old Shiguan vault entry using existing CAS-safe Obsidian config handling.
- [ ] Register the new `shiguan-tree` vault without forcing it open.
- [ ] Run preserve-only sync and require `removed=0`.
- [ ] On an existing host, do not render memory projections until Task 3 migration and the single-physical-store checks pass.
- [ ] After `CUTOVER_VERIFIED`, initialize or adopt the authoritative Shiguan root as one local Git repository. Apply the privacy allowlist before its first add, keep it remote-free, serialize commits, record parent/HEAD/tracked-path receipts, and require a clean index after every checkpoint. Formal records are append-only; memory decisions evolve separately with record/commit lineage.
- [ ] Implement `court memory scan` and `court memory adjudicate` as JSON agent-first commands over side-effect-free policy functions. Scan emits evidence/privacy/dedup/conflict/scope/freshness facts only; adjudicate requires the Menxia aggregate receipt and emits stable `decision_id`, decision/status fields, resolution, origin, evidence refs, and optional `supersedes`.
- [ ] Make memory decision history append-only. Disable or replace the `tidy_shiguan_records.py --apply` path that rewrites verdicts in place; maintenance may normalize non-semantic metadata only, or append a new superseding decision with an explicit Menxia receipt.
- [ ] For every runtime/controller-verified installed tool in the open class set, resolve the native memory root and owning Git repository without moving the root. Register an existing repo + memory pathspec when present; otherwise initialize at the native root only after compatibility proof, or use a separate git-dir with the native root as work tree. Require independent repositories, no submodule/subtree/nested tracking or shared-repo body copy, and no unapproved staging of pre-existing changes. New repos have no remote; preserve but never mutate or use an existing tool-owned remote. Exclude native git-dir/object history from the shared repo, Obsidian, and packages.
- [ ] Write one versioned begin/end-marker pinned navigation block at the top of each canonical memory entrypoint, immediately after any mandatory tool frontmatter/header and before ordinary content, linking to the shared `shiguan-tree/_index.md` and `memories/tools/<tool_class>/`. Preserve all bytes and line endings outside the block; use a supported `00-SHIGUAN.md`/equivalent top-pinned entry when direct insertion is unsafe, otherwise return `LINK_BINDING_BLOCKED` and block completion.
- [ ] In the shared Shiguan Git hub, write one registry/namespace link per native memory Git repository with `memory_store_id`, native repo/source/pathspec/HEAD, shared namespace/HEAD, state, write policy, and paired commit receipt. In the native repo, make the pinned block point back to the shared repo id/namespace/commit. Commit both sides separately under the same serialized `transaction_id`, reread both, and emit `MIGRATION_LINKS_VERIFIED` only when the reciprocal ids, commits, and pathspecs agree. Empty/disabled memory stores still require a Git repository, empty-state namespace, and both links.
- [ ] Reuse the existing bridge/index/export/sync path to render index-level MEMORY/memories projections only for tool classes whose install projection/manifest proves this skill is installed. Normalize to `codex|hermes|claude-code|other:<stable-id>`; emit one isolated namespace and graph per class and reject all cross-tool nodes/edges. Do not add a database, daemon, or generalized discovery layer.
- [ ] Keep every native memory file tool-authoritative. Outside the managed pinned block, tool-native writes, and separately approved current-tool update-note, Shiguan must not alter bodies. Project only relative source id/path, repository HEAD/hash or live-prefix fingerprint, state, headings/topics/relations; exclude private raw bodies and release packages from both projection inputs and packaged outputs. Leave body mirroring blocked for a later explicit decree and Menxia privacy review.
- [ ] On a blank host, before creating the shared root or Obsidian registration, derive the bounded detected/selected tool set from the install projection/manifest and run the no-write memory-feature probe. Show each enum result, evidence, and a user-facing choice prompt; do not install or enable anything in the probe. Only after that decision may the normal blank-host branch create the `.agents` shared root; do not install unrelated tools.

Run:

```powershell
python -B scripts/ensure_portable_court_bootstrap.py --shared-shiguan-and-obsidian-only --check-only
python -B scripts/sync_shiguan_obsidian_vault.py --dry-run
python -B scripts/check_shiguan_host_memory_and_child_trace.py
python -B scripts/check_portability.py
```

Expected: registered vault is the `.agents` tree, unrelated Obsidian entries are preserved, and zero files are removed.

### Task 5: Apply current-tool installation and all-office binding semantics

**Files:** create the projection installer/checker; update all office TOML/dossiers and related binding checks.

- [ ] Define three projections: shared `.agents`, portable current-tool copy, and repository-only files.
- [ ] Require `.agents` in every installation.
- [ ] Detect the current tool from the running environment/config.
- [ ] Use this same bounded install projection/manifest as the only memory-probe candidate and Obsidian-projection eligibility source. A detected/selected tool may be probed, but it is not projected until the manifest proves this skill is actually installed; never full-scan the host to discover more tools or memories.
- [ ] Treat `codex|claude-code|hermes` as built-in adapters, not the complete tool set. Normalize every other verified tool to stable `other:<stable-id>` and require the same native-path, independent-Git, namespace, link, privacy, and write-policy contract before claiming support.
- [ ] Make blank-host write entrypoints consume the prior probe receipt and user choice before shared-root create, any Git initialization, memory enable, or install write. `unknown` blocks automatic memory enablement; `disabled` is reported rather than silently enabled. For verified installed Claude/Hermes/other, the newest instruction authorizes only in-place Git stewardship plus the pinned managed-link block; enablement, configuration, installation, and body writeback still require separate newest explicit authorization.
- [ ] Install only the current tool in addition to `.agents`.
- [ ] Allow Claude/Hermes/other skill installation, configuration, memory enablement, or body writeback only through a newest explicit user request. The already requested in-place Git stewardship and pinned managed-link block are a narrow exception for tools proven `active_verified|installed_verified`.
- [ ] Only after Task 3 migration (or blank-host no-source proof), Task 4 shared-root work, and the normalized current-tool installation/projection stage pass, run the read-only config-standard/controller probe for `codex|claude-code|hermes|other:<stable-id>`. Do not move this branch ahead of migration/current-tool completion.
- [ ] If standard config requirements are unmet, emit `REMINDER_ONLY` with exact evidence, `compliance_claimed=false`, and no mutation. The reminder is not a stop gate for unrelated migration, install, Obsidian, validation, or packaging work.
- [ ] Before any authorized config mutation, probe CC Switch and the target-specific ownership/precedence chain. When its target block is proven, back up the sensitive controller/config preimage and use a reversible transaction against that upstream block before updating actual effective files; never patch only a leaf TOML that the controller can overwrite.
- [ ] For Codex, structurally parse and merge the approved delta equivalently/compatibly into both `config.toml` and `managed_config.toml`; preserve credentials, provider routing, comments/unknown keys where supported, and unrelated values. Without CC Switch, use the same controlled backup/rollback dual-file path. Reject blind byte replacement.
- [ ] For Hermes, preserve a CC Switch upstream attempt/result when present; if controller management fails, use the reversible actual-file path only with newest explicit config-change authority and certain loader/path/precedence/current-value semantics. Apply the same controller-first and actual-file acceptance rule to `claude-code` and `other:<stable-id>`.
- [ ] If DB schema, field ownership, effective precedence, current values, or delta compatibility is uncertain, do not modify anything; report each uncertainty and continue unaffected work. Accept configuration compliance only after actual effective files reread and parse to the intended semantics, plus a runtime probe when available; DB state alone never passes.
- [ ] Keep the Codex config default at 16 whole-tree threads. Preserve a current explicit `--threads N` above 16 without clamping, but treat configuration as capacity only: dispatch still requires current explicit count/unlock provenance and the Taizi resource lease.
- [ ] Apply office display name, profile identity, TOML binding, accepted skill semantics, superior, dossier, and evidence contract to every office file, not only one office.
- [ ] Persist profile, dossier, and skill sources as normalized relative paths while resolving and hashing their absolute files only in memory.
- [ ] Pin the sufficient initial semantic load at the top of `SKILL.md` and make the existing catalog/binding checks reject a missing, late, or incomplete pinned block.
- [ ] Put P05 hierarchical budgeting, the direct-superior chain, registry-first selection/Libu-HR maintenance, phase-level TDD, current-tool/shared-Shiguan boundaries, and continuation/closeout gates into `SKILL.md` or its direct unique governing references. Record source file hashes and passing behavior tests; never cite `MEMORY.md` as implementation proof.
- [ ] Route post-court skill selection through the existing capability registry first. Record relative skill path, current-tool compatibility, version/hash, verification time/evidence, status, and failure/refresh reason; refuse unconditional full rescans and prefer no suitable result over an unverified registry bypass.
- [ ] Make 吏部 the active maintenance owner through bounded event-driven refreshes at install/upgrade, detected drift, failed dispatch, and phase closeout. Do not add a daemon or a second source of truth.
- [ ] Enforce the existing responsibility chain at preload/dispatch: 太子/三省 own intake, audit, rejection, sequencing and integration; 六部 receive approved executable specialist assignments; 工坊/工匠 receive concrete execution steps. This is a loading contract and must not redefine the governing office semantics.
- [ ] Make exact role-dossier loading mandatory for every spawned child; persist `agent_dossier_loaded=YES` only after the child acknowledges the relative dossier path and current hash. Ordinary `child_agent|worktree_thread` carriers resolve only `agents/office-dossiers/<role>/AGENTS.md`; `agents/supercc-dossiers` is unreachable unless the newest explicit topology is superCC. Reject prompt-only identity, stale hashes, wrong-role dossiers, ordinary-to-superCC fallback, and missing preload acknowledgement before any task action.
- [ ] Normalize office carrier receipts as `child_agent|worktree_thread|supercc_cli_office`. Worktree threads use the root-visible task plus project-scoped child worktree/attached path, exact-role preload, semantic receipt, budget/lease/write-set, message/status/result binding, and independent Shiguan worktree record. Carrier changes never create another authority or concurrent writer for the same scope.
- [ ] Split all superCC-only semantics into one directly linked on-demand annex plus `agents/supercc-dossiers`. At authority/topology selection disclose experimental CLI-only status and requirements; load/probe that surface only for a newest explicit `superCC` selection. The ordinary path must use `agents/office-dossiers` and demonstrate zero superCC dossier/annex/profile/script/watchdog/daemon/visible-office loads or starts.
- [ ] Implement the Decretum Matrix rename through one identity manifest and bounded surface owners. Set canonical skill name/invocation to `decretum-matrix` / `$decretum-matrix`, display `Decretum Matrix（诏令矩阵）`, remove the withdrawn `DecreeMatri` from current identity consumers, and update all tests. Keep `court-capability-router` only in the approved locator/history/deprecated-input allowlist, resolve any supported compatibility input to the same physical authority, and never create a duplicate alias skill. Use structured parsers/constants where available; do not apply a repository-wide textual replacement.
- [ ] Initialize new task charter revision/hash and verify pause/resume/correction continues the same task, invalidates stale derived state, returns to 三省, and preserves the empty Git index.
- [ ] Consume the already-passed Task 1.1/1.2 Semantic Continuity guard and ledger durability. This task only attaches memory/task-point/install/Obsidian downstream apply/commit/closeout to the current receipt and reuses the same task-point binding; it must not reimplement the core or add another state system.
- [ ] Consume the completed RC2/RC4 generic operation and office-lifecycle contract. After Tasks 2-4 prove the real authority root, attach only the RC6 root receipt and RC2 real archive stage; do not allocate a new main code, alter frozen lineage, or create per-worktree task/event ledgers.
- [ ] Expose `court office admit|start|report|finish|close` as the canonical lifecycle. Keep `agent-*` as child-agent compatibility wrappers and require the worktree proof extension to remain limited to `thread_id/worktree_fingerprint/branch/start_head`.
- [ ] Verify every downstream mutation rejects drift/stale epochs and preserves quarantine/reconcile semantics established earlier.
- [ ] Keep `.codex/agents/*.toml` model-neutral.
- [ ] After an authorized install updates the manifest, refresh only that tool class's isolated metadata/index projection. Projection is not memory writeback and must not modify the source MEMORY/memories files.
- [ ] Implement `court memory apply`, `court memory verify`, and `court memory reconcile`. Apply requires `adjudication_status=approved`, `decision_id`, `menxia_receipt`, current-tool newest write authority or non-current newest target authorization, and adapter capability evidence. Verify rereads the native store and both Git receipts; reconcile completes or rolls back partial paired transactions without changing the semantic verdict.
- [ ] Treat native pending/approve/reject queues as application gates only. Record their result in `application_status`; they cannot replace or rewrite the Menxia verdict.
- [ ] Register and checkpoint the installed tool's native memory through its independent Git repository without relocating it. Stage only the approved managed-link/current-tool update-note pathspec, preserve unrelated dirty state, create no remote and perform no remote operation, and pair its commit receipt with the shared Shiguan registry commit. Preserve any existing tool-owned remote unchanged. Non-current tools default to observe/index plus the explicitly required pinned block; their memory bodies remain untouched.
- [ ] Extend the existing Shiguan checkpoint/archive contract so each worktree writes or backfills an independent metadata-first record at first use, phase acceptance, and terminal disposition. The record may reference child lifecycle and test evidence but cannot be replaced by them. Reuse `archive_checkpoint.py`, runtime evidence, and plan archives; do not add another store or service.
- [ ] Implement the minimal office loading contract entirely in the pure Skill/bootstrap/dispatch/checker path: fully read a compact root `SKILL.md`, fully read the compact exact-role dossier/profile, then add direct adjacency, bounded task/budget/worktree packet, registry hit, and only behavior-triggered extended references. Record actual relative paths, hashes, bytes, load/escalation reason, preload-ack latency, and first-report latency.
- [ ] Reserve expanded governing-reference/role-annex loading for behavior edits, semantic disputes, audits, releases, final semantic reload, or explicit escalation. The selected compact root `SKILL.md` remains fully read in every case. Prove every triggered governing reference is loaded; never trade correctness for the byte target.
- [ ] Do not create or depend on plugin manifests, caches, adapter skills, marketplace assets, plugin-only MCP/UI paths, or plugin-specific fallbacks. Pure Skill is the complete runtime and release baseline.
- [ ] After Task 3 migration and Task 4 shared-root acceptance, create task-point capsules only for structured executable child assignments: create-only inert capsule first, bind its relative path/detached SHA-256 and current runtime/charter/dispatch/role/superior/worktree/lease state in the existing admission record, reread that binding, then send the minimal envelope. Wake/status/heartbeat never create task-points.
- [ ] Before `running`, require the child to resolve under the shared root, hash and cross-check the capsule/current runtime, fully reread the compact root `SKILL.md` and exact-role dossier/profile, and return the complete binding/preload ack. Missing, revoked, stale, old-revision, wrong-bound or path-escaping capsules fail closed and never downgrade to pure pointer.
- [ ] Reuse `court_runtime.py`, `court_cli.py`, `archive_runtime_task.py`, `archive_checkpoint.py`, append-only court events and existing checks. Target envelope `<=800` UTF-8 bytes, capsule `<=1800`, resolver return `<=250`; claim context saving only when effective post-resolve input is `<=80%` of the inline baseline, otherwise use full inline assignment or label `reliability_only`.

Required matrix:

```python
assert targets("codex", []) == [agents_root, codex_root]
assert targets("claude-code", []) == [agents_root, claude_root]
assert targets("hermes", []) == [agents_root, hermes_root]
assert targets("unknown", []) == [agents_root]
assert targets("codex", ["hermes"]) == [agents_root, codex_root, hermes_root]
```

Run:

```powershell
python -B scripts/check_install_current_agent_copy.py
python -B scripts/check_court_office_assignment_binding.py
python -B scripts/check_court_dispatch_policy.py
python -B scripts/check_court_intake_gate.py
python -B scripts/check_court_runtime.py
python -B scripts/check_semantic_continuity.py --json
python -B scripts/check_court_preload_semantics.py
python -B scripts/check_catalog.py --strict
python -B scripts/ensure_court_agent_config.py --check
python -B scripts/check_court_capability_recruitment.py
python -B scripts/check_shiguan_host_memory_and_child_trace.py
```

Expected: all offices pass; Codex does not install, configure, enable, or rewrite Claude/Hermes memory bodies. Their only cross-tool write is the explicitly required, reversible in-place Git registration and pinned managed-link block after verified eligibility and compatibility.

### Task 6: Update the blank-host prompt, README/logs, and corrected release package

**Files:** update `INSTALL-PROMPT.md`, release docs/logs, package scripts, manifest, and staging tree.

- [ ] Keep `INSTALL-PROMPT.md` short. It must say:

  ```text
  On a blank host, first probe memory support read-only for each manifest-detected/selected tool,
  show enabled|disabled|unavailable|unknown with evidence, and ask before any write or enablement.
  Verify the package, install .agents, detect the current agent tool, install only that tool,
  add other tools only when explicitly requested, then create/check the shared Shiguan Git repository.
  Keep every verified tool's native memory at its original path, manage it as an independent local Git repository,
  and create isolated Obsidian projections plus verified pinned/reverse Shiguan links without copying memory bodies.
  Probe the effective config controller after current-tool resolution; unmet standards are REMINDER_ONLY,
  and configuration changes require a newest explicit permission and effective-file verification.
  ```

- [ ] Update `README.md`, `CHANGELOG.md`, `RELEASE-LOG.md`, and `docs/logs/2026-07-14-shiguan-install-remediation.md` with the actual accepted behavior. Update `docs/logs/README.md` to point to the latest entry.
- [ ] Keep logs short and sanitized; do not include raw Shiguan/runtime bodies, credentials, or machine-private content.
- [ ] Exclude host config/controller preimages, CC Switch databases and sidecars, backups, transaction journals, controller dumps, provider/auth values, and effective config files from the release payload. Tests use synthetic fixtures only; sanitized status may name paths and hashes but never secret values.
- [ ] Exclude host `.git` directories/git-dirs, object history, native memory bodies, repository receipts containing absolute private paths, and live Shiguan/native-memory commits from the release payload. Package only implementation, schemas, sanitized fixtures, and portable documentation.
- [ ] Mark existing `beta0.5.13\run1` and `run2` as rejected evidence without changing them.
- [ ] Stage corrected `beta0.5.13`, generate `release-manifest.json`, and build new no-clobber `run1b` and `run2b` ZIPs.
- [ ] Write SHA-256 sidecars outside the ZIP; do not place the ZIP's own digest inside `release-manifest.json`.

Run:

```powershell
python -B scripts/check_install_prompt.py
python -B scripts/check_package_privacy.py
python -B scripts/release_payload_manifest.py --check --json
python -B scripts/package_skill.py --out D:\project\release-packages\court-capability-router\beta0.5.13\run1b\court-capability-router-beta0.5.13.zip
python -B scripts/package_skill.py --out D:\project\release-packages\court-capability-router\beta0.5.13\run2b\court-capability-router-beta0.5.13.zip
```

Expected: both ZIPs are byte-identical, private Shiguan/Obsidian data is absent, and the package contains `INSTALL-PROMPT.md`.

### Task 6.1: Build one lossless updater and validate a local npm package after migration

This task remains strictly downstream of Tasks 3-4 migration/shared-root acceptance and does not change P00 priority. Build one updater mutation core with thin source-skill and npm CLI entrypoints; do not implement parallel updater logic, another state machine, or another package authority.

- The source skill exposes controlled `update|migrate` calls. Detect both legacy `court-capability-router` and canonical `Decretum Matrix`, then route both to the same physical skill/authority and updater core.
- The only write sequence is `backup -> staged atomic apply -> native reread -> authorized-root/five-root verification -> rollback receipt`. Produce a replayable JSON plan/receipt and restore the preimage on any failed apply, reread, hash, loader, or partial-root check.
- Task 7 `.agents + Codex` installation and the later final five-root convergence must use this same core. Default targeting remains `.agents + current tool`; five-root fanout occurs only under the existing final explicit authorization. The existing source installer becomes a thin updater entrypoint rather than a second implementation.
- Add a cross-platform npm CLI/package whose explicit `update|migrate` commands invoke the same logic and receipt schema. This run performs no `npm publish`, remote, tag, or external release. Create a no-clobber local `.tgz` and verify explicit local `npm exec --package <local.tgz>` / `npx --package <local.tgz>` invocation on Windows/macOS/Linux fixtures. Future one-command npm updates must reuse the accepted core.
- Do not use implicit or dangerous `postinstall`. Never overwrite, migrate, stage, or package the shared Shiguan, `pending/**`, private/raw evidence, native memory bodies, Obsidian private state, or unauthorized controller/config files. Legacy entrypoints are deprecated compatibility routers only.

**GREEN:** One core produces equivalent source-entry and npm-entry receipts for legacy/canonical detection, backup, staged apply, atomic replace, native loader/version reread, per-file hashes, authorized target selection, and rollback. Add a focused behavior checker without duplicating the updater.

**SPEC:** `update` and `migrate` are bounded modes over one target/provenance/backup/apply/verify/rollback contract. Preserve `.agents + current tool`, explicit extra-tool/five-root authority, Decretum Matrix single authority, package privacy, P00 bounded receipts, and controller-first config ownership. npm is a transport, not a behavior source.

**QUALITY:** Cover Windows/macOS/Linux paths, long paths, permissions/file occupancy, legacy migration, version upgrade/downgrade, idempotent replay, killpoint rollback, bad package/hash, native reread failure, partial five-root failure, and zero implicit postinstall mutation. The local `.tgz`, ZIP determinism/privacy/no-clobber, clean-index, no-`.pyc`, and no-remote/no-publish gates all pass.

**Final acceptance:** The actual host install and final five-root sync are accepted only from this updater's receipts plus native reread and per-file hash equality. Rollback remains executable; shared Shiguan/pending/private/memory/unauthorized config stay unchanged; legacy routing resolves to the canonical authority. This run closes with local `.tgz` evidence only and publishes nothing.

### Task 7: Install this host and run final acceptance

This task remains blocked until Tasks 2–6.1 pass.

- [ ] Back up `.agents`, the detected current-tool target, and only the canonical entrypoint/Git metadata needed to roll back each eligible native memory repository. Do not duplicate full native memory bodies merely for link binding.
- [ ] Install the verified staging payload to `.agents + Codex` only:

  The command below must be the thin source entrypoint to the Task 6.1 updater core and must emit the same backup/apply/reread/verify/rollback receipt used by the npm CLI; a legacy direct-copy implementation does not pass.

  ```powershell
  python -B scripts/install_current_agent_copy.py `
    --source D:\project\release-staging\beta0.5.13 `
    --current-tool codex `
    --write `
    --json
  ```

- [ ] Verify `.agents` and Codex report `beta0.5.13` and matching portable hashes.
- [ ] Verify Claude/Hermes skill/config/body hashes are unchanged except for the exact approved pinned managed-link path and local Git metadata; no memory store moved and no feature was enabled.
- [ ] Verify the shared Shiguan exists only under `.agents`; the old path is only a junction.
- [ ] Verify the shared Shiguan is one local-only Git repository with distinct record/memory lifecycles, allowlisted tracking, append-only committed records, no remote, and a clean index.
- [ ] Verify the Obsidian vault path and preserve-only result.
- [ ] Verify every manifest-eligible installed tool in the open class set retains its native memory path and has an independent Git repository, registered repo/pathspec/HEAD/state/write-policy receipt, no submodule/subtree/nested tracking/shared-repo body copy, and a clean index. New repos have no remote; any existing tool-owned remote is byte/semantically unchanged and no network operation occurred. Verify exactly one pinned Shiguan link and one reverse namespace link with matching paired commit receipts; otherwise report `LINK_BINDING_BLOCKED` and do not claim migration complete.
- [ ] Verify every eligible installed tool class has exactly one isolated Obsidian metadata/index namespace and graph, with no cross-tool nodes/edges. Source bodies are unchanged outside the managed block and approved tool-native/current-tool note paths; no private raw body, Git object history, or release package appears.
- [ ] Verify the blank-host fixture produces a read-only memory/Git-compatibility probe receipt and user prompt before shared-root/Git/init/enable/install writes, uses only enum states with evidence, fails closed on automatic enablement for `unknown`, and leaves Claude/Hermes/other unchanged outside the approved in-place Git/pinned-link contract.
- [ ] Verify blank-host config fixtures produce non-blocking `REMINDER_ONLY` without a compliance claim when unmet/unapproved/uncertain; controller-owned Codex rejects leaf-only or DB-only success, preserves unknown/provider/secret fields, and passes only from compatible `config.toml` + `managed_config.toml` reread/parse plus an available runtime probe. Verify the no-CC-Switch path and Hermes upstream-failure fallback gates.
- [ ] Verify protected cross-conversation files remain at their original paths and hashes.
- [ ] Verify `run1b` and `run2b` hashes match and `run1/run2` remain unchanged.
- [ ] Verify `git diff --cached --name-only` is empty.
- [ ] Verify the pinned initial semantic load and one-to-one office loading/dispatch contract.
- [ ] Verify the current court task can be revised/resumed without creating another task and must re-enter 三省 before 六部 execution.
- [ ] Verify every legal `WRITE` carries `adjudication_status=approved`, stable `decision_id`, Menxia receipt, newest applicable write/target authority, adapter result, native reread, and matching shared/native `transaction_id`; no Git/Obsidian/native queue/file-presence evidence is accepted as semantic approval.
- [ ] Verify historical memory decisions are immutable and every correction appends a superseding decision. Candidate-only reevaluation and tidy operations cannot silently change a verdict.
- [ ] Verify every participating worktree has a separate Shiguan record with stable identity, approved write set, index/pyc evidence, RED/GREEN/SPEC/QUALITY pointers, recovery anchor, and `integrated|retained|retired|blocked` disposition; no record contains full prompts/diffs/private bodies.
- [ ] Verify representative role-local routine preloads meet the minimum contract and measured target, every escalation loads its required governing references, and no runtime/package surface contains or requires a plugin artifact.

Final gates:

```powershell
python -B scripts/quick_validate.py .
python -B scripts/check_catalog.py --strict
python -B scripts/check_portability.py
python -B scripts/check_install_prompt.py
python -B scripts/check_install_current_agent_copy.py
python -B scripts/check_court_office_assignment_binding.py
python -B scripts/check_court_dispatch_policy.py
python -B scripts/check_court_intake_gate.py
python -B scripts/check_court_runtime.py
python -B scripts/check_semantic_continuity.py --json
python -B scripts/check_court_preload_semantics.py
python -B scripts/check_shiguan_host_memory_and_child_trace.py
python -B scripts/check_court_memory.py --json
python -B scripts/check_package_privacy.py
python -B scripts/release_payload_manifest.py --check --json
git diff --check
git diff --cached --name-only
```

Required independent verdicts:

```text
RED demonstrated
GREEN passed
SPEC PASS
QUALITY READY YES
MEMORY_ADJUDICATION_V2 PASS
COMPLEXITY BUDGET PASS
Git index empty
```

These gates complete the pre-audit whole-insertion acceptance, but the parent plan must not resume until Tasks 8 and 10 also pass.

### Task 8: Run the macOS platform/package gate before the final repository audit

This platform/package gate runs only after RED, GREEN, SPEC, QUALITY, and the existing whole-insertion acceptance. It does not move ahead of or weaken the Shiguan-migration-first order, and it does not replace Task 10's final repository audit.

- [ ] Prefer proof that the same release package and installation logic work on macOS. If that cannot be proved, build a separately named no-clobber macOS package and accept it independently.
- [ ] Run a Darwin clean-home fixture using POSIX-relative persisted paths and prove there is no Windows Registry, MSI, backslash-persistence, or drive-letter assumption.
- [ ] Prove the macOS result still has one `.agents/court-shiguan/court-capability-router/references` physical Shiguan root and defaults to `.agents + current tool` only.
- [ ] Re-run package privacy checks and emit per-file plus package SHA-256 manifests for the accepted same-package or separate-package result.
- [ ] Record actual Darwin evidence, same-package/separate-package decision, privacy result, and hashes in README/release docs/`docs/logs` for every version iteration. This C5 wave changes only the two A02 plans and does not edit those files.
- [ ] Sign the final package as `RowlandL <3289324701@qq.com>`. The default open-source option is Apache-2.0 with `LICENSE`, `COPYRIGHT`, and `NOTICE`; preserve attribution/license/NOTICE and include the statement “学习交流、非官方售卖渠道、禁止冒充官方或移除署名” without turning it into an additional enforceable no-commercial-resale restriction on Apache-2.0.
- [ ] An OSI open-source license cannot carry an additional legally enforceable commercial-resale ban. If the user's final choice still requires enforceable no-resale, obtain a newest explicit choice and any necessary legal review before release, switch to a noncommercial/source-available custom license, and label the release `NOT_OPEN_SOURCE`. Never publish Apache-2.0 and “禁止转卖” as simultaneously operative contradictory terms.

Only after `FINAL_MACOS_RELEASE_GATE=PASS` may Task 10 run. Final Shiguan closeout and parent Task 3 GREEN still wait for `FULL_AUDIT_PASS` or `FULL_AUDIT_REMEDIATION_COMMITTED_LOCAL` plus every remaining A02 gate.

### Task 9: Execute the project-scoped root-control governance resume gate

A later explicit instruction paused A02 at the `20260715-175826` recovery point and authorized this local governance task before A02 resumes. This task changes no A02 business semantics, pending data, or release output. Installed roots remain immutable except that a missing protected anchor may be restored byte-for-byte from a verified snapshot to its original path and original SHA-256; no regenerated substitute is allowed. Optional reference skills remain `$github-init` and `$github:github`; they authorize no remote, push, tag, release, PR, or publication action.

- [x] Initialize `D:\project` itself as the local root control repository and single new Codex project entry. Baseline commits are `58cd9f9` and `de715f3`; root has no remote and a clean staged diff.
- [x] Track only the control plane, governance docs/templates, selected evidence metadata, and asset inventory. Ignore independent child repositories, real release/recovery/staging bodies, live `.codex/config.toml`, runtime task state, and child worktrees.
- [x] Add dependency-free `workspace.yaml` + JSON Schema and generic `repo-control`; adding a future project is a manifest-only operation. Keep branches, versions, publishability and paths project-owned.
- [x] Keep every child repository's common-dir, history, branches, tags, CI, licensing, security policy, and release lifecycle independent. Forbid submodules and ordinary nested-repository tracking.
- [x] Create real child code worktrees under `D:\project\worktrees\<project-id>\<task-id>` and expose them through a root task's ignored `attached/<project-id>` junction/symlink. Each child worktree connects only to its own common-dir.
- [x] Prove a user-owned Codex Worktree task under the single root project can visibly operate UU without registering UU again: task `019f6585-fa75-7ec0-98dd-1011401b3dbe`, child path `D:\project\worktrees\uu-remote-cli\root-ui-smoke-20260715`, branch `work/root-ui-smoke-20260715`, common-dir `D:\project\uu-remote-cli\.git`.
- [x] Leave Codex's global managed-worktree setting unchanged. `D:\project\worktrees` is a project-level real-code policy, not a whole-machine setting.
- [x] Use per-project/per-task atomic state and immutable event records; do not recreate a shared writable `tasks.json` failure mode. The ledger remains routing metadata and never replaces a worktree Shiguan record.
- [x] Verify root `repo-control doctor=PASS`, controller tests `7/7 PASS`, `github-init inspect` clean, no tracked sensitive path, and no remote/publication action.
- [x] Finish and independently verify the visible child governance branches, then integrate only the accepted commits: Court `main=b7b2b440cb53bdc26ba53af676ef9c75f070183a`; UU `main=cb43a2d92acfed3030af00546b1d0056b90469ec`.
- [x] Refresh the root version/branch ledger and inventory at `root main=8d6b056412395c3dcd12fab5733b0d55cdb22f88`; verify Court `beta0.5.9`, UU `0.0.1`, root/Court/UU remote count `0`, staged diff empty, and the Court `work/a02-baseline` history-secret publication block.
- [x] Restore the four protected installed Shiguan anchors byte-for-byte from the matching local legacy snapshot after a read-only check found them absent. Verify the original paths, sizes, and all four recorded SHA-256 values; do not regenerate them or touch `pending/**`.
- [x] Revalidate the recovery package at `92/92` hashes and checkpoint SHA-256 `740C42C3021435794B02AFF3CFCEFF7C69755B6B2E0A92D1632DDCA092CC8060`; backfill 25 independent metadata-first worktree records with 25 unique trace ids, 25 valid index entries, required fields, terminal dispositions, independently verified `.pyc=0`, and empty indexes. Root closeout is `b3eada2a62922a9cd4a3538e6713c82565f5ea54`. Menxia verdict: `PHASE8_REPOSITORY_GOVERNANCE_VERDICT=PASS`, `A02_PHASE1_RESUME=ALLOWED`. Resume the existing A02 Phase 1 task; keep dirty worktrees until integrated or given a traced terminal disposition.

Acceptance: the root controller and both child repositories pass their local checks; future projects are manifest-extensible; visible worktree tasks require only the root Codex project; actual child worktrees live under the project-scoped physical root and map to exactly one child common-dir; no global Codex setting, direct Codex state database, remote, or publication was changed. After acceptance, resume A02 immediately and do not extend this governance phase with low-value polish.

Acceptance result: `PASSED`. The temporary repository-governance pause is cleared; continuation returns to the existing A02 Phase 1 and does not resume parent Task 3.

The workspace-governance acceptance does not replace the A02 worktree evidence gate: every participating worktree must also have an independently replayable metadata-first Shiguan record and terminal disposition before final closeout.

### Task 10: Run the final full-repository specialist audit and release-stage remediation gate

Run this task after Tasks 1-8, V2 memory-adjudication remediation, phase/cluster RED-GREEN-SPEC-QUALITY, and platform/package checks, but before final acceptance/publication judgment, final Shiguan closeout, or parent Task 3. Task 9 governance remains the already-passed prerequisite. Discovery is read-only and must not modify the current A02/release/main branch.

- [ ] Fan out bounded read-only A-G specialists over root `SKILL.md` and direct governing references; every standing TOML and supercc dossier; scripts, CLI/wrappers, services/daemons, bridge/index/registry/migration/install/package paths; checkers/fixtures; README/install/CHANGELOG/release docs/manifests; and Windows/macOS/Linux path, shell, Python, rollback, and evidence behavior.
- [ ] Quantify duplicated/near-duplicate rules, ambiguous subject/condition/default/stop semantics, cross-source conflicts and stale rules, duplicate/orphan/unreachable CLI paths, planned-but-unimplemented, implemented-but-uncalled, fixture-only production claims, production-without-test gaps, and security/privacy/Git/Obsidian/native-memory/cross-platform boundaries.
- [ ] Verify Section 0.5 and the earlier RC2/RC4/RC6 receipts cover numbering, frozen lineage, operation replay, closeout recovery, authority-root binding, and child/worktree lifecycle. If any part is absent, return the finding to its original cluster; do not first implement it in this final audit task.
- [ ] Require the common finding schema from every reviewer. Menxia alone deduplicates and adjudicates `ACCEPTED|REJECTED_FALSE_POSITIVE|DEFERRED|SUPERSEDED`; Shangshu groups only accepted findings into dependency/write-set clusters.
- [ ] If `ACCEPTED findings=0`, emit `FULL_AUDIT_PASS` with specialty coverage and create no empty branch, worktree, or commit.
- [ ] If `ACCEPTED findings>0`, use root repo-control or its manifest-safe equivalent to enter the clean child worktree under `D:\project\worktrees\court-capability-router\<task>` for the current major stage; its branch must be the current `release/beta0.5.x`, not a separate `codex/...` product-remediation branch.
- [ ] On that release worktree only, run each cluster through minimal RED, single-owner GREEN, matching specialist rereview, SPEC, QUALITY, and whole-repository regression. Stage only approved pathspecs; preserve unrelated dirty state; require empty indexes before and after every acceptance gate.
- [ ] Create one bounded local stage commit under Section 2.2 and report branch, commit, tests, and remaining findings; when there is no file delta, reuse accepted HEAD and create no empty commit. Do not push, open a PR, tag, release, publish, auto-merge, or fast-forward during Task 10. Task 11 completes the clean-package and next-release-branch steps of the same final major-stage loop.

Run:

```powershell
python -B scripts/check_full_repository_audit.py --json
git diff --check
git diff --cached --name-only
```

Required result: `FULL_AUDIT_PASS` or `FULL_AUDIT_REMEDIATION_COMMITTED_LOCAL`. A blocked or incomplete audit prevents Task 11, final closeout, and parent Task 3.

### Task 11: Converge the latest branch, final package, five installed roots, and Shiguan system

This is the last local acceptance task. It runs only after Task 10 and all accepted clusters pass. It does not authorize any remote publication.

- [ ] From the accepted Task 10 commit, use its clean child worktree and confirm every accepted A02 change is converged in adjudicated order. Preserve unrelated dirty worktrees and run the full cluster/repository regression on that exact commit.
- [ ] Update README, CHANGELOG, RELEASE-LOG, docs/logs, release/identity manifests, LICENSE/COPYRIGHT/NOTICE and version evidence from actual results. Current product metadata must say `Decretum Matrix（诏令矩阵）` / `decretum-matrix`; `DecreeMatri` is absent from current identity surfaces and old `court-capability-router` names are limited to the locator/history/deprecated-input allowlist. Rebuild no-clobber deterministic `run1b/run2b` only from that clean worktree; require byte-identical packages, per-file/package hashes, privacy checks, and unchanged old run1/run2 plus beta0.5.12. After package verification and the Section 2.3 previous-version terminal outcome, create the next sequential `release/beta0.5.(x+1)` child branch/worktree from the same commit, mirror only its mapping metadata, and complete Section 2.4 auto-handoff.
- [ ] Back up and install/upgrade the accepted portable skill to exactly five technical locator roots: `~/.agents/skills/court-capability-router`, `~/.codex/skills/court-capability-router`, `~/.claude/skills/court-capability-router`, `~/.hermes/skills/court-capability-router`, and `user_data_base()/hermes/skills/court-capability-router`. Every loader must expose canonical `decretum-matrix` / `Decretum Matrix（诏令矩阵）`; no duplicate alias directory is installed. This newest explicit authorization covers skill bytes only, not config changes, memory enablement/body writes, unknown tools, or remote operations.
- [ ] Verify all five roots expose the same `VERSION`, identity/release manifests, canonical name/display, and allowlisted per-file SHA-256, and pass `check_active_copy_hashes.py`, the name-surface checker, and each tool's effective loader/runtime probe. Directory existence alone is insufficient.
- [ ] Run `SHIGUAN_LATEST_SYSTEM_GATE`: the one physical `.agents` Shiguan, LocalAppData junction, shared Git, schemas/indexes, runtime/CLI/checkers, bridge/daemon/service, Obsidian registration/projection, native-memory links, worktree records, and recovery/paired receipts must match the final branch/package manifest and be usable. Reject stale services/code/schema, a second physical root, broken links, dirty indexes, or incomplete migration.
- [ ] Preserve the pending-body, quiescence, privacy, protected-file, controller/config, and no-remote gates. Current `pending_count=69` blocks this task's migration/system-pass claim until lawfully cleared; do not inspect or bypass bodies.

Required final results:

```text
LATEST_BRANCH_CONVERGED
DECRETUM_MATRIX_IDENTITY_GATE=PASS
FINAL_PACKAGE_VERIFIED
FIVE_ROOTS_LATEST_HASH_EQUAL
SHIGUAN_LATEST_SYSTEM_GATE=PASS
all affected Git indexes empty
remote publication not run
```

## 3. Stop conditions

Stop immediately if:

- an active conversation still owns any record or ownership is unknown;
- the metadata-only pending count is nonzero or unknown;
- the two quiescent scans differ;
- source metadata changes before or during cutover;
- the source/target are not the same volume, the source directory file-id changes, or the metadata inventory differs;
- a target/reparse point already exists or a junction target is unexpected;
- the target resolves outside `.agents`;
- a protected cross-conversation file would move or change;
- Obsidian CAS conflicts or preserve-only sync would remove a file;
- current-tool detection is ambiguous;
- the installer plans an unrequested tool;
- an existing-host memory projection is attempted before verified Shiguan migration;
- the install projection/manifest is missing, ambiguous, derived from full-host scanning, or cannot prove the projected tool class actually has this skill installed;
- a memory projection merges namespaces, nodes, or edges across `codex`, `hermes`, `claude-code`, or stable `other:<id>`;
- an eligible tool is rejected merely because it is not Codex/Claude/Hermes, or lacks a stable `other:<stable-id>` adapter;
- a verified tool memory is migrated/copied into the shared Shiguan repo, changes its effective native path, is not an independent Git repository, becomes a submodule/subtree/nested tracked repo, gains a Shiguan-created remote, has an existing remote changed/used, leaks native git-dir/objects into shared/Obsidian/package output, or lacks repo/pathspec/HEAD/state/write-policy evidence;
- a Git checkpoint stages unrelated dirty paths, rewrites existing history, leaves either index dirty, or claims cross-repository atomicity without paired receipts;
- a shared Shiguan registry entry or native pinned block lacks the reciprocal repo id/namespace/pathspec/commit/transaction id, points to an unregistered repo, is orphaned/stale, or fails readback; physical cutover alone cannot pass this gate;
- a projection/probe reads or writes a source memory body outside the managed block/tool-native/current-tool-authorized path, omits required metadata evidence, or includes a private raw body, Git object history, or release package;
- `memory_decision=WRITE` lacks `adjudication_status=approved`, `decision_id`, `menxia_receipt`, newest applicable write/target authority, adapter result, native reread, or matching `transaction_id` receipts;
- a Git commit, Obsidian projection, native approval queue, file existence, candidate-only reevaluation, or expected-failure checker is treated as a Menxia semantic verdict;
- any tool rewrites a historical memory decision in place rather than appending an explicit superseding decision;
- a blank-host path creates the shared root, initializes any Shiguan/native-memory Git, enables memory, or performs an install write before the read-only enum/evidence probe and user prompt;
- `unknown` is automatically enabled, or Claude/Hermes/other is installed, configured, enabled, or body-written without newest explicit authorization beyond the already authorized in-place Git/pinned-link contract;
- any tool configuration is mutated without newest explicit config-change authority, or a release/log/test artifact captures a real config/controller preimage, CC Switch DB/sidecar/backup, credential, provider/auth value, or secret-bearing effective file;
- a proposed change is rejected by `complexity_budget_gate`, exceeds the user-explicit boundary, or is low-value relative to current budget;
- the package contains real Shiguan data, private Obsidian state, credentials, raw logs, pending imports, or memory bodies;
- `run1b` and `run2b` differ;
- Task 11 does not converge every accepted change on the exact accepted child release commit, the final package is not built from its clean worktree, the next sequential child release ref is not created from that commit, or old preserved artifacts change;
- any of the five authorized skill roots is missing/stale, differs in version or allowlisted file hashes, fails its effective loader probe, or the installer changes tool config/memory/body state;
- `SHIGUAN_LATEST_SYSTEM_GATE` finds stale runtime/CLI/service/schema, a second physical store, an incorrect junction, broken Git/Obsidian/native-memory/worktree/recovery links, a dirty index, or a final-manifest mismatch;
- the project/release Git index becomes non-empty, or any managed data repository remains dirty after its scoped checkpoint.
- a specialist reviewer mutates files, a non-Menxia role issues the aggregate adjudication, Shangshu dispatches a non-accepted finding, or a repair cluster has overlapping writers;
- Task 10 discovery mutates the current release worktree, creates a separate product-remediation branch or empty commit, stages outside approved pathspecs, auto-merges/fast-forwards, or performs any remote/PR/tag/release/publication action;
- a routine office path or release artifact depends on or creates a Codex plugin, plugin cache, plugin-only manifest/MCP/UI surface, or second semantic entrypoint.
- a pure Shiguan pointer authorizes execution, a task-point capsule is accepted without current runtime/hash/role/superior/worktree/lease/preload binding, an old revision/attempt reactivates, or the implementation adds a second authority/store/service.
- a worktree carrier bypasses exact-role/semantic/budget/write-set/result binding, duplicates an authority/writer, connects the wrong common-dir, or lacks its own Shiguan worktree record;
- superCC is not disclosed as experimental CLI-only before selection, is inferred from ordinary super/parallel/history/config, or any superCC annex/profile/script/watchdog/daemon/visible-office state loads while it is not explicitly active;
- any current user-facing or machine identity surface disagrees with `Decretum Matrix（诏令矩阵）` / `decretum-matrix`, the withdrawn `DecreeMatri` remains current, a remaining `court-capability-router` occurrence is outside the approved technical-locator/history/deprecated-input allowlist, compatibility is falsely claimed, a duplicate alias skill/package authority is created, or a protected path/hash or Git/worktree/recovery/Shiguan lineage changes because of the rename;
- any dispatch/result/apply/commit/resume/closeout lacks the current semantic receipt, a stale result is silently rebased/applied, correction leaves an old binding/agent/capsule/attempt active, a mutation proceeds while drifted/unverified, or a second semantic epoch/state authority is created.
- the same operation produces a second allocation/archive/index/task/event side effect, a `record_uid` collides, decree-open reallocates a main code, historical `court_code` changes without an explicit append-only reclassification, child/worktree lineage drifts, a worktree lifecycle is absent, or task/event/archive/index receipts diverge;
- the authority realm/root fingerprint mismatches or cannot be proven, or the operation requires cross-host/NFS/SMB/distributed-lock semantics. These cases fail closed as `BLOCKED|UNSUPPORTED`; they never justify SQLite, HTTP, MQ, a second ledger, or per-worktree tasks/events.

Configuration-scoped stop: if controller ownership, DB schema, effective precedence, current values, semantic compatibility, backup/rollback, actual-file reread/parse, or the available runtime probe cannot be proven, stop or roll back only that config branch, emit `REMINDER_ONLY` with the exact uncertainty and `compliance_claimed=false`, and continue unaffected work. A leaf-only TOML patch or DB-only verification never satisfies this branch.

## 4. Completion contract

The remediation is complete only when:

```text
one physical Shiguan store exists under .agents
old LocalAppData path is a junction to it
the shared Shiguan store is one local-only Git repository with no remote, allowlisted tracking, append-only committed records, separate memory lifecycle, and a clean index
pending body count was zero before cutover and no pending body was opened, read, hashed, copied, moved, deleted, or marked-seen
active conversations were zero on two stable scans before migration
Obsidian registers the .agents shiguan-tree and removes zero files
.agents is installed
only the current tool is additionally installed by default
install projection/manifest is the sole eligibility source; no full-host memory/tool scan occurs
codex, claude-code, and hermes are built-in examples rather than a closed set; every additional verified tool uses stable other:<stable-id> under the same contract
every manifest-proven installed tool keeps its native loader path and is managed as an independent Git repository with repo/pathspec/HEAD/state/write-policy receipt; no native memory migration, shared-repo body copy, submodule, subtree, or nested tracking occurs; new repos have no remote and existing tool-owned remotes remain unchanged and unused
the shared Shiguan Git repository is the management hub and links every native memory Git repository through one stable registry entry plus reciprocal pinned link; repo ids, namespaces, pathspecs, commits, and transaction ids match on both sides
each native memory repository and the shared Shiguan repository have matching paired commit/link receipts; only approved pathspecs were staged and all affected indexes are clean
every manifest-proven installed tool class has its own Obsidian metadata/index namespace and graph with no cross-tool nodes or edges
every eligible native memory entry has exactly one top-pinned shared-Shiguan/tool-namespace link and each namespace has the verified reverse native-path/repository-HEAD link; every tool must pass MIGRATION_LINKS_VERIFIED, while LINK_BINDING_BLOCKED prevents completion and CUTOVER_VERIFIED alone is not migration completion
source MEMORY/memories remain tool-authoritative; outside the managed block, tool-native writes, and separately authorized current-tool update-note their bodies are unchanged; projections contain only relative source ids/paths, repository HEADs, fingerprints, states, headings/topics/relations and exclude private bodies, Git histories, and release packages
semantic_adjudication, write_authority, and native_application are independently evidenced and cannot substitute for one another
every WRITE has adjudication_status=approved, stable decision_id, Menxia receipt, newest applicable authority, native reread, and matching transaction receipts
historical memory decisions are append-only and every correction carries supersedes
body mirroring remains blocked pending a later explicit decree and Menxia privacy review
blank-host setup probes every manifest-detected/selected tool read-only before any shared-root, Shiguan/native-memory Git init, memory-enable, or install write; it shows enum state, native path/repository evidence, and a user prompt
unknown is not auto-enabled and Claude/Hermes/other receives no unauthorized install, config, enablement, or body write beyond the approved in-place Git/pinned-link contract
blank-host config targets are normalized as codex|claude-code|hermes|other:<stable-id>; unmet, unauthorized, or uncertain standards remain non-blocking REMINDER_ONLY and never claim compliance
authorized Codex config change is controller-aware and reversible, preserves secrets/provider/unknown fields, keeps config.toml and managed_config.toml semantically compatible, and passes only on effective-file reread/parse plus an available runtime probe, never DB alone
release packages exclude actual host configs, controller databases/sidecars/backups/journals/dumps, provider/auth values, and config preimages
all office TOML/dossiers accept the same name/profile/skill semantics
Decretum Matrix（诏令矩阵） is the only canonical user-facing identity; decretum-matrix is the canonical skill name/invocation, DecreeMatri is absent from current identity surfaces, and every court-capability-router occurrence is allowlisted as a technical locator, history, or deprecated compatibility input
all persisted profile/dossier/skill paths are normalized relative paths
pinned initial semantic load is present, early, sufficient, and single-source
Taizi/Three-Departments load audit and coordination duties; ministries/workshops load execution duties
every spawned child loads and acknowledges its exact role AGENTS.md before running
resume/correction continues the existing task and re-enters Three Departments
semantic_epoch equals charter_revision; current charter/capsule receipt binds every dispatch, result, apply, commit, resume, and closeout
correction revokes all stale derived/binding/agent/capsule/attempt state, quarantines late results, and forces ThreeDepartments re-entry
compaction/resume/reboot/long-idle and plan/Git/recovery evidence pass the same drift detector; SEMANTIC_CONTINUITY_GUARD PASS
every participating worktree has a separate metadata-first Shiguan record and terminal disposition; child traces and workspace ledgers are pointers, not substitutes
routine office loading is role-local/on-demand through the pure Skill path, meets the measured target when safe, escalates every required governing reference, and contains no plugin dependency or artifact
child_agent and worktree_thread carriers have equivalent task/role/hierarchy/budget/write-set/preload/semantic/communication/result receipts without duplicate authority/writer
decree-open assigns one immutable main_court_code per decree and only explicit reclassify advances lineage_version; historical court_code values remain unchanged
default 16 means root plus 15 children, explicit 17 means root plus 16 children, and explicit 18 means root plus 17 children; the explicit count is never treated as child slots
the 32-process allocator uniqueness regression passes and 32 concurrent replays of one operation produce exactly one allocation/archive/index/task/event side effect
PREPARED -> ARCHIVE_COMMITTED -> TASK_EVENT_COMMITTED recovers exactly once across allocation/archive/index/task/event killpoints through closeout-recover --operation-id
at least two child_agent and two worktree_thread cases have isomorphic admit/start/report/finish/close schemas; worktree adds only thread_id/worktree_fingerprint/branch/start_head proof
authority realm/root mismatch fails closed on Windows/macOS/Linux local filesystems; cross-host/NFS/SMB/distributed locking remains DEFERRED or UNSUPPORTED
operation/context payloads contain hashes, relative paths, and evidence pointers only, with no full prompt, diff, private body, or pending body
superCC is disclosed as experimental CLI-only and activates/loads only from the newest explicit superCC selection; its annex/runtime surface remains unloaded otherwise
pure Shiguan pointers are rejected; the hybrid envelope/capsule path is current-runtime/hash-bound and acknowledged before running
canonical court_code remains unchanged; independent task-point sequence/revision/attempt is collision-free and revoked state cannot reactivate
task-point false accept, post-revoke activity, unauthorized scope escape, and duplicate execution are zero; p95 resolve/read/hash/binding is <=1000 ms after at least 30 samples
task-point savings claims include effective post-resolve chars/UTF-8 bytes and satisfy the 80% break-even rule; capsules contain no pending/private body, full prompt/diff/private log, plugin, database, daemon, or second store
README and docs/logs are updated for this version iteration
beta0.5.13 run1b/run2b are deterministic and authoritative
beta0.5.13 run1/run2 and beta0.5.12 remain preserved
all accepted changes are converged on local release/beta0.5.13 and the final package is built from that exact branch
the five authorized technical locator roots report the same latest VERSION, identity/release manifests, Decretum Matrix/decretum-matrix identity, allowlisted per-file hashes, and effective loader/runtime success, with no duplicate alias skill
SHIGUAN_LATEST_SYSTEM_GATE PASS: the migrated one-root Shiguan runtime, schemas, services, Obsidian, Git/link, worktree, and recovery evidence match the final manifest
specialist findings use the common schema; Menxia is the sole aggregate adjudicator and only accepted repair clusters are dispatched
FULL_AUDIT_PASS or FULL_AUDIT_REMEDIATION_COMMITTED_LOCAL
any full-audit remediation commit remains on the applicable child release branch; only a later Section 2.3 receipt may authorize exact previous-version remote actions
SPEC PASS
QUALITY READY YES
complexity_budget_gate PASS
project/release Git index empty and every managed data repository clean after its scoped checkpoint
network calls zero
remote publication not run
```

`CCR-R2-SHIR-20260714-A02` is `APPROVED_EXECUTION_ACTIVE`. Execute in the stated order, preserve cluster/phase-level TDD review, and do not resume the parent Task 3 until Task 11 and every insertion gate pass. The known pending-body hard stop remains in force.

## 2026-07-16 Decretum Matrix legal/provenance pointer

- Governing detail: `docs/plans/2026-07-16-decretum-matrix-dual-license-rights-and-provenance-plan.md`; do not duplicate that plan here.
- Cursor: `R0_LOCAL_RENAME_POST_FINGERPRINT -> P0_LEGAL_PREIMAGE_INVENTORY` on `D:\project\decretum-matrix-beta0.5.10`.
- Acceptance overlay: local rename/mapping, permanent upstream MIT provenance, future `AGPL-3.0-only` architecture, CLA/trademark/legal package, protected hashes, pending-body zero access, index-empty, and new-name staged-publication gates are mandatory before package/publication closeout.

## Post-A02 Office Identity Pack / DLC / Scope queue

- Governing detail: `docs/plans/2026-07-16-decretum-matrix-office-identity-pack-dlc-and-scope-plan.md`; do not duplicate it here.
- Cursor: `A02_ACCEPTED_COMMIT -> CLEAN_PACKAGE -> PER_RELEASE_LOCAL_INSTALL/MIGRATION/INDEX -> NEXT_RELEASE_HANDOFF_ACCEPTED -> MAINLINE_ACCEPTED_BASELINE_GATE -> POST_MAINLINE_REBASE/P0 -> OFFICE_PACK_Q0`.
- Acceptance: P0 must rebase every path/schema/topology assumption onto the final accepted baseline; this queue is plan-only and does not implement pack/DLC/scope/knowledge promotion now.
- Acceptance: plan-only until the cursor is reached. Shared global defaults may later reuse the one shared Shiguan Git manifest domain, but must not create a second repo/ledger/authority or override the Decree Kernel; no implementation or pending-body access is authorized in the current A02 release.
