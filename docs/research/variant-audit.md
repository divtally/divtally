# Variant-unique / timeless-jewel behaviour audit (CURRENT vs D-0019)

**Date:** 2026-07-27 · **Scope:** the PUBLIC pricing path only (`public/api/…`), which is
what D-0019 targets. **Method:** static read of the code + probes of the bundled trade schema.
**Evidence sources (primary):** the code files below; `public/api/_data/trade_stats.json` and
`trade_items.json` (saved *verbatim* from GGG `/api/trade/data/stats|items` by
`research/probe_trade.py` line 110); `docs/research/trade1.md`; `docs/00-decision-log.md`.
Provenance tags: **[SOURCE]** = derived from the above. **[VERIFY-BUILD]** = needs a live
poe.ninja call (allowed) or a live trade call (must be the sole-budget spot-check agent, D-0019
step 5) — not run here. Nothing in this doc is web/wiki-claimed.

Files read: `querybuild.py`, `response.py`, `poeninja.py`, `models.py`, `statmap.py`, `util.py`,
`refdata.py`, `engine.py`, `build.py`, `docs/00-decision-log.md`, `docs/research/trade1.md`,
`research/probe_trade.py`, `tests.py`.

---

## 0. TL;DR

Today every unique — plain OR variant-defining — gets the **same name+base query with an EMPTY
stat group** (the only stat filters `_unique_query` ever adds are skill-gem-level mods). The
notable of a Forbidden Flesh, the aura mods of a Watcher's Eye, and the *seed* of a Lethal Pride —
the entire price identity of each — are **absent from the query**. poe.ninja variant matching is a
lexical token-overlap against poe.ninja's `variant` **label** (not stat ids), falling to a
min..p90 **range** whenever ambiguous. The affix picker *does* list uniques' mods (D-0015) and for
Forbidden Flesh / Watcher's Eye those mods are even individually **searchable with correct stat
ids** — but for uniques they are all forced to `priority:"skip"` / `prefer:false`, so they are
never prefilled, never required, and never labelled as the defining mod. Timeless-jewel seeds are
worse: the seed maps to a stat id but the picker can only prefill `min` (never `min=max`), and
poe.ninja cannot price by seed at all. **No `variant_uniques.json` registry exists** — the only
per-item "defining mod" the code knows is the hard-coded skill-level-mod class.

---

## 1. Q1 — What query does each item get TODAY?

All three route the same way: `engine.run_estimate` → `PublicPricer.price_build`
(querybuild.py 690-707) → `it.category == CAT_UNIQUE` → `price_unique_ninja`
(620-661) → `_unique_query` (475-484). `_unique_query` builds:

```
{status, name, type: base_type, stats: [{type:"and", filters: vfilters}]}  (+ filters.socket if 5L+)
```

where `vfilters = _unique_value_filters(item)` (462-472). **`_unique_value_filters` keeps ONLY
mods for which `_is_skill_level_mod(mod)` is true** — i.e. text contains "to level of all" AND
"skill" (111-113). Nothing else is ever added to a unique's stats. The scope is always name + base
`type` (never a `category`, never a defining mod). Status defaults to `available` (D-0017;
build.py 66, querybuild.py 279).

### Forbidden Flesh (name="Forbidden Flesh", base="Cobalt Jewel") [SOURCE]
Defining mod = "Allocates *Notable* if you have the matching modifier on Forbidden Flame" — **not**
a skill-level mod → `vfilters = []`. Jewel → no sockets → no links filter. **Query today:**
```json
{"status":{"option":"available"},"name":"Forbidden Flesh","type":"Cobalt Jewel",
 "stats":[{"type":"and","filters":[]}]}
```
The allocated notable — the whole reason the item is worth anything — is **not in the query**.
(Forbidden Flame is identical with base "Crimson Jewel".)

### Watcher's Eye (name="Watcher's Eye", base="Prismatic Jewel") [SOURCE]
Defining mods = the 1-3 "… while affected by *Aura*" lines — normal explicit stats, not skill-level
→ `vfilters = []`. **Query today:**
```json
{"status":{"option":"available"},"name":"Watcher's Eye","type":"Prismatic Jewel",
 "stats":[{"type":"and","filters":[]}]}
```
Searches *every* Watcher's Eye regardless of which auras it rolls (the sole price determinant).

### Lethal Pride (name="Lethal Pride", base="Timeless Jewel") [SOURCE]
Defining data = the seed, carried in the mod "Commanded leadership over *N* warriors under
*Conqueror*" — not skill-level → `vfilters = []`. **Query today:**
```json
{"status":{"option":"available"},"name":"Lethal Pride","type":"Timeless Jewel",
 "stats":[{"type":"and","filters":[]}]}
```
Neither the seed `N` nor the conqueror is in the query. All base types confirmed present in
`trade_items.json` (Cobalt Jewel / Prismatic Jewel / Timeless Jewel), so `resolve_type` succeeds
and each query is *valid* — just under-specified to uselessness for a variant item.

---

## 2. Q2 — How does the ninja price-match pick among variant lines TODAY?

Lives in `PoeNinjaEconomy.unique_price` (poeninja.py 350-407), called from
`price_unique_ninja` (633). **Not cheapest, not first** — it is either a single-variant point
estimate or a range:

1. Load every economy line for the name, merged across UniqueWeapon/Armour/Accessory/Flask/**Jewel**
   overviews (`_load_uniques` 325-344); if `base_type` known, keep only same-base lines (369-373).
2. **n == 1** (378-384) → point estimate, `matched="name"`, min=median=high = that line's
   `chaosValue`, confidence from `listing_count` (`_confidence_from_lc`: ≥5 high / ≥2 medium / else
   low).
3. **n > 1** → tokenise (`_variant_tokens` 346-348: lowercase, split on non-alphanumeric, keep
   tokens ≥3 chars). `item_tokens` = tokens of the item's **concatenated mod text**
   (`" ".join(explicit_mods)`, passed at 632). For each line, `cover = |variant_label_tokens ∩
   item_tokens| / |variant_label_tokens|` (386-394). Sort desc.
   - If `top_cover ≥ 0.6` **and** `top_cover > second_cover` and the line's chaosValue is numeric
     (398) → **`matched="variant"`**, point = that variant's chaosValue, confidence high if
     `listing_count ≥ 5` else medium.
   - Else → **`matched="range"`** (404-407): min = `min(vals)`, median = `util.median(vals)`,
     high = `util.percentile(vals, 90)` across **all** variant chaos values; `listing_count = 0`
     → confidence forced **low**; note "N variants … showing the price range … verify via the
     trade link" (651-653).

`price_unique_ninja` maps `matched` → method/confidence/note (647-660) and stuffs
`n_variants`/`variant`/`listing_count` into `extra` (643-646).

**Gaps [SOURCE unless tagged]:**
- Matching is **purely lexical against poe.ninja's `variant` label string**, never against trade
  stat ids or the actual mod set. The item's real defining mod is invisible to the match.
- The denominator is the *label*'s tokens. For Watcher's Eye, poe.ninja labels a variant by its
  aura name(s); a 2-3-aura combo, or the *specific* mod among several for one aura (there are many
  "… while affected by Clarity" mods), is not distinguished — coverage can hit ≥0.6 on the wrong
  or a partial variant. **[VERIFY-BUILD: pull the live UniqueJewel overview and read the exact
  `variant` labels poe.ninja uses for Watcher's Eye / Forbidden Flesh / Lethal Pride.]**
- The `≥0.6 AND > second` gate means the items that most need a specific number (many
  near-tokenwise-identical variants) fall to the **range**, i.e. a min..p90 spread that for
  Watcher's Eye / timeless spans orders of magnitude — a non-answer dressed as a number-range.
- **Timeless jewels can't be priced by seed at all**: poe.ninja lists at most per conqueror /
  keystone, so two Lethal Prides with the same conqueror but different seeds (which can differ
  ~100× in value) collapse to one line / one range. The seed never enters `unique_price`.
- No registry → the code cannot tell a variant-defining unique (Impresence, Mageblood, Watcher's
  Eye, Forbidden pair, timeless jewels…) from an incidental multi-line name, and treats them all
  with the same token heuristic.

---

## 3. Q3 — Does the picker let a user add the defining mod TODAY?

**Uniques DO get an affix payload** — the premise "uniques got no affix payload" is false in the
public path. `response.build_response` (response.py 157-183) includes `CAT_UNIQUE` in the `rares`
dict and calls `pricer.affix_options(it)` (164), emitting `affixes` + `pseudo` per unique. But the
payload is shaped so the user is **not** guided to the defining mod, and for timeless jewels it is
mechanically unable to express one:

`affix_options` (querybuild.py 365-428) per explicit mod:
- Calls `mapper.match(line, group)` (384). **The mapper resolves the defining mods** (see §5):
  Forbidden's "Allocates …" → a pipe-option id; Watcher's aura mods → normal explicit ids;
  timeless seed → a `pseudo_timeless_jewel_*` id. So `searchable:true` with a correct `stat_id`
  for all three.
- BUT `is_unique` forces **`priority` via `_affix_tier`** (116-126) to `"skip"` for every non
  skill-level mod, and **`prefer = ok and ((not is_unique) or _is_skill_level_mod(line))`** (385)
  → `false` for these. Rares prefill **all-ticked** (`_rare_default_filters`, 443-460); uniques
  get the defining mod listed but **un-prefilled, skip-tier, unlabelled**. Nothing in the payload
  says "this is the variant/defining mod."
- The unique's `scope_q` in the response is `{name, type}` only (response.py 170) — no defining-mod
  channel, no `scopes` picker (that branch is rares/magic only, 172-180).

If a user *manually* ticks a defining mod:
- **Forbidden Flesh:** `_statf`/`_build_stat_groups` emit `{"id": "explicit.stat_2460506030|33645"}`.
  The pipe id **is** the directly-searchable filter id (GGG delivers these option mods pre-split;
  see §5) → correct search. Value is `None` (no number in "Allocates …") → no min/max needed.
- **Watcher's Eye:** emits `{"id": "explicit.stat_…", "value":{"min": roll}}` → a reasonable
  ≥-roll search. Works.
- **Lethal Pride:** the seed mod prefills **`default_min = seed` only** — `_affix_defaults`
  (159-169, confirmed line 169 `return (None, value) if neg else (value, None)`) has **no exact
  (min=max) mode**. A `min=seed` filter means "seed ≥ N", which is meaningless for a nominal seed
  id. D-0019 requires seed **min=max**; the current picker cannot express it.

Net: the machinery to *search* Forbidden/Watcher defining mods already exists and is even wired
into the payload, but it is gated off (skip/prefer=false), un-prefilled, and unlabelled; timeless
seeds additionally lack the min=max prefill. The autoscan/server-default path ignores all of them.

---

## 4. Q4 — Where the "variant … best-effort with confidence note / range" logic lives, and its gaps

- **poe.ninja token-overlap variant match + range fallback:** `poeninja.py` `unique_price`
  386-407 (+ `_variant_tokens` 346-348). This is the *only* variant logic in the public path.
- **matched → method / confidence / note / range plumbing:** `querybuild.py` `price_unique_ninja`
  620-661 (range branch 647-653, variant branch 654-656, name branch 657-660;
  `_confidence_from_lc` 525-527).
- **The listing-based variant detector `_variant_affixes` does NOT exist in the public path.** It
  lives only in the local, trade-enabled `bpc/pricing.py` (parent 395-485; tested in `tests.py`
  539-557 against `bpc.pricing.Pricer`, not `PublicPricer`). It needs live trade listings, which
  the public server is forbidden to fetch (D-0008) — so the public build has *no* mod-level variant
  detection, only the poe.ninja label heuristic above.

**Gaps** (beyond the ninja-match gaps in §2): the confidence/range logic is downstream of a match
that never inspects the defining mod, so a "low / range" note is emitted for *ambiguity of labels*,
not *ambiguity of the actual item*. A Watcher's Eye whose exact auras are known still gets a range,
because the query and the match both discard those auras.

---

## 5. Primary-source stat shapes (what a correct search actually needs)

Probed from `trade_stats.json` (verbatim GGG). **16 350 entries, ZERO carry a structured
`option.options` array** — PoE1 delivers every option mod **pre-split** as `stat_id|optionid`
with the option baked into `text` (1 265 such ids: Explicit 713 / Enchant 524 / Implicit 28).
`trade1.md` line 235 documents this (`imbued.pseudo_built_in_support|3582467606` etc.). So:

- **Forbidden Flesh/Flame "Allocates X":** each notable is its own entry, e.g.
  `explicit.stat_2460506030|33645` = "Allocates Oath of Summer if you have the matching modifier on
  Forbidden Flame". **The pipe id IS the search filter id** — no base+`value.option` split is
  needed (and none exists in code; `_build_stat_groups` 225-226 supports `value.option` but nothing
  feeds it). `mod_to_pattern` is case-preserving and only blanks numbers (util.py 30-49), so the
  item's mod text matches the entry text exactly → `mapper.match` returns the pipe id. **[LIVE-adjacent:
  GGG's own stat dictionary is delivered in this pre-split form and the official trade site searches
  these mods by that exact id; not re-POSTed here — the sole-budget spot-check agent (D-0019 step 5)
  should confirm a `|`-id filter returns results.]**
- **Watcher's Eye auras:** plain `explicit.stat_*` (no pipe, no option), searched with a numeric
  `value.min`. e.g. `explicit.stat_556659145` = "#% increased Mana Recovery Rate while affected by
  Clarity".
- **Timeless-jewel seed:** the seed is the numeric `#` in a **conqueror-keyed pseudo id**:
  `explicit.pseudo_timeless_jewel_kaom` = "Commanded leadership over # warriors under Kaom"
  (Lethal Pride: kaom/rakiata/akoya/kiloava; Glorious Vanity: xibaqua/doryani/ahuana/zerphi; etc.).
  Correct search = `{"id":"explicit.pseudo_timeless_jewel_kaom","value":{"min":SEED,"max":SEED}}`.
  The conqueror is encoded by *which* pseudo id; the seed by min=max. The mapper resolves the id
  from the item's mod text today, but the query builder can only emit min (§3).

`statmap.py` needs **no change to matching** — it already resolves pipe/option and
`pseudo_timeless_jewel_*` ids from mod text. The gap is entirely (a) the registry doesn't exist,
(b) `_unique_query` doesn't require defining mods, (c) the picker deprioritises/mislabels them, and
(d) `_affix_defaults` has no min=max mode.

---

## 6. Touchpoints the Build phase MUST change (with line refs)

**New data + tool (D-0019 steps 1-2) — does not exist yet:**
- `public/api/_data/variant_uniques.json` — **absent** (`_data/` holds only `trade_stats.json` +
  `trade_items.json`). Needs: per variant-defining unique, its defining-mod stat ids (incl.
  pipe-option ids and per-conqueror timeless pseudo ids) + the poe.ninja `variant` label mapping.
- A rebuildable generator + a `refdata`-style loader for it.

**`public/api/_lib/querybuild.py`:**
- `_is_skill_level_mod` (111-113) + `_unique_value_filters` (462-472): generalise from
  "skill-level only" to **registry-driven required defining mods**; add timeless seed (min=max) +
  conqueror handling.
- `_unique_query` (475-484): inject the REQUIRED defining-mod filters for registry items (option
  pipe ids need no value; seed needs min=max).
- `_affix_tier` (116-126) + `affix_options` (365-428) + the `prefer` rule (385): mark registry
  defining mods `priority:"required"` / `prefer:true` and label them "defining/variant" so the
  picker prefills + highlights (D-0019 step 4). Uniques must stop blanket-`skip`ping them.
- `_affix_defaults` (159-169): add an **exact (min=max)** prefill mode for timeless seeds (today
  min-only, line 169).
- `price_unique_ninja` (620-661): make registry-aware — for Forbidden/Watcher, match the ninja
  variant to the *known* defining mod instead of token overlap; for timeless jewels, treat as
  **unpriceable-by-seed → trade link + no number** (the "no misleading number" guardrail) rather
  than a conqueror-level range.

**`public/api/_lib/poeninja.py`:**
- `unique_price` (350-407) + `_variant_tokens` (346-348): the token-overlap match + range fallback
  — replace/augment with registry-driven variant selection; timeless seed is out of poe.ninja's
  reach (route to link).

**`public/api/_lib/response.py`:**
- The rares/uniques picker payload (157-183): uniques currently emit `affixes`+`pseudo` but **no
  defining-mod designation and no `scopes`** (170). Surface the registry defining-mod flags (and
  the seed's exact-match intent) so the site/extension picker can render "defining mod (required)"
  (D-0019 step 4). `_price_obj` (41-57) may need to pass through new variant/seed `extra` fields.

**`public/api/_lib/models.py`:** likely add a field (e.g. `Item`/`PriceResult` variant-registry
info: defining mod ids, seed, conqueror) to carry registry data through the pipeline.

**No change needed:** `statmap.py` matching (already resolves the ids); `_build_stat_groups`
option plumbing (225-236, already supports `value.option` — just unused).

**Also touched but outside querybuild/response (note for the Build owner):** the site picker UI
(`core.js` / the stash skin) and the extension must render the required/defining rows; D-0019
step 4 ("picker shows defining mods") and step 5 (adversarial + sole-trade-budget live spot-check).

---

## 7. One load-bearing item to verify in Build (not resolvable under containment)
GGG's search endpoint accepting a `stat_id|optionid` filter id directly (Forbidden "Allocates"
mods). Strong [SOURCE] indirect evidence: the stat dictionary is saved verbatim from GGG in exactly
this pre-split form and the official trade site is built from it — but this audit did not POST to
`/api/trade/search`. Assign to the D-0019 step-5 sole-budget spot-check agent.
