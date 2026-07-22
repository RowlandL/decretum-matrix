# Changelog

## beta1.0.4-hotfix-v1 - 2026-07-22

### Fixed

- Restored `references/benchmarks/cft0808-edict.yaml` to the release ZIP, npm
  carrier, and all five installation projections as a frozen reference.
- The installer makes that reference read-only after each sync and temporarily
  unfreezes it only to apply a later release replacement.
- The frozen reference remains outside runtime loading and does not restore any
  post-install hash-validation behavior.
- Replaced stale hierarchy-receipt hash references with the existing manifest
  path provenance, restoring the fast startup and admission paths without
  reintroducing runtime hash checks.
- Retired nine source-only Shiguan service and checker compatibility adapters
  from the public CLI surface.
- Updated superCC profile/dossier regression evidence to use declared paths and
  identity bindings instead of obsolete profile or dossier digest fields.
- Kept archive closeout verification on its objective receipt id, path, lineage,
  and closeout identity; it no longer expects retired receipt or archive digests.

### Release identity

- Product/tag/artifact version: `beta1.0.4-hotfix-v1`.
- npm version: `1.0.4-beta.0.hotfix.1` on the `beta` dist-tag.
- `beta1.0.4` and `1.0.4-beta.0` remain immutable predecessor evidence.

## beta1.0.4 - 2026-07-22

### Fixed

- Restored short no-write closeout as a real `结诏` path: even compact probes now
  carry `史馆实录` and `记忆裁定`, with a lightweight archive checkpoint when
  the host can write.
- Restored the opening choice surface to authority plus explanation, with a
  separate `serial/parallel` selector that can be driven from keyboard or mouse
  in the supported client surfaces.
- Kept the installed runtime surface narrow and removed the old active-copy
  hash-check gate from release manifests and install-facing guidance.
- Accepted an already-migrated shared Shiguan topology when legacy locators are
  junctions to the canonical root, so Hermes closeout can generate `court_code`
  and `ancient_lineage` instead of reporting missing cutover evidence.
- Blank-host npm installation now accepts only structural ZIP checks at runtime;
  any future temporary bootstrap validator must be removed before activation, and
  the installed skill keeps no release manifest or release-validation helper.

### Release identity

- Product/tag/artifact version: `beta1.0.4`.
- npm version: `1.0.4-beta.0` on the `beta` dist-tag.
- Published as the `beta1.0.4` prerelease with its matching branch, tag, assets,
  and npm package on the `beta` dist-tag.

## beta1.0.3 - 2026-07-21

### Fixed

- Kept the established progressive court flow while removing blanket startup
  probes for Git, Shiguan services, pending imports, YOLO, capability refresh,
  portable bootstrap, install, and release tooling.
- Reframed `court open --fast` as optional pre-dispatch preparation. It no
  longer selects every ministry by default or reports packet/admission checks as
  physical child dispatch.
- Kept the Three Departments flow intact and moved Six Ministry selection to
  Shangshu's result-driven, bounded subset after the Taizi reply.

### Release identity

- Product/tag/artifact version: `beta1.0.3`.
- npm version: `1.0.3-beta.0` on the `beta` dist-tag.
- This branch is a local candidate; publication requires separate authorization.

## beta1.0.2 - 2026-07-21

### Changed

- Reframed Decretum Matrix as an edict-centered multi-agent collaboration
  skill whose default formal path is Three Departments and Six Ministries, with
  scene-appropriate routing for casual chat, light tasks, formal tasks,
  corrections, continuations, and explicit closeout.
- Preserved beta0.5.9 capabilities and explicit later additions while
  separating ordinary skill runtime from project-level release, install, legal,
  manifest, and package gates.
- Restored Shiguan base memory as the normal record/query layer, kept GBrain as
  a consolidation/organization layer, and kept Shiguan Git Federation as an
  explicit management function.
- Tightened authority/behavior wording so `approval|autonomous|super` remain
  authorization boundaries and `serial|parallel` remain execution modes.
- Repaired external-CWD CLI behavior so user relative paths are resolved from
  the caller directory while project check/release commands still run from the
  code root.

### Release identity

- Product/tag/artifact version: `beta1.0.2`.
- npm version: `1.0.2-beta.0` on the `beta` dist-tag.
- Remote publication status is proven only by later remote rereads.

## beta1.0.1 - 2026-07-20

### Fixed

- Made `approval|autonomous|super` authority independent from
  `serial|parallel` behavior across native and superCC execution receipts.
- Split native and superCC startup, imports, task stores, dossiers, transport,
  admission, and lifecycle; only neutral office configuration hashes are shared.
- Repaired the semantic-context producer/consumer boundary so an invalid
  authority revision fails closed with zero dispatch and no manual bypass.
- Resolved and cached a skill/MCP/plugin/CLI/script capability snapshot before
  Three Departments deliberation without spawning libu-hr for a read.
- Kept warm court-open p50 inside the accepted 10% regression budget while
  preserving one-process startup and the 20 KiB preload ceiling.

### Release identity

- Product/tag/artifact version: `beta1.0.1`.
- npm version: `1.0.1-beta.0` on the `beta` dist-tag.

## beta1.0.0-hotfix-v2 - 2026-07-20

### Fixed

- Forced the packaged Python launcher to reconfigure stdout/stderr as UTF-8,
  preventing Windows GBK `npm postinstall` from failing while printing a
  structured receipt containing replacement characters.
- Added a behavioral GBK stream regression to the unified CLI gate so the
  launcher must encode `U+FFFD` as UTF-8 rather than relying on host code pages.

### Release boundary

- Product/tag/artifact version: `beta1.0.0-hotfix-v2`.
- npm version: `1.0.0-beta.0.hotfix.2` on the existing `beta` dist-tag.
- Published `hotfix-v1` remains immutable evidence and is superseded rather
  than overwritten.

## beta1.0.0-hotfix-v1 - 2026-07-20

### Fixed

- Decoupled ordinary super parallelism from the explicit superCC runtime at the
  carrier layer. Shared standing profiles remain single-source, while ordinary
  Codex roles resolve only `agents/office-dossiers` and explicit visible carriers
  resolve only `agents/supercc-dossiers`.
- Removed superCC validation and topology fields from the ordinary runtime probe,
  so the ordinary path no longer imports, probes, or reports the visible runtime.
- Made `decretum-matrix shiguan archive-checkpoint` return a UTF-8 structured
  receipt with archive/receipt hashes and exact closeout identity lines.
- Rejected model-allocated decree identifiers and lineages: a fourteen-line
  closeout now requires the current CLI archive receipt, otherwise a non-closeout
  response family must be used.
- Re-compacted the root skill without relaxing the 20 KiB preload ceiling;
  maximum role preload is 20,173 bytes and measured cold/warm p50 improvements
  remain 88.60%/99.33%.

### Release boundary

- Product/tag/artifact version: `beta1.0.0-hotfix-v1`.
- npm version: `1.0.0-beta.0.hotfix.1`, preserving the existing
  `1.0.0-beta.0` package as immutable registry evidence.
- Publication, tag, assets, installation, and Latest status are asserted only by
  the final hotfix receipts.

## beta1.0.0 - 2026-07-19

### Added

- Added a local-only shared Shiguan Git management hub with an explicit tracking
  allowlist, independent Codex/Claude Code/Hermes native memory repositories,
  reciprocal managed links, stable registry entries, and paired commit receipts.
- Added authorized blank-host bootstrap for canonical Codex, Claude Code, and
  Hermes memory roots while keeping probe mode read-only.
- Added concise GitHub release metadata as a mandatory source gate and restored
  the packaged brand icon to the repository README.

### Changed

- Aligned VERSION, SBOM, release manifest inputs, package artifacts, npm
  candidate identity, and release-facing documentation to beta1.0.0.
- Added a governance-neutral framework contract, shared Shiguan GBrain recall,
  and a default official 三省六部 adapter backed by the existing hierarchy.
- Added one non-default direct-review reference implementation to validate
  replacement without adding runtime, evidence, or memory authorities.
- Added a four-dimension request-understanding gate with a 95 sufficiency
  threshold, one-question clarification, bounded options, and clear-request
  direct execution.
- Activated the single final-stage branch from the accepted beta0.5.13 baseline
  and jumped directly to beta1.0.0 without creating an intermediate beta0.5.x
  release branch or another worktree.
- Extended GBrain recall with path-private Git provenance while preserving
  advisory authority, current-decree precedence, and cross-governance ordering.

### Fixed

- Closed the deferred shared-Shiguan managed-Git and native-memory reciprocal
  link gap without reading pending bodies or introducing a remote/service/DB.
- Fixed non-ASCII Shiguan filenames being misclassified by Git quoted-path output.
- Fixed empty native-memory glob pathspecs and same-transaction recovery for an
  initialized repository that had not yet created its first commit.

### Release boundary

- The original beta1.0.0 tag, GitHub assets, and npm `1.0.0-beta.0` package are
  published baseline evidence. This coverage revision does not claim to have
  replaced them until a new candidate/install/publication receipt closes.
- All 43 candidate source steps now have passing evidence, including concise
  release metadata, Shiguan Git federation, governance, privacy, and measured
  CLI performance. Live install and publication remain separately gated.
- GitHub release bodies were shortened and beta1.0.0 was marked Latest without
  changing the existing tag or five release assets.

## beta0.5.13 - 2026-07-19

### Added

- Added the `decretum-matrix` npm executable and lazy unified CLI registry while
  retaining verified compatibility adapters for existing entrypoints.
- Added single-process `court open --fast`, structured result attribution, and
  deterministic cold/warm performance gates.
- Added managed-file install backups plus explicit rollback for direct atomic
  overwrite updates.
- Added a bounded npm `postinstall` that verifies the embedded release ZIP,
  installs the canonical `.agents` runtime, creates or atomically migrates the
  physical Shiguan root, and emits durable rollback receipts.

### Changed

- Compacted root skill and role preloads to stay below 20 KiB while resolving
  detailed behavior through direct governing references.
- Expanded release gates to cover unified CLI, fast-open, result semantics, and
  measured performance; source audit steps now isolate temporary Git indexes.
- Aligned VERSION, SBOM, package, payload, artifact, and npm candidate identity
  to beta0.5.13.

### Fixed

- Removed the V2/legacy agent-type protocol conflict at the CLI boundary.
- Kept protected Shiguan record, index, evidence, and data paths outside install
  reads and writes while retaining managed-file backup and rollback coverage.
- Added the current `release-manifest.json` to every managed skill projection so
  installed VERSION, identity, payload index, and release identity converge.
- Made successful legacy skill-directory migrations explicitly rollbackable,
  including the zero-file-delta case, and reject canonical Shiguan links or
  dual physical roots before mutation.
- Bound autosync sidecars to the generated pending filename and timezone-aware
  import timestamp without reading pending bodies.
- Restored discovery of public legacy court commands in unified top-level help.
- Corrected remaining current-product naming, canonical package-root, bytecode,
  fixture-index, and release-builder contract drift.

External push, tag, GitHub Release, npm publication, assets, and final host
installation remain receipt-gated and are not asserted by this source entry.

## beta0.5.12 - 2026-07-18

### Added

- Added versioned offline Wiki pages for installation, usage, governance,
  architecture, troubleshooting, and release notes, plus a read-only
  online/offline consistency checker.

### Changed

- Aligned VERSION, SBOM, package, manifest, artifact, and npm candidate identity
  to beta0.5.12.
- Reduced README to the product, shortest install command, shortest invocation,
  and documentation entry points.
- Converged shared Shiguan and Obsidian paths on the canonical
  `.agents/court-shiguan/decretum-matrix/references` root.

### Fixed

- Restored protected Shiguan anchors and legacy semantic bootstrap recovery.
- Fixed host-memory/child-trace gates and package synthetic-secret fixtures.
- Fixed stale host skill locators and repair holds that blocked native
  `$decretum-matrix` discovery after the install-directory migration.

External tag, GitHub Release, npm publication, assets, and online Wiki remain
receipt-gated and are not asserted by this source entry.

## beta0.5.11 — 2026-07-17

### Added
- RB1 added atomic admission around the shared hierarchy/profile gate, rejects zero-mutation denials without state writes, and binds v2 lease/preload evidence to an append-only admission event anchor.
- RB2 added the normal `superCC` shared delivery preflight, identity ACK, `preload_pending -> delivery success`, `ENTER_DISPATCH` P00 context, and an atomic delivery/state chain with correction-gap coverage.
- Added formal closeout identifier validation: `SCGSDYJM-20260606-1Z-DAAA` is the positive decree-code example, and lineage is exactly `史馆总纪·朝制志·官署门·三省六部纲·回复格式目·结诏标识条·内容谱系诏`; `CCR`, `Phase`, `RB`, task ids, and workflow paths are rejected as lineage.
- Added the bounded source split for dispatch contract, delivery, admission contract, and autosync projection modules, plus a live source-state focused checker.

### Changed
- The current display identity is exactly `Decretum Matrix（诏令矩阵）`; `诏令矩阵` is explanatory only, while machine/package/invocation remain `decretum-matrix` / `$decretum-matrix`.
- Shiguan Web/autosync uses atomic state transitions, a filesystem preserve-only primary channel, optional non-blocking REST, and asynchronous refresh requests for an existing daemon.
- Expanded the release policy to 42 manifest steps: 37 source, 4 installation, and 1 conditional runtime step; candidate pre-install selects 36 source steps and normal post-install selects 5.
- The canonical physical install authority is `skills/decretum-matrix`; the ZIP internal root remains `court-capability-router/`, any legacy install locator must resolve to the same authority, and host migration remains `NOT_RUN`.
- The beta0.5.11 release source tree measures 273 portable files / 6,138,661 bytes against the unchanged ceiling of 275 files / 6,200,000 bytes.

### Fixed
- Aligned the intervention baseline with production caller/direct-superior edges, bounded child ownership/write scopes, serial no-mutation behavior, canonical preloads, and the 16-slot tree cap.
- Closed admission-to-start and `superCC` delivery TOCTOU gaps before any persistent state transition.
- Repaired Shiguan WebUI autosync controls, busy-state handling, local-only errors, daemon freshness, and preserve-only refresh transitions.

### npm backfill and release boundaries
- The public GitHub Packages `beta` dist-tag currently resolves to the immutable `0.5.10-beta.0` release-assets carrier. It has no dependencies or lifecycle scripts and does not modify skill directories.
- `0.5.11-beta.0` npm publication is `NOT_RUN`; after release, the dist-tag and online install must be verified before that state changes. Any required authentication is limited to `read:packages` through process-scoped `NODE_AUTH_TOKEN` and a temporary npmrc, with no token persistence.
- `pending_body_access=NO`; no pending body was opened, hashed, moved, deleted, or marked seen.
- `beta0.5.10` remains immutable historical release/lineage evidence.
- Candidate, installation, tag, push, GitHub Release, npm publication, and asset success require their own later receipts and are not asserted here.

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
  release.
- The `cft0808/edict` MIT notice and fixed commit provenance remain independent
  and complete. Zero whole-file blob matches are not represented as zero
  influence or zero borrowing.
- This entry records the release payload and local acceptance. Remote
  publication is proven only by its external tag, release and asset receipts;
  repository text alone never claims those actions succeeded.
- Tagless candidates now use a reusable, no-clobber commit directory with an
  external candidate receipt. Final release attestation remains annotated-tag-only.
- Final promotion requires the exact accepted candidate SHA-256 and rejects a
  mismatch before creating the final version directory.

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
