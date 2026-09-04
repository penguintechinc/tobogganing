"""DNS resolver fleet-node service — P3 data-plane."""
import sys
from pathlib import Path

# Ensure proto modules are importable by adding repo root to path
# This allows 'from proto.netsvcs.v1 import ...' to work whether running
# from repo root or from within engines/netsvcs-dns directory
# __file__ = .../engines/netsvcs-dns/app/__init__.py
# Need to go up 3 levels to reach the repo root
_repo_root = Path(__file__).parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

__version__ = "0.1.0"
