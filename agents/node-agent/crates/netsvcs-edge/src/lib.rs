//! `node_agent_netsvcs_edge`: local `:53` DNS forwarder (`hickory-server`)
//! to the P3 DoH upstream resolvers, plus DHCP (`dhcproto`) and NTP
//! (`ntp-proto`) clients.
//!
//! **Stage F stub.** This crate currently exposes a compilable no-op
//! `run()` so `agent` and the workspace build green while
//! `feature/p4-netsvcs-edge` fills in the real implementation against the
//! `node_agent_core::ControlPlaneClient` contract.

use node_agent_core::{ControlPlaneClient, NetsvcsEdgeConfig, Result};
use std::sync::Arc;
use tokio_util::sync::CancellationToken;

/// Runs the netsvcs-edge module until `shutdown` is cancelled.
///
/// Stage F: logs startup/shutdown and otherwise does nothing — no DNS/DHCP/
/// NTP service is bound yet. Real implementation lands via
/// `feature/p4-netsvcs-edge`.
pub async fn run(
    _cfg: NetsvcsEdgeConfig,
    _client: Arc<dyn ControlPlaneClient>,
    shutdown: CancellationToken,
) -> Result<()> {
    tracing::info!(module = "netsvcs-edge", "starting");
    shutdown.cancelled().await;
    tracing::info!(module = "netsvcs-edge", "stopped");
    Ok(())
}
