# Standard Skill Installation

This package is a standard Codex skill directory:

```text
court-capability-router/
  SKILL.md
  agents/openai.yaml
  agents/standing-officials/*.toml
  references/court-*.md
  references/department-map.md
  references/install.md
  references/shiguan-tree/
  references/shiguan-index.jsonl
  references/shiguan-knowledge-graph.json
  references/startup-tasks/README.md
  web/shiguan-tree/index.html
  web/shiguan-tree/styles.css
  web/shiguan-tree/app.js
  scripts/check_catalog.py
  scripts/archive_checkpoint.py
  scripts/query_shiguan_index.py
  scripts/grow_shiguan_tree.py
  scripts/build_shiguan_knowledge_graph.py
  scripts/export_shiguan_obsidian.py
  scripts/rebuild_shiguan_index.py
  scripts/ensure_codex_yolo_startup_task.py
  scripts/ensure_court_agent_config.py
  scripts/ensure_portable_court_bootstrap.py
  scripts/ensure_supercc_court.py
  scripts/supercc_office_state.py
  scripts/ensure_shiguan_service_daemon.py
  scripts/ensure_shiguan_web.py
  scripts/shiguan_service_daemon.py
  scripts/serve_shiguan_tree.py
  scripts/shiguan_peer_downloads.py
  scripts/refresh_capability_registry.py
  scripts/package_skill.py
  scripts/shiguan_paths.py
  scripts/migrate_shared_shiguan.py
  scripts/sync_shiguan_obsidian_vault.py
  scripts/register_agent_presence.py
  scripts/sync_codex_agents_from_profiles.py
  scripts/check_codex_agent_roles.py
  scripts/repair_archive_placeholders.py
  scripts/memory_decision.py
```

Public packages contain neither host-local Shiguan bodies nor
`references/plan-archives/` or `references/memory-decisions/`, including their
README placeholders. They also exclude generated
`references/startup-tasks/*` review artifacts, generated
`references/shiguan-tree/leaves/*.md`, generated local capability catalogs, or
local Shiguan graph/index data. They also exclude `references/obsidian-sync/`
because it can contain host-local REST API keys. Portable seed files are limited
to the explicitly listed seed surfaces such as the empty index, seed graph,
seed tree, and `references/startup-tasks/README.md`. Private `plan-archives` and
`memory-decisions` directories are initialized only in the target host's shared
Shiguan root after installation.

## Shared Shiguan Data Root

Writable Shiguan data is not stored under a single skill installation. All
Codex, Agent Skills, and Hermes installs resolve the shared root through
`scripts/shiguan_paths.py`:

```text
default data root: %LOCALAPPDATA%\court-shiguan\court-capability-router
default references: %LOCALAPPDATA%\court-shiguan\court-capability-router\references
override env: COURT_SHARED_SHIGUAN_ROOT or SHIGUAN_SHARED_ROOT
```

On a blank install, the first Shiguan script, service daemon, or WebUI startup calls
`ensure_shared_seed()` and creates `plan-archives`, `memory-decisions`,
`court-runtime`, `agente-logs`, `shiguan-imports`, `shiguan-peers`,
`obsidian-sync`, `shiguan-tree`, `shiguan-tree\sources`, an empty
`shiguan-index.jsonl`, and a portable seed knowledge graph. This is seed creation
only; legacy `.codex`, `.agents`,
or Hermes archives are not silently merged on a new host.

To explicitly merge local legacy archives after installation:

```powershell
python -B scripts/migrate_shared_shiguan.py --dry-run
python -B scripts/migrate_shared_shiguan.py
```

## One-command Portable Bootstrap

After copying the skill into a new Codex install and restarting Codex, run the
portable bootstrap from the installed skill directory:

```powershell
python -B scripts/ensure_portable_court_bootstrap.py --check-only --format text
python -B scripts/ensure_portable_court_bootstrap.py --apply --format text
```

This creates the shared Shiguan seed, registers the shared Shiguan tree with
Obsidian, ensures the `CourtShiguanDaemon` service, enables Codex/Hermes native
memory flags when disabled, records the metadata-only memory bridge, installs
or checks first-run `superCC` dependencies (`zellij.exe` and `squad.exe`), and
runs `squad init` when the workspace lacks `.squad`.

The bootstrap installs zellij/squad only from configured GitHub release assets
and requires a GitHub asset digest or sha256 sidecar unless the active decree
explicitly passes `--allow-unverified-release-asset`. It does not copy private
memory bodies, does not hand-edit Codex SQLite, does not include Obsidian API
keys in packages, and does not process `shiguan-imports\pending` into official
records.

For only the `superCC` substrate, use:

```powershell
python -B scripts/ensure_portable_court_bootstrap.py --apply --supercc-deps-only --format text
python -B scripts/ensure_supercc_court.py --check-only --format text
python -B scripts/ensure_supercc_court.py --turn-start --reclaim-existing --format text
python -B scripts/ensure_supercc_court.py --closeout-silence --format text
```

The per-turn command reuses current visible offices, runs the simple squad
responsiveness check, releases noncurrent inactive canonical ids, reopens missing
visible-core offices, and writes shared Shiguan runtime state. 六部 are
non-visible and `silent` by default. They activate only after 尚书省 dispatches an
approved bounded step through the ministry task channel or `--wake-offices` from
a Shangshu-bound context; visible ministry panes require explicit bounded
authorization in the newest decree. After 结诏, use
`--closeout-silence --unfinished-offices <roles>` only when a named office still
has unresolved work. Hermes CLI reproduction uses the same launcher with
`--office-client hermescli --hermescli-command <path>`.

## Prerequisites

The package does not vendor every possible worker. A portable court install
expects the host Codex environment to provide at least:

```text
%CODEX_HOME%\skills\find-skills\SKILL.md
%CODEX_HOME%\skills\.system\skill-creator\SKILL.md
%CODEX_HOME%\skills\.system\skill-creator\scripts\quick_validate.py
```

If `CODEX_HOME` is unset, use `%USERPROFILE%\.codex`. If either prerequisite is
missing, install or repair it with the host's standard Codex skill bootstrap or
skill installer before relying on full court routing. Inside the court model,
吏部 treats missing prerequisites as a recruitment/remediation task.

For `find-skills`, use the public skill page and Skills CLI command:

```powershell
# Browse:
# https://www.skills.sh/vercel-labs/skills/find-skills

npx skills add https://github.com/vercel-labs/skills --skill find-skills
```

If the Skills CLI itself is missing, install Node.js/npm first, then run the
same command through `npx`. After installing `find-skills`, restart Codex so the
skill registry refreshes.

## Install From A Local Folder

1. Copy `court-capability-router` into the Codex skills directory:

```python
from pathlib import Path
import os
import shutil

src = Path("court-capability-router")
skills_root = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "skills"
dst = skills_root / "court-capability-router-beta0.5.9"
if dst.exists():
    raise SystemExit(f"refusing to overwrite existing install: {dst}")
shutil.copytree(src, dst)
```

2. Restart the Codex session so the skill list refreshes.
3. Apply the approved bounded recursive-agent defaults:

```sh
python -B scripts/ensure_court_agent_config.py --managed-overlay --write --protocol v2
```

This writes `[agents] max_depth = 4`, enables Multi-Agent V2, writes
`features.multi_agent_v2.max_concurrent_threads_per_session = 16`, sets
`hide_spawn_agent_metadata = true`, and removes the incompatible legacy
`[agents].max_threads` key from `CODEX_HOME/config.toml` (or
`~/.codex/config.toml` when `CODEX_HOME` is unset). It creates a backup before
changing an existing file. Restart Codex after this step; a running session may
not hot-reload recursion settings or the reserved collaboration tool schema.

The V2 ceiling covers the whole tree: the root consumes one of 16 slots, leaving
at most 15 children. Do not restore legacy `[agents].max_threads`; admission
clamps to proven capacity, reclamation, depth, and request budgets.

The former bidirectional V1/V2 startup switch is deprecated. Keep V1 source,
fixtures, prior configuration, and immutable backups for recovery/audit, but do
not select V1 during routine installation or advertise it as a live switch.
Production installation remains V2 unless a newer explicit user decree reopens
the capability.

4. Invoke with `$court-capability-router`; the skill defaults to the court
   workflow and asks only for the three execution authorities when needed.
   The startup menu also names the Shiguan local manager:
   `web/shiguan-tree/index.html`. Editing requires the local server command
   shown below.

If the host lacks standing court officials, do not copy the structured
`agents/standing-officials/*.toml` templates directly into
`%CODEX_HOME%\agents\`. Codex custom agent role files must be string-only TOML,
so render the installed role files from the templates:

```powershell
python -B scripts/sync_codex_agents_from_profiles.py --write
python -B scripts/check_codex_agent_roles.py
```

The templates keep the structured `[profile]`官署档案 used by superCC runtime,
profile hashes, and patrol checks. The installed `%CODEX_HOME%\agents\*.toml`
files contain `name`, `description`, and `developer_instructions` strings only,
with the profile/soul summary embedded in `developer_instructions`.

## Validate

Read-only validation from the installed skill directory:

```sh
python -B scripts/quick_validate.py
python -B scripts/check_catalog.py --strict
python -B scripts/ensure_portable_court_bootstrap.py --check-only --format text
python -B scripts/ensure_court_agent_config.py --check
python -B scripts/check_codex_agent_roles.py
python -B scripts/sync_shiguan_obsidian_vault.py --dry-run
python -B scripts/quick_validate.py .
```

`check_catalog.py --strict` verifies the portable court assets, required host
prerequisites, loading indexes, response few-shot gate, package-required
references, standing profiles, and Codex agent role shape without initializing
shared Shiguan state. If `find-skills` is missing it prints the `skills.sh` page
and install command. If the Codex agent config is below `max_depth = 4` or V2
`max_concurrent_threads_per_session = 16`, still contains legacy
`agents.max_threads`, or exposes reserved spawn metadata, it prints the
`ensure_court_agent_config.py --write` remediation command. The Obsidian dry-run verifies `preserve_only=true` and
`removed=0` before any real vault refresh. On this host, `quick_validate.py` has
a minimal frontmatter parser fallback, so it can run even when PyYAML is not
installed. If another host still has an older `skill-creator`, repair that
system skill or use `check_catalog.py` plus package structure checks until
`skill-creator` is fixed.

Writeback/local index validation requires explicit authority:

```powershell
python -B scripts/sync_codex_agents_from_profiles.py --write
python -B scripts/refresh_capability_registry.py
python -B scripts/rebuild_shiguan_index.py
```

`sync_codex_agents_from_profiles.py --write` renders installed Codex agent TOML
from standing-office templates. `refresh_capability_registry.py` scans the
target host's skills, standing agents, and selected CLIs, then writes that
host's local 官籍 catalogs. `rebuild_shiguan_index.py` initializes or rebuilds
the host's own Shiguan recall index, growth tree, and knowledge graph in the
shared Shiguan root.

Do not copy `agents/standing-officials/*.toml` directly into
`%CODEX_HOME%\agents`. Standing profiles contain structured `[profile]` source
data; installed Codex agent files must be string-only TOML rendered by
`sync_codex_agents_from_profiles.py`. If a direct-copy template reaches
`.codex/agents`, `check_codex_agent_roles.py` reports
`TEMPLATE_COPIED_DIRECTLY`.

The archive command writes a real self-test checkpoint into the shared Shiguan
database. Run it only when a write test is desired; otherwise use the read-only
checks above.

```powershell
python -B scripts/archive_checkpoint.py --topic "install-self-test" --phase "复核" --status "DONE" --summary "archive script works" --evidence "manual self-test" --next "none" --keywords "install,self-test" --key-actions "archive,index"
python -B scripts/rebuild_shiguan_index.py
python -B scripts/query_shiguan_index.py "install-self-test"
python -B scripts/grow_shiguan_tree.py
python -B scripts/memory_decision.py --topic "install-self-test" --decision "SKIP" --content "no durable memory" --reason "self-test only"
```

The rebuild command scans every existing file under `references/plan-archives/`
and `references/memory-decisions/` in the shared root, rewrites
`references/shiguan-index.jsonl`,
adds bilingual recall fields (`keyword_summary_zh`, `keyword_summary_en`,
`keywords_zh`, `keywords_en`), and refreshes the Markdown growth tree. Run it
after upgrading older installs.

## Verify the beta0.5.9 Release

Release assets:

```text
court-capability-router-beta0.5.9.zip
court-capability-router-beta0.5.9.zip.sha256
```

The ZIP has one top-level root: `court-capability-router/`.

```powershell
$zip = 'court-capability-router-beta0.5.9.zip'
$expected = ((Get-Content "$zip.sha256" -Raw).Trim() -split '\s+')[0]
$actual = (Get-FileHash $zip -Algorithm SHA256).Hash
if ($actual -ine $expected) { throw 'SHA256 mismatch' }
```

After extraction, inspect `VERSION` and `release-manifest.json`, then run the portable install checks from the skill root:

```powershell
python -B scripts/quick_validate.py .
python -B scripts/check_catalog.py --strict
python -B scripts/check_release_manifest.py --json
```

The root `release-manifest.json` describes this artifact. `references/manifests/release-gates.v1.json` describes the source release-gate policy; neither replaces SHA256 verification. Maintainers run the full package gate from a clean canonical source tree with `scripts/check_release_gate.py --package <path-to-zip> --require-package --skip-runtime --json`, because the extracted release intentionally contains generated portable seed files that are absent from the active-source tree.

After installing, copying, or recruiting any new skill, run:

```powershell
python -B scripts/refresh_capability_registry.py
```

The court will then classify the new skill into likely 三省六部 offices and may
dispatch it by explicit 差遣.

## Dangerous Codex YOLO Startup Draft

The skill can check whether a Windows startup task already exists for:

```powershell
codex --dangerously-bypass-approvals-and-sandbox
```

Default check/generation command:

```powershell
python -B scripts/ensure_codex_yolo_startup_task.py
```

This checks `\CodexCourt\CodexYoloStartup`. If the task is missing, it generates
local review artifacts under `references/startup-tasks/`: a registration script,
an unregister script, and JSON metadata listing the task name, trigger, command,
working directory, log path, revoke command, and risk. It does not register the
Windows task by default.

Startup-task drafts are target-root-local review material. Do not copy generated
register scripts between `.codex`, `.agents`, Claude, or Hermes skill roots; run
the generator in the target root if a fresh review draft is required. Portable
packages include only `references/startup-tasks/README.md`.

Check-only mode:

```powershell
python -B scripts/ensure_codex_yolo_startup_task.py --check-only
```

Actual registration is a persistent dangerous external-state change. no-sandbox
autostart requires explicit confirmation and must not be inferred from installing
or enabling the skill, or from choosing `super`. Only after a separate
太子回奏 and explicit user approval should the court run:

```powershell
python -B scripts/ensure_codex_yolo_startup_task.py --register --i-understand-dangerous-yolo-startup
```

To revoke a registered task, run the generated
`references/startup-tasks/CodexYoloStartup.unregister.ps1` or use the
`manual_revoke` command recorded in the JSON metadata.

## Local And LAN Shiguan Web Manager

The package includes a standard-library local web manager for the built-in
growth tree. The default ensure command starts or reuses a LAN-reachable service
and reports both the same-machine URL and any same-network URLs. The preferred
entry point is the service watchdog, which also installs/reuses a hidden user
logon task for preserve-only autosync:

```powershell
python -B scripts/ensure_shiguan_service_daemon.py
python -B scripts/ensure_shiguan_web.py
```

The watchdog task is named `CourtShiguanDaemon`; revoke it with
`schtasks /Delete /TN CourtShiguanDaemon /F`.

Manual LAN service command:

```powershell
python -B scripts/serve_shiguan_tree.py --host 0.0.0.0 --port 8765
```

Open `http://127.0.0.1:8765/` on the host machine, or open one of the returned
`lan_urls` such as `http://<LAN-IP>:8765/` from a phone, tablet, or another
computer on the same network. The service is intended for LAN use only. Do not
set up router port forwarding, public tunneling, or public remote exposure unless the
user explicitly asks for that separate external-access change. If Windows
Firewall blocks inbound access, allow the Python process or the chosen local
port for the private network profile.

The web UI includes phone and tablet breakpoints: desktop uses a three-panel
workspace, tablet prioritizes the graph with side panels below, and phones use a
single-column touch layout with larger tap targets and stable graph height.

Opening
`web/shiguan-tree/index.html` directly shows the static shell only; the server
is required for writes and export.

To generate an Obsidian-compatible copy, export outside the source skill
directory:

```powershell
python -B scripts/export_shiguan_obsidian.py --out "./Court-Shiguan-export" --check --zip
```

The export is a derived Markdown vault with frontmatter, wikilinks, redacted
source copies, and no `.obsidian` settings.

For the normal Obsidian cache refresh, use the preserve-only wrapper instead of
exporting directly into the real vault:

```powershell
python -B scripts/sync_shiguan_obsidian_vault.py --dry-run
python -B scripts/sync_shiguan_obsidian_vault.py
```

Obsidian edits and imported files are treated as inbound materials. They go to
shared `shiguan-imports\pending` and require 三省会审/门下复核 before becoming
official records.

## Relationship To Existing Skills

This merged skill replaces the need to invoke `installed-skill-selector`,
`codex-edict`, or `codex-workgroup` directly. It carries the court framework,
refresh scripts, standing-official templates, and an empty portable Shiguan
seed. Local catalogs and stage archives are generated on the host.

- `court-capability-router`: one skill that reads the catalog and applies the
  default court workflow, including the three execution authorities, light/full
  catalog refresh, court roles, 三省上奏/太子回奏 dispatch gates, stage archives,
  Shiguan bilingual keyword/key-behavior recall, built-in growth tree, macro
  relationship graph web manager, old-archive rebuild, Obsidian-compatible
  export, memory decisions, standing-official templates, and memorial reporting.

## Build The Portable Package

Use the packaging script instead of hand-zipping the live directory:

```sh
python -B scripts/package_skill.py --out "court-capability-router-skill.zip"
```

The script stages a clean copy, removes host-local Shiguan record bodies,
derived local records, and local capability catalogs, writes the empty Shiguan
seed files, validates the zip, and keeps the root folder as
`court-capability-router/`.

For true no-sandbox `super` sessions, start Codex with one of these commands
before invoking the skill:

```powershell
codex --dangerously-bypass-approvals-and-sandbox
codex --sandbox danger-full-access --ask-for-approval never
```

A running sandboxed Codex session cannot be reliably hot-switched in place by a
skill; it can only use runtime escalation gates until restarted.
