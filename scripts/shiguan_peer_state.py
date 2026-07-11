"""Canonical peer state, node identity, and peer-key codec helpers."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import base64
import copy
from datetime import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import stat
from typing import Callable
import uuid

from court_file_lock import atomic_write_text, file_lock
from shiguan_paths import reference_path, references_root as shared_references_root


CAESAR_SHIFT = 7
PEER_STATE_SCHEMA = "court.shiguan.peer_state.v1"
PEER_STATE_MAX_BYTES = 4 * 1024 * 1024
PEER_STATE_FIELDS = {
    "schema", "revision", "transaction_id", "updated_at", "issued_keys", "imported_peers",
}
PUBLIC_PEER_FIELDS = {
    "peer_id", "key_id", "role", "endpoint", "node", "created_at", "expires_at",
    "clock", "imported_at", "disabled", "disabled_at",
}
PUBLIC_NODE_FIELDS = {"node_id", "machine_uid", "node_name", "created_at", "updated_at", "status"}
PUBLIC_CLOCK_FIELDS = {
    "issued_at", "expires_at", "server_time", "ttl_seconds", "pending_download_seconds",
    "renewal_authority",
}
_MISSING = object()


class PeerStateError(ValueError):
    """Raised when durable peer state cannot be trusted."""


def peer_root() -> Path:
    return shared_references_root() / "shiguan-peers"


def node_identity_path() -> Path:
    return peer_root() / "node.json"


def issued_keys_path() -> Path:
    return peer_root() / "issued-keys.json"


def imported_peers_path() -> Path:
    return peer_root() / "imported-peers.json"


def peer_state_path() -> Path:
    return peer_root() / "peer-state.json"


def peer_state_lock_path() -> Path:
    return reference_path("court-runtime", "shiguan-web-state.lock")


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_bounded_json(path: Path, label: str) -> object:
    for _attempt in range(3):
        try:
            before = path.lstat()
        except FileNotFoundError:
            return _MISSING
        except OSError:
            raise PeerStateError(f"{label} cannot be inspected") from None
        if not stat.S_ISREG(before.st_mode):
            raise PeerStateError(f"{label} must be a regular non-symlink file")
        if before.st_size > PEER_STATE_MAX_BYTES:
            raise PeerStateError(f"{label} exceeds the size limit")
        try:
            with path.open("r", encoding="utf-8") as handle:
                opened = os.fstat(handle.fileno())
                same_file = (
                    before.st_dev == opened.st_dev
                    and (not before.st_ino or not opened.st_ino or before.st_ino == opened.st_ino)
                    and before.st_size == opened.st_size
                )
                if not same_file:
                    continue
                return json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise PeerStateError(f"{label} is malformed") from None
    raise PeerStateError(f"{label} changed during inspection")


def _record_list(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(record, dict) for record in value):
        raise PeerStateError(f"{label} must be a list of objects")
    return copy.deepcopy(value)


def _legacy_records(path: Path, label: str) -> list[dict[str, object]]:
    value = _read_bounded_json(path, label)
    return [] if value is _MISSING else _record_list(value, label)


def _validated_state(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != PEER_STATE_FIELDS:
        raise PeerStateError("canonical peer state schema fields are invalid")
    revision = value.get("revision")
    if (
        value.get("schema") != PEER_STATE_SCHEMA
        or type(revision) is not int
        or int(revision) < 1
        or not isinstance(value.get("transaction_id"), str)
        or not str(value.get("transaction_id")).strip()
        or not isinstance(value.get("updated_at"), str)
        or not str(value.get("updated_at")).strip()
    ):
        raise PeerStateError("canonical peer state metadata is invalid")
    return {
        "schema": PEER_STATE_SCHEMA,
        "revision": revision,
        "transaction_id": str(value["transaction_id"]),
        "updated_at": str(value["updated_at"]),
        "issued_keys": _record_list(value.get("issued_keys"), "canonical issued_keys"),
        "imported_peers": _record_list(value.get("imported_peers"), "canonical imported_peers"),
    }


def read_peer_state() -> dict[str, object]:
    value = _read_bounded_json(peer_state_path(), "canonical peer state")
    if value is not _MISSING:
        return _validated_state(value)
    return {
        "schema": PEER_STATE_SCHEMA,
        "revision": 0,
        "transaction_id": "",
        "updated_at": "",
        "issued_keys": _legacy_records(issued_keys_path(), "legacy issued keys"),
        "imported_peers": _legacy_records(imported_peers_path(), "legacy imported peers"),
    }


def peer_state_snapshot() -> dict[str, object]:
    return read_peer_state()


def update_peer_state(
    mutator: Callable[[dict[str, object]], object],
) -> tuple[dict[str, object], object]:
    with file_lock(peer_state_lock_path(), timeout=15.0):
        current = read_peer_state()
        working = {
            "issued_keys": copy.deepcopy(current["issued_keys"]),
            "imported_peers": copy.deepcopy(current["imported_peers"]),
        }
        result = mutator(working)
        committed = {
            "schema": PEER_STATE_SCHEMA,
            "revision": int(current["revision"]) + 1,
            "transaction_id": uuid.uuid4().hex,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "issued_keys": _record_list(working.get("issued_keys"), "issued_keys"),
            "imported_peers": _record_list(working.get("imported_peers"), "imported_peers"),
        }
        atomic_write_text(peer_state_path(), _json_text(committed))
        return copy.deepcopy(committed), result


def issued_keys(snapshot: dict[str, object] | None = None) -> list[dict[str, object]]:
    state = snapshot if snapshot is not None else read_peer_state()
    return _record_list(state.get("issued_keys"), "issued_keys")


def imported_peers(snapshot: dict[str, object] | None = None) -> list[dict[str, object]]:
    state = snapshot if snapshot is not None else read_peer_state()
    return _record_list(state.get("imported_peers"), "imported_peers")


def save_issued_keys(keys: list[dict[str, object]]) -> None:
    update_peer_state(lambda state: state.__setitem__("issued_keys", copy.deepcopy(keys)))


def save_imported_peers(peers: list[dict[str, object]]) -> None:
    update_peer_state(lambda state: state.__setitem__("imported_peers", copy.deepcopy(peers)))


def stable_machine_uid(node_id: object) -> str:
    text = str(node_id or "").strip() or "shiguan-node"
    return hashlib.sha1(text.encode("utf-8")).hexdigest().upper()[:10]


def _read_node_value() -> dict[str, object]:
    try:
        value = _read_bounded_json(node_identity_path(), "node identity")
    except PeerStateError:
        return {}
    return value if isinstance(value, dict) else {}


def read_node_identity() -> dict[str, object]:
    identity = _read_node_value()
    if identity.get("node_id"):
        result = dict(identity)
        result.setdefault("machine_uid", stable_machine_uid(result.get("node_id")))
        return result
    return {
        "node_id": "",
        "machine_uid": "",
        "node_name": socket.gethostname() or "shiguan-node",
        "status": "missing",
    }


def ensure_node_identity() -> dict[str, object]:
    with file_lock(peer_state_lock_path(), timeout=15.0):
        identity = _read_node_value()
        if identity.get("node_id"):
            if not identity.get("machine_uid"):
                identity = dict(identity)
                identity["machine_uid"] = stable_machine_uid(identity.get("node_id"))
                identity["updated_at"] = datetime.now().isoformat(timespec="seconds")
                atomic_write_text(node_identity_path(), _json_text(identity))
            return identity
        node_id = secrets.token_hex(12)
        identity = {
            "node_id": node_id,
            "machine_uid": stable_machine_uid(node_id),
            "node_name": socket.gethostname() or "shiguan-node",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        atomic_write_text(node_identity_path(), _json_text(identity))
        return identity


def caesar_transform(text: str, shift: int) -> str:
    output: list[str] = []
    for char in text:
        code = ord(char)
        output.append(chr(32 + ((code - 32 + shift) % 95)) if 32 <= code <= 126 else char)
    return "".join(output)


def encode_peer_key(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    packed = base64.urlsafe_b64encode(raw).decode("ascii")
    wrapped = caesar_transform(packed, CAESAR_SHIFT)
    chunks = "\n".join(wrapped[index:index + 76] for index in range(0, len(wrapped), 76))
    checksum = hashlib.sha256(wrapped.encode("ascii")).hexdigest()
    return "\n".join([
        "SHIGUAN-PEER-KEY-v2", "format: caesar-7-base64-json",
        f"length: {len(wrapped)}", f"checksum: {checksum}", "PAYLOAD", chunks,
        "END-SHIGUAN-PEER-KEY-v2", "",
    ])


def decode_peer_key(text: str) -> dict[str, object]:
    packed = text.strip()
    if packed.startswith("SHIGUAN-PEER-KEY-v2"):
        raw_lines = packed.splitlines()
        marker_lines = [line.strip() for line in raw_lines]
        try:
            start = marker_lines.index("PAYLOAD") + 1
            end = marker_lines.index("END-SHIGUAN-PEER-KEY-v2")
        except ValueError:
            raise ValueError("密钥文件格式不完整") from None
        metadata = {}
        for line in marker_lines[1:start - 1]:
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()
        packed = "".join(raw_lines[start:end])
        expected = metadata.get("checksum", "")
        if expected and not hmac.compare_digest(hashlib.sha256(packed.encode("ascii")).hexdigest(), expected):
            raise ValueError("密钥文件校验失败")
        expected_length = metadata.get("length", "")
        if expected_length and expected_length.isdigit() and int(expected_length) != len(packed):
            raise ValueError("密钥文件长度校验失败")
    elif packed.startswith("SHIGUAN-PEER-KEY-v1"):
        packed = packed.split("\n", 1)[1].strip()
    else:
        raise ValueError("密钥文件必须使用 .shiguan-key 专用格式")
    try:
        value = json.loads(base64.urlsafe_b64decode(caesar_transform(packed, -CAESAR_SHIFT)).decode("utf-8"))
    except Exception:
        raise ValueError("密钥文件无法解码") from None
    if not isinstance(value, dict) or value.get("type") != "shiguan_peer_key":
        raise ValueError("不是史馆 peer 密钥")
    return value


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_peer(record: dict[str, object]) -> dict[str, object]:
    value = {key: item for key, item in record.items() if key in PUBLIC_PEER_FIELDS - {"node", "clock"}}
    node = record.get("node")
    clock = record.get("clock")
    if isinstance(node, dict):
        value["node"] = {key: item for key, item in node.items() if key in PUBLIC_NODE_FIELDS}
    if isinstance(clock, dict):
        value["clock"] = {key: item for key, item in clock.items() if key in PUBLIC_CLOCK_FIELDS}
    return value
