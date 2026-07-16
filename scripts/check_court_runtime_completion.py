"""Isolated R3 charter-revision checks for the local court runtime."""

from __future__ import annotations

from argparse import Namespace
from copy import deepcopy
import contextlib
import io
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.dont_write_bytecode = True

import archive_runtime_task
import court_runtime


ASSESSMENT_SCHEMA = "court.outcome_assessment.v1"
BINDING_SCHEMA = "court.runtime_assessment_binding.v1"
RECEIPT_SCHEMA = "court.shiguan_checkpoint_receipt.v1"
REVISION_THREE_CHARTER = "offline fixture revision 3"
REVISION_FOUR_CHARTER = "offline fixture revision 4"


def charter_sha256(charter: str) -> str:
    return hashlib.sha256(charter.encode("utf-8")).hexdigest()


def revision_capsule(charter: str, revision: int) -> dict[str, object]:
    digest = charter_sha256(charter)
    label = f"revision-{revision}"
    return {
        "schema": "court.semantic.invariant_capsule.v1",
        "latest_decree_anchor": charter,
        "latest_decree_sha256": digest,
        "non_goals": [f"{label}:do not touch real runtime state"],
        "boundaries": [f"{label}:TemporaryDirectory fixture only"],
        "allowed_actions": [f"{label}:synthetic completion check"],
        "forbidden_actions": [f"{label}:real Shiguan access"],
        "acceptance": [f"{label}:completion checker passes"],
        "evidence_requirements": [f"{label}:machine-readable result"],
        "stop_gates": [f"{label}:semantic drift"],
        "write_set": ["scripts/check_court_runtime_completion.py"],
        "governing_hashes": {label: charter_sha256(label)},
        "charter_sha256": digest,
    }


def revision_binding(charter: str, revision: int) -> dict[str, object]:
    return court_runtime.semantic_binding_for_revision(
        charter,
        revision,
        revision_capsule(charter, revision),
    )


def record_revision_kwargs(
    task: dict[str, object],
    *,
    new_charter: str = REVISION_FOUR_CHARTER,
) -> dict[str, object]:
    new_revision = int(task["charter_revision"]) + 1
    return {
        "expected_revision": task["charter_revision"],
        "expected_sha256": task["charter_sha256"],
        "new_revision": new_revision,
        "new_sha256": charter_sha256(new_charter),
        "new_charter": new_charter,
        "new_invariant_capsule": revision_capsule(new_charter, new_revision),
        "event_head_sha256": "0" * 64,
        "event_head_bytes": 0,
        "actor": "zhongshu",
        "evidence": "approved correction",
    }


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
        "rationale": "completion checker fixture",
    }


def correction_gate(task_id: str) -> dict[str, object]:
    return {
        **formal_gate(),
        "active_decree": True,
        "active_decree_state": "ACTIVE",
        "message_class": "TASK_CORRECTION",
        "relation_to_active_decree": "CORRECTS",
        "taskization_consent": "NOT_REQUIRED",
        "target_task_id": task_id,
    }


def create_args(task_id: str) -> Namespace:
    return Namespace(
        task_id=task_id,
        title="completion contract",
        charter="offline fixture",
        work_kind="implementation",
        intake_gate=formal_gate(),
        intake_file=None,
        owner="taizi",
        report_tier="standard",
        evidence="fixture",
        note="fixture",
    )


def revision_args(task_id: str, **overrides: object) -> Namespace:
    values: dict[str, object] = {
        "task_id": task_id,
        "expected_revision": 3,
        "expected_sha256": charter_sha256(REVISION_THREE_CHARTER),
        "new_revision": 4,
        "new_sha256": charter_sha256(REVISION_FOUR_CHARTER),
        "new_charter": REVISION_FOUR_CHARTER,
        "new_charter_file": None,
        "new_invariant_capsule": revision_capsule(REVISION_FOUR_CHARTER, 4),
        "new_invariant_capsule_file": None,
        "correction_gate": correction_gate(task_id),
        "correction_file": None,
        "actor": "zhongshu",
        "evidence": "approved correction",
        "note": "fixture revision",
    }
    values.update(overrides)
    return Namespace(**values)


def seed_revision(task: dict[str, object]) -> dict[str, object]:
    seeded = deepcopy(task)
    seeded["charter"] = REVISION_THREE_CHARTER
    seeded.update(revision_binding(REVISION_THREE_CHARTER, 3))
    seeded["outcome_assessment"] = {
        "schema": "court.outcome_assessment.v1",
        "gate": "PASSED",
        "reasons": [],
        "outcome": {"nested": ["source"]},
    }
    seeded["assessment_binding"] = {
        "schema": "court.runtime_assessment_binding.v1",
        "status": "VERIFIED",
    }
    seeded["shiguan_checkpoint"] = {"status": "VERIFIED"}
    seeded["completion"] = {"status": "READY"}
    return seeded


def assessment(
    task: dict[str, object],
    *,
    gate: str = "PASSED",
    reasons: list[str] | None = None,
    evidence_sha256: str = "e" * 64,
) -> dict[str, object]:
    return {
        "schema": BINDING_SCHEMA,
        "gate": gate,
        "reasons": list(reasons or []),
        "task_id": task["task_id"],
        "charter_revision": task["charter_revision"],
        "charter_sha256": task["charter_sha256"],
        "assessment_sha256": "d" * 64,
        "evidence_sha256": evidence_sha256,
        "assessed_at": "2026-07-14T09:30:00+08:00",
    }


def assessment_args(task_id: str, record: dict[str, object]) -> Namespace:
    return Namespace(
        task_id=task_id,
        expected_revision=record["charter_revision"],
        expected_charter_sha256=record["charter_sha256"],
        assessment=record,
        assessment_file=None,
        actor="menxia",
        evidence="reviewed evidence bundle",
        note="bind outcome assessment",
    )


def checkpoint_receipt(task: dict[str, object], receipt_id: str = "receipt-001") -> dict[str, object]:
    return {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": receipt_id,
        "task_id": task["task_id"],
        "charter_revision": task["charter_revision"],
        "charter_sha256": task["charter_sha256"],
        "assessment_sha256": task["assessment_binding"]["assessment_sha256"],
        "record_sha256": "e" * 64,
        "archive_path": f"fixture://shiguan/{receipt_id}",
        "recorded_at": "2026-07-14T00:01:00Z",
    }


def checkpoint_ready_task(task_id: str) -> dict[str, object]:
    task = assessment_ready_task(task_id)
    task = court_runtime.bind_assessment_record(task, assessment(task))
    receipt = checkpoint_receipt(task)
    task["state"] = "ShiguanRecorded"
    task["shiguan_checkpoint"] = {
        "status": "VERIFIED",
        "receipt_id": receipt["receipt_id"],
        "record_sha256": receipt["record_sha256"],
        "archive_path": receipt["archive_path"],
        "recorded_at": receipt["recorded_at"],
    }
    task["completion"] = {"status": "READY"}
    return task


def complete_args(task: dict[str, object], receipt: dict[str, object]) -> Namespace:
    return Namespace(
        task_id=task["task_id"],
        expected_revision=task["charter_revision"],
        expected_charter_sha256=task["charter_sha256"],
        receipt=receipt,
        receipt_file=None,
        actor="taizi",
        evidence="verified checkpoint receipt",
        note="atomic completion",
    )


def envelope_sha256(value: dict[str, object]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def assessment_ready_task(task_id: str) -> dict[str, object]:
    task = court_runtime.create_task(create_args(task_id)).task
    task["state"] = "MenxiaReview"
    task["charter"] = REVISION_THREE_CHARTER
    task.update(revision_binding(REVISION_THREE_CHARTER, 3))
    task["evidence_sha256"] = "e" * 64
    return task


def check_runtime_source_is_outcome_gate_independent() -> None:
    source = Path(court_runtime.__file__).read_text(encoding="utf-8")
    assert "import court_outcome_gate" not in source
    assert "from court_outcome_gate import" not in source


def check_assessment_validation_and_deep_copy() -> None:
    task = assessment_ready_task("bind-pure")
    record = assessment(task)
    source_task = deepcopy(task)
    source_record = deepcopy(record)
    bound = court_runtime.bind_assessment_record(task, record)
    assert task == source_task
    assert record == source_record
    binding = bound["assessment_binding"]
    assert binding["schema"] == BINDING_SCHEMA
    assert binding["task_id"] == task["task_id"]
    assert binding["charter_revision"] == task["charter_revision"]
    assert binding["charter_sha256"] == task["charter_sha256"]
    assert binding["evidence_sha256"] == "e" * 64
    assert binding["assessment_sha256"] == "d" * 64
    assert binding["status"] == "VERIFIED"
    assert binding["source_envelope"] == source_record
    assert binding["source_envelope"] is not record
    assert binding["source_envelope_sha256"] == envelope_sha256(source_record)
    assert bound["completion"] == {"status": "ASSESSMENT_BOUND"}
    bound["assessment_binding"]["reasons"].append("alias")
    assert record == source_record

    invalid_cases = (
        ({"schema": "wrong"}, "invalid_runtime_assessment_binding_schema"),
        ({"gate": "UNKNOWN"}, "invalid_outcome_assessment_gate"),
        ({"reasons": "not-a-list"}, "invalid_outcome_assessment_reasons"),
        ({"reasons": [""]}, "invalid_outcome_assessment_reason"),
        ({"assessment_sha256": "bad"}, "invalid_assessment_sha256"),
        ({"evidence_sha256": "bad"}, "invalid_assessment_evidence_sha256"),
        ({"evidence_sha256": "f" * 64}, "assessment_evidence_sha256_mismatch"),
        ({"assessed_at": "not-time"}, "invalid_assessment_timestamp"),
        ({"task_id": "another"}, "assessment_task_mismatch"),
        ({"charter_revision": 2}, "assessment_charter_revision_mismatch"),
        ({"charter_sha256": "b" * 64}, "assessment_charter_sha256_mismatch"),
        ({"unknown": "field"}, "assessment_unknown_fields"),
    )
    for override, expected in invalid_cases:
        candidate = {**assessment(task), **override}
        expect_error(lambda candidate=candidate: court_runtime.bind_assessment_record(task, candidate), expected)


def check_partial_and_blocked_are_noncompletable() -> None:
    task = assessment_ready_task("bind-noncomplete")
    for gate in ("PARTIAL", "BLOCKED"):
        record = assessment(task, gate=gate, reasons=[f"{gate.lower()} reason"])
        bound = court_runtime.bind_assessment_record(task, record)
        assert bound["assessment_binding"]["status"] == "NONCOMPLETABLE"
        assert bound["completion"] == {"status": "NONCOMPLETABLE_ASSESSMENT"}
        expect_error(
            lambda bound=bound: court_runtime.validate_runtime_gate(
                bound, "MenxiaReview", "ShiguanRecorded", "checkpoint"
            ),
            "outcome_assessment_not_completable",
        )
        recorded = deepcopy(bound)
        recorded["state"] = "ShiguanRecorded"
        expect_error(
            lambda recorded=recorded: court_runtime.validate_runtime_gate(
                recorded, "ShiguanRecorded", "Done", "final evidence"
            ),
            "atomic_completion_required",
        )
    passed = court_runtime.bind_assessment_record(task, assessment(task))
    expect_error(
        lambda: court_runtime.validate_runtime_gate(
            passed, "MenxiaReview", "ShiguanRecorded", "assessment only"
        ),
        "shiguan_checkpoint_not_verified",
    )
    recorded = deepcopy(passed)
    recorded["state"] = "ShiguanRecorded"
    recorded["shiguan_checkpoint"] = {"status": "VERIFIED"}
    expect_error(
        lambda: court_runtime.validate_runtime_gate(
            recorded, "ShiguanRecorded", "Done", "assessment and checkpoint only"
        ),
        "atomic_completion_required",
    )
    expect_error(
        lambda: court_runtime.bind_assessment_record(task, assessment(task, gate="PASSED", reasons=["bad"])),
        "passed_assessment_must_not_have_reasons",
    )
    for gate in ("PARTIAL", "BLOCKED"):
        expect_error(
            lambda gate=gate: court_runtime.bind_assessment_record(task, assessment(task, gate=gate)),
            "nonpassed_assessment_requires_reasons",
        )


def check_assessment_cli_cas_idempotency_and_rollback() -> None:
    task = assessment_ready_task("bind-cli")
    tasks = court_runtime.load_tasks()
    tasks[task["task_id"]] = task
    court_runtime.write_tasks(tasks)
    record = assessment(task)
    record["assessed_at"] = "2026-07-14T01:30:00Z"
    writes = 0
    events = 0
    original_write = court_runtime.write_tasks
    original_append = court_runtime.append_event

    def counted_write(value: dict[str, dict[str, object]]) -> None:
        nonlocal writes
        writes += 1
        original_write(value)

    def counted_append(value: dict[str, object]) -> None:
        nonlocal events
        events += 1
        original_append(value)

    court_runtime.write_tasks = counted_write  # type: ignore[assignment]
    court_runtime.append_event = counted_append  # type: ignore[assignment]
    try:
        first = court_runtime.bind_assessment_task(assessment_args("bind-cli", record))
        duplicate = court_runtime.bind_assessment_task(assessment_args("bind-cli", deepcopy(record)))
    finally:
        court_runtime.write_tasks = original_write  # type: ignore[assignment]
        court_runtime.append_event = original_append  # type: ignore[assignment]
    assert writes == 1 and events == 1
    assert first.event["action"] == "bind_assessment"
    assert duplicate.event == first.event
    assert duplicate.task == first.task
    assert first.task["assessment_binding"]["source_envelope"]["assessed_at"] == (
        "2026-07-14T01:30:00Z"
    )
    assert first.task["state"] == "MenxiaReview"

    before_tasks = court_runtime.tasks_path().read_bytes()
    before_events = court_runtime.events_path().read_bytes()
    different = assessment(first.task)
    different["assessment_sha256"] = "f" * 64
    expect_error(
        lambda: court_runtime.bind_assessment_task(assessment_args("bind-cli", different)),
        "assessment_binding_conflict",
    )
    timestamp_spelling = deepcopy(record)
    timestamp_spelling["assessed_at"] = "2026-07-14T01:30:00+00:00"
    expect_error(
        lambda: court_runtime.bind_assessment_task(
            assessment_args("bind-cli", timestamp_spelling)
        ),
        "assessment_binding_conflict",
    )
    stale = assessment_args("bind-cli", record)
    stale.expected_revision = 2
    expect_error(lambda: court_runtime.bind_assessment_task(stale), "stale_charter_revision")
    intruder = assessment_args("bind-cli", record)
    intruder.actor = "intruder"
    expect_error(lambda: court_runtime.bind_assessment_task(intruder), "unknown_actor_office")
    assert court_runtime.tasks_path().read_bytes() == before_tasks
    assert court_runtime.events_path().read_bytes() == before_events

    revised = court_runtime.revise_charter_record(
        first.task,
        **record_revision_kwargs(first.task),
    )
    revised["state"] = "MenxiaReview"
    expect_error(
        lambda: court_runtime.bind_assessment_record(revised, record),
        "assessment_charter_revision_mismatch",
    )

    rollback_task = assessment_ready_task("bind-rollback")
    tasks = court_runtime.load_tasks()
    tasks[rollback_task["task_id"]] = rollback_task
    court_runtime.write_tasks(tasks)
    before_tasks = court_runtime.tasks_path().read_bytes()
    before_events = court_runtime.events_path().read_bytes()

    def failed_append(_event: dict[str, object]) -> None:
        raise RuntimeError("injected append failure")

    court_runtime.append_event = failed_append  # type: ignore[assignment]
    try:
        try:
            court_runtime.bind_assessment_task(
                assessment_args("bind-rollback", assessment(rollback_task))
            )
        except RuntimeError as exc:
            assert str(exc) == "injected append failure"
        else:
            raise AssertionError("append failure was swallowed")
    finally:
        court_runtime.append_event = original_append  # type: ignore[assignment]
    assert court_runtime.tasks_path().read_bytes() == before_tasks
    assert court_runtime.events_path().read_bytes() == before_events


def check_stored_binding_integrity_is_revalidated() -> None:
    task = assessment_ready_task("binding-integrity")
    partial = court_runtime.bind_assessment_record(
        task,
        assessment(task, gate="PARTIAL", reasons=["missing proof"]),
    )
    partial["assessment_binding"]["status"] = "VERIFIED"
    partial["shiguan_checkpoint"] = {"status": "VERIFIED"}
    partial["completion"] = {"status": "COMPLETED"}
    expect_error(
        lambda: court_runtime.validate_runtime_gate(
            partial, "MenxiaReview", "ShiguanRecorded", "forged derived fields"
        ),
        "outcome_assessment_not_completable",
    )

    passed = court_runtime.bind_assessment_record(task, assessment(task))
    passed["shiguan_checkpoint"] = {"status": "VERIFIED"}
    tampered_cases = []
    source_changed = deepcopy(passed)
    source_changed["assessment_binding"]["source_envelope"]["assessed_at"] = (
        "2026-07-14T01:30:00Z"
    )
    tampered_cases.append(source_changed)
    source_rehashed = deepcopy(source_changed)
    source_rehashed["assessment_binding"]["source_envelope_sha256"] = envelope_sha256(
        source_rehashed["assessment_binding"]["source_envelope"]
    )
    tampered_cases.append(source_rehashed)
    hash_changed = deepcopy(passed)
    hash_changed["assessment_binding"]["source_envelope_sha256"] = "0" * 64
    tampered_cases.append(hash_changed)
    core_changed = deepcopy(passed)
    core_changed["assessment_binding"]["gate"] = "PARTIAL"
    tampered_cases.append(core_changed)
    for candidate in tampered_cases:
        expect_error(
            lambda candidate=candidate: court_runtime.validate_runtime_gate(
                candidate, "MenxiaReview", "ShiguanRecorded", "tampered binding"
            ),
            "assessment_binding_integrity",
        )


def check_archive_builder_is_pure_and_unverified() -> None:
    task = checkpoint_ready_task("archive-builder")
    task["owner"] = "shiguan"
    task["heartbeat"] = "alive"
    task["title"] = "fixture title"
    args = Namespace(
        task_id="archive-builder",
        topic="",
        phase="fixture phase",
        status="",
        next="",
        memory_decision="PROPOSE",
        memory_content="",
        memory_reason="",
        event_limit=7,
    )
    events = court_runtime.read_events(limit=7, task_id=task["task_id"])
    summary = archive_runtime_task.runtime_summary(task, events)
    assert "completion_status=READY" in summary
    assert "completion_verified=false" in summary
    evidence = archive_runtime_task.runtime_evidence(task, 7, events)
    assert "charter_revision=3" in evidence
    command = archive_runtime_task.build_archive_command(task, args)
    assert command[0] == archive_runtime_task.sys.executable
    assert command[1].endswith("archive_checkpoint.py")
    assert command[command.index("--summary") + 1] == summary
    assert command[command.index("--evidence") + 1] == evidence
    assert command[command.index("--status") + 1] == "READY"


def check_verified_completion_projection() -> None:
    handoff = assessment_ready_task("projection-handoff")
    handoff["completion"] = {"status": "HANDOFF"}

    partial_source = assessment_ready_task("projection-partial")
    partial = court_runtime.bind_assessment_record(
        partial_source,
        assessment(partial_source, gate="PARTIAL", reasons=["fixture partial"]),
    )
    blocked_source = assessment_ready_task("projection-blocked")
    blocked = court_runtime.bind_assessment_record(
        blocked_source,
        assessment(blocked_source, gate="BLOCKED", reasons=["fixture blocker"]),
    )
    ready = checkpoint_ready_task("projection-ready")
    recorded = deepcopy(ready)
    recorded["completion"] = {"status": "READY"}

    raw_done = deepcopy(ready)
    receipt_id = raw_done["shiguan_checkpoint"]["receipt_id"]
    raw_done["state"] = "Done"
    raw_done["completion"] = {"status": "COMPLETED", "receipt_id": receipt_id}
    raw_done["consumed_checkpoint_receipt_ids"] = [receipt_id]

    legacy = deepcopy(raw_done)
    legacy["runtime_schema_version"] = 2
    legacy.pop("migrated_from_runtime_schema_version", None)

    stale_receipt = deepcopy(raw_done)
    stale_receipt["completion"]["receipt_id"] = "receipt-stale"

    omitted_assessment_digest = deepcopy(raw_done)
    omitted_assessment_digest["assessment_binding"].pop("assessment_sha256")
    omitted_checkpoint_digest = deepcopy(raw_done)
    omitted_checkpoint_digest["shiguan_checkpoint"].pop("record_sha256")
    malformed_record_digest = deepcopy(raw_done)
    malformed_record_digest["shiguan_checkpoint"]["record_sha256"] = "not-a-digest"
    partial_complete = deepcopy(raw_done)
    partial_complete["completion"]["status"] = "PARTIAL_COMPLETE"
    reordered_history = deepcopy(raw_done)
    reordered_history["completion"]["proof"] = {
        "schema": "court.completion_proof.v1",
        "events": [
            {"kind": "completion", "sequence": 2},
            {"kind": "checkpoint", "sequence": 1},
        ],
        "proof_sha256": "0" * 64,
    }

    cases = {
        "HANDOFF": handoff,
        "PARTIAL": partial,
        "BLOCKED": blocked,
        "READY": ready,
        "ShiguanRecorded": recorded,
        "raw_Done": raw_done,
        "legacy": legacy,
        "stale_receipt": stale_receipt,
        "omitted_assessment_digest": omitted_assessment_digest,
        "omitted_checkpoint_digest": omitted_checkpoint_digest,
        "malformed_record_digest": malformed_record_digest,
        "PARTIAL_COMPLETE": partial_complete,
        "reordered_history": reordered_history,
    }
    for name, task in cases.items():
        projection = court_runtime.completion_projection(task)
        assert projection["verified"] is False, (name, projection)
        summary = court_runtime.task_summary(task)
        archive_summary = archive_runtime_task.runtime_summary(task)
        assert "VERIFIED_COMPLETE" not in summary
        assert "completion_verified=false" in archive_summary
        original_list_tasks = court_runtime.list_tasks
        original_read_events = court_runtime.read_events
        court_runtime.list_tasks = lambda args, task=task: [task]  # type: ignore[assignment]
        court_runtime.read_events = lambda **kwargs: []  # type: ignore[assignment]
        try:
            item = court_runtime.status_payload(Namespace(limit=1, state=""))["tasks"][0]
        finally:
            court_runtime.list_tasks = original_list_tasks  # type: ignore[assignment]
            court_runtime.read_events = original_read_events  # type: ignore[assignment]
        assert item["completion_verified"] is False, name
        assert item["completion_status"] != "COMPLETED", name

    assert court_runtime.completion_projection(raw_done)["status"] != "COMPLETED"
    assert court_runtime.completion_projection(omitted_assessment_digest)["status"] == "INVALID_UNVERIFIED"
    assert court_runtime.completion_projection(omitted_checkpoint_digest)["status"] == "INVALID_UNVERIFIED"
    assert court_runtime.completion_projection(malformed_record_digest)["status"] == "INVALID_UNVERIFIED"
    assert court_runtime.completion_projection(partial_complete)["status"] != "COMPLETED"

    unsafe_args = Namespace(
        task_id="projection-raw-done", topic="", phase="fixture", status="",
        next="", memory_decision="PROPOSE", memory_content="", memory_reason="",
        event_limit=1,
    )
    unsafe_command = archive_runtime_task.build_archive_command(raw_done, unsafe_args)
    assert unsafe_command[unsafe_command.index("--status") + 1] != "Done"

    assert court_runtime.completion_projection(legacy)["status"] == "LEGACY_UNVERIFIED"
    assert "Done" in court_runtime.task_summary(legacy)

    original_list_tasks = court_runtime.list_tasks
    original_read_events = court_runtime.read_events
    court_runtime.list_tasks = lambda args: [partial]  # type: ignore[assignment]
    court_runtime.read_events = lambda **kwargs: []  # type: ignore[assignment]
    try:
        payload = court_runtime.status_payload(Namespace(limit=5, state=""))
    finally:
        court_runtime.list_tasks = original_list_tasks  # type: ignore[assignment]
        court_runtime.read_events = original_read_events  # type: ignore[assignment]
    assert payload["tasks"][0]["completion_status"] == "PARTIAL"
    assert payload["tasks"][0]["completion_verified"] is False
    assert "VERIFIED_COMPLETE" not in payload["dashboard"]


def check_checkpoint_receipt_strict_binding() -> None:
    task = checkpoint_ready_task("receipt-bind")
    receipt = checkpoint_receipt(task)
    source = deepcopy(receipt)
    validated = court_runtime.validate_checkpoint_receipt(task, receipt)
    assert receipt == source
    assert validated == {**source, "recorded_at": "2026-07-14T00:01:00+00:00"}

    cases = (
        ({"schema": "wrong"}, "invalid_checkpoint_receipt_schema"),
        ({"receipt_id": "fake receipt"}, "invalid_checkpoint_receipt_id"),
        ({"task_id": "another"}, "checkpoint_receipt_task_mismatch"),
        ({"charter_revision": 2}, "checkpoint_receipt_revision_mismatch"),
        ({"charter_sha256": "f" * 64}, "checkpoint_receipt_charter_mismatch"),
        ({"assessment_sha256": "f" * 64}, "checkpoint_receipt_assessment_mismatch"),
        ({"record_sha256": ""}, "invalid_checkpoint_record_sha256"),
        ({"record_sha256": "f" * 64}, "checkpoint_receipt_record_mismatch"),
        ({"archive_path": "fixture://shiguan/other"}, "checkpoint_receipt_path_mismatch"),
        ({"recorded_at": "2026-07-14T00:02:00Z"}, "checkpoint_receipt_time_mismatch"),
        ({"unknown": "field"}, "checkpoint_receipt_unknown_fields"),
    )
    for override, expected in cases:
        candidate = {**receipt, **override}
        expect_error(
            lambda candidate=candidate: court_runtime.validate_checkpoint_receipt(task, candidate),
            expected,
        )

    prestate = deepcopy(task)
    prestate["state"] = "MenxiaReview"
    expect_error(
        lambda: court_runtime.validate_checkpoint_receipt(prestate, receipt),
        "checkpoint_receipt_requires_shiguan_recorded",
    )
    consumed = deepcopy(task)
    consumed["consumed_checkpoint_receipt_ids"] = [receipt["receipt_id"]]
    expect_error(
        lambda: court_runtime.validate_checkpoint_receipt(consumed, receipt),
        "checkpoint_receipt_already_consumed",
    )

    opaque = checkpoint_ready_task("opaque-path")
    opaque_receipt = checkpoint_receipt(opaque, "receipt-opaque")
    opaque_receipt["archive_path"] = "fixture://shiguan/link/../receipt-opaque"
    opaque["shiguan_checkpoint"]["receipt_id"] = "receipt-opaque"
    opaque["shiguan_checkpoint"]["archive_path"] = opaque_receipt["archive_path"]
    assert court_runtime.validate_checkpoint_receipt(opaque, opaque_receipt)["archive_path"] == (
        "fixture://shiguan/link/../receipt-opaque"
    )


def check_atomic_complete_and_exact_rollback() -> None:
    task = checkpoint_ready_task("atomic-complete")
    receipt = checkpoint_receipt(task)
    tasks = court_runtime.load_tasks()
    tasks[task["task_id"]] = task
    court_runtime.write_tasks(tasks)
    checkpoint_ledger_event = {
        "time": "2026-07-14T00:01:00+00:00",
        "task_id": task["task_id"],
        "action": "record_shiguan",
        "from_state": "MenxiaReview",
        "to_state": "ShiguanRecorded",
        "actor": "shiguan",
        "receipt_id": receipt["receipt_id"],
        "assessment_sha256": receipt["assessment_sha256"],
        "record_sha256": receipt["record_sha256"],
    }
    court_runtime.append_event(checkpoint_ledger_event)
    writes = 0
    events = 0
    original_write = court_runtime.write_tasks
    original_append = court_runtime.append_event

    def counted_write(value: dict[str, dict[str, object]]) -> None:
        nonlocal writes
        writes += 1
        original_write(value)

    def counted_append(value: dict[str, object]) -> None:
        nonlocal events
        events += 1
        original_append(value)

    court_runtime.write_tasks = counted_write  # type: ignore[assignment]
    court_runtime.append_event = counted_append  # type: ignore[assignment]
    try:
        result = court_runtime.complete_task_atomically(complete_args(task, receipt))
    finally:
        court_runtime.write_tasks = original_write  # type: ignore[assignment]
        court_runtime.append_event = original_append  # type: ignore[assignment]
    assert writes == 1 and events == 1
    assert result.task["state"] == "Done"
    assert result.task["completion"]["status"] == "COMPLETED"
    assert result.task["consumed_checkpoint_receipt_ids"] == ["receipt-001"]
    assert result.event["action"] == "complete"
    proof = result.task["completion"]["proof"]
    assert proof["schema"] == "court.completion_proof.v1"
    assert proof["task_id"] == task["task_id"]
    assert proof["receipt_id"] == receipt["receipt_id"]
    assert proof["assessment_sha256"] == receipt["assessment_sha256"]
    assert proof["record_sha256"] == receipt["record_sha256"]
    assert [item["kind"] for item in proof["events"]] == ["checkpoint", "completion"]
    assert proof["events"][0]["sequence"] < proof["events"][1]["sequence"]
    assert proof["events"][1]["event"] == result.event
    assert len(proof["proof_sha256"]) == 64
    persisted_events = court_runtime.read_events(limit=10, task_id=task["task_id"])
    assert persisted_events[-1] == proof["events"][1]["event"] == result.event
    assert court_runtime.completion_projection(result.task)["verified"] is False
    assert court_runtime.completion_projection(result.task, [result.event])["verified"] is False
    assert court_runtime.completion_projection(result.task, persisted_events)["verified"] is True
    assert "VERIFIED_COMPLETE" not in court_runtime.task_summary(result.task)
    assert "VERIFIED_COMPLETE" in court_runtime.task_summary(result.task, persisted_events)
    assert "completion_verified=false" in archive_runtime_task.runtime_summary(result.task, [])
    assert "completion_verified=true" in archive_runtime_task.runtime_summary(
        result.task, persisted_events
    )

    wrong_receipt_events = deepcopy(persisted_events)
    wrong_receipt_events[-1]["receipt_id"] = "wrong-receipt"
    assert court_runtime.completion_projection(result.task, wrong_receipt_events)["verified"] is False
    assert "completion_verified=false" in archive_runtime_task.runtime_summary(
        result.task, wrong_receipt_events
    )

    checkpoint_event = deepcopy(proof["events"][0]["event"])
    checkpoint_event["time"] = checkpoint_event.pop("recorded_at")
    ordered_events = [checkpoint_event, result.event]
    assert court_runtime.completion_projection(result.task, ordered_events)["verified"] is True
    reordered_events = [result.event, checkpoint_event]
    assert court_runtime.completion_projection(result.task, reordered_events)["verified"] is False

    original_list_tasks = court_runtime.list_tasks
    original_read_events = court_runtime.read_events
    court_runtime.list_tasks = lambda args: [result.task]  # type: ignore[assignment]
    court_runtime.read_events = lambda **kwargs: wrong_receipt_events  # type: ignore[assignment]
    try:
        bad_payload = court_runtime.status_payload(Namespace(limit=1, state=""))
        bad_command = archive_runtime_task.build_archive_command(
            result.task,
            Namespace(
                task_id=task["task_id"], topic="", phase="fixture", status="",
                next="", memory_decision="PROPOSE", memory_content="",
                memory_reason="", event_limit=10,
            ),
        )
    finally:
        court_runtime.list_tasks = original_list_tasks  # type: ignore[assignment]
        court_runtime.read_events = original_read_events  # type: ignore[assignment]
    assert bad_payload["tasks"][0]["completion_verified"] is False
    assert "VERIFIED_COMPLETE" not in bad_payload["dashboard"]
    assert bad_command[bad_command.index("--status") + 1] != "COMPLETED"
    assert "completion_verified=false" in bad_command[bad_command.index("--summary") + 1]

    for index in range(13):
        court_runtime.append_event({
            "time": f"2026-07-14T01:{index:02d}:00+00:00",
            "task_id": f"unrelated-{index}",
            "action": "heartbeat",
            "from_state": "Workshops",
            "to_state": "Workshops",
            "actor": "gongbu",
        })
    original_list_tasks = court_runtime.list_tasks
    court_runtime.list_tasks = lambda args: [result.task]  # type: ignore[assignment]
    try:
        retained_payload = court_runtime.status_payload(Namespace(limit=1, state=""))
    finally:
        court_runtime.list_tasks = original_list_tasks  # type: ignore[assignment]
    assert retained_payload["tasks"][0]["completion_verified"] is True
    assert "VERIFIED_COMPLETE" in retained_payload["dashboard"], retained_payload["dashboard"]

    retained_command = archive_runtime_task.build_archive_command(
        result.task,
        Namespace(
            task_id=task["task_id"], topic="", phase="fixture", status="",
            next="", memory_decision="PROPOSE", memory_content="",
            memory_reason="", event_limit=10,
        ),
    )
    assert retained_command[retained_command.index("--status") + 1] == "COMPLETED"
    output_buffer = io.StringIO()
    with contextlib.redirect_stdout(output_buffer):
        court_runtime.output(result, "text")
    assert "VERIFIED_COMPLETE" in output_buffer.getvalue()
    expect_error(
        lambda: court_runtime.complete_task_atomically(complete_args(task, receipt)),
        "checkpoint_receipt_already_consumed",
    )

    rollback = checkpoint_ready_task("atomic-rollback")
    rollback_receipt = checkpoint_receipt(rollback, "receipt-rollback")
    rollback["shiguan_checkpoint"]["receipt_id"] = "receipt-rollback"
    rollback["shiguan_checkpoint"]["archive_path"] = "fixture://shiguan/receipt-rollback"
    tasks = court_runtime.load_tasks()
    tasks[rollback["task_id"]] = rollback
    court_runtime.write_tasks(tasks)
    before_tasks = court_runtime.tasks_path().read_bytes()
    before_events = court_runtime.events_path().read_bytes() if court_runtime.events_path().exists() else b""

    def failed_append(_event: dict[str, object]) -> None:
        raise RuntimeError("injected completion append failure")

    court_runtime.append_event = failed_append  # type: ignore[assignment]
    try:
        try:
            court_runtime.complete_task_atomically(complete_args(rollback, rollback_receipt))
        except RuntimeError as exc:
            assert str(exc) == "injected completion append failure"
        else:
            raise AssertionError("completion append failure was swallowed")
    finally:
        court_runtime.append_event = original_append  # type: ignore[assignment]
    assert court_runtime.tasks_path().read_bytes() == before_tasks
    current_events = court_runtime.events_path().read_bytes() if court_runtime.events_path().exists() else b""
    assert current_events == before_events

    stale = checkpoint_ready_task("atomic-stale")
    stale_receipt = checkpoint_receipt(stale, "receipt-stale")
    stale["shiguan_checkpoint"]["receipt_id"] = "receipt-stale"
    stale["shiguan_checkpoint"]["archive_path"] = "fixture://shiguan/receipt-stale"
    tasks = court_runtime.load_tasks()
    tasks[stale["task_id"]] = stale
    court_runtime.write_tasks(tasks)
    before_tasks = court_runtime.tasks_path().read_bytes()
    before_events = court_runtime.events_path().read_bytes()
    stale_args = complete_args(stale, stale_receipt)
    stale_args.expected_revision = 2
    expect_error(
        lambda: court_runtime.complete_task_atomically(stale_args),
        "stale_charter_revision",
    )
    assert court_runtime.tasks_path().read_bytes() == before_tasks
    assert court_runtime.events_path().read_bytes() == before_events


def check_pause_resume_is_limited_to_menxia_review() -> None:
    task = assessment_ready_task("pause-resume")
    tasks = court_runtime.load_tasks()
    tasks[task["task_id"]] = task
    court_runtime.write_tasks(tasks)
    paused = court_runtime.pause_task(
        Namespace(
            task_id=task["task_id"], actor="shangshu", reason="hold",
            evidence_preserved="fixture", unsafe_remaining="none",
            affected_scope="completion", note="pause",
        )
    )
    assert paused.task["state"] == "Paused"
    assert paused.task["paused_from"] == "MenxiaReview"
    resumed = court_runtime.resume_task(
        Namespace(
            task_id=task["task_id"], to_state="MenxiaReview", actor="shangshu",
            resume_evidence="hold cleared", affected_scope="completion",
            from_paused_state="MenxiaReview", note="resume",
        )
    )
    assert resumed.task["state"] == "MenxiaReview"
    for forbidden in ("Done", "ShiguanRecorded"):
        candidate = deepcopy(paused.task)
        tasks = court_runtime.load_tasks()
        tasks[task["task_id"]] = candidate
        court_runtime.write_tasks(tasks)
        args = Namespace(
            task_id=task["task_id"], to_state=forbidden, actor="shangshu",
            resume_evidence="attempt", affected_scope="completion",
            from_paused_state="MenxiaReview", note="resume",
        )
        expect_error(lambda args=args: court_runtime.resume_task(args), "illegal paused resume target")


def check_generic_completion_paths_fail_closed() -> None:
    recorded = checkpoint_ready_task("generic-done")
    expect_error(
        lambda: court_runtime.validate_runtime_gate(
            recorded, "ShiguanRecorded", "Done", "generic completion"
        ),
        "atomic_completion_required",
    )
    missing = assessment_ready_task("generic-record")
    expect_error(
        lambda: court_runtime.validate_runtime_gate(
            missing, "MenxiaReview", "ShiguanRecorded", "generic record"
        ),
        "assessment_binding_integrity",
    )
    bound = court_runtime.bind_assessment_record(missing, assessment(missing))
    expect_error(
        lambda: court_runtime.validate_runtime_gate(
            bound, "MenxiaReview", "ShiguanRecorded", "generic record"
        ),
        "shiguan_checkpoint_not_verified",
    )


def check_persistent_completion_recovery() -> None:
    task = checkpoint_ready_task("crash-recovery")
    receipt = checkpoint_receipt(task, "receipt-crash")
    task["shiguan_checkpoint"]["receipt_id"] = "receipt-crash"
    task["shiguan_checkpoint"]["archive_path"] = "fixture://shiguan/receipt-crash"
    tasks = court_runtime.load_tasks()
    tasks[task["task_id"]] = task
    court_runtime.write_tasks(tasks)
    before_tasks = court_runtime.tasks_path().read_bytes()
    before_events = court_runtime.events_path().read_bytes()
    original_append = court_runtime.append_event

    def crash_after_task_write(_event: dict[str, object]) -> None:
        raise SystemExit("simulated process death")

    court_runtime.append_event = crash_after_task_write  # type: ignore[assignment]
    try:
        try:
            court_runtime.complete_task_atomically(complete_args(task, receipt))
        except SystemExit as exc:
            assert str(exc) == "simulated process death"
        else:
            raise AssertionError("simulated process death was swallowed")
    finally:
        court_runtime.append_event = original_append  # type: ignore[assignment]
    marker = court_runtime.completion_transaction_path(task["task_id"])
    assert marker.exists()
    marker_data = json.loads(marker.read_text(encoding="utf-8"))
    assert marker_data["phase"] == "TASK_WRITTEN"
    assert court_runtime.tasks_path().read_bytes() != before_tasks
    tampered = deepcopy(marker_data)
    tampered["receipt_id"] = "receipt-tampered"
    marker.write_text(json.dumps(tampered), encoding="utf-8")
    expect_error(
        lambda: court_runtime.recover_completion_transaction(marker),
        "completion_transaction_marker_integrity",
    )
    marker.write_text(json.dumps(marker_data), encoding="utf-8")
    recovered = court_runtime.recover_completion_transaction(marker)
    assert recovered == "ROLLED_BACK"
    assert court_runtime.tasks_path().read_bytes() == before_tasks
    assert court_runtime.events_path().read_bytes() == before_events
    assert not marker.exists()

    court_runtime.append_event = crash_after_task_write  # type: ignore[assignment]
    try:
        try:
            court_runtime.complete_task_atomically(complete_args(task, receipt))
        except SystemExit:
            pass
        else:
            raise AssertionError("second simulated process death was swallowed")
    finally:
        court_runtime.append_event = original_append  # type: ignore[assignment]
    assert marker.exists()
    restarted = court_runtime.complete_task_atomically(complete_args(task, receipt))
    assert restarted.task["state"] == "Done"
    assert restarted.task["consumed_checkpoint_receipt_ids"] == ["receipt-crash"]
    assert not marker.exists()


def check_event_written_marker_finalizes_consistent_ledgers() -> None:
    task = checkpoint_ready_task("event-finalize")
    receipt = checkpoint_receipt(task, "receipt-finalize")
    task["shiguan_checkpoint"]["receipt_id"] = "receipt-finalize"
    task["shiguan_checkpoint"]["archive_path"] = "fixture://shiguan/receipt-finalize"
    tasks = court_runtime.load_tasks()
    tasks[task["task_id"]] = task
    court_runtime.write_tasks(tasks)
    original_remove = court_runtime._remove_completion_transaction_marker

    def leave_marker(_path: Path) -> None:
        return None

    court_runtime._remove_completion_transaction_marker = leave_marker  # type: ignore[assignment]
    try:
        completed = court_runtime.complete_task_atomically(complete_args(task, receipt))
    finally:
        court_runtime._remove_completion_transaction_marker = original_remove  # type: ignore[assignment]
    marker = court_runtime.completion_transaction_path(task["task_id"])
    assert marker.exists()
    marker_data = json.loads(marker.read_text(encoding="utf-8"))
    assert marker_data["phase"] == "EVENT_WRITTEN"
    task_bytes = court_runtime.tasks_path().read_bytes()
    event_bytes = court_runtime.events_path().read_bytes()
    assert court_runtime.recover_completion_transaction(marker) == "FINALIZED"
    assert court_runtime.tasks_path().read_bytes() == task_bytes
    assert court_runtime.events_path().read_bytes() == event_bytes
    assert court_runtime.load_tasks()[task["task_id"]]["completion"] == completed.task["completion"]
    assert not marker.exists()


def expect_error(callable_: object, expected: str) -> None:
    try:
        callable_()  # type: ignore[operator]
    except ValueError as exc:
        assert str(exc) == expected, (str(exc), expected)
    else:
        raise AssertionError(f"expected {expected}")


def check_revision_invalidates_derived_state() -> None:
    task = seed_revision(court_runtime.create_task(create_args("pure-revision")).task)
    source = deepcopy(task)
    revision_kwargs = record_revision_kwargs(task)
    revised = court_runtime.revise_charter_record(
        task,
        **{
            **revision_kwargs,
            "new_sha256": str(revision_kwargs["new_sha256"]).upper(),
        },
    )
    assert task == source
    assert revised["charter_revision"] == 4
    assert revised["charter_sha256"] == charter_sha256(REVISION_FOUR_CHARTER)
    assert revised["outcome_assessment"] == {
        "schema": "court.outcome_assessment.v1",
        "gate": "UNASSESSED",
        "reasons": [],
        "outcome": None,
    }
    assert revised["assessment_binding"] == {}
    assert revised["shiguan_checkpoint"] == {}
    assert revised["completion"] == {"status": "INVALIDATED_BY_CHARTER_REVISION"}
    assert revised["charter_revision_history"][-1] == {
        "revision": 3,
        "sha256": charter_sha256(REVISION_THREE_CHARTER),
        "actor": "zhongshu",
        "evidence": "approved correction",
    }
    revised["outcome_assessment"]["reasons"].append("alias-check")
    assert task == source


def check_pure_revision_rejections() -> None:
    task = seed_revision(court_runtime.create_task(create_args("pure-rejections")).task)
    cases = (
        ({"expected_revision": 2}, "stale_charter_revision"),
        ({"expected_sha256": "c" * 64}, "stale_charter_sha256"),
        ({"new_revision": 3}, "invalid_charter_revision_increment"),
        ({"new_sha256": "not-a-digest"}, "invalid_charter_sha256"),
    )
    defaults = record_revision_kwargs(task)
    for overrides, expected in cases:
        kwargs = {**defaults, **overrides}
        expect_error(lambda kwargs=kwargs: court_runtime.revise_charter_record(task, **kwargs), expected)
    illegal = deepcopy(task)
    illegal["state"] = "Done"
    expect_error(
        lambda: court_runtime.revise_charter_record(illegal, **defaults),
        "task_state_cannot_be_rechartered",
    )
    expect_error(
        lambda: court_runtime.revise_charter_record(task, **{**defaults, "actor": "intruder"}),
        "unknown_actor_office",
    )


def check_cli_compare_and_swap() -> None:
    created = court_runtime.create_task(create_args("cli-revision"))
    tasks = court_runtime.load_tasks()
    tasks["cli-revision"] = seed_revision(created.task)
    court_runtime.write_tasks(tasks)

    writes = 0
    events = 0
    original_write = court_runtime.write_tasks
    original_append = court_runtime.append_event

    def counted_write(value: dict[str, dict[str, object]]) -> None:
        nonlocal writes
        writes += 1
        original_write(value)

    def counted_append(value: dict[str, object]) -> None:
        nonlocal events
        events += 1
        original_append(value)

    court_runtime.write_tasks = counted_write  # type: ignore[assignment]
    court_runtime.append_event = counted_append  # type: ignore[assignment]
    try:
        result = court_runtime.revise_charter_task(revision_args("cli-revision"))
    finally:
        court_runtime.write_tasks = original_write  # type: ignore[assignment]
        court_runtime.append_event = original_append  # type: ignore[assignment]
    assert writes == 1 and events == 1
    assert result.event["action"] == "revise_charter"
    assert result.task["charter_revision"] == 4
    assert len(result.task["charter_revision_history"]) == 1

    task_bytes = court_runtime.tasks_path().read_bytes()
    event_bytes = court_runtime.events_path().read_bytes()
    for args, expected in (
        (revision_args("cli-revision"), "stale_charter_revision"),
        (
            revision_args(
                "cli-revision",
                expected_revision=4,
                expected_sha256=charter_sha256(REVISION_FOUR_CHARTER),
                new_revision=5,
                new_sha256="c" * 64,
                correction_gate=correction_gate("another-task"),
            ),
            "task_correction_target_mismatch",
        ),
    ):
        expect_error(lambda args=args: court_runtime.revise_charter_task(args), expected)
        assert court_runtime.tasks_path().read_bytes() == task_bytes
        assert court_runtime.events_path().read_bytes() == event_bytes

    intruder = revision_args(
        "cli-revision",
        expected_revision=4,
        expected_sha256=charter_sha256(REVISION_FOUR_CHARTER),
        new_revision=5,
        new_sha256="c" * 64,
        actor="intruder",
    )
    expect_error(lambda: court_runtime.revise_charter_task(intruder), "unknown_actor_office")
    assert court_runtime.tasks_path().read_bytes() == task_bytes
    assert court_runtime.events_path().read_bytes() == event_bytes


def check_uppercase_expected_digest_and_transaction_rollback() -> None:
    created = court_runtime.create_task(create_args("rollback-revision"))
    tasks = court_runtime.load_tasks()
    tasks["rollback-revision"] = seed_revision(created.task)
    court_runtime.write_tasks(tasks)

    before_tasks = court_runtime.tasks_path().read_bytes()
    before_events = court_runtime.events_path().read_bytes()
    original_append = court_runtime.append_event

    def failed_append(_event: dict[str, object]) -> None:
        raise RuntimeError("injected append failure")

    court_runtime.append_event = failed_append  # type: ignore[assignment]
    try:
        try:
            court_runtime.revise_charter_task(
                revision_args(
                    "rollback-revision",
                    expected_sha256=charter_sha256(REVISION_THREE_CHARTER).upper(),
                )
            )
        except RuntimeError as exc:
            assert str(exc) == "injected append failure"
        else:
            raise AssertionError("append failure was swallowed")
    finally:
        court_runtime.append_event = original_append  # type: ignore[assignment]
    assert court_runtime.tasks_path().read_bytes() == before_tasks
    assert court_runtime.events_path().read_bytes() == before_events


def check_cli_parser() -> None:
    capsule_json = json.dumps(
        revision_capsule(REVISION_FOUR_CHARTER, 4),
        ensure_ascii=False,
        sort_keys=True,
    )
    parsed = court_runtime.build_parser().parse_args(
        [
            "revise-charter",
            "--task-id", "cli",
            "--expected-revision", "3",
            "--expected-sha256", "a" * 64,
            "--new-revision", "4",
            "--new-sha256", "b" * 64,
            "--new-charter", REVISION_FOUR_CHARTER,
            "--new-invariant-capsule-json", capsule_json,
            "--correction-file", "correction.json",
            "--actor", "zhongshu",
            "--evidence", "approved",
            "--note", "audit note",
        ]
    )
    assert parsed.command == "revise-charter"
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            court_runtime.build_parser().parse_args(
                [
                    "revise-charter",
                    "--task-id", "cli",
                    "--expected-revision", "3",
                    "--expected-sha256", "a" * 64,
                    "--new-revision", "4",
                    "--new-sha256", "b" * 64,
                    "--new-charter", REVISION_FOUR_CHARTER,
                    "--new-invariant-capsule-json", capsule_json,
                    "--correction-file", "correction.json",
                    "--actor", "zhongshu",
                    "--evidence", "approved",
                ]
            )
        except court_runtime.CourtCliArgumentError as exc:
            assert str(exc) == "the following arguments are required: --note"
        else:
            raise AssertionError("revise-charter accepted an omitted --note")

    parsed = court_runtime.build_parser().parse_args(
        [
            "bind-assessment",
            "--task-id", "cli",
            "--expected-revision", "3",
            "--expected-charter-sha256", "a" * 64,
            "--assessment-file", "assessment.json",
            "--actor", "menxia",
            "--evidence", "reviewed bundle",
            "--note", "bind exact assessment",
        ]
    )
    assert parsed.command == "bind-assessment"


def main() -> int:
    with TemporaryDirectory() as temp_dir:
        original_runtime_root = court_runtime.runtime_root
        court_runtime.runtime_root = lambda: Path(temp_dir)  # type: ignore[assignment]
        try:
            check_runtime_source_is_outcome_gate_independent()
            check_assessment_validation_and_deep_copy()
            check_partial_and_blocked_are_noncompletable()
            check_assessment_cli_cas_idempotency_and_rollback()
            check_stored_binding_integrity_is_revalidated()
            check_archive_builder_is_pure_and_unverified()
            check_verified_completion_projection()
            check_checkpoint_receipt_strict_binding()
            check_atomic_complete_and_exact_rollback()
            check_pause_resume_is_limited_to_menxia_review()
            check_generic_completion_paths_fail_closed()
            check_persistent_completion_recovery()
            check_event_written_marker_finalizes_consistent_ledgers()
            check_revision_invalidates_derived_state()
            check_pure_revision_rejections()
            check_cli_compare_and_swap()
            check_uppercase_expected_digest_and_transaction_rollback()
            check_cli_parser()
        finally:
            court_runtime.runtime_root = original_runtime_root  # type: ignore[assignment]
    print("COURT_RUNTIME_COMPLETION_OK cases=18")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
