"""Regression checks for strict superCC pane, client, and supervisor truth gates."""

from __future__ import annotations

from pathlib import Path
import sys

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

    parser = ensure_supercc_court.build_parser()
    args = parser.parse_args(["--workspace", str(ROOT), "--rename-taizi"])
    failed_manifest = ensure_supercc_court.side_effect_manifest(args, {"ok": False})
    assert failed_manifest["planned_if_live"]
    assert failed_manifest["applied"] == []
    assert failed_manifest["mutates_runtime"] is False

    print("SUPERCC_TRUTH_GATES_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
