# R2 - Consolidated judgment (Builds 1-4) + adversarial UX audit

**Round:** 2 (browser UI via Playwright + the real extension v1.2.1 on `https://divtally.com`) of the
D-0020 five-round campaign. **Inputs:** `docs/bugtest/r2-build1..4.md` (the four drive reports).
**Scope of this doc:** consolidation + adversarial judgment only. No browser work, no trade traffic
was performed to produce it. Load-bearing source claims (F1 root cause, F3 mechanism, F2 copy) were
re-verified read-only against the deployed `public/site/assets/core.js` - see the CONFIRMED tags.

Provenance: every number is copied from a drive report's source-derived reading unless tagged
`[DERIVED]` (a judge-side calculation from those readings) or `[INFERRED]`.

---

## 1. Cross-build TIMING SUMMARY

Median per-item ms is the **honest** per-item figure: an in-page `scanstatus` observer for Builds 3-4;
the intra-chunk **incremental** derivation for Builds 1-2 (which lacked the observer). Both approximate
the same thing - the raw `scanStatus().ms` field is chunk-cumulative and unusable (Finding F3).

| Build | Char | Rares scanned (priced / 0-match) | Rows scanned | totalMs | Median honest per-item | % in rate-waits `[DERIVED]` | Big window back-off |
|---|---|---|---|---|---|---|---|
| 1 `qwartus` | Occultist | **9** (1 / 8) | 12 = 9r + 3 magic | **63.8 s** | 3 466 ms | **~88-90%** (norm.) | yes - ~24-28 s tail, on a magic flask |
| 2 `Sergohero` | Deadeye | **6** (3 / 3) | 9 = 6r + 2 magic + 1 variant | **28.6 s** | 3 423 ms | **~90-92%** | none (rode the floor) |
| 3 `f1fti` | - | **11** (8 / 3) | 14 = 11r + 1 magic + 2 variant | **71.0 s** | 3 514 ms | **~95%** | yes - 28.3 s mid-scan |
| 4 `yalokk` | Champion | **3** (0 / 3) | 13 = 3r + 8 magic + 2 variant | **67.6 s** | 3 623 ms | **~93%** | yes - 27.9 s on Watcher's Eye |

Pacing floor is source-derived on every build: `background.js` `spacing = ceil(10000 / effectiveCap(5))
= 3.33 s` between searches (GGG's `[5,10]` search window). The `[DERIVED]` % is wait vs active-HTTP,
computed from each report's clean first-search round-trip (0.25-0.87 s) and its observed inter-search
gap series; it is not a directly instrumented per-stage timer (the product emits none - that gap is
itself Finding F3).

### Verdict: durations are fully explained by the limiter. The only "waste" is scan SCOPE, not the engine.

1. **Median per-item = 3.42-3.62 s on all four builds = the ~3.33 s pacing quantum.** Every scan is
   `>=~88-95%` limiter wait and `~0%` compute/parse (clean first-search round-trips were 0.25-0.87 s).
   The scans are rate-limiter-bound by construction, exactly as the load-bearing rate discipline
   requires. This is correct behavior, not slack.
2. **No unnecessary re-searches.** Exactly one search per scannable row on every build (12/12, 9/9,
   14/14, 13/13). Zero-match rows correctly skip the fetch; priced rows do 1 search + 1 fetch batch.
   No redundant trade calls were observed on any build.
3. **No chunk-boundary idle.** Despite the chunk-of-3 dispatch (`core.js` `CHUNK=3`), searches fire
   **continuously** at the ~3.33 s floor across chunk boundaries - the Build 3/4 gap series show no
   systematically larger gap at every 3rd search. Fetch latency is hidden under the search pacing
   (interleaved at the cheaper fetch spacing). The chunk structure corrupts the timing **instrument**
   (F3) but adds **zero wall-clock**.
4. **The big ~24-28 s stalls (Builds 1, 3, 4) are genuine GGG window back-offs**, not product hangs -
   they land at ~search 11 once the short windows saturate, and surface honestly as a live countdown
   (validated V4). Build 2 avoided one **purely by search order** (its two 10k-result flasks landed at
   positions 1-2, before saturation). Order-dependence, not inefficiency.
5. **The one real efficiency lever is scan SCOPE (Finding F4), and it is a design choice, not a limiter
   defect.** Because each scan is pacing-bound, every scanned row costs ~one 3.33 s quantum of
   wall-clock regardless of its value. Live-scanning magic flasks/clusters that can only resolve to a
   ~0.066c floor therefore burns **5% (B3, 1 row) -> 23% (B2) -> 38% (B4, 8 rows = ~26 s)** of scan
   wall-clock for ~0.5c of value. In Build 1 a **tail-positioned** magic flask also triggered the
   ~24 s window back-off that dominated that scan - so magic scope both wastes quanta *and* can provoke
   the back-offs. Cutting magic from the scan would cut wall-clock roughly proportionally and reduce
   window saturation. This is an owner/design call (D-0015 neighborhood), tracked as F4, not a bug in
   the pacing.

**Bottom line:** no evidence of engine waste (no re-searches, no chunk gaps, no compute cost). The
elapsed time is the limiter doing its job. The only lever worth pulling is *what gets scanned* (magic
rows), which is F4 and the owner's call.

---

## 2. FRUITION verdict (per build)

The D-0020 hard criterion (b): scans to completion, **zero intervention**, no row stuck non-terminal.

| Build | Auto-start | Rows terminal | Stuck / error | Console / pageerrors | Hands-free? |
|---|---|---|---|---|---|
| 1 `qwartus` | +5.0 s, 0 clicks | **12 / 12** | 0 / 0 | 0 / 0 | **PASS** |
| 2 `Sergohero` | +5.0 s, 0 clicks | **9 / 9** | 0 / 0 | 0 / 0 | **PASS** (timeless jewel priced itself) |
| 3 `f1fti` | +5.0 s, 0 clicks | **14 / 14** | 0 / 0 | 0 / 0 | **PASS** (28.3 s back-off self-resolved) |
| 4 `yalokk` | +5.0 s, 0 clicks | **13 / 13** (x2 runs) | 0 / 0 | 0 / 0 | **PASS x2** (27.9 s back-off self-resolved) |

**All four builds reached full hands-free fruition with zero stuck rows and a clean console.** Every
build auto-started at +5.0 s on an untouched profile (auto-scan ON, pick-affixes OFF, swap OFF, tier
min, "Instant Buyout and In Person" - all correct with no clicks) after the single sanctioned `Enter`.

- The three large window back-offs (B1/B3/B4) each **resolved themselves** hands-free with an honest
  decrementing countdown; no row ever hit stage `error`, and the progress bar held the current item
  through the wait rather than freezing (V4).
- **Build 4's re-scan is not a product defect.** Run 1's *product* scan completed hands-free (13/13,
  67.5 s); the re-scan recovered a post-scan audit lost to an **auditor-harness** bug (a `page.evaluate`
  passed a string instead of a function). Both runs reached identical fruition (67.5 / 67.6 s), which
  is corroborating evidence, not a fruition failure. No fruition regressions anywhere.

**Hard-criterion (a)** (scan-duration audit produced) is also PASS on all four - though note the raw
instrument is itself buggy (F3); Builds 3-4 produced the audit via a corrected in-page observer.

---

## 3. Deduped, ranked findings

Five unique findings survive dedup across the four reports (the reports filed 22 numbered items;
17 are duplicates of these five). Ranked most-severe first. Verdicts: **CONFIRMED** = root cause traced
to deployed source and/or reproduced on multiple builds; **PLAUSIBLE** = single-build, evidence-consistent
but not source-verified.

### F1 - MAJOR - a 0-match **variant unique** is counted in the headline total at its stale poe.ninja placeholder `[CONFIRMED]`
**Merges:** R2c-1 (Build 3) + R2d-1 (Build 4). Reproduced on **2 builds**; root cause verified verbatim
in `public/site/assets/core.js`.
A D-0019 variant unique (Forbidden Flame/Flesh; Watcher's Eye) gets a poe.ninja name-level **placeholder**
at load, then its exact locked-mod search returns `total_found = 0`. Instead of falling back to
link-only (as the 3 genuine 0-match rares do, and as Bubonic Trail - a variant with **no** placeholder -
correctly does), the row **keeps the placeholder, renders it as its price, stays `included`, and its
warning chip clears** so the failed row is visually indistinguishable from a real price.
- **Source-confirmed root cause:** `foldBatch` `res.amount==null` branch (core.js:795-798) calls
  `applyPrice(..., {include:false})` with **no `chaos`** in the patch. In `applyPrice`,
  `merged = Object.assign({}, cur, patch)` (core.js:450) then `if (patch.chaos)` is skipped (451), so
  `merged.chaos` **retains the load-time ninja placeholder**. The include gate (458-459) is
  `else if (!(key in state.enabled))`, which is **false** for a row already enabled from its load-time
  economy price -> `{include:false}` is a **no-op** -> the row stays counted. `totals()` sums it.
- **Corroborating arithmetic (Build 4):** `priced=28, included=26`; removing Watcher's Eye gives
  `included=25, min=1869.6c`; observed `min=1924.6c`; `1924.6 - 55 = 1869.6` -> the 55c **is** in the total.
- **Magnitude:** Build 3 = 37.8c / 33 362c = **0.11%** (invisible); Build 4 = 55c / 1924.6c = **2.9%**,
  ~0.44 div, **headline-visible** (15.5 -> ~15.1 div). The **class** is unbounded: a variant whose
  name-floor is high but whose specific roll is unlisted injects an arbitrary number.
- **Contract breach:** contradicts Locked **D-0019** ("floor is a PLACEHOLDER, not its price";
  "unmatchable -> link + no number" - the exact words are in the code comment at core.js:867) and the
  core **"never a misleading number"** guardrail. Inconsistent with the genuine 0-match rares in the
  same builds.
- **Fix:** in `foldBatch`'s `nobuyout`/`error` branches, when the row is a variant unique, pass explicit
  `chaos:{min:null,median:null,high:null}` **and** force `state.enabled[key]=false` (link-only, like a
  0-match rare / like Bubonic-on-a-miss); or make `applyPrice` honor `opts.include===false` as an
  explicit exclusion for non-cache overrides. If the owner instead prefers keeping a floor, the row
  needs a visible "floor - not the variant's price" marker AND D-0019's text + the rare 0-match handling
  must change to match. **Owner may reclassify only by changing D-0019.**

### F2 - minor - zero-match rows show self-contradictory "no buyout among 0 listings" copy `[CONFIRMED]`
**Merges:** R2-1 + R2b-1 + R2c-2 + R2d-2. Reproduced on **all 4 builds** -> class bug; source-confirmed.
When `total_found = 0`, the chip reads **"no buyout among 0 listings - 0 fetched, 0 without a buyout"**
and the note **"listings exist but none had a buyout price [search 200, 0 fetched, 0 w/o buyout]"** -
describing the empty set, and internally contradictory (chip "0 listings" vs note "search 200").
- **Source-confirmed:** core.js:797 applies the note "listings exist but none had a buyout price"
  **unconditionally** in the `amount==null` branch, which fires for both `total=0` and
  `total>0 & no-buyout`. No branch on `res.total===0`.
- Hits the **D-0020 UI-truthfulness** criterion and the owner's standing **"no buyout everywhere"**
  sensitivity (**D-0012**). **Compounds F1** for the variant rows (Build 3: keeps a number *and*
  mislabels the reason). User-facing (the chip is rendered), which is why it ranks above F3.
- **Fix:** branch on `res.total === 0` -> distinct copy, e.g. *"no listings match all N affixes
  (exact-affix search)"* + open-search link, separate from the genuine `total>0 & amount==null` case;
  reconcile the "search 200 / 0 fetched / tf 0" internal accounting.

### F3 - minor - raw per-row `ms` is chunk-cumulative, not per-item (degrades the audit instrument) `[CONFIRMED]`
**Merges:** R2-2 + R2b-2 + R2c-3 + R2d-3. Reproduced on **all 4 builds** -> class bug; source-confirmed.
`scanStatus().status[k].ms` stamps `t0` at **chunk dispatch** (all 3 keys set to `"scanning"` at once),
so later-in-chunk rows inherit predecessors' search+fetch+wait. Overstatement reaches **9.9x** (Build 3
row 7: 34 901 raw / 3 515 honest) and **9.3x** (Build 4), and on Build 4 the raw field **mis-ranks the
scan** - it names Cluster of the Brute the most-expensive row when Watcher's Eye actually was.
- **Source-confirmed:** core.js:739 `if (s.t0 == null && stage !== "queued") s.t0 = Date.now();` +
  core.js:858 `keys.forEach(k => scanSet(k, "scanning"))` sets the whole chunk at dispatch, before the
  extension prices serially. Honest per-item is 3.1-3.9 s for every row on every build.
- **Not user-facing** (the progress bar and chips are correct/monotonic; only this telemetry field is
  wrong) - but it **degrades the D-0020 hard-criterion (a) instrument itself**, so it is the highest-value
  minor to fix before further timing rounds lean on the number. The extension already emits a per-item
  `searching` event (the observer Builds 3-4 tapped is the working reference), so the fix is cheap.
- **Fix:** stamp `t0` on the row's own first `searching` progress event, or record per-stage durations.

### F4 - minor - magic flasks/clusters are live-scanned for a foregone ~0.066c floor `[CONFIRMED]`
**Merges:** R2-3 + R2b-3 + R2c-4 + R2d-4. Observed on **all 4 builds**; quantified.
Each magic row matches the 10 000-result generic cap, spends a full ~3.33 s pacing quantum, and prices
to a uniform ~0.066c floor. Worst instance Build 4: 8 magic rows (5 flasks + 3 small-cluster jewels) =
~26 s = **~38% of wall-clock** for ~0.5c of value. The generic magic match also **ignores the rolled
notable on magic small-cluster jewels** - the one magic class that can carry real chaos - so those are
mildly *under*priced to floor (an accuracy gap, though tiny in totals). This is the main scan-duration
efficiency lever (see Section 1, point 5).
- **Fix (design, defer to owner):** floor-price magic flasks from the economy / skip them from autoscan;
  price magic cluster jewels by their notable. Low totals impact either way.

### F5 - nit (minor) - "rares to price yourself" header count reads as an off-by-one `[PLAUSIBLE]`
**Source:** R2b-5 (Build 2 only); screenshot-based, reconcilable, not source-verified.
Header "**8** rares to price yourself" vs a **9**-row RARES-TO-PRICE list vs sub-header "**3** still need
a price." All internally consistent (the 8 excludes Lethal Pride - a *unique* that also appears as a
scannable seed-priced row; the 3 = zero-match rows), but the naked 8-vs-9 can momentarily confuse.
- **Fix:** count the variant/timeless unique in the "to price yourself" figure ("9"), or label it
  separately ("8 rares + 1 variant unique").

---

## 4. By-design observations (NOT findings - recorded for the owner)

- **O1 [D-0015] Variable rare yield under the strict all-affix default.** Priced rares: B1 1/9, B2 3/6,
  B3 8/11, B4 0/3. The no-match rows correctly offer the affix picker for manual relaxation. Merges
  R2-4/R2b-4/R2c-5/R2d-5. Working as the owner specified - not a bug.
- **O2 [D-0016 #4] Tier selector inert on some builds** (B1, B4) because no *included* row carries a
  `min!=high` distribution - composition, not code. Positively **proven** to move the rendered headline
  on B3 (269 -> 277 div) and move a row on B2 (Kraken 1c -> 7c). Merges R2-5/R2d-6. Not a bug.
- **O3 [D-0015] Conf-low single-listing prices enter the headline at full weight** (B2 Hypnotic Ruin
  873.6c from 1 listing). A real listing, correctly badged low-confidence at the row; the headline
  carries no confidence signal. The reports declined to file it. Owner-decision only.
- **Non-findings** explicitly cleared by the reports: B2's 0.0038c float-sum dip (sub-display,
  reordering artifact); B4's auditor-harness `page.evaluate` bug (auditor-side, not product).

## 5. Positive validations (all PASS across the round)

For completeness: R1's foil/relic-unique fix (Nimis, B2/B3); D-0019 timeless-seed (B2), notable-jewel
(B3), socket-count + roll-defined 3-mod-incl-boolean (B4); currency rates map; weapon-swap exclude +
toggle incl. a 2-item set (B4, re-includes to the exact economy sum); gem host-grouping with no GRANTED
mislabel; honest rate-limit countdown; duplicate-name row handling (B3). No positive validation regressed.

---

## 6. Round verdict

**D-0020 hard criteria: PASS on all four builds** - (a) scan-duration audit produced (via the corrected
observer; the raw field is F3), (b) hands-free fruition reached with zero stuck rows and a clean
console. **Zero blockers.** The scans' durations are honestly the limiter's, not the engine's.

**But not a clean bill of health:** one confirmed **MAJOR** correctness/guardrail defect (F1 - a
misleading number in the headline, source-traced, contradicting Locked D-0019, headline-visible at 2.9%
on Build 4's Watcher's Eye) plus four minors. Recommended fix order before R3:
**F1 (variant 0-match -> link-only + floor marker) -> F3 (per-item `t0`, so the campaign's own timing
numbers are trustworthy) -> F2 (zero-match copy) -> F4 (magic scope, owner design call) -> F5 (nit).**
