"""Alembic environment configuration for Tobogganing Hub API.

Uses SQLAlchemy models defined in database/models.py as the MetaData
source for autogenerate support.

Run migrations:
    cd services/hub-api
    alembic -c database/migrations/alembic.ini upgrade head

Offline (SQL script) generation:
    alembic -c database/migrations/alembic.ini upgrade head --sql

Create a new migration:
    alembic -c database/migrations/alembic.ini revision --autogenerate -m "description"
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the hub-api package importable when running Alembic from the
# services/hub-api/ directory.
_HERE = Path(__file__).resolve().parent.parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from database.models import metadata as target_metadata  # noqa: E402

# Alembic Config object — gives access to the .ini file values.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Database URI resolution
# ---------------------------------------------------------------------------

def _get_sync_uri() -> str:
    """Return a sync SQLAlchemy URI for Alembic (psycopg2 / pymysql / sqlite).

    Alembic runs migrations offline or via a sync engine, so we map the
    async driver prefixes (asyncpg, aiomysql) back to their sync equivalents.
    """
    db_type = os.getenv("DB_TYPE", "mysql")

    if db_type == "mysql":
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "3306")
        user = os.getenv("DB_USER", "tobogganing")
        password = os.getenv("DB_PASSWORD", "tobogganing")
        database = os.getenv("DB_NAME", "tobogganing")
        charset = os.getenv("DB_CHARSET", "utf8mb4")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset={charset}"

    elif db_type == "postgresql":
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        user = os.getenv("DB_USER", "tobogganing")
        password = os.getenv("DB_PASSWORD", "tobogganing")
        database = os.getenv("DB_NAME", "tobogganing")
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"

    elif db_type == "sqlite":
        db_path = os.getenv("DB_PATH", "/data/tobogganing.db")
        return f"sqlite:///{db_path}"

    else:
        raise ValueError(f"Unsupported DB_TYPE: {db_type}")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with a URL and emits SQL to stdout without
    establishing a real database connection.
    """
    url = _get_sync_uri()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using a live DB connection."""
    url = _get_sync_uri()

    # Override the URL from alembic.ini (which may be empty/placeholder)
    cfg_section = config.get_section(config.config_ini_section) or {}
    cfg_section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        cfg_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
