"""Polite HTTP helpers for public-page acquisition.

Shared by the acquisition layer (async) and media downloads (sync). Goals:

* Per-host rate limit so one agent run cannot burst a brand site into 429.
* Retry 429/503 with Retry-After when present, else exponential backoff + jitter.
* Browser-like User-Agent / Accept headers (bot UAs get throttled harder).
* In-run URL response cache so the same page is not re-fetched in one case.
* Optional JSONL fetch log per case for post-mortem of rate-limit events.

SSRF checks stay in the caller (assert_public_url / public_https_url) — this
module only paces, retries, caches and logs already-cleared public URLs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

DEFAULT_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,*/*;q=0.8"
)
JSON_ACCEPT = "application/json, text/plain, */*"

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": BROWSER_UA,
    "Accept": DEFAULT_ACCEPT,
    "Accept-Language": "en-US,en;q=0.9",
}

# Soft defaults: slow enough for Shopify/Cloudflare brand sites, not glacial.
DEFAULT_MIN_INTERVAL_S = 2.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_S = 2.0
DEFAULT_BACKOFF_CAP_S = 60.0
RETRYABLE_STATUS = frozenset({429, 503})


@dataclass
class PoliteResponse:
    """Minimal response surface providers need (keeps tests free of full httpx)."""

    url: str
    status_code: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)
    request_url: str = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code} for {self.url}",
                request=httpx.Request("GET", self.request_url or self.url),
                response=httpx.Response(self.status_code, text=self.text),
            )


def _hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().rstrip(".")


def _merge_headers(extra: dict[str, str] | None, *, accept: str | None = None) -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    if accept:
        headers["Accept"] = accept
    if extra:
        headers.update(extra)
    # Always keep a browser UA unless the caller explicitly overrides it.
    if "User-Agent" not in headers or not headers["User-Agent"].strip():
        headers["User-Agent"] = BROWSER_UA
    return headers


def retry_after_seconds(headers: dict[str, str], attempt: int) -> float:
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw:
        try:
            return min(DEFAULT_BACKOFF_CAP_S, max(0.0, float(raw.strip())))
        except ValueError:
            pass
    # Exponential backoff with full jitter, capped.
    base = min(DEFAULT_BACKOFF_CAP_S, DEFAULT_BACKOFF_BASE_S * (2**attempt))
    return random.uniform(0.0, base)


def _append_fetch_log(path: Path | None, record: dict[str, Any]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.debug("fetch_log write failed: %s", exc)


class _AsyncHostGate:
    """Serialize requests per host and enforce a minimum gap between them.

    The lock is held for the *entire* request (via ``hold``), not just the
    pre-request sleep — otherwise two concurrent tool calls can both pass the
    gap check and burst the same host into 429.
    """

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}
        self._meta = asyncio.Lock()

    async def _lock_for(self, host: str) -> asyncio.Lock:
        async with self._meta:
            lock = self._locks.get(host)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[host] = lock
            return lock

    class _Hold:
        def __init__(self, gate: _AsyncHostGate, host: str) -> None:
            self.gate = gate
            self.host = host
            self.wait_s = 0.0
            self._lock: asyncio.Lock | None = None

        async def __aenter__(self) -> float:
            if not self.host:
                return 0.0
            self._lock = await self.gate._lock_for(self.host)
            await self._lock.acquire()
            now = time.monotonic()
            last = self.gate._last.get(self.host, 0.0)
            delay = self.gate.min_interval - (now - last)
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                delay = 0.0
            self.wait_s = delay
            return delay

        async def __aexit__(self, *exc) -> bool:
            if self.host and self._lock is not None:
                self.gate._last[self.host] = time.monotonic()
                self._lock.release()
            return False

    def hold(self, host: str) -> _AsyncHostGate._Hold:
        return _AsyncHostGate._Hold(self, host)

    async def wait(self, host: str) -> float:
        """Backward-compat spacing only (does not cover the request itself)."""
        async with self.hold(host) as delay:
            return delay


class _SyncHostGate:
    """Sync counterpart: lock held for whole request via ``hold``."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}
        self._meta = threading.Lock()

    def _lock_for(self, host: str) -> threading.Lock:
        with self._meta:
            lock = self._locks.get(host)
            if lock is None:
                lock = threading.Lock()
                self._locks[host] = lock
            return lock

    class _Hold:
        def __init__(self, gate: _SyncHostGate, host: str) -> None:
            self.gate = gate
            self.host = host
            self.wait_s = 0.0
            self._lock: threading.Lock | None = None

        def __enter__(self) -> float:
            if not self.host:
                return 0.0
            self._lock = self.gate._lock_for(self.host)
            self._lock.acquire()
            now = time.monotonic()
            last = self.gate._last.get(self.host, 0.0)
            delay = self.gate.min_interval - (now - last)
            if delay > 0:
                time.sleep(delay)
            else:
                delay = 0.0
            self.wait_s = delay
            return delay

        def __exit__(self, *exc) -> bool:
            if self.host and self._lock is not None:
                self.gate._last[self.host] = time.monotonic()
                self._lock.release()
            return False

    def hold(self, host: str) -> _SyncHostGate._Hold:
        return _SyncHostGate._Hold(self, host)

    def wait(self, host: str) -> float:
        with self.hold(host) as delay:
            return delay


class PoliteSession:
    """In-run cache + host gate + fetch log for one research case."""

    def __init__(
        self,
        *,
        min_interval: float = DEFAULT_MIN_INTERVAL_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        fetch_log_path: str | Path | None = None,
        cache_enabled: bool = True,
    ) -> None:
        self.min_interval = float(min_interval)
        self.max_retries = int(max_retries)
        self.fetch_log_path = Path(fetch_log_path) if fetch_log_path else None
        self.cache_enabled = cache_enabled
        self._cache: dict[str, PoliteResponse] = {}
        self._async_gate = _AsyncHostGate(self.min_interval)
        self._sync_gate = _SyncHostGate(self.min_interval)

    def clear_cache(self) -> None:
        self._cache.clear()

    async def aget(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
        accept: str | None = None,
        follow_redirects: bool = True,
    ) -> PoliteResponse:
        if self.cache_enabled and url in self._cache:
            cached = self._cache[url]
            _append_fetch_log(
                self.fetch_log_path,
                {
                    "ts": time.time(),
                    "url": url,
                    "final_url": cached.url,
                    "status": cached.status_code,
                    "cached": True,
                    "retries": 0,
                    "wait_s": 0.0,
                },
            )
            return cached

        host = _hostname(url)
        merged = _merge_headers(headers, accept=accept)
        # Hold the per-host lock for spacing + request + retries so concurrent
        # tool calls cannot burst the same origin.
        async with self._async_gate.hold(host) as initial_wait:
            wait_s = float(initial_wait)
            attempt = 0
            response: PoliteResponse | None = None

            while attempt <= self.max_retries:
                started = time.monotonic()
                try:
                    async with httpx.AsyncClient(
                        follow_redirects=follow_redirects,
                        timeout=timeout,
                        proxy=proxy,
                        trust_env=False,
                    ) as client:
                        raw = await client.get(url, headers=merged)
                    response = PoliteResponse(
                        url=str(raw.url),
                        status_code=raw.status_code,
                        text=raw.text,
                        headers={k.lower(): v for k, v in raw.headers.items()},
                        request_url=url,
                    )
                except httpx.HTTPError as exc:
                    _append_fetch_log(
                        self.fetch_log_path,
                        {
                            "ts": time.time(),
                            "url": url,
                            "status": 0,
                            "error": f"{type(exc).__name__}: {exc}",
                            "cached": False,
                            "retries": attempt,
                            "wait_s": wait_s,
                            "elapsed_s": round(time.monotonic() - started, 3),
                        },
                    )
                    if attempt >= self.max_retries:
                        raise
                    sleep_for = retry_after_seconds({}, attempt)
                    await asyncio.sleep(sleep_for)
                    wait_s += sleep_for
                    attempt += 1
                    continue

                if response.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                    sleep_for = retry_after_seconds(response.headers, attempt)
                    _append_fetch_log(
                        self.fetch_log_path,
                        {
                            "ts": time.time(),
                            "url": url,
                            "final_url": response.url,
                            "status": response.status_code,
                            "cached": False,
                            "retries": attempt,
                            "wait_s": wait_s,
                            "backoff_s": round(sleep_for, 3),
                            "elapsed_s": round(time.monotonic() - started, 3),
                            "retrying": True,
                        },
                    )
                    await asyncio.sleep(sleep_for)
                    wait_s += sleep_for
                    attempt += 1
                    continue

                _append_fetch_log(
                    self.fetch_log_path,
                    {
                        "ts": time.time(),
                        "url": url,
                        "final_url": response.url,
                        "status": response.status_code,
                        "cached": False,
                        "retries": attempt,
                        "wait_s": round(wait_s, 3),
                        "elapsed_s": round(time.monotonic() - started, 3),
                        "bytes": len(response.text.encode("utf-8", errors="replace")),
                    },
                )
                # Cache successes and terminal 429/503 so one banned URL cannot
                # burn another multi-minute retry storm inside the same case.
                if self.cache_enabled and (
                    response.status_code < 400
                    or response.status_code in RETRYABLE_STATUS
                ):
                    self._cache[url] = response
                return response

            assert response is not None
            if self.cache_enabled:
                self._cache[url] = response
            return response

    def get(
        self,
        url: str,
        *,
        timeout: float = 18.0,
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
        accept: str | None = None,
        follow_redirects: bool = False,
        stream_max_bytes: int | None = None,
    ) -> tuple[bytes, str, str, int]:
        """Sync GET used by media downloads.

        Returns ``(body, content_type, final_url, status_code)``.
        When ``follow_redirects`` is False the caller must handle Location
        (media.py re-validates each hop for SSRF).
        """
        cache_key = f"sync:{url}"
        if self.cache_enabled and cache_key in self._cache:
            cached = self._cache[cache_key]
            _append_fetch_log(
                self.fetch_log_path,
                {
                    "ts": time.time(),
                    "url": url,
                    "final_url": cached.url,
                    "status": cached.status_code,
                    "cached": True,
                    "retries": 0,
                    "wait_s": 0.0,
                    "sync": True,
                },
            )
            body = cached.text.encode("utf-8", errors="replace")
            ctype = cached.headers.get("content-type", "")
            return body, ctype, cached.url, cached.status_code

        host = _hostname(url)
        merged = _merge_headers(headers, accept=accept)
        wait_s = self._sync_gate.wait(host)
        attempt = 0
        last_exc: Exception | None = None

        while attempt <= self.max_retries:
            started = time.monotonic()
            try:
                with httpx.Client(
                    timeout=timeout,
                    follow_redirects=follow_redirects,
                    trust_env=False,
                    proxy=proxy,
                    headers=merged,
                ) as client:
                    if stream_max_bytes is not None:
                        with client.stream("GET", url) as response:
                            if 300 <= response.status_code < 400:
                                # Caller handles redirects; surface Location via empty body.
                                loc = response.headers.get("location", "")
                                _append_fetch_log(
                                    self.fetch_log_path,
                                    {
                                        "ts": time.time(),
                                        "url": url,
                                        "status": response.status_code,
                                        "location": loc,
                                        "cached": False,
                                        "retries": attempt,
                                        "wait_s": wait_s,
                                        "sync": True,
                                    },
                                )
                                return b"", response.headers.get("content-type", ""), url, response.status_code
                            if (
                                response.status_code in RETRYABLE_STATUS
                                and attempt < self.max_retries
                            ):
                                sleep_for = retry_after_seconds(
                                    {k.lower(): v for k, v in response.headers.items()},
                                    attempt,
                                )
                                _append_fetch_log(
                                    self.fetch_log_path,
                                    {
                                        "ts": time.time(),
                                        "url": url,
                                        "status": response.status_code,
                                        "cached": False,
                                        "retries": attempt,
                                        "wait_s": wait_s,
                                        "backoff_s": round(sleep_for, 3),
                                        "retrying": True,
                                        "sync": True,
                                    },
                                )
                                time.sleep(sleep_for)
                                wait_s += sleep_for + self._sync_gate.wait(host)
                                attempt += 1
                                continue
                            response.raise_for_status()
                            total = 0
                            chunks: list[bytes] = []
                            for part in response.iter_bytes():
                                total += len(part)
                                if total > stream_max_bytes:
                                    raise ValueError("Response exceeds configured download limit")
                                chunks.append(part)
                            body = b"".join(chunks)
                            ctype = response.headers.get("content-type", "")
                            final = url
                            _append_fetch_log(
                                self.fetch_log_path,
                                {
                                    "ts": time.time(),
                                    "url": url,
                                    "final_url": final,
                                    "status": response.status_code,
                                    "cached": False,
                                    "retries": attempt,
                                    "wait_s": round(wait_s, 3),
                                    "elapsed_s": round(time.monotonic() - started, 3),
                                    "bytes": len(body),
                                    "sync": True,
                                },
                            )
                            if (
                                self.cache_enabled
                                and response.status_code < 400
                                and "image/" not in ctype.lower()
                            ):
                                # Cache text-ish only; binary images skip text cache.
                                try:
                                    text = body.decode("utf-8", errors="replace")
                                except Exception:  # noqa: BLE001
                                    text = ""
                                self._cache[cache_key] = PoliteResponse(
                                    url=final,
                                    status_code=response.status_code,
                                    text=text,
                                    headers={"content-type": ctype},
                                    request_url=url,
                                )
                            return body, ctype, final, response.status_code
                    else:
                        raw = client.get(url)
                        if raw.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                            sleep_for = retry_after_seconds(
                                {k.lower(): v for k, v in raw.headers.items()},
                                attempt,
                            )
                            time.sleep(sleep_for)
                            wait_s += sleep_for + self._sync_gate.wait(host)
                            attempt += 1
                            continue
                        raw.raise_for_status()
                        body = raw.content
                        ctype = raw.headers.get("content-type", "")
                        final = str(raw.url)
                        _append_fetch_log(
                            self.fetch_log_path,
                            {
                                "ts": time.time(),
                                "url": url,
                                "final_url": final,
                                "status": raw.status_code,
                                "cached": False,
                                "retries": attempt,
                                "wait_s": round(wait_s, 3),
                                "elapsed_s": round(time.monotonic() - started, 3),
                                "bytes": len(body),
                                "sync": True,
                            },
                        )
                        return body, ctype, final, raw.status_code
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise
                sleep_for = retry_after_seconds({}, attempt)
                time.sleep(sleep_for)
                wait_s += sleep_for
                attempt += 1

        if last_exc:
            raise last_exc
        raise RuntimeError(f"polite sync GET exhausted retries for {url}")


# Process-wide default session for callers that do not own a case directory.
_default_session: PoliteSession | None = None
_default_lock = threading.Lock()


def default_session() -> PoliteSession:
    global _default_session
    with _default_lock:
        if _default_session is None:
            _default_session = PoliteSession()
        return _default_session


def reset_default_session() -> None:
    """Test helper: drop the process-wide session so rate/cache state is fresh."""
    global _default_session
    with _default_lock:
        _default_session = None


__all__ = [
    "BROWSER_UA",
    "DEFAULT_ACCEPT",
    "DEFAULT_HEADERS",
    "DEFAULT_MIN_INTERVAL_S",
    "JSON_ACCEPT",
    "RETRYABLE_STATUS",
    "PoliteResponse",
    "PoliteSession",
    "default_session",
    "reset_default_session",
    "retry_after_seconds",
]
