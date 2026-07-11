"""Authenticated envelope and external head for pending-governance events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
import sys
from typing import Any
import uuid

sys.dont_write_bytecode = True

from court_file_lock import fsync_parent_directory
from shiguan_paths import reference_path, shared_root


TRUST_FIELDS = frozenset(
    {
        "sequence",
        "previous_event_sha256",
        "actor_identity",
        "event_sha256",
        "record_hmac_sha256",
    }
)
HEAD_SCHEMA = "court.shiguan_pending_governance_head.v1"
HEAD_FIELDS = frozenset(
    {
        "schema",
        "checkpoint_id",
        "previous_checkpoint_sha256",
        "event_count",
        "last_sequence",
        "last_event_sha256",
        "created_at",
        "checkpoint_sha256",
        "checkpoint_hmac_sha256",
    }
)
ZERO_SHA256 = "0" * 64
SHA256_RE = __import__("re").compile(r"^[0-9a-f]{64}$")
AGENT_ID_RE = __import__("re").compile(r"^(?:/root(?:/[A-Za-z0-9_-]+){0,4}|[0-9a-f-]{36})$")
TERMINAL_TASK_STATES = frozenset({"Done", "Cancelled", "Failed", "Paused"})


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: object, field: str) -> str:
    text = str(value or "").strip().lower()
    if not SHA256_RE.fullmatch(text):
        raise ValueError(f"{field} must be a lowercase SHA256 digest")
    return text


def _bounded(value: object, field: str, *, maximum: int = 512) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum or any(ord(char) < 32 for char in text):
        raise ValueError(f"{field} must be bounded text")
    return text


def _timestamp(value: object, field: str, *, enforce_future_bound: bool = False) -> tuple[str, datetime]:
    text = _bounded(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    if parsed.isoformat(timespec="seconds") != text:
        raise ValueError(f"{field} must be canonical to whole seconds")
    if enforce_future_bound and parsed.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError(f"{field} is implausibly far in the future")
    return text, parsed.astimezone(timezone.utc)


def _is_reparse(value: os.stat_result) -> bool:
    return bool(int(getattr(value, "st_file_attributes", 0) or 0) & 0x400)


def _outside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return True
    return False


def _identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mode


def _read_regular(path: Path, *, label: str, maximum: int, exact: int | None = None) -> bytes:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or _is_reparse(before) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError(f"{label} is not a strict regular file")
    if before.st_size > maximum or (exact is not None and before.st_size != exact):
        raise RuntimeError(f"{label} has an invalid size")
    flags = os.O_RDONLY | int(getattr(os, "O_BINARY", 0) or 0) | int(getattr(os, "O_NOFOLLOW", 0) or 0)
    descriptor = os.open(str(path), flags)
    try:
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before) or _is_reparse(opened) or not stat.S_ISREG(opened.st_mode):
            raise RuntimeError(f"{label} changed before read")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise RuntimeError(f"{label} exceeded its read limit")
        after = os.fstat(descriptor)
        if _identity(after) != _identity(opened):
            raise RuntimeError(f"{label} changed during read")
    finally:
        os.close(descriptor)
    value = b"".join(chunks)
    if exact is not None and len(value) != exact:
        raise RuntimeError(f"{label} changed size during read")
    return value


class GovernanceTrust:
    """Bind events to runtime identities and an authenticated external checkpoint."""

    def __init__(
        self,
        ledger_root: Path,
        *,
        runtime_tasks_path: Path | None = None,
        trust_root: Path | None = None,
    ) -> None:
        self.ledger_root = Path(ledger_root).expanduser().absolute()
        self.runtime_tasks_path = Path(
            runtime_tasks_path or reference_path("court-runtime", "tasks.json")
        ).expanduser().absolute()
        self.trust_root = Path(
            trust_root or (shared_root() / "private-runtime" / "pending-governance")
        ).expanduser().absolute()
        if not _outside(self.trust_root, self.ledger_root):
            raise ValueError("governance trust root must be outside the append-only ledger root")
        self.key_path = self.trust_root / "pending-governance-v3.key"
        self.head_path = self.trust_root / "pending-governance-head.v3.jsonl"

    def _ensure_trust_root(self) -> None:
        self.trust_root.mkdir(parents=True, exist_ok=True)
        directory = self.trust_root.lstat()
        if stat.S_ISLNK(directory.st_mode) or _is_reparse(directory) or not stat.S_ISDIR(directory.st_mode):
            raise RuntimeError("pending governance trust root is not a strict directory")

    def _load_key(self, *, required: bool) -> bytes | None:
        try:
            info = self.key_path.lstat()
        except FileNotFoundError:
            if required:
                raise RuntimeError("pending governance trust key is missing")
            return None
        return _read_regular(
            self.key_path,
            label="pending governance trust key",
            maximum=32,
            exact=32,
        )

    def key_for_read(self, *, ledger_exists: bool, head_exists: bool) -> bytes | None:
        if not ledger_exists and not head_exists:
            return self._load_key(required=False)
        return self._load_key(required=True)

    def ensure_key(self) -> bytes:
        existing = self._load_key(required=False)
        if existing is not None:
            return existing
        self._ensure_trust_root()
        value = secrets.token_bytes(32)
        try:
            descriptor = os.open(
                str(self.key_path),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | int(getattr(os, "O_BINARY", 0) or 0),
                0o600,
            )
        except FileExistsError:
            return self._load_key(required=True) or b""
        try:
            written = 0
            while written < len(value):
                written += os.write(descriptor, value[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.chmod(self.key_path, 0o600)
        except OSError:
            pass
        fsync_parent_directory(self.trust_root)
        return value

    def _runtime_tasks(self) -> dict[str, Any]:
        try:
            raw = _read_regular(
                self.runtime_tasks_path,
                label="trusted court runtime task ledger",
                maximum=16 * 1024 * 1024,
            )
        except FileNotFoundError as exc:
            raise ValueError("trusted court runtime task ledger is missing") from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
            raise ValueError("trusted court runtime task ledger is unreadable") from exc
        if not isinstance(value, dict):
            raise ValueError("trusted court runtime task ledger root is invalid")
        return value

    def derive_actor_identity(self, *, actor: str, task_id: str, agent_id: str) -> dict[str, str]:
        tasks = self._runtime_tasks()
        task_key = _bounded(task_id, "task_id", maximum=256)
        task = tasks.get(task_key)
        if not isinstance(task, dict) or task.get("task_id") not in {None, task_key}:
            raise ValueError("actor task is absent from the trusted runtime ledger")
        state = _bounded(task.get("state"), "task.state", maximum=64)
        if state in TERMINAL_TASK_STATES:
            raise ValueError("actor task is not live")
        if actor == "taizi":
            if agent_id != "/root":
                raise ValueError("taizi governance writes require the root thread identity")
            created_at, _ = _timestamp(task.get("created_at"), "task.created_at")
            return {
                "kind": "root_thread",
                "task_id": task_key,
                "agent_id": "/root",
                "role": "taizi",
                "task_created_at": created_at,
            }
        if not AGENT_ID_RE.fullmatch(str(agent_id or "")):
            raise ValueError("agent_id is not a canonical collaboration identity")
        agents = task.get("agents")
        record = agents.get(agent_id) if isinstance(agents, dict) else None
        if not isinstance(record, dict) or record.get("role") != actor or record.get("agent_id") not in {None, agent_id}:
            raise ValueError("actor role does not match the trusted runtime identity")
        if record.get("status") != "running":
            raise ValueError("office actor is not currently running")
        for field in ("preload_status", "office_identity_evidence", "model_route_status"):
            if record.get(field) != "PASSED":
                raise ValueError(f"office actor lacks trusted {field}")
        preload_at, _ = _timestamp(record.get("preload_ack_at"), "actor.preload_ack_at")
        return {
            "kind": "court_agent",
            "task_id": task_key,
            "agent_id": str(agent_id),
            "role": actor,
            "model_route_id": _bounded(record.get("model_route_id"), "actor.model_route_id", maximum=128),
            "profile_hash": _digest(record.get("profile_hash"), "actor.profile_hash"),
            "dossier_hash": _digest(record.get("dossier_hash"), "actor.dossier_hash"),
            "court_skill_hash": _digest(record.get("court_skill_hash"), "actor.court_skill_hash"),
            "preload_ack_at": preload_at,
        }

    @staticmethod
    def normalize_actor_identity(value: object, *, actor: str) -> dict[str, str]:
        if not isinstance(value, dict):
            raise ValueError("actor_identity must be an object")
        kind = value.get("kind")
        if kind == "root_thread":
            fields = {"kind", "task_id", "agent_id", "role", "task_created_at"}
            if set(value) != fields or value.get("agent_id") != "/root" or actor != "taizi" or value.get("role") != actor:
                raise ValueError("root actor identity is invalid")
            created_at, _ = _timestamp(value.get("task_created_at"), "actor_identity.task_created_at")
            return {
                "kind": "root_thread",
                "task_id": _bounded(value.get("task_id"), "actor_identity.task_id", maximum=256),
                "agent_id": "/root",
                "role": actor,
                "task_created_at": created_at,
            }
        fields = {
            "kind", "task_id", "agent_id", "role", "model_route_id", "profile_hash",
            "dossier_hash", "court_skill_hash", "preload_ack_at",
        }
        if kind != "court_agent" or set(value) != fields or value.get("role") != actor:
            raise ValueError("office actor identity is invalid")
        agent_id = str(value.get("agent_id") or "")
        if not AGENT_ID_RE.fullmatch(agent_id):
            raise ValueError("actor_identity.agent_id is invalid")
        preload_at, _ = _timestamp(value.get("preload_ack_at"), "actor_identity.preload_ack_at")
        return {
            "kind": "court_agent",
            "task_id": _bounded(value.get("task_id"), "actor_identity.task_id", maximum=256),
            "agent_id": agent_id,
            "role": actor,
            "model_route_id": _bounded(value.get("model_route_id"), "actor_identity.model_route_id", maximum=128),
            "profile_hash": _digest(value.get("profile_hash"), "actor_identity.profile_hash"),
            "dossier_hash": _digest(value.get("dossier_hash"), "actor_identity.dossier_hash"),
            "court_skill_hash": _digest(value.get("court_skill_hash"), "actor_identity.court_skill_hash"),
            "preload_ack_at": preload_at,
        }

    def seal_event(self, event: dict[str, Any], prior_events: list[dict[str, Any]], identity: dict[str, str], key: bytes) -> dict[str, Any]:
        record = dict(event)
        record["sequence"] = len(prior_events) + 1
        record["previous_event_sha256"] = str((prior_events[-1] if prior_events else {}).get("event_sha256") or ZERO_SHA256)
        record["actor_identity"] = identity
        record["event_sha256"] = _sha256(_canonical(record))
        record["record_hmac_sha256"] = hmac.new(key, record["event_sha256"].encode("ascii"), hashlib.sha256).hexdigest()
        return record

    def validate_event_envelope(
        self,
        event: dict[str, Any],
        *,
        line_number: int,
        previous_event_sha256: str,
        previous_created_at: datetime | None,
        seen_event_ids: set[str],
        key: bytes,
    ) -> datetime:
        event_id = str(event.get("event_id") or "")
        try:
            canonical_id = str(uuid.UUID(event_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("event_id must be a canonical UUID") from exc
        if canonical_id != event_id.lower() or canonical_id in seen_event_ids:
            raise ValueError("event_id is non-canonical or duplicated")
        seen_event_ids.add(canonical_id)
        if event.get("sequence") != line_number:
            raise ValueError("event sequence is not globally contiguous")
        if _digest(event.get("previous_event_sha256"), "previous_event_sha256") != previous_event_sha256:
            raise ValueError("event hash chain is broken")
        event["actor_identity"] = self.normalize_actor_identity(event.get("actor_identity"), actor=str(event.get("actor") or ""))
        created_at, created = _timestamp(event.get("created_at"), "created_at", enforce_future_bound=True)
        event["created_at"] = created_at
        if previous_created_at is not None and created < previous_created_at:
            raise ValueError("event timestamps moved backwards")
        claimed_hash = _digest(event.get("event_sha256"), "event_sha256")
        claimed_hmac = _digest(event.get("record_hmac_sha256"), "record_hmac_sha256")
        unsigned = {name: value for name, value in event.items() if name not in {"event_sha256", "record_hmac_sha256"}}
        if not hmac.compare_digest(_sha256(_canonical(unsigned)), claimed_hash):
            raise ValueError("event digest mismatch")
        expected_hmac = hmac.new(key, claimed_hash.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_hmac, claimed_hmac):
            raise ValueError("event authentication mismatch")
        return created

    def _read_heads(self, key: bytes) -> list[dict[str, Any]]:
        if not self.head_path.exists():
            return []
        heads: list[dict[str, Any]] = []
        previous_hash = ZERO_SHA256
        previous_count = 0
        previous_time: datetime | None = None
        seen_ids: set[str] = set()
        raw = _read_regular(
            self.head_path,
            label="pending governance external head",
            maximum=16 * 1024 * 1024,
        )
        for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict) or set(value) != HEAD_FIELDS or value.get("schema") != HEAD_SCHEMA:
                    raise ValueError("checkpoint fields or schema mismatch")
                checkpoint_id = str(uuid.UUID(str(value.get("checkpoint_id") or "")))
                if checkpoint_id != value.get("checkpoint_id") or checkpoint_id in seen_ids:
                    raise ValueError("checkpoint_id is invalid or duplicated")
                seen_ids.add(checkpoint_id)
                if _digest(value.get("previous_checkpoint_sha256"), "previous_checkpoint_sha256") != previous_hash:
                    raise ValueError("checkpoint chain is broken")
                count = value.get("event_count")
                if not isinstance(count, int) or count <= previous_count or value.get("last_sequence") != count:
                    raise ValueError("checkpoint event count is invalid")
                _digest(value.get("last_event_sha256"), "last_event_sha256")
                created_at, created = _timestamp(value.get("created_at"), "checkpoint.created_at", enforce_future_bound=True)
                value["created_at"] = created_at
                if previous_time is not None and created < previous_time:
                    raise ValueError("checkpoint timestamps moved backwards")
                claimed_hash = _digest(value.get("checkpoint_sha256"), "checkpoint_sha256")
                claimed_hmac = _digest(value.get("checkpoint_hmac_sha256"), "checkpoint_hmac_sha256")
                unsigned = {name: item for name, item in value.items() if name not in {"checkpoint_sha256", "checkpoint_hmac_sha256"}}
                if not hmac.compare_digest(_sha256(_canonical(unsigned)), claimed_hash):
                    raise ValueError("checkpoint digest mismatch")
                expected_hmac = hmac.new(key, claimed_hash.encode("ascii"), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(expected_hmac, claimed_hmac):
                    raise ValueError("checkpoint authentication mismatch")
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"pending governance external head invalid at line {line_number}: {exc}") from exc
            heads.append(value)
            previous_hash = value["checkpoint_sha256"]
            previous_count = value["event_count"]
            previous_time = created
        return heads

    def verify_head(self, events: list[dict[str, Any]], key: bytes | None) -> None:
        if not events:
            if self.head_path.exists() and self.head_path.stat().st_size:
                raise RuntimeError("pending governance external head exists without ledger events")
            return
        if key is None:
            raise RuntimeError("pending governance trust key is unavailable")
        heads = self._read_heads(key)
        if not heads:
            raise RuntimeError("pending governance authenticated external head is missing")
        latest = heads[-1]
        if latest.get("event_count") != len(events) or latest.get("last_sequence") != len(events) or latest.get("last_event_sha256") != events[-1].get("event_sha256"):
            raise RuntimeError("pending governance external head does not match the ledger")

    def append_head(self, events: list[dict[str, Any]], key: bytes) -> None:
        heads = self._read_heads(key)
        previous_hash = str((heads[-1] if heads else {}).get("checkpoint_sha256") or ZERO_SHA256)
        checkpoint: dict[str, Any] = {
            "schema": HEAD_SCHEMA,
            "checkpoint_id": str(uuid.uuid4()),
            "previous_checkpoint_sha256": previous_hash,
            "event_count": len(events),
            "last_sequence": len(events),
            "last_event_sha256": str(events[-1]["event_sha256"]),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        checkpoint["checkpoint_sha256"] = _sha256(_canonical(checkpoint))
        checkpoint["checkpoint_hmac_sha256"] = hmac.new(
            key, checkpoint["checkpoint_sha256"].encode("ascii"), hashlib.sha256
        ).hexdigest()
        self._ensure_trust_root()
        encoded = (json.dumps(checkpoint, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | int(getattr(os, "O_BINARY", 0) or 0) | int(getattr(os, "O_NOFOLLOW", 0) or 0)
        descriptor = os.open(str(self.head_path), flags, 0o600)
        try:
            opened = os.fstat(descriptor)
            if _is_reparse(opened) or not stat.S_ISREG(opened.st_mode):
                raise RuntimeError("pending governance external head is not a strict regular file")
            written = 0
            while written < len(encoded):
                written += os.write(descriptor, encoded[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        fsync_parent_directory(self.trust_root)
