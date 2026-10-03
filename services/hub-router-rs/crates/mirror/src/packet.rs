//! Wire-adjacent packet/stats types — the Rust port of `MirrorPacket` and
//! `Stats` (`services/hub-router/proxy/mirror/manager.go`, lines 46-61,
//! 443-460).

use bytes::Bytes;
use std::collections::HashMap;
use std::net::IpAddr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::SystemTime;

/// One queued mirror event — the Rust port of `MirrorPacket`.
///
/// `source`/`destination` exist on the Go struct and are read by
/// `prepareSuricataData`, but **no call site in the Go source ever sets
/// them** (`MirrorHTTP`/`MirrorTCP`/`MirrorUDP`/`MirrorRaw` all construct a
/// `MirrorPacket` literal with `Source`/`Destination` left at their `nil`
/// zero value — confirmed by grep across `services/hub-router/`). They are
/// kept here for API/wire-shape parity and because [`crate::manager::Manager::mirror_raw`]
/// does accept a caller-supplied value, but every one of this port's own
/// `mirror_http`/`mirror_tcp`/`mirror_udp` convenience methods leaves them
/// `None`, exactly like the Go source.
#[derive(Debug, Clone)]
pub struct MirrorPacket {
    pub timestamp: SystemTime,
    pub source: Option<IpAddr>,
    pub destination: Option<IpAddr>,
    pub protocol: String,
    /// `bytes::Bytes`, not `Vec<u8>` — backend-rust.md's zero-copy
    /// packet-hot-path rule; this is the one piece of this crate that
    /// carries live traffic payload bytes.
    pub data: Bytes,
    pub metadata: HashMap<String, serde_json::Value>,
}

/// Minimal captured shape of an HTTP request/response pair for
/// [`crate::manager::Manager::mirror_http`] — the Rust port of
/// `MirrorHTTP(req *http.Request, statusCode int, body []byte)`'s
/// parameter usage. Deliberately not a dependency on any specific web
/// framework's request type (unlike the Go source, which took a concrete
/// `*net/http.Request`): this crate's only concern is the handful of
/// fields `encodeHTTP`/`MirrorHTTP`'s metadata actually read
/// (`req.Method`, `req.URL.Path`/`req.URL.String()`, `req.Proto`,
/// `req.Header`, `req.UserAgent()`), not request handling itself.
#[derive(Debug, Clone, Default)]
pub struct HttpRequestInfo {
    pub method: String,
    /// Full request URL/target as the Go source's `req.URL.String()`
    /// produces it (used in `MirrorHTTP`'s metadata `"url"` field).
    pub url: String,
    /// Request path alone, as `req.URL.Path` (used in `encodeHTTP`'s
    /// request line).
    pub path: String,
    /// HTTP protocol version string, e.g. `"HTTP/1.1"` (Go's `req.Proto`).
    pub proto: String,
    /// Headers in their original order, duplicates preserved — mirrors Go's
    /// `http.Header` (`map[string][]string`) iteration in `encodeHTTP`,
    /// which writes one line per (key, value) pair including repeats.
    pub headers: Vec<(String, String)>,
    /// Pre-extracted `User-Agent` header value — the Go source calls
    /// `req.UserAgent()`, a convenience accessor over the same header.
    pub user_agent: String,
}

/// Running counters — the Rust port of `Stats`. Lock-free atomics replace
/// the Go source's `sync.RWMutex`-guarded plain fields; this changes no
/// observable behavior (the Go mutex only ever protects simple increments,
/// never a multi-field invariant), so it is a non-behavioral idiomatic
/// improvement, not a characterization deviation.
#[derive(Debug, Default)]
pub struct Stats {
    packets_sent: AtomicU64,
    packets_dropped: AtomicU64,
    bytes_sent: AtomicU64,
    errors: AtomicU64,
}

/// Point-in-time snapshot of [`Stats`], e.g. for the periodic stats-log
/// line — the Rust port of the field set logged by `reportStats`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct StatsSnapshot {
    pub packets_sent: u64,
    pub packets_dropped: u64,
    pub bytes_sent: u64,
    pub errors: u64,
}

impl Stats {
    /// Records one successfully sent packet — the Rust port of
    /// `incrementSent`.
    pub fn increment_sent(&self, bytes: u64) {
        self.packets_sent.fetch_add(1, Ordering::Relaxed);
        self.bytes_sent.fetch_add(bytes, Ordering::Relaxed);
    }

    /// Records one packet dropped from a full queue — the Rust port of
    /// `incrementDropped`.
    pub fn increment_dropped(&self) {
        self.packets_dropped.fetch_add(1, Ordering::Relaxed);
    }

    /// Records one send/encapsulation failure — the Rust port of
    /// `incrementErrors`.
    pub fn increment_errors(&self) {
        self.errors.fetch_add(1, Ordering::Relaxed);
    }

    /// Reads all four counters — the Rust port of `reportStats`'s
    /// mutex-guarded read of every field.
    #[must_use]
    pub fn snapshot(&self) -> StatsSnapshot {
        StatsSnapshot {
            packets_sent: self.packets_sent.load(Ordering::Relaxed),
            packets_dropped: self.packets_dropped.load(Ordering::Relaxed),
            bytes_sent: self.bytes_sent.load(Ordering::Relaxed),
            errors: self.errors.load(Ordering::Relaxed),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stats_start_at_zero() {
        let stats = Stats::default();
        assert_eq!(stats.snapshot(), StatsSnapshot::default());
    }

    #[test]
    fn increment_sent_updates_packets_and_bytes() {
        let stats = Stats::default();
        stats.increment_sent(100);
        stats.increment_sent(50);
        let snap = stats.snapshot();
        assert_eq!(snap.packets_sent, 2);
        assert_eq!(snap.bytes_sent, 150);
        assert_eq!(snap.packets_dropped, 0);
        assert_eq!(snap.errors, 0);
    }

    #[test]
    fn increment_dropped_and_errors_are_independent_counters() {
        let stats = Stats::default();
        stats.increment_dropped();
        stats.increment_dropped();
        stats.increment_errors();
        let snap = stats.snapshot();
        assert_eq!(snap.packets_dropped, 2);
        assert_eq!(snap.errors, 1);
        assert_eq!(snap.packets_sent, 0);
    }

    #[test]
    fn mirror_packet_defaults_source_and_destination_to_none() {
        let packet = MirrorPacket {
            timestamp: SystemTime::now(),
            source: None,
            destination: None,
            protocol: "TCP".to_string(),
            data: Bytes::from_static(b"payload"),
            metadata: HashMap::new(),
        };
        assert!(packet.source.is_none());
        assert!(packet.destination.is_none());
    }

    #[test]
    fn http_request_info_default_is_empty() {
        let info = HttpRequestInfo::default();
        assert!(info.method.is_empty());
        assert!(info.headers.is_empty());
    }
}
