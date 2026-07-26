"""py4web Fixture for scope-based authorization via penguin-aaa.

Reads validated OIDC claims stored by OIDCFixture at
``request.local.claims`` and enforces the required scope(s).

Usage example::

    from auth.oidc_fixture import OIDCFixture
    from auth.scope_fixture import ScopeFixture

    oidc = OIDCFixture()
    require_policies_read = ScopeFixture("policies:read", oidc)

    @action("api/v1/policies", method=["GET"])
    @action.uses(require_policies_read)
    def list_policies():
        ...
"""

from __future__ import annotations

import logging
from typing import Any

from py4web import HTTP, Fixture, request

logger = logging.getLogger(__name__)


class ScopeFixture(Fixture):
    """py4web Fixture that enforces a required OIDC scope.

    The fixture reads ``request.local.claims`` populated by
    :class:`~auth.oidc_fixture.OIDCFixture`.  When the required scope is
    absent, an HTTP 403 is raised.

    Args:
        scope:       The scope string that must be present (e.g. ``"policies:read"``).
        oidc_fixture: The upstream OIDCFixture instance — listed as a
                      prerequisite so py4web executes it first.
    """

    def __init__(self, scope: str, oidc_fixture: Fixture) -> None:
        self.__prerequisites__: list[Any] = [oidc_fixture]
        self._scope = scope

    # ------------------------------------------------------------------
    # Fixture protocol
    # ------------------------------------------------------------------

    def on_request(self, context: Any) -> None:
        """Verify the required scope is present in the request's claims."""
        claims = getattr(request.local, "claims", None)

        if claims is None:
            # OIDCFixture did not populate claims — route must be public.
            # Raise 403 because accessing a scoped endpoint without claims
            # is a permission error (not an authentication error).
            raise HTTP(
                403,
                {
                    "status": "error",
                    "data": {"message": "No claims available; cannot verify scope"},
                    "meta": {},
                },
            )

        # Claims may be a pydantic model (penguin_aaa.authn.types.Claims)
        # or a plain dict — handle both.
        if hasattr(claims, "model_dump"):
            claims_dict: dict[str, Any] = claims.model_dump()
        elif hasattr(claims, "__dict__"):
            claims_dict = vars(claims)
        else:
            claims_dict = dict(claims)  # type: ignore[arg-type]

        raw_scopes = claims_dict.get("scopes", claims_dict.get("scope", []))
        if isinstance(raw_scopes, str):
            granted: set[str] = set(raw_scopes.split())
        else:
            granted = set(raw_scopes or [])

        if self._scope not in granted:
            logger.warning(
                "Scope denied: required=%s granted=%s sub=%s",
                self._scope,
                granted,
                claims_dict.get("sub", "unknown"),
            )
            raise HTTP(
                403,
                {
                    "status": "error",
                    "data": {
                        "message": f"Missing required scope: '{self._scope}'"
                    },
                    "meta": {},
                },
            )

    def on_error(self, context: Any, exc: BaseException) -> None:
        """Let HTTP exceptions pass through unchanged."""
        if isinstance(exc, HTTP):
            raise exc
        raise exc
