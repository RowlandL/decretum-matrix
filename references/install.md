# Install And Local Synchronization

This reference governs local installation of `decretum-matrix` into the active
agent skill roots. It is runtime-focused; release packaging and publication
checks stay in the source tree and are not startup prerequisites.

The current beta1.1.2 source is an unreleased local development version.
The commands and target details below do not authorize installing beta1.1.2;
its installation requires a later explicit external installation transaction
and a matching receipt.

## Targets

The five governed synchronization targets are fixed:

- `<home>/.agents/skills/decretum-matrix`
- `<home>/.codex/skills/decretum-matrix`
- `<home>/.claude/skills/decretum-matrix`
- `<home>/.hermes/skills/decretum-matrix`
- the Hermes platform user-data skill root when present

An additional `<home>/.qoder/skills/decretum-matrix` target is permitted only
through explicit `--include-qoder` authorization; it does not change the
default five-root contract.

`<home>` is `%USERPROFILE%` on Windows and `$HOME` on macOS/Linux. The Hermes
platform user-data root is `%LOCALAPPDATA%/hermes` on Windows and `~/.hermes` on
macOS/Linux.

The canonical installed name is `decretum-matrix`. The old
`court-capability-router` locator may exist only when it resolves to the same
physical authority; otherwise report the conflict and stop before writing.

## Runtime Surface

For the unreleased beta1.1.2 development version, no installed runtime surface
is being claimed. A later explicitly authorized installation transaction may
project the bounded skill, governing references, office materials, and runtime
helpers described by the manifest; projection, synchronization, release, and
package tools remain outside that runtime. Startup, preload, and ordinary
runtime are metadata-only and must not import or invoke those external tools.

## Diagnostics And Fixes

The unified CLI exposes three maintenance surfaces:

```text
decretum-matrix doctor [--source-root <root>] [--mapped-root <root>]
decretum-matrix debug [--source-root <root>] [--mapped-root <root>]
decretum-matrix fix update|migrate|rollback [options]
```

`doctor` compares the selected source contract, Git identity, complete managed
projection, Codex MCP configuration/runtime probe, and production hard-coded
path policy. `debug` adds Python/platform/Git/source-resolution evidence while
remaining read-only. Both commands redact secrets and never read private or
pending bodies. `fix` reuses the existing atomic installer and migration
receipts: it is a read-only plan by default and requires `--apply` for any
write. Every invocation emits a `workspace.operation_event.v1` intent/result
pair under the git-mirror `.repo-control/events/decretum-matrix/` path.

During beta development the default source authority is the local checkout.
The intended post-publication default is a pinned GitHub release of
`RowlandL/decretum-matrix`; network fetching is deliberately disabled in the
beta implementation until a release tag, commit, and artifact SHA are bound.
If a UNC checkout is not usable by a host subprocess, pass both roots. The
mapped root is accepted only when `VERSION`, the declared source/install
revision, and (when available) Git `HEAD` match:

```powershell
python -B scripts/court_cli.py doctor `
  --source-root "<git-mirror>\decretum-matrix" `
  --mapped-root "<mapped-git-mirror>\decretum-matrix"
```

The selected root and equivalence decision are recorded in the diagnostic
receipt; no legacy mirror root or UNC path is embedded in product configuration.

## MCP Protocol Contract

The current MCP wire target is the official `2026-07-28` revision. The stdio
facade is modern and stateless: every request carries
`_meta.io.modelcontextprotocol/protocolVersion`,
`_meta.io.modelcontextprotocol/clientCapabilities`; clientInfo may be omitted,
but when present it must be an Implementation object with non-empty `name` and
`version` strings. `server/discover` is implemented and reports the supported versions,
tools capability, server identity, and public cache hints. `tools/list` and
`tools/call` return `resultType=complete` plus self-describing server metadata.
This implementation does not paginate `tools/list`: omit `cursor` or send an
empty string; non-empty cursors are rejected with `-32602`. Malformed JSON is
`-32700`, while invalid JSON-RPC requests (including missing or null ids) are
`-32600`.

`2025-11-25` remains a compatibility path only. A client that sends
`initialize` selects legacy per-process semantics; it must then send
`notifications/initialized` and may use `tools/list`/`tools/call` without
modern `_meta`. Modern and legacy receipts are recorded separately. A source
wire probe is available at
`scripts/probe_court_mcp_modern_wire.py`; it never proves Codex/CC Switch
loading or tool visibility.

Use the same probe shape for source and installed-copy receipts, while keeping
host visibility separate:

```powershell
python -B scripts/probe_court_mcp_modern_wire.py --host-state source_checkout
python -B scripts/probe_court_mcp_modern_wire.py --server "%USERPROFILE%\.agents\skills\decretum-matrix\scripts\court_mcp_server.py" --root "%USERPROFILE%\.agents\skills\decretum-matrix" --expected-root <validated-source-root> --host-state host_degraded
```

Do not load release gates, fixtures-only helpers, package builders, GitHub
publication helpers, or broad compatibility checkers as startup tools. A
handler may be installed for the seven-group CLI without becoming a startup
dependency. Commands that require Git/tag authority return a typed
`SOURCE_CHECKOUT_REQUIRED` or other blocked receipt outside a source checkout.

The unreleased beta1.1.2 development version does not promise automatic
installation or reuse of `zellij`, `squad`, or any other extra dependency.
Any such dependency must be handled by a later explicitly authorized external
installation transaction with its own receipt; the exact command is not
defined in this development reference.

## External Installation Transaction

Beta1.1.2 is not released, so this reference does not prescribe an installed-root
command. When T09 supplies a later explicitly authorized external installation
transaction, that transaction must bind the source, artifact, installation
revision, selected roots, and rollback information; project each approved target;
run one existing verifier outside the active runtime after all projections finish;
and persist the resulting receipt. A missing, interrupted, or failed transaction
remains `NOT_RUN` or `FAILED` and cannot be inferred from metadata.

Normal startup, preload, and runtime read only bounded version, revision,
transaction, and receipt metadata. They do not scan or summarize installed
files, invoke external projection tools, or perform content-hash checks. Optional
roots and extra dependencies require the same explicit transaction and receipt;
the exact command is intentionally left to T09.

## Blank Host And Restart Receipt Fields

Blank-host/current-tool configuration uses the following machine-readable
receipt vocabulary. These fields describe the installer decision; they do not
authorize writes to other tools or an automatic restart:

```text
shared_root=%USERPROFILE%\.agents\court-shiguan\decretum-matrix\references
probe_before_write=true
install_current_tool_only=true
unapproved_other_tools=REMINDER_ONLY
auto_start_obsidian=false
auto_start_daemon=false
auto_install_dependencies=false
restart_required=true
restart_deferred=true
tasks_continued=true
restart_requires_latest_explicit_authority=true
input_token_semantics=version_specific
```

Schema alone is not application-version evidence. Reread the current CC Switch
and Codex versions, effective configuration, and runtime receipts before
acceptance.

If a physical `court-capability-router` locator conflicts with the canonical
directory, do not delete it or overwrite it manually. First use the dedicated
legacy-locator entrypoint for a read-only plan:

```powershell
python -B scripts/migrate_legacy_skill_locator.py plan --json
```

With explicit written authorization, apply it and keep the returned
`receipt_path`:

```powershell
python -B scripts/migrate_legacy_skill_locator.py apply --write --json
```

Rollback is also receipt-bound:

```powershell
python -B scripts/migrate_legacy_skill_locator.py rollback --receipt <receipt_path> --write --json
```

The migration either renames a legacy-only physical root to the canonical name,
or backs up a duplicate legacy physical root before replacing it with a
compatibility alias to the canonical directory. It never treats the old locator
as a second current skill authority. After a successful migration, wait for the
next explicitly authorized external installation transaction to refresh managed
files.

If the receipt-bound installer rejects a current-tool root with
`protected_anchor_wrong_target`, that root is an old full replica carrying
shared-only Shiguan anchors. Do not prune or overwrite it manually. From the
source checkout, first plan the directory-level rollbackable migration against
the exact release ZIP:

```powershell
python -B scripts/migrate_current_tool_replica.py plan --package <release_zip> --json
python -B scripts/migrate_current_tool_replica.py apply --package <release_zip> --write --json
```

The tool atomically archives the complete old current-tool root under
`~/.agents/install-backups/decretum-matrix/`, archives the installer with its
SHA-256, then applies the package projection transactionally. Its receipt
records both the managed-file backup and the full-directory preimage. Roll back
with the same ZIP and receipt:

```powershell
python -B scripts/migrate_current_tool_replica.py rollback --receipt <receipt_path> --package <release_zip> --write --json
```

## Boundaries

Local synchronization is not publication. It must not push Git branches, create
tags, upload assets, open pull requests, start public services, read private
pending bodies, or mutate unrelated projects.

File differences are normal work to copy, not a task blocker. Report copied,
unchanged, and removed counts; continue unless the source projection is missing
or a target path is unsafe.

The single post-projection verifier, when authorized, runs outside the active
runtime after an installation transaction has completed. The installed skill
roots must not retain that verifier or make file summaries part of loading,
startup, preload, or ordinary runtime.
