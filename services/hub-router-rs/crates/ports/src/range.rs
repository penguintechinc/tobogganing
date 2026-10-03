//! Port-range configuration parsing — the Rust port of the Go headend's
//! `ports.PortManager.parseRangeString`
//! (`services/hub-router/proxy/ports/manager.go`). Parses strings like
//! `"8000-8100,9000,9500-9600"` into a list of [`PortRange`]s.
//!
//! The Go source overloads a single `PortRange` struct for two different
//! purposes: the lean `{StartPort, EndPort, Protocol}` triple produced by
//! parsing, and the Manager API's detailed `{ID, Description, Enabled,
//! CreatedAt, UpdatedAt, ...}` JSON shape (`config_client.go`), leaving the
//! extra fields zero-valued whenever a `PortRange` is built by the parser.
//! This port splits that conflation into [`PortRange`] (parsed config) and
//! [`crate::config_client::PortRangeDetail`] (Manager API detail) —
//! fix-while-porting, not a behavior change.

use std::fmt;

/// Transport protocol a [`PortRange`] applies to.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Protocol {
    Tcp,
    Udp,
}

impl fmt::Display for Protocol {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Protocol::Tcp => write!(f, "tcp"),
            Protocol::Udp => write!(f, "udp"),
        }
    }
}

/// A single parsed port range (inclusive on both ends) for one protocol —
/// `start_port == end_port` for a single-port entry (e.g. `"9000"`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PortRange {
    pub start_port: u16,
    pub end_port: u16,
    pub protocol: Protocol,
}

/// Failure parsing one range-string entry — variant text mirrors the Go
/// source's `fmt.Errorf` messages exactly (`manager.go::parseRangeString`)
/// so characterization tests can assert against known-good Go wording.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum RangeParseError {
    #[error("invalid range format: {0}")]
    InvalidRangeFormat(String),
    #[error("invalid start port: {0}")]
    InvalidStartPort(String),
    #[error("invalid end port: {0}")]
    InvalidEndPort(String),
    #[error("start port {start} greater than end port {end}")]
    StartGreaterThanEnd { start: i64, end: i64 },
    #[error("port range {start}-{end} outside valid range 1-65535")]
    RangeOutOfBounds { start: i64, end: i64 },
    #[error("invalid port: {0}")]
    InvalidPort(String),
    #[error("port {0} outside valid range 1-65535")]
    PortOutOfBounds(i64),
}

/// Parses a comma-separated range string (e.g. `"8000-8100,9000"`) for a
/// single `protocol` into zero or more [`PortRange`]s.
///
/// Behavior deliberately mirrors `parseRangeString` in
/// `services/hub-router/proxy/ports/manager.go`, including two
/// characterized Go quirks preserved as-is (not "fixed") because they are
/// the Go headend's actual observable behavior and callers may depend on
/// it:
/// - A blank/whitespace-only input parses to an empty list, not an error.
/// - Empty entries from doubled/trailing commas (`"8000,,9000,"`) are
///   silently skipped.
/// - A bare negative number (e.g. `"-5"`) is treated as range syntax
///   (it contains `-`), splitting into an empty start segment and erroring
///   as [`RangeParseError::InvalidStartPort`] rather than
///   [`RangeParseError::InvalidPort`] — surprising, but exactly what the Go
///   `strings.Contains(part, "-")` branch does.
#[tracing::instrument(skip(range_str), fields(protocol = %protocol))]
pub fn parse_port_ranges(
    range_str: &str,
    protocol: Protocol,
) -> Result<Vec<PortRange>, RangeParseError> {
    let start = std::time::Instant::now();
    let result = parse_port_ranges_inner(range_str, protocol);
    let outcome = if result.is_ok() { "ok" } else { "error" };
    crate::metrics::record_range_parse(start.elapsed().as_secs_f64(), protocol, outcome);
    result
}

fn parse_port_ranges_inner(
    range_str: &str,
    protocol: Protocol,
) -> Result<Vec<PortRange>, RangeParseError> {
    let mut ranges = Vec::new();

    if range_str.trim().is_empty() {
        return Ok(ranges);
    }

    for raw_part in range_str.split(',') {
        let part = raw_part.trim();
        if part.is_empty() {
            continue;
        }

        if part.contains('-') {
            let range_parts: Vec<&str> = part.split('-').collect();
            if range_parts.len() != 2 {
                return Err(RangeParseError::InvalidRangeFormat(part.to_string()));
            }

            let start_raw = range_parts[0].trim();
            let end_raw = range_parts[1].trim();

            let start: i64 = start_raw
                .parse()
                .map_err(|_| RangeParseError::InvalidStartPort(start_raw.to_string()))?;
            let end: i64 = end_raw
                .parse()
                .map_err(|_| RangeParseError::InvalidEndPort(end_raw.to_string()))?;

            if start > end {
                return Err(RangeParseError::StartGreaterThanEnd { start, end });
            }
            if start < 1 || end > 65535 {
                return Err(RangeParseError::RangeOutOfBounds { start, end });
            }

            ranges.push(PortRange {
                // SAFETY/invariant: 1 <= start <= end <= 65535 was just
                // checked above, so both casts are lossless.
                start_port: start as u16,
                end_port: end as u16,
                protocol,
            });
        } else {
            let port: i64 = part
                .parse()
                .map_err(|_| RangeParseError::InvalidPort(part.to_string()))?;

            if !(1..=65535).contains(&port) {
                return Err(RangeParseError::PortOutOfBounds(port));
            }

            ranges.push(PortRange {
                start_port: port as u16,
                end_port: port as u16,
                protocol,
            });
        }
    }

    Ok(ranges)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tcp(s: &str) -> Result<Vec<PortRange>, RangeParseError> {
        parse_port_ranges(s, Protocol::Tcp)
    }

    #[test]
    fn empty_string_yields_no_ranges() {
        assert_eq!(tcp("").unwrap(), vec![]);
    }

    #[test]
    fn whitespace_only_yields_no_ranges() {
        assert_eq!(tcp("   ").unwrap(), vec![]);
    }

    #[test]
    fn single_port_parses() {
        assert_eq!(
            tcp("9000").unwrap(),
            vec![PortRange {
                start_port: 9000,
                end_port: 9000,
                protocol: Protocol::Tcp
            }]
        );
    }

    #[test]
    fn simple_range_parses() {
        assert_eq!(
            tcp("8000-8100").unwrap(),
            vec![PortRange {
                start_port: 8000,
                end_port: 8100,
                protocol: Protocol::Tcp
            }]
        );
    }

    #[test]
    fn mixed_ranges_and_singles_parse_in_order() {
        let got = tcp("8000-8100,9000,9500-9600").unwrap();
        assert_eq!(
            got,
            vec![
                PortRange {
                    start_port: 8000,
                    end_port: 8100,
                    protocol: Protocol::Tcp
                },
                PortRange {
                    start_port: 9000,
                    end_port: 9000,
                    protocol: Protocol::Tcp
                },
                PortRange {
                    start_port: 9500,
                    end_port: 9600,
                    protocol: Protocol::Tcp
                },
            ]
        );
    }

    #[test]
    fn doubled_and_trailing_commas_are_skipped() {
        let got = tcp("8000,,9000,").unwrap();
        assert_eq!(
            got,
            vec![
                PortRange {
                    start_port: 8000,
                    end_port: 8000,
                    protocol: Protocol::Tcp
                },
                PortRange {
                    start_port: 9000,
                    end_port: 9000,
                    protocol: Protocol::Tcp
                },
            ]
        );
    }

    #[test]
    fn whitespace_inside_a_range_is_trimmed() {
        assert_eq!(
            tcp(" 8000 - 8100 ").unwrap(),
            vec![PortRange {
                start_port: 8000,
                end_port: 8100,
                protocol: Protocol::Tcp
            }]
        );
    }

    #[test]
    fn too_many_dashes_is_invalid_range_format() {
        assert_eq!(
            tcp("8000-9000-1000").unwrap_err(),
            RangeParseError::InvalidRangeFormat("8000-9000-1000".to_string())
        );
    }

    #[test]
    fn non_numeric_start_is_invalid_start_port() {
        assert_eq!(
            tcp("abc-100").unwrap_err(),
            RangeParseError::InvalidStartPort("abc".to_string())
        );
    }

    #[test]
    fn non_numeric_end_is_invalid_end_port() {
        assert_eq!(
            tcp("100-abc").unwrap_err(),
            RangeParseError::InvalidEndPort("abc".to_string())
        );
    }

    #[test]
    fn start_greater_than_end_is_rejected() {
        assert_eq!(
            tcp("100-50").unwrap_err(),
            RangeParseError::StartGreaterThanEnd {
                start: 100,
                end: 50
            }
        );
    }

    #[test]
    fn start_below_one_is_out_of_bounds() {
        assert_eq!(
            tcp("0-10").unwrap_err(),
            RangeParseError::RangeOutOfBounds { start: 0, end: 10 }
        );
    }

    #[test]
    fn end_above_65535_is_out_of_bounds() {
        assert_eq!(
            tcp("65000-70000").unwrap_err(),
            RangeParseError::RangeOutOfBounds {
                start: 65000,
                end: 70000
            }
        );
    }

    #[test]
    fn non_numeric_single_port_is_invalid_port() {
        assert_eq!(
            tcp("abc").unwrap_err(),
            RangeParseError::InvalidPort("abc".to_string())
        );
    }

    #[test]
    fn single_port_zero_is_out_of_bounds() {
        assert_eq!(tcp("0").unwrap_err(), RangeParseError::PortOutOfBounds(0));
    }

    #[test]
    fn single_port_above_65535_is_out_of_bounds() {
        assert_eq!(
            tcp("70000").unwrap_err(),
            RangeParseError::PortOutOfBounds(70000)
        );
    }

    /// Characterizes a Go quirk: a bare negative number contains `-`, so it
    /// takes the range-parsing branch rather than the single-port branch —
    /// `strings.Split("-5", "-")` yields `["", "5"]`, so the *start* half
    /// fails to parse (empty string), not the whole token as one value.
    #[test]
    fn bare_negative_number_is_treated_as_range_syntax() {
        assert_eq!(
            tcp("-5").unwrap_err(),
            RangeParseError::InvalidStartPort(String::new())
        );
    }

    /// Characterizes the same quirk for a full negative range: `"-5-10"`
    /// splits on `-` into three parts (`["", "5", "10"]`), which fails the
    /// Go source's `len(rangeParts) != 2` check before the values are ever
    /// interpreted as negative numbers.
    #[test]
    fn negative_range_syntax_is_invalid_range_format() {
        assert_eq!(
            tcp("-5-10").unwrap_err(),
            RangeParseError::InvalidRangeFormat("-5-10".to_string())
        );
    }

    #[test]
    fn protocol_is_attached_to_every_parsed_range() {
        let got = parse_port_ranges("1000", Protocol::Udp).unwrap();
        assert_eq!(got[0].protocol, Protocol::Udp);
    }

    #[test]
    fn protocol_display_matches_go_json_lowercase() {
        assert_eq!(Protocol::Tcp.to_string(), "tcp");
        assert_eq!(Protocol::Udp.to_string(), "udp");
    }
}
