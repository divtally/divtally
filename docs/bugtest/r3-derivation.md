# D-0020 Round 3 - Offline query-derivation audit (query TRUTH)

**Scope:** For every item row in the four owner Allflame builds (fetched fresh from poe.ninja,
`status=available`, no cache, no pathofexile.com), re-derive from the item's OWN data + the
BUNDLED trade schema + the documented rules what each `trade_query` SHOULD contain, and DIFF
against what the engine emitted. Question answered: *does every search we generate actually
describe the item, and can a real listing satisfy it.*

**Builds** (all league `Allflame`, a real tradeable league; `data/leagues` fixture confirms):
| # | char | items | rare | unique | magic | gem | ninja-priced |
|---|---|---|---|---|---|---|---|
| 1 | qwartus_niceboat | 30 | 9 | 5 | 3 | 12 | 16 |
| 2 | SergoheroGaz | 29 | 6 | 15 | 3 | 5 | 19 |
| 3 | ArleAllflame | 36 | 11 | 20 | 1 | 4 | 23 |
| 4 | TimeForAurab | 31 | 3 | 13 | 8 | 7 | 18 |

**Method.** An independent oracle (`scratchpad/audit.py`) rebuilds each expected query directly
from `_data/trade_stats.json` (the shipped slim schema the code sees) + `trade_data_filters.json`
(category options) + the D-0016/15/17/18/19 rules, WITHOUT importing `querybuild`, and validates
every emitted id/category/filter against the raw schema. Cross-checks against the full
`research/data/trade_stats.json`. All derivation inputs (normalised `Item` fields, `affix_options`,
`trade_query`, `trade_url`) were dumped per item and diffed mechanically, then the price-critical
and structurally-diverse queries were inspected by hand mod-by-mod.

---

## Verdict

The mechanical derivation is **correct across the board** - category scope, the 85% armour rule,
links, status, swap exclusion, `trade_url==trade_query`, and the entire D-0019 variant/timeless
machinery all verified clean on all four builds (matrix in section 3). **Two real query-truth
defects** survive, both concentrated on **cluster jewels** (and one allocate-enchant rare); one is
documented in the project's own research notes as an unfinished transform. One minor
duplicate-id fragility and one verify-live name case round it out.

| ID | Sev | Finding | Items hit (these builds) |
|---|---|---|---|
| **F1** | **MAJOR** | Option-stats emitted as verbatim `base\|opt` piped ids - never split to `{id:base,value:{option:N}}` | 10 default queries (all cluster jewels + Entropy Idol) + 16 picker rows |
| **F2** | **MAJOR** | Singular "1 Added Passive Skill is a Jewel Socket" silently dropped (schema/enchant has plural only) | 6 Medium Cluster Jewels |
| **F3** | minor | Duplicate-display-text stat ids: code picks first-in-schema; may not be the item's id | 3 filters (Onslaught x1, Mana-Reservation-Eff x2) |
| **F4** | verify-live | League name-prefix "Foulborn <unique>" carried verbatim into trade `name` | 2 uniques (Esh's Mirror, Matua Tupuna) |

---

## F1 - Option-stats sent as verbatim piped ids (MAJOR)

**The defect.** The bundled schema pre-flattens option-stats into one entry per option, with the
option baked into the id after a pipe: `enchant.stat_3948993189|31` = "Added Small Passive Skills
grant: 10% increased Area Damage" (1427 such piped entries; the bare base id `enchant.stat_3948993189`
does **not** exist as its own entry). GGG's trade **search** wants the SPLIT form
`{"id":"enchant.stat_3948993189","value":{"option":31}}`. The variant path (`variantreg` /
`_apply_defining`) splits correctly - but the normal affix path (`StatMapper.match` ->
`affix_options` -> `_statf`) emits the raw piped id **verbatim, with no `option` value**.

`public/api/_lib/statmap.py` has zero pipe handling; `querybuild.py::_rare_default_filters._statf`
does `{"id": o["stat_id"]}` where `stat_id` is the piped id straight from `mapper.match`.

**This is a known, flagged-but-unfinished transform.** `docs/research/variant-stats.md` sec 0.1:
> "a *flattened* `base|opt` entry must be SPLIT ... rather than sent verbatim as `{"id":"base|opt"}`.
> ... the registry builder MUST perform this split (**the current `_statf`/`statmap` path stores the
> id verbatim, so option-stats need this transform added** - see sec 14). ... a verbatim `base|opt`
> id would **400 if unsupported**."

The registry got the split (D-0019); the general affix path did not.

**Evidence - Pandemonium Shine (build2, rare Medium Cluster Jewel), the mod
"Added Small Passive Skills grant: 10% increased Area Damage":**
```
ACTUAL   (emitted default query filter):  {"id": "enchant.stat_3948993189|31"}
EXPECTED (GGG wire form / variant-stats sec 0.1): {"id": "enchant.stat_3948993189", "value": {"option": 31}}
```

**Blast radius on these builds** - 10 piped filters in ACTUAL default (autoscan) queries:
| build | item | piped filter id | mod |
|---|---|---|---|
| 1 | Entropy Idol (rare Jade Amulet) | `enchant.stat_2954116742\|20832` | Allocates Sanctuary (enchant) |
| 2 | Hypnotic Ruin (Large Cluster) | `enchant.stat_3948993189\|8` | Small Passives grant: 12% inc. ... |
| 2 | Pandemonium Shine (Med Cluster) | `enchant.stat_3948993189\|31` | Small Passives grant: 10% inc. Area Dmg |
| 2 | Cataclysm Ornament (Med Cluster) | `enchant.stat_3948993189\|31` | " |
| 3 | Hypnotic Solace / Soul Desire / Dragon Stone / Fulgent Bliss (Med Cluster) | `...\|31` | " |
| 3 | Gale Desire / Foe Bliss (Large Cluster) | `...\|8` | " |

Plus 16 `affix_options` picker rows carry the piped `stat_id` with `option` **absent** (so the
manual/advanced search path is broken too), including the "Allocates X" enchants on uniques
Ashes of the Stars, The Jinxed Juju and the build-4 Small Cluster Jewels.

**Impact.** For every RARE with an option-stat mod (cluster jewels are the common case, and every
cluster jewel has "Added Small Passive Skills grant: X"), the generated default/autoscan query
contains a filter the trade API does not recognise in that shape. Per the project's own note it
"would 400 if unsupported" - meaning the **whole** search for that item fails, not just that one
filter, so the item shows no price and its trade link is broken. Worst realistic case is a wrong
(over-broad) match if the API silently drops the unknown id. Either way the search does **not**
describe the item. Guardrail holds (no *wrong number* is shown - the item just stays unpriced), so
this is MAJOR rather than a misleading-price blocker, but it silently defeats cluster-jewel pricing.

**Fix.** Where `mapper.match` returns an id containing `|`, split it: `base, opt = sid.split("|",1)`
and carry `{"id": base, "value": {"option": int(opt)}}` - in `affix_options` (set `row["stat_id"]`
to the base and `row["option"]`) and in `_statf`/`_rare_default_filters` (emit `value.option`).
`_build_stat_groups` already threads `option` (querybuild.py:225-226), and `_apply_defining` already
does exactly this split for variants - reuse that logic. **The one thing to confirm live** (F1 is in
the sample below): whether a verbatim piped id 400s the search or is silently ignored.

---

## F2 - Singular "1 ... is a Jewel Socket" dropped from cluster-jewel queries (MAJOR)

The schema's only Jewel-Socket-added stat is the **plural** `stat_4079888060` =
`"# Added Passive Skills are Jewel Sockets"` (in Explicit/Fractured/Enchant). A cluster jewel with
exactly one jewel socket renders the **singular** `"1 Added Passive Skill is a Jewel Socket"`, whose
pattern (`# Added Passive Skill is a Jewel Socket`) does not equal the plural pattern, and because the
mod is an **enchant** the mapper never falls back to another group -> it is dropped as unsearchable and
omitted from the query. This is the same singular/plural class as the R1 Bubonic Trail abyssal-socket
fix (D-0020 R1), unfixed for jewel sockets.

**Clean isolation** (same registry, count is the only difference):
| item | jewel-socket mod (verbatim) | matched? |
|---|---|---|
| Hypnotic Ruin (Large Cluster) | `2 Added Passive Skills are Jewel Sockets` (plural) | YES -> `enchant.stat_4079888060` emitted |
| Pandemonium Shine (Medium Cluster) | `1 Added Passive Skill is a Jewel Socket` (singular) | NO -> dropped |

```
Pandemonium Shine ACTUAL stats.filters ids:
  [explicit.stat_1811604576, explicit.stat_3721672021, explicit.stat_4222265138,
   explicit.stat_2886441936, enchant.stat_3086156145, enchant.stat_3948993189|31]
EXPECTED to also contain the jewel socket:
  {"id": "enchant.stat_4079888060", "value": {"min": 1}}      # "# Added Passive Skills are Jewel Sockets"
```

Hits 6 Medium Cluster Jewels (build2 Pandemonium Shine, Cataclysm Ornament; build3 Hypnotic Solace,
Soul Desire, Dragon Stone, Fulgent Bliss). A jewel socket is a real value driver on a cluster jewel;
omitting it relaxes the search to a superset (matches otherwise-identical clusters with no socket),
biasing price **low** and mis-describing the item. **Fix:** normalise the singular text to
`stat_4079888060` with the count read from the "1" (mirror the R1 abyssal-socket normalisation).

---

## F3 - Duplicate-display-text stat ids (minor / fragility)

`mod_to_pattern` collapses the roll number to `#`, so distinct stats with identical display text
(and, for durations, distinct numbers) map to one pattern; `StatMapper` keeps the **first** id in
schema order. Three emitted filters land on such ids:

| build | item | mod | picked id | pattern shared by |
|---|---|---|---|---|
| 1 | Brood Slippers | 16% chance to gain Onslaught for 4 seconds on Kill | `explicit.stat_665823128` | 3 ids - two "4 seconds", one **"10 seconds"** (collides because the duration -> `#`) |
| 4 | Armageddon Star | 3% increased Mana Reservation Efficiency of Skills | `explicit.stat_1269219558` | 2 ids (identical text) |
| 4 | Luminous Curio | 3% increased Mana Reservation Efficiency of Skills | `explicit.stat_1269219558` | 2 ids (identical text) |

In an AND-all default query, if the item's actual underlying id differs from the one picked, that
filter matches nothing -> the whole item over-constrains to 0 results (contributes to the "no buyout"
class the owner has fought). No *wrong price* results (guardrail holds), so minor - but the search may
not match its own item. The Onslaught duration collapse is the sharper edge: a genuine "10 seconds on
Kill" item would be searched with a "4 seconds" id. (None of the four builds carry the 10s variant, so
no live miss here.) Options: OR duplicate-text ids in a `count>=1` group, or drop the magnitude for
these ids.

---

## F4 - "Foulborn <unique>" league-prefix names (verify live, not a confirmed defect)

Allflame decorates some uniques with a name prefix ("Foulborn Esh's Mirror" on a Vaal Spirit Shield;
"Foulborn Matua Tupuna"). The prefix is carried verbatim into the trade `name`:
```
{"status":{"option":"available"}, "name":"Foulborn Esh's Mirror", "type":"Vaal Spirit Shield", ...}
```
poe.ninja **does** enumerate "Foulborn ..." lines (these priced via `unique-ninja-range`/`-variant`),
and the league is tradeable, so the trade site plausibly indexes the same name - but a base-game unique
named "Foulborn Esh's Mirror" does not exist, so if trade treats "Foulborn" as a modifier on the base
unique rather than a distinct name, the search returns nothing. Contrast "Replica X" (Replica Voidwalker,
Replica Maloney's), which **are** real distinct tradeable names and are correct. **Confirm in the live
sample**; if trade rejects the prefixed name, strip the league prefix and search the base unique name.

---

## 3. What PASSED (verified correct on all four builds)

| Rule | Verified | Evidence |
|---|---|---|
| **Category scope (D-0016)** | every default scope is a real `category` option id in `trade_data_filters.json`, correct for the slot | Grim Coat->`armour.chest`, Storm Thirst (Convoking Wand)->`weapon.wand`, rings->`accessory.ring`, clusters->`jewel`, flasks->`flask` |
| **armour_filters 85%** | `min == int(0.85*total)` for every armour piece, exact | Woe Ward es447->379, Brood es312->265, Tempest es413->351, Grim Coat es1253->1065 |
| **Links** | `socket_filters.links.min == max_link`, present iff `>=5` | Grim Coat 6L->`{"min":6}`; 4L/3L items -> no links filter |
| **Status (D-0017)** | `{"option":"available"}` on 100% of queries | all builds |
| **Swap (D-0018)** | Weapon2/Offhand2 flagged `swap:true` and excluded from totals | build1 `priced_items=16` excludes the swap Maloney's (11c) and Bone Bow; build3 excludes swap Atziri's Disfavour (245c) |
| **trade_url == trade_query** | `?q=` decodes byte-for-byte to the payload | all rows |
| **Unique name+base** | name + base carried; skill-level rolls locked as `{min}` | Headhunter/Nimis name+base; Ashes of the Stars + Dark Seer lock a `+#` skill-level roll |
| **Timeless seed (D-0019)** | exact seed `{"min":N,"max":N}` on the correct conqueror id | Lethal Pride `explicit.pseudo_timeless_jewel_rakiata {"min":13032,"max":13032}` |
| **Notable-jewel option (D-0019)** | correct base id + option int, option resolves to the named notable | Forbidden Flame/Flesh option `43195` -> child text "Allocates Slayer" for both `2460506030` and `1190333629` |
| **Socket-defined (D-0019)** | abyssal count from the socket array, `{"min":N,"max":N}` | Bubonic Trail `explicit.stat_3527617737 {"min":1,"max":1}` |
| **Roll-defined (D-0019)** | each "while affected by" aura mod locked at its roll/flag | Watcher's Eye: Determination crit-reduction `>=53`, Grace suppress `>=14`, Purity-of-Ice chilled-ground flag (no value) |
| **Foil/relic routing (R1 fix)** | frameType 10 -> unique, priced + name search | Nimis (Topaz Ring, ~7000c) |
| **Gem queries** | `gem.activegem`/`gem.supportgem` category + `gem_level/quality/corrupted` misc | all 28 gems |
| **Local-defence exclusion** | flat/%-ES/AR/EV mods on armour omitted from stats (searched via armour_filters) | Grim Coat's "+105 to max ES" / "159% increased ES" correctly not in stats |
| **Negation shape** | (no `reduced` mods occurred; path present, `_swap` verified) | 0 `value.max` filters emitted |

No mismatches found in category, armour, links, status, swap, url, seed, option-int, or skill-level
derivations. The 3 automated "major" armour flags in an earlier oracle pass were **oracle bugs**
(wrong expected shape) - the emitted 85% values are all correct.

---

## 4. LIVE SAMPLE - 12 queries for the next phase (paced, sole trade budget)

Chosen for price-criticality + structural diversity + to confirm F1/F2/F4. "MUST match" = what a
returned listing has to show for the query to be honest. League = **Allflame** for all.

| # | build | item (scope) | Structural class / why | A returned listing MUST show |
|---|---|---|---|---|
| 1 | 2 | **Pandemonium Shine** (rare, `category:jewel`) | **F1 + F2** - piped grant enchant + dropped jewel socket | Confirm the query's live behaviour: does `enchant.stat_3948993189\|31` 400 or silently drop? Listing (Medium Cluster) must show both "also grant" mods + Assert Dominance + Magnifier + the Area-Damage grant + a jewel socket |
| 2 | 1 | **Entropy Idol** (rare Jade Amulet, `category:accessory.amulet`) | **F1** on a non-cluster rare (Allocates-enchant) | Amulet with the 7 mods incl. `Allocates Sanctuary`; confirm the `enchant.stat_2954116742\|20832` filter is honoured |
| 3 | 1 | **Grim Coat** (rare, `category:armour.chest`) | armour_filters(85%) + 6L links + multi-resist | ES >= 1065, 6-link, +Fire Res, +Lightning Res, Stun/Block Recovery, Cold+Chaos Res, the enchant |
| 4 | 1 | **Storm Thirst** (rare Convoking Wand, `category:weapon.wand`) | weapon subcategory derivation | a Wand carrying all 6 mapped mods |
| 5 | 2 | **Lethal Pride** (unique Timeless Jewel) | timeless exact-seed | "Commanded leadership over **13032** warriors under Rakiata" (exact seed) |
| 6 | 3 | **Forbidden Flame** (unique Crimson Jewel) | notable-jewel option (the CORRECT contrast to F1) | name Forbidden Flame + a listing whose option-43195 mod reads "Allocates Slayer ... Forbidden Flesh" |
| 7 | 4 | **Watcher's Eye** (unique Prismatic Jewel) | roll-defined multi-aura lock | all 3: Determination crit-dmg-reduction >= 53, Grace suppress >= 14, Purity-of-Ice chilled-ground |
| 8 | 4 | **Bubonic Trail** (unique Murder Boots) | socket-defined exact count | name + "Has 1 Abyssal Sockets" + the boots' link tier |
| 9 | 2 | **Headhunter** (unique Leather Belt, ~14613c) | highest-value plain unique name+base | name=Headhunter, base=Leather Belt returns live listings |
| 10 | 2 | **Inpulsa's Broken Heart** (unique Sadist Garb, 6L) | link-split unique + links filter | name + base + 6-link listings (ninja matched the 6L line) |
| 11 | 2 | **Nimis** (unique Topaz Ring, foil frameType 10, ~7000c) | foil routing + high value | name=Nimis, base=Topaz Ring returns listings |
| 12 | 3 | **Foulborn Esh's Mirror** (unique Vaal Spirit Shield) | **F4** - league name-prefix | confirm `name:"Foulborn Esh's Mirror"` returns listings in Allflame; else determine the correct name form |

Sample covers: both confirmed defects (1,2), the correct option contrast (6), every derivation class
(armour+links 3, weapon subcat 4, seed 5, socket-count 8, roll-lock 7, plain/link-split/foil uniques
9-11), and the one uncertain case (12); spread across all four builds.

---

## Appendix - artifacts

- Fresh API docs + per-item derivation bundles: `scratchpad/{build}_doc.json`, `{build}_deriv.json`
- Independent oracle + findings: `scratchpad/audit.py`, `scratchpad/{build}_findings.json`
- Fix targets: `public/api/_lib/statmap.py` (`match` - split piped ids) and
  `public/api/_lib/querybuild.py` (`affix_options` ~L421-435, `_statf`/`_rare_default_filters`
  ~L518-523 - carry `value.option`; jewel-socket singular normalisation).
