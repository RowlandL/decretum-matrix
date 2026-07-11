---
type: shiguan_capability_index_seed
portable_seed: true
capability_index_skill_gate: "seed"
---

# 能力官籍索引 / Capability Routing Index

Portable seed. Run `python -B scripts/refresh_capability_registry.py` after install to generate the host-local skill/agent/MCP/CLI/script routing table.

Invocation rule: index first, select the smallest suitable bounded capability set, then call under the active authority. Do not wait for the user to name the capability and do not invoke every matching candidate.
