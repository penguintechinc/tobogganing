//! Port of `engines/testserver/internal/validation/validation.go` — the
//! request-input allowlists and sanitizers every REST/gRPC handler runs
//! before dispatching to `testserver-protocols`. Field names, limits, and
//! whitelist values are copied 1:1 from the Go source (this is the
//! behavioral parity contract, not a redesign).

use crate::error::ApiError;
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};
use std::sync::LazyLock;

pub const MAX_TARGET_LENGTH: usize = 255;
pub const MAX_QUERY_LENGTH: usize = 255;
pub const MAX_TIMEOUT_SECONDS: i64 = 300; // 5 minutes max
pub const MAX_COUNT: i64 = 1000;
pub const MIN_PORT: i64 = 1;
pub const MAX_PORT: i64 = 65535;
pub const MAX_PROTOCOL_LENGTH: usize = 50;
pub const MAX_METHOD_LENGTH: usize = 10;

const VALID_HTTP_PROTOCOLS: &[&str] = &[
    "http1", "http/1.1", "http1.1", "http2", "http/2", "http3", "http/3", "HTTP/1.1", "HTTP/2",
    "HTTP/3",
];
const VALID_TCP_PROTOCOLS: &[&str] = &[
    "raw", "raw_tcp", "Raw TCP", "tcp", "tls", "TLS", "ssh", "SSH",
];
const VALID_UDP_PROTOCOLS: &[&str] = &["raw", "raw_udp", "Raw UDP", "udp", "dns", "DNS"];
const VALID_ICMP_PROTOCOLS: &[&str] = &["ping", "traceroute"];
const VALID_HTTP_METHODS: &[&str] = &["GET", "POST", "HEAD", "OPTIONS"];

static HOSTNAME_RE: LazyLock<regex::Regex> = LazyLock::new(|| {
    regex::Regex::new(
        r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$",
    )
    .expect("HOSTNAME_RE is a fixed, compile-time-verified pattern")
});

static DOMAIN_RE: LazyLock<regex::Regex> = LazyLock::new(|| {
    regex::Regex::new(
        r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.?$",
    )
    .expect("DOMAIN_RE is a fixed, compile-time-verified pattern")
});

/// Returns true if `ip` lands in a range this service must never let a
/// caller-supplied probe target reach: loopback (`127.0.0.0/8`, `::1`),
/// link-local (`169.254.0.0/16` — this is also the cloud-metadata range,
/// `169.254.169.254`; `fe80::/10`), IPv6 unique-local (`fc00::/7`), and
/// unspecified (`0.0.0.0`, `::`). This is the authoritative SSRF guard —
/// it supersedes the Go original's string-prefix denylist, which only
/// matched a subset of these and (per
/// `validate_target_ip_literal_denylist_is_dead_code_parity_with_go`) never
/// actually ran against IP-literal input.
///
/// Deliberate divergence from Go parity: the Go source explicitly *allows*
/// loopback/`localhost` ("permitted... intentional to support testing
/// against local services" per its own comment) — this port tightens that
/// policy per a security review, since a probe server that lets an
/// authenticated-but-untrusted caller direct traffic at `127.0.0.1:<port>`
/// can be used to reach loopback-only-bound services the caller has no
/// other path to. RFC1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`,
/// `192.168.0.0/16`) remain allowed, matching the Go policy — internal
/// connectivity testing is this service's entire purpose.
fn is_blocked_ip(ip: &IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => is_blocked_ipv4(*v4),
        IpAddr::V6(v6) => {
            if let Some(mapped) = v6.to_ipv4_mapped() {
                return is_blocked_ipv4(mapped);
            }
            v6.is_loopback()
                || v6.is_unspecified()
                || is_link_local_v6(*v6)
                || is_unique_local_v6(*v6)
        }
    }
}

fn is_blocked_ipv4(v4: Ipv4Addr) -> bool {
    v4.is_loopback() || v4.is_unspecified() || is_link_local_v4(v4)
}

fn is_link_local_v4(ip: Ipv4Addr) -> bool {
    let o = ip.octets();
    o[0] == 169 && o[1] == 254
}

fn is_link_local_v6(ip: Ipv6Addr) -> bool {
    (ip.segments()[0] & 0xffc0) == 0xfe80
}

fn is_unique_local_v6(ip: Ipv6Addr) -> bool {
    (ip.segments()[0] & 0xfe00) == 0xfc00
}

const SSRF_DENY_MESSAGE: &str =
    "access to loopback, link-local, cloud-metadata, or unspecified addresses is prohibited";

/// Validates a target hostname or IP address. Ported from Go's
/// `ValidateTarget`, with SSRF hardening layered on top (see
/// `is_blocked_ip`'s doc comment for the parity/divergence rationale):
///
/// 1. An IP-literal target is checked against the block-list directly —
///    this fixes the Go original's dead-code bug where `net.ParseIP`
///    short-circuited *before* its own denylist check ever ran.
/// 2. A hostname target is resolved via DNS and *every* resolved address
///    is checked against the block-list (anti-DNS-rebind: a hostname that
///    resolves to a blocked address is rejected even though the hostname
///    string itself looks benign). This closes the validation-time gap but
///    does not by itself guarantee the later probe connects to the exact
///    address validated here — `testserver-protocols` re-resolves
///    independently at connect time, so full TOCTOU closure requires
///    pinning the resolved address through to the connect call, tracked as
///    a further hardening follow-up.
///
/// RFC1918 private ranges (`10.x`, `172.16-31.x`, `192.168.x`) stay
/// allowed, matching the Go policy.
pub async fn validate_target(target: &str) -> Result<(), ApiError> {
    if target.is_empty() {
        return Err(ApiError::validation("target", "target cannot be empty"));
    }
    if target.len() > MAX_TARGET_LENGTH {
        return Err(ApiError::validation(
            "target",
            format!("target exceeds maximum length of {MAX_TARGET_LENGTH}"),
        ));
    }

    // Remove URL scheme if present for validation.
    let clean_target = if target.contains("://") {
        let parsed = url::Url::parse(target)
            .map_err(|_| ApiError::validation("target", "invalid URL format"))?;
        parsed.host_str().unwrap_or("").to_string()
    } else {
        target.to_string()
    };

    // Remove port if present (naive rsplit on ':', matching the Go
    // implementation's net.SplitHostPort-with-fallback behavior; neither
    // implementation is fully IPv6-bracket-aware).
    let host = if clean_target.contains(':') {
        clean_target
            .rsplit_once(':')
            .map(|(h, _)| h.to_string())
            .unwrap_or(clean_target.clone())
    } else {
        clean_target.clone()
    };

    // IP-literal target: check the block-list directly (see is_blocked_ip).
    if let Ok(ip) = host.parse::<IpAddr>() {
        if is_blocked_ip(&ip) {
            return Err(ApiError::validation("target", SSRF_DENY_MESSAGE));
        }
        return Ok(());
    }

    if !HOSTNAME_RE.is_match(&host) {
        return Err(ApiError::validation("target", "invalid hostname format"));
    }

    // Anti-DNS-rebind: resolve the hostname and reject if ANY resolved
    // address lands in a blocked range — this is what actually matters for
    // hostnames like a spoofed "metadata.internal" pointed at
    // 169.254.169.254; the string-based checks above can't catch it since
    // the hostname text itself never contains the IP. A resolution failure
    // is not treated as invalid input (transient DNS issues shouldn't block
    // validation) — the probe itself will surface a clear connect error.
    if let Ok(addrs) = tokio::net::lookup_host((host.as_str(), 0)).await {
        for addr in addrs {
            if is_blocked_ip(&addr.ip()) {
                return Err(ApiError::validation(
                    "target",
                    "target hostname resolves to a prohibited address",
                ));
            }
        }
    }

    Ok(())
}

/// Validates a DNS query string (optional field — empty is allowed).
pub fn validate_dns_query(query: &str) -> Result<(), ApiError> {
    if query.is_empty() {
        return Ok(());
    }
    if query.len() > MAX_QUERY_LENGTH {
        return Err(ApiError::validation(
            "query",
            format!("query exceeds maximum length of {MAX_QUERY_LENGTH}"),
        ));
    }
    if !DOMAIN_RE.is_match(query) {
        return Err(ApiError::validation("query", "invalid domain name format"));
    }
    Ok(())
}

pub fn validate_port(port: i64) -> Result<(), ApiError> {
    if !(MIN_PORT..=MAX_PORT).contains(&port) {
        return Err(ApiError::validation(
            "port",
            format!("port must be between {MIN_PORT} and {MAX_PORT}"),
        ));
    }
    Ok(())
}

pub fn validate_timeout(timeout: i64) -> Result<(), ApiError> {
    if timeout < 1 {
        return Err(ApiError::validation(
            "timeout",
            "timeout must be at least 1 second",
        ));
    }
    if timeout > MAX_TIMEOUT_SECONDS {
        return Err(ApiError::validation(
            "timeout",
            format!("timeout cannot exceed {MAX_TIMEOUT_SECONDS} seconds"),
        ));
    }
    Ok(())
}

pub fn validate_count(count: i64) -> Result<(), ApiError> {
    if count < 1 {
        return Err(ApiError::validation("count", "count must be at least 1"));
    }
    if count > MAX_COUNT {
        return Err(ApiError::validation(
            "count",
            format!("count cannot exceed {MAX_COUNT}"),
        ));
    }
    Ok(())
}

fn validate_against_whitelist(
    field: &'static str,
    label: &'static str,
    value: &str,
    whitelist: &[&str],
) -> Result<(), ApiError> {
    if value.is_empty() {
        return Ok(()); // Will use default.
    }
    if value.len() > MAX_PROTOCOL_LENGTH {
        return Err(ApiError::validation(
            field,
            format!("{label} string too long"),
        ));
    }
    if !whitelist.contains(&value) {
        return Err(ApiError::validation(field, format!("invalid {label}")));
    }
    Ok(())
}

pub fn validate_http_protocol(protocol: &str) -> Result<(), ApiError> {
    validate_against_whitelist("protocol", "HTTP protocol", protocol, VALID_HTTP_PROTOCOLS)
}

pub fn validate_tcp_protocol(protocol: &str) -> Result<(), ApiError> {
    validate_against_whitelist("protocol", "TCP protocol", protocol, VALID_TCP_PROTOCOLS)
}

pub fn validate_udp_protocol(protocol: &str) -> Result<(), ApiError> {
    validate_against_whitelist("protocol", "UDP protocol", protocol, VALID_UDP_PROTOCOLS)
}

pub fn validate_icmp_protocol(protocol: &str) -> Result<(), ApiError> {
    validate_against_whitelist("protocol", "ICMP protocol", protocol, VALID_ICMP_PROTOCOLS)
}

pub fn validate_http_method(method: &str) -> Result<(), ApiError> {
    if method.is_empty() {
        return Ok(());
    }
    if method.len() > MAX_METHOD_LENGTH {
        return Err(ApiError::validation("method", "method string too long"));
    }
    if !VALID_HTTP_METHODS.contains(&method) {
        return Err(ApiError::validation("method", "invalid HTTP method"));
    }
    Ok(())
}

/// Trims whitespace, truncates to `max_length`, and strips control
/// characters (except tab/CR/LF) — ported from Go's `SanitizeString`.
pub fn sanitize_string(input: &str, max_length: usize) -> String {
    let trimmed = input.trim();
    let truncated: String = trimmed.chars().take(max_length).collect();
    truncated
        .chars()
        .filter(|&c| (c as u32) >= 32 || c == '\t' || c == '\n' || c == '\r')
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn validate_target_rejects_empty() {
        assert!(validate_target("").await.is_err());
    }

    #[tokio::test]
    async fn validate_target_accepts_ipv4() {
        assert!(validate_target("192.168.1.1").await.is_ok());
        assert!(validate_target("8.8.8.8").await.is_ok());
    }

    #[tokio::test]
    async fn validate_target_rejects_bare_ipv6_parity_with_go() {
        // Parity quirk documented directly in the Go test
        // (validation_test.go: "bare IPv6 addresses like ::1 are not
        // supported by ValidateTarget because the colon detection sends it
        // into net.SplitHostPort which requires a port") — colon-based
        // port-stripping misparses an unbracketed IPv6 literal into a
        // non-IP, non-hostname string, so it's rejected in both languages.
        assert!(validate_target("::1").await.is_err());
    }

    #[tokio::test]
    async fn validate_target_accepts_rfc1918_private_ranges() {
        // Intentional permissiveness, matches Go — internal connectivity
        // testing is this service's entire purpose.
        assert!(validate_target("10.0.0.5").await.is_ok());
        assert!(validate_target("192.168.1.1").await.is_ok());
        assert!(validate_target("172.16.0.5").await.is_ok());
    }

    #[tokio::test]
    async fn validate_target_rejects_loopback_ip_literal_ssrf_hardening() {
        // Security-review divergence from Go (which explicitly *allows*
        // loopback/localhost) — see is_blocked_ip's doc comment. A probe
        // server letting a caller reach 127.0.0.1:<port> can pivot to
        // loopback-only-bound services with no other path to them.
        assert!(validate_target("127.0.0.1").await.is_err());
        assert!(validate_target("127.0.0.53").await.is_err());
    }

    #[tokio::test]
    async fn validate_target_rejects_unspecified_ip_literal() {
        assert!(validate_target("0.0.0.0").await.is_err());
    }

    #[tokio::test]
    async fn validate_target_rejects_link_local_and_cloud_metadata_ip_literal() {
        assert!(validate_target("169.254.1.1").await.is_err());
        // The AWS/GCP/Azure cloud-metadata endpoint — the canonical SSRF
        // pivot this guard exists to close.
        assert!(validate_target("169.254.169.254").await.is_err());
    }

    #[test]
    fn is_blocked_ip_covers_ipv6_loopback_link_local_and_unique_local() {
        assert!(is_blocked_ip(&"::1".parse().unwrap()));
        assert!(is_blocked_ip(&"fe80::1".parse().unwrap()));
        assert!(is_blocked_ip(&"fc00::1".parse().unwrap()));
        assert!(is_blocked_ip(&"::".parse().unwrap()));
        assert!(!is_blocked_ip(&"2001:db8::1".parse().unwrap()));
    }

    #[test]
    fn is_blocked_ip_covers_ipv4_mapped_ipv6() {
        // ::ffff:127.0.0.1 — an IPv4-mapped IPv6 loopback, a classic SSRF
        // filter-bypass trick if the mapped form isn't unwrapped first.
        assert!(is_blocked_ip(&"::ffff:127.0.0.1".parse().unwrap()));
        assert!(is_blocked_ip(&"::ffff:169.254.169.254".parse().unwrap()));
    }

    #[tokio::test]
    async fn validate_target_anti_rebind_rejects_hostname_resolving_to_loopback() {
        // "localhost" is a hostname (not an IP literal), so it takes the
        // DNS-resolution branch — this is the anti-rebind regression test:
        // a hostname that LOOKS benign but resolves to a blocked address
        // must still be rejected. Deliberately diverges from Go's explicit
        // "localhost allowed" test case, per the security review.
        assert!(validate_target("localhost").await.is_err());
    }

    #[tokio::test]
    async fn validate_target_strips_scheme_and_port() {
        assert!(validate_target("https://example.com:8443/path")
            .await
            .is_ok());
        assert!(validate_target("example.com:8080").await.is_ok());
    }

    #[tokio::test]
    async fn validate_target_rejects_invalid_hostname() {
        assert!(validate_target("not a hostname!!").await.is_err());
    }

    #[tokio::test]
    async fn validate_target_rejects_leading_hyphen_hostname() {
        assert!(validate_target("-evil.example.com").await.is_err());
    }

    #[test]
    fn validate_dns_query_optional() {
        assert!(validate_dns_query("").is_ok());
        assert!(validate_dns_query("example.com").is_ok());
        assert!(validate_dns_query("not a domain!!").is_err());
    }

    #[test]
    fn validate_port_bounds() {
        assert!(validate_port(0).is_err());
        assert!(validate_port(1).is_ok());
        assert!(validate_port(65535).is_ok());
        assert!(validate_port(65536).is_err());
    }

    #[test]
    fn validate_timeout_bounds() {
        assert!(validate_timeout(0).is_err());
        assert!(validate_timeout(1).is_ok());
        assert!(validate_timeout(300).is_ok());
        assert!(validate_timeout(301).is_err());
    }

    #[test]
    fn validate_count_bounds() {
        assert!(validate_count(0).is_err());
        assert!(validate_count(1000).is_ok());
        assert!(validate_count(1001).is_err());
    }

    #[test]
    fn protocol_whitelists_allow_empty_as_default() {
        assert!(validate_http_protocol("").is_ok());
        assert!(validate_tcp_protocol("").is_ok());
        assert!(validate_udp_protocol("").is_ok());
        assert!(validate_icmp_protocol("").is_ok());
        assert!(validate_http_method("").is_ok());
    }

    #[test]
    fn protocol_whitelists_reject_unknown_values() {
        assert!(validate_http_protocol("gopher").is_err());
        assert!(validate_tcp_protocol("quic").is_err());
        assert!(validate_udp_protocol("quic").is_err());
        assert!(validate_icmp_protocol("arp").is_err());
        assert!(validate_http_method("PATCH").is_err());
    }

    #[test]
    fn protocol_whitelists_accept_known_values() {
        assert!(validate_http_protocol("http2").is_ok());
        assert!(validate_tcp_protocol("tls").is_ok());
        assert!(validate_tcp_protocol("ssh").is_ok());
        assert!(validate_udp_protocol("dns").is_ok());
        assert!(validate_icmp_protocol("ping").is_ok());
        assert!(validate_http_method("POST").is_ok());
    }

    #[test]
    fn sanitize_string_trims_truncates_and_strips_control_chars() {
        assert_eq!(sanitize_string("  hello  ", 100), "hello");
        assert_eq!(sanitize_string("abcdef", 3), "abc");
        assert_eq!(sanitize_string("a\0b\tc\nd", 100), "ab\tc\nd");
    }
}
