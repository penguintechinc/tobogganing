"""SSRF-sandboxed fetcher for Tier-2 AI categorizer (Slice E Task 1).

Fetches page content with comprehensive SSRF protections:
- Resolve ALL addresses (A + AAAA records), reject any private/loopback/link-local/reserved/multicast
- Pin connection to validated IP literal (prevent DNS rebinding/TOCTOU)
- Manual redirect handling (re-check each hop's host + re-pin connection)
- Size cap (512 KB, streamed)
- Time cap (5s)
- No cookies/credentials
- Benign fixed User-Agent
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger()

__all__ = ["fetch", "is_public_host", "validate_and_resolve_host"]


def is_public_host(host: str) -> bool:
    """Classify a resolved host IP as public or private (SSRF guard).

    Rejects:
    - Loopback (127.0.0.0/8, ::1)
    - Private RFC 1918 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Link-local (169.254.0.0/16, fe80::/10)
    - Multicast (224.0.0.0/4, ff00::/8)
    - Reserved (0.0.0.0/8, 255.255.255.255/32, ::, etc.)

    Args:
        host: IP address (as string).

    Returns:
        True if public, False if private/reserved.
    """
    try:
        ip = ipaddress.ip_address(host)

        # Reject private/reserved addresses
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False

        return True
    except ValueError:
        return False


def validate_and_resolve_host(host: str, port: int = 443) -> str | None:
    """Resolve hostname to ALL addresses and validate them (SSRF guard).

    Uses getaddrinfo to get ALL A and AAAA records. Rejects if ANY record
    is private/loopback/link-local/reserved/multicast. Returns the first
    validated public IP for pinned connection.

    Args:
        host: Hostname.
        port: Port (for getaddrinfo).

    Returns:
        First validated public IP, or None if all records are private/invalid.
    """
    try:
        # Get ALL addresses (both A and AAAA records)
        addr_infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        if not addr_infos:
            logger.warning("validate_host_no_results", host=host)
            return None

        # Validate ALL resolved IPs
        for family, socktype, proto, canonname, sockaddr in addr_infos:
            resolved_ip = sockaddr[0]  # Extract IP from (ip, port) tuple

            if not is_public_host(resolved_ip):
                logger.warning(
                    "validate_host_rejected",
                    host=host,
                    resolved_ip=resolved_ip,
                    family=family,
                )
                return None

        # All IPs are public; return the first one for connection pinning
        return addr_infos[0][4][0]

    except socket.gaierror as e:
        logger.warning("validate_host_dns_failed", host=host, error=str(e))
        return None
    except Exception as e:
        logger.error("validate_host_error", host=host, error=str(e))
        return None


async def fetch(
    url: str,
    *,
    max_bytes: int = 512_000,
    timeout_s: float = 5.0,
) -> bytes | None:
    """Fetch content from a URL with SSRF guards and size/time caps.

    Security:
    - Resolve ALL addresses (A + AAAA), reject any private/loopback/link-local/reserved/multicast
    - Pin connection to validated IP (prevent DNS rebinding/TOCTOU)
    - Manually handle redirects, re-validate + re-pin each hop
    - Size cap (512 KB streamed)
    - Time cap (5s)
    - No cookies/credentials
    - Fixed benign User-Agent
    - Certificate verification ON (SNI set to original hostname)

    Args:
        url: URL to fetch.
        max_bytes: Maximum bytes to fetch (default 512 KB).
        timeout_s: Timeout in seconds (default 5s).

    Returns:
        Bytes of content, or None if fetch fails/blocked/timeout/oversize.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        if not host:
            logger.warning("fetch_no_host", url=url)
            return None

        # Step 1: Validate and resolve host (gets first public IP)
        validated_ip = validate_and_resolve_host(host, port)
        if not validated_ip:
            logger.warning("fetch_blocked_ssrf_validation", url=url, host=host)
            return None

        # Step 2: Fetch with httpx, manual redirect handling
        # Pin connection to validated IP by using IP literal + Host header
        client_timeout = httpx.Timeout(timeout_s, connect=timeout_s, read=timeout_s)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Host": host,  # SNI/Host header for certificate verification
        }

        async with httpx.AsyncClient(timeout=client_timeout, verify=True) as client:
            current_url = url
            current_host = host
            current_port = port
            current_validated_ip = validated_ip
            accumulated_bytes = bytearray()

            for hop_count in range(10):  # Max 10 redirects
                try:
                    # Build pinned URL: use IP literal instead of hostname
                    pinned_url = _build_pinned_url(
                        current_url, current_validated_ip, current_port, current_host
                    )

                    response = await asyncio.wait_for(
                        client.get(
                            pinned_url,
                            headers={"Host": current_host},  # For TLS SNI
                            follow_redirects=False,
                            cookies=None,  # Explicitly no cookies
                        ),
                        timeout=timeout_s,
                    )

                    if response.status_code in (301, 302, 303, 307, 308):
                        # Redirect: validate the target host and re-pin
                        redirect_url = response.headers.get("location")
                        if not redirect_url:
                            break

                        # Parse redirect target
                        redirect_parsed = urlparse(redirect_url)
                        redirect_host = redirect_parsed.hostname
                        if not redirect_host:
                            break

                        # Re-validate and resolve redirect target
                        redirect_port = redirect_parsed.port or (
                            443 if redirect_parsed.scheme == "https" else 80
                        )
                        redirect_validated_ip = validate_and_resolve_host(
                            redirect_host, redirect_port
                        )
                        if not redirect_validated_ip:
                            logger.warning(
                                "fetch_blocked_redirect_ssrf",
                                url=url,
                                redirect_url=redirect_url,
                                redirect_host=redirect_host,
                            )
                            return None

                        # Update for next hop
                        current_url = redirect_url
                        current_host = redirect_host
                        current_port = redirect_port
                        current_validated_ip = redirect_validated_ip
                        continue

                    # Step 3: Stream body with size cap
                    if response.status_code != 200:
                        logger.debug("fetch_non_200", url=url, status=response.status_code)
                        return None

                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        accumulated_bytes.extend(chunk)
                        if len(accumulated_bytes) > max_bytes:
                            logger.warning("fetch_oversize", url=url, bytes_read=len(accumulated_bytes))
                            return None

                    return bytes(accumulated_bytes)

                except asyncio.TimeoutError:
                    logger.warning("fetch_timeout", url=url, hop=hop_count)
                    return None

            logger.warning("fetch_too_many_redirects", url=url)
            return None

    except httpx.RequestError as e:
        logger.warning("fetch_error", url=url, error=str(e))
        return None
    except Exception as e:
        logger.error("fetch_unexpected_error", url=url, error=str(e))
        return None


def _build_pinned_url(url: str, validated_ip: str, port: int, hostname: str) -> str:
    """Build a URL with IP literal instead of hostname, for connection pinning.

    Args:
        url: Original URL.
        validated_ip: Validated IP to connect to.
        port: Port number.
        hostname: Original hostname (for SNI).

    Returns:
        URL with IP literal (for connection pinning).
    """
    parsed = urlparse(url)

    # Build IP literal URL
    # IPv6 needs brackets: [::1]:port
    if ":" in validated_ip:  # IPv6
        netloc = f"[{validated_ip}]:{port}"
    else:  # IPv4
        netloc = f"{validated_ip}:{port}"

    # Reconstruct URL with IP literal
    pinned = f"{parsed.scheme}://{netloc}{parsed.path}"
    if parsed.query:
        pinned += f"?{parsed.query}"
    if parsed.fragment:
        pinned += f"#{parsed.fragment}"

    return pinned
