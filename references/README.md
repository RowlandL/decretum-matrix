# Court Router References

This file is the second-level loading index. Read `SKILL.md` first, then this file when a task points at a broad governing area and you need to choose the smallest reference body to open. For 500+ line volumes, read `reference-section-index.md` before opening the full file.

## Reference Scale Index

Token policy remains three-level: `metadata_precision` first, `body_reference_policy` second, and `on_demand_loading` third. Use this index to avoid opening every governing volume by default.

## Second-Level Loading Map

| Need | Open |
| --- | --- |
| 中文完整介绍、初级/进阶/高阶使用手册、常用命令速查 | `user-manual-zh.md` |
| Newest decree precedence, semantic invariants, source-of-truth placement | `court-core-contract.md` |
| Opening a court turn, 三权 authority, startup checks, bootstrap, first-run setup | `court-startup-authority.md`; approval details shard `references/sections/court-startup-approval-policy-details.md` |
| Codex/Hermes/Claude/generic CLI `superCC` runtime selection, zellij+squad normal gate, Hermes readiness evidence, and 静默监督 lifecycle | `court-supercc-runtime-selection.md`; phase cycling and silent-supervisor shard `supercc-phase-cycling-model.md` |
| Court voice, office responsibility, 三省/六部 dispatch, direct-superior routing | `court-offices-dispatch.md` |
| Reply fields, few-shot response families, generated draft fixture lint, progress updates, clarification questions, code review reports, office report samples, office-title grammar positive/counterexamples | `references/sections/court-response-fewshot-format.md`; office voice shard `references/sections/court-office-voice-fewshot.md`; fixture `references/fixtures/response-draft-families.json`; gate `scripts/check_response_draft_fixtures.py` |
| Context compaction, semantic compression survival, original decree/plan anchors, or post-resume skill invocation drift | `references/sections/court-context-compression-survival.md`; fixture `references/fixtures/context-compression-survival.json`; gate `scripts/check_context_compression_survival.py` |
| State machine, recursive agents, runtime ledgers, heartbeat, cleanup, closeout silence | `court-state-runtime-agents.md` |
| Capability catalog, skills/MCP/CLI/script/agent routing, 官籍 refresh, active index skill gate | `court-capability-registry.md`; shard `references/sections/court-capability-verification-index.md` |
| Fallback static department map and capability dimensions when generated local catalog is absent | `department-map.md` |
| Shiguan records, lineage, memory decisions, metadata-only bridge, tokenized evidence | `court-shiguan-memory.md` |
| Closeout, semantic reload, memorial fields, validation, packaging | `court-closeout-validation.md`; memorial shard `references/sections/court-closeout-memorial-format.md` |
| Windows/Hermes terminal pitfalls, local GUI/HTTP exclusions, host-specific hazards | `court-host-platform-pitfalls.md` |
| Obsidian preserve-only sync and pending imports | `obsidian-autosync-rest.md` |

## Large Reference Loading Matrix

These broad volumes should be opened by section after reading their `## Contents` list:

| Large volume | Owns |
| --- | --- |
| `court-state-runtime-agents.md` | State transitions, recursive agent hierarchy, runtime ledgers, superCC pane/session lifecycle, rate-limit cleanup. |
| `court-offices-dispatch.md` | 三省六部 responsibility model, intent clarification, dispatch contracts, direct-superior routing, ordinary/subagent office semantics. |
| `references/sections/court-response-fewshot-format.md` | User-facing and office-facing reply field contract, few-shot prompt families, generated draft fixture lint, code review report shape, blocked/partial answer shape, response repair gate, and the office voice shard link. |
| `references/sections/court-context-compression-survival.md` | Multi-cycle context compression survival, original decree and plan source anchors, mandatory post-compaction skill reload, and reply-format drift repair. |
| `court-startup-authority.md` | 开朝 sequence, authority gates, superCC startup, bootstrap/dependency gates, read-only vs live action classification; approval policy details are sharded at `references/sections/court-startup-approval-policy-details.md`. |
| `court-closeout-validation.md` | Long-context semantic reload, official report contract, closeout fields, package-ready gates, validation command classes; memorial details are sharded at `references/sections/court-closeout-memorial-format.md`; installation/validation details are sharded at `references/sections/court-closeout-installation-validation.md`. |
| `court-capability-registry.md` | 官籍/personnel system, recruitment, catalog refresh, and capability verification index skill gate; active index details are sharded at `references/sections/court-capability-verification-index.md`. |
| `supercc-phase-cycling-model.md` | Small shard for superCC phase cycling, routine visible core, 静默监督, non-visible ministry task queues, and request-rate budget alignment. |

If a task only needs one field or invariant from a large volume, prefer `rg`/targeted section reads over full-file loading.

Section-level routing for these large volumes is maintained in `reference-section-index.md`.

## Portable Package Boundary

Portable packages do not include host-local Shiguan record bodies, memory-decision bodies, generated leaves, raw logs, local capability catalogs, runtime ledgers, agente logs, local backups, import queues, peer sharing state, or tidy reports because they can contain host-local evidence or private operational state.

On first use, use the read-only validation commands in `install.md` first. Run `python -B scripts/refresh_capability_registry.py` and `python -B scripts/rebuild_shiguan_index.py` only when local 官籍/Shiguan writes are authorized.
