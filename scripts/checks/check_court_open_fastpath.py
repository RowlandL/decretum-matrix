

#!/usr/bin/env python3
"""Focused checks for the single-process court-open and Shangshu packet path."""

from __future__ import annotations

# A+B layering: real module lives in scripts/checks/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.dont_write_bytecode = True

import court_open_fastpath


SOURCE_PRELOAD_MARGIN_BYTES = 1024


class FakeRuntime:
    def __init__(self, task: dict[str, object]) -> None:
        self.task = task
        self.load_calls = 0
        self.admission_calls = 0

    def load_tasks(self) -> dict[str, dict[str, object]]:
        self.load_calls += 1
        return {str(self.task["task_id"]): self.task}

    @staticmethod
    def public_dispatch_context_packet(task: dict[str, object], wave_id: str) -> dict[str, object]:
        receipt = task["semantic_receipt"]
        return {
            "schema": "court.semantic.dispatch_context_packet.v1",
            "task_id": task["task_id"],
            "sub_id": wave_id,
            "case_ref": receipt["case_ref"],
            "semantic_receipt_id": receipt["receipt_id"],
        }

    @staticmethod
    def public_context_budget_pool(task: dict[str, object], wave_id: str) -> dict[str, object]:
        return {
            "schema": "court.budget.pool.v1",
            "budget_id": f"budget:{task['task_id']}:{wave_id}",
            "root_id": "taizi",
        }

    def validate_fast_admission(
        self,
        task: dict[str, object],
        request: dict[str, object],
    ) -> dict[str, object]:
        from court_runtime import (
            _validate_canonical_admission_preloads, build_parser, public_admission_request_argv,
        )

        binding = request["requested_bindings"][0]
        parsed = build_parser().parse_args(public_admission_request_argv(request))
        _validate_canonical_admission_preloads(parsed)
        from court_agent_admission import _admission_lease_metadata_error
        assert _admission_lease_metadata_error(
            request["budget_lease"], calling_office=request["calling_office"],
            direct_superior=request["direct_superior"], next_depth=request["next_depth"],
        ) is None
        self.admission_calls += 1
        return {
            "allowed": True,
            "decision": "admitted",
            "selected_protocol": "v2",
            "selected_bindings": [binding],
        }


def _task() -> dict[str, object]:
    return {
        "task_id": "fast-open-fixture",
        "semantic_epoch": 3,
        "semantic_state": "DISPATCHABLE",
        "semantic_receipt": {
            "receipt_id": "SR-FAST-OPEN",
            "semantic_epoch": 3,
            "case_ref": {"court_code": "SREVIEW-20260906-1", "charter_revision": 3},
            "checkpoint_id": "SC-FAST-OPEN",
            "plan_ref": {"court_code": "SREVIEW-20260906-1", "charter_revision": 3, "plan_revision": 1},
            "plan_cursor": "PHASE5.2 -> PHASE9 -> PHASE10",
            "verdict": "DISPATCHABLE",
        },
    }


def _identity(path: Path) -> tuple[dict[str, object], list[list[str]]]:
    return (
        {
            "path": str(path.resolve()),
            "branch": "release/beta1.0.2-hotfix-v1",
            "HEAD": "5" * 40,
            "index_count": 0,
            "tracked_dirty_count": 0,
        },
        [["git", "fixture"]],
    )


def _write_skill(root: Path, *, wrong_ministry: str | None = None, oversized: bool = False) -> None:
    skill = "---\nname: decretum-matrix\n---\n# Decretum Matrix\n"
    if oversized:
        skill += "x" * court_open_fastpath.MINIMAL_PRELOAD_BYTES
    (root / "SKILL.md").write_text(skill, encoding="utf-8")
    startup = root / "references" / "court-normal-startup.md"
    startup.parent.mkdir(parents=True, exist_ok=True)
    startup.write_text("# Startup fixture\n", encoding="utf-8")
    hierarchy_path = root / "references" / "manifests" / "court-dispatch-hierarchy.v1.json"
    hierarchy_path.parent.mkdir(parents=True, exist_ok=True)
    hierarchy_path.write_text(
        json.dumps(
            {
                "schema": "court.dispatch_hierarchy.v1",
                "canonical_roles": {
                    role: {"direct_superior": superior}
                    for role, superior in court_open_fastpath.ROLE_SUPERIORS.items()
                },
                "allowed_edges": [
                    *[
                        {"action": "dispatch", "caller": "taizi", "target": role}
                        for role in court_open_fastpath.THREE_DEPARTMENTS
                    ],
                    *[
                        {"action": "dispatch", "caller": "shangshu", "target": role}
                        for role in court_open_fastpath.SIX_MINISTRIES
                    ],
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    office_zh = {
        "zhongshu": "Zhongshu",
        "menxia": "Menxia",
        "shangshu": "Shangshu",
        "libu-hr": "LibuHR",
        "hubu": "Hubu",
        "libu": "Libu",
        "bingbu": "Bingbu",
        "xingbu": "Xingbu",
        "gongbu": "Gongbu",
    }
    for role in (*court_open_fastpath.THREE_DEPARTMENTS, *court_open_fastpath.SIX_MINISTRIES):
        superior = court_open_fastpath.ROLE_SUPERIORS[role]
        if role == wrong_ministry:
            superior = "taizi"
        profile = root / "agents" / "standing-officials" / f"{role}.toml"
        dossier = root / "agents" / "office-dossiers" / role / "AGENTS.md"
        profile.parent.mkdir(parents=True, exist_ok=True)
        dossier.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text(
            "[profile]\n"
            f'role_key = "{role}"\n'
            f'office_zh = "{office_zh[role]}"\n'
            f'direct_superior = "{superior}"\n',
            encoding="utf-8",
        )
        dossier.write_text(f"# Fixture\n\n- role: {role}\n", encoding="utf-8")


def _request(root: Path, worktree: Path) -> dict[str, object]:
    return {
        "schema": court_open_fastpath.REQUEST_SCHEMA,
        "operation_id": "court-open-fixture",
        "task_id": "fast-open-fixture",
        "authority": "super",
        "authority_source": "explicit_latest_user",
        "behavior": "parallel",
        "worktree": str(worktree),
        "skill_root": str(root),
        "host_capacity": 16,
        "host_active_agents": 1,
        "host_retained_agents": 0,
        "host_reclamation_status": "verified",
        "system_memory_percent": 40.0,
        "requested_offices": list(court_open_fastpath.THREE_DEPARTMENTS),
        "write_sets": {},
        "expected_branch": "release/beta1.0.2-hotfix-v1",
        "expected_head": "5" * 40,
        "case_ref": {"court_code": "SREVIEW-20260906-1", "charter_revision": 3},
        "plan_ref": {"court_code": "SREVIEW-20260906-1", "charter_revision": 3, "plan_revision": 1},
        "semantic_receipt_id": "SR-FAST-OPEN",
        "transport": "codex",
        "task_focus": "fast court open fixture",
        "expires_at_utc": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
    }


def _main_json(argv: list[str]) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        code = court_open_fastpath.main([*argv, "--format", "json"])
    result = json.loads(stdout.getvalue())
    if not isinstance(result, dict):
        raise AssertionError("fastpath main did not emit a JSON object")
    return code, result


def _main_parse_exit(argv: list[str]) -> tuple[int, str]:
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        try:
            code = court_open_fastpath.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, stderr.getvalue()


def _request_template_checks() -> dict[str, bool]:
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="court-open-template-") as temp_text:
        worktree = Path(temp_text) / "worktree"
        worktree.mkdir()
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        common = [
            "--fast",
            "--request-template",
            "--task-id",
            "template-fixture",
            "--authority",
            "super",
            "--behavior",
            "parallel",
            "--worktree",
            str(worktree),
            "--task-focus",
            "read-only request template fixture",
        ]

        template_prepare_calls: list[object] = []
        original_prepare = court_open_fastpath.prepare_fast_open

        def forbidden_prepare(value: object, **_kwargs: object) -> dict[str, object]:
            template_prepare_calls.append(value)
            raise AssertionError("request template entered prepare_fast_open")

        court_open_fastpath.prepare_fast_open = forbidden_prepare
        try:
            default_code, default_template = _main_json(common)
            known_code, known_template = _main_json(
                [
                    *common,
                    "--host-capacity",
                    "16",
                    "--host-active-agents",
                    "1",
                    "--host-reclamation-status",
                    "verified",
                    "--expires-at-utc",
                    expires_at,
                ]
            )
            single_code, single_template = _main_json(
                [
                    *common,
                    "--authority-source",
                    "startup_question_answered",
                    "--requested-office",
                    "shangshu",
                    "--host-capacity",
                    "16",
                    "--host-active-agents",
                    "1",
                    "--host-reclamation-status",
                    "verified",
                    "--expires-at-utc",
                    expires_at,
                ]
            )
            exclusive_code, exclusive = _main_json(
                [*common, "--request-json", json.dumps({"schema": court_open_fastpath.REQUEST_SCHEMA})]
            )
        finally:
            court_open_fastpath.prepare_fast_open = original_prepare

        required_outer_fields = {
            "schema",
            "task_id",
            "authority",
            "authority_source",
            "behavior",
            "worktree",
            "host_capacity",
            "host_active_agents",
            "host_reclamation_status",
            "expires_at_utc",
            "task_focus",
        }
        instructions = default_template.get("template_instructions")
        checks["request_template_schema_and_required_fields"] = (
            default_code == 0
            and default_template.get("schema") == court_open_fastpath.REQUEST_SCHEMA
            and required_outer_fields.issubset(default_template)
            and default_template.get("authority_source") == "explicit_latest_user"
            and default_template.get("requested_offices")
            == list(court_open_fastpath.THREE_DEPARTMENTS)
            and default_template.get("host_capacity") is None
            and default_template.get("host_active_agents") is None
            and default_template.get("host_reclamation_status") == "unknown"
            and default_template.get("expires_at_utc") is None
            and isinstance(instructions, dict)
            and instructions.get("status") == "FILL_REQUIRED"
            and all(field in instructions for field in (
                "host_capacity",
                "host_active_agents",
                "host_reclamation_status",
                "expires_at_utc",
            ))
        )

        unknown_runtime = FakeRuntime(_task())
        try:
            court_open_fastpath.normalize_request(default_template)
        except court_open_fastpath.FastPathInvalid as exc:
            normalize_problem = str(exc)
        else:
            normalize_problem = ""
        try:
            court_open_fastpath.prepare_fast_open(
                default_template,
                runtime_api=unknown_runtime,
                identity_loader=_identity,
                concurrent_preload=False,
            )
        except court_open_fastpath.FastPathInvalid as exc:
            prepare_problem = str(exc)
        else:
            prepare_problem = ""
        checks["request_template_unknown_fails_closed"] = (
            normalize_problem == "expires_at_utc_required"
            and prepare_problem == "expires_at_utc_required"
            and unknown_runtime.load_calls == 0
            and unknown_runtime.admission_calls == 0
        )

        normalized = court_open_fastpath.normalize_request(known_template)
        checks["request_template_known_facts_normalize_without_prepare"] = (
            known_code == 0
            and normalized.get("host_capacity") == 16
            and normalized.get("host_active_agents") == 1
            and normalized.get("host_reclamation_status") == "verified"
            and normalized.get("expires_at_utc") == expires_at
            and not template_prepare_calls
        )
        normalized_single = court_open_fastpath.normalize_request(single_template)
        checks["request_template_authority_source_and_single_office"] = (
            single_code == 0
            and single_template.get("authority_source") == "startup_question_answered"
            and single_template.get("requested_offices") == ["shangshu"]
            and normalized_single.get("authority_source") == "startup_question_answered"
            and normalized_single.get("requested_offices") == ["shangshu"]
            and not template_prepare_calls
        )
        invalid_source_code, invalid_source_stderr = _main_parse_exit(
            [*common, "--authority-source", "invalid-authority-source"]
        )
        checks["request_template_authority_source_parser_rejects_invalid"] = (
            invalid_source_code == 2
            and "invalid choice" in invalid_source_stderr
            and "invalid-authority-source" in invalid_source_stderr
        )
        checks["request_template_sources_are_exclusive"] = (
            exclusive_code == 3
            and exclusive.get("status") == "INVALID"
            and exclusive.get("problems") == ["request_template_exclusive"]
            and not template_prepare_calls
        )

        root = Path(temp_text) / "skill"
        root.mkdir()
        _write_skill(root)
        request = _request(root, worktree)
        request_file = Path(temp_text) / "request.json"
        request_file.write_text(json.dumps(request), encoding="utf-8")
        source_template_option_code, source_template_option_stderr = _main_parse_exit(
            [
                "--fast",
                "--request-json",
                json.dumps(request),
                "--authority-source",
                "explicit_latest_user",
            ]
        )
        source_calls: list[object] = []

        def prepared(value: object, **_kwargs: object) -> dict[str, object]:
            source_calls.append(value)
            return {
                "schema": court_open_fastpath.RECEIPT_SCHEMA,
                "ok": True,
                "status": "READY_FOR_HOST_DISPATCH",
            }

        court_open_fastpath.prepare_fast_open = prepared
        try:
            json_code, _json_result = _main_json(
                ["--fast", "--request-json", json.dumps(request)]
            )
            file_code, _file_result = _main_json(
                ["--fast", "--request-file", str(request_file)]
            )
        finally:
            court_open_fastpath.prepare_fast_open = original_prepare
        file_basis = source_calls[1].get("path_basis") if len(source_calls) == 2 else None
        json_source = dict(source_calls[0]) if len(source_calls) == 2 else {}
        file_source = dict(source_calls[1]) if len(source_calls) == 2 else {}
        file_source.pop("path_basis", None)
        checks["request_template_existing_request_sources_unchanged"] = (
            json_code == 0
            and file_code == 0
            and len(source_calls) == 2
            and source_calls[0].get("task_id") == request["task_id"]
            and json_source == request
            and file_source == request
            and isinstance(file_basis, dict)
            and file_basis.get("kind") == "request_file_parent"
            and file_basis.get("path") == str(request_file.parent.resolve())
            and source_template_option_code == 2
            and "require --request-template" in source_template_option_stderr
        )
    return checks


def run_checks(*, shangshu_only: bool = False, concurrent_probes: bool = True) -> dict[str, object]:
    problems: list[str] = []
    checks: dict[str, object] = {}
    checks.update(_request_template_checks())
    root_reads = ('SKILL.md', 'references/court-normal-startup.md',
                  'agents/office-dossiers/taizi/AGENTS.md', 'agents/standing-officials/taizi.toml')
    checks['root_entry_with_metadata_budget'] = (
        sum((court_open_fastpath.ROOT / name).stat().st_size for name in root_reads) + 512
        <= court_open_fastpath.MINIMAL_PRELOAD_BYTES
    )
    source_roles = (*court_open_fastpath.THREE_DEPARTMENTS, *court_open_fastpath.SIX_MINISTRIES)
    startup_path = "references/court-normal-startup.md"
    with tempfile.TemporaryDirectory() as temp:
        source_fixture = Path(temp)
        source_paths = ["SKILL.md", "references/court-normal-startup.md", "references/manifests/court-dispatch-hierarchy.v1.json", *[f"agents/{folder}/{role}{suffix}" for role in source_roles for folder, suffix in (("standing-officials", ".toml"), ("office-dossiers", "/AGENTS.md"))]]
        for relative in source_paths:
            target = source_fixture / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((court_open_fastpath.ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8", newline="\r\n")
        startup_bytes = len((source_fixture / startup_path).read_text(encoding="utf-8").encode("utf-8"))
        with patch.object(Path, "read_bytes", side_effect=AssertionError("fastpath file rehash")):
            source_preloads = court_open_fastpath.load_preloads(source_fixture, source_roles, concurrent=False)
        (source_fixture / "SKILL.md").write_bytes(b"\xff")
        try: court_open_fastpath.load_preloads(source_fixture, (), concurrent=False)
        except court_open_fastpath.FastPathMiss as exc: assert exc.reason == "preload_unavailable"
        else: raise AssertionError("invalid preload accepted")
    source_preload_bytes = {
        role: {
            "loaded_bytes": source_preloads[role].loaded_bytes,
            "remaining_bytes": (
                court_open_fastpath.MINIMAL_PRELOAD_BYTES - source_preloads[role].loaded_bytes
            ),
        }
        for role in source_roles
    }
    source_preload_payloads = {
        role: court_open_fastpath._preload_payload(source_preloads[role])
        for role in source_roles
    }
    checks["source_preload_startup_contract"] = all(
        getattr(source_preloads[role], "startup_guide_path", None) == startup_path
        and getattr(source_preloads[role], "startup_guide_bytes", None) == startup_bytes
        and source_preloads[role].loaded_bytes
        == (
            source_preloads[role].skill_bytes
            + startup_bytes
            + source_preloads[role].dossier_bytes
            + source_preloads[role].profile_bytes
            + source_preloads[role].metadata_bytes
        )
        and source_preload_payloads[role].get("startup_guide_path") == startup_path
        and source_preload_payloads[role].get("startup_guide_bytes") == startup_bytes
        and startup_path in source_preload_payloads[role].get("verified_source_paths", [])
        for role in source_roles
    )
    assert checks["source_preload_startup_contract"], (
        "RolePreload/_role_preload/_preload_payload did not read, count, and verify "
        "the real startup guide"
    )
    checks["source_preload_target"] = (
        len(source_roles) == 9
        and set(source_preloads) == set(source_roles)
        and all(
            source_preloads[role].loaded_bytes <= court_open_fastpath.MINIMAL_PRELOAD_BYTES
            for role in source_roles
        )
    )
    checks["source_preload_margin"] = all(
        values["remaining_bytes"] >= SOURCE_PRELOAD_MARGIN_BYTES
        for values in source_preload_bytes.values()
    )
    with tempfile.TemporaryDirectory(prefix="court-open-fastpath-") as tmp_text:
        root = Path(tmp_text) / "skill"
        worktree = Path(tmp_text) / "worktree"
        root.mkdir()
        worktree.mkdir()
        _write_skill(root)
        request = _request(root, worktree)
        runtime = FakeRuntime(_task())
        first = court_open_fastpath.prepare_fast_open(
            request,
            runtime_api=runtime,
            identity_loader=_identity,
            concurrent_preload=concurrent_probes,
        )
        second = court_open_fastpath.prepare_fast_open(
            request,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=concurrent_probes,
        )
        checks["success"] = first.get("ok") is True
        precheck_runtime = FakeRuntime(_task())
        prechecked = court_open_fastpath.prepare_fast_open(
            {**request, "admission_precheck_requested": True},
            runtime_api=precheck_runtime, identity_loader=_identity,
            concurrent_preload=concurrent_probes,
        )
        checks["admission_precheck_public_parser"] = (
            prechecked.get("ok") is True and precheck_runtime.admission_calls == 3
            and prechecked.get("admission_check_count") == 3
            and prechecked.get("dispatch_count") == 0
        )
        derived = court_open_fastpath.prepare_fast_open(
            {**request, "case_ref": None, "semantic_receipt_id": None, "plan_ref": None},
            runtime_api=FakeRuntime(_task()), identity_loader=_identity,
            concurrent_preload=concurrent_probes,
        )
        receipt = _task()["semantic_receipt"]
        checks["current_references_derived"] = (
            derived.get("ok") is True and derived.get("case_ref") == receipt["case_ref"]
            and derived.get("semantic_receipt_id") == receipt["receipt_id"]
            and derived.get("mutations") == [] and derived.get("dispatch_count") == 0
        )
        for field, reason in (("case_ref", "case_ref_drift"), ("plan_ref", "plan_drift")):
            stale = court_open_fastpath.prepare_fast_open(
                {**request, field: {**receipt[field], "charter_revision": 2}},
                runtime_api=FakeRuntime(_task()), identity_loader=_identity,
                concurrent_preload=concurrent_probes,
            )
            checks[reason] = stale.get("status") == "FAST_PATH_MISS:" + reason
        checks["runtime_loaded_once"] = runtime.load_calls == 1
        checks["single_process"] = first.get("python_child_processes") == 0
        checks["no_partial_mutation"] = first.get("mutations") == []
        checks["exact_retry"] = (
            first.get("operation_id") == second.get("operation_id")
            and first.get("receipt_id") == second.get("receipt_id")
            and first.get("case_ref") == second.get("case_ref")
            and first.get("department_packets") == second.get("department_packets")
        )
        checks["three_departments"] = len(first.get("department_packets", [])) == 3
        checks["default_zero_ministries"] = (
            first.get("shangshu_ministry_packets") == []
            and first.get("shangshu_ministry_coordination") is None
            and first.get("planned_ministry_count") == 0
            and first.get("planned_office_count") == 3
            and first.get("admission_check_count") == 0
            and first.get("admission_precheck_requested") is False
            and first.get("agent_admission_satisfies_office_work") is False
            and len(first.get("preloads", [])) == 3
        )
        checks["preparation_never_claims_spawn"] = (
            first.get("preparation_only") is True
            and first.get("host_spawn_performed") is False
            and first.get("dispatch_count") == 0
            and first.get("physical_child_dispatch_count") == 0
            and all(
                packet.get("physical_child_agent_spawned") is False
                and packet.get("host_spawn_status") == "NOT_PERFORMED_PREPARATION_ONLY"
                for packet in first.get("department_packets", [])
            )
        )

        one_request = {**request, "ministry_assignments": ["gongbu"]}
        one_runtime = FakeRuntime(_task())
        one = court_open_fastpath.prepare_fast_open(
            one_request,
            runtime_api=one_runtime,
            identity_loader=_identity,
            concurrent_preload=concurrent_probes,
        )
        checks["one_ministry_assignment"] = (
            [packet.get("role") for packet in one.get("shangshu_ministry_packets", [])]
            == ["gongbu"]
            and one.get("planned_ministry_count") == 1
            and one.get("planned_office_count") == 4
            and one.get("admission_check_count") == 0
            and one_runtime.admission_calls == 0
            and one.get("dispatch_count") == 0
            and one.get("physical_child_dispatch_count") == 0
        )

        two_request = {**request, "ministry_assignments": ["hubu", "gongbu"]}
        two_runtime = FakeRuntime(_task())
        two = court_open_fastpath.prepare_fast_open(
            two_request,
            runtime_api=two_runtime,
            identity_loader=_identity,
            concurrent_preload=concurrent_probes,
        )
        checks["two_ministry_assignments"] = (
            [packet.get("role") for packet in two.get("shangshu_ministry_packets", [])]
            == ["hubu", "gongbu"]
            and two.get("planned_ministry_count") == 2
            and two.get("planned_office_count") == 5
            and two.get("admission_check_count") == 0
            and two_runtime.admission_calls == 0
            and len(two.get("preloads", [])) == 5
        )
        checks["ministry_superiors"] = all(
            packet["hierarchy"]["direct_superior"] == "shangshu"
            for packet in two.get("shangshu_ministry_packets", [])
        )
        coordination = two.get("shangshu_ministry_coordination")
        checks["shangshu_coordination_present"] = (
            isinstance(coordination, dict)
            and coordination.get("schema") == "court.shangshu_ministry_coordination.v1"
            and coordination.get("coordinator") == "shangshu"
            and coordination.get("behavior") == request["behavior"]
        )
        checks["shangshu_selects_ministries"] = (
            isinstance(coordination, dict)
            and coordination.get("selected_ministries") == ["hubu", "gongbu"]
            and coordination.get("selection_policy")
            == "bounded_ministries_selected_by_shangshu_after_taizi_reply"
        )
        checks["shangshu_prepares_ministry_children_without_dispatch"] = (
            isinstance(coordination, dict)
            and coordination.get("dispatch_initiator") is None
            and coordination.get("planned_dispatch_initiator") == "shangshu"
            and coordination.get("dispatch_target_kind") == "six_ministry_child_offices"
            and coordination.get("host_dispatch_performed") is False
            and coordination.get("dispatch_status") == "PREPARED_NOT_PERFORMED"
            and coordination.get("taizi_direct_ministry_dispatch_allowed") is False
        )
        checks["shangshu_integrates_ministries"] = (
            isinstance(coordination, dict)
            and coordination.get("integration_owner") == "shangshu"
            and coordination.get("evidence_return") == "shangshu_integrates_then_reports_to_taizi"
        )
        checks["ministry_admission_caller_is_shangshu"] = all(
            packet.get("admission") is None
            and packet.get("admission_status") == "NOT_REQUESTED_PREPARATION_ONLY"
            and packet.get("host_dispatch_required_for_done") is True
            for packet in two.get("shangshu_ministry_packets", [])
        )
        checks["ministry_binding_superior_is_shangshu"] = all(
            packet.get("hierarchy", {}).get("direct_superior") == "shangshu"
            for packet in two.get("shangshu_ministry_packets", [])
        )
        authority_gate = first.get("authority_selection_gate")
        checks["startup_authority_binding_only"] = (
            isinstance(authority_gate, dict)
            and authority_gate.get("schema") == "court.startup.authority_selection_gate.v1"
            and authority_gate.get("authority_source") == "explicit_latest_user"
            and authority_gate.get("source_policy")
            == "latest_explicit_or_current_question_or_same_conversation_same_boundary"
            and authority_gate.get("semantic_owner") == "SKILL.md"
            and authority_gate.get("selected_authority") == "super"
            and authority_gate.get("selected_behavior") == "parallel"
            and authority_gate.get("authority_behavior_orthogonal") is True
            and "prompt" not in authority_gate
            and "must_not_inherit_from" not in authority_gate
        )
        agent_hierarchy = two.get("agent_hierarchy")
        hierarchy_nodes = agent_hierarchy.get("nodes", []) if isinstance(agent_hierarchy, dict) else []
        ministry_parent_map = {
            node.get("role"): node.get("parent_role")
            for node in hierarchy_nodes
            if isinstance(node, dict) and node.get("role") in court_open_fastpath.SIX_MINISTRIES
        }
        checks["agent_tree_ministries_under_shangshu"] = (
            isinstance(agent_hierarchy, dict)
            and agent_hierarchy.get("schema") == "court.agent_hierarchy_tree.v1"
            and agent_hierarchy.get("six_ministry_parent") == "shangshu"
            and agent_hierarchy.get("six_ministries_are_shangshu_child_agents") is True
            and ministry_parent_map
            == {"hubu": "shangshu", "gongbu": "shangshu"}
            and agent_hierarchy.get("rendering_contract")
            == "render_six_ministries_nested_under_shangshu_not_as_taizi_siblings"
        )
        reuse_policy = first.get("agent_reuse_policy")
        checks["agent_reuse_policy_present"] = (
            isinstance(reuse_policy, dict)
            and reuse_policy.get("schema") == "court.agent.reuse_policy.v1"
            and reuse_policy.get("compatible_instance_policy") == "REUSE_FIRST"
            and reuse_policy.get("context_occupancy_limit") == 0.80
            and "context_occupancy_ratio >= 0.80" in reuse_policy.get("do_not_reuse_if", [])
        )
        reuse_candidate = {
            "status": "running",
            "role": "gongbu",
            "direct_superior": "shangshu",
            "context_occupancy_ratio": 0.42,
            "task_relation": "related",
        }
        checks["agent_reuse_decision_reuses_related_live"] = (
            court_open_fastpath.evaluate_agent_reuse_candidate(
                reuse_candidate,
                {"role": "gongbu", "direct_superior": "shangshu", "next_task_relation": "related"},
            ).get("decision")
            == "REUSE"
        )
        checks["agent_reuse_decision_blocks_80_percent_context"] = (
            court_open_fastpath.evaluate_agent_reuse_candidate(
                {**reuse_candidate, "context_occupancy_ratio": 0.80},
                {"role": "gongbu", "direct_superior": "shangshu", "next_task_relation": "related"},
            ).get("reason_codes")
            == ["context_occupancy_at_or_above_80_percent"]
        )
        checks["agent_reuse_decision_blocks_unrelated_task"] = (
            court_open_fastpath.evaluate_agent_reuse_candidate(
                reuse_candidate,
                {"role": "gongbu", "direct_superior": "shangshu", "next_task_relation": "unrelated"},
            ).get("reason_codes")
            == ["next_task_unrelated"]
        )
        checks["agent_reuse_decision_allows_fresh_large_parallel"] = (
            court_open_fastpath.evaluate_agent_reuse_candidate(
                reuse_candidate,
                {
                    "role": "gongbu",
                    "direct_superior": "shangshu",
                    "next_task_relation": "related",
                    "large_scale_parallel": True,
                    "performance_allows_fresh_instance": True,
                },
            ).get("reason_codes")
            == ["large_scale_parallel_fresh_instance_preferred"]
        )
        checks["preload_target"] = all(
            preload.get("target_met") is True for preload in first.get("preloads", [])
        )
        checks["compact_metadata"] = all(
            isinstance(preload.get("metadata_bytes"), int)
            and preload["metadata_bytes"] > 0
            and preload.get("metadata", {}).get("registry_policy") == "registry-first"
            and "references/manifests/court-dispatch-hierarchy.v1.json"
            in preload.get("verified_source_paths", [])
            and preload.get("preload_evidence_kind") == "dispatcher_source_validation"
            and preload.get("child_preload_ack_status") == "NOT_AVAILABLE_PRE_SPAWN"
            for preload in first.get("preloads", [])
        )

        no_probe_request = dict(request)
        no_probe_request.pop("expected_branch")
        no_probe_request.pop("expected_head")
        original_capability_resolver = court_open_fastpath.resolve_capability_snapshot

        def forbidden_identity(_path: Path) -> tuple[dict[str, object], list[list[str]]]:
            raise AssertionError("default preparation attempted a Git probe")

        def forbidden_capability(*_args: object, **_kwargs: object) -> tuple[dict[str, object], str, float]:
            raise AssertionError("default preparation attempted a capability probe")

        court_open_fastpath.resolve_capability_snapshot = forbidden_capability
        try:
            no_probe = court_open_fastpath.prepare_fast_open(
                no_probe_request,
                runtime_api=FakeRuntime(_task()),
                identity_loader=forbidden_identity,
                concurrent_preload=False,
            )
        finally:
            court_open_fastpath.resolve_capability_snapshot = original_capability_resolver
        checks["capability_and_git_checks_are_opt_in"] = (
            no_probe.get("ok") is True
            and no_probe.get("git_check_requested") is False
            and no_probe.get("worktree", {}).get("status") == "NOT_REQUESTED"
            and no_probe.get("process_audit") == []
            and no_probe.get("capability_check_requested") is False
            and no_probe.get("capability_cache_status") == "NOT_REQUESTED"
            and no_probe.get("capability_snapshot", {}).get("status") == "NOT_REQUESTED"
        )

        capacity = dict(request)
        capacity["host_capacity"] = 2
        capacity_miss = court_open_fastpath.prepare_fast_open(
            capacity,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        checks["capacity_miss"] = capacity_miss.get("status") == "FAST_PATH_MISS:capacity_insufficient"

        overlap = dict(request)
        overlap["write_sets"] = {"zhongshu": ["shared.txt"], "menxia": ["shared.txt"]}
        overlap_miss = court_open_fastpath.prepare_fast_open(
            overlap,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        checks["overlap_miss"] = overlap_miss.get("status") == "FAST_PATH_MISS:write_set_overlap"

        stale = dict(request)
        stale["semantic_receipt_id"] = "SR-OTHER-RECEIPT"
        stale_miss = court_open_fastpath.prepare_fast_open(
            stale,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        checks["semantic_miss"] = stale_miss.get("status") == "FAST_PATH_MISS:semantic_receipt_drift"

        missing_authority_source = dict(request)
        missing_authority_source.pop("authority_source")
        try:
            court_open_fastpath.prepare_fast_open(
                missing_authority_source,
                runtime_api=FakeRuntime(_task()),
                identity_loader=_identity,
                concurrent_preload=False,
            )
        except court_open_fastpath.FastPathInvalid as exc:
            checks["authority_source_required"] = str(exc) == "authority_source_required"
        else:
            checks["authority_source_required"] = False

        serial = dict(request)
        serial["behavior"] = "serial"
        serial_result = court_open_fastpath.prepare_fast_open(
            serial,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        serial_packets = (
            serial_result.get("department_packets", [])
            + serial_result.get("shangshu_ministry_packets", [])
        )
        checks["serial_preserves_office_duties_without_child_spawn"] = (
            serial_result.get("ok") is True
            and serial_result.get("dispatch_count") == 0
            and serial_result.get("physical_child_dispatch_count") == 0
            and serial_result.get("planned_office_count") == 3
            and serial_result.get("admission_check_count") == 0
            and serial_result.get("serial_office_duty_count") == 3
            and all(
                packet.get("serial_action") == "serial_inline_office_duty"
                and packet.get("office_duty_preserved") is True
                and packet.get("physical_child_agent_spawned") is False
                for packet in serial_packets
            )
        )

        wrong_root = Path(tmp_text) / "wrong-skill"
        wrong_root.mkdir()
        _write_skill(wrong_root, wrong_ministry="gongbu")
        unselected_wrong = {**request, "skill_root": str(wrong_root)}
        unselected_result = court_open_fastpath.prepare_fast_open(
            unselected_wrong,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        selected_wrong = {
            **unselected_wrong,
            "ministry_assignments": ["gongbu"],
        }
        wrong_miss = court_open_fastpath.prepare_fast_open(
            selected_wrong,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        checks["unselected_broken_profile_not_loaded"] = (
            unselected_result.get("ok") is True
            and [preload.get("role") for preload in unselected_result.get("preloads", [])]
            == list(court_open_fastpath.THREE_DEPARTMENTS)
        )
        checks["selected_broken_profile_fails_atomically"] = (
            wrong_miss.get("status") == "FAST_PATH_MISS:hierarchy_incomplete"
            and wrong_miss.get("mutations") == []
        )

        invalid_ministry = {**request, "ministry_assignments": ["not-a-ministry"]}
        duplicate_ministry = {**request, "ministry_assignments": ["gongbu", "gongbu"]}
        bounded_errors: list[str] = []
        for candidate in (invalid_ministry, duplicate_ministry):
            try:
                court_open_fastpath.normalize_request(candidate)
            except court_open_fastpath.FastPathInvalid as exc:
                bounded_errors.append(str(exc))
        checks["ministry_assignments_are_bounded"] = bounded_errors == [
            "ministry_assignment_invalid:not-a-ministry",
            "ministry_assignments_duplicate",
        ]

        large_root = Path(tmp_text) / "large-skill"
        large_root.mkdir()
        _write_skill(large_root, oversized=True)
        large = dict(request)
        large["skill_root"] = str(large_root)
        large_miss = court_open_fastpath.prepare_fast_open(
            large,
            runtime_api=FakeRuntime(_task()),
            identity_loader=_identity,
            concurrent_preload=False,
        )
        checks["preload_budget_miss"] = large_miss.get("status") == "FAST_PATH_MISS:preload_budget_exceeded"
        source_text = Path(court_open_fastpath.__file__).read_text(encoding="utf-8")
        checks["production_capability_not_checker_import"] = (
            "check_capability_index_gate" not in source_text
        )
        checks["legacy_include_ministries_path_removed"] = (
            "include_shangshu_ministries" not in source_text
        )

    for name, passed in checks.items():
        if passed is not True:
            problems.append(name)
    fast_gate = all(
        checks.get(name) is True
        for name in (
            "success",
            "runtime_loaded_once",
            "single_process",
            "no_partial_mutation",
            "capacity_miss",
            "overlap_miss",
            "semantic_miss",
            "authority_source_required",
            "default_zero_ministries",
            "preparation_never_claims_spawn",
            "capability_and_git_checks_are_opt_in",
            "serial_preserves_office_duties_without_child_spawn",
            "source_preload_target",
            "source_preload_margin",
            "preload_budget_miss",
            "compact_metadata",
            "production_capability_not_checker_import",
            "legacy_include_ministries_path_removed",
            "request_template_schema_and_required_fields",
            "request_template_unknown_fails_closed",
            "request_template_known_facts_normalize_without_prepare",
            "request_template_authority_source_and_single_office",
            "request_template_authority_source_parser_rejects_invalid",
            "request_template_sources_are_exclusive",
            "request_template_existing_request_sources_unchanged",
        )
    )
    shangshu_gate = all(
        checks.get(name) is True
        for name in (
            "one_ministry_assignment",
            "two_ministry_assignments",
            "ministry_superiors",
            "shangshu_coordination_present",
            "shangshu_selects_ministries",
            "shangshu_prepares_ministry_children_without_dispatch",
            "shangshu_integrates_ministries",
            "ministry_admission_caller_is_shangshu",
            "ministry_binding_superior_is_shangshu",
            "startup_authority_binding_only",
            "agent_tree_ministries_under_shangshu",
            "agent_reuse_policy_present",
            "agent_reuse_decision_reuses_related_live",
            "agent_reuse_decision_blocks_80_percent_context",
            "agent_reuse_decision_blocks_unrelated_task",
            "agent_reuse_decision_allows_fresh_large_parallel",
            "unselected_broken_profile_not_loaded",
            "selected_broken_profile_fails_atomically",
            "ministry_assignments_are_bounded",
            "exact_retry",
        )
    )
    ok = shangshu_gate if shangshu_only else fast_gate and shangshu_gate and not problems
    return {
        "schema": "court.open.fast.check.v1",
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "FAST_OPEN_SINGLE_PROCESS": "PASS" if fast_gate else "FAIL",
        "SHANGSHU_FIRST_DISPATCH": "PASS" if shangshu_gate else "FAIL",
        "SIX_MINISTRY_DIRECT_SUPERIOR": "PASS" if checks.get("ministry_superiors") is True else "FAIL",
        "checks": checks,
        "source_preload_bytes": source_preload_bytes,
        "problems": problems,
        "pending_body_access": "NO",
    }


def check_runtime_selection_has_no_profile_io() -> dict[str, object]:
    """Selecting a runtime must not inventory every office before admission."""
    from unittest.mock import patch
    import court_native_execution
    import court_supercc_execution
    accessed: list[str] = []

    def unexpected_read(path: Path, *_args: object, **_kwargs: object) -> None:
        accessed.append(str(path))
        raise AssertionError("runtime_selection_read_office_content:" + str(path))

    with tempfile.TemporaryDirectory(prefix="runtime-pointer-only-") as temp_text:
        with patch.object(Path, "read_text", unexpected_read), patch.object(Path, "read_bytes", unexpected_read), patch.object(Path, "glob", unexpected_read):
            native = court_native_execution.select_native_execution(authority="super", behavior="parallel", root=Path(temp_text)).as_dict()
            supercc = court_supercc_execution.select_supercc_execution(authority="super", behavior="parallel", root=Path(temp_text)).as_dict()
    assert not accessed, "runtime selection read profiles before an office was selected"
    assert native["office_config"] == supercc["office_config"], "neutral pointer diverged across runtimes"
    assert native["office_config"]["path"] == "references/manifests/court-dispatch-hierarchy.v1.json", "neutral hierarchy pointer lost"
    return {"ok": True, "profile_io_count": len(accessed), "runtime_count": 2}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shangshu", action="store_true")
    parser.add_argument("--serial-probes", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = run_checks(
        shangshu_only=args.shangshu,
        concurrent_probes=not args.serial_probes,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        for gate in (
            "FAST_OPEN_SINGLE_PROCESS",
            "SHANGSHU_FIRST_DISPATCH",
            "SIX_MINISTRY_DIRECT_SUPERIOR",
        ):
            print(f"{gate}={result[gate]}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
