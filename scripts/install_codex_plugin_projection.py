"""Compatibility shell (A+B layering) for scripts/commands/install_codex_plugin_projection.py.

Registered in check_unified_cli.COMPATIBILITY_SHELL_ENTRYPOINTS so it is not discovered twice; direct ``python scripts/install_codex_plugin_projection.py`` calls keep working.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = str(Path(__file__).resolve().parent)
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from commands import install_codex_plugin_projection as _real  # noqa: E402

sys.modules[__name__] = _real

if __name__ == "__main__":
    sys.exit(_real.main())
