"""Web acquisition layer — how a public web page becomes agent-readable content.

Ported from product_research_agent v0.2.0, minus the Settings/config plumbing
(function arguments + environment variables instead) and minus the
DB-workflow couplings. The hard-won lessons are preserved verbatim:

The agent's ``web_fetch`` capability used to call ``httpx`` directly and hand
the model a truncated slice of raw HTML — including ``<script>``, ``<nav>``
and ``<footer>`` noise — and it could not render JavaScript. Modern brand
sites are SPAs whose product specifications and prices are injected by JS, so
the legacy path systematically produced empty shells for the exact fields a
product spec requires.

Following the Crawl4AI-vs-Scrapling selection note, the first stage uses
**Crawl4AI as the primary acquisition provider** (clean Markdown + JS
rendering), with the **httpx fetcher as an automatic fallback**. They are two
adapters behind one ``WebAcquirer`` protocol — not two capabilities or two
agents.

Security invariants that hold for every provider (do not weaken):

* SSRF: every URL passes ``assert_public_url`` *before* any network call, and
  the final/redirected URL is re-checked after the fetch.
* No new capability, no new agent — this is an implementation detail of the
  existing ``web_fetch`` capability.

The Crawl4AI dependency is an optional extra (``crawl = ["crawl4ai>=0.6"]``).
When it is absent, ``build_acquirer(provider="auto")`` transparently falls
back to the httpx provider, so the base install keeps working in environments
without Chromium.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypedDict
from urllib.parse import urlsplit

from .polite_http import (
    BROWSER_UA,
    JSON_ACCEPT,
    PoliteSession,
    default_session,
)
from .shopify import (
    MAX_CONTENT_CHARS,
    SPEC_SECTION_CHARS,
    extract_product_info_from_json,
    is_shopify_store,
    shopify_products_json_url,
    shopify_single_product_json_url,
    truncate_to_spec_section,
)
from .web_security import assert_public_url

log = logging.getLogger(__name__)

# Mirror the legacy behaviour: never hand the model more than this many chars.
_MAX_CONTENT_CHARS = 80_000

# Kept as alias so older call sites / docs referring to _USER_AGENT still read
# as intentional; the polite session supplies the real browser UA.
_USER_AGENT = BROWSER_UA


@dataclass(frozen=True)
class FetchResult:
    """Normalised output every provider must return."""

    url: str
    final_url: str
    title: str
    markdown: str
    status_code: int | None = None


class WebAcquirer(Protocol):
    """A single-URL acquisition adapter behind ``web_fetch``."""

    async def fetch(self, url: str) -> FetchResult:  # pragma: no cover - protocol
        ...


# --------------------------------------------------------------------------- #
# Shopify JSON provider — lightweight .json API before full page crawl.
# Ported from ebike-intelligence-radar skill (v2.5).
# --------------------------------------------------------------------------- #


class ShopifyJsonProvider:
    """Try Shopify's /products/{handle}.json before falling back to the
    underlying provider. Reduces per-page token consumption from 80K+ chars
    to ~2-5K chars of structured product data, and fetches in ~0.5s instead
    of 8-20s for a full browser crawl.

    This is a transparent wrapper — the caller does not need to know whether
    the page came from JSON or full HTML.
    """

    def __init__(
        self,
        fallback: WebAcquirer,
        *,
        timeout_seconds: float,
        allow_proxy_dns: bool,
        proxy_url: str | None,
        session: PoliteSession | None = None,
    ) -> None:
        self._fallback = fallback
        self.timeout_seconds = timeout_seconds
        self.allow_proxy_dns = allow_proxy_dns
        self.proxy_url = proxy_url
        self.session = session or default_session()

    async def fetch(self, url: str) -> FetchResult:
        # Only attempt Shopify JSON path for known Shopify domains.
        if not is_shopify_store(url):
            return await self._fallback.fetch(url)

        # Store root, collections, and explicit catalog URLs: the HTML is the
        # heaviest page on the store (80K+ chars of nav/marketing). Prefer
        # /products.json (structured, a few K) before falling back to HTML.
        path = urlsplit(url).path.rstrip("/")
        use_catalog = (
            path in {"", "/products.json"}
            or path.startswith("/collections")
            or path == "/products"
        )
        if use_catalog:
            catalog_url = shopify_products_json_url(url)
            if catalog_url:
                catalog = await self._fetch_store_catalog(catalog_url, requested_url=url)
                if catalog is not None:
                    return catalog
                # Catalog returned None — if the failure was rate-limit, skip HTML.
                # Probe the session cache for the catalog URL.
                cache = getattr(self.session, "_cache", {}) or {}
                cached = cache.get(catalog_url)
                if cached is None:
                    for key, val in cache.items():
                        if "products.json" in str(key) and cached is None:
                            # same-store catalog endpoints share host+path prefix
                            from urllib.parse import urlsplit as _us

                            if _us(key).hostname == _us(catalog_url).hostname:
                                cached = val
                                break
                if cached is not None and cached.status_code in {429, 503}:
                    log.info("shopify catalog rate-limited for %s; skipping HTML fallback", url)
                    return FetchResult(
                        url=url,
                        final_url=catalog_url,
                        title="",
                        markdown=(
                            f"FETCH FAILED for {url}: HTTP {cached.status_code} on Shopify "
                            f"catalog `{catalog_url}`. Same-host HTML fallback skipped. "
                            "Record as evidence gap; retry later."
                        ),
                        status_code=cached.status_code,
                    )

        json_url = shopify_single_product_json_url(url)
        if json_url is None:
            return await self._fallback.fetch(url)

        try:
            import json as _json


            normalized = await assert_public_url(json_url, allow_proxy_dns=self.allow_proxy_dns)
            response = await self.session.aget(
                normalized,
                timeout=self.timeout_seconds,
                proxy=self.proxy_url,
                accept=JSON_ACCEPT,
            )
            response.raise_for_status()
            data = _json.loads(response.text)
        except Exception as exc:  # noqa: BLE001 — most JSON-path failures fall back
            # If the JSON endpoint itself was rate-limited, do NOT immediately
            # hit the HTML page on the same host — that deepens the 429.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in {429, 503} or "429" in str(exc) or "503" in str(exc):
                log.info("shopify json rate-limited for %s; skipping HTML fallback", url)
                return FetchResult(
                    url=url,
                    final_url=json_url,
                    title="",
                    markdown=(
                        f"FETCH FAILED for {url}: HTTP {status or 429} on Shopify JSON "
                        f"`{json_url}`. Same-host HTML fallback skipped to avoid deepening "
                        "rate limits. Record as evidence gap; retry later."
                    ),
                    status_code=status or 429,
                )
            log.debug("shopify json fetch failed for %s (%s); falling back", url, type(exc).__name__)
            return await self._fallback.fetch(url)

        try:
            info = extract_product_info_from_json(data)
        except Exception as exc:  # noqa: BLE001
            log.debug("shopify json parse failed for %s (%s); falling back", url, type(exc).__name__)
            return await self._fallback.fetch(url)

        # Synthesize clean, LLM-friendly markdown from structured JSON.
        # This is 10-20x smaller than the full Shopify HTML page.
        title = info.get("title", "")
        product_type = info.get("product_type", "")
        vendor = info.get("vendor", "")
        body = (info.get("body_html", "") or "").strip()
        # Strip HTML from body_html (lightweight, no heavy deps needed)
        import re as _re

        body_text = _re.sub(r"<[^>]+>", " ", body)
        body_text = _re.sub(r"\s+", " ", body_text).strip()
        tags = ", ".join(info.get("tags", []))
        variants = info.get("variants", [])
        price_min = info.get("price_min", 0)
        price_max = info.get("price_max", 0)
        images = info.get("images", [])
        image_count = len(images)

        # Include first product image for the report.
        first_image_url = ""
        if images:
            first_img = images[0]
            if isinstance(first_img, dict):
                first_image_url = str(first_img.get("src", "") or "")
                if first_image_url and not first_image_url.startswith("http"):
                    first_image_url = (
                        "https:" + first_image_url if first_image_url.startswith("//") else ""
                    )

        markdown_parts = [
            f"# {title}",
            "",
            f"_Source: Shopify product JSON — `{json_url}`_",
            "",
        ]
        if first_image_url:
            markdown_parts.append(f"![{title}]({first_image_url})")
            markdown_parts.append("")
        markdown_parts.extend(
            [
                f"**Vendor:** {vendor}  ",
                f"**Product Type:** {product_type}  ",
                f"**Tags:** {tags}  ",
            ]
        )
        if price_min > 0:
            if price_min == price_max:
                markdown_parts.append(f"**Price:** ${price_min:.2f} USD  ")
            else:
                markdown_parts.append(
                    f"**Price Range:** ${price_min:.2f} — ${price_max:.2f} USD  "
                )
        markdown_parts.append(f"**Variants:** {len(variants)}  ")
        markdown_parts.append(f"**Images:** {image_count}  ")
        markdown_parts.append("")
        if body_text:
            markdown_parts.append("## Product Description")
            markdown_parts.append("")
            markdown_parts.append(body_text[:SPEC_SECTION_CHARS])
            markdown_parts.append("")
        if variants:
            markdown_parts.append("## Variants")
            markdown_parts.append("")
            for v in variants[:20]:  # cap at 20 variants
                v_title = str(v.get("title", "") or "")
                v_price = v.get("price", "")
                v_sku = str(v.get("sku", "") or "")
                v_available = v.get("available", True)
                avail = "✓" if v_available else "✗"
                line = f"- {avail} **{v_title}**"
                if v_price:
                    try:
                        line += f" — ${float(str(v_price)):.2f}"
                    except (ValueError, TypeError):
                        pass
                if v_sku:
                    line += f" (SKU: {v_sku})"
                markdown_parts.append(line)
            if len(variants) > 20:
                markdown_parts.append(f"... and {len(variants) - 20} more variants")
            markdown_parts.append("")

        clean_md = "\n".join(markdown_parts)
        final_url = str(response.url)
        log.info("shopify json fetch: %s → %d chars markdown (vs ~80K full page)", url, len(clean_md))
        return FetchResult(
            url=url,
            final_url=final_url,
            title=title,
            markdown=clean_md[:MAX_CONTENT_CHARS],
            status_code=response.status_code,
        )

    async def _fetch_store_catalog(
        self, catalog_url: str, *, requested_url: str | None = None
    ) -> FetchResult | None:
        """Compact SKU/price matrix from the store's /products.json endpoint.

        The store homepage weighs 80K+ chars of navigation; this returns a few
        K of structured catalog facts the agent can actually reason over.
        Returns None on any failure so the caller falls back to full HTML.
        """
        import json as _json

        try:
            normalized = await assert_public_url(catalog_url, allow_proxy_dns=self.allow_proxy_dns)
            response = await self.session.aget(
                normalized,
                timeout=self.timeout_seconds,
                proxy=self.proxy_url,
                accept=JSON_ACCEPT,
            )
            response.raise_for_status()
            data = _json.loads(response.text)
        except Exception as exc:  # noqa: BLE001 — any failure falls back
            log.debug("shopify catalog fetch failed (%s); falling back", type(exc).__name__)
            return None

        products = data.get("products", []) if isinstance(data, dict) else []
        if not isinstance(products, list) or not products:
            return None

        cite = catalog_url
        origin = requested_url or catalog_url
        lines = [
            "# Store catalog (fetched from /products.json)",
            "",
            f"_Source JSON:_ `{cite}`",
            f"_Requested page:_ `{origin}`",
            "",
            f"Total products: {len(products)}",
            "",
            "| Product | Handle | Type | Price (USD) |",
            "|---|---|---|---|",
        ]
        for p in products[:50]:
            if not isinstance(p, dict):
                continue
            title = str(p.get("title", "")).replace("|", "/")
            handle = str(p.get("handle", ""))
            ptype = str(p.get("product_type", ""))
            prices: list[float] = []
            for v in p.get("variants") or []:
                if isinstance(v, dict):
                    try:
                        prices.append(float(str(v.get("price", "0"))))
                    except ValueError:
                        pass
            if not prices:
                price = ""
            elif min(prices) == max(prices):
                price = f"{prices[0]:.0f}"
            else:
                price = f"{min(prices):.0f}-{max(prices):.0f}"
            lines.append(f"| {title} | {handle} | {ptype} | {price} |")
        lines += [
            "",
            "For a product's full variants and specs, fetch its /products/<handle> page.",
        ]
        markdown = "\n".join(lines)
        log.info(
            "shopify catalog fetch: %d products → %d chars markdown (vs ~80K homepage)",
            len(products),
            len(markdown),
        )
        return FetchResult(
            url=origin,
            final_url=str(response.url),
            title="Store catalog",
            markdown=markdown,
            status_code=response.status_code,
        )


# --------------------------------------------------------------------------- #
# httpx provider — the legacy plain-HTML path, now one adapter among several.
# --------------------------------------------------------------------------- #


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", flags=re.IGNORECASE | re.DOTALL)


def _html_title(content: str) -> str:
    match = _TITLE_RE.search(content)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


class HttpxProvider:
    """Fetch raw HTML via ``httpx`` and trim it to the legacy content budget.

    This is the exact behaviour the agent had before Crawl4AI was introduced,
    extracted verbatim so the fallback path is observable and testable. It does
    not render JavaScript and returns raw (lightly trimmed) HTML as the
    ``markdown`` field to preserve backward compatibility for environments that
    cannot run a browser.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float,
        allow_proxy_dns: bool,
        proxy_url: str | None,
        user_agent: str = _USER_AGENT,
        session: PoliteSession | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.allow_proxy_dns = allow_proxy_dns
        self.proxy_url = proxy_url
        self.user_agent = user_agent
        self.session = session or default_session()

    async def fetch(self, url: str) -> FetchResult:
        # SSRF gate before the network call — same door every provider uses.
        normalized = await assert_public_url(url, allow_proxy_dns=self.allow_proxy_dns)
        response = await self.session.aget(
            normalized,
            timeout=self.timeout_seconds,
            proxy=self.proxy_url,
            headers={"User-Agent": self.user_agent},
        )
        response.raise_for_status()
        # Re-check the final URL: the request may have followed a redirect to a
        # private/host-local address the pre-fetch check could not see.
        final_url = await assert_public_url(str(response.url), allow_proxy_dns=self.allow_proxy_dns)
        # Shopify product pages average 80K+ chars (nav + grids + footer) while
        # the spec-relevant section is ~2-6K chars around SPECIFICATIONS /
        # PERFORMANCE markers — collapse it (10-12x fewer tokens). Non-Shopify
        # pages keep raw trimmed HTML so hrefs stay available for discovery.
        if is_shopify_store(final_url):
            content = truncate_to_spec_section(response.text, is_html=True)
        else:
            content = response.text[:_MAX_CONTENT_CHARS]
        return FetchResult(
            url=url,
            final_url=final_url,
            title=_html_title(response.text),
            markdown=content,
            status_code=response.status_code,
        )


# --------------------------------------------------------------------------- #
# Crawl4AI provider — clean Markdown + JS rendering.
# --------------------------------------------------------------------------- #


class Crawl4AIUnavailable(RuntimeError):
    """Raised when Crawl4AI was requested but the extra is not installed."""


class Crawl4AIProvider:
    """Acquire a page with Crawl4AI, returning LLM-ready Markdown.

    The crawl4ai import is deferred so that simply importing this module does
    not require the (heavy) Playwright/Chromium stack. If the extra is missing,
    callers get ``Crawl4AIUnavailable`` and can fall back to ``HttpxProvider``.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float,
        allow_proxy_dns: bool,
        proxy_url: str | None,
        user_agent: str = _USER_AGENT,
        session: PoliteSession | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.allow_proxy_dns = allow_proxy_dns
        self.proxy_url = proxy_url
        self.user_agent = user_agent
        self.session = session or default_session()

    async def fetch(self, url: str) -> FetchResult:
        # Import lazily: the crawl extra may be absent.
        try:
            from crawl4ai import (
                AsyncWebCrawler,
                BrowserConfig,
                CrawlerRunConfig,
            )
        except ImportError as exc:  # pragma: no cover - exercised via build path
            raise Crawl4AIUnavailable(
                "crawl4ai is not installed. Install the optional extra "
                "(`uv sync --extra crawl`) or use build_acquirer(provider='httpx')."
            ) from exc

        # SSRF gate before launching the browser — same door every provider uses.
        normalized = await assert_public_url(url, allow_proxy_dns=self.allow_proxy_dns)
        # Share the per-host polite gate with httpx fetches so Crawl4AI does not
        # burst the same brand site the HTTP path just hit.
        host = (urlsplit(normalized).hostname or "").lower()
        await self.session._async_gate.wait(host)

        browser_kwargs: dict[str, object] = {
            "headless": True,
            "user_agent": self.user_agent,
            # Chromium needs --no-sandbox to launch as a non-root user in most
            # container/server environments. This does not weaken the SSRF gate
            # (which is enforced before the browser starts); it only relaxes the
            # browser process's own Linux namespace sandbox.
            "extra_args": ["--no-sandbox"],
        }
        if self.proxy_url:
            # crawl4ai accepts a playwright-style proxy descriptor.
            browser_kwargs["proxy_config"] = {"server": self.proxy_url}

        run_config = CrawlerRunConfig(
            page_timeout=self.timeout_seconds * 1000,
            cache_mode="BYPASS",  # always fetch fresh; this is evidence, not a cache
        )

        async with AsyncWebCrawler(config=BrowserConfig(**browser_kwargs)) as crawler:
            result = await crawler.arun(url=normalized, config=run_config)

        if not getattr(result, "success", True):
            error = getattr(result, "error_message", "unknown crawl4ai failure")
            raise RuntimeError(f"crawl4ai reported failure: {error}")

        final_url_raw = str(getattr(result, "url", normalized))
        # Re-check the final URL: the browser may have followed a redirect to a
        # private/host-local address the pre-fetch check could not see.
        final_url = await assert_public_url(final_url_raw, allow_proxy_dns=self.allow_proxy_dns)

        # crawl4ai 0.9.x: result.markdown is a StringCompatibleMarkdown object;
        # the canonical string content is .raw_markdown. Fall back to str() of
        # the markdown object (still content, not a repr) and finally to cleaned
        # HTML, so a missing Markdown generator never yields an empty page.
        raw_md_obj = getattr(result, "markdown", None)
        markdown = ""
        if raw_md_obj is not None:
            markdown = getattr(raw_md_obj, "raw_markdown", None) or str(raw_md_obj)
        if not markdown:
            markdown = getattr(result, "cleaned_html", "") or ""

        # Apply Shopify-aware content truncation: for known Shopify stores,
        # keep only the spec-relevant section (~6-8K chars) instead of the
        # full 80K+ page. This is a 10-15x token savings from the
        # ebike-intelligence-radar skill.
        if is_shopify_store(url):
            markdown = truncate_to_spec_section(markdown, is_html=False)
            log.debug("shopify page truncated to %d chars", len(markdown))

        return FetchResult(
            url=url,
            final_url=final_url,
            title=_html_title(getattr(result, "html", "") or "") or _html_title(markdown),
            markdown=markdown[:_MAX_CONTENT_CHARS],
            status_code=getattr(result, "status_code", None),
        )


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
    if val.strip().startswith("socks"):
        log.info("ignoring SOCKS proxy from environment (httpx does not support it): %s", val)
        return None
    return val.strip()


class _ProviderKwargs(TypedDict):
    """Shared constructor kwargs for both providers (keep in sync)."""

    timeout_seconds: float
    allow_proxy_dns: bool
    proxy_url: str | None


def build_acquirer(
    provider: str = "auto",
    *,
    timeout_seconds: float = 30.0,
    allow_proxy_dns: bool = False,
    proxy_url: str | None = None,
    fetch_log_path: str | Path | None = None,
    session: PoliteSession | None = None,
) -> WebAcquirer:
    """Construct the web acquisition adapter.

    Resolution rules:

    * ``httpx``    — always the legacy fetcher.
    * ``crawl4ai`` — Crawl4AI only; raise ``Crawl4AIUnavailable`` if missing.
    * ``auto``     — prefer Crawl4AI, transparently fall back to httpx when the
                     extra is not installed or the import fails. This is the
                     zero-impact default.

    ``proxy_url`` defaults to the standard proxy environment variables
    (HTTP(S)_PROXY / ALL_PROXY); SOCKS proxies are ignored (httpx cannot use
    them).

    ``fetch_log_path`` (optional) enables per-case JSONL logging of every
    polite HTTP attempt (status, retries, cache hits). One ``PoliteSession``
    is shared across Shopify / httpx / Crawl4AI so rate limit and in-run
    cache apply to the whole case.
    """
    if provider not in {"auto", "httpx", "crawl4ai"}:
        raise ValueError(f"unknown acquisition provider: {provider!r}")
    resolved_session = session or (
        PoliteSession(fetch_log_path=Path(fetch_log_path) if fetch_log_path else None)
        if fetch_log_path
        else default_session()
    )
    common_kwargs: _ProviderKwargs = {
        "timeout_seconds": timeout_seconds,
        "allow_proxy_dns": allow_proxy_dns,
        "proxy_url": _proxy_from_env() if proxy_url is None else proxy_url,
    }
    provider_kwargs = {**common_kwargs, "session": resolved_session}

    base: WebAcquirer
    if provider == "httpx":
        base = HttpxProvider(**provider_kwargs)
    elif provider == "crawl4ai":
        base = Crawl4AIProvider(**provider_kwargs)
    else:
        # auto: try Crawl4AI, fall back silently.
        try:
            import crawl4ai  # noqa: F401
        except ImportError:
            log.info(
                "provider=auto but the crawl4ai extra is not installed; using HttpxProvider. "
                "Install with `uv sync --extra crawl` for clean Markdown + JS rendering."
            )
            base = HttpxProvider(**provider_kwargs)
        else:
            base = Crawl4AIProvider(**provider_kwargs)

    # Wrap every provider with the Shopify JSON fast path.
    # For Shopify product pages, /products/{handle}.json is tried first
    # (~0.5s, ~2-5K chars).  Falls back to the underlying provider if the
    # URL is not Shopify or the JSON endpoint is unavailable.
    # Zero overhead for non-Shopify URLs (is_shopify_store returns False
    # without any network call).
    return ShopifyJsonProvider(base, **provider_kwargs)


__all__ = [
    "Crawl4AIProvider",
    "Crawl4AIUnavailable",
    "FetchResult",
    "HttpxProvider",
    "ShopifyJsonProvider",
    "WebAcquirer",
    "build_acquirer",
]
