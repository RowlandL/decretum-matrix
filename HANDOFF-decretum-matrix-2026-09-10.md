# HANDOFF beta1.1.2 closeout

Date: 2026-09-10 local time
Branch: `release/beta1.1.2`
Latest pushed source commit before this handoff update:
`7b910d4409fdf7c7e651cfa72353e362baf7d643`

## Scope

This handoff closes the beta1.1.2 source-gate and local-install remediation for
portable paths, DeepSeek Harness, Hermes, and GitHub Actions. It records the
final verified state and the remaining boundaries. It does not claim package,
native runtime, or full release acceptance beyond the evidence listed here.

## Source Changes Closed

| Commit | Purpose |
| --- | --- |
| `0deef0b26fac52655c918ac91412f6c61e2e709c` | Enforce portable source path checks and reject workstation roots in formal source/package candidates. |
| `b50a0a394bf5494183227cf79890324764b0d63f` | Normalize runtime path comparisons across Windows aliases and POSIX real paths. |
| `8182bcce7d732ae244dc85d3a13f5f91ec539983` | Recognize Hermes receipt roots across host layouts. |
| `7b910d4409fdf7c7e651cfa72353e362baf7d643` | Treat `package-entrypoint` `NOT_CONFIGURED` as CI-neutral in required summary. |

Root causes closed:

- Direct path string comparisons rejected equivalent host paths.
- Hermes receipt root recognition was incomplete across platform user-data roots.
- Required CI summary incorrectly treated intentionally unconfigured package
  entrypoint status as a blocking source failure.
- Formal source had no fail-closed workstation-root scan; `check_portability.py`
  now covers formal source text and portable package candidate text.

## Verified Evidence

| Check | Result |
| --- | --- |
| `python -B scripts/check_release_gate.py --self-test --json` | PASS |
| `python -B scripts/checks/check_source_state_budget.py --json` | PASS after final handoff rewrite; portable source `9,297,021 / 9,300,000` bytes |
| `python -B scripts/check_release_gate.py --phase source --json` | PASS; source layer `PASSED`, failed list empty |
| `python -B scripts/check_portability.py .` | PASS; formal source leaked count `0`, portable candidate leaked count `0` |
| `git diff --check` | PASS |
| GitHub Actions run `34403127274` | PASS; Ubuntu, Windows, macOS, aggregate, package-entrypoint, and required-summary all succeeded |

GitHub emitted Node 20 deprecation annotations for pinned setup actions. They
were warning annotations only and did not block the run.

## Local Install State

- Active-copy sync returned `status=PASS`.
- Shared agent skill root and current Codex skill root were applied/current.
- 14 Codex agent role profiles were `synced`.
- DeepSeek Harness web-desktop MCP config and Hermes MCP config both point to
  the shared agent skill root for Decretum Matrix.
- No DSH app-local skill copy was created because the current DSH MCP config
  already consumes the shared root.
- Hermes platform-local compatibility skill copy had its existing
  `scripts/checks/check_release_gate.py` updated. Source/destination SHA-256:
  `8f183d1f73468852ba5dd8617a576413ae24b264bcd7789a0f368b972d85725d`.

## Path Portability Decision

Runtime source, CI config, `references/`, `SKILL.md`, `package.json`,
`release-manifest.json`, and `VERSION` were scanned for workstation absolute
roots after the fix and had no matches. Historical docs/logs/handoff/evidence
files still preserve old host paths as append-only evidence; they are not
formal runtime source or install projection input.

Future handoffs should prefer updating this existing file over adding a new
top-level or docs handoff path, because `release-manifest.json` itself counts
against the portable byte budget.

## Boundaries And Risks

- This closeout proves the source gate and active local installation state only.
- Portable source byte budget is very tight. Rerun
  `python -B scripts/checks/check_source_state_budget.py --json` after any
  source or handoff edit.
- Do not bulk-rewrite historical evidence paths without a separate
  evidence-preservation decision.
- Package-entrypoint remains intentionally `NOT_CONFIGURED`; current policy is
  CI-neutral while all source-contract jobs and required summary must pass.
