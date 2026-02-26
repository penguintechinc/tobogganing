🗄️ Database Guide - Your Data's New Home
==========================================

Part of [Development Standards](../STANDARDS.md)

Welcome to the database standards! This guide explains how to set up, manage, and query data safely and efficiently. Think of databases as libraries—they organize your information so you can find and update it quickly.

## What Databases Do We Support?

Your application speaks the language of **four databases**. Pick one to start, and your code will work with the rest:

| Database | Identifier | Version | Best For | Emoji |
|----------|-----------|---------|----------|-------|
| **PostgreSQL** | `postgresql` | **16.x** (standard) | Production, real apps | ⭐⭐⭐⭐⭐ |
| **MySQL** | `mysql` | 8.0+ | Production alternative | ⭐⭐⭐⭐ |
| **MariaDB Galera** | `mysql` | 10.11+ | High-availability clusters | ⭐⭐⭐⭐⭐ |
| **SQLite** | `sqlite` | 3.x | Development, testing | ⭐⭐⭐ |

---

## The Secret Sauce: Two Libraries (Not One!)

Here's the magic trick: we use **two different libraries** working together. It sounds odd, but trust us—it's brilliant.

### The Analogy 🎭

Think of a restaurant kitchen:
- **SQLAlchemy** = Head chef who designs the kitchen layout and equipment (schemas, tables, structure)
- **PyDAL** = Line cooks who prep and serve food every day (queries, operations, data handling)

The head chef designs once. The line cooks execute thousands of times. Both need to see the same kitchen design, but they have different jobs.

### Why Two Libraries? (The Real Reasons)

✅ **SQLAlchemy + Alembic** handles:
- Defining your database structure (schemas, tables, columns)
- Creating migrations (versioned changes to your database)
- Type-safe schema definitions
- One-time setup tasks

✅ **PyDAL** handles:
- Day-to-day queries (SELECT, INSERT, UPDATE, DELETE)
- Connection pooling (reusing connections efficiently)
- Thread-safe access (safe for multiple requests)
- Runtime operations

**Result?** Clean separation, fewer bugs, easier maintenance.

---

## Step-by-Step: Set Up Your Database

### Step 1: Choose Your Database

Pick one from the table above. For development, SQLite is easiest. For production, use PostgreSQL.

### Step 2: Define Your Schema (SQLAlchemy)

This runs **once** during initial setup:

```python
"""Database initialization - Run ONCE during setup"""
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Boolean, DateTime
import os

def initialize_database():
    """Create tables in your database"""
    db_type = os.getenv('DB_TYPE', 'postgresql')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'app_db')
    db_user = os.getenv('DB_USER', 'app_user')
    db_pass = os.getenv('DB_PASS', 'app_pass')

    # Build the database URL
    if db_type == 'sqlite':
        db_url = f"sqlite:///{db_name}.db"
    else:
        dialect_map = {
            'postgresql': 'postgresql',
            'mysql': 'mysql+pymysql',
        }
        dialect = dialect_map.get(db_type, 'postgresql')
        db_url = f"{dialect}://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    # Create engine and schema
    engine = create_engine(db_url)
    metadata = MetaData()

    # Define your tables
    users_table = Table('auth_user', metadata,
        Column('id', Integer, primary_key=True),
        Column('email', String(255), unique=True, nullable=False),
        Column('password', String(255)),
        Column('active', Boolean, default=True),
        Column('fs_uniquifier', String(64), unique=True),
        Column('confirmed_at', DateTime),
    )

    # Create all tables
    metadata.create_all(engine)
    print("✅ Database schema created!")

# Run this ONCE when setting up
if __name__ == '__main__':
    initialize_database()
```

💡 **Tip:** Run this once, then move on. You don't need this code in your daily application.

### Step 3: Query Your Data (PyDAL)

This is what your app does **every single day**:

```python
"""Runtime database operations - Use this in your app"""
from pydal import DAL, Field
import os

def get_db_connection():
    """Connect to the database for queries"""
    db_type = os.getenv('DB_TYPE', 'postgresql')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'app_db')
    db_user = os.getenv('DB_USER', 'app_user')
    db_pass = os.getenv('DB_PASS', 'app_pass')
    pool_size = int(os.getenv('DB_POOL_SIZE', '10'))

    # Build connection string
    if db_type == 'sqlite':
        db_uri = f"sqlite://{db_name}.db"
    else:
        db_uri = f"{db_type}://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    # Connect with connection pooling
    db = DAL(
        db_uri,
        pool_size=pool_size,     # Reuse connections
        migrate=True,             # Auto-create tables if missing
        check_reserved=['all'],
        lazy_tables=True
    )

    # Define tables (mirrors your SQLAlchemy schema)
    db.define_table('auth_user',
        Field('email', 'string', unique=True, notnull=True),
        Field('password', 'password'),
        Field('active', 'boolean', default=True),
        Field('fs_uniquifier', 'string', unique=True),
        Field('confirmed_at', 'datetime'),
        migrate=True
    )

    return db

# Use in your app
db = get_db_connection()

# Query examples
all_active_users = db(db.auth_user.active == True).select()
specific_user = db(db.auth_user.email == 'user@example.com').select().first()
# Create: db.auth_user.insert(email='new@example.com', active=True)
# Update: db(db.auth_user.id == 1).update(active=False)
# Delete: db(db.auth_user.id == 1).delete()
```

✅ **Now your app can read, write, and update data!**

---

## 💡 Pro Tips for Database Work

**Connection Pooling is Your Friend**
```python
# Pool size calculation: (2 × CPU cores) + disk spindles
# Example: 4 CPUs + 1 disk = pool size of 9
# This reuses connections, making your app 10× faster
db = DAL(db_uri, pool_size=9)
```

**Always Wait for the Database to Be Ready**
```python
import time

def wait_for_database(max_retries=5, retry_delay=5):
    """Don't start until database is ready"""
    for attempt in range(max_retries):
        try:
            test_db = get_db_connection()
            test_db.close()
            print("✅ Database is ready!")
            return True
        except Exception as e:
            print(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    return False

# In your app startup:
if not wait_for_database():
    raise Exception("Could not connect to database!")
```

---

## ⚠️ Common Pitfalls (Don't Do These!)

❌ **Mistake 1: Sharing a DAL instance across threads**
```python
# WRONG - will cause errors!
db = DAL(db_uri)  # Global instance
def worker():
    db.auth_user.select()  # Multiple threads using same object
```

✅ **Right way:**
```python
import threading
thread_local = threading.local()

def get_thread_db():
    if not hasattr(thread_local, 'db'):
        thread_local.db = DAL(db_uri)  # Each thread gets its own
    return thread_local.db

def worker():
    db = get_thread_db()  # Safe to use
    db.auth_user.select()
```

---

❌ **Mistake 2: Not waiting for the database**
```python
# WRONG - starts immediately!
app = Flask(__name__)
db = DAL(db_uri)  # Might not exist yet!
```

✅ **Right way:**
```python
# Implement retry logic (see "Pro Tips" above)
if not wait_for_database():
    sys.exit(1)
db = DAL(db_uri)  # Now safe!
```

---

❌ **Mistake 3: Hardcoding database settings**
```python
# WRONG - breaks on different servers
db = DAL("mysql://root:password@localhost/mydb")
```

✅ **Right way:**
```python
# Use environment variables
db_uri = f"{os.getenv('DB_TYPE')}://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
db = DAL(db_uri)
```

---

❌ **Mistake 4: Mixing SQLAlchemy and PyDAL for queries**
```python
# WRONG - SQLAlchemy is only for setup!
from sqlalchemy import select
engine = create_engine(db_uri)
session = Session(engine)
users = session.query(User).all()  # Don't do this at runtime
```

✅ **Right way:**
```python
# SQLAlchemy = setup only (initialize_database function)
# PyDAL = queries (in your app)
db = DAL(db_uri)
users = db(db.auth_user.id > 0).select()  # Clean and fast
```

---

## 🔧 Troubleshooting Common Errors

### Problem: "Connection refused" or "Cannot connect to database"

**Solution 1: Check the database is running**
```bash
# For PostgreSQL
docker ps | grep postgres

# For MySQL
docker ps | grep mysql

# For SQLite (always runs)
ls -la *.db
```

**Solution 2: Verify environment variables**
```bash
echo $DB_TYPE
echo $DB_HOST
echo $DB_PORT
echo $DB_USER
echo $DB_NAME
```

**Solution 3: Check the connection string**
```python
print(f"Connecting to: {db_uri}")  # What does it look like?
```

### Problem: "Table already exists" error

**Solution:** This is usually harmless. It means the table was created on a previous run.
```python
# This is safe - PyDAL won't recreate if it already exists
db = DAL(db_uri, migrate=True)
```

### Problem: "Too many connections"

**Solution:** Increase your pool size or reduce concurrent requests
```python
# Before: pool_size=5 (only 5 connections)
db = DAL(db_uri, pool_size=5)

# After: pool_size=20 (handle more requests)
db = DAL(db_uri, pool_size=20)
```

### Problem: "Unique constraint violated" when inserting

**Solution:** Check if the record already exists
```python
existing = db(db.auth_user.email == 'test@example.com').select().first()
if existing:
    print("User already exists!")
else:
    db.auth_user.insert(email='test@example.com')
```

---

## Environment Variables (Your Database Config)

Your database talks to your app through these settings:

```bash
DB_TYPE=postgresql           # postgresql, mysql, sqlite
DB_HOST=localhost            # Where the database lives
DB_PORT=5432                 # Port number (5432=postgres, 3306=mysql)
DB_NAME=app_db              # Database name
DB_USER=app_user            # Username
DB_PASS=app_pass            # Password
DB_POOL_SIZE=10             # How many connections to keep ready
DB_MAX_RETRIES=5            # How many times to try connecting
DB_RETRY_DELAY=5            # Seconds between retry attempts
```

---

## Special Handling: MariaDB Galera Clusters

MariaDB Galera is like having multiple database copies that stay in sync. Special care needed:

```python
def get_galera_db():
    """MariaDB Galera configuration"""
    db_uri = f"mysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

    db = DAL(
        db_uri,
        pool_size=int(os.getenv('DB_POOL_SIZE', '10')),
        migrate=True,
        check_reserved=['all'],
        lazy_tables=True,
        driver_args={'charset': 'utf8mb4'}  # Galera requirement
    )
    return db
```

**Galera Tips:**
- ✅ Keep transactions short (avoid conflicts)
- ✅ Avoid long-running queries (they block other nodes)
- ✅ DDL changes (ALTER TABLE) should happen during low-traffic times

---

## Go Applications (High-Performance Backend)

When using Go, use GORM for database access:

```go
package main

import (
    "os"
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

    db, err := gorm.Open(dialector, &gorm.Config{})
    return db, err
}
```

---

## Threading & Async: Choose Your Power Level

Different workloads need different approaches:

| Your Situation | Use This | Why |
|---|---|---|
| Web API with 100+ requests | `asyncio` + `databases` | Single-threaded, super fast |
| Mixed blocking code | `threading` + `ThreadPoolExecutor` | Handles old code + new code |
| CPU-heavy calculations | `multiprocessing` | True parallel processing |

### Flask + Async Pattern (Recommended)

```python
from flask import Flask, g
from concurrent.futures import ThreadPoolExecutor
import asyncio

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=20)

def run_in_thread(async_func):
    """Run async code in Flask"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(async_func)
    finally:
        loop.close()

@app.route('/users')
def get_users():
    """Returns users quickly using async"""
    async def fetch():
        db = await get_async_db()
        users = await db.fetch_all("SELECT * FROM auth_user WHERE active = :active", values={"active": True})
        await db.disconnect()
        return users

    future = executor.submit(run_in_thread, fetch())
    return {"users": future.result(timeout=30)}
```

---

## Migrations: Deploy Before New Code

**Database migrations MUST be applied before deploying new code to any environment.**

**Why:** Schema mismatches between code and database cause runtime errors. Always run migrations first, then deploy the application.

```bash
# Production deployment checklist:
1. Apply migrations:   ./scripts/migrate.sh <environment>
2. Wait for completion (database is updated)
3. Deploy new code:    make deploy-<environment>
4. Verify health:      ./scripts/health-check.sh <environment>
```

**In Kubernetes:** Use an init container or Job to apply migrations before the main application Pod starts.

---

## Per-Service Database Accounts (Mandatory)

Every microservice and container **must have its own database account** with fine-grained permissions. You're not creating separate databases—all services share one database, but each gets separate credentials scoped to only the tables and operations it needs.

**Reference implementation:** Check out Waddlebot (`~/code/waddlebot`) for a real example. It uses 34+ module-specific accounts with RLS (Row-Level Security) policies and column-level grants on shared tables.

### The Strategy

| Principle | What to Do |
|-----------|-----------|
| **Separate tables per service** | Preferred — each service owns its tables where possible (backend-api owns users/sessions, connector owns integrations/webhooks) |
| **Shared tables when needed** | Acceptable if unavoidable — protect with RLS policies or column-level grants so services only see their data |
| **Per-service credentials** | Mandatory — each container reads its own `DB_USER` and `DB_PASS` from environment variables |
| **Cache/Redis accounts** | Same pattern — per-service credentials for caching layers |
| **Migration accounts** | Separate admin account used ONLY for schema changes, NEVER at runtime |

### Access Levels

What permissions each type of service needs:

| Level | Permissions | When to Use |
|-------|-------------|------------|
| Read-only | `SELECT` only | Services that only query data (analytics, reporting, read replicas) |
| Read-write | `SELECT, INSERT, UPDATE, DELETE` | Services that manage their own data |
| Scoped read-write | Read-write + RLS policies | Services sharing tables but restricted to specific rows (e.g., platform-scoped data) |
| Admin | `ALL` + DDL | Migration runners only — never used by runtime services |

### Example: Creating Per-Service Accounts

Here's what it looks like in SQL. Each service gets its own user with exactly the permissions it needs:

```sql
-- Backend API service (read-write on its tables)
CREATE USER 'backend-api-rw' IDENTIFIED BY '${BACKEND_API_DB_PASS}';
GRANT SELECT, INSERT, UPDATE, DELETE ON app_db.users TO 'backend-api-rw';
GRANT SELECT, INSERT, UPDATE, DELETE ON app_db.sessions TO 'backend-api-rw';
GRANT SELECT, INSERT, UPDATE, DELETE ON app_db.settings TO 'backend-api-rw';

-- Connector service (read-write on its tables)
CREATE USER 'connector-rw' IDENTIFIED BY '${CONNECTOR_DB_PASS}';
GRANT SELECT, INSERT, UPDATE, DELETE ON app_db.integrations TO 'connector-rw';
GRANT SELECT, INSERT, UPDATE, DELETE ON app_db.webhooks TO 'connector-rw';

-- Analytics service (read-only on shared tables)
CREATE USER 'analytics-ro' IDENTIFIED BY '${ANALYTICS_DB_PASS}';
GRANT SELECT ON app_db.users TO 'analytics-ro';
GRANT SELECT ON app_db.sessions TO 'analytics-ro';
GRANT SELECT ON app_db.events TO 'analytics-ro';

-- Shared platform integrations table with Row-Level Security (PostgreSQL)
ALTER TABLE platform_integrations ENABLE ROW LEVEL SECURITY;

CREATE POLICY twitch_platform_policy ON platform_integrations
  FOR ALL TO 'twitch-trigger'
  USING (platform = 'twitch');

CREATE POLICY discord_platform_policy ON platform_integrations
  FOR ALL TO 'discord-trigger'
  USING (platform = 'discord');

-- Migration runner account (admin, for schema changes only)
CREATE USER 'migrate-admin' IDENTIFIED BY '${MIGRATE_DB_PASS}';
GRANT ALL ON app_db.* TO 'migrate-admin';
```

### Each Container Gets Its Own Credentials

In your `docker-compose.yml` or Kubernetes manifests, pass different credentials to each service:

```bash
# Backend API container
DB_USER=backend-api-rw
DB_PASS=<secret-backend-api>

# Connector container
DB_USER=connector-rw
DB_PASS=<secret-connector>

# Analytics container
DB_USER=analytics-ro
DB_PASS=<secret-analytics>

# Migration jobs only
DB_USER=migrate-admin
DB_PASS=<secret-admin>
```

### Benefits

✅ **Security:** Services can't access tables they don't need
✅ **Compliance:** Easy audit trail of who accessed what
✅ **Isolation:** One compromised service doesn't give access to everything
✅ **Least privilege:** Each service has minimal required permissions

### Per-Service Cache (Redis/Valkey) Accounts

Apply the same security model to your caching layer. Each service gets separate Redis/Valkey credentials with ACL restrictions on key prefixes.

**Key prefix convention:** `{service-name}:{key}` (e.g., `backend-api:users`, `connector:webhooks`)

```bash
# Redis/Valkey ACL setup for per-service cache isolation
# Backend API (read-write on backend-api:* keys)
ACL SETUSER backend-api-cache on >api_cache_pass +@all ~backend-api:*

# Connector (read-write on connector:* keys)
ACL SETUSER connector-cache on >connector_cache_pass +@all ~connector:*

# Analytics (read-only on analytics:* keys)
ACL SETUSER analytics-cache on >analytics_cache_pass +@read ~analytics:*
```

Each container gets its own `CACHE_USER` and `CACHE_PASS`:

```bash
# Backend API container
CACHE_USER=backend-api-cache
CACHE_PASS=<secret-api>

# Analytics container (read-only)
CACHE_USER=analytics-cache
CACHE_PASS=<secret-analytics>
```

**Blast radius:** One compromised container accessing only its key prefix means data from other services remains protected. Read-only services get `+@read` only, not `+@all`.

---

## Summary: Database Recipe

1. **Setup Once:** Use SQLAlchemy to define your schema
2. **Query Always:** Use PyDAL for all runtime operations
3. **Use Environment Variables:** Never hardcode database settings
4. **Wait for Database:** Implement retry logic on startup
5. **Thread Safety:** Each thread gets its own connection
6. **Pool Your Connections:** Formula is (2 × CPU cores) + spindles
7. **Migrations First:** Always apply migrations before deploying new code
8. **Per-Service Accounts:** Each microservice gets its own database credentials with minimal required permissions

**Your data is safe, fast, and ready to scale!** 🚀
