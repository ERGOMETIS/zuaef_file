"""Offline tests for the search provider layer.

Contract under test (spec §13): a failed query must NEVER raise — it returns
the standard _no_results_marker payload so the agent records an evidence gap.
Zero network: httpx is always monkeypatched.
"""
from __future__ import annotations

import asyncio

import pytest

from open_product_research import search
from open_product_research.search import (
    BraveProvider,
    DuckDuckGoProvider,
    TavilyProvider,
    _no_results_marker,
    build_search_provider,
)


def _boom_client_factory(monkeypatch):
    """Replace httpx.AsyncClient with one whose context entry always fails."""

    class _Boom:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            raise ConnectionError("network down")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(search.httpx, "AsyncClient", _Boom)


def test_no_results_marker_shape():
    marker = _no_results_marker("vantable x200", "Tavily error: ConnectError")
    assert len(marker) == 1
    item = marker[0]
    assert set(item) == {"title", "href", "body"}
    assert "vantable x200" in item["body"]
    assert item["title"] == "(no results)"


def test_build_search_provider_auto_without_keys_is_duckduckgo(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    provider = build_search_provider("auto")
    assert isinstance(provider, DuckDuckGoProvider)


def test_build_search_provider_auto_prefers_tavily(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("BRAVE_API_KEY", "brave-test")
    provider = build_search_provider("auto")
    assert isinstance(provider, TavilyProvider)


def test_build_search_provider_tavily_without_key_raises(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(ValueError):
        build_search_provider("tavily")


def test_tavily_failure_returns_marker_not_raise(monkeypatch):
    _boom_client_factory(monkeypatch)
    provider = TavilyProvider(api_key="k", timeout_seconds=5, proxy_url=None)
    results = asyncio.run(provider.search("ebike motor supplier germany"))
    assert results[0]["title"] == "(no results)"
    assert "Tavily error" in results[0]["body"]


def test_brave_failure_returns_marker_not_raise(monkeypatch):
    _boom_client_factory(monkeypatch)
    provider = BraveProvider(api_key="k", timeout_seconds=5, proxy_url=None)
    results = asyncio.run(provider.search("cargo bike oem netherlands"))
    assert results[0]["title"] == "(no results)"
