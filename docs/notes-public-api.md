# Notes — public serverless pricing function (`public/api/`)

Engineering notes for the self-contained Vercel Python project that powers the public site
(B-001 / D-0008). The consumer-facing schema is in `docs/public-contract.md`; this doc
records **what was built, what was vendored/adapted and why, how it was verified, and how to
deploy it**. Built 2026-07-26.

## 0. What it is / the invariant
`api/build` turns a poe.ninja PoE1 character URL (or a PoB code / paste link) into ONE JSON
document: build meta + every item row (category/group/host-gem structure mirroring the local
engine's `_result_dict`), **prices filled only from the poe.ninja economy** (gems incl.
supports, currency rates, uniques by name incl. unique flasks; jewels/variant-uniques
best-effort with a confidence note), and — for every rare/unpriced item — the prebuilt
browser `trade_url` **and** the exact trade-API `trade_query` JSON for a client-side
extension to execute.

**HARD INVARIANT (D-0008 / B-001):** nothing here ever calls pathofexile.com — not the trade
search/fetch/exchange API, not the `data/*` reference endpoints, not in any test. This is why
the architecture exists (trade calls happen only on user machines). It is enforced three ways:
1. **Structural** — the vendored `_http._guard_host` blocks any request whose host is (or ends
   with) `pathofexile.com`, at the transport layer.
2. **By omission** — no `TradeClient` is vendored; the trade-search methods of `pricing.py`
   (`_search_listings`, `price_unique`, `price_rare`, `price_magic`, `search`/`fetch`/
   `exchange`) are deliberately NOT ported. Only the *query-construction* and *poe.ninja*
   paths are.
3. **By bundling** — the two pieces of GGG trade **reference** data the query builder needs
   (`data/stats`, `data/items`) ship as static JSON in `api/_data/` and are read from disk.

Audited: the only executable `www.pathofexile.com` literal in `_lib/` is the browser
`/trade/search/` **link** builder (`querybuild._q_url`); everything else is comments. The
generated document contains zero `/api/trade` strings — only browser `/trade/search` links.

## 1. File map
```
public/api/
  build.py            Vercel function: POST/GET /api/build   (handler class `handler`)
  health.py           Vercel function: GET /api/health  (offline; validates the data bundle)
  requirements.txt    empty (pure stdlib — see §5)
  vercel.json         functions config: maxDuration + includeFiles for _data (see §6)
  _lib/               vendored, trade-free engine (underscore => not routed by Vercel)
    __init__.py
    _http.py          NEW  stdlib urllib GET/text + the pathofexile.com blocklist
    cache.py          ADAPTED  /tmp + in-process memo, swallows read-only-FS errors
    models.py         VERBATIM  Item / PriceTier / PriceResult / BuildMeta / CAT_*
    util.py           VERBATIM  strip_rich / mod_to_pattern / percentile / trim_outliers
    statmap.py        ADAPTED  StatMapper takes the stats-data dict (not a TradeClient)
    refdata.py        NEW  loads bundled trade_stats/trade_items; builds item_types()
    poeninja.py       ADAPTED  urllib client + normalize (verbatim) + PoeNinjaEconomy
                               gains unique-overview pricing + current_challenge_league()
    pob.py            VERBATIM  PoB decode/parse (types come from refdata)
    currency.py       ADAPTED  economy-only; trade `exchange` fallback DELETED
    querybuild.py     NEW  PublicPricer: the query-building slice of pricing.py + poe.ninja
                          gem/unique pricing; every row gets trade_url + trade_query
    engine.py         ADAPTED  input routing + trade-free league resolution + wiring
    response.py       NEW  shapes (meta,results,pricer,league) -> the contract document
  _data/
    trade_stats.json  bundled /api/trade/data/stats  (SLIMMED, see §4)
    trade_items.json  bundled /api/trade/data/items  (SLIMMED, see §4)
```

## 2. The trade-free boundary (what was reused vs cut from `bpc/pricing.py`)
**Reused (pure query construction — no search):** `_links_filter`, `_q_url` (→ browser
link), `_gem_search_url`/`_gem_query`, `resolve_type`, `_rare_scopes`, `affix_options`,
`_rare_query`, `_rare_default_filters`, `_unique_value_filters`, `_build_stat_groups`,
`res_contributions`, `_is_res_affix`/`_affix_tier`/`_is_skill_level_mod`, and `price_skill`
(poe.ninja-only). Copied faithfully with `self.client.league` → `self.league`.

**Cut (they call trade):** `_search_listings`/`_search_collect`, `price_unique`,
`price_rare`, `price_magic`, `price_rare_custom`, `price_unique_custom`, `currency_image`
(used trade `static_data` — replaced with poe.ninja currency images), `load_item_types`
(used trade `data/items` — replaced by `refdata.item_types()`), and the whole `TradeClient`
+ `CurrencyConverter._lookup` trade fallback.

**Replaced with poe.ninja / new code:**
- Uniques: `PublicPricer.price_unique_ninja` prices by exact name via the merged poe.ninja
  unique overviews (see §3). (The local build searched trade — forbidden here.)
- Rares/magic: `price_rare_unpriced` / `price_magic_unpriced` build the exact default query
  (identical to what the local engine would have searched) and attach it as `trade_query` +
  `trade_url`; no number.
- League: `engine.resolve_league` uses an override → the poe.ninja league → poe.ninja's
  current challenge league. (The local `resolve_trade_league` hit the trade `data/leagues`
  endpoint.)

## 3. New piece — poe.ninja unique-overview pricing
`PoeNinjaEconomy` gained `_load_uniques()` + `unique_price()`. It fetches and merges the five
variant-bearing unique overviews (`/poe1/api/economy/stash/current/item/overview?type=
Unique{Weapon,Armour,Accessory,Flask,Jewel}`) into one `name_lc → [line,…]` index. Line shape
(live-verified 2026-07-26): `{name, baseType, variant, chaosValue, divineValue, listingCount,
count, …}`. Matching (best-effort, honest):
- **1 line** → point estimate; confidence from `listingCount`.
- **several lines, one clear match** → that variant (its `variant` tokens are ≥60% contained
  in the item's mod text, and it's the sole strong match — e.g. Mageblood "5 Flasks",
  Impresence "Lightning"); `method:"unique-ninja-variant"`.
- **several lines, ambiguous** → a **range** (`chaos.min/median/high` across the variant
  values), `method:"unique-ninja-range"`, always `confidence:"low"`, with a note + the
  `trade_url` — never a fabricated point estimate (honours the "no misleading number"
  guardrail). This covers Watcher's Eye / other multi-mod jewels we can't pin exactly.
- **name not listed** → `unique-unpriced` (no number; `trade_query` provided).
Note: poe.ninja now lists "Foulborn …"-prefixed league variants; matching is **exact name**
(not substring), so a plain "Mageblood" never mis-binds to "Foulborn Mageblood".

## 4. Bundled reference data (slimmed, provenance recorded)
The query builder needs two GGG trade reference blobs. They are shipped static and read from
disk (never fetched):
- `trade_stats.json` — the stat dictionary for `StatMapper`. Slimmed from the full
  `research/data/trade_stats.json` (3.04 MB → 1.89 MB) to the **9 groups StatMapper consults**
  (Pseudo, Explicit, Implicit, Fractured, Enchant, Scourge, Crafted, Veiled, Crucible) and the
  **3 fields it reads** per entry (`id`, `text`, `type`). The verifier asserts the slim file
  produces a **byte-identical** `StatMapper._map` and `_groups` vs the full file — the dropped
  groups (Imbued/Mercenary/Delve/Ultimatum/Sanctum) are never stored, so this is provably
  lossless.
- `trade_items.json` — base types per category for `resolve_type` + PoB parsing. Slimmed
  (665 KB → 164 KB) to `label` + entries' `type` (all `load_item_types` reads).
**Regeneration** (when a league changes the stat dictionary — rare; stat ids are stable):
re-run the two `json`-slimming steps from `research/data/trade_{stats,items}.json` into
`public/api/_data/`. The one-off script lives in this session's history; the transform is:
keep the 9 stat groups + `{id,text,type}`; keep items `{label, entries:[{type}]}`.

Currency icons (`chaos_img`/`divine_img`) come from the poe.ninja Currency overview `items[]`
at runtime, so the trade `data/static` blob is **not** bundled.

## 5. Pure-stdlib (no `requests`)
The vendored HTTP layer uses `urllib` (stdlib). This removes the only third-party dependency,
so `requirements.txt` is empty, there is no pip-install step (faster cold starts), and nothing
to pin/audit. `poeninja`, `engine`, and the PoB-link fetch all go through `_http`.

## 6. Deployment (Vercel Hobby / free tier)
- **Runtime:** Vercel's Python runtime auto-detects `api/*.py` that define a
  `BaseHTTPRequestHandler` subclass named `handler`. `_lib`/`_data` are underscore-prefixed →
  not treated as routes; `_lib` is import-traced into each function bundle automatically.
- **`vercel.json` + `requirements.txt` placement (ACTION REQUIRED):** Vercel reads
  `vercel.json` only from the project **Root Directory**. Set the Vercel project's Root
  Directory to the repo's **`public/`** folder (so functions resolve as `api/build.py`), and
  place `vercel.json` at `public/vercel.json`. Because file ownership for this task was scoped
  to `public/api/**`, the file was written to **`public/api/vercel.json`** — **copy it to
  `public/vercel.json`** before deploy (same for `requirements.txt` if Vercel doesn't pick up
  the `api/`-level one). The globs inside (`api/build.py`, `includeFiles: "api/_data/**"`) are
  already written relative to root = `public/`.
- **`includeFiles`** ships `api/_data/*.json` (data files aren't import-traced). `refdata.py`
  also probes several candidate dirs so it still finds the data if the bundle layout differs.
- **maxDuration:** 30 s for `build` (a cold call fetches the ~4.6 MB SkillGem overview + five
  unique overviews from poe.ninja), 5 s for `health`.
- **Caching:** cross-request caching is the CDN's job (`s-maxage=600` + SWR) plus the future
  Workers-KV layer (B-001) — not `_lib/cache.py`, which is only an in-process/`/tmp`
  best-effort memo that never crashes on the read-only serverless FS.
- **CORS:** `*` on every response (public data), set in the handlers.

## 7. Verification (local, no Vercel account)
Runner: `scratchpad/run_public_api_tests.py` (imports the vendored lib + the real Vercel
`handler`). **All checks passed.**
- **Phase A (offline, hermetic):** `poeninja.get_json` monkeypatched to serve `research/data`
  fixtures; exercises the real `normalize → PublicPricer.price_build → response.build_response`
  path. Asserts: slim-vs-full StatMapper equality; `unique_price` name/variant/range matching
  (crafted fixture); full contract validation on `char_poe1.json` **and**
  `char_poe1_unicode.json` (41 / 28 items); gems priced from poe.ninja; the GRANTED gem
  (Herald of the Hive) excluded from its total; strict-JSON (no NaN/Inf); a PoB-code import
  (encoded `pob_sample.xml`, 64 items) with a 5/6-link carrying a `links` filter in its
  `trade_query`; the `bad_input` error shape; `total_chaos == sum(priced gems)`.
- **Phase B (live, one character, via the real handler on `127.0.0.1:8951`):** GET
  `/api/build?url=<live poe.ninja char>` → **HTTP 200 in ~1.6–2.2 s**; headers `CORS: *` and
  `Cache-Control: public, s-maxage=600, stale-while-revalidate=86400`; **41 items, 22 priced /
  19 unpriced**, `totals.chaos.median ≈ 31,986` (≈270 div), `divine_to_chaos = 118.3`. Live
  asserts a real unique priced by name (Maloney's Mechanism = 14 c, conf high, 319 listings)
  and gems priced (transfigured "Ethereal Knives of the Massacre", total 2971.9 c). Verified
  the whole document has **no** `/api/trade` or `pathofexile.com/api` strings — only 58
  browser `/trade/search` links. Health check green + `calls_pathofexile_com: false`.
- Handful of poe.ninja calls total; **zero** pathofexile.com calls. The **cache seeder was NOT
  run** (it drives the local app which performs trade searches) — out of scope here.
- Rerun offline-only with `BPC_SKIP_LIVE=1`. Override the live character with
  `BPC_LIVE_CHAR_URL` if the default has rotated out of poe.ninja's snapshot.

## 8. Known limitations / best-effort (flag to consumers)
- **Variant uniques** (Watcher's Eye, multi-mod jewels): often reported as a `range` with
  `confidence:"low"` — the exact roll can't be pinned from poe.ninja alone. The `trade_query`
  is exact; the extension can price it precisely client-side.
- **League mapping** assumes the poe.ninja league display name == the trade league id (true
  for challenge leagues; verified vs the trade `data/leagues` fixture). Override via `league`
  if a `trade_url` 404s.
- **Rare cluster jewels / rares generally** are never server-priced — by design.
- **totals** cover only poe.ninja-priced items (gems + uniques); rares add to cost only once
  priced client-side. The site should surface `unpriced_items` so the total reads as a floor.
- Cross-invocation cache relies on the CDN/KV, not the function — a cold instance re-fetches
  poe.ninja. `s-maxage` keeps this cheap.
