//! OTel instrumentation for the firewall subsystem, mirroring
//! `hub_router_ports::metrics`'s self-contained-meter pattern
//! (critical-rules.md Observability: histograms for load/latency first):
//! this crate reads the process-wide global meter provider
//! (`opentelemetry::global::meter`) directly rather than depending on
//! the `hub-router` binary crate, so it stays a safe no-op in any build
//! that never calls `hub_router::telemetry::init_meter_provider` (unit
//! tests, other consumers) and picks up real export automatically once
//! that provider is installed.

use opentelemetry::metrics::{Histogram, Meter};
use opentelemetry::KeyValue;
use std::sync::{OnceLock, PoisonError, RwLock};

struct FirewallMetrics {
    access_check_duration_seconds: Histogram<f64>,
}

impl FirewallMetrics {
    fn new(meter: &Meter) -> Self {
        Self {
            access_check_duration_seconds: meter
                .f64_histogram("hub_router.firewall.access_check.duration_seconds")
                .with_description(
                    "Latency of one firewall rule-set evaluation (Manager::check_access), labeled by outcome reason",
                )
                .with_unit("s")
                .build(),
        }
    }
}

static METRICS: OnceLock<RwLock<FirewallMetrics>> = OnceLock::new();

fn cell() -> &'static RwLock<FirewallMetrics> {
    METRICS.get_or_init(|| {
        RwLock::new(FirewallMetrics::new(&opentelemetry::global::meter(
            "hub-router-firewall",
        )))
    })
}

/// Records one [`crate::manager::Manager::check_access`] call's latency,
/// labeled by outcome reason (`"allow"` / `"deny_matched"` /
/// `"deny_no_match"` / `"deny_no_rules"` — see
/// [`crate::engine::CheckOutcome::reason`]). A no-op against the real
/// exporter if no OTLP meter provider has been installed yet — never
/// panics either way (critical-rules.md: a dead exporter never breaks
/// the app).
pub fn record_access_check(duration_secs: f64, reason: &str) {
    let attrs = [KeyValue::new("reason", reason.to_string())];
    let metrics = cell().read().unwrap_or_else(PoisonError::into_inner);
    metrics
        .access_check_duration_seconds
        .record(duration_secs, &attrs);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recording_before_any_provider_is_installed_never_panics() {
        record_access_check(0.001, "allow");
        record_access_check(0.002, "deny_no_match");
        record_access_check(0.0005, "deny_no_rules");
    }
}
