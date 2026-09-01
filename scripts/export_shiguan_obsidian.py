"""Compatibility shell (A+B layering) for scripts/services/export_shiguan_obsidian.py.

Registered in check_unified_cli.COMPATIBILITY_SHELL_ENTRYPOINTS so it is not discovered twice; direct ``python scripts/export_shiguan_obsidian.py`` calls keep working.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = str(Path(__file__).resolve().parent)
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from services import export_shiguan_obsidian as _real  # noqa: E402

sys.modules[__name__] = _real

if __name__ == "__main__":
    sys.exit(_real.main())
