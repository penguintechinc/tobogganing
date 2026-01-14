# Language Selection Criteria

Part of [Development Standards](../STANDARDS.md)

**Evaluate on a case-by-case basis which language to use for each project or service:**

## Python 3.13 (Default Choice)

**Use Python for most applications:**
- Web applications and REST APIs
- Business logic and data processing
- Integration services and connectors
- CRUD applications
- Admin panels and internal tools
- Low to moderate traffic applications (<10K req/sec)

**Advantages:**
- Rapid development and iteration
- Rich ecosystem of libraries
- Excellent for prototyping and MVPs
- Strong support for data processing
- Easy maintenance and debugging

## Go 1.24.x (Performance-Critical Only)

**Use Go ONLY for high-traffic, performance-critical applications:**
- Applications handling >10K requests/second
- Network-intensive services requiring low latency
- Services with latency requirements <10ms
- CPU-bound operations requiring maximum throughput
- Systems requiring minimal memory footprint
- Real-time processing pipelines

**Traffic Threshold Decision Matrix:**

| Requests/Second | Language Choice | Rationale |
|-----------------|-----------------|-----------|
| < 1K req/sec    | Python 3.13     | Development speed priority |
| 1K - 10K req/sec| Python 3.13     | Python can handle with optimization |
| 10K - 50K req/sec| Evaluate both  | Consider complexity vs performance needs |
| > 50K req/sec   | Go 1.24.x       | Performance becomes critical |

**Important Considerations:**
- Start with Python for faster iteration
- Profile and measure actual performance before switching
- Consider operational complexity of multi-language stack
- Go adds development overhead - only use when necessary
