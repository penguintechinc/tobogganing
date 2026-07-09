"""Database session and engine creation helpers for Alembic."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from core.db.base import Base, metadata

if TYPE_CHECKING:
    from core.config import Config


def create_engine_for_uri(db_uri: str, pool_size: int = 10) -> Engine:
    """Create a SQLAlchemy engine for the given database URI.

    Args:
        db_uri: Database connection URI.
        pool_size: Connection pool size.

    Returns:
        Configured SQLAlchemy engine.
    """
    return create_engine(
        db_uri,
        poolclass=None,  # Alembic migration doesn't use connection pooling
        echo=False,
    )


def get_metadata() -> Any:  # type: ignore[name-defined]
    """Get the metadata object for Alembic.

    Returns:
        SQLAlchemy MetaData object.
    """
    return metadata


__all__ = ["create_engine_for_uri", "get_metadata", "Base", "metadata"]
