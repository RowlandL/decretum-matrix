# Install And Local Synchronization

This reference governs local installation of `decretum-matrix` into the active
agent skill roots. It is runtime-focused; release packaging and publication
checks stay in the source tree and are not startup prerequisites.

## Targets

The local synchronization target set is fixed:

- `%USERPROFILE%\.agents\skills\decretum-matrix`
- `%USERPROFILE%\.codex\skills\decretum-matrix`
- `%USERPROFILE%\.claude\skills\decretum-matrix`
- `%USERPROFILE%\.hermes\skills\decretum-matrix`
- the Hermes platform user-data skill root when present

The canonical installed name is `decretum-matrix`. The old
`court-capability-router` locator may exist only when it resolves to the same
physical authority; otherwise report the conflict and stop before writing.

## Runtime Surface

The installed surface is defined by
`references/manifests/install-projection.v1.json`. It includes the entry
`SKILL.md`, the current governing references, office dossiers/profiles,
Shiguan/GBrain and superCC runtime helpers, and `sync_active_copies.py`.

Do not install release gates, fixtures, benchmarks, package builders, GitHub
publication helpers, or broad compatibility checkers as startup tools.

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
