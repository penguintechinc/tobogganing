//! `node_agent_netsvcs_edge`: local `:53` DNS forwarder (`hickory-server`)
//! to the P3 DoH upstream resolvers, plus DHCP (`dhcproto`) and NTP
//! (`ntp-proto`) clients.
//!
//! Each capability is independently runtime-gated by its
//! `NetsvcsEdgeConfig` flag (`dns_enabled`, `dhcp_enabled`, `ntp_enabled`)
//! and supervised under the shared `shutdown` token passed to [`run`].

mod dhcp;
mod dns;
mod ntp;

use node_agent_core::{ControlPlaneClient, NetsvcsEdgeConfig, Result};
use std::sync::Arc;
use tokio::task::JoinSet;
use tokio_util::sync::CancellationToken;

/// Runs the netsvcs-edge module until `shutdown` is cancelled: spawns the
/// DNS forwarder, DHCP client, and NTP client as independent supervised
/// tasks, each gated by its own `cfg.*_enabled` flag, and waits for all of
/// them to finish (which happens once `shutdown` is cancelled).
pub async fn run(
    cfg: NetsvcsEdgeConfig,
    client: Arc<dyn ControlPlaneClient>,
    shutdown: CancellationToken,
) -> Result<()> {
    tracing::info!(module = "netsvcs-edge", "starting");

    // Installing the process-wide rustls crypto provider is idempotent
    // (`install_default` on an already-configured process is a documented
    // no-op) — call it defensively here so this module also works when
    // exercised outside `agent::run`'s startup sequence (e.g. in tests).
    node_agent_transport::install_crypto_provider()?;

    let mut tasks = JoinSet::new();

    if cfg.dns_enabled {
        let dns_cfg = cfg.dns.clone();
        let doh_client = Arc::clone(&client);
        let token = shutdown.clone();
        tasks.spawn(async move { dns::run(dns_cfg, doh_client, token).await });
    } else {
        tracing::info!(module = "netsvcs-edge.dns", "disabled by config");
    }

    if cfg.dhcp_enabled {
        let dhcp_cfg = cfg.dhcp.clone().unwrap_or_default();
        let token = shutdown.clone();
        tasks.spawn(async move { dhcp::run(dhcp_cfg, token).await });
    } else {
        tracing::info!(module = "netsvcs-edge.dhcp", "disabled by config");
    }

    if cfg.ntp_enabled {
        let ntp_cfg = cfg.ntp.clone().unwrap_or_default();
        let token = shutdown.clone();
        tasks.spawn(async move { ntp::run(ntp_cfg, token).await });
    } else {
        tracing::info!(module = "netsvcs-edge.ntp", "disabled by config");
    }

    if tasks.is_empty() {
        shutdown.cancelled().await;
        tracing::info!(module = "netsvcs-edge", "stopped");
        return Ok(());
    }

    while let Some(joined) = tasks.join_next().await {
        match joined {
            Ok(Ok(())) => {}
            Ok(Err(err)) => {
                tracing::error!(error = %err, "a netsvcs-edge subtask exited with an error")
            }
            Err(join_err) => {
                tracing::error!(error = %join_err, "a netsvcs-edge subtask panicked or was aborted")
            }
        }
    }

    tracing::info!(module = "netsvcs-edge", "stopped");
    Ok(())
}
