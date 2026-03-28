"""py4web Fixture for OIDC Bearer token validation via penguin-aaa.

OIDCRelyingParty is async; py4web runs synchronously, so we use
asyncio.run() to bridge the gap.  Validated claims are stored on
``request.local.claims`` so downstream fixtures and route handlers can
read them without repeating token parsing.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from py4web import HTTP, Fixture, request, response
from penguin_aaa import OIDCRelyingParty
from penguin_aaa.authn.oidc_rp import OIDCRPConfig

logger = logging.getLogger(__name__)

# Public paths that never require a Bearer token.
_DEFAULT_PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/healthz",
        "/metrics",
        "/api/v1/status",
    }
)


def _build_rp() -> OIDCRelyingParty:
    """Construct an OIDCRelyingParty from environment variables.

    Required env vars:
        OIDC_ISSUER_URL    – OIDC provider base URL (e.g. https://auth.example.com)
        OIDC_CLIENT_ID     – Client ID registered with the provider
        OIDC_CLIENT_SECRET – Client secret
        OIDC_REDIRECT_URL  – Redirect URI (e.g. https://app.example.com/callback)

    Optional:
        OIDC_ALGORITHMS    – Comma-separated algorithms, defaults to RS256
    """
    issuer_url = os.environ["OIDC_ISSUER_URL"]
    client_id = os.environ["OIDC_CLIENT_ID"]
    client_secret = os.environ["OIDC_CLIENT_SECRET"]
    redirect_url = os.environ["OIDC_REDIRECT_URL"]
    algorithms = [
        a.strip()
        for a in os.getenv("OIDC_ALGORITHMS", "RS256").split(",")
        if a.strip()
    ]

    config = OIDCRPConfig(
        issuer_url=issuer_url,
        client_id=client_id,
        client_secret=client_secret,
        redirect_url=redirect_url,
        algorithms=algorithms,
    )
    return OIDCRelyingParty(config)


class OIDCFixture(Fixture):
    """py4web Fixture that validates Bearer tokens via OIDCRelyingParty.

    On success, validated claims are placed at ``request.local.claims``.
    On failure, an HTTP 401 is raised immediately.

    Args:
        rp:           An OIDCRelyingParty instance.  Pass ``None`` to
                      auto-construct one from environment variables.
        public_paths: Paths that bypass token validation entirely.
    """

    HEADER_NAME = b"authorization"

    def __init__(
        self,
        rp: OIDCRelyingParty | None = None,
        public_paths: frozenset[str] | None = None,
    ) -> None:
        self.__prerequisites__: list[Any] = []
        self._rp: OIDCRelyingParty = rp if rp is not None else _build_rp()
        self._public_paths: frozenset[str] = (
            public_paths if public_paths is not None else _DEFAULT_PUBLIC_PATHS
        )

    # ------------------------------------------------------------------
    # Fixture protocol
    # ------------------------------------------------------------------

    def on_request(self, context: Any) -> None:
        """Validate the Bearer token on every non-public request."""
        path: str = request.path

        # Allow public paths through without a token.
        if path in self._public_paths:
            return

        auth: str = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTP(
                401,
                {
                    "status": "error",
                    "data": {"message": "Missing or invalid Bearer token"},
                    "meta": {},
                },
            )

        token = auth[7:]
        try:
            claims = asyncio.run(self._rp.validate_token(token))
        except Exception as exc:
            logger.warning("OIDC token validation failed: %s", exc)
            raise HTTP(
                401,
                {
                    "status": "error",
                    "data": {"message": "Token verification failed"},
                    "meta": {},
                },
            ) from exc

        # Store claims on request.local for downstream fixtures/handlers.
        request.local.claims = claims

    def on_error(self, context: Any, exc: BaseException) -> None:
        """Let HTTP exceptions pass through; re-raise everything else."""
        if isinstance(exc, HTTP):
            raise exc
        logger.error("Unexpected error in OIDCFixture: %s", exc)
        raise HTTP(
            500,
            {
                "status": "error",
                "data": {"message": "Internal authentication error"},
                "meta": {},
            },
        ) from exc
