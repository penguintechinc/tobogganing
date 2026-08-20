//! `node_agent_connectivity`: SASE connectivity module — a userspace
//! WireGuard data plane (`boringtun`), a connectivity-scoped
//! enroll/heartbeat/config-poll/refresh control-plane loop, and the
//! optional XDP inspection tap (`aya`, feature `xdp`, not default).
//!
//! Real implementation for squawk-P4/`feature/p4-connectivity`. WireGuard
//! and the control-plane loop are always built; `xdp` stays opt-in so the
//! default `cargo build`/`clippy` never needs an eBPF toolchain — see the
//! [`xdp`] module docs for why.

mod control;
mod device;
mod keys;
mod netconfig;
mod uapi;
#[cfg(feature = "xdp")]
pub mod xdp;

use device::WireguardDevice;
use node_agent_core::{
    AgentError, ConnectivityConfig, ControlPlaneClient, Result, WireguardConfig,
};
use rtnetlink::Handle;
use std::sync::Arc;
use tokio_util::sync::CancellationToken;

/// Runs the connectivity module until `shutdown` is cancelled.
///
/// 1. Generates this node's WireGuard keypair (never persisted across
///    restarts, matching the Go reference client's re-register-on-start
///    behavior).
/// 2. If `cfg` already carries a [`WireguardConfig`] (e.g. handed down from
///    the top-level agent's own initial enrollment), best-effort brings up
///    the `boringtun` data plane immediately.
/// 3. Bootstraps a connectivity-scoped machine-JWT identity and runs the
///    enroll → heartbeat → config-poll → refresh control-plane loop
///    described in the P4 design doc, (re)applying the WireGuard interface
///    address/routes/DNS on every config change it publishes.
///
/// Every failure mode here degrades gracefully — a missing signing key, a
/// permission-denied TUN creation (no `NET_ADMIN`), or a control-plane
/// error is logged and the module falls back to the least-capable working
/// state rather than crashing the agent.
pub async fn run(
    cfg: ConnectivityConfig,
    client: Arc<dyn ControlPlaneClient>,
    shutdown: CancellationToken,
) -> Result<()> {
    tracing::info!(module = "connectivity", "starting");

    if !cfg.wireguard_enabled {
        tracing::info!(
            module = "connectivity",
            "WireGuard disabled by config; idling until shutdown"
        );
        shutdown.cancelled().await;
        tracing::info!(module = "connectivity", "stopped");
        return Ok(());
    }

    let keypair = keys::generate();
    tracing::info!(module = "connectivity", public_key = %keypair.public_key_b64, "generated WireGuard keypair");
    let private_key_b64 = keys::private_key_b64(&keypair.private_key);
    let listen_port = cfg.wireguard_listen_port;

    let mut device: Option<WireguardDevice> = None;
    if let Some(wg_cfg) = &cfg.wireguard {
        bring_up(&mut device, &private_key_b64, listen_port, wg_cfg).await;
    }

    let (config_tx, mut config_rx) = tokio::sync::mpsc::unbounded_channel();

    let control_loop = async {
        match control::bootstrap_identity(&keypair.public_key_b64) {
            Ok(identity) => {
                if let Err(err) = control::run_control_loop(
                    client.as_ref(),
                    identity,
                    control::DEFAULT_TICK_INTERVAL,
                    &shutdown,
                    config_tx,
                )
                .await
                {
                    tracing::warn!(error = %err, "connectivity control loop exited early");
                }
            }
            Err(err) => {
                tracing::warn!(
                    error = %err,
                    "no machine-JWT signer available; running WireGuard with only the static config, no control-plane loop"
                );
                drop(config_tx);
                shutdown.cancelled().await;
            }
        }
    };

    let apply_loop = async {
        loop {
            tokio::select! {
                _ = shutdown.cancelled() => break,
                maybe_cfg = config_rx.recv() => {
                    match maybe_cfg {
                        Some(wg_cfg) => bring_up(&mut device, &private_key_b64, listen_port, &wg_cfg).await,
                        None => break,
                    }
                }
            }
        }
    };

    tokio::join!(control_loop, apply_loop);

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
