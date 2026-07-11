"""Verify the Shiguan pending quarantine planner in isolated fixtures only."""

from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import tempfile
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import patch
import uuid


BASE = Path(__file__).resolve().parent
PLANNER_PATH = BASE / "plan_shiguan_pending_quarantine.py"
GOVERNANCE_PATH = BASE / "shiguan_pending_governance.py"
REQUIRED_SIDECAR_FIELDS = {
    "id",
    "filename",
    "source_type",
    "status",
    "imported_at",
    "char_count",
    "estimated_tokens",
    "sha256",
    "suggested_processor",
}


def load_planner():
    sys.path.insert(0, str(BASE))
    spec = importlib.util.spec_from_file_location("court_pending_quarantine_planner_test", PLANNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load quarantine planner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_governance():
    sys.path.insert(0, str(BASE))
    spec = importlib.util.spec_from_file_location("court_pending_governance_test", GOVERNANCE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load pending governance")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_sidecar(metadata_id: str, filename: str) -> dict[str, object]:
    value = {
        "id": metadata_id,
        "filename": filename,
        "source_type": Path(filename).suffix.lstrip(".") or "json",
        "status": "pending",
        "imported_at": "2026-07-10T00:00:00+00:00",
        "char_count": 321,
        "estimated_tokens": 81,
        "sha256": "a" * 64,
        "suggested_processor": "codex",
    }
    if set(value) != REQUIRED_SIDECAR_FIELDS:
        raise AssertionError("test sidecar schema drifted")
    return value


def write_sidecar(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def write_runtime_identity_fixture(path: Path, task_id: str) -> dict[str, str]:
    agents: dict[str, object] = {}
    identities: dict[str, str] = {"taizi": "/root"}
    for role in ("menxia", "xingbu", "shiguan"):
        agent_id = f"/root/fixture-{role}"
        identities[role] = agent_id
        agents[agent_id] = {
            "agent_id": agent_id,
            "role": role,
            "status": "running",
            "preload_status": "PASSED",
            "office_identity_evidence": "PASSED",
            "model_route_status": "PASSED",
            "model_route_id": f"cmr-fixture-{role}",
            "profile_hash": "1" * 64,
            "dossier_hash": "2" * 64,
            "court_skill_hash": "3" * 64,
            "preload_ack_at": "2026-07-11T00:00:00+00:00",
        }
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                task_id: {
                    "task_id": task_id,
                    "state": "SixMinistries",
                    "created_at": "2026-07-11T00:00:00+00:00",
                    "agents": agents,
                }
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return identities


@contextmanager
def forbid_body_open(body_paths: set[Path]) -> Iterator[None]:
    original_open = Path.open
    normalized = {path.absolute() for path in body_paths}

    def guarded_open(path: Path, *args: object, **kwargs: object):
        if path.absolute() in normalized:
            raise AssertionError(f"pending body was opened: {path.name}")
        return original_open(path, *args, **kwargs)

    with patch.object(Path, "open", guarded_open):
        yield


def assert_no_mutation_api() -> None:
    source = PLANNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(PLANNER_PATH))
    forbidden_attrs = {"mkdir", "rename", "unlink", "rmdir", "touch", "write_bytes", "write_text", "remove", "move"}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in forbidden_attrs:
            found.append(node.func.attr)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "open":
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                continue
            mode = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
            if mode != "rb":
                found.append(f"open:{mode}")
    if found:
        raise AssertionError(f"planner exposes mutation-capable file APIs: {found}")
    compact = source.replace(" ", "")
    for forbidden_call in ("os.replace(", "os.rename(", "os.remove(", "shutil.move(", "Path.replace("):
        if forbidden_call in compact:
            raise AssertionError(f"planner exposes mutation-capable call: {forbidden_call}")


def fixture_check() -> dict[str, object]:
    planner = load_planner()
    governance = load_governance()
    with tempfile.TemporaryDirectory(prefix="court-pending-quarantine-") as temp_text:
        root = Path(temp_text) / "shiguan-imports" / "pending"
        root.mkdir(parents=True)

        bodies = {
            root / "valid.json",
            root / "missing.md",
            root / "invalid.txt",
            root / "duplicate-a.json",
            root / "duplicate-b.json",
            root / "binary.bin",
            root / "mismatch.json",
        }
        for index, body in enumerate(sorted(bodies)):
            body.write_bytes(b"\xff\xfe\x80NEVER-DECODE-PENDING-BODY-" + str(index).encode("ascii"))

        write_sidecar(root / "valid.metadata.json", valid_sidecar("valid-id", "valid.json"))
        (root / "invalid.metadata.json").write_bytes(b"\xffnot-json")
        write_sidecar(root / "duplicate-a.metadata.json", valid_sidecar("duplicate-id", "duplicate-a.json"))
        write_sidecar(root / "duplicate-b.metadata.json", valid_sidecar("duplicate-id", "duplicate-b.json"))
        write_sidecar(root / "mismatch.metadata.json", valid_sidecar("mismatch-id", "wrong-name.json"))
        write_sidecar(root / "orphan.metadata.json", valid_sidecar("orphan-id", "orphan.json"))
        (root / "unknown-directory-entry").mkdir()

        before = tree_snapshot(root)
        with forbid_body_open(bodies):
            plan = planner.build_plan(root)
        after = tree_snapshot(root)
        if before != after:
            raise AssertionError("dry-run planner changed fixture queue bytes")
        if plan.get("schema") != "court.shiguan_pending_quarantine_plan.v1":
            raise AssertionError("unexpected planner schema")
        contract = plan.get("inspection_contract")
        if not isinstance(contract, dict) or contract.get("body_content_reads") != 0:
            raise AssertionError("body read contract missing")
        if contract.get("apply_supported") is not False or contract.get("queue_mutations") != 0:
            raise AssertionError("planner is not permanently dry-run")

        counts = plan.get("counts")
        expected = {
            "valid_sidecar": 1,
            "missing_sidecar": 1,
            "invalid_sidecar": 2,
            "duplicate_id": 2,
            "orphan_sidecar": 1,
            "unsupported_body_type": 1,
            "unknown_entry_type": 1,
        }
        if not isinstance(counts, dict) or counts.get("classifications") != expected:
            raise AssertionError(f"classification mismatch: {counts}")
        if counts.get("pending_bodies") != 8 or counts.get("quarantine_recommended") != 8:
            raise AssertionError("unexpected body/quarantine counts")
        if not planner.is_reparse_point_stat(SimpleNamespace(st_file_attributes=0x400)):
            raise AssertionError("Windows reparse-point attribute was not detected")
        if planner.is_reparse_point_stat(SimpleNamespace(st_file_attributes=0)):
            raise AssertionError("ordinary file was misclassified as a reparse point")

        original_lstat = Path.lstat

        def reparse_root_lstat(path: Path):
            if path.absolute() == root.absolute():
                return SimpleNamespace(
                    st_mode=stat.S_IFDIR | 0o755,
                    st_dev=1,
                    st_ino=1,
                    st_size=0,
                    st_mtime=0,
                    st_mtime_ns=0,
                    st_file_attributes=0x400,
                )
            return original_lstat(path)

        with patch.object(Path, "lstat", reparse_root_lstat):
            reparse_root_plan = planner.build_plan(root)
        if reparse_root_plan.get("status") != "queue_unavailable" or "pending_root_reparse_point_rejected" not in reparse_root_plan.get("errors", []):
            raise AssertionError("reparse pending root did not fail closed")

        sidecar_path = root / "valid.metadata.json"
        original_fstat = planner.os.fstat
        calls = 0

        def swapped_fstat(descriptor: int):
            nonlocal calls
            calls += 1
            value = original_fstat(descriptor)
            if calls == 1:
                return SimpleNamespace(
                    st_dev=value.st_dev,
                    st_ino=value.st_ino + 1,
                    st_size=value.st_size,
                    st_mtime_ns=value.st_mtime_ns,
                    st_file_attributes=0,
                )
            return value

        with patch.object(planner.os, "fstat", side_effect=swapped_fstat):
            _value, swap_errors, _fingerprint, _digest = planner.load_sidecar(sidecar_path, "valid.json")
        if "sidecar_identity_changed_before_read" not in swap_errors:
            raise AssertionError("sidecar check/open identity swap did not fail closed")

        items = plan.get("items")
        if not isinstance(items, list):
            raise AssertionError("items missing")
        for item in items:
            if not isinstance(item, dict):
                raise AssertionError("invalid item")
            source = item.get("source")
            if not isinstance(source, dict):
                raise AssertionError("source evidence missing")
            fingerprint = source.get("source_fingerprint")
            if not isinstance(fingerprint, dict) or "size_bytes" not in fingerprint or "mtime_ns" not in fingerprint:
                raise AssertionError("stat fingerprint missing")
            if item.get("recommendation") == "quarantine_recommended":
                suggestion = item.get("suggested_quarantine")
                rollback = item.get("rollback_hint")
                if not isinstance(suggestion, dict) or not suggestion.get("copy_targets"):
                    raise AssertionError("quarantine target missing")
                if suggestion.get("source_retention_required") is not True:
                    raise AssertionError("quarantine plan did not preserve the source")
                if not isinstance(rollback, dict) or rollback.get("source_retention_required") is not True:
                    raise AssertionError("append-only quarantine rollback contract missing")
                if "move" in json.dumps({"suggestion": suggestion, "rollback": rollback}, ensure_ascii=False).lower():
                    raise AssertionError("quarantine plan still describes move/delete semantics")
                for target in suggestion["copy_targets"]:
                    if Path(str(target)).exists():
                        raise AssertionError("planner created a suggested target")

        valid_item = next(item for item in items if item.get("classification") == "valid_sidecar")
        binding = valid_item.get("governance_binding")
        if not isinstance(binding, dict):
            raise AssertionError("valid sidecar did not produce a body snapshot binding")
        for field in (
            "candidate_id",
            "filename",
            "source_fingerprint_sha256",
            "sidecar_metadata_sha256",
            "declared_body_sha256",
            "plan_snapshot_sha256",
        ):
            if not binding.get(field):
                raise AssertionError(f"governance binding missing {field}")

        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [sys.executable, str(PLANNER_PATH), "--pending-root", str(root), "--format", "json"],
            cwd=str(BASE.parent),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(f"planner CLI failed: {completed.stderr}")
        cli_plan = json.loads(completed.stdout)
        if cli_plan.get("snapshot_fingerprint", {}).get("sha256") != plan.get("snapshot_fingerprint", {}).get("sha256"):
            raise AssertionError("CLI and importable planner snapshots differ")
        if tree_snapshot(root) != before:
            raise AssertionError("planner CLI changed fixture queue")

        rejected = subprocess.run(
            [sys.executable, str(PLANNER_PATH), "--pending-root", str(root), "--apply"],
            cwd=str(BASE.parent),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        if rejected.returncode == 0 or "unrecognized arguments: --apply" not in rejected.stderr:
            raise AssertionError("planner unexpectedly accepted --apply")
        if tree_snapshot(root) != before:
            raise AssertionError("rejected --apply invocation changed fixture queue")

        governance_root = Path(temp_text) / "governance"
        trust_root = Path(temp_text) / "private-runtime" / "pending-governance"
        runtime_tasks_path = Path(temp_text) / "court-runtime" / "tasks.json"
        task_id = "fixture-pending-governance"
        identities = write_runtime_identity_fixture(runtime_tasks_path, task_id)
        ledger = governance.PendingGovernanceLedger(
            governance_root,
            pending_root=root,
            runtime_tasks_path=runtime_tasks_path,
            trust_root=trust_root,
            fixture_mode=True,
        )

        def actor_identity(role: str) -> dict[str, str]:
            return {"task_id": task_id, "agent_id": identities[role]}

        review_id = str(uuid.uuid4())
        if ledger.body_access_allowed("valid-id", review_id):
            raise AssertionError("pending body access allowed before authorization")
        ledger.transition(
            candidate_id="valid-id",
            review_id=review_id,
            actor="menxia",
            **actor_identity("menxia"),
            to_state="metadata_reviewed",
            evidence="fixture metadata reviewed",
            target="valid.json",
            rollback_hint="retain pending metadata state",
        )
        try:
            ledger.transition(
                candidate_id="valid-id",
                review_id=review_id,
                actor="menxia",
                **actor_identity("menxia"),
                to_state="reviewed",
                evidence="must fail before body authorization",
                target="valid.json",
                rollback_hint="retain pending metadata state",
                review_result_sha256="b" * 64,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("reviewed transition bypassed body authorization")
        forged_authorization_binding = dict(binding)
        forged_authorization_binding["plan_snapshot_sha256"] = "f" * 64
        try:
            ledger.authorize_body(
                candidate_ids=("valid-id",),
                review_id=review_id,
                actor="taizi",
                **actor_identity("taizi"),
                evidence="must reject caller-self-certified snapshot",
                scope_kind="candidate",
                scope_id="valid-id",
                target="fixture-review",
                rollback_hint="retain pending metadata state",
                candidate_bindings={"valid-id": forged_authorization_binding},
            )
        except ValueError:
            pass
        else:
            raise AssertionError("body authorization accepted a binding not independently recomputed from the pending snapshot")

        ledger.authorize_body(
            candidate_ids=("valid-id",),
            review_id=review_id,
            actor="taizi",
            **actor_identity("taizi"),
            evidence="explicit fixture candidate authorization",
            scope_kind="candidate",
            scope_id="valid-id",
            target="fixture-review",
            rollback_hint="revoke authorization before body access",
            candidate_bindings={"valid-id": binding},
        )
        if not ledger.body_access_allowed("valid-id", review_id, binding):
            raise AssertionError("explicit body authorization was not recognized")
        tampered_binding = dict(binding)
        tampered_binding["source_fingerprint_sha256"] = "f" * 64
        if ledger.body_access_allowed("valid-id", review_id, tampered_binding):
            raise AssertionError("body authorization survived a source fingerprint change")
        ledger.transition(
            candidate_id="valid-id",
            review_id=review_id,
            actor="menxia",
            **actor_identity("menxia"),
            to_state="reviewed",
            evidence="fixture body review result recorded",
            target="fixture-review-result",
            rollback_hint="retain original pending artifact",
            review_result_sha256="b" * 64,
        )
        try:
            ledger.transition(
                candidate_id="valid-id",
                review_id=review_id,
                actor="shiguan",
                **actor_identity("shiguan"),
                to_state="promoted",
                evidence="must not pass actor gate",
                target="approved-index",
                rollback_hint="retain reviewed decision",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("unauthorized actor wrote a promoted terminal decision")
        terminal = ledger.transition(
            candidate_id="valid-id",
            review_id=review_id,
            actor="menxia",
            **actor_identity("menxia"),
            to_state="promoted",
            evidence="fixture promotion decision only",
            target="approved-index",
            rollback_hint="return decision to reviewed state",
        )
        if terminal["state"] != "promoted" or terminal["queue_mutations"] != 0:
            raise AssertionError("terminal governance record mutated the queue")
        if ledger.body_operation_counters() != {
            "open": 0,
            "read": 0,
            "hash": 0,
            "move": 0,
            "delete": 0,
            "mark_seen": 0,
        }:
            raise AssertionError("governance ledger reported body operations")
        if tree_snapshot(root) != before:
            raise AssertionError("governance state machine changed fixture queue")
        if ledger.event_count("valid-id") != 4:
            raise AssertionError("unexpected append-only governance event count")

        metadata_only_review = str(uuid.uuid4())
        ledger.transition(
            candidate_id="unsafe-entry",
            review_id=metadata_only_review,
            actor="xingbu",
            **actor_identity("xingbu"),
            to_state="metadata_reviewed",
            evidence="fixture reparse metadata only",
            target="unsafe-entry",
            rollback_hint="retain original pending entry",
        )
        metadata_terminal = ledger.transition(
            candidate_id="unsafe-entry",
            review_id=metadata_only_review,
            actor="xingbu",
            **actor_identity("xingbu"),
            to_state="quarantined",
            evidence="metadata-only isolation decision",
            target="append-only quarantine manifest",
            rollback_hint="retain original pending entry",
        )
        if metadata_terminal.get("metadata_only_decision") is not True:
            raise AssertionError("unsafe metadata-only quarantine required body authorization")

        unauthorized_review = str(uuid.uuid4())
        ledger.transition(
            candidate_id="actor-gate",
            review_id=unauthorized_review,
            actor="shiguan",
            **actor_identity("shiguan"),
            to_state="metadata_reviewed",
            evidence="metadata cataloging only",
            target="actor-gate",
            rollback_hint="retain pending metadata",
        )
        try:
            ledger.authorize_body(
                candidate_ids=("actor-gate",),
                review_id=unauthorized_review,
                actor="shiguan",
                **actor_identity("shiguan"),
                evidence="must not authorize body",
                scope_kind="candidate",
                scope_id="actor-gate",
                target="actor-gate",
                rollback_hint="retain pending metadata",
                candidate_bindings={"actor-gate": binding},
            )
        except ValueError:
            pass
        else:
            raise AssertionError("unauthorized actor granted body access")

        forged_root = Path(temp_text) / "forged-governance"
        forged_trust = Path(temp_text) / "private-runtime" / "forged-governance"
        forged = governance.PendingGovernanceLedger(
            forged_root,
            pending_root=root,
            runtime_tasks_path=runtime_tasks_path,
            trust_root=forged_trust,
            fixture_mode=True,
        )
        forged_review = str(uuid.uuid4())
        forged.transition(
            candidate_id="forged-id",
            review_id=forged_review,
            actor="menxia",
            **actor_identity("menxia"),
            to_state="metadata_reviewed",
            evidence="legitimate first event",
            target="forged-id",
            rollback_hint="retain pending metadata",
        )
        forged_record = dict(forged.latest("forged-id"))
        forged_record["event_id"] = str(uuid.uuid4())
        forged_record["sequence"] = int(forged_record["sequence"]) + 1
        forged_record["previous_event_sha256"] = forged_record["event_sha256"]
        forged_record["from_state"] = "metadata_reviewed"
        forged_record["state"] = "body_authorized"
        forged_record["body_authorization_explicit"] = True
        forged_record["authorization_binding"] = dict(binding, candidate_id="forged-id")
        forged_record["authorization_scope"] = {"kind": "candidate", "id": "forged-id", "candidate_ids": ["forged-id"]}
        forged_record["event_sha256"] = "0" * 64
        forged_record["record_hmac_sha256"] = "0" * 64
        with forged.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(forged_record) + "\n")
        forged_binding = dict(binding)
        forged_binding["candidate_id"] = "forged-id"
        try:
            forged.body_access_allowed("forged-id", forged_review, forged_binding)
        except RuntimeError:
            pass
        else:
            raise AssertionError("forged governance event bypassed strict replay validation")

        identity_mismatch_review = str(uuid.uuid4())
        try:
            ledger.transition(
                candidate_id="identity-mismatch",
                review_id=identity_mismatch_review,
                actor="menxia",
                **actor_identity("xingbu"),
                to_state="metadata_reviewed",
                evidence="must reject role identity mismatch",
                target="identity-mismatch",
                rollback_hint="retain pending metadata",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("actor label was accepted without matching trusted runtime identity")

        duplicate_review = str(uuid.uuid4())
        existing_event_id = ledger.latest("valid-id")["event_id"]
        with patch.object(governance.uuid, "uuid4", return_value=uuid.UUID(existing_event_id)):
            try:
                ledger.transition(
                    candidate_id="duplicate-event-id",
                    review_id=duplicate_review,
                    actor="menxia",
                    **actor_identity("menxia"),
                    to_state="metadata_reviewed",
                    evidence="must reject duplicate event id",
                    target="duplicate-event-id",
                    rollback_hint="retain pending metadata",
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("duplicate event_id was accepted")

        timestamp_review = str(uuid.uuid4())
        with patch.object(governance, "_now", return_value="2026-07-11T00:00:00"):
            try:
                ledger.transition(
                    candidate_id="naive-timestamp",
                    review_id=timestamp_review,
                    actor="menxia",
                    **actor_identity("menxia"),
                    to_state="metadata_reviewed",
                    evidence="must reject naive timestamp",
                    target="naive-timestamp",
                    rollback_hint="retain pending metadata",
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("timezone-naive governance timestamp was accepted")

        head_tamper = governance.PendingGovernanceLedger(
            Path(temp_text) / "head-tamper-governance",
            pending_root=root,
            runtime_tasks_path=runtime_tasks_path,
            trust_root=Path(temp_text) / "private-runtime" / "head-tamper-governance",
            fixture_mode=True,
        )
        head_review = str(uuid.uuid4())
        head_tamper.transition(
            candidate_id="head-tamper",
            review_id=head_review,
            actor="menxia",
            **actor_identity("menxia"),
            to_state="metadata_reviewed",
            evidence="create authenticated external head fixture",
            target="head-tamper",
            rollback_hint="retain pending metadata",
        )
        forged_head = json.loads(head_tamper.trust.head_path.read_text(encoding="utf-8").splitlines()[-1])
        forged_head["checkpoint_id"] = str(uuid.uuid4())
        forged_head["previous_checkpoint_sha256"] = forged_head["checkpoint_sha256"]
        forged_head["event_count"] = int(forged_head["event_count"]) + 1
        forged_head["last_sequence"] = int(forged_head["last_sequence"]) + 1
        with head_tamper.trust.head_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(forged_head, sort_keys=True) + "\n")
        try:
            head_tamper.latest("head-tamper")
        except RuntimeError:
            pass
        else:
            raise AssertionError("forged external governance head was accepted")

        production_fail_closed = governance.PendingGovernanceLedger(
            Path(temp_text) / "production-governance",
            pending_root=root,
            runtime_tasks_path=runtime_tasks_path,
            trust_root=Path(temp_text) / "private-runtime" / "production-governance",
        )
        production_review = str(uuid.uuid4())
        production_fail_closed.transition(
            candidate_id="valid-id",
            review_id=production_review,
            actor="menxia",
            **actor_identity("menxia"),
            to_state="metadata_reviewed",
            evidence="production metadata review fixture",
            target="valid.json",
            rollback_hint="retain pending metadata",
        )
        try:
            production_fail_closed.authorize_body(
                candidate_ids=("valid-id",),
                review_id=production_review,
                actor="taizi",
                **actor_identity("taizi"),
                evidence="must fail without host actor capability",
                scope_kind="candidate",
                scope_id="valid-id",
                target="fixture-review",
                rollback_hint="retain pending metadata",
                candidate_bindings={"valid-id": binding},
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("production body authorization did not fail closed without a host-issued actor capability")
        if production_fail_closed.body_access_allowed("valid-id", production_review, binding):
            raise AssertionError("production body access was allowed without a host-issued actor capability")

        return {
            "schema": "court.shiguan_pending_quarantine_plan_check.v1",
            "status": "PASSED",
            "fixture_only": True,
            "pending_bodies": counts["pending_bodies"],
            "classifications": counts["classifications"],
            "quarantine_recommended": counts["quarantine_recommended"],
            "body_open_guard": "PASSED",
            "undecodable_body_fixture": "PASSED",
            "queue_unchanged": "PASSED",
            "apply_surface_absent": "PASSED",
            "governance_state_machine": "PASSED",
            "governance_body_operations": 0,
            "governance_binding": "PASSED",
            "metadata_only_quarantine": "PASSED",
            "reparse_root_rejected": "PASSED",
            "sidecar_identity_swap_rejected": "PASSED",
            "terminal_actor_gate": "PASSED",
            "forged_event_rejected": "PASSED",
            "trusted_actor_identity": "PASSED",
            "independent_snapshot_recompute": "PASSED",
            "external_authenticated_head": "PASSED",
            "unique_event_id": "PASSED",
            "aware_timestamp": "PASSED",
            "production_body_authorization": "HOST_CAPABILITY_REQUIRED_FAIL_CLOSED",
            "snapshot_sha256": plan["snapshot_fingerprint"]["sha256"],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args()
    assert_no_mutation_api()
    result = fixture_check()
    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(
            "SHIGUAN_PENDING_QUARANTINE_PLAN_OK "
            f"bodies={result['pending_bodies']} "
            f"quarantine={result['quarantine_recommended']} "
            f"body_open_guard={result['body_open_guard']} "
            f"apply_surface_absent={result['apply_surface_absent']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
