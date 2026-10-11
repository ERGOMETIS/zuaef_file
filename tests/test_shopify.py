"""Offline tests for the Shopify fast-path helpers.

The spec-marker truncation is the token-saving trick ported from
ebike-intelligence-radar: an 80K-char product page collapses to ~8K chars
around PERFORMANCE / SPECIFICATIONS markers (10-12x fewer tokens).
Zero network.
"""
from __future__ import annotations

from open_product_research.shopify import (
    MAX_CONTENT_CHARS,
    SPEC_SECTION_CHARS,
    extract_product_info_from_json,
    is_shopify_store,
    shopify_products_json_url,
    shopify_single_product_json_url,
    truncate_to_spec_section,
)

_LONG_PAGE = (
    "<html><body><nav>" + "menu " * 4000 + "</nav>"
    "<h1>Specifications</h1>"
    "<table><tr><td>Motor</td><td>Bafang M600</td></tr>"
    "<tr><td>Battery</td><td>720 Wh</td></tr></table>"
    "<footer>" + "junk " * 4000 + "</footer></body></html>"
)


def test_truncate_returns_short_content_unchanged():
    text = "Motor: Bafang. Battery: 48V 14Ah."
    assert truncate_to_spec_section(text) == text


def test_truncate_cuts_to_spec_marker():
    out = truncate_to_spec_section(_LONG_PAGE, is_html=True)
    assert "Specifications" in out
    assert "Bafang M600" in out
    assert len(out) <= SPEC_SECTION_CHARS
    # Navigation noise before the marker must be gone.
    assert "menu menu" not in out


def test_truncate_no_marker_uses_second_half():
    text = "A" * 100 + "-middle-" + "B" * (SPEC_SECTION_CHARS * 2)
    out = truncate_to_spec_section(text)
    assert "A" * 100 not in out  # first half dropped
    assert len(out) <= SPEC_SECTION_CHARS


def test_truncate_respects_max_fallback():
    text = "x" * (MAX_CONTENT_CHARS + 500)
    out = truncate_to_spec_section(text)
    assert len(out) <= MAX_CONTENT_CHARS


def test_is_shopify_store_known_domain_and_myshopify():
    assert is_shopify_store("https://aventon.com/products/level-4")
    assert is_shopify_store("https://somebrand.myshopify.com/")
    assert not is_shopify_store("https://brand.example/products/bike")


def test_products_json_url_for_known_store():
    url = shopify_products_json_url("https://aventon.com/products/level-4-rec-ebike")
    assert url == "https://aventon.com/products.json?limit=50"


def test_products_json_url_none_for_unknown_store():
    assert shopify_products_json_url("https://brand.example/products/bike") is None


def test_single_product_json_url():
    url = shopify_single_product_json_url("https://aventon.com/products/level-4-rec-ebike")
    assert url == "https://aventon.com/products/level-4-rec-ebike.json"
    assert shopify_single_product_json_url("https://brand.example/collections/all") is None


def test_extract_product_info_from_json():
    data = {
        "title": "Level 2 Commuter Ebike",
        "handle": "level-2-commuter-ebike",
        "product_type": "Ebikes",
        "vendor": "Aventon",
        "tags": "ebike, commuter, step-through",
        "variants": [
            {"title": "Small / Forest", "sku": "L2-S-FOR", "price": "1899.00", "available": True},
            {"title": "Large / Black", "sku": "L2-L-BLK", "price": "2099.00", "available": True},
        ],
        "images": [{"src": "https://cdn.shopify.com/x/level2.jpg"}],
    }
    info = extract_product_info_from_json(data)
    assert info["title"] == "Level 2 Commuter Ebike"
    assert info["handle"] == "level-2-commuter-ebike"
    assert info["vendor"] == "Aventon"
    assert "ebike" in info["tags"]
    assert info["price_min"] == 1899.0
    assert info["price_max"] == 2099.0
    assert len(info["variants"]) == 2
    assert info["images"]
