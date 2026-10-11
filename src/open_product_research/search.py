"""Search provider layer — the search-side twin of ``acquisition.py``.

Ported from product_research_agent v0.2.0, with Settings replaced by plain
function arguments and ``os.environ`` reads. The hard-won lessons are kept:

The agent's ``web_search`` capability used to call DuckDuckGo directly. On
hosts where DuckDuckGo is network-blocked (observed: a TUN proxy maps
duckduckgo.com to a node that completes the TCP handshake but never returns
application data, so the call hangs in ``ep_poll`` and never raises), the
agent is stuck on its very first query with zero sources and zero claims.

Following the same provider/adapter shape as the fetch layer, this module
exposes Tavily and Brave as alternative search backends behind one
``SearchProvider`` protocol. They are not new capabilities or new agents —
they are implementation details of the existing ``web_search`` capability.

Contract shared by every provider: **a failed query must not raise**. It
returns a clearly-marked no-results list so the agent records an evidence gap
instead of aborting the whole job.

Both Tavily and Brave are plain ``httpx`` REST calls, so — unlike crawl4ai —
no optional dependency is needed. API keys come from the provider-canonical
environment variables ``TAVILY_API_KEY`` / ``BRAVE_API_KEY`` (or explicit
constructor/factory arguments).
"""

from __future__ import annotations

import logging
import os
from typing import Protocol, cast

import httpx

log = logging.getLogger(__name__)

# Result schema kept compatible with the legacy DuckDuckGo tool so the agent's
# prompt and downstream parsing do not change when the backend switches.
# Keys: title, href (URL), body (snippet).

_TAVILY_ENDPOINT = "https://api.tavily.com/search"
_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_DEFAULT_MAX_RESULTS = 8
_SEARCH_TIMEOUT_FALLBACK = 30.0


def _no_results_marker(query: str, reason: str) -> list[dict[str, str]]:
    """Standard "missing data is an honest gap" payload."""
    return [
        {
            "title": "(no results)",
            "href": "",
            "body": (
                f"The search for {query!r} returned no usable results ({reason}). "
                "Reformulate the query, try a different angle, or record this as an evidence gap."
            ),
        }
    ]


class SearchProvider(Protocol):
    """A query-to-results adapter behind ``web_search``."""

    async def search(self, query: str) -> list[dict[str, str]]:  # pragma: no cover - protocol
        ...


# --------------------------------------------------------------------------- #
# DuckDuckGo provider — the legacy path, now one adapter among several.
# --------------------------------------------------------------------------- #


class DuckDuckGoProvider:
    """DuckDuckGo via the upstream ``ddgs`` library.

    Extracted from the former ``_resilient_web_search`` so the legacy
    behaviour is observable and testable. Still the zero-impact default when
    no API key is configured. On hosts where DDG hangs at the TCP layer this
    provider will block until the timeout and then return a no-results marker
    rather than raising.
    """

    def __init__(self, *, timeout_seconds: float, proxy_url: str | None) -> None:
        self.timeout_seconds = timeout_seconds
        self.proxy_url = proxy_url

    async def search(self, query: str) -> list[dict[str, str]]:
        # The imports live inside the never-raise guard: a missing `ddgs`
        # extra must degrade to the marker, not crash the query.
        try:
            from ddgs import DDGS
            from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool

            base_tool = duckduckgo_search_tool(
                DDGS(
                    proxy=self.proxy_url,
                    timeout=max(5, int(self.timeout_seconds)),
                )
            )
            base_fn = base_tool.function
            return cast("list[dict[str, str]]", await base_fn(query))
        except Exception as exc:  # noqa: BLE001 — ImportError + DDGSException + httpx errors
            log.warning("duckduckgo_search returned no results for %r: %s", query, exc)
            return _no_results_marker(query, "DuckDuckGo rate-limit, empty response, or network error")


# --------------------------------------------------------------------------- #
# Tavily provider — POST https://api.tavily.com/search, api_key in body.
# --------------------------------------------------------------------------- #


class TavilyProvider:
    """Tavily Search. LLM-oriented; returns a ranked ``results`` array plus an
    optional synthesized ``answer``. Auth: ``api_key`` in the JSON body."""

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        proxy_url: str | None,
        max_results: int = _DEFAULT_MAX_RESULTS,
    ) -> None:
        if not api_key:
            raise ValueError("TavilyProvider requires a non-empty api_key")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.proxy_url = proxy_url
        self.max_results = max_results

    async def search(self, query: str) -> list[dict[str, str]]:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": self.max_results,
            "include_answer": False,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                proxy=self.proxy_url,
                trust_env=self.proxy_url is not None,
            ) as client:
                response = await client.post(_TAVILY_ENDPOINT, json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 — httpx errors, JSON errors, auth errors
            log.warning("tavily_search failed for %r: %s", query, exc)
            return _no_results_marker(query, f"Tavily error: {type(exc).__name__}")

        results = cast("list[dict[str, object]]", data.get("results", []))
        mapped: list[dict[str, str]] = []
        for item in results:
            mapped.append(
                {
                    "title": str(item.get("title", "")),
                    "href": str(item.get("url", "")),
                    "body": str(item.get("content", "")),
                }
            )
        if not mapped:
            return _no_results_marker(query, "Tavily returned an empty results array")
        return mapped


# --------------------------------------------------------------------------- #
# Brave provider — GET https://api.search.brave.com/res/v1/web/search,
# X-Subscription-Token header.
# --------------------------------------------------------------------------- #


class BraveProvider:
    """Brave Search API. Auth: ``X-Subscription-Token`` header (the old
    ``apikey`` query param is deprecated). Results live under
    ``web.results[].{title,url,description}``."""

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        proxy_url: str | None,
        max_results: int = _DEFAULT_MAX_RESULTS,
    ) -> None:
        if not api_key:
            raise ValueError("BraveProvider requires a non-empty api_key")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.proxy_url = proxy_url
        self.max_results = max_results

    async def search(self, query: str) -> list[dict[str, str]]:
        headers = {
            "X-Subscription-Token": self.api_key,
            "Accept": "application/json",
        }
        params: dict[str, str | int] = {"q": query, "count": self.max_results}
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                proxy=self.proxy_url,
                trust_env=self.proxy_url is not None,
            ) as client:
                response = await client.get(_BRAVE_ENDPOINT, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 — httpx errors, JSON errors, auth errors
            log.warning("brave_search failed for %r: %s", query, exc)
            return _no_results_marker(query, f"Brave error: {type(exc).__name__}")

        web = cast("dict[str, object]", data.get("web", {}))
        results = cast("list[dict[str, object]]", web.get("results", []))
        mapped: list[dict[str, str]] = []
        for item in results:
            mapped.append(
                {
                    "title": str(item.get("title", "")),
                    "href": str(item.get("url", "")),
                    "body": str(item.get("description", "")),
                }
            )
        if not mapped:
            return _no_results_marker(query, "Brave returned an empty web.results array")
        return mapped


# --------------------------------------------------------------------------- #
# Factory.
# --------------------------------------------------------------------------- #


def _proxy_from_env() -> str | None:
    val = (
        os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or os.getenv("HTTP_PROXY")
        or os.getenv("http_proxy")
        or os.getenv("ALL_PROXY")
        or os.getenv("all_proxy")
    )
    if not val or not val.strip():
        return None
    # httpx does not support SOCKS proxies; if one is configured, ignore it
    # and let the caller fall through to direct connection.
    if val.strip().startswith("socks"):
        log.info("ignoring SOCKS proxy from environment (httpx does not support it): %s", val)
        return None
    return val.strip()


def build_search_provider(
    provider: str = "auto",
    *,
    tavily_api_key: str | None = None,
    brave_api_key: str | None = None,
    timeout_seconds: float = _SEARCH_TIMEOUT_FALLBACK,
    proxy_url: str | None = None,
) -> SearchProvider:
    """Construct the search adapter.

    Resolution rules:

    * ``duckduckgo`` — always the legacy library path (may hang on blocked hosts).
    * ``tavily``     — Tavily only; raise ``ValueError`` if the key is missing.
    * ``brave``      — Brave only; raise ``ValueError`` if the key is missing.
    * ``auto``       — first provider with a configured key wins, in order
                       ``tavily`` → ``brave`` → ``duckduckgo``. This is the
                       zero-impact default: with no keys set, behaviour equals
                       the pre-change DuckDuckGo-only path.

    Keys default to the ``TAVILY_API_KEY`` / ``BRAVE_API_KEY`` environment
    variables; ``proxy_url`` defaults to the standard proxy env vars.
    """
    if provider not in {"auto", "duckduckgo", "tavily", "brave"}:
        raise ValueError(f"unknown search provider: {provider!r}")
    proxy = _proxy_from_env() if proxy_url is None else proxy_url
    tavily_key = tavily_api_key if tavily_api_key is not None else os.environ.get("TAVILY_API_KEY", "")
    brave_key = brave_api_key if brave_api_key is not None else os.environ.get("BRAVE_API_KEY", "")

    if provider == "duckduckgo":
        return DuckDuckGoProvider(timeout_seconds=timeout_seconds, proxy_url=proxy)

    if provider == "tavily":
        if not tavily_key:
            raise ValueError(
                "provider=tavily but TAVILY_API_KEY is not set. "
                "Set the key or switch to provider='auto'/'brave'/'duckduckgo'."
            )
        return TavilyProvider(
            api_key=tavily_key, timeout_seconds=timeout_seconds, proxy_url=proxy
        )

    if provider == "brave":
        if not brave_key:
            raise ValueError(
                "provider=brave but BRAVE_API_KEY is not set. "
                "Set the key or switch to provider='auto'/'tavily'/'duckduckgo'."
            )
        return BraveProvider(api_key=brave_key, timeout_seconds=timeout_seconds, proxy_url=proxy)

    # auto: prefer a key-configured provider, else legacy DuckDuckGo.
    if tavily_key:
        log.info("provider=auto → using Tavily (TAVILY_API_KEY is set)")
        return TavilyProvider(api_key=tavily_key, timeout_seconds=timeout_seconds, proxy_url=proxy)
    if brave_key:
        log.info("provider=auto → using Brave (BRAVE_API_KEY is set)")
        return BraveProvider(api_key=brave_key, timeout_seconds=timeout_seconds, proxy_url=proxy)
    log.info(
        "provider=auto but no search API key is set; using DuckDuckGo. "
        "Set TAVILY_API_KEY or BRAVE_API_KEY to switch backends."
    )
    return DuckDuckGoProvider(timeout_seconds=timeout_seconds, proxy_url=proxy)


__all__ = [
    "BraveProvider",
    "DuckDuckGoProvider",
    "SearchProvider",
    "TavilyProvider",
    "build_search_provider",
]
