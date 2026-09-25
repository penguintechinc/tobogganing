"""Seam 4 (P5-E2E/D): resolver/agent IOC lookup via the real gRPC CheckIOC RPC
reflects the threatintel block decision, end-to-end from feed ingest through
the wire; the RPC fails open (not an aborted call) when the blocklist lookup
itself errors — an outage in threatintel must never take resolver query
processing down with it.

This chains seam 3's ingest->curate pipeline into seam 1/2's gRPC harness,
covering the full stack a node-agent's `ioc:read`-scoped machine-JWT
actually exercises in production (agents/node-agent/crates/agent/src/run.rs
requests `ioc:read` in its bootstrap scope specifically for this RPC).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from penguin_dal import AsyncDB

from hub_api.auth.jwt import encode_access_token
from hub_api.auth.machine_claims import build_machine_claims
from hub_api.modules.netsvcs.grpc.server import ENROLLMENT_TENANT
from hub_api.modules.threatintel.blocklist.curator import BlocklistCurator
from hub_api.modules.threatintel.blocklist.store import BlocklistStore
from hub_api.modules.threatintel.feeds.ingestor import ingest_feed_source
from proto.netsvcs.v1 import manager_pb2

from .conftest import FakeFeedSession


async def _machine_token(manager_grpc_harness, sub_id: str) -> str:
    """Mint an ioc:read-scoped machine-JWT verifiable by the harness's servicer."""
    claims = build_machine_claims(
        sub_id=sub_id, node_type="dns_resolver", tenant=ENROLLMENT_TENANT, iss="tobogganing"
    )
    return await encode_access_token(claims, manager_grpc_harness.key_provider, ttl_hours=1)


@pytest.mark.asyncio
async def test_check_ioc_grpc_reflects_curated_feed_indicator_end_to_end(
    manager_grpc_harness, real_dal: AsyncDB
) -> None:
    """Full stack: CSV feed ingest -> BlocklistCurator -> BlocklistStore ->
    real gRPC CheckIOC blocks the listed domain, allows an unlisted one."""
    tenant_id = str(uuid4())
    csv_body = "domain,confidence\ngrpc-seam4.example.com,90\n"
    session = FakeFeedSession(200, csv_body)

    stats = await ingest_feed_source(
        real_dal, tenant_id, "csv", "https://feeds.example.com/seam4.csv", session
    )
    assert stats == {"added": 1, "updated": 0, "errors": 0}

    # Curate into the SAME cache the running ManagerServicer's IOCChecker reads.
    store = BlocklistStore(cache=manager_grpc_harness.cache)
    curator = BlocklistCurator(real_dal, store)
    curation_stats = await curator.curate(tenant_id)
    assert curation_stats.stored == 1

    token = await _machine_token(manager_grpc_harness, "resolver-seam4")

    with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True):
        blocked_response = await manager_grpc_harness.stub.CheckIOC(
            manager_pb2.CheckIOCRequest(api_version="v1", domain="grpc-seam4.example.com", ip=""),
            metadata=[("authorization", f"Bearer {token}")],
        )
        assert blocked_response.blocked is True
        assert blocked_response.feed_source == "csv"
        assert blocked_response.severity == "critical"  # confidence=90 -> critical

        clean_response = await manager_grpc_harness.stub.CheckIOC(
            manager_pb2.CheckIOCRequest(api_version="v1", domain="clean-seam4.example.com", ip=""),
            metadata=[("authorization", f"Bearer {token}")],
        )
        assert clean_response.blocked is False
        assert clean_response.feed_source == ""


@pytest.mark.asyncio
async def test_check_ioc_grpc_fails_open_on_blocklist_lookup_error(manager_grpc_harness) -> None:
    """CheckIOC returns blocked=False (fails open), not an internal-error
    abort, when the underlying blocklist lookup raises."""
    token = await _machine_token(manager_grpc_harness, "resolver-seam4-failopen")

    with (
        patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True),
        patch.object(
            manager_grpc_harness.servicer.ioc_checker,
            "check_domain",
            new=AsyncMock(side_effect=Exception("blocklist backend unavailable")),
        ),
    ):
        response = await manager_grpc_harness.stub.CheckIOC(
            manager_pb2.CheckIOCRequest(api_version="v1", domain="explodes.example.com", ip=""),
            metadata=[("authorization", f"Bearer {token}")],
        )

    assert response.blocked is False
    assert response.feed_source == ""


@pytest.mark.asyncio
async def test_check_ioc_grpc_requires_ioc_read_scope(manager_grpc_harness) -> None:
    """A machine-JWT without ioc:read scope is rejected before any blocklist
    lookup happens (never a fail-open path substituting for missing auth)."""
    claims = {
        "sub": "resolver:no-scope",
        "iss": "tobogganing",
        "aud": "headend",
        "tenant": ENROLLMENT_TENANT,
        "scope": "",  # no ioc:read
    }
    token = await encode_access_token(claims, manager_grpc_harness.key_provider, ttl_hours=1)

    import grpc

    with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled", return_value=True):
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await manager_grpc_harness.stub.CheckIOC(
                manager_pb2.CheckIOCRequest(api_version="v1", domain="anything.example.com", ip=""),
                metadata=[("authorization", f"Bearer {token}")],
            )
    assert exc_info.value.code() == grpc.StatusCode.PERMISSION_DENIED
