//! Pure packet-encoding/encapsulation functions — the Rust port of
//! `encapsulateVXLAN`, `encapsulateGRE`, `encapsulateERSPAN`, `encodeHTTP`,
//! and `prepareSuricataData`
//! (`services/hub-router/proxy/mirror/manager.go`, lines 338-500). Kept
//! free of any I/O/socket concern so every byte-for-byte characterization
//! case can run as a plain unit test.
//!
//! Two deliberate, non-behavioral adjustments from the Go source (both
//! documented at the relevant function below): (1) [`encapsulate_erspan`]
//! derives its pseudo-unique "index" field from the
//! [`crate::packet::MirrorPacket`]'s own `timestamp` rather than
//! re-querying the system clock at encapsulation time, for determinism
//! and testability — the Go source's index has no cryptographic
//! significance (its own comment: "simplified"/"Session ID 1" hardcoded),
//! so this produces an equivalent pseudo-unique value, not a different
//! one; (2) [`encode_http`] iterates `headers` in caller-supplied order
//! (a `Vec`) rather than Go's `map[string][]string` (iteration order
//! unspecified by the Go language spec) — strictly more deterministic,
//! never less correct.

use crate::packet::{HttpRequestInfo, MirrorPacket};
use bytes::{BufMut, Bytes, BytesMut};
use std::time::{SystemTime, UNIX_EPOCH};

/// Hardcoded VXLAN Network Identifier — the Rust port of
/// `encapsulateVXLAN`'s `vni := uint32(1000)`. Not configurable in the Go
/// source (no config field threads a VNI through); characterized as-is.
const VXLAN_VNI: u32 = 1000;

/// VXLAN header (8 bytes: I-flag + reserved, then a 24-bit VNI in a
/// 32-bit field) prepended to `packet.data` — the Rust port of
/// `encapsulateVXLAN`. Infallible (the Go source's `error` return is
/// always `nil`; this signature drops it rather than carry a dead `Ok`
/// branch).
#[must_use]
pub fn encapsulate_vxlan(packet: &MirrorPacket) -> Bytes {
    let mut header = BytesMut::with_capacity(8 + packet.data.len());
    header.put_u8(0x08); // Flags (I flag set)
    header.put_bytes(0, 3); // reserved
    header.put_u32(VXLAN_VNI << 8); // VNI occupies the top 3 of these 4 bytes
    header.extend_from_slice(&packet.data);
    header.freeze()
}

/// Minimal 4-byte GRE header (version/flags left zero, EtherType IPv4)
/// prepended to `packet.data` — the Rust port of `encapsulateGRE`. The Go
/// source's own doc comment calls this "simplified" (no checksum, key, or
/// sequence-number fields); characterized as-is.
#[must_use]
pub fn encapsulate_gre(packet: &MirrorPacket) -> Bytes {
    let mut header = BytesMut::with_capacity(4 + packet.data.len());
    header.put_u16(0x0000); // version/flags
    header.put_u16(0x0800); // EtherType: IPv4
    header.extend_from_slice(&packet.data);
    header.freeze()
}

/// 8-byte ERSPAN Type II header (version 1 / VLAN 0, session ID 1,
/// 20-bit pseudo-unique index) prepended to `packet.data` — the Rust port
/// of `encapsulateERSPAN`. See the module doc for the index-source
/// deviation (packet timestamp, not clock-at-encapsulation-time).
#[must_use]
pub fn encapsulate_erspan(packet: &MirrorPacket) -> Bytes {
    let unix_secs = packet
        .timestamp
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let index = (unix_secs & 0xFFFFF) as u32;

    let mut header = BytesMut::with_capacity(8 + packet.data.len());
    header.put_u16(0x1000); // Version(4)=1 | VLAN(12)=0
    header.put_u16(0x0001); // COS(3)|EN(2)|T(1)|SessionID(10)=1
    header.put_u32(index); // Reserved(12)=0 | Index(20)
    header.extend_from_slice(&packet.data);
    header.freeze()
}

/// Dispatches to the configured protocol's encapsulation, falling back to
/// the raw, un-encapsulated payload for any unrecognized protocol string
/// — the Rust port of `sendPacket`'s `switch m.protocol { ... default:
/// encapsulated = packet.Data }` (characterized as-is: an unrecognized
/// protocol is not an error in the Go source).
#[must_use]
pub fn encapsulate(protocol: &str, packet: &MirrorPacket) -> Bytes {
    match protocol {
        "VXLAN" => encapsulate_vxlan(packet),
        "GRE" => encapsulate_gre(packet),
        "ERSPAN" => encapsulate_erspan(packet),
        _ => packet.data.clone(),
    }
}

/// Minimal HTTP/1.x request+response-status text framing — the Rust port
/// of `encodeHTTP`. See the module doc for the header-ordering deviation.
#[must_use]
pub fn encode_http(info: &HttpRequestInfo, status_code: u16, body: &[u8]) -> Bytes {
    let mut buf = BytesMut::new();
    buf.extend_from_slice(format!("{} {} {}\r\n", info.method, info.path, info.proto).as_bytes());

    for (key, value) in &info.headers {
        buf.extend_from_slice(format!("{key}: {value}\r\n").as_bytes());
    }

    buf.extend_from_slice(format!("\r\nHTTP/1.1 {status_code}\r\n").as_bytes());
    buf.extend_from_slice(format!("Content-Length: {}\r\n\r\n", body.len()).as_bytes());
    buf.extend_from_slice(body);
    buf.freeze()
}

/// Formats an RFC 3339 nanosecond timestamp matching Go's
/// `time.RFC3339Nano` layout closely enough for Suricata EVE JSON
/// consumption (`YYYY-MM-DDTHH:MM:SS.fffffffff+00:00`) — used by
/// [`prepare_suricata_data`] for both the envelope and top-level
/// timestamp fields, exactly as the Go source reuses one formatted string
/// for both.
fn format_rfc3339_nano(ts: SystemTime) -> String {
    let dur = ts.duration_since(UNIX_EPOCH).unwrap_or_default();
    let secs = dur.as_secs();
    let nanos = dur.subsec_nanos();
    let days = secs / 86400;
    let rem = secs % 86400;
    let (hour, minute, second) = (rem / 3600, (rem % 3600) / 60, rem % 60);

    // Civil-from-days (Howard Hinnant's algorithm) — avoids pulling in a
    // date/time crate for one formatting helper used only here.
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

    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}.{nanos:09}+00:00")
}

/// Builds the Suricata EVE-JSON-formatted, newline-terminated envelope
/// sent to the Suricata IDS/IPS connection — the Rust port of
/// `prepareSuricataData`. Infallible: unlike the Go source's
/// `json.Marshal` (which can theoretically fail on a cyclic/unsupported
/// `interface{}` value and falls back to raw `packet.Data`), serializing
/// an already-validated `serde_json::Value`-backed structure cannot fail,
/// so this port has no fallback branch to characterize — a documented,
/// non-behavioral simplification of unreachable Go error-handling.
#[must_use]
pub fn prepare_suricata_data(packet: &MirrorPacket) -> Bytes {
    let ts = format_rfc3339_nano(packet.timestamp);
    let unix_nanos = packet
        .timestamp
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);

    let mut envelope = serde_json::json!({
        "timestamp": ts,
        "protocol": packet.protocol,
        "metadata": packet.metadata,
        "data_size": packet.data.len(),
    });
    if let Some(src) = packet.source {
        envelope["src_ip"] = serde_json::Value::String(src.to_string());
    }
    if let Some(dst) = packet.destination {
        envelope["dst_ip"] = serde_json::Value::String(dst.to_string());
    }

    let cluster = packet
        .metadata
        .get("cluster_id")
        .cloned()
        .unwrap_or(serde_json::Value::Null);
    let user = packet
        .metadata
        .get("user_id")
        .cloned()
        .unwrap_or(serde_json::Value::Null);

    let eve_log = serde_json::json!({
        "timestamp": ts,
        "flow_id": format!("{unix_nanos:x}"),
        "event_type": "mirror",
        "mirror": envelope,
        "sasewaddle": {
            "cluster": cluster,
            "user": user,
        },
    });

    // serde_json::Value serialization is infallible — see the doc above.
    let mut json_bytes = serde_json::to_vec(&eve_log).unwrap_or_default();
    json_bytes.push(b'\n');
    Bytes::from(json_bytes)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;
    use std::time::Duration;

    fn packet_with(protocol: &str, data: &[u8]) -> MirrorPacket {
        MirrorPacket {
            timestamp: UNIX_EPOCH + Duration::from_secs(1_700_000_000),
            source: None,
            destination: None,
            protocol: protocol.to_string(),
            data: Bytes::copy_from_slice(data),
            metadata: HashMap::new(),
        }
    }

    #[test]
    fn vxlan_header_matches_the_go_byte_layout() {
        let packet = packet_with("TCP", b"payload");
        let out = encapsulate_vxlan(&packet);
        // flags=0x08, reserved x3, VNI(1000<<8)=0x0003E800 big-endian.
        assert_eq!(&out[..8], &[0x08, 0x00, 0x00, 0x00, 0x00, 0x03, 0xE8, 0x00]);
        assert_eq!(&out[8..], b"payload");
    }

    #[test]
    fn gre_header_matches_the_go_byte_layout() {
        let packet = packet_with("TCP", b"xy");
        let out = encapsulate_gre(&packet);
        assert_eq!(&out[..4], &[0x00, 0x00, 0x08, 0x00]);
        assert_eq!(&out[4..], b"xy");
    }

    #[test]
    fn erspan_header_matches_the_go_byte_layout_for_a_fixed_timestamp() {
        let packet = packet_with("TCP", b"z");
        let out = encapsulate_erspan(&packet);
        assert_eq!(&out[0..2], &[0x10, 0x00]);
        assert_eq!(&out[2..4], &[0x00, 0x01]);
        // index = 1_700_000_000 & 0xFFFFF
        let expected_index: u32 = (1_700_000_000u64 & 0xFFFFF) as u32;
        assert_eq!(&out[4..8], &expected_index.to_be_bytes());
        assert_eq!(&out[8..], b"z");
    }

    #[test]
    fn erspan_index_upper_bits_are_always_zero() {
        let packet = packet_with("TCP", b"");
        let out = encapsulate_erspan(&packet);
        let index = u32::from_be_bytes([out[4], out[5], out[6], out[7]]);
        assert_eq!(index & !0xFFFFF, 0, "reserved upper 12 bits must be zero");
    }

    #[test]
    fn encapsulate_dispatches_by_protocol_name() {
        let packet = packet_with("TCP", b"p");
        assert_eq!(encapsulate("VXLAN", &packet), encapsulate_vxlan(&packet));
        assert_eq!(encapsulate("GRE", &packet), encapsulate_gre(&packet));
        assert_eq!(encapsulate("ERSPAN", &packet), encapsulate_erspan(&packet));
    }

    #[test]
    fn encapsulate_falls_back_to_raw_data_for_unknown_protocol() {
        let packet = packet_with("TCP", b"raw-passthrough");
        assert_eq!(encapsulate("RAW", &packet), packet.data);
        assert_eq!(encapsulate("", &packet), packet.data);
    }

    #[test]
    fn encode_http_matches_the_go_text_layout() {
        let info = HttpRequestInfo {
            method: "GET".to_string(),
            url: "http://example.com/health".to_string(),
            path: "/health".to_string(),
            proto: "HTTP/1.1".to_string(),
            headers: vec![("X-Trace".to_string(), "abc".to_string())],
            user_agent: "test-agent".to_string(),
        };
        let out = encode_http(&info, 200, b"ok");
        let text = String::from_utf8(out.to_vec()).unwrap();
        assert_eq!(
            text,
            "GET /health HTTP/1.1\r\nX-Trace: abc\r\n\r\nHTTP/1.1 200\r\nContent-Length: 2\r\n\r\nok"
        );
    }

    #[test]
    fn encode_http_with_no_headers_and_empty_body() {
        let info = HttpRequestInfo {
            method: "GET".to_string(),
            path: "/".to_string(),
            proto: "HTTP/1.1".to_string(),
            ..Default::default()
        };
        let out = encode_http(&info, 204, b"");
        let text = String::from_utf8(out.to_vec()).unwrap();
        assert_eq!(
            text,
            "GET / HTTP/1.1\r\n\r\nHTTP/1.1 204\r\nContent-Length: 0\r\n\r\n"
        );
    }

    #[test]
    fn encode_http_preserves_duplicate_header_keys_in_order() {
        let info = HttpRequestInfo {
            method: "GET".to_string(),
            path: "/".to_string(),
            proto: "HTTP/1.1".to_string(),
            headers: vec![
                ("Set-Cookie".to_string(), "a=1".to_string()),
                ("Set-Cookie".to_string(), "b=2".to_string()),
            ],
            ..Default::default()
        };
        let out = encode_http(&info, 200, b"");
        let text = String::from_utf8(out.to_vec()).unwrap();
        assert!(text.contains("Set-Cookie: a=1\r\nSet-Cookie: b=2\r\n"));
    }

    #[test]
    fn prepare_suricata_data_produces_newline_terminated_eve_json() {
        let mut metadata = HashMap::new();
        metadata.insert(
            "cluster_id".to_string(),
            serde_json::Value::String("cluster-1".to_string()),
        );
        metadata.insert(
            "user_id".to_string(),
            serde_json::Value::String("user-9".to_string()),
        );
        let packet = MirrorPacket {
            metadata,
            ..packet_with("TCP", b"abc")
        };

        let out = prepare_suricata_data(&packet);
        assert_eq!(*out.last().unwrap(), b'\n');

        let without_newline = &out[..out.len() - 1];
        let parsed: serde_json::Value = serde_json::from_slice(without_newline).unwrap();
        assert_eq!(parsed["event_type"], "mirror");
        assert_eq!(parsed["mirror"]["protocol"], "TCP");
        assert_eq!(parsed["mirror"]["data_size"], 3);
        assert_eq!(parsed["sasewaddle"]["cluster"], "cluster-1");
        assert_eq!(parsed["sasewaddle"]["user"], "user-9");
    }

    #[test]
    fn prepare_suricata_data_includes_src_dst_ip_only_when_present() {
        let packet = packet_with("UDP", b"d");
        let out = prepare_suricata_data(&packet);
        let parsed: serde_json::Value = serde_json::from_slice(&out[..out.len() - 1]).unwrap();
        assert!(parsed["mirror"].get("src_ip").is_none());
        assert!(parsed["mirror"].get("dst_ip").is_none());

        let mut with_ips = packet_with("UDP", b"d");
        with_ips.source = Some("10.0.0.1".parse().unwrap());
        with_ips.destination = Some("10.0.0.2".parse().unwrap());
        let out2 = prepare_suricata_data(&with_ips);
        let parsed2: serde_json::Value = serde_json::from_slice(&out2[..out2.len() - 1]).unwrap();
        assert_eq!(parsed2["mirror"]["src_ip"], "10.0.0.1");
        assert_eq!(parsed2["mirror"]["dst_ip"], "10.0.0.2");
    }

    #[test]
    fn prepare_suricata_data_nulls_missing_cluster_and_user() {
        let packet = packet_with("TCP", b"x");
        let out = prepare_suricata_data(&packet);
        let parsed: serde_json::Value = serde_json::from_slice(&out[..out.len() - 1]).unwrap();
        assert!(parsed["sasewaddle"]["cluster"].is_null());
        assert!(parsed["sasewaddle"]["user"].is_null());
    }
}
