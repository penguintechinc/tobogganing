"""Regression tests for MetricsReporter.to_heartbeat_dict.

Regression: metrics.py read ``Counter._value._value`` on labeled Counters
(``queries_total``/``errors_total``), which raises AttributeError — the parent
of a labeled Counter has no ``_value`` — crashing every heartbeat cycle (the
error was swallowed by the caller's broad ``except``). It now sums each Counter
across all label combinations via the public ``collect()`` API.
"""

from app.metrics import (
    MetricsReporter,
    cache_hits_total,
    errors_total,
    queries_total,
)


def test_to_heartbeat_dict_sums_labeled_and_unlabeled_without_crashing() -> None:
    before = MetricsReporter.to_heartbeat_dict()
    assert isinstance(before, dict)
    assert all(isinstance(v, int) for v in before.values())

    queries_total.labels(type="A").inc()
    queries_total.labels(type="AAAA").inc(2)
    errors_total.labels(error_type="timeout").inc(3)
    cache_hits_total.inc(4)

    after = MetricsReporter.to_heartbeat_dict()
    assert all(isinstance(v, int) for v in after.values())
    assert after["queries_total"] == before["queries_total"] + 3
    assert after["errors"] == before["errors"] + 3
    assert after["cache_hits"] == before["cache_hits"] + 4
