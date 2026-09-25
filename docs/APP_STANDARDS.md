# Tobogganing Application Standards

Project-specific architecture and patterns for Tobogganing services.

## penguin-dal 0.2.0+ Async Runtime Usage

### Core Pattern

**penguin-dal AsyncDB** provides async-native database access matching SQLAlchemy's reflected schema. All runtime queries use the async API; SQLAlchemy + Alembic handle schema only.

```python
from penguin_dal import AsyncDB

# Create AsyncDB and reflect schema
dal = AsyncDB(uri="sqlite:///db.sqlite")
await dal.reflect()

# Query: await db(condition).select() → Rows (call .first() for one, iterate for many)
rowset = await dal(dal.users.tenant == "tenant-1", dal.users.is_active == True).select()
user = rowset.first()  # Single row, or None
for row in rowset:  # Iterate all rows
    print(row.id, row.email)

# Multi-condition: conditions are AND-combined
rowset = await dal(dal.users.id == "uuid-123", dal.users.tenant == "tenant-1").select()

# Count: await db(condition).count() → int
count = await dal(dal.users.tenant == "tenant-1").count()

# Insert: await db.tablename.async_insert(**all_not_null_cols) → int (last_insert_id)
await dal.users.async_insert(
    id=str(uuid4()),
    email="user@example.com",
    username="testuser",
    password_hash=bcrypt.hashpw(...),
    is_active=True,
    mfa_enabled=False,
    tenant="tenant-1",
    created_at=datetime.utcnow(),
    updated_at=datetime.utcnow(),
)

# Update: await db(condition).update(**changes) → None
await dal(dal.users.id == "uuid-123", dal.users.tenant == "tenant-1").update(
    email="newemail@example.com",
    updated_at=datetime.utcnow(),
)

# Delete: await db(condition).delete() → None
await dal(dal.users.id == "uuid-123", dal.users.tenant == "tenant-1").delete()

# Atomic increment (uses DB-side operation, no race conditions)
await dal(dal.clusters.id == "cluster-1").update(
    client_count=dal.clusters.client_count + 1,
)
```

### Manager Pattern

All data access is encapsulated in **async manager classes** that own the AsyncDB instance and expose typed methods.

```python
class UserManager:
    """Manages users via penguin-dal."""

    def __init__(self, db: AsyncDB) -> None:
        """Initialize with a real AsyncDB instance (never None)."""
        if db is None:
            raise ValueError("Database instance cannot be None")
        self.db = db

    async def create_user(self, username: str, email: str, password: str, tenant: str) -> User:
        """Create user. Always supply all NOT NULL columns explicitly.
        
        penguin-dal reflection does not apply model-side Python defaults
        (e.g., created_at=datetime.utcnow()). Caller must provide all.
        """
        user_id = str(uuid4())
        now = datetime.utcnow()
        
        # Pass all NOT NULL columns per schema
        await self.db.users.async_insert(
            id=user_id,
            username=username,
            email=email,
            password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
            is_active=True,
            mfa_enabled=False,
            tenant=tenant,  # ALWAYS scoped to tenant
            created_at=now,
            updated_at=now,
        )
        
        return User(id=user_id, username=username, email=email, tenant=tenant, created_at=now)

    async def get_user(self, user_id: str, tenant: str) -> User | None:
        """Retrieve user. Always filter by tenant."""
        rowset = await self.db(
            self.db.users.id == user_id,
            self.db.users.tenant == tenant,  # MANDATORY tenant filter
        ).select()
        
        row = rowset.first()
        if not row:
            return None
        
        return User(
            id=row.id,
            username=row.username,
            email=row.email,
            tenant=row.tenant,
            created_at=row.created_at,
        )

    async def list_users(self, tenant: str) -> list[User]:
        """List all users in tenant. Filters by tenant before any other condition."""
        rowset = await self.db(
            self.db.users.tenant == tenant,
        ).select(orderby=self.db.users.created_at)
        
        return [
            User(id=row.id, username=row.username, email=row.email, tenant=row.tenant, created_at=row.created_at)
            for row in rowset
        ]
```

### Tenant Isolation (Hard Boundary)

**Every query must include a tenant filter.** This is enforced at the DAL layer, not the API layer.

```python
# ✅ CORRECT: Tenant filter present
rowset = await dal(
    dal.users.tenant == "tenant-1",  # FIRST condition
    dal.users.is_active == True,      # Additional filters
).select()

# ❌ WRONG: Missing tenant filter (will break in any-tenant bug check or review)
rowset = await dal(dal.users.is_active == True).select()  # No tenant scope!
```

**Why:** Tenant is part of every table's primary logical key. A query without tenant filter is a logical error—cross-tenant data pollution or a bug waiting to happen.

### Async Context: Routes and Managers

**Routes (Quart):** Are natively `async def`. Each coroutine holds one AsyncDB instance for its request.

```python
from quart import Blueprint

bp = Blueprint("users", __name__)

@bp.route("/users", methods=["POST"])
async def create_user() -> tuple[dict, int]:
    """Create a new user. Each request gets a fresh AsyncDB."""
    db = app.config["DAL"]  # Fresh AsyncDB per request
    manager = UserManager(db)
    
    user = await manager.create_user(...)  # All operations async
    return {"id": user.id}, 201
```

**Managers:** Are instantiated with a DAL instance and expose `async def` methods. They do not hold state across requests.

```python
class UserManager:
    def __init__(self, db: AsyncDB) -> None:
        self.db = db  # Per-request instance
    
    async def create_user(self, ...) -> User:
        await self.db.users.async_insert(...)
        ...
```

**Celery workers:** Create a fresh AsyncDB per task using `asyncio.run()`.

```python
@celery.task
def process_user(user_id: str) -> None:
    """Celery tasks wrap async with asyncio.run()."""
    async def _run() -> None:
        db = AsyncDB(uri=os.getenv("DATABASE_URL"))
        await db.reflect()
        try:
            manager = UserManager(db)
            await manager.process(user_id)
        finally:
            await db.close()
    
    asyncio.run(_run())
```

### Type Hints and Dataclasses

All data structures use `@dataclass(slots=True)` for type safety and memory efficiency.

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(slots=True)
class User:
    """Immutable user record from DB."""
    id: str
    username: str
    email: str
    tenant: str
    created_at: datetime
    is_active: bool = True
    last_login: datetime | None = None

@dataclass(slots=True)
class CreateUserRequest:
    """Mutable request DTO (frozen=False by default)."""
    username: str
    email: str
    password: str
    tenant: str
```

### Error Handling

Managers catch DB exceptions and log them with context, never re-raising unless critical.

```python
async def create_user(self, ...) -> User:
    try:
        await self.db.users.async_insert(...)
        logger.info("user_created", user_id=user_id, tenant=tenant)
        return user
    except Exception as e:
        if "unique" in str(e).lower():
            logger.warning("user_exists", email=email, tenant=tenant)
            raise ValueError("Email already registered")
        logger.error("user_creation_error", email=email, error=str(e))
        raise
```

### Testing: Real Integration Tests

**All managers must have real_dal integration tests** that hit a real database. Mocks hide schema mismatches and API errors.

The `real_dal` fixture (in `conftest.py`) builds schema via `alembic upgrade head`, then reflects an AsyncDB.

```python
@pytest.mark.asyncio
async def test_user_roundtrip(real_dal: AsyncDB) -> None:
    """Verify user create/get against real DB."""
    manager = UserManager(real_dal)
    tenant = "test-tenant-1"
    
    # Create
    user = await manager.create_user("alice", "alice@example.com", "pass", tenant)
    assert user.id is not None
    
    # Retrieve
    retrieved = await manager.get_user(user.id, tenant)
    assert retrieved is not None
    assert retrieved.email == "alice@example.com"

@pytest.mark.asyncio
async def test_tenant_isolation(real_dal: AsyncDB) -> None:
    """Verify cross-tenant data is isolated."""
    manager = UserManager(real_dal)
    
    # Create users in different tenants
    user1 = await manager.create_user("alice", "alice@example.com", "pass", "tenant-1")
    user2 = await manager.create_user("bob", "bob@example.com", "pass", "tenant-2")
    
    # Tenant-1 cannot see tenant-2's user
    retrieved = await manager.get_user(user2.id, "tenant-1")
    assert retrieved is None  # Cross-tenant access fails
```

### Known Schema Divergences

**Model UUID vs Migration String:**
- `models.py` defines `id: Column[str] = Column(UUID(as_uuid=False), ...)` (Python string)
- Migrations store as `String(36)` (DB-level authority)
- AsyncDB reflects as `String(36)`, which is correct. Models will be aligned later.

**Entitlements metering.count_users:**
- Currently: `rowset = await dal(...).select(); len(rowset)`
- Should be: `count = await dal(...).count()`
- Follow-up: Switch to `.count()` to avoid loading all rows into memory.

## Architecture Overview

### Modules

- **core/modules/sase/**: SASE cluster, client, and network management
  - `auth/user_manager.py`: User authentication and sessions
  - `network/port_manager.py`: Headend port configurations
  - `network/vrf_manager.py`: VRF and OSPF configuration
  - `firewall/access_control.py`: Firewall rules and access policies

- **core/modules/waddleperf_cluster/**: WaddlePerf cluster and device management
- **core/modules/waddleperf_client/**: WaddlePerf client device coordination
- **core/modules/waddleperf_c2c/**: Cluster-to-cluster performance testing

### Database

- **Runtime:** penguin-dal AsyncDB (all managers)
- **Schema:** SQLAlchemy models + Alembic migrations (authority)
- **Connection:** Per-request or per-task AsyncDB instance (no pooling across requests)

### Auth & Tenancy

- JWT tokens from auth service carry tenant claim
- Tenant middleware runs first in all requests
- ALL queries scoped to `request.tenant_id`
- Cross-tenant access returns 403 automatically

### Feature Flags & Licensing

- Every feature behind PostHog feature flag (default OFF)
- Enterprise features additionally license-gated
- Flags checked at route entry, not in managers
