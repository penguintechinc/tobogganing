# Performance Standards

Part of [Development Standards](../STANDARDS.md)

## Performance Best Practices

**ALWAYS prioritize performance and stability through modern concurrency patterns**

### Python Performance Requirements

#### Concurrency Patterns - Choose Based on Use Case

1. **asyncio** - For I/O-bound operations:
   - Database queries and connections
   - HTTP/REST API calls
   - File I/O operations
   - Network communication
   - Best for operations that wait on external resources

2. **threading.Thread** - For I/O-bound operations with blocking libraries:
   - Legacy libraries without async support
   - Blocking I/O operations
   - Moderate parallelism (10-100 threads)
   - Use ThreadPoolExecutor for managed thread pools

3. **multiprocessing** - For CPU-bound operations:
   - Data processing and transformations
   - Cryptographic operations
   - Image/video processing
   - Heavy computational tasks
   - Bypasses GIL for true parallelism

**Decision Matrix:**
```python
# I/O-bound + async library available → asyncio
async def fetch_data():
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# I/O-bound + blocking library → threading
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=10) as executor:
    results = executor.map(blocking_function, data)

# CPU-bound → multiprocessing
from multiprocessing import Pool
with Pool(processes=8) as pool:
    results = pool.map(cpu_intensive_function, data)
```

#### Dataclasses with Slots - MANDATORY

**ALL data structures MUST use dataclasses with slots for memory efficiency:**

```python
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass(slots=True, frozen=True)
class User:
    """User model with slots for 30-50% memory reduction"""
    id: int
    name: str
    email: str
    created_at: str
    metadata: dict = field(default_factory=dict)
```

**Benefits of Slots:**
- 30-50% less memory per instance
- Faster attribute access
- Better type safety with type hints
- Immutability with `frozen=True`

#### Type Hints - MANDATORY

**Comprehensive type hints are REQUIRED for all Python code:**

```python
from typing import Optional, List, Dict
from collections.abc import AsyncIterator

async def process_users(
    user_ids: List[int],
    batch_size: int = 100,
    callback: Optional[Callable[[User], None]] = None
) -> Dict[int, User]:
    """Process users with full type hints"""
    results: Dict[int, User] = {}
    for user_id in user_ids:
        user = await fetch_user(user_id)
        results[user_id] = user
        if callback:
            callback(user)
    return results
```

### Go Performance Requirements
- **Goroutines**: Leverage goroutines and channels for concurrent operations
- **Sync primitives**: Use sync.Pool, sync.Map for concurrent data structures
- **Context**: Proper context propagation for cancellation and timeouts

---

## High-Performance Networking

**Evaluate on a case-by-case basis for network-intensive applications**

### When to Consider XDP/AF_XDP

Only evaluate XDP (eXpress Data Path) and AF_XDP for applications with extreme network requirements:

**Traffic Thresholds:**
- Standard applications: Regular socket programming (most cases)
- High traffic (>100K packets/sec): Consider XDP/AF_XDP
- Extreme traffic (>1M packets/sec): XDP/AF_XDP strongly recommended

### XDP (eXpress Data Path)

**Kernel-level packet processing:**
- Processes packets at the earliest point in networking stack
- Bypass most of kernel networking code
- Can drop, redirect, or pass packets
- Ideal for DDoS mitigation, load balancing, packet filtering

**Use Cases:**
- Network firewalls and packet filters
- Load balancers
- DDoS protection
- High-frequency trading systems
- Real-time packet inspection

**Language Considerations:**
- Typically implemented in C with BPF bytecode
- Can be triggered from Go or Python applications
- Requires kernel support (Linux 4.8+)

### AF_XDP (Address Family XDP)

**Zero-copy socket for user-space packet processing:**
- Bypass kernel networking stack entirely
- Direct packet access from NIC to user-space
- Lowest latency possible for packet processing
- More flexible than kernel XDP

**Use Cases:**
- Custom network protocols
- Ultra-low latency applications
- Network monitoring and analytics
- Packet capture at high speeds

**Implementation Notes:**
```python
# Python with pyxdp (if available)
# Generally prefer Go for AF_XDP implementations
```

```go
// Go with AF_XDP libraries
import (
    "github.com/asavie/xdp"
)

// AF_XDP socket setup for high-performance packet processing
func setupAFXDP(ifname string, queueID int) (*xdp.Socket, error) {
    program := &xdp.SocketOptions{
        NumFrames:      4096,
        FrameSize:      2048,
        FillRingSize:   2048,
        CompletionRingSize: 2048,
        RxRingSize:     2048,
        TxRingSize:     2048,
    }

    return xdp.NewSocket(ifname, queueID, program)
}
```

### Decision Matrix: Networking Implementation

| Packets/Sec | Technology | Language | Justification |
|-------------|------------|----------|---------------|
| < 10K       | Standard sockets | Python 3.13 | Regular networking sufficient |
| 10K - 100K  | Optimized sockets | Python/Go | Standard with optimization |
| 100K - 500K | Consider XDP | Go + XDP | High performance needed |
| > 500K      | XDP/AF_XDP required | Go + AF_XDP | Extreme performance critical |

**Important:**
- Start with standard networking
- Profile actual performance before optimization
- XDP/AF_XDP adds significant complexity
- Requires specialized knowledge and maintenance
