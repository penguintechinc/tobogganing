//! Goal 1 (alt path) + goal 3 contrast: use the `rtnetlink` crate directly
//! (native tokio async socket, NOT blocking) to list links and find `wg0`'s
//! ifindex. This demonstrates the crate landscape has two different
//! concurrency shapes:
//!
//! - `rtnetlink` 0.23: async-native, safe to `.await` directly in a tokio
//!   task — no `spawn_blocking` needed for route/link queries.
//! - `wireguard-control` 2.0 (see `wg_control.rs`): synchronous blocking
//!   netlink calls under the hood (raw `libc` sockets, not tokio) — MUST be
//!   wrapped in `spawn_blocking` (see `blocking.rs`) or it starves the tokio
//!   runtime, per migration-plan risk #2.
//!
//! NEEDS PRIVILEGED ENV: opening an `rtnetlink` socket itself does not
//! require privilege (`NETLINK_ROUTE` sockets are readable by any user for
//! `RTM_GETLINK` dumps), so `find_wg0_ifindex` should actually run in this
//! sandbox — it was validated live, no privilege needed for the read path.
//! Only *mutating* link state (create/delete) needs `CAP_NET_ADMIN`.

use futures::stream::TryStreamExt;
use rtnetlink::Handle;

/// Look up `wg0`'s ifindex via a raw rtnetlink link dump, independent of the
/// WireGuard generic-netlink family. Useful as a cheap, no-special-privilege
/// existence check before deciding whether `wg_control::probe_wg0` needs to
/// go down the (privileged) WG genl read path at all.
pub async fn find_wg0_ifindex(handle: &Handle) -> anyhow::Result<Option<u32>> {
    let mut links = handle.link().get().match_name("wg0".to_string()).execute();
    match links.try_next().await {
        Ok(Some(msg)) => Ok(Some(msg.header.index)),
        Ok(None) => Ok(None),
        Err(rtnetlink::Error::NetlinkError(e)) if e.raw_code() == -19 => {
            // ENODEV: "no such device" — wg0 doesn't exist yet.
            Ok(None)
        }
        Err(e) => Err(e.into()),
    }
}

/// Establishes an rtnetlink connection + spawns its driver task, mirroring
/// the pattern hub-router's control plane would use once per process.
pub fn connect() -> anyhow::Result<(Handle, tokio::task::JoinHandle<()>)> {
    let (conn, handle, _messages) = rtnetlink::new_connection()?;
    let driver = tokio::spawn(conn);
    Ok((handle, driver))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// VALIDATED live in this sandbox: rtnetlink link dumps need no
    /// elevated privilege, so this actually exercises the real kernel
    /// netlink path (unlike the wg_control tests, which fail-closed on
    /// EPERM). Asserts only that the call completes without panicking and
    /// returns a well-formed `Option` — the interface may or may not exist
    /// depending on the host.
    #[tokio::test(flavor = "multi_thread")]
    async fn link_dump_does_not_require_privilege() {
        let (handle, driver) = connect().expect("rtnetlink connection should open unprivileged");
        let result = find_wg0_ifindex(&handle).await;
        driver.abort();
        assert!(
            result.is_ok(),
            "unprivileged link dump should not error: {result:?}"
        );
    }
}
