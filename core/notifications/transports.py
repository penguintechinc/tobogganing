"""Notification delivery transports (email, webhook)."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class TransportError(Exception):
    """Raised when transport delivery fails."""

    message: str
    details: str | None = None

    def __str__(self) -> str:
        """Return string representation."""
        msg = self.message
        if self.details:
            msg = f"{msg}: {self.details}"
        return msg


class EmailTransport:
    """Send notifications via SMTP email."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        from_addr: str | None = None,
    ) -> None:
        """Initialize email transport.

        Args:
            host: SMTP host (defaults to SMTP_HOST env var)
            port: SMTP port (defaults to SMTP_PORT env var or 587)
            user: SMTP user (defaults to SMTP_USER env var)
            password: SMTP password (defaults to SMTP_PASS env var)
            from_addr: From address (defaults to SMTP_FROM env var)
        """
        self.host = host or os.environ.get("SMTP_HOST", "localhost")
        self.port = port or int(os.environ.get("SMTP_PORT", "587"))
        self.user = user or os.environ.get("SMTP_USER", "")
        self.password = password or os.environ.get("SMTP_PASS", "")
        self.from_addr = from_addr or os.environ.get("SMTP_FROM", "noreply@tobogganing.local")

    async def send(self, to: list[str], subject: str, body: str) -> None:
        """Send email via SMTP.

        Args:
            to: List of recipient email addresses
            subject: Email subject
            body: Email body

        Raises:
            TransportError: On SMTP connection or send failures
        """
        await asyncio.to_thread(self._send_sync, to, subject, body)

    def _send_sync(self, to: list[str], subject: str, body: str) -> None:
        """Synchronous SMTP send (run in thread pool)."""
        try:
            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)

                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = self.from_addr
                msg["To"] = ", ".join(to)

                msg.attach(MIMEText(body, "plain"))

                server.sendmail(self.from_addr, to, msg.as_string())

            log.info("email_sent", to=len(to), subject=subject)
        except smtplib.SMTPException as e:
            log.error("smtp_error", error=str(e))
            raise TransportError(f"SMTP error: {str(e)}", details=str(e)) from e
        except Exception as e:
            log.error("email_send_error", error=str(e))
            raise TransportError(f"Failed to send email: {str(e)}", details=str(e)) from e


class WebhookTransport:
    """Send notifications via HTTPS webhooks with HMAC-SHA256 signatures."""

    def __init__(self, timeout: float = 30.0) -> None:
        """Initialize webhook transport.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def send(self, url: str, secret: str, subject: str, body: str) -> None:
        """Send webhook with HMAC-SHA256 signature.

        Args:
            url: Webhook URL (must be https)
            secret: HMAC secret key
            subject: Notification subject
            body: Notification body

        Raises:
            TransportError: On HTTP or signature errors
        """
        if not url.startswith("https://"):
            raise TransportError("Webhook URL must use https")

        try:
            client = await self._get_client()

            # Create timestamp and payload
            timestamp = datetime.utcnow().isoformat()
            payload = {
                "subject": subject,
                "body": body,
                "timestamp": timestamp,
            }

            # Serialize to JSON
            json_body = json.dumps(payload, separators=(",", ":"))

            # Compute HMAC-SHA256 signature
            signature = "sha256=" + hmac.new(
                secret.encode(),
                json_body.encode(),
                hashlib.sha256,
            ).hexdigest()

            # Send POST request
            headers = {
                "Content-Type": "application/json",
                "X-Tobogganing-Signature": signature,
            }

            response = await client.post(
                url,
                content=json_body,
                headers=headers,
            )

            if response.status_code >= 400:
                error_text = response.text[:200]
                log.error(
                    "webhook_failed",
                    url=url,
                    status=response.status_code,
                    error=error_text,
                )
                raise TransportError(
                    f"Webhook failed with HTTP {response.status_code}",
                    details=error_text,
                )

            log.info("webhook_sent", url=url, subject=subject)

        except httpx.RequestError as e:
            log.error("webhook_network_error", url=url, error=str(e))
            raise TransportError(f"Failed to reach webhook: {str(e)}", details=str(e)) from e
        except TransportError:
            raise
        except Exception as e:
            log.error("webhook_error", url=url, error=str(e))
            raise TransportError(f"Webhook error: {str(e)}", details=str(e)) from e

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
