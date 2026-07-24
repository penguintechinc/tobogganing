"""Feature flag integration for Tobogganing Core."""
from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to sys.path for imports if needed
repo_root = Path(__file__).parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from shared.licensing.entitlements import feature_enabled

__all__ = ["feature_enabled"]
