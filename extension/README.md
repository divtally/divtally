# PoE1 Build Price Checker — Trade Bridge (browser extension)

This extension prices **rares/uniques** for the public Build Price Checker website by calling
the official PoE1 trade API **from your own browser and IP**. That's the only safe way to do
live rare pricing on a public site: the trade API blocks browser pages (CORS) and bans a shared
server IP that searches for everyone, but an extension is privileged (CORS-exempt) and uses each
user's own per-IP rate budget. Ported 1:1 from the app's Python trade client
(`bpc/trade.py`): same endpoints, same conservative rate limiter, same 429 back-off — with the
limiter state **persisted** so an MV3 service-worker restart can't burst past GGG's cap.

## Files
- `manifest.json` — MV3 manifest (Chrome/Edge + Firefox keys).
- `background.js` — service worker: trade search→fetch→cheapest listing + persistent rate limiter.
- `content.js` — bridge injected into the site (page ⇄ service worker via `postMessage`).
- `popup.html` / `popup.js` — a built-in tester (no website needed).

## Load it (Chrome / Edge)
1. Go to `chrome://extensions` (Edge: `edge://extensions`).
2. Turn on **Developer mode** (top-right in Chrome, left in Edge).
3. Click **Load unpacked** and select this `extension` folder (the one with `manifest.json`).
4. The card appears. Click the **service worker** link on the card to open its console/logs.
   *(Reload the extension with the circular ↻ icon after any code edit; reload target tabs too.)*

## Load it (Firefox)
1. Go to `about:debugging` → **This Firefox** → **Load Temporary Add-on…**
2. Select the **`manifest.json`** file (not the folder). It's removed when Firefox restarts.
   The manifest already includes the `gecko.id` and a `background.scripts` fallback Firefox needs.

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
`{ key, amount, currency, total }` (cheapest online listing) or `{ key, error }`.

## Adding origins
Edit `manifest.json` → `content_scripts[0].matches` to include each site origin the extension
should activate on (local dev + every staging/prod domain), then reload the extension.

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
