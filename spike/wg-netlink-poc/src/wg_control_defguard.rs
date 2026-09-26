//! Goal 1, alternate crate: same probe/create/adopt/list operations as
//! `wg_control.rs`, implemented against `defguard_wireguard_rs` 0.12.1
//! instead of `wireguard-control` 2.0.0.
//!
//! Why this module exists: `cargo deny check` on this crate (see
//! `deny.toml`) FAILS on `wireguard-control` — it is itself
//! `LGPL-2.1-or-later` licensed (not just a transitive dependency issue) and
//! its dependency tree is pinned to old `netlink-packet-*` versions that pull
//! in `paste` v1.0.15, flagged unmaintained (RUSTSEC-2024-0436, no safe
//! upgrade). `defguard_wireguard_rs` is Apache-2.0 and depends on the current
//! `netlink-packet-*` line (0.9/0.5/0.33/0.6) — verified clean against the
//! same `deny.toml` in isolation (see spike report). **This is the
//! recommended crate**, not `wireguard-control`.

use std::io;

use defguard_wireguard_rs::{
    host::Host, key::Key as DgKey, net::IpAddrMask, peer::Peer, InterfaceConfiguration, Kernel,
    WGApi, WireguardInterfaceApi,
};

use crate::wg_control::WG_IFACE;

fn map_err(e: defguard_wireguard_rs::error::WireguardInterfaceError) -> io::Error {
    io::Error::other(e.to_string())
}

/// Goal 1a/1c: read current `wg0` state (equivalent to `wg show`), the
/// adoption read-path. `create_interface()` below is idempotent (its Linux
/// netlink backend swallows `EEXIST`, confirmed by reading
/// `defguard_wireguard_rs-0.12.1/src/netlink.rs`), so calling it against an
/// already-running `wg0` is safe and does not tear it down.
///
/// NEEDS PRIVILEGED ENV: same as `wg_control::probe_wg0` — WireGuard generic
/// netlink reads require `CAP_NET_ADMIN`.
pub fn read_wg0() -> io::Result<Host> {
    let api = WGApi::<Kernel>::new(WG_IFACE.to_string()).map_err(map_err)?;
    api.read_interface_data().map_err(map_err)
}

/// Goal 1a: create-or-adopt `wg0` and push device config. Mirrors
/// `wg_control::create_wg0` but via the Apache-2.0-licensed crate.
pub fn create_or_adopt_wg0(private_key_hex: &str, listen_port: u16) -> io::Result<()> {
    let mut api = WGApi::<Kernel>::new(WG_IFACE.to_string()).map_err(map_err)?;
    api.create_interface().map_err(map_err)?;

    let config = InterfaceConfiguration {
        name: WG_IFACE.to_string(),
        prvkey: private_key_hex.to_string(),
        addresses: Vec::new(),
        port: listen_port,
        peers: Vec::new(),
        mtu: None,
        fwmark: None,
    };
    api.configure_interface(&config).map_err(map_err)
}

/// Goal 1b: upsert a single peer without touching others — `configure_peer`
/// is documented as "Adds a peer or updates peer configuration", matching
/// the non-destructive merge semantics `wg_control::upsert_peer` relies on.
pub fn upsert_peer(pubkey_hex: &str, allowed_ip_cidr: &str) -> io::Result<()> {
    let api = WGApi::<Kernel>::new(WG_IFACE.to_string()).map_err(map_err)?;

    let public_key = DgKey::decode(pubkey_hex)
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e.to_string()))?;
    let allowed_ip: IpAddrMask = allowed_ip_cidr
        .parse()
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "bad CIDR"))?;

    let mut peer = Peer::new(public_key);
    peer.allowed_ips.push(allowed_ip);

    api.configure_peer(&peer).map_err(map_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// VALIDATED (no privilege needed): confirms the `WGApi::<Kernel>::new`
    /// constructor and struct wiring compile against defguard_wireguard_rs
    /// 0.12.1's real signatures — `new()` itself does no privileged I/O, it
    /// only stores the interface name.
    #[test]
    fn wgapi_construction_does_not_require_privilege() {
        let api = WGApi::<Kernel>::new(WG_IFACE.to_string());
        assert!(api.is_ok(), "WGApi::new should not touch the kernel");
    }

    /// NEEDS PRIVILEGED ENV: reading wg0 state requires CAP_NET_ADMIN. Fails
    /// closed (Err, no panic) in this sandbox.
    #[test]
    fn read_wg0_fails_closed_without_net_admin() {
        match read_wg0() {
            Ok(_) => {
                // CAP_NET_ADMIN present in some other environment — fine.
            }
            Err(e) => {
                // defguard wraps the underlying OS error in its own error
                // type + Display; we only assert it's a clean Err, not that
                // it's a specific io::ErrorKind (the crate's error enum
                // doesn't preserve the raw errno through `io::Error::other`).
                assert!(!e.to_string().is_empty());
            }
        }
    }
}
