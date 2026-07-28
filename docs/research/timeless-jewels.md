# Timeless jewels - why they are the hardest item to price, and how DivTally should price them

Deep-dive research for **D-0019** (variant-unique registry + timeless-jewel handling). The owner's
note: *"timeless jewels are worse - research why."* This is the why, from primary sources, plus the
recommended pricing policy.

**Provenance tags** (project convention, same as `taxonomy.md` / `economy.md`):
- **[SRC:trade-stats]** - read from `research/data/trade_stats.json` (the bundled trade stat schema).
- **[SRC:trade-items]** - read from `research/data/trade_items.json` (bundled trade item/type list).
- **[SRC:char]** - read from a live poe.ninja character item in `research/data/char_poe1*.json`.
- **[SRC:pob]** - read from `research/data/pob_sample.xml` (a Path of Building export).
- **[SRC:ninja]** - read live from the poe.ninja PoE1 `UniqueJewel` economy overview
  (`stash/current/item/overview?type=UniqueJewel`), probed 2026-07-27, league Allflame. No dump was
  committed (file-ownership scope), so the numbers here are the probe's stdout, reproducible.
- **[INFERRED]** - my reasoning from the above, not a fact any single source states outright.
- **[NOT FROM SOURCE - <where>]** - community/wiki/tool lore; cross-check context only, never mixed in
  as if it were source-derived (global RULE: flag non-source math/claims loudly at point of use).

---

## 0. TL;DR - the policy (the rest of the doc is the evidence)

A timeless jewel's value is **`f(exact seed, conqueror, jewel type)`**. Two copies of "Glorious
Vanity" with different seeds are **different items** with different prices - the way two different rare
rings are different items. Name-only pricing is therefore meaningless, and - critically - **poe.ninja
gives exactly one price per jewel NAME** (no conqueror split, no seed), so the ninja number is a
floor across *every* seed of *every* conqueror, not this jewel's price. [SRC:ninja]

DivTally should, for any item with `baseType == "Timeless Jewel"`:

1. **Build the honest exact search.** Parse the conqueror + the displayed seed number out of the
   item's own explicit line, map the conqueror to its trade stat id, and add a
   `{min: seed, max: seed}` filter to a `name` + `type` query. This is the *truthful* search - thin
   (often 0-few live listings), but it prices *this* jewel. **(a)**
2. **Attach the poe.ninja name-level number only as a LOW-confidence floor**, labelled as "cheapest
   copy of any seed of this jewel", never as the item's price, and never at high confidence even
   though the listing count is enormous. **(b)**
3. **Always attach the clickable trade link** for the exact-seed query, so the user (or the
   extension, on their machine) can see the real listings. **(c)**
4. If the seed/conqueror can't be parsed -> **link + no number**, exactly as every other unpriceable
   row (CLAUDE.md guardrail).

This is D-0019 verbatim ("timeless jewels searched by exact seed (min=max) + keystone variant;
unmatchable -> link + no number as ever"), refined by one evidence correction: ninja's PoE1 data is
**name-level, not keystone-level** (section 5), so the floor is even coarser than D-0019 assumed and
must be capped at low confidence.

---

## 1. What a timeless jewel is

Five uniques, all `baseType "Timeless Jewel"`, `frameType 3` (unique), that socket into passive-tree
jewel sockets (`inventoryId "PassiveJewels"`). [SRC:char] [SRC:trade-items] Each is listed as its own
unique **name** under `type "Timeless Jewel"` in the trade item list: [SRC:trade-items]

| Jewel | Legion it "Conquers" | Conqueror-line flavour template | version id |
|---|---|---|---|
| **Glorious Vanity** | the Vaal | `Bathed in the blood of # sacrificed in the name of <C>` | 1 |
| **Lethal Pride** | the Karui *[NOT FROM SOURCE - community]* | `Commanded leadership over # warriors under <C>` | 2 *[INFERRED]* |
| **Brutal Restraint** | the Maraketh *[NOT FROM SOURCE - community]* | `Denoted service of # dekhara in the akhara of <C>` | 3 *[INFERRED]* |
| **Militant Faith** | the Templars *[NOT FROM SOURCE - community]* | `Carved to glorify # new faithful converted by High Templar <C>` | 4 *[INFERRED]* |
| **Elegant Hubris** | the Eternal Empire | `Commissioned # coins to commemorate <C>` | 5 |

- `version 1 = Glorious Vanity` and `version 5 = Elegant Hubris` are **[SRC:char]** (the two items in
  the sample data); the 2/3/4 order is **[INFERRED]** from the standard listing order.
- "Conquered by the Vaal" / "Conquered by the Eternal Empire" are **[SRC:char]** (and corroborated by
  the icon filenames `VaalCivilization` / `EternalEmpireCivilization` **[SRC:char]**). The Karui /
  Maraketh / Templar legions for the other three are **[NOT FROM SOURCE - community]** - and don't
  matter for pricing (the legion is implied by the name; it is not a searchable field).

### Why it's harder than a normal unique
A normal unique (Headhunter) has a fixed identity; you price it by name (+ maybe a variant roll). A
timeless jewel's mods are **not on the jewel** - the jewel is an instruction that **deterministically
rewrites every passive skill inside its radius** on the tree. Two inputs decide the rewrite:

1. **the conqueror** `<C>` (3 live options per jewel) - picks *which* transformation table applies, and
2. **the seed** `#` - a number that selects, per affected passive, exactly which notable/keystone/stat
   it becomes.

The jewel itself displays only the seed + conqueror; the actual value lives in *what the tree turns
into* around wherever you socket it. So its market price is set by whether its specific seed produces
a sought-after cluster of transformed notables - which is why buyers shop by **exact seed**, not by
name. That determinism (same seed + same conqueror + same socket = same tree, every time) is what the
structured fields in section 3 encode; the exact seed->notable table is in the game data and is
**[NOT FROM SOURCE]** here (it isn't in any bundled dump - see section 8).

---

## 2. The combinatorial size of the problem (from source)

poe.ninja's item template lists the **displayed seed range** for each live conqueror. [SRC:ninja]
(Probed 2026-07-27, Allflame.)

| Jewel | Live conquerors + displayed-seed span [SRC:ninja] |
|---|---|
| Glorious Vanity | Xibaqua (120-7945), Ahuana (120-7986), Doryani (109-7998) |
| Lethal Pride | Kaom (10014-17983), Akoya (10032-17988), Rakiata (10004-17932) |
| Brutal Restraint | Balbala (514-8000), Nasima (548-7970), Asenath (501-7994) |
| Militant Faith | Maxarius (2007-9982), Avarius (2037-9978), Dominus (2003-9972) + Devotion axis (sec. 6) |
| Elegant Hubris | Cadiro (2040-159840), Caspiro (4040-159220), Victario (2460-159700) |

So a single jewel name spans **~8,000 seeds x 3 conquerors ~= 24,000 distinct items**, and Elegant
Hubris spans ~160,000 displayed values (see the x20 quirk, section 3). Every one of those is a
genuinely different item that can be worth 1c or hundreds of divines. That is why a name search means
nothing: it lumps ~24,000 items into one row.

---

## 3. How the item encodes the seed - and the Elegant Hubris x20 trap

A live jewel carries **two parallel representations**. Worked example, the Elegant Hubris in the
sample character (`char_poe1.json`): [SRC:char]

**(A) The human-readable display strings** (`explicitMods`) - also exactly what a PoB export gives
(`pob_sample.xml`, same text) [SRC:char] [SRC:pob]:
```
"Commissioned 29120 coins to commemorate Caspiro\nPassives in radius are Conquered by the Eternal Empire"
"Historic"
```

**(B) The structured deterministic parameters** (`mods.explicit[].stats`) [SRC:char]:
```jsonc
"id": "UniqueJewelAlternateTreeInRadiusEternal",
"stats": {
  "local_unique_jewel_alternate_tree_version":  5,     // 5 = Elegant Hubris
  "local_unique_jewel_alternate_tree_seed":     1456,  // the INTERNAL seed
  "local_unique_jewel_alternate_tree_keystone": 3,     // 3rd conqueror (Caspiro)
  "local_jewel_effect_base_radius":             1500,  // "Large"
  "local_is_alternate_tree_jewel":              1
}
```

Cross-check with the Glorious Vanity sample (`char_poe1_unicode.json`): [SRC:char]
```
display:    "Bathed in the blood of 3496 sacrificed in the name of Xibaqua ..."
structured: version 1 (Glorious Vanity), seed 3496, keystone 1 (Xibaqua)
```

### The trap: the displayed number is NOT the internal seed for Elegant Hubris
- Glorious Vanity: **displayed 3496 == internal seed 3496** (x1). [SRC:char]
- Elegant Hubris: **displayed 29120 == internal seed 1456 x 20** (x1456 * 20 = 29120). [SRC:char]

Elegant Hubris multiplies its internal seed by **20** for the "coins" display; the other four display
the raw seed. **[INFERRED - two-point derivation]**: proven directly for Elegant Hubris and Glorious
Vanity from the sample items; the "the other three are x1 like GV" generalisation is [INFERRED] from
the seed spans in section 2 lining up with x1 display. Corroborated by ninja's displayed EH span
(2040-159840) being ~20x the ~100-8000 span of the raw-seed jewels. [SRC:ninja]

**Consequence for pricing (load-bearing):** the trade site searches the **displayed** value, because
its stat text ("Commissioned # coins...") matches the item's **displayed** mod line. So the query
value for the Caspiro example is **29120**, not 1456. **Build the trade filter from the display-string
parse (A), never from the structured `local_..._seed` (B)** - for Elegant Hubris the structured seed
(1456) would return zero results. The display parse is also the only representation available on the
PoB import path (B is poe.ninja-only), so it is the correct common denominator for both inputs.
[SRC:char] [SRC:pob] [INFERRED]

The structured fields (B) are still useful for *identification/validation* and for a picker display
(unambiguous jewel + conqueror index), but they are **not** the query input.

---

## 4. How the trade site searches a timeless jewel

There is **no** "timeless jewel" special UI and **no** separate searchable "seed" or "Conquered by"
field. Confirmed: grep for `Conquered by` / `Passives in radius` in the stat schema -> **0 matches**;
grep for `timeless` / `seed` in `trade_data_filters.json` -> **0 matches**. [SRC:trade-stats]
The seed is searched as an ordinary **numeric explicit stat**, one stat id **per conqueror**, with the
conqueror baked into the id and the flavour text: [SRC:trade-stats]

- `explicit.pseudo_timeless_jewel_caspiro` -> text `"Commissioned # coins to commemorate Caspiro"`
- `explicit.pseudo_timeless_jewel_xibaqua` -> text `"Bathed in the blood of # sacrificed in the name of Xibaqua"`

The `#` is the **displayed** seed; set `value.min == value.max` to pin an exact seed. Because each
conqueror is a distinct stat id, choosing the id *also* fixes the conqueror (and therefore the jewel).

### The 20 classic-conqueror stat ids [SRC:trade-stats]
Grouped by jewel via their flavour template. Three are **live**; the fourth per jewel is a
**legacy** name (still in the schema for Standard-league legacy copies). The live/legacy split is
**[SRC:ninja]** for Elegant Hubris (ninja's live item template lists only Cadiro/Caspiro/Victario -
Chitus is absent) and **[INFERRED]** for the analogous fourth name on the other four jewels.

| Jewel | Live conquerors (stat id suffix) | Legacy (stat id suffix) |
|---|---|---|
| Glorious Vanity | `_xibaqua`, `_doryani`, `_ahuana` | `_zerphi` |
| Lethal Pride | `_kaom`, `_rakiata`, `_akoya` | `_kiloava` |
| Brutal Restraint | `_asenath`, `_nasima`, `_balbala` | `_deshret` |
| Militant Faith | `_avarius`, `_maxarius`, `_dominus` | `_venarius` |
| Elegant Hubris | `_cadiro`, `_victario`, `_caspiro` | `_chitus` |

Full id = `explicit.pseudo_timeless_jewel_<suffix>`. The suffix is simply the lower-cased conqueror
name, so the mapping is mechanical - **but build the `{conqueror -> stat id}` table by parsing the
bundled `trade_stats.json` at load** (data-driven, robust to any spelling quirk), the same way
`statmap.py` already indexes stats. [INFERRED - recommended]

### The exact trade query (worked, Caspiro / 29120)
Extends the existing `PublicPricer._unique_query` (name + base) with the seed stat:
```jsonc
{
  "query": {
    "status": {"option": "available"},          // D-0017 default
    "name":   "Elegant Hubris",
    "type":   "Timeless Jewel",
    "stats": [
      {"type": "and", "filters": [
        {"id": "explicit.pseudo_timeless_jewel_caspiro",
         "value": {"min": 29120, "max": 29120}}   // displayed seed, pinned
      ]}
    ]
  },
  "sort": {"price": "asc"}
}
```
The `name`/`type`/`{min,max}`/`value` shapes are all already used and verified in `querybuild.py`
(`_unique_query`, `_unique_value_filters`), so this is additive, not new machinery. [SRC:code]

---

## 5. How poe.ninja represents them - the decisive finding

D-0019 asked: *do ninja variants capture the keystone but not the seed?* **Answer, from the live
overview: ninja captures NEITHER.** For PoE1 timeless jewels poe.ninja returns **exactly one
aggregate line per jewel NAME, with no `variant` key at all**. [SRC:ninja]

Probed 2026-07-27, Allflame, `type=UniqueJewel` (153 lines total, 5 timeless):
```
Elegant Hubris   chaos 121.2  div 1.0   listingCount 7009   (one line, no variant)
Lethal Pride     chaos  67.5  div 0.56  listingCount 6189
Glorious Vanity  chaos  29.8  div 0.25  listingCount 9766
Brutal Restraint chaos  26.0  div 0.21  listingCount 7342
Militant Faith   chaos  11.0  div 0.09  listingCount 8657
```

Proof it stores no seed/conqueror: the Elegant Hubris line's `explicitModifiers` are the **full
possible ranges of all three conquerors**, each flagged `optional`, not any real listing's value:
[SRC:ninja]
```
"Commissioned (2040-159840) coins to commemorate Cadiro ..."   optional
"Commissioned (4040-159220) coins to commemorate Caspiro ..."  optional
"Commissioned (2460-159700) coins to commemorate Victario ..." optional
```

And ninja *does* use the `variant` field for other jewels when it wants to (e.g. **Voices** splits by
passive count; **Foulborn** jewels have 3-4 variants each) [SRC:ninja] - so the omission for timeless
jewels is deliberate: the seed space is too large to enumerate, so ninja collapses it.

**What the ninja number actually is:** the ~cheapest/typical of **6,000-9,700 listings spanning every
conqueror and every seed** of that jewel name. For Militant Faith that is `11c`; a *good-seed*
Militant Faith is worth many divines. So the ninja figure is a **floor for the junk-seed copy**, and
its huge `listingCount` makes the existing `_confidence_from_lc` mis-rate it as **"high"** - which the
policy must override to **"low"** (section 7).

---

## 6. Militant Faith is even more complicated (a second axis)

The other four jewels have one value axis (seed). **Militant Faith adds a second**: besides
transforming passives, it grants **Devotion** and converts a passive into a **keystone**, and the
"per 10 Devotion" scaling stats are real, separately searchable explicit mods. ninja's Militant Faith
template carries **17 extra Devotion-bearing mod ranges** on top of the 3 conqueror lines. [SRC:ninja]
Examples of the searchable Devotion stats: [SRC:trade-stats]
```
explicit.stat_3808469650  "#% increased Minion Attack and Cast Speed per 10 Devotion"
explicit.stat_2697019412  "#% increased Brand Damage per 10 Devotion"
explicit.stat_2566390555  "#% increased Totem Damage per 10 Devotion"
```
So a Militant Faith buyer often filters on **seed + conqueror + the granted keystone + Devotion
amount** - up to four axes. For DivTally's purposes the seed+conqueror pin (section 4) is still the
primary handle; the granted-keystone/Devotion filters are an **optional refinement** a future picker
could expose. The exact keystone-name stats are **[NOT FROM SOURCE]** here (they'd need their own
live probe) - do not assert them; the seed pin is sufficient for an honest search, and the trade link
lets the user add keystone/Devotion by hand.

---

## 7. Recommended pricing policy (detail)

Trigger: `item.baseType == "Timeless Jewel"` (and `item.name` in the five classic names). Handle it as
its **own branch** before the generic `price_unique_ninja` path, because both the query and the
confidence rules differ.

### 7.1 Parse (display-string -> filter)
1. Take the first physical line of the item's timeless explicit mod (split `explicitMods[i]` on
   `\n`; it's the line that isn't `"Historic"` and matches one of the five flavour templates).
2. `seed = first integer in that line` (the **displayed** value - `util.first_number`).
3. `conqueror = the trailing name` in that line (regex-capture the token after the template's
   connective, or match against the `{conqueror -> stat id}` table built from `trade_stats.json`).
4. `stat_id = table[conqueror.lower()]`. If the number or conqueror won't parse, or the name isn't a
   known conqueror -> **no seed filter** (fall through to 7.4 link-only).

### 7.2 The truthful search (a)
Build the section-4 query: `name` + `type "Timeless Jewel"` + one stat filter
`{id: stat_id, value: {min: seed, max: seed}}`. Attach it as both `trade_url` and
`extra["trade_query"]` (via the existing `_attach_query`). This is the search the **extension** runs
on the user's machine; whatever real listings it finds (`prices[]`, D-0016) are the *real* tiers for
this exact jewel. If it finds **0 buyouts**, that is the honest answer ("no exact-seed copy currently
listed") -> keep the number empty, show the link. Never widen the seed to fake a match (D-0015: never
relax a filter the user didn't relax).

### 7.3 The poe.ninja floor (b)
Also read the ninja name-level line (`unique_price(name)` -> the single aggregate). Surface it only as
a **floor**, with:
- `confidence = "low"` **always** (override `_confidence_from_lc`; the large `listing_count` is not
  evidence about *this* seed);
- a note like: `"poe.ninja floor: cheapest of ALL seeds/conquerors of {name} (Nc) - your exact seed
  is priced on your machine via the trade link"`;
- method e.g. `"timeless-ninja-floor"` so the UI can render it as `community/unverified`-style, never
  the green verified dot.

### 7.4 Unparseable -> link + no number (D-0019 tail, existing guardrail)
If 7.1 fails: `confidence = "none"`, name+base trade link only, note "exact seed unreadable; price via
the trade link". Same contract as every other unpriceable row.

### 7.5 Confidence summary
| Situation | number shown | confidence |
|---|---|---|
| Extension ran exact-seed search, >=1 buyout | real trimmed tiers | from real sample (`_confidence_from_lc`) |
| Extension ran exact-seed search, 0 buyouts | none (link only) | none |
| No extension: ninja name-floor available | floor, labelled | **low** (hard cap) |
| Seed/conqueror unparseable | none (link only) | none |

### 7.6 Where it plugs in (implementation map, for the coding agent)
- **`statmap.py`**: add a loader that indexes the `pseudo_timeless_jewel_*` stats from the bundled
  schema into `{conqueror_lower -> stat_id}` (+ `{stat_id -> jewel_name}` for validation).
- **`querybuild.py`**: a `_timeless_query(item)` mirroring `_unique_query` plus the seed stat filter;
  a `price_timeless(item)` branch in `price_build` gated on `baseType == "Timeless Jewel"`, ahead of
  `CAT_UNIQUE`. Reuse `_attach_query`, `_status`, `_confidence_from_lc`.
- **confidence cap**: do **not** route timeless jewels through the generic ninja confidence; force
  `low` on the floor (section 5's trap).
- **picker/response**: expose parsed `{jewel, conqueror, seed}` so the UI can show "Elegant Hubris -
  Caspiro - seed 29120" and the exact-seed vs floor distinction (contract-additive, like D-0006).

---

## 8. Community seed-calculator lore (context only - NOT source)

Why buyers care about the *exact* seed, for context. All **[NOT FROM SOURCE]**; none of this is in any
bundled dump and none should be presented as a DivTally price input:

- The seed->notable mapping is deterministic and has been reverse-engineered from the game data into
  community **timeless-jewel calculators** - e.g. Vilsol's tool
  **[NOT FROM SOURCE - vilsol.github.io/timeless-jewels]** and various reddit/PoE-forum tools - which
  let a player enter a seed + conqueror + socket and see exactly which passives in radius become which
  notables/keystones/stats. This is the machinery buyers use; DivTally does not replicate it.
- "**God seed**" / "god-tier seed" **[NOT FROM SOURCE - community slang]** = a seed that converts an
  unusually valuable cluster of nearby passives (e.g. several small passives into a specific notable,
  or a keystone into a build-defining one) at a good socket. These command large premiums that the
  poe.ninja name-floor (section 5) will *never* reflect - reinforcing why the exact-seed trade search,
  not a name lookup, is the only honest price.
- Because value depends on the **socket** too (which passives are in radius), the "same" seed can be
  worth different amounts to different builds. DivTally prices the *item* (seed+conqueror), not its fit
  to a socket - the trade link is where a buyer confirms fit. **[INFERRED]**

---

## 9. Edge cases / out of scope

- **Elegant Hubris x20**: handled by parsing the displayed value (section 3). No special-casing needed
  if you never touch the structured seed. **[INFERRED]**
- **Legacy conquerors** (`_zerphi`, `_kiloava`, `_deshret`, `_venarius`, `_chitus`): still valid stat
  ids [SRC:trade-stats]; a Standard legacy copy would parse fine and search correctly. No special
  handling; the data-driven conqueror table covers them for free. **[INFERRED]**
- **"Heroic Tragedy"**: appears in `trade_items.json` as a unique under `type "Timeless Jewel"`
  [SRC:trade-items], but has **no** poe.ninja economy line [SRC:ninja] and **no** identifiable
  `pseudo_timeless_jewel_*` conqueror stat. Out of the classic-5 scope; treat as link-only. Its
  identity/mechanics are **[NOT FROM SOURCE - unverified]** - do not assert them.
- **Non-classic seed families** in the schema: the stat list also carries 8 further seed-style ids
  under three *different* flavour templates - `Remembrancing # songworthy deeds by the line of`
  (Vorana, Uhtred, Medved), `Subjugating # souls in the thrall of` (Kurgal, Amanamu, Ulaman, Tecrod),
  `Binding # souls to phylacteries to sustain` (Zorath). [SRC:trade-stats] None maps to any of the 5
  classic timeless-jewel names in the item list, and none appears in the sample builds; their identity
  is **out of scope / [NOT FROM SOURCE - unverified]**. The pricing branch should key strictly off the
  20 classic-conqueror ids matched to the 5 jewel names and treat anything else as link-only.

---

## 10. Source index (reproduce these)
- Seed stats + Devotion stats: `research/data/trade_stats.json`
  (`grep pseudo_timeless_jewel`, `grep "per 10 Devotion"`).
- Jewel names / bases: `research/data/trade_items.json` (`grep "Timeless Jewel"`).
- Live jewel items (structured + display): `research/data/char_poe1.json` (Elegant Hubris/Caspiro,
  ~L12030) and `char_poe1_unicode.json` (Glorious Vanity/Xibaqua, ~L10790); PoB text in
  `research/data/pob_sample.xml` (~L476).
- ninja `UniqueJewel` overview: `GET https://poe.ninja/poe1/api/economy/stash/current/item/overview
  ?league=<Name>&type=UniqueJewel` (browser UA + `Referer: https://poe.ninja/poe1/economy`; no dump
  committed - re-probe to refresh).
- Query shapes to extend: `public/api/_lib/querybuild.py` (`_unique_query`, `_attach_query`,
  `price_unique_ninja`, `_confidence_from_lc`), `public/api/_lib/statmap.py` (stat indexing).
