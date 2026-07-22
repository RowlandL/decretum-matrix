# Install And Local Synchronization

This reference governs local installation of `decretum-matrix` into the active
agent skill roots. It is runtime-focused; release packaging and publication
checks stay in the source tree and are not startup prerequisites.

## Targets

The local synchronization target set is fixed:

- `<home>/.agents/skills/decretum-matrix`
- `<home>/.codex/skills/decretum-matrix`
- `<home>/.claude/skills/decretum-matrix`
- `<home>/.hermes/skills/decretum-matrix`
- the Hermes platform user-data skill root when present

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

The first command shows what would change. The second command copies the
projection to the five roots and prunes obsolete script files. The final command
checks the installed skill frontmatter and lightweight court-format contracts.

If a target root is missing, the sync command creates it when `--write` is used.
If a legacy locator conflicts with the canonical directory, fix that locator
manually before syncing.

## Boundaries

Local synchronization is not publication. It must not push Git branches, create
tags, upload assets, open pull requests, start public services, read private
pending bodies, or mutate unrelated projects.

File differences are normal work to copy, not a task blocker. Report copied,
unchanged, and removed counts; continue unless the source projection is missing
or a target path is unsafe.

Install-time archive or dependency digest checks are allowed only before a file
is activated. The installed skill root must not retain file-summary validators
or make file summaries part of ordinary startup.
