# Edict Registry Import

Use this reference when importing or designing Edict-like standing-agent registries from external config/SOUL files.

## Import rule

If no authoritative Hermes standing-agent import command is discoverable, do not mutate Hermes internals speculatively. Generate a neutral bundle first:

```text
references/hermes-standing-agents/registry.json
references/hermes-standing-agents/role-prompts.md
```

Preserve machine-actionable contracts: identity, source prompt/SOUL, tool/runtime access, delegation ACLs, workflow ownership and transitions, escalation paths, approval gates, dashboard metadata, and observability/audit events. Validate ACL targets and state references before using the bundle for dispatch.
