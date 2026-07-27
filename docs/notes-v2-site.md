# Notes — v2 SITE work (D-0016 items 1-4, site side)

**Date:** 2026-07-27 · **Scope of this change:** `public/site/**` only (+ this notes doc).
**Spec:** `docs/00-decision-log.md` **D-0016** (owner's four picker asks) under **D-0015** (no
implicit affix exclusion). **Reference (read-only):** the parent's shipped 2026-06-14 mod-priority
survey — `C:\scripts\buildpricechecker\bpc\ui\stash.html` (pkRenderSurvey / pkApplyTiers / the
group editor) — replicated *behaviourally* in the DivTally picker (match-shop-patterns).

Paired work already shipped: **item 2 API side** (`docs/notes-v2-api.md` — `rares[].scopes`) and
**item 4 extension side** (`docs/notes-v2-ext.md` — additive `prices[]`, ext v1.2.0). This batch is
the SITE consumer of both.

---

## Files touched (all owned)
- `public/site/assets/core.js` — pure logic: multi-group `buildRareQuery`, tier prefill in
  `rareDefaultPicks`, new `tierGroups` (survey→groups), `applyScope` (category↔base), and the ported
  rare-price **distribution math** (`rareTiersFromPrices`/`tiersFromChaos`).
- `public/site/index.html` — picker scale-up (CSS), header **scope selector**, the **priority-tier
  survey + count spinner + "edit groups" editor**, and tier-aware rare rows/totals.
- `public/site/assets/sample.js` — mock rares enriched with `scopes` + one extension-priced rare
  with real `{min,median,high}` so `?mock` exercises items 2 & 4.
- `public/site/test_picker.mjs` — existing 9 cases stay green; new cases for tiers→groups, count
  spinner, scope both ways, all-required==previous.

---

## Item 1 — SCALE UP (CSS only, inside the `.pick` modal)
Owner found the picker fonts too small. Changes are confined to the `.pick` modal so nothing else
on the page moves. Wider `max-width`, taller `max-height` (kept `overflow:auto` → still scrolls on
small screens), and larger fonts on the three things he named: the intro line (`.phint`), the
base/scope line (`.ph .scope`), and the affix rows (`.afx .atext`). Bronze palette (`--bz*`)
untouched. A `@media (max-width:560px)` rule keeps it at `96vw` with slightly tighter type.

## Item 2 — SCOPE SELECTOR (picker header)
The API now emits `rares[k].scopes = { category:{id,label}|null, base:{type,label}|null }`
(notes-v2-api.md). The picker header shows a `<select>`:
- default **"Any &lt;category.label&gt;"** → the generic category scope (`type_filters.category`);
- option **"Exact base: &lt;base.type&gt;"** → the exact-base scope (`type`).

The active scope drives the client query builder. **Core:** new pure `applyScope(rare, origQuery,
which)` returns a copy of the item's query re-scoped to `'category'` or `'base'` from `rare.scopes`
— it swaps ONLY the scope fields (`type` ↔ `type_filters.category`) and preserves everything else
(`status`, the 5/6-link `socket_filters`, `name`). It never invents a scope: if the requested one
is absent it returns the query unchanged. When no category maps (`scopes.category == null`), the
default IS the base and the selector shows a "why" hint ("no item-category filter for this slot").

## Item 3 — PRIORITY TIERS + COUNT GROUPS + "edit groups" (PoE2 parity)
Replicates the parent's mod-priority survey, adapted to DivTally's client query builder and to
**D-0015**.

### The site's THREE tiers (owner's exact enumeration)
`required` · `nice-to-have` · `not-needed`. The parent has four (Required/Nice/Not-important/
Unnecessary); the owner collapsed them to three for DivTally. Query build (owner's words):
- **required → the AND group**, min/max **"as now"** (the prefilled roll — NOT the parent's 60%
  relaxation; a silent loosen would violate D-0015).
- **nice-to-have → ONE count group** with a user-editable **"match at least N"** spinner; **default
  N = the nice count (all of them)** — strictest, so the default still requires every affix
  (D-0015-safe; count-of-all ≡ AND for matching).
- **not-needed → excluded** (unticking IS an explicit user action).

### Prefill mapping — API `priority` → site tier (**the key D-0015 call**)
The API's `_affix_tier` scores each searchable rare affix `required`/`nice`/`notimp` (score bands)
and only ever emits `skip` for **unsearchable** affixes (verified in `querybuild.py::_affix_tier`).
Mapping:

| API `priority` | site tier | why |
|---|---|---|
| `required` | required | — |
| `nice` | nice-to-have | — |
| `notimp` | **nice-to-have** | D-0015: prefilling it `not-needed` would be the tool AUTO-EXCLUDING on a low score. `nice` keeps it searched (count group, default N=all ⇒ still required); the user may demote it. |
| `skip` | not-needed | only ever on unsearchable affixes → never emitted into a query anyway |
| (absent) | required | strictest; keeps the all-affix default (and the test fixtures) intact |

Prefilled tiers are **visible suggestions** the user reviews before clicking Search (D-0016) — the
sheet hides nothing and the owner may veto any prefill.

### "edit groups" reveal
A second picker view exposes the raw group composition: per-group **type** select (And / Count /
Not), a count **threshold** spinner, each affix's **min/max**, and a per-row **group** selector to
move an affix between groups (+ add/remove group). This is the parent's group editor, minus its
"+ add off-item stat" (the public API exposes no full stat dictionary client-side — out of scope,
noted). Survey and editor both feed the SAME `buildRareQuery`.

### Core shape
`buildRareQuery(rare, origQuery, picks)` is now group-aware: `picks.groups = [{type,min},…]` +
each pick's `.group` index splits filters across `query.stats` groups (count groups carry the
trade API's group-level `value:{min}`). **No `picks.groups` ⇒ a single AND group of every ticked
affix — byte-identical to the old behaviour** (all 9 legacy tests stay green). `tierGroups(rare,
picks)` is the pure survey→groups derivation; `rareDefaultPicks` now also prefills each pick's
`tier`.

## Item 4 — MIN/MEDIAN/HIGH move rares too (distribution math)
The extension (v1.2.0) returns `prices[] = [{amount,currency},…]` (all fetched listings, fetch =
price-ascending order). The site now computes real tiers from them with the **local app's
distribution math**, ported byte-faithfully from `bpc/pricing.py::Pricer._tiers` +
`bpc/util.py` (identical in both repos):
- `trim_outliers` — keep listings in `[0.30, 6.0] × median` (drops scam-low / typo-high);
- `min = kept[0]` (cheapest kept), `median = median(kept)`, `high = 90th-percentile(kept)`.

New pure `rareTiersFromPrices(prices, rate)` (chaos+divine convert via an explicit rate; other
currencies dropped, never fabricated) + `tiersFromChaos(chaos[])`. In `foldBatch` an
extension-priced rare now stores real `{min,median,high}`; the community-cache POST sends those
real tiers. **Fallbacks:** an old v1.1.0 extension (no `prices[]`) or an all-non-convertible set →
single-value tiers (`min=median=high`), exactly as before. Whisper-paste rows stay single-value
(honest). Because rares now carry a real band, the existing MIN/MEDIAN/HIGH selector moves rare
rows + totals exactly like uniques — the site side just makes the manual-panel price tier-aware
and repaints it on tier change.

---

## Verification (run after each file — owner instruction)
Baseline before any edit: `test_picker` 42 pass · `test_scanstatus` 47 pass.

- **After `core.js`** (distribution math, multi-group builder, tier prefill, tierGroups, applyScope):
  `node --check` OK; `test_picker` **42/42** (legacy stays green — the multi-group refactor defaults
  to a single AND group, byte-identical); `test_scanstatus` **47/47** (D-0012 chunking + v1.1
  statuses untouched).
- **After `test_picker.mjs`** (+41 new assertions): **83/83** — tier prefill from priority,
  tiers→groups, count spinner loosen/clamp, not-needed drop, all-required==previous single-AND,
  scope category↔base (+ links/status preserved), distribution min/median/high + fallbacks.
- **After `index.html`** (scale-up CSS, scope selector, survey+groups picker, tier-aware rows):
  inline `<script>` parses (test_picker's parse-check) — **83/83**; `test_scanstatus` **47/47**.
- **After `sample.js`** (mock `scopes`): `node --check` OK; both harnesses still **83 / 47**.
- **`?mock` end-to-end smoke** (real Chrome, headless, static-served, offline): **PASS, 0 code
  errors.** Verified live: build renders with no backend; a **priced rare row moves with the
  min/median/high selector** (45c → 1.7 div/180c) [item 4]; the picker opens roomier [item 1] with
  a **header scope selector** (2 options, default “Any Body Armour”, switches to exact base) [item
  2]; **priority-tier selects** per affix, **nice-to-have reveals the count spinner**, **“edit
  groups” shows the group-box editor** with type controls [item 3]; the base scope drives
  `type=<base>`; **Search builds and opens one real `…/trade/search/…` URL** and closes the picker.
  (The only console noise is external `web.poecdn.com` item-image 404s — expected offline, not code.)

Final combined sweep: `core.js`/`sample.js`/`config.js` parse OK · `test_picker` **83** ·
`test_scanstatus` **47** · `?mock` smoke **PASS**.

## Notes / deliberate scope boundaries
- **notimp → nice-to-have** is the load-bearing D-0015 call (see the prefill table). It keeps the
  default search requiring every affix (count-of-all ≡ AND) — the tool never auto-excludes.
- The **"edit groups" editor omits "+ add off-item stat"** (the parent had it): the public API
  exposes no full trade stat dictionary to the client, so there is nothing to search. Move / change
  type / threshold / add-remove group are all present.
- The **pseudo-fold toggle shows in the survey only**; entering "edit groups" locks the fold as it
  was (re-deriving groups on a fold-flip would discard the user's manual group moves). Go back to
  tiers to change the fold.
- **Autoscan (queue "price all remaining")** still uses each rare's DEFAULT (category-scoped,
  all-affix) query — per-rare scope/tier picks apply to the rare you're editing, not the bulk
  default (matches the API's autoscan default).
