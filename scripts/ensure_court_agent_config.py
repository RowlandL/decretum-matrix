"""Compatibility shell (A+B layering) for scripts/commands/ensure_court_agent_config.py.

Registered in check_unified_cli.COMPATIBILITY_SHELL_ENTRYPOINTS so it is not discovered twice; direct ``python scripts/ensure_court_agent_config.py`` calls keep working through this shell.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = str(Path(__file__).resolve().parent)
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from commands import ensure_court_agent_config as _real  # noqa: E402

sys.modules[__name__] = _real

if __name__ == "__main__":
    _main = getattr(_real, "main", None)
    if callable(_main):
        sys.exit(_main())
    import runpy
    runpy.run_path(str(Path(__file__).resolve().parent / "commands" / "ensure_court_agent_config.py"), run_name="__main__")
