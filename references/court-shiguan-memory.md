# Shiguan And Memory / 史馆与记忆

渐进加载注记：本卷由原 `SKILL.md` 顶级章节机械迁移而来，保留原文语义用于按需加载。新的短 `SKILL.md` 是入口、硬门禁与直接索引；本卷是该入口直接链接的 governing reference。若旧文出现“必须写入 SKILL.md”等位置性表述，在本次渐进加载结构下解释为：硬门禁、触发、三权、只读、安全、状态机、史馆/记忆、语义再载入、奏报模板等规则必须在短 `SKILL.md` 保持摘要和直链；细节规则可写入本卷等直接链接 governing reference。史馆仍只作证据与召回锚点，不替代本 skill 源文件与 governing references。

原始来源：`SKILL.md` sha256 `64c7a9089275de004bbd2fc4e9c59633d2bbfe9e2a355178816c3da65f6563c9`。本卷章节：`Shiguan Lineage And Court Code`, `史馆实录`, `Memory Decision Gate`。

## Contents

- [Shiguan Lineage And Court Code](#shiguan-lineage-and-court-code)
- [史馆实录](#史馆实录)
- [Token Three-Level Optimization / 令牌三级优化](#token-three-level-optimization--令牌三级优化)
- [Codex/Hermes Internal Memory Bridge](#codexhermes-internal-memory-bridge)
- [Memory Conflict Downgrade Rules](#memory-conflict-downgrade-rules)
- [Memory Decision Gate](#memory-decision-gate)

## Moved Source

## Shiguan Lineage And Court Code

史馆分类 must use content, not action labels. Do not classify the growth tree by
`记忆裁定`, `兵部实现`, `门下复核`, or other workflow phases. Keep those as record
fields only. Use a content lineage like:

```text
史馆总纪 -> 志 -> 门 -> 纲 -> 目 -> 条 -> 诏 -> 实录
```

The display lineage should use meaningful names at every layer, similar to
biological taxonomy:

```text
史馆总纪·朝制志·官署门·三省六部纲·递归差遣目·星图交互条·右键菜单诏
```

Classification follows a local knowledge-organization rule informed by common
classification methods: a controlled vocabulary for consistent retrieval, a
hierarchical trunk for the main content tree, and facet fields for orthogonal
properties. Therefore:

- Main lineage fields (`志/门/纲/目/条/诏`) describe what the record is about.
- `星图` and `树图` are only two presentation modes for the same official
  content lineage. They must use the same trunk nodes and ordering; they may
  differ in layout geometry, animation, and interaction, but not in
  classification semantics.
- Facets such as `phase`, `status`, `memory_decision`, `risk_level`,
  `knowledge_value`, `priority_level`, department action labels, and
  `诏令行为谱系` remain searchable fields, not tree branches. Keep facet
  relationships visually and structurally independent from the official trunk;
  do not let facet nodes become parents of content-lineage records.
- If an entry fits multiple topics, choose the highest-scoring content lineage
  for the trunk and keep the other terms in keywords/facets for graph links and
  recall.
- The web UI and Markdown leaves must show at least Chinese `关键词`, `摘要`, and
  `理由`; raw `summary`, `evidence`, and `memory_content` should remain
  unchanged as source fields.
- Also maintain a lightweight multidimensional knowledge graph at
  `references/shiguan-knowledge-graph.json`. Treat the growth tree as the
  official trunk and the graph as a side index: records connect to lineage,
  keywords, phase/status/memory facets, risk/value/priority facets, edict
  behavior facets, source, and time. The graph uses local JSON nodes/edges and
  must not require Neo4j, RDF stores, or any background service to operate.
- The local web UI should use this graph for star/tree relationships: selecting
  a list entry should focus the matching node, selected nodes and related edges
  should be visibly highlighted, and nodes may use slow drift animation as long
  as labels remain readable. Clicking a lineage node must focus the complete
  上下属 chain for that lineage: ancestors, descendants, the lineage edges
  between them, and the leaf records attached to that chain remain visible as a
  coherent path. Focused views must not merely switch to the global tree view
  and must not use star/ring clustering. They must first gather the selected
  node plus its related nodes into a focused subgraph, then lay out that
  clustered subgraph as a compact tree/chain. Manual free browsing may use
  星图, but selection focus, search-card jumps, and lineage-chain focus must
  show the focused subgraph with tree-style hierarchy.

Every Shiguan entry should also carry a compact machine-stable code:

```text
层级码串-YYYYMMDD-日内36进制序号-四字码
```

Example: `SCGSDYJM-20260606-1Z-DAAA`.

User-facing reports and Shiguan UI labels call this code `诏令编号`. The internal
field name may remain `court_code` for compatibility. Do not label this code
`机器编号` in final memorials, web labels, graph tooltips, or generated tree
leaves.

Existing generated `court_code` values are historical evidence and must not be
bulk-renumbered merely because the generation rule improves. Batch changes may
update the generation rule, validation, display legend, index enrichment, and
future outputs, but they must preserve already written `court_code` fields
unless the user explicitly orders historical renumbering.

The `层级码串` is a concatenation of per-layer representative codes for
`史馆总纪/志/门/纲/目/条/诏`. Each layer defaults to one character when the
controlled vocabulary makes that unambiguous, but a layer has no fixed maximum
length. Increase that layer's representative code when a single character would
be ambiguous, capped, overloaded, or generated from an unknown term. Unknown
Chinese lineage values must not collapse to generic `X`; use a deterministic
stable fallback such as `U` plus base36/hash material, or add the term to the
controlled vocabulary. `X` must never mean both "unknown" and a concrete
category such as `星图`.

Knowledge-base, record, and machine identifiers are independent of the semantic
lineage code. They exist for import/export deduplication, cross-store
reconciliation, and shared-machine recognition, not for taxonomy meaning. Do
not prepend or append them to `court_code`. Generate compact stable fields such
as `kb_uid`, `record_uid`, and a per-machine `machine_uid`/`node_id`
separately. They are normally hidden from local records; when a shared
knowledge base is connected, the peer machine identifier must surface as
searchable Chinese keywords in the Shiguan menu/list and in the leaf editor's
keyword field.

Final `/court` memorials have a narrow identifier block: show only `诏令编号`
and `古制谱系`. Do not show `机器编号`, `kb_uid`, `record_uid`, `machine_uid`, or
other import/export identifiers in the final memorial unless the user directly
asks for an internal diagnostic.

The final four characters are fixed and must be remembered in this order:

```text
第1位：状态
第2位：风险等级
第3位：知识库价值等级
第4位：优先级等级
```

The first character is a discrete execution-status code, not a grade. Show it
with a Chinese status label and color, but do not quantify it. Risk, knowledge
value, and priority use the same `S/A/B/C/D/E/F` grade ladder unless a specific
decree overrides it. `S` is highest and `F` is lowest. The web UI must show this
four-character meaning so future operators do not confuse the repeated letters.
## 史馆实录

史馆 records every meaningful stage result. This is not optional bookkeeping; it
is part of `/court` state progression.

Current implementation root:

```text
%LOCALAPPDATA%\court-shiguan\court-capability-router\references\plan-archives\
```

All writable Shiguan data is resolved by `scripts/shiguan_paths.py`.
`COURT_SHARED_SHIGUAN_ROOT` or `SHIGUAN_SHARED_ROOT` may override the default
shared root. Skill-local `references/` is for governing references and portable
seed material; it is not the authoritative runtime archive. The directory name
remains `plan-archives` for compatibility with the existing script, but the
court semantics are 史馆实录.

### RC6_LOCAL_AUTHORITY_REALM_PHASE1

Phase 1 的 local authority realm 只产生 pure receipt 和
`TemporaryDirectory` fixture。`authority_realm_id` 标识本机 realm，
`root_fingerprint` 绑定已验证的 filesystem/directory identity；Windows
大小写、长短路径和已解析的词法别名不得产生第二个物理根身份。只有带迁移收据证明的
exact junction 可作为同根别名；未证明 junction、symlink、generic reparse
或 containment escape 返回 `AUTHORITY_ROOT_UNTRUSTED`。

此阶段不探测或绑定真实 `.agents` Shiguan root，也不接入 archive transaction。
任何 receipt 即使在 synthetic fixture 内匹配，也必须保持
`production_ready=false`、`authority_root_bound=false`、
`archive_transaction_bound=false`。真实绑定须按顺序通过
`PENDING_COUNT_ZERO`、`QUIESCENCE_STABLE`、`MIGRATION_GATE_PASSED` 后由单一
writer 串行接入。UNC、NFS、SMB、cross-host 或无法证明 local filesystem 的
输入返回 `AUTHORITY_TRANSPORT_UNSUPPORTED`；不得引入 distributed lock、第二
ledger、SQLite、HTTP service 或 message queue 作为回退。

史馆 triggers:

- Every trigger below writes a complete stage record, not merely a final
  closeout note. A complete stage record may be concise, but it must preserve
  the decree/boundary, state transition, responsible offices, gate decision,
  evidence, verification status, next action, and memory decision needed for
  later replay. Final closeouts additionally require the full Memorial Format.
- After 开朝 capability classification finishes.
- After 中书省 requests clarification through 太子.
- After 太子 receives the user's clarification answers.
- After 三省会审 produces an approved, rejected, or caveated decree draft.
- After 尚书省 dispatches assignments.
- After any 六部 or 工坊 work group completes with evidence.
- After 门下省复核, before claiming Done.
- After Completion/Pause Semantic Reload finishes, when it changes the closeout
  wording, detects drift, fails, or has durable routing value.
- Before any formal decree or skill-behavior correction claims Done, to preserve
  the complete Memorial Format, hard-gate fields, evidence chain, and the
  user-facing short memorial's Shiguan anchor.
- Before any skill package is built after a behavior correction, so the local
  skill contains the complete 史馆完整结诏 for the correction and the package only
  ships the durable source rule, not host-local record bodies.
- After memory candidates are written, proposed, skipped, or deferred.
- When blocked, paused, cancelled, or when a different decree starts.
- When `superCC` is selected, record `supercc_env_gate`,
  `standing_officials`, `context_packet_complete`,
  `temporary_ministry_release`, and the zellij/squad/Codex evidence needed to
  replay whether the court really entered Codex 官署 mode. Use recall keywords
  such as `superCC`, `Codex 官署`, `zellij`, `squad`, `standing 三省`,
  `temporary 六部`, and `design context packet`.

Use `scripts/archive_checkpoint.py` whenever the filesystem is writable. For
ordinary intermediate stages, compact fields are acceptable only when they still
cover every required gate. For final closeout, package readiness, skill-behavior
corrections, drift correction, or any decree where traceability is questioned,
the archive must include the full Shiguan process record through
`--full-record-file` or `--full-record`; a summary-only checkpoint is not enough.

When the same Shiguan records are shared by multiple local agents, every
checkpoint must preserve the writing agent identity. `archive_checkpoint.py`
auto-detects this from the skill root and writes `source_agent`,
`source_agent_label`, `source_agent_skill_root`, and searchable keywords such as
`agent:codex`, `agent:hermes`, `agent:claude-code`, and `代理:Claude Code`.
Use `--source-agent` only for
explicit bridge/import jobs where the runtime cannot be detected from the skill
path.
The user-facing closeout must also expose this identity through
`作业AI：<source_agent_label>`; if Codex completes the work it says `Codex`, and
if Hermes completes the work it says `Hermes`; if Claude Code completes the work
through the `.claude` skill junction or Claude Code environment, it says
`Claude Code`.

```powershell
python -B scripts/archive_checkpoint.py --topic "<short-topic>" --phase "门下封驳" --status "APPROVED" --summary "<what changed>" --evidence "<files/commands>" --next "<next action>" --memory-decision "PROPOSE" --memory-content "<candidate or none>" --memory-reason "<why>"
python -B scripts/archive_checkpoint.py --topic "<short-topic>" --phase "结诏" --status "DONE" --summary "<compact summary>" --evidence "<commands/files/package>" --next "<next action>" --memory-decision "WRITE" --memory-content "<durable rule or none>" --memory-reason "<why>" --full-record-file "<utf8-full-shiguan-record.txt>"
```

When a checkpoint has durable routing value, include `--keywords` and
`--key-actions`. The script appends a JSONL recall entry to
the shared `references/shiguan-index.jsonl` so future 三省六部 work can search prior
keywords, key behaviors, evidence, memory decisions, source archives, and
whether a checkpoint carries an attached full record.
After each checkpoint or memory decision, the scripts refresh the built-in
Markdown growth tree under the shared `references/shiguan-tree/` asynchronously
through the Shiguan service daemon. The foreground checkpoint path must stay
fast: it writes the raw archive and `shiguan-index.jsonl`, returns the generated
court code, and records a refresh request. Use `archive_checkpoint.py --sync`,
`archive_checkpoint.py --refresh-tree`, or the explicit growth/export scripts
only when the newest decree or validation gate requires blocking refresh
evidence. Treat shared `plan-archives/` and `memory-decisions/` as the raw
evidence layer, shared `shiguan-index.jsonl` as the recall layer, and shared
`shiguan-tree/` as the living tree layer. The tree is Obsidian-friendly but
remains the court's internal memory source; Obsidian exports are derived copies,
not the source of truth.
Every entry must be enriched with short bilingual recall fields:

- `keyword_summary_zh`: concise Chinese summary for the user.
- `keyword_summary_en`: concise English summary for agente/tool retrieval.
- `keywords_zh`: Chinese search terms.
- `keywords_en`: English search terms.

Use `scripts/shiguan_entry_utils.py` for this enrichment; do not hand-roll
separate formats in individual scripts.
Keep retrieval token-light: default to
`scripts/query_shiguan_index.py --format compact --limit 5 --summary-chars 160`
with task keywords and key actions. Open raw source archives or detailed JSON
only when compact hits are insufficient, disputed, or needed as evidence.
Before planning similar work, query it:

```powershell
python -B scripts/rebuild_shiguan_index.py
python -B scripts/query_shiguan_index.py "<keyword>" "<key-action>"
python -B scripts/grow_shiguan_tree.py
python -B scripts/export_shiguan_obsidian.py --out "./Court-Shiguan-export" --check --zip
```

Obsidian participates through a preserve-only cache and import queue:
`scripts/sync_shiguan_obsidian_vault.py` refreshes the configured vault from the
shared Shiguan source without deleting user notes, while Obsidian edits/imports
must enter shared `shiguan-imports/pending/` and wait for 三省会审/门下复核 before
becoming official records.

Use the local web manager for human-readable edits and additions:

```text
static entry: web/shiguan-tree/index.html
editable service: local_url such as http://127.0.0.1:8765/ plus LAN `lan_urls`
```

Opening the HTML file directly is a static shell. Saving, rebuilding,
growth-tree refresh, and Obsidian export require the local server command above.
The web manager includes a macro graph view inspired by MC百科-style Mod
relationship star maps: center node, branches, topics, leaves, and keyword/action
relationship edges. Preserve the search/list/editor functions when changing the
graph.

The web manager also exposes agente presence as read-only status. Ordinary
court scripts register the active runtime through `shiguan_paths.register_agent_presence()`
when `ensure_shared_seed()` runs, using labels such as `Codex`, `Hermes`, or
`Agents`; WebUI reads shared `court-runtime/agente-presence/*.json` through
`/api/agent-presence` and `/api/state.agent_presence`. Long-running WebUI,
autosync, and service-daemon processes must set `COURT_DISABLE_AGENT_PRESENCE=1`
so they do not keep a completed Codex/Hermes session falsely online. This status
surface is listen-only: it must not add remote-control actions for agente.

Every meaningful checkpoint must carry a memory decision. Use `WRITE` only
after 门下封驳 approves durable writeback; otherwise use `PROPOSE`, `SKIP`, or
`DEFERRED`.

If the script cannot run, append the same fields manually to the current 史馆
record and report `史馆实录：手动入录` or `史馆实录：失败，原因...`. Do not silently
skip 史馆 recording.

If the script prints `ARCHIVE_PERMISSION_REQUIRED`, request approval/escalation
and rerun the same command. In `super` mode, a read-only 史馆 check or a write to
this skill's own 史馆 directory is considered in-scope unless the runtime blocks
it; request runtime escalation immediately if required. Only fall back to manual
recording when escalation is denied or unavailable.

## Token Three-Level Optimization / 令牌三级优化

史馆、记忆桥、官籍目录、导入队列和 office context packet must obey this three-level
token optimization policy:

1. **元数据精准 / `metadata_precision`**: record enough structured metadata to
   retrieve and verify without loading the whole body. Required metadata normally
   includes `court_code`, `lineage_display`, `lineage_key`, `lineage_parts`,
   bilingual keywords, `key_actions`, source path, source kind, source agent,
   evidence command/path, hashes or prefix hashes when useful, mtimes/sizes, task
   ids, profile/dossier hashes, and risk/knowledge/priority grades.
2. **正文精简引用 / `body_reference_policy`**: keep record bodies compact. Use
   summaries, path+line anchors, short excerpts, and evidence handles. Do not
   copy full transcripts, raw logs, private Shiguan bodies, full Codex/Hermes
   memory files, or entire imported documents unless the newest decree explicitly
   requests a body-level copy and 门下省 approves redaction/privacy gates.
3. **按需加载 / `on_demand_loading`**: query compact indexes first, then open only
   the specific archive, source file range, import sample, generated leaf, or
   runtime artifact needed for the current decision. For large or append-only
   files, record stable prefix fingerprints and source paths; future turns load
   the raw body only when compact metadata is insufficient, disputed, or required
   as evidence.

Every checkpoint with durable routing value should record the token gate in its
summary/evidence or full record as
`token_optimization_policy=PASSED | PARTIAL | FAILED | authority_blocked`. A
`PARTIAL` or `FAILED` gate must name whether the problem was imprecise metadata,
overlong body copying, or eager loading of unrelated sources.

## Codex/Hermes Internal Memory Bridge

Codex and Hermes built-in memories are the agents' own runtime memory layers.
Shiguan is the shared audit and recall layer. Bridging internal memory to
Shiguan must therefore preserve discoverability without turning Shiguan into a
silent raw-memory mirror.

Governed bridge command:

```powershell
python -B scripts/ensure_portable_court_bootstrap.py --check-only
python -B scripts/ensure_portable_court_bootstrap.py --apply
python -B scripts/internal_memory_shiguan_bridge.py inspect --format json
python -B scripts/internal_memory_shiguan_bridge.py record --content-mode metadata --refresh-mode async
```

Use the portable bootstrap when Codex or Hermes built-in memory is disabled:
it enables only native memory flags, preserves existing provider fields, and
then records a metadata-only Shiguan bridge. The bootstrap must not hand-edit
Codex SQLite, copy raw Hermes profile bodies, process pending imports, or
install third-party memory providers.

Index-level content bridge is preferred when the user wants content to be
discoverable but does not require copying the full body. Write a normal
`archive_checkpoint.py` record and let `shiguan_entry_utils.enrich_entry()`
derive the recall fields. The resulting index entry and generated leaf must
carry:

- `lineage_display`, `lineage_key`, `lineage_parts`, and `court_code` for
  precise 古制谱系 and 诏令编号 recall.
- `keywords`, `keywords_zh`, `keywords_en`, `keyword_summary_zh`,
  `keyword_summary_en`, and `key_actions` for keyword search.
- `capability_vector_schema`, `capability_vector_kind`,
  `capability_lineage`, `capability_vector_terms`,
  `capability_vector_text`, `capability_vector_sparse`, and
  `capability_vector_hash` for capability-lineage vector or hybrid search.
  This vector is about 三省六部/官籍/能力类型/工具/skill/script/agent/史馆谱系,
  not a generic full-text embedding.
- `capability_source_paths` and evidence fields for local source paths, such as
  a Codex session JSONL,
  `memories_1.sqlite`, Hermes `MEMORY.md`/`USER.md`, or a profile memory file.
- Optional `original_sha256`, `original_size`, and `original_mtime` in evidence
  or full-record when the file exists.
- For live append-only sources such as the active Codex session JSONL, do not
  present a whole-file sha256 as a durable invariant. Record
  `live_prefix_size`, `live_prefix_sha256`, and `live_prefix_mtime_utc`, then
  verify future recall by hashing only the first `live_prefix_size` bytes. This
  keeps the source path auditable without copying the private transcript body
  and remains valid when later turns append to the same JSONL.
- Searchable bilingual keywords such as `能力谱系向量`, `内容级桥接`,
  `古制谱系`, `诏令编号`, `source path`, and the file basename when paths matter.
- A clear privacy note that recall points to the source path; reading that
  source still follows the active authority, redaction, and 门下 review gates.

This index-level bridge gives future Codex/Hermes sessions a precise indexable
leaf without duplicating private bodies into Shiguan. It is also the preferred
way to reference complete conversation transcripts: store the capability
vector, lineage/code, keywords/actions, and session file path/fingerprint in the
Shiguan leaf, not the full transcript, unless the user explicitly orders a
separately designed and approved body-level copy.

Default bridge semantics:

- Codex bridge reads `%CODEX_HOME%` or `%USERPROFILE%\.codex`, records
  `features.memories`, `[memories] generate_memories/use_memories`, and
  metadata for `memories_1.sqlite`, including hash, size, mtime, table names,
  columns, and row counts.
- Hermes bridge reads the actual `config.yaml` under `%HERMES_HOME%` or
  `%LOCALAPPDATA%\hermes`, records the `memory:` block, built-in provider
  status, root memory file metadata, and profile memory file metadata.
- `metadata` mode never copies `MEMORY.md`, `USER.md`, Codex SQLite rows, raw
  logs, or private profile facts into Shiguan. It stores only enablement state,
  paths, hashes, sizes, mtimes, counts, and inventory.
- If Codex `memories_1.sqlite` has no rows in the candidate body table
  `stage1_outputs`, record `content_recall_status=empty_store_no_body_rows`
  and `memory_body_rows=0`. If rows exist, record `body_table_state` with the
  candidate table, candidate text column, row count, nonempty count, empty
  boolean, and `counts_only_no_raw_sqlite_body` policy. Do not seed or mutate
  the Codex SQLite store by hand to manufacture a recall result.
- The former `redacted` mode is intentionally disabled. Arbitrary memory text
  cannot be proven secret-free merely by bounded excerpting; the bridge rejects
  that mode and remains metadata-only. A future body-level bridge needs a new
  explicit decree, a dedicated secret-safe design, and 门下 privacy review.
- Index-level content bridge does not need a separate custom script: use
  `archive_checkpoint.py` with strong keywords, key_actions, source paths, and
  full-record fields so `query_shiguan_index.py`, the growth tree, and the web
  graph can locate the capability context, source path, 诏令编号, and 古制谱系
  precisely.
- The bridge must not process `shiguan-imports/pending` and must not install or
  enable Hindsight, ScopeRecall, or other third-party memory providers merely to
  satisfy a built-in memory bridge.
- Every bridge record uses `archive_checkpoint.py` with bilingual keywords such
  as `内置记忆`, `史馆桥接`, `Codex memories`, `Hermes built-in memory`,
  `metadata-only`, and `privacy`, so future Codex/Hermes sessions can recall the
  current memory architecture without reading private memory bodies.

## Pending Import Governance Trust Boundary

Pending bodies remain raw materials. The metadata planner may inspect filenames,
`lstat` fingerprints, and bounded sidecar JSON only; it may not open, read, hash,
move, delete, or mark-seen a body. The v3 governance ledger adds:

- exact court-runtime actor identity evidence derived from a live task and a
  passed office preload record;
- per-event HMAC authentication, globally contiguous sequence numbers, an event
  hash chain, unique UUIDs, and timezone-aware nondecreasing timestamps;
- an authenticated append-only head under the private runtime root, outside the
  append-only governance ledger directory;
- independent recomputation of the candidate binding from the current pending
  metadata snapshot at authorization and every body-access check; and
- metadata-only reject/quarantine decisions that plan append-copy provenance and
  retain the original source.

The current Codex host does not expose a non-forgeable host-issued actor
capability to the skill. Production `body_authorized` and body access therefore
fail closed; only fixture tests exercise that state. This is a deliberate
compatibility conclusion, not permission to treat a test binding as a real
authorization. Real pending bodies stay untouched until a later host capability
and an explicit body decree both exist.

When Codex memory is enabled through configuration, the preferred minimal
configuration is:

```toml
[features]
memories = true

[memories]
generate_memories = true
use_memories = true
```

If the newest user decree explicitly says to remember or make a durable behavior
rule, 门下省 first verifies that native Codex memory is enabled. If it is not,
enable only the native `[features] memories = true` and `[memories]`
`generate_memories/use_memories = true` flags; do not install third-party memory
providers. Then record the durable rule in current Codex memory through the
available write path. If direct memory writeback is unavailable, write one small
ad-hoc note under `%USERPROFILE%\.codex\memories\extensions\ad_hoc\notes\` for
later ingestion and report that fallback explicitly.

When Hermes memory is enabled, keep its built-in memory as the default bridge
source unless the user separately approves a provider change. The bootstrap
sets the enablement booleans and preserves any existing `provider` value:

```yaml
memory:
  memory_enabled: true
  user_profile_enabled: true
```

## Memory Conflict Downgrade Rules

When `MEMORY.md`, rollout summaries, Shiguan leaves, plan archives, imported
snapshots, or Hermes profile memories disagree with the current `SKILL.md` and
directly linked governing references, treat the older material as evidence, not
authority. Record the downgrade in the current decree instead of silently
following stale memory.

Current downgrade rules:

- Hermes desktop/profile-native-only `superCC`, including old
  `hermes_desktop_zellij_gate=SKIPPED_DESKTOP` wording, is historical readiness
  language. Current normal `superCC` still requires zellij+`squad`; Hermes
  desktop/profile evidence is supplemental readiness or dispatch evidence only.
- Legacy visible `patrol-inspector` / `AWAKE_STATUS_ONLY` status-table windows
  and closeout-watch panes are historical diagnostics. Routine supervision is
  the silent `scripts/supercc_watchdog.py` path; visible patrol requires a fresh
  bounded diagnostic decree.
- The old `court-lite` four-pane tmux shape with 太子、三省/史馆 variants is
  historical startup evidence. Current terminal-visible normal `superCC` visible
  core is 太子 plus 三省; 六部、史馆 and 监察 are non-visible/silent unless explicitly
  requested through a bounded dispatch or diagnostic.
- Twelve-line and thirteen-line closeout records are historical formats. Current
  user-facing closeout has exactly fourteen labels from `SKILL.md`.
- `libuhr` is a legacy Hermes/profile alias. Durable court role keys use
  `libu-hr` for 吏部 HR/铨选 and `libu` for 礼部; aliases must be normalized in
  evidence instead of creating a new office.
- The older request to auto-apply the 三省六部 skill as default Hermes memory for
  every new Hermes session remains an open/unimplemented requirement until a
  current decree validates the actual Hermes startup path. Do not claim it is
  already implemented from memory alone.
- Skill-local `references/` may contain imported snapshots, portable seed files,
  or host-local archive remnants. Writable authoritative Shiguan data lives in
  the shared root resolved by `scripts/shiguan_paths.py`; packages and active-copy
  hash checks must exclude raw private Shiguan bodies, memory decisions, plan
  archives, runtime ledgers, logs, Obsidian config/API keys, peer/import state,
  generated local indexes, and `references.imported-*`.
## Memory Decision Gate

史馆实录 and long-term memories are different:

- **史馆实录** records what happened in this decree: plans, questions, decisions,
  evidence, verification, rejected options, office reports, 考课, and next
  actions.
- **长期记忆** records stable information likely to help future conversations:
  durable user preferences, standing operating rules, installed capability
  changes, canonical archive locations, recurring project conventions, and
  explicit long-term decisions.

Every decree must end with one memory decision, but not every intermediate
stage needs a durable-memory candidate. When a checkpoint is written, it still
must carry `memory_decision`, `memory_content`, and `memory_reason` fields; for
pure evidence, read-only diagnostics, transient status corrections, and routine
verification, fill them as `SKIP`, `none`, and a concise reason such as `pure
evidence`. When no checkpoint is written because the newest decree forbids audit
writes, report the skipped Shiguan/memory fields in the user-facing closeout.
When a checkpoint changes stable rules, user preferences, capability inventory,
safety policy, or recurring workflow behavior, 史馆 proposes memory candidates,
户部 checks durable value, 礼部 edits them into concise neutral wording, 刑部
checks privacy/security, and 门下省 approves or rejects memory writeback. 史馆
only records candidates and recommendations; final durable memory writeback
requires both 门下封驳 and the newest decree's memory-write boundary.

Autonomous memory policy:

- `approval`: propose memory candidates and ask before writing them.
- `autonomous`: may write low-risk durable preferences, workflow rules, and
  capability-map changes only when the newest decree allows durable memory
  writeback and 门下 approves; ask before storing personal, sensitive, private,
  broad, or ambiguous information.
- `super`: may write low-risk durable memory without an extra confirmation only
  when the newest decree allows durable memory writeback and 门下 approves. Still
  stop for secrets, credentials, private data, paid/commercial info,
  medical/legal/finance sensitive facts, or anything the user might reasonably
  not expect to persist.

Stable corrections to court voice, durable skill behavior, office hierarchy,
agent autonomy, memory gates, and report contracts are valid durable-memory
content when the user explicitly asks to record them. 史馆 must preserve the rule
itself, not merely the event that exposed the drift.

Never store:

- passwords, tokens, keys, cookies, auth material, or secret paths;
- private personal data unless the user explicitly asks to remember it;
- transient task state, raw logs, one-off command output, speculation, or
  unverified claims;
- copyrighted/private content summaries beyond what is needed as a durable
  preference or instruction.

When a memory is written, proposed, skipped, or deferred, include it in both
the 史馆实录 checkpoint and the court output:

```text
记忆裁定：WRITE | PROPOSE | SKIP | DEFERRED
记忆内容：...
理由：...
```

If Codex memory writeback is unavailable in the current interface, or if 门下省
has not yet approved writeback, record the candidate with
`scripts/memory_decision.py` and report
`记忆裁定：已候选入史馆，待门下封驳/记忆接口可用时写入`.

## Current-Tool Install And Memory Projection Gates

`current_tool_only_install_gate` installs only the current-tool requested by the
newest explicit user instruction into its governed `.agents` surface and shared
Shiguan boundary. `no_unrequested_tool_gate` forbids installing or mutating any
other tool merely because it was discovered during inspection.

`agent_tool_memory_obsidian_projection_gate` is metadata-only and
`source_read_only`. Eligibility comes from
`installed_tool_manifest_eligibility_gate`; each tool has an isolated graph under
`per_tool_memory_graph_isolation_gate`, and a blank host must pass
`blank_host_memory_probe_before_write_gate`. The
`metadata_index_only_projection_gate` records `prompt_evidence_state`,
`canonical_tool_classes` (`codex`, `hermes`, `claude-code`,
`other:<stable-id>`), and `tool_memory_state` (`enabled`, `disabled`,
`unavailable`, `unknown`). `unknown_state_fail_closed` and
`no_unrequested_tool_mutation_gate` prevent inferred writes.
