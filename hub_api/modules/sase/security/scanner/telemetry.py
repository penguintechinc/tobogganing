"""OTel metric instruments and loud-failure error type for the SASE scanner.

Instruments come from the global OTel meter provider configured by
``hub_api.telemetry.init_otel``; before it runs they are no-op proxies, so
recording a metric never fails a scan.
"""

from __future__ import annotations

from opentelemetry import metrics as otel_metrics

_meter = otel_metrics.get_meter("hub_api.sase.scanner")

CHECK_RESULTS = _meter.create_counter(
    "sase.scanner.check.results",
    unit="1",
    description="Scanner check outcomes by check and status (pass/fail/not_applicable/error)",
)
THREAT_LOOKUPS = _meter.create_counter(
    "sase.scanner.threat_lookups",
    unit="1",
    description="Threat-feed indicator lookups by indicator type and result (hit/miss/error)",
)
INFRA_MONITOR_RUNS = _meter.create_counter(
    "sase.scanner.infra_monitor.runs",
    unit="1",
    description="Infrastructure monitor component runs by component and status",
)
LOOKUP_DURATION = _meter.create_histogram(
    "sase.scanner.threat_lookup.duration",
    unit="s",
    description="Threat-feed lookup latency",
)


class ScannerDependencyError(RuntimeError):
    """A scan could not run because a required dependency or data source is unavailable.

    Raised instead of silently returning no findings so the scan is recorded
    as failed (``SecurityScanner._execute_scan`` stores the error message).
    """
