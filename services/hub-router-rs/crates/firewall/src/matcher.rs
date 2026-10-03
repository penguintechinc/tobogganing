//! Pure rule-matching predicates — the Rust port of the Go source's
//! `match*` helpers (`services/hub-router/proxy/firewall/manager.go`'s
//! `matchDomain`/`matchIP`/`matchIPRange`/`matchURLPattern`/
//! `matchProtocolRule` and their shared `parseConnectionTarget`/
//! `matchIPOrRange`/`matchPort` internals). Every function here is a
//! pure function of its inputs (no I/O, no shared state) — this module's
//! `tests` submodule is the characterization-test suite written against
//! the Go source's documented/observed behavior *before* `engine`/
//! `manager` existed, per this PR's characterize-first requirement.

use crate::rule::FirewallRule;
use std::net::IpAddr;
use std::str::FromStr;

/// Extracts the hostname/IP portion of `target`: if `target` is an
/// `http://`/`https://` URL, its parsed host; otherwise `target`
/// unchanged. Mirrors the repeated
/// `strings.HasPrefix(target, "http://") ...; url.Parse(target)` block
/// in the Go source's `matchIP`/`matchIPRange` (an equivalent inline
/// block, lower-cased, lives in `match_domain` since that one lower-cases
/// the result).
fn url_host_or_self(target: &str) -> String {
    if target.starts_with("http://") || target.starts_with("https://") {
        if let Ok(parsed) = url::Url::parse(target) {
            if let Some(host) = parsed.host_str() {
                return host.to_string();
            }
        }
    }
    target.to_string()
}

/// Strips a trailing `:port` from `host_port`, mirroring Go's
/// `net.SplitHostPort` used defensively
/// (`if host, _, err := net.SplitHostPort(...); err == nil`) — i.e. only
/// strip when it's unambiguous. A bracketed IPv6 literal (`[::1]:8080`)
/// strips to `::1`; a bare, bracket-less IPv6 literal (ambiguous: colons
/// are part of the address, not a port separator) is left untouched,
/// exactly as `net.SplitHostPort` fails (and that failure is ignored) on
/// that input in Go.
fn strip_port(host_port: &str) -> &str {
    if let Some(rest) = host_port.strip_prefix('[') {
        if let Some(end) = rest.find(']') {
            return &rest[..end];
        }
        return host_port;
    }
    if host_port.matches(':').count() == 1 {
        if let Some(idx) = host_port.rfind(':') {
            return &host_port[..idx];
        }
    }
    host_port
}

/// Parses `s` as an IP address, returning its canonical form — collapses
/// an IPv4-mapped IPv6 address (`::ffff:a.b.c.d`) onto the equivalent
/// plain IPv4 address. This matches Go's `net.IP` internal representation:
/// `net.ParseIP` always stores an IPv4 address in 16-byte form internally,
/// so `net.IP.Equal` treats the mapped and plain forms as identical — see
/// `tests::ipv4_mapped_ipv6_matches_plain_ipv4_like_go_net_ip_equal`.
fn parse_ip_canonical(s: &str) -> Option<IpAddr> {
    IpAddr::from_str(s).ok().map(|ip| ip.to_canonical())
}

/// Case-insensitive exact-or-wildcard-subdomain match — the Rust port of
/// `matchDomain`. `*.example.com` matches both `example.com` itself and
/// any subdomain of it (Go source:
/// `targetDomain == baseDomain || strings.HasSuffix(targetDomain, "."+baseDomain)`).
///
/// Preserved Go quirk (characterized as-is, not fixed): when `target`
/// isn't an `http(s)://` URL, no port is stripped — a bare (non-URL)
/// target of `example.com:8080` will NOT match an `example.com` pattern,
/// unlike [`match_ip`]/[`match_ip_range`] which always strip a port
/// first. Domain rules are evaluated against bare hostnames or full URLs
/// in practice, so this is low-risk; "fixing" it could silently change
/// which already-deployed rules match in production, so it's documented
/// here rather than changed.
pub(crate) fn match_domain(pattern: &str, target: &str) -> bool {
    let target_domain = if target.starts_with("http://") || target.starts_with("https://") {
        url::Url::parse(target)
            .ok()
            .and_then(|u| u.host_str().map(str::to_lowercase))
            .unwrap_or_default()
    } else {
        target.to_lowercase()
    };
    let pattern = pattern.to_lowercase();

    if pattern == target_domain {
        return true;
    }

    if let Some(base_domain) = pattern.strip_prefix("*.") {
        if target_domain == base_domain || target_domain.ends_with(&format!(".{base_domain}")) {
            return true;
        }
    }

    false
}

/// Exact single-address match — the Rust port of `matchIP`. Both
/// `pattern` and the (URL/port-stripped) `target` must parse as valid IP
/// addresses; malformed input never matches.
pub(crate) fn match_ip(pattern: &str, target: &str) -> bool {
    let target_host = strip_port(&url_host_or_self(target)).to_string();
    match (
        parse_ip_canonical(&target_host),
        parse_ip_canonical(pattern),
    ) {
        (Some(t), Some(p)) => t == p,
        _ => false,
    }
}

/// CIDR-range containment match — the Rust port of `matchIPRange`.
pub(crate) fn match_ip_range(pattern: &str, target: &str) -> bool {
    let target_host = strip_port(&url_host_or_self(target)).to_string();
    let Ok(target_addr) = IpAddr::from_str(&target_host) else {
        return false;
    };
    let Ok(network) = ipnet::IpNet::from_str(pattern) else {
        return false;
    };
    network.contains(&target_addr)
}

/// Case-insensitive regex match against the full `target` string — the
/// Rust port of `matchURLPattern`. An invalid regex pattern is logged
/// and treated as a non-match (Go source: `log.Errorf(...); return
/// false`), never a panic — one malformed stored rule must not take down
/// evaluation of every other rule.
pub(crate) fn match_url_pattern(pattern: &str, target: &str) -> bool {
    match regex::RegexBuilder::new(pattern)
        .case_insensitive(true)
        .build()
    {
        Ok(re) => re.is_match(target),
        Err(error) => {
            tracing::error!(pattern, %error, "invalid firewall url_pattern regex");
            false
        }
    }
}

/// `protocol:src_ip:src_port->dst_ip:dst_port:direction` connection
/// 5-tuple, parsed from a `target` string — the Rust port of
/// `parseConnectionTarget`. Returns `None` if `target` has no `->`
/// separator (not a protocol-rule target at all), matching the Go
/// source's `if !strings.Contains(target, "->") { return nil }`.
#[derive(Debug, Clone, PartialEq, Eq)]
struct ConnInfo {
    protocol: String,
    src_ip: String,
    src_port: String,
    dst_ip: String,
    dst_port: String,
    direction: String,
}

fn parse_connection_target(target: &str) -> Option<ConnInfo> {
    let (src_part, dst_part) = target.split_once("->")?;

    let mut src_components = src_part.split(':');
    let protocol = src_components.next().unwrap_or_default().to_string();
    let src_ip = src_components.next().unwrap_or("*").to_string();
    let src_port = src_components.next().unwrap_or("*").to_string();

    let mut dst_components = dst_part.split(':');
    let dst_ip = dst_components.next().unwrap_or("*").to_string();
    let dst_port = dst_components.next().unwrap_or("*").to_string();
    let direction = dst_components.next().unwrap_or("outbound").to_string();

    Some(ConnInfo {
        protocol,
        src_ip,
        src_port,
        dst_ip,
        dst_port,
        direction,
    })
}

/// IP-or-CIDR-or-wildcard match used for a protocol rule's `src_ip`/
/// `dst_ip` fields — the Rust port of `matchIPOrRange`.
fn match_ip_or_range(rule_ip: &str, target_ip: &str) -> bool {
    if rule_ip == "*" || target_ip == "*" {
        return true;
    }
    if rule_ip.contains('/') {
        let Ok(network) = ipnet::IpNet::from_str(rule_ip) else {
            return false;
        };
        let Ok(target_addr) = IpAddr::from_str(target_ip) else {
            return false;
        };
        return network.contains(&target_addr);
    }
    match (parse_ip_canonical(rule_ip), parse_ip_canonical(target_ip)) {
        (Some(r), Some(t)) => r == t,
        _ => false,
    }
}

/// Single-port, port-range (`"80-443"`), port-list (`"80,443,8080"`), or
/// wildcard (`"*"`) match — the Rust port of `matchPort`. Precedence
/// (range checked before list) matches the Go source's `if
/// strings.Contains(rulePort, "-") { ... } else if
/// strings.Contains(rulePort, ",") { ... } else { single port }` chain.
fn match_port(rule_port: &str, target_port: &str) -> bool {
    if rule_port == "*" || target_port == "*" {
        return true;
    }
    let Ok(target_num) = target_port.parse::<i64>() else {
        return false;
    };

    if let Some((start, end)) = rule_port.split_once('-') {
        let (Ok(start), Ok(end)) = (start.trim().parse::<i64>(), end.trim().parse::<i64>()) else {
            return false;
        };
        return target_num >= start && target_num <= end;
    }

    if rule_port.contains(',') {
        return rule_port
            .split(',')
            .filter_map(|p| p.trim().parse::<i64>().ok())
            .any(|p| p == target_num);
    }

    match rule_port.parse::<i64>() {
        Ok(rule_num) => rule_num == target_num,
        Err(_) => false,
    }
}

/// Protocol-5-tuple match: every non-empty field on `rule` must match
/// the corresponding component parsed out of `target` — the Rust port of
/// `matchProtocolRule`. `direction: "both"` (or an empty `direction`)
/// matches either direction, mirroring the Go source's
/// `if rule.Direction != "" && rule.Direction != "both" { ... }` guard.
pub(crate) fn match_protocol_rule(rule: &FirewallRule, target: &str) -> bool {
    let Some(conn) = parse_connection_target(target) else {
        return false;
    };

    if !rule.protocol.is_empty() && !rule.protocol.eq_ignore_ascii_case(&conn.protocol) {
        return false;
    }
    if !rule.src_ip.is_empty() && !match_ip_or_range(&rule.src_ip, &conn.src_ip) {
        return false;
    }
    if !rule.dst_ip.is_empty() && !match_ip_or_range(&rule.dst_ip, &conn.dst_ip) {
        return false;
    }
    if !rule.src_port.is_empty() && !match_port(&rule.src_port, &conn.src_port) {
        return false;
    }
    if !rule.dst_port.is_empty() && !match_port(&rule.dst_port, &conn.dst_port) {
        return false;
    }
    if !rule.direction.is_empty() && rule.direction != "both" && rule.direction != conn.direction {
        return false;
    }

    true
}

#[cfg(test)]
mod tests {
    use super::*;

    fn protocol_rule(
        protocol: &str,
        src_ip: &str,
        dst_ip: &str,
        src_port: &str,
        dst_port: &str,
        direction: &str,
    ) -> FirewallRule {
        FirewallRule {
            pattern: "protocol-rule".to_string(),
            priority: 10,
            description: String::new(),
            src_ip: src_ip.to_string(),
            dst_ip: dst_ip.to_string(),
            protocol: protocol.to_string(),
            src_port: src_port.to_string(),
            dst_port: dst_port.to_string(),
            direction: direction.to_string(),
        }
    }

    // --- match_domain ---------------------------------------------------

    #[test]
    fn domain_exact_match_is_case_insensitive() {
        assert!(match_domain("Example.com", "example.COM"));
    }

    #[test]
    fn domain_wildcard_matches_subdomain_and_base() {
        assert!(match_domain("*.example.com", "sub.example.com"));
        assert!(match_domain("*.example.com", "example.com"));
        assert!(!match_domain("*.example.com", "evil-example.com"));
        assert!(!match_domain("*.example.com", "other.com"));
    }

    #[test]
    fn domain_extracts_host_from_url_target() {
        assert!(match_domain(
            "example.com",
            "https://example.com/some/path?q=1"
        ));
        assert!(match_domain("*.example.com", "http://api.example.com/v1"));
    }

    #[test]
    fn domain_no_match_for_unrelated_pattern() {
        assert!(!match_domain("example.com", "example.org"));
    }

    /// Characterized Go quirk: a bare (non-URL) target keeps its port,
    /// so it never matches a bare-hostname pattern — see this module's
    /// doc on `match_domain`.
    #[test]
    fn domain_bare_target_with_port_does_not_match_bare_pattern() {
        assert!(!match_domain("example.com", "example.com:8080"));
    }

    // --- match_ip ---------------------------------------------------------

    #[test]
    fn ip_exact_match() {
        assert!(match_ip("10.0.0.1", "10.0.0.1"));
        assert!(!match_ip("10.0.0.1", "10.0.0.2"));
    }

    #[test]
    fn ip_strips_port_from_bare_target() {
        assert!(match_ip("10.0.0.1", "10.0.0.1:8443"));
    }

    #[test]
    fn ip_strips_bracketed_ipv6_port() {
        assert!(match_ip("::1", "[::1]:8443"));
    }

    #[test]
    fn ip_extracts_host_from_url_target() {
        assert!(match_ip("93.184.216.34", "http://93.184.216.34:8080/path"));
    }

    #[test]
    fn ip_malformed_input_never_matches() {
        assert!(!match_ip("not-an-ip", "10.0.0.1"));
        assert!(!match_ip("10.0.0.1", "not-an-ip"));
    }

    /// Characterization of Go's `net.IP.Equal` semantics: `net.ParseIP`
    /// always stores IPv4 addresses in 16-byte (IPv4-in-IPv6-mapped)
    /// form internally, so a plain IPv4 literal and its `::ffff:`-mapped
    /// IPv6 form compare equal. `parse_ip_canonical`'s `.to_canonical()`
    /// call exists specifically to preserve this.
    #[test]
    fn ipv4_mapped_ipv6_matches_plain_ipv4_like_go_net_ip_equal() {
        assert!(match_ip("1.2.3.4", "::ffff:1.2.3.4"));
        assert!(match_ip("::ffff:1.2.3.4", "1.2.3.4"));
    }

    // --- match_ip_range -----------------------------------------------

    #[test]
    fn ip_range_contains_address_in_cidr() {
        assert!(match_ip_range("10.0.0.0/24", "10.0.0.55"));
        assert!(!match_ip_range("10.0.0.0/24", "10.0.1.55"));
    }

    #[test]
    fn ip_range_strips_port_and_url_host() {
        assert!(match_ip_range("10.0.0.0/24", "10.0.0.55:9000"));
        assert!(match_ip_range(
            "10.0.0.0/24",
            "http://10.0.0.55:9000/healthz"
        ));
    }

    #[test]
    fn ip_range_ipv6_cidr() {
        assert!(match_ip_range("2001:db8::/32", "2001:db8::1"));
        assert!(!match_ip_range("2001:db8::/32", "2001:dead::1"));
    }

    #[test]
    fn ip_range_invalid_cidr_never_matches() {
        assert!(!match_ip_range("not-a-cidr", "10.0.0.1"));
    }

    // --- match_url_pattern -----------------------------------------------

    #[test]
    fn url_pattern_matches_case_insensitively() {
        assert!(match_url_pattern(
            r"^https://.*\.EXAMPLE\.com/admin",
            "https://api.example.com/admin/users"
        ));
    }

    #[test]
    fn url_pattern_no_match_returns_false() {
        assert!(!match_url_pattern(
            r"^https://.*\.example\.com/admin",
            "https://api.example.com/public"
        ));
    }

    /// Characterized Go behavior: an invalid regex pattern is treated as
    /// a non-match, not an error/panic (`log.Errorf`; `return false`).
    #[test]
    fn url_pattern_invalid_regex_is_a_non_match_not_a_panic() {
        assert!(!match_url_pattern("(unclosed", "anything"));
    }

    // --- match_protocol_rule / parse_connection_target --------------------

    #[test]
    fn protocol_rule_matches_full_tuple() {
        let rule = protocol_rule("tcp", "10.0.0.0/24", "8.8.8.8", "*", "443", "outbound");
        assert!(match_protocol_rule(
            &rule,
            "tcp:10.0.0.5:51234->8.8.8.8:443:outbound"
        ));
    }

    #[test]
    fn protocol_rule_protocol_mismatch_denies() {
        let rule = protocol_rule("udp", "*", "*", "*", "*", "");
        assert!(!match_protocol_rule(
            &rule,
            "tcp:10.0.0.5:1->8.8.8.8:443:outbound"
        ));
    }

    #[test]
    fn protocol_rule_protocol_match_is_case_insensitive() {
        let rule = protocol_rule("TCP", "*", "*", "*", "*", "");
        assert!(match_protocol_rule(
            &rule,
            "tcp:10.0.0.5:1->8.8.8.8:443:outbound"
        ));
    }

    #[test]
    fn protocol_rule_non_connection_target_never_matches() {
        let rule = protocol_rule("tcp", "*", "*", "*", "*", "");
        assert!(!match_protocol_rule(&rule, "example.com"));
    }

    #[test]
    fn protocol_rule_direction_both_matches_either_direction() {
        let rule = protocol_rule("tcp", "*", "*", "*", "*", "both");
        assert!(match_protocol_rule(
            &rule,
            "tcp:10.0.0.5:1->8.8.8.8:443:outbound"
        ));
        assert!(match_protocol_rule(
            &rule,
            "tcp:10.0.0.5:1->8.8.8.8:443:inbound"
        ));
    }

    #[test]
    fn protocol_rule_direction_defaults_to_outbound_when_omitted() {
        let rule = protocol_rule("tcp", "*", "*", "*", "*", "outbound");
        // No direction component at all in the target -> parse default "outbound".
        assert!(match_protocol_rule(&rule, "tcp:10.0.0.5:1->8.8.8.8:443"));
    }

    #[test]
    fn protocol_rule_dst_port_range_matches() {
        let rule = protocol_rule("tcp", "*", "*", "*", "8000-9000", "");
        assert!(match_protocol_rule(
            &rule,
            "tcp:10.0.0.5:1->8.8.8.8:8500:outbound"
        ));
        assert!(!match_protocol_rule(
            &rule,
            "tcp:10.0.0.5:1->8.8.8.8:9500:outbound"
        ));
    }

    #[test]
    fn protocol_rule_dst_port_list_matches() {
        let rule = protocol_rule("tcp", "*", "*", "*", "80,443,8080", "");
        assert!(match_protocol_rule(
            &rule,
            "tcp:10.0.0.5:1->8.8.8.8:443:outbound"
        ));
        assert!(!match_protocol_rule(
            &rule,
            "tcp:10.0.0.5:1->8.8.8.8:22:outbound"
        ));
    }

    /// `protocol` must be the empty string to mean "any protocol" — the
    /// Go source gives `protocol` no `"*"` wildcard special-case (unlike
    /// `src_ip`/`dst_ip`/the port fields, which explicitly treat `"*"`
    /// as "any" in `matchIPOrRange`/`matchPort`), so a literal `"*"`
    /// pattern only matches a connection whose protocol is literally the
    /// string `"*"`.
    #[test]
    fn protocol_rule_empty_protocol_and_wildcard_ip_port_always_matches() {
        let rule = protocol_rule("", "*", "*", "*", "*", "");
        assert!(match_protocol_rule(
            &rule,
            "icmp:1.2.3.4:0->5.6.7.8:0:outbound"
        ));
    }

    #[test]
    fn protocol_rule_literal_asterisk_protocol_is_not_a_wildcard() {
        let rule = protocol_rule("*", "*", "*", "*", "*", "");
        assert!(!match_protocol_rule(
            &rule,
            "icmp:1.2.3.4:0->5.6.7.8:0:outbound"
        ));
    }
}
