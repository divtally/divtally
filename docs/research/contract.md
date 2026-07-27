# Engine -> UI JSON contract (PoE2 parent -> PoE1 port)

This is the authoritative rename/removal map for the **web/UI port (P2)**. The core port
(this pass) kept the engine->UI JSON **structurally identical** to the PoE2 parent and
renamed **only** what currency (exalted -> chaos) and taxonomy (rune removal, no charms)
forced. P2 applies the edits below to `bpc/web.py`, `bpc/ui/assets/core.js`,
`bpc/ui/assets/sample.js`, and every `bpc/ui/*.html` skin. Nothing structural changed:
same job-polling model, same per-item `{min,median,high}` + confidence + `trade_url`,
same rares/affix-picker payload, same recent-builds/saved-result flow.

Grounding: field lists below were read from the ported `bpc/report.py` (mine, already
renamed) and the current `bpc/web.py` + `bpc/ui/assets/core.js` (P2's, NOT yet edited).
The core side is DONE; P2 mirrors these names.

---

## 1. Currency rename: `exalted` -> `chaos` (base unit flipped)

PoE1's trade index unit is **Chaos**, displayed alongside **Divine** (the parent used
Exalted+Divine). Every `exalted`-named field becomes its `chaos` equivalent. Divine stays.

### 1a. `report.build_payload` (CLI `--json`) - ALREADY DONE in `bpc/report.py`
| Parent key | PoE1 key |
|---|---|
| `divine_to_exalted` | `divine_to_chaos` |
| `currency_unit: "exalted"` | `currency_unit: "chaos"` |
| per-item `"exalted": {min,median,high}` | `"chaos": {min,median,high}` |
| `totals_exalted: {min,median,high}` | `totals_chaos: {min,median,high}` |

### 1b. `bpc/web.py` - P2 TO EDIT
| Location | Parent | PoE1 |
|---|---|---|
| `_result_dict` priced entry | `"exalted": {min,median,high}` | `"chaos": {min,median,high}` |
| `_run_job` meta dict | `"divine_to_exalted": report._finite(div)` | `"divine_to_chaos": ...` |
| `_run_job` meta dict | `"exalted_img": pricer.currency_image("exalted")` | `"chaos_img": pricer.currency_image("chaos")` |
| meta dict | `"divine_img": pricer.currency_image("divine")` | unchanged |

`CurrencyConverter.divine_rate()` / `.fmt()` method NAMES are unchanged (fmt now renders
`"N chaos"` / `"M div (N chaos)"`). `pricer.conv.to_exalted(...)` was renamed to
`to_chaos(...)` **but web.py never calls it** (only `pricing.py` did, already updated).

### 1c. `bpc/ui/assets/core.js` + `sample.js` + every skin - P2 TO EDIT
- `JOB.priced[k].exalted.{min,median,high}` -> `.chaos.{...}` (every read; core.js
  `fillPriced`, `recompute`, and each skin's price rendering).
- `JOB.meta.divine_to_exalted` -> `divine_to_chaos` (core.js `divr()` and skins).
- `JOB.meta.exalted_img` -> `chaos_img` (core.js `curImg`, skins).
- `curImg('ex')` -> `curImg('chaos')`; the `fmt()` unit label `' ex'` -> `' chaos'`;
  `curImg` mapping `kind==='div'?divine_img:exalted_img` -> `...:chaos_img`; the "1 divine
  = N exalted" header text -> "N chaos". (Purely string/label; the number math is unchanged
  because chaos is now the base, so `div = base / divine_to_chaos` still holds.)
- `sample.js` mock payload keys: same `exalted`->`chaos`, `divine_to_exalted`->`divine_to_chaos`.

---

## 2. Taxonomy: rune section removed, no charms

- **Rune group/section deleted.** PoE1 has no runes / soul cores.
  - core.js `GROUPS` and any skin group list: **remove** `['rune','Runes / Soul Cores']`.
  - `report._GROUP_ORDER`/`_GROUP_TITLE` already dropped `rune` (mine).
- **"Flasks & Charms" -> "Flasks"** (no charm slot in PoE1).
  - core.js `GROUPS`: `['flask','Flasks & Charms']` -> `['flask','Flasks']` (+ skins).
  - `report._GROUP_TITLE` already renamed (mine).
- **`bpc/web.py` imports**: `from .models import (..., CAT_RUNE, ...)` -> drop `CAT_RUNE`
  (it no longer exists in `models.py`).
- **`bpc/web.py` `_METHOD_OK`**: remove the `CAT_RUNE: ("exchange",)` entry. Keep
  `CAT_GEM: ("skill",)` (gem method is still `"skill"`), `CAT_UNIQUE: ("unique",)`,
  `CAT_RARE: ("rare",)`, `CAT_MAGIC: ("magic",)` - all still valid method prefixes.
- **`bpc/web.py` `_price_task`**: the `kind == "rune"` and `kind == "gems"` branches are
  now **dead code** (no `CAT_RUNE` items are ever produced; `"gems"` is never queued;
  `pricer.price_rune` / `pricer.price_gems_aggregate` were **deleted** from `pricing.py`).
  Remove both branches. (`price_skill`, `price_unique`, `price_rune`->gone, `price_magic`,
  `price_rare`, `price_rare_custom`, `price_unique_custom` remain.)

---

## 3. Gem row + gem `extra` reshape (uncut/lineage -> real-gem pricing)

PoE1 gems are **real tradeable items** priced by name+level+quality+corruption via the
poe.ninja SkillGem economy. The PoE2 uncut-gem + Jeweller's-Orb + lineage model is deleted.
Method string stays `"skill"` (so `_METHOD_OK` is unaffected).

### 3a. Gem skeleton row (`bpc/web.py` `_run_job`, the `if it.category == CAT_GEM` block)
| Parent field | PoE1 |
|---|---|
| `row["level"] = it.gem_level` | unchanged (still present) |
| `row["sockets"] = it.gem_sockets` | **`it.gem_sockets` removed** -> use `len(it.supports)` for a support count, or drop the field |
| `row["supports"] = it.supports` | unchanged field name, **new element shape** (see 3b) |
| `row["granted"] = ...` | unchanged |
| (new) | may add `row["quality"] = it.gem_quality` |

Also add `row["quality"] = it.gem_quality` if a skin shows gem quality.

### 3b. `it.supports[]` element shape
- Parent: `{name, lineage, icon}`
- PoE1: `{name, level, quality, corrupted, icon}` (each support is a priced gem; `lineage`
  is gone).

### 3c. Gem priced-entry `extra` (merged into `priced[idx]` by `_result_dict`)
- Parent (PoE2): `{kind:"skill", level, sockets, source, uncut, uncut_total, cut,
  cut_total, lineage:[{name, exalted:{min,median,high}, trade_url}]}`
- **PoE1**: `{kind:"skill", level, quality, corrupted, source:"poe.ninja",
  total_chaos, gems:[{name, support, level, quality, corrupted, chaos, variant, trade_url}]}`
  - `total_chaos` = the group's summed chaos price (active + every support). Equals the
    row's `chaos.median` (a point estimate, min==median==high).
  - `gems[]` = per-gem breakdown (first entry is the active skill, `support:false`).
- Any skin that read `.uncut`/`.cut`/`.uncut_total`/`.lineage`/`.sockets` from the gem
  extra must switch to `.total_chaos` / `.gems[]`. The gem row's normal
  `chaos.{min,median,high}` still carries the group total, so a skin that only shows the
  price column needs no gem-specific change beyond the `exalted`->`chaos` rename.

### 3d. Non-gem mods tooltip bucket (`_run_job`, the `else` mods block)
- Parent: `mods = {"implicit":[...], "explicit":[...], "rune":[strip_rich(m) for m in it.rune_mods]}`
- PoE1: **`it.rune_mods` removed** -> drop the `"rune"` bucket:
  `mods = {"implicit":[...], "explicit":[...]}`.

---

## 4. New engine-exposed fields (additions - safe to ignore, nice to surface)

The `Item` now carries PoE1 socket/link data. Skins that ignore them are unaffected; a
skin can show a "6L" badge (docs/research/taxonomy.md 4.9). If P2 wants them in the row,
add in `_run_job`:
- `it.max_link` (int) - size of the largest linked socket group (5/6 = the price driver).
- `it.total_sockets` (int) - `len(it.sockets)`.
- `it.socket_colours` (list[str]) - per-socket R/G/B/W/A.
- `it.sockets` (raw `[{group,attr,sColour}]`).

Rares/uniques whose `max_link >= 5` are already priced WITH a `socket_filters.links` filter
by the engine, so the `trade_url` and price already reflect the link count - no UI change
needed for correctness; the badge is cosmetic.

---

## 5. Unchanged (do NOT restructure)

- Job model: `POST /api/price` -> `{job_id}`, poll `GET /api/job?id=`, `state`
  queued/running/done/error, `progress[]`, `items[]` skeleton, `priced{}`, `rares{}`,
  `searches`, `from_saved`, `saved_ts`. Identical.
- Rares/affix picker payload `rares[idx] = {status, name, scope, kind, scope_q, affixes[],
  pseudo[]}`; `affixes[]` entry `{kind:"stat"|"equip", text, stat_id, key, value,
  searchable, resist, negated, prefer, priority, reason}`. Identical (the pseudo-resistance
  ids are the same in PoE1).
- `POST /api/rare?id=&index=` body `{filters:[{stat_id,min,max}], equip:[{key,min,max}],
  groups?}` or `{skip:true}`. Identical.
- `/api/leagues`, `/api/cache`, `/api/stats`, recent-builds, include/exclude checkboxes,
  saved-result seeding + `_saved_result_aligned` guard. Identical (only the `_METHOD_OK`
  table drops rune, per section 2).
- `pricer.currency_image(cid)`, `pricer.status`, `pricer.client.search_count`,
  `pricer.resolve_type`, `pricer.affix_options`, `pricer._rare_scopes`,
  `pricer.conv.divine_rate/fmt` - all present, same signatures. `Pricer.__init__` gained an
  `economy=` kwarg but web.py builds pricers via `engine.prepare_*` (unchanged returns).
- Trade browser links are now `https://www.pathofexile.com/trade/search/{league}[/{id}|?q=]`
  (no `trade2`, no `poe2` realm segment) - produced by the engine; the UI just renders
  `trade_url`. No UI change.

---

## 6. P2 quick checklist
1. core.js + sample.js + 10 skins: `exalted`->`chaos` everywhere (`p.exalted`->`p.chaos`,
   `divine_to_exalted`->`divine_to_chaos`, `exalted_img`->`chaos_img`, `curImg('ex')`,
   `' ex'` label, "= N exalted" text). Divine untouched.
2. core.js + skins: `GROUPS` drop `rune`, rename flask title to "Flasks".
3. web.py: drop `CAT_RUNE` import; `_result_dict` `exalted`->`chaos`; meta
   `divine_to_exalted`->`divine_to_chaos`, `exalted_img`->`chaos_img` (currency_image
   arg `"chaos"`); `_METHOD_OK` drop rune; `_price_task` remove dead rune/gems branches;
   gem row `sockets`->`len(supports)` (or drop) + optional `quality`; supports element
   shape; drop the `rune` mods bucket.
4. skins reading gem `extra`: `.uncut/.cut/.lineage` -> `.total_chaos/.gems[]`.
5. (optional) surface `max_link`/`total_sockets` for a "6L" badge.

---

## 7. D-0006 additions (feedback round 1) - ADDITIVE only

These fields were ADDED (no renames/removals) for owner feedback round 1. Full UI spec +
real example payloads: `docs/feedback1-spec.md`. Contract-level summary:

### 7a. Gem `PriceResult.extra` gained (merged into `priced[k]` by `web._result_dict`)
- `granted` (bool) - the ACTIVE gem is item-provided (from the character JSON
  `itemProvidedGems` / `isBuiltInSupport`), so it is EXCLUDED from `total_chaos`.
- `host_slot` / `host_name` / `host_base` / `host_unique` / `host_inventory_id` - the gear
  the skill group is socketed into (for grouping gem rows under a host-item header).
  Empty for PoB imports (no `itemSlot`).
- Each `gems[]` element gained `granted` (bool) and `note` (str), plus `support` is now the
  gem's REAL support-ness (a group may hold >1 active). `chaos` is `null` iff granted.
  Invariant: `total_chaos == sum(g.chaos for g in gems if g.chaos != null)`.

### 7b. `Item` (`bpc/models.py`) gained (additive fields, defaults keep old behaviour)
- `granted` (bool, default False), `host_slot`/`host_name`/`host_base`
  (str, default ""), `host_unique` (bool, default False), `host_inventory_id` (str).
- `Item.supports[]` elements now also carry `support` (bool) and `granted` (bool) alongside
  the existing `{name, level, quality, corrupted, icon}`.

### 7c. GRANTED tag source (root-cause fix)
The engine now computes `Item.granted`. The web layer must set the gem skeleton row's
`granted` from it: `row["granted"] = bool(it.granted)` (was inferred from
`it.raw.inventoryId`, which is always `None` for PoE1 `skills[]` gems -> tagged everything).
`core.js::itemGranted` already reads `it.granted`; no core.js change needed.

### 7d. Result order = build order (flask belt order)
`Pricer.price_build` now RETURNS results in the build's original order (belt order for
flasks, `skills[]` order for gems, `items[]` order for gear) while still pricing in
budget-priority order. The report/CLI display each group in source order; the web skeleton
already iterated `items` in order, so this only makes the CLI report consistent. No UI change.
