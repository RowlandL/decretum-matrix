# superCC Phase-Cycling Model

This reference governs superCC phase cycling without changing the current
runtime-family rule: routine terminal-visible core panes are 太子 + 三省.
Legacy 监察使 / patrol-inspector is not part of the default runtime shape;
routine health checks use silent script evidence.

## Core Model

superCC is not blind all-office fanout. It is a phase-cycling court workflow:

1. Planning/intake phase:
   - Visible core: 太子 + 中书省 + 门下省 + 尚书省.
   - 三省 return findings as 三省上奏 / dispatch findings.
   - 监察 is absent; routine abnormal-close/429/silence checks use the silent
     supervisor script.

2. Open-decree receive posture:
   - While the decree remains open, 太子、中书省、门下省、尚书省 stay in
     `awake_no_silence` receive/heartbeat posture after 三省 returns.
   - They may enter `idle_receive` only after final `结诏`, an explicit pause, or
     a recorded unresolved-office exception allowed by the newest decree.
   - Standing awake is a receive posture, not permission to execute or redispatch
     without the appropriate office assignment.

3. Execution/ministry phase:
   - 太子 re-wakes 尚书省 as dispatcher.
   - 尚书省 dispatches only selected 六部 required by the approved step plan.
   - 中书省 and 门下省 remain awake for reports/review during 六部 execution but
     do not execute ministry work unless the next approved step assigns them.
   - Request pressure is governed by the 20 model-triggering requests/minute
     budget and explicit total budgets, not by a fixed office-count cap.

## Visible-Window Contract

By default, terminal-visible superCC panes are limited to the routine core:

- 太子 (`S Taizi #0001`)
- 三省 (`AZS Zhongshu #0001`, `AMX Menxia #0001`, `ASS Shangshu #0001`)

六部 and 史馆 are non-visible/silent by default. A missing visible pane for
六部/史馆 is not an error under this contract. A visible 六部/史馆 pane is allowed
only when the newest decree explicitly approves bounded visibility;
otherwise it is runtime drift that must be closed or marked degraded.

## Silent Supervisor Contract

`scripts/supercc_watchdog.py` is the routine 429, abnormal-close, and
abnormal-silence supervisor. It is script evidence, not a visible office:

- Default mode is read-only JSON/text evidence.
- Hidden long-running mode uses `--daemon --quiet --log-jsonl <path>` and must
  record `watchdog_pid_file`, `watchdog_no_visible_window`, and a later
  `--stop-daemon` result unless persistence is explicitly approved.
- Bounded repair requires explicit `--apply`; otherwise use `--no-apply` or
  `--dry-run` to produce planned recovery commands.

Normal 六部/史馆 silence must never display diagnostic labels such as `缺窗`,
`缺身份`, `非显性`, or `心跳滞后` in a visible status column. Those diagnostics
may remain in JSON/JSONL evidence and Shiguan only.

## Non-Visible Ministry Dispatch

When 尚书 dispatches a 六部 task under the default contract, the route is:

`SQUAD_STRUCTURED_TASK_WITH_AUDIT_MIRROR_NON_VISIBLE_MINISTRY`

This means:

1. create a structured `squad task` assigned to the ministry;
2. send a `squad send` mirror carrying the task id when audit mirroring is
   useful or required;
3. preserve `task_queued_non_visible_success` evidence: task id exists, no
   forbidden 六部 pane was opened, and the request budget is preserved;
4. do not use native zellij double-enter for non-visible ministries unless a
   bounded visible pane was explicitly approved.

The silent supervisor may classify failed visible targets and emit bounded
recovery commands. It must not spawn extra long-lived profile sessions by
default and must not retry the same dispatch uid in an unbounded loop.

## Channel Order

For Hermes source dispatch under normal `superCC`:

`SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER -> NATIVE_DOUBLE_ENTER_VISIBLE_RECEIVE_COMMAND -> HERMES_PROFILE_NATIVE_READINESS_SUPPLEMENT`

For non-Hermes source dispatch:

`SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER -> NATIVE_DOUBLE_ENTER_VISIBLE_RECEIVE_COMMAND`

For default non-visible ministry dispatch:

`SQUAD_STRUCTURED_TASK_WITH_AUDIT_MIRROR_NON_VISIBLE_MINISTRY`

`squad` is a structured task and audit mirror, not the primary wake channel for
visible panes. For default non-visible ministries it is the semantic task queue
channel; the silent supervisor may verify that no forbidden visible pane was
opened through JSON/JSONL evidence without creating a visible monitor.
