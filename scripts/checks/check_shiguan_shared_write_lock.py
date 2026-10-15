"""Contract check for the shared (multi-writer) Shiguan write lock and the
launcher-side rotation deferral.

Proves with temporary fixtures, without writing authoritative Shiguan data:

1. Independent processes can overlap shared holders of the same OS byte lock.
2. Shared/exclusive exclude each other in both directions, including old CRT locks.
3. ``shiguan_paths.ensure_shared_seed`` holds the shared form, so several
   idempotent seed writers may run at once.
4. The launcher path never reclaims in place: a failed rename reports
   ``ROTATION_DEFERRED`` and leaves the pinned log byte-identical.

The per-path in-process RLock still serializes threads. Run
``python -B scripts/checks/check_shiguan_shared_write_lock.py``.
"""

from __future__ import annotations

import importlib
import multiprocessing
import os
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


CONTRACT = "SHIGUAN_SHARED_WRITE_LOCK"


def _holder(path: str, shared: bool, ready: object, release: object,
            legacy: bool = False, crash: bool = False) -> None:
    from court_file_lock import file_lock
    if legacy:
        import msvcrt
        with Path(path).open("r+b", buffering=0) as handle:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            ready.set()
            if not release.wait(15):
                raise TimeoutError("CRT holder release timed out")
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        with file_lock(Path(path), shared=shared, timeout=5):
            ready.set()
            if crash:
                os._exit(17)
            if not release.wait(15):
                raise TimeoutError("OS holder release timed out")


def _overlap(path: Path, held_shared: bool, requested_shared: bool, *,
             held_legacy: bool = False, requested_legacy: bool = False) -> bool:
    from court_file_lock import file_lock
    context = multiprocessing.get_context("spawn")
    ready, release = context.Event(), context.Event()
    child = context.Process(target=_holder,
        args=(str(path), held_shared, ready, release, held_legacy))
    child.start()
    try:
        assert ready.wait(8), "child never acquired its lock"
        if requested_legacy:
            import msvcrt
            with path.open("r+b", buffering=0) as handle:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    admitted = False
                else:
                    admitted = True
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            try:
                with file_lock(path, shared=requested_shared, timeout=0.25, poll_interval=0.01):
                    admitted = True
            except TimeoutError:
                admitted = False
        assert child.is_alive(), "holder exited before the overlapping request"
        return admitted
    finally:
        release.set()
        child.join(8)
        if child.is_alive():
            child.terminate()
            child.join(5)
        assert child.exitcode == 0, child.exitcode
        with file_lock(path, timeout=2):
            pass  # Release, not just conflict, must work.


def main() -> int:
    failures: list[str] = []
    evidence: dict[str, object] = {}

    lock_module = importlib.import_module("court_file_lock")
    log_module = importlib.import_module("shiguan_service_log")
    paths_module = importlib.import_module("shiguan_paths")

    seed_source = Path(paths_module.__file__).read_text(encoding="utf-8")
    seed_shared = re.search(r"file_lock\(write_lock,\s*shared=True\)", seed_source) is not None
    if not seed_shared:
        failures.append("ensure_shared_seed_not_shared")
    evidence["ensure_shared_seed_shared"] = seed_shared

    log_source = Path(log_module.__file__).read_text(encoding="utf-8")
    launcher_defers = "allow_in_place=False" in log_source
    if not launcher_defers:
        failures.append("launcher_still_reclaims_in_place")
    if "ROTATION_DEFERRED" not in log_source:
        failures.append("rotation_deferred_action_missing")
    evidence["launcher_defers_in_place"] = launcher_defers

    with tempfile.TemporaryDirectory(prefix="fixture-shared-lock-") as raw:
        root = Path(raw)
        lock_path = root / "shared.lock"
        lock_path.write_bytes(b"\0")
        shared_overlap = _overlap(lock_path, True, True)
        shared_blocks_exclusive = not _overlap(lock_path, True, False)
        exclusive_blocks_shared = not _overlap(lock_path, False, True)
        exclusive_blocks_exclusive = not _overlap(lock_path, False, False)
        evidence["real_process_overlap"] = {
            "shared_shared": shared_overlap,
            "shared_exclusive_blocked": shared_blocks_exclusive,
            "exclusive_shared_blocked": exclusive_blocks_shared,
            "exclusive_exclusive_blocked": exclusive_blocks_exclusive,
        }
        if not all((shared_overlap, shared_blocks_exclusive,
                    exclusive_blocks_shared, exclusive_blocks_exclusive)):
            failures.append("cross_process_shared_exclusive_contract")
        if os.name == "nt":
            evidence["legacy_crt_interop"] = (
                not _overlap(lock_path, False, True, held_legacy=True)
                and not _overlap(lock_path, True, False, requested_legacy=True))
            if not evidence["legacy_crt_interop"]:
                failures.append("legacy_crt_exclusion")

        # A shared recursion must not silently become an exclusive lock.
        with lock_module.file_lock(lock_path, shared=True):
            try:
                with lock_module.file_lock(lock_path):
                    failures.append("shared_to_exclusive_fake_upgrade")
            except ValueError:
                pass
            with lock_module.file_lock(lock_path, shared=True):
                pass
        with lock_module.file_lock(lock_path):
            with lock_module.file_lock(lock_path, shared=True):
                pass
            with lock_module.file_lock(lock_path):
                pass
        try:
            with lock_module.file_lock(lock_path):
                raise RuntimeError("isolated body failure")
        except RuntimeError:
            pass
        with lock_module.file_lock(lock_path):
            pass
        evidence["reentrancy_and_exception_release"] = True

        context = multiprocessing.get_context("spawn")
        ready, release = context.Event(), context.Event()
        crashed = context.Process(target=_holder,
            args=(str(lock_path), True, ready, release, False, True))
        crashed.start()
        assert ready.wait(8), "shared crash holder never acquired"
        crashed.join(8)
        assert crashed.exitcode == 17, crashed.exitcode
        with lock_module.file_lock(lock_path, timeout=2):
            pass
        evidence["shared_crash_release"] = True

        # A non-conflict OS error must remain the OS error, not become a timeout.
        if os.name == "nt" and hasattr(lock_module, "_LOCK_FILE_EX"):
            with lock_path.open("r+b", buffering=0) as handle, \
                    patch.object(lock_module, "_LOCK_FILE_EX", return_value=0), \
                    patch.object(lock_module.ctypes, "get_last_error", return_value=5):
                try:
                    lock_module._try_os_lock(handle, shared=True)
                except OSError as exc:
                    assert exc.winerror == 5, exc
                else:
                    failures.append("non_conflict_error_swallowed")
            evidence["non_conflict_error_preserved"] = True

        # A shared holder is acquirable, and an exclusive request still excludes
        # it (serialization observed by ordering, not by wall-clock timing).
        with lock_module.file_lock(lock_path, timeout=2.0, shared=True):
            evidence["shared_acquired"] = True
        order: list[str] = []
        with lock_module.file_lock(lock_path, timeout=2.0, shared=True):
            order.append("shared")
        with lock_module.file_lock(lock_path, timeout=2.0):
            order.append("exclusive")
        evidence["shared_then_exclusive_order"] = order
        if order != ["shared", "exclusive"]:
            failures.append("shared_and_exclusive_not_serialized")

        # Launcher deferral: a pinned log must survive byte-identical.
        pinned = root / "pinned.log"
        original = b"z" * 4096
        pinned.write_bytes(original)
        real_replace = log_module.os.replace

        def _blocked(*_args: object, **_kwargs: object) -> None:
            raise PermissionError("fixture pin")

        try:
            log_module.os.replace = _blocked
            result = log_module.rotate_service_log(
                pinned, max_bytes=1024, allow_in_place=False
            )
        finally:
            log_module.os.replace = real_replace
        evidence["launcher_action"] = result.get("action")
        evidence["launcher_live_bytes"] = pinned.stat().st_size
        if result.get("action") != "ROTATION_DEFERRED":
            failures.append("launcher_action_not_deferred")
        if pinned.stat().st_size != len(original):
            failures.append("launcher_mutated_pinned_log")
        if not Path(str(pinned) + ".1").exists() and str(pinned) + ".1" in str(
            result.get("archive")
        ):
            failures.append("launcher_archived_pinned_log")

    failures = list(dict.fromkeys(failures))
    print(f"{CONTRACT}={'PASS' if not failures else 'FAIL'}")
    for item in failures:
        print(f"  failure: {item}")
    if not failures:
        print(f"  evidence: {evidence}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
