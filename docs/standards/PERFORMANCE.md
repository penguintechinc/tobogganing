# ⚡ Performance Guide - Making Things Fast

Part of [Development Standards](../STANDARDS.md)

## 🧘 Don't Optimize Prematurely

Before diving into optimization, remember: **premature optimization is the root of all evil**. Always:
1. **Measure first** - Use profilers, not guesses
2. **Identify the bottleneck** - Usually it's not where you think
3. **Make a change** - One at a time
4. **Measure again** - Verify improvement
5. **Ship it** - Move on to the next problem

## 🔍 Finding Bottlenecks

Use profilers to measure what's actually slow:

```bash
python -m cProfile -s cumulative your_app.py  # CPU profile
python -m memory_profiler your_script.py      # Memory usage
kernprof -l -v your_script.py                 # Line-by-line
```

Don't guess - measure. You'll be surprised what's actually slow.

## ⚡ Python Performance Tips

### Dataclasses with Slots - MANDATORY for Memory Efficiency

**Before (30-50% more memory overhead):**
```python
class User:
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email
```

**After (lean and mean):**
```python
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class User:
    id: int
    name: str
    email: str
```

**Why?** Slots prevent Python from creating a `__dict__` for each instance. With 1 million users, that's 30-50MB saved. Every instance also gets faster attribute access.

### Type Hints - MANDATORY for Code Quality

**Before (unclear, slow without optimization):**
```python
async def process_users(user_ids, batch_size=100, callback=None):
    results = {}
    for user_id in user_ids:
        user = await fetch_user(user_id)
        results[user_id] = user
        if callback:
            callback(user)
    return results
```

**After (clear, enables optimization):**
```python
from typing import Callable, Optional, Dict

async def process_users(
    user_ids: list[int],
    batch_size: int = 100,
    callback: Optional[Callable[[User], None]] = None
) -> Dict[int, User]:
    results: Dict[int, User] = {}
    for user_id in user_ids:
        user = await fetch_user(user_id)
        results[user_id] = user
        if callback:
            callback(user)
    return results
```

Type hints help Python optimize your code and catch bugs before runtime.

## 🔄 Concurrency: Async vs Threading vs Multiprocessing

Think of three scenarios at a restaurant:

**Asyncio** 🎯 - One waiter, many tables
- Waiter takes your order, serves another table while your food cooks
- Comes back when your food is ready
- Best for I/O waiting (network, disk, database)
- Single thread, multiple async tasks

```python
async def fetch_users(user_ids):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_user(session, id) for id in user_ids]
        return await asyncio.gather(*tasks)  # Wait for all simultaneously
```

**Threading** 👥 - Multiple waiters, shared kitchen
- Each waiter works independently on their tables
- Works great for blocking operations (legacy libraries)
- Good for moderate parallelism (10-100 threads)
- Useful when async libraries don't exist

```python
from concurrent.futures import ThreadPoolExecutor

def fetch_legacy_api(user_id):
    return requests.get(f"/users/{user_id}").json()

with ThreadPoolExecutor(max_workers=10) as executor:
    users = list(executor.map(fetch_legacy_api, user_ids))
```

**Multiprocessing** 💪 - Separate restaurants
- Multiple fully independent operations
- Each has their own Python interpreter (bypasses GIL)
- Only for CPU-bound work: calculations, compression, cryptography
- Higher overhead (use for real compute)

```python
from multiprocessing import Pool

def expensive_calculation(data):
    return sum(x**2 for x in data)  # Real CPU work

with Pool(processes=8) as pool:
    results = pool.map(expensive_calculation, large_datasets)
```

**Choose the right tool:**
- Database queries, API calls, file reading → **asyncio**
- Blocking library, legacy code → **threading**
- Heavy math, compression, crypto → **multiprocessing**

## 🗄️ Database Query Optimization

**The fastest query is the one you don't run.**

**Before (N+1 problem - 101 queries!):**
```python
users = User.query.all()
for user in users:
    print(user.name, user.team.name)  # 1 query per user!
```

**After (join - 1 query):**
```python
users = db.session.query(User).options(
    joinedload(User.team)
).all()
for user in users:
    print(user.name, user.team.name)  # Already loaded
```

**Other tricks:**
- Use `EXPLAIN` to see what your database is actually doing
- Add indexes on columns you filter/join by
- Select only columns you need (not `SELECT *`)
- Use connection pooling (default in modern libraries)
- Cache expensive queries (see next section)

## 💾 Caching Strategies

**Cache when:** Same data requested repeatedly, computation is expensive, freshness isn't critical

**Don't cache:** Sensitive data (passwords), very small datasets, real-time data

**In-memory cache (fastest):**
```python
from functools import lru_cache
import time

@lru_cache(maxsize=128)
def expensive_calculation(x):
    time.sleep(1)
    return x ** 2

expensive_calculation(5)  # 1 second
expensive_calculation(5)  # Instant (cached)
```

**Redis cache (shared across servers):**
```python
import redis

cache = redis.Redis(host='localhost', port=6379, decode_responses=True)

def get_user(user_id):
    cached = cache.get(f"user:{user_id}")
    if cached:
        return json.loads(cached)

    user = db.fetch_user(user_id)
    cache.setex(f"user:{user_id}", 3600, json.dumps(user))  # 1 hour TTL
    return user
```

## 🦫 Go Performance for High-Traffic Services

Go is your choice when Python can't keep up. Use Go for:
- Services handling >10K requests/second
- Sub-10ms latency requirements
- Network-intensive applications

Go's strengths: Goroutines (millions cheap), fast startup, compiled, no GIL

```go
func handleRequests(ch chan Request) {
    for r := range ch {
        go processRequest(r)  // Goroutine per request, cheap!
    }
}
```

Connection pools and proper context handling:
```go
// Connection pooling built-in, use context for timeouts
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()
result := db.QueryContext(ctx, "SELECT ...")
```

## 📊 Monitoring in Production

You can't optimize what you don't measure. Monitor these metrics:

**Application metrics:**
```python
from prometheus_client import Counter, Histogram, Gauge

# How many requests?
request_count = Counter('requests_total', 'Total requests')

# How long do they take?
request_duration = Histogram('request_duration_seconds', 'Request duration')

# How much memory/CPU are we using?
memory_usage = Gauge('memory_usage_bytes', 'Memory usage')

# Example: Record request time
with request_duration.time():
    response = handle_request()
```

**Alert thresholds:** Response time > 1s, Error rate > 1%, Memory > 80%, Exhausted DB pool, Cache hit < 70%

**Tools:** Prometheus (metrics), Grafana (visualization), DataDog/New Relic (all-in-one), Cloud provider monitoring

**Key insight:** If you're not measuring it, you can't improve it.

## 🚀 High-Performance Networking (Case-by-Case)

Only for extreme network requirements:

**Traffic thresholds:**
- < 10K packets/sec: Standard sockets (Python, most cases)
- 10K-100K packets/sec: Optimized sockets (Python + careful design)
- > 100K packets/sec: Consider Go or XDP

**XDP (eXpress Data Path)** - Kernel-level packet processing
- Filters packets at network driver, before kernel processing
- Use for: DDoS mitigation, firewalls, load balancing
- Trade-off: Complex, requires C/eBPF knowledge

**AF_XDP** - User-space packet processing, zero-copy
- Direct packet access from NIC to app
- Use for: Ultra-low latency, custom protocols
- Trade-off: Highest complexity, best performance

**When in doubt:** Start with standard sockets. Profile first. Add complexity only if proven necessary.
