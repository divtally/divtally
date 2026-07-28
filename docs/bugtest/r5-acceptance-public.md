# R5 - Public-Product Acceptance (fresh eyes vs. the written promises)

**Date:** 2026-07-28
**Round:** 5 (regression + acceptance). Judge the shipped product against its own public
promises; prove the four prior rounds' fixes still cohere.
**Scope of promise surfaces:** `public/site/how-it-works.html` (every claim), the hero +
upgrade-card copy in `public/site/index.html`, `docs/store-listings.md`, `docs/launch-post.md`.
**Reality checked against:** live site (`https://divtally.com`), live API
(`https://divtally.vercel.app`), live Worker (`https://divtally-cache.divtally.workers.dev`),
GitHub repo/releases, and the repo source (site/api/worker/extension).
**Trade rule honoured:** zero calls to pathofexile.com. Only our site/API/worker, poe.ninja,
and GitHub (repo reachability) were contacted.

## Verdict

**PASS - with 4 minor wording/drift fixes.** Every load-bearing trust claim (privacy,
endpoints, the pathofexile-never-server-side invariant, "not affiliated", open source, the
community-cache trust hardening, Chaos/Divine, unpriceable->link) is **TRUE in code and
verified live.** No blocker/major. The four findings are precision/drift nits on the docs and
the trust page - none change what the product actually does or exposes.

---

## Claim checklist + verdicts

Legend: PASS = claim true & verified; PASS* = true but wording imprecise (see finding);
DRIFT = doc references stale reality.

### A. Endpoints table ("every server DivTally contacts") - `how-it-works.html`

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| A1 | Appraise -> `{API_BASE}/api/build`, "ours (reads poe.ninja only)" | PASS* | Live `GET /api/build` (no args) -> 400 usage JSON as documented. Server reads poe.ninja; **also fetches pobb.in/pastebin.com server-side for PoB paste links** -> see F1. |
| A2 | Icons -> `web.poecdn.com`, your browser, images only | PASS | `index.html` renders `<img src=poecdn ...>` client-side; no cookies/credentials on img loads. |
| A3 | Cached rare read -> `GET {WORKER_BASE}/cache` (ours, KV store) | PASS | Live `GET /cache?league=Standard&keys=...` -> `{}` 200; `worker.js` is a dumb KV store, never calls poe/ggg. |
| A4 | Cache write -> `POST {WORKER_BASE}/cache` (writes your result) | PASS | `worker.js` POST path; live OPTIONS `/cache` -> 204 preflight. |
| A5 | Trade link -> `pathofexile.com/trade/...` = your browser tab | PASS | Anchor links only; opened by the user. |
| A6 | Extension prices a rare -> `POST pathofexile.com/api/trade/...` = your browser & IP | PASS | `background.js BASE="https://www.pathofexile.com/api/trade"`, runs in the extension SW on the user's IP. |
| A7 | "Fonts served from this site, not Google" | PASS | `fonts.css` references only `/assets/fonts/*.woff2`; live `index.html` loads only `/assets/fonts.css`. No googleapis. |
| A8 | Live config endpoints match the table | PASS | Live `config.js`: `API_BASE=divtally.vercel.app`, `WORKER_BASE=divtally-cache.divtally.workers.dev`. |
| A9 | Server may never reach pathofexile.com (hard invariant) | PASS | `_http.py _BLOCKED_HOSTS=("pathofexile.com",)` guarded on initial URL **and every 3xx hop**; live `/api/health` -> `"calls_pathofexile_com": false`. |

### B. Privacy / storage - `how-it-works.html`

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| B1 | "no cookies we set" | PASS | Live `HEAD https://divtally.com/` -> **no Set-Cookie** header. |
| B2 | No analytics, no ad/tracking pixels, no third-party scripts | PASS | Live `index.html` loads only `/config.js`, `/assets/sample.js`, `/assets/core.js`, `/assets/fonts.css`. No gtag/GA/sentry/plausible/hotjar/mixpanel. |
| B3 | Only 3rd-party server on a normal page load = `web.poecdn.com` | PASS | API_BASE/WORKER_BASE are first-party; poe.ninja/pobb/pastebin are server-side; poecdn only for icons. |
| B4 | localStorage keys listed (`bpc_manual`, `bpc_purchased`, `bpc_recent_builds`, `bpc_status`/`bpc_league`/`bpc_tier`, `bpc_cache_optout`) | PASS* | All present in `core.js` **except** the status key is `bpc_status_v2` in code, not `bpc_status` -> see F3. |
| B5 | Clear storage -> everything on device is gone | PASS | State lives only in localStorage (`lsget`/`lsset`); no cookies/IndexedDB. |

### C. Community cache trust hardening - `how-it-works.html` + `worker.js`

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| C1 | Entries expire after 24 hours | PASS | `TTL_SECONDS=86400` on every `KV.put`. |
| C2 | Always exact-match; keyed by hash of league+name+mods | PASS | Client-computed `KEY_RE=/^v[0-9]{1,3}_[0-9a-f]{16,64}$/`; KV namespaced per league (`kvName`). |
| C3 | Holds no character name / account / identifying data | PASS | Stored record = numeric tiers + confidence + method + sample_size + total_found + note + trade_url + ts (price data only; `sanitizeEntry` whitelists fields). |
| C4 | Confidence computed on our side; sender's claim ignored | PASS | `sanitizeEntry` sets `confidence = confFromTotal(total_found)`; client `confidence` dropped. Matches `core.js confFromTotal` (>=5 high, >=2 medium). |
| C5 | Always shown "community - unverified", never the verified green dot | PASS | `index.html` `p.source==='cache'` -> `<span class="dot none">community - unverified`; label "community". |
| C6 | Values capped to sane magnitudes | PASS | `num()` rejects >`MAX_TIER=1e8`, non-finite, negative. |
| C7 | Per-contributor daily write limit | PASS | `MAX_WRITES_PER_IP_DAY=600`, day-bucketed per-IP counter; overflow -> `throttled`. |
| C8 | Opt-out actually stops read+write | PASS | `cacheEnabled()` = WORKER_BASE set && !optout; toggle writes `bpc_cache_optout`; how-it-works page + footer share the same key. |
| C9 | trade_url can't be an arbitrary injected URL | PASS (bonus) | `sanitizeEntry` keeps `trade_url` only if it starts with `https://www.pathofexile.com/trade`. |

### D. The extension - `how-it-works.html`, upgrade card, `store-listings.md`, `launch-post.md`

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| D1 | Only requests to `pathofexile.com/api/trade/*` + DivTally domain | PASS | `manifest.json host_permissions=["https://www.pathofexile.com/api/trade/*"]`; content scripts only on divtally.com/www/pages.dev. |
| D2 | No tabs, history, cookies, other-site access | PASS | `permissions=["storage"]` only; `content.js` uses `window.postMessage` bridge, no tabs/history APIs. |
| D3 | Logged out; no login/session/POESESSID | PASS | `background.js fetch(..., credentials:"omit")`. |
| D4 | Careful rate limiter: reads X-Rate-Limit, honours Retry-After, one at a time, stays under caps | PASS | `applyHeaderRules(X-Rate-Limit-Ip)`, `parseRetryAfter`, `serialize()` (one call at a time), `MARGIN=0.7`, persisted to `chrome.storage.local`. |
| D5 | Unminified / readable source | PASS | `background.js`/`content.js`/`manifest.json` all human-readable, commented. |
| D6 | Collects no personal data; no analytics | PASS | Manifest `data_collection_permissions.required=["none"]`; no network beyond trade API. |
| D7 | Nothing on our side ever touches the trade API | PASS | Enforced by `_http.py` block (A9). |
| D8 | Downloadable from GitHub while stores are in review | PASS | `github.com/divtally/divtally/releases` -> 200; release **v1.2.1** carries `divtally-extension-chrome-edge-1.2.1.zip` + `-firefox-1.2.1.zip`. |
| D9 | "Store-only distribution (no sideloading)" | PASS* | Contradicts the live GitHub-release path (which is sideloading) offered meanwhile -> see F2. |

### E. Headline product claims - `index.html`, `launch-post.md`

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| E1 | Build link OR PoB import code / paste link as input | PASS | `engine.detect` routes poe.ninja char / pobb.in / pastebin / raw PoB. |
| E2 | Prices gems, currency, uniques-by-name from public economy instantly | PASS | `poeninja.py` reads poe.ninja gem/currency/unique overviews; `source="poe.ninja"`. |
| E3 | Every skill + support gem (Awakened/Empower/Enlighten) | PASS | `index.html`: "active skill + every support gem (each gem by name/level/quality/corruption)". |
| E4 | Understands 5/6-links as a price factor on rares & uniques | PASS | `querybuild._links_filter` -> `socket_filters.links.min = max_link`, applied to rare + unique queries. |
| E5 | Totals in Chaos, shown alongside Divine, using live exchange rates | PASS | `response._divine_tier(div_rate)`; `core.js divRate()` from `meta.divine_to_chaos` (poe.ninja); never fabricated when absent. |
| E6 | Headline is a FLOOR until rares priced | PASS | Rares start unpriced; `querybuild` notes "priced on your machine via the trade link". |
| E7 | Can't price honestly -> trade link, never a made-up number | PASS | Unpriceable paths set a note + trade_url, no chaos number (`querybuild` lines 769-848). |
| E8 | Variant uniques (Watcher's Eye, timeless jewels) show a range/low-confidence + exact link | PASS | `variantreg` + `index.html` variant notes ("cheapest copy of any seed", "verify via the trade link"). |

### F. "Not affiliated" present everywhere promised

| Surface | Present? | Evidence |
|---------|----------|----------|
| `index.html` meta description | YES | "...Not affiliated with Grinding Gear Games." |
| `index.html` upgrade card | YES | "Not affiliated with or endorsed by Grinding Gear Games" |
| `index.html` footer | YES | "...Path of Exile is a trademark of GGG." (verified live) |
| `how-it-works.html` callout + footer | YES | "Not affiliated with GGG" callout + footer line |
| `store-listings.md` | YES | "NOT AFFILIATED" section in full description |
| `launch-post.md` | YES | closing "Not affiliated with, endorsed by, or associated with GGG." |

---

## Findings (all MINOR)

### F1 (minor) - Trust page: "reads only poe.ninja" omits the PoB paste hosts
`how-it-works.html` states, in the endpoints table ("Ours (reads poe.ninja only)") and the
footnote ("The build function reads only poe.ninja."), that the build function's only outbound
read is poe.ninja. In reality `engine.py` + `_http.get_text` also fetch **pobb.in** and
**pastebin.com** server-side when the user pastes a PoB *paste link* (raw PoB code and
poe.ninja char links do not). This is user-initiated, sends only the paste id the user chose,
is invisible to the browser's Network tab (so the table's browser-verifiability framing still
holds), and the guard still makes pathofexile.com impossible. But on a page whose whole selling
point is precision about "every server," the prose should say so.
**Fix:** reword to e.g. "reads poe.ninja (and, for a PoB paste link, the paste host you supply
- pobb.in / pastebin.com)".

### F2 (minor) - Distribution-channel wording contradicts the interim GitHub path
The live `how-it-works.html` "The extension, precisely" section says **"Store-only
distribution (Chrome / Edge / Firefox)"**, and `launch-post.md` says **"Store-only distribution
(no sideloading)"** - yet the hero CTA, the upgrade card, and Rung 2 of the same how-it-works
page all currently direct users to **"download from GitHub while store listings are in review"**,
which for Chrome/Edge is a sideload. The two statements are internally inconsistent during the
review window.
**Fix:** reconcile to something like "Store distribution once approved; signed GitHub release
builds meanwhile" so the interim path isn't contradicted by an absolute "store-only / no
sideloading" line.

### F3 (minor) - Storage table key mismatch: `bpc_status` vs `bpc_status_v2`
`how-it-works.html` "On your device" lists `bpc_status / bpc_league / bpc_tier`. The code
(`core.js`) actually uses **`bpc_status_v2`** (`bpc_league` and `bpc_tier` match). A user
auditing localStorage as the page invites would not find `bpc_status`.
**Fix:** list `bpc_status_v2` (or add both).

### F4 (minor) - `store-listings.md` references stale v1.1.0 artifacts
The store-listing doc's "Artifacts to upload" names
`public/dist/divtally-extension-chrome-edge-1.1.0.zip` / `...-firefox-1.1.0.zip`, and the
screenshot checklist shows "active - v1.1.0". Reality: `public/dist/` and the GitHub release are
**v1.2.1** (also a v1.2.0); no 1.1.0 zip exists. Following the doc literally at submission time
would fail to find the file / label the wrong version.
**Fix:** bump the doc's artifact names and the screenshot version string to 1.2.1.

---

## Regression cohesion (do the prior 4 rounds still hold together?)

- **Invariant (D-0008/B-001):** enforced in code (`_http.py` block + guarded redirects) AND
  asserted live (`/api/health` -> `calls_pathofexile_com:false`). Extension keeps trade calls on
  the user's IP (`credentials:"omit"`). Intact.
- **Confidence derivation is consistent across tiers:** worker `confFromTotal` == site
  `confFromTotal` (>=5 high / >=2 medium / else low); cache prices are forced to
  "community - unverified" regardless of what a poisoned sender claims. Intact.
- **Unpriceable -> link, never a fake number:** preserved in `querybuild` note paths and the
  cache `sanitizeEntry` trade_url domain guard. Intact.
- **Live plumbing is green end to end:** site 200, `/how-it-works` clean-URL 200,
  `/api/build` usage 400, `/api/health` 200, worker OPTIONS 204 / GET-good `{}` / GET-no-league
  400 - all exactly as the docs describe.
- **Endpoints/config match the deployed reality:** live `config.js` API_BASE/WORKER_BASE equal
  the how-it-works table; store URLs still `REPLACE_ME` (consistent with "in review" copy, and
  the store buttons degrade to a disabled state rather than dead `#` links).

**Bottom line:** the honesty-first brand survives fresh-eyes scrutiny. Ship-blocking: none.
Recommend fixing F1-F4 (all wording/drift) before the public launch post goes out, since two of
them sit on the trust page itself.
