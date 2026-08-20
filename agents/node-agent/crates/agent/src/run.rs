//! `run` subcommand: loads config, enrolls with the control plane, and
//! supervises the connectivity/netsvcs-edge modules plus a periodic
//! heartbeat loop until an interrupt is received.

use jsonwebtoken::Algorithm;
use node_agent_core::{
    AgentConfig, AgentError, AgentMode, ControlPlaneClient, EnrollRequest, Heartbeat,
    MachineJwtSigner, Result,
};
use std::path::Path;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio_util::sync::CancellationToken;

/// Runs the agent: load config → install the shared TLS crypto provider →
/// build a transport client → enroll → spawn the capability modules and a
/// heartbeat loop under a shared [`CancellationToken`] → wait for an
/// interrupt → cancel and join every task.
pub async fn run(
    config_path: Option<&Path>,
    mode_override: Option<AgentMode>,
    control_plane_url_override: Option<String>,
) -> Result<()> {
    let mut cfg = AgentConfig::load(config_path)?;
    if let Some(mode) = mode_override {
        cfg.mode = mode;
    }
    if let Some(url) = control_plane_url_override {
        cfg.control_plane_url = url;
    }

    node_agent_transport::install_crypto_provider()?;
    let client = node_agent_transport::build_client(&cfg);

    let signer = MachineJwtSigner::from_pem_file(&cfg.machine_jwt_path, Algorithm::ES256)?;
    let hostname = local_hostname()?;
    // node_id isn't known until the control plane assigns one in
    // EnrollResponse, so the hostname doubles as the bootstrap JWT subject.
    let machine_jwt = signer.sign(
        "node-agent",
        &hostname,
        "node-agent",
        "dns:config:read metrics:write ioc:read",
        Duration::from_secs(300),
    )?;

    let enroll_resp = client
        .enroll(EnrollRequest {
            machine_jwt,
            node_type: "node-agent".to_string(),
            hostname: hostname.clone(),
            public_key: None,
        })
        .await?;
    tracing::info!(node_id = %enroll_resp.node_id, tenant = %enroll_resp.tenant, "enrolled with control plane");

    let shutdown = CancellationToken::new();
    let mut tasks = tokio::task::JoinSet::new();

    #[cfg(feature = "connectivity")]
    if cfg.features.connectivity {
        let module_cfg = enroll_resp.config.connectivity.clone();
        let client = Arc::clone(&client);
        let token = shutdown.clone();
        tasks.spawn(async move { node_agent_connectivity::run(module_cfg, client, token).await });
    }

    #[cfg(feature = "netsvcs-edge")]
    if cfg.features.netsvcs_edge {
        let module_cfg = enroll_resp.config.edge.clone();
        let client = Arc::clone(&client);
        let token = shutdown.clone();
        tasks.spawn(async move { node_agent_netsvcs_edge::run(module_cfg, client, token).await });
    }

    {
        let client = Arc::clone(&client);
        let node_id = enroll_resp.node_id.clone();
        let interval_secs = cfg.heartbeat_interval_secs;
        let token = shutdown.clone();
        tasks.spawn(async move {
            heartbeat_loop(client, node_id, interval_secs, token).await;
            Ok(())
        });
    }

    let _ = tokio::signal::ctrl_c().await;
    tracing::info!("received interrupt; shutting down");
    shutdown.cancel();

    while let Some(joined) = tasks.join_next().await {
        match joined {
            Ok(Ok(())) => {}
            Ok(Err(err)) => tracing::error!(error = %err, "a supervised task exited with an error"),
            Err(join_err) => {
                tracing::error!(error = %join_err, "a supervised task panicked or was aborted")
            }
        }
    }

    Ok(())
}

/// Periodically reports liveness to the control plane until `shutdown` is
/// cancelled; a single failed heartbeat is logged and retried on the next
/// tick rather than tearing down the process.
async fn heartbeat_loop(
    client: Arc<dyn ControlPlaneClient>,
    node_id: String,
    interval_secs: u64,
    shutdown: CancellationToken,
) {
    let mut interval = tokio::time::interval(Duration::from_secs(interval_secs.max(1)));
    loop {
        tokio::select! {
            _ = shutdown.cancelled() => return,
            _ = interval.tick() => {
                let hb = Heartbeat { node_id: node_id.clone(), timestamp: unix_now(), config_version: 0 };
                if let Err(err) = client.heartbeat(hb).await {
                    tracing::warn!(error = %err, "heartbeat failed");
                }
            }
        }
    }
}

fn unix_now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or_default()
}

/// Resolves this node's hostname from the `HOSTNAME` environment variable
/// (always set inside containers; commonly set by the shell on bare metal)
/// — a dependency-free source for Stage F, avoiding a libc `gethostname`
/// binding for a single startup-time value.
fn local_hostname() -> Result<String> {
    std::env::var("HOSTNAME")
        .map_err(|_| AgentError::Config("HOSTNAME environment variable is not set".to_string()))
}
