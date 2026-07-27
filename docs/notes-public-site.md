# Public front-end — `public/site/` (B-001 / D-0008)

The self-contained static site deployable to Cloudflare Pages as-is. It is the **stash skin**
(D-0007, "stash is the face") rewired for the public architecture: a one-shot serverless build
document + client-side rare pricing (community cache · whisper-paste · extension bridge). Built
2026-07-26 by the site agent.

**Hard invariant honored (B-001):** nothing in this site ever calls `pathofexile.com`. The site
fetches only our own `API_BASE/api/build` (which reads poe.ninja only) and `WORKER_BASE/cache`
(a dumb KV store). Every request to pathofexile.com originates in the visitor's own browser — a
trade link *they* click, or the extension running on *their* IP. No live trade call, no cache
seeder run, and no `pathofexile.com` call was made building or testing this.

Contracts this was built against (read these for the shapes): `docs/public-contract.md` (the
`/api/build` response), `docs/notes-public-worker.md` (`/cache` GET/POST + the cache-key recipe),
`docs/notes-public-ext.md` (the `postMessage` extension protocol), `docs/backlog.md` B-001.

---

## 1. File map (all created; ownership = `public/site/**`)
```
public/site/
  config.js            REPLACE_ME placeholders: API_BASE / WORKER_BASE / STORE_URLS / REPO_URL.
                       Loaded first; read by core.js AND both pages. Owner edits this, nothing else.
  index.html           the stash skin, public-mode. Copied verbatim from bpc/ui/stash.html then
                       adapted: server job/poll + rare-picker REMOVED; manual-pricing panel,
                       calm upgrade card, bridge badge, footer, and how-it-works link ADDED.
  how-it-works.html    the B-001 transparency page (self-contained: own CSS + inline JS). Exact
                       endpoints, what is stored, a WORKING cache opt-out toggle, rate-limit ethics,
                       GGG non-affiliation. Doubles as launch-post copy.
  assets/core.js       the PUBLIC engine (adapted copy of bpc/ui/assets/core.js). See §2.
  assets/sample.js     verbatim copy of bpc/ui/assets/sample.js — the ?mock / demo snapshot.
  stub-build.json      a valid public-contract build document for local testing of the fetch path
                       (used only with ?stub; harmless to ship).
```

## 2. What changed in `core.js` (local → public)
The whole view-facing surface is **preserved byte-for-byte** (currency formatting, `totals()`,
include/exclude, purchase tracking, `gemGroups`/`gemBreakdown`/`gemHost`) so the stash view renders
unchanged. Only the backend was swapped:

- **Job/poll → one shot.** `start()` now does `GET/POST {API_BASE}/api/build` and `loadBuild(doc)`
  reshapes the public document (contract §2) into the view's state: `state.items` (skeleton) +
  `state.priced[index]` (the item's embedded `price` object, with `trade_url`/`trade_query` copied
  on so `p.trade_url` keeps working). Short poe.ninja/pobb.in links go via GET (CDN-cacheable);
  long PoB codes via POST (URL-length safe). Removed: `/api/price`, `/api/job`, `/api/rare`,
  `/api/leagues`, `/api/cache`, all polling, and the entire server-side rare-picker flow
  (`submitRare`/`skipRare`/`searchAllRares`/…) — superseded here (RULE 6 clean cutover; there is
  no server to run a rare search).
- **Three client-side price sources**, each folded into the same rows/totals via `applyPrice()`:
  1. **Community cache read-through** — after a build loads, `cacheReadThrough()` computes the
     shared cache key for every *unpriced* rare/magic row and `GET {WORKER_BASE}/cache?league=&keys=`
     (≤60/batch), folding any hits (`source:"cache"`). Respects the opt-out.
  2. **Whisper-paste (manual)** — `parseWhisper(text, divineRate)` (pure, unit-tested) reads a full
     GGG buyout whisper (`…listed for 35 chaos…`), a `~b/o`/`~price` note, or a bare `35c` / `2 div`
     / `200 exalted` / fractions. `applyWhisper()` folds chaos/divine into the total and **persists
     per build+item** in `localStorage` (`bpc_manual:<account>:<char>`), restored on reload. Chaos +
     Divine convert (via `meta.divine_to_chaos`); any other currency is shown raw and kept OUT of
     the total (never a fabricated number — the "no misleading number" guardrail).
  3. **Extension bridge** — the documented `postMessage` protocol, byte-identical to `_exttest.html`
     / the shipped `content.js`: announce/`ping` → `hello`/`pong` detect; `autoscan()` groups the
     unpriced rares by league and sends ONE `price` message per league with `queries:[{key, query}]`
     (the **inner** query object, not the `{query:…}` wrapper); results fold in (`source:"trade"`)
     **and** POST back to the community cache (`cachePost()`), short TTL, for the next visitor.
     `credentials`-free per the extension; the site never touches the trade API itself.
- **Cache key recipe** (`cacheKey`/`itemIdentity`/`leagueKeyspace`) copied from
  `notes-public-worker.md §1` and proven byte-identical to the Worker's expectations (see §4).
- **Recent builds** now persist in `localStorage` (`bpc_recent_builds`) since there is no
  `/api/cache`. Leagues are a small static override list (Auto = the build's own league) — the
  public function can't call the trade `data/leagues` endpoint.

## 3. What changed in the page (`index.html`)
Same look, adapted behavior:
- **Toolbar** trimmed to URL + league override + listing status + "fresh pull" + Appraise (the
  `advanced`/`survey me` server-picker toggles are gone).
- **Rares are "manual state":** each unpriced rare/magic gets a red/orange board cue as before, and
  a new **"Rares to price"** panel lists them with an *open search ↗* link, a whisper-paste input,
  and (when the bridge is live) a per-row ⚡auto + a top **Autoscan (N)** button. Clicking a rare
  slot (or its ✎ pip) opens a lean manual-pricing modal (trade link + paste + extension).
- **Calm upgrade card** (does / never-does list + store-link placeholders) shows only when there
  are rares to price AND no extension is detected; a **bridge badge** in the top nav flips to
  "bridge active" when it is. No dark patterns — the site is fully usable with nothing installed.
- **Footer** on every page: how-it-works, open-source link (placeholder), a live community-cache
  on/off toggle, and **"Not affiliated with or endorsed by Grinding Gear Games."**

## 4. Verification (local, offline — ZERO pathofexile.com calls, no live API, no seeder)
Runner: `scratchpad/test_core.mjs` (Node 22). core.js is DOM-free, so it loads under shims
(window/localStorage/fetch/crypto + a fake extension over postMessage) and the REAL logic is
exercised. **74/74 assertions pass.** Coverage:
1. **`parseWhisper`** — `35 chaos`, `35c`, `2 div`/`2 divine`/`1.5 div`, full `…listed for 35
   chaos…` whisper, `~b/o 2 divine`, `~price 150 chaos`, "listed for" beating a later stash note,
   `200 exalted`/`5 mirror` (currency kept, chaos null with no rate), fractions, junk/empty → null.
2. **Cache-key parity** — `cacheKey`/`itemIdentity`/`leagueKeyspace` vs the real
   `public/worker/worker.js`: keys match `^v1_<32hex>$`, pass `worker.validKey`, are
   slot-independent, and site-built records pass the Worker's own `sanitizeEntry`.
3. **`loadMock`** → items/totals render; granted gem excluded; 6-link gem breakdown.
4. **`applyWhisper`** folds `2 div` into the total, auto-includes, persists to localStorage;
   bad paste rejected; `clearManual` reverts.
5. **`loadBuild`** reshapes the stub `/api/build` document (via mocked fetch): 5 items, unique 3c
   and gem 265c from poe.ninja, `trade_url`/`trade_query` copied onto prices, gem `sockets` derived,
   `manualRows` = exactly the 3 unpriced rares/magic, `totals = 268` (poe.ninja-priced only).
6. **Cache read-through** — a seeded `/cache` GET fills a jewel to 50c (`source:"cache"`) and it
   joins the total.
7. **Extension bridge** — `pong` flips the bridge active; `autoscan` sends a protocol-correct
   `price` message (`source:"bpc-page"`, per-league, INNER query object); divine results fold to
   chaos (`source:"trade"`); records POST back with worker-valid keys + sanitize-passing values;
   a "no buyout" result leaves the row unpriced (no fake number).

Also: `node public/worker/worker.test.mjs` → **55/55** (confirms the import
path + contract understanding); `node --check` on config.js / core.js / sample.js and both HTML
files' inline scripts → all parse; a static pass confirms **all 49 `$('#id')` references resolve**
(static or dynamically created) and the **handshake tokens match `_exttest.html` exactly**;
`python -m http.server` on `public/site:8952` → `index.html`, `index.html?mock`, `how-it-works.html`,
`config.js`, `assets/*.js`, `stub-build.json` all HTTP 200 with expected markers; stub JSON valid.
Server killed after.

### How to re-run
```
node <scratchpad>/test_core.mjs                     # 74 core assertions, offline
node public/worker/worker.test.mjs                  # 45 worker assertions, offline
cd public/site && python -m http.server 8952        # then open:
  http://127.0.0.1:8952/index.html?mock             #   demo, no API
  http://127.0.0.1:8952/index.html?stub=1&api=http://127.0.0.1:8952   # real fetch path vs stub-build.json
  http://127.0.0.1:8952/how-it-works.html
```

## 5. What I could NOT test locally (flagged)
- **No real browser render.** `jsdom` isn't installed and there's no browser-automation tool here,
  so the DOM was not painted live. Mitigated by: the node tests drive the real core logic that the
  view consumes; every referenced DOM id was statically confirmed to resolve; all inline JS
  parses; the served pages return 200 with the expected elements. A human should still open
  `index.html?mock` once (owner-test rung) to eyeball layout/animation.
- **No live `/api/build`.** By rule I did not run the Vercel api runner live (it calls poe.ninja).
  The fetch/reshape path was proven against `stub-build.json` (a hand-written valid contract doc)
  instead. First real end-to-end (poe.ninja → document → render) is an owner post-deploy step.
- **No live worker, no cache round-trip over the wire.** Cache GET/POST were exercised against a
  mock; key/record *agreement* with the real worker is proven via `worker.js`'s own validators.
- **No live extension.** The bridge was driven by a fake extension speaking the documented
  protocol; a real Chrome/Edge/Firefox load-unpacked test against `/v/_exttest` (or this site) is
  the owner's step per `docs/notes-public-ext.md`.

## 6. Known limitations / follow-ups (not blockers)
- **Non-chaos/divine currencies** (exalted, mirror, …) can't be converted — the build document only
  carries `divine_to_chaos`. Such a paste/extension result is shown raw and excluded from the chaos
  total. If this matters, add more rates to the `/api/build` `meta` and extend `toChaos`.
- **Ranged variant uniques** (`unique-ninja-range`, confidence low) are server-priced, so clicking
  them opens the trade search rather than the manual pricer; there's no in-UI way to override that
  number with a whisper today. Rares/magic are the manual focus.
- **Manual panel re-renders wholesale** on each price event; an in-progress input elsewhere could be
  wiped if an async cache fill lands mid-type (rare — cache fills happen right after load). A
  targeted row update would remove the risk.
- Owner deploy steps (fill `config.js`, set the Vercel/Worker/store URLs, submit the extension) are
  the manual GOING-PUBLIC.md sequence — this site is otherwise deploy-ready.
