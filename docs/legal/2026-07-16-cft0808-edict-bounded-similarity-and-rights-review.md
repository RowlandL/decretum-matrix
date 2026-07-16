# cft0808/edict bounded similarity and rights review

Receipt: `DM-LPR-P1-P3-20260716`

Status: `PASS_WITH_LEGAL_REVIEW_REQUIRED`

This receipt records a bounded technical provenance review and a maintainer
rights declaration. It is not a warranty of title, a copyrightability opinion
or legal advice. No pending body or full-history file body was opened, copied,
moved or hashed.

## 1. GitHub primary-source capture

- Repository: `https://github.com/cft0808/edict`
- Fixed commit: `14a207557719c046af0f993a7bff1cc5a5015b33`
- Git tree: `7b44f37128938137493fe07be85aad99408fb54a`
- Commit author/date from the GitHub Git API: `cft0808`,
  `2026-05-06T15:01:33Z`
- Tree API result: `truncated=false`, `223` blob entries; excluding `LICENSE`
  leaves the previously reviewed `222` payload blobs.
- Fixed codeload archive:
  `https://codeload.github.com/cft0808/edict/zip/14a207557719c046af0f993a7bff1cc5a5015b33`
- Archive bytes: `49,776,552`
- Archive SHA-256:
  `16aa03be260c13ee3cee7044c074a0df3a8e84b7478c6450ae9e77c4822f7fda`
- Extracted file count: `223`
- Upstream LICENSE Git blob SHA-1:
  `69499c3250cbecc6079c69dc0e5a0f7a4be716da`
- Upstream LICENSE bytes: `1,093`
- Upstream LICENSE SHA-256:
  `5f67c084a1b5bd87409f05221d5985cde0b99472aa34670613761e614330d93c`

The MIT hash and copyright boundary match `THIRD_PARTY_NOTICES.md` and
`references/benchmarks/cft0808-edict.yaml`. The archive was used only from a
temporary directory.

## 2. Bounded comparison scope

Local semantic-core scope (`18` files):

1. `SKILL.md`
2. `README.md`
3. `references/court-core-contract.md`
4. `references/court-offices-dispatch.md`
5. `references/court-capability-registry.md`
6. `references/court-state-runtime-agents.md`
7. `references/court-closeout-validation.md`
8. `references/edict-registry-import.md`
9. `scripts/court_runtime.py`
10. `scripts/court_cli.py`
11. `scripts/court_dispatch_policy.py`
12. `scripts/court_intake_gate.py`
13. `scripts/court_outcome_gate.py`
14. `scripts/court_operation_journal.py`
15. `scripts/court_semantic_continuity.py`
16. `scripts/court_office_bootstrap.py`
17. `scripts/court_multi_agent_protocol.py`
18. `scripts/court_agent_admission.py`

The ordered path/size/SHA-256 scope fingerprint is
`6a117ebc561b5211d5b39fa4f800b1b47a23b5c155fe9f5633bdc3c0d100d3e6`.
The upstream comparison set was every Markdown and Python file at the fixed
commit: `113` files. Same-kind local/upstream pairs: `1,040`.

The then-current `release-manifest.json` input had SHA-256
`7f4ef971cb8bfe274818ef5c39a78f1c810326dc85071068790950fbf549e2e9`
and `269` file entries. Comparing those declared whole-file SHA-256 values with
all `223` extracted upstream files produced
`whole_file_sha256_intersection_count=0`.

That exact-file result does not mean zero borrowing. It does not exclude
rewritten fragments, structural influence, selected concepts or semantic
adaptation. It is retained only as one bounded signal.

## 3. Reproducible rules and thresholds

All text is decoded as UTF-8 with replacement for invalid bytes. No OCR or
image comparison is included.

1. Normalized-text metric: Unicode NFKC, case-fold, retain ASCII
   letters/digits/underscore and CJK characters, replace other characters with
   spaces, collapse whitespace, then calculate set Jaccard over 12-character
   shingles. Review threshold: `0.08`.
2. Token-shingle metric: tokens are ASCII identifiers, numbers or individual
   CJK characters; calculate set Jaccard over 5-token shingles. Review
   threshold: `0.05`.
3. Exact normalized long-line metric: retain normalized lines of at least 24
   characters. Review when containment against the smaller set is at least
   `0.15` or there are at least `3` exact long lines.
4. Python structure metric: `0.70 * cosine(AST node-type counts) + 0.30 *
   Jaccard(function/class name tokens)`.
5. Markdown structure metric: `0.60 * cosine(heading/list/fence/table/quote
   counts) + 0.40 * Jaccard(heading tokens)`.
6. Structure review threshold: `0.75`. Structure alone is a triage signal and
   cannot establish copied expression.

## 4. Top hits and manual adjudication

| Local | Upstream | char-12 | token-5 | long-line containment | exact long lines | structure |
|---|---|---:|---:|---:|---:|---:|
| `scripts/court_cli.py` | `edict/backend/app/channels/webhook.py` | 0.033441 | 0.007246 | 0.250000 | 1 | 0.590074 |
| `scripts/court_cli.py` | `edict/backend/app/channels/base.py` | 0.032215 | 0.000000 | 0.250000 | 1 | 0.553482 |
| `scripts/court_operation_journal.py` | `scripts/file_lock.py` | 0.031892 | 0.007905 | 0.000000 | 0 | 0.728862 |
| `scripts/court_runtime.py` | `dashboard/server.py` | 0.011592 | 0.000405 | 0.000000 | 0 | 0.720490 |
| `scripts/court_runtime.py` | `edict/backend/app/workers/dispatch_worker.py` | 0.006184 | 0.000177 | 0.004049 | 1 | 0.709242 |

Results:

- No pair reached the normalized-text or token-shingle threshold.
- No pair reached the structure threshold.
- `15` pairs reached the long-line containment threshold only because
  `scripts/court_cli.py` has four qualifying long lines and shared the single
  standard Python directive `from __future__ import annotations` with those
  upstream files. No pair had three exact long lines.
- The additional exact line in the `court_runtime.py` / `dispatch_worker.py`
  sample was the standard import `from datetime import datetime, timezone`.
- Manual inspection of the top structure pairs found different function/class
  names and project-specific state, journal, gate and dispatch contracts.

Adjudication: `NO_MATERIAL_TEXTUAL_MATCH_IDENTIFIED_IN_BOUNDED_SCOPE`.
This is not a non-infringement finding. The three-departments/six-ministries
review flow, mandatory review, state transitions, liveness and audit concepts
remain acknowledged as `upstream-inspired`. Any later identified copied or
adapted protected expression must be reclassified and retained under MIT.

## 5. Current package rights matrix

The `269` manifest entries were assigned by ordered, mutually exclusive module
rules. The default/catch-all classification relies on the maintainer declaration
below and remains `LEGAL_REVIEW_REQUIRED`; it is not inferred from NOTICE,
AUTHORS, commit metadata or checker success.

| Classification | Count | Ordered scope and treatment |
|---|---:|---|
| `third-party` | 3 | `LICENSE` is the unmodified AGPL text; `THIRD_PARTY_NOTICES.md` contains the independent upstream MIT notice; `references/benchmarks/cft0808-edict.yaml` is the local record of that MIT source. No third-party text is claimed exclusively by the project. |
| `project-directed original/generated artwork` | 4 | `assets/brand/*`; selected v2 icon receipt and hashes are listed below. Not part of the cft0808/edict MIT boundary. |
| `upstream-inspired / locally implemented` | 114 | `SKILL.md`, named court semantic references, office dossiers/profiles and court/superCC/semantic runtime families. Local expression is declared project-directed; conceptual/structural influence remains disclosed. |
| `project-directed generated local surface` | 14 | Remaining `agents/*`, `references/manifests/*` and `references/sections/*` after earlier rules. Generator/source traceability remains required. |
| `original / locally developed` | 134 | Remaining release, Shiguan, storage, privacy, install, packaging, validation, documentation and runtime files under the maintainer declaration. This is a provenance classification, not conclusive legal title. |
| `modified-derived` | 0 identified | No file was classified as modified-derived from upstream protected expression in this bounded review. This does not mean zero borrowing; any later supported finding supersedes this row and preserves MIT. |

Count check: `3 + 4 + 114 + 14 + 134 + 0 = 269`.

## 6. Maintainer declaration and reachable identity metadata

The user, acting as project maintainer, expressly declares `孙华清` as the
project rights subject and CLA licensor for project-directed material. The
public GitHub maintainer identity remains only `@RowlandL` (GitHub ID
`42199880`); it is not expanded into a second legal identity. This declaration
does not transfer third-party rights, establish copyrightability, prove every
employment/client clearance or replace qualified legal review.

Metadata-only command `git log --all --format=%an%x09%cn` returned `29`
reachable commit rows:

| Metadata identity | Author count | Committer count | Treatment |
|---|---:|---:|---|
| `RowlandL` | 12 | 12 | Git metadata for the public maintainer identity; not title evidence by itself. |
| `Court Release Bot` | 17 | 17 | Local automation identity, not a legal person or external contributor. Inputs and operator authority follow the maintainer declaration and remain legally reviewable. |

No other author or committer name appeared in that bounded metadata query. No
email address was collected or recorded. Absence of another name does not prove
absence of another right.

## 7. Brand asset receipt

Classification: `project-directed original/generated artwork /
LEGAL_REVIEW_REQUIRED`.

- `source_thread=019f6691-258f-71a1-b63d-f7ad0b881d70`
- `latest_selected=v2_after_node_alignment_and_symmetry_fix`
- `assets/brand/decretum-matrix-icon.svg`: `4,155` bytes, SHA-256
  `38566711fcf9bc308c411d6d42fa3fd5a89e28e376caf20cea935383cc597163`
- `assets/brand/decretum-matrix-icon-256.png`: `35,682` bytes, SHA-256
  `05894a5620385ede86b3fae5e7e4862e95c1dbc248636b2533ff107f97aabe28`
- `assets/brand/decretum-matrix-icon.ico`: `57,232` bytes, SHA-256
  `0799777bf8d9113e6ab0bdcd4aa7e6639c816684eaf17956abef2bdad2dc585b`
- `assets/brand/README.md`: `777` bytes, SHA-256
  `496089d5cfe918d60e6b1ef09adc612d97c38f79b1b0e781c4015ec2432a1d9c`

All four files matched their current release-manifest size and SHA-256 entries.
The asset README records the selected revision, transparency boundary, no
registered-trademark claim and no asserted third-party source. Those statements
are maintainer provenance declarations, not independent proof. These assets are
not classified as cft0808/edict material and do not narrow the upstream MIT
grant.

## 8. Gate result

- `P1_UPSTREAM_MIT_PROVENANCE_GATE=PASS_WITH_LEGAL_REVIEW_REQUIRED`
- `P3_CLA_AND_RIGHTS_CHAIN_GATE=PASS_WITH_LEGAL_REVIEW_REQUIRED`
- `pending_body_access=NO`

P1 passes because the fixed primary source, MIT boundary, exact-file result,
three-axis thresholds, top hits and human adjudication are recorded while the
influence disclosure remains conservative. P3 passes as a governance gate
because every current manifest entry maps to an ordered rights class, the
maintainer declaration is explicit, the two reachable metadata identities are
accounted for, the brand assets have a receipt and third-party rights remain
separate. Both results remain subject to legal review and must be reopened if a
new contributor, source, asset or material similarity finding appears.
