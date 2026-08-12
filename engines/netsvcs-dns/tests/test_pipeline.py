"""Tests for the ResolvePipeline."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.pipeline import ResolvePipeline, ResolvePipelineConfig
from app.resolver import DNSResolver
from app.router import SelectiveRouter, TokenClaims
from app.cache import CacheManager


@pytest.fixture
def pipeline() -> ResolvePipeline:
    """Create a pipeline with mocked components."""
    resolver = AsyncMock(spec=DNSResolver)
    router = MagicMock(spec=SelectiveRouter)
    cache = AsyncMock(spec=CacheManager)

    return ResolvePipeline(
        resolver=resolver, router=router, cache=cache, config=ResolvePipelineConfig()
    )


@pytest.mark.asyncio
async def test_resolve_query_cache_hit(pipeline: ResolvePipeline) -> None:
    """Test that cache hits short-circuit resolution."""
    cached_result = {
        "Status": 0,
        "Question": [{"name": "example.com", "type": "A"}],
        "Answer": [{"name": "example.com", "type": "A", "TTL": 300, "data": "1.2.3.4"}],
    }

    pipeline.cache.get.return_value = cached_result

    result = await pipeline.resolve_query("example.com", "A")

    assert result == cached_result
    pipeline.cache.get.assert_called_once_with("example.com", "A")
    pipeline.resolver.resolve.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_query_cache_miss(pipeline: ResolvePipeline) -> None:
    """Test cache miss leads to resolution."""
    upstream_result = {
        "Status": 0,
        "Question": [{"name": "example.com", "type": "A"}],
        "Answer": [{"name": "example.com", "type": "A", "TTL": 300, "data": "1.2.3.4"}],
    }

    pipeline.cache.get.return_value = None
    pipeline.router.should_serve_zone.return_value = True
    pipeline.router.get_zone_records.return_value = None
    pipeline.resolver.resolve.return_value = upstream_result

    result = await pipeline.resolve_query("example.com", "A")

    assert result == upstream_result
    pipeline.cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_query_ioc_blocked(pipeline: ResolvePipeline) -> None:
    """Test IOC-blocked domains return NXDOMAIN."""
    pipeline.cache.get.return_value = None

    # Mock ioc_check to return True (blocked)
    with patch.object(pipeline, "ioc_check", return_value=True):
        result = await pipeline.resolve_query("malware.example.com", "A")

    assert result["Status"] == 3  # NXDOMAIN
    assert result["Answer"] == []
    pipeline.resolver.resolve.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_query_split_horizon_denied(pipeline: ResolvePipeline) -> None:
    """Test split-horizon permission denial returns REFUSED."""
    pipeline.cache.get.return_value = None

    # Mock IOC check to pass
    with patch.object(pipeline, "ioc_check", return_value=False):
        # Mock router to deny access
        pipeline.router.should_serve_zone.return_value = False

        result = await pipeline.resolve_query("internal.example.com", "A")

    assert result["Status"] == 5  # REFUSED
    assert result["Answer"] == []
    pipeline.resolver.resolve.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_query_custom_zone(pipeline: ResolvePipeline) -> None:
    """Test custom zone resolution."""
    zone_records = [{"name": "api.internal.com", "type": "A", "ttl": 300, "value": "10.0.0.1"}]
    custom_result = {
        "Status": 0,
        "Question": [{"name": "api.internal.com", "type": "A"}],
        "Answer": [{"name": "api.internal.com", "type": "A", "TTL": 300, "data": "10.0.0.1"}],
    }

    pipeline.cache.get.return_value = None
    pipeline.router.should_serve_zone.return_value = True
    pipeline.router.get_zone_records.return_value = zone_records
    pipeline.resolver.resolve_custom_zone.return_value = custom_result

    with patch.object(pipeline, "ioc_check", return_value=False):
        result = await pipeline.resolve_query("api.internal.com", "A")

    assert result == custom_result
    pipeline.resolver.resolve_custom_zone.assert_called_once_with(
        "api.internal.com", "A", zone_records
    )
    pipeline.resolver.resolve.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_query_upstream_recursion(pipeline: ResolvePipeline) -> None:
    """Test upstream public DNS recursion."""
    upstream_result = {
        "Status": 0,
        "Question": [{"name": "example.com", "type": "A"}],
        "Answer": [{"name": "example.com", "type": "A", "TTL": 300, "data": "93.184.216.34"}],
    }

    pipeline.cache.get.return_value = None
    pipeline.router.should_serve_zone.return_value = True
    pipeline.router.get_zone_records.return_value = None
    pipeline.resolver.resolve.return_value = upstream_result

    with patch.object(pipeline, "ioc_check", return_value=False):
        result = await pipeline.resolve_query("example.com", "A")

    assert result == upstream_result
    pipeline.resolver.resolve.assert_called_once_with("example.com", "A")


@pytest.mark.asyncio
async def test_resolve_query_degraded_mode_public_only(pipeline: ResolvePipeline) -> None:
    """Test degraded mode serves only public zones."""
    pipeline.cache.get.return_value = None

    with patch.object(pipeline, "ioc_check", return_value=False):
        # In degraded mode, public zones are served but internal zones are denied
        pipeline.router.should_serve_zone.return_value = False

        result = await pipeline.resolve_query(
            "internal.example.com", "A", mode="degraded"
        )

    assert result["Status"] == 5  # REFUSED
    pipeline.resolver.resolve.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_query_no_cache_on_error(pipeline: ResolvePipeline) -> None:
    """Test that failed queries are not cached."""
    error_result = {
        "Status": 2,  # SERVFAIL
        "Question": [{"name": "nonexistent.example.com", "type": "A"}],
        "Answer": [],
    }

    pipeline.cache.get.return_value = None
    pipeline.router.should_serve_zone.return_value = True
    pipeline.router.get_zone_records.return_value = None
    pipeline.resolver.resolve.return_value = error_result

    with patch.object(pipeline, "ioc_check", return_value=False):
        result = await pipeline.resolve_query("nonexistent.example.com", "A")

    assert result["Status"] == 2
    # Cache.set should NOT be called for non-NOERROR responses
    pipeline.cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_query_with_token(pipeline: ResolvePipeline) -> None:
    """Test resolve with DNS client token."""
    token = "test_token_123"
    upstream_result = {
        "Status": 0,
        "Question": [{"name": "example.com", "type": "A"}],
        "Answer": [{"name": "example.com", "type": "A", "TTL": 300, "data": "1.2.3.4"}],
    }

    pipeline.cache.get.return_value = None
    pipeline.router.should_serve_zone.return_value = True
    pipeline.router.get_zone_records.return_value = None
    pipeline.resolver.resolve.return_value = upstream_result

    # Mock the methods as mocks so we can assert on them
    ioc_mock = AsyncMock(return_value=False)
    claims_mock = AsyncMock(return_value=None)

    with patch.object(pipeline, "ioc_check", ioc_mock):
        with patch.object(pipeline, "_claims_for_token", claims_mock):
            result = await pipeline.resolve_query("example.com", "A", token=token)

    assert result == upstream_result
    # _claims_for_token should have been called with the token
    claims_mock.assert_called_once_with(token)


@pytest.mark.asyncio
async def test_ioc_check_stub(pipeline: ResolvePipeline) -> None:
    """Test IOC check stub (returns False for S2)."""
    # S2 stub: always returns False (not blocked)
    result = await pipeline.ioc_check("example.com")
    assert result is False

    result = await pipeline.ioc_check("malware.example.com")
    assert result is False


@pytest.mark.asyncio
async def test_claims_for_token_stub(pipeline: ResolvePipeline) -> None:
    """Test claims-for-token stub (returns None for S2)."""
    # S2 stub: always returns None (no claims)
    result = await pipeline._claims_for_token(None)
    assert result is None

    result = await pipeline._claims_for_token("test_token")
    assert result is None


# S3 Tests: Control-plane wiring


@pytest.mark.asyncio
async def test_ioc_check_with_manager_client(stub_server_addr: str) -> None:
    """Test IOC check via control-plane CheckIOC gRPC (fail-open on error)."""
    import tempfile
    from app.manager_client import ManagerClient

    with tempfile.TemporaryDirectory() as tmpdir:
        manager_client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Enroll
        enrolled = await manager_client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True

        resolver = AsyncMock(spec=DNSResolver)
        router = MagicMock(spec=SelectiveRouter)
        cache = AsyncMock(spec=CacheManager)

        pipeline = ResolvePipeline(
            resolver=resolver,
            router=router,
            cache=cache,
            manager_client=manager_client,
            config=ResolvePipelineConfig(),
        )

        # Test blocked domain
        blocked_result = await pipeline.ioc_check("blocked.example.com")
        assert blocked_result is True

        # Test clean domain
        clean_result = await pipeline.ioc_check("clean.example.com")
        assert clean_result is False

        await manager_client.close()


@pytest.mark.asyncio
async def test_ioc_check_fail_open(stub_server_addr: str) -> None:
    """Test IOC check fails open on control-plane error."""
    import tempfile
    from app.manager_client import ManagerClient

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create client with invalid address (will fail on check_ioc)
        manager_client = ManagerClient(
            grpc_addr="127.0.0.1:1",  # Invalid
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Manually set enrolled state (skip real enrollment)
        manager_client.server_id = "test-server"
        manager_client.jwt = "test-jwt"

        resolver = AsyncMock(spec=DNSResolver)
        router = MagicMock(spec=SelectiveRouter)
        cache = AsyncMock(spec=CacheManager)

        pipeline = ResolvePipeline(
            resolver=resolver,
            router=router,
            cache=cache,
            manager_client=manager_client,
            config=ResolvePipelineConfig(),
        )

        # Even with invalid address, ioc_check should return False (fail-open)
        result = await pipeline.ioc_check("any.domain")
        assert result is False

        await manager_client.close()


@pytest.mark.asyncio
async def test_validate_token_with_manager_client(stub_server_addr: str) -> None:
    """Test token validation via control-plane ValidateToken gRPC."""
    import tempfile
    from app.manager_client import ManagerClient

    with tempfile.TemporaryDirectory() as tmpdir:
        manager_client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Enroll
        enrolled = await manager_client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True

        resolver = AsyncMock(spec=DNSResolver)
        router = MagicMock(spec=SelectiveRouter)
        cache = AsyncMock(spec=CacheManager)

        pipeline = ResolvePipeline(
            resolver=resolver,
            router=router,
            cache=cache,
            manager_client=manager_client,
            config=ResolvePipelineConfig(),
        )

        # Test valid token
        claims = await pipeline._claims_for_token("test-token-z1")
        assert claims is not None
        assert "z1" in claims.allowed_zone_ids

        # Test invalid token
        invalid_claims = await pipeline._claims_for_token("unknown-token")
        assert invalid_claims is None

        await manager_client.close()


@pytest.mark.asyncio
async def test_token_scoped_zones(stub_server_addr: str) -> None:
    """Test that tokens with allowed_zone_ids can only access their zones."""
    import tempfile
    from app.manager_client import ManagerClient

    with tempfile.TemporaryDirectory() as tmpdir:
        manager_client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Enroll
        enrolled = await manager_client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True

        # Setup router with zones that have IDs for tenant scoping.
        # Use internal zones with no team restrictions to test zone scoping
        # independently from team-based visibility logic.
        router = SelectiveRouter()
        router.load_zones([
            {
                "id": "z1",  # Zone ID for control-plane scoping
                "name": "example.com",
                "visibility": "public",
                "allowed_teams": [],
                "records": [],
            },
            {
                "id": "z2",  # Zone ID for control-plane scoping
                "name": "internal.example.com",
                "visibility": "internal",  # Internal with no team restrictions
                "allowed_teams": [],  # No team restrictions, any token allowed
                "records": [],
            },
        ])

        resolver = AsyncMock(spec=DNSResolver)
        cache = AsyncMock(spec=CacheManager)

        pipeline = ResolvePipeline(
            resolver=resolver,
            router=router,
            cache=cache,
            manager_client=manager_client,
            config=ResolvePipelineConfig(),
        )

        # Token with access to z1 only
        claims_z1 = await pipeline._claims_for_token("test-token-z1")
        assert claims_z1 is not None
        assert claims_z1.allowed_zone_ids == ["z1"]

        # Should be able to access z1 (public)
        can_access_z1 = router.check_zone_permission("example.com", claims_z1)
        assert can_access_z1 is True

        # Should NOT be able to access z2 (not in allowed_zone_ids)
        can_access_z2 = router.check_zone_permission("internal.example.com", claims_z1)
        assert can_access_z2 is False

        # Token with access to all zones
        claims_all = await pipeline._claims_for_token("test-token-all")
        assert claims_all is not None
        assert set(claims_all.allowed_zone_ids) == {"z1", "z2"}

        # Should be able to access both
        can_access_z1_all = router.check_zone_permission("example.com", claims_all)
        assert can_access_z1_all is True

        can_access_z2_all = router.check_zone_permission("internal.example.com", claims_all)
        assert can_access_z2_all is True

        await manager_client.close()


@pytest.mark.asyncio
async def test_invalid_token_no_access(stub_server_addr: str) -> None:
    """Test that invalid/unvalidatable tokens get no access (fail-closed)."""
    import tempfile
    from app.manager_client import ManagerClient

    with tempfile.TemporaryDirectory() as tmpdir:
        manager_client = ManagerClient(
            grpc_addr=stub_server_addr,
            tls_ca_path=None,
            insecure_dev_flag=True,
            cache_dir=tmpdir,
            server_name="dns-test",
        )

        # Enroll
        enrolled = await manager_client.enroll(
            bootstrap_token="test-bootstrap",
            hostname="test-host",
            version="0.1.0",
        )
        assert enrolled is True

        resolver = AsyncMock(spec=DNSResolver)
        router = MagicMock(spec=SelectiveRouter)
        cache = AsyncMock(spec=CacheManager)

        pipeline = ResolvePipeline(
            resolver=resolver,
            router=router,
            cache=cache,
            manager_client=manager_client,
            config=ResolvePipelineConfig(),
        )

        # Invalid token should return None (no claims, fail-closed)
        invalid_claims = await pipeline._claims_for_token("bad-signature-token")
        assert invalid_claims is None

        await manager_client.close()
