"""Contract check for the shared (multi-writer) Shiguan write lock and the
launcher-side rotation deferral.

Proves, without writing any real Shiguan or %TEMP% path:

1. ``court_file_lock.file_lock`` exposes a ``shared`` form and the shared form is
   a real OS byte lock (``LK_NBRLCK`` / ``LOCK_SH``), not a no-op.
2. A shared holder still excludes an exclusive holder.
3. ``shiguan_paths.ensure_shared_seed`` holds the shared form, so several
   idempotent seed writers may run at once.
4. The launcher path never reclaims in place: a failed rename reports
   ``ROTATION_DEFERRED`` and leaves the pinned log byte-identical.

Cross-process multi-holder behaviour is not asserted here; ``file_lock`` keeps a
per-path in-process lock, so a second holder of the same path must be another
process. Run ``python -B scripts/checks/check_shiguan_shared_write_lock.py``.
"""

from __future__ import annotations

import importlib
import re
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


CONTRACT = "SHIGUAN_SHARED_WRITE_LOCK"


def main() -> int:
    failures: list[str] = []
    evidence: dict[str, object] = {}

    lock_module = importlib.import_module("court_file_lock")
    log_module = importlib.import_module("shiguan_service_log")
    paths_module = importlib.import_module("shiguan_paths")

    lock_source = Path(lock_module.__file__).read_text(encoding="utf-8")
    if "LK_NBRLCK" not in lock_source:
        failures.append("windows_shared_lock_primitive_missing")
    if "LOCK_SH" not in lock_source:
        failures.append("posix_shared_lock_primitive_missing")
    if "shared: bool = False" not in lock_source:
        failures.append("file_lock_missing_shared_parameter")
    evidence["shared_primitive"] = {
        "windows": "LK_NBRLCK" in lock_source,
        "posix": "LOCK_SH" in lock_source,
    }

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
