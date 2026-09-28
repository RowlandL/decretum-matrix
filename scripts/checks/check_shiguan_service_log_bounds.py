"""Independent bounds/rotation contract check for the Shiguan service log.

Verifies ``scripts/shiguan_service_log.py`` (``service_log_path`` /
``rotate_service_log`` / ``open_service_log`` / ``maintain_service_log`` /
``record_rotation``, single ``"<path>.1"`` archive, independent ``"<path>.lock"``,
bounded ``"<path>.rotation.json"`` action journal) plus the three daemon/WebUI
call sites that redirect stdout and the two long-lived daemon loops that must
keep bounding the log they inherit. Everything runs against isolated
temp-directory fixtures: no real %TEMP% service log, no repository data and no
Shiguan runtime path is written.
"""

from __future__ import annotations

import argparse
import importlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


MODULE_NAME = "shiguan_service_log"
CONTRACT = "SHIGUAN_LOG_BOUNDS"
SCHEMA = "court.shiguan_service_log_bounds_check.v1"
EXPECTED_MAX_BYTES = 8 * 1024 * 1024
EXPECTED_ACTIONS = frozenset(
    {"KEPT", "ROTATED", "ROTATED_INPLACE", "ROTATION_BLOCKED", "SKIPPED_LOCKED"}
)
RESULT_FIELDS = frozenset({"action", "size_bytes", "archive"})
FIXTURE_PREFIX = "fixture-"
FOREIGN_LOCK_NAME = "shiguan-write.lock"
CALL_SITES = (
    "scripts/services/ensure_shiguan_autosync.py",
    "scripts/services/ensure_shiguan_service_daemon.py",
    "scripts/commands/ensure_shiguan_web.py",
)
# A launcher can only bound the log at start time; these loops outlive it and
# must keep reclaiming the live file they inherit for their whole lifetime.
DAEMON_LOOPS = (
    "scripts/services/shiguan_autosync_daemon.py",
    "scripts/services/shiguan_service_daemon.py",
)
ROTATION_CALLS = ("maintain_service_log(", "rotate_service_log(", "rotate_held_service_log(")
RECORDED_ACTIONS = frozenset(
    {"ROTATED", "ROTATED_INPLACE", "ROTATION_BLOCKED", "SKIPPED_LOCKED"}
)
JOURNAL_SUFFIX = ".rotation.json"
JOURNAL_MAX_BYTES = 1024
BARE_APPEND_OPEN = re.compile(r"""open\(\s*["']a""")


def _size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _archives(path: Path) -> list[Path]:
    return sorted(item for item in path.parent.glob(path.name + ".[0-9]*") if item.is_file())


def _foreign_locks(directory: Path, allowed: str) -> list[str]:
    return sorted(
        item.name
        for item in directory.glob("*.lock")
        if item.name != allowed
    )


def _result_shape(result: Any, label: str, failures: list[str]) -> bool:
    valid = (
        isinstance(result, dict)
        and set(result) == RESULT_FIELDS
        and result.get("action") in EXPECTED_ACTIONS
        and isinstance(result.get("size_bytes"), int)
        and not isinstance(result.get("size_bytes"), bool)
        and result.get("size_bytes") >= 0
        and (result.get("archive") is None or isinstance(result.get("archive"), str))
    )
    if not valid:
        failures.append(f"rotate_result_shape_invalid:{label}")
    return valid


def _journal(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _close(handle: Any) -> None:
    try:
        handle.close()
    except OSError:
        pass


def _function_body(text: str, name: str) -> str:
    """Slice one top-level ``def`` body (enough for the two daemon loops)."""

    marker = f"\ndef {name}("
    start = text.find(marker)
    if start < 0:
        return ""
    start += 1
    end = text.find("\ndef ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def _check_daemon_loops(failures: list[str], evidence: dict[str, Any]) -> None:
    """The long-lived loops must bound the log they inherit, not just start it."""

    observed: dict[str, Any] = {}
    for relative in DAEMON_LOOPS:
        source = ROOT / relative
        if not source.is_file():
            failures.append(f"daemon_loop_module_missing:{relative}")
            continue
        body = _function_body(source.read_text(encoding="utf-8"), "daemon_loop")
        loop = body.split("while True", 1)[1] if "while True" in body else ""
        calls = [name for name in ROTATION_CALLS if name in loop]
        if not loop:
            failures.append(f"daemon_loop_missing_while_true:{relative}")
        elif not calls:
            failures.append(f"daemon_loop_missing_runtime_rotation:{relative}")
        observed[relative] = {
            "daemon_loop": bool(body),
            "while_true": bool(loop),
            "runtime_rotation_calls": calls,
            "journals_action": "record_rotation(" in loop or "maintain_service_log(" in loop,
        }
    evidence["daemon_loops"] = observed


def _check_call_sites(failures: list[str], evidence: dict[str, Any]) -> None:
    observed: dict[str, Any] = {}
    for relative in CALL_SITES:
        source = ROOT / relative
        if not source.is_file():
            failures.append(f"call_site_missing:{relative}")
            continue
        text = source.read_text(encoding="utf-8")
        uses_service_log_path = "service_log_path(" in text
        uses_open_service_log = "open_service_log(" in text
        bare_append = BARE_APPEND_OPEN.search(text) is not None
        if not uses_service_log_path:
            failures.append(f"call_site_missing_service_log_path:{relative}")
        if not uses_open_service_log:
            failures.append(f"call_site_missing_open_service_log:{relative}")
        if bare_append:
            failures.append(f"call_site_bare_append_open:{relative}")
        observed[relative] = {
            "service_log_path": uses_service_log_path,
            "open_service_log": uses_open_service_log,
            "bare_append_open": bare_append,
        }
    evidence["call_sites"] = observed


def evaluate() -> dict[str, Any]:
    failures: list[str] = []
    evidence: dict[str, Any] = {}

    try:
        module = importlib.import_module(MODULE_NAME)
    except ImportError as exc:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "FAIL",
            "contract": CONTRACT,
            "evidence": {"implementation_import": f"{type(exc).__name__}: {exc}"},
            "failures": [f"implementation_not_importable:{MODULE_NAME}"],
        }

    evidence["implementation"] = {
        "module": getattr(module, "__file__", MODULE_NAME),
        "default_max_bytes": getattr(module, "DEFAULT_MAX_BYTES", None),
    }
    if getattr(module, "DEFAULT_MAX_BYTES", None) != EXPECTED_MAX_BYTES:
        failures.append("default_max_bytes_not_8MiB")
    for name in (
        "service_log_path",
        "rotate_service_log",
        "rotate_held_service_log",
        "maintain_service_log",
        "record_rotation",
        "rotation_journal_path",
        "open_service_log",
    ):
        if not callable(getattr(module, name, None)):
            failures.append(f"contract_callable_missing:{name}")
    if failures:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "FAIL",
            "contract": CONTRACT,
            "evidence": evidence,
            "failures": list(dict.fromkeys(failures)),
        }

    # Pure path computation: proves the shared %TEMP% anchor without writing it.
    expected_default = Path(tempfile.gettempdir()) / "court-shiguan-autosync.log"
    if module.service_log_path("court-shiguan-autosync.log") != expected_default:
        failures.append("service_log_path_not_tempdir_anchored")
    evidence["service_log_path_tempdir_anchored"] = (
        module.service_log_path("court-shiguan-autosync.log") == expected_default
    )

    module_source = Path(str(module.__file__)).read_text(encoding="utf-8")
    if "shiguan-write" in module_source or "shiguan_write_lock" in module_source:
        failures.append("implementation_uses_shiguan_write_lock")
    if ".lock" not in module_source:
        failures.append("implementation_missing_lock_suffix")
    evidence["implementation_lock_independent"] = (
        "shiguan-write" not in module_source
        and "shiguan_write_lock" not in module_source
        and ".lock" in module_source
    )

    max_bytes = 4096

    with tempfile.TemporaryDirectory(prefix="court-shiguan-log-bounds-") as temp_dir:
        temp = Path(temp_dir)
        # One directory per fixture so lock/archive scans cannot see siblings.
        kept_dir = temp / "kept"
        rotated_dir = temp / "rotated"
        cycles_dir = temp / "cycles"
        open_dir = temp / "open"
        for directory in (kept_dir, rotated_dir, cycles_dir, open_dir):
            directory.mkdir()

        # 1) Under the limit: KEPT and zero byte mutation, no archive.
        kept_path = kept_dir / (FIXTURE_PREFIX + "kept.log")
        kept_path.write_bytes(b"k" * 1024)
        kept_before = kept_path.read_bytes()
        kept = module.rotate_service_log(kept_path)
        _result_shape(kept, "kept", failures)
        if kept.get("action") != "KEPT":
            failures.append("under_limit_action_not_kept")
        if kept_path.read_bytes() != kept_before:
            failures.append("under_limit_mutated_file")
        if kept.get("size_bytes") != 1024:
            failures.append("under_limit_size_bytes_invalid")
        if kept.get("archive") is not None:
            failures.append("under_limit_archive_reported")
        if _archives(kept_path):
            failures.append("under_limit_created_archive")
        kept_foreign = _foreign_locks(kept_dir, kept_path.name + ".lock")
        if kept_foreign:
            failures.append("under_limit_foreign_lock:" + ",".join(kept_foreign))
        evidence["under_limit_kept_unchanged"] = (
            kept.get("action") == "KEPT"
            and kept_path.read_bytes() == kept_before
            and not _archives(kept_path)
        )

        # 2) Over the limit: single archive equals the original bytes, live file
        #    reset, live+archive within 2 * max_bytes, independent lock file.
        rotated_path = rotated_dir / (FIXTURE_PREFIX + "rotated.log")
        rotated_path.write_bytes(b"r" * 7000)
        rotated_before = rotated_path.read_bytes()
        rotated = module.rotate_service_log(rotated_path, max_bytes=max_bytes)
        _result_shape(rotated, "rotated", failures)
        rotated_archive = Path(str(rotated_path) + ".1")
        if rotated.get("action") != "ROTATED":
            failures.append("over_limit_action_not_rotated")
        if not rotated_archive.is_file():
            failures.append("over_limit_archive_missing")
        elif rotated_archive.read_bytes() != rotated_before:
            failures.append("over_limit_archive_content_mismatch")
        if rotated.get("archive") is not None and Path(str(rotated.get("archive"))) != rotated_archive:
            failures.append("over_limit_archive_path_mismatch")
        if _size(rotated_path) != 0:
            failures.append("over_limit_live_file_not_reset")
        live_plus_archive = _size(rotated_path) + _size(rotated_archive)
        if live_plus_archive > 2 * max_bytes:
            failures.append("over_limit_total_exceeds_two_limits")
        if rotated.get("size_bytes") not in (len(rotated_before), 0):
            failures.append("over_limit_size_bytes_unexpected")
        lock_path = Path(str(rotated_path) + ".lock")
        if not lock_path.is_file():
            failures.append("independent_lock_file_missing")
        stray_locks = _foreign_locks(rotated_dir, lock_path.name)
        if stray_locks:
            failures.append("foreign_lock_file_created:" + ",".join(stray_locks))
        foreign_write_locks = sorted(
            item.name for item in temp.rglob(FOREIGN_LOCK_NAME)
        )
        if foreign_write_locks:
            failures.append("shiguan_write_lock_created")
        evidence["rotation"] = {
            "action": rotated.get("action"),
            "archive_bytes": _size(rotated_archive),
            "original_bytes": len(rotated_before),
            "live_bytes_after": _size(rotated_path),
            "live_plus_archive": live_plus_archive,
            "limit": max_bytes,
            "archive_count": len(_archives(rotated_path)),
            "lock_file": lock_path.name,
            "lock_file_present": lock_path.is_file(),
        }
        evidence["over_limit_rotated_and_bounded"] = (
            rotated.get("action") == "ROTATED"
            and _size(rotated_archive) == len(rotated_before)
            and _size(rotated_path) == 0
            and live_plus_archive <= 2 * max_bytes
            and len(_archives(rotated_path)) == 1
        )
        evidence["independent_lock_not_shiguan_write"] = (
            lock_path.is_file() and not stray_locks and not foreign_write_locks
        )

        # 3) Idempotent repeat: a second rotate produces no extra archive and
        #    never rewrites the retained history; repeated open/write/close
        #    sessions stay bounded instead of growing without limit.
        cycle_path = cycles_dir / (FIXTURE_PREFIX + "cycles.log")
        chunk = max_bytes // 4
        cycle_path.write_bytes(b"c" * (max_bytes + max_bytes // 3))
        first_rotate = module.rotate_service_log(cycle_path, max_bytes=max_bytes)
        _result_shape(first_rotate, "cycles-first", failures)
        cycle_archive = Path(str(cycle_path) + ".1")
        first_archive_bytes = cycle_archive.read_bytes() if cycle_archive.is_file() else b""
        second_rotate = module.rotate_service_log(cycle_path, max_bytes=max_bytes)
        _result_shape(second_rotate, "cycles-second", failures)
        if second_rotate.get("action") != "KEPT":
            failures.append("repeat_rotate_not_kept")
        if _size(cycle_path) != 0:
            failures.append("repeat_rotate_mutated_live_file")
        if not cycle_archive.is_file() or cycle_archive.read_bytes() != first_archive_bytes:
            failures.append("repeat_rotate_rewrote_archive")
        if len(_archives(cycle_path)) != 1:
            failures.append("repeat_rotate_created_extra_archive")

        # Each session appends at most `chunk` bytes, so a compliant
        # implementation bounds live+archive by 2 * max_bytes + 2 * chunk
        # independently of the number of sessions.
        session_lines = [f"session-{index:03d}\n" for index in range(24)]
        for line in session_lines:
            padding = chunk - len(line.encode("utf-8"))
            with module.open_service_log(cycle_path, max_bytes=max_bytes) as handle:
                handle.write(line)
                handle.write("c" * padding)
        unbounded_reference = len(session_lines) * chunk
        bound = 2 * max_bytes + 2 * chunk
        cycle_total = _size(cycle_path) + _size(cycle_archive)
        if cycle_total > bound:
            failures.append("sessions_total_exceeds_bound")
        if _size(cycle_path) > max_bytes + chunk:
            failures.append("sessions_live_file_exceeds_bound")
        if len(_archives(cycle_path)) != 1:
            failures.append("sessions_created_extra_archive")
        retained = cycle_path.read_text(encoding="utf-8")
        if not retained.endswith(session_lines[-1] + "c" * (chunk - len(session_lines[-1].encode("utf-8")))):
            failures.append("sessions_last_write_not_retained")
        evidence["sessions"] = {
            "count": len(session_lines),
            "bytes_per_session": chunk,
            "unbounded_reference_bytes": unbounded_reference,
            "bound_bytes": bound,
            "observed_live_plus_archive": cycle_total,
            "archive_count": len(_archives(cycle_path)),
        }
        evidence["sessions_bounded_and_idempotent"] = (
            second_rotate.get("action") == "KEPT"
            and len(_archives(cycle_path)) == 1
            and cycle_total <= bound
        )

        # 4) open_service_log appends (never truncates) and writes through to
        #    the managed file.
        open_path = open_dir / (FIXTURE_PREFIX + "open.log")
        with module.open_service_log(open_path, max_bytes=max_bytes) as handle:
            handle.write("first-session\n")
        with module.open_service_log(open_path, max_bytes=max_bytes) as handle:
            handle.write("second-session\n")
        open_text = open_path.read_text(encoding="utf-8")
        if open_text != "first-session\nsecond-session\n":
            failures.append("open_service_log_append_semantics_invalid")
        evidence["open_service_log_appends"] = open_text == (
            "first-session\nsecond-session\n"
        )

        # 5) Live-holder fallback (R1): a detached child keeps the log handle
        #    open, so os.replace fails exactly when rotation matters most. The
        #    implementation must reclaim space in place (bounded tail archived,
        #    live file truncated) and report ROTATED_INPLACE; a reclaim that is
        #    itself blocked must not degrade into a silent lock skip.
        pinned_path = open_dir / (FIXTURE_PREFIX + "pinned.log")
        pinned_path.write_bytes(b"p" * (max_bytes * 2))
        real_replace = module.os.replace

        def _blocked_replace(*_args: Any, **_kwargs: Any) -> None:
            raise PermissionError("fixture_live_handle_blocks_replace")

        try:
            module.os.replace = _blocked_replace
            pinned = module.rotate_service_log(pinned_path, max_bytes=max_bytes)
        finally:
            module.os.replace = real_replace
        _result_shape(pinned, "live-handle", failures)
        pinned_archive = Path(str(pinned_path) + ".1")
        if pinned.get("action") != "ROTATED_INPLACE":
            failures.append("live_handle_action_not_inplace")
        if _size(pinned_path) != 0:
            failures.append("live_handle_live_file_not_reclaimed")
        if not pinned_archive.is_file():
            failures.append("live_handle_tail_not_archived")
        elif _size(pinned_archive) > module.TAIL_KEEP_BYTES:
            failures.append("live_handle_tail_exceeds_bound")
        evidence["live_handle_fallback"] = {
            "action": pinned.get("action"),
            "live_bytes_after": _size(pinned_path),
            "tail_bytes": _size(pinned_archive),
            "tail_bound": module.TAIL_KEEP_BYTES,
        }
        evidence["live_handle_reclaims_in_place"] = (
            pinned.get("action") == "ROTATED_INPLACE"
            and _size(pinned_path) == 0
            and _size(pinned_archive) <= module.TAIL_KEEP_BYTES
        )

        # 6) Rotation journal: the action the launcher used to drop must land in
        #    a bounded "<log>.rotation.json" that is atomically rewritten, never
        #    appended, so a degraded reclaim stays observable at runtime.
        journal_dir = temp / "journal"
        locked_dir = temp / "locked"
        held_dir = temp / "held"
        blocked_dir = temp / "blocked"
        for directory in (journal_dir, locked_dir, held_dir, blocked_dir):
            directory.mkdir()

        journal_path = journal_dir / (FIXTURE_PREFIX + "journal.log")
        journal_path.write_bytes(b"j" * 7000)
        _close(module.open_service_log(journal_path, max_bytes=max_bytes))
        journal = module.rotation_journal_path(journal_path)
        if journal.name != journal_path.name + JOURNAL_SUFFIX:
            failures.append("rotation_journal_path_invalid")
        first_record = _journal(journal)
        if not journal.is_file():
            failures.append("rotation_journal_missing")
        elif _size(journal) > JOURNAL_MAX_BYTES:
            failures.append("rotation_journal_exceeds_bound")
        if first_record.get("action") not in RECORDED_ACTIONS:
            failures.append("rotation_journal_action_not_recorded")
        first_journal_bytes = _size(journal)
        journal_path.write_bytes(b"j" * 7000)
        _close(module.open_service_log(journal_path, max_bytes=max_bytes))
        second_journal_bytes = _size(journal)
        if (
            second_journal_bytes > JOURNAL_MAX_BYTES
            or second_journal_bytes > first_journal_bytes + 256
        ):
            failures.append("rotation_journal_grew")
        if sorted(item.name for item in journal_dir.glob(".*.tmp")):
            failures.append("rotation_journal_temp_residue")
        evidence["rotation_journal"] = {
            "path": journal.name,
            "action": first_record.get("action"),
            "bytes": first_journal_bytes,
            "bytes_after_repeat": second_journal_bytes,
            "bound_bytes": JOURNAL_MAX_BYTES,
        }
        evidence["rotation_journal_bounded"] = (
            journal.is_file()
            and first_record.get("action") in RECORDED_ACTIONS
            and 0 < first_journal_bytes <= JOURNAL_MAX_BYTES
            and second_journal_bytes <= first_journal_bytes + 256
        )

        # 7) A lock skip is a degradation, not a silent no-op: it must be
        #    journalled as SKIPPED_LOCKED for the running service.
        locked_path = locked_dir / (FIXTURE_PREFIX + "locked.log")
        locked_path.write_bytes(b"k" * 7000)
        real_lock = module.file_lock

        class _RaisingLock:
            def __enter__(self) -> None:
                raise TimeoutError("fixture_lock_holder")

            def __exit__(self, *_exc: Any) -> bool:
                return False

        def _blocked_lock(*_args: Any, **_kwargs: Any) -> Any:
            return _RaisingLock()

        try:
            module.file_lock = _blocked_lock
            _close(module.open_service_log(locked_path, max_bytes=max_bytes))
        finally:
            module.file_lock = real_lock
        locked_record = _journal(module.rotation_journal_path(locked_path))
        if locked_record.get("action") != "SKIPPED_LOCKED":
            failures.append("skipped_locked_not_journalled")
        evidence["degraded_lock_skip_journalled"] = (
            locked_record.get("action") == "SKIPPED_LOCKED"
        )

        # 8) The daemon-held path: a long-lived writer reclaims its own log in
        #    place, rewinds its handle to zero and journals the action. The write
        #    that follows must land at offset 0, because truncation does not move
        #    a file offset: a stale offset would punch a zero-filled hole into the
        #    freshly reclaimed log (the R1 live-writer caveat). A stream that is
        #    not provably the log must fail closed instead of truncating it.
        held_path = held_dir / (FIXTURE_PREFIX + "held.log")
        held_path.write_bytes(b"h" * (max_bytes * 2))
        held_journal = module.rotation_journal_path(held_path)
        held = {}
        held_record: dict[str, Any] = {}
        held_stream = held_path.open("a", encoding="utf-8")
        try:
            held = module.maintain_service_log(
                held_path, max_bytes=max_bytes, live_stream=held_stream
            )
            _result_shape(held, "maintain", failures)
            held_record = _journal(held_journal)
            held_stream.write("held-after-reclaim\n")
            held_stream.flush()
        finally:
            held_stream.close()
        held_archive = Path(str(held_path) + ".1")
        held_after = held_path.read_bytes()
        held_text = held_path.read_text(encoding="utf-8")
        held_journal_bytes = held_journal.read_bytes() if held_journal.is_file() else b""
        if held.get("action") != "ROTATED_INPLACE":
            failures.append("maintain_action_not_inplace")
        if held_record.get("action") != "ROTATED_INPLACE":
            failures.append("inplace_not_journalled")
        if _size(held_archive) == 0 or _size(held_archive) > module.TAIL_KEEP_BYTES:
            failures.append("maintain_tail_not_bounded")
        if held_after.count(b"\x00") or not held_after.startswith(b"held-after-reclaim"):
            failures.append("held_handle_stale_offset_hole")
        if held_text != "held-after-reclaim\n" or _size(held_path) > 64:
            failures.append("maintain_live_file_not_reclaimed")

        # Idempotent once back under the cap, and a foreign stream (not this log)
        # must not truncate a file it does not own.
        repeat = module.maintain_service_log(
            held_path, max_bytes=max_bytes, live_stream=io.StringIO()
        )
        _result_shape(repeat, "maintain-repeat", failures)
        if repeat.get("action") != "KEPT":
            failures.append("maintain_repeat_not_kept")
        if not held_journal_bytes or held_journal.read_bytes() != held_journal_bytes:
            failures.append("maintain_rewrote_journal_when_kept")
        foreign_path = held_dir / (FIXTURE_PREFIX + "foreign.log")
        foreign_path.write_bytes(b"f" * (max_bytes * 2))
        foreign_before = foreign_path.read_bytes()
        foreign = module.maintain_service_log(
            foreign_path, max_bytes=max_bytes, live_stream=io.StringIO()
        )
        _result_shape(foreign, "maintain-foreign", failures)
        if foreign.get("action") != "ROTATION_BLOCKED":
            failures.append("foreign_stream_not_fail_closed")
        if foreign_path.read_bytes() != foreign_before:
            failures.append("foreign_stream_mutated_log")
        evidence["held_handle_maintenance"] = {
            "action": held.get("action"),
            "live_bytes_after": _size(held_path),
            "tail_bytes": _size(held_archive),
            "journal_action": held_record.get("action"),
            "repeat_action": repeat.get("action"),
            "nul_bytes_after_reclaim": held_after.count(b"\x00"),
            "foreign_stream_action": foreign.get("action"),
        }
        evidence["held_handle_reclaims_in_place"] = (
            held.get("action") == "ROTATED_INPLACE"
            and held_text == "held-after-reclaim\n"
            and held_record.get("action") == "ROTATED_INPLACE"
            and repeat.get("action") == "KEPT"
        )
        evidence["held_handle_rewound_no_hole"] = bool(
            held_after.startswith(b"held-after-reclaim") and not held_after.count(b"\x00")
        )
        evidence["foreign_stream_fails_closed"] = bool(
            foreign.get("action") == "ROTATION_BLOCKED"
            and foreign_path.read_bytes() == foreign_before
        )

        # 9) P3: an unwritable log target degrades to a usable sink instead of
        #    raising out of the launcher and blocking service start.
        blocker = blocked_dir / (FIXTURE_PREFIX + "blocker")
        blocker.write_text("not a directory", encoding="utf-8")
        blocked_path = blocker / (FIXTURE_PREFIX + "unwritable.log")
        degraded: Any = None
        degraded_error = ""
        failed_open = True
        try:
            degraded = module.open_service_log(blocked_path, max_bytes=max_bytes)
            degraded.write("degraded-degraded\n")
            degraded.flush()
        except OSError as exc:
            degraded_error = f"{type(exc).__name__}:{exc}"
        else:
            failed_open = callable(getattr(degraded, "fileno", None))
        finally:
            if degraded is not None:
                _close(degraded)
        if degraded_error:
            failures.append("unwritable_log_blocked_start:" + degraded_error)
        if blocked_path.exists():
            failures.append("unwritable_log_target_created")
        sink = module.DegradedLogSink()
        if sink.write("x") != 1:
            failures.append("degraded_sink_write_invalid")
        sink.close()
        evidence["unwritable_log_degrades"] = {
            "error": degraded_error,
            "usable_handle": bool(not degraded_error and failed_open),
            "target_created": blocked_path.exists(),
        }
        evidence["startup_not_blocked_by_unwritable_log"] = bool(
            not degraded_error and not blocked_path.exists()
        )

        # 10) D1 fail-closed: when the bounded tail cannot be archived (here
        #     "<log>.1" is a directory), the reclaim must report ROTATION_BLOCKED
        #     and must not truncate, and the launcher must still journal that
        #     decision instead of reporting a successful ROTATED_INPLACE.
        noarchive_dir = temp / "noarchive"
        noarchive_dir.mkdir()
        noarchive_bytes = b"n" * 7000
        noarchive_path = noarchive_dir / (FIXTURE_PREFIX + "noarchive.log")
        noarchive_path.write_bytes(noarchive_bytes)
        (noarchive_dir / (FIXTURE_PREFIX + "noarchive.log.1")).mkdir()
        noarchive = module.rotate_service_log(noarchive_path, max_bytes=max_bytes)
        _result_shape(noarchive, "noarchive", failures)
        if noarchive.get("action") != "ROTATION_BLOCKED":
            failures.append("archive_failure_not_blocked")
        if noarchive.get("archive") is not None:
            failures.append("archive_failure_claimed_archive")
        if noarchive_path.read_bytes() != noarchive_bytes:
            failures.append("archive_failure_lost_bytes")
        journaled_path = noarchive_dir / (FIXTURE_PREFIX + "noarchive-open.log")
        journaled_path.write_bytes(noarchive_bytes)
        (noarchive_dir / (FIXTURE_PREFIX + "noarchive-open.log.1")).mkdir()
        _close(module.open_service_log(journaled_path, max_bytes=max_bytes))
        journaled_after = journaled_path.read_bytes()
        if journaled_after != noarchive_bytes:
            failures.append("journaled_archive_failure_lost_bytes")
        noarchive_record = _journal(module.rotation_journal_path(journaled_path))
        if noarchive_record.get("action") != "ROTATION_BLOCKED":
            failures.append("archive_failure_not_journalled")
        evidence["archive_failure_fails_closed"] = {
            "action": noarchive.get("action"),
            "archive_field": noarchive.get("archive"),
            "direct_bytes_unchanged": noarchive_path.read_bytes() == noarchive_bytes,
            "journal_action": noarchive_record.get("action"),
            "journaled_bytes_unchanged": journaled_after == noarchive_bytes,
        }
        evidence["archive_failure_keeps_bytes_and_journals"] = bool(
            noarchive.get("action") == "ROTATION_BLOCKED"
            and noarchive_path.read_bytes() == noarchive_bytes
            and noarchive_record.get("action") == "ROTATION_BLOCKED"
            and journaled_after == noarchive_bytes
        )

        # Fixture isolation guard: every write stays inside the temp fixture.
        fixtures = (
            kept_path,
            rotated_path,
            cycle_path,
            open_path,
            pinned_path,
            journal_path,
            locked_path,
            held_path,
            foreign_path,
            blocked_path,
            noarchive_path,
            journaled_path,
        )
        if any(not item.name.startswith(FIXTURE_PREFIX) for item in fixtures):
            failures.append("fixture_isolation_violation")
        if any(temp not in item.parents for item in fixtures):
            failures.append("fixture_escaped_temp_root")

    # 6) Static wiring: the three production call sites stay on the shared
    #    opener, and both long-lived daemon loops keep bounding the live log.
    _check_call_sites(failures, evidence)
    _check_daemon_loops(failures, evidence)

    failures = list(dict.fromkeys(failures))
    return {
        "schema": SCHEMA,
        "ok": not failures,
        "status": "PASS" if not failures else "FAIL",
        "contract": CONTRACT,
        "evidence": evidence,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate()
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": SCHEMA,
            "ok": False,
            "status": "ERROR",
            "contract": CONTRACT,
            "failures": [f"checker_setup_error:{type(exc).__name__}:{exc}"],
        }
    if args.json:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"SHIGUAN_LOG_BOUNDS={result['status']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
