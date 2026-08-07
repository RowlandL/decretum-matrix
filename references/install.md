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
Shiguan/GBrain and superCC runtime helpers, and `sync_active_copies.py`.

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
projection to the five governed roots and prunes obsolete script files. The
final command checks the installed skill frontmatter and lightweight
court-format contracts. The optional Qoder commands extend that same operation
only after explicit authorization.

If a target root is missing, the sync command creates it when `--write` is used.

If a physical `court-capability-router` locator conflicts with the canonical
directory, do not delete it or overwrite it manually. With explicit written
authorization, plan then apply the transactional migration:

```powershell
python -B scripts/sync_active_copies.py --migrate-legacy-locators --prune-obsolete --json
python -B scripts/sync_active_copies.py --write --migrate-legacy-locators --prune-obsolete --json
```

The migration moves each full legacy directory to a distinct backup under the
user's local Decretum Matrix install-backup root, then creates a compatibility
alias to the updated canonical directory. If migration or synchronization
fails, it restores the moved legacy directories; a `FAIL_PARTIAL_APPLIED`
receipt still requires the source-only hash check before any further install
action.

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
