# R2 / Build 2 - Browser UI hands-free scan audit

**Round:** 2 (browser UI via Playwright + the real extension) of the D-0020 five-round bug campaign.
**Build:** `Sergohero-2699 / SergoheroGaz` (Deadeye L100, Allflame) -
`https://poe.ninja/poe1/builds/allflame/character/Sergohero-2699/SergoheroGaz`
**Under test:** LIVE site `https://divtally.com/?v=r2-2` + unpacked extension
`C:\scripts\buildpricechecker-poe1\extension` (**v1.2.1**), loaded into a real Chromium via
Playwright persistent context (headless:false, 1280x900).
**Date:** 2026-07-28. **Auditor scope:** the ONLY pathofexile.com traffic is what the extension
itself performed under its own limiter (the product under test). **1 full scan, 0 re-scans** used
(re-scan budget was 2; not needed). No repo files touched except this report.

Every number below is **source-derived** (a live `bpc.scanStatus()` / `bpc.totals()` reading, the
rendered DOM, the post-scan screenshot, or the actual extension/site source) unless tagged
`[DERIVED]` / `[INFERRED]`.

Driver + raw capture (scratchpad, not in repo): `r2driver2.mjs`, `r2_results2.json`,
`r2_progress2.jsonl`, `r2_build2_final.png`. Profile: `...\scratchpad\r2profile2`.

**Why this build matters:** it exercises three things Build 1 (qwartus) structurally could not - a
**timeless jewel** (Lethal Pride, seed 13032), a **foil/relic unique** (Nimis, the D-0020 R1 fix),
and a **rare with a real multi-listing price spread** (Kraken Star, 14 listings) that positively
drives the MIN->HIGH tier selector. Plus **two weapon/off-hand swaps** and **alch/divine currency
conversion**. All passed hands-free.

---

## 0. D-0020 HARD-CRITERIA VERDICT (read first)

| Hard criterion (D-0020 amendment) | Result |
|---|---|
| **(a) Scan-duration audit** - total wall-clock + per-item timings | **PRODUCED** - `totalMs = 28 582 ms` (28.6 s); per-row `ms` for all 9 rows (see §1). Same instrumentation caveat as Build 1: Finding R2b-2. |
| **(b) Hands-free fruition** - scans to completion, zero intervention, no row stuck non-terminal | **PASS** - scan auto-started at **+5.0 s with zero clicks**; all **9/9 rows reached a terminal stage**; **0 stuck, 0 error**; 0 pageerrors, 0 console errors. The timeless jewel priced itself hands-free (exact-seed search). |

The build reached full fruition hands-free. **No blocker, no major.** Findings are minor
(two confirmed-across-builds instrumentation/copy issues, one flask-budget note) plus by-design
consequences of locked decisions, all flagged with provenance. This round adds **seven positive
validations** (§4B) of features Build 1 could not reach.

**Hands-free chain observed** (no intervention after one `Enter`): page load -> content script
`hello` -> badge lit **"extension active - v1.2.1"** -> URL submitted -> 9 rows loaded at +5.0 s ->
`maybeAutoStart()` fired `bpc.autoscan()` automatically (defaults: auto-scan-on-load ON,
pick-affixes OFF, swap OFF) -> serial priced scan (incl. the variant/timeless row via
`needsScan`) -> `scanEnd()` at +35.1 s. Every default was already correct with an untouched
profile (`bpc_autoscan_auto=null` -> ON, `bpc_pick_affixes=null` -> OFF, `bpc_include_swap=null` ->
OFF, `tier=min`, `bpc_status_v2` -> "Instant Buyout and In Person" per D-0017) - **no clicks were
needed to set up the run.**

---

## 1. THE TIMING TABLE

**Total scan wall-clock:** `totalMs = 28 582 ms` (28.6 s), `scanStatus().startedAt -> finishedAt`.
Wall-clock from the single `Enter` to `active=false` = **35.1 s** (includes ~5.0 s build fetch +
board build before the scan starts).
**Rows scanned:** 9 = **6 rares** (all jewels) + **2 magic flasks** + **1 variant/timeless unique**
(Lethal Pride). The other 20 items (14 plain uniques + 5 gems + Maloney's swap unique) are
economy-priced at load and are **not** part of the extension scan. The weapon-swap magic bow is
excluded by default (D-0018), so 9 rows scan, not 10.

### 1a. Per-row time, sorted DESC (raw `scanStatus().status[k].ms`)

| # | Item | Cat | Chunk-pos | Raw ms | Incremental ms `[DERIVED]` | Terminal stage | Price applied |
|---|------|-----|-----------|-------:|-----------:|----------------|---------------|
| 1 | Lethal Pride, Timeless Jewel | unique | 2-3 | 10 715 | 3 659 | done | **124.8c** (1 div, exact seed 13032, tf 1) |
| 2 | Cataclysm Ornament, Medium Cluster Jewel | rare | 3-3 | 10 692 | 3 745 | done | 25c (tf 1) |
| 3 | Grim Arbiter, Searching Eye Jewel | rare | 1-3 | 7 146 | 3 339 | nobuyout (0 found) | - (unpriced, link) |
| 4 | Foul Sphere, Searching Eye Jewel | rare | 2-2 | 7 056 | 3 414 | nobuyout (0 found) | - (unpriced, link) |
| 5 | Pandemonium Shine, Medium Cluster Jewel | rare | 3-2 | 6 947 | 3 423 | nobuyout (0 found) | - (unpriced, link) |
| 6 | Abecedarian's Amethyst Flask of Incision | magic | 1-2 | 3 807 | 3 384 | done | 0.07c (1 alch, tf 10000) |
| 7 | Kraken Star, Crimson Jewel | rare | 2-1 | 3 642 | 3 642 | done | **1c..7c** (14 listings, real spread) |
| 8 | Hypnotic Ruin, Large Cluster Jewel | rare | 3-1 | 3 524 | 3 524 | done | 873.6c (7 div, tf 1, conf low) |
| 9 | Dolomite Divine Life Flask of Allaying | magic | 1-1 | 423 | **423** | done | 0.07c (1 alch, tf 10000) |

"Chunk-pos" = `chunk-position`; core.js sends the scan in **chunks of 3** (`CHUNK=3`, 3 chunks),
sequentially. **Incremental ms** = the successive intra-chunk difference (position 1 = raw;
position 2/3 = raw minus the prior position's raw) - see Finding R2b-2 for why this is the honest
per-item figure and the raw column is not.

### 1b. Time share: searching vs waiting `[DERIVED]`

The extension paces evenly across the tightest search window (D-0018). Search spacing is
**source-derived** from `background.js`: `DEFAULT_RULES.search[0] = [5,10]` ->
`spacing = ceil(10000 / effectiveCap(5)) = ceil(10000/3) = 3 334 ms` between searches.

- **Cleanest single measurement:** the very first search (Dolomite flask) had no prior request to
  pace against and returned in **423 ms** - a real search+fetch round-trip is well under half a
  second. Every per-row figure above ~0.4 s is dominated by limiter pacing, not HTTP.
- **The scan is pacing-bound at the floor:** 9 searches at ~3.33 s spacing = ~26.7 s minimum
  (first is free -> 8 gaps x 3.33 s = 26.7 s). Observed total 28.6 s. That ~1.9 s of headroom is
  the 6 fetch GETs (interleaved at the cheap ~0.5 s fetch spacing). **This scan hit NO window
  back-off spike** - a notable contrast with Build 1 (whose tail flask fetch cost ~28 s of
  back-off). The two 10 000-result flasks here were positions 1 and 2 (windows not yet saturated),
  so their fetches were cheap. Order matters.
- **Estimated split of the 28.6 s:** **~25-27 s waiting (limiter pacing, ~88-92%)** vs **~2-4 s
  active HTTP (9 search POSTs + 6 fetch GETs, ~8-12%)**. `[DERIVED]` - exact per-stage attribution
  is blocked by Finding R2b-2 (no per-stage timers) and the 5 s poll granularity.

**Takeaway:** the scan is **rate-limiter-bound, not compute- or parse-bound**, and this run rode
the pacing floor cleanly with no back-off spike. The three tf=0 rares (Grim Arbiter, Foul Sphere,
Pandemonium) each cost a single ~0.25 s zero-match search; their raw ms (7 146 / 7 056 / 6 947) is
the *cumulative* artifact of Finding R2b-2, not their own cost (honest cost ~3.3-3.4 s each, which
is itself almost all pacing wait).

---

## 2. Findings summary

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| R2b-1 | minor | **Zero-match rares mislabelled** "no buyout among 0 listings - 0 fetched, 0 without a buyout" + tooltip "listings exist but none had a buyout price" - self-contradictory when `total_found=0` (describes an empty set). **Confirms Build 1 R2-1 on a second build -> class bug, not build-specific.** | 3/6 rares: `total_found=0`, stage `nobuyout`, `detail={total:0,fetched:0,nulls:0}`; chip text visible in screenshot; core.js `foldBatch` folds `res.amount==null` into the "listings exist but none had a buyout" branch regardless of `total` |
| R2b-2 | minor | **Per-row `ms` is chunk-cumulative, not per-item** - t0 is stamped at chunk dispatch (all 3 keys set to "scanning" at once, core.js:815), so later-in-chunk rows inherit predecessors' search+fetch+wait. The D-0020 "per-item timings" instrument overstates non-first-in-chunk rows. **Confirms Build 1 R2-2** - crystal-clear reproduction (below). | Grim Arbiter raw 7 146 ms for a single ~0.25 s zero-match search; every chunk shows pos1 ~0.4-3.6 s / pos2 +~3.4 s / pos3 +~3.5 s; core.js:739 stamps t0 on first non-"queued" stage |
| R2b-3 | minor | **Magic flasks live-scanned for ~0.07c** - 2 of 9 searches spent on ~free flasks (1 alch each, 10 000-result generic match). Lower impact than Build 1 (they landed early -> no back-off), but still spends limiter budget on worthless rows. | rows 6/9: magic, `tf=10000`, `1 alch` -> 0.07c, conf `high` |
| R2b-4 | obs `[D-0015]` | **Hands-free autoscan priced 3 of 6 rares** (3 = zero matches) - the strict all-affix default. **By design** (D-0015 owner veto). Better yield than Build 1 (1/9); surfaced for the record. | 3x `tf=0`; priced: Kraken (14), Hypnotic (1), Cataclysm (1) |
| R2b-5 | nit | **Header count vs list length**: "**8** rares to price yourself" while the RARES-TO-PRICE list shows **9** rows and the sub-header says "**3** still need a price". Reconcilable (the 8 excludes Lethal Pride, a unique that also appears for seed-pricing; the 3 = the zero-match rows) but the 8-vs-9 can momentarily confuse. | screenshot header vs list; Lethal Pride is `category:"unique"` yet a scannable row |

No **blocker** (fruition reached, nothing stuck/errored), no **major** (no crash, no wrong or
misleading *number*; every unpriced rare correctly shows no number + a trade link, and every
priced number is sane and source-backed).

---

## 3. UI-truthfulness audit (the R2 lens)

All PASS except where a finding is cited.

- **Extension-active badge:** lit within ~2.5 s of load; text **"extension active - v1.2.1"**;
  `state.bridge = {active:true, version:"1.2.1"}`. PASS.
- **Defaults on an untouched profile:** auto-scan-on-load **ON**, pick-affixes **OFF**,
  weapon-swap **excluded**, tier **min**, listings **"Instant Buyout and In Person"** (D-0017).
  PASS - no clicks needed to set up.
- **Progress bar counts monotonic:** `scanning N/9` climbed 2 -> 4 -> 5 -> 6 -> 8 -> 9 with no
  regression; `done` count non-decreasing; the bar's current-item name always matched
  `scanStatus().current` (Abecedarian, Kraken Star, Foul Sphere, Lethal Pride, Pandemonium,
  Cataclysm across polls). `monotonic = {ok:true, violations:[]}`. PASS.
- **Chips match `scanStatus` stages:** every rendered chip is derived from and agrees with the
  row's `status[k].stage`. The only issue is the *copy* of the zero-match chip (Finding R2b-1),
  not a stage mismatch. PASS (with R2b-1).
- **Totals climb as prices land:** `0 -> 29 677.0c (+5 s, 20 economy items) -> 29 707.3c (+25 s,
  Lethal Pride's exact-seed price replaces its ninja placeholder, +30.3c) -> 30 605.9c (+35 s,
  Hypnotic Ruin +873.6c and Cataclysm +25c land)`. Monotonic **to display resolution**. PASS.
  *Footnote:* `totalsMonotonic` flagged a single **0.0038c** dip at +10 s (29 677.0346 ->
  29 677.0308) - a float-sum reordering artifact as tiny rare prices fold in, ~0.00001% of the
  total, far below the UI's ~0.1c/1-div display grain. Not user-visible; not a finding.
- **Tier flip MIN -> HIGH changes rares:** **PASS (positively exercised this round).** Kraken Star
  (14 listings -> real distribution `{min 1, median 1, high 7}`) renders **1.0c at MIN** and
  **7.0c at HIGH** (`anyRareRowMoved=true`). This is the D-0016 item-4 feature working end-to-end
  in the browser - which Build 1 could not demonstrate (all its rows were single-listing/flat).
  *Instrumentation note:* the driver's `totalsMoved=false` is **not** a defect and **not** a valid
  test - `bpc.totals()` returns the full `{min,median,high}` triple **independent of the selected
  display tier**, so it never changes on a tier click by construction. The real signals are (a)
  the row price moving (it did) and (b) the totals triple itself carrying a spread
  (`30 605.9 / 30 605.9 / 30 611.9` = +6c, all from Kraken's 1->7c). The +6c is invisible at the
  245-div banner grain, but the mechanism is correct.
- **Variant rows show labels:** **PASS (positively exercised this round).** Lethal Pride renders
  the variant tag **"Rakiata seed 13032"** (with lock glyph) in both the stash jewel tile and the
  rare row, plus a **"see what this seed does"** deep-link (the D-0019 Vilsol calculator link).
  `state.items[].variant` = `{class:"seed-jewel", label:"Rakiata seed 13032", locked_stats:[{stat_id:
  "explicit.pseudo_timeless_jewel_rakiata", value:{min:13032,max:13032}, text:"Commanded leadership
  over 13032 warriors under Rakiata"}]}`.
- **Swap items absent from the rares list (default):** PASS - `Honed Thicket Bow of Restoration`
  (Weapon swap, magic) and `Maloney's Mechanism, Ornate Quiver` (Off-hand swap, unique) are
  **excluded** (totals `included=24`), absent from the 9-row scan set and manual list; they render
  on the board in the swap slots (`slot-wswap` / `slot-oswap`, dimmed) only.
- **Weapon-swap toggle re-includes:** PASS - checking "weapon swap" -> `includeSwap()=true`, manual
  list **9 -> 10** (Honed Thicket Bow added as an unpriced scan row), totals `included 24 -> 25`,
  `min 30 605.9c -> 30 616.9c` (**+11c = Maloney's economy value**; the bow is unpriced magic so
  it adds 0 until scanned). It did **not** trigger a runaway re-scan (`scanActive` stayed false -
  the `autoFired` per-build guard held).

---

## 4A. Detailed findings

### R2b-1 (minor) - zero-match rares are mislabelled "no buyout among 0 listings"
3 of 6 rares (Grim Arbiter, Foul Sphere, Pandemonium Shine - all high-affix jewels) resolved to
`total_found = 0` under the strict all-affix default: the search returned **no matching listings at
all**. The extension correctly returns `{total:0, amount:null}`; core.js routes `amount==null` to
stage `nobuyout` with the note *"listings exist but none had a buyout price"*. That note - and the
rendered chip **"WARNING  no buyout among 0 listings - 0 fetched, 0 without a buyout"** plus the
sub-line **"listings exist but none had a buyout price [search 200, 0 fetched, o w/o buyout]"** -
are **false when `total=0`**: there were zero listings, so "no buyout among them" describes the
empty set. This is the **same defect Build 1 filed as R2-1**; reproducing it on a structurally
different build confirms it is a **class bug** (the `foldBatch` `amount==null` branch never
distinguishes `total===0` from `total>0 & no-buyout`). Directly hits the D-0020 UI-truthfulness
criterion and the owner's standing "no buyout everywhere" sensitivity (D-0012).
**Fix hint:** in `foldBatch`, branch on `res.total === 0` -> a distinct stage/copy, e.g.
*"no listings match all N affixes (exact-affix search)"* with the open-search link, separate from
the genuine `total>0 & amount==null` no-buyout case.

### R2b-2 (minor) - per-row `ms` is chunk-cumulative, not per-item (confirmed; textbook reproduction)
`scanSet` stamps `s.t0` on a row's first non-`queued` stage (core.js:739), but `nextChunk` sets
**all three** chunk keys to `"scanning"` at dispatch (core.js:815) before the extension prices them
**serially**. So positions 2 and 3 start their clock at chunk dispatch and their `ms` includes the
rows ahead of them. This build shows it perfectly - each chunk's three raw figures are a near-exact
arithmetic progression of the ~3.33 s search spacing:

| Chunk | pos1 raw | pos2 raw | pos3 raw | pos2-pos1 | pos3-pos2 |
|---|---:|---:|---:|---:|---:|
| 1 | 423 | 3 807 | 7 146 | 3 384 | 3 339 |
| 2 | 3 642 | 7 056 | 10 715 | 3 414 | 3 659 |
| 3 | 3 524 | 6 947 | 10 692 | 3 423 | 3 745 |

Every increment is ~3.3-3.7 s (the pacing quantum); the raw value just accumulates it. Concretely,
**Grim Arbiter's raw 7 146 ms is a single ~0.25 s zero-match search** that happened to be third in
its chunk; its honest per-item cost is the **3 339 ms** increment (almost all pacing wait). The
D-0020 amendment sells this instrument as "per-item timings" - it is really
"time-from-chunk-dispatch-to-terminal." **Fix hint:** stamp t0 on the row's own first `"searching"`
progress event (per-item, emitted by `background.js`), or record per-stage durations; then the raw
column becomes the honest per-item figure and §1a needs no "incremental" derivation.

### R2b-3 (minor) - magic flasks burn scan budget for ~0.07c
The 2 magic flasks were live-scanned (22% of the search budget), each matching the 10 000-result
cap on a generic search (`1 alch`) and pricing to a uniform **0.07c** floor. Unlike Build 1 (where
the flask fetch was the scan's ~28 s tail bottleneck), here they landed at positions 1-2 with no
back-off - so the cost was low this time, but the budget is still spent on near-worthless rows
whose generic match ignores suffix/enchant value. **Fix hint (design, defer to owner):** floor-price
magic flasks from the economy (or skip them from autoscan) instead of spending limiter budget.

### R2b-4 (observation, by-design under D-0015) - strict default -> 3 of 6 rares no-match
Downstream of locked D-0015 ("if the user doesn't manually exclude an affix we should not be doing
that for them"; autoscan stays strict-all-affix). On this build hands-free autoscan priced **3 of 6
rares** (Kraken Star tf=14, Hypnotic Ruin tf=1, Cataclysm Ornament tf=1) and left 3 as honest "no
match". This is the documented tradeoff working as specified - **not a bug** - recorded so the
real-world yield (better than Build 1's 1/9, because this build's priced rares happen to have
looser affix sets) is on file. The 3 no-match rows correctly offer the affix picker
("edit affixes"/"auto") for the user to relax manually.

### R2b-5 (nit) - "8 rares to price yourself" vs 9 list rows vs "3 still need a price"
The header subtitle reads "20 items priced from economy data - **8** rares to price yourself" while
the RARES-TO-PRICE list contains **9** rows and its own sub-header says "**3** still need a price".
All three are internally consistent once you know Lethal Pride is a **unique** (in the 20
economy-priced) that *also* appears as a scannable row for exact-seed pricing, and "3 still need a
price" counts only the zero-match rows. But the naked "8" vs a 9-row list can read as an off-by-one.
**Fix hint:** count the timeless/variant unique in the "to price yourself" figure (say "9"), or
label it separately ("8 rares + 1 variant unique").

## 4B. Positive validations (features Build 1 could not reach - all PASS)

| # | Feature (decision) | Result on this build |
|---|---|---|
| V1 | **Timeless-jewel exact-seed pricing (D-0019)** | Lethal Pride seed **13032** -> exact-seed search (`min=max`) -> `tf=1` -> **124.8c** (1 div), `source:"trade"` (not the ninja floor placeholder). Variant label + lock glyph + "see what this seed does" deep-link all render. **Hands-free** (via `needsScan`). |
| V2 | **Foil/relic unique routing (D-0020 R1)** | Nimis, Topaz Ring priced **7 488c (~60 div)**, `method:"unique-ninja"`, `include:true`, on the board. In-browser confirmation of the R1 fix that stopped foil/relic uniques dropping to `normal` (a ~27% undercount pre-fix). |
| V3 | **Rare min/median/high distribution (D-0016 #4)** | Kraken Star, 14 listings -> `{min 1, median 1, high 7}`; row shows 1.0c at MIN, 7.0c at HIGH. The tier selector visibly moves a real rare. |
| V4 | **Currency rates map (D-0018)** | Flasks priced in **alch** (1 alch -> 0.07c) and jewels in **divine** (1 div -> 124.8c; 7 div -> 873.6c) all converted to chaos. Previously non-chaos/divine currencies fell out with "no chaos rate". |
| V5 | **Weapon-swap exclude + toggle (D-0018)** | 2 swaps excluded by default (`included=24`), re-included by the toggle (`included=25`, +11c Maloney's), no runaway re-scan. |
| V6 | **Gem host-grouping + GRANTED fix (D-0006)** | Gems grouped under host items (Inpulsa's -> Kinetic Blast; Replica Voidwalker -> Sniper's Mark; Piscator's -> Shield Charge; Esh's Mirror -> Haste + Precision), each priced; **no GRANTED mislabel**. |
| V7 | **Untouched-profile defaults (D-0006/17/18)** | autoscan ON, pick-affixes OFF, swap OFF, tier min, listings "Instant Buyout and In Person" - all correct with zero clicks. |

**Economy-price sanity (source `poe.ninja`, shown for the "no misleading number" check):**
Headhunter 15 201c (~122 div), Nimis 7 488c (~60 div), Dying Sun 3 120c (~25 div), Inpulsa's 349c
(~2.8 div), Ashes of the Stars 333c (~2.7 div), Maloney's (swap) 11c. All plausible for the league.
The one number worth the owner's eye is **Hypnotic Ruin 873.6c (7 div) from a single listing**
(`tf=1`, conf **low**) - it is a real listing, correctly badged low-confidence at the row, but it is
summed into the headline total at full weight (the total carries no confidence signal). By-design
under D-0015 (honest number + confidence badge, nothing hidden); noted only so the owner can decide
whether conf-low single-listing items belong in the headline sum. Not filed as a finding.

---

## 5. Console / pageerror capture

- **`pageerror` count: 0.**
- **`console.error` / `console.warning` count: 0.**
- No failed-bridge fallback, no timeout chunks, no 429 surfaced to the page (the limiter absorbed
  all pacing internally; no row reached stage `error`). The extension bridge, the chunked scan
  (incl. the exact-seed timeless search), the cache POSTs, and the tier/swap controls all ran
  without a single page-side error.

Clean.

---

## 6. Method / reproduction

1. Playwright `chromium.launchPersistentContext(r2profile2, {headless:false, viewport:1280x900,
   args:['--disable-extensions-except=<ext>','--load-extension=<ext>','--no-first-run',
   '--no-default-browser-check']})` - extension `v1.2.1` from `C:\scripts\buildpricechecker-poe1\extension`.
2. `goto https://divtally.com/?v=r2-2`; confirm `#bridgeBadge.on` + defaults; **no clicks**.
3. `fill('#url', <build>)` + `press('#url','Enter')` - the single sanctioned interaction.
4. Poll `bpc.scanStatus()` every 5 s (cap 10 min) until `active===false` && every row terminal.
5. Post-scan audit: capture per-row detail; read variant tags; screenshot; click
   `#btSeg [data-tier=high]`; `check('#swapInc')` and re-read totals.
6. All readings dumped to `r2_results2.json`; browser closed in a `finally`.

**Trade footprint:** exactly one hands-free scan (9 search POSTs + 6 fetch GETs - the 3 zero-match
rows fetched nothing; Kraken fetched 14 listings; the timeless row ran one exact-seed search), all
by the extension under its own limiter. **0 re-scans** (budget was 2). No direct pathofexile.com
calls by the auditor.

---

## 7. Cross-round note (for the campaign owner)

Two Build-1 findings **reproduce** here and are therefore **class bugs**, not build-specific:
- **R2-1 == R2b-1** (zero-match "no buyout among 0 listings" copy) - 2 builds, distinct item sets.
- **R2-2 == R2b-2** (chunk-cumulative per-row `ms`) - reproduces as a textbook arithmetic
  progression; note this one **degrades the D-0020 hard-criterion (a) instrument itself**, so it is
  worth fixing before further rounds lean on the per-item numbers.

Everything Build 1 flagged as "could not exercise" (tier spread, variant labels) is now
**positively validated** (V1, V3). No new blocker or major surfaced. Recommend the next round test
a build with a **PoB-code input** (browser path) and a **corrupted/6-link unique** to keep widening
the lens per D-0020's "different tests each round".
