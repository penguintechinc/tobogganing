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

#[cfg(test)]
mod tests {
    use super::*;
    use async_trait::async_trait;
    use node_agent_core::{
        DhcpConfig, DnsConfig, EnrollRequest, EnrollResponse, Heartbeat, IocVerdict, Metrics,
        NodeConfig, NtpConfig, RefreshResponse,
    };
    use std::time::Duration;

    /// A `ControlPlaneClient` double that is never actually called by these
    /// tests (`ioc_filtering` stays off, so the DNS handler never reaches
    /// `check_ioc`) — every method panics if invoked, which would itself be
    /// a useful test failure signal.
    struct UnusedClient;

    #[async_trait]
    impl ControlPlaneClient for UnusedClient {
        async fn enroll(&self, _req: EnrollRequest) -> Result<EnrollResponse> {
            unimplemented!("not exercised by netsvcs-edge::run tests")
        }
        async fn heartbeat(&self, _hb: Heartbeat) -> Result<()> {
            unimplemented!("not exercised by netsvcs-edge::run tests")
        }
        async fn get_config(
            &self,
            _node_id: &str,
            _current_version: i64,
        ) -> Result<Option<NodeConfig>> {
            unimplemented!("not exercised by netsvcs-edge::run tests")
        }
        async fn report_metrics(&self, _m: Metrics) -> Result<()> {
            unimplemented!("not exercised by netsvcs-edge::run tests")
        }
        async fn refresh_token(&self, _refresh_token: &str) -> Result<RefreshResponse> {
            unimplemented!("not exercised by netsvcs-edge::run tests")
        }
        async fn check_ioc(&self, _indicator: &str) -> Result<IocVerdict> {
            unimplemented!("not exercised by netsvcs-edge::run tests")
        }
    }

    fn client() -> Arc<dyn ControlPlaneClient> {
        Arc::new(UnusedClient)
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn run_idles_and_returns_once_cancelled_when_every_capability_is_disabled() {
        let cfg = NetsvcsEdgeConfig {
            dns_enabled: false,
            dhcp_enabled: false,
            ntp_enabled: false,
            ..NetsvcsEdgeConfig::default()
        };
        let shutdown = CancellationToken::new();
        let shutdown_clone = shutdown.clone();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(20)).await;
            shutdown_clone.cancel();
        });

        let result = tokio::time::timeout(Duration::from_secs(5), run(cfg, client(), shutdown))
            .await
            .expect("run must return promptly after cancellation, not hang");
        assert!(result.is_ok());
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn run_propagates_a_subtask_error_without_panicking() {
        // An unparsable DNS `listen_addr` makes `dns::run` fail fast (no
        // socket bind attempted), exercising the `Ok(Err(err))` arm of the
        // supervision loop's `tasks.join_next()` match without needing to
        // wait for cancellation at all — the task completes on its own.
        let cfg = NetsvcsEdgeConfig {
            dns_enabled: true,
            dhcp_enabled: false,
            ntp_enabled: false,
            dns: DnsConfig {
                listen_addr: "not-a-valid-address".to_string(),
                ..DnsConfig::default()
            },
            ..NetsvcsEdgeConfig::default()
        };
        let shutdown = CancellationToken::new();

        let result = tokio::time::timeout(Duration::from_secs(5), run(cfg, client(), shutdown))
            .await
            .expect("run must return promptly once its only subtask errors out");
        // The supervisor logs and continues past a subtask error rather
        // than propagating it as its own `Err`.
        assert!(result.is_ok());
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn run_supervises_every_capability_and_stops_cleanly_on_cancel() {
        let cfg = NetsvcsEdgeConfig {
            dns_enabled: true,
            dhcp_enabled: true,
            ntp_enabled: true,
            dns: DnsConfig {
                listen_addr: "127.0.0.1:0".to_string(),
                ..DnsConfig::default()
            },
            dhcp: Some(DhcpConfig::default()),
            // No servers configured — the NTP client idles until shutdown
            // rather than attempting a real network query.
            ntp: Some(NtpConfig::default()),
            ..NetsvcsEdgeConfig::default()
        };
        let shutdown = CancellationToken::new();
        let shutdown_clone = shutdown.clone();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(100)).await;
            shutdown_clone.cancel();
        });

        let result = tokio::time::timeout(Duration::from_secs(10), run(cfg, client(), shutdown))
            .await
            .expect("run must join every supervised subtask and return after cancellation");
        assert!(result.is_ok());
    }
}
