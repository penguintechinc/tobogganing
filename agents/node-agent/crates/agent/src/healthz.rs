//! `healthz` subcommand: a lightweight, dependency-free liveness check
//! wired as the container `HEALTHCHECK` command. Runs as a fresh process
//! invocation, so it validates the binary and its configuration rather
//! than querying a running daemon's in-memory state.

use node_agent_core::{AgentConfig, Result};
use std::path::Path;

/// Validates that configuration loads cleanly — the failure mode a broken
/// image or misconfigured rollout hits most often. A liveness probe against
/// the running daemon (local status file or loopback probe) lands with
/// Stage I packaging.
pub async fn healthz(config_path: Option<&Path>) -> Result<()> {
    let _ = AgentConfig::load(config_path)?;
    Ok(())
}
