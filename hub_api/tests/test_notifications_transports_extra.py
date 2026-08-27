"""Additional coverage for hub_api.notifications.transports SMTP/webhook branches.

test_notifications.py exercises WebhookTransport happy/error paths via an
injected AsyncMock http client and only smoke-tests EmailTransport's
interface; this file exercises the real SMTP send path (mocked smtplib) and
the remaining WebhookTransport error branches.
"""

from __future__ import annotations

import os
import smtplib
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from hub_api.notifications.transports import EmailTransport, TransportError, WebhookTransport


class TestTransportError:
    """Tests for TransportError.__str__."""

    def test_str_with_details(self) -> None:
        """Includes details when present."""
        err = TransportError("failed", details="root cause")
        assert str(err) == "failed: root cause"

    def test_str_without_details(self) -> None:
        """Omits details when absent."""
        err = TransportError("failed")
        assert str(err) == "failed"


class TestEmailTransportInit:
    """Tests for EmailTransport env-var defaults."""

    def test_defaults_from_env(self) -> None:
        """Falls back to env vars / hardcoded defaults when args are omitted."""
        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": "2525",
                "SMTP_USER": "user1",
                "SMTP_PASS": "pass1",
                "SMTP_FROM": "alerts@example.com",
            },
            clear=True,
        ):
            transport = EmailTransport()

        assert transport.host == "smtp.example.com"
        assert transport.port == 2525
        assert transport.user == "user1"
        assert transport.password == "pass1"
        assert transport.from_addr == "alerts@example.com"

    def test_explicit_args_override_env(self) -> None:
        """Explicit constructor args take priority over env vars."""
        with patch.dict(os.environ, {"SMTP_HOST": "env-host"}, clear=True):
            transport = EmailTransport(host="explicit-host", port=25)

        assert transport.host == "explicit-host"
        assert transport.port == 25


class TestEmailTransportSend:
    """Tests for EmailTransport.send() via mocked smtplib.SMTP."""

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        """send() connects, logs in (if creds present), and sends via smtplib."""
        transport = EmailTransport(
            host="smtp.example.com", port=587, user="u", password="p", from_addr="a@example.com"
        )

        fake_smtp = MagicMock()
        fake_smtp.__enter__.return_value = fake_smtp
        fake_smtp.__exit__.return_value = False

        with patch("smtplib.SMTP", return_value=fake_smtp) as mock_smtp_cls:
            await transport.send(["to@example.com"], "Subject", "Body text")

        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587)
        fake_smtp.starttls.assert_called_once()
        fake_smtp.login.assert_called_once_with("u", "p")
        fake_smtp.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_without_credentials_skips_login(self) -> None:
        """send() does not call login() when user/password are empty."""
        transport = EmailTransport(host="smtp.example.com", port=587, user="", password="")

        fake_smtp = MagicMock()
        fake_smtp.__enter__.return_value = fake_smtp
        fake_smtp.__exit__.return_value = False

        with patch("smtplib.SMTP", return_value=fake_smtp):
            await transport.send(["to@example.com"], "Subject", "Body")

        fake_smtp.login.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_smtp_exception_raises_transport_error(self) -> None:
        """send() wraps smtplib.SMTPException as TransportError."""
        transport = EmailTransport(host="smtp.example.com", port=587)

        with patch("smtplib.SMTP", side_effect=smtplib.SMTPConnectError(421, "refused")):
            with pytest.raises(TransportError, match="SMTP error"):
                await transport.send(["to@example.com"], "Subject", "Body")

    @pytest.mark.asyncio
    async def test_send_generic_exception_raises_transport_error(self) -> None:
        """send() wraps unexpected exceptions as TransportError."""
        transport = EmailTransport(host="smtp.example.com", port=587)

        with patch("smtplib.SMTP", side_effect=OSError("network unreachable")):
            with pytest.raises(TransportError, match="Failed to send email"):
                await transport.send(["to@example.com"], "Subject", "Body")


class TestWebhookTransportErrors:
    """Tests for WebhookTransport error branches not covered elsewhere."""

    @pytest.mark.asyncio
    async def test_non_https_url_rejected(self) -> None:
        """send() rejects a non-https webhook URL before making any request."""
        transport = WebhookTransport()
        with pytest.raises(TransportError, match="https"):
            await transport.send("http://example.com/webhook", "secret", "Subj", "Body")

    @pytest.mark.asyncio
    async def test_get_client_lazily_creates_httpx_client(self) -> None:
        """_get_client() lazily constructs and caches an httpx.AsyncClient."""
        transport = WebhookTransport(timeout=5.0)
        assert transport._client is None

        client = await transport._get_client()
        assert isinstance(client, httpx.AsyncClient)
        assert transport._client is client

        # Second call reuses the cached client
        client2 = await transport._get_client()
        assert client2 is client
        await transport.close()

    @pytest.mark.asyncio
    async def test_request_error_raises_transport_error(self) -> None:
        """send() wraps httpx.RequestError as TransportError."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        transport = WebhookTransport()
        transport._client = mock_client

        with pytest.raises(TransportError, match="Failed to reach webhook"):
            await transport.send("https://example.com/webhook", "secret", "Subj", "Body")

    @pytest.mark.asyncio
    async def test_generic_exception_raises_transport_error(self) -> None:
        """send() wraps unexpected exceptions as TransportError."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = ValueError("unexpected")

        transport = WebhookTransport()
        transport._client = mock_client

        with pytest.raises(TransportError, match="Webhook error"):
            await transport.send("https://example.com/webhook", "secret", "Subj", "Body")

    @pytest.mark.asyncio
    async def test_close_when_no_client_is_noop(self) -> None:
        """close() is a no-op when no client was ever created."""
        transport = WebhookTransport()
        await transport.close()
        assert transport._client is None

    @pytest.mark.asyncio
    async def test_close_closes_and_clears_client(self) -> None:
        """close() calls aclose() on the client and clears the reference."""
        mock_client = AsyncMock()
        transport = WebhookTransport()
        transport._client = mock_client

        await transport.close()

        mock_client.aclose.assert_called_once()
        assert transport._client is None
