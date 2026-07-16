# Court Department Capability Map

Use this fallback map when this skill's installed catalog is absent or stale.
Prefer `references/installed-capabilities-catalog.md` when available.

This map is part of the court's 官籍/能力图谱. A skill, MCP, CLI, script, custom
agent, or worker agente may fit several offices. 吏部 evaluates capability
dimensions first, then 尚书省 grants a task-specific 差遣 under the approved
decree. Do not treat a table row as a permanent single-department label.

The governing boundary from formal intake through verified presentation and
local-first recruitment is documented in
[Court Runtime Result And Recruitment Contract](sections/court-runtime-result-and-recruitment-contract.md).
Broader public discovery, creation, installation, or write behavior elsewhere in
this map is outside the I1/C purified lane. For I1/C, the dedicated contract
governs: zero network calls, zero external writes, no capability mutation,
`ASK_USER` intent-only handoff, and `C2_FULL=HOLD_BY_AUTHORITY`.

Capability roots are deliberately distinct. Resolve `%CODEX_HOME%` first; if it
is unset, use `%USERPROFILE%\.codex`.

- `%CODEX_HOME%\skills`: primary Codex skill / 工坊技艺 library.
- `%USERPROFILE%\.agents\skills`: Agent Skills fallback and cross-host 工坊技艺 library.
- `%CODEX_HOME%\agents`: actual Codex custom agents / standing court officials.

Current standing Codex custom agents: `taizi.toml`, `zhongshu.toml`,
`menxia.toml`, `shangshu.toml`, `libu-hr.toml`, `hubu.toml`, `libu.toml`,
`bingbu.toml`, `xingbu.toml`, `gongbu.toml`, `shiguan.toml`,
`shiguan-hermes.toml`, `zaochao.toml`.

| Court Unit | Responsibility | Primary Local Capabilities |
| --- | --- | --- |
| Taizi | User-facing intake, decree charter, clarification relay, final 回奏, approval for standing-agent/registry changes | `taizi.toml`, `decretum-matrix`, `zoom-out` |
| Zhongshu | Decree drafting, research, planning, issue breakdown, acceptance criteria; does not directly command 六部 | `zhongshu.toml`, `writing-plans`, `to-prd`, `to-issues`, `request-refactor-plan`, `spec`, `improve-codebase-architecture`, `brainstorming` |
| Menxia | 封驳, plan review, completeness/risk/resources gate, final semantic review; 史馆三省共监、门下主审 | `menxia.toml`, `review`, `requesting-code-review`, `plan-eng-review`, `plan-ceo-review`, `plan-design-review`, `plan-devex-review`, `grill-me`, `grill-with-docs` |
| Shangshu | Executes approved decrees, commands 六部, grants 差遣, integrates reports | `shangshu.toml`, `decretum-matrix`, `dispatching-parallel-agents`, `subagent-driven-development`, `executing-plans`, `handoff` |
| Hubu | Resource ledger, budget/caps, dependencies, environment, path permissions, version and capability inventory | `hubu.toml`, `decretum-matrix`, `find-skills`, `refresh_capability_registry.py`, `setup-gbrain`, `sync-gbrain`, `benchmark`, `benchmark-models`, `health`, `setup` defaults |
| Libu | Ritual and text: requirement wording, docs, reports, teaching, citations, output contract, rubric | `libu.toml`, `edit-article`, `writing-beats`, `writing-fragments`, `writing-shape`, `document-generate`, `document-release`, `teach`, `make-pdf`, `ubiquitous-language` |
| Bingbu | Tactical operations: incident response, complex debugging, migration/concurrency campaigns, runtime battle plan | `bingbu.toml`, `systematic-debugging`, `diagnose`, `receiving-code-review`, `sn-search-code` |
| Xingbu | Law and risk: security, privacy, compliance, destructive/paid/install/external-write gates, test and rollback audit | `xingbu.toml`, `guard`, `careful`, `cso`, `review`, `verification-before-completion`, `git-guardrails-claude-code`, `setup-pre-commit` |
| Gongbu | Engineering works: implementation, prototype, build, QA execution, deployment, browser/GUI/external app operations | `gongbu.toml`, `tdd`, `test-driven-development`, `prototype`, `migrate-to-shoehorn`, `gstack`, `qa`, `browse`, `qa-only`, `canary`, `land-and-deploy`, `ship`, `setup-deploy`, `davinci-resolve-mcp`, enabled `davinci-resolve` MCP |
| Libu-HR | 官籍 and 铨选: discover, score, recruit, appoint, and review skills/agents/MCPs/CLIs/scripts | `libu-hr.toml`, `decretum-matrix`, `find-skills`, `refresh_capability_registry.py`, `dispatching-parallel-agents`, `subagent-driven-development` |
| Shiguan | 三省共监、门下主审的史馆实录: 实录, 本纪, 表, 书/志, 列传, bilingual keyword/key-behavior recall, built-in growth tree, macro relationship graph web manager, old-archive rebuild, Obsidian-compatible export, memory candidates, memory decisions, evidence chain, 考课 archive | `shiguan.toml`, `shiguan-hermes.toml`, `context-save`, `context-restore`, `handoff`, `landing-report`, `archive_checkpoint.py`, `query_shiguan_index.py`, `grow_shiguan_tree.py`, `build_shiguan_knowledge_graph.py`, `rebuild_shiguan_index.py`, `shiguan_entry_utils.py`, `serve_shiguan_tree.py`, `export_shiguan_obsidian.py`, `web/shiguan-tree`, `memory_decision.py` |
| Zaochao | Briefings, retrospectives, health/status summaries | `zaochao.toml`, `retro`, `health`, `landing-report`, `context-save`, `context-restore` |

Libu-HR registry note: local Codex plugins are first-class `plugin` candidates;
embedded plugin skills remain `skill` candidates sourced from `codex_plugin`.
Disabled entries are visible but non-dispatchable. Recruitment is local-first;
public metadata requires injected authority. Create/install/write returns
`ASK_USER` and goes to 尚书省 as a structured proposal, never as direct 吏部
mutation; missing authority or verification is explicit blocked/degraded state.

## Capability Registry Dimensions

| Dimension | Meaning |
| --- | --- |
| 身 | Environment fit, permissions, dependencies, sandbox and path boundaries. |
| 言 | Clarification quality, report quality, and parent/user communication. |
| 书 | Code/document structure, formatting, maintainability, and contract adherence. |
| 判 | Judgment, risk recognition, tradeoff quality, and verifiable decisions. |
| 德行 | Safety, honesty, respect for user changes, and no unauthorized scope expansion. |
| 才用 | Domain skill, tool fluency, prior evidence, and task match. |
| 劳效 | Delivery record, test evidence, reliability, defects, and corrections. |
