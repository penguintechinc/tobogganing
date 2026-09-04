//! Local `:53` DNS forwarder: a `hickory-server` [`RequestHandler`] that
//! forwards every query to the P3 DoH resolver pool, in front of a bounded
//! TTL response cache and optional IOC-based domain blocking.

mod cache;
mod doh;

use cache::{CacheKey, CachedAnswer, ResponseCache};
use doh::DohClient;
use hickory_proto::op::{Header, HeaderCounts, MessageType, Metadata, OpCode, ResponseCode};
use hickory_proto::rr::{Name, Record, RecordType};
use hickory_server::net::runtime::Time;
use hickory_server::server::{Request, RequestHandler, ResponseHandler, ResponseInfo, Server};
use hickory_server::zone_handler::MessageResponseBuilder;
use node_agent_core::{AgentError, ControlPlaneClient, DnsConfig, Result};
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;
use tokio::net::{TcpListener, UdpSocket};
use tokio_util::sync::CancellationToken;

/// Runs the `:53` UDP+TCP forwarder on `cfg.listen_addr` until `shutdown`
/// is cancelled.
pub(super) async fn run(
    cfg: DnsConfig,
    client: Arc<dyn ControlPlaneClient>,
    shutdown: CancellationToken,
) -> Result<()> {
    tracing::info!(module = "netsvcs-edge.dns", listen_addr = %cfg.listen_addr, "starting");

    let addr: SocketAddr = cfg.listen_addr.parse().map_err(|err| {
        AgentError::Config(format!(
            "invalid netsvcs-edge dns listen_addr {:?}: {err}",
            cfg.listen_addr
        ))
    })?;

    let handler = EdgeDnsHandler {
        doh: DohClient::new(cfg.upstream_doh_urls.clone())?,
        cache: ResponseCache::new(cfg.cache_enabled, cfg.cache_max_entries, cfg.cache_ttl_secs),
        client,
        ioc_filtering: cfg.ioc_filtering,
    };

    let udp = UdpSocket::bind(addr).await?;
    let tcp = TcpListener::bind(addr).await?;

    let mut server = Server::new(handler);
    server.register_socket(udp);
    server.register_listener(tcp, Duration::from_secs(10), 4096);

    tokio::select! {
        _ = shutdown.cancelled() => {
            if let Err(err) = server.shutdown_gracefully().await {
                tracing::warn!(error = %err, "netsvcs-edge dns server shutdown reported an error");
            }
        }
        result = server.block_until_done() => {
            if let Err(err) = result {
                tracing::error!(error = %err, "netsvcs-edge dns server task failed");
            }
        }
    }

    tracing::info!(module = "netsvcs-edge.dns", "stopped");
    Ok(())
}

/// Forwards every DNS query it receives to the P3 DoH resolver pool,
/// consulting the local cache first and — when `ioc_filtering` is enabled —
/// the control plane's threat-intel feed before forwarding.
struct EdgeDnsHandler {
    doh: DohClient,
    cache: ResponseCache,
    client: Arc<dyn ControlPlaneClient>,
    ioc_filtering: bool,
}

impl EdgeDnsHandler {
    /// Resolves `name`/`rtype`, in order: IOC block check (fail-open on
    /// lookup error), cache, then the DoH upstream on a miss.
    async fn resolve(&self, name: &Name, rtype: RecordType) -> CachedAnswer {
        if self.ioc_filtering {
            let domain = name.to_ascii();
            let indicator = domain.trim_end_matches('.');
            match self.client.check_ioc(indicator).await {
                Ok(verdict) if verdict.malicious => {
                    tracing::warn!(domain = %indicator, "blocked malicious domain via IOC filtering");
                    return CachedAnswer {
                        response_code: ResponseCode::NXDomain,
                        answers: Vec::new(),
                        authorities: Vec::new(),
                        additionals: Vec::new(),
                    };
                }
                Ok(_) => {}
                Err(err) => {
                    tracing::warn!(error = %err, domain = %indicator, "IOC lookup failed; failing open");
                }
            }
        }

        let key: CacheKey = (name.clone(), rtype);
        if let Some(cached) = self.cache.get(&key).await {
            return cached;
        }

        match self.doh.lookup(name, rtype).await {
            Ok(msg) => {
                let answer = CachedAnswer {
                    response_code: msg.metadata.response_code,
                    answers: msg.answers,
                    authorities: msg.authorities,
                    // The upstream's OPT pseudo-record is transport-local
                    // to that hop and must not be relayed verbatim.
                    additionals: msg
                        .additionals
                        .into_iter()
                        .filter(|r| r.record_type() != RecordType::OPT)
                        .collect::<Vec<Record>>(),
                };
                self.cache.put(key, answer.clone()).await;
                answer
            }
            Err(err) => {
                tracing::warn!(error = %err, name = %name, "DoH upstream lookup failed");
                CachedAnswer {
                    response_code: ResponseCode::ServFail,
                    answers: Vec::new(),
                    authorities: Vec::new(),
                    additionals: Vec::new(),
                }
            }
        }
    }
}

#[async_trait::async_trait]
impl RequestHandler for EdgeDnsHandler {
    async fn handle_request<R: ResponseHandler, T: Time>(
        &self,
        request: &Request,
        mut response_handle: R,
    ) -> ResponseInfo {
        let info = match request.request_info() {
            Ok(info) => info,
            Err(err) => {
                tracing::warn!(error = %err, "malformed DNS request");
                return send_error(request, ResponseCode::FormErr, &mut response_handle).await;
            }
        };

        if request.metadata.message_type != MessageType::Query
            || request.metadata.op_code != OpCode::Query
        {
            return send_error(request, ResponseCode::NotImp, &mut response_handle).await;
        }

        let name: Name = info.query.name().clone().into();
        let rtype = info.query.query_type();
        let answer = self.resolve(&name, rtype).await;

        let mut metadata = Metadata::response_from_request(&request.metadata);
        metadata.response_code = answer.response_code;

        let response = MessageResponseBuilder::from_message_request(request).build(
            metadata,
            answer.answers.iter(),
            answer.authorities.iter(),
            std::iter::empty(),
            answer.additionals.iter(),
        );

        match response_handle.send_response(response).await {
            Ok(info) => info,
            Err(err) => {
                tracing::warn!(error = %err, "failed to send DNS response");
                ResponseInfo::from(Header {
                    metadata,
                    counts: HeaderCounts::default(),
                })
            }
        }
    }
}

/// Builds and sends a records-free error response for `code`, falling back
/// to a bare header if the send itself fails.
async fn send_error<R: ResponseHandler>(
    request: &Request,
    code: ResponseCode,
    response_handle: &mut R,
) -> ResponseInfo {
    let response =
        MessageResponseBuilder::from_message_request(request).error_msg(&request.metadata, code);
    match response_handle.send_response(response).await {
        Ok(info) => info,
        Err(err) => {
            tracing::warn!(error = %err, "failed to send DNS error response");
            let mut metadata = Metadata::response_from_request(&request.metadata);
            metadata.response_code = code;
            ResponseInfo::from(Header {
                metadata,
                counts: HeaderCounts::default(),
            })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use async_trait::async_trait;
    use hickory_proto::op::{MessageType as ProtoMessageType, Query};
    use hickory_proto::rr::RData;
    use hickory_server::net::xfer::Protocol;
    use hickory_server::server::Request;
    use node_agent_core::{
        EnrollRequest, EnrollResponse, Heartbeat, IocVerdict, Metrics, NodeConfig, RefreshResponse,
    };
    use std::net::Ipv4Addr;
    use std::str::FromStr;

    /// A `ControlPlaneClient` mock whose only meaningful behavior is
    /// `check_ioc`, configurable to return a verdict or an error, for
    /// exercising the IOC-block and fail-open paths without a live server.
    struct MockClient {
        verdict: std::sync::Mutex<Option<Result<IocVerdict>>>,
    }

    impl MockClient {
        fn malicious() -> Self {
            Self {
                verdict: std::sync::Mutex::new(Some(Ok(IocVerdict {
                    indicator: "bad.example.".to_string(),
                    malicious: true,
                    source: Some("test-feed".to_string()),
                }))),
            }
        }

        fn erroring() -> Self {
            Self {
                verdict: std::sync::Mutex::new(Some(Err(AgentError::Transport(
                    "ioc feed unreachable".to_string(),
                )))),
            }
        }
    }

    #[async_trait]
    impl ControlPlaneClient for MockClient {
        async fn enroll(&self, _req: EnrollRequest) -> Result<EnrollResponse> {
            unimplemented!("not exercised by these tests")
        }
        async fn heartbeat(&self, _hb: Heartbeat) -> Result<()> {
            unimplemented!("not exercised by these tests")
        }
        async fn get_config(
            &self,
            _node_id: &str,
            _current_version: i64,
        ) -> Result<Option<NodeConfig>> {
            unimplemented!("not exercised by these tests")
        }
        async fn report_metrics(&self, _m: Metrics) -> Result<()> {
            unimplemented!("not exercised by these tests")
        }
        async fn refresh_token(&self, _refresh_token: &str) -> Result<RefreshResponse> {
            unimplemented!("not exercised by these tests")
        }
        async fn check_ioc(&self, _indicator: &str) -> Result<IocVerdict> {
            self.verdict
                .lock()
                .unwrap()
                .take()
                .expect("check_ioc called more than once in this test")
        }
    }

    fn mock_request(name: &str, rtype: RecordType) -> Request {
        let query = Query::query(Name::from_str(name).unwrap(), rtype);
        let metadata = Metadata::new(1, ProtoMessageType::Query, OpCode::Query);
        let message = hickory_server::zone_handler::MessageRequest::mock(metadata, query);
        Request::from_message(message, "127.0.0.1:5353".parse().unwrap(), Protocol::Udp).unwrap()
    }

    #[tokio::test]
    async fn ioc_filtering_blocks_malicious_domain_without_querying_upstream() {
        let handler = EdgeDnsHandler {
            // No upstreams configured — if the IOC block didn't short-circuit,
            // the DoH lookup would fail with a "no upstreams" config error
            // instead of returning NXDomain, so this also proves ordering.
            doh: DohClient::new(Vec::new()).unwrap(),
            cache: ResponseCache::new(true, 100, 300),
            client: Arc::new(MockClient::malicious()),
            ioc_filtering: true,
        };

        let name = Name::from_str("bad.example.").unwrap();
        let answer = handler.resolve(&name, RecordType::A).await;
        assert_eq!(answer.response_code, ResponseCode::NXDomain);
        assert!(answer.answers.is_empty());
    }

    #[tokio::test]
    async fn ioc_lookup_error_fails_open_to_servfail_without_upstream() {
        let handler = EdgeDnsHandler {
            doh: DohClient::new(Vec::new()).unwrap(),
            cache: ResponseCache::new(true, 100, 300),
            client: Arc::new(MockClient::erroring()),
            ioc_filtering: true,
        };

        let name = Name::from_str("maybe-fine.example.").unwrap();
        let answer = handler.resolve(&name, RecordType::A).await;
        // Fails open past the IOC check (no block), then the DoH lookup
        // itself fails (no upstreams configured) -> ServFail, not NXDomain.
        assert_eq!(answer.response_code, ResponseCode::ServFail);
    }

    #[tokio::test]
    async fn cache_hit_short_circuits_resolve() {
        let handler = EdgeDnsHandler {
            doh: DohClient::new(Vec::new()).unwrap(),
            cache: ResponseCache::new(true, 100, 300),
            client: Arc::new(MockClient::erroring()),
            ioc_filtering: false,
        };

        let name = Name::from_str("cached.example.").unwrap();
        let key: CacheKey = (name.clone(), RecordType::A);
        handler
            .cache
            .put(
                key,
                CachedAnswer {
                    response_code: ResponseCode::NoError,
                    answers: vec![Record::from_rdata(
                        name.clone(),
                        300,
                        RData::A(Ipv4Addr::new(203, 0, 113, 9).into()),
                    )],
                    authorities: Vec::new(),
                    additionals: Vec::new(),
                },
            )
            .await;

        let answer = handler.resolve(&name, RecordType::A).await;
        assert_eq!(answer.response_code, ResponseCode::NoError);
        assert_eq!(answer.answers.len(), 1);
    }

    #[tokio::test]
    async fn handle_request_returns_formerr_for_zero_queries() {
        let handler = EdgeDnsHandler {
            doh: DohClient::new(Vec::new()).unwrap(),
            cache: ResponseCache::new(false, 0, 300),
            client: Arc::new(MockClient::erroring()),
            ioc_filtering: false,
        };

        // A metadata-only request (no queries) fails `request_info()`'s
        // exactly-one-query invariant, exercising the FormErr path.
        let metadata = Metadata::new(7, ProtoMessageType::Query, OpCode::Query);
        let message = hickory_server::zone_handler::MessageRequest {
            metadata,
            queries: hickory_server::zone_handler::Queries::new(Vec::new()),
            answers: Vec::new(),
            authorities: Vec::new(),
            additionals: Vec::new(),
            signature: None,
            edns: None,
        };
        let request =
            Request::from_message(message, "127.0.0.1:5353".parse().unwrap(), Protocol::Udp)
                .unwrap();

        let info = handler
            .handle_request::<NoopResponseHandler, hickory_server::net::runtime::TokioTime>(
                &request,
                NoopResponseHandler,
            )
            .await;
        assert_eq!(info.response_code, ResponseCode::FormErr);
    }

    /// A `ResponseHandler` that records the last response sent, for
    /// asserting on `handle_request`'s outcome without a real socket.
    #[derive(Clone, Default)]
    struct NoopResponseHandler;

    #[async_trait]
    impl ResponseHandler for NoopResponseHandler {
        async fn send_response<'a>(
            &mut self,
            response: hickory_server::zone_handler::MessageResponse<
                '_,
                'a,
                impl Iterator<Item = &'a Record> + Send + 'a,
                impl Iterator<Item = &'a Record> + Send + 'a,
                impl Iterator<Item = &'a Record> + Send + 'a,
                impl Iterator<Item = &'a Record> + Send + 'a,
            >,
        ) -> std::result::Result<ResponseInfo, hickory_server::net::NetError> {
            Ok(ResponseInfo::from(Header {
                metadata: *response.metadata(),
                counts: HeaderCounts::default(),
            }))
        }
    }

    #[test]
    fn resolve_name_conversion_smoke() {
        let req = mock_request("smoke.example.", RecordType::A);
        let info = req.request_info().unwrap();
        let name: Name = info.query.name().clone().into();
        assert_eq!(name.to_ascii(), "smoke.example.");
    }

    #[tokio::test]
    async fn run_rejects_an_unparsable_listen_addr_before_binding_anything() {
        let cfg = DnsConfig {
            listen_addr: "not-a-valid-socket-address".to_string(),
            ..DnsConfig::default()
        };
        let err = run(
            cfg,
            Arc::new(MockClient::erroring()),
            CancellationToken::new(),
        )
        .await
        .expect_err("an unparsable listen_addr must error before any bind attempt");
        assert!(matches!(err, AgentError::Config(_)));
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn run_binds_udp_and_tcp_then_shuts_down_gracefully_on_cancel() {
        let cfg = DnsConfig {
            listen_addr: "127.0.0.1:0".to_string(),
            ..DnsConfig::default()
        };
        let shutdown = CancellationToken::new();
        let shutdown_clone = shutdown.clone();
        tokio::spawn(async move {
            tokio::time::sleep(std::time::Duration::from_millis(50)).await;
            shutdown_clone.cancel();
        });

        let result = tokio::time::timeout(
            std::time::Duration::from_secs(10),
            run(cfg, Arc::new(MockClient::erroring()), shutdown),
        )
        .await
        .expect("run must return promptly after cancellation, not hang");
        assert!(result.is_ok());
    }
}
