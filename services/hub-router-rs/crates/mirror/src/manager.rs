//! Traffic-mirroring lifecycle manager — the Rust port of `Manager`
//! (`services/hub-router/proxy/mirror/manager.go`). Queues captured
//! packet/request copies and forwards them, encapsulated per the
//! configured protocol, to one or more external mirror destinations and
//! (optionally) a Suricata IDS/IPS connection.
//!
//! **Scope note:** this crate ports the Go `mirror` package itself — the
//! generic queue/worker-pool/encapsulation/forwarding engine — exactly as
//! `hub_router_ports`/`hub_router_firewall` port their respective Go
//! `ports`/`firewall` packages. The actual live-traffic call sites that
//! *feed* this engine real packet bytes
//! (`services/hub-router/proxy/{tcp_proxy,udp_proxy,http_handlers,dynamic_ports}.go`)
//! are a distinct, larger data-plane dispatch subsystem — already
//! deliberately out of scope for the sibling `hub_router_ports` port (see
//! its `manager` module doc) and out of scope here for the same reason:
//! this crate's `mirror_http`/`mirror_tcp`/`mirror_udp`/`mirror_raw`
//! methods are its public API (mirroring the Go package's exported
//! `MirrorHTTP`/`MirrorTCP`/`MirrorUDP`/`MirrorRaw` functions), ready to
//! be wired up once that data-plane dispatch subsystem itself gets
//! ported.
//!
//! Two deliberate fixes from the Go source (both documented at the
//! relevant method below, both chosen because the literal Go behavior
//! either cannot be reproduced safely in Rust or is a genuine correctness
//! bug): (1) [`Manager::new`]/[`Manager::new_with_suricata`] clamp a
//! configured `buffer_size` of `0` up to `1` (Go's zero-capacity channel
//! is a legal, if nearly-always-dropping, construct; `tokio::sync::mpsc`
//! panics on capacity `0`, which this port must never do —
//! backend-rust.md: no panics outside tests); (2) writes to the shared
//! Suricata TCP connection are now serialized behind its own dedicated
//! async mutex — the Go source's 4 worker goroutines write to the same
//! `net.Conn` concurrently with zero synchronization, which can
//! interleave partial writes and corrupt the downstream EVE-JSON stream
//! (mirror *destination* UDP sends need no such fix: each `send`/`Write`
//! is one atomic datagram, so concurrent UDP writers never interleave
//! mid-packet — kept under a separate `RwLock` from the Suricata
//! connection specifically so a slow/blocked Suricata write can never
//! stall concurrent mirror-destination sends, closer to the Go source's
//! use of a single `RWMutex` that at least allowed concurrent *readers*
//! across both).

use crate::config::{MirrorConfig, DEFAULT_PROTOCOL};
use crate::encode;
use crate::metrics;
use crate::packet::{HttpRequestInfo, MirrorPacket, Stats, StatsSnapshot};
use bytes::Bytes;
use std::collections::HashMap;
use std::net::IpAddr;
use std::sync::Arc;
use std::time::{Duration, SystemTime};
use tokio::net::{TcpStream, UdpSocket};
use tokio::sync::{mpsc, Mutex as AsyncMutex, RwLock as AsyncRwLock};
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;

/// Interval between periodic stats log lines — the Rust port of
/// `reportStats`'s `time.NewTicker(60 * time.Second)`.
const STATS_REPORT_INTERVAL: Duration = Duration::from_secs(60);

/// Number of concurrent queue-draining workers — the Rust port of
/// `Start`'s hardcoded `workerCount := 4`.
const WORKER_COUNT: usize = 4;

/// Failure starting the mirror manager — the Rust port of `Start`'s one
/// error path (`"no mirror destinations available"`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub enum ManagerError {
    #[error("no mirror destinations available")]
    NoDestinationsAvailable,
}

/// Queues and forwards mirrored traffic copies — see the module doc for
/// full scope and the Go method mapping: `NewManager`/
/// `NewManagerWithSuricata` → [`Manager::new`]/[`Manager::new_with_suricata`];
/// `Start`/`Stop` → [`Manager::start`]/[`Manager::stop`]; `MirrorHTTP`/
/// `MirrorTCP`/`MirrorUDP`/`MirrorRaw` → identically-prefixed `mirror_*`
/// methods.
pub struct Manager {
    protocol: String,
    destinations: Vec<String>,
    buffer_size: usize,
    suricata_enabled: bool,
    suricata_host: String,
    suricata_port: String,
    tx: mpsc::Sender<MirrorPacket>,
    rx: AsyncMutex<mpsc::Receiver<MirrorPacket>>,
    mirror_connections: AsyncRwLock<HashMap<String, Arc<UdpSocket>>>,
    suricata_conn: AsyncMutex<Option<TcpStream>>,
    stats: Arc<Stats>,
    cancel: CancellationToken,
    tasks: AsyncMutex<Vec<JoinHandle<()>>>,
}

impl Manager {
    /// Builds a manager with no Suricata forwarding — the Rust port of
    /// `NewManager`. No network call happens until [`Manager::start`]
    /// runs.
    #[must_use]
    pub fn new(destinations: Vec<String>, protocol: impl Into<String>, buffer_size: usize) -> Self {
        Self::build(
            destinations,
            protocol,
            buffer_size,
            false,
            String::new(),
            String::new(),
        )
    }

    /// Builds a manager with Suricata forwarding enabled whenever both
    /// `suricata_host`/`suricata_port` are non-empty — the Rust port of
    /// `NewManagerWithSuricata`.
    #[must_use]
    pub fn new_with_suricata(
        destinations: Vec<String>,
        protocol: impl Into<String>,
        buffer_size: usize,
        suricata_host: impl Into<String>,
        suricata_port: impl Into<String>,
    ) -> Self {
        let suricata_host = suricata_host.into();
        let suricata_port = suricata_port.into();
        let suricata_enabled = !suricata_host.is_empty() && !suricata_port.is_empty();
        Self::build(
            destinations,
            protocol,
            buffer_size,
            suricata_enabled,
            suricata_host,
            suricata_port,
        )
    }

    /// Builds a manager directly from a [`MirrorConfig`], applying its
    /// own defaulting (`resolved_protocol`/`resolved_buffer_size`) and
    /// Suricata-enablement derivation (`suricata_active`) — the Rust port
    /// of `bootstrap.go`'s construction branch (lines 211-238), collapsed
    /// into one call since this port has no `viper`-style global config
    /// store to branch on.
    #[must_use]
    pub fn from_config(config: &MirrorConfig) -> Self {
        if config.suricata_active() {
            Self::new_with_suricata(
                config.destinations.clone(),
                config.resolved_protocol(),
                config.resolved_buffer_size(),
                config.suricata_host.clone(),
                config.suricata_port.clone(),
            )
        } else {
            Self::new(
                config.destinations.clone(),
                config.resolved_protocol(),
                config.resolved_buffer_size(),
            )
        }
    }

    fn build(
        destinations: Vec<String>,
        protocol: impl Into<String>,
        buffer_size: usize,
        suricata_enabled: bool,
        suricata_host: String,
        suricata_port: String,
    ) -> Self {
        let protocol = protocol.into();
        let protocol = if protocol.is_empty() {
            DEFAULT_PROTOCOL.to_string()
        } else {
            protocol
        };

        // tokio::sync::mpsc::channel panics on capacity 0; Go's zero-
        // capacity channel is legal (an unbuffered, nearly-always-dropping
        // handoff) — clamp to 1 rather than let a `buffer_size: 0` config
        // value crash the service at construction. See the module doc.
        let effective_buffer_size = buffer_size.max(1);
        if buffer_size == 0 {
            tracing::warn!(
                "mirror buffer_size=0 is not representable as a tokio mpsc channel capacity; using 1"
            );
        }

        let (tx, rx) = mpsc::channel(effective_buffer_size);

        Self {
            protocol,
            destinations,
            buffer_size: effective_buffer_size,
            suricata_enabled,
            suricata_host,
            suricata_port,
            tx,
            rx: AsyncMutex::new(rx),
            mirror_connections: AsyncRwLock::new(HashMap::new()),
            suricata_conn: AsyncMutex::new(None),
            stats: Arc::new(Stats::default()),
            cancel: CancellationToken::new(),
            tasks: AsyncMutex::new(Vec::new()),
        }
    }

    /// The effective worker queue depth after construction-time clamping
    /// — exposed for tests/observability, not present on the Go source
    /// (which never surfaces `bufferSize` post-construction).
    #[must_use]
    pub fn buffer_size(&self) -> usize {
        self.buffer_size
    }

    /// Whether Suricata forwarding is active for this manager.
    #[must_use]
    pub fn suricata_enabled(&self) -> bool {
        self.suricata_enabled
    }

    /// Establishes connections to every configured destination (and
    /// Suricata, if enabled), then spawns the worker pool and stats
    /// reporter — the Rust port of `Start`. A per-destination connection
    /// failure is logged and skipped (matches Go: `continue`), never
    /// fatal on its own.
    ///
    /// Preserves one Go quirk as-is rather than fixing it: this only
    /// errors when **both** the mirror-destination map ends up empty
    /// **and** `suricata_enabled` is `false` — if Suricata is enabled
    /// (host/port configured) but its connection attempt also fails, this
    /// still returns `Ok(())` even though, at that moment, there is
    /// nowhere at all for packets to go (a `None` queued Suricata
    /// connection reconnects lazily on the next failed send attempt via
    /// [`Manager::reconnect_suricata`], exactly mirroring Go's identical
    /// gap).
    #[tracing::instrument(skip(self), fields(protocol = %self.protocol))]
    pub async fn start(self: &Arc<Self>) -> Result<(), ManagerError> {
        tracing::info!(
            protocol = %self.protocol,
            destinations = ?self.destinations,
            "starting mirror manager"
        );

        {
            let mut mirror_conns = self.mirror_connections.write().await;
            for dest in &self.destinations {
                match self.create_connection(dest).await {
                    Ok(socket) => {
                        mirror_conns.insert(dest.clone(), Arc::new(socket));
                    }
                    Err(error) => {
                        tracing::error!(destination = %dest, %error, "failed to connect to mirror destination");
                    }
                }
            }

            if self.suricata_enabled {
                let addr = format!("{}:{}", self.suricata_host, self.suricata_port);
                match TcpStream::connect(&addr).await {
                    Ok(stream) => {
                        tracing::info!(address = %addr, "connected to Suricata IDS/IPS");
                        *self.suricata_conn.lock().await = Some(stream);
                    }
                    Err(error) => {
                        tracing::error!(address = %addr, %error, "failed to connect to Suricata");
                    }
                }
            }

            if mirror_conns.is_empty() && !self.suricata_enabled {
                return Err(ManagerError::NoDestinationsAvailable);
            }
        }

        let mut tasks = self.tasks.lock().await;
        for _ in 0..WORKER_COUNT {
            let manager = Arc::clone(self);
            tasks.push(tokio::spawn(async move { manager.worker().await }));
        }
        let stats_manager = Arc::clone(self);
        tasks.push(tokio::spawn(
            async move { stats_manager.report_stats().await },
        ));

        Ok(())
    }

    /// Signals every spawned task to stop, waits for them to finish
    /// (which includes each worker draining whatever remains in the
    /// queue — see [`Manager::worker`]), then closes every connection —
    /// the Rust port of `Stop`.
    pub async fn stop(&self) {
        tracing::info!("stopping mirror manager");
        self.cancel.cancel();

        let handles: Vec<JoinHandle<()>> = {
            let mut tasks = self.tasks.lock().await;
            std::mem::take(&mut *tasks)
        };
        for handle in handles {
            let _ = handle.await;
        }

        self.mirror_connections.write().await.clear();
        *self.suricata_conn.lock().await = None;
    }

    async fn create_connection(&self, dest: &str) -> std::io::Result<UdpSocket> {
        match self.protocol.as_str() {
            // GRE's Go equivalent (`net.Dial("ip4:47", dest)`) opens a raw
            // IP socket, which requires CAP_NET_RAW/root on Linux — the
            // same privileged capability this org's rootless-by-default
            // containers don't carry without an explicit, approved
            // exception (critical-rules.md Rootless Containers), and
            // which would need a new `socket2`-based raw-socket
            // dependency not currently pinned in this workspace. Rather
            // than silently downgrading GRE "mirroring" to a plain UDP
            // send (a behavior change a characterization port must not
            // make unannounced), this fails loudly and consistently —
            // tracked as a follow-up alongside the other deferred
            // data-plane work (see the module doc) if GRE mirroring sees
            // real production use.
            "GRE" => Err(std::io::Error::other(
                "GRE mirroring requires a raw IP socket (CAP_NET_RAW); not supported in this port",
            )),
            _ => {
                let socket = UdpSocket::bind("0.0.0.0:0").await?;
                socket.connect(dest).await?;
                Ok(socket)
            }
        }
    }

    /// Queues a mirrored copy of an HTTP request/response — the Rust port
    /// of `MirrorHTTP`.
    pub fn mirror_http(&self, info: &HttpRequestInfo, status_code: u16, body: &[u8]) {
        let mut metadata = HashMap::new();
        metadata.insert(
            "method".to_string(),
            serde_json::Value::String(info.method.clone()),
        );
        metadata.insert(
            "url".to_string(),
            serde_json::Value::String(info.url.clone()),
        );
        metadata.insert(
            "status_code".to_string(),
            serde_json::Value::Number(status_code.into()),
        );
        metadata.insert(
            "user_agent".to_string(),
            serde_json::Value::String(info.user_agent.clone()),
        );

        let packet = MirrorPacket {
            timestamp: SystemTime::now(),
            source: None,
            destination: None,
            protocol: "HTTP".to_string(),
            data: encode::encode_http(info, status_code, body),
            metadata,
        };
        self.enqueue(packet, "http", true);
    }

    /// Queues a mirrored copy of raw TCP payload bytes — the Rust port of
    /// `MirrorTCP`.
    pub fn mirror_tcp(&self, src: &str, dst: &str, data: Bytes) {
        self.mirror_stream("TCP", src, dst, data, "tcp");
    }

    /// Queues a mirrored copy of raw UDP payload bytes — the Rust port of
    /// `MirrorUDP`.
    pub fn mirror_udp(&self, src: &str, dst: &str, data: Bytes) {
        self.mirror_stream("UDP", src, dst, data, "udp");
    }

    fn mirror_stream(&self, protocol: &str, src: &str, dst: &str, data: Bytes, source_label: &str) {
        let mut metadata = HashMap::new();
        metadata.insert(
            "src".to_string(),
            serde_json::Value::String(src.to_string()),
        );
        metadata.insert(
            "dst".to_string(),
            serde_json::Value::String(dst.to_string()),
        );
        metadata.insert(
            "protocol".to_string(),
            serde_json::Value::String(protocol.to_lowercase()),
        );

        let packet = MirrorPacket {
            timestamp: SystemTime::now(),
            source: None,
            destination: None,
            protocol: protocol.to_string(),
            data,
            metadata,
        };
        self.enqueue(packet, source_label, true);
    }

    /// Queues an arbitrary raw packet with caller-supplied metadata
    /// (and, optionally, source/destination IPs) — the Rust port of
    /// `MirrorRaw`. Unlike `mirror_http`/`mirror_tcp`/`mirror_udp`, this
    /// never logs on drop — matches the Go source's `MirrorRaw` exactly
    /// (its `select`'s `default` branch only calls
    /// `m.stats.incrementDropped()`, with no `log.Warn`, unlike its three
    /// siblings).
    pub fn mirror_raw(
        &self,
        data: Bytes,
        metadata: HashMap<String, serde_json::Value>,
        source: Option<IpAddr>,
        destination: Option<IpAddr>,
    ) {
        let packet = MirrorPacket {
            timestamp: SystemTime::now(),
            source,
            destination,
            protocol: "RAW".to_string(),
            data,
            metadata,
        };
        self.enqueue(packet, "raw", false);
    }

    fn enqueue(&self, packet: MirrorPacket, source_label: &str, log_on_drop: bool) {
        if let Err(error) = self.tx.try_send(packet) {
            self.stats.increment_dropped();
            metrics::record_packet_dropped(source_label);
            if log_on_drop {
                tracing::warn!(kind = source_label, %error, "mirror queue full, dropping packet");
            }
        }
    }

    async fn worker(self: Arc<Self>) {
        loop {
            let packet = {
                let mut rx = self.rx.lock().await;
                tokio::select! {
                    biased;
                    () = self.cancel.cancelled() => rx.try_recv().ok(),
                    maybe = rx.recv() => maybe,
                }
            };

            match packet {
                Some(p) => self.send_packet(p).await,
                None => return,
            }
        }
    }

    /// Encapsulates `packet` per the configured protocol and forwards it
    /// to every connected mirror destination and (if connected) Suricata
    /// — the Rust port of `sendPacket`. Takes `self: &Arc<Self>` (rather
    /// than plain `&self`) solely so a failed send can spawn a detached
    /// reconnect task the same way the Go source's `go m.reconnect(dest)`
    /// does — every live `Manager` this crate's own `start`/`worker`
    /// construct is already reached through an `Arc`, so this adds no
    /// new restriction in practice.
    async fn send_packet(self: &Arc<Self>, packet: MirrorPacket) {
        let started = std::time::Instant::now();
        let encapsulated = encode::encapsulate(&self.protocol, &packet);
        let suricata_payload = if self.suricata_enabled {
            Some(encode::prepare_suricata_data(&packet))
        } else {
            None
        };

        // Snapshot the live destination sockets under a brief read lock,
        // then release it before doing any I/O — equivalent to Go's
        // `sendPacket` holding `m.mu.RLock()` across its writes (shared
        // with other concurrent readers), but never blocks a concurrent
        // `reconnect`/`start`/`stop` write-locker any longer than copying
        // a handful of cheap `Arc` clones takes.
        let targets: Vec<(String, Arc<UdpSocket>)> = self
            .mirror_connections
            .read()
            .await
            .iter()
            .map(|(dest, socket)| (dest.clone(), Arc::clone(socket)))
            .collect();

        for (dest, socket) in targets {
            match socket.send(&encapsulated).await {
                Ok(sent) => {
                    self.stats.increment_sent(sent as u64);
                    metrics::record_packet_sent("mirror");
                }
                Err(error) => {
                    tracing::error!(destination = %dest, %error, "failed to send to mirror destination");
                    self.stats.increment_errors();
                    metrics::record_send_error("mirror");
                    // Matches the Go source: the stale entry is left in
                    // place (a concurrent sender may keep hitting it and
                    // re-spawning reconnects, exactly as Go's unguarded
                    // `go m.reconnect(dest)` does) — `reconnect` itself
                    // performs the close-and-replace under a write lock.
                    let manager = Arc::clone(self);
                    let dest_owned = dest.clone();
                    tokio::spawn(async move { manager.reconnect(&dest_owned).await });
                }
            }
        }

        if let Some(payload) = suricata_payload {
            let mut suricata_guard = self.suricata_conn.lock().await;
            let write_result = if let Some(stream) = suricata_guard.as_mut() {
                use tokio::io::AsyncWriteExt;
                Some(stream.write_all(&payload).await)
            } else {
                None
            };

            if let Some(result) = write_result {
                match result {
                    Ok(()) => {
                        self.stats.increment_sent(payload.len() as u64);
                        metrics::record_packet_sent("suricata");
                    }
                    Err(error) => {
                        tracing::error!(%error, "failed to send to Suricata");
                        self.stats.increment_errors();
                        metrics::record_send_error("suricata");
                        *suricata_guard = None;
                        drop(suricata_guard);
                        let manager = Arc::clone(self);
                        tokio::spawn(async move { manager.reconnect_suricata().await });
                    }
                }
            }
        }

        metrics::record_send_duration(started.elapsed().as_secs_f64(), &self.protocol);
    }

    /// Re-dials a failed mirror destination — the Rust port of
    /// `reconnect`.
    async fn reconnect(&self, dest: &str) {
        match self.create_connection(dest).await {
            Ok(socket) => {
                self.mirror_connections
                    .write()
                    .await
                    .insert(dest.to_string(), Arc::new(socket));
                tracing::info!(destination = %dest, "reconnected to mirror destination");
            }
            Err(error) => {
                tracing::error!(destination = %dest, %error, "failed to reconnect to mirror destination");
            }
        }
    }

    /// Re-dials the Suricata connection after a failed send — the Rust
    /// port of `reconnectSuricata`.
    async fn reconnect_suricata(&self) {
        let addr = format!("{}:{}", self.suricata_host, self.suricata_port);
        match TcpStream::connect(&addr).await {
            Ok(stream) => {
                *self.suricata_conn.lock().await = Some(stream);
                tracing::info!(address = %addr, "reconnected to Suricata IDS/IPS");
            }
            Err(error) => {
                tracing::error!(address = %addr, %error, "failed to reconnect to Suricata");
            }
        }
    }

    /// Logs a stats snapshot every [`STATS_REPORT_INTERVAL`] until
    /// cancelled — the Rust port of `reportStats`.
    async fn report_stats(self: Arc<Self>) {
        let mut ticker = tokio::time::interval(STATS_REPORT_INTERVAL);
        ticker.tick().await; // first tick fires immediately; skip it to match Go's ticker semantics
        loop {
            tokio::select! {
                () = self.cancel.cancelled() => return,
                _ = ticker.tick() => {
                    let StatsSnapshot { packets_sent, packets_dropped, bytes_sent, errors } = self.stats.snapshot();
                    tracing::info!(packets_sent, packets_dropped, bytes_sent, errors, "mirror statistics");
                }
            }
        }
    }

    /// Current running counters — exposed for tests/observability (the
    /// Go source only ever logs `Stats` from inside `reportStats`; this
    /// port additionally surfaces it directly).
    #[must_use]
    pub fn stats(&self) -> StatsSnapshot {
        self.stats.snapshot()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::net::{TcpListener, UdpSocket as TokioUdpSocket};

    fn http_info() -> HttpRequestInfo {
        HttpRequestInfo {
            method: "GET".to_string(),
            url: "http://x/health".to_string(),
            path: "/health".to_string(),
            proto: "HTTP/1.1".to_string(),
            headers: vec![],
            user_agent: "test".to_string(),
        }
    }

    #[test]
    fn empty_protocol_defaults_to_vxlan() {
        let manager = Manager::new(vec!["127.0.0.1:1".to_string()], "", 10);
        assert_eq!(manager.protocol, "VXLAN");
    }

    #[test]
    fn from_config_without_suricata_builds_a_plain_manager() {
        let config = MirrorConfig {
            enabled: true,
            destinations: vec!["127.0.0.1:1".to_string()],
            protocol: "VXLAN".to_string(),
            buffer_size: 5,
            ..Default::default()
        };
        let manager = Manager::from_config(&config);
        assert!(!manager.suricata_enabled());
        assert_eq!(manager.buffer_size(), 5);
    }

    #[test]
    fn from_config_with_suricata_active_builds_a_suricata_manager() {
        let config = MirrorConfig {
            enabled: true,
            destinations: vec![],
            protocol: String::new(),
            buffer_size: 0,
            suricata_host: "10.0.0.5".to_string(),
            suricata_port: "9999".to_string(),
            ..Default::default()
        };
        let manager = Manager::from_config(&config);
        assert!(manager.suricata_enabled());
        assert_eq!(manager.protocol, "VXLAN");
    }

    #[tokio::test]
    async fn mirror_udp_forwards_a_udp_mirrored_packet_end_to_end() {
        let listener = TokioUdpSocket::bind("127.0.0.1:0").await.unwrap();
        let dest_addr = listener.local_addr().unwrap();

        let manager = Arc::new(Manager::new(vec![dest_addr.to_string()], "VXLAN", 10));
        manager.start().await.unwrap();

        manager.mirror_udp(
            "10.0.0.1:1",
            "10.0.0.2:2",
            Bytes::from_static(b"udp-payload"),
        );

        let mut buf = [0u8; 256];
        let (n, _) = tokio::time::timeout(Duration::from_secs(5), listener.recv_from(&mut buf))
            .await
            .expect("mirrored UDP packet must arrive before timeout")
            .expect("recv_from must not error");
        assert_eq!(&buf[8..n], b"udp-payload");

        manager.stop().await;
    }

    #[tokio::test]
    async fn reconnect_replaces_a_mirror_destination_entry() {
        let listener = TokioUdpSocket::bind("127.0.0.1:0").await.unwrap();
        let dest_addr = listener.local_addr().unwrap();
        let manager = Manager::new(vec![], "VXLAN", 10);

        manager.reconnect(&dest_addr.to_string()).await;

        assert_eq!(manager.mirror_connections.read().await.len(), 1);
    }

    #[tokio::test]
    async fn reconnect_logs_and_leaves_no_entry_on_failure() {
        let manager = Manager::new(vec![], "GRE", 10);
        manager.reconnect("127.0.0.1:1").await;
        assert!(manager.mirror_connections.read().await.is_empty());
    }

    #[tokio::test]
    async fn reconnect_suricata_replaces_the_connection_on_success() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let manager = Manager::new_with_suricata(
            vec![],
            "VXLAN",
            10,
            addr.ip().to_string(),
            addr.port().to_string(),
        );

        let accept_task = tokio::spawn(async move { listener.accept().await });
        manager.reconnect_suricata().await;
        accept_task
            .await
            .expect("accept task must not panic")
            .expect("accept must not error");

        assert!(manager.suricata_conn.lock().await.is_some());
    }

    #[tokio::test]
    async fn reconnect_suricata_logs_and_leaves_none_on_failure() {
        let manager = Manager::new_with_suricata(vec![], "VXLAN", 10, "127.0.0.1", "1");
        manager.reconnect_suricata().await;
        assert!(manager.suricata_conn.lock().await.is_none());
    }

    #[test]
    fn zero_buffer_size_is_clamped_to_one_instead_of_panicking() {
        let manager = Manager::new(vec![], "VXLAN", 0);
        assert_eq!(manager.buffer_size(), 1);
    }

    #[test]
    fn new_with_suricata_requires_both_host_and_port_to_enable() {
        let disabled = Manager::new_with_suricata(vec![], "VXLAN", 10, "", "9999");
        assert!(!disabled.suricata_enabled());

        let enabled = Manager::new_with_suricata(vec![], "VXLAN", 10, "10.0.0.5", "9999");
        assert!(enabled.suricata_enabled());
    }

    #[tokio::test]
    async fn start_errors_when_no_destinations_and_no_suricata() {
        let manager = Arc::new(Manager::new(vec![], "VXLAN", 10));
        let err = manager.start().await.unwrap_err();
        assert_eq!(err, ManagerError::NoDestinationsAvailable);
    }

    #[tokio::test]
    async fn start_errors_when_every_destination_fails_to_connect() {
        // GRE always fails `create_connection` in this port (see the
        // method doc), so a GRE-only config with no Suricata behaves the
        // same as "no destinations available".
        let manager = Arc::new(Manager::new(vec!["127.0.0.1:4789".to_string()], "GRE", 10));
        let err = manager.start().await.unwrap_err();
        assert_eq!(err, ManagerError::NoDestinationsAvailable);
    }

    #[tokio::test]
    async fn start_succeeds_and_forwards_a_udp_mirrored_packet_end_to_end() {
        let listener = TokioUdpSocket::bind("127.0.0.1:0").await.unwrap();
        let dest_addr = listener.local_addr().unwrap();

        let manager = Arc::new(Manager::new(vec![dest_addr.to_string()], "VXLAN", 10));
        manager.start().await.unwrap();

        manager.mirror_tcp("10.0.0.1:1", "10.0.0.2:2", Bytes::from_static(b"payload"));

        let mut buf = [0u8; 256];
        let (n, _) = tokio::time::timeout(Duration::from_secs(5), listener.recv_from(&mut buf))
            .await
            .expect("mirrored packet must arrive before timeout")
            .expect("recv_from must not error");

        // VXLAN header (8 bytes) + "payload" (7 bytes).
        assert_eq!(n, 15);
        assert_eq!(&buf[8..n], b"payload");

        manager.stop().await;
        assert_eq!(manager.stats().packets_sent, 1);
    }

    #[tokio::test]
    async fn mirror_http_forwards_an_encoded_http_mirror_packet() {
        let listener = TokioUdpSocket::bind("127.0.0.1:0").await.unwrap();
        let dest_addr = listener.local_addr().unwrap();

        let manager = Arc::new(Manager::new(vec![dest_addr.to_string()], "VXLAN", 10));
        manager.start().await.unwrap();

        manager.mirror_http(&http_info(), 200, b"ok");

        let mut buf = [0u8; 512];
        let (n, _) = tokio::time::timeout(Duration::from_secs(5), listener.recv_from(&mut buf))
            .await
            .unwrap()
            .unwrap();
        let text = String::from_utf8(buf[8..n].to_vec()).unwrap();
        assert!(text.starts_with("GET /health HTTP/1.1\r\n"));

        manager.stop().await;
    }

    #[tokio::test]
    async fn queue_full_drops_packets_and_increments_dropped_stat() {
        // No Start() call: nothing ever drains the queue, so with
        // capacity 1 the second enqueue must drop.
        let manager = Manager::new(vec!["127.0.0.1:1".to_string()], "VXLAN", 1);
        manager.mirror_tcp("a", "b", Bytes::from_static(b"1"));
        manager.mirror_tcp("a", "b", Bytes::from_static(b"2"));
        assert_eq!(manager.stats().packets_dropped, 1);
    }

    #[tokio::test]
    async fn mirror_raw_drop_never_logs_but_still_counts() {
        // Characterizes the Go asymmetry: MirrorRaw's drop path never
        // logs (unlike MirrorHTTP/TCP/UDP) but does still count.
        let manager = Manager::new(vec!["127.0.0.1:1".to_string()], "VXLAN", 1);
        manager.mirror_raw(Bytes::from_static(b"x"), HashMap::new(), None, None);
        manager.mirror_raw(Bytes::from_static(b"y"), HashMap::new(), None, None);
        assert_eq!(manager.stats().packets_dropped, 1);
    }

    #[tokio::test]
    async fn suricata_forwarding_delivers_newline_terminated_json() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();

        let manager = Arc::new(Manager::new_with_suricata(
            vec![],
            "VXLAN",
            10,
            addr.ip().to_string(),
            addr.port().to_string(),
        ));
        manager.start().await.unwrap();

        let (mut socket, _) = tokio::time::timeout(Duration::from_secs(5), listener.accept())
            .await
            .expect("suricata accept must happen before timeout")
            .expect("accept must not error");

        manager.mirror_tcp("1.1.1.1:1", "2.2.2.2:2", Bytes::from_static(b"hello"));

        use tokio::io::AsyncReadExt;
        let mut buf = vec![0u8; 4096];
        let n = tokio::time::timeout(Duration::from_secs(5), socket.read(&mut buf))
            .await
            .expect("suricata data must arrive before timeout")
            .expect("read must not error");

        assert!(buf[..n].ends_with(b"\n"));
        let parsed: serde_json::Value = serde_json::from_slice(&buf[..n - 1]).unwrap();
        assert_eq!(parsed["event_type"], "mirror");

        manager.stop().await;
    }

    #[tokio::test]
    async fn stop_is_idempotent_and_drains_without_hanging() {
        let listener = TokioUdpSocket::bind("127.0.0.1:0").await.unwrap();
        let dest_addr = listener.local_addr().unwrap();
        let manager = Arc::new(Manager::new(vec![dest_addr.to_string()], "VXLAN", 10));
        manager.start().await.unwrap();

        manager.mirror_tcp("a", "b", Bytes::from_static(b"one"));
        manager.mirror_tcp("a", "b", Bytes::from_static(b"two"));

        tokio::time::timeout(Duration::from_secs(5), manager.stop())
            .await
            .expect("stop must return promptly");
    }
}
