# Complexity Budget

Keep review fast and local. Reuse owners and small recurrence guards; exclude
unrelated Web/API/security work and generated, private, or pending state.

Fast path: `quick_validate.py`, `check_catalog.py --strict`,
`check_portability.py`, `check_supercc_profiles.py`,
`check_codex_agent_roles.py`, `sync_active_copies.py --json`, and
`check_supercc_functional.py --workspace . --json --diagnose`.

## Measured History

| Date | Portable source | Ceiling |
| --- | ---: | ---: |
| 2026-07-11 | 185 files / 2.65 MB | 190 files / 2.95 MB |
| 2026-07-16 | 258 files / 5,409,889 bytes | 265 files / 5,600,000 bytes |
| 2026-07-17 | 273 files / 6,138,661 bytes | 275 files / 6,200,000 bytes |
| 2026-07-18 | 273 files / 6,205,322 bytes | 275 files / 6,225,000 bytes |

`references/manifests/source-state-budget.v1.json` owns classification and
ceilings. Focused checkers own behavior; history does not permit growth.
