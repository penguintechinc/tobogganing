"""Tests for gRPC security interceptors.

Covers the AuthInterceptor scope-based authorization path and the
RateLimitInterceptor JWT-verification fix — regression coverage for a
forged `sub` claim previously accepted via an unverified decode.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import grpc
import jwt

from py_libs.grpc.interceptors import AuthInterceptor, RateLimitInterceptor

SECRET = "correct-horse-battery-staple"  # noqa: S105 - test fixture secret
ATTACKER_SECRET = "attacker-controlled-secret"  # noqa: S105


@dataclass
class FakeHandlerCallDetails:
    """Minimal stand-in for grpc.HandlerCallDetails."""

    method: str
    invocation_metadata: list[tuple[str, str]]


class FakeContext:
    """Captures context.abort() calls instead of raising into grpc internals."""

    def __init__(self) -> None:
        self.aborted: tuple[grpc.StatusCode, str] | None = None

    def abort(self, code: grpc.StatusCode, details: str) -> None:
        self.aborted = (code, details)


def make_continuation() -> Callable[[Any], str]:
    """Continuation stub that returns a sentinel so tests can assert it ran."""

    def continuation(_handler_call_details: Any) -> str:
        return "SENTINEL_HANDLER"

    return continuation


def make_token(secret: str, **claims: Any) -> str:
    payload = {"sub": "user-123", "exp": time.time() + 300, **claims}
    return jwt.encode(payload, secret, algorithm="HS256")


def call(
    interceptor: grpc.ServerInterceptor,
    method: str,
    token: str | None,
) -> tuple[Any, FakeContext | None]:
    """Invoke intercept_service and, if aborted, drive the abort handler."""
    metadata = [("authorization", f"Bearer {token}")] if token else []
    hcd = FakeHandlerCallDetails(method=method, invocation_metadata=metadata)
    continuation = make_continuation()
    result = interceptor.intercept_service(continuation, hcd)

    if result == "SENTINEL_HANDLER":
        return result, None

    context = FakeContext()
    result.unary_unary(None, context)  # type: ignore[union-attr]
    return result, context


class TestAuthInterceptorScopeAuthorization:
    """AuthInterceptor.method_scopes — scope-based authz (never role names)."""

    def test_public_method_skips_auth_entirely(self) -> None:
        interceptor = AuthInterceptor(secret_key=SECRET, public_methods={"/svc/Public"})
        result, ctx = call(interceptor, "/svc/Public", token=None)
        assert result == "SENTINEL_HANDLER"
        assert ctx is None

    def test_missing_auth_header_is_unauthenticated(self) -> None:
        interceptor = AuthInterceptor(secret_key=SECRET)
        result, ctx = call(interceptor, "/svc/Method", token=None)
        assert ctx is not None
        assert ctx.aborted == (
            grpc.StatusCode.UNAUTHENTICATED,
            "Missing or invalid authorization header",
        )

    def test_valid_token_with_no_scope_requirement_is_authenticated_only(self) -> None:
        interceptor = AuthInterceptor(secret_key=SECRET)
        token = make_token(SECRET, scope="anything:here")
        result, ctx = call(interceptor, "/svc/Method", token=token)
        assert result == "SENTINEL_HANDLER"
        assert ctx is None

    def test_valid_token_with_sufficient_scope_is_authorized(self) -> None:
        interceptor = AuthInterceptor(
            secret_key=SECRET,
            method_scopes={"/svc/DeleteWidget": {"widgets:delete"}},
        )
        token = make_token(SECRET, scope="widgets:read widgets:delete")
        result, ctx = call(interceptor, "/svc/DeleteWidget", token=token)
        assert result == "SENTINEL_HANDLER"
        assert ctx is None

    def test_valid_token_with_insufficient_scope_is_denied(self) -> None:
        interceptor = AuthInterceptor(
            secret_key=SECRET,
            method_scopes={"/svc/DeleteWidget": {"widgets:delete"}},
        )
        token = make_token(SECRET, scope="widgets:read")
        result, ctx = call(interceptor, "/svc/DeleteWidget", token=token)
        assert ctx is not None
        assert ctx.aborted == (
            grpc.StatusCode.PERMISSION_DENIED,
            "Insufficient scope for this operation",
        )

    def test_missing_scope_claim_is_denied_when_scope_required(self) -> None:
        interceptor = AuthInterceptor(
            secret_key=SECRET,
            method_scopes={"/svc/DeleteWidget": {"widgets:delete"}},
        )
        token = jwt.encode({"sub": "user-1", "exp": time.time() + 300}, SECRET, algorithm="HS256")
        result, ctx = call(interceptor, "/svc/DeleteWidget", token=token)
        assert ctx is not None
        assert ctx.aborted is not None
        assert ctx.aborted[0] == grpc.StatusCode.PERMISSION_DENIED

    def test_expired_token_is_unauthenticated(self) -> None:
        interceptor = AuthInterceptor(secret_key=SECRET)
        token = jwt.encode({"sub": "user-1", "exp": time.time() - 10}, SECRET, algorithm="HS256")
        result, ctx = call(interceptor, "/svc/Method", token=token)
        assert ctx is not None
        assert ctx.aborted == (grpc.StatusCode.UNAUTHENTICATED, "Token has expired")

    def test_forged_signature_is_rejected(self) -> None:
        interceptor = AuthInterceptor(secret_key=SECRET)
        forged = make_token(ATTACKER_SECRET, scope="admin:write")
        result, ctx = call(interceptor, "/svc/Method", token=forged)
        assert ctx is not None
        assert ctx.aborted == (grpc.StatusCode.UNAUTHENTICATED, "Invalid token")


class TestRateLimitInterceptorSignatureVerification:
    """RateLimitInterceptor must verify JWT signatures before trusting `sub`.

    Regression coverage for the prior `jwt.decode(..., options={"verify_signature":
    False})` bug — an attacker could set an arbitrary `sub` claim to dodge their
    own rate limit or frame another client's identity.
    """

    def test_verified_token_uses_real_sub_as_client_id(self) -> None:
        interceptor = RateLimitInterceptor(requests_per_minute=5, per_user=True, secret_key=SECRET)
        token = make_token(SECRET, sub="alice")
        result, ctx = call(interceptor, "/svc/Method", token=token)
        assert result == "SENTINEL_HANDLER"
        assert "alice" in interceptor.limits
        assert interceptor.limits["alice"].count == 1

    def test_forged_token_does_not_impersonate_victim_identity(self) -> None:
        """A token signed with the wrong key must never land in the victim's bucket."""
        interceptor = RateLimitInterceptor(requests_per_minute=5, per_user=True, secret_key=SECRET)
        forged = make_token(ATTACKER_SECRET, sub="victim")
        result, ctx = call(interceptor, "/svc/Method", token=forged)
        assert result == "SENTINEL_HANDLER"
        assert "victim" not in interceptor.limits
        assert "anonymous" in interceptor.limits

    def test_without_secret_key_falls_back_to_ip_not_unverified_sub(self) -> None:
        interceptor = RateLimitInterceptor(requests_per_minute=5, per_user=True)
        forged = make_token(ATTACKER_SECRET, sub="victim")
        hcd = FakeHandlerCallDetails(
            method="/svc/Method",
            invocation_metadata=[
                ("authorization", f"Bearer {forged}"),
                ("x-forwarded-for", "203.0.113.5"),
            ],
        )
        continuation = make_continuation()
        result = interceptor.intercept_service(continuation, hcd)
        assert result == "SENTINEL_HANDLER"
        assert "victim" not in interceptor.limits
        assert "203.0.113.5" in interceptor.limits

    def test_per_ip_mode_uses_forwarded_for_header(self) -> None:
        interceptor = RateLimitInterceptor(requests_per_minute=5, per_user=False)
        hcd = FakeHandlerCallDetails(
            method="/svc/Method",
            invocation_metadata=[("x-forwarded-for", "198.51.100.1")],
        )
        continuation = make_continuation()
        interceptor.intercept_service(continuation, hcd)
        assert "198.51.100.1" in interceptor.limits

    def test_rate_limit_exceeded_aborts_resource_exhausted(self) -> None:
        interceptor = RateLimitInterceptor(requests_per_minute=1, per_user=True, secret_key=SECRET)
        token = make_token(SECRET, sub="bob")

        first_result, first_ctx = call(interceptor, "/svc/Method", token=token)
        assert first_result == "SENTINEL_HANDLER"

        second_result, second_ctx = call(interceptor, "/svc/Method", token=token)
        assert second_ctx is not None
        assert second_ctx.aborted == (grpc.StatusCode.RESOURCE_EXHAUSTED, "Rate limit exceeded")
