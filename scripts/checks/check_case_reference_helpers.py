"""Small reference helpers used by normal court protocol fields."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from court_case_binding import (  # noqa: E402
    build_case_binding,
    case_reference,
    office_capsule_reference,
    plan_reference,
)
from court_plan_artifacts import submit_plan  # noqa: E402
from court_semantic_continuity import (  # noqa: E402
    build_semantic_receipt,
    invariant_capsule_template,
    normalize_semantic_context,
    semantic_binding_for_revision,
    verify_semantic_receipt,
)
from court_semantic_continuity import validate_dispatch_context_packet  # noqa: E402
from court_semantic_continuity import (  # noqa: E402
    normalize_consultation_refs,
    normalize_result_envelope,
    result_binding_problems,
)


class CaseReferenceHelperTests(unittest.TestCase):
    def test_case_plan_and_office_references_keep_existing_identities(self) -> None:
        task = {
            "task_id": "existing-local-alias",
            "court_code": "SCOS-20260906-1-NDAA",
            "charter_revision": 2,
            "zhongshu_plan": {"revision": 3},
        }
        case_ref = {"court_code": "SCOS-20260906-1-NDAA", "charter_revision": 2}

        self.assertEqual(case_reference(task), case_ref)
        self.assertEqual(plan_reference(task), {**case_ref, "plan_revision": 3})
        self.assertEqual(
            office_capsule_reference(case_ref, "libu-hr", "libu-hr#0001", "2026-09-06T07:04:27+08:00"),
            {
                "capsule_id": "SCOS-20260906-1-NDAA-0704LBH",
                "case_ref": case_ref,
                "office_instance_id": "libu-hr#0001",
                "role_key": "libu-hr",
                "issued_at": "2026-09-06T07:04:27+08:00",
            },
        )

    def test_binding_keeps_business_fields_without_identity_digests(self) -> None:
        task = {
            "task_id": "existing-local-alias",
            "session_id": "host-session",
            "court_code": "SCOS-20260906-1-NDAA",
            "charter_revision": 2,
            "charter_sha256": "a" * 64,
            "case_execution": {"authority": "autonomous", "behavior": "serial"},
            "zhongshu_plan": None,
            "case_reviews": {},
        }
        allocation = {
            "schema": "court.session_court_code_allocation.v1",
            "session_id": "host-session",
            "date": "20260906",
            "daily_sequence": "1",
            "court_code": "SCOS-20260906-1-NDAA",
        }

        binding = build_case_binding(task, allocation)

        self.assertEqual(binding["task_id"], "existing-local-alias")
        self.assertEqual(binding["session_id"], "host-session")
        self.assertEqual(binding["case_execution"], task["case_execution"])
        self.assertEqual(binding["charter_revision"], 2)
        self.assertFalse(any("sha256" in str(key).lower() for key in binding))

    def test_plan_keeps_existing_business_shape_without_digest_references(self) -> None:
        task = {
            "task_id": "existing-local-alias",
            "court_code": "SCOS-20260906-1-NDAA",
            "charter_revision": 2,
            "state": "ThreeDepartments",
            "case_execution": {"authority": "autonomous", "behavior": "serial"},
        }
        document = {
            "goal": "prepare the existing plan",
            "non_goals": [],
            "steps": [{"id": "step-1", "role": "gongbu", "action": "prepare"}],
            "acceptance": ["reviewed"],
            "write_set": [],
        }

        planned = submit_plan(
            task,
            document,
            {"kind": "serial_inline", "agent_id": "", "evidence": "serial plan"},
            [],
        )

        plan = planned["zhongshu_plan"]
        self.assertEqual(plan["court_code"], "SCOS-20260906-1-NDAA")
        self.assertEqual(plan["charter_revision"], 2)
        self.assertEqual(plan["revision"], 1)
        self.assertFalse(any("sha256" in str(key).lower() for key in plan))

    def test_semantic_binding_uses_court_code_when_present(self) -> None:
        binding = semantic_binding_for_revision(
            "actual charter wording",
            2,
            invariant_capsule_template("actual charter wording"),
            court_code="SCOS-20260906-1-NDAA",
        )

        self.assertEqual(binding["court_code"], "SCOS-20260906-1-NDAA")
        self.assertEqual(binding["charter_revision"], 2)
        self.assertEqual(
            binding["invariant_capsule"]["case_ref"],
            {"court_code": "SCOS-20260906-1-NDAA", "charter_revision": 2},
        )
        self.assertEqual(
            binding["invariant_capsule"]["boundaries"], ["exact charter only"]
        )
        self.assertFalse(any("sha256" in str(key).lower() for key in binding))

    def test_normal_semantic_binding_rejects_missing_court_code(self) -> None:
        with self.assertRaisesRegex(ValueError, "court_code_required"):
            semantic_binding_for_revision("actual charter wording", 2)

    def test_normal_context_uses_case_and_plan_references(self) -> None:
        case_ref = {"court_code": "SCOS-20260906-1-NDAA", "charter_revision": 2}
        value = {
            "authority_revision": 2,
            "case_ref": case_ref,
            "plan_ref": None,
            "plan_cursor": "ThreeDepartments@revision-2",
            "recovery_checkpoint_id": "EVT-CREATE-1",
            "shiguan_revision": 0,
        }

        self.assertEqual(normalize_semantic_context(value), value)

    def test_normal_receipt_uses_case_reference_not_digest(self) -> None:
        capsule = invariant_capsule_template("actual charter wording")
        capsule["write_set"] = ["docs/plan.md"]
        task = semantic_binding_for_revision(
            "actual charter wording",
            2,
            capsule,
            court_code="SCOS-20260906-1-NDAA",
        )
        task.update(task_id="local-alias", charter="actual charter wording")
        context = {
            "authority_revision": 2,
            "case_ref": {"court_code": "SCOS-20260906-1-NDAA", "charter_revision": 2},
            "plan_ref": None,
            "plan_cursor": "ThreeDepartments@revision-2",
            "recovery_checkpoint_id": "EVT-CREATE-1",
            "shiguan_revision": 0,
        }

        receipt = build_semantic_receipt(
            task,
            context,
            event_head_id="EVT-CREATE-1",
            trigger="checkpoint",
            created_at="2026-09-06T08:00:00+08:00",
        )

        self.assertEqual(receipt["case_ref"], context["case_ref"])
        self.assertEqual(receipt["write_set"], ["docs/plan.md"])
        self.assertTrue(receipt["receipt_id"])
        self.assertFalse(any("sha256" in str(key).lower() for key in receipt))
        self.assertEqual(verify_semantic_receipt(task, receipt, context), [])

        packet = {
            "schema": "court.semantic.dispatch_context_packet.v1",
            "task_id": "local-alias",
            "sub_id": "wave-1",
            "semantic_epoch": 2,
            "case_ref": context["case_ref"],
            "plan_ref": None,
            "semantic_receipt_id": receipt["receipt_id"],
            "plan_cursor": context["plan_cursor"],
            "fork_context": "none",
            "context_mode": "bounded",
            "pointers": [{"path": "authority/current.md", "case_ref": context["case_ref"]}],
            "summary": {
                "text": "bounded packet",
                "semantic_receipt_id": receipt["receipt_id"],
            },
        }
        task["semantic_receipt"] = receipt
        validated = validate_dispatch_context_packet(task, receipt, packet)
        self.assertEqual(validated["packet"], packet)
        self.assertNotIn("packet_sha256", validated)

        envelope = normalize_result_envelope(
            {
                "schema": "court.office.result.v1",
                "task_id": "local-alias",
                "semantic_epoch": 2,
                "case_ref": context["case_ref"],
                "plan_ref": None,
                "checkpoint_id": receipt["checkpoint_id"],
                "dispatch_uid": "dispatch-1",
                "attempt": 1,
                "office_instance_id": "zhongshu#0001",
                "office_instance_kind": "child_agent",
                "carrier_proof": {"agent_id": "agent-1"},
                "agent_id": "agent-1",
                "role": "zhongshu",
                "direct_superior": "taizi",
                "worktree": "local",
                "write_set": ["docs/plan.md"],
                "status": "completed",
                "summary": "completed plan",
                "evidence": ["host report"],
                "produced_at": "2026-09-06T08:01:00+08:00",
            }
        )
        consultations = normalize_consultation_refs(
            [
                {
                    "consultation_id": "CON-1",
                    "case_ref": context["case_ref"],
                    "plan_ref": None,
                    "from_role": "zhongshu",
                    "to_role": "menxia",
                    "purpose": "review plan",
                    "input_pointer": "court-runtime:tasks/local/plan",
                    "reply_pointer": "court-runtime:tasks/local/review",
                    "write_authority_granted": False,
                }
            ]
        )
        self.assertEqual(envelope["case_ref"], context["case_ref"])
        self.assertEqual(consultations[0]["consultation_id"], "CON-1")
        self.assertFalse(any("sha256" in str(key).lower() for key in envelope))
        self.assertEqual(
            result_binding_problems(
                envelope,
                {
                    "case_ref": context["case_ref"],
                    "semantic_epoch": 2,
                    "checkpoint_id": receipt["checkpoint_id"],
                    "dispatch_uid": "dispatch-1",
                    "attempt": 1,
                    "office_instance_id": "zhongshu#0001",
                    "agent_id": "agent-1",
                    "role": "zhongshu",
                    "direct_superior": "taizi",
                    "worktree": "local",
                    "write_set": ["docs/plan.md"],
                },
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
