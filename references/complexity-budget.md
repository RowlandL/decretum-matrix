# Complexity Budget

This skill must keep routine review fast and local.

- Prefer existing governing references and small validators over new frameworks.
- Add a validator when it prevents a known recurrence; avoid broad rewrites for
  one-off wording fixes.
- Keep Web/API/network-security changes out of non-Web rectification batches
  unless the newest decree explicitly includes them.
- Large generated files and private state must stay outside portable release
  authority. When a generated artifact must be refreshed, record the generator
  and validation command instead of treating the artifact as hand-authored.
- Fast review path: `quick_validate.py`, `check_catalog.py --strict`,
  `check_portability.py`, `check_supercc_profiles.py`,
  `check_codex_agent_roles.py`, `check_active_copy_hashes.py --json`, and
  `check_supercc_functional.py --workspace . --json --diagnose`.

## 2026-07-11 Measured Revision

The portable-source ceiling is deliberately revised from 185 files / 2.65 MB
to 190 files / 2.95 MB. This is not a hidden allowance for copied history: the
new measured source consists of separated protocol selection/launcher modules,
append-only pending governance, and the single-writer Obsidian config CAS layer.
`references.imported-*`, Shiguan backups, runtime ledgers, pending bodies,
bytecode, caches, plans, memories, and local config remain excluded and retain a
zero-target warning.

The line budgets now name the new production modules explicitly. The modest
increase for `serve_shiguan_tree.py` and `shiguan_peer_downloads.py` covers only
their peer-delivery/revocation wiring; further peer or Obsidian behavior should
be split into the existing state/download/config modules instead of raising the
monolith limits again without a new measured review.

The pending-governance trust envelope and CLI are separate modules rather than
new growth in the governance state machine: `shiguan_pending_governance.py`
remains below 650 lines, `shiguan_pending_governance_cli.py` below 220, and
`shiguan_pending_trust.py` below 460. The latter owns strict-file reads, runtime
identity derivation, HMAC/event-chain verification, and the external append-only
head; future trust changes belong there instead of returning those concerns to
the governance core or Web server.

## 2026-07-16 Measured Revision

This measured revision supersedes both the 2026-07-11 documented ceiling of
190 files / 2.95 MB and the later manifest ceiling of 220 files / 3,300,000
bytes. After classifying `.github/` and `docs/` as repository-only surfaces,
the measured portable source is 258 files / 5,409,889 bytes; the new hard
ceiling is 265 files / 5,600,000 bytes. These limits are a measured baseline,
not a growth entitlement. If either repository-only directory later becomes
part of the portable payload, its exclusion must be removed and the package
contract remeasured.

The admission split keeps `court_multi_agent_protocol.py` at 488 lines under
its unchanged 600-line limit and moves the independently testable admission
surface into `court_agent_admission.py`, measured at 611 lines with a 650-line
limit. `agent_runtime_probe.py` is measured at 1,106 lines; its narrow ceiling
is 1,120. Future admission or probe growth must be split or justified by a new
measured revision rather than silently raising these limits.
