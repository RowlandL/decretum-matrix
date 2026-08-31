"""Compatibility shell (A+B layering) for scripts/commands/query_shiguan_index.py.

Re-exports the real module via sys.modules so ``import query_shiguan_index``
(used by court_public_api / domain_ledger_api) and direct CLI invocation both
resolve to the canonical implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = str(Path(__file__).resolve().parent)
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from commands import query_shiguan_index as _real  # noqa: E402

sys.modules[__name__] = _real

if __name__ == "__main__":
    sys.exit(_real.main())
