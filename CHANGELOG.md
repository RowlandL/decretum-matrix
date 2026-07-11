# Changelog

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
