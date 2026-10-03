//! OTel instrumentation for the ports subsystem, mirroring
//! `hub-router`'s `telemetry::RouterMetrics` pattern (critical-rules.md
//! Observability: histograms for load/latency first) but self-contained —
//! this crate reads the process-wide global meter provider
//! (`opentelemetry::global::meter`) directly rather than depending on the
//! `hub-router` binary crate, so it stays a safe no-op in any build that
//! never calls `hub_router::telemetry::init_meter_provider` (unit tests,
//! other consumers) and picks up real export automatically once that
//! provider is installed.
//!
//! Covers the one genuinely variable-cost, input-dependent operation this
//! crate performs — expanding a configured port-range string — plus
//! listener bind outcomes (the real observable "did this succeed" signal
//! an operator needs when a configured range can't be bound).

use crate::range::Protocol;
use opentelemetry::metrics::{Counter, Histogram, Meter};
use opentelemetry::KeyValue;
use std::sync::{OnceLock, PoisonError, RwLock};

struct PortsMetrics {
    range_parse_duration_seconds: Histogram<f64>,
    listeners_started_total: Counter<u64>,
    listeners_failed_total: Counter<u64>,
}

impl PortsMetrics {
    fn new(meter: &Meter) -> Self {
        Self {
            range_parse_duration_seconds: meter
                .f64_histogram("hub_router.ports.range_parse.duration_seconds")
                .with_description(
                    "Latency of parsing a configured TCP/UDP port-range string, labeled by protocol and outcome",
                )
                .with_unit("s")
                .build(),
            listeners_started_total: meter
                .u64_counter("hub_router.ports.listeners.started_total")
                .with_description("Count of port listeners successfully bound, labeled by protocol")
                .build(),
            listeners_failed_total: meter
                .u64_counter("hub_router.ports.listeners.failed_total")
                .with_description("Count of port listener bind failures, labeled by protocol")
                .build(),
        }
    }
}

static METRICS: OnceLock<RwLock<PortsMetrics>> = OnceLock::new();

fn cell() -> &'static RwLock<PortsMetrics> {
    METRICS.get_or_init(|| {
        RwLock::new(PortsMetrics::new(&opentelemetry::global::meter(
            "hub-router-ports",
        )))
    })
}

/// Records one `parse_port_ranges` call's latency, labeled by protocol and
/// outcome (`"ok"`/`"error"`). A no-op against the real exporter if no
/// OTLP meter provider has been installed yet — never panics either way.
pub fn record_range_parse(duration_secs: f64, protocol: Protocol, outcome: &str) {
    let attrs = [
        KeyValue::new("protocol", protocol.to_string()),
        KeyValue::new("outcome", outcome.to_string()),
    ];
    let metrics = cell().read().unwrap_or_else(PoisonError::into_inner);
    metrics
        .range_parse_duration_seconds
        .record(duration_secs, &attrs);
}

/// Records one successful listener bind.
pub fn record_listener_started(protocol: Protocol) {
    let attrs = [KeyValue::new("protocol", protocol.to_string())];
    let metrics = cell().read().unwrap_or_else(PoisonError::into_inner);
    metrics.listeners_started_total.add(1, &attrs);
}

/// Records one failed listener bind.
pub fn record_listener_failed(protocol: Protocol) {
    let attrs = [KeyValue::new("protocol", protocol.to_string())];
    let metrics = cell().read().unwrap_or_else(PoisonError::into_inner);
    metrics.listeners_failed_total.add(1, &attrs);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recording_before_any_provider_is_installed_never_panics() {
        record_range_parse(0.001, Protocol::Tcp, "ok");
        record_listener_started(Protocol::Udp);
        record_listener_failed(Protocol::Tcp);
    }
}
