"""Compatibility shell (A+B layering) for scripts/services/archive_runtime_task.py.

Registered in check_unified_cli.COMPATIBILITY_SHELL_ENTRYPOINTS so it is not discovered twice; direct ``python scripts/archive_runtime_task.py`` calls keep working through this shell.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = str(Path(__file__).resolve().parent)
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from services import archive_runtime_task as _real  # noqa: E402

sys.modules[__name__] = _real

if __name__ == "__main__":
    _main = getattr(_real, "main", None)
    if callable(_main):
        sys.exit(_main())
    import runpy
    runpy.run_path(str(Path(__file__).resolve().parent / "services" / "archive_runtime_task.py"), run_name="__main__")
