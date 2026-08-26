# Decretum Matrix AI Installation README

This file is the machine-facing installation contract for AI agents. It is
separate from `INSTALL-PROMPT.md`, which is the human-oriented offline prompt.

## Authority And Scope

- The local git mirror is the **local validation authority** for this build.
- GitHub is only a future publication target after complete verification and
  explicit push authorization.
- Never fetch a replacement package from the network during installation.
- Canonical product, skill, and locator name: `decretum-matrix`.
- `court-capability-router` is deprecated and may only resolve to the same
  physical authority after a receipt-bound migration probe.

## Installation Targets

Default Windows targets are:

1. `%USERPROFILE%\.agents\skills\decretum-matrix`
2. `%USERPROFILE%\.codex\skills\decretum-matrix` when the current tool is Codex

Do not fan out to Claude, Hermes, or other tools unless the latest user request
names them. Preserve private data, Shiguan contents, user configuration, and
unmanaged files. Before replacing a target, create a complete rollback preimage
and a typed install receipt.

## CC Switch Detection And MCP Import

If `%USERPROFILE%\.cc-switch\cc-switch.db` exists, or CC Switch is running,
assume CC Switch owns the Codex configuration path.

1. Prefer CC Switch's **Import MCP** flow. Import one stdio server named
   `decretum_matrix` with:

   - `command`: the host Python executable used for installation
   - `args`: `-B`, then the absolute installed path to
     `scripts/court_mcp_server.py`
   - `startup_timeout_sec`: `30`
   - enable the server for Codex only

2. After import, ask CC Switch to apply/sync its active Codex configuration.
3. Resolve and record the CC Switch upstream source used for the import: the
   supported CLI/config-management entrypoint, its common-config path and
   section, or the manager registry source explicitly documented for the
   installed CC Switch version. The generated `%USERPROFILE%\.codex\config.toml`
   is an effective projection, not the upstream authority.
4. If the importer is unavailable, do not edit the generated Codex TOML or
   CC Switch SQLite by assumption. First resolve the version-specific
   common-config source/section and add `[mcp_servers.decretum_matrix]` there
   through the supported configuration mechanism. Manual SQLite edits are
   allowed only when the current CC Switch documentation explicitly identifies
   that database as its API-owned source. Otherwise report
   `CONFIGURATION_INCOMPLETE` and stop.
5. For any supported fallback write, save the source preimage, SHA-256, and a
   typed receipt; trigger CC Switch sync/reload; then verify the effective
   `%USERPROFILE%\.codex\config.toml`, installed server target hash, modern
   `2026-07-28` runtime probe, and new-session tool visibility.
6. Restart CC Switch/Codex after configuration sync. A stale running process is
   not configuration evidence.

The installed MCP facade must expose these read-only tools only:

`court.status`, `court.command_help`, `shiguan.query`,
`shiguan.archive_dry_run`, `memory.scan`.

MCP and the unified CLI are peer transports. Both use the source
`scripts/court_public_api.py`; MCP must not spawn `court_cli.py`, parse CLI
stdout, or create a second ledger/receipt path. A successful MCP probe and a
successful CLI probe therefore validate the same runtime projection, while
their transport receipts remain separate.

## MCP Protocol Requirement

The current protocol target is `2026-07-28`.

- Modern clients use `server/discover` and include
  `io.modelcontextprotocol/protocolVersion`,
  and `io.modelcontextprotocol/clientCapabilities` in request `_meta`.
- `io.modelcontextprotocol/clientInfo` may be omitted; when present it must be
  an Implementation object with non-empty `name` and `version` strings.
- Modern results include `resultType = "complete"` and server metadata.
- This server does not paginate `tools/list`: omit `cursor` or send an empty
  string; a non-empty cursor is rejected with JSON-RPC `-32602`.
- Malformed JSON is `-32700`; non-object, wrong-version, missing-id, and
  null-id requests are `-32600`.
- Unsupported versions fail closed with `UnsupportedProtocolVersionError`
  semantics and the supported-version list.
- `initialize` remains only as a compatibility path for older Codex clients.

Run the source checker and a runtime probe before claiming MCP readiness:

```powershell
python -B scripts/check_court_mcp_server.py
python -B scripts/probe_court_mcp_modern_wire.py --host-state source_checkout
```

After installation, replay the same modern wire probe against the installed
server path and record the host layer separately:

```powershell
python -B scripts/probe_court_mcp_modern_wire.py --server "%USERPROFILE%\.agents\skills\decretum-matrix\scripts\court_mcp_server.py" --root "%USERPROFILE%\.agents\skills\decretum-matrix" --expected-root <validated-source-root> --host-state host_degraded
python -B scripts/check_active_copy_hashes.py --json
python -B scripts/check_codex_agent_roles.py --format json
```

The active-copy write must render `%USERPROFILE%\.codex\agents\*.toml` from
the just-installed profiles before either command may pass. Recomputing an
in-memory preload manifest is not host evidence; the installed native role
files must bind the same skill, profile, and dossier hashes.

## Codex Hooks

The Codex plugin projection is the lifecycle integration path. It is enabled
by the plugin manifest at `.codex-plugin/plugin.json`, which points to
`hooks/claude-codex-hooks.json`. The hooks only inject bounded context telling
the agent that the Decretum Matrix MCP is available; they do not grant
authority and they do not replace the CLI or MCP probe.

- `scripts/court_codex_hook.py` is the Codex lifecycle hook entrypoint.
- `scripts/court_hooks_advisory.py` remains the Git-hook compatibility report;
  it must not install `.git/hooks` or set `core.hooksPath`.
- Neither hook may write memory, archive checkpoints, close out tasks, publish
  releases, dispatch agents, or change MCP configuration.
- The decree number still comes only from the `archive-checkpoint` receipt;
  hooks and MCP never allocate it.

Verify the boundary with:

```powershell
python -B scripts/check_court_hooks_advisory.py
```

Install the reversible Codex plugin projection from the validated mirror with:

```powershell
python -B scripts/install_codex_plugin_projection.py install
```

The installer copies only the plugin manifest, hook manifest, and lifecycle
entrypoint, backs up the prior plugin/config preimage under
`%USERPROFILE%\.agents\install-backups\decretum-matrix`, and leaves the direct
CC Switch MCP registration untouched. Use the `rollback_command` in the
receipt to restore the preimage, then restart Codex before judging hook
activation.

## MCP Replacement Boundary

MCP is not a wholesale replacement for the CLI. The current read-only MCP
surface can replace CLI calls for status, command help, Shiguan queries,
archive dry-runs, and memory scans. Mutating court/office lifecycle actions,
archive checkpoints, installs/migrations, release operations, and superCC
actions remain CLI/script workflows because they require authority-bound
receipts, host-native probes, rollback, or controlled writes. Treat MCP and CLI
as equal transport choices for the read-only subset; do not make MCP call the
CLI or infer write capability from a successful read-only probe.

## Verification And Rollback

The final report must include the package SHA-256, target roots, backup root,
install receipt, CC Switch import/sync evidence, current config TOML hash,
source MCP probe, installed MCP probe, active-copy hash receipt, hook advisory
probe, and explicit rollback command.

Do not claim "configured" from file presence alone. Configuration is complete
only when the host registry/import path, live Codex TOML, restart, and runtime
MCP probe all agree. If any one is missing, report `CONFIGURATION_INCOMPLETE`
and stop before publication.

For Codex host status, report the four layers independently:

- `manager_registered`: CC Switch or another manager has a registry row.
- `effective_config`: the active Codex configuration contains the server.
- `process_probe`: a direct stdio server probe passes for the installed copy.
- `tool_visible`: a new Codex session can see and call the MCP tool.

If only the manager row or plugin source is present, use
`host_degraded / effective_runtime_unverified` instead of "active" or
"configured".
