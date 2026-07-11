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
