# Python Language Standards

## ⚠️ CRITICAL RULES

**MANDATORY REQUIREMENTS - Non-negotiable:**
1. **Python 3.13 ONLY** (3.12+ minimum) - NO exceptions
2. **SQLAlchemy for schema ONLY** - database initialization and migrations via Alembic
3. **PyDAL for ALL runtime operations** - NEVER query database with SQLAlchemy
4. **Type hints on EVERY function** - `mypy` strict mode must pass
5. **Dataclasses with slots mandatory** - all data structures use `@dataclass(slots=True)`
6. **Linting MUST pass before commit** - flake8, black, isort, mypy, bandit
7. **No hardcoded secrets** - environment variables ONLY
8. **Thread-local database connections** - use `threading.local()` for multi-threaded contexts

## Python Version

- **Required**: Python 3.13
- **Minimum**: Python 3.12+
- **Use Case**: Default choice for all applications (<10K req/sec, business logic, web APIs)

## Database Standards

### Dual-Library Architecture (MANDATORY)

**SQLAlchemy + Alembic** → Schema definition and migrations (one-time setup)
**PyDAL** → ALL runtime database operations (queries, inserts, updates, deletes)

```python
# ✅ CORRECT: Use SQLAlchemy for initialization ONLY
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String

def initialize_schema():
    """One-time database schema initialization"""
    engine = create_engine(db_url)
    metadata = MetaData()
    users = Table('auth_user', metadata, Column('id', Integer, primary_key=True), ...)
    metadata.create_all(engine)

# ✅ CORRECT: Use PyDAL for ALL runtime operations
from pydal import DAL, Field

db = DAL(db_uri, pool_size=10, migrate=True, lazy_tables=True)
db.define_table('auth_user', Field('email', 'string'), ...)
users = db(db.auth_user.active == True).select()
```

❌ **NEVER** query database with SQLAlchemy at runtime

### Supported Databases

All applications MUST support by default:
- **PostgreSQL** (DB_TYPE='postgresql') - default
- **MySQL** (DB_TYPE='mysql') - 8.0+
- **MariaDB Galera** (DB_TYPE='mysql') - cluster-aware
- **SQLite** (DB_TYPE='sqlite') - development/lightweight

### Database Connection Pattern

```python
import os
from pydal import DAL

def get_db_connection():
    """Initialize PyDAL with connection pooling"""
    db_uri = f"{os.getenv('DB_TYPE')}://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    return DAL(db_uri, pool_size=int(os.getenv('DB_POOL_SIZE', '10')), migrate=True, lazy_tables=True)
```

### Thread-Safe Database Access

```python
import threading
from pydal import DAL

thread_local = threading.local()

def get_thread_db():
    """Get thread-local database connection"""
    if not hasattr(thread_local, 'db'):
        thread_local.db = DAL(db_uri, pool_size=10, migrate=True)
    return thread_local.db
```

## Performance Standards

### Dataclasses with Slots (MANDATORY)

All data structures MUST use dataclasses with slots for 30-50% memory reduction:

```python
from dataclasses import dataclass, field
from typing import Optional, Dict

@dataclass(slots=True, frozen=True)
class User:
    """User model with slots for memory efficiency"""
    id: int
    name: str
    email: str
    created_at: str
    metadata: Dict = field(default_factory=dict)
```

### Type Hints (MANDATORY)

Comprehensive type hints required on ALL functions:

```python
from typing import List, Optional, Dict, AsyncIterator
from collections.abc import Callable

def process_users(
    user_ids: List[int],
    batch_size: int = 100,
    callback: Optional[Callable[[User], None]] = None
) -> Dict[int, User]:
    """Process users - full type hints required"""
    results: Dict[int, User] = {}
    for user_id in user_ids:
        user = fetch_user(user_id)
        results[user_id] = user
        if callback:
            callback(user)
    return results
```

### Concurrency Selection

Choose based on workload:

1. **asyncio** - I/O-bound operations (database, HTTP, file I/O)
   - Use when: >100 concurrent requests, network-heavy operations
   - Libraries: `asyncio`, `aiohttp`, `databases`

2. **threading** - Blocking I/O with legacy libraries
   - Use when: 10-100 concurrent operations, blocking I/O, legacy integrations
   - Libraries: `threading`, `concurrent.futures.ThreadPoolExecutor`

3. **multiprocessing** - CPU-bound operations
   - Use when: Data processing, calculations, cryptography
   - Libraries: `multiprocessing`, `concurrent.futures.ProcessPoolExecutor`

```python
# I/O-bound: asyncio
async def fetch_users_async(user_ids: List[int]) -> List[User]:
    async with aiohttp.ClientSession() as session:
        return await asyncio.gather(*[fetch_user(uid) for uid in user_ids])

# Blocking I/O: threading
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=10) as executor:
    users = list(executor.map(fetch_user, user_ids))

# CPU-bound: multiprocessing
from multiprocessing import Pool
with Pool(processes=8) as pool:
    results = pool.map(compute_hash, data)
```

## Linting & Code Quality (MANDATORY)

All code MUST pass before commit:

- **flake8**: Style and errors (`flake8 .`)
- **black**: Code formatting (`black .`)
- **isort**: Import sorting (`isort .`)
- **mypy**: Type checking (`mypy . --strict`)
- **bandit**: Security scanning (`bandit -r .`)

```bash
# Pre-commit validation
flake8 . && black . && isort . && mypy . --strict && bandit -r .
```

## PEP Compliance

- **PEP 8**: Style guide (enforced by flake8, black)
- **PEP 257**: Docstrings (all modules, classes, functions)
- **PEP 484**: Type hints (mandatory on all functions)

```python
"""Module docstring following PEP 257"""

def function_name(param: str) -> str:
    """
    Function docstring with type hints.

    Args:
        param: Description

    Returns:
        Description of return value
    """
    return param.upper()
```

## Flask Integration

- **Flask + Flask-Security-Too**: Mandatory for authentication
- **PyDAL**: Runtime database operations
- **Thread-safe contexts**: Use Flask's `g` object for request-scoped DB access

```python
from flask import Flask, g
from pydal import DAL

app = Flask(__name__)

def get_db():
    """Get database connection for current request"""
    if 'db' not in g:
        g.db = DAL(db_uri, pool_size=10)
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Close database after request"""
    db = g.pop('db', None)
    if db is not None:
        db.close()
```

## Common Pitfalls

❌ **DON'T:**
- Use SQLAlchemy for runtime queries
- Share database connections across threads
- Ignore type hints or mypy warnings
- Hardcode credentials
- Use dict/list instead of dataclasses with slots
- Skip linting before commit
- Assume blocking libraries work with asyncio

✅ **DO:**
- Use PyDAL for all runtime database operations
- Create thread-local DB instances per thread
- Add type hints to every function
- Use environment variables for configuration
- Use dataclasses with slots for data structures
- Run full linting suite before every commit
- Profile performance before optimizing
