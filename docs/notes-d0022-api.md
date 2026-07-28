# D-0022 item 1 - Dragonfang's Flight gem-level pricing (API/registry side)

Implementation + primary-source record for D-0022 item 1: price **Replica Dragonfang's Flight**
by its price-defining gem-level mod. Owned files touched:
`public/api/_lib/variantreg.py`, `public/api/_data/variant_uniques.json` (regenerated),
`tools/build_variant_registry.py`, `public/api/_verify.py`. `trade_stats.json` **unchanged**
(see sec 2). All findings below are PRIMARY-SOURCED from the live trade API and the committed
poe.ninja dumps; anything not source-derived is tagged **[INFERRED]**.

---

## 0. TL;DR

- The gem-level mod is **NOT an option stat**. PoE1 ships each `+# to Level of all <X> Gems` as
  an **individual** trade stat id (one `explicit.indexable_skill_N` per specific gem; one
  `explicit.stat_N` per damage tag). There is **no `base|opt` (pipe) form** for gem levels
  anywhere in the live dump. So D-0022's "OPTION stat that was SLIMMED out" premise is wrong.
- **`trade_stats.json` needed no change** (a NO-OP): every id we need is already in the slim
  bundle and resolves offline. Size delta = **0 bytes**.
- **Base "Dragonfang's Flight" does not exist** as a tradeable PoE1 unique (three primary
  sources). Only **Replica Dragonfang's Flight** ships in the registry.
- Recipe class = **roll-defined** (value = which gem the copy rolled; poe.ninja folds all gems
  into one line, so floor-only). The runtime matches the copy's OWN gem-level mod by text.
- **LIVE-VERIFIED** (1 search POST): the Determination query returns 14 listings, all carrying
  `stat.explicit.indexable_skill_67`.

---

## 1. PRIMARY-SOURCE: the gem-level stat is an INDIVIDUAL id, not an option

`GET https://www.pathofexile.com/api/trade/data/stats` (live, 2026-07-28) + the committed full
dump `research/data/trade_stats.json`, cross-checked with the poe.ninja UniqueAccessory dump
`research/data/ninja_uniques_uniqueaccessory.json`:

| Mod on the item | Live trade stat id | text |
|---|---|---|
| Replica: `+3 to Level of all Determination Gems` | `explicit.indexable_skill_67` | `+# to Level of all Determination Gems` |
| Replica: `+3 to Level of all Defiance Banner Gems` | `explicit.indexable_skill_242` | `+# to Level of all Defiance Banner Gems` |
| Replica: `+3 to Level of all Blade Vortex Gems` | `explicit.indexable_skill_138` | `+# to Level of all Blade Vortex Gems` |
| (base tag, [INFERRED] form) `Fire Skill Gems` | `explicit.stat_599749213` | `+# to Level of all Fire Skill Gems` |

Verified facts (each a live/committed-dump query, not memory):

- Each `indexable_skill_N` entry is a **plain** `{id, text, type}` with the full per-gem text.
  There is **no** `explicit.indexable_skill_67|<opt>` child anywhere. Contrast the real option
  stat Forbidden Flesh `explicit.stat_1190333629`, which exists ONLY as 165 `|opt` children.
- **`option-form (pipe) "Level of all" ids: 0`** in both the slim bundle and the LIVE dump.
- **287 `indexable_skill` entries** live == **287** in the slim bundle (identical count).
- All **283** gem mods poe.ninja enumerates for Replica Dragonfang resolve through the slim
  `StatMapper` (0 misses). The 5 damage-tag ids (`stat_599749213`/`_1078455967`/`_1147690586`/
  `_619213329`/`_67169579`) also resolve.

Conclusion: the mod is priced by matching the copy's own `+# to Level of all <X> Gems` line to
its individual id and searching with `value:{min:roll}` - the roll-defined/mod-variant pattern,
NOT the notable-jewel OPTION pattern.

## 2. trade_stats.json: NO-OP (nothing was slimmed out)

D-0022 said the option stat "was SLIMMED out of the bundled trade_stats.json - must be re-added."
Primary source disproves this: there is no option stat, and every id the recipe needs is already
present and offline-resolvable (sec 1). `public/api/_data/trade_stats.json` is therefore
**unchanged** - size delta **0 bytes**. Re-adding anything would be dead weight. The slim/full
`StatMapper` equality check in `_verify.py` phase A still holds.

## 3. Base "Dragonfang's Flight" does NOT exist (only Replica ships)

D-0022 asked to price base Dragonfang's Flight too ("`+# to Level of all <tag> Skill Gems`").
Three PRIMARY sources agree it is **not a tradeable PoE1 unique**:

1. **LIVE `GET /api/trade/data/items`** (the authoritative trade-name catalog): the only
   Dragonfang entry is `Replica Dragonfang's Flight` (Onyx Amulet). "Flight" uniques total:
   Replica Dragonfang's Flight, Garukhan's Flight, Victario's Flight. No base Dragonfang.
2. **LIVE search POST** `name:"Dragonfang's Flight"` -> HTTP **400** `{"code":2,"message":
   "Unknown item name"}`.
3. **poe.ninja** UniqueAccessory dump: only `Replica Dragonfang's Flight`.

So the base is **removed** from the registry (a phantom entry would generate a 400-ing query).
Secondary reason it needs no recipe even in principle: a per-tag `... Skill Gems` mod carries the
word "Skill", so `querybuild._is_skill_level_mod` already routes it through the generic
`_unique_value_filters` path - only the Replica's `... Gems` (no "Skill") form was invisible to
that path, which is the real gap. **[INFERRED]** the owner's per-tag description came from
community memory/wiki; the runtime `_is_gem_level_mod` still matches the per-tag form, so a
future per-tag gem-level unique is a one-line roster add. **FLAGGED to owner** (reconcile
D-0022's base clause).

## 4. The recipe (registry + runtime)

**Registry** (`variant_uniques.json`, generated by `build_variant_registry.py`):

```
name  : "Replica Dragonfang's Flight"   base: ["Onyx Amulet"]   class: "roll-defined"
defining[0] = { stat_id: "explicit.indexable_skill_138" (rep, documentation only),
                kind: "gem-level", axis: "gem", family_size: 289,
                from: { group:"explicit", match:"gem-level",
                        pattern:"+# to Level of all <Gem> Gems", emit:"roll-min" } }
ninja_variant_rule: floor-only   (poe.ninja folds all gems -> one 15c/7216-listing line)
confidence_policy.cap: "low"
```

**Runtime** (`variantreg.build_variant`, roll-defined/mod-variant branch): a new FIRST-priority
dispatch case when any `defining[].from.match == "gem-level"`:

```python
gem_level = any((d.get("from") or {}).get("match") == "gem-level" for d in defining)
if gem_level:
    picked = [r for r in resolved if _is_gem_level_mod(r[3])]
    label  = picked[0][3] if picked else "gem-level variant"
```

with `_is_gem_level_mod(text) = "to level of all" in t and t.endswith("gems")` (matches both the
per-gem `... Gems` and per-tag `... Skill Gems` forms; rejects the item's fixed
resistance / reservation-efficiency / reduced-attribute mods, none of which carry "to level of
all"). It is checked first so it wins over the aura/presence/def-id/own-rolls dispatch, and the
own-rolls fallback is guarded with `and not gem_level` so a gem-level item never folds its fixed
mods into the query. Only the ONE gem-level mod becomes a required filter
(`{id: indexable_skill_N, value:{min:roll}}`).

No change was needed in `querybuild.py`: the existing `_variant_for` -> `_unique_query` (adds
`var.filters`) and `affix_options` (flags `locked_by_idx` as defining/required/prefilled) paths
are generic and pick this up. The item-row `variant_info` block and the picker "defining" row
follow automatically.

**End-to-end behaviour**
- Replica with a Determination copy -> query `name + Onyx Amulet + {indexable_skill_67 min:3}`;
  poe.ninja floor 15c at LOW confidence (`unique-ninja-floor`); the trade link prices the exact
  gem. A Spark copy emits `indexable_skill_27` instead (copy-specific, proven in `_verify.py`).

## 5. Harvest gap + guard (task 6)

**The gap (a CLASS bug):** poe.ninja folds every gem version of a gem-level unique into ONE line
with `variant = null` (Replica Dragonfang: 283 `optional:true` `+# to Level of all <Gem> Gems`
modifiers on a single line, 15c/7216 listings). `build_variant_registry.durable_ninja_names`
keys on names with **>= 2 distinct variant LABELS**, so it never surfaces this class for the
roster - exactly why the harvest missed Replica Dragonfang.

**The guard** (`detect_folded_gem_variants`, wired into `assemble`): scan the cached dumps for the
FOLD SIGNATURE - a line whose `explicitModifiers` carry `>= 3` optional `to Level of all ... Gems`
entries - and WARN (non-fatal, stderr) about any such name absent from the hand-authored roster.
Two coverage fields record the result:
`folded_gem_variant_names: ["Replica Dragonfang's Flight"]` and
`folded_gem_variant_unregistered: []` (must stay empty; a future league's new gem-level unique
would appear here and trip the warning). Detection only - the gem axis needs a StatMapper-matched
filter, not a ninja variant line, so recipes stay hand-authored (`do not over-engineer`).

## 6. LIVE VERIFY (2026-07-28, 1 search POST of the 8 budget)

Query built by the REAL `PublicPricer._unique_query` (dogfooded), status `online`, league
`Allflame`, real User-Agent, rate headers honoured (IP state stayed 1/5 in the 10s window):

```
POST /api/trade/search/Allflame
  {"query":{"status":{"option":"online"},"name":"Replica Dragonfang's Flight",
            "type":"Onyx Amulet",
            "stats":[{"type":"and","filters":[{"id":"explicit.indexable_skill_67",
                                               "value":{"min":3}}]}]},
   "sort":{"price":"asc"}}
  -> total_found: 14
GET /api/trade/fetch/<3 ids>  ->  all three items carry, in explicitMods (objects):
   {"description":"+3 to Level of all Determination Gems",
    "hash":"stat.explicit.indexable_skill_67"}
   prices 10c / 15c / 60c
```

All fetched listings carry **exactly** the Determination gem-level mod (`indexable_skill_67`) -
not a different gem. The 10/15/60c spread for one gem, vs poe.ninja's folded 15c floor, is the
concrete justification for D-0022: the folded ninja line is only a floor; the per-gem price comes
from this defining-mod trade search. (A 2nd POST for the base name 400'd - sec 3.)

## 7. Verification / regression

- `python public/api/_verify.py` (offline phases A + variant): **ALL CHECKS PASSED**, incl. the
  new Replica-exact-filter, floor-cap, variant-label, copy-specific-Spark, picker-defining-row,
  and the three `_is_gem_level_mod` matcher-contract checks. Non-vacuous: the Spark check fails if
  the branch emitted a fixed id instead of the copy's own gem.
- `python tools/build_variant_registry.py --offline`: 41 items, deterministic; diff vs the prior
  artifact = only the timestamp, the two coverage counts, the Replica entry, the two folded-gem
  coverage fields, and the roll-defined class note.
- `python tests.py` (local app): green (untouched; changes are public-build only).
