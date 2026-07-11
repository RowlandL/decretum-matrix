"""Append-only metadata governance for pending Shiguan candidates.

This module never opens, hashes, moves, deletes, or marks a pending body. It
records metadata review state and a fixture-tested authorization contract;
production body authorization remains fail-closed until the host supplies a
non-forgeable actor capability. Queue mutation is always a separate concern.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable
import uuid

sys.dont_write_bytecode = True

from court_file_lock import file_lock, fsync_parent_directory
from shiguan_pending_trust import GovernanceTrust, TRUST_FIELDS, ZERO_SHA256
from shiguan_paths import reference_path


SCHEMA = "court.shiguan_pending_governance.v3"
STATES = (
    "pending",
    "metadata_reviewed",
    "body_authorized",
    "reviewed",
    "promoted",
    "rejected",
    "quarantined",
)
TERMINAL_STATES = frozenset({"promoted", "rejected", "quarantined"})
TRANSITIONS = {
    "pending": {"metadata_reviewed"},
    "metadata_reviewed": {"body_authorized", "rejected", "quarantined"},
    "body_authorized": {"reviewed"},
    "reviewed": set(TERMINAL_STATES),
    "promoted": set(),
    "rejected": set(),
    "quarantined": set(),
}
ACTORS = frozenset(
    {
        "taizi",
        "zhongshu",
        "menxia",
        "shangshu",
        "hubu",
        "libu",
        "bingbu",
        "xingbu",
        "gongbu",
        "libu-hr",
        "shiguan",
        "zaochao",
    }
)
ACTORS_BY_STATE = {
    "metadata_reviewed": frozenset({"zhongshu", "menxia", "shangshu", "xingbu", "shiguan"}),
    "body_authorized": frozenset({"taizi", "menxia"}),
    "reviewed": frozenset({"menxia", "xingbu"}),
    "promoted": frozenset({"menxia"}),
    "rejected": frozenset({"menxia", "xingbu"}),
    "quarantined": frozenset({"menxia", "xingbu"}),
}
ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BINDING_FIELDS = frozenset(
    {
        "candidate_id",
        "filename",
        "source_fingerprint_sha256",
        "sidecar_metadata_sha256",
        "declared_body_sha256",
        "plan_snapshot_sha256",
    }
)
EVENT_FIELDS = frozenset(
    {
        "schema",
        "event_id",
        "candidate_id",
        "review_id",
        "actor",
        "from_state",
        "state",
        "evidence_sha256",
        "target",
        "rollback_hint_sha256",
        "review_result_sha256",
        "body_authorization_explicit",
        "authorization_scope",
        "authorization_binding",
        "metadata_only_decision",
        "queue_mutations",
        "body_operations",
        "created_at",
    }
) | TRUST_FIELDS
BODY_OPERATION_COUNTERS = {
    "open": 0,
    "read": 0,
    "hash": 0,
    "move": 0,
    "delete": 0,
    "mark_seen": 0,
}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _safe_id(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not ID_RE.fullmatch(text):
        raise ValueError(f"{field} must be a bounded identifier")
    return text


def _review_id(value: object) -> str:
    text = str(value or "").strip()
    try:
        parsed = uuid.UUID(text)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("review_id must be a canonical UUID") from exc
    if str(parsed) != text.lower():
        raise ValueError("review_id must be a canonical UUID")
    return str(parsed)


def _safe_actor(value: object) -> str:
    actor = str(value or "").strip().lower()
    if actor not in ACTORS:
        raise ValueError("unknown governance actor")
    return actor


def _safe_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 512 or any(ord(char) < 32 for char in text):
        raise ValueError(f"{field} must be bounded non-secret text")
    if re.search(r"(?i)(?:[a-z]:[\\/]|\\\\|(?:^|\s)/[^\s]+)", text):
        raise ValueError(f"{field} must not contain an absolute path")
    return text


def _sha256_text(value: object, field: str) -> str:
    text = _safe_text(value, field)
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()


def _sha256_digest(value: object, field: str) -> str:
    text = str(value or "").strip().lower()
    if not SHA256_RE.fullmatch(text):
        raise ValueError(f"{field} must be a lowercase SHA256 digest")
    return text


def _canonical_uuid(value: object, field: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = uuid.UUID(text)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"{field} must be a canonical UUID") from exc
    if str(parsed) != text.lower():
        raise ValueError(f"{field} must be a canonical UUID")
    return str(parsed)


def _safe_binding(value: object, candidate_id: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != BINDING_FIELDS:
        raise ValueError("authorization binding fields are invalid")
    candidate = _safe_id(value.get("candidate_id"), "binding.candidate_id")
    if candidate != candidate_id:
        raise ValueError("authorization binding candidate mismatch")
    filename = str(value.get("filename") or "").strip()
    if not filename or Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise ValueError("authorization binding filename is invalid")
    return {
        "candidate_id": candidate,
        "filename": filename,
        "source_fingerprint_sha256": _sha256_digest(value.get("source_fingerprint_sha256"), "binding.source_fingerprint_sha256"),
        "sidecar_metadata_sha256": _sha256_digest(value.get("sidecar_metadata_sha256"), "binding.sidecar_metadata_sha256"),
        "declared_body_sha256": _sha256_digest(value.get("declared_body_sha256"), "binding.declared_body_sha256"),
        "plan_snapshot_sha256": _sha256_digest(value.get("plan_snapshot_sha256"), "binding.plan_snapshot_sha256"),
    }


def _safe_scope(value: object, candidate_id: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"kind", "id", "candidate_ids"}:
        raise ValueError("authorization scope is invalid")
    kind = str(value.get("kind") or "").strip().lower()
    scope_id = _safe_id(value.get("id"), "authorization_scope.id")
    raw_candidates = value.get("candidate_ids")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValueError("authorization scope candidates are invalid")
    candidates = [_safe_id(item, "authorization_scope.candidate_id") for item in raw_candidates]
    if len(candidates) != len(set(candidates)) or candidate_id not in candidates:
        raise ValueError("authorization scope does not bind the candidate")
    if kind == "candidate":
        if candidates != [candidate_id] or scope_id != candidate_id:
            raise ValueError("candidate authorization scope is invalid")
    elif kind != "batch":
        raise ValueError("authorization scope kind is invalid")
    return {"kind": kind, "id": scope_id, "candidate_ids": candidates}


class PendingGovernanceLedger:
    def __init__(
        self,
        root: Path | None = None,
        *,
        pending_root: Path | None = None,
        runtime_tasks_path: Path | None = None,
        trust_root: Path | None = None,
        fixture_mode: bool = False,
    ) -> None:
        self.root = (root or reference_path("shiguan-imports", "governance")).resolve()
        self.path = self.root / "pending-governance.v3.jsonl"
        self.lock_path = self.root / "pending-governance.lock"
        self.pending_root = (pending_root or reference_path("shiguan-imports", "pending")).expanduser().absolute()
        self.fixture_mode = fixture_mode is True
        self.trust = GovernanceTrust(
            self.root,
            runtime_tasks_path=runtime_tasks_path,
            trust_root=trust_root,
        )

    def _validate_events(self, events: list[dict[str, Any]], key: bytes) -> list[dict[str, Any]]:
        latest_by_candidate: dict[str, dict[str, Any]] = {}
        normalized: list[dict[str, Any]] = []
        seen_event_ids: set[str] = set()
        previous_event_sha256 = ZERO_SHA256
        previous_created_at = None
        for line_number, raw in enumerate(events, start=1):
            try:
                if not isinstance(raw, dict) or set(raw) != EVENT_FIELDS or raw.get("schema") != SCHEMA:
                    raise ValueError("event fields or schema mismatch")
                event = dict(raw)
                previous_created_at = self.trust.validate_event_envelope(
                    event,
                    line_number=line_number,
                    previous_event_sha256=previous_event_sha256,
                    previous_created_at=previous_created_at,
                    seen_event_ids=seen_event_ids,
                    key=key,
                )
                event["event_id"] = _canonical_uuid(event.get("event_id"), "event_id")
                candidate = _safe_id(event.get("candidate_id"), "candidate_id")
                review = _review_id(event.get("review_id"))
                actor = _safe_actor(event.get("actor"))
                state = str(event.get("state") or "").strip().lower()
                from_state = str(event.get("from_state") or "").strip().lower()
                if state not in STATES or from_state not in STATES:
                    raise ValueError("state is invalid")
                if actor not in ACTORS_BY_STATE.get(state, frozenset()):
                    raise ValueError("actor is not authorized for transition")
                prior = latest_by_candidate.get(candidate)
                expected_from = str((prior or {}).get("state") or "pending")
                if from_state != expected_from or state not in TRANSITIONS.get(from_state, set()):
                    raise ValueError("event chain transition is invalid")
                if prior and prior.get("review_id") != review:
                    raise ValueError("event chain changed review_id")
                event["evidence_sha256"] = _sha256_digest(event.get("evidence_sha256"), "evidence_sha256")
                event["rollback_hint_sha256"] = _sha256_digest(event.get("rollback_hint_sha256"), "rollback_hint_sha256")
                event["target"] = _safe_text(event.get("target"), "target")
                if event.get("queue_mutations") != 0 or event.get("body_operations") != BODY_OPERATION_COUNTERS:
                    raise ValueError("event reports forbidden queue/body operations")

                explicit = event.get("body_authorization_explicit") is True
                metadata_only = event.get("metadata_only_decision") is True
                binding = event.get("authorization_binding")
                scope = event.get("authorization_scope")
                if state == "body_authorized":
                    event["authorization_binding"] = _safe_binding(binding, candidate)
                    event["authorization_scope"] = _safe_scope(scope, candidate)
                    if not explicit or metadata_only:
                        raise ValueError("body authorization flags are invalid")
                elif from_state in {"body_authorized", "reviewed"}:
                    event["authorization_binding"] = _safe_binding(binding, candidate)
                    event["authorization_scope"] = _safe_scope(scope, candidate)
                    if not explicit or metadata_only:
                        raise ValueError("authorized review chain flags are invalid")
                    if prior and (
                        event["authorization_binding"] != prior.get("authorization_binding")
                        or event["authorization_scope"] != prior.get("authorization_scope")
                    ):
                        raise ValueError("authorization binding changed in review chain")
                elif state in {"rejected", "quarantined"} and from_state == "metadata_reviewed":
                    if explicit or not metadata_only or binding is not None or scope is not None:
                        raise ValueError("metadata-only terminal flags are invalid")
                else:
                    if explicit or metadata_only or binding is not None or scope is not None:
                        raise ValueError("unauthorized binding appeared before body authorization")

                review_digest = event.get("review_result_sha256")
                if state == "reviewed":
                    event["review_result_sha256"] = _sha256_digest(review_digest, "review_result_sha256")
                elif review_digest is not None:
                    raise ValueError("review_result_sha256 appeared outside reviewed state")
                event["candidate_id"] = candidate
                event["review_id"] = review
                event["actor"] = actor
                event["from_state"] = from_state
                event["state"] = state
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"pending governance event invalid at line {line_number}: {exc}") from exc
            latest_by_candidate[candidate] = event
            normalized.append(event)
            previous_event_sha256 = event["event_sha256"]
        return normalized

    def _read_unlocked(self) -> list[dict[str, Any]]:
        ledger_exists = self.path.exists()
        head_exists = self.trust.head_path.exists()
        if not ledger_exists:
            self.trust.verify_head([], self.trust.key_for_read(ledger_exists=False, head_exists=head_exists))
            return []
        key = self.trust.key_for_read(ledger_exists=True, head_exists=head_exists)
        if key is None:
            raise RuntimeError("pending governance trust key is unavailable")
        events: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"pending governance ledger corrupt at line {line_number}") from exc
                events.append(event)
        normalized = self._validate_events(events, key)
        self.trust.verify_head(normalized, key)
        return normalized

    def _append_many_unlocked(self, records: Iterable[dict[str, Any]], all_events: list[dict[str, Any]], key: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        serialized = "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        )
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        fsync_parent_directory(self.root)
        self.trust.append_head(all_events, key)

    @staticmethod
    def _latest_from(events: list[dict[str, Any]], candidate_id: str) -> dict[str, Any] | None:
        matches = [event for event in events if event.get("candidate_id") == candidate_id]
        return dict(matches[-1]) if matches else None

    def latest(self, candidate_id: str) -> dict[str, Any]:
        candidate = _safe_id(candidate_id, "candidate_id")
        with file_lock(self.lock_path):
            latest = self._latest_from(self._read_unlocked(), candidate)
        return latest or {"schema": SCHEMA, "candidate_id": candidate, "state": "pending", "queue_mutations": 0}

    def event_count(self, candidate_id: str) -> int:
        candidate = _safe_id(candidate_id, "candidate_id")
        with file_lock(self.lock_path):
            return sum(1 for event in self._read_unlocked() if event.get("candidate_id") == candidate)

    def body_operation_counters(self) -> dict[str, int]:
        return dict(BODY_OPERATION_COUNTERS)

    def _current_binding(self, candidate_id: str) -> dict[str, str]:
        from plan_shiguan_pending_quarantine import build_plan

        candidate = _safe_id(candidate_id, "candidate_id")
        plan = build_plan(self.pending_root)
        if plan.get("status") == "queue_unavailable" or plan.get("errors"):
            raise ValueError("pending queue snapshot cannot be independently verified")
        matches = [
            item.get("governance_binding")
            for item in plan.get("items", [])
            if isinstance(item, dict)
            and isinstance(item.get("governance_binding"), dict)
            and item["governance_binding"].get("candidate_id") == candidate
        ]
        if len(matches) != 1:
            raise ValueError("candidate is not uniquely present in a valid metadata snapshot")
        return _safe_binding(matches[0], candidate)

    def _sealed_record(
        self,
        record: dict[str, Any],
        events: list[dict[str, Any]],
        *,
        actor: str,
        task_id: str,
        agent_id: str,
        key: bytes,
    ) -> dict[str, Any]:
        identity = self.trust.derive_actor_identity(
            actor=actor,
            task_id=task_id,
            agent_id=agent_id,
        )
        return self.trust.seal_event(record, events, identity, key)

    def body_access_allowed(
        self,
        candidate_id: str,
        review_id: str,
        authorization_binding: dict[str, object] | None = None,
    ) -> bool:
        if not self.fixture_mode or authorization_binding is None:
            return False
        candidate = _safe_id(candidate_id, "candidate_id")
        binding = _safe_binding(authorization_binding, candidate)
        latest = self.latest(candidate_id)
        try:
            current_binding = self._current_binding(candidate)
        except ValueError:
            return False
        return bool(
            latest.get("review_id") == _review_id(review_id)
            and latest.get("state") in {"body_authorized", "reviewed"}
            and latest.get("body_authorization_explicit") is True
            and latest.get("authorization_binding") == binding
            and binding == current_binding
        )

    def transition(
        self,
        *,
        candidate_id: str,
        review_id: str,
        actor: str,
        task_id: str,
        agent_id: str,
        to_state: str,
        evidence: str,
        target: str,
        rollback_hint: str,
        review_result_sha256: str | None = None,
    ) -> dict[str, Any]:
        candidate = _safe_id(candidate_id, "candidate_id")
        review = _review_id(review_id)
        office = _safe_actor(actor)
        target_state = str(to_state or "").strip().lower()
        if target_state == "body_authorized":
            raise ValueError("body_authorized requires authorize_body with explicit scope")
        if target_state not in STATES:
            raise ValueError("unknown pending governance state")
        if office not in ACTORS_BY_STATE.get(target_state, frozenset()):
            raise ValueError("actor is not authorized for this governance transition")
        target_text = _safe_text(target, "target")
        evidence_sha256 = _sha256_text(evidence, "evidence")
        rollback_sha256 = _sha256_text(rollback_hint, "rollback_hint")
        self.root.mkdir(parents=True, exist_ok=True)
        with file_lock(self.lock_path):
            events = self._read_unlocked()
            key = self.trust.ensure_key()
            current = self._latest_from(events, candidate)
            from_state = str((current or {}).get("state") or "pending")
            if current and current.get("review_id") != review:
                raise ValueError("candidate is already bound to another review_id")
            if target_state not in TRANSITIONS.get(from_state, set()):
                raise ValueError(f"illegal pending transition: {from_state} -> {target_state}")
            if target_state == "reviewed":
                digest = _sha256_digest(review_result_sha256, "review_result_sha256")
            else:
                if review_result_sha256 is not None:
                    raise ValueError("review_result_sha256 is only accepted for reviewed")
                digest = None
            if from_state in {"body_authorized", "reviewed"}:
                if (current or {}).get("authorization_binding") != self._current_binding(candidate):
                    raise ValueError("authorized candidate metadata snapshot changed")
            timestamp = _now()
            metadata_only_decision = target_state in {"rejected", "quarantined"} and from_state == "metadata_reviewed"
            base_record: dict[str, Any] = {
                "schema": SCHEMA,
                "event_id": str(uuid.uuid4()),
                "candidate_id": candidate,
                "review_id": review,
                "actor": office,
                "from_state": from_state,
                "state": target_state,
                "evidence_sha256": evidence_sha256,
                "target": target_text,
                "rollback_hint_sha256": rollback_sha256,
                "review_result_sha256": digest,
                "body_authorization_explicit": bool((current or {}).get("body_authorization_explicit")) and not metadata_only_decision,
                "authorization_scope": None if metadata_only_decision else (current or {}).get("authorization_scope"),
                "authorization_binding": None if metadata_only_decision else (current or {}).get("authorization_binding"),
                "metadata_only_decision": metadata_only_decision,
                "queue_mutations": 0,
                "body_operations": dict(BODY_OPERATION_COUNTERS),
                "created_at": timestamp,
            }
            record = self._sealed_record(
                base_record,
                events,
                actor=office,
                task_id=task_id,
                agent_id=agent_id,
                key=key,
            )
            all_events = self._validate_events([*events, record], key)
            self._append_many_unlocked([record], all_events, key)
            return dict(record)

    def authorize_body(
        self,
        *,
        candidate_ids: tuple[str, ...],
        review_id: str,
        actor: str,
        task_id: str,
        agent_id: str,
        evidence: str,
        scope_kind: str,
        scope_id: str,
        target: str,
        rollback_hint: str,
        candidate_bindings: dict[str, dict[str, object]],
    ) -> list[dict[str, Any]]:
        if not self.fixture_mode:
            raise RuntimeError(
                "body authorization requires a host-issued actor capability; current host integration is unavailable"
            )
        candidates = tuple(dict.fromkeys(_safe_id(value, "candidate_id") for value in candidate_ids))
        if not candidates:
            raise ValueError("explicit candidate_ids are required")
        review = _review_id(review_id)
        office = _safe_actor(actor)
        if office not in ACTORS_BY_STATE["body_authorized"]:
            raise ValueError("actor is not authorized to grant body access")
        scope = str(scope_kind or "").strip().lower()
        scope_value = _safe_id(scope_id, "scope_id")
        if scope == "candidate":
            if len(candidates) != 1 or candidates[0] != scope_value:
                raise ValueError("candidate authorization scope must name exactly that candidate")
        elif scope != "batch":
            raise ValueError("scope_kind must be candidate or batch")
        evidence_sha256 = _sha256_text(evidence, "evidence")
        target_text = _safe_text(target, "target")
        rollback_sha256 = _sha256_text(rollback_hint, "rollback_hint")
        self.root.mkdir(parents=True, exist_ok=True)
        with file_lock(self.lock_path):
            events = self._read_unlocked()
            key = self.trust.ensure_key()
            records: list[dict[str, Any]] = []
            timestamp = _now()
            for candidate in candidates:
                current = self._latest_from(events, candidate)
                if not current or current.get("state") != "metadata_reviewed":
                    raise ValueError(f"candidate is not metadata_reviewed: {candidate}")
                if current.get("review_id") != review:
                    raise ValueError("authorization review_id mismatch")
                raw_binding = candidate_bindings.get(candidate) if isinstance(candidate_bindings, dict) else None
                binding = _safe_binding(raw_binding, candidate)
                if binding != self._current_binding(candidate):
                    raise ValueError("authorization binding does not match an independently recomputed pending snapshot")
                base_record = {
                        "schema": SCHEMA,
                        "event_id": str(uuid.uuid4()),
                        "candidate_id": candidate,
                        "review_id": review,
                        "actor": office,
                        "from_state": "metadata_reviewed",
                        "state": "body_authorized",
                        "evidence_sha256": evidence_sha256,
                        "target": target_text,
                        "rollback_hint_sha256": rollback_sha256,
                        "review_result_sha256": None,
                        "body_authorization_explicit": True,
                        "authorization_scope": {"kind": scope, "id": scope_value, "candidate_ids": list(candidates)},
                        "authorization_binding": binding,
                        "metadata_only_decision": False,
                        "queue_mutations": 0,
                        "body_operations": dict(BODY_OPERATION_COUNTERS),
                        "created_at": timestamp,
                    }
                record = self._sealed_record(
                    base_record,
                    [*events, *records],
                    actor=office,
                    task_id=task_id,
                    agent_id=agent_id,
                    key=key,
                )
                records.append(record)
            all_events = self._validate_events([*events, *records], key)
            self._append_many_unlocked(records, all_events, key)
            return [dict(record) for record in records]


def main(argv: list[str] | None = None) -> int:
    from shiguan_pending_governance_cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
