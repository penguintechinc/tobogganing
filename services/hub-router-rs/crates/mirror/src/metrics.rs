//! OTel instrumentation for the mirror subsystem, mirroring
//! `hub_router_firewall::metrics`/`hub_router_ports::metrics`'s
//! self-contained-meter pattern (critical-rules.md Observability:
//! histograms for load/latency first): this crate reads the process-wide
//! global meter provider (`opentelemetry::global::meter`) directly rather
//! than depending on the `hub-router` binary crate, so it stays a safe
//! no-op in any build that never calls
//! `hub_router::telemetry::init_meter_provider` (unit tests, other
//! consumers) and picks up real export automatically once that provider
//! is installed.

use opentelemetry::metrics::{Counter, Histogram, Meter};
use opentelemetry::KeyValue;
use std::sync::{OnceLock, PoisonError, RwLock};

struct MirrorMetrics {
    send_duration_seconds: Histogram<f64>,
    packets_sent_total: Counter<u64>,
    packets_dropped_total: Counter<u64>,
    send_errors_total: Counter<u64>,
}

impl MirrorMetrics {
    fn new(meter: &Meter) -> Self {
        Self {
            send_duration_seconds: meter
                .f64_histogram("hub_router.mirror.send.duration_seconds")
                .with_description(
                    "Latency of one Manager::send_packet call (encapsulate + forward), labeled by protocol",
                )
                .with_unit("s")
                .build(),
            packets_sent_total: meter
                .u64_counter("hub_router.mirror.packets_sent_total")
                .with_description("Count of mirrored packets successfully forwarded, labeled by sink (mirror/suricata)")
                .build(),
            packets_dropped_total: meter
                .u64_counter("hub_router.mirror.packets_dropped_total")
                .with_description("Count of packets dropped because the mirror worker queue was full, labeled by source")
                .build(),
            send_errors_total: meter
                .u64_counter("hub_router.mirror.send_errors_total")
                .with_description("Count of forwarding failures, labeled by sink (mirror/suricata)")
                .build(),
        }
    }
}

static METRICS: OnceLock<RwLock<MirrorMetrics>> = OnceLock::new();

fn cell() -> &'static RwLock<MirrorMetrics> {
    METRICS.get_or_init(|| {
        RwLock::new(MirrorMetrics::new(&opentelemetry::global::meter(
            "hub-router-mirror",
        )))
    })
}

/// Records one [`crate::manager::Manager::send_packet`] call's latency,
/// labeled by encapsulation protocol. A no-op against the real exporter
/// if no OTLP meter provider has been installed yet — never panics
/// either way (critical-rules.md: a dead exporter never breaks the app).
pub fn record_send_duration(duration_secs: f64, protocol: &str) {
    let attrs = [KeyValue::new("protocol", protocol.to_string())];
    let metrics = cell().read().unwrap_or_else(PoisonError::into_inner);
    metrics.send_duration_seconds.record(duration_secs, &attrs);
}

/// Records one successfully forwarded packet, labeled by sink
/// (`"mirror"` for a regular destination, `"suricata"`).
pub fn record_packet_sent(sink: &str) {
    let attrs = [KeyValue::new("sink", sink.to_string())];
    let metrics = cell().read().unwrap_or_else(PoisonError::into_inner);
    metrics.packets_sent_total.add(1, &attrs);
}

/// Records one packet dropped from a full queue, labeled by the
/// `mirror_*` entry point that enqueued it (`"http"`/`"tcp"`/`"udp"`/`"raw"`).
pub fn record_packet_dropped(source: &str) {
    let attrs = [KeyValue::new("source", source.to_string())];
    let metrics = cell().read().unwrap_or_else(PoisonError::into_inner);
    metrics.packets_dropped_total.add(1, &attrs);
}

/// Records one forwarding failure, labeled by sink.
pub fn record_send_error(sink: &str) {
    let attrs = [KeyValue::new("sink", sink.to_string())];
    let metrics = cell().read().unwrap_or_else(PoisonError::into_inner);
    metrics.send_errors_total.add(1, &attrs);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recording_before_any_provider_is_installed_never_panics() {
        record_send_duration(0.001, "VXLAN");
        record_packet_sent("mirror");
        record_packet_dropped("tcp");
        record_send_error("suricata");
    }
}
