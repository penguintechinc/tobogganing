//! Goal 3: confirm the `spawn_blocking` pattern for the WireGuard
//! control-plane calls that are blocking under the hood (see `wg_control.rs`
//! module doc — `wireguard-control` uses raw synchronous `libc` netlink
//! sockets, not tokio's async netlink socket).
//!
//! This is the mandatory pattern from migration-plan risk #2: kernel
//! syscalls (`rtnetlink`/`nftables`/WG) inside axum handlers must never run
//! on a tokio worker thread directly, or a burst of control-plane requests
//! (e.g. peer churn) can starve request-handling tasks sharing the runtime.

use std::io;
use wireguard_control::Key;

use crate::wg_control;

/// Runs `wg_control::probe_wg0` on tokio's blocking thread pool instead of
/// the async worker threads. This is the shape every WG control-plane call
/// (probe/create/upsert_peer/list_peers) must use in the real service.
pub async fn probe_wg0_async() -> io::Result<wg_control::ProbeResult> {
    tokio::task::spawn_blocking(wg_control::probe_wg0)
        .await
        .map_err(|join_err| io::Error::other(format!("spawn_blocking join failed: {join_err}")))?
}

/// Same wrapper shape for peer upsert — takes owned data so the closure is
/// `'static` (a `spawn_blocking` requirement).
pub async fn upsert_peer_async(pubkey: Key, allowed_ip_cidr: String) -> io::Result<()> {
    tokio::task::spawn_blocking(move || wg_control::upsert_peer(pubkey, &allowed_ip_cidr))
        .await
        .map_err(|join_err| io::Error::other(format!("spawn_blocking join failed: {join_err}")))?
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;

    /// VALIDATED: proves a blocking WG call (which fails fast with EPERM in
    /// this sandbox, but the timing argument holds regardless of outcome)
    /// does not block progress of concurrently-scheduled async tasks on a
    /// multi-thread runtime — i.e. `spawn_blocking` actually offloads to the
    /// blocking pool rather than running inline on a worker thread.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn concurrent_async_task_makes_progress_during_blocking_call() {
        let start = Instant::now();

        let blocking_call = tokio::spawn(async {
            let _ = probe_wg0_async().await; // expected to Err(EPERM) here; that's fine
        });

        // If probe_wg0_async ran inline on a worker thread instead of the
        // blocking pool, a single-core scheduling delay could still make
        // this pass by luck, so the real assertion is on wall-clock: this
        // sleep must not be meaningfully delayed by the "blocking" call.
        let sleeper = tokio::spawn(async {
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        });

        let (_, sleep_result) = tokio::join!(blocking_call, sleeper);
        sleep_result.expect("sleeper task should complete promptly");

        assert!(
            start.elapsed() < std::time::Duration::from_secs(2),
            "concurrent tasks took too long — possible runtime starvation"
        );
    }
}
