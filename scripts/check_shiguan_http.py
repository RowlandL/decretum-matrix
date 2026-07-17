"""Security regression checks for the Shiguan HTTP service and local helpers."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import importlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile


PUBLIC_HEALTH_FIELDS = {
    "ok",
    "service",
    "version",
    "port",
    "read_only",
    "admin_auth_required",
}
PUBLIC_STATE_FIELDS = {
    "service",
    "version",
    "entries",
    "count",
    "local_count",
    "peer_count",
    "shown",
    "shown_total",
    "knowledge_graph",
    "port",
    "read_only",
    "admin_auth",
}
PUBLIC_ENTRY_FIELDS = {
    "id",
    "court_code",
    "ancient_lineage",
    "lineage_display",
    "topic",
    "phase",
    "status",
    "time",
    "record_type",
    "risk_level",
    "knowledge_value",
    "priority_level",
    "court_code_parts",
    "display_summary_zh",
    "display_keywords_zh",
    "source_agent_label",
}
FORBIDDEN_PUBLIC_KEYS = {
    "memory_content",
    "memory_reason",
    "evidence",
    "source",
    "capability_source_paths",
    "shared_shiguan_root",
    "tree_root",
    "index_path",
    "web_root",
    "agent_presence",
    "import_queue",
    "issued_keys",
    "pending_downloads",
    "obsidian_sync",
    "node",
    "peers",
}
SECURITY_HEADERS = {
    "Content-Security-Policy",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Permissions-Policy",
    "Cross-Origin-Resource-Policy",
}
ABSOLUTE_PATH_RE = re.compile(
    r"(?i)(?:[A-Z]:[\\/]|\\\\|/(?:home|users|mnt|tmp|var/tmp)/)[^\s\"'<>]+"
)


def fetch_json(
    url: str,
    timeout: float,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, object] | None = None,
) -> tuple[int, dict[str, object], dict[str, str]]:
    request_headers = {"Accept": "application/json", **(headers or {})}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw or "{}"), dict(response.headers.items())
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"error": raw}
        return int(exc.code), body, dict(exc.headers.items())


def assert_security_headers(headers: dict[str, str]) -> None:
    missing = sorted(name for name in SECURITY_HEADERS if not headers.get(name))
    if missing:
        raise AssertionError(f"missing security headers: {','.join(missing)}")


def assert_public_health(body: dict[str, object]) -> None:
    if set(body) != PUBLIC_HEALTH_FIELDS:
        raise AssertionError(f"public health fields drifted: {sorted(set(body) ^ PUBLIC_HEALTH_FIELDS)}")


def assert_public_state(body: dict[str, object]) -> None:
    if set(body) != PUBLIC_STATE_FIELDS:
        raise AssertionError(f"public state fields drifted: {sorted(set(body) ^ PUBLIC_STATE_FIELDS)}")
    if FORBIDDEN_PUBLIC_KEYS & set(body):
        raise AssertionError("public state contains forbidden top-level fields")
    entries = body.get("entries")
    if not isinstance(entries, list):
        raise AssertionError("public state entries must be a list")
    for entry in entries:
        if not isinstance(entry, dict):
            raise AssertionError("public entry must be an object")
        if not set(entry) <= PUBLIC_ENTRY_FIELDS:
            raise AssertionError(f"public entry contains forbidden fields: {sorted(set(entry) - PUBLIC_ENTRY_FIELDS)}")
        if FORBIDDEN_PUBLIC_KEYS & set(entry):
            raise AssertionError("public entry contains sensitive fields")
    serialized = json.dumps(body, ensure_ascii=False)
    if ABSOLUTE_PATH_RE.search(serialized):
        raise AssertionError("public state contains an absolute local path")


def run_static_regressions() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    scripts = root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    previous_root = os.environ.get("COURT_SHARED_SHIGUAN_ROOT")
    previous_presence = os.environ.get("COURT_DISABLE_AGENT_PRESENCE")
    previous_remote_obsidian = os.environ.get("SHIGUAN_ALLOW_REMOTE_OBSIDIAN_ENDPOINT")
    try:
        with tempfile.TemporaryDirectory(prefix="shiguan-security-check-") as temp_text:
            temp = Path(temp_text)
            os.environ["COURT_SHARED_SHIGUAN_ROOT"] = str(temp / "court-data")
            os.environ["COURT_DISABLE_AGENT_PRESENCE"] = "1"
            server = importlib.import_module("serve_shiguan_tree")
            web_ensure = importlib.import_module("ensure_shiguan_web")
            service_daemon = importlib.import_module("shiguan_service_daemon")
            exporter = importlib.import_module("export_shiguan_obsidian")
            autosync = importlib.import_module("shiguan_autosync_daemon")
            filesystem_sync = importlib.import_module("sync_shiguan_obsidian_vault")
            autosync_ensure = importlib.import_module("ensure_shiguan_autosync")
            index_rebuild = importlib.import_module("rebuild_shiguan_index")

            healthy_filesystem_config = {
                "has_api_key": False,
                "sync_mode": "filesystem_preserve_only",
                "autosync_enabled": True,
            }
            healthy_autosync = {"ok": True, "mode": "daemon", "pid": 5100}
            with (
                mock.patch.object(server, "obsidian_sync_config", return_value=healthy_filesystem_config),
                mock.patch.object(server, "autosync_public_status", return_value=healthy_autosync),
            ):
                healthy_filesystem_status = server.obsidian_sync_status()
                healthy_filesystem_public_state = server.obsidian_sync_public_state()
            if healthy_filesystem_status.get("ok") is not True:
                raise AssertionError("healthy filesystem autosync was reported as overall disconnected")
            if healthy_filesystem_public_state.get("ok") is not True:
                raise AssertionError("healthy filesystem autosync was reported as disconnected in public state")
            status_message = str(healthy_filesystem_status.get("message") or "")
            if "尚未保存 API key" in status_message or "REST" not in status_message or "可选" not in status_message:
                raise AssertionError("optional unconfigured REST channel was not reported as non-blocking")
            public_message = str(healthy_filesystem_public_state.get("message") or "")
            if "尚未保存 API key" in public_message or "REST" not in public_message or "可选" not in public_message:
                raise AssertionError("public state did not preserve the optional REST explanation")
            rest_status = healthy_filesystem_status.get("rest")
            if not isinstance(rest_status, dict) or rest_status.get("configured") is not False:
                raise AssertionError("REST channel configuration state was not separated from overall sync health")

            for one_shot_record in (
                {"ok": True, "mode": "once"},
                {"ok": False, "last_cycle_ok": True, "mode": "once", "phase": "stopped"},
            ):
                one_shot_record["updated_at"] = datetime.now().isoformat(timespec="seconds")
                with mock.patch.object(server, "read_json_file", return_value=one_shot_record):
                    one_shot_public = server.autosync_public_status()
                if one_shot_public.get("ok") is not False:
                    raise AssertionError("mode=once was exposed as permanently healthy autosync")
                if one_shot_public.get("last_cycle_ok") is not True or one_shot_public.get("phase") != "stopped":
                    raise AssertionError("mode=once lost its successful one-shot receipt while clearing daemon health")

            for legacy_mode, expected_enabled in (("auto", True), ("manual", False)):
                normalized = server.obsidian_sync_config(
                    stored_override={"sync_mode": legacy_mode}
                )
                if normalized.get("sync_mode") != "filesystem_preserve_only":
                    raise AssertionError(
                        f"legacy {legacy_mode} scheduling mode escaped the preserve-only backend contract"
                    )
                if bool(normalized.get("autosync_enabled")) is not expected_enabled:
                    raise AssertionError(
                        f"legacy {legacy_mode} scheduling state was not preserved"
                    )
            try:
                server.obsidian_sync_config(stored_override={"sync_mode": "unexpected"})
            except ValueError:
                pass
            else:
                raise AssertionError("an unknown Obsidian backend sync mode did not fail closed")

            legacy_base = {
                "endpoint": "https://127.0.0.1:27124",
                "verify_ssl": False,
                "sync_mode": "filesystem_preserve_only",
                "auto_enabled": True,
                "autosync_enabled": True,
                "vault_path": str(temp / "vault"),
                "cache_vault_path": str(temp / "vault"),
                "source_vault_path": str(temp / "source"),
                "parent_vault_path": str(temp / "parent"),
                "watch_paths": [str(temp / "vault")],
            }
            with (
                mock.patch.object(server, "read_obsidian_sync_config_snapshot", return_value=legacy_base),
                mock.patch.object(
                    server,
                    "patch_obsidian_sync_config",
                    return_value={
                        "conflict": False,
                        "committed_revision": 1,
                        "transaction_id": "legacy-mode-fixture",
                        "post_write_verified": True,
                    },
                ) as patch_config,
            ):
                server.save_obsidian_sync_config({"sync_mode": "manual"})
            legacy_changes = patch_config.call_args.args[0]
            if legacy_changes.get("sync_mode") != "filesystem_preserve_only":
                raise AssertionError("legacy manual save escaped the preserve-only backend contract")
            if legacy_changes.get("auto_enabled") is not False or legacy_changes.get("autosync_enabled") is not False:
                raise AssertionError("legacy manual save did not disable autosync scheduling consistently")

            long_cycle_status = {
                "ok": True,
                "mode": "daemon",
                "phase": "running",
                "updated_at": (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds"),
                "fresh_for_seconds": 1260,
            }
            if not autosync_ensure.status_is_fresh(long_cycle_status, 30):
                raise AssertionError("a bounded in-progress autosync cycle was reported as stale")
            with mock.patch.object(server, "read_json_file", return_value=long_cycle_status):
                legacy_running_public = server.autosync_public_status()
            if legacy_running_public.get("ok") is not False or legacy_running_public.get("phase") != "running":
                raise AssertionError("a legacy 1260-second running status remained false-green")
            idle_status = {**long_cycle_status, "phase": "idle"}
            if autosync_ensure.status_is_fresh(idle_status, 30):
                raise AssertionError("an actually stale idle autosync status was reported as fresh")

            daemon_status_writes: list[dict[str, object]] = []

            def capture_daemon_status(_path, value):
                daemon_status_writes.append(dict(value))

            with (
                mock.patch.object(autosync, "ensure_shared_seed"),
                mock.patch.object(autosync, "write_json", side_effect=capture_daemon_status),
                mock.patch.object(autosync, "run_once", side_effect=KeyboardInterrupt),
            ):
                try:
                    autosync.daemon_loop(20)
                except KeyboardInterrupt:
                    pass
            for phase in ("starting", "running"):
                status = next(
                    (item for item in daemon_status_writes if item.get("phase") == phase),
                    None,
                )
                if not isinstance(status, dict):
                    raise AssertionError(f"autosync daemon omitted its {phase} status")
                if status.get("ok") is not False:
                    raise AssertionError(
                        f"autosync daemon pre-declared the {phase} phase healthy before a cycle completed"
                    )

            active_running_status = {
                "ok": True,
                "mode": "daemon",
                "phase": "running",
                "pid": 5100,
                "interval_seconds": 30,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "fresh_for_seconds": 1260,
            }
            with (
                mock.patch.object(autosync_ensure, "read_json", return_value=active_running_status),
                mock.patch.object(autosync_ensure, "pid_alive", return_value=True),
                mock.patch.object(autosync_ensure, "find_running_daemon_pid", return_value=5100),
            ):
                running_probe = autosync_ensure._ensure_unlocked(30, check_only=True)
            if running_probe.get("status") != "REUSED":
                raise AssertionError("an exact, fresh running daemon was not reusable")
            if running_probe.get("cycle_phase") != "running" or running_probe.get("cycle_ok") is not False:
                raise AssertionError("running daemon reuse was reported as completed healthy work")

            ensure_status_writes: list[dict[str, object]] = []
            with (
                mock.patch.object(autosync_ensure, "read_json", return_value={}),
                mock.patch.object(autosync_ensure, "pid_alive", return_value=False),
                mock.patch.object(autosync_ensure, "find_running_daemon_pid", return_value=0),
                mock.patch.object(autosync_ensure, "ensure_shared_seed"),
                mock.patch.object(autosync_ensure, "start_daemon", return_value=5200),
                mock.patch.object(
                    autosync_ensure,
                    "write_json",
                    side_effect=lambda _path, value: ensure_status_writes.append(dict(value)),
                ),
            ):
                started_probe = autosync_ensure._ensure_unlocked(30, check_only=False)
            if started_probe.get("status") != "STARTED" or len(ensure_status_writes) != 1:
                raise AssertionError("autosync ensure did not expose the bounded starting transition")
            started_status = ensure_status_writes[0]
            if started_status.get("ok") is not False or started_status.get("phase") != "starting":
                raise AssertionError("autosync ensure pre-declared a newly spawned daemon healthy")

            unchanged_index = temp / "unchanged-index.jsonl"
            unchanged_index.write_text("same\n", encoding="utf-8")
            unchanged_mtime = unchanged_index.stat().st_mtime_ns
            if index_rebuild.write_index_if_changed(unchanged_index, "same\n") is not False:
                raise AssertionError("unchanged Shiguan index was rewritten")
            if unchanged_index.stat().st_mtime_ns != unchanged_mtime:
                raise AssertionError("unchanged Shiguan index mtime drifted and would trigger autosync")
            if index_rebuild.write_index_if_changed(unchanged_index, "changed\n") is not True:
                raise AssertionError("changed Shiguan index was not written")

            before_refresh = {"refresh_request": {"mtime_ns": 1}}
            during_refresh = {"refresh_request": {"mtime_ns": 2}}
            with (
                mock.patch.object(autosync, "ensure_shared_seed"),
                mock.patch.object(autosync, "sync_config", return_value={}),
                mock.patch.object(autosync, "configured_watch_roots", return_value=[]),
                mock.patch.object(
                    autosync,
                    "read_json",
                    return_value={"snapshot": {"seed": {}}, "source_signature": {"old": {}}},
                ),
                mock.patch.object(autosync, "source_signature", side_effect=[before_refresh, during_refresh]) as signature,
                mock.patch.object(autosync, "configured_cache_vault", return_value=temp / "cache"),
                mock.patch.object(autosync, "managed_sync_hashes", return_value={}),
                mock.patch.object(autosync, "snapshot_roots", side_effect=[{}, {}]),
                mock.patch.object(autosync, "queue_vault_changes", return_value=[]),
                mock.patch.object(autosync, "run_filesystem_sync", return_value={"ok": True, "removed": 0}),
                mock.patch.object(autosync, "write_json") as write_json,
            ):
                concurrent_refresh_report = autosync._run_once_unlocked()
            if signature.call_count != 1 or concurrent_refresh_report.get("source_signature") != before_refresh:
                raise AssertionError("a refresh requested during sync could be swallowed by the completed cycle")
            one_shot_statuses = [
                call.args[1]
                for call in write_json.call_args_list
                if isinstance(call.args[1], dict) and call.args[1].get("mode") == "once"
            ]
            if len(one_shot_statuses) != 1:
                raise AssertionError("mode=once status receipt was not written exactly once")
            one_shot_status = one_shot_statuses[0]
            if (
                one_shot_status.get("ok") is not False
                or one_shot_status.get("last_cycle_ok") is not True
                or one_shot_status.get("phase") != "stopped"
            ):
                raise AssertionError("mode=once status file claimed permanent daemon health")

            lock_events: list[str] = []

            class TrackingLock:
                def __init__(self, label: str):
                    self.label = label

                def __enter__(self):
                    lock_events.append(f"enter:{self.label}")

                def __exit__(self, _kind, _value, _traceback):
                    lock_events.append(f"exit:{self.label}")

            def tracking_lock(path, **_kwargs):
                return TrackingLock(Path(path).name)

            def tracked_cycle(**_kwargs):
                lock_events.append("run:cycle")
                return {"ok": True}

            with (
                mock.patch.object(autosync, "file_lock", side_effect=tracking_lock),
                mock.patch.object(autosync, "sync_config", return_value={}),
                mock.patch.object(autosync, "_run_once_unlocked", side_effect=tracked_cycle),
            ):
                autosync.run_once(lock_timeout=0)
            config_enter = f"enter:{autosync.config_lock_path().name}"
            config_exit = f"exit:{autosync.config_lock_path().name}"
            cycle_event = "run:cycle"
            if not all(event in lock_events for event in (config_enter, cycle_event, config_exit)):
                raise AssertionError("autosync config lock lifecycle evidence is incomplete")
            if not (
                lock_events.index(config_enter)
                < lock_events.index(cycle_event)
                < lock_events.index(config_exit)
            ):
                raise AssertionError("autosync released the config lock before the filesystem cycle completed")

            daemon_source = (scripts / "shiguan_autosync_daemon.py").read_text(encoding="utf-8")
            for marker in ('"phase": "running"', '"fresh_for_seconds":'):
                if marker not in daemon_source:
                    raise AssertionError(f"autosync in-progress heartbeat contract missing: {marker}")

            presence = temp / "presence"
            presence.mkdir()
            (presence / "fresh.json").write_text(
                json.dumps(
                    {
                        "agent_id": "fresh",
                        "label": "Fresh",
                        "last_seen": datetime.now().isoformat(timespec="seconds"),
                        "ttl_seconds": 180,
                    }
                ),
                encoding="utf-8",
            )
            (presence / "stale.json").write_text(
                json.dumps(
                    {
                        "agent_id": "stale",
                        "label": "Stale",
                        "last_seen": (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds"),
                        "ttl_seconds": 180,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(server, "agent_presence_root", return_value=presence):
                presence_statuses = server.agent_presence_statuses()
            if [item.get("agent_id") for item in presence_statuses] != ["fresh"]:
                raise AssertionError("stale agent presence was exposed as current WebUI status")

            timeout_vault = temp / "timeout-vault"
            timeout_vault.mkdir()
            timeout_config = {
                "endpoint": "https://127.0.0.1:27124",
                "verify_ssl": False,
                "sync_mode": "filesystem_preserve_only",
                "autosync_interval_seconds": 20,
                "vault_path": str(timeout_vault),
                "cache_vault_path": str(timeout_vault),
                "source_vault_path": str(temp / "source"),
                "parent_vault_path": str(temp / "parent"),
            }
            with (
                mock.patch.object(server, "read_obsidian_sync_config_snapshot", return_value={}),
                mock.patch.object(server, "obsidian_sync_config", return_value=timeout_config),
                mock.patch.object(server, "default_obsidian_inbox", return_value=temp / "inbox"),
                mock.patch.object(server, "autosync_daemon_health", return_value={"status": "REUSED", "pid": 5100}),
                mock.patch.object(
                    server,
                    "request_obsidian_autosync_refresh",
                    return_value={"requested_at": "2026-07-17T03:00:00", "path": str(temp / "refresh.json")},
                ),
                mock.patch.object(server, "patch_obsidian_sync_config") as patch_config,
                mock.patch.object(server.subprocess, "run") as run_subprocess,
            ):
                queued_sync = server.obsidian_filesystem_sync(
                    {"vault_path": str(timeout_vault), "save_config": False}
                )
            if patch_config.called or run_subprocess.called:
                raise AssertionError("a healthy daemon refresh mutated config or launched a competing forced cycle")
            if queued_sync.get("filesystem_sync", {}).get("reason") != "daemon_refresh_requested":
                raise AssertionError("the WebUI file sync action did not enqueue the existing daemon")

            with (
                mock.patch.object(server, "read_obsidian_sync_config_snapshot", return_value={}),
                mock.patch.object(server, "obsidian_sync_config", return_value=timeout_config),
                mock.patch.object(server, "default_obsidian_inbox", return_value=temp / "inbox"),
                mock.patch.object(server, "autosync_daemon_health", return_value={"status": "NOT_RUNNING", "pid": 0}),
                mock.patch.object(
                    server,
                    "patch_obsidian_sync_config",
                    return_value={"conflict": False, "committed_revision": 1, "transaction_id": "fixture", "post_write_verified": True},
                ),
                mock.patch.object(
                    server.subprocess,
                    "run",
                    side_effect=server.subprocess.TimeoutExpired(cmd="autosync", timeout=30),
                ),
            ):
                try:
                    server.obsidian_filesystem_sync(
                        {"vault_path": str(timeout_vault), "timeout_seconds": 30, "save_config": True}
                    )
                except TimeoutError as exc:
                    if "30" not in str(exc) or "超时" not in str(exc):
                        raise AssertionError("autosync timeout was not actionable") from exc
                except server.subprocess.TimeoutExpired as exc:
                    raise AssertionError("raw subprocess timeout escaped the Web orchestration boundary") from exc
                else:
                    raise AssertionError("autosync timeout did not fail")

            local_exception_logger = getattr(server, "log_local_exception", None)
            if not callable(local_exception_logger):
                raise AssertionError("generic Web management failures are not written to the promised local log")
            with (
                mock.patch.object(server.traceback, "print_exc") as print_exc,
                mock.patch.object(server.sys, "stderr", io.StringIO()),
            ):
                try:
                    raise RuntimeError("fixture")
                except RuntimeError:
                    local_exception_logger("fixture")
            if print_exc.call_count != 1:
                raise AssertionError("local exception logger did not preserve a traceback")

            app_source = (root / "web" / "shiguan-tree" / "app.js").read_text(encoding="utf-8")
            dialog_start = app_source.index("async function openObsidianSyncDialog")
            dialog_end = app_source.index("async function pushCurrentShiguanToObsidianRest")
            dialog_source = app_source[dialog_start:dialog_end]
            for marker in (
                "let actionBusy = false;",
                "setObsidianActionBusy",
                "执行中：",
                "status.rest?.ok",
                "save_config: false",
                'sync_mode: "filesystem_preserve_only"',
                "autosync_enabled: Boolean(el.obsidianAutoEnabled?.checked)",
                "AI 心跳",
                "文件同步请求已提交",
            ):
                if marker not in app_source:
                    raise AssertionError(f"WebUI interaction/status contract missing: {marker}")
            for forbidden in ('const syncMode =', 'sync_mode: "manual"', "sync_mode: syncMode"):
                if forbidden in app_source:
                    raise AssertionError(
                        f"WebUI scheduling mode leaked into the preserve-only backend contract: {forbidden}"
                    )
            if dialog_source.count("resolve(null);") != 4:
                raise AssertionError("Obsidian dialog resolves before it is actually closed")
            if '共享机器 ${peerTotal} 台' in app_source:
                raise AssertionError("top status duplicates the peer summary already shown in status chips")

            if server.DEFAULT_BIND_HOST != "127.0.0.1":
                raise AssertionError("serve_shiguan_tree default bind is not loopback")
            if web_ensure.DEFAULT_BIND_HOST != "127.0.0.1":
                raise AssertionError("ensure_shiguan_web default bind is not loopback")
            if service_daemon.DEFAULT_BIND_HOST != "127.0.0.1":
                raise AssertionError("shiguan_service_daemon default bind is not loopback")
            loopback_result = web_ensure.result("CHECK_ONLY", "127.0.0.1", 8765)
            lan_result = web_ensure.result("CHECK_ONLY", "0.0.0.0", 8765)
            if loopback_result.get("explicit_lan_opt_in") is not False:
                raise AssertionError("loopback result was mislabeled as LAN opt-in")
            if lan_result.get("explicit_lan_opt_in") is not True:
                raise AssertionError("wildcard result did not label explicit LAN opt-in")
            if server.validate_peer_endpoint("http://127.0.0.1:8765/") != "http://127.0.0.1:8765":
                raise AssertionError("loopback peer endpoint was rejected")
            for unsafe_peer in (
                "http://192.168.1.10:8765/",
                "https://user:pass@example.invalid/",
                "https://example.invalid/?token=secret",
                "https://example.invalid/#fragment",
            ):
                try:
                    server.validate_peer_endpoint(unsafe_peer)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"unsafe peer endpoint was accepted: {unsafe_peer}")

            blank_identity_root = temp / "court-data"
            identity = server.read_node_identity()
            if identity.get("status") != "missing" or blank_identity_root.exists():
                raise AssertionError("read-only node identity lookup created persistent state")

            canary = server.public_entry_projection(
                {
                    "id": "safe-id",
                    "topic": r"C:\\Users\\Example\\private.md",
                    "display_summary_zh": "token=do-not-expose",
                    "memory_content": "private",
                    "evidence": "private",
                    "source": r"C:\\Users\\Example\\source.jsonl",
                    "capability_source_paths": [r"C:\\Users\\Example\\session.jsonl"],
                }
            )
            if FORBIDDEN_PUBLIC_KEYS & set(canary):
                raise AssertionError("public projection retained sensitive keys")
            canary_text = json.dumps(canary, ensure_ascii=False)
            if "do-not-expose" in canary_text or ABSOLUTE_PATH_RE.search(canary_text):
                raise AssertionError("public projection failed content redaction")

            unknown = temp / "unknown-export"
            unknown.mkdir()
            sentinel = unknown / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")
            try:
                exporter.export_destination_mode(unknown)
            except ValueError:
                pass
            else:
                raise AssertionError("unknown non-empty export directory was accepted")
            if sentinel.read_text(encoding="utf-8") != "keep":
                raise AssertionError("export destination guard modified the sentinel")
            empty = temp / "empty-export"
            empty.mkdir()
            if exporter.export_destination_mode(empty) != "empty":
                raise AssertionError("empty export directory was not accepted")
            managed = temp / "managed-export"
            managed.mkdir()
            exporter.write_managed_marker(managed)
            (managed / "generated.md").write_text("generated", encoding="utf-8")
            if exporter.export_destination_mode(managed) != "managed":
                raise AssertionError("managed export directory was not accepted")
            preserve_cache = temp / "preserve-cache"
            preserve_cache.mkdir()
            preserve_sentinel = preserve_cache / "user-note.md"
            preserve_sentinel.write_text("keep this user note", encoding="utf-8")
            exporter.write_managed_marker(preserve_cache)
            filesystem_sync.write_sync_manifest(
                preserve_cache,
                {
                    "schema": filesystem_sync.SYNC_MANIFEST_SCHEMA,
                    "state": "committed",
                    "managed_by": "court-capability-router",
                    "updated_at": "fixture",
                    "files": {},
                },
            )
            try:
                exporter.export_destination_mode(preserve_cache)
            except ValueError:
                pass
            else:
                raise AssertionError("preserve-only cache was accepted for wholesale export replacement")
            if preserve_sentinel.read_text(encoding="utf-8") != "keep this user note":
                raise AssertionError("preserve-only export guard modified the user sentinel")

            source = temp / "source-note.md"
            source.write_text("security regression fixture", encoding="utf-8")
            imported = server.import_obsidian({"path": str(source), "commit": True})
            if imported.get("committed") is not False or imported.get("status") != "pending_review":
                raise AssertionError("Obsidian import bypassed pending review")
            index = temp / "court-data" / "references" / "shiguan-index.jsonl"
            if index.exists() and index.read_text(encoding="utf-8").strip():
                raise AssertionError("Obsidian import wrote the official index")
            pending = temp / "court-data" / "references" / "shiguan-imports" / "pending"
            pending_bodies = [
                path for path in pending.glob("*.json")
                if not path.name.endswith(".metadata.json")
            ]
            if len(pending_bodies) != 1:
                raise AssertionError("Obsidian import did not create exactly one pending record")
            sidecar = pending / f"{pending_bodies[0].stem}.metadata.json"
            sidecar_value = json.loads(sidecar.read_text(encoding="utf-8"))
            required_sidecar = {
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
            if set(sidecar_value) != required_sidecar or "text" in sidecar_value or "raw_text" in sidecar_value:
                raise AssertionError("pending metadata sidecar contract drifted")
            sidecar.unlink()
            duplicate = server.import_obsidian({"path": str(source), "commit": True})
            if duplicate.get("queue", {}).get("duplicate_count") != 1 or not sidecar.is_file():
                raise AssertionError("duplicate import did not repair the metadata sidecar")
            original_read_text = Path.read_text
            original_open = Path.open

            def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
                if path.resolve() == pending_bodies[0].resolve():
                    raise AssertionError("pending body was opened during metadata-only summary")
                return original_read_text(path, *args, **kwargs)

            def guarded_open(path: Path, *args: object, **kwargs: object):
                if path.resolve() == pending_bodies[0].resolve():
                    raise AssertionError("pending body was opened during metadata-only summary")
                return original_open(path, *args, **kwargs)

            with mock.patch.object(Path, "read_text", guarded_read_text), mock.patch.object(Path, "open", guarded_open):
                queue_summary = server.import_queue_summary()
            if queue_summary.get("pending_count") != 1 or queue_summary.get("unknown_metadata_count") != 0:
                raise AssertionError("metadata-only queue summary did not use the repaired sidecar")

            if server.validate_obsidian_endpoint("https://127.0.0.1:27124", False) != "https://127.0.0.1:27124":
                raise AssertionError("loopback Obsidian endpoint was rejected")
            os.environ.pop("SHIGUAN_ALLOW_REMOTE_OBSIDIAN_ENDPOINT", None)
            try:
                server.validate_obsidian_endpoint("https://obsidian.example", True)
            except ValueError:
                pass
            else:
                raise AssertionError("remote Obsidian endpoint was accepted without explicit opt-in")
            os.environ["SHIGUAN_ALLOW_REMOTE_OBSIDIAN_ENDPOINT"] = "1"
            try:
                server.validate_obsidian_endpoint("https://obsidian.example", False)
            except ValueError:
                pass
            else:
                raise AssertionError("remote Obsidian endpoint was accepted without TLS verification")
            server.validate_obsidian_endpoint("https://obsidian.example", True)

            for unsafe in (
                Path(Path.home().anchor),
                Path.home(),
                server.skill_root(),
                server.skill_root() / "scripts",
                server.shiguan_shared_root(),
                server.shiguan_shared_root() / "references",
            ):
                try:
                    server.validate_local_content_root(unsafe, "security regression path")
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"unsafe watch/import root was accepted: {unsafe}")
            server.validate_local_content_root(server.default_obsidian_inbox(), "dedicated ingress")
            saved_config = server.save_obsidian_sync_config({})
            if not server.obsidian_endpoint_is_loopback(str(saved_config.get("endpoint") or "")):
                raise AssertionError("default Obsidian sync config did not remain loopback-only")
            try:
                server.validated_obsidian_import_paths([str(Path.home())])
            except ValueError:
                pass
            else:
                raise AssertionError("absolute Obsidian import_path was accepted")
            daemon_roots = autosync.configured_watch_roots(
                {
                    "watch_paths": [
                        str(temp / "cache-vault"),
                        str(server.default_obsidian_inbox()),
                    ]
                }
            )
            if len(daemon_roots) != 2:
                raise AssertionError("autosync daemon rejected safe dedicated watch roots")
            try:
                autosync.configured_watch_roots({"watch_paths": [str(server.skill_root() / "scripts")]})
            except ValueError:
                pass
            else:
                raise AssertionError("autosync daemon accepted a skill-tree watch root")

            stale_status = {"pid": 777, "updated_at": "2000-01-01T00:00:00", "interval_seconds": 30}
            with (
                mock.patch.object(autosync_ensure, "read_json", return_value=stale_status),
                mock.patch.object(autosync_ensure, "pid_alive", side_effect=lambda pid: pid == 777),
                mock.patch.object(autosync_ensure, "find_running_daemon_pid", return_value=0),
                mock.patch.object(autosync_ensure, "start_daemon", return_value=888),
            ):
                stale_report = autosync_ensure.ensure(30, check_only=False)
            if stale_report.get("status") != "STARTED" or stale_report.get("pid") != 888:
                raise AssertionError("stale autosync status PID was incorrectly reused")
            with (
                mock.patch.object(autosync_ensure, "read_json", return_value=stale_status),
                mock.patch.object(autosync_ensure, "pid_alive", side_effect=lambda pid: pid == 777),
                mock.patch.object(autosync_ensure, "find_running_daemon_pid", return_value=777),
            ):
                stale_check = autosync_ensure.ensure(30, check_only=True)
            if stale_check.get("status") != "RUNNING_UNHEALTHY":
                raise AssertionError("check-only hid a stale but still-running autosync daemon")

            # A daemon restart after the cache copy but before snapshot commit
            # must not re-import the router's own generated Markdown. A genuine
            # user edit still differs from the published manifest and must enter
            # pending review with a metadata-only sidecar.
            cache_vault = temp / "cache-vault"
            generated_source = temp / "generated-source"
            cache_vault.mkdir(exist_ok=True)
            generated_source.mkdir()
            generated_note = generated_source / "generated.md"
            generated_note.write_text("generated by Shiguan", encoding="utf-8")
            (cache_vault / "generated.md").write_text("generated by Shiguan", encoding="utf-8")
            applying_manifest = filesystem_sync.generated_sync_manifest(generated_source, "applying")
            filesystem_sync.write_sync_manifest(cache_vault, applying_manifest)
            generated_snapshot = autosync.snapshot_roots([cache_vault])
            generated_key = next(iter(generated_snapshot))
            stale_snapshot = {
                generated_key: {
                    **generated_snapshot[generated_key],
                    "sha256": "0" * 64,
                }
            }
            restart_events = autosync.queue_vault_changes(
                stale_snapshot,
                generated_snapshot,
                False,
                cache_vault=cache_vault,
                generated_hashes=autosync.managed_sync_hashes(cache_vault),
            )
            if len(restart_events) != 1 or restart_events[0].get("reason") != "managed_sync_output":
                raise AssertionError("autosync restart re-imported managed cache output")

            bootstrap_note = cache_vault / "user-bootstrap.md"
            bootstrap_note.write_text("pre-existing user note", encoding="utf-8")
            bootstrap_snapshot = autosync.snapshot_roots([cache_vault])
            bootstrap_events = autosync.queue_vault_changes(
                {},
                bootstrap_snapshot,
                True,
                cache_vault=cache_vault,
                generated_hashes=autosync.managed_sync_hashes(cache_vault),
            )
            if sum(1 for item in bootstrap_events if item.get("reason") == "managed_sync_output") != 1:
                raise AssertionError("first-run provenance did not suppress the exact managed output")
            if sum(1 for item in bootstrap_events if item.get("queued")) != 1:
                raise AssertionError("first-run provenance silently adopted an untracked cache note")
            bootstrap_note.unlink()

            bootstrap_inbox = temp / "bootstrap-inbox"
            bootstrap_inbox.mkdir()
            (bootstrap_inbox / "incoming.md").write_text("existing inbound note", encoding="utf-8")
            inbox_events = autosync.queue_vault_changes(
                {},
                autosync.snapshot_roots([bootstrap_inbox]),
                True,
                cache_vault=cache_vault,
                generated_hashes=autosync.managed_sync_hashes(cache_vault),
            )
            if len(inbox_events) != 1 or not inbox_events[0].get("queued"):
                raise AssertionError("first-run provenance silently adopted the dedicated inbox")

            legacy_cache = temp / "legacy-cache-no-manifest"
            legacy_inbox = temp / "legacy-inbox"
            legacy_source = temp / "legacy-generated-source"
            legacy_cache.mkdir()
            legacy_inbox.mkdir()
            legacy_source.mkdir()
            (legacy_cache / "generated.md").write_text("managed legacy output", encoding="utf-8")
            (legacy_source / "generated.md").write_text("managed legacy output", encoding="utf-8")
            (legacy_cache / "user-note.md").write_text("user note must queue", encoding="utf-8")
            (legacy_inbox / "incoming.md").write_text("inbox note must queue", encoding="utf-8")
            autosync.write_json(
                autosync.reference_path("obsidian-sync", "config.json"),
                {
                    "cache_vault_path": str(legacy_cache),
                    "watch_paths": [str(legacy_cache), str(legacy_inbox)],
                },
            )
            if autosync.state_path().exists():
                autosync.state_path().unlink()

            def fake_legacy_sync(_config: dict[str, object]) -> dict[str, object]:
                filesystem_sync.write_sync_manifest(
                    legacy_cache,
                    filesystem_sync.generated_sync_manifest(legacy_source, "committed"),
                )
                return {
                    "ok": True,
                    "preserve_only": True,
                    "removed": 0,
                    "user_modified_conflicts": [],
                    "user_modified_conflict_count": 0,
                }

            with mock.patch.object(autosync, "run_filesystem_sync", fake_legacy_sync):
                legacy_report = autosync.run_once(force_sync=False)
            if not legacy_report.get("deferred_cache_bootstrap"):
                raise AssertionError("legacy cache bootstrap was not deferred until provenance existed")
            if legacy_report.get("queued_count") != 2:
                raise AssertionError("legacy cache bootstrap flooded generated files or lost user/inbox notes")
            if legacy_report.get("managed_output_skip_count") != 1:
                raise AssertionError("legacy cache generated file did not become manifest-managed")

            migration_source = temp / "legacy-migration-source"
            migration_cache = temp / "legacy-migration-cache"
            migration_source.mkdir()
            migration_cache.mkdir()
            (migration_source / "generated.md").write_text("generated-v1", encoding="utf-8")
            (migration_cache / "generated.md").write_text("generated-v1", encoding="utf-8")
            (migration_source / "index.jsonl").write_text('{"v":1}\n', encoding="utf-8")
            (migration_cache / "index.jsonl").write_text('{"v":1}\n', encoding="utf-8")
            exporter.write_managed_marker(migration_cache)
            autosync.write_json(
                autosync.state_path(),
                {
                    "cache_vault_path": str(migration_cache),
                    "snapshot": autosync.snapshot_roots([migration_cache]),
                },
            )
            (migration_source / "generated.md").write_text("generated-v2", encoding="utf-8")
            (migration_source / "index.jsonl").write_text('{"v":2}\n', encoding="utf-8")
            migration_result = filesystem_sync.mirror_tree(migration_source, migration_cache)
            if migration_result.get("updated") != 2 or migration_result.get("user_modified_conflict_count") != 0:
                raise AssertionError("legacy cache provenance did not permit generated updates")
            if migration_result.get("manifest_migration_source") != "legacy_autosync_snapshot_and_managed_nontext":
                raise AssertionError("legacy cache did not record its provenance migration source")
            if not migration_result.get("legacy_export_marker_removed"):
                raise AssertionError("legacy managed-export marker was not removed after manifest creation")

            (cache_vault / "generated.md").write_text("user edited note", encoding="utf-8")
            conflict_result = filesystem_sync.mirror_tree(generated_source, cache_vault)
            if conflict_result.get("user_modified_conflict_count") != 1:
                raise AssertionError("preserve-only sync did not identify a user-modified cache conflict")
            if (cache_vault / "generated.md").read_text(encoding="utf-8") != "user edited note":
                raise AssertionError("preserve-only sync overwrote a user-modified cache note")
            edited_snapshot = autosync.snapshot_roots([cache_vault])
            edit_events = autosync.queue_vault_changes(
                generated_snapshot,
                edited_snapshot,
                False,
                cache_vault=cache_vault,
                generated_hashes=autosync.managed_sync_hashes(cache_vault),
            )
            if len(edit_events) != 1 or not edit_events[0].get("queued"):
                raise AssertionError("autosync suppressed a genuine cache-vault edit")
            edit_sidecar = Path(str(edit_events[0].get("metadata_sidecar") or ""))
            edit_metadata = json.loads(edit_sidecar.read_text(encoding="utf-8"))
            if set(edit_metadata) != required_sidecar or "text" in edit_metadata or "raw_text" in edit_metadata:
                raise AssertionError("autosync pending import omitted its metadata-only sidecar")

            json_source = temp / "json-source"
            json_cache = temp / "json-cache"
            json_source.mkdir()
            json_cache.mkdir()
            (json_source / "generated.jsonl").write_text('{"version":1}\n', encoding="utf-8")
            (json_cache / "generated.jsonl").write_text('{"version":1}\n', encoding="utf-8")
            filesystem_sync.write_sync_manifest(
                json_cache,
                filesystem_sync.generated_sync_manifest(json_source, "committed"),
            )
            (json_source / "generated.jsonl").write_text('{"version":2}\n', encoding="utf-8")
            json_update = filesystem_sync.mirror_tree(json_source, json_cache)
            if json_update.get("updated") != 1 or json_update.get("user_modified_conflict_count") != 0:
                raise AssertionError("generated JSON/JSONL was not refreshed through the manifest")
            if (json_cache / "generated.jsonl").read_text(encoding="utf-8") != '{"version":2}\n':
                raise AssertionError("generated JSON/JSONL cache stayed stale")
            (json_cache / "generated.jsonl").write_text('{"user":"edit"}\n', encoding="utf-8")
            (json_source / "generated.jsonl").write_text('{"version":3}\n', encoding="utf-8")
            json_conflict = filesystem_sync.mirror_tree(json_source, json_cache)
            if json_conflict.get("user_modified_conflict_count") != 1:
                raise AssertionError("user-modified JSON/JSONL conflict was not preserved")
            if (json_cache / "generated.jsonl").read_text(encoding="utf-8") != '{"user":"edit"}\n':
                raise AssertionError("user-modified JSON/JSONL was overwritten")

            race_source = temp / "race-source"
            race_cache = temp / "race-cache"
            race_source.mkdir()
            race_cache.mkdir()
            (race_source / "race.md").write_text("generated-v1", encoding="utf-8")
            (race_cache / "race.md").write_text("generated-v1", encoding="utf-8")
            filesystem_sync.write_sync_manifest(
                race_cache,
                filesystem_sync.generated_sync_manifest(race_source, "committed"),
            )
            (race_source / "race.md").write_text("generated-v2", encoding="utf-8")
            original_copy2 = filesystem_sync.shutil.copy2

            def racing_copy2(src: Path, dst: Path, *args: object, **kwargs: object) -> object:
                copied = original_copy2(src, dst, *args, **kwargs)
                (race_cache / "race.md").write_text("user edit during copy", encoding="utf-8")
                return copied

            with mock.patch.object(filesystem_sync.shutil, "copy2", side_effect=racing_copy2):
                race_result = filesystem_sync.mirror_tree(race_source, race_cache)
            if race_result.get("user_modified_conflict_count") != 1:
                raise AssertionError("hash-to-replace race did not become a user conflict")
            if (race_cache / "race.md").read_text(encoding="utf-8") != "user edit during copy":
                raise AssertionError("staged sync overwrote an edit made during copy")

            def assert_serialized(lock_call, patched_target: object, patched_name: str) -> None:
                active = 0
                max_active = 0
                guard = threading.Lock()
                errors: list[BaseException] = []

                def fake_work(*_args: object, **_kwargs: object) -> object:
                    nonlocal active, max_active
                    with guard:
                        active += 1
                        max_active = max(max_active, active)
                    time.sleep(0.05)
                    with guard:
                        active -= 1
                    return {} if patched_name == "_run_once_unlocked" else 0

                def worker() -> None:
                    try:
                        lock_call()
                    except BaseException as exc:  # pragma: no cover - evidence capture
                        errors.append(exc)

                with mock.patch.object(patched_target, patched_name, side_effect=fake_work):
                    threads = [threading.Thread(target=worker) for _ in range(2)]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join(timeout=5)
                if errors or any(thread.is_alive() for thread in threads) or max_active != 1:
                    raise AssertionError(f"sync lock did not serialize workers: errors={errors} max={max_active}")

            assert_serialized(
                lambda: autosync.run_once(lock_timeout=2.0),
                autosync,
                "_run_once_unlocked",
            )
            lock_args = argparse.Namespace(lock_timeout=2.0, result_json="", zip=False)
            assert_serialized(
                lambda: filesystem_sync.run_locked_write_sync(lock_args, temp / "locked-vault"),
                filesystem_sync,
                "run_write_sync",
            )

            status_source = temp / "status-source"
            status_cache = temp / "status-cache"
            status_source.mkdir()
            status_cache.mkdir()
            filesystem_sync.mirror_tree(status_source, status_cache)
            status_result = filesystem_sync.write_marker(status_cache, {"ok": True}, False)
            if not status_result.get("written"):
                raise AssertionError("generated status marker was not written")
            status_before = autosync.snapshot_roots([status_cache])
            status_path = status_cache / filesystem_sync.AUTO_SYNC_STATUS_NAME
            status_path.write_text("user edited status", encoding="utf-8")
            status_conflict = filesystem_sync.write_marker(status_cache, {"ok": True}, False)
            if not status_conflict.get("conflict") or status_path.read_text(encoding="utf-8") != "user edited status":
                raise AssertionError("status marker user edit was overwritten")
            status_after = autosync.snapshot_roots([status_cache])
            status_events = autosync.queue_vault_changes(
                status_before,
                status_after,
                False,
                cache_vault=status_cache,
                generated_hashes=autosync.managed_sync_hashes(status_cache),
            )
            if len(status_events) != 1 or not status_events[0].get("queued"):
                raise AssertionError("status marker user edit was suppressed by filename")
            try:
                server.validated_obsidian_watch_paths(
                    [str(temp / f"watch-{index}") for index in range(server.MAX_OBSIDIAN_WATCH_PATHS + 1)]
                )
            except ValueError:
                pass
            else:
                raise AssertionError("watch_paths count limit was not enforced")

            oversized_zip = temp / "oversized.zip"
            with zipfile.ZipFile(oversized_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("oversized.md", b"x" * (server.MAX_OBSIDIAN_IMPORT_FILE_BYTES + 1))
            try:
                server.load_obsidian_files(oversized_zip)
            except ValueError:
                pass
            else:
                raise AssertionError("zip single-member decompression limit was not enforced")
            too_many_zip = temp / "too-many.zip"
            with zipfile.ZipFile(too_many_zip, "w", compression=zipfile.ZIP_STORED) as archive:
                for index in range(server.MAX_OBSIDIAN_IMPORT_FILES + 1):
                    archive.writestr(f"note-{index}.md", b"x")
            try:
                server.load_obsidian_files(too_many_zip)
            except ValueError:
                pass
            else:
                raise AssertionError("zip member-count limit was not enforced")
            excessive_total_zip = temp / "excessive-total.zip"
            with zipfile.ZipFile(excessive_total_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for index in range(5):
                    archive.writestr(f"large-{index}.md", b"x" * server.MAX_OBSIDIAN_IMPORT_FILE_BYTES)
            try:
                server.load_obsidian_files(excessive_total_zip)
            except ValueError:
                pass
            else:
                raise AssertionError("zip total decompression limit was not enforced")

            server.save_issued_keys([{"key_id": "test-key", "revoked_at": "", "permanent": True, "expires_at": ""}])
            server.remember_pending_key_download(
                {"key_id": "test-key", "role": "read", "filename": "test.shiguan-key", "key_text": "fixture"}
            )
            current_keys = server.issued_keys()
            key_download = server.pending_downloads(current_keys)[0]
            try:
                server.download_pending_key("test-key", "wrong-nonce", current_keys)
            except PermissionError:
                pass
            else:
                raise AssertionError("key export accepted an invalid download nonce")
            server.download_pending_key("test-key", str(key_download.get("download_nonce") or ""), current_keys)
            try:
                server.download_pending_key("test-key", str(key_download.get("download_nonce") or ""), current_keys)
            except ValueError:
                pass
            else:
                raise AssertionError("key export download nonce was reusable")

            with server.PENDING_KEY_DOWNLOADS_LOCK:
                server.PENDING_KEY_DOWNLOADS.clear()
            server.save_issued_keys([])
            server.save_imported_peers([])
            with ThreadPoolExecutor(max_workers=8) as executor:
                key_results = list(
                    executor.map(
                        server.export_peer_key,
                        [{"role": "read", "days": 7, "note": f"concurrency-{index}"} for index in range(16)],
                    )
                )
            if any(
                not isinstance(item.get("transaction"), dict)
                or int(item["transaction"].get("revision") or 0) < 1
                for item in key_results
            ):
                raise AssertionError("peer-key issuance omitted canonical transaction metadata")
            issued = server.issued_keys()
            issued_ids = {str(item.get("key_id") or "") for item in issued}
            if len(issued) != 16 or len(issued_ids) != 16:
                raise AssertionError(f"concurrent peer-key issuance lost updates: {len(issued)} / {len(issued_ids)}")
            with server.PENDING_KEY_DOWNLOADS_LOCK:
                pending_ids = set(server.PENDING_KEY_DOWNLOADS)
            if pending_ids != issued_ids:
                raise AssertionError("concurrent peer-key issuance lost in-memory download credentials")
            with ThreadPoolExecutor(max_workers=8) as executor:
                renew_results = list(
                    executor.map(
                        server.manage_key,
                        [
                            {"action": "renew", "key_id": str(item.get("key_id") or ""), "days": 30 + index}
                            for index, item in enumerate(key_results)
                        ],
                    )
                )
            if any(not isinstance(item.get("transaction"), dict) for item in renew_results):
                raise AssertionError("peer-key renewal omitted transaction metadata")
            renewed = server.issued_keys()
            if len(renewed) != 16 or any(not item.get("updated_at") for item in renewed):
                raise AssertionError("concurrent peer-key renewal lost an update")
            with ThreadPoolExecutor(max_workers=8) as executor:
                import_results = list(
                    executor.map(server.import_peer_key, [{"key_text": item["key_text"]} for item in key_results])
                )
            if any(
                not isinstance(item.get("transaction"), dict) or "token" in item
                for item in import_results
            ):
                raise AssertionError("peer import transaction/public projection drifted")
            imported = server.imported_peers()
            if len(imported) != 16 or len({str(item.get("peer_id") or "") for item in imported}) != 16:
                raise AssertionError("concurrent peer-key import lost an update")
            first_key_id = str(key_results[0].get("key_id") or "")
            first_peer = next(item for item in imported if str(item.get("key_id") or "") == first_key_id)
            expired = server.expire_key({"key_id": first_key_id, "peer_id": str(first_peer.get("peer_id") or "")})
            if expired.get("changed") != 2 or not isinstance(expired.get("transaction"), dict):
                raise AssertionError("dual-domain expire did not use one canonical transaction")
            peer_snapshot = server.peer_state_snapshot()
            if (
                not server.peer_state_path().is_file()
                or int(peer_snapshot.get("revision") or 0)
                != int(expired.get("transaction", {}).get("revision") or -1)
                or "token" in server.public_peer(server.imported_peers(peer_snapshot)[0])
                or "token_hash" in server.public_issued_key(
                    server.issued_keys(peer_snapshot)[0],
                    server.issued_keys(peer_snapshot),
                )
            ):
                raise AssertionError("canonical peer-state projection or revision drifted")

            config_updates = [
                {"import_query": "phase-b-query"},
                {"output_folder": "Phase B Output"},
                {"autosync_interval_seconds": 37},
            ]
            with ThreadPoolExecutor(max_workers=3) as executor:
                list(executor.map(server.save_obsidian_sync_config, config_updates))
            final_config = server.obsidian_sync_config(include_secret=False)
            if (
                final_config.get("import_query") != "phase-b-query"
                or final_config.get("output_folder") != "Phase B Output"
                or final_config.get("autosync_interval_seconds") != 37
            ):
                raise AssertionError("concurrent Obsidian config updates lost disjoint fields")

            pending_root = server.import_pending_root()
            pending_root.mkdir(parents=True, exist_ok=True)
            unknown_pending = pending_root / "unknown-sidecar-fixture.json"
            unknown_pending.write_text(
                json.dumps({"id": "unknown-sidecar-fixture", "text": "fixture-private-body"}),
                encoding="utf-8",
            )
            malicious_pending = pending_root / "malicious-sidecar-fixture.json"
            malicious_pending.write_text("opaque-body", encoding="utf-8")
            server.pending_import_metadata_path(malicious_pending).write_text(
                json.dumps({"id": "malicious-sidecar-fixture", "content": "SIDE-CAR-SECRET"}),
                encoding="utf-8",
            )
            oversized_pending = pending_root / "oversized-sidecar-fixture.json"
            oversized_pending.write_text("opaque-body", encoding="utf-8")
            server.pending_import_metadata_path(oversized_pending).write_bytes(
                b"{" + b" " * server.PENDING_IMPORT_METADATA_MAX_BYTES + b"}"
            )
            unknown_summary = server.import_queue_summary(limit=2)
            if (
                unknown_summary.get("estimated_tokens") is not None
                or unknown_summary.get("estimated_tokens_status") not in {"unknown", "partial"}
                or int(unknown_summary.get("unknown_metadata_count") or 0) < 3
                or int(unknown_summary.get("unknown_estimated_tokens_count") or 0) < 3
                or "0 tokens" in str(unknown_summary.get("startup_message") or "")
                or "SIDE-CAR-SECRET" in json.dumps(unknown_summary, ensure_ascii=False)
            ):
                raise AssertionError("invalid pending sidecars escaped metadata-only queue semantics")
            for pending in (unknown_pending, malicious_pending, oversized_pending):
                pending.unlink()
                metadata = server.pending_import_metadata_path(pending)
                if metadata.exists():
                    metadata.unlink()

            api_text = (root / "web" / "shiguan-tree" / "api.js").read_text(encoding="utf-8")
            if "localStorage" in api_text or "sessionStorage" not in api_text or "history.replaceState" not in api_text:
                raise AssertionError("admin token browser storage migration is incomplete")
    finally:
        if previous_root is None:
            os.environ.pop("COURT_SHARED_SHIGUAN_ROOT", None)
        else:
            os.environ["COURT_SHARED_SHIGUAN_ROOT"] = previous_root
        if previous_presence is None:
            os.environ.pop("COURT_DISABLE_AGENT_PRESENCE", None)
        else:
            os.environ["COURT_DISABLE_AGENT_PRESENCE"] = previous_presence
        if previous_remote_obsidian is None:
            os.environ.pop("SHIGUAN_ALLOW_REMOTE_OBSIDIAN_ENDPOINT", None)
        else:
            os.environ["SHIGUAN_ALLOW_REMOTE_OBSIDIAN_ENDPOINT"] = previous_remote_obsidian
    return {
        "public_projection": True,
        "web_state_transaction_lock": True,
        "peer_state_single_commit": True,
        "peer_state_same_revision_snapshot": True,
        "web_get_identity_read_only": True,
        "pending_key_download_thread_lock": True,
        "pending_unknown_estimate_semantics": True,
        "export_unknown_nonempty_rejected": True,
        "export_managed_directory_accepted": True,
        "import_pending_only": True,
        "import_metadata_sidecar": True,
        "autosync_managed_output_recovery": True,
        "autosync_metadata_sidecar": True,
        "autosync_stale_pid_not_reused": True,
        "autosync_user_edit_conflict_preserved": True,
        "autosync_generated_json_refresh": True,
        "autosync_first_run_provenance": True,
        "autosync_legacy_cache_bootstrap": True,
        "autosync_legacy_manifest_migration": True,
        "autosync_cycle_lock": True,
        "filesystem_sync_lock": True,
        "filesystem_sync_staged_race_guard": True,
        "preserve_cache_wholesale_export_rejected": True,
        "obsidian_boundaries": True,
        "key_download_nonce": True,
        "browser_token_session_only": True,
        "loopback_bind_defaults": True,
        "peer_endpoint_policy": True,
        "obsidian_webui_status_and_actions": True,
        "obsidian_mode_contract": True,
        "autosync_config_lock_full_cycle": True,
        "autosync_health_phase_contract": True,
        "autosync_once_receipt_not_daemon_health": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--lan-url", default="")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    results: dict[str, object] = {"static": run_static_regressions()}
    if args.static_only:
        print(json.dumps({"ok": True, "results": results}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    try:
        status, health, headers = fetch_json(f"{base}/api/health", args.timeout)
        assert status == 200
        assert_public_health(health)
        assert_security_headers(headers)
        results["health_projection_ok"] = True

        status, private_health, _headers = fetch_json(f"{base}/api/health/private", args.timeout)
        results["local_private_health_ok"] = bool(
            status == 200
            and private_health.get("service") == "shiguan-tree"
            and private_health.get("shared_shiguan_root")
        )

        status, state, headers = fetch_json(f"{base}/api/state?limit=1&ui_collapsed=1", args.timeout)
        results["local_state_status"] = status
        results["local_state_ok"] = status == 200 and "entries" in state
        assert_security_headers(headers)

        status, _body, _headers = fetch_json(
            f"{base}/api/security-check",
            args.timeout,
            method="POST",
            headers={"Content-Type": "application/json"},
            payload={},
        )
        results["missing_admin_request_header_rejected"] = status == 403

        status, _body, _headers = fetch_json(
            f"{base}/api/security-check",
            args.timeout,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Shiguan-Admin-Request": "1",
                "Origin": "https://evil.invalid",
            },
            payload={},
        )
        results["evil_origin_rejected"] = status == 403

        status, _body, _headers = fetch_json(
            f"{base}/api/security-check",
            args.timeout,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Shiguan-Admin-Request": "1",
                "Origin": base,
            },
            payload={},
        )
        results["same_origin_write_gate_ok"] = status == 200

        status, _body, _headers = fetch_json(
            f"{base}/api/security-check",
            args.timeout,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Shiguan-Admin-Request": "1",
                "Origin": "http://evil.invalid:8765",
                "Host": "evil.invalid:8765",
            },
            payload={},
        )
        results["dns_rebinding_host_rejected"] = status == 403
    except (AssertionError, URLError, TimeoutError, OSError) as exc:
        results["local_error"] = str(exc)

    if args.lan_url:
        lan = args.lan_url.rstrip("/")
        try:
            status, public_state, headers = fetch_json(f"{lan}/api/state?limit=1&ui_collapsed=1", args.timeout)
            assert status == 200
            assert_public_state(public_state)
            assert_security_headers(headers)
            results["lan_public_state_projection_ok"] = True

            status, public_health, _headers = fetch_json(f"{lan}/api/health", args.timeout)
            assert status == 200
            assert_public_health(public_health)
            results["lan_public_health_projection_ok"] = True

            status, _body, _headers = fetch_json(f"{lan}/api/health/private", args.timeout)
            results["lan_private_health_without_token_rejected"] = status == 403

            status, _body, _headers = fetch_json(f"{lan}/api/keys", args.timeout)
            results["lan_admin_get_without_token_rejected"] = status == 403

            status, _body, _headers = fetch_json(
                f"{lan}/api/security-check",
                args.timeout,
                method="POST",
                headers={"Content-Type": "application/json", "X-Shiguan-Admin-Request": "1"},
                payload={},
            )
            results["lan_admin_write_without_token_rejected"] = status == 403
        except (AssertionError, URLError, TimeoutError, OSError) as exc:
            results["lan_error"] = str(exc)
    else:
        results["lan_checks"] = "not_requested"

    required = [
        "health_projection_ok",
        "local_private_health_ok",
        "local_state_ok",
        "missing_admin_request_header_rejected",
        "evil_origin_rejected",
        "same_origin_write_gate_ok",
        "dns_rebinding_host_rejected",
    ]
    if args.lan_url:
        required.extend(
            [
                "lan_public_state_projection_ok",
                "lan_public_health_projection_ok",
                "lan_private_health_without_token_rejected",
                "lan_admin_get_without_token_rejected",
                "lan_admin_write_without_token_rejected",
            ]
        )
    ok = all(results.get(name) is True for name in required)
    print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
