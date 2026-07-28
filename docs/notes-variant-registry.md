# Variant-unique registry -- build notes (D-0019)

**Artifact:** `public/api/_data/variant_uniques.json` (committed, generated)
**Generator:** `tools/build_variant_registry.py`
**League harvested:** Allflame  ·  **Ninja dumps:** `research/data/ninja_uniques_*.json` (2026-07-27)
**Stat schema validated against:** `public/api/_data/trade_stats.json` (the file the runtime reads)

This is DivTally's OWN variant-unique database. At appraisal time the runtime reads ONLY this
JSON (no internet source) to decide, for each price-variant-sensitive unique, how to turn the
build's own copy into a faithful trade search and how to map it onto poe.ninja's enumeration.
It implements D-0019's step (1)-(2): "build our own item database ... generated artifact +
rebuildable tool," harvested from primary data, with community additions merged only where a
primary recipe exists.

---

## 1. How to (re)build

```
python tools/build_variant_registry.py            # OFFLINE: cached ninja dumps (deterministic)
python tools/build_variant_registry.py --refresh  # re-fetch ninja Unique* overviews (polite)
python tools/build_variant_registry.py --check     # build + validate in memory, do NOT write
python tools/build_variant_registry.py --league <Name>
```

The tool is **deterministic**: fixed class+name ordering, sorted inner lists. Two runs produce
byte-identical `items` (only the `_meta.generated` timestamp moves -- verified). It **fails loud**
(non-zero exit) if any defining stat id does not resolve or any durable ninja variant name is
missing, so a broken registry cannot ship. It NEVER calls pathofexile.com/trade (CLAUDE.md
RULE 4); poe.ninja overview + index-state are the only network calls, and only with `--refresh`
/ live-league; the committed build ran fully offline against the cached dumps.

---

## 2. Per-item schema (what the runtime consumes)

```jsonc
{
  "name": "Forbidden Flame",
  "class": "notable-jewel",           // seed-jewel | notable-jewel | socket-defined |
                                      //   roll-defined | mod-variant | links
  "base": ["Crimson Jewel"],          // primary-confirmed base(s) (trade_items.json)
  "source": "primary-stat",           // ninja-harvest | primary-stat | crosscheck (why included)
  "variant_sensitive": true,
  "also_links": true,                 // (optional) ALSO 5L/6L-sensitive (engine adds the filter)
  "defining": [                       // the REQUIRED defining filter(s) for the trade search
    { "stat_id": "explicit.stat_2460506030",   // base id (option: has pipe children in schema)
      "kind": "option",               // option | value | seed
      "axis": "ascendancy-notable",
      "option_count": 165,
      "from": { "group": "explicit",  // Item.mod_src group to scope StatMapper.match in
                "match": "option-by-name",
                "pattern": "Allocates <Notable> if you have the matching modifier on ...",
                "emit": "option-split",         // how to turn the matched id into a filter
                "note": "..." } } ],
  "defining_rule": "ninja-variant-label",       // (optional) generic rule instead of fixed ids
  "ninja_variant_rule": {             // how to map an owned copy -> the overview variant string
    "strategy": "floor-only",         // floor-only | map-count | map-base | map-variant
    "axis": "seed",
    "match": "<prose instruction>",
    "observed_variants": [ {"variant":"Chaos","chaos":90.0,"listing_count":493}, ... ],  // harvested
    "ninja_floor_chaos": 20.0, "ninja_floor_listings": 1108, "harvested": true },
  "confidence_policy": { "ninja":"floor-low", "cap":"low", "trade":"...", "unmatchable":"none-link-only",
                         "note":"..." },
  "flags": ["elegant-hubris-displayed-seed-x20"],   // (optional)
  "crosscheck_tags": ["[NOT FROM SOURCE - poewiki ...]"],  // (optional) community-sourced claim(s)
  "notes": "..."
}
```

`emit` tokens: `option-split` (matched id is `base|opt` -> `{id:base, value:{option:opt}}`),
`seed-exact` / `count-exact` (`{min:N,max:N}`), `roll-min` (`{min:roll}`), `presence` (`{min:1}`).

---

## 3. Class taxonomy -> runtime strategy

| class | who | defining filter | poe.ninja handling |
|---|---|---|---|
| **seed-jewel** | the 5 timeless jewels | `pseudo_timeless_jewel_<conq>` seed, **exact** min=max | floor-only, hard-capped LOW (no seed split) |
| **notable-jewel** | Forbidden Flame/Flesh, Impossible Escape, Thread of Hope | OPTION stat (`base|opt`) resolved by notable/keystone/size **name** | floor-only (ninja can't split) |
| **socket-defined** | Voices + 6 abyssal-socket uniques | exact COUNT (`Has # Abyssal Sockets` / `Adds # Small Passive Skills...`) | map-count, by **observed** count (labels not literal -- sec 5) |
| **roll-defined** | Watcher's Eye, Megalomaniac, Sublime Vision, Aul's Uprising, Split Personality, That Which Was Taken | the copy's own rolled mod family (aura combo / notables / own rolls) | floor-only; price from the copy's mods |
| **mod-variant** | element/type/base variants poe.ninja enumerates | usually none -- the ninja variant LINE is the price | map-variant / map-base (owned copy -> variant label) |
| **links** | 5L/6L price swing (237 names) | handled GENERICALLY by the engine's `max_link>=5` filter (D-0003) | **NOT enumerated here** (see sec 5) |

---

## 4. Coverage (this build)

- **Registry items: 40.** By class: seed-jewel 5, notable-jewel 4, socket-defined 7,
  roll-defined 6, mod-variant 18.
- **By inclusion source:** ninja-harvest 10, primary-stat 19, crosscheck 11.
- **Defining stat ids (+ samples) validated against the shipped schema: 52 -- ALL resolve.**
  (Independent re-check, not the tool's own: PASS.)
- **Durable ninja enumeration coverage: 12 / 12 multi-variant + 3 / 3 base-variant names present.**
  These are the non-`Foulborn` names poe.ninja lists with >=2 `variant` strings or >=2 bases -- the
  set that MUST be in the registry. All present (validation 2 PASS).
- **Cross-check additions dropped by the resolution gate: 0** (every rostered community item's
  defining family resolved in the primary schema).
- **Deliberately excluded:** 237 `Foulborn ` league-transient copies (sec 5); 183 pure links-variant
  names (engine-handled, sec 5); ~1,406 ninja names harvested total.

### Full roster
- **seed-jewel (5):** Glorious Vanity, Lethal Pride, Brutal Restraint, Militant Faith, Elegant Hubris.
- **notable-jewel (4):** Forbidden Flame, Forbidden Flesh, Impossible Escape, Thread of Hope.
- **socket-defined (7):** Voices, Bubonic Trail, Tombfist, Lightpoacher, Shroud of the Lightless,
  Command of the Pit, Hale Negator.
- **roll-defined (6):** Watcher's Eye, Megalomaniac, Sublime Vision, Aul's Uprising,
  Split Personality, That Which Was Taken.
- **mod-variant (18):** Impresence, Doryani's Invitation, Volkuur's Guidance, Mageblood,
  Yriel's Fostering, Atziri's Splendour, The First Crest (7 ninja-harvest); Grand Spectrum,
  Combat Focus, Precursor's Emblem (3 base-variant); Circle of Nostalgia/Guilt/Anguish/Fear/Regret,
  Vessel of Vinktar, Doryani's Delusion, The Light of Meaning (8 crosscheck).

---

## 5. Key decisions (defensible, recorded)

1. **Foulborn excluded (237 names).** poe.ninja mints a per-league `Foulborn <base>` copy with its
   own `variant` label; variant-ninja.md flags these `[INFERRED]` league noise that groups under a
   *different* name and is transient. A **durable** own-database (D-0019) excludes them; regenerate
   per league if a future consumer wants them. Counted in `_meta.coverage.excluded_foulborn_names`.

2. **`links` is not enumerated as registry entries.** 183 non-Foulborn uniques swing 5L/6L this
   league, but the engine ALREADY adds `socket_filters.links.min` for any `max_link>=5` item
   (D-0003) -- the complete recipe, no defining MOD needed. Enumerating them would bloat the
   registry with rows that carry no extra instruction. Items that ALSO vary by another axis carry
   `also_links:true` (Atziri's Splendour, Yriel's Fostering, Doryani's Delusion). The `links` class
   stays in the enum for completeness but has 0 standalone members by design.

3. **Cross-check gate implemented as code.** D-0019: "merge cross-check additions ONLY where a
   primary-data recipe exists (defining stat id resolvable)." `add_gated()` builds each community
   item's defining family and DROPS it (recording the reason in `coverage.crosscheck_dropped`) if it
   resolves to 0 schema stats. Every community roster row carries a `crosscheck_tags`
   `[NOT FROM SOURCE - <where>]` flag at point of use; wiki claims are never presented as primary.
   **Editorially excluded** (kept OUT of the roster, not gate-dropped): **Storm Secret** (community
   "pen variant" has no confirmed variant axis; its pen family is generic, not item-specific) and
   **Voidforge** (re-randomized hit damage; no fixed filter, not ninja-enumerated). Both are
   `[NOT FROM SOURCE - poewiki]` with no actionable primary recipe.

4. **Socket-count map is data-driven, NOT label-parsed.** poe.ninja's `<N> Jewel(s)` label is NOT
   always the literal socket count: **Shroud of the Lightless**'s "1 Jewel" line carries
   `Has 3 Abyssal Sockets` (Bubonic Trail's are literal: 1<->1, 2<->2). The tool reads the actual
   `Has # Abyssal Sockets` value from each variant line's `explicitModifiers` into
   `observed_variants[].abyssal_count`, and `ninja_variant_rule` tells the runtime to map by that
   OBSERVED count, not the label. This is why socket-defined items get BOTH an exact-count trade
   filter (the reliable price) and the ninja count map (a cross-ref).

5. **Option-stats are pre-flattened (`base|opt`), so validation checks pipe children.** PoE1 ships
   Forbidden/Impossible-Escape/Thread-of-Hope/cluster-grant option stats as `explicit.stat_X|<opt>`
   entries (no bare `explicit.stat_X`). The registry records the **base** id + `kind:option`; the
   validator confirms the base has >=1 pipe child (Forbidden 165, Impossible Escape 48, Thread of
   Hope 5). At runtime StatMapper resolves the item's mod text -> the full `base|opt` id; `emit:
   option-split` says to search it as `{id:base, value:{option:opt}}`.

6. **Elegant Hubris displays seed x20.** Its "Commissioned # coins" line shows `internal_seed * 20`;
   the trade stat matches the DISPLAYED value, so the recipe uses the displayed number as-is
   (`flags:["elegant-hubris-displayed-seed-x20"]`, `from.x20:true`). The other four display the raw
   seed. Parsing the display string (never the poe.ninja-only structured seed) is the common
   denominator for both the ninja and PoB input paths (timeless-jewels.md sec 3).

7. **Timeless conquerors are data-driven from the schema.** All 4 conqueror seed ids per jewel
   (3 live + 1 legacy) are pulled from the `pseudo_timeless_jewel_*` entries grouped by flavour
   template, so the recipe self-validates. Live/legacy split: `[SRC:ninja]` for Elegant Hubris
   (ninja lists only Cadiro/Caspiro/Victario), `[INFERRED]` for the analogous 4th elsewhere
   (Zerphi/Kiloava/Deshret/Venarius/Chitus marked `live:false`). Legacy ids stay valid for Standard
   copies. Militant Faith carries a note for its second (Devotion/keystone) axis.

8. **mod-variant items carry `defining:[]` + a `defining_rule`.** Their price recipe is the ninja
   variant/base LINE itself (mapped in `ninja_variant_rule` from the live harvest), not a fixed
   trade filter -- so no defining stat id is needed to price them. `defining_rule:"ninja-variant-
   label"` / `"ninja-base-line"` records that. (The cross-check mod-variants Circles/Vinktar/
   Delusion/Light-of-Meaning DO carry a resolved defining family, because ninja did NOT enumerate
   them this league, so the family IS their actionable recipe.)

---

## 6. Provenance / source tiers (owner EVIDENCE RULE)

- **PRIMARY** = poe.ninja Unique* economy API (variant/base/links enumeration, floor prices,
  listing counts -- all `[OBSERVED]` in the dumps) + the bundled trade stat schema (every defining
  stat id validated against `trade_stats.json`) + `trade_items.json` (name->base grounding). The
  per-class defining recipes come from `docs/research/variant-stats.md` (all `[SRC]`) and
  `docs/research/timeless-jewels.md`.
- **CROSS-CHECK** = the community roster in `docs/research/variant-crosscheck.md`. Merged only where
  the recipe resolves (sec 5.3); each surviving row carries its `[NOT FROM SOURCE - <where>]` tag in
  `crosscheck_tags`. No community claim is presented alongside primary data as if equally
  authoritative.
- `_meta.source_tier_policy` restates this inside the artifact.

---

## 7. Open items for the CONSUMER phase (this task did NOT touch runtime code)

These are flagged for whoever wires the registry into `querybuild.py` / `poeninja.py` /
`response.py` (D-0019 steps 3-5); they are recorded here so they are not lost:

1. **Option wire-format fork (needs the D-0019 step-5 live spot-check).** `variant-audit.md` sec 5/7
   says the pre-split id `explicit.stat_X|opt` may be POSTed **verbatim** as `{"id":"stat_X|opt"}`;
   `variant-stats.md` sec 0.1 recommends the **split** form `{"id":"stat_X","value":{"option":opt}}`.
   The registry records the BASE id + `option_count` + `emit:option-split` (the safe canonical
   form), losing no information -- but the consumer MUST verify one live search before shipping
   (the sole-trade-budget agent). Both forms are constructible from the registry.
2. **Timeless seed needs an exact (min=max) prefill mode** in `_affix_defaults` (audit sec 3) --
   the current picker can only prefill `min`. The registry's `emit:seed-exact` is the contract.
3. **Confidence override for floor-only classes.** seed-jewel / notable-jewel / roll-defined carry
   `confidence_policy.cap:"low"`; the consumer must override `_confidence_from_lc` (whose huge
   listing counts would mis-rate the floor as "high") -- this is the whole point for timeless jewels.
4. **Heroic Tragedy** is a 6th `Timeless Jewel`-base unique in `trade_items.json` but has no ninja
   line and no `pseudo_timeless_jewel_*` conqueror stat -- **out of scope** (link-only), per
   timeless-jewels.md sec 9. Not in the registry by design.
5. **Implicit-scoped pass** (Precursor's Emblem / synthesis Circles) -- variant-stats.md sec 12
   notes `affix_options` never iterates `implicit_mods` today; base-pin covers Precursor's Emblem
   for now (its implicit follows the base), but a full implicit variant would need that pass.

---

## 8. Validation results (this build)

```
VALIDATION 1 (every defining stat_id + sample resolves in the shipped schema): PASS  (52 ids)
VALIDATION 2 (every durable ninja multi/base-variant name present):            PASS  (12/12 + 3/3)
VALIDATION 3 (per-item shape + class enum + defining kind enum):               PASS  (40 items)
Determinism (items byte-identical across two runs):                            PASS
```
Run `tools/build_variant_registry.py --check` (self-validation, fails loud) to reproduce 1-2.
