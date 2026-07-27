# Trade Bridge extension — productionization notes + site-side protocol spec

Task owner: extension-productionization agent (2026-07-26). Scope of files touched (ownership):
`extension/**`, `public/dist/**` (created), this file, `docs/store-listings.md`.
Governing spec: `docs/00-decision-log.md` D-0006..D-0008, `docs/backlog.md` B-001 (trust checklist).

**Hard rule honored:** nothing here calls `pathofexile.com`. No trade calls were made. The
extension is the ONLY component that ever touches the trade API, and only on a user's machine/IP.

---

## 1. The postMessage protocol — the site MUST speak exactly this (DO NOT CHANGE)

This is the contract the shipped `content.js` implements and `_exttest.html` already drives. The
public site's client JS talks to the extension **only** through `window.postMessage` on
`window` at `location.origin`. Every message carries a `source` discriminator so each side
ignores its own and foreign messages.

### Page → extension (site sends these)
```js
// 1. Detect the bridge
window.postMessage({ source: "bpc-page", type: "ping", reqId }, location.origin);

// 2. Price one league's worth of items (batch; one request per league)
window.postMessage({
  source: "bpc-page",
  type:   "price",
  reqId,                                   // your correlation id (string); echoed back
  league,                                  // e.g. "Settlers" — the trade league name
  queries: [ { key, query }, ... ]         // key = your row id; query = the trade `query` object
}, location.origin);
```

### Extension → page (site listens for these)
```js
// Announced once when the content script loads (unsolicited — light up "live pricing available"):
{ source: "bpc-ext", type: "hello", version }

// Reply to a ping:
{ source: "bpc-ext", type: "pong", reqId, version }

// Reply to a price request:
{ source: "bpc-ext", type: "price-result", reqId, results: [ ... ] }   // success
{ source: "bpc-ext", type: "price-result", reqId, error: "<message>" } // whole-batch failure
```

### `query` — what to put in it
`query` is the **inner trade `query` object** (`{ status, type, name, stats, filters, ... }`) —
**exactly** the object the site already serializes into its clickable
`https://www.pathofexile.com/trade/search/<league>?q=<url-encoded {"query":{...}}>` links. Pass
the `query` sub-object, not the whole `{query:...}` wrapper. The extension adds
`sort: { price: "asc" }` itself.

### Per-item result shape (each element of `results[]`)
```js
// priced OK (cheapest online listing with a buyout):
{ key, total, amount, currency, listingId }
//   key       — echoes the queries[].key you sent
//   total     — number of matching online listings (sres.total)
//   amount    — numeric price of the cheapest buyout listing
//   currency  — e.g. "chaos", "divine", "exalted"  (raw GGG currency id)
//   listingId — the trade search id (build a ?q= permalink from it if useful)

// listings exist but none had a buyout price (offer-only):
{ key, total, amount: null, currency: null, listingId }

// this single item failed (others in the batch may still succeed):
{ key, error: "<message>" }
```

### Correct site-side usage pattern (mirrors `_exttest.html`)
- Keep a `pending[reqId] -> callback` map; generate a unique `reqId` per send.
- On load, send a `ping`; if no `hello`/`pong` within ~1.2 s, treat the bridge as absent and fall
  back to Rung-1 (clickable `?q=` links + whisper-paste). The site MUST be fully useful with no
  extension installed (D-0008 / B-001 no-dark-patterns rule).
- **Group rows by league** and send one `price` message per league (the extension prices the
  batch serially under its own rate limiter — do not fan out many `price` messages in parallel).
- Fold returned `amount`/`currency` into totals client-side; convert to chaos with the same
  economy rates the site already uses; show `no buyout`/`error` states honestly (never a fake
  number — matches the "unpriceable = link, no number" engine guardrail).

**The extension does not change the protocol for productionization. Only the manifest, icons,
version, and packaging changed. The wire format above is identical to what shipped in D-0006/07.**

---

## 2. Manifest audit (B-001 trust checklist) — before → after

| Item | Before (v0.1.0) | After (v1.0.0, store) |
|------|-----------------|------------------------|
| `version` | `0.1.0` | **`1.0.0`** |
| `name` | PoE1 …Trade Bridge | unchanged (one-identity rule) |
| `description` | … | + "Not affiliated with Grinding Gear Games." |
| `permissions` | `["storage"]` | `["storage"]` (limiter persistence only — unchanged) |
| `host_permissions` | `https://www.pathofexile.com/*` | **`https://www.pathofexile.com/api/trade/*`** (exact — narrowed) |
| content-script matches | `127.0.0.1:8765`, `localhost:8765`, `*.pages.dev`, `*.vercel.app` | **`https://REPLACE-WITH-YOUR-DOMAIN/*`** only (localhost/staging moved to dev manifest) |
| `icons` / `action.default_icon` | absent | **16/32/48/128 bronze-coin PNGs wired** |
| `background` | `service_worker` + `scripts` | Chrome: `service_worker` only; Firefox zip re-adds `scripts` fallback |
| `browser_specific_settings.gecko.id` | present | present (Firefox AMO id; Chrome ignores silently) |

**Why narrowing host_permissions is safe:** `background.js` only ever calls
`https://www.pathofexile.com/api/trade/{search,fetch}/...` (const `BASE`), so `/api/trade/*`
fully covers runtime needs while dropping the broad site-wide grant reviewers frown on.

**Dev vs store manifest tradeoff (task-required note):** localhost + staging wildcards (needed for
`/v/_exttest` bridge testing) live in **`extension/manifest.dev.json`**, never in the submitted
`manifest.json`. Store reviewers frown on `localhost`/broad `*.pages.dev` matches in a production
extension, and they add nothing for end users, so they are kept out of the store artifact. The
owner swaps in the dev manifest only for local testing (README "Load it for LOCAL testing").

**No cookies/tabs/all_urls/scripting/webRequest.** `credentials:"omit"` in every fetch →
per-IP unauthenticated limits, no GGG account risk (works logged-out).

---

## 3. Icons
`extension/generate_icons.py` (Pillow) renders a bronze currency-coin monogram bearing a bold
"1" (PoE**1**; also distinguishes the PoE2 sibling) on a dark stash-tab tile, 8× supersampled →
LANCZOS downscale. Palette from `bpc/ui/stash.html` + popup accent (#c8aa6e bronze, #1a140d tile).
Outputs `icons/icon{16,32,48,128}.png` (RGBA, verified square/correct dims). Regenerate any time;
deterministic. The generator is dev-only and excluded from the store zips.

---

## 4. Packaging — `public/dist/build_zips.py`
One command builds both **unminified** store artifacts (source copied verbatim — reviewers/users
read every line, satisfying the open-source/unminified trust item):
- `public/dist/trade-bridge-chrome-edge-1.0.0.zip` (Chrome Web Store + Edge Add-ons)
- `public/dist/trade-bridge-firefox-1.0.0.zip` (Firefox AMO)

Version drives the filenames (read from `manifest.json`). Per-target manifest specialization is
the only difference between the two: Chrome gets `background.service_worker` only; Firefox adds
`background.scripts` (event-page fallback) + keeps `gecko.id`. Excludes `manifest.dev.json` and
`generate_icons.py`. Prints a loud warning while the domain placeholder is unreplaced.

**Owner pre-submission step:** replace `REPLACE-WITH-YOUR-DOMAIN` in `extension/manifest.json`
with the real public origin (e.g. `poe1price.pages.dev`), re-run `build_zips.py`, then submit.

---

## 5. Verification performed (no pathofexile.com calls)
- `python -m json.load` on `manifest.json` and `manifest.dev.json` → both valid.
- `node --check` on `background.js`, `content.js`, `popup.js` → all pass.
- `build_zips.py` runs clean; both zips `testzip()` = OK; unzip listing confirms all payload
  files present, dev-only files excluded, per-target manifest keys correct (see run log).
- Icons rendered and visually inspected at 16 px and 128 px — coin + "1" legible at both.
- Protocol re-read against shipped `content.js` + `_exttest.html` — spec in §1 matches byte-for-
  byte; nothing in the protocol was modified.

**Not done (by rule):** no live trade call, no cache-seeder run, no store submission/deploy — those
are the owner's manual steps.
