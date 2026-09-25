"""Cross-cutting security primitives shared across hub_api modules.

Currently: sliding-window rate limiting (rate_limit.py). Anything here must
be genuinely generic -- product/module-specific logic stays in its own
module (e.g. hub_api/modules/perftest_cluster/security/).
"""

from __future__ import annotations
