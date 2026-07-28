# DivTally Browser Extension

> **Download packaged builds:** https://github.com/divtally/divtally/releases (same files submitted to the stores). Store installs are recommended once the listings go live - they auto-update.

This extension prices **rares/uniques** for the public DivTally website by calling
the official PoE1 trade API **from your own browser and IP**. That's the only safe way to do
live rare pricing on a public site: the trade API blocks browser pages (CORS) and bans a shared
server IP that searches for everyone, but an extension is privileged (CORS-exempt) and uses each
user's own per-IP rate budget. Ported 1:1 from the app's Python trade client
(`bpc/trade.py`): same endpoints, same conservative rate limiter, same 429 back-off — with the
limiter state **persisted** so an MV3 service-worker restart can't burst past GGG's cap.

## Files
- `manifest.json` — **store** MV3 manifest (v1.2.0). Minimal by design: `storage` only,
  `host_permissions` = **exactly** `https://www.pathofexile.com/api/trade/*`, and the DivTally
  production content-script matches already baked in (`https://divtally.com/*`,
  `https://www.divtally.com/*`, `https://divtally.pages.dev/*`). No localhost, no wildcard hosts,
  no cookies/tabs/all_urls.
- `manifest.dev.json` — **local-testing** manifest. Same permissions, but its content-script
  matches also include `http://127.0.0.1:*/*`, `localhost`, and `*.pages.dev`/`*.vercel.app`
  staging wildcards so you can exercise the bridge locally. **Never submitted to a store.**
- `icons/icon{16,32,48,128}.png` — bronze-coin monogram (regenerate with `generate_icons.py`).
- `generate_icons.py` — Pillow icon generator (dev-only; not shipped in the store zip).
- `background.js` — service worker: trade search→fetch→cheapest listing + persistent rate limiter.
- `content.js` — bridge injected into the site (page ⇄ service worker via `postMessage`).
- `popup.html` / `popup.js` — a built-in tester (no website needed).

## Load it for LOCAL testing (Chrome / Edge)
The store `manifest.json` has **no localhost match**, so to test the bridge against the local app
you load the **dev** manifest instead:
1. Copy `manifest.dev.json` over `manifest.json` **in a scratch copy of this folder** (don't commit
   the swap), OR temporarily rename: keep `manifest.json` aside and rename `manifest.dev.json` →
   `manifest.json`.
2. Go to `chrome://extensions` (Edge: `edge://extensions`), turn on **Developer mode**.
3. Click **Load unpacked** and select the folder (the one with `manifest.json`).
4. Click the **service worker** link on the card to open its console/logs.
   *(Reload the extension with the circular ↻ icon after any code edit; reload target tabs too.)*

The **popup tester** (toolbar icon) needs no site and works with either manifest — it is the
fastest way to confirm search/fetch + rate limiting run from your IP.

## Load it for LOCAL testing (Firefox)
1. Go to `about:debugging` → **This Firefox** → **Load Temporary Add-on…**
2. Select the dev **`manifest.json`** file (the swapped-in `manifest.dev.json`) — not the folder.
   It's removed when Firefox restarts. Firefox uses the `gecko.id` + `background.scripts` fallback.

## Test it — three ways, easiest first

**A. Popup (no website needed).** Click the extension's toolbar icon. Paste a PoE1 trade `?q=`
link (open a build in the local app, click any item's trade button, copy that URL) into the box
and hit **Price it**. You should see the cheapest online listing price. This alone proves the
trade search/fetch + rate limiting work from your IP.

**B. Local test harness page.** Start the local app (`python run.py --web`), open
`http://127.0.0.1:8765/v/_exttest`, and confirm it says **“extension detected.”** Paste one or
more trade links (one per line) and click **Price via extension**. This exercises the full
page → content-script → service-worker → trade-API path (the same protocol the public site uses).

**C. Public staging site.** Once staging is deployed (see the setup Word doc), add its URL to
`manifest.json` → `content_scripts[].matches` (e.g. `"https://bpc-staging.pages.dev/*"`), reload
the extension, and test against the real public origin.

## The protocol (for the website side)
The page talks to the extension only via `window.postMessage`:
```js
// detect
window.postMessage({ source:"bpc-page", type:"ping", reqId }, location.origin);
// price (one request per league)
window.postMessage({ source:"bpc-page", type:"price", reqId, league,
                     queries:[{ key, query }] }, location.origin);
// the extension replies with { source:"bpc-ext", type:"pong"|"price-result", reqId, ... }
```
`query` is the trade **query** object (status/type/name/stats/filters) — exactly the inner
object the site already builds for its clickable `?q=` links. The extension returns, per item,
`{ key, amount, currency, total, prices }` (cheapest online listing) or `{ key, error }` — each
result also carries `debug: { searchStatus, fetchStatus, fetched, nulls }` (v1.1) so a failing row
is self-describing.

`prices` (**v1.2.0, additive**) is the **whole fetched price picture**: every fetched listing's
buyout price as `[{ amount, currency }, …]` in fetch order (the search sorts price-ascending, so
`prices[0]` equals the existing `amount`/`currency` cheapest fields). Null-price listings are
skipped (and counted in `debug.nulls`); a no-buyout item returns `prices: []`. The page uses this
to compute min/median/high tiers with its own distribution math — nothing is hidden or dropped
(D-0015). All pre-existing fields are unchanged, so an old site keeps working against a v1.2.0
extension and a new site keeps working against an old (v1.1.0) extension (it just gets no
`prices`).

### Live scan status (protocol v1.1, additive)
When the page's `price` request carries `protocolVersion >= 1.1` (and comes from a tab, not the
popup), the service worker streams **per-item progress** to that tab, which `content.js` relays to
the page as `{ source:"bpc-ext", type:"price-progress", reqId, key, stage, detail }`:

| `stage` | `detail` | meaning |
|---------|----------|---------|
| `queued` | `{}` | item accepted, waiting its turn (all items emit this up front) |
| `searching` | `{}` | about to POST the trade search |
| `waiting` | `{ waitMs }` | the rate limiter (or a 429 back-off) is pausing this long |
| `fetching` | `{}` | about to GET the listing details |
| `done` | `{ total, amount, currency }` | priced from the cheapest buyout listing |
| `nobuyout` | `{ total, fetched, nulls }` | listings exist but none had a buyout price |
| `error` | `{ message, status }` | this item failed (`status` = HTTP status, or `null`) |

A pre-1.1 page simply never sends `protocolVersion`, gets no progress, and works exactly as
before. A page that receives an unknown `price-progress` type ignores it. Full spec:
`docs/notes-scan-status-ext.md`.

## Adding origins
For **local/staging** work, edit `manifest.dev.json` → `content_scripts[0].matches`, then reload.
For **production**, the DivTally origins are already set in `manifest.json`
(`https://divtally.com/*`, `https://www.divtally.com/*`, `https://divtally.pages.dev/*`); if the
public origin ever changes, edit them there and rebuild the store zips.

## Build the store zips
`python public/dist/build_zips.py` produces two **unminified** artifacts in `public/dist/`:
`divtally-extension-chrome-edge-1.2.0.zip` and `divtally-extension-firefox-1.2.0.zip`. It reads
`manifest.json` (the version drives the filenames), copies every source file verbatim, and
specialises only the manifest per target (Chrome: `service_worker` only; Firefox: adds the
`background.scripts` fallback + keeps `gecko.id`). It excludes `manifest.dev.json` and
`generate_icons.py`. It refuses (non-zero exit) if the domain placeholder is ever reintroduced.
Store-listing copy + permission justifications: `docs/store-listings.md`. Site-side protocol
spec: `docs/notes-public-ext.md`.

## Safety / what to watch during testing
- **Unauthenticated by design:** requests use `credentials:"omit"` → **per-IP** limits, no account
  risk. (Do not switch to `include` without understanding it shifts limits onto your GGG account.)
- **Rate limits:** search ≈ 30 / 5 min per IP; the limiter keeps you under ~70% of that. If you
  still see a `429`/back-off message, that's the limiter protecting you — wait it out. **reset
  limits** in the popup clears the local window (use only if you know the real window has passed).
- **If pricing returns HTTP 403 / empty unexpectedly:** the trade API may want a Referer/identity
  the extension can't set from a plain `fetch`. That's the main thing this test is meant to find —
  if it happens, tell me and we'll add a `declarativeNetRequest` Referer rule or route the call
  through a pathofexile.com tab. (Open the service-worker console to see the exact status.)
- **MV3 idle:** the service worker may sleep between builds; that's fine (state is persisted). A
  long 429 back-off could be interrupted by a worker restart — rare during normal use.
