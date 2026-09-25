"""Seam 1 (P5-E2E/D, highest blast radius): machine-JWT enroll -> RegisterServer
-> hub issues ServerConfig + refresh_token -> refresh single-use replay is
rejected.

Exercises the full wire path (real gRPC over an ephemeral port, real_dal —
not MagicMock) rather than the direct servicer method calls
test_netsvcs_grpc.py / test_netsvcs_grpc_hardening.py already cover, so this
catches what those structurally cannot: wire (de)serialization and the real
ConfigService/ServerManager query path together, in one round trip.

Regression: squawk-merge P2 gRPC hardening (M2 JTI caching, M4 fail-closed
cache-set, replay detection) — re-verified here against a real_dal-backed
server over a real socket, not a mocked cache.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import grpc
import pytest
from penguin_dal import AsyncDB

from hub_api.modules.netsvcs.grpc.server import ENROLLMENT_TENANT
from proto.netsvcs.v1 import manager_pb2

BOOTSTRAP_TOKEN = "test-p5-e2e-bootstrap-token"  # nosec B105 - test fixture literal, not a real secret


@pytest.mark.asyncio
async def test_enroll_issues_config_matching_seeded_zone_and_refresh_replay_is_rejected(
    manager_grpc_harness, real_dal: AsyncDB, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RegisterServer over real gRPC returns a ServerConfig reflecting seeded
    DB state (what a real node-agent/resolver applies on enrollment); then a
    replay of the already-superseded refresh token is rejected, not
    silently accepted."""
    monkeypatch.setenv("ENROLLMENT_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)

    # Seed a zone + record under the shared resolver-fleet ("enrollment")
    # tenant — RegisterServer's config must reflect this, the same shape a
    # node-agent/resolver applies on enroll.
    now = datetime.now(timezone.utc)
    zone_id = str(uuid4())
    await real_dal.dns_zones.async_insert(
        id=zone_id,
        tenant=ENROLLMENT_TENANT,
        name="enroll-seam.example.com",
        visibility="public",
        description=None,
        created_at=now,
        updated_at=now,
    )
    await real_dal.dns_records.async_insert(
        id=str(uuid4()),
        zone_id=zone_id,
        tenant=ENROLLMENT_TENANT,
        name="www",
        type="A",
        value="192.0.2.50",
        ttl=300,
        priority=None,
        weight=None,
        port=None,
        created_at=now,
        updated_at=now,
    )

    stub = manager_grpc_harness.stub
    metadata = [("authorization", f"Bearer {BOOTSTRAP_TOKEN}")]

    response = await stub.RegisterServer(
        manager_pb2.RegisterServerRequest(
            api_version="v1", hostname="resolver-seam-1", version="1.2.3"
        ),
        metadata=metadata,
    )

    # === enroll -> config: the shape a node-agent/resolver applies ===
    assert response.server_id
    assert response.jwt
    assert response.refresh_token
    assert response.refresh_token != response.jwt

    config = response.config
    assert len(config.zones) == 1
    zone = config.zones[0]
    assert zone.name == "enroll-seam.example.com"
    assert zone.visibility == "public"
    assert len(zone.records) == 1
    record = zone.records[0]
    assert record.name == "www"
    assert record.type == "A"
    assert record.value == "192.0.2.50"
    assert record.ttl == 300
    assert config.cache_settings.ttl == 300
    assert config.cache_settings.enabled is True

    first_refresh_token = response.refresh_token
    server_id = response.server_id

    # === refresh: first use succeeds and rotates the token ===
    refresh_response = await stub.RefreshToken(
        manager_pb2.RefreshTokenRequest(api_version="v1", server_id=server_id),
        metadata=[("authorization", f"Bearer {first_refresh_token}")],
    )
    assert refresh_response.jwt

    # === regression: squawk-merge P2 gRPC hardening (M2/M4) ===
    # Replaying the now-superseded original refresh token must be rejected
    # over the real wire (single-use JTI check), not silently accepted.
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await stub.RefreshToken(
            manager_pb2.RefreshTokenRequest(api_version="v1", server_id=server_id),
            metadata=[("authorization", f"Bearer {first_refresh_token}")],
        )
    assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_register_server_rejects_missing_bootstrap_token_over_real_wire(
    manager_grpc_harness,
) -> None:
    """RegisterServer without a bootstrap token is rejected UNAUTHENTICATED
    over the real wire (fail-closed enrollment gate — never silently issue
    a machine-JWT to an unauthenticated caller)."""
    with pytest.raises(grpc.aio.AioRpcError) as exc_info:
        await manager_grpc_harness.stub.RegisterServer(
            manager_pb2.RegisterServerRequest(
                api_version="v1", hostname="resolver-seam-1-noauth", version="1.0.0"
            )
        )
    assert exc_info.value.code() == grpc.StatusCode.UNAUTHENTICATED
