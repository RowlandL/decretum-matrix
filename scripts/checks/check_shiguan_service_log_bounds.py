"""Independent bounds/rotation contract check for the Shiguan service log.

Verifies ``scripts/shiguan_service_log.py`` (``service_log_path`` /
``rotate_service_log`` / ``open_service_log``, single ``"<path>.1"`` archive,
independent ``"<path>.lock"``) plus the three daemon/WebUI call sites that
redirect stdout, entirely against isolated temp-directory fixtures: no real
%TEMP% service log, no repository data and no Shiguan runtime path is written.
"""

from __future__ import annotations

import argparse
import importlib
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
EXPECTED_ACTIONS = frozenset({"KEPT", "ROTATED", "SKIPPED_LOCKED"})
RESULT_FIELDS = frozenset({"action", "size_bytes", "archive"})
FIXTURE_PREFIX = "fixture-"
FOREIGN_LOCK_NAME = "shiguan-write.lock"
CALL_SITES = (
    "scripts/services/ensure_shiguan_autosync.py",
    "scripts/services/ensure_shiguan_service_daemon.py",
    "scripts/commands/ensure_shiguan_web.py",
)
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
    for name in ("service_log_path", "rotate_service_log", "open_service_log"):
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

        # Fixture isolation guard: every write stays inside the temp fixture.
        fixtures = (kept_path, rotated_path, cycle_path, open_path)
        if any(not item.name.startswith(FIXTURE_PREFIX) for item in fixtures):
            failures.append("fixture_isolation_violation")
        if any(temp not in item.parents for item in fixtures):
            failures.append("fixture_escaped_temp_root")

    # 5) Static wiring of the three production call sites.
    _check_call_sites(failures, evidence)

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
