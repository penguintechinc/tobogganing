//! Diagnostic probe implementations, ported from
//! `engines/testserver/internal/protocols` (Go). This PR ports the "easy"
//! protocols (HTTP/1.1+HTTP/2, raw TCP, TLS, raw UDP, DNS) with parity
//! tests; ICMP/traceroute/`*_trace` (shell-out probes) and the SSH banner
//! probe are deferred to a follow-up PR — see `deferred` and the PR
//! description's tracking list.

pub mod deferred;
pub mod http;
pub mod tcp;
pub mod tls_provider;
pub mod udp;

pub use http::{test_http, HttpTestRequest, HttpTestResult};
pub use tcp::{test_tcp, TcpTestRequest, TcpTestResult};
pub use udp::{test_udp, UdpTestRequest, UdpTestResult};
