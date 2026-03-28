"""Database initialization and configuration for Tobogganing Hub API.

Uses penguin-dal (AsyncDB via Quart extension) instead of PyDAL directly.
Schema is owned by SQLAlchemy / Alembic (see database/migrations/).
penguin-dal reflects the live schema at startup via AsyncDB.reflect().
"""

from __future__ import annotations

import os
import logging
from typing import Optional

from penguin_dal import AsyncDB
from penguin_dal.quart_ext import init_dal
from penguin_dal.quart_ext import get_db as _quart_get_db

logger = logging.getLogger(__name__)

# Module-level references kept for backwards-compat callers that do
# `from database import get_db, get_read_db, close_database`.
# The actual AsyncDB instances are managed by the Quart extension
# (stored in app.extensions["_penguin_dal"]).  These module globals
# are only used by non-request-context callers such as BackupManager
# and AnalyticsManager that hold a reference acquired during startup.

_db: Optional[AsyncDB] = None
_db_read: Optional[AsyncDB] = None


def get_database_uri() -> str:
    """Get primary database URI from environment variables."""
    db_type = os.getenv('DB_TYPE', 'mysql')

    if db_type == 'mysql':
        host = os.getenv('DB_HOST', 'localhost')
        port = os.getenv('DB_PORT', '3306')
        user = os.getenv('DB_USER', 'tobogganing')
        password = os.getenv('DB_PASSWORD', 'tobogganing')
        database = os.getenv('DB_NAME', 'tobogganing')

        uri = f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}"

        tls_params = []
        if os.getenv('DB_TLS_ENABLED', 'false').lower() == 'true':
            tls_params.append('ssl=true')

            if ssl_ca := os.getenv('DB_TLS_CA_CERT'):
                tls_params.append(f'ssl-ca={ssl_ca}')
            if ssl_cert := os.getenv('DB_TLS_CLIENT_CERT'):
                tls_params.append(f'ssl-cert={ssl_cert}')
            if ssl_key := os.getenv('DB_TLS_CLIENT_KEY'):
                tls_params.append(f'ssl-key={ssl_key}')

            ssl_verify = os.getenv('DB_TLS_VERIFY_MODE', 'VERIFY_CA')
            if ssl_verify in ['VERIFY_IDENTITY', 'VERIFY_CA', 'DISABLED']:
                tls_params.append(f'ssl-mode={ssl_verify}')

        conn_params = []
        if charset := os.getenv('DB_CHARSET', 'utf8mb4'):
            conn_params.append(f'charset={charset}')
        if collation := os.getenv('DB_COLLATION'):
            conn_params.append(f'collation={collation}')
        if timeout := os.getenv('DB_CONNECT_TIMEOUT'):
            conn_params.append(f'connect_timeout={timeout}')

        all_params = tls_params + conn_params
        if all_params:
            uri += '?' + '&'.join(all_params)

        return uri

    elif db_type == 'postgresql':
        host = os.getenv('DB_HOST', 'localhost')
        port = os.getenv('DB_PORT', '5432')
        user = os.getenv('DB_USER', 'tobogganing')
        password = os.getenv('DB_PASSWORD', 'tobogganing')
        database = os.getenv('DB_NAME', 'tobogganing')

        uri = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"

        tls_params = []
        if os.getenv('DB_TLS_ENABLED', 'false').lower() == 'true':
            ssl_mode = os.getenv('DB_TLS_VERIFY_MODE', 'require')
            tls_params.append(f'sslmode={ssl_mode}')

            if ssl_ca := os.getenv('DB_TLS_CA_CERT'):
                tls_params.append(f'sslrootcert={ssl_ca}')
            if ssl_cert := os.getenv('DB_TLS_CLIENT_CERT'):
                tls_params.append(f'sslcert={ssl_cert}')
            if ssl_key := os.getenv('DB_TLS_CLIENT_KEY'):
                tls_params.append(f'sslkey={ssl_key}')

        conn_params = []
        if timeout := os.getenv('DB_CONNECT_TIMEOUT'):
            conn_params.append(f'connect_timeout={timeout}')

        all_params = tls_params + conn_params
        if all_params:
            uri += '?' + '&'.join(all_params)

        return uri

    elif db_type == 'sqlite':
        db_path = os.getenv('DB_PATH', '/data/tobogganing.db')
        return f"sqlite+aiosqlite://{db_path}"

    else:
        raise ValueError(f"Unsupported database type: {db_type}")


def get_read_replica_uri() -> Optional[str]:
    """Get read replica database URI if configured."""
    if not os.getenv('DB_READ_REPLICA_ENABLED', 'false').lower() == 'true':
        return None

    db_type = os.getenv('DB_TYPE', 'mysql')

    if db_type == 'mysql':
        host = os.getenv('DB_READ_HOST', os.getenv('DB_HOST', 'localhost'))
        port = os.getenv('DB_READ_PORT', os.getenv('DB_PORT', '3306'))
        user = os.getenv('DB_READ_USER', os.getenv('DB_USER', 'tobogganing'))
        password = os.getenv('DB_READ_PASSWORD', os.getenv('DB_PASSWORD', 'tobogganing'))
        database = os.getenv('DB_READ_NAME', os.getenv('DB_NAME', 'tobogganing'))

        return f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}"

    elif db_type == 'postgresql':
        host = os.getenv('DB_READ_HOST', os.getenv('DB_HOST', 'localhost'))
        port = os.getenv('DB_READ_PORT', os.getenv('DB_PORT', '5432'))
        user = os.getenv('DB_READ_USER', os.getenv('DB_USER', 'tobogganing'))
        password = os.getenv('DB_READ_PASSWORD', os.getenv('DB_PASSWORD', 'tobogganing'))
        database = os.getenv('DB_READ_NAME', os.getenv('DB_NAME', 'tobogganing'))

        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"

    # SQLite doesn't support read replicas
    return None


def initialize_database(app: object) -> None:
    """Initialize penguin-dal on a Quart application.

    Replaces the old PyDAL-based initialize_database().  The Quart
    extension registers before_serving / after_serving hooks that
    call AsyncDB.reflect() and AsyncDB.close() automatically.

    Schema must already exist (created by Alembic migrations before
    the service starts).  penguin-dal discovers all tables via
    SQLAlchemy MetaData.reflect() at startup.

    Args:
        app: The Quart application instance.
    """
    global _db, _db_read

    primary_uri = get_database_uri()
    logger.info(
        "Registering penguin-dal (AsyncDB) on Quart app: %s",
        primary_uri.split('@')[0] + '@***',
    )

    pool_size = int(os.getenv('DB_POOL_SIZE', '10'))
    init_dal(app, uri=primary_uri, pool_size=pool_size)

    # Stash a bare AsyncDB reference for non-request-context callers.
    # Note: reflect() has NOT been called yet at this point — it runs
    # inside the before_serving hook registered by init_dal().
    _db = AsyncDB(uri=primary_uri, pool_size=pool_size)

    read_replica_uri = get_read_replica_uri()
    if read_replica_uri:
        logger.info(
            "Configuring read replica: %s",
            read_replica_uri.split('@')[0] + '@***',
        )
        read_pool_size = int(os.getenv('DB_READ_POOL_SIZE', '5'))
        _db_read = AsyncDB(uri=read_replica_uri, pool_size=read_pool_size)
    else:
        _db_read = _db
        logger.info("No read replica configured, using primary database for reads")


def get_db() -> AsyncDB:
    """Get the primary AsyncDB instance for write operations.

    For code running inside a Quart request context, prefer using
    ``penguin_dal.quart_ext.get_db()`` which returns the app-managed
    instance.  This function is provided for non-request callers
    (BackupManager, AnalyticsManager, etc.) that hold a startup-time
    reference.
    """
    if _db is None:
        raise RuntimeError("Database not initialized. Call initialize_database(app) first.")
    return _db


def get_read_db() -> AsyncDB:
    """Get the read AsyncDB instance (read replica if available, otherwise primary)."""
    if _db_read is None:
        raise RuntimeError("Database not initialized. Call initialize_database(app) first.")
    return _db_read


async def close_database() -> None:
    """Close database connections.

    The Quart extension also calls close() via after_serving, so this
    is a belt-and-suspenders shutdown for the module-level instances.
    """
    global _db, _db_read

    if _db is not None:
        await _db.close()
        _db = None

    if _db_read is not None and _db_read is not _db:
        await _db_read.close()
    _db_read = None

    logger.info("Database connections closed")
