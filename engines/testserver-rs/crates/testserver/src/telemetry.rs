//! Tracing (structured logs, never `println!`) + OTLP export + Prometheus
//! `/metrics` — both signal paths run together per critical-rules.md
//! Observability (OTel): OTLP is the primary transport, Prometheus is the
//! secondary HPA/ServiceMonitor scrape surface. The OTLP endpoint is always
//! env-configurable (`OTEL_EXPORTER_OTLP_ENDPOINT`) — never hardcoded.

use opentelemetry::trace::TracerProvider as _;
use opentelemetry_sdk::Resource;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use tracing_subscriber::EnvFilter;

/// Initializes the global `tracing` subscriber: an `EnvFilter` (INFO
/// default per critical-rules.md Observability, `RUST_LOG` overrides),
/// JSON-formatted stdout logging, and — only when
/// `OTEL_EXPORTER_OTLP_ENDPOINT` is set — an OTLP span exporter. Returns the
/// tracer provider so `main` can flush it on shutdown; `None` means OTLP
/// export is disabled (dev/test), logging still works either way.
pub fn init_tracing(service_name: &str) -> Option<opentelemetry_sdk::trace::SdkTracerProvider> {
    let env_filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));

    let provider = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT")
        .ok()
        .and_then(|_| {
            let exporter = opentelemetry_otlp::SpanExporter::builder()
                .with_tonic()
                .build()
                .inspect_err(|e| eprintln!("otlp span exporter init failed: {e}"))
                .ok()?;
            Some(
                opentelemetry_sdk::trace::SdkTracerProvider::builder()
                    .with_batch_exporter(exporter)
                    .with_resource(
                        Resource::builder()
                            .with_service_name(service_name.to_string())
                            .build(),
                    )
                    .build(),
            )
        });

    let otel_layer = provider
        .as_ref()
        .map(|p| tracing_opentelemetry::layer().with_tracer(p.tracer(service_name.to_string())));

    tracing_subscriber::registry()
        .with(env_filter)
        .with(tracing_subscriber::fmt::layer().json())
        .with(otel_layer)
        .init();

    if provider.is_none() {
        tracing::warn!(
            "OTEL_EXPORTER_OTLP_ENDPOINT unset — OTLP span export disabled (logs still emitted)"
        );
    }

    provider
}

/// Installs the Prometheus `/metrics` HTTP exporter on `port` — secondary
/// scrape surface for HPA/ServiceMonitor alongside OTLP metrics (not yet
/// wired in this PR: OTLP metrics export is a TODO alongside the OTLP
/// meter provider; Prometheus covers the mandatory `/metrics` surface today).
pub fn init_metrics(port: u16) {
    metrics_exporter_prometheus::PrometheusBuilder::new()
        .with_http_listener(([0, 0, 0, 0], port))
        .install()
        .expect("failed to install Prometheus exporter");
}
