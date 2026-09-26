//! Diagnostic probe implementations, ported from
//! `engines/testserver/internal/protocols` (Go). HTTP/1.1+HTTP/2, raw TCP,
//! TLS, raw UDP, DNS, ICMP (`ping`/`traceroute` shell-out), and the
//! `http_trace`/`tcp_trace`/`traceroute`/`udp_trace` family all have parity
//! tests. Only the SSH banner probe remains deferred to a follow-up PR (see
//! `tcp.rs`'s `ssh` protocol branch, which returns
//! `ApiError::NotImplemented`).

pub mod http;
pub mod icmp;
mod shellout;
pub mod tcp;
pub mod tls_provider;
pub mod trace;
pub mod udp;

pub use http::{test_http, HttpTestRequest, HttpTestResult};
pub use icmp::{test_icmp, IcmpTestRequest, IcmpTestResult};
pub use tcp::{test_tcp, TcpTestRequest, TcpTestResult};
pub use trace::{
    test_http_trace, test_tcp_trace, test_traceroute, test_udp_trace, HopDetail, HttpTraceRequest,
    TcpTraceRequest, TraceResult, TracerouteRequest, UdpTraceRequest,
};
pub use udp::{test_udp, UdpTestRequest, UdpTestResult};
