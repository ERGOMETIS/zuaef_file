"""Shopify-optimised acquisition and content strategies for product pages.

Ported from the ebike-intelligence-radar skill (v2.5, 2026-05-31) via
product_research_agent v0.2.0. Key insights: Shopify product pages average 80K+
chars (full navigation + product grid + footer), while the spec-relevant
section is only ~2-6K chars around "PERFORMANCE" or "SPECIFICATIONS" markers.
Using the lightweight /products.json API or smart marker-based truncation
reduces token consumption by 10-15x per page.

Strategies:
1. ``/products.json`` helpers — fetch structured JSON instead of heavy HTML
   (see ``shopify_single_product_json_url`` + ``extract_product_info_from_json``,
   consumed by ``acquisition.ShopifyJsonProvider``).
2. ``truncate_to_spec_section`` — find spec markers, keep only relevant text.
3. ``classify_shopify_product`` — ported classification system from the radar.

All functions here are self-contained (stdlib only) so the acquisition layer
can import them without any workflow/storage dependency.
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import TypedDict
from urllib.parse import urljoin, urlsplit

log = logging.getLogger(__name__)

# Spec section markers (ordered by priority — first match wins).
# Ported from extract_specs_fullpage.py in ebike-intelligence-radar.
_SPEC_MARKERS = [
    "PERFORMANCE",
    "SPECIFICATIONS",
    "TECHNICAL SPECS",
    "Specifications",
    "Technical Specifications",
    "Product Details",
    "规格参数",
    "技术规格",
    "产品参数",
]

# Common e-bike Shopify store domains (for /products.json detection).
_SHOPIFY_DOMAINS = {
    "aventon.com",
    "lectricebikes.com",
    "radpowerbikes.com",
    "velotricbike.com",
    "heybike.com",
    "juicedbikes.com",
    "ride1up.com",
    "super73.com",
    "arielrider.com",
    "lectricbikes.co.uk",
    "blixbike.com",
}

# Content budget: keep only spec-relevant bytes (vs 80K full page).
SPEC_SECTION_CHARS = 8_000
# Full-page fallback when no spec marker is found.
MAX_CONTENT_CHARS = 20_000


class ShopifyProductInfo(TypedDict, total=False):
    """Lightweight product info from /products.json (subset of fields)."""

    title: str
    handle: str
    product_type: str
    vendor: str
    tags: list[str]
    variants: list[dict[str, object]]
    images: list[dict[str, object]]
    body_html: str
    price_min: float
    price_max: float


# --------------------------------------------------------------------------- #
# Content truncation — find the spec section, discard navigation noise.
# --------------------------------------------------------------------------- #


class _TextStripper(HTMLParser):
    """Strip HTML tags, keep text content. Ported from extract_specs_fullpage.py."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def _strip_html_to_text(html: str) -> str:
    """Remove scripts, styles, noscript; keep JSON-LD; extract plain text."""
    # Keep JSON-LD scripts (structured product data)
    html = re.sub(
        r'<script\b(?!.*type=["\']application/ld\+json["\'])[^>]*>.*?</script>',
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    html = re.sub(r"<noscript[^>]*>.*?</noscript>", "", html, flags=re.DOTALL)
    stripper = _TextStripper()
    stripper.feed(html)
    text = stripper.get_text()
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate_to_spec_section(content: str, *, is_html: bool = False) -> str:
    """Extract only the spec-relevant section from a Shopify product page.

    Strategy (from ebike-intelligence-radar fullpage-spec-extraction):
    1. If HTML, strip to plain text first.
    2. Search for spec section markers (PERFORMANCE, SPECIFICATIONS, etc.).
    3. If found, take ``SPEC_SECTION_CHARS`` chars from that position.
    4. If not found, take the last half (specs are usually at the bottom)
       capped at ``SPEC_SECTION_CHARS``.
    5. Fall back to first ``MAX_CONTENT_CHARS`` chars.

    This reduces token consumption from 80K+ chars to ~6-8K chars per page,
    a 10-12x improvement.
    """
    text = _strip_html_to_text(content) if is_html else content

    if len(text) <= SPEC_SECTION_CHARS:
        return text

    # Search for spec section markers
    for marker in _SPEC_MARKERS:
        pos = text.find(marker)
        if pos >= 0:
            section = text[pos : pos + SPEC_SECTION_CHARS]
            log.debug("spec section found at marker %r (pos %d, %d chars)", marker, pos, len(section))
            return section

    # No marker found — take the second half (specs tend to be at the bottom)
    half = len(text) // 2
    section = text[half : half + SPEC_SECTION_CHARS]
    if len(section) > 100:
        log.debug("no spec marker found; using second-half slice (%d chars)", len(section))
        return section

    # Degenerate case: take first MAX_CONTENT_CHARS
    return text[:MAX_CONTENT_CHARS]


# --------------------------------------------------------------------------- #
# Shopify /products.json lightweight fetch helpers.
# --------------------------------------------------------------------------- #


def is_shopify_store(url: str) -> bool:
    """Check if a URL's domain belongs to a known Shopify e-bike store.

    Also detects common Shopify CDN patterns (myshopify.com, cdn.shopify.com).
    """
    hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
    if hostname.endswith(".myshopify.com") or "shopify" in hostname:
        return True
    for domain in _SHOPIFY_DOMAINS:
        if hostname == domain or hostname.endswith("." + domain):
            return True
    return False


def shopify_products_json_url(url: str) -> str | None:
    """Derive the /products.json endpoint from a Shopify product/store URL.

    Returns None if the URL doesn't look like a Shopify store.
    """
    parts = urlsplit(url)
    hostname = (parts.hostname or "").lower()
    if not is_shopify_store(url):
        return None
    # Build the API URL from the origin
    origin = f"{parts.scheme}://{hostname}"
    if parts.port:
        origin += f":{parts.port}"
    return urljoin(origin, "/products.json?limit=50")


def shopify_single_product_json_url(url: str) -> str | None:
    """Derive the single-product .json URL from a product page URL.

    E.g. https://aventon.com/products/level-4-rec-ebike
      → https://aventon.com/products/level-4-rec-ebike.json
    """
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    if not path.startswith("/products/"):
        return None
    if not is_shopify_store(url):
        return None
    origin = f"{parts.scheme}://{parts.hostname}"
    return f"{origin}{path}.json"


def extract_product_info_from_json(data: dict[str, object]) -> ShopifyProductInfo:
    """Extract lightweight product info from a Shopify product JSON object.

    Ported from ebike_product_crawler.py classify_product() — uses tags as
    comma-separated string (Shopify API convention), not list.
    """
    from typing import Any, cast

    # handle both {product:{...}} and bare {...}
    product: dict[str, Any] = cast("dict[str, Any]", data.get("product", data))
    tags_raw = product.get("tags", "")
    # Shopify tags is a COMMA-SEPARATED STRING, not a list (pitfall #9).
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    elif isinstance(tags_raw, list):
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    else:
        tags = []

    variants = product.get("variants", [])
    prices: list[float] = []
    for v in variants:
        try:
            p = float(v.get("price", "0") or "0")
            if p > 0:
                prices.append(p)
        except (ValueError, TypeError):
            pass
    images = product.get("images", [])

    return ShopifyProductInfo(
        title=str(product.get("title", "")),
        handle=str(product.get("handle", "")),
        product_type=str(product.get("product_type", "")),
        vendor=str(product.get("vendor", "")),
        tags=tags,
        variants=variants,
        images=images,
        body_html=str(product.get("body_html", "") or ""),
        price_min=min(prices) if prices else 0.0,
        price_max=max(prices) if prices else 0.0,
    )


def classify_shopify_product(info: ShopifyProductInfo) -> str:
    """Classify a Shopify product into: bike, accessory, part, warranty, gift_card, other.

    Ported from ebike_product_crawler.py v2.3 with all documented pitfalls.
    All products are returned with a label — nothing is silently discarded.
    """
    title = info.get("title", "")
    title_lower = title.lower()
    product_type = info.get("product_type", "").lower()
    price = info.get("price_min", 0) or 0

    # --- Explicit non-product filters (pitfall #4) ---
    spare_battery_patterns = ["spare battery", "replacement battery", "extra battery"]
    if any(p in title_lower for p in spare_battery_patterns):
        return "part"
    non_bike_titles = ["bike rack", "power station", "safe shield"]
    if any(p in title_lower for p in non_bike_titles):
        return "accessory"

    # --- Warranty / Gift Card (price-independent) ---
    if "warranty" in title_lower or "protection plan" in title_lower:
        return "warranty"
    if "gift card" in title_lower or "giftcard" in title_lower:
        return "gift_card"

    # --- Part detection (price-aware, pitfall #12) ---
    part_keywords = [
        "battery",
        "charger",
        "controller",
        "display",
        "motor kit",
        "brake pads",
        "brake rotor",
        "derailleur",
        "cassette",
        "chain",
        "crankset",
        "pedal",
        "fork",
        "shock",
        "wheel",
        "tire",
    ]
    for kw in part_keywords:
        if kw in title_lower and "bike" not in title_lower:
            return "part"

    # High-priced battery as part (pitfall #12)
    if "battery" in title_lower and price >= 300:
        return "part"
    if "battery" in title_lower and price > 0 and price < 50:
        return "accessory"

    # --- Accessory detection ---
    accessory_keywords = [
        "helmet",
        "lock",
        "rack",
        "fender",
        "mirror",
        "light",
        "bag",
        "basket",
        "pump",
        "tool",
        "cover",
        "stand",
        "phone mount",
        "water bottle",
        "apparel",
        "glove",
        "jersey",
    ]
    for kw in accessory_keywords:
        if kw in title_lower and price < 300 and "bike" not in title_lower:
            return "accessory"

    if "accessories" in product_type or "accessory" in product_type:
        return "accessory"
    if "component" in product_type or "part" in product_type:
        return "part"

    # --- Brand-specific model detection (pitfall #11) ---
    # super73: "SUPER73-ZX", "SUPER73-S2"
    if re.match(r"^super73[- ][a-z0-9]", title_lower) and price >= 300:
        return "bike"

    # --- Bike detection ---
    bike_keywords = [
        "ebike",
        "e-bike",
        "electric bike",
        "electric bicycle",
        "commuter",
        "mountain",
        "folding bike",
        "cargo bike",
        "cruiser",
        "step-through",
        "step-thru",
        "fat tire",
    ]
    for kw in bike_keywords:
        if kw in title_lower:
            return "bike"

    # Title contains "bike" and price suggests it's a bike
    if "bike" in title_lower and price >= 300:
        return "bike"

    # Product type from Shopify
    if "bicycle" in product_type or "bike" in product_type:
        return "bike"

    # --- Fallback ---
    if price >= 500:
        return "bike"
    if price > 0 and price < 50:
        return "accessory"

    return "other"


__all__ = [
    "MAX_CONTENT_CHARS",
    "SPEC_SECTION_CHARS",
    "ShopifyProductInfo",
    "classify_shopify_product",
    "extract_product_info_from_json",
    "is_shopify_store",
    "shopify_products_json_url",
    "shopify_single_product_json_url",
    "truncate_to_spec_section",
]
