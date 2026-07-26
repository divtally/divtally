# v2 - Live CLI verification (`python -m bpc ... --json`)

- **Date:** 2026-07-26 (league **Allflame**, verified live from the API - not memory).
- **Pass:** driven as a skeptical PoE1 player - end-to-end LIVE run of the real CLI pipeline
  against a real current-league character, then every price/section/number cross-checked
  against live poe.ninja + pathofexile.com trade responses.
- **VERDICT: PASS.** No crash, no empty pricing, no nonsense numbers, no rate-limit violation.
- All evidence below is **[LIVE 2026-07-26]** (from actual API responses this session) unless
  tagged otherwise. Historical price "norms" I mention are **[NOT FROM SOURCE - recollection]**
  and used only as a sniff test, never as a verdict.

---

## 1. What was run

```
python -m bpc "https://poe.ninja/poe1/builds/allflame/character/Belirs-4934/RaiderFixEuServers" --json
```

The full pricing pass was driven through `engine.run_estimate(..., refresh=True)` (the exact
function `cli.py` calls) to force an all-live pull and capture the trade-search count; the
literal `python -m bpc ... --json` / `python -m bpc ...` commands were then run to confirm the
CLI entrypoint and the cache. Same engine, same `report.render_json`, so the output is identical.

### Character choice (and a real finding)
The doc's canonical character `example-0416/TestCharacter` is **live** and has a 6L
(Blunderbore) - but it carries **35 non-gem items (17 rare jewels)**, which exceeds the tool's
`SEARCH_BUDGET = 30` searches/run. That means run 1 would **skip** items and a "cached" re-run
would perform **new live searches** for the skipped ones (see finding F1). To get a clean,
budget-safe, fully-cacheable live run I scanned the live ladder (poe.ninja protobuf `/search`,
poe.ninja-only) and picked a leaner build that still hits every path:

**`Belirs-4934/RaiderFixEuServers`** - Pathfinder L100, **18 non-gem items + 6 gem groups**:
4 uniques, 6 rare gear, 2 rare jewels, 5 flasks, 1 normal, and **two linked items - Dendrobate
(6-link body) and Darkscorn (5-link bow)** - so the link filter is tested at both thresholds.

---

## 2. Live run result (headline)

| Metric | Value |
|---|---|
| Trade searches used (fresh run) | **23** (0 skipped; under the 30 budget) |
| Fresh run wall time | **302.5 s** (well-paced; ~13 s/search incl. fetches) |
| Items in JSON | 24 (18 priced-or-linked + 6 gem groups) |
| Priced / Unpriced | **15 priced / 9 unpriced** (all 9 = link-only, no fake number) |
| `divine_to_chaos` | **106.0** |
| `currency_unit` | `chaos` |
| Totals (chaos) | min 455.28 / median 485.75 / high 518.96 |
| Residue scan (rune/soul core/exalted/desecrated/charm/lineage/uncut/trade2/poe2) | **NONE** |

Distinct `method`s: `unique-name, rare-all, rare-all-base, magic-base, skill, none` - all
PoE1-native. Distinct `group`s: `equipment, flask, jewel, gem`. Distinct `category`s:
`unique, rare, magic, gem, normal`. No PoE2 sections/labels anywhere.

---

## 3. Skeptic checks - each PASSED

### 3.1 Every section makes sense for PoE1 - PASS
Report groups are Equipment / Flasks / Jewels / Gems. No "Runes / Soul Cores" section, no
charms, no exalted base unit. Gems render as a group price ("active + N supports") sourced from
poe.ninja - e.g. `Scourge Arrow ... active + 6 supports = 115c` (a 6-link skill in the 6L body).
JSON residue grep returned nothing.

### 3.2 Chaos/Divine numbers plausible + divine:chaos sane - PASS
- **`divine_to_chaos = 106.0` exactly matches the live poe.ninja Currency line**
  (`exchange/current/overview?type=Currency` -> divine `primaryValue = 106.0`, and
  `1/core.rates.divine = 105.99`). The classic `/api/data/currencyoverview` is **404** in current
  PoE1 (confirmed live), so the new economy endpoint is the authoritative source - and the tool
  reads it correctly.
- Divine display math correct: 260c -> 2.45d, totals 485.75c -> "4.6 div (486 chaos)".
- Spot currency magnitudes (live): exalted 0.80c, mirror 18150c, vaal 0.57c, annul 6.78c - all
  plausible PoE1 values; the tool normalises every listing to chaos via these rates.

### 3.3 5/6-link items carry link filters - PASS (decoded from the query JSON, no guessing)
Decoded the `?q=` payload embedded in each item's `trade_url`:
- **Dendrobate (max_link 6)** -> `filters.socket_filters.filters.links.min = 6` - PASS
- **Darkscorn (max_link 5)** -> `filters.socket_filters.filters.links.min = 5` - PASS

Below 5 links, no socket filter is emitted (correct - links don't move price under 5).

**Validated the filter is meaningful, not cosmetic** (spot-checks, live):
- `Dendrobate` with **no** link filter -> **493** online listings (cheapest 1c, all maxlink 1-3).
- `Dendrobate` with `links.min:6` -> **0** online listings.

So the tool correctly refuses to price a 6-link body as the 1c *unlinked* price; it shows the
link instead. This is exactly-right behaviour (mispricing a 6L as 1c would be a serious error).

### 3.4 Unpriceable items are link-only, never a fake number - PASS
All 9 unpriced items have `chaos = {min:null, median:null, high:null}` and a `trade_url`:
- 2 uniques (Dendrobate 6L, Darkscorn 5L): "no online listings" (genuinely 0 at that link count).
- 6 rares + jewels: "no listing matches requires N affixes (item may be uniquely rolled) - see
  trade_url" (default rare search requires ALL affixes; see F2).
- The only item with no link is a **Normal `Crude Bow`** (a weapon-swap white item) -> "normal
  item; not priced". No number, correctly not linked. Acceptable.

No misleading numbers anywhere.

### 3.5 Priced numbers verified against live listings
- **Death Rush, Amethyst Ring: 240/260/276c, LOW confidence (2 listings).** Looked high vs my
  recollection of this unique, so I spot-checked: live market = **3** online listings at
  `240 chaos, 240 chaos, 280 chaos` - denominated directly in chaos. So 240c is a **real listing**,
  not a conversion bug; the tool faithfully reports a thin fresh-league market and flags it LOW.
- **Null and Void: 1/1/2c (sample 19/378, high conf)** - cheap unique, matches a deep market. Good.
- **Miracle Crown (rare Lion Pelt): 5/15/15c, medium.** `trade_url` shows the documented rare
  methodology: 4 explicit affix stat-ids **+ `armour_filters.ev >= 619`** (85% of the item's
  evasion total). Correct.
- **Magic flasks: 0-1c each** over 1.7k-6k listings - correct (magic flasks are ~free).
- **Gems (poe.ninja economy, NOT trade): Scourge Arrow 115c, Frenzy 42c, Flame Dash 18c, ...**
  Frenzy 42c is a touch high vs recollection but is a real poe.ninja bucket price (level/quality/
  corrupt matched); sourced-and-flagged, not a trade number. Acceptable.

### 3.6 Cache makes a second run near-instant - PASS
| Run | Command | Time | Trade searches |
|---|---|---|---|
| Fresh (forced live) | `run_estimate(refresh=True)` | 302.5 s | 23 |
| 2nd run | `python -m bpc ... --json` | **0.59 s** | 0 |
| 3rd run (text) | `python -m bpc ...` | 1.39 s | **"(0 trade searches used.)"** |

Identical JSON on the cached run (totals 455.28/485.75/518.96, divine 106.0). The 0.59 s wall
time alone proves no rate-limited trade call ran; the text mode's own "(0 trade searches used.)"
confirms it. Cache is package-relative (`...\buildpricechecker-poe1\cache`), 30-min price TTL.

### 3.7 Rate-limit discipline - PASS (no violation observed)
The fresh run's 23 searches over 302 s were paced by the client with no error. My 3 follow-up
spot-check searches used a proper contact User-Agent, `>= 3 s` spacing, and logged every header:
`X-Rate-Limit-Ip = 5:10:60,15:60:300,30:300:1800,600:21600:3600`, state stayed at **1-3 hits**
per window (far under caps), **no 429, no Retry-After**. Budget spent: one full build run + 3
spot-check searches (+2 fetches). Within the allotted budget.

---

## 4. Findings (all MINOR - none block the pass)

- **F1 - Over-budget builds don't fully cache in one run.** With `SEARCH_BUDGET = 30`, a build
  with more than ~30 searchable non-gem items (e.g. the 35-item `example` char) skips the overflow
  in run 1 (`note: "skipped to stay within trade rate limits"`, no number, **no trade_url**), and
  a subsequent bare run performs *new* live searches for those skipped items (search_count resets
  per process; cache misses -> live search) until enough runs accumulate. So "near-instant 2nd run"
  and complete totals only strictly hold for builds within the budget (the common case, verified
  here at 18 items / 23 searches / 0 skips). Intentional ban-safety, but worth documenting; a
  skipped item having no `trade_url` (unlike every other unpriceable row) is a small inconsistency.
- **F2 - CLI default rare pricing is very strict (requires ALL affixes).** On this build 6 of 8
  rares were unpriced (link-only) because nothing matches every affix at once. This is documented
  behaviour ("genuinely uncommon rares are left unpriced with a link rather than a misleading
  number") and 2 rares did price, but the CLI has no affix picker (that lives in the web UI), so
  CLI totals can substantially exclude rares. The report does say so ("N items could not be
  priced ... totals exclude them"). Users wanting rare ballparks must use the web advanced picker.
- **F3 - Absolute plausibility is only as good as live data, and thin fresh-league markets read
  high.** Death Rush 260c / Frenzy 42c look high vs historical norms but were each verified as
  faithful reports (Death Rush = real 240c chaos listings; Frenzy = a real poe.ninja bucket). The
  tool surfaces this honestly via LOW/na confidence and links. No code action; a caution for
  whoever reads the numbers early in a league.

---

## 5. Reproduction

```
# from C:\scripts\buildpricechecker-poe1  (or set PYTHONPATH to it)
python -m bpc "https://poe.ninja/poe1/builds/allflame/character/Belirs-4934/RaiderFixEuServers" --json
python -m bpc "https://poe.ninja/poe1/builds/allflame/character/Belirs-4934/RaiderFixEuServers"        # 2nd run: cached, ~1s, 0 searches
```
(If the ladder has rolled and that character is gone, any live `poe.ninja/poe1/builds/.../character/...`
link works; prefer one with a 6-link and <= ~25 non-gem items so it fully caches in one run.)
