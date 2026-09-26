//! Tracing (structured logs, never `println!`) + OTLP export (traces,
//! logs, metrics) + Prometheus `/metrics` — all four signal paths run
//! together per critical-rules.md Observability (OTel): OTLP is the
//! primary transport, Prometheus is the secondary HPA/ServiceMonitor
//! scrape surface. The OTLP endpoint is always env-configurable
//! (`OTEL_EXPORTER_OTLP_ENDPOINT`) — never hardcoded. A dead/unset
//! exporter never breaks a request: every OTLP path here degrades to a
//! documented no-op (in-process fmt logging keeps working; OTel
//! instruments fall back to the global no-op provider) rather than
//! panicking or blocking.

use opentelemetry::metrics::{Counter, Histogram, Meter};
use opentelemetry::trace::TracerProvider as _;
use opentelemetry_appender_tracing::layer::OpenTelemetryTracingBridge;
use opentelemetry_sdk::logs::SdkLoggerProvider;
use opentelemetry_sdk::metrics::SdkMeterProvider;
use opentelemetry_sdk::trace::SdkTracerProvider;
use opentelemetry_sdk::Resource;
use std::sync::OnceLock;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use tracing_subscriber::EnvFilter;

/// Bundles the two provider handles `main`/tests must keep alive (dropping
/// either flushes+shuts down its exporter) and can explicitly flush before
/// process exit or, in tests, before asserting against a mock collector.
/// `None` in either field means that signal's OTLP export is disabled
/// (`OTEL_EXPORTER_OTLP_ENDPOINT` unset) — logging to stdout and the
/// Prometheus `/metrics` surface keep working regardless.
pub struct TelemetryProviders {
    pub tracer_provider: Option<SdkTracerProvider>,
    pub logger_provider: Option<SdkLoggerProvider>,
}

impl TelemetryProviders {
    /// Forces an immediate export attempt on both signal pipelines rather
    /// than waiting for their batch processors' normal flush interval —
    /// used by the telemetry-validation smoke test so assertions don't
    /// race the batch timer, and by graceful shutdown so in-flight
    /// telemetry isn't dropped on exit.
    pub fn force_flush(&self) {
        if let Some(p) = &self.tracer_provider {
            if let Err(e) = p.force_flush() {
                tracing::warn!(error = %e, "otlp trace force_flush failed");
            }
        }
        if let Some(p) = &self.logger_provider {
            if let Err(e) = p.force_flush() {
                tracing::warn!(error = %e, "otlp log force_flush failed");
            }
        }
    }
}

/// Initializes the global `tracing` subscriber: an `EnvFilter` (INFO
/// default per critical-rules.md Observability, `RUST_LOG` overrides),
/// JSON-formatted stdout logging (always on), and — only when
/// `OTEL_EXPORTER_OTLP_ENDPOINT` is set — an OTLP span exporter and an
/// OTLP log exporter (bridged from the same `tracing` events via
/// `opentelemetry-appender-tracing`, so every `tracing::info!`/`warn!`/etc.
/// call site becomes both a JSON stdout line and an OTLP LogRecord with no
/// separate call site to maintain). Returns the provider handles so
/// `main` can flush them on shutdown; `None` fields mean that signal's
/// OTLP export is disabled (dev/test), stdout logging still works either
/// way.
pub fn init_tracing(service_name: &'static str) -> TelemetryProviders {
    let env_filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    let otlp_endpoint = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT").ok();

    let tracer_provider = otlp_endpoint.as_ref().and_then(|_| {
        let exporter = opentelemetry_otlp::SpanExporter::builder()
            .with_tonic()
            .build()
            .inspect_err(|e| eprintln!("otlp span exporter init failed: {e}"))
            .ok()?;
        Some(
            SdkTracerProvider::builder()
                .with_batch_exporter(exporter)
                .with_resource(
                    Resource::builder()
                        .with_service_name(service_name.to_string())
                        .build(),
                )
                .build(),
        )
    });

    let logger_provider = otlp_endpoint.as_ref().and_then(|_| {
        let exporter = opentelemetry_otlp::LogExporter::builder()
            .with_tonic()
            .build()
            .inspect_err(|e| eprintln!("otlp log exporter init failed: {e}"))
            .ok()?;
        Some(
            SdkLoggerProvider::builder()
                .with_batch_exporter(exporter)
                .with_resource(
                    Resource::builder()
                        .with_service_name(service_name.to_string())
                        .build(),
                )
                .build(),
        )
    });

    let otel_trace_layer = tracer_provider
        .as_ref()
        .map(|p| tracing_opentelemetry::layer().with_tracer(p.tracer(service_name.to_string())));
    let otel_log_layer = logger_provider
        .as_ref()
        .map(OpenTelemetryTracingBridge::new);

    tracing_subscriber::registry()
        .with(env_filter)
        .with(tracing_subscriber::fmt::layer().json())
        .with(otel_trace_layer)
        .with(otel_log_layer)
        .init();

    if otlp_endpoint.is_none() {
        tracing::warn!(
            "OTEL_EXPORTER_OTLP_ENDPOINT unset — OTLP span/log export disabled (stdout logging still emitted)"
        );
    }

    TelemetryProviders {
        tracer_provider,
        logger_provider,
    }
}

/// Installs the Prometheus `/metrics` HTTP exporter on `port` — secondary
/// scrape surface for HPA/ServiceMonitor alongside the OTLP metrics
/// pipeline (see [`init_meter_provider`]).
pub fn init_metrics(port: u16) {
    metrics_exporter_prometheus::PrometheusBuilder::new()
        .with_http_listener(([0, 0, 0, 0], port))
        .install()
        .expect("failed to install Prometheus exporter");
}

/// Initializes the OTLP metrics pipeline: an `opentelemetry_sdk` meter
/// provider backed by a periodic OTLP exporter, only when
/// `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Also (re)binds the process-wide
/// probe instruments (see [`record_probe`]) to whichever provider results
/// — a real OTLP-backed meter when the endpoint is configured, otherwise
/// the OpenTelemetry no-op meter, so `record_probe` call sites never need
/// to branch on whether OTLP is actually configured (a dead/absent
/// exporter is always a silent no-op, never a panic or a blocked request).
/// Returns the provider so `main` can flush/shut it down; `None` means
/// OTLP metric export is disabled.
pub fn init_meter_provider(service_name: &'static str) -> Option<SdkMeterProvider> {
    let provider = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT")
        .ok()
        .and_then(|_| {
            let exporter = opentelemetry_otlp::MetricExporter::builder()
                .with_tonic()
                .build()
                .inspect_err(|e| eprintln!("otlp metric exporter init failed: {e}"))
                .ok()?;
            Some(
                SdkMeterProvider::builder()
                    .with_periodic_exporter(exporter)
                    .with_resource(
                        Resource::builder()
                            .with_service_name(service_name.to_string())
                            .build(),
                    )
                    .build(),
            )
        });

    match &provider {
        Some(p) => opentelemetry::global::set_meter_provider(p.clone()),
        None => {
            tracing::warn!(
                "OTEL_EXPORTER_OTLP_ENDPOINT unset — OTLP metric export disabled (Prometheus /metrics still served)"
            );
        }
    }

    // Rebind the cached probe instruments to whatever provider is now
    // globally installed — see `probe_metrics_cell()`'s doc comment for why
    // this is a rebind-in-place (`RwLock`), not a lazily-populated
    // `OnceLock`: `init_meter_provider` can run more than once in a single
    // process (e.g. the telemetry smoke test re-initializing with a mock
    // collector endpoint after an earlier disabled call), and a plain
    // `OnceLock::set` would silently keep the *first* call's (possibly
    // no-op) instruments forever.
    let meter = opentelemetry::global::meter(service_name);
    *probe_metrics_cell()
        .write()
        .unwrap_or_else(std::sync::PoisonError::into_inner) = ProbeMetrics::new(&meter);

    provider
}

/// Histogram (probe latency — the load/latency signal critical-rules.md
/// flags as "most-often-missing") + counter (probe event count) recorded
/// against whichever meter [`init_meter_provider`] most recently installed.
struct ProbeMetrics {
    duration_seconds: Histogram<f64>,
    probes_total: Counter<u64>,
}

impl ProbeMetrics {
    fn new(meter: &Meter) -> Self {
        Self {
            duration_seconds: meter
                .f64_histogram("testserver.probe.duration_seconds")
                .with_description("Probe execution latency in seconds, labeled by probe_type")
                .with_unit("s")
                .build(),
            probes_total: meter
                .u64_counter("testserver.probe.total")
                .with_description("Count of probe executions, labeled by probe_type and success")
                .build(),
        }
    }
}

/// Process-wide probe instrument cache, lazily created on first access
/// against whatever meter provider is globally installed *at that moment*
/// (the OTel no-op provider if [`init_meter_provider`] hasn't run yet —
/// [`record_probe`] is always safe to call). [`init_meter_provider`]
/// rebinds the contents in place once the real (or explicitly-disabled)
/// provider is known, so instruments always reflect the most recent call.
static PROBE_METRICS: OnceLock<std::sync::RwLock<ProbeMetrics>> = OnceLock::new();

fn probe_metrics_cell() -> &'static std::sync::RwLock<ProbeMetrics> {
    PROBE_METRICS.get_or_init(|| {
        std::sync::RwLock::new(ProbeMetrics::new(&opentelemetry::global::meter(
            "testserver",
        )))
    })
}

/// Records one probe execution against the OTLP metrics pipeline —
/// histogram first (latency), then a labeled counter (event). A no-op
/// (falls back to the OTel no-op meter) if [`init_meter_provider`] was
/// never called or OTLP export is disabled; callers never need to check,
/// and a dead/unreachable OTLP collector never blocks or fails the caller
/// (the SDK's exporter buffers/drops internally — see critical-rules.md
/// Observability's "a dead exporter never breaks the app").
pub fn record_probe(probe_type: &str, duration_secs: f64, success: bool) {
    let attrs = [
        opentelemetry::KeyValue::new("probe_type", probe_type.to_string()),
        opentelemetry::KeyValue::new("success", success),
    ];
    let metrics = probe_metrics_cell()
        .read()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    metrics.duration_seconds.record(duration_secs, &attrs);
    metrics.probes_total.add(1, &attrs);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn record_probe_before_init_is_a_silent_noop() {
        // Whether PROBE_METRICS' RwLock happens to already be populated by
        // a real provider depends on test execution order within this
        // process (it's process-global, and other tests in this binary may
        // have called init_meter_provider first); the only real invariant
        // under test is that calling record_probe never panics either way.
        record_probe("smoke", 0.001, true);
    }

    #[test]
    fn init_meter_provider_without_otlp_endpoint_is_disabled_but_populates_instruments() {
        // SAFETY: single-threaded assertion against a process-global env var
        // — no other test in this binary sets OTEL_EXPORTER_OTLP_ENDPOINT
        // (tests/telemetry_smoke.rs is a *separate* test binary/process, so
        // there is no cross-test race here).
        unsafe {
            std::env::remove_var("OTEL_EXPORTER_OTLP_ENDPOINT");
        }
        let provider = init_meter_provider("testserver-unit-test");
        assert!(provider.is_none());
        // Must not panic even though export is disabled.
        record_probe("http", 0.5, true);
    }

    #[test]
    fn telemetry_providers_force_flush_is_a_noop_when_otlp_disabled() {
        let providers = TelemetryProviders {
            tracer_provider: None,
            logger_provider: None,
        };
        providers.force_flush();
    }

    #[test]
    fn init_metrics_installs_the_prometheus_exporter() {
        // `metrics_exporter_prometheus::PrometheusBuilder::install()` sets
        // the process-wide global `metrics` recorder — can only succeed
        // once per process, so this must be the *only* test in this binary
        // calling `init_metrics`. Port 0 lets the OS pick an ephemeral one.
        init_metrics(0);
    }

    #[test]
    fn init_tracing_without_otlp_endpoint_logs_a_warning_and_disables_otlp_export() {
        // `tracing_subscriber::registry().init()` sets the process-wide
        // default subscriber — can only succeed once per process, so this
        // must be the *only* test in this binary calling `init_tracing`
        // (tests/telemetry_smoke.rs exercises the OTLP-enabled path in its
        // own separate test binary/process).
        unsafe {
            std::env::remove_var("OTEL_EXPORTER_OTLP_ENDPOINT");
        }
        let providers = init_tracing("testserver-unit-test");
        assert!(providers.tracer_provider.is_none());
        assert!(providers.logger_provider.is_none());
        providers.force_flush();
    }
}
