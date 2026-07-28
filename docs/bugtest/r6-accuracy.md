# R6 - Pricing-accuracy triangulation (are the NUMBERS right?)

Lens: recompute every priced number by hand from the raw poe.ninja economy lines and diff vs
what the code emits. Fresh angle for R6 (the 4 standard lenses R1-R5 are done; R5 found no
functional bugs). Method: **freeze** the economy to the bundled snapshots
(`research/data/ninja_econ_skillgem.json`, `ninja_uniques_*.json`, `ninja_econ_currency.json`),
run the **real** public pipeline (`_lib.poeninja.normalize` -> `PublicPricer.price_build` ->
`response.build_response`) on all **4 owner builds** (freshly fetched to scratchpad) **+** the
example fixture, then independently recompute gems / uniques / totals / divine / rates from the
same raw lines. Distribution math (`core.js`) tested under node against hand fixtures + Python
`util` for byte-parity.

Harnesses (scratchpad): `r6_audit.py` (full reconciliation), `r6_gemgap.py` (gem
substitution/completeness), `r6_dist.mjs` (core.js trim+percentile + currency gap),
`r6_corrupt.py` (ninja-path corruption-flag scan). Offline & deterministic (economy frozen).

## Verdict
The pricing **arithmetic is sound**. Across all 5 builds, every gem-group total, unique
selection, min/median/high sum, and divine figure reconciled **exactly** (to <1e-3 c) against
independent hand recomputation from the raw lines. Two **real but low-impact** defects found,
both in **currency conversion of non-chaos/non-divine listings** (component 3). No blocker/major.

---

## What reconciled EXACTLY (no findings)

| Component | Check | Result |
|---|---|---|
| **1 Gem groups** | per-gem chaos == picked SkillGem line's `chaosValue`; group total == Σ non-granted; support completeness | **EXACT** all 5 builds. Breakdown rows == raw `allGems` (build1 35/35, build2 16/16, build3 16/16, build4 22/22, example 17/17). **0** dropped supports, **0** silent-unpriced non-granted gems, **0** granted-but-priced. |
| **1 Gem bucketing** | 24 "material" bucket substitutions triaged against raw lines | **All data-driven** (poe.ninja lacks the exact L/Q/corrupt bucket); the score `|Δlvl|+0.3|Δq|+100·Δcorr` picks the correct nearest available line in every case. Corruption penalty (100) correctly dominates (never crosses corruption when a same-corruption line exists). **No formula mis-pick.** |
| **2 Uniques** | code `chaos` == the selected raw line for the OWNED link-tier / variant | **EXACT.** 6L->6L (Inpulsa 300, Blunderbore 120.3), 5L->5L (Victario 20), <5L->unlinked (Silverbranch 1, Golden Charlatan 10326), socket-count->owned count (Bubonic Trail "1 Jewel" 1c), token-variant & range paths all correct. |
| **2 Unique confidence** | floors/ranges labelled honestly | floor->`low`, range->`low`, variant->`high` iff `listing_count>=5` else `medium`. Forbidden Flesh/Flame, Watcher's Eye, timeless all `low` FLOOR per D-0019 (counted at low confidence by design). |
| **4 Totals** | Σ over `source=="poe.ninja"`, non-swap, finite tier == `totals.chaos.{min,median,high}` | **EXACT** (build1 1477.700, build2 29858.700, build3 min 28359.850/med 28361.850/high 28365.210, build4 1723.000, example 33114.000). |
| **4 Divine** | `totals.divine == round(chaos/divine_to_chaos, 3)` | **EXACT** (e.g. 1477.7/102.5=14.417; 1723/102.5=16.81). `_sum_tier` ignores `item.count` while `core.js totals()` multiplies by it, but **`item.count` is hardcoded 1 everywhere** (never set from poe.ninja/PoB data) -> divergence is **unreachable**, not a bug. |
| **5 Distribution** | `tiersFromChaos` trim(`[0.30,6.0]×median`)+percentile(90) vs hand fixture; JS vs Python `util` | **EXACT & byte-parity.** Fixture `[1,40,...,110,900]` -> min40/med75/high103/sample8 (1 and 900 trimmed) in both JS and Python. |
| **ninja-path corruption** | L>20/Q>20 gems flagged uncorrupted (would mis-bucket to cheap line) | **0 real gaps.** The 2 hits are L30 *item-boosted* gems (Herald of the Hive = granted/excluded; Generosity L30 = boosted, correctly uncorrupted, correctly priced at the L20 tradeable line). poe.ninja's `corrupted` flag is reliable; R4-1's PoB-only inference isn't needed here. |

---

## FINDING R6-1 (minor) - rates map uses 3 wrong/dead currency ids; Chromatic & Jeweller's never convert
`public/api/_lib/response.py` `_RATE_IDS` (feeds `meta.rates`, the D-0018 client-side
conversion map) contains **`chrom`, `jew`, `chisel`**. None is a valid poe.ninja currency line
id: poe.ninja uses **`chrome`** (Chromatic) and **`jewellers`** (Jeweller's), and does not track
Cartographer's Chisel at all. So `conv.rate("chrom"/"jew"/"chisel")` -> `chaos_by_id` miss ->
these three are **silently omitted** from `meta.rates` (verified: **16 of 19** ids present on all
5 builds; `chrom`/`jew`/`chisel` always absent).

Because the **trade listing** currency ids are *also* `chrome`/`jewellers` (trade `data/static`),
`core.js toChaos("...","chrome")` looks up `rates["chrome"]` -> `undefined` -> not chaos/divine
-> **`null`**: any extension-fetched rare or pasted whisper priced in Chromatic or Jeweller's
Orbs **cannot be converted** and drops from the total/distribution (or shows no number).

- **Reachable:** the project's own R3 live data lists real rares priced in "chrome"
  (`r3-live.md`: "2 chrome"; `r3-reverify1.md`: "1c-2 chrome").
- **Impact: LOW** - Chromatic (~0.05c) and Jeweller's (~0.13c) are near-worthless and almost
  never used to price gear; no owner build is affected. But the D-0018 rates-map fix is partially
  non-functional for two currencies, and ships a dead id (`chisel`).
- **Fix:** `_RATE_IDS` -> use `"chrome"`, `"jewellers"`; drop `"chisel"` (poe.ninja lists no
  such line). One-line, no schema change.

## FINDING R6-2 (minor) - the rare DISTRIBUTION band ignores `meta.rates` (only chaos+divine), contradicting its own "byte-faithful" invariant
`public/site/assets/core.js` `_amtToChaos(amount, currency, rate)` (used by
`rareTiersFromPrices`, the **primary** path that builds an extension-priced rare's
`{min,median,high}` in `foldBatch`) converts **only chaos and divine** - it takes a single
`rate` (the divine rate) and **never consults `meta.rates`**, unlike its sibling `toChaos`
(the single-cheapest fallback, which *does* use the map). Every fetched listing priced in
exalted / mirror / annul / alch / etc. is **silently dropped** from the distribution band.

This violates the function's **own documented invariant** (core.js: *"byte-faithful so an
extension-priced rare gets the SAME {min,median,high} the desktop app would compute from the
same listings"*) - the desktop `bpc/pricing.py _search_listings` converts **every** currency via
`CurrencyConverter.to_chaos` (full poe.ninja rate map) before trim/percentile - and it partially
re-opens the D-0018 "non-chaos/divine listings fall out" issue on the distribution path.

- **Demonstrated** (`r6_dist.mjs`): listings `{chaos,divine,exalted,mirror,alch}` (5) ->
  band `sample=2` (exalted/mirror/alch dropped); an **exalted-only** rare -> `band=null`, so the
  distribution collapses to the single-cheapest point estimate (min==median==high) via the
  `toChaos` fallback (which *does* convert exalted) - the min/median/high spread D-0016 item 4
  was built to provide is lost.
- **The comment reasoning is mistaken:** `_amtToChaos` says *"anything else has no build rate"* -
  but the build **does** carry rates for exalted/mirror/alch/... in `meta.rates`; only this
  function fails to use them.
- **Impact: LOW-to-MODERATE, near-zero in practice** - biases a rare's tiers only when
  exotic-currency listings are among its fetched sample; the current economy prices rares in
  chaos/divine (exalted is 0.72c -> exotic-priced rares are usually dump listings trim removes
  anyway). No owner build is affected. But it's a genuine cross-implementation fidelity gap on
  the tool's primary deliverable.
- **Fix:** thread the rates map into `_amtToChaos` (mirror `toChaos`: `if (rates[c] > 0) return
  amount * rates[c]`), so the band converts the same currencies the desktop app and the
  single-cheapest fallback already do.

---

## Observations (not findings - by-design or data-coverage, no numeric error)
- **Quality gems price off the Q0 line** when poe.ninja lacks the quality bucket (e.g. Sniper's
  Mark Q20 -> Q0 line 3c; Enlighten/Empower Q20 corrupted -> Q0 corrupted line). Systematic small
  underprice (GCP-scale); a data-coverage limit of the SkillGem overview, not a code defect.
- **Distant-bucket substitutions** (e.g. Pact of K'Tash L20/Q20 -> the only line, L1/Q0, 24c;
  Clarity L11 -> L20) are presented at `listing_count`-based confidence with no "approximate
  bucket" signal. Correct nearest available line; a labelling nicety at most.
- **Foulborn / registry range uniques** (Foulborn Esh's Mirror -> `unique-ninja-range`, median of
  3 variant lines) show a range at `low` confidence per D-0019 - correct.

## Files
- Report: `docs/bugtest/r6-accuracy.md` (this file).
- Suspect code: `public/api/_lib/response.py` (`_RATE_IDS`, R6-1); `public/site/assets/core.js`
  (`_amtToChaos`, R6-2).
