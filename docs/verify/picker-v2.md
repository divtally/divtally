# Adversarial verification - D-0016 "Picker upgrade batch" (picker-v2)

Date: 2026-07-27. Scope: verify D-0016 (items 1-4) against its spec + the D-0015 no-implicit-
exclusion veto. Read-only review + offline harnesses + fixture re-derivation. No pathofexile.com
calls, no writes outside this file (scratchpad scripts only).

## VERDICT: PASS - 0 blocker, 0 major, 2 minor (both informational / no action required to ship)

Every harness is green; every `node --check` passes. The D-0015 strict-default invariant HOLDS on
every path (proven, not assumed). Category scope ids are all valid; uniques are untouched; the rare
tier math is byte-faithful to the local app; the cache POST validates against the worker. The two
minor items are a documented semantic-equivalence nuance and a cosmetic small-viewport edge.

---

## Part 1 - Harnesses (all green)

| harness | result |
|---|---|
| `python tests.py` | All self-tests passed |
| `node public/site/test_picker.mjs` | 83 passed, 0 failed |
| `node public/site/test_scanstatus.mjs` | 47 passed, 0 failed |
| `node extension/test_protocol.mjs` | PASS (all checks) |
| `node public/worker/worker.test.mjs` | 55 passed, 0 failed |
| `python public/api/_verify.py` | ALL CHECKS PASSED (offline + live phase) |
| `node --check` x13 (`bpc/ui/assets/{core,sample}.js`, `extension/{background,content,popup,test_protocol}`, `public/site/{assets/core,assets/sample,config,test_picker,test_scanstatus}`, `public/worker/{worker,worker.test}`) | all OK |

Aside (not a D-0016 finding): `_verify.py` writes its two sample dumps to the OS temp dir
(`%TEMP%\sample_response_*.json`) via tempfile - benign, pre-existing, not OneDrive.

## Part 2 - D-0015 compliance re-trace (the BLOCKER-exception check)

Question: with defaults untouched, does the built query still require EVERY affix (modulo the
D-0016 category scope), or does a prefill silently drop / count-relax anything?

Traced all three query paths:

1. **Server default / Autoscan trade_query** - `querybuild.py::_rare_default_filters` (L456-459):
   `stat_groups = [{"type":"and","filters":stat_filters}]` - a SINGLE AND group over every
   searchable affix. The D-0014 count(n-1) auto-relax is genuinely DELETED (comment cites the
   D-0015 owner veto). Presence-only by design (min carried only on negated affixes, L448-452),
   which is the pre-existing strict default. No count group. Nothing dropped.

2. **Client Autoscan batch** - `index.html` L1917 calls
   `bpc.buildRareQuery(rare, itemOrigQuery(it), bpc.rareDefaultPicks(rare))`. `buildRareQuery`
   reads only `ticked/min/max/group` and ignores `.tier`; with no `picks.groups` it emits ONE AND
   group (core.js L1015). Identical to the strict baseline. No count group.

3. **Picker default view (survey)** - the only path that can surface a count group. `pkmInit`
   sets `view:'survey'` (L1698); `surveyPicks()` -> `tierGroups()` (L1737). `rareDefaultPicks`
   prefills each affix's tier from the API `priority` via `_siteTierOf` (core.js L961-967):
   required->required, nice|notimp->**nice**, skip->notneeded. Critically, `_affix_tier`
   (`querybuild.py` L116-126) can only return `skip` for an UNSEARCHABLE affix (`not ok`) or a
   UNIQUE - so **no searchable rare affix is ever prefilled not-needed**. The lowest a searchable
   rare affix falls is `nice`, which `tierGroups` routes into ONE count group with
   `min = #nice = all` (core.js L1083-1084).

**Proof (scratchpad simulation, rare with priorities required/nice/notimp/no-hint):**
- STRICT baseline stats: `[{and: s.A,s.B,s.C,s.D}]`
- DEFAULT tier-view stats: `[{and: s.A,s.D}, {count(min=2, filters=2): s.B,s.C}]`
- Same set of affix ids in both (nothing dropped); the count group is `min==filters` => "match
  ALL" == AND-equivalent. Result set is identical to strict.

Judgment against D-0016 wording: D-0016 item 3 EXPLICITLY permits prefilled visible tier
suggestions from `_affix_tier`; D-0015's hard rule is "nothing silently dropped", and `N=all`
guarantees that. The task's BLOCKER exception ("...unless the default sheet still requires
everything; the INITIAL query must be all-required") is SATISFIED - the initial query does require
everything. **NOT a blocker.** See finding P2-1 for the one nuance.

## Part 3 - Scope (D-0016 item 2)

- **Category ids all valid.** All 18 ids `_category_option`/`_gem_query` can emit
  (`_INVENTORY_CATEGORY` + `_WEAPON_SUFFIX_CATEGORY` + `armour.quiver` + `gem.activegem/supportgem`)
  exist as `category` options in `research/data/trade_data_filters.json` (83 options). All 16
  `_CATEGORY_LABEL` strings match the official option `text` verbatim (independent cross-check).
- **Base fallback works.** `_rare_scopes` returns `[category, base]` category-first, or base-only
  when no category maps; `scope_choices` returns `category:null` then, and `defaultScope`
  (index.html L1693) falls to `'base'`. Both-null -> `scope="unpriceable"` / empty `scope_q`
  (unpriceable guardrail: link, no number). `applyScope` never invents a scope (returns oq
  unchanged for an unavailable request).
- **Uniques unchanged.** `response.py` L146-149: uniques keep `scope="unique: <name>"` and
  `scope_q={name,type}` with NO `scopes` key; `_unique_query` is name+base(+links)(+skill-level).
  `applyScope` on a unique is a no-op (`scopes.base` absent -> returns oq). The is_unique
  `skip->notneeded` tiering never causes a default drop because uniques price by name, not via the
  affix picker.

## Part 4 - Rare tier math (D-0016 item 4)

- **Byte-faithful distribution.** `core.js` `_percentile/_median/_trimOutliers/tiersFromChaos`
  mirror `bpc/util.py` + `bpc/pricing.py::Pricer._tiers` (HIGH_PCT=90, trim window
  [0.30, 6.0]*median, linear-interp percentile). Ran BOTH on 3 hand-computed fixtures:

  | fixture | hand min/median/high | Python `_tiers` | JS `tiersFromChaos` |
  |---|---|---|---|
  | `[10,20,30,40,50]` | 10 / 30 / 46 | 10 / 30 / 46 (n5) | 10 / 30 / 46 (n5) |
  | `[1,10,12,15,18,20,200]` (scam lo+hi) | 10 / 15 / 19.2 | 10 / 15 / 19.2 (n5) | 10 / 15 / 19.2 (n5) |
  | `[200,50]` (2div@100 + 50c) | 50 / 125 / 185 | 50 / 125 / 185 (n2) | 50 / 125 / 185 (n2) |

  All identical (Python `30.0` vs JS `30` is float repr only).
- **prices[] path.** `rareTiersFromPrices` converts `{amount,currency}` via `_amtToChaos`
  (chaos/divine only), drops non-convertible/null entries (not fabricated), then `tiersFromChaos`.
  Fixture C via the real prices[] shape (2 div, 50 chaos, null, fusing) -> 50/125/185/n2. Matches.
- **Old-ext fallback graceful.** `undefined` / `[]` / all-non-convertible / divine-with-no-rate
  all -> `null` (no fabricated number). core.js L787-795 then falls back to the single cheapest
  (`toChaos`) as a flat point estimate, or `include:false` with an honest "no chaos rate" note.
- **Cache POST validates against the worker.** Site POSTs `{chaos:{min,median,high}, total_found,
  sample_size, method:"extension", note, trade_url}` (core.js L808-812) - exactly
  `worker.js::sanitizeEntry`'s expected shape. `num()` caps each tier finite/>=0/<=1e8 (else null);
  confidence is re-derived server-side from `total_found` (client value ignored); entry rejected
  unless >=1 finite tier survives. `confFromTotal` thresholds match on both sides (>=5 high, >=2
  medium). worker.test.mjs (55) covers the sanitize/cap path.

## Part 5 - UI scale-up + small-screen scroll (D-0016 item 1)

- **Scale-up present.** `.pick` is roomier: `width:min(640px,96vw)`, `max-height:92vh`, larger
  fonts - header 22px (L557), base/scope line 15px (L560), affix text 16px (L592), min/max 14px.
  D-0016 item 1 markers on the CSS (L549, L724).
- **Small-screen scroll.** `.pick { max-height:92vh; overflow:auto }` (L552) scrolls the picker
  content within the modal; `@media (max-width:560px)` tightens to 96vw + smaller columns (L725),
  `@media (max-width:720px)` collapses the board (L734). `?mock` demo mode exists
  (`bpc.loadMock`, `state._mock`, `/assets/sample.js`) to exercise the markup with no backend.
- See finding P5-1 (very-short-viewport clip, cosmetic).

---

## FINDINGS

### P2-1 (minor / informational) - opened picker's default query is AND + count(N=all), not a single AND
When a user OPENS the affix picker (an explicit action) and clicks Search without changing
anything, the survey view builds `(AND: required affixes) + (count>=#nice of #nice: nice affixes)`
rather than the single AND group the pure-autoscan path builds. This is STRUCTURALLY different but
SEMANTICALLY identical (count min==filter-count == "match all"), and only occurs once the user has
opened the picker and is looking at the prefilled tier suggestions. It is D-0015-safe (proven:
nothing dropped) and explicitly permitted by D-0016 item 3 ("tiers may be prefilled visible
suggestions"). Note only: the task's phrasing "count groups appear ONLY from explicit user tier
changes" is met in spirit (the pure default/autoscan path has no count group) but a count group
does also arise from the prefill itself in the opened picker - acceptable because N=all. No action
required; flagged for owner awareness in case he wants the opened-picker default to also render as
a single AND until a tier is actually changed.

### P5-1 (minor / cosmetic) - picker can clip a few px on viewports shorter than ~500px tall
`#pickwrap` is `position:fixed; inset:0; align-items:center; padding:20px` with no `overflow-y`,
and `.pick` is `max-height:92vh`. When viewport height < ~500px (landscape phones), 92vh can exceed
the wrapper's inner height (100vh-40px); flex-centering with no wrapper scroll makes the top few px
of the picker header unreachable (the picker's own `overflow:auto` still scrolls its body). Trivial
fix if desired: add `overflow-y:auto` to `#pickwrap`, or `max-height:calc(100vh - 40px)`, or
`align-items:flex-start` on a short-height media query. Does not affect normal phones/tablets/desktop.

## Provenance
All numbers/behaviors above are SOURCE-DERIVED: live harness output, the actual `bpc/pricing.py` +
`bpc/util.py` run on fixtures, `research/data/trade_data_filters.json`, and the shipped
`core.js`/`querybuild.py`/`worker.js`/`response.py`/`index.html`. The only [INFERRED] element in the
code path is `_weapon_subcategory` (self-tagged [INFERRED] in its docstring: weapon class from the
base-name's last word) - but every id it can emit (weapon.wand/bow/sceptre/claw) was independently
confirmed valid against the trade filter data, so the inference does not produce an invalid scope.
