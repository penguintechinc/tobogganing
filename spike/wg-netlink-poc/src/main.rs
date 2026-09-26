//! THROWAWAY spike prototype — Phase 2a hub-router WireGuard/netlink
//! redesign de-risk. See docs/spikes/2026-09-25-rust-wireguard-netlink-spike.md
//! for the write-up this crate exists to support. Not production code.

// Several API-shape demonstrations (create_wg0, upsert_peer, list_peers,
// upsert_peer_async) are exercised only by their own unit tests, not by this
// demo binary's main() flow — allowed here since the point of the spike is
// proving the crate API shapes compile and behave, not building a full CLI.
#![allow(dead_code)]

mod blocking;
mod nft_batch;
mod rtnl_probe;
mod so_mark;
mod wg_control;
mod wg_control_defguard;

use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()))
        .init();

    let has_net_admin = nix_has_net_admin();
    if !has_net_admin {
        tracing::warn!(
            "running without CAP_NET_ADMIN — WG/netlink/nft calls below are expected \
             to fail with EPERM; this run only validates that they fail *closed* \
             (clean Err, no panic), not that they succeed. Re-run on a privileged \
             cluster node to validate the happy path."
        );
    }

    tracing::info!("goal 1: probing for an existing wg0 (rtnetlink unprivileged link dump)");
    let (handle, driver) = rtnl_probe::connect()?;
    match rtnl_probe::find_wg0_ifindex(&handle).await {
        Ok(Some(idx)) => tracing::info!(ifindex = idx, "wg0 exists"),
        Ok(None) => tracing::info!("wg0 does not exist"),
        Err(e) => tracing::warn!(error = %e, "rtnetlink probe failed"),
    }
    driver.abort();

    tracing::info!("goal 1: probing for an existing wg0 (WireGuard genl, needs CAP_NET_ADMIN)");
    match blocking::probe_wg0_async().await {
        Ok(wg_control::ProbeResult::Absent) => tracing::info!("no wg0 — would create fresh"),
        Ok(wg_control::ProbeResult::ExistingDevice {
            peer_count,
            listen_port,
        }) => {
            tracing::info!(peer_count, ?listen_port, "wg0 exists — would adopt");
        }
        Err(e) => {
            tracing::warn!(error = %e, "WG genl probe failed (expected without CAP_NET_ADMIN)")
        }
    }

    tracing::info!(
        "goal 1 (recommended crate): probing wg0 via defguard_wireguard_rs (needs CAP_NET_ADMIN)"
    );
    match tokio::task::spawn_blocking(wg_control_defguard::read_wg0).await {
        Ok(Ok(host)) => tracing::info!(peer_count = host.peers.len(), "wg0 exists — would adopt"),
        Ok(Err(e)) => {
            tracing::warn!(error = %e, "defguard read_wg0 failed (expected without CAP_NET_ADMIN)")
        }
        Err(join_err) => tracing::error!(error = %join_err, "spawn_blocking join failed"),
    }

    tracing::info!("goal 2: SO_MARK on a scratch TCP listener (needs CAP_NET_ADMIN)");
    let listener = std::net::TcpListener::bind("127.0.0.1:0")?;
    match so_mark::set_socket_mark(&listener, so_mark::AUTHENTICATED_MARK) {
        Ok(()) => tracing::info!("SO_MARK applied"),
        Err(e) => tracing::warn!(error = %e, "SO_MARK failed (expected without CAP_NET_ADMIN)"),
    }

    tracing::info!("goal 4: atomic nft ruleset apply (needs CAP_NET_ADMIN)");
    let ruleset = nft_batch::authenticated_mark_ruleset(so_mark::AUTHENTICATED_MARK);
    match nft_batch::apply_ruleset_atomic(&ruleset).await {
        Ok(()) => tracing::info!("nft ruleset applied atomically"),
        Err(e) => tracing::warn!(error = %e, "nft apply failed (expected without CAP_NET_ADMIN)"),
    }

    Ok(())
}

fn nix_has_net_admin() -> bool {
    // Cheap heuristic for the startup banner only (not a security check):
    // try the cheapest privileged netlink mutation and see if it's rejected.
    // Real capability introspection would read /proc/self/status Cap*
    // fields; skipped here since this is just a log-banner nicety.
    std::fs::read_to_string("/proc/self/status")
        .ok()
        .and_then(|s| {
            s.lines()
                .find(|l| l.starts_with("CapEff:"))
                .map(|l| l.trim_start_matches("CapEff:").trim().to_string())
        })
        .and_then(|hex| u64::from_str_radix(&hex, 16).ok())
        .map(|caps| caps & (1 << 12) != 0) // CAP_NET_ADMIN = 12
        .unwrap_or(false)
}
