# R3 — Picker query-truth audit (offline) + R2 carry-forward (F2–F5)

**Round:** 3 of the D-0020 campaign. **Lens (owner):** query TRUTH — does every search the picker
generates actually describe the item, and does it drop nothing the user didn't drop (D-0015)?
**Method:** fully offline. The REAL deployed `public/site/assets/core.js` was loaded in a Node `vm`
(via `require`, same as `test_picker.mjs`) and driven with **real affix payloads** pulled from our
own `/api/build` for the four banked builds (poe.ninja-backed; **zero pathofexile.com traffic** — no
trade search/fetch/exchange of any kind). Producer behaviour was cross-checked by calling the actual
Python `querybuild` functions on real mod text. Every number below is source-derived (a harness
reading, a real API payload, or a direct code line) unless tagged `[REALISTIC — not in the 4 banked
builds]`.

Builds: `qwartus-3381`, `Sergohero-2699`, `f1fti-6231`, `yalokk-2571` (Allflame). Picker fns exercised:
`rareDefaultPicks · buildRareQuery · tierGroups · applyScope · queryLinks · rareTradeUrl`.

---

## 1. Findings (picker query-truth) — 2 MAJOR

### R3-1 — MAJOR — a variant-DEFINING **resistance** mod is folded into the pseudo total and DROPPED from the picker query `[CONFIRMED]`
The resist-fold in `buildRareQuery` runs **before** the defining-mod branch, so a defining mod that is
also a resistance is skipped and never emitted as its locked filter:
```
core.js:1087   if (usePseudo && a.resist) return;                       // folds ALL resist affixes
core.js:1091   if (a.defining) { if (gi===0) filters.push(_definingFilter(a)); return; }   // never reached
```
- **Producer confirms the trigger** (real Python `querybuild._is_res_affix` / `res_contributions` on
  real mod text): `"+22% to Cold Resistance while affected by Purity of Ice"` → `resist=1`,
  and because "cold" buckets into the elemental total a `pseudo.pseudo_total_elemental_resistance`
  row is emitted → `rareDefaultPicks.usePseudo` defaults **true**. Same for `"+30% to Fire Resistance
  while affected by Purity of Fire"` and, for **Grand Spectrum (Viridian)**, `"+15% to all Elemental
  Resistances per Grand Spectrum"` (`resist=1`, pseudo emitted).
- **Consumer reproduced on the real `core.js`** (Purity-cold-res Watcher's Eye, default picker state):
  emitted ids = `["explicit.stat_3627458291","pseudo.pseudo_total_elemental_resistance"]` — **the
  defining cold-res filter is gone**; the query degrades to "any Watcher's Eye with the Anger crit mod
  + 22 total elemental res." Toggling pseudo-fold OFF restores it (proves the fold is the cause); the
  real picker pipeline (`tierGroups` → `buildRareQuery`, index.html `pkBuildQuery`) drops it too.
- **Impact:** the exact-variant identity is lost → the search matches the WRONG Watcher's Eye variant
  (biased-low "cheapest of a looser superset", i.e. a **misleading number**) or 0 matches. Contradicts
  Locked **D-0019** (defining mod = item identity, "search WITH the specific mod") and **D-0015**
  (a mod dropped the user never excluded — one the picker cannot even re-tick).
- **Reach:** the manual **✎ "refine + open the exact-variant search"** flow for a registry variant
  unique (index.html:1473/1597 → `openPicker(k,{edit:true})`) — the headline D-0019 feature. Hands-free
  autoscan is **unaffected** (it uses the server's `_unique_query`, which has no fold bug — core.js:764).
- **Class, not this build:** `[REALISTIC — not in the 4 banked builds]` yalokk's actual Watcher's Eye
  auras (reduced-crit-extra-dmg / suppress / unaffected-by-chilled-ground) are non-resist, so the four
  banked builds don't trip it. Purity-resistance Watcher's Eyes and Viridian Grand Spectrum are common,
  high-value variants — the class is real.
- **Fix:** move the `a.defining` branch **above** the `if (usePseudo && a.resist) return;` line in
  `buildRareQuery` (and mirror the order in `tierGroups`' counting loop, core.js:1141–1142) so a
  defining mod is emitted before any fold. A defining resistance must never be folded away.

### R3-2 — MAJOR — the picker's DEFAULT (survey) view silently EXCLUDES searchable unique mods + the pseudo resistance total `[CONFIRMED]`
`_siteTierOf` maps affix `priority` to a tier on a documented — but **false** — assumption:
```
core.js:1014   // `skip` is only ever assigned to unsearchable affixes (never emitted).
core.js:1020   if (pr === "skip") return "notneeded";                   // notneeded -> unticked -> dropped
```
But `querybuild.affix_options` assigns `priority:"skip"` to **every non-skill-level explicit mod on a
UNIQUE** and to the **pseudo total on a unique** (`_affix_tier`: `is_unique → "skip"`; pseudo/equip:
`"skip" if is_unique`). The picker opens in `view:'survey'` (index.html:1836), and `currentPicks()`
→ `surveyPicks()` → `tierGroups()` (index.html:1881/1891) re-derives `ticked` **from the tier** — so
every `skip`→`notneeded` mod is unticked and omitted. `rareDefaultPicks` ticks everything regardless of
tier (so the item's DEFAULT/all-ticked query is correct), but the survey view diverges from it.
- **Reproduced on all 4 banked builds** — survey-default query (no user edits) vs the item's all-ticked
  default: **51 of 53 uniques drop filters; 0 of 44 rares do.** Examples: Headhunter `6→1`,
  Replica Voidwalker / Rumi's Concoction / Inpulsa's / The Fledgling → **empty stat group** (name-only),
  Vaal Caress drops 4 explicits **+ the `pseudo.pseudo_total_elemental_resistance` total**.
- **Impact:** opening the affix picker on a unique and hitting Search **with zero edits** silently
  excludes most/all of its searchable mods + its pseudo resistance total — the exact auto-exclusion the
  code comment says is forbidden and the owner vetoed in **D-0015** ("if the user doesn't manually
  exclude an affix we should not be doing that for them"). Live harm is **bounded** (the unique NAME
  still scopes the search, and variant **defining** mods survive as `required`), so it broadens rather
  than mis-identifies — but it degrades the D-0019 ✎ refine flow and drops the pseudo res total, and it
  makes the picker-default query disagree with the item-default/autoscan query.
- **Reach:** variant uniques (✎ edit) + unpriced uniques (manual-row `.mr-affix`, index.html:2156).
  Name-priced uniques (Headhunter, Nimis, …) aren't picker-openable today, so their drop is **latent**.
  RARES are unaffected (their searchable mods score required/nice/notimp, never skip).
- **Fix:** treat `skip` like `notimp` for **searchable** rows — a suggestion that still defaults to
  searched (tier `nice`/`required`), never an auto-exclusion; only **unsearchable** (`stat_id==null`)
  rows should be `notneeded`. Equivalently, gate the `skip→notneeded` map on `!a.searchable`. This
  restores D-0015's "prefilled all-ticked" for uniques.

---

## 2. What passed (query truth holds) — positive validations

- **Trade-schema well-formedness: 227/227.** Every query built across default / untick-one /
  pseudo-fold-on/off / tier+count-spinner / scope×2 on f1fti + yalokk is well-formed per
  `docs/research/trade1.md`: valid `status.option`; `stats` groups typed in
  `{and,not,if,count,weight,weight2}`; filters `{id[,value{min|max|option|weight}]}` with numeric
  values and no null/`"null"` ids; **count** groups carry `value.min ∈ [1,#filters]`; `type` and
  `type_filters.category` never both present; `socket_filters.links.min` / `armour_filters.{ar,ev,es,
  ward}.min` shapes correct. **No malformed query on any real payload or action.**
- **Faithful default/untick/pseudo/scope (D-0015):** all-ticked reproduces the item's strict query;
  untick removes exactly one filter; pseudo-fold on↔off swaps individual resistances ↔ the totals;
  `applyScope` swaps exact-base ↔ category while preserving status, links and defining filters
  verbatim (never invented). The only faithfulness failures were the tier-path drops → R3-2.
- **Variant locking works for non-resist defining mods:** yalokk's real Watcher's Eye (3 defining:
  reduced-crit / suppress / unaffected-chilled) and Bubonic Trail (`1 Abyssal Socket`, exact min=max=1)
  survive `tierGroups` and emit their locked filters; option-split (Forbidden) and exact-seed (timeless)
  locking hold per the existing `test_picker.mjs` (98/0). R3-1 is the sole variant-locking gap and it is
  resistance-specific.

---

## 3. R2 carry-forward — F2–F5 re-evaluated (F1 already fixed: D-0020 R2 F1)

| # | R2 sev | Verdict now | Evidence (current code) |
|---|---|---|---|
| **F2** | minor | **STILL REAL — unfixed** | Zero-match chip reads **"no buyout among 0 listings · 0 fetched, 0 w/o buyout"** — `index.html:2223-2224` (`n=d.total`, **no `total===0` branch**) + `core.js:804` applies note **"listings exist but none had a buyout price"** unconditionally in the `res.amount==null` branch (fires for `total=0` too). Self-contradictory; hits owner's "no-buyout" sensitivity (D-0012). r2-fix1 §4 explicitly left it untouched. |
| **F3** | minor | **STILL REAL — unfixed** | Raw per-row `ms` is chunk-cumulative: `core.js:865` sets all 3 chunk keys to `"scanning"` at dispatch, and `core.js:746` stamps `s.t0` on that first non-queued stage — so later-in-chunk rows inherit predecessors' search+fetch+wait. `scanStatus().status[k].ms` overstates (judge measured up to 9.9×) and can mis-rank the scan. Degrades the D-0020 hard-criterion (a) timing instrument. Fix: stamp `t0` on the row's own first `"searching"` event. |
| **F4** | minor | **STILL REAL — owner design call (not a code bug)** | Magic flasks/small-cluster jewels are still live-scanned to a ~0.066c floor (≈38% of wall-clock on yalokk). Pacing/scope behaviour unchanged since R2; this is the scan-SCOPE lever, deferred to the owner (floor-price / skip magic from autoscan; price magic cluster jewels by their notable). No code defect — needs an owner decision. |
| **F5** | nit | **STILL REAL — nit** | Header count = `bpc.manualRows().filter(r=>!r.priced).length` (`index.html:1272`) but the rendered RARES list = **all** `manualRows()` (`index.html:2319/2337`). A **floor-priced variant unique** is `priced` (excluded from the header) yet still listed (it `needsScan`), so header "N" < list length. Cosmetic; fix by counting the variant/timeless unique in the "to price yourself" figure or labelling it separately. |

---

## 4. Ranked summary for the fix agent

1. **R3-1 (MAJOR)** — `buildRareQuery`/`tierGroups`: emit `a.defining` **before** the
   `usePseudo && a.resist` fold, so a variant-defining resistance mod (Purity Watcher's Eye, Viridian
   Grand Spectrum) is never folded away. `public/site/assets/core.js:1087-1091` (+ `:1141-1142`).
2. **R3-2 (MAJOR)** — `_siteTierOf`: `skip → notneeded` only when `!a.searchable`; searchable `skip`
   rows default to searched (like `notimp`). Restores D-0015 all-ticked default for uniques (51/53).
   `public/site/assets/core.js:1016-1022`.
3. **F2 (minor)** — branch the zero-match copy on `res.total===0` (distinct chip + note).
   `public/site/assets/core.js:802-805`, `public/site/index.html:2223-2224`.
4. **F3 (minor)** — stamp per-row `t0` on the row's own first `searching` event (not chunk dispatch).
   `public/site/assets/core.js:746, 865`.
5. **F5 (nit)** — reconcile the "N rares to price yourself" header with the rendered list.
   `public/site/index.html:1272`.
6. **F4 (owner design call)** — magic-scan scope; needs an owner decision, not a code fix.

**Round verdict:** the picker builds **well-formed** queries on all real data (227/227 schema-valid),
and its default / untick / pseudo-fold / scope paths are **faithful**. But two MAJOR **query-truth**
defects break faithfulness in the manual picker: a variant-defining **resistance** mod is folded away
(R3-1, wrong-variant/misleading price, breaches D-0019) and the survey view silently **auto-excludes**
searchable unique mods + the pseudo res total (R3-2, breaches D-0015, 51/53 uniques). Hands-free
autoscan and all four D-0020 hard-criteria paths are unaffected. Carry-forward F2/F3/F5 remain real
(unfixed); F4 remains an owner design call.

## 5. Provenance
- Consumer: real `public/site/assets/core.js` in a Node `vm` (`require`), driven by `buildRareQuery` /
  `rareDefaultPicks` / `tierGroups` / `applyScope`. Producer: real `public/api/_lib/querybuild.py`
  (`_is_res_affix`, `res_contributions`, `affix_options`, `_siteTierOf` semantics).
- Real payloads: `GET {divtally.vercel.app}/api/build?url=<build>` for the four
  `research/data/bugtest/inputs.json` characters (poe.ninja-backed; **no pathofexile.com call**).
- Decisions: D-0015, D-0016 (#2/#3), D-0019 in `docs/00-decision-log.md`; schema `docs/research/trade1.md`,
  `docs/research/variant-stats.md`. Carry-forward source: `docs/bugtest/r2-judge.md` §3,
  `docs/bugtest/r2-fix1.md`/`r2-fix2.md`.
