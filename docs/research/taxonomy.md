# PoE1 Item-Taxonomy Port Plan

How every category of item on a PoE1 character maps into this codebase's pipeline
(normalise -> categorise -> price -> report), versus the parent PoE2 tool at
`C:\scripts\buildpricechecker`.

RULE 6 governs this doc: a mechanism that REPLACES another must DELETE the old code in the
same cutover. This plan therefore names the specific PoE2 code that must die.

---

## 0. Provenance & method (read this before trusting a number)

Evidence tags used throughout:

- **[SRC:parent]** - read directly from the parent PoE2 code (`bpc/models.py`, `engine.py`,
  `poeninja.py`, `pricing.py`, `report.py`, `trade.py`, `README.md`) on 2026-07-26.
- **[SRC:char]** - read from a LIVE PoE1 character JSON I fetched from poe.ninja on 2026-07-26
  (see below). This is the single ground-truth sample the task allotted.
- **[SRC:trade-items]** - a single cheap GET of `https://www.pathofexile.com/api/trade/data/items`.
- **[SRC:trade-stats]** - a single cheap GET of `https://www.pathofexile.com/api/trade/data/stats`.
- **[INFERRED]** - NOT verified from any of the above (e.g. the trade *search/exchange* query
  schema, which this task is forbidden to call). Treat as a hypothesis to verify before shipping.

**The sample character.** poe.ninja PoE1 builds live under `https://poe.ninja/poe1/api/...`
(NOT `/api/...` and NOT `/poe2/api/...`; see the correction to D-0002 in section 8). Path used:

1. `GET /poe1/api/data/index-state` -> current build league = **Allflame** (slug `allflame`),
   snapshot version `2022-20260726-26251`. [SRC:char]
2. `GET /poe1/api/builds/{version}/search?overview=allflame` -> the ladder, returned as
   **protobuf** (`application/x-protobuf`), columnar (record 0 = character names, record 1 =
   accounts, aligned by index). [SRC:char]
3. `GET /poe1/api/builds/{version}/character?account=example-0416&name=TestCharacter&overview=allflame&timeMachine=`
   -> full character JSON (212 KB). Level 100 Elementalist, Allflame. [SRC:char]

A raw copy of the sample is in the session scratchpad (`char_poe1_sample.json`) - it is NOT
committed here because `research/data/` is owned by another agent; the endpoint-mapping agent
should persist a canonical copy.

---

## 1. Current (PoE2) model - what we are porting FROM [SRC:parent]

**Categories** (`models.py`, `CAT_*`), routed by `frameType`:

| const | value | meaning (PoE2) | routed by |
|-------|-------|----------------|-----------|
| `CAT_UNIQUE` | `unique` | frameType 3 | `_categorise` |
| `CAT_RARE` | `rare` | frameType 2 | `_categorise` |
| `CAT_MAGIC` | `magic` | frameType 1 - "magic flasks / charms" | `_categorise` |
| `CAT_RUNE` | `rune` | frameType 5 currency, socketed - "runes / soul cores" | `_categorise` |
| `CAT_GEM` | `gem` | frameType 4 | `_categorise` |
| `CAT_NORMAL` | `normal` | frameType 0 | `_categorise` |

**Groups** (`Item.group`, drives report sections): `equipment` | `flask` | `jewel` | `rune` | `gem`.

**Report sections** (`report.py` `_GROUP_ORDER` / `_GROUP_TITLE`): Equipment, "Flasks & Charms",
Jewels, "Runes / Soul Cores", Gems.

**Normalisation sources** (`poeninja.normalize`): `data["items"]` (equipment), `data["flasks"]`,
`data["jewels"]`, `data["skills"]` (gems). Runes are extracted from each equipment item's
`socketedItems` where `frameType == 5`, then `dedupe_runes` collapses duplicates.

**Pricing by category** (`pricing.py`):
- unique -> search by name + base type; refine to build's skill-level roll / version affixes.
- rare -> base type (then category) + all searchable affixes; defences matched by TOTAL via
  `equipment_filters`; resistances can fold into `pseudo.pseudo_total_*_resistance`.
- magic -> base type only ("typically cheap").
- rune -> poe.ninja exchange rate (`Runes`/`SoulCores`/`Idols` economy categories), no search.
- gem -> poe.ninja economy, priced as **uncut** DIY: Uncut Skill Gem at level + Jeweller's Orbs
  for support sockets (Lesser->3/Greater->4/Perfect->5) + lineage supports. NO trade search.

**Trade client** (`trade.py`): `BASE = .../api/trade2`, `REALM = poe2`, base currency Exalted.

**Mod buckets folded together for searching** (`poeninja._EXPLICIT_MOD_KEYS`): `explicitMods`,
`craftedMods`, `desecratedMods`, `fracturedMods`, `enchantMods` - each carries a trade
stat-group tag (`explicit`/`crafted`/`desecrated`/`fractured`/`enchant`) because an enchant and an
explicit can share display text but map to different stat ids.

**Note:** the parent has **no socket/link handling at all** - `gem_sockets` refers to PoE2
support-gem sockets, not gear links. Grep confirms no `links`/`socket_filters` anywhere. [SRC:parent]

---

## 2. Ground truth - what a PoE1 character JSON actually contains [SRC:char]

Top-level keys (relevant ones):

| key | shape in sample | meaning | priceable? |
|-----|-----------------|---------|------------|
| `items` | list[11] | equipment (weapon/armour/jewellery), each with `sockets` + `socketedItems` | YES |
| `flasks` | list[5] | the flask belt (PoE1 = up to 5 flasks) | YES (uniques) |
| `jewels` | list[19] | tree jewels: regular, unique, **cluster**, **timeless** (abyss would appear here too) | YES |
| `skills` | list[6] | poe.ninja's grouping of the socketed gems: `{itemSlot, allGems, dps}` | YES (gems) |
| `clusterJewels` | dict keyed by tree-socket id | passive-tree EXPANSION geometry (subgraph/nodes) | NO - render metadata, not an item |
| `itemProvidedGems` | list[1] | gems granted BY an item (e.g. "Herald of the Hive" from a ring) | NO - the item is already priced |
| `keyStones` | list[3] | allocated passive keystones | NO |
| `masteries` | list[6] | passive mastery choices | NO |
| `runegrafts` | list[1] | PoE1 runegraft buff ("Runegraft of the Spellbound") | edge - see 4.11 |
| `tattoos` | list[0] | PoE1 tattoos | edge - see 4.11 |
| `guardianItems` | list[0] | items equipped on an Animate Guardian minion | edge - see 4.11 |
| `pathOfBuildingExport` | str | PoB import code (base64/zlib) | passthrough |

There is **NO `charms` key and no `Charm` inventoryId** anywhere in the character. PoE1 has no
charm slot in standard leagues. [SRC:char] (Also confirmed: the trade item DB has no "Charm"
category. [SRC:trade-items])

**Equipment item shape** [SRC:char] - full key set:
`baseType, typeLine, name, frameType, frameTypeId, rarity, inventoryId, ilvl, corrupted,
identified, sockets, socketedItems, implicitMods, enchantMods, explicitMods, craftedMods,
fracturedMods, scourgeMods, crucibleMods, mutatedMods, utilityMods, veiledMods(?), properties,
requirements, icon, x, y, w, h, replica, synthesised, fractured, searing, tangled, vestigial,
duplicated, crucibleMods, ...`

`inventoryId` values seen: `Weapon, Weapon2, Offhand2, Helm, BodyArmour, Gloves, Boots, Belt,
Amulet, Ring, Ring2`. (`Weapon`/`Weapon2` = the two weapon-swap sets; `useSecondWeaponSet` flags
which is live.) [SRC:char]

### 2.1 Sockets & LINKS (canonical GGG model) [SRC:char]

Each item carries `sockets: [{group, attr, sColour}, ...]` and `socketedItems: [{..., socket: i}]`.
**Links = sockets that share the same `group`.** The link count that matters for price is the
size of the largest group. Real examples from the sample:

- BodyArmour "Blunderbore" (Astral Plate): `sockets` = 6, all `group 0` -> **6-LINK**.
- Helm "The Gull": 4 sockets, all group 0 -> 4-link.
- Weapon "The Golden Charlatan" (Lion Sword, a 2H): 6 sockets in `{0:2, 1:2, 2:2}` -> six
  sockets but the max link is only **2** (three separate 2-links), NOT a 6-link.

So the price-relevant derived field is `max_links = max(count of sockets per group)` and
`total_sockets = len(sockets)`. A 5L/6L body armour or 2H weapon is a **major** price component
the parent does not model at all.

### 2.2 Gems [SRC:char]

Gems are `socketedItems` with `frameType == 4`, tied to their gear by `socket` (index into the
gear's `sockets`). poe.ninja ALSO pre-groups them in the top-level `skills` array with the SAME
`{itemSlot, allGems}` shape the parent already parses (`allGems[0]` = active, rest = supports).
Each gem's `itemData` has: `typeLine`/`baseType` (the gem name, including transfigured/alt names
like "Ethereal Knives of the Massacre" and tiered supports like "Greater Spell Echo Support"),
`support` (bool), `corrupted` (bool), and `properties` containing a **"Level"** entry (e.g.
`[["2",0]]`) and a **"Quality"** entry. `ilvl` is 0 for gems. [SRC:char]

This is the single biggest divergence: **PoE1 gems are real tradeable items priced by
name + level + quality + corruption.** There is no uncut gem, no Jeweller's Orb socket ladder,
and no lineage support - those are all PoE2 (section 5).

### 2.3 Jewels [SRC:char + SRC:trade-items]

All jewels arrive in `data["jewels"]` with `inventoryId = PassiveJewels` (tree sockets). Types
seen, distinguished by `baseType` / `frameType` / mod text:

- **Regular** (rare, ft2): base `Cobalt/Viridian/Crimson Jewel`, plain explicit mods.
- **Unique** (ft3): e.g. "The Balance of Terror" (Cobalt Jewel), priced by name.
- **Cluster** (ft2): base `Large/Medium/Small Cluster Jewel`. The value drivers live in mods:
  `enchantMods` = `"Adds N Passive Skills"`, `"K Added Passive Skills are Jewel Sockets"`,
  `"Added Small Passive Skills grant: <stat>"`; `explicitMods` = `"1 Added Passive Skill is
  <Notable>"` (one per notable). Price by base + passive count + the added-small stat + the
  specific notables.
- **Timeless** (ft3): base is one of the 5 timeless bases (sample had "Elegant Hubris",
  `typeLine "Timeless Jewel"`). Variation is the **seed + conqueror**, encoded in the explicit
  text: `"Commissioned 29120 coins to commemorate Caspiro / Passives in radius are Conquered by
  the Eternal Empire"` + `"Historic"`. The seed (29120) and conqueror (Caspiro) make each nearly
  unique; price by base + the seed stat (and flag link-only if unmatched). [SRC:char]
- **Abyss**: NONE in this sample, but the trade "Jewels" category lists them
  (`Hypnotic/Assembled/Murderous/Searching/Ghastly Eye Jewel`). [SRC:trade-items] They socket into
  item **abyssal** sockets rather than the tree, so in the character JSON they may appear either
  in `jewels` or inside an item's `socketedItems`. **[INFERRED]** - not observable here; the
  jewel GROUP is the right home either way (confirmed by the task hint and the trade category).

`clusterJewels` (the top-level dict) is the passive-tree subgraph geometry (groups/nodes/orbits)
used to render the expanded tree - it is NOT a priceable item and must not be double-counted with
the cluster jewel entries in `jewels`. [SRC:char]

### 2.4 Flasks [SRC:char]

`data["flasks"]` = 5 entries. Sample: 4 uniques (ft3: "Wine of the Prophet", "The Overflowing
Chalice", "Cinderswallow Urn", "Atziri's Promise") + 1 magic utility flask
(ft1: "Alchemist's Quicksilver Flask of the Cheetah" = prefix `Alchemist's` + base + suffix
`of the Cheetah`). Flask fields: `utilityMods` (the flask's utility line), `explicitMods` (the
affixes), `enchantMods` (flask enchant, e.g. "Used when Charges reach full" from instilling),
`implicitMods`. Unique flasks price by name; magic utility flasks price by base (+ optional
affixes) and are typically cheap. [SRC:char]

### 2.5 Mod buckets & enchants [SRC:char + SRC:trade-stats]

PoE1 items carry many mod arrays: `implicitMods, enchantMods, explicitMods, craftedMods,
fracturedMods, scourgeMods, crucibleMods, mutatedMods, veiledMods, utilityMods`. [SRC:char]

The trade **stats** DB has 14 groups: `Pseudo, Explicit, Implicit, Imbued, Fractured, Enchant
(2035 entries), Scourge, Crafted, Mercenary, Veiled, Delve, Ultimatum, Sanctum, Crucible`.
[SRC:trade-stats] Note there is **no "Desecrated" group** in PoE1 (that is a PoE2 bucket).

**Enchants map to the `Enchant` stat group** - verified ids include
`enchant.stat_3287581721 "Used when Charges reach full"` (flask), `enchant.stat_3086156145
"Adds # Passive Skills"` (cluster), and option-encoded cluster grants like
`enchant.stat_3948993189|26`. [SRC:trade-stats] Helm/lab enchants (which can dominate an item's
value) live in the same `enchantMods` array on the helm and the same `Enchant` group on trade, so
the parent's enchant group-scoping logic PORTS unchanged (an enchant and an explicit with
identical text still need separate `enchant.*` vs `explicit.*` ids).

**Pseudo total-resistance ids are IDENTICAL to the parent's**:
`pseudo.pseudo_total_elemental_resistance`, `pseudo.pseudo_total_chaos_resistance` (plus PoE1 also
exposes per-element `pseudo_total_fire/cold/lightning_resistance`,
`pseudo_total_all_elemental_resistances`, `pseudo_count_resistances`). [SRC:trade-stats] The
parent's `res_contributions` / pseudo logic ports directly.

---

## 3. Master mapping table: PoE2 concept -> PoE1 fate

Fate = KEEP / RENAME / DELETE / NEW.

| PoE2 concept | kind | PoE1 fate | why / evidence |
|---|---|---|---|
| `CAT_UNIQUE` = "unique" | category | **KEEP** | frameType 3 identical [SRC:char] |
| `CAT_RARE` = "rare" | category | **KEEP** | frameType 2 identical [SRC:char] |
| `CAT_MAGIC` = "magic" (flasks/charms) | category | **KEEP, redefine** | frameType 1; drop "charms" (none in PoE1) -> magic flasks + magic jewels [SRC:char] |
| `CAT_RUNE` = "rune" | category | **DELETE** | no runes/soul cores in PoE1; frameType-5 currency is never socketed on a char [SRC:char] |
| `CAT_GEM` = "gem" | category | **KEEP, rewrite pricing** | gems are real items (level/quality/corrupt), not uncut+orbs [SRC:char] |
| `CAT_NORMAL` = "normal" | category | **KEEP** | frameType 0 (white bases, rarely priced) |
| group `equipment` | group | **KEEP** | `data["items"]` [SRC:char] |
| group `flask` | group | **KEEP** | `data["flasks"]` [SRC:char] |
| group `jewel` | group | **KEEP, expand** | `data["jewels"]` incl. cluster/timeless/abyss [SRC:char/trade-items] |
| group `rune` | group | **DELETE** | no PoE1 equivalent |
| group `gem` | group | **KEEP** | `data["skills"]` [SRC:char] |
| section "Equipment" | report | **KEEP** | |
| section "Flasks & Charms" | report | **RENAME -> "Flasks"** | no charms in PoE1 [SRC:char] |
| section "Jewels" | report | **KEEP** | |
| section "Runes / Soul Cores" | report | **DELETE** | |
| section "Gems" | report | **KEEP** | |
| `_categorise` ft==5 -> CAT_RUNE | code | **DELETE** | |
| `normalize`: extract frame-5 runes from `socketedItems` | code | **DELETE**, replace with read `sockets[]` -> `max_links`/`total_sockets` per equipment item | links are the new price component [SRC:char] |
| `dedupe_runes` | code | **DELETE** | no runes to dedupe |
| `price_rune`, `_RUNE_ECON_CATS`, exchange path | code | **DELETE** | |
| gem model: `price_skill` (uncut+lineage), `_socket_orb_cost`, `_ORB_LADDER`, `_max_uncut_id`, `price_gems_aggregate`, `Item.gem_sockets/supports/is_lineage` | code | **DELETE**, replace with name+level+quality+corrupt pricing (4.5) | all PoE2-only [SRC:parent] |
| `PoeNinjaEconomy` `UncutGems/LineageSupportGems` categories | code | **DELETE**, repoint to PoE1 SkillGem economy | [SRC:parent] |
| `_EXPLICIT_MOD_KEYS` incl. `desecratedMods` | code | **RENAME/EXPAND**: drop `desecrated`; PoE1 adds `scourge`/`crucible`/`veiled`/`mutated` buckets as needed | no Desecrated group in PoE1 [SRC:trade-stats] |
| `_INVENTORY_CATEGORY` `"Charm": "flask"` | code | **DELETE** the Charm entry | [SRC:char/trade-items] |
| socket LINKS in a search | code | **NEW** | major PoE1 price driver, absent from parent (4.9) |
| cluster-jewel pricing | code | **NEW** | base + passives + notables (4.7) |
| timeless-jewel pricing | code | **NEW** | seed + conqueror (4.7) |
| abyss-jewel routing into jewel group | code | **NEW (minor)** | [INFERRED] (4.7) |
| `BASE=trade2`, `REALM=poe2`, base=Exalted | code (trade.py) | **RENAME**: `trade`, realm `pc`, base **Chaos** (per D-0002) | [SRC:parent] + [INFERRED] realm token (verify) |
| poe.ninja `/poe2/api/...` endpoints | code (poeninja.py) | **RENAME -> `/poe1/api/...`** | verified live [SRC:char] |

---

## 4. Per-category port specs

### 4.1 Uniques - KEEP (mostly)
Search by `name` + `base type`; the parent's version-unique detection and skill-level-roll
refinement port unchanged. **ADD**: when the unique is a body armour / 2H weapon with a 5L/6L,
add the socket-links filter (4.9) - a corrupted 6-link unique vs a 4-link is a large price gap.
Timeless/cluster uniques are handled in 4.7.

### 4.2 Rares - KEEP + add links
Base-type (then category) scope + all searchable affixes; defences via `equipment_filters` totals;
resistances via pseudo totals (ids verified identical, section 2.5). **ADD**: socket-links filter
for body/weapon (4.9). `_INVENTORY_CATEGORY` needs PoE1 category tokens re-verified against
`/api/trade/data/items` groups (Accessories/Armour/Weapons/Jewels/Flasks) - **[INFERRED]** exact
option strings (e.g. `armour.chest`) until the trade-schema agent confirms.

### 4.3 Magic - KEEP, redefine (NO charms)
frameType-1 items = magic utility **flasks** and occasional magic **jewels**. Price by base type
only (cheap). Remove every "charm" reference (`CAT_MAGIC` comment, `_INVENTORY_CATEGORY` Charm).

### 4.4 Runes / Soul Cores - DELETE ENTIRELY
No PoE1 equivalent. Nothing "replaces" it structurally. The task's hint is confirmed: abyss
jewels are NOT a rune replacement - they live in the jewel group (4.7). Delete the category, the
group, the report section, `price_rune`, `_RUNE_ECON_CATS`, `dedupe_runes`, and the frame-5
extraction in `normalize`.

### 4.5 Gems - KEEP category, REWRITE pricing (the big one)
Parse from `data["skills"]` exactly as the parent does (`allGems[0]` active + supports), but price
each gem as a **real item by name + level + quality + corruption** [SRC:char]. Level and quality
come from the gem's `properties` ("Level"/"Quality"); the parent's `_gem_level` already reads
"Level" and ports.

Recommended pricing source: **poe.ninja PoE1 SkillGem economy** (no trade search -> no ban risk,
matching the parent's "gems off poe.ninja" philosophy). poe.ninja tracks gems by variant
(level/quality/corrupted, and separately for Awakened/Enlighten/Empower/transfigured), which is
where nearly all gem value sits (e.g. Awakened supports, Enlighten 4, corrupted +1/+2, 20/20
vs 21/23). **[INFERRED]** exact endpoint - by analogy `https://poe.ninja/poe1/api/economy/...`
type `SkillGem`; the economy-mapping agent owns the precise shape. Fallback for a gem poe.ninja
does not track: a clickable trade link by name + `gem_level`/`gem_quality`/`corrupted` misc
filters (no auto-search, to protect the search budget). **[INFERRED]** the misc_filter keys.

DELETE the entire PoE2 gem economy path (uncut gem + Jeweller's Orb ladder + lineage supports +
`gem_sockets`/`supports`/`is_lineage`). Do NOT price `itemProvidedGems` (the granting item is
already priced) [SRC:char].

### 4.6 Flasks - KEEP
Unique flasks (ft3) -> price by name. Magic utility flasks (ft1) -> price by base (cheap noise;
the prefix/suffix like `Alchemist's ... of the Cheetah` rarely moves price, though instilled
`enchantMods` and specific suffixes occasionally matter - default to base-only, flag as low
confidence). [SRC:char]

### 4.7 Jewels - KEEP group, add cluster/timeless/abyss handling
- **Regular** rare jewel -> price by base + affixes (like a small rare); usually cheap unless it
  rolls a chase combo.
- **Unique** jewel -> price by name (+ any version affix, e.g. corrupted implicit).
- **Cluster** jewel -> price by base (`Large/Medium/Small Cluster Jewel`) + passive count + the
  "Added Small Passive Skills grant: <stat>" enchant + the specific notables ("1 Added Passive
  Skill is <Notable>"). The notable list is the dominant price driver. **[INFERRED]** the exact
  trade encoding: the added-passive-count and grant are `enchant.*` (some option-encoded, e.g.
  `enchant.stat_3948993189|26` [SRC:trade-stats]); notables are `explicit.*` "1 Added Passive
  Skill is #". Verify the option ids before shipping.
- **Timeless** jewel -> price by base (one of the 5) + the seed stat ("Commissioned # coins ...").
  Each seed+conqueror is near-unique; expect thin listings -> often show a base-level ballpark and
  fall back to a **link-only** (clickable trade search) rather than a misleading number. **[INFERRED]**
  the exact seed-stat id / whether trade exposes the numeric seed as a searchable value.
- **Abyss** jewel -> route into the jewel group; price by base (`* Eye Jewel`) + affixes. **[INFERRED]**
  (none in sample) whether it arrives in `jewels` or an item's abyssal `socketedItems`; handle both.

### 4.8 Enchants - KEEP the group-scoping logic
`enchantMods` -> `Enchant` stat group (verified to exist, 2035 entries) [SRC:trade-stats]. Lab/helm
enchants can dominate an item's value; keep the parent's rule that an enchant is searched in its
OWN `enchant.*` group (never as an `explicit.*` with the same text). Cluster-jewel "Adds N Passive
Skills" and flask "Used when Charges reach full" are also `Enchant`-group ids.

### 4.9 Socket LINKS - NEW, major price component
The parent has NO link handling. For PoE1, derive per equipment item from `sockets[]`:
`max_links = max(count per group)`, `total_sockets = len(sockets)`. [SRC:char] When pricing a
body armour or (two-handed) weapon whose `max_links >= 5`, ADD a links filter to the query so the
result compares like-for-like; a 6L is often the single largest cost on a budget build (fusing/
crafting cost) and on uniques (a 6L Tabula/typical-6L unique vs the 4L base).

Proposed query addition **[INFERRED - PoE1 trade query schema, NOT verifiable this task (search is
forbidden); the trade-client agent must confirm before shipping]**:
```
"filters": {
  "socket_filters": {
    "filters": {
      "links":   {"min": <max_links>},   # 5 or 6
      "sockets": {"min": <total_sockets>}  # optional; 6S has value below 6L
    }
  }
}
```
Also expose `max_links`/`total_sockets` in the engine->UI JSON so a skin can show "6L" and the
user can toggle it (a 5L vs 6L is a common "what if" like the parent's include/exclude).

### 4.10 Corrupted implicits - KEEP `corrupted` flag; treat as a value modifier
`corrupted` is a per-item bool [SRC:char]. Corrupted implicits (e.g. Blunderbore's
"+2 to Level of Socketed Projectile Gems", or gem corruptions +1 level / +/-quality) can swing
price. Fold the corrupted implicit into the mod set the same way explicits are searched, and
carry `corrupted` into the query where it matters (double-corrupt rares, corrupted uniques). The
parent already threads `corrupted` through `Item`; keep it. Gems: `corrupted` + level/quality is
the whole pricing key (4.5).

### 4.11 PoE1-only extras - default SKIP, log to backlog
Not in the parent, present/possible in PoE1, generally minor - do NOT price in v1 unless owner asks:
- `runegrafts` (trade category "Graft", 17 bases [SRC:trade-items]) - the sample has 1; a buff
  from the Allflame/rune mechanic, usually not a market item. **[INFERRED]** priceability.
- `tattoos` (Ancestor-league passive tattoos) - list[0] here; itemised currency, usually cheap.
- Tinctures (trade category "Tincture", 15 bases [SRC:trade-items]) - claw-slot; none in sample.
- Idols (trade category "Idol", 45 bases [SRC:trade-items]) - league-specific; none in sample.
- `guardianItems` (Animate Guardian gear) - list[0] here, but CAN be expensive (Kingmaker, etc.).
  Flag as a NEW optional sub-group for the backlog.

---

## 5. Concepts that MUST DIE (PoE2-only) - RULE 6 delete list

Delete in the same cutover that adds the PoE1 path (leaving them compiling means they silently
win):

1. **Runes / Soul Cores** - `CAT_RUNE`, group `rune`, section "Runes / Soul Cores", `price_rune`,
   `_RUNE_ECON_CATS`, `dedupe_runes`, frame-5 `socketedItems` extraction in `normalize`. [no PoE1
   equivalent, SRC:char]
2. **Uncut-gem economy model** - `price_skill` (uncut + lineage), `_socket_orb_cost`, `_ORB_LADDER`,
   `_max_uncut_id`, `price_gems_aggregate`, and `Item.gem_sockets/supports/is_lineage`. PoE1 gems
   are real items (4.5). [SRC:char shows level/quality/corrupt gems, not uncut]
3. **Charms** - the "charms" wording in `CAT_MAGIC`, the "Flasks & Charms" section title, and
   `_INVENTORY_CATEGORY["Charm"]`. No charm slot in PoE1. [SRC:char/trade-items]
4. **`desecratedMods` bucket** - PoE1 has no Desecrated stat group. [SRC:trade-stats]
5. **PoE2 realm/base wiring** - `trade2` base URL, `REALM = poe2`, Exalted-as-base, and every
   `/poe2/api/...` poe.ninja URL. PoE1 = `/api/trade` + realm `pc` + Chaos base (D-0002) +
   `/poe1/api/...`. [SRC:char verified the poe.ninja side; trade side [INFERRED] realm token]
6. The parent's "this is a PoE1 link, we only price PoE2" guard in `parse_build_url` (inverts).

---

## 6. Proposed PoE1 engine model + report layout

**Categories:** `CAT_UNIQUE`, `CAT_RARE`, `CAT_MAGIC` (flasks + magic jewels), `CAT_GEM`,
`CAT_NORMAL`. (No `CAT_RUNE`.)

**Groups / report sections (order):**
1. `equipment` -> "Equipment"
2. `flask` -> "Flasks"      (renamed; no charms)
3. `jewel` -> "Jewels"      (regular / unique / cluster / timeless / abyss)
4. `gem` -> "Gems"
(no `rune` group / section)

**New `Item` fields:** `max_links: int`, `total_sockets: int` (from `sockets[]`); drop
`gem_sockets`/`supports`/`is_lineage`. Keep `corrupted`, `gem_level`; add `gem_quality`.

**Engine->UI JSON contract deltas** (coordinate with the contract-rename pass in D-0002):
`exalted` -> `chaos` everywhere; per-item add `max_links`/`total_sockets`; drop lineage/uncut
fields from the gem `extra`. Sections list drops "rune". Keep the min/median/high + confidence +
`trade_url` shape so all 10 UI skins port with string changes only.

---

## 7. Open items to verify (owned by other agents)

- **[INFERRED]** the `socket_filters` links/sockets query JSON (4.9) - trade-client agent, verify
  against a live search once (that agent holds the search budget).
- **[INFERRED]** PoE1 trade realm token (`pc`?), `_INVENTORY_CATEGORY` option strings, gem
  `misc_filter` keys (`gem_level`/`gem_quality`/`corrupted`), timeless seed-stat id, cluster
  enchant option ids - trade-schema agent.
- **[INFERRED]** poe.ninja PoE1 gem/currency economy endpoint shape and category names
  (`SkillGem`, `Currency`, `UniqueJewel`, ...) - economy-mapping agent.
- **[INFERRED]** abyss-jewel location in the character JSON (jewels vs abyssal socketedItems) -
  needs a character that runs abyss jewels.

## 8. Correction to record in the decision log (not my file to edit)

D-0002 states the poe.ninja PoE1 API is "`poe.ninja/builds` ... `/api/...` - NOT `/poe2/api/...`".
**Verified wrong in the middle segment**: it is `https://poe.ninja/poe1/api/...`
(`/poe1/api/data/index-state`, `/poe1/api/builds/{version}/character`,
`/poe1/api/builds/{version}/search?overview=<slug>`). Plain `/api/data/index-state` returns 404.
[SRC:char] The coordinator should amend D-0002 (or add a decision) so the endpoint-mapping agent
codes the right base. The builds *ladder* is protobuf (`application/x-protobuf`), not JSON - a
second surprise worth recording.
