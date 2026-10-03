//! OTel instrumentation for the syslog log-forwarding subsystem,
//! mirroring `hub_router_mirror::metrics`/`hub_router_firewall::metrics`/
//! `hub_router_ports::metrics`'s self-contained-meter pattern
//! (critical-rules.md Observability: histograms for load/latency first):
//! this crate reads the process-wide global meter provider
//! (`opentelemetry::global::meter`) directly rather than depending on the
//! `hub-router` binary crate, so it stays a safe no-op in any build that
//! never calls `hub_router::telemetry::init_meter_provider` (unit tests,
//! other consumers) and picks up real export automatically once that
//! provider is installed.

use opentelemetry::metrics::{Counter, Histogram, Meter};
use std::sync::{OnceLock, PoisonError, RwLock};

struct SyslogMetrics {
    send_duration_seconds: Histogram<f64>,
    logs_sent_total: Counter<u64>,
    logs_dropped_total: Counter<u64>,
    send_errors_total: Counter<u64>,
}

impl SyslogMetrics {
    fn new(meter: &Meter) -> Self {
        Self {
            send_duration_seconds: meter
                .f64_histogram("hub_router.syslog.send.duration_seconds")
                .with_description(
                    "Latency of one Logger::send_log call (format + UDP send) per access log entry",
                )
                .with_unit("s")
                .build(),
            logs_sent_total: meter
                .u64_counter("hub_router.syslog.logs_sent_total")
                .with_description("Count of access log entries successfully sent to the syslog destination")
                .build(),
            logs_dropped_total: meter
                .u64_counter("hub_router.syslog.logs_dropped_total")
                .with_description("Count of access log entries dropped because the syslog worker queue was full")
                .build(),
            send_errors_total: meter
                .u64_counter("hub_router.syslog.send_errors_total")
                .with_description("Count of failed sends to the syslog destination (connection down, marshal failure)")
                .build(),
        }
    }
}

static METRICS: OnceLock<RwLock<SyslogMetrics>> = OnceLock::new();

fn cell() -> &'static RwLock<SyslogMetrics> {
    METRICS.get_or_init(|| {
        RwLock::new(SyslogMetrics::new(&opentelemetry::global::meter(
            "hub-router-syslog",
        )))
    })
}

/// Records one [`crate::logger::Logger`] `send_log` call's latency. A
/// no-op against the real exporter if no OTLP meter provider has been
/// installed yet — never panics either way (critical-rules.md: a dead
/// exporter never breaks the app).
pub fn record_send_duration(duration_secs: f64) {
    let metrics = cell().read().unwrap_or_else(PoisonError::into_inner);
    metrics.send_duration_seconds.record(duration_secs, &[]);
}

/// Records one successfully sent access log entry.
pub fn record_log_sent() {
    let metrics = cell().read().unwrap_or_else(PoisonError::into_inner);
    metrics.logs_sent_total.add(1, &[]);
}

/// Records one access log entry dropped from a full queue.
pub fn record_log_dropped() {
    let metrics = cell().read().unwrap_or_else(PoisonError::into_inner);
    metrics.logs_dropped_total.add(1, &[]);
}

/// Records one failed send (connection failure or JSON marshal failure).
pub fn record_send_error() {
    let metrics = cell().read().unwrap_or_else(PoisonError::into_inner);
    metrics.send_errors_total.add(1, &[]);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recording_before_any_provider_is_installed_never_panics() {
        record_send_duration(0.001);
        record_log_sent();
        record_log_dropped();
        record_send_error();
    }
}
