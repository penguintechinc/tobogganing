//! NTP client (`ntp-proto`) that queries configured upstream servers and
//! computes clock offset and round-trip delay using the standard
//! four-timestamp formula (RFC 5905 SS8). Runtime-gated by
//! `NetsvcsEdgeConfig::ntp_enabled` (default off).
//!
//! `ntp-proto`'s packet-level API (`NtpPacket` and friends) is marked
//! "not intended as a public interface at this time" by its own docs and
//! sits behind the `__internal-api` cargo feature (enabled in this crate's
//! `Cargo.toml`) — it is nonetheless the crate this module was chosen to
//! use, and the only way to build/parse NTP packets with it.

use node_agent_core::{AgentError, NtpConfig, Result};
use ntp_proto::{NoCipher, NtpTimestamp, PollInterval};
use std::io::Cursor;
use std::net::{IpAddr, SocketAddr};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::net::UdpSocket;
use tokio_util::sync::CancellationToken;

const NTP_PORT: u16 = 123;
const QUERY_TIMEOUT: Duration = Duration::from_secs(5);
/// Seconds between the NTP epoch (1900-01-01) and the Unix epoch
/// (1970-01-01), per RFC 5905 SS6.
const NTP_UNIX_EPOCH_OFFSET: u32 = 2_208_988_800;
/// `2^6 = 64s` poll interval — a reasonable default between "chatty" and
/// "stale" for an edge client with no adaptive polling.
const DEFAULT_POLL_EXPONENT: i8 = 6;

/// The result of one successful NTP query: the server's stratum plus the
/// computed clock offset and round-trip delay, in seconds.
#[derive(Debug, Clone, Copy, PartialEq)]
pub(super) struct QueryResult {
    pub stratum: u8,
    pub offset_secs: f64,
    pub delay_secs: f64,
}

/// Runs the NTP client loop until `shutdown` is cancelled: round-robins
/// `cfg.servers`, querying one per `cfg.poll_interval_secs` tick and
/// logging the resulting offset/delay (or the failure).
pub(super) async fn run(cfg: NtpConfig, shutdown: CancellationToken) -> Result<()> {
    tracing::info!(module = "netsvcs-edge.ntp", servers = ?cfg.servers, "starting");

    if cfg.servers.is_empty() {
        tracing::warn!(
            module = "netsvcs-edge.ntp",
            "no NTP servers configured; idling until shutdown"
        );
        shutdown.cancelled().await;
        tracing::info!(module = "netsvcs-edge.ntp", "stopped");
        return Ok(());
    }

    let poll_interval = Duration::from_secs(u64::from(cfg.poll_interval_secs.max(1)));
    let mut next_server = 0usize;

    loop {
        let server = cfg.servers[next_server % cfg.servers.len()].clone();
        next_server = next_server.wrapping_add(1);

        match query_server(&server).await {
            Ok(result) => tracing::info!(
                module = "netsvcs-edge.ntp",
                server = %server,
                stratum = result.stratum,
                offset_secs = result.offset_secs,
                delay_secs = result.delay_secs,
                "NTP query succeeded"
            ),
            Err(err) => tracing::warn!(
                module = "netsvcs-edge.ntp",
                server = %server,
                error = %err,
                "NTP query failed"
            ),
        }

        tokio::select! {
            _ = shutdown.cancelled() => break,
            _ = tokio::time::sleep(poll_interval) => {}
        }
    }

    tracing::info!(module = "netsvcs-edge.ntp", "stopped");
    Ok(())
}

/// Sends a client `poll_message` to `server`, awaits the reply (bounded by
/// `QUERY_TIMEOUT`), validates it against the request's origin timestamp,
/// and computes offset/delay from the four exchange timestamps.
async fn query_server(server: &str) -> Result<QueryResult> {
    let addr = resolve_server(server).await?;
    let socket = UdpSocket::bind(("0.0.0.0", 0)).await?;
    socket.connect(addr).await?;

    let (request, identifier) =
        ntp_proto::NtpPacket::poll_message(PollInterval::from_byte(DEFAULT_POLL_EXPONENT as u8));

    let mut send_buf = [0u8; 1024];
    let len = {
        let mut cursor = Cursor::new(&mut send_buf[..]);
        request.serialize(&mut cursor, &NoCipher, None)?;
        cursor.position() as usize
    };

    let t1 = system_now_ntp();
    socket.send(&send_buf[..len]).await?;

    let mut recv_buf = [0u8; 1024];
    let n = tokio::time::timeout(QUERY_TIMEOUT, socket.recv(&mut recv_buf))
        .await
        .map_err(|_| {
            AgentError::Transport(format!("timed out waiting for NTP response from {server}"))
        })??;
    let t4 = system_now_ntp();

    let (response, _cookie) = ntp_proto::NtpPacket::deserialize(&recv_buf[..n], &NoCipher)
        .map_err(|err| AgentError::Transport(err.to_string()))?;

    if !response.valid_server_response(identifier, false) {
        return Err(AgentError::Transport(format!(
            "NTP response from {server} failed origin-timestamp validation"
        )));
    }

    let t2 = response.receive_timestamp();
    let t3 = response.transmit_timestamp();

    Ok(QueryResult {
        stratum: response.stratum(),
        offset_secs: ntp_offset_secs(t1, t2, t3, t4),
        delay_secs: ntp_delay_secs(t1, t2, t3, t4),
    })
}

/// Standard NTP client offset formula (RFC 5905 SS8):
/// `offset = ((T2 - T1) + (T3 - T4)) / 2`.
fn ntp_offset_secs(t1: NtpTimestamp, t2: NtpTimestamp, t3: NtpTimestamp, t4: NtpTimestamp) -> f64 {
    ((t2 - t1).to_seconds() + (t3 - t4).to_seconds()) / 2.0
}

/// Standard NTP client round-trip delay formula (RFC 5905 SS8):
/// `delay = (T4 - T1) - (T3 - T2)`.
fn ntp_delay_secs(t1: NtpTimestamp, t2: NtpTimestamp, t3: NtpTimestamp, t4: NtpTimestamp) -> f64 {
    (t4 - t1).to_seconds() - (t3 - t2).to_seconds()
}

/// Converts the current wall-clock time to an NTP-era timestamp.
fn system_now_ntp() -> NtpTimestamp {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let ntp_secs = (now.as_secs() as u32).wrapping_add(NTP_UNIX_EPOCH_OFFSET);
    NtpTimestamp::from_seconds_nanos_since_ntp_era(ntp_secs, now.subsec_nanos())
}

/// Resolves `server` (`host`, `host:port`, or a bare IP) to a `SocketAddr`,
/// defaulting to `NTP_PORT` when no port is present. Uses Tokio's async
/// resolver rather than `std::net::ToSocketAddrs` so a slow DNS lookup
/// never blocks the runtime.
async fn resolve_server(server: &str) -> Result<SocketAddr> {
    let target = normalize_server_addr(server);
    let resolved = tokio::net::lookup_host(&target).await?.next();
    resolved.ok_or_else(|| AgentError::Config(format!("could not resolve NTP server {server}")))
}

fn normalize_server_addr(server: &str) -> String {
    if server.parse::<SocketAddr>().is_ok() {
        return server.to_string();
    }
    if let Ok(ip) = server.parse::<IpAddr>() {
        return SocketAddr::new(ip, NTP_PORT).to_string();
    }
    if let Some((_, port)) = server.rsplit_once(':') {
        if port.parse::<u16>().is_ok() {
            return server.to_string();
        }
    }
    format!("{server}:{NTP_PORT}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalize_bare_hostname_appends_default_port() {
        assert_eq!(normalize_server_addr("pool.ntp.org"), "pool.ntp.org:123");
    }

    #[test]
    fn normalize_hostname_with_port_is_passed_through() {
        assert_eq!(
            normalize_server_addr("ntp.internal:1230"),
            "ntp.internal:1230"
        );
    }

    #[test]
    fn normalize_bare_ipv4_appends_default_port() {
        assert_eq!(normalize_server_addr("192.0.2.1"), "192.0.2.1:123");
    }

    #[test]
    fn normalize_socket_addr_is_passed_through() {
        assert_eq!(normalize_server_addr("192.0.2.1:9123"), "192.0.2.1:9123");
    }

    #[test]
    fn offset_and_delay_formulas_match_hand_computed_values() {
        let t1 = NtpTimestamp::from_seconds_nanos_since_ntp_era(1_000, 0);
        let t2 = NtpTimestamp::from_seconds_nanos_since_ntp_era(1_001, 0);
        let t3 = NtpTimestamp::from_seconds_nanos_since_ntp_era(1_001, 0);
        let t4 = NtpTimestamp::from_seconds_nanos_since_ntp_era(1_002, 0);

        // offset = ((1001-1000) + (1001-1002)) / 2 = (1 + -1) / 2 = 0
        assert!((ntp_offset_secs(t1, t2, t3, t4) - 0.0).abs() < 1e-6);
        // delay = (1002-1000) - (1001-1001) = 2 - 0 = 2
        assert!((ntp_delay_secs(t1, t2, t3, t4) - 2.0).abs() < 1e-6);
    }

    #[test]
    fn request_response_wireformat_round_trip_validates_origin_timestamp() {
        // Build a client request, serialize + parse it (wireformat round
        // trip), then build a server-shaped response echoing the request's
        // transmit timestamp as its origin timestamp — exactly what a real
        // NTP server does — and confirm `valid_server_response` accepts it
        // and rejects a response with a mismatched origin timestamp.
        let (request, identifier) = ntp_proto::NtpPacket::poll_message(PollInterval::from_byte(6));

        let mut buf = [0u8; 1024];
        let len = {
            let mut cursor = Cursor::new(&mut buf[..]);
            request.serialize(&mut cursor, &NoCipher, None).unwrap();
            cursor.position() as usize
        };
        let (decoded_request, _cookie) =
            ntp_proto::NtpPacket::deserialize(&buf[..len], &NoCipher).unwrap();

        let mut good_response = ntp_proto::NtpPacket::test();
        good_response.set_mode(ntp_proto::NtpAssociationMode::Server);
        good_response.set_origin_timestamp(decoded_request.transmit_timestamp());
        good_response
            .set_transmit_timestamp(NtpTimestamp::from_seconds_nanos_since_ntp_era(2_000, 0));
        good_response
            .set_receive_timestamp(NtpTimestamp::from_seconds_nanos_since_ntp_era(1_999, 0));
        assert!(good_response.valid_server_response(identifier, false));

        let (_second_request, second_identifier) =
            ntp_proto::NtpPacket::poll_message(PollInterval::from_byte(6));
        let mut mismatched_response = ntp_proto::NtpPacket::test();
        mismatched_response.set_mode(ntp_proto::NtpAssociationMode::Server);
        mismatched_response
            .set_origin_timestamp(NtpTimestamp::from_seconds_nanos_since_ntp_era(1, 0));
        assert!(!mismatched_response.valid_server_response(second_identifier, false));
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn run_idles_until_shutdown_when_no_servers_are_configured() {
        let shutdown = CancellationToken::new();
        let shutdown_clone = shutdown.clone();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(20)).await;
            shutdown_clone.cancel();
        });

        let result =
            tokio::time::timeout(Duration::from_secs(5), run(NtpConfig::default(), shutdown))
                .await
                .expect("run must return promptly after cancellation, not hang");
        assert!(result.is_ok());
    }

    /// Spins up a minimal loopback UDP "NTP server" that answers exactly
    /// one client poll with a well-formed, origin-timestamp-matching
    /// response — enough to drive `query_server`'s full success path
    /// (serialize request, send, receive, validate, compute offset/delay)
    /// without a live NTP server.
    async fn spawn_fake_ntp_server() -> std::net::SocketAddr {
        let socket = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let addr = socket.local_addr().unwrap();

        tokio::spawn(async move {
            let mut buf = [0u8; 1024];
            let Ok((n, peer)) = socket.recv_from(&mut buf).await else {
                return;
            };
            let Ok((decoded_request, _cookie)) =
                ntp_proto::NtpPacket::deserialize(&buf[..n], &NoCipher)
            else {
                return;
            };

            let mut response = ntp_proto::NtpPacket::test();
            response.set_mode(ntp_proto::NtpAssociationMode::Server);
            response.set_origin_timestamp(decoded_request.transmit_timestamp());
            response.set_receive_timestamp(system_now_ntp());
            response.set_transmit_timestamp(system_now_ntp());

            let mut out = [0u8; 1024];
            let len = {
                let mut cursor = Cursor::new(&mut out[..]);
                response.serialize(&mut cursor, &NoCipher, None).unwrap();
                cursor.position() as usize
            };
            let _ = socket.send_to(&out[..len], peer).await;
        });

        addr
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn query_server_computes_offset_and_delay_against_a_fake_local_server() {
        let addr = spawn_fake_ntp_server().await;
        let result = query_server(&addr.to_string())
            .await
            .expect("query against the fake local server must succeed");
        assert!(result.offset_secs.is_finite());
        assert!(result.delay_secs.is_finite());
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn query_server_times_out_against_a_silent_server() {
        // Bound but never responds — proves the `QUERY_TIMEOUT` path maps
        // to a `Transport` error rather than hanging indefinitely.
        let socket = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let addr = socket.local_addr().unwrap();
        tokio::spawn(async move {
            let mut buf = [0u8; 1024];
            let _ = socket.recv_from(&mut buf).await; // absorb the request, never reply
        });

        let err = tokio::time::timeout(
            QUERY_TIMEOUT + Duration::from_secs(2),
            query_server(&addr.to_string()),
        )
        .await
        .expect("query_server itself must time out well before the outer guard")
        .expect_err("a silent server must surface as a timeout error");
        assert!(matches!(err, AgentError::Transport(_)));
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn run_completes_a_successful_query_cycle_then_stops_on_cancel() {
        let addr = spawn_fake_ntp_server().await;
        let shutdown = CancellationToken::new();
        let shutdown_clone = shutdown.clone();
        tokio::spawn(async move {
            // Long enough for the fake server to have answered and `run`
            // to have logged the successful query before we cancel.
            tokio::time::sleep(Duration::from_millis(200)).await;
            shutdown_clone.cancel();
        });

        let cfg = NtpConfig {
            servers: vec![addr.to_string()],
            poll_interval_secs: 1,
        };
        let result = tokio::time::timeout(Duration::from_secs(10), run(cfg, shutdown))
            .await
            .expect("run must return promptly after cancellation, not hang");
        assert!(result.is_ok());
    }
}
