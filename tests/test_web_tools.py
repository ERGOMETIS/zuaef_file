"""Offline tests for the capability adapters (web_tools).

The adapters bind the ported acquisition/search layer as the local fallbacks
of the native WebSearch/WebFetch capabilities. Contracts: mapping is correct
and neither fetch failures nor search failures ever raise.
"""
from __future__ import annotations

import asyncio

from open_product_research.acquisition import FetchResult
from open_product_research.web_tools import make_local_fetch, make_local_search


class _FakeAcquirer:
    def __init__(self):
        self.calls: list[str] = []

    async def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        return FetchResult(
            url=url,
            final_url=url + "/final",
            title="Bike X200",
            markdown="# X200\nMotor: 750W",
            status_code=200,
        )


class _RaisingAcquirer:
    async def fetch(self, url: str) -> FetchResult:
        raise TimeoutError("site unreachable")


class _FakeSearch:
    async def search(self, query: str):
        return [{"title": "t", "href": "https://x", "body": "b"}]


def test_fetch_adapter_maps_fetch_result():
    tool = make_local_fetch(_FakeAcquirer())
    assert tool.name == "web_fetch_local"
    out = asyncio.run(tool.function("https://brand.example/bike"))
    assert out["url"] == "https://brand.example/bike/final"
    assert out["title"] == "Bike X200"
    assert "750W" in out["content"]


def test_fetch_adapter_returns_failure_note_instead_of_raising():
    tool = make_local_fetch(_RaisingAcquirer())
    out = asyncio.run(tool.function("https://down.example/"))
    assert "FETCH FAILED" in out["content"]
    assert "TimeoutError" in out["content"]
    assert out["url"] == "https://down.example/"


def test_search_adapter_passes_results_through():
    tool = make_local_search(_FakeSearch())
    assert tool.name == "web_search_local"
    out = asyncio.run(tool.function("x200 ebike"))
    assert out == [{"title": "t", "href": "https://x", "body": "b"}]


def test_build_agent_wires_local_backends(monkeypatch):
    from open_product_research.agent import build_agent

    # Keep the test offline: OpenRouterProvider insists on a key at wiring time.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-offline-dummy-key")
    agent = build_agent("openrouter:deepseek/deepseek-v4.1-flash", "/tmp/zuaef-agent-test")
    caps = agent._root_capability.capabilities
    cap_ids = [type(c).__name__ for c in caps]
    assert "WebSearch" in cap_ids
    assert "WebFetch" in cap_ids
    ws = next(c for c in caps if type(c).__name__ == "WebSearch")
    wf = next(c for c in caps if type(c).__name__ == "WebFetch")
    assert ws.local.name == "web_search_local"
    assert wf.local.name == "web_fetch_local"
