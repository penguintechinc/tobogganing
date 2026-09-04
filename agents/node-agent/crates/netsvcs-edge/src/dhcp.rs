//! DHCP client (`dhcproto`) that performs a DISCOVER -> OFFER -> REQUEST ->
//! ACK exchange against the LAN's DHCP server and periodically renews the
//! resulting lease. Runtime-gated by `NetsvcsEdgeConfig::dhcp_enabled`
//! (default off) — most PenguinTech edge deployments run behind
//! infrastructure-managed DHCP and opt in only when this node itself needs
//! a client-side lease (e.g. bare-metal edge hardware).
//!
//! Binding the client identifier to the real NIC hardware address for
//! `DhcpConfig::interface` requires OS-specific interface enumeration not
//! pulled in here; until that lands, `chaddr` is a process-local
//! locally-administered synthetic address (RFC 7042 SS2.1), which is
//! sufficient to complete a real DISCOVER/OFFER/REQUEST/ACK exchange and
//! obtain a routable lease from a standards-compliant DHCP server.

use dhcproto::v4::{DhcpOption, DhcpOptions, Flags, HType, Message, MessageType, OptionCode};
use dhcproto::{Decodable, Decoder, Encodable, Encoder};
use node_agent_core::{AgentError, DhcpConfig, Result};
use std::net::Ipv4Addr;
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::net::UdpSocket;
use tokio_util::sync::CancellationToken;

const DHCP_CLIENT_PORT: u16 = 68;
const DHCP_SERVER_PORT: u16 = 67;
const LEASE_RETRY_INTERVAL: Duration = Duration::from_secs(300);
const LEASE_RESPONSE_TIMEOUT: Duration = Duration::from_secs(5);
const MIN_RENEWAL_SECS: u32 = 60;
const DEFAULT_LEASE_SECS: u32 = 3600;

/// A minimal view of a granted DHCP lease — enough to log and to schedule
/// the next renewal attempt.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) struct Lease {
    pub your_ip: Ipv4Addr,
    pub server_ip: Ipv4Addr,
    pub lease_secs: u32,
}

/// Runs the DHCP client loop until `shutdown` is cancelled: attempts a
/// DISCOVER/OFFER/REQUEST/ACK exchange, then sleeps until the next renewal
/// attempt (half the granted lease time, or a fixed retry interval on
/// failure), repeating until cancelled.
pub(super) async fn run(cfg: DhcpConfig, shutdown: CancellationToken) -> Result<()> {
    tracing::info!(module = "netsvcs-edge.dhcp", interface = ?cfg.interface, "starting");

    let chaddr = synthetic_chaddr();

    loop {
        let next_attempt = match acquire_lease(&chaddr, cfg.hostname.as_deref()).await {
            Ok(lease) => {
                tracing::info!(
                    module = "netsvcs-edge.dhcp",
                    your_ip = %lease.your_ip,
                    server_ip = %lease.server_ip,
                    lease_secs = lease.lease_secs,
                    "DHCP lease acquired"
                );
                Duration::from_secs(u64::from(lease.lease_secs.max(MIN_RENEWAL_SECS) / 2))
            }
            Err(err) => {
                tracing::warn!(
                    module = "netsvcs-edge.dhcp",
                    error = %err,
                    "DHCP lease acquisition failed; retrying later"
                );
                LEASE_RETRY_INTERVAL
            }
        };

        tokio::select! {
            _ = shutdown.cancelled() => break,
            _ = tokio::time::sleep(next_attempt) => {}
        }
    }

    tracing::info!(module = "netsvcs-edge.dhcp", "stopped");
    Ok(())
}

/// Performs one full DISCOVER/OFFER/REQUEST/ACK exchange over a broadcast
/// UDP socket and returns the granted lease.
async fn acquire_lease(chaddr: &[u8; 6], hostname: Option<&str>) -> Result<Lease> {
    let socket = UdpSocket::bind((Ipv4Addr::UNSPECIFIED, DHCP_CLIENT_PORT)).await?;
    socket.set_broadcast(true)?;

    let xid = next_xid();
    let discover = build_discover(xid, chaddr, hostname);
    socket
        .send_to(
            &encode_message(&discover)?,
            (Ipv4Addr::BROADCAST, DHCP_SERVER_PORT),
        )
        .await?;

    let offer = recv_message_of_type(&socket, xid, MessageType::Offer).await?;
    let offered_ip = offer.yiaddr();
    let server_id = server_identifier(&offer)?;

    let request = build_request(xid, chaddr, offered_ip, server_id, hostname);
    socket
        .send_to(
            &encode_message(&request)?,
            (Ipv4Addr::BROADCAST, DHCP_SERVER_PORT),
        )
        .await?;

    let ack = recv_message_of_type(&socket, xid, MessageType::Ack).await?;
    Ok(Lease {
        your_ip: ack.yiaddr(),
        server_ip: server_identifier(&ack).unwrap_or(offered_ip),
        lease_secs: lease_time(&ack).unwrap_or(DEFAULT_LEASE_SECS),
    })
}

/// Receives datagrams until one decodes as a DHCP message matching `xid`
/// and `want`'s message type, or `LEASE_RESPONSE_TIMEOUT` elapses.
/// Malformed or unrelated broadcast traffic on the same port is ignored
/// rather than treated as fatal.
async fn recv_message_of_type(socket: &UdpSocket, xid: u32, want: MessageType) -> Result<Message> {
    let recv_loop = async {
        loop {
            let mut buf = [0u8; 1500];
            let (n, _src) = socket.recv_from(&mut buf).await?;
            let Ok(msg) = Message::decode(&mut Decoder::new(&buf[..n])) else {
                continue;
            };
            if msg.xid() != xid {
                continue;
            }
            if msg.opts().msg_type() == Some(want) {
                return Ok::<Message, std::io::Error>(msg);
            }
        }
    };

    tokio::time::timeout(LEASE_RESPONSE_TIMEOUT, recv_loop)
        .await
        .map_err(|_| AgentError::Transport(format!("timed out waiting for DHCP {want:?}")))?
        .map_err(AgentError::from)
}

/// Builds the base header shared by DISCOVER and REQUEST: BootRequest
/// opcode, Ethernet hardware type, and the broadcast flag set (this client
/// has no IP yet, so the reply must be broadcast back).
fn base_message(xid: u32, chaddr: &[u8; 6]) -> Message {
    let mut msg = Message::new_with_id(
        xid,
        Ipv4Addr::UNSPECIFIED,
        Ipv4Addr::UNSPECIFIED,
        Ipv4Addr::UNSPECIFIED,
        Ipv4Addr::UNSPECIFIED,
        chaddr,
    );
    msg.set_htype(HType::Eth);
    msg.set_flags(Flags::default().set_broadcast());
    msg
}

fn parameter_request_list() -> Vec<OptionCode> {
    vec![
        OptionCode::SubnetMask,
        OptionCode::Router,
        OptionCode::DomainNameServer,
        OptionCode::AddressLeaseTime,
    ]
}

/// Builds a DHCPDISCOVER message per RFC 2131 SS4.4.1.
pub(super) fn build_discover(xid: u32, chaddr: &[u8; 6], hostname: Option<&str>) -> Message {
    let mut msg = base_message(xid, chaddr);
    let mut opts = DhcpOptions::default();
    opts.insert(DhcpOption::MessageType(MessageType::Discover));
    opts.insert(DhcpOption::ParameterRequestList(parameter_request_list()));
    if let Some(hostname) = hostname {
        opts.insert(DhcpOption::Hostname(hostname.to_string()));
    }
    msg.set_opts(opts);
    msg
}

/// Builds a DHCPREQUEST message per RFC 2131 SS4.3.2, selecting the offer
/// identified by `requested_ip`/`server_id`.
pub(super) fn build_request(
    xid: u32,
    chaddr: &[u8; 6],
    requested_ip: Ipv4Addr,
    server_id: Ipv4Addr,
    hostname: Option<&str>,
) -> Message {
    let mut msg = base_message(xid, chaddr);
    let mut opts = DhcpOptions::default();
    opts.insert(DhcpOption::MessageType(MessageType::Request));
    opts.insert(DhcpOption::RequestedIpAddress(requested_ip));
    opts.insert(DhcpOption::ServerIdentifier(server_id));
    opts.insert(DhcpOption::ParameterRequestList(parameter_request_list()));
    if let Some(hostname) = hostname {
        opts.insert(DhcpOption::Hostname(hostname.to_string()));
    }
    msg.set_opts(opts);
    msg
}

fn encode_message(msg: &Message) -> Result<Vec<u8>> {
    let mut buf = Vec::new();
    let mut encoder = Encoder::new(&mut buf);
    msg.encode(&mut encoder)
        .map_err(|err| AgentError::Transport(err.to_string()))?;
    Ok(buf)
}

fn server_identifier(msg: &Message) -> Result<Ipv4Addr> {
    match msg.opts().get(OptionCode::ServerIdentifier) {
        Some(DhcpOption::ServerIdentifier(ip)) => Ok(*ip),
        _ => Err(AgentError::Transport(
            "DHCP response missing server identifier option".to_string(),
        )),
    }
}

fn lease_time(msg: &Message) -> Option<u32> {
    match msg.opts().get(OptionCode::AddressLeaseTime) {
        Some(DhcpOption::AddressLeaseTime(secs)) => Some(*secs),
        _ => None,
    }
}

/// Generates a process-local, locally-administered, unicast MAC address
/// (the U/L and I/G bits per RFC 7042 SS2.1) to use as `chaddr` — stable
/// for the lifetime of this process, never collides with real hardware
/// addresses on the segment.
fn synthetic_chaddr() -> [u8; 6] {
    let seed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0)
        ^ (std::process::id() as u64).wrapping_shl(32);

    let bytes = seed.to_be_bytes();
    let mut mac = [0u8; 6];
    mac.copy_from_slice(&bytes[2..8]);
    // Locally administered (bit 1 set) + unicast (bit 0 clear) in the first
    // octet, per the standard MAC address convention.
    mac[0] = (mac[0] & 0b1111_1100) | 0b0000_0010;
    mac
}

/// Monotonically increasing transaction ID source — DHCP only requires
/// per-exchange uniqueness on the wire, not cryptographic randomness.
fn next_xid() -> u32 {
    static COUNTER: AtomicU32 = AtomicU32::new(0);
    let seed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(0);
    seed ^ COUNTER.fetch_add(1, Ordering::Relaxed)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn discover_round_trips_through_wire_encoding() {
        let chaddr = [0x02, 0x11, 0x22, 0x33, 0x44, 0x55];
        let msg = build_discover(0xdead_beef, &chaddr, Some("edge-node"));
        let wire = encode_message(&msg).unwrap();

        let decoded = Message::decode(&mut Decoder::new(&wire)).unwrap();
        assert_eq!(decoded.xid(), 0xdead_beef);
        assert_eq!(decoded.chaddr(), &chaddr);
        assert_eq!(decoded.opts().msg_type(), Some(MessageType::Discover));
        assert!(decoded.flags().broadcast());
        assert_eq!(
            decoded.opts().get(OptionCode::Hostname),
            Some(&DhcpOption::Hostname("edge-node".to_string()))
        );
    }

    #[test]
    fn request_round_trips_and_carries_offered_ip_and_server_id() {
        let chaddr = [0x02, 0xaa, 0xbb, 0xcc, 0xdd, 0xee];
        let offered = Ipv4Addr::new(192, 0, 2, 42);
        let server = Ipv4Addr::new(192, 0, 2, 1);
        let msg = build_request(1, &chaddr, offered, server, None);
        let wire = encode_message(&msg).unwrap();

        let decoded = Message::decode(&mut Decoder::new(&wire)).unwrap();
        assert_eq!(decoded.opts().msg_type(), Some(MessageType::Request));
        assert_eq!(
            decoded.opts().get(OptionCode::RequestedIpAddress),
            Some(&DhcpOption::RequestedIpAddress(offered))
        );
        assert_eq!(
            decoded.opts().get(OptionCode::ServerIdentifier),
            Some(&DhcpOption::ServerIdentifier(server))
        );
    }

    #[test]
    fn server_identifier_extracts_from_a_well_formed_ack() {
        let mut opts = DhcpOptions::default();
        opts.insert(DhcpOption::MessageType(MessageType::Ack));
        opts.insert(DhcpOption::ServerIdentifier(Ipv4Addr::new(10, 0, 0, 1)));
        opts.insert(DhcpOption::AddressLeaseTime(1800));
        let mut msg = base_message(5, &[0, 1, 2, 3, 4, 5]);
        msg.set_opts(opts);

        assert_eq!(server_identifier(&msg).unwrap(), Ipv4Addr::new(10, 0, 0, 1));
        assert_eq!(lease_time(&msg), Some(1800));
    }

    #[test]
    fn server_identifier_errors_when_option_missing() {
        let msg = base_message(6, &[0, 1, 2, 3, 4, 5]);
        assert!(server_identifier(&msg).is_err());
        assert_eq!(lease_time(&msg), None);
    }

    #[test]
    fn synthetic_chaddr_is_locally_administered_unicast() {
        let mac = synthetic_chaddr();
        assert_eq!(mac[0] & 0b0000_0011, 0b0000_0010);
    }

    #[test]
    fn next_xid_values_are_not_all_identical() {
        let a = next_xid();
        let b = next_xid();
        assert_ne!(a, b);
    }

    /// This process runs unprivileged, so binding `DHCP_CLIENT_PORT` (68,
    /// a privileged port) fails immediately — exercising `run`'s
    /// error-and-retry loop iteration plus the shutdown-vs-sleep `select!`
    /// without waiting out `LEASE_RETRY_INTERVAL`.
    #[tokio::test(flavor = "multi_thread")]
    async fn run_logs_and_retries_when_the_client_socket_cannot_bind_then_stops_on_cancel() {
        let shutdown = CancellationToken::new();
        let shutdown_clone = shutdown.clone();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(50)).await;
            shutdown_clone.cancel();
        });

        let result =
            tokio::time::timeout(Duration::from_secs(5), run(DhcpConfig::default(), shutdown))
                .await
                .expect(
                    "run must return promptly after cancellation, not wait out the retry interval",
                );
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn acquire_lease_fails_when_the_privileged_client_port_is_unavailable() {
        let chaddr = [0x02, 0x01, 0x02, 0x03, 0x04, 0x05];
        let err = acquire_lease(&chaddr, None)
            .await
            .expect_err("binding the privileged DHCP client port must fail unprivileged");
        assert!(matches!(err, AgentError::Io(_)));
    }
}
