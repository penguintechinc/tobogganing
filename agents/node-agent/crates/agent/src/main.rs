//! `node-agent`: the unified tobogganing node-agent binary. Delivers SASE
//! connectivity and local netsvcs-edge services from one build, packaged
//! two ways (static musl bare-metal, K8s DaemonSet container) per
//! `docs/superpowers/specs/2026-08-20-squawk-P4-rust-node-agent.md`.

mod cli;
mod healthz;
mod run;
mod telemetry;

use clap::Parser;
use cli::{Cli, Command};
use std::process::ExitCode;

#[tokio::main]
async fn main() -> ExitCode {
    let telemetry_guard = telemetry::init("node-agent");

    let cli = Cli::parse();
    let result = match cli.command {
        Command::Run {
            mode,
            control_plane_url,
        } => run::run(cli.config.as_deref(), mode, control_plane_url).await,
        Command::Healthz => healthz::healthz(cli.config.as_deref()).await,
    };

    let exit_code = match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            tracing::error!(error = %err, "node-agent exited with an error");
            ExitCode::FAILURE
        }
    };

    // Best-effort flush of any pending OTLP export before exit — never
    // blocks the actual exit code on a dead/unreachable collector (see
    // `TelemetryGuard::shutdown`'s doc comment).
    telemetry_guard.shutdown();
    exit_code
}
