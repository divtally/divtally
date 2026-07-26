# Core-pipeline port notes (PoE2 -> PoE1)

Written by the core-port agent, 2026-07-26. The coordinator should fold the **Decisions**
below into `docs/00-decision-log.md` (D-0003+). This documents what changed in the `bpc/`
core (everything except `web.py` / `ui/` / `extension/`, which P2 ports per
`docs/research/contract.md`). Everything here is grounded in the research docs + the live
smoke run; `[INFERRED]` marks anything not directly observed.

## What was ported (files I own)
`models.py, poeninja.py, trade.py, statmap.py, currency.py, pricing.py, pob.py, engine.py,
report.py, cli.py, cache.py, __init__.py, tests.py` + `docs/research/contract.md`.
Verified: all target modules import clean; `python tests.py` green (offline); one live
end-to-end smoke run succeeded (evidence at the bottom).

## Decisions to record (D-0003+)

- **Currency = Chaos base, rates from poe.ninja (no trade exchange needed).**
  `CurrencyConverter._BASE="chaos"`, `rate("chaos")=1.0`. Rates come from the poe.ninja
  Currency economy where `line.primaryValue` is ALREADY the price in chaos (no rate
  multiply, unlike the PoE2 parent). `divine_rate()` = the Divine currency line's
  `primaryValue` (~102-104 chaos/div). The trade `exchange` endpoint is now only a
  fallback for a currency poe.ninja doesn't list -> the parent's per-run ban-risk exchange
  call is eliminated for the normal path.

- **Gems priced as real items (name+level+quality+corruption), every gem counts.**
  PoE1 gems are tradeable cut gems. `price_skill` prices the active gem PLUS **every**
  support gem (Awakened/Empower/Enlighten supports are often the biggest cost) via the
  poe.ninja SkillGem item-overview (`chaosValue` per matched bucket). Bucket match =
  exact name (case-insensitive) then nearest level/quality with a corrupted-match
  preference (economy.md 3c). The whole PoE2 uncut-gem + Jeweller's-Orb-ladder + lineage
  model is DELETED. **Method string stays `"skill"`** so web.py's `_METHOD_OK` is
  unaffected. Group total surfaces as the row's `chaos.{min==median==high}` (point
  estimate); per-gem breakdown rides in `PriceResult.extra` for the UI.

- **Sockets / LINKS are a new price component.** `Item` gained `sockets`, `max_link`,
  `total_sockets`, `socket_colours` (from the poe.ninja/PoB socket data). Any item with
  `max_link >= 5` (body armour / 2H weapon) gets a `socket_filters.links` min added to its
  unique AND rare trade searches so a 6L compares to 6Ls. Confirmed live: a `links` filter
  is accepted by the PoE1 search API (trade1.md 2b).

- **Defence totals via `armour_filters` (not `equipment_filters`).** PoE1 has no
  `equipment_filters`; ar/ev/es/ward field names are unchanged, only the group renamed.

- **Fetched-listing mods are OBJECTS, not strings.** PoE1 `item.explicitMods` entries are
  `{description, hash, mods:[...]}`. `pricing._search_listings` now reads `m["description"]`
  (guarded) for the version-unique pattern detection. (statmap is unaffected -- it maps the
  build's poe.ninja/PoB mod strings, not trade-listing mods.)

- **Rune / charm / desecrated concepts DELETED (clean cutover, RULE 6).** No `CAT_RUNE`,
  no rune group/section, no `price_rune`/`_RUNE_ECON_CATS`/`dedupe_runes`, no frame-5
  socketedItems extraction, no lineage/uncut methods, no `desecratedMods` bucket, no Charm
  slot/category. "Flasks & Charms" -> "Flasks". Gem `socketedItems` are the GEMS (also in
  `skills[]`, priced there -> not double-counted).

- **poe.ninja economy uses TWO endpoints.** `/poe1/api/economy/exchange/current/overview`
  (fungible currency: `{core,items,lines}`) and `/poe1/api/economy/stash/current/item/overview`
  (variant items incl. `SkillGem`: `{lines:[...]}` only). The old flat
  `/api/data/currencyoverview` + `itemoverview` are 404 (economy.md 0).

- **Pricer/converter wiring.** `Pricer.__init__` gained `economy=` (a `PoeNinjaEconomy`),
  injected by `engine.prepare_*` and passed into `CurrencyConverter(client, economy)`. The
  parent's post-hoc `pricer.economy = ...` assignment is gone (constructor injection).

- **Engine->UI JSON contract** stays structurally identical; only currency (`exalted`->
  `chaos`, `divine_to_exalted`->`divine_to_chaos`, `totals_exalted`->`totals_chaos`) and
  taxonomy (rune section removed, gem `extra` reshaped uncut/lineage -> `total_chaos`/`gems`)
  changed. Full rename map for P2 in `docs/research/contract.md`.

## Surprises / judgment calls

- **D-0002 endpoint correction (already flagged in taxonomy.md 8) is confirmed live:** the
  poe.ninja PoE1 API is `https://poe.ninja/poe1/api/...` (NOT `/api/...`). The smoke run's
  character fetch + economy calls all used `/poe1/` and succeeded.

- **Kept a reshaped `supports` list** even though taxonomy.md 6 says "drop supports". The
  gem-pricing authority (economy.md 3c.4) requires pricing every socketed gem, and PoE1
  support gems are expensive real items -> the support list (now `{name,level,quality,
  corrupted,icon}`, lineage dropped) is load-bearing for correct gem totals. economy.md
  governs this detail; noted so the log reflects the reconciliation.

- **`gemQuality`/`corrupted` in SkillGem lines can be `null`** -> treated as 0 / False.
  Gem `allGems[]` entries carry clean top-level `level`/`quality` ints, used directly.

- **PoB support `nameSpec` lacks the "Support" suffix** (`"Empower"` vs overview
  `"Empower Support"`). `gem_price` retries with `" Support"` appended. `[INFERRED]` but
  test-covered.

- **`utilityMods` folded into flask mod buckets** (tagged `explicit` group) so a unique/
  enchanted flask's defining line is searchable (poeninja-poe1.md 7).

- **SEARCH_BUDGET=30 (unchanged from parent)** means a heavy build (this smoke char has 19
  jewels) hits the cap and marks the overflow "skipped" -- designed ban-safety, not a bug.
  Owner may want to raise it for jewel-heavy builds (trade-off: more trade load). Left at
  the parent's value for parity; flag for owner if desired.

- **`socket_filters` colour/attr sub-counts NOT used** (only `links.min`, which is
  live-confirmed). Colour sub-filters are `[INFERRED]` in trade1.md and untested; skipped.

## Verification evidence
- Rate limiter parses the live 3-part PoE1 header
  `X-Rate-Limit-Ip: 5:10:60,15:60:300,30:300:1800,600:21600:3600`, only ever tightens,
  effective caps stay under margin (search cap 5 -> eff 3). Seeded from the live windows.
- **Live smoke** (`python -m bpc "<example-0416/TestCharacter>" --json`): Elementalist
  L100, Allflame. 41 items (11 equipment / 5 flask / 19 jewel / 6 gem), 17 priced (rest hit
  the 30-search budget). `currency_unit="chaos"`, `divine_to_chaos=103.6`, no `exalted`
  anywhere. Sane chaos: The Gull 10.5c, Death Rush 280c, Headhunter ~17,612c (~170 div,
  realistic), Ethereal Knives skill setup 1670c; an untracked item-granted gem correctly
  showed no number. Every `trade_url` is `https://www.pathofexile.com/trade/search/Allflame?q=...`
  (0 with `trade2`/`poe2`). No 429s / back-offs during the run.
