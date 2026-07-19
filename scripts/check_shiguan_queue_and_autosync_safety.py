"""Isolated regressions for Shiguan seen-ledger and autosync health truth.

The checks use a temporary shared root and monkeypatched process evidence.  They
do not inspect the host pending queue and do not start or stop real daemons.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
import tempfile
from unittest import mock


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import ensure_shiguan_autosync as autosync  # noqa: E402
import ensure_obsidian_shared_vault as obsidian  # noqa: E402
import check_shiguan_import_queue as import_queue  # noqa: E402
import migrate_shared_shiguan as migration  # noqa: E402
import plan_shiguan_pending_quarantine as quarantine_plan  # noqa: E402
import shiguan_autosync_daemon as autosync_daemon  # noqa: E402
import shiguan_paths  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_seen_ledger_concurrency() -> dict[str, object]:
    worker = """
import os
import sys
sys.path.insert(0, os.environ['COURT_TEST_SCRIPTS'])
import check_shiguan_import_queue as queue
queue.queue_summary = lambda limit: {'_pending_ids': [os.environ['COURT_TEST_SEEN_ID']]}
sys.argv = ['check_shiguan_import_queue.py', '--format', 'json', '--mark-seen']
raise SystemExit(queue.main())
""".strip()
    expected = {f"concurrent-{index:02d}" for index in range(32)}
    with tempfile.TemporaryDirectory(prefix="court-seen-ledger-") as raw_temp:
        root = Path(raw_temp)
        processes: list[subprocess.Popen[str]] = []
        for seen_id in sorted(expected):
            env = os.environ.copy()
            env.update(
                {
                    "COURT_SHARED_SHIGUAN_ROOT": str(root),
                    "COURT_DISABLE_AGENT_PRESENCE": "1",
                    "COURT_TEST_SCRIPTS": str(SCRIPTS),
                    "COURT_TEST_SEEN_ID": seen_id,
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-c", worker],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        failures: list[str] = []
        for process in processes:
            _, stderr = process.communicate(timeout=30)
            if process.returncode != 0:
                failures.append(stderr[-1000:])
        require(not failures, f"concurrent --mark-seen workers failed: {failures[:3]}")
        ledger = root / "references" / "shiguan-imports" / "startup-seen.json"
        payload = json.loads(ledger.read_text(encoding="utf-8"))
        actual = {str(item) for item in payload.get("seen_ids", [])}
        require(actual == expected, f"seen ledger lost updates: missing={sorted(expected - actual)}")
        lock_path = root / "references" / "court-runtime" / "shiguan-import-seen.lock"
        require(lock_path.is_file(), "shared seen-ledger lock was not created in the isolated root")
        return {"workers": len(processes), "seen_ids": len(actual), "lock_exists": True}


def check_invalid_sidecar_truth() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="court-invalid-sidecar-") as raw_temp:
        root = Path(raw_temp)
        pending = root / "references" / "shiguan-imports" / "pending"
        pending.mkdir(parents=True)
        bodies = [
            pending / "extra-key.json",
            pending / "oversized.json",
            pending / "contract-drift.json",
        ]
        for body in bodies:
            body.write_bytes(b"opaque-pending-body-never-opened")
        (pending / "extra-key.metadata.json").write_text(
            json.dumps({"id": "extra-key", "content": "must-not-leak"}),
            encoding="utf-8",
        )
        (pending / "oversized.metadata.json").write_bytes(
            b"{" + b" " * import_queue.MAX_SIDECAR_BYTES + b"}"
        )
        (pending / "contract-drift.metadata.json").write_text(
            json.dumps(
                {
                    "id": "contract-drift",
                    "filename": "README.md",
                    "source_type": "md",
                    "status": "pending",
                    "imported_at": "2026-07-19T12:00:00",
                    "char_count": 10,
                    "estimated_tokens": 4,
                    "sha256": "0" * 64,
                    "suggested_processor": "codex",
                }
            ),
            encoding="utf-8",
        )
        original_read_text = Path.read_text
        original_open = Path.open

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path.resolve() in {body.resolve() for body in bodies}:
                raise AssertionError(f"pending body was opened: {path}")
            return original_read_text(path, *args, **kwargs)

        def guarded_open(path: Path, *args: object, **kwargs: object):
            if path.resolve() in {body.resolve() for body in bodies}:
                raise AssertionError(f"pending body was opened: {path}")
            return original_open(path, *args, **kwargs)

        with (
            mock.patch.dict(os.environ, {"COURT_SHARED_SHIGUAN_ROOT": str(root)}),
            mock.patch.object(Path, "read_text", guarded_read_text),
            mock.patch.object(Path, "open", guarded_open),
        ):
            summary = import_queue.queue_summary(8)
        serialized = json.dumps(summary, ensure_ascii=False)
        require(summary.get("unknown_metadata_count") == 3, "invalid sidecars were counted as valid metadata")
        require(summary.get("unknown_estimated_tokens_count") == 3, "missing token metrics were undercounted")
        require("must-not-leak" not in serialized, "unknown sidecar field leaked into queue output")
        require("3 份缺少可用 estimated_tokens" in str(summary.get("startup_message")), "unknown metric message drifted")
        return {"invalid_sidecars": 3, "pending_body_reads": 0, "unknown_tokens": 3}


def fresh_status(pid: int, interval: int = 20) -> dict[str, object]:
    return {
        "ok": True,
        "mode": "daemon",
        "pid": pid,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "interval_seconds": interval,
    }


def check_autosync_health_truth() -> dict[str, object]:
    require(autosync.process_query_gone(87), "gone")
    require(not autosync.process_query_gone(5), "access")
    exact = f'"{sys.executable}" "{autosync.daemon_script()}" --interval 20'
    wrong = autosync.daemon_script().with_name("not-the-daemon.py")
    require(autosync.command_line_runs_daemon(exact), "exact canonical daemon path was not recognized")
    require(
        not autosync.command_line_runs_daemon(f'"{sys.executable}" "{wrong}" --interval 20'),
        "different script path was accepted as the daemon",
    )
    require(
        not autosync.command_line_runs_daemon(f'"{sys.executable}" "{autosync.daemon_script()}.bak"'),
        "daemon-path prefix/suffix lookalike was accepted",
    )
    require(
        autosync.status_is_fresh({"updated_at": datetime.now().astimezone().isoformat()}, 20),
        "timezone-aware daemon timestamp was rejected",
    )
    require(
        not autosync.command_line_runs_daemon(
            f'"{sys.executable}" "{wrong}" --decoy "{autosync.daemon_script()}"'
        ),
        "daemon path in a decoy argument was accepted as the executed script",
    )
    alternate = autosync.daemon_script().parents[2] / ".codex-fixture" / "scripts" / autosync.daemon_script().name
    with mock.patch.object(
        autosync,
        "trusted_daemon_script_paths",
        return_value={
            autosync.normalized_process_path(autosync.daemon_script()),
            autosync.normalized_process_path(alternate),
        },
    ):
        require(
            autosync.command_line_runs_daemon(f'"{sys.executable}" "{alternate}" --interval 20'),
            "trusted alternate active-copy daemon path was not recognized",
        )

    with tempfile.TemporaryDirectory(prefix="court-autosync-health-") as raw_temp:
        isolated_lock = Path(raw_temp) / "obsidian-autosync-ensure.lock"
        isolated_env = {"COURT_SHARED_SHIGUAN_ROOT": str(Path(raw_temp) / "court-data")}
        with (
            mock.patch.object(autosync, "ensure_lock_path", return_value=isolated_lock),
            mock.patch.dict(os.environ, isolated_env),
            mock.patch.object(autosync, "read_json", return_value=fresh_status(101)),
            mock.patch.object(autosync, "pid_alive", side_effect=lambda pid: pid == 101),
            mock.patch.object(autosync, "find_running_daemon_pid", return_value=101),
        ):
            reused = autosync.ensure(20, check_only=False)
        require(reused.get("status") == "REUSED", "fresh same-PID exact process was not reused")

        stale = {"pid": 202, "updated_at": "2000-01-01T00:00:00", "interval_seconds": 20}
        with (
            mock.patch.object(autosync, "ensure_lock_path", return_value=isolated_lock),
            mock.patch.dict(os.environ, isolated_env),
            mock.patch.object(autosync, "read_json", return_value=stale),
            mock.patch.object(autosync, "pid_alive", side_effect=lambda pid: pid == 202),
            mock.patch.object(autosync, "find_running_daemon_pid", return_value=202),
            mock.patch.object(autosync, "ensure_shared_seed", side_effect=AssertionError("must not start second daemon")),
            mock.patch.object(autosync, "start_daemon", side_effect=AssertionError("must not start second daemon")),
        ):
            unhealthy = autosync.ensure(20, check_only=False)
        require(unhealthy.get("status") == "RUNNING_UNHEALTHY", "stale running daemon was falsely reused")
        require("status_stale_or_missing" in str(unhealthy.get("reason")), "stale reason was not preserved")

        with (
            mock.patch.dict(os.environ, isolated_env),
            mock.patch.object(autosync, "read_json", return_value=stale),
            mock.patch.object(autosync, "pid_alive", side_effect=lambda pid: pid == 202),
            mock.patch.object(autosync, "find_running_daemon_pid", return_value=202),
        ):
            read_only_unhealthy = autosync.ensure(20, check_only=True)
        require(
            read_only_unhealthy.get("status") == "RUNNING_UNHEALTHY",
            "read-only audit hid a stale but still-running daemon",
        )
        require(
            "status_stale_or_missing" in str(read_only_unhealthy.get("reason")),
            "read-only stale-process reason was not preserved",
        )

        with (
            mock.patch.object(autosync, "ensure_lock_path", return_value=isolated_lock),
            mock.patch.dict(os.environ, isolated_env),
            mock.patch.object(autosync, "read_json", return_value=fresh_status(303)),
            mock.patch.object(autosync, "pid_alive", return_value=True),
            mock.patch.object(
                autosync,
                "find_running_daemon_pid",
                return_value=autosync.PROCESS_DISCOVERY_MULTIPLE,
            ),
            mock.patch.object(autosync, "start_daemon", side_effect=AssertionError("must not start with duplicates")),
        ):
            multiple = autosync.ensure(20, check_only=False)
        require(multiple.get("status") == "RUNNING_UNHEALTHY", "duplicate daemons were not rejected")

        with (
            mock.patch.object(autosync, "ensure_lock_path", return_value=isolated_lock),
            mock.patch.dict(os.environ, isolated_env),
            mock.patch.object(autosync, "read_json", return_value=stale),
            mock.patch.object(autosync, "pid_alive", return_value=True),
            mock.patch.object(autosync, "find_running_daemon_pid", return_value=0),
            mock.patch.object(autosync, "ensure_shared_seed"),
            mock.patch.object(autosync, "start_daemon", return_value=404),
            mock.patch.object(autosync, "write_json"),
        ):
            started = autosync.ensure(20, check_only=False)
        require(started.get("status") == "STARTED" and started.get("pid") == 404, "clean absence did not start one daemon")

    with tempfile.TemporaryDirectory(prefix="court-autosync-read-only-") as raw_temp:
        isolated_root = Path(raw_temp) / "court-data"
        with (
            mock.patch.dict(os.environ, {"COURT_SHARED_SHIGUAN_ROOT": str(isolated_root)}),
            mock.patch.object(autosync, "find_running_daemon_pid", return_value=0),
        ):
            read_only = autosync.ensure(20, check_only=True)
        require(read_only.get("status") == "NOT_RUNNING", "blank read-only audit returned an unexpected state")
        require(not isolated_root.exists(), "--check-only created shared-root or lock state")

    malformed = {
        "ok": True,
        "mode": "daemon",
        "pid": "not-an-int",
        "interval_seconds": "not-an-int",
        "updated_at": "not-a-time",
    }
    with (
        mock.patch.dict(os.environ, isolated_env),
        mock.patch.object(autosync, "read_json", return_value=malformed),
        mock.patch.object(autosync, "find_running_daemon_pid", return_value=0),
    ):
        malformed_report = autosync.ensure(20, check_only=True)
    require(malformed_report.get("status") == "NOT_RUNNING", "malformed status crashed or became healthy")

    return {
        "exact_path_match": True,
        "fresh_same_pid": reused.get("status"),
        "stale_exact_process": unhealthy.get("status"),
        "stale_exact_process_check_only": read_only_unhealthy.get("status"),
        "multiple_exact_processes": multiple.get("status"),
        "clean_absence": started.get("status"),
        "blank_check_only_no_write": True,
        "malformed_status_fail_closed": True,
    }


def check_install_path_convergence() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="decretum-obsidian-paths-") as raw_temp:
        fixture = Path(raw_temp)
        home = fixture / "home"
        data_base = fixture / "localappdata"
        canonical = home / ".agents" / "court-shiguan" / "decretum-matrix"
        require(
            shiguan_paths.default_shared_root(home)
            == Path(os.path.abspath(str(canonical))),
            "default shared root still uses the legacy product locator",
        )
        require(
            shiguan_paths.DEFAULT_PROTECTED_ROOT
            == (Path.home() / ".agents" / "skills" / "decretum-matrix" / "references").resolve(),
            "protected skill root still uses the legacy locator",
        )
        (canonical / "references").mkdir(parents=True)
        require(
            shiguan_paths._active_shared_root(
                canonical,
                shiguan_paths.default_legacy_shared_root(data_base),
            )
            == canonical,
            "renamed target-only shared root is not selectable",
        )

        upgrade_home = fixture / "upgrade-home"
        upgrade_data = fixture / "upgrade-localappdata"
        upgrade_target = shiguan_paths.default_shared_root(upgrade_home)
        prior = shiguan_paths.default_previous_shared_root(upgrade_home)
        localappdata = shiguan_paths.default_legacy_shared_root(upgrade_data)
        prior_refs = prior / "references"
        localappdata_refs = localappdata / "references"
        prior_refs.mkdir(parents=True)
        selected = shiguan_paths.default_migration_source_root(upgrade_home, upgrade_data)
        require(
            selected == prior and shiguan_paths._active_shared_root(upgrade_target, selected) == prior,
            "published .agents root was not kept active",
        )
        target_refs = upgrade_target / "references"
        with (
            mock.patch.object(migration, "default_migration_source_root", return_value=prior),
            mock.patch.object(migration, "default_shared_root", return_value=upgrade_target),
        ):
            plan = migration.migration_plan()
        require(
            (plan["source_root"], plan["target_root"]) == (str(prior_refs), str(target_refs)),
            "default migration plan ignored selector",
        )
        original_kind = shiguan_paths._path_kind

        def select_with(kinds: dict[Path, str], targets: dict[Path, Path]) -> object:
            with (
                mock.patch.object(shiguan_paths, "_path_kind", side_effect=lambda p: kinds.get(Path(p)) or original_kind(Path(p))),
                mock.patch.object(shiguan_paths, "_resolved_junction_target", side_effect=lambda p: targets.get(Path(p)) or Path(p).resolve(strict=True)),
            ):
                try:
                    return shiguan_paths.default_migration_source_root(upgrade_home, upgrade_data)
                except RuntimeError as exc:
                    return str(exc)

        require(
            select_with({localappdata_refs: "junction"}, {localappdata_refs: prior_refs}) == prior,
            "exact alias counted as physical",
        )
        target_refs.mkdir(parents=True)
        junctions = {prior_refs: "junction", localappdata_refs: "junction"}
        require(select_with(junctions, dict.fromkeys(junctions, target_refs)) == prior, "exact aliases blocked")
        single = {prior_refs: "absent", localappdata_refs: "junction"}
        require(select_with(single, {localappdata_refs: target_refs}) == localappdata, "exact single alias blocked")
        for kind in ("unknown", "other", "symlink", "reparse"):
            require(
                select_with({prior_refs: kind}, {}) == "transitional_shiguan_legacy_root_untrusted",
                f"untrusted {kind} accepted",
            )
        require(
            select_with(single, {localappdata_refs: fixture / "wrong-target"})
            == "transitional_shiguan_multiple_legacy_roots",
            "mismatched junction accepted",
        )
        localappdata_refs.mkdir(parents=True)
        require(
            select_with({}, {}) == "transitional_shiguan_multiple_legacy_roots",
            "two physical roots accepted",
        )
        with (
            mock.patch.object(autosync.Path, "home", return_value=home),
            mock.patch.object(autosync, "user_data_base", return_value=data_base),
        ):
            trusted = autosync.trusted_daemon_script_paths()
        expected_roots = [
            home / root / "skills" / "decretum-matrix"
            for root in (".agents", ".codex", ".claude", ".hermes")
        ] + [data_base / "hermes" / "skills" / "decretum-matrix"]
        expected = {
            autosync.normalized_process_path(root / "scripts" / "shiguan_autosync_daemon.py")
            for root in expected_roots
        }
        require(expected.issubset(trusted), "renamed active roots are absent from daemon discovery")

        refs = canonical / "references"
        source = refs / "shiguan-tree"
        parent = home / "Documents" / "Obsidian Vault"
        cache = parent / "Court Shiguan"
        inbox = source / "Obsidian 回传"
        old_skill = home / ".codex" / "skills" / "court-capability-router"
        canonical_skill = home / ".agents" / "skills" / "decretum-matrix"
        canonical_scripts = canonical_skill / "scripts"
        canonical_scripts.mkdir(parents=True)
        names = {path.name for path in shiguan_paths.RUNTIME_MARKER_PATHS}
        names.update(("sync_shiguan_obsidian_vault.py", "ensure_shiguan_service_daemon.py"))
        for name in names:
            (canonical_scripts / name).write_text("# fixture\n", encoding="utf-8")
        current = {
            "api_key": "must-" + "not-leak",
            "service_daemon_script": str(old_skill / "scripts" / "shiguan_service_daemon.py"),
            "service_ensure_script": str(old_skill / "scripts" / "ensure_shiguan_service_daemon.py"),
        }
        with (
            mock.patch.object(obsidian.Path, "home", return_value=home),
            mock.patch.object(obsidian, "default_obsidian_cache_vault", return_value=cache),
            mock.patch.object(obsidian, "default_obsidian_parent_vault", return_value=parent),
            mock.patch.object(obsidian, "default_obsidian_inbox", return_value=inbox),
            mock.patch.object(obsidian, "references_root", return_value=refs),
        ):
            rebound = obsidian.build_sync_config(source, current)
        for field in ("service_daemon_script", "service_ensure_script"):
            require("court-capability-router" not in str(rebound[field]), f"stale {field}")
        for field in (
            "autosync_script",
            "filesystem_sync_script",
            "service_daemon_script",
            "service_ensure_script",
        ):
            require(
                Path(str(rebound[field])).parent == canonical_scripts,
                f"{field} did not bind the canonical installed runtime root",
            )
        require(Path(str(rebound["shared_shiguan_root"])) == refs, "shared root was not rebound")
        require([Path(str(item)) for item in rebound["watch_paths"]] == [cache, inbox], "watch roots were not rebound")
        public = obsidian.public_config(rebound)
        require("api_key" not in public and public.get("has_api_key") is True, "API key projection drift")
        base = {
            "schema": "court.obsidian.sync_config.v2",
            "revision": 3,
            "transaction_id": "existing-transaction",
            "api_key": "must-" + "not-leak",
        }

        def capture_patch(changes: dict[str, object], **_: object) -> dict[str, object]:
            reserved = {"schema", "revision", "transaction_id", "updated_at"}
            require(not reserved.intersection(changes), "reserved config fields were replayed")
            return {"conflict": False}

        with (
            mock.patch.object(obsidian, "read_config_snapshot", return_value=base),
            mock.patch.object(obsidian, "build_sync_config", return_value=rebound),
            mock.patch.object(obsidian, "patch_config", side_effect=capture_patch),
        ):
            obsidian.update_sync_config(source)
        return {"active_roots": len(expected), "pending_body_reads": 0, "api_key_public": "REDACTED"}


def check_autosync_sidecar_contract() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="court-autosync-sidecar-") as raw_temp:
        root = Path(raw_temp)
        source_root = root / "obsidian"
        source_root.mkdir()
        source = source_root / "README.md"
        body = "fixture pending body\n"
        source.write_text(body, encoding="utf-8")
        pending = root / "pending"
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        with mock.patch.object(autosync_daemon, "pending_root", return_value=pending):
            queued = autosync_daemon.queue_pending_file(
                source,
                source_root,
                source.name,
                digest,
                "fixture",
            )
        sidecar_path = Path(str(queued["metadata_sidecar"]))
        target_path = pending / f"{queued['id']}.json"
        metadata = json.loads(sidecar_path.read_text(encoding="utf-8"))
        errors = quarantine_plan.validate_sidecar(metadata, target_path.name)
        require(not errors, f"autosync sidecar is not governance-valid: {errors}")
        require(metadata.get("filename") == target_path.name, "sidecar filename is not the pending body filename")
        imported_at = datetime.fromisoformat(str(metadata.get("imported_at") or ""))
        require(imported_at.tzinfo is not None, "sidecar imported_at is timezone-naive")
        return {
            "valid": True,
            "filename": metadata["filename"],
            "timezone_aware": True,
            "pending_body_reads": 0,
        }


def main() -> int:
    result = {
        "seen_ledger": check_seen_ledger_concurrency(),
        "invalid_sidecar_truth": check_invalid_sidecar_truth(),
        "autosync_health": check_autosync_health_truth(),
        "install_path_convergence": check_install_path_convergence(),
        "autosync_sidecar_contract": check_autosync_sidecar_contract(),
    }
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
