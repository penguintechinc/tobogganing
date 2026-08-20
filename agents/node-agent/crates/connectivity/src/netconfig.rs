//! Applies the *real* interface address, allowed-IP routes, and upstream
//! DNS servers for a running WireGuard interface — the pieces the Go
//! reference client (`internal/vpn/embedded.go`'s `configureInterfaceIP`/
//! `configureDNS`) left as print-only stubs. Addresses/links/routes go
//! through `rtnetlink` (async, tokio-native); DNS is a direct
//! `/etc/resolv.conf` rewrite, matching the "not critical" best-effort
//! handling the Go reference already documents for DNS.

use futures::stream::TryStreamExt;
use node_agent_core::{AgentError, Result, WireguardConfig};
use rtnetlink::{Handle, LinkUnspec, RouteMessageBuilder};
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};
use std::path::Path;

/// Parses a `"<ip>/<prefix>"` CIDR string (WireGuard's `AllowedIPs`/
/// interface-address format) into an address and prefix length, validating
/// the prefix against the address family's bit width.
pub fn parse_cidr(s: &str) -> Result<(IpAddr, u8)> {
    let (addr_part, prefix_part) = s
        .split_once('/')
        .ok_or_else(|| AgentError::Config(format!("{s:?} is not in \"ip/prefix\" CIDR form")))?;
    let addr: IpAddr = addr_part
        .parse()
        .map_err(|e| AgentError::Config(format!("invalid address in {s:?}: {e}")))?;
    let prefix: u8 = prefix_part
        .parse()
        .map_err(|e| AgentError::Config(format!("invalid prefix length in {s:?}: {e}")))?;
    let max = if addr.is_ipv4() { 32 } else { 128 };
    if prefix > max {
        return Err(AgentError::Config(format!(
            "prefix length {prefix} exceeds {max} for address family in {s:?}"
        )));
    }
    Ok((addr, prefix))
}

/// Looks up `interface_name`'s link index — required by every subsequent
/// rtnetlink call. Returns [`AgentError::Task`] if the interface doesn't
/// exist (e.g. the boringtun device failed to come up).
async fn link_index(handle: &Handle, interface_name: &str) -> Result<u32> {
    let mut links = handle
        .link()
        .get()
        .match_name(interface_name.to_string())
        .execute();
    links
        .try_next()
        .await
        .map_err(|e| AgentError::Task(format!("rtnetlink link lookup failed: {e}")))?
        .map(|l| l.header.index)
        .ok_or_else(|| AgentError::Task(format!("interface {interface_name} not found")))
}

/// Assigns `cfg.interface_address` to `interface_name` and brings the link
/// up. Requires `CAP_NET_ADMIN` — callers should treat failure as a
/// capability gap to log and degrade from, not a crash.
pub async fn configure_address_and_link(
    handle: &Handle,
    interface_name: &str,
    cfg: &WireguardConfig,
) -> Result<()> {
    let index = link_index(handle, interface_name).await?;
    let (addr, prefix) = parse_cidr(&cfg.interface_address)?;
    handle
        .address()
        .add(index, addr, prefix)
        .execute()
        .await
        .map_err(|e| AgentError::Task(format!("failed to set interface address: {e}")))?;
    handle
        .link()
        .set(LinkUnspec::new_with_index(index).up().build())
        .execute()
        .await
        .map_err(|e| {
            AgentError::Task(format!(
                "failed to bring up interface {interface_name}: {e}"
            ))
        })?;
    Ok(())
}

/// Routes every CIDR in `cfg.allowed_ips` through `interface_name` with no
/// gateway — WireGuard tunnels are point-to-point over the noise session,
/// so the peer's allowed IPs are reached simply by egressing the tunnel
/// device. A single malformed entry is logged and skipped rather than
/// aborting the rest.
pub async fn configure_routes(
    handle: &Handle,
    interface_name: &str,
    cfg: &WireguardConfig,
) -> Result<()> {
    let index = link_index(handle, interface_name).await?;
    for allowed in &cfg.allowed_ips {
        let (addr, prefix) = match parse_cidr(allowed) {
            Ok(parsed) => parsed,
            Err(err) => {
                tracing::warn!(allowed_ip = %allowed, error = %err, "skipping invalid allowed_ip route");
                continue;
            }
        };
        let result = match addr {
            IpAddr::V4(v4) => {
                let route = RouteMessageBuilder::<Ipv4Addr>::new()
                    .destination_prefix(v4, prefix)
                    .output_interface(index)
                    .build();
                handle.route().add(route).execute().await
            }
            IpAddr::V6(v6) => {
                let route = RouteMessageBuilder::<Ipv6Addr>::new()
                    .destination_prefix(v6, prefix)
                    .output_interface(index)
                    .build();
                handle.route().add(route).execute().await
            }
        };
        if let Err(err) = result {
            tracing::warn!(allowed_ip = %allowed, error = %err, "failed to add route");
        }
    }
    Ok(())
}

/// Rewrites the resolver config at `path` to use `servers` — the
/// unit-testable core of [`configure_dns`]. Best-effort by contract: a
/// write failure is returned to the caller, who is expected to log and
/// continue rather than fail tunnel bring-up over DNS.
pub fn configure_dns_at(path: &Path, servers: &[String]) -> Result<()> {
    if servers.is_empty() {
        return Ok(());
    }
    let mut body = String::from("# managed by tobogganing node-agent (WireGuard)\n");
    for server in servers {
        body.push_str("nameserver ");
        body.push_str(server);
        body.push('\n');
    }
    std::fs::write(path, body).map_err(AgentError::Io)
}

/// Rewrites `/etc/resolv.conf` to point at `cfg.dns`. A no-op when `cfg.dns`
/// is empty (no DNS pushed down the tunnel).
pub fn configure_dns(cfg: &WireguardConfig) -> Result<()> {
    configure_dns_at(Path::new("/etc/resolv.conf"), &cfg.dns)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_cidr_accepts_valid_ipv4() {
        let (addr, prefix) = parse_cidr("10.200.0.5/32").expect("valid CIDR");
        assert_eq!(addr, "10.200.0.5".parse::<IpAddr>().unwrap());
        assert_eq!(prefix, 32);
    }

    #[test]
    fn parse_cidr_accepts_valid_ipv6() {
        let (addr, prefix) = parse_cidr("::/0").expect("valid CIDR");
        assert!(addr.is_ipv6());
        assert_eq!(prefix, 0);
    }

    #[test]
    fn parse_cidr_rejects_missing_slash() {
        assert!(parse_cidr("10.200.0.5").is_err());
    }

    #[test]
    fn parse_cidr_rejects_bad_address() {
        assert!(parse_cidr("not-an-ip/32").is_err());
    }

    #[test]
    fn parse_cidr_rejects_out_of_range_prefix() {
        assert!(parse_cidr("10.200.0.5/33").is_err());
        assert!(parse_cidr("::/129").is_err());
    }

    #[test]
    fn configure_dns_at_writes_nameserver_lines() {
        let dir = std::env::temp_dir().join(format!(
            "node-agent-connectivity-dns-test-{}-{}",
            std::process::id(),
            line!()
        ));
        std::fs::create_dir_all(&dir).expect("temp dir creatable");
        let path = dir.join("resolv.conf");

        configure_dns_at(&path, &["10.200.0.1".to_string(), "10.200.0.2".to_string()])
            .expect("write must succeed");
        let contents = std::fs::read_to_string(&path).expect("file must exist");
        assert!(contents.contains("nameserver 10.200.0.1\n"));
        assert!(contents.contains("nameserver 10.200.0.2\n"));

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn configure_dns_at_is_a_noop_for_empty_servers() {
        let path = Path::new("/nonexistent/should/not/be/touched/resolv.conf");
        configure_dns_at(path, &[])
            .expect("empty server list must be a no-op, not a write attempt");
    }
}
