# Decretum Matrix（诏令矩阵） provenance and rights matrix

Status: `ACTIVE / P1_P3_PASS_WITH_LEGAL_REVIEW_REQUIRED`

This document records source and rights boundaries. It is not a warranty of title and is not legal advice.

## Project identity

- Product: `Decretum Matrix（诏令矩阵）`
- Canonical repository/skill/package name: `decretum-matrix`
- Project rights subject, CLA licensor and trademark policy owner for project-directed material, as expressly declared by the user/maintainer: `孙华清`
- Public maintainer identity: `@RowlandL` (GitHub ID `42199880`)
- Stable protected install/Shiguan locators may retain `court-capability-router`; they are compatibility paths, not the current product identity.

This maintainer declaration is a governance record, not a warranty of title or
a substitute for contributor, employer/client, copyrightability or legal review.

## Third-party source: cft0808/edict

- Repository: `https://github.com/cft0808/edict`
- Fixed reviewed commit: `14a207557719c046af0f993a7bff1cc5a5015b33`
- License: MIT
- LICENSE Git blob SHA-1: `69499c3250cbecc6079c69dc0e5a0f7a4be716da`
- LICENSE SHA-256: `5f67c084a1b5bd87409f05221d5985cde0b99472aa34670613761e614330d93c`
- Original copyright: `Copyright (c) 2026 openclaw-sansheng-liubu contributors`
- Runtime dependency: `false`
- Governing source: `false`
- Purpose: `engineering_semantic_benchmark`

The full upstream MIT text and copyright are preserved in `THIRD_PARTY_NOTICES.md`. Those rights remain independent and are not assigned to, or claimed exclusively by, 孙华清. The repository-level `AGPL-3.0-only` designation applies only to material for which 孙华清 has authority to license; it does not relicense, supersede, revoke or narrow the upstream MIT grant. Any file-level derivative-work or combined-work conclusion remains `LEGAL_REVIEW_REQUIRED`.

## Comparison evidence and conservative conclusion

A prior bounded audit compared the then-current 252 worktree files and all reachable local Git objects with the 222 non-LICENSE payload blobs at the fixed upstream commit. Whole-file matches: `0`. This prior history/object comparison was not rerun in the current review.

The current bounded receipt is
`docs/legal/2026-07-16-cft0808-edict-bounded-similarity-and-rights-review.md`.
GitHub primary-source evidence shows `223` total blobs at tree
`7b44f37128938137493fe07be85aad99408fb54a`; excluding `LICENSE` leaves the
same `222` payload-blob scope. A current 18-file semantic-core review against
all 113 upstream Markdown/Python files found no normalized-text, token-shingle
or structure score at its review threshold. Fifteen long-line containment
flags were manually adjudicated as the single standard directive
`from __future__ import annotations`. The current review found no identical
whole file in the reviewed scope.

That result means only that no identical whole file was found. It does not exclude rewritten fragments, structural influence, concept selection or semantic borrowing. The user explicitly confirmed that earlier versions were influenced by the upstream project, so this project permanently retains the upstream MIT notice and classifies the affected semantic architecture as `upstream-inspired`.

`upstream-inspired` is a provenance disclosure, not a conclusion that every affected local file contains MIT-covered expression. If a local file copies or adapts protected upstream expression, the upstream portion must remain identified and distributed with the MIT notice; adopting ideas or workflows alone does not make an otherwise local file an upstream copy. Those boundaries require file-level review.

## Module classification

| Module or file family | Classification | Basis and required treatment |
|---|---|---|
| Upstream MIT license text in `THIRD_PARTY_NOTICES.md`; any identified copy or substantial portion of cft0808/edict | `third-party / MIT` | Upstream copyright and license remain independent; never claim exclusive project ownership or treat the material as relicensed under AGPL. |
| `references/benchmarks/cft0808-edict.yaml` | `local provenance record` | Records fixed upstream evidence; the metadata record does not make the upstream repository a runtime dependency or governing source. |
| `SKILL.md`, `references/court-core-contract.md`, `references/court-offices-dispatch.md`, court review/state-transition semantics | `upstream-inspired` | Local expression and implementation with acknowledged conceptual/structural influence from cft0808/edict. The label is not itself a finding of copied expression; retain provenance and review any suspected copy or adaptation under MIT. |
| Runtime dispatch, lifecycle, operation journal, semantic continuity and office-assignment scripts | `upstream-inspired / locally implemented` | No whole-file upstream match was found; architecture may reflect adopted dimensions such as mandatory review, liveness and audit trails. |
| Shared Shiguan storage, migration, privacy, host-memory and protected-locator implementation | `original / locally developed` | Project-specific Windows/runtime implementation; no known upstream runtime dependency. |
| Packaging, deterministic release, SBOM, manifest, legal/privacy checkers | `original / locally developed` | Project-specific release engineering; third-party notices remain separate inputs. |
| Standing profiles, office dossiers, fixtures, user/development manuals and bilingual documentation | `original or generated from local sources` | Generated files must trace to their local generator; current brand surfaces use Decretum Matrix（诏令矩阵） while historical/path locators are allowlisted. |
| Current A02 uncommitted changes | `AI-assisted / directed local work` | Produced under the direction of 孙华清 in this workspace; copyrightability and commercial relicensing treatment remain subject to legal review. |
| `assets/brand/decretum-matrix-icon.svg`, PNG, ICO and README | `project-directed original/generated artwork / LEGAL_REVIEW_REQUIRED` | Selected from user task `019f6691-258f-71a1-b63d-f7ad0b881d70`, latest v2 after node-alignment/symmetry repair. The maintainer declaration is in the bounded receipt. No third-party source is asserted; this is not independent title proof and is not cft0808/edict material. |
| Any file later shown to copy or adapt protected upstream expression | `modified-derived / MIT` | No such file was identified in the bounded review. If later evidence supports this classification, preserve upstream copyright/MIT and supersede the current matrix; never interpret zero current identifications as zero borrowing. |
| Any future external contribution | `unknown-needs-review until DCO + CLA accepted` | No inclusion in dual/commercial licensing until contribution and rights gates pass. |

## Existing contribution and rights-chain matrix

| Local metadata identity | Reachable commit count | Provisional rights treatment |
|---|---:|---|
| `@RowlandL` (GitHub ID `42199880`) | 12 | Maintainer account only. Commit attribution supports provenance but does not establish ownership, a separate legal identity or authority to relicense. |
| `Court Release Bot` | 17 | Automation identity, not a legal person. Treat content as operator-generated local release work only after confirming its inputs and operator authority; author metadata is not title evidence. |
| cft0808/edict contributors | independent upstream | MIT rights and copyright remain upstream; never include in a claim of exclusive ownership. |

The metadata-only `git log --all --format=%an%x09%cn` query returned 29 local
reachable commit rows. Author and committer counts were the same: `RowlandL=12`
and `Court Release Bot=17`. No other name appeared and no email was collected.
That is not proof that no other rights exist.

For `CLA_AND_RIGHTS_CHAIN_GATE`, each included file/module maps to one of:

1. verified original material for which 孙华清 controls the necessary rights; maintainer metadata for `@RowlandL` (GitHub ID `42199880`) does not itself establish ownership;
2. verified local automation output whose inputs and operator rights are recorded;
3. upstream/third-party material retained under its original license;
4. a contributor with an accepted DCO + CLA or retrospective written permission;
5. removed or cleanly rewritten material where rights cannot be established.

The 269-entry ordered matrix in the bounded receipt maps all current manifest
paths to `third-party`, `project-directed original/generated artwork`,
`upstream-inspired / locally implemented`, `project-directed generated local
surface`, `original / locally developed`, or `modified-derived` (none currently
identified). Gate:
`P3_CLA_AND_RIGHTS_CHAIN_GATE=PASS_WITH_LEGAL_REVIEW_REQUIRED`.

## Logo, artwork and brand-asset provenance gate

The product name is separate from rights in logo artwork and other assets. The
four files under `assets/brand/` are traced to their source task and revision in
the bounded review and are classified as project-directed original/generated
artwork under the maintainer declaration. Their legal title,
copyrightability and trademark enforceability remain `LEGAL_REVIEW_REQUIRED`;
no registered status or third-party source is claimed. Gate:
`LOGO_AND_ASSET_PROVENANCE_GATE=PASS_WITH_LEGAL_REVIEW_REQUIRED`.

## Current provenance gates

- `P1_UPSTREAM_MIT_PROVENANCE_GATE=PASS_WITH_LEGAL_REVIEW_REQUIRED`
- `P3_CLA_AND_RIGHTS_CHAIN_GATE=PASS_WITH_LEGAL_REVIEW_REQUIRED`
- `source_thread=019f6691-258f-71a1-b63d-f7ad0b881d70`
- `pending_body_access=NO`

## No-affiliation boundary

Decretum Matrix（诏令矩阵） is not affiliated with or endorsed by cft0808/edict, openclaw-sansheng-liubu contributors, GNU, the Apache Software Foundation or OpenAI. Necessary source descriptions and license notices do not imply sponsorship.
