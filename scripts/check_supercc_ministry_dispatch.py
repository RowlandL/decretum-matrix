"""Regression-test the superCC six-ministry dispatch boundary."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OFFICE_STATE_FIXTURES: dict[str, dict[str, object]] = {}
RUNTIME_TASK_FIXTURES: dict[str, dict[str, object]] = {}


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
    non_visible_special_roles = {"shiguan-hermes", "zaochao"}
    expected_offices = expected_standing | inspection_roles | ministry_roles | special_roles | non_visible_special_roles
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
    if set(ensure_supercc_court.SPECIAL_LIFECYCLE_OFFICES) != special_roles | inspection_roles | non_visible_special_roles:
        raise AssertionError(
            f"SPECIAL_LIFECYCLE_OFFICES drifted: {ensure_supercc_court.SPECIAL_LIFECYCLE_OFFICES!r}"
        )
    if set(ensure_supercc_court.NON_VISIBLE_DEFAULT_SILENT_OFFICES) != ministry_roles | special_roles:
        raise AssertionError(f"NON_VISIBLE_DEFAULT_SILENT_OFFICES drifted: {ensure_supercc_court.NON_VISIBLE_DEFAULT_SILENT_OFFICES!r}")
    gongbu_dossier = ensure_supercc_court.office_dossier_text("gongbu")
    required_hierarchy_terms = (
        "court.dispatch_hierarchy.v1",
        "ordinary and superCC use the same validator",
        "court.child_office_profile.v1",
        "canonical_authority=false",
        "court.semantic.dispatch_context_packet.v1",
        "court.semantic.invariant_capsule.v1",
        "loaded_skills including decretum-matrix",
    )
    missing_hierarchy_terms = [
        term for term in required_hierarchy_terms if term not in gongbu_dossier
    ]
    if missing_hierarchy_terms:
        raise AssertionError(
            "generated superCC dossier hierarchy/P00 contract drifted: "
            f"missing={missing_hierarchy_terms}"
        )
    if "loaded_skills including court-capability-router" in gongbu_dossier:
        raise AssertionError("generated superCC dossier retained the legacy skill identity")
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
                dispatch_context_packet_json=dispatch_context_fixture(
                    "gongbu", "shangshu", "TEST-DISPATCH", "probe"
                ),
                office_preload_acks_json=preload_ack_fixture(
                    ensure_supercc_court, fake_check(), "gongbu"
                ),
                calling_office="shangshu",
                dry_run=True,
            )
        )
        if not dispatch_payload.get("ok"):
            raise AssertionError(f"dry-run dispatch should pass: {dispatch_payload}")
        if dispatch_payload.get("calling_office") != "shangshu":
            raise AssertionError("ministry dispatch must preserve shangshu caller")
        profile_gate = dispatch_payload.get("target_profile_gate")
        if not isinstance(profile_gate, dict) or profile_gate.get("ok") is not True:
            raise AssertionError(f"ministry dispatch target profile gate failed: {dispatch_payload}")
        expected_hierarchy = ensure_supercc_court.validate_dispatch_hierarchy(
            action="dispatch",
            calling_office="shangshu",
            target_role="gongbu",
            target_direct_superior="shangshu",
            instance_kind="office",
            canonical_authority=True,
            owner_role=None,
            child_profile=None,
        )
        expected_hierarchy_fields = {
            "hierarchy_gate": "PASSED",
            "hierarchy_schema": expected_hierarchy.hierarchy_schema,
            "hierarchy_manifest_sha256": expected_hierarchy.hierarchy_manifest_sha256,
            "hierarchy_edge_class": expected_hierarchy.edge_class,
            "hierarchy_calling_office": expected_hierarchy.normalized_caller,
            "hierarchy_target_role": expected_hierarchy.normalized_target,
            "hierarchy_owner_role": expected_hierarchy.normalized_owner,
        }
        actual_hierarchy_fields = {
            key: dispatch_payload.get(key) for key in expected_hierarchy_fields
        }
        if actual_hierarchy_fields != expected_hierarchy_fields:
            raise AssertionError(
                "ordinary/shared validator and superCC hierarchy evidence diverged: "
                f"expected={expected_hierarchy_fields} actual={actual_hierarchy_fields}"
            )
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
                dispatch_context_packet_json=dispatch_context_fixture(
                    "gongbu", "shangshu", "TEST-DISPATCH-NONVISIBLE", "probe"
                ),
                office_preload_acks_json=preload_ack_fixture(
                    ensure_supercc_court, fake_check(visible=False), "gongbu"
                ),
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
                dispatch_context_packet_json=dispatch_context_fixture(
                    "gongbu", "shangshu", "TEST-DISPATCH-DUP", "probe"
                ),
                office_preload_acks_json=preload_ack_fixture(
                    ensure_supercc_court, fake_check(duplicate=True), "gongbu"
                ),
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
                dispatch_context_packet_json=dispatch_context_fixture(
                    "gongbu", "shangshu", "TEST-DISPATCH-NO-TASK-ID", "probe"
                ),
                office_preload_acks_json=preload_ack_fixture(
                    ensure_supercc_court, fake_check(), "gongbu"
                ),
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


def check_taizi_to_gongbu_rejected_before_side_effects() -> None:
    """Future contract: a forbidden explicit caller stops before every adapter."""

    sys.path.insert(0, str(SCRIPTS))
    import ensure_supercc_court  # noqa: PLC0415

    counters = {
        "structured_task_creation": 0,
        "squad_send_mirror": 0,
        "pane_launch": 0,
        "pane_wake": 0,
        "native_enter_command": 0,
        "office_state_write": 0,
    }

    def fake_check(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "supercc_env_gate": "PASSED",
            "visible_display_gate": "PASSED",
            "display_transport_gate": "PASSED",
            "office_client_gate": "PASSED",
            "zellij": {
                "env": {"ZELLIJ_SESSION_NAME": "hierarchy-red", "ZELLIJ_PANE_ID": "0"},
                "panes_list": [
                    {
                        "pane_id": "terminal_gongbu",
                        "type": "terminal",
                        "title": ensure_supercc_court.OFFICES["gongbu"]["title"],
                    }
                ],
            },
            "squad": {
                "agents_json": [
                    {
                        "id": "gongbu",
                        "role": "gongbu",
                        "status": "active",
                        "supports_task_commands": True,
                        "supports_json_receive": True,
                    }
                ]
            },
        }

    def fake_create_task(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["structured_task_creation"] += 1
        return {
            "ok": True,
            "task_id": "hierarchy-red-task",
            "task_id_parse_ok": True,
        }

    def fake_send(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["squad_send_mirror"] += 1
        return {"ok": True, "task_id": "hierarchy-red-task"}

    def fake_run(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["native_enter_command"] += 1
        return {"ok": True, "returncode": 0, "stdout": "", "stderr": ""}

    def fake_launch(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["pane_launch"] += 1
        return {"ok": True}

    def fake_wake(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["pane_wake"] += 1
        return {"ok": True, "skipped": True, "reason": "spy"}

    def fake_state_write(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["office_state_write"] += 1
        return {"ok": True}

    originals = {
        "supercc_check_for_args": ensure_supercc_court.supercc_check_for_args,
        "create_squad_task_assignment": ensure_supercc_court.create_squad_task_assignment,
        "send_squad_notice": ensure_supercc_court.send_squad_notice,
        "run_command": ensure_supercc_court.run_command,
        "launch_offices": ensure_supercc_court.launch_offices,
        "maybe_send_inspector_wake_cc": ensure_supercc_court.maybe_send_inspector_wake_cc,
        "write_office_state": ensure_supercc_court.write_office_state,
        "sleep": ensure_supercc_court.time.sleep,
    }
    try:
        ensure_supercc_court.supercc_check_for_args = fake_check  # type: ignore[assignment]
        ensure_supercc_court.create_squad_task_assignment = fake_create_task  # type: ignore[assignment]
        ensure_supercc_court.send_squad_notice = fake_send  # type: ignore[assignment]
        ensure_supercc_court.run_command = fake_run  # type: ignore[assignment]
        ensure_supercc_court.launch_offices = fake_launch  # type: ignore[assignment]
        ensure_supercc_court.maybe_send_inspector_wake_cc = fake_wake  # type: ignore[assignment]
        ensure_supercc_court.write_office_state = fake_state_write  # type: ignore[assignment]
        ensure_supercc_court.time.sleep = lambda _seconds: None  # type: ignore[assignment]
        payload = ensure_supercc_court.enter_dispatch(
            argparse.Namespace(
                workspace=str(ROOT),
                role="gongbu",
                message="future hierarchy rejection probe",
                dispatch_uid="HIERARCHY-RED-TAIZI-GONGBU",
                calling_office="taizi",
                dry_run=False,
                allow_squad_only_fallback=False,
                enable_inspector=False,
                skip_inspector=False,
            )
        )
    finally:
        ensure_supercc_court.supercc_check_for_args = originals["supercc_check_for_args"]  # type: ignore[assignment]
        ensure_supercc_court.create_squad_task_assignment = originals["create_squad_task_assignment"]  # type: ignore[assignment]
        ensure_supercc_court.send_squad_notice = originals["send_squad_notice"]  # type: ignore[assignment]
        ensure_supercc_court.run_command = originals["run_command"]  # type: ignore[assignment]
        ensure_supercc_court.launch_offices = originals["launch_offices"]  # type: ignore[assignment]
        ensure_supercc_court.maybe_send_inspector_wake_cc = originals["maybe_send_inspector_wake_cc"]  # type: ignore[assignment]
        ensure_supercc_court.write_office_state = originals["write_office_state"]  # type: ignore[assignment]
        ensure_supercc_court.time.sleep = originals["sleep"]  # type: ignore[assignment]

    reason = (
        payload.get("dispatch_hierarchy_reason")
        or payload.get("dispatch_block_reason")
        or payload.get("reason")
    )
    violations: list[str] = []
    if payload.get("ok") is not False or payload.get("dispatch_blocked") is not True:
        violations.append(
            f"explicit taizi->gongbu was accepted: ok={payload.get('ok')!r} "
            f"dispatch_blocked={payload.get('dispatch_blocked')!r}"
        )
    if reason != "dispatch_hierarchy_edge_forbidden":
        violations.append(f"wrong rejection reason: {reason!r}")
    for boundary, count in counters.items():
        if count != 0:
            violations.append(f"{boundary} expected=0 actual={count}")
    if violations:
        raise AssertionError(
            "missing superCC dispatch hierarchy rejection before side effects: "
            + "; ".join(violations)
        )


def check_missing_target_profile_rejected_before_side_effects() -> None:
    """A canonical dispatch requires the target's exact standing profile."""

    sys.path.insert(0, str(SCRIPTS))
    import ensure_supercc_court  # noqa: PLC0415

    counters = {
        "environment_probe": 0,
        "structured_task_creation": 0,
        "squad_send_mirror": 0,
        "native_enter_command": 0,
        "office_state_write": 0,
    }

    def missing_profile(_role: str) -> dict[str, object]:
        return {
            "office_profile_loaded": False,
            "profile_source": str(ROOT / "agents" / "standing-officials" / "gongbu.toml"),
            "profile_hash": None,
            "profile_version": None,
            "profile_fields": {},
            "profile_missing_fields": ["role_key", "direct_superior"],
        }

    def fake_check(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["environment_probe"] += 1
        return {}

    def fake_create_task(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["structured_task_creation"] += 1
        return {"ok": True, "task_id": "unexpected-task"}

    def fake_send(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["squad_send_mirror"] += 1
        return {"ok": True}

    def fake_run(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["native_enter_command"] += 1
        return {"ok": True}

    def fake_state_write(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["office_state_write"] += 1
        return {"ok": True}

    originals = {
        "profile_metadata": ensure_supercc_court.profile_metadata,
        "supercc_check_for_args": ensure_supercc_court.supercc_check_for_args,
        "create_squad_task_assignment": ensure_supercc_court.create_squad_task_assignment,
        "send_squad_notice": ensure_supercc_court.send_squad_notice,
        "run_command": ensure_supercc_court.run_command,
        "write_office_state": ensure_supercc_court.write_office_state,
    }
    try:
        ensure_supercc_court.profile_metadata = missing_profile  # type: ignore[assignment]
        ensure_supercc_court.supercc_check_for_args = fake_check  # type: ignore[assignment]
        ensure_supercc_court.create_squad_task_assignment = fake_create_task  # type: ignore[assignment]
        ensure_supercc_court.send_squad_notice = fake_send  # type: ignore[assignment]
        ensure_supercc_court.run_command = fake_run  # type: ignore[assignment]
        ensure_supercc_court.write_office_state = fake_state_write  # type: ignore[assignment]
        payload = ensure_supercc_court.enter_dispatch(
            argparse.Namespace(
                workspace=str(ROOT),
                role="gongbu",
                message="missing standing profile must fail closed",
                dispatch_uid="HIERARCHY-RED-MISSING-PROFILE",
                calling_office="shangshu",
                dry_run=False,
                allow_squad_only_fallback=False,
                enable_inspector=False,
                skip_inspector=False,
            )
        )
    finally:
        ensure_supercc_court.profile_metadata = originals["profile_metadata"]  # type: ignore[assignment]
        ensure_supercc_court.supercc_check_for_args = originals["supercc_check_for_args"]  # type: ignore[assignment]
        ensure_supercc_court.create_squad_task_assignment = originals["create_squad_task_assignment"]  # type: ignore[assignment]
        ensure_supercc_court.send_squad_notice = originals["send_squad_notice"]  # type: ignore[assignment]
        ensure_supercc_court.run_command = originals["run_command"]  # type: ignore[assignment]
        ensure_supercc_court.write_office_state = originals["write_office_state"]  # type: ignore[assignment]

    violations: list[str] = []
    if payload.get("ok") is not False or payload.get("dispatch_blocked") is not True:
        violations.append(f"missing target profile was accepted: {payload}")
    if payload.get("dispatch_hierarchy_reason") != "dispatch_hierarchy_target_profile_required":
        violations.append(
            "wrong missing-profile reason: "
            f"{payload.get('dispatch_hierarchy_reason')!r}"
        )
    for boundary, count in counters.items():
        if count != 0:
            violations.append(f"{boundary} expected=0 actual={count}")
    if violations:
        raise AssertionError(
            "missing superCC target-profile rejection before side effects: "
            + "; ".join(violations)
        )


def check_special_lifecycle_dispatch_edges() -> None:
    """Special lifecycle roles keep explicit callers and deny ministry bypass."""

    sys.path.insert(0, str(SCRIPTS))
    import ensure_supercc_court  # noqa: PLC0415

    legal_cases = (
        ("shiguan", "taizi", "archive_evidence_dispatch", "taizi/menxia"),
        ("shiguan", "menxia", "archive_evidence_dispatch", "taizi/menxia"),
        ("shiguan-hermes", "menxia", "hermes_archive_evidence_dispatch", "taizi/menxia"),
        ("patrol-inspector", "taizi", "bounded_diagnostic_dispatch", "taizi"),
        ("zaochao", "taizi", "briefing_dispatch", "taizi"),
    )

    original_check = ensure_supercc_court.supercc_check_for_args
    try:
        ensure_supercc_court.supercc_check_for_args = lambda *_args, **_kwargs: {  # type: ignore[assignment]
            "supercc_env_gate": "PASSED",
            "visible_display_gate": "PASSED",
            "display_transport_gate": "PASSED",
            "office_client_gate": "PASSED",
            "zellij": {
                "env": {"ZELLIJ_SESSION_NAME": "special-lifecycle", "ZELLIJ_PANE_ID": "0"},
                "panes_list": [],
            },
            "squad": {"agents_json": []},
        }
        for role, caller, action, superior in legal_cases:
            message = f"bounded {action} fixture"
            dispatch_uid = f"SPECIAL-POSITIVE-{role}-{caller}"
            try:
                payload = ensure_supercc_court.enter_dispatch(
                    argparse.Namespace(
                        workspace=str(ROOT),
                        role=role,
                        message=message,
                        dispatch_uid=dispatch_uid,
                        dispatch_context_packet_json=dispatch_context_fixture(
                            role, caller, dispatch_uid, message
                        ),
                        calling_office=caller,
                        dry_run=True,
                        allow_squad_only_fallback=False,
                        enable_inspector=False,
                        skip_inspector=False,
                    )
                )
            except ValueError as exc:
                raise AssertionError(
                    f"legal special lifecycle edge raised instead of dispatching: role={role} caller={caller} error={exc}"
                ) from exc
            if payload.get("ok") is not True:
                raise AssertionError(f"legal special lifecycle edge was rejected: {payload}")
            if payload.get("hierarchy_gate") != "PASSED":
                raise AssertionError(f"special lifecycle hierarchy gate missing: {payload}")
            if payload.get("hierarchy_edge_class") != "special_lifecycle_dispatch":
                raise AssertionError(f"special lifecycle edge class drifted: {payload}")
            if payload.get("special_lifecycle_action") != action:
                raise AssertionError(f"special lifecycle action drifted: {payload}")
            if payload.get("direct_superior") != superior:
                raise AssertionError(f"special lifecycle direct superior drifted: {payload}")
            if payload.get("dispatch_delivery_channel") != ensure_supercc_court.NON_VISIBLE_SPECIAL_LIFECYCLE_DISPATCH_CHANNEL:
                raise AssertionError(f"special lifecycle must stay non-visible by default: {payload}")
            native = payload.get("native_enter_dispatch")
            if not isinstance(native, dict) or native.get("skipped") is not True or native.get("commands") != []:
                raise AssertionError(f"special lifecycle non-visible dispatch planned native input: {payload}")
    finally:
        ensure_supercc_court.supercc_check_for_args = original_check  # type: ignore[assignment]

    for role, _caller, _action, _superior in legal_cases:
        counters = {
            "environment_probe": 0,
            "structured_task_creation": 0,
            "squad_send_mirror": 0,
            "native_enter_command": 0,
            "office_state_write": 0,
        }

        def fake_check(*_args: object, **_kwargs: object) -> dict[str, object]:
            counters["environment_probe"] += 1
            return {}

        def fake_create_task(*_args: object, **_kwargs: object) -> dict[str, object]:
            counters["structured_task_creation"] += 1
            return {"ok": True, "task_id": "unexpected-task"}

        def fake_send(*_args: object, **_kwargs: object) -> dict[str, object]:
            counters["squad_send_mirror"] += 1
            return {"ok": True}

        def fake_run(*_args: object, **_kwargs: object) -> dict[str, object]:
            counters["native_enter_command"] += 1
            return {"ok": True}

        def fake_state_write(*_args: object, **_kwargs: object) -> dict[str, object]:
            counters["office_state_write"] += 1
            return {"ok": True}

        originals = {
            "supercc_check_for_args": ensure_supercc_court.supercc_check_for_args,
            "create_squad_task_assignment": ensure_supercc_court.create_squad_task_assignment,
            "send_squad_notice": ensure_supercc_court.send_squad_notice,
            "run_command": ensure_supercc_court.run_command,
            "write_office_state": ensure_supercc_court.write_office_state,
        }
        try:
            ensure_supercc_court.supercc_check_for_args = fake_check  # type: ignore[assignment]
            ensure_supercc_court.create_squad_task_assignment = fake_create_task  # type: ignore[assignment]
            ensure_supercc_court.send_squad_notice = fake_send  # type: ignore[assignment]
            ensure_supercc_court.run_command = fake_run  # type: ignore[assignment]
            ensure_supercc_court.write_office_state = fake_state_write  # type: ignore[assignment]
            try:
                payload = ensure_supercc_court.enter_dispatch(
                    argparse.Namespace(
                        workspace=str(ROOT),
                        role=role,
                        message="ministry must not dispatch special lifecycle roles",
                        dispatch_uid=f"SPECIAL-NEGATIVE-GONGBU-{role}",
                        calling_office="gongbu",
                        dry_run=False,
                        allow_squad_only_fallback=False,
                        enable_inspector=False,
                        skip_inspector=False,
                    )
                )
            except ValueError as exc:
                raise AssertionError(
                    f"illegal ministry->special edge raised without structured hierarchy evidence: role={role} error={exc}"
                ) from exc
        finally:
            ensure_supercc_court.supercc_check_for_args = originals["supercc_check_for_args"]  # type: ignore[assignment]
            ensure_supercc_court.create_squad_task_assignment = originals["create_squad_task_assignment"]  # type: ignore[assignment]
            ensure_supercc_court.send_squad_notice = originals["send_squad_notice"]  # type: ignore[assignment]
            ensure_supercc_court.run_command = originals["run_command"]  # type: ignore[assignment]
            ensure_supercc_court.write_office_state = originals["write_office_state"]  # type: ignore[assignment]

        violations: list[str] = []
        if payload.get("ok") is not False or payload.get("dispatch_blocked") is not True:
            violations.append(f"gongbu->{role} was accepted: {payload}")
        if payload.get("dispatch_hierarchy_reason") != "dispatch_hierarchy_edge_forbidden":
            violations.append(f"gongbu->{role} wrong reason: {payload.get('dispatch_hierarchy_reason')!r}")
        for boundary, count in counters.items():
            if count != 0:
                violations.append(f"gongbu->{role} {boundary} expected=0 actual={count}")
        if violations:
            raise AssertionError(
                "special lifecycle hierarchy bypass remains: " + "; ".join(violations)
            )

    wake_counters = {
        "environment_probe": 0,
        "squad_send": 0,
        "office_state_write": 0,
    }

    def wake_check(*_args: object, **_kwargs: object) -> dict[str, object]:
        wake_counters["environment_probe"] += 1
        return {"squad": {"agents_json": []}, "zellij": {"panes_list": []}}

    def wake_send(*_args: object, **_kwargs: object) -> dict[str, object]:
        wake_counters["squad_send"] += 1
        return {"ok": True}

    def wake_state(*_args: object, **_kwargs: object) -> dict[str, object]:
        wake_counters["office_state_write"] += 1
        return {"ok": True}

    wake_originals = {
        "supercc_check_for_args": ensure_supercc_court.supercc_check_for_args,
        "send_squad_notice": ensure_supercc_court.send_squad_notice,
        "write_office_state": ensure_supercc_court.write_office_state,
    }
    try:
        ensure_supercc_court.supercc_check_for_args = wake_check  # type: ignore[assignment]
        ensure_supercc_court.send_squad_notice = wake_send  # type: ignore[assignment]
        ensure_supercc_court.write_office_state = wake_state  # type: ignore[assignment]
        try:
            wake_payload = ensure_supercc_court.wake_roles(
                argparse.Namespace(
                    workspace=str(ROOT),
                    dry_run=False,
                    calling_office="gongbu",
                    enable_inspector=False,
                    skip_inspector=False,
                ),
                ("shiguan",),
                reason="forbidden ministry special-role wake",
                sender="gongbu",
            )
        except (KeyError, NameError, ValueError) as exc:
            raise AssertionError(
                f"illegal ministry special-role wake raised without structured hierarchy evidence: {exc}"
            ) from exc
    finally:
        ensure_supercc_court.supercc_check_for_args = wake_originals["supercc_check_for_args"]  # type: ignore[assignment]
        ensure_supercc_court.send_squad_notice = wake_originals["send_squad_notice"]  # type: ignore[assignment]
        ensure_supercc_court.write_office_state = wake_originals["write_office_state"]  # type: ignore[assignment]

    wake_violations: list[str] = []
    if wake_payload.get("ok") is not False or wake_payload.get("dispatch_blocked") is not True:
        wake_violations.append(f"gongbu->shiguan wake was accepted: {wake_payload}")
    if wake_payload.get("dispatch_hierarchy_reason") != "dispatch_hierarchy_edge_forbidden":
        wake_violations.append(
            f"gongbu->shiguan wake wrong reason: {wake_payload.get('dispatch_hierarchy_reason')!r}"
        )
    for boundary, count in wake_counters.items():
        if count != 0:
            wake_violations.append(f"wake {boundary} expected=0 actual={count}")
    if wake_violations:
        raise AssertionError(
            "special lifecycle wake bypass remains: " + "; ".join(wake_violations)
        )


def check_cli_special_lifecycle_preflight_before_bootstrap() -> None:
    """CLI LAUNCH/WAKE must reject illegal special edges before all runtime setup."""

    sys.path.insert(0, str(SCRIPTS))
    import ensure_supercc_court  # noqa: PLC0415
    import supercc_client_selection  # noqa: PLC0415

    special_roles = (
        "shiguan",
        "shiguan-hermes",
        "patrol-inspector",
        "zaochao",
    )
    actions = (
        ("launch", "--launch-offices"),
        ("wake", "--wake-offices"),
    )
    violations: list[str] = []

    for action_name, action_flag in actions:
        for role in special_roles:
            counters = {
                "office_client_resolve": 0,
                "office_client_maps": 0,
                "cli_source_signals": 0,
                "dependency_bootstrap": 0,
                "environment_probe": 0,
                "task_create": 0,
                "squad_send": 0,
                "native_command": 0,
                "office_state_write": 0,
            }

            original_resolve = ensure_supercc_court.resolve_office_client_args
            original_maps = ensure_supercc_court.normalize_office_client_maps
            original_cli_source_signals = supercc_client_selection.cli_source_signals

            def spy_resolve(*args: object, **kwargs: object) -> object:
                counters["office_client_resolve"] += 1
                return original_resolve(*args, **kwargs)

            def spy_maps(*args: object, **kwargs: object) -> object:
                counters["office_client_maps"] += 1
                return original_maps(*args, **kwargs)

            def spy_cli_source_signals() -> dict[str, object]:
                counters["cli_source_signals"] += 1
                return {
                    "office_client": "codex",
                    "source": "test_cli_source_signal",
                    "command": None,
                    "signals": ["test"],
                }

            def fake_bootstrap(*_args: object, **_kwargs: object) -> dict[str, object]:
                counters["dependency_bootstrap"] += 1
                return {"ok": True, "skipped": True, "reason": "test_stub"}

            def fake_environment(*_args: object, **_kwargs: object) -> dict[str, object]:
                counters["environment_probe"] += 1
                return {
                    "passed": True,
                    "ok": True,
                    "supercc_env_gate": "PASSED",
                    "visible_display_gate": "PASSED",
                    "display_transport_gate": "PASSED",
                    "office_client_gate": "PASSED",
                    "squad": {"agents_json": []},
                    "zellij": {"panes_list": [], "env": {}},
                    "codex": {},
                }

            def fake_task(*_args: object, **_kwargs: object) -> dict[str, object]:
                counters["task_create"] += 1
                return {"ok": True, "task_id": "test-task"}

            def fake_squad(*_args: object, **_kwargs: object) -> dict[str, object]:
                counters["squad_send"] += 1
                return {"ok": True}

            def fake_native(*_args: object, **_kwargs: object) -> dict[str, object]:
                counters["native_command"] += 1
                return {"ok": True, "returncode": 0, "stdout": "", "stderr": ""}

            def fake_state(*_args: object, **_kwargs: object) -> dict[str, object]:
                counters["office_state_write"] += 1
                return {"ok": True}

            originals = {
                "resolve_office_client_args": original_resolve,
                "normalize_office_client_maps": original_maps,
                "maybe_bootstrap_supercc_dependencies": ensure_supercc_court.maybe_bootstrap_supercc_dependencies,
                "check_office_client": ensure_supercc_court.check_office_client,
                "check_office_clients_for_roles": ensure_supercc_court.check_office_clients_for_roles,
                "supercc_check_for_args": ensure_supercc_court.supercc_check_for_args,
                "create_squad_task_assignment": ensure_supercc_court.create_squad_task_assignment,
                "send_squad_notice": ensure_supercc_court.send_squad_notice,
                "run_command": ensure_supercc_court.run_command,
                "write_office_state": ensure_supercc_court.write_office_state,
            }
            stdout = io.StringIO()
            stderr = io.StringIO()
            exit_code: int | None = None
            raised: BaseException | None = None
            try:
                ensure_supercc_court.resolve_office_client_args = spy_resolve  # type: ignore[assignment]
                ensure_supercc_court.normalize_office_client_maps = spy_maps  # type: ignore[assignment]
                supercc_client_selection.cli_source_signals = spy_cli_source_signals  # type: ignore[assignment]
                ensure_supercc_court.maybe_bootstrap_supercc_dependencies = fake_bootstrap  # type: ignore[assignment]
                ensure_supercc_court.check_office_client = fake_environment  # type: ignore[assignment]
                ensure_supercc_court.check_office_clients_for_roles = fake_environment  # type: ignore[assignment]
                ensure_supercc_court.supercc_check_for_args = fake_environment  # type: ignore[assignment]
                ensure_supercc_court.create_squad_task_assignment = fake_task  # type: ignore[assignment]
                ensure_supercc_court.send_squad_notice = fake_squad  # type: ignore[assignment]
                ensure_supercc_court.run_command = fake_native  # type: ignore[assignment]
                ensure_supercc_court.write_office_state = fake_state  # type: ignore[assignment]
                try:
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        exit_code = ensure_supercc_court.main(
                            [
                                "--workspace",
                                str(ROOT),
                                action_flag,
                                role,
                                "--calling-office",
                                "gongbu",
                                "--office-client",
                                "auto",
                                "--dry-run",
                                "--no-auto-install-deps",
                                "--format",
                                "json",
                            ]
                        )
                except BaseException as exc:  # argparse raises SystemExit on an entry-contract failure.
                    raised = exc
            finally:
                for name, original in originals.items():
                    setattr(ensure_supercc_court, name, original)
                supercc_client_selection.cli_source_signals = original_cli_source_signals  # type: ignore[assignment]

            case = f"gongbu->{role} {action_name}"
            if raised is not None:
                violations.append(
                    f"{case} raised {type(raised).__name__}: {raised}; stderr={stderr.getvalue().strip()!r}"
                )
                continue
            if exit_code != 2:
                violations.append(f"{case} exit expected=2 actual={exit_code}")
            try:
                payload = json.loads(stdout.getvalue())
            except json.JSONDecodeError as exc:
                violations.append(f"{case} did not emit structured JSON: {exc}; stdout={stdout.getvalue()!r}")
                continue
            if payload.get("ok") is not False or payload.get("dispatch_blocked") is not True:
                violations.append(f"{case} was accepted: {payload}")
            if payload.get("dispatch_hierarchy_reason") != "dispatch_hierarchy_edge_forbidden":
                violations.append(
                    f"{case} wrong hierarchy reason: {payload.get('dispatch_hierarchy_reason')!r}"
                )
            bootstrap = payload.get("dependency_bootstrap") or {}
            if bootstrap.get("skipped") is not True:
                violations.append(f"{case} missing skipped bootstrap evidence: {bootstrap}")
            for boundary, count in counters.items():
                if count != 0:
                    violations.append(f"{case} {boundary} expected=0 actual={count}")

    if violations:
        raise AssertionError(
            "CLI special lifecycle preflight must precede all client/bootstrap/runtime boundaries: "
            + "; ".join(violations)
        )


def dispatch_context_fixture(
    role: str,
    caller: str,
    dispatch_uid: str,
    message: str,
) -> str:
    import court_semantic_continuity  # noqa: PLC0415

    task_id = "supercc-dispatch-fixture"
    charter = "bounded superCC dispatch fixture charter"
    charter_sha256 = hashlib.sha256(charter.encode("utf-8")).hexdigest()
    capsule = court_semantic_continuity.build_invariant_capsule(
        charter,
        charter_sha256,
    )
    for field in (
        "non_goals",
        "boundaries",
        "allowed_actions",
        "forbidden_actions",
        "acceptance",
        "evidence_requirements",
        "stop_gates",
        "write_set",
    ):
        capsule[field] = [f"fixture-{field}"]
    capsule["governing_hashes"] = {"fixture": hashlib.sha256(b"fixture").hexdigest()}
    task: dict[str, object] = {
        "task_id": task_id,
        "charter": charter,
        "charter_revision": 1,
        "semantic_epoch": 1,
        "charter_sha256": charter_sha256,
        "invariant_capsule": capsule,
        "invariant_capsule_sha256": court_semantic_continuity.canonical_json_sha256(
            capsule
        ),
    }
    authority_sha256 = hashlib.sha256(b"fixture-authority").hexdigest()
    plan_sha256 = hashlib.sha256(b"fixture-plan").hexdigest()
    receipt = court_semantic_continuity.build_semantic_receipt(
        task,
        {
            "authority_revision": 1,
            "authority_sha256": authority_sha256,
            "plan_revision": 1,
            "plan_sha256": plan_sha256,
            "plan_cursor": "ENTER_DISPATCH",
            "git_fingerprint": "fixture-git",
            "recovery_checkpoint_id": "fixture-recovery",
            "shiguan_revision": 0,
            "shiguan_fingerprint": hashlib.sha256(b"fixture-shiguan").hexdigest(),
        },
        event_head_sha256=hashlib.sha256(b"fixture-event-head").hexdigest(),
        event_head_bytes=0,
        trigger="checkpoint",
        created_at="2026-07-17T00:00:00+00:00",
    )
    task["semantic_receipt"] = receipt
    RUNTIME_TASK_FIXTURES[task_id] = task
    semantic_packet = {
        "schema": "court.semantic.dispatch_context_packet.v1",
        "task_id": task_id,
        "sub_id": dispatch_uid,
        "semantic_epoch": 1,
        "invariant_capsule_sha256": task["invariant_capsule_sha256"],
        "semantic_receipt_id": receipt["receipt_id"],
        "semantic_receipt_sha256": receipt["receipt_sha256"],
        "authority_sha256": authority_sha256,
        "plan_sha256": plan_sha256,
        "plan_cursor": receipt["plan_cursor"],
        "fork_context": "none",
        "context_mode": "bounded",
        "pointers": [
            {"path": "authority/current.json", "sha256": authority_sha256},
            {"path": "plans/current.json", "sha256": plan_sha256},
        ],
    }
    if role in {"libu-hr", "hubu", "libu", "bingbu", "xingbu", "gongbu"}:
        direct_superior = "shangshu"
    elif role in {"shiguan", "shiguan-hermes"}:
        direct_superior = "taizi/menxia"
    else:
        direct_superior = "taizi"
    packet = {
        "schema": "court.supercc.enter_dispatch_context.v1",
        "dispatch_uid": dispatch_uid,
        "task_id": semantic_packet["task_id"],
        "role_key": role,
        "calling_office": caller,
        "direct_superior": direct_superior,
        "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        "semantic_packet": semantic_packet,
        "scope": {
            "allowed_paths": ["scripts/ensure_supercc_court.py"],
            "allowed_actions": ["inspect", "edit", "test"],
            "forbidden_actions": ["publish", "read_pending_body"],
            "acceptance": ["return bounded evidence"],
            "evidence_requirements": ["checker output"],
            "stop_gates": ["stop on authority or delivery failure"],
        },
    }
    return json.dumps(packet, ensure_ascii=False)


def preload_ack_fixture(
    ensure_supercc_court: object,
    check: dict[str, object],
    role: str,
) -> str:
    require_visible = role in {"taizi", "zhongshu", "menxia", "shangshu"}
    pending_check = {
        "zellij": check.get("zellij", {}),
        "squad": {"agents_json": []},
    }
    pending = ensure_supercc_court.active_office_preload_ack_gate(  # type: ignore[attr-defined]
        argparse.Namespace(workspace=str(ROOT), reclaim_existing=False),
        pending_check,
        role,
        require_visible=require_visible,
        allow_missing_identity=True,
    )
    generation = pending.get("identity_generation_challenge")
    if pending.get("gate") != "PRELOAD_PENDING" or not isinstance(generation, str):
        raise AssertionError(f"cannot enter PRELOAD_PENDING fixture phase: {pending}")
    OFFICE_STATE_FIXTURES[role] = {
        "preload_status": "PRELOAD_PENDING",
        "identity_id": None,
        "identity_generation": generation,
        "preload_ack": None,
    }
    identity = ensure_supercc_court.active_office_identity_fingerprint(  # type: ignore[attr-defined]
        check,
        role,
        require_visible=require_visible,
        workspace=ROOT,
    )
    if identity.get("ok") is not True:
        raise AssertionError(f"cannot build preload ACK fixture: {identity}")
    profile = ensure_supercc_court.profile_metadata(role)  # type: ignore[attr-defined]
    ack = {
        "schema": ensure_supercc_court.OFFICE_PRELOAD_ACK_SCHEMA,  # type: ignore[attr-defined]
        "preload_status": "PASSED",
        "identity_id": identity["identity_id"],
        "identity_generation": identity["identity_generation"],
        "identity_fingerprint": identity["identity_fingerprint"],
        "role_key": role,
        "direct_superior": ensure_supercc_court.direct_superior_metadata(role)[  # type: ignore[attr-defined]
            "direct_superior"
        ],
        "profile_hash": profile["profile_hash"],
        "dossier_hash": ensure_supercc_court.sha256_file(  # type: ignore[attr-defined]
            ensure_supercc_court.office_dossier_path(role)  # type: ignore[attr-defined]
        ),
        "court_skill_hash": ensure_supercc_court.sha256_file(  # type: ignore[attr-defined]
            ensure_supercc_court.skill_root() / "SKILL.md"  # type: ignore[attr-defined]
        ),
        "agent_dossier_loaded": "YES",
        "loaded_skills": ["decretum-matrix"],
    }
    return json.dumps({role: ack}, ensure_ascii=False)


def check_normal_role_transport_preflight_precedes_mutation() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import ensure_supercc_court  # noqa: PLC0415

    class BoundaryReached(RuntimeError):
        pass

    def missing_profile(_role: str) -> dict[str, object]:
        return {
            "office_profile_loaded": False,
            "profile_source": str(ROOT / "agents" / "standing-officials" / "zhongshu.toml"),
            "profile_hash": None,
            "profile_version": None,
            "profile_fields": {},
            "profile_missing_fields": ["role_key", "direct_superior"],
        }

    def boundary(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise BoundaryReached("runtime boundary reached before normal-role preflight")

    originals = {
        "profile_metadata": ensure_supercc_court.profile_metadata,
        "check_office_client": ensure_supercc_court.check_office_client,
        "supercc_check_for_args": ensure_supercc_court.supercc_check_for_args,
    }
    violations: list[str] = []
    args = argparse.Namespace(
        workspace=str(ROOT),
        dry_run=False,
        force=False,
        skip_inspector=False,
        calling_office="taizi",
        restart_offices="zhongshu",
        turn_start="zhongshu",
    )
    try:
        ensure_supercc_court.profile_metadata = missing_profile  # type: ignore[assignment]
        ensure_supercc_court.check_office_client = boundary  # type: ignore[assignment]
        ensure_supercc_court.supercc_check_for_args = boundary  # type: ignore[assignment]
        actions = (
            ("launch", lambda: ensure_supercc_court.launch_offices(args, ("zhongshu",))),
            ("wake", lambda: ensure_supercc_court.wake_roles(args, ("zhongshu",), reason="red", sender="taizi")),
            ("restart", lambda: ensure_supercc_court.restart_offices(args)),
            ("turn_start", lambda: ensure_supercc_court.turn_start(args)),
        )
        for name, action in actions:
            try:
                payload = action()
            except BoundaryReached as exc:
                violations.append(f"{name}:{exc}")
                continue
            if payload.get("ok") is not False or payload.get("dispatch_blocked") is not True:
                violations.append(f"{name}:missing-profile preflight did not block: {payload}")
    finally:
        for name, original in originals.items():
            setattr(ensure_supercc_court, name, original)
    if violations:
        raise AssertionError("normal-role mutation preceded shared preflight: " + "; ".join(violations))


def check_active_identity_preload_ack_required() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import ensure_supercc_court  # noqa: PLC0415

    counters = {"send": 0, "state": 0}
    check = {
        "supercc_env_gate": "PASSED",
        "visible_display_gate": "PASSED",
        "display_transport_gate": "PASSED",
        "office_client_gate": "PASSED",
        "zellij": {
            "selected_session": "preload-red",
            "env": {"ZELLIJ_SESSION_NAME": "preload-red"},
            "panes_list": [
                {
                    "pane_id": "terminal_zhongshu",
                    "title": ensure_supercc_court.OFFICES["zhongshu"]["title"],
                }
            ],
        },
        "squad": {
            "agents_json": [
                {
                    "id": "zhongshu",
                    "role": "zhongshu",
                    "status": "active",
                    "effective_client_type": "codex",
                }
            ]
        },
    }

    def send(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["send"] += 1
        return {"ok": True}

    def state(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["state"] += 1
        return {"ok": True}

    originals = {
        "supercc_check_for_args": ensure_supercc_court.supercc_check_for_args,
        "send_squad_notice": ensure_supercc_court.send_squad_notice,
        "write_office_state": ensure_supercc_court.write_office_state,
    }
    try:
        ensure_supercc_court.supercc_check_for_args = lambda *_args, **_kwargs: check  # type: ignore[assignment]
        ensure_supercc_court.send_squad_notice = send  # type: ignore[assignment]
        ensure_supercc_court.write_office_state = state  # type: ignore[assignment]
        payload = ensure_supercc_court.wake_roles(
            argparse.Namespace(
                workspace=str(ROOT),
                dry_run=False,
                calling_office="taizi",
                enable_inspector=False,
                skip_inspector=False,
            ),
            ("zhongshu",),
            reason="preload ack red",
            sender="taizi",
        )
        if payload.get("ok") is not False or payload.get("dispatch_block_reason") != "active_office_identity_generation_required":
            raise AssertionError(f"active disk-only office was accepted without current identity preload ACK: {payload}")
        if counters != {"send": 0, "state": 0}:
            raise AssertionError(f"preload ACK rejection reached delivery/state: {counters}")

        allowed = ensure_supercc_court.wake_roles(
            argparse.Namespace(
                workspace=str(ROOT),
                dry_run=False,
                calling_office="taizi",
                office_preload_acks_json=preload_ack_fixture(
                    ensure_supercc_court, check, "zhongshu"
                ),
                enable_inspector=False,
                skip_inspector=False,
            ),
            ("zhongshu",),
            reason="preload ack green",
            sender="taizi",
        )
        if allowed.get("ok") is not True or allowed.get("woken") != ["zhongshu"]:
            raise AssertionError(f"current identity-bound preload ACK was rejected: {allowed}")
        if counters != {"send": 1, "state": 1}:
            raise AssertionError(f"valid preload ACK did not reach one delivery/state write: {counters}")
    finally:
        for name, original in originals.items():
            setattr(ensure_supercc_court, name, original)


def check_enter_dispatch_context_and_delivery_state_atomicity() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import ensure_supercc_court  # noqa: PLC0415

    counters = {"environment": 0, "task": 0, "send": 0, "state": 0}
    empty_check = {
        "supercc_env_gate": "PASSED",
        "visible_display_gate": "PASSED",
        "display_transport_gate": "PASSED",
        "office_client_gate": "PASSED",
        "zellij": {"env": {"ZELLIJ_SESSION_NAME": "dispatch-red"}, "panes_list": []},
        "squad": {"agents_json": []},
    }

    def environment(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["environment"] += 1
        return empty_check

    def task(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["task"] += 1
        return {"ok": True, "task_id": "dispatch-red-task", "task_id_parse_ok": True}

    def send(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["send"] += 1
        return {"ok": False, "reason": "simulated_delivery_failure"}

    def state(*_args: object, **_kwargs: object) -> dict[str, object]:
        counters["state"] += 1
        return {"ok": True}

    originals = {
        "supercc_check_for_args": ensure_supercc_court.supercc_check_for_args,
        "create_squad_task_assignment": ensure_supercc_court.create_squad_task_assignment,
        "send_squad_notice": ensure_supercc_court.send_squad_notice,
        "write_office_state": ensure_supercc_court.write_office_state,
    }
    try:
        ensure_supercc_court.supercc_check_for_args = environment  # type: ignore[assignment]
        ensure_supercc_court.create_squad_task_assignment = task  # type: ignore[assignment]
        ensure_supercc_court.send_squad_notice = send  # type: ignore[assignment]
        ensure_supercc_court.write_office_state = state  # type: ignore[assignment]
        missing_context = ensure_supercc_court.enter_dispatch(
            argparse.Namespace(
                workspace=str(ROOT),
                role="gongbu",
                message="bounded dispatch",
                dispatch_uid="DISPATCH-CONTEXT-RED",
                calling_office="shangshu",
                dry_run=False,
                allow_squad_only_fallback=False,
                enable_inspector=False,
                skip_inspector=False,
            )
        )
        if missing_context.get("ok") is not False or missing_context.get("dispatch_block_reason") != "enter_dispatch_context_packet_required":
            raise AssertionError(f"ENTER_DISPATCH accepted a missing bounded context/scope packet: {missing_context}")
        if counters != {"environment": 0, "task": 0, "send": 0, "state": 0}:
            raise AssertionError(f"missing context reached runtime boundary: {counters}")

        escaped = json.loads(
            dispatch_context_fixture(
                "gongbu", "shangshu", "DISPATCH-SCOPE-RED", "bounded dispatch"
            )
        )
        escaped["scope"]["allowed_paths"] = ["../pending/body"]
        escaped_scope = ensure_supercc_court.enter_dispatch(
            argparse.Namespace(
                workspace=str(ROOT),
                role="gongbu",
                message="bounded dispatch",
                dispatch_uid="DISPATCH-SCOPE-RED",
                dispatch_context_packet_json=json.dumps(escaped, ensure_ascii=False),
                calling_office="shangshu",
                dry_run=False,
                allow_squad_only_fallback=False,
                enable_inspector=False,
                skip_inspector=False,
            )
        )
        if escaped_scope.get("dispatch_block_reason") != "enter_dispatch_scope_invalid:allowed_paths":
            raise AssertionError(f"escaping dispatch scope was not rejected: {escaped_scope}")
        if counters != {"environment": 0, "task": 0, "send": 0, "state": 0}:
            raise AssertionError(f"escaping scope reached runtime boundary: {counters}")

        counters.update(environment=0, task=0, send=0, state=0)
        message = "bounded dispatch"
        failed_delivery = ensure_supercc_court.enter_dispatch(
            argparse.Namespace(
                workspace=str(ROOT),
                role="gongbu",
                message=message,
                dispatch_uid="DISPATCH-DELIVERY-RED",
                dispatch_context_packet_json=dispatch_context_fixture(
                    "gongbu", "shangshu", "DISPATCH-DELIVERY-RED", message
                ),
                calling_office="shangshu",
                dry_run=False,
                allow_squad_only_fallback=False,
                enable_inspector=False,
                skip_inspector=False,
            )
        )
    finally:
        for name, original in originals.items():
            setattr(ensure_supercc_court, name, original)
    if failed_delivery.get("ok") is not False:
        raise AssertionError(f"failed squad delivery was reported as successful: {failed_delivery}")
    if counters["state"] != 0:
        raise AssertionError(f"failed squad delivery wrote queued/awake state: {counters}")


def check_menxia_reject_correction_red_matrix() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import ensure_supercc_court  # noqa: PLC0415

    failures: dict[str, list[str]] = {
        "preflight_current_authority": [],
        "identity_generation": [],
        "native_short_circuit": [],
        "exact_string_scope": [],
        "launch_state_persistence": [],
    }

    active_check = {
        "passed": True,
        "supercc_env_gate": "PASSED",
        "visible_display_gate": "PASSED",
        "display_transport_gate": "PASSED",
        "office_client_gate": "PASSED",
        "zellij": {
            "selected_session": "menxia-correction-red",
            "env": {"ZELLIJ_SESSION_NAME": "menxia-correction-red"},
            "panes_list": [
                {
                    "pane_id": "terminal_zhongshu",
                    "title": ensure_supercc_court.OFFICES["zhongshu"]["title"],
                }
            ],
        },
        "squad": {
            "agents_json": [
                {
                    "id": "zhongshu",
                    "role": "zhongshu",
                    "status": "active",
                    "effective_client_type": "codex",
                }
            ]
        },
    }

    bootstrap_calls: list[str] = []
    original_bootstrap = ensure_supercc_court.maybe_bootstrap_supercc_dependencies
    original_check = ensure_supercc_court.supercc_check_for_args
    original_launch = ensure_supercc_court.launch_offices
    try:
        ensure_supercc_court.maybe_bootstrap_supercc_dependencies = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: bootstrap_calls.append("bootstrap")
            or {"ok": True, "skipped": False}
        )
        ensure_supercc_court.supercc_check_for_args = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: active_check
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            ensure_supercc_court.main(
                [
                    "--workspace",
                    str(ROOT),
                    "--turn-start",
                    "zhongshu",
                    "--format",
                    "json",
                ]
            )
        if bootstrap_calls:
            failures["preflight_current_authority"].append(
                "turn-start reached dependency bootstrap before full identity/ACK preflight"
            )

        bootstrap_calls.clear()
        ensure_supercc_court.launch_offices = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: {"ok": True}
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            ensure_supercc_court.main(
                [
                    "--workspace",
                    str(ROOT),
                    "--launch-offices",
                    "zhongshu",
                    "--format",
                    "json",
                ]
            )
        if bootstrap_calls != ["bootstrap"]:
            failures["preflight_current_authority"].append(
                f"new-identity launch bootstrap exception was not explicit/usable: {bootstrap_calls}"
            )
    finally:
        ensure_supercc_court.maybe_bootstrap_supercc_dependencies = original_bootstrap  # type: ignore[assignment]
        ensure_supercc_court.supercc_check_for_args = original_check  # type: ignore[assignment]
        ensure_supercc_court.launch_offices = original_launch  # type: ignore[assignment]

    fake_message = "bounded dispatch"
    fake_packet = dispatch_context_fixture(
        "gongbu",
        "shangshu",
        "DISPATCH-CURRENT-AUTHORITY-RED",
        fake_message,
    )
    fake_task_id = json.loads(fake_packet)["task_id"]
    current_task = RUNTIME_TASK_FIXTURES.pop(fake_task_id)
    fake_authority = ensure_supercc_court.validate_enter_dispatch_context(
        argparse.Namespace(
            dispatch_context_packet_json=fake_packet,
            dispatch_uid="DISPATCH-CURRENT-AUTHORITY-RED",
            message=fake_message,
        ),
        "gongbu",
        "shangshu",
        "shangshu",
    )
    if fake_authority.get("ok") is not False:
        failures["preflight_current_authority"].append(
            "self-consistent fake SHA/P00 packet passed without a current runtime task/receipt"
        )
    RUNTIME_TASK_FIXTURES[fake_task_id] = current_task
    forged_packet = json.loads(fake_packet)
    forged_packet["semantic_packet"]["invariant_capsule_sha256"] = "f" * 64
    forged_authority = ensure_supercc_court.validate_enter_dispatch_context(
        argparse.Namespace(
            dispatch_context_packet_json=json.dumps(forged_packet),
            dispatch_uid="DISPATCH-CURRENT-AUTHORITY-RED",
            message=fake_message,
        ),
        "gongbu",
        "shangshu",
        "shangshu",
    )
    if (
        forged_authority.get("ok") is not False
        or forged_authority.get("reason")
        != "enter_dispatch_semantic_authority_invalid"
    ):
        failures["preflight_current_authority"].append(
            "forged capsule hash was not rejected by the shared current-authority validator"
        )

    non_visible_check = {
        "zellij": {
            "selected_session": "generation-red",
            "env": {"ZELLIJ_SESSION_NAME": "generation-red"},
            "panes_list": [],
        },
        "squad": {
            "agents_json": [
                {
                    "id": "gongbu",
                    "role": "gongbu",
                    "status": "active",
                    "effective_client_type": "codex",
                }
            ]
        },
    }
    OFFICE_STATE_FIXTURES.pop("gongbu", None)
    generationless = ensure_supercc_court.active_office_identity_fingerprint(
        non_visible_check,
        "gongbu",
        require_visible=False,
    )
    if generationless.get("ok") is not False:
        failures["identity_generation"].append(
            "non-visible active identity fingerprint accepted no incarnation/challenge"
        )
    pending = ensure_supercc_court.active_office_preload_ack_gate(
        argparse.Namespace(workspace=str(ROOT)),
        {"zellij": {"panes_list": []}, "squad": {"agents_json": []}},
        "gongbu",
        require_visible=False,
        allow_missing_identity=True,
    )
    if (
        pending.get("gate") != "PRELOAD_PENDING"
        or not isinstance(pending.get("identity_generation_challenge"), str)
        or pending.get("preload_ack") is not None
        or (pending.get("identity") or {}).get("identity_fingerprint") is not None
    ):
        failures["identity_generation"].append(
            "new identity did not expose PRELOAD_PENDING challenge without controller-synthesized fingerprint/ACK"
        )
    else:
        generation = pending["identity_generation_challenge"]
        OFFICE_STATE_FIXTURES["gongbu"] = {
            "preload_status": "PRELOAD_PENDING",
            "identity_id": None,
            "identity_generation": generation,
            "preload_ack": None,
        }
        identity = ensure_supercc_court.active_office_identity_fingerprint(
            non_visible_check,
            "gongbu",
            require_visible=False,
            workspace=ROOT,
        )
        profile = ensure_supercc_court.profile_metadata("gongbu")
        office_ack = {
            "schema": ensure_supercc_court.OFFICE_PRELOAD_ACK_SCHEMA,
            "preload_status": "PASSED",
            "identity_id": identity.get("identity_id"),
            "identity_generation": identity.get("identity_generation"),
            "identity_fingerprint": identity.get("identity_fingerprint"),
            "role_key": "gongbu",
            "direct_superior": "shangshu",
            "profile_hash": profile.get("profile_hash"),
            "dossier_hash": ensure_supercc_court.sha256_file(
                ensure_supercc_court.office_dossier_path("gongbu")
            ),
            "court_skill_hash": ensure_supercc_court.sha256_file(
                ensure_supercc_court.skill_root() / "SKILL.md"
            ),
            "agent_dossier_loaded": "YES",
            "loaded_skills": ["decretum-matrix"],
        }
        ack_args = argparse.Namespace(
            workspace=str(ROOT),
            office_preload_acks_json=json.dumps({"gongbu": office_ack}),
        )
        ack_gate = ensure_supercc_court.active_office_preload_ack_gate(
            ack_args,
            non_visible_check,
            "gongbu",
            require_visible=False,
            allow_missing_identity=False,
        )
        if ack_gate.get("gate") != "PASSED":
            failures["identity_generation"].append(
                f"PRELOAD_PENDING challenge did not accept office ACK: {ack_gate.get('reason')}"
            )
        else:
            OFFICE_STATE_FIXTURES["gongbu"] = {
                "preload_status": "PASSED",
                "identity_id": identity.get("identity_id"),
                "identity_generation": identity.get("identity_generation"),
                "preload_ack": office_ack,
            }
            resumed = ensure_supercc_court.active_office_preload_ack_gate(
                argparse.Namespace(workspace=str(ROOT)),
                non_visible_check,
                "gongbu",
                require_visible=False,
                allow_missing_identity=False,
            )
            if resumed.get("gate") != "PASSED":
                failures["identity_generation"].append(
                    f"office ACK could not resume from persisted current generation: {resumed.get('reason')}"
                )

            old_generation = identity.get("identity_generation")
            original_archive_run = ensure_supercc_court.run_command
            original_archive_write = ensure_supercc_court.write_office_state
            try:
                ensure_supercc_court.run_command = (  # type: ignore[assignment]
                    lambda *_args, **_kwargs: {"ok": True}
                )

                def record_archive_state(
                    _workspace: object,
                    modes: dict[str, dict[str, object]],
                    **_kwargs: object,
                ) -> dict[str, object]:
                    OFFICE_STATE_FIXTURES.update(modes)
                    return {"ok": True}

                ensure_supercc_court.write_office_state = record_archive_state  # type: ignore[assignment]
                archived = ensure_supercc_court.archive_agent(
                    "gongbu",
                    ROOT,
                    False,
                    zellij_session="generation-red",
                )
            finally:
                ensure_supercc_court.run_command = original_archive_run  # type: ignore[assignment]
                ensure_supercc_court.write_office_state = original_archive_write  # type: ignore[assignment]
            reset = OFFICE_STATE_FIXTURES.get("gongbu", {})
            if (
                archived.get("ok") is not True
                or reset.get("preload_status") != "PRELOAD_PENDING"
                or reset.get("preload_ack") is not None
                or reset.get("identity_generation") == old_generation
            ):
                failures["identity_generation"].append(
                    "archive did not rotate generation and clear the old preload ACK"
                )
            stale_ack = ensure_supercc_court.active_office_preload_ack_gate(
                ack_args,
                non_visible_check,
                "gongbu",
                require_visible=False,
                allow_missing_identity=False,
            )
            if stale_ack.get("gate") != "FAILED":
                failures["identity_generation"].append(
                    "same-session same-id rejoin reused the archived generation's old ACK"
                )

    original_run = ensure_supercc_court.run_command
    original_sleep = ensure_supercc_court.time.sleep
    try:
        calls: list[list[str]] = []
        sleeps: list[float] = []

        def first_write_fails(command: list[str], **_kwargs: object) -> dict[str, object]:
            calls.append(command)
            return {"ok": False, "reason": "write_chars_failed"}

        ensure_supercc_court.run_command = first_write_fails  # type: ignore[assignment]
        ensure_supercc_court.time.sleep = lambda seconds: sleeps.append(seconds)  # type: ignore[assignment]
        ensure_supercc_court.native_pane_enter_sequence(
            ROOT,
            "terminal-red",
            "receive",
            dry_run=False,
        )
        if len(calls) != 1 or sleeps:
            failures["native_short_circuit"].append(
                f"write-chars failure continued to Enter/sleep: calls={len(calls)} sleeps={sleeps}"
            )

        calls.clear()
        sleeps.clear()
        results = iter((True, False, True))

        def first_enter_fails(command: list[str], **_kwargs: object) -> dict[str, object]:
            calls.append(command)
            return {"ok": next(results)}

        ensure_supercc_court.run_command = first_enter_fails  # type: ignore[assignment]
        ensure_supercc_court.native_pane_enter_sequence(
            ROOT,
            "terminal-red",
            "receive",
            dry_run=False,
        )
        if len(calls) != 2 or sleeps:
            failures["native_short_circuit"].append(
                f"first Enter failure continued to sleep/second Enter: calls={len(calls)} sleeps={sleeps}"
            )
    finally:
        ensure_supercc_court.run_command = original_run  # type: ignore[assignment]
        ensure_supercc_court.time.sleep = original_sleep  # type: ignore[assignment]

    visible_check = {
        "passed": True,
        "supercc_env_gate": "PASSED",
        "visible_display_gate": "PASSED",
        "display_transport_gate": "PASSED",
        "office_client_gate": "PASSED",
        "zellij": {
            "selected_session": "enter-live-red",
            "env": {"ZELLIJ_SESSION_NAME": "enter-live-red"},
            "panes_list": [
                {
                    "pane_id": "terminal_zhongshu",
                    "title": ensure_supercc_court.OFFICES["zhongshu"]["title"],
                }
            ],
        },
        "squad": {
            "agents_json": [
                {
                    "id": "zhongshu",
                    "role": "zhongshu",
                    "status": "active",
                    "effective_client_type": "codex",
                }
            ]
        },
    }
    visible_ack = preload_ack_fixture(
        ensure_supercc_court,
        visible_check,
        "zhongshu",
    )
    original_enter_check = ensure_supercc_court.supercc_check_for_args
    original_enter_task = ensure_supercc_court.create_squad_task_assignment
    original_enter_send = ensure_supercc_court.send_squad_notice
    original_enter_run = ensure_supercc_court.run_command
    original_enter_sleep = ensure_supercc_court.time.sleep
    original_enter_state = ensure_supercc_court.write_office_state
    try:
        ensure_supercc_court.supercc_check_for_args = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: visible_check
        )
        ensure_supercc_court.create_squad_task_assignment = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: {
                "ok": True,
                "task_id": "11111111-1111-1111-1111-111111111111",
                "task_id_parse_ok": True,
            }
        )
        ensure_supercc_court.send_squad_notice = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: {"ok": True}
        )
        state_writes: list[object] = []
        ensure_supercc_court.write_office_state = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: state_writes.append(True) or {"ok": True}
        )

        def run_visible_failure(outcomes: tuple[bool, ...], dispatch_uid: str) -> tuple[dict[str, object], list[list[str]], list[float]]:
            commands: list[list[str]] = []
            sleeps: list[float] = []
            values = iter(outcomes)

            def command_result(command: list[str], **_kwargs: object) -> dict[str, object]:
                commands.append(command)
                return {"ok": next(values)}

            ensure_supercc_court.run_command = command_result  # type: ignore[assignment]
            ensure_supercc_court.time.sleep = lambda seconds: sleeps.append(seconds)  # type: ignore[assignment]
            message = "visible sequential dispatch"
            payload = ensure_supercc_court.enter_dispatch(
                argparse.Namespace(
                    workspace=str(ROOT),
                    role="zhongshu",
                    message=message,
                    dispatch_uid=dispatch_uid,
                    dispatch_context_packet_json=dispatch_context_fixture(
                        "zhongshu", "taizi", dispatch_uid, message
                    ),
                    office_preload_acks_json=visible_ack,
                    calling_office="taizi",
                    dry_run=False,
                    allow_squad_only_fallback=False,
                    enable_inspector=False,
                    skip_inspector=False,
                )
            )
            return payload, commands, sleeps

        write_failed, commands, sleeps = run_visible_failure(
            (False,),
            "ENTER-LIVE-WRITE-FAIL",
        )
        if (
            write_failed.get("ok") is not False
            or (write_failed.get("native_enter_dispatch") or {}).get("reason")
            != "native_write_chars_failed_before_enter"
            or len(commands) != 1
            or sleeps
            or state_writes
        ):
            failures["native_short_circuit"].append(
                "enter_dispatch live write-chars failure did not short-circuit before Enter/sleep/state"
            )

        state_writes.clear()
        enter_failed, commands, sleeps = run_visible_failure(
            (True, False),
            "ENTER-LIVE-FIRST-ENTER-FAIL",
        )
        if (
            enter_failed.get("ok") is not False
            or (enter_failed.get("native_enter_dispatch") or {}).get("reason")
            != "native_first_enter_failed_before_delay"
            or len(commands) != 2
            or sleeps
            or state_writes
        ):
            failures["native_short_circuit"].append(
                "enter_dispatch live first-Enter failure did not short-circuit before delay/second Enter/state"
            )
    finally:
        ensure_supercc_court.supercc_check_for_args = original_enter_check  # type: ignore[assignment]
        ensure_supercc_court.create_squad_task_assignment = original_enter_task  # type: ignore[assignment]
        ensure_supercc_court.send_squad_notice = original_enter_send  # type: ignore[assignment]
        ensure_supercc_court.run_command = original_enter_run  # type: ignore[assignment]
        ensure_supercc_court.time.sleep = original_enter_sleep  # type: ignore[assignment]
        ensure_supercc_court.write_office_state = original_enter_state  # type: ignore[assignment]

    native_wake_calls: list[str] = []
    original_preflight = ensure_supercc_court.supercc_transport_preflight
    original_send = ensure_supercc_court.send_squad_notice
    original_native = ensure_supercc_court.native_pane_enter_sequence
    try:
        ensure_supercc_court.supercc_transport_preflight = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: {
                "ok": True,
                "transport_preflight": [
                    {"role": role, "active_office_preload_ack_gate": {"gate": "PASSED"}}
                    for role in ensure_supercc_court.NO_SILENCE_ROLES
                ],
            }
        )
        ensure_supercc_court.send_squad_notice = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: {"ok": False, "reason": "squad_send_failed"}
        )
        ensure_supercc_court.native_pane_enter_sequence = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: native_wake_calls.append("native") or {"ok": True}
        )
        ensure_supercc_court.mark_turn_start_open_decree(
            argparse.Namespace(workspace=str(ROOT), dry_run=False),
            active_check,
        )
        if native_wake_calls:
            failures["native_short_circuit"].append(
                "turn-start squad-send failure still reached native double-enter"
            )
    finally:
        ensure_supercc_court.supercc_transport_preflight = original_preflight  # type: ignore[assignment]
        ensure_supercc_court.send_squad_notice = original_send  # type: ignore[assignment]
        ensure_supercc_court.native_pane_enter_sequence = original_native  # type: ignore[assignment]

    launch_check = {
        "passed": True,
        "supercc_env_gate": "PASSED",
        "visible_display_gate": "PASSED",
        "display_transport_gate": "PASSED",
        "office_client_gate": "PASSED",
        "zellij": {
            "selected_session": "launch-state-red",
            "env": {"ZELLIJ_SESSION_NAME": "launch-state-red"},
            "panes_list": [],
        },
        "squad": {"agents_json": []},
    }
    launch_originals = {
        "supercc_transport_preflight": ensure_supercc_court.supercc_transport_preflight,
        "check_office_client": ensure_supercc_court.check_office_client,
        "check_office_clients_for_roles": ensure_supercc_court.check_office_clients_for_roles,
        "rename_taizi_pane": ensure_supercc_court.rename_taizi_pane,
        "join_agent": ensure_supercc_court.join_agent,
        "request_budget_summary": ensure_supercc_court.request_budget_summary,
        "write_office_state": ensure_supercc_court.write_office_state,
    }
    try:
        ensure_supercc_court.supercc_transport_preflight = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: {
                "ok": True,
                "transport_preflight": [
                    {
                        "role": "taizi",
                        "active_office_preload_ack_gate": {
                            "gate": "PRELOAD_PENDING",
                            "identity_generation_challenge": "a" * 64,
                        },
                    }
                ],
                "special_lifecycle_preflight": [],
                "check": launch_check,
            }
        )
        ensure_supercc_court.check_office_client = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: {"available": True}
        )
        ensure_supercc_court.check_office_clients_for_roles = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: {"available": True, "roles": {}}
        )
        ensure_supercc_court.rename_taizi_pane = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: {"ok": True}
        )
        ensure_supercc_court.join_agent = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: {"ok": True, "actual_id": "taizi"}
        )
        ensure_supercc_court.request_budget_summary = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: {
                "ok": True,
                "request_rate_limit_per_minute": 10,
                "request_interval_seconds": 6.0,
                "office_show_delay": {
                    "jitter_requested_seconds": 0.0,
                    "base_seconds": 0.0,
                },
                "provider_launch_queue": [],
            }
        )
        ensure_supercc_court.write_office_state = (  # type: ignore[assignment]
            lambda *_args, **_kwargs: {
                "ok": False,
                "reason": "simulated_launch_state_write_failure",
            }
        )
        launch_payload = ensure_supercc_court.launch_offices(
            argparse.Namespace(
                workspace=str(ROOT),
                dry_run=True,
                force=False,
                skip_inspector=False,
                archive_test_agents=False,
                reclaim_existing=False,
                ministry_mode="independent",
                office_client="codex",
                enable_inspector=False,
            ),
            (),
        )
        if launch_payload.get("ok") is not False:
            failures["launch_state_persistence"].append(
                "launch_offices reported success after PRELOAD_PENDING state persistence failed"
            )
    finally:
        for name, original in launch_originals.items():
            setattr(ensure_supercc_court, name, original)

    invalid_scope_values: tuple[object, ...] = (True, 1, None, {"x": "y"}, ["nested"])
    for invalid in invalid_scope_values:
        packet = json.loads(fake_packet)
        packet["scope"]["allowed_actions"] = [invalid]
        scoped = ensure_supercc_court.validate_enter_dispatch_context(
            argparse.Namespace(
                dispatch_context_packet_json=json.dumps(packet, ensure_ascii=False),
                dispatch_uid="DISPATCH-CURRENT-AUTHORITY-RED",
                message=fake_message,
            ),
            "gongbu",
            "shangshu",
            "shangshu",
        )
        if scoped.get("reason") != "enter_dispatch_scope_invalid:allowed_actions":
            failures["exact_string_scope"].append(
                f"non-string scope element was not rejected exactly: {invalid!r} -> {scoped.get('reason')!r}"
            )

    failed_groups = {
        group: reasons for group, reasons in failures.items() if reasons
    }
    if failed_groups:
        raise AssertionError(
            "MENXIA_REJECT_CORRECTION_RED="
            + json.dumps(failed_groups, ensure_ascii=False, sort_keys=True)
        )


def main() -> int:
    sys.path.insert(0, str(SCRIPTS))
    import ensure_supercc_court  # noqa: PLC0415

    original_read_office_state = ensure_supercc_court.read_office_state
    original_load_tasks = ensure_supercc_court.court_runtime.load_tasks
    ensure_supercc_court.read_office_state = (  # type: ignore[assignment]
        lambda *_args, **_kwargs: {
            "ok": True,
            "roles": OFFICE_STATE_FIXTURES,
        }
    )
    ensure_supercc_court.court_runtime.load_tasks = (  # type: ignore[assignment]
        lambda: dict(RUNTIME_TASK_FIXTURES)
    )
    try:
        check_source_rules()
        check_supercc_launcher_shape()
        check_dispatch_evidence()
        check_taizi_to_gongbu_rejected_before_side_effects()
        check_missing_target_profile_rejected_before_side_effects()
        check_special_lifecycle_dispatch_edges()
        check_cli_special_lifecycle_preflight_before_bootstrap()
        check_normal_role_transport_preflight_precedes_mutation()
        check_active_identity_preload_ack_required()
        check_enter_dispatch_context_and_delivery_state_atomicity()
        check_menxia_reject_correction_red_matrix()
    finally:
        ensure_supercc_court.read_office_state = original_read_office_state  # type: ignore[assignment]
        ensure_supercc_court.court_runtime.load_tasks = original_load_tasks  # type: ignore[assignment]
    print("SUPERCC_MINISTRY_DISPATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
