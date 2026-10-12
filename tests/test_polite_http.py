"""Offline unit tests for polite HTTP pacing, retry, cache and fetch log."""
from __future__ import annotations

import asyncio
import json
from typing import ClassVar

import httpx
import pytest

from open_product_research import polite_http
from open_product_research.polite_http import (
    PoliteSession,
    reset_default_session,
    retry_after_seconds,
)


class _FakeRaw:
    def __init__(self, text: str, url: str, status_code: int = 200, headers: dict | None = None):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/html"}


class _FakeAsyncClient:
    """Scripted httpx.AsyncClient stand-in. Queue of responses (or callables)."""

    queue: ClassVar[list] = []
    calls: ClassVar[list] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        type(self).calls.append(url)
        assert type(self).queue, f"unexpected GET {url}"
        item = type(self).queue.pop(0)
        if callable(item):
            item = item(url)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _clean_session(monkeypatch, tmp_path):
    reset_default_session()
    _FakeAsyncClient.queue = []
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(polite_http.httpx, "AsyncClient", _FakeAsyncClient)
    yield
    reset_default_session()


def test_retry_after_honors_header():
    assert retry_after_seconds({"Retry-After": "7"}, 0) == 7.0
    assert retry_after_seconds({"retry-after": "1.5"}, 2) == 1.5


def test_retry_after_jitter_without_header():
    values = {retry_after_seconds({}, 0) for _ in range(20)}
    assert min(values) >= 0.0
    assert max(values) <= 2.0  # base 2.0 * 2^0


def test_cache_hit_skips_second_network_call(tmp_path):
    log_path = tmp_path / "fetch_log.jsonl"
    session = PoliteSession(min_interval=0.0, max_retries=1, fetch_log_path=log_path)
    _FakeAsyncClient.queue = [_FakeRaw("<html>ok</html>", "https://example.com/a")]

    async def run():
        a = await session.aget("https://example.com/a", timeout=5.0)
        b = await session.aget("https://example.com/a", timeout=5.0)
        return a, b

    a, b = asyncio.run(run())
    assert a.text == b.text == "<html>ok</html>"
    assert _FakeAsyncClient.calls == ["https://example.com/a"]  # only once
    lines = [json.loads(x) for x in log_path.read_text().splitlines()]
    assert lines[0]["cached"] is False
    assert lines[1]["cached"] is True


def test_429_retries_then_succeeds(tmp_path, monkeypatch):
    log_path = tmp_path / "fetch_log.jsonl"
    session = PoliteSession(min_interval=0.0, max_retries=3, fetch_log_path=log_path)
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(polite_http.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(polite_http.random, "uniform", lambda a, b: b)  # deterministic

    _FakeAsyncClient.queue = [
        _FakeRaw("nope", "https://brand.example/p", 429, {"retry-after": "0.01"}),
        _FakeRaw("nope", "https://brand.example/p", 429, {"retry-after": "0.01"}),
        _FakeRaw("<html>ok</html>", "https://brand.example/p", 200),
    ]

    result = asyncio.run(session.aget("https://brand.example/p", timeout=5.0))
    assert result.status_code == 200
    assert result.text == "<html>ok</html>"
    assert len(_FakeAsyncClient.calls) == 3
    assert sleeps  # backed off
    lines = [json.loads(x) for x in log_path.read_text().splitlines()]
    assert any(line.get("retrying") for line in lines)
    assert lines[-1]["status"] == 200


def test_429_exhausted_returns_last_response(monkeypatch):
    session = PoliteSession(min_interval=0.0, max_retries=1)

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(polite_http.asyncio, "sleep", fake_sleep)
    _FakeAsyncClient.queue = [
        _FakeRaw("no", "https://brand.example/x", 429, {"retry-after": "0"}),
        _FakeRaw("still no", "https://brand.example/x", 429, {"retry-after": "0"}),
    ]
    result = asyncio.run(session.aget("https://brand.example/x", timeout=5.0))
    assert result.status_code == 429
    with pytest.raises(httpx.HTTPStatusError):
        result.raise_for_status()


def test_host_gate_serializes_same_host(monkeypatch):
    session = PoliteSession(min_interval=0.05, max_retries=0)
    order: list[str] = []

    async def run():
        async def one(name: str, url: str):
            order.append(f"start-{name}")
            await session.aget(url, timeout=5.0)
            order.append(f"end-{name}")

        _FakeAsyncClient.queue = [
            _FakeRaw("a", "https://same.example/1"),
            _FakeRaw("b", "https://same.example/2"),
        ]
        await asyncio.gather(
            one("a", "https://same.example/1"),
            one("b", "https://same.example/2"),
        )

    asyncio.run(run())
    # Both completed; gate does not deadlock.
    assert set(order) == {"start-a", "end-a", "start-b", "end-b"}
    assert len(_FakeAsyncClient.calls) == 2


def test_browser_ua_sent(monkeypatch):
    session = PoliteSession(min_interval=0.0, max_retries=0)
    seen: dict = {}

    class CapturingClient(_FakeAsyncClient):
        async def get(self, url, **kwargs):
            seen["headers"] = kwargs.get("headers") or {}
            return await super().get(url, **kwargs)

    monkeypatch.setattr(polite_http.httpx, "AsyncClient", CapturingClient)
    _FakeAsyncClient.queue = [_FakeRaw("ok", "https://example.com/")]
    asyncio.run(session.aget("https://example.com/", timeout=5.0))
    ua = seen["headers"].get("User-Agent", "")
    assert "Mozilla/5.0" in ua
    assert "Chrome" in ua


def test_429_terminal_is_cached(monkeypatch):
    session = PoliteSession(min_interval=0.0, max_retries=0)

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(polite_http.asyncio, "sleep", fake_sleep)
    _FakeAsyncClient.queue = [
        _FakeRaw("no", "https://brand.example/x", 429, {"retry-after": "0"}),
    ]
    first = asyncio.run(session.aget("https://brand.example/x", timeout=5.0))
    assert first.status_code == 429
    # Second call must not hit the network again.
    second = asyncio.run(session.aget("https://brand.example/x", timeout=5.0))
    assert second.status_code == 429
    assert _FakeAsyncClient.calls == ["https://brand.example/x"]
