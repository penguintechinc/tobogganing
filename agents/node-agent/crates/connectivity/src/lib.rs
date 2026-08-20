//! `node_agent_connectivity`: SASE connectivity module — a userspace
//! WireGuard data plane (`boringtun`) driven by node-level config the
//! top-level agent binary owns, plus the optional XDP inspection tap
//! (`aya`, feature `xdp`, not default).
//!
//! This module is data-plane only: it neither enrolls with the control
//! plane nor runs its own heartbeat/refresh loop. The agent binary
//! (`crates/agent/src/run.rs`) owns the single node-level enroll →
//! heartbeat → config-poll → refresh lifecycle for the whole process,
//! generates this node's WireGuard identity once via [`wireguard_identity`]
//! *before* that single enrollment call (so the public key can be
//! advertised in the `EnrollRequest`), and drives this module's
//! [`run`] with that identity plus a `watch` channel of
//! [`ConnectivityConfig`] updates published on every config change the
//! lifecycle loop observes.
//!
//! WireGuard is always built; `xdp` stays opt-in so the default
//! `cargo build`/`clippy` never needs an eBPF toolchain — see the [`xdp`]
//! module docs for why.

mod device;
mod keys;
mod netconfig;
mod uapi;
#[cfg(feature = "xdp")]
pub mod xdp;

use device::WireguardDevice;
use node_agent_core::{AgentError, ConnectivityConfig, Result, WireguardConfig};
use rtnetlink::Handle;
use tokio::sync::watch;
use tokio_util::sync::CancellationToken;

/// This node's WireGuard identity: the base64 public key advertised to the
/// control plane in [`EnrollRequest::public_key`](node_agent_core::EnrollRequest::public_key),
/// and the matching base64 private key [`run`] uses to bring up the local
/// `boringtun` device. Produced once per agent process lifetime by
/// [`wireguard_identity`] — WireGuard keys are not persisted across
/// restarts, matching the Go reference client's re-register-on-start
/// behavior.
#[derive(Debug, Clone)]
pub struct WireguardIdentity {
    pub public_key_b64: String,
    pub private_key_b64: String,
}

/// Generates a fresh ephemeral WireGuard keypair for this node when
/// `cfg.wireguard_enabled`, or returns `Ok(None)` when WireGuard is
/// disabled. Called by the agent binary *before* its single enrollment
/// call so `Some(identity).public_key_b64` can be attached to
/// `EnrollRequest::public_key` — the control plane can then hand back a
/// matching peer config in that very first response. Infallible in
/// practice (key generation only touches the OS CSPRNG); returns `Result`
/// to leave room for a future hardware-backed key source without a
/// signature change.
pub fn wireguard_identity(cfg: &ConnectivityConfig) -> Result<Option<WireguardIdentity>> {
    if !cfg.wireguard_enabled {
        return Ok(None);
    }
    let keypair = keys::generate();
    tracing::info!(module = "connectivity", public_key = %keypair.public_key_b64, "generated WireGuard keypair");
    Ok(Some(WireguardIdentity {
        public_key_b64: keypair.public_key_b64,
        private_key_b64: keys::private_key_b64(&keypair.private_key),
    }))
}

/// Runs the connectivity module until `shutdown` is cancelled.
///
/// Idles until shutdown when WireGuard is disabled (`!cfg.wireguard_enabled`)
/// or `wg_identity` is `None` — this module never generates its own
/// identity or talks to the control plane; both are owned by the agent
/// binary's single node-level lifecycle. Otherwise, brings up the
/// `boringtun` data plane using `wg_identity`'s private key (immediately,
/// if `cfg` already carries a [`WireguardConfig`] from the enrollment
/// response) and (re)applies the interface address/routes/DNS every time
/// `config_rx` publishes a newer [`ConnectivityConfig`].
///
/// Every failure mode here degrades gracefully — a permission-denied TUN
/// creation (no `NET_ADMIN`) is logged and the module falls back to the
/// least-capable working state rather than crashing the agent.
pub async fn run(
    cfg: ConnectivityConfig,
    wg_identity: Option<WireguardIdentity>,
    mut config_rx: watch::Receiver<ConnectivityConfig>,
    shutdown: CancellationToken,
) -> Result<()> {
    tracing::info!(module = "connectivity", "starting");

    let identity = match (cfg.wireguard_enabled, wg_identity) {
        (true, Some(identity)) => identity,
        _ => {
            tracing::info!(
                module = "connectivity",
                "WireGuard disabled or no identity available; idling until shutdown"
            );
            shutdown.cancelled().await;
            tracing::info!(module = "connectivity", "stopped");
            return Ok(());
        }
    };

    let mut device: Option<WireguardDevice> = None;
    if let Some(wg_cfg) = &cfg.wireguard {
        bring_up(
            &mut device,
            &identity.private_key_b64,
            cfg.wireguard_listen_port,
            wg_cfg,
        )
        .await;
    }

    loop {
        tokio::select! {
            _ = shutdown.cancelled() => break,
            changed = config_rx.changed() => {
                if changed.is_err() {
                    // Sender (the agent's lifecycle loop) is gone; nothing left to drive us.
                    break;
                }
                let (listen_port, wg_cfg) = {
                    let latest = config_rx.borrow();
                    (latest.wireguard_listen_port, latest.wireguard.clone())
                };
                if let Some(wg_cfg) = wg_cfg {
                    bring_up(&mut device, &identity.private_key_b64, listen_port, &wg_cfg).await;
                }
            }
        }
    }

    drop(device);
    tracing::info!(module = "connectivity", "stopped");
    Ok(())
}

/// (Re)configures the WireGuard interface with `cfg`: creates the boringtun
/// device on first use (or reapplies over the existing UAPI control socket
/// on subsequent config changes), then applies the interface
/// address/routes/DNS. Failures at any step are logged and non-fatal — a
/// bad or unprivileged environment degrades to "no data plane this tick"
/// rather than tearing down the whole connectivity module.
async fn bring_up(
    device: &mut Option<WireguardDevice>,
    private_key_b64: &str,
    listen_port: u16,
    cfg: &WireguardConfig,
) {
    let apply_result = match device {
        Some(dev) => dev.apply(private_key_b64, listen_port, cfg),
        None => {
            match WireguardDevice::create(&cfg.interface_name, private_key_b64, listen_port, cfg) {
                Ok(created) => {
                    *device = Some(created);
                    Ok(())
                }
                Err(err) => Err(err),
            }
        }
    };

    match apply_result {
        Ok(()) => {
            if let Some(dev) = device.as_ref() {
                if let Err(err) = apply_networking(dev, cfg).await {
                    tracing::warn!(error = %err, "failed to apply WireGuard interface networking (address/routes/DNS)");
                }
            }
        }
        Err(err) => {
            tracing::warn!(
                error = %err,
                interface = %cfg.interface_name,
                "failed to bring up/apply the WireGuard interface (likely missing NET_ADMIN)"
            );
        }
    }
}

/// Opens a fresh rtnetlink connection and applies `cfg`'s interface
/// address, allowed-IP routes, and DNS servers to `dev`'s interface.
async fn apply_networking(dev: &WireguardDevice, cfg: &WireguardConfig) -> Result<()> {
    let (connection, handle, _): (_, Handle, _) = rtnetlink::new_connection()
        .map_err(|e| AgentError::Task(format!("failed to open rtnetlink connection: {e}")))?;
    tokio::spawn(connection);

    netconfig::configure_address_and_link(&handle, dev.interface_name(), cfg).await?;
    netconfig::configure_routes(&handle, dev.interface_name(), cfg).await?;
    if let Err(err) = netconfig::configure_dns(cfg) {
        tracing::warn!(error = %err, "failed to configure DNS (non-fatal)");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn wg_config() -> WireguardConfig {
        WireguardConfig {
            peer_public_key: "peer-key".to_string(),
            peer_endpoint: "headend.example.internal:51820".to_string(),
            interface_address: "10.200.0.5/32".to_string(),
            ..WireguardConfig::default()
        }
    }

    #[test]
    fn wireguard_identity_returns_none_when_disabled() {
        let cfg = ConnectivityConfig {
            wireguard_enabled: false,
            ..ConnectivityConfig::default()
        };
        let identity = wireguard_identity(&cfg).expect("must not error");
        assert!(identity.is_none());
    }

    #[test]
    fn wireguard_identity_returns_a_keypair_when_enabled() {
        let cfg = ConnectivityConfig {
            wireguard_enabled: true,
            ..ConnectivityConfig::default()
        };
        let identity = wireguard_identity(&cfg)
            .expect("must not error")
            .expect("must produce an identity when enabled");
        assert_eq!(identity.public_key_b64.len(), 44);
        assert_eq!(identity.private_key_b64.len(), 44);
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn run_idles_until_shutdown_when_wireguard_disabled() {
        let cfg = ConnectivityConfig {
            wireguard_enabled: false,
            ..ConnectivityConfig::default()
        };
        let (_tx, rx) = watch::channel(cfg.clone());
        let shutdown = CancellationToken::new();
        let shutdown_clone = shutdown.clone();
        tokio::spawn(async move {
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
            shutdown_clone.cancel();
        });

        let result = run(cfg, None, rx, shutdown).await;
        assert!(result.is_ok());
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn run_idles_until_shutdown_when_no_identity_even_if_enabled() {
        let cfg = ConnectivityConfig {
            wireguard_enabled: true,
            wireguard: Some(wg_config()),
            ..ConnectivityConfig::default()
        };
        let (_tx, rx) = watch::channel(cfg.clone());
        let shutdown = CancellationToken::new();
        let shutdown_clone = shutdown.clone();
        tokio::spawn(async move {
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
            shutdown_clone.cancel();
        });

        // No identity supplied (e.g. wireguard_identity returned None
        // earlier) — must idle rather than attempt to bring up a device
        // with no private key.
        let result = run(cfg, None, rx, shutdown).await;
        assert!(result.is_ok());
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn run_ends_when_the_sender_is_dropped() {
        let cfg = ConnectivityConfig {
            wireguard_enabled: true,
            wireguard: None,
            ..ConnectivityConfig::default()
        };
        let (tx, rx) = watch::channel(cfg.clone());
        let identity = WireguardIdentity {
            public_key_b64: "test-pub".to_string(),
            private_key_b64: "test-priv".to_string(),
        };
        drop(tx); // simulate the agent's lifecycle loop going away

        let result = run(cfg, Some(identity), rx, CancellationToken::new()).await;
        assert!(result.is_ok());
    }
}
