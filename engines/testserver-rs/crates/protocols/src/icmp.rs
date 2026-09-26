//! Port of `engines/testserver/internal/protocols/icmp.go`'s `TestICMP`.
//! **Confirmed by source analysis: this shells out to the system `ping`/
//! `traceroute` binaries via a subprocess and regex/string-parses stdout —
//! it does NOT use raw ICMP sockets.** This port preserves that exactly
//! (`tokio::process::Command` in place of `os/exec`).
//!
//! Output-parsing/statistics (`parse_ping_latencies`, `apply_ping_stats`,
//! `parse_icmp_traceroute_hops`) are pure, synchronous functions tested
//! directly against captured fixture text in `#[cfg(test)]` below — the
//! only part of this module that touches a real subprocess is
//! `crate::shellout::run_command`, so none of these tests depend on `ping`/
//! `traceroute` being installed on the test runner.
//!
//! Field names and two deliberately-permissive parity quirks are preserved
//! from the Go source (the migration contract):
//!   1. `testPing`'s "command ran but zero packets parsed" branch sets
//!      `success: false` with `error: "No packets received"` and returns
//!      `Ok` (not `Err`) — only a hard command failure (non-zero exit /
//!      spawn failure) is an `Err`.
//!   2. `testTraceroute`'s ICMP-protocol traceroute branch reports
//!      `success: true` unconditionally once the command exits zero, even
//!      when zero hop lines were parsed out of the output.

use crate::shellout::run_command;
use serde::{Deserialize, Serialize};
use testserver_core::ApiError;

#[derive(Debug, Clone, Default, Deserialize)]
pub struct IcmpTestRequest {
    pub target: String,
    #[serde(default)]
    pub protocol: String,
    #[serde(default)]
    pub protocol_detail: String,
    #[serde(default)]
    pub count: i64,
    #[serde(default)]
    pub timeout: i64,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct IcmpTestResult {
    pub target: String,
    pub protocol: String,
    pub success: bool,
    pub packets_sent: i64,
    pub packets_received: i64,
    pub packet_loss_percent: f64,
    /// Average latency across all received replies.
    pub latency_ms: f64,
    pub min_latency_ms: f64,
    pub max_latency_ms: f64,
    pub jitter_ms: f64,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub error: String,
    /// Populated only for the `traceroute` protocol.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub hops: Vec<String>,
}

/// Removes URL scheme and port from `target` — port of Go's
/// `extractHostname`. Naive colon-based port stripping, same caveat as the
/// `parse_target` helpers in `tcp.rs`/`udp.rs` (not IPv6-bracket-aware).
fn extract_hostname(target: &str) -> String {
    if target.contains("://") {
        if let Ok(parsed) = url::Url::parse(target) {
            return parsed.host_str().unwrap_or("").to_string();
        }
    }
    if let Some((host, _rest)) = target.split_once(':') {
        return host.to_string();
    }
    target.to_string()
}

/// Builds the platform-specific `ping` argument vector — port of
/// `testPing`'s `runtime.GOOS` switch. `std::env::consts::OS` reports
/// `"macos"` where Go's `runtime.GOOS` reports `"darwin"`; the mapping is
/// otherwise 1:1.
fn ping_args(target: &str, count: i64, timeout: i64) -> Result<Vec<String>, ApiError> {
    match std::env::consts::OS {
        "linux" => Ok(vec![
            "-c".to_string(),
            count.to_string(),
            "-W".to_string(),
            timeout.to_string(),
            target.to_string(),
        ]),
        "macos" => Ok(vec![
            "-c".to_string(),
            count.to_string(),
            "-W".to_string(),
            (timeout * 1000).to_string(),
            target.to_string(),
        ]),
        "windows" => Ok(vec![
            "-n".to_string(),
            count.to_string(),
            "-w".to_string(),
            (timeout * 1000).to_string(),
            target.to_string(),
        ]),
        other => Err(ApiError::TestExecution(format!(
            "unsupported platform for ping: {other}"
        ))),
    }
}

/// Builds the platform-specific traceroute argument vector for the ICMP
/// `protocol=traceroute` branch — port of `testTraceroute`'s `runtime.GOOS`
/// switch (distinct from, and simpler than, `trace.rs`'s TCP/UDP/HTTP trace
/// variants).
fn icmp_traceroute_args(
    target: &str,
    timeout: i64,
) -> Result<(&'static str, Vec<String>), ApiError> {
    match std::env::consts::OS {
        "linux" | "macos" => Ok((
            "traceroute",
            vec![
                "-w".to_string(),
                timeout.to_string(),
                "-m".to_string(),
                "30".to_string(),
                target.to_string(),
            ],
        )),
        "windows" => Ok((
            "tracert",
            vec![
                "-w".to_string(),
                (timeout * 1000).to_string(),
                "-h".to_string(),
                "30".to_string(),
                target.to_string(),
            ],
        )),
        other => Err(ApiError::TestExecution(format!(
            "unsupported platform for traceroute: {other}"
        ))),
    }
}

/// Extracts every `time=<N>` (or `time<N>`) latency sample from `ping`
/// output — port of the manual `strings.Contains`/`strings.Split` parsing
/// in `testPing` (the Go source does not use `regexp` for this).
fn parse_ping_latencies(output: &str) -> Vec<f64> {
    let mut latencies = Vec::new();
    for line in output.lines() {
        if let Some(idx) = line.find("time=") {
            let after = &line[idx + "time=".len()..];
            if let Some(time_str) = after.split_whitespace().next() {
                if let Ok(latency) = time_str.parse::<f64>() {
                    latencies.push(latency);
                }
            }
        }
    }
    latencies
}

/// Applies packet-loss/latency/jitter statistics to `result` from raw
/// `ping` output — the pure core of `testPing`, split out so it is fully
/// unit-testable on fixture text. Mirrors Go exactly, including the
/// "command succeeded but zero latencies parsed" branch staying a
/// non-error, `success: false` result.
fn apply_ping_stats(result: &mut IcmpTestResult, count: i64, output: &str) {
    let latencies = parse_ping_latencies(output);
    result.packets_sent = count;
    result.packets_received = latencies.len() as i64;
    result.packet_loss_percent = (count - latencies.len() as i64) as f64 / count as f64 * 100.0;

    if latencies.is_empty() {
        result.success = false;
        result.error = "No packets received".to_string();
        return;
    }

    result.success = true;
    let sum: f64 = latencies.iter().sum();
    let min = latencies.iter().cloned().fold(f64::INFINITY, f64::min);
    let max = latencies.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    result.latency_ms = sum / latencies.len() as f64;
    result.min_latency_ms = min;
    result.max_latency_ms = max;

    if latencies.len() > 1 {
        let jitter_sum: f64 = latencies.windows(2).map(|w| (w[1] - w[0]).abs()).sum();
        result.jitter_ms = jitter_sum / (latencies.len() - 1) as f64;
    }
}

/// Filters traceroute output down to hop lines — port of `testTraceroute`'s
/// inline filter (distinct from, and simpler than, `trace::parse_traceroute_output`:
/// no "Hop N: " reformatting, raw trimmed lines are kept as-is).
fn parse_icmp_traceroute_hops(output: &str) -> Vec<String> {
    output
        .lines()
        .map(str::trim)
        .filter(|line| {
            !line.is_empty() && !line.starts_with("traceroute") && !line.starts_with("Tracing")
        })
        .map(str::to_string)
        .collect()
}

async fn test_ping(target: &str, count: i64, timeout: i64) -> Result<IcmpTestResult, ApiError> {
    let mut result = IcmpTestResult {
        target: target.to_string(),
        protocol: "ping".to_string(),
        ..Default::default()
    };

    let args = ping_args(target, count, timeout)?;
    let output = run_command("ping", &args).await;
    let combined = output.combined();

    if !output.success {
        result.error = format!("ping command failed\nOutput: {combined}");
        return Err(ApiError::TestExecution(result.error));
    }

    apply_ping_stats(&mut result, count, &combined);
    Ok(result)
}

async fn test_icmp_traceroute(target: &str, timeout: i64) -> Result<IcmpTestResult, ApiError> {
    let mut result = IcmpTestResult {
        target: target.to_string(),
        protocol: "traceroute".to_string(),
        ..Default::default()
    };

    let (program, args) = icmp_traceroute_args(target, timeout)?;
    let output = run_command(program, &args).await;
    let combined = output.combined();

    if !output.success {
        result.error = format!("traceroute command failed\nOutput: {combined}");
        return Err(ApiError::TestExecution(result.error));
    }

    // Deliberately permissive parity quirk: success is unconditional once
    // the command exits zero, even if zero hop lines were parsed.
    result.hops = parse_icmp_traceroute_hops(&combined);
    result.success = true;
    Ok(result)
}

/// Runs an ICMP-family diagnostic (`ping` or `traceroute`) against
/// `req.target` — port of `TestICMP`. `protocol_detail` is used when
/// `protocol` is empty (compatibility field, same convention as `http.rs`/
/// `tcp.rs`/`udp.rs`); an empty result still defaults to `"ping"`.
pub async fn test_icmp(req: IcmpTestRequest) -> Result<IcmpTestResult, ApiError> {
    let mut protocol = if !req.protocol.is_empty() {
        req.protocol.clone()
    } else {
        req.protocol_detail.clone()
    };
    if protocol.is_empty() {
        protocol = "ping".to_string();
    }

    let target = extract_hostname(&req.target);
    let count = if req.count == 0 { 4 } else { req.count };
    let timeout = if req.timeout == 0 { 10 } else { req.timeout };

    match protocol.as_str() {
        "ping" => test_ping(&target, count, timeout).await,
        "traceroute" => test_icmp_traceroute(&target, timeout).await,
        other => Err(ApiError::TestExecution(format!(
            "unsupported protocol: {other}"
        ))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------
    // extract_hostname
    // -----------------------------------------------------------------

    #[test]
    fn extract_hostname_strips_scheme() {
        assert_eq!(extract_hostname("https://localhost"), "localhost");
    }

    #[test]
    fn extract_hostname_strips_port() {
        assert_eq!(extract_hostname("localhost:8080"), "localhost");
    }

    #[test]
    fn extract_hostname_passes_through_plain_host() {
        assert_eq!(extract_hostname("8.8.8.8"), "8.8.8.8");
    }

    // -----------------------------------------------------------------
    // parse_ping_latencies / apply_ping_stats — fixture text, no real ping
    // -----------------------------------------------------------------

    const PING_FIXTURE_LINUX: &str = "PING 127.0.0.1 (127.0.0.1) 56(84) bytes of data.\n\
64 bytes from 127.0.0.1: icmp_seq=1 ttl=64 time=0.032 ms\n\
64 bytes from 127.0.0.1: icmp_seq=2 ttl=64 time=0.048 ms\n\
64 bytes from 127.0.0.1: icmp_seq=3 ttl=64 time=0.041 ms\n\
\n\
--- 127.0.0.1 ping statistics ---\n\
3 packets transmitted, 3 received, 0% packet loss, time 2043ms\n\
rtt min/avg/max/mdev = 0.032/0.040/0.048/0.007 ms\n";

    #[test]
    fn parse_ping_latencies_extracts_all_samples() {
        let latencies = parse_ping_latencies(PING_FIXTURE_LINUX);
        assert_eq!(latencies, vec![0.032, 0.048, 0.041]);
    }

    #[test]
    fn apply_ping_stats_computes_avg_min_max_jitter() {
        let mut result = IcmpTestResult::default();
        apply_ping_stats(&mut result, 3, PING_FIXTURE_LINUX);
        assert!(result.success);
        assert_eq!(result.packets_sent, 3);
        assert_eq!(result.packets_received, 3);
        assert_eq!(result.packet_loss_percent, 0.0);
        assert!((result.min_latency_ms - 0.032).abs() < 1e-9);
        assert!((result.max_latency_ms - 0.048).abs() < 1e-9);
        assert!(result.jitter_ms > 0.0);
        assert!(result.error.is_empty());
    }

    #[test]
    fn apply_ping_stats_partial_loss_computes_percent() {
        let fixture = "64 bytes from 127.0.0.1: icmp_seq=1 ttl=64 time=1.0 ms\n";
        let mut result = IcmpTestResult::default();
        apply_ping_stats(&mut result, 4, fixture);
        assert!(result.success);
        assert_eq!(result.packets_received, 1);
        assert_eq!(result.packet_loss_percent, 75.0);
        // Single sample: jitter stays at its default zero (no adjacent pair).
        assert_eq!(result.jitter_ms, 0.0);
    }

    #[test]
    fn apply_ping_stats_zero_samples_is_success_false_but_no_error_thrown() {
        // Parity quirk: command succeeded (exit 0) but no "time=" lines
        // matched — success:false with a specific error string, but this
        // is a value returned from a pure function, never an Err/panic.
        let fixture = "PING 127.0.0.1: Destination Host Unreachable\n";
        let mut result = IcmpTestResult::default();
        apply_ping_stats(&mut result, 2, fixture);
        assert!(!result.success);
        assert_eq!(result.error, "No packets received");
        assert_eq!(result.packets_received, 0);
        assert_eq!(result.packet_loss_percent, 100.0);
    }

    // -----------------------------------------------------------------
    // parse_icmp_traceroute_hops — fixture text
    // -----------------------------------------------------------------

    #[test]
    fn parse_icmp_traceroute_hops_filters_header_and_blank_lines() {
        let fixture = "traceroute to 127.0.0.1 (127.0.0.1), 30 hops max\n\
 1  10.0.0.1  1.234 ms\n\
 2  10.0.0.2  2.345 ms\n\
\n";
        let hops = parse_icmp_traceroute_hops(fixture);
        assert_eq!(hops, vec!["1  10.0.0.1  1.234 ms", "2  10.0.0.2  2.345 ms"]);
    }

    #[test]
    fn parse_icmp_traceroute_hops_filters_windows_tracing_header() {
        let fixture = "Tracing route to 127.0.0.1 over a maximum of 30 hops\n\
  1    <1 ms    <1 ms    <1 ms  127.0.0.1\n";
        let hops = parse_icmp_traceroute_hops(fixture);
        assert_eq!(hops, vec!["1    <1 ms    <1 ms    <1 ms  127.0.0.1"]);
    }

    #[test]
    fn parse_icmp_traceroute_hops_empty_output_yields_empty_vec() {
        assert!(parse_icmp_traceroute_hops("").is_empty());
    }

    // -----------------------------------------------------------------
    // ping_args / icmp_traceroute_args — pure argument construction
    // -----------------------------------------------------------------

    #[test]
    fn ping_args_matches_current_platform_convention() {
        let args = ping_args("127.0.0.1", 4, 10).expect("this platform must be supported");
        // We don't assert the exact flag set across all three platforms in
        // one run (only one `std::env::consts::OS` is active), but the
        // target must always be the final argument, and count/timeout must
        // be present as strings.
        assert_eq!(args.last().unwrap(), "127.0.0.1");
        assert!(args.contains(&"4".to_string()));
    }

    #[test]
    fn icmp_traceroute_args_targets_correct_binary_for_platform() {
        let (program, args) = icmp_traceroute_args("127.0.0.1", 5).expect("supported platform");
        assert!(program == "traceroute" || program == "tracert");
        assert_eq!(args.last().unwrap(), "127.0.0.1");
    }

    // -----------------------------------------------------------------
    // test_icmp — protocol dispatch (no subprocess touched on this path)
    // -----------------------------------------------------------------

    #[tokio::test]
    async fn unsupported_protocol_returns_error_without_touching_a_subprocess() {
        let req = IcmpTestRequest {
            target: "127.0.0.1".into(),
            protocol: "flood".into(),
            count: 1,
            timeout: 2,
            ..Default::default()
        };
        assert!(test_icmp(req).await.is_err());
    }

    #[tokio::test]
    async fn protocol_detail_fallback_used_when_protocol_empty() {
        // Exercises the protocol-defaulting branch; "traceroute" here means
        // this deterministically runs the (possibly-missing) `traceroute`
        // binary, which either errors (Err) or degrades to a permissive
        // success — either way this must not depend on it existing.
        let req = IcmpTestRequest {
            target: "127.0.0.1".into(),
            protocol_detail: "traceroute".into(),
            timeout: 1,
            ..Default::default()
        };
        let _ = test_icmp(req).await; // must not panic regardless of outcome
    }

    #[tokio::test]
    async fn empty_protocol_and_zero_defaults_dispatch_to_ping() {
        let req = IcmpTestRequest {
            target: "127.0.0.1".into(),
            count: 0,
            timeout: 0,
            ..Default::default()
        };
        // Defaults (count=4, timeout=10) get applied before dispatch to
        // test_ping; whether `ping` exists on the runner or not, this must
        // resolve to a definite Ok/Err, never hang or panic.
        let _ = test_icmp(req).await;
    }
}
