"""Prometheus metrics for DNS resolver service.

P3-S4: Metrics collection and exposure for the resolver pipeline.
Integrates with prometheus-client to track DNS operations, cache performance,
IOC blocks, and upstream latency.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Prometheus metric definitions (module-level singletons)
queries_total = Counter(
    "netsvcs_dns_queries_total", "Total DNS queries received", labelnames=["type"]
)
cache_hits_total = Counter("netsvcs_dns_cache_hits_total", "Total cache hits")
cache_misses_total = Counter("netsvcs_dns_cache_misses_total", "Total cache misses")
errors_total = Counter(
    "netsvcs_dns_errors_total", "Total DNS resolution errors", labelnames=["error_type"]
)
ioc_blocks_total = Counter("netsvcs_dns_ioc_blocks_total", "Total IOC-blocked queries")

# Histograms
upstream_latency_seconds = Histogram(
    "netsvcs_dns_upstream_latency_seconds",
    "Upstream DNS query latency (seconds)",
    buckets=(0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)
query_latency_seconds = Histogram(
    "netsvcs_dns_query_latency_seconds",
    "Total query resolution latency (seconds)",
    buckets=(0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)

# Gauges
cache_size_bytes = Gauge("netsvcs_dns_cache_size_bytes", "Approximate cache size in bytes")


class MetricsReporter:
    """Prometheus metrics convenience methods for DNS resolver operations."""

    @staticmethod
    def record_query(record_type: str) -> None:
        """Record a DNS query by type.

        Args:
            record_type: DNS record type (A, AAAA, CNAME, etc.).
        """
        queries_total.labels(type=record_type).inc()

    @staticmethod
    def record_cache_hit() -> None:
        """Record a cache hit."""
        cache_hits_total.inc()

    @staticmethod
    def record_cache_miss() -> None:
        """Record a cache miss."""
        cache_misses_total.inc()

    @staticmethod
    def record_error(error_type: str) -> None:
        """Record an error.

        Args:
            error_type: Error classification (e.g., 'servfail', 'refused', 'timeout').
        """
        errors_total.labels(error_type=error_type).inc()

    @staticmethod
    def record_ioc_block() -> None:
        """Record an IOC-blocked query."""
        ioc_blocks_total.inc()

    @staticmethod
    def record_upstream_latency(latency_seconds: float) -> None:
        """Record upstream DNS query latency.

        Args:
            latency_seconds: Latency in seconds.
        """
        upstream_latency_seconds.observe(latency_seconds)

    @staticmethod
    def record_query_latency(latency_seconds: float) -> None:
        """Record total query resolution latency.

        Args:
            latency_seconds: Latency in seconds.
        """
        query_latency_seconds.observe(latency_seconds)

    @staticmethod
    def update_cache_size(size_bytes: int) -> None:
        """Update the cache size gauge.

        Args:
            size_bytes: Cache size in bytes.
        """
        cache_size_bytes.set(size_bytes)

    @staticmethod
    def to_heartbeat_dict() -> dict[str, float | int]:
        """Return current metrics as a dict for heartbeat reporting.

        Sums each Counter across all its label combinations via the public
        ``collect()`` API. Reading ``Counter._value`` directly raised
        AttributeError on the labeled Counters (``queries_total``/``errors_total``
        have no top-level ``_value`` — only their per-label children do), which
        crashed every heartbeat cycle (the error was swallowed upstream).

        Returns:
            Dict with metric snapshots.
        """

        def _total(counter: Counter) -> int:
            return int(
                sum(
                    sample.value
                    for metric in counter.collect()
                    for sample in metric.samples
                    if sample.name.endswith("_total")
                )
            )

        return {
            "queries_total": _total(queries_total),
            "cache_hits": _total(cache_hits_total),
            "cache_misses": _total(cache_misses_total),
            "errors": _total(errors_total),
            "ioc_blocks": _total(ioc_blocks_total),
        }
