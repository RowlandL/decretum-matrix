"""Ensure Codex agent recursion defaults for the court router.

This script checks or updates both Codex config layers with a parameterized
thread recommendation. Sixteen is the normal default; an explicit
``--threads N`` remains a current-user count override and is preserved above
sixteen rather than clamped. Actual host capacity/rejection, max depth,
hierarchy, resources, and write-set gates remain authoritative. Blank or
unresolved installs default to V2:

- `[agents].max_depth = 4`
- legacy `[agents].max_threads` is absent while Multi-Agent V2 is enabled
- `[features.multi_agent_v2].enabled = true`
- `[features.multi_agent_v2].max_concurrent_threads_per_session = --threads N`
- `[features.multi_agent_v2].hide_spawn_agent_metadata = true`
- V1 additionally uses `[features].multi_agent = true` and a compatible child
  count, while the V2 table remains present with
  `enabled = false`

Multi-Agent V2 counts the root inside the configured per-session value.

Default mode is a nonblocking check. `--apply --threads N` updates both
`config.toml` and `managed_config.toml` with backups and reread verification.
Apply probes the host CC Switch controller path before either effective file is
written. A supported controller profile is backed up and updated first.
Unknown versions, schemas, locks, or profile payloads remain `REMINDER_ONLY`
and are never guessed or migrated.
Apply never restarts or stops Codex: it reports restart required/deferred and
keeps current tasks running.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
from typing import Callable

sys.dont_write_bytecode = True

from court_file_lock import atomic_write_text, file_lock
from court_multi_agent_protocol import render_protocol_config
from shiguan_paths import reference_path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None  # type: ignore[assignment]


DEFAULT_MAX_DEPTH = 4
ADVISORY_BASELINE_THREADS = 16
DEFAULT_HIGH_PARALLEL_THREADS = 16
DEFAULT_MAX_THREADS = DEFAULT_HIGH_PARALLEL_THREADS
CC_SWITCH_317_PROFILE_COLUMNS = (
    "id",
    "name",
    "payload",
    "sort_order",
    "created_at",
    "updated_at",
)
CC_SWITCH_317_INPUT_TOKEN_TABLES = (
    "proxy_request_logs",
    "usage_daily_rollups",
)
CC_SWITCH_317_INPUT_TOKEN_SEMANTICS_COLUMN = "input_token_semantics"


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured)
    return Path.home() / ".codex"


def default_config_path() -> Path:
    return codex_home() / "config.toml"


def default_managed_config_path() -> Path:
    return codex_home() / "managed_config.toml"


def default_cc_switch_db_path() -> Path:
    configured = os.environ.get("CC_SWITCH_HOME")
    root = Path(configured).expanduser() if configured else Path.home() / ".cc-switch"
    return root / "cc-switch.db"


def find_section(lines: list[str], section_name: str) -> tuple[int | None, int]:
    start: int | None = None
    end = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == f"[{section_name}]":
            start = index
            continue
        if start is not None and index > start and re.match(r"^\[[^\]]+\]\s*$", stripped):
            end = index
            break
    return start, end


def find_agents_section(lines: list[str]) -> tuple[int | None, int]:
    return find_section(lines, "agents")


def read_agent_settings(text: str) -> tuple[int | None, int | None, bool]:
    lines = text.splitlines()
    start, end = find_agents_section(lines)
    if start is None:
        return None, None, False
    section = "\n".join(lines[start + 1 : end])
    depth_match = re.search(r"(?m)^\s*max_depth\s*=\s*(\d+)\s*$", section)
    threads_match = re.search(r"(?m)^\s*max_threads\s*=\s*(\d+)\s*$", section)
    depth = int(depth_match.group(1)) if depth_match else None
    threads = int(threads_match.group(1)) if threads_match else None
    return depth, threads, True


def read_config_settings(text: str) -> dict[str, object]:
    result: dict[str, object] = {
        "agents_section": False,
        "max_depth": None,
        "max_threads": None,
        "legacy_max_threads": None,
        "v2_max_concurrent_threads_per_session": None,
        "effective_child_thread_limit": None,
        "config_conflict": False,
        "selected_protocol": None,
        "multi_agent_enabled": None,
        "multi_agent_v2_present": False,
        "multi_agent_v2_enabled": False,
        "multi_agent_v2_disabled": False,
        "spawn_agent_metadata_visible": False,
        "spawn_agent_metadata_hidden": False,
        "reserved_spawn_schema_compatible": False,
        "inactive_v2_config_preserved": False,
    }
    if not text.strip() or tomllib is None:
        return result
    data = tomllib.loads(text)
    agents = data.get("agents")
    if isinstance(agents, dict):
        result["agents_section"] = True
        result["max_depth"] = agents.get("max_depth")
        result["legacy_max_threads"] = agents.get("max_threads")
    features = data.get("features")
    if isinstance(features, dict):
        result["multi_agent_enabled"] = features.get("multi_agent")
    multi_agent = features.get("multi_agent_v2") if isinstance(features, dict) else None
    if isinstance(multi_agent, dict):
        result["multi_agent_v2_present"] = True
        result["multi_agent_v2_enabled"] = multi_agent.get("enabled") is True
        result["multi_agent_v2_disabled"] = multi_agent.get("enabled") is False
        result["spawn_agent_metadata_visible"] = multi_agent.get("hide_spawn_agent_metadata") is False
        result["spawn_agent_metadata_hidden"] = multi_agent.get("hide_spawn_agent_metadata") is True
        v2_threads = multi_agent.get("max_concurrent_threads_per_session")
        result["v2_max_concurrent_threads_per_session"] = v2_threads
        result["inactive_v2_config_preserved"] = bool(
            multi_agent.get("enabled") is False
            and isinstance(v2_threads, int)
            and not isinstance(v2_threads, bool)
            and v2_threads >= 2
            and multi_agent.get("hide_spawn_agent_metadata") is True
        )
    if result["multi_agent_v2_enabled"]:
        result["selected_protocol"] = "v2"
        v2_threads = result["v2_max_concurrent_threads_per_session"]
        if isinstance(v2_threads, int) and not isinstance(v2_threads, bool):
            result["max_threads"] = v2_threads
            result["effective_child_thread_limit"] = max(v2_threads - 1, 0)
    elif (
        result["multi_agent_v2_present"]
        and result["multi_agent_v2_disabled"]
        and result["multi_agent_enabled"] is True
        and isinstance(result["legacy_max_threads"], int)
        and not isinstance(result["legacy_max_threads"], bool)
    ):
        result["selected_protocol"] = "v1"
        result["max_threads"] = result["legacy_max_threads"]
        result["effective_child_thread_limit"] = result["legacy_max_threads"]
    result["config_conflict"] = bool(
        result["multi_agent_v2_enabled"] and result["legacy_max_threads"] is not None
    )
    result["reserved_spawn_schema_compatible"] = bool(
        result["multi_agent_v2_enabled"] and result["spawn_agent_metadata_hidden"]
    )
    return result


def update_setting(lines: list[str], start: int, end: int, key: str, value: int) -> bool:
    pattern = re.compile(rf"^(\s*){re.escape(key)}\s*=.*$")
    for index in range(start + 1, end):
        match = pattern.match(lines[index])
        if match:
            lines[index] = f"{match.group(1)}{key} = {value}"
            return True
    lines.insert(end, f"{key} = {value}")
    return False


def update_bool_setting(lines: list[str], start: int, end: int, key: str, value: bool) -> bool:
    pattern = re.compile(rf"^(\s*){re.escape(key)}\s*=.*$")
    rendered = "true" if value else "false"
    for index in range(start + 1, end):
        match = pattern.match(lines[index])
        if match:
            lines[index] = f"{match.group(1)}{key} = {rendered}"
            return True
    lines.insert(end, f"{key} = {rendered}")
    return False


def remove_setting(lines: list[str], start: int, end: int, key: str) -> bool:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=.*$")
    removed = False
    for index in range(end - 1, start, -1):
        if pattern.match(lines[index]):
            lines.pop(index)
            removed = True
    return removed


def remove_legacy_feature_scalar(lines: list[str]) -> None:
    start, end = find_section(lines, "features")
    if start is None:
        return
    pattern = re.compile(r"^\s*multi_agent_v2\s*=.*$")
    for index in range(end - 1, start, -1):
        if pattern.match(lines[index]):
            lines.pop(index)


def desired_text(original: str, max_depth: int, max_threads: int, *, protocol: str = "auto") -> str:
    if protocol not in {"auto", "v1", "v2"}:
        raise ValueError(f"unsupported protocol target: {protocol}")
    selected = protocol
    if selected == "auto":
        current = read_config_settings(original).get("selected_protocol")
        selected = str(current) if current in {"v1", "v2"} else "v2"
    return render_protocol_config(
        original,
        selected,  # type: ignore[arg-type]
        max_depth=max_depth,
        total_threads=max_threads,
    )


def default_backup_root() -> Path:
    return reference_path("host-capability-backups", "codex-agent-config")


def backup_path(path: Path, *, backup_root: Path | None = None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    root = (backup_root or default_backup_root()).expanduser().resolve()
    return root / f"{path.name}.court-agent-config-{stamp}.bak"


def create_immutable_backup(path: Path, *, backup_root: Path | None = None) -> Path:
    """Create a byte-for-byte, exclusive, read-only backup in shared Shiguan."""

    candidate = backup_path(path, backup_root=backup_root)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    payload = path.read_bytes()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(candidate, flags, stat.S_IREAD)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if candidate.read_bytes() != payload:
            raise OSError("immutable backup verification failed")
        shutil.copystat(path, candidate, follow_symlinks=True)
        candidate.chmod(stat.S_IREAD)
    except Exception:
        try:
            candidate.chmod(stat.S_IREAD)
        except OSError:
            pass
        raise
    return candidate


def write_config_update(
    path: Path,
    expected_original: bytes,
    updated: str,
    *,
    backup_root: Path | None = None,
) -> Path | None:
    """CAS-protect, back up, atomically replace, and verify one config layer."""

    lock_path = reference_path("court-runtime", "locks", "codex-agent-config", f"{path.name}.lock")
    with file_lock(lock_path):
        current = path.read_bytes() if path.exists() else b""
        if current != expected_original:
            raise RuntimeError(f"config changed since read: {path}")
        backup = create_immutable_backup(path, backup_root=backup_root) if path.exists() else None
        atomic_write_text(path, updated)
        if path.read_bytes() != updated.encode("utf-8"):
            raise OSError("config post-write verification failed")
        return backup


def _sqlite_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def create_immutable_sqlite_backup(
    path: Path,
    *,
    backup_root: Path | None = None,
) -> Path:
    """Create a consistent read-only SQLite backup without copying live sidecars."""

    candidate = backup_path(path, backup_root=backup_root)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        candidate,
        os.O_RDWR | os.O_CREAT | os.O_EXCL,
        stat.S_IREAD | stat.S_IWRITE,
    )
    os.close(descriptor)
    try:
        with closing(_sqlite_read_only(path)) as source, closing(
            sqlite3.connect(candidate)
        ) as destination:
            source.backup(destination)
            destination.commit()
            quick_check = destination.execute("PRAGMA quick_check").fetchone()
            if not quick_check or quick_check[0] != "ok":
                raise OSError("SQLite backup quick_check failed")
        shutil.copystat(path, candidate, follow_symlinks=True)
        candidate.chmod(stat.S_IREAD)
        return candidate
    except Exception:
        try:
            candidate.chmod(stat.S_IREAD | stat.S_IWRITE)
            candidate.unlink()
        except OSError:
            pass
        raise


def _restore_sqlite_backup(backup: Path, destination: Path, *, mode: int) -> None:
    destination.chmod(stat.S_IREAD | stat.S_IWRITE)
    with closing(_sqlite_read_only(backup)) as source, closing(
        sqlite3.connect(destination)
    ) as target:
        source.backup(target)
        target.commit()
    destination.chmod(mode)


def _sqlite_columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})"))


def _cc_switch_317_input_token_semantics_verified(
    connection: sqlite3.Connection,
) -> bool:
    return all(
        CC_SWITCH_317_INPUT_TOKEN_SEMANTICS_COLUMN
        in _sqlite_columns(connection, table)
        for table in CC_SWITCH_317_INPUT_TOKEN_TABLES
    )


def _probe_cc_switch_controller(
    path: Path,
    *,
    version: str | None,
    max_depth: int,
    threads: int,
) -> dict[str, object]:
    result: dict[str, object] = {
        "present": path.is_file(),
        "supported": False,
        "reason": "controller_missing",
        "profile_id": None,
        "payload": None,
        "desired_payload": None,
        "change_required": False,
    }
    if not path.is_file():
        return result
    if not version or re.fullmatch(r"3\.(16|17)\.\d+", version) is None:
        result["reason"] = "unknown_controller_version"
        return result
    try:
        with closing(_sqlite_read_only(path)) as connection:
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            profiles_columns = _sqlite_columns(connection, "profiles")
            settings_columns = _sqlite_columns(connection, "settings")
            result["user_version"] = user_version
            result["profiles_columns"] = profiles_columns
            if version.startswith("3.17."):
                token_tables_ok = _cc_switch_317_input_token_semantics_verified(connection)
                schema_ok = (
                    user_version == 13
                    and profiles_columns == CC_SWITCH_317_PROFILE_COLUMNS
                    and {"key", "value"}.issubset(settings_columns)
                    and token_tables_ok
                )
                reason = "cc_switch_3_17_user_version_13"
            else:
                schema_ok = (
                    user_version == 11
                    and {"id", "payload"}.issubset(profiles_columns)
                    and {"key", "value"}.issubset(settings_columns)
                )
                reason = "cc_switch_3_16_user_version_11"
            if not schema_ok:
                result["reason"] = "unknown_or_mismatched_controller_schema"
                return result

            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                ("current_profile_id_codex",),
            ).fetchone()
            profile_rows: list[tuple[object, object]]
            if row and str(row[0]).strip():
                profile_rows = connection.execute(
                    "SELECT id, payload FROM profiles WHERE id = ?", (str(row[0]),)
                ).fetchall()
            else:
                profile_rows = connection.execute("SELECT id, payload FROM profiles").fetchall()
            candidates: list[tuple[str, dict[str, object]]] = []
            for profile_id, raw_payload in profile_rows:
                try:
                    payload = json.loads(str(raw_payload))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if (
                    isinstance(payload, dict)
                    and payload.get("tool") == "codex"
                    and isinstance(payload.get("config_toml"), str)
                ):
                    candidates.append((str(profile_id), payload))
            if len(candidates) != 1:
                result["reason"] = "controller_codex_profile_payload_unproven"
                return result
            profile_id, payload = candidates[0]
            desired_config = desired_text(
                str(payload["config_toml"]), max_depth, threads, protocol="v2"
            )
            desired_payload = dict(payload)
            desired_payload["config_toml"] = desired_config
            result.update(
                {
                    "supported": True,
                    "reason": reason,
                    "profile_id": profile_id,
                    "payload": payload,
                    "desired_payload": desired_payload,
                    "change_required": desired_payload != payload,
                }
            )
            return result
    except (OSError, sqlite3.Error):
        result["reason"] = "controller_probe_failed"
        return result


def _update_cc_switch_controller(
    path: Path,
    *,
    expected_original: bytes,
    profile_id: str,
    desired_payload: dict[str, object],
) -> None:
    if path.read_bytes() != expected_original:
        raise RuntimeError("controller changed since read")
    connection = sqlite3.connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "UPDATE profiles SET payload = ? WHERE id = ?",
            (json.dumps(desired_payload, ensure_ascii=False, sort_keys=True), profile_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("controller profile changed since probe")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _config_layer_verified(text: str, *, max_depth: int, threads: int) -> bool:
    settings = read_config_settings(text)
    return bool(
        settings.get("selected_protocol") == "v2"
        and settings.get("max_depth") == max_depth
        and settings.get("v2_max_concurrent_threads_per_session") == threads
        and settings.get("legacy_max_threads") is None
        and settings.get("spawn_agent_metadata_hidden") is True
        and settings.get("config_conflict") is False
    )


def _native_read_verified(result: object, *, max_depth: int, threads: int) -> bool:
    if not isinstance(result, dict) or result.get("ok") is not True:
        return False
    native_threads = result.get("max_concurrent_threads_per_session")
    if native_threads is None and isinstance(result.get("multi_agent_v2"), dict):
        native_threads = result["multi_agent_v2"].get("max_concurrent_threads_per_session")
    return result.get("max_depth") == max_depth and native_threads == threads


def _restore_path(path: Path, payload: bytes | None) -> None:
    if payload is None:
        if path.exists():
            path.unlink()
        return
    atomic_write_text(path, payload.decode("utf-8"))


def reconcile_agent_config(
    *,
    config_path: Path,
    managed_config_path: Path,
    threads: int = DEFAULT_HIGH_PARALLEL_THREADS,
    max_depth: int = DEFAULT_MAX_DEPTH,
    apply: bool = False,
    backup_root: Path | None = None,
    controller_db: Path | None = None,
    controller_version: str | None = None,
    native_read: Callable[[Path, Path], dict[str, object]] | None = None,
) -> dict[str, object]:
    """Check or apply one reversible Codex config delta without restarting anything."""

    if isinstance(threads, bool) or not isinstance(threads, int) or threads < 2:
        raise ValueError("threads must be an integer >= 2")
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 1:
        raise ValueError("max_depth must be a positive integer")
    max_depth = min(max_depth, DEFAULT_MAX_DEPTH)
    config_path = config_path.expanduser().resolve()
    managed_config_path = managed_config_path.expanduser().resolve()
    resolved_backup_root = (backup_root or default_backup_root()).expanduser().resolve()
    originals: dict[Path, bytes | None] = {
        path: path.read_bytes() if path.exists() else None
        for path in (config_path, managed_config_path)
    }
    original_text = {
        path: (payload or b"").decode("utf-8", errors="strict")
        for path, payload in originals.items()
    }
    desired = {
        path: desired_text(text, max_depth, threads, protocol="v2")
        for path, text in original_text.items()
    }
    layer_changes = [path for path in desired if desired[path] != original_text[path]]
    events: list[str] = []
    controller_probe: dict[str, object] | None = None
    controller_original: bytes | None = None
    controller_mode: int | None = None
    controller_backup: Path | None = None
    if apply and controller_db is None:
        controller_db = default_cc_switch_db_path()
        events.append("controller_auto_discovered")
    if controller_db is not None:
        controller_db = controller_db.expanduser().resolve()
        events.append("controller_probed")
        controller_probe = _probe_cc_switch_controller(
            controller_db,
            version=controller_version,
            max_depth=max_depth,
            threads=threads,
        )
        if controller_probe.get("present") and controller_probe.get("supported") is not True:
            return {
                "status": "REMINDER_ONLY",
                "blocking": False,
                "compliance_claimed": False,
                "reason": controller_probe.get("reason"),
                "requested_threads": threads,
                "advisory_baseline_threads": ADVISORY_BASELINE_THREADS,
                "default_high_parallel_threads": DEFAULT_HIGH_PARALLEL_THREADS,
                "events": events,
                "restart_required": False,
                "restart_deferred": True,
                "tasks_continued": True,
                "native_read_verified": False,
                "process_control_calls": 0,
            }
        if controller_probe.get("present"):
            controller_original = controller_db.read_bytes()
            controller_mode = stat.S_IMODE(controller_db.stat().st_mode)

    controller_change = bool(
        controller_probe is not None and controller_probe.get("change_required") is True
    )
    if not apply and (layer_changes or controller_change):
        return {
            "status": "REMINDER_ONLY",
            "blocking": False,
            "compliance_claimed": False,
            "reason": "configuration_below_requested_advisory",
            "requested_threads": threads,
            "advisory_baseline_threads": ADVISORY_BASELINE_THREADS,
            "default_high_parallel_threads": DEFAULT_HIGH_PARALLEL_THREADS,
            "events": events,
            "restart_required": False,
            "restart_deferred": True,
            "tasks_continued": True,
            "native_read_verified": False,
            "process_control_calls": 0,
        }

    backups: list[str] = []
    try:
        if apply and controller_change:
            assert controller_db is not None and controller_original is not None
            assert controller_probe is not None
            controller_backup = create_immutable_sqlite_backup(
                controller_db, backup_root=resolved_backup_root / "controller"
            )
            backups.append(str(controller_backup))
            events.append("controller_backup_created")
            _update_cc_switch_controller(
                controller_db,
                expected_original=controller_original,
                profile_id=str(controller_probe["profile_id"]),
                desired_payload=dict(controller_probe["desired_payload"]),
            )
            events.append("controller_updated")
        elif controller_probe is not None and controller_probe.get("present"):
            events.append("controller_already_compliant")

        if apply and layer_changes:
            for path in layer_changes:
                if path.exists():
                    backup = create_immutable_backup(
                        path, backup_root=resolved_backup_root / "effective"
                    )
                    backups.append(str(backup))
            for path in layer_changes:
                atomic_write_text(path, desired[path])
            events.append("effective_files_updated")

        if not all(
            _config_layer_verified(path.read_text(encoding="utf-8"), max_depth=max_depth, threads=threads)
            for path in (config_path, managed_config_path)
        ):
            raise RuntimeError("effective config reread verification failed")
        events.append("effective_files_verified")

        native_ok = False
        if native_read is not None:
            native_ok = _native_read_verified(
                native_read(config_path, managed_config_path),
                max_depth=max_depth,
                threads=threads,
            )
            if not native_ok:
                raise RuntimeError("native config/read verification failed")
            events.append("native_read_verified")

        changed = bool(layer_changes or controller_change)
        status = (
            "UPDATED"
            if changed and native_ok
            else "UPDATED_PENDING_NATIVE_READ"
            if changed
            else "ALREADY_COMPLIANT"
        )
        return {
            "status": status,
            "blocking": False,
            "compliance_claimed": native_ok,
            "reason": "verified" if native_ok else "native_read_not_supplied",
            "requested_threads": threads,
            "advisory_baseline_threads": ADVISORY_BASELINE_THREADS,
            "default_high_parallel_threads": DEFAULT_HIGH_PARALLEL_THREADS,
            "events": events,
            "backups": backups,
            "restart_required": changed,
            "restart_deferred": True,
            "tasks_continued": True,
            "native_read_verified": native_ok,
            "process_control_calls": 0,
        }
    except Exception as exc:
        for path, payload in originals.items():
            _restore_path(path, payload)
        if (
            controller_db is not None
            and controller_original is not None
            and controller_backup is not None
            and controller_mode is not None
        ):
            _restore_sqlite_backup(
                controller_backup,
                controller_db,
                mode=controller_mode,
            )
        events.append("rollback_completed")
        return {
            "status": "REMINDER_ONLY",
            "blocking": False,
            "compliance_claimed": False,
            "reason": type(exc).__name__,
            "requested_threads": threads,
            "events": events,
            "restart_required": False,
            "restart_deferred": True,
            "tasks_continued": True,
            "native_read_verified": False,
            "process_control_calls": 0,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--managed-config", type=Path, default=default_managed_config_path())
    parser.add_argument(
        "--managed-overlay",
        action="store_true",
        help="Write/check the protocol-only managed_config.toml layer instead of the Desktop-owned user config.",
    )
    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    parser.add_argument(
        "--threads",
        "--max-threads",
        dest="threads",
        type=int,
        default=DEFAULT_HIGH_PARALLEL_THREADS,
        help="Requested whole-tree threads; default 16, explicit values above 16 are preserved.",
    )
    parser.add_argument("--protocol", choices=("auto", "v1", "v2"), default="auto")
    parser.add_argument("--backup-root", type=Path, help="Shared Shiguan backup root override.")
    parser.add_argument("--cc-switch-db", type=Path, help="Explicit CC Switch SQLite controller fixture/store.")
    parser.add_argument("--cc-switch-version", help="Proven CC Switch app version for schema allowlisting.")
    parser.add_argument("--native-read-json", type=Path, help="Sanitized native config/read receipt; never starts or restarts Codex.")
    parser.add_argument("--check", action="store_true", help="Check only. This is also the default.")
    parser.add_argument("--write", action="store_true", help="Write config changes. Default is check-only.")
    parser.add_argument("--apply", action="store_true", help="Alias for --write.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    apply_requested = bool(args.write or args.apply)

    refusal_reason = None
    if apply_requested and args.managed_overlay:
        refusal_reason = "managed_overlay_apply_bypass_disabled"
    elif apply_requested and args.protocol == "v1":
        refusal_reason = "v1_apply_deprecated_fail_closed"
    if refusal_reason is not None:
        result = {
            "status": "REFUSED",
            "blocking": True,
            "compliance_claimed": False,
            "reason": refusal_reason,
            "restart_required": False,
            "restart_deferred": True,
            "tasks_continued": True,
            "native_read_verified": False,
            "process_control_calls": 0,
        }
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                f"AGENT_CONFIG_REFUSED reason={refusal_reason} "
                "restart_required=false restart_deferred=true tasks_continued=true"
            )
        return 2

    if not args.managed_overlay:
        native_read = None
        if args.native_read_json is not None:
            receipt = json.loads(args.native_read_json.read_text(encoding="utf-8"))

            def native_read(_config: Path, _managed: Path) -> dict[str, object]:
                return dict(receipt)

        result = reconcile_agent_config(
            config_path=args.config,
            managed_config_path=args.managed_config,
            threads=args.threads,
            max_depth=args.max_depth,
            apply=apply_requested,
            backup_root=args.backup_root,
            controller_db=args.cc_switch_db,
            controller_version=args.cc_switch_version,
            native_read=native_read,
        )
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                f"AGENT_CONFIG_{result['status']} threads={args.threads} "
                f"blocking={str(result['blocking']).lower()} "
                f"restart_required={str(result['restart_required']).lower()} "
                f"restart_deferred={str(result['restart_deferred']).lower()} "
                f"tasks_continued={str(result['tasks_continued']).lower()}"
            )
        return 0

    path = (args.managed_config if args.managed_overlay else args.config).expanduser().resolve()
    layer = "managed_overlay" if args.managed_overlay else "user_config"
    original_bytes = path.read_bytes() if path.exists() else b""
    original = original_bytes.decode("utf-8", errors="replace")
    settings = read_config_settings(original)
    current_depth = settings["max_depth"]
    current_threads = settings["max_threads"]
    legacy_threads = settings["legacy_max_threads"]
    has_agents = bool(settings["agents_section"])
    updated = desired_text(original, args.max_depth, args.threads, protocol=args.protocol)
    target_settings = read_config_settings(updated)
    target_protocol = target_settings.get("selected_protocol")
    changed = updated != original

    if not changed:
        print(
            f"AGENT_CONFIG_OK {path} layer={layer} max_depth={current_depth} max_threads={current_threads} "
            f"legacy_max_threads={legacy_threads} "
            f"effective_child_thread_limit={settings['effective_child_thread_limit']} "
            f"selected_protocol={settings['selected_protocol']} "
            f"multi_agent_v2_enabled={settings['multi_agent_v2_enabled']} "
            f"inactive_v2_config_preserved={settings['inactive_v2_config_preserved']} "
            f"spawn_agent_metadata_hidden={settings['spawn_agent_metadata_hidden']} "
            f"reserved_spawn_schema_compatible={settings['reserved_spawn_schema_compatible']}"
        )
        return 0

    if not (args.write or args.apply):
        section = "present" if has_agents else "missing"
        print(
            f"AGENT_CONFIG_BELOW_RECOMMENDED {path} layer={layer} "
            f"agents_section={section} current_max_depth={current_depth} "
            f"current_max_threads={current_threads} legacy_max_threads={legacy_threads} "
            f"config_conflict={settings['config_conflict']} target_max_depth={args.max_depth} "
            f"target_max_threads={args.threads} target_protocol={target_protocol}"
        )
        overlay_flag = " --managed-overlay" if args.managed_overlay else ""
        print(f"Run: python .\\scripts\\ensure_court_agent_config.py --write --protocol {target_protocol}{overlay_flag}")
        return 0

    backup = write_config_update(path, original_bytes, updated, backup_root=args.backup_root)
    print(
        f"AGENT_CONFIG_UPDATED {path} layer={layer} max_depth={args.max_depth} "
        f"selected_protocol={target_protocol} max_concurrent_threads_per_session={target_settings['v2_max_concurrent_threads_per_session']} "
        f"effective_child_thread_limit={target_settings['effective_child_thread_limit']} "
        f"legacy_max_threads={target_settings['legacy_max_threads']} multi_agent_v2_enabled={target_settings['multi_agent_v2_enabled']} "
        f"inactive_v2_config_preserved={target_settings['inactive_v2_config_preserved']} "
        f"spawn_agent_metadata_hidden={target_settings['spawn_agent_metadata_hidden']} "
        f"reserved_spawn_schema_compatible={target_settings['reserved_spawn_schema_compatible']}"
    )
    if backup:
        print(f"AGENT_CONFIG_BACKUP {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
