"""Compatibility shell (A+B layering) for scripts/services/serve_shiguan_tree.py.

Re-exports the real module via sys.modules so ``import serve_shiguan_tree``
(used by check_shiguan_concurrency / check_shiguan_peer_state_transaction) and
direct ``python scripts/serve_shiguan_tree.py`` invocations (web daemon) resolve
to the canonical implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = str(Path(__file__).resolve().parent)
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from services import serve_shiguan_tree as _real  # noqa: E402

sys.modules[__name__] = _real

if __name__ == "__main__":
    _real.main()
