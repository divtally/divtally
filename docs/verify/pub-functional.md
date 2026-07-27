# Public build — functional verification (B-001 / D-0008)

**Verifier:** functional-verification agent, 2026-07-26. **Verdict: PASS** — the public build
(api / site / worker / seeder / extension) is functionally sound and deploy-ready pending the
owner's documented manual steps (fill `config.js`, deploy Vercel + Worker, submit extension).
**2 MINOR findings** (one contract-count cosmetic, one deploy-config footgun), no blockers/majors.

Spec of record read verbatim first: `docs/00-decision-log.md` D-0006..D-0008, `docs/backlog.md`
B-001, `docs/public-contract.md`, and each component's `docs/notes-public-*.md`.

## Hard invariant — CONFIRMED
Nothing server-side ever calls `pathofexile.com`. Directly exercised `_http._guard_host`:
`www.pathofexile.com`, apex `pathofexile.com`, and `prod.pathofexile.com` all **blocked**;
`poe.ninja` **allowed**. Every emitted document (offline + one live) contains **zero**
`/api/trade` / `pathofexile.com/api` strings — only browser `/trade/search/` links (58 in the
live doc). No live trade call, no live cache seed, and no `pathofexile.com` request was made by
anything I ran. The only live network was a handful of poe.ninja reads (one character + economy).

## Method / containment note
- Wrote **no** files into the project except this report (file-ownership honored). All checks ran
  via inline `python -`/`node --input-type=commonjs` heredocs (nothing persisted), `zipfile`
  in-memory reads, `python -m http.server` (serves, writes nothing), and the committed runners.
- The committed `public/api/_verify.py` runner was driven by **importing** it and calling
  `phase_a()`/`phase_b()` (not `main()`), so its optional `sample_response_*.json` dump did **not**
  run — nothing was written. The vendored `_lib/cache.py` + `_verify.fresh_cache()` create
  ephemeral `tempfile.mkdtemp("bpc_test_")` dirs under the system temp (inherent to the runner;
  not the OneDrive-synced part of the home dir). No other writes outside the project.
- All local servers were killed after use (static :8952, api :8955, plus in-process :8951/:8953
  `shutdown()` in their scripts). Confirmed down.

---

## 1. API — `public/api/` (Vercel Python function)  ✅
Ran the committed `_verify.py` phase A (offline fixtures) + phase B (**one live poe.ninja
character**, `example-0416/TestCharacter`, still in the current Allflame top-5) through the
**real Vercel `handler`**, plus independent assertions.

- **Committed harness: 0 failures.** Phase A: ascii fixture 41 items, unicode 28 items, PoB
  import 64 items, `bad_input` shape, slim-vs-full `StatMapper` byte-identical, gems priced from
  poe.ninja, granted gem excluded, strict-JSON. Phase B live: HTTP 200 in ~2.0 s.
- **Headers (independent, live + offline handler):** success → `Access-Control-Allow-Origin: *`
  and `Cache-Control: public, s-maxage=600, stale-while-revalidate=86400`; `OPTIONS` → **204** +
  `Access-Control-Allow-Methods: GET, POST, OPTIONS`; error → **400** + `Cache-Control: no-store`
  + `error_type: bad_input`.
- **Contract (independent, offline + live docs):** every `rare`/`magic` row carries a
  `/trade/search/` `trade_url` **and** a `trade_query.query` dict, is not poe.ninja-priced, and has
  a null median; poe.ninja prices present (21 ninja-priced rows live); **no item lacks a query**;
  zero `/api/trade` in the document.
- **Host guard:** blocks pathofexile.com (apex/sub/www), allows poe.ninja.

**MINOR-1 (contract count).** `response.py:146` `priced_n = sum(... source=="poe.ninja")` counts a
**granted-only gem group** that has *no* poe.ninja number (`source=="poe.ninja"` but all chaos
tiers `null` — e.g. "Herald of the Hive", item-granted, its only gem excluded). So
`totals.priced_items` = 6 (live 22) while only 5 (live 21) items actually carry a number, versus the
contract §2.2 definition "items with a poe.ninja number". Non-misleading: `totals.chaos.median`
correctly excludes it (2190.1 offline), and the site's `core.js totals()` recomputes counts
client-side by `median!=null` (shows 5), so the UI is unaffected. Fix if desired: require a finite
median (or `_has_tier`) in the `priced_n` predicate.

---

## 2. Site — `public/site/` (Cloudflare Pages static)  ✅
core.js loaded under Node (CommonJS; DOM-free) with window/localStorage/fetch shims; real logic
exercised.

- **`parseWhisper` (node, pure):** 15 cases pass — `35 chaos`, `35c`, `2 div`/`2 divine`/`1.5 div`,
  full `…listed for 35 chaos…` whisper, `~b/o 2 divine`, `~price 150 chaos`, fraction `3/2 div`,
  priority ("listed for" beats a later `~b/o`), and `200 exalted`/`5 mirror` → **chaos `null`**
  (kept out of totals, no fabricated number). Junk/empty/null → `null`.
- **`loadBuild` reshape (stub contract doc):** 5 items; `totals.median=268` (ninja-priced only:
  unique 3 + gem 265); 2 included/priced; `manualRows` = exactly the 3 unpriced rares/magic, each
  with a `/trade/search` link.
- **Whisper fold-in + persistence:** `2 div` on a rare → total 504.6 and a `bpc_manual:<build>`
  localStorage entry `{currency:"divine",chaos:236.6}`; `200 exalted` → total unchanged, persisted
  with `chaos:null`. **Reload → `restoreManual` re-applies** from localStorage (504.6).
  `clearManual` reverts to 268 and drops the localStorage entry.
- **`loadMock` (demo, no backend):** 26 items, totals 14060.2, the 1 granted gem excluded from the
  total, 5 host-grouped gem sections.
- **Real site→local-api integration (genuine HTTP):** pointed core.js at the fixture-backed
  `handler` via the built-in **`?api=` override** (no `config.js` edit needed) using Node's real
  `fetch`; `startUrl` → real GET → real handler doc → reshaped **41 items**, `meta.league=Allflame`,
  ninja numbers folded (median 2190.1), 35 manual rows all with trade links.
- **Static serve** (`python -m http.server :8952`): `index.html`, `index.html?mock`,
  `index.html?stub=1&api=…`, `how-it-works.html`, `config.js`, `assets/core.js`, `assets/sample.js`,
  `stub-build.json` all **200** with correct content-types; markers present (config/sample/core
  script tags, `#bridgeBadge`, `#upgradeCard`, GGG disclaimer, how-it-works link). `node --check`
  clean on config.js/core.js/sample.js.
- **UI-marker statics:** upgrade card shows only when `unpriced>0 && !bridge.active`
  (`updateUpgradeCard`); bridge badge flips on `bridge` event; footer has how-it-works + open-source
  + live community-cache toggle + "Not affiliated with or endorsed by Grinding Gear Games."
  `how-it-works.html` documents exact endpoints, localStorage keys, a working cache opt-out, and
  rate-limit ethics.

*Not testable here (flagged, as the build notes already flag):* no real browser paint (no
jsdom/browser) — owner should eyeball `index.html?mock` once; live extension bridge driven only by
the protocol cross-check (below), not a loaded extension.

---

## 3. Worker + key recipe — `public/worker/`  ✅
- **`node worker.test.mjs` → 45/45.**
- **3-way cache-key recipe parity (the required cross-check):** fed identical item+league JSON
  (a unique with unsorted mods, a gem with 2 supports, league `"Hardcore  Allflame"` with a double
  space) to **seed_cache.py** and **core.js**; computed a sample key in each and compared, and
  validated with **worker.js**:
  - `league_keyspace` identical py/js/worker → `"hardcore allflame"` (double space collapsed);
  - `item_identity` byte-identical js==py (implicit/explicit mods + gem supports sort identically);
  - `cache_key` **byte-identical** js==py for both items (`v1_9a8a7a20…`, `v1_ba45a9c2…`);
  - `worker.validKey` accepts them; `worker.kvName` namespaces to `p1:hardcore allflame::<key>`;
    shape `^v1_[0-9a-f]{32}$`.
  The recipe is identical in all three. ✅

---

## 4. Seeder — `tools/seed_cache.py`  ✅ (no trade calls)
- **`--dry-run -n 5`:** resolved current league (Allflame, snapshot `0414-…`), listed the top-5
  builds incl. a Cyrillic name (UTF-8 stdout OK) — **poe.ninja ladder only, priced nothing**.
- **`--from-cache-only`:** harvested the one cached build on disk
  (`TestCharacter`/Elementalist/Allflame) → **23 priced records, zero network** (skipped/
  unpriceable rows correctly omitted).
- **Seeder→Worker ingestibility (in-memory, no `--out` write):** all **23/23** records pass the
  Worker's own `sanitizeEntry`, all 23 keys pass `validKey` (0 bad, 0 rejected) — proving the
  seeder's output is worker-ingestible under the shared recipe.
- The live default `--worker-url` mode (the only trade-touching path) was **not** run, per rule.

---

## 5. Extension — `extension/` + `public/dist/*.zip`  ✅
- **Both zips unzip clean** (`testzip()` = None), 10 files each, **no** `manifest.dev.json` /
  `generate_icons.py` (dev-only excluded), all payload + 16/32/48/128 icons present.
- **Manifest valid + minimal (from the zipped copies):** MV3, v1.0.0, `permissions:["storage"]`,
  `host_permissions:["https://www.pathofexile.com/api/trade/*"]` (narrowed to the trade API), no
  `tabs`/`cookies`/`<all_urls>`/`webRequest`/`scripting`/`history`, gecko id present, content-script
  match is only the placeholder domain (no localhost/staging in the store artifact). Chrome zip:
  `background.service_worker` only; Firefox zip: adds `background.scripts` fallback.
- **Protocol cross-check (static, content.js ↔ core.js):** matches byte-for-byte. Site sends
  `{source:"bpc-page", type:"ping"|"price", reqId, league, queries:[{key,query}]}` (inner query
  object); content.js listens for those, forwards `{league, queries}` to the SW, and emits
  `{source:"bpc-ext", type:"hello"|"pong"|"price-result", reqId, results|error}`. `background.js`
  only ever calls `https://www.pathofexile.com/api/trade/{search,fetch}` with `credentials:"omit"`.

**MINOR-2 (deploy config).** `vercel.json` (sets `build.py maxDuration:30` + `includeFiles`) lives
at `public/api/vercel.json`, but Vercel reads `vercel.json` only from the **project root**
(= `public/`). If the owner does not copy it to `public/vercel.json` before deploy (as
`notes-public-api.md §6` already flags "ACTION REQUIRED"), `build.py` runs at the Hobby default
(~10 s) and a cold call — which fetches the ~4.6 MB poe.ninja SkillGem overview + 5 unique overviews
— can 504. Fix: copy `vercel.json` to `public/` root at deploy (owner step; already documented).

---

## Reproduce
```
python public/api/_verify.py                              # full api harness (writes samples to temp)
node public/worker/worker.test.mjs                        # 45/45
python tools/seed_cache.py --dry-run -n 5                 # ladder only
python tools/seed_cache.py --from-cache-only              # 23 records, no network
cd public/site && python -m http.server 8952 --bind 127.0.0.1
  # then index.html?mock  ·  index.html?stub=1  ·  index.html?api=<local api>  ·  how-it-works.html
```
(The parity, whisper, reshape, ingestibility and header checks above were run as inline
python/node harnesses — see the verification session for exact scripts.)
