"""Small public-URL image tools; neither image identity nor image rights is inferred."""
from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import re
import socket
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError

from .polite_http import PoliteSession, default_session

MAX_PAGE_BYTES = 2_000_000
MAX_IMAGE_BYTES = 10_000_000

# Optional case-scoped session; capability can replace this for fetch_log.
_media_session: PoliteSession | None = None


def set_media_session(session: PoliteSession | None) -> None:
    """Bind media downloads to the same polite session as web_fetch (optional)."""
    global _media_session
    _media_session = session


def _session() -> PoliteSession:
    return _media_session or default_session()


def public_https_url(value: str) -> str:
    """Refuse non-public hosts before fetching a URL suggested by a model."""
    p = urlsplit(value.strip())
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        raise ValueError("Only public HTTPS URLs without embedded credentials are allowed")
    hostname = p.hostname.rstrip(".")
    if hostname.lower() == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Local network destinations are not allowed")
    try:
        addresses = [x[4][0] for x in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)]
    except socket.gaierror as e:
        raise ValueError("Hostname did not resolve") from e
    if not addresses or any(not ipaddress.ip_address(x).is_global for x in addresses):
        raise ValueError("Host resolves to a non-public IP address")
    return value.strip()


def _fetch(url: str, *, max_bytes: int) -> tuple[bytes, str, str]:
    """Download bytes with polite pacing; never auto-follow unchecked redirects."""
    import time as _time

    import httpx as _httpx

    from .polite_http import DEFAULT_HEADERS, RETRYABLE_STATUS, retry_after_seconds

    url = public_https_url(url)
    session = _session()
    for _ in range(4):
        host = (urlsplit(url).hostname or "").lower()
        with session._sync_gate.hold(host):
            attempt = 0
            while attempt <= session.max_retries:
                with _httpx.Client(
                    timeout=18,
                    follow_redirects=False,
                    trust_env=False,
                    headers=DEFAULT_HEADERS,
                ) as client, client.stream("GET", url) as response:
                    if 300 <= response.status_code < 400 and response.headers.get("location"):
                        url = public_https_url(urljoin(url, response.headers["location"]))
                        break  # leave hold, continue outer redirect loop
                    if (
                        response.status_code in RETRYABLE_STATUS
                        and attempt < session.max_retries
                    ):
                        sleep_for = retry_after_seconds(
                            {k.lower(): v for k, v in response.headers.items()},
                            attempt,
                        )
                        _time.sleep(sleep_for)
                        attempt += 1
                        continue
                    response.raise_for_status()
                    total = 0
                    chunks: list[bytes] = []
                    for part in response.iter_bytes():
                        total += len(part)
                        if total > max_bytes:
                            raise ValueError("Response exceeds configured download limit")
                        chunks.append(part)
                    return b"".join(chunks), response.headers.get("content-type", ""), url
            else:
                # exhausted retries without return/redirect
                continue
            # redirected
            continue
    raise ValueError("Too many redirects")



def find_product_images(page_url: str) -> list[dict[str, str]]:
    """Inspect image candidates from one real HTML page; never guess URLs."""
    data, content_type, final_url = _fetch(page_url, max_bytes=MAX_PAGE_BYTES)
    if "html" not in content_type.lower():
        raise ValueError("Page is not HTML")
    soup = BeautifulSoup(data, "html.parser")
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for elem in soup.select('meta[property="og:image"], meta[name="twitter:image"], img, source'):
        candidates = []
        if elem.name == "meta":
            candidates.append(elem.get("content", ""))
        else:
            candidates.extend(elem.get(k, "") for k in ("src", "data-src", "data-original", "data-lazy-src"))
            for key in ("srcset", "data-srcset"):
                srcset = elem.get(key) or ""
                for item in srcset.split(","):
                    candidates.append(item.strip().split(" ")[0])
        for v in candidates:
            if not v or v.startswith(("data:", "blob:")):
                continue
            u = urljoin(final_url, v)
            if urlsplit(u).scheme != "https" or u in seen:
                continue
            seen.add(u)
            items.append({"url": u, "alt": (elem.get("alt") or "")[:160], "source_page": final_url})
            if len(items) >= 40:
                return items
    return items


def save_product_image(case_dir: Path, image_url: str, source_page: str, sku: str) -> dict[str, str]:
    """Verify image bytes, save provenance, return Markdown relative path."""
    if not sku.strip():
        raise ValueError("SKU/model label is required")
    source_page = public_https_url(source_page)
    data, _mime, actual_url = _fetch(image_url, max_bytes=MAX_IMAGE_BYTES)
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w < 350 or h < 200:
            raise ValueError("Image too small for a client report")
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("Downloaded bytes are not a valid image") from e
    assets = case_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    label = re.sub(r"[^a-z0-9]+", "-", sku.lower()).strip("-")[:45] or "model"
    identifier = hashlib.sha256(data).hexdigest()[:12]
    path = assets / f"{label}-{identifier}.jpg"
    img.thumbnail((2000, 1500))
    img.save(path, "JPEG", quality=89, optimize=True)
    metadata = {"sku_label": sku, "source_page": source_page, "image_url": actual_url,
                "image_sha256": hashlib.sha256(data).hexdigest(), "saved_as": f"assets/{path.name}",
                "downloaded_at": datetime.now(UTC).isoformat(),
                "dimensions": [w, h], "identity_verified": False, "rights_verified": False}
    with (assets / "image_sources.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
    return {"path": metadata["saved_as"], "source_page": source_page,
            "image_url": actual_url, "note": "Confirm SKU and reuse rights separately"}
