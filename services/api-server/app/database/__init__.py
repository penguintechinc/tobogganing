"""Database initialization and configuration for Flask API Server."""

import os
import logging
from typing import Optional
from pydal import DAL

from .models import define_schema

logger = logging.getLogger(__name__)

# Global database instances
db: Optional[DAL] = None
db_read: Optional[DAL] = None


def get_database_uri() -> str:
    """Get primary database URI from environment variables."""
    db_type = os.getenv('DB_TYPE', 'postgresql')

    if db_type == 'mysql':
        host = os.getenv('DB_HOST', 'localhost')
        port = os.getenv('DB_PORT', '3306')
        user = os.getenv('DB_USER', 'sasewaddle')
        password = os.getenv('DB_PASSWORD', 'sasewaddle')
        database = os.getenv('DB_NAME', 'sasewaddle')

        uri = f"mysql://{user}:{password}@{host}:{port}/{database}"

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
        user = os.getenv('DB_USER', 'sasewaddle')
        password = os.getenv('DB_PASSWORD', 'sasewaddle')
        database = os.getenv('DB_NAME', 'sasewaddle')

        uri = f"postgresql://{user}:{password}@{host}:{port}/{database}"

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
        db_path = os.getenv('DB_PATH', '/data/sasewaddle.db')
        return f"sqlite://{db_path}"

    else:
        raise ValueError(f"Unsupported database type: {db_type}")


def get_read_replica_uri() -> Optional[str]:
    """Get read replica database URI if configured."""
    if not os.getenv('DB_READ_REPLICA_ENABLED', 'false').lower() == 'true':
        return None

    db_type = os.getenv('DB_TYPE', 'postgresql')

    if db_type == 'mysql':
        host = os.getenv('DB_READ_HOST', os.getenv('DB_HOST', 'localhost'))
        port = os.getenv('DB_READ_PORT', os.getenv('DB_PORT', '3306'))
        user = os.getenv('DB_READ_USER', os.getenv('DB_USER', 'sasewaddle'))
        password = os.getenv('DB_READ_PASSWORD', os.getenv('DB_PASSWORD', 'sasewaddle'))
        database = os.getenv('DB_READ_NAME', os.getenv('DB_NAME', 'sasewaddle'))

        return f"mysql://{user}:{password}@{host}:{port}/{database}"

    elif db_type == 'postgresql':
        host = os.getenv('DB_READ_HOST', os.getenv('DB_HOST', 'localhost'))
        port = os.getenv('DB_READ_PORT', os.getenv('DB_PORT', '5432'))
        user = os.getenv('DB_READ_USER', os.getenv('DB_USER', 'sasewaddle'))
        password = os.getenv('DB_READ_PASSWORD', os.getenv('DB_PASSWORD', 'sasewaddle'))
        database = os.getenv('DB_READ_NAME', os.getenv('DB_NAME', 'sasewaddle'))

        return f"postgresql://{user}:{password}@{host}:{port}/{database}"

    return None


def initialize_database() -> None:
    """Initialize the database connections and schema."""
    global db, db_read

    try:
        primary_uri = get_database_uri()
        logger.info(f"Connecting to primary database: {primary_uri.split('@')[0]}@***")

        db = DAL(
            primary_uri,
            pool_size=int(os.getenv('DB_POOL_SIZE', '10')),
            migrate=True,
            fake_migrate=False,
            check_reserved=['mysql', 'postgresql'],
            lazy_tables=True
        )

        read_replica_uri = get_read_replica_uri()
        if read_replica_uri:
            logger.info(f"Connecting to read replica: {read_replica_uri.split('@')[0]}@***")
            db_read = DAL(
                read_replica_uri,
                pool_size=int(os.getenv('DB_READ_POOL_SIZE', '5')),
                migrate=False,
                fake_migrate=False,
                check_reserved=['mysql', 'postgresql'],
                lazy_tables=True
            )
        else:
            db_read = db
            logger.info("No read replica configured, using primary database for reads")

        define_schema(db)

        db.commit()
        if db_read != db:
            db_read.commit()

        logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


def get_db() -> DAL:
    """Get the primary database instance for write operations."""
    if db is None:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    return db


def get_read_db() -> DAL:
    """Get the read database instance (read replica if available, otherwise primary)."""
    if db_read is None:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    return db_read


def close_database() -> None:
    """Close database connections."""
    global db, db_read

    if db:
        db.close()
        db = None

    if db_read and db_read != db:
        db_read.close()
    db_read = None

    logger.info("Database connections closed")
