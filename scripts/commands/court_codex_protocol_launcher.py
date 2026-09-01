"""Append-only quiescent protocol-switch ledger and guarded Codex resume launcher."""

from __future__ import annotations

# A+B layering: real module lives in scripts/commands/; keep scripts root importable.
import sys
from pathlib import Path
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[1])
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)


import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Protocol

sys.dont_write_bytecode = True

from court_file_lock import file_lock
from court_multi_agent_protocol import (
    QuiescenceSnapshot,
    SelectedMode,
    assess_quiescence,
    build_exact_resume_command,
    validate_session_id,
)
from shiguan_paths import reference_path


SCHEMA = "court.multi_agent.protocol_switch.v1"
STATES = (
    "SWITCH_REQUESTED",
    "QUIESCING",
    "SNAPSHOT_SAVED",
    "ENGINE_STOPPED",
    "SESSION_RESUMING",
    "RESUME_VERIFIED",
    "FAILED",
)
TERMINAL_STATES = frozenset({"RESUME_VERIFIED", "FAILED"})
TRANSITIONS = {
    "SWITCH_REQUESTED": {"QUIESCING", "FAILED"},
    "QUIESCING": {"SNAPSHOT_SAVED", "FAILED"},
    "SNAPSHOT_SAVED": {"ENGINE_STOPPED", "FAILED"},
    "ENGINE_STOPPED": {"SESSION_RESUMING", "FAILED"},
    "SESSION_RESUMING": {"RESUME_VERIFIED", "FAILED"},
    "RESUME_VERIFIED": set(),
    "FAILED": set(),
}
PLANNED_EFFECTS = ("engine_stop", "session_resume")


class SwitchInProgress(RuntimeError):
    pass


class EffectOutcomeUnknown(RuntimeError):
    pass


class QuiescenceError(RuntimeError):
    pass


class SwitchEngine(Protocol):
    def stop(self, operation_id: str) -> bool: ...

    def resume(self, operation_id: str, command: tuple[str, ...]) -> bool: ...

    def verify(self, operation_id: str, expected: dict[str, str]) -> bool: ...


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _canonical_uuid(value: object, field: str) -> str:
    try:
        return validate_session_id(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a canonical UUID") from exc


def _validate_protocol(value: object, field: str) -> SelectedMode:
    text = str(value or "").strip().lower()
    if text not in {"v1", "v2", "serial"}:
        raise ValueError(f"{field} must be v1, v2, or serial")
    return text  # type: ignore[return-value]


def _validate_history_digest(value: object) -> str:
    text = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError("history_prefix_sha256 must be a lowercase SHA256 digest")
    return text


class ProtocolSwitchLedger:
    """A single append-only JSONL ledger protected by a cross-process file lock."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or reference_path("court-runtime", "protocol-switches")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "protocol-switches.jsonl"
        self.lock_path = self.root / "protocol-switches.lock"

    def _read_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"protocol switch ledger corrupt at line {line_number}") from exc
                if not isinstance(item, dict) or item.get("schema") != SCHEMA:
                    raise RuntimeError(f"protocol switch ledger schema mismatch at line {line_number}")
                events.append(item)
        return events

    def _append_unlocked(self, record: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _latest_from(events: list[dict[str, Any]], operation_id: str) -> dict[str, Any]:
        matches = [event for event in events if event.get("operation_id") == operation_id]
        if not matches:
            raise KeyError(operation_id)
        return dict(matches[-1])

    def latest(self, operation_id: str) -> dict[str, Any]:
        exact_operation = _canonical_uuid(operation_id, "operation_id")
        with file_lock(self.lock_path):
            return self._latest_from(self._read_unlocked(), exact_operation)

    def event_count(self, operation_id: str) -> int:
        exact_operation = _canonical_uuid(operation_id, "operation_id")
        with file_lock(self.lock_path):
            return sum(1 for event in self._read_unlocked() if event.get("operation_id") == exact_operation)

    def acquire(
        self,
        *,
        operation_id: str,
        session_id: str,
        goal_thread_id: str,
        court_task_id: str,
        from_protocol: SelectedMode,
        to_protocol: SelectedMode,
        history_prefix_sha256: str,
    ) -> dict[str, Any]:
        exact_operation = _canonical_uuid(operation_id, "operation_id")
        exact_session = _canonical_uuid(session_id, "session_id")
        exact_goal = _canonical_uuid(goal_thread_id, "goal_thread_id")
        source = _validate_protocol(from_protocol, "from_protocol")
        target = _validate_protocol(to_protocol, "to_protocol")
        if source == target:
            raise ValueError("protocol switch source and target must differ")
        task_id = str(court_task_id or "").strip()
        if not task_id:
            raise ValueError("court_task_id is required")
        history_digest = _validate_history_digest(history_prefix_sha256)
        with file_lock(self.lock_path):
            events = self._read_unlocked()
            matching = [event for event in events if event.get("operation_id") == exact_operation]
            immutable = {
                "session_id": exact_session,
                "goal_thread_id": exact_goal,
                "court_task_id": task_id,
                "from_protocol": source,
                "to_protocol": target,
                "history_prefix_sha256": history_digest,
            }
            if matching:
                latest = dict(matching[-1])
                if any(latest.get(key) != value for key, value in immutable.items()):
                    raise ValueError("operation_id replay changed immutable switch fields")
                latest["replayed"] = True
                return latest
            latest_by_operation: dict[str, dict[str, Any]] = {}
            for event in events:
                if event.get("session_id") == exact_session:
                    latest_by_operation[str(event.get("operation_id"))] = event
            active = [event for event in latest_by_operation.values() if event.get("state") not in TERMINAL_STATES]
            if active:
                raise SwitchInProgress(f"switch already active for session {exact_session}")
            lease_epoch = 1 + max(
                (int(event.get("lease_epoch", 0)) for event in events if event.get("session_id") == exact_session),
                default=0,
            )
            timestamp = _now()
            record: dict[str, Any] = {
                "schema": SCHEMA,
                "operation_id": exact_operation,
                **immutable,
                "state": "SWITCH_REQUESTED",
                "lease_epoch": lease_epoch,
                "planned_side_effects": list(PLANNED_EFFECTS),
                "prepared_effect_ids": [],
                "completed_effect_ids": [],
                "created_at": timestamp,
                "updated_at": timestamp,
                "replayed": False,
            }
            self._append_unlocked(record)
            return dict(record)

    def transition(self, operation_id: str, to_state: str, *, evidence: str) -> dict[str, Any]:
        exact_operation = _canonical_uuid(operation_id, "operation_id")
        target = str(to_state or "").strip().upper()
        if target not in STATES:
            raise ValueError(f"unknown switch state: {target}")
        with file_lock(self.lock_path):
            events = self._read_unlocked()
            current = self._latest_from(events, exact_operation)
            if current["state"] == target:
                current["replayed"] = True
                return current
            if target not in TRANSITIONS.get(str(current.get("state")), set()):
                raise ValueError(f"illegal switch transition: {current.get('state')} -> {target}")
            updated = dict(current)
            updated.update(
                {
                    "state": target,
                    "updated_at": _now(),
                    "evidence_sha256": hashlib.sha256(str(evidence).encode("utf-8")).hexdigest(),
                    "replayed": False,
                }
            )
            self._append_unlocked(updated)
            return updated

    def prepare_effect(self, operation_id: str, effect_id: str) -> dict[str, Any]:
        exact_operation = _canonical_uuid(operation_id, "operation_id")
        effect = str(effect_id or "").strip()
        if effect not in PLANNED_EFFECTS:
            raise ValueError(f"unplanned side effect: {effect}")
        with file_lock(self.lock_path):
            events = self._read_unlocked()
            current = self._latest_from(events, exact_operation)
            completed = list(current.get("completed_effect_ids") or [])
            prepared = list(current.get("prepared_effect_ids") or [])
            if effect in completed:
                current["replayed"] = True
                return current
            if effect in prepared:
                raise EffectOutcomeUnknown(f"side effect outcome unknown: {effect}")
            prepared.append(effect)
            updated = dict(current)
            updated.update({"prepared_effect_ids": prepared, "updated_at": _now(), "replayed": False})
            self._append_unlocked(updated)
            return updated

    def complete_effect(self, operation_id: str, effect_id: str) -> dict[str, Any]:
        exact_operation = _canonical_uuid(operation_id, "operation_id")
        effect = str(effect_id or "").strip()
        with file_lock(self.lock_path):
            events = self._read_unlocked()
            current = self._latest_from(events, exact_operation)
            completed = list(current.get("completed_effect_ids") or [])
            prepared = list(current.get("prepared_effect_ids") or [])
            if effect in completed:
                current["replayed"] = True
                return current
            if effect not in prepared:
                raise ValueError(f"effect was not prepared: {effect}")
            completed.append(effect)
            updated = dict(current)
            updated.update({"completed_effect_ids": completed, "updated_at": _now(), "replayed": False})
            self._append_unlocked(updated)
            return updated


def execute_switch(
    *,
    ledger: ProtocolSwitchLedger,
    operation_id: str,
    session_id: str,
    goal_thread_id: str,
    court_task_id: str,
    from_protocol: SelectedMode,
    to_protocol: SelectedMode,
    quiescence: QuiescenceSnapshot,
    resume_command: tuple[str, ...],
    history_prefix_sha256: str,
    engine: SwitchEngine,
) -> dict[str, Any]:
    gate = assess_quiescence(quiescence)
    if not gate.ok:
        raise QuiescenceError("quiescence gate failed: " + ", ".join(gate.errors))
    exact_session = validate_session_id(session_id)
    if gate.session_id != exact_session:
        raise QuiescenceError("quiescence session does not match requested session")
    if tuple(resume_command)[-2] != exact_session:
        raise ValueError("resume command session does not match switch session")
    current = ledger.acquire(
        operation_id=operation_id,
        session_id=exact_session,
        goal_thread_id=goal_thread_id,
        court_task_id=court_task_id,
        from_protocol=from_protocol,
        to_protocol=to_protocol,
        history_prefix_sha256=history_prefix_sha256,
    )
    if current.get("state") == "RESUME_VERIFIED":
        current["replayed"] = True
        return current
    if current.get("state") == "FAILED":
        current["replayed"] = True
        return current
    try:
        if current["state"] == "SWITCH_REQUESTED":
            current = ledger.transition(operation_id, "QUIESCING", evidence="quiescence verified")
        if current["state"] == "QUIESCING":
            current = ledger.transition(operation_id, "SNAPSHOT_SAVED", evidence="durable snapshot saved")
        if current["state"] == "SNAPSHOT_SAVED":
            current = ledger.prepare_effect(operation_id, "engine_stop")
            if not engine.stop(operation_id):
                ledger.transition(operation_id, "FAILED", evidence="engine stop rejected")
                raise RuntimeError("engine stop failed")
            current = ledger.complete_effect(operation_id, "engine_stop")
            current = ledger.transition(operation_id, "ENGINE_STOPPED", evidence="engine stop acknowledged")
        if current["state"] == "ENGINE_STOPPED":
            current = ledger.prepare_effect(operation_id, "session_resume")
            if not engine.resume(operation_id, resume_command):
                ledger.transition(operation_id, "FAILED", evidence="session resume rejected")
                raise RuntimeError("session resume failed")
            current = ledger.complete_effect(operation_id, "session_resume")
            current = ledger.transition(operation_id, "SESSION_RESUMING", evidence="session resume acknowledged")
        if current["state"] == "SESSION_RESUMING":
            expected = {
                "session_id": exact_session,
                "goal_thread_id": validate_session_id(goal_thread_id),
                "court_task_id": str(court_task_id),
                "history_prefix_sha256": _validate_history_digest(history_prefix_sha256),
                "protocol": _validate_protocol(to_protocol, "to_protocol"),
            }
            if not engine.verify(operation_id, expected):
                ledger.transition(operation_id, "FAILED", evidence="resume verification failed")
                raise RuntimeError("resume verification failed")
            current = ledger.transition(operation_id, "RESUME_VERIFIED", evidence="resume verification passed")
    except EffectOutcomeUnknown:
        raise
    return current


def _snapshot_from_json(path: Path) -> QuiescenceSnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("quiescence snapshot must be a JSON object")
    return QuiescenceSnapshot(**payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Validate a switch plan without writing or stopping an engine.")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--goal-thread-id", required=True)
    parser.add_argument("--court-task-id", required=True)
    parser.add_argument("--from-protocol", choices=("v1", "v2", "serial"), required=True)
    parser.add_argument("--to-protocol", choices=("v1", "v2", "serial"), required=True)
    parser.add_argument("--history-prefix-sha256", required=True)
    parser.add_argument("--quiescence-json", type=Path, required=True)
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--internal-prompt", required=True)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)
    if not args.check_only:
        parser.error("CLI apply requires a host controller; use --check-only")
    snapshot = _snapshot_from_json(args.quiescence_json)
    gate = assess_quiescence(snapshot)
    command = build_exact_resume_command(args.codex_executable, args.session_id, args.internal_prompt)
    payload = {
        "schema": "court.multi_agent.protocol_switch.check.v1",
        "ok": gate.ok,
        "errors": list(gate.errors),
        "session_id": validate_session_id(args.session_id),
        "goal_thread_id": validate_session_id(args.goal_thread_id),
        "court_task_id": args.court_task_id,
        "from_protocol": args.from_protocol,
        "to_protocol": args.to_protocol,
        "history_prefix_sha256": _validate_history_digest(args.history_prefix_sha256),
        "resume_argv_shape": [Path(command[0]).name, *command[1:3], "<internal-prompt>"],
        "quiescence": asdict(snapshot),
        "writes_performed": False,
        "engine_stopped": False,
    }
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"protocol_switch_check ok={payload['ok']} errors={','.join(payload['errors']) or 'none'}")
    return 0 if gate.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())



