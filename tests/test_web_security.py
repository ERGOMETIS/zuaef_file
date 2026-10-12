"""Offline tests for the SSRF guard. No real DNS — getaddrinfo is monkeypatched."""
from __future__ import annotations

import asyncio
import socket

import pytest

from open_product_research import web_security
from open_product_research.web_security import (
    UnsafeUrlError,
    assert_public_url,
    normalize_url,
)


def _fake_getaddrinfo(*addresses: str):
    def fake(host, port, /, **kwargs):
        return [
            (socket.AF_INET if ":" not in addr else socket.AF_INET6, socket.SOCK_STREAM, 6, "", (addr, 0))
            for addr in addresses
        ]

    return fake


# --------------------------------------------------------------------------- #
# normalize_url
# --------------------------------------------------------------------------- #


def test_normalize_url_accepts_http_and_https():
    assert normalize_url("https://example.com/path?q=1") == "https://example.com/path?q=1"
    assert normalize_url("http://example.com/") == "http://example.com/"


def test_normalize_url_strips_fragment():
    assert normalize_url("https://example.com/page#section-2") == "https://example.com/page"


def test_normalize_url_rejects_embedded_credentials():
    with pytest.raises(UnsafeUrlError):
        normalize_url("https://user:pass@example.com/")
    with pytest.raises(UnsafeUrlError):
        normalize_url("https://user@example.com/")


def test_normalize_url_rejects_missing_hostname():
    with pytest.raises(UnsafeUrlError):
        normalize_url("https:///just-a-path")


def test_normalize_url_rejects_non_http_schemes():
    with pytest.raises(UnsafeUrlError):
        normalize_url("ftp://example.com/file")
    with pytest.raises(UnsafeUrlError):
        normalize_url("file:///etc/passwd")


# --------------------------------------------------------------------------- #
# assert_public_url — DNS monkeypatched, zero network
# --------------------------------------------------------------------------- #


def test_assert_public_url_rejects_localhost(monkeypatch):
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))
    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_public_url("http://localhost/admin"))


def test_assert_public_url_rejects_loopback_ip(monkeypatch):
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))
    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_public_url("http://127.0.0.1:8080/"))


def test_assert_public_url_rejects_cloud_metadata(monkeypatch):
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("169.254.169.254"))
    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_public_url("http://169.254.169.254/latest/meta-data/"))


def test_assert_public_url_rejects_ipv6_loopback(monkeypatch):
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("::1"))
    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_public_url("http://[::1]/"))


def test_assert_public_url_rejects_private_range(monkeypatch):
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("10.0.0.5"))
    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_public_url("https://internal.example.com/"))


def test_assert_public_url_rejects_unresolvable_host(monkeypatch):
    def gaierror(host, port, /, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(web_security.socket, "getaddrinfo", gaierror)
    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_public_url("https://does-not-resolve.example.com/"))


def test_assert_public_url_accepts_public_address(monkeypatch):
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    result = asyncio.run(assert_public_url("https://example.com/page#frag"))
    assert result == "https://example.com/page"


def test_proxy_dns_mode_allows_private_but_keeps_hard_blocklist(monkeypatch):
    # Behind a transparent proxy, a private pool address is tolerated...
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("10.1.2.3"))
    assert asyncio.run(assert_public_url("https://example.com/", allow_proxy_dns=True)) == (
        "https://example.com/"
    )
    # ...but metadata endpoints stay blocked in every mode.
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("169.254.169.254"))
    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_public_url("http://metadata.internal/", allow_proxy_dns=True))
    # ...and so does loopback.
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))
    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_public_url("http://localhost/", allow_proxy_dns=True))
