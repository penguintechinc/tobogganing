//! Message formatting for the syslog log-forwarding subsystem — the Rust
//! port of `AccessLog`, the facility/severity priority constants, and
//! `sendLog`'s wire framing
//! (`services/hub-router/proxy/syslog/logger.go`, lines 27-81, 266-305).
//!
//! **The package doc's "RFC3164 compliant" claim is inaccurate** —
//! characterized here exactly as Go emits it, not corrected, since any
//! existing syslog receiver already parses this specific (non-standard)
//! shape and changing the wire format is a breaking change outside this
//! port's scope. The real framing is `<priority>timestamp hostname
//! appname: json`, where:
//! - `priority` is genuinely RFC3164's `facility*8+severity`.
//! - the outer `timestamp` is Go's `time.RFC3339`
//!   (`"2006-01-02T15:04:05Z07:00"`, whole seconds only), not RFC3164's
//!   `"Mmm dd hh:mm:ss"` timestamp — see [`format_rfc3339`].
//! - the message body is a JSON payload (`AccessLog`), not RFC3164 free
//!   text.
//!
//! The embedded JSON payload's own `timestamp` field uses Go's
//! `time.Time` default JSON encoding: strict RFC3339 with up to 9
//! fractional digits, trailing zeros trimmed (e.g. a whole-second instant
//! marshals as `"...00Z"` with no fractional part at all). This port
//! always emits the full 9-digit nanosecond-precision, untrimmed form
//! instead (e.g. `"...00.000000000Z"`) — a cosmetic formatting
//! difference only, matching the identical, already-reviewed precedent
//! in `hub_router_mirror::encode`'s own RFC3339-nano helper; no
//! downstream ISO-8601 JSON consumer treats trimmed vs. untrimmed
//! trailing fractional zeros as semantically different. See
//! [`serialize_rfc3339_nano`].

use serde::{Serialize, Serializer};
use std::time::{SystemTime, UNIX_EPOCH};

/// RFC3164 facility codes — the Rust port of Go's `FacilityLocal0`..
/// `FacilityLocal7` constants. Only [`Facility::Local0`] is ever actually
/// used by [`crate::logger::Logger`] (hardcoded in its constructor,
/// exactly as Go's `NewSyslogLogger` hardcodes `facility: FacilityLocal0`
/// and never reads the (dead) `syslog.facility` config value — see
/// [`crate::config`]'s module doc); the rest are kept only for parity
/// with the Go source's exported constant surface.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u16)]
pub enum Facility {
    Local0 = 16,
    Local1 = 17,
    Local2 = 18,
    Local3 = 19,
    Local4 = 20,
    Local5 = 21,
    Local6 = 22,
    Local7 = 23,
}

/// RFC3164 severity codes — the Rust port of Go's `SeverityEmergency`..
/// `SeverityDebug` constants. Only [`Severity::Informational`] is ever
/// actually used (same hardcoding note as [`Facility`]).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u16)]
pub enum Severity {
    Emergency = 0,
    Alert = 1,
    Critical = 2,
    Error = 3,
    Warning = 4,
    Notice = 5,
    Informational = 6,
    Debug = 7,
}

/// RFC3164 priority value — the Rust port of `sendLog`'s `priority :=
/// s.facility*8 + s.severity` (line 277).
#[must_use]
pub fn priority(facility: Facility, severity: Severity) -> u16 {
    facility as u16 * 8 + severity as u16
}

fn is_zero_i32(v: &i32) -> bool {
    *v == 0
}

fn is_zero_i64(v: &i64) -> bool {
    *v == 0
}

/// A user access log entry — field-for-field port of Go's `AccessLog`
/// struct (lines 28-42). Field order matters: Go's `encoding/json`
/// marshals struct fields in declaration order, and `serde_json`
/// (default, no `preserve_order`/map re-sorting) marshals a
/// `#[derive(Serialize)]` struct in the same declared-field order, so
/// this must mirror Go's field order exactly for byte-identical JSON
/// payloads. The six `omitempty`-tagged Go fields
/// (`method`/`path`/`status_code`/`bytes_sent`/`user_agent`/
/// `request_id`) are ported with `skip_serializing_if`.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct AccessLog {
    #[serde(serialize_with = "serialize_rfc3339_nano")]
    pub timestamp: SystemTime,
    pub user_id: String,
    pub username: String,
    pub source_ip: String,
    pub target_host: String,
    pub protocol: String,
    /// `"allow"` or `"deny"` — never empty, no `omitempty` tag on the Go
    /// side either.
    pub action: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub method: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub path: String,
    #[serde(skip_serializing_if = "is_zero_i32")]
    pub status_code: i32,
    #[serde(skip_serializing_if = "is_zero_i64")]
    pub bytes_sent: i64,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub user_agent: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub request_id: String,
}

impl Default for AccessLog {
    /// All-zero-value `AccessLog`, matching Go's struct zero value
    /// (`time.Time{}`'s zero value is the year-1 epoch; this port uses
    /// [`UNIX_EPOCH`] as its "unset" sentinel instead, exactly as
    /// `Logger::log_access`'s `IsZero()` check — ported as `timestamp ==
    /// SystemTime::UNIX_EPOCH` — expects).
    fn default() -> Self {
        Self {
            timestamp: UNIX_EPOCH,
            user_id: String::new(),
            username: String::new(),
            source_ip: String::new(),
            target_host: String::new(),
            protocol: String::new(),
            action: String::new(),
            method: String::new(),
            path: String::new(),
            status_code: 0,
            bytes_sent: 0,
            user_agent: String::new(),
            request_id: String::new(),
        }
    }
}

/// Splits a Unix-epoch second count into civil `(year, month, day, hour,
/// minute, second)` components — Howard Hinnant's civil-from-days
/// algorithm, duplicated (not shared as a workspace dependency) from
/// `hub_router_mirror::encode`'s identical private helper. Each ported
/// subsystem crate stays self-contained with no cross-subsystem
/// dependency, matching this workspace's established pattern (`ports`,
/// `firewall`, and `mirror` don't depend on each other either).
fn civil_from_unix_secs(secs: u64) -> (i64, u32, u32, u64, u64, u64) {
    let days = secs / 86400;
    let rem = secs % 86400;
    let (hour, minute, second) = (rem / 3600, (rem % 3600) / 60, rem % 60);

    let z = days as i64 + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146_096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = if month <= 2 { y + 1 } else { y };

    (year, month as u32, day as u32, hour, minute, second)
}

/// Formats a whole-second RFC3339 UTC timestamp — the Rust port of
/// `accessLog.Timestamp.Format(time.RFC3339)`, used for the *outer*
/// frame's timestamp (see [`format_frame`]). Distinct from the embedded
/// JSON payload's own `timestamp` field, which uses
/// [`serialize_rfc3339_nano`]'s nanosecond-precision format instead — Go
/// independently re-marshals `Timestamp` inside `json.Marshal`, so the
/// two are allowed to differ in precision even in the original Go
/// source.
#[must_use]
pub fn format_rfc3339(ts: SystemTime) -> String {
    let secs = ts.duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
    let (year, month, day, hour, minute, second) = civil_from_unix_secs(secs);
    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}Z")
}

/// Formats a nanosecond-precision RFC3339 UTC timestamp for the embedded
/// JSON payload's `timestamp` field — see the module doc's note on the
/// deliberate (cosmetic) deviation from Go's trailing-zero-trimmed
/// encoding.
fn serialize_rfc3339_nano<S>(ts: &SystemTime, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    let dur = ts.duration_since(UNIX_EPOCH).unwrap_or_default();
    let (year, month, day, hour, minute, second) = civil_from_unix_secs(dur.as_secs());
    let nanos = dur.subsec_nanos();
    serializer.serialize_str(&format!(
        "{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}.{nanos:09}Z"
    ))
}

/// Formats the full outer syslog frame — the Rust port of `sendLog`'s
/// `fmt.Sprintf("<%d>%s %s %s: %s", priority, timestamp, hostname,
/// appName, jsonData)` (lines 288-295). `timestamp` must already be
/// formatted per [`format_rfc3339`]; this function does no formatting of
/// its own, matching Go's literal `fmt.Sprintf` call exactly.
#[must_use]
pub fn format_frame(
    priority: u16,
    timestamp_rfc3339: &str,
    hostname: &str,
    app_name: &str,
    json_payload: &str,
) -> String {
    format!("<{priority}>{timestamp_rfc3339} {hostname} {app_name}: {json_payload}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn priority_is_facility_times_eight_plus_severity() {
        // The only combination the Go source ever actually constructs
        // (FacilityLocal0=16, SeverityInformational=6): 16*8+6=134.
        assert_eq!(priority(Facility::Local0, Severity::Informational), 134);
    }

    #[test]
    fn priority_covers_the_full_facility_severity_matrix() {
        assert_eq!(priority(Facility::Local0, Severity::Emergency), 128);
        assert_eq!(priority(Facility::Local7, Severity::Debug), 191);
    }

    #[test]
    fn format_rfc3339_matches_go_time_rfc3339_for_a_whole_second_instant() {
        // UNIX_EPOCH + 1 day exactly.
        let ts = UNIX_EPOCH + std::time::Duration::from_secs(86_400);
        assert_eq!(format_rfc3339(ts), "1970-01-02T00:00:00Z");
    }

    #[test]
    fn format_rfc3339_discards_sub_second_precision() {
        let ts = UNIX_EPOCH + std::time::Duration::new(60, 999_999_999);
        assert_eq!(format_rfc3339(ts), "1970-01-01T00:01:00Z");
    }

    #[test]
    fn format_frame_matches_go_fmt_sprintf_byte_for_byte() {
        let frame = format_frame(
            134,
            "1970-01-01T00:00:00Z",
            "host1",
            "sasewaddle-headend",
            "{}",
        );
        assert_eq!(
            frame,
            "<134>1970-01-01T00:00:00Z host1 sasewaddle-headend: {}"
        );
    }

    fn sample_log() -> AccessLog {
        AccessLog {
            timestamp: UNIX_EPOCH,
            user_id: "u1".to_string(),
            username: "alice".to_string(),
            source_ip: "10.0.0.1:1234".to_string(),
            target_host: "10.0.0.2:443".to_string(),
            protocol: "TCP".to_string(),
            action: "allow".to_string(),
            ..AccessLog::default()
        }
    }

    #[test]
    fn minimal_access_log_omits_every_omitempty_field_in_go_declared_order() {
        let json = serde_json::to_string(&sample_log()).unwrap();
        assert_eq!(
            json,
            "{\"timestamp\":\"1970-01-01T00:00:00.000000000Z\",\
             \"user_id\":\"u1\",\"username\":\"alice\",\
             \"source_ip\":\"10.0.0.1:1234\",\"target_host\":\"10.0.0.2:443\",\
             \"protocol\":\"TCP\",\"action\":\"allow\"}"
        );
    }

    #[test]
    fn fully_populated_access_log_includes_every_field_in_go_declared_order() {
        let log = AccessLog {
            method: "GET".to_string(),
            path: "/health".to_string(),
            status_code: 200,
            bytes_sent: 42,
            user_agent: "curl/8.0".to_string(),
            request_id: "req-1".to_string(),
            ..sample_log()
        };
        let json = serde_json::to_string(&log).unwrap();
        assert_eq!(
            json,
            "{\"timestamp\":\"1970-01-01T00:00:00.000000000Z\",\
             \"user_id\":\"u1\",\"username\":\"alice\",\
             \"source_ip\":\"10.0.0.1:1234\",\"target_host\":\"10.0.0.2:443\",\
             \"protocol\":\"TCP\",\"action\":\"allow\",\"method\":\"GET\",\
             \"path\":\"/health\",\"status_code\":200,\"bytes_sent\":42,\
             \"user_agent\":\"curl/8.0\",\"request_id\":\"req-1\"}"
        );
    }

    #[test]
    fn timestamp_serializes_with_untrimmed_nanosecond_precision() {
        let ts = UNIX_EPOCH + std::time::Duration::new(0, 123_456_789);
        let log = AccessLog {
            timestamp: ts,
            ..sample_log()
        };
        let value: serde_json::Value =
            serde_json::from_str(&serde_json::to_string(&log).unwrap()).unwrap();
        assert_eq!(value["timestamp"], "1970-01-01T00:00:00.123456789Z");
    }

    #[test]
    fn zero_value_access_log_is_the_default() {
        let log = AccessLog::default();
        assert_eq!(log.timestamp, UNIX_EPOCH);
        assert_eq!(log.protocol, "");
        assert_eq!(log.status_code, 0);
    }
}
