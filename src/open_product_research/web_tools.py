"""Adapters that plug the local acquisition/search layer into native capabilities.

PydanticAI's ``WebSearch.local`` and ``WebFetch.local`` accept arbitrary
callables/Tools. These adapters bind our ported experience layer — the
Tavily→Brave→DuckDuckGo search chain and the Crawl4AI→httpx acquisition chain
with SSRF gates and Shopify fast paths — as the local fallbacks of the official
capabilities. No second agent loop; the capabilities stay the model-facing tools.

Two hard contracts inherited from the ported layer:

* A failed search/query NEVER raises — it returns the standard no-results
  marker so the agent records an evidence gap instead of aborting the run.
* A failed fetch NEVER raises either — tool exceptions would abort the whole
  run, so errors are returned as page content with an explicit failure note.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic_ai.tools import Tool

from .acquisition import WebAcquirer, build_acquirer
from .search import SearchProvider, build_search_provider

log = logging.getLogger(__name__)


def make_local_search(provider: SearchProvider | None = None) -> Tool[Any]:
    """``web_search`` local fallback: Tavily → Brave → DuckDuckGo, first
    configured backend wins. Failure returns the honest no-results marker."""
    resolved = provider or build_search_provider("auto")

    async def web_search_local(query: str) -> list[dict[str, str]]:
        return await resolved.search(query)

    return Tool(
        web_search_local,
        name="web_search_local",
        description=(
            "Search the web. Returns a list of {title, href, body} results. "
            "A single '(no results)' entry means every backend failed or found "
            "nothing — treat it as an evidence gap, not as proof of absence."
        ),
    )


def make_local_fetch(acquirer: WebAcquirer | None = None) -> Tool[Any]:
    """``web_fetch`` local fallback: SPA-capable acquisition chain with SSRF
    pre/post checks, Shopify /products.json fast path and content truncation."""
    resolved = acquirer or build_acquirer("auto")

    async def web_fetch_local(url: str) -> dict[str, str]:
        try:
            result = await resolved.fetch(url)
        except Exception as exc:  # noqa: BLE001 — must not abort the run
            log.warning("web_fetch failed for %s: %s", url, exc)
            return {
                "url": url,
                "title": "",
                "content": (
                    f"FETCH FAILED for {url}: {type(exc).__name__}: {exc}. "
                    "Record this as an evidence gap; do not guess page content."
                ),
            }
        return {
            "url": result.final_url or result.url,
            "title": result.title or "",
            "content": result.markdown,
        }

    return Tool(
        web_fetch_local,
        name="web_fetch_local",
        description=(
            "Fetch a web page and return its content as markdown. Renders "
            "JavaScript-heavy pages when a browser backend is available. "
            "Failed fetches return an explicit FETCH FAILED note."
        ),
    )
