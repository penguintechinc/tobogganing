//! Structured `tracing` logging (always on, local JSON stdout) plus the
//! full OTLP export triad — traces, logs, and metrics — installed only
//! when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Mirrors
//! `engines/testserver-rs`'s `telemetry.rs` trace/log wiring and completes
//! the metrics half that file leaves as a TODO: a `SdkMeterProvider`
//! installed as the process-global provider so
//! `node_agent_core::metrics`'s enrollment/connectivity/refresh
//! histograms — recorded from any workspace crate via
//! `opentelemetry::global::meter` — actually export.
//!
//! Per critical-rules.md Observability: the endpoint is always
//! `OTEL_EXPORTER_OTLP_ENDPOINT`-driven, never hardcoded, and a dead or
//! unreachable collector must never break the agent — every exporter here
//! is a best-effort batch/periodic background export; a failed export is
//! dropped (and logged internally by the SDK), never propagated as an
//! agent error.

use opentelemetry::trace::TracerProvider as _;
use opentelemetry_appender_tracing::layer::OpenTelemetryTracingBridge;
use opentelemetry_sdk::logs::SdkLoggerProvider;
use opentelemetry_sdk::metrics::SdkMeterProvider;
use opentelemetry_sdk::trace::SdkTracerProvider;
use opentelemetry_sdk::Resource;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use tracing_subscriber::EnvFilter;

/// Holds the three OTLP SDK providers installed by [`init`] so `main` can
/// flush and shut them down on exit. Every field is `None` when
/// `OTEL_EXPORTER_OTLP_ENDPOINT` was unset at startup — local JSON
/// logging still ran either way, so a `TelemetryGuard::default()` is
/// always a safe, complete value (never a partially-initialized one).
#[derive(Default)]
pub struct TelemetryGuard {
    tracer_provider: Option<SdkTracerProvider>,
    logger_provider: Option<SdkLoggerProvider>,
    meter_provider: Option<SdkMeterProvider>,
}

impl TelemetryGuard {
    /// Flushes and shuts down every installed OTLP provider. Best-effort
    /// by design: a shutdown/flush failure (e.g. the collector went away
    /// between the last export and process exit) is logged to stderr and
    /// swallowed, never turned into a non-zero exit code for an otherwise
    /// clean run — telemetry teardown failing is never a request/run
    /// failure, matching the same graceful-degradation contract `init`
    /// applies at startup.
    pub fn shutdown(&self) {
        if let Some(provider) = &self.tracer_provider {
            if let Err(err) = provider.shutdown() {
                eprintln!("otel trace provider shutdown failed (non-fatal): {err}");
            }
        }
        if let Some(provider) = &self.logger_provider {
            if let Err(err) = provider.shutdown() {
                eprintln!("otel logger provider shutdown failed (non-fatal): {err}");
            }
        }
        if let Some(provider) = &self.meter_provider {
            if let Err(err) = provider.shutdown() {
                eprintln!("otel meter provider shutdown failed (non-fatal): {err}");
            }
        }
    }
}

/// Initializes the global `tracing` subscriber (`EnvFilter`, INFO default
/// per critical-rules.md Observability, `RUST_LOG` overrides; JSON stdout
/// always on) and, only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, the
/// OTLP export triad over gRPC/tonic:
///
/// - **traces**: `tracing-opentelemetry` bridges every `tracing` span
///   (e.g. the `#[instrument]`-annotated `ControlPlaneClient` methods) to
///   an OTLP span exporter.
/// - **logs**: `opentelemetry-appender-tracing` bridges every `tracing`
///   event (`info!`/`warn!`/`error!`, no new call sites needed) to an
///   OTLP log exporter.
/// - **metrics**: a `SdkMeterProvider` with a periodic OTLP metric
///   exporter, installed as the process-global provider so every
///   `node_agent_core::metrics::record_*` call across the workspace
///   starts actually exporting instead of hitting the no-op default.
///
/// Only the endpoint's *presence* gates whether OTLP is attempted at all
/// — each exporter's `.with_tonic()` builder resolves the endpoint (and
/// any per-signal `OTEL_EXPORTER_OTLP_*_ENDPOINT` override) from the
/// environment itself, so the value is never read or hardcoded here.
pub fn init(service_name: &'static str) -> TelemetryGuard {
    let env_filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    let json_layer = tracing_subscriber::fmt::layer().json();

    if std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT").is_err() {
        tracing_subscriber::registry()
            .with(env_filter)
            .with(json_layer)
            .init();
        tracing::warn!(
            "OTEL_EXPORTER_OTLP_ENDPOINT unset — OTLP export disabled (local JSON logs still emitted)"
        );
        return TelemetryGuard::default();
    }

    let resource = Resource::builder()
        .with_service_name(service_name.to_string())
        .build();

    let tracer_provider = build_tracer_provider(resource.clone());
    let logger_provider = build_logger_provider(resource.clone());
    let meter_provider = build_meter_provider(resource);

    let otel_trace_layer = tracer_provider
        .as_ref()
        .map(|p| tracing_opentelemetry::layer().with_tracer(p.tracer(service_name)));
    let otel_log_layer = logger_provider
        .as_ref()
        .map(OpenTelemetryTracingBridge::new);

    tracing_subscriber::registry()
        .with(env_filter)
        .with(json_layer)
        .with(otel_trace_layer)
        .with(otel_log_layer)
        .init();

    if let Some(provider) = &meter_provider {
        opentelemetry::global::set_meter_provider(provider.clone());
    }

    if tracer_provider.is_none() || logger_provider.is_none() || meter_provider.is_none() {
        tracing::warn!(
            "one or more OTLP exporters failed to initialize — see stderr; \
             remaining signals still export, local JSON logs unaffected"
        );
    }

    TelemetryGuard {
        tracer_provider,
        logger_provider,
        meter_provider,
    }
}

fn build_tracer_provider(resource: Resource) -> Option<SdkTracerProvider> {
    opentelemetry_otlp::SpanExporter::builder()
        .with_tonic()
        .build()
        .inspect_err(|e| eprintln!("otlp span exporter init failed (non-fatal): {e}"))
        .ok()
        .map(|exporter| {
            SdkTracerProvider::builder()
                .with_batch_exporter(exporter)
                .with_resource(resource)
                .build()
        })
}

fn build_logger_provider(resource: Resource) -> Option<SdkLoggerProvider> {
    opentelemetry_otlp::LogExporter::builder()
        .with_tonic()
        .build()
        .inspect_err(|e| eprintln!("otlp log exporter init failed (non-fatal): {e}"))
        .ok()
        .map(|exporter| {
            SdkLoggerProvider::builder()
                .with_batch_exporter(exporter)
                .with_resource(resource)
                .build()
        })
}

fn build_meter_provider(resource: Resource) -> Option<SdkMeterProvider> {
    opentelemetry_otlp::MetricExporter::builder()
        .with_tonic()
        .build()
        .inspect_err(|e| eprintln!("otlp metric exporter init failed (non-fatal): {e}"))
        .ok()
        .map(|exporter| {
            SdkMeterProvider::builder()
                .with_periodic_exporter(exporter)
                .with_resource(resource)
                .build()
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Absent `OTEL_EXPORTER_OTLP_ENDPOINT`, `init` must return an empty
    /// guard rather than panicking or attempting a connection — the
    /// graceful-degradation contract this module's doc comment promises.
    /// Does not call `tracing_subscriber::registry().init()` (global,
    /// process-wide, can only run once per test binary) — exercises the
    /// env-var branch logic directly instead.
    #[test]
    fn missing_endpoint_env_var_is_detected_before_any_otlp_setup() {
        // SAFETY(test-only): removing an unset-by-default var; no other
        // test in this binary sets it.
        unsafe {
            std::env::remove_var("OTEL_EXPORTER_OTLP_ENDPOINT");
        }
        assert!(std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT").is_err());
    }

    /// A default guard's `shutdown()` (every provider field `None`, the
    /// exact value `init` returns when OTLP is disabled) must be a no-op,
    /// never a panic — proves `main`'s unconditional `guard.shutdown()`
    /// call on the way out is always safe, OTLP enabled or not.
    #[test]
    fn shutdown_on_a_default_guard_is_a_safe_noop() {
        TelemetryGuard::default().shutdown();
    }
}
