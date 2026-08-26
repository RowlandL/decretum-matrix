# Install And Local Synchronization

This reference governs local installation of `decretum-matrix` into the active
agent skill roots. It is runtime-focused; release packaging and publication
checks stay in the source tree and are not startup prerequisites.

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

The installed surface is defined by
`references/manifests/install-projection.v1.json`. It includes the entry
`SKILL.md`, the current governing references, office dossiers/profiles,
Shiguan/GBrain and superCC runtime helpers, `sync_active_copies.py`, and the
dedicated legacy locator migration entrypoint
`migrate_legacy_skill_locator.py`.

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

Do not install release gates, fixtures-only checkers, package builders, GitHub
publication helpers, or broad compatibility checkers as startup tools.

First install may install or reuse the superCC runtime dependencies `zellij` and
`squad`. This is a dependency bootstrap, not a startup checker. The receipt must
thank and link the upstream open source projects:

- Zellij: https://github.com/zellij-org/zellij
- squad: https://github.com/mco-org/squad

Default dependency tool roots are `C:/Tools/bin` on Windows and `~/.local/bin`
on macOS/Linux; `COURT_TOOL_INSTALL_DIR` may override them.

## Procedure

From the source skill root:

```sh
python -B scripts/sync_active_copies.py --json
python -B scripts/sync_active_copies.py --write --prune-obsolete --json
python -B scripts/quick_validate.py .
```

After synchronization, run the source-only hash checker from the release or
repository checkout:

```powershell
python -B scripts/check_active_copy_hashes.py --json
```

Qoder is outside the default five-root contract. Only when the latest written
authorization explicitly names Qoder, repeat synchronization and verification
with `--include-qoder`:

```powershell
python -B scripts/sync_active_copies.py --write --prune-obsolete --include-qoder --json
python -B scripts/check_active_copy_hashes.py --include-qoder --json
```

`check_active_copy_hashes.py` is a standalone post-install/release gate. It is
declared `repository_only`, must not appear in any installed projection, and
must never be imported or invoked by skill loading, startup, preload, runtime,
or `sync_active_copies.py`. Runtime identity SHA-256 use remains valid and is
independent of this installation checker.

The first command shows what would change. The second command copies the
projection to the governed roots, prunes obsolete files, and renders the
Codex native role files from the newly installed standing profiles. Its JSON
must report `codex_agent_roles.status` as `CURRENT` or `APPLIED`. The final
hash command also validates those role files whenever the selected roots include
the Codex skill root, so a current skill paired with stale preload hashes fails
the post-install gate. The optional Qoder commands extend that same operation
only after explicit authorization.

If a target root is missing, the sync command creates it when `--write` is used.

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
as a second current skill authority. After a successful migration, run the
normal `sync_active_copies.py --write --prune-obsolete --json` flow from the
current release source to refresh managed files.

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

Archive or dependency digest gates run before activation. The standalone
post-install checker may inspect activated roots from the source checkout, but
the installed skill roots must not retain that checker or make file summaries
part of loading, startup, preload, or ordinary runtime.
