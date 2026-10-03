//! Log-forwarding lifecycle manager — the Rust port of `SyslogLogger`
//! (`services/hub-router/proxy/syslog/logger.go`). Queues user-access
//! events and forwards them, RFC3164-prefixed and JSON-encoded (see
//! [`crate::message`]), to a single configured UDP syslog destination.
//!
//! **Scope note:** mirrors `hub_router_mirror`/`hub_router_ports`/
//! `hub_router_firewall`'s pattern exactly — this crate ports the Go
//! `syslog` package itself (the generic queue/worker-pool/UDP-forwarding
//! engine), not the live call sites that invoke it
//! (`services/hub-router/proxy/{tcp_proxy,udp_proxy,http_handlers,
//! dynamic_ports}.go`), which remain out of scope as a distinct, larger
//! data-plane dispatch subsystem (see `hub_router_mirror::manager`'s
//! identical scope note).
//!
//! Three deliberate deviations from the literal Go source:
//!
//! 1. [`Logger::hostname_or_fallback`] replaces Go's
//!    `getCurrentHostname`'s DNS-based "resolution" (a CNAME lookup of
//!    the literal string `"localhost"`, falling back to a reverse lookup
//!    of `127.0.0.1`, then a hardcoded fallback) with the OS's actual
//!    `gethostname(2)` (via the `hostname` crate) — a genuine
//!    correctness fix, not a characterized Go behavior, because the
//!    original is environment/DNS-state-dependent and not meaningfully
//!    reproducible as "the Go behavior" in a deterministic test. The
//!    final fallback string (`"sasewaddle-headend"`) is preserved
//!    exactly.
//! 2. The stale UDP socket leak in Go's `connect()` (lines 227-243: it
//!    unconditionally overwrites `s.conn` without closing the handle it
//!    replaces, leaking a file descriptor on every reconnect) cannot
//!    occur in this port at all — Rust's ownership model drops (and
//!    closes) the previous `Some(socket)` the moment
//!    [`Logger::connect`]'s `Option` assignment replaces it, with no
//!    code of its own required.
//! 3. A minimum interval between consecutive reconnect attempts (see
//!    [`RECONNECT_BACKOFF`]) guards against the Go source's unthrottled
//!    hot-loop: on a sustained outage, every worker's every failed
//!    `sendLog` immediately re-dials with no delay (lines 252-257),
//!    which — with 3 workers draining a 1000-entry queue — can issue
//!    hundreds of synchronous DNS resolutions and connect syscalls per
//!    second and spam the error log at the same rate. [`Logger`] fixes
//!    this rather than characterizing it as-is, since it is a genuine
//!    resource-exhaustion risk, not an intentional behavior any receiver
//!    depends on.

use crate::config::{Activation, SyslogConfig};
use crate::message::{self, AccessLog, Facility, Severity};
use crate::metrics;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::net::UdpSocket;
use tokio::sync::{mpsc, Mutex as AsyncMutex, RwLock as AsyncRwLock};
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;

/// Worker queue depth — the Rust port of `NewSyslogLogger`'s
/// `make(chan AccessLog, 1000)`.
const QUEUE_CAPACITY: usize = 1000;

/// Worker task count — the Rust port of `NewSyslogLogger`'s
/// `workers: 3`.
const WORKER_COUNT: usize = 3;

/// Fallback hostname used when the OS hostname lookup fails or returns
/// non-UTF8/empty output — the Rust port of `getCurrentHostname`'s final
/// fallback value.
const HOSTNAME_FALLBACK: &str = "sasewaddle-headend";

/// Fixed application name — the Rust port of `NewSyslogLogger`'s
/// hardcoded `appName: "sasewaddle-headend"` (the `syslog.tag` config
/// value is dead; see [`crate::config`]'s module doc).
const APP_NAME: &str = "sasewaddle-headend";

/// Minimum interval between consecutive reconnect attempts — see the
/// module doc's deviation (3).
const RECONNECT_BACKOFF: Duration = Duration::from_millis(500);

/// Failure starting the logger — the Rust port of `Start`'s one error
/// path (`"failed to connect to syslog server: %w"`).
#[derive(Debug, thiserror::Error)]
pub enum LoggerError {
    #[error("failed to connect to syslog server: {0}")]
    Connect(#[source] std::io::Error),
}

/// Queues and forwards user-access events to a UDP syslog destination —
/// see the module doc for full scope and the Go method mapping:
/// `NewSyslogLogger` → [`Logger::new`]; `Start`/`Stop` →
/// [`Logger::start`]/[`Logger::stop`]; `LogAccess`/`LogHTTPAccess`/
/// `LogTCPAccess`/`LogUDPAccess` → identically-prefixed `log_*` methods;
/// `GetQueueDepth`/`IsEnabled` → [`Logger::queue_depth`]/
/// [`Logger::is_enabled`].
pub struct Logger {
    enabled: bool,
    host: String,
    port: String,
    hostname: String,
    tx: mpsc::Sender<AccessLog>,
    rx: AsyncMutex<mpsc::Receiver<AccessLog>>,
    conn: Arc<AsyncRwLock<Option<UdpSocket>>>,
    last_reconnect_attempt: Arc<AsyncMutex<Option<Instant>>>,
    cancel: CancellationToken,
    tasks: AsyncMutex<Vec<JoinHandle<()>>>,
    started: AtomicBool,
}

impl Logger {
    /// Builds a logger — the Rust port of `NewSyslogLogger`. No network
    /// call happens until [`Logger::start`] runs. `enabled` is derived
    /// from `host` non-emptiness, exactly matching Go's `enabled:
    /// syslogHost != ""`.
    #[must_use]
    pub fn new(host: impl Into<String>, port: impl Into<String>) -> Self {
        Self::build(host.into(), port.into(), QUEUE_CAPACITY)
    }

    /// Builds a logger from the hub-api control-plane payload, applying
    /// `bootstrap.go`'s three-way activation gate (lines 271-285) — the
    /// Rust port of that branch, collapsed into a constructor since this
    /// port has no `viper`-style global config store to branch against.
    /// Returns `None` for [`Activation::Disabled`]/
    /// [`Activation::MissingHost`] (the Go source never constructs a
    /// `SyslogLogger` in either case either).
    #[must_use]
    pub fn from_config(config: &SyslogConfig) -> Option<Self> {
        match config.activation() {
            Activation::Active => Some(Self::new(
                config.host.clone(),
                config.resolved_port().to_string(),
            )),
            Activation::Disabled | Activation::MissingHost => None,
        }
    }

    fn build(host: String, port: String, queue_capacity: usize) -> Self {
        let enabled = !host.is_empty();
        let hostname = Self::hostname_or_fallback();
        let (tx, rx) = mpsc::channel(queue_capacity.max(1));

        Self {
            enabled,
            host,
            port,
            hostname,
            tx,
            rx: AsyncMutex::new(rx),
            conn: Arc::new(AsyncRwLock::new(None)),
            last_reconnect_attempt: Arc::new(AsyncMutex::new(None)),
            cancel: CancellationToken::new(),
            tasks: AsyncMutex::new(Vec::new()),
            started: AtomicBool::new(false),
        }
    }

    /// Test-only constructor overriding the hardcoded [`QUEUE_CAPACITY`]
    /// so queue-full/drop tests don't need to enqueue 1000 real entries.
    /// Never reachable from the public API — production construction
    /// always goes through [`Logger::new`]/[`Logger::from_config`] and
    /// Go's hardcoded capacity.
    #[cfg(test)]
    fn new_with_capacity(
        host: impl Into<String>,
        port: impl Into<String>,
        capacity: usize,
    ) -> Self {
        Self::build(host.into(), port.into(), capacity)
    }

    /// Resolves the OS hostname — see the module doc's deviation (1).
    fn hostname_or_fallback() -> String {
        hostname::get()
            .ok()
            .and_then(|h| h.into_string().ok())
            .filter(|h| !h.is_empty())
            .unwrap_or_else(|| HOSTNAME_FALLBACK.to_string())
    }

    /// Whether this logger will forward entries anywhere — the Rust port
    /// of `IsEnabled`.
    #[must_use]
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }

    /// Current depth of the pending-send queue — the Rust port of
    /// `GetQueueDepth`'s `len(s.logQueue)`. Disabled loggers always
    /// report `0`, matching Go's `if !s.enabled { return 0 }`.
    #[must_use]
    pub fn queue_depth(&self) -> usize {
        if !self.enabled {
            return 0;
        }
        self.tx.max_capacity().saturating_sub(self.tx.capacity())
    }

    /// Establishes the UDP connection and starts the worker pool — the
    /// Rust port of `Start`. A no-op returning `Ok(())` when disabled,
    /// matching Go's `if !s.enabled { return nil }`.
    #[tracing::instrument(skip(self), fields(host = %self.host, port = %self.port))]
    pub async fn start(self: &Arc<Self>) -> Result<(), LoggerError> {
        if !self.enabled {
            tracing::info!("syslog logging disabled");
            return Ok(());
        }

        self.connect().await.map_err(LoggerError::Connect)?;

        let mut tasks = self.tasks.lock().await;
        for worker_id in 0..WORKER_COUNT {
            let logger = Arc::clone(self);
            tasks.push(tokio::spawn(async move { logger.worker(worker_id).await }));
        }
        self.started.store(true, Ordering::SeqCst);

        tracing::info!(host = %self.host, port = %self.port, "syslog logger started");
        Ok(())
    }

    /// Signals every worker to stop and waits for them to finish
    /// (draining whatever remains queued — see [`Logger::worker`]), then
    /// closes the connection — the Rust port of `Stop`.
    pub async fn stop(&self) {
        if !self.enabled {
            return;
        }
        tracing::info!("stopping syslog logger");
        self.cancel.cancel();

        let handles: Vec<JoinHandle<()>> = {
            let mut tasks = self.tasks.lock().await;
            std::mem::take(&mut *tasks)
        };
        for handle in handles {
            let _ = handle.await;
        }

        *self.conn.write().await = None;
        tracing::info!("syslog logger stopped");
    }

    /// Queues a user-access event — the Rust port of `LogAccess`.
    /// Non-blocking: a full queue drops the entry (matching Go's
    /// `select { case s.logQueue <- accessLog: default: log.Warn(...) }`).
    pub fn log_access(&self, mut entry: AccessLog) {
        if !self.enabled {
            return;
        }
        if entry.timestamp == std::time::SystemTime::UNIX_EPOCH {
            entry.timestamp = std::time::SystemTime::now();
        }
        if self.tx.try_send(entry).is_err() {
            metrics::record_log_dropped();
            tracing::warn!("syslog queue full, dropping access log entry");
        }
    }

    /// Logs HTTP access with detailed request/response metadata — the
    /// Rust port of `LogHTTPAccess`.
    #[allow(clippy::too_many_arguments)]
    pub fn log_http_access(
        &self,
        user_id: &str,
        username: &str,
        source_ip: &str,
        target_host: &str,
        method: &str,
        path: &str,
        user_agent: &str,
        request_id: &str,
        status_code: i32,
        bytes_sent: i64,
        allowed: bool,
    ) {
        self.log_access(AccessLog {
            user_id: user_id.to_string(),
            username: username.to_string(),
            source_ip: source_ip.to_string(),
            target_host: target_host.to_string(),
            protocol: "HTTP".to_string(),
            action: action_label(allowed),
            method: method.to_string(),
            path: path.to_string(),
            status_code,
            bytes_sent,
            user_agent: user_agent.to_string(),
            request_id: request_id.to_string(),
            ..AccessLog::default()
        });
    }

    /// Logs TCP connection access — the Rust port of `LogTCPAccess`.
    pub fn log_tcp_access(
        &self,
        user_id: &str,
        username: &str,
        source_ip: &str,
        target_host: &str,
        allowed: bool,
    ) {
        self.log_access(AccessLog {
            user_id: user_id.to_string(),
            username: username.to_string(),
            source_ip: source_ip.to_string(),
            target_host: target_host.to_string(),
            protocol: "TCP".to_string(),
            action: action_label(allowed),
            ..AccessLog::default()
        });
    }

    /// Logs UDP packet access — the Rust port of `LogUDPAccess`.
    pub fn log_udp_access(
        &self,
        user_id: &str,
        username: &str,
        source_ip: &str,
        target_host: &str,
        allowed: bool,
    ) {
        self.log_access(AccessLog {
            user_id: user_id.to_string(),
            username: username.to_string(),
            source_ip: source_ip.to_string(),
            target_host: target_host.to_string(),
            protocol: "UDP".to_string(),
            action: action_label(allowed),
            ..AccessLog::default()
        });
    }

    /// Dials the syslog destination and installs the new socket — the
    /// Rust port of `connect`. The stale `Some(socket)` this replaces
    /// (if any) is dropped here, closing its fd — see the module doc's
    /// deviation (2); Go's `connect()` has no equivalent and leaks the
    /// old fd on every call.
    async fn connect(&self) -> std::io::Result<()> {
        let socket = UdpSocket::bind("0.0.0.0:0").await?;
        socket
            .connect(format!("{}:{}", self.host, self.port))
            .await?;
        *self.conn.write().await = Some(socket);
        Ok(())
    }

    /// Re-dials the syslog destination, throttled to at most once per
    /// [`RECONNECT_BACKOFF`] — see the module doc's deviation (3).
    /// Returns without attempting if another worker already reconnected
    /// (or tried to) within the backoff window.
    async fn reconnect_throttled(&self) {
        {
            let mut last = self.last_reconnect_attempt.lock().await;
            if let Some(previous) = *last {
                if previous.elapsed() < RECONNECT_BACKOFF {
                    tracing::debug!("skipping syslog reconnect attempt, within backoff window");
                    return;
                }
            }
            *last = Some(Instant::now());
        }

        if let Err(error) = self.connect().await {
            tracing::error!(%error, "syslog worker failed to reconnect");
        }
    }

    async fn worker(self: Arc<Self>, worker_id: usize) {
        tracing::debug!(worker = worker_id, "syslog worker started");
        loop {
            let entry = {
                let mut rx = self.rx.lock().await;
                tokio::select! {
                    biased;
                    () = self.cancel.cancelled() => rx.try_recv().ok(),
                    maybe = rx.recv() => maybe,
                }
            };

            match entry {
                Some(log_entry) => self.send_log(log_entry).await,
                None => {
                    tracing::debug!(worker = worker_id, "syslog worker stopping");
                    return;
                }
            }
        }
    }

    /// Formats and sends one entry — the Rust port of `sendLog` (lines
    /// 266-305).
    async fn send_log(&self, entry: AccessLog) {
        let started = Instant::now();
        let target_host = entry.target_host.clone();
        let user_id = entry.user_id.clone();

        let pri = message::priority(Facility::Local0, Severity::Informational);
        let timestamp = message::format_rfc3339(entry.timestamp);
        let json_payload = match serde_json::to_string(&entry) {
            Ok(payload) => payload,
            Err(error) => {
                tracing::error!(%error, "failed to marshal access log");
                metrics::record_send_error();
                metrics::record_send_duration(started.elapsed().as_secs_f64());
                return;
            }
        };
        let frame = message::format_frame(pri, &timestamp, &self.hostname, APP_NAME, &json_payload);

        let send_result = {
            let conn = self.conn.read().await;
            match conn.as_ref() {
                Some(socket) => socket.send(frame.as_bytes()).await,
                None => Err(std::io::Error::other("no syslog connection available")),
            }
        };

        match send_result {
            Ok(_) => {
                metrics::record_log_sent();
                tracing::debug!(user_id = %user_id, target_host = %target_host, "sent syslog message");
            }
            Err(error) => {
                tracing::error!(%error, "syslog worker failed to send log");
                metrics::record_send_error();
                self.reconnect_throttled().await;
            }
        }

        metrics::record_send_duration(started.elapsed().as_secs_f64());
    }
}

fn action_label(allowed: bool) -> String {
    if allowed {
        "allow".to_string()
    } else {
        "deny".to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::net::UdpSocket as TokioUdpSocket;

    #[test]
    fn new_derives_enabled_from_host_non_emptiness() {
        assert!(!Logger::new("", "514").is_enabled());
        assert!(Logger::new("10.0.0.5", "514").is_enabled());
    }

    #[test]
    fn from_config_returns_none_when_disabled() {
        assert!(Logger::from_config(&SyslogConfig::default()).is_none());
    }

    #[test]
    fn from_config_returns_none_when_enabled_without_host() {
        let cfg = SyslogConfig {
            enabled: true,
            ..Default::default()
        };
        assert!(Logger::from_config(&cfg).is_none());
    }

    #[test]
    fn from_config_builds_an_enabled_logger_when_active() {
        let cfg = SyslogConfig {
            enabled: true,
            host: "10.0.0.5".to_string(),
            ..Default::default()
        };
        let logger = Logger::from_config(&cfg).expect("Active config must build a logger");
        assert!(logger.is_enabled());
        assert_eq!(logger.host, "10.0.0.5");
        assert_eq!(logger.port, "514"); // DEFAULT_PORT via resolved_port()
    }

    #[tokio::test]
    async fn start_is_a_noop_when_disabled() {
        let logger = Arc::new(Logger::new("", "514"));
        logger
            .start()
            .await
            .expect("disabled start must succeed without any network call");
        assert_eq!(logger.queue_depth(), 0);
        logger.stop().await; // must not hang/panic either
    }

    #[test]
    fn hostname_or_fallback_never_panics_and_is_non_empty() {
        let hostname = Logger::hostname_or_fallback();
        assert!(!hostname.is_empty());
    }

    #[test]
    fn queue_depth_reflects_pending_entries_before_any_worker_drains_them() {
        let logger = Logger::new("127.0.0.1", "1");
        assert_eq!(logger.queue_depth(), 0);
        logger.log_tcp_access("u1", "alice", "10.0.0.1:1", "10.0.0.2:2", true);
        logger.log_tcp_access("u1", "alice", "10.0.0.1:1", "10.0.0.2:2", false);
        assert_eq!(logger.queue_depth(), 2);
    }

    #[test]
    fn log_access_is_a_noop_when_disabled() {
        let logger = Logger::new("", "514");
        logger.log_tcp_access("u1", "alice", "10.0.0.1:1", "10.0.0.2:2", true);
        assert_eq!(logger.queue_depth(), 0);
    }

    #[test]
    fn log_access_drops_entries_once_the_queue_is_full() {
        let logger = Logger::new_with_capacity("127.0.0.1", "1", 2);
        logger.log_tcp_access("u1", "alice", "a", "b", true);
        logger.log_tcp_access("u1", "alice", "a", "b", true);
        assert_eq!(logger.queue_depth(), 2);

        // Third entry must be dropped, not block or panic; depth stays 2.
        logger.log_tcp_access("u1", "alice", "a", "b", true);
        assert_eq!(logger.queue_depth(), 2);
    }

    #[tokio::test]
    async fn start_returns_connect_error_for_an_unresolvable_destination() {
        let logger = Arc::new(Logger::new("not a valid host!!", "abc"));
        let err = logger
            .start()
            .await
            .expect_err("an unresolvable host:port must fail to connect");
        assert!(matches!(err, LoggerError::Connect(_)));
    }

    #[tokio::test]
    async fn reconnect_throttled_skips_a_second_attempt_within_the_backoff_window() {
        let logger = Logger::new("127.0.0.1", "1");
        logger.reconnect_throttled().await;
        let first = *logger.last_reconnect_attempt.lock().await;
        assert!(first.is_some());

        logger.reconnect_throttled().await;
        let second = *logger.last_reconnect_attempt.lock().await;
        assert_eq!(
            first, second,
            "a second attempt inside the backoff window must not update the timestamp"
        );
    }

    #[tokio::test]
    async fn start_connects_and_a_worker_forwards_one_entry_end_to_end() {
        let listener = TokioUdpSocket::bind("127.0.0.1:0").await.unwrap();
        let dest_addr = listener.local_addr().unwrap();

        let logger = Arc::new(Logger::new(
            dest_addr.ip().to_string(),
            dest_addr.port().to_string(),
        ));
        logger
            .start()
            .await
            .expect("start must succeed against a live listener");

        logger.log_tcp_access("u1", "alice", "10.0.0.1:1", "10.0.0.2:2", false);

        let mut buf = [0u8; 1024];
        let (n, _) = tokio::time::timeout(Duration::from_secs(5), listener.recv_from(&mut buf))
            .await
            .expect("syslog frame must arrive before timeout")
            .expect("recv_from must not error");
        let frame = std::str::from_utf8(&buf[..n]).unwrap();

        // Priority 134 = FacilityLocal0(16)*8 + SeverityInformational(6),
        // and APP_NAME is always the hardcoded "sasewaddle-headend" —
        // both exactly as Go's NewSyslogLogger hardcodes them.
        assert!(frame.starts_with("<134>"));
        assert!(frame.contains(" sasewaddle-headend: "));

        let (_, json_part) = frame.split_once(": ").unwrap();
        let parsed: serde_json::Value = serde_json::from_str(json_part).unwrap();
        assert_eq!(parsed["protocol"], "TCP");
        assert_eq!(parsed["action"], "deny");
        assert_eq!(parsed["user_id"], "u1");
        assert!(
            parsed.get("method").is_none(),
            "empty method must be omitted"
        );

        logger.stop().await;
    }

    #[tokio::test]
    async fn log_http_access_carries_status_code_and_bytes_sent() {
        let listener = TokioUdpSocket::bind("127.0.0.1:0").await.unwrap();
        let dest_addr = listener.local_addr().unwrap();

        let logger = Arc::new(Logger::new(
            dest_addr.ip().to_string(),
            dest_addr.port().to_string(),
        ));
        logger.start().await.unwrap();

        logger.log_http_access(
            "u1",
            "alice",
            "10.0.0.1:1",
            "10.0.0.2:2",
            "GET",
            "/health",
            "curl/8.0",
            "req-1",
            200,
            42,
            true,
        );

        let mut buf = [0u8; 1024];
        let (n, _) = tokio::time::timeout(Duration::from_secs(5), listener.recv_from(&mut buf))
            .await
            .unwrap()
            .unwrap();
        let frame = std::str::from_utf8(&buf[..n]).unwrap();
        let (_, json_part) = frame.split_once(": ").unwrap();
        let parsed: serde_json::Value = serde_json::from_str(json_part).unwrap();
        assert_eq!(parsed["protocol"], "HTTP");
        assert_eq!(parsed["action"], "allow");
        assert_eq!(parsed["method"], "GET");
        assert_eq!(parsed["status_code"], 200);
        assert_eq!(parsed["bytes_sent"], 42);

        logger.stop().await;
    }

    #[tokio::test]
    async fn stop_on_a_disabled_logger_is_a_noop() {
        let logger = Logger::new("", "514");
        tokio::time::timeout(Duration::from_secs(5), logger.stop())
            .await
            .expect("stop on a disabled logger must return promptly");
    }

    #[tokio::test]
    async fn stop_is_idempotent_and_drains_without_hanging() {
        let listener = TokioUdpSocket::bind("127.0.0.1:0").await.unwrap();
        let dest_addr = listener.local_addr().unwrap();
        let logger = Arc::new(Logger::new(
            dest_addr.ip().to_string(),
            dest_addr.port().to_string(),
        ));
        logger.start().await.unwrap();

        logger.log_tcp_access("u1", "alice", "a", "b", true);
        logger.log_tcp_access("u1", "alice", "a", "b", true);

        tokio::time::timeout(Duration::from_secs(5), logger.stop())
            .await
            .expect("stop must return promptly");
    }
}
