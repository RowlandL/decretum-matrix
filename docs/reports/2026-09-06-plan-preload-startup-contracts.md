# Plan, preload and startup contract repair

The native test task `01a074d5-3399-7ed3-a642-b8a163538943` produced real
department reports, but plan submission required a charter_revision field that
normal agent creation never wrote. New agents and report events now carry that
revision. Legacy epoch-only records remain readable when task, semantic epoch,
charter digest, office, superior and the actual report event still bind the
current case. Explicit conflicting revisions are rejected; old agents are not
silently rewritten. Native delivery receipt checks remain required.

`court plan submit` accepts either its three-field request or the complete,
task-bound `court plan template` payload. Unknown fields and foreign template
task IDs are rejected. No manual metadata stripping is needed.

Preload evidence accepts positional Get-Content paths, explicit -Path or
-LiteralPath, and semicolon or newline separators. It still requires completed
successful host read events, installed paths and the child acceptance. Preview,
dynamic shell expressions and textual mentions cannot replace reads. Real
Shangshu commands previously classified as zero reads now resolve correctly.

Early deliberation states can use the dedicated pause command and resume within
their original stage's legal transitions. Pause does not bypass plan review or
allow a jump to ministries/completion.

For startup use `court status --view compact --limit 1`, or MCP court.status with
view=compact. This path does not read event history or emit agent/admission
ledgers. Existing default full status remains compatible. In the real copied
case, response payload size fell from 143275 to 446 UTF-8 bytes (99.69%); this is
an output-size measurement, not an end-to-end model token benchmark. Unchanged
skill reads are reused and history/help is loaded only when needed. Runtime
file rehash remains forbidden; installation declarations are generated only by
the normal installation process.

The four special lifecycle roles (shiguan, shiguan-hermes, zaochao and
patrol-inspector) have no ordinary native dispatch edge in the existing
hierarchy. MCP now reports ordinary_native_dispatch_not_supported for these
known roles instead of an unknown-role error. No dispatch edges, actor
authority or superCC fallback were added. A fourteen-role native OK claim is
therefore still unsupported and must be reported accurately.

Validation includes real producer -> plan submission on a private copy through
the CLI, direct template submission, legacy compatibility and stale/foreign
producer negatives, legitimate read forms and negative read evidence, pause/
resume, compact MCP/CLI status, runtime regression and no-file-rehash checks.
The source test task retains responsibility for a new real office/closeout
acceptance. A copied-case regression is not fresh model acceptance.
