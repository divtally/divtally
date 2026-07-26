# PoE1 Path of Building import-code format (porting `bpc/pob.py`)

Reverse-engineered 2026-07-26 from a **live PoE1 PoB export** and the parent PoB2 parser.

- **Sample XML:** `research/data/pob_sample.xml` (52,693 chars). Char: `example-0416 / TestCharacter`, Elementalist lvl 100, Allflame (3.29) league.
- **Regenerate:** `python research/probe_pob.py` (decodes `research/data/char_poe1.json` if
  present, else does the live poe.ninja PoE1 flow below).
- **Parent parser under study:** `C:\scripts\buildpricechecker\bpc\pob.py` (PoB2/PoE2), read read-only.

Everything below is **source-derived** (from the decoded XML, the live poe.ninja API, or the
parent code) unless tagged **[INFERRED]** / **[NOT FROM SOURCE]**.

---

## 1. Where to get a PoE1 PoB code

### 1a. poe.ninja PoE1 character API (verified live 2026-07-26)
PoE1 mirrors the PoE2 site under a **`/poe1/`** prefix (canonical page host: `poe.ninja/poe1/builds/`).
The endpoints the site's JS (`assets.poe.ninja/_astro/*.mjs`) calls:

| Step | Request | Returns |
|---|---|---|
| 1 | `GET https://poe.ninja/poe1/api/data/index-state` | JSON: `economyLeagues`, `snapshotVersions[]` (`url`,`type`,`name`,`version`,`snapshotName`,`overviewType`,`passiveTree`), `buildLeagues` |
| 2 | `GET https://poe.ninja/poe1/api/builds/<version>/search?overview=<snapshotName>&type=exp` | **`application/x-protobuf`** columnar table of ranked chars; columns include `name`, `account` (+ `class`,`skills`,`level`,`ehp`,`dps`...) |
| 3 | `GET https://poe.ninja/poe1/api/builds/<version>/character?account=<acc>&name=<char>&overview=<snapshotName>&type=exp` | **JSON** character; key **`pathOfBuildingExport`** (plus `items`,`skills`,`flasks`,`jewels`, stats) |

- `type=exp` = the experience/level ladder (the default "exp" snapshot). `version` looks like
  `2019-20260726-01354`; `snapshotName` for current league = `allflame`.
- The `/character` endpoint validates that **`account` + `name` are required** (400 otherwise) and
  404s if the pair is wrong — so account/name must be **row-aligned** from the `/search` protobuf.
  `research/probe_pob.py` parses that protobuf minimally (no schema) to recover aligned pairs.
- **Auth:** none. No POESESSID, no pathofexile.com calls. Politeness: single-shot GETs, real UA.
- **[INFERRED]** The old PoE1 endpoints (`/api/data/getbuildoverview`, `/api/data/index-state`
  with no `/poe1/`) are gone — all returned 404 in testing. Only the `/poe1/`-prefixed ones work.

### 1b. Paste-link services (from parent `bpc/engine.py`, source-verified — host-based, game-agnostic)
The parent already fetches raw PoB codes from an allowlist; these hosts serve **PoE1 and PoE2
codes identically** (they store whatever code was uploaded — a PoE1 code decodes to
`<PathOfBuilding>`), so the fetch layer needs **no change** for PoE1:

- Allowlist hosts (`_POB_LINK_HOSTS`): `pobb.in`, `pastebin.com`, `poe.ninja`, `poe2.ninja`.
- Raw-URL candidates (`_pob_raw_candidates`), most-specific first:
  - `pobb.in`   -> `https://pobb.in<path>/raw`
  - `pastebin.com` -> `https://pastebin.com/raw/<last-path-segment>`
  - generic fallback -> `<url>/raw`, then `<url>`
- Validated by `pob.looks_like_code()` = decodes and contains `<PathOfBuilding` in the first 200
  chars. **This substring check already matches PoE1** (`<PathOfBuilding>`), so it works as-is.
- **[INFERRED]** For a PoE1 tool, drop/keep `poe2.ninja` and add `poe.ninja/poe1/...` handling in
  `engine.prepare_auto`; the `pobb.in`/`pastebin` raw patterns need no change.

---

## 2. Decode envelope (identical to PoB2)

PoB code = optional `pob://` prefix -> whitespace-stripped -> **URL-safe base64** (std base64
fallback) -> **zlib decompress** -> UTF-8 XML. The parent `pob.decode()` works on PoE1 codes
unchanged (the live sample decoded via `urlsafe_b64decode` + `zlib`).

**Discriminators PoE1 vs PoE2:**
| | PoE1 | PoE2 |
|---|---|---|
| Root element | `<PathOfBuilding>` | `<PathOfBuilding2>` |
| `Build/@targetVersion` | `"3_0"` | (absent / different) |

The parent's guard `if "PathOfBuilding" not in root.tag` **passes for both** (substring match), so
root detection needs no change.

---

## 3. XML structure (from the live sample)

### 3.1 `<Build>` (attributes)
```
<Build level="100" targetVersion="3_0" pantheonMajorGod="Lunaris" bandit="Alira"
       className="Witch" ascendClassName="Elementalist" characterLevelAutoMode="false"
       mainSocketGroup="4" viewMode="TREE" pantheonMinorGod="Ralakesh">
```
- Parent reads `ascendClassName` / `className` / `level` — **all present, works unchanged.**
- PoE1-only attrs (ignored by the pricer, noted for completeness): `bandit`,
  `pantheonMajorGod`, `pantheonMinorGod`, `targetVersion`. **No** `Spirit` anywhere (PoE2-only).

### 3.2 `<Items>` / `<ItemSet>` / `<Slot>`
```
<Items activeItemSet="1" showStatDifferences="true" useSecondWeaponSet="nil">
  <Item id="1"> ... </Item>
  ...
  <ItemSet useSecondWeaponSet="nil" id="1">
    <Slot itemPbURL="" name="Weapon 1" itemId="31"/>
    <Slot itemPbURL="" active="true" name="Flask 5" itemId="28"/>
    <Slot itemPbURL="" name="Helmet Abyssal Socket 1" itemId="0"/>
    <Slot itemPbURL="" name="Graft 1" itemId="0"/>
    ...
```
- `Items/@activeItemSet`, `ItemSet/@id`, `Slot/@itemId`, `Slot/@name` — **all present, parent logic
  works.** (`Slot` also carries `itemPbURL` and an `active="true"` flag on filled flask slots; both
  harmless/ignored.)
- **Equipped equipment/flask slot names (verified) all match the parent `_SLOT_MAP` exactly:**
  `Weapon 1`, `Weapon 1 Swap`, `Weapon 2 Swap`, `Body Armour`, `Helmet`, `Gloves`, `Boots`,
  `Belt`, `Amulet`, `Ring 1`, `Ring 2`, `Flask 1`..`Flask 5`.
- **PoE1-only slot families** (present as extra `<Slot>` rows, mostly `itemId="0"` empty here):
  - `"<Base> Abyssal Socket <1..6>"` (e.g. `Belt Abyssal Socket 2`, `Weapon 1 Abyssal Socket 5`)
    — hold **Abyss jewels**. Not in `_SLOT_MAP`.
  - `"Graft <N>"` — rune-graft slots (3.26+). Not in `_SLOT_MAP`.
  - `"Ring 3"` slot exists (empty here). Parent already maps `Ring 3` -> Ring.
- **No `Charm <N>` slots** (PoE2-only). Harmless — parent's `Charm` map entries simply never match.

### 3.3 Item text format (inside each `<Item>`)
`el.itertext()` yields the in-game text; child `<ModRange .../>` elements are empty self-closing
and stripped by the parent's `not ln.startswith("<")` filter. Real examples:

**Rare cluster jewel (id 1):**
```
Rarity: RARE
Phoenix Star
Large Cluster Jewel
Unique ID: 5315a49fc168105a...
Item Level: 82
LevelReq: 60
Implicits: 3
{crafted}Adds 8 Passive Skills
{crafted}2 Added Passive Skills are Jewel Sockets
{crafted}Added Small Passive Skills grant: 12% increased Chaos Damage
Added Small Passive Skills also grant: 2% increased Damage
...
```

**Unique armour with sockets/quality/defences (id 23, "The Gull"):**
```
Rarity: UNIQUE
The Gull
Raven Mask
Evasion: 316
EvasionBasePercentile: 0.6665
Energy Shield: 150
EnergyShieldBasePercentile: 0.7042
Unique ID: 90fd67e78f7f...
Item Level: 80
Quality: 20
Sockets: W-R-B-W
LevelReq: 38
Implicits: 0
Trigger Level 1 Create Lesser Shrine when you Kill an Enemy
131% increased Evasion and Energy Shield
...
```

**Unique amulet with catalyst (id 32, "Marylene's Fallacy"):**
```
Rarity: UNIQUE
Marylene&apos;s Fallacy
Lapis Amulet
Unique ID: c61a6268...
Catalyst: Unstable
CatalystQuality: 20
Item Level: 83
LevelReq: 40
Implicits: 2
{crafted}Allocates Force of Darkness
+23 to Intelligence
...
```

Structure rules (same shape as PoB2):
- Line 1 `Rarity: NORMAL|MAGIC|RARE|UNIQUE|RELIC`. RARE/UNIQUE -> line2 = name, line3 = base.
  MAGIC/NORMAL -> single combined type line (parent already handles both).
- Header/property lines (before the mod block): `Unique ID:`, `Item Level:`, `LevelReq:`,
  `Quality:`, `Sockets:`, `Armour:`/`Evasion:`/`Energy Shield:`, `Radius:`, `Limited to:`,
  and **PoE1-only:** `ArmourBasePercentile:`, `EvasionBasePercentile:`,
  `EnergyShieldBasePercentile:`, `Catalyst:`, `CatalystQuality:`.
- `Implicits: N` — first N mod lines are implicits; the rest explicit (same as PoB2).
- `Corrupted` line -> corrupted flag (same). Amp: `&apos;`/`&amp;` XML entities in names (ET decodes).
- Mod tags seen: `{crafted}` (others possible: `{fractured}`, `{enchant}`, `{range:...}`).
  **[INFERRED]** PoB1 can also emit affix-annotated exports (`Prefix: {range}Mod` / `Suffix:` /
  `{tags}` incl. `{fractured}`) when the user enables that export mode; not present in this sample.

### 3.4 Sockets / links notation (PoE1-specific, PoE2 has no colored links)
`Sockets: <group> <group> ...` where each group is socket-color letters joined by `-` (linked);
a **space separates unlinked groups**. Colors: `R` red / `G` green / `B` blue / `W` white /
`A` abyss. Examples from the sample: `Sockets: R-G-W` (a 3-link), `Sockets: W-R-B-W` (a 4-link).
- **[INFERRED]** `A` = abyssal socket, `DV`/`D` = special (delve/tincture) — not present in sample.
- The parent treats `Sockets:` purely as a skip-able header property (link count **not** extracted).
  For PoE1 pricing this is where **6-link / N-socket** value would come from — currently dropped.

### 3.5 `<Skills>` / `<SkillSet>` / `<Skill>` / `<Gem>`  (gems)
```
<Skills sortGemsByDPSField="CombinedDPS" activeSkillSet="1" ...>
  <SkillSet id="1">
    <Skill mainActiveSkill="1" label="On Kill Monster Explosion" enabled="true" source="Explode">
      <Gem ... skillId="EnemyExplode" level="1" quality="0" count="nil" nameSpec="" enabled="true"/>
    </Skill>
    <Skill ...>
      <Gem variantId="SupportEmpower" skillId="SupportEmpower"
           gemId="Metadata/Items/Gems/SupportGemAdditionalLevel"
           level="3" quality="20" count="nil" enabled="true" nameSpec="Empower"/>
      ...
```
- `Skills/@activeSkillSet`, `SkillSet/@id`, `Skill/@source` — present; parent's active-set +
  source-skip logic works (the `source="Explode"` / item-granted skills are correctly skipped).
- **Gem attributes:** `nameSpec` (display name), `skillId`, `gemId`
  (`Metadata/Items/Gems/...`; supports = `SupportGem...`), `level`, `quality`, `enabled`,
  `variantId`, and **`count="nil"`**.
- Support detection: parent's `skillId.lower().startswith("support")` +
  `"supportgem" in gemId.lower()` — **works** (`SupportEmpower` / `SupportGemAdditionalLevel`).

### 3.6 Tree jewels & abyss jewels
- **Passive-tree jewels:** `<Tree><Spec ...><Sockets><Socket nodeId="61834" itemId="12"/></Sockets>`.
  Note attr **`nodeId`** (PoB2 socket may differ) but the **`itemId`** attr is the same. Parent's
  `root.iter("Socket")` collecting `itemId` **works unchanged** (found 19 tree jewels here).
  `<Spec>` also carries `masteryEffects`, `nodes`, `ascendClassId`, `clusterHashFormatVersion`.
- **Abyss jewels:** live in the `"<Base> Abyssal Socket <N>"` **ItemSet slots** (3.2), *not* in
  `<Socket>`. Empty in this sample. Parent would price them via the `base in jewel_types` fallback
  (their bases like `Ghastly Eye Jewel` are in the trade Jewels group) **[INFERRED — unverified;
  depends on `jewel_types` including abyss "Eye Jewel" bases]**. The tree-`Socket` `jewel_ids` set
  does **not** cover them.

---

## 4. Diff table — parent PoB2 parser vs PoE1 reality

Ran the **unmodified** parent `bpc.pob.parse()` on `pob_sample.xml` (empty types dict). Result:
`35 items` parsed (11 equipment, 5 flask, 19 jewel) — **but `gems: []`** and mod pollution. Details:

| Concern | Parent (`bpc/pob.py`) expects (PoB2) | PoE1 actual | Port action |
|---|---|---|---|
| Root tag | `<PathOfBuilding2>` (`"PathOfBuilding" in tag`) | `<PathOfBuilding>` | none (substring match passes) |
| Envelope | base64url+zlib XML | identical | none |
| `Build` class/level | `ascendClassName`/`className`/`level` | identical | none |
| Equipment/flask slots | `_SLOT_MAP` names | **all match** | none |
| Tree jewels | `iter("Socket")` `itemId` | `<Socket nodeId itemId>` (extra `nodeId`) | none |
| **Gems** | filter `(count or "1") in {"nil","0",""}` -> skip | **every gem has `count="nil"`** -> **ALL 32 gems dropped** | **FIX: stop treating `count="nil"` as "not equipped"; gate on `enabled!="false"` and `nameSpec` non-empty (treat `nil`->1)** |
| **Header props** | `_PROP_PREFIXES` list | PoE1 adds `ArmourBasePercentile:` / `EvasionBasePercentile:` / `EnergyShieldBasePercentile:` / `Catalyst:` / `CatalystQuality:` | **FIX: add these prefixes** — else they leak into mods |
| Implicit boundary | `Implicits:N` slice | **shifted** when Catalyst lines precede it | **FIX** (same as above): Marylene's real implicit `Allocates Force of Darkness` was pushed into explicits and `Catalyst:/CatalystQuality:` became the "implicits" |
| Sockets/links | skipped as property | `Sockets: R-G-W` colored links carry 6L/socket value | optional: parse for 6-link pricing (currently dropped) |
| Abyss jewels | n/a (PoE2) | in `"<Base> Abyssal Socket N"` slots | verify `jewel_types` fallback covers them; not in `jewel_ids` |
| Charm slots | `Charm 1..5` in `_SLOT_MAP` | none (PoE2-only) | harmless; can drop |
| Runes / Soul Cores | `Rune:` / `Soul Core:` item lines | none in PoE1 (uses `Graft` slots + `{crafted}` mods) | harmless; PoE1 has no per-item rune lines |

### Confirmed-bug evidence (parent parser, unmodified, on the live PoE1 sample)
1. **Gems dropped:** `gems: []`. All 32 named gems (`Empower`, `Righteous Fire`, `Herald of *`,
   `Ethereal Knives of the Massacre`, ...) have `count="nil"` -> the
   `if (gem.get("count") or "1") in ("nil","0",""): continue` line skips **100%** of them.
2. **`The Gull` explicit_mods** began with `EvasionBasePercentile: 0.6665`,
   `EnergyShieldBasePercentile: 0.7042` (garbage leaked as mods).
3. **`Marylene's Fallacy`** parsed `implicit_mods = ['Catalyst: Unstable', 'CatalystQuality: 20']`
   and its true implicit `Allocates Force of Darkness` fell into explicits — the `Implicits:2`
   boundary was corrupted by the two leaked catalyst lines.

---

## 5. Minimal port checklist for `bpc/pob.py` (PoE1)
1. **Gem filter:** replace the `count`-based skip with `enabled != "false"` + non-empty `nameSpec`
   (PoE1 sets `count="nil"` for normal single gems). Keep `source`-skip and support detection.
2. **`_PROP_PREFIXES`:** add `"ArmourBasePercentile"`, `"EvasionBasePercentile"`,
   `"EnergyShieldBasePercentile"`, `"WardBasePercentile"` **[INFERRED name — Ward not in sample]**,
   `"Catalyst"`, `"CatalystQuality"`. (These have no `:`-adjacent value the defence regex catches.)
3. Root/envelope/slots/tree-jewels/`Build`: **no change needed** (verified).
4. Optional (pricing quality): parse `Sockets:` colored-link groups for 6-link/socket value;
   confirm abyss-jewel bases are in the trade `Jewels` group for the base-type fallback.
5. `engine.prepare_auto`: route `poe.ninja/poe1/...` character links to the PoE1 fetch; `pobb.in` /
   `pastebin` raw patterns are unchanged.
