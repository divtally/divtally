# R2 / Build 3 - Browser UI hands-free scan audit

**Round:** 2 (browser UI via Playwright + the real extension) of the D-0020 five-round bug campaign.
**Build:** `f1fti-6231 / ArleAllflame` (Allflame) -
`https://poe.ninja/poe1/builds/allflame/character/f1fti-6231/ArleAllflame`
**Under test:** LIVE site `https://divtally.com/?v=r2-3` + unpacked extension
`C:\scripts\buildpricechecker-poe1\extension` (**v1.2.1**), loaded into a real Chromium via
Playwright persistent context (headless:false, 1280x900).
**Date:** 2026-07-28. **Auditor scope:** the ONLY pathofexile.com traffic is what the extension
itself performed under its own limiter (the product under test). **1 full scan, 0 re-scans** used
(re-scan budget was 2; not needed). No repo files touched except this report.

Every number below is **source-derived** (a live `bpc.scanStatus()` / `bpc.totals()` reading, the
rendered DOM, the `bpc.on('scanstatus')` event stream captured in-page, the post-scan screenshots,
or the actual extension/site source) unless tagged `[DERIVED]` / `[INFERRED]`.

Driver + raw capture (scratchpad, not in repo): `r2driver3.mjs`, `r2_results3.json`,
`r2_progress3.jsonl`, `r2_build3_final.png`, `r2_build3_banner_min.png`, `r2_build3_banner_high.png`.
Profile: `...\scratchpad\r2profile3`.

**Why this build matters (fresh lens vs Builds 1-2):**
- A **Forbidden Flame + Forbidden Flesh** pair (D-0019 variant uniques that *allocate an ascendancy
  notable* - "Slayer") - a **different** D-0019 sub-case than Build 2's timeless jewel. This is the
  first build where a variant unique **failed** its exact-mod search, and it surfaced the campaign's
  **first non-minor bug** (R2c-1, major).
- **Two rares carrying real multi-listing distributions** that positively move the **rendered
  headline** min->high (Build 1's selector was inert; Build 2's spread was sub-grain) - so this is
  the first build to demonstrate the tier selector moving the actual headline pixels.
- **Duplicate-named rows** (two "Hollow Goad" rares, two "Might of the Meek" uniques) - an edge case
  neither sibling build had.
- A **28.3 s mid-scan rate-limit back-off** rendered as a **truthful live countdown**.
- A **corrected per-item timing instrument** (in-page `scanstatus` observer) that measures the
  honest per-item cost the buggy `scanStatus().ms` field cannot (R2c-3).

---

## 0. D-0020 HARD-CRITERIA VERDICT (read first)

| Hard criterion (D-0020 amendment) | Result |
|---|---|
| **(a) Scan-duration audit** - total wall-clock + per-item timings | **PRODUCED** - `totalMs = 70 956 ms` (71.0 s); honest per-item ms for all 14 rows via an independent observer (see §1), plus the raw `scanStatus().ms` for comparison. The raw field is still chunk-cumulative (Finding R2c-3) - this round *builds and reports the corrected instrument*. |
| **(b) Hands-free fruition** - scans to completion, zero intervention, no row stuck non-terminal | **PASS** - scan auto-started at **+5.0 s with zero clicks**; all **14/14 rows reached a terminal stage**; **0 stuck, 0 error**; 0 pageerrors, 0 console errors. A 28.3 s rate-limit back-off mid-scan resolved itself hands-free (honest countdown, then priced). |

The build reached full fruition hands-free. **One MAJOR finding (R2c-1)** - a variant unique whose
exact search returned zero listings is nonetheless **counted in the headline total at a stale
poe.ninja placeholder** - the campaign's first genuine correctness/guardrail issue. The rest are
minors (two confirmed-across-builds class bugs, a flask-budget note) plus by-design consequences of
locked decisions, all flagged with provenance. This round also adds **seven positive validations**
(§4B), including two features no prior build could exercise.

**Hands-free chain observed** (no intervention after one `Enter`): page load -> content script
`hello` -> badge lit **"extension active - v1.2.1"** -> URL submitted -> 14 rows loaded at +5.0 s ->
`maybeAutoStart()` fired `bpc.autoscan()` automatically (defaults: auto-scan-on-load ON,
pick-affixes OFF, swap OFF, tier min) -> serial priced scan (incl. the two Forbidden variant rows
via `needsScan`) -> a 28.3 s window back-off on row 11 (honest countdown) -> `scanEnd()` at +75.2 s.
Every default was already correct on an untouched profile (`bpc_autoscan_auto=null` -> ON,
`bpc_pick_affixes=null` -> OFF, `bpc_include_swap=null` -> OFF, `tier=min`, `bpc_status_v2=null` ->
"Instant Buyout and In Person" per D-0017) - **no clicks were needed to set up the run.**

---

## 1. THE TIMING TABLE

**Total scan wall-clock:** `totalMs = 70 956 ms` (71.0 s), `scanStatus().startedAt -> finishedAt`
(the in-page observer independently measured the identical `70 956 ms`, start-of-first-search to
scan-end). Wall-clock from the single `Enter` to `active=false` = **75.2 s** (includes ~5.0 s build
fetch + board build before the scan starts).
**Rows scanned:** 14 = **11 rares** (8 cluster/searching-eye jewels priced, 3 zero-match) + **1
magic flask** + **2 variant uniques** (the Forbidden pair, via `needsScan`). The other 22 items (18
plain uniques + 4 gems) are economy-priced at load; the weapon-swap unique (Atziri's Disfavour) is
excluded by default (D-0018). So 14 rows scan.

### 1a. HONEST per-item time (observer), sorted DESC - the corrected instrument

The `honest ms` column is **search-event -> terminal-event** for that row's OWN events, captured
from the `bpc.on('scanstatus')` stream (the extension emits a per-item `searching` event when it
actually starts that row). This is the figure the D-0020 amendment asked for; the `raw ms` column is
`scanStatus().status[k].ms`, which is chunk-cumulative and **wrong for non-first-in-chunk rows**
(Finding R2c-3). "send@" = when the extension actually started that row's search (scan-relative s).

| # | Item | Cat | **honest ms** | raw ms | raw/honest | send@ (s) | Terminal | Price applied |
|---|------|-----|-------:|-------:|-----:|------:|----------|---------------|
| 1 | Hollow Goad, Searching Eye Jewel (copy 1) | rare | **28 258** | 31 386 | 1.1x | 32.2 | done | 247.8 / 619.5 / 619.5c (6 listings) - **incl. the 28.3 s back-off** |
| 2 | Hypnotic Solace, Medium Cluster Jewel | rare | **3 915** | 7 930 | 2.0x | 4.0 | done | 495.6c (1 listing) |
| 3 | Dragon Stone, Medium Cluster Jewel | rare | **3 906** | 10 812 | 2.8x | 25.2 | done | 58c (2 listings) |
| 4 | Morbid Iridescence, Searching Eye Jewel | rare | **3 703** | 6 801 | 1.8x | 11.0 | done | 371.7c (1 listing) |
| 5 | Enthralling Gaze, Searching Eye Jewel | rare | **3 593** | 3 601 | 1.0x | 64.0 | done | 619.5 / 867.3 / 1239c (10 listings) |
| 6 | Foe Bliss, Large Cluster Jewel | rare | **3 531** | 3 536 | 1.0x | 18.3 | done | 371.7c (1 listing) |
| 7 | Hollow Goad, Searching Eye Jewel (copy 2) | rare | **3 515** | **34 901** | **9.9x** | 60.5 | done | 1362.9c (1 listing) |
| 8 | Gale Desire, Large Cluster Jewel | rare | **3 512** | 10 313 | 2.9x | 14.7 | done | 1486.8c (2 listings) |
| 9 | Soul Desire, Medium Cluster Jewel | rare | **3 370** | 6 906 | 2.0x | 21.8 | nobuyout (0) | - (unpriced, link) |
| 10 | Ancient Weaver, Searching Eye Jewel | rare | **3 347** | 6 948 | 2.1x | 67.6 | nobuyout (0) | - (unpriced, link) |
| 11 | Fulgent Bliss, Medium Cluster Jewel | rare | **3 123** | 3 127 | 1.0x | 29.1 | nobuyout (0) | - (unpriced, link) |
| 12 | Forbidden Flame, Crimson Jewel (var "Slayer") | unique | **3 122** | 4 013 | 1.3x | 0.9 | nobuyout (0) | **15c placeholder - see R2c-1** |
| 13 | Forbidden Flesh, Cobalt Jewel (var "Slayer") | unique | **3 092** | 3 096 | 1.0x | 7.9 | nobuyout (0) | **22.8c placeholder - see R2c-1** |
| 14 | Dabbler's Diamond Flask of Incision | magic | **869** | 893 | 1.0x | 0.03 | done | 0.07c (10 000-result generic match) |

**The exhibit for R2c-3:** row 7 (Hollow Goad copy 2) is a trivial **3 515 ms** row that the raw
instrument reports as **34 901 ms** - the single "most expensive" row by raw ms, a **9.9x**
overstatement - purely because its chunk (`[Fulgent, Hollow#1, Hollow#2]`) was dispatched at 29.1 s
and its raw clock (`t0`) started then, absorbing Fulgent's 3 s **and** Hollow#1's 28.3 s back-off.
Its honest cost is 3.5 s. This is a sharper reproduction than Build 1 (Cataclysm 34 781 raw / 3 336
honest) or Build 2 (Grim Arbiter 7 146 / 3 339).

### 1b. Time share: searching vs waiting `[DERIVED]` from observed search-event gaps

Observed inter-search gaps (the `searching`-event spacing, scan-relative, source-derived from the
live event stream): `[0.86, 3.13, 3.93, 3.09, 3.70, 3.53, 3.53, 3.37, 3.92, 3.13, 28.26, 3.53,
3.59]` s.

- **Cleanest single HTTP measurement:** the very first search (Dabbler flask) fired at scan-rel
  0.03 s and terminated at 0.89 s -> **869 ms** for a real search+fetch round-trip with no prior
  request to pace against. Every per-row figure above ~0.9 s is limiter pacing, not HTTP.
- **Pacing floor (source-derived):** `background.js:22` `DEFAULT_RULES.search[0] = [5,10]`;
  `background.js:84` `spacing = ceil(10000 / effectiveCap(5))`. The **12 non-outlier gaps average
  3.28 s** - corroborating `effectiveCap(5) ~= 3` -> ~3.33 s floor. The scan is pacing-bound at this
  floor.
- **One window back-off:** gap #11 (before Hollow Goad copy 1) was **28.26 s** - a genuine
  rate-limit pause (the row's chip literally read `"rate limit - 25s...20s...15s..."`, §4B V4). This
  single stall is **40 % of the entire 71 s scan.**
- **Estimated split of the 71.0 s:** **~39 s even pacing (55 %)** + **~28 s single window back-off
  (40 %)** + **~4 s actual HTTP + first-search + tail (~5 %)**. `[DERIVED]` from the observed gap
  series. The scan is **>=95 % rate-limiter waiting**, essentially 0 % compute/parse.

**Takeaway:** rate-limiter-bound, not compute-bound. Unlike Build 2 (which rode the floor with no
back-off) and like Build 1 (which hit a bigger tail stall), this scan took one ~28 s window back-off
mid-run; it resolved hands-free with an honest countdown. **Order/window-saturation dependent** -
the back-off landed on search 11, once the short windows had filled.

---

## 2. Findings summary

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| **R2c-1** | **major** | **A variant unique whose exact-mod search returns 0 listings is still COUNTED in the headline total at a stale poe.ninja name-level placeholder.** Forbidden Flame (15c) + Forbidden Flesh (22.8c) both resolved `total_found=0` (nobuyout) yet render a price **and** are `included` - contradicting D-0019 ("floor is a PLACEHOLDER, not its price"; "unmatchable -> link + no number") and the core guardrail ("never a misleading number"), and **inconsistent with the 3 genuine rares** that hit 0 matches (correctly excluded, no number). Post-scan the failed rows look identical to legitimately-priced rows. | `state.priced` shows both Forbidden rows `method:"extension", source:"trade", chaos:{min:15/22.8}, total_found:0`, stage `nobuyout`; `totals()` `priced=33, included=32` (the only exclusion is the swap) -> both counted; root cause traced in §4A |
| R2c-2 | minor | **Zero-match rows mislabelled** "no buyout among 0 listings - 0 fetched, 0 without a buyout" + note "listings exist but none had a buyout price" - self-contradictory when `total_found=0`. **Third confirmation** (Builds 1 R2-1, 2 R2b-1) -> class bug. Hits **5 rows** here (3 rares + the 2 Forbidden uniques). | chip text captured mid-scan: `"⚠ no buyout among 0 listings · 0 fetched, 0 without a buyout"` on Soul Desire / Fulgent Bliss / Ancient Weaver; same note on both Forbidden rows; core.js `foldBatch` folds `amount==null` regardless of `total` |
| R2c-3 | minor | **Raw per-row `ms` is chunk-cumulative, not per-item.** **Third confirmation** - and this round the **corrected instrument was built** (in-page `scanstatus` observer): honest per-item is 3.1-3.9 s for every row vs raw up to 34 901 ms (row 7, 9.9x). Still degrades the D-0020 hard-criterion (a) field. | §1a table (raw vs honest columns); core.js:739 stamps `t0` on first non-queued stage, core.js:858 sets the whole chunk to `"scanning"` at dispatch |
| R2c-4 | minor | **Magic flask live-scanned for ~free** - Dabbler's Diamond Flask matched the 10 000-result generic cap and priced to a 0.07c floor. Only 1 flask here (vs 3/2 in Builds 1/2); landed first, no back-off, so low cost - but still spends a search on a worthless row. Confirms R2-3/R2b-3. | row 14: magic, `tf=10000`, 0.07c |
| R2c-5 | obs `[D-0015]` | **Strict all-affix default -> hands-free autoscan priced 8 of 11 rares** (3 zero-match) **and neither Forbidden unique** (both 0-match). **By design** (D-0015 owner veto). Best rare yield of the three builds; surfaced for the record. | 8 rares `done`; 3 rares + 2 uniques `tf=0` |

No **blocker** (fruition reached, nothing stuck/errored). **One major** (R2c-1). No crash; every
priced *rare* number is sane and source-backed; the misleading-number issue is confined to the
failed variant-unique fallback (R2c-1).

---

## 3. UI-truthfulness audit (the R2 lens)

All PASS except where a finding is cited.

- **Extension-active badge:** lit within ~2.5 s of load; text **"extension active - v1.2.1"**;
  `state.bridge = {active:true, version:"1.2.1"}`. PASS.
- **Defaults on an untouched profile:** auto-scan-on-load **ON**, pick-affixes **OFF**, weapon-swap
  **excluded**, tier **min**, listings **"Instant Buyout and In Person"** (D-0017). PASS - zero
  clicks to set up.
- **Progress bar counts monotonic:** `scanning N/14` climbed 2 -> 3 -> 5 -> 6 -> 7 -> 9 -> 10 -> 11
  -> 12 -> 13 -> 14 with no regression; `done` non-decreasing; the bar's current-item name always
  matched `scanStatus().current`. `monotonic = {ok:true, violations:[]}`. PASS.
- **Chips match `scanStatus` stages:** every rendered chip is derived from and agrees with the row's
  `status[k].stage` - including the honest `queued -> scanning/searching -> waiting -> done/nobuyout`
  progression and the live "N ahead" queue position. The only issue is the *copy* of the zero-match
  chip (R2c-2), not a stage mismatch. PASS (with R2c-2).
- **Totals climb as prices land:** `0 -> 28 348c (+5 s, 22 economy items + first rares) -> 30 702c
  (+25 s) -> 31 132c (+35 s) -> 33 362c (+75 s, the big cluster/searching-eye jewels land)`.
  `totalsMonotonic = {ok:true, violations:[]}` - **no dip at all** (cleaner than Build 2, which had a
  sub-display float wobble). PASS.
- **Tier flip MIN -> MEDIAN -> HIGH moves the RENDERED headline + rare rows:** **PASS - positively
  exercised, and the first build to move the headline pixels.** The `#btVal` headline read **269 div
  at MIN -> 274 at MEDIAN -> 277 at HIGH** (triple `33 362 / 33 984 / 34 358c`, ~996c spread).
  Two rare rows carry real distributions and visibly move: **Enthralling Gaze** `5.0 (620c) -> 7.0
  (867c) -> 10.0 (1239c)` div and **Hollow Goad copy 1** `2.0 (248c) -> 5.0 (620c)`. Banner
  screenshots captured at MIN and HIGH. *(Build 1 was inert - no spread; Build 2 had a real spread
  but only ~6c, sub-grain at the div-rounded banner, so its headline didn't visibly move. This build
  clears the grain: +8 div.)*
- **Variant rows show labels:** **PASS.** Both Forbidden jewels render the variant tag **"Slayer"**
  (with lock glyph) in the rare row - the ascendancy notable they allocate. `state.items[].variant =
  {class:"notable-jewel", label:"Slayer", locked_stats:[{stat_id:"explicit.stat_2460506030",
  value:{option:43195}, text:"Allocates Slayer"}]}` (Flame) and `explicit.stat_1190333629`
  (Flesh). The *label + defining-mod lock* half of D-0019 works; the *pricing fallback when 0-match*
  is the R2c-1 bug.
- **Swap items absent from the rares list (default):** PASS - `Atziri's Disfavour, Vaal Axe` (Weapon
  swap, unique) is **excluded** (`included=32`), absent from the 14-row scan set and the manual list;
  it renders on the board's swap slot only.
- **Weapon-swap toggle re-includes:** PASS - checking "weapon swap" -> `includeSwap()=true`, totals
  `included 32 -> 33`, `min 33 362c -> 33 592c` (**+229.8c = Atziri's Disfavour economy value**). It
  did **not** trigger a runaway re-scan (`scanActive` stayed false - the `autoFired` per-build guard
  held). The manual/rares list stayed **14 -> 14** (correct - the swap is an economy-priced unique,
  not a scannable rare, so it joins the total without adding a scan row).

---

## 4A. Detailed findings

### R2c-1 (MAJOR) - a 0-match variant unique is counted in the total at its stale ninja placeholder

**What happens.** Both Forbidden jewels are D-0019 variant uniques: at load they get a poe.ninja
*name-level* floor (`unique-ninja-variant`, 15c / 22.8c) that D-0019 explicitly calls **"a
PLACEHOLDER, not its price"**, and `needsScan()` flags them for an exact-mod trade search. That
search ran hands-free (correctly locked to the defining mod "Allocates Slayer", option 43195) and
returned **`total_found = 0`** - no listing of a *Slayer* Forbidden Flame/Flesh with a buyout. The
correct outcome per D-0019 is "unmatchable -> link + no number" (exactly how the 3 genuine 0-match
rares resolve). Instead **both rows keep the 15c / 22.8c placeholder, render it as their price, and
are counted in the headline total.**

**Root cause (traced through the source).**
1. `foldBatch` `amount==null` branch (core.js:795) calls
   `applyPrice(key, {method:"extension", source:"trade", note:"...", total_found:0 /* NO chaos */},
   {include:false})`.
2. `applyPrice` (core.js:450) does `merged = Object.assign({}, cur, patch)` - since the patch has
   **no `chaos`**, `merged.chaos` **retains the load-time ninja placeholder** `{min:15,...}`.
3. The include gate (core.js:458-459) is
   `if (opts.include) ...; else if (!(key in state.enabled)) state.enabled[key] = defaultOn(key);`.
   The row was **already** `state.enabled = true` from its load-time economy price, so
   `!(key in state.enabled)` is **false** -> `{include:false}` is a **no-op**; the row stays
   included.
4. `method` is now `"extension"` (not `unique-ninja*`), so `needsScan()` returns false -> the row is
   considered "finished" and never re-flagged.
Result: `totals()` (core.js:154, counts any item with `state.enabled[k] && p.chaos.median!=null`)
sums the placeholder. Confirmed by `priced=33, included=32` where the *only* excluded row is the
weapon swap - both Forbidden rows are in the included 32.

**Impact.** On THIS build the magnitude is tiny - 37.8c of 33 362c (**0.11 %**), invisible at the
269-div headline. But the **class** is not tiny: a variant unique whose name-level floor is high but
whose specific variant is cheap/unlisted (or vice-versa) injects an arbitrary placeholder into the
total, and the failed row is **visually indistinguishable from a real price** post-scan (the chip
clears once it has a number). This is the campaign's first violation of the "never a misleading
number" guardrail, and it directly contradicts a Locked decision (D-0019). Severity **major** on the
guardrail/design-contract grounds despite the small numeric size here; the owner can down-rank if he
prefers a name-level floor over "no number" for these rows - but then the *genuine rare* 0-match
handling and D-0019's text should change to match, and the row needs a visible "floor / not the
variant price" signal.

**Fix options.**
- *Targeted:* in `foldBatch`'s `nobuyout`/`error` branches, when the row is a variant unique
  (`state.priced[key].variant` / prior `method` was `unique-ninja*`), pass an explicit
  `chaos:{min:null,median:null,high:null}` in the patch **and** force `state.enabled[key]=false`, so
  it falls back to link-only exactly like a 0-match rare.
- *Root-cause:* make `applyPrice` honor `opts.include===false` as an **explicit exclusion** (set
  `state.enabled[key]=false`) for non-cache overrides, not merely "don't auto-include a new row". (A
  cache-fill should keep its current passive behaviour - branch on an `opts.explicit` flag.)

### R2c-2 (minor) - zero-match rows mislabelled "no buyout among 0 listings" (third confirmation)
The strict all-affix default (D-0015) returned **no listings** for 5 rows (3 rares: Soul Desire,
Fulgent Bliss, Ancient Weaver; + both Forbidden uniques). The extension correctly returns
`{total:0, amount:null}`; core.js routes `amount==null` to stage `nobuyout` with the note *"listings
exist but none had a buyout price"* and the chip **"⚠ no buyout among 0 listings · 0 fetched, 0
without a buyout"** - all **false when `total=0`** (they describe the empty set). Filed identically
by Build 1 (R2-1) and Build 2 (R2b-1); reproducing on a third, structurally different build (jewel-
heavy, with variant uniques) confirms a **class bug** in the `foldBatch` `amount==null` branch.
Compounds R2c-1 for the Forbidden rows (doubly wrong: keeps a number *and* mislabels the reason).
**Fix hint:** branch on `res.total === 0` -> distinct copy, e.g. *"no listings match all N affixes
(exact-affix search)"* + open-search link, separate from the genuine `total>0 & amount==null` case.

### R2c-3 (minor) - raw per-row `ms` is chunk-cumulative; corrected instrument built this round
Same mechanism as R2-2/R2b-2: `scanSet` stamps `t0` on a row's first non-`queued` stage
(core.js:739), but `nextChunk` sets **all** keys in a chunk of 3 to `"scanning"` at dispatch
(core.js:858) before the extension prices them serially - so later-in-chunk rows inherit their
predecessors' time. This round I added an in-page observer on the `bpc.on('scanstatus')` event
stream that records the timestamp of each row's **own** `searching` event, giving the honest
per-item duration (§1a). It reproduces the bug at up to **9.9x** (row 7: raw 34 901 ms / honest
3 515 ms) and, crucially, provides the number the D-0020 amendment actually wants.
**Fix hint:** stamp `t0` on the row's own first `searching` progress event (the extension already
emits it per-item; the observer here consumes exactly that), or store per-stage durations. Then the
raw column becomes honest and §1a needs no separate instrument.

### R2c-4 (minor) - magic flask burns a search for ~0.07c
Dabbler's Diamond Flask was live-scanned (1 of 14 searches), matched the 10 000-result generic cap,
priced to a 0.07c floor. It landed first (no back-off) so the cost was one ~0.9 s round-trip - low
this build - but the generic match ignores suffix/enchant value and buys neither accuracy nor speed.
Confirms R2-3/R2b-3. **Fix hint (design, defer to owner):** floor-price magic flasks from the
economy or skip them from autoscan.

### R2c-5 (observation, by-design under D-0015)
Downstream of locked D-0015 (autoscan stays strict-all-affix). Hands-free autoscan priced **8 of 11
rares** (Hypnotic Solace, Morbid Iridescence, Gale Desire, Foe Bliss, Dragon Stone, both Hollow
Goads, Enthralling Gaze) and left 3 rares + both Forbidden uniques as 0-match. Best rare yield of the
three R2 builds (Build 1: 1/9, Build 2: 3/6). The 3 no-match rares correctly offer the affix picker
for manual relaxation. **Not a bug** - the documented tradeoff working as specified.

## 4B. Positive validations (all PASS)

| # | Feature (decision) | Result on this build |
|---|---|---|
| V1 | **D-0019 variant registry - defining-mod lock (new sub-case)** | Forbidden Flame + Forbidden Flesh correctly identified as `notable-jewel` variants and searched **with** the locked defining mod "Allocates Slayer" (`option 43195`; stat ids `explicit.stat_2460506030` / `explicit.stat_1190333629`), `method:"extension"` (not name-only). Variant tag **"Slayer"** + lock glyph render. A *different* D-0019 path than Build 2's timeless-jewel seed. (The 0-match pricing fallback is R2c-1; the identification/mod-lock half is validated.) |
| V2 | **Tier selector moves the RENDERED headline (D-0016 #4)** | `#btVal` **269 -> 274 -> 277 div** across MIN/MEDIAN/HIGH; two rares move (Enthralling Gaze 5->7->10 div, Hollow Goad#1 2->5 div). **First build to move the headline pixels** (Build 1 inert, Build 2 sub-grain). |
| V3 | **Duplicate-named rows keyed by index** | Two **"Hollow Goad, Searching Eye Jewel"** rares (one 6-listing distribution 247.8/619.5/619.5c, one 1-listing 1362.9c) and two **"Might of the Meek, Crimson Jewel"** uniques (5c each) - all distinct rows, independently scanned/priced/counted; no collision in the product (my driver's name-keyed analysis *did* collide - product keys on `item.index`, correctly). |
| V4 | **Rate-limit back-off shown as an honest live countdown (D-0018 + v1.1 waiting)** | The 28.3 s window pause on Hollow Goad#1 rendered a **decrementing chip**: `"rate limit - 25s" -> "20s" -> "15s" -> "10s" -> "5s"`, while queued rows showed `"⏳ waiting - 1/2 ahead"`. Not a frozen UI; the wait resolved hands-free and the row priced. `scanStatus().waitUntil` drives it. |
| V5 | **Weapon-swap exclude + toggle (D-0018)** | Atziri's Disfavour (Vaal Axe, weapon swap, unique) excluded by default (`included=32`), re-included by the toggle (`included=33`, +229.8c), no runaway re-scan (`scanActive` stayed false). |
| V6 | **Rare distribution math (D-0016 #4)** | Cluster/searching-eye jewels priced from real multi-listing fetches (Gale Desire 2, Dragon Stone 2, Hollow Goad#1 6, Enthralling Gaze 10 listings), local trim+percentile tiers computed; single-listing rares flat. |
| V7 | **Untouched-profile defaults + clean console** | autoscan ON, pick-affixes OFF, swap OFF, tier min, listings "Instant Buyout and In Person" - all correct, zero clicks; 0 console errors/warnings, 0 pageerrors across the whole run. |

**Economy-price sanity (source `poe.ninja`, for the "no misleading number" check):** Headhunter
15 201c (~123 div), Nimis (foil/relic, D-0020 R1) 7 488c (~60 div), Dying Sun 3 120c, Ashes of the
Stars 333c, Cinderswallow Urn 249.6c, Inpulsa's 349.2c, Atziri's Disfavour (swap) 229.8c,
Unnatural Instinct 343c, Piscator's Vigil / The Wise Oak 1c. All plausible for the league. The only
misleading numbers are the two Forbidden placeholders (R2c-1).

---

## 5. Console / pageerror capture

- **`pageerror` count: 0.**
- **`console.error` / `console.warning` count: 0.** (Total page-console messages captured: 0.)
- No failed-bridge fallback, no timeout chunks, no page-side 429. The 28.3 s rate-limit back-off was
  handled entirely by the extension's service-worker limiter and surfaced to the page **only** as the
  honest `waiting`/countdown progress event (§4B V4) - **no error reached the page**, no row hit
  stage `error`. The bridge, the chunked scan (incl. both exact-mod Forbidden searches), the cache
  POSTs (8 priced rares), and the tier/swap controls all ran without a single page-side error.

*Capture limitation (noted for honesty):* the extension's rate-limit decisions live in the MV3
service worker, which this page-side console cannot see; the 28.3 s pause was reconstructed from the
`scanstatus` `waiting`/`waitUntil` events (which the page *does* receive) and the observed search-gap
series, not from the worker's network log. The exact triggering window ([5,10] vs [15,60] vs a
server `Retry-After`) is **[INFERRED]** - not distinguishable from page-side capture; the chip's
"rate limit" label + ~28 s magnitude are the source-derived facts.

---

## 6. Method / reproduction

1. Playwright `chromium.launchPersistentContext(r2profile3, {headless:false, viewport:1280x900,
   args:['--disable-extensions-except=<ext>','--load-extension=<ext>','--no-first-run',
   '--no-default-browser-check']})` - extension `v1.2.1` from
   `C:\scripts\buildpricechecker-poe1\extension`.
2. `goto https://divtally.com/?v=r2-3`; confirm `#bridgeBadge.on` + defaults; install the in-page
   `bpc.on('scanstatus')` observer; **no clicks**.
3. `fill('#url', <build>)` + `press('#url','Enter')` - the single sanctioned interaction.
4. Poll `bpc.scanStatus()` every 5 s (cap 10 min) until `active===false` && every row terminal.
5. Post-scan audit: read the observer's honest per-item timings; capture per-row detail + variant
   tags + chip/notes; screenshot banner at MIN; click `#btSeg [data-tier=median]` then `[high]`,
   read `#btVal` + per-rare row prices at each; screenshot banner at HIGH; `check('#swapInc')` and
   re-read totals.
6. All readings dumped to `r2_results3.json`; browser closed in a `finally`.

**Trade footprint:** exactly one hands-free scan (14 search POSTs + fetches for the 8 priced rares +
2 exact-mod Forbidden searches; the 5 zero-match rows fetched nothing), all by the extension under
its own limiter. **0 re-scans** (budget was 2). No direct pathofexile.com calls by the auditor.

---

## 7. Cross-round note (for the campaign owner)

- **Two prior findings reproduce a THIRD time -> firmly class bugs:** R2c-2 (== R2-1 == R2b-1,
  zero-match "no buyout among 0 listings" copy) and R2c-3 (== R2-2 == R2b-2, chunk-cumulative raw
  `ms`). R2c-3 degrades the D-0020 hard-criterion (a) instrument itself and now has a proven, cheap
  fix (stamp `t0` on the per-item `searching` event - the observer this round is a working
  reference). **Recommend fixing both before further rounds lean on the per-item numbers / no-buyout
  copy.**
- **NEW major (R2c-1):** the first genuine correctness/guardrail issue of the campaign - a 0-match
  variant unique counted at a stale ninja placeholder. It only appears when a variant unique
  **fails** its exact search (Build 2's timeless jewel succeeded, so no prior build hit it). Root
  cause + two fixes in §4A. Worth an owner call on the desired fallback (link-only vs labelled
  floor).
- **Positively validated for the first time:** the tier selector moving the **rendered headline**
  (V2), the **honest rate-limit countdown** during a real back-off (V4), and **duplicate-name**
  handling (V3).
- Everything Build 1 could not exercise (tier spread) and a new D-0019 sub-case (ascendancy-notable
  Forbidden pair) are now covered. Per D-0020's "different tests each round," a good next lens is a
  **PoB-code input** (browser paste path, still unexercised in R2) and a **corrupted / 6-link
  unique**, plus a **manual affix-picker** run to exercise the relax path the strict default (R2c-5)
  leaves on the table.
