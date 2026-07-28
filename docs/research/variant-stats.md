# Variant-defining stats in the trade schema (per-class recipes)

How each **variant class** of unique/jewel is expressed in the pathofexile.com trade
`query.stats` schema, and **exactly how to build the required filter from the character item's own
mod text**. Grounds D-0019 (variant-unique registry + timeless jewels) and honours D-0015 (this
ADDS required defining-mod filters; it never drops a mod the user kept).

## Evidence tags (owner EVIDENCE RULE)
- **[SRC]** = derived directly from a bundled primary source: `research/data/trade_stats.json`
  (GGG `/api/trade/data/stats` dump, 14 groups), `research/data/trade_data_filters.json`,
  `research/data/char_poe1.json` (the character's own items), or `bpc/*.py` (the consumer code).
  The slim shippable copy `public/api/_data/trade_stats.json` was verified to carry every id below.
- **[INFERRED]** = GGG trade convention not exercised by the bundled dumps (no bundled dump contains
  a live option-stat *search*). Flagged at point of use; confirm with the D-0019 live spot-check.
- **[LORE]** = well-known PoE item↔effect association, not present in the stat dump. Not load-bearing
  (recipes key off the mod TEXT, not the association).

All stat ids, option ids, texts and counts below are **[SRC]** unless tagged otherwise.

---

## 0. The three encoding kinds (this is the whole grammar)

Every variant-defining requirement reduces to one of three filter shapes. A `query.stats` filter is
`{"id": <stat-id>, "value": {...}}` inside a group `{"type":"and"|"count"|..., "filters":[...]}`.

| Kind | Stat text shape | Dump signature | Filter value | Build |
|---|---|---|---|---|
| **VALUE** | has a `#` placeholder | plain id, no `\|`, no `option` array | `{"min":X}` (threshold) or `{"min":X,"max":X}` (exact) | `{"id":sid,"value":{"min":n}}` |
| **OPTION** | fully-resolved text (the choice is baked in) | id ends `…\|<optionid>` **OR** carries an `option:{options:[…]}` array | `{"option":<int>}` | see split rule below |
| **FLAG** | no `#`, a fixed statement | plain id, no `\|`, no `option` | none (or `{"min":1}`) | `{"id":sid}` |

### 0.1 OPTION-stat encoding — two representations, ONE query form
This dump contains option-stats in **two** representations (counts from `trade_stats.json`): [SRC]
- **Pre-flattened** — the option is baked into the id after a pipe and the text is fully resolved,
  with **no** `option` array. Counts: explicit 713, enchant 524, imbued 162, implicit 28.
  Example: `explicit.stat_2460506030|33645` = "Allocates Oath of Summer if you have the matching
  modifier on Forbidden Flame".
- **Live `option` array** — a base id (no pipe) plus `option.options:[{id,text},…]`. Only **88**
  entries, **all in the `pseudo` group** (Searing/Eater implicit tiers, Temple room states). These
  can ONLY be queried as `{"id":base,"value":{"option":N}}` — there is no pipe form to use verbatim.

**The query form for BOTH is the split form:** [INFERRED for the flattened case; SRC for the array case]
```
{"id": "<id before the pipe>", "value": {"option": <int after the pipe>}}
```
- **[SRC]** that `value.option` is the mechanism: the 88 pseudo option-array stats have no other
  encoding, and `bpc/pricing.py::_build_stat_groups` already emits `val["option"] = f["option"]`
  (lines 178-179, 189-190) into `{"id":sid,"value":{"option":…}}`.
- **[INFERRED]** that a *flattened* `base|opt` entry must be SPLIT (use `base` as id, the trailing
  integer as `value.option`) rather than sent verbatim as `{"id":"base|opt"}`. No bundled dump runs
  such a search. The split form is the canonical trade-site wire format and is the safe choice; the
  registry builder MUST perform this split (the current `_statf`/`statmap` path stores the id
  verbatim, so option-stats need this transform added — see §14). **Verify once live** (D-0019's
  sole-trade-budget spot-check) before shipping — a verbatim `base|opt` id would 400 if unsupported.

### 0.2 How the item's mod text reaches you (codebase pipeline) [SRC]
`bpc/poeninja.py::_all_explicit_mods` flattens these item buckets into the parallel lists
`Item.explicit_mods` + `Item.mod_src` (the trade group to scope each match in):
`explicitMods→explicit`, `craftedMods→crafted`, `fracturedMods→fractured`, `enchantMods→enchant`,
`utilityMods→explicit`, `scourgeMods→scourge`, `crucibleMods→crucible`, `veiledMods→veiled`.
`Item.implicit_mods` is a **separate** list (`d["implicitMods"]`) and is **NOT** iterated by
`Pricer.affix_options` today — so implicit-variant uniques (Precursor's Emblem, synthesis Circles)
are currently invisible to the pricer and need an implicit-scoped pass added (see §11-12, §14).
`StatMapper.match(text, group=…)` normalises text via `util.mod_to_pattern` (numbers→`#`, rich
markup stripped) and looks up the stat id within the given group.

---

## 1. Per-class recipe table (summary)

| Class | Kind | Base stat id(s) | What varies | From item text |
|---|---|---|---|---|
| Forbidden Flesh | OPTION | `explicit.stat_1190333629` (165 opts) | ascendancy notable = option | "Allocates **X** …Forbidden Flesh" → notable→option |
| Forbidden Flame | OPTION | `explicit.stat_2460506030` (165 opts) | ascendancy notable = option | "Allocates **X** …Forbidden Flame" → notable→option |
| Watcher's Eye | VALUE ×N | one `explicit.stat_*` per aura mod | which aura mods + rolls | each "…while affected by **Aura**" → sid+min |
| Impossible Escape | OPTION | `explicit.stat_2422708892` | keystone = option | "Passives in Radius of **K** can be Allocated…" |
| Timeless jewel (×5) | VALUE exact | `explicit.pseudo_timeless_jewel_<conq>` (20) | conqueror=id, seed=number | split `\n`; parse seed line; min=max=seed |
| Cluster notable / Megalomaniac | FLAG ×N | one `explicit.stat_*` per notable | which notables | each "1 Added Passive Skill is **X**" → sid |
| Cluster small-grant | OPTION | `enchant.stat_3948993189` | reward = option | "Added Small Passive Skills grant: **R**" |
| Cluster sockets / size | VALUE | `enchant.stat_4079888060`, `enchant.stat_3086156145` | socket & passive count | "# Added…Jewel Sockets", "Adds # Passive Skills" |
| Thread of Hope | OPTION | `explicit.stat_3642528642` (5 opts) | ring size = option 1–5 | "Only affects Passives in **Size** Ring" |
| Grand Spectrum | VALUE/FLAG | one `explicit.stat_*` per bonus | which bonus (colour) | "…per Grand Spectrum" → sid |
| Voices | VALUE exact | `explicit.stat_1085446536` | 3/5/7 small passives | "Adds **N** Small Passive Skills which grant nothing" |
| Precursor's Emblem | VALUE (implicit) | per-variant `implicit.stat_*` | which implicit | implicit line → sid+min (needs implicit scan) |
| Synthesis Circle | VALUE (implicit) | per-variant `implicit.stat_*` | which implicit + herald | implicit line → sid+min (needs implicit scan) |
| Split Personality | VALUE | own `explicit.stat_*` | which attribute reward | name + own explicit sids |
| That Which Was Taken | VALUE | own `explicit.stat_*` | which explicit rolls | name + own explicit sids |

---

## 2. Forbidden Flesh / Forbidden Flame (Allocates ascendancy notable) — OPTION

- **Base ids [SRC]:** Flesh = `explicit.stat_1190333629`; Flame = `explicit.stat_2460506030`.
- **Option count [SRC]:** 165 notables each (verified: 165 distinct `|optionid` entries per base —
  covers every "matching modifier"-allocatable ascendancy notable).
- **Entry form:** `explicit.stat_1190333629|4194` = "Allocates Berserker if you have the matching
  modifier on Forbidden Flesh"; `explicit.stat_2460506030|33645` = "Allocates Oath of Summer if you
  have the matching modifier on Forbidden Flame".
- **Item mod text:** "Allocates **&lt;Notable&gt;** if you have the matching modifier on Forbidden
  Flesh/Flame" (one explicit mod). The pair only functions if BOTH pieces name the same notable, but
  each ITEM is only Flesh or Flame — **search each item on its own base id**.
- **Recipe:**
  1. Detect by base type "Forbidden Flesh" / "Forbidden Flame".
  2. Extract the notable from the "Allocates **X**" segment of the item's explicit mod (match on the
     notable substring, not full-string equality — robust to the "if you have the matching modifier…"
     clause being present/absent/newline-split).
  3. Find the flattened entry under the correct base whose text contains "Allocates X"; take the
     integer after the `|`.
  4. Emit (split rule §0.1): `{"id":"explicit.stat_2460506030","value":{"option":33645}}`.
  Search with name+type (the item's own name) AND this option filter. No min/max.
- **Note:** item mod-text format is **[INFERRED]** from the stat text (the sample char carries no
  Forbidden jewel); substring-matching the notable makes the recipe format-agnostic.

## 3. Watcher's Eye (aura mods) — VALUE × N

- **Kind:** each aura mod is its **own** plain explicit VALUE stat; the variant = *which* aura mods
  are present and their rolls (a 1/2/3-mod Watcher's Eye). No option, no pipe.
- **Sample ids [SRC]** (of ~144 "while affected by" explicit stats):
  - `explicit.stat_2255914633` "Gain #% of Physical Damage as Extra Lightning Damage while affected by Wrath"
  - `explicit.stat_1222888897` "Damage Penetrates #% Cold Resistance while affected by Hatred"
  - `explicit.stat_3111519953` "Damage Penetrates #% Fire Resistance while affected by Anger"
  - `explicit.stat_2643562209` "Adds # to # Cold Damage while affected by Hatred"
  - `explicit.stat_3627458291` "+#% to Critical Strike Multiplier while affected by Anger"
- **Recipe:** name "Watcher's Eye" + type "Prismatic Jewel"; for each explicit mod line,
  `StatMapper.match(line)` (explicit group) → `{"id":sid,"value":{"min":<roll from util.first_number>}}`.
  AND-group all matched aura mods — that combination IS the variant identity. The generic Watcher's
  Eye "+#% to maximum Energy Shield"/life lines can be included as-is; the aura mods are the price
  drivers. This class already works via the normal explicit-mod path once mapped.

## 4. Impossible Escape (keystone radius) — OPTION

- **Base id [SRC]:** `explicit.stat_2422708892`. Keystone = option. Entry form:
  `explicit.stat_2422708892|31703` = "Passives in Radius of Pain Attunement can be Allocated
  without being connected to your tree"; `…|34098` = Mind Over Matter; `…|17818` = Crimson Dance;
  `…|12926` = Iron Grip; `…|56075` = Eldritch Battery; `…|50288` = Iron Will; `…|18663` = Minion
  Instability; `…|19732` = The Agnostic (many more).
- **Do NOT confuse with siblings [SRC]:** `explicit.stat_1725885727` "Passive Skills in Radius can
  be Allocated…" (Intuitive Leap, no keystone) and `explicit.stat_1211779989` "Keystone Passive
  Skills in Radius…" (generic) are different stats — Impossible Escape is the **`_2422708892`** family.
- **Item mod text:** "Passives in Radius of **&lt;Keystone&gt;** can be Allocated without being
  connected to your tree".
- **Recipe:** extract the keystone name (the "Radius of **X**" segment) → find the
  `explicit.stat_2422708892|…` entry containing that keystone → split → `{"id":
  "explicit.stat_2422708892","value":{"option":<opt>}}`, plus name "Impossible Escape".

## 5. Timeless jewels (×5) — VALUE, EXACT seed (why they are "worse")

- **20 seed stat ids [SRC]** — the conqueror is encoded in the id; the `#` is the seed:

  | Jewel [LORE] | Seed stat text | Conqueror stat ids `explicit.pseudo_timeless_jewel_…` |
  |---|---|---|
  | Glorious Vanity (Vaal) | "Bathed in the blood of # sacrificed in the name of **X**" | `_doryani`, `_xibaqua`, `_ahuana`, `_zerphi` |
  | Lethal Pride (Karui) | "Commanded leadership over # warriors under **X**" | `_rakiata`, `_kaom`, `_akoya`, `_kiloava` |
  | Brutal Restraint (Maraketh) | "Denoted service of # dekhara in the akhara of **X**" | `_nasima`, `_asenath`, `_balbala`, `_deshret` |
  | Militant Faith (Templar) | "Carved to glorify # new faithful converted by High Templar **X**" | `_avarius`, `_maxarius`, `_dominus`, `_venarius` |
  | Elegant Hubris (Eternal) | "Commissioned # coins to commemorate **X**" | `_victario`, `_cadiro`, `_caspiro`, `_chitus` |

- **Item mod text — the trap [SRC]:** in `char_poe1.json` the Elegant Hubris stores the seed line
  **newline-joined with the conqueror line as ONE explicit mod**:
  `"Commissioned 29120 coins to commemorate Caspiro\nPassives in radius are Conquered by the Eternal Empire"`.
  `util.mod_to_pattern` collapses the `\n` to a space, so the naive text-match FAILS (it never
  equals the stat text "Commissioned # coins to commemorate Caspiro"). This is the concrete reason
  timeless jewels need bespoke handling.
- **"Conquered by the &lt;X&gt;" is NOT searchable [SRC]:** 0 hits in the stat dump. The conqueror
  is fully captured by the seed stat id — ignore the "Conquered by" line entirely.
- **Recipe:**
  1. Detect a timeless jewel (base type is one of the five names, or any explicit mod matches one of
     the 5 seed-phrase templates).
  2. Split the combined explicit mod on `\n`; take the seed sub-line.
  3. Parse conqueror (word after "commemorate/under/akhara of/name of/High Templar") → stat id
     suffix; parse the integer → seed. The displayed number **is** the filter number (the stat text
     uses the same "coins/warriors/…" count — no transform).
  4. Emit **exact**: `{"id":"explicit.pseudo_timeless_jewel_caspiro","value":{"min":29120,"max":29120}}`,
     plus the item name.
- **Why worse than every other class:** (a) mod is `\n`-bundled → breaks text-match; (b) filter is
  an **exact** seed (min=max), not a threshold — a different seed is a different jewel; (c) the
  conqueror lives in the id, not a value; (d) the seed silently determines dozens of passive
  transforms that are NOT printed as mods, so only exact-seed matching returns the SAME jewel. Price
  the exact `(conqueror, seed)` line on poe.ninja's Unique* variant enumeration.

## 6. Cluster jewel notables + Megalomaniac ("Added Passive Skill is X") — FLAG × N

**[SRC] Correction to the D-0019 task premise:** "1 Added Passive Skill is X" is **not** an option-
stat. Each notable is its **own individual `explicit.stat_*` FLAG** (value-less, fully-resolved
text). ~605 such entries. The item stores them in `explicitMods` (also mirrored in `fractured` if
fractured). The real cluster **option-stat** is the *small-passive grant* (§7).

- **Notable flag ids [SRC] (examples):** `explicit.stat_2780712583` "1 Added Passive Skill is Touch
  of Cruelty"; `explicit.stat_2342448236` "…Prismatic Heart"; `explicit.stat_3599340381` "…Fuel the
  Fight". Fractured variant: `fractured.stat_2780712583` (same number, `fractured` prefix).
  Verified present in `char_poe1.json` cluster jewels: "1 Added Passive Skill is Empowered Envoy",
  "…Endbringer", "…Touch of Cruelty", "…Unspeakable Gifts", "…Unwaveringly Evil".
- **Recipe (Megalomaniac = unique 3-notable Medium Cluster):** name "Megalomaniac" + AND-group its
  three "1 Added Passive Skill is X" FLAG stats. Each: `{"id":"explicit.stat_2780712583"}` (no value;
  a harmless `{"min":1}` is acceptable since text "1 …" → `util.first_number`=1). Match each notable
  by text in the **explicit** group (`mod_src`="explicit"). `util.mod_to_pattern` turns the leading
  "1 " into "# " on both item and stat sides, so they align.
- **Recipe (regular cluster jewel):** AND its notable flags (§6) + the small-grant option (§7) +
  socket/size values (§8). All present in the item's own enchant/explicit buckets.

## 7. Cluster "Added Small Passive Skills grant: R" — OPTION

- **Base id [SRC]:** `enchant.stat_3948993189`. Reward = option. Entry form:
  `enchant.stat_3948993189|10` "Added Small Passive Skills grant: 10% increased Spell Damage";
  `…|20` "…12% increased Physical Damage over Time"; `…|26` "…10% increased Damage while affected by
  a Herald". The reward's own number is part of the option identity (fixed per reward), not a roll.
- **Item mod text [SRC]:** in `enchantMods`, e.g. "Added Small Passive Skills grant: 12% increased
  Chaos Damage" (char Phoenix Star). `mod_src`="enchant" → scope the match to the **enchant** group.
- **Distinguish from "…ALSO grant: R" [SRC]:** the item ALSO carries "Added Small Passive Skills
  **also** grant: …" lines in `explicitMods` — a different stat family (the jewel's own explicit
  extra grant). Different text, different group; don't conflate.
- **Recipe:** match the "…grant: R" line in the enchant group → resolve the `|opt` → split →
  `{"id":"enchant.stat_3948993189","value":{"option":<opt>}}`. **Caveat:** because
  `util.mod_to_pattern` strips the reward's number, two rewards that differ only by number could
  collide in the text→id map (first wins). For an exact reward match the registry should key off the
  **un-normalised** reward text, not the `#`-normalised pattern.

## 8. Cluster socket / passive counts — VALUE

- `enchant.stat_4079888060` "# Added Passive Skills are Jewel Sockets" (value = socket count; char
  shows 1 or 2). Singular "1 Added Passive Skill is a Jewel Socket" normalises to the same pattern. [SRC]
- `enchant.stat_3086156145` / `explicit.stat_3086156145` "Adds # Passive Skills" (value = total
  passive count, e.g. 4/5/8 by cluster size). Scope by `mod_src`. [SRC]
- Recipe: plain VALUE filters `{"id":sid,"value":{"min":N}}` (or exact for a variant match).

## 9. Thread of Hope (ring size) — OPTION

- **Base id [SRC]:** `explicit.stat_3642528642`. Ring size = option:
  `|1`=Small, `|2`=Medium, `|3`=Large, `|4`=Very Large, `|5`=Massive.
- **Item mod text:** "Only affects Passives in **&lt;Size&gt;** Ring".
- **Recipe:** map the size word to 1–5 → split → `{"id":"explicit.stat_3642528642","value":
  {"option":N}}`, plus name "Thread of Hope". The ring size is the whole variant (it dictates which
  passive band the jewel reaches) and drives the price.

## 10. Grand Spectrum — VALUE / FLAG (variant = which bonus)

- **Kind:** each bonus is its own `explicit.stat_*` "…per Grand Spectrum"; the colour/base picks the
  family. Ids [SRC]: `explicit.stat_242161915` "+#% to all Elemental Resistances per Grand Spectrum",
  `explicit.stat_3163738488` "#% increased Elemental Damage per Grand Spectrum",
  `explicit.stat_2948375275` "…Critical Strike Chance…", `explicit.stat_308799121`/`596758264`/
  `2276643899` "+# to Minimum Power/Frenzy/Endurance Charges per Grand Spectrum", etc.
- **Recipe:** name "Grand Spectrum" (+ the specific base: Viridian/Cobalt/Crimson Jewel via type)
  + the matched explicit stat id (presence is enough to pin the variant; the "per Grand Spectrum"
  value is fixed by the base so a min bound is optional).

## 11. Voices (empty passive sockets) — VALUE, EXACT

- **Ids [SRC]:** `explicit.stat_1085446536` "Adds # Small Passive Skills which grant nothing"
  (# = 3/5/7 — this number IS the variant); `explicit.stat_3086156145` "Adds # Passive Skills".
- **Recipe:** name "Voices" + `{"id":"explicit.stat_1085446536","value":{"min":N,"max":N}}` with N
  the exact count → pins the 1×7 / 2×5 / 3×3 sub-variant (corrupted Voices differ by this number).

## 12. Precursor's Emblem & synthesis "Circle of X" rings — VALUE via IMPLICIT

- **Kind:** the variant is an **implicit** mod, not explicit. Examples [SRC]: implicit
  `implicit.stat_2353576063` "#% increased Effect of your Curses"; `implicit.stat_991194404`
  "Regenerate #% of Energy Shield per Second while affected by Discipline"; `implicit.stat_1873457881`
  "#% additional Physical Damage Reduction while affected by Determination". Precursor's Emblem
  variants are its charge/resistance/attribute implicits (each a plain `implicit.stat_*`).
- **GAP [SRC]:** `Pricer.affix_options` iterates only `explicit_mods`+defences, never
  `implicit_mods`, so these variants are invisible today. The feature must add an **implicit-scoped**
  pass: for each `Item.implicit_mods` line, `StatMapper.match(line, group="implicit")` →
  `{"id":sid,"value":{"min":<roll>}}` and AND it into the unique's query.
- **Recipe:** name + type + the item's implicit-mod filter(s) in the `implicit` group.

## 13. Name-only variant uniques — VALUE (own explicit mods)

**Split Personality** and **That Which Was Taken** carry no special option/flag encoding — the
variant is *which of the item's own explicit rolls* are present (attribute/life/mana/ES rewards for
Split Personality; the rolled explicit stats for That Which Was Taken). Their names are not stat
entries. Recipe: name + the item's own explicit stat ids via the normal `affix_options` path (each
`explicit.stat_*` matched by text). No bespoke handling beyond preferring the defining explicit rolls.

---

## 14. Implementation notes for the registry builder (D-0019)

1. **Split the pipe (§0.1).** For any matched entry whose id contains `|`, emit
   `{"id":id.split("|")[0], "value":{"option":int(id.split("|")[1])}}`. The current `_statf`
   (`pricing.py`) and `StatMapper` store ids verbatim — add this split for option-stats. [INFERRED
   wire form → live spot-check per D-0019.]
2. **Timeless jewels need `\n`-splitting BEFORE matching (§5).** Split each explicit mod on newline
   and test each sub-line; the seed line matches an `explicit.pseudo_timeless_jewel_*` template.
   Emit exact `min==max`. Drop the "Conquered by" sub-line.
3. **Notable/keystone/ring lookups key off the un-normalised text (§2,4,6,7,9).** For OPTION and
   per-notable FLAG stats, resolve by the notable/keystone/reward **name substring** against the
   dump, not the `#`-normalised pattern (which discards the distinguishing text/number and can
   collide).
4. **Add an implicit-scoped pass (§12)** so implicit-variant uniques (Precursor's Emblem, Circles)
   contribute their defining filter.
5. **Group scoping is load-bearing.** Use `Item.mod_src[i]` to scope each match (enchant vs explicit
   vs fractured vs implicit): identical text maps to different ids per group
   (`enchant.stat_X` ≠ `explicit.stat_X`).
6. **D-0015 compliance.** Every filter here is ADDITIVE (a required defining filter). Nothing here
   removes a user-kept mod; it makes a variant search MORE faithful to the exact item.
7. **Shippable source confirmed [SRC]:** `public/api/_data/trade_stats.json` (the slim public bundle)
   carries every base id above (Forbidden ×2, timeless, Thread of Hope, cluster grant+notable,
   Impossible Escape `_2422708892`, Watcher samples, Voices) — the registry can be generated offline
   from it, no live `/data/stats` fetch needed.
