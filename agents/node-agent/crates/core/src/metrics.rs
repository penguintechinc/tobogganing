//! Shared OTLP histogram helpers for the agent's real work: enrollment,
//! WireGuard connectivity bring-up, and access-token refresh latency —
//! the three call sites `agents/node-agent` and `node-agent-connectivity`
//! actually perform, per critical-rules.md Observability's "histograms for
//! load/latency first" rule.
//!
//! Callable from any workspace crate via `opentelemetry::global::meter`,
//! the process-global meter API — this module depends on the lightweight
//! `opentelemetry` API crate only, never the SDK/OTLP-exporter crates.
//! Before `node-agent`'s `telemetry::init` installs a real
//! [`opentelemetry_sdk`] meter provider (or when `OTEL_EXPORTER_OTLP_ENDPOINT`
//! is unset), the global default is a no-op meter, so every call here is
//! always safe and never blocks or panics — recording a value is simply
//! dropped until a real provider is installed.

use opentelemetry::metrics::Histogram;
use opentelemetry::KeyValue;
use std::sync::OnceLock;
use std::time::Instant;

/// The single meter instance shared by every histogram in this module —
/// one `opentelemetry::global::meter()` call, cached for the process
/// lifetime rather than re-resolved (and re-registered against the global
/// provider) on every record.
fn meter() -> &'static opentelemetry::metrics::Meter {
    static METER: OnceLock<opentelemetry::metrics::Meter> = OnceLock::new();
    METER.get_or_init(|| opentelemetry::global::meter("node-agent"))
}

/// Records `elapsed` (seconds) against a named latency histogram, tagged
/// with `outcome` (`"ok"` or `"error"`/`"degraded"`) — the shared shape
/// every call site below uses, mirroring `testserver-rs`'s
/// `record_probe()` labeled-histogram pattern.
fn record_seconds(name: &'static str, description: &'static str, elapsed_secs: f64, outcome: &str) {
    static HISTOGRAMS: OnceLock<
        std::sync::Mutex<std::collections::HashMap<&'static str, Histogram<f64>>>,
    > = OnceLock::new();
    let cache = HISTOGRAMS.get_or_init(|| std::sync::Mutex::new(std::collections::HashMap::new()));
    // A poisoned lock (a prior recorder panicking mid-insert) must not take
    // telemetry recording down with it — recover the inner map and carry on
    // rather than propagating the panic into hot agent logic.
    let mut guard = cache
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    let histogram = guard.entry(name).or_insert_with(|| {
        meter()
            .f64_histogram(name)
            .with_description(description)
            .with_unit("s")
            .build()
    });
    histogram.record(
        elapsed_secs,
        &[KeyValue::new("outcome", outcome.to_string())],
    );
}

/// Records one enrollment round-trip's duration (control-plane `enroll`
/// RPC, `agents/node-agent` runs this exactly once at startup).
pub fn record_enrollment_latency(elapsed: std::time::Duration, outcome: &str) {
    record_seconds(
        "node_agent_enrollment_duration_seconds",
        "Duration of this node's single enrollment round-trip with the control plane",
        elapsed.as_secs_f64(),
        outcome,
    );
}

/// Records one WireGuard interface bring-up/reapply's duration
/// (`node-agent-connectivity`'s `bring_up`, called on first connectivity
/// config and every subsequent config change).
pub fn record_connectivity_latency(elapsed: std::time::Duration, outcome: &str) {
    record_seconds(
        "node_agent_connectivity_bringup_duration_seconds",
        "Duration of a WireGuard interface create/apply cycle",
        elapsed.as_secs_f64(),
        outcome,
    );
}

/// Records one access-token refresh round-trip's duration (the lifecycle
/// loop's `refresh_token` RPC, called once per tick within the expiry
/// margin).
pub fn record_refresh_latency(elapsed: std::time::Duration, outcome: &str) {
    record_seconds(
        "node_agent_refresh_duration_seconds",
        "Duration of an access-token refresh round-trip with the control plane",
        elapsed.as_secs_f64(),
        outcome,
    );
}

/// Small helper so call sites read as `let _t = metrics::timer(); ... record(_t.elapsed(), outcome)`
/// without every caller re-importing `std::time::Instant` directly.
pub fn start_timer() -> Instant {
    Instant::now()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Against the process-default no-op meter provider (no
    /// `telemetry::init` call in this crate's own unit tests), every
    /// recorder must be a safe no-op — proves the "always safe to call"
    /// contract in this module's doc comment rather than assuming it.
    #[test]
    fn every_recorder_is_safe_against_the_default_noop_meter_provider() {
        let start = start_timer();
        record_enrollment_latency(start.elapsed(), "ok");
        record_connectivity_latency(start.elapsed(), "degraded");
        record_refresh_latency(start.elapsed(), "error");
    }
}
