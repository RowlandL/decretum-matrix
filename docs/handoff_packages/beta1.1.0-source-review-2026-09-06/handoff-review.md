# beta1.1.0 Source-Level Review & Re-Verification Handoff (2026-09-06)

- Resumed thread: `codex://threads/01a0715e-8957-7910-9800-eb19ed5d1437` (original status `systemError`)
- This review thread: DeepSeek Harness session (workspace `D:\project`)
- Authority brief: `D:\project\decretum-matrix\docs\handoff_packages\handoff.MD`
- Branch: `release/beta1.1.0`
- Source head (committed): `c7115ed fix: make plan review templates directly composable`
- Working tree: **dirty** — carries the previous thread's uncommitted refactor plus this review's corrective edits
- Target version: `beta1.1.0`
- Purpose: independent source-level review + re-verification, 5-Why root-cause tracing, then package for ChatGPT web re-review.

---

## 1. Executive Summary

| Item | Result |
|---|---|
| T08 red-line gates (4 named in handoff) | **GREEN** (isolated, verified) |
| Full required suite (`run_checks`, 39 checks) | **25 PASS / 14 FAIL** (measured live) |
| Root cause of most failures | One **incomplete `court_code` / `semantic-binding` refactor** left production code and check fixtures in mismatched states |
| Review verdict | Not release-ready as-is; T08 slice is deliverable; the surrounding suite needs the remaining fixture/contract reconciliation |

The four red-line gates listed in the handoff are now fail-closed and are backed by fresh isolated evidence (see `evidence/t08-gate-status.json` and the green marker files). Remaining failures are **not** the four gates; they are separate stale-contract/stale-fixture issues left by the previous thread.

---

## 2. Verification Method

- Runs were executed locally on Windows (Python 3.14) via the repository scripts.
- The full required suite was run through the existing isolated runner:
  `D:\project\.staging\dm110-20260905\run_checks.py --run review-full-20260906-171707 --jobs 4`
  (each check runs in its own sandbox with cleaned `COURT_*`/`SHIGUAN_*` environment, `HOME`/`USERPROFILE` redirected, and `cwd = D:\project\decretum-matrix`).
- Full result file: `evidence/full-suite-summary.json` (39 rows).
- The four T08 gates were verified by the isolated harness:
  `D:\project\.staging\dm110-20260905\t08-bingbu\t08-gate-evidence.py`
  → `T08_GATE_EVIDENCE_GREEN_OK` (exit 0), output in `evidence/*`.

Cleanup performed before re-verification: removed `scripts/**/__pycache__` (7 stale `.pyc` files) that were counted as `generated_runtime` by `source_budget`.

---

## 3. T08 Red-Line Gates — RESOLVED (green)

| Gate | Status | Verifying check |
|---|---|---|
| `CONSULTATION_INVALID_SENDER_ACCEPTED` | GREEN | `check_consultation_refs_stay_on_existing_report_and_result_evidence` |
| `CONSULTATION_UNADMITTED_OFFICE_ACCEPTED` | GREEN | same |
| `KeyError: 'residual_gaps'` (archive producer) | GREEN | `check_archive_receipt_records_runtime_replays_and_completes_with_concerns` |
| `CHECKPOINT_PRODUCER_MISSING_BOTH_ACCEPTED` | GREEN | same |

Evidence files in this package:
- `evidence/t08-gate-status.json`
- `evidence/green-consultation.txt` → `CONSULTATION_GREEN_OK`
- `evidence/green-archive-producer.txt` → `ARCHIVE_PRODUCER_GREEN_OK`
- `evidence/green-consultation-unadmitted-office.txt` → `CONSULTATION_UNADMITTED_OFFICE_REJECTED`
- `evidence/green-checkpoint-producer-missing-both.txt` → `CHECKPOINT_PRODUCER_MISSING_BOTH_REJECTED`

### 3.1 Root cause (5-Why) for the four gates

1. **Why were all four gates red?** The runtime either accepted invalid consultation refs / missing producer evidence, or the archive producer receipt lacked `residual_gaps`.
2. **Why did the runtime accept them?** The validation code was written against the *old* contract: consultation refs were checked via `task.charter_sha256`/`task_id` fields that no longer exist after the refactor, the `agent-start` `--case-ref` CLI arg was not JSON-parsed (string vs dict), and `complete_task_atomically` did not require `producer_receipt`/`producer_receipt_sha256` in the checkpoint.
3. **Why did the contract change underneath the validation?** The prior thread introduced `court_code` + `invariant_capsule` + `case_ref` as the identity spine and removed `charter_sha256`-based identity from creation, but did not finish migrating all consumers (runtime validators, CLI parsers, check fixtures).
4. **Why wasn't the migration finished?** The thread ended in `systemError` mid-refactor (crash), leaving a mixed old/new contract.
5. **Why did this survive to handoff?** The handoff brief listed the four gates as blockers; the new T08 check functions existed but could not run green because their fixtures (plan-backed admission, `case_ref` args) and the runtime branch still used old fields.

### 3.2 Fixes applied (T08)

- `scripts/court_runtime.py`:
  - `_validated_consultation_refs_for_task`: replaced obsolete `task_id`/`charter_sha256` checks with a normalized `case_ref` comparison (court_code + charter_revision) against `case_reference(task)`; sender-role mismatch, unadmitted/invalid recipient, foreign/stale plan, write-authority grant all raise.
  - `build_parser().add_agent_semantic_binding`: `--case-ref` now uses `type=json_object_argument` (previously stayed a string → `agent_semantic_binding_mismatch:case_ref`).
  - `create_task`: legacy (non-case) creates now generate a deterministic, contract-valid `court_code` (`_legacy_court_code`), fixing `court_code_required` for legacy fixtures and binding capsule/case-ref/archive to one code.
  - `complete_task_atomically`/`validate_checkpoint_receipt`: producer receipt + digest are mandatory (`archive_producer_evidence_missing` when both missing) — verified by reproducer and the archive check.
- `scripts/checks/check_semantic_continuity.py`:
  - T08 consultation check now builds a plan-reviewed dispatchable case (`_reviewed_dispatchable_case`) before admission; report args carry `case_ref`; the stale-binding test mutates the normalized `case_ref`+plan_ref instead of a removed top-level `charter_revision`.
- `scripts/checks/check_court_runtime_completion.py`:
  - `revision_binding` receives `court_code`; `revision_capsule` drops forbidden digest fields; `complete_args` supplies `case_ref` instead of `expected_charter_sha256`.
- `scripts/court_semantic_continuity.py`:
  - `semantic_binding_for_revision` now **derives and stores** `charter_sha256` and `invariant_capsule_sha256` on the task/binding so the refactor does not strand consumers (semantic resume, result binding, many checks) that still read those fields.
- `scripts/court_runtime.py` additionally: invalidation snapshot now records `invariant_capsule_sha256`.

---

## 4. Additional Regressions Found & Fixed During Review

### 4.1 `ImportError: cannot import name 'canonical_child_office_binding_sha256'`

- **Observed:** `check_court_runtime`, `check_court_agent_lifecycle`, `check_court_dispatch_policy` all fail at import.
- **5-Why:** (1) module import fails → (2) function no longer defined in `court_office_bootstrap` → (3) previous thread deleted `canonical_child_office_binding_sha256` + `_canonical_child_binding_value` from the working tree → (4) those functions were still consumed by many check modules → (5) the deletion was part of the incomplete refactor and no full-suite import check ran before the crash.
- **Fix applied:** restored `_canonical_child_binding_value` and `canonical_child_office_binding_sha256` (plus `hashlib`/`json` imports) in `scripts/court_office_bootstrap.py` verbatim from HEAD. `check_court_runtime` now progresses past import (fails later on a stale help-contract assertion, see §5).

### 4.2 `court_code_required` for legacy creates

- **Observed:** `check_court_runtime_completion` and `reproduce_missing_both.py` crashed with `ValueError: court_code_required` on plain `create_task`.
- **5-Why:** `create_task` called `initial_semantic_binding(...)` without a court code when no `session_id` case-selection is present; the new `semantic_binding_for_revision` requires `court_code`; the refactor only wired the case-backed path.
- **Fix applied:** `_legacy_court_code` + pass through in `create_task` (§3.2).

### 4.3 `invariant_capsule_fields_unknown:charter_sha256,governing_hashes,latest_decree_sha256`

- **Observed:** `check_court_runtime_completion` and `check_court_agent_lifecycle` contain stale invariant-capsule fixtures with digest fields.
- **5-Why:** `normalize_invariant_capsule` tightened to exact template field sets and forbids digest references; fixtures still carried `latest_decree_sha256`/`governing_hashes`/`charter_sha256`.
- **Fix applied:** updated `revision_capsule` in the completion check to the allowed template fields (the *agent_lifecycle* fixture still needs the same edit — see §5).

---

## 5. Remaining Full-Suite Failures (25/39 green, 14 red)

Live result: `evidence/full-suite-summary.json`
Green: `quick_validate`, `release_manifest`, `governance`, `result_semantics`, `open_fastpath`, `read_only`, `unified_cli`, `iku`, `numbering`, `full_record`, `taxonomy`, `lineage_compat`, `recall`, `conflict_scan`, `model_router`, `office_worker`, `agent_config`, `http_static`, `shiguan_concurrency`, `git_federation`, `context_survival`, `outcome_gate`, `projection_closure`, `package_privacy`, `decree/…` (25 total).

Red (14):

| # | Check | Failure | Class |
|---|---|---|---|
| 1 | `completion` | `KeyError: 'charter_sha256'` at `check_assessment_validation_and_deep_copy` (line 425) | stale fixture vs new binding |
| 2 | `semantic_continuity` | `SEMANTIC_RESULT_ENVELOPE: case_plan_not_drafted` then `SEMANTIC_RESUME: _semantic_context() missing task_id` | stale fixtures (plan-backed admission / helper signature) |
| 3 | `runtime` | `PUBLIC_CREATE_HELP_MISSING:sha256(exact UTF-8 charter)` | stale help-contract assertion |
| 4 | `runtime_concurrency` | `COURT_RUNTIME_ERROR standard_create_requires_session_id_authority_behavior` | check create args missing new required fields |
| 5 | `agent_lifecycle` | `invariant_capsule_fields_unknown:charter_sha256,governing_hashes,latest_decree_sha256` | stale capsule fixture |
| 6 | `startup_fastpath` | `semantic_template_roundtrip: case_binding_court_code_required`; `preload_cache_invalidation: 'RolePreload' has no attribute 'profile_sha256'` | contract drift in startup/preload |
| 7 | `hierarchy` | `HIERARCHY_DECISION_MISMATCH ... expected=True:actual=False` (`dispatch_hierarchy_child_profile_required` vs expected scope-reason) | validator contract changed, check fixtures stale |
| 8 | `session_closeout` | `ordinary closeout constructed an archive receipt` — `_default_archive_writer` now calls `append_checkpoint` which builds an archive receipt | **production regression suspicion** (closeout writer no longer lightweight) |
| 9 | `preload_semantics` | `FileNotFoundError: references/manifests/installed-preload-identity.v1.json` | missing manifest / fixture not creating it |
| 10 | `skill_identity` | `SKILL_IDENTITY_DIGEST_MISMATCH` declared `E94D…` vs actual `2A91…` for `SKILL.md` | SKILL.md edited, identity manifest not refreshed |
| 11 | `source_budget` | `generated_runtime_present` (7 files / 968,616 bytes) | stale `__pycache__` artifacts (now cleaned; re-run needed) |
| 12 | `mcp` | `decretum-mcp internal error: RuntimeError: secret-detail` | runtime/MCP-adapter error (needs diagnosis; may be fixture/environment) |
| 13 | `portability` | "SKILL validation examples use portable script paths" + 4 entrypoints missing `sys.dont_write_bytecode` before local imports (`court_case_binding.py`, `court_complexity_budget.py`, `court_native_host_dispatch.py`, `court_semantic_continuity.py`) | real portability violations |
| 14 | `installer_fixture` | `ok:false`; `exact_version_legacy_locator_still_backs_up_and_rolls_back:contract_failed` (INSTALLED result but contract `ok:true` not accepted); declared 37 cases | installer/check contract drift |

### 5.1 5-Why per remaining failure (root-cause chains)

**#1 completion & #2 semantic_continuity (same class):**
- Why red? → check fixtures assert/feed fields the new runtime no longer produces.
- Why? → the new binding uses `case_ref`; fixtures still use `charter_sha256` and ad-hoc (plan-less) create+admit instead of the plan-reviewed dispatchable path.
- Why? → previous thread migrated production `court_runtime` and part of `check_semantic_continuity` but not the deep fixture helpers (`assessment_args`, `checkpoint_receipt`, `bind_assessment_record` assertions, several `_semantic_context()` calls).
- Why? → thread crashed before a full-search/upgrade pass over the check files.
- Why? → no automated contract-diff gate existed between runtime fields and check expectations; the suite was only run at an older green head.

**#3 runtime help contract:**
- Why? → assertion looks for `sha256(exact UTF-8 charter)` in create help; the new create help text changed (court_code/session wording).
- Why? → help text is generated from the new parser; the old check was not updated to the new public contract.
- Resolution: update the expected fragments (or keep the old phrase if the contract still requires it).

**#4 runtime_concurrency:**
- Why? → `standard_create_requires_session_id_authority_behavior`.
- Why? → `create_task` now treats any `session_id`-bearing create as a standard-session case and requires `authority`+`behavior`; the concurrency check's create args omit them.
- Resolution: add `--session-id`/`--authority`/`--behavior` (or use the legacy path without `session_id`).

**#5 agent_lifecycle:**
- Why? → identical stale-capsule class as §4.3; the fixture in `check_court_agent_lifecycle.py` still emits digest fields.
- Resolution: same edit as `revision_capsule` (drop `charter_sha256`, `latest_decree_sha256`, `governing_hashes`).

**#6 startup_fastpath:**
- Why? → `case_binding_court_code_required` (case binding requires task court_code; fixture has none) and `RolePreload.profile_sha256` missing (preload cache record shape changed).
- Why? → refactor moved identity to court_code/case binding and renamed preload fields; startup fixtures and `RolePreload` dataclass were not updated.
- Resolution: align `RolePreload`/preload-cache fields and supply court_code in semantic template fixtures.

**#7 hierarchy:**
- Why? → validator now requires `child_profile` before accepting a hierarchy decision; check fixtures provide owner/scope but not `child_profile`, so denial reason changes.
- Why? → `validate_dispatch_hierarchy` API gained `child_profile`; check cases not regenerated.
- Resolution: regenerate expected reason tuples to `dispatch_hierarchy_child_profile_required` or provide valid `child_profile` in allowed cases.

**#8 session_closeout (production-regression candidate — needs gate-owner decision):**
- Why? → `_default_archive_writer(draft)` now calls `append_checkpoint(args)` which internally calls `build_archive_receipt`.
- Why? → during refactor `append_checkpoint` grew a receipt builder, and the closeout writer was routed through it.
- Why? → the check contract says ordinary session closeout must NOT construct an archive receipt (lightweight writer); this is now violated.
- Resolution (choose one): (a) keep `_default_archive_writer` receipt-free (call a dedicated `archive_checkpoint`-lite path), or (b) deliberate contract change + update check. **Not fixed here.**

**#9 preload_semantics:**
- Why? → `installed-preload-identity.v1.json` not found in the fixture root.
- Why? → `isolated_preload_installation.write_skill(root)` does not emit the pin file; `installed_identity_fixture.write_identity` exists but isn't called.
- Why? → manifest concept was introduced in the refactor; fixture not rewired.
- Resolution: call `installed_identity_fixture.write_identity` inside the preload fixture (or create the manifest in the installer path) and re-run.

**#10 skill_identity:**
- Why? → `SKILL.md` digest mismatch with `references/manifests/skill-identity.v1.json`.
- Why? → previous thread edited `SKILL.md` (M in git status) without regenerating the identity manifest.
- Resolution: regenerate manifest digest from the LF-normalized `SKILL.md` (or restore SKILL.md to the declared digest).

**#11 source_budget:**
- Why? → `generated_runtime_present` because 7 `.pyc` files existed under `scripts`.
- Why? → running check modules as `__main__` before `sys.dont_write_bytecode` guards created bytecode.
- Resolution: **done locally** (removed `__pycache__`); add `PYTHONDONTWRITEBYTECODE=1` or ensure `-B`/dont_write_bytecode consistently; re-run to confirm 0/0.

**#12 mcp:**
- Why? → `decretum-mcp internal error: RuntimeError: secret-detail`.
- Why? → MCP adapter raised at a tool/secret-detail path; needs a deeper trace (assertion/security detail redaction).
- Resolution: run `check_court_mcp_server` with debug, capture full traceback, and fix the raised path or the fixture expectation. Possibly environment/config; not resolved here.

**#13 portability:**
- Why? → 4 Python entrypoints don't disable bytecode before local imports; SKILL validation examples reference non-portable script paths.
- Why? → refactor added/renamed entrypoints without adding `sys.dont_write_bytecode = True`; some SKILL examples use absolute/host paths.
- Resolution: add the guard to the four files and make SKILL examples portable (mechanical).

**#14 installer_fixture:**
- Why? → `exact_version_legacy_locator_still_backs_up_and_rolls_back:contract_failed` although the installer returned `INSTALLED`/rollback OK.
- Why? → the declared contract (37 cases / 31 config cases) no longer matches the installer's new result schema or legacy-locator behavior after the refactor.
- Resolution: regenerate the installer check cases/expectations to the new result schema (and re-baseline skill identity, since it also feeds the installer).

---

## 6. Source-Level Audit Findings (cross-cutting)

1. **The refactor is genuinely half-migrated.** `create_task`/`semantic_binding_for_revision` now produce `court_code`/`case_ref`/`invariant_capsule` but multiple production consumers still read `charter_sha256` / `invariant_capsule_sha256` (`semantic_resume` line ~6258, result binding line ~1842, lifecycle line ~7762). This review partially repaired this by *deriving* those hashes again in `semantic_binding_for_revision`; a deeper audit should decide whether to fully migrate consumers or keep the derived fields as the compatibility projection.
2. **Check fixtures are split-brain.** `check_semantic_continuity.py` is mostly migrated; `check_court_runtime_completion.py`, `check_court_agent_lifecycle.py`, `check_court_runtime.py`, `check_startup_fastpath_contract.py`, `check_court_dispatch_hierarchy.py`, `check_court_session_closeout.py`, `check_court_preload_semantics.py` still carry old fixtures.
3. **Manifest drift:** `references/manifests/skill-identity.v1.json` digest does not match `SKILL.md`; `references/manifests/installed-preload-identity.v1.json` is absent from the tree and from HEAD.
4. **Working-tree hygiene:** `scripts/**/__pycache__` artifacts were present (removed); `git status` shows a large dirty set (≈40 files) that must be triaged before any commit/candidate.
5. **The four T08 gates are now isolated-green**, but the required suite is not; do not accept a release attestation on this tree yet.

---

## 7. File Change Inventory (this review)

Modified (already modified before review; this review's edits are marked in the diff):
- `scripts/court_runtime.py` — consultation-refs case_ref validation, `--case-ref` JSON parse, `_legacy_court_code`, invalidation snapshot field.
- `scripts/court_semantic_continuity.py` — derived `charter_sha256`/`invariant_capsule_sha256` in `semantic_binding_for_revision`.
- `scripts/court_office_bootstrap.py` — restored `canonical_child_office_binding_sha256` + helper + imports.
- `scripts/checks/check_semantic_continuity.py` — T08 + result-envelope + correction tests use plan-reviewed dispatchable case; report `case_ref`; stale case_ref/plan mutation.
- `scripts/checks/check_court_runtime_completion.py` — revision binding court_code, capsule field cleanup, complete_args `case_ref`.
- `docs/reports/beta110-20260905/evidence-summary.json` — `t08` updated + `t08_resume_evidence`.

Created by this review:
- `docs/handoffs/2026-09-06-beta1.1.0-t08-resume-closure.md`
- `D:\project\.staging\dm110-20260905\t08-bingbu\t08-gate-evidence.py`, `t08-gate-status.json`, green marker files.
- This package (`docs/handoff_packages/beta1.1.0-source-review-2026-09-06/`).

---

## 8. Review Checklist for ChatGPT Web Reviewer

1. Confirm the four T08 gates are green via `evidence/t08-gate-status.json` + marker files (and re-run `t08-gate-evidence.py` if desired).
2. Read `evidence/current-working-tree-diff.patch` and verify the T08 fixes match §3.2 (especially the `case_ref`-based consultation validation and producer-evidence requirement).
3. Confirm the 14 remaining suite failures and their 5-Why chains in §5; sanity-check each classification (stale fixture vs production regression). Pay particular attention to:
   - `session_closeout` (#8) — possible production regression in `_default_archive_writer`.
   - `mcp` (#12) — `RuntimeError: secret-detail` needs a real traceback.
   - `skill_identity` (#10) — manifest digest must be regenerated or SKILL.md restored.
4. Verify no release-gate claim is made on this dirty tree; the suite must be 39/39 (or re-baselined with an explicit decision) before candidate/pre-install/publication.
5. Recommend the next single-writer reconciliation workplan: migrate fixture helpers to the new contract (charter_sha256→case_ref/capsule, session_id+authority+behavior creates, child_profile hierarchy fixtures, RolePreload fields, preload manifest), then run the full suite clean.

---

*Prepared for external re-review. Evidence is machine-generated; no release/tag/push was performed.*
