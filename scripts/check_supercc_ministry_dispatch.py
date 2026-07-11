"""Regression-test the superCC six-ministry dispatch boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def legacy_term(*parts: str) -> str:
    return "_".join(parts)


LEGACY_FIELD_TERMS = [
    legacy_term("patrol", "status", "table", "markdown"),
    legacy_term("patrol", "status", "table", "rendered"),
    legacy_term("gum", "status", "render", "policy"),
    legacy_term("patrol", "agent", "duty", "dispatch"),
    legacy_term("jiancha", "bidirectional", "recovery"),
]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require_terms(path: str, terms: list[str]) -> None:
    text = read(path)
    missing = [term for term in terms if term not in text]
    if missing:
        raise AssertionError(f"{path} missing terms: {missing}")


def reject_terms(path: str, terms: list[str]) -> None:
    text = read(path)
    found = [term for term in terms if term in text]
    if found:
        raise AssertionError(f"{path} still has forbidden terms: {found}")


def check_source_rules() -> None:
    shared_dispatch_terms = [
        "taizi_no_silence",
        "three_departments_no_silence",
        "no_silence_roles",
        "monitor_no_silence_roles",
        "taizi_stale_explanation",
        "closeout_silence_policy",
        "idle_receive",
        "noncurrent_inactive_pane_cleanup",
        "direct_superior_source",
        "SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER",
        "SUPERCC_SQUAD_RECEIVE_COMMAND",
        "post_dispatch_physical_enter_delay_seconds",
        "office_dossier_path",
        "office_dossier_hash",
        "AGENTS.md",
        "light_bootstrap_policy",
        "six_ministry_step_plan_policy",
        "turn_start_open_decree",
        "turn_start_native_wake_policy",
        "native_turn_start_wake",
        "silent_supervisor",
        "supercc_watchdog",
        "watchdog_daemon_stop",
        "cli_probe",
    ]
    require_terms(
        "SKILL.md",
        [
            "Core Metadata Index",
            "Reference Index",
            "Office abstraction",
            "Token Three-Level Optimization",
            "Healthy offices do their own duties",
            "Request pressure is rate-bounded",
            "--turn-start",
            "--closeout-silence",
            "court-supercc-runtime-selection.md",
            "court-state-runtime-agents.md",
            "court-offices-dispatch.md",
            "court-closeout-validation.md",
            "court-host-platform-pitfalls.md",
            *shared_dispatch_terms,
        ],
    )
    require_terms(
        "references/court-state-runtime-agents.md",
        [
            "The main/visible pane remains 太子",
            "not a 六部 creation or menu surface",
            "dispatcher=shangshu",
            "must not add 六部 creation controls to the 太子 main pane/menu",
            "Routine superCC recovery is hierarchical plus silent script supervision",
            "supervision_channel",
            *shared_dispatch_terms,
        ],
    )
    require_terms(
        "references/court-offices-dispatch.md",
        [
            "六部 scale-out is created by 尚书省差遣",
            "turn_start_health",
            "ministry_silent_until_dispatch",
            "calling_office=shangshu",
            "direct_superior=shangshu",
            "ENTER_DISPATCH",
            "native_enter_dispatch",
            "post_dispatch_physical_enter_delay_seconds",
            "squad_evidence",
            "profile_hash",
            "Default `superCC` supervision channels",
            "六部 -> 尚书省",
            "supervision_channel",
            "supervision_evidence",
            *shared_dispatch_terms,
        ],
    )
    require_terms(
        "references/court-closeout-validation.md",
        [
            "redispatch_actions",
            "office_profile_loaded",
            "dispatch_delivery_channel",
            "native_enter_dispatch",
            "post_dispatch_physical_enter_delay_seconds",
            "squad_evidence",
            "supercc_model_session_count",
            "supercc_session_cap",
            "supervision_channel",
            "supervision_evidence",
            "legacy_patrol_visible_pane",
            *shared_dispatch_terms,
        ],
    )
    for path in (
        "SKILL.md",
        "references/court-closeout-validation.md",
        "references/court-state-runtime-agents.md",
        "references/court-offices-dispatch.md",
    ):
        reject_terms(
            path,
            LEGACY_FIELD_TERMS,
        )


def check_supercc_launcher_shape() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import ensure_supercc_court  # noqa: PLC0415
    import supercc_watchdog  # noqa: PLC0415

    expected_standing = {"zhongshu", "menxia", "shangshu"}
    inspection_roles = {"patrol-inspector"}
    ministry_roles = {"hubu", "libu", "bingbu", "xingbu", "gongbu", "libu-hr"}
    special_roles = {"shiguan"}
    expected_offices = expected_standing | inspection_roles | ministry_roles | special_roles
    if set(ensure_supercc_court.OFFICES) != expected_offices:
        raise AssertionError(f"superCC launcher OFFICES drifted: {ensure_supercc_court.OFFICES!r}")
    if set(ensure_supercc_court.THREE_OFFICES) != expected_standing:
        raise AssertionError(f"THREE_OFFICES drifted: {ensure_supercc_court.THREE_OFFICES!r}")
    if set(ensure_supercc_court.MINISTRY_OFFICES) != ministry_roles:
        raise AssertionError(f"MINISTRY_OFFICES drifted: {ensure_supercc_court.MINISTRY_OFFICES!r}")
    if set(ensure_supercc_court.INSPECTION_OFFICES) != inspection_roles:
        raise AssertionError(f"INSPECTION_OFFICES drifted: {ensure_supercc_court.INSPECTION_OFFICES!r}")
    if set(ensure_supercc_court.SUPERCC_VISIBLE_CORE_OFFICES) != expected_standing:
        raise AssertionError(f"SUPERCC_VISIBLE_CORE_OFFICES drifted: {ensure_supercc_court.SUPERCC_VISIBLE_CORE_OFFICES!r}")
    if "patrol-inspector" in ensure_supercc_court.ALL_VISIBLE_OFFICES:
        raise AssertionError("legacy inspection identity must not be in routine visible offices")
    if set(ensure_supercc_court.SPECIAL_OFFICES) != special_roles:
        raise AssertionError(f"SPECIAL_OFFICES drifted: {ensure_supercc_court.SPECIAL_OFFICES!r}")
    if set(ensure_supercc_court.NON_VISIBLE_DEFAULT_SILENT_OFFICES) != ministry_roles | special_roles:
        raise AssertionError(f"NON_VISIBLE_DEFAULT_SILENT_OFFICES drifted: {ensure_supercc_court.NON_VISIBLE_DEFAULT_SILENT_OFFICES!r}")
    if tuple(ensure_supercc_court.CORE_IDS) != ("taizi", *ensure_supercc_court.ALL_VISIBLE_OFFICES, *ensure_supercc_court.INSPECTION_OFFICES):
        raise AssertionError(f"CORE_IDS drifted: {ensure_supercc_court.CORE_IDS!r}")
    if tuple(ensure_supercc_court.STATUS_OFFICES) != ("taizi", *ensure_supercc_court.ALL_VISIBLE_OFFICES):
        raise AssertionError(f"STATUS_OFFICES drifted: {ensure_supercc_court.STATUS_OFFICES!r}")
    if set(ensure_supercc_court.CLOSEOUT_SILENCE_ROLES) != set(ensure_supercc_court.STATUS_OFFICES):
        raise AssertionError(f"CLOSEOUT_SILENCE_ROLES drifted: {ensure_supercc_court.CLOSEOUT_SILENCE_ROLES!r}")
    if tuple(ensure_supercc_court.NO_SILENCE_ROLES) != ("taizi", *ensure_supercc_court.THREE_OFFICES):
        raise AssertionError(f"NO_SILENCE_ROLES drifted: {ensure_supercc_court.NO_SILENCE_ROLES!r}")
    if ensure_supercc_court.inspector_enabled(argparse.Namespace(enable_inspector=True, skip_inspector=False)):
        raise AssertionError("legacy inspector must stay disabled")
    if ensure_supercc_court.SUPERCC_WATCHDOG_SCRIPT != "supercc_watchdog.py":
        raise AssertionError("silent supervisor script drifted")

    if ensure_supercc_court.bounded_office_show_delay(-1) != 0.0:
        raise AssertionError("negative office show delay must clamp to zero")
    if ensure_supercc_court.bounded_office_show_delay(1) != 1.0:
        raise AssertionError("one-second office show delay must remain one second")
    if ensure_supercc_court.bounded_office_show_delay(9) != 5.0:
        raise AssertionError("office show delay must cap at five seconds")
    if ensure_supercc_court.office_start_delay(index=0, show_delay=1.0) != 0.0:
        raise AssertionError("the first visible office must have no artificial cooldown")
    if ensure_supercc_court.office_start_delay(index=1, show_delay=9.0) != 5.0:
        raise AssertionError("adjacent visible office start delay must cap at five seconds")
    if ensure_supercc_court.ordinary_spawn_delay_seconds() != 0.0:
        raise AssertionError("ordinary spawned subagents must have no presentation delay")
    alias_resolution = ensure_supercc_court.office_show_delay_resolution(
        argparse.Namespace(
            office_show_delay=None,
            codex_start_stagger=9.0,
            launch_delay=None,
            codex_start_jitter=0.0,
            codex_start_cooldown=None,
            codex_batch_gap=None,
        )
    )
    if alias_resolution["effective_interval_seconds"] != 5.0:
        raise AssertionError("deprecated stagger alias was not capped to five seconds")
    if not any("capped_to=5" in warning for warning in alias_resolution["warnings"]):
        raise AssertionError("deprecated stagger cap did not emit warning evidence")
    if ensure_supercc_court.provider_retry_backoff_seconds(5, retry_after_seconds=90) != 90.0:
        raise AssertionError("provider Retry-After must remain independent and may exceed show-delay cap")
    provider_queue = ensure_supercc_court.provider_launch_queue_plan(
        argparse.Namespace(
            request_rate_limit_per_minute=20,
            office_client="codex",
            office_client_map_resolved={},
            codex_retry_attempts=1,
        ),
        ("zhongshu", "menxia", "shangshu", "hubu", "libu", "bingbu"),
    )
    if provider_queue[4]["state"] != "ready" or provider_queue[5]["state"] != "queued_rate_limit":
        raise AssertionError(f"provider request window queue drifted: {provider_queue}")
    if provider_queue[5]["provider_queue_offset_seconds"] != 60.0:
        raise AssertionError("sixth four-unit Codex start must enter the next provider window")

    launcher_text = (SCRIPTS / "ensure_supercc_court.py").read_text(encoding="utf-8")
    for term in (
        "--launch-offices",
        "--launch-visible-core",
        "--turn-start",
        "--closeout-silence",
        "--super-entry",
        "--enter-dispatch",
        "codex-start-stagger",
        "duplicate_visible_panes",
        "native_enter_dispatch",
        "SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER",
        "SUPERCC_SQUAD_RECEIVE_COMMAND",
        "post_dispatch_physical_enter_delay_seconds",
        "PHYSICAL_ENTER_BYTE",
        "squad_evidence",
        "profile_hash",
        "SUPERCC_REQUEST_RATE_LIMIT_PER_MINUTE",
        "SUPERCC_REQUEST_LIMIT_POLICY",
        "SUPERCC_OFFICE_SHOW_DELAY_DEFAULT_SECONDS",
        "SUPERCC_OFFICE_SHOW_DELAY_MAX_SECONDS",
        "SUPERCC_CODEX_RETRY_BACKOFF_DEFAULT_SECONDS",
        "bounded_office_show_delay",
        "office_start_delay",
        "ordinary_spawn_delay_seconds",
        "queued_rate_limit",
        "--office-show-delay",
        "SUPERCC_LIGHT_BOOTSTRAP_POLICY",
        "SUPERCC_VISIBLE_LAYOUT_POLICY",
        "SUPERCC_DOSSIER_FILE_NAME",
        "--write-agent-dossiers",
        "office_dossier_path",
        "request-total-limit",
        "supercc_watchdog.py",
        "cli_probe",
        "NO_SILENCE_ROLES",
        "RATE_LIMIT_WAKE_HIERARCHY",
        "CLOSEOUT_SILENCE_POLICY",
        "STATUS_OFFICES",
        "NON_VISIBLE_DEFAULT_SILENT_OFFICES",
        "CLOSEOUT_SILENCE_ROLES",
        "noncurrent_inactive_pane_cleanup",
        "direct_superior_source",
        "turn_start_open_decree",
        "TURN_START_NATIVE_WAKE_POLICY",
        "native_turn_start_wake",
        "office_uniqueness_gate",
        "task_evidence",
        "allow-squad-only-fallback",
    ):
        if term not in launcher_text:
            raise AssertionError(f"launcher missing {term!r}")
    for forbidden in (
        "SUPERCC_CODEX_START_COOLDOWN_SECONDS = 60.0",
        "SUPERCC_CODEX_START_STAGGER_FLOOR_SECONDS = 60.0",
        "SUPERCC_CODEX_BATCH_GAP_SECONDS = 60.0",
        "SUPERCC_CODEX_RETRY_BACKOFF_FLOOR_SECONDS = 300.0",
        "Enforced minimum is 60s",
        "Enforced minimum is 300s",
    ):
        if forbidden in launcher_text:
            raise AssertionError(f"launcher still contains artificial delay floor {forbidden!r}")
    if "return launch_offices(args, THREE_OFFICES)" not in launcher_text:
        raise AssertionError("launch_three must route only through THREE_OFFICES")
    if "return launch_offices(args, SUPERCC_VISIBLE_CORE_OFFICES)" not in launcher_text:
        raise AssertionError("launch_visible_core must route through SUPERCC_VISIBLE_CORE_OFFICES")

    prompt = ensure_supercc_court.office_prompt("shangshu", "shangshu", ROOT, "TEST")
    for term in (
        "六部/workshop creation is only a 尚书省差遣",
        "direct_superior=尚书省",
        "never refresh or attach 六部 creation to the Taizi/main pane/menu",
        "Fast path",
        "task_workspace_env=SUPERCC_TASK_WORKSPACE",
        "office_runtime_cwd=role_dossier_directory",
        "local superCC squad wrapper",
        "ack/execute/complete",
        "Mode-neutral office preload manifest",
        "dossier_path",
        "light_bootstrap_policy",
        "layout_policy",
    ):
        if term not in prompt:
            raise AssertionError(f"standing office prompt missing {term!r}")
    ministry_prompt = ensure_supercc_court.office_prompt("hubu", "hubu", ROOT, "TEST")
    for term in ("temporary 六部 pane under 尚书省", "release or idle after 结诏", "Default state: SILENT", "profile_hash", "office_profile_loaded", "AGENTS.md"):
        if term not in ministry_prompt:
            raise AssertionError(f"ministry prompt missing {term!r}")
    dossier_text = ensure_supercc_court.office_dossier_text("hubu")
    for term in ("Fast Dispatch Protocol", "non-blocking inbox check", "task complete", "same wrapper", "Reply only upward", "poll in a loop"):
        if term not in dossier_text:
            raise AssertionError(f"office dossier missing fast dispatch term {term!r}")

    args = argparse.Namespace(
        office_client="futureagent",
        office_client_command=None,
        office_client_arg=[],
        office_client_args=None,
        office_client_prompt_mode="argument",
        office_client_map=[],
        office_client_command_map=[],
        office_client_args_map=[],
        office_client_prompt_mode_map=[],
    )
    ensure_supercc_court.resolve_office_client_args(args)
    ensure_supercc_court.normalize_office_client_maps(args)
    if args.office_client != "cli" or args.office_client_command != "futureagent":
        raise AssertionError(f"unknown CLI did not normalize to probed generic cli: {args}")

    watchdog_args = argparse.Namespace(
        workspace=str(ROOT),
        roles="visible-core",
        zellij_session=None,
        apply=False,
        no_apply=True,
        dry_run=True,
        force=False,
        max_actions=1,
        max_iterations=1,
        interval=1.0,
        log_jsonl=str(ROOT / "references" / "court-runtime" / "test-watchdog.jsonl"),
    )
    daemon_command = supercc_watchdog.hidden_daemon_command(watchdog_args)
    daemon_text = json.dumps(daemon_command, ensure_ascii=False)
    for term in ("supercc_watchdog.py", "--watch", "--quiet", "--log-jsonl"):
        if term not in daemon_text:
            raise AssertionError(f"silent supervisor daemon command missing {term!r}: {daemon_command}")


def check_dispatch_evidence() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import ensure_supercc_court  # noqa: PLC0415

    def fake_check(*, duplicate: bool = False, visible: bool = True) -> dict[str, object]:
        agents = [
            {
                "id": "gongbu",
                "role": "gongbu",
                "status": "active",
                "supports_task_commands": True,
                "supports_json_receive": True,
            }
        ]
        if duplicate:
            agents.append(
                {
                    "id": "gongbu-2",
                    "role": "gongbu",
                    "status": "active",
                    "supports_task_commands": True,
                    "supports_json_receive": True,
                }
            )
        panes = [
            {"pane_id": "terminal_9", "type": "terminal", "title": ensure_supercc_court.OFFICES["gongbu"]["title"]}
        ] if visible else []
        return {
            "supercc_env_gate": "PASSED",
            "visible_display_gate": "PASSED",
            "display_transport_gate": "PASSED",
            "office_client_gate": "PASSED",
            "zellij": {
                "env": {"ZELLIJ_SESSION_NAME": "test-session", "ZELLIJ_PANE_ID": "0"},
                "panes_list": panes,
            },
            "squad": {"agents_json": agents},
        }

    original_supercc_check = ensure_supercc_court.supercc_check
    original_create_task = ensure_supercc_court.create_squad_task_assignment
    try:
        ensure_supercc_court.supercc_check = lambda _workspace, *_, **__: fake_check()  # type: ignore[assignment]
        dispatch_payload = ensure_supercc_court.enter_dispatch(
            argparse.Namespace(
                workspace=str(ROOT),
                role="gongbu",
                message="probe",
                dispatch_uid="TEST-DISPATCH",
                calling_office="shangshu",
                dry_run=True,
            )
        )
        if not dispatch_payload.get("ok"):
            raise AssertionError(f"dry-run dispatch should pass: {dispatch_payload}")
        if dispatch_payload.get("calling_office") != "shangshu":
            raise AssertionError("ministry dispatch must preserve shangshu caller")
        direct_source = str(dispatch_payload.get("direct_superior_source") or "")
        if not direct_source.startswith("standing_profile:") or not direct_source.endswith("gongbu.toml"):
            raise AssertionError(f"direct superior source drifted: {dispatch_payload}")
        if dispatch_payload.get("post_dispatch_physical_enter_delay_seconds") != 1.0:
            raise AssertionError("dispatch must keep delayed second Enter evidence")
        native = dispatch_payload.get("native_enter_dispatch")
        if not isinstance(native, dict) or str(native.get("physical_enter_byte")) != "13":
            raise AssertionError(f"native dispatch physical Enter drifted: {native}")
        if native.get("squad_delivery_order") != "SQUAD_TASK_AND_SEND_BEFORE_NATIVE_ENTER":
            raise AssertionError(f"dispatch must queue squad before native Enter: {dispatch_payload}")
        if native.get("native_enter_payload_kind") != "SUPERCC_SQUAD_RECEIVE_COMMAND":
            raise AssertionError(f"native dispatch must enter the receive wrapper command: {native}")
        command_text = " ".join(str(part) for part in (native.get("commands") or [[]])[0])
        if ("supercc-squad" not in command_text and "supercc_squad.py" not in command_text) or "receive" not in command_text:
            raise AssertionError(f"native dispatch command drifted: {native}")
        task_text = json.dumps(dispatch_payload.get("task_evidence") or {}, ensure_ascii=False)
        if "TEST-DISPATCH" not in task_text:
            raise AssertionError(f"dispatch task evidence missing uid: {dispatch_payload}")

        ensure_supercc_court.supercc_check = lambda _workspace, *_, **__: fake_check(visible=False)  # type: ignore[assignment]
        non_visible = ensure_supercc_court.enter_dispatch(
            argparse.Namespace(
                workspace=str(ROOT),
                role="gongbu",
                message="probe",
                dispatch_uid="TEST-DISPATCH-NONVISIBLE",
                calling_office="shangshu",
                dry_run=True,
            )
        )
        if not non_visible.get("ok"):
            raise AssertionError(f"default non-visible ministry dispatch should pass through squad task evidence: {non_visible}")
        if non_visible.get("dispatch_delivery_channel") != ensure_supercc_court.NON_VISIBLE_MINISTRY_DISPATCH_CHANNEL:
            raise AssertionError(f"default non-visible ministry channel drifted: {non_visible}")
        native = non_visible.get("native_enter_dispatch")
        if not isinstance(native, dict) or native.get("ok") is not False or native.get("skipped") is not True:
            raise AssertionError(f"non-visible ministry must not report native Enter success: {native}")
        if native.get("commands") != []:
            raise AssertionError(f"non-visible ministry must not plan native Enter commands: {native}")
        if non_visible.get("native_enter_payload_kind") is not None:
            raise AssertionError(f"non-visible ministry must not report native payload kind: {non_visible}")
        squad_command = (non_visible.get("squad_evidence") or {}).get("command", [])
        if "--task-id" not in squad_command:
            raise AssertionError(f"non-visible ministry mirror must carry task id: {non_visible}")
        if non_visible.get("dispatch_route_policy_phase1") != [ensure_supercc_court.NON_VISIBLE_MINISTRY_DISPATCH_CHANNEL]:
            raise AssertionError(f"non-visible ministry route policy drifted: {non_visible}")

        ensure_supercc_court.supercc_check = lambda _workspace, *_, **__: fake_check(duplicate=True)  # type: ignore[assignment]
        blocked = ensure_supercc_court.enter_dispatch(
            argparse.Namespace(
                workspace=str(ROOT),
                role="gongbu",
                message="probe",
                dispatch_uid="TEST-DISPATCH-DUP",
                calling_office="shangshu",
                dry_run=True,
            )
        )
        if blocked.get("ok"):
            raise AssertionError("duplicate office identity must block dispatch")
        uniqueness = blocked.get("office_uniqueness_gate")
        if not isinstance(uniqueness, dict) or uniqueness.get("ok") is not False:
            raise AssertionError(f"duplicate office must fail uniqueness gate: {blocked}")
        if blocked.get("dispatch_delivery_channel") != "FAILED_OFFICE_UNIQUENESS_GATE":
            raise AssertionError(f"duplicate office must block dispatch channel: {blocked}")

        ensure_supercc_court.supercc_check = lambda _workspace, *_, **__: fake_check()  # type: ignore[assignment]
        ensure_supercc_court.create_squad_task_assignment = lambda *_, **__: {  # type: ignore[assignment]
            "ok": True,
            "dry_run": True,
            "task_id": None,
            "task_id_parse_ok": False,
            "policy": "structured_task_required_for_office_execution",
        }
        parse_failed = ensure_supercc_court.enter_dispatch(
            argparse.Namespace(
                workspace=str(ROOT),
                role="gongbu",
                message="probe",
                dispatch_uid="TEST-DISPATCH-NO-TASK-ID",
                calling_office="shangshu",
                dry_run=True,
            )
        )
        if parse_failed.get("ok"):
            raise AssertionError(f"missing task id must block dispatch success: {parse_failed}")
        native = parse_failed.get("native_enter_dispatch")
        if not isinstance(native, dict) or native.get("reason") != "squad_delivery_failed_before_native_enter":
            raise AssertionError(f"missing task id must stop before native Enter: {parse_failed}")
        squad_reason = (parse_failed.get("squad_evidence") or {}).get("reason")
        if squad_reason != "task_id_parse_failed_before_squad_mirror":
            raise AssertionError(f"missing task id must block squad mirror: {parse_failed}")
    finally:
        ensure_supercc_court.supercc_check = original_supercc_check  # type: ignore[assignment]
        ensure_supercc_court.create_squad_task_assignment = original_create_task  # type: ignore[assignment]


def main() -> int:
    check_source_rules()
    check_supercc_launcher_shape()
    check_dispatch_evidence()
    print("SUPERCC_MINISTRY_DISPATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
