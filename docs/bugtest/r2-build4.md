# R2 / Build 4 - Browser UI hands-free scan audit

**Round:** 2 (browser UI via Playwright + the real extension) of the D-0020 five-round bug campaign.
**Build:** `yalokk-2571 / TimeForAurab` (Champion, L100, Allflame) -
`https://poe.ninja/poe1/builds/allflame/character/yalokk-2571/TimeForAurab`
**Under test:** LIVE site `https://divtally.com/?v=r2-4` + unpacked extension
`C:\scripts\buildpricechecker-poe1\extension` (**v1.2.1**), loaded into a real Chromium via
Playwright persistent context (headless:false, 1280x900).
**Date:** 2026-07-28. **Auditor scope:** the ONLY pathofexile.com traffic is what the extension
itself performed under its own limiter (the product under test). **1 full scan + 1 targeted re-scan**
used (re-scan budget was 2; the second run recovered the post-scan audit lost to an auditor-harness
bug - see §6). No repo files touched except this report.

**Deployed code identity:** `public/site/assets/core.js` mtime 2026-07-28 00:13 / committed 00:14
("R1 fixes deployed"). Build 3 ran ~00:57 against this same code and Build 4 tests it unchanged, so
the three carry-over class bugs below (R2d-1/2/3) are reproduced on **identical** deployed code, not a
new build.

Every number below is **source-derived** (a live `bpc.scanStatus()` / `bpc.totals()` reading, the
rendered DOM, the `bpc.on('scanstatus')` event stream captured in-page, the item's own built
`trade_query`, the post-scan screenshots, or the actual extension/site source) unless tagged
`[DERIVED]` / `[INFERRED]`.

Driver + raw capture (scratchpad, not in repo): `r2driver4.mjs`, `r2_results4.json` (re-scan,
authoritative), `r2_results4_run1.json` (first scan), `r2_progress4.jsonl`, `r2_build4_final.png`,
`r2_build4_banner_min.png`, `r2_build4_banner_high.png`. Profile: `...\scratchpad\r2profile4`.

**Why this build matters (fresh lens vs Builds 1-3):**
- **Watcher's Eye, Prismatic Jewel** - a **ROLL-DEFINED** D-0019 variant with **three** locked mods
  (*affected by Determination, Grace, Purity of Ice*), including one **boolean** mod with no numeric
  value. The marquee variant-unique case, never exercised in R2. Its exact 3-mod search **failed
  (0 matches)** and surfaced the campaign's first-major (R2c-1) again - now on the **highest-profile
  variant** at a **materially larger, headline-visible magnitude** (55c / 2.9% vs Build 3's 0.11%).
- **Bubonic Trail, Murder Boots** - a **SOCKET-DEFINED "count variant"** (abyssal socket count), a
  *different* D-0019 sub-case than Build 2 (timeless seed) or Build 3 (notable-jewel). It had **no
  poe.ninja placeholder** at all, so it is the clean **control** for R2c-1 - and it priced correctly
  (real trade match, 1.0c). The two variants side by side isolate the R2c-1 bug precisely.
- **A TWO-item weapon-swap SET** (Silverbranch bow + Replica Maloney's quiver) - Build 3 had one
  swap; here exclude-by-default + toggle-re-include must handle a **pair**, and both re-include with
  the total moving by **exactly** the sum of both economy values.
- **Heaviest magic load of the campaign - 8 magic rows** (5 flasks + 3 small-cluster jewels) - which
  quantifies R2c-4 at scale (~38% of the scan burned on near-worthless generic matches; the 3 cluster
  jewels' notable value ignored).
- The scan was driven **twice**, hands-free, to identical completion (67.5 s / 67.6 s, 13/13) - the
  strongest fruition evidence of the round.

---

## 0. D-0020 HARD-CRITERIA VERDICT (read first)

| Hard criterion (D-0020 amendment) | Result |
|---|---|
| **(a) Scan-duration audit** - total wall-clock + per-item timings | **PRODUCED** - `totalMs = 67 619 ms` (67.6 s) on the audited re-scan (`67 496 ms` on the first scan - two independent measurements agree to 0.2 %). Honest per-item ms for all 13 rows via an independent in-page observer (§1), plus the raw `scanStatus().ms` for comparison. The raw field is still chunk-cumulative (Finding R2d-3, up to **9.3x** here). |
| **(b) Hands-free fruition** - scans to completion, zero intervention, no row stuck non-terminal | **PASS (twice)** - scan auto-started at **+5.0 s with zero clicks** on both runs; all **13/13 rows reached a terminal stage**; **0 stuck, 0 error**; **0 pageerrors, 0 console messages** across both runs. A 27.9 s rate-limit back-off on Watcher's Eye resolved itself hands-free (honest countdown). |

Both runs reached full fruition hands-free. **One MAJOR finding (R2d-1)** - the marquee Watcher's Eye,
whose exact 3-aura roll search returns 0 listings, is nonetheless **counted in the headline total at a
55c poe.ninja placeholder** (2.9 % of the total, headline-visible), and its warning chip **clears** so
the failed row looks identical to a legitimately-priced one. This is the same class as Build 3's R2c-1,
reproduced on a higher-profile variant with a larger, now-visible magnitude. The rest are the two
confirmed carry-over minors (R2d-2 zero-match copy, R2d-3 chunk-cumulative ms - both now on their
**4th** build) and R2d-4 (magic-burns-searches, worst instance yet), plus by-design consequences of
locked decisions. This round adds **seven positive validations** (§4B), two of them D-0019 sub-cases
no prior build could exercise.

**Hands-free chain observed** (no intervention after one `Enter`): page load -> content script
`hello` -> badge lit **"extension active - v1.2.1"** -> URL submitted -> 13 rows loaded at +5.0 s ->
`maybeAutoStart()` fired `bpc.autoscan()` automatically -> serial priced scan (incl. both variant
exact-mod searches via `needsScan`) -> a 27.9 s window back-off on Watcher's Eye (honest countdown) ->
`scanEnd()` at +70.2 s. Every default was already correct on an untouched profile
(`bpc_autoscan_auto=null` -> ON, `bpc_pick_affixes=null` -> OFF, `bpc_include_swap=null` -> OFF,
`tier=min`, `bpc_status_v2=null` -> "Instant Buyout and In Person" per D-0017) - **no clicks were
needed to set up the run.**

---

## 1. THE TIMING TABLE

**Total scan wall-clock:** `totalMs = 67 619 ms` (67.6 s), `scanStatus().startedAt -> finishedAt` (the
in-page observer independently measured `67 619 ms`, first-search to scan-end). The first scan
measured `67 496 ms` - the two agree to 0.2 %. Wall-clock from the single `Enter` to `active=false` =
**70.2 s** (identical both runs; includes ~5.0 s build fetch + board build before the scan starts).
**Rows scanned:** 13 = **3 rares** (all 0-match) + **8 magic** (5 flasks + 3 small-cluster jewels, all
generic-matched) + **2 variant uniques** (Watcher's Eye + Bubonic Trail, via `needsScan`). The other
18 items (9 plain economy uniques + 7 gems + the 2 weapon-swap uniques) are economy-priced at load; the
2 swaps are excluded by default (D-0018). So 13 rows scan.

### 1a. HONEST per-item time (observer), sorted DESC - the corrected instrument

The `honest ms` column is **search-event -> terminal-event** for that row's OWN events, from the
`bpc.on('scanstatus')` stream. `raw ms` is `scanStatus().status[k].ms`, chunk-cumulative and wrong for
non-first-in-chunk rows (Finding R2d-3). "send@" = when the extension actually started that row's
search (scan-relative s).

| # | Item | Cat | **honest ms** | raw ms | raw/honest | send@ (s) | Terminal | Price applied |
|---|------|-----|-------:|-------:|-----:|------:|----------|---------------|
| 1 | **Watcher's Eye, Prismatic Jewel** (var, 3-aura) | unique | **27 871** | 31 631 | 1.1x | 32.5 | **nobuyout (tf 0)** | **55c placeholder - counted - see R2d-1** |
| 2 | Potent Small Cluster Jewel of the Brute | magic | **3 810** | **35 441** | **9.3x** | 60.4 | done | 0.066c (10 000-generic) |
| 3 | Potent Small Cluster Jewel of the Lost | magic | **3 756** | 3 760 | 1.0x | 28.8 | done | 0.066c (10 000-generic) |
| 4 | Potent Small Cluster Jewel of the Drake | magic | **3 703** | 7 259 | 2.0x | 21.8 | done | 0.066c (10 000-generic) |
| 5 | Perpetual Basalt Flask of the Curlew | magic | **3 683** | 7 121 | 1.9x | 11.0 | done | 0.066c (10 000-generic) |
| 6 | Bubonic Trail, Murder Boots (var, sockets) | unique | **3 632** | 3 925 | 1.1x | 0.3 | done | **1.0c (real match, tf 2876) - V1** |
| 7 | Bottomless Divine Life Flask of Alleviation | magic | **3 623** | 7 548 | 2.1x | 3.9 | done | 0.066c (10 000-generic) |
| 8 | Abundant Jade Flask of the Ibex | magic | **3 562** | 10 683 | 3.0x | 14.7 | done | 0.066c (10 000-generic) |
| 9 | Dabbler's Amethyst Flask of the Lynx | magic | **3 551** | 3 556 | 1.0x | 18.3 | done | 0.066c (10 000-generic) |
| 10 | Bountiful Granite Flask of the Tortoise | magic | **3 433** | 3 438 | 1.0x | 7.6 | done | 0.066c (10 000-generic) |
| 11 | Luminous Curio, Cobalt Jewel | rare | **3 388** | 3 389 | 1.0x | 64.2 | nobuyout (tf 0) | - (unpriced, link) |
| 12 | Armageddon Star, Viridian Jewel | rare | **3 250** | 10 510 | 3.2x | 25.5 | nobuyout (tf 0) | - (unpriced, link) |
| 13 | Golem Trap, Leather Belt | rare | **266** | 294 | 1.1x | 0.03 | nobuyout (tf 0) | - (unpriced, link) |

**Two exhibits in one table:**
- **Row 1 (Watcher's Eye)** is the genuinely most-expensive row - **27 871 ms honest** - because its
  3-mod search actually incurred the scan's single 27.9 s rate-limit back-off. And it 0-matched: the
  most expensive row of the whole scan bought the **worst-quality result** (a mispriced placeholder,
  R2d-1).
- **Row 2 (Cluster of the Brute)** is the R2d-3 exhibit: a trivial **3 810 ms** row that the raw
  instrument reports as **35 441 ms** (**9.3x**) - the raw "most expensive" row - purely because its
  chunk was dispatched right after Watcher's back-off and its raw clock absorbed it. The raw
  instrument therefore **names the wrong row as most-expensive** (Brute, not Watcher's Eye). Sharper
  than Build 3 (9.9x on a 3.5 s row) in that it now *inverts the ranking*.

### 1b. Time share: searching vs waiting `[DERIVED]` from observed search-event gaps

Observed inter-search gaps (source-derived from the live event stream): `[0.26, 3.64, 3.64, 3.43,
3.68, 3.58, 3.55, 3.71, 3.26, 3.76, 27.87, 3.82]` s.

- **Cleanest single HTTP measurement:** the first search (Golem Trap rare) fired at scan-rel 0.03 s
  and terminated at 0.29 s -> **266 ms** for a real search round-trip with nothing to pace against.
  Every per-row figure above ~0.3 s is limiter pacing, not HTTP.
- **Pacing floor (source-derived):** the 11 non-outlier gaps average **3.30 s** - corroborating
  `background.js` `spacing = ceil(10000 / effectiveCap(5)) ~= 3.33 s`. The scan is pacing-bound at
  this floor.
- **One window back-off:** gap #11 (before Watcher's Eye) was **27.87 s** - a genuine rate-limit
  pause (§4B V4). This single stall is **41 % of the entire 67.6 s scan**, and it landed on the one
  variant that then 0-matched.
- **Estimated split of the 67.6 s:** **~35.5 s even pacing (52 %)** + **~27.9 s single window back-off
  (41 %)** + **~4.2 s actual HTTP + first-search + tail (~7 %)**. `[DERIVED]` from the observed gap
  series. The scan is **>=93 % rate-limiter waiting**, essentially 0 % compute/parse.
- **Magic tax `[DERIVED]`:** the 8 magic rows occupy 8 of the 13 search slots at the ~3.3 s floor =
  **~26 s (~38 % of wall-clock)** spent pricing five flasks and three cluster jewels to a 0.066c floor
  (R2d-4).

**Takeaway:** rate-limiter-bound, not compute-bound - same conclusion as Builds 1-3. This build's
back-off landed on the failing variant (Build 3's landed on a rare that *did* price), so the scan's
single most expensive event produced its single worst result.

---

## 2. Findings summary

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| **R2d-1** | **major** | **The marquee Watcher's Eye - a roll-defined variant whose exact 3-aura search returns 0 listings - is COUNTED in the headline total at a 55c poe.ninja placeholder, and its warning chip CLEARS so it looks like a real price.** Same class as Build 3's R2c-1 (variant 0-match keeps its stale ninja floor), now on the highest-profile variant, at **2.9 % of the total** (55c of 1924.6c, ~0.44 div) - **headline-visible** (15.5 -> ~15.1 div if corrected), vs Build 3's invisible 0.11 %. Contradicts D-0019 ("floor is a PLACEHOLDER, not its price"; "unmatchable -> link + no number") and the core "never a misleading number" guardrail. Directly inconsistent with the 3 genuine rares here that 0-match and are correctly excluded, and with **Bubonic Trail** (a variant with no placeholder that priced correctly). | `detail`: Watcher's Eye `method:"extension", tf:0, stage:nobuyout, chaos:{55,55,55}`; `totals()` at min = `priced 28, included 26` -> removing Watcher's would give included 25 / min 1869.6c, so its 55c **is** in the 1924.6c total; post-scan `chip:null` (cleared); root cause §4A |
| R2d-2 | minor | **Zero-match rows mislabelled.** 3 rares (Golem Trap, Armageddon Star, Luminous Curio) render chip **"no buyout among 0 listings - 0 fetched, 0 without a buyout"** with note **"listings exist but none had a buyout price [search 200, 0 fetched, 0 w/o buyout]"** - self-contradictory (chip says 0 listings, note says "search 200"; `total_found=0`). **4th confirmation** (Builds 1/2/3). | chip + note strings captured from `detail`; `total_found:0` on all three |
| R2d-3 | minor | **Raw per-row `ms` is chunk-cumulative, not per-item.** **4th confirmation** - and the sharpest yet: **9.3x** (Cluster of the Brute raw 35 441 / honest 3 810), and this build the raw instrument **mis-ranks** the scan (names Brute the most-expensive row when Watcher's Eye actually was). Degrades the D-0020 hard-criterion (a) field; the in-page observer is the working corrected reference. | §1a raw-vs-honest columns; `background.js` sets the whole chunk to `"scanning"` at dispatch so later-in-chunk rows inherit predecessors' time |
| R2d-4 | minor | **8 magic rows burned on generic matches (worst instance of the campaign).** Five flasks + three small-cluster jewels each matched the 10 000-result generic cap and priced to a 0.066c floor - **~26 s (~38 % of wall-clock)** for ~0.5c of total value. The **3 cluster jewels' notable-roll value is entirely ignored** by the generic magic match (a magic small-cluster with a good notable can be worth real chaos). Confirms R2-3/R2b-3/R2c-4 at 8x the item count. | 8 magic rows `tf:10000, chaos:0.066, done`; §1a |
| R2d-5 | obs `[D-0015]` | **Strict all-affix default -> 0 of 3 rares priced** (all 0-match). Worst rare yield of the four R2 builds (B3 was 8/11). **By design** (D-0015 owner veto); the 3 rows correctly offer the affix picker for manual relaxation. | 3 rares `tf:0, nobuyout`; no auto-relax |
| R2d-6 | obs | **Tier selector inert on this build** (min=median=high=1924.628c; headline 15.5 div at all three tiers; 0 rows move). **Correct, not a regression:** no *included* row carries a min!=high distribution - the only rows that would (the 3 rares) all 0-matched, and everything else is flat (economy single-values, magic 0.066, Bubonic 1.0, Watcher's 55 placeholder). Build 3 already proved the selector moves the headline when a distribution exists. | `tierAudit`: `headlineMoved:false, tripleHasSpread:false, movedRows:0`; min triple all 1924.628 |

No **blocker** (fruition reached twice, nothing stuck/errored). **One major** (R2d-1). No crash in the
product; every priced number except the Watcher's Eye placeholder is sane and source-backed.

---

## 3. UI-truthfulness audit (the R2 lens)

All PASS except where a finding is cited.

- **Extension-active badge:** lit within ~2.5 s of load; text **"extension active - v1.2.1"**;
  `state.bridge = {active:true, version:"1.2.1"}`. PASS.
- **Defaults on an untouched profile:** auto-scan-on-load **ON**, pick-affixes **OFF**, weapon-swap
  **excluded**, tier **min**, listings **"Instant Buyout and In Person"** (D-0017). PASS - zero clicks
  to set up (confirmed on both runs).
- **Progress bar counts monotonic:** `scanning N/13` climbed 2 -> 4 -> 5 -> 6 -> 8 -> 9 -> 11 -> 12 ->
  (13) with no regression; `done` non-decreasing; the bar's current-item name always matched
  `scanStatus().current` (it correctly held **"scanning 11/13 - Watcher's Eye"** through the entire
  27.9 s back-off rather than freezing or skipping). `monotonic = {ok:true, violations:[]}`. PASS.
- **Chips match `scanStatus` stages:** every rendered chip derives from and agrees with the row's
  `status[k].stage`. The only issue is the *copy* of the zero-match chip (R2d-2) and the fact that
  Watcher's Eye's chip **clears** once it has the placeholder number (compounding R2d-1) - not a stage
  mismatch. PASS (with R2d-1/R2d-2).
- **Totals climb as prices land:** `0 -> 1924.1c (+5 s, 16 economy items + first rows) -> 1924.166 ->
  1924.364 -> 1924.496 -> 1925.562c` (final). `totalsMonotonic = {ok:true, violations:[]}` - no dip.
  (The climb is tiny because the 13 scanned rows are nearly all cheap - the economy uniques/gems
  dominate the 1924c base.) PASS.
- **Tier flip MIN -> MEDIAN -> HIGH:** headline `#btVal` = **15.5 div at all three tiers**; triple
  `1924.628 / 1924.628 / 1924.628c` (no spread); 0 rare rows move. **Correct-inert** for this build
  (R2d-6) - faithfully shows no spread because no priced row carries a distribution. Banner
  screenshots captured at MIN and HIGH (identical, as expected). *(Build 3 moved 269 -> 277 div; this
  build has nothing to move - the selector is honest either way.)*
- **Variant rows show labels:** **PASS - both, and richer than any prior build.** Watcher's Eye renders
  the full roll-variant tag **"affected by Determination, Grace, Purity of Ice"** (the 3 auras its mods
  key on); Bubonic Trail renders the socket-count tag **"1 Abyssal Sockets"**. Both with the lock
  glyph. See §4B V1/V2 for the query-lock proof.
- **Swap items absent from the rares list (default):** PASS - **both** `Silverbranch, Crude Bow`
  (Weapon swap) and `Replica Maloney's Mechanism, Ornate Quiver` (Off-hand swap) are excluded
  (`included=26` of `priced=28`), absent from the 13-row scan set and the manual list; they render on
  the board's swap slots only.
- **Weapon-swap toggle re-includes:** **PASS - stronger than Build 3 (two items).** Checking "weapon
  swap" -> `includeSwap()=true`, `included 26 -> 28` (**both** swaps), `min 1924.628c -> 1936.228c`
  (**+11.6c = Silverbranch 1.0c + Replica Maloney's 10.6c, exactly** the sum of both economy values).
  No runaway re-scan (`scanActive` stayed false - the `autoFired` per-build guard held). Manual/rares
  list stayed **13 -> 13** (both swaps are economy-priced uniques, not scannable rares). Note
  Silverbranch is itself a `unique-ninja-variant` in a swap slot - excluded-by-default correctly
  wins over the variant flag.

---

## 4A. Detailed findings

### R2d-1 (MAJOR) - the marquee Watcher's Eye 0-matches yet is counted at a 55c placeholder

**What happens.** Watcher's Eye is a D-0019 **roll-defined** variant: at load it gets a poe.ninja
name-level floor (`unique-ninja-floor`, 55c) that D-0019 explicitly calls **"a PLACEHOLDER, not its
price"**, and `needsScan()` flags it for an exact-mod trade search. That search ran hands-free and -
this is the positive half - **correctly locked all three roll mods** (§4B V2), including the boolean
one. It returned **`total_found = 0`** (no listing of a Watcher's Eye with *exactly* those three
Determination/Grace/Purity-of-Ice rolls at/above the build's values). The correct outcome per D-0019 is
"unmatchable -> link + no number" - exactly how the 3 genuine 0-match rares here resolve, and how
Bubonic Trail (a variant with no placeholder) would have. Instead **the row keeps the 55c placeholder,
renders it as its price, is counted in the headline total, and its warning chip clears.**

**Root cause (traced through the source, same as Build 3 R2c-1 - unchanged code).**
1. `foldBatch`'s `amount==null` branch calls `applyPrice(key, {method:"extension", ..., total_found:0
   /* NO chaos */}, {include:false})`.
2. `applyPrice` does `merged = Object.assign({}, cur, patch)` - the patch has **no `chaos`**, so
   `merged.chaos` **retains the load-time ninja placeholder** `{min:55, median:55, high:55}`.
3. The include gate is `if (opts.include) ...; else if (!(key in state.enabled)) ...`. The row was
   **already** `state.enabled = true` from its load-time economy price, so the `{include:false}` patch
   is a **no-op** - the row stays included.
4. `method` is now `"extension"` (not `unique-ninja*`), so `needsScan()` returns false - the row is
   "finished" and never re-flagged.
`totals()` then sums the placeholder. **Confirmed by the counts:** at min tier `priced=28, included=26`;
the only two excluded are the swaps, so Watcher's Eye is among the included 26. Excluding it (as the 3
rares are) would give `included=25, min=1869.6c`; the observed `min=1924.6c` **includes** the 55c.

**Impact.** On THIS build the magnitude is **material and visible**: 55c of 1924.6c = **2.9 %**, ~0.44
div, enough to move the rendered headline from 15.5 to ~15.1 div. The **class** is worse than the
number: a variant whose name-level floor is high but whose specific roll is unlisted (Watcher's Eyes
vary 10x-100x by which auras/mods they carry - a name-level floor is nearly meaningless for them)
injects an arbitrary number into the total, and post-scan the failed row is **indistinguishable from a
real price** (chip cleared, no "floor / not the variant price" signal). This is the campaign's clearest
instance of the "never a misleading number" guardrail breaking, and it contradicts Locked D-0019.

**Fix options (unchanged from Build 3, now with a higher-value repro to justify it).**
- *Targeted:* in `foldBatch`'s `nobuyout`/`error` branches, when the row is a variant unique (prior
  `method` was `unique-ninja*` / `state.priced[key].variant`), pass an explicit
  `chaos:{min:null,median:null,high:null}` **and** force `state.enabled[key]=false`, so it falls back
  to link-only exactly like a 0-match rare / like Bubonic Trail would.
- *Root-cause:* make `applyPrice` honor `opts.include===false` as an **explicit exclusion** for
  non-cache overrides (branch on an `opts.explicit` flag so a passive cache-fill keeps its current
  behaviour).
- Either way the picker/row needs a visible "floor - not the variant's price" marker if the owner
  prefers keeping a floor over "no number".

### R2d-2 (minor) - zero-match rows mislabelled (4th confirmation)
The strict all-affix default (D-0015) returned no buyout for the 3 rares (Golem Trap, Armageddon Star,
Luminous Curio). The rendered chip **"no buyout among 0 listings - 0 fetched, 0 without a buyout"** and
note **"listings exist but none had a buyout price [search 200, 0 fetched, 0 w/o buyout]"** are
mutually contradictory (chip: "0 listings"; note: "search 200"; `total_found`: 0) and self-negating
("no buyout among **0**", "**0** without a buyout"). Filed identically by Builds 1/2/3 -> firmly a
**class bug** in the `foldBatch` `amount==null` copy. **Fix hint:** branch on `res.total === 0` ->
distinct copy (e.g. *"no listings match all N affixes (exact-affix search)"* + open-search link),
separate from the genuine `total>0 & amount==null` case, and reconcile the "search 200 / 0 fetched /
tf 0" internal accounting.

### R2d-3 (minor) - raw per-row `ms` is chunk-cumulative (4th confirmation; sharpest)
Same mechanism as R2-2/R2b-2/R2c-3: a chunk of 3 is all set to `"scanning"` at dispatch before the
extension prices them serially, so later-in-chunk rows inherit predecessors' time. Here the raw
instrument reports **Cluster of the Brute at 35 441 ms** (honest **3 810 ms**, **9.3x**) and, because
Brute's chunk followed Watcher's 27.9 s back-off, the raw column **mis-ranks the scan** - it names
Brute the most-expensive row when the actually-most-expensive row was Watcher's Eye (27 871 ms honest).
The in-page `scanstatus` observer (this driver) is the working corrected reference. **Fix hint:** stamp
`t0` on the row's own first `searching` event (the extension already emits it per-item).

### R2d-4 (minor) - 8 magic rows burned on generic matches (worst instance)
All 8 magic items (5 flasks + 3 small-cluster jewels) were live-scanned, each matched the 10 000-result
generic cap, and priced to a 0.066c floor - **~26 s (~38 %) of the 67.6 s scan** for ~0.5c of value.
The three **small-cluster jewels** are the notable twist: a magic small cluster's worth is its rolled
notable, which the generic magic match ignores entirely (it prices them the same 0.066c as a white
flask). Confirms R2-3/R2b-3/R2c-4 at 8x the item count. **Fix hint (design, defer to owner):**
floor-price flasks from the economy / skip them from autoscan; price magic cluster jewels by their
notable (they are the one magic class that carries real value).

### R2d-5 (observation, by-design under D-0015)
Downstream of locked D-0015 (autoscan stays strict-all-affix). 0 of 3 rares priced (all 0-match) - the
worst rare yield of the four R2 builds. The 3 no-match rares correctly offer the affix picker for
manual relaxation. **Not a bug** - the documented tradeoff, and a reminder that this build's headline
leans almost entirely on economy-priced uniques/gems (the scan barely moves the total).

### R2d-6 (observation) - tier selector correctly inert
Covered in §3 / §2. min=median=high because no included row has a distribution; the selector faithfully
shows no spread. Build 3 proved it moves when a distribution exists, so this is composition, not
regression.

## 4B. Positive validations (all PASS)

| # | Feature (decision) | Result on this build |
|---|---|---|
| V1 | **D-0019 socket-count variant - NEW sub-case (Bubonic Trail)** | Identified as a `socket-defined` "count variant" and searched **with the socket-count locked**: the built `trade_query` carries required filter `explicit.stat_3527617737` `value:{min:1,max:1}` (exactly 1 abyssal socket). It **matched real listings (`tf:2876`) and priced 1.0c** at stage `done`, tag **"1 Abyssal Sockets"**. This is the **control that proves R2d-1 is a bug, not the design**: a variant with no ninja placeholder resolves to a real trade price or nothing - it does not invent a number. |
| V2 | **D-0019 roll-defined variant lock - 3 mods incl. a boolean (Watcher's Eye)** | The built `trade_query` correctly emitted **all three** roll mods as required filters: `explicit.stat_68410701 {min:53}` (reduced crit extra dmg while affected by Determination), `explicit.stat_4071658793 {min:14}` (Suppress while affected by Grace), and the **value-less boolean** `explicit.stat_2647344903 value:null` (Unaffected by Chilled Ground while affected by Purity of Ice) - the last correctly emitted as a presence filter with no min. Variant identification + full multi-mod lock (the hard half of D-0019) **works**; only the 0-match *fallback* is R2d-1. |
| V3 | **Two-item weapon-swap SET exclude + toggle (D-0018)** | Both Silverbranch (Weapon swap) and Replica Maloney's (Off-hand swap) excluded by default (`included=26`); the toggle re-includes **both** (`included=28`, `min +11.6c` = exact sum of the two economy values 1.0c + 10.6c), no runaway re-scan (`scanActive` stayed false), manual list unchanged 13->13. Stronger than Build 3's single swap. |
| V4 | **Rate-limit back-off shown as an honest live countdown (D-0018)** | The 27.9 s window pause on Watcher's Eye held the progress bar at **"scanning 11/13 - Watcher's Eye"** and kept the row's chip live rather than freezing; the wait resolved hands-free and the row terminated. `scanStatus().waitUntil` drives it. |
| V5 | **Untouched-profile defaults + clean console (twice)** | autoscan ON, pick-affixes OFF, swap OFF, tier min, listings "Instant Buyout and In Person" - all correct, zero clicks; **0 console messages, 0 pageerrors across BOTH full runs**. |
| V6 | **Repeatable hands-free fruition** | Two independent hands-free scans completed to 13/13 terminal at 67.5 s / 67.6 s (0.2 % apart), 0 stuck / 0 error both times. Fruition is robust, not a one-off. |
| V7 | **Monotonic progress + totals climb** | `monotonic {ok:true}`, `totalsMonotonic {ok:true}` - no bar regression and no totals dip on either run, including across the 27.9 s back-off. |

**Economy-price sanity (source `poe.ninja`, for the "no misleading number" check):** the 1924.6c base
is dominated by economy-priced uniques/gems - all plausible for the league (e.g. Victario's Influence
`unique-ninja-range` 1/33/102.6c, Ventor's Gamble, Alpha's Howl, The Dark Seer, etc.) plus 7 gems.
Bubonic Trail 1.0c (real match) and the 8 magic 0.066c floors are sane. The **only** misleading number
is the Watcher's Eye 55c placeholder (R2d-1).

---

## 5. Console / pageerror capture

- **`pageerror` count: 0** (both runs).
- **`console.error` / `console.warning` count: 0** - in fact **0 total page-console messages** on both
  runs.
- No failed-bridge fallback, no timeout chunks, no page-side 429. The 27.9 s rate-limit back-off was
  handled entirely by the extension's service-worker limiter and surfaced to the page **only** as the
  honest `waiting`/countdown progress event (§4B V4) - no error reached the page, no row hit stage
  `error`. The bridge, the chunked scan (incl. both variant exact-mod searches), the cache POSTs, and
  the tier/swap controls all ran without a single page-side error.

*Capture limitation (noted for honesty):* the extension's rate-limit decisions live in the MV3 service
worker, which the page-side console cannot see; the 27.9 s pause was reconstructed from the
`scanstatus` `waiting`/`waitUntil` events (which the page *does* receive) and the observed search-gap
series. The exact triggering window is **[INFERRED]** - not distinguishable from page-side capture; the
~27.9 s magnitude and the "rate limit" chip label are the source-derived facts.

---

## 6. Method / reproduction (incl. the auditor-harness bug + re-scan honesty)

1. Playwright `chromium.launchPersistentContext(r2profile4, {headless:false, viewport:1280x900,
   args:['--disable-extensions-except=<ext>','--load-extension=<ext>','--no-first-run',
   '--no-default-browser-check']})` - extension `v1.2.1` from `C:\scripts\buildpricechecker-poe1\
   extension`.
2. `goto https://divtally.com/?v=r2-4`; confirm `#bridgeBadge.on` + defaults; install the in-page
   `bpc.on('scanstatus')` observer; **no clicks**.
3. `fill('#url', <build>)` + `press('#url','Enter')` - the single sanctioned interaction.
4. Poll `bpc.scanStatus()` every 5 s (cap 10 min) until `active===false` && every row terminal.
5. Post-scan audit: observer honest per-item timings; per-row detail incl. each item's built
   `trade_query` stat filters (the variant-lock proof); variant tags; screenshot banner at MIN; click
   `#btSeg [data-tier=median]` then `[high]`, read `#btVal` + per-rare row prices; screenshot banner
   at HIGH; `check('#swapInc')` and re-read totals/included counts.
6. All readings dumped to `r2_results4.json`; browser closed in a `finally`.

**Auditor-harness bug (transparency):** on the **first** run the *product scan completed cleanly and
hands-free* (13/13 terminal, `totalMs 67 496 ms` - the fruition + timing criteria were met and are
recorded in `r2_results4_run1.json`), but my post-scan instrumentation crashed - I passed the `DETAIL`
probe to `page.evaluate` as a **string** (evaluated as an expression, so the function object was
returned unserialized -> `undefined`) instead of a real function, so `detail.rows` threw. This is a bug
in **my driver**, not the product. I fixed it (real arrow function, `extractStats` inlined) and re-ran
**once** to capture the post-scan audit (tier flip, swap toggle, query-lock proof) that requires a live
priced page. Both runs completed hands-free identically, which is why this report can cite two
independent fruition measurements.

**Trade footprint:** exactly **two** hands-free scans (13 search POSTs + fetches each, all by the
extension under its own limiter; the 3 zero-match rares + Watcher's Eye fetched nothing after their
searches). This used **1 full scan + 1 targeted re-scan of the budgeted 2** (1 re-scan remains unused).
No direct pathofexile.com calls by the auditor.

---

## 7. Cross-round note (for the campaign owner)

- **Three prior findings now reproduce a FOURTH time -> rock-solid class bugs:** R2d-1 (== R2c-1,
  variant 0-match counted at a stale ninja placeholder), R2d-2 (== R2-1/R2b-1/R2c-2, zero-match copy),
  R2d-3 (== R2-2/R2b-2/R2c-3, chunk-cumulative raw `ms`). **R2d-1 is now the priority:** Build 3 hit it
  at 0.11 % (invisible); Build 4 hits it at **2.9 %, headline-visible, on the single most iconic
  variant unique in the game** (Watcher's Eye), and the failing row's chip **clears** so it hides in
  plain sight. R2d-3 degrades the D-0020 hard-criterion (a) instrument itself and now mis-ranks a scan.
  **Recommend fixing R2d-1 (variant 0-match -> link-only + a floor marker) and R2d-3 (per-item `t0`)
  before further rounds lean on these numbers.**
- **The R2d-1 fix is now well-bounded** by having its own control in the same build: **Bubonic Trail**
  (variant, no placeholder) priced correctly to a real trade match (V1), proving the desired behaviour
  is "resolve to a real price or nothing, never invent a floor." The fix should make Watcher's Eye
  behave like Bubonic-on-a-miss (link, no number), not like Bubonic-on-a-hit.
- **Positively validated for the first time this round:** the **socket-count** D-0019 sub-case (V1),
  the **roll-defined 3-mod lock incl. a boolean mod** (V2), a **two-item weapon-swap set** re-including
  to the exact economy sum (V3), and **repeatable** hands-free fruition (V6).
- **Coverage still open for later rounds** (per D-0020 "different tests each round"): a **PoB-code
  input** (browser paste path, still unexercised in R2), a build that actually **prices multiple rares
  with distributions** through the picker's manual-relax path (to exercise R2d-5's left-on-the-table
  yield), and a **6-link / high-value corrupted unique**. R4/R5 territory.
