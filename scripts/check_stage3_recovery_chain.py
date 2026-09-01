"""Compatibility shell (A+B layering) for scripts/checks/check_stage3_recovery_chain.py.

Registered in check_unified_cli.COMPATIBILITY_SHELL_ENTRYPOINTS so it is not discovered as a second entrypoint; direct ``python scripts/check_stage3_recovery_chain.py`` calls keep working through this shell.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = str(Path(__file__).resolve().parent)
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from checks import check_stage3_recovery_chain as _real  # noqa: E402

sys.modules[__name__] = _real

if __name__ == "__main__":
    sys.exit(_real.main())
