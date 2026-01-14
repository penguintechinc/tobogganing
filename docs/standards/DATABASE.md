# Database Standards

Part of [Development Standards](../STANDARDS.md)

## Supported Databases

ALL applications MUST support the following databases by default:

| Database | DB_TYPE Value | Use Case | Notes |
|----------|---------------|----------|-------|
| **PostgreSQL** | `postgresql` | Production (default) | Primary database for all deployments |
| **MySQL** | `mysql` | Production alternative | Full support for MySQL 8.0+ |
| **MariaDB Galera** | `mysql` | High-availability clusters | Requires special handling (see below) |
| **SQLite** | `sqlite` | Development/lightweight | File-based, no server required |

## Dual-Library Architecture (Python) - MANDATORY

ALL Python applications MUST use a dual-library approach for database access:

1. **SQLAlchemy** - Database Initialization ONLY
   - Create database schemas and initial structure
   - One-time setup operations
   - NOT used for runtime queries or migrations

2. **PyDAL** - Runtime Operations and Migrations
   - ALL runtime database queries and operations
   - Schema migrations via `migrate=True`
   - Connection pooling and thread-safe access

**Why This Approach:**
- SQLAlchemy provides robust schema creation and DDL generation
- PyDAL offers simpler runtime query syntax and automatic migrations
- Separation of concerns between initialization and runtime
- Better compatibility with MariaDB Galera cluster requirements

### SQLAlchemy Initialization Example

```python
"""Database initialization using SQLAlchemy - RUN ONCE during setup"""
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.schema import CreateTable
import os

def get_sqlalchemy_engine():
    """Create SQLAlchemy engine for initialization only"""
    db_type = os.getenv('DB_TYPE', 'postgresql')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'app_db')
    db_user = os.getenv('DB_USER', 'app_user')
    db_pass = os.getenv('DB_PASS', 'app_pass')

    # Map DB_TYPE to SQLAlchemy dialect
    dialect_map = {
        'postgresql': 'postgresql',
        'mysql': 'mysql+pymysql',
        'sqlite': 'sqlite',
    }
    dialect = dialect_map.get(db_type, 'postgresql')

    if db_type == 'sqlite':
        db_url = f"sqlite:///{db_name}.db"
    else:
        db_url = f"{dialect}://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    return create_engine(db_url)

def initialize_database():
    """One-time database schema initialization"""
    engine = get_sqlalchemy_engine()
    metadata = MetaData()

    # Define tables for initial schema creation
    users = Table('auth_user', metadata,
        Column('id', Integer, primary_key=True),
        Column('email', String(255), unique=True, nullable=False),
        Column('password', String(255)),
        Column('active', Boolean, default=True),
        Column('fs_uniquifier', String(64), unique=True),
        Column('confirmed_at', DateTime),
    )

    roles = Table('auth_role', metadata,
        Column('id', Integer, primary_key=True),
        Column('name', String(80), unique=True),
        Column('description', String(255)),
    )

    # Create all tables
    metadata.create_all(engine)
    print("Database schema initialized via SQLAlchemy")

# Run during application first-time setup ONLY
if __name__ == '__main__':
    initialize_database()
```

### PyDAL Runtime Example

```python
"""Runtime database operations using PyDAL"""
from pydal import DAL, Field
import os

def get_pydal_connection():
    """Get PyDAL connection for runtime operations"""
    db_type = os.getenv('DB_TYPE', 'postgresql')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'app_db')
    db_user = os.getenv('DB_USER', 'app_user')
    db_pass = os.getenv('DB_PASS', 'app_pass')
    pool_size = int(os.getenv('DB_POOL_SIZE', '10'))

    if db_type == 'sqlite':
        db_uri = f"sqlite://{db_name}.db"
    else:
        db_uri = f"{db_type}://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    db = DAL(
        db_uri,
        pool_size=pool_size,
        migrate=True,  # PyDAL handles all migrations
        check_reserved=['all'],
        lazy_tables=True
    )

    # Define tables for PyDAL (mirrors SQLAlchemy schema)
    db.define_table('auth_user',
        Field('email', 'string', unique=True, notnull=True),
        Field('password', 'password'),
        Field('active', 'boolean', default=True),
        Field('fs_uniquifier', 'string', unique=True),
        Field('confirmed_at', 'datetime'),
        migrate=True
    )

    return db

# Runtime usage
db = get_pydal_connection()
# Query example: db(db.auth_user.active == True).select()
```

## MariaDB Galera Cluster Support

MariaDB Galera requires special handling for cluster-aware operations:

```python
"""MariaDB Galera-specific configuration"""
import os

def get_galera_pydal_connection():
    """PyDAL connection with Galera-specific settings"""
    db_uri = f"mysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

    db = DAL(
        db_uri,
        pool_size=int(os.getenv('DB_POOL_SIZE', '10')),
        migrate=True,
        check_reserved=['all'],
        lazy_tables=True,
        # Galera-specific: Use ROW format for binary logging
        driver_args={'charset': 'utf8mb4'}
    )

    return db

# Galera-specific considerations:
# 1. AUTO_INCREMENT: Use larger increment steps for multi-node writes
# 2. WSREP: Check wsrep_ready before critical operations
# 3. Transactions: Avoid long-running transactions (certification conflicts)
# 4. DDL: Schema changes replicate as TOI (Total Order Isolation)
```

**Galera Requirements:**
- Use `innodb_autoinc_lock_mode=2` for interleaved auto-increment
- Check `wsrep_ready` status before writes
- Keep transactions short to avoid certification failures
- Plan DDL operations during low-traffic periods

## Async and Multi-Threading Requirements

Database operations MUST use appropriate concurrency patterns based on workload characteristics:

### Decision Matrix

| Workload Type | Recommended Approach | Libraries | Use Case |
|---------------|---------------------|-----------|----------|
| **I/O-bound (network, disk)** | Async/await | `asyncio`, `aiohttp`, `databases` | Web APIs, external service calls |
| **CPU-bound** | Multi-processing | `multiprocessing`, `concurrent.futures` | Data processing, calculations |
| **Mixed I/O with blocking** | Multi-threading | `threading`, `concurrent.futures` | Legacy integrations, file I/O |
| **High-concurrency web** | Async + thread pool | `asyncio` + `ThreadPoolExecutor` | Flask/async hybrid patterns |

### Async Database Operations (Recommended for Web APIs)

```python
"""Async database operations for high-concurrency scenarios"""
import asyncio
from databases import Database
import os

# Async database connection (use alongside PyDAL for specific async needs)
async def get_async_db():
    """Get async database connection for I/O-bound operations"""
    db_type = os.getenv('DB_TYPE', 'postgresql')
    db_url = f"{db_type}://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

    database = Database(db_url)
    await database.connect()
    return database

async def fetch_users_async(database: Database):
    """Example async query - better for high-concurrency web requests"""
    query = "SELECT * FROM auth_user WHERE active = :active"
    return await database.fetch_all(query=query, values={"active": True})

# Usage in async context
async def main():
    db = await get_async_db()
    users = await fetch_users_async(db)
    await db.disconnect()
```

### Multi-Threading for Blocking Operations

```python
"""Thread-safe database operations for blocking I/O"""
import threading
from concurrent.futures import ThreadPoolExecutor
from pydal import DAL, Field

# Thread-local storage for DAL instances
thread_local = threading.local()

def get_thread_db():
    """Get thread-local PyDAL connection"""
    if not hasattr(thread_local, 'db'):
        db_uri = f"{os.getenv('DB_TYPE')}://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        thread_local.db = DAL(db_uri, pool_size=5, migrate=False)
    return thread_local.db

def process_user(user_id: int):
    """Process user in separate thread"""
    db = get_thread_db()
    user = db(db.auth_user.id == user_id).select().first()
    # Process user...
    return user

# Parallel processing with thread pool
def process_users_parallel(user_ids: list[int], max_workers: int = 10):
    """Process multiple users in parallel threads"""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_user, user_ids))
    return results
```

### Flask Async Hybrid Pattern

```python
"""Flask with async database operations"""
from flask import Flask, g
import asyncio
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=20)

def run_async(coro):
    """Run async coroutine in thread pool for Flask compatibility"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route('/users')
def get_users():
    """Endpoint using async database operations"""
    async def fetch():
        db = await get_async_db()
        users = await fetch_users_async(db)
        await db.disconnect()
        return users

    # Run async operation in thread pool
    future = executor.submit(run_async, fetch())
    users = future.result(timeout=30)
    return {"users": users}
```

### Performance Guidelines

1. **Choose async when:**
   - Handling >100 concurrent requests
   - Operations are primarily network I/O (database, HTTP calls)
   - Low latency is critical (<100ms response time)

2. **Choose multi-threading when:**
   - Integrating with blocking libraries (legacy code)
   - File system operations
   - Moderate concurrency needs (10-100 concurrent operations)

3. **Choose multi-processing when:**
   - CPU-intensive calculations
   - Data transformation pipelines
   - Batch processing jobs

4. **Connection Pool Sizing:**
   - Async: Pool size = expected concurrent requests / 2
   - Threading: Pool size = number of worker threads + buffer
   - Rule of thumb: `pool_size = (2 * CPU_cores) + disk_spindles`

## Go Database Requirements

When using Go for high-performance applications, MUST use a DAL supporting PostgreSQL and MySQL:

**Recommended Options:**
1. **GORM** (Preferred)
   - Full-featured ORM
   - Supports PostgreSQL, MySQL, SQLite, SQL Server
   - Active maintenance and large community
   - Auto migrations and associations

2. **sqlx** (Alternative)
   - Lightweight extension of database/sql
   - Supports PostgreSQL, MySQL, SQLite
   - More control, less abstraction
   - Good for performance-critical scenarios

**Example GORM Implementation:**
```go
package main

import (
    "os"
    "gorm.io/driver/postgres"
    "gorm.io/driver/mysql"
    "gorm.io/gorm"
)

func initDB() (*gorm.DB, error) {
    dbType := os.Getenv("DB_TYPE") // "postgres" or "mysql"
    dsn := os.Getenv("DATABASE_URL")

    var dialector gorm.Dialector
    switch dbType {
    case "mysql":
        dialector = mysql.Open(dsn)
    default: // postgres
        dialector = postgres.Open(dsn)
    }

    db, err := gorm.Open(dialector, &gorm.Config{})
    return db, err
}
```

## Environment Variables

Applications MUST accept these Docker environment variables:
- `DB_TYPE`: Database type (postgresql, mysql, sqlite, mssql, oracle, etc.)
- `DB_HOST`: Database host/IP address
- `DB_PORT`: Database port (default depends on DB_TYPE)
- `DB_NAME`: Database name
- `DB_USER`: Database username
- `DB_PASS`: Database password
- `DB_POOL_SIZE`: Connection pool size (default: 10)
- `DB_MAX_RETRIES`: Maximum connection retry attempts (default: 5)
- `DB_RETRY_DELAY`: Delay between retry attempts in seconds (default: 5)

## Database Connection Requirements

1. **Wait for Database Initialization**: Application MUST wait for database to be ready
   - Implement retry logic with exponential backoff
   - Maximum retry attempts configurable via `DB_MAX_RETRIES`
   - Log each connection attempt for debugging
   - Fail gracefully with clear error messages

2. **Connection Pooling**: MUST use PyDAL's built-in connection pooling
   - Configure pool size via `DB_POOL_SIZE` environment variable
   - Implement proper connection lifecycle management
   - Handle connection timeouts and stale connections
   - Monitor pool utilization via metrics

3. **Database URI Construction**: Build connection string from environment variables
   ```python
   db_uri = f"{DB_TYPE}://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
   ```

## Implementation Pattern

```python
import os
import time
from pydal import DAL, Field

def wait_for_database(max_retries=5, retry_delay=5):
    """Wait for database to be available with retry logic"""
    retries = 0
    while retries < max_retries:
        try:
            db = get_db_connection(test=True)
            db.close()
            print(f"Database connection successful")
            return True
        except Exception as e:
            retries += 1
            print(f"Database connection attempt {retries}/{max_retries} failed: {e}")
            if retries < max_retries:
                time.sleep(retry_delay)
    return False

def get_db_connection():
    """Initialize PyDAL database connection with pooling"""
    db_type = os.getenv('DB_TYPE', 'postgresql')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'app_db')
    db_user = os.getenv('DB_USER', 'app_user')
    db_pass = os.getenv('DB_PASS', 'app_pass')
    pool_size = int(os.getenv('DB_POOL_SIZE', '10'))

    db_uri = f"{db_type}://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    db = DAL(
        db_uri,
        pool_size=pool_size,
        migrate_enabled=True,
        check_reserved=['all'],
        lazy_tables=True
    )

    return db

# Application startup
if __name__ == '__main__':
    max_retries = int(os.getenv('DB_MAX_RETRIES', '5'))
    retry_delay = int(os.getenv('DB_RETRY_DELAY', '5'))

    if not wait_for_database(max_retries, retry_delay):
        print("Failed to connect to database after maximum retries")
        sys.exit(1)

    db = get_db_connection()
    # Continue with application initialization...
```

## Thread Safety Requirements

**PyDAL MUST be used in a thread-safe manner:**

1. **Thread-local connections**: Each thread MUST have its own DAL instance
   - NEVER share a single DAL instance across multiple threads
   - Use thread-local storage (threading.local()) for per-thread DAL instances
   - Connection pooling handles multi-threaded access automatically

2. **Implementation Pattern for Threading:**
   ```python
   import threading
   from pydal import DAL

   # Thread-local storage for DAL instances
   thread_local = threading.local()

   def get_thread_db():
       """Get thread-local database connection"""
       if not hasattr(thread_local, 'db'):
           thread_local.db = DAL(
               db_uri,
               pool_size=10,
               migrate_enabled=True,
               check_reserved=['all'],
               lazy_tables=True
           )
       return thread_local.db

   # Usage in threaded context
   def worker_function():
       db = get_thread_db()  # Each thread gets its own connection
       # Perform database operations...
   ```

3. **Flask/WSGI Applications**: Flask already handles thread-local contexts
   ```python
   from flask import Flask, g

   app = Flask(__name__)

   def get_db():
       """Get database connection for current request context"""
       if 'db' not in g:
           g.db = DAL(db_uri, pool_size=10)
       return g.db

   @app.teardown_appcontext
   def close_db(error):
       """Close database connection after request"""
       db = g.pop('db', None)
       if db is not None:
           db.close()
   ```

4. **Async/Threading Considerations**:
   - When using threading.Thread, ensure each thread creates its own DAL instance
   - When using asyncio, use async-compatible database drivers if available
   - Connection pooling is thread-safe and manages concurrent access automatically
   - NEVER pass DAL instances between threads

5. **Multi-process Safety**:
   - Each process MUST create its own DAL instance
   - Connection pool is per-process, not shared across processes
