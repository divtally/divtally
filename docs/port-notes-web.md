# Web / UI / extension port notes (PoE2 -> PoE1)  [P2]

Written by the web-layer port agent, 2026-07-26. Companion to `docs/port-notes-core.md`
(the engine port) and `docs/research/contract.md` (the authoritative rename/removal map,
which this pass applied). Everything here is grounded in the research docs, the ported
`bpc/report.py`/`models.py` field names, and live verification (below). `[INFERRED]` marks
anything not directly observed.

## Files I own / changed
- `bpc/web.py`
- `bpc/ui/assets/core.js`, `bpc/ui/assets/sample.js`
- all `bpc/ui/*.html` skins: `abacus, atelier, binder, console, facts, foundry, ledger,
  manifest, stash, waterfall` + the two underscore views `_reference.html`, `_exttest.html`
- `extension/` (`README.md, manifest.json, background.js, content.js, popup.html, popup.js`)
- this doc

Everything else (`engine.py`, `pricing.py`, `report.py`, `models.py`, ...) is the core
agent's and was left untouched.

## 1. Currency rename `exalted` -> `chaos` (contract sec 1)
Applied a single **base64-safe** anchored substitution pass across core.js + web.py + all
skins (script recorded in the session scratchpad, not committed). Every search token carried a
`.`, `:`, `_`, `(`, quote, or space -- none of which occur in the poecdn base64 image blobs
embedded in the skins -- so no image URL could be corrupted. Renames:
`divine_to_exalted->divine_to_chaos`, `exalted_img->chaos_img`, `.exalted->.chaos` (every
`p.exalted.{min,median,high}` read), `exalted:`->`chaos:` (JS object keys), `curImg('ex')` /
`curImg("ex")` -> `curImg('chaos')`, `Exalted Orb`->`Chaos Orb`. Python dict keys `"exalted":`
(quote before the colon) were intentionally **not** matched by the script and were fixed by
hand in web.py (`_result_dict`, the error/skip fallback dicts, `currency_image("chaos")`).
Residual prose (`Prices in Exalted`, `1 Divine in Exalted`, `EXALTED`, comments) fixed
per-file. Divine untouched (still the secondary display unit; `divRate()` math is unchanged
because chaos is now the base).

## 2. Taxonomy: rune section removed, "Flasks & Charms" -> "Flasks" (contract sec 2)
- `core.js GROUPS` -> dropped `['rune',...]`, renamed flask title. This alone re-taxonomises
  the 3 skins that render from `bpc.itemsByGroup()`/`bpc.GROUPS` (atelier, facts, ledger).
- Every skin that keeps its OWN group map was edited: `foundry` (ASM_CODE/ASM_LABEL + a
  schematic `Rune:` slot coord), `abacus` (rarity-class + command-alias maps), `console`
  (SECTOR_ICON + rarClass), `binder` (GROUP_LABEL/SIGIL/RARITY_COLOR + sigilGlyph line),
  `waterfall` (GCOL/GLABEL + section order), `manifest` (gateCodes -> contiguous A-D, grpLabel),
  `stash` (SLOT_GLYPH `Rune`, catClass, panel-head text, section order, tooltip mods bucket).
- web.py classic `PAGE`: `GROUPS` const + the Python `_run_job` mods bucket both dropped rune.

## 3. web.py structural (contract sec 1b/2/3)
- Dropped `CAT_RUNE` from the `.models` import (it no longer exists -> would be an ImportError).
- `_METHOD_OK`: removed the `CAT_RUNE: ("exchange",)` entry.
- `_price_task`: deleted the now-dead `kind=="gems"` and `kind=="rune"` branches
  (`price_gems_aggregate`/`price_rune` were deleted from pricing.py). `_run_job` queue: removed
  the `CAT_RUNE` branch.
- Gem skeleton row: `it.gem_sockets` is **gone** on the model (would AttributeError) ->
  `row["sockets"] = len(it.supports)` (a support count, so skins showing "N sup" still work);
  added `row["quality"]=it.gem_quality` and `row["corrupted"]=it.corrupted` (both real Item
  fields, verified in models.py). `it.rune_mods` is gone -> the non-gem mods tooltip bucket is
  now just `{implicit, explicit}`.
- meta dict currency image arg `currency_image("exalted")` -> `("chaos")`.
- Branding: gallery/classic `<title>`+`<h1>`, argparse description, startup print, module
  docstring, `_warm_stats` comment, and the metaHead "Path of Building **2** import code" ->
  "Path of Building import code". (The engine already emits `divine_to_chaos`/`chaos_img`.)

## 4. gem `extra` reshape in stash.html (contract sec 3c) -- the only deep skin change
stash is the sole skin that renders the gem `extra`. The PoE2 uncut/cut/lineage model was
replaced with the PoE1 per-gem model:
- `renderSkills`: the `uncut` local (= group total) -> `total` (= `p.chaos.median`); the
  "uncut (DIY) ... poe.ninja tracks uncut gems only" note -> "priced from the poe.ninja gem
  economy: active skill + every support gem ... (each gem by name / level / quality /
  corruption)". Trade-search title dropped the stale "N sockets".
- `supportsHTML`: was keyed off `p.lineage[]` with "free" non-lineage rows; now keyed off
  `p.gems[]` (first entry = active, rest = supports, each a real priced gem) -- every support
  shows its own chaos price + a `Lv X/Q` (and `corrupted`) tag. Matches supports to their price
  by name (case-insensitive).

## 5. Charm doll in stash.html -> flask belt
PoE1 has no charm slot; the flask belt is exactly 5 (life | 3 utility | mana), which is the
doll's existing 5-cell bottom row. Kept the layout + CSS grid-area names (`slot-ch1..3`)
verbatim; only the JS var `charms`->`utils`, dropped the `indexOf('charm')` special case, and
retitled the overflow "Flasks & Charms" -> "Flasks". Look/layout unchanged.

## 6. Trade links (contract sec 5, trade1.md sec 8)
The engine emits PoE1 `trade_url`s (`/trade/search/{league}[?q=|/{id}]`, no realm) and the UIs
just render them -- no change needed there. BUT stash builds its OWN fallback `?q=` links
(`pkBuildTradeUrl`, `cardTradeUrl`): those were PoE2 (`/trade2/search/poe2/...` +
`equipment_filters`). Fixed to `/trade/search/{league}?q=...` and **`armour_filters`** (PoE1 has
no `equipment_filters`; ar/ev/es/ward field names are unchanged -- trade1.md sec 2c/6). This is
a real correctness fix (a PoE2 link would 404 / mis-query on the PoE1 site), not cosmetic.
`_exttest.html`'s league-extraction regex `/\/poe2\/(..)/` -> `/\/search\/(..)/` (PoE1 URLs put
the league right after `/search/`), placeholder URL and "PoE2" copy updated.

## 7. sample.js -- rewritten as a real PoE1 build (marked demo)
A fictional level-96 Elementalist **Firestorm** build, but every item name, base, gem, icon and
chaos price is drawn from **live poe.ninja Allflame economy data** fetched this session (probe
scripts in scratchpad; a handful of polite GETs to `poe.ninja/poe1/api/economy/*`, no trade API
touched). So the `?mock` preview shows authentic PoE1 content:
- Chaos Orb / Divine Orb icons + `divine_to_chaos = 106` from the live currency overview.
- Real uniques with real current prices: Headhunter (11,660c), The Pandemonius, Watcher's Eye,
  Thread of Hope, Atziri's Step/Promise, Doryani's Catalyst, The Taming, Crown of the Inward
  Eye, Piscator's Vigil, Prism Guardian (+ real poecdn icons). Rare slots reuse a same-slot
  unique's art purely so the box has a picture.
- Real gem economy: a 6-link Firestorm group (active + Spell Echo/Controlled Destruction/
  Elemental Focus/Concentrated Effect/Ignite Prolif) totalling ~429c; a Determination + **Enlighten 4**
  group (~1040c, showing an expensive support driving the cost); a granted Flame Dash group.
  Uses the new `extra` shape (`total_chaos`, `gems:[{name,support,level,quality,corrupted,
  chaos,variant,trade_url}]`) and `supports:[{name,level,quality,corrupted,icon}]`.
- One rare cluster jewel is left **unpriced** (null, with a trade link) to demo the "no
  misleading number, just a link" path. Rare affix-picker payloads reuse the parent's stat ids
  (`explicit.stat_*`, `pseudo.*`) -- these hashes are shared across PoE1/PoE2 for common mods
  and the pseudo-res ids are confirmed identical (contract sec 5). **[DEMO DATA]** the exact
  affix values/notes are illustrative, not a live search result.

## 8. extension/ -- PoE1 endpoints + branding
- `background.js`: `BASE .../api/trade2` -> `.../api/trade`; removed `REALM="poe2"` and its two
  uses (search path has no realm segment; fetch drops `&realm=poe2`). `DEFAULT_RULES` seeded
  with the PoE1 windows (trade1.md sec 7): search adds `600:21600`, fetch adds `50:300` +
  `1000:21600`. (Exchange isn't used by the extension.)
- `popup.js` league regex `/\/poe2\/(..)/` -> `/\/search\/(..)/`; placeholder + copy -> PoE1.
- README/manifest/content/popup branding "PoE2 Trade Bridge" -> "PoE1"; the site-origin
  `content_scripts.matches` (localhost:8765 + staging) are game-agnostic and unchanged.

## 9. Judgment calls / deliberately left
- **Dead CSS selectors kept.** Category/group colour rules keyed by classes that are never
  emitted anymore (`.r-rune`, `--rune`, `.rar-rune`, `.mtag.rune`, `.rtag.rune`, `.tt-mod.rune`,
  `.h-rune`, `--g-rune`) are inert -- no element ever receives category/group "rune", so they
  cannot render a section or "silently win" any behaviour (RULE 6 is about superseded *logic*).
  Removing each would mean pulling both a `--var` and its dependent selector across large CSS
  blocks for zero visible effect, against "keep each skin's look intact". Left in place. The
  superseded gem-support CSS that WAS tied to deleted logic (`.sup.lineage`, and the "free"
  support tag) was removed from stash.
- **`max_link`/`total_sockets` badge not added** (contract sec 4, optional). The engine already
  bakes link count into unique/rare `trade_url`s + prices, so correctness needs no UI change;
  the "6L" badge is cosmetic and out of scope for this pass. Left for backlog.
- **stat ids in sample rares are the parent's** (shared GGG hashes) -- fine for a demo and for
  the pseudo-res ids (verified identical), but flagged as demo, not a source-derived pricing.

## 10. Verification evidence (all green, no trade API touched)
- Syntax: `node --check` on core.js, sample.js, background.js, content.js, popup.js; `ast.parse`
  on web.py; `json.load` on manifest.json -- all OK.
- Residual sweep across bpc/ui + web.py + extension: **zero**
  `PoE2|poe2|trade2|exalted|equipment_filters|gem_sockets|price_rune|price_gems|CAT_RUNE|
  divine_to_exalted|Flasks & Charms|Runes / Soul|Path of Building 2` (excluding the documented
  inert CSS class names). 
- Live server render (`verify_web.py`): started `bpc.web` in-process on port 8799 (importing +
  `_bind` never runs the stats pre-warm; no `POST /api/price`), fetched `/`, `/classic`, and
  `atelier/stash/foundry/waterfall` with `?mock`, plus `/assets/core.js` + `/assets/sample.js`.
  **39/39** assertions passed (PoE1 branding, no PoE2/exalted, no "Flasks & Charms"/"Runes /
  Soul Cores", chaos data present). Server shut down after.
- Mock render engine test (`node_verify.js`): loaded the real sample.js + core.js and ran
  `bpc.loadMock()` exactly as a skin does. **14/14** passed: totals compute in chaos
  (median **13,649c = 129 div**), `priceHTML` emits the real PoE1 Chaos Orb + Divine Orb icons,
  `itemsByGroup()` = equipment/flask/jewel/gem (no rune), gem 18 carries `total_chaos=428.6` +
  `gems[6]`, the granted gem and the unpriced cluster are excluded from the total.
