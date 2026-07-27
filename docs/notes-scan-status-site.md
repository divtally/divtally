# Live scan-status UX (site side) — implementation notes

Task owner: scan-status-site agent (2026-07-27). Files touched (ownership honored — site only):
`public/site/assets/core.js`, `public/site/index.html`, `public/site/test_scanstatus.mjs` (new),
this file. **No pathofexile.com calls. No extension/worker/engine edits** (those are other agents').
Governing spec: `docs/00-decision-log.md` D-0006..D-0012, `docs/notes-public-ext.md` §1, and the
pinned **protocol v1.1** addition (per-item progress). Owner is live-testing; his asks drove this:
per-rare live status, no button press for valid prices, and failure visibility (his scans show
"listings exist but none had a buyout price" on *every* row — the debug fields must expose why).

---

## 1. Protocol v1.1 — exactly what the site now speaks (must match the extension side)

**Page → extension** (unchanged shape + one additive field):
```js
{ source:"bpc-page", type:"price", reqId, league, queries:[{key,query}], protocolVersion: 1.1 }
```
`protocolVersion: 1.1` is sent on **every** price message (feature flag). An old extension ignores
the field and emits no progress; the site detects that by simply never receiving progress events.

**Extension → page** (new message the site consumes, verbatim per the pin):
```js
{ source:"bpc-ext", type:"price-progress", reqId, key, stage, detail }
```
`stage` ∈ `queued | searching | fetching | waiting | done | nobuyout | error`, with `detail`:
| stage      | detail shape                                   |
|------------|------------------------------------------------|
| `waiting`  | `{ waitMs }`  (rate-limiter pause)              |
| `done`     | `{ total, amount, currency }`                  |
| `nobuyout` | `{ total, fetched, nulls }`                    |
| `error`    | `{ message, status }`  (status = HTTP status) |
| others     | `null`                                          |

**Final `price-result`** per-item objects additionally carry (v1.1):
```js
debug: { searchStatus, fetchStatus, fetched, nulls }
```
The site treats `debug` as optional (absent from an old extension) and folds it into the row note +
keeps the raw object on `price.debug` for the tooltip. **Progress is STATUS ONLY** — the priced
numbers still come from the final `price-result` (single source of truth), exactly as before.

Routing: progress is accepted only when `reqId` belongs to the live scan (`scan.reqIds[reqId]`) **and**
`key` is in the scan's send order — stale/foreign events are ignored.

---

## 2. core.js changes (engine/event surface)

- **Scan session module** (new): `scan = {active, order, names, status, reqIds}` + `scanBegin/scanSet/
  scanEnd/scanSnapshot`. Emits a new **`scanstatus`** event and exposes **`bpc.scanStatus()`**:
  `{ active, total, done, current, order, names, status{ key → {stage, detail, ahead, resolved,
  waitUntil} } }`. `ahead` = number of unresolved rows earlier in **send order** (drives "waiting — N
  ahead"); `current` = the active row (searching/fetching/waiting), else the next unresolved (drives
  the progress-bar label + %). `reset()` now calls `scanReset()` so a new build starts clean.
- **`price-progress` handler** added to the bridge `message` listener (routes into `scanSet`).
- **`priceRowsViaExtension`** — the **D-0012 chunked sequential send is preserved verbatim** (the
  4-line comment, `CHUNK=3`, per-chunk `30000 + 30000*len` timeout, sequential `nextChunk`, "a failed
  chunk never blocks the rest"). Additive only:
  - `scanBegin()` over the flat send order before the first chunk; `scanEnd()` after the last.
  - Each `price` message now carries `protocolVersion: 1.1`; its `reqId` is registered in
    `scan.reqIds`; the chunk's rows are marked `scanning` at send time (the generic "sent" state that
    v1.1 progress later refines — and the **only** state an old-extension run ever shows).
  - `foldBatch` resolves each row's scan stage (`done`/`nobuyout`/`error`) and now threads `debug`
    into the note (`debugSuffix()`) + stores it on `price.debug`. A per-chunk `keys` list lets a
    whole-chunk error/timeout (or an omitted key) resolve to a self-describing `error` so the bar +
    chips always complete (previously such rows were left silently untouched).
- **`bpc.scanStatus`** exported on the api object. No existing message types changed → old site + new
  extension and new site + old extension both keep working (feature-detected).

## 3. index.html changes (the UX)

- **Per-row status chip** (`.mr-scanchip`) injected into every "Rares to price" row. While a row is
  actively scanning its manual controls (open-search / input / apply / auto) give way to the chip
  (`.mrow.scanning`); a terminal **failure** keeps the controls **and** shows the chip
  (`.mrow.scanfail`) so the visitor can still paste a price. Chip text by stage:
  queued → "waiting — N ahead" / "up next"; scanning → "scanning…"; searching → "searching listings…";
  fetching → "fetching listings…"; waiting → "rate limit — Ns" (live countdown via a 1s ticker);
  nobuyout → "⚠ no buyout among N listings · F fetched, M without a buyout"; error → "✕ <msg> (HTTP n)".
- **Autoscan button → progress bar** while a scan runs: a determinate fill + "scanning k/N — <item>…",
  disabled during the run, restored to "⚡ Autoscan" on `scanEnd`. Driven entirely by `scanstatus`.
- **Board slots** for scanning rares get the existing "Appraising" overlay (`.slot.loading`), its
  label set to the live stage; resolved rows repaint via `updateSlot`.
- **Auto-scan-on-load toggle** — a small remembered checkbox by the Autoscan button
  (`localStorage bpc_autoscan_auto`, **DEFAULT ON**, only shown when the bridge is active). When on,
  a freshly-loaded build with unpriced rares auto-runs Autoscan **exactly once** (`autoFired` Set keyed
  by build identity → never loops, never re-triggers on cache-only reloads; skips the demo, skips while
  a scan is in progress). This is the owner's "not very auto if i have to press a button" ask.
- **Feature-detect / graceful degrade**: none of the UI depends on v1.1 events. With an old extension,
  rows sit at the generic "scanning…" chip (chunk boundaries are page-side) and resolve from the chunk
  reply; the bar still advances per chunk; failures still surface (minus the debug tail).

## 4. Owner's live mystery — what will now be visible

For a row that comes back "listings exist but none had a buyout price", the note **and** the chip now
carry the debug fields once the extension ships v1.1:
`… [search 200, fetch 200, 10 fetched, 10 w/o buyout]`. That distinguishes "search returned nothing"
(fetched 0) from "listings fetched but every price was null" (fetched N, nulls N) — the latter points
at either genuinely offer-only listings or a price-read bug in the extension's fetch parsing.
**Dependency:** the debug tail only appears once the **extension side** emits `debug` + progress
(protocol v1.1). Against the currently-shipped extension the row still reads the plain sentence (no
tail) and prices still work — no regression.

## 5. Verification (offline; no pathofexile.com)

- `node --check assets/core.js` → OK. `node --check test_scanstatus.mjs` → OK.
- **`node public/site/test_scanstatus.mjs` → 47 passed, 0 failed.** Loads core.js in a `vm` realm with
  a fake-window postMessage bus + a scripted fake extension, and drives a full autoscan:
  - **NEW extension**: protocolVersion 1.1 on every message; D-0012 chunking (2 msgs, sizes [3,1],
    sequential); all stages observed (queued/searching/fetching/waiting/done/nobuyout/error); "N ahead"
    and `waitUntil` bookkeeping; final `done===total` (bar 100%), inactive; prices auto-applied from
    `price-result`; nobuyout note self-describing with debug fields + `price.debug` retained; HTTP-403
    error surfaced; only the two successes auto-included in totals.
  - **OLD extension** (no progress, no debug, ignores protocolVersion): page still sends
    protocolVersion 1.1; **no** searching/fetching/waiting stages ever appear (only generic "scanning");
    scan still completes and prices still auto-apply; nobuyout/error still surface (no debug bracket).
  - single-row scan tracks exactly 1 item; loading a new build clears the scan session.
  - compile-checks the index.html inline `<script>` (parse only).
- `python -m http.server` smoke of `index.html?mock`: index + core.js + sample.js + config.js all
  200; new markers present in the served page; server killed after.

## 6. Not done (by rule / out of scope)

- No extension/worker/engine edits — the extension must implement the emitter side of protocol v1.1
  (progress events keyed to `sender.tab.id` + `debug` on results) for the precise chips + debug tail to
  appear. Site is forward/backward compatible either way.
- No live trade calls, no deploy (main agent deploys). No decision-log entry written (site agent scope);
  recommend the main agent log the v1.1 protocol addition as a new D-entry when both sides land.
