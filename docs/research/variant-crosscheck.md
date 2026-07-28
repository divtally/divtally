# Variant-sensitive uniques — community CROSS-CHECK list (D-0019)

**Purpose.** An independent list of variant-sensitive PoE1 uniques compiled from **community
knowledge** (poewiki / fandom variant pages, poedb, trade-site experience), to catch anything the
poe.ninja Unique\* harvest folds together or misses. This is a *cross-check*, **not** the registry:
per the owner EVIDENCE RULE, every item sourced from community text carries a
**[NOT FROM SOURCE - <where>]** tag, and each entry states whether I could confirm it in **primary
data** (the bundled trade schema dumps + character JSON) or not.

**Primary data available to this agent (what "confirmed" means below):**
- `research/data/trade_items.json` — the full official `data/items` dump (1544 named uniques). Trade
  splits some uniques into **multiple entries** keyed by `type` (base) and `disc` (discriminator:
  `legacy`, `relic`-style, `map`, etc.). Confirmations of an item's *name*, *base(s)*, and whether
  **trade itself distinguishes variants as separate entries** come from here. **PRIMARY.**
- `public/api/_data/trade_stats.json` — the official `data/stats` dump (16,350 stat filters across
  Pseudo/Explicit/Implicit/Fractured/Enchant/Scourge/Crafted/Veiled/Crucible). Confirmations that a
  variant's **defining filter exists** (the explicit/enchant/pseudo id you'd search on) come from
  here. **PRIMARY.**
- I do **NOT** have a local poe.ninja Unique\* economy dump. So "ninja folds this / ninja enumerates
  this" claims below are **[NOT FROM SOURCE]** community inference — they are exactly the assertions
  the ninja-harvest agent must verify against the live `Unique*` overviews. Flagged per item.

**The core distinction this doc draws** (it is the whole point of D-0019):

| Class | How trade distinguishes the variant | Does the trade *item* dump show it as separate entries? | Risk to a name-only search |
|---|---|---|---|
| **A. Base-split** | different `type`/`disc` entry per variant | **YES** — visible in `trade_items.json` | Low (base is picked from the build item) but element/mod axis can still hide (see D) |
| **B. Mod-defined (single entry)** | one item entry; variant = which **explicit/enchant** mod it rolled | **NO** — one entry, many prices | **HIGH** — name-only averages incomparable variants |
| **C. Roll-defined value (single entry)** | one item entry; value = **magnitude/combo** of a rolled mod; ninja has ~no variants | **NO** | **HIGH** — ninja price is meaningless for the specific copy |
| **D. Seed/keystone (timeless & kin)** | one item entry; value = exact **seed** + resulting notables/keystone | **NO** | **HIGHEST** — see the dedicated section |

Class-B/C/D items are precisely where the ninja harvest is weakest and where D-0019's
"search WITH the defining mod from the build's own copy" rule earns its keep.

---

## Class A — base-split variants (trade shows separate entries; primary-confirmed)

These are the *only* variant items the trade `data/items` dump enumerates explicitly. All confirmed
present as multi-entry names in `trade_items.json` (base list = primary). Most multi-entry names in
the dump are **legacy base-swaps** (`disc: "legacy"`, e.g. old vs current quiver/wand base) — those
are historical drop versions, usually NOT price-relevant to a current build and are folded fine by
ninja. The genuinely price-relevant, *simultaneously-obtainable* base-split variants are:

| Item | Bases (primary: `trade_items.json`) | Variant meaning | Notes |
|---|---|---|---|
| **Doryani's Delusion** | Slink Boots / Sorcerer Boots / Titan Greaves (+3 legacy) | base picks the **armour type**; a separate **element** mod axis (Fire/Cold/Lightning aura + pen) rides on top → **also Class B** | Confirmed 6 entries. The element axis is NOT in the item dump — must add the mod filter. [element axis NOT FROM SOURCE - poewiki "Doryani's Delusion"] |
| **Precursor's Emblem** | Prismatic / Ruby / Sapphire / Topaz / Two-Stone Ring | base ↔ which resist/attribute the ring can roll | 5 entries, all `disc:None` (current). Primary-confirmed. |
| **Combat Focus** | Cobalt / Crimson / Viridian Jewel | colour picks which element is prevented from igniting/etc (Cobalt=fire, Crimson=cold... [mapping NOT FROM SOURCE - poewiki "Combat Focus"]) | 3 entries. Primary-confirmed the split; the colour→effect mapping is community. |
| **Grand Spectrum** | Cobalt / Crimson / Viridian Jewel | colour picks the stacking bonus (resist / crit multi / AoE etc [mapping NOT FROM SOURCE - poewiki]) | 3 entries. Primary-confirmed split. |
| **Stormblood** | Sapphire / Topaz Flask | base picks the flask's resist/effect | 2 entries, `disc:None`. Primary-confirmed. |

**Cross-check gap flag:** trade base-split covers the *base* axis only. Where an item is base-split
**and** mod-defined (Doryani's Delusion), a name+base search still averages the element variants —
the registry must carry the element mod filter too. **Could NOT be inferred from the item dump
alone; confirmed as a real gap.**

---

## Class B — mod-defined variants, ONE trade entry (the main ninja-fold gap)

Every item below is a **single** entry in `trade_items.json` (one name, one base, `disc:None`) — so
the trade item dump gives **no hint** that variants exist. The variant lives entirely in an
**explicit/enchant mod**, which the registry must add as a required filter. poe.ninja *does*
typically enumerate these as separate variant lines (e.g. "Impresence (Lightning)"), so the harvest
*may* capture them — **but only if it reads ninja's per-variant rows and maps each to its mod
filter.** If the harvest keys on item name alone, these collapse to one meaningless average.
Base confirmations = primary (`trade_items.json`); variant enumerations = community, tagged.

| Item | Base (primary) | Variant axis | Defining filter in `trade_stats.json` (primary) | ninja enumerates? |
|---|---|---|---|---|
| **Watcher's Eye** | Prismatic Jewel | 1–3 of a large pool of "**while affected by [aura]**" mods; price = the specific mod *combo* | many `explicit.*"...while affected by Herald/Grace/..."` present (150+ "while affected by" stats) | ninja lists single-mod variants only; combos are trade-only. [NOT FROM SOURCE - poewiki "Watcher's Eye"] → **treat as Class C too** |
| **Sublime Vision** | Prismatic Jewel | which **aura** the hybrid mod names (disables others, boosts that one) | aura-effect explicit stats present | [NOT FROM SOURCE - poeprices/poewiki] |
| **Impresence** | Onyx Amulet | **element** (Lightning/Fire/Cold/Chaos/Physical...) picks the free-curse + damage mods | element explicit stats present | ninja: "Impresence (X)" rows. [7 variants NOT FROM SOURCE - fandom] |
| **Vessel of Vinktar** | Topaz Flask | 4–5 variants: Added Lightning to Spells / to Attacks / Phys→Lightning / Lightning Pen / (shock-spread) | conversion + added-damage explicit stats present | ninja: "Vessel of Vinktar (X)" rows. [variant list NOT FROM SOURCE - poewiki] |
| **Yriel's Fostering** | Exquisite Leather | **Rhoa / Snake / Ursa** picks which animal skill + damage type is granted | granted-skill explicit stats present | ninja: 3 rows. [NOT FROM SOURCE - poewiki "Yriel's Fostering (Rhoa/Snake/Ursa)"] |
| **Volkuur's Guidance** | Zealot Gloves | **element** (Lightning/Fire/Cold) picks the self-cast-curse-on-hit + res mod | element res + curse explicit stats present | ninja: 3 rows. [NOT FROM SOURCE - poewiki] |
| **Circle of Nostalgia / Guilt / Anguish / Fear / Regret** | Amethyst/Iron/Ruby/Sapphire/Topaz Ring | each ring has a **"while affected by Herald of X"** variant — the Herald named varies | `explicit.*"while affected by Herald of Agony/Ash/Ice/Thunder/Purity"` present | ninja: per-Herald rows. [Elder "Circle" ring family NOT FROM SOURCE - poewiki] |
| **Storm Secret** | Topaz Ring | elemental-pen variant [NOT FROM SOURCE - poewiki] | pen explicit stats present | verify against ninja |
| **The Light of Meaning** | Prismatic Jewel | which **stat** (per-attribute / resist) the "modifiers to X in radius" amplifies | `explicit.*"...in Radius"` amplify stats present | [NOT FROM SOURCE - poewiki] |

**Could NOT confirm in primary data:** the *enumeration* of which variants exist per item, and the
*claim* that ninja splits them. Both are community; both are exactly what the harvest agent must
prove against ninja's live `Unique*` rows. **Confirmed in primary:** each is one item entry, and the
*type* of defining stat exists in the trade stat dump (so a mod-filtered search is constructible).

---

## Class C — roll-defined value, ninja has ~no usable variants (worst folds)

Single trade entry; the *magnitude or combination* of a rolled mod sets the price, and poe.ninja
either lists one line or a coarse handful — so the ninja number is nearly useless for a specific
copy. These must be priced from the **build's own rolled values** as min=roll filters.

| Item | Base (primary) | Why ninja folds it | Filter to use (primary in `trade_stats.json`) |
|---|---|---|---|
| **Split Personality** | Crimson Jewel *(primary; also drops on other jewel bases historically)* | value = **which two attributes/resists** the two mods rolled; ninja shows one "Split Personality" | the specific attribute/life/ES explicit stats; search the build copy's exact pair |
| **Watcher's Eye** *(also here)* | Prismatic Jewel | combos of 2–3 aura mods are astronomically varied; ninja lists single-mod prices only | mod combo via multiple `while affected by` explicit filters |
| **Megalomaniac** | Medium Cluster Jewel | rolls **3 random notables** from the whole pool; ninja can't meaningfully price the combo | notable **enchant** option-stats `enchant.stat_3948993189\|<opt>` + `enchant.stat_4079888060` (added-passive-are-sockets). Search by the 3 specific notable hashes. [3-random-notables NOT FROM SOURCE - maxroll "Cluster Jewels Explained"] |
| **That Which Was Taken** | Crimson Jewel | value = which mods rolled | explicit stats present |
| **Aul's Uprising** | Onyx Amulet | value dominated by **which aura's reservation-removal** mod rolled (huge swing) | reservation explicit stats present. [aura-roll price driver NOT FROM SOURCE - poewiki/trade experience] |
| **Voidforge** | Infernal Sword | added-damage rolls re-randomize each hit; roll ranges wide [NOT FROM SOURCE - poewiki] | verify |

**Could NOT confirm in primary data:** that ninja lacks per-combo variants (I have no ninja Unique
dump) — but this is structurally certain for combinatorial items (Watcher's Eye / Megalomaniac).
**Confirmed in primary:** single item entry + the roll's stat filter exists.

---

## Class C′ — empty-socket / socket-count tiers (implicit/enchant-defined, one entry)

Single trade entry; the price tier is a **count implicit/enchant**, which ninja usually does NOT
split, and which a name search ignores entirely.

| Item | Base (primary) | Tier axis | Filter (primary `trade_stats.json`) |
|---|---|---|---|
| **Voices** | Large Cluster Jewel | **"Adds 7 / 5 / 3 / 1 Passive Skills"** (the 7-socket is the classic; community notes 3 can be *preferable*) | `explicit.stat_3086156145` "Adds # Passive Skills" (min=max on the tier). [7/5/3/1 tiers NOT FROM SOURCE - fandom "Voices" / maxroll] |
| **Bubonic Trail** | Murder Boots | **1 vs 2 Abyssal Sockets** | `explicit.stat_3527617737` "Has # Abyssal Sockets" |
| **Tombfist** | Steelscale Gauntlets | **1 vs 2 Abyssal Sockets** | `explicit.stat_3527617737` "Has # Abyssal Sockets" |
| **Lightpoacher / Shroud of the Lightless / Command of the Pit / Hale Negator** | (various) | Abyssal socket count [NOT FROM SOURCE - poewiki abyss-socket uniques] | `explicit.stat_3527617737` |
| Generic **cluster jewels** (rare, not unique) | Large/Medium/Small Cluster Jewel | # added passives + which notables (enchants) | `enchant.stat_3948993189\|<opt>` (notable), `enchant.stat_4079888060` (jewel-socket), `explicit.stat_3086156145` (count) |

**Confirmed in primary:** every filter id above exists in the stat dump. **NOT FROM SOURCE:** the
per-item tier lists and the "3 > 7 for Voices" playbook note (community).

---

## Class D — timeless jewels & keystone/notable-radius jewels (highest risk)

Owner: "timeless jewels are worse — research why." **Here is why, primary-confirmed.**

A timeless jewel's entire value is a function of its **seed** (a single integer) combined with which
**conqueror** it names — together they deterministically decide *which passives in its radius get
transformed into which notables/keystones*. Two Glorious Vanity jewels with different seeds are
effectively different items; ninja lists at most a coarse "Glorious Vanity" line (or a few
conqueror rows) and **cannot** price by seed. The trade site prices them by an **exact seed filter**
(`min=max`) plus the conqueror pseudo-stat.

**Primary-confirmed:** the seed is a first-class trade filter. `trade_stats.json` carries a
dedicated `explicit.pseudo_timeless_jewel_*` stat **per conqueror**, whose value IS the seed:

- **Glorious Vanity** (Vaal) — `..._doryani` / `_xibaqua` / `_ahuana` / `_zerphi` = "Bathed in the blood of # sacrificed in the name of X"
- **Lethal Pride** (Karui) — `..._kaom` / `_rakiata` / `_akoya` / `_kiloava` = "Commanded leadership over # warriors under X"
- **Brutal Restraint** (Maraketh) — `..._nasima` / `_asenath` / `_balbala` / `_deshret` = "Denoted service of # dekhara in the akhara of X"
- **Militant Faith** (Templar) — `..._avarius` / `_maxarius` / `_dominus` / `_venarius` = "Carved to glorify # new faithful converted by High Templar X"  *(+ a Devotion pool axis)*
- **Elegant Hubris** (Eternal) — `..._cadiro` / `_victario` / `_caspiro` / `_chitus` = "Commissioned # coins to commemorate X"
- (also present: `_vorana` / `_uhtred` / `_medved` "Remembrancing # songworthy deeds", and
  `_kurgal` / `_amanamu` / `_ulaman` / `_tecrod` "Subjugating # souls", `_zorath` "Binding # souls" —
  these are the newer/PoE-lore conquerors; enumerate all when building the registry.)

**Registry rule for timeless (from D-0019, now primary-grounded):** search by the **exact seed**
(`min=max` on the matching `pseudo_timeless_jewel_<conqueror>` stat) **and** the conqueror identity.
Unmatchable → link + no number.

**Keystone / notable radius jewels** (same "one entry, value from what it allocates" problem, all
single entries in `trade_items.json`, filters primary-confirmed):

| Item | Base (primary) | Variant axis | Filter (primary) |
|---|---|---|---|
| **Forbidden Flame** (Crimson) + **Forbidden Flesh** (Cobalt) | must be bought as a **matching pair** naming the **same ascendancy notable** | `explicit.stat_2460506030\|<opt>` (Flame) / `explicit.stat_1190333629\|<opt>` (Flesh) "Allocates <Notable> if you have the matching modifier on Forbidden Flame/Flesh" — the `\|opt` IS the notable selector | primary-confirmed, both halves |
| **Impossible Escape** | Viridian Jewel | which **keystone** it names (Passives near that keystone allocate freely) | `explicit.stat_2422708892\|<keystone-opt>` "Passive Skills in Radius of <Keystone> can be Allocated" | primary-confirmed |
| **Thread of Hope** | Crimson Jewel | **ring size** implicit: Small / Medium / Large / Very Large / Massive | `explicit.stat_3642528642\|1..N` "Only affects Passives in <size> Ring" | primary-confirmed (5 size options in dump) |
| **Unnatural Instinct / Intuitive Leap / Fluid Motion / Brute Force Solution** | Viridian Jewel | radius-content dependent (value ≈ placement, not a mod) — **name-only price is fine**; flagged so the registry does NOT over-filter them | n/a | [NOT FROM SOURCE - poewiki]; verify they need NO variant filter |

**Could NOT confirm in primary data:** the human-readable conqueror→jewel mapping labels
(Glorious Vanity = Vaal, etc.) are community lore [NOT FROM SOURCE - poewiki timeless-jewel pages] —
but the **seed stat ids themselves are primary** and are what the query actually uses, so the mapping
is only cosmetic. Everything load-bearing (seed filter, notable/keystone option-stats) is primary.

---

## Items I explicitly could NOT confirm as variant-sensitive in primary data

Flagged so the harvest doesn't waste filters on non-variants, and so nothing here is quietly trusted:

- **The colour→effect mappings** for Combat Focus / Grand Spectrum (which colour = which element/
  bonus): **[NOT FROM SOURCE - poewiki]**. The *split* is primary; the *meaning* is community.
- **Exact variant enumerations** (how many Vinktar/Impresence/Yriel variants, their mod text):
  **[NOT FROM SOURCE - poewiki/fandom]**. Primary confirms one item entry + that the mod-type exists,
  not the count.
- **"poe.ninja folds/enumerates X"** for every item: **[NOT FROM SOURCE]** — no local ninja Unique
  dump. This is the single biggest thing the harvest agent must verify against live `Unique*` rows;
  this doc only tells it *where to look*.
- **Voidforge, Storm Secret, Aul's Uprising price-driver claims**, and the **abyss-socket unique
  roster** (Lightpoacher/Command of the Pit/etc.): **[NOT FROM SOURCE - poewiki]** — bases are
  primary, the "this is why it's variant-priced" is community.
- **Split Personality alternate jewel bases**: dump shows Crimson Jewel only; historical other-base
  drops are **[NOT FROM SOURCE]** and may be legacy — verify before adding.

## Net cross-check verdict

The ninja harvest is **safe** for Class A (trade already base-splits; ninja mirrors it) and for plain
single-variant uniques. It is **at risk** for:
1. **Class B combos not on ninja** (Watcher's Eye / Sublime Vision mod combos),
2. **Class C roll-defined** (Split Personality, Aul's Uprising, Megalomaniac, That Which Was Taken),
3. **Class C′ socket/passive-count tiers** (Voices, Bubonic Trail, Tombfist — ninja rarely splits),
4. **Class D timeless-by-seed and Forbidden pairs / Impossible Escape / Thread of Hope** — ninja
   cannot price by seed/keystone at all.

Every filter needed to fix 1–4 is **present in the bundled trade stat dump** (ids cited above), so
D-0019's "required defining-mod filter from the build's own copy" is fully constructible from primary
data — the community list here only supplies the *roster* of which items to apply it to, and every
roster claim is tagged.

**Sources (community, all cross-check-only, tagged [NOT FROM SOURCE] at point of use):**
poewiki.net (Watcher's Eye, Vessel of Vinktar, Doryani's Delusion, Yriel's Fostering, Voices, Circle
rings, timeless jewel pages), pathofexile.fandom.com (Vessel of Vinktar, Voices, Doryani's
Delusion), poeprices.info (Sublime Vision, Watcher's Eye), maxroll.gg "Cluster Jewels Explained"
(Megalomaniac / Voices). Primary sources: `research/data/trade_items.json`,
`public/api/_data/trade_stats.json`.
