"""Test-collection setup for the standalone py_libs package.

py_libs is published/consumed as a top-level import (`import py_libs...`),
not via the `shared.py_libs...` namespace path — its own __init__.py does
absolute imports (`from py_libs.validation import ...`) that only resolve
when the package root is on sys.path. Add it here so tests can be run from
the monorepo worktree root without a separate editable install.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PY_LIBS_ROOT = Path(__file__).resolve().parent.parent

if str(_PY_LIBS_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_LIBS_ROOT))
