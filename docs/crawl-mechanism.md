# Crawl / fetch mechanism (project-local)

## Pipeline

```
Agent web_fetch / inspect_product_images
        │
        ▼
web_tools.make_local_fetch(case_dir)  ──► build_acquirer(fetch_log_path=case/fetch_log.jsonl)
        │                                      │
        │                                      ├─ PoliteSession (rate limit, 429 retry, cache, log)
        │                                      ▼
        │                               ShopifyJsonProvider
        │                                 ├─ known Shopify + (/, /collections/*, /products.json)
        │                                 │     → GET /products.json  (structured catalog)
        │                                 ├─ /products/{handle}
        │                                 │     → GET /products/{handle}.json
        │                                 └─ else / JSON miss → HttpxProvider or Crawl4AIProvider
        │
        └─ media._fetch  (same PoliteSession when case_dir bound)
```

Evidence citations for Shopify fast paths include the concrete `.json` URL in the
returned markdown so `evidence.md` can point at the structured source, not only
the HTML storefront page.

## Root causes observed (cases/*-20261012)

Failed/partial e-bike runs (Aventon, Rad Power, Super73 incomplete, Trek placeholder)
show the same pattern in `evidence.md` / `report.md`:

1. **Burst fetches** — the agent requested many URLs on one host in a short window
   with **no per-host gap** and **no concurrency control**.
2. **Bot User-Agent** — `OpenProductResearchAgent/0.1` (and media's similar string)
   is easy for Shopify/Cloudflare-style edges to throttle.
3. **No 429/503 retry** — `response.raise_for_status()` failed immediately; the
   model recorded "HTTP 429" as an evidence gap and kept requesting sibling URLs,
   which deepened the throttle.
4. **No in-run URL cache** — the same collection/product URL could be fetched
   repeatedly inside one case.
5. **Shopify catalog underused for collections** — `/products.json` was only
   auto-tried for store root, not `/collections/...` lead pages (e.g. Super73).

Single manual fetches from another network often returned 200 for the same URLs,
so the failure mode is **tooling cadence**, not permanent site unavailability.

## Patch (this change set)

| Control | Behaviour |
|---|---|
| Per-host rate limit | ~2s minimum gap; one in-flight wait gate per host (async + sync) |
| 429 / 503 | Honor `Retry-After` when numeric; else exponential backoff + full jitter; up to 3 retries |
| Headers | Browser Chrome UA + `Accept` / `Accept-Language` |
| In-run cache | Successful responses cached by request URL for the case session |
| Shopify | Collections + root prefer `/products.json`; product pages prefer `.json`; cite JSON URL |
| `fetch_log.jsonl` | Per-case JSONL: url, status, retries, wait_s, cached, backoff |
| Negative cache | Terminal 429/503 cached for the case so one URL is not re-hammered |
| Shopify 429 | JSON 429 skips same-host HTML fallback |

PDF rendering is **out of scope** for this patch. Report/evidence generation must
keep working; wide-table PDF failures remain a separate render issue.

## Remaining limits

* Aggressive bot scores (JS challenges, CAPTCHA, IP reputation) are not solved by
  polite HTTP alone — Crawl4AI may still help on JS-heavy pages, but can also
  share the same edge throttle.
* Catalog `/products.json?limit=50` is a sample, not always the full store.
* Cross-process / multi-agent shared rate limits are not coordinated (one session
  per case run).
* Search backends (Tavily/Brave/DDG) are unchanged by this patch.
* Official non-Shopify sites (e.g. Trek) still need HTML/crawl paths; only pacing
  and retries apply there.
* **IP reputation / cooldown**: after a prior burst, a host may keep returning 429
  for minutes even to polite single requests. The patch records and backs off, but
  cannot clear an edge ban; wait or change egress.

## Live sanity (Super73, 2026-10-12, O6)

Case: `cases/super73-patched-20261012` vs baseline `cases/super73-20261012`.

Observed on this host after earlier burst runs:

* `fetch_log.jsonl` recorded Retry-After honors (~60s), per-host spacing, retry
  attempts, and later cache hits.
* `/products.json` eventually returned **HTTP 200** (2×) and the provisional
  `report.md` cited that JSON catalog with SKU/price rows.
* Subsequent per-product `.json` URLs stayed **429** for long stretches — O6's
  egress IP was still in Super73's penalty window. Same URLs returned 200 from
  a different network at the same time.
* Agent did not finish `evidence.md` / image within `--request-limit 20` because
  multi-minute 429 backoff consumed wall clock between model turns.
* PDF render of the provisional report succeeded (1 page); wide-table PDF issues
  were not re-tested here.

Takeaway: the crawl patch changes failure mode from "silent burst → permanent
gap" to "paced retry + structured JSON preference + observable log", but it
cannot clear an already-hot IP ban mid-cooldown.
