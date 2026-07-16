# Court Office Name, Profile, And Skill Binding

This section governs office admission for every court transport. An office is
execution-ready only when three independent proofs all pass for the same
assignment: canonical name binding, standing-profile binding, and required-skill
binding. No one proof implies either of the other two.

## Canonical assignment mapping

`task_name` is collaboration routing metadata. It selects and distinguishes a
bounded assignment; its prefix must match the canonical office token below, but
the name alone does not prove that the standing profile or required skills were
loaded.

| `role_key` | official name head | `task_name` prefix | agent-id prefix |
| --- | --- | --- | --- |
| `taizi` | `TaiZi` | `taizi` | `taizi` |
| `zhongshu` | `ZhongShu` | `zhongshu` | `zhongshu` |
| `menxia` | `MenXia` | `menxia` | `menxia` |
| `shangshu` | `ShangShu` | `shangshu` | `shangshu` |
| `libu-hr` | `LiBuHR` | `libu_hr` | `libu-hr` |
| `libu` | `LiBu` | `libu` | `libu` |
| `hubu` | `HuBu` | `hubu` | `hubu` |
| `gongbu` | `GongBu` | `gongbu` | `gongbu` |
| `xingbu` | `XingBu` | `xingbu` | `xingbu` |
| `bingbu` | `BingBu` | `bingbu` | `bingbu` |
| `shiguan` | `ShiGuan` | `shiguan` | `shiguan` |
| `shiguan-hermes` | `ShiGuanHermes` | `shiguan_hermes` | `shiguan-hermes` |
| `zaochao` | `ZaoChao` | `zaochao` | `zaochao` |
| `patrol-inspector` | `PatrolInspector` | `patrol_inspector` | `patrol-inspector` |

The `task_name` form is `<task_name prefix>_<bounded-suffix>` and the agent-id
form is `<agent-id prefix>-<bounded-suffix>`. Suffixes must be nonempty canonical
lowercase tokens; path separators, traversal, prefix lookalikes, and empty
suffixes fail closed.

## GongJiang semantics

`GongJiang` is an explicit 工部 worker specialization, not a fifteenth standing
office and not a free-form label. When `requires_gongjiang=true`, `role_key` must
remain `gongbu`, the official head becomes `GongBu-GongJiang`, the `task_name`
prefix becomes `gongbu_gongjiang`, and the agent-id prefix becomes
`gongbu-gongjiang`. The specialized assignment records
`direct_superior=gongbu`; the ordinary canonical Gongbu office continues to
record `direct_superior=shangshu`. Applying `GongJiang` to another role,
omitting it when the assignment requires it, or using a lookalike token fails
as `missing_gongjiang` or `office_name_mismatch`.

## The three independent proofs

1. **Name proof.** Validate the exact `role_key`, canonical `task_name` prefix,
   agent-id prefix, and GongJiang specialization. A matching name proves routing
   metadata only.
2. **Profile proof.** Resolve `agents/standing-officials/<role_key>.toml` inside
   the configured profile root, parse it as declarative TOML, require
   `[profile].role_key`, `office_zh`, and `direct_superior`, and bind the resolved
   absolute `profile_source` plus lowercase SHA-256 `profile_hash`. The TOML is
   declarative identity/mandate data only: its existence, filename, or contents
   do not execute an office and do not prove skill loading.
3. **Skill proof.** For every required skill, bind `name`, resolved absolute
   `source`, lowercase SHA-256 `sha256`, and nonempty `purpose`; verify the file
   exists and its current bytes match. The acknowledgement must repeat the same
   identity as `ack_name` and `ack_sha256`. `decretum-matrix` is always required;
   its technical source locator remains the repository `SKILL.md`.
   `court-capability-router` may be accepted only as a deprecated technical
   locator input and is normalized to `decretum-matrix` in persisted current
   bindings. Missing, conflicting, duplicate-with-different-evidence, stale, or
   incomplete skill evidence fails closed.

For assignment admission, the skill evidence and acknowledgement schema is:

```text
required_skill_bindings[] = {
  name, source, sha256, purpose, ack_name, ack_sha256
}
ack_name == name
ack_sha256 == sha256
```

For spawn preload acknowledgement, preserve
`schema=court.office.preload_ack.v1`, `preload_status=PASSED`, `role_key`,
`office_zh`, `direct_superior`, `profile_hash`, `dossier_hash`,
`court_skill_hash`, `agent_dossier_loaded=YES`, and `loaded_skills` containing
`decretum-matrix`. The assignment proof and preload acknowledgement are
complementary; neither may be inferred from a successful spawn call.

For ordinary carriers, `office_instance_kind=child_agent|worktree_thread` uses
one admission and lifecycle contract. The instance id and first-spawn
`task_name` must be role-prefixed; a bound `task_name` may be reused only by the
same role. Sidebar labels and thread titles are display metadata, never identity
or readiness proof. `assignment_binding_ready` does not imply
`office_execution_ready`; the latter becomes true only after the exact ordinary
dossier/profile/skill preload acknowledgement passes.

Every ordinary `write_set` and `read_scope` entry is persisted as a
repository-relative portable key: `/` separators plus case-folded path
components. Absolute, drive-qualified, UNC, empty-component, `.` and `..`
paths fail closed. Writer equality and either ancestor/descendant direction are
the same ownership conflict.

A `worktree_thread` proof is never accepted from its asserted fields alone. The
runtime executes only read-only Git queries in the claimed existing worktree and
independently recomputes top-level path, git common-dir, branch, HEAD,
repository/worktree identity, and fingerprints. Every asserted field must match
that recomputation before the first task repository binding is stored; a
self-asserted first-use value is not authority.

## Mode-neutral applicability and false-ready prevention

These rules apply to **all** court offices and all workshop/工匠 assignments in
ordinary serial, ordinary `approval`/`autonomous`/`super`, ordinary
`super并行`, `superCC`, and supported Hermes transports. Ordinary parallelism
does not weaken the binding rule and does not limit it to visible standing
offices: every spawned 三省、六部、史馆、监察 or workshop worker must carry its own
same-assignment proofs before useful work is counted.

Legacy records that treated a matching `task_name`, a plausible agent label, a
spawn success, a visible pane, an active identity, or profile-file presence as
execution readiness are `legacy_false_ready`. They are historical evidence only
and must not be promoted to `office_execution_ready=true` without fresh complete
proofs.

Admission is fail closed. Canonical success is
`name_binding=PASSED`, `profile_binding=PASSED`, `skill_binding=PASSED`, and only
then `office_execution_ready=true`. Rejections preserve the most specific status
or reason, including `office_name_mismatch`, `missing_gongjiang`,
`standing_profile_missing`, `standing_profile_invalid`,
`standing_profile_identity_mismatch`, `standing_profile_fields_missing`,
`standing_profile_path_escape`, `skill_binding_invalid`,
`required_court_skill_missing`, `required_skill_missing`,
`required_skill_hash_mismatch`, `skill_source_not_resolved`,
`skill_ack_incomplete`, `skill_binding_conflict`, and
`stale_profile_or_skill`. Unknown or incomplete state is not readiness.

## TOCTOU freshness gate

Build and validate the complete name/profile/skill binding before acquiring the
runtime mutation lock (`prelock`). After the lock is acquired and immediately
before lifecycle state is written (`inlock`), rebuild the binding from the same
inputs and reread the profile and skill bytes. The in-lock binding must equal the
pre-lock binding exactly. Any file replacement, hash drift, acknowledgement
drift, mapping drift, missing input, or reconstruction error is
`stale_profile_or_skill`; abort admission without creating or advancing the
agent lifecycle. Never reuse a prior binding across assignments or convert a
freshness failure into a warning.
