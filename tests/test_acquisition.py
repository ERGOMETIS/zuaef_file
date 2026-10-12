"""Offline tests for the acquisition layer. No network — httpx and DNS are monkeypatched."""
from __future__ import annotations

import asyncio
import json
import socket

import pytest

from open_product_research import polite_http, web_security
from open_product_research.acquisition import (
    Crawl4AIProvider,
    FetchResult,
    HttpxProvider,
    ShopifyJsonProvider,
    build_acquirer,
)
from open_product_research.polite_http import PoliteSession, reset_default_session
from open_product_research.web_security import UnsafeUrlError


def _fake_getaddrinfo(*addresses: str):
    def fake(host, port, /, **kwargs):
        return [
            (socket.AF_INET if ":" not in addr else socket.AF_INET6, socket.SOCK_STREAM, 6, "", (addr, 0))
            for addr in addresses
        ]

    return fake


class _FakeResponse:
    def __init__(self, text: str, url: str, status_code: int = 200, headers: dict | None = None) -> None:
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/html"}

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    """Async-context-manager stand-in for httpx.AsyncClient serving canned responses."""

    response: _FakeResponse | None = None
    instantiations = 0

    def __init__(self, *args, **kwargs) -> None:
        type(self).instantiations += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        assert type(self).response is not None
        return type(self).response

    async def post(self, url, **kwargs):
        assert type(self).response is not None
        return type(self).response


class _StubAcquirer:
    def __init__(self, final_url: str = "https://example.com/") -> None:
        self.final_url = final_url
        self.calls: list[str] = []

    async def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        return FetchResult(url=url, final_url=self.final_url, title="stub", markdown="# stub")


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #


def test_build_acquirer_httpx_wraps_in_shopify_provider():
    acquirer = build_acquirer("httpx", timeout_seconds=5.0, proxy_url=None)
    assert isinstance(acquirer, ShopifyJsonProvider)
    assert isinstance(acquirer._fallback, HttpxProvider)
    assert acquirer.timeout_seconds == 5.0


def test_build_acquirer_auto_falls_back_without_crawl4ai():
    try:
        import crawl4ai  # noqa: F401

        pytest.skip("crawl4ai installed; auto path uses Crawl4AIProvider here")
    except ImportError:
        pass
    acquirer = build_acquirer("auto", proxy_url=None)
    assert isinstance(acquirer, ShopifyJsonProvider)
    assert isinstance(acquirer._fallback, HttpxProvider)


def test_build_acquirer_rejects_unknown_provider():
    with pytest.raises(ValueError):
        build_acquirer("browserless")


def test_crawl4ai_provider_raises_unavailable_when_extra_missing():
    try:
        import crawl4ai  # noqa: F401

        pytest.skip("crawl4ai installed; unavailability path not reachable")
    except ImportError:
        pass
    provider = Crawl4AIProvider(timeout_seconds=5.0, allow_proxy_dns=False, proxy_url=None)
    with pytest.raises(Exception) as excinfo:
        asyncio.run(provider.fetch("https://example.com/"))
    # Must be the specific sentinel error, not a bare ImportError.
    assert type(excinfo.value).__name__ == "Crawl4AIUnavailable"



def _fast_session() -> PoliteSession:
    reset_default_session()
    return PoliteSession(min_interval=0.0, max_retries=0)


# --------------------------------------------------------------------------- #
# HttpxProvider — SSRF + fetch
# --------------------------------------------------------------------------- #


def test_httpx_provider_blocks_private_url_before_any_request(monkeypatch):
    monkeypatch.setattr(polite_http.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))
    _FakeAsyncClient.instantiations = 0
    provider = HttpxProvider(timeout_seconds=5.0, allow_proxy_dns=False, proxy_url=None, session=_fast_session())
    with pytest.raises(UnsafeUrlError):
        asyncio.run(provider.fetch("http://localhost/page"))
    # The HTTP client must never be constructed for a blocked URL.
    assert _FakeAsyncClient.instantiations == 0


def test_httpx_provider_fetches_and_truncates(monkeypatch):
    monkeypatch.setattr(polite_http.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    html = "<html><head><title> Demo   Bike </title></head><body>" + "x" * 100_000 + "</body></html>"
    _FakeAsyncClient.response = _FakeResponse(html, "https://example.com/final")
    provider = HttpxProvider(timeout_seconds=5.0, allow_proxy_dns=False, proxy_url=None, session=_fast_session())
    result = asyncio.run(provider.fetch("https://example.com/start"))
    assert result.title == "Demo Bike"
    assert result.final_url == "https://example.com/final"
    assert result.status_code == 200
    assert len(result.markdown) == 80_000  # _MAX_CONTENT_CHARS budget


def test_httpx_provider_rechecks_final_url_for_ssrf(monkeypatch):
    monkeypatch.setattr(polite_http.httpx, "AsyncClient", _FakeAsyncClient)
    resolved: list[str] = ["93.184.216.34", "169.254.169.254"]  # redirect target is metadata

    def getaddrinfo(host, port, /, **kwargs):
        addr = resolved.pop(0) if resolved else "169.254.169.254"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0))]

    monkeypatch.setattr(web_security.socket, "getaddrinfo", getaddrinfo)
    _FakeAsyncClient.response = _FakeResponse("<html></html>", "http://169.254.169.254/")
    provider = HttpxProvider(timeout_seconds=5.0, allow_proxy_dns=False, proxy_url=None, session=_fast_session())
    with pytest.raises(UnsafeUrlError):
        asyncio.run(provider.fetch("https://example.com/"))


# --------------------------------------------------------------------------- #
# ShopifyJsonProvider
# --------------------------------------------------------------------------- #


def test_shopify_json_provider_falls_back_for_non_shopify_url():
    stub = _StubAcquirer()
    provider = ShopifyJsonProvider(stub, timeout_seconds=5.0, allow_proxy_dns=False, proxy_url=None, session=_fast_session())
    result = asyncio.run(provider.fetch("https://brand.example/products/bike"))
    assert stub.calls == ["https://brand.example/products/bike"]
    assert result.markdown == "# stub"


def test_shopify_json_provider_uses_json_fast_path(monkeypatch):
    monkeypatch.setattr(polite_http.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    payload = {
        "product": {
            "title": "Level 4 E-Bike",
            "handle": "level-4",
            "product_type": "Ebikes",
            "vendor": "Aventon",
            "tags": "ebike, commuter",
            "body_html": "<p>Great <b>commuter</b> bike.</p>",
            "variants": [{"title": "Small", "price": "1999.00", "sku": "L4-S", "available": True}],
            "images": [{"src": "//cdn.example/level4.jpg"}],
        }
    }
    _FakeAsyncClient.response = _FakeResponse(
        json.dumps(payload), "https://aventon.com/products/level-4.json"
    )
    stub = _StubAcquirer()
    provider = ShopifyJsonProvider(stub, timeout_seconds=5.0, allow_proxy_dns=False, proxy_url=None, session=_fast_session())
    result = asyncio.run(provider.fetch("https://aventon.com/products/level-4"))
    # JSON fast path served the page — the fallback was never consulted.
    assert stub.calls == []
    assert result.title == "Level 4 E-Bike"
    assert "**Vendor:** Aventon" in result.markdown
    assert "**Price:** $1999.00 USD" in result.markdown
    assert "- ✓ **Small** — $1999.00 (SKU: L4-S)" in result.markdown
    assert "cdn.example/level4.jpg" in result.markdown
    # 10-20x smaller than the 80K full page.
    assert len(result.markdown) < 2_000


def test_shopify_json_provider_serves_store_catalog_for_root_url(monkeypatch):
    monkeypatch.setattr(polite_http.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    payload = {
        "products": [
            {
                "title": "XP Lite",
                "handle": "xp-lite",
                "product_type": "Ebikes",
                "variants": [{"price": "999.00"}, {"price": "1099.00"}],
            },
            {
                "title": "XPremium",
                "handle": "xpremium",
                "product_type": "Ebikes",
                "variants": [{"price": "2399.00"}],
            },
        ]
    }
    _FakeAsyncClient.response = _FakeResponse(
        json.dumps(payload), "https://lectricebikes.com/products.json?limit=50"
    )
    stub = _StubAcquirer()
    provider = ShopifyJsonProvider(stub, timeout_seconds=5.0, allow_proxy_dns=False, proxy_url=None, session=_fast_session())
    result = asyncio.run(provider.fetch("https://lectricebikes.com/"))
    # Catalog fast path served the homepage — the fallback was never consulted.
    assert stub.calls == []
    assert result.title == "Store catalog"
    assert "| XP Lite | xp-lite | Ebikes | 999-1099 |" in result.markdown
    assert "| XPremium | xpremium | Ebikes | 2399 |" in result.markdown
    # Homepage is 80K+ chars; the catalog view is a few K at most.
    assert len(result.markdown) < 2_000


def test_httpx_provider_truncates_shopify_page_but_not_others(monkeypatch):
    monkeypatch.setattr(polite_http.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    html = (
        "<html><head><title>Level 4</title></head><body><nav>"
        + "menu " * 5000
        + "</nav><h1>Specifications</h1><p>Motor: 750W</p><footer>"
        + "junk " * 5000
        + "</footer></body></html>"
    )
    provider = HttpxProvider(timeout_seconds=5.0, allow_proxy_dns=False, proxy_url=None, session=_fast_session())

    # Shopify page: spec-marker truncation collapses the nav/footer noise.
    _FakeAsyncClient.response = _FakeResponse(html, "https://aventon.com/products/level-4")
    result = asyncio.run(provider.fetch("https://aventon.com/products/level-4"))
    assert "Specifications" in result.markdown
    assert "750W" in result.markdown
    assert "menu menu" not in result.markdown
    assert len(result.markdown) <= 8_000

    # Non-Shopify page: legacy raw-HTML path preserved (hrefs for discovery).
    _FakeAsyncClient.response = _FakeResponse(html, "https://brand.example/products/level-4")
    result2 = asyncio.run(provider.fetch("https://brand.example/products/level-4"))
    assert result2.markdown == html


def test_shopify_json_provider_serves_catalog_for_collections_url(monkeypatch):
    monkeypatch.setattr(polite_http.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(web_security.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    payload = {
        "products": [
            {
                "title": "SUPER73-S2",
                "handle": "super73-s2",
                "product_type": "Bikes",
                "variants": [{"price": "2995.00"}],
            }
        ]
    }
    _FakeAsyncClient.response = _FakeResponse(
        json.dumps(payload), "https://super73.com/products.json?limit=50"
    )
    stub = _StubAcquirer()
    provider = ShopifyJsonProvider(
        stub, timeout_seconds=5.0, allow_proxy_dns=False, proxy_url=None, session=_fast_session()
    )
    result = asyncio.run(provider.fetch("https://super73.com/collections/electric-bikes"))
    assert stub.calls == []
    assert "SUPER73-S2" in result.markdown
    assert "products.json" in result.markdown
    assert "super73.com/collections/electric-bikes" in result.markdown
