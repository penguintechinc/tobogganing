# Database Standards Quick Reference

## ⚠️ CRITICAL RULES

1. **PyDAL MANDATORY for ALL runtime operations** - no exceptions
2. **SQLAlchemy + Alembic for schema/migrations only** - never for runtime queries
3. **Support ALL databases by default**: PostgreSQL, MySQL, MariaDB Galera, SQLite
4. **DB_TYPE environment variable required** - maps to connection string prefix
5. **Connection pooling REQUIRED** - use PyDAL built-in pool_size configuration
6. **Thread-safe connections MANDATORY** - thread-local storage for multi-threaded apps
7. **Retry logic with exponential backoff** - handle database initialization delays
8. **MariaDB Galera special handling** - WSREP checks, short transactions, charset utf8mb4

---

## Database Support Matrix

| Database | DB_TYPE | Version | Default Port | Use Case |
|----------|---------|---------|--------------|----------|
| PostgreSQL | `postgresql` | **16.x** | 5432 | Production (primary) |
| MySQL | `mysql` | 8.0+ | 3306 | Production alternative |
| MariaDB Galera | `mysql` | 10.11+ | 3306 | HA clusters (special config) |
| SQLite | `sqlite` | 3.x | N/A | Development/lightweight |

---

## Dual-Library Architecture (Python)

### SQLAlchemy + Alembic
- **Purpose**: Schema definition and version-controlled migrations ONLY
- **When**: Application first-time setup
- **What**: Define tables, columns, relationships
- **Not for**: Runtime queries, data operations

### PyDAL
- **Purpose**: ALL runtime database operations
- **When**: Every request, transaction, query
- **What**: Queries, inserts, updates, deletes, transactions
- **Built-in**: Connection pooling, thread safety, retry logic

---

## Environment Variables

```bash
DB_TYPE=postgresql        # Database type
DB_HOST=localhost         # Database host
DB_PORT=5432             # Database port
DB_NAME=app_db           # Database name
DB_USER=app_user         # Database username
DB_PASS=app_pass         # Database password
DB_POOL_SIZE=10          # Connection pool size (default: 10)
DB_MAX_RETRIES=5         # Maximum connection retries (default: 5)
DB_RETRY_DELAY=5         # Retry delay in seconds (default: 5)
```

---

## PyDAL Connection Pattern

```python
from pydal import DAL

def get_db():
    db_type = os.getenv('DB_TYPE', 'postgresql')
    db_uri = f"{db_type}://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    db = DAL(
        db_uri,
        pool_size=int(os.getenv('DB_POOL_SIZE', '10')),
        migrate=True,
        check_reserved=['all'],
        lazy_tables=True
    )
    return db
```

---

## Thread-Safe Usage Pattern

**NEVER share DAL instance across threads. Use thread-local storage:**

```python
import threading

thread_local = threading.local()

def get_thread_db():
    if not hasattr(thread_local, 'db'):
        thread_local.db = DAL(db_uri, pool_size=10, migrate=False)
    return thread_local.db
```

**Flask pattern (automatic via g context):**

```python
from flask import g

def get_db():
    if 'db' not in g:
        g.db = DAL(db_uri, pool_size=10)
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db: db.close()
```

---

## MariaDB Galera Special Requirements

1. **Connection String**: Use `mysql://` (same as MySQL)
2. **Driver Args**: Set charset to utf8mb4
3. **WSREP Checks**: Verify `wsrep_ready` before critical writes
4. **Auto-Increment**: Configure `innodb_autoinc_lock_mode=2` for interleaved mode
5. **Transactions**: Keep short to avoid certification conflicts
6. **DDL Operations**: Plan during low-traffic periods (uses Total Order Isolation)

```python
# Galera-specific configuration
db = DAL(
    f"mysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    pool_size=10,
    driver_args={'charset': 'utf8mb4'}
)
```

---

## Connection Pooling & Retry Logic

```python
import time

def wait_for_database(max_retries=5, retry_delay=5):
    """Wait for DB with retry logic"""
    for attempt in range(max_retries):
        try:
            db = get_db()
            db.close()
            return True
        except Exception as e:
            print(f"Attempt {attempt+1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    return False

# Application startup
if not wait_for_database():
    sys.exit(1)
db = get_db()
```

---

## Concurrency Selection

| Workload | Approach | Libraries | Pool Size Formula |
|----------|----------|-----------|-------------------|
| I/O-bound (>100 concurrent) | Async | `asyncio`, `databases` | pool = concurrent / 2 |
| CPU-bound | Multi-processing | `multiprocessing` | pool = CPU cores |
| Mixed/Blocking I/O | Multi-threading | `threading`, `ThreadPoolExecutor` | pool = (2 × cores) + spindles |

---

## Go Database Requirements

When using Go for high-performance apps:
- **GORM** (preferred): Full ORM with PostgreSQL/MySQL support
- **sqlx** (alternative): Lightweight, more control
- Must support PostgreSQL, MySQL, SQLite
- Active maintenance required

```go
import (
    "gorm.io/driver/postgres"
    "gorm.io/driver/mysql"
    "gorm.io/gorm"
)

func initDB() (*gorm.DB, error) {
    dbType := os.Getenv("DB_TYPE")
    dsn := os.Getenv("DATABASE_URL")

    var dialector gorm.Dialector
    switch dbType {
    case "mysql":
        dialector = mysql.Open(dsn)
    default:
        dialector = postgres.Open(dsn)
    }

    return gorm.Open(dialector, &gorm.Config{})
}
```

---

## See Also

- `/home/penguin/code/project-template/docs/standards/DATABASE.md` - Full documentation
- Alembic migrations: https://alembic.sqlalchemy.org/
- PyDAL docs: https://py4web.io/en_US/chapter-12.html
