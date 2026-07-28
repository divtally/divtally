# R6 - Performance lens (fresh eyes)

**Date:** 2026-07-28
**Round:** 6 (fresh lenses). Lens: **performance / latency / payload / caching**.
**Surfaces measured (live):** site `https://divtally.com` (Cloudflare Pages), API
`https://divtally.vercel.app` (Vercel Python), Worker
`https://divtally-cache.divtally.workers.dev` (Cloudflare Worker + KV).
**Trade rule honoured:** ZERO calls to pathofexile.com. Only our site/API/worker and
poe.ninja (server-side, via `/api/build`) were contacted. All timings from `curl 8.15`
(brotli+gzip capable), `--compressed` where the browser would send `Accept-Encoding`.
Client location routes to Vercel `iad1` (US-East) and Cloudflare's nearest edge, so the
absolute ms include one WAN RTT - read the **distributions and the cold/warm deltas**, not
the absolute floor.

## Verdict

**PASS - performance is healthy. No blocker/major. One MINOR (requested) finding:**
version-stamped assets and immutable font binaries carry a short `max-age=14400` (4h) +
`must-revalidate` instead of a long `immutable` TTL. Everything that matters for payload is
already right: **the big `/api/build` JSON is brotli-compressed** (157 KB -> ~25 KB), the
HTML/JS/CSS are all `br`, `core.js` is small (26 KB decompressed), warm latencies are tight,
and repeat appraisals are edge-cached. I went looking for the classic disasters
(uncompressed 500 KB JSON, megabyte JS bundle, cache-busting `no-store` on statics, a cold
start that dominates every call) and **none are present**.

---

## Results (distributions)

All times in seconds. n>=12 warm samples per surface unless noted; "cold" = first hit after
idle (labelled). ttfb = `time_starttransfer`.

| Surface | Call | n | cold (1st) | warm median | warm min-max | notes |
|---|---|---|---|---|---|---|
| API `/api/health` | GET (pure, no network) | 12 | **0.964** | **0.292** | 0.282-0.339 | `no-store`, 190 B, always `X-Vercel-Cache: MISS` (executes every time). Cold delta ~+670 ms = Python fn cold start. |
| API `/api/build` | GET, **fresh** (MISS) | 2 | **2.42** / **2.00** | - | - | Dominated by **server-side poe.ninja fetch chain** (char page + item/price data) + build compute, not fn cold start. Inherent to the product. |
| API `/api/build` | GET, **repeat** (edge HIT) | 5 | - | **0.142** | 0.131-0.222 | Identical query served from Vercel edge cache (`X-Vercel-Cache: HIT`, `Age` grows). |
| Site `/` (index.html) | GET | 12 | 0.266 | **0.126** | 0.116-0.143 | Cloudflare, `br`, 45.8 KB decompressed HTML. `Cache-Control: public, max-age=0, must-revalidate` (correct for HTML). |
| Assets `/assets/core.js` | GET | - | - | ~0.10 | - | 26.2 KB **decompressed** (`br` on wire), edge-cached (`cf-cache-status: REVALIDATED`). |
| Worker `/cache` | GET (KV read) | 12 | 0.303 | **0.094** | 0.086-0.117 | 2 B `{}` body, `Access-Control-Allow-Origin: *`. |
| Worker `/cache` | POST (KV write) | 6 | - | **0.472** | 0.427-0.548 | Global KV write latency; expected, and off the render path (fire-and-forget seed). |

### Payload + compression (the thing that would be a MAJOR if wrong - it's fine)

| Response | Uncompressed | Encoding | On-wire | Ratio |
|---|---|---|---|---|
| `/api/build` (ArleAllflame, 41 items) | **157,229 B** | **`br`** | 24,977 B | 6.3x |
| `/api/build` (SergoheroGaz) | 127,058 B | `br` | ~20 KB | ~6x |
| `index.html` | 45,770 B | `br` | ~9 KB | ~5x |
| `core.js` | 26,183 B | `br` | ~7-8 KB | ~3.5x |
| `sample.js` | 8,595 B | `br` | - | - |
| `fonts.css` | 605 B | `br` | - | - |
| `/api/health` | 190 B | none | 190 B | tiny, fine |
| Worker `/cache` GET | 2 B | none | 2 B | tiny, fine |

Fonts (woff2, already-compressed, served raw as they should be):
`cormorantgaramond-400-normal-latin` 37.6 KB, `...-ext` 33.7 KB,
`cormorantgaramond-500-italic-latin` 23.9 KB, `marcellus-400-normal-latin` 14.6 KB. Browser
only pulls the `unicode-range` subset it needs, so typical first paint loads ~2-4 of these.

---

## Findings

### MINOR - Static assets & immutable fonts get a 4h TTL + `must-revalidate`, not `immutable`

**What:** every static asset returns
`Cache-Control: public, max-age=14400, must-revalidate`:

- `/assets/core.js?v=20260727g`, `sample.js?v=...`, `fonts.css?v=...`, `/config.js`
- all `/assets/fonts/*.woff2`

The JS/CSS URLs are **version-stamped** (`?v=20260727g`) and the woff2 files are effectively
**immutable binaries** (a font change ships a new file). Both are the textbook case for
`Cache-Control: public, max-age=31536000, immutable`. Instead, after 4 hours every repeat
visitor issues a conditional revalidation (observed live: `cf-cache-status: REVALIDATED`,
`ETag` present) on each asset. `must-revalidate` on a versioned URL is strictly wasted -
the URL changes when the content changes, so it can never serve stale.

**Impact:** small. Files are tiny, brotli'd, and Cloudflare absorbs the revalidation at the
edge (304s, not full transfers), so a returning user pays a handful of ~90-120 ms
conditional GETs rather than 0. It is **repeat-visit / CDN-offload perf left on the table**,
not a user-facing stall. Flagged because the round brief explicitly asks whether versioned
assets get a long cache - they don't.

**Fix hint:** on Cloudflare Pages, set headers via `public/_headers`:

```
/assets/*
  Cache-Control: public, max-age=31536000, immutable
/assets/fonts/*
  Cache-Control: public, max-age=31536000, immutable
```

Keep `config.js` (unversioned, may change per deploy) on a short TTL - or better, drop
`must-revalidate` and give it `max-age=300`. Leave `index.html` / `how-it-works.html` as
`max-age=0, must-revalidate` (correct - they must pick up new `?v=` stamps).

---

## Non-findings (checked, deliberately NOT flagged)

- **`/api/build` compression** - brotli is ON (`Content-Encoding: br`), 157 KB -> 25 KB. The
  "uncompressed big JSON" disaster does not exist here.
- **`/api/build` fresh latency ~2 s** - this is the server-side poe.ninja fetch chain, not a
  defect. It is the product's core work and it only runs on a cache MISS; repeats are ~140 ms
  edge hits. Not a perf bug.
- **Cold starts** - health cold ~965 ms vs warm ~290 ms is ordinary Vercel Python cold-start
  behaviour, amortised away under any real traffic. Not egregious.
- **Worker POST ~470 ms** - a global KV write; it is fire-and-forget cache seeding off the
  render path, so it never blocks a user's result. Fine.
- **`core.js` size** - 26 KB decompressed / ~7-8 KB on wire. Small. No bundle bloat.
- **Fonts double-compression** - woff2 correctly served with NO `Content-Encoding` (already
  compressed). Good.
- **`/api/build` carries `Cache-Control: public` (no max-age)** and Vercel edge-caches the
  result (`X-Vercel-Cache: HIT`, `Age` climbing). This is **perf-positive** (fast repeats);
  any staleness concern belongs to a correctness lens, not performance.

## Method / reproducibility

- Warm distributions: 12 back-to-back `curl --compressed` per surface; first sample labelled
  cold. Times are `time_starttransfer` / `time_total` from curl's `-w`.
- Cold-start isolation: a spaced background probe (`coldprobe.sh`, ~3.5-min idle gaps) in the
  session scratchpad re-measured `/api/health` after an eviction window: post-idle
  **0.859 s** vs immediate warm **0.288 s** - reproducing the natural first-hit cold (0.964 s)
  and confirming the ~600-670 ms cold-start delta is stable and function-local (health does
  no network).
- Build payload: `--compressed` decompressed body measured with `wc -c`; on-wire from
  `size_download`; encoding from response `Content-Encoding`.
