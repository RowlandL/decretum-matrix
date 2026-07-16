# Changelog

## beta0.5.10 — 2026-07-16

### Added

- Added the canonical Decretum Matrix（诏令矩阵） identity, `decretum-matrix`
  skill/package name, `$decretum-matrix` invocation, and role-prefixed ordinary
  office dossier/preload contracts.
- Added body-bound semantic continuity, P00 bounded dispatch/resume packets,
  idempotent decree/closeout operation receipts, office-carrier lifecycle
  checks, capability recruitment, and current-tool install projection tests.
- Added `AGPL-3.0-only` community licensing, separate commercial-license
  notice, DCO + CLA governance, trademark policy, authorship metadata, and
  explicit upstream MIT provenance.

### Changed

- Renamed the local repository, managed worktree namespace, release artifacts,
  documentation, SBOM, and release manifest to `decretum-matrix`; the protected
  `court-capability-router` install/archive/Shiguan locators remain explicit
  compatibility surfaces.
- Updated the release artifact contract to
  `decretum-matrix-beta0.5.10.zip` while retaining the stable ZIP internal root
  `court-capability-router/` for existing installations.
- Decoupled the Decretum Matrix kernel from any named Superpowers methodology;
  optional workflow skills remain ordinary bounded tool invocations.

### Fixed

- Closed semantic-binding fixture drift, ministry authority overreach,
  preload-source reachability, Windows 8.3 temporary-root false positives,
  stage validation without Git metadata, portable bytecode ordering, and
  deterministic package privacy regressions.

### Release and compatibility notes

- `beta0.5.9` remains an immutable historical Apache-2.0 release. Its grants are
  not withdrawn; the AGPL cutover applies to the new `beta0.5.10` community
  release candidate.
- The `cft0808/edict` MIT notice and fixed commit provenance remain independent
  and complete. Zero whole-file blob matches are not represented as zero
  influence or zero borrowing.
- This entry records a locally verified candidate. Remote push, tag, PR and
  GitHub Release remain separate acceptance actions and are not claimed here.
- Tagless candidates now use a reusable, no-clobber commit directory with an
  external candidate receipt. Final release attestation remains annotated-tag-only.

## beta0.5.9 — 2026-07-12

### Added

- Imported `COURT-DYNMSG-BUDGET-V1-20260712`: dispatch-message budget floor 6000, allocation quantum 1000, and ceiling 12000.
- Added Apache-2.0 project licensing, `NOTICE`, contributor/provenance rules, security and privacy policies, an SPDX 2.3 SBOM, and the complete upstream MIT notice for `cft0808/edict` commit `14a207557719c046af0f993a7bff1cc5a5015b33`.
- Added a strict v2 payload manifest, legal gate, capability-index gate, package regression gate, and immutable artifact-builder gate.
- Added exclusive final release directories containing the ZIP, SHA256 sidecar, source/tag/tree attestation, release notes, and SBOM.

### Changed

- Resolved capability-index checks through the shared Shiguan root instead of a stale skill-local catalog.
- Made ZIP output byte-reproducible with stored entries, a fixed timestamp and mode, UTF-8 path ordering, stable source reads, and no-clobber publication.
- Made Shiguan Web services loopback-only by default. LAN binding now requires explicit `--host 0.0.0.0`; non-loopback peers require HTTPS, reject redirects and embedded credentials, and never forward bearer tokens to another origin.
- Classified the strict superCC runtime truth check as conditional runtime evidence. Ordinary `super` release checks report `NOT_APPLICABLE` with reason `runtime_not_selected` when runtime checks are not selected.

### Fixed

- Rejected malformed release manifests without uncaught exceptions and detected missing, extra, reordered, or hash-drifted package payloads.
- Closed quoted-JSON secret-redaction gaps and documented that `.shiguan-key` obfuscation is not encryption.
- Hardened source copying and package publication against symlink/reparse traversal, source replacement races, late competing outputs, and accidental overwrite.

### Release and compatibility notes

- `beta0.5.8`, its tag, and every historical artifact remain immutable; this release neither overwrites nor deletes them.
- The package embeds no Git remote, GitHub account, access token, credential helper state, or authenticated publication configuration.
- Physical host child-thread reclamation remains unverified and is not claimed fixed in this release.
- Apache-2.0 applies only to material the contributors have the right to license. Publication must stop if ownership, copied material, trademarks, privacy consent, or third-party provenance is unresolved.

## beta0.5.8 — 2026-07-11

### Changed

- Standardized production configuration on Multi-Agent V2 with 16 whole-tree slots, including the root, and maximum depth 4.
- Clarified that the Six Ministries are non-visible and silent until bounded Shangshu dispatch.

### Fixed

- Removed legacy `[agents].max_threads` from recommended V2 configuration.
- Corrected package documentation: `plan-archives` and `memory-decisions`, including placeholder READMEs, are not ZIP contents.
- Replaced the fail-open package denylist with a case-insensitive, fail-closed portable path policy.
- Rejected unknown directories, symlink/junction/reparse entries, nested archives, Zip Slip paths, duplicate/case-colliding members, binary payloads and compression bombs.
- Promoted historical/generated-runtime zero budgets from warnings to release hard failures.
- Removed a secret-like test fixture false positive while preserving the original transaction test.

### Added

- Added `VERSION`, `RELEASE-LOG.md`, root `release-manifest.json`, an external SHA256 sidecar and Git-tree-to-ZIP verification.
- Added 20 package privacy regression tests.

### Privacy

- This release contains no personal Shiguan records, plan archives, memory decisions, raw logs, sessions, credentials, Obsidian secrets, peer/import/runtime state, backups or host-local generated indexes.
