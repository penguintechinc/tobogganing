//! `node-agent`: the unified tobogganing node-agent binary. Delivers SASE
//! connectivity and local netsvcs-edge services from one build, packaged
//! two ways (static musl bare-metal, K8s DaemonSet container) per
//! `docs/superpowers/specs/2026-08-20-squawk-P4-rust-node-agent.md`.

mod cli;
mod healthz;
mod run;

use clap::Parser;
use cli::{Cli, Command};
use std::process::ExitCode;

#[tokio::main]
async fn main() -> ExitCode {
    init_tracing();

    let cli = Cli::parse();
    let result = match cli.command {
        Command::Run {
            mode,
            control_plane_url,
        } => run::run(cli.config.as_deref(), mode, control_plane_url).await,
        Command::Healthz => healthz::healthz(cli.config.as_deref()).await,
    };

    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            tracing::error!(error = %err, "node-agent exited with an error");
            ExitCode::FAILURE
        }
    }
}

/// Initializes structured JSON logging via `tracing-subscriber`, honoring
/// `RUST_LOG` for level filtering — never raw `println!`/stdout per the
/// org's structured-logging policy.
fn init_tracing() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .json()
        .init();
}
