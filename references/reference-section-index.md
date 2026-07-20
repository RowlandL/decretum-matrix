# Reference Section Index

This is the section-level shard index for large governing references. Read `SKILL.md`, then `references/README.md`, then this file when a task points to a 500+ line volume and only one section is needed. Prefer `rg` or targeted section reads over loading the whole large volume.

## Section-Level Shard Index

| Large reference | Section | Physical shard | Load when... |
| --- | --- | --- | --- |
| `court-state-runtime-agents.md` | `## State Machine` |  | Legal state transitions, 三省会审/太子回奏/尚书分派/门下复核 state, recursive state gates. |
| `court-state-runtime-agents.md` | `## Codex Agent Hierarchy` |  | Recursive agents, ordinary spawned offices, superCC runtime ledgers, pane/session lifecycle, no-Taizi-substitution, rate-limit cleanup. |
| `court-state-runtime-agents.md` | `## 协同上朝` |  | Multi-agent court collaboration startup, squad participation, role handoff, collaborative court posture. |
| `court-offices-dispatch.md` | `## 三省六部 Semantic Bedrock` |  | Office identity, 三省六部 responsibility model, shared office abstraction, non-substitution semantics. |
| `court-offices-dispatch.md` | `## Court Roles` |  | Role list, Taizi/three departments/six ministries/Shiguan responsibility labels. |
| `court-offices-dispatch.md` | `## Court Semantics` |  | Court workflow semantics and how labels bind to actual duties. |
| `court-offices-dispatch.md` | `## Court Voice And Pronouns` |  | User-facing language, court voice, pronoun handling, report style. |
| `court-offices-dispatch.md` | `## Internal Court Functions` |  | Legacy intent hints mapped into court functions. |
| `court-offices-dispatch.md` | `## Clarification Loop` |  | One-question-at-a-time clarification, scope gaps, 三省 question routing. |
| `court-offices-dispatch.md` | `## Dispatch Rules` |  | 尚书 dispatch, 六部 tasking, direct-superior routing, ENTER_DISPATCH, ordinary/subagent office work. |
| `court-startup-authority.md` | `## Quick Start` |  | Minimal startup sequence, fast open checks, first commands for a court turn. |
| `court-startup-authority.md` | `## Approval Policy Details` | `references/sections/court-startup-approval-policy-details.md` | exact three-authority domain, orthogonal serial/parallel behavior, separate superCC runtime, read-only/live action boundaries, index-first capability invocation, packaging governance. |
| `court-startup-authority.md` | `## 开朝 Selection` |  | Authority selection question, startup gate selection, startup scripts, profile/bootstrap checks. |
| `court-supercc-runtime-selection.md` | `## Codex Branch` / phase cycling | `supercc-phase-cycling-model.md` | Routine visible core, silent supervisor lifecycle, phase cycling, non-visible ministry task queues, and request-rate budget alignment. |
| `court-closeout-validation.md` | `## Long Conversation Drift Guard` |  | Drift risks, encoding/read issues, long-context closeout discipline. |
| `court-closeout-validation.md` | `## Completion/Pause Semantic Reload` |  | Mandatory semantic reload, skill-behavior correction check, final closeout gate. |
| `court-closeout-validation.md` | `## Official Report Contract` |  | Full memorial fields, evidence contract, token policy fields, superCC closeout fields. |
| `court-closeout-validation.md` | `## Memorial Format` | `references/sections/court-closeout-memorial-format.md` | User-facing memorial shape, abbreviated vs full report projection, `hard_memorial_gate`, Shiguan Web URL line. |
| `court-closeout-validation.md` | `## Long Conversation Drift Guard` / context compaction | `references/sections/court-context-compression-survival.md` | Multi-cycle semantic compression, original decree/plan preservation, mandatory 三省六部 skill reload, or post-resume reply-format drift repair. |
| `court-closeout-validation.md` | `## Installation And Validation` | `references/sections/court-closeout-installation-validation.md` | Validation commands, packaging rules, portable checks, read-only vs mutating validation classes, `package_ready_gate`, `package_exclusion_check`. |
| `court-shiguan-memory.md` | `## Shiguan Lineage And Court Code` |  | 诏令编号/court_code lineage, Shiguan taxonomy, graph/tree identifiers, import/export identifier display. |
| `court-shiguan-memory.md` | `## 史馆实录` |  | Shiguan checkpoints, archive commands, evidence pointers, record lifecycle, memory decision fields. |
| `court-shiguan-memory.md` | `## Token Three-Level Optimization / 令牌三级优化` |  | Metadata precision, concise body references, on-demand loading, token policy for Shiguan/memory packets. |
| `court-shiguan-memory.md` | `## Codex/Hermes Internal Memory Bridge` |  | Native memory enablement, metadata-only memory bridge, built-in memory status, ad-hoc note fallback. |
| `court-shiguan-memory.md` | `## Memory Decision Gate` |  | WRITE/PROPOSE/SKIP/DEFERRED decisions, durable-memory approvals, autonomous memory policy, forbidden stored content. |

## Small Reference Shards

| Governing area | Physical shard | Load when... |
| --- | --- | --- |
| `court-capability-registry.md` | `references/sections/court-capability-verification-index.md` | Capability verification, recruitment, skill repair, registry drift, or audit needs the active index skill gate for `find-skills`, `skill-creator`, `refresh_capability_registry.py`, and `check_catalog.py`. |
| `court-supercc-runtime-selection.md` | `supercc-phase-cycling-model.md` | superCC phase-cycling rules, default visible core vs silent supervision, non-visible ministry dispatch, or request-rate budget semantics. |
| `court-offices-dispatch.md` / `court-closeout-validation.md` | `references/sections/court-response-fewshot-format.md`; `references/sections/court-office-voice-fewshot.md`; fixture `references/fixtures/response-draft-families.json`; gate `scripts/check_response_draft_fixtures.py` | Reply formatting, few-shot response prompt, office-title grammar positive/counterexamples, generated draft fixture lint, progress updates, clarification question shape, code review report shape, blocked/partial answer shape, or office report samples. |
| `court-closeout-validation.md` | `references/sections/court-context-compression-survival.md`; fixture `references/fixtures/context-compression-survival.json`; gate `scripts/check_context_compression_survival.py` | Multi-cycle context compression survival, post-compaction semantic reload, original decree/plan anchors, and reply-format preservation. |

## Loading Rule

If a needed term is not located through this section index, search the named large reference with `rg` first. Only open the full large reference when targeted section reads are insufficient or when performing a skill-behavior audit/release.
