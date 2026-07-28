# Public API contract — `api/build` (PoE1 Build Price Checker)

**Audience:** the site agent (and the browser extension) building against the public
serverless function. This document is the source of truth for the request/response shapes.
The function lives in `public/api/` (self-contained Vercel Python project); see
`docs/notes-public-api.md` for how it is built and verified.

**Status:** Locked v1.0 (2026-07-26). Verified end-to-end locally against
`research/data` fixtures (offline) and one live poe.ninja PoE1 character (see notes).
**Additive update 2026-07-27 (D-0016):** the default rare/magic search scope is now the item
**category** (generic, e.g. `weapon.wand`) instead of the exact base, with the exact base kept
as a user option; a new `rares[].scopes` field exposes both (§2.5, §2.6.1). Uniques are
unchanged. See `docs/notes-v2-api.md`.

**Additive update 2026-07-27 (D-0019 — variant-unique registry):** variant-defining uniques
(Forbidden Flesh/Flame, Watcher's Eye, timeless jewels, Voices, abyssal-socket uniques,
Impresence, Mageblood, …) are now priced by the **owned variant**, not by name alone. Additive,
back-compatible fields: a per-item **`variant`** block (§2.8); the unique's `trade_query` gains
the **required defining-mod filters** built from the build's own copy (Allocates-option split,
exact timeless seed `min==max`, exact socket/passive count, aura-combo); `rares[].affixes` gain
**`defining`** / **`option`** / **`exact`** (§2.6); and two new `price.method`s
(**`unique-ninja-floor`**, and the existing `unique-ninja-variant` now also covers registry
map-count/-variant/-base matches). Non-registry uniques are unchanged. See
`docs/notes-variant-querybuild.md`.

**Additive/corrective update 2026-07-27 (D-0020 Round 1 bug fixes):** all schema-compatible.
- **Foil/relic uniques** (frameType 9 Relic, 10 SupporterFoil — e.g. Nimis) now route to
  `category:"unique"` and are priced/listed like any unique (were mis-categorised `normal` and
  dropped from pricing + totals).
- **Weapon-swap items** (`swap:true`, Weapon2/Offhand2) are now excluded from `totals` and
  `priced_items` **by default**, matching D-0018 and the site (§2.2, §2.3). They remain in
  `items[]` and `rares{}` so a "weapon swap" toggle can re-include them client-side.
- **Implicit mods** now appear as opt-in `rares[].affixes` rows (`group:"implicit"`; §2.6) so a
  searchable corrupted/base implicit can be added to the search; they are NOT in the default rare
  query (base implicits come with the base). Previously omitted entirely.
- **Link-split uniques**: `unique-ninja-variant` now also selects the poe.ninja line for the
  copy's socket-link tier (5L/6L vs unlinked) when the name is link-split, instead of a vague
  `unique-ninja-range` (§3).
- **Duplicate distinct gems** (e.g. several identical minion gems in one item) are no longer
  collapsed into a single row (only true weapon-swap duplicates, keyed on gem id, still collapse).
- **Bad-URL classification**: a build-overview link, a PoE2 link, and other parse-level URL
  mistakes now return **400 `bad_input`** (per §4), not 502 `ninja_error` (which stays reserved
  for genuine poe.ninja fetch failures).

---

## 0. The hard invariant (read first)

This function **never calls pathofexile.com** — not the trade search/fetch/exchange API,
not the `data/*` reference endpoints. (Enforced structurally: the vendored HTTP layer
blocks the host; the reference data is bundled; trade queries are *built, never executed*.)

Consequences for you, the consumer:

- **Item prices come only from poe.ninja**: gems (active + supports), currency rates, and
  uniques by name. These arrive as real chaos numbers with a confidence.
- **Rares (and magic items, and uniques poe.ninja doesn't list) are NOT priced here.** For
  each, the response carries a ready-to-run **`trade_query`** (the exact JSON body to POST
  to `https://www.pathofexile.com/api/trade/search/<league>`) **and** a clickable
  **`trade_url`** (the same query as a `?q=` browser link). Pricing them happens on the
  **user's** machine — the browser link (Rung 1) or the extension bridge (Rung 2). This is
  the whole point of B-001: *users are the scanners*.

---

## 1. Endpoints

### `POST /api/build`  (preferred for the site)
Body: JSON object. The build input may be under any of
`input` / `url` / `build` / `pob` / `code` / `text` (first non-empty wins).

```jsonc
{
  "input": "https://poe.ninja/poe1/builds/<league>/character/<account>/<char>",
  "league": "Standard",     // OPTIONAL trade-league override (see §5)
  "status": "online"        // OPTIONAL listing status: online|any|onlineleague|available|securable
}
```

### `GET /api/build?url=<...>&league=<...>&status=<...>`
Same semantics via query string (`url` or `input` accepted). Handy for testing / links.

### `GET /api/health`
Offline readiness probe (never hits the network). Returns:
```jsonc
{ "ok": true, "service": "bpc-public-api", "schema_version": "1.0",
  "calls_pathofexile_com": false,
  "refdata": { "stat_groups": 9, "stat_patterns": 8077, "base_types": 3952 },
  "ts": 1785122891 }
```

### `OPTIONS` (any) — CORS preflight, returns 204 with the CORS headers.

**Accepted inputs** (auto-detected): a poe.ninja PoE1 **character** URL; a **Path of
Building** import code (the base64 blob); or a **PoB paste link** on `pobb.in`,
`pastebin.com`, or `poe.ninja/pob/...`. A poe.ninja *build-overview* link (no `/character/`)
is rejected with guidance.

---

## 2. Response — the ONE document (success, HTTP 200)

Top-level keys: `ok`, `schema_version`, `meta`, `totals`, `items`, `rares`, `warnings`.

### 2.1 `meta`
| field | type | notes |
|---|---|---|
| `character` | string | character name (poe.ninja) or `"Path of Building import"` |
| `account` | string | poe.ninja account (dash-encoded); `""` for PoB |
| `class` | string | ascendancy/class |
| `level` | int | |
| `league` | string | **the trade league used in every `trade_url`/`trade_query`** |
| `ninja_league` | string | the poe.ninja league display name (usually == `league`) |
| `source` | `"poe.ninja"` \| `"pob"` | which input path produced the build |
| `source_url` | string | the poe.ninja URL, or `"(Path of Building import)"` |
| `pob_code` | string | the build's PoB export code if poe.ninja provided one (else `""`) |
| `cache_key` | string | `poeninja:char:<version>:<account>:<char>` (stable per snapshot) or `""` |
| `currency_unit` | `"chaos"` | base unit for every price |
| `divine_to_chaos` | number\|null | chaos per 1 Divine Orb (the Divine display rate) |
| `chaos_img` / `divine_img` | string | poecdn currency icon URLs (may be `""`) |
| `generated_at` | int | unix seconds |
| `pricing_note` | string | human-readable statement of the invariant (for a UI footer) |

### 2.2 `totals`
Sums **only poe.ninja-priced items** (gems + uniques). Rares/magic are excluded (they have
no server-side number). **Weapon-swap items** (`swap:true`) are also excluded by default
(D-0018); they stay in `items[]`/`rares{}` for a client-side toggle to re-include.
```jsonc
{ "currency": "chaos",
  "chaos":  { "min": 31760.26, "median": 31985.66, "high": 32438.54 },
  "divine": { "min": 268.472,  "median": 270.378,  "high": 274.206 },
  "priced_items": 22,      // items with a poe.ninja number
  "unpriced_items": 19,    // items carrying a trade_query but no server number
  "note": "…" }
```
Any tier value may be `null` (nothing priced). `divine.*` = `chaos.* / divine_to_chaos`.

### 2.3 `items[]` — one row per build item, in **build order**
(belt order for flasks, `skills[]` order for gems, `items[]` order for gear).

Common fields (every row):
| field | type | notes |
|---|---|---|
| `index` | int | stable position in this response's `items` array; the key used in `rares` |
| `name` | string | display name (`"Unique, Base"` or type line) |
| `group` | `equipment`\|`flask`\|`jewel`\|`gem` | |
| `category` | `unique`\|`rare`\|`magic`\|`gem`\|`normal` | routing/pricing class |
| `slot` | string | display slot ("Body Armour", "Ring", "?", …) |
| `rarity` | string | "Unique"/"Rare"/"Magic"/"Gem"/… |
| `count` | int | copies |
| `icon` | string | item art URL |
| `price` | object | see §2.4 |
| `trade_url` | string | clickable `?q=` browser search (**empty** only if no query could be built) |
| `trade_query` | object\|null | the exact `{query, sort}` to POST to the trade **API** (§2.5) |

Present when the item has sockets/links (a 5/6-link drives price):
`max_link` (int), `total_sockets` (int), `socket_colours` (string[] of R/G/B/W/A).

`swap` (bool, present + `true` only on Weapon2/Offhand2 items) — a weapon-swap item, excluded
from `totals`/`priced_items` by default (D-0018). `rarity` reads `"Unique"`/`"Relic"` for
foil/relic uniques (frameType 10/9), which route to `category:"unique"`.

Non-gem rows add `mods`: `{ "implicit": string[], "explicit": string[] }` (rich-text
stripped) when the item has any.

**Variant-registered unique rows** add `variant` (object, §2.8) — what makes this copy a
price-variant and the defining stats that were pinned into its `trade_query`. Present only for
uniques in the D-0019 registry; absent on every other row.

**Gem rows** add: `level`, `quality` (int), `corrupted` (bool), `granted` (bool — the
active skill is item-provided, so excluded from its price total), `supports` (array of
`{name, level, quality, corrupted, icon, support, granted}`), and host grouping fields
`host_slot`, `host_name`, `host_base`, `host_unique` (bool), `host_inventory_id`.

### 2.4 `price` object (mirrors the local engine's `_result_dict`)
| field | type | notes |
|---|---|---|
| `chaos` | `{min,median,high}` | numbers or `null`. For point estimates (gems, name-matched uniques) all three are equal. |
| `divine` | `{min,median,high}` | derived: `chaos / divine_to_chaos` (or `null`) |
| `confidence` | `high`\|`medium`\|`low`\|`none` | |
| `method` | string | see §3 for the enum |
| `source` | `poe.ninja`\|`trade`\|`none` | **`poe.ninja`** = a real server-side number; **`trade`** = priced client-side via `trade_query`; **`none`** = normal/unpriceable item |
| `note` | string | human explanation |
| `sample_size` / `total_found` | int | poe.ninja listing sample / total (`listing_count` echoes it for uniques) |

Gem-priced rows additionally carry (merged from the engine's `extra`):
`kind:"skill"`, `level`, `quality`, `corrupted`, `total_chaos` (= sum of priced gems;
**`null` iff nothing priced**), and `gems[]` — the per-gem breakdown, each
`{name, support, granted, level, quality, corrupted, chaos|null, variant, note, trade_url}`.
**Invariant:** `total_chaos == sum(g.chaos for g in gems if g.chaos != null)`; a `granted`
gem always has `chaos: null` and is excluded.

Unique-priced rows additionally carry: `listing_count` (int), `n_variants` (int — how many
poe.ninja lines share this name), `variant` (string — the chosen variant, or `""`).

### 2.5 `trade_query` — the extension deliverable
For rares, magic items, and uniques, this is the **exact** body to POST to
`https://www.pathofexile.com/api/trade/search/<meta.league>`:
```jsonc
{ "query": { "status": {"option":"online"}, "type":"…", "name":"…",
             "stats":[{"type":"and","filters":[{"id":"explicit.stat_…"}, …]}],
             "filters": { "armour_filters": {…}, "socket_filters": {…}, … } },
  "sort": { "price": "asc" } }
```
`trade_url` is the identical payload URL-encoded onto `…/trade/search/<league>?q=<payload>`
(the browser search page). Both open/execute the SAME search. The extension should POST
`trade_query`, read the returned `id` + result hashes, then `GET
…/api/trade/fetch/<ids>?query=<id>` — exactly what the local engine does, but from the
user's IP. **Rate-limit discipline is the extension's responsibility.**

Query construction is faithful to the local engine:
- **rares** → scoped to the item **category** by default (generic, e.g. `weapon.wand`; §2.6.1),
  with the exact base as the user alternative; require every *searchable* affix (AND group) +
  each total defence value at ≥85% (`armour_filters`) + a `socket_filters.links.min` for
  5/6-links.
- **uniques** → `name` + base `type` (+ links) (+ any build-defining `+# to Level of all …
  Skills` roll pinned to the build's value). *(D-0016 leaves uniques on name+type.)*
- **magic** → the item **category** by default (exact base available; §2.6.1), no affix
  filters.
- **gems** → `type`=gem name + `type_filters.category` (gem.activegem/gem.supportgem) +
  `misc_filters` (`gem_level.min`, `quality.min`, `corrupted`).

### 2.6 `rares` — affix-picker payload (for manual refinement UIs)
Keyed by the item `index` (string) for every trade-queryable **rare, unique, AND magic** item
(gems are priced by poe.ninja, not affix-searched, so they are absent). Mirrors the local web
`rares_meta` map, enriched so a client picker can render every option with no extra lookups.
Per **D-0015 the default query already requires _all_ of an item's searchable affixes** — this
map is what lets the *user* (never the tool) choose to exclude one: every affix is listed,
including the unsearchable ones (shown greyed, `searchable:false`), so the user sees everything
and the tool hides nothing.

```jsonc
"6": {
  "status": "priced" | "unpriced",       // "priced" => poe.ninja gave a number (uniques only)
  "name": "…", "kind": "rare" | "unique" | "magic",
  "scope": "category: Wand" | "base: Opal Wand" | "unique: Mageblood",  // human label of scope_q
  "scope_q": { "filters": {…category…} } | { "type":"…" } | { "name":"…","type":"…" },  // the DEFAULT scope
  "scopes": { "category": {"id","label"}|null, "base": {"type","label"}|null },  // rare/magic ONLY (§2.6.1)
  "affixes": [ AffixOption, … ],          // the item's mods + total-defence values, display order
  "pseudo":  [ PseudoOption, … ]          // combined resistance totals (may be [])
}
```

**`AffixOption`** — one selectable line (a mod, or a total-defence value):

| field | type | meaning |
|---|---|---|
| `kind` | `"stat"` \| `"equip"` | `stat` = an explicit-style mod (searched via `stats`); `equip` = a total defence value (searched via `armour_filters`) |
| `text` | string | display line (rich markup stripped; enchants suffixed `" (enchant)"`) |
| `stat_id` | string \| null | trade stat id for a searchable `stat` affix; `null` when unsearchable or for `equip` |
| `key` | string | **`equip` only** — `ar`/`ev`/`es`/`ward` (the `armour_filters` key); absent on `stat` |
| `value` | number \| null | the item's roll (signed; negative when `negated`). Always present, even when unsearchable |
| `default_min` | number \| null | value to prefill the search **min** (= the roll for a normal affix); `null` when unsearchable or when the roll prefills max instead |
| `default_max` | number \| null | value to prefill the search **max** (only for a `negated`/"reduced" roll); else `null` |
| `searchable` | bool | `false` = no trade filter matches this mod → the picker greys it out but still lists it (`reason` says why) |
| `negated` | bool | the roll is a "reduced" value carried on the opposite-polarity "increased" stat → filter as a max, not a min |
| `resist` | bool | this mod folds into a `pseudo` resistance total (the picker hides it when the pseudo toggle is on) |
| `group` | string | the mod's trade stat group: `explicit` · `crafted` · `fractured` · `enchant` · `implicit` · `veiled` · `scourge` · `crucible`; `equip` for defence totals; `pseudo` for pseudo entries. Defaults to `explicit` for PoB imports (which carry no per-mod group). **`implicit` rows are OPT-IN**: listed so a searchable corrupted/base implicit can be added, but `prefer:false`, `default_min`/`default_max` `null`, and NOT in the default rare query |
| `prefer` | bool | ticked-by-default in the picker (rares: every searchable affix; uniques: only build-defining `+# to Level of all … Skills` rolls **and D-0019 variant-defining mods**) |
| `priority` | enum | default tier — `required` · `nice` · `notimp` · `skip` (a `defining` mod is always `required`) |
| `defining` | bool | **D-0019** — this mod is a variant-DEFINING mod of a registered unique (the aura combo, the Allocates notable, the timeless seed, the socket/passive count …). Always `searchable:true`, `prefer:true`, `priority:"required"`; the picker should lock/highlight it. `false` on every ordinary affix and every non-registry item |
| `option` | int | **D-0019, defining OPTION mods only** — the trade `value.option` for an "Allocates X" / ring-size / keystone-radius mod. When present, `stat_id` is the **base** id (pipe stripped) and the filter is `{"id":stat_id,"value":{"option":option}}`; `default_min`/`default_max` are both `null` (no numeric bound). Absent otherwise |
| `exact` | bool | **D-0019, defining EXACT mods only** (timeless seed, socket/passive count) — search `min == max == default_min` (a different seed/count is a different item). `default_max` stays `null` (so the ≤1-bound rule holds); the client sets `max = min`. Absent/`false` otherwise |
| `reason` | string | why unsearchable (e.g. `"no trade filter matches this mod"`), else `""` |

**`PseudoOption`** — a combined resistance total the picker can search instead of the item's
individual resist mods. Same fields as a `stat` AffixOption (always `searchable:true`,
`resist:true`, `group:"pseudo"`), **plus `folds`**: the affixes summed into this total, so the
picker can grey out exactly the rows it replaced.

| field | type | meaning |
|---|---|---|
| `stat_id` | string | `pseudo.pseudo_total_elemental_resistance` or `pseudo.pseudo_total_chaos_resistance` (real trade pseudo ids, present in the bundled stats) |
| `value` / `default_min` | number | the item's prefilled total. An `all Elemental` roll counts ×3 into the elemental total; an `all Resistances` roll feeds **both** the elemental and chaos totals |
| `folds` | array | `[{ "index": <position in this item's `affixes`>, "text", "stat_id", "value" }, …]` — every member's `index` points to a `resist:true` affix on the same item |

Real fixture example (offline Allflame sample): a **magic** bow now gains a picker entry, and a
unique carries a total-defence `equip` option plus a folded elemental-resistance pseudo total:
```jsonc
"6": {                                    // magic item — magic now gets a picker entry too
  "status":"unpriced", "kind":"magic", "name":"Upgraded Thicket Bow",
  "scope":"category: Bow",                 // D-0016 default = the item category, not the base
  "scope_q":{"filters":{"type_filters":{"filters":{"category":{"option":"weapon.bow"}}}}},
  "scopes":{"category":{"id":"weapon.bow","label":"Bow"},   // weapon subcategory [INFERRED] from base
            "base":{"type":"Thicket Bow","label":"Thicket Bow"}},
  "affixes":[ { "kind":"stat", "text":"+8% to Quality of Socketed Gems",
                "stat_id":"explicit.stat_3828613551", "value":8.0, "default_min":8.0,
                "default_max":null, "searchable":true, "resist":false, "negated":false,
                "group":"crafted", "prefer":true, "priority":"notimp", "reason":"" } ],
  "pseudo":[] },
"1": {
  "status":"priced", "kind":"unique", "name":"The Gull, Raven Mask", "scope":"unique: The Gull",
  "affixes":[ /* … */
    { "kind":"equip", "key":"ev", "stat_id":null, "text":"Total Evasion Rating", "value":316,
      "default_min":316, "default_max":null, "searchable":true, "resist":false, "negated":false,
      "group":"equip", "prefer":false, "priority":"skip", "reason":"" } ],
  "pseudo":[
    { "kind":"stat", "text":"+#% total Elemental Resistance",
      "stat_id":"pseudo.pseudo_total_elemental_resistance", "value":32, "default_min":32,
      "default_max":null, "searchable":true, "resist":true, "negated":false, "group":"pseudo",
      "prefer":false, "priority":"skip", "reason":"",
      "folds":[ { "index":2, "text":"+32% to Cold Resistance",
                  "stat_id":"explicit.stat_4220027924", "value":32.0 } ] } ] }
```
(`equip` affixes carry `key` = `ar`/`ev`/`es`/`ward` instead of `stat_id`; searched via
`armour_filters`. An unsearchable affix — e.g. `"1 Added Passive Skill is a Jewel Socket"` — is
still listed with `searchable:false`, `stat_id:null`, `default_min:null` and a `reason`.)

### 2.6.1 `rares[].scopes` — category vs exact base (D-0016)
For **rare and magic** entries only (uniques search by name+type and omit this field), `scopes`
carries the two search scopes so a picker can let the user choose which to run:

```jsonc
"scopes": {
  "category": { "id": "weapon.wand", "label": "Wand" },   // the DEFAULT (generic) — or null
  "base":     { "type": "Opal Wand", "label": "Opal Wand" }  // the exact-base option — or null
}
```

- **`category` is the default.** `scope`, `scope_q`, the item's top-level `trade_query`, and
  `trade_url` are all scoped to `category.id` — a trade `type_filters.filters.category.option`,
  i.e. the site's "Item Category" dropdown — whenever the item's slot maps to one. Generic on
  purpose: *any wand*, not *Opal Wand*. `id` is always a real trade category (taken from the
  trade `data/filters` "Item Category" list — no invented ids); `label` is that option's exact
  display text.
- **`base` is the exact-base alternative** the user can switch to — a `scope_q` of
  `{ "type": <base> }`. Null only when the base isn't a recognised trade type.
- **Fallback:** when the slot maps to no category (`category: null`), the default *is* the
  exact base (`scope_q` = `{ "type": <base> }`), so a search can always be built.
- **Weapon subcategory** (`weapon.wand` / `weapon.bow` / `weapon.sceptre` / `weapon.claw`) is
  **[INFERRED]** from the base name's last word — the trade items endpoint groups every weapon
  under one label, so the base name is the only class signal in bundled data. Ambiguous weapon
  classes (sword / axe / mace / staff / dagger — one- vs two-handed, or base vs rune/war
  variants, can't be told apart from the base name) stay the generic `weapon` ("Any Weapon"),
  which is still a correct scope. A quiver in the off-hand slot is scoped to `armour.quiver`
  (not `armour.shield`). Full mapped/unmapped table: `docs/notes-v2-api.md`.

### 2.7 `warnings[]`
Array of human-readable strings (empty in v1.0; reserved for soft issues).

### 2.8 item `variant` — the variant-unique block (D-0019)
Present on an item row **only** for a unique in the variant registry
(`api/_data/variant_uniques.json`; runtime reads that file, never the network). It states what
makes this copy a *price-variant* and which stats were pinned into its `trade_query`, so a UI
can render/lock the defining mods and explain the price.

```jsonc
"variant": {
  "class": "seed-jewel",             // seed-jewel | notable-jewel | socket-defined |
                                     //   roll-defined | mod-variant
  "label": "Caspiro seed 29120",     // human summary of THIS copy's variant
  "locked_stats": [                  // the REQUIRED defining filters (a subset of trade_query.stats)
    { "stat_id": "explicit.pseudo_timeless_jewel_caspiro",
      "value": { "min": 29120, "max": 29120 },   // {option:N} | {min:N,max:N} | {min:N} | null
      "text": "Commissioned 29120 coins to commemorate Caspiro" } ]
}
```

- **`class`** — how the variant is encoded (and how it is priced): `seed-jewel` (timeless; exact
  displayed-seed `min==max`, conqueror in the stat id; ninja floor-only), `notable-jewel`
  (Forbidden/Impossible-Escape/Thread-of-Hope OPTION stat; ninja floor-only), `socket-defined`
  (exact abyssal/passive count; ninja `map-count`), `roll-defined` (Watcher's-Eye aura combo,
  own-rolls uniques; ninja floor-only, capped low), `mod-variant` (element/base forms poe.ninja
  enumerates; ninja `map-variant`/`map-base`; `locked_stats` may be `[]` when the ninja line
  itself is the price).
- **`label`** — a concise, deterministic description built from the copy alone (e.g.
  `"Berserker"`, `"affected by Hatred, Anger"`, `"7 Added Small Passives"`,
  `"Kaom seed 15000"`); for a `mod-variant` it may be filled from the matched ninja variant.
- **`locked_stats[]`** — the defining filters, each `{stat_id, value, text}`. `value` mirrors the
  emitted trade filter: `{"option":N}` for an OPTION mod (search `{"id":stat_id,"value":{"option":N}}`),
  `{"min":N,"max":N}` for an EXACT seed/count, `{"min":N}` for an aura/own roll, or `null`. These
  are ADDITIVE (D-0015): they are the *new required* filters the item's `trade_query` now carries
  — nothing the item rolled is dropped. The matching `rares[].affixes` rows are flagged
  `defining:true` (with `option`/`exact` as applicable, §2.6).

---

## 3. Enums

**`price.method`**
- `skill` — gem group priced from poe.ninja.
- `unique-ninja` — unique priced by exact name (single poe.ninja line).
- `unique-ninja-variant` — a specific poe.ninja variant matched to the item. Non-registry: the
  variant `label` tokens are covered by the item's mods, **or** — when poe.ninja splits the name
  by socket-link count — the line for the copy's link tier (5L / 6L / unlinked), `variant` then
  reads e.g. `"6-link"`. **D-0019 registry:** the line for the
  OWNED variant, selected deterministically — by socket/passive **count** (`map-count`, e.g.
  Voices "7 passives"; the observed abyssal count when the label isn't literal), by variant
  **label** vs the copy's mods (`map-variant`, e.g. Impresence "Lightning"), or by **base**
  (`map-base`, e.g. Grand Spectrum).
- `unique-ninja-floor` — **D-0019** — poe.ninja lists only ONE aggregate line for a
  variant-registered name whose variants it cannot split (timeless seed, "Allocates X" notable,
  Watcher's-Eye aura combo, and other roll-defined uniques). `chaos.{min,median,high}` are that
  **floor** (the cheapest line = the min of the range across all variants); always
  `confidence:"low"`. The real price is this row's exact-variant `trade_query` (the trade link).
- `unique-ninja-range` — **(non-registry only)** several variants of a name not in the registry;
  `chaos.{min,median,high}` is the spread across them (exact roll unclear — verify via
  `trade_url`). Always `confidence:"low"`.
- `unique-unpriced` — name not on poe.ninja (or unnamed), **or** a registry variant whose exact
  owned variant poe.ninja does not enumerate (never a cheapest-any-variant number — D-0019). No
  number; use `trade_query`.
- `rare-unpriced` — rares are never server-priced; use `trade_query`.
- `magic-unpriced` — magic items; use `trade_query`.
- `none` — normal item, not priced.

**`price.source`**: `poe.ninja` (real number) · `trade` (client must run `trade_query`) ·
`none` (no query, no number).

**`price.confidence`**: `high` · `medium` · `low` · `none`. For gems/uniques it reflects
the poe.ninja `listingCount` (≥5 high, ≥2 medium, else low); `unique-ninja-range` and
`unique-ninja-floor` are always `low` (D-0019: the floor/range is a bound, not a match on the
exact variant, so its huge aggregate listing count never earns a high rating).

**`affixes[].priority`** (default picker tier): `required` · `nice` · `notimp` · `skip`.

---

## 4. Errors (HTTP 400/500/502)
```jsonc
{ "ok": false,
  "error_type": "bad_input" | "ninja_error" | "upstream_error" | "server_error",
  "error": "human-readable message" }
```
- `bad_input` (400) — unrecognised URL/code, a build-overview link, an unsupported paste
  host, or missing input.
- `ninja_error` (502) — poe.ninja was unreachable / returned no data / the character is
  private/unindexed. Message is safe to show.
- `upstream_error` (502) — a blocked/failed upstream (should not occur in normal flow).
- `server_error` (500) — unexpected. Message is `TypeName: detail`.

Always branch on the boolean **`ok`**, not the HTTP code.

---

## 5. League handling (important)
The public function **cannot** call the trade `data/leagues` endpoint, so:
- For a **poe.ninja character**, `meta.league` = the poe.ninja league display name, used
  verbatim as the trade league. For challenge leagues the two are identical (verified
  against the trade `data/leagues` fixture: poe.ninja `"Allflame"` == trade id `"Allflame"`).
- For a **PoB import** (no league), the current challenge league from poe.ninja is used.
- Pass **`league`** to override (e.g. `"Hardcore Allflame"`, `"Standard"`). If a build's
  `trade_url`/`trade_query` ever 404s on the trade site, the league string is the thing to
  correct — re-request with the right `league`.

---

## 6. Caching & CORS (response headers)
- Success: `Cache-Control: public, s-maxage=600, stale-while-revalidate=86400` — the CDN
  serves a cached copy for 10 min and a stale copy (revalidating in the background) for up
  to a day. poe.ninja data isn't realtime, so this is safe and keeps the free tier cheap.
- Errors: `Cache-Control: no-store`.
- CORS (all responses): `Access-Control-Allow-Origin: *` (public data),
  `Access-Control-Allow-Methods: GET, POST, OPTIONS`, `Access-Control-Allow-Headers:
  Content-Type`. So any origin (the pages.dev site, a userscript, the extension) may call it.

---

## 7. Real example (abridged — a live Allflame character)
Full untrimmed captures are written by the verifier to
`scratchpad/sample_response_{offline,live}.json`. Long `trade_url`/PoB strings truncated
below with `…`.

```jsonc
{
  "ok": true, "schema_version": "1.0",
  "meta": {
    "character": "TestCharacter", "account": "example-0416",
    "class": "Elementalist", "level": 100,
    "league": "Allflame", "ninja_league": "Allflame", "source": "poe.ninja",
    "currency_unit": "chaos", "divine_to_chaos": 118.3,
    "chaos_img": "https://web.poecdn.com/gen/image/…", "generated_at": 1785122891,
    "pricing_note": "Item prices are from the poe.ninja economy only … never calls pathofexile.com."
  },
  "totals": {
    "currency": "chaos",
    "chaos":  { "min": 31760.26, "median": 31985.66, "high": 32438.54 },
    "divine": { "min": 268.47,   "median": 270.38,   "high": 274.21 },
    "priced_items": 22, "unpriced_items": 19
  },
  "items": [
    {                                                    // ── a UNIQUE priced by name ──
      "index": 0, "name": "Maloney's Mechanism, Ornate Quiver",
      "group": "equipment", "category": "unique", "slot": "Off-hand (swap)",
      "rarity": "Unique", "count": 1, "icon": "https://web.poecdn.com/…",
      "max_link": 3, "total_sockets": 3, "socket_colours": ["R","G","W"],
      "mods": { "implicit": ["Has 1 Socket"],
                "explicit": ["Has 2 Sockets","Trigger a Socketed Bow Skill …",
                             "12% increased Attack Speed","+66 to maximum Life", …] },
      "price": {
        "chaos": {"min":14.0,"median":14.0,"high":14.0},
        "divine": {"min":0.118,"median":0.118,"high":0.118},
        "confidence":"high", "note":"poe.ninja price by name", "method":"unique-ninja",
        "source":"poe.ninja", "sample_size":1, "total_found":319,
        "listing_count":319, "n_variants":1, "variant":""
      },
      "trade_url": "https://www.pathofexile.com/trade/search/Allflame?q=…",
      "trade_query": { "query": { "status":{"option":"online"},
                                  "name":"Maloney's Mechanism", "type":"Ornate Quiver",
                                  "stats":[{"type":"and","filters":[]}] },
                       "sort": {"price":"asc"} }
    },
    {                                                    // ── a GEM group (transfigured) ──
      "index": 35, "name": "Ethereal Knives of the Massacre",
      "group":"gem", "category":"gem", "slot":"?", "rarity":"Gem", "count":1,
      "level":20, "quality":20, "corrupted":false, "granted":false,
      "supports":[ {"name":"Greater Spell Echo Support","level":3,"quality":20,
                    "corrupted":false,"support":true,"granted":false}, … ],
      "host_slot":"Body Armour", "host_name":"Blunderbore", "host_base":"Astral Plate",
      "host_unique":true, "host_inventory_id":"BodyArmour",
      "price": {
        "chaos": {"min":2971.9,"median":2971.9,"high":2971.9},
        "divine": {"min":25.12,"median":25.12,"high":25.12},
        "confidence":"low", "note":"poe.ninja gem prices: active + 5 supports",
        "method":"skill", "source":"poe.ninja", "kind":"skill",
        "level":20, "quality":20, "corrupted":false, "total_chaos":2971.9,
        "gems": [
          {"name":"Ethereal Knives of the Massacre","support":false,"granted":false,
           "level":20,"quality":20,"corrupted":false,"chaos":98.0,"variant":"20/20",
           "note":"","trade_url":"https://www.pathofexile.com/trade/search/Allflame?q=…"},
          {"name":"Greater Spell Echo Support","support":true,"granted":false,"level":3,
           "quality":20,"corrupted":false,"chaos":2366,"variant":"3/20","note":"",
           "trade_url":"…"}
        ]
      },
      "trade_url":"https://www.pathofexile.com/trade/search/Allflame?q=…",
      "trade_query": { "query": { "status":{"option":"online"},
        "type":"Ethereal Knives of the Massacre",
        "filters": { "type_filters":{"filters":{"category":{"option":"gem.activegem"}}},
                     "misc_filters":{"filters":{"gem_level":{"min":20},"quality":{"min":20}}} },
        "stats":[{"type":"and","filters":[]}] }, "sort":{"price":"asc"} }
    },
    {                                                    // ── a RARE (priced client-side) ──
      "index": 12, "name": "Phoenix Star, Large Cluster Jewel",
      "group":"jewel", "category":"rare", "slot":"Jewel", "rarity":"Rare", "count":1,
      "mods": { "implicit": [], "explicit": ["Adds 3 Passive Skills", …] },
      "price": { "chaos":{"min":null,"median":null,"high":null},
                 "divine":{"min":null,"median":null,"high":null},
                 "confidence":"none", "method":"rare-unpriced", "source":"trade",
                 "note":"rares are priced on your machine via the trade link / extension …" },
      "trade_url":"https://www.pathofexile.com/trade/search/Allflame?q=…",
      "trade_query": { "query": {                       // D-0016 default: category scope, not "type"
        "filters":{"type_filters":{"filters":{"category":{"option":"jewel"}}}},
        "status":{"option":"online"},
        "stats":[{"type":"and","filters":[ {"id":"explicit.stat_1719521705"},
          {"id":"explicit.stat_3258414199"}, {"id":"enchant.stat_3948993189|16"}, … ]}] },
        "sort":{"price":"asc"} } }
  ],
  "rares": {
    "12": { "status":"unpriced", "name":"Phoenix Star, Large Cluster Jewel", "kind":"rare",
            "scope":"category: Any Jewel",
            "scope_q":{"filters":{"type_filters":{"filters":{"category":{"option":"jewel"}}}}},
            "scopes":{"category":{"id":"jewel","label":"Any Jewel"},
                      "base":{"type":"Large Cluster Jewel","label":"Large Cluster Jewel"}},
            "affixes":[ {"kind":"stat","text":"Adds 3 Passive Skills","stat_id":"…",
              "value":3,"searchable":true,"resist":false,"negated":false,"prefer":true,
              "priority":"nice","reason":""}, … ], "pseudo":[] }
  },
  "warnings": []
}
```
