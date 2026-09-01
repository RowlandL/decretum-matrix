"""Isolated transaction regressions for canonical Shiguan peer state."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True
import tempfile
import threading
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import shiguan_peer_state as peer  # type: ignore  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def use_root(root: Path) -> None:
    os.environ["COURT_SHARED_SHIGUAN_ROOT"] = str(root)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def tree_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def seed_legacy(root: Path) -> tuple[bytes, bytes]:
    use_root(root)
    write_json(peer.issued_keys_path(), [{"key_id": "legacy-key", "token_hash": "fixture-hash"}])
    write_json(
        peer.imported_peers_path(),
        [{"peer_id": "legacy-peer", "token": "fixture-token", "endpoint": "http://127.0.0.1:9/"}],
    )
    return peer.issued_keys_path().read_bytes(), peer.imported_peers_path().read_bytes()


def check_legacy_read_zero_write(base: Path) -> dict[str, object]:
    root = base / "legacy-zero-write"
    seed_legacy(root)
    before = tree_snapshot(root)
    state = peer.read_peer_state()
    after = tree_snapshot(root)
    require(before == after, "legacy read mutated files or mtimes")
    require(not peer.peer_state_path().exists(), "legacy read created canonical state")
    require(state.get("revision") == 0, "legacy compatibility snapshot revision must be zero")
    require(len(peer.issued_keys(state)) == 1 and len(peer.imported_peers(state)) == 1, "legacy records lost")
    return {"files": len(before), "revision": 0, "canonical_created": False}


def check_first_mutation(base: Path) -> dict[str, object]:
    root = base / "first-mutation"
    legacy_keys, legacy_peers = seed_legacy(root)

    def append_key(state: dict[str, object]) -> None:
        state["issued_keys"].append({"key_id": "new-key"})  # type: ignore[union-attr]

    committed, _ = peer.update_peer_state(append_key)
    require(committed.get("revision") == 1, "first mutation did not create revision one")
    require(set(committed) == peer.PEER_STATE_FIELDS, "canonical state fields drifted")
    require(peer.issued_keys_path().read_bytes() == legacy_keys, "legacy issued keys were changed")
    require(peer.imported_peers_path().read_bytes() == legacy_peers, "legacy imported peers were changed")
    require(len(peer.issued_keys(committed)) == 2 and len(peer.imported_peers(committed)) == 1, "migration lost records")
    return {"revision": 1, "issued_keys": 2, "imported_peers": 1, "legacy_unchanged": True}


def check_atomic_failure(base: Path, server) -> dict[str, object]:
    root = base / "atomic-failure"
    use_root(root)
    peer.save_issued_keys([{"key_id": "durable-key", "revoked_at": ""}])
    before = peer.peer_state_path().read_bytes()
    before_revision = peer.read_peer_state()["revision"]

    def append_key(state: dict[str, object]) -> None:
        state["issued_keys"].append({"key_id": "must-not-commit"})  # type: ignore[union-attr]

    with mock.patch.object(peer, "atomic_write_text", side_effect=OSError("fixture replace failure")):
        try:
            peer.update_peer_state(append_key)
        except OSError:
            pass
        else:
            raise AssertionError("atomic replace failure was not propagated")
    require(peer.peer_state_path().read_bytes() == before, "failed atomic replace changed committed bytes")
    require(peer.read_peer_state()["revision"] == before_revision, "failed replace advanced revision")

    peer.ensure_node_identity()
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
    with mock.patch.object(peer, "atomic_write_text", side_effect=OSError("fixture key commit failure")):
        try:
            server.export_peer_key({"role": "read", "share_host": "127.0.0.1", "share_port": 9})
        except OSError:
            pass
        else:
            raise AssertionError("key commit failure was not propagated")
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        require(not server.PENDING_KEY_DOWNLOADS, "provisional plaintext remained after failed durable commit")

    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS["durable-key"] = {"key_id": "durable-key"}
    with mock.patch.object(peer, "atomic_write_text", side_effect=OSError("fixture delete failure")):
        try:
            server.manage_key({"action": "delete", "key_id": "durable-key"})
        except OSError:
            pass
        else:
            raise AssertionError("delete failure was not propagated")
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        require("durable-key" in server.PENDING_KEY_DOWNLOADS, "download state cleared before durable commit")
        server.PENDING_KEY_DOWNLOADS.clear()
    return {
        "revision": before_revision,
        "bytes_unchanged": True,
        "download_preserved": True,
        "failed_generation_plaintext_removed": True,
    }


def expect_fail_closed() -> None:
    try:
        peer.read_peer_state()
    except peer.PeerStateError:
        return
    raise AssertionError("invalid canonical state fell back to legacy")


def check_malformed_fail_closed(base: Path) -> dict[str, object]:
    root = base / "malformed"
    seed_legacy(root)
    canonical = peer.peer_state_path()
    canonical.write_text("not-json", encoding="utf-8")
    expect_fail_closed()
    write_json(
        canonical,
        {
            "schema": "wrong-schema",
            "revision": 1,
            "transaction_id": "fixture",
            "updated_at": "fixture",
            "issued_keys": [],
            "imported_peers": [],
        },
    )
    expect_fail_closed()
    canonical.write_bytes(b"x" * (peer.PEER_STATE_MAX_BYTES + 1))
    expect_fail_closed()
    canonical.replace(canonical.with_name("peer-state-oversized-preserved.json"))
    target = canonical.with_name("peer-state-target.json")
    write_json(
        target,
        {
            "schema": peer.PEER_STATE_SCHEMA,
            "revision": 1,
            "transaction_id": "fixture",
            "updated_at": "fixture",
            "issued_keys": [],
            "imported_peers": [],
        },
    )
    try:
        canonical.symlink_to(target.name)
    except OSError as exc:
        if os.name != "nt" or getattr(exc, "winerror", None) != 1314:
            raise AssertionError(f"fixture could not create canonical symlink: {exc}") from None
        symlink_stat = os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 1, 0, 0, 0, 0, 0, 0))
        with mock.patch.object(Path, "lstat", return_value=symlink_stat):
            expect_fail_closed()
        symlink_check = "simulated_lstat_after_winerror_1314"
    else:
        expect_fail_closed()
        symlink_check = "native"
    return {"malformed": True, "schema": True, "oversized": True, "symlink": symlink_check}


def check_revision_and_concurrency(base: Path) -> dict[str, object]:
    root = base / "concurrency"
    use_root(root)

    def writer(index: int) -> tuple[int, str]:
        field = "issued_keys" if index % 2 == 0 else "imported_peers"
        identity = f"fixture-{index:02d}"

        def append(state: dict[str, object]) -> None:
            record = {"key_id": identity} if field == "issued_keys" else {"peer_id": identity}
            state[field].append(record)  # type: ignore[union-attr]

        committed, _ = peer.update_peer_state(append)
        return int(committed["revision"]), str(committed["transaction_id"])

    with ThreadPoolExecutor(max_workers=12) as executor:
        commits = list(executor.map(writer, range(24)))
    state = peer.read_peer_state()
    revisions = {revision for revision, _transaction_id in commits}
    transactions = {transaction_id for _revision, transaction_id in commits}
    require(revisions == set(range(1, 25)), "concurrent revisions were not monotonic and unique")
    require(len(transactions) == 24, "transaction ids were reused")
    require(len(peer.issued_keys(state)) == 12 and len(peer.imported_peers(state)) == 12, "disjoint updates were lost")
    return {"writers": 24, "revision": state["revision"], "issued_keys": 12, "imported_peers": 12}


def check_expire_single_commit_and_projection(base: Path, server) -> dict[str, object]:
    root = base / "expire"
    use_root(root)

    def seed(state: dict[str, object]) -> None:
        state["issued_keys"] = [{"key_id": "expire-key", "token_hash": "fixture-hash", "revoked_at": ""}]
        state["imported_peers"] = [{
            "peer_id": "expire-peer", "token": "fixture-token", "disabled": False,
            "node": {"node_name": "fixture", "token": "fixture-node-secret"},
            "clock": {"server_time": "fixture", "token": "fixture-clock-secret"},
            "unexpected_secret": "fixture-extension-secret",
        }]

    before, _ = peer.update_peer_state(seed)
    writes = 0
    original_atomic = peer.atomic_write_text

    def counted_atomic(path: Path, text: str, *args, **kwargs) -> None:
        nonlocal writes
        writes += 1
        original_atomic(path, text, *args, **kwargs)

    with mock.patch.object(peer, "atomic_write_text", side_effect=counted_atomic):
        result = server.expire_key({"key_id": "expire-key", "peer_id": "expire-peer"})
    after = peer.read_peer_state()
    keys = peer.issued_keys(after)
    peers = peer.imported_peers(after)
    require(writes == 1, "expire_key performed more than one durable commit")
    require(after["revision"] == int(before["revision"]) + 1, "expire_key revision did not advance once")
    require(result.get("changed") == 2, "expire_key did not update both domains")
    require(bool(keys[0].get("revoked_at")) and peers[0].get("disabled") is True, "expire state is mixed")
    public = {
        "key": server.public_issued_key(keys[0], keys),
        "peer": peer.public_peer(peers[0]),
    }
    serialized = json.dumps(public, ensure_ascii=False)
    require("secret" not in serialized and "fixture-hash" not in serialized, "public projection leaked secrets")
    require(result.get("transaction", {}).get("revision") == after["revision"], "transaction result drifted")
    return {"writes": writes, "revision": after["revision"], "changed": 2, "public_secret_fields": 0}


def check_generate_uses_commit_snapshot(base: Path, server) -> dict[str, object]:
    root = base / "generate-snapshot"
    use_root(root)
    with mock.patch.object(server, "peer_state_snapshot", side_effect=AssertionError("post-commit reread")):
        result = server.generate_peer_key({"role": "read", "share_host": "127.0.0.1", "share_port": 9})
    state = peer.read_peer_state()
    key = result.get("key") if isinstance(result.get("key"), dict) else {}
    require(result.get("transaction", {}).get("revision") == state["revision"], "response revision drifted")
    require(str(key.get("key_id") or "") in {str(item.get("key_id") or "") for item in peer.issued_keys(state)}, "response key was not from committed snapshot")
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
    return {"revision": state["revision"], "post_commit_rereads": 0}


def check_pending_snapshot_cannot_evict_newer(base: Path, server) -> dict[str, object]:
    root = base / "pending-snapshot"
    use_root(root)
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
    result_a, snapshot_a = server._export_peer_key_with_snapshot({"role": "read", "share_host": "127.0.0.1", "share_port": 9})
    result_b, _snapshot_b = server._export_peer_key_with_snapshot({"role": "read", "share_host": "127.0.0.1", "share_port": 9})
    key_a, key_b = str(result_a["key_id"]), str(result_b["key_id"])
    keys_a = peer.issued_keys(snapshot_a)
    server.public_issued_key(next(item for item in keys_a if str(item.get("key_id")) == key_a), keys_a)
    visible = {str(item.get("key_id")) for item in server.pending_downloads(keys_a)}
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        durable_pending = set(server.PENDING_KEY_DOWNLOADS)
    require(key_b in durable_pending, "older snapshot evicted a newer pending download")
    require(visible == {key_a}, "snapshot response view was not filtered without mutation")
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS["expired-fixture"] = {
            "key_id": "expired-fixture", "key_text": "fixture-secret", "download_expires_at": "2000-01-01T00:00:00",
        }
    server.pending_downloads(keys_a)
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        require("expired-fixture" not in server.PENDING_KEY_DOWNLOADS, "expired download material remained in memory")
        server.PENDING_KEY_DOWNLOADS.clear()
    return {"newer_pending_preserved": True, "snapshot_view_keys": 1, "expired_material_removed": True}


def check_ephemeral_restart_and_consume_contract(base: Path, server) -> dict[str, object]:
    root = base / "ephemeral-restart"
    use_root(root)
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
    generated = server.generate_peer_key({"role": "read", "share_host": "127.0.0.1", "share_port": 9})
    state = peer.read_peer_state()
    keys = peer.issued_keys(state)
    key = generated.get("key") if isinstance(generated.get("key"), dict) else {}
    key_id = str(key.get("key_id") or "")
    pending = server.pending_downloads(keys)
    require(key.get("download_state") == "ready" and key.get("download_ready") is True, "new credential was not ready")
    require(len(pending) == 1 and pending[0].get("key_id") == key_id, "ready download was not listed")
    before_switch = server.credential_transition_gate(keys)
    require(before_switch.get("safe_to_restart_or_switch") is False, "unconfirmed credential did not block restart")
    require(before_switch.get("unconfirmed_delivery_count") == 1, "unconfirmed credential count drifted")
    try:
        server.download_pending_key(key_id, str(pending[0].get("download_nonce") or ""))
    except ValueError:
        pass
    else:
        raise AssertionError("credential download did not require the current durable-key view")
    try:
        server.download_pending_key(key_id, str(pending[0].get("download_nonce") or ""), [])
    except ValueError:
        pass
    else:
        raise AssertionError("credential download ignored the current durable-key view")
    consumed = server.download_pending_key(key_id, str(pending[0].get("download_nonce") or ""), keys)
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        consumed_tombstone = dict(server.PENDING_KEY_DOWNLOADS.get(key_id, {}))
    require(not consumed_tombstone.get("key_text"), "consumed plaintext remained in the process-memory store")
    require(not consumed_tombstone.get("download_nonce"), "consumed nonce remained in the process-memory store")
    server.mark_pending_key_delivery(key_id, delivered=True)
    consumed_view = server.public_issued_key(keys[0], keys)
    require(consumed_view.get("download_state") == "consumed", "consumed credential state was not explicit")
    require(consumed_view.get("download_ready") is False, "consumed credential remained download-ready")
    require(server.pending_downloads(keys) == [], "consumed credential remained in ready list")
    after_consume = server.credential_transition_gate(keys)
    require(after_consume.get("safe_to_restart_or_switch") is True, "consumed credential still blocked restart")
    try:
        server.download_pending_key(key_id, str(pending[0].get("download_nonce") or ""))
    except ValueError:
        pass
    else:
        raise AssertionError("one-time credential was reusable")
    durable_bytes = peer.peer_state_path().read_bytes()
    require(str(consumed.get("key_text") or "").encode("utf-8") not in durable_bytes, "plaintext key file was persisted")
    require(str(pending[0].get("download_nonce") or "").encode("utf-8") not in durable_bytes, "download nonce was persisted")
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
    restarted_view = server.public_issued_key(keys[0], keys)
    require(restarted_view.get("download_state") == "regenerate_required", "restart loss was not explicit")
    require(restarted_view.get("download_regeneration_required") is True, "restart loss did not require regeneration")
    require(key_id in {str(item.get("key_id") or "") for item in peer.issued_keys()}, "durable key disappeared with ephemeral state")
    after_restart = server.credential_transition_gate(keys)
    require(after_restart.get("safe_to_restart_or_switch") is True, "restart-lost material incorrectly blocked restart")
    return {
        "ready_then_consumed": True,
        "consumed_plaintext_destroyed": True,
        "consumed_nonce_destroyed": True,
        "restart_state": "regenerate_required",
        "plaintext_persisted": False,
        "durable_key_preserved": True,
        "inactive_key_download_blocked": True,
        "durable_key_view_required": True,
        "switch_blocked_until_delivery_confirmed": True,
    }


def check_missing_durable_view_fails_closed(base: Path, server) -> dict[str, object]:
    root = base / "missing-durable-view"
    use_root(root)
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
        server.PENDING_KEY_DOWNLOADS["view-key"] = {
            "key_id": "view-key",
            "role": "read",
            "filename": "view-key.shiguan-key",
            "key_text": "fixture-plaintext-canary",
            "download_nonce": "fixture-nonce-canary",
            "created_at": "fixture",
            "download_expires_at": "2999-01-01T00:00:00+00:00",
            "downloaded_at": "",
            "delivery_state": "ready",
        }
    record = {
        "key_id": "view-key",
        "role": "read",
        "permanent": True,
        "expires_at": "",
        "revoked_at": "",
    }
    require(server.pending_key_download("view-key") is None, "get exposed plaintext without durable view")
    require(server.latest_pending_key_download() is None, "latest exposed plaintext without durable view")
    require(server.pending_downloads() == [], "ready list exposed nonce without durable view")
    public = server.public_issued_key(record)
    require(public.get("download_state") == "regenerate_required", "public view failed open without durable view")
    require(public.get("download_unavailable_reason") == "durable_key_view_required", "missing-view reason drifted")
    serialized = json.dumps(public, ensure_ascii=False)
    require("fixture-plaintext-canary" not in serialized and "fixture-nonce-canary" not in serialized, "missing-view public projection leaked credential material")
    active = [record]
    require(server.pending_key_download("view-key", active_keys=active) is not None, "canonical durable view did not unlock matching credential")
    require(len(server.pending_downloads(active)) == 1, "canonical durable view did not expose matching ready item")
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
    return {
        "get_without_view": "closed",
        "latest_without_view": "closed",
        "ready_without_view": 0,
        "public_reason": "durable_key_view_required",
    }


def check_concurrent_consume_and_delivery_uncertainty(base: Path, server) -> dict[str, object]:
    root = base / "concurrent-consume"
    use_root(root)
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
    generated = server.generate_peer_key({"role": "read", "share_host": "127.0.0.1", "share_port": 9})
    keys = peer.issued_keys()
    key = generated.get("key") if isinstance(generated.get("key"), dict) else {}
    key_id = str(key.get("key_id") or "")
    nonce = str(server.pending_downloads(keys)[0].get("download_nonce") or "")

    def consume_once(_index: int) -> bool:
        try:
            result = server.download_pending_key(key_id, nonce, keys)
        except (PermissionError, ValueError):
            return False
        return bool(result.get("key_text"))

    with ThreadPoolExecutor(max_workers=32) as executor:
        outcomes = list(executor.map(consume_once, range(32)))
    require(sum(1 for item in outcomes if item) == 1, "concurrent consume delivered plaintext more than once")
    uncertain = server.public_issued_key(keys[0], keys)
    require(uncertain.get("download_state") == "regenerate_required", "pre-response tombstone did not require regeneration")
    require(uncertain.get("download_unavailable_reason") == "delivery_outcome_unknown_revoke_then_regenerate", "uncertain delivery reason drifted")
    server.mark_pending_key_delivery(key_id, delivered=False)
    failed = server.public_issued_key(keys[0], keys)
    require(failed.get("download_state") == "regenerate_required", "failed delivery became reusable")
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        tombstone = dict(server.PENDING_KEY_DOWNLOADS.get(key_id, {}))
    require(not tombstone.get("key_text") and not tombstone.get("download_nonce"), "delivery-failure tombstone retained secret material")
    return {
        "workers": 32,
        "plaintext_deliveries": 1,
        "delivery_failure_state": "regenerate_required",
        "tombstone_secret_fields": 0,
    }


def check_revoke_before_regenerate(base: Path, server) -> dict[str, object]:
    root = base / "revoke-before-regenerate"
    use_root(root)
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
    first = server.generate_peer_key({"role": "read", "share_host": "127.0.0.1", "share_port": 9})
    old_id = str(first.get("key", {}).get("key_id") or "")
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()

    with mock.patch.object(server, "_export_peer_key_with_snapshot", side_effect=RuntimeError("fixture issue failure")):
        try:
            server.generate_peer_key({
                "role": "read",
                "share_host": "127.0.0.1",
                "share_port": 9,
                "regenerate_from": old_id,
            })
        except RuntimeError:
            pass
        else:
            raise AssertionError("regeneration issue failure was not propagated")
    after_failed_issue = peer.issued_keys()
    old_after_failure = next(item for item in after_failed_issue if str(item.get("key_id") or "") == old_id)
    require(bool(old_after_failure.get("revoked_at")), "old key was not durably revoked before new issue")
    require(not any(str(item.get("regenerate_from") or "") == old_id for item in after_failed_issue), "failed issue committed a replacement")

    replacement = server.generate_peer_key({
        "role": "read",
        "share_host": "127.0.0.1",
        "share_port": 9,
        "regenerate_from": old_id,
    })
    new_id = str(replacement.get("key", {}).get("key_id") or "")
    final_keys = peer.issued_keys()
    old_record = next(item for item in final_keys if str(item.get("key_id") or "") == old_id)
    new_record = next(item for item in final_keys if str(item.get("key_id") or "") == new_id)
    require(bool(old_record.get("revoked_at")), "old key became active after regeneration")
    require(str(new_record.get("regenerate_from") or "") == old_id, "replacement did not bind its revoked predecessor")
    require(not new_record.get("revoked_at"), "new replacement key was not active")
    try:
        server.generate_peer_key({
            "role": "read",
            "share_host": "127.0.0.1",
            "share_port": 9,
            "regenerate_from": old_id,
        })
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate active replacement was issued for the same predecessor")

    revoked = server.manage_key({"action": "delete", "key_id": new_id})
    retained = peer.issued_keys()
    retained_new = next(item for item in retained if str(item.get("key_id") or "") == new_id)
    require(bool(retained_new.get("revoked_at")), "delete compatibility action did not revoke the durable record")
    require(any(str(item.get("key_id") or "") == new_id for item in retained), "delete compatibility action removed durable history")
    require(revoked.get("changed") == 1, "revoke compatibility action did not report one change")
    revoked_at = str(retained_new.get("revoked_at") or "")
    for action in ("renew", "extend", "permanent"):
        result = server.manage_key({"action": action, "key_id": new_id, "days": 30})
        after_action = next(
            item for item in peer.issued_keys()
            if str(item.get("key_id") or "") == new_id
        )
        require(result.get("changed") == 0, f"{action} reactivated a revoked key")
        require(str(after_action.get("revoked_at") or "") == revoked_at, f"{action} cleared revoked_at")
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
    return {
        "old_revoked_before_issue": True,
        "failed_issue_left_old_revoked": True,
        "replacement_bound": True,
        "duplicate_replacement_blocked": True,
        "delete_is_non_destructive_revoke": True,
        "revoked_key_reactivation_blocked": True,
    }


def check_expired_durable_key_blocks_download(base: Path, server) -> dict[str, object]:
    root = base / "expired-durable-key"
    use_root(root)
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
    generated = server.generate_peer_key({"role": "read", "share_host": "127.0.0.1", "share_port": 9})
    keys = peer.issued_keys()
    key = generated.get("key") if isinstance(generated.get("key"), dict) else {}
    key_id = str(key.get("key_id") or "")
    pending = server.pending_downloads(keys)
    require(len(pending) == 1, "expired-key fixture did not create a ready download")
    expired_keys = [dict(record) for record in keys]
    expired_keys[0]["expires_at"] = "2000-01-01T00:00:00"
    public = server.public_issued_key(expired_keys[0], expired_keys)
    require(public.get("download_state") == "regenerate_required", "expired durable key remained download-ready")
    require(server.pending_downloads(expired_keys) == [], "expired durable key remained in the ready list")
    try:
        server.download_pending_key(key_id, str(pending[0].get("download_nonce") or ""), expired_keys)
    except ValueError:
        pass
    else:
        raise AssertionError("expired durable key was downloadable")
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
    return {"expired_key_download_blocked": True, "expired_key_ready_listed": False}


def check_malformed_expiry_fails_closed(base: Path, server) -> dict[str, object]:
    root = base / "malformed-expiry"
    use_root(root)
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
    generated = server.generate_peer_key({"role": "read", "share_host": "127.0.0.1", "share_port": 9})
    keys = peer.issued_keys()
    key = generated.get("key") if isinstance(generated.get("key"), dict) else {}
    key_id = str(key.get("key_id") or "")
    pending = server.pending_downloads(keys)
    require(len(pending) == 1, "malformed-expiry fixture did not create a ready download")

    malformed_keys = [dict(record) for record in keys]
    malformed_keys[0]["expires_at"] = "not-an-iso-time"
    malformed_view = server.public_issued_key(malformed_keys[0], malformed_keys)
    require(malformed_view.get("download_state") == "regenerate_required", "malformed durable expiry failed open")
    require(server.pending_downloads(malformed_keys) == [], "malformed durable expiry remained in the ready list")
    try:
        server.download_pending_key(key_id, str(pending[0].get("download_nonce") or ""), malformed_keys)
    except ValueError:
        pass
    else:
        raise AssertionError("malformed durable expiry was downloadable")

    aware_expired_keys = [dict(record) for record in keys]
    aware_expired_keys[0]["expires_at"] = "2000-01-01T00:00:00+00:00"
    aware_view = server.public_issued_key(aware_expired_keys[0], aware_expired_keys)
    require(aware_view.get("download_state") == "regenerate_required", "timezone-aware expired key failed open")

    future_aware_keys = [dict(record) for record in keys]
    future_aware_keys[0]["expires_at"] = "2999-01-01T00:00:00+08:00"
    future_view = server.public_issued_key(future_aware_keys[0], future_aware_keys)
    require(future_view.get("download_state") == "ready", "timezone-aware future key was rejected")

    invalid_offset_keys = [dict(record) for record in keys]
    invalid_offset_keys[0]["expires_at"] = "2999-01-01T00:00:00+25:00"
    invalid_offset_view = server.public_issued_key(invalid_offset_keys[0], invalid_offset_keys)
    require(invalid_offset_view.get("download_state") == "regenerate_required", "invalid timezone offset failed open")

    missing_expiry_keys = [dict(record) for record in keys]
    missing_expiry_keys[0]["expires_at"] = ""
    missing_expiry_keys[0]["permanent"] = False
    missing_expiry_view = server.public_issued_key(missing_expiry_keys[0], missing_expiry_keys)
    require(missing_expiry_view.get("download_state") == "regenerate_required", "missing non-permanent expiry failed open")

    with server.PENDING_KEY_DOWNLOADS_LOCK:
        server.PENDING_KEY_DOWNLOADS.clear()
        server.PENDING_KEY_DOWNLOADS[key_id] = {
            "key_id": key_id,
            "role": "read",
            "filename": "malformed-expiry.shiguan-key",
            "key_text": "fixture-secret",
            "download_nonce": "fixture-nonce",
            "created_at": "fixture",
            "download_expires_at": "not-an-iso-time",
            "downloaded_at": "",
        }
    require(server.pending_downloads(keys) == [], "malformed ephemeral expiry remained ready")
    with server.PENDING_KEY_DOWNLOADS_LOCK:
        require(key_id not in server.PENDING_KEY_DOWNLOADS, "malformed ephemeral plaintext was not destroyed")
    return {
        "malformed_durable_expiry_closed": True,
        "timezone_aware_expiry_supported": True,
        "future_timezone_aware_supported": True,
        "invalid_timezone_offset_closed": True,
        "missing_non_permanent_expiry_closed": True,
        "malformed_ephemeral_plaintext_destroyed": True,
    }


def check_peer_network_io_outside_state_lock(base: Path, server) -> dict[str, object]:
    root = base / "network-outside-lock"
    use_root(root)

    def seed(state: dict[str, object]) -> None:
        state["imported_peers"] = [{
            "peer_id": "blocked-peer", "key_id": "fixture", "token": "fixture-token",
            "endpoint": "http://127.0.0.1:9/", "disabled": False,
        }]

    initial, _ = peer.update_peer_state(seed)
    peers = peer.imported_peers(initial)
    entered = threading.Event()
    release = threading.Event()

    def blocked_call(*_args, **_kwargs):
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("fixture network release timed out")
        return {"count": 0, "server_time": "fixture", "node": {"node_name": "fixture"}}

    with mock.patch.object(server, "call_peer", side_effect=blocked_call):
        with ThreadPoolExecutor(max_workers=2) as pool:
            reader = pool.submit(server.check_peer_statuses, peers)
            require(entered.wait(timeout=2), "fixture network call did not start")
            writer = pool.submit(
                peer.update_peer_state,
                lambda state: state["issued_keys"].append({"key_id": "writer-progress"}),  # type: ignore[union-attr]
            )
            committed, _ = writer.result(timeout=2)
            release.set()
            statuses = reader.result(timeout=5)
    require(int(committed.get("revision") or 0) == int(initial.get("revision") or 0) + 1, "writer did not progress during blocked network I/O")
    require(statuses and statuses[0].get("status") == "online", "blocked peer read did not finish")
    return {"writer_progressed_before_network_release": True, "peer_file_lock_held_during_network": False}


def check_public_projection_allowlists(base: Path, server) -> dict[str, object]:
    use_root(base / "projection-allowlists")
    key = server.public_issued_key({
        "key_id": "public-key", "role": "read", "token_hash": "hash-secret", "token": "token-secret",
        "file_nonce": "nonce-secret", "unexpected_secret": "extension-secret",
        "clock": {"server_time": "fixture", "token": "clock-secret"},
    }, [])
    peer_public = peer.public_peer({"peer_id": "peer", "node": "node-secret", "clock": "clock-secret"})
    with mock.patch.object(server, "call_peer", return_value={
        "count": 1, "server_time": "fixture", "node": {"node_name": "safe", "token": "remote-secret", "unexpected_secret": "remote-extension"},
    }):
        pinged = server.ping_peer({"peer_id": "peer", "token": "transport-secret", "endpoint": "http://127.0.0.1:9/"})
    serialized = json.dumps({"key": key, "peer": peer_public, "ping": pinged}, ensure_ascii=False)
    require("secret" not in serialized and "nonce" not in serialized, "public allowlist leaked an unknown or nested field")
    return {"issued_key_allowlist": True, "peer_nested_types_closed": True, "remote_node_allowlist": True}


def check_empty_read_zero_write(base: Path, server) -> dict[str, object]:
    root = base / "empty-read"
    use_root(root)
    require(not root.exists(), "empty fixture unexpectedly exists")
    state = peer.peer_state_snapshot()
    server.read_node_identity()
    server.check_peer_statuses(peer.imported_peers(state))
    server.fetch_peer_entries("", 1, peers=peer.imported_peers(state))
    require(not root.exists(), "read-only peer helpers created persistent state")
    return {"revision": 0, "files_created": 0}


def check_peer_endpoint_and_key_protection(base: Path, server) -> dict[str, object]:
    use_root(base / "endpoint-policy")
    require(
        server.validate_peer_endpoint("http://127.0.0.1:8765/") == "http://127.0.0.1:8765",
        "loopback peer endpoint was rejected",
    )
    for endpoint in (
        "http://192.168.1.10:8765/",
        "https://user:pass@example.invalid/",
        "https://example.invalid/?token=secret",
        "https://example.invalid/#fragment",
    ):
        try:
            server.validate_peer_endpoint(endpoint)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe peer endpoint was accepted: {endpoint}")

    handler = server.NoRedirectHandler()
    require(
        handler.redirect_request(None, None, 302, "fixture", {}, "https://other.invalid/") is None,
        "peer redirect handler did not reject redirects",
    )
    exported = server.export_peer_key(
        {"role": "read", "endpoint": "http://127.0.0.1:8765/", "note": "fixture"}
    )
    require(exported.get("protection") == "obfuscation_not_encryption", "key protection metadata missing")
    require(exported.get("credential_semantics") == "bearer_secret_plaintext_equivalent", "key bearer warning missing")
    require(exported.get("recommended_file_mode") == "0600", "key file mode guidance missing")
    decoded = peer.decode_peer_key(str(exported.get("key_text") or ""))
    require(decoded.get("protection") == "obfuscation_not_encryption", "encoded key warning missing")
    return {"remote_http_rejected": True, "redirects_rejected": True, "key_warning_exported": True}


def main() -> int:
    previous_root = os.environ.get("COURT_SHARED_SHIGUAN_ROOT")
    try:
        with tempfile.TemporaryDirectory(prefix="court-peer-state-") as raw_temp:
            base = Path(raw_temp)
            use_root(base / "bootstrap")
            import serve_shiguan_tree as server  # type: ignore

            result = {
                "legacy_read_zero_write": check_legacy_read_zero_write(base),
                "first_mutation": check_first_mutation(base),
                "atomic_failure": check_atomic_failure(base, server),
                "malformed_fail_closed": check_malformed_fail_closed(base),
                "revision_concurrency": check_revision_and_concurrency(base),
                "expire_single_commit": check_expire_single_commit_and_projection(base, server),
                "generate_commit_snapshot": check_generate_uses_commit_snapshot(base, server),
                "pending_snapshot_isolation": check_pending_snapshot_cannot_evict_newer(base, server),
                "ephemeral_restart_contract": check_ephemeral_restart_and_consume_contract(base, server),
                "missing_durable_view_contract": check_missing_durable_view_fails_closed(base, server),
                "concurrent_consume_contract": check_concurrent_consume_and_delivery_uncertainty(base, server),
                "revoke_before_regenerate": check_revoke_before_regenerate(base, server),
                "expired_durable_key_contract": check_expired_durable_key_blocks_download(base, server),
                "malformed_expiry_contract": check_malformed_expiry_fails_closed(base, server),
                "network_io_outside_state_lock": check_peer_network_io_outside_state_lock(base, server),
                "public_projection_allowlists": check_public_projection_allowlists(base, server),
                "empty_read_zero_write": check_empty_read_zero_write(base, server),
                "endpoint_and_key_protection": check_peer_endpoint_and_key_protection(base, server),
            }
            print(json.dumps({"ok": True, "results": result}, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    finally:
        if previous_root is None:
            os.environ.pop("COURT_SHARED_SHIGUAN_ROOT", None)
        else:
            os.environ["COURT_SHARED_SHIGUAN_ROOT"] = previous_root


if __name__ == "__main__":
    raise SystemExit(main())
