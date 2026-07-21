# Court Office Name, Profile, And Skill Binding

This section governs office admission for every court transport. An office is
execution-ready when the assignment identity, direct superior, scope, and host
delivery evidence all match the same task. Standing profiles and dossiers are
semantic sources, not byte-validation gates.

## Canonical assignment mapping

`task_name` is collaboration routing metadata. It selects and distinguishes a
bounded assignment; its prefix must match the canonical office token below, but
the name alone does not prove that the office has accepted the assignment.

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

## Executable hierarchy and bounded child-office profile

Name/profile/skill source binding is useful context, but it does not create a
dispatch edge. Ordinary admission/lifecycle and `superCC` must pass the same
deny-by-default `court.dispatch_hierarchy.v1` decision before capacity
selection, task delivery, pane wake, or state mutation. The only normal edges
are `user -> taizi`, `taizi -> zhongshu|menxia|shangshu`, `shangshu -> 六部`,
and an owning ministry to its own bounded child office. Task names,
collaboration addresses, display titles, caller overrides, transport choice,
and special lifecycle roles do not grant another edge.

A non-canonical worker/craftsman assignment must carry
`schema=court.child_office_profile.v1` with:

- exact `child_role`, `office_instance_id`, `owner_role`, and
  `direct_superior`, where `owner_role == direct_superior` is one Six-Ministry
  role;
- `canonical_authority=false` and a worker/craftsman instance kind;
- bounded mandate, expected result, portable `read_scope` and `write_set`, task,
  dispatch, shard/attempt, terminal condition, and source pointers for any
  profile/dossier/skill material the task truly needs;
- the existing P00 `court.semantic.dispatch_context_packet.v1`, which binds the
  one existing `court.semantic.invariant_capsule.v1`.

The child may execute only its bounded assignment; it cannot dispatch a
canonical office, integrate globally, promote itself to a standing office, or
create a separate ledger. A second capsule, child charter override, second
receipt authority, scope widening, changed owner, peer/cross-owner child
dispatch, or synchronized binding/profile tamper fails closed before task/event
bytes change.

## The three source checks

1. **Name check.** Validate the exact `role_key`, canonical `task_name` prefix,
   agent-id prefix, and GongJiang specialization. A matching name proves routing
   metadata only.
2. **Profile check.** Resolve `agents/standing-officials/<role_key>.toml` inside
   the configured profile root when the assignment needs standing mandate
   details. Parse it as declarative TOML and use `[profile].role_key`,
   `office_zh`, and `direct_superior` as semantic evidence. If the file is
   unavailable, report `profile_unavailable` and continue from the bounded
   assignment unless that missing mandate is necessary for the current answer.
3. **Skill check.** Use `decretum-matrix` as the governing skill for court
   semantics. Other skills, MCPs, CLIs, and scripts are selected only when the
   current task needs that capability. Missing or changed auxiliary sources are
   reported as context drift, not as a reason to simulate or loop.

For assignment admission, the task packet should carry:

```text
office_assignment = {
  role_key, office_zh, direct_superior, assignment_id,
  authority, behavior, read_scope, write_set, expected_result,
  profile_source?, dossier_path?, required_skill_names?
}
```

For the office's first reply, preserve
`schema=court.office.role_ack.v1`, `role_acknowledged=YES|DEGRADED`, `role_key`,
`office_zh`, `direct_superior`, `assignment_id`, `agent_dossier_loaded=YES|NO|NOT_NEEDED`,
and `loaded_skills` when a skill was actually loaded. The assignment packet and
first reply are complementary; neither may be inferred from a successful spawn
call.

For ordinary carriers, `office_instance_kind=child_agent|worktree_thread` uses
one admission and lifecycle contract. The instance id and first-spawn
`task_name` must be role-prefixed; a bound `task_name` may be reused only by the
same role. Sidebar labels and thread titles are display metadata, never identity
or readiness proof. `assignment_binding_ready` becomes useful work only after
the office acknowledges the same role, direct superior, scope, and expected
result.

Every ordinary `write_set` and `read_scope` entry is persisted as a
repository-relative portable key: `/` separators plus case-folded path
components. Absolute, drive-qualified, UNC, empty-component, `.` and `..`
paths fail closed. Writer equality and either ancestor/descendant direction are
the same ownership conflict.

A `worktree_thread` proof is never accepted from its asserted fields alone. The
runtime executes only read-only Git queries in the claimed existing worktree and
independently recomputes top-level path, git common-dir, branch, HEAD, and
repository/worktree identity. Every asserted field must match that
recomputation before the first task repository binding is stored; a self-asserted
first-use value is not authority.

## Mode-neutral applicability and false-ready prevention

These rules apply to **all** court offices and all workshop/工匠 assignments in
ordinary serial, ordinary `approval`/`autonomous`/`super`, ordinary
`super并行`, `superCC`, and supported Hermes transports. Ordinary parallelism
does not weaken the binding rule and does not limit it to visible standing
offices: every spawned 三省、六部、史馆、监察 or workshop worker must carry its own
same-assignment identity before useful work is counted.

Legacy records that treated a matching `task_name`, a plausible agent label, a
spawn success, a visible pane, an active identity, or profile-file presence as
execution readiness are `legacy_false_ready`. They are historical evidence only
and must not be promoted to `office_execution_ready=true` without fresh current
assignment acceptance.

Admission is fail closed only for authority and identity faults. Canonical
success is `name_binding=PASSED`, `profile_context=PASSED|NOT_NEEDED|DEGRADED`,
`skill_context=PASSED|NOT_NEEDED|DEGRADED`, and
`office_assignment_accepted=true`. Rejections preserve the most specific status
or reason, including `office_name_mismatch`, `missing_gongjiang`,
`standing_profile_invalid`, `standing_profile_identity_mismatch`,
`standing_profile_fields_missing`, `standing_profile_path_escape`,
`skill_source_not_resolved`, `skill_binding_conflict`, `wrong_direct_superior`,
`scope_conflict`, and `host_delivery_missing`. Unknown or incomplete state is
not readiness, but it is also not a reason to replace a real office dispatch
with CLI loops.

## Freshness at task boundaries

Reconfirm role, direct superior, scope, and expected result immediately before
mutation or final acceptance. If a referenced file changed, treat it as
`context_drift`: reread only the material needed for the current task and keep
moving unless the new content changes authority, scope, risk, or acceptance.
Never turn file freshness into a standalone startup check.
