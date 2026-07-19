# Decretum Matrix Unified CLI and Fast Court Open Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task, while preserving the Decretum Matrix court hierarchy and the A02 single-writer rules.

**Goal:** 在 `release/beta0.5.13` 建立一个完整、可发现、可审计的 `decretum-matrix` 统一 CLI，并用单进程开朝快速路径消除当前串行脚本编排、尚书首次派遣缺包以及门下/太子复核署名不实的问题。

**Architecture:** 保留现有 `court_runtime.py` 和各领域模块作为唯一行为与状态权威，在其前方增加惰性命令注册表和统一回执协议。开朝快速路径只编排既有 runtime、semantic、admission 与 preload 核心，不新建 daemon、缓存权威、ledger 或状态机；低频维护、检查与发布命令可以继续隔离运行，但必须由统一命令面发现和调用。

**Tech Stack:** Python 3 标准库、现有 `court_runtime.py`/`court_cli.py`、JSON manifest/receipt、现有 checker fixtures、Node.js npm release harness、PowerShell/POSIX shell compatibility。

---

## 1. Authority and execution binding

- Task book: `docs/plans/2026-07-14-ccr-r2-shir-a02-execution-book.md`
- Branch: `release/beta0.5.13`
- Designated execution thread: `019f764c-4000-73b0-817c-f59e81d454eb`
- Accepted baseline: `release/beta0.5.12@e3fcecf4f8869a97bec1da465134f2ce7bd14f46`
- Current carrier at plan creation: `584d34ef9877db088241c3818aaec5b2b829a508`
- Performance and failure baseline conversation: `019f75cb-d31a-7e40-bb09-2af17c518955` (direct conversation evidence; do not substitute Shiguan summaries).
- Governing skill: `C:\Users\32893\.agents\skills\decretum-matrix\SKILL.md`
- `pending_body_access=NO`; no pending/private body read, scan, hash, move, delete, or status mutation.
- No new worktree, main/PR/force, push, tag, npm publication, or beta0.5.13 release without later explicit authorization.
- The installation command remains: `npm install @rowlandl/decretum-matrix@beta --registry=https://npm.pkg.github.com`.
- `OFFICE_PACK_Q1_Q8` remains deferred to `QUEUED_POST_A02_HANDOFF`.

## 2. Scope and non-goals

### In scope

1. Register every supported executable script in one versioned command-surface manifest.
2. Expose one public command root, `decretum-matrix`, with stable domain groups and JSON/text receipts.
3. Keep legacy script entrypoints as compatibility wrappers until parity is proven.
4. Add `court open --fast` as a single-process orchestration path.
5. Make the first Shangshu dispatch packet complete, validated, idempotent, and all-or-nothing before host spawn.
6. Require a real Menxia report for `MenxiaReview`; otherwise label the root result `TaiziSynthesis` or `TaiziReply`.
7. Reuse the Phase 5.1 updater mutation core from the unified `install` command group.
8. Measure cold/warm p50 and p95 without counting model or real child-agent startup as Python speedup.

### Out of scope

- Combining all Python modules into one file.
- Importing every checker at CLI startup.
- Creating a second runtime, ledger, semantic authority, cache, service, or daemon.
- Rewriting every low-frequency script solely for naming consistency.
- Removing legacy entrypoints before manifest coverage and parity pass.
- Treating a CLI flag as authority elevation.
- Implementing host-level batch `spawn_agent`; the CLI prepares a complete wave but cannot invent host APIs.
- Reading pending or private bodies for inventory or tests.

## 3. Canonical command surface

```text
decretum-matrix court open --fast
decretum-matrix court <runtime-command>
decretum-matrix office <lifecycle-command>
decretum-matrix shiguan <command>
decretum-matrix supercc <command>
decretum-matrix install update|migrate
decretum-matrix release <command>
decretum-matrix check <command|all>
```

The source-tree equivalent remains:

```powershell
python -B scripts/court_cli.py <group> <command> --format json
```

All commands use exit code `0` for pass/success, `2` for a validated blocked/failed gate, and `3` for invalid invocation or malformed input. Structured output includes `schema`, `ok`, `command`, `status`, `receipt_id` when state changes, `problems`, and `evidence`.

## 4. File map

| Responsibility | Files |
| --- | --- |
| Versioned inventory and public/compatibility metadata | Create `references/manifests/cli-command-surface.v1.json` |
| Lazy command selection and stable result envelope | Create `scripts/court_cli_registry.py`; modify `scripts/court_cli.py` |
| Existing runtime handlers and state authority | Modify only bounded handlers in `scripts/court_runtime.py` |
| Single-process open orchestration | Create `scripts/court_open_fastpath.py` |
| Unified CLI contract tests | Create `scripts/check_unified_cli.py` |
| Fast open and packet tests | Create `scripts/check_court_open_fastpath.py`; modify `scripts/check_court_dispatch_policy.py` |
| Review actor/label semantics | Modify `scripts/court_result_semantics.py`, `scripts/check_court_result_semantics.py`, and `references/fixtures/response-draft-families.json` |
| npm command projection | Modify `scripts/build_npm_package.mjs`, `scripts/check_npm_package.mjs`, and the package template inputs they already own |
| Release/source gates | Modify `references/manifests/release-gates.v1.json`, `scripts/check_release_manifest.py`, and `scripts/quick_validate.py` only after focused gates pass |
| User and governing docs | Modify `SKILL.md`, `README.md`, `references/install.md`, and the directly affected command references |

## 5. Task sequence

### Task 1: Freeze the executable command inventory

- [ ] Generate `cli-command-surface.v1.json` from tracked Python/Node/shell entrypoints without reading ignored runtime or pending trees.
- [ ] Record for each entry `id`, `domain`, `legacy_path`, `handler`, `public`, `side_effect`, `authority_source`, `receipt_schema`, and `compatibility_state`.
- [ ] Add a failing inventory test that rejects an executable entrypoint absent from the manifest and rejects duplicate public command tuples.
- [ ] Run `python -B scripts/check_unified_cli.py --inventory-only --json`; expected pre-implementation result is `CLI_ENTRYPOINT_COVERAGE=FAIL` with an exact missing list.
- [ ] Fill only real tracked entrypoints, rerun, and require `CLI_ENTRYPOINT_COVERAGE=PASS`.

### Task 2: Add the lazy command registry

- [ ] Add a registry record with `group`, `command`, `loader`, `side_effect`, and `authority_requirement`; loader imports only the selected handler module.
- [ ] Keep existing `court_runtime.main()` behavior reachable through compatibility aliases.
- [ ] Add tests that inspect `sys.modules` and prove `--help` does not import Shiguan, superCC, updater, package, or checker implementations.
- [ ] Run `python -B scripts/check_unified_cli.py --registry --json`; require `CLI_LAZY_LOAD=PASS`, stable exit codes, and deterministic help ordering.

### Task 3: Project existing domains into the unified CLI

- [ ] Register `court`, `office`, `shiguan`, `supercc`, `install`, `release`, and `check` groups.
- [ ] Make legacy scripts invoke the same handler or an isolated subprocess adapter declared in the manifest; forbid hidden script-to-script Python chains on the court hot path.
- [ ] Compare normalized JSON from every public legacy/new command pair on synthetic fixtures.
- [ ] Run `python -B scripts/check_unified_cli.py --parity --json`; require `CLI_LEGACY_PARITY=PASS` and no undeclared adapter.

### Task 4: Implement `court open --fast`

- [ ] Build one immutable request from current user authority, task id, charter/semantic receipt, current plan cursor, worktree identity, live capacity, and requested offices.
- [ ] Load skill/profile/dossier hashes and current runtime state once; run only independent read-only probes concurrently inside the same interpreter.
- [ ] Reuse/create the task, verify semantic continuity, prepare dispatch packets, validate admission, and emit one `court.open.fast.v1` receipt.
- [ ] Return `FAST_PATH_MISS:<reason>` before mutation when the task is ambiguous, semantic sources drift, capacity is unknown, a write set overlaps, or hierarchy data is incomplete.
- [ ] Add a process-spawn guard that fails if the deterministic open segment starts another Python interpreter.
- [ ] Run `python -B scripts/check_court_open_fastpath.py --json`; require `FAST_OPEN_SINGLE_PROCESS=PASS` and zero partial mutations across every miss fixture.

### Task 5: Make Shangshu first dispatch complete

- [ ] Prepare all six ministry packets before starting Shangshu execution: target role, `direct_superior=shangshu`, task/charter/semantic epoch, operation id, budget/lease, work/read/write scope, profile/dossier/skill hashes, and evidence contract.
- [ ] Validate the whole packet set atomically with the existing hierarchy and admission contracts; one invalid ministry blocks all dispatch side effects.
- [ ] Bind an idempotent operation id so retry returns the prior decision instead of creating a second wave.
- [ ] Add fixtures for missing semantic epoch, missing packet, wrong superior, missing budget, preload mismatch, partial capacity, and exact retry.
- [ ] Run `python -B scripts/check_court_dispatch_policy.py` and `python -B scripts/check_court_open_fastpath.py --shangshu --json`; require `SHANGSHU_FIRST_DISPATCH=PASS` and `SIX_MINISTRY_DIRECT_SUPERIOR=PASS`.

### Task 6: Enforce review attribution

- [ ] Require an accepted report with `role=menxia` and a current evidence binding before the runtime records `MenxiaReview`.
- [ ] Render root-only aggregation as `TaiziSynthesis` and user-facing final delivery as `TaiziReply`; never rename either to Menxia review.
- [ ] Add negative fixtures for Taizi impersonation, stale Menxia evidence, pre-ministry review, and missing final follow-up.
- [ ] Run `python -B scripts/check_court_result_semantics.py`; require `MENXIA_REVIEW_ATTRIBUTION=PASS` and `TAIZI_LABEL_SEMANTICS=PASS`.

### Task 7: Connect updater and npm without a second core

- [ ] Register `install update|migrate` as thin calls to the Phase 5.1 mutation core and its plan/receipt schema.
- [ ] Add `decretum-matrix` as the npm `bin` command while keeping install side effects explicit; no dangerous or implicit `postinstall`.
- [ ] Compare source CLI and local `.tgz` receipts on clean-home Windows/macOS/Linux fixtures.
- [ ] Run `node scripts/check_npm_package.mjs --self-test` and `python -B scripts/check_release_manifest.py --npm-harness-self-test --json`; require `UPDATER_SINGLE_CORE=PASS` and no publication.

### Task 8: Benchmark, document, and enter release gates

- [ ] Capture at least ten cold and ten warm runs for the legacy flow and `court open --fast`; record Python process count, deterministic segment duration, p50, and p95.
- [ ] Require one Python interpreter and at least 30% deterministic p50 improvement before making `--fast` default; report p95 independently.
- [ ] Update governing/user docs only for commands proven by tests, preserving the exact GitHub Packages install command.
- [ ] Add the focused CLI/fast-open gates to the existing release-gate manifest after they pass independently.
- [ ] Run `python -B scripts/quick_validate.py .`, `python -B scripts/check_release_gate.py --self-test --json`, `git diff --check`, and index/no-pyc checks.
- [ ] Follow the A02 final-stage commit rule: one bounded local commit only when the current acceptance stage authorizes it; never create per-task empty commits.

## 6. Acceptance gates

```text
CLI_ENTRYPOINT_COVERAGE=PASS
CLI_LAZY_LOAD=PASS
CLI_LEGACY_PARITY=PASS
FAST_OPEN_SINGLE_PROCESS=PASS
SHANGSHU_FIRST_DISPATCH=PASS
SIX_MINISTRY_DIRECT_SUPERIOR=PASS
MENXIA_REVIEW_ATTRIBUTION=PASS
TAIZI_LABEL_SEMANTICS=PASS
UPDATER_SINGLE_CORE=PASS
CLI_PERFORMANCE_GATE=PASS
INDEX_EMPTY=PASS
PYC_COUNT=0
```

Phase 5.2 is complete only when every gate above passes, the A02 execution book receives append-only result evidence at its then-current EOF, and Phase 9/10 can consume the same verified receipts without rebuilding the feature or widening pending access.
