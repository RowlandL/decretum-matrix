"""Focused contract checks for the standard session case binding."""

from __future__ import annotations

from argparse import Namespace
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import unittest


sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from court_case_binding import (  # noqa: E402
    build_case_binding,
    case_reference,
    plan_reference,
    refresh_case_binding,
    validate_case_binding,
)
import archive_runtime_task  # noqa: E402
import archive_checkpoint  # noqa: E402
import court_runtime  # noqa: E402
from court_intake_gate import minimal_request_understanding_example  # noqa: E402
from court_session_numbering import resolve_session_allocation  # noqa: E402


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def plan(task_id: str, court_code: str, revision: int = 1) -> dict[str, object]:
    return {
        "schema": "court.zhongshu_plan.v1",
        "task_id": task_id,
        "court_code": court_code,
        "charter_revision": 1,
        "plan_id": f"PLAN-{task_id}-r{revision}",
        "revision": revision,
        "document": {"goal": "fixture"},
        "producer": {"kind": "serial_inline", "role": "zhongshu", "agent_id": ""},
    }


def task_fixture() -> tuple[dict[str, object], dict[str, object]]:
    task_id = "case-binding-fixture"
    court_code = "CCR-20260906-1-ABCD"
    current_plan = plan(task_id, court_code)
    reviews = {
        "menxia": {
            "schema": "court.plan_review.v1",
            "role": "menxia",
            "task_id": task_id,
            "court_code": court_code,
            "charter_revision": 1,
            "plan_revision": current_plan["revision"],
            "review_id": "REV-MENXIA-1",
            "producer": {"kind": "serial_inline", "role": "menxia", "agent_id": ""},
        },
        "shangshu": {
            "schema": "court.plan_review.v1",
            "role": "shangshu",
            "task_id": task_id,
            "court_code": court_code,
            "charter_revision": 1,
            "plan_revision": current_plan["revision"],
            "review_id": "REV-SHANGSHU-1",
            "producer": {"kind": "serial_inline", "role": "shangshu", "agent_id": ""},
        },
    }
    task: dict[str, object] = {
        "task_id": task_id,
        "session_id": "case-binding-session",
        "court_code": court_code,
        "charter_revision": 1,
        "case_execution": {"authority": "super", "behavior": "serial"},
        "zhongshu_plan": current_plan,
        "case_reviews": reviews,
    }
    allocation: dict[str, object] = {
        "schema": "court.session_court_code_allocation.v1",
        "session_id": "case-binding-session",
        "date": "20260906",
        "daily_sequence": "1",
        "court_code": "CCR-20260906-1-ABCD",
    }
    return task, allocation


class CaseBindingTests(unittest.TestCase):
    def test_canonical_binding_covers_identity_execution_plan_and_reviews(self) -> None:
        task, allocation = task_fixture()
        binding = build_case_binding(task, allocation)
        task["case_binding"] = binding
        validated = validate_case_binding(binding, task, allocation=allocation)
        self.assertEqual(validated, binding)
        self.assertEqual(binding["session_id"], allocation["session_id"])
        self.assertEqual(binding["court_code"], allocation["court_code"])
        self.assertEqual(case_reference(binding), case_reference(task))
        self.assertEqual(binding["case_execution"], task["case_execution"])
        self.assertEqual(binding["zhongshu_plan"], {
            "plan_id": task["zhongshu_plan"]["plan_id"],
            "revision": task["zhongshu_plan"]["revision"],
        })
        self.assertEqual(set(binding["case_reviews"]), {"menxia", "shangshu"})

    def test_refresh_requires_a_real_plan_and_rebinds_dynamic_summaries(self) -> None:
        task, allocation = task_fixture()
        task["case_binding"] = build_case_binding(task, allocation)
        stable_reference = case_reference(task["case_binding"])
        changed = deepcopy(task)
        changed_plan = plan(str(changed["task_id"]), str(changed["court_code"]), revision=2)
        changed["zhongshu_plan"] = changed_plan
        changed["case_reviews"] = {}
        with self.assertRaisesRegex(ValueError, "case_binding"):
            validate_case_binding(changed["case_binding"], changed)
        rebound = refresh_case_binding(changed)
        changed["case_binding"] = rebound
        validate_case_binding(rebound, changed)
        self.assertEqual(case_reference(rebound), stable_reference)
        self.assertEqual(rebound["zhongshu_plan"]["revision"], 2)
        self.assertEqual(rebound["case_reviews"], {})

        capsule = deepcopy(changed)
        capsule["zhongshu_plan"] = {"schema": "court.semantic.invariant_capsule.v1"}
        with self.assertRaisesRegex(ValueError, "case_binding_plan"):
            refresh_case_binding(capsule)

    def test_foreign_allocation_and_execution_drift_are_rejected_without_mutation(self) -> None:
        task, allocation = task_fixture()
        binding = build_case_binding(task, allocation)
        task["case_binding"] = binding
        original = deepcopy(task)
        foreign = {**allocation, "session_id": "other-session"}
        with self.assertRaisesRegex(ValueError, "case_binding"):
            validate_case_binding(binding, task, allocation=foreign)
        foreign_code = {**allocation, "court_code": "CCR-20260906-1-ZZZZ"}
        with self.assertRaisesRegex(ValueError, "case_binding"):
            validate_case_binding(binding, task, allocation=foreign_code)
        task["case_execution"] = {"authority": "approval", "behavior": "serial"}
        with self.assertRaisesRegex(ValueError, "case_binding"):
            validate_case_binding(binding, task)
        self.assertEqual(original["case_binding"], binding)


def formal_gate() -> dict[str, object]:
    return {
        "schema": "court.conversation_gate.v1",
        "active_decree": False,
        "active_decree_state": "NONE",
        "message_class": "FORMAL_TASK",
        "confidence": "HIGH",
        "relation_to_active_decree": "NONE",
        "taskization_consent": "EXPLICIT",
        "requires_tools": True,
        "mutates_state": True,
        "risk_present": False,
        "next_route": "THREE_DEPARTMENTS",
        "question": "",
        "rationale": "case binding focused fixture",
        "understanding": minimal_request_understanding_example(),
    }


def standard_create_args(task_id: str, session_id: str) -> Namespace:
    return Namespace(
        task_id=task_id,
        title="standard case fixture",
        charter="standard case charter",
        work_kind="implementation",
        intake_gate=formal_gate(),
        intake_file=None,
        invariant_capsule=None,
        invariant_capsule_file=None,
        owner="taizi",
        report_tier="standard",
        evidence="case create fixture",
        note="case create fixture",
        session_id=session_id,
        authority="super",
        behavior="serial",
    )


def reviewed_plan(task: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    document = {
        "goal": "verify canonical case binding",
        "non_goals": ["no external writes"],
        "steps": [{"id": "verify", "role": "xingbu", "action": "verify case fields"}],
        "acceptance": ["archive identity is exact"],
        "write_set": [],
    }
    plan: dict[str, object] = {
        "schema": "court.zhongshu_plan.v1",
        "task_id": task["task_id"],
        "court_code": task["court_code"],
        "charter_revision": task["charter_revision"],
        "plan_id": "PLAN-CASE-BINDING-r1",
        "revision": 1,
        "document": document,
        "producer": {
            "kind": "serial_inline",
            "role": "zhongshu",
            "agent_id": "",
            "evidence": "serial_inline://fixture/zhongshu",
        },
    }
    reviews: dict[str, object] = {}
    for role, decision in (("menxia", "approved"), ("shangshu", "dispatchable")):
        review: dict[str, object] = {
            "schema": "court.plan_review.v1",
            "role": role,
            "decision": decision,
            "task_id": task["task_id"],
            "court_code": task["court_code"],
            "charter_revision": task["charter_revision"],
            "plan_revision": plan["revision"],
            "review_id": f"REV-CASE-BINDING-{role}",
            "producer": {
                "kind": "serial_inline",
                "role": role,
                "agent_id": "",
                "evidence": f"serial_inline://fixture/{role}",
            },
        }
        reviews[role] = review
    return plan, reviews


class StandardCaseRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original_runtime_root = court_runtime.runtime_root
        self.original_environment = {
            key: os.environ.get(key)
            for key in ("COURT_SHARED_SHIGUAN_ROOT", "COURT_RUNTIME_ROOT", "HOME", "USERPROFILE")
        }
        court_runtime.runtime_root = lambda: self.root / "runtime"  # type: ignore[assignment]
        os.environ.update(
            {
                "COURT_SHARED_SHIGUAN_ROOT": str(self.root / "shared"),
                "COURT_RUNTIME_ROOT": str(self.root / "runtime"),
                "HOME": str(self.root / "home"),
                "USERPROFILE": str(self.root / "home"),
            }
        )

    def tearDown(self) -> None:
        court_runtime.runtime_root = self.original_runtime_root  # type: ignore[assignment]
        for key, value in self.original_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp.cleanup()

    def _persist(self, task: dict[str, object]) -> dict[str, object]:
        tasks = court_runtime.load_tasks()
        tasks[str(task["task_id"])] = task
        court_runtime.write_tasks(tasks)
        return court_runtime.load_tasks()[str(task["task_id"])]

    def test_standard_session_create_is_idempotent_and_cross_day_safe(self) -> None:
        parsed = court_runtime.build_parser().parse_args(
            [
                "create",
                "--title", "standard case fixture",
                "--charter", "standard case charter",
                "--task-id", "parser-case",
                "--session-id", "parser-session",
                "--authority", "super",
                "--behavior", "serial",
                "--work-kind", "implementation",
                "--intake-file", "fixture-intake.json",
            ]
        )
        self.assertEqual(
            (parsed.session_id, parsed.authority, parsed.behavior),
            ("parser-session", "super", "serial"),
        )
        args = standard_create_args("case-create", "case-create-session")
        first = court_runtime.create_task(args)
        self.assertEqual(first.task["session_id"], "case-create-session")
        self.assertEqual(first.task["case_execution"], {"authority": "super", "behavior": "serial"})
        self.assertEqual(first.task["case_bootstrap"]["plan_status"], "BOOTSTRAP_UNPLANNED")
        self.assertEqual(first.task["case_binding"]["court_code"], first.task["court_code"])
        self.assertTrue(first.task["decree_id"])
        self.assertEqual(first.task["main_court_code"], first.task["court_code"])
        decree_receipt = next(iter(first.task["operations"].values()))["receipt"]
        self.assertEqual(
            decree_receipt["case_ref"],
            case_reference(first.task),
        )
        before_tasks = court_runtime.tasks_path().read_bytes()
        before_events = court_runtime.events_path().read_bytes()
        replay = court_runtime.create_task(standard_create_args("case-create", "case-create-session"))
        self.assertEqual(replay.task, first.task)
        self.assertEqual(court_runtime.tasks_path().read_bytes(), before_tasks)
        self.assertEqual(court_runtime.events_path().read_bytes(), before_events)

        with self.assertRaisesRegex(ValueError, "case_create_session_task_conflict"):
            court_runtime.create_task(standard_create_args("other-task", "case-create-session"))
        self.assertEqual(court_runtime.tasks_path().read_bytes(), before_tasks)
        self.assertEqual(court_runtime.events_path().read_bytes(), before_events)
        cross_day = resolve_session_allocation("case-create-session", "20990101")
        self.assertIsInstance(cross_day, dict)
        self.assertEqual(cross_day["court_code"], first.task["court_code"])

        invalid = standard_create_args("missing-authority", "missing-authority-session")
        invalid.authority = ""
        with self.assertRaisesRegex(ValueError, "case_create_authority_required"):
            court_runtime.create_task(invalid)

        concurrent_args = standard_create_args("case-concurrent", "case-concurrent-session")
        results: list[object] = []
        failures: list[BaseException] = []

        def create_in_thread() -> None:
            try:
                results.append(court_runtime.create_task(Namespace(**vars(concurrent_args))))
            except BaseException as exc:  # pragma: no cover - asserted below
                failures.append(exc)

        threads = [threading.Thread(target=create_in_thread) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(failures)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].task["case_binding"], results[1].task["case_binding"])
        create_events = [
            event for event in court_runtime.events_for_task("case-concurrent", limit=None)
            if event.get("action") == "create"
        ]
        self.assertEqual(len(create_events), 1)

    def test_standard_create_recovers_after_decree_allocation_crash_without_reissuing(self) -> None:
        original_decree_open = court_runtime.decree_open_task
        calls = {"count": 0}

        def crash_after_allocation(args: Namespace) -> dict[str, object]:
            calls["count"] += 1
            if calls["count"] == 1:
                injected = Namespace(**vars(args))
                injected.killpoint = "after_allocation"
                return original_decree_open(injected)
            return original_decree_open(args)

        court_runtime.decree_open_task = crash_after_allocation  # type: ignore[assignment]
        try:
            with self.assertRaises(court_runtime.SimulatedDecreeOpenCrash):
                court_runtime.create_task(
                    standard_create_args("case-crash", "case-crash-session")
                )
        finally:
            court_runtime.decree_open_task = original_decree_open  # type: ignore[assignment]
        interrupted = court_runtime.load_tasks()["case-crash"]
        allocation_before = resolve_session_allocation("case-crash-session", "20990101")
        self.assertIsInstance(allocation_before, dict)
        self.assertEqual(interrupted["main_court_code"], allocation_before["court_code"])
        operation = next(iter(interrupted["operations"].values()))
        self.assertEqual(operation["status"], "ALLOCATED")

        recovered = court_runtime.create_task(
            standard_create_args("case-crash", "case-crash-session")
        )
        allocation_after = resolve_session_allocation("case-crash-session", "20990101")
        self.assertEqual(allocation_after, allocation_before)
        self.assertEqual(recovered.task["court_code"], allocation_before["court_code"])
        recovered_operation = next(iter(recovered.task["operations"].values()))
        self.assertEqual(recovered_operation["status"], "COMMITTED")
        decree_events = [
            event for event in court_runtime.events_for_task("case-crash", limit=None)
            if event.get("action") == "decree_open"
        ]
        self.assertEqual(len(decree_events), 1)

    def test_decree_archive_and_record_reject_foreign_binding_without_runtime_writes(self) -> None:
        from check_court_runtime_completion import assessment

        task = court_runtime.create_task(
            standard_create_args("case-archive", "case-archive-session")
        ).task
        issued = resolve_session_allocation("case-archive-session", "20990101")
        self.assertIsInstance(issued, dict)
        self.assertEqual(task["decree_id"], task["operations"][next(iter(task["operations"]))]["receipt"]["decree_id"])
        self.assertEqual(task["main_court_code"], issued["court_code"])
        task["state"] = "MenxiaReview"
        task["evidence_sha256"] = "e" * 64
        plan_value, reviews = reviewed_plan(task)
        task["zhongshu_plan"] = plan_value
        task["case_reviews"] = reviews
        task["case_binding"] = refresh_case_binding(task)
        task = court_runtime.bind_assessment_record(task, assessment(task))
        self._persist(task)
        task = court_runtime.load_tasks()["case-archive"]
        args = Namespace(
            task_id="case-archive",
            topic="",
            phase="case archive fixture",
            status="",
            next="",
            memory_decision="SKIP",
            memory_content="",
            memory_reason="",
            event_limit=8,
        )
        preflight = court_runtime.record_shiguan_preflight(
            archive_runtime_task._record_args(task, {"preflight": "not-used"})
        )
        self.assertEqual(preflight["court_code"], issued["court_code"])
        command = archive_runtime_task.build_archive_command(task, args)
        self.assertEqual(command[command.index("--session-id") + 1], "case-archive-session")
        self.assertIn("--case-binding-json", command)
        produced = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(produced.returncode, 0, produced.stderr)
        producer_receipt = json.loads(produced.stdout)
        self.assertEqual(producer_receipt["case_ref"], case_reference(task))
        self.assertEqual(producer_receipt["case_binding"], task["case_binding"])

        bad_binding = deepcopy(task["case_binding"])
        bad_binding["court_code"] = str(bad_binding["court_code"])[:-4] + "ZZZZ"
        index_path = self.root / "shared" / "references" / "shiguan-index.jsonl"
        archive_path = Path(str(producer_receipt["path"]))
        before_index = index_path.read_bytes()
        before_archive = archive_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "archive_case_binding_allocation_foreign"):
            archive_checkpoint.append_checkpoint(
                Namespace(
                    topic="blocked foreign binding",
                    session_id=task["session_id"],
                    case_binding=bad_binding,
                    phase="case archive fixture",
                    status="PASSED",
                    summary="blocked fixture",
                    evidence="blocked fixture",
                    next="none",
                    memory_decision="SKIP",
                    memory_content="none",
                    memory_reason="fixture",
                    residual_gaps_json="",
                    residual_gaps_sha256="",
                    risk_level=None,
                    knowledge_value=None,
                    priority_level=None,
                    keywords="",
                    key_actions="",
                    source_agent=None,
                    full_record=None,
                    full_record_file=None,
                    lock_timeout=1.0,
                )
            )
        self.assertEqual(index_path.read_bytes(), before_index)
        self.assertEqual(archive_path.read_bytes(), before_archive)

        before_tasks = court_runtime.tasks_path().read_bytes()
        before_events = court_runtime.events_path().read_bytes()
        for field, value in (
            ("task_id", "foreign-task"),
            ("session_id", "foreign-session"),
            ("court_code", "CCR-20260906-1-ZZZZ"),
            ("charter_revision", 999),
            ("case_ref", {"court_code": "CCR-20260906-1-ZZZZ", "charter_revision": task["charter_revision"]}),
            ("case_binding", bad_binding),
            ("missing", None),
        ):
            bad_receipt = deepcopy(producer_receipt)
            if field == "missing":
                bad_receipt.pop("session_id")
            else:
                bad_receipt[field] = value
            with self.assertRaises(ValueError):
                court_runtime.record_shiguan_task(archive_runtime_task._record_args(task, bad_receipt))
            self.assertEqual(court_runtime.tasks_path().read_bytes(), before_tasks)
            self.assertEqual(court_runtime.events_path().read_bytes(), before_events)

        recorded = court_runtime.record_shiguan_task(
            archive_runtime_task._record_args(task, producer_receipt)
        )
        self.assertEqual(recorded.task["state"], "ShiguanRecorded")
        self.assertEqual(recorded.task["shiguan_checkpoint"]["case_ref"], case_reference(task))
        replayed = archive_runtime_task.archive_and_record_task(args)
        self.assertEqual(replayed["status"], "REPLAYED")

    def test_case_concerns_require_assessment_gaps_before_producer_writes(self) -> None:
        from check_court_runtime_completion import assessment

        task = court_runtime.create_task(standard_create_args('case-concerns', 'case-concerns-session')).task
        task.update(state='MenxiaReview', evidence_sha256='e' * 64)
        task['zhongshu_plan'], task['case_reviews'] = reviewed_plan(task)
        task['case_binding'] = refresh_case_binding(task)
        gaps = ['fixture outstanding concern']
        task = court_runtime.bind_assessment_record(task, assessment(task, gate='PASSED_WITH_CONCERNS', reasons=gaps, residual_gaps=gaps))
        task = self._persist(task)
        args = Namespace(task_id=task['task_id'], topic='', phase='fixture', status='', next='',
                         memory_decision='SKIP', memory_content='', memory_reason='', event_limit=8)
        preflight_args = archive_runtime_task._record_args(task, {})
        old_shape = court_runtime.record_shiguan_preflight(preflight_args)
        expanded = court_runtime.record_shiguan_preflight(preflight_args, include_residual_gaps=True)
        self.assertNotIn('residual_gaps', old_shape)  # Preserve prior receipt-cache keys.
        self.assertEqual(expanded['residual_gaps'], gaps)
        command = archive_runtime_task.build_archive_command(task, args) + ['--refresh-mode', 'none']
        invalid = list(command)
        invalid[invalid.index('--residual-gaps-json') + 1] = '[]'
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        rejected = subprocess.run(invalid, capture_output=True, encoding='utf-8', timeout=30)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('archive_runtime_assessment_or_residual_gaps_mismatch', rejected.stdout + rejected.stderr)
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        produced = subprocess.run(command, capture_output=True, encoding='utf-8', timeout=30)
        self.assertEqual(produced.returncode, 0, produced.stdout + produced.stderr)
        receipt = json.loads(produced.stdout)
        self.assertEqual(receipt['residual_gaps'], gaps)
        recorded = court_runtime.record_shiguan_task(archive_runtime_task._record_args(task, receipt))
        self.assertEqual(recorded.task['state'], 'ShiguanRecorded')


if __name__ == "__main__":
    unittest.main()
