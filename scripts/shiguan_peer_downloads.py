"""Ephemeral peer-key download state and safe public projections.

Durable peer records keep verification material only.  The encoded key file and
its one-time download nonce intentionally live in process memory, so a service
restart destroys them.  Callers must expose that loss as ``regenerate_required``
instead of persisting plaintext or pretending the file can be reconstructed.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from datetime import datetime, timedelta
import hmac
import hashlib
import secrets
import threading

from shiguan_peer_state import PUBLIC_CLOCK_FIELDS


PEER_PENDING_DOWNLOAD_SECONDS = 3600
DOWNLOAD_CONTRACT = "process_memory_one_time_no_plaintext_persistence"
DOWNLOAD_READY = "ready"
DOWNLOAD_CONSUMED = "consumed"
DOWNLOAD_REGENERATE_REQUIRED = "regenerate_required"


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _time_reached(value: object, *, missing_is_reached: bool) -> bool:
    text = str(value or "").strip()
    if not text:
        return missing_is_reached
    parsed = _parse_time(text)
    if parsed is None:
        return True
    now = datetime.now(parsed.tzinfo) if parsed.tzinfo is not None else datetime.now()
    return parsed <= now


def key_expired(record: dict[str, object]) -> bool:
    expires_at = str(record.get("expires_at") or "").strip()
    if not expires_at:
        return not bool(record.get("permanent"))
    return _time_reached(expires_at, missing_is_reached=True)


def _active_key_ids(active_keys: list[dict[str, object]]) -> set[str]:
    return {
        str(record.get("key_id") or "")
        for record in active_keys
        if record.get("key_id")
        if not record.get("revoked_at")
        if not key_expired(record)
    }


def peer_transaction(snapshot: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "court.shiguan.peer_state.transaction.v1",
        "transaction_id": str(snapshot.get("transaction_id") or ""),
        "revision": int(snapshot.get("revision") or 0),
        "updated_at": str(snapshot.get("updated_at") or ""),
    }


class EphemeralKeyDownloadStore:
    """Thread-safe one-process store for plaintext key-file material."""

    def __init__(self, ttl_seconds: int = PEER_PENDING_DOWNLOAD_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self.entries: dict[str, dict[str, object]] = {}
        self.lock = threading.RLock()

    def _expire_locked(self) -> None:
        for key_id, pending in list(self.entries.items()):
            if _time_reached(pending.get("download_expires_at"), missing_is_reached=True):
                self.entries.pop(key_id, None)

    def cleanup(self) -> None:
        # Only time-based destruction is implicit.  A caller-supplied durable
        # snapshot may be stale and must never delete a newer credential.
        with self.lock:
            self._expire_locked()

    def remember(self, result: dict[str, object]) -> None:
        key_id = str(result.get("key_id") or "")
        if not key_id:
            return
        expires_at = (
            datetime.now() + timedelta(seconds=self.ttl_seconds)
        ).isoformat(timespec="seconds")
        entry = {
            "key_id": key_id,
            "role": str(result.get("role") or ""),
            "filename": str(result.get("filename") or ""),
            "key_text": str(result.get("key_text") or ""),
            "download_nonce": secrets.token_urlsafe(32),
            "created_at": _now_text(),
            "download_expires_at": expires_at,
            "downloaded_at": "",
            "delivery_state": "ready",
            "delivery_attempted_at": "",
            "delivery_failed_at": "",
        }
        with self.lock:
            self._expire_locked()
            self.entries[key_id] = entry

    def get(
        self,
        key_id: str,
        *,
        active_keys: list[dict[str, object]] | None = None,
    ) -> dict[str, object] | None:
        if active_keys is None:
            return None
        with self.lock:
            self._expire_locked()
            if key_id not in _active_key_ids(active_keys):
                return None
            pending = self.entries.get(str(key_id or ""))
            return dict(pending) if pending else None

    def latest(
        self,
        active_keys: list[dict[str, object]] | None = None,
    ) -> dict[str, object] | None:
        if active_keys is None:
            return None
        with self.lock:
            self._expire_locked()
            active_ids = _active_key_ids(active_keys)
            ready = [
                item
                for key_id, item in self.entries.items()
                if key_id in active_ids
                if item.get("delivery_state", "ready") == "ready"
                if item.get("key_text") and item.get("download_nonce")
            ]
            return dict(max(ready, key=lambda item: str(item.get("created_at") or ""))) if ready else None

    def consume(
        self,
        key_id: str,
        download_nonce: str,
        *,
        active_keys: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        if active_keys is None:
            raise ValueError("下载必须使用当前 durable-key 视图校验")
        with self.lock:
            self._expire_locked()
            if active_keys is not None and key_id not in _active_key_ids(active_keys):
                raise ValueError("密钥已删除、吊销或过期；临时导出材料不可再使用")
            pending = self.entries.get(str(key_id or "")) if key_id else None
            if not pending:
                raise ValueError("没有可导出的密钥；临时材料可能已过期或因服务重启销毁，请删除旧密钥后重新生成")
            if pending.get("delivery_state", "ready") != "ready" or pending.get("downloaded_at"):
                raise ValueError("密钥下载凭据已使用；请删除旧密钥后重新生成")
            expected_nonce = str(pending.get("download_nonce") or "")
            if not expected_nonce or not download_nonce or not hmac.compare_digest(expected_nonce, str(download_nonce)):
                raise PermissionError("密钥下载凭据无效")
            attempted_at = _now_text()
            result = dict(pending)
            result["delivery_attempted_at"] = attempted_at
            pending["delivery_state"] = "prepared"
            pending["delivery_attempted_at"] = attempted_at
            pending.pop("key_text", None)
            pending.pop("download_nonce", None)
            return result

    def mark_delivery(self, key_id: str, *, delivered: bool) -> None:
        """Finalize an already-consumed response without restoring secrets."""

        with self.lock:
            pending = self.entries.get(str(key_id or ""))
            if not pending:
                return
            now = _now_text()
            if delivered:
                pending["delivery_state"] = "delivered"
                pending["downloaded_at"] = now
                pending["delivery_failed_at"] = ""
            else:
                pending["delivery_state"] = "failed"
                pending["delivery_failed_at"] = now
                pending["downloaded_at"] = ""
            pending.pop("key_text", None)
            pending.pop("download_nonce", None)

    def ready_items(
        self,
        active_keys: list[dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        if active_keys is None:
            return []
        with self.lock:
            self._expire_locked()
            allowed_ids = _active_key_ids(active_keys)
            return [
                {
                    "key_id": str(item.get("key_id") or ""),
                    "role": str(item.get("role") or ""),
                    "filename": str(item.get("filename") or ""),
                    "created_at": str(item.get("created_at") or ""),
                    "download_expires_at": str(item.get("download_expires_at") or ""),
                    "download_nonce": str(item.get("download_nonce") or ""),
                }
                for item in self.entries.values()
                if item.get("delivery_state", "ready") == "ready"
                if item.get("key_text") and item.get("download_nonce")
                if str(item.get("key_id") or "") in allowed_ids
            ]

    def transition_gate(self, active_keys: list[dict[str, object]] | None) -> dict[str, object]:
        """Return nonce-free restart/switch readiness from the current durable view."""

        if active_keys is None:
            return {
                "schema": "court.peer_credential_transition_gate.v1",
                "safe_to_restart_or_switch": False,
                "reason": "durable_key_view_required",
                "unconfirmed_delivery_count": None,
                "regenerate_required_count": None,
                "plaintext_or_nonce_exposed": False,
            }
        with self.lock:
            self._expire_locked()
            active_ids = _active_key_ids(active_keys)
            unconfirmed_ids = sorted(
                key_id
                for key_id, item in self.entries.items()
                if key_id in active_ids
                if item.get("delivery_state", "ready") == "ready"
                if item.get("key_text") and item.get("download_nonce")
            )
            delivered_ids = {
                key_id
                for key_id, item in self.entries.items()
                if key_id in active_ids and item.get("delivery_state") == "delivered"
            }
            regenerate_ids = sorted(active_ids - set(unconfirmed_ids) - delivered_ids)
        digest = hashlib.sha256("\n".join(unconfirmed_ids).encode("utf-8")).hexdigest()
        return {
            "schema": "court.peer_credential_transition_gate.v1",
            "safe_to_restart_or_switch": not unconfirmed_ids,
            "reason": "clear" if not unconfirmed_ids else "unconfirmed_one_time_credential_delivery",
            "unconfirmed_delivery_count": len(unconfirmed_ids),
            "unconfirmed_key_ids_sha256": digest,
            "regenerate_required_count": len(regenerate_ids),
            "required_action": (
                "none"
                if not unconfirmed_ids
                else "complete_delivery_or_revoke_then_regenerate_before_restart_or_protocol_switch"
            ),
            "plaintext_or_nonce_exposed": False,
        }


PENDING_KEY_DOWNLOAD_STORE = EphemeralKeyDownloadStore()
PENDING_KEY_DOWNLOADS = PENDING_KEY_DOWNLOAD_STORE.entries
PENDING_KEY_DOWNLOADS_LOCK = PENDING_KEY_DOWNLOAD_STORE.lock


def cleanup_pending_key_downloads() -> None:
    PENDING_KEY_DOWNLOAD_STORE.cleanup()


def remember_pending_key_download(result: dict[str, object]) -> None:
    PENDING_KEY_DOWNLOAD_STORE.remember(result)


def pending_key_download(
    key_id: str,
    consume: bool = False,
    active_keys: list[dict[str, object]] | None = None,
) -> dict[str, object] | None:
    if consume:
        raise ValueError("consume requires download_pending_key with a nonce")
    return PENDING_KEY_DOWNLOAD_STORE.get(key_id, active_keys=active_keys)


def latest_pending_key_download(
    active_keys: list[dict[str, object]] | None = None,
) -> dict[str, object] | None:
    return PENDING_KEY_DOWNLOAD_STORE.latest(active_keys)


def download_pending_key(
    key_id: str,
    download_nonce: str,
    active_keys: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return PENDING_KEY_DOWNLOAD_STORE.consume(
        key_id,
        download_nonce,
        active_keys=active_keys,
    )


def mark_pending_key_delivery(key_id: str, *, delivered: bool) -> None:
    PENDING_KEY_DOWNLOAD_STORE.mark_delivery(key_id, delivered=delivered)


def pending_downloads(
    active_keys: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    return PENDING_KEY_DOWNLOAD_STORE.ready_items(active_keys)


def credential_transition_gate(
    active_keys: list[dict[str, object]] | None,
) -> dict[str, object]:
    return PENDING_KEY_DOWNLOAD_STORE.transition_gate(active_keys)


def public_issued_key(
    record: dict[str, object],
    active_keys: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    allowed = {
        "key_id", "role", "created_at", "expires_at", "ttl_seconds", "permanent",
        "endpoint", "revoked_at", "revoked_reason", "regeneration_requested_at",
        "regenerate_from", "note", "updated_at",
    }
    value = {key: item for key, item in record.items() if key in allowed}
    clock = record.get("clock")
    if isinstance(clock, dict):
        value["clock"] = {key: item for key, item in clock.items() if key in PUBLIC_CLOCK_FIELDS}
    key_id = str(record.get("key_id") or "")
    durable_view_known = active_keys is not None
    pending = pending_key_download(key_id, active_keys=active_keys) if key_id and durable_view_known else None
    expired = key_expired(record)
    revoked = bool(record.get("revoked_at"))
    delivery_state = str(pending.get("delivery_state") or "ready") if pending else ""
    if not durable_view_known:
        state, reason = DOWNLOAD_REGENERATE_REQUIRED, "durable_key_view_required"
    elif expired or revoked:
        state, reason = DOWNLOAD_REGENERATE_REQUIRED, "durable_key_revoked_or_expired"
    elif pending and delivery_state == "ready" and pending.get("key_text") and pending.get("download_nonce"):
        state, reason = DOWNLOAD_READY, ""
    elif pending and delivery_state == "delivered":
        state, reason = DOWNLOAD_CONSUMED, "one_time_credential_consumed"
    elif pending and delivery_state in {"prepared", "failed"}:
        state, reason = DOWNLOAD_REGENERATE_REQUIRED, "delivery_outcome_unknown_revoke_then_regenerate"
    else:
        state = DOWNLOAD_REGENERATE_REQUIRED
        reason = "ephemeral_material_unavailable_after_restart_expiry_or_cleanup"
    value.update({
        "expired": expired,
        "revoked": revoked,
        "download_ready": state == DOWNLOAD_READY,
        "download_state": state,
        "download_expires_at": str(pending.get("download_expires_at") or "") if pending else "",
        "download_regeneration_required": state != DOWNLOAD_READY,
        "download_unavailable_reason": reason,
        "download_contract": DOWNLOAD_CONTRACT,
    })
    return value
