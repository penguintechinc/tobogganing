"""Coverage for hub_api.flags.__init__'s sys.path bootstrap guard.

By the time most tests import hub_api.flags, the repo root is already on
sys.path (inserted by an earlier import in the same session), so the `if str
not in sys.path` guard's insert() branch is never exercised. This test
removes the repo root from sys.path first, then reloads the module, to
exercise the insertion branch directly.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import hub_api.flags as flags_module


def test_bootstraps_repo_root_onto_sys_path_when_missing() -> None:
    """Reloading with repo_root absent from sys.path re-inserts it."""
    repo_root = str(Path(flags_module.__file__).parent.parent.parent)

    was_present = repo_root in sys.path
    if was_present:
        sys.path.remove(repo_root)

    try:
        assert repo_root not in sys.path
        reloaded = importlib.reload(flags_module)
        assert repo_root in sys.path
        assert callable(reloaded.feature_enabled)
    finally:
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        importlib.reload(flags_module)
