"""Database module providing penguin-dal integration."""
from __future__ import annotations

try:
    from penguin_dal.quart_ext import init_dal, get_db
except ImportError:
    # Allow tests to run without penguin-dal installed
    init_dal = None  # type: ignore[assignment]
    get_db = None  # type: ignore[assignment]

__all__ = ["init_dal", "get_db"]
