//! Standalone validation of a pair of TCP/UDP port-range configuration
//! strings — the Rust port of `PortManager.ValidatePortRanges`
//! (`services/hub-router/proxy/ports/manager.go`). The Go method is
//! attached to `*PortManager` but reads none of the manager's own state
//! (only re-invokes its parser), so this is a free function here rather
//! than a [`crate::manager::PortManager`] method — matches actual
//! behavior, not the (misleading) receiver type.
//!
//! The Go doc comment claims this "checks if the specified port ranges
//! are valid and available" — in reality it only parses and checks for
//! *configuration-level* duplicates (same protocol, same port claimed by
//! two entries); it never probes whether a port is actually bindable on
//! the host. This port keeps that exact behavior (duplicate detection
//! only) but corrects the doc comment rather than repeating the
//! overclaim — see [`validate_port_ranges`].

use crate::range::{parse_port_ranges, Protocol, RangeParseError};
use std::collections::HashSet;

/// Failure validating a TCP/UDP port-range configuration pair. Wrapping
/// text mirrors `ValidatePortRanges`'s `fmt.Errorf` prefixes exactly
/// (distinct from [`crate::manager::ManagerError`]'s "failed to parse ..."
/// wording used by `ParsePortRanges` for the *same* underlying parse
/// failure) — the Go source really does use two different prefixes for
/// the same error depending on which exported function is called.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum ValidateError {
    #[error("invalid TCP ranges: {0}")]
    InvalidTcp(#[source] RangeParseError),
    #[error("invalid UDP ranges: {0}")]
    InvalidUdp(#[source] RangeParseError),
    #[error("duplicate TCP port {0} in configuration")]
    DuplicateTcp(u16),
    #[error("duplicate UDP port {0} in configuration")]
    DuplicateUdp(u16),
}

/// Validates that `tcp_ranges`/`udp_ranges` parse successfully and contain
/// no duplicate port within the same protocol (TCP and UDP occupy
/// independent namespaces, so the same port number in both is fine — it's
/// two different listening sockets). Does **not** check whether any port
/// is actually free on the host; see the module doc.
#[tracing::instrument]
pub fn validate_port_ranges(tcp_ranges: &str, udp_ranges: &str) -> Result<(), ValidateError> {
    let tcp_parsed =
        parse_port_ranges(tcp_ranges, Protocol::Tcp).map_err(ValidateError::InvalidTcp)?;
    let udp_parsed =
        parse_port_ranges(udp_ranges, Protocol::Udp).map_err(ValidateError::InvalidUdp)?;

    let mut seen_tcp: HashSet<u16> = HashSet::new();
    for range in &tcp_parsed {
        for port in range.start_port..=range.end_port {
            if !seen_tcp.insert(port) {
                return Err(ValidateError::DuplicateTcp(port));
            }
        }
    }

    let mut seen_udp: HashSet<u16> = HashSet::new();
    for range in &udp_parsed {
        for port in range.start_port..=range.end_port {
            if !seen_udp.insert(port) {
                return Err(ValidateError::DuplicateUdp(port));
            }
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn disjoint_ranges_are_valid() {
        assert!(validate_port_ranges("8000-8010", "9000-9010").is_ok());
    }

    #[test]
    fn same_port_number_in_tcp_and_udp_is_not_a_duplicate() {
        // TCP and UDP are independent namespaces.
        assert!(validate_port_ranges("8000", "8000").is_ok());
    }

    #[test]
    fn exact_duplicate_single_ports_in_tcp_are_rejected() {
        assert_eq!(
            validate_port_ranges("8000,8000", "").unwrap_err(),
            ValidateError::DuplicateTcp(8000)
        );
    }

    #[test]
    fn overlapping_tcp_ranges_are_rejected_at_first_overlap() {
        assert_eq!(
            validate_port_ranges("8000-8010,8005-8015", "").unwrap_err(),
            ValidateError::DuplicateTcp(8005)
        );
    }

    #[test]
    fn duplicate_udp_ports_are_rejected() {
        assert_eq!(
            validate_port_ranges("", "9000,9000").unwrap_err(),
            ValidateError::DuplicateUdp(9000)
        );
    }

    #[test]
    fn invalid_tcp_ranges_are_wrapped_as_invalid_tcp() {
        assert_eq!(
            validate_port_ranges("abc-100", "").unwrap_err(),
            ValidateError::InvalidTcp(RangeParseError::InvalidStartPort("abc".to_string()))
        );
    }

    #[test]
    fn invalid_udp_ranges_are_wrapped_as_invalid_udp() {
        assert_eq!(
            validate_port_ranges("", "abc-100").unwrap_err(),
            ValidateError::InvalidUdp(RangeParseError::InvalidStartPort("abc".to_string()))
        );
    }

    /// Documents the real (not aspirational) behavior: validation never
    /// probes the OS, so a port already bound by something else on this
    /// host still validates successfully.
    #[tokio::test]
    async fn validation_does_not_check_host_port_availability() {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
            .await
            .expect("binding an ephemeral port for this test");
        let bound_port = listener.local_addr().unwrap().port();

        assert!(validate_port_ranges(&bound_port.to_string(), "").is_ok());
    }
}
