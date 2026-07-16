# Decretum Matrix Taizi, Three Departments, Shangshu, and Six Ministries Dispatch Hierarchy Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the execution hierarchy fail closed in every transport: the user enters through Taizi, Taizi dispatches the Three Departments, Shangshu alone dispatches the Six Ministries, and a ministry alone may dispatch its own bounded child office.

**Architecture:** Add one data-backed, mode-neutral hierarchy validator with no runtime imports. Ordinary admission, runtime lifecycle, and superCC must call that same validator before capacity selection, task delivery, pane wake, or state mutation. A child office carries a generated bounded profile plus the existing P00 dispatch-context packet and invariant capsule; it never creates a second semantic authority.

**Tech Stack:** Python 3 standard library, JSON manifests, TOML standing profiles, Markdown/YAML authority documents, existing script-style regression checkers and release-gate manifests.

---

## Status and authority

- Plan state: PLAN_ONLY.
- Worktree: D:\project\decretum-matrix-beta0.5.11.
- Branch: release/beta0.5.11.
- Landing base: d79b083fc202d9dc8c89834460191b4da69ad082.
- Current VERSION preimage: beta0.5.10.
- Current index at plan landing: empty.
- Pending-body access: forbidden.
- External publication actions: not authorized by this plan.

### Completed predecessor evidence

The beta0.5.10 release and local-install handoff are complete:

- Release: https://github.com/RowlandL/decretum-matrix/releases/tag/beta0.5.10
- Publication receipt: libu-beta0.5.10-publication-355183007
- Publication receipt SHA-256: b57602c20e514c9b7c77889591e2cd8d661ad8944efc66915946691ac2d867ae
- Install receipt SHA-256: df2a25519555265b0d657fe1aecfd61eee2a430571b015924b7fcdc8481bbf1a
- Next branch/worktree handoff: release/beta0.5.11 at d79b083fc202d9dc8c89834460191b4da69ad082, clean with index zero.

These facts satisfy PLAN_LANDING_GATE. They do not satisfy VERSION_ALIGNMENT_GATE because the new branch intentionally starts with VERSION still equal to beta0.5.10.

## Gate order

The release cycle must preserve this order:

    BETA_0_5_10_INSTALL_PUBLICATION_HANDOFF=PASS
      -> PLAN_LANDING_GATE=PASS
      -> VERSION_ALIGNMENT_GATE
      -> HIERARCHY_RED_GATE
      -> HIERARCHY_GREEN_GATE
      -> ORDINARY_HIERARCHY_GATE
      -> CHILD_OFFICE_P00_GATE
      -> SUPERCC_HIERARCHY_GATE
      -> ROLE_SURFACE_MATCH_GATE
      -> SPEC_GATE
      -> QUALITY_GATE
      -> NEXT_RELEASE_PREPUBLICATION_GATE

PLAN_LANDING_GATE requires the published beta0.5.10 release, accepted local-install receipt, a distinct beta0.5.11 branch/worktree, and clean root/index state. It does not require VERSION to have changed.

VERSION_ALIGNMENT_GATE is implementation Task 1. It aligns VERSION, release constants, manifest identity, and release-facing documents to beta0.5.11 before hierarchy implementation is accepted.

NEXT_RELEASE_PREPUBLICATION_GATE is the final local gate. It may be evaluated only after the implementation, focused regressions, full release suite, deterministic package, and clean-index checks pass. Passing it does not authorize a tag, push, GitHub release, upload, or installation.

## Normative dispatch graph

The validator must classify an edge by action, caller, target, target profile, and instance shape:

| Edge class | Allowed caller | Allowed target | Target direct superior | Notes |
| --- | --- | --- | --- | --- |
| court entry | user | taizi | user | User-facing entry only. |
| deliberation dispatch | taizi | zhongshu, menxia, shangshu | taizi | The main thread/Taizi does not dispatch a ministry. |
| ministry execution dispatch | shangshu | libu-hr, hubu, libu, bingbu, xingbu, gongbu | shangshu | Shangshu is the sole Six-Ministry dispatcher. |
| bounded child-office dispatch | owning ministry | non-canonical child of that same ministry | owning ministry | Requires a validated child-office profile, bounded scopes, and P00 context. |

Special lifecycle roles such as Shiguan, Zaochao, and the bounded patrol diagnostic keep their existing explicit authorities. They are outside the ministry execution graph and must never be accepted as aliases or bypasses for a Taizi-to-ministry or cross-ministry dispatch.

The following must fail closed with stable reason codes:

- taizi -> any Six Ministry;
- zhongshu or menxia -> any Six Ministry;
- user or main -> any office other than taizi;
- any Six Ministry -> a canonical peer ministry;
- a ministry -> another ministry's child office;
- shangshu -> a child-office instance that lacks its owning ministry as direct superior;
- a task/thread name used as caller identity without a bound office profile;
- unknown caller, target, action, profile schema, or instance kind;
- profile, dossier, semantic receipt, or direct-superior mismatch;
- ordinary and superCC interpretations that differ for the same normalized request.

## Data and API contract

### Hierarchy manifest

Create references/manifests/court-dispatch-hierarchy.v1.json as the declarative graph. It must contain:

- schema court.dispatch_hierarchy.v1;
- exact canonical role sets for Taizi, Three Departments, Six Ministries, and special lifecycle roles;
- exact allowed edge classes;
- expected direct superior for each canonical target;
- child-office constraints;
- stable rejection reason codes;
- a deny-by-default policy.

The manifest is data, not executable authority by itself. scripts/court_dispatch_hierarchy.py owns parsing, schema validation, normalization, and decisions.

### Shared validator

Create scripts/court_dispatch_hierarchy.py as a leaf module that imports only the Python standard library. Expose a typed decision and one public validator:

    validate_dispatch_hierarchy(
        *,
        action,
        calling_office,
        target_role,
        target_direct_superior,
        instance_kind,
        canonical_authority,
        owner_role=None,
        child_profile=None,
    ) -> DispatchHierarchyDecision

The decision records allowed, edge_class, normalized caller/target/owner, reason_codes, hierarchy schema, and manifest SHA-256. Unknown or incomplete evidence returns denied, never an inferred edge.

Existing budget-lease direct_superior values describe the caller's position in the court. They must not be mistaken for target_direct_superior. Ordinary admission obtains the target superior from requested_bindings; superCC obtains it from the loaded standing profile. The validator must keep those concepts separate.

### Child-office profile

A bounded child is not a new standing ministry. Its generated court.child_office_profile.v1 object contains:

- child_role and office_instance_id;
- owner_role and direct_superior, which must be the same Six-Ministry role;
- canonical_authority=false;
- instance_kind=worker, craftsman, or office_worker_instance;
- bounded mandate and expected result;
- portable read_scope and write_set;
- task_id, dispatch_uid, shard_id, and attempt;
- profile, dossier, and governing-skill hashes;
- expiry/terminal condition;
- dispatch_context_packet_sha256 and semantic_receipt_sha256.

The child profile carries the existing court.semantic.dispatch_context_packet.v1. That packet carries the existing court.semantic.invariant_capsule.v1 under P00. Do not add a second invariant capsule, second charter, second semantic receipt authority, or a child-owned durable ledger.

GongBu-GongJiang remains the canonical compatibility example: role_key remains gongbu, owner_role/direct_superior is gongbu for the worker instance, and canonical Gongbu remains directly under Shangshu.

## Non-goals

- No redesign of Shiguan, Zaochao, patrol diagnostics, memory governance, or pending imports.
- No second shared task ledger or mutable tasks.json.
- No new visible Six-Ministry core panes.
- No generic parent/child agent framework outside the court hierarchy.
- No release publication, remote mutation, tag, PR, or installation.
- No office-pack, DLC, scope-promotion, or dual-license-plan implementation.

## Task 1: Align the beta0.5.11 release identity

**Files:**

- Modify: VERSION
- Modify: scripts/release_payload_manifest.py
- Modify: scripts/check_release_manifest.py
- Modify: release-manifest.json
- Modify: README.md
- Modify: CHANGELOG.md
- Modify: RELEASE-LOG.md

**Step 1: Write the failing identity expectations**

Change the release self-tests and manifest checker expectations to beta0.5.11, version core 0.5.11, artifact decretum-matrix-beta0.5.11.zip, matching sidecar/attestation names, and refs/tags/beta0.5.11.

Run:

    python scripts/check_release_manifest.py --json
    python scripts/release_payload_manifest.py --self-test --check --json

Expected: FAIL because VERSION and production release constants still identify beta0.5.10.

**Step 2: Align production identity**

Set VERSION and production constants to beta0.5.11. Add beta0.5.11 branch/release sections to README.md, CHANGELOG.md, and RELEASE-LOG.md without claiming publication. Update release-manifest.json through the existing manifest generator/check flow; do not hand-edit payload hashes that the generator owns.

**Step 3: Verify VERSION_ALIGNMENT_GATE**

Run:

    python scripts/check_release_manifest.py --json
    python scripts/release_payload_manifest.py --self-test --check --json
    git diff --check

Expected: both identity checks pass and every release-facing surface reports beta0.5.11. Record VERSION_ALIGNMENT_GATE=PASS. Re-run manifest generation after later source changes before final acceptance.

## Task 2: Land the hierarchy RED matrix

**Files:**

- Create: scripts/check_court_dispatch_hierarchy.py
- Create: references/manifests/court-dispatch-hierarchy.v1.json
- Modify: scripts/check_court_dispatch_policy.py
- Modify: scripts/check_court_agent_lifecycle.py
- Modify: scripts/check_supercc_ministry_dispatch.py

**Step 1: Add table-driven edge fixtures**

Cover at least:

- taizi -> zhongshu/menxia/shangshu accepted;
- shangshu -> each Six Ministry accepted;
- taizi -> gongbu rejected;
- zhongshu -> hubu rejected;
- menxia -> libu rejected;
- gongbu -> canonical xingbu rejected;
- gongbu -> bounded GongBu-GongJiang accepted;
- gongbu -> Hubu-owned child rejected;
- caller/profile direct-superior mismatch rejected;
- missing caller, target, owner, or instance evidence rejected;
- identical normalized request produces the same decision in ordinary and superCC adapters.

**Step 2: Add entry-point regressions**

Add a real ordinary admission probe that currently selects gongbu for calling_office=taizi. Add a superCC probe that currently resolves an explicit taizi caller for role=gongbu. Assert both are rejected before state change or delivery.

**Step 3: Prove RED**

Run:

    python scripts/check_court_dispatch_hierarchy.py
    python scripts/check_court_dispatch_policy.py
    python scripts/check_court_agent_lifecycle.py
    python scripts/check_supercc_ministry_dispatch.py

Expected: the new hierarchy assertions fail against the beta0.5.10-derived runtime. Preserve the first exact failures and record HIERARCHY_RED_GATE=PASS only when the failures are caused by the missing shared enforcement, not fixture defects.

## Task 3: Implement the canonical hierarchy validator

**Files:**

- Create: scripts/court_dispatch_hierarchy.py
- Modify: references/manifests/court-dispatch-hierarchy.v1.json
- Modify: scripts/check_court_dispatch_hierarchy.py

**Step 1: Validate the manifest itself**

Reject duplicate roles/edges, role-set overlap, unsupported schema, a canonical role used as a child, a child edge whose owner is not a Six Ministry, and any edge whose expected direct superior disagrees with the canonical role table.

**Step 2: Implement normalization and stable decisions**

Normalize exact lowercase role keys only. Do not accept collaboration paths, display titles, office_zh text, aliases, or task names as authority. Return stable reasons such as:

- dispatch_hierarchy_caller_required;
- dispatch_hierarchy_target_required;
- dispatch_hierarchy_unknown_caller;
- dispatch_hierarchy_unknown_target;
- dispatch_hierarchy_edge_forbidden;
- dispatch_hierarchy_target_superior_mismatch;
- dispatch_hierarchy_child_profile_required;
- dispatch_hierarchy_child_owner_mismatch;
- dispatch_hierarchy_child_scope_unbounded;
- dispatch_hierarchy_manifest_invalid.

**Step 3: Make the leaf checker GREEN**

Run:

    python scripts/check_court_dispatch_hierarchy.py

Expected: PASS with a machine-readable summary naming the manifest schema/hash and every allowed/denied fixture count.

## Task 4: Enforce the hierarchy in ordinary admission and lifecycle

**Files:**

- Modify: scripts/court_agent_admission.py
- Modify: scripts/court_dispatch_policy.py
- Modify: scripts/court_runtime.py
- Modify: scripts/court_cli.py
- Modify: scripts/check_court_dispatch_policy.py
- Modify: scripts/check_court_agent_lifecycle.py

**Step 1: Validate before capacity selection**

In court_agent_admission.admit_roles and court_dispatch_policy.select_wave, validate every requested role/binding before approved-budget selection and slot truncation. A forbidden edge must select zero roles and preserve all requested roles as deferred with the hierarchy reason.

**Step 2: Bind target identity**

Require requested_bindings for formal office dispatch. Bind target direct superior, canonical_authority, instance_kind, owner_role, profile/dossier hashes, and child profile where applicable. Do not infer authorization from requested_roles alone.

**Step 3: Revalidate at the mutation boundary**

The lifecycle path must repeat the same hierarchy validation under its existing lock immediately before persisting admission/start evidence. If the caller, profile, manifest hash, or child profile changed, reject without changing runtime bytes.

**Step 4: Persist parity evidence**

Admission/lifecycle receipts must include hierarchy_schema, hierarchy_manifest_sha256, hierarchy_edge_class, hierarchy_calling_office, hierarchy_target_role, hierarchy_owner_role when applicable, and hierarchy_gate=PASSED.

**Step 5: Verify ordinary paths**

Run:

    python scripts/check_court_dispatch_hierarchy.py
    python scripts/check_court_dispatch_policy.py
    python scripts/check_court_agent_lifecycle.py
    python scripts/check_court_runtime.py

Expected: PASS, including rejection-with-unchanged-bytes checks for taizi -> ministry and cross-ministry child dispatch. Record ORDINARY_HIERARCHY_GATE=PASS.

## Task 5: Bind bounded child offices to owner profile and P00

**Files:**

- Modify: scripts/court_office_bootstrap.py
- Modify: scripts/court_runtime.py
- Modify: scripts/court_semantic_continuity.py
- Modify: scripts/check_court_office_assignment_binding.py
- Modify: scripts/check_court_agent_lifecycle.py
- Modify: scripts/check_semantic_continuity.py
- Modify: scripts/check_p00_semantic_dispatch_context.py
- Modify: references/sections/court-office-name-profile-skill-binding.md
- Modify: references/court-state-runtime-agents.md

**Step 1: Generate the child-office profile**

Extend office assignment binding to emit court.child_office_profile.v1 only for non-canonical worker instances. Require the owner ministry's exact profile/dossier/skill hashes, bounded portable scopes, task and dispatch ids, and a terminal condition.

**Step 2: Preserve the single semantic capsule**

Bind the generated profile to the existing dispatch context packet and semantic receipt. Reject unknown second-capsule fields, child charter overrides, capsule/receipt hash mismatch, a stale semantic epoch, or a packet over the existing 2 KiB P00 limit.

**Step 3: Preserve one canonical authority**

The child may execute only its bounded assignment. It cannot dispatch a canonical office, integrate globally, change owner_role, widen read/write scope, or survive its terminal condition as a standing office.

**Step 4: Verify P00 and compatibility**

Run:

    python scripts/check_court_office_assignment_binding.py
    python scripts/check_semantic_continuity.py
    python scripts/check_p00_semantic_dispatch_context.py
    python scripts/check_court_agent_lifecycle.py

Expected: PASS. GongBu-GongJiang remains supported, a same-owner bounded child passes, and second-capsule/cross-owner fixtures fail without mutation. Record CHILD_OFFICE_P00_GATE=PASS.

## Task 6: Enforce the same validator in superCC

**Files:**

- Modify: scripts/ensure_supercc_court.py
- Modify: scripts/supercc_office_state.py
- Modify: scripts/check_supercc_ministry_dispatch.py
- Modify: scripts/check_supercc_functional.py
- Modify: scripts/check_supercc_truth_gates.py

**Step 1: Validate before transport work**

In enter_dispatch, resolve the caller and target profile, call the shared validator, and stop on denial before uniqueness checks trigger delivery, before squad task/send, before native-enter wake, and before office-state mutation.

**Step 2: Remove caller override bypass**

An explicit --calling-office may narrow or accurately state authority; it may not replace the canonical hierarchy. Therefore --calling-office taizi --role gongbu must fail with dispatch_hierarchy_edge_forbidden. The default ministry caller remains shangshu and must pass when its profile evidence is valid.

**Step 3: Bind delivery evidence**

The dispatch payload and returned JSON include the same hierarchy schema/hash/edge fields as ordinary admission. The transport may add pane, squad, and native-enter evidence, but it may not reinterpret the hierarchy result.

**Step 4: Verify no-delivery failure**

Use fixture/mocked transport hooks to prove a forbidden edge performs zero squad task/send, zero native-enter, zero pane launch/wake, and zero state write.

Run:

    python scripts/check_supercc_ministry_dispatch.py
    python scripts/check_supercc_functional.py
    python scripts/check_supercc_truth_gates.py
    python scripts/check_court_dispatch_hierarchy.py

Expected: PASS with explicit ordinary/superCC decision parity. Record SUPERCC_HIERARCHY_GATE=PASS.

## Task 7: Align skill, references, profiles, and dossiers

**Files:**

- Modify: SKILL.md
- Modify: README.md
- Modify: references/court-roles.yaml
- Modify: references/court-offices-dispatch.md
- Modify: references/court-state-runtime-agents.md
- Modify: references/sections/court-office-name-profile-skill-binding.md
- Modify: agents/standing-officials/taizi.toml
- Modify: agents/standing-officials/zhongshu.toml
- Modify: agents/standing-officials/menxia.toml
- Modify: agents/standing-officials/shangshu.toml
- Modify: agents/standing-officials/libu-hr.toml
- Modify: agents/standing-officials/hubu.toml
- Modify: agents/standing-officials/libu.toml
- Modify: agents/standing-officials/bingbu.toml
- Modify: agents/standing-officials/xingbu.toml
- Modify: agents/standing-officials/gongbu.toml
- Modify generated matching files under agents/office-dossiers and agents/supercc-dossiers

**Step 1: State the executable hierarchy exactly**

Every authority surface must say:

- Taizi/main may dispatch only the Three Departments for normal court execution;
- Zhongshu drafts and Menxia reviews but neither dispatches a Six Ministry;
- Shangshu alone dispatches the Six Ministries;
- a ministry may dispatch only its own bounded child office;
- ordinary and superCC call the same validator;
- child offices reuse the existing P00 semantic capsule and do not gain canonical authority.

**Step 2: Regenerate role files from standing profiles**

Use scripts/sync_codex_agents_from_profiles.py for only the affected canonical roles. Review generated diffs for matching direct superior, dispatch policy, child-office boundary, and no user-facing ministry language.

**Step 3: Check all role surfaces**

Run:

    python scripts/check_supercc_profiles.py
    python scripts/check_codex_agent_roles.py
    python scripts/check_court_office_assignment_binding.py
    python scripts/check_supercc_ministry_dispatch.py

Expected: PASS with role/profile/dossier parity. Record ROLE_SURFACE_MATCH_GATE=PASS.

## Task 8: Make hierarchy enforcement a mandatory release gate

**Files:**

- Modify: scripts/release_gate_manifest.py
- Modify: references/manifests/release-gates.v1.json
- Modify: references/court-policy.yaml
- Modify: scripts/check_release_gate.py
- Modify: scripts/package_skill.py
- Modify: scripts/check_portability.py
- Modify: release-manifest.json

**Step 1: Register the source gate**

Add court_dispatch_hierarchy as an always-required source gate invoking:

    $PYTHON scripts/check_court_dispatch_hierarchy.py

The release-gate manifest checker must require the exact step name, class, command, and always condition.

**Step 2: Include all new authority files**

Add the new Python checker/module and hierarchy JSON manifest to packaging and portability allowlists. Regenerate release-manifest.json so their exact bytes and SHA-256 values are covered.

**Step 3: Prove the gate cannot be omitted**

The release-gate self-test must fail when the hierarchy step is missing, renamed, reordered outside its source phase, conditionalized, or pointed at another command.

Run:

    python scripts/check_release_gate.py
    python scripts/check_portability.py
    python scripts/check_release_manifest.py --json

Expected: PASS with court_dispatch_hierarchy listed as mandatory. Do not set NEXT_RELEASE_PREPUBLICATION_GATE yet.

## Task 9: Run the SPEC review

**Files:**

- Modify only if a contradiction is found: SKILL.md, README.md, references/court-roles.yaml, references/court-offices-dispatch.md, references/court-state-runtime-agents.md

**Step 1: Search for contradictory authority**

Run:

    rg -n -i "taizi.*(dispatch|create|spawn).*(libu|hubu|bingbu|xingbu|gongbu|ministry)|calling_office=taizi|Six Ministries.*Taizi|六部.*太子" SKILL.md README.md references agents scripts

Classify every hit as allowed historical/example text, special lifecycle authority, or a contradiction. No unexplained execution bypass may remain.

**Step 2: Trace one request across both modes**

Document the same normalized request through:

    taizi -> shangshu -> gongbu -> bounded GongBu-GongJiang

For ordinary and superCC, compare caller, target, owner, direct superior, manifest hash, semantic receipt, rejection behavior, and mutation boundary.

**Step 3: Record SPEC_GATE**

SPEC_GATE=PASS requires no contradictory authority, no mode-specific hierarchy, no second semantic capsule, and no special-role bypass of ministry execution.

## Task 10: Run QUALITY and the beta0.5.11 prepublication gate

**Files:**

- Modify generated release identity/hash surfaces only when required by the existing deterministic build flow.

**Step 1: Run focused gates**

    python scripts/check_court_dispatch_hierarchy.py
    python scripts/check_court_dispatch_policy.py
    python scripts/check_court_agent_lifecycle.py
    python scripts/check_court_office_assignment_binding.py
    python scripts/check_semantic_continuity.py
    python scripts/check_p00_semantic_dispatch_context.py
    python scripts/check_supercc_ministry_dispatch.py
    python scripts/check_supercc_functional.py
    python scripts/check_supercc_truth_gates.py
    python scripts/check_supercc_profiles.py

**Step 2: Run the release suite**

    python scripts/quick_validate.py .
    python scripts/check_release_gate.py
    python scripts/check_release_manifest.py --json
    python scripts/release_payload_manifest.py --self-test --check --json
    python scripts/check_portability.py
    python scripts/check_package_privacy.py -q
    python scripts/build_release_artifacts.py --self-test --json

Also execute every always-required source command from references/manifests/release-gates.v1.json through the existing release-gate runner.

**Step 3: Rebuild deterministic identity evidence**

Regenerate release-manifest.json after the final source bytes are fixed. Build the beta0.5.11 artifact in the approved release output location, then verify Git-tree-to-ZIP mapping, payload manifest, sidecar naming, privacy exclusions, and deterministic rebuild equality.

**Step 4: Verify repository state**

    git diff --check
    git status --short
    git diff --cached --name-only

Expected: diff check passes; no staged files; no unexpected generated/private artifacts. Before any later acceptance handoff, the designated implementation owner must leave the child repository index empty.

**Step 5: Set final local gates**

QUALITY_GATE=PASS requires every focused and release check above to pass with preserved receipts.

NEXT_RELEASE_PREPUBLICATION_GATE=PASS requires:

- VERSION_ALIGNMENT_GATE=PASS;
- HIERARCHY_RED_GATE=PASS and HIERARCHY_GREEN_GATE=PASS;
- ORDINARY_HIERARCHY_GATE=PASS;
- CHILD_OFFICE_P00_GATE=PASS;
- SUPERCC_HIERARCHY_GATE=PASS;
- ROLE_SURFACE_MATCH_GATE=PASS;
- SPEC_GATE=PASS;
- QUALITY_GATE=PASS;
- deterministic beta0.5.11 package and manifest evidence;
- clean working tree/index at the release handoff;
- zero pending-body access;
- zero unauthorized remote/publication action.

Only after this gate passes may a separately authorized beta0.5.11 publication workflow begin.

## Stop conditions

Stop and preserve evidence if:

- beta0.5.10 publication/install receipts cannot be verified at the release handoff;
- VERSION, release constants, manifest identity, or docs disagree;
- ordinary and superCC return different hierarchy decisions;
- a forbidden edge reaches capacity selection, task delivery, native-enter, or state mutation;
- child-office scope is unbounded or owner/profile/P00 evidence is incomplete;
- a second semantic capsule or mutable shared ledger is introduced;
- a required release gate is missing or can be bypassed;
- the repository has staged changes at an acceptance gate;
- pending-body access or an unauthorized external action would be required.

## Completion contract

Implementation is complete only when beta0.5.11 locally proves this invariant:

    USER -> TAIZI -> THREE_DEPARTMENTS
    SHANGSHU -> SIX_MINISTRIES
    SIX_MINISTRY -> SAME_OWNER_BOUNDED_CHILD_OFFICE

Every other normal execution edge is denied before side effects, ordinary and superCC cite the same hierarchy manifest and validator decision, child offices carry a bounded generated profile plus the one existing P00 semantic capsule, and the mandatory hierarchy release gate passes before beta0.5.11 publication.
