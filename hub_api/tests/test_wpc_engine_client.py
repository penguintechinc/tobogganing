"""Tests for WaddlePerf cluster engine client."""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from hub_api.modules.perftest_cluster.services.engine_client import (
    ALLOWED_TEST_TYPES,
    TEST_TYPE_ALIASES,
    EngineClient,
    EngineError,
    TestserverSpeedtestBackend,
)

# "throughput" is dispatched through ThroughputBackend, not the generic
# /api/v1/test/{type} POST convention exercised by test_run_test_all_types.
_GENERIC_TEST_TYPES = ALLOWED_TEST_TYPES - {"throughput"}


class TestEngineClientInit:
    """Tests for EngineClient initialization."""

    def test_init_with_explicit_url_and_key(self) -> None:
        """Test client initialization with explicit parameters."""
        client = EngineClient(
            base_url="http://engine:8080",
            api_key="sk-test-key",
        )
        assert client.base_url == "http://engine:8080"
        assert client.api_key == "sk-test-key"
        assert client.timeout == 30.0

    def test_init_from_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test client initialization from environment variables."""
        monkeypatch.setenv("ENGINE_URL", "http://prod-engine:8080")
        monkeypatch.setenv("ENGINE_API_KEY", "sk-prod-key")

        client = EngineClient()
        assert client.base_url == "http://prod-engine:8080"
        assert client.api_key == "sk-prod-key"

    def test_init_default_url_when_env_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test client uses default URL when ENV not set."""
        monkeypatch.delenv("ENGINE_URL", raising=False)

        client = EngineClient()
        assert client.base_url == "http://testserver:8080"
        assert client.api_key is None

    def test_init_no_api_key_when_env_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test client works without API key."""
        monkeypatch.delenv("ENGINE_API_KEY", raising=False)

        client = EngineClient(base_url="http://engine:8080")
        assert client.api_key is None

    def test_init_custom_timeout(self) -> None:
        """Test client initialization with custom timeout."""
        client = EngineClient(base_url="http://engine:8080", timeout=60.0)
        assert client.timeout == 60.0

    def test_init_explicit_url_overrides_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test explicit URL parameter overrides environment variable."""
        monkeypatch.setenv("ENGINE_URL", "http://env-engine:8080")

        client = EngineClient(base_url="http://explicit-engine:8080")
        assert client.base_url == "http://explicit-engine:8080"

    def test_init_empty_url_raises_error(self) -> None:
        """Test initialization with empty URL raises EngineError."""
        with pytest.raises(EngineError, match="base_url required"):
            EngineClient(base_url="")


class TestEngineClientHealth:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_health_success(self) -> None:
        """Test successful health check."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            result = await client.health()
            assert result is True
            mock_get.assert_called_once_with("http://engine:8080/health")

        await client.close()

    @pytest.mark.asyncio
    async def test_health_failure(self) -> None:
        """Test health check returns False on non-200 status."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_get.return_value = mock_response

            result = await client.health()
            assert result is False

        await client.close()

    @pytest.mark.asyncio
    async def test_health_network_error(self) -> None:
        """Test health check raises EngineError on network failure."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = httpx.RequestError("Connection refused")

            with pytest.raises(EngineError, match="Failed to reach engine"):
                await client.health()

        await client.close()

    @pytest.mark.asyncio
    async def test_health_unexpected_error(self) -> None:
        """Test health check raises EngineError on unexpected exception."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock
        ) as mock_get:
            mock_get.side_effect = RuntimeError("Unexpected error")

            with pytest.raises(EngineError, match="Unexpected error during health"):
                await client.health()

        await client.close()


class TestEngineClientRunTest:
    """Tests for test execution functionality."""

    @pytest.mark.asyncio
    async def test_run_test_success(self) -> None:
        """Test successful test execution."""
        client = EngineClient(
            base_url="http://engine:8080",
            api_key="sk-test-key",
        )

        device_headers = {
            "X-Device-Serial": "device-123",
            "X-Device-Hostname": "test-host",
        }

        expected_response = {"status": "success", "latency_ms": 45}

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = expected_response
            mock_post.return_value = mock_response

            result = await client.run_test(
                test_type="http",
                target="example.com",
                device_headers=device_headers,
                port=80,
                timeout=30,
            )

            assert result == expected_response
            mock_post.assert_called_once()

            # Verify call arguments
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"]["target"] == "example.com"
            assert call_kwargs["json"]["port"] == 80
            assert call_kwargs["json"]["timeout"] == 30
            assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test-key"
            assert call_kwargs["headers"]["X-Device-Serial"] == "device-123"
            assert call_kwargs["headers"]["X-Device-Hostname"] == "test-host"

        await client.close()

    @pytest.mark.asyncio
    async def test_run_test_all_types(self) -> None:
        """Test that all generic (non-throughput) allowed test types are accepted."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "success"}
            mock_post.return_value = mock_response

            for test_type in _GENERIC_TEST_TYPES:
                result = await client.run_test(
                    test_type=test_type,
                    target="example.com",
                )
                assert result == {"status": "success"}

        await client.close()

    @pytest.mark.asyncio
    async def test_run_test_invalid_type(self) -> None:
        """Test that invalid test type raises EngineError."""
        client = EngineClient(base_url="http://engine:8080")

        with pytest.raises(EngineError, match="Invalid test_type"):
            await client.run_test(
                test_type="invalid_test",
                target="example.com",
            )

        await client.close()

    @pytest.mark.asyncio
    async def test_run_test_http_error(self) -> None:
        """Test that HTTP errors raise EngineError."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Bad request"
            mock_post.return_value = mock_response

            with pytest.raises(EngineError, match="Test execution failed"):
                await client.run_test(
                    test_type="http",
                    target="example.com",
                )

        await client.close()

    @pytest.mark.asyncio
    async def test_run_test_network_error(self) -> None:
        """Test that network errors raise EngineError."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.side_effect = httpx.RequestError("Connection timeout")

            with pytest.raises(EngineError, match="Failed to communicate"):
                await client.run_test(
                    test_type="http",
                    target="example.com",
                )

        await client.close()

    @pytest.mark.asyncio
    async def test_run_test_without_api_key(self) -> None:
        """Test that requests work without API key."""
        client = EngineClient(
            base_url="http://engine:8080",
            api_key=None,
        )

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "success"}
            mock_post.return_value = mock_response

            await client.run_test(
                test_type="http",
                target="example.com",
            )

            # Verify Authorization header not present
            call_kwargs = mock_post.call_args[1]
            assert "Authorization" not in call_kwargs["headers"]

        await client.close()

    @pytest.mark.asyncio
    async def test_run_test_without_device_headers(self) -> None:
        """Test that requests work without device headers."""
        client = EngineClient(base_url="http://engine:8080", api_key="sk-key")

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "success"}
            mock_post.return_value = mock_response

            await client.run_test(
                test_type="http",
                target="example.com",
            )

            # Verify only Authorization header present
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "Bearer sk-key"
            assert len(call_kwargs["headers"]) == 1

        await client.close()

    @pytest.mark.asyncio
    async def test_run_test_with_extra_params(self) -> None:
        """Test that extra parameters are passed through."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "success"}
            mock_post.return_value = mock_response

            await client.run_test(
                test_type="tcp",
                target="example.com",
                port=443,
                timeout=60,
                count=5,
                protocol_detail=True,
            )

            # Verify all parameters are in request
            call_kwargs = mock_post.call_args[1]
            body = call_kwargs["json"]
            assert body["target"] == "example.com"
            assert body["port"] == 443
            assert body["timeout"] == 60
            assert body["count"] == 5
            assert body["protocol_detail"] is True

        await client.close()

    @pytest.mark.asyncio
    async def test_run_test_unexpected_error(self) -> None:
        """Test that unexpected errors raise EngineError."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.side_effect = RuntimeError("Unexpected error")

            with pytest.raises(EngineError, match="Unexpected error during test"):
                await client.run_test(
                    test_type="http",
                    target="example.com",
                )

        await client.close()


class TestEngineClientThroughput:
    """Tests for the "throughput" test type (heavy-tier speed test)."""

    @pytest.mark.asyncio
    async def test_throughput_maps_throughput_mbps(self) -> None:
        """throughput_mbps from the engine maps into `throughput` in the result."""
        client = EngineClient(base_url="http://engine:8080", api_key="sk-test-key")
        device_headers = {"X-Device-ID": "d1"}

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "success": True,
                "bytes_received": 10485760,
                "duration_ms": 812,
                "throughput_mbps": 103.4,
            }
            mock_post.return_value = mock_response

            result = await client.run_test(
                test_type="throughput",
                target="10.0.0.1",
                device_headers=device_headers,
            )

            assert result["throughput"] == 103.4
            assert result["throughput_mbps"] == 103.4
            assert result["bytes_transferred"] == 10485760
            assert result["duration_ms"] == 812

            call_args, call_kwargs = mock_post.call_args
            assert call_args[0] == "http://engine:8080/speedtest/upload"
            assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test-key"
            assert call_kwargs["headers"]["X-Device-ID"] == "d1"
            # Payload is uploaded as raw bytes, not JSON.
            assert "content" in call_kwargs
            assert isinstance(call_kwargs["content"], bytes)

        await client.close()

    @pytest.mark.asyncio
    async def test_speedtest_alias_resolves_to_throughput(self) -> None:
        """"speedtest" is accepted as an alias and routes identically."""
        assert TEST_TYPE_ALIASES["speedtest"] == "throughput"

        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"throughput_mbps": 50.0}
            mock_post.return_value = mock_response

            result = await client.run_test(test_type="speedtest", target="10.0.0.1")
            assert result["throughput"] == 50.0

            called_url = mock_post.call_args[0][0]
            assert called_url == "http://engine:8080/speedtest/upload"

        await client.close()

    @pytest.mark.asyncio
    async def test_throughput_respects_size_mb_param(self) -> None:
        """`size_mb` param is clamped to [1, 100] and controls payload size."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"throughput_mbps": 1.0}
            mock_post.return_value = mock_response

            await client.run_test(test_type="throughput", target="x", size_mb=500)
            payload = mock_post.call_args[1]["content"]
            assert len(payload) == 100 * 1024 * 1024  # clamped to MAX

        await client.close()

    @pytest.mark.asyncio
    async def test_throughput_http_error_raises_engine_error(self) -> None:
        """A non-2xx response from /speedtest/upload raises EngineError."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_response.text = "Service unavailable"
            mock_post.return_value = mock_response

            with pytest.raises(EngineError, match="Test execution failed"):
                await client.run_test(test_type="throughput", target="10.0.0.1")

        await client.close()

    @pytest.mark.asyncio
    async def test_throughput_network_error_raises_engine_error(self) -> None:
        """A network error during the upload raises EngineError."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_post.side_effect = httpx.RequestError("Connection refused")

            with pytest.raises(EngineError, match="Failed to communicate"):
                await client.run_test(test_type="throughput", target="10.0.0.1")

        await client.close()

    @pytest.mark.asyncio
    async def test_custom_throughput_backend_is_used(self) -> None:
        """A custom ThroughputBackend can be injected without touching run_test."""

        class _FakeBackend:
            called_with: dict[str, Any] = {}

            async def run(
                self,
                client: httpx.AsyncClient,
                base_url: str,
                target: str,
                headers: dict[str, str],
                **params: Any,
            ) -> dict[str, Any]:
                self.called_with = {"base_url": base_url, "target": target}
                return {"throughput": 777.0}

        backend = _FakeBackend()
        client = EngineClient(base_url="http://engine:8080", throughput_backend=backend)

        result = await client.run_test(test_type="throughput", target="10.0.0.1")

        assert result == {"throughput": 777.0}
        assert backend.called_with == {
            "base_url": "http://engine:8080",
            "target": "10.0.0.1",
        }

        await client.close()

    def test_default_throughput_backend_is_testserver_speedtest(self) -> None:
        """EngineClient defaults to TestserverSpeedtestBackend."""
        client = EngineClient(base_url="http://engine:8080")
        assert isinstance(client.throughput_backend, TestserverSpeedtestBackend)


class TestEngineClientHttp2Ping:
    """Tests for the "http2" test type (Tier-1 HTTP/2 reachability/latency probe).

    Follows the same generic `/api/v1/test/{type}` convention as `http`,
    distinct from ThroughputBackend's dedicated speedtest path. The
    testserver-side handler is a documented follow-up seam (Go dev work);
    this only verifies hub_api's routing/mapping via a mocked h2 response.
    """

    @pytest.mark.asyncio
    async def test_http2_dispatches_to_generic_test_endpoint(self) -> None:
        """run_test("http2", ...) POSTs to /api/v1/test/http2 and passes
        through the (mocked) HTTP/2 response untouched."""
        client = EngineClient(base_url="http://engine:8080")

        h2_response = {
            "latency_ms": 15.2,
            "http_version": "HTTP/2",
            "reachable": True,
        }

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = h2_response
            mock_post.return_value = mock_response

            result = await client.run_test(test_type="http2", target="example.com")

            assert result == h2_response
            called_url = mock_post.call_args[0][0]
            assert called_url == "http://engine:8080/api/v1/test/http2"

        await client.close()

    @pytest.mark.asyncio
    async def test_http2_ping_alias_resolves_to_http2(self) -> None:
        """"http2_ping" is accepted as an alias and routes identically."""
        assert TEST_TYPE_ALIASES["http2_ping"] == "http2"

        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"latency_ms": 9.9}
            mock_post.return_value = mock_response

            result = await client.run_test(test_type="http2_ping", target="example.com")
            assert result == {"latency_ms": 9.9}

            called_url = mock_post.call_args[0][0]
            assert called_url == "http://engine:8080/api/v1/test/http2"

        await client.close()

    @pytest.mark.asyncio
    async def test_http2_not_yet_implemented_on_testserver_surfaces_engine_error(
        self,
    ) -> None:
        """Until the Go testserver adds the h2 handler, a 404 from the
        (real, unmodified) testserver surfaces as a normal EngineError --
        the documented seam, not a silent failure."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock
        ) as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = "404 page not found"
            mock_post.return_value = mock_response

            with pytest.raises(EngineError, match="Test execution failed"):
                await client.run_test(test_type="http2", target="example.com")

        await client.close()


class TestEngineClientClose:
    """Tests for client lifecycle management."""

    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        """Test that close properly closes the HTTP client."""
        client = EngineClient(base_url="http://engine:8080")

        with patch.object(httpx.AsyncClient, "aclose", new_callable=AsyncMock) as mock_close:
            # Get the client first to initialize it
            await client._get_client()
            await client.close()

            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Test that async context manager works."""
        with patch.object(httpx.AsyncClient, "aclose", new_callable=AsyncMock):
            async with EngineClient(base_url="http://engine:8080") as client:
                assert client.base_url == "http://engine:8080"


class TestEngineError:
    """Tests for EngineError exception."""

    def test_error_with_message_only(self) -> None:
        """Test EngineError with message only."""
        error = EngineError("Test failed")
        assert str(error) == "Test failed"

    def test_error_with_status_code(self) -> None:
        """Test EngineError with status code."""
        error = EngineError("Test failed", status_code=500)
        assert "HTTP 500" in str(error)

    def test_error_with_details(self) -> None:
        """Test EngineError with details."""
        error = EngineError("Test failed", details="Connection timeout")
        assert "Connection timeout" in str(error)

    def test_error_with_all_fields(self) -> None:
        """Test EngineError with all fields."""
        error = EngineError(
            "Test failed",
            status_code=502,
            details="Bad gateway",
        )
        error_str = str(error)
        assert "Test failed" in error_str
        assert "HTTP 502" in error_str
        assert "Bad gateway" in error_str
