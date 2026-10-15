"""Regression checks for strict superCC pane, client, and supervisor truth gates."""

from __future__ import annotations

from pathlib import Path
from contextlib import ExitStack
from contextlib import redirect_stdout
import io
import json
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_supercc_functional  # type: ignore  # noqa: E402
import ensure_supercc_court  # type: ignore  # noqa: E402


T04_ORIGINAL_DEGRADED_COUNTEREXAMPLE: dict[str, object] = {
    "check_passed": False,
    "supercc_env_gate": "runtime_degraded",
    "dispatch": {"ok": False},
    "supervisor": {"silent_supervisor": True, "abnormal_count": 3},
}


def check_fixture(title: str | None, *, actual_client: str = "codex", duplicate: bool = False) -> dict[str, object]:
    panes: list[dict[str, str]] = []
    if title is not None:
        panes.append({"title": title, "pane_id": "terminal_1"})
    if duplicate:
        panes.append({"title": ensure_supercc_court.role_title("zhongshu"), "pane_id": "terminal_2"})
    return {
        "zellij": {"selected_session": "fixture", "panes_list": panes},
        "squad": {
            "agents_json": [
                {
                    "id": "zhongshu",
                    "role": "zhongshu",
                    "status": "active",
                    "effective_client_type": actual_client,
                }
            ]
        },
    }


def assert_strict_gate_matrix() -> None:
    """Keep the T04 counterexample and exact strict gate type checks explicit."""

    valid = {
        "check_passed": True,
        "supercc_env_gate": "PASSED",
        "dispatch": {"ok": True},
        "supervisor": {"silent_supervisor": True, "abnormal_count": 0},
    }
    cases: tuple[tuple[str, object, bool], ...] = (
        ("positive_exact", valid, True),
        ("T04_original_runtime_degraded", T04_ORIGINAL_DEGRADED_COUNTEREXAMPLE, False),
        ("summary_non_dict", None, False),
        ("top_level_list", [], False),
        ("check_failed", {**valid, "check_passed": False}, False),
        ("check_passed_string", {**valid, "check_passed": "true"}, False),
        ("missing_check_passed", {k: v for k, v in valid.items() if k != "check_passed"}, False),
        ("missing_env_gate", {k: v for k, v in valid.items() if k != "supercc_env_gate"}, False),
        ("missing_dispatch", {k: v for k, v in valid.items() if k != "dispatch"}, False),
        ("missing_supervisor", {k: v for k, v in valid.items() if k != "supervisor"}, False),
        ("env_gate_none", {**valid, "supercc_env_gate": None}, False),
        ("runtime_degraded_otherwise_success", {**valid, "supercc_env_gate": "runtime_degraded"}, False),
        ("dispatch_none", {**valid, "dispatch": None}, False),
        ("dispatch_non_dict", {**valid, "dispatch": "ok"}, False),
        ("dispatch_ok_false", {**valid, "dispatch": {"ok": False}}, False),
        ("dispatch_ok_missing", {**valid, "dispatch": {}}, False),
        ("dispatch_ok_string", {**valid, "dispatch": {"ok": "true"}}, False),
        ("supervisor_none", {**valid, "supervisor": None}, False),
        ("supervisor_non_dict", {**valid, "supervisor": []}, False),
        (
            "silent_supervisor_false",
            {**valid, "supervisor": {"silent_supervisor": False, "abnormal_count": 0}},
            False,
        ),
        (
            "silent_supervisor_missing",
            {**valid, "supervisor": {"abnormal_count": 0}},
            False,
        ),
        (
            "silent_supervisor_string",
            {**valid, "supervisor": {"silent_supervisor": "true", "abnormal_count": 0}},
            False,
        ),
        ("abnormal_count_missing", {**valid, "supervisor": {"silent_supervisor": True}}, False),
        (
            "abnormal_count_none",
            {**valid, "supervisor": {"silent_supervisor": True, "abnormal_count": None}},
            False,
        ),
        (
            "abnormal_count_one",
            {**valid, "supervisor": {"silent_supervisor": True, "abnormal_count": 1}},
            False,
        ),
        (
            "abnormal_count_string",
            {**valid, "supervisor": {"silent_supervisor": True, "abnormal_count": "0"}},
            False,
        ),
        (
            "abnormal_count_bool",
            {**valid, "supervisor": {"silent_supervisor": True, "abnormal_count": False}},
            False,
        ),
        (
            "abnormal_count_negative",
            {**valid, "supervisor": {"silent_supervisor": True, "abnormal_count": -1}},
            False,
        ),
    )
    for name, summary, expected in cases:
        actual = check_supercc_functional.strict_passes(summary)  # type: ignore[arg-type]
        assert actual is expected, f"strict gate matrix case {name}: expected {expected}, got {actual}"


def assert_action_receipts() -> list[dict[str, object]]:
    """Exercise action outcomes independently of the environment health gate."""
    launcher = ensure_supercc_court
    parser = launcher.build_parser()
    receipts: list[dict[str, object]] = []
    for rename_ok, join_ok, expected in (
        (False, False, "FAILED"),
        (True, False, "PARTIAL"),
        (False, True, "PARTIAL"),
        (True, True, "SUCCESS"),
    ):
        args = parser.parse_args(["--workspace", str(ROOT), "--rename-taizi"])
        health = {"passed": True, "squad": {"agents_json": []}, "zellij": {}}
        with ExitStack() as stack:
            stack.enter_context(patch.object(launcher, "supercc_check_for_args", return_value=health))
            stack.enter_context(patch.object(launcher, "rename_taizi_pane", return_value={"ok": rename_ok}))
            stack.enter_context(patch.object(launcher, "join_agent", return_value={"ok": join_ok}))
            result = launcher.rename_taizi_only(args)
        assert result["ok"] is (expected == "SUCCESS"), result
        assert result["status"] == expected, result
        applied = launcher.side_effect_manifest(args, result)["applied"]
        assert applied == (["rename_current_pane"] if rename_ok else []) + (["join_taizi_identity"] if join_ok else [])
        receipts.append({"action": "rename_taizi", "rename_ok": rename_ok, "join_ok": join_ok, "status": expected, "applied": applied})

    # For rename, a healthy environment and a bare ok are not mutation evidence.
    assert launcher.side_effect_manifest(args, {"ok": True})["applied"] == []

    # The public CLI must return a failure exit for partial/failed action results.
    for status, exit_code in (("SUCCESS", 0), ("PARTIAL", 2), ("FAILED", 2)):
        with ExitStack() as stack:
            stack.enter_context(patch.object(launcher, "maybe_bootstrap_supercc_dependencies", return_value={"ok": True}))
            stack.enter_context(patch.object(launcher, "rename_taizi_only", return_value={"ok": status == "SUCCESS", "status": status}))
            stack.enter_context(redirect_stdout(io.StringIO()))
            assert launcher.main(["--workspace", str(ROOT), "--rename-taizi"]) == exit_code

    for sends, state_ok, expected in (
        ({"bingbu": False, "gongbu": False}, False, "FAILED"),
        ({"bingbu": True, "gongbu": False}, True, "PARTIAL"),
        ({"bingbu": True, "gongbu": True}, False, "PARTIAL"),
        ({"bingbu": True, "gongbu": True}, True, "SUCCESS"),
    ):
        args = parser.parse_args(["--workspace", str(ROOT), "--closeout-silence"])
        health = {"passed": True, "squad": {"agents_json": [{"id": role, "status": "active"} for role in sends]}, "zellij": {}}
        with ExitStack() as stack:
            stack.enter_context(patch.object(launcher, "supercc_check_for_args", return_value=health))
            stack.enter_context(patch.object(launcher, "send_squad_notice", side_effect=lambda _workspace, _sender, role, *_args: {"ok": sends[role]}))
            writer = stack.enter_context(patch.object(launcher, "write_office_state", return_value={"ok": state_ok}))
            result = launcher.silence_roles(args, ("bingbu", "gongbu", "hubu"), unfinished=set(), reason="fixture")
        assert result["ok"] is (expected == "SUCCESS"), result
        assert result["status"] == expected, result
        assert result["silenced"] == ([role for role, ok in sends.items() if ok] if state_ok else []), result
        written_modes = writer.call_args.args[1]
        assert all(role not in written_modes for role, ok in sends.items() if not ok)
        assert "hubu" not in result["silenced"]
        applied = launcher.side_effect_manifest(args, result)["applied"]
        assert ("write_idle_receive_modes" in applied) is state_ok
        assert ("send_silence_notice:bingbu" in applied) is sends["bingbu"]
        assert ("send_silence_notice:gongbu" in applied) is sends["gongbu"]
        receipts.append({"action": "silence", "sends": sends, "state_ok": state_ok, "status": expected, "silenced": result["silenced"], "applied": applied})

    # Real state writers raise on invalid state or I/O failure; retain delivery evidence.
    with ExitStack() as stack:
        stack.enter_context(patch.object(launcher, "supercc_check_for_args", return_value=health))
        stack.enter_context(patch.object(launcher, "send_squad_notice", return_value={"ok": True}))
        stack.enter_context(patch.object(launcher, "write_office_state", side_effect=OSError("fixture write denied")))
        result = launcher.silence_roles(args, ("bingbu",), unfinished=set(), reason="fixture")
    assert result["status"] == "PARTIAL" and result["silenced"] == []
    assert result["state"]["ok"] is False

    # Dry-run success is planning only; protected and unfinished roles are never sent silence.
    args.dry_run = True
    with ExitStack() as stack:
        stack.enter_context(patch.object(launcher, "supercc_check_for_args", return_value=health))
        sender = stack.enter_context(patch.object(launcher, "send_squad_notice", return_value={"ok": True, "dry_run": True}))
        stack.enter_context(patch.object(launcher, "write_office_state", return_value={"ok": True, "dry_run": True}))
        result = launcher.silence_roles(args, ("bingbu", "gongbu", "taizi"), unfinished={"gongbu"}, reason="fixture")
    assert sender.call_count == 1
    assert result["silenced"] == [] and result["expected_silenced_roles_for_supervisor"] == []
    assert launcher.side_effect_manifest(args, result)["applied"] == []
    return receipts


def assert_side_effect_manifest_compatibility() -> list[dict[str, object]]:
    """Preserve untouched action results while explicit evidence takes priority."""
    launcher = ensure_supercc_court
    parser = launcher.build_parser()
    receipts: list[dict[str, object]] = []
    # This is the real successful write_agent_dossiers result shape from the
    # integration regression; that producer does not emit explicit evidence.
    dossier_success = {
        "ok": True,
        "written_count": 1,
        "dossiers": [{"ok": True, "written": True, "changed": True}],
    }
    for flags, payload in (
        (["--write-agent-dossiers"], dossier_success),
        (["--launch-three"], {"ok": True}),
        (["--launch-visible-core"], {"ok": True}),
        (["--launch-offices", "bingbu"], {"ok": True}),
        (["--turn-start", "visible-core"], {"ok": True}),
        (["--restart-offices", "bingbu"], {"ok": True}),
        (["--wake-offices", "bingbu"], {"ok": True}),
        (["--enter-dispatch"], {"ok": True}),
        (["--super-entry", "launch"], {"ok": True}),
    ):
        args = parser.parse_args(["--workspace", str(ROOT), *flags])
        result = launcher.side_effect_manifest(args, payload)
        assert result["applied"] == result["planned_if_live"] and result["applied"], result
        assert result["mutates_runtime"] is True
        receipts.append({"action": result["selected_action"], "applied": result["applied"]})
        for evidence in ([], ["one_confirmed_effect"]):
            explicit = launcher.side_effect_manifest(args, {**payload, "_applied_side_effects": evidence})
            assert explicit["applied"] == evidence, explicit
        assert launcher.side_effect_manifest(args, {"ok": False})["applied"] == []
        args.dry_run = True
        assert launcher.side_effect_manifest(args, payload)["applied"] == []

    # F07 producers must never expand planned effects from their top-level ok,
    # even if an explicit list is empty or unavailable.
    for flag in ("--rename-taizi", "--closeout-silence"):
        args = parser.parse_args(["--workspace", str(ROOT), flag])
        for payload in ({"ok": True}, {"ok": False}, {"ok": True, "_applied_side_effects": []}):
            result = launcher.side_effect_manifest(args, payload)
            assert result["applied"] == [] and result["mutates_runtime"] is False, result
        partial = launcher.side_effect_manifest(args, {"ok": False, "_applied_side_effects": ["one_confirmed_effect"]})
        assert partial["applied"] == ["one_confirmed_effect"], partial
    return receipts


def main() -> int:
    canonical = ensure_supercc_court.role_title("zhongshu")

    check = check_fixture(canonical)
    visible = ensure_supercc_court.visible_office_panes(check)
    assert ensure_supercc_court.office_uniqueness_gate(check, visible, "zhongshu")["ok"] is True

    for bad_title in ("zhongshu", "*zhongshu"):
        check = check_fixture(bad_title)
        visible = ensure_supercc_court.visible_office_panes(check)
        gate = ensure_supercc_court.office_uniqueness_gate(check, visible, "zhongshu")
        assert gate["ok"] is False
        assert gate["visible_pane_selection"]["reason"] == "pane_title_drift"

    check = check_fixture(None)
    visible = ensure_supercc_court.visible_office_panes(check)
    gate = ensure_supercc_court.office_uniqueness_gate(check, visible, "zhongshu")
    assert gate["ok"] is False
    assert "missing_current_zellij_pane_for_visible_role" in gate["reason"]

    check = check_fixture(canonical, duplicate=True)
    visible = ensure_supercc_court.visible_office_panes(check)
    assert ensure_supercc_court.office_uniqueness_gate(check, visible, "zhongshu")["ok"] is False

    check = check_fixture(canonical, actual_client="codex")
    assert ensure_supercc_court.office_identity_client_binding(check, "zhongshu", "codex")["ok"] is True
    mismatch = ensure_supercc_court.office_identity_client_binding(check, "zhongshu", "claude")
    assert mismatch["ok"] is False
    assert mismatch["reason"] == "active_squad_identity_client_mismatch"

    profile = ensure_supercc_court.profile_metadata("zhongshu")
    profile_gate = ensure_supercc_court.dispatch_target_profile_gate("zhongshu", profile)
    assert profile_gate["ok"] is True
    wrong_role_profile = dict(profile)
    wrong_role_profile["profile_fields"] = {
        **dict(profile.get("profile_fields") or {}),
        "role_key": "menxia",
    }
    wrong_role_gate = ensure_supercc_court.dispatch_target_profile_gate(
        "zhongshu", wrong_role_profile
    )
    assert wrong_role_gate["ok"] is False
    assert "standing_profile_role_mismatch" in wrong_role_gate["reason_codes"]

    special_cases = (
        ("shiguan", "menxia", "archive_evidence_dispatch", "taizi/menxia"),
        ("shiguan-hermes", "taizi", "hermes_archive_evidence_dispatch", "taizi/menxia"),
        ("patrol-inspector", "taizi", "bounded_diagnostic_dispatch", "taizi"),
        ("zaochao", "taizi", "briefing_dispatch", "taizi"),
    )
    for role, caller, action, direct_superior in special_cases:
        role_profile = ensure_supercc_court.profile_metadata(role)
        role_profile_gate = ensure_supercc_court.dispatch_target_profile_gate(
            role, role_profile
        )
        superior = ensure_supercc_court.direct_superior_metadata(role)
        assert superior["direct_superior"] == direct_superior
        decision, authority = ensure_supercc_court.special_lifecycle_dispatch_authority(
            role,
            caller,
            superior,
            role_profile,
            role_profile_gate,
        )
        assert decision.allowed is True
        assert decision.edge_class == "special_lifecycle_dispatch"
        assert authority["gate"] == "PASSED"
        assert authority["action"] == action
        denied, denied_authority = ensure_supercc_court.special_lifecycle_dispatch_authority(
            role,
            "gongbu",
            superior,
            role_profile,
            role_profile_gate,
        )
        assert denied.allowed is False
        assert denied.reason_codes == ("dispatch_hierarchy_edge_forbidden",)
        assert denied_authority["reason"] == "dispatch_hierarchy_edge_forbidden"

    for signal in ensure_supercc_court.current_process_chain_signals():
        assert ";cmd=" not in signal.lower()

    assert_strict_gate_matrix()
    receipts = assert_action_receipts()
    compatibility_receipts = assert_side_effect_manifest_compatibility()

    parser = ensure_supercc_court.build_parser()
    args = parser.parse_args(["--workspace", str(ROOT), "--rename-taizi"])
    failed_manifest = ensure_supercc_court.side_effect_manifest(args, {"ok": False})
    assert failed_manifest["planned_if_live"]
    assert failed_manifest["applied"] == []
    assert failed_manifest["mutates_runtime"] is False

    print(json.dumps({"ok": True, "status": "PASSED", "action_receipts": receipts, "side_effect_compatibility": compatibility_receipts, "real_pane_squad": "NOT_RUN"}, ensure_ascii=False))
    print("SUPERCC_TRUTH_GATES_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
