# poe.ninja Path of Exile 1 builds pipeline

Live reverse-engineering notes for porting `bpc/poeninja.py` (currently PoE2) to
**Path of Exile 1**. Everything here was verified against LIVE responses on
**2026-07-26** (current league **Allflame**). The parent PoE2 code lives at
`C:\scripts\buildpricechecker\bpc\poeninja.py` (read-only reference).

Provenance tags: facts below are **[LIVE]** (observed in an actual poe.ninja API
response), **[JS]** (read out of poe.ninja's own compiled front-end bundle), or
**[INFERRED]** (reasoned, not directly observed). No web-guide/wiki claims are used.

Saved artifacts (this folder's sibling `research/data/`):
- `char_poe1.json` - full character: account `example-0416`, char `TestCharacter`,
  Elementalist L100 (has a 6-link body armour - the canonical socket/link example).
- `char_poe1_unicode.json` - account `Poteitik-3151`, char `ПОТЕЙТИК` (Cyrillic) -
  demonstrates non-ASCII character/account names the port must handle.
- Reproduce with `python research/probe_ninja.py`.

---

## 0. TL;DR - what changes for the port

1. **Path prefix `/poe2/` becomes `/poe1/`.** The whole API mirrors PoE2 under a
   `/poe1/` prefix. `index-state` and `character` are shaped almost identically, and
   the **character endpoint returns JSON** just like PoE2 (so `r.json()` still works).
2. **`overview` param must be the `snapshotName`, and it now genuinely differs from
   the league url slug** (e.g. slug `allflamehc` -> snapshotName `hardcore-allflame`)
   for 96 of 106 snapshots. The parent already resolves this correctly; it is still
   load-bearing.
3. **The API only accepts the DASH-encoded account form** (`example-0416`). The raw
   `example#0416` returns **404**. Convert `#`+trailing-digits -> `-` before calling.
4. **Items carry classic PoE1 sockets/links** (`sockets:[{group,attr,sColour}]`).
   Max link = size of the largest `group` cluster. This is BRAND NEW vs PoE2 and is
   the single biggest addition the port needs (links pricing depends on it).
5. **Gems live in BOTH `item.socketedItems` (frameType 4) AND `skills[].allGems`.**
   Price gems via `skills[]` only (as the parent already does) to avoid double count.
   PoE2's rune extraction (frameType-5 socketedItems) finds nothing in PoE1 and should
   be deleted; PoE2 lineage-support logic is likewise dead in PoE1.
6. Delete the PoE2 guard in `parse_build_url` (it currently *rejects* PoE1 links).

---

## 1. User-facing URL (what a person pastes)

```
https://poe.ninja/poe1/builds/<league-slug>/character/<account-dash>/<charName>
```
Real, resolves 200: **[LIVE]**
```
https://poe.ninja/poe1/builds/allflame/character/example-0416/TestCharacter
```
- `<account-dash>` is the account with its `#1234` discriminator written as `-1234`.
- `<charName>` is URL-encoded (can be non-ASCII, e.g. `%D0%9F...` for Cyrillic). **[LIVE]**
- Optional trailing `?type=<ladderType>` when the ladder is not the default `exp`
  (e.g. `?type=depthsolo` for the Delve depth ladder). **[JS]**
- There is also a `.../passive-tree` variant of the same path. **[JS]**

**Positional parse** (identical layout to PoE2, so the parent's `parse_build_url`
anchor-on-`builds` logic ports directly): path parts `[poe1, builds, <slug>,
character, <account>, <char>]`; `builds` index = bi; slug=bi+1; require
parts[bi+2]=="character"; account=bi+3; char=bi+4. **[LIVE]** The ONE change: the
parent hard-rejects any URL without `poe2` (and prints "this looks like a Path of
Exile 1 link ... this tool only prices PoE2 builds"). Flip that: require `poe1`.

The `<account-dash>` in the pasted URL is already the form the API wants, so
`urllib.parse.unquote(parts[bi+3])` yields e.g. `example-0416` directly. Still run it
through the `#`->`-` encoder (section 8) in case a user hand-types a `#`.

---

## 2. Endpoint map

| Purpose | Method + URL | Returns |
|---|---|---|
| **Index / league list** | `GET https://poe.ninja/poe1/api/data/index-state` | JSON **[LIVE]** |
| **Character (THE one)** | `GET https://poe.ninja/poe1/api/builds/{version}/character?account={dash}&name={char}&overview={snapshotName}&timeMachine=` | **JSON [LIVE]** |
| Build-index landing | `GET https://poe.ninja/poe1/api/data/build-index-state` | JSON (aggregate stats only, no chars) **[LIVE]** |
| Character list / faceted search | `GET https://poe.ninja/poe1/api/builds/{version}/search?overview={snapshotName}` | **protobuf** (`application/x-protobuf`) **[LIVE]** |
| Search field dictionary | `GET https://poe.ninja/poe1/api/builds/dictionary` | (not needed) **[JS]** |
| Item tooltip | `GET https://poe.ninja/poe1/api/builds/{version}/tooltip` , `.../builds/tooltip/any` | (not needed) **[JS]** |
| Live streamers | `GET https://poe.ninja/poe1/api/builds/streamers/live` | JSON `{updatedAtUtc, items:[{twitchLogin,online}]}` **[LIVE]** |

Notes:
- The **404 error body is JSON** (RFC 9110 problem+json: `{"title":"Not Found","status":404,...}`),
  so a wrong account/name gives a clean JSON 404, not an HTML page. **[LIVE]**
- The old bare `/api/data/getindexstate` and `/api/data/index-state` (no game prefix)
  now **404** - PoE1 moved under `/poe1/`. **[LIVE]**
- The site itself is a static Astro shell that hydrates React islands; the API paths
  above were extracted from its compiled bundles at `https://assets.poe.ninja/_astro/*.mjs`. **[JS]**

The port only needs the two **bold** endpoints. The `/search` protobuf is used by
`research/probe_ninja.py` purely to discover a real (account,name) pair for testing.

### 2a. `/character` request params **[LIVE]**
`account` (dash form, required) · `name` (char name, required) · `overview`
(= snapshotName, required) · `timeMachine` (empty string for "latest"; a token like
`tm:day-1` for historical snapshots **[JS]**). Same param names as the PoE2 parent.

---

## 3. `index-state` response **[LIVE]**

`GET https://poe.ninja/poe1/api/data/index-state` ->
```
{ economyLeagues:[...], oldEconomyLeagues:[...],
  snapshotVersions:[...], buildLeagues:[...], oldBuildLeagues:[...] }
```

### snapshotVersions[] (106 entries)
```json
{ "url":"allflame", "type":"exp", "name":"Allflame",
  "timeMachineLabels":["hour-6","hour-18","hour-3","hour-12","day-2","day-1"],
  "version":"2019-20260726-01354", "snapshotName":"allflame",
  "overviewType":0, "passiveTree":"PassiveTree-3.29", "atlasTree":"AtlasTree-3.29" }
```
- Fields the parent uses -- `url`, `version`, `snapshotName`, `name` -- **all present.** **[LIVE]**
- **New PoE1 fields:** `type`, `timeMachineLabels`, `overviewType`, `passiveTree`,
  `atlasTree`. **[LIVE]**
- **GOTCHA: two rows per league url** -- one `type:"exp"` and one `type:"depthsolo"`
  (the Delve depth ladder), sharing the same `version` + `snapshotName`. The parent's
  "first match on url" still returns a usable version/snapshotName, but prefer
  `type=="exp"` for determinism. **[LIVE]**
- **`url != snapshotName` for 96/106 snapshots** (only the 4 flagship + a few match).
  Examples: `allflamehc`->`hardcore-allflame`, `allflamessf`->`ssf-allflame`,
  `allflamer`->`ruthless-allflame`. So `overview` MUST come from `snapshotName`, never
  the slug. **[LIVE]**

### buildLeagues[] (14 entries)
```json
{ "name":"Hardcore Allflame", "url":"allflamehc", "displayName":"Hardcore Allflame" }
```
- Parent reads `name`+`url` -- present. **New:** `displayName` (cleaner label; for
  private/event leagues `name` is like `"Les Croustipotes (PL83768)"` while
  `displayName` is `"Les Croustipotes"`). Consider using `displayName` for UI. **[LIVE]**

### oldBuildLeagues[] - `{name,url,displayName}` for leagues no longer snapshotted
(`Ancestors`, `Mirage`, ...). A slug found only here can't be priced; raise a clear
error (the parent already does this by absence from `snapshotVersions`). **[LIVE]**

---

## 4. Character JSON - top level **[LIVE]**

`char_poe1.json` top-level keys (Elementalist example):
```
account, name, league, defensiveStats, breakdowns, skills, level, class,
pathOfBuildingExport, items, keyStones, flasks, jewels, guardianItems,
passiveSelection, lastSeenUtc, updatedUtc, lastCheckedUtc, status,
itemProvidedGems, masteries, runegrafts, tattoos, banditChoice, pantheonMajor,
pantheonMinor, economy, baseClass, useSecondWeaponSet, ascendancyClassId,
ascendancyClassName, secondaryAscendancyClassId, secondaryAscendancyClassName,
passiveTreeName, atlasTreeName, clusterJewels, hashesEx
```
Everything the parent's `normalize()` reads is present:

| Parent reads | PoE1 value | Notes |
|---|---|---|
| `account` | `"example-0416"` | **dash form** (not `#`). **[LIVE]** |
| `name` | `"TestCharacter"` | can be non-ASCII **[LIVE]** |
| `class` | `"Elementalist"` | ascendancy name (see below) **[LIVE]** |
| `level` | `100` | **[LIVE]** |
| `league` | `"Allflame"` | display name; matches `buildLeagues[].name`. Parent injects `_league` but this real field is also a fine fallback. **[LIVE]** |
| `pathOfBuildingExport` | 13872-char string | base64(zlib(xml)), decodes to `<?xml ...><PathOfBuilding>` (section 9) **[LIVE]** |
| `items` | 11 entries | section 5 **[LIVE]** |
| `flasks` | 5 entries | section 7 **[LIVE]** |
| `jewels` | 19 entries | section 7 **[LIVE]** |
| `skills` | 6 entries | section 6 **[LIVE]** |

**Extra PoE1-only top-level blocks the parent ignores** (harmless, but documented for
future features): `baseClass` (`"Witch"`), `ascendancyClassName`/`ascendancyClassId`,
`secondaryAscendancyClassName` (observed value `"Lycia Bloodline"`; optional - absent
on the Champion example),
`defensiveStats` (`{life,energyShield,mana,ward,movementSpeed,lifeRegen,evasionRating,
armour,strength,dexterity,intelligence,enduranceCharges}`), `keyStones`
(`[{name,icon,stats}]`), `masteries` (`[{name,group,nodeId}]`), `runegrafts`
(`[{name,stats,nodeId,icon}]`), `tattoos` (`[{...}]`, empty here), `clusterJewels`
(dict keyed by tree node id), `guardianItems` (empty here), `passiveSelection`
(list of allocated node ids), `banditChoice` (`"Alira"`), `pantheonMajor`/`Minor`,
`itemProvidedGems` (`[{slot,gems:[{name,level,quality,isBuiltInSupport}]}]` - gems
granted by items), `passiveTreeName` (`"PassiveTree-3.29"`), `atlasTreeName`,
`useSecondWeaponSet`, `hashesEx`, `breakdowns`, `economy` (empty `{}` here),
`status`, `*Utc` timestamps. **[LIVE]**

---

## 5. Item JSON (`items[]`) - and the SOCKET / LINK model

### Wrapper
Each entry is `{ "itemData": {...}, "itemSlot": <int> }`. **[LIVE]**
PoE2 wrapper was `{itemData}` only; PoE1 adds `itemSlot` (int). You do NOT need
`itemSlot` -- `itemData.inventoryId` (string) is still present and is what the
parent's `_slot_name()` already reads. Mapping observed **[LIVE]**:

| itemSlot | inventoryId | | itemSlot | inventoryId |
|---|---|---|---|---|
| 1 | Helm | | 8 | Ring |
| 2 | Gloves | | 9 | Ring2 |
| 3 | BodyArmour | | 11 | Belt |
| 4 | Amulet | | 15 | Weapon2 (swap) |
| 5 | Boots | | 16 | Offhand2 (swap) |
| 7 | Weapon | | 12 | PassiveJewels (jewels) |

(PoE1 adds `Weapon2`/`Offhand2` swap slots and `PassiveJewels`; the parent's
`_INVENTORY_NAMES` already has `Weapon2`/`Offhand2` from PoE2.)

### `itemData` keys (rare/unique gear) **[LIVE]**
```
additionalProperties, baseType, corrupted, craftedMods, crucibleMods, duplicated,
enchantMods, explicitMods, flavourText, fractured, fracturedMods, frameType,
frameTypeId, h, icon, id, identified, ilvl, implicitMods, inventoryId, league,
mods, mutated, mutatedMods, name, properties, rarity, replica, requirements,
scourgeMods, searing, socketedItems, sockets, synthesised, tangled, typeLine,
utilityMods, verified, vestigial, w, x, y
```
Everything the parent's `_make_item` reads is present: `frameType`, `name`,
`baseType`, `typeLine`, `inventoryId`, `properties`, `explicitMods`, `implicitMods`,
`craftedMods`, `fracturedMods`, `enchantMods`, `corrupted`, `ilvl`, `support`,
`icon`, `mods`. **[LIVE]**

- `mods` shape is the same as PoE2: `{ "explicit":[{"id":..,"stats":{stat_id:val}}],
  "implicit":[...] }` (parent reads `mods.explicit`). **[LIVE]**
- `properties[]` are `{name, values:[[str,int]], displayMode, type}` -- same shape the
  parent's `_defences`/`_gem_level` parse. Defence property names are the classic
  `Armour`, `Evasion Rating`, `Energy Shield`, `Ward` and gem level lives under
  `Level` -- all match the parent. Body-armour example: `Quality => +20%`,
  `Armour => 1958`. **[LIVE]**

### SOCKETS + LINKS (new vs PoE2 - load-bearing for links pricing) **[LIVE]**
`itemData.sockets` is an array with **one object per socket**:
```json
"sockets": [
  {"group":0,"attr":"G","sColour":"W"},
  {"group":0,"attr":"D","sColour":"G"},
  {"group":0,"attr":"S","sColour":"R"},
  {"group":0,"attr":"G","sColour":"W"},
  {"group":0,"attr":"D","sColour":"G"},
  {"group":0,"attr":"D","sColour":"G"}
]
```
- **`group`** = the LINK-GROUP id. Sockets sharing a `group` are LINKED. **The item's
  max link = the size of the largest `group` cluster.** **[LIVE]**
- **`attr`** = socket attribute requirement, domain observed `{S,D,I,G}` = Str / Dex /
  Int / Generic(white). **[LIVE]** (`A`=abyssal, `DV`=delve appear on other items **[INFERRED]**.)
- **`sColour`** = display colour, domain observed `{R,G,B,W}` = Red / Green / Blue /
  White. **[LIVE]**

Worked examples from `char_poe1.json` **[LIVE]**:
| item | #sockets | groups (id:size) | MAX LINK |
|---|---|---|---|
| Blunderbore (BodyArmour) | 6 | `{0:6}` | **6L** |
| The Gull (Helm) | 4 | `{0:4}` | 4L |
| Boots | 4 | `{0:4}` | 4L |
| Gloves | 4 | `{0:4}` | 4L |
| The Golden Charlatan (Weapon) | 6 | `{0:2,1:2,2:2}` | 2L (3x 2-link) |
| Upgraded Thicket Bow (Weapon2) | 6 | `{0:2,1:2,2:2}` | 2L |
| Maloney's Mechanism (Offhand2/quiver) | 3 | `{0:3}` | 3L |

**Max-link algorithm:** `max(Counter(s["group"] for s in sockets).values())`
(0 if `sockets` is empty). Socket-colour string (for a trade query like "6L R-R-R-R-B-B")
= `[s["sColour"] for s in sockets]`. The parent has **no** socket/link handling today
(PoE2 has no links) -- this must be added to the `Item` model and to pricing.

### `socketedItems` = the GEMS (not runes) **[LIVE]**
In PoE1 `itemData.socketedItems` holds the **skill/support gems** socketed in the
item (frameType **4**), NOT PoE2's frameType-5 runes. Each entry:
```json
{ "socket":0, "colour":"I", "frameType":4, "frameTypeId":"Gem", "support":true,
  "typeLine":"Greater Spell Echo Support", "baseType":"Greater Spell Echo Support",
  "properties":[{"name":"Level","values":[["2",0]],"type":5},
                {"name":"Quality","values":[["+20%",1]],"type":6}, ...],
  "explicitMods":[...], "additionalProperties":[{"name":"Experience",...}],
  "abyssalSocket":..., "sockets":[], "socketedItems":[], "id":"...", "icon":"..." }
```
- `socket` = index into the item's `sockets` array. `colour` = I/S/D (int/str/dex).
- `support` distinguishes support gems from the active skill.
- Level/Quality come from `properties` (`"20 (Max)"`, `"+20%"`) exactly like the
  parent's `_gem_level` already parses. **[LIVE]**

**These same gems are ALSO enumerated in `skills[]` (section 6).** The parent prices
gems via `skills[]` only -- keep that, and do NOT also emit gems from
`socketedItems`, or every gem is priced twice. The parent's current rune-extraction
loop (`socketedItems` where `frameType==5`) matches nothing in PoE1 and should be
deleted per the clean-cutover rule.

### frameType domain seen **[LIVE]**
`1`=Magic, `2`=Rare, `3`=Unique, `4`=Gem (also `frameTypeId` mirrors as
`"Magic"/"Rare"/"Unique"/"Gem"`). Full PoE1 range is 0-9
(0 Normal,5 Currency,6 Divination,7 Quest,8 Prophecy,9 Relic **[INFERRED]**). The
parent's `FRAME_RARITY` maps `9`->`Foil`; in PoE1 `9`=Relic -- adjust if a relic
appears (cosmetic only; doesn't affect routing since categorisation keys on 1-5).

---

## 6. `skills[]` - gem groups **[LIVE]**

```json
{ "itemSlot":3, "dps":..., "allGems":[ {"name":"Ethereal Knives of the Massacre",
    "itemData":{...frameType:4, support:false...}},
    {"name":"Greater Spell Echo Support","itemData":{...support:true...}}, ... ] }
```
- Structure is the **same as PoE2**: each skill entry has `allGems`, where
  `allGems[0]` is the ACTIVE skill and the rest are its support gems. The parent's
  grouping logic (build one active-skill `Item`, attach supports, `gem_sockets =
  min(#supports,5)`) ports directly. **[LIVE]**
- Each gem entry has a top-level `name` **and** an `itemData` blob; the parent's
  `allg[0].get("itemData", allg[0])` and `gd.get("baseType") or gd.get("typeLine")`
  both work. **[LIVE]**
- `itemSlot` = which equipment slot the group is socketed in (lets you correlate a
  skill group to its host item's link count for "N-link skill setup" pricing). **[LIVE]**
- **No lineage supports in PoE1.** The parent's `_is_lineage` (checks properties for
  `LineageSupports`, a PoE2 mechanic) is always False here -- dead path; remove the
  lineage special-casing in the port. **[LIVE]** (`char_poe1.json` has 6 skill groups
  with 6/2/2/2/4/1 gems.)

---

## 7. Flasks and jewels **[LIVE]**

**Flasks** (`flasks[]`): wrapper `{itemData, itemSlot}`; `itemData` is a full item with
the same keys as gear PLUS `descrText`. The flask's effect line is in **`utilityMods`**
(e.g. `"30% increased Rarity of Items found"`) and its affixes in `explicitMods`
(e.g. `"+60 to Maximum Charges"`, `"41% increased Charges per use"`). The parent's
mod-bucket list (`explicitMods/craftedMods/desecratedMods/fracturedMods/enchantMods`)
does NOT include `utilityMods`, so a unique/enchanted flask's defining line would be
invisible to the pricer -- **add `utilityMods` to the flask mod buckets** (and drop
the PoE2-only `desecratedMods`). **[LIVE]**

**Jewels** (`jewels[]`): wrapper `{itemData, itemSlot}` (itemSlot 12); `itemData`
has `inventoryId:"PassiveJewels"`, a real `frameType` (2=rare here) and normal
`explicitMods` -- priced by mods exactly like gear. The passive-tree socket the jewel
sits in is `itemData.x` (e.g. `20`) with `y`. **[LIVE]** (The front-end pairs jewels
to tree nodes via `itemData.x` -> `jewelSlots[x]`. **[JS]**) Cluster jewels also appear
under the top-level `clusterJewels` dict keyed by node id. Pricing only needs the mods,
so `x` is informational.

---

## 8. Account `#` encoding **[LIVE] + [JS]**

The `/character` API accepts **only** the dash form:
- `account=example-0416` -> **200** (valid JSON). **[LIVE]**
- `account=example#0416` (sent as `%23`) -> **404**. **[LIVE]**

poe.ninja's own encoder (front-end, function `T`/`Pe` in `a.CePSw7YT.mjs`) is: walk
the string from the end; skip trailing chars matching `/\d/`; if the char before them
is `#`, replace that single `#` with `-`; otherwise leave the string unchanged. **[JS]**
i.e. only the final `#<digits>` discriminator is converted. Port equivalent (already
implemented in `research/probe_ninja.py::dash_account`):
```python
def dash_account(a):
    for i in range(len(a) - 1, -1, -1):
        if a[i].isdigit():
            continue
        return a[:i] + "-" + a[i+1:] if a[i] == "#" else a
    return a
```
Because the pasted poe.ninja URL already contains the dash form, the parent's
`unquote(parts[bi+3])` normally yields the correct value; run it through this encoder
anyway to be safe against hand-typed `#`. The character JSON echoes `account` back in
dash form -- if you want to render a "real" account name or link to the GGG profile,
note the front-end builds `https://www.pathofexile.com/account/view-profile/{account}/
characters?characterName={name}` from the returned (dash) account. **[JS]**

---

## 9. PoB export **[LIVE]**

`pathOfBuildingExport` is present and is the **same envelope as PoE2**: URL-safe
base64 of a zlib stream. Decoding (`zlib.decompress(base64.b64decode(s.replace('-','+')
.replace('_','/')))`) yields standard Path of Building XML:
```
<?xml version="1.0" encoding="UTF-8"?>
<PathOfBuilding>
  <Build level="100" ...>
```
(52693 bytes for the example.) The only PoE1/PoE2 difference is downstream: PoE1 uses
the `pob://` URI scheme and PoB Community; PoE2 uses `pob2://`. The decode path in the
parent's `bpc/pob.py` should work unchanged; verify it handles URL-safe base64. **[LIVE]**

---

## 10. DIFF TABLE - PoE2 parent `poeninja.py` vs PoE1 live

Legend: **SAME** (no change) · **RENAMED/MOVED** · **GONE** (PoE2-only, absent in PoE1)
· **NEW** (PoE1-only, must handle or safely ignore).

### Endpoints / flow
| Parent (PoE2) | PoE1 | Status |
|---|---|---|
| `…/poe2/api/data/index-state` | `…/poe1/api/data/index-state` | RENAMED (prefix) - same shape |
| `…/poe2/api/builds/{ver}/character?account&name&overview&timeMachine` | `…/poe1/api/builds/{ver}/character?…` | RENAMED (prefix) - same params, still **JSON** |
| `parse_build_url` requires `poe2` in path | require `poe1` | must flip guard |
| account passed through from URL | must be **dash form**; API 404s on `#` | NEW constraint |
| overview = snapshotName | same, but slug!=snapshotName for 96/106 | SAME logic, now actually diverges |

### index-state fields
| Parent reads | PoE1 | Status |
|---|---|---|
| `snapshotVersions[].url/.version/.snapshotName/.name` | present | SAME |
| (n/a) | `type` (exp/depthsolo), `timeMachineLabels`, `overviewType`, `passiveTree`, `atlasTree` | NEW; **2 rows per url** (pick `type=="exp"`) |
| `buildLeagues[].name/.url` | present | SAME (+ NEW `displayName`) |

### Character top-level
| Parent reads | PoE1 | Status |
|---|---|---|
| `account,name,class,level,pathOfBuildingExport,league` | all present | SAME (account is dash form) |
| `items[]`, `flasks[]`, `jewels[]`, `skills[]` | present | SAME containers |
| (ignored) | `keyStones,masteries,runegrafts,tattoos,clusterJewels,itemProvidedGems,defensiveStats,banditChoice,pantheon*,ascendancy*,baseClass,passiveSelection,hashesEx,breakdowns,economy,…` | NEW (safe to ignore) |

### Item wrapper + itemData
| Parent reads | PoE1 | Status |
|---|---|---|
| wrapper `{itemData}` | `{itemData, itemSlot}` | NEW `itemSlot` (redundant; keep using `inventoryId`) |
| `inventoryId` (slot) | present (string) | SAME (+ Weapon2/Offhand2/PassiveJewels) |
| `frameType,name,baseType,typeLine,icon,ilvl,corrupted,support` | present | SAME |
| `properties[]` `{name,values,displayMode,type}` | present | SAME (defence names, gem `Level` all match) |
| `explicitMods,implicitMods,craftedMods,fracturedMods,enchantMods` | present | SAME |
| `mods.explicit` `[{id,stats}]` | present | SAME |
| `runeMods` | absent | GONE (PoE2-only) |
| `desecratedMods` | absent | GONE (PoE2-only) |
| `socketedItems` treated as runes (frameType 5) | socketedItems are **gems** (frameType 4) | CHANGED - delete rune extraction; gems come via `skills[]` |
| (n/a) | **`sockets[] {group,attr,sColour}`** | NEW - LINKS; max-link = largest group. **Add to model + pricing.** |
| (n/a) | `utilityMods` (flasks), `crucibleMods,scourgeMods,mutatedMods` | NEW mod buckets (add `utilityMods` for flasks) |
| (n/a) | `requirements,additionalProperties,rarity,frameTypeId,id,w,h,x,y,identified,verified,replica,synthesised,fractured,…` | NEW (mostly ignorable) |

### Gems / skills
| Parent behaviour | PoE1 | Status |
|---|---|---|
| `skills[].allGems`, [0]=active, rest=supports | identical | SAME |
| gem name via `baseType`/`typeLine`, level via `Level` prop | works | SAME |
| `_is_lineage` (LineageSupports) special-casing | no lineage gems in PoE1 | GONE (dead path - remove) |
| (n/a) | `skills[].itemSlot`, `skills[].dps` | NEW (lets you tie a skill to its host item's links) |

---

## 11. Port action checklist (derived from the diff)

1. Swap every `/poe2/` -> `/poe1/`; update `INDEX_STATE` and the character URL builder.
2. `parse_build_url`: require `poe1` (not `poe2`); keep the anchor-on-`builds`
   positional parse; run the account through the `#`->`-` encoder.
3. `resolve_snapshot`: pick the `type=="exp"` snapshotVersion for a slug (2 exist);
   keep using `snapshotName` for `overview` (now genuinely != slug).
4. Add **sockets/links** to the `Item` model: `sockets` (list of `{group,attr,sColour}`),
   `max_link` (largest group), and a colour list; wire into links pricing.
5. Delete PoE2-only paths per clean-cutover: rune extraction from `socketedItems`
   (frameType 5), `runeMods`/`desecratedMods` buckets, and `_is_lineage`/lineage pricing.
6. Add `utilityMods` to the flask mod buckets (drop `desecratedMods`).
7. Keep gem pricing via `skills[]` only (gems also live in `socketedItems`; don't
   double count).
8. `pathOfBuildingExport` + `bpc/pob.py`: confirm URL-safe base64 handling; format is
   otherwise the standard PoB XML envelope.
9. Handle non-ASCII account/character names end-to-end (see `char_poe1_unicode.json`).

---

## 12. Appendix - `/search` protobuf (context only; port does NOT need it)

`GET https://poe.ninja/poe1/api/builds/{version}/search?overview={snapshotName}` returns
`application/x-protobuf` (~65 KB). **[LIVE]** It is a faceted-search payload, not a plain
list. Structure (reverse-engineered by generic wire-parsing) **[LIVE]**:
- Everything is wrapped in field **1**.
- `1.1` = total build count (e.g. 101019).
- `1.2` = repeated dimension histograms: `{key(1), key(2), repeated {valueId(1),count(2)}(3)}`
  for `class, secondascendancy, weaponmode, bandit, items, skills, skillmodes,
  keypassives, anointed, atlasskills, masteries, runegrafts, tattoos, shrinebeltbuffs,
  allgems, pantheon`.
- `1.5` = the **columnar result table**: repeated `Column{ key(1)=string,
  values(2)=repeated {1:string} }`. Columns (all length 100, aligned by row index):
  `name, account, class, skills, keypassives, level, life, energyshield, ehp, dps`.
  Zip the `name` and `account` columns to get real (char, dash-account) pairs.
- Other fields are dimension metadata / column display defs / float histograms.

`research/probe_ninja.py` includes a minimal decoder that extracts the `name`+`account`
columns so the probe can auto-pick a live character to fetch. Because it is protobuf,
naive ASCII string-scraping mis-pairs rows whenever a name/account contains multi-byte
UTF-8 (e.g. Cyrillic) -- decode the columns structurally, as the probe does.
