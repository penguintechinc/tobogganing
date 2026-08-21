"""SSRF guard for user-supplied feed source URLs.

A tenant-controlled URL that the server fetches server-side (feed source
create/refresh) is a classic SSRF vector — without this guard an
authenticated threatintel:write user could point a feed at cloud metadata
(169.254.169.254), loopback, or internal-only services and have the server
fetch it on their behalf. Every fetch path (initial request and each
redirect hop) must re-validate: DNS can rebind between validation and use.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = frozenset({"http", "https"})


class UnsafeFeedURLError(ValueError):
    """Raised when a feed source URL is disallowed by the SSRF guard.

    Covers: non-http(s) scheme, unresolvable host, or any resolved address
    that is private (RFC1918), loopback, link-local (incl. 169.254.169.254
    cloud metadata), reserved, unspecified, or multicast.
    """


def _resolve_addresses_sync(host: str) -> list[str]:
    """Blocking DNS resolution helper — always call via asyncio.to_thread."""
    addrinfo = socket.getaddrinfo(host, None)
    return [sockaddr[0] for _family, _type, _proto, _canon, sockaddr in addrinfo]


async def assert_safe_feed_url(url: str) -> None:
    """Validate a feed source URL is safe to fetch server-side (SSRF guard).

    Enforces an http(s) scheme, then resolves the hostname and rejects the
    URL if ANY resolved address is private/loopback/link-local/reserved/
    unspecified/multicast (covers 10/8, 172.16/12, 192.168/16, 127/8,
    169.254/16, fc00::/7, fe80::/10, ::, etc.).

    Call this at feed-source creation AND immediately before every fetch
    (initial request and each redirect hop) — DNS can change or rebind
    between validation and use (TOCTOU).

    Args:
        url: The feed source URL to validate.

    Raises:
        UnsafeFeedURLError: If the scheme, host, or any resolved address
            is disallowed.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeFeedURLError(f"unsupported URL scheme: {parsed.scheme!r}")

    host = parsed.hostname
    if not host:
        raise UnsafeFeedURLError("URL has no hostname")

    try:
        addresses = await asyncio.to_thread(_resolve_addresses_sync, host)
    except socket.gaierror as e:
        raise UnsafeFeedURLError(f"could not resolve host: {host!r}") from e

    if not addresses:
        raise UnsafeFeedURLError(f"could not resolve host: {host!r}")

    for addr_str in addresses:
        try:
            addr = ipaddress.ip_address(addr_str)
        except ValueError as e:
            raise UnsafeFeedURLError(f"unparseable resolved address for host {host!r}") from e

        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_unspecified
            or addr.is_multicast
        ):
            raise UnsafeFeedURLError(
                f"host {host!r} resolves to a disallowed private/internal address"
            )
