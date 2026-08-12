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
