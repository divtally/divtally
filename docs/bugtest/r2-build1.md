# R2 / Build 1 - Browser UI hands-free scan audit

**Round:** 2 (browser UI via Playwright + the real extension) of the D-0020 five-round bug campaign.
**Build:** `qwartus-3381 / qwartus_niceboat` (Occultist L100, Allflame) -
`https://poe.ninja/poe1/builds/allflame/character/qwartus-3381/qwartus_niceboat`
**Under test:** LIVE site `https://divtally.com/?v=r2-1` + unpacked extension
`C:\scripts\buildpricechecker-poe1\extension` (**v1.2.1**), loaded into a real Chromium via
Playwright persistent context (headless:false, 1280x900).
**Date:** 2026-07-28. **Auditor scope:** the ONLY pathofexile.com traffic is what the extension
itself performed under its own limiter (the product under test). **1 full scan, 0 re-scans** used
(re-scan budget was 2; not needed). No repo files touched except this report.

Every number below is **source-derived** (a live `bpc.scanStatus()` / `bpc.totals()` reading, the
rendered DOM, or the actual extension/site source) unless tagged `[DERIVED]` / `[INFERRED]`.

Driver + raw capture (scratchpad, not in repo): `r2driver.mjs`, `r2_results.json`,
`r2_progress.jsonl`. Profile: `...\scratchpad\r2profile1`.

---

## 0. D-0020 HARD-CRITERIA VERDICT (read first)

| Hard criterion (D-0020 amendment) | Result |
|---|---|
| **(a) Scan-duration audit** - total wall-clock + per-item timings | **PRODUCED** - `totalMs = 63 827 ms` (63.8 s); per-row `ms` for all 12 rows (see §1). One instrumentation caveat: Finding R2-2. |
| **(b) Hands-free fruition** - scans to completion, zero intervention, no row stuck non-terminal | **PASS** - scan auto-started at **+5.0 s with zero clicks**; all **12/12 rows reached a terminal stage**; **0 stuck, 0 error**; 0 pageerrors, 0 console errors. |

The build reached full fruition hands-free. **No blocker, no major.** All findings are minor
(UI-copy truthfulness, timing-instrument fidelity, and a scan-budget observation) plus by-design
consequences of locked decisions (D-0015 strict default, D-0018 swap), flagged with provenance.

**Hands-free chain observed** (no intervention after one `Enter`): page load -> content script
`hello` -> badge lit **"extension active - v1.2.1"** (bridge active, v1.2.1) -> URL submitted ->
12 rows loaded at +5.0 s -> `maybeAutoStart()` fired `bpc.autoscan()` automatically (defaults:
auto-scan-on-load ON, pick-affixes OFF) -> serial priced scan -> `scanEnd()` at +70.2 s. Every
default was already correct with an untouched profile (`bpc_autoscan_auto=null` -> ON,
`bpc_pick_affixes=null` -> OFF, `bpc_include_swap=null` -> OFF, `tier=min`) - **no clicks were
needed to set up the run.**

---

## 1. THE TIMING TABLE

**Total scan wall-clock:** `totalMs = 63 827 ms` (63.8 s), `scanStatus().startedAt -> finishedAt`.
Wall-clock from the single `Enter` to `active=false` = **70.2 s** (includes ~5.0 s build fetch +
board build before the scan starts).
**Rows scanned:** 12 (9 rares + 3 magic flasks). Uniques/gems/normals are economy-priced at load
and are not part of the extension scan.

### 1a. Per-row time, sorted DESC (raw `scanStatus().status[k].ms`)

| # | Item | Cat | Chunk-pos | Raw ms | Incremental ms `[DERIVED]` | Terminal stage | Price applied |
|---|------|-----|-----------|-------:|-----------:|----------------|---------------|
| 1 | Cataclysm Spark, Cobalt Jewel | rare | 4-3 | 34 781 | 3 336 | nobuyout (0 found) | - (unpriced, link) |
| 2 | Investigator's Quartz Flask of the Mockingbird | magic | 4-2 | 31 445 | **28 030** | done | 0.0654c (tf 10000) |
| 3 | Panicked Divine Life Flask of Sealing | magic | 3-3 | 11 044 | 3 992 | done | 0.0654c (tf 10000) |
| 4 | Grim Coat, Twilight Regalia | rare | 2-3 | 10 592 | 3 479 | nobuyout (0 found) | - (unpriced, link) |
| 5 | Brood Slippers, Warlock Boots | rare | 1-3 | 7 360 | 3 682 | nobuyout (0 found) | - (unpriced, link) |
| 6 | Tempest Spell, Titanium Spirit Shield | rare | 2-2 | 7 113 | 3 453 | nobuyout (0 found) | - (unpriced, link) |
| 7 | Storm Thirst, Convoking Wand | rare | 3-2 | 7 052 | 3 407 | nobuyout (0 found) | - (unpriced, link) |
| 8 | Woe Ward, Lich's Circlet | rare | 1-2 | 3 678 | 3 427 | nobuyout (0 found) | - (unpriced, link) |
| 9 | Entropy Idol, Jade Amulet | rare | 2-1 | 3 660 | 3 660 | done | **124.8c** (tf 1) |
| 10 | Vortex Knuckle, Amethyst Ring | rare | 3-1 | 3 645 | 3 645 | nobuyout (0 found) | - (unpriced, link) |
| 11 | Endless Quicksilver Flask of the Goldfish | magic | 4-1 | 3 415 | 3 415 | done | 0.0654c (tf 10000) |
| 12 | Entropy Gyre, Amethyst Ring | rare | 1-1 | 251 | **251** | nobuyout (0 found) | - (unpriced, link) |

"Chunk-pos" = `chunk-position`; core.js sends the scan in **chunks of 3** (CHUNK=3, 4 chunks),
sequentially. **Incremental ms** = the successive intra-chunk difference (position 1 = raw;
position 2/3 = raw minus the prior position's raw) - see Finding R2-2 for why this is the honest
per-item figure and the raw column is not.

### 1b. Time share: searching vs waiting `[DERIVED]`

The extension paces evenly across the tightest search window (D-0018). Search spacing is
**source-derived** from `background.js`: `DEFAULT_RULES.search[0] = [5,10]` ->
`spacing = ceil(10000 / effectiveCap(5)) = ceil(10000/3) = 3 334 ms` between searches.

- **Cleanest single measurement:** the very first search (Entropy Gyre) had no prior request to
  pace against and returned in **251 ms** - i.e. a real zero-match search round-trip is ~0.25 s of
  actual network. Every per-row figure above ~0.25 s is dominated by limiter waiting, not HTTP.
- **Rate-limiter waiting (pacing):** ~`11 x 3 334 ms = 36.7 s` minimum just to space the 12
  searches (the first is free). Plus the short windows (5/10 s, 15/60 s) begin biting by search
  ~10-12: chunk 4 shows the blow-up (row #2 incremental **28 030 ms** = the 10 000-result flask
  fetch **plus** a window back-off).
- **Estimated split of the 63.8 s:** **~37-45 s waiting (rate-limiter pacing + window back-off,
  ~58-70%)** vs **~19-27 s active HTTP (12 search POSTs + 4 fetch GETs, ~30-42%)**. `[DERIVED]` -
  exact per-stage attribution is blocked by Finding R2-2 (no per-stage timers) and the 5 s poll
  granularity.

**Takeaway:** the scan is **rate-limiter-bound, not compute- or parse-bound**. The only genuine
per-item cost outlier is the **Investigator's Quartz Flask (~28 s of real work)** - a magic flask
whose generic search matched the 10 000-result cap and whose fetch + back-off stalled the tail of
the scan (see Finding R2-3). Its raw 31 445 ms and Cataclysm's raw 34 781 ms are the *cumulative*
artifact of Finding R2-2, not that item's own cost.

---

## 2. Findings summary

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| R2-1 | minor | **Zero-match rares mislabelled** "no buyout among 0 listings - 0 fetched, 0 without a buyout" (self-contradictory: describes a set of zero). Distinct from a real total>0 no-buyout. | 8/9 rares: `total_found=0`, stage `nobuyout`, chip text as quoted; core.js foldBatch collapses `total=0` into the "listings exist but none had a buyout" branch |
| R2-2 | minor | **Per-row `ms` is chunk-cumulative, not per-item** - t0 is stamped at chunk dispatch ("scanning" set on all 3 at once), so later-in-chunk rows inherit predecessors' search+fetch+wait. The D-0020 "per-item timings" instrument overstates non-first rows. | Cataclysm raw 34 781 ms (nobuyout, a single ~0.25 s search) vs incremental 3 336 ms; core.js:739 stamps t0 on first non-"queued" stage, core.js:858 sets whole chunk to "scanning" |
| R2-3 | minor | **Magic flasks are live-scanned for ~0.065c** - 3 of 12 searches spent on ~free flasks; the Investigator flask (10 000-result generic match) was the scan's tail bottleneck (~28 s). | rows 2/3/11: magic, `tf=10000`, tier `0.0654c`, conf `high`; consider floor-pricing magic flasks from economy instead |
| R2-4 | obs `[D-0015]` | **Hands-free autoscan priced only 1 of 9 rares** (8 = zero matches) - the strict all-affix default. **By design** (D-0015 owner veto), surfaced so the real-world yield is on record. | 8x `tf=0`; total (1938c) is ~99% uniques+gems; rares added 124.8c + ~0.2c flasks |
| R2-5 | obs `[D-0015]` | **min/median/high selector is inert on this build** - no INCLUDED priced item has a tier spread, so MIN->HIGH moves nothing. The control fired correctly (state -> high, repaint ran); there is simply nothing to spread. | Entropy Idol tf=1 -> 124.8/124.8/124.8; flasks uniform floor -> 0.0654 x3; totals min==median==high at every poll |

No **blocker** (fruition reached, nothing stuck/errored), no **major** (no crash, no wrong or
misleading *number*; the unpriced rares correctly show no number + a trade link).

---

## 3. UI-truthfulness audit (the R2 lens)

All PASS except where a finding is cited.

- **Extension-active badge:** lit within ~2.5 s of load; text **"extension active - v1.2.1"**;
  `state.bridge = {active:true, version:"1.2.1"}`. PASS.
- **Defaults on an untouched profile:** auto-scan-on-load **ON** (`bpc_autoscan_auto=null`),
  pick-affixes **OFF** (`bpc_pick_affixes=null`), weapon-swap **excluded** (`bpc_include_swap=null`),
  tier **min**. PASS - matches the spec; no clicks needed to set up.
- **Progress bar counts monotonic:** `scanning N/12` never regressed; `done` count non-decreasing.
  `monotonic = {ok:true, violations:[]}`. PASS.
- **Chips match `scanStatus` stages:** every rendered chip is derived from and agrees with the
  row's `status[k].stage` (queued -> scanning/searching/fetching/waiting -> done/nobuyout). The
  only issue is the *copy* of the zero-match chip (Finding R2-1), not a stage mismatch. PASS
  (with R2-1).
- **Totals climb as prices land:** monotonic non-decreasing -
  `0 -> 1813.1c (+5 s, uniques+gems) -> 1937.9c (+25 s) -> 1937.97c (+35 s) -> 1938.10c (+70 s)`.
  PASS. (The rare/flask contribution is tiny - see R2-4 - but the climb is real and never dips.)
- **Tier flip MIN -> HIGH changes rares + totals:** **did NOT change** (totals + every rare row
  identical). Root cause is data, not code (Finding R2-5): no included item has a spread. The
  control itself works (`state.tier` -> "high", `on('control')` repaint ran). **Could not be
  positively exercised on this build** - defer a spread-bearing case to a later build/round.
- **Variant rows show labels:** **N/A** - this build has **0 variant/timeless uniques**
  (`.mr-vtag` count = 0), consistent with the API capture. The label path could not be exercised
  here; not a defect.
- **Swap items absent from the rares list (default):** PASS - `Maloney's Mechanism, Ornate Quiver`
  (Off-hand swap) and `Bone Bow` (Weapon swap) are **excluded from totals** (`included=20`) and
  absent from the manual list; they render on the board in the swap slots (`slot-oswap` /
  `slot-wswap`) only.
- **Weapon-swap toggle re-includes:** PASS - checking "weapon swap" -> `includeSwap()=true`,
  totals `min 1938.10c -> 1949.10c` (+11c = Maloney's economy value), `included 20 -> 21`. It did
  **not** trigger a runaway re-scan (`scanActive` stayed false - the `autoFired` per-build guard
  held). Bone Bow is a normal (unpriced) so it adds no total, correctly.

---

## 4. Detailed findings

### R2-1 (minor) - zero-match rares are mislabelled "no buyout among 0 listings"
8 of 9 rares resolved to `total_found = 0` (the strict all-affix default returned **no matching
listings at all**). The extension correctly returns `{total:0, amount:null}` (`background.js`
priceQuery, `!ids.length` branch), and core.js routes `amount==null` to stage `nobuyout` with the
note *"listings exist but none had a buyout price"*. That note - and the rendered chip
**"WARNING no buyout among 0 listings - 0 fetched, 0 without a buyout"** - are **false when
`total=0`**: there were zero listings, so "no buyout among them" and "0 without a buyout" describe
the empty set. This directly hits the D-0020 UI-truthfulness criterion and the owner's standing
"no buyout everywhere" sensitivity (D-0012).
**Fix hint:** in `foldBatch`, branch on `res.total === 0` -> a distinct stage/copy, e.g.
*"no listings match all N affixes (exact-affix search)"* with the open-search link, separate from
the genuine `total>0 & amount==null` no-buyout case. Keeps the honest "0 matches" story the strict
default (D-0015) is supposed to tell.

### R2-2 (minor) - per-row `ms` is chunk-cumulative, not per-item
`scanSet` stamps `s.t0` on a row's first non-`queued` stage (core.js:739). But core.js sends the
scan in chunks of 3 and immediately sets **all three** chunk keys to `"scanning"` on dispatch
(core.js:858) before the extension prices them **serially**. So t0 for positions 2 and 3 starts at
chunk dispatch, and their `ms` (terminal - t0) includes the full search+fetch+rate-limit time of
the rows ahead of them in the chunk. Concretely: Cataclysm Spark's raw **34 781 ms** is a single
~0.25 s zero-match search that merely happened to be last in its chunk; its honest per-item cost is
the **3 336 ms** incremental. The D-0020 amendment sells this instrument as "per-item timings" - it
is really "time-from-chunk-dispatch-to-terminal." **Fix hint:** stamp t0 on the row's own first
`"searching"` progress event (per-item, emitted by `background.js` `priceQuery`), or record
per-stage durations; then the raw column becomes the honest per-item figure and §1a needs no
"incremental" derivation.

### R2-3 (minor) - magic flasks burn scan budget for ~0.065c
The 3 magic flasks were live-scanned (25% of the scan's search budget). Each matched the
10 000-result cap on a generic search and priced to a uniform **0.0654c** floor at `high`
confidence. The Investigator's Quartz Flask fetch + back-off was the tail bottleneck of the whole
scan (~28 s of real work, Finding R2-2 aside). Flasks are near-worthless and their generic match
ignores any suffix/enchant value, so the live scan buys neither accuracy nor speed here.
**Fix hint (design, defer to owner):** floor-price magic flasks from the economy (or skip them from
autoscan) instead of spending limiter budget; if kept, constrain the query so the number means
something. Low impact on totals either way.

### R2-4 / R2-5 (observations, by-design under D-0015) - strict default -> mostly no-match, inert tiers
Both are downstream of the **locked D-0015 decision** ("if the user doesn't manually exclude an
affix we should not be doing that for them"; autoscan stays strict-all-affix). On a real L100
build, hands-free autoscan priced **1 of 9 rares** (Entropy Idol, the one with a single matching
listing) and left 8 as honest "no match". Because the only priced rares are a single-listing item
(tf=1) and three floor-priced flasks, **no included item has a min!=high spread**, so the
min/median/high selector has nothing to move. These are **not bugs** - they are the documented
tradeoff working exactly as the owner specified - but they mean this particular build cannot
positively demonstrate the tier-distribution feature (D-0016 item 4). Recommend a later round use a
build (or the per-rare affix picker) that yields a multi-listing rare so the spread is exercised
end-to-end in the browser.

---

## 5. Console / pageerror capture

- **`pageerror` count: 0.**
- **`console.error` / `console.warning` count: 0.**
- No failed-bridge fallback, no timeout chunks, no 429 surfaced to the page (the limiter absorbed
  all pacing internally; no row reached stage `error`).

Clean. The extension bridge, the chunked scan, the cache POSTs (4 priced rows -> community cache),
and the tier/swap controls all ran without a single page-side error.

---

## 6. Method / reproduction

1. Playwright `chromium.launchPersistentContext(r2profile1, {headless:false, viewport:1280x900,
   args:['--disable-extensions-except=<ext>','--load-extension=<ext>','--no-first-run',
   '--no-default-browser-check']})` - extension `v1.2.1` from `C:\scripts\buildpricechecker-poe1\extension`.
2. `goto https://divtally.com/?v=r2-1`; confirm `#bridgeBadge.on` + defaults; **no clicks**.
3. `fill('#url', <build>)` + `press('#url','Enter')` - the single sanctioned interaction.
4. Poll `bpc.scanStatus()` every 5 s (cap 10 min) until `active===false` && every row terminal.
5. Post-scan audit: click `#btSeg [data-tier=high]`; read variant tags; read swap-excluded list;
   `check('#swapInc')` and re-read totals.
6. All readings dumped to `r2_results.json`; browser closed in a `finally`.

**Trade footprint:** exactly one hands-free scan (12 searches + 4 fetches, all by the extension
under its own limiter). 0 re-scans. No direct pathofexile.com calls by the auditor.
