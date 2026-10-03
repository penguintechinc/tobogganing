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
//!
//! Mirrors `engines/testserver-rs`'s `testserver::telemetry` module
//! exactly, with this service's own instrument names (request + inbound
//! JWT-verification latency, the two histograms this PR's middleware
//! produces).

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
/// `opentelemetry-appender-tracing`). Returns the provider handles so
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
/// request instruments (see [`record_request`]/[`record_jwt_verify`]) to
/// whichever provider results, so those call sites never need to branch on
/// whether OTLP is actually configured. Returns the provider so `main` can
/// flush/shut it down; `None` means OTLP metric export is disabled.
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

    let meter = opentelemetry::global::meter(service_name);
    *router_metrics_cell()
        .write()
        .unwrap_or_else(std::sync::PoisonError::into_inner) = RouterMetrics::new(&meter);

    provider
}

/// Histograms (request/verify latency — the load/latency signal
/// critical-rules.md flags as "most-often-missing") + counters, recorded
/// against whichever meter [`init_meter_provider`] most recently installed.
struct RouterMetrics {
    request_duration_seconds: Histogram<f64>,
    requests_total: Counter<u64>,
    jwt_verify_duration_seconds: Histogram<f64>,
    jwt_verify_total: Counter<u64>,
}

impl RouterMetrics {
    fn new(meter: &Meter) -> Self {
        Self {
            request_duration_seconds: meter
                .f64_histogram("hub_router.request.duration_seconds")
                .with_description("Inbound HTTP request latency in seconds, labeled by route")
                .with_unit("s")
                .build(),
            requests_total: meter
                .u64_counter("hub_router.request.total")
                .with_description("Count of inbound HTTP requests, labeled by route and status")
                .build(),
            jwt_verify_duration_seconds: meter
                .f64_histogram("hub_router.jwt_verify.duration_seconds")
                .with_description("Inbound JWT verification latency in seconds")
                .with_unit("s")
                .build(),
            jwt_verify_total: meter
                .u64_counter("hub_router.jwt_verify.total")
                .with_description("Count of inbound JWT verification attempts, labeled by outcome")
                .build(),
        }
    }
}

/// Process-wide instrument cache, lazily created on first access against
/// whatever meter provider is globally installed *at that moment* (the
/// OTel no-op provider if [`init_meter_provider`] hasn't run yet — both
/// record functions are always safe to call). [`init_meter_provider`]
/// rebinds the contents in place once the real (or explicitly-disabled)
/// provider is known.
static ROUTER_METRICS: OnceLock<std::sync::RwLock<RouterMetrics>> = OnceLock::new();

fn router_metrics_cell() -> &'static std::sync::RwLock<RouterMetrics> {
    ROUTER_METRICS.get_or_init(|| {
        std::sync::RwLock::new(RouterMetrics::new(&opentelemetry::global::meter(
            "hub-router",
        )))
    })
}

/// Records one inbound HTTP request's latency against the OTLP metrics
/// pipeline — histogram first, then a labeled counter. A no-op if OTLP
/// export is disabled; a dead/unreachable OTLP collector never blocks or
/// fails the caller (critical-rules.md: "a dead exporter never breaks the
/// app").
pub fn record_request(route: &str, duration_secs: f64, status: u16) {
    let attrs = [
        opentelemetry::KeyValue::new("route", route.to_string()),
        opentelemetry::KeyValue::new("status", i64::from(status)),
    ];
    let metrics = router_metrics_cell()
        .read()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    metrics
        .request_duration_seconds
        .record(duration_secs, &attrs);
    metrics.requests_total.add(1, &attrs);
}

/// Records one inbound JWT verification attempt's latency — separate from
/// [`record_request`] so verify-step latency is visible independent of
/// whatever the route handler itself does afterward.
pub fn record_jwt_verify(duration_secs: f64, outcome: &str) {
    let attrs = [opentelemetry::KeyValue::new("outcome", outcome.to_string())];
    let metrics = router_metrics_cell()
        .read()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    metrics
        .jwt_verify_duration_seconds
        .record(duration_secs, &attrs);
    metrics.jwt_verify_total.add(1, &attrs);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn record_functions_before_init_are_silent_noops() {
        // Whether ROUTER_METRICS happens to already be populated by a real
        // provider depends on test execution order within this process
        // (process-global); the only real invariant under test is that
        // calling these never panics either way.
        record_request("/health", 0.001, 200);
        record_jwt_verify(0.0005, "valid");
    }

    #[test]
    fn init_meter_provider_without_otlp_endpoint_is_disabled_but_populates_instruments() {
        // SAFETY: single-threaded assertion against a process-global env
        // var — tests/telemetry_smoke.rs is a *separate* test
        // binary/process, so there is no cross-test race here.
        unsafe {
            std::env::remove_var("OTEL_EXPORTER_OTLP_ENDPOINT");
        }
        let provider = init_meter_provider("hub-router-unit-test");
        assert!(provider.is_none());
        record_request("/health", 0.5, 200);
        record_jwt_verify(0.001, "invalid");
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
        // `PrometheusBuilder::install()` sets the process-wide global
        // `metrics` recorder — can only succeed once per process, so this
        // must be the *only* test in this binary calling `init_metrics`.
        // Port 0 lets the OS pick an ephemeral one.
        init_metrics(0);
    }

    #[test]
    fn init_tracing_without_otlp_endpoint_logs_a_warning_and_disables_otlp_export() {
        // `tracing_subscriber::registry().init()` sets the process-wide
        // default subscriber — can only succeed once per process, so this
        // must be the *only* test in this binary calling `init_tracing`.
        unsafe {
            std::env::remove_var("OTEL_EXPORTER_OTLP_ENDPOINT");
        }
        let providers = init_tracing("hub-router-unit-test");
        assert!(providers.tracer_provider.is_none());
        assert!(providers.logger_provider.is_none());
        providers.force_flush();
    }
}
