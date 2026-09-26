//! Goal 1: kernel WireGuard device/peer control via the `wireguard-control`
//! crate (pure-Rust netlink under the hood — verified by reading its source
//! in `~/.cargo/registry/src/.../wireguard-control-2.0.0/src/backends/kernel.rs`,
//! not just its crate description).
//!
//! Key finding from source inspection: `DeviceUpdate::apply()` calls an
//! internal `add_del(iface, true)` which issues `RTM_NEWLINK` with
//! `NLM_F_CREATE | NLM_F_EXCL`, and explicitly swallows `ErrorKind::AlreadyExists`.
//! That means `apply()` is idempotent w.r.t. link creation: calling it against
//! an already-existing `wg0` (e.g. one `wg-quick` created) does NOT fail and
//! does NOT tear it down — it just pushes the given device/peer attributes on
//! top. Combined with `Device::get()` to read current state first, this is
//! the adopt-without-teardown path the cutover plan needs (§4.5 phase 3).

use std::io;
use wireguard_control::{Backend, Device, DeviceUpdate, InterfaceName, Key, PeerConfigBuilder};

/// WireGuard interface name the hub-router owns in production (`wg0`).
pub const WG_IFACE: &str = "wg0";

/// Result of probing for an existing WireGuard device on this host.
#[derive(Debug)]
pub enum ProbeResult {
    /// No `wg0` device found — this process should create + own it.
    Absent,
    /// `wg0` exists with the given peer count — this process should adopt it
    /// (read state, then apply non-destructively) rather than recreate it.
    ExistingDevice {
        peer_count: usize,
        listen_port: Option<u16>,
    },
}

/// Goal 1a/1c: does `wg0` already exist, and if so what does it look like?
///
/// This is the first call the Rust control plane makes at startup — it
/// decides create-fresh vs adopt-existing (cutover phase 3, decision #3 in
/// the migration plan: the Rust process owns `wg0` going forward, but must
/// not disrupt an interface the old `entrypoint.sh`/`wg-quick` already set up
/// during the handoff window).
///
/// NEEDS PRIVILEGED ENV: reading device state via the WireGuard generic
/// netlink family requires `CAP_NET_ADMIN` (or root) even for reads. In this
/// sandbox (no `CAP_NET_ADMIN`, confirmed via `ip link add ... type wireguard`
/// -> "Operation not permitted") this returns `Err` with `EPERM`/`EACCES` —
/// that failure path is exactly what's exercised by the unit test below.
pub fn probe_wg0() -> io::Result<ProbeResult> {
    let iface: InterfaceName = WG_IFACE.parse().map_err(|e| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("bad interface name: {e}"),
        )
    })?;

    let existing = Device::list(Backend::Kernel)?;
    if !existing.iter().any(|n| n.as_str_lossy() == WG_IFACE) {
        return Ok(ProbeResult::Absent);
    }

    let dev = Device::get(&iface, Backend::Kernel)?;
    Ok(ProbeResult::ExistingDevice {
        peer_count: dev.peers.len(),
        listen_port: dev.listen_port,
    })
}

/// Goal 1a: create `wg0` fresh and own its lifecycle (the non-adoption path,
/// e.g. first boot on a node that has never run the Go daemon).
///
/// `apply()` both creates the link (via the internal add_del) and pushes the
/// device config in one call — no separate `ip link add` step needed.
pub fn create_wg0(private_key: Key, listen_port: u16) -> io::Result<()> {
    let iface: InterfaceName = WG_IFACE
        .parse()
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, format!("{e}")))?;

    DeviceUpdate::new()
        .set_private_key(private_key)
        .set_listen_port(listen_port)
        .apply(&iface, Backend::Kernel)
}

/// Goal 1b: add/update a peer without disturbing existing peers.
///
/// Deliberately does NOT call `.replace_peers()` — that flag is what would
/// wipe every peer not in this call's list. Omitting it means the WG generic
/// netlink layer merges: a peer with a new pubkey is added, a peer with a
/// matching pubkey is updated in place, and every other existing peer is left
/// alone. This is the behavior the adopt-on-startup path depends on.
pub fn upsert_peer(pubkey: Key, allowed_ip_cidr: &str) -> io::Result<()> {
    let iface: InterfaceName = WG_IFACE
        .parse()
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, format!("{e}")))?;

    let allowed_ip: wireguard_control::AllowedIp = allowed_ip_cidr
        .parse()
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "bad CIDR"))?;

    let peer = PeerConfigBuilder::new(&pubkey).add_allowed_ip(allowed_ip.address, allowed_ip.cidr);

    DeviceUpdate::new()
        .add_peer(peer)
        .apply(&iface, Backend::Kernel)
}

/// Goal 1b: list configured peers — replaces the Go anti-pattern of shelling
/// `wg show wg0 allowed-ips` and string-parsing the output per connection.
pub fn list_peers() -> io::Result<Vec<(String, Vec<String>)>> {
    let iface: InterfaceName = WG_IFACE
        .parse()
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, format!("{e}")))?;

    let dev = Device::get(&iface, Backend::Kernel)?;
    Ok(dev
        .peers
        .into_iter()
        .map(|p| {
            let key = p.config.public_key.to_base64();
            let ips = p
                .config
                .allowed_ips
                .iter()
                .map(|ip| format!("{}/{}", ip.address, ip.cidr))
                .collect();
            (key, ips)
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// VALIDATED (no privilege needed): confirms the crate's `InterfaceName`
    /// parser accepts `wg0` and the API shapes used above compile against
    /// wireguard-control 2.0.0's real signatures (this is a compile-time
    /// assertion as much as a runtime one — the test existing and compiling
    /// is itself half the finding).
    #[test]
    fn wg0_interface_name_parses() {
        let iface: Result<InterfaceName, _> = WG_IFACE.parse();
        assert!(iface.is_ok(), "wg0 must be a valid InterfaceName");
    }

    /// NEEDS PRIVILEGED ENV to reach the "found it" branch. In this sandbox
    /// (no CAP_NET_ADMIN) `Device::list` itself fails, so we assert the
    /// failure is a permission error, not a panic/crash — i.e. the code
    /// degrades to `Err` cleanly rather than unwrapping.
    #[test]
    fn probe_wg0_fails_closed_without_net_admin() {
        match probe_wg0() {
            Ok(_) => {
                // Running with CAP_NET_ADMIN in some other environment —
                // both outcomes are acceptable, we just must not panic.
            }
            Err(e) => {
                assert!(
                    matches!(e.kind(), io::ErrorKind::PermissionDenied)
                        || e.raw_os_error() == Some(libc::EPERM)
                        || e.raw_os_error() == Some(libc::EACCES),
                    "unexpected error kind without CAP_NET_ADMIN: {e:?}"
                );
            }
        }
    }
}
