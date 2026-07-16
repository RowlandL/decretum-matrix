# Decretum Matrix provenance and rights matrix

Status: `ACTIVE / LEGAL_REVIEW_REQUIRED`

This document records source and rights boundaries. It is not a warranty of title and is not legal advice.

## Project identity

- Product: `Decretum Matrix（诏令矩阵）`
- Canonical repository/skill/package name: `decretum-matrix`
- Legal owner, CLA licensor and trademark owner for material in which those rights are held: `孙华清`
- Public maintainer identity: `@RowlandL` (GitHub ID `42199880`)
- Stable protected install/Shiguan locators may retain `court-capability-router`; they are compatibility paths, not the current product identity.

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

A prior bounded audit compared the then-current 252 worktree files and all reachable local Git objects with the 222 blobs at the fixed upstream commit. Whole-file matches: `0`.

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
| Standing profiles, office dossiers, fixtures, user/development manuals and bilingual documentation | `original or generated from local sources` | Generated files must trace to their local generator; current brand surfaces use Decretum Matrix while historical/path locators are allowlisted. |
| Current A02 uncommitted changes | `AI-assisted / directed local work` | Produced under the direction of 孙华清 in this workspace; copyrightability and commercial relicensing treatment remain subject to legal review. |
| Candidate logo, icon and brand artwork, including any material associated with `work/decretum-matrix-icon` | `unknown-needs-review` until receipt exists | Do not publish, package or claim exclusive rights until source, generation process, author/rightsholder, license, exact path and SHA-256 are recorded. |
| Any future external contribution | `unknown until DCO + CLA accepted` | No inclusion in dual/commercial licensing until contribution and rights gates pass. |

## Existing contribution and rights-chain matrix

| Local metadata identity | Reachable commit count | Provisional rights treatment |
|---|---:|---|
| `@RowlandL` (GitHub ID `42199880`) | 11 | Maintainer account only. Commit attribution supports provenance but does not establish ownership, a separate legal identity or authority to relicense. |
| `Court Release Bot` | 17 | Automation identity, not a legal person. Treat content as operator-generated local release work only after confirming its inputs and operator authority; author metadata is not title evidence. |
| cft0808/edict contributors | independent upstream | MIT rights and copyright remain upstream; never include in a claim of exclusive ownership. |

No other human author name appears in the bounded reachable local commit metadata. That is not proof that no other rights exist.

Before `CLA_AND_RIGHTS_CHAIN_GATE` can pass, each included file/module must map to one of:

1. verified original material for which 孙华清 controls the necessary rights; maintainer metadata for `@RowlandL` (GitHub ID `42199880`) does not itself establish ownership;
2. verified local automation output whose inputs and operator rights are recorded;
3. upstream/third-party material retained under its original license;
4. a contributor with an accepted DCO + CLA or retrospective written permission;
5. removed or cleanly rewritten material where rights cannot be established.

## Logo, artwork and brand-asset provenance gate

The product name is separate from rights in logo artwork and other assets. No logo, icon, illustration, screenshot, font, template, generated image or other brand/release asset is cleared for official use until a receipt records its exact path and SHA-256, source, author/rightsholder, license, modifications, generation tool/process and applicable terms, plus approval by 孙华清. Absence from the current repository, or a claim that an asset was AI-generated, is not rights clearance. Until reviewed, such assets remain excluded from release packages, repository or social branding, marketing and exclusive-rights claims. Gate: `LOGO_AND_ASSET_PROVENANCE_GATE=LEGAL_REVIEW_REQUIRED`.

## No-affiliation boundary

Decretum Matrix is not affiliated with or endorsed by cft0808/edict, openclaw-sansheng-liubu contributors, GNU, the Apache Software Foundation or OpenAI. Necessary source descriptions and license notices do not imply sponsorship.
