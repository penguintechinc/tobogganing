//! RFC 8484 DNS-over-HTTPS (wireformat) client that forwards a single
//! question to the P3 resolver pool (`engines/netsvcs-dns`). Builds the
//! query via `hickory_proto`, `POST`s the raw wire bytes
//! (`application/dns-message`, no per-query auth — matches the P3 DoH data
//! path) to a round-robined upstream, and parses the wire-format response
//! back into a `Message`.

use hickory_proto::op::{Message, MessageType, OpCode, Query};
use hickory_proto::rr::{Name, RecordType};
use node_agent_core::{AgentError, Result};
use std::sync::atomic::{AtomicUsize, Ordering};

/// DoH wireformat client round-robining across the configured upstream
/// `/dns-query` URLs. Holds one shared `reqwest::Client` (connection pool)
/// for the lifetime of the DNS module.
pub(super) struct DohClient {
    http: reqwest::Client,
    upstreams: Vec<String>,
    next: AtomicUsize,
}

impl DohClient {
    /// Builds a client targeting `upstreams` (each a full
    /// `https://.../dns-query` URL, per `DnsConfig::upstream_doh_urls`).
    pub(super) fn new(upstreams: Vec<String>) -> Result<Self> {
        // Idempotent — see `node_agent_transport::install_crypto_provider`.
        // Called here (not only in the top-level module `run()`) so this
        // client also works when constructed directly, e.g. in tests.
        node_agent_transport::install_crypto_provider()?;
        let http = reqwest::Client::builder()
            .build()
            .map_err(|err| AgentError::Transport(err.to_string()))?;
        Ok(Self {
            http,
            upstreams,
            next: AtomicUsize::new(0),
        })
    }

    fn next_upstream(&self) -> Option<&str> {
        if self.upstreams.is_empty() {
            return None;
        }
        let index = self.next.fetch_add(1, Ordering::Relaxed) % self.upstreams.len();
        Some(self.upstreams[index].as_str())
    }

    /// Resolves `name`/`rtype` against the next upstream in the rotation,
    /// returning the parsed wire-format response message.
    pub(super) async fn lookup(&self, name: &Name, rtype: RecordType) -> Result<Message> {
        let upstream = self
            .next_upstream()
            .ok_or_else(|| AgentError::Config("no DoH upstreams configured".to_string()))?;

        // RFC 8484 SS6.1: DoH clients using "application/dns-message"
        // SHOULD use a DNS ID of 0 on every request to maximize HTTP cache
        // friendliness; the original client's query ID is restored on the
        // response by the caller before it's sent back to the LAN client.
        let mut query = Message::new(0, MessageType::Query, OpCode::Query);
        query.metadata.recursion_desired = true;
        query.add_query(Query::query(name.clone(), rtype));
        let wire = query
            .to_vec()
            .map_err(|err| AgentError::Transport(err.to_string()))?;

        let response = self
            .http
            .post(upstream)
            .header(reqwest::header::CONTENT_TYPE, "application/dns-message")
            .header(reqwest::header::ACCEPT, "application/dns-message")
            .body(wire)
            .send()
            .await
            .map_err(|err| AgentError::Transport(err.to_string()))?;

        if !response.status().is_success() {
            return Err(AgentError::Transport(format!(
                "DoH upstream {upstream} returned HTTP {}",
                response.status()
            )));
        }

        let body = response
            .bytes()
            .await
            .map_err(|err| AgentError::Transport(err.to_string()))?;
        Message::from_vec(&body).map_err(|err| AgentError::Transport(err.to_string()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use hickory_proto::rr::RData;
    use std::net::Ipv4Addr;
    use std::str::FromStr;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpListener;

    /// Spins up a minimal loopback HTTP/1.1 responder that decodes the
    /// posted DNS wire-format query, asserts it matches `expected_name`,
    /// and replies with a synthesized wire-format A-record answer — enough
    /// to exercise the real request/response wireformat round-trip without
    /// a live DoH server.
    async fn spawn_mock_doh(expected_name: &'static str) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();

        tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut buf = vec![0u8; 4096];
            let n = stream.read(&mut buf).await.unwrap();
            let request = &buf[..n];

            // Split HTTP headers from body on the blank-line boundary.
            let sep = b"\r\n\r\n";
            let header_end = request.windows(sep.len()).position(|w| w == sep).unwrap() + sep.len();
            let body = &request[header_end..];

            let query = Message::from_vec(body).unwrap();
            assert_eq!(query.queries.len(), 1);
            assert_eq!(query.queries[0].name().to_ascii(), expected_name);

            let mut answer_msg = Message::new(0, MessageType::Response, OpCode::Query);
            answer_msg.metadata.response_code = hickory_proto::op::ResponseCode::NoError;
            answer_msg.add_query(query.queries[0].clone());
            answer_msg.add_answer(hickory_proto::rr::Record::from_rdata(
                Name::from_str(expected_name).unwrap(),
                300,
                RData::A(Ipv4Addr::new(192, 0, 2, 1).into()),
            ));
            let wire = answer_msg.to_vec().unwrap();

            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/dns-message\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                wire.len()
            );
            stream.write_all(response.as_bytes()).await.unwrap();
            stream.write_all(&wire).await.unwrap();
            stream.shutdown().await.ok();
        });

        format!("http://{addr}/dns-query")
    }

    #[tokio::test]
    async fn lookup_round_trips_wireformat_query_and_response() {
        let upstream = spawn_mock_doh("www.example.com.").await;
        let client = DohClient::new(vec![upstream]).unwrap();

        let name = Name::from_str("www.example.com.").unwrap();
        let response = client.lookup(&name, RecordType::A).await.unwrap();

        assert_eq!(
            response.metadata.response_code,
            hickory_proto::op::ResponseCode::NoError
        );
        assert_eq!(response.answers.len(), 1);
    }

    #[tokio::test]
    async fn lookup_without_upstreams_fails_closed() {
        let client = DohClient::new(Vec::new()).unwrap();
        let name = Name::from_str("example.com.").unwrap();
        let err = client.lookup(&name, RecordType::A).await.unwrap_err();
        assert!(matches!(err, AgentError::Config(_)));
    }

    #[tokio::test]
    async fn lookup_round_robins_across_upstreams() {
        let a = spawn_mock_doh("round-robin.example.").await;
        let b = spawn_mock_doh("round-robin.example.").await;
        let client = DohClient::new(vec![a, b]).unwrap();
        let name = Name::from_str("round-robin.example.").unwrap();

        // Each mock server only accepts a single connection; two
        // successful lookups prove both upstreams were exercised.
        client.lookup(&name, RecordType::A).await.unwrap();
        client.lookup(&name, RecordType::A).await.unwrap();
    }
}
