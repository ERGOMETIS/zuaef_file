"""SSRF guard for every outbound URL the agent touches.

Ported from product_research_agent v0.2.0, stripped of the DB-backed
``SourceVerifier`` workflow (the new base has no source-verification tables).
What remains is the reusable core: URL normalization plus the two-layer IP
policy.

Two-layer block policy (do not weaken):

* ``_is_public_ip`` — the strict default. Any non-public address (private,
  loopback, link-local, multicast, reserved, unspecified) is rejected.
* ``_is_hard_blocked_ip`` — the permanent blocklist used when
  ``allow_proxy_dns=True`` (transparent-proxy hosts where every hostname maps
  onto a virtual pool, so the strict test would block legitimate sources).
  Loopback, link-local, unspecified and the cloud metadata endpoints stay
  blocked in every mode: they expose host credentials to anyone who can reach
  them, which is exactly what the SSRF guard exists to prevent.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit


class UnsafeUrlError(ValueError):
    """A URL failed normalization or resolved to a non-public address."""


def normalize_url(url: str) -> str:
    """Validate and canonicalize a URL, stripping the fragment."""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in {"http", "https"}:
        raise UnsafeUrlError("only http and https URLs are allowed")
    if not parts.hostname:
        raise UnsafeUrlError("URL must include a hostname")
    host = parts.hostname.lower().rstrip(".")
    if parts.username or parts.password:
        raise UnsafeUrlError("URLs with embedded credentials are not allowed")
    port = parts.port
    try:
        parsed_ip = ipaddress.ip_address(host)
        display_host = f"[{host}]" if parsed_ip.version == 6 else host
    except ValueError:
        display_host = host
    netloc = display_host if port is None else f"{display_host}:{port}"
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def _is_public_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


# Cloud instance metadata endpoints and similar host-local control planes.
# These must be blocked regardless of any proxy relaxation, because they expose
# credentials to anyone who can reach them from the host.
_METADATA_ENDPOINTS = {
    ipaddress.ip_address("169.254.169.254"),  # AWS / Azure / GCP metadata
    ipaddress.ip_address("fd00:ec2::254"),  # AWS IMDS IPv6
}


def _is_hard_blocked_ip(value: str) -> bool:
    """Addresses that must never be reached, even when proxy DNS is allowed.

    Loopback, link-local, unspecified and cloud metadata endpoints remain blocked
    so the SSRF intent (prevent the agent from reaching host-local control
    planes) is preserved when running behind a transparent proxy.
    """
    ip = ipaddress.ip_address(value)
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_unspecified
        or ip in _METADATA_ENDPOINTS
    )


async def assert_public_url(url: str, *, allow_proxy_dns: bool = False) -> str:
    """Resolve ``url``'s host and reject non-public addresses.

    Returns the normalized URL on success, raises ``UnsafeUrlError`` otherwise.
    With ``allow_proxy_dns=True`` only the hard blocklist (loopback /
    link-local / metadata) applies — the transparent-proxy relaxation.
    """
    normalized = normalize_url(url)
    host = urlsplit(normalized).hostname
    assert host is not None

    def _resolve() -> set[str]:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        return {str(item[4][0]) for item in infos}

    try:
        addresses = await asyncio.to_thread(_resolve)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"hostname resolution failed: {host}") from exc
    if not addresses:
        raise UnsafeUrlError(f"hostname resolution returned no addresses: {host}")
    if allow_proxy_dns:
        # Behind a transparent proxy: every hostname maps onto a virtual pool,
        # so the strict public-IP test would block legitimate sources. Keep only
        # the hard blocklist (loopback / link-local / metadata) and accept the rest.
        blocked = any(_is_hard_blocked_ip(addr) for addr in addresses)
        verdict = "hard-blocked"
    else:
        # Direct-connection default: reject if any resolved address is non-public.
        blocked = any(not _is_public_ip(addr) for addr in addresses)
        verdict = "non-public"
    if blocked:
        raise UnsafeUrlError(f"hostname resolves to a {verdict} address: {host}")
    return normalized


__all__ = [
    "UnsafeUrlError",
    "assert_public_url",
    "normalize_url",
]
