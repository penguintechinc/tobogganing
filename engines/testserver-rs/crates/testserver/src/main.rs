//! WaddlePerf diagnostic probe target — Rust rewrite of `engines/testserver`
//! (Go). Serves REST (axum, `:8080`) + gRPC (tonic, `:50051`) surfaces
//! against the same probe implementations (`testserver-protocols`), backed
//! by SeaORM (`testserver-db`) with a degraded-start/reconnect DB lifecycle,
//! and emits OTLP traces + Prometheus metrics (`:9090`).

use clap::{Parser, Subcommand};
use std::time::Duration;
use testserver::telemetry;
use testserver_core::AppConfig;
use tokio_util::sync::CancellationToken;

#[derive(Parser)]
#[command(
    name = "testserver",
    version,
    about = "WaddlePerf diagnostic probe target"
)]
struct Cli {
    #[command(subcommand)]
    command: Option<Command>,
}

#[derive(Subcommand)]
enum Command {
    /// Run the HTTP + gRPC servers (default when no subcommand is given).
    Run,
    /// Native Rust liveness check for the container HEALTHCHECK — never
    /// curl, per devops-containers.md.
    Healthcheck,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let cli = Cli::parse();
    match cli.command.unwrap_or(Command::Run) {
        Command::Run => run().await,
        Command::Healthcheck => healthcheck().await,
    }
}

/// Reads `PORT` for the healthcheck's target — pure/no I/O so it's
/// unit-testable without mutating the process environment (mirrors
/// `testserver_core::config`'s env-var-parsing test pattern).
fn healthcheck_port(raw: Option<&str>) -> u16 {
    raw.and_then(|v| v.parse::<u16>().ok()).unwrap_or(8080)
}

async fn healthcheck() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let port = healthcheck_port(std::env::var("PORT").ok().as_deref());

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()?;
    let url = format!("http://127.0.0.1:{port}/health");

    match client.get(&url).send().await {
        Ok(resp) if resp.status().is_success() => Ok(()),
        Ok(resp) => {
            eprintln!("healthcheck: unhealthy status {}", resp.status());
            std::process::exit(1);
        }
        Err(e) => {
            eprintln!("healthcheck: request failed: {e}");
            std::process::exit(1);
        }
    }
}

async fn run() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    // Fails closed here (never starts with auth silently unenforceable) if
    // AUTH_ENABLED=true and no ES256 JWT public key is configured, or if a
    // configured key is malformed — see testserver_core::config::ConfigError.
    let cfg = AppConfig::from_env()?;
    let telemetry_providers = telemetry::init_tracing("testserver");
    let meter_provider = telemetry::init_meter_provider("testserver");
    telemetry::init_metrics(cfg.metrics_port);
    testserver_protocols::tls_provider::install_crypto_provider();

    let shutdown = CancellationToken::new();
    let signal_shutdown = shutdown.clone();
    tokio::spawn(async move {
        testserver::app::wait_for_os_shutdown_signal().await;
        signal_shutdown.cancel();
    });

    let result = testserver::app::serve(&cfg, shutdown).await;

    // Flush any batched-but-not-yet-exported traces/logs/metrics before
    // exit — graceful shutdown must not silently drop in-flight telemetry.
    telemetry_providers.force_flush();
    if let Some(provider) = &meter_provider {
        if let Err(e) = provider.force_flush() {
            tracing::warn!(error = %e, "otlp metric force_flush failed");
        }
    }

    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn healthcheck_port_defaults_when_unset_or_unparseable() {
        assert_eq!(healthcheck_port(None), 8080);
        assert_eq!(healthcheck_port(Some("")), 8080);
        assert_eq!(healthcheck_port(Some("not-a-port")), 8080);
        assert_eq!(healthcheck_port(Some("99999999")), 8080); // out of u16 range
    }

    #[test]
    fn healthcheck_port_parses_valid_value() {
        assert_eq!(healthcheck_port(Some("9091")), 9091);
    }

    #[test]
    fn cli_defaults_to_run_when_no_subcommand_given() {
        let cli = Cli::try_parse_from(["testserver"]).expect("no subcommand must parse");
        assert!(cli.command.is_none());
        // Mirrors main()'s `unwrap_or(Command::Run)` dispatch — the actual
        // branch under test there, not just the parser.
        assert!(matches!(cli.command.unwrap_or(Command::Run), Command::Run));
    }

    #[test]
    fn cli_parses_run_subcommand_explicitly() {
        let cli = Cli::try_parse_from(["testserver", "run"]).expect("must parse");
        assert!(matches!(cli.command, Some(Command::Run)));
    }

    #[test]
    fn cli_parses_healthcheck_subcommand() {
        let cli = Cli::try_parse_from(["testserver", "healthcheck"]).expect("must parse");
        assert!(matches!(cli.command, Some(Command::Healthcheck)));
    }

    #[test]
    fn cli_rejects_unknown_subcommand() {
        assert!(Cli::try_parse_from(["testserver", "bogus"]).is_err());
    }
}
