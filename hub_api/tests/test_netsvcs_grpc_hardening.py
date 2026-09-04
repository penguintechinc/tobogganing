"""gRPC hardening tests for netsvcs module — error disclosure, cache fail-closed."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import grpc
import pytest

from hub_api.modules.netsvcs.grpc.server import ManagerServicer
from proto.netsvcs.v1 import manager_pb2


@pytest.mark.asyncio
async def test_validate_token_verbose_error_not_exposed() -> None:
    """Test ValidateToken does not expose exception details in the response."""
    from unittest.mock import patch

    # Mock dependencies
    db_mock = MagicMock()
    cache_mock = AsyncMock()
    key_provider_mock = MagicMock()

    # Set up database to raise exception when querying
    query_proxy_mock = AsyncMock()
    query_proxy_mock.select.side_effect = Exception("Database connection failed: auth timeout")
    db_mock.return_value = query_proxy_mock
    db_mock.side_effect = None  # Clear side_effect so __call__ returns the proxy

    servicer = ManagerServicer(db=db_mock, cache=cache_mock, key_provider=key_provider_mock)

    # Mock context with valid token (bypass auth check by mocking decode_token)
    context_mock = MagicMock(spec=grpc.aio.ServicerContext)
    context_mock.invocation_metadata.return_value = [
        ("authorization", "Bearer valid-test-jwt")
    ]

    # Mock feature_enabled and decode_token to return valid claims
    with patch("hub_api.modules.netsvcs.grpc.server.feature_enabled") as mock_feature, \
         patch("hub_api.modules.netsvcs.grpc.server.decode_token") as mock_decode:
        mock_feature.return_value = True
        mock_decode.return_value = {
            "sub": "resolver:test",
            "iss": "tobogganing",
            "aud": "headend",
            "tenant": "default",
            "scope": "ioc:read",
        }

        # Build request
        request = manager_pb2.ValidateTokenRequest(
            api_version="v1",
            token="some-invalid-token",
        )

        # Call ValidateToken
        response = await servicer.ValidateToken(request, context_mock)

        # Verify response does NOT expose exception details
        assert response.valid is False
        assert "Database connection failed" not in response.reason
        assert "auth timeout" not in response.reason
        assert response.reason == "validation failed"  # Generic message only


@pytest.mark.asyncio
async def test_register_server_verbose_error_not_exposed_in_abort() -> None:
    """Test RegisterServer does not expose exception details when aborting."""
    # Mock dependencies
    db_mock = MagicMock()
    cache_mock = AsyncMock()
    key_provider_mock = MagicMock()

    servicer = ManagerServicer(db=db_mock, cache=cache_mock, key_provider=key_provider_mock)

    # Mock context to capture abort call
    context_mock = MagicMock(spec=grpc.aio.ServicerContext)
    abort_calls = []

    async def mock_abort(code, details):
        abort_calls.append((code, details))
        raise grpc.RpcError()

    context_mock.abort = mock_abort
    context_mock.invocation_metadata.return_value = [
        ("authorization", "Bearer invalid-token")
    ]

    # Build request
    request = manager_pb2.RegisterServerRequest(
        api_version="v1",
        hostname="test-resolver",
        version="1.0",
    )

    # Call RegisterServer with invalid bootstrap token
    with pytest.raises(grpc.RpcError):
        await servicer.RegisterServer(request, context_mock)

    # Verify abort was called with correct code and generic message
    assert len(abort_calls) > 0
    code, details = abort_calls[0]
    assert code == grpc.StatusCode.UNAUTHENTICATED
    assert details == "enrollment token required"
