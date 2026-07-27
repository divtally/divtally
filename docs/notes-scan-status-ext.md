# Trade Bridge v1.1 - per-item live scan status (extension side)

Agent: extension scan-status agent (2026-07-27). Files touched (my ownership):
`extension/background.js`, `extension/content.js`, `extension/manifest.json`,
`extension/manifest.dev.json`, `extension/README.md`, `extension/test_protocol.mjs` (created),
`public/dist/build_zips.py`-built zips (rebuilt to 1.1.0; stale 1.0.0 zips removed), this file.

**Hard rule honored:** nothing here calls `pathofexile.com`. No trade calls were made. All
verification is offline (stubbed `chrome.*` + `fetch`). Live trade verification + deploy are the
main agent's job.

Motivation (owner, live-testing): he wants per-rare live scan status, NO manual button presses to
get valid prices, and better failure visibility - his scans report "listings exist but none had a
buyout price" on every row, and the debug fields below are meant to expose why.

---

## 1. The pinned v1.1 protocol (additive; both agents implement EXACTLY this)

The wire format from D-0006/07 (documented in `docs/notes-public-ext.md`) is UNCHANGED. v1.1 only
ADDS a progress stream + a per-result debug object. Everything is feature-detected, so old site +
new extension and new site + old extension both keep working (see section 4).

### Background -> tab (service worker emits per-item progress)
`chrome.tabs.sendMessage(sender.tab.id, ...)`:
```js
{ type:"bpc-price-progress", reqId, key, stage, detail }
```
`content.js` relays it to the page VERBATIM as:
```js
{ source:"bpc-ext", type:"price-progress", reqId, key, stage, detail }   // via window.postMessage
```

### Stages (one per transition) and their `detail`
| stage       | detail                          | emitted when |
|-------------|---------------------------------|--------------|
| `queued`    | `{}`                            | all items, up front, before any work |
| `searching` | `{}`                            | immediately before the search POST |
| `waiting`   | `{ waitMs }`                    | the rate limiter (or a 429 back-off) pauses > 1s |
| `fetching`  | `{}`                            | immediately before the fetch GET |
| `done`      | `{ total, amount, currency }`   | priced from the cheapest buyout listing |
| `nobuyout`  | `{ total, fetched, nulls }`     | listings returned, none had a buyout price |
| `error`     | `{ message, status }`           | this item failed (`status` = HTTP status or `null`) |

### Per-result debug object (in the existing `price-result` reply)
Every element of `results[]` now ALSO carries:
```js
debug: { searchStatus, fetchStatus, fetched, nulls }
```
- `searchStatus` / `fetchStatus` - HTTP status of each call (or `null` if never reached).
- `fetched` - how many listings the fetch actually returned (0..10).
- `nulls` - how many of those had no buyout price.

**This is exactly the owner's mystery-solver.** "Listings exist but none had a buyout" =
`amount:null` with `total>0`. The debug now distinguishes the two very different causes:
- `fetched: N, nulls: N` (fetchStatus 200) -> the fetch returned N listings but our parser found a
  buyout price in none of them (points at the price-extraction path / genuinely offer-only rows).
- `fetched: 0` (fetchStatus 200) -> search found `total>0` but the fetch returned no listings
  (query/fetch mismatch, or the ids expired).
- `searchStatus: 4xx/5xx` -> the failure is upstream at search; the row is an `error`, not nobuyout.

---

## 2. What changed in the code

### `background.js`
- **`priceMany(queries, league, ctx)`** - new `ctx` param `{ tabId, reqId }` (null = no progress).
  Emits `queued` for every item up front, then per item emits the terminal `done`/`nobuyout`/
  `error`, and attaches `debug` (a snapshot of the per-item accumulator) to EVERY result -
  priced, nobuyout, and error alike.
- **`priceQuery(query, league, emit, dbg)`** - emits `searching` before the search and `fetching`
  before the fetch; records `dbg.fetched` (listings returned) and `dbg.nulls` (listings with no
  buyout).
- **`tradeRequest(bucket, method, url, body, attempt, emit, dbg)`** - records `dbg.searchStatus` /
  `dbg.fetchStatus` from the response; emits `waiting` on a 429 back-off. **Diagnostics-in-product:**
  a non-OK response now throws `HTTP <status> from trade API: <first 80 chars of body>`, and a
  non-JSON response throws `non-JSON response (HTTP <status>, content-type '<ct>'): <80 chars>`.
  Both attach `.status` to the Error so `priceMany` can put it in the `error` detail.
- **`rateLimitGate(bucket, emit)`** - emits `waiting { waitMs }` whenever the computed pause is
  > 1s (sub-second jitter is not worth a message).
- **New helpers:** `emitProgress(ctx,key,stage,detail)` (fire-and-forget `chrome.tabs.sendMessage`,
  swallows all send failures + reads `lastError`); `protoAtLeast(v,maj,min)` (tolerant version
  compare: `"1.1"`, `"1.1.0"`, number `1.1`, etc.); `snapshotDebug(dbg)`.
- **Message listener** - for `bpc-price`, builds `ctx` ONLY when
  `sender.tab && sender.tab.id != null && protoAtLeast(msg.protocolVersion, 1, 1)`. Popup requests
  (no `sender.tab`) and pre-1.1 requests get `ctx = null` -> progress silently skipped. The
  `price-result` reply path is unchanged.

### `content.js`
- Forwards `reqId` + `protocolVersion` on the existing `bpc-price` message (REQUIRED: the worker
  cannot label progress with the page's `reqId`, nor version-gate, without them - there is no other
  channel). This is the only change to the request bridge; it is purely additive (a pre-1.1 worker
  ignores both fields).
- New receive-only `chrome.runtime.onMessage` listener relays `bpc-price-progress` to the page as
  `price-progress` (via the existing `toPage`, which stamps `source:"bpc-ext"`). Returns undefined
  so the message channel closes immediately.

### Manifests / packaging
- `manifest.json` + `manifest.dev.json` version `1.0.0` -> **`1.1.0`**.
- `README.md` - version strings updated (1.0.0 -> 1.1.0), a "Live scan status" section + the debug
  field added to the protocol docs.
- Rebuilt `public/dist/trade-bridge-{chrome-edge,firefox}-1.1.0.zip`; removed the stale 1.0.0 zips.
- **No manifest permission change.** `chrome.tabs.sendMessage` does NOT require the `tabs`
  permission (only privacy-sensitive tab fields do), and the content script is already injected on
  the DivTally origins, so the worker can message those tabs with the existing grants. `storage`
  + narrowed `host_permissions` are untouched (D-0009 minimal-permission posture preserved).

---

## 3. Verification performed (offline; no pathofexile.com)
- `node --check` on `background.js`, `content.js`, `popup.js`, `test_protocol.mjs` - all pass.
- **`extension/test_protocol.mjs`** (`node extension/test_protocol.mjs`) - loads `background.js`
  verbatim into a scope with stubbed `chrome.*` + `fetch` (+ a setTimeout clamped to <=5ms so
  rate-limiter/429 sleeps are near-instant). 35 checks, all PASS:
  - **A** 2 items (done + nobuyout): asserts the EXACT event sequence
    `queued x2 -> searching/fetching/done (k1) -> searching/fetching/nobuyout (k2)`, the
    `done`/`nobuyout` details, and both results' `debug` (`{200,200,1,0}` and `{200,200,3,3}`).
  - **B** search HTTP 400: asserts `queued/searching/error` (no fetching), `error.detail.status
    === 400`, the message names `HTTP 400` + carries the body head + is truncated to 80 body chars
    (length 105), and `debug {400,null,0,0}`.
  - **C** pre-seeded limiter: asserts a `waiting` event with `waitMs > 1000` lands between
    `searching` and `fetching`, and the item still resolves to `done`.
  - **D** gating via the real message listener: popup (no tab, no version) -> pricing still works,
    ZERO progress; tab + `protocolVersion:"1.1"` -> progress, all to the right tabId + reqId; tab +
    `protocolVersion:"1.0"` -> ZERO progress (version gate).
  - **P** `protoAtLeast` unit checks (1.1/1.1.0/number 1.1/1.2/2.0 true; 1.0/1/undefined false).
- `build_zips.py` runs clean (exit 0, no placeholder). Both zips: `testzip()` OK; manifest version
  1.1.0; Chrome `background` = `service_worker` only, Firefox = `service_worker` + `scripts`;
  `background.js` in-zip contains the progress code; `content.js` in-zip relays progress + forwards
  `protocolVersion`; `manifest.dev.json` + `generate_icons.py` excluded.

**Not done (by rule):** no live trade call, no store submission, no deploy - owner/main-agent steps.

---

## 4. Compatibility matrix (why nothing breaks)
| site \ extension | pre-1.1 extension | v1.1 extension |
|------------------|-------------------|----------------|
| pre-1.1 site (no `protocolVersion`) | unchanged | worker sees no `protocolVersion` -> `ctx` null -> no progress; pricing + `price-result` unchanged |
| v1.1 site (sends `protocolVersion`) | old worker ignores the extra fields -> no progress, pricing works; site feature-detects the absence of progress | full progress stream + `debug` |

The `debug` object is attached to results unconditionally (additive field); a pre-1.1 site simply
ignores it. A page that receives an unknown `price-progress` type ignores it.

---

## 5. Coordination note for the main agent (RULE 1)
The v1.1 progress protocol is an additive extension to the page<->extension contract - a
"fundamental" item under RULE 1. It is fully specified here, but I could not add a decision-log
entry (the decision log is outside this agent's file ownership). **Please record it in
`docs/00-decision-log.md`** (next id looks like D-0013) and confirm the site-side agent implements
the page half to the same spec (send `protocolVersion` on `price`; render `price-progress`; read
`result.debug`). The pinned spec both agents share is reproduced verbatim in section 1.
