//! `node_agent_connectivity`: SASE connectivity module — WireGuard data
//! plane (`boringtun`), enrollment + heartbeat loops, the optional XDP
//! inspection tap (`aya`), and the Ziti hook.
//!
//! **Stage F stub.** This crate currently exposes a compilable no-op
//! `run()` so `agent` and the workspace build green while
//! `feature/p4-connectivity` fills in the real implementation against the
//! `node_agent_core::ControlPlaneClient` contract.

use node_agent_core::{ConnectivityConfig, ControlPlaneClient, Result};
use std::sync::Arc;
use tokio_util::sync::CancellationToken;

/// Runs the connectivity module until `shutdown` is cancelled.
///
/// Stage F: logs startup/shutdown and otherwise does nothing — no
/// WireGuard/Ziti data plane is started yet. Real implementation lands via
/// `feature/p4-connectivity`.
pub async fn run(
    _cfg: ConnectivityConfig,
    _client: Arc<dyn ControlPlaneClient>,
    shutdown: CancellationToken,
) -> Result<()> {
    tracing::info!(module = "connectivity", "starting");
    shutdown.cancelled().await;
    tracing::info!(module = "connectivity", "stopped");
    Ok(())
}
