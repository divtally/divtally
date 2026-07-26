# poe.ninja PoE1 economy API - currency rates + gem prices

Live reverse-engineering notes for porting `bpc/currency.py` and the gem-pricing part of
`bpc/pricing.py` from the PoE2 parent to PoE1.

- **Probed live:** 2026-07-26, league **Allflame** (current challenge league).
- **Probe script:** `research/probe_econ.py` (poe.ninja only; never touches pathofexile.com trade).
- **Raw dumps:** `research/data/ninja_econ_index_state.json`, `..._currency.json`,
  `..._skillgem.json` (full 5660-line gem dump, 4.6 MB), `..._skillgem_sample.json` (readable).
- Everything below marked plainly: **[OBSERVED]** = read from a live response in the dumps;
  **[INFERRED]** = my proposed rule / reasoning, not a fact stated by the API.

---

## 0. Headline finding: the classic PoE1 endpoints are GONE

The old, widely-documented PoE1 endpoints **return HTTP 404 "not found"** as of 2026-07:

- ~~`https://poe.ninja/api/data/currencyoverview?league=X&type=Currency`~~ -> 404 **[OBSERVED]**
- ~~`https://poe.ninja/api/data/itemoverview?league=X&type=SkillGem`~~ -> 404 **[OBSERVED]**

poe.ninja **unified PoE1 and PoE2 under the same new `/<game>/api/economy/...` structure.**
This is the single most important porting fact: the PoE1 economy now uses **the same response
shape** the parent already coded against for PoE2 (`core` / `lines` / `items`), just with a
`/poe1/` prefix and a different set of `type` categories. The parent's `PoeNinjaEconomy` class
(`bpc/poeninja.py`) is ~90% reusable for **currency**; **gems** need a second endpoint and a
new matching layer (below).

Endpoint discovery method (recorded so it can be repeated when a league rolls): the economy page
is an Astro-islands SPA; the item-overview component is `Poe1ItemOverviewPage` in
`https://assets.poe.ninja/_astro/a2.AMB5Xu_u.mjs`, whose imported chunks contain the literal path
templates `GET /poe1/api/economy/exchange/{version}/overview` and
`GET /poe1/api/economy/stash/{version}/item/overview`. `{version}` accepts the literal string
`current` **[OBSERVED]** (or a snapshot version id from index-state).

---

## 1. Verified endpoints

All GET, no auth, JSON. Send a real browser `User-Agent` (+ `Referer: https://poe.ninja/poe1/economy`
is polite; not required). Politely rate-limited by us; poe.ninja is cheap vs the trade API.

### 1a. League discovery
```
GET https://poe.ninja/poe1/api/data/index-state
```
`economyLeagues: [{name, url, displayName}]` -> **[OBSERVED]** `Allflame`, `Hardcore Allflame`,
`Standard`, `Hardcore`. Pick the first non-Standard/Hardcore entry as "current challenge league",
or match the build's league. The **`name`** field ("Allflame") is what every overview call wants
in `?league=`; the **`url`** slug ("allflame") is for building web links. `snapshotVersions[]`
carries `{url, version, snapshotName}` if a pinned (non-`current`) snapshot is ever needed.

### 1b. Currency + stackable "exchange" categories  (feeds `currency.py`)
```
GET https://poe.ninja/poe1/api/economy/exchange/current/overview?league=<Name>&type=Currency
```
`type` values that return data on this endpoint **[OBSERVED]**: `Currency` (102 lines),
`Fragment` (71), `Essence` (104), `Scarab` (115), `DivinationCard` (383), `Oil` (16), `Fossil` (25),
`Resonator` (4), `DeliriumOrb` (12), `Omen` (12), `Tattoo` (50), `Artifact` (4). These are the
bulk/stackable "priced as one fungible rate" items. `SkillGem`, `UniqueJewel`, `Unique*`,
`ClusterJewel`, `BaseType` return `200` with **0 lines** here - they are NOT exchange items.

### 1c. Gems + variant-bearing "item" categories  (feeds gem pricing in `pricing.py`)
```
GET https://poe.ninja/poe1/api/economy/stash/current/item/overview?league=<Name>&type=SkillGem
```
`type` values that return data **[OBSERVED]**: `SkillGem` (5660 lines), `UniqueJewel` (151),
`ClusterJewel` (850), `UniqueWeapon` (533), `UniqueArmour` (833), `UniqueAccessory` (344),
`UniqueFlask` (39), `BaseType` (10831). These are the items whose price depends on a **variant**
(gem level/quality/corruption; unique roll tier; base ilvl+influence). Response top-level is just
`{"lines": [...]}` - **no `core`/`items`/`rates`** wrapper (unlike the exchange endpoint).

---

## 2. Currency shape + conversion rule (port target: `currency.py`)

`type=Currency` response (`research/data/ninja_econ_currency.json`):

```jsonc
{
  "core": {
    "primary": "chaos",              // PoE1 base unit  [OBSERVED]
    "secondary": "divine",           // the "display" unit  [OBSERVED]
    "rates": { "divine": 0.009761 }, // divine PER chaos  [OBSERVED]
    "items": [ {"id":"chaos","name":"Chaos Orb",...}, {"id":"divine",...} ]
  },
  "items": [ {"id":"divine","name":"Divine Orb","image":"/gen/...","category":"Currency",
              "detailsId":"divine-orb"}, ... ],   // id -> name/image for all 102 currencies
  "lines": [ {"id":"divine","primaryValue":102.5,"volumePrimaryValue":..,
              "maxVolumeCurrency":"chaos","maxVolumeRate":..,"sparkline":{...}}, ... ]
}
```

**The rule (differs fundamentally from the parent):**
- **`line.primaryValue` is the price of 1 unit of that currency IN CHAOS, directly.** No
  multiply-by-rate step. Divine Orb = **102.5 chaos**, Exalted = **0.7216 chaos**, Mirror =
  **16787 chaos**, Vaal = 0.5976, Annul = 6.6, Chaos = 1.0 (chaos is in `lines` as a self price of 1).
  **[OBSERVED, Allflame 2026-07-26]**
- **chaos-per-divine (for the Divine display column) = the Divine Orb line's `primaryValue`
  (102.5)**, equivalently `1 / core.rates.divine` = 1/0.009761 = 102.45. **[OBSERVED]** Use the
  Divine line's `primaryValue` as the canonical figure; `core.rates.divine` is the same number
  inverted and is a fine cross-check.
- **`id` = the canonical GGG currency id** ("divine", "exalted", "chaos", "mirror", "annul",
  "vaal", "regal", "fusing"...). Trade listing prices report `price.currency` as these same ids,
  so `rate(id) = line.primaryValue` maps a listing directly to chaos. **[INFERRED]** - the id
  alignment between poe.ninja and the trade static currency list should be spot-checked against
  the trade agent's `data/static` dump for the handful of currencies builds are actually quoted
  in (divine/chaos/exalted/mirror/annul); a couple of niche ids (e.g. `chromatic`, `alchemy`)
  were absent from the Currency `lines` under these exact ids **[OBSERVED]** and would fall back
  to "unpriceable".

**Design consequence:** the port can build the whole currency-conversion table from **one
poe.ninja GET** and skip the trade `exchange` endpoint entirely - eliminating the ban-risk the
parent carried (its `CurrencyConverter._lookup` hit `client.exchange()`). Recommended port:
`CurrencyConverter` becomes a thin reader over `PoeNinjaEconomy` Currency lines, canonical unit =
**chaos** (`_BASE = "chaos"`, `rate("chaos") = 1.0`), with a `divine_rate()` that returns the
Divine line's `primaryValue` for the "N chaos (M div)" formatter. Keep a trade-exchange fallback
only for a currency id poe.ninja doesn't list. **[INFERRED - recommended design]**

---

## 3. Gem shape + matching rule (port target: gem pricing in `pricing.py`)

`type=SkillGem` line schema (`research/data/ninja_econ_skillgem.json`, 5660 lines; readable
subset in `..._skillgem_sample.json`). **[OBSERVED]** keys:

```jsonc
{
  "id": 3227,
  "name": "Increased Critical Damage Support",  // EXACT gem name (see variants below)
  "icon": "https://web.poecdn.com/gen/image/...",
  "levelRequired": 72,
  "variant": "21/20c",         // the bucket string: "<level>[/<quality>][c]"  (c = corrupted)
  "itemClass": 4,              // 4 for every gem line in the dump (active AND support)  [OBSERVED]
  "corrupted": true,           // bool
  "gemLevel": 21,              // int  (authoritative; also encoded in `variant`)
  "gemQuality": 20,            // int  (ABSENT when quality is 0)
  "chaosValue": 9225,          // price in CHAOS  <- canonical
  "exaltedValue": 12784,       // price in exalted
  "divineValue": 90.0,         // price in divine (absent on ~34 cheapest lines)
  "count": 1, "listingCount": 1, // sample support (see confidence)
  "detailsId": "increased-critical-damage-support-21-20c"
}
```

### 3a. The `variant` bucket string  **[OBSERVED]**
`variant` encodes level/quality/corruption compactly:
`"<level>"` or `"<level>/<quality>"`, with a trailing `"c"` when corrupted.
Observed variant frequency across all 5660 lines (top): `1` (729), `1/20` (673), `21/20c` (624),
`20/20` (604), `20` (590), `21c` (555), `1/23c` (467), `20/23c` (460), `20/20c` (402), `20c` (312),
`21/23c` (130), `1c` (71), plus sparse `2/3/4/5` levels for awakened/special gems.

**The discrete buckets that actually exist per normal gem:** levels **{1, 20, 21}**, qualities
**{0, 20, 23}**, corrupted **{false, true}** - but not the full cross-product. Level 21 and
quality 23 appear **only** on corrupted lines (`21c`, `21/20c`, `20/23c`, `1/23c`, `21/23c`) -
which is correct game behaviour: 21/23 come from corruption. `gemQuality` is simply omitted for
0-quality buckets; treat missing as 0. **[OBSERVED]**

### 3b. How the special gem categories appear **[OBSERVED - verified in dump]**
- **Awakened gems**: only the 3 that exist - `Awakened Empower/Enlighten/Enhance Support` - as
  their own `name`s, with sparse buckets (level 1..5; `5c` = corrupted max). Very expensive
  (Awakened Enhance `1` = 512c, `5c` = 15375c). No "Awakened <damage>" here in Allflame data
  (those exist in the game but simply weren't listed this snapshot).
- **Transfigured gems**: appear as **separate `name`s** using the "`<Skill> of <Suffix>`" pattern -
  262 such names **[OBSERVED]** (e.g. `Arc of Oscillating`, `Arc of Surging`, `Ball Lightning of
  Orbiting`, `Absolution of Inspiring`). They are NOT a variant of the base skill; matching by
  exact `name` handles them for free. The PoB/poe.ninja character item will carry the transfigured
  name in its `typeLine`/`baseType`, so no special logic is needed beyond exact-name lookup.
- **Alternate-quality gems (Anomalous / Divergent / Phantasmal)**: **ZERO lines** in the 2026
  Allflame data **[OBSERVED]**. This category was removed from PoE1 (folded away in 3.24); the
  variant string has no alt-quality prefix and no `name` contains those words. **The port must NOT
  implement alt-quality gem variants** - they don't exist in current data. (Historical PoE1 dumps
  had a `Vaal`/alt-quality dimension; gone now.)
- **Vaal skill gems** (e.g. "Vaal Arc") exist as their own `name`s where applicable, same as any
  other distinct gem name. **[INFERRED]** - not separately spot-checked, but consistent with the
  "each distinct gem is its own name" structure.

### 3c. Matching rule the port should implement  **[INFERRED - proposed, grounded in 3a/3b]**
Given a character's socketed gem `(name, level, quality, corrupted)`:
1. **Filter lines by exact `name`** (case-insensitive). Transfigured/awakened/Vaal names match
   directly; a support gem's name includes the "Support" suffix, matching the line's `name`.
2. Among that name's lines, **pick the bucket nearest to the character's actual gem**, in priority
   order: (a) exact `corrupted` match, then (b) nearest `gemLevel`, then (c) nearest `gemQuality`.
   Because buckets are coarse (levels {1,20,21}, qual {0,20,23}), a real level-19/q17 gem should
   snap to `20/20`; a level-21 corrupted 20-quality gem to `21/20c`. A simple scoring metric
   (`abs(dL) + 0.3*abs(dQ) + big_penalty_if_corrupted_mismatch`) reproduces this.
3. Use **`chaosValue`** as the canonical price (already chaos); derive divine via the Divine rate
   from section 2 (or the line's own `divineValue`). This IS the finished/cut gem price - PoE1
   gems are traded as leveled cut gems, so unlike PoE2 there's **no uncut-gem + jeweller-orb
   synthesis**. One name+bucket lookup = one real market price.
4. **Support gems are priced the same way** (they're in the same list) - PoE1 has no free-vs-uncut
   distinction. A build's total gem cost = sum over every socketed gem of its matched-bucket price.
   (Contrast the parent, which priced only active skills + lineage supports.)

### 3d. Which gems are worth pricing vs noise (floor)  **[INFERRED - proposed default]**
Price distribution across all lines **[OBSERVED]**: min 0.05c, p10 1c, **median 6c**, p90 99c,
max 15375c; **44% of lines < 5c, 69% < 20c**. Level-1 / 0-quality buckets are ~1c filler.
- A build's *actual* gems are almost always the **`20/20`** (level 20 / 20% quality, uncorrupted)
  or **`21/20c`** (corrupted "perfect") buckets, which are the priced ones (e.g. Determination
  `21/20c` = 117c, Arc `21/20c` = 45c). So matching to the character's real level/quality
  naturally lands on the meaningful price.
- **Proposed floor for display noise (not exclusion):** still sum every gem into the total, but
  only surface a gem as its own line-item when its matched price **>= ~5 chaos (~0.05 div)**;
  lump anything below into a single "misc gems" figure. This keeps a 40-gem build from rendering
  40 rows of 1c filler. Tune the 5c number against the report's other floors. **[INFERRED]**
- **Confidence:** each line carries `listingCount` (how many were sampled for that bucket).
  Buckets with `listingCount` >= ~5 are reliable; `1-2` are thin. Map to the report's
  high/medium/low confidence the way the parent maps sample size. **[INFERRED]**

---

## 4. Diff vs the parent (PoE2) gem/currency model

| Aspect | Parent PoE2 (`bpc/poeninja.py`, `currency.py`, `pricing.py`) | PoE1 (this research) |
|---|---|---|
| Economy base endpoint | `/poe2/api/economy/exchange/current/overview` | `/poe1/api/economy/exchange/current/overview` (currency) **+** `/poe1/api/economy/stash/current/item/overview` (gems/items) - **two endpoints** [OBSERVED] |
| Canonical unit | Exalted (`_BASE="exalted"`); `core.rates.exalted` = ex-per-divine; `primaryValue` in **divine** | **Chaos** (`core.primary="chaos"`); `primaryValue` already in **chaos**; `core.rates.divine` = div-per-chaos [OBSERVED] |
| Currency source | trade `exchange` API (ban risk) in `CurrencyConverter._lookup` | can come entirely from poe.ninja Currency `lines` -> **no trade calls** [INFERRED design] |
| Gem model | uncut gem + Jeweller's Orbs synthesis; poe.ninja `UncutGems`/`LineageSupportGems` categories; only active skills + lineage supports priced | **cut gems priced directly** by name + level/quality/corruption bucket via `SkillGem` item overview; **every** socketed gem (active + support) has a real market price; no orb synthesis [OBSERVED] |
| Gem response shape | `core`+`lines`+`items`; price = `primaryValue * core.rates.exalted` | item overview = `{lines:[...]}` only; price = `chaosValue` (per-line, direct) [OBSERVED] |
| Gem variants | uncut level only | `variant` string `"<lvl>[/<qual>][c]"`; buckets lvl{1,20,21} x qual{0,20,23} x corrupt [OBSERVED] |
| Awakened gems | n/a (PoE2 has none) | 3 support awakened as own names, sparse buckets [OBSERVED] |
| Transfigured gems | n/a | separate `name`s ("`Skill of Suffix`"), 262 in data; matched by exact name [OBSERVED] |
| Alt-quality gems | n/a | **do not exist in current PoE1 data** - do not implement [OBSERVED] |
| Runes / Soul Cores | priced from exchange (`Runes`/`SoulCores`/`Idols`) | **not present in PoE1** (PoE2-only mechanic) - drop `price_rune`; the exchange endpoint instead offers Fragment/Essence/Scarab/Oil/etc. as future fallback categories [OBSERVED] |

### Concrete port edits implied
- `currency.py`: `_BASE = "chaos"`; source rates from `PoeNinjaEconomy` Currency lines
  (`rate(id) = primaryValue`), not `client.exchange`; `divine_rate()` = Divine line `primaryValue`;
  `fmt()` renders "N chaos (M div)".
- `poeninja.py` `PoeNinjaEconomy`: base URL `/poe1/...`; add a second fetch for the
  `stash/current/item/overview` endpoint whose lines are `{name, variant, gemLevel, gemQuality,
  corrupted, chaosValue, divineValue, listingCount}` (no `core`/rate multiply).
- `pricing.py`: replace `price_skill` (uncut synthesis) + `price_gems_aggregate` +
  `_socket_orb_cost` + `_price_lineage` + `_max_uncut_id` with a single **name+bucket lookup**
  against the SkillGem overview; delete `price_rune` / rune categories. Gem total = sum of every
  socketed gem's matched `chaosValue`.

---

## 5. Open items / risks for the port
- **id alignment** (poe.ninja currency `id` vs trade `price.currency`) needs a spot-check against
  the trade agent's static currency dump for the currencies builds are quoted in. **[INFERRED]**
- **League rollover:** `current` in the path is a live alias; when Allflame ends, index-state's
  `economyLeagues` changes - the port must resolve the build's league name dynamically (already the
  pattern). Standard/Hardcore are always present.
- **Gem name normalisation:** the character JSON's gem `typeLine`/`baseType` must equal the
  overview `name` exactly (including "Support" suffix and transfigured "of ..." names). Verify the
  PoE1 poeninja normaliser produces matching strings when that port lands. **[INFERRED]**
- **Thin buckets:** some exact buckets have `listingCount` 1-2 (e.g. a `20/20` uncorrupted showing
  a volatile 82c for Spark vs 3c for the `20` bucket) - reflect that in confidence, and consider
  falling back to a neighbouring bucket when the exact one is a single noisy listing. **[INFERRED]**
