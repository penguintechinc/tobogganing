"""Tests for SSRF-sandboxed fetcher (Slice E Task 1)."""

from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from hub_api.modules.sase.security.swg.tier2.fetcher import (
    _build_pinned_url,
    fetch,
    is_public_host,
    validate_and_resolve_host,
)


class TestIsPublicHost:
    """Test IP classification and SSRF rejection."""

    def test_rejects_loopback(self) -> None:
        """Loopback addresses must be rejected."""
        assert not is_public_host("127.0.0.1")
        assert not is_public_host("127.255.255.255")
        assert not is_public_host("::1")

    def test_rejects_private(self) -> None:
        """Private RFC 1918 addresses must be rejected."""
        assert not is_public_host("10.0.0.1")
        assert not is_public_host("172.16.0.1")
        assert not is_public_host("192.168.1.1")

    def test_rejects_link_local(self) -> None:
        """Link-local addresses must be rejected."""
        assert not is_public_host("169.254.1.1")
        assert not is_public_host("fe80::1")

    def test_rejects_multicast(self) -> None:
        """Multicast addresses must be rejected."""
        assert not is_public_host("224.0.0.1")
        assert not is_public_host("ff00::1")

    def test_rejects_reserved(self) -> None:
        """Reserved addresses must be rejected."""
        assert not is_public_host("0.0.0.0")
        assert not is_public_host("255.255.255.255")

    def test_accepts_public(self) -> None:
        """Public addresses must be accepted."""
        assert is_public_host("8.8.8.8")
        assert is_public_host("1.1.1.1")
        assert is_public_host("2001:4860:4860::8888")

    def test_rejects_unparseable_value(self) -> None:
        """A non-IP string raises ValueError internally and is rejected."""
        assert not is_public_host("not-an-ip-address")


class TestValidateAndResolveHost:
    """Test DNS resolution with SSRF validation (multi-record + IPv6)."""

    def test_rejects_if_any_record_is_private(self) -> None:
        """If getaddrinfo returns any private IP, reject (# regression: SSRF DNS-rebind / multi-record)."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            # Simulate getaddrinfo returning both public and private IPs
            # In reality, getaddrinfo returns a list of (family, type, proto, canonname, sockaddr)
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 443)),  # Private!
            ]

            result = validate_and_resolve_host("example.com", 443)
            assert result is None

    def test_accepts_if_all_records_are_public(self) -> None:
        """If all records are public, accept and return first IP."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:4860:4860::8888", 443)),
            ]

            result = validate_and_resolve_host("example.com", 443)
            assert result == "8.8.8.8"

    def test_rejects_ipv6_private(self) -> None:
        """If getaddrinfo returns IPv6 private (::1), reject (# regression: IPv6 loopback)."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443)),  # IPv6 loopback
            ]

            result = validate_and_resolve_host("example.com", 443)
            assert result is None

    def test_rejects_ipv6_link_local(self) -> None:
        """If getaddrinfo returns IPv6 link-local (fe80::), reject."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", 443)),
            ]

            result = validate_and_resolve_host("example.com", 443)
            assert result is None

    def test_dns_resolution_failure(self) -> None:
        """If getaddrinfo fails (gaierror), return None."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = socket.gaierror("Temporary failure")

            result = validate_and_resolve_host("invalid.example.com", 443)
            assert result is None

    def test_no_addrinfo_results(self) -> None:
        """An empty getaddrinfo result set is treated as resolution failure."""
        with patch("socket.getaddrinfo", return_value=[]):
            result = validate_and_resolve_host("example.com", 443)
            assert result is None

    def test_unexpected_exception_is_caught(self) -> None:
        """A non-gaierror exception from getaddrinfo is caught and returns None."""
        with patch("socket.getaddrinfo", side_effect=RuntimeError("unexpected")):
            result = validate_and_resolve_host("example.com", 443)
            assert result is None


class TestBuildPinnedUrl:
    """Test the IP-literal URL reconstruction helper directly."""

    def test_ipv4_pinned_url(self) -> None:
        """An IPv4 validated_ip produces a plain host:port netloc."""
        result = _build_pinned_url("https://example.com/path", "8.8.8.8", 443, "example.com")
        assert result == "https://8.8.8.8:443/path"

    def test_ipv6_pinned_url_uses_brackets(self) -> None:
        """An IPv6 validated_ip is bracketed in the netloc."""
        result = _build_pinned_url(
            "https://example.com/path", "2001:4860:4860::8888", 443, "example.com"
        )
        assert result == "https://[2001:4860:4860::8888]:443/path"

    def test_query_and_fragment_are_preserved(self) -> None:
        """Query string and fragment from the original URL are carried over."""
        result = _build_pinned_url(
            "https://example.com/path?a=1#section", "8.8.8.8", 443, "example.com"
        )
        assert result == "https://8.8.8.8:443/path?a=1#section"


class TestFetch:
    """Test SSRF-guarded fetcher."""

    @pytest.mark.asyncio
    async def test_fetch_public_host(self) -> None:
        """Fetch from a public host returns bytes."""
        html_body = b"<html>Test</html>"

        async def mock_aiter_bytes(chunk_size: int = 65536) -> None:
            """Mock async iterator for response body."""
            yield html_body

        with (
            patch("socket.gethostbyname", return_value="8.8.8.8"),
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.httpx.AsyncClient"
            ) as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.aiter_bytes = mock_aiter_bytes
            mock_response.headers = {}

            # Setup context manager
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Setup get method
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            result = await fetch("https://example.com")
            assert result == html_body

    @pytest.mark.asyncio
    async def test_fetch_rejects_loopback(self) -> None:
        """Fetch to loopback address is rejected."""
        result = await fetch("http://127.0.0.1/")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_rejects_private_ip(self) -> None:
        """Fetch to private IP is rejected."""
        result = await fetch("http://192.168.1.1/")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_rejects_link_local(self) -> None:
        """Fetch to link-local address is rejected."""
        result = await fetch("http://169.254.1.1/")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_timeout(self) -> None:
        """Fetch timeout returns None."""
        with (
            patch("socket.gethostbyname", return_value="8.8.8.8"),
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.httpx.AsyncClient"
            ) as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = httpx.TimeoutException("timeout")
            mock_client_class.return_value = mock_client

            result = await fetch("https://example.com", timeout_s=0.001)
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_oversize(self) -> None:
        """Fetch exceeding size cap returns None or is truncated."""
        large_body = b"x" * (512_001)  # Over 512KB

        async def iter_bytes_mock(chunk_size: int = 65536) -> None:
            """Mock async iterator that yields oversized data."""
            for i in range(0, len(large_body), 65536):
                yield large_body[i : i + 65536]

        with (
            patch("socket.gethostbyname", return_value="8.8.8.8"),
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.httpx.AsyncClient"
            ) as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.aiter_bytes = iter_bytes_mock
            mock_response.headers = {}

            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await fetch("https://example.com", max_bytes=512_000)
            assert result is None or len(result) <= 512_000

    @pytest.mark.asyncio
    async def test_fetch_no_cookies(self) -> None:
        """Fetch does not send cookies or auth headers."""

        async def iter_bytes_mock(chunk_size: int = 65536) -> None:
            """Mock async iterator."""
            yield b"test"

        with (
            patch("socket.gethostbyname", return_value="8.8.8.8"),
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.httpx.AsyncClient"
            ) as mock_client_class,
        ):
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.aiter_bytes = iter_bytes_mock
            mock_response.headers = {}
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await fetch("https://example.com")

            # Verify get was called without cookies/auth
            call_kwargs = mock_client.get.call_args[1]
            assert "cookies" not in call_kwargs or call_kwargs.get("cookies") is None
            assert "auth" not in call_kwargs or call_kwargs.get("auth") is None

    @pytest.mark.asyncio
    async def test_fetch_redirect_to_private_rejected(self) -> None:
        """Redirect to private IP is rejected (manual re-validation)."""

        async def iter_bytes_mock(chunk_size: int = 65536) -> None:
            """Mock async iterator."""
            yield b"test"

        with (
            patch("socket.getaddrinfo") as mock_getaddrinfo,
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.httpx.AsyncClient"
            ) as mock_client_class,
        ):
            # First call validates original host (public)
            # Second call validates redirect target (private) - should reject
            mock_getaddrinfo.side_effect = [
                [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],  # original
                [
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 443))
                ],  # redirect private
            ]

            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 301
            mock_response.headers = {"location": "https://internal.local/"}
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await fetch("https://example.com")
            assert result is None  # Should reject due to private redirect target

    @pytest.mark.asyncio
    async def test_fetch_no_host_in_url(self) -> None:
        """A URL with no parseable hostname returns None before any I/O."""
        result = await fetch("not-a-url-at-all")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_non_200_status_returns_none(self) -> None:
        """A non-redirect, non-200 status code returns None."""

        async def iter_bytes_mock(chunk_size: int = 65536):
            yield b"unused"

        with (
            patch("socket.getaddrinfo") as mock_getaddrinfo,
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.httpx.AsyncClient"
            ) as mock_client_class,
        ):
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            ]
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 404
            mock_response.aiter_bytes = iter_bytes_mock
            mock_response.headers = {}
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await fetch("https://example.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_redirect_missing_location_header(self) -> None:
        """A redirect status with no Location header breaks out and returns None."""
        with (
            patch("socket.getaddrinfo") as mock_getaddrinfo,
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.httpx.AsyncClient"
            ) as mock_client_class,
        ):
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            ]
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 301
            mock_response.headers = {}  # no "location"
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await fetch("https://example.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_redirect_location_has_no_hostname(self) -> None:
        """A redirect Location that parses to no hostname breaks out and returns None."""
        with (
            patch("socket.getaddrinfo") as mock_getaddrinfo,
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.httpx.AsyncClient"
            ) as mock_client_class,
        ):
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            ]
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 302
            mock_response.headers = {"location": "/just/a/relative/path"}
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await fetch("https://example.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_follows_valid_redirect_to_success(self) -> None:
        """A redirect to a validated public host is followed and the next hop succeeds."""

        async def iter_bytes_mock(chunk_size: int = 65536):
            yield b"final body"

        with (
            patch("socket.getaddrinfo") as mock_getaddrinfo,
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.httpx.AsyncClient"
            ) as mock_client_class,
        ):
            # Both the original host and the redirect target resolve publicly
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            ]

            redirect_response = AsyncMock()
            redirect_response.status_code = 302
            redirect_response.headers = {"location": "https://redirected.example.com/final"}

            success_response = AsyncMock()
            success_response.status_code = 200
            success_response.headers = {}
            success_response.aiter_bytes = iter_bytes_mock

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(side_effect=[redirect_response, success_response])
            mock_client_class.return_value = mock_client

            result = await fetch("https://example.com")
            assert result == b"final body"

    @pytest.mark.asyncio
    async def test_fetch_too_many_redirects_returns_none(self) -> None:
        """Exceeding the 10-hop redirect cap returns None."""
        with (
            patch("socket.getaddrinfo") as mock_getaddrinfo,
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.httpx.AsyncClient"
            ) as mock_client_class,
        ):
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            ]

            redirect_response = AsyncMock()
            redirect_response.status_code = 302
            redirect_response.headers = {"location": "https://example.com/next"}

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=redirect_response)  # always redirects
            mock_client_class.return_value = mock_client

            result = await fetch("https://example.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_real_asyncio_timeout(self) -> None:
        """A request that outlasts asyncio.wait_for's deadline is treated as a timeout."""

        async def slow_get(*args: object, **kwargs: object) -> None:
            await asyncio.sleep(1)

        with (
            patch("socket.getaddrinfo") as mock_getaddrinfo,
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.httpx.AsyncClient"
            ) as mock_client_class,
        ):
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            ]
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = slow_get
            mock_client_class.return_value = mock_client

            result = await fetch("https://example.com", timeout_s=0.01)
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_unexpected_exception_is_caught(self) -> None:
        """A non-httpx exception (e.g. from AsyncClient construction) is caught."""
        with (
            patch("socket.getaddrinfo") as mock_getaddrinfo,
            patch(
                "hub_api.modules.sase.security.swg.tier2.fetcher.httpx.AsyncClient",
                side_effect=RuntimeError("client construction failed"),
            ),
        ):
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            ]

            result = await fetch("https://example.com")
            assert result is None
