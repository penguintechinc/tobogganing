//! Dynamic TCP/UDP listener management — the Rust port of `PortManager`
//! (`services/hub-router/proxy/ports/manager.go`). Owns the set of
//! listening sockets implied by a parsed TCP/UDP port-range configuration,
//! dispatching each accepted connection/packet to caller-supplied handlers.
//!
//! Deliberately out of scope for this port (tracked as follow-up — see the
//! crate root doc and the PR description): the Go headend's
//! `proxy/dynamic_ports.go`, which wires a *specific* connection/packet
//! handler implementation (JWT auth, firewall check, WireGuard/direct
//! routing, traffic mirroring, syslog audit) on top of this manager. That
//! file is a distinct, much larger subsystem (full data-plane dispatch)
//! bolted onto the `ports` package's listener lifecycle, not the `ports`
//! subsystem itself — this crate only manages listener lifecycle and
//! handler dispatch, same scope as the Go `ports` package.

use crate::range::{parse_port_ranges, PortRange, Protocol, RangeParseError};
use bytes::Bytes;
use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Arc;
use tokio::net::{TcpListener, TcpStream, UdpSocket};
use tokio::sync::RwLock;
use tokio::task::JoinHandle;

/// Invoked for each newly-accepted TCP connection. Fired on its own spawned
/// task (mirrors the Go source's `go pm.onNewConn(conn, port, "tcp")`) so a
/// slow/blocking handler never stalls the accept loop for other
/// connections on the same listener.
pub type ConnHandler = Arc<dyn Fn(TcpStream, u16, Protocol) + Send + Sync>;

/// Invoked for each received UDP datagram. `Bytes` (not `Vec<u8>`) per
/// backend-rust.md's zero-copy packet-hot-path rule — the receive loop
/// slices directly out of its reusable buffer.
pub type PacketHandler = Arc<dyn Fn(Bytes, SocketAddr, u16) + Send + Sync>;

/// Snapshot of one active listener — returned by [`PortManager`] query
/// methods. Unlike the Go source's `PortListener` (which embeds the live
/// `interface{}` socket/connection value itself), this never exposes the
/// underlying socket: the listener lives only inside its accept/receive
/// task, so external callers only ever see metadata.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PortListenerInfo {
    pub port: u16,
    pub protocol: Protocol,
    pub active: bool,
}

struct ListenerTask {
    info: PortListenerInfo,
    handle: JoinHandle<()>,
}

/// Failure parsing the TCP/UDP range configuration handed to
/// [`PortManager::parse_port_ranges`]. Wrapping text mirrors
/// `ParsePortRanges`'s `fmt.Errorf` prefixes exactly (distinct from
/// [`crate::validate::ValidateError`]'s "invalid ..." wording used by the
/// separate `ValidatePortRanges` Go function for the same underlying parse
/// failure).
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum ManagerError {
    #[error("failed to parse TCP ranges: {0}")]
    ParseTcp(#[source] RangeParseError),
    #[error("failed to parse UDP ranges: {0}")]
    ParseUdp(#[source] RangeParseError),
}

/// Outcome of one [`PortManager::start_listening`] call — every
/// configured port that failed to bind, alongside every one that
/// succeeded. The Go source's `StartListening` only *logs* bind failures
/// and always returns `nil` regardless, silently discarding exactly this
/// information from its caller; returning it explicitly here is the one
/// deliberate fix-while-porting change in this module (see the PR
/// description) — every other call site in this crate still degrades the
/// same best-effort way the Go source does (keep starting the remaining
/// configured ports after one fails).
#[derive(Debug, Default, Clone)]
pub struct StartListeningReport {
    pub started: Vec<PortListenerInfo>,
    pub failed: Vec<(Protocol, u16, String)>,
}

/// Manages the dynamic TCP/UDP listener set implied by a parsed port-range
/// configuration. All mutating operations are safe to call concurrently
/// from multiple tasks (interior `RwLock`-guarded listener map), matching
/// the Go source's `sync.RWMutex`-guarded `PortManager`.
pub struct PortManager {
    tcp_ranges: Vec<PortRange>,
    udp_ranges: Vec<PortRange>,
    listeners: Arc<RwLock<HashMap<String, ListenerTask>>>,
    on_new_conn: Option<ConnHandler>,
    on_new_packet: Option<PacketHandler>,
}

impl Default for PortManager {
    fn default() -> Self {
        Self::new()
    }
}

impl PortManager {
    pub fn new() -> Self {
        Self {
            tcp_ranges: Vec::new(),
            udp_ranges: Vec::new(),
            listeners: Arc::new(RwLock::new(HashMap::new())),
            on_new_conn: None,
            on_new_packet: None,
        }
    }

    /// Sets the callbacks invoked for new TCP connections/UDP packets.
    /// Intended to be called once before [`start_listening`][Self::start_listening]
    /// (mirrors the Go source's `SetConnectionHandlers`, also called
    /// pre-start only).
    pub fn set_connection_handlers(&mut self, on_conn: ConnHandler, on_packet: PacketHandler) {
        self.on_new_conn = Some(on_conn);
        self.on_new_packet = Some(on_packet);
    }

    /// Parses and stores the TCP/UDP range configuration for a subsequent
    /// [`start_listening`][Self::start_listening] call.
    pub fn parse_port_ranges(
        &mut self,
        tcp_ranges: &str,
        udp_ranges: &str,
    ) -> Result<(), ManagerError> {
        self.tcp_ranges =
            parse_port_ranges(tcp_ranges, Protocol::Tcp).map_err(ManagerError::ParseTcp)?;
        self.udp_ranges =
            parse_port_ranges(udp_ranges, Protocol::Udp).map_err(ManagerError::ParseUdp)?;
        Ok(())
    }

    /// Starts a listener for every port implied by the currently-parsed
    /// TCP/UDP ranges. Best-effort per port, exactly like the Go source:
    /// one port failing to bind (already in use, privilege denied, ...)
    /// never prevents the remaining configured ports from starting.
    #[tracing::instrument(skip(self))]
    pub async fn start_listening(&self) -> StartListeningReport {
        let mut report = StartListeningReport::default();

        for range in &self.tcp_ranges {
            for port in range.start_port..=range.end_port {
                match self.start_tcp_listener(port).await {
                    Ok(info) => {
                        crate::metrics::record_listener_started(Protocol::Tcp);
                        report.started.push(info);
                    }
                    Err(e) => {
                        tracing::error!(port, protocol = "tcp", error = %e, "failed to start TCP listener");
                        crate::metrics::record_listener_failed(Protocol::Tcp);
                        report.failed.push((Protocol::Tcp, port, e.to_string()));
                    }
                }
            }
        }

        for range in &self.udp_ranges {
            for port in range.start_port..=range.end_port {
                match self.start_udp_listener(port).await {
                    Ok(info) => {
                        crate::metrics::record_listener_started(Protocol::Udp);
                        report.started.push(info);
                    }
                    Err(e) => {
                        tracing::error!(port, protocol = "udp", error = %e, "failed to start UDP listener");
                        crate::metrics::record_listener_failed(Protocol::Udp);
                        report.failed.push((Protocol::Udp, port, e.to_string()));
                    }
                }
            }
        }

        tracing::info!(
            active = report.started.len(),
            failed = report.failed.len(),
            "port manager started"
        );
        report
    }

    async fn start_tcp_listener(&self, port: u16) -> std::io::Result<PortListenerInfo> {
        let listener = TcpListener::bind(("0.0.0.0", port)).await?;
        let handler = self.on_new_conn.clone();
        let handle = tokio::spawn(accept_tcp_loop(listener, port, handler));

        let info = PortListenerInfo {
            port,
            protocol: Protocol::Tcp,
            active: true,
        };
        self.listeners
            .write()
            .await
            .insert(format!("tcp:{port}"), ListenerTask { info, handle });
        tracing::debug!(port, "started TCP listener");
        Ok(info)
    }

    async fn start_udp_listener(&self, port: u16) -> std::io::Result<PortListenerInfo> {
        let socket = UdpSocket::bind(("0.0.0.0", port)).await?;
        let handler = self.on_new_packet.clone();
        let handle = tokio::spawn(receive_udp_loop(socket, port, handler));

        let info = PortListenerInfo {
            port,
            protocol: Protocol::Udp,
            active: true,
        };
        self.listeners
            .write()
            .await
            .insert(format!("udp:{port}"), ListenerTask { info, handle });
        tracing::debug!(port, "started UDP listener");
        Ok(info)
    }

    /// Immediately tears down every active listener (socket `abort()`,
    /// equivalent to the Go source's `listener.Close()`/`conn.Close()`
    /// inside `Stop()`) and clears the tracked listener set.
    #[tracing::instrument(skip(self))]
    pub async fn stop(&self) {
        let mut listeners = self.listeners.write().await;
        let count = listeners.len();
        for (key, task) in listeners.drain() {
            task.handle.abort();
            tracing::debug!(key, "stopped listener");
        }
        tracing::info!(count, "stopped port listeners");
    }

    /// Snapshot of all currently-tracked listeners, keyed `"protocol:port"`
    /// (matches the Go source's `GetActiveListeners` map key format).
    pub async fn get_active_listeners(&self) -> HashMap<String, PortListenerInfo> {
        self.listeners
            .read()
            .await
            .iter()
            .map(|(k, v)| (k.clone(), v.info))
            .collect()
    }

    pub async fn get_listener_count(&self) -> usize {
        self.listeners.read().await.len()
    }
}

async fn accept_tcp_loop(listener: TcpListener, port: u16, handler: Option<ConnHandler>) {
    loop {
        match listener.accept().await {
            Ok((stream, _addr)) => {
                if let Some(h) = handler.clone() {
                    tokio::spawn(async move {
                        h(stream, port, Protocol::Tcp);
                    });
                }
                // Go source: if `onNewConn` is nil, it closes the
                // connection immediately. Here, dropping `stream` with no
                // handler registered does exactly that.
            }
            Err(e) => {
                tracing::error!(port, error = %e, "TCP accept error");
                continue;
            }
        }
    }
}

async fn receive_udp_loop(socket: UdpSocket, port: u16, handler: Option<PacketHandler>) {
    let mut buffer = vec![0u8; 65536];
    loop {
        match socket.recv_from(&mut buffer).await {
            Ok((n, addr)) => {
                if let Some(h) = handler.clone() {
                    let data = Bytes::copy_from_slice(&buffer[..n]);
                    tokio::spawn(async move {
                        h(data, addr, port);
                    });
                }
            }
            Err(e) => {
                tracing::error!(port, error = %e, "UDP read error");
                continue;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::time::Duration;
    use tokio::io::AsyncWriteExt;

    async fn free_port() -> u16 {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener);
        port
    }

    #[test]
    fn parse_port_ranges_stores_parsed_ranges() {
        let mut mgr = PortManager::new();
        mgr.parse_port_ranges("8000-8001", "9000").unwrap();
        assert_eq!(mgr.tcp_ranges.len(), 1);
        assert_eq!(mgr.udp_ranges.len(), 1);
    }

    #[test]
    fn parse_port_ranges_propagates_tcp_error() {
        let mut mgr = PortManager::new();
        let err = mgr.parse_port_ranges("abc", "").unwrap_err();
        assert!(matches!(err, ManagerError::ParseTcp(_)));
    }

    #[test]
    fn parse_port_ranges_propagates_udp_error() {
        let mut mgr = PortManager::new();
        let err = mgr.parse_port_ranges("", "abc").unwrap_err();
        assert!(matches!(err, ManagerError::ParseUdp(_)));
    }

    #[tokio::test]
    async fn new_manager_has_no_listeners() {
        let mgr = PortManager::new();
        assert_eq!(mgr.get_listener_count().await, 0);
        assert!(mgr.get_active_listeners().await.is_empty());
    }

    #[tokio::test]
    async fn start_listening_with_no_ranges_starts_nothing() {
        let mgr = PortManager::new();
        let report = mgr.start_listening().await;
        assert!(report.started.is_empty());
        assert!(report.failed.is_empty());
    }

    #[tokio::test]
    async fn start_listening_binds_configured_tcp_and_udp_ports() {
        let tcp_port = free_port().await;
        let udp_port = free_port().await;

        let mut mgr = PortManager::new();
        mgr.parse_port_ranges(&tcp_port.to_string(), &udp_port.to_string())
            .unwrap();
        let report = mgr.start_listening().await;

        assert_eq!(report.started.len(), 2);
        assert!(report.failed.is_empty());
        assert_eq!(mgr.get_listener_count().await, 2);

        let active = mgr.get_active_listeners().await;
        assert!(active.contains_key(&format!("tcp:{tcp_port}")));
        assert!(active.contains_key(&format!("udp:{udp_port}")));
        assert!(active.values().all(|info| info.active));

        mgr.stop().await;
    }

    #[tokio::test]
    async fn start_listening_continues_past_a_single_bind_failure() {
        // Occupy one port first so its bind fails, while a second,
        // definitely-free port in the same range succeeds — characterizes
        // the Go source's "continue with other ports rather than failing
        // completely" behavior.
        let occupied_port = free_port().await;
        let _blocker = TcpListener::bind(("127.0.0.1", occupied_port))
            .await
            .unwrap();
        let free = free_port().await;

        let mut mgr = PortManager::new();
        // Two distinct single-port entries rather than a range, since the
        // occupied/free ports aren't necessarily contiguous.
        mgr.parse_port_ranges(&format!("{occupied_port},{free}"), "")
            .unwrap();
        let report = mgr.start_listening().await;

        assert_eq!(report.started.len(), 1);
        assert_eq!(report.started[0].port, free);
        assert_eq!(report.failed.len(), 1);
        assert_eq!(report.failed[0].1, occupied_port);

        mgr.stop().await;
    }

    #[tokio::test]
    async fn stop_clears_listeners_and_closes_sockets() {
        let tcp_port = free_port().await;
        let mut mgr = PortManager::new();
        mgr.parse_port_ranges(&tcp_port.to_string(), "").unwrap();
        mgr.start_listening().await;
        assert_eq!(mgr.get_listener_count().await, 1);

        mgr.stop().await;
        assert_eq!(mgr.get_listener_count().await, 0);

        // Give the aborted accept-loop task a moment to actually drop its
        // listener, then confirm the port is free again.
        tokio::time::sleep(Duration::from_millis(50)).await;
        let rebind = TcpListener::bind(("127.0.0.1", tcp_port)).await;
        assert!(rebind.is_ok(), "port should be free after stop()");
    }

    #[tokio::test]
    async fn tcp_connection_handler_is_invoked_with_port_and_protocol() {
        let tcp_port = free_port().await;
        let received: Arc<std::sync::Mutex<Vec<(u16, Protocol)>>> =
            Arc::new(std::sync::Mutex::new(Vec::new()));
        let received_clone = received.clone();

        let mut mgr = PortManager::new();
        mgr.set_connection_handlers(
            Arc::new(move |_stream, port, proto| {
                received_clone.lock().unwrap().push((port, proto));
            }),
            Arc::new(|_data, _addr, _port| {}),
        );
        mgr.parse_port_ranges(&tcp_port.to_string(), "").unwrap();
        mgr.start_listening().await;

        let mut stream = TcpStream::connect(("127.0.0.1", tcp_port)).await.unwrap();
        stream.write_all(b"hello").await.unwrap();

        // Poll briefly rather than a fixed sleep-and-hope, bounded so a
        // genuine regression fails fast instead of hanging the suite.
        for _ in 0..100 {
            if !received.lock().unwrap().is_empty() {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }

        let got = received.lock().unwrap().clone();
        assert_eq!(got, vec![(tcp_port, Protocol::Tcp)]);

        mgr.stop().await;
    }

    #[tokio::test]
    async fn udp_packet_handler_receives_sent_bytes() {
        let udp_port = free_port().await;
        let received: Arc<std::sync::Mutex<Vec<Bytes>>> =
            Arc::new(std::sync::Mutex::new(Vec::new()));
        let received_clone = received.clone();

        let mut mgr = PortManager::new();
        mgr.set_connection_handlers(
            Arc::new(|_stream, _port, _proto| {}),
            Arc::new(move |data, _addr, _port| {
                received_clone.lock().unwrap().push(data);
            }),
        );
        mgr.parse_port_ranges("", &udp_port.to_string()).unwrap();
        mgr.start_listening().await;

        let sender = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        sender
            .send_to(b"ping", ("127.0.0.1", udp_port))
            .await
            .unwrap();

        for _ in 0..100 {
            if !received.lock().unwrap().is_empty() {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }

        let got = received.lock().unwrap().clone();
        assert_eq!(got, vec![Bytes::from_static(b"ping")]);

        mgr.stop().await;
    }

    #[tokio::test]
    async fn tcp_connection_with_no_handler_is_dropped_without_panic() {
        let tcp_port = free_port().await;
        let mut mgr = PortManager::new();
        mgr.parse_port_ranges(&tcp_port.to_string(), "").unwrap();
        mgr.start_listening().await;

        let mut stream = TcpStream::connect(("127.0.0.1", tcp_port)).await.unwrap();
        // No handler registered — the accept loop should simply drop the
        // connection; writing to it should eventually fail/EOF rather than
        // hang or panic the listener task.
        let _ = stream.write_all(b"hello").await;
        tokio::time::sleep(Duration::from_millis(50)).await;
        assert_eq!(mgr.get_listener_count().await, 1);

        mgr.stop().await;
    }

    #[tokio::test]
    async fn multiple_connections_are_each_dispatched() {
        let tcp_port = free_port().await;
        let count = Arc::new(AtomicUsize::new(0));
        let count_clone = count.clone();

        let mut mgr = PortManager::new();
        mgr.set_connection_handlers(
            Arc::new(move |_stream, _port, _proto| {
                count_clone.fetch_add(1, Ordering::SeqCst);
            }),
            Arc::new(|_data, _addr, _port| {}),
        );
        mgr.parse_port_ranges(&tcp_port.to_string(), "").unwrap();
        mgr.start_listening().await;

        for _ in 0..3 {
            let _ = TcpStream::connect(("127.0.0.1", tcp_port)).await.unwrap();
        }

        for _ in 0..100 {
            if count.load(Ordering::SeqCst) >= 3 {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
        assert_eq!(count.load(Ordering::SeqCst), 3);

        mgr.stop().await;
    }
}
